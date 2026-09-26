# Stage 4 Academic Calendar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local, deterministic academic calendar and a read-only study-day summary without introducing UI, network access, or automatic task rescheduling.

**Architecture:** Frozen calendar models and pure date/schedule functions live in `companion.domain`; `CalendarRepository` is a persistence port; SQLite migration v3 and `SQLiteCalendarRepository` store terms, recurring rules, and exceptions. `build_study_plan` combines supplied task/course snapshots with an injected as-of instant and has no repository or clock dependency.

**Tech Stack:** Python 3.10+, standard-library `datetime` and `sqlite3`, existing PySide6 Essentials app (unchanged), pytest and pytest-qt.

**Spec:** `docs/superpowers/specs/2026-09-26-stage-4-academic-calendar-design.md`

## Global Constraints

- Calendar date ranges use inclusive local calendar dates; no timezone conversion is performed for course wall times.
- `week_one_start` is supplied explicitly and is on or before `start_date`; weekdays use Python numbering Monday=0 through Sunday=6.
- `domain` has no Qt, SQLite, network, Windows API, or implicit current-time dependency.
- All schema changes are additive migration v3; v1 and v2 migration definitions remain unchanged.
- Calendar and course notes remain local; no calendar data is logged or sent to a service.
- No calendar UI, automatic task rescheduling, activity monitoring, LLM, or new runtime dependency is added.

## Review Focus

- Partial first/last term weeks and exact inclusive boundaries must not leak courses outside the term; pin both edges in calendar tests.
- Odd/even parity must use the 1-based week anchored at `week_one_start`, including makeup dates; test actual-date week numbering.
- A holiday/rest exception must suppress all recurring rules; duplicate same-day exceptions must fail deterministically.
- Migration v3 must preserve v2 rows and roll back every v3 table if a later DDL statement fails; use a populated v2 fixture and injected SQL failure.
- Study summaries must not mutate tasks or read the machine clock; pass a fixed aware UTC instant and assert deadline flags and unchanged inputs.

---

## File Responsibilities

- Create `src/companion/domain/calendar.py`: `AcademicTerm`, `CourseRule`, `CalendarException`, `CourseOccurrence`, and `courses_for_day`.
- Create `src/companion/domain/study_plan.py`: `HardDeadlineSummary`, `StudyPlanSummary`, and `build_study_plan`.
- Create `src/companion/ports/calendar.py`: `CalendarRepository` Protocol.
- Modify `src/companion/infrastructure/sqlite/migrations.py`: set latest schema to 3 and append only v3 table/index statements.
- Modify `src/companion/infrastructure/sqlite/repositories.py`: add `SQLiteCalendarRepository` with parameterized SQL and stable reads.
- Create `tests/domain/test_calendar.py`, `tests/domain/test_study_plan.py`, and `tests/infrastructure/test_sqlite_calendar.py`; extend `tests/infrastructure/test_sqlite_migrations.py`.
- Modify `outputs/architecture-decision.md`, `outputs/mvp-plan.md`, and `README.md` to describe actual Stage 4 behavior and the next roadmap stage.

### Task 1: Calendar Models and Pure Schedule Function

**Interfaces:**

```python
def courses_for_day(
    day: date,
    term: AcademicTerm,
    rules: Sequence[CourseRule],
    exceptions: Sequence[CalendarException],
) -> list[CourseOccurrence]: ...
```

- [x] Write failing tests for inclusive term edges, a partial first week, week-one Monday/Sunday anchors, odd/even/all parity, weekday numbering, holiday/rest suppression, makeup replacement weekday, actual-date parity on makeup, duplicate exceptions, mismatched term IDs, and stable ordering.
- [x] Run `..\..\..\..\.venv\Scripts\python.exe -m pytest tests/domain/test_calendar.py -q`; confirmed the import failed before implementation.
- [x] Implement frozen dataclasses with intrinsic range/name/time validation; derive `AcademicTerm.total_weeks`; implement exception precedence and stable occurrence ordering without accessing local/system time.
- [x] Rerun `tests/domain/test_calendar.py` and `tests/domain/test_models.py`; 49 passed, including whole-second wall-time validation.

### Task 2: Read-only Study Plan Summary

**Interfaces:**

```python
def build_study_plan(
    day: date,
    tasks: Sequence[Task],
    courses: Sequence[CourseOccurrence],
    as_of_utc: datetime,
) -> StudyPlanSummary: ...

@dataclass(frozen=True)
class HardDeadlineSummary:
    task_id: str
    title: str
    hard_end: datetime
    remaining_minutes: int
    overdue: bool

@dataclass(frozen=True)
class StudyPlanSummary:
    day: date
    courses: tuple[CourseOccurrence, ...]
    remaining_tasks: tuple[Task, ...]
    total_remaining_minutes: int
    hard_deadlines: tuple[HardDeadlineSummary, ...]
```

- [x] Add tests that completed tasks are filtered, remaining tasks use Stage 3 progress rounding and deterministic priority/deadline/start/title/id order, courses are preserved, deadlines before/at/after `as_of_utc` are labeled correctly, and input tasks are unchanged.
- [x] Run the study-plan tests and confirm they fail because the summary types/function are absent.
- [x] Implement frozen summary records and the pure builder. Reject naive `as_of_utc`, normalize aware timestamps to UTC, sort deadline summaries by hard end then task ID, and do not call a system clock.
- [x] Rerun domain study-plan and Stage 3 decision/lifecycle tests.

### Task 3: Calendar Port and Additive SQLite Migration v3

**Interfaces:**

```python
class CalendarRepository(Protocol):
    def add_term(self, term: AcademicTerm) -> None: ...
    def get_term(self, term_id: str) -> AcademicTerm | None: ...
    def list_terms(self) -> list[AcademicTerm]: ...
    def delete_term(self, term_id: str) -> None: ...
    def add_rule(self, rule: CourseRule) -> None: ...
    def get_rule(self, rule_id: str) -> CourseRule | None: ...
    def list_rules(self, term_id: str) -> list[CourseRule]: ...
    def delete_rule(self, rule_id: str) -> None: ...
    def add_exception(self, exception: CalendarException) -> None: ...
    def get_exception(self, term_id: str, day: date) -> CalendarException | None: ...
    def list_exceptions(self, term_id: str) -> list[CalendarException]: ...
    def delete_exception(self, term_id: str, day: date) -> None: ...
```

- [x] Extend migration tests first: assert v3 adds the three tables/constraints, a v2 task and Stage 3 reminder data survive upgrade, foreign keys cascade, unique term/date is enforced, and a deliberately invalid v3 SQL statement rolls back all v3 DDL while schema remains v2.
- [x] Run `tests/infrastructure/test_sqlite_migrations.py -q` and confirm the v3 assertions fail before adding the migration.
- [x] Add `academic_terms`, `course_rules`, and `calendar_exceptions` statements as migration version 3 only. Use ISO local date/time text, CHECKs for weekdays/weeks/parity/time ordering and exception shape, and foreign keys with `ON DELETE CASCADE`.
- [x] Rerun migration tests, including idempotent reopening and proof that v1/v2 statement tuples are unchanged.

### Task 4: SQLite Calendar Repository

**Interfaces:**

```python
class SQLiteCalendarRepository(CalendarRepository):
    # Encode dates as ISO dates and local wall times as ISO times.
    # Translate invalid/duplicate writes to ValidationError and missing deletes to NotFoundError.
    def add_term(self, term: AcademicTerm) -> None: ...
    def get_term(self, term_id: str) -> AcademicTerm | None: ...
    def list_terms(self) -> list[AcademicTerm]: ...
    def delete_term(self, term_id: str) -> None: ...
    def add_rule(self, rule: CourseRule) -> None: ...
    def get_rule(self, rule_id: str) -> CourseRule | None: ...
    def list_rules(self, term_id: str) -> list[CourseRule]: ...
    def delete_rule(self, rule_id: str) -> None: ...
    def add_exception(self, exception: CalendarException) -> None: ...
    def get_exception(self, term_id: str, day: date) -> CalendarException | None: ...
    def list_exceptions(self, term_id: str) -> list[CalendarException]: ...
    def delete_exception(self, term_id: str, day: date) -> None: ...
```

- [x] Add temporary-database tests for term/rule/exception round trips after a new repository/connection is opened, stable list order, duplicate IDs/date exceptions, missing deletes, and term-delete cascade behavior.
- [x] Run `tests/infrastructure/test_sqlite_calendar.py -q` and confirm it fails before repository implementation.
- [x] Implement row conversion helpers and parameterized add/get/list/delete methods using the existing `SQLiteDatabase.connection()` transaction/error behavior; do not compute course occurrences in the repository.
- [x] Rerun repository, migration, Stage 2 repository, and Stage 3 reminder repository tests.

### Task 5: Documentation, Full Regression, Review, and Stage Commit

- [x] Update the architecture decision's academic-term fields to include explicit inclusive `end_date`, and explain that `total_weeks` is derived from the anchor.
- [x] Mark Stage 4 complete in `outputs/mvp-plan.md` after acceptance tests pass; name Stage 5 LLM provider/text conversation as the next roadmap stage and keep Stage 6/7 deferrals accurate.
- [x] Update README to describe local calendar persistence and deterministic summaries; do not imply calendar UI/import exists.
- [x] Run the complete suite with `$env:QT_QPA_PLATFORM='offscreen'; ..\..\..\..\.venv\Scripts\python.exe -m pytest -q`; 245 passed. `compileall`, `pip check`, staged whitespace validation, and staged secret-pattern scan also pass.
- [x] Inspect the complete diff and staged file list for secret values, local databases, virtual environments, caches, temporary files, unrelated edits, or changed v1/v2 migration definitions; only the 14 intended Stage 4 source, tests, and documentation files are staged, and v1/v2 definitions are unchanged.
- [x] Complete the read-only whole-Stage review. It found that SQLite accepts `24:00:00`; a focused failing test was added, the schema now constrains hours to `00`–`23`, and the full suite passes again.
- [ ] Commit Stage 4 independently with `feat: add local academic calendar and study plan`.

## Self-review

- Spec coverage: term/rule/exception entities and schedule precedence are Task 1; summary behavior is Task 2; additive schema and persistence are Tasks 3–4; local privacy, roadmap status, and regression evidence are Task 5.
- Cross-aggregate boundaries are explicit: `courses_for_day` rejects a rule for another term; no database scheduling logic is needed.
- Date boundaries and odd/even weeks use local calendar arithmetic only; UTC is required only for `as_of_utc` deadline labels.
- The plan adds no UI dependencies and keeps calendar reads/writes separate from task decisions.
- Stage 4 is small enough for one implementation commit; Stage 5 provider work remains outside this plan.
