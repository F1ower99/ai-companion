# Stage 7I Memory Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline under existing autonomous authorization.

**Goal:** Inspect/search/delete saved local memories from a temporary privacy panel.

**Architecture:** Bounded Qt-free service over existing repository/Clock; additive SQLite offset; injected dialog in existing provider settings. No new persistence tables or automatic memory behavior.

**Tech Stack:** existing Python/PySide6/SQLite/pytest only.

**Spec:** `docs/superpowers/specs/2026-10-20-stage-7i-memory-controls-design.md`

## Constraints and review focus

Use only fake/temporary data. No credentials/network/microphone, auto creation, bulk delete or permanent toolbar. Test expiry visibility separately from provider expiry, paging after deletion, HTML-like content as literal text, cancellation and stale selection. Time must come from injected clock.

## Task 1: Paging and service

Modify `ports/repositories.py`, `infrastructure/sqlite/repositories.py`; create `application/memory_management.py`, `tests/application/test_memory_management.py`; add tests to `tests/infrastructure/test_sqlite_repositories.py`.

- [x] RED tests for offset paging/validation and unchanged defaults.
- [x] Add keyword-only offset without changing other consumers; focused GREEN.
- [x] RED service tests: clock/lookahead/query propagation, invalid clock/query/offset, exact delete/NotFound.
- [x] Implement MemoryPage and MemoryManagementService; focused GREEN.

## Task 2: Temporary memory dialog and composition

Create `desktop/memory_dialog.py`, `tests/desktop/test_memory_dialog.py`; modify `provider_settings_dialog.py`, `chat_window.py`, `app.py`; test settings/lifecycle wiring with fake services.

- [x] RED UI tests for open/filter/page/plain detail/confirm/cancel/error/clear-on-hide.
- [x] Implement minimal dialog and provider-settings button; inject service only from app composition.
- [x] Add temporary SQLite reopen/provider-context deletion regression.
- [x] Update README/roadmap/task ledger; run full regression, compileall, pip check, diff/secret checks.
- [x] Fresh independent review; repair important findings; full regression; separate commit and normal push.
