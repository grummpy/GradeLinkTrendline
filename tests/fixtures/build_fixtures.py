"""Write synthetic .eml and .mbox fixtures. Students and teachers are fictional."""

from __future__ import annotations

from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path

OUT = Path(__file__).parent / "inbox"


def render(spec: dict[str, object]) -> bytes:
    msg = EmailMessage()
    msg["From"] = "GradeLink Alerts <alerts@example.com>"
    msg["To"] = "Parent <parent@example.com>"
    msg["Subject"] = str(spec["subject_line"])
    when = spec["header_date"]
    assert isinstance(when, datetime)
    msg["Date"] = format_datetime(when)
    message_id = spec.get("message_id")
    if message_id:
        msg["Message-ID"] = str(message_id)
    body = spec.get("body")
    if spec.get("html"):
        msg.set_content(str(body), subtype="html", charset="utf-8")
    else:
        msg.set_content("" if body is None else str(body), subtype="plain", charset="utf-8")
    return msg.as_bytes()


def labeled(
    *,
    slug: str,
    student: str,
    subject: str,
    teacher: str,
    assignment: str,
    category: str,
    earned: int,
    possible: int,
    letter: str,
    percent: int,
    observed: str,
    subject_key: str = "Course",
    header_date: datetime,
) -> dict[str, object]:
    body = (
        f"Student: {student}\n"
        f"{subject_key}: {subject}\n"
        f"Teacher: {teacher}\n"
        f"Assignment: {assignment}\n"
        f"Category: {category}\n"
        f"Score: {earned}/{possible}\n"
        f"Letter: {letter}\n"
        f"Percent: {percent}%\n"
        f"Date: {observed}\n"
        f"\n"
        f"Fixture footer {slug}.\n"
        "This is a fictional automated alert from Example Academy.\n"
    )
    return {
        "name": f"{slug}.eml",
        "subject_line": f"Low grade alert: {student} - {subject}",
        "header_date": header_date,
        "message_id": f"<{slug}@example.com>",
        "body": body,
    }


def utc(year: int, month: int, day: int, hour: int = 15) -> datetime:
    return datetime(year, month, day, hour, 0, tzinfo=UTC)


SPECS: list[dict[str, object]] = [
    labeled(
        slug="a-penmanship-0901",
        student="Student A",
        subject="Penmanship",
        teacher="Ms. Rivera",
        assignment="Cursive Packet",
        category="Homework",
        earned=66,
        possible=100,
        letter="D",
        percent=66,
        observed="2026-09-01",
        header_date=utc(2026, 9, 1),
    ),
    {
        "name": "a-penmanship-0909.eml",
        "subject_line": "Low grade alert: Student A - Penmanship",
        "header_date": utc(2026, 9, 9),
        "message_id": "<a-penmanship-0909@example.com>",
        "body": (
            "Student Name: Student A\n"
            "Class: Penmanship - Period 2\n"
            "Instructor: Ms. Rivera\n"
            "Work Item: Weekly Journal\n"
            "Grade Category: Classwork\n"
            "Points: 62 of 100\n"
            "Grade Letter: D\n"
            "Recorded On: September 9, 2026\n"
            "\n"
            "Fixture footer a-penmanship-0909.\n"
        ),
    },
    labeled(
        slug="a-penmanship-0916",
        student="Student A",
        subject="Penmanship",
        teacher="Ms. Rivera",
        assignment="Handwriting Quiz",
        category="Quizzes",
        earned=58,
        possible=100,
        letter="F",
        percent=58,
        observed="2026-09-16",
        subject_key="Subject",
        header_date=utc(2026, 9, 16),
    ),
    labeled(
        slug="a-penmanship-0928",
        student="Student A",
        subject="Penmanship",
        teacher="Ms. Rivera",
        assignment="Makeup Sheet",
        category="Classwork",
        earned=71,
        possible=100,
        letter="C",
        percent=71,
        observed="2026-09-28",
        header_date=utc(2026, 9, 28),
    ),
    {
        "name": "a-math-0820.eml",
        "subject_line": "Low grade alert: Student A - Math",
        "header_date": utc(2026, 8, 20),
        "message_id": "<a-math-0820@example.com>",
        "body": (
            "Student A received a low grade in Math.\n"
            "\n"
            "Assignment: Chapter Quiz\n"
            "Category: Quizzes\n"
            "Score: 61 out of 100 (61%, D)\n"
            "Teacher: Ms. Okonkwo\n"
            "Date: 2026-08-20\n"
            "\n"
            "Fixture footer a-math-0820.\n"
        ),
    },
    labeled(
        slug="a-math-0903",
        student="Student A",
        subject="Math",
        teacher="Ms. Okonkwo",
        assignment="Problem Set",
        category="Homework",
        earned=68,
        possible=100,
        letter="D",
        percent=68,
        observed="2026-09-03",
        header_date=utc(2026, 9, 3),
    ),
    labeled(
        slug="a-math-0917",
        student="Student A",
        subject="Math",
        teacher="Ms. Okonkwo",
        assignment="Check-in",
        category="Classwork",
        earned=74,
        possible=100,
        letter="C",
        percent=74,
        observed="2026-09-17",
        header_date=utc(2026, 9, 17),
    ),
    labeled(
        slug="a-math-1001",
        student="Student A",
        subject="Math",
        teacher="Ms. Okonkwo",
        assignment="Unit Review",
        category="Quizzes",
        earned=82,
        possible=100,
        letter="B",
        percent=82,
        observed="2026-10-01",
        header_date=utc(2026, 10, 1),
    ),
    {
        "name": "a-science-0904.eml",
        "subject_line": "Low grade alert: Student A - Science",
        "header_date": utc(2026, 9, 4),
        "message_id": "<a-science-0904@example.com>",
        "body": (
            "Student: Student A\n"
            "Subject: Science\n"
            "Assignment: Lab Safety Quiz\n"
            "Category: Quizzes\n"
            "Score: 16/25\n"
            "Letter: D\n"
            "Percent: 64%\n"
            "Date: September 4, 2026\n"
            "Teacher: Mr. Chen\n"
            "\n"
            "Fixture footer a-science-0904.\n"
        ),
    },
    {
        "name": "a-history-0911.eml",
        "subject_line": "Low grade alert: Student A - History",
        "header_date": utc(2026, 9, 11),
        "message_id": "<a-history-0911@example.com>",
        "body": (
            "Student A | History | Map Quiz | Quizzes | 59/100 | F | 59% | 2026-09-11 | Mx. Adler\n"
            "\n"
            "Fixture footer a-history-0911.\n"
        ),
    },
    labeled(
        slug="a-history-0925",
        student="Student A",
        subject="History",
        teacher="Mx. Adler",
        assignment="Essay Outline",
        category="Essays",
        earned=63,
        possible=100,
        letter="D",
        percent=63,
        observed="2026-09-25",
        header_date=utc(2026, 9, 25),
    ),
    {
        "name": "b-science-0818.eml",
        "subject_line": "Low grade alert: Student B - Science",
        "header_date": utc(2026, 8, 18),
        "message_id": "<b-science-0818@example.com>",
        "html": True,
        "body": """<html><body>
<p>Example Academy fictional alert.</p>
<table>
<tr><th>Student Name</th><td>Student B</td></tr>
<tr><th>Subject</th><td>Science</td></tr>
<tr><th>Assignment Title</th><td>Lab 1</td></tr>
<tr><th>Category</th><td>Labs</td></tr>
<tr><th>Points</th><td>11/20</td></tr>
<tr><th>Letter Grade</th><td>F</td></tr>
<tr><th>Percentage</th><td>55%</td></tr>
<tr><th>Posted</th><td>August 18, 2026</td></tr>
<tr><th>Teacher</th><td>Mr. Chen</td></tr>
</table>
<p>Fixture footer b-science-0818.</p>
</body></html>
""",
    },
    labeled(
        slug="b-science-0828",
        student="Student B",
        subject="Science",
        teacher="Mr. Chen",
        assignment="Quiz 2",
        category="Quizzes",
        earned=60,
        possible=100,
        letter="D",
        percent=60,
        observed="2026-08-28",
        header_date=utc(2026, 8, 28),
    ),
    labeled(
        slug="b-science-0905",
        student="Student B",
        subject="Science",
        teacher="Mr. Chen",
        assignment="Chapter Test",
        category="Tests",
        earned=58,
        possible=100,
        letter="F",
        percent=58,
        observed="2026-09-05",
        header_date=utc(2026, 9, 5),
    ),
    labeled(
        slug="b-science-0922",
        student="Student B",
        subject="Science",
        teacher="Mr. Chen",
        assignment="Lab 4",
        category="Labs",
        earned=67,
        possible=100,
        letter="D",
        percent=67,
        observed="2026-09-22",
        header_date=utc(2026, 9, 22),
    ),
    labeled(
        slug="b-math-0912",
        student="Student B",
        subject="Math",
        teacher="Ms. Okonkwo",
        assignment="Warmup",
        category="Classwork",
        earned=69,
        possible=100,
        letter="D",
        percent=69,
        observed="2026-09-12",
        header_date=utc(2026, 9, 12),
    ),
    {
        "name": "b-history-0918.eml",
        "subject_line": "Low grade alert: Student B - History",
        "header_date": utc(2026, 9, 18),
        "message_id": "<b-history-0918@example.com>",
        "body": (
            "Student: Student B\n"
            "Subject: History\n"
            "Assignment: Essay Draft\n"
            "Teacher: Mx. Adler\n"
            "Letter: D\n"
            "Date: 2026-09-18\n"
            "\n"
            "Fixture footer b-history-0918.\n"
        ),
    },
    {
        "name": "malformed-missing-student.eml",
        "subject_line": "Low grade alert",
        "header_date": utc(2026, 9, 1, 12),
        "message_id": "<malformed-missing-student@example.com>",
        "body": (
            "Subject: Penmanship\n"
            "Percent: 60%\n"
            "Date: 2026-09-01\n"
            "Assignment: Journal\n"
            "Teacher: Ms. Rivera\n"
            "\n"
            "Fixture footer malformed-missing-student.\n"
        ),
    },
    {
        "name": "malformed-garbled.eml",
        "subject_line": "Notice",
        "header_date": utc(2026, 9, 2),
        "message_id": "<malformed-garbled@example.com>",
        "body": (
            "Hello the grade is somewhere maybe 12 or banana.\n"
            "Fixture footer malformed-garbled.\n"
        ),
    },
    {
        "name": "malformed-ambiguous-percent.eml",
        "subject_line": "Low grade alert: Student A - Math",
        "header_date": utc(2026, 9, 3, 18),
        "message_id": "<malformed-ambiguous-percent@example.com>",
        "body": (
            "Student: Student A\n"
            "Subject: Math\n"
            "Percent: 61%\n"
            "Percent: 80%\n"
            "Date: 2026-09-03\n"
            "Assignment: Quiz 4\n"
            "Teacher: Ms. Okonkwo\n"
            "\n"
            "Fixture footer malformed-ambiguous-percent.\n"
        ),
    },
    {
        "name": "malformed-fraction-disagrees.eml",
        "subject_line": "Low grade alert: Student B - Science",
        "header_date": utc(2026, 9, 6),
        "message_id": "<malformed-fraction-disagrees@example.com>",
        "body": (
            "Student: Student B\n"
            "Subject: Science\n"
            "Score: 10/20 (40%)\n"
            "Date: 2026-09-06\n"
            "Assignment: Lab\n"
            "Teacher: Mr. Chen\n"
            "\n"
            "Fixture footer malformed-fraction-disagrees.\n"
        ),
    },
    {
        "name": "malformed-empty.eml",
        "subject_line": "Empty notice",
        "header_date": utc(2026, 9, 7),
        "message_id": "<malformed-empty@example.com>",
        "body": None,
    },
    {
        "name": "malformed-ambiguous-date.eml",
        "subject_line": "Low grade alert: Student A - History",
        "header_date": utc(2026, 1, 15),
        "message_id": "<malformed-ambiguous-date@example.com>",
        "body": (
            "Student: Student A\n"
            "Subject: History\n"
            "Percent: 60%\n"
            "Letter: D\n"
            "Date: 03/04/2026\n"
            "Assignment: Timeline\n"
            "Teacher: Mx. Adler\n"
            "\n"
            "Fixture footer malformed-ambiguous-date.\n"
        ),
    },
    {
        "name": "a-science-header-date.eml",
        "subject_line": "Low grade alert: Student A - Science",
        "header_date": utc(2026, 10, 1, 16),
        "message_id": "<a-science-header-date@example.com>",
        "body": (
            "Student: Student A\n"
            "Subject: Science\n"
            "Teacher: Mr. Chen\n"
            "Assignment: Reading Notes\n"
            "Category: Homework\n"
            "Score: 72/100\n"
            "Letter: C\n"
            "Percent: 72%\n"
            "\n"
            "Fixture footer a-science-header-date.\n"
        ),
    },
    {
        "name": "a-science-multi.eml",
        "subject_line": "Low grade alert: Student A - Science",
        "header_date": utc(2026, 9, 10, 17),
        "message_id": "<a-science-multi@example.com>",
        "body": (
            "Student: Student A\n"
            "Subject: Science\n"
            "Teacher: Mr. Chen\n"
            "\n"
            "Assignment: Density Lab | Category: Labs | Score: 14/25 | Letter: F | Percent: 56% | Date: 2026-09-08\n"
            "Assignment: Vocabulary | Category: Homework | Score: 7/10 | Letter: C | Percent: 70% | Date: 2026-09-10\n"
            "\n"
            "Fixture footer a-science-multi.\n"
        ),
    },
    {
        "name": "b-penmanship-0921.eml",
        "subject_line": "Low grade alert: Student B - Penmanship",
        "header_date": utc(2026, 9, 21),
        "message_id": "<b-penmanship-0921@example.com>",
        "body": (
            "Student: Student B\n"
            "Subject: Penmanship\n"
            "Teacher: Ms. Rivera\n"
            "Assignment: Stroke Practice\n"
            "Category: Classwork\n"
            "Score: 64/100\n"
            "Letter: D\n"
            "Percent: 64%\n"
            "Date: 09/21/2026\n"
            "\n"
            "Fixture footer b-penmanship-0921.\n"
        ),
    },
    {
        "name": "a-history-nomsgid.eml",
        "subject_line": "Low grade alert: Student A - History",
        "header_date": utc(2026, 10, 2),
        "message_id": None,
        "body": (
            "Student: Student A\n"
            "Subject: History\n"
            "Teacher: Mx. Adler\n"
            "Assignment: Source Check\n"
            "Category: Homework\n"
            "Score: 65/100\n"
            "Letter: D\n"
            "Percent: 65%\n"
            "Date: 2026-10-02\n"
            "\n"
            "Fixture footer a-history-nomsgid.\n"
        ),
    },
]

MBOX = [
    {
        "subject_line": "Low grade alert: Student B - History",
        "header_date": utc(2026, 10, 3),
        "message_id": "<mbox-b-history-1003@example.com>",
        "body": (
            "Student: Student B\n"
            "Subject: History\n"
            "Teacher: Mx. Adler\n"
            "Assignment: Final Outline\n"
            "Category: Essays\n"
            "Score: 88/100\n"
            "Letter: B\n"
            "Percent: 88%\n"
            "Date: 2026-10-03\n"
            "\n"
            "Fixture footer mbox-b-history-1003.\n"
        ),
    },
    {
        "subject_line": "Score notice: Student A - Math",
        "header_date": utc(2026, 9, 24),
        "message_id": "<mbox-a-math-0924@example.com>",
        "body": (
            "Student: Student A\n"
            "Subject: Math\n"
            "Teacher: Ms. Okonkwo\n"
            "Assignment: Exit Ticket\n"
            "Category: Classwork\n"
            "Score: 71/100\n"
            "Letter: C\n"
            "Percent: 71%\n"
            "Date: 2026-09-24\n"
            "\n"
            "Fixture footer mbox-a-math-0924.\n"
        ),
    },
]


def build_mbox(messages: list[bytes]) -> bytes:
    chunks: list[bytes] = []
    for raw in messages:
        text = raw.replace(b"\r\n", b"\n")
        if not text.endswith(b"\n"):
            text += b"\n"
        chunks.append(b"From glt-fixtures@example.com Mon Aug 18 12:00:00 2026\n")
        for line in text.splitlines(keepends=True):
            if line.startswith(b"From "):
                line = b">" + line
            chunks.append(line)
        chunks.append(b"\n")
    return b"".join(chunks)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for spec in SPECS:
        (OUT / str(spec["name"])).write_bytes(render(spec))
    original = OUT / "a-penmanship-0901.eml"
    (OUT / "dup-a-penmanship-0901.eml").write_bytes(original.read_bytes())
    (OUT / "sample.mbox").write_bytes(build_mbox([render(spec) for spec in MBOX]))


if __name__ == "__main__":
    main()
