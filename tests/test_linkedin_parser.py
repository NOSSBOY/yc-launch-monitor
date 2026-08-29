"""Tests for LinkedIn post parser."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from yc_launch_monitor.models.linkedin_signal import SOURCE_LINKEDIN
from yc_launch_monitor.monitors.linkedin.parser import (
    LinkedInParseError,
    parse_linkedin_payload,
    parse_linkedin_post,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def test_parse_linkedin_post_extracts_expected_fields() -> None:
    payload = load_fixture("linkedin_posts.json")
    item = payload["posts"][0]
    signal = parse_linkedin_post(item)

    assert signal is not None
    assert signal.stable_id == "li:7190000000000000001"
    assert signal.post_id == "7190000000000000001"
    assert signal.author_name == "Elena Rostova"
    assert signal.author_profile_url == "https://www.linkedin.com/in/elena-rostova"
    assert signal.author_urn == "urn:li:person:elena123"
    assert signal.company_name == "AgentScale"
    assert signal.batch == "S26"
    assert signal.program == "YC"
    assert signal.source == SOURCE_LINKEDIN
    assert signal.source == "linkedin"
    assert "7190000000000000001" in signal.post_url


def test_parse_linkedin_payload_filters_irrelevant_and_invalid() -> None:
    payload = load_fixture("linkedin_posts.json")
    signals = parse_linkedin_payload(payload, require_relevant=True)

    # Out of 5 items: 3 relevant, 1 casual mention, 1 malformed
    assert len(signals) == 3
    assert {s.post_id for s in signals} == {
        "7190000000000000001",
        "7190000000000000002",
        "7190000000000000003",
    }


def test_parse_linkedin_post_requires_id() -> None:
    with pytest.raises(LinkedInParseError, match="missing id"):
        parse_linkedin_post({"text": "We got into YC S26!"})


def test_parse_linkedin_post_requires_text() -> None:
    with pytest.raises(LinkedInParseError, match="missing text"):
        parse_linkedin_post({"id": "7190000000000000099"})


def test_parse_linkedin_nested_commentary() -> None:
    post = {
        "id": "7190000000000000088",
        "author": {"name": "Alex Smith", "urn": "urn:li:person:alex88"},
        "commentary": {"text": "We got into YC W27! Building CloudNova."},
    }
    signal = parse_linkedin_post(post)
    assert signal is not None
    assert signal.post_id == "7190000000000000088"
    assert signal.author_name == "Alex Smith"
    assert signal.author_urn == "urn:li:person:alex88"
    assert signal.batch == "W27"
    assert signal.company_name == "CloudNova"
