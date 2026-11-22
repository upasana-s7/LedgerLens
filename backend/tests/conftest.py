"""Shared test fixtures.

Every test runs against a throw-away in-memory SQLite database, so the real
`backend/ledgerlens.db` file is never read or written. The API's `get_db`
dependency is overridden to hand out that same in-memory session.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  (registers the tables on Base.metadata)
from app.core.database import Base, get_db
from app.core.security import get_current_user
from app.main import app
from app.models.user import User
from app.seed.seed_data import seed_database


@pytest.fixture()
def db_session():
    """A fresh, empty in-memory database for one test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine)
    with maker() as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def seeded_db(db_session):
    """The same in-memory database, already holding the Bloom & Bean data."""
    result = seed_database(db_session)
    assert result["seeded"] is True
    return db_session


@pytest.fixture()
def client(seeded_db):
    """A LOGGED-IN TestClient wired to `seeded_db`.

    Since Stage 11 every financial route requires a session. Most tests are
    about the numbers, not about the login screen, so this fixture bypasses
    the cookie check: `get_current_user` is overridden to return a stand-in
    user. That keeps the existing 185 tests focused on what they actually test.

    Use `public_client` when the test needs the real cookie behaviour (401s,
    register / login / logout).

    Note: `TestClient(app)` is created without a `with` block on purpose.
    Entering the context manager would run the app lifespan, which would seed
    the real ledgerlens.db. The routes under test do not need the lifespan.
    """

    def override_get_db():
        yield seeded_db

    def override_current_user() -> User:
        # Never added to the database: routes only check that someone is
        # signed in, and the financial data is shared anyway.
        return User(id=1, name="Test User", email="test@example.com")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def public_client(seeded_db):
    """A TestClient with the REAL auth dependency - i.e. an empty browser.

    Register / login set a genuine HttpOnly cookie on this client, so a test
    can walk the whole flow. Before the first request the jar is empty, which
    is exactly what the 401 tests need.
    """

    def override_get_db():
        yield seeded_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
