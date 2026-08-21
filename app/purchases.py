from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import func, or_

from . import db
from .auth import login_required
from .models import (
    CashMovement,
    FinancialAccount,
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

    row_count = len(catalog_ids)
    if row_count == 0:
        raise ValueError("Agregá al menos un modelo a la compra.")

    field_lengths = {
        "modelos": len(catalog_ids),
        "cantidades": len(quantities),
        "costos": len(unit_costs),
        "unidades de compra": len(purchase_units),
        "unidades de stock": len(stock_units),
        "conversiones": len(conversion_factors),
    }
    if any(length != row_count for length in field_lengths.values()):
        raise ValueError(
            "La compra contiene una línea incompleta. Recargá la página y volvé a agregar los productos."
        )

    for index in range(row_count):
        raw_catalog_id = catalog_ids[index]
        raw_qty = quantities[index]
        raw_cost = unit_costs[index]
        purchase_unit = purchase_units[index]
        stock_unit = stock_units[index]
        raw_factor = conversion_factors[index]

        if not raw_catalog_id:
            continue

        try:
            catalog_id = int(raw_catalog_id)
            qty = int(raw_qty)
            cost = float(raw_cost)
            factor = int(raw_factor or 1)
        except (ValueError, TypeError):
            raise ValueError(f"Revisá los datos del producto #{index + 1}.")

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
            account = FinancialAccount.query.get(request.form.get("account_id", type=int))
            if not account or not account.active:
                db.session.rollback()
                flash("Seleccioná la cuenta desde la que pagaste.", "error")
                return redirect(url_for("purchases.index"))
            purchase.cash_movements.append(
                CashMovement(
                    date=date_value,
                    movement_type="Egreso",
                    category="Pago a proveedor",
                    description=f"Pago inicial compra #{purchase.id} · {supplier.name}",
                    payment_method=request.form.get("payment_method") or "Transferencia",
                    currency="ARS",
                    amount=paid,
                    account=account,
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
        "purchases/detail.html",
        purchase=Purchase.query.get_or_404(purchase_id),
        accounts=FinancialAccount.query.filter_by(active=True).order_by(FinancialAccount.id).all(),
    )


@purchases_bp.route("/<int:purchase_id>/edit", methods=["GET", "POST"])
@login_required
def edit_purchase(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)
    catalog_items = (
        MasterCatalogItem.query.filter_by(active=True)
        .order_by(MasterCatalogItem.brand, MasterCatalogItem.model)
        .all()
    )

    if request.method == "POST":
        try:
            purchase.date = datetime.strptime(request.form["date"], "%Y-%m-%d").date()
        except (ValueError, KeyError):
            flash("Revisá la fecha de la compra.", "error")
            return redirect(url_for("purchases.edit_purchase", purchase_id=purchase.id))

        item_ids = request.form.getlist("item_id[]")
        catalog_ids = request.form.getlist("catalog_item_id[]")
        quantities = request.form.getlist("quantity[]")
        unit_costs = request.form.getlist("unit_cost[]")
        purchase_units = request.form.getlist("purchase_unit[]")
        stock_units = request.form.getlist("stock_unit[]")
        factors = request.form.getlist("conversion_factor[]")
        delete_flags = request.form.getlist("delete_line[]")

        count = len(catalog_ids)
        if not count or any(len(v) != count for v in (
            item_ids, quantities, unit_costs, purchase_units, stock_units, factors, delete_flags
        )):
            flash("Hay una línea incompleta en la compra.", "error")
            return redirect(url_for("purchases.edit_purchase", purchase_id=purchase.id))

        parsed = []
        for idx in range(count):
            # Líneas marcadas para eliminar no requieren validar producto/costo.
            remove = delete_flags[idx] == "1"
            existing_id = int(item_ids[idx]) if item_ids[idx] else None

            if remove:
                if existing_id:
                    item = PurchaseItem.query.filter_by(
                        id=existing_id, purchase_id=purchase.id
                    ).first()
                    if item:
                        parsed.append({
                            "action": "delete",
                            "item": item,
                            "old_product_id": item.product_id,
                            "old_stock_qty": item.stock_quantity,
                        })
                continue

            try:
                catalog_id = int(catalog_ids[idx])
                qty = int(quantities[idx])
                cost = float(unit_costs[idx])
                factor = int(factors[idx] or 1)
            except (ValueError, TypeError):
                flash(f"Revisá los datos del producto #{idx + 1}.", "error")
                return redirect(url_for("purchases.edit_purchase", purchase_id=purchase.id))

            if qty <= 0 or cost < 0 or factor <= 0:
                flash(f"Cantidad, costo o conversión inválidos en producto #{idx + 1}.", "error")
                return redirect(url_for("purchases.edit_purchase", purchase_id=purchase.id))

            catalog = MasterCatalogItem.query.get(catalog_id)
            if not catalog:
                flash(f"No pude identificar el producto #{idx + 1}.", "error")
                return redirect(url_for("purchases.edit_purchase", purchase_id=purchase.id))

            product, _ = get_or_create_product(catalog)

            if existing_id:
                item = PurchaseItem.query.filter_by(
                    id=existing_id, purchase_id=purchase.id
                ).first()
                if not item:
                    flash("No pude identificar una línea existente de la compra.", "error")
                    return redirect(url_for("purchases.edit_purchase", purchase_id=purchase.id))
                parsed.append({
                    "action": "update",
                    "item": item,
                    "old_product_id": item.product_id,
                    "old_stock_qty": item.stock_quantity,
                    "product": product,
                    "qty": qty,
                    "cost": cost,
                    "purchase_unit": clean_text(purchase_units[idx]) or "Unidad",
                    "stock_unit": clean_text(stock_units[idx]) or "Unidad",
                    "factor": factor,
                })
            else:
                parsed.append({
                    "action": "add",
                    "product": product,
                    "qty": qty,
                    "cost": cost,
                    "purchase_unit": clean_text(purchase_units[idx]) or "Unidad",
                    "stock_unit": clean_text(stock_units[idx]) or "Unidad",
                    "factor": factor,
                })

        active_rows = [row for row in parsed if row["action"] != "delete"]
        if not active_rows:
            flash("La compra debe conservar al menos un producto.", "error")
            return redirect(url_for("purchases.edit_purchase", purchase_id=purchase.id))

        # Para compras recibidas, simula el impacto completo antes de guardar.
        if purchase.status == "Recibida":
            old_by_product = {}
            new_by_product = {}

            for item in purchase.items:
                old_by_product[item.product_id] = (
                    old_by_product.get(item.product_id, 0) + item.stock_quantity
                )

            for row in active_rows:
                new_qty = row["qty"] * row["factor"]
                product_id = row["product"].id
                new_by_product[product_id] = new_by_product.get(product_id, 0) + new_qty

            shortages = []
            for product_id in set(old_by_product) | set(new_by_product):
                product = Product.query.get(product_id)
                resulting = (
                    product.stock
                    - old_by_product.get(product_id, 0)
                    + new_by_product.get(product_id, 0)
                )
                if resulting < 0:
                    shortages.append(
                        f"{product.brand} {product.model} (quedaría en {resulting})"
                    )

            if shortages:
                db.session.rollback()
                flash(
                    "No se puede aplicar el cambio porque dejaría stock negativo en: "
                    + "; ".join(shortages),
                    "error",
                )
                return redirect(url_for("purchases.edit_purchase", purchase_id=purchase.id))

        # Aplicar eliminaciones / cambios / altas.
        for row in parsed:
            if row["action"] == "delete":
                db.session.delete(row["item"])
                continue

            if row["action"] == "update":
                item = row["item"]
            else:
                item = PurchaseItem()
                purchase.items.append(item)

            item.product = row["product"]
            item.quantity = row["qty"]
            item.unit_cost = row["cost"]
            item.purchase_unit = row["purchase_unit"]
            item.stock_unit = row["stock_unit"]
            item.conversion_factor = row["factor"]

        purchase.reference = clean_text(request.form.get("reference")) or None
        purchase.notes = request.form.get("notes", "").strip() or None
        db.session.flush()

        paid = purchase.paid or 0
        if paid > purchase.total:
            msg = (
                f"Compra actualizada. Total ARS {purchase.total:.2f}. "
                f"Saldo a favor ARS {paid - purchase.total:.2f}."
            )
        else:
            msg = (
                f"Compra actualizada. Total ARS {purchase.total:.2f}. "
                f"Pendiente ARS {purchase.balance:.2f}."
            )

        db.session.commit()
        flash(msg, "success")
        return redirect(url_for("purchases.detail", purchase_id=purchase.id))

    return render_template(
        "purchases/edit.html",
        purchase=purchase,
        catalog_items=catalog_items,
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
    old_factor = item.conversion_factor or 1

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

    # Limpia únicamente los ajustes compensatorios automáticos creados por
    # la primera versión de la conversión histórica. Esos ajustes preservaban
    # por error el stock anterior (ej.: 1 caja x24 seguía mostrando 1).
    legacy_prefix = f"Conversión histórica compra #{item.purchase_id}:"
    legacy_adjustments = StockAdjustment.query.filter(
        StockAdjustment.product_id == product.id,
        StockAdjustment.reason == "Corrección por conversión de unidad",
        StockAdjustment.notes.like(f"{legacy_prefix}%"),
    ).all()
    for adjustment in legacy_adjustments:
        db.session.delete(adjustment)

    # La compra histórica es la fuente del stock: cambiar su presentación
    # convierte también las unidades aportadas por esa compra.
    db.session.commit()
    flash(
        f"Conversión actualizada: {item.quantity} {item.purchase_unit} = "
        f"{item.stock_quantity} {item.stock_unit}. "
        f"Costo por {item.stock_unit}: ARS {item.inventory_unit_cost:.2f}.",
        "success",
    )
    return redirect(url_for("purchases.detail", purchase_id=item.purchase_id))
