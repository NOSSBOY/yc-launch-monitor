"""Tests for YC Directory persistence and monitor behavior."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from yc_launch_monitor.config import Settings
from yc_launch_monitor.models.company import CompanyStatus, ParsedCompany
from yc_launch_monitor.monitors.yc_directory.monitor import YCDirectoryMonitor
from yc_launch_monitor.monitors.yc_directory.parser import parse_algolia_response
from yc_launch_monitor.storage.sqlite import CompanyStore, format_timestamp, parse_timestamp

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RUN_TIME = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
LATER_RUN_TIME = datetime(2026, 2, 1, 8, 30, 0, tzinfo=timezone.utc)


@pytest.fixture
def parsed_companies() -> list[ParsedCompany]:
    payload = json.loads((FIXTURES_DIR / "yc_directory_algolia_page.json").read_text(encoding="utf-8"))
    return parse_algolia_response(payload)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        state_db_path=tmp_path / "state.db",
        log_level="INFO",
        yc_companies_url="https://www.ycombinator.com/companies",
        yc_algolia_app_id=None,
        yc_algolia_api_key=None,
        yc_algolia_index="YCCompany_production",
        yc_algolia_hits_per_page=1000,
    )


def test_save_company_detects_new_company(settings: Settings, parsed_companies: list[ParsedCompany]) -> None:
    store = CompanyStore(settings.state_db_path)
    company = parsed_companies[0]

    connection = store.connect()
    try:
        status = store.save_company(connection, company, seen_at=RUN_TIME)
        connection.commit()
    finally:
        connection.close()

    assert status is CompanyStatus.NEW
    assert store.count_companies(store.connect()) == 1


def test_save_company_detects_already_seen_company(
    settings: Settings,
    parsed_companies: list[ParsedCompany],
) -> None:
    store = CompanyStore(settings.state_db_path)
    company = parsed_companies[0]

    connection = store.connect()
    try:
        first_status = store.save_company(connection, company, seen_at=RUN_TIME)
        second_status = store.save_company(connection, company, seen_at=LATER_RUN_TIME)
        connection.commit()
        record = store.get_by_stable_id(connection, company.stable_id)
    finally:
        connection.close()

    assert first_status is CompanyStatus.NEW
    assert second_status is CompanyStatus.ALREADY_SEEN
    assert store.count_companies(store.connect()) == 1
    assert record is not None
    assert record.first_detected_at == RUN_TIME
    assert record.last_seen_at == LATER_RUN_TIME


def test_monitor_prevents_duplicate_records_on_rerun(
    settings: Settings,
    parsed_companies: list[ParsedCompany],
) -> None:
    monitor = YCDirectoryMonitor(settings)

    first_result = monitor.ingest_companies(parsed_companies, seen_at=RUN_TIME)
    second_result = monitor.ingest_companies(parsed_companies, seen_at=LATER_RUN_TIME)

    assert first_result.discovered == 2
    assert first_result.new == 2
    assert first_result.already_seen == 0

    assert second_result.discovered == 2
    assert second_result.new == 0
    assert second_result.already_seen == 2

    store = CompanyStore(settings.state_db_path)
    connection = store.connect()
    try:
        assert store.count_companies(connection) == 2
        airbnb = store.get_by_stable_id(connection, "yc-dir:airbnb")
    finally:
        connection.close()

    assert airbnb is not None
    assert airbnb.first_detected_at == RUN_TIME
    assert airbnb.last_seen_at == LATER_RUN_TIME


def test_monitor_counts_failed_records_from_invalid_hits(settings: Settings) -> None:
    payload = json.loads((FIXTURES_DIR / "yc_directory_algolia_page.json").read_text(encoding="utf-8"))
    invalid_hit = json.loads((FIXTURES_DIR / "yc_directory_invalid_hit.json").read_text(encoding="utf-8"))

    def fetch_hits() -> list[dict]:
        return [*payload["hits"], invalid_hit]

    monitor = YCDirectoryMonitor(settings, fetch_hits=fetch_hits)
    result = monitor.run(seen_at=RUN_TIME)

    assert result.discovered == 3
    assert result.new == 2
    assert result.failed == 1
    assert result.already_seen == 0


def test_timestamp_helpers_round_trip() -> None:
    original = datetime(2026, 3, 4, 9, 15, 30, tzinfo=timezone.utc)
    restored = parse_timestamp(format_timestamp(original))
    assert restored == original
