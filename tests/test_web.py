"""Routes: authentication, the main pages, and creating records through forms."""

from datetime import date

import pytest

from app.constants import Stage
from app.models import Child, Family, Guardian, User

PROTECTED_PAGES = [
    "/",
    "/students/",
    "/students/board",
    "/students/new",
    "/families/",
    "/families/new",
    "/reports/",
    "/team/",
    "/account",
]


@pytest.mark.parametrize("path", PROTECTED_PAGES)
def test_pages_require_sign_in(client, path):
    response = client.get(path)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_sign_in_with_the_right_password(client, user):
    response = client.post(
        "/login",
        data={"email": "staff@example.com", "password": "correct-horse-battery"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Enrollment dashboard" in response.data


def test_sign_in_is_case_insensitive_on_email(client, user):
    response = client.post(
        "/login",
        data={"email": "  STAFF@Example.com ", "password": "correct-horse-battery"},
        follow_redirects=True,
    )
    assert b"Enrollment dashboard" in response.data


def test_wrong_password_is_rejected(client, user):
    response = client.post(
        "/login",
        data={"email": "staff@example.com", "password": "wrong"},
        follow_redirects=True,
    )
    assert b"Email or password is incorrect" in response.data


def test_a_deactivated_account_cannot_sign_in(client, db, user):
    user.is_active_user = False
    db.session.commit()

    response = client.post(
        "/login",
        data={"email": "staff@example.com", "password": "correct-horse-battery"},
        follow_redirects=True,
    )
    assert b"deactivated" in response.data


def test_login_redirect_ignores_an_offsite_next(client, user):
    response = client.post(
        "/login?next=https://evil.example.com/steal",
        data={"email": "staff@example.com", "password": "correct-horse-battery"},
    )
    assert response.headers["Location"] in ("/", "http://localhost/")


def test_creating_a_family_with_a_first_contact(auth_client, db):
    response = auth_client.post(
        "/families/new",
        data={
            "family_name": "The Okafor Family",
            "city": "Springfield",
            "referral_source": "Word of mouth",
            "guardian_first_name": "Ada",
            "guardian_last_name": "Okafor",
            "guardian_email": "ada@example.com",
            "guardian_phone": "555-0101",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    family = Family.query.filter_by(family_name="The Okafor Family").one()
    assert family.primary_guardian.full_name == "Ada Okafor"
    assert family.primary_guardian.is_primary is True


def test_a_family_needs_a_name(auth_client, db):
    auth_client.post("/families/new", data={"family_name": "   "})
    assert Family.query.count() == 0


def test_adding_a_student_puts_them_in_the_funnel(auth_client, db):
    family = Family(family_name="The Test Family")
    db.session.add(family)
    db.session.commit()

    auth_client.post(
        "/students/new",
        data={
            "first_name": "Mei",
            "last_name": "Test",
            "family_id": family.id,
            "inquiry_date": "2026-02-01",
        },
        follow_redirects=True,
    )

    child = Child.query.one()
    assert child.stage == Stage.INQUIRY
    assert child.inquiry_date == date(2026, 2, 1)


def test_moving_a_student_to_declined_through_the_form(auth_client, db):
    family = Family(family_name="The Test Family")
    db.session.add(family)
    db.session.commit()
    auth_client.post(
        "/students/new",
        data={"first_name": "Mei", "last_name": "Test", "family_id": family.id},
        follow_redirects=True,
    )
    child = Child.query.one()

    auth_client.post(
        f"/students/{child.id}/stage",
        data={
            "stage": Stage.DECLINED,
            "occurred_on": "2026-03-15",
            "reason": "Cost / tuition",
            "note": "Chose a cheaper option",
        },
        follow_redirects=True,
    )

    assert child.stage == Stage.DECLINED
    assert child.declined_date == date(2026, 3, 15)
    assert child.decline_reason == "Cost / tuition"


def test_declining_without_a_reason_is_refused_by_the_form(auth_client, db):
    family = Family(family_name="The Test Family")
    db.session.add(family)
    db.session.commit()
    auth_client.post(
        "/students/new",
        data={"first_name": "Mei", "last_name": "Test", "family_id": family.id},
        follow_redirects=True,
    )
    child = Child.query.one()

    response = auth_client.post(
        f"/students/{child.id}/stage",
        data={"stage": Stage.DECLINED, "occurred_on": "2026-03-15"},
        follow_redirects=True,
    )

    assert b"reason is required" in response.data
    assert child.stage == Stage.INQUIRY


def test_the_pipeline_board_and_reports_render(auth_client, db):
    family = Family(family_name="The Test Family")
    db.session.add(family)
    db.session.commit()
    auth_client.post(
        "/students/new",
        data={"first_name": "Mei", "last_name": "Test", "family_id": family.id},
        follow_redirects=True,
    )

    assert auth_client.get("/students/board").status_code == 200
    assert auth_client.get("/reports/").status_code == 200
    assert auth_client.get("/students/?stage=inquiry").status_code == 200


def test_csv_export_includes_the_funnel_columns(auth_client, db):
    family = Family(family_name="The Test Family")
    db.session.add(family)
    db.session.commit()
    auth_client.post(
        "/students/new",
        data={"first_name": "Mei", "last_name": "Test", "family_id": family.id},
        follow_redirects=True,
    )

    response = auth_client.get("/students/export.csv")
    assert response.status_code == 200
    body = response.data.decode()
    assert "Decline reason" in body
    assert "Withdraw reason" in body
    assert "Mei" in body


def test_only_one_guardian_stays_primary(auth_client, db):
    family = Family(family_name="The Test Family")
    db.session.add(family)
    db.session.commit()

    for first in ("Ada", "Ben"):
        auth_client.post(
            f"/families/{family.id}/guardians",
            data={"first_name": first, "last_name": "Test", "is_primary": "1"},
            follow_redirects=True,
        )

    primaries = Guardian.query.filter_by(family_id=family.id, is_primary=True).all()
    assert len(primaries) == 1
    assert primaries[0].first_name == "Ben"


def test_adding_a_teammate(auth_client, db):
    auth_client.post(
        "/team/new",
        data={"name": "Pat Helper", "email": "Pat@Example.com", "password": "another-long-one"},
        follow_redirects=True,
    )

    created = User.query.filter_by(email="pat@example.com").one()
    assert created.check_password("another-long-one")


def test_a_short_password_is_refused(auth_client, db):
    auth_client.post(
        "/team/new",
        data={"name": "Pat Helper", "email": "pat@example.com", "password": "short"},
        follow_redirects=True,
    )
    assert User.query.filter_by(email="pat@example.com").first() is None


def test_you_cannot_deactivate_yourself(auth_client, db, user):
    response = auth_client.post(f"/team/{user.id}/toggle", follow_redirects=True)
    assert b"cannot deactivate your own account" in response.data
    assert user.is_active_user is True


def test_deleting_a_family_removes_its_children(auth_client, db):
    family = Family(family_name="The Test Family")
    db.session.add(family)
    db.session.commit()
    auth_client.post(
        "/students/new",
        data={"first_name": "Mei", "last_name": "Test", "family_id": family.id},
        follow_redirects=True,
    )
    assert Child.query.count() == 1

    auth_client.post(f"/families/{family.id}/delete", follow_redirects=True)

    assert Family.query.count() == 0
    assert Child.query.count() == 0
