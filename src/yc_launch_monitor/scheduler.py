"""Continuous scheduler for recurring monitor execution."""

from __future__ import annotations

import dataclasses
import logging
import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from yc_launch_monitor.config import Settings
from yc_launch_monitor.monitors.linkedin.monitor import LinkedInMonitor, LinkedInMonitorResult
from yc_launch_monitor.monitors.x.monitor import XMonitor, XMonitorResult
from yc_launch_monitor.monitors.yc_directory.monitor import MonitorResult, YCDirectoryMonitor
from yc_launch_monitor.monitors.yc_speedrun.monitor import YCSpeedrunMonitor
from yc_launch_monitor.storage.sqlite import CompanyStore, utc_now

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CycleSummary:
    """Summary statistics and status of a single monitoring cycle."""

    cycle_number: int
    started_at: datetime
    completed_at: datetime
    yc_directory_result: MonitorResult | None = None
    yc_speedrun_result: MonitorResult | None = None
    x_result: XMonitorResult | None = None
    linkedin_result: LinkedInMonitorResult | None = None
    errors: dict[str, str] = field(default_factory=dict)


class MonitorScheduler:
    """
    Orchestrates recurring, sequential execution of all monitors.

    Runs monitors in order:
      1. YC Directory
      2. YC Speedrun
      3. X (Twitter)
      4. LinkedIn

    Ensures failure isolation: an error in one monitor does not halt other monitors
    or abort future scheduled cycles.
    """

    def __init__(
        self,
        settings: Settings,
        store: CompanyStore | None = None,
        yc_directory_monitor: YCDirectoryMonitor | None = None,
        yc_speedrun_monitor: YCSpeedrunMonitor | None = None,
        x_monitor: XMonitor | None = None,
        linkedin_monitor: LinkedInMonitor | None = None,
        sleep_fn: Callable[[float], None] | None = None,
    ) -> None:
        self._settings = settings
        self._store = store or CompanyStore(settings.state_db_path)
        self._yc_directory_monitor = yc_directory_monitor or YCDirectoryMonitor(
            settings, store=self._store
        )
        self._yc_speedrun_monitor = yc_speedrun_monitor or YCSpeedrunMonitor(
            settings, store=self._store
        )
        self._x_monitor = x_monitor or XMonitor(settings, store=self._store)
        self._linkedin_monitor = linkedin_monitor or LinkedInMonitor(
            settings, store=self._store
        )
        self._sleep_fn = sleep_fn or time.sleep
        self._running = False

    @property
    def is_running(self) -> bool:
        """Return True if the scheduler is actively looping."""
        return self._running

    def run_cycle(self, cycle_number: int = 1) -> CycleSummary:
        """
        Execute one complete monitoring cycle across all sources sequentially.

        Catches and records exceptions per monitor so errors remain isolated.
        """
        started_at = utc_now()
        logger.info("=== Starting Monitoring Cycle #%s at %s ===", cycle_number, started_at.isoformat())

        errors: dict[str, str] = {}
        yc_dir_result: MonitorResult | None = None
        yc_speedrun_result: MonitorResult | None = None
        x_result: XMonitorResult | None = None
        linkedin_result: LinkedInMonitorResult | None = None

        # 1. YC Directory Monitor
        try:
            logger.info("Cycle #%s: Running YC Directory monitor...", cycle_number)
            yc_dir_result = self._yc_directory_monitor.run()
            logger.info(
                "Cycle #%s [YC Directory]: discovered=%s new=%s already_seen=%s failed=%s",
                cycle_number,
                yc_dir_result.discovered,
                yc_dir_result.new,
                yc_dir_result.already_seen,
                yc_dir_result.failed,
            )
        except Exception as exc:
            errors["yc_directory"] = str(exc)
            logger.error(
                "Cycle #%s [YC Directory] encountered an error: %s",
                cycle_number,
                exc,
                exc_info=True,
            )

        # 2. YC Speedrun Monitor
        try:
            logger.info("Cycle #%s: Running YC Speedrun monitor...", cycle_number)
            yc_speedrun_result = self._yc_speedrun_monitor.run()
            logger.info(
                "Cycle #%s [YC Speedrun]: discovered=%s new=%s already_seen=%s failed=%s",
                cycle_number,
                yc_speedrun_result.discovered,
                yc_speedrun_result.new,
                yc_speedrun_result.already_seen,
                yc_speedrun_result.failed,
            )
        except Exception as exc:
            errors["yc_speedrun"] = str(exc)
            logger.error(
                "Cycle #%s [YC Speedrun] encountered an error: %s",
                cycle_number,
                exc,
                exc_info=True,
            )

        # 3. X (Twitter) Monitor
        try:
            logger.info("Cycle #%s: Running X (Twitter) monitor...", cycle_number)
            x_result = self._x_monitor.run()
            logger.info(
                "Cycle #%s [X (Twitter)]: discovered=%s relevant=%s early=%s already_seen=%s failed=%s",
                cycle_number,
                x_result.discovered,
                x_result.relevant_signals,
                x_result.early_signals,
                x_result.already_seen,
                x_result.failed,
            )
        except Exception as exc:
            errors["x"] = str(exc)
            logger.error(
                "Cycle #%s [X (Twitter)] encountered an error: %s",
                cycle_number,
                exc,
                exc_info=True,
            )

        # 4. LinkedIn Monitor
        try:
            logger.info("Cycle #%s: Running LinkedIn monitor...", cycle_number)
            linkedin_result = self._linkedin_monitor.run()
            logger.info(
                "Cycle #%s [LinkedIn]: discovered=%s relevant=%s early=%s speedrun=%s confirmed=%s already_seen=%s failed=%s",
                cycle_number,
                linkedin_result.discovered,
                linkedin_result.relevant_signals,
                linkedin_result.early_signals,
                linkedin_result.speedrun_signals,
                linkedin_result.confirmed_yc,
                linkedin_result.already_seen,
                linkedin_result.failed,
            )
        except Exception as exc:
            errors["linkedin"] = str(exc)
            logger.error(
                "Cycle #%s [LinkedIn] encountered an error: %s",
                cycle_number,
                exc,
                exc_info=True,
            )

        completed_at = utc_now()
        duration_seconds = (completed_at - started_at).total_seconds()
        logger.info(
            "=== Completed Monitoring Cycle #%s in %.2fs (errors=%s) ===",
            cycle_number,
            duration_seconds,
            len(errors),
        )

        return CycleSummary(
            cycle_number=cycle_number,
            started_at=started_at,
            completed_at=completed_at,
            yc_directory_result=yc_dir_result,
            yc_speedrun_result=yc_speedrun_result,
            x_result=x_result,
            linkedin_result=linkedin_result,
            errors=errors,
        )

    def start(
        self,
        interval_seconds: int | None = None,
        max_cycles: int | None = None,
    ) -> None:
        """
        Start recurring monitor cycles with graceful shutdown support.

        Repeats indefinitely every interval_seconds until stopped via stop() or Ctrl+C.
        """
        interval = (
            interval_seconds
            if interval_seconds is not None
            else self._settings.monitor_interval_seconds
        )
        logger.info(
            "Starting YC Launch Monitor scheduler (interval=%ss, max_cycles=%s)",
            interval,
            max_cycles or "unlimited",
        )
        self._running = True
        cycle = 0

        def _signal_handler(signum: int, frame: object) -> None:
            sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
            logger.info("Received signal %s; shutting down scheduler gracefully...", sig_name)
            self.stop()

        try:
            signal.signal(signal.SIGINT, _signal_handler)
            if hasattr(signal, "SIGTERM"):
                signal.signal(signal.SIGTERM, _signal_handler)
        except (ValueError, AttributeError):
            # Not in main thread or platform signal restrictions
            pass

        try:
            while self._running:
                cycle += 1
                self.run_cycle(cycle_number=cycle)

                if max_cycles is not None and cycle >= max_cycles:
                    logger.info("Reached target cycle count (%s); exiting scheduler.", max_cycles)
                    break

                if not self._running:
                    break

                logger.info("Sleeping %ss until next cycle...", interval)
                self._sleep_fn(interval)
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received; exiting scheduler cleanly.")
        finally:
            self._running = False
            logger.info("YC Launch Monitor scheduler stopped.")

    def stop(self) -> None:
        """Signal the scheduler to stop running after the current cycle."""
        self._running = False
