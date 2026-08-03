from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy import or_
from . import db
from .auth import login_required
from .models import Purchase, PurchaseItem, Product, Supplier, CashMovement

purchases_bp = Blueprint('purchases', __name__, url_prefix='/purchases')

def parse_lines(form):
    product_ids = form.getlist('product_id[]')
    quantities = form.getlist('quantity[]')
    unit_costs = form.getlist('unit_cost[]')
    lines = []
    seen = set()
    for raw_pid, raw_qty, raw_cost in zip(product_ids, quantities, unit_costs):
        if not raw_pid: continue
        try:
            pid, qty, cost = int(raw_pid), int(raw_qty), float(raw_cost)
        except (ValueError, TypeError):
            raise ValueError('Revisá los productos, cantidades y costos.')
        if qty <= 0 or cost < 0: raise ValueError('Las cantidades deben ser mayores a cero y los costos no negativos.')
        if pid in seen: raise ValueError('Un producto está repetido. Sumá sus unidades en una sola línea.')
        product = Product.query.get(pid)
        if not product or not product.active: raise ValueError('Uno de los productos ya no está disponible.')
        seen.add(pid); lines.append((product, qty, cost))
    if not lines: raise ValueError('Agregá al menos un producto a la compra.')
    return lines

@purchases_bp.route('/', methods=['GET','POST'])
@login_required
def index():
    if request.method == 'POST':
        try:
            date_value = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
            supplier_id = int(request.form['supplier_id'])
            paid = float(request.form.get('paid') or 0)
            lines = parse_lines(request.form)
        except (ValueError, TypeError) as exc:
            flash(str(exc) or 'Revisá los datos ingresados.', 'error')
            return redirect(url_for('purchases.index'))
        supplier = Supplier.query.get(supplier_id)
        if not supplier or not supplier.active:
            flash('El proveedor seleccionado no está disponible.', 'error'); return redirect(url_for('purchases.index'))
        purchase = Purchase(date=date_value, reference=request.form.get('reference','').strip() or None,
            supplier_id=supplier_id, currency='ARS', paid=paid,
            status=request.form.get('status') or 'Recibida', notes=request.form.get('notes','').strip() or None)
        for product, qty, cost in lines:
            purchase.items.append(PurchaseItem(product_id=product.id, quantity=qty, unit_cost=cost))
        db.session.add(purchase); db.session.flush()
        if paid > 0:
            purchase.cash_movements.append(CashMovement(
                date=date_value, movement_type='Egreso', category='Pago a proveedor',
                description=f'Pago inicial compra #{purchase.id} · {supplier.name}',
                payment_method=request.form.get('payment_method') or 'Transferencia',
                currency=purchase.currency, amount=paid,
            ))
        db.session.commit()
        msg = f'Compra completa guardada: {len(lines)} productos y {purchase.units} unidades.'
        if purchase.status == 'Pendiente': msg += ' Todavía no afecta el stock.'
        flash(msg, 'success')
        return redirect(url_for('purchases.detail', purchase_id=purchase.id))

    q=request.args.get('q','').strip(); status=request.args.get('status',''); supplier_id=request.args.get('supplier_id','')
    query=Purchase.query.join(Supplier)
    if q:
        term=f'%{q}%'; query=query.filter(or_(Purchase.reference.ilike(term), Supplier.name.ilike(term)))
    if status: query=query.filter(Purchase.status==status)
    if supplier_id: query=query.filter(Purchase.supplier_id==int(supplier_id))
    rows=query.order_by(Purchase.date.desc(), Purchase.id.desc()).all()
    products=Product.query.filter_by(active=True).order_by(Product.brand, Product.model).all()
    suppliers=Supplier.query.filter_by(active=True).order_by(Supplier.name).all()
    totals={'count':len(rows),'units':sum(p.units for p in rows if p.status=='Recibida'),
            'amount':sum(p.total for p in rows if p.status!='Cancelada'),
            'balance':sum(p.balance for p in rows if p.status!='Cancelada')}
    return render_template('purchases/index.html', rows=rows, products=products, suppliers=suppliers, totals=totals,
        q=q, selected_status=status, selected_supplier=supplier_id)

@purchases_bp.route('/<int:purchase_id>')
@login_required
def detail(purchase_id): return render_template('purchases/detail.html', purchase=Purchase.query.get_or_404(purchase_id))

@purchases_bp.post('/<int:purchase_id>/cancel')
@login_required
def cancel(purchase_id):
    purchase=Purchase.query.get_or_404(purchase_id); purchase.status='Cancelada'; db.session.commit()
    flash('Compra cancelada. Todas sus líneas dejaron de afectar stock y costos.', 'success')
    return redirect(url_for('purchases.detail', purchase_id=purchase.id))
