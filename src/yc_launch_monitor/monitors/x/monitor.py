"""Orchestrates X post retrieval, signal parsing, early detection, and persistence."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from yc_launch_monitor.config import Settings
from yc_launch_monitor.models.x_signal import ParsedXSignal, XPostStatus
from yc_launch_monitor.monitors.x.detector import XSignalDetector
from yc_launch_monitor.monitors.x.fetcher import XFetcher
from yc_launch_monitor.monitors.x.matcher import CompanyConfirmationMatcher
from yc_launch_monitor.monitors.x.parser import XParseError, parse_x_post
from yc_launch_monitor.storage.sqlite import CompanyStore, utc_now

logger = logging.getLogger(__name__)

FetchPostsFn = Callable[[], list[dict]]


@dataclass(frozen=True, slots=True)
class XMonitorResult:
    """Summary of an X monitoring run."""

    discovered: int
    relevant_signals: int
    early_signals: int
    already_seen: int
    failed: int


class XMonitor:
    """Monitors X/Twitter for early YC/Speedrun founder announcements."""

    def __init__(
        self,
        settings: Settings,
        store: CompanyStore | None = None,
        fetcher: XFetcher | None = None,
        detector: XSignalDetector | None = None,
        matcher: CompanyConfirmationMatcher | None = None,
        fetch_posts: FetchPostsFn | None = None,
    ) -> None:
        self._settings = settings
        self._store = store or CompanyStore(settings.state_db_path)
        self._fetcher = fetcher or XFetcher(settings)
        self._detector = detector or XSignalDetector()
        self._matcher = matcher or CompanyConfirmationMatcher(self._store)
        self._fetch_posts = fetch_posts

    def run(self, seen_at: datetime | None = None) -> XMonitorResult:
        """Fetch recent X posts, detect signals, match against directory, and persist."""
        seen_at = seen_at or utc_now()
        raw_posts = self._fetch_posts() if self._fetch_posts is not None else self._fetcher.search_recent_posts()

        discovered = len(raw_posts)
        relevant_count = 0
        early_count = 0
        already_seen_count = 0
        failed_count = 0

        connection = self._store.connect()
        try:
            for index, item in enumerate(raw_posts, start=1):
                try:
                    signal = parse_x_post(
                        item,
                        detector=self._detector,
                        require_relevant=True,
                    )
                except XParseError as exc:
                    failed_count += 1
                    logger.warning("Failed to parse X post #%s: %s", index, exc)
                    continue

                # If post does not match any YC/Speedrun acceptance pattern, skip storage
                if signal is None:
                    logger.debug("Post #%s ignored (no relevant YC/Speedrun signal)", index)
                    continue

                relevant_count += 1

                # Classify whether the post is an EARLY signal or already confirmed in directory
                evaluated_signal = self._matcher.evaluate_signal(connection, signal)
                if evaluated_signal.is_early_signal:
                    early_count += 1
                    logger.info(
                        "EARLY YC SIGNAL detected: %s (@%s) -> %s",
                        evaluated_signal.company_name or evaluated_signal.author_name or "Unknown Company",
                        evaluated_signal.author_username,
                        evaluated_signal.signal_reason,
                    )
                else:
                    logger.info(
                        "Confirmed YC social signal: %s (@%s) -> %s",
                        evaluated_signal.company_name or evaluated_signal.author_name or "Confirmed Company",
                        evaluated_signal.author_username,
                        evaluated_signal.signal_reason,
                    )

                status = self._store.save_x_signal(connection, evaluated_signal, seen_at=seen_at)
                if status is XPostStatus.ALREADY_SEEN:
                    already_seen_count += 1

            connection.commit()
        except Exception:
            connection.rollback()
            logger.exception("X monitor run failed; rolled back transaction")
            raise
        finally:
            connection.close()

        result = XMonitorResult(
            discovered=discovered,
            relevant_signals=relevant_count,
            early_signals=early_count,
            already_seen=already_seen_count,
            failed=failed_count,
        )
        logger.info(
            "X monitor complete: discovered=%s relevant_signals=%s early_signals=%s already_seen=%s failed=%s",
            result.discovered,
            result.relevant_signals,
            result.early_signals,
            result.already_seen,
            result.failed,
        )
        return result

    def ingest_signals(
        self,
        signals: list[ParsedXSignal],
        seen_at: datetime | None = None,
    ) -> XMonitorResult:
        """Persist pre-parsed X signals (used by tests and pipelines)."""
        seen_at = seen_at or utc_now()
        early_count = 0
        already_seen_count = 0

        connection = self._store.connect()
        try:
            for signal in signals:
                evaluated_signal = self._matcher.evaluate_signal(connection, signal)
                if evaluated_signal.is_early_signal:
                    early_count += 1

                status = self._store.save_x_signal(connection, evaluated_signal, seen_at=seen_at)
                if status is XPostStatus.ALREADY_SEEN:
                    already_seen_count += 1
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        return XMonitorResult(
            discovered=len(signals),
            relevant_signals=len(signals),
            early_signals=early_count,
            already_seen=already_seen_count,
            failed=0,
        )
