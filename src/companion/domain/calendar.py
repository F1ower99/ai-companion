from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Literal, Sequence

from companion.domain.errors import ValidationError


WeekParity = Literal["all", "odd", "even"]
ExceptionKind = Literal["holiday", "rest", "makeup"]


def _require_id(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field_name} must not be blank.")


def _require_day(value: date, field_name: str) -> None:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ValidationError(f"{field_name} must be a calendar date.")


def _require_wall_time(value: time, field_name: str) -> None:
    if not isinstance(value, time) or value.tzinfo is not None or value.microsecond != 0:
        raise ValidationError(
            f"{field_name} must be a whole-second local wall-clock time without a timezone."
        )


@dataclass(frozen=True)
class AcademicTerm:
    id: str
    name: str
    start_date: date
    end_date: date
    week_one_start: date

    def __post_init__(self) -> None:
        _require_id(self.id, "id")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValidationError("Term name must not be blank.")
        object.__setattr__(self, "name", self.name.strip())
        _require_day(self.start_date, "start_date")
        _require_day(self.end_date, "end_date")
        _require_day(self.week_one_start, "week_one_start")
        if self.end_date < self.start_date:
            raise ValidationError("Term end_date cannot be earlier than start_date.")
        if self.week_one_start > self.start_date:
            raise ValidationError("week_one_start must be on or before term start_date.")
        if self.total_weeks > 53:
            raise ValidationError("An academic term cannot span more than 53 teaching weeks.")

    @property
    def total_weeks(self) -> int:
        return (self.end_date - self.week_one_start).days // 7 + 1


@dataclass(frozen=True)
class CourseRule:
    id: str
    term_id: str
    weekday: int
    start_week: int
    end_week: int
    week_parity: WeekParity
    start_time: time
    end_time: time
    course_name: str

    def __post_init__(self) -> None:
        _require_id(self.id, "id")
        _require_id(self.term_id, "term_id")
        if type(self.weekday) is not int or not 0 <= self.weekday <= 6:
            raise ValidationError("weekday must be an integer from 0 to 6.")
        if type(self.start_week) is not int or not 1 <= self.start_week <= 53:
            raise ValidationError("start_week must be an integer from 1 to 53.")
        if type(self.end_week) is not int or not 1 <= self.end_week <= 53:
            raise ValidationError("end_week must be an integer from 1 to 53.")
        if self.end_week < self.start_week:
            raise ValidationError("end_week cannot be earlier than start_week.")
        if self.week_parity not in ("all", "odd", "even"):
            raise ValidationError("week_parity must be all, odd, or even.")
        _require_wall_time(self.start_time, "start_time")
        _require_wall_time(self.end_time, "end_time")
        if self.end_time <= self.start_time:
            raise ValidationError("end_time must be later than start_time; overnight courses are unsupported.")
        if not isinstance(self.course_name, str) or not self.course_name.strip():
            raise ValidationError("Course name must not be blank.")
        object.__setattr__(self, "course_name", self.course_name.strip())


@dataclass(frozen=True)
class CalendarException:
    term_id: str
    day: date
    kind: ExceptionKind
    replacement_weekday: int | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        _require_id(self.term_id, "term_id")
        _require_day(self.day, "day")
        if self.kind not in ("holiday", "rest", "makeup"):
            raise ValidationError("Exception kind must be holiday, rest, or makeup.")
        if self.kind == "makeup":
            if type(self.replacement_weekday) is not int or not 0 <= self.replacement_weekday <= 6:
                raise ValidationError("A makeup exception requires a replacement weekday from 0 to 6.")
        elif self.replacement_weekday is not None:
            raise ValidationError("Only a makeup exception may have a replacement weekday.")
        if self.note is not None and not isinstance(self.note, str):
            raise ValidationError("Exception note must be text or None.")
        if self.note is not None:
            normalized_note = self.note.strip()
            object.__setattr__(self, "note", normalized_note or None)


@dataclass(frozen=True)
class CourseOccurrence:
    term_id: str
    rule_id: str
    day: date
    week_number: int
    weekday: int
    start_time: time
    end_time: time
    course_name: str

    def __post_init__(self) -> None:
        _require_id(self.term_id, "term_id")
        _require_id(self.rule_id, "rule_id")
        _require_day(self.day, "day")
        if type(self.week_number) is not int or not 1 <= self.week_number <= 53:
            raise ValidationError("week_number must be an integer from 1 to 53.")
        if type(self.weekday) is not int or not 0 <= self.weekday <= 6:
            raise ValidationError("weekday must be an integer from 0 to 6.")
        _require_wall_time(self.start_time, "start_time")
        _require_wall_time(self.end_time, "end_time")
        if self.end_time <= self.start_time:
            raise ValidationError("end_time must be later than start_time.")
        if not isinstance(self.course_name, str) or not self.course_name.strip():
            raise ValidationError("Course name must not be blank.")
        object.__setattr__(self, "course_name", self.course_name.strip())


def courses_for_day(
    day: date,
    term: AcademicTerm,
    rules: Sequence[CourseRule],
    exceptions: Sequence[CalendarException],
) -> list[CourseOccurrence]:
    """Resolve the recurring schedule and date override for one local date."""
    _require_day(day, "day")
    if not isinstance(term, AcademicTerm):
        raise ValidationError("An academic term is required.")
    if not isinstance(rules, Sequence) or isinstance(rules, (str, bytes)):
        raise ValidationError("Course rules must be a sequence.")
    if not isinstance(exceptions, Sequence) or isinstance(exceptions, (str, bytes)):
        raise ValidationError("Calendar exceptions must be a sequence.")

    exceptions_by_day: dict[date, CalendarException] = {}
    for exception in exceptions:
        if not isinstance(exception, CalendarException):
            raise ValidationError("Calendar exceptions must use CalendarException values.")
        if exception.term_id != term.id:
            raise ValidationError("Calendar exceptions must reference the same term.")
        if exception.day in exceptions_by_day:
            raise ValidationError("Only one exception may be supplied for a term and day.")
        exceptions_by_day[exception.day] = exception

    for rule in rules:
        if not isinstance(rule, CourseRule):
            raise ValidationError("Course rules must use CourseRule values.")
        if rule.term_id != term.id:
            raise ValidationError("Course rules must reference the same term.")

    if not term.start_date <= day <= term.end_date:
        return []

    exception = exceptions_by_day.get(day)
    if exception is not None and exception.kind in ("holiday", "rest"):
        return []

    week_number = (day - term.week_one_start).days // 7 + 1
    weekday = (
        exception.replacement_weekday
        if exception is not None and exception.kind == "makeup"
        else day.weekday()
    )
    occurrences = []
    for rule in rules:
        if rule.weekday != weekday or not rule.start_week <= week_number <= rule.end_week:
            continue
        if rule.week_parity == "odd" and week_number % 2 == 0:
            continue
        if rule.week_parity == "even" and week_number % 2 != 0:
            continue
        occurrences.append(CourseOccurrence(
            term_id=term.id,
            rule_id=rule.id,
            day=day,
            week_number=week_number,
            weekday=weekday,
            start_time=rule.start_time,
            end_time=rule.end_time,
            course_name=rule.course_name,
        ))
    return sorted(
        occurrences,
        key=lambda occurrence: (
            occurrence.start_time,
            occurrence.end_time,
            occurrence.course_name.casefold(),
            occurrence.rule_id,
        ),
    )
