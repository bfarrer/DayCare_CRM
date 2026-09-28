"""Dashboard: the funnel at a glance."""

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required
from sqlalchemy import text

from ..extensions import db
from ..reporting import dashboard_context

bp = Blueprint("dashboard", __name__)


@bp.route("/healthz")
def healthz():
    """Liveness check for the host. Deliberately unauthenticated.

    Reports whether the database is reachable, and nothing else -- it must
    never leak record counts or any family information to an anonymous caller.
    """
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        db.session.rollback()
        return jsonify({"status": "error", "database": "unreachable"}), 503
    return jsonify({"status": "ok", "database": "ok"}), 200


@bp.route("/")
@login_required
def index():
    # ?school_year=2026 selects the year beginning April 2026; anything we do
    # not offer falls back to the current year rather than erroring.
    selected = request.args.get("school_year", type=int)
    return render_template("dashboard.html", **dashboard_context(school_year_start=selected))
