from flask import Flask

from .bootstrap import prepare_database
from .config import Config
from .extensions import db
from .registry import register_blueprints


def create_app() -> Flask:
    """Factory central de ARVOX ERP."""
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    register_blueprints(app)
    prepare_database(app)

    return app
