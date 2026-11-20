"""Database connection (SQLAlchemy + SQLite).

Placeholder for Stage 1.

In Stage 2 this file will hold:
  - the SQLAlchemy `engine` created from settings.DATABASE_URL
  - a `SessionLocal` session factory
  - a `Base` declarative base for the models in `app/models`
  - a `get_db()` FastAPI dependency that yields a session and closes it

Nothing is implemented yet on purpose: this stage only sets up the skeleton.
"""
