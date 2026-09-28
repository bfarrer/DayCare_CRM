"""School-year windowing and the open-pipeline definition."""

from datetime import date

import pytest

from app.constants import PROSPECT_STAGES, Stage
from app.models import Child, Family
from app.reporting import (
    conversion_summary,
    dashboard_context,
    school_year_bounds,
    school_year_label,
)
from app.services import change_stage, create_child


@pytest.fixture
def family(db):
    family = Family(family_name="The Test Family")
    db.session.add(family)
    db.session.commit()
    return family


@pytest.mark.parametrize(
    "today, expected_start, expected_end",
    [
        # April 1 opens a new school year.
        (date(2026, 4, 1), date(2026, 4, 1), date(2027, 3, 31)),
        # Mid-year.
        (date(2026, 9, 28), date(2026, 4, 1), date(2027, 3, 31)),
        # January still belongs to the year that began the previous April.
        (date(2027, 1, 15), date(2026, 4, 1), date(2027, 3, 31)),
        # March 31 is the last day of that year.
        (date(2027, 3, 31), date(2026, 4, 1), date(2027, 3, 31)),
        # The day before a year starts belongs to the previous one.
        (date(2026, 3, 31), date(2025, 4, 1), date(2026, 3, 31)),
        # Leap year: February 29 resolves normally.
        (date(2028, 2, 29), date(2027, 4, 1), date(2028, 3, 31)),
    ],
)
def test_school_year_bounds(today, expected_start, expected_end):
    start, end = school_year_bounds(today)
    assert (start, end) == (expected_start, expected_end)


def test_school_years_are_contiguous_with_no_orphan_day():
    """Every date belongs to exactly one school year -- no gap at the boundary."""
    from datetime import timedelta

    _, end = school_year_bounds(date(2026, 6, 1))
    next_start, _ = school_year_bounds(end + timedelta(days=1))
    assert next_start == date(2027, 4, 1)
    assert end == date(2027, 3, 31)


def test_school_year_label():
    assert school_year_label(date(2026, 4, 1)) == "2026–27"
    assert school_year_label(date(2029, 4, 1)) == "2029–30"


def test_open_pipeline_counts_only_prospects(db, family):
    """Inquiry through Waitlist. Enrolled and Active are already won."""
    plan = [
        (Stage.INQUIRY, None),
        (Stage.CONTACTED, None),
        (Stage.TOUR_SCHEDULED, None),
        (Stage.TOUR_COMPLETED, None),
        (Stage.WAITLIST, None),
        (Stage.ENROLLED, None),
        (Stage.ACTIVE, None),
        (Stage.GRADUATED, None),
        (Stage.DECLINED, "Cost / tuition"),
        (Stage.WITHDREW, "Moved out of area"),
    ]
    for index, (stage, reason) in enumerate(plan):
        child = create_child(family=family, first_name=f"Kid{index}", last_name="Test")
        if stage != Stage.INQUIRY:
            change_stage(child, stage, reason=reason)
    db.session.commit()

    summary = conversion_summary(Child.query.all())

    # One child sits in each of the five prospect stages.
    assert summary["open_pipeline"] == 5
    assert len(PROSPECT_STAGES) == 5
    # The two in our care are reported separately, not doubled into the pipeline.
    assert summary["currently_enrolled"] == 2


def test_dashboard_funnel_is_limited_to_the_current_school_year(db, family):
    today = date(2026, 9, 28)  # school year 2026-27

    this_year = create_child(
        family=family, first_name="Now", last_name="Test", inquiry_date=date(2026, 5, 2)
    )
    last_year = create_child(
        family=family, first_name="Old", last_name="Test", inquiry_date=date(2026, 3, 30)
    )
    # A family who inquired last school year but is still being worked.
    change_stage(last_year, Stage.TOUR_COMPLETED, occurred_on=date(2026, 4, 10))
    db.session.commit()

    context = dashboard_context(today=today)

    # The funnel covers only the child who inquired inside this school year.
    assert context["summary"]["inquiries"] == 1
    assert context["school_year"]["label"] == "2026–27"
    assert context["school_year"]["start"] == date(2026, 4, 1)
    assert context["school_year"]["end"] == date(2027, 3, 31)

    # But the live pipeline still shows both -- last year's family is real work.
    assert context["live"]["open_pipeline"] == 2
    assert context["live"]["total_students"] == 2


def test_a_march_thirty_first_inquiry_is_not_lost(db, family):
    """The boundary day belongs to a school year rather than falling through."""
    create_child(
        family=family, first_name="Edge", last_name="Test", inquiry_date=date(2027, 3, 31)
    )
    db.session.commit()

    # Counted in 2026-27, on its final day...
    assert dashboard_context(today=date(2027, 3, 31))["summary"]["inquiries"] == 1
    # ...and not carried into the next year.
    assert dashboard_context(today=date(2027, 4, 1))["summary"]["inquiries"] == 0
