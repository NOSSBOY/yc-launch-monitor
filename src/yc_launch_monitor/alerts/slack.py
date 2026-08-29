"""Slack alerting integration via Incoming Webhooks."""

from __future__ import annotations

import json
import logging
import sqlite3
import urllib.error
import urllib.request
from typing import Any, Callable

from yc_launch_monitor.config import Settings
from yc_launch_monitor.models.company import (
    SOURCE_YC_DIRECTORY,
    SOURCE_YC_SPEEDRUN,
    CompanyRecord,
    ParsedCompany,
)
from yc_launch_monitor.models.linkedin_signal import (
    LinkedInSignalClassification,
    LinkedInSignalRecord,
    ParsedLinkedInSignal,
)
from yc_launch_monitor.models.x_signal import ParsedXSignal, XSignalRecord
from yc_launch_monitor.storage.sqlite import CompanyStore

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 10.0
TEST_MESSAGE = "YC Launch Monitor Slack integration is working."


def format_company_alert(company: ParsedCompany | CompanyRecord) -> str:
    """Format a Slack alert for a new company."""
    if company.source == SOURCE_YC_SPEEDRUN:
        return (
            "⚡ *NEW SPEEDRUN COMPANY*\n\n"
            f"*Company:* {company.name}\n"
            f"*Batch:* {company.batch or 'Speedrun'}\n"
            f"*Source:* YC Speedrun\n"
            f"*Website:* {company.website or 'N/A'}\n"
            f"*Profile:* {company.yc_profile_url}"
        )

    return (
        "🚀 *NEW YC COMPANY*\n\n"
        f"*Company:* {company.name}\n"
        f"*Batch:* {company.batch or 'Undetermined'}\n"
        f"*Source:* YC Directory\n"
        f"*Website:* {company.website or 'N/A'}\n"
        f"*YC Profile:* {company.yc_profile_url}"
    )


def format_x_signal_alert(signal: ParsedXSignal | XSignalRecord) -> str:
    """Format a Slack alert for an X (Twitter) social signal."""
    if signal.program == "Speedrun":
        header = "⚡ *SPEEDRUN SIGNAL*"
    elif signal.is_early_signal:
        header = "🚨 *EARLY YC SIGNAL*"
    else:
        header = "🚀 *CONFIRMED YC SIGNAL*"

    company_line = signal.company_name or signal.author_name or "Unknown Company"
    author_display = f"{signal.author_name} (@{signal.author_username})" if signal.author_name else f"@{signal.author_username}"
    author_profile = signal.author_url or f"https://x.com/{signal.author_username}"

    lines = [
        header,
        "",
        f"*Company:* {company_line}",
        f"*Batch:* {signal.batch or ('Speedrun' if signal.program == 'Speedrun' else 'Undetermined')}",
        f"*Signal:* {signal.signal_reason or 'Founder announcement'}",
        f"*Source:* X",
        f"*Author:* {author_display}",
        f"*Author Profile:* {author_profile}",
        f"*Post:* {signal.post_url}",
        "",
        f"> {signal.post_text}",
    ]
    return "\n".join(lines)


def format_linkedin_signal_alert(signal: ParsedLinkedInSignal | LinkedInSignalRecord) -> str:
    """Format a Slack alert for a LinkedIn social signal."""
    if signal.is_speedrun_signal or signal.program == "Speedrun":
        header = "⚡ *SPEEDRUN SIGNAL*"
    elif signal.is_early_signal:
        header = "🚨 *EARLY YC SIGNAL*"
    else:
        header = "🚀 *CONFIRMED YC SIGNAL*"

    company_line = signal.company_name or signal.author_name or "Unknown Company"
    author_profile = signal.author_profile_url or "N/A"

    lines = [
        header,
        "",
        f"*Company:* {company_line}",
        f"*Batch:* {signal.batch or ('Speedrun' if signal.program == 'Speedrun' else 'Undetermined')}",
        f"*Signal:* {signal.signal_reason or 'Founder announcement'}",
        f"*Source:* LinkedIn",
        f"*Author:* {signal.author_name}",
        f"*Author Profile:* {author_profile}",
        f"*Post:* {signal.post_url}",
        "",
        f"> {signal.post_text}",
    ]
    return "\n".join(lines)


class SlackNotifier:
    """Sends notifications to Slack via Incoming Webhooks with SQLite deduplication."""

    def __init__(
        self,
        settings: Settings,
        store: CompanyStore | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        http_post_fn: Callable[[str, dict[str, Any], float], bool] | None = None,
    ) -> None:
        self._settings = settings
        self._store = store or CompanyStore(settings.state_db_path)
        self._timeout_seconds = timeout_seconds
        self._http_post_fn = http_post_fn

    @property
    def is_configured(self) -> bool:
        """Return True if a Slack webhook URL is configured."""
        return bool(self._settings.slack_webhook_url)

    def send_message(self, text: str, blocks: list[dict[str, Any]] | None = None) -> bool:
        """Send a raw text message / blocks payload to the configured Slack webhook."""
        webhook_url = self._settings.slack_webhook_url
        if not webhook_url:
            logger.debug("Slack webhook URL not configured; skipping notification.")
            return False

        payload: dict[str, Any] = {"text": text}
        if blocks:
            payload["blocks"] = blocks

        if self._http_post_fn is not None:
            return self._http_post_fn(webhook_url, payload, self._timeout_seconds)

        try:
            req = urllib.request.Request(
                webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self._timeout_seconds) as response:
                if response.status in (200, 204):
                    logger.info("Slack notification sent successfully.")
                    return True
                logger.warning("Slack webhook returned unexpected status %s", response.status)
                return False
        except urllib.error.HTTPError as exc:
            logger.error("Slack webhook HTTP error: %s %s", exc.code, exc.reason)
            return False
        except urllib.error.URLError as exc:
            logger.error("Slack webhook connection error: %s", exc.reason)
            return False
        except TimeoutError:
            logger.error("Slack webhook timed out after %ss", self._timeout_seconds)
            return False
        except Exception as exc:
            logger.error("Unexpected error sending Slack notification: %s", exc)
            return False

    def send_test_message(self) -> bool:
        """Send a test message to verify Slack webhook integration."""
        return self.send_message(TEST_MESSAGE)

    def send_company_alert(
        self,
        company: ParsedCompany | CompanyRecord,
        connection: sqlite3.Connection | None = None,
    ) -> bool:
        """
        Send an alert for a newly detected company if not previously alerted.

        Records the alert in SQLite to prevent duplicate notifications.
        """
        if not self.is_configured:
            return False

        own_connection = connection is None
        conn = connection or self._store.connect()
        try:
            if self._store.has_slack_alert_been_sent(conn, company.stable_id):
                logger.debug("Slack alert already sent for %s; skipping.", company.stable_id)
                return False

            text = format_company_alert(company)
            success = self.send_message(text)
            if success:
                alert_type = (
                    "NEW_SPEEDRUN_COMPANY"
                    if company.source == SOURCE_YC_SPEEDRUN
                    else "NEW_YC_COMPANY"
                )
                self._store.mark_slack_alert_sent(conn, company.stable_id, alert_type)
                if own_connection:
                    conn.commit()
            return success
        finally:
            if own_connection:
                conn.close()

    def send_x_signal_alert(
        self,
        signal: ParsedXSignal | XSignalRecord,
        connection: sqlite3.Connection | None = None,
    ) -> bool:
        """
        Send an alert for a newly detected X social signal if not previously alerted.

        Records the alert in SQLite to prevent duplicate notifications.
        """
        if not self.is_configured:
            return False

        own_connection = connection is None
        conn = connection or self._store.connect()
        try:
            if self._store.has_slack_alert_been_sent(conn, signal.stable_id):
                logger.debug("Slack alert already sent for %s; skipping.", signal.stable_id)
                return False

            text = format_x_signal_alert(signal)
            success = self.send_message(text)
            if success:
                alert_type = (
                    "SPEEDRUN_SIGNAL"
                    if signal.program == "Speedrun"
                    else ("EARLY_YC_SIGNAL" if signal.is_early_signal else "CONFIRMED_YC_SIGNAL")
                )
                self._store.mark_slack_alert_sent(conn, signal.stable_id, alert_type)
                if own_connection:
                    conn.commit()
            return success
        finally:
            if own_connection:
                conn.close()

    def send_linkedin_signal_alert(
        self,
        signal: ParsedLinkedInSignal | LinkedInSignalRecord,
        connection: sqlite3.Connection | None = None,
    ) -> bool:
        """
        Send an alert for a newly detected LinkedIn social signal if not previously alerted.

        Records the alert in SQLite to prevent duplicate notifications.
        """
        if not self.is_configured:
            return False

        own_connection = connection is None
        conn = connection or self._store.connect()
        try:
            if self._store.has_slack_alert_been_sent(conn, signal.stable_id):
                logger.debug("Slack alert already sent for %s; skipping.", signal.stable_id)
                return False

            text = format_linkedin_signal_alert(signal)
            success = self.send_message(text)
            if success:
                alert_type = (
                    "SPEEDRUN_SIGNAL"
                    if (signal.is_speedrun_signal or signal.program == "Speedrun")
                    else ("EARLY_YC_SIGNAL" if signal.is_early_signal else "CONFIRMED_YC_SIGNAL")
                )
                self._store.mark_slack_alert_sent(conn, signal.stable_id, alert_type)
                if own_connection:
                    conn.commit()
            return success
        finally:
            if own_connection:
                conn.close()
