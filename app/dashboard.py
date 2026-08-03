from collections import defaultdict
from datetime import date, timedelta, datetime
from flask import Blueprint, render_template, request
from .auth import login_required
from .models import Product, Purchase, SalesOrder, Customer, Supplier, Expense, CashMovement

dashboard_bp = Blueprint("dashboard", __name__)


def resolve_period(period, start_raw=None, end_raw=None):
    today = date.today()
    if period == "today":
        return today, today, "Hoy"
    if period == "week":
        return today - timedelta(days=today.weekday()), today, "Esta semana"
    if period == "year":
        return date(today.year, 1, 1), today, "Este año"
    if period == "custom":
        try:
            start = datetime.strptime(start_raw, "%Y-%m-%d").date()
            end = datetime.strptime(end_raw, "%Y-%m-%d").date()
            if start > end:
                start, end = end, start
            return start, end, "Período personalizado"
        except (TypeError, ValueError):
            pass
    return date(today.year, today.month, 1), today, "Este mes"


@dashboard_bp.route("/")
@login_required
def index():
    period = request.args.get("period", "month")
    currency = "ARS"
    start_date, end_date, period_label = resolve_period(
        period,
        request.args.get("start"),
        request.args.get("end"),
    )

    products = Product.query.filter_by(active=True).all()
    sales = SalesOrder.query.filter(
        SalesOrder.date >= start_date,
        SalesOrder.date <= end_date,
        SalesOrder.currency == currency,
        SalesOrder.status != "Cancelada",
    ).order_by(SalesOrder.date.desc(), SalesOrder.id.desc()).all()
    delivered_sales = [s for s in sales if s.status == "Entregada"]

    purchases = Purchase.query.filter(
        Purchase.date >= start_date,
        Purchase.date <= end_date,
        Purchase.currency == currency,
        Purchase.status != "Cancelada",
    ).order_by(Purchase.date.desc(), Purchase.id.desc()).all()

    customers = Customer.query.filter_by(active=True).all()
    suppliers = Supplier.query.filter_by(active=True).all()

    sales_total = sum(s.total for s in sales)
    profit_total = sum(s.profit for s in delivered_sales)
    purchases_total = sum(p.total for p in purchases)
    receivable = sum(s.balance for s in sales)
    payable = sum(p.balance for p in purchases)

    low_stock_products = sorted(
        [p for p in products if p.available_stock <= p.min_stock],
        key=lambda p: (p.available_stock, p.brand, p.model),
    )[:8]

    # Rankings by product.
    product_units = defaultdict(int)
    product_revenue = defaultdict(float)
    product_profit = defaultdict(float)
    product_lookup = {}
    for sale in delivered_sales:
        for item in sale.items:
            product_lookup[item.product_id] = item.product
            product_units[item.product_id] += item.quantity
            product_revenue[item.product_id] += item.subtotal
            product_profit[item.product_id] += item.profit

    top_selling = [
        {
            "product": product_lookup[pid],
            "units": units,
            "amount": product_revenue[pid],
        }
        for pid, units in sorted(product_units.items(), key=lambda x: x[1], reverse=True)[:6]
    ]
    top_profitable = [
        {
            "product": product_lookup[pid],
            "profit": profit,
            "units": product_units[pid],
        }
        for pid, profit in sorted(product_profit.items(), key=lambda x: x[1], reverse=True)[:6]
    ]

    # Rankings by customer, only selected period and currency.
    customer_sales = defaultdict(float)
    customer_balance = defaultdict(float)
    customer_lookup = {}
    for sale in sales:
        customer_lookup[sale.customer_id] = sale.customer_record
        customer_sales[sale.customer_id] += sale.total
        customer_balance[sale.customer_id] += sale.balance

    top_customers = [
        {"customer": customer_lookup[cid], "amount": amount}
        for cid, amount in sorted(customer_sales.items(), key=lambda x: x[1], reverse=True)[:6]
    ]
    debtor_customers = [
        {"customer": customer_lookup[cid], "balance": balance}
        for cid, balance in sorted(customer_balance.items(), key=lambda x: x[1], reverse=True)
        if balance > 0
    ][:6]

    # Supplier debts in selected period and currency.
    supplier_balance = defaultdict(float)
    supplier_lookup = {}
    for purchase in purchases:
        supplier_lookup[purchase.supplier_id] = purchase.supplier
        supplier_balance[purchase.supplier_id] += purchase.balance
    supplier_debts = [
        {"supplier": supplier_lookup[sid], "balance": balance}
        for sid, balance in sorted(supplier_balance.items(), key=lambda x: x[1], reverse=True)
        if balance > 0
    ][:6]

    # Daily sales chart. Always cover the selected period, capped at 31 bars for readability.
    chart_start = max(start_date, end_date - timedelta(days=30))
    daily = defaultdict(float)
    for sale in sales:
        if sale.date >= chart_start:
            daily[sale.date] += sale.total
    chart = []
    cursor = chart_start
    while cursor <= end_date:
        chart.append({"date": cursor, "amount": daily[cursor]})
        cursor += timedelta(days=1)
    chart_max = max((x["amount"] for x in chart), default=0)
    for row in chart:
        row["height"] = (row["amount"] / chart_max * 100) if chart_max else 0

    stock_value = sum(max(p.stock, 0) * p.avg_cost for p in products if p.currency == currency)
    available_units = sum(max(p.available_stock, 0) for p in products)

    alerts = []
    if low_stock_products:
        alerts.append({"type": "warning", "text": f"Hay {len(low_stock_products)} productos con stock mínimo o agotado."})
    if receivable > 0:
        alerts.append({"type": "money", "text": f"Tenés {currency} {receivable:,.2f} pendientes de cobro en el período."})
    if payable > 0:
        alerts.append({"type": "money", "text": f"Tenés {currency} {payable:,.2f} pendientes de pago a proveedores."})
    if top_selling:
        leader = top_selling[0]
        alerts.append({"type": "info", "text": f"{leader['product'].brand} {leader['product'].model} es el producto más vendido: {leader['units']} unidades."})
    if not sales:
        alerts.append({"type": "info", "text": "Todavía no hay ventas registradas en este período."})

    expenses_total = sum(
        x.amount for x in Expense.query.filter_by(currency=currency).all()
        if start_date <= x.date <= end_date
    )
    cash_balance = sum(
        x.signed_amount for x in CashMovement.query.filter_by(currency=currency).all()
    )
    net_profit = profit_total - expenses_total

    totals = {
        "sales": sales_total,
        "profit": profit_total,
        "purchases": purchases_total,
        "receivable": receivable,
        "payable": payable,
        "stock_value": stock_value,
        "stock_units": available_units,
        "low_stock": len(low_stock_products),
        "sales_count": len(sales),
        "expenses": expenses_total,
        "net_profit": net_profit,
        "cash_balance": cash_balance,
    }

    return render_template(
        "dashboard/index.html",
        totals=totals,
        currency=currency,
        period=period,
        period_label=period_label,
        start_date=start_date,
        end_date=end_date,
        low_stock_products=low_stock_products,
        recent_purchases=purchases[:6],
        recent_sales=sales[:6],
        top_selling=top_selling,
        top_profitable=top_profitable,
        top_customers=top_customers,
        debtor_customers=debtor_customers,
        supplier_debts=supplier_debts,
        chart=chart,
        alerts=alerts,
    )
