"""Parse X post payloads into normalized domain signals."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from yc_launch_monitor.models.x_signal import (
    SOURCE_X,
    ParsedXSignal,
    build_x_author_url,
    build_x_post_url,
    build_x_stable_id,
)
from yc_launch_monitor.monitors.x.detector import DetectionResult, XSignalDetector

logger = logging.getLogger(__name__)


class XParseError(ValueError):
    """Raised when an X post payload cannot be parsed."""


def parse_x_post(
    tweet: dict[str, Any],
    detector: XSignalDetector | None = None,
    require_relevant: bool = True,
) -> ParsedXSignal | None:
    """
    Parse a raw tweet dictionary into a normalized ParsedXSignal.

    If require_relevant is True and the post has no YC/Speedrun signal, returns None.
    """
    post_id = _extract_post_id(tweet)
    text = _extract_text(tweet)
    author_username = _extract_username(tweet)
    author_name = _extract_author_name(tweet)
    author_url = _extract_author_url(tweet, author_username)
    post_url = _extract_post_url(tweet, author_username, post_id)
    detected_at = _extract_timestamp(tweet)

    detector = detector or XSignalDetector()
    detection: DetectionResult = detector.detect(
        text=text,
        author_name=author_name,
        author_username=author_username,
    )

    if require_relevant and not detection.is_relevant:
        logger.debug("Skipping non-relevant X post #%s", post_id)
        return None

    return ParsedXSignal(
        stable_id=build_x_stable_id(post_id),
        post_id=post_id,
        author_username=author_username,
        author_name=author_name,
        author_url=author_url,
        company_name=detection.company_name,
        batch=detection.batch,
        program=detection.program,
        post_text=text,
        post_url=post_url,
        source=SOURCE_X,
        is_early_signal=False,  # Evaluated by Matcher/Monitor against SQLite
        is_confirmed_yc=False,  # Evaluated by Matcher/Monitor against SQLite
        signal_reason=detection.signal_reason,
        detected_at=detected_at,
    )


def parse_x_payload(
    payload: dict[str, Any] | list[Any],
    detector: XSignalDetector | None = None,
    require_relevant: bool = True,
) -> list[ParsedXSignal]:
    """Parse a list or dictionary payload of tweets into normalized signals."""
    items: list[Any]
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("data", []) or payload.get("posts", []) or payload.get("tweets", [])
    else:
        raise XParseError("X payload must be a dict or list")

    signals: list[ParsedXSignal] = []
    detector = detector or XSignalDetector()

    for item in items:
        if not isinstance(item, dict):
            logger.warning("Skipping non-object tweet item: %r", item)
            continue
        try:
            signal = parse_x_post(item, detector=detector, require_relevant=require_relevant)
            if signal is not None:
                signals.append(signal)
        except XParseError as exc:
            logger.warning("Failed to parse tweet item: %s", exc)
            continue

    return signals


def _extract_post_id(tweet: dict[str, Any]) -> str:
    for key in ("id", "post_id", "tweet_id", "id_str"):
        val = tweet.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    raise XParseError("Tweet is missing id")


def _extract_text(tweet: dict[str, Any]) -> str:
    for key in ("text", "full_text", "content", "body"):
        val = tweet.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    raise XParseError("Tweet is missing text/content")


def _extract_username(tweet: dict[str, Any]) -> str:
    for key in ("author_username", "username", "screen_name"):
        val = tweet.get(key)
        if val is not None and str(val).strip():
            return str(val).strip().lstrip("@")

    user_obj = tweet.get("user") or tweet.get("author")
    if isinstance(user_obj, dict):
        for key in ("username", "screen_name"):
            val = user_obj.get(key)
            if val is not None and str(val).strip():
                return str(val).strip().lstrip("@")

    return "unknown_user"


def _extract_author_name(tweet: dict[str, Any]) -> str | None:
    for key in ("author_name", "name", "display_name"):
        val = tweet.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()

    user_obj = tweet.get("user") or tweet.get("author")
    if isinstance(user_obj, dict):
        for key in ("name", "display_name"):
            val = user_obj.get(key)
            if val is not None and str(val).strip():
                return str(val).strip()

    return None


def _extract_author_url(tweet: dict[str, Any], username: str) -> str:
    for key in ("author_url", "profile_url"):
        val = tweet.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()

    user_obj = tweet.get("user") or tweet.get("author")
    if isinstance(user_obj, dict):
        val = user_obj.get("url")
        if val is not None and str(val).strip():
            return str(val).strip()

    return build_x_author_url(username)


def _extract_post_url(tweet: dict[str, Any], username: str, post_id: str) -> str:
    for key in ("post_url", "url"):
        val = tweet.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()

    return build_x_post_url(username, post_id)


def _extract_timestamp(tweet: dict[str, Any]) -> datetime | None:
    val = tweet.get("created_at") or tweet.get("detected_at")
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    try:
        dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None
