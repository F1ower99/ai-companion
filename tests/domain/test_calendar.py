from datetime import date, time, timedelta, timezone

import pytest

from companion.domain.calendar import (
    AcademicTerm,
    CalendarException,
    CourseRule,
    courses_for_day,
)
from companion.domain.errors import ValidationError


TERM = AcademicTerm(
    id="fall-2026",
    name="Fall 2026",
    start_date=date(2026, 9, 9),
    end_date=date(2026, 10, 13),
    week_one_start=date(2026, 9, 7),
)


def make_rule(rule_id="math-mon", **changes):
    values = {
        "id": rule_id,
        "term_id": TERM.id,
        "weekday": 0,
        "start_week": 1,
        "end_week": 6,
        "week_parity": "all",
        "start_time": time(9, 0),
        "end_time": time(10, 0),
        "course_name": "Math",
    }
    values.update(changes)
    return CourseRule(**values)


def test_term_uses_inclusive_dates_and_explicit_week_one_anchor():
    assert TERM.total_weeks == 6
    assert courses_for_day(date(2026, 9, 9), TERM, [make_rule(weekday=2)], [])
    assert courses_for_day(date(2026, 10, 13), TERM, [make_rule(weekday=1)], [])
    assert courses_for_day(date(2026, 9, 8), TERM, [make_rule(weekday=1)], []) == []
    assert courses_for_day(date(2026, 10, 14), TERM, [make_rule(weekday=2)], []) == []


@pytest.mark.parametrize(
    "values",
    [
        {"start_date": date(2026, 9, 10), "end_date": date(2026, 9, 9)},
        {"start_date": date(2026, 9, 9), "week_one_start": date(2026, 9, 10)},
        {"name": "   "},
        {"end_date": date(2028, 1, 1)},
    ],
)
def test_term_rejects_invalid_ranges_and_names(values):
    current = {
        "id": "fall-2026",
        "name": "Fall 2026",
        "start_date": date(2026, 9, 9),
        "end_date": date(2026, 10, 13),
        "week_one_start": date(2026, 9, 7),
    }
    current.update(values)
    with pytest.raises(ValidationError):
        AcademicTerm(**current)


@pytest.mark.parametrize(
    "day, weekday, week_number",
    [
        (date(2026, 9, 9), 2, 1),  # Partial first week begins midweek.
        (date(2026, 9, 10), 3, 1),
        (date(2026, 9, 14), 0, 2),
    ],
)
def test_weekday_and_week_number_use_python_day_and_one_based_anchor(day, weekday, week_number):
    occurrence = courses_for_day(day, TERM, [make_rule(weekday=weekday)], [])[0]
    assert occurrence.day == day
    assert occurrence.weekday == weekday
    assert occurrence.week_number == week_number


@pytest.mark.parametrize(
    "week_number, parity, expected",
    [(1, "odd", True), (1, "even", False), (2, "odd", False), (2, "even", True)],
)
def test_parity_matches_one_based_teaching_week(week_number, parity, expected):
    day = date(2026, 9, 9) + timedelta(days=7 * (week_number - 1))
    matches = courses_for_day(
        day,
        TERM,
        [make_rule(weekday=day.weekday(), week_parity=parity)],
        [],
    )
    assert bool(matches) is expected


@pytest.mark.parametrize("kind", ["holiday", "rest"])
def test_holiday_and_rest_exceptions_suppress_all_weekly_rules(kind):
    day = date(2026, 9, 7)
    exception = CalendarException(TERM.id, day, kind)
    assert courses_for_day(day, TERM, [make_rule()], [exception]) == []


def test_makeup_uses_replacement_weekday_but_actual_dates_week_number():
    day = date(2026, 9, 19)  # Saturday in teaching week 2 (even).
    exception = CalendarException(TERM.id, day, "makeup", replacement_weekday=2)
    rules = [
        make_rule("wednesday-even", weekday=2, week_parity="even"),
        make_rule("wednesday-odd", weekday=2, week_parity="odd"),
        make_rule("saturday", weekday=5),
    ]
    occurrences = courses_for_day(day, TERM, rules, [exception])
    assert [(item.rule_id, item.week_number, item.weekday) for item in occurrences] == [
        ("wednesday-even", 2, 2),
    ]


def test_makeup_requires_valid_replacement_weekday():
    with pytest.raises(ValidationError):
        CalendarException(TERM.id, date(2026, 9, 19), "makeup")
    with pytest.raises(ValidationError):
        CalendarException(TERM.id, date(2026, 9, 19), "makeup", replacement_weekday=7)
    with pytest.raises(ValidationError):
        CalendarException(TERM.id, date(2026, 9, 19), "holiday", replacement_weekday=0)


def test_duplicate_day_exceptions_are_rejected_instead_of_order_dependent():
    day = date(2026, 9, 19)
    exceptions = [
        CalendarException(TERM.id, day, "rest"),
        CalendarException(TERM.id, day, "makeup", replacement_weekday=2),
    ]
    with pytest.raises(ValidationError, match="one exception"):
        courses_for_day(day, TERM, [make_rule()], exceptions)


def test_rule_for_another_term_is_rejected():
    with pytest.raises(ValidationError, match="same term"):
        courses_for_day(date(2026, 9, 14), TERM, [make_rule(term_id="spring")], [])


def test_occurrences_have_stable_order_for_overlapping_rules():
    day = date(2026, 9, 14)
    rules = [
        make_rule("zeta", course_name="Biology", start_time=time(9, 0)),
        make_rule("math-late", course_name="Algebra", start_time=time(10, 0), end_time=time(11, 0)),
        make_rule("alpha", course_name="algebra", start_time=time(9, 0)),
    ]
    occurrences = courses_for_day(day, TERM, rules, [])
    assert [item.rule_id for item in occurrences] == ["alpha", "zeta", "math-late"]


@pytest.mark.parametrize(
    "changes",
    [
        {"id": " "},
        {"course_name": " "},
        {"weekday": 7},
        {"start_week": 0},
        {"start_week": 4, "end_week": 3},
        {"end_week": 54},
        {"week_parity": "biweekly"},
        {"start_time": time(10, 0), "end_time": time(9, 0)},
        {"start_time": time(9, 0, tzinfo=timezone.utc)},
        {"start_time": time(9, 0, 0, 1)},
    ],
)
def test_course_rule_rejects_invalid_values(changes):
    with pytest.raises(ValidationError):
        make_rule(**changes)
