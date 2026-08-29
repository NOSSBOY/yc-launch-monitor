"""Tests for the MonitorScheduler and CLI scheduler subcommand."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from yc_launch_monitor.cli import main
from yc_launch_monitor.config import Settings
from yc_launch_monitor.models.linkedin_signal import LinkedInSignalClassification
from yc_launch_monitor.monitors.linkedin.monitor import LinkedInMonitorResult
from yc_launch_monitor.monitors.x.monitor import XMonitorResult
from yc_launch_monitor.monitors.yc_directory.monitor import MonitorResult
from yc_launch_monitor.scheduler import CycleSummary, MonitorScheduler


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        state_db_path=tmp_path / "state.db",
        log_level="INFO",
        monitor_interval_seconds=300,
    )


def test_scheduler_runs_monitors_sequentially(settings: Settings) -> None:
    call_order: list[str] = []

    mock_yc_dir = MagicMock()
    mock_yc_dir.run.side_effect = lambda: (
        call_order.append("yc_directory"),
        MonitorResult(discovered=10, new=2, already_seen=8, failed=0),
    )[1]

    mock_yc_sr = MagicMock()
    mock_yc_sr.run.side_effect = lambda: (
        call_order.append("yc_speedrun"),
        MonitorResult(discovered=5, new=1, already_seen=4, failed=0),
    )[1]

    mock_x = MagicMock()
    mock_x.run.side_effect = lambda: (
        call_order.append("x"),
        XMonitorResult(discovered=20, relevant_signals=4, early_signals=2, already_seen=2, failed=0),
    )[1]

    mock_linkedin = MagicMock()
    mock_linkedin.run.side_effect = lambda: (
        call_order.append("linkedin"),
        LinkedInMonitorResult(
            discovered=15,
            relevant_signals=3,
            early_signals=1,
            speedrun_signals=1,
            confirmed_yc=1,
            already_seen=0,
            failed=0,
        ),
    )[1]

    scheduler = MonitorScheduler(
        settings=settings,
        yc_directory_monitor=mock_yc_dir,
        yc_speedrun_monitor=mock_yc_sr,
        x_monitor=mock_x,
        linkedin_monitor=mock_linkedin,
    )

    summary: CycleSummary = scheduler.run_cycle(cycle_number=1)

    assert call_order == ["yc_directory", "yc_speedrun", "x", "linkedin"]
    assert summary.cycle_number == 1
    assert summary.errors == {}
    assert summary.yc_directory_result is not None
    assert summary.yc_directory_result.new == 2
    assert summary.yc_speedrun_result is not None
    assert summary.yc_speedrun_result.new == 1
    assert summary.x_result is not None
    assert summary.x_result.early_signals == 2
    assert summary.linkedin_result is not None
    assert summary.linkedin_result.speedrun_signals == 1


def test_scheduler_isolates_individual_monitor_failures(settings: Settings) -> None:
    mock_yc_dir = MagicMock()
    mock_yc_dir.run.return_value = MonitorResult(discovered=10, new=2, already_seen=8, failed=0)

    mock_yc_sr = MagicMock()
    mock_yc_sr.run.side_effect = RuntimeError("Speedrun fetch connection timeout")

    mock_x = MagicMock()
    mock_x.run.side_effect = RuntimeError("X API rate limited (HTTP 429)")

    mock_linkedin = MagicMock()
    mock_linkedin.run.return_value = LinkedInMonitorResult(
        discovered=5,
        relevant_signals=2,
        early_signals=1,
        speedrun_signals=0,
        confirmed_yc=1,
        already_seen=0,
        failed=0,
    )

    scheduler = MonitorScheduler(
        settings=settings,
        yc_directory_monitor=mock_yc_dir,
        yc_speedrun_monitor=mock_yc_sr,
        x_monitor=mock_x,
        linkedin_monitor=mock_linkedin,
    )

    # Should not raise exception
    summary = scheduler.run_cycle(cycle_number=2)

    assert summary.cycle_number == 2
    assert summary.yc_directory_result is not None
    assert summary.yc_speedrun_result is None
    assert summary.x_result is None
    assert summary.linkedin_result is not None
    assert "yc_speedrun" in summary.errors
    assert "Speedrun fetch connection timeout" in summary.errors["yc_speedrun"]
    assert "x" in summary.errors
    assert "X API rate limited" in summary.errors["x"]
    assert "yc_directory" not in summary.errors
    assert "linkedin" not in summary.errors


def test_scheduler_respects_max_cycles_and_interval(settings: Settings) -> None:
    mock_yc_dir = MagicMock()
    mock_yc_dir.run.return_value = MonitorResult(discovered=0, new=0, already_seen=0, failed=0)
    mock_yc_sr = MagicMock()
    mock_yc_sr.run.return_value = MonitorResult(discovered=0, new=0, already_seen=0, failed=0)
    mock_x = MagicMock()
    mock_x.run.return_value = XMonitorResult(discovered=0, relevant_signals=0, early_signals=0, already_seen=0, failed=0)
    mock_linkedin = MagicMock()
    mock_linkedin.run.return_value = LinkedInMonitorResult(discovered=0, relevant_signals=0, early_signals=0, speedrun_signals=0, confirmed_yc=0, already_seen=0, failed=0)

    sleep_calls: list[float] = []

    def mock_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    scheduler = MonitorScheduler(
        settings=settings,
        yc_directory_monitor=mock_yc_dir,
        yc_speedrun_monitor=mock_yc_sr,
        x_monitor=mock_x,
        linkedin_monitor=mock_linkedin,
        sleep_fn=mock_sleep,
    )

    scheduler.start(interval_seconds=45, max_cycles=3)

    assert mock_yc_dir.run.call_count == 3
    assert mock_yc_sr.run.call_count == 3
    assert mock_x.run.call_count == 3
    assert mock_linkedin.run.call_count == 3
    assert scheduler.is_running is False


def test_scheduler_handles_keyboard_interrupt_gracefully(settings: Settings) -> None:
    mock_yc_dir = MagicMock()
    mock_yc_dir.run.return_value = MonitorResult(discovered=0, new=0, already_seen=0, failed=0)
    mock_yc_sr = MagicMock()
    mock_yc_sr.run.return_value = MonitorResult(discovered=0, new=0, already_seen=0, failed=0)
    mock_x = MagicMock()
    mock_x.run.return_value = XMonitorResult(discovered=0, relevant_signals=0, early_signals=0, already_seen=0, failed=0)
    mock_linkedin = MagicMock()
    mock_linkedin.run.return_value = LinkedInMonitorResult(discovered=0, relevant_signals=0, early_signals=0, speedrun_signals=0, confirmed_yc=0, already_seen=0, failed=0)

    def mock_sleep_interrupt(seconds: float) -> None:
        raise KeyboardInterrupt()

    scheduler = MonitorScheduler(
        settings=settings,
        yc_directory_monitor=mock_yc_dir,
        yc_speedrun_monitor=mock_yc_sr,
        x_monitor=mock_x,
        linkedin_monitor=mock_linkedin,
        sleep_fn=mock_sleep_interrupt,
    )

    # Should exit cleanly without unhandled KeyboardInterrupt
    scheduler.start(interval_seconds=60)
    assert scheduler.is_running is False
    assert mock_yc_dir.run.call_count == 1


def test_scheduler_cli_once_flag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("STATE_DB_PATH", str(tmp_path / "state.db"))
    run_cycle_mock = MagicMock(
        return_value=CycleSummary(
            cycle_number=1,
            started_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 1, 1, 12, 0, 5, tzinfo=timezone.utc),
        )
    )
    monkeypatch.setattr(MonitorScheduler, "run_cycle", run_cycle_mock)

    exit_code = main(["scheduler", "--once"])
    assert exit_code == 0
    assert run_cycle_mock.call_count == 1

