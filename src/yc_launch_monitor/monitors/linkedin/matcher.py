"""Company confirmation matcher to classify LinkedIn signals."""

from __future__ import annotations

import dataclasses
import logging
import sqlite3

from yc_launch_monitor.models.linkedin_signal import (
    LinkedInSignalClassification,
    ParsedLinkedInSignal,
)
from yc_launch_monitor.storage.sqlite import CompanyStore

logger = logging.getLogger(__name__)


class LinkedInCompanyConfirmationMatcher:
    """Matches LinkedIn signal entities against SQLite persistent directory records."""

    def __init__(self, store: CompanyStore) -> None:
        self._store = store

    def evaluate_signal(
        self,
        connection: sqlite3.Connection,
        signal: ParsedLinkedInSignal,
    ) -> ParsedLinkedInSignal:
        """
        Determine if the post is an EARLY_YC_SIGNAL, CONFIRMED_YC, or SPEEDRUN_SIGNAL.

        - If Speedrun -> classification=SPEEDRUN_SIGNAL, is_speedrun_signal=True
        - If YC & confirmed in local SQLite store -> classification=CONFIRMED_YC, is_confirmed_yc=True, is_early_signal=False
        - If YC & NOT confirmed in local SQLite store -> classification=EARLY_YC_SIGNAL, is_confirmed_yc=False, is_early_signal=True
        """
        is_confirmed = False

        # Try matching by extracted company name
        if signal.company_name:
            company = self._store.find_company_by_name(connection, signal.company_name)
            if company is not None:
                is_confirmed = True
                logger.debug(
                    "Matched LinkedIn signal company %r to confirmed YC company %r (%s)",
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
                    "Matched LinkedIn signal author %r to confirmed YC company %r (%s)",
                    signal.author_name,
                    company.name,
                    company.stable_id,
                )

        is_early = not is_confirmed

        if signal.program == "Speedrun":
            classification = LinkedInSignalClassification.SPEEDRUN_SIGNAL
        elif is_confirmed:
            classification = LinkedInSignalClassification.CONFIRMED_YC
        else:
            classification = LinkedInSignalClassification.EARLY_YC_SIGNAL

        return dataclasses.replace(
            signal,
            classification=classification,
            is_confirmed_yc=is_confirmed,
            is_early_signal=is_early,
            is_speedrun_signal=signal.program == "Speedrun",
        )
