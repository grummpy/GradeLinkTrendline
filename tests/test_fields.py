from datetime import date

from gradelinktrendline.fields import parse_date, parse_points


def test_iso_and_month_name_dates():
    assert parse_date("2026-09-14").value == date(2026, 9, 14)
    assert parse_date("September 8, 2026").value == date(2026, 9, 8)
    assert parse_date("Sep 8, 2026").value == date(2026, 9, 8)


def test_numeric_date_is_stored_only_when_one_order_is_possible():
    ambiguous = parse_date("03/04/2026")
    assert ambiguous.value is None
    assert ambiguous.blocked
    assert any("ambiguous" in note for note in ambiguous.notes)

    month_first = parse_date("09/21/2026")
    assert month_first.value == date(2026, 9, 21)

    day_first = parse_date("21/09/2026")
    assert day_first.value == date(2026, 9, 21)


def test_fraction_percent_must_agree_with_stated_percent():
    agreed = parse_points("11 out of 20 (55%, F)")
    assert agreed.score == 11
    assert agreed.points_possible == 20
    assert agreed.percent == 55
    assert agreed.percent_source == "stated"
    assert agreed.letter == "F"
    assert agreed.conflicts == []

    conflict = parse_points("10/20 (40%)")
    assert conflict.percent is None
    assert conflict.conflicts
    assert conflict.score == 10


def test_bare_score_does_not_invent_a_percent():
    parsed = parse_points("62")
    assert parsed.score == 62
    assert parsed.percent is None
    assert parsed.points_possible is None


def test_letter_alone_is_not_a_percent():
    parsed = parse_points("D")
    assert parsed.percent is None
    assert parsed.letter is None or parsed.conflicts
