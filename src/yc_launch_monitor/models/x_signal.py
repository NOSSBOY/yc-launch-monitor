"""Domain models for X/Twitter launch and founder signal monitoring."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

SOURCE_X = "x"
X_POST_BASE_URL = "https://x.com/"


class SignalClassification(str, Enum):
    """Classification of an X signal relative to official directory confirmation."""

    EARLY_YC_SIGNAL = "EARLY_YC_SIGNAL"
    CONFIRMED_YC_SIGNAL = "CONFIRMED_YC_SIGNAL"
    IRRELEVANT = "IRRELEVANT"


class XPostStatus(str, Enum):
    """Result of saving an X post/signal against persistent storage."""

    NEW = "NEW"
    ALREADY_SEEN = "ALREADY_SEEN"


def build_x_stable_id(post_id: str) -> str:
    """Return a stable identifier for an X post."""
    normalized = str(post_id).strip()
    if not normalized:
        raise ValueError("post_id is required to build a stable X post id")
    return f"x:{normalized}"


def build_x_post_url(username: str, post_id: str) -> str:
    """Construct canonical X post URL."""
    clean_user = username.strip().lstrip("@")
    clean_id = str(post_id).strip()
    return f"{X_POST_BASE_URL}{clean_user}/status/{clean_id}"


def build_x_author_url(username: str) -> str:
    """Construct canonical X user profile URL."""
    clean_user = username.strip().lstrip("@")
    return f"{X_POST_BASE_URL}{clean_user}"


@dataclass(frozen=True, slots=True)
class ParsedXSignal:
    """Normalized X signal model extracted and classified from a post."""

    stable_id: str
    post_id: str
    author_username: str
    post_text: str
    post_url: str
    author_name: str | None = None
    author_url: str | None = None
    company_name: str | None = None
    batch: str | None = None
    program: str = "YC"
    source: str = SOURCE_X
    is_early_signal: bool = False
    is_confirmed_yc: bool = False
    signal_reason: str | None = None
    detected_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class XSignalRecord:
    """X signal persisted in SQLite database."""

    stable_id: str
    post_id: str
    author_username: str
    post_text: str
    post_url: str
    author_name: str | None
    author_url: str | None
    company_name: str | None
    batch: str | None
    program: str
    source: str
    is_early_signal: bool
    is_confirmed_yc: bool
    signal_reason: str | None
    detected_at: datetime
    last_seen_at: datetime
