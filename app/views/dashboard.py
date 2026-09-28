"""Dashboard: the funnel at a glance."""

from flask import Blueprint, render_template, request
from flask_login import login_required

from ..reporting import dashboard_context

bp = Blueprint("dashboard", __name__)


@bp.route("/")
@login_required
def index():
    # ?school_year=2026 selects the year beginning April 2026; anything we do
    # not offer falls back to the current year rather than erroring.
    selected = request.args.get("school_year", type=int)
    return render_template("dashboard.html", **dashboard_context(school_year_start=selected))
