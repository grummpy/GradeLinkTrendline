"""Trend math for confirmed observations.

Low-grade alert: a percent under 70, or a letter of D or F when no percent is present.
A letter is never turned into a percent. Contradictory letter/percent pairs are not counted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import pandas as pd

LOW_PERCENT = 70.0
REPEAT_MIN = 3
REPEAT_WITHIN_DAYS = 21
WINDOW_DAYS = 14
ROLLING_DAYS = 14

BANNED_LABEL = re.compile(
    r"struggl|behind|lazy|gifted|disabilit|diagnos|dyslex|adhd|autis|"
    r"stupid|\bdumb\b|low ability|bad at|can't|cannot learn",
    re.IGNORECASE,
)

_LOW_LETTERS = {"D", "D+", "D-", "F"}
_HIGH_LETTERS = {"A", "A+", "A-", "B", "B+", "B-", "C", "C+", "C-"}


def contains_banned_label(text: str) -> bool:
    return BANNED_LABEL.search(text) is not None


@dataclass
class Point:
    student: str
    subject: str
    observed_on: date
    percent: float | None
    rolling_avg: float | None
    is_low: bool
    assignment: str | None
    letter: str | None
    teacher: str | None
    category: str | None
    message_id: str


@dataclass
class WindowCount:
    start: date
    end: date
    low_alerts: int


@dataclass
class SubjectSummary:
    student: str
    subject: str
    repeat_trouble: bool
    repeat_start: date | None
    repeat_end: date | None
    repeat_count: int
    slope_per_week: float | None
    latest_percent: float | None
    latest_rolling_avg: float | None
    low_alert_count: int
    observation_count: int
    windows: list[WindowCount] = field(default_factory=list)
    points: list[Point] = field(default_factory=list)


@dataclass
class WeekNote:
    student: str
    week_start: date
    text: str


@dataclass
class Analysis:
    subjects: list[SubjectSummary]
    weeks: list[WeekNote]
    points_frame: pd.DataFrame
    subjects_frame: pd.DataFrame
    windows_frame: pd.DataFrame


def classify_low(percent: float | None, letter: str | None) -> bool | None:
    """Return True/False, or None when the two signals disagree or both are missing."""
    letter_low: bool | None = None
    if letter in _LOW_LETTERS:
        letter_low = True
    elif letter in _HIGH_LETTERS:
        letter_low = False
    elif letter:
        return None
    percent_low = None if percent is None else percent < LOW_PERCENT
    if letter_low is None and percent_low is None:
        return None
    if letter_low is not None and percent_low is not None and letter_low != percent_low:
        return None
    if percent_low is not None:
        return percent_low
    return letter_low


def slope_per_week(dates: list[date], percents: list[float | None]) -> float | None:
    pairs = [(item_date, percent) for item_date, percent in zip(dates, percents, strict=True) if percent is not None]
    if len(pairs) < 2:
        return None
    origin = min(item_date for item_date, _ in pairs)
    xs = [(item_date - origin).days for item_date, _ in pairs]
    ys = [percent for _, percent in pairs]
    if len(set(xs)) < 2:
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:
        return None
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    return (numerator / denominator) * 7


def rolling_averages(
    dates: list[date],
    percents: list[float | None],
    window_days: int = ROLLING_DAYS,
) -> list[float | None]:
    averages: list[float | None] = []
    for index, end in enumerate(dates):
        start = end - timedelta(days=window_days - 1)
        window = [
            percent
            for item_date, percent in zip(dates[: index + 1], percents[: index + 1], strict=True)
            if percent is not None and start <= item_date <= end
        ]
        averages.append(sum(window) / len(window) if window else None)
    return averages


def two_week_windows(
    dates: list[date],
    low_flags: list[bool],
    origin: date | None = None,
) -> list[WindowCount]:
    if not dates:
        return []
    start_origin = origin or min(dates)
    last = max(dates)
    windows: list[WindowCount] = []
    start = start_origin
    while start <= last:
        end = start + timedelta(days=WINDOW_DAYS - 1)
        count = sum(
            1
            for item_date, is_low in zip(dates, low_flags, strict=True)
            if is_low and start <= item_date <= end
        )
        windows.append(WindowCount(start=start, end=end, low_alerts=count))
        start = end + timedelta(days=1)
    return windows


def repeat_trouble(low_dates: list[date]) -> tuple[bool, date | None, date | None, int]:
    ordered = sorted(low_dates)
    best_count = 0
    best_span: tuple[date, date] | None = None
    for start in ordered:
        limit = start + timedelta(days=REPEAT_WITHIN_DAYS)
        group = [item for item in ordered if start <= item <= limit]
        if len(group) > best_count:
            best_count = len(group)
            best_span = (group[0], group[-1])
    if best_count >= REPEAT_MIN and best_span is not None:
        return True, best_span[0], best_span[1], best_count
    return False, None, None, best_count


def analyze(rows: list[dict[str, object]]) -> Analysis:
    normalized = [_normalize(row) for row in rows]
    confirmed = [row for row in normalized if _usable(row)]
    frame = pd.DataFrame(confirmed)
    subjects: list[SubjectSummary] = []
    if not frame.empty:
        frame["observed_on"] = pd.to_datetime(frame["observed_on"])
        grouped = frame.groupby(["student", "subject"], sort=True)
        for (student, subject), group in grouped:
            group = group.sort_values(["observed_on", "message_id"])
            dates = [item.date() for item in group["observed_on"]]
            percents = [None if pd.isna(value) else float(value) for value in group["percent"]]
            flags = [bool(value) for value in group["is_low"]]
            rolling = rolling_averages(dates, percents)
            low_dates = [item_date for item_date, is_low in zip(dates, flags, strict=True) if is_low]
            flagged, repeat_start, repeat_end, repeat_count = repeat_trouble(low_dates)
            windows = two_week_windows(dates, flags)
            points = [
                Point(
                    student=str(student),
                    subject=str(subject),
                    observed_on=item_date,
                    percent=percent,
                    rolling_avg=avg,
                    is_low=is_low,
                    assignment=_text(record.get("assignment")),
                    letter=_text(record.get("letter")),
                    teacher=_text(record.get("teacher")),
                    category=_text(record.get("category")),
                    message_id=str(record.get("message_id") or ""),
                )
                for record, item_date, percent, avg, is_low in zip(
                    group.to_dict("records"),
                    dates,
                    percents,
                    rolling,
                    flags,
                    strict=True,
                )
            ]
            percent_points = [point for point in points if point.percent is not None]
            subjects.append(
                SubjectSummary(
                    student=str(student),
                    subject=str(subject),
                    repeat_trouble=flagged,
                    repeat_start=repeat_start,
                    repeat_end=repeat_end,
                    repeat_count=repeat_count,
                    slope_per_week=slope_per_week(dates, percents),
                    latest_percent=percent_points[-1].percent if percent_points else None,
                    latest_rolling_avg=percent_points[-1].rolling_avg if percent_points else None,
                    low_alert_count=sum(flags),
                    observation_count=len(points),
                    windows=windows,
                    points=points,
                )
            )
    subjects.sort(key=lambda item: (item.student.lower(), _subject_key(item.subject)))
    weeks = _weekly_notes(subjects)
    return Analysis(
        subjects=subjects,
        weeks=weeks,
        points_frame=_points_frame(subjects),
        subjects_frame=_subjects_frame(subjects),
        windows_frame=_windows_frame(subjects),
    )


def conversation_prompts(summary: SubjectSummary) -> list[str]:
    prompts: list[str] = []
    if summary.repeat_trouble and summary.repeat_start and summary.repeat_end:
        prompts.append(
            f"{summary.subject} has {summary.repeat_count} low-grade alerts between "
            f"{summary.repeat_start.isoformat()} and {summary.repeat_end.isoformat()}. "
            "Which assignments and categories fall in that window?"
        )
    if summary.slope_per_week is not None and summary.slope_per_week < -0.5:
        prompts.append(
            f"Recorded percents in {summary.subject} change by {summary.slope_per_week:.1f} "
            "percentage points per week across this range. "
            "Which recent scores sit below the 70 percent line?"
        )
    letter_only = sum(1 for point in summary.points if point.is_low and point.percent is None)
    if letter_only:
        noun = "low-grade alert" if letter_only == 1 else "low-grade alerts"
        prompts.append(
            f"{summary.subject} has {letter_only} {noun} with a letter and no percent. "
            "This sheet does not invent a percent for those."
        )
    return prompts[:3]


def _weekly_notes(subjects: list[SubjectSummary]) -> list[WeekNote]:
    by_student: dict[str, list[SubjectSummary]] = {}
    for summary in subjects:
        by_student.setdefault(summary.student, []).append(summary)
    notes: list[WeekNote] = []
    for student, summaries in by_student.items():
        flags = {item.subject: item.repeat_trouble for item in summaries}
        buckets: dict[date, list[Point]] = {}
        for summary in summaries:
            for point in summary.points:
                buckets.setdefault(_week_start(point.observed_on), []).append(point)
        frame = pd.DataFrame({"week_start": list(buckets)})
        if frame.empty:
            continue
        frame["week_start"] = pd.to_datetime(frame["week_start"])
        for stamp in frame.sort_values("week_start")["week_start"]:
            week_date = stamp.date()
            points = buckets[week_date]
            notes.append(
                WeekNote(
                    student=student,
                    week_start=week_date,
                    text=_week_text(student, week_date, points, flags),
                )
            )
    return notes


def _week_text(student: str, week_start: date, points: list[Point], flags: dict[str, bool]) -> str:
    lines = [f"Week of {week_start.isoformat()}, {student}"]
    by_subject: dict[str, list[Point]] = {}
    for point in points:
        by_subject.setdefault(point.subject, []).append(point)
    for subject in sorted(by_subject, key=_subject_key):
        items = sorted(by_subject[subject], key=lambda item: item.observed_on)
        lows = [item for item in items if item.is_low]
        if lows:
            noun = "low-grade alert" if len(lows) == 1 else "low-grade alerts"
            line = f"{subject}: {len(lows)} {noun} ({_details(lows)})."
            if flags.get(subject):
                line += (
                    " This subject has a repeat-trouble flag "
                    "(3 or more low-grade alerts within 21 days)."
                )
        else:
            noun = "recorded score" if len(items) == 1 else "recorded scores"
            line = (
                f"{subject}: {len(items)} {noun} ({_details(items)}), "
                "none under the 70 percent alert line."
            )
        lines.append(line)
    lines.append(
        "These counts describe alert emails and recorded scores. "
        "They are not a statement about ability."
    )
    return "\n".join(lines)


def _details(points: list[Point]) -> str:
    chunks = []
    for point in points:
        if point.percent is not None:
            grade = f"{point.percent:g}%"
        elif point.letter:
            grade = f"letter {point.letter}"
        else:
            grade = "no percent stored"
        label = point.assignment or "untitled item"
        chunks.append(f"{grade} on {point.observed_on.isoformat()}, {label}")
    return "; ".join(chunks)


def _points_frame(subjects: list[SubjectSummary]) -> pd.DataFrame:
    records = []
    for summary in subjects:
        for point in summary.points:
            records.append(
                {
                    "student": point.student,
                    "subject": point.subject,
                    "observed_on": point.observed_on.isoformat(),
                    "percent": point.percent,
                    "rolling_avg_14d": point.rolling_avg,
                    "is_low": point.is_low,
                    "assignment": point.assignment,
                    "letter": point.letter,
                    "teacher": point.teacher,
                    "category": point.category,
                    "slope_per_week": summary.slope_per_week,
                    "repeat_trouble": summary.repeat_trouble,
                    "message_id": point.message_id,
                }
            )
    return pd.DataFrame(records)


def _subjects_frame(subjects: list[SubjectSummary]) -> pd.DataFrame:
    records = [
        {
            "student": item.student,
            "subject": item.subject,
            "repeat_trouble": item.repeat_trouble,
            "repeat_start": item.repeat_start.isoformat() if item.repeat_start else None,
            "repeat_end": item.repeat_end.isoformat() if item.repeat_end else None,
            "repeat_count": item.repeat_count,
            "slope_per_week": item.slope_per_week,
            "latest_percent": item.latest_percent,
            "latest_rolling_avg": item.latest_rolling_avg,
            "low_alert_count": item.low_alert_count,
            "observation_count": item.observation_count,
        }
        for item in subjects
    ]
    return pd.DataFrame(records)


def _windows_frame(subjects: list[SubjectSummary]) -> pd.DataFrame:
    records = [
        {
            "student": item.student,
            "subject": item.subject,
            "window_start": window.start.isoformat(),
            "window_end": window.end.isoformat(),
            "low_alerts": window.low_alerts,
        }
        for item in subjects
        for window in item.windows
    ]
    return pd.DataFrame(records)


def _usable(row: dict[str, object]) -> bool:
    if row.get("needs_review"):
        return False
    if not row.get("student") or not row.get("subject") or not row.get("observed_on"):
        return False
    return classify_low(_float_or_none(row.get("percent")), _text(row.get("letter"))) is not None


def _normalize(row: dict[str, object]) -> dict[str, object]:
    item = dict(row)
    item["observed_on"] = _as_date(item.get("observed_on"))
    item["percent"] = _float_or_none(item.get("percent"))
    item["needs_review"] = bool(item.get("needs_review"))
    letter = _text(item.get("letter"))
    item["letter"] = letter
    status = classify_low(item["percent"], letter)  # type: ignore[arg-type]
    item["is_low"] = bool(status) if status is not None else None
    return item


def _as_date(value: object) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    return None


def _float_or_none(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return float(value)  # type: ignore[arg-type]


def _text(value: object) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    text = str(value).strip()
    return text or None


def _week_start(value: date) -> date:
    return value - timedelta(days=value.weekday())


def _subject_key(name: str) -> tuple[int, str]:
    order = {"math": 0, "science": 1, "penmanship": 2, "history": 3}
    return (order.get(name.lower(), 10), name.lower())
