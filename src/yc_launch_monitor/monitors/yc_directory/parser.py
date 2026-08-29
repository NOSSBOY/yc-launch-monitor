"""Parse YC Directory company payloads into normalized models."""

from __future__ import annotations

import logging
from typing import Any

from yc_launch_monitor.models.company import (
    SOURCE_YC_DIRECTORY,
    ParsedCompany,
    build_profile_url,
    build_stable_id,
)

logger = logging.getLogger(__name__)


class YCDirectoryParseError(ValueError):
    """Raised when a YC Directory payload cannot be parsed."""


def parse_algolia_hit(hit: dict[str, Any]) -> ParsedCompany:
    """Parse one Algolia company hit into a normalized company model."""
    slug = _extract_slug(hit)
    name = _extract_name(hit, slug)
    description = _extract_description(hit)
    batch = _extract_optional_str(hit, "batch")
    website = _extract_optional_str(hit, "website")
    category = _extract_category(hit)

    return ParsedCompany(
        stable_id=build_stable_id(slug),
        name=name,
        yc_profile_url=build_profile_url(slug),
        description=description,
        batch=batch,
        website=website,
        category=category,
        source=SOURCE_YC_DIRECTORY,
    )


def parse_algolia_response(payload: dict[str, Any]) -> list[ParsedCompany]:
    """Parse all company hits from an Algolia query response."""
    hits = payload.get("hits")
    if not isinstance(hits, list):
        raise YCDirectoryParseError("Algolia response is missing a hits list")

    companies: list[ParsedCompany] = []
    for hit in hits:
        if not isinstance(hit, dict):
            logger.warning("Skipping non-object Algolia hit: %r", hit)
            continue
        companies.append(parse_algolia_hit(hit))
    return companies


def _extract_slug(hit: dict[str, Any]) -> str:
    slug = _extract_optional_str(hit, "slug")
    if slug:
        return slug

    object_id = _extract_optional_str(hit, "objectID")
    if object_id:
        return object_id

    profile_url = _extract_optional_str(hit, "url") or _extract_optional_str(hit, "company_url")
    if profile_url and "/companies/" in profile_url:
        return profile_url.rstrip("/").split("/companies/")[-1]

    raise YCDirectoryParseError("Algolia hit is missing slug/objectID")


def _extract_name(hit: dict[str, Any], slug: str) -> str:
    name = _extract_optional_str(hit, "name")
    if name:
        return name
    raise YCDirectoryParseError(f"Algolia hit for slug '{slug}' is missing name")


def _extract_description(hit: dict[str, Any]) -> str | None:
    for key in ("one_liner", "oneLiner", "description", "long_description", "longDescription"):
        value = _extract_optional_str(hit, key)
        if value:
            return value
    return None


def _extract_category(hit: dict[str, Any]) -> str | None:
    industries = hit.get("industries")
    if isinstance(industries, list):
        cleaned = [str(item).strip() for item in industries if str(item).strip()]
        if cleaned:
            return ", ".join(cleaned)

    tags = hit.get("tags")
    if isinstance(tags, list):
        cleaned = [str(item).strip() for item in tags if str(item).strip()]
        if cleaned:
            return ", ".join(cleaned)

    for key in ("industry", "category"):
        value = _extract_optional_str(hit, key)
        if value:
            return value

    return None


def _extract_optional_str(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    stripped = value.strip()
    return stripped or None
