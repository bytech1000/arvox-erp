from collections import defaultdict
from csv import writer
from datetime import datetime, timedelta
from io import StringIO
from flask import Blueprint, render_template, request, Response
from .auth import login_required
from .models import SalesOrder, SaleItem, Product, Expense, Customer

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")

PERIODS = {
    "today": "Hoy",
    "week": "Semana",
    "month": "Mes",
    "year": "Año",
    "custom": "Personalizado",
}

def period_dates():
    today = datetime.now().date()
    period = request.args.get("period", "month")
    if period == "today":
        start = end = today
    elif period == "week":
        start = today - timedelta(days=today.weekday())
        end = today
    elif period == "year":
        start = today.replace(month=1, day=1)
        end = today
    elif period == "custom":
        try:
            start = datetime.strptime(request.args.get("start", ""), "%Y-%m-%d").date()
            end = datetime.strptime(request.args.get("end", ""), "%Y-%m-%d").date()
        except ValueError:
            start = today.replace(day=1)
            end = today
    else:
        period = "month"
        start = today.replace(day=1)
        end = today
    if start > end:
        start, end = end, start
    return period, start, end

def filtered_sales(start, end, currency):
    return SalesOrder.query.filter(
        SalesOrder.date >= start,
        SalesOrder.date <= end,
        SalesOrder.currency == currency,
        SalesOrder.status == "Entregada",
    ).order_by(SalesOrder.date.desc(), SalesOrder.id.desc()).all()

def filtered_expenses(start, end, currency):
    return Expense.query.filter(
        Expense.date >= start,
        Expense.date <= end,
        Expense.currency == currency,
    ).order_by(Expense.date.desc(), Expense.id.desc()).all()

def report_data(start, end, currency):
    sales = filtered_sales(start, end, currency)
    expenses = filtered_expenses(start, end, currency)

    total_sales = sum(s.total for s in sales)
    cost_total = sum(s.cost_total for s in sales)
    gross_profit = total_sales - cost_total
    expense_total = sum(e.amount for e in expenses)
    net_profit = gross_profit - expense_total
    units = sum(s.units for s in sales)

    products = defaultdict(lambda: {"quantity": 0, "sales": 0.0, "profit": 0.0, "brand": "", "model": ""})
    brands = defaultdict(lambda: {"quantity": 0, "sales": 0.0, "profit": 0.0})
    customers = defaultdict(lambda: {"sales": 0.0, "orders": 0, "units": 0})

    for sale in sales:
        customers[sale.customer]["sales"] += sale.total
        customers[sale.customer]["orders"] += 1
        customers[sale.customer]["units"] += sale.units
        for item in sale.items:
            key = item.product_id
            row = products[key]
            row["brand"] = item.product.brand
            row["model"] = item.product.model
            row["quantity"] += item.quantity
            row["sales"] += item.subtotal
            row["profit"] += item.profit
            brand = brands[item.product.brand]
            brand["quantity"] += item.quantity
            brand["sales"] += item.subtotal
            brand["profit"] += item.profit

    expense_categories = defaultdict(float)
    for expense in expenses:
        expense_categories[expense.category] += expense.amount

    inventory = []
    stock_value = 0.0
    for product in Product.query.filter_by(active=True).order_by(Product.brand, Product.model).all():
        value = max(product.stock, 0) * product.avg_cost
        stock_value += value
        inventory.append({
            "product": product,
            "stock": product.stock,
            "available": product.available_stock,
            "avg_cost": product.avg_cost,
            "value": value,
            "critical": product.available_stock <= product.min_stock,
        })

    return {
        "sales": sales,
        "expenses": expenses,
        "total_sales": total_sales,
        "cost_total": cost_total,
        "gross_profit": gross_profit,
        "expense_total": expense_total,
        "net_profit": net_profit,
        "units": units,
        "average_ticket": total_sales / len(sales) if sales else 0,
        "margin_pct": gross_profit / total_sales * 100 if total_sales else 0,
        "products": sorted(products.values(), key=lambda x: (x["quantity"], x["sales"]), reverse=True),
        "brands": sorted([{"name": k, **v} for k, v in brands.items()], key=lambda x: x["sales"], reverse=True),
        "customers": sorted([{"name": k, **v} for k, v in customers.items()], key=lambda x: x["sales"], reverse=True),
        "expense_categories": sorted([{"name": k, "amount": v} for k, v in expense_categories.items()], key=lambda x: x["amount"], reverse=True),
        "inventory": inventory,
        "stock_value": stock_value,
        "critical_count": sum(1 for x in inventory if x["critical"]),
    }

@reports_bp.get("/")
@login_required
def index():
    period, start, end = period_dates()
    currency = request.args.get("currency", "USD")
    data = report_data(start, end, currency)
    return render_template(
        "reports/index.html",
        period=period,
        periods=PERIODS,
        start=start,
        end=end,
        currency=currency,
        **data,
    )

@reports_bp.get("/export/<kind>.csv")
@login_required
def export_csv(kind):
    period, start, end = period_dates()
    currency = request.args.get("currency", "USD")
    data = report_data(start, end, currency)
    output = StringIO()
    csv = writer(output)

    if kind == "sales":
        csv.writerow(["Fecha", "Cliente", "Referencia", "Unidades", "Total", "Costo", "Ganancia", "Moneda"])
        for sale in data["sales"]:
            csv.writerow([sale.date.isoformat(), sale.customer, sale.reference or "", sale.units, f"{sale.total:.2f}", f"{sale.cost_total:.2f}", f"{sale.profit:.2f}", sale.currency])
    elif kind == "products":
        csv.writerow(["Marca", "Modelo", "Unidades vendidas", "Ventas", "Ganancia", "Moneda"])
        for row in data["products"]:
            csv.writerow([row["brand"], row["model"], row["quantity"], f'{row["sales"]:.2f}', f'{row["profit"]:.2f}', currency])
    elif kind == "expenses":
        csv.writerow(["Fecha", "Categoría", "Descripción", "Medio de pago", "Importe", "Moneda"])
        for expense in data["expenses"]:
            csv.writerow([expense.date.isoformat(), expense.category, expense.description, expense.payment_method, f"{expense.amount:.2f}", expense.currency])
    elif kind == "inventory":
        csv.writerow(["Código", "Marca", "Modelo", "Stock", "Disponible", "Costo promedio", "Valor stock", "Estado"])
        for row in data["inventory"]:
            product = row["product"]
            csv.writerow([product.code, product.brand, product.model, row["stock"], row["available"], f'{row["avg_cost"]:.2f}', f'{row["value"]:.2f}', "Crítico" if row["critical"] else "Normal"])
    else:
        return Response("Reporte inválido", status=404)

    filename = f"arvox_{kind}_{start.isoformat()}_{end.isoformat()}.csv"
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
