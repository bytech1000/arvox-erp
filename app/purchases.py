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
    StockAdjustment,
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
    purchase_units = form.getlist("purchase_unit[]")
    stock_units = form.getlist("stock_unit[]")
    conversion_factors = form.getlist("conversion_factor[]")

    lines = []
    seen = set()
    created_count = 0

    for raw_catalog_id, raw_qty, raw_cost, purchase_unit, stock_unit, raw_factor in zip(catalog_ids, quantities, unit_costs, purchase_units, stock_units, conversion_factors):
        if not raw_catalog_id:
            continue

        try:
            catalog_id = int(raw_catalog_id)
            qty = int(raw_qty)
            cost = float(raw_cost)
            factor = int(raw_factor or 1)
        except (ValueError, TypeError):
            raise ValueError("Revisá los modelos, cantidades y costos.")

        if qty <= 0 or cost < 0 or factor <= 0:
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
        lines.append((product, qty, cost, clean_text(purchase_unit) or "Unidad", clean_text(stock_unit) or "Unidad", factor))

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

        for product, qty, cost, purchase_unit, stock_unit, factor in lines:
            purchase.items.append(
                PurchaseItem(
                    product_id=product.id, quantity=qty, unit_cost=cost,
                    purchase_unit=purchase_unit, stock_unit=stock_unit,
                    conversion_factor=factor
                )
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
    catalog_brands = sorted({item.brand for item in catalog_items}, key=str.casefold)
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
        catalog_brands=catalog_brands,
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


@purchases_bp.post("/<int:purchase_id>/receive")
@login_required
def receive(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)
    if purchase.status == "Cancelada":
        flash("Una compra cancelada no puede recibirse.", "error")
        return redirect(url_for("purchases.detail", purchase_id=purchase.id))
    if purchase.status == "Recibida":
        flash("La compra ya estaba recibida. El stock no se modificó nuevamente.", "success")
        return redirect(url_for("purchases.detail", purchase_id=purchase.id))
    purchase.status = "Recibida"
    db.session.commit()
    flash("Compra marcada como recibida. Las unidades ingresaron al stock una sola vez.", "success")
    return redirect(url_for("purchases.detail", purchase_id=purchase.id))


@purchases_bp.post("/<int:purchase_id>/delete")
@login_required
def delete(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)

    # A received purchase can only be removed if its reversal does not
    # leave any involved product with negative physical stock.
    if purchase.status == "Recibida":
        quantities = {}
        for item in purchase.items:
            quantities[item.product_id] = quantities.get(item.product_id, 0) + item.stock_quantity

        shortages = []
        for product_id, quantity in quantities.items():
            product = Product.query.get(product_id)
            resulting_stock = product.stock - quantity
            if resulting_stock < 0:
                shortages.append(
                    f"{product.brand} {product.model} (quedaría en {resulting_stock})"
                )

        if shortages:
            flash(
                "No se puede eliminar la compra porque dejaría stock negativo en: "
                + "; ".join(shortages)
                + ". Revisá las ventas o movimientos posteriores.",
                "error",
            )
            return redirect(url_for("purchases.detail", purchase_id=purchase.id))

    reference = purchase.reference or f"Compra #{purchase.id}"

    # Delete linked cash movements first so PostgreSQL foreign keys remain valid.
    for movement in list(purchase.cash_movements):
        db.session.delete(movement)

    db.session.delete(purchase)
    db.session.commit()
    flash(
        f"{reference} eliminada. Se revirtieron stock, deuda y pagos vinculados.",
        "success",
    )
    return redirect(url_for("purchases.index"))


@purchases_bp.post("/item/<int:item_id>/conversion")
@login_required
def update_conversion(item_id):
    """Corrige la unidad/factor de una línea histórica sin alterar el stock físico actual."""
    item = PurchaseItem.query.get_or_404(item_id)
    product = item.product
    old_physical_stock = product.stock

    try:
        factor = int(request.form.get("conversion_factor") or 1)
        if factor <= 0:
            raise ValueError
    except (ValueError, TypeError):
        flash("El factor de conversión debe ser un número entero mayor a cero.", "error")
        return redirect(url_for("purchases.detail", purchase_id=item.purchase_id))

    item.purchase_unit = clean_text(request.form.get("purchase_unit")) or "Unidad"
    item.stock_unit = clean_text(request.form.get("stock_unit")) or "Unidad"
    item.conversion_factor = factor

    # Flush makes product.stock reflect the new conversion. We then create a
    # balancing adjustment so correcting a historical purchase never changes
    # what the user physically counted in the warehouse.
    db.session.flush()
    difference = old_physical_stock - product.stock
    if difference:
        db.session.add(StockAdjustment(
            product_id=product.id,
            date=datetime.today().date(),
            quantity=difference,
            reason="Corrección por conversión de unidad",
            notes=f"Conversión histórica compra #{item.purchase_id}: 1 {item.purchase_unit} = {factor} {item.stock_unit}. Stock físico preservado en {old_physical_stock}."
        ))

    db.session.commit()
    flash(
        f"Conversión actualizada. Stock físico: {product.stock} {item.stock_unit}. "
        f"Costo por {item.stock_unit}: ARS {item.inventory_unit_cost:.2f}.",
        "success",
    )
    return redirect(url_for("purchases.detail", purchase_id=item.purchase_id))
