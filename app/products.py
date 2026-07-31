from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy import or_
from . import db
from .auth import login_required
from .models import Product

products_bp = Blueprint("products", __name__, url_prefix="/products")

@products_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        code = request.form["code"].strip().upper()
        if Product.query.filter_by(code=code).first():
            flash("Ya existe un producto con ese código.", "error")
            return redirect(url_for("products.index"))

        product = Product(
            code=code,
            brand=request.form["brand"].strip(),
            model=request.form["model"].strip(),
            year=request.form.get("year") or None,
            category=request.form.get("category") or "Paleta",
            sale_price=request.form.get("sale_price") or 0,
            min_stock=request.form.get("min_stock") or 1,
            image_url=request.form.get("image_url") or None,
            description=request.form.get("description") or None,
            notes=request.form.get("notes") or None,
            shape=request.form.get("shape") or None,
            balance=request.form.get("balance") or None,
            level=request.form.get("level") or None,
            weight=request.form.get("weight") or None,
        )
        db.session.add(product)
        db.session.commit()
        flash("Producto creado correctamente.", "success")
        return redirect(url_for("products.index"))

    q = request.args.get("q", "").strip()
    brand = request.args.get("brand", "").strip()
    active = request.args.get("active", "1")

    query = Product.query
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Product.code.ilike(like),
            Product.brand.ilike(like),
            Product.model.ilike(like),
        ))
    if brand:
        query = query.filter_by(brand=brand)
    if active in ("0", "1"):
        query = query.filter_by(active=(active == "1"))

    rows = query.order_by(Product.brand, Product.model).all()
    brands = db.session.query(Product.brand).distinct().order_by(Product.brand).all()

    return render_template(
        "products/index.html",
        rows=rows,
        brands=[b[0] for b in brands],
        q=q,
        selected_brand=brand,
        selected_active=active,
    )

@products_bp.route("/<int:product_id>")
@login_required
def detail(product_id):
    product = Product.query.get_or_404(product_id)
    margin_pct = (product.margin / product.sale_price * 100) if product.sale_price else 0
    return render_template("products/detail.html", product=product, margin_pct=margin_pct)

@products_bp.route("/<int:product_id>/edit", methods=["GET", "POST"])
@login_required
def edit(product_id):
    product = Product.query.get_or_404(product_id)
    if request.method == "POST":
        new_code = request.form["code"].strip().upper()
        duplicate = Product.query.filter(Product.code == new_code, Product.id != product.id).first()
        if duplicate:
            flash("Ese código ya pertenece a otro producto.", "error")
            return redirect(url_for("products.edit", product_id=product.id))

        product.code = new_code
        product.brand = request.form["brand"].strip()
        product.model = request.form["model"].strip()
        product.year = request.form.get("year") or None
        product.category = request.form.get("category") or "Paleta"
        product.sale_price = request.form.get("sale_price") or 0
        product.min_stock = request.form.get("min_stock") or 1
        product.image_url = request.form.get("image_url") or None
        product.description = request.form.get("description") or None
        product.notes = request.form.get("notes") or None
        product.shape = request.form.get("shape") or None
        product.balance = request.form.get("balance") or None
        product.level = request.form.get("level") or None
        product.weight = request.form.get("weight") or None
        db.session.commit()
        flash("Producto actualizado.", "success")
        return redirect(url_for("products.detail", product_id=product.id))

    return render_template("products/edit.html", product=product)

@products_bp.post("/<int:product_id>/toggle")
@login_required
def toggle(product_id):
    product = Product.query.get_or_404(product_id)
    product.active = not product.active
    db.session.commit()
    flash("Estado actualizado.", "success")
    return redirect(url_for("products.index"))
