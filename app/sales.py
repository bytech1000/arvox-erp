from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy import or_
from . import db
from .auth import login_required
from .models import Product, SalesOrder, SaleItem, Customer, CashMovement

sales_bp = Blueprint("sales", __name__, url_prefix="/sales")

def parse_items(form):
    product_ids = form.getlist("product_id[]")
    quantities = form.getlist("quantity[]")
    prices = form.getlist("unit_price[]")
    discounts = form.getlist("discount_pct[]")

    items = []
    requested = {}

    for product_id, quantity, price, discount in zip(product_ids, quantities, prices, discounts):
        if not product_id:
            continue
        product = Product.query.get(int(product_id))
        if not product or not product.active:
            raise ValueError("Uno de los productos ya no está disponible.")

        qty = int(quantity)
        unit_price = float(price)
        discount_pct = float(discount or 0)

        if qty <= 0 or unit_price < 0 or not 0 <= discount_pct <= 100:
            raise ValueError("Revisá cantidades, precios y descuentos.")

        requested[product.id] = requested.get(product.id, 0) + qty
        items.append((product, qty, unit_price, discount_pct))

    if not items:
        raise ValueError("Agregá al menos un producto.")

    return items, requested

def validate_stock(requested, status):
    if status not in ("Entregada", "Reservada"):
        return
    for product_id, qty in requested.items():
        product = Product.query.get(product_id)
        if qty > product.available_stock:
            raise ValueError(
                f"Stock insuficiente para {product.brand} {product.model}. "
                f"Disponible: {product.available_stock}."
            )

@sales_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        try:
            date_value = datetime.strptime(request.form["date"], "%Y-%m-%d").date()
            collected = float(request.form.get("collected") or 0)
            status = request.form.get("status") or "Entregada"
            items, requested = parse_items(request.form)
            validate_stock(requested, status)
        except (ValueError, TypeError) as exc:
            flash(str(exc), "error")
            return redirect(url_for("sales.index"))

        customer_id = int(request.form["customer_id"])
        customer = Customer.query.get(customer_id)
        if not customer or not customer.active:
            flash("El cliente seleccionado no está disponible.", "error")
            return redirect(url_for("sales.index"))

        sale = SalesOrder(
            date=date_value,
            reference=request.form.get("reference", "").strip() or None,
            customer_id=customer.id,
            customer=customer.name,
            whatsapp=customer.whatsapp or None,
            currency="ARS",
            payment_method=request.form.get("payment_method") or "Transferencia",
            collected=collected,
            status=status,
            notes=request.form.get("notes", "").strip() or None,
        )

        for product, qty, unit_price, discount_pct in items:
            sale.items.append(SaleItem(
                product_id=product.id,
                quantity=qty,
                unit_price=unit_price,
                discount_pct=discount_pct,
                cost_snapshot=product.avg_cost,
            ))

        if collected < 0:
            flash("El importe cobrado no puede ser negativo.", "error")
            return redirect(url_for("sales.index"))

        calculated_total = sum(
            qty * unit_price * (1 - discount_pct / 100)
            for _, qty, unit_price, discount_pct in items
        )
        if collected > calculated_total + 0.01:
            flash(
                f"El importe cobrado (ARS {collected:.2f}) no puede superar "
                f"el total calculado de la venta (ARS {calculated_total:.2f}).",
                "error",
            )
            return redirect(url_for("sales.index"))

        db.session.add(sale)
        db.session.flush()
        if collected > 0:
            sale.cash_movements.append(CashMovement(
                date=date_value, movement_type="Ingreso", category="Cobro de venta",
                description=f"Cobro inicial venta #{sale.id} · {sale.customer}",
                payment_method=sale.payment_method, currency=sale.currency, amount=collected,
            ))
        db.session.commit()
        flash("Venta registrada correctamente.", "success")
        return redirect(url_for("sales.detail", sale_id=sale.id))

    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    query = SalesOrder.query

    if q:
        term = f"%{q}%"
        query = query.filter(or_(
            SalesOrder.customer.ilike(term),
            SalesOrder.reference.ilike(term),
            SalesOrder.whatsapp.ilike(term),
        ))
    if status:
        query = query.filter_by(status=status)

    rows = query.order_by(SalesOrder.date.desc(), SalesOrder.id.desc()).all()
    products = Product.query.filter_by(active=True).order_by(Product.brand, Product.model).all()
    customers = Customer.query.filter_by(active=True).order_by(Customer.name).all()

    totals = {
        "count": len(rows),
        "units": sum(x.units for x in rows if x.status == "Entregada"),
        "amount": sum(x.total for x in rows if x.status != "Cancelada"),
        "profit": sum(x.profit for x in rows if x.status == "Entregada"),
        "balance": sum(x.balance for x in rows if x.status != "Cancelada"),
    }

    return render_template(
        "sales/index.html",
        rows=rows,
        products=products,
        customers=customers,
        totals=totals,
        q=q,
        selected_status=status,
    )

@sales_bp.route("/<int:sale_id>")
@login_required
def detail(sale_id):
    sale = SalesOrder.query.get_or_404(sale_id)
    return render_template("sales/detail.html", sale=sale)

@sales_bp.post("/<int:sale_id>/status/<status>")
@login_required
def change_status(sale_id, status):
    if status not in ("Reservada", "Entregada", "Cancelada"):
        flash("Estado inválido.", "error")
        return redirect(url_for("sales.detail", sale_id=sale_id))

    sale = SalesOrder.query.get_or_404(sale_id)

    if status in ("Reservada", "Entregada") and sale.status == "Cancelada":
        requested = {item.product_id: item.quantity for item in sale.items}
        try:
            validate_stock(requested, status)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("sales.detail", sale_id=sale.id))

    sale.status = status
    db.session.commit()
    flash("Estado de la venta actualizado.", "success")
    return redirect(url_for("sales.detail", sale_id=sale.id))
