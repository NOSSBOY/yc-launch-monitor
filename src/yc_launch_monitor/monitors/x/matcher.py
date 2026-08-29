"""Company confirmation matcher to classify X signals as EARLY vs CONFIRMED."""

from __future__ import annotations

import dataclasses
import logging
import sqlite3

from yc_launch_monitor.models.x_signal import ParsedXSignal
from yc_launch_monitor.storage.sqlite import CompanyStore

logger = logging.getLogger(__name__)


class CompanyConfirmationMatcher:
    """Matches X signal entities against SQLite persistent directory records."""

    def __init__(self, store: CompanyStore) -> None:
        self._store = store

    def evaluate_signal(
        self,
        connection: sqlite3.Connection,
        signal: ParsedXSignal,
    ) -> ParsedXSignal:
        """
        Determine if the post is an EARLY YC signal or a CONFIRMED directory signal.

        - If the company is already confirmed in the local SQLite store -> is_confirmed_yc=True, is_early_signal=False
        - If the company is NOT confirmed in the local SQLite store -> is_confirmed_yc=False, is_early_signal=True
        """
        is_confirmed = False

        # Try matching by extracted company name
        if signal.company_name:
            company = self._store.find_company_by_name(connection, signal.company_name)
            if company is not None:
                is_confirmed = True
                logger.debug(
                    "Matched signal company %r to confirmed YC company %r (%s)",
                    signal.company_name,
                    company.name,
                    company.stable_id,
                )

        # Try matching by author display name if not yet confirmed
        if not is_confirmed and signal.author_name:
            company = self._store.find_company_by_name(connection, signal.author_name)
            if company is not None:
                is_confirmed = True
                logger.debug(
                    "Matched signal author %r to confirmed YC company %r (%s)",
                    signal.author_name,
                    company.name,
                    company.stable_id,
                )

        is_early = not is_confirmed

        return dataclasses.replace(
            signal,
            is_confirmed_yc=is_confirmed,
            is_early_signal=is_early,
        )
