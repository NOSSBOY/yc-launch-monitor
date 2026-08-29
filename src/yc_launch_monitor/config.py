"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_STATE_DB_PATH = Path("./data/state.db")
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_YC_COMPANIES_URL = "https://www.ycombinator.com/companies"
DEFAULT_YC_SPEEDRUN_URL = "https://speedrun.a16z.com/companies/"
DEFAULT_YC_ALGOLIA_INDEX = "YCCompany_production"
DEFAULT_YC_ALGOLIA_HITS_PER_PAGE = 1000
DEFAULT_X_SEARCH_QUERY = (
    '("got into YC" OR "accepted into YC" OR "accepted to YC" OR "YC S26" OR '
    '"YC W27" OR "YC W26" OR "YC S25" OR "backed by Y Combinator" OR '
    '"Speedrun batch" OR "accepted to Speedrun") -is:retweet'
)
DEFAULT_X_MAX_RESULTS = 100
DEFAULT_LINKEDIN_SEARCH_QUERY = (
    '("got into YC" OR "accepted into YC" OR "accepted to YC" OR "YC S26" OR '
    '"YC W27" OR "YC W26" OR "YC S25" OR "backed by Y Combinator" OR '
    '"Speedrun batch" OR "accepted to Speedrun")'
)
DEFAULT_MONITOR_INTERVAL_SECONDS = 300


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
    x_bearer_token: str | None = None
    x_api_key: str | None = None
    x_api_secret: str | None = None
    x_search_query: str = DEFAULT_X_SEARCH_QUERY
    x_max_results: int = DEFAULT_X_MAX_RESULTS
    linkedin_access_token: str | None = None
    linkedin_client_id: str | None = None
    linkedin_client_secret: str | None = None
    linkedin_search_query: str = DEFAULT_LINKEDIN_SEARCH_QUERY
    monitor_interval_seconds: int = DEFAULT_MONITOR_INTERVAL_SECONDS
    slack_webhook_url: str | None = None


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
        x_bearer_token=_optional_env("X_BEARER_TOKEN"),
        x_api_key=_optional_env("X_API_KEY"),
        x_api_secret=_optional_env("X_API_SECRET"),
        x_search_query=os.getenv("X_SEARCH_QUERY", DEFAULT_X_SEARCH_QUERY),
        x_max_results=int(os.getenv("X_MAX_RESULTS", str(DEFAULT_X_MAX_RESULTS))),
        linkedin_access_token=_optional_env("LINKEDIN_ACCESS_TOKEN"),
        linkedin_client_id=_optional_env("LINKEDIN_CLIENT_ID"),
        linkedin_client_secret=_optional_env("LINKEDIN_CLIENT_SECRET"),
        linkedin_search_query=os.getenv("LINKEDIN_SEARCH_QUERY", DEFAULT_LINKEDIN_SEARCH_QUERY),
        monitor_interval_seconds=int(
            os.getenv("MONITOR_INTERVAL_SECONDS", str(DEFAULT_MONITOR_INTERVAL_SECONDS))
        ),
        slack_webhook_url=_optional_env("SLACK_WEBHOOK_URL"),
    )


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
