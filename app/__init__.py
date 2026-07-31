from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from .config import Config

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)

    from .auth import auth_bp
    from .dashboard import dashboard_bp
    from .products import products_bp
    from .suppliers import suppliers_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(suppliers_bp)

    with app.app_context():
        db.create_all()
        _seed_data(app)

    return app

def _seed_data(app):
    from .models import User, Product, Supplier

    if not User.query.first():
        user = User(username=app.config["ADMIN_USER"])
        user.set_password(app.config["ADMIN_PASSWORD"])
        db.session.add(user)

    if not Product.query.first():
        products = [
            Product(code="AD0001", brand="Adidas", model="Metalbone HRD+ 2024", year=2024, category="Paleta", sale_price=450, active=True, min_stock=1),
            Product(code="NX0001", brand="Nox", model="AT10 Genius 18K Alum 2025 By Agustin Tapia", year=2025, category="Paleta", sale_price=490, active=True, min_stock=1),
            Product(code="NX0002", brand="Nox", model="AT10 Luxury Genius 12K 2025 By Agustin Tapia", year=2025, category="Paleta", sale_price=470, active=True, min_stock=1),
            Product(code="BP0001", brand="Bullpadel", model="Ionic Power 2026", year=2026, category="Paleta", sale_price=390, active=True, min_stock=1),
            Product(code="AD0002", brand="Adidas", model="Metalbone Carbon 2026", year=2026, category="Paleta", sale_price=430, active=True, min_stock=1),
            Product(code="BP0002", brand="Bullpadel", model="Neuron 02 Edge 2026", year=2026, category="Paleta", sale_price=390, active=True, min_stock=1),
            Product(code="AD0003", brand="Adidas", model="Metalbone Carbon 3.4 2025", year=2025, category="Paleta", sale_price=440, active=True, min_stock=1),
            Product(code="HD0001", brand="Head", model="Coello Pro 2025", year=2025, category="Paleta", sale_price=440, active=True, min_stock=1),
        ]
        db.session.add_all(products)


    if not Supplier.query.first():
        supplier = Supplier(
            name="Padel Goats",
            contact="Santiago",
            whatsapp="+54 9 11 5343-4308",
            city="Buenos Aires, Argentina",
            currency="USD",
            notes="Proveedor utilizado en la compra inicial. Buena página con valores. No posee local físico.",
            active=True,
        )
        db.session.add(supplier)

    db.session.commit()
