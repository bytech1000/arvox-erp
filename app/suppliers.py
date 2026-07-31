from urllib.parse import quote
from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy import or_
from . import db
from .auth import login_required
from .models import Supplier

suppliers_bp = Blueprint("suppliers", __name__, url_prefix="/suppliers")

def normalize_whatsapp(value):
    if not value:
        return ""
    return "".join(ch for ch in value if ch.isdigit())

@suppliers_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        name = request.form["name"].strip()

        if Supplier.query.filter(Supplier.name.ilike(name)).first():
            flash("Ya existe un proveedor con ese nombre.", "error")
            return redirect(url_for("suppliers.index"))

        supplier = Supplier(
            name=name,
            contact=request.form.get("contact", "").strip() or None,
            whatsapp=request.form.get("whatsapp", "").strip() or None,
            email=request.form.get("email", "").strip() or None,
            city=request.form.get("city", "").strip() or None,
            website=request.form.get("website", "").strip() or None,
            payment_terms=request.form.get("payment_terms", "").strip() or None,
            currency=request.form.get("currency") or "USD",
            notes=request.form.get("notes", "").strip() or None,
            active=True,
        )
        db.session.add(supplier)
        db.session.commit()
        flash("Proveedor creado correctamente.", "success")
        return redirect(url_for("suppliers.detail", supplier_id=supplier.id))

    q = request.args.get("q", "").strip()
    active = request.args.get("active", "1")
    currency = request.args.get("currency", "").strip()

    query = Supplier.query

    if q:
        term = f"%{q}%"
        query = query.filter(or_(
            Supplier.name.ilike(term),
            Supplier.contact.ilike(term),
            Supplier.whatsapp.ilike(term),
            Supplier.email.ilike(term),
            Supplier.city.ilike(term),
        ))

    if active in ("0", "1"):
        query = query.filter_by(active=(active == "1"))

    if currency:
        query = query.filter_by(currency=currency)

    rows = query.order_by(Supplier.name).all()

    totals = {
        "suppliers": len(rows),
        "purchases": sum(x.total_purchased for x in rows),
        "balance": sum(x.balance for x in rows),
        "active": sum(1 for x in rows if x.active),
    }

    return render_template(
        "suppliers/index.html",
        rows=rows,
        totals=totals,
        q=q,
        selected_active=active,
        selected_currency=currency,
    )

@suppliers_bp.route("/<int:supplier_id>")
@login_required
def detail(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    whatsapp_number = normalize_whatsapp(supplier.whatsapp)
    whatsapp_message = quote(
        f"Hola {supplier.contact or supplier.name}, te contacto desde ARVOX."
    )
    whatsapp_url = (
        f"https://wa.me/{whatsapp_number}?text={whatsapp_message}"
        if whatsapp_number else None
    )

    purchases = sorted(
        supplier.purchases,
        key=lambda x: (x.date, x.id),
        reverse=True,
    )[:30]

    return render_template(
        "suppliers/detail.html",
        supplier=supplier,
        purchases=purchases,
        whatsapp_url=whatsapp_url,
    )

@suppliers_bp.route("/<int:supplier_id>/edit", methods=["GET", "POST"])
@login_required
def edit(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)

    if request.method == "POST":
        name = request.form["name"].strip()
        duplicate = Supplier.query.filter(
            Supplier.name.ilike(name),
            Supplier.id != supplier.id,
        ).first()

        if duplicate:
            flash("Ese nombre pertenece a otro proveedor.", "error")
            return redirect(url_for("suppliers.edit", supplier_id=supplier.id))

        supplier.name = name
        supplier.contact = request.form.get("contact", "").strip() or None
        supplier.whatsapp = request.form.get("whatsapp", "").strip() or None
        supplier.email = request.form.get("email", "").strip() or None
        supplier.city = request.form.get("city", "").strip() or None
        supplier.website = request.form.get("website", "").strip() or None
        supplier.payment_terms = request.form.get("payment_terms", "").strip() or None
        supplier.currency = request.form.get("currency") or "USD"
        supplier.notes = request.form.get("notes", "").strip() or None

        db.session.commit()
        flash("Proveedor actualizado.", "success")
        return redirect(url_for("suppliers.detail", supplier_id=supplier.id))

    return render_template("suppliers/edit.html", supplier=supplier)

@suppliers_bp.post("/<int:supplier_id>/toggle")
@login_required
def toggle(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    supplier.active = not supplier.active
    db.session.commit()
    flash("Estado del proveedor actualizado.", "success")
    return redirect(url_for("suppliers.index"))
