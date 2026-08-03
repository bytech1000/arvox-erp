from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy import or_
from . import db
from .auth import login_required
from .models import Purchase, Product, Supplier

purchases_bp = Blueprint("purchases", __name__, url_prefix="/purchases")

@purchases_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        try:
            date_value = datetime.strptime(request.form["date"], "%Y-%m-%d").date()
            product_id = int(request.form["product_id"])
            supplier_id = int(request.form["supplier_id"])
            quantity = int(request.form["quantity"])
            unit_cost = float(request.form["unit_cost"])
            paid = float(request.form.get("paid") or 0)
        except (ValueError, TypeError):
            flash("Revisá la fecha, cantidad y valores ingresados.", "error")
            return redirect(url_for("purchases.index"))

        if quantity <= 0 or unit_cost < 0 or paid < 0:
            flash("La cantidad debe ser mayor a cero y los importes no pueden ser negativos.", "error")
            return redirect(url_for("purchases.index"))

        product = Product.query.get(product_id)
        supplier = Supplier.query.get(supplier_id)

        if not product or not product.active:
            flash("El producto seleccionado no está disponible.", "error")
            return redirect(url_for("purchases.index"))

        if not supplier or not supplier.active:
            flash("El proveedor seleccionado no está disponible.", "error")
            return redirect(url_for("purchases.index"))

        purchase = Purchase(
            date=date_value,
            reference=request.form.get("reference", "").strip() or None,
            supplier_id=supplier_id,
            product_id=product_id,
            quantity=quantity,
            unit_cost=unit_cost,
            currency=request.form.get("currency") or "USD",
            paid=paid,
            status=request.form.get("status") or "Recibida",
            notes=request.form.get("notes", "").strip() or None,
        )
        db.session.add(purchase)
        db.session.commit()

        flash(
            "Compra registrada. El stock y los costos se actualizaron automáticamente."
            if purchase.status == "Recibida"
            else "Compra registrada como pendiente. Todavía no afecta el stock.",
            "success",
        )
        return redirect(url_for("purchases.detail", purchase_id=purchase.id))

    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    supplier_id = request.args.get("supplier_id", "")

    query = Purchase.query.join(Product).join(Supplier)

    if q:
        term = f"%{q}%"
        query = query.filter(or_(
            Purchase.reference.ilike(term),
            Product.code.ilike(term),
            Product.brand.ilike(term),
            Product.model.ilike(term),
            Supplier.name.ilike(term),
        ))

    if status:
        query = query.filter(Purchase.status == status)

    if supplier_id:
        query = query.filter(Purchase.supplier_id == int(supplier_id))

    rows = query.order_by(Purchase.date.desc(), Purchase.id.desc()).all()
    products = Product.query.filter_by(active=True).order_by(Product.brand, Product.model).all()
    suppliers = Supplier.query.filter_by(active=True).order_by(Supplier.name).all()

    totals = {
        "count": len(rows),
        "units": sum(x.quantity for x in rows if x.status == "Recibida"),
        "amount": sum(x.total for x in rows if x.status != "Cancelada"),
        "balance": sum(x.balance for x in rows if x.status != "Cancelada"),
    }

    return render_template(
        "purchases/index.html",
        rows=rows,
        products=products,
        suppliers=suppliers,
        totals=totals,
        q=q,
        selected_status=status,
        selected_supplier=supplier_id,
    )

@purchases_bp.route("/<int:purchase_id>")
@login_required
def detail(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)
    return render_template("purchases/detail.html", purchase=purchase)

@purchases_bp.route("/<int:purchase_id>/edit", methods=["GET", "POST"])
@login_required
def edit(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)

    if request.method == "POST":
        try:
            purchase.date = datetime.strptime(request.form["date"], "%Y-%m-%d").date()
            purchase.quantity = int(request.form["quantity"])
            purchase.unit_cost = float(request.form["unit_cost"])
            purchase.paid = float(request.form.get("paid") or 0)
        except (ValueError, TypeError):
            flash("Revisá los datos ingresados.", "error")
            return redirect(url_for("purchases.edit", purchase_id=purchase.id))

        purchase.reference = request.form.get("reference", "").strip() or None
        purchase.supplier_id = int(request.form["supplier_id"])
        purchase.product_id = int(request.form["product_id"])
        purchase.currency = request.form.get("currency") or "USD"
        purchase.status = request.form.get("status") or "Recibida"
        purchase.notes = request.form.get("notes", "").strip() or None
        db.session.commit()

        flash("Compra actualizada. Stock y costos recalculados.", "success")
        return redirect(url_for("purchases.detail", purchase_id=purchase.id))

    products = Product.query.filter_by(active=True).order_by(Product.brand, Product.model).all()
    suppliers = Supplier.query.filter_by(active=True).order_by(Supplier.name).all()
    return render_template(
        "purchases/edit.html",
        purchase=purchase,
        products=products,
        suppliers=suppliers,
    )

@purchases_bp.post("/<int:purchase_id>/cancel")
@login_required
def cancel(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)
    purchase.status = "Cancelada"
    db.session.commit()
    flash("Compra cancelada. Ya no afecta stock ni costos.", "success")
    return redirect(url_for("purchases.detail", purchase_id=purchase.id))
