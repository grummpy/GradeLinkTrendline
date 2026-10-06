from datetime import date, timedelta

import pytest

from gradelinktrendline.trends import (
    analyze,
    classify_low,
    contains_banned_label,
    repeat_trouble,
    rolling_averages,
    slope_per_week,
    two_week_windows,
)


def test_classify_low_never_mixes_contradictions():
    assert classify_low(69, "D") is True
    assert classify_low(70, "C") is False
    assert classify_low(70, None) is False
    assert classify_low(None, "D") is True
    assert classify_low(None, "B") is False
    assert classify_low(80, None) is False
    assert classify_low(None, None) is None
    assert classify_low(50, "C") is None
    assert classify_low(90, "F") is None


def test_rolling_average_uses_a_trailing_14_day_window():
    origin = date(2026, 9, 1)
    dates = [origin, origin + timedelta(days=7), origin + timedelta(days=14)]
    averages = rolling_averages(dates, [64, 61, 58])
    assert averages[0] == 64
    assert averages[1] == (64 + 61) / 2
    assert averages[2] == (61 + 58) / 2


def test_two_week_windows_count_lows_only():
    origin = date(2026, 9, 1)
    dates = [origin, origin + timedelta(days=7), origin + timedelta(days=14), origin + timedelta(days=20)]
    windows = two_week_windows(dates, [True, True, True, False], origin=origin)
    assert [(window.start, window.low_alerts) for window in windows] == [
        (date(2026, 9, 1), 2),
        (date(2026, 9, 15), 1),
    ]


def test_repeat_trouble_flag():
    origin = date(2026, 9, 1)
    assert repeat_trouble([origin, origin + timedelta(days=10), origin + timedelta(days=21)])[0] is True
    assert repeat_trouble([origin, origin + timedelta(days=10)])[0] is False
    assert repeat_trouble([origin, origin + timedelta(days=11), origin + timedelta(days=22)])[0] is False
    assert repeat_trouble([origin, origin, origin])[0] is True


def test_slope_matches_hand_fit_and_stays_empty_when_underdetermined():
    origin = date(2026, 9, 1)
    dates = [origin + timedelta(days=day) for day in (0, 7, 14, 19)]
    assert slope_per_week(dates, [64, 61, 58, 60]) == pytest.approx((-51 / 206) * 7)
    assert slope_per_week([origin], [50]) is None
    assert slope_per_week([origin, origin], [50, 80]) is None
    assert slope_per_week([origin, origin + timedelta(days=7)], [None, 80]) is None


def test_weekly_summary_states_counts_without_ability_labels():
    rows = []
    for offset, percent in ((0, 66), (8, 62), (15, 58)):
        rows.append(
            {
                "student": "Student A",
                "subject": "Penmanship",
                "observed_on": date(2026, 9, 1) + timedelta(days=offset),
                "percent": percent,
                "letter": "D",
                "assignment": "Journal",
                "category": "Homework",
                "teacher": "Ms. Rivera",
                "needs_review": False,
                "message_id": f"m{offset}",
            }
        )
    analysis = analyze(rows)
    summary = analysis.subjects[0]
    assert summary.repeat_trouble is True
    assert summary.low_alert_count == 3
    assert summary.slope_per_week is not None
    assert summary.slope_per_week < 0
    text = "\n".join(note.text for note in analysis.weeks)
    assert "Penmanship" in text
    assert "low-grade alert" in text
    assert "repeat-trouble flag" in text
    assert "not a statement about ability" in text
    assert contains_banned_label(text) is False


def test_review_rows_are_left_out_of_the_series():
    analysis = analyze(
        [
            {
                "student": "Student A",
                "subject": "Math",
                "observed_on": date(2026, 9, 1),
                "percent": 10,
                "letter": "A",
                "needs_review": True,
                "message_id": "bad",
            }
        ]
    )
    assert analysis.subjects == []
