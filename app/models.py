"""Database models.

Kept deliberately plain so the same definitions work on the local SQLite
prototype and on a shared Postgres database later -- no SQLite-specific
column types or defaults.
"""

from datetime import date, datetime, timezone

from flask_login import UserMixin
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash

from .constants import (
    CLOSED_STAGES,
    ENROLLED_STAGES,
    STAGE_DATE_FIELDS,
    Stage,
    stage_index,
    stage_label,
)
from .extensions import db


def utcnow():
    """Timezone-aware UTC timestamp, stored naive for cross-database safety."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    """A staff member who signs in. All users have equal permissions."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active_user = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    last_login_at = db.Column(db.DateTime)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self):
        """Flask-Login uses this to block sign-in for deactivated accounts."""
        return self.is_active_user

    @staticmethod
    def normalize_email(email):
        return (email or "").strip().lower()

    def __repr__(self):
        return f"<User {self.email}>"


class Family(db.Model):
    """A household. Holds the address and ties guardians to children."""

    __tablename__ = "families"

    id = db.Column(db.Integer, primary_key=True)
    family_name = db.Column(db.String(160), nullable=False, index=True)
    address_line1 = db.Column(db.String(200))
    address_line2 = db.Column(db.String(200))
    city = db.Column(db.String(120))
    state = db.Column(db.String(60))
    postal_code = db.Column(db.String(20))
    referral_source = db.Column(db.String(80))
    preferred_contact_method = db.Column(db.String(40))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    guardians = db.relationship(
        "Guardian",
        back_populates="family",
        cascade="all, delete-orphan",
        order_by="Guardian.is_primary.desc(), Guardian.id",
    )
    children = db.relationship(
        "Child",
        back_populates="family",
        cascade="all, delete-orphan",
        order_by="Child.first_name",
    )
    interactions = db.relationship(
        "Interaction",
        back_populates="family",
        cascade="all, delete-orphan",
        order_by="Interaction.occurred_on.desc(), Interaction.id.desc()",
    )

    @property
    def primary_guardian(self):
        for guardian in self.guardians:
            if guardian.is_primary:
                return guardian
        return self.guardians[0] if self.guardians else None

    @property
    def address_oneline(self):
        parts = [self.address_line1, self.address_line2]
        city_state = " ".join(p for p in [self.city, self.state] if p)
        if city_state and self.postal_code:
            city_state = f"{city_state} {self.postal_code}"
        elif self.postal_code:
            city_state = self.postal_code
        parts.append(city_state)
        return ", ".join(p.strip() for p in parts if p and p.strip())

    def __repr__(self):
        return f"<Family {self.family_name}>"


class Guardian(db.Model):
    """A parent or guardian contact within a family."""

    __tablename__ = "guardians"

    id = db.Column(db.Integer, primary_key=True)
    family_id = db.Column(
        db.Integer, db.ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True
    )
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    relationship_to_child = db.Column(db.String(40))
    email = db.Column(db.String(255), index=True)
    phone = db.Column(db.String(40))
    is_primary = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    family = db.relationship("Family", back_populates="guardians")

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __repr__(self):
        return f"<Guardian {self.full_name}>"


class Child(db.Model):
    """A prospective or enrolled student, and their position in the funnel."""

    __tablename__ = "children"

    id = db.Column(db.Integer, primary_key=True)
    family_id = db.Column(
        db.Integer, db.ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True
    )
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    date_of_birth = db.Column(db.Date)
    program = db.Column(db.String(80))
    classroom = db.Column(db.String(80))
    desired_start_date = db.Column(db.Date)
    notes = db.Column(db.Text)

    stage = db.Column(db.String(40), nullable=False, default=Stage.INQUIRY, index=True)

    # One date per stage, stamped when the child first reaches that stage.
    inquiry_date = db.Column(db.Date)
    contacted_date = db.Column(db.Date)
    tour_scheduled_date = db.Column(db.Date)
    tour_completed_date = db.Column(db.Date)
    waitlist_date = db.Column(db.Date)
    enrolled_date = db.Column(db.Date)
    active_date = db.Column(db.Date)
    graduated_date = db.Column(db.Date)

    declined_date = db.Column(db.Date)
    decline_reason = db.Column(db.String(120))
    decline_notes = db.Column(db.Text)

    withdrew_date = db.Column(db.Date)
    withdraw_reason = db.Column(db.String(120))
    withdraw_notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    family = db.relationship("Family", back_populates="children")
    stage_events = db.relationship(
        "StageEvent",
        back_populates="child",
        cascade="all, delete-orphan",
        order_by="StageEvent.occurred_on.desc(), StageEvent.id.desc()",
    )
    interactions = db.relationship(
        "Interaction",
        back_populates="child",
        cascade="all, delete-orphan",
        order_by="Interaction.occurred_on.desc(), Interaction.id.desc()",
    )

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def stage_display(self):
        return stage_label(self.stage)

    @property
    def is_closed(self):
        return self.stage in CLOSED_STAGES

    @property
    def is_enrolled(self):
        return self.stage in ENROLLED_STAGES

    @property
    def age_display(self):
        """Age as 'N yr M mo', or months alone under two years old."""
        if not self.date_of_birth:
            return ""
        today = date.today()
        months = (today.year - self.date_of_birth.year) * 12 + (
            today.month - self.date_of_birth.month
        )
        if today.day < self.date_of_birth.day:
            months -= 1
        if months < 0:
            return "Not yet born"
        if months < 24:
            return f"{months} mo"
        return f"{months // 12} yr {months % 12} mo"

    @property
    def stage_date(self):
        """The date stamped for the stage the child is currently in."""
        field = STAGE_DATE_FIELDS.get(self.stage)
        return getattr(self, field, None) if field else None

    @property
    def exit_reason(self):
        if self.stage == Stage.DECLINED:
            return self.decline_reason
        if self.stage == Stage.WITHDREW:
            return self.withdraw_reason
        return None

    @property
    def days_inquiry_to_enrolled(self):
        """Days from first inquiry to enrollment, or None if either is missing."""
        if self.inquiry_date and self.enrolled_date:
            return (self.enrolled_date - self.inquiry_date).days
        return None

    @property
    def toured(self):
        return self.tour_completed_date is not None

    def furthest_pipeline_index(self):
        """How far down the pipeline this child ever got.

        Uses the stamped dates rather than the current stage, so a child who
        toured and then declined still counts as having toured.
        """
        furthest = stage_index(self.stage)
        for stage, field in STAGE_DATE_FIELDS.items():
            if getattr(self, field, None) is not None:
                furthest = max(furthest, stage_index(stage))
        return furthest

    def __repr__(self):
        return f"<Child {self.full_name} ({self.stage})>"


class StageEvent(db.Model):
    """An append-only record of every stage change, and who made it."""

    __tablename__ = "stage_events"

    id = db.Column(db.Integer, primary_key=True)
    child_id = db.Column(
        db.Integer, db.ForeignKey("children.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    from_stage = db.Column(db.String(40))
    to_stage = db.Column(db.String(40), nullable=False)
    occurred_on = db.Column(db.Date, nullable=False, default=date.today)
    reason = db.Column(db.String(120))
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    child = db.relationship("Child", back_populates="stage_events")
    user = db.relationship("User")

    @property
    def from_label(self):
        return stage_label(self.from_stage) if self.from_stage else "New"

    @property
    def to_label(self):
        return stage_label(self.to_stage)

    def __repr__(self):
        return f"<StageEvent {self.from_stage}->{self.to_stage}>"


class Interaction(db.Model):
    """A logged touchpoint: a call, an email, a tour, or a free-form note."""

    __tablename__ = "interactions"

    id = db.Column(db.Integer, primary_key=True)
    family_id = db.Column(
        db.Integer, db.ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True
    )
    child_id = db.Column(
        db.Integer, db.ForeignKey("children.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    interaction_type = db.Column(db.String(40), nullable=False, default="Note")
    occurred_on = db.Column(db.Date, nullable=False, default=date.today)
    summary = db.Column(db.String(200))
    body = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    family = db.relationship("Family", back_populates="interactions")
    child = db.relationship("Child", back_populates="interactions")
    user = db.relationship("User")

    def __repr__(self):
        return f"<Interaction {self.interaction_type} {self.occurred_on}>"


def count_children_by_stage():
    """{stage: count} across all children, for the dashboard and board."""
    rows = db.session.query(Child.stage, func.count(Child.id)).group_by(Child.stage).all()
    return {stage: count for stage, count in rows}
