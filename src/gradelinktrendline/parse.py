"""Turn a raw message into observations with an explicit confidence score."""

from __future__ import annotations

from gradelinktrendline.models import Candidate, Observation, RawMessage
from gradelinktrendline.patterns import default_patterns

REVIEW_THRESHOLD = 0.75
_FIELDS = (
    "student",
    "subject",
    "assignment",
    "category",
    "score",
    "points_possible",
    "letter",
    "percent",
    "observed_on",
    "teacher",
)


def parse_message(raw: RawMessage, patterns: list[object] | None = None) -> list[Observation]:
    chosen = default_patterns() if patterns is None else patterns
    singles: list[Candidate] = []
    rows: list[Candidate] = []
    for pattern in chosen:
        found = list(pattern.apply(raw))  # type: ignore[attr-defined]
        if not found:
            continue
        if getattr(pattern, "emits_rows", False):
            rows.extend(found)
        else:
            singles.extend(found)

    if not rows and not singles:
        reason = "empty body" if not raw.body_text.strip() else "no pattern matched"
        return [
            _observation(
                raw,
                Candidate(pattern_id="none"),
                remainder=raw.body_text.strip(),
                extra_reasons=(reason,),
                header_date_allowed=False,
            )
        ]

    base = _consensus(singles) if singles else None
    merged = [_consensus([row, base]) if base else row for row in rows] if rows else [_consensus(singles)]
    consumed: set[int] = set()
    for item in merged:
        consumed.update(item.consumed_lines)
    if base and rows:
        consumed.update(base.consumed_lines)
    remainder = _remainder(raw.body_text, consumed)
    header_allowed = True
    return [_observation(raw, item, remainder=remainder, header_date_allowed=header_allowed) for item in merged]


def _consensus(candidates: list[Candidate]) -> Candidate:
    present = [item for item in candidates if item is not None]
    if len(present) == 1:
        return present[0]
    notes: list[str] = []
    conflicts: list[str] = []
    consumed: set[int] = set()
    block = False
    ids: list[str] = []
    for item in present:
        notes.extend(item.notes)
        conflicts.extend(item.conflicts)
        consumed.update(item.consumed_lines)
        block = block or item.block_header_date
        ids.append(item.pattern_id)
    chosen: dict[str, object] = {}
    for name in _FIELDS:
        values: list[tuple[object, str]] = []
        for item in present:
            value = getattr(item, name)
            if value is not None:
                values.append((value, item.pattern_id))
        unique: list[tuple[object, str]] = []
        for value, pattern_id in values:
            if not any(_equal(name, value, previous) for previous, _ in unique):
                unique.append((value, pattern_id))
        if len(unique) == 1:
            chosen[name] = unique[0][0]
        elif len(unique) > 1:
            chosen[name] = None
            shown = ", ".join(f"{value!r} ({pattern_id})" for value, pattern_id in unique)
            conflicts.append(f"conflict on {name}: {shown}")
            if name == "observed_on":
                block = True
    percent = chosen.get("percent")
    percent_source = None
    if percent is not None:
        for item in present:
            if item.percent is not None and _equal("percent", item.percent, percent):
                if item.percent_source == "stated":
                    percent_source = "stated"
                    break
                percent_source = item.percent_source or percent_source
    observed = chosen.get("observed_on")
    date_source = None
    if observed is not None:
        date_source = "body"
    return Candidate(
        pattern_id="+".join(sorted(set(ids))),
        student=chosen.get("student"),  # type: ignore[arg-type]
        subject=chosen.get("subject"),  # type: ignore[arg-type]
        assignment=chosen.get("assignment"),  # type: ignore[arg-type]
        category=chosen.get("category"),  # type: ignore[arg-type]
        score=chosen.get("score"),  # type: ignore[arg-type]
        points_possible=chosen.get("points_possible"),  # type: ignore[arg-type]
        letter=chosen.get("letter"),  # type: ignore[arg-type]
        percent=percent,  # type: ignore[arg-type]
        percent_source=percent_source,
        observed_on=observed,  # type: ignore[arg-type]
        date_source=date_source,
        teacher=chosen.get("teacher"),  # type: ignore[arg-type]
        consumed_lines=frozenset(consumed),
        notes=tuple(dict.fromkeys(notes)),
        conflicts=tuple(dict.fromkeys(conflicts)),
        block_header_date=block,
    )


def _observation(
    raw: RawMessage,
    candidate: Candidate,
    *,
    remainder: str,
    extra_reasons: tuple[str, ...] = (),
    header_date_allowed: bool,
) -> Observation:
    notes = list(candidate.notes)
    conflicts = list(candidate.conflicts)
    observed = candidate.observed_on
    date_source = candidate.date_source
    if (
        observed is None
        and header_date_allowed
        and not candidate.block_header_date
        and raw.message_date is not None
        and candidate.pattern_id != "none"
    ):
        observed = raw.message_date.date()
        date_source = "message-header"
        notes.append(
            "date taken from the message Date header because the body had no unambiguous date"
        )
    percent = candidate.percent
    if percent is not None and not 0 <= percent <= 100:
        conflicts.append("percent outside 0-100")
    disagreement = _letter_percent_conflict(percent, candidate.letter)
    if disagreement:
        conflicts.append(disagreement)
    confidence, reasons, needs_review = _score(
        student=candidate.student,
        subject=candidate.subject,
        assignment=candidate.assignment,
        category=candidate.category,
        score=candidate.score,
        letter=candidate.letter,
        percent=percent,
        percent_source=candidate.percent_source,
        observed_on=observed,
        date_source=date_source,
        teacher=candidate.teacher,
        conflicts=conflicts,
    )
    reasons = list(dict.fromkeys([*reasons, *extra_reasons]))
    return Observation(
        message_id=raw.message_id,
        student=candidate.student,
        subject=candidate.subject,
        assignment=candidate.assignment,
        category=candidate.category,
        score=candidate.score,
        points_possible=candidate.points_possible,
        letter=candidate.letter,
        percent=percent,
        percent_source=candidate.percent_source if percent is not None else None,
        observed_on=observed,
        date_source=date_source if observed is not None else None,
        teacher=candidate.teacher,
        confidence=confidence,
        pattern_id=candidate.pattern_id,
        needs_review=needs_review,
        review_reasons=tuple(reasons),
        notes=tuple(dict.fromkeys(notes)),
        unparsed_remainder=remainder,
    )


def _score(
    *,
    student: str | None,
    subject: str | None,
    assignment: str | None,
    category: str | None,
    score: float | None,
    letter: str | None,
    percent: float | None,
    percent_source: str | None,
    observed_on: object,
    date_source: str | None,
    teacher: str | None,
    conflicts: list[str],
) -> tuple[float, list[str], bool]:
    reasons: list[str] = []
    raw = 0.0
    if student:
        raw += 0.22
    else:
        reasons.append("missing student")
    if subject:
        raw += 0.22
    else:
        reasons.append("missing subject")
    has_percent = percent is not None
    has_letter = letter is not None
    if has_percent and percent_source == "computed":
        raw += 0.18
    elif has_percent:
        raw += 0.22
    elif has_letter:
        raw += 0.20
    elif score is not None:
        raw += 0.08
        reasons.append("score without a percent")
    else:
        reasons.append("missing grade signal")
    if observed_on is not None:
        raw += 0.12 if date_source == "body" else 0.06
    else:
        reasons.append("missing date")
    if assignment:
        raw += 0.08
    if category:
        raw += 0.07
    if teacher:
        raw += 0.07
    raw = min(raw, 1.0)
    needs_review = bool(conflicts) or observed_on is None or not student or not subject
    if not has_percent and not has_letter:
        needs_review = True
        if "missing grade signal" not in reasons and "score without a percent" not in reasons:
            reasons.append("missing grade signal")
    if raw < REVIEW_THRESHOLD:
        needs_review = True
    reasons.extend(conflicts)
    if conflicts:
        raw = min(raw, 0.49)
    elif needs_review:
        raw = min(raw, 0.74)
    return raw, list(dict.fromkeys(reasons)), needs_review


def _letter_percent_conflict(percent: float | None, letter: str | None) -> str | None:
    if percent is None or letter is None:
        return None
    low_letter = letter[0] in {"D", "F"}
    high_letter = letter[0] in {"A", "B", "C"}
    low_percent = percent < 70
    if (low_letter and not low_percent) or (high_letter and low_percent):
        return "letter and percent disagree about whether the score is under 70"
    return None


def _equal(name: str, left: object, right: object) -> bool:
    if isinstance(left, float) and isinstance(right, float):
        tolerance = 0.5 if name == "percent" else 1e-6
        return abs(left - right) <= tolerance
    return left == right


def _remainder(text: str, consumed: set[int]) -> str:
    kept = [line for index, line in enumerate(text.splitlines()) if index not in consumed]
    return "\n".join(kept).strip()
