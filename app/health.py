from flask import Blueprint, jsonify

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health():
    """Endpoint simple para comprobar que Render mantiene ARVOX operativo."""
    return jsonify(status="ok", app="ARVOX ERP"), 200
