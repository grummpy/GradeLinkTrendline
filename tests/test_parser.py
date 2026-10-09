from datetime import date
from pathlib import Path

from gradelinktrendline.mailio import load_messages
from gradelinktrendline.models import Candidate, RawMessage
from gradelinktrendline.parse import parse_message

FIXTURES = Path(__file__).parent / "fixtures" / "inbox"


def _one(name: str):
    messages = load_messages(FIXTURES / name)
    assert len(messages) == 1
    observations = parse_message(messages[0])
    return messages[0], observations


def test_labeled_penmanship_extracts_every_field():
    raw, observations = _one("a-penmanship-0901.eml")
    assert len(observations) == 1
    item = observations[0]
    assert item.needs_review is False
    assert "labeled-fields" in item.pattern_id
    assert item.student == "Student A"
    assert item.subject == "Penmanship"
    assert item.assignment == "Cursive Packet"
    assert item.category == "Homework"
    assert item.score == 66
    assert item.points_possible == 100
    assert item.letter == "D"
    assert item.percent == 66
    assert item.percent_source == "stated"
    assert item.observed_on == date(2026, 9, 1)
    assert item.date_source == "body"
    assert item.teacher == "Ms. Rivera"
    assert "Fixture footer a-penmanship-0901." in item.unparsed_remainder
    assert "Student: Student A" not in item.unparsed_remainder
    assert raw.message_id == "<a-penmanship-0901@example.com>"


def test_alias_block_strips_period_and_computes_percent():
    _, observations = _one("a-penmanship-0909.eml")
    item = observations[0]
    assert item.needs_review is False
    assert item.subject == "Penmanship"
    assert item.assignment == "Weekly Journal"
    assert item.category == "Classwork"
    assert item.teacher == "Ms. Rivera"
    assert item.percent == 62
    assert item.percent_source == "computed"
    assert item.letter == "D"
    assert item.observed_on == date(2026, 9, 9)
    assert any("period suffix" in note for note in item.notes)
    assert any("computed from score" in note for note in item.notes)


def test_prose_and_labels_agree():
    _, observations = _one("a-math-0820.eml")
    item = observations[0]
    assert item.needs_review is False
    assert "prose-alert" in item.pattern_id
    assert "labeled-fields" in item.pattern_id
    assert item.student == "Student A"
    assert item.subject == "Math"
    assert item.percent == 61
    assert item.letter == "D"
    assert item.score == 61
    assert item.points_possible == 100
    assert item.teacher == "Ms. Okonkwo"
    assert item.observed_on == date(2026, 8, 20)
    assert item.assignment == "Chapter Quiz"


def test_compact_row():
    _, observations = _one("a-history-0911.eml")
    item = observations[0]
    assert item.needs_review is False
    assert "compact-row" in item.pattern_id
    assert item.student == "Student A"
    assert item.subject == "History"
    assert item.assignment == "Map Quiz"
    assert item.percent == 59
    assert item.letter == "F"
    assert item.teacher == "Mx. Adler"
    assert item.observed_on == date(2026, 9, 11)
    assert "Fixture footer a-history-0911." in item.unparsed_remainder


def test_html_table():
    _, observations = _one("b-science-0818.eml")
    item = observations[0]
    assert item.needs_review is False
    assert "html-table" in item.pattern_id
    assert item.student == "Student B"
    assert item.subject == "Science"
    assert item.assignment == "Lab 1"
    assert item.category == "Labs"
    assert item.percent == 55
    assert item.letter == "F"
    assert item.teacher == "Mr. Chen"
    assert item.observed_on == date(2026, 8, 18)
    assert "Fixture footer b-science-0818." in item.unparsed_remainder


def test_letter_only_does_not_invent_percent():
    _, observations = _one("b-history-0918.eml")
    item = observations[0]
    assert item.needs_review is False
    assert item.student == "Student B"
    assert item.subject == "History"
    assert item.letter == "D"
    assert item.percent is None
    assert item.percent_source is None
    assert item.observed_on == date(2026, 9, 18)


def test_month_name_date_and_fraction():
    _, observations = _one("a-science-0904.eml")
    item = observations[0]
    assert item.needs_review is False
    assert item.percent == 64
    assert item.score == 16
    assert item.points_possible == 25
    assert item.observed_on == date(2026, 9, 4)


def test_unambiguous_numeric_date():
    _, observations = _one("b-penmanship-0921.eml")
    item = observations[0]
    assert item.needs_review is False
    assert item.observed_on == date(2026, 9, 21)
    assert item.student == "Student B"
    assert item.percent == 64


def test_multi_assignment_rows():
    _, observations = _one("a-science-multi.eml")
    assert len(observations) == 2
    assert all(item.needs_review is False for item in observations)
    by_assignment = {item.assignment: item for item in observations}
    lab = by_assignment["Density Lab"]
    words = by_assignment["Vocabulary"]
    assert lab.percent == 56
    assert lab.letter == "F"
    assert lab.observed_on == date(2026, 9, 8)
    assert lab.student == "Student A"
    assert lab.subject == "Science"
    assert words.percent == 70
    assert words.letter == "C"
    assert words.observed_on == date(2026, 9, 10)
    assert "Fixture footer a-science-multi." in lab.unparsed_remainder


def test_two_compact_rows_remain_two_source_linked_observations():
    raw = RawMessage(
        message_id="<two-compact-rows@example.com>",
        source="memory",
        sender="alerts@example.com",
        subject="alert",
        message_date=None,
        body_text=(
            "Student A | Math | Quiz 1 | Homework | 6/10 | D | 60% | 2026-09-01 | Ms. Rivera\n"
            "Student A | Math | Quiz 2 | Homework | 7/10 | C | 70% | 2026-09-02 | Ms. Rivera\n"
        ),
        body_html="",
        body_sha256="abc",
    )
    observations = parse_message(raw)
    assert len(observations) == 2
    assert {item.assignment for item in observations} == {"Quiz 1", "Quiz 2"}
    assert {item.message_id for item in observations} == {raw.message_id}
    assert [(item.score, item.points_possible, item.percent) for item in observations] == [
        (6, 10, 60),
        (7, 10, 70),
    ]


def test_header_date_is_labeled_when_body_has_none():
    _, observations = _one("a-science-header-date.eml")
    item = observations[0]
    assert item.needs_review is False
    assert item.observed_on == date(2026, 10, 1)
    assert item.date_source == "message-header"
    assert item.percent == 72
    assert any("Date header" in note for note in item.notes)


def test_missing_message_id_uses_content_hash():
    raw, observations = _one("a-history-nomsgid.eml")
    assert raw.message_id.startswith("sha256:")
    assert observations[0].needs_review is False
    assert observations[0].percent == 65
    assert observations[0].observed_on == date(2026, 10, 2)


def test_missing_student_stays_in_review():
    _, observations = _one("malformed-missing-student.eml")
    item = observations[0]
    assert item.needs_review is True
    assert item.student is None
    assert item.subject == "Penmanship"
    assert item.percent == 60
    assert any("missing student" in reason for reason in item.review_reasons)
    assert "Fixture footer malformed-missing-student." in item.unparsed_remainder


def test_garbled_message_is_not_guessed():
    _, observations = _one("malformed-garbled.eml")
    item = observations[0]
    assert item.needs_review is True
    assert item.student is None
    assert item.subject is None
    assert item.percent is None
    assert item.score is None
    assert item.pattern_id == "none"
    assert item.confidence == 0
    assert "banana" in item.unparsed_remainder


def test_ambiguous_percent_is_not_chosen():
    _, observations = _one("malformed-ambiguous-percent.eml")
    item = observations[0]
    assert item.needs_review is True
    assert item.percent is None
    assert item.student == "Student A"
    assert any("percent" in reason for reason in item.review_reasons)


def test_stated_percent_disagreement_is_not_chosen():
    _, observations = _one("malformed-fraction-disagrees.eml")
    item = observations[0]
    assert item.needs_review is True
    assert item.percent is None
    assert item.score == 10
    assert item.points_possible == 20
    assert any("disagrees" in reason for reason in item.review_reasons)


def test_empty_body_is_review_and_ignores_header_date():
    _, observations = _one("malformed-empty.eml")
    item = observations[0]
    assert item.needs_review is True
    assert item.observed_on is None
    assert item.date_source is None
    assert any("empty body" in reason for reason in item.review_reasons)


def test_ambiguous_date_is_not_replaced_by_the_header():
    _, observations = _one("malformed-ambiguous-date.eml")
    item = observations[0]
    assert item.needs_review is True
    assert item.observed_on is None
    assert item.observed_on != date(2026, 1, 15)
    assert any("ambiguous" in reason for reason in item.review_reasons)


def test_mbox_has_two_distinct_messages():
    messages = load_messages(FIXTURES / "sample.mbox")
    assert len(messages) == 2
    parsed = [parse_message(message)[0] for message in messages]
    assert all(item.needs_review is False for item in parsed)
    found = {(item.student, item.subject, item.percent, item.observed_on) for item in parsed}
    assert ("Student B", "History", 88, date(2026, 10, 3)) in found
    assert ("Student A", "Math", 71, date(2026, 9, 24)) in found


def test_cross_pattern_disagreement_does_not_pick_a_subject():
    raw = RawMessage(
        message_id="<conflict@example.com>",
        source="memory",
        sender="alerts@example.com",
        subject="alert",
        message_date=None,
        body_text=(
            "Student A received a low grade in Math.\n"
            "Subject: Science\n"
            "Percent: 50%\n"
            "Date: 2026-09-01\n"
            "Assignment: Quiz\n"
            "Teacher: Mr. Chen\n"
        ),
        body_html="",
        body_sha256="abc",
    )
    observations = parse_message(raw)
    assert len(observations) == 1
    item = observations[0]
    assert item.needs_review is True
    assert item.subject is None
    assert item.percent == 50
    assert any("conflict on subject" in reason for reason in item.review_reasons)


def test_custom_pattern_can_be_registered():
    class Marker:
        pattern_id = "custom-demo"
        emits_rows = False

        def apply(self, raw: RawMessage) -> list[Candidate]:
            if "CUSTOM-MARKER" not in raw.body_text:
                return []
            return [
                Candidate(
                    pattern_id="custom-demo",
                    student="Student A",
                    subject="Art",
                    assignment="Sketch",
                    category="Classwork",
                    percent=40,
                    percent_source="stated",
                    observed_on=date(2026, 9, 1),
                    date_source="body",
                    teacher="Ms. Rivera",
                )
            ]

    raw = RawMessage(
        message_id="<custom@example.com>",
        source="memory",
        sender="alerts@example.com",
        subject="alert",
        message_date=None,
        body_text="CUSTOM-MARKER\n",
        body_html="",
        body_sha256="abc",
    )
    observations = parse_message(raw, patterns=[Marker()])
    assert observations[0].subject == "Art"
    assert observations[0].percent == 40
    assert observations[0].pattern_id == "custom-demo"
    assert observations[0].needs_review is False


def test_fixture_folder_covers_many_variants():
    names = sorted(path.name for path in FIXTURES.iterdir() if path.suffix in {".eml", ".mbox"})
    assert len(names) >= 12
