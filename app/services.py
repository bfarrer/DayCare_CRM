"""Business rules that change data, kept out of the view functions."""

from datetime import date

from .constants import EXIT_STAGES, STAGE_DATE_FIELDS, Stage, stage_label
from .extensions import db
from .models import Child, Interaction, StageEvent


class StageChangeError(ValueError):
    """Raised when a requested stage change is not allowed."""


def change_stage(child, new_stage, occurred_on=None, reason=None, note=None, user=None):
    """Move a child to a new stage, stamping dates and writing an audit event.

    Declining and withdrawing both require a reason -- that is the whole point
    of tracking them separately from the rest of the funnel.
    """
    if new_stage not in STAGE_DATE_FIELDS:
        raise StageChangeError(f"'{new_stage}' is not a valid stage.")

    if new_stage in EXIT_STAGES and not reason:
        raise StageChangeError(f"A reason is required when marking a child {stage_label(new_stage)}.")

    occurred_on = occurred_on or date.today()
    previous_stage = child.stage

    if previous_stage == new_stage and _stage_date(child, new_stage) == occurred_on:
        # Nothing changed -- avoid writing a duplicate audit row.
        return None

    child.stage = new_stage
    setattr(child, STAGE_DATE_FIELDS[new_stage], occurred_on)

    if new_stage == Stage.DECLINED:
        child.decline_reason = reason
        child.decline_notes = note
    elif new_stage == Stage.WITHDREW:
        child.withdraw_reason = reason
        child.withdraw_notes = note

    event = StageEvent(
        child=child,
        user=user if user and getattr(user, "id", None) else None,
        from_stage=previous_stage,
        to_stage=new_stage,
        occurred_on=occurred_on,
        reason=reason,
        note=note,
    )
    db.session.add(event)
    return event


def _stage_date(child, stage):
    field = STAGE_DATE_FIELDS.get(stage)
    return getattr(child, field, None) if field else None


def create_child(family, first_name, last_name, stage=Stage.INQUIRY, inquiry_date=None, user=None, **fields):
    """Create a child already positioned in the funnel with its audit trail."""
    child = Child(
        family=family,
        first_name=first_name,
        last_name=last_name,
        stage=Stage.INQUIRY,
        inquiry_date=inquiry_date or date.today(),
        **fields,
    )
    db.session.add(child)
    db.session.add(
        StageEvent(
            child=child,
            user=user if user and getattr(user, "id", None) else None,
            from_stage=None,
            to_stage=Stage.INQUIRY,
            occurred_on=child.inquiry_date,
            note="Record created.",
        )
    )
    # A child added straight into a later stage gets that transition recorded too.
    if stage and stage != Stage.INQUIRY:
        change_stage(child, stage, occurred_on=date.today(), user=user)
    return child


def log_interaction(family, user, interaction_type, occurred_on=None, summary=None, body=None, child=None):
    """Record a touchpoint against a family, optionally tied to one child."""
    interaction = Interaction(
        family=family,
        child=child,
        user=user if user and getattr(user, "id", None) else None,
        interaction_type=interaction_type or "Note",
        occurred_on=occurred_on or date.today(),
        summary=summary,
        body=body,
    )
    db.session.add(interaction)
    return interaction
