"""Database connection (SQLAlchemy 2.x + SQLite).

This module owns three things:
  1. `engine`        - the connection to the SQLite file
  2. `SessionLocal`  - a factory that creates short-lived database sessions
  3. `Base`          - the parent class every model inherits from

FastAPI routes get a session through the `get_db()` dependency, which makes
sure the session is always closed afterwards.
"""

import warnings

from sqlalchemy import create_engine
from sqlalchemy.exc import SAWarning
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

# ---------------------------------------------------------------------------
# Money is stored as Numeric(14, 2) and handled as Python `Decimal`.
# SQLite has no real decimal type, so SQLAlchemy converts on the way in and
# out and prints a warning about possible rounding. For our amounts (rupees,
# 2 decimals, far below the float precision limit) the conversion is exact,
# and using Decimal still avoids binary float drift inside Python.
# We silence only that one warning so the log stays readable.
# ---------------------------------------------------------------------------
warnings.filterwarnings(
    "ignore",
    message=r".*does \*not\* support Decimal objects natively.*",
    category=SAWarning,
)

engine = create_engine(
    settings.DATABASE_URL,
    # FastAPI may handle a request on a different thread than the one that
    # opened the connection, which SQLite blocks by default.
    connect_args={"check_same_thread": False},
)

# `autocommit=False` + `autoflush=False` keeps transactions explicit and easy
# to reason about for beginners.
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    """Parent class for all ORM models (tables)."""


def get_db():
    """FastAPI dependency: yield a session, always close it afterwards.

    Used in routes like:

        def list_items(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create every table that does not exist yet.

    Importing `app.models` registers all model classes on `Base.metadata`,
    which is what `create_all` needs to know about them. This is safe to call
    repeatedly: existing tables are left untouched.
    """
    # Import for the side effect of registering the models. The noqa comment
    # tells linters this import is intentional even though it is "unused".
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
