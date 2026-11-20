"""Application settings.

Values are read from environment variables, and from a local `backend/.env`
file if one exists. Every value has a safe default so the app always starts.

Beginner note: we never hardcode secrets here. `GEMINI_API_KEY` is empty by
default and must come from `.env`, which is git-ignored.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ folder, no matter which directory the server is started from.
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """All configuration for the LedgerLens API."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",  # ignore unrelated variables in .env
    )

    # --- App metadata ------------------------------------------------------
    APP_NAME: str = "LedgerLens API"
    VERSION: str = "0.1.0"

    # --- Database ----------------------------------------------------------
    # Stage 2 will create the SQLite file named here.
    DATABASE_URL: str = "sqlite:///./ledgerlens.db"

    # --- Gemini (Stage 8) --------------------------------------------------
    # Empty by default: the app falls back to rule-based explanations.
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # --- Demo data ---------------------------------------------------------
    # A fixed "today" so every demo run produces the same numbers.
    AS_OF_DATE: str = "2026-11-19"

    # --- CORS --------------------------------------------------------------
    # The Vite dev server runs on 5173 and `vite preview` on 4173.
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ]

    # Dev-only safety net: Vite quietly moves to 5174, 5175, ... when 5173 is
    # already taken. This regex accepts those ports too, so a busy port does
    # not break the browser with a CORS error during development.
    CORS_ORIGIN_REGEX: str = r"^http://(localhost|127\.0\.0\.1):(517\d|417\d)$"


# One shared settings object that the rest of the app imports.
settings = Settings()
