"""Command line: glt ingest, glt report, glt serve, and optional glt fetch-gmail."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from gradelinktrendline.gmail_fetch import (
    DEFAULT_CLIENT,
    DEFAULT_QUERY,
    DEFAULT_TOKEN,
    GmailConfigError,
    fetch_gmail,
)
from gradelinktrendline.pipeline import ingest_path
from gradelinktrendline.report import write_report
from gradelinktrendline.store import Store

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


def assert_loopback(host: str) -> str:
    if host not in LOOPBACK_HOSTS:
        raise SystemExit(f"glt serve only binds to loopback; refused host {host}")
    if host == "localhost":
        return "127.0.0.1"
    return host


def make_server(host: str, port: int, directory: Path) -> ThreadingHTTPServer:
    bound = assert_loopback(host)
    handler = partial(QuietHandler, directory=str(directory))
    return ThreadingHTTPServer((bound, port), handler)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except GmailConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="glt",
        description="Parse GradeLink low-grade alert mail into local trend charts.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Parse .eml files or an mbox export into the local database")
    ingest.add_argument("path", type=Path)
    ingest.add_argument("--db", type=Path, default=Path("data/glt.sqlite"))
    ingest.set_defaults(func=cmd_ingest)

    report = sub.add_parser("report", help="Write the dashboard, printable summaries, and CSV")
    report.add_argument("--db", type=Path, default=Path("data/glt.sqlite"))
    report.add_argument("--out", type=Path, default=Path("data/reports"))
    report.add_argument(
        "--term-boundary",
        type=_date_arg,
        action="append",
        default=[],
        metavar="YYYY-MM-DD",
        help="Start a new explicit reporting term on this date; repeat for multiple boundaries.",
    )
    report.set_defaults(func=cmd_report)

    serve = sub.add_parser("serve", help="Serve the dashboard on 127.0.0.1")
    serve.add_argument("--db", type=Path, default=Path("data/glt.sqlite"))
    serve.add_argument("--out", type=Path, default=Path("data/reports"))
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument(
        "--term-boundary",
        type=_date_arg,
        action="append",
        default=[],
        metavar="YYYY-MM-DD",
        help="Start a new explicit reporting term on this date; repeat for multiple boundaries.",
    )
    serve.set_defaults(func=cmd_serve)

    review = sub.add_parser("review", help="List unresolved parser items in the local review queue")
    review.add_argument("--db", type=Path, default=Path("data/glt.sqlite"))
    review.set_defaults(func=cmd_review)

    resolve = sub.add_parser(
        "resolve-review",
        help="Save an explicit local resolution for one review item without changing parsed evidence",
    )
    resolve.add_argument("observation_id", type=int)
    resolve.add_argument("--db", type=Path, default=Path("data/glt.sqlite"))
    resolve.add_argument("--student", required=True)
    resolve.add_argument("--subject", required=True)
    resolve.add_argument("--date", dest="observed_on", type=_date_arg, required=True, metavar="YYYY-MM-DD")
    grade = resolve.add_mutually_exclusive_group(required=True)
    grade.add_argument("--percent", type=float)
    grade.add_argument("--letter")
    resolve.add_argument("--rationale", required=True)
    resolve.add_argument("--assignment")
    resolve.add_argument("--category")
    resolve.add_argument("--teacher")
    resolve.set_defaults(func=cmd_resolve_review)

    fetch = sub.add_parser(
        "fetch-gmail",
        help="Optional read-only Gmail download. Not used unless you run this command.",
    )
    fetch.add_argument("--client", type=Path, default=DEFAULT_CLIENT)
    fetch.add_argument("--token", type=Path, default=DEFAULT_TOKEN)
    fetch.add_argument("--out", type=Path, default=Path("data/gmail"))
    fetch.add_argument("--query", default=DEFAULT_QUERY)
    fetch.set_defaults(func=cmd_fetch)
    return parser


def cmd_ingest(args: argparse.Namespace) -> int:
    if not args.path.exists():
        print(f"input path not found: {args.path}", file=sys.stderr)
        return 1
    store = Store(args.db)
    try:
        stats = ingest_path(args.path, store)
    finally:
        store.close()
    print(
        f"seen {stats.messages_seen} messages, inserted {stats.messages_inserted}, "
        f"skipped {stats.duplicates} duplicates, {stats.observations} observations, "
        f"{stats.review} in the review queue"
    )
    print(f"database: {args.db}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    if not args.db.exists():
        print(f"database not found: {args.db}. Run glt ingest first.", file=sys.stderr)
        return 1
    store = Store(args.db)
    try:
        rows = store.observation_rows()
    finally:
        store.close()
    analysis = write_report(rows, args.out, term_boundaries=args.term_boundary)
    review = sum(1 for row in rows if row.get("needs_review"))
    print(
        f"wrote {args.out / 'index.html'} "
        f"({len(analysis.subjects)} subject series, {review} in the review queue)"
    )
    for note in analysis.weeks:
        print()
        print(note.text)
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    host = assert_loopback(args.host)
    if not args.db.exists():
        print(f"database not found: {args.db}. Run glt ingest first.", file=sys.stderr)
        return 1
    store = Store(args.db)
    try:
        rows = store.observation_rows()
    finally:
        store.close()
    write_report(rows, args.out, term_boundaries=args.term_boundary)
    server = make_server(host, args.port, args.out)
    bound_host, bound_port = server.server_address[:2]
    print(f"serving {args.out} at http://{bound_host}:{bound_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopped")
    finally:
        server.server_close()
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    count = fetch_gmail(args.client, args.token, args.out, query=args.query)
    print(f"saved {count} messages to {args.out}")
    print("Gmail fetch is read-only. Ingest the folder with glt ingest when you want it in the database.")
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    if not args.db.exists():
        print(f"database not found: {args.db}. Run glt ingest first.", file=sys.stderr)
        return 1
    store = Store(args.db)
    try:
        rows = store.review_rows()
    finally:
        store.close()
    if not rows:
        print("review queue is empty")
        return 0
    for row in rows:
        reasons = "; ".join(str(reason) for reason in row["review_reasons"])
        print(
            f"{row['id']}: source={row['source']} student={row.get('student') or '—'} "
            f"subject={row.get('subject') or '—'} date={row.get('observed_on') or '—'} "
            f"reasons={reasons}"
        )
    return 0


def cmd_resolve_review(args: argparse.Namespace) -> int:
    if not args.db.exists():
        print(f"database not found: {args.db}. Run glt ingest first.", file=sys.stderr)
        return 1
    store = Store(args.db)
    try:
        store.resolve_review(
            args.observation_id,
            student=args.student,
            subject=args.subject,
            observed_on=args.observed_on,
            percent=args.percent,
            letter=args.letter,
            rationale=args.rationale,
            assignment=args.assignment,
            category=args.category,
            teacher=args.teacher,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        store.close()
    print(f"saved local resolution for review observation {args.observation_id}")
    return 0


def _date_arg(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc
