"""Students: the list, the pipeline board, and stage changes."""

import csv
import io
from datetime import date

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from ..constants import ALL_STAGES, PIPELINE_STAGES, STAGE_DATE_FIELDS, Stage, stage_label
from ..extensions import db
from ..models import Child, Family
from ..reporting import search_children
from ..services import StageChangeError, change_stage, create_child
from ..utils import clean, parse_date

bp = Blueprint("children", __name__, url_prefix="/students")


@bp.route("/")
@login_required
def index():
    term = clean(request.args.get("q"))
    stage = clean(request.args.get("stage"))
    if stage not in ALL_STAGES:
        stage = None
    children = search_children(term=term, stage=stage)
    return render_template("children/index.html", children=children, term=term or "", stage=stage)


@bp.route("/board")
@login_required
def board():
    """Pipeline board: one column per stage."""
    columns = []
    for stage in PIPELINE_STAGES:
        children = (
            Child.query.filter(Child.stage == stage)
            .order_by(Child.last_name, Child.first_name)
            .all()
        )
        columns.append({"stage": stage, "label": stage_label(stage), "children": children})

    exits = {
        stage: Child.query.filter(Child.stage == stage).count()
        for stage in (Stage.DECLINED, Stage.WITHDREW)
    }
    return render_template("children/board.html", columns=columns, exits=exits)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    family_id = request.args.get("family_id", type=int)
    families = Family.query.order_by(Family.family_name).all()

    if request.method == "POST":
        first_name = clean(request.form.get("first_name"), 80)
        last_name = clean(request.form.get("last_name"), 80)
        family = db.session.get(Family, request.form.get("family_id", type=int) or 0)

        if not (first_name and last_name and family):
            flash("A first name, last name, and family are all required.", "error")
            return render_template(
                "children/form.html", child=None, families=families, form=request.form
            )

        child = create_child(
            family=family,
            first_name=first_name,
            last_name=last_name,
            inquiry_date=parse_date(request.form.get("inquiry_date")) or date.today(),
            user=current_user,
            date_of_birth=parse_date(request.form.get("date_of_birth")),
            desired_start_date=parse_date(request.form.get("desired_start_date")),
            program=clean(request.form.get("program"), 80),
            classroom=clean(request.form.get("classroom"), 80),
            notes=clean(request.form.get("notes")),
        )
        db.session.commit()
        flash(f"Added {child.full_name} to the funnel.", "success")
        return redirect(url_for("children.detail", child_id=child.id))

    return render_template(
        "children/form.html",
        child=None,
        families=families,
        form={"family_id": family_id, "inquiry_date": date.today().isoformat()},
    )


@bp.route("/<int:child_id>")
@login_required
def detail(child_id):
    child = db.session.get(Child, child_id) or abort(404)
    timeline = [
        {"stage": stage, "label": stage_label(stage), "date": getattr(child, field, None)}
        for stage, field in STAGE_DATE_FIELDS.items()
        if getattr(child, field, None) is not None
    ]
    timeline.sort(key=lambda item: item["date"])
    return render_template("children/detail.html", child=child, timeline=timeline)


@bp.route("/<int:child_id>/edit", methods=["GET", "POST"])
@login_required
def edit(child_id):
    child = db.session.get(Child, child_id) or abort(404)
    families = Family.query.order_by(Family.family_name).all()

    if request.method == "POST":
        first_name = clean(request.form.get("first_name"), 80)
        last_name = clean(request.form.get("last_name"), 80)
        family = db.session.get(Family, request.form.get("family_id", type=int) or 0)
        if not (first_name and last_name and family):
            flash("A first name, last name, and family are all required.", "error")
            return render_template(
                "children/form.html", child=child, families=families, form=request.form
            )

        child.first_name = first_name
        child.last_name = last_name
        child.family = family
        child.date_of_birth = parse_date(request.form.get("date_of_birth"))
        child.desired_start_date = parse_date(request.form.get("desired_start_date"))
        child.inquiry_date = parse_date(request.form.get("inquiry_date")) or child.inquiry_date
        child.program = clean(request.form.get("program"), 80)
        child.classroom = clean(request.form.get("classroom"), 80)
        child.notes = clean(request.form.get("notes"))
        db.session.commit()
        flash("Student details saved.", "success")
        return redirect(url_for("children.detail", child_id=child.id))

    return render_template("children/form.html", child=child, families=families, form={})


@bp.route("/<int:child_id>/stage", methods=["POST"])
@login_required
def update_stage(child_id):
    child = db.session.get(Child, child_id) or abort(404)
    new_stage = clean(request.form.get("stage"))
    reason = clean(request.form.get("reason"), 120)

    # "Other" reasons live in the note; keep the dropdown value as the reason.
    note = clean(request.form.get("note"))

    try:
        change_stage(
            child,
            new_stage,
            occurred_on=parse_date(request.form.get("occurred_on")) or date.today(),
            reason=reason,
            note=note,
            user=current_user,
        )
    except StageChangeError as exc:
        db.session.rollback()
        flash(str(exc), "error")
        return redirect(url_for("children.detail", child_id=child.id))

    db.session.commit()
    flash(f"{child.full_name} is now {stage_label(child.stage)}.", "success")
    return redirect(url_for("children.detail", child_id=child.id))


@bp.route("/<int:child_id>/delete", methods=["POST"])
@login_required
def delete(child_id):
    child = db.session.get(Child, child_id) or abort(404)
    family_id = child.family_id
    name = child.full_name
    db.session.delete(child)
    db.session.commit()
    flash(f"Deleted {name}.", "success")
    return redirect(url_for("families.detail", family_id=family_id))


@bp.route("/export.csv")
@login_required
def export_csv():
    """Every student with their funnel dates -- for spreadsheets and backups."""
    children = Child.query.join(Family).order_by(Family.family_name, Child.first_name).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "Child first name",
            "Child last name",
            "Date of birth",
            "Family",
            "Primary contact",
            "Primary email",
            "Primary phone",
            "Referral source",
            "Stage",
            "Inquiry date",
            "Contacted date",
            "Tour scheduled",
            "Tour completed",
            "Waitlist date",
            "Enrolled date",
            "Start date (active)",
            "Graduated date",
            "Declined date",
            "Decline reason",
            "Withdrew date",
            "Withdraw reason",
        ]
    )

    for child in children:
        contact = child.family.primary_guardian if child.family else None
        writer.writerow(
            [
                child.first_name,
                child.last_name,
                child.date_of_birth or "",
                child.family.family_name if child.family else "",
                contact.full_name if contact else "",
                contact.email if contact else "",
                contact.phone if contact else "",
                child.family.referral_source if child.family else "",
                stage_label(child.stage),
                child.inquiry_date or "",
                child.contacted_date or "",
                child.tour_scheduled_date or "",
                child.tour_completed_date or "",
                child.waitlist_date or "",
                child.enrolled_date or "",
                child.active_date or "",
                child.graduated_date or "",
                child.declined_date or "",
                child.decline_reason or "",
                child.withdrew_date or "",
                child.withdraw_reason or "",
            ]
        )

    filename = f"students-{date.today().isoformat()}.csv"
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
