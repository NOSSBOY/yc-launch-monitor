"""SQLite persistence for discovered companies."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from yc_launch_monitor.models.company import CompanyRecord, CompanyStatus, ParsedCompany

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
