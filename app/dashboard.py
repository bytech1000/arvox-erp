from flask import Blueprint, render_template
from .auth import login_required
from .models import Product, Purchase, Sale

dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route("/")
@login_required
def index():
    products = Product.query.filter_by(active=True).all()

    totals = {
        "products": len(products),
        "stock": sum(p.stock for p in products),
        "stock_value": sum(p.stock * p.avg_cost for p in products),
        "low_stock": sum(1 for p in products if p.stock <= p.min_stock),
        "sales_month": 0,
        "profit_month": 0,
    }

    low_stock_products = sorted(
        [p for p in products if p.stock <= p.min_stock],
        key=lambda p: (p.stock, p.brand, p.model)
    )[:6]

    recent_purchases = Purchase.query.order_by(Purchase.id.desc()).limit(5).all()
    recent_sales = Sale.query.order_by(Sale.id.desc()).limit(5).all()

    return render_template(
        "dashboard/index.html",
        totals=totals,
        products=products[:8],
        low_stock_products=low_stock_products,
        recent_purchases=recent_purchases,
        recent_sales=recent_sales,
    )
