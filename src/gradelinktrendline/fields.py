"""Field parsers shared by pluggable patterns.

A value is stored only when a pattern names it. Percents are never inferred
from letter grades. Numeric dates that are valid both ways are left empty.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

ALIASES: dict[str, str] = {
    "student": "student",
    "student name": "student",
    "learner": "student",
    "course": "subject",
    "subject": "subject",
    "class": "subject",
    "teacher": "teacher",
    "instructor": "teacher",
    "assignment": "assignment",
    "assignment title": "assignment",
    "work item": "assignment",
    "category": "category",
    "grade category": "category",
    "score": "score",
    "points": "score",
    "points earned": "score",
    "letter": "letter",
    "letter grade": "letter",
    "grade letter": "letter",
    "percent": "percent",
    "percentage": "percent",
    "date": "date",
    "posted": "date",
    "recorded on": "date",
    "date recorded": "date",
}

_LETTER = re.compile(r"^[A-F][+-]?$")
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent\b)", re.IGNORECASE)
_PERCENT_EXACT = re.compile(r"\s*(\d+(?:\.\d+)?)\s*(?:%|percent)\s*$", re.IGNORECASE)
_FRACTION = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:/|out of|of)\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_NUMERIC_DATE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
_MONTH_FORMATS = ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y")


@dataclass
class PointsParse:
    score: float | None = None
    points_possible: float | None = None
    percent: float | None = None
    percent_source: str | None = None
    letter: str | None = None
    notes: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)


@dataclass
class DateParse:
    value: date | None = None
    notes: list[str] = field(default_factory=list)
    # True when a date token was present but not stored.
    blocked: bool = False


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def clean_student(raw: str) -> str | None:
    text = normalize_space(raw)
    if not text or len(text) > 80 or any(ch in text for ch in "|<>"):
        return None
    return text


def clean_subject(raw: str) -> tuple[str | None, list[str]]:
    text = normalize_space(raw)
    if not text or len(text) > 80:
        return None, [f"subject value rejected: {raw!r}"]
    match = re.fullmatch(r"(.+?)\s+-\s+Period\s+\d+", text, re.IGNORECASE)
    if match:
        return match.group(1).strip(), ["removed class period suffix"]
    return text, []


def parse_letter(raw: str) -> str | None:
    text = normalize_space(raw).upper()
    if _LETTER.fullmatch(text):
        return text
    return None


def parse_percent(raw: str) -> float | None:
    match = _PERCENT_EXACT.fullmatch(raw.strip())
    if not match:
        return None
    return float(match.group(1))


def _calendar(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_date(raw: str) -> DateParse:
    text = normalize_space(raw)
    if not text:
        return DateParse(blocked=True, notes=["empty date"])
    try:
        return DateParse(date.fromisoformat(text))
    except ValueError:
        pass
    for fmt in _MONTH_FORMATS:
        try:
            return DateParse(datetime.strptime(text, fmt).date())
        except ValueError:
            continue
    match = _NUMERIC_DATE.fullmatch(text)
    if match:
        month_first = int(match.group(1))
        day_second = int(match.group(2))
        year = int(match.group(3))
        as_mdy = _calendar(year, month_first, day_second)
        as_dmy = _calendar(year, day_second, month_first)
        if as_mdy and as_dmy and as_mdy != as_dmy:
            return DateParse(
                blocked=True,
                notes=["ambiguous numeric date; month and day are both plausible"],
            )
        if as_mdy and as_dmy:
            return DateParse(as_mdy)
        if as_mdy:
            return DateParse(as_mdy, notes=["numeric date read as month/day/year"])
        if as_dmy:
            return DateParse(as_dmy, notes=["numeric date read as day/month/year"])
        return DateParse(blocked=True, notes=[f"unparsed date: {text}"])
    return DateParse(blocked=True, notes=[f"unparsed date: {text}"])


def parse_points(raw: str) -> PointsParse:
    """Parse a score cell. A parenthetical percent is kept only when it matches the fraction."""
    text = normalize_space(raw)
    result = PointsParse()
    core = text
    paren = re.search(r"\(([^)]*)\)\s*$", text)
    if paren:
        core = text[: paren.start()].strip()
        inside = paren.group(1)
        percent_match = _PERCENT.search(inside)
        if percent_match:
            result.percent = float(percent_match.group(1))
            result.percent_source = "stated"
        letter_match = re.search(r"\b([A-F][+-]?)\b", inside, re.IGNORECASE)
        if letter_match:
            result.letter = letter_match.group(1).upper()
    fraction = _FRACTION.fullmatch(core)
    if fraction:
        score = float(fraction.group(1))
        possible = float(fraction.group(2))
        result.score = score
        result.points_possible = possible
        if possible <= 0:
            result.conflicts.append("points possible must be positive")
            result.percent = None
            result.percent_source = None
            return result
        if score > possible:
            result.conflicts.append("score is greater than points possible")
            result.percent = None
            result.percent_source = None
            return result
        computed = round(score / possible * 100, 2)
        if result.percent is not None and abs(result.percent - computed) > 0.5:
            result.conflicts.append(
                f"stated percent {result.percent:g} disagrees with "
                f"{score:g}/{possible:g} ({computed:.2f})"
            )
            result.percent = None
            result.percent_source = None
            return result
        if result.percent is None:
            result.percent = computed
            result.percent_source = "computed"
            result.notes.append("percent computed from score and points possible")
        return result
    bare = re.fullmatch(r"(\d+(?:\.\d+)?)", core)
    if bare:
        result.score = float(bare.group(1))
        if result.percent is None:
            result.notes.append("score has no points possible; percent was not computed")
        return result
    if result.percent is None and result.letter is None:
        result.conflicts.append(f"unparsed score: {raw}")
    return result
