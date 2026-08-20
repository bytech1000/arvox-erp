import json
import zipfile
from datetime import date, datetime
from io import BytesIO

from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, url_for
from sqlalchemy import inspect as sa_inspect, text

from . import db
from .auth import login_required
from .models import (
    CashMovement,
    FinancialAccount,
    MasterCatalogItem,
    Customer,
    Expense,
    Product,
    Purchase,
    PurchaseItem,
    Quote,
    QuoteItem,
    SaleItem,
    SalesOrder,
    StockAdjustment,
    Supplier,
    SystemSetting,
    User,
)

maintenance_bp = Blueprint("maintenance", __name__, url_prefix="/maintenance")

BACKUP_FORMAT = "ARVOX_BACKUP_V2"
BACKUP_MEMBER = "arvox_backup.json"

# Dependency order for creating and reverse dependency order for deleting.
BACKUP_MODELS = (
    FinancialAccount,
    MasterCatalogItem,
    Product,
    Supplier,
    Customer,
    Purchase,
    PurchaseItem,
    SalesOrder,
    SaleItem,
    Quote,
    QuoteItem,
    Expense,
    CashMovement,
    FinancialAccount,
    MasterCatalogItem,
    StockAdjustment,
)
DELETE_MODELS = tuple(reversed(BACKUP_MODELS))


def get_setting(key, default=None):
    row = SystemSetting.query.filter_by(key=key).first()
    return row.value if row else default


def set_setting(key, value):
    row = SystemSetting.query.filter_by(key=key).first()
    if row:
        row.value = str(value)
    else:
        db.session.add(SystemSetting(key=key, value=str(value)))


def encode_value(value):
    if isinstance(value, datetime):
        return {"__type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"__type__": "date", "value": value.isoformat()}
    return value


def decode_value(value):
    if isinstance(value, dict) and value.get("__type__") == "datetime":
        return datetime.fromisoformat(value["value"])
    if isinstance(value, dict) and value.get("__type__") == "date":
        return date.fromisoformat(value["value"])
    return value


def serialize_row(row):
    mapper = sa_inspect(row.__class__)
    return {
        column.key: encode_value(getattr(row, column.key))
        for column in mapper.columns
    }


def business_counts():
    return {
        "financial_accounts": FinancialAccount.query.count(),
        "catalog_items": MasterCatalogItem.query.count(),
        "products": Product.query.count(),
        "suppliers": Supplier.query.count(),
        "customers": Customer.query.count(),
        "purchases": Purchase.query.count(),
        "sales": SalesOrder.query.count(),
        "quotes": Quote.query.count(),
        "expenses": Expense.query.count(),
        "cash_movements": CashMovement.query.count(),
        "stock_adjustments": StockAdjustment.query.count(),
    }


def delete_business_data():
    for model in DELETE_MODELS:
        db.session.query(model).delete(synchronize_session=False)
    set_setting("skip_demo_seed", "1")
    set_setting("last_reset_at", datetime.utcnow().isoformat())
    db.session.flush()


def reset_sequences_if_sqlite():
    if db.engine.dialect.name != "sqlite":
        return
    try:
        names = [model.__tablename__ for model in BACKUP_MODELS]
        quoted = ",".join(f"'{name}'" for name in names)
        db.session.execute(text(f"DELETE FROM sqlite_sequence WHERE name IN ({quoted})"))
    except Exception:
        # Some SQLite files do not have sqlite_sequence. IDs still remain valid.
        pass


@maintenance_bp.get("/")
@login_required
def index():
    counts = business_counts()
    total_records = sum(counts.values())
    database_kind = db.engine.dialect.name.upper()
    return render_template(
        "maintenance/index.html",
        counts=counts,
        total_records=total_records,
        database_kind=database_kind,
        last_backup=get_setting("last_backup_at"),
        last_restore=get_setting("last_restore_at"),
        last_reset=get_setting("last_reset_at"),
        version="6.3.0",
    )


@maintenance_bp.get("/backup")
@login_required
def backup():
    payload = {
        "format": BACKUP_FORMAT,
        "created_at": datetime.utcnow().isoformat(),
        "app_version": "6.3.0",
        "database": db.engine.dialect.name,
        "includes": ["cuentas_financieras", "catalogo_maestro", "productos", "proveedores", "clientes", "compras", "ventas", "cotizaciones", "gastos", "caja", "stock"],
        "counts": business_counts(),
        "tables": {
            model.__tablename__: [serialize_row(row) for row in model.query.order_by(model.id).all()]
            for model in BACKUP_MODELS
        },
    }

    raw_json = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(BACKUP_MEMBER, raw_json)
        zf.writestr(
            "LEEME.txt",
            "Respaldo completo de ARVOX ERP 6.3.0. Incluye Catálogo Maestro y todos los datos comerciales. Restauralo solamente desde Configuración > Mantenimiento.\n",
        )
    archive.seek(0)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    set_setting("last_backup_at", datetime.utcnow().isoformat())
    db.session.commit()

    return send_file(
        archive,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"ARVOX_BACKUP_{timestamp}.zip",
    )


@maintenance_bp.post("/restore")
@login_required
def restore():
    if request.form.get("confirmation", "").strip().upper() != "RESTAURAR":
        flash("Escribí RESTAURAR para confirmar la restauración.", "error")
        return redirect(url_for("maintenance.index"))

    uploaded = request.files.get("backup_file")
    if not uploaded or not uploaded.filename:
        flash("Seleccioná un archivo de respaldo de ARVOX.", "error")
        return redirect(url_for("maintenance.index"))

    try:
        raw = uploaded.read()
        if len(raw) > 25 * 1024 * 1024:
            raise ValueError("El respaldo supera el tamaño permitido de 25 MB.")

        with zipfile.ZipFile(BytesIO(raw), "r") as zf:
            if BACKUP_MEMBER not in zf.namelist():
                raise ValueError("El ZIP no contiene un respaldo válido de ARVOX.")
            payload = json.loads(zf.read(BACKUP_MEMBER).decode("utf-8"))

        if payload.get("format") not in {BACKUP_FORMAT, "ARVOX_BACKUP_V1"}:
            raise ValueError("El formato del respaldo no es compatible.")

        tables = payload.get("tables")
        if not isinstance(tables, dict):
            raise ValueError("El respaldo está incompleto.")

        delete_business_data()
        reset_sequences_if_sqlite()

        for model in BACKUP_MODELS:
            rows = tables.get(model.__tablename__, [])
            if not isinstance(rows, list):
                raise ValueError(f"Datos inválidos en {model.__tablename__}.")
            valid_columns = {column.key for column in sa_inspect(model).columns}
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError(f"Registro inválido en {model.__tablename__}.")
                values = {
                    key: decode_value(value)
                    for key, value in row.items()
                    if key in valid_columns
                }
                db.session.add(model(**values))
            db.session.flush()

        set_setting("skip_demo_seed", "1")
        set_setting("last_restore_at", datetime.utcnow().isoformat())
        db.session.commit()
        flash("Respaldo restaurado correctamente.", "success")
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("No se pudo restaurar el respaldo")
        flash(f"No se pudo restaurar el respaldo: {exc}", "error")

    return redirect(url_for("maintenance.index"))


@maintenance_bp.post("/reset")
@login_required
def reset():
    if request.form.get("confirmation", "").strip().upper() != "REINICIAR":
        flash("Escribí REINICIAR para confirmar el borrado.", "error")
        return redirect(url_for("maintenance.index"))

    try:
        delete_business_data()
        reset_sequences_if_sqlite()
        db.session.commit()
        flash(
            "ARVOX quedó vacío. Se conservó el usuario administrador y toda la estructura del sistema.",
            "success",
        )
    except Exception:
        db.session.rollback()
        current_app.logger.exception("No se pudo reiniciar ARVOX")
        flash("No se pudo reiniciar la base de datos.", "error")

    return redirect(url_for("maintenance.index"))


@maintenance_bp.post("/integrity")
@login_required
def integrity():
    try:
        if db.engine.dialect.name == "sqlite":
            result = db.session.execute(text("PRAGMA integrity_check")).scalar()
            if result != "ok":
                raise ValueError(str(result))
        else:
            db.session.execute(text("SELECT 1"))
        flash("La conexión y la integridad básica de la base son correctas.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(f"La verificación detectó un problema: {exc}", "error")
    return redirect(url_for("maintenance.index"))
