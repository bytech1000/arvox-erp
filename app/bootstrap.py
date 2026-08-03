from flask import Flask
from sqlalchemy import inspect, text

from .extensions import db


def prepare_database(app: Flask) -> None:
    """Crea tablas, aplica migraciones compatibles y carga datos iniciales."""
    with app.app_context():
        db.create_all()
        migrate_schema()
        seed_data(app)


def migrate_schema() -> None:
    """Migraciones pequeñas y seguras para instalaciones SQLite existentes."""
    inspector = inspect(db.engine)
    table_names = set(inspector.get_table_names())

    if "product" in table_names:
        product_columns = {
            column["name"] for column in inspector.get_columns("product")
        }
        additions = {
            "currency": "VARCHAR(10) DEFAULT 'USD'",
            "opening_stock": "INTEGER DEFAULT 0",
            "opening_cost": "FLOAT DEFAULT 0",
        }
        for name, definition in additions.items():
            if name not in product_columns:
                db.session.execute(
                    text(f"ALTER TABLE product ADD COLUMN {name} {definition}")
                )

    db.session.commit()


def seed_data(app: Flask) -> None:
    """Carga el usuario administrador y datos iniciales solo cuando faltan."""
    from .models import Product, Supplier, SystemSetting, User

    if not User.query.first():
        user = User(username=app.config["ADMIN_USER"])
        user.set_password(app.config["ADMIN_PASSWORD"])
        db.session.add(user)

    demo_seed_disabled = SystemSetting.query.filter_by(key="skip_demo_seed").first() is not None

    if not Product.query.first() and not demo_seed_disabled:
        db.session.add_all([
            Product(code="AD0001", brand="Adidas", model="Metalbone HRD+ 2024", year=2024, category="Paleta", sale_price=450, currency="USD", opening_stock=2, opening_cost=230, active=True, min_stock=1),
            Product(code="NX0001", brand="Nox", model="AT10 Genius 18K Alum 2025 By Agustin Tapia", year=2025, category="Paleta", sale_price=490, currency="USD", opening_stock=1, opening_cost=210, active=True, min_stock=1),
            Product(code="NX0002", brand="Nox", model="AT10 Luxury Genius 12K 2025 By Agustin Tapia", year=2025, category="Paleta", sale_price=470, currency="USD", opening_stock=1, opening_cost=199, active=True, min_stock=1),
            Product(code="BP0001", brand="Bullpadel", model="Ionic Power 2026", year=2026, category="Paleta", sale_price=390, currency="USD", opening_stock=2, opening_cost=185, active=True, min_stock=1),
            Product(code="AD0002", brand="Adidas", model="Metalbone Carbon 2026", year=2026, category="Paleta", sale_price=430, currency="USD", opening_stock=1, opening_cost=229, active=True, min_stock=1),
            Product(code="BP0002", brand="Bullpadel", model="Neuron 02 Edge 2026", year=2026, category="Paleta", sale_price=390, currency="USD", opening_stock=1, opening_cost=249, active=True, min_stock=1),
            Product(code="AD0003", brand="Adidas", model="Metalbone Carbon 3.4 2025", year=2025, category="Paleta", sale_price=440, currency="USD", opening_stock=1, opening_cost=213, active=True, min_stock=1),
            Product(code="HD0001", brand="Head", model="Coello Pro 2025", year=2025, category="Paleta", sale_price=440, currency="USD", opening_stock=1, opening_cost=229, active=True, min_stock=1),
        ])

    if not Supplier.query.first() and not demo_seed_disabled:
        db.session.add(Supplier(
            name="Padel Goats",
            contact="Santiago",
            whatsapp="+54 9 11 5343-4308",
            city="Buenos Aires, Argentina",
            currency="USD",
            notes="Proveedor utilizado en la compra inicial. Buena página con valores. No posee local físico.",
            active=True,
        ))

    db.session.commit()
