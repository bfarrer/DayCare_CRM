"""Funnel vocabulary for the CRM.

Everything about the student acquisition funnel -- the stage list, the order
stages normally happen in, which date field each stage stamps, and the
dropdown reasons for the two exit stages -- is defined here so the pipeline
can be adjusted without hunting through templates and views.
"""


class Stage:
    INQUIRY = "inquiry"
    CONTACTED = "contacted"
    TOUR_SCHEDULED = "tour_scheduled"
    TOUR_COMPLETED = "tour_completed"
    WAITLIST = "waitlist"
    ENROLLED = "enrolled"
    ACTIVE = "active"
    GRADUATED = "graduated"
    DECLINED = "declined"
    WITHDREW = "withdrew"


# The happy path, in order. Position in this list drives the pipeline board
# column order and the "furthest stage reached" reporting.
PIPELINE_STAGES = [
    Stage.INQUIRY,
    Stage.CONTACTED,
    Stage.TOUR_SCHEDULED,
    Stage.TOUR_COMPLETED,
    Stage.WAITLIST,
    Stage.ENROLLED,
    Stage.ACTIVE,
    Stage.GRADUATED,
]

# Stages a family can land in instead of continuing down the pipeline.
EXIT_STAGES = [Stage.DECLINED, Stage.WITHDREW]

# Side branches, not required steps. Step-conversion reporting skips these so
# the stage after them is still compared against the last required stage --
# otherwise "enrolled as a % of waitlist" reads as a nonsense number over 100%.
OPTIONAL_STAGES = {Stage.WAITLIST}

ALL_STAGES = PIPELINE_STAGES + EXIT_STAGES

# Stages where the student is no longer moving through the funnel.
CLOSED_STAGES = {Stage.GRADUATED, Stage.DECLINED, Stage.WITHDREW}

# Stages where the student is in our care right now.
ENROLLED_STAGES = {Stage.ENROLLED, Stage.ACTIVE}

STAGE_LABELS = {
    Stage.INQUIRY: "Inquiry",
    Stage.CONTACTED: "Contacted",
    Stage.TOUR_SCHEDULED: "Tour Scheduled",
    Stage.TOUR_COMPLETED: "Tour Completed",
    Stage.WAITLIST: "Waitlist",
    Stage.ENROLLED: "Enrolled",
    Stage.ACTIVE: "Active",
    Stage.GRADUATED: "Graduated",
    Stage.DECLINED: "Declined",
    Stage.WITHDREW: "Withdrew",
}

STAGE_DESCRIPTIONS = {
    Stage.INQUIRY: "Family reached out or we captured their interest.",
    Stage.CONTACTED: "We have responded and made contact.",
    Stage.TOUR_SCHEDULED: "A tour is on the calendar.",
    Stage.TOUR_COMPLETED: "The family has visited.",
    Stage.WAITLIST: "Family wants a spot; none available yet.",
    Stage.ENROLLED: "Paperwork done, start date set, not yet attending.",
    Stage.ACTIVE: "Child is attending.",
    Stage.GRADUATED: "Child completed the program and moved on.",
    Stage.DECLINED: "Family chose not to enroll.",
    Stage.WITHDREW: "Family left after enrolling.",
}

# Each stage stamps a date on the Child record so the funnel history survives
# even after the child moves on to a later stage.
STAGE_DATE_FIELDS = {
    Stage.INQUIRY: "inquiry_date",
    Stage.CONTACTED: "contacted_date",
    Stage.TOUR_SCHEDULED: "tour_scheduled_date",
    Stage.TOUR_COMPLETED: "tour_completed_date",
    Stage.WAITLIST: "waitlist_date",
    Stage.ENROLLED: "enrolled_date",
    Stage.ACTIVE: "active_date",
    Stage.GRADUATED: "graduated_date",
    Stage.DECLINED: "declined_date",
    Stage.WITHDREW: "withdrew_date",
}

DECLINE_REASONS = [
    "Cost / tuition",
    "No availability at desired time",
    "Waitlist too long",
    "Chose another provider",
    "Location / commute",
    "Schedule or hours mismatch",
    "Moved out of area",
    "Care no longer needed",
    "Family stopped responding",
    "Other",
]

WITHDRAW_REASONS = [
    "Moved out of area",
    "Cost / tuition",
    "Schedule change",
    "Parent work change / care no longer needed",
    "Dissatisfied with care",
    "Switched to another provider",
    "Started public pre-K or school",
    "Other",
]

# How the family found us. Feeds the "where do enrollments come from" report.
REFERRAL_SOURCES = [
    "Word of mouth",
    "Google / web search",
    "Facebook",
    "Instagram",
    "Drive-by / signage",
    "Current family referral",
    "Former family",
    "Church",
    "Community event",
    "Other",
]

GUARDIAN_RELATIONSHIPS = [
    "Mother",
    "Father",
    "Grandmother",
    "Grandfather",
    "Stepmother",
    "Stepfather",
    "Guardian",
    "Other",
]

CONTACT_METHODS = ["Phone", "Email", "Text", "In person", "Other"]

INTERACTION_TYPES = [
    "Phone call",
    "Email",
    "Text message",
    "Tour",
    "In-person visit",
    "Note",
    "Other",
]


def stage_label(stage):
    """Human-readable label for a stage key, falling back to the raw key."""
    return STAGE_LABELS.get(stage, stage or "Unknown")


def stage_index(stage):
    """Position in the pipeline, or -1 for exit stages and unknown values."""
    try:
        return PIPELINE_STAGES.index(stage)
    except ValueError:
        return -1


def reasons_for_stage(stage):
    """Reason dropdown options for the stages that require a reason."""
    if stage == Stage.DECLINED:
        return DECLINE_REASONS
    if stage == Stage.WITHDREW:
        return WITHDRAW_REASONS
    return []
