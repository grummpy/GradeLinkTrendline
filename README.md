![GradeLink Trendline](docs/cover.jpg)

# GradeLink Trendline

A parent gets low-grade alert mail from a school information system (senders such as `alerts@gradelink.com`) for two kids. GradeLink Trendline parses those messages on your own machine into per-student, per-subject observations and shows the trend, so a repeat run of alerts in a subject such as Penmanship or Science is visible before report cards.

The figures count alert emails and recorded scores. They are not a statement about ability, and the tool does not diagnose anything.

## Install

Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

`pandas` is the only runtime dependency. The dashboard is a self-contained HTML file with inline SVG. It does not load chart libraries or any other asset from a CDN.

## Run

Put `.eml` files or an `.mbox` export in a folder, then:

```bash
glt ingest tests/fixtures/inbox
glt report
glt serve
```

- `glt ingest` reads the folder into `data/glt.sqlite` (gitignored). A message id that is already stored is skipped.
- `glt report` writes `data/reports/index.html`, a printable one-page `summary-<student>.html` per student, CSV files, and a weekly text summary.
- `glt serve` rebuilds that report and serves it on `127.0.0.1:8765` only. Other hosts are refused.

Open `http://127.0.0.1:8765`. The review queue is on the dashboard and is also counted in the ingest output.

The fixtures are fictional: students are Student A and Student B, teachers are Ms. Rivera, Ms. Okonkwo, Mr. Chen, and Mx. Adler, and every address is `@example.com`.

## Privacy

This repository is public.

- Do not commit real emails, names, or grades. `data/` and `secrets/` are gitignored.
- Synthetic fixtures are the only mail in git. `pytest` fails if a fixture contains an email address whose domain is not `example.com`.
- Reports display a path relative to the current directory, or only the file name when the file lives outside it.
- The optional Gmail command is off unless you run it. It asks for the `gmail.readonly` scope only, reads an OAuth client file you supply, and writes tokens to `secrets/gmail_token.json`. No client secret or token is stored in the repo.

## Supported formats

Drop a directory, a `.eml` file, or an `.mbox` file on `glt ingest`. Parsers are separate patterns. Each one records only fields it can point at, plus a confidence score and the unparsed remainder.

| Pattern | What it looks for |
| --- | --- |
| `labeled-fields` | Lines such as `Student:`, `Course:` / `Subject:` / `Class:`, `Assignment:`, `Score:`, `Letter:`, `Percent:`, `Date:`, `Teacher:` |
| `html-table` | An HTML table with those labels in header cells |
| `prose-alert` | A sentence such as "Student A received a low grade in Math." |
| `compact-row` | One pipe-separated row: student, subject, assignment, category, score, letter, percent, date, teacher |
| `assignment-rows` | Several `Assignment: ... \| Category: ... \| Score: ...` lines under a shared header |

A row is **confirmed** only when it has a student, a subject, a date, and a grade signal (a percent or a letter), confidence is at least 0.75, and no field is in conflict. Everything else stays in the review queue and is left off the charts.

Field rules, so the parser does not guess:

- A letter is never turned into a percent. A score without points possible is not turned into a percent.
- A percent written next to a fraction is kept only when the two agree within 0.5 points. Otherwise the percent is left empty and the row is reviewed.
- Two different values for the same field are a conflict. The field is left empty.
- `2026-09-14` and `September 8, 2026` are dates. A numeric date is stored only when just one of month/day or day/month is a real calendar date. `03/04/2026` is reviewed, not guessed.
- If the body has no date field, the message `Date` header can fill the date, and the note says so. An unreadable date in the body blocks that fallback.
- `Class: Penmanship - Period 2` keeps `Penmanship` and notes that the period suffix was removed.

You can pass your own pattern objects to `parse_message` if a new layout shows up. Low-confidence mail stays in the queue until a pattern actually matches it.

## Trends

Confirmed observations, per student and subject:

- **Low-grade alert:** percent under 70, or a letter of D or F when the message has no percent. A percent of 70 is not under the line. If the letter and the percent disagree, the row is not counted.
- **14-day rolling average:** mean of recorded percents in the trailing 14 days, ending on that observation's date.
- **Low-grade alerts per 2-week window:** counts in non-overlapping 14-day bins anchored on the first confirmed date for that student and subject.
- **Repeat-trouble flag:** 3 or more low-grade alerts in that subject within any 21-day span.
- **Slope:** ordinary least-squares fit of percent against days, reported as percentage points per week. It is omitted when fewer than two different days have a percent. It is not a forecast.
- **Weekly summary:** counts for that ISO week (Monday start), plus the repeat-trouble flag when it applies.

`glt report` also writes a one-page sheet per student for a parent-teacher or tutor conversation: subject table, the latest observations, and a few questions about assignments and categories. Older rows stay on the dashboard so the sheet can stay on one page.

## Optional Gmail fetch

This does not run during ingest.

```bash
glt fetch-gmail --client secrets/gmail_client.json --out data/gmail
glt ingest data/gmail
```

Create an OAuth desktop client in Google Cloud and download its JSON to `secrets/gmail_client.json` (gitignored). The browser step requests only `https://www.googleapis.com/auth/gmail.readonly`. The default query is `from:alerts@gradelink.com newer_than:365d`. Tokens are written under `secrets/`, not into the repository. A token that comes back with any other scope is refused.

## Tests

```bash
pytest
ruff check .
```

The suite covers the parser on the synthetic variants (including malformed, ambiguous, and empty messages), message-id dedupe, the rolling average, 14-day windows, the repeat-trouble flag, slope, report HTML, the loopback server, the fixture email-address gate, and the Gmail scope guard.

Regenerate the fixture files with `python tests/fixtures/build_fixtures.py` after editing that script. The generated mail is what the tests read.

## Limitations

- The patterns were built for the layouts in `tests/fixtures`, not from a live GradeLink template. Real alerts that use another layout stay in the review queue until a pattern is added. That is intentional: the tool does not invent a student, subject, or score to make a chart.
- There is no screen for editing or approving a review item. Fix the pattern, or leave the row out of the trends.
- Dedupe is by `Message-ID`. A later copy with the same id is ignored, even if the body changed. A file with no id is keyed by a hash of the raw bytes.
- Message-header dates are the UTC calendar date of the `Date` header. A late evening in another timezone can land on the next UTC day, and the note records that the body did not contain the date.
- The rolling average and the slope use percents only. Letter-only alerts still count as low-grade alerts, and they are not given a made-up percent on the chart.
- Repeat trouble is an alert count inside 21 days. It is not a description of the child.
- The printable sheet lists the eight latest observations. A longer history is on the dashboard, so a very full term may not fit the paper page if you print the dashboard instead.
- `glt serve` is a local static file server. It is not an account system and it is not reachable on a public interface.
- The Gmail fetcher is covered with fake HTTP responses. It has not been run against a live mailbox here.
- The picture at the top of this file is a recreation of the GradeLink Trendline illustration attached with the project brief. Use that file as `docs/cover.jpg`.
