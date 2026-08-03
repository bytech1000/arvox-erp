from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from . import db

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), unique=True, nullable=False, index=True)
    brand = db.Column(db.String(80), nullable=False, index=True)
    model = db.Column(db.String(180), nullable=False, index=True)
    year = db.Column(db.Integer)
    category = db.Column(db.String(80), default='Paleta')
    sale_price = db.Column(db.Float, default=0)
    currency = db.Column(db.String(10), default='USD')
    opening_stock = db.Column(db.Integer, default=0)
    opening_cost = db.Column(db.Float, default=0)
    active = db.Column(db.Boolean, default=True)
    min_stock = db.Column(db.Integer, default=1)
    image_url = db.Column(db.String(500))
    description = db.Column(db.Text)
    notes = db.Column(db.Text)
    shape = db.Column(db.String(80))
    balance = db.Column(db.String(80))
    level = db.Column(db.String(80))
    weight = db.Column(db.String(80))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    purchase_items = db.relationship('PurchaseItem', backref='product', lazy=True)
    sale_items = db.relationship('SaleItem', backref='product', lazy=True)

    @property
    def purchased_units(self):
        return sum(i.quantity for i in self.purchase_items if i.purchase.status == 'Recibida')
    @property
    def sold_units(self):
        return sum(i.quantity for i in self.sale_items if i.sale.status == 'Entregada')

    @property
    def reserved_units(self):
        return sum(i.quantity for i in self.sale_items if i.sale.status == 'Reservada')

    @property
    def stock(self):
        return (self.opening_stock or 0) + self.purchased_units - self.sold_units

    @property
    def available_stock(self):
        return self.stock - self.reserved_units
    @property
    def avg_cost(self):
        rows = [i for i in self.purchase_items if i.purchase.status == 'Recibida']
        opening_units = self.opening_stock or 0
        total_units = opening_units + sum(i.quantity for i in rows)
        if not total_units: return 0
        total_value = opening_units * (self.opening_cost or 0) + sum(i.quantity * i.unit_cost for i in rows)
        return total_value / total_units
    @property
    def last_cost(self):
        rows = [i for i in self.purchase_items if i.purchase.status == 'Recibida']
        if not rows: return self.opening_cost or 0
        latest = max(rows, key=lambda i: (i.purchase.date, i.id or 0))
        return latest.unit_cost
    @property
    def margin(self): return (self.sale_price or 0) - self.avg_cost
    @property
    def margin_pct(self): return (self.margin / self.sale_price * 100) if self.sale_price else 0

class Supplier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False, index=True)
    contact = db.Column(db.String(120))
    whatsapp = db.Column(db.String(80))
    email = db.Column(db.String(180))
    city = db.Column(db.String(140))
    website = db.Column(db.String(300))
    payment_terms = db.Column(db.String(120))
    currency = db.Column(db.String(20), default='USD')
    notes = db.Column(db.Text)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    purchases = db.relationship('Purchase', backref='supplier', lazy=True)
    @property
    def total_purchased(self): return sum(p.total for p in self.purchases if p.status != 'Cancelada')
    @property
    def total_paid(self): return sum((p.paid or 0) for p in self.purchases if p.status != 'Cancelada')
    @property
    def balance(self): return self.total_purchased - self.total_paid
    @property
    def purchase_count(self): return sum(1 for p in self.purchases if p.status != 'Cancelada')

class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    reference = db.Column(db.String(80))
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'), nullable=False)
    currency = db.Column(db.String(20), default='USD')
    paid = db.Column(db.Float, default=0)
    status = db.Column(db.String(30), default='Recibida')
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('PurchaseItem', backref='purchase', lazy=True, cascade='all, delete-orphan')
    @property
    def total(self): return sum(i.subtotal for i in self.items)
    @property
    def units(self): return sum(i.quantity for i in self.items)
    @property
    def balance(self): return self.total - (self.paid or 0)

class PurchaseItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey('purchase.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_cost = db.Column(db.Float, nullable=False)
    @property
    def subtotal(self): return self.quantity * self.unit_cost

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False, index=True)
    whatsapp = db.Column(db.String(80))
    email = db.Column(db.String(180))
    city = db.Column(db.String(140))
    notes = db.Column(db.Text)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sales = db.relationship("SalesOrder", backref="customer_record", lazy=True)
    quotes = db.relationship("Quote", backref="customer_record", lazy=True)

    @property
    def total_sold(self):
        return sum(x.total for x in self.sales if x.status != "Cancelada")

    @property
    def total_collected(self):
        return sum((x.collected or 0) for x in self.sales if x.status != "Cancelada")

    @property
    def balance(self):
        return self.total_sold - self.total_collected

    @property
    def sale_count(self):
        return sum(1 for x in self.sales if x.status != "Cancelada")


class SalesOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    reference = db.Column(db.String(80))
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    customer = db.Column(db.String(150), nullable=False)
    whatsapp = db.Column(db.String(80))
    currency = db.Column(db.String(20), default="USD")
    payment_method = db.Column(db.String(50), default="Transferencia")
    collected = db.Column(db.Float, default=0)
    status = db.Column(db.String(30), default="Entregada")
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship("SaleItem", backref="sale", lazy=True, cascade="all, delete-orphan")

    @property
    def total(self):
        return sum(i.subtotal for i in self.items)

    @property
    def cost_total(self):
        return sum(i.cost_snapshot * i.quantity for i in self.items)

    @property
    def profit(self):
        return self.total - self.cost_total

    @property
    def balance(self):
        return self.total - (self.collected or 0)

    @property
    def units(self):
        return sum(i.quantity for i in self.items)


class SaleItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales_order.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    discount_pct = db.Column(db.Float, default=0)
    cost_snapshot = db.Column(db.Float, default=0)

    @property
    def subtotal(self):
        gross = self.quantity * self.unit_price
        return gross * (1 - (self.discount_pct or 0) / 100)

    @property
    def profit(self):
        return self.subtotal - (self.cost_snapshot * self.quantity)


class Quote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(30), unique=True, nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)
    valid_until = db.Column(db.Date)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    customer = db.Column(db.String(150), nullable=False)
    currency = db.Column(db.String(20), default="USD")
    status = db.Column(db.String(30), default="Borrador")
    notes = db.Column(db.Text)
    converted_sale_id = db.Column(db.Integer, db.ForeignKey("sales_order.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    items = db.relationship("QuoteItem", backref="quote", lazy=True, cascade="all, delete-orphan")
    converted_sale = db.relationship("SalesOrder", foreign_keys=[converted_sale_id])

    @property
    def subtotal(self):
        return sum(i.gross for i in self.items)

    @property
    def discount_total(self):
        return self.subtotal - self.total

    @property
    def total(self):
        return sum(i.subtotal for i in self.items)

    @property
    def cost_total(self):
        return sum(i.cost_snapshot * i.quantity for i in self.items)

    @property
    def expected_profit(self):
        return self.total - self.cost_total

    @property
    def margin_pct(self):
        return (self.expected_profit / self.total * 100) if self.total else 0

    @property
    def units(self):
        return sum(i.quantity for i in self.items)


class QuoteItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quote_id = db.Column(db.Integer, db.ForeignKey("quote.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    discount_pct = db.Column(db.Float, default=0)
    cost_snapshot = db.Column(db.Float, default=0)

    product = db.relationship("Product")

    @property
    def gross(self):
        return self.quantity * self.unit_price

    @property
    def subtotal(self):
        return self.gross * (1 - (self.discount_pct or 0) / 100)

    @property
    def expected_profit(self):
        return self.subtotal - (self.cost_snapshot * self.quantity)
