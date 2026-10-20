# Stage 7J Reminder Replies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline under existing autonomous authorization.

**Goal:** Preview and explicitly apply bounded offline reply commands to the current reminder.

**Architecture:** Qt-free parser → transient explicit reply dialog → existing ReminderCard/respond path. No decision-policy, persistence, provider or microphone changes.

**Tech Stack:** existing Python/PySide6/pytest; stdlib regex/unicode only.

**Spec:** `docs/superpowers/specs/2026-10-21-stage-7j-reminder-replies-design.md`

## Constraints/review focus

Automatic cards must still not accept keyboard focus. Parsing is not execution. All service constraints remain authoritative. Raw text must not be persisted/sent/logged. Test edited proposals, double-clicks, parent dismissal, ambiguous snooze durations and masked errors.

## Task 1: Pure reply proposals

Create `application/reminder_reply.py`, `tests/application/test_reminder_reply.py`.

- [ ] RED action/duration grammar and rejection tests, including half-hour and Chinese numerals.
- [ ] Implement minimal immutable proposal/parser; focused GREEN.

## Task 2: Explicit temporary reply UI

Create `desktop/reminder_reply_dialog.py`; modify `desktop/reminder_card.py`; add `tests/desktop/test_reminder_reply_dialog.py` using fake services.

- [ ] RED preview/confirm/no-focus/edited/cancel/stale/busy/error tests.
- [ ] Implement reply button/dialog and structured forwarding; preserve original buttons and card close semantics.
- [ ] Add fake-clock/temporary-SQLite parsed extension acceptance and re-evaluation coverage.
- [ ] Update README/roadmap/task record; full regression, compileall, pip check, diff/secret checks.
- [ ] Independent review, necessary fixes/retest, separate stage commit and normal push.
