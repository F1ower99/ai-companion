# Stage 6 Design: Minimal Local Activity Awareness

Date: 2026-10-12
Status: Approved for autonomous implementation by the user's overnight development instruction.
Roadmap: `outputs/mvp-plan.md`
Prior contracts: Stage 3 `ActivitySource` / `ActivitySnapshot`; Stage 5 local-first privacy boundary.

## Problem and intent

The Stage 3 decision engine already accepts `idle`, `focused`, and `unknown`, but production always supplies `unknown`. Ordinary reminders therefore remain quiet whenever the engine cannot establish that the user is available. Stage 6 adds one narrow, opt-in local signal so the existing deterministic engine can distinguish recent user activity from an idle session.

This is not application or task monitoring. The signal means only that the current Windows interactive session received input recently. It cannot say what application is open, what the user is doing, or whether the input belongs to the planned task.

## Goals

- Provide a local `ActivitySource` that maps recent input to the existing activity states without exposing input content.
- Let the user enable and pause the signal explicitly; default is disabled.
- Keep all activity timestamps and state transitions in memory. Persist only the enabled preference.
- Preserve the existing deterministic decision engine and use case boundaries; no Qt, Windows API, or SQLite dependency enters the domain.
- Keep the application useful if Windows APIs are missing, fail, or the preference store is unavailable.

## Non-goals

- No foreground process or application name, window title, URL, keyboard text, mouse coordinates, screenshots, clipboard, or chat content.
- No activity timeline, historical analytics, task classification, inference about which task is being performed, or network transmission.
- No background service when the desktop app is closed, no startup monitoring before the user enables the setting, and no LLM-based activity or reminder decisions.
- No microphone, voice, streaming, calendar sync, or automatic rescheduling.

## State semantics

`ActivityState.FOCUSED` retains the Stage 3 enum value for compatibility, but its Stage 6 production meaning is precise: **the current Windows session reported input within the last five minutes**. It does not mean that a particular application or task is in the foreground. The UI describes this as “recently active.”

`ActivityState.IDLE` means the last input is at least five minutes old. `ActivityState.UNKNOWN` means awareness is paused, unsupported, unavailable, or failed. The existing decision engine remains the sole authority for deciding whether any resulting state permits a reminder.

The Windows adapter keeps only the last emitted state and its transition instant in process memory. The first sample after startup or a state change starts the interval at the sample instant; a gap longer than five minutes between samples also starts a fresh interval so sleep, suspension, or a delayed scheduler cannot be counted as continuous focus. Time while disabled is never counted as focused time. An adapter/API error resets that in-memory state and returns `unknown`.

## Architecture and interfaces

- `ActivityAwarenessPreferences(enabled: bool = False)` is a validated domain value.
- `ActivityPreferencesRepository.get() -> ActivityAwarenessPreferences` and `.save(preferences) -> None` form a persistence port.
- A version-5 SQLite migration creates one singleton preferences row with `enabled = 0`; no activity event or timestamp table is added.
- `WindowsIdleActivitySource.snapshot(at: datetime) -> ActivitySnapshot` implements the existing port and provides `reset()`. A `ResettableActivitySource` port extends `ActivitySource` with `.reset() -> None` and an `.available: bool` property. A small injectable idle-duration reader isolates Win32 calls and supports deterministic tests.
- The Win32 adapter uses `GetLastInputInfo` for the current interactive session and a tick counter only to compute elapsed time. Since `LASTINPUTINFO.dwTime` is a 32-bit tick value and Windows documents that it may not increase monotonically, invalid or implausible deltas produce `unknown` rather than a confident state. Windows documents that tick count includes sleep and hibernation time; on resume this source can report idle, never a long focused interval. [Microsoft: GetLastInputInfo](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getlastinputinfo), [Microsoft: Windows Time](https://learn.microsoft.com/en-us/windows/win32/sysinfo/windows-time).
- `ActivityAwarenessService` is a Qt-free application boundary that owns the enabled preference, wraps the source, returns `unknown` when disabled, and resets the source's in-memory interval on enable/disable changes. `ProactiveReminderService` receives this object through its existing `ActivitySource` parameter.
- The application composition root wires the SQLite preference repository and Windows source. Other platforms receive a source that returns `unknown` and cannot enable unsupported sensing.
- The existing reminder settings surface adds one unchecked control and clear copy explaining the five-minute, session-only signal and that no app name or input content is collected. Changing this control saves immediately and triggers one reminder reevaluation. It does not change reminder enabled/quiet-hour preferences.

## Lifecycle and failure behavior

1. A fresh install stores `enabled = false`; the reminder service sees `unknown` and performs no Windows query.
2. When the user enables awareness, the setting is persisted first, the in-memory activity interval is reset, and the scheduler reevaluates using one new snapshot.
3. Application composition loads the persisted preference once; the single-instance guard prevents a second process from changing it. While enabled, each scheduler evaluation may query Windows. A focused interval begins at the first sample following startup/resume/enable, not retroactively from an unknown time.
4. Pausing persists `false`, clears the in-memory interval, and immediately reevaluates as `unknown`. No further Windows calls happen while paused.
5. Unsupported platform, API failure, impossible tick arithmetic, or preference-load failure becomes `unknown`. It never falls back to another form of monitoring or logs raw timing data.
6. If saving the preference fails, the UI restores its last persisted checkbox state, displays a generic storage error, and reevaluates only if the stored value changed.

## Persistence, privacy, and data flow

Only the boolean opt-in survives restart. `ActivitySnapshot` is transient and flows from the local adapter through the existing application service into the deterministic decision engine. It is not added to chat context, memory, message payloads, event history, logs, or SQLite. The feature makes no network request.

The source is polled only by the existing reminder scheduler while the application is running and only when enabled. Pausing awareness is independent of turning reminders off; either control can suppress reminders, and the existing decision rules still apply.

## Test strategy

- Domain tests validate preference types and the disabled default.
- Repository/migration tests prove v4 data remains intact, the v5 row defaults off, settings survive reopening, and update failures are safe.
- Adapter tests inject idle durations and Win32 function wrappers; cover five-minute boundary, wrap arithmetic, non-monotonic/impossible values, API failure, unsupported platforms, state transitions, pause/resume reset, and no raw event/content surface.
- Application tests prove disabled and failed preferences return `unknown` without querying the source, enabled values are forwarded, pause resets state, and reminder evaluation remains deterministic.
- Qt tests verify unchecked default, privacy copy, persistence, revert on storage failure, immediate reevaluation, and disabled control on unsupported platforms.
- Run the full Stage 1–6 test suite, `compileall`, `pip check`, staged diff and secret scans. No real OS input content or external service is required in tests.

## Acceptance criteria

- Activity awareness is opt-in and starts disabled on a new profile.
- Enabling it queries only last-input age in the current Windows session; `focused` means recent input within five minutes, not a named app or task.
- Pausing it prevents subsequent OS queries and resets focused duration.
- No raw activity values or history are persisted or transmitted; no prohibited data source is read.
- Errors, unsupported platforms, and storage failures degrade to `unknown` without stopping chat, tasks, or reminders.
- Existing Stage 3 rule behavior remains unchanged for identical `ActivitySnapshot` inputs.
- UI explains what the signal does before the user enables it.
- All tests and static checks pass, the full diff is reviewed, and Stage 6 receives its own commit.

## Deferred work

Foreground application categorization, long-term activity history, task matching, smart schedules, personalized thresholds, Windows session/lock-state notifications, prompt/LLM use, voice, and richer activity privacy controls remain deferred. Any move beyond the single idle-duration signal requires a new privacy review and a separate spec.