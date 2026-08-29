"""Tests for X post parser."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from yc_launch_monitor.models.x_signal import SOURCE_X
from yc_launch_monitor.monitors.x.parser import XParseError, parse_x_payload, parse_x_post

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def test_parse_x_post_extracts_expected_fields() -> None:
    payload = load_fixture("x_posts.json")
    item = payload["posts"][0]
    signal = parse_x_post(item)

    assert signal is not None
    assert signal.stable_id == "x:1890000000000000001"
    assert signal.post_id == "1890000000000000001"
    assert signal.author_username == "sarah_founder"
    assert signal.author_name == "Sarah Chen"
    assert signal.author_url == "https://x.com/sarah_founder"
    assert signal.post_url == "https://x.com/sarah_founder/status/1890000000000000001"
    assert signal.batch == "S26"
    assert signal.program == "YC"
    assert signal.company_name == "AgentScale"
    assert signal.source == SOURCE_X
    assert signal.source == "x"


def test_parse_x_payload_filters_irrelevant_and_invalid() -> None:
    payload = load_fixture("x_posts.json")
    signals = parse_x_payload(payload, require_relevant=True)

    # Out of 5 posts: 3 are relevant YC/Speedrun signals, 1 is casual/unrelated, 1 is malformed
    assert len(signals) == 3
    assert {s.post_id for s in signals} == {
        "1890000000000000001",
        "1890000000000000002",
        "1890000000000000003",
    }


def test_parse_x_post_requires_id() -> None:
    with pytest.raises(XParseError, match="missing id"):
        parse_x_post({"text": "We got into YC S26!"})


def test_parse_x_post_requires_text() -> None:
    with pytest.raises(XParseError, match="missing text"):
        parse_x_post({"id": "12345"})
