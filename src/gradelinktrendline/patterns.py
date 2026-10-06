"""Pluggable extraction patterns.

Each pattern returns only fields it can point at in the message. It does not
borrow a percent from a letter grade or pick between two contradictory values.
"""

from __future__ import annotations

import re
from collections import defaultdict

from gradelinktrendline.fields import (
    ALIASES,
    clean_student,
    clean_subject,
    normalize_space,
    parse_date,
    parse_letter,
    parse_percent,
    parse_points,
)
from gradelinktrendline.mailio import html_to_text
from gradelinktrendline.models import Candidate, RawMessage

_LABELED = re.compile(r"^(?P<key>[A-Za-z][A-Za-z ]{0,40}?)\s*:\s*(?P<value>\S.*?)\s*$")
_PROSE = re.compile(
    r"(?P<student>[A-Z][A-Za-z.'-]*(?: [A-Z][A-Za-z.'-]*)+) received a low grade in "
    r"(?P<subject>[A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+)*)\."
)
_PROSE_ALERT = re.compile(
    r"[Ll]ow grade alert for (?P<student>[A-Z][A-Za-z.'-]*(?: [A-Z][A-Za-z.'-]*)+) in "
    r"(?P<subject>[A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+)*)\."
)
_HTML_ROW = re.compile(
    r"(?is)<tr[^>]*>\s*<t[dh][^>]*>(.*?)</t[dh]>\s*<t[dh][^>]*>(.*?)</t[dh]>\s*</tr>"
)
_COMPACT_FIELDS = (
    "student",
    "subject",
    "assignment",
    "category",
    "score",
    "letter",
    "percent",
    "date",
    "teacher",
)


def _candidate_from_buckets(
    pattern_id: str,
    buckets: dict[str, list[tuple[str, int]]],
) -> Candidate | None:
    if not buckets:
        return None
    notes: list[str] = []
    conflicts: list[str] = []
    consumed: set[int] = set()
    block_header_date = False

    def take_unique(field: str) -> list[str]:
        values = buckets.get(field, [])
        for _, line_index in values:
            consumed.add(line_index)
        return [raw for raw, _ in values]

    student = None
    student_values = take_unique("student")
    if student_values:
        parsed = [clean_student(value) for value in student_values]
        distinct = {value for value in parsed if value}
        if len(distinct) == 1 and all(parsed):
            student = next(iter(distinct))
        elif len(distinct) > 1:
            conflicts.append("conflicting student values: " + ", ".join(sorted(distinct)))
        else:
            conflicts.append("unparsed student value")

    subject = None
    for raw in take_unique("subject"):
        cleaned, subject_notes = clean_subject(raw)
        notes.extend(subject_notes)
        if cleaned is None:
            conflicts.append(f"unparsed subject: {raw}")
            continue
        if subject is None:
            subject = cleaned
        elif subject != cleaned:
            conflicts.append(f"conflicting subject values: {subject!r} vs {cleaned!r}")
            subject = None

    assignment = _plain_value("assignment", take_unique("assignment"), conflicts)
    category = _plain_value("category", take_unique("category"), conflicts)
    teacher = _plain_value("teacher", take_unique("teacher"), conflicts)

    percent_values: list[float] = []
    for raw in take_unique("percent"):
        parsed_percent = parse_percent(raw)
        if parsed_percent is None:
            conflicts.append(f"unparsed percent: {raw}")
        else:
            percent_values.append(parsed_percent)

    letters: list[str] = []
    for raw in take_unique("letter"):
        parsed_letter = parse_letter(raw)
        if parsed_letter is None:
            conflicts.append(f"unparsed letter: {raw}")
        else:
            letters.append(parsed_letter)

    score = None
    possible = None
    points_percent = None
    points_source = None
    points_letter = None
    for raw in take_unique("score"):
        parsed_points = parse_points(raw)
        notes.extend(parsed_points.notes)
        conflicts.extend(parsed_points.conflicts)
        if parsed_points.score is not None:
            if score is None:
                score = parsed_points.score
                possible = parsed_points.points_possible
            elif score != parsed_points.score or possible != parsed_points.points_possible:
                conflicts.append("conflicting score values")
                score = None
                possible = None
        if parsed_points.percent is not None:
            points_percent = parsed_points.percent
            points_source = parsed_points.percent_source
        if parsed_points.letter is not None:
            points_letter = parsed_points.letter

    percent = None
    percent_source = None
    stated = _unique_floats(percent_values)
    if len(percent_values) > 1 and stated is None:
        conflicts.append(
            "conflicting percent values: " + ", ".join(f"{value:g}" for value in percent_values)
        )
    elif stated is not None and points_percent is not None and abs(stated - points_percent) > 0.5:
        conflicts.append(
            f"conflicting percent values: labeled {stated:g} and score field {points_percent:g}"
        )
    elif stated is not None:
        percent = stated
        percent_source = "stated"
    elif points_percent is not None and not any("disagrees" in item for item in conflicts):
        percent = points_percent
        percent_source = points_source

    letter = None
    letter_values = list(letters)
    if points_letter:
        letter_values.append(points_letter)
    distinct_letters = set(letter_values)
    if len(distinct_letters) == 1:
        letter = next(iter(distinct_letters))
    elif len(distinct_letters) > 1:
        conflicts.append("conflicting letter values: " + ", ".join(sorted(distinct_letters)))

    observed_on = None
    date_notes: list[str] = []
    saw_date = False
    for raw in take_unique("date"):
        saw_date = True
        parsed_date = parse_date(raw)
        if parsed_date.blocked or parsed_date.value is None:
            block_header_date = True
            conflicts.extend(parsed_date.notes or ["unparsed date"])
            continue
        date_notes.extend(parsed_date.notes)
        if observed_on is None:
            observed_on = parsed_date.value
        elif observed_on != parsed_date.value:
            conflicts.append("conflicting dates")
            observed_on = None
            block_header_date = True
    notes.extend(date_notes)
    if saw_date and observed_on is None:
        block_header_date = True

    if percent_source != "computed":
        notes = [note for note in notes if note != "percent computed from score and points possible"]

    if not any(
        value is not None
        for value in (
            student,
            subject,
            assignment,
            category,
            teacher,
            percent,
            letter,
            score,
            observed_on,
        )
    ):
        return None

    return Candidate(
        pattern_id=pattern_id,
        student=student,
        subject=subject,
        assignment=assignment,
        category=category,
        score=score,
        points_possible=possible,
        letter=letter,
        percent=percent,
        percent_source=percent_source,
        observed_on=observed_on,
        date_source="body" if observed_on else None,
        teacher=teacher,
        consumed_lines=frozenset(consumed),
        notes=tuple(dict.fromkeys(notes)),
        conflicts=tuple(dict.fromkeys(conflicts)),
        block_header_date=block_header_date,
    )


def _plain_value(field: str, values: list[str], conflicts: list[str]) -> str | None:
    cleaned = [normalize_space(value) for value in values if normalize_space(value)]
    distinct = set(cleaned)
    if len(distinct) == 1:
        return next(iter(distinct))
    if len(distinct) > 1:
        conflicts.append(f"conflicting {field} values")
    return None


def _unique_floats(values: list[float]) -> float | None:
    if not values:
        return None
    first = values[0]
    if all(abs(value - first) <= 0.5 for value in values):
        return first
    return None


def _labeled_buckets(text: str) -> dict[str, list[tuple[str, int]]]:
    buckets: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for index, line in enumerate(text.splitlines()):
        match = _LABELED.match(line.strip())
        if not match:
            continue
        key = match.group("key").strip().lower()
        field = ALIASES.get(key)
        if not field:
            continue
        value = match.group("value").strip()
        if "|" in value:
            continue
        buckets[field].append((value, index))
    return buckets


class LabeledFieldsPattern:
    pattern_id = "labeled-fields"
    emits_rows = False

    def apply(self, raw: RawMessage) -> list[Candidate]:
        candidate = _candidate_from_buckets(self.pattern_id, _labeled_buckets(raw.body_text))
        return [candidate] if candidate else []


class HtmlTablePattern:
    pattern_id = "html-table"
    emits_rows = False

    def apply(self, raw: RawMessage) -> list[Candidate]:
        if not raw.body_html:
            return []
        buckets: dict[str, list[tuple[str, int]]] = defaultdict(list)
        for key_html, value_html in _HTML_ROW.findall(raw.body_html):
            key = normalize_space(html_to_text(key_html)).lower()
            value = normalize_space(html_to_text(value_html))
            field = ALIASES.get(key)
            if not field or not value:
                continue
            buckets[field].append((value, -1))
        candidate = _candidate_from_buckets(self.pattern_id, buckets)
        if candidate is None:
            return []
        text_lines = raw.body_text.splitlines()
        consumed = set(candidate.consumed_lines)
        known_tokens = set()
        for values in buckets.values():
            for raw_value, _ in values:
                known_tokens.add(normalize_space(raw_value))
        for key in buckets:
            known_tokens.add(key)
            known_tokens.update(alias for alias, target in ALIASES.items() if target == key)
        for index, line in enumerate(text_lines):
            if normalize_space(line).lower() in {token.lower() for token in known_tokens}:
                consumed.add(index)
        candidate.consumed_lines = frozenset(index for index in consumed if index >= 0)
        return [candidate]


class ProseAlertPattern:
    pattern_id = "prose-alert"
    emits_rows = False

    def apply(self, raw: RawMessage) -> list[Candidate]:
        buckets: dict[str, list[tuple[str, int]]] = defaultdict(list)
        for index, line in enumerate(raw.body_text.splitlines()):
            match = _PROSE.search(line) or _PROSE_ALERT.search(line)
            if not match:
                continue
            buckets["student"].append((match.group("student"), index))
            buckets["subject"].append((match.group("subject"), index))
        candidate = _candidate_from_buckets(self.pattern_id, buckets)
        return [candidate] if candidate else []


class CompactRowPattern:
    pattern_id = "compact-row"
    emits_rows = False

    def apply(self, raw: RawMessage) -> list[Candidate]:
        found: list[Candidate] = []
        for index, line in enumerate(raw.body_text.splitlines()):
            if line.count("|") < 4 or ":" in line:
                continue
            cells = [cell.strip() for cell in line.split("|")]
            if cells and cells[0].lower() == "student":
                continue
            if len(cells) != len(_COMPACT_FIELDS):
                continue
            buckets: dict[str, list[tuple[str, int]]] = {
                field: [(cells[position], index)]
                for position, field in enumerate(_COMPACT_FIELDS)
                if cells[position]
            }
            candidate = _candidate_from_buckets(self.pattern_id, buckets)
            if candidate and candidate.student and candidate.subject:
                found.append(candidate)
        return found


class AssignmentRowsPattern:
    """Several keyed rows under one student/subject header."""

    pattern_id = "assignment-rows"
    emits_rows = True

    def apply(self, raw: RawMessage) -> list[Candidate]:
        header = _labeled_buckets(raw.body_text)
        header.pop("assignment", None)
        header.pop("score", None)
        header.pop("percent", None)
        header.pop("letter", None)
        header.pop("date", None)
        header.pop("category", None)
        rows: list[Candidate] = []
        for index, line in enumerate(raw.body_text.splitlines()):
            stripped = line.strip()
            if "|" not in stripped or ":" not in stripped:
                continue
            buckets: dict[str, list[tuple[str, int]]] = defaultdict(list)
            for piece in stripped.split("|"):
                match = _LABELED.match(piece.strip())
                if not match:
                    continue
                field = ALIASES.get(match.group("key").strip().lower())
                if field:
                    buckets[field].append((match.group("value").strip(), index))
            if "assignment" not in buckets and "score" not in buckets and "percent" not in buckets:
                continue
            for field, values in header.items():
                buckets.setdefault(field, []).extend(values)
            candidate = _candidate_from_buckets(self.pattern_id, buckets)
            if candidate:
                rows.append(candidate)
        return rows


def default_patterns() -> list[object]:
    return [
        LabeledFieldsPattern(),
        HtmlTablePattern(),
        ProseAlertPattern(),
        CompactRowPattern(),
        AssignmentRowsPattern(),
    ]
