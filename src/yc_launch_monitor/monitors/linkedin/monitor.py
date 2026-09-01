"""Orchestrates LinkedIn post retrieval, signal parsing, early detection, and persistence."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Callable

from yc_launch_monitor.config import Settings
from yc_launch_monitor.models.linkedin_signal import (
    LinkedInPostStatus,
    LinkedInSignalClassification,
    ParsedLinkedInSignal,
)
from yc_launch_monitor.monitors.linkedin.detector import LinkedInSignalDetector
from yc_launch_monitor.monitors.linkedin.fetcher import LinkedInFetchError, LinkedInFetcher
from yc_launch_monitor.monitors.linkedin.matcher import LinkedInCompanyConfirmationMatcher
from yc_launch_monitor.monitors.linkedin.parser import LinkedInParseError, parse_linkedin_post
from yc_launch_monitor.storage.sqlite import CompanyStore, utc_now

if TYPE_CHECKING:
    from yc_launch_monitor.alerts.slack import SlackNotifier

logger = logging.getLogger(__name__)

FetchLinkedInPostsFn = Callable[[], list[dict]]


@dataclass(frozen=True, slots=True)
class LinkedInMonitorResult:
    """Summary of a LinkedIn monitoring run."""

    discovered: int
    relevant_signals: int
    early_signals: int
    speedrun_signals: int
    confirmed_yc: int
    already_seen: int
    failed: int


class LinkedInMonitor:
    """Monitors LinkedIn for early YC/Speedrun founder announcements and launches."""

    def __init__(
        self,
        settings: Settings,
        store: CompanyStore | None = None,
        fetcher: LinkedInFetcher | None = None,
        detector: LinkedInSignalDetector | None = None,
        matcher: LinkedInCompanyConfirmationMatcher | None = None,
        fetch_posts: FetchLinkedInPostsFn | None = None,
        notifier: SlackNotifier | None = None,
    ) -> None:
        self._settings = settings
        self._store = store or CompanyStore(settings.state_db_path)
        self._fetcher = fetcher or LinkedInFetcher(settings)
        self._detector = detector or LinkedInSignalDetector()
        self._matcher = matcher or LinkedInCompanyConfirmationMatcher(self._store)
        self._fetch_posts = fetch_posts
        self._notifier = notifier

    def run(self, seen_at: datetime | None = None) -> LinkedInMonitorResult:
        """Fetch recent LinkedIn posts, detect signals, match against directory, and persist."""
        seen_at = seen_at or utc_now()
        try:
            raw_posts = (
                self._fetch_posts()
                if self._fetch_posts is not None
                else self._fetcher.fetch_recent_posts()
            )
        except LinkedInFetchError as exc:
            logger.warning('LinkedIn monitor skipped this cycle: %s', exc)
            return LinkedInMonitorResult(0, 0, 0, 0, 0, 0, 0)

        discovered = len(raw_posts)
        relevant_count = 0
        early_count = 0
        speedrun_count = 0
        confirmed_count = 0
        already_seen_count = 0
        failed_count = 0

        connection = self._store.connect()
        try:
            for index, item in enumerate(raw_posts, start=1):
                try:
                    signal = parse_linkedin_post(
                        item,
                        detector=self._detector,
                        require_relevant=True,
                    )
                except LinkedInParseError as exc:
                    failed_count += 1
                    logger.warning("Failed to parse LinkedIn post #%s: %s", index, exc)
                    continue

                if signal is None:
                    logger.debug("LinkedIn post #%s ignored (no relevant signal)", index)
                    continue

                relevant_count += 1

                # Classify signal against SQLite directory
                evaluated_signal = self._matcher.evaluate_signal(connection, signal)

                if evaluated_signal.classification == LinkedInSignalClassification.SPEEDRUN_SIGNAL:
                    speedrun_count += 1
                    logger.info(
                        "SPEEDRUN SIGNAL detected: %s (%s) -> %s",
                        evaluated_signal.company_name or evaluated_signal.author_name,
                        evaluated_signal.post_id,
                        evaluated_signal.signal_reason,
                    )
                elif evaluated_signal.classification == LinkedInSignalClassification.EARLY_YC_SIGNAL:
                    early_count += 1
                    logger.info(
                        "EARLY YC SIGNAL detected: %s (%s) -> %s",
                        evaluated_signal.company_name or evaluated_signal.author_name,
                        evaluated_signal.post_id,
                        evaluated_signal.signal_reason,
                    )
                elif evaluated_signal.classification == LinkedInSignalClassification.CONFIRMED_YC:
                    confirmed_count += 1
                    logger.info(
                        "Confirmed YC LinkedIn signal: %s (%s) -> %s",
                        evaluated_signal.company_name or evaluated_signal.author_name,
                        evaluated_signal.post_id,
                        evaluated_signal.signal_reason,
                    )

                status = self._store.save_linkedin_signal(
                    connection, evaluated_signal, seen_at=seen_at
                )
                if status is LinkedInPostStatus.ALREADY_SEEN:
                    already_seen_count += 1
                elif status is LinkedInPostStatus.NEW:
                    if self._notifier is not None:
                        try:
                            self._notifier.send_linkedin_signal_alert(evaluated_signal, connection=connection)
                        except Exception as exc:
                            logger.error("Failed to send Slack alert for LinkedIn signal %s: %s", evaluated_signal.stable_id, exc)

            connection.commit()
        except Exception:
            connection.rollback()
            logger.exception("LinkedIn monitor run failed; rolled back transaction")
            raise
        finally:
            connection.close()

        result = LinkedInMonitorResult(
            discovered=discovered,
            relevant_signals=relevant_count,
            early_signals=early_count,
            speedrun_signals=speedrun_count,
            confirmed_yc=confirmed_count,
            already_seen=already_seen_count,
            failed=failed_count,
        )
        logger.info(
            "LinkedIn monitor complete: discovered=%s relevant_signals=%s early_signals=%s "
            "speedrun_signals=%s confirmed_yc=%s already_seen=%s failed=%s",
            result.discovered,
            result.relevant_signals,
            result.early_signals,
            result.speedrun_signals,
            result.confirmed_yc,
            result.already_seen,
            result.failed,
        )
        return result

    def ingest_signals(
        self,
        signals: list[ParsedLinkedInSignal],
        seen_at: datetime | None = None,
    ) -> LinkedInMonitorResult:
        """Persist pre-parsed LinkedIn signals (used by tests and pipelines)."""
        seen_at = seen_at or utc_now()
        early_count = 0
        speedrun_count = 0
        confirmed_count = 0
        already_seen_count = 0

        connection = self._store.connect()
        try:
            for signal in signals:
                evaluated_signal = self._matcher.evaluate_signal(connection, signal)
                if evaluated_signal.classification == LinkedInSignalClassification.SPEEDRUN_SIGNAL:
                    speedrun_count += 1
                elif evaluated_signal.classification == LinkedInSignalClassification.EARLY_YC_SIGNAL:
                    early_count += 1
                elif evaluated_signal.classification == LinkedInSignalClassification.CONFIRMED_YC:
                    confirmed_count += 1

                status = self._store.save_linkedin_signal(
                    connection, evaluated_signal, seen_at=seen_at
                )
                if status is LinkedInPostStatus.ALREADY_SEEN:
                    already_seen_count += 1
                elif status is LinkedInPostStatus.NEW:
                    if self._notifier is not None:
                        try:
                            self._notifier.send_linkedin_signal_alert(evaluated_signal, connection=connection)
                        except Exception as exc:
                            logger.error("Failed to send Slack alert for LinkedIn signal %s: %s", evaluated_signal.stable_id, exc)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        return LinkedInMonitorResult(
            discovered=len(signals),
            relevant_signals=len(signals),
            early_signals=early_count,
            speedrun_signals=speedrun_count,
            confirmed_yc=confirmed_count,
            already_seen=already_seen_count,
            failed=0,
        )
