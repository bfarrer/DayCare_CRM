"""Application factory for the daycare enrollment CRM."""

import os
import warnings
from datetime import date

from dotenv import load_dotenv
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from . import constants
from .config import Config
from .extensions import csrf, db, login_manager, migrate
from .utils import date_input, display_date


def create_app(config_object=Config):
    load_dotenv()

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_object)
    os.makedirs(app.instance_path, exist_ok=True)

    if not app.config.get("TESTING") and not os.environ.get("SECRET_KEY"):
        warnings.warn(
            "SECRET_KEY is not set, so a new one is generated each start and "
            "everyone is signed out on restart. Set it in .env before real use.",
            RuntimeWarning,
            stacklevel=2,
        )

    if app.config.get("BEHIND_PROXY"):
        # One proxy hop (the host's load balancer). Without this, Flask sees
        # http:// and would refuse to set the secure session cookie.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from .views.auth import bp as auth_bp
    from .views.children import bp as children_bp
    from .views.dashboard import bp as dashboard_bp
    from .views.families import bp as families_bp
    from .views.reports import bp as reports_bp
    from .views.users import bp as users_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(families_bp)
    app.register_blueprint(children_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(users_bp)

    _register_template_helpers(app)
    _register_cli(app)

    # The local SQLite prototype creates its tables on first run. Production
    # uses Alembic migrations instead: create_all() cannot alter existing
    # tables, so relying on it would silently skip every future schema change.
    if app.config.get("AUTO_CREATE_TABLES"):
        with app.app_context():
            db.create_all()

    return app


def _register_template_helpers(app):
    """Expose the funnel vocabulary and date formatting to every template."""
    app.jinja_env.filters["display_date"] = display_date
    app.jinja_env.filters["date_input"] = date_input

    @app.context_processor
    def inject_globals():
        return {
            "today_iso": date.today().isoformat(),
            "STAGES": constants.ALL_STAGES,
            "PIPELINE_STAGES": constants.PIPELINE_STAGES,
            "EXIT_STAGES": constants.EXIT_STAGES,
            "STAGE_LABELS": constants.STAGE_LABELS,
            "STAGE_DESCRIPTIONS": constants.STAGE_DESCRIPTIONS,
            "DECLINE_REASONS": constants.DECLINE_REASONS,
            "WITHDRAW_REASONS": constants.WITHDRAW_REASONS,
            "REFERRAL_SOURCES": constants.REFERRAL_SOURCES,
            "GUARDIAN_RELATIONSHIPS": constants.GUARDIAN_RELATIONSHIPS,
            "CONTACT_METHODS": constants.CONTACT_METHODS,
            "INTERACTION_TYPES": constants.INTERACTION_TYPES,
            "stage_label": constants.stage_label,
            "daycare_name": app.config["DAYCARE_NAME"],
        }


def _register_cli(app):
    """CLI helpers: create the first account, and load demo data."""
    import click

    @app.cli.command("create-user")
    @click.option("--email", prompt=True)
    @click.option("--name", prompt="Full name")
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    def create_user(email, name, password):
        """Create a staff account."""
        from .models import User

        email = User.normalize_email(email)
        if User.query.filter_by(email=email).first():
            click.echo(f"A user with {email} already exists.")
            return
        user = User(email=email, name=name)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Created {email}.")

    @app.cli.command("backup")
    @click.option("--output-dir", default="backups", show_default=True,
                  help="Where to write the backup file.")
    def backup(output_dir):
        """Write every record to a timestamped JSON file."""
        from .backup import export_backup

        path, counts = export_backup(output_dir)
        click.echo(f"Wrote {path}")
        for table, count in counts.items():
            click.echo(f"  {table}: {count}")
        click.echo("\nThis file contains family data and password hashes. "
                   "Keep it out of the repository and somewhere access-controlled.")

    @app.cli.command("restore")
    @click.argument("path", type=click.Path(exists=True))
    @click.option("--force", is_flag=True,
                  help="Allow restoring into a database that already holds records.")
    def restore(path, force):
        """Restore records from a backup file."""
        from .backup import import_backup

        try:
            counts = import_backup(path, allow_non_empty=force)
        except RuntimeError as exc:
            raise click.ClickException(str(exc))
        click.echo(f"Restored from {path}")
        for table, count in counts.items():
            click.echo(f"  {table}: {count}")

    @app.cli.command("seed-demo")
    def seed_demo():
        """Load sample families so the funnel and reports have data."""
        from .seed import seed_demo_data

        created = seed_demo_data()
        db.session.commit()
        click.echo(f"Seeded {created} demo children.")
