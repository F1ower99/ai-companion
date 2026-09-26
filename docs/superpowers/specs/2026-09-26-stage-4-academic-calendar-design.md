# Stage 4 Design Spec: Task Planning and Academic Calendar

Date: 2026-09-26
Status: Authorized for autonomous implementation in the 2026-09-26 overnight session

## Purpose

Stage 4 adds a local academic calendar foundation that can answer “what courses are scheduled on this date?” and a read-only study-day summary that combines those occurrences with the day's open tasks. It follows the existing roadmap and provides stable inputs for later reminder and conversation work without adding automatic rescheduling or a dashboard.

The calendar is deterministic and offline. Calendar dates and course wall-clock times are local schedule values; this stage does not infer a timezone, read the operating-system clock, or convert class times to UTC. Any “as of” instant used to label a hard deadline is supplied by the caller.

## Goals

- Persist academic terms, recurring course rules, and date-specific exceptions in the existing SQLite database through additive migration v3.
- Compute course occurrences as a pure domain function with explicit date, term, rule, and exception inputs.
- Make inclusive term boundaries, teaching-week numbering, odd/even parity, and exception precedence explicit and testable.
- Produce a read-only summary of open tasks, remaining planned minutes, course occurrences, and hard deadlines for a supplied local date.
- Preserve the existing dependency direction: domain has no Qt, SQLite, network, Windows, or implicit current-time dependency; repositories persist and query only; UI remains outside this stage.

## Non-goals

- Calendar import/sync, recurring event editing UI, or a calendar dashboard.
- Automatic task creation, movement, or rescheduling from courses.
- Holiday databases, international time-zone conversion, notifications, LLM reasoning, activity monitoring, or cloud storage.
- Resolving overlapping course rules by silently dropping one. Every matching rule is returned.

## Domain model

All calendar entities are frozen dataclasses. IDs are supplied by callers, as in the existing Stage 2 models.

`AcademicTerm(id, name, start_date, end_date, week_one_start)` uses inclusive `start_date` and `end_date`. `week_one_start` is the configured local date on which teaching week 1 begins and must be on or before `start_date`; it is not assumed to be Monday. `total_weeks` is derived as `floor((end_date - week_one_start).days / 7) + 1`; this first version supports up to 53 teaching weeks. A date outside the inclusive term range has no occurrences, including dates in a partial first or last teaching week.

`CourseRule(id, term_id, weekday, start_week, end_week, week_parity, start_time, end_time, course_name)` uses Python weekday numbering (Monday=0 through Sunday=6), inclusive 1-based teaching-week bounds in the range 1–53, parity `all`, `odd`, or `even`, and local wall-clock `time` values without timezone information or fractional seconds. `end_week` must not precede `start_week`; `end_time` must be later than `start_time`; classes do not cross midnight. Names and IDs must not be blank. A rule matches its weekday, inclusive week range, and parity.

`CalendarException(term_id, day, kind, replacement_weekday=None, note=None)` supports `holiday`, `rest`, and `makeup`. `makeup` requires a replacement weekday in 0–6; `holiday` and `rest` require it to be absent. There is at most one exception per term and date. A blank note is normalized to `None`.

`CourseOccurrence(term_id, rule_id, day, week_number, weekday, start_time, end_time, course_name)` is derived, not persisted. It represents one rule matched on one date. Results are ordered by start time, end time, case-insensitive course name, then rule ID.

## Calendar function and precedence

`courses_for_day(day, term, rules, exceptions) -> list[CourseOccurrence]` has no hidden inputs. It returns an empty list when `day` is outside the term. Otherwise it derives `week_number = ((day - term.week_one_start).days // 7) + 1`.

The date exception is applied before weekly rules:

1. `holiday` and `rest` return no occurrences.
2. `makeup` evaluates rules for `replacement_weekday`, while keeping the teaching week derived from the actual calendar date.
3. With no exception, evaluate rules for `day.weekday()`.

Duplicate exceptions for the same day are invalid rather than order-dependent. Rules with an inconsistent `term_id` are invalid inputs. Matching rules are all returned in the stable order above; the engine does not guess which overlapping class is correct.

## Study-day summary

`build_study_plan(day, tasks, courses, as_of_utc) -> StudyPlanSummary` is pure and read-only. `tasks` and `courses` are already selected for the requested local day by the caller. The summary filters completed tasks, sorts remaining open tasks by priority, hard deadline (missing last), planned start, case-insensitive title, and ID, and reports their total estimated remaining minutes using the same ceiling-based progress estimate as Stage 3. It includes the supplied course occurrences and a sorted `HardDeadlineSummary` for each open task with `hard_end`; each deadline reports the task ID/title, hard-end instant, remaining minutes, and whether it has passed at `as_of_utc`.

`HardDeadlineSummary` has `task_id`, `title`, `hard_end`, `remaining_minutes`, and `overdue`. `StudyPlanSummary` has `day`, immutable `courses`, immutable `remaining_tasks`, `total_remaining_minutes`, and immutable `hard_deadlines` fields.

`as_of_utc` must be timezone-aware and is normalized to UTC. The function never calls `datetime.now()` or `date.today()`. It does not change Task state, infer that attending a course completes a task, or promise that planned minutes fit between classes.

## Persistence and ports

Migration v3 adds three tables without editing v1 or v2 statements:

- `academic_terms`: term ID/name, inclusive start/end dates, and `week_one_start`.
- `course_rules`: rule ID, term foreign key, weekday/week range/parity, local start/end time, and course name.
- `calendar_exceptions`: term foreign key, date, kind, optional replacement weekday, and optional note; unique on `(term_id, day)`.

Rules and exceptions cascade when a term is deleted. Date and wall-clock values use ISO strings (`YYYY-MM-DD` and `HH:MM:SS`); they are not UTC timestamps. Database CHECK constraints cover intrinsic ranges and exception shape; cross-record decision behavior remains in domain/application code. Repository operations use parameterized SQL and existing connection transaction handling. A `CalendarRepository` Protocol exposes term, rule, and exception add/get/list/delete operations; `SQLiteCalendarRepository` implements it and performs no scheduling.

## Failure handling and privacy

Invalid entity values or ambiguous duplicate in-memory exceptions raise `ValidationError`. Missing persisted IDs raise `NotFoundError`; SQLite failures become `StorageError` using existing repository conventions. A failed migration rolls back completely and leaves the previous schema usable. Course names and notes stay local in SQLite and are not written to logs. This stage adds no network or operating-system monitoring.

## Test strategy

- Domain unit tests cover term validation and inclusive boundaries, week-one anchoring, 1-based odd/even weeks, all-week rules, weekday matching, exception precedence, makeup weekdays with actual-date parity, duplicate exceptions, stable result order, and invalid rule inputs.
- Study-plan tests cover open/completed tasks, quantity progress rounding, deterministic task order, course preservation, past/future hard deadlines, aware-time validation, and no mutation of source objects.
- Migration tests upgrade a populated v2 database to v3, preserve prior tables/data and placeholder reminders, verify v3 constraints/foreign keys/indexes, and prove a failed v3 migration rolls back.
- Repository tests reopen the database and round-trip terms, rules, exceptions, filters, deletes, and uniqueness constraints.
- Run the entire existing suite after the new focused tests, plus `compileall`, `pip check`, staged whitespace checks, and a staged secret-pattern scan.

## Acceptance criteria

1. An out-of-term date returns no courses; the first in-term date maps to the week anchored by `week_one_start`, including a partial first week.
2. Weekly rules match inclusive week bounds, parity, and Python weekday numbering, with deterministic ordering.
3. Holiday/rest dates suppress every periodic rule; a makeup date uses its replacement weekday without changing its actual teaching-week number.
4. Migration v3 upgrades v2 data without changing prior migration definitions, and terms/rules/exceptions survive closing and reopening SQLite.
5. The study summary includes only open candidate tasks, correct remaining-minute estimates, supplied courses, and explicit hard-deadline state at the injected instant.
6. Existing Stage 1–3 behavior and all tests remain intact. No Qt UI, auto-rescheduling, activity monitoring, LLM, or additional runtime dependency is introduced.

## Deferred work

Calendar UI/import, task-to-course conflict optimization, automatic study-session generation, reminders informed by upcoming classes, external calendar sync, timezone-aware travel schedules, and LLM explanation are deferred to later roadmap stages or user research.

## Design decisions

- Store an explicit inclusive `end_date` rather than relying only on `total_weeks`. This preserves partial final weeks and makes out-of-term checks reflect the actual academic calendar; `total_weeks` is derived.
- Keep class times as local wall-clock values because Stage 4 has no selected campus timezone. Conversion is deferred until a later UI/application boundary has a user-selected timezone.
- Keep the study planner as a pure summary function over supplied snapshots. A later application/UI stage can decide when and where to display it without coupling this stage to Qt.
