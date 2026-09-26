# Stage 3 Proactive Decision Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Deliver a deterministic, local Stage 3 decision and reminder lifecycle that chooses when to speak and when to stay quiet, with a reviewable card in the existing desktop shell.

**Architecture:** Keep all scoring, filtering, timing thresholds, and action semantics in pure domain code. Application services assemble inputs through injected Clock/activity/repository ports and persist actions before UI effects. Qt only schedules evaluation and renders results; SQLite only serializes records and transactions.

**Tech Stack:** Python 3.10+, stdlib `datetime`/SQLite, host OS local-time rules through an injected adapter, PySide6 Essentials already pinned in `pyproject.toml`, pytest, pytest-qt. This Windows environment has no IANA tzdata database, so the implementation must not depend on `zoneinfo` data being installed. No new runtime dependency, LLM, or Windows activity monitor.

**Spec:** `docs/superpowers/specs/2026-09-24-stage-3-proactive-decision-design.md`

## Global Constraints

- `companion.domain` must not import Qt, SQLite, Windows APIs, network clients, or call the system clock.
- Decision time and local-time context must be explicit inputs from an injected Clock; tests must use a fake clock.
- Reminder decisions remain deterministic and local; there is no LLM or network call in this stage.
- SQLite changes use an additive schema version 2 migration; v1 migration SQL and its `reminders` placeholder remain unchanged.
- No activity app name, window title, keystroke, screen content, or chat text is collected or stored.
- Hard start/end are immutable constraints; snooze and extension state are separate reminder state.
- The UI displays a structured decision and forwards user actions; it does not implement decision rules.
- At most one reminder card may be surfaced per evaluation; reminders are silent during disabled/quiet periods.
- A complete Stage is committed once after full regression verification and diff/security review; do not merge or force-push.

## Review Focus

1. Invalid or boundary task data (completed quantity, zero planned time, hard start after now, expired hard end) must not produce negative estimates, crash, or describe a missed hard deadline as achievable; Task 1 and Task 3 tests cover it.
2. Local midnight, UTC conversion, quiet-hour boundaries, and ambiguous/nonexistent DST wall times must be explicit and deterministic; Task 2 and Task 5 tests cover injected time conversion.
3. Duplicate button clicks, process restart, repeated scheduler ticks, and a crash between task completion and event recording must not accept two extensions or surface duplicate cards; Task 4 tests cover idempotency and restart behavior.
4. Stale/failing activity sources must degrade to `unknown`; unknown/idle/quiet/disabled states must not show an ordinary reminder; Task 1 and Task 4 tests cover each gate.
5. Candidate queries must include overdue tasks and tasks planned today even when their due date is later, while excluding completed/inactive-goal work without dropping another eligible P0/P1 candidate; Task 3 and Task 4 tests cover the query/selection boundary.

---

### Task 1: Pure Reminder Domain and Decision Rules

**Files:**
- Modify: `src/companion/domain/models.py`
- Create: `src/companion/domain/reminders.py`
- Create: `src/companion/domain/decisions.py`
- Test: `tests/domain/test_models.py`
- Create: `tests/domain/test_decisions.py`

**Interfaces:**
- Consumes: existing immutable `Task`, `Goal`, `Priority`, `TaskStatus` domain models.
- Produces: `ActivityState`, `ActivitySnapshot`, `ReminderPreferences`, `TaskReminderState`, `DecisionContext`, `Decision`, `DecisionKind`, `ReasonCode`, `remaining_minutes(task)`, and `decide(context)`.
- `DecisionContext` carries an aware UTC `now`, an aware `local_now`, tasks, goal snapshots, activity, task/global reminder state, preferences, and already-resolved local quiet-window boundaries. The core does not resolve system time zones.
- `decide(context)` returns `SHOW_REMINDER`, `WAIT`, or `SILENT`; `SHOW_REMINDER` contains no more than one task id.

- [x] **Step 1: Write failing model tests for soft start and reminder value validation.**

```python
def test_task_normalizes_planned_start_to_utc():
    local = datetime(2026, 9, 26, 19, 30, tzinfo=timezone(timedelta(hours=8)))
    assert make_task(planned_start_at=local).planned_start_at == datetime(
        2026, 9, 26, 11, 30, tzinfo=timezone.utc
    )

def test_task_rejects_naive_planned_start():
    with pytest.raises(ValidationError):
        make_task(planned_start_at=datetime(2026, 9, 26, 19, 30))
```

- [x] **Step 2: Run only the model tests and verify the planned-start cases fail because the Task field is missing.**

Run: `..\..\..\..\.venv\Scripts\python.exe -m pytest tests/domain/test_models.py -k planned_start -q`

Expected: the two tests fail at Task construction for the missing keyword field; pytest collects both tests successfully.

- [x] **Step 3: Add `Task.planned_start_at`, immutable reminder input/output dataclasses, enums, validation, and the pure decision function.**

Use aware UTC instants for comparisons. For target tasks compute `ceil(planned_minutes * remaining_units / target_units)`. Candidate eligibility checks open status, remaining units, active goal, local-day plan/due date, soft-start grace, hard-start, skip/snooze, and feasibility. Rank by future hard-deadline slack first, then P0/P1/P2, overdue hard-end within priority, soft planned start, goal priority, creation time, and id. Apply quiet/disabled/activity/cooldown gates and select only among candidates that can surface. Return the next meaningful evaluation time for waits.

- [x] **Step 4: Add decision-table tests and run them until green.**

Required examples: planned-start 4m59s grace vs 5m; P2 remains quiet while focused; P1 can surface after 120m when late 30m; critical P0 can show a non-modal decision before 120m; idle/unknown/quiet/disabled gate ordinary reminders; done/inactive tasks are ignored; deadline risk is stable and precedes priority only when future; completed-unit estimates use literal hand-calculated values; a blocked P2 does not hide an eligible P1; ties end at task id; a second evaluation at identical context returns the identical Decision.

Run: `..\..\..\..\.venv\Scripts\python.exe -m pytest tests/domain/test_models.py tests/domain/test_decisions.py -q`

Expected: all focused domain tests pass with no Qt or database imports in the decision module.

- [x] **Step 5: Run existing domain tests and inspect the domain dependency boundary.**

Run: `..\..\..\..\.venv\Scripts\python.exe -m pytest tests/domain -q`

Expected: all existing model/TaskService tests and new decision tests pass. Confirm `rg -n "PySide6|sqlite3|datetime\.now|date\.today" src/companion/domain/decisions.py src/companion/domain/reminders.py` returns no matches.

### Task 2: Injected Clock, Local-Time Conversion, and TaskService

**Files:**
- Create: `src/companion/ports/clock.py`
- Create: `src/companion/ports/activity.py`
- Create: `src/companion/infrastructure/system_clock.py`
- Modify: `src/companion/application/task_service.py`
- Modify: `src/companion/desktop/app.py`
- Modify: `tests/domain/test_task_service.py`
- Create: `tests/infrastructure/test_system_clock.py`

**Interfaces:**
- `Clock.now_utc() -> datetime` returns one aware UTC instant for task creation.
- `Clock.snapshot(preferences: ReminderPreferences) -> ClockSnapshot` returns one atomic time snapshot. Its fields are `now_utc`, `local_now`, `local_date`, `local_day_start_utc`, `next_local_day_start_utc`, `quiet_hours_active`, `tonight_quiet_start_utc`, and `quiet_period_end_utc`.
- `Clock.resolve_local(day: date, local_time: time) -> datetime` returns an aware UTC instant or raises `ValidationError` for ambiguous/nonexistent input.
- `SystemClock` is the infrastructure implementation; it may call the OS clock and Windows local-time rules. Decision code receives only its explicit snapshot.
- `ActivitySource.snapshot(at: datetime) -> ActivitySnapshot` is a port only; production default for Stage 3 returns `unknown` at the supplied instant and makes no Windows calls.
- `TaskService` receives a Clock and uses it for new Goal/Task creation timestamps.

- [x] **Step 1: Write a failing TaskService test proving the injected clock controls created_at.**

```python
class FixedClock:
    def now_utc(self):
        return datetime(2026, 9, 26, 12, tzinfo=timezone.utc)

    def snapshot(self, preferences=None):
        return ClockSnapshot(
            now_utc=datetime(2026, 9, 26, 12, tzinfo=timezone.utc),
            local_now=datetime(2026, 9, 26, 20, tzinfo=timezone(timedelta(hours=8))),
            local_date=date(2026, 9, 26),
            local_day_start_utc=datetime(2026, 9, 25, 16, tzinfo=timezone.utc),
            next_local_day_start_utc=datetime(2026, 9, 26, 16, tzinfo=timezone.utc),
            quiet_hours_active=False,
            tonight_quiet_start_utc=datetime(2026, 9, 26, 14, tzinfo=timezone.utc),
            quiet_period_end_utc=datetime(2026, 9, 26, 0, tzinfo=timezone.utc),
        )

def test_add_task_uses_injected_clock(service_with_clock):
    task = service_with_clock.add_task(
        title="Vocabulary", goal_id="goal-1", due_date=date(2026, 9, 26),
        planned_minutes=30, priority=Priority.P1,
    )
    assert task.created_at == datetime(2026, 9, 26, 12, tzinfo=timezone.utc)
```

- [x] **Step 2: Run only that test and verify it fails because TaskService currently calls `utc_now()` directly.**

Run: `..\..\..\..\.venv\Scripts\python.exe -m pytest tests/domain/test_task_service.py::test_add_task_uses_injected_clock -q`

Expected: a focused assertion failure, not a fixture/import error.

- [x] **Step 3: Implement Clock/ClockSnapshot, SystemClock local-time resolution, the ActivitySource Protocol, and TaskService injection.**

Use the standard library and existing Qt/Windows platform support; do not add a timezone package. Verify local wall-time conversion by enumerating candidate UTC offsets and round-tripping through the injected host-zone resolver; reject wall times that do not map uniquely. `SystemClock` is constructed once in desktop composition and passed into TaskService and the reminder service. A fake resolver covers normal, ambiguous, and nonexistent times on every platform.

- [x] **Step 4: Add tests for host-local midnight bounds, UTC/local representation, valid conversion, and explicit rejection of ambiguous/nonexistent wall times using an injected transition resolver.**

Run: `..\..\..\..\.venv\Scripts\python.exe -m pytest tests/infrastructure/test_system_clock.py tests/domain/test_task_service.py -q`

Expected: all clock/service tests pass and fixed-clock tests never read the live clock.

- [x] **Step 5: Run domain and infrastructure tests.**

Run: `..\..\..\..\.venv\Scripts\python.exe -m pytest tests/domain tests/infrastructure -q`

Expected: old behavior stays green; app composition has a single explicit `SystemClock` construction.

### Task 3: Additive SQLite v2 and Reminder Repositories

**Files:**
- Modify: `src/companion/infrastructure/sqlite/migrations.py`
- Modify: `src/companion/ports/repositories.py`
- Create: `src/companion/ports/reminders.py`
- Modify: `src/companion/infrastructure/sqlite/repositories.py`
- Modify: `tests/infrastructure/test_sqlite_migrations.py`
- Modify: `tests/infrastructure/test_sqlite_repositories.py`
- Create: `tests/infrastructure/test_sqlite_reminders.py`

**Interfaces:**
- Extend `TaskRepository` with `list_for_decisions(day, day_start_utc, next_day_start_utc)` and preserve existing `list_for_day` behavior.
- `ReminderRepository` reads task state and global last-shown time, stores user actions, records one displayed event, and atomically updates reminder state plus append-only event by idempotency key.
- `ReminderPreferencesRepository` reads/writes validated ReminderPreferences via namespaced keys in v1 `settings`.
- No repository method decides reminder eligibility, task rank, or quiet hours.

- [x] **Step 1: Write failing migration tests for v1→v2, planned-start NULL backfill, three reminder tables, and v1 placeholder preservation.**

```python
def test_version_two_adds_reminder_schema_without_changing_v1(connection):
    apply_migrations(connection)
    assert read_schema_version(connection) == 2
    task_columns = {row[1] for row in connection.execute("PRAGMA table_info(tasks)")}
    tables = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert "planned_start_at" in task_columns
    assert {"task_reminder_state", "reminder_runtime_state", "reminder_events"} <= tables
    assert "reminders" in tables
```

- [x] **Step 2: Run the migration tests and verify they fail on schema version 1 / missing v2 tables.**

Run: `..\..\..\..\.venv\Scripts\python.exe -m pytest tests/infrastructure/test_sqlite_migrations.py -q`

Expected: assertions identify only missing v2 schema changes; v1 rollback tests still collect.

- [x] **Step 3: Implement v2 as a new migration entry and parameterized repository operations.**

Persist aware timestamps as ISO UTC, task/day state with a composite unique key, one global runtime row, append-only events with unique idempotency keys, and a task-delete `SET NULL` event reference. Keep transactions on the existing SQLiteDatabase connection context; do not change version 1 SQL.

- [x] **Step 4: Write failing repository tests for planned-start round trip, due-or-planned candidate listing, action/event atomicity, duplicate idempotency key, preference validation, and reopen persistence.**

Run: `..\..\..\..\.venv\Scripts\python.exe -m pytest tests/infrastructure/test_sqlite_reminders.py tests/infrastructure/test_sqlite_repositories.py -q`

Expected before implementation: import/missing-method failures for the new repository contracts, then green once implemented. Also inject a failing event write and assert task/global state is rolled back.

- [x] **Step 5: Run all infrastructure tests and migration failure rollback tests.**

Run: `..\..\..\..\.venv\Scripts\python.exe -m pytest tests/infrastructure -q`

Expected: v1 data and schema survive a failed v2 migration; a second initialize remains idempotent; foreign keys stay enabled.

### Task 4: Proactive Reminder Application Service and Lifecycle

**Files:**
- Create: `src/companion/application/proactive_reminder_service.py`
- Modify: `src/companion/application/task_service.py`
- Modify: `src/companion/ports/activity.py`
- Modify: `src/companion/ports/reminders.py`
- Create: `tests/application/test_proactive_reminder_service.py`

**Interfaces:**
- `ProactiveReminderService.evaluate() -> Decision` assembles one ClockSnapshot, task/goal snapshots, activity, preferences, and reminder state; persists a `SHOW_REMINDER` before returning it to UI.
- `ProactiveReminderService.respond(task_id, action, minutes=None) -> Decision` validates and persists now/later/extension/skip/done. Completion delegates to TaskService and is logged only after the TaskService call succeeds.
- A deterministic fallback `UnknownActivitySource` returns `unknown`; stale/failing source snapshots are normalized to unknown.
- User-action idempotency keys are required input or derived from an action id supplied by UI; one accepted extension per task/local date is enforced transactionally.

- [x] **Step 1: Write a failing service test proving display state is persisted before a show decision is returned.**

```python
def test_evaluate_persists_before_returning_show(fake_service):
    decision = fake_service.evaluate()
    assert decision.kind is DecisionKind.SHOW_REMINDER
    assert fake_service.reminders.events[-1].kind == "displayed"
    assert fake_service.reminders.last_shown_at == decision.generated_at
```

- [x] **Step 2: Run the focused service test and verify it fails because the application service does not exist.**

Run: `..\..\..\..\.venv\Scripts\python.exe -m pytest tests/application/test_proactive_reminder_service.py -q`

Expected: one expected missing-import/behavior failure after test collection is corrected.

- [x] **Step 3: Implement the service orchestration and typed ports.**

The service must use one captured ClockSnapshot per operation; must re-fetch current task, goal, activity, preferences, and state on every evaluation; must not cache a past Decision through extension time; and must persist action/state/event atomically before returning. A duplicate action id returns the prior outcome without incrementing extension count or generating another card.

- [x] **Step 4: Add literal fake-clock/repository tests for actions, errors, cooldowns, restart, and deadline re-evaluation.**

Required cases: now rechecks after 30m; later rechecks after 15m; extension at 30m reloads task/progress/activity and may return WAIT or SILENT; a second extension same local day is rejected; extension crossing hard_end/quiet-start is rejected; skip expires at local date rollover; completed operation failure writes no done event; completion triggers immediate next candidate; DB error returns safe storage failure and never returns a show event; repeated action IDs are idempotent.

- [x] **Step 5: Run all domain/application/infrastructure tests.**

Run: `..\..\..\..\.venv\Scripts\python.exe -m pytest tests/domain tests/infrastructure tests/application -q`

Expected: all pre-existing tests plus the new reminder lifecycle suite pass.

### Task 5: Minimal UI and Scheduler Wiring

**Files:**
- Create: `src/companion/desktop/reminder_card.py`
- Create: `src/companion/desktop/reminder_settings_dialog.py`
- Create: `src/companion/desktop/reminder_scheduler.py`
- Modify: `src/companion/desktop/tasks_dialog.py`
- Modify: `src/companion/desktop/app.py`
- Modify: `src/companion/desktop/chat_window.py`
- Create: `tests/desktop/test_reminder_card.py`
- Create: `tests/desktop/test_reminder_settings_dialog.py`
- Modify: `tests/desktop/test_tasks_dialog.py`
- Modify: `tests/desktop/test_app_lifecycle.py`

**Interfaces:**
- Task creation includes an optional local planned date/time, converts it through Clock/LocalTimeResolver before calling TaskService, and leaves it unset when blank.
- `ReminderScheduler` owns a Qt timer at 60-second maximum interval, evaluates on startup/tick and after activity/task/action events, and emits only structured Decision values.
- `ReminderCard` renders one structured SHOW_REMINDER and forwards action + minutes + unique action id to the application service; it contains no thresholds, rank, or SQLite calls.
- `ReminderSettingsDialog` edits only enabled/quiet-hours preferences through the application service and is opened from the existing chat panel; it adds no dashboard or activity controls.

- [x] **Step 1: Write failing Qt tests for optional planned time and the five action buttons.**

```python
def test_blank_planned_time_is_passed_as_none(qtbot, task_service):
    dialog = TodayTasksDialog(task_service, today=date(2026, 9, 26))
    qtbot.addWidget(dialog)
    dialog.title_input.setText("Vocabulary")
    QTest.mouseClick(dialog.add_task_button, Qt.MouseButton.LeftButton)
    assert task_service.calls[-1][1]["planned_start_at"] is None
```

- [x] **Step 2: Run the new UI tests and verify they fail because no planned-time control/card exists.**

Run: `$env:QT_QPA_PLATFORM='offscreen'; ..\..\..\..\.venv\Scripts\python.exe -m pytest tests/desktop/test_tasks_dialog.py tests/desktop/test_reminder_card.py -q`

Expected: targeted missing-widget/action behavior failures, not Qt startup errors.

- [x] **Step 3: Add optional local QDateEdit/QTimeEdit fields, a small non-modal reminder card, and the QTimer scheduler wiring.**

Keep the chosen wall date/time separate until the injected resolver receives it, so Qt cannot silently normalize a DST gap or repeated wall time. Reject invalid/ambiguous wall time with a safe form hint. The card displays the selected task, priority, goal, planned time, delay and reason. Closing the card submits only the close action. Action widgets submit through the service; visual text is a local reason-code mapping. Keep the existing pet/chat dimensions and Today Tasks layout compact.

- [x] **Step 4: Add Qt tests that verify every action is forwarded exactly once, a WAIT/SILENT decision renders no card, display-only text uses reason codes, and no button steals focus or creates a second card.**

Run: `$env:QT_QPA_PLATFORM='offscreen'; ..\..\..\..\.venv\Scripts\python.exe -m pytest tests/desktop/test_tasks_dialog.py tests/desktop/test_reminder_card.py tests/desktop/test_app_lifecycle.py -q`

Expected: all focused UI/lifecycle tests pass, including database failure leaving the pet shell alive.

- [x] **Step 5: Test reminder settings and validated enabled/quiet-hour preferences; the dialog must not expose activity-monitor or LLM controls in this stage.**

Run: `$env:QT_QPA_PLATFORM='offscreen'; ..\\..\\..\\..\\.venv\\Scripts\\python.exe -m pytest tests/desktop/test_reminder_settings_dialog.py -q`

Expected: changed preferences are persisted through the application service and take effect on the next scheduler evaluation.

- [x] **Step 6: Run the full Qt desktop test directory.**

Run: `$env:QT_QPA_PLATFORM='offscreen'; ..\..\..\..\.venv\Scripts\python.exe -m pytest tests/desktop -q`

Expected: old pet interactions and Today Tasks behavior remain green alongside the reminder UI.

### Task 6: Roadmap, Integration Acceptance, and Stage Commit

**Files:**
- Modify: `outputs/mvp-plan.md`
- Modify: `README.md`
- Create: `tests/application/test_stage3_acceptance.py`
- Create: `.superpowers/sdd/2026-09-26-stage-3-proactive-decision/progress.md`
- Create: `.superpowers/sdd/2026-09-26-stage-3-proactive-decision/final-review-package.md`

**Interfaces:**
- Consumes the completed domain, storage, service, and UI interfaces from Tasks 1–5.
- Produces one documented Stage 3 completion status and one Stage 3 implementation commit. The existing Stage 4 calendar, Stage 5 LLM, and Stage 7 voice work remain future roadmap items; the old Stage 6 decision loop is marked superseded by Stage 3.

- [x] **Step 1: Write failing acceptance tests for the 19:30/20:10/130-minute focus scenario and the post-extension full re-evaluation.**

```python
NOW_1930 = datetime(2026, 9, 26, 11, 30, tzinfo=timezone.utc)
LOCAL_1930 = datetime(2026, 9, 26, 19, 30, tzinfo=timezone(timedelta(hours=8)))

def test_1930_due_task_does_not_interrupt_at_due_time():
    vocab = Task(
        id="vocab", title="Vocabulary", goal_id="study", due_date=date(2026, 9, 26),
        planned_minutes=20, priority=Priority.P1,
        planned_start_at=NOW_1930,
        created_at=datetime(2026, 9, 26, 8, tzinfo=timezone.utc),
    )
    context = make_context(
        now_utc=NOW_1930, local_now=LOCAL_1930,
        activity=ActivitySnapshot(ActivityState.FOCUSED, NOW_1930, NOW_1930),
        tasks=(vocab,), goals=(Goal("study", "Study"),),
    )
    assert decide(context).kind is DecisionKind.WAIT

def test_2010_after_130m_focus_selects_late_p1_when_p0_is_not_yet_eligible():
    vocab = Task(
        id="vocab", title="Vocabulary", goal_id="study", due_date=date(2026, 9, 26),
        planned_minutes=20, priority=Priority.P1,
        planned_start_at=datetime(2026, 9, 26, 11, 30, tzinfo=timezone.utc),
        created_at=datetime(2026, 9, 26, 8, tzinfo=timezone.utc),
    )
    course = Task(
        id="course", title="Professional course", goal_id="study", due_date=date(2026, 9, 26),
        planned_minutes=60, priority=Priority.P0,
        planned_start_at=datetime(2026, 9, 26, 13, 0, tzinfo=timezone.utc),
        created_at=datetime(2026, 9, 26, 8, tzinfo=timezone.utc),
    )
    now = datetime(2026, 9, 26, 12, 10, tzinfo=timezone.utc)
    context = make_context(
        now_utc=now,
        local_now=datetime(2026, 9, 26, 20, 10, tzinfo=timezone(timedelta(hours=8))),
        activity=ActivitySnapshot(
            ActivityState.FOCUSED, now, datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)
        ),
        tasks=(vocab, course), goals=(Goal("study", "Study"),),
    )
    decision = decide(context)
    assert decision.kind is DecisionKind.SHOW_REMINDER
    assert decision.task_id == "vocab"
    assert ReasonCode.PLANNED_START_LATE in decision.reason_codes

def make_context(*, now_utc, local_now, activity, tasks, goals):
    return DecisionContext(
        now_utc=now_utc,
        local_now=local_now,
        local_date=local_now.date(),
        local_day_start_utc=datetime(2026, 9, 25, 16, tzinfo=timezone.utc),
        next_local_day_start_utc=datetime(2026, 9, 26, 16, tzinfo=timezone.utc),
        tonight_quiet_start_utc=datetime(2026, 9, 26, 14, tzinfo=timezone.utc),
        quiet_period_end_utc=datetime(2026, 9, 27, 0, tzinfo=timezone.utc),
        tasks=tasks,
        goals=goals,
        activity=activity,
        reminder_states={},
        last_global_shown_at=None,
        preferences=ReminderPreferences(),
    )
```

- [x] **Step 2: Run acceptance tests and verify they fail only on missing Stage 3 behaviors.**

Run: `..\..\..\..\.venv\Scripts\python.exe -m pytest tests/application/test_stage3_acceptance.py -q`

Expected: the behavior assertion fails until the new deterministic engine implements this scenario; fixtures use complete immutable models and fixed time/activity snapshots.

- [x] **Step 3: Add acceptance cases and update docs with only implemented behavior.**

The acceptance suite covers schedule lateness vs activity, remaining time/priority, and extension re-evaluation. Update README to state that local deterministic reminders exist but Windows activity monitoring and LLM integration remain deferred. Update roadmap so Stage 3 is complete, old Windows monitor tasks are deferred, old Stage 6 decision tasks are superseded, and Stage 4 calendar remains the next planned stage.

- [x] **Step 4: Run all verification commands, inspect the full diff, and inspect the staged file list for secrets/debug/cache/database artifacts.**

Run: `$env:QT_QPA_PLATFORM='offscreen'; ..\..\..\..\.venv\Scripts\python.exe -m pytest -q`; then `..\..\..\..\.venv\Scripts\python.exe -m compileall -q src tests`; then `..\..\..\..\.venv\Scripts\python.exe -m pip check`; then `git diff --check` and `git status --short`.

Expected: full suite passes, compileall exits 0, pip reports no broken requirements, whitespace checks are clean, and only Stage 3 source/test/docs files are present.

- [x] **Step 5: Commit the complete Stage 3 change once.**

Stage all the Stage 3 spec correction, plan, code, tests, and roadmap/README changes; exclude `.superpowers/sdd` because it is git-ignored. Commit with `feat: add deterministic proactive reminders`. Do not push until after final review verifies the branch contains no secrets or unrelated changes.

## Plan Self-Review

- Spec coverage maps to Tasks 1–5: domain/time/candidate rules (1–2), additive persistence (3), reminder lifecycle/actions/failure/idempotency (4), UI/scheduler (5), acceptance and roadmap (6).
- The spec's fake clock/repository/activity-source strategy appears in Tasks 1–4; the Qt boundary appears in Task 5.
- The five Review Focus conditions are assigned to concrete tests in Tasks 1–5.
- The plan resolves the timezone implementation against this Windows host: no IANA database is available, so local conversion is isolated behind a resolver and never imported by the decision engine.
- No Stage 3 task adds Windows monitoring, LLM, voice, cloud, or a new dependency.
- Stage 3 gets one complete-stage implementation commit after the full suite and diff review, following the user's Git instruction.
