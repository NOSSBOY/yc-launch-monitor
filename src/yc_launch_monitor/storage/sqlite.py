"""SQLite persistence for discovered companies."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from yc_launch_monitor.models.company import CompanyRecord, CompanyStatus, ParsedCompany
from yc_launch_monitor.models.linkedin_signal import (
    LinkedInPostStatus,
    LinkedInSignalRecord,
    ParsedLinkedInSignal,
)
from yc_launch_monitor.models.x_signal import ParsedXSignal, XPostStatus, XSignalRecord

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    stable_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    yc_profile_url TEXT NOT NULL,
    description TEXT,
    batch TEXT,
    website TEXT,
    category TEXT,
    source TEXT NOT NULL,
    first_detected_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_companies_profile_url
    ON companies(yc_profile_url);

CREATE TABLE IF NOT EXISTS x_signals (
    stable_id TEXT PRIMARY KEY,
    post_id TEXT NOT NULL,
    author_name TEXT,
    author_username TEXT NOT NULL,
    author_url TEXT,
    company_name TEXT,
    batch TEXT,
    program TEXT NOT NULL,
    post_text TEXT NOT NULL,
    post_url TEXT NOT NULL,
    source TEXT NOT NULL,
    is_early_signal INTEGER NOT NULL,
    is_confirmed_yc INTEGER NOT NULL,
    signal_reason TEXT,
    detected_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_x_signals_username
    ON x_signals(author_username);
CREATE INDEX IF NOT EXISTS idx_x_signals_company_name
    ON x_signals(company_name);
CREATE INDEX IF NOT EXISTS idx_x_signals_is_early
    ON x_signals(is_early_signal);

CREATE TABLE IF NOT EXISTS linkedin_signals (
    stable_id TEXT PRIMARY KEY,
    post_id TEXT NOT NULL,
    author_name TEXT NOT NULL,
    author_profile_url TEXT,
    author_urn TEXT,
    company_name TEXT,
    batch TEXT,
    program TEXT NOT NULL,
    post_text TEXT NOT NULL,
    post_url TEXT NOT NULL,
    source TEXT NOT NULL,
    classification TEXT NOT NULL,
    is_early_signal INTEGER NOT NULL,
    is_confirmed_yc INTEGER NOT NULL,
    is_speedrun_signal INTEGER NOT NULL,
    signal_reason TEXT,
    detected_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_linkedin_signals_post_id
    ON linkedin_signals(post_id);
CREATE INDEX IF NOT EXISTS idx_linkedin_signals_author_name
    ON linkedin_signals(author_name);
CREATE INDEX IF NOT EXISTS idx_linkedin_signals_company_name
    ON linkedin_signals(company_name);
CREATE INDEX IF NOT EXISTS idx_linkedin_signals_classification
    ON linkedin_signals(classification);
CREATE INDEX IF NOT EXISTS idx_linkedin_signals_is_early
    ON linkedin_signals(is_early_signal);
"""


def utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


def format_timestamp(value: datetime) -> str:
    """Serialize a datetime as ISO-8601 UTC."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def parse_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp from SQLite."""
    return datetime.fromisoformat(value)


class CompanyStore:
    """SQLite-backed store for YC Directory companies."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    @property
    def db_path(self) -> Path:
        return self._db_path

    def connect(self) -> sqlite3.Connection:
        """Open a SQLite connection with schema initialized."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        connection.executescript(SCHEMA)
        return connection

    def get_by_stable_id(self, connection: sqlite3.Connection, stable_id: str) -> CompanyRecord | None:
        """Fetch a company by stable identifier."""
        row = connection.execute(
            "SELECT * FROM companies WHERE stable_id = ?",
            (stable_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def save_company(
        self,
        connection: sqlite3.Connection,
        company: ParsedCompany,
        seen_at: datetime | None = None,
    ) -> CompanyStatus:
        """
        Insert a new company or update an existing one.

        Existing rows are matched by stable_id and only update mutable fields
        plus last_seen_at. first_detected_at is preserved.
        """
        seen_at = seen_at or utc_now()
        existing = self.get_by_stable_id(connection, company.stable_id)

        if existing is None:
            connection.execute(
                """
                INSERT INTO companies (
                    stable_id,
                    name,
                    yc_profile_url,
                    description,
                    batch,
                    website,
                    category,
                    source,
                    first_detected_at,
                    last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company.stable_id,
                    company.name,
                    company.yc_profile_url,
                    company.description,
                    company.batch,
                    company.website,
                    company.category,
                    company.source,
                    format_timestamp(seen_at),
                    format_timestamp(seen_at),
                ),
            )
            logger.debug("Inserted new company: %s", company.stable_id)
            return CompanyStatus.NEW

        connection.execute(
            """
            UPDATE companies
            SET name = ?,
                yc_profile_url = ?,
                description = ?,
                batch = ?,
                website = ?,
                category = ?,
                source = ?,
                last_seen_at = ?
            WHERE stable_id = ?
            """,
            (
                company.name,
                company.yc_profile_url,
                company.description,
                company.batch,
                company.website,
                company.category,
                company.source,
                format_timestamp(seen_at),
                company.stable_id,
            ),
        )
        logger.debug("Updated existing company: %s", company.stable_id)
        return CompanyStatus.ALREADY_SEEN

    def count_companies(self, connection: sqlite3.Connection) -> int:
        """Return the total number of stored companies."""
        row = connection.execute("SELECT COUNT(*) AS count FROM companies").fetchone()
        return int(row["count"])

    def find_company_by_name(self, connection: sqlite3.Connection, name: str) -> CompanyRecord | None:
        """Look up a company in the store by name or slug."""
        clean = name.strip()
        if not clean:
            return None

        # Exact case-insensitive match on name
        row = connection.execute(
            "SELECT * FROM companies WHERE LOWER(TRIM(name)) = LOWER(?)",
            (clean,),
        ).fetchone()
        if row is not None:
            return self._row_to_record(row)

        # Match against stable ID slug variants (yc-dir:{slug}, yc-sr:{slug})
        slug_clean = clean.lower().replace(" ", "-")
        row = connection.execute(
            "SELECT * FROM companies WHERE stable_id IN (?, ?)",
            (f"yc-dir:{slug_clean}", f"yc-sr:{slug_clean}"),
        ).fetchone()
        if row is not None:
            return self._row_to_record(row)

        return None

    def get_x_signal_by_stable_id(
        self, connection: sqlite3.Connection, stable_id: str
    ) -> XSignalRecord | None:
        """Fetch an X signal record by stable identifier."""
        row = connection.execute(
            "SELECT * FROM x_signals WHERE stable_id = ?",
            (stable_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_x_signal_record(row)

    def save_x_signal(
        self,
        connection: sqlite3.Connection,
        signal: ParsedXSignal,
        seen_at: datetime | None = None,
    ) -> XPostStatus:
        """
        Insert a new X signal or update last_seen_at for an existing post.

        Preserves the original detected_at on subsequent encounters.
        """
        seen_at = seen_at or signal.detected_at or utc_now()
        existing = self.get_x_signal_by_stable_id(connection, signal.stable_id)

        if existing is None:
            connection.execute(
                """
                INSERT INTO x_signals (
                    stable_id,
                    post_id,
                    author_name,
                    author_username,
                    author_url,
                    company_name,
                    batch,
                    program,
                    post_text,
                    post_url,
                    source,
                    is_early_signal,
                    is_confirmed_yc,
                    signal_reason,
                    detected_at,
                    last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.stable_id,
                    signal.post_id,
                    signal.author_name,
                    signal.author_username,
                    signal.author_url,
                    signal.company_name,
                    signal.batch,
                    signal.program,
                    signal.post_text,
                    signal.post_url,
                    signal.source,
                    1 if signal.is_early_signal else 0,
                    1 if signal.is_confirmed_yc else 0,
                    signal.signal_reason,
                    format_timestamp(seen_at),
                    format_timestamp(seen_at),
                ),
            )
            logger.debug("Inserted new X signal: %s", signal.stable_id)
            return XPostStatus.NEW

        connection.execute(
            """
            UPDATE x_signals
            SET author_name = ?,
                author_username = ?,
                author_url = ?,
                company_name = ?,
                batch = ?,
                program = ?,
                post_text = ?,
                post_url = ?,
                source = ?,
                is_early_signal = ?,
                is_confirmed_yc = ?,
                signal_reason = ?,
                last_seen_at = ?
            WHERE stable_id = ?
            """,
            (
                signal.author_name,
                signal.author_username,
                signal.author_url,
                signal.company_name,
                signal.batch,
                signal.program,
                signal.post_text,
                signal.post_url,
                signal.source,
                1 if signal.is_early_signal else 0,
                1 if signal.is_confirmed_yc else 0,
                signal.signal_reason,
                format_timestamp(seen_at),
                signal.stable_id,
            ),
        )
        logger.debug("Updated existing X signal: %s", signal.stable_id)
        return XPostStatus.ALREADY_SEEN

    def count_x_signals(self, connection: sqlite3.Connection) -> int:
        """Return the total number of stored X signals."""
        row = connection.execute("SELECT COUNT(*) AS count FROM x_signals").fetchone()
        return int(row["count"])

    def get_linkedin_signal_by_stable_id(
        self, connection: sqlite3.Connection, stable_id: str
    ) -> LinkedInSignalRecord | None:
        """Fetch a LinkedIn signal record by stable identifier."""
        row = connection.execute(
            "SELECT * FROM linkedin_signals WHERE stable_id = ?",
            (stable_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_linkedin_signal_record(row)

    def save_linkedin_signal(
        self,
        connection: sqlite3.Connection,
        signal: ParsedLinkedInSignal,
        seen_at: datetime | None = None,
    ) -> LinkedInPostStatus:
        """
        Insert a new LinkedIn signal or update last_seen_at for an existing post.

        Preserves the original detected_at on subsequent encounters.
        """
        seen_at = seen_at or signal.detected_at or utc_now()
        existing = self.get_linkedin_signal_by_stable_id(connection, signal.stable_id)

        if existing is None:
            connection.execute(
                """
                INSERT INTO linkedin_signals (
                    stable_id,
                    post_id,
                    author_name,
                    author_profile_url,
                    author_urn,
                    company_name,
                    batch,
                    program,
                    post_text,
                    post_url,
                    source,
                    classification,
                    is_early_signal,
                    is_confirmed_yc,
                    is_speedrun_signal,
                    signal_reason,
                    detected_at,
                    last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.stable_id,
                    signal.post_id,
                    signal.author_name,
                    signal.author_profile_url,
                    signal.author_urn,
                    signal.company_name,
                    signal.batch,
                    signal.program,
                    signal.post_text,
                    signal.post_url,
                    signal.source,
                    str(
                        signal.classification.value
                        if hasattr(signal.classification, "value")
                        else signal.classification
                    ),
                    1 if signal.is_early_signal else 0,
                    1 if signal.is_confirmed_yc else 0,
                    1 if signal.is_speedrun_signal else 0,
                    signal.signal_reason,
                    format_timestamp(seen_at),
                    format_timestamp(seen_at),
                ),
            )
            logger.debug("Inserted new LinkedIn signal: %s", signal.stable_id)
            return LinkedInPostStatus.NEW

        connection.execute(
            """
            UPDATE linkedin_signals
            SET author_name = ?,
                author_profile_url = ?,
                author_urn = ?,
                company_name = ?,
                batch = ?,
                program = ?,
                post_text = ?,
                post_url = ?,
                source = ?,
                classification = ?,
                is_early_signal = ?,
                is_confirmed_yc = ?,
                is_speedrun_signal = ?,
                signal_reason = ?,
                last_seen_at = ?
            WHERE stable_id = ?
            """,
            (
                signal.author_name,
                signal.author_profile_url,
                signal.author_urn,
                signal.company_name,
                signal.batch,
                signal.program,
                signal.post_text,
                signal.post_url,
                signal.source,
                str(
                    signal.classification.value
                    if hasattr(signal.classification, "value")
                    else signal.classification
                ),
                1 if signal.is_early_signal else 0,
                1 if signal.is_confirmed_yc else 0,
                1 if signal.is_speedrun_signal else 0,
                signal.signal_reason,
                format_timestamp(seen_at),
                signal.stable_id,
            ),
        )
        logger.debug("Updated existing LinkedIn signal: %s", signal.stable_id)
        return LinkedInPostStatus.ALREADY_SEEN

    def count_linkedin_signals(self, connection: sqlite3.Connection) -> int:
        """Return the total number of stored LinkedIn signals."""
        row = connection.execute("SELECT COUNT(*) AS count FROM linkedin_signals").fetchone()
        return int(row["count"])

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> CompanyRecord:
        return CompanyRecord(
            stable_id=row["stable_id"],
            name=row["name"],
            yc_profile_url=row["yc_profile_url"],
            description=row["description"],
            batch=row["batch"],
            website=row["website"],
            category=row["category"],
            source=row["source"],
            first_detected_at=parse_timestamp(row["first_detected_at"]),
            last_seen_at=parse_timestamp(row["last_seen_at"]),
        )

    @staticmethod
    def _row_to_x_signal_record(row: sqlite3.Row) -> XSignalRecord:
        return XSignalRecord(
            stable_id=row["stable_id"],
            post_id=row["post_id"],
            author_username=row["author_username"],
            post_text=row["post_text"],
            post_url=row["post_url"],
            author_name=row["author_name"],
            author_url=row["author_url"],
            company_name=row["company_name"],
            batch=row["batch"],
            program=row["program"],
            source=row["source"],
            is_early_signal=bool(row["is_early_signal"]),
            is_confirmed_yc=bool(row["is_confirmed_yc"]),
            signal_reason=row["signal_reason"],
            detected_at=parse_timestamp(row["detected_at"]),
            last_seen_at=parse_timestamp(row["last_seen_at"]),
        )

    @staticmethod
    def _row_to_linkedin_signal_record(row: sqlite3.Row) -> LinkedInSignalRecord:
        return LinkedInSignalRecord(
            stable_id=row["stable_id"],
            post_id=row["post_id"],
            author_name=row["author_name"],
            post_text=row["post_text"],
            post_url=row["post_url"],
            author_profile_url=row["author_profile_url"],
            author_urn=row["author_urn"],
            company_name=row["company_name"],
            batch=row["batch"],
            program=row["program"],
            source=row["source"],
            classification=row["classification"],
            is_early_signal=bool(row["is_early_signal"]),
            is_confirmed_yc=bool(row["is_confirmed_yc"]),
            is_speedrun_signal=bool(row["is_speedrun_signal"]),
            signal_reason=row["signal_reason"],
            detected_at=parse_timestamp(row["detected_at"]),
            last_seen_at=parse_timestamp(row["last_seen_at"]),
        )


