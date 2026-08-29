"""Tests for YC Directory parsing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from yc_launch_monitor.monitors.yc_directory.parser import (
    YCDirectoryParseError,
    parse_algolia_hit,
    parse_algolia_response,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def test_parse_algolia_hit_extracts_expected_fields() -> None:
    payload = load_fixture("yc_directory_algolia_page.json")
    company = parse_algolia_hit(payload["hits"][0])

    assert company.stable_id == "yc-dir:airbnb"
    assert company.name == "Airbnb"
    assert company.yc_profile_url == "https://www.ycombinator.com/companies/airbnb"
    assert company.description == "Book accommodations around the world."
    assert company.batch == "Summer 2009"
    assert company.website == "https://www.airbnb.com"
    assert company.category == "Consumer, Travel"
    assert company.source == "yc_directory"


def test_parse_algolia_response_returns_all_valid_hits() -> None:
    payload = load_fixture("yc_directory_algolia_page.json")
    companies = parse_algolia_response(payload)

    assert len(companies) == 2
    assert {company.stable_id for company in companies} == {"yc-dir:airbnb", "yc-dir:stripe"}


def test_parse_algolia_hit_requires_name() -> None:
    invalid_hit = json.loads((FIXTURES_DIR / "yc_directory_invalid_hit.json").read_text(encoding="utf-8"))

    with pytest.raises(YCDirectoryParseError, match="missing name"):
        parse_algolia_hit(invalid_hit)
