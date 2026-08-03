from urllib.parse import quote
from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy import or_
from . import db
from .auth import login_required
from .models import Customer

customers_bp = Blueprint("customers", __name__, url_prefix="/customers")

def normalize_whatsapp(value):
    if not value:
        return ""
    return "".join(ch for ch in value if ch.isdigit())

@customers_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        name = request.form["name"].strip()
        if Customer.query.filter(Customer.name.ilike(name)).first():
            flash("Ya existe un cliente con ese nombre.", "error")
            return redirect(url_for("customers.index"))

        customer = Customer(
            name=name,
            whatsapp=request.form.get("whatsapp", "").strip() or None,
            email=request.form.get("email", "").strip() or None,
            city=request.form.get("city", "").strip() or None,
            notes=request.form.get("notes", "").strip() or None,
            active=True,
        )
        db.session.add(customer)
        db.session.commit()
        flash("Cliente creado correctamente.", "success")
        return redirect(url_for("customers.detail", customer_id=customer.id))

    q = request.args.get("q", "").strip()
    active = request.args.get("active", "1")

    query = Customer.query

    if q:
        term = f"%{q}%"
        query = query.filter(or_(
            Customer.name.ilike(term),
            Customer.whatsapp.ilike(term),
            Customer.email.ilike(term),
            Customer.city.ilike(term),
        ))

    if active in ("0", "1"):
        query = query.filter_by(active=(active == "1"))

    rows = query.order_by(Customer.name).all()

    totals = {
        "customers": len(rows),
        "sales": sum(x.total_sold for x in rows),
        "collected": sum(x.total_collected for x in rows),
        "balance": sum(x.balance for x in rows),
    }

    return render_template(
        "customers/index.html",
        rows=rows,
        totals=totals,
        q=q,
        selected_active=active,
    )

@customers_bp.route("/<int:customer_id>")
@login_required
def detail(customer_id):
    customer = Customer.query.get_or_404(customer_id)

    whatsapp_number = normalize_whatsapp(customer.whatsapp)
    whatsapp_message = quote(f"Hola {customer.name}, te contacto desde ARVOX.")
    whatsapp_url = (
        f"https://wa.me/{whatsapp_number}?text={whatsapp_message}"
        if whatsapp_number else None
    )

    sales = sorted(
        customer.sales,
        key=lambda x: (x.date, x.id),
        reverse=True,
    )[:30]

    products = {}
    for sale in customer.sales:
        if sale.status == "Cancelada":
            continue
        for item in sale.items:
            key = item.product_id
            if key not in products:
                products[key] = {
                    "product": item.product,
                    "quantity": 0,
                    "amount": 0,
                }
            products[key]["quantity"] += item.quantity
            products[key]["amount"] += item.subtotal

    top_products = sorted(
        products.values(),
        key=lambda x: (x["quantity"], x["amount"]),
        reverse=True,
    )[:8]

    return render_template(
        "customers/detail.html",
        customer=customer,
        sales=sales,
        whatsapp_url=whatsapp_url,
        top_products=top_products,
    )

@customers_bp.route("/<int:customer_id>/edit", methods=["GET", "POST"])
@login_required
def edit(customer_id):
    customer = Customer.query.get_or_404(customer_id)

    if request.method == "POST":
        name = request.form["name"].strip()
        duplicate = Customer.query.filter(
            Customer.name.ilike(name),
            Customer.id != customer.id,
        ).first()

        if duplicate:
            flash("Ese nombre pertenece a otro cliente.", "error")
            return redirect(url_for("customers.edit", customer_id=customer.id))

        customer.name = name
        customer.whatsapp = request.form.get("whatsapp", "").strip() or None
        customer.email = request.form.get("email", "").strip() or None
        customer.city = request.form.get("city", "").strip() or None
        customer.notes = request.form.get("notes", "").strip() or None

        db.session.commit()
        flash("Cliente actualizado.", "success")
        return redirect(url_for("customers.detail", customer_id=customer.id))

    return render_template("customers/edit.html", customer=customer)

@customers_bp.post("/<int:customer_id>/toggle")
@login_required
def toggle(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    customer.active = not customer.active
    db.session.commit()
    flash("Estado del cliente actualizado.", "success")
    return redirect(url_for("customers.index"))
