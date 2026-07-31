from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from . import db

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), unique=True, nullable=False, index=True)
    brand = db.Column(db.String(80), nullable=False, index=True)
    model = db.Column(db.String(180), nullable=False, index=True)
    year = db.Column(db.Integer)
    category = db.Column(db.String(80), default="Paleta")
    sale_price = db.Column(db.Float, default=0)
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

    purchases = db.relationship("Purchase", backref="product", lazy=True)
    sales = db.relationship("Sale", backref="product", lazy=True)

    @property
    def purchased_units(self):
        return sum(x.quantity for x in self.purchases if x.status == "Recibida")

    @property
    def sold_units(self):
        return sum(x.quantity for x in self.sales if x.status == "Entregada")

    @property
    def stock(self):
        return self.purchased_units - self.sold_units

    @property
    def avg_cost(self):
        rows = [x for x in self.purchases if x.status == "Recibida"]
        total_units = sum(x.quantity for x in rows)
        if not total_units:
            return 0
        return sum(x.quantity * x.unit_cost for x in rows) / total_units

    @property
    def margin(self):
        return self.sale_price - self.avg_cost

class Supplier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False, index=True)
    contact = db.Column(db.String(120))
    whatsapp = db.Column(db.String(80))
    email = db.Column(db.String(180))
    city = db.Column(db.String(140))
    website = db.Column(db.String(300))
    payment_terms = db.Column(db.String(120))
    currency = db.Column(db.String(20), default="USD")
    notes = db.Column(db.Text)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    purchases = db.relationship("Purchase", backref="supplier_record", lazy=True)

    @property
    def total_purchased(self):
        return sum(
            x.quantity * x.unit_cost
            for x in self.purchases
            if x.status != "Cancelada"
        )

    @property
    def total_paid(self):
        return sum(
            (x.paid or 0)
            for x in self.purchases
            if x.status != "Cancelada"
        )

    @property
    def balance(self):
        return self.total_purchased - self.total_paid

    @property
    def purchase_count(self):
        return sum(1 for x in self.purchases if x.status != "Cancelada")

class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey("supplier.id"))
    quantity = db.Column(db.Integer, nullable=False)
    unit_cost = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(30), default="Recibida")
    paid = db.Column(db.Float, default=0)
    supplier = db.relationship("Supplier", overlaps="purchases,supplier_record")

class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    customer = db.Column(db.String(150), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(30), default="Entregada")
