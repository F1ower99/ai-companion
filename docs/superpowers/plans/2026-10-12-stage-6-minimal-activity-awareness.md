# Stage 6 Minimal Local Activity Awareness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit opt-in local idle/recent-input signal to the existing deterministic reminder flow without recording application identity or input content.

**Architecture:** A versioned SQLite preference stores only the enabled bit. An application service owns enable/pause behavior and wraps a resettable activity source; the Windows adapter uses only last-input age and maps failures to `unknown`. The existing Qt settings surface exposes the opt-in control, while Stage 3 decision rules remain unchanged.

**Tech Stack:** Python 3.10+, PySide6 Essentials 6.11.2, SQLite, Win32 `GetLastInputInfo`/tick count via `ctypes`, pytest.

**Spec:** [`2026-10-12-stage-6-minimal-activity-awareness-design.md`](../specs/2026-10-12-stage-6-minimal-activity-awareness-design.md)

## Global Constraints

- Activity awareness is opt-in and disabled by default.
- The only Windows signal is last-input age for the current interactive session; no app name, title, input content, coordinates, screen, or clipboard data.
- Only the enabled boolean persists; activity state and timestamps remain in process memory and never enter chat/provider context.
- Windows/API/storage failures and unsupported platforms resolve to `unknown` and leave the app usable.
- No new runtime dependency, background service, LLM decision, or network request is added.
- A sampling gap longer than five minutes resets the in-memory state interval.

## Review Focus

- New profiles must remain disabled after database creation, migration, and restart.
- Enabling or pausing must only take effect after the preference write succeeds; failed writes preserve the prior effective state.
- Pause/resume and a scheduler gap longer than five minutes must not accumulate focused time.
- Win32 false returns, non-monotonic/future tick values, unsupported OS, and malformed reader values must return `unknown` without escaping into the UI.
- The decision layer must receive identical snapshots and preserve Stage 3 results; no activity value may be persisted or added to provider payloads.

---

### Task 1: Activity Preferences Domain and SQLite Migration

**Files:**
- Create: `src/companion/domain/activity.py`
- Modify: `src/companion/ports/activity.py`, `src/companion/ports/repositories.py`
- Modify: `src/companion/infrastructure/sqlite/migrations.py`
- Create: `src/companion/infrastructure/sqlite/activity_preferences.py`
- Test: `tests/domain/test_activity.py`, `tests/infrastructure/test_sqlite_activity_preferences.py`, `tests/infrastructure/test_sqlite_migrations.py`

**Interfaces:**
- `ActivityAwarenessPreferences(enabled: bool = False)` validates a real boolean.
- `ActivityPreferencesRepository.get() -> ActivityAwarenessPreferences` and `.save(preferences) -> None` are the persistence port.
- `ResettableActivitySource` extends `ActivitySource` with `.reset() -> None` and a read-only `.available: bool` property.
- SQLite schema v5 creates a singleton preference row with `enabled = 0`.

- [ ] **Step 1: Write failing tests** for the disabled default, invalid preference type, v4-to-v5 upgrade preservation, singleton constraints, and preference read/write across database reopen.
- [ ] **Step 2: Run the domain, repository, and migration tests** and confirm they fail for missing v5 APIs/schema.
- [ ] **Step 3: Implement the preference value, repository port/adapter, and append-only v5 migration.** Store only `enabled`; do not add activity event/timestamp columns or tables.
- [ ] **Step 4: Run the focused tests** and confirm the new schema defaults off and existing v4 records remain intact.

### Task 2: Windows Idle Activity Adapter

**Files:**
- Create: `src/companion/infrastructure/windows_activity.py`
- Test: `tests/infrastructure/test_windows_activity.py`

**Interfaces:**
- `IdleDurationReader.idle_seconds() -> float` isolates operating-system access.
- `WindowsIdleDurationReader.idle_seconds() -> float` reads only `GetLastInputInfo` plus the tick counter and raises on unsupported or failed APIs.
- `WindowsIdleActivitySource.snapshot(at: datetime) -> ActivitySnapshot`, `.reset() -> None`, and `.available: bool` implement the resettable activity port. It uses a 300-second threshold and a 300-second maximum sample gap.

- [ ] **Step 1: Write fake-reader tests** for 299/300-second boundary, state transitions, first-sample timing, five-minute sample gaps, reset, unsupported platform, failed API, malformed values, and tick wrap/impossible deltas.
- [ ] **Step 2: Run the adapter tests** and verify they fail before implementation.
- [ ] **Step 3: Implement the lazy `ctypes` Win32 reader and in-memory state mapper.** No Win32 imports or calls occur until enabled sampling reaches the adapter.
- [ ] **Step 4: Run the adapter tests**; all OS interactions use fakes and no real user-input state is queried.

### Task 3: Application Awareness Service and Pause Semantics

**Files:**
- Create: `src/companion/application/activity_awareness_service.py`
- Test: `tests/application/test_activity_awareness_service.py`

**Interfaces:**
- `ActivityAwarenessService(source: ResettableActivitySource, preferences: ActivityPreferencesRepository)` implements `ActivitySource`.
- `.get_preferences() -> ActivityAwarenessPreferences` reads the persisted setting.
- `.set_enabled(enabled: bool) -> ActivityAwarenessPreferences` persists first, then updates effective state and resets the source.
- `.snapshot(at: datetime) -> ActivitySnapshot` returns `unknown` when disabled, unsupported, unavailable, or on source failure.

- [ ] **Step 1: Write failing fake-based tests** for disabled zero-query behavior, enabled forwarding, pause/resume reset, no state change after persistence failure, unsupported enable rejection, and source failure to `unknown`.
- [ ] **Step 2: Run the service tests** and verify the assertions fail before implementation.
- [ ] **Step 3: Implement the Qt-free wrapper** with fail-closed startup behavior and no database calls from the decision engine.
- [ ] **Step 4: Run application tests** and confirm Stage 3 reminder tests remain unchanged for the same snapshots.

### Task 4: Opt-In Settings and Application Composition

**Files:**
- Modify: `src/companion/desktop/app.py`, `src/companion/desktop/chat_window.py`, `src/companion/desktop/reminder_settings_dialog.py`
- Test: `tests/desktop/test_reminder_settings_dialog.py`, `tests/desktop/test_app_lifecycle.py`, `tests/application/test_stage6_acceptance.py`
- Modify: `README.md`, `outputs/mvp-plan.md`, `outputs/architecture-decision.md`
- Create: `docs/superpowers/tasks/2026-10-12-stage-6-minimal-activity-awareness.md`

**Interfaces:**
- The application composes `SQLiteActivityPreferencesRepository`, `WindowsIdleActivitySource`, and `ActivityAwarenessService`, then passes the service to `ProactiveReminderService` and the reminder settings dialog.
- `ReminderSettingsDialog` exposes an unchecked `activityAwarenessEnabled` control with concise privacy text. It saves this toggle immediately and emits `activityAwarenessChanged(bool)` only after a successful save.

- [ ] **Step 1: Write failing Qt/composition tests** for unchecked default, privacy copy, immediate toggle persistence and reevaluation, rollback on storage error, disabled control on unsupported platforms, and disabled startup making no OS calls.
- [ ] **Step 2: Run the focused UI and composition tests** and confirm they fail before wiring.
- [ ] **Step 3: Wire the service and settings control.** A failed save restores the persisted checkbox; a successful toggle requests exactly one reminder evaluation. Update README/roadmap/architecture decision with the opt-in boundary and completion record.
- [ ] **Step 4: Run focused UI/application tests** and verify task, chat, reminder, and provider controls remain usable.

### Task 5: Whole-Stage Review and Commit

**Files:**
- Review: all Stage 6 source, tests, migrations, and docs.
- Modify: `docs/superpowers/plans/2026-10-12-stage-6-minimal-activity-awareness.md`

- [ ] **Step 1: Review the full diff** for policy scope, state-duration correctness, SQLite migration immutability, UI failure behavior, and accidental collection/persistence/network paths; fix findings.
- [ ] **Step 2: Run full verification:** `pytest -q`, `python -m compileall -q src tests`, `python -m pip check`, `git diff --check`, and focused secret/debug/activity-data scans.
- [ ] **Step 3: Re-review the staged diff and Git status.** Confirm no real OS polling occurred during tests, no temporary artifacts are staged, and the only durable activity setting is the opt-in boolean.
- [ ] **Step 4: Commit** with `feat: add opt-in local activity awareness`.
- [ ] **Step 5: Record** the actual commit hash and verification in the completion record and overnight report. Stop before manual Windows experience testing; the user should first review the new opt-in control and verify expected idle behavior on their own machine.