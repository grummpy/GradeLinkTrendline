import threading
import urllib.request
from pathlib import Path

from gradelinktrendline.cli import main, make_server
from gradelinktrendline.pipeline import ingest_path
from gradelinktrendline.report import write_report
from gradelinktrendline.store import Store
from gradelinktrendline.trends import contains_banned_label

FIXTURES = Path(__file__).parent / "fixtures" / "inbox"

REPEAT = {
    ("Student A", "Penmanship"): True,
    ("Student A", "Math"): False,
    ("Student A", "Science"): False,
    ("Student A", "History"): True,
    ("Student B", "Science"): True,
    ("Student B", "Math"): False,
    ("Student B", "History"): False,
    ("Student B", "Penmanship"): False,
}


def _ingest(tmp_path: Path) -> Store:
    store = Store(tmp_path / "glt.sqlite")
    stats = ingest_path(FIXTURES, store)
    assert stats.duplicates == 1
    assert stats.messages_inserted == stats.messages_seen - 1
    return store


def test_dedupe_by_message_id(tmp_path: Path):
    store = _ingest(tmp_path)
    first = len(store.observation_rows())
    again = ingest_path(FIXTURES, store)
    assert again.duplicates == again.messages_seen
    assert again.messages_inserted == 0
    assert len(store.observation_rows()) == first
    store.close()


def test_confirmed_rows_have_identity_grade_and_date(tmp_path: Path):
    store = _ingest(tmp_path)
    rows = store.observation_rows()
    store.close()
    confirmed = [row for row in rows if not row["needs_review"]]
    review = [row for row in rows if row["needs_review"]]
    assert len(review) == 6
    assert confirmed
    for row in confirmed:
        assert row["student"] in {"Student A", "Student B"}
        assert row["subject"]
        assert row["observed_on"]
        assert row["percent"] is not None or row["letter"]
    ids = [row["message_id"] for row in rows]
    assert ids.count("<a-penmanship-0901@example.com>") == 1


def test_repeat_flags_and_slopes(tmp_path: Path):
    store = _ingest(tmp_path)
    rows = store.observation_rows()
    store.close()
    analysis = write_report(rows, tmp_path / "reports")
    found = {(item.student, item.subject): item for item in analysis.subjects}
    for key, flagged in REPEAT.items():
        assert found[key].repeat_trouble is flagged
    assert found[("Student A", "Math")].slope_per_week is not None
    assert found[("Student A", "Math")].slope_per_week > 0
    assert found[("Student B", "History")].slope_per_week is None
    assert found[("Student B", "Penmanship")].slope_per_week is None
    assert found[("Student A", "Penmanship")].low_alert_count == 3


def test_report_is_local_and_neutral(tmp_path: Path):
    store = _ingest(tmp_path)
    rows = store.observation_rows()
    store.close()
    out = tmp_path / "reports"
    write_report(rows, out)
    index = (out / "index.html").read_text(encoding="utf-8")
    summary = (out / "summary-student-a.html").read_text(encoding="utf-8")
    weekly = (out / "weekly.txt").read_text(encoding="utf-8")
    for text in (index, summary, weekly):
        assert "https://" not in text
        assert "http://" not in text
        assert "<script" not in text.lower()
        assert "cdn" not in text.lower()
        assert contains_banned_label(text) is False
    assert "Student A" in index
    assert "Penmanship" in index
    assert "<svg" in index
    assert "Review queue" in index
    assert "not a statement about ability" in summary
    assert "parent-teacher or tutor" in summary
    assert "Repeat trouble" in summary or "repeat" in summary.lower()
    assert (out / "observations.csv").exists()
    assert (out / "windows.csv").exists()
    assert "/home/" not in index


def test_cli_ingest_and_report(tmp_path: Path):
    db = tmp_path / "glt.sqlite"
    out = tmp_path / "out"
    assert main(["ingest", str(FIXTURES), "--db", str(db)]) == 0
    assert main(["report", "--db", str(db), "--out", str(out)]) == 0
    assert (out / "index.html").exists()
    assert main(["ingest", str(tmp_path / "missing"), "--db", str(db)]) == 1


def test_serve_refuses_non_loopback(tmp_path: Path):
    try:
        code = main(["serve", "--host", "0.0.0.0", "--db", str(tmp_path / "missing.sqlite")])
    except SystemExit as exc:
        code = exc.code
    assert code != 0


def test_serve_answers_on_loopback(tmp_path: Path):
    db = tmp_path / "glt.sqlite"
    out = tmp_path / "out"
    assert main(["ingest", str(FIXTURES), "--db", str(db)]) == 0
    assert main(["report", "--db", str(db), "--out", str(out)]) == 0
    server = make_server("127.0.0.1", 0, out)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/index.html", timeout=5) as response:
            body = response.read().decode("utf-8")
            status = response.status
        with urllib.request.urlopen(f"http://{host}:{port}/summary-student-b.html", timeout=5) as response:
            summary = response.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert status == 200
    assert "GradeLink" in body
    assert "Student B" in summary
    assert "https://" not in body
