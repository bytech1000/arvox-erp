from flask import Flask


def register_blueprints(app: Flask) -> None:
    """Registra todos los módulos funcionales de ARVOX."""
    from .auth import auth_bp
    from .dashboard import dashboard_bp
    from .products import products_bp
    from .suppliers import suppliers_bp
    from .purchases import purchases_bp
    from .sales import sales_bp
    from .customers import customers_bp
    from .quotes import quotes_bp
    from .health import health_bp
    from .finance import finance_bp
    from .reports import reports_bp

    for blueprint in (
        auth_bp,
        dashboard_bp,
        products_bp,
        suppliers_bp,
        purchases_bp,
        sales_bp,
        customers_bp,
        quotes_bp,
        finance_bp,
        reports_bp,
        health_bp,
    ):
        app.register_blueprint(blueprint)
