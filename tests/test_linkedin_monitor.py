"""Tests for LinkedIn monitor, persistence, and signal classification."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from yc_launch_monitor.config import Settings
from yc_launch_monitor.models.company import ParsedCompany
from yc_launch_monitor.models.linkedin_signal import (
    LinkedInPostStatus,
    LinkedInSignalClassification,
    ParsedLinkedInSignal,
)
from yc_launch_monitor.monitors.linkedin.fetcher import LinkedInFetcher, LinkedInFetchError
from yc_launch_monitor.monitors.linkedin.matcher import LinkedInCompanyConfirmationMatcher
from yc_launch_monitor.monitors.linkedin.monitor import LinkedInMonitor
from yc_launch_monitor.monitors.linkedin.parser import parse_linkedin_payload
from yc_launch_monitor.storage.sqlite import CompanyStore

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RUN_TIME = datetime(2026, 2, 10, 14, 0, 0, tzinfo=timezone.utc)
LATER_RUN_TIME = datetime(2026, 2, 20, 18, 30, 0, tzinfo=timezone.utc)


@pytest.fixture
def raw_linkedin_payload() -> dict:
    return json.loads((FIXTURES_DIR / "linkedin_posts.json").read_text(encoding="utf-8"))


@pytest.fixture
def parsed_signals(raw_linkedin_payload: dict) -> list[ParsedLinkedInSignal]:
    return parse_linkedin_payload(raw_linkedin_payload, require_relevant=True)


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
        x_bearer_token=None,
        linkedin_access_token=None,
    )


def test_detects_early_yc_signal_when_unconfirmed(
    settings: Settings,
    parsed_signals: list[ParsedLinkedInSignal],
) -> None:
    store = CompanyStore(settings.state_db_path)
    matcher = LinkedInCompanyConfirmationMatcher(store)
    unconfirmed_signal = parsed_signals[0]  # AgentScale

    connection = store.connect()
    try:
        evaluated = matcher.evaluate_signal(connection, unconfirmed_signal)
    finally:
        connection.close()

    assert evaluated.is_early_signal is True
    assert evaluated.is_confirmed_yc is False
    assert evaluated.classification == LinkedInSignalClassification.EARLY_YC_SIGNAL


def test_does_not_mark_early_when_company_already_confirmed_in_db(
    settings: Settings,
    parsed_signals: list[ParsedLinkedInSignal],
) -> None:
    store = CompanyStore(settings.state_db_path)
    connection = store.connect()
    try:
        # Pre-seed confirmed Airbnb company in the database
        confirmed_company = ParsedCompany(
            stable_id="yc-dir:airbnb",
            name="Airbnb",
            yc_profile_url="https://www.ycombinator.com/companies/airbnb",
            description="Book accommodations around the world.",
            batch="Summer 2009",
            website="https://www.airbnb.com",
            category="Travel",
            source="yc_directory",
        )
        store.save_company(connection, confirmed_company, seen_at=RUN_TIME)
        connection.commit()

        # Signal #3 mentions Airbnb ("We at Airbnb are continuing...")
        airbnb_signal = next(s for s in parsed_signals if s.company_name == "Airbnb")
        matcher = LinkedInCompanyConfirmationMatcher(store)
        evaluated = matcher.evaluate_signal(connection, airbnb_signal)
    finally:
        connection.close()

    assert evaluated.is_confirmed_yc is True
    assert evaluated.is_early_signal is False
    assert evaluated.classification == LinkedInSignalClassification.CONFIRMED_YC


def test_classifies_speedrun_signal(
    settings: Settings,
    parsed_signals: list[ParsedLinkedInSignal],
) -> None:
    store = CompanyStore(settings.state_db_path)
    matcher = LinkedInCompanyConfirmationMatcher(store)
    speedrun_signal = next(s for s in parsed_signals if s.program == "Speedrun")

    connection = store.connect()
    try:
        evaluated = matcher.evaluate_signal(connection, speedrun_signal)
    finally:
        connection.close()

    assert evaluated.is_speedrun_signal is True
    assert evaluated.classification == LinkedInSignalClassification.SPEEDRUN_SIGNAL


def test_linkedin_monitor_prevents_duplicates_and_preserves_detected_at(
    settings: Settings,
    raw_linkedin_payload: dict,
) -> None:
    def fetch_posts() -> list[dict]:
        return raw_linkedin_payload["posts"]

    monitor = LinkedInMonitor(settings, fetch_posts=fetch_posts)

    first_result = monitor.run(seen_at=RUN_TIME)
    assert first_result.discovered == 5
    assert first_result.relevant_signals == 3
    assert first_result.early_signals == 2  # AgentScale, Airbnb (when not preseeded)
    assert first_result.speedrun_signals == 1  # HyperForge
    assert first_result.already_seen == 0
    assert first_result.failed == 1

    second_result = monitor.run(seen_at=LATER_RUN_TIME)
    assert second_result.discovered == 5
    assert second_result.relevant_signals == 3
    assert second_result.already_seen == 3
    assert second_result.failed == 1

    store = CompanyStore(settings.state_db_path)
    connection = store.connect()
    try:
        assert store.count_linkedin_signals(connection) == 3
        record = store.get_linkedin_signal_by_stable_id(connection, "li:7190000000000000001")
    finally:
        connection.close()

    assert record is not None
    assert record.detected_at == RUN_TIME
    assert record.last_seen_at == LATER_RUN_TIME
    assert record.source == "linkedin"
    assert record.is_early_signal is True


def test_save_linkedin_signal_returns_new_and_already_seen_statuses(
    settings: Settings,
    parsed_signals: list[ParsedLinkedInSignal],
) -> None:
    store = CompanyStore(settings.state_db_path)
    signal = parsed_signals[0]

    connection = store.connect()
    try:
        first_status = store.save_linkedin_signal(connection, signal, seen_at=RUN_TIME)
        second_status = store.save_linkedin_signal(connection, signal, seen_at=LATER_RUN_TIME)
        connection.commit()
    finally:
        connection.close()

    assert first_status is LinkedInPostStatus.NEW
    assert second_status is LinkedInPostStatus.ALREADY_SEEN


def test_fetcher_raises_when_access_token_missing(settings: Settings) -> None:
    fetcher = LinkedInFetcher(settings)
    with pytest.raises(LinkedInFetchError, match="LINKEDIN_ACCESS_TOKEN is not configured"):
        fetcher.fetch_recent_posts()
