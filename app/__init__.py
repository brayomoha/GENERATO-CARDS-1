"""
CIS School System - App Factory
=================================
Creates and configures the Flask web application.
"""

import os
from flask import Flask
from .models import db


def create_app(config=None):
    app = Flask(__name__, template_folder="templates", static_folder="static")

    # -----------------------------------------------------------------------
    # CONFIGURATION
    # -----------------------------------------------------------------------
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "cis-dev-secret-change-in-production")

    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    db_path  = os.path.join(base_dir, "data", "cis_school.db")

    # Use DATABASE_URL env var if set (Render/cloud), otherwise local SQLite
    database_url = os.environ.get("DATABASE_URL", f"sqlite:///{db_path}")
    # Render uses postgres:// but SQLAlchemy needs postgresql://
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["UPLOAD_FOLDER"]                  = os.path.join(base_dir, "uploads")
    app.config["REPORTS_FOLDER"]                 = os.path.join(base_dir, "reports")
    app.config["MAX_CONTENT_LENGTH"]             = 16 * 1024 * 1024   # 16 MB

    # Create required folders if they don't exist (important for cloud deployment)
    for folder in [os.path.join(base_dir, "data"),
                   os.path.join(base_dir, "uploads"),
                   os.path.join(base_dir, "reports")]:
        os.makedirs(folder, exist_ok=True)

    if config:
        app.config.update(config)

    # -----------------------------------------------------------------------
    # EXTENSIONS
    # -----------------------------------------------------------------------
    db.init_app(app)

    # -----------------------------------------------------------------------
    # BLUEPRINTS
    # -----------------------------------------------------------------------
    from .routes.auth      import auth_bp
    from .routes.admin     import admin_bp
    from .routes.marks     import marks_bp
    from .routes.reports   import reports_bp
    from .routes.main      import main_bp
    from .routes.reception import reception_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp,       url_prefix="/auth")
    app.register_blueprint(admin_bp,      url_prefix="/admin")
    app.register_blueprint(marks_bp,      url_prefix="/marks")
    app.register_blueprint(reports_bp,    url_prefix="/reports")
    app.register_blueprint(reception_bp,  url_prefix="/reception")

    # -----------------------------------------------------------------------
    # CREATE TABLES + SEED COMMENT TEMPLATES
    # -----------------------------------------------------------------------
    with app.app_context():
        # Import CommentTemplate here so the table is registered
        from .comments_bank import CommentTemplate, seed_comment_templates
        db.create_all()
        seed_comment_templates(app)

    return app
