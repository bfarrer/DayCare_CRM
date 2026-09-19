"""Sign in, sign out, and changing your own password."""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..models import User, utcnow
from ..utils import clean

bp = Blueprint("auth", __name__)


def _is_safe_next(target):
    """Only allow relative redirects, so ?next= cannot bounce off-site."""
    return bool(target) and target.startswith("/") and not target.startswith("//")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        email = User.normalize_email(request.form.get("email"))
        password = request.form.get("password") or ""
        user = User.query.filter_by(email=email).first()

        if user is None or not user.check_password(password):
            # Deliberately vague: do not reveal which accounts exist.
            flash("Email or password is incorrect.", "error")
        elif not user.is_active_user:
            flash("That account has been deactivated. Ask a teammate to re-enable it.", "error")
        else:
            login_user(user, remember=bool(request.form.get("remember")))
            user.last_login_at = utcnow()
            db.session.commit()
            target = request.args.get("next")
            return redirect(target if _is_safe_next(target) else url_for("dashboard.index"))

    return render_template("login.html")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "success")
    return redirect(url_for("auth.login"))


@bp.route("/account", methods=["GET", "POST"])
@login_required
def account():
    if request.method == "POST":
        name = clean(request.form.get("name"), 120)
        current = request.form.get("current_password") or ""
        new_password = request.form.get("new_password") or ""
        confirm = request.form.get("confirm_password") or ""

        if not current_user.check_password(current):
            flash("Your current password is incorrect.", "error")
            return render_template("account.html")

        if name:
            current_user.name = name

        if new_password:
            if len(new_password) < 10:
                flash("Choose a password of at least 10 characters.", "error")
                return render_template("account.html")
            if new_password != confirm:
                flash("The new passwords do not match.", "error")
                return render_template("account.html")
            current_user.set_password(new_password)

        db.session.commit()
        flash("Your account has been updated.", "success")
        return redirect(url_for("auth.account"))

    return render_template("account.html")
