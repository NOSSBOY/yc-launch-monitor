"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_STATE_DB_PATH = Path("./data/state.db")
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_YC_COMPANIES_URL = "https://www.ycombinator.com/companies"
DEFAULT_YC_SPEEDRUN_URL = "https://www.ycombinator.com/speedrun"
DEFAULT_YC_ALGOLIA_INDEX = "YCCompany_production"
DEFAULT_YC_ALGOLIA_HITS_PER_PAGE = 1000


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings for the YC Launch Monitor."""

    state_db_path: Path = DEFAULT_STATE_DB_PATH
    log_level: str = DEFAULT_LOG_LEVEL
    yc_companies_url: str = DEFAULT_YC_COMPANIES_URL
    yc_algolia_app_id: str | None = None
    yc_algolia_api_key: str | None = None
    yc_algolia_index: str = DEFAULT_YC_ALGOLIA_INDEX
    yc_algolia_hits_per_page: int = DEFAULT_YC_ALGOLIA_HITS_PER_PAGE
    yc_speedrun_url: str = DEFAULT_YC_SPEEDRUN_URL


def load_settings() -> Settings:
    """Load settings from `.env` (if present) and environment variables."""
    load_dotenv()

    state_db_path = Path(os.getenv("STATE_DB_PATH", str(DEFAULT_STATE_DB_PATH)))
    log_level = os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()

    return Settings(
        state_db_path=state_db_path,
        log_level=log_level,
        yc_companies_url=os.getenv("YC_COMPANIES_URL", DEFAULT_YC_COMPANIES_URL),
        yc_speedrun_url=os.getenv("YC_SPEEDRUN_URL", DEFAULT_YC_SPEEDRUN_URL),
        yc_algolia_app_id=_optional_env("YC_ALGOLIA_APP_ID"),
        yc_algolia_api_key=_optional_env("YC_ALGOLIA_API_KEY"),
        yc_algolia_index=os.getenv("YC_ALGOLIA_INDEX", DEFAULT_YC_ALGOLIA_INDEX),
        yc_algolia_hits_per_page=int(
            os.getenv("YC_ALGOLIA_HITS_PER_PAGE", str(DEFAULT_YC_ALGOLIA_HITS_PER_PAGE))
        ),
    )


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
