from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import func, or_

from . import db
from .auth import login_required
from .models import (
    CashMovement,
    MasterCatalogItem,
    Product,
    Purchase,
    PurchaseItem,
    Supplier,
)

purchases_bp = Blueprint("purchases", __name__, url_prefix="/purchases")


def clean_text(value):
    return " ".join((value or "").strip().split())


def find_product_for_catalog_item(catalog_item):
    """Find the inventory product linked by normalized brand and model."""
    return Product.query.filter(
        func.lower(func.trim(Product.brand)) == catalog_item.brand.strip().casefold(),
        func.lower(func.trim(Product.model)) == catalog_item.model.strip().casefold(),
    ).first()


def generate_product_code(catalog_item):
    """Generate a stable, unique internal code for a catalog-created product."""
    base = f"ARX-{catalog_item.id:06d}"
    candidate = base
    suffix = 1
    while Product.query.filter_by(code=candidate).first():
        suffix += 1
        candidate = f"{base}-{suffix}"
    return candidate


def get_or_create_product(catalog_item):
    product = find_product_for_catalog_item(catalog_item)
    if product:
        if not product.active:
            product.active = True
        return product, False

    product = Product(
        code=generate_product_code(catalog_item),
        brand=clean_text(catalog_item.brand),
        model=clean_text(catalog_item.model),
        category="Paleta",
        currency="ARS",
        opening_stock=0,
        opening_cost=0,
        sale_price=0,
        min_stock=1,
        active=True,
        notes="Creado automáticamente desde el Catálogo Maestro al registrar una compra.",
    )
    db.session.add(product)
    db.session.flush()
    return product, True


def parse_lines(form):
    catalog_ids = form.getlist("catalog_item_id[]")
    quantities = form.getlist("quantity[]")
    unit_costs = form.getlist("unit_cost[]")

    lines = []
    seen = set()
    created_count = 0

    for raw_catalog_id, raw_qty, raw_cost in zip(catalog_ids, quantities, unit_costs):
        if not raw_catalog_id:
            continue

        try:
            catalog_id = int(raw_catalog_id)
            qty = int(raw_qty)
            cost = float(raw_cost)
        except (ValueError, TypeError):
            raise ValueError("Revisá los modelos, cantidades y costos.")

        if qty <= 0 or cost < 0:
            raise ValueError(
                "Las cantidades deben ser mayores a cero y los costos no pueden ser negativos."
            )
        if catalog_id in seen:
            raise ValueError(
                "Un modelo está repetido. Sumá sus unidades en una sola línea."
            )

        catalog_item = MasterCatalogItem.query.get(catalog_id)
        if not catalog_item or not catalog_item.active:
            raise ValueError("Uno de los modelos del Catálogo Maestro ya no está disponible.")

        product, created = get_or_create_product(catalog_item)
        created_count += int(created)
        seen.add(catalog_id)
        lines.append((product, qty, cost))

    if not lines:
        raise ValueError("Agregá al menos un modelo a la compra.")

    return lines, created_count


@purchases_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        try:
            date_value = datetime.strptime(request.form["date"], "%Y-%m-%d").date()
            supplier_id = int(request.form["supplier_id"])
            paid = float(request.form.get("paid") or 0)
            lines, created_count = parse_lines(request.form)
        except (ValueError, TypeError) as exc:
            db.session.rollback()
            flash(str(exc) or "Revisá los datos ingresados.", "error")
            return redirect(url_for("purchases.index"))

        supplier = Supplier.query.get(supplier_id)
        if not supplier or not supplier.active:
            db.session.rollback()
            flash("El proveedor seleccionado no está disponible.", "error")
            return redirect(url_for("purchases.index"))

        purchase = Purchase(
            date=date_value,
            reference=request.form.get("reference", "").strip() or None,
            supplier_id=supplier_id,
            currency="ARS",
            paid=paid,
            status=request.form.get("status") or "Recibida",
            notes=request.form.get("notes", "").strip() or None,
        )

        for product, qty, cost in lines:
            purchase.items.append(
                PurchaseItem(product_id=product.id, quantity=qty, unit_cost=cost)
            )

        db.session.add(purchase)
        db.session.flush()

        if paid > 0:
            purchase.cash_movements.append(
                CashMovement(
                    date=date_value,
                    movement_type="Egreso",
                    category="Pago a proveedor",
                    description=f"Pago inicial compra #{purchase.id} · {supplier.name}",
                    payment_method=request.form.get("payment_method") or "Transferencia",
                    currency="ARS",
                    amount=paid,
                )
            )

        db.session.commit()

        msg = (
            f"Compra guardada: {len(lines)} modelos y {purchase.units} unidades."
        )
        if created_count:
            msg += f" Se crearon {created_count} productos nuevos automáticamente."
        if purchase.status == "Pendiente":
            msg += " Los productos quedaron creados, pero la compra todavía no afecta el stock."
        else:
            msg += " Productos, costos y stock fueron actualizados."

        flash(msg, "success")
        return redirect(url_for("purchases.detail", purchase_id=purchase.id))

    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    supplier_id = request.args.get("supplier_id", "")

    query = Purchase.query.join(Supplier)
    if q:
        term = f"%{q}%"
        query = query.filter(
            or_(Purchase.reference.ilike(term), Supplier.name.ilike(term))
        )
    if status:
        query = query.filter(Purchase.status == status)
    if supplier_id:
        query = query.filter(Purchase.supplier_id == int(supplier_id))

    rows = query.order_by(Purchase.date.desc(), Purchase.id.desc()).all()
    catalog_items = (
        MasterCatalogItem.query.filter_by(active=True)
        .order_by(MasterCatalogItem.brand, MasterCatalogItem.model)
        .all()
    )
    suppliers = Supplier.query.filter_by(active=True).order_by(Supplier.name).all()
    totals = {
        "count": len(rows),
        "units": sum(p.units for p in rows if p.status == "Recibida"),
        "amount": sum(p.total for p in rows if p.status != "Cancelada"),
        "balance": sum(p.balance for p in rows if p.status != "Cancelada"),
    }

    return render_template(
        "purchases/index.html",
        rows=rows,
        catalog_items=catalog_items,
        suppliers=suppliers,
        totals=totals,
        q=q,
        selected_status=status,
        selected_supplier=supplier_id,
    )


@purchases_bp.route("/<int:purchase_id>")
@login_required
def detail(purchase_id):
    return render_template(
        "purchases/detail.html", purchase=Purchase.query.get_or_404(purchase_id)
    )


@purchases_bp.post("/<int:purchase_id>/cancel")
@login_required
def cancel(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)
    purchase.status = "Cancelada"
    db.session.commit()
    flash(
        "Compra cancelada. Todas sus líneas dejaron de afectar stock y costos.",
        "success",
    )
    return redirect(url_for("purchases.detail", purchase_id=purchase.id))
