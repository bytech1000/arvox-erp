from flask import Flask
from sqlalchemy import inspect, text

from .extensions import db


def prepare_database(app: Flask) -> None:
    """Crea tablas, aplica migraciones compatibles y carga datos iniciales."""
    with app.app_context():
        db.create_all()
        migrate_schema()
        normalize_currency_to_ars()
        seed_financial_accounts()
        assign_historical_financial_accounts()
        seed_data(app)
        seed_master_catalog()


def migrate_schema() -> None:
    """Migraciones pequeñas y seguras para instalaciones SQLite existentes."""
    inspector = inspect(db.engine)
    table_names = set(inspector.get_table_names())

    if "product" in table_names:
        product_columns = {
            column["name"] for column in inspector.get_columns("product")
        }
        additions = {
            "currency": "VARCHAR(10) DEFAULT 'ARS'",
            "opening_stock": "INTEGER DEFAULT 0",
            "opening_cost": "FLOAT DEFAULT 0",
        }
        for name, definition in additions.items():
            if name not in product_columns:
                db.session.execute(
                    text(f"ALTER TABLE product ADD COLUMN {name} {definition}")
                )

    if "purchase_item" in table_names:
        purchase_item_columns = {
            column["name"] for column in inspector.get_columns("purchase_item")
        }
        additions = {
            "purchase_unit": "VARCHAR(40) DEFAULT 'Unidad'",
            "stock_unit": "VARCHAR(40) DEFAULT 'Unidad'",
            "conversion_factor": "INTEGER DEFAULT 1",
        }
        for name, definition in additions.items():
            if name not in purchase_item_columns:
                db.session.execute(
                    text(f"ALTER TABLE purchase_item ADD COLUMN {name} {definition}")
                )


    if "cash_movement" in table_names:
        cash_columns = {
            column["name"] for column in inspector.get_columns("cash_movement")
        }
        additions = {
            "account_id": "INTEGER",
            "transfer_group": "VARCHAR(64)",
        }
        for name, definition in additions.items():
            if name not in cash_columns:
                db.session.execute(
                    text(f"ALTER TABLE cash_movement ADD COLUMN {name} {definition}")
                )

    db.session.commit()


def seed_data(app: Flask) -> None:
    """Crea únicamente el usuario administrador.

    ARVOX no vuelve a cargar productos ni proveedores de demostración.
    De esta forma, un reinicio o un nuevo despliegue conserva el sistema vacío.
    """
    from .models import User

    if not User.query.first():
        user = User(username=app.config["ADMIN_USER"])
        user.set_password(app.config["ADMIN_PASSWORD"])
        db.session.add(user)

    db.session.commit()



def seed_financial_accounts():
    """Crea las dos cuentas iniciales de ARVOX."""
    from .models import FinancialAccount

    defaults = (
        ("Caja chica", "Efectivo"),
        ("Ualá", "Cuenta digital"),
    )
    for name, account_type in defaults:
        if not FinancialAccount.query.filter_by(name=name).first():
            db.session.add(FinancialAccount(name=name, account_type=account_type))
    db.session.commit()


def assign_historical_financial_accounts():
    """Clasifica una única vez los movimientos existentes sin cambiar importes."""
    from .models import CashMovement, FinancialAccount, SystemSetting

    setting = SystemSetting.query.filter_by(key="financial_accounts_v1_migrated").first()
    if setting:
        return

    cash = FinancialAccount.query.filter_by(name="Caja chica").first()
    uala = FinancialAccount.query.filter_by(name="Ualá").first()
    if not cash or not uala:
        return

    for movement in CashMovement.query.filter(CashMovement.account_id.is_(None)).all():
        movement.account_id = cash.id if movement.payment_method == "Efectivo" else uala.id

    db.session.add(SystemSetting(key="financial_accounts_v1_migrated", value="1"))
    db.session.commit()


def normalize_currency_to_ars():
    """Force every monetary record to Argentine pesos."""
    table_names = [
        "product", "supplier", "purchase", "sales_order",
        "quote", "cash_movement", "expense"
    ]
    with db.engine.begin() as conn:
        inspector = inspect(db.engine)
        existing = set(inspector.get_table_names())
        for table in table_names:
            if table in existing:
                columns = {c["name"] for c in inspector.get_columns(table)}
                if "currency" in columns:
                    conn.exec_driver_sql(f"UPDATE {table} SET currency = 'ARS' WHERE currency IS NULL OR currency <> 'ARS'")


def seed_master_catalog():
    """Carga una única vez la Base Maestra entregada por el usuario."""
    from .catalog_seed import MASTER_CATALOG
    from .models import MasterCatalogItem, SystemSetting

    setting = SystemSetting.query.filter_by(key="master_catalog_v1_loaded").first()
    if setting:
        return

    existing = {
        (row.brand.casefold(), row.model.casefold())
        for row in MasterCatalogItem.query.all()
    }
    for brand, model in MASTER_CATALOG:
        key = (brand.casefold(), model.casefold())
        if key not in existing:
            db.session.add(MasterCatalogItem(brand=brand, model=model))
            existing.add(key)

    db.session.add(SystemSetting(key="master_catalog_v1_loaded", value="148"))
    db.session.commit()
