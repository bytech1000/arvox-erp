from datetime import datetime
from io import StringIO
import csv
from flask import Blueprint, render_template, request, redirect, url_for, flash, Response
from sqlalchemy import or_
from . import db
from .auth import login_required
from .models import Product, StockAdjustment

inventory_bp = Blueprint("inventory", __name__, url_prefix="/stock")


def stock_rows(products):
    rows=[]
    for product in products:
        rows.append({
            "product": product,
            "physical": product.stock,
            "reserved": product.reserved_units,
            "in_transit": product.in_transit_units,
            "available": product.available_stock,
            "value": product.stock * product.avg_cost,
            "status": "Sin stock" if product.available_stock <= 0 else "Crítico" if product.available_stock <= product.min_stock else "Disponible",
        })
    return rows


@inventory_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        try:
            product_id=int(request.form["product_id"])
            date=datetime.strptime(request.form["date"], "%Y-%m-%d").date()
            counted=int(request.form["counted_stock"])
        except (ValueError, TypeError):
            flash("Revisá el producto, la fecha y el stock contado.", "error")
            return redirect(url_for("inventory.index"))
        product=Product.query.get(product_id)
        if not product:
            flash("Producto inexistente.", "error")
            return redirect(url_for("inventory.index"))
        difference=counted-product.stock
        if difference == 0:
            flash("El stock contado coincide con el sistema. No fue necesario ajustar.", "success")
            return redirect(url_for("inventory.index"))
        adjustment=StockAdjustment(
            date=date, product_id=product.id, quantity=difference,
            reason=request.form.get("reason") or "Conteo físico",
            notes=request.form.get("notes", "").strip() or None,
        )
        db.session.add(adjustment)
        db.session.commit()
        flash(f"Stock de {product.brand} {product.model} ajustado en {difference:+d} unidades.", "success")
        return redirect(url_for("inventory.product", product_id=product.id))

    q=request.args.get("q", "").strip()
    status=request.args.get("status", "")
    view=request.args.get("view", "with_stock")
    brand=request.args.get("brand", "")
    query=Product.query
    if q:
        term=f"%{q}%"
        query=query.filter(or_(Product.code.ilike(term), Product.brand.ilike(term), Product.model.ilike(term)))
    if brand: query=query.filter_by(brand=brand)
    products=query.order_by(Product.brand, Product.model).all()
    rows=stock_rows(products)
    if view == "with_stock":
        rows=[r for r in rows if r["physical"] > 0]
    elif view == "in_transit":
        rows=[r for r in rows if r["in_transit"] > 0]
    elif view == "no_stock":
        rows=[r for r in rows if r["physical"] <= 0]
    elif view != "all":
        view = "with_stock"
        rows=[r for r in rows if r["physical"] > 0]
    if status: rows=[r for r in rows if r["status"] == status]
    brands=[x[0] for x in db.session.query(Product.brand).distinct().order_by(Product.brand).all()]
    totals={
        "products": len(rows),
        "physical": sum(r["physical"] for r in rows),
        "reserved": sum(r["reserved"] for r in rows),
        "in_transit": sum(r["in_transit"] for r in rows),
        "available": sum(r["available"] for r in rows),
        "value": sum(r["value"] for r in rows),
        "critical": sum(1 for r in rows if r["status"] in ("Crítico", "Sin stock")),
    }
    selected_product_id = request.args.get("product_id", type=int)
    return render_template("inventory/index.html", rows=rows, products=Product.query.filter_by(active=True).order_by(Product.brand,Product.model).all(), brands=brands, totals=totals, q=q, selected_status=status, selected_view=view, selected_brand=brand, selected_product_id=selected_product_id, today=datetime.now().date().isoformat())


@inventory_bp.get("/product/<int:product_id>")
@login_required
def product(product_id):
    product=Product.query.get_or_404(product_id)
    movements=[]
    if product.opening_stock:
        movements.append({"date": product.created_at.date() if product.created_at else None, "type":"Stock inicial", "reference":"Alta de producto", "quantity":product.opening_stock, "notes":None})
    for item in product.purchase_items:
        if item.purchase.status == "Recibida": movements.append({"date":item.purchase.date,"type":"Compra","reference":item.purchase.reference or f"Compra #{item.purchase.id}","quantity":item.quantity,"notes":item.purchase.supplier.name})
    for item in product.sale_items:
        if item.sale.status == "Entregada": movements.append({"date":item.sale.date,"type":"Venta","reference":item.sale.reference or f"Venta #{item.sale.id}","quantity":-item.quantity,"notes":item.sale.customer})
        elif item.sale.status == "Reservada": movements.append({"date":item.sale.date,"type":"Reserva","reference":item.sale.reference or f"Venta #{item.sale.id}","quantity":0,"notes":f"{item.quantity} unidades reservadas para {item.sale.customer}"})
    for adj in product.stock_adjustments:
        movements.append({"date":adj.date,"type":"Ajuste","reference":adj.reason,"quantity":adj.quantity,"notes":adj.notes})
    movements.sort(key=lambda x: (x["date"] or datetime.min.date()), reverse=True)
    return render_template("inventory/product.html", product=product, movements=movements)


@inventory_bp.get("/export.csv")
@login_required
def export_csv():
    output=StringIO(); writer=csv.writer(output)
    writer.writerow(["Código","Marca","Modelo","Stock físico","En tránsito","Reservado","Disponible","Stock mínimo","Costo promedio","Valor stock","Estado"])
    for row in stock_rows(Product.query.order_by(Product.brand, Product.model).all()):
        p=row["product"]
        writer.writerow([p.code,p.brand,p.model,row["physical"],row["in_transit"],row["reserved"],row["available"],p.min_stock,f"{p.avg_cost:.2f}",f"{row['value']:.2f}",row["status"]])
    return Response('\ufeff'+output.getvalue(), mimetype='text/csv; charset=utf-8', headers={'Content-Disposition':'attachment; filename=arvox_stock.csv'})
