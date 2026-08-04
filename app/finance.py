from collections import defaultdict
from datetime import date, datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy import or_

from .extensions import db
from .auth import login_required
from .models import CashMovement, Expense, SalesOrder, Purchase

finance_bp = Blueprint("finance", __name__, url_prefix="/finance")

PAYMENT_METHODS = ("Efectivo", "Transferencia", "Mercado Pago", "Tarjeta")
EXPENSE_CATEGORIES = (
    "Publicidad", "Envíos", "Packaging", "Comisiones", "Combustible",
    "Impuestos", "Servicios", "Mercado Pago", "Otros"
)


def parse_date(raw):
    return datetime.strptime(raw, "%Y-%m-%d").date()


def create_movement(*, movement_type, category, description, amount, currency,
                    payment_method, movement_date, sale=None, purchase=None,
                    expense=None, notes=None):
    movement = CashMovement(
        date=movement_date,
        movement_type=movement_type,
        category=category,
        description=description,
        payment_method=payment_method,
        currency=currency,
        amount=amount,
        sale=sale,
        purchase=purchase,
        expense=expense,
        notes=notes,
    )
    db.session.add(movement)
    return movement


@finance_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        try:
            movement_date = parse_date(request.form["date"])
            movement_type = request.form["movement_type"]
            amount = float(request.form["amount"])
        except (ValueError, TypeError, KeyError):
            flash("Revisá la fecha y el importe.", "error")
            return redirect(url_for("finance.index"))

        if movement_type not in ("Ingreso", "Egreso") or amount <= 0:
            flash("El tipo o el importe del movimiento no es válido.", "error")
            return redirect(url_for("finance.index"))

        category = request.form.get("category", "Otros").strip() or "Otros"
        description = request.form.get("description", "").strip()
        if not description:
            flash("Ingresá un detalle para el movimiento.", "error")
            return redirect(url_for("finance.index"))

        create_movement(
            movement_type=movement_type,
            category=category,
            description=description,
            amount=amount,
            currency="ARS",
            payment_method=request.form.get("payment_method") or "Transferencia",
            movement_date=movement_date,
            notes=request.form.get("notes", "").strip() or None,
        )
        db.session.commit()
        flash("Movimiento de caja registrado.", "success")
        return redirect(url_for("finance.index"))

    currency = "ARS"
    q = request.args.get("q", "").strip()
    method = request.args.get("payment_method", "")
    movement_type = request.args.get("movement_type", "")

    query = CashMovement.query.filter_by(currency=currency)
    if q:
        term = f"%{q}%"
        query = query.filter(or_(
            CashMovement.description.ilike(term),
            CashMovement.category.ilike(term),
        ))
    if method:
        query = query.filter_by(payment_method=method)
    if movement_type:
        query = query.filter_by(movement_type=movement_type)

    rows = query.order_by(CashMovement.date.desc(), CashMovement.id.desc()).all()
    all_currency_rows = CashMovement.query.filter_by(currency=currency).all()

    method_balances = defaultdict(float)
    for row in all_currency_rows:
        method_balances[row.payment_method] += row.signed_amount

    today = date.today()
    today_rows = [x for x in all_currency_rows if x.date == today]
    totals = {
        "balance": sum(x.signed_amount for x in all_currency_rows),
        "income_today": sum(x.amount for x in today_rows if x.movement_type == "Ingreso"),
        "expense_today": sum(x.amount for x in today_rows if x.movement_type == "Egreso"),
        "receivable": sum(max(s.balance, 0) for s in SalesOrder.query.filter_by(currency=currency).all() if s.status != "Cancelada"),
        "payable": sum(max(p.balance, 0) for p in Purchase.query.filter_by(currency=currency).all() if p.status != "Cancelada"),
    }
    totals["result_today"] = totals["income_today"] - totals["expense_today"]

    pending_sales = [
        x for x in SalesOrder.query.filter_by(currency=currency).order_by(SalesOrder.date.desc()).all()
        if x.status != "Cancelada" and x.balance > 0.005
    ][:12]
    pending_purchases = [
        x for x in Purchase.query.filter_by(currency=currency).order_by(Purchase.date.desc()).all()
        if x.status != "Cancelada" and x.balance > 0.005
    ][:12]

    return render_template(
        "finance/index.html", rows=rows, totals=totals,
        method_balances=method_balances, payment_methods=PAYMENT_METHODS,
        pending_sales=pending_sales, pending_purchases=pending_purchases,
        currency=currency, q=q, selected_method=method,
        selected_type=movement_type,
    )


@finance_bp.route("/expenses", methods=["GET", "POST"])
@login_required
def expenses():
    if request.method == "POST":
        try:
            expense_date = parse_date(request.form["date"])
            amount = float(request.form["amount"])
        except (ValueError, TypeError, KeyError):
            flash("Revisá la fecha y el importe del gasto.", "error")
            return redirect(url_for("finance.expenses"))
        if amount <= 0:
            flash("El gasto debe ser mayor a cero.", "error")
            return redirect(url_for("finance.expenses"))

        description = request.form.get("description", "").strip()
        if not description:
            flash("Ingresá una descripción para el gasto.", "error")
            return redirect(url_for("finance.expenses"))

        expense = Expense(
            date=expense_date,
            category=request.form.get("category") or "Otros",
            description=description,
            payment_method=request.form.get("payment_method") or "Transferencia",
            currency="ARS",
            amount=amount,
            notes=request.form.get("notes", "").strip() or None,
        )
        db.session.add(expense)
        db.session.flush()
        create_movement(
            movement_type="Egreso", category=expense.category,
            description=expense.description, amount=expense.amount,
            currency=expense.currency, payment_method=expense.payment_method,
            movement_date=expense.date, expense=expense, notes=expense.notes,
        )
        db.session.commit()
        flash("Gasto registrado y descontado de Caja.", "success")
        return redirect(url_for("finance.expenses"))

    currency = "ARS"
    rows = Expense.query.filter_by(currency=currency).order_by(Expense.date.desc(), Expense.id.desc()).all()
    by_category = defaultdict(float)
    for row in rows:
        by_category[row.category] += row.amount
    category_rows = sorted(by_category.items(), key=lambda x: x[1], reverse=True)
    total = sum(x.amount for x in rows)
    return render_template(
        "finance/expenses.html", rows=rows, total=total,
        category_rows=category_rows, categories=EXPENSE_CATEGORIES,
        payment_methods=PAYMENT_METHODS, currency=currency,
    )


@finance_bp.post("/collect/<int:sale_id>")
@login_required
def collect_sale(sale_id):
    sale = SalesOrder.query.get_or_404(sale_id)
    try:
        amount = float(request.form["amount"])
        movement_date = parse_date(request.form["date"])
    except (ValueError, TypeError, KeyError):
        flash("Revisá la fecha y el importe del cobro.", "error")
        return redirect(request.referrer or url_for("sales.detail", sale_id=sale.id))

    if amount <= 0 or amount > sale.balance + 0.005:
        flash(f"El cobro debe ser mayor a cero y no superar {sale.currency} {sale.balance:.2f}.", "error")
        return redirect(request.referrer or url_for("sales.detail", sale_id=sale.id))

    method = request.form.get("payment_method") or "Transferencia"
    sale.collected = (sale.collected or 0) + amount
    create_movement(
        movement_type="Ingreso", category="Cobro de venta",
        description=f"Cobro venta #{sale.id} · {sale.customer}", amount=amount,
        currency=sale.currency, payment_method=method,
        movement_date=movement_date, sale=sale,
        notes=request.form.get("notes", "").strip() or None,
    )
    db.session.commit()
    flash("Cobro registrado. Se actualizó Caja y la cuenta corriente del cliente.", "success")
    return redirect(request.referrer or url_for("sales.detail", sale_id=sale.id))


@finance_bp.post("/pay/<int:purchase_id>")
@login_required
def pay_purchase(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)
    try:
        amount = float(request.form["amount"])
        movement_date = parse_date(request.form["date"])
    except (ValueError, TypeError, KeyError):
        flash("Revisá la fecha y el importe del pago.", "error")
        return redirect(request.referrer or url_for("purchases.detail", purchase_id=purchase.id))

    if amount <= 0 or amount > purchase.balance + 0.005:
        flash(f"El pago debe ser mayor a cero y no superar {purchase.currency} {purchase.balance:.2f}.", "error")
        return redirect(request.referrer or url_for("purchases.detail", purchase_id=purchase.id))

    method = request.form.get("payment_method") or "Transferencia"
    purchase.paid = (purchase.paid or 0) + amount
    create_movement(
        movement_type="Egreso", category="Pago a proveedor",
        description=f"Pago compra #{purchase.id} · {purchase.supplier.name}", amount=amount,
        currency=purchase.currency, payment_method=method,
        movement_date=movement_date, purchase=purchase,
        notes=request.form.get("notes", "").strip() or None,
    )
    db.session.commit()
    flash("Pago registrado. Se actualizó Caja y la cuenta corriente del proveedor.", "success")
    return redirect(request.referrer or url_for("purchases.detail", purchase_id=purchase.id))


@finance_bp.post("/expenses/<int:expense_id>/delete")
@login_required
def delete_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    description = expense.description
    amount = expense.amount

    # Expense.movement uses delete-orphan, but deleting it explicitly keeps
    # behavior predictable in both SQLite and PostgreSQL.
    if expense.movement:
        db.session.delete(expense.movement)
    db.session.delete(expense)
    db.session.commit()
    flash(
        f"Gasto eliminado: {description} · ARS {amount:.2f}. Caja fue actualizada.",
        "success",
    )
    return redirect(url_for("finance.expenses"))
