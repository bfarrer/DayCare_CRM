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


def test_available_years_span_from_the_earliest_inquiry(db, family):
    create_child(family=family, first_name="Old", last_name="Test", inquiry_date=date(2024, 6, 1))
    create_child(family=family, first_name="New", last_name="Test", inquiry_date=date(2026, 6, 1))
    db.session.commit()

    from app.reporting import available_school_years

    years = available_school_years(today=date(2026, 9, 28))

    # Newest first, contiguous, with no gap for the year that had no inquiries.
    assert [y["label"] for y in years] == ["2026–27", "2025–26", "2024–25"]
    assert years[0]["is_current"] is True
    assert years[1]["is_current"] is False


def test_available_years_is_never_empty_on_a_fresh_database(db):
    from app.reporting import available_school_years

    years = available_school_years(today=date(2026, 9, 28))
    assert len(years) == 1
    assert years[0]["label"] == "2026–27"
    assert years[0]["is_current"] is True


def test_selecting_a_past_school_year(db, family):
    create_child(family=family, first_name="Old", last_name="Test", inquiry_date=date(2025, 9, 1))
    create_child(family=family, first_name="New", last_name="Test", inquiry_date=date(2026, 9, 1))
    db.session.commit()

    current = dashboard_context(today=date(2026, 9, 28))
    past = dashboard_context(today=date(2026, 9, 28), school_year_start=2025)

    assert current["summary"]["inquiries"] == 1
    assert current["school_year"]["is_current"] is True
    assert past["summary"]["inquiries"] == 1
    assert past["school_year"]["label"] == "2025–26"
    assert past["school_year"]["is_current"] is False
    # Live counts describe right now, so they do not change with the selection.
    assert past["live"]["open_pipeline"] == current["live"]["open_pipeline"] == 2


def test_an_unknown_school_year_falls_back_to_the_current_one(db, family):
    create_child(family=family, first_name="Now", last_name="Test", inquiry_date=date(2026, 9, 1))
    db.session.commit()

    for bogus in (1999, 9999, -1):
        context = dashboard_context(today=date(2026, 9, 28), school_year_start=bogus)
        assert context["school_year"]["label"] == "2026–27"
        assert context["school_year"]["is_current"] is True


def test_the_dashboard_renders_a_selected_year(auth_client, db):
    from app.models import Family

    family = Family(family_name="The Test Family")
    db.session.add(family)
    db.session.commit()
    auth_client.post(
        "/students/new",
        data={"first_name": "Mei", "last_name": "Test", "family_id": family.id},
        follow_redirects=True,
    )

    assert auth_client.get("/?school_year=2025").status_code == 200
    # A non-numeric value must not raise.
    assert auth_client.get("/?school_year=banana").status_code == 200
