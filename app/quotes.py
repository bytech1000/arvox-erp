from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy import or_
from . import db
from .auth import login_required
from .models import Quote, QuoteItem, Product, Customer, SalesOrder, SaleItem

quotes_bp = Blueprint("quotes", __name__, url_prefix="/quotes")

VALID_STATUSES = ("Borrador", "Enviada", "Aceptada", "Rechazada", "Vencida", "Convertida")

def next_quote_number():
    last = Quote.query.order_by(Quote.id.desc()).first()
    next_id = (last.id + 1) if last else 1
    return f"COT-{next_id:06d}"

def parse_items(form):
    product_ids = form.getlist("product_id[]")
    quantities = form.getlist("quantity[]")
    prices = form.getlist("unit_price[]")
    discounts = form.getlist("discount_pct[]")

    items = []
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

        items.append((product, qty, unit_price, discount_pct))

    if not items:
        raise ValueError("Agregá al menos un producto.")

    return items

def apply_items(quote, items):
    quote.items.clear()
    for product, qty, unit_price, discount_pct in items:
        quote.items.append(QuoteItem(
            product_id=product.id,
            quantity=qty,
            unit_price=unit_price,
            discount_pct=discount_pct,
            cost_snapshot=product.avg_cost,
        ))

def validate_stock_for_conversion(quote):
    requested = {}
    for item in quote.items:
        requested[item.product_id] = requested.get(item.product_id, 0) + item.quantity

    for product_id, qty in requested.items():
        product = Product.query.get(product_id)
        if qty > product.available_stock:
            raise ValueError(
                f"Stock insuficiente para {product.brand} {product.model}. "
                f"Disponible: {product.available_stock}."
            )

@quotes_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        try:
            date_value = datetime.strptime(request.form["date"], "%Y-%m-%d").date()
            valid_until = datetime.strptime(request.form["valid_until"], "%Y-%m-%d").date()
            customer_id = int(request.form["customer_id"])
            items = parse_items(request.form)
        except (ValueError, TypeError) as exc:
            flash(str(exc), "error")
            return redirect(url_for("quotes.index"))

        customer = Customer.query.get(customer_id)
        if not customer or not customer.active:
            flash("El cliente seleccionado no está disponible.", "error")
            return redirect(url_for("quotes.index"))

        quote = Quote(
            number=next_quote_number(),
            date=date_value,
            valid_until=valid_until,
            customer_id=customer.id,
            customer=customer.name,
            currency=request.form.get("currency") or "USD",
            status=request.form.get("status") or "Borrador",
            notes=request.form.get("notes", "").strip() or None,
        )
        apply_items(quote, items)
        db.session.add(quote)
        db.session.commit()

        flash("Cotización creada correctamente.", "success")
        return redirect(url_for("quotes.detail", quote_id=quote.id))

    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    customer_id = request.args.get("customer_id", "")

    query = Quote.query

    if q:
        term = f"%{q}%"
        query = query.filter(or_(
            Quote.number.ilike(term),
            Quote.customer.ilike(term),
        ))
    if status:
        query = query.filter_by(status=status)
    if customer_id:
        query = query.filter_by(customer_id=int(customer_id))

    rows = query.order_by(Quote.date.desc(), Quote.id.desc()).all()
    customers = Customer.query.filter_by(active=True).order_by(Customer.name).all()
    products = Product.query.filter_by(active=True).order_by(Product.brand, Product.model).all()

    totals = {
        "count": len(rows),
        "amount": sum(q.total for q in rows if q.status not in ("Rechazada", "Vencida")),
        "accepted": sum(q.total for q in rows if q.status in ("Aceptada", "Convertida")),
        "converted": sum(1 for q in rows if q.status == "Convertida"),
    }

    return render_template(
        "quotes/index.html",
        rows=rows,
        customers=customers,
        products=products,
        totals=totals,
        q=q,
        selected_status=status,
        selected_customer=customer_id,
        default_date=datetime.now().date().isoformat(),
        default_valid_until=(datetime.now().date() + timedelta(days=15)).isoformat(),
    )

@quotes_bp.route("/<int:quote_id>")
@login_required
def detail(quote_id):
    quote = Quote.query.get_or_404(quote_id)
    return render_template("quotes/detail.html", quote=quote)

@quotes_bp.route("/<int:quote_id>/edit", methods=["GET", "POST"])
@login_required
def edit(quote_id):
    quote = Quote.query.get_or_404(quote_id)

    if quote.status == "Convertida":
        flash("Una cotización convertida no puede editarse.", "error")
        return redirect(url_for("quotes.detail", quote_id=quote.id))

    if request.method == "POST":
        try:
            quote.date = datetime.strptime(request.form["date"], "%Y-%m-%d").date()
            quote.valid_until = datetime.strptime(request.form["valid_until"], "%Y-%m-%d").date()
            customer_id = int(request.form["customer_id"])
            items = parse_items(request.form)
        except (ValueError, TypeError) as exc:
            flash(str(exc), "error")
            return redirect(url_for("quotes.edit", quote_id=quote.id))

        customer = Customer.query.get(customer_id)
        if not customer or not customer.active:
            flash("El cliente seleccionado no está disponible.", "error")
            return redirect(url_for("quotes.edit", quote_id=quote.id))

        quote.customer_id = customer.id
        quote.customer = customer.name
        quote.currency = request.form.get("currency") or "USD"
        quote.status = request.form.get("status") or "Borrador"
        quote.notes = request.form.get("notes", "").strip() or None
        apply_items(quote, items)

        db.session.commit()
        flash("Cotización actualizada.", "success")
        return redirect(url_for("quotes.detail", quote_id=quote.id))

    customers = Customer.query.filter_by(active=True).order_by(Customer.name).all()
    products = Product.query.filter_by(active=True).order_by(Product.brand, Product.model).all()
    return render_template(
        "quotes/edit.html",
        quote=quote,
        customers=customers,
        products=products,
    )

@quotes_bp.post("/<int:quote_id>/status/<status>")
@login_required
def change_status(quote_id, status):
    quote = Quote.query.get_or_404(quote_id)
    if status not in VALID_STATUSES or status == "Convertida":
        flash("Estado inválido.", "error")
        return redirect(url_for("quotes.detail", quote_id=quote.id))
    if quote.status == "Convertida":
        flash("La cotización ya fue convertida en venta.", "error")
        return redirect(url_for("quotes.detail", quote_id=quote.id))

    quote.status = status
    db.session.commit()
    flash("Estado actualizado.", "success")
    return redirect(url_for("quotes.detail", quote_id=quote.id))

@quotes_bp.post("/<int:quote_id>/duplicate")
@login_required
def duplicate(quote_id):
    source = Quote.query.get_or_404(quote_id)
    duplicate = Quote(
        number=next_quote_number(),
        date=datetime.now().date(),
        valid_until=datetime.now().date() + timedelta(days=15),
        customer_id=source.customer_id,
        customer=source.customer,
        currency=source.currency,
        status="Borrador",
        notes=source.notes,
    )
    for item in source.items:
        duplicate.items.append(QuoteItem(
            product_id=item.product_id,
            quantity=item.quantity,
            unit_price=item.unit_price,
            discount_pct=item.discount_pct,
            cost_snapshot=item.product.avg_cost,
        ))

    db.session.add(duplicate)
    db.session.commit()
    flash("Cotización duplicada como nuevo borrador.", "success")
    return redirect(url_for("quotes.edit", quote_id=duplicate.id))

@quotes_bp.post("/<int:quote_id>/convert")
@login_required
def convert_to_sale(quote_id):
    quote = Quote.query.get_or_404(quote_id)

    if quote.status == "Convertida" or quote.converted_sale_id:
        flash("Esta cotización ya fue convertida.", "error")
        return redirect(url_for("quotes.detail", quote_id=quote.id))

    try:
        validate_stock_for_conversion(quote)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("quotes.detail", quote_id=quote.id))

    sale = SalesOrder(
        date=datetime.now().date(),
        reference=quote.number,
        customer_id=quote.customer_id,
        customer=quote.customer,
        whatsapp=quote.customer_record.whatsapp,
        currency=quote.currency,
        payment_method="Transferencia",
        collected=0,
        status="Entregada",
        notes=f"Venta generada desde {quote.number}" + (f". {quote.notes}" if quote.notes else ""),
    )

    for item in quote.items:
        sale.items.append(SaleItem(
            product_id=item.product_id,
            quantity=item.quantity,
            unit_price=item.unit_price,
            discount_pct=item.discount_pct,
            cost_snapshot=item.product.avg_cost,
        ))

    db.session.add(sale)
    db.session.flush()
    quote.status = "Convertida"
    quote.converted_sale_id = sale.id
    db.session.commit()

    flash("Cotización convertida en venta correctamente.", "success")
    return redirect(url_for("sales.detail", sale_id=sale.id))
