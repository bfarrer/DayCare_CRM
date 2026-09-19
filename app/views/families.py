"""Families, their guardians, and the contact log."""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from ..extensions import db
from ..models import Family, Guardian
from ..services import log_interaction
from ..utils import clean, parse_bool, parse_date

bp = Blueprint("families", __name__, url_prefix="/families")


@bp.route("/")
@login_required
def index():
    term = clean(request.args.get("q"))
    query = Family.query
    if term:
        like = f"%{term}%"
        query = query.outerjoin(Guardian).filter(
            or_(
                Family.family_name.ilike(like),
                Guardian.first_name.ilike(like),
                Guardian.last_name.ilike(like),
                Guardian.email.ilike(like),
                Guardian.phone.ilike(like),
            )
        ).distinct()
    families = query.order_by(Family.family_name).all()
    return render_template("families/index.html", families=families, term=term or "")


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "POST":
        family_name = clean(request.form.get("family_name"), 160)
        if not family_name:
            flash("A family name is required.", "error")
            return render_template("families/form.html", family=None, form=request.form)

        family = Family()
        _apply_family_form(family, request.form)
        db.session.add(family)
        db.session.flush()
        _apply_guardian_form(family, request.form)
        db.session.commit()
        flash(f"Added the {family.family_name} family.", "success")
        return redirect(url_for("families.detail", family_id=family.id))

    return render_template("families/form.html", family=None, form={})


@bp.route("/<int:family_id>")
@login_required
def detail(family_id):
    family = db.session.get(Family, family_id) or abort(404)
    return render_template("families/detail.html", family=family)


@bp.route("/<int:family_id>/edit", methods=["GET", "POST"])
@login_required
def edit(family_id):
    family = db.session.get(Family, family_id) or abort(404)
    if request.method == "POST":
        if not clean(request.form.get("family_name"), 160):
            flash("A family name is required.", "error")
            return render_template("families/form.html", family=family, form=request.form)
        _apply_family_form(family, request.form)
        db.session.commit()
        flash("Family details saved.", "success")
        return redirect(url_for("families.detail", family_id=family.id))

    return render_template("families/form.html", family=family, form={})


@bp.route("/<int:family_id>/delete", methods=["POST"])
@login_required
def delete(family_id):
    family = db.session.get(Family, family_id) or abort(404)
    name = family.family_name
    db.session.delete(family)
    db.session.commit()
    flash(f"Deleted the {name} family and all of its records.", "success")
    return redirect(url_for("families.index"))


@bp.route("/<int:family_id>/guardians", methods=["POST"])
@login_required
def add_guardian(family_id):
    family = db.session.get(Family, family_id) or abort(404)
    first_name = clean(request.form.get("first_name"), 80)
    last_name = clean(request.form.get("last_name"), 80)

    if not first_name or not last_name:
        flash("A guardian needs both a first and last name.", "error")
        return redirect(url_for("families.detail", family_id=family.id))

    guardian = Guardian(family=family, first_name=first_name, last_name=last_name)
    _apply_guardian_fields(guardian, request.form)
    db.session.add(guardian)
    db.session.flush()
    _enforce_single_primary(family, guardian)
    db.session.commit()
    flash(f"Added {guardian.full_name}.", "success")
    return redirect(url_for("families.detail", family_id=family.id))


@bp.route("/guardians/<int:guardian_id>/edit", methods=["POST"])
@login_required
def edit_guardian(guardian_id):
    guardian = db.session.get(Guardian, guardian_id) or abort(404)
    first_name = clean(request.form.get("first_name"), 80)
    last_name = clean(request.form.get("last_name"), 80)
    if not first_name or not last_name:
        flash("A guardian needs both a first and last name.", "error")
        return redirect(url_for("families.detail", family_id=guardian.family_id))

    guardian.first_name = first_name
    guardian.last_name = last_name
    _apply_guardian_fields(guardian, request.form)
    _enforce_single_primary(guardian.family, guardian)
    db.session.commit()
    flash(f"Updated {guardian.full_name}.", "success")
    return redirect(url_for("families.detail", family_id=guardian.family_id))


@bp.route("/guardians/<int:guardian_id>/delete", methods=["POST"])
@login_required
def delete_guardian(guardian_id):
    guardian = db.session.get(Guardian, guardian_id) or abort(404)
    family_id = guardian.family_id
    db.session.delete(guardian)
    db.session.commit()
    flash("Removed the contact.", "success")
    return redirect(url_for("families.detail", family_id=family_id))


@bp.route("/<int:family_id>/interactions", methods=["POST"])
@login_required
def add_interaction(family_id):
    family = db.session.get(Family, family_id) or abort(404)
    summary = clean(request.form.get("summary"), 200)
    body = clean(request.form.get("body"))

    if not summary and not body:
        flash("Add a summary or a note before saving.", "error")
        return redirect(url_for("families.detail", family_id=family.id))

    child = None
    child_id = clean(request.form.get("child_id"))
    if child_id and child_id.isdigit():
        child = next((c for c in family.children if c.id == int(child_id)), None)

    log_interaction(
        family=family,
        user=current_user,
        interaction_type=clean(request.form.get("interaction_type"), 40),
        occurred_on=parse_date(request.form.get("occurred_on")),
        summary=summary,
        body=body,
        child=child,
    )
    db.session.commit()
    flash("Logged the contact.", "success")
    return redirect(url_for("families.detail", family_id=family.id))


def _apply_family_form(family, form):
    family.family_name = clean(form.get("family_name"), 160)
    family.address_line1 = clean(form.get("address_line1"), 200)
    family.address_line2 = clean(form.get("address_line2"), 200)
    family.city = clean(form.get("city"), 120)
    family.state = clean(form.get("state"), 60)
    family.postal_code = clean(form.get("postal_code"), 20)
    family.referral_source = clean(form.get("referral_source"), 80)
    family.preferred_contact_method = clean(form.get("preferred_contact_method"), 40)
    family.notes = clean(form.get("notes"))


def _apply_guardian_form(family, form):
    """Create the first guardian from the new-family form, if one was given."""
    first_name = clean(form.get("guardian_first_name"), 80)
    last_name = clean(form.get("guardian_last_name"), 80)
    if not (first_name and last_name):
        return
    guardian = Guardian(
        family=family,
        first_name=first_name,
        last_name=last_name,
        relationship_to_child=clean(form.get("guardian_relationship"), 40),
        email=clean(form.get("guardian_email"), 255),
        phone=clean(form.get("guardian_phone"), 40),
        is_primary=True,
    )
    db.session.add(guardian)


def _apply_guardian_fields(guardian, form):
    guardian.relationship_to_child = clean(form.get("relationship_to_child"), 40)
    guardian.email = clean(form.get("email"), 255)
    guardian.phone = clean(form.get("phone"), 40)
    guardian.is_primary = parse_bool(form.get("is_primary"))


def _enforce_single_primary(family, guardian):
    """Exactly one primary contact per family."""
    if guardian.is_primary:
        for other in family.guardians:
            if other.id != guardian.id:
                other.is_primary = False
    elif not any(g.is_primary for g in family.guardians):
        guardian.is_primary = True
