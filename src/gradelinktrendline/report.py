"""Self-contained HTML dashboard and one-page conversation sheets. No runtime CDN."""

from __future__ import annotations

import html
from datetime import date
from pathlib import Path

from gradelinktrendline.trends import Analysis, Point, SubjectSummary, analyze, conversation_prompts

_COLORS = {
    "math": "#2F6FED",
    "science": "#2E9B57",
    "penmanship": "#E0A100",
    "history": "#7B5EA7",
}
_PALETTE = ["#2F6FED", "#2E9B57", "#E0A100", "#7B5EA7", "#D4654A", "#3A7CA5"]


def write_report(rows: list[dict[str, object]], out_dir: Path) -> Analysis:
    out_dir.mkdir(parents=True, exist_ok=True)
    analysis = analyze(rows)
    review = [row for row in rows if row.get("needs_review")]
    (out_dir / "index.html").write_text(_dashboard(analysis, review), encoding="utf-8")
    for student in sorted({item.student for item in analysis.subjects}):
        slug = _slug(student)
        sheet = _printable(student, analysis)
        (out_dir / f"summary-{slug}.html").write_text(sheet, encoding="utf-8")
    analysis.points_frame.to_csv(out_dir / "observations.csv", index=False)
    analysis.subjects_frame.to_csv(out_dir / "subjects.csv", index=False)
    analysis.windows_frame.to_csv(out_dir / "windows.csv", index=False)
    weekly = "\n\n".join(note.text for note in analysis.weeks)
    if weekly:
        weekly += "\n"
    (out_dir / "weekly.txt").write_text(weekly, encoding="utf-8")
    return analysis


def _dashboard(analysis: Analysis, review: list[dict[str, object]]) -> str:
    generated = date.today().isoformat()
    students = sorted({item.student for item in analysis.subjects})
    sections = []
    if not students and not review:
        sections.append("<p>No observations yet. Run <code>glt ingest</code> on a folder of .eml or .mbox files.</p>")
    for student in students:
        summaries = [item for item in analysis.subjects if item.student == student]
        weeks = [note.text for note in analysis.weeks if note.student == student]
        slug = _slug(student)
        flag_names = [item.subject for item in summaries if item.repeat_trouble]
        flag_line = ""
        if flag_names:
            names = ", ".join(flag_names)
            flag_line = (
                f"<p class='flag'>Repeat-trouble flag: {esc(names)} "
                "(3 or more low-grade alerts within 21 days).</p>"
            )
        week_html = "".join(f"<pre>{esc(text)}</pre>" for text in weeks)
        sections.append(
            f"""
            <section class="card" id="{esc(slug)}">
              <h2>{esc(student)}</h2>
              <p><a href="summary-{esc(slug)}.html">Printable one-page summary</a></p>
              {flag_line}
              {_chart(summaries)}
              {_legend(summaries)}
              <h3>Subjects</h3>
              {_subject_table(summaries)}
              <h3>Weekly summary</h3>
              {week_html or "<p>No dated observations.</p>"}
            </section>
            """
        )
    return _shell(
        "GradeLink Trendline",
        f"""
        <header>
          <p class="eyebrow">Local dashboard</p>
          <h1><span>GradeLink</span> Trendline</h1>
          <p>Confirmed observations: {sum(item.observation_count for item in analysis.subjects)}.
             Review queue: {len(review)}. Generated {esc(generated)}.</p>
        </header>
        <main>
          <p class="note">Low-grade alert means a recorded percent under 70, or a letter of D or F when the
          message has no percent. A letter is never converted into a percent. Charts use confirmed parses only.</p>
          {"".join(sections)}
          <section class="card" id="review">
            <h2>Review queue</h2>
            <p>These messages were not added to the charts. Nothing was filled in to make them fit.</p>
            {_review_table(review)}
          </section>
        </main>
        """,
    )


def _printable(student: str, analysis: Analysis) -> str:
    summaries = [item for item in analysis.subjects if item.student == student]
    points = [point for item in summaries for point in item.points]
    points.sort(key=lambda item: item.observed_on, reverse=True)
    omitted = max(0, len(points) - 8)
    shown = points[:8]
    prompts: list[str] = []
    for summary in summaries:
        prompts.extend(conversation_prompts(summary))
    prompts = prompts[:3]
    if not prompts:
        prompts.append(
            "Which assignments in the table were under the 70 percent alert line, and what categories were they in?"
        )
    dates = [point.observed_on for point in points]
    span = ""
    if dates:
        span = f"{min(dates).isoformat()} to {max(dates).isoformat()}"
    prompt_html = "".join(f"<li>{esc(item)}</li>" for item in prompts)
    return _shell(
        f"GradeLink Trendline — {student}",
        f"""
        <article class="sheet">
          <p class="eyebrow">Conversation summary</p>
          <h1>{esc(student)}</h1>
          <p>For a parent-teacher or tutor conversation. Range: {esc(span or "no dated scores")}.
             Generated {esc(date.today().isoformat())}.</p>
          <p class="note">These figures count alert emails and recorded scores.
             They are not a statement about ability.</p>
          {_chart(summaries, width=700, height=180)}
          {_subject_table(summaries)}
          <h2>Recent observations</h2>
          {_point_table(shown)}
          {f"<p>{omitted} older observations are on the local dashboard.</p>" if omitted else ""}
          <h2>Questions to take to the meeting</h2>
          <ul>{prompt_html}</ul>
        </article>
        """,
        printable=True,
    )


def _subject_table(summaries: list[SubjectSummary]) -> str:
    rows = []
    for item in summaries:
        windows = "; ".join(
            f"{window.start.isoformat()}–{window.end.isoformat()}: {window.low_alerts}"
            for window in item.windows
        )
        repeat = "yes" if item.repeat_trouble else "no"
        rows.append(
            "<tr>"
            f"<td>{esc(item.subject)}</td>"
            f"<td>{item.low_alert_count}</td>"
            f"<td>{esc(repeat)}</td>"
            f"<td>{esc(_fmt_percent(item.latest_percent))}</td>"
            f"<td>{esc(_fmt_percent(item.latest_rolling_avg))}</td>"
            f"<td>{esc(_fmt_slope(item.slope_per_week))}</td>"
            f"<td>{esc(windows)}</td>"
            "</tr>"
        )
    body = "".join(rows) or "<tr><td colspan='7'>No confirmed observations.</td></tr>"
    return (
        "<table><thead><tr>"
        "<th>Subject</th><th>Low-grade alerts</th><th>Repeat trouble</th>"
        "<th>Latest percent</th><th>14-day average</th><th>Slope</th>"
        "<th>Low-grade alerts per 14-day window</th>"
        f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _point_table(points: list[Point]) -> str:
    rows = []
    for point in points:
        rows.append(
            "<tr>"
            f"<td>{esc(point.observed_on.isoformat())}</td>"
            f"<td>{esc(point.subject)}</td>"
            f"<td>{esc(point.assignment)}</td>"
            f"<td>{esc(point.category)}</td>"
            f"<td>{esc(_fmt_percent(point.percent))}</td>"
            f"<td>{esc(point.letter)}</td>"
            f"<td>{esc(point.teacher)}</td>"
            f"<td>{'yes' if point.is_low else 'no'}</td>"
            "</tr>"
        )
    body = "".join(rows) or "<tr><td colspan='8'>None.</td></tr>"
    return (
        "<table><thead><tr><th>Date</th><th>Subject</th><th>Assignment</th><th>Category</th>"
        "<th>Percent</th><th>Letter</th><th>Teacher</th><th>Low-grade alert</th>"
        f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _review_table(review: list[dict[str, object]]) -> str:
    if not review:
        return "<p>The review queue is empty.</p>"
    rows = []
    for item in review:
        reasons = item.get("review_reasons") or []
        if not isinstance(reasons, list):
            reasons = [str(reasons)]
        notes = item.get("notes") or []
        if not isinstance(notes, list):
            notes = [str(notes)]
        observed = item.get("observed_on")
        observed_text = observed.isoformat() if isinstance(observed, date) else ""
        rows.append(
            "<tr>"
            f"<td>{esc(_display_source(item.get('source')))}</td>"
            f"<td>{esc(_num(item.get('confidence')))}</td>"
            f"<td>{esc(item.get('pattern_id'))}</td>"
            f"<td>{esc(item.get('student'))}</td>"
            f"<td>{esc(item.get('subject'))}</td>"
            f"<td>{esc(_fmt_percent(_as_float(item.get('percent'))))}</td>"
            f"<td>{esc(item.get('letter'))}</td>"
            f"<td>{esc(observed_text)}</td>"
            f"<td>{esc('; '.join(str(reason) for reason in reasons))}</td>"
            f"<td>{esc('; '.join(str(note) for note in notes))}</td>"
            f"<td><pre>{esc(item.get('unparsed_remainder'))}</pre></td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Source</th><th>Confidence</th><th>Patterns</th><th>Student</th>"
        "<th>Subject</th><th>Percent</th><th>Letter</th><th>Date</th><th>Why it is in review</th>"
        f"<th>Notes</th><th>Unparsed remainder</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def _chart(summaries: list[SubjectSummary], width: int = 760, height: int = 280) -> str:
    dated = [point for item in summaries for point in item.points if point.percent is not None]
    if not dated:
        return "<p>No percents to plot. Alerts without a percent stay in the table.</p>"
    left, right, top, bottom = 36, 12, 12, 24
    plot_w = width - left - right
    plot_h = height - top - bottom
    dates = [point.observed_on for point in dated]
    min_d, max_d = min(dates), max(dates)
    span = max((max_d - min_d).days, 1)

    def x_of(value: date) -> float:
        return left + ((value - min_d).days / span) * plot_w

    def y_of(percent: float) -> float:
        return top + ((100 - percent) / 100) * plot_h

    parts = [
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='Recorded percents by subject'>",
        "<title>Recorded percents by subject</title>",
        f"<rect x='0' y='0' width='{width}' height='{height}' fill='#ffffff' rx='12'></rect>",
    ]
    for tick in (0, 50, 70, 100):
        y = y_of(float(tick))
        color = "#C47B00" if tick == 70 else "#E6E0D4"
        dash = " stroke-dasharray='4 4'" if tick == 70 else ""
        parts.append(
            f"<line x1='{left}' y1='{y:.1f}' x2='{width - right}' y2='{y:.1f}' "
            f"stroke='{color}'{dash}></line>"
        )
        parts.append(
            f"<text x='4' y='{y + 4:.1f}' fill='#5C6B82' font-size='11'>{tick}</text>"
        )
    parts.append(
        f"<text x='{left}' y='{height - 6}' fill='#5C6B82' font-size='11'>{esc(min_d.isoformat())}</text>"
    )
    parts.append(
        f"<text x='{width - 90}' y='{height - 6}' fill='#5C6B82' font-size='11'>{esc(max_d.isoformat())}</text>"
    )
    for index, summary in enumerate(summaries):
        color = _COLORS.get(summary.subject.lower(), _PALETTE[index % len(_PALETTE)])
        percent_points = [point for point in summary.points if point.percent is not None]
        if len(percent_points) >= 2:
            coords = " ".join(
                f"{x_of(point.observed_on):.1f},{y_of(point.percent or 0):.1f}" for point in percent_points
            )
            parts.append(f"<polyline fill='none' stroke='{color}' stroke-width='2.5' points='{coords}'></polyline>")
        rolling = [point for point in summary.points if point.rolling_avg is not None and point.percent is not None]
        if len(rolling) >= 2:
            coords = " ".join(
                f"{x_of(point.observed_on):.1f},{y_of(point.rolling_avg or 0):.1f}" for point in rolling
            )
            parts.append(
                f"<polyline fill='none' stroke='{color}' stroke-width='1.5' stroke-dasharray='5 4' "
                f"points='{coords}'></polyline>"
            )
        for point in percent_points:
            parts.append(
                f"<circle cx='{x_of(point.observed_on):.1f}' cy='{y_of(point.percent or 0):.1f}' r='3.5' "
                f"fill='{color}'><title>{esc(summary.subject)} {esc(_fmt_percent(point.percent))} "
                f"on {esc(point.observed_on.isoformat())}</title></circle>"
            )
    parts.append("</svg>")
    parts.append(
        "<p class='note'>Solid lines connect recorded percents. Dashed lines are the trailing 14-day average. "
        "The marked horizontal line is the 70 percent alert line.</p>"
    )
    return "".join(parts)


def _legend(summaries: list[SubjectSummary]) -> str:
    chips = []
    for index, summary in enumerate(summaries):
        color = _COLORS.get(summary.subject.lower(), _PALETTE[index % len(_PALETTE)])
        chips.append(
            f"<span class='chip'><i style='background:{color}'></i>{esc(summary.subject)}</span>"
        )
    return f"<p class='legend'>{''.join(chips)}</p>" if chips else ""


def _shell(title: str, body: str, printable: bool = False) -> str:
    sheet = "body { max-width: 8in; }" if printable else "main { max-width: 980px; margin: 0 auto; padding: 24px; }"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{esc(title)}</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ margin: 0; background: #FBF6EC; color: #1B2A4A;
    font: 16px/1.45 "Segoe UI", "Helvetica Neue", Arial, sans-serif; }}
  {sheet}
  header {{ background: #1B2A4A; color: #FBF6EC; padding: 28px 32px; }}
  header h1 {{ margin: 0; font-size: 32px; }}
  header h1 span {{ color: #8FD9B3; }}
  h1, h2, h3 {{ line-height: 1.2; }}
  .eyebrow {{ text-transform: uppercase; letter-spacing: 0.08em; font-size: 12px; margin: 0 0 8px; }}
  .card, .sheet {{ background: #fff; border-radius: 16px; padding: 18px 20px; margin: 16px 0; overflow-x: auto; }}
  .sheet {{ margin: 16px auto; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ text-align: left; vertical-align: top; padding: 6px 8px;
    border-bottom: 1px solid #E6E0D4; font-size: 14px; }}
  th {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.03em; color: #5C6B82; }}
  .note {{ color: #5C6B82; font-size: 14px; }}
  .flag {{ color: #8A5A00; font-weight: 700; }}
  pre {{ white-space: pre-wrap; font: 13px/1.4 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    background: #FBF6EC; padding: 8px; border-radius: 8px; }}
  a {{ color: #1F6B4A; }}
  svg {{ width: 100%; height: auto; }}
  .chip {{ display: inline-flex; align-items: center; gap: 6px; margin-right: 12px; font-size: 14px; }}
  .chip i {{ width: 12px; height: 12px; border-radius: 99px; display: inline-block; }}
  @page {{ size: letter; margin: 0.5in; }}
  @media print {{
    body {{ background: #fff; }}
    header, .card, .sheet {{ box-shadow: none; }}
    a {{ color: inherit; text-decoration: none; }}
  }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def _display_source(source: object) -> str:
    text = str(source or "")
    suffix = ""
    path_text = text
    if "#" in text:
        path_text, index = text.rsplit("#", 1)
        suffix = "#" + index
    path = Path(path_text)
    try:
        shown = str(path.resolve().relative_to(Path.cwd().resolve()))
    except (ValueError, OSError):
        shown = path.name
    return shown + suffix


def _fmt_percent(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.1f}%"


def _fmt_slope(value: float | None) -> str:
    if value is None:
        return "not enough percents"
    return f"{value:+.1f} percentage points per week"


def _as_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _num(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.2f}"
    return ""


def _slug(name: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in name)
    return "-".join(part for part in cleaned.split("-") if part)


def esc(value: object) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)
