import os

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "cambiar-esta-clave-en-produccion")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///arvox.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Render sometimes provides postgres:// instead of postgresql://
    if SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace(
            "postgres://", "postgresql://", 1
        )

    ADMIN_USER = os.getenv("ADMIN_USER", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
