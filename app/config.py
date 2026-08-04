import os


def _database_uri() -> str:
    """Return a SQLAlchemy URI suitable for local SQLite or Render Postgres."""
    raw = (os.getenv("DATABASE_URL") or "").strip()
    on_render = (os.getenv("RENDER") or "").lower() == "true"

    # Never allow Render to fall back to an ephemeral SQLite file.
    if on_render and not raw:
        raise RuntimeError(
            "DATABASE_URL no está configurada. ARVOX en Render requiere PostgreSQL "
            "para conservar los datos entre reinicios."
        )

    if not raw:
        return "sqlite:///arvox.db"

    # Render can provide postgres:// or postgresql://. Explicitly use psycopg 3.
    if raw.startswith("postgres://"):
        raw = "postgresql+psycopg://" + raw[len("postgres://"):]
    elif raw.startswith("postgresql://"):
        raw = "postgresql+psycopg://" + raw[len("postgresql://"):]

    return raw


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "cambiar-esta-clave-en-produccion")
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

    ADMIN_USER = os.getenv("ADMIN_USER", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
