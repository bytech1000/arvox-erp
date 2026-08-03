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
    """Crea únicamente el usuario administrador.

    ARVOX no vuelve a cargar productos ni proveedores de demostración.
    De esta forma, un reinicio o un nuevo despliegue conserva el sistema vacío.
    """
    from .models import User

    if not User.query.first():
        user = User(username=app.config["ADMIN_USER"])
        user.set_password(app.config["ADMIN_PASSWORD"])
        db.session.add(user)

    db.session.commit()
