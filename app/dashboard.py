from flask import Blueprint, render_template
from .auth import login_required
from .models import Product

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
    }
    return render_template("dashboard/index.html", totals=totals, products=products[:8])
