import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db as _db
from app.models import User


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def user(db):
    user = User(email="staff@example.com", name="Sam Staff")
    user.set_password("correct-horse-battery")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(client, user):
    client.post(
        "/login",
        data={"email": "staff@example.com", "password": "correct-horse-battery"},
        follow_redirects=True,
    )
    return client
