"""The funnel rules: stage changes, date stamping, and exit reasons."""

from datetime import date, timedelta

import pytest

from app.constants import Stage
from app.models import Child, Family, StageEvent
from app.reporting import conversion_summary, reason_breakdown, reach_counts
from app.services import StageChangeError, change_stage, create_child


@pytest.fixture
def family(db):
    family = Family(family_name="The Test Family")
    db.session.add(family)
    db.session.commit()
    return family


def test_new_child_starts_at_inquiry_with_a_stamped_date(db, family):
    child = create_child(family=family, first_name="Ada", last_name="Test")
    db.session.commit()

    assert child.stage == Stage.INQUIRY
    assert child.inquiry_date == date.today()
    assert len(child.stage_events) == 1


def test_stage_change_stamps_the_matching_date_and_logs_an_event(db, family, user):
    child = create_child(family=family, first_name="Ada", last_name="Test")
    db.session.commit()

    when = date.today() - timedelta(days=3)
    change_stage(child, Stage.TOUR_COMPLETED, occurred_on=when, user=user)
    db.session.commit()

    assert child.stage == Stage.TOUR_COMPLETED
    assert child.tour_completed_date == when
    event = StageEvent.query.filter_by(to_stage=Stage.TOUR_COMPLETED).one()
    assert event.from_stage == Stage.INQUIRY
    assert event.user_id == user.id


def test_declining_requires_a_reason(db, family):
    child = create_child(family=family, first_name="Ada", last_name="Test")
    db.session.commit()

    with pytest.raises(StageChangeError):
        change_stage(child, Stage.DECLINED)

    assert child.stage == Stage.INQUIRY


def test_withdrawing_requires_a_reason(db, family):
    child = create_child(family=family, first_name="Ada", last_name="Test")
    db.session.commit()

    with pytest.raises(StageChangeError):
        change_stage(child, Stage.WITHDREW)


def test_decline_records_reason_and_notes_separately_from_withdrawal(db, family):
    child = create_child(family=family, first_name="Ada", last_name="Test")
    change_stage(child, Stage.DECLINED, reason="Cost / tuition", note="Going with grandma")
    db.session.commit()

    assert child.stage == Stage.DECLINED
    assert child.decline_reason == "Cost / tuition"
    assert child.decline_notes == "Going with grandma"
    assert child.withdraw_reason is None
    assert child.exit_reason == "Cost / tuition"


def test_withdrawal_is_tracked_apart_from_decline(db, family):
    child = create_child(family=family, first_name="Ben", last_name="Test")
    change_stage(child, Stage.ACTIVE, occurred_on=date(2026, 1, 12))
    change_stage(child, Stage.WITHDREW, occurred_on=date(2026, 6, 1), reason="Moved out of area")
    db.session.commit()

    assert child.stage == Stage.WITHDREW
    assert child.withdrew_date == date(2026, 6, 1)
    assert child.withdraw_reason == "Moved out of area"
    assert child.decline_reason is None
    # The earlier progress is preserved, not overwritten by the exit.
    assert child.active_date == date(2026, 1, 12)


def test_an_unknown_stage_is_rejected(db, family):
    child = create_child(family=family, first_name="Ada", last_name="Test")
    with pytest.raises(StageChangeError):
        change_stage(child, "napping")


def test_repeating_the_same_stage_and_date_does_not_duplicate_history(db, family):
    child = create_child(family=family, first_name="Ada", last_name="Test")
    change_stage(child, Stage.CONTACTED, occurred_on=date(2026, 5, 1))
    db.session.commit()
    before = len(child.stage_events)

    change_stage(child, Stage.CONTACTED, occurred_on=date(2026, 5, 1))
    db.session.commit()

    assert len(child.stage_events) == before


def test_a_child_who_toured_then_declined_still_counts_as_toured(db, family):
    child = create_child(family=family, first_name="Ada", last_name="Test")
    change_stage(child, Stage.TOUR_COMPLETED, occurred_on=date(2026, 3, 1))
    change_stage(child, Stage.DECLINED, occurred_on=date(2026, 3, 9), reason="Cost / tuition")
    db.session.commit()

    reached = reach_counts([child])
    assert reached[Stage.TOUR_COMPLETED] == 1
    assert child.toured is True


def test_conversion_summary_counts_declines_and_withdrawals_separately(db, family):
    enrolled = create_child(family=family, first_name="Ada", last_name="Test")
    change_stage(enrolled, Stage.ENROLLED, occurred_on=date.today())

    declined = create_child(family=family, first_name="Bo", last_name="Test")
    change_stage(declined, Stage.DECLINED, reason="Location / commute")

    withdrew = create_child(family=family, first_name="Cy", last_name="Test")
    change_stage(withdrew, Stage.ENROLLED, occurred_on=date.today())
    change_stage(withdrew, Stage.WITHDREW, reason="Schedule change")
    db.session.commit()

    summary = conversion_summary(Child.query.all())
    assert summary["total"] == 3
    assert summary["declined"] == 1
    assert summary["withdrew"] == 1
    assert summary["enrolled"] == 2  # both reached Enrolled, even the one who left


def test_reason_breakdown_groups_by_reason(db, family):
    for name in ("Ada", "Bo"):
        child = create_child(family=family, first_name=name, last_name="Test")
        change_stage(child, Stage.DECLINED, reason="Cost / tuition")
    other = create_child(family=family, first_name="Cy", last_name="Test")
    change_stage(other, Stage.DECLINED, reason="Location / commute")
    db.session.commit()

    rows = reason_breakdown(Child.query.all(), Stage.DECLINED)
    assert rows[0]["reason"] == "Cost / tuition"
    assert rows[0]["count"] == 2
    assert rows[0]["pct"] == pytest.approx(66.7, abs=0.1)


def test_days_from_inquiry_to_enrollment(db, family):
    child = create_child(family=family, first_name="Ada", last_name="Test", inquiry_date=date(2026, 1, 1))
    change_stage(child, Stage.ENROLLED, occurred_on=date(2026, 2, 10))
    db.session.commit()

    assert child.days_inquiry_to_enrolled == 40


def test_waitlist_does_not_distort_step_conversion(db, family):
    """The waitlist is a side branch, so Enrolled is measured against Tour Completed."""
    from app.reporting import funnel_rows

    # Four children tour; one waits, and two of the four go on to enroll.
    children = []
    for index, name in enumerate(("Ada", "Bo", "Cy", "Di")):
        child = create_child(family=family, first_name=name, last_name="Test")
        change_stage(child, Stage.TOUR_COMPLETED, occurred_on=date(2026, 2, 1))
        children.append(child)
    change_stage(children[0], Stage.WAITLIST, occurred_on=date(2026, 2, 5))
    change_stage(children[1], Stage.ENROLLED, occurred_on=date(2026, 2, 8))
    change_stage(children[2], Stage.ENROLLED, occurred_on=date(2026, 2, 9))
    db.session.commit()

    rows = {row["stage"]: row for row in funnel_rows(Child.query.all())}

    assert rows[Stage.WAITLIST]["count"] == 1
    assert rows[Stage.WAITLIST]["optional"] is True
    assert rows[Stage.ENROLLED]["count"] == 2
    # 2 of the 4 who toured -- not 200% of the single waitlisted child.
    assert rows[Stage.ENROLLED]["pct_of_previous"] == pytest.approx(50.0)
