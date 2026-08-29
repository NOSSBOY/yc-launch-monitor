"""Tests for YC Speedrun persistence and monitor behavior."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from yc_launch_monitor.config import Settings
from yc_launch_monitor.models.company import CompanyStatus, ParsedCompany
from yc_launch_monitor.monitors.yc_speedrun.monitor import YCSpeedrunMonitor
from yc_launch_monitor.monitors.yc_speedrun.parser import parse_speedrun_payload
from yc_launch_monitor.storage.sqlite import CompanyStore

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RUN_TIME = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
LATER_RUN_TIME = datetime(2026, 2, 1, 8, 30, 0, tzinfo=timezone.utc)


@pytest.fixture
def parsed_speedrun_companies() -> list[ParsedCompany]:
    payload = json.loads((FIXTURES_DIR / "yc_speedrun_page.json").read_text(encoding="utf-8"))
    return parse_speedrun_payload(payload)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        state_db_path=tmp_path / "state.db",
        log_level="INFO",
        yc_companies_url="https://www.ycombinator.com/companies",
        yc_speedrun_url="https://www.ycombinator.com/speedrun",
        yc_algolia_app_id=None,
        yc_algolia_api_key=None,
        yc_algolia_index="YCCompany_production",
        yc_algolia_hits_per_page=1000,
    )


def test_save_speedrun_company_detects_new_company(
    settings: Settings,
    parsed_speedrun_companies: list[ParsedCompany],
) -> None:
    store = CompanyStore(settings.state_db_path)
    company = parsed_speedrun_companies[0]

    connection = store.connect()
    try:
        status = store.save_company(connection, company, seen_at=RUN_TIME)
        connection.commit()
    finally:
        connection.close()

    assert status is CompanyStatus.NEW
    assert store.count_companies(store.connect()) == 1


def test_save_speedrun_company_detects_already_seen_company(
    settings: Settings,
    parsed_speedrun_companies: list[ParsedCompany],
) -> None:
    store = CompanyStore(settings.state_db_path)
    company = parsed_speedrun_companies[0]

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
    assert record.source == "yc_speedrun"


def test_speedrun_monitor_prevents_duplicate_records_on_rerun(
    settings: Settings,
    parsed_speedrun_companies: list[ParsedCompany],
) -> None:
    monitor = YCSpeedrunMonitor(settings)

    first_result = monitor.ingest_companies(parsed_speedrun_companies, seen_at=RUN_TIME)
    second_result = monitor.ingest_companies(parsed_speedrun_companies, seen_at=LATER_RUN_TIME)

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
        nova = store.get_by_stable_id(connection, "yc-sr:nova-ai")
    finally:
        connection.close()

    assert nova is not None
    assert nova.first_detected_at == RUN_TIME
    assert nova.last_seen_at == LATER_RUN_TIME
    assert nova.source == "yc_speedrun"


def test_speedrun_monitor_records_identified_as_yc_speedrun(
    settings: Settings,
    parsed_speedrun_companies: list[ParsedCompany],
) -> None:
    monitor = YCSpeedrunMonitor(settings)
    monitor.ingest_companies(parsed_speedrun_companies, seen_at=RUN_TIME)

    store = CompanyStore(settings.state_db_path)
    connection = store.connect()
    try:
        for company in parsed_speedrun_companies:
            record = store.get_by_stable_id(connection, company.stable_id)
            assert record is not None
            assert record.source == "yc_speedrun"
    finally:
        connection.close()


def test_speedrun_monitor_counts_failed_records_from_invalid_hits(settings: Settings) -> None:
    payload = json.loads((FIXTURES_DIR / "yc_speedrun_page.json").read_text(encoding="utf-8"))
    invalid_item = json.loads((FIXTURES_DIR / "yc_speedrun_invalid_item.json").read_text(encoding="utf-8"))

    def fetch_items() -> list[dict]:
        return [*payload["companies"], invalid_item]

    monitor = YCSpeedrunMonitor(settings, fetch_items=fetch_items)
    result = monitor.run(seen_at=RUN_TIME)

    assert result.discovered == 3
    assert result.new == 2
    assert result.failed == 1
    assert result.already_seen == 0
