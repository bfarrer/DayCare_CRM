"""Demo data so the funnel and reports have something to show.

Never run this against a database holding real families.
"""

import random
from datetime import date, timedelta

from .constants import DECLINE_REASONS, REFERRAL_SOURCES, WITHDRAW_REASONS, Stage
from .extensions import db
from .models import Child, Family, Guardian, User
from .services import change_stage, create_child, log_interaction

FAMILY_SEEDS = [
    ("The Alvarez Family", "Maria", "Alvarez", "Mother", "maria.alvarez@example.com", "555-0142"),
    ("The Bennett Family", "James", "Bennett", "Father", "j.bennett@example.com", "555-0178"),
    ("The Chen Family", "Wei", "Chen", "Mother", "wei.chen@example.com", "555-0113"),
    ("The Donnelly Family", "Erin", "Donnelly", "Mother", "erin.d@example.com", "555-0196"),
    ("The Ferraro Family", "Nick", "Ferraro", "Father", "nferraro@example.com", "555-0155"),
    ("The Grant Family", "Alicia", "Grant", "Mother", "agrant@example.com", "555-0127"),
    ("The Haddad Family", "Samir", "Haddad", "Father", "shaddad@example.com", "555-0164"),
    ("The Iverson Family", "Beth", "Iverson", "Grandmother", "beth.iverson@example.com", "555-0189"),
    ("The Jackson Family", "Tanya", "Jackson", "Mother", "tjackson@example.com", "555-0131"),
    ("The Kowalski Family", "Peter", "Kowalski", "Father", "pkowalski@example.com", "555-0172"),
    ("The Lindqvist Family", "Anna", "Lindqvist", "Mother", "anna.l@example.com", "555-0148"),
    ("The Moreau Family", "Claire", "Moreau", "Mother", "cmoreau@example.com", "555-0159"),
]

CHILD_NAMES = [
    "Sofia", "Liam", "Mei", "Declan", "Gianna", "Owen", "Layla", "Noah",
    "Zara", "Elliot", "Ingrid", "Theo", "Rosa", "Marcus", "Nina", "Caleb",
]

# Each tuple is (final stage, how many students land there).
STAGE_PLAN = [
    (Stage.INQUIRY, 3),
    (Stage.CONTACTED, 2),
    (Stage.TOUR_SCHEDULED, 2),
    (Stage.TOUR_COMPLETED, 2),
    (Stage.WAITLIST, 2),
    (Stage.ENROLLED, 2),
    (Stage.ACTIVE, 4),
    (Stage.GRADUATED, 2),
    (Stage.DECLINED, 4),
    (Stage.WITHDREW, 2),
]

# The path a student walks to reach each final stage.
PATHS = {
    Stage.INQUIRY: [],
    Stage.CONTACTED: [Stage.CONTACTED],
    Stage.TOUR_SCHEDULED: [Stage.CONTACTED, Stage.TOUR_SCHEDULED],
    Stage.TOUR_COMPLETED: [Stage.CONTACTED, Stage.TOUR_SCHEDULED, Stage.TOUR_COMPLETED],
    Stage.WAITLIST: [Stage.CONTACTED, Stage.TOUR_SCHEDULED, Stage.TOUR_COMPLETED, Stage.WAITLIST],
    Stage.ENROLLED: [Stage.CONTACTED, Stage.TOUR_SCHEDULED, Stage.TOUR_COMPLETED, Stage.ENROLLED],
    Stage.ACTIVE: [
        Stage.CONTACTED, Stage.TOUR_SCHEDULED, Stage.TOUR_COMPLETED, Stage.ENROLLED, Stage.ACTIVE,
    ],
    Stage.GRADUATED: [
        Stage.CONTACTED, Stage.TOUR_SCHEDULED, Stage.TOUR_COMPLETED, Stage.ENROLLED,
        Stage.ACTIVE, Stage.GRADUATED,
    ],
    Stage.DECLINED: [Stage.CONTACTED, Stage.TOUR_SCHEDULED, Stage.TOUR_COMPLETED, Stage.DECLINED],
    Stage.WITHDREW: [
        Stage.CONTACTED, Stage.TOUR_SCHEDULED, Stage.TOUR_COMPLETED, Stage.ENROLLED,
        Stage.ACTIVE, Stage.WITHDREW,
    ],
}


def seed_demo_data(seed=20260919):
    """Create demo families and students. Returns how many children were made."""
    rng = random.Random(seed)
    today = date.today()
    user = User.query.order_by(User.id).first()

    families = []
    for index, (name, first, last, rel, email, phone) in enumerate(FAMILY_SEEDS):
        family = Family(
            family_name=name,
            address_line1=f"{100 + index * 7} Maple Street",
            city="Springfield",
            state="IL",
            postal_code="62704",
            referral_source=REFERRAL_SOURCES[index % len(REFERRAL_SOURCES)],
            preferred_contact_method=rng.choice(["Phone", "Email", "Text"]),
        )
        db.session.add(family)
        db.session.add(
            Guardian(
                family=family,
                first_name=first,
                last_name=last,
                relationship_to_child=rel,
                email=email,
                phone=phone,
                is_primary=True,
            )
        )
        families.append(family)
    db.session.flush()

    plan = [stage for stage, count in STAGE_PLAN for _ in range(count)]
    created = 0

    for index, final_stage in enumerate(plan):
        family = families[index % len(families)]
        surname = family.family_name.replace("The ", "").replace(" Family", "")
        # Older records for the closed stages, recent ones for the live pipeline.
        age_days = rng.randint(400, 900) if final_stage in {Stage.GRADUATED, Stage.WITHDREW} else rng.randint(5, 330)
        inquiry_date = today - timedelta(days=age_days)

        child = create_child(
            family=family,
            first_name=CHILD_NAMES[index % len(CHILD_NAMES)],
            last_name=surname,
            inquiry_date=inquiry_date,
            user=user,
            date_of_birth=today - timedelta(days=rng.randint(200, 1800)),
            desired_start_date=inquiry_date + timedelta(days=rng.randint(20, 90)),
            program=rng.choice(["Full-time", "Part-time (3 days)", "Half-day"]),
        )
        db.session.flush()

        cursor = inquiry_date
        for stage in PATHS[final_stage]:
            cursor = cursor + timedelta(days=rng.randint(2, 30))
            if cursor > today:
                cursor = today
            reason = None
            if stage == Stage.DECLINED:
                reason = rng.choice(DECLINE_REASONS[:6])
            elif stage == Stage.WITHDREW:
                reason = rng.choice(WITHDRAW_REASONS[:5])
            change_stage(child, stage, occurred_on=cursor, reason=reason, user=user)

        log_interaction(
            family=family,
            user=user,
            interaction_type="Phone call",
            occurred_on=inquiry_date,
            summary="Initial inquiry about openings",
            body=f"Asked about availability for {child.first_name}.",
            child=child,
        )
        created += 1

    # A couple of tours on the calendar so the dashboard has something upcoming.
    for offset, child in enumerate(Child.query.filter_by(stage=Stage.TOUR_SCHEDULED).all()):
        child.tour_scheduled_date = today + timedelta(days=3 + offset * 4)

    return created
