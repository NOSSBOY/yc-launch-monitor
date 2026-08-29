"""Tests for YC Speedrun parsing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from yc_launch_monitor.models.company import SOURCE_YC_SPEEDRUN
from yc_launch_monitor.monitors.yc_speedrun.parser import (
    YCSpeedrunParseError,
    parse_speedrun_html,
    parse_speedrun_item,
    parse_speedrun_payload,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def test_parse_speedrun_item_extracts_expected_fields() -> None:
    payload = load_fixture("yc_speedrun_page.json")
    item = payload["companies"][0]
    company = parse_speedrun_item(item)

    assert company.stable_id == "yc-sr:nova-ai"
    assert company.name == "Nova AI"
    assert company.yc_profile_url == "https://www.ycombinator.com/speedrun/companies/nova-ai"
    assert company.description == "Autonomous AI workflows for creative teams."
    assert company.batch == "Speedrun Winter 2024"
    assert company.website == "https://nova-ai.example.com"
    assert company.category == "Artificial Intelligence, Developer Tools"
    assert company.source == SOURCE_YC_SPEEDRUN
    assert company.source == "yc_speedrun"


def test_parse_speedrun_payload_returns_all_valid_items() -> None:
    payload = load_fixture("yc_speedrun_page.json")
    companies = parse_speedrun_payload(payload)

    assert len(companies) == 2
    assert {company.stable_id for company in companies} == {"yc-sr:nova-ai", "yc-sr:hyperspeed-data"}
    for company in companies:
        assert company.source == "yc_speedrun"


def test_parse_speedrun_item_requires_name() -> None:
    invalid_item = load_fixture("yc_speedrun_invalid_item.json")

    with pytest.raises(YCSpeedrunParseError, match="missing name"):
        parse_speedrun_item(invalid_item)


def test_parse_speedrun_item_requires_slug() -> None:
    item_without_slug = {"name": "No Slug Co"}

    with pytest.raises(YCSpeedrunParseError, match="missing slug/id"):
        parse_speedrun_item(item_without_slug)


def test_parse_speedrun_html_embedded_next_data() -> None:
    payload = load_fixture("yc_speedrun_page.json")
    embedded_data = json.dumps({"props": {"pageProps": {"companies": payload["companies"]}}})
    html = f"""
    <!DOCTYPE html>
    <html>
      <head><title>Speedrun Companies</title></head>
      <body>
        <div id="__next"></div>
        <script id="__NEXT_DATA__" type="application/json">
          {embedded_data}
        </script>
      </body>
    </html>
    """
    companies = parse_speedrun_html(html)
    assert len(companies) == 2
    assert companies[0].stable_id == "yc-sr:nova-ai"
    assert companies[1].stable_id == "yc-sr:hyperspeed-data"
    assert all(c.source == "yc_speedrun" for c in companies)


def test_parse_speedrun_api_paginated_dict() -> None:
    payload = load_fixture("yc_speedrun_page.json")
    api_response = {
        "count": 2,
        "next": None,
        "previous": None,
        "results": payload["companies"],
    }
    companies = parse_speedrun_payload(api_response)
    assert len(companies) == 2
    assert companies[0].stable_id == "yc-sr:nova-ai"
    assert companies[1].stable_id == "yc-sr:hyperspeed-data"


def test_parse_speedrun_html_nested_results_in_next_data() -> None:
    payload = load_fixture("yc_speedrun_page.json")
    embedded_data = json.dumps({
        "props": {
            "pageProps": {
                "companies": {
                    "count": 2,
                    "results": payload["companies"],
                }
            }
        }
    })
    html = f"""
    <!DOCTYPE html>
    <html>
      <head><title>Speedrun Companies</title></head>
      <body>
        <script id="__NEXT_DATA__" type="application/json">{embedded_data}</script>
      </body>
    </html>
    """
    companies = parse_speedrun_html(html)
    assert len(companies) == 2
    assert companies[0].stable_id == "yc-sr:nova-ai"
    assert companies[1].stable_id == "yc-sr:hyperspeed-data"

