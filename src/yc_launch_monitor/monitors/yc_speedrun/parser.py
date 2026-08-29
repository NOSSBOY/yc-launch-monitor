"""Parse YC Speedrun company payloads into normalized models."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from yc_launch_monitor.models.company import (
    SOURCE_YC_SPEEDRUN,
    ParsedCompany,
    build_speedrun_profile_url,
    build_speedrun_stable_id,
)

logger = logging.getLogger(__name__)


class YCSpeedrunParseError(ValueError):
    """Raised when a YC Speedrun payload cannot be parsed."""


def parse_speedrun_item(hit: dict[str, Any]) -> ParsedCompany:
    """Parse one Speedrun company item into a normalized company model."""
    slug = _extract_slug(hit)
    name = _extract_name(hit, slug)
    description = _extract_description(hit)
    batch = _extract_optional_str(hit, "batch") or _extract_optional_str(hit, "cohort") or _extract_optional_str(hit, "program") or "Speedrun"
    website = _extract_website(hit)
    category = _extract_category(hit)
    profile_url = _extract_profile_url(hit, slug)

    return ParsedCompany(
        stable_id=build_speedrun_stable_id(slug),
        name=name,
        yc_profile_url=profile_url,
        description=description,
        batch=batch,
        website=website,
        category=category,
        source=SOURCE_YC_SPEEDRUN,
    )


def parse_speedrun_payload(payload: dict[str, Any] | list[Any]) -> list[ParsedCompany]:
    """Parse all company records from a Speedrun API or JSON payload."""
    items: list[Any]
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = _extract_items_from_dict(payload)
    else:
        raise YCSpeedrunParseError("Speedrun payload must be a dict or list")

    companies: list[ParsedCompany] = []
    for item in items:
        if not isinstance(item, dict):
            logger.warning("Skipping non-object Speedrun item: %r", item)
            continue
        companies.append(parse_speedrun_item(item))
    return companies


def parse_speedrun_html(html: str) -> list[ParsedCompany]:
    """Extract and parse Speedrun companies embedded in HTML pages."""
    # Look for __NEXT_DATA__
    next_data_match = re.search(
        r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>',
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if next_data_match:
        try:
            next_json = json.loads(next_data_match.group(1))
            items = _extract_items_from_dict(next_json)
            if items:
                return [parse_speedrun_item(item) for item in items if isinstance(item, dict)]
        except json.JSONDecodeError as exc:
            raise YCSpeedrunParseError(f"Invalid __NEXT_DATA__ JSON in HTML: {exc}") from exc

    # Look for generic JSON script blocks
    script_matches = re.findall(
        r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>',
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    for script_content in script_matches:
        try:
            script_json = json.loads(script_content.strip())
            if isinstance(script_json, (dict, list)):
                return parse_speedrun_payload(script_json)
        except json.JSONDecodeError:
            continue

    raise YCSpeedrunParseError("Could not find structured company data in Speedrun HTML")


def _extract_slug(hit: dict[str, Any]) -> str:
    for key in ("slug", "objectID", "id", "company_slug"):
        slug = _extract_optional_str(hit, key)
        if slug:
            return slug

    profile_url = _extract_optional_str(hit, "url") or _extract_optional_str(hit, "profile_url") or _extract_optional_str(hit, "company_url")
    if profile_url:
        for marker in ("/speedrun/companies/", "/companies/", "/speedrun/"):
            if marker in profile_url:
                slug_part = profile_url.rstrip("/").split(marker)[-1]
                if slug_part:
                    return slug_part

    raise YCSpeedrunParseError("Speedrun company is missing slug/id")


def _extract_name(hit: dict[str, Any], slug: str) -> str:
    for key in ("name", "company_name", "title"):
        name = _extract_optional_str(hit, key)
        if name:
            return name
    raise YCSpeedrunParseError(f"Speedrun company for slug '{slug}' is missing name")


def _extract_description(hit: dict[str, Any]) -> str | None:
    for key in (
        "one_liner",
        "oneLiner",
        "description",
        "summary",
        "pitch",
        "short_description",
        "long_description",
        "longDescription",
    ):
        value = _extract_optional_str(hit, key)
        if value:
            return value
    return None


def _extract_website(hit: dict[str, Any]) -> str | None:
    for key in ("website", "website_url", "homepage", "link"):
        value = _extract_optional_str(hit, key)
        if value:
            return value
    return None


def _extract_profile_url(hit: dict[str, Any], slug: str) -> str:
    for key in ("profile_url", "yc_profile_url", "speedrun_url"):
        url = _extract_optional_str(hit, key)
        if url:
            return url
    return build_speedrun_profile_url(slug)


def _extract_category(hit: dict[str, Any]) -> str | None:
    for key in ("industries", "tags", "categories"):
        val_list = hit.get(key)
        if isinstance(val_list, list):
            cleaned = [str(item).strip() for item in val_list if str(item).strip()]
            if cleaned:
                return ", ".join(cleaned)

    for key in ("industry", "category", "vertical", "sector"):
        value = _extract_optional_str(hit, key)
        if value:
            return value

    return None


def _extract_items_from_dict(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("companies", "hits", "items", "results", "data", "speedrun_companies"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            for subkey in ("results", "items", "companies", "data"):
                subval = value.get(subkey)
                if isinstance(subval, list):
                    return [item for item in subval if isinstance(item, dict)]

    props = payload.get("props", {})
    if isinstance(props, dict):
        page_props = props.get("pageProps", {})
        if isinstance(page_props, dict):
            for key in ("companies", "hits", "items", "results", "data"):
                value = page_props.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
                if isinstance(value, dict):
                    for subkey in ("results", "items", "companies", "data"):
                        subval = value.get(subkey)
                        if isinstance(subval, list):
                            return [item for item in subval if isinstance(item, dict)]

    return []


def _extract_optional_str(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    stripped = value.strip()
    return stripped or None
