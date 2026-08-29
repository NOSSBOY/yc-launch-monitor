"""Domain models for LinkedIn launch and founder signal monitoring."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

SOURCE_LINKEDIN = "linkedin"
LINKEDIN_FEED_UPDATE_BASE_URL = "https://www.linkedin.com/feed/update/"
LINKEDIN_IN_BASE_URL = "https://www.linkedin.com/in/"


class LinkedInSignalClassification(str, Enum):
    """Classification of a LinkedIn signal relative to official directory confirmation."""

    EARLY_YC_SIGNAL = "EARLY_YC_SIGNAL"
    CONFIRMED_YC = "CONFIRMED_YC"
    SPEEDRUN_SIGNAL = "SPEEDRUN_SIGNAL"
    IRRELEVANT = "IRRELEVANT"


class LinkedInPostStatus(str, Enum):
    """Result of saving a LinkedIn post/signal against persistent storage."""

    NEW = "NEW"
    ALREADY_SEEN = "ALREADY_SEEN"


def build_linkedin_stable_id(post_id: str) -> str:
    """Return a stable identifier for a LinkedIn post."""
    normalized = str(post_id).strip()
    if not normalized:
        raise ValueError("post_id is required to build a stable LinkedIn post id")
    return f"li:{normalized}"


def build_linkedin_post_url(post_id: str) -> str:
    """Construct canonical LinkedIn post URL from post ID or URN."""
    clean_id = str(post_id).strip()
    if clean_id.startswith("http://") or clean_id.startswith("https://"):
        return clean_id
    if clean_id.startswith("urn:li:"):
        return f"{LINKEDIN_FEED_UPDATE_BASE_URL}{clean_id}"
    return f"{LINKEDIN_FEED_UPDATE_BASE_URL}urn:li:activity:{clean_id}"


def build_linkedin_author_url(author_identifier: str) -> str:
    """Construct canonical LinkedIn user profile URL."""
    clean_author = author_identifier.strip().lstrip("@")
    if clean_author.startswith("http://") or clean_author.startswith("https://"):
        return clean_author
    return f"{LINKEDIN_IN_BASE_URL}{clean_author}"


@dataclass(frozen=True, slots=True)
class ParsedLinkedInSignal:
    """Normalized LinkedIn signal model extracted and classified from a post."""

    stable_id: str
    post_id: str
    author_name: str
    post_text: str
    post_url: str
    author_profile_url: str | None = None
    author_urn: str | None = None
    company_name: str | None = None
    batch: str | None = None
    program: str = "YC"
    source: str = SOURCE_LINKEDIN
    classification: LinkedInSignalClassification = LinkedInSignalClassification.IRRELEVANT
    is_early_signal: bool = False
    is_confirmed_yc: bool = False
    is_speedrun_signal: bool = False
    signal_reason: str | None = None
    detected_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class LinkedInSignalRecord:
    """LinkedIn signal persisted in SQLite database."""

    stable_id: str
    post_id: str
    author_name: str
    post_text: str
    post_url: str
    author_profile_url: str | None
    author_urn: str | None
    company_name: str | None
    batch: str | None
    program: str
    source: str
    classification: str
    is_early_signal: bool
    is_confirmed_yc: bool
    is_speedrun_signal: bool
    signal_reason: str | None
    detected_at: datetime
    last_seen_at: datetime
