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
from app.main import app
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
    """A TestClient wired to `seeded_db` instead of the real database file.

    Note: `TestClient(app)` is created without a `with` block on purpose.
    Entering the context manager would run the app lifespan, which would seed
    the real ledgerlens.db. The routes under test do not need the lifespan.
    """

    def override_get_db():
        yield seeded_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
