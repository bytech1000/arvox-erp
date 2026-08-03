# API pública del paquete. Mantiene compatibilidad con los módulos existentes.
from .extensions import db
from .factory import create_app

__all__ = ["db", "create_app"]
