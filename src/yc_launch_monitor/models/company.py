"""Company domain models for YC Directory monitoring."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


SOURCE_YC_DIRECTORY = "yc_directory"
SOURCE_YC_SPEEDRUN = "yc_speedrun"
YC_PROFILE_BASE_URL = "https://www.ycombinator.com/companies/"
YC_SPEEDRUN_PROFILE_BASE_URL = "https://www.ycombinator.com/speedrun/companies/"


class CompanyStatus(str, Enum):
    """Result of comparing a parsed company against persistent storage."""

    NEW = "NEW"
    ALREADY_SEEN = "ALREADY_SEEN"


def build_stable_id(slug: str) -> str:
    """Return a stable identifier for a YC Directory company."""
    normalized = slug.strip().lower()
    if not normalized:
        raise ValueError("slug is required to build a stable company id")
    return f"yc-dir:{normalized}"


def build_profile_url(slug: str) -> str:
    """Build the canonical YC profile URL from a company slug."""
    return f"{YC_PROFILE_BASE_URL}{slug.strip()}"


def build_speedrun_stable_id(slug: str) -> str:
    """Return a stable identifier for a YC Speedrun company."""
    normalized = slug.strip().lower()
    if not normalized:
        raise ValueError("slug is required to build a stable company id")
    return f"yc-sr:{normalized}"


def build_speedrun_profile_url(slug: str) -> str:
    """Build the canonical Speedrun profile URL from a company slug."""
    return f"{YC_SPEEDRUN_PROFILE_BASE_URL}{slug.strip()}"


@dataclass(frozen=True, slots=True)
class ParsedCompany:
    """Normalized company data extracted from a YC Directory payload."""

    stable_id: str
    name: str
    yc_profile_url: str
    description: str | None
    batch: str | None
    website: str | None
    category: str | None
    source: str = SOURCE_YC_DIRECTORY


@dataclass(frozen=True, slots=True)
class CompanyRecord:
    """Company row persisted in SQLite."""

    stable_id: str
    name: str
    yc_profile_url: str
    description: str | None
    batch: str | None
    website: str | None
    category: str | None
    source: str
    first_detected_at: datetime
    last_seen_at: datetime
