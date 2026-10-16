# Stage 6 Completion Record: Minimal Local Activity Awareness

Started: 2026-10-12; completed: 2026-10-16
Spec: [`Stage 6 design`](../specs/2026-10-12-stage-6-minimal-activity-awareness-design.md)
Plan: [`Stage 6 implementation plan`](../plans/2026-10-12-stage-6-minimal-activity-awareness.md)

## Delivered

- Added schema v5 for one opt-in boolean preference; new and upgraded profiles default to disabled.
- Added a Qt-free `ActivityAwarenessService` and an injectable Windows idle-duration adapter. Only recent-input age from the current session is read, and all status timestamps remain in memory.
- Added an independent privacy-described enable/pause control to Reminder Settings. A successful toggle triggers one reminder reevaluation; a failed save reverts the control.
- Added tests for threshold and tick boundaries, pause/resume, stale intervals, storage/API failures, restart persistence, unsupported systems, UI disclosure, app composition, and zero OS polling while disabled.

## Architecture decisions

- Kept the current activity preference protocol alongside `ActivitySource` in `ports/activity.py`; it is a distinct repository from reminder preferences and contains only a boolean.
- Kept state timestamps and idle values transient; no activity timeline/history or provider context is created.
- Used a fixed five-minute threshold and five-minute maximum sample gap. State means recent input, not a named app, foreground focus, or task identity.
- No real Windows input query was run during automated tests or development.

## Review and verification

- Focused Stage 6 layer/UI/lifecycle tests: 85 passed before final full regression.
- App startup subprocess tests now set `LOCALAPPDATA` to a per-test temporary directory; this prevents an already-running user's instance lock from making tests fail or touching the real profile. The new isolation regression test was observed failing before the helper fix.
- Final full suite: `QT_QPA_PLATFORM=offscreen python -m pytest -q -p no:cacheprovider` — 370 passed (latest fresh run recorded at commit time).
- `compileall` passed with bytecode redirected to a temp cache; `pip check` reported no broken requirements; `git diff --check` passed; token-shaped secret, debug hook, and prohibited activity API scans were clean.
- The non-monotonic, full-counter-cycle, and greater-than-half-cycle new-input regression tests were observed failing before their fixes and pass afterward; all 17 Windows activity adapter tests pass. The adapter uses `GetTickCount64` to maintain an in-memory input timestamp epoch and returns `unknown` when a full-cycle epoch cannot be resolved.
- Whole-diff independent review found and the implementation fixed the long-uptime 32-bit tick ambiguity. Follow-up review confirmed no remaining behavioral finding; re-review included the staged fix and regression test.

An auto-review rejected a temporary test-only edit that would have removed the SQLite singleton constraint. The schema invariant was kept; the direct insertion test and full test suite verify the constraint without weakening implementation.

## Remaining validation

The user should manually review the unchecked-by-default setting and, only if desired, enable it on Windows to validate idle transitions. No application identity or input content is captured. Stage 5 live provider UX remains untested and requires a user-owned credential and an explicitly selected message/context.
