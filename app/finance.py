from collections import defaultdict
from datetime import date, datetime
from uuid import uuid4
from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy import or_

from .extensions import db
from .auth import login_required
from .models import CashMovement, Expense, SalesOrder, Purchase, FinancialAccount

finance_bp = Blueprint("finance", __name__, url_prefix="/finance")

PAYMENT_METHODS = ("Efectivo", "Transferencia", "Mercado Pago", "Tarjeta")
EXPENSE_CATEGORIES = (
    "Publicidad", "Envíos", "Packaging", "Comisiones", "Combustible",
    "Impuestos", "Servicios", "Mercado Pago", "Otros"
)


def parse_date(raw):
    return datetime.strptime(raw, "%Y-%m-%d").date()


def create_movement(*, movement_type, category, description, amount, currency,
                    payment_method, movement_date, account=None, sale=None, purchase=None,
                    expense=None, notes=None, transfer_group=None):
    movement = CashMovement(
        date=movement_date,
        movement_type=movement_type,
        category=category,
        description=description,
        payment_method=payment_method,
        currency=currency,
        amount=amount,
        account=account,
        transfer_group=transfer_group,
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

        account = FinancialAccount.query.get(request.form.get("account_id", type=int))
        if not account or not account.active:
            flash("Seleccioná una cuenta válida.", "error")
            return redirect(url_for("finance.index"))

        create_movement(
            movement_type=movement_type,
            category=category,
            description=description,
            amount=amount,
            currency="ARS",
            payment_method=request.form.get("payment_method") or "Transferencia",
            movement_date=movement_date, account=account,
            notes=request.form.get("notes", "").strip() or None,
        )
        db.session.commit()
        flash("Movimiento de caja registrado.", "success")
        return redirect(url_for("finance.index"))

    currency = "ARS"
    q = request.args.get("q", "").strip()
    method = request.args.get("payment_method", "")
    movement_type = request.args.get("movement_type", "")
    account_id = request.args.get("account_id", type=int)

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
    if account_id:
        query = query.filter_by(account_id=account_id)

    rows = query.order_by(CashMovement.date.desc(), CashMovement.id.desc()).all()
    all_currency_rows = CashMovement.query.filter_by(currency=currency).all()

    method_balances = defaultdict(float)
    for row in all_currency_rows:
        method_balances[row.payment_method] += row.signed_amount

    accounts = FinancialAccount.query.filter_by(active=True).order_by(FinancialAccount.id).all()
    account_balances = {
        account.id: sum(row.signed_amount for row in all_currency_rows if row.account_id == account.id)
        for account in accounts
    }

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
        selected_type=movement_type, accounts=accounts,
        account_balances=account_balances, selected_account_id=account_id,
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

        account = FinancialAccount.query.get(request.form.get("account_id", type=int))
        if not account or not account.active:
            flash("Seleccioná la cuenta desde la que pagaste el gasto.", "error")
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
            movement_date=expense.date, account=account, expense=expense, notes=expense.notes,
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
        accounts=FinancialAccount.query.filter_by(active=True).order_by(FinancialAccount.id).all(),
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
    account = FinancialAccount.query.get(request.form.get("account_id", type=int))
    if not account or not account.active:
        flash("Seleccioná la cuenta donde ingresó el cobro.", "error")
        return redirect(request.referrer or url_for("sales.detail", sale_id=sale.id))
    sale.collected = (sale.collected or 0) + amount
    create_movement(
        movement_type="Ingreso", category="Cobro de venta",
        description=f"Cobro venta #{sale.id} · {sale.customer}", amount=amount,
        currency=sale.currency, payment_method=method,
        movement_date=movement_date, account=account, sale=sale,
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
    account = FinancialAccount.query.get(request.form.get("account_id", type=int))
    if not account or not account.active:
        flash("Seleccioná la cuenta desde la que hiciste el pago.", "error")
        return redirect(request.referrer or url_for("purchases.detail", purchase_id=purchase.id))
    purchase.paid = (purchase.paid or 0) + amount
    create_movement(
        movement_type="Egreso", category="Pago a proveedor",
        description=f"Pago compra #{purchase.id} · {purchase.supplier.name}", amount=amount,
        currency=purchase.currency, payment_method=method,
        movement_date=movement_date, account=account, purchase=purchase,
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




@finance_bp.post("/transfer")
@login_required
def transfer():
    try:
        movement_date = parse_date(request.form["date"])
        amount = float(request.form["amount"])
        source_id = int(request.form["source_account_id"])
        destination_id = int(request.form["destination_account_id"])
    except (ValueError, TypeError, KeyError):
        flash("Revisá los datos de la transferencia.", "error")
        return redirect(url_for("finance.index"))

    if amount <= 0 or source_id == destination_id:
        flash("La transferencia debe ser mayor a cero y entre cuentas distintas.", "error")
        return redirect(url_for("finance.index"))

    source = FinancialAccount.query.get(source_id)
    destination = FinancialAccount.query.get(destination_id)
    if not source or not destination or not source.active or not destination.active:
        flash("Seleccioná cuentas válidas.", "error")
        return redirect(url_for("finance.index"))

    group = uuid4().hex
    detail = request.form.get("description", "").strip() or f"{source.name} → {destination.name}"
    create_movement(
        movement_type="Egreso", category="Transferencia interna",
        description=f"Transferencia a {destination.name} · {detail}",
        amount=amount, currency="ARS", payment_method="Transferencia",
        movement_date=movement_date, account=source, transfer_group=group,
    )
    create_movement(
        movement_type="Ingreso", category="Transferencia interna",
        description=f"Transferencia desde {source.name} · {detail}",
        amount=amount, currency="ARS", payment_method="Transferencia",
        movement_date=movement_date, account=destination, transfer_group=group,
    )
    db.session.commit()
    flash("Transferencia registrada. El disponible total no cambió.", "success")
    return redirect(url_for("finance.index"))


@finance_bp.post("/movement/<int:movement_id>/account")
@login_required
def change_movement_account(movement_id):
    movement = CashMovement.query.get_or_404(movement_id)
    if movement.transfer_group:
        flash("Las transferencias internas no se reclasifican desde el historial.", "error")
        return redirect(request.referrer or url_for("finance.index"))
    account = FinancialAccount.query.get(request.form.get("account_id", type=int))
    if not account or not account.active:
        flash("Seleccioná una cuenta válida.", "error")
        return redirect(request.referrer or url_for("finance.index"))
    movement.account = account
    db.session.commit()
    flash(f"Movimiento asignado a {account.name}.", "success")
    return redirect(request.referrer or url_for("finance.index"))


@finance_bp.post("/movements/<int:movement_id>/delete")
@login_required
def delete_movement(movement_id):
    movement = CashMovement.query.get_or_404(movement_id)
    description = movement.description
    amount = movement.amount
    movement_type = movement.movement_type

    if movement.transfer_group:
        for row in CashMovement.query.filter_by(transfer_group=movement.transfer_group).all():
            db.session.delete(row)
        db.session.commit()
        flash("Transferencia interna eliminada de ambas cuentas.", "success")
        return redirect(request.referrer or url_for("finance.index"))

    # If the movement came from a sale collection, reverse the collected amount.
    if movement.sale is not None:
        movement.sale.collected = max((movement.sale.collected or 0) - movement.amount, 0)

    # If the movement came from a purchase payment, reverse the paid amount.
    if movement.purchase is not None:
        movement.purchase.paid = max((movement.purchase.paid or 0) - movement.amount, 0)

    # If the movement belongs to an expense, delete the expense too.
    # The relationship is delete-orphan, so removing the expense removes its movement.
    if movement.expense is not None:
        expense = movement.expense
        db.session.delete(expense)
    else:
        db.session.delete(movement)

    db.session.commit()
    flash(
        f"Movimiento eliminado: {description} · {movement_type} ARS {amount:.2f}. Caja fue actualizada.",
        "success",
    )
    return redirect(request.referrer or url_for("finance.index"))
