"""Shared records for raw mail and parsed observations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True)
class RawMessage:
    message_id: str
    source: str
    sender: str
    subject: str
    message_date: datetime | None
    body_text: str
    body_html: str
    body_sha256: str


@dataclass
class Candidate:
    """One pattern's reading of a message. Null fields were not found."""

    pattern_id: str
    student: str | None = None
    subject: str | None = None
    assignment: str | None = None
    category: str | None = None
    score: float | None = None
    points_possible: float | None = None
    letter: str | None = None
    percent: float | None = None
    percent_source: str | None = None
    observed_on: date | None = None
    date_source: str | None = None
    teacher: str | None = None
    consumed_lines: frozenset[int] = field(default_factory=frozenset)
    notes: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    block_header_date: bool = False


@dataclass(frozen=True)
class Observation:
    message_id: str
    student: str | None
    subject: str | None
    assignment: str | None
    category: str | None
    score: float | None
    points_possible: float | None
    letter: str | None
    percent: float | None
    percent_source: str | None
    observed_on: date | None
    date_source: str | None
    teacher: str | None
    confidence: float
    pattern_id: str
    needs_review: bool
    review_reasons: tuple[str, ...]
    notes: tuple[str, ...]
    unparsed_remainder: str
