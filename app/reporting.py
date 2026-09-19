"""Read-only funnel analytics used by the dashboard and the reports page."""

from collections import Counter, OrderedDict
from datetime import date, timedelta

from sqlalchemy import or_

from .constants import (
    CLOSED_STAGES,
    ENROLLED_STAGES,
    OPTIONAL_STAGES,
    PIPELINE_STAGES,
    STAGE_DATE_FIELDS,
    Stage,
    stage_label,
)
from .extensions import db
from .models import Child, Family
from .utils import pct


def children_in_window(start=None, end=None):
    """Children whose inquiry falls in the window, newest first.

    The window is applied to inquiry_date because every funnel question
    ("of the families who asked about us in Q1, how many enrolled?") is
    anchored to when the family first came in.
    """
    query = Child.query
    if start:
        query = query.filter(Child.inquiry_date >= start)
    if end:
        query = query.filter(Child.inquiry_date <= end)
    return query.order_by(Child.inquiry_date.desc().nullslast(), Child.id.desc()).all()


def stage_counts(children):
    """Current stage -> count."""
    counts = Counter(child.stage for child in children)
    ordered = OrderedDict()
    for stage in PIPELINE_STAGES + [Stage.DECLINED, Stage.WITHDREW]:
        ordered[stage] = counts.get(stage, 0)
    return ordered


def reach_counts(children):
    """How many children ever reached each pipeline stage.

    Counted from the stamped stage dates, so a family that toured and then
    declined still counts toward "toured".
    """
    reached = OrderedDict()
    for stage in PIPELINE_STAGES:
        field = STAGE_DATE_FIELDS[stage]
        reached[stage] = sum(1 for child in children if getattr(child, field, None) is not None)
    return reached


def funnel_rows(children):
    """Funnel table: stage, how many reached it, and % of all inquiries."""
    reached = reach_counts(children)
    top = reached.get(Stage.INQUIRY, 0) or len(children)
    rows = []
    previous = None
    for stage, count in reached.items():
        optional = stage in OPTIONAL_STAGES
        rows.append(
            {
                "stage": stage,
                "label": stage_label(stage),
                "count": count,
                "optional": optional,
                "pct_of_inquiries": pct(count, top),
                # Step conversion against the last *required* stage, so an
                # optional branch like the waitlist does not distort the chain.
                "pct_of_previous": pct(count, previous) if previous is not None else None,
            }
        )
        if not optional:
            previous = count
    return rows


def conversion_summary(children):
    """The handful of numbers worth putting on the dashboard."""
    total = len(children)
    reached = reach_counts(children)
    inquiries = reached.get(Stage.INQUIRY, 0) or total
    toured = reached.get(Stage.TOUR_COMPLETED, 0)
    enrolled = reached.get(Stage.ENROLLED, 0)
    started = reached.get(Stage.ACTIVE, 0)

    declined = sum(1 for c in children if c.stage == Stage.DECLINED)
    withdrew = sum(1 for c in children if c.stage == Stage.WITHDREW)

    durations = [c.days_inquiry_to_enrolled for c in children if c.days_inquiry_to_enrolled is not None]

    return {
        "total": total,
        "inquiries": inquiries,
        "toured": toured,
        "enrolled": enrolled,
        "started": started,
        "declined": declined,
        "withdrew": withdrew,
        "tour_rate": pct(toured, inquiries),
        "tour_to_enroll_rate": pct(enrolled, toured),
        "inquiry_to_enroll_rate": pct(enrolled, inquiries),
        "avg_days_to_enroll": round(sum(durations) / len(durations), 1) if durations else None,
        "open_pipeline": sum(1 for c in children if c.stage not in CLOSED_STAGES),
        "currently_enrolled": sum(1 for c in children if c.stage in ENROLLED_STAGES),
    }


def reason_breakdown(children, stage):
    """Exit reasons for declined/withdrew children, most common first."""
    attr = "decline_reason" if stage == Stage.DECLINED else "withdraw_reason"
    reasons = Counter(
        getattr(child, attr) or "Not recorded" for child in children if child.stage == stage
    )
    total = sum(reasons.values())
    return [
        {"reason": reason, "count": count, "pct": pct(count, total)}
        for reason, count in reasons.most_common()
    ]


def source_breakdown(children):
    """Referral source performance: inquiries vs. how many enrolled."""
    buckets = {}
    for child in children:
        source = (child.family.referral_source if child.family else None) or "Not recorded"
        bucket = buckets.setdefault(source, {"source": source, "inquiries": 0, "enrolled": 0})
        bucket["inquiries"] += 1
        if child.enrolled_date is not None:
            bucket["enrolled"] += 1
    rows = sorted(buckets.values(), key=lambda row: (-row["inquiries"], row["source"]))
    for row in rows:
        row["rate"] = pct(row["enrolled"], row["inquiries"])
    return rows


def monthly_inquiries(months=12, today=None):
    """Inquiries and enrollments per month for the trend chart."""
    today = today or date.today()
    start_month = (today.replace(day=1) - timedelta(days=31 * (months - 1))).replace(day=1)

    buckets = OrderedDict()
    cursor = start_month
    while cursor <= today.replace(day=1):
        buckets[(cursor.year, cursor.month)] = {
            "label": cursor.strftime("%b %Y"),
            "inquiries": 0,
            "enrolled": 0,
        }
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)

    for child in Child.query.all():
        if child.inquiry_date:
            key = (child.inquiry_date.year, child.inquiry_date.month)
            if key in buckets:
                buckets[key]["inquiries"] += 1
        if child.enrolled_date:
            key = (child.enrolled_date.year, child.enrolled_date.month)
            if key in buckets:
                buckets[key]["enrolled"] += 1

    return list(buckets.values())


def upcoming_tours(limit=10, today=None):
    """Scheduled tours that have not happened yet, soonest first."""
    today = today or date.today()
    return (
        Child.query.filter(
            Child.stage == Stage.TOUR_SCHEDULED,
            Child.tour_scheduled_date.isnot(None),
            Child.tour_scheduled_date >= today,
        )
        .order_by(Child.tour_scheduled_date.asc())
        .limit(limit)
        .all()
    )


def needs_follow_up(days=7, limit=10, today=None):
    """Open pipeline children with no movement in a while.

    These are the families most likely to go quiet and decline by default.
    """
    today = today or date.today()
    cutoff = today - timedelta(days=days)
    open_children = Child.query.filter(~Child.stage.in_(list(CLOSED_STAGES))).all()

    stale = []
    for child in open_children:
        last_touch = max(
            [d for d in [child.stage_date, child.inquiry_date] if d is not None]
            + [i.occurred_on for i in child.interactions if i.occurred_on]
            or [date.min]
        )
        if last_touch <= cutoff:
            stale.append((last_touch, child))

    stale.sort(key=lambda pair: pair[0])
    return [{"child": child, "last_touch": last_touch} for last_touch, child in stale[:limit]]


def search_children(term=None, stage=None):
    """Child list filtered by free-text search and/or stage."""
    query = Child.query.join(Family)
    if stage:
        query = query.filter(Child.stage == stage)
    if term:
        like = f"%{term.strip()}%"
        query = query.filter(
            or_(
                Child.first_name.ilike(like),
                Child.last_name.ilike(like),
                Family.family_name.ilike(like),
            )
        )
    return query.order_by(Child.last_name, Child.first_name).all()


def dashboard_context(today=None):
    """Everything the dashboard needs, in one call."""
    today = today or date.today()
    children = Child.query.all()
    return {
        "summary": conversion_summary(children),
        "stage_counts": stage_counts(children),
        "funnel": funnel_rows(children),
        "upcoming_tours": upcoming_tours(today=today),
        "follow_ups": needs_follow_up(today=today),
        "monthly": monthly_inquiries(today=today),
        "total_families": db.session.query(Family).count(),
    }
