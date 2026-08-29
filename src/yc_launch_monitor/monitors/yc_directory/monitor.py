"""Orchestrates YC Directory fetch, parse, and persistence."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from yc_launch_monitor.config import Settings
from yc_launch_monitor.models.company import CompanyStatus, ParsedCompany
from yc_launch_monitor.monitors.yc_directory.fetcher import YCDirectoryFetcher
from yc_launch_monitor.monitors.yc_directory.parser import (
    YCDirectoryParseError,
    parse_algolia_hit,
)
from yc_launch_monitor.storage.sqlite import CompanyStore, utc_now

logger = logging.getLogger(__name__)

FetchHitsFn = Callable[[], list[dict]]


@dataclass(frozen=True, slots=True)
class MonitorResult:
    """Summary of one YC Directory monitor run."""

    discovered: int
    new: int
    already_seen: int
    failed: int


class YCDirectoryMonitor:
    """Monitor https://www.ycombinator.com/companies and persist company state."""

    def __init__(
        self,
        settings: Settings,
        store: CompanyStore | None = None,
        fetcher: YCDirectoryFetcher | None = None,
        fetch_hits: FetchHitsFn | None = None,
    ) -> None:
        self._settings = settings
        self._store = store or CompanyStore(settings.state_db_path)
        self._fetcher = fetcher or YCDirectoryFetcher(settings)
        self._fetch_hits = fetch_hits

    def run(self, seen_at: datetime | None = None) -> MonitorResult:
        """Fetch companies, persist them, and return run statistics."""
        seen_at = seen_at or utc_now()
        hits = self._fetch_hits() if self._fetch_hits is not None else self._fetcher.fetch_company_pages()

        discovered = len(hits)
        new_count = 0
        already_seen_count = 0
        failed_count = 0

        connection = self._store.connect()
        try:
            for index, hit in enumerate(hits, start=1):
                try:
                    company = parse_algolia_hit(hit)
                except YCDirectoryParseError as exc:
                    failed_count += 1
                    logger.warning("Failed to parse company hit #%s: %s", index, exc)
                    continue

                status = self._store.save_company(connection, company, seen_at=seen_at)
                if status is CompanyStatus.NEW:
                    new_count += 1
                    logger.info("NEW company detected: %s (%s)", company.name, company.stable_id)
                else:
                    already_seen_count += 1
                    logger.debug("Already seen company: %s (%s)", company.name, company.stable_id)

            connection.commit()
        except Exception:
            connection.rollback()
            logger.exception("YC Directory monitor run failed; rolled back transaction")
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
            "YC Directory monitor complete: discovered=%s new=%s already_seen=%s failed=%s",
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
        """Persist pre-parsed companies (used by tests and future pipelines)."""
        seen_at = seen_at or utc_now()
        new_count = 0
        already_seen_count = 0

        connection = self._store.connect()
        try:
            for company in companies:
                status = self._store.save_company(connection, company, seen_at=seen_at)
                if status is CompanyStatus.NEW:
                    new_count += 1
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
