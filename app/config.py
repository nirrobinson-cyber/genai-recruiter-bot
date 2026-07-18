"""Typed application settings loaded from .env (spec N-2: zero magic constants).

Usage:
    from app.config import get_settings
    settings = get_settings()
"""

import logging
from datetime import datetime
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Every field maps to an .env variable."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- OpenAI ---
    openai_api_key: str = ""

    # --- Models ---
    main_agent_model: str = "gpt-4o-mini"
    advisor_model: str = "gpt-4o-mini"
    exit_advisor_finetuned_model: str = ""  # empty => prompted fallback (Strategy, spec §5.2)
    embedding_model: str = "text-embedding-3-small"

    # --- Behavior ---
    decision_temperature: float = 0.0
    message_temperature: float = 0.7
    max_advisor_consults: int = 3  # guard R-1
    retrieval_top_k: int = 4

    # --- Paths ---
    sqlite_db_path: str = "data/tech.db"
    chroma_persist_dir: str = "data/chroma"
    chroma_collection: str = "job_description"
    job_description_pdf: str = "data/raw/Python_Developer_Job_Description.pdf"
    conversations_json: str = "data/raw/sms_conversations.json"

    # --- Demo mode (risk #4) ---
    demo_now_override: str = ""

    # --- Logging ---
    log_level: str = "INFO"

    def now(self) -> datetime:
        """'Now' for relative-date resolution (spec §7.3, A-5).

        Returns the demo override when set (DB is seeded for 2024), else wall clock.
        """
        if self.demo_now_override:
            return datetime.fromisoformat(self.demo_now_override.replace("Z", "+00:00"))
        return datetime.now().astimezone()


@lru_cache
def get_settings() -> Settings:
    """Singleton settings accessor."""
    return Settings()


def setup_logging(level: str | None = None) -> None:
    """Configure structured-ish logging for every advisor call (spec N-4)."""
    logging.basicConfig(
        level=(level or get_settings().log_level).upper(),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
