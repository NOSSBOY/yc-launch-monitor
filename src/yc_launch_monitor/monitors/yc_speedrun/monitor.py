"""Orchestrates YC Speedrun fetch, parse, and persistence."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Callable

from yc_launch_monitor.config import Settings
from yc_launch_monitor.models.company import CompanyStatus, ParsedCompany
from yc_launch_monitor.monitors.yc_directory.monitor import MonitorResult
from yc_launch_monitor.monitors.yc_speedrun.fetcher import YCSpeedrunFetcher
from yc_launch_monitor.monitors.yc_speedrun.parser import (
    YCSpeedrunParseError,
    parse_speedrun_item,
)
from yc_launch_monitor.storage.sqlite import CompanyStore, utc_now

if TYPE_CHECKING:
    from yc_launch_monitor.alerts.slack import SlackNotifier

logger = logging.getLogger(__name__)

FetchItemsFn = Callable[[], list[dict]]


class YCSpeedrunMonitor:
    """Monitor YC Speedrun directory/page and persist company state."""

    def __init__(
        self,
        settings: Settings,
        store: CompanyStore | None = None,
        fetcher: YCSpeedrunFetcher | None = None,
        fetch_items: FetchItemsFn | None = None,
        notifier: SlackNotifier | None = None,
    ) -> None:
        self._settings = settings
        self._store = store or CompanyStore(settings.state_db_path)
        self._fetcher = fetcher or YCSpeedrunFetcher(settings)
        self._fetch_items = fetch_items
        self._notifier = notifier

    def run(self, seen_at: datetime | None = None) -> MonitorResult:
        """Fetch Speedrun companies, persist them, and return run statistics."""
        seen_at = seen_at or utc_now()
        items = self._fetch_items() if self._fetch_items is not None else self._fetcher.fetch_companies()

        discovered = len(items)
        new_count = 0
        already_seen_count = 0
        failed_count = 0

        connection = self._store.connect()
        try:
            for index, item in enumerate(items, start=1):
                try:
                    company = parse_speedrun_item(item)
                except YCSpeedrunParseError as exc:
                    failed_count += 1
                    logger.warning("Failed to parse Speedrun item #%s: %s", index, exc)
                    continue

                status = self._store.save_company(connection, company, seen_at=seen_at)
                if status is CompanyStatus.NEW:
                    new_count += 1
                    logger.info(
                        "NEW Speedrun company detected: %s (%s)",
                        company.name,
                        company.stable_id,
                    )
                    if self._notifier is not None:
                        try:
                            self._notifier.send_company_alert(company, connection=connection)
                        except Exception as exc:
                            logger.error("Failed to send Slack alert for %s: %s", company.name, exc)
                else:
                    already_seen_count += 1
                    logger.debug(
                        "Already seen Speedrun company: %s (%s)",
                        company.name,
                        company.stable_id,
                    )

            connection.commit()
        except Exception:
            connection.rollback()
            logger.exception("YC Speedrun monitor run failed; rolled back transaction")
            raise
        finally:
            connection.close()

        result = MonitorResult(
            discovered=discovered,
            new=new_count,
            already_seen=already_seen_count,
            failed=failed_count,
        )
        logger.info(
            "YC Speedrun monitor complete: discovered=%s new=%s already_seen=%s failed=%s",
            result.discovered,
            result.new,
            result.already_seen,
            result.failed,
        )
        return result

    def ingest_companies(
        self,
        companies: list[ParsedCompany],
        seen_at: datetime | None = None,
    ) -> MonitorResult:
        """Persist pre-parsed Speedrun companies (used by tests and pipelines)."""
        seen_at = seen_at or utc_now()
        new_count = 0
        already_seen_count = 0

        connection = self._store.connect()
        try:
            for company in companies:
                status = self._store.save_company(connection, company, seen_at=seen_at)
                if status is CompanyStatus.NEW:
                    new_count += 1
                    if self._notifier is not None:
                        try:
                            self._notifier.send_company_alert(company, connection=connection)
                        except Exception as exc:
                            logger.error("Failed to send Slack alert for %s: %s", company.name, exc)
                else:
                    already_seen_count += 1
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        return MonitorResult(
            discovered=len(companies),
            new=new_count,
            already_seen=already_seen_count,
            failed=0,
        )
