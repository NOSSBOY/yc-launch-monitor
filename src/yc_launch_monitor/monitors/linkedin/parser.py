"""Parse LinkedIn post payloads into normalized domain signals."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from yc_launch_monitor.models.linkedin_signal import (
    SOURCE_LINKEDIN,
    LinkedInSignalClassification,
    ParsedLinkedInSignal,
    build_linkedin_author_url,
    build_linkedin_post_url,
    build_linkedin_stable_id,
)
from yc_launch_monitor.monitors.linkedin.detector import (
    LinkedInDetectionResult,
    LinkedInSignalDetector,
)

logger = logging.getLogger(__name__)


class LinkedInParseError(ValueError):
    """Raised when a LinkedIn post payload cannot be parsed."""


def parse_linkedin_post(
    post: dict[str, Any],
    detector: LinkedInSignalDetector | None = None,
    require_relevant: bool = True,
) -> ParsedLinkedInSignal | None:
    """
    Parse a raw LinkedIn post dictionary into a normalized ParsedLinkedInSignal.

    If require_relevant is True and the post has no YC/Speedrun signal, returns None.
    """
    post_id = _extract_post_id(post)
    text = _extract_text(post)
    author_name = _extract_author_name(post)
    author_urn = _extract_author_urn(post)
    author_profile_url = _extract_author_url(post, author_urn or author_name)
    post_url = _extract_post_url(post, post_id)
    author_company = _extract_author_company(post)
    detected_at = _extract_timestamp(post)

    detector = detector or LinkedInSignalDetector()
    detection: LinkedInDetectionResult = detector.detect(
        text=text,
        author_name=author_name,
        author_company=author_company,
    )

    if require_relevant and not detection.is_relevant:
        logger.debug("Skipping non-relevant LinkedIn post #%s", post_id)
        return None

    return ParsedLinkedInSignal(
        stable_id=build_linkedin_stable_id(post_id),
        post_id=post_id,
        author_name=author_name,
        author_profile_url=author_profile_url,
        author_urn=author_urn,
        company_name=detection.company_name,
        batch=detection.batch,
        program=detection.program,
        post_text=text,
        post_url=post_url,
        source=SOURCE_LINKEDIN,
        classification=LinkedInSignalClassification.IRRELEVANT,  # Evaluated by Matcher/Monitor against SQLite
        is_early_signal=False,  # Evaluated by Matcher/Monitor
        is_confirmed_yc=False,  # Evaluated by Matcher/Monitor
        is_speedrun_signal=detection.program == "Speedrun",
        signal_reason=detection.signal_reason,
        detected_at=detected_at,
    )


def parse_linkedin_payload(
    payload: dict[str, Any] | list[Any],
    detector: LinkedInSignalDetector | None = None,
    require_relevant: bool = True,
) -> list[ParsedLinkedInSignal]:
    """Parse a list or dictionary payload of LinkedIn posts into normalized signals."""
    items: list[Any]
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = (
            payload.get("elements")
            or payload.get("posts")
            or payload.get("data")
            or payload.get("items")
            or []
        )
    else:
        raise LinkedInParseError("LinkedIn payload must be a dict or list")

    signals: list[ParsedLinkedInSignal] = []
    detector = detector or LinkedInSignalDetector()

    for item in items:
        if not isinstance(item, dict):
            logger.warning("Skipping non-object LinkedIn item: %r", item)
            continue
        try:
            signal = parse_linkedin_post(item, detector=detector, require_relevant=require_relevant)
            if signal is not None:
                signals.append(signal)
        except LinkedInParseError as exc:
            logger.warning("Failed to parse LinkedIn item: %s", exc)
            continue

    return signals


def _extract_post_id(post: dict[str, Any]) -> str:
    for key in ("id", "post_id", "urn", "activity_urn", "id_str"):
        val = post.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    raise LinkedInParseError("LinkedIn post is missing id")


def _extract_text(post: dict[str, Any]) -> str:
    for key in ("text", "commentary", "content", "post_text", "body", "description"):
        val = post.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()

    # Nested LinkedIn REST commentary structure
    commentary = post.get("commentary", {})
    if isinstance(commentary, dict):
        val = commentary.get("text")
        if val is not None and str(val).strip():
            return str(val).strip()

    raise LinkedInParseError("LinkedIn post is missing text/content")


def _extract_author_name(post: dict[str, Any]) -> str:
    for key in ("author_name", "name", "display_name", "author"):
        val = post.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()

    author_obj = post.get("author") or post.get("actor") or post.get("user")
    if isinstance(author_obj, dict):
        for key in ("name", "display_name", "title", "formatted_name"):
            val = author_obj.get(key)
            if val is not None and str(val).strip():
                return str(val).strip()

    return "Unknown Author"


def _extract_author_urn(post: dict[str, Any]) -> str | None:
    for key in ("author_urn", "actor_urn", "urn"):
        val = post.get(key)
        if isinstance(val, str) and val.strip().startswith("urn:li:"):
            return val.strip()

    author_obj = post.get("author") or post.get("actor")
    if isinstance(author_obj, dict):
        val = author_obj.get("urn")
        if isinstance(val, str) and val.strip():
            return val.strip()

    return None


def _extract_author_url(post: dict[str, Any], author_identifier: str) -> str:
    for key in ("author_profile_url", "author_url", "profile_url"):
        val = post.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()

    author_obj = post.get("author") or post.get("actor")
    if isinstance(author_obj, dict):
        for key in ("profile_url", "url"):
            val = author_obj.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()

    return build_linkedin_author_url(author_identifier)


def _extract_post_url(post: dict[str, Any], post_id: str) -> str:
    for key in ("post_url", "url", "share_url"):
        val = post.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()

    return build_linkedin_post_url(post_id)


def _extract_author_company(post: dict[str, Any]) -> str | None:
    for key in ("author_company", "company", "company_name", "organization"):
        val = post.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()

    author_obj = post.get("author") or post.get("actor")
    if isinstance(author_obj, dict):
        for key in ("company", "headline", "organization"):
            val = author_obj.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()

    return None


def _extract_timestamp(post: dict[str, Any]) -> datetime | None:
    val = post.get("created_at") or post.get("detected_at") or post.get("published_at")
    if not val:
        created_obj = post.get("created")
        if isinstance(created_obj, dict):
            val = created_obj.get("time")

    if not val:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, (int, float)):
        # Epoch timestamp (ms or s)
        ts = val / 1000.0 if val > 1e11 else float(val)
        return datetime.fromtimestamp(ts, tz=timezone.utc)

    try:
        dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None
