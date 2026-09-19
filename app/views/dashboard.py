"""Dashboard: the funnel at a glance."""

from flask import Blueprint, render_template
from flask_login import login_required

from ..reporting import dashboard_context

bp = Blueprint("dashboard", __name__)


@bp.route("/")
@login_required
def index():
    return render_template("dashboard.html", **dashboard_context())
