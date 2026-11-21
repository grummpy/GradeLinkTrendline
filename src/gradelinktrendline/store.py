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

CREATE TABLE IF NOT EXISTS review_resolutions (
    observation_id INTEGER PRIMARY KEY,
    student TEXT NOT NULL,
    subject TEXT NOT NULL,
    assignment TEXT,
    category TEXT,
    percent REAL,
    letter TEXT,
    observed_on TEXT NOT NULL,
    teacher TEXT,
    rationale TEXT NOT NULL,
    resolved_at TEXT NOT NULL,
    FOREIGN KEY(observation_id) REFERENCES observations(id)
);
"""

_VALID_LETTERS = {"A", "A+", "A-", "B", "B+", "B-", "C", "C+", "C-", "D", "D+", "D-", "F"}


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
                m.sender AS sender,
                r.observation_id AS resolution_id,
                r.student AS resolved_student,
                r.subject AS resolved_subject,
                r.assignment AS resolved_assignment,
                r.category AS resolved_category,
                r.percent AS resolved_percent,
                r.letter AS resolved_letter,
                r.observed_on AS resolved_observed_on,
                r.teacher AS resolved_teacher,
                r.rationale AS resolution_rationale,
                r.resolved_at AS resolved_at
            FROM observations o
            JOIN messages m ON m.message_id = o.message_id
            LEFT JOIN review_resolutions r ON r.observation_id = o.id
            ORDER BY o.id
            """
        ).fetchall()
        return [_decode(row) for row in rows]

    def review_rows(self) -> list[dict[str, object]]:
        """Return only unresolved parser output, retaining its original reasons."""
        return [row for row in self.observation_rows() if row["needs_review"]]

    def resolve_review(
        self,
        observation_id: int,
        *,
        student: str,
        subject: str,
        observed_on: date,
        percent: float | None,
        letter: str | None,
        rationale: str,
        assignment: str | None = None,
        category: str | None = None,
        teacher: str | None = None,
    ) -> None:
        """Store a local, explicit resolution without overwriting parsed evidence.

        Resolutions are intentionally a side table. The parser's original fields,
        review reasons, and raw message remain available in ``observations``.
        """
        original = self.conn.execute(
            "SELECT needs_review, assignment, category, teacher FROM observations WHERE id = ?", (observation_id,)
        ).fetchone()
        if original is None:
            raise ValueError(f"review observation {observation_id} does not exist")
        if not original["needs_review"] and not self.conn.execute(
            "SELECT 1 FROM review_resolutions WHERE observation_id = ?", (observation_id,)
        ).fetchone():
            raise ValueError(f"observation {observation_id} is already confirmed; only review items can be resolved")
        if not student.strip() or not subject.strip() or not rationale.strip():
            raise ValueError("student, subject, and rationale are required to resolve a review item")
        if (percent is None) == (letter is None):
            raise ValueError("provide exactly one final grade signal: percent or letter")
        if percent is not None and not 0 <= percent <= 100:
            raise ValueError("percent must be between 0 and 100")
        if letter is not None and letter.upper() not in _VALID_LETTERS:
            raise ValueError("letter must be A through F with an optional + or -")
        assignment = assignment if assignment is not None else original["assignment"]
        category = category if category is not None else original["category"]
        teacher = teacher if teacher is not None else original["teacher"]

        with self.conn:
            self.conn.execute(
                """
                INSERT INTO review_resolutions (
                    observation_id, student, subject, assignment, category, percent, letter,
                    observed_on, teacher, rationale, resolved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(observation_id) DO UPDATE SET
                    student = excluded.student,
                    subject = excluded.subject,
                    assignment = excluded.assignment,
                    category = excluded.category,
                    percent = excluded.percent,
                    letter = excluded.letter,
                    observed_on = excluded.observed_on,
                    teacher = excluded.teacher,
                    rationale = excluded.rationale,
                    resolved_at = excluded.resolved_at
                """,
                (
                    observation_id,
                    student.strip(),
                    subject.strip(),
                    _clean_optional(assignment),
                    _clean_optional(category),
                    percent,
                    letter.upper() if letter else None,
                    observed_on.isoformat(),
                    _clean_optional(teacher),
                    rationale.strip(),
                    datetime.now(UTC).isoformat(),
                ),
            )


def _decode(row: sqlite3.Row) -> dict[str, object]:
    item = dict(row)
    item["needs_review"] = bool(item["needs_review"])
    observed = item.get("observed_on")
    if isinstance(observed, str) and observed:
        item["observed_on"] = date.fromisoformat(observed)
    item["review_reasons"] = json.loads(item["review_reasons"])
    item["notes"] = json.loads(item["notes"])
    if item.pop("resolution_id") is not None:
        item["original_review_reasons"] = list(item["review_reasons"])
        item["needs_review"] = False
        item["review_reasons"] = []
        item["student"] = item.pop("resolved_student")
        item["subject"] = item.pop("resolved_subject")
        item["assignment"] = item.pop("resolved_assignment")
        item["category"] = item.pop("resolved_category")
        item["percent"] = item.pop("resolved_percent")
        item["letter"] = item.pop("resolved_letter")
        item["observed_on"] = date.fromisoformat(str(item.pop("resolved_observed_on")))
        item["date_source"] = "local-review-resolution"
        item["teacher"] = item.pop("resolved_teacher")
        rationale = str(item.pop("resolution_rationale"))
        item["notes"].append(f"Locally resolved review item: {rationale}")
        item["review_resolution"] = {"rationale": rationale, "resolved_at": item.pop("resolved_at")}
    else:
        for key in (
            "resolved_student",
            "resolved_subject",
            "resolved_assignment",
            "resolved_category",
            "resolved_percent",
            "resolved_letter",
            "resolved_observed_on",
            "resolved_teacher",
            "resolution_rationale",
            "resolved_at",
        ):
            item.pop(key)
    return item


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
