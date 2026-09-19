"""Team management. Every signed-in user has the same permissions."""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import User
from ..utils import clean

bp = Blueprint("users", __name__, url_prefix="/team")

MIN_PASSWORD_LENGTH = 10


@bp.route("/")
@login_required
def index():
    users = User.query.order_by(User.name).all()
    return render_template("users/index.html", users=users)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "POST":
        email = User.normalize_email(request.form.get("email"))
        name = clean(request.form.get("name"), 120)
        password = request.form.get("password") or ""

        error = None
        if not email or "@" not in email:
            error = "Enter a valid email address."
        elif not name:
            error = "Enter the person's name."
        elif len(password) < MIN_PASSWORD_LENGTH:
            error = f"Choose a password of at least {MIN_PASSWORD_LENGTH} characters."
        elif User.query.filter_by(email=email).first():
            error = "Someone with that email already has an account."

        if error:
            flash(error, "error")
            return render_template("users/form.html", form=request.form)

        user = User(email=email, name=name)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash(f"Added {user.name}. Share the password with them and ask them to change it.", "success")
        return redirect(url_for("users.index"))

    return render_template("users/form.html", form={})


@bp.route("/<int:user_id>/toggle", methods=["POST"])
@login_required
def toggle_active(user_id):
    user = db.session.get(User, user_id) or abort(404)

    if user.id == current_user.id:
        flash("You cannot deactivate your own account.", "error")
        return redirect(url_for("users.index"))

    active_count = User.query.filter_by(is_active_user=True).count()
    if user.is_active_user and active_count <= 1:
        flash("At least one account must stay active.", "error")
        return redirect(url_for("users.index"))

    user.is_active_user = not user.is_active_user
    db.session.commit()
    state = "reactivated" if user.is_active_user else "deactivated"
    flash(f"{user.name} has been {state}.", "success")
    return redirect(url_for("users.index"))


@bp.route("/<int:user_id>/reset-password", methods=["POST"])
@login_required
def reset_password(user_id):
    """Set a teammate's password -- for when someone is locked out."""
    user = db.session.get(User, user_id) or abort(404)
    password = request.form.get("password") or ""

    if len(password) < MIN_PASSWORD_LENGTH:
        flash(f"Choose a password of at least {MIN_PASSWORD_LENGTH} characters.", "error")
    else:
        user.set_password(password)
        db.session.commit()
        flash(f"Set a new password for {user.name}.", "success")

    return redirect(url_for("users.index"))
