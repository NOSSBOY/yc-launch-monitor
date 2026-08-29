"""Unit and integration tests for Slack alert notifications."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from yc_launch_monitor.alerts.slack import (
    SlackNotifier,
    format_company_alert,
    format_linkedin_signal_alert,
    format_x_signal_alert,
)
from yc_launch_monitor.cli import main
from yc_launch_monitor.config import Settings
from yc_launch_monitor.models.company import (
    SOURCE_YC_DIRECTORY,
    SOURCE_YC_SPEEDRUN,
    ParsedCompany,
)
from yc_launch_monitor.models.linkedin_signal import (
    LinkedInSignalClassification,
    ParsedLinkedInSignal,
)
from yc_launch_monitor.models.x_signal import ParsedXSignal
from yc_launch_monitor.monitors.linkedin.monitor import LinkedInMonitorResult
from yc_launch_monitor.monitors.x.monitor import XMonitorResult
from yc_launch_monitor.monitors.yc_directory.monitor import MonitorResult
from yc_launch_monitor.monitors.yc_speedrun.monitor import YCSpeedrunMonitor
from yc_launch_monitor.scheduler import MonitorScheduler
from yc_launch_monitor.storage.sqlite import CompanyStore


@pytest.fixture
def store(tmp_path: Path) -> CompanyStore:
    return CompanyStore(tmp_path / "test_state.db")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        state_db_path=tmp_path / "test_state.db",
        log_level="INFO",
        slack_webhook_url="https://hooks.slack.com/services/T00/B00/XXXX",
    )


@pytest.fixture
def unconfigured_settings(tmp_path: Path) -> Settings:
    return Settings(
        state_db_path=tmp_path / "test_state.db",
        log_level="INFO",
        slack_webhook_url=None,
    )


def test_slack_missing_webhook_returns_false(unconfigured_settings: Settings, store: CompanyStore) -> None:
    notifier = SlackNotifier(unconfigured_settings, store=store)
    assert not notifier.is_configured
    assert notifier.send_message("Test message") is False


def test_slack_successful_webhook_post(settings: Settings, store: CompanyStore) -> None:
    mock_post = MagicMock(return_value=True)
    notifier = SlackNotifier(settings, store=store, http_post_fn=mock_post)

    assert notifier.is_configured
    success = notifier.send_message("Hello Slack")

    assert success is True
    mock_post.assert_called_once_with(
        "https://hooks.slack.com/services/T00/B00/XXXX",
        {"text": "Hello Slack"},
        10.0,
    )


def test_slack_http_error_handling(settings: Settings, store: CompanyStore) -> None:
    mock_post = MagicMock(return_value=False)
    notifier = SlackNotifier(settings, store=store, http_post_fn=mock_post)

    success = notifier.send_message("Failing message")
    assert success is False


def test_slack_format_yc_company_alert() -> None:
    company = ParsedCompany(
        stable_id="yc-dir:acme-ai",
        name="Acme AI",
        yc_profile_url="https://www.ycombinator.com/companies/acme-ai",
        description="Autonomous agents for enterprise.",
        batch="S27",
        website="https://acme.example.com",
        category="Artificial Intelligence",
        source=SOURCE_YC_DIRECTORY,
    )

    alert_text = format_company_alert(company)
    assert "🚀 *NEW YC COMPANY*" in alert_text
    assert "*Company:* Acme AI" in alert_text
    assert "*Batch:* S27" in alert_text
    assert "*Source:* YC Directory" in alert_text
    assert "*Website:* https://acme.example.com" in alert_text
    assert "*YC Profile:* https://www.ycombinator.com/companies/acme-ai" in alert_text


def test_slack_format_speedrun_company_alert() -> None:
    company = ParsedCompany(
        stable_id="yc-sr:nova-game",
        name="Nova Game",
        yc_profile_url="https://speedrun.a16z.com/companies/nova-game",
        description="Next-gen game engine.",
        batch="SR003",
        website="https://nova.example.com",
        category="Gaming",
        source=SOURCE_YC_SPEEDRUN,
    )

    alert_text = format_company_alert(company)
    assert "⚡ *NEW SPEEDRUN COMPANY*" in alert_text
    assert "*Company:* Nova Game" in alert_text
    assert "*Batch:* SR003" in alert_text
    assert "*Source:* YC Speedrun" in alert_text
    assert "*Website:* https://nova.example.com" in alert_text


def test_slack_format_early_yc_x_signal_alert() -> None:
    signal = ParsedXSignal(
        stable_id="x:123456",
        post_id="123456",
        author_username="jane_founder",
        post_text="Super excited to announce we got into YC S27 with DataFlow!",
        post_url="https://x.com/jane_founder/status/123456",
        author_name="Jane Doe",
        author_url="https://x.com/jane_founder",
        company_name="DataFlow",
        batch="S27",
        program="YC",
        source="x",
        is_early_signal=True,
        is_confirmed_yc=False,
        signal_reason="Accepted into Y Combinator (YC S27)",
    )

    alert_text = format_x_signal_alert(signal)
    assert "🚨 *EARLY YC SIGNAL*" in alert_text
    assert "*Company:* DataFlow" in alert_text
    assert "*Batch:* S27" in alert_text
    assert "*Signal:* Accepted into Y Combinator (YC S27)" in alert_text
    assert "*Source:* X" in alert_text
    assert "*Author:* Jane Doe (@jane_founder)" in alert_text
    assert "*Post:* https://x.com/jane_founder/status/123456" in alert_text
    assert "> Super excited to announce" in alert_text


def test_slack_format_speedrun_linkedin_signal_alert() -> None:
    signal = ParsedLinkedInSignal(
        stable_id="li:987654",
        post_id="987654",
        author_name="John Smith",
        post_text="Thrilled to share that we have been accepted into Speedrun batch 004!",
        post_url="https://www.linkedin.com/feed/update/urn:li:activity:987654",
        author_profile_url="https://www.linkedin.com/in/johnsmith",
        company_name="VoxelAI",
        batch="Speedrun batch 004",
        program="Speedrun",
        source="linkedin",
        classification=LinkedInSignalClassification.SPEEDRUN_SIGNAL,
        is_early_signal=False,
        is_confirmed_yc=False,
        is_speedrun_signal=True,
        signal_reason="Accepted into Speedrun",
    )

    alert_text = format_linkedin_signal_alert(signal)
    assert "⚡ *SPEEDRUN SIGNAL*" in alert_text
    assert "*Company:* VoxelAI" in alert_text
    assert "*Batch:* Speedrun batch 004" in alert_text
    assert "*Source:* LinkedIn" in alert_text
    assert "*Author:* John Smith" in alert_text
    assert "> Thrilled to share" in alert_text


def test_slack_prevents_duplicate_alerts(settings: Settings, store: CompanyStore) -> None:
    mock_post = MagicMock(return_value=True)
    notifier = SlackNotifier(settings, store=store, http_post_fn=mock_post)

    company = ParsedCompany(
        stable_id="yc-dir:repeat-ai",
        name="Repeat AI",
        yc_profile_url="https://www.ycombinator.com/companies/repeat-ai",
        description="AI persistence",
        batch="W26",
        website="https://repeat.ai",
        category="DevTools",
        source=SOURCE_YC_DIRECTORY,
    )

    # First send should succeed and record in DB
    assert notifier.send_company_alert(company) is True
    assert mock_post.call_count == 1

    # Second send of identical entity must be skipped
    assert notifier.send_company_alert(company) is False
    assert mock_post.call_count == 1

    conn = store.connect()
    try:
        assert store.has_slack_alert_been_sent(conn, "yc-dir:repeat-ai") is True
        assert store.count_slack_alerts_sent(conn) == 1
    finally:
        conn.close()


def test_scheduler_continues_when_slack_fails(settings: Settings) -> None:
    # Setup mock SlackNotifier where send_message throws an exception
    failing_notifier = MagicMock()
    failing_notifier.send_company_alert.side_effect = RuntimeError("Slack gateway 504 Gateway Timeout")

    mock_yc_dir = MagicMock()
    mock_yc_dir.run.return_value = MonitorResult(discovered=5, new=1, already_seen=4, failed=0)
    mock_yc_sr = MagicMock()
    mock_yc_sr.run.return_value = MonitorResult(discovered=5, new=0, already_seen=5, failed=0)
    mock_x = MagicMock()
    mock_x.run.return_value = XMonitorResult(discovered=10, relevant_signals=2, early_signals=1, already_seen=0, failed=0)
    mock_linkedin = MagicMock()
    mock_linkedin.run.return_value = LinkedInMonitorResult(discovered=8, relevant_signals=1, early_signals=0, speedrun_signals=1, confirmed_yc=0, already_seen=0, failed=0)

    scheduler = MonitorScheduler(
        settings=settings,
        yc_directory_monitor=mock_yc_dir,
        yc_speedrun_monitor=mock_yc_sr,
        x_monitor=mock_x,
        linkedin_monitor=mock_linkedin,
        notifier=failing_notifier,
    )

    # run_cycle should not raise exception despite Slack error
    summary = scheduler.run_cycle(cycle_number=1)
    assert summary.cycle_number == 1
    assert summary.yc_directory_result is not None


def test_cli_slack_test_unconfigured(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("STATE_DB_PATH", str(tmp_path / "state.db"))

    exit_code = main(["slack", "test"])
    assert exit_code == 1


def test_cli_slack_test_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T00/B00/TEST")
    monkeypatch.setenv("STATE_DB_PATH", str(tmp_path / "state.db"))

    with patch.object(SlackNotifier, "send_test_message", return_value=True):
        exit_code = main(["slack", "test"])
        assert exit_code == 0
