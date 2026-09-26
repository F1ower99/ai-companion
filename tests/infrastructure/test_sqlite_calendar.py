from datetime import date, time

import pytest

from companion.domain.calendar import AcademicTerm, CalendarException, CourseRule
from companion.domain.errors import NotFoundError, ValidationError
from companion.infrastructure.sqlite.database import SQLiteDatabase
from companion.infrastructure.sqlite.repositories import SQLiteCalendarRepository


@pytest.fixture
def calendar_store(tmp_path):
    database = SQLiteDatabase(tmp_path / "calendar.sqlite3")
    database.initialize()
    return database, SQLiteCalendarRepository(database)


def make_term(term_id="fall", **changes):
    values = {
        "id": term_id,
        "name": "Fall 2026",
        "start_date": date(2026, 9, 1),
        "end_date": date(2026, 12, 31),
        "week_one_start": date(2026, 8, 31),
    }
    values.update(changes)
    return AcademicTerm(**values)


def make_rule(rule_id="math-mon", term_id="fall", **changes):
    values = {
        "id": rule_id,
        "term_id": term_id,
        "weekday": 0,
        "start_week": 1,
        "end_week": 16,
        "week_parity": "all",
        "start_time": time(9, 0),
        "end_time": time(10, 0),
        "course_name": "Math",
    }
    values.update(changes)
    return CourseRule(**values)


def test_calendar_records_round_trip_after_database_reopens(calendar_store, tmp_path):
    database, repository = calendar_store
    term = make_term()
    rule = make_rule(start_time=time(9, 30), course_name="  Discrete Math  ")
    exception = CalendarException(
        term_id=term.id,
        day=date(2026, 10, 3),
        kind="makeup",
        replacement_weekday=0,
        note="  Replacement class  ",
    )
    repository.add_term(term)
    repository.add_rule(rule)
    repository.add_exception(exception)

    reopened = SQLiteCalendarRepository(SQLiteDatabase(database.path))
    assert reopened.get_term(term.id) == term
    assert reopened.get_rule(rule.id) == rule
    assert reopened.get_exception(term.id, exception.day) == exception
    assert reopened.list_terms() == [term]
    assert reopened.list_rules(term.id) == [rule]
    assert reopened.list_exceptions(term.id) == [exception]


def test_calendar_lists_have_stable_semantic_order(calendar_store):
    _, repository = calendar_store
    fall = make_term("fall", start_date=date(2026, 9, 1))
    spring = make_term(
        "spring", name="Spring 2026", start_date=date(2026, 2, 1),
        end_date=date(2026, 6, 30), week_one_start=date(2026, 1, 26),
    )
    repository.add_term(fall)
    repository.add_term(spring)
    repository.add_rule(make_rule("late", start_time=time(11), end_time=time(12)))
    repository.add_rule(make_rule("early", start_time=time(9), end_time=time(10)))
    repository.add_rule(make_rule("tuesday", weekday=1))
    repository.add_exception(CalendarException("fall", date(2026, 10, 10), "rest"))
    repository.add_exception(CalendarException("fall", date(2026, 9, 12), "holiday"))

    assert [item.id for item in repository.list_terms()] == ["spring", "fall"]
    assert [item.id for item in repository.list_rules("fall")] == ["early", "late", "tuesday"]
    assert [item.day for item in repository.list_exceptions("fall")] == [
        date(2026, 9, 12), date(2026, 10, 10),
    ]


def test_calendar_repository_translates_duplicate_and_missing_reference_writes(calendar_store):
    _, repository = calendar_store
    term = make_term()
    repository.add_term(term)
    with pytest.raises(ValidationError):
        repository.add_term(term)
    rule = make_rule()
    repository.add_rule(rule)
    with pytest.raises(ValidationError):
        repository.add_rule(rule)
    with pytest.raises(ValidationError):
        repository.add_rule(make_rule("orphan", term_id="missing"))
    exception = CalendarException("fall", date(2026, 10, 1), "holiday")
    repository.add_exception(exception)
    with pytest.raises(ValidationError):
        repository.add_exception(CalendarException("fall", exception.day, "rest"))


def test_calendar_repository_missing_deletes_raise_not_found(calendar_store):
    _, repository = calendar_store
    with pytest.raises(NotFoundError):
        repository.delete_term("missing")
    with pytest.raises(NotFoundError):
        repository.delete_rule("missing")
    with pytest.raises(NotFoundError):
        repository.delete_exception("missing", date(2026, 9, 1))


def test_deleting_term_cascades_rules_and_exceptions(calendar_store):
    _, repository = calendar_store
    term = make_term()
    rule = make_rule()
    exception = CalendarException("fall", date(2026, 10, 1), "holiday")
    repository.add_term(term)
    repository.add_rule(rule)
    repository.add_exception(exception)
    repository.delete_term(term.id)
    assert repository.get_term(term.id) is None
    assert repository.get_rule(rule.id) is None
    assert repository.list_rules(term.id) == []
    assert repository.list_exceptions(term.id) == []
