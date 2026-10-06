"""SQLite storage under a local data directory. Re-imports skip a known Message-ID."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

from gradelinktrendline.models import Observation, RawMessage

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    sender TEXT,
    subject TEXT,
    message_date TEXT,
    body_sha256 TEXT NOT NULL,
    ingested_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL,
    student TEXT,
    subject TEXT,
    assignment TEXT,
    category TEXT,
    score REAL,
    points_possible REAL,
    letter TEXT,
    percent REAL,
    percent_source TEXT,
    observed_on TEXT,
    date_source TEXT,
    teacher TEXT,
    confidence REAL NOT NULL,
    pattern_id TEXT,
    needs_review INTEGER NOT NULL,
    review_reasons TEXT NOT NULL,
    notes TEXT NOT NULL,
    unparsed_remainder TEXT NOT NULL,
    FOREIGN KEY(message_id) REFERENCES messages(message_id)
);
"""


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def has_message(self, message_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM messages WHERE message_id = ?",
            (message_id,),
        ).fetchone()
        return row is not None

    def insert(self, raw: RawMessage, observations: list[Observation]) -> bool:
        """Insert a message and its observations. Return False when the Message-ID is already stored."""
        if self.has_message(raw.message_id):
            return False
        ingested = datetime.now(UTC).isoformat()
        message_date = raw.message_date.isoformat() if raw.message_date else None
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO messages (
                    message_id, source, sender, subject, message_date, body_sha256, ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    raw.message_id,
                    raw.source,
                    raw.sender,
                    raw.subject,
                    message_date,
                    raw.body_sha256,
                    ingested,
                ),
            )
            for item in observations:
                self.conn.execute(
                    """
                    INSERT INTO observations (
                        message_id, student, subject, assignment, category, score, points_possible,
                        letter, percent, percent_source, observed_on, date_source, teacher,
                        confidence, pattern_id, needs_review, review_reasons, notes, unparsed_remainder
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.message_id,
                        item.student,
                        item.subject,
                        item.assignment,
                        item.category,
                        item.score,
                        item.points_possible,
                        item.letter,
                        item.percent,
                        item.percent_source,
                        item.observed_on.isoformat() if item.observed_on else None,
                        item.date_source,
                        item.teacher,
                        item.confidence,
                        item.pattern_id,
                        1 if item.needs_review else 0,
                        json.dumps(list(item.review_reasons)),
                        json.dumps(list(item.notes)),
                        item.unparsed_remainder,
                    ),
                )
        return True

    def observation_rows(self) -> list[dict[str, object]]:
        rows = self.conn.execute(
            """
            SELECT
                o.*,
                m.source AS source,
                m.subject AS message_subject,
                m.sender AS sender
            FROM observations o
            JOIN messages m ON m.message_id = o.message_id
            ORDER BY o.id
            """
        ).fetchall()
        return [_decode(row) for row in rows]


def _decode(row: sqlite3.Row) -> dict[str, object]:
    item = dict(row)
    item["needs_review"] = bool(item["needs_review"])
    observed = item.get("observed_on")
    if isinstance(observed, str) and observed:
        item["observed_on"] = date.fromisoformat(observed)
    item["review_reasons"] = json.loads(item["review_reasons"])
    item["notes"] = json.loads(item["notes"])
    return item
