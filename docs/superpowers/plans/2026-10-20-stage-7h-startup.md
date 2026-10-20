# Stage 7H Startup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline, task-by-task under existing autonomous authorization.

**Goal:** Add explicit current-user startup without enabling it during development.

**Architecture:** Qt-free StartupService owns conflict/error policy; WindowsStartupStore owns one lazy registry value; a lazy tray action queries on menu open and writes only on user toggle. Command composition supports source Pythonw and compiled executable without inheriting argv or secrets.

**Tech Stack:** existing Python, PySide6, stdlib winreg/subprocess; no dependency or schema change.

**Spec:** `docs/superpowers/specs/2026-10-20-stage-7h-startup-design.md`

## Global constraints

No actual registry writes or reads in automated checks. Default off, HKCU only, exact value ownership, sanitized errors, no modal UI. Reuse the existing isolated worktree; new `codex/stage7h-startup-setting` branch. No compiler, driver or dependency installation.

## Review focus

Conflict races and read/write failures preserve unrelated entries; refresh does not emit a write; source paths with quotes/spaces survive bootstrap; startup does not inherit API/model environment config; application construction never accesses registry.

## Task 1: Store, policy and command

Create `application/startup.py`, `infrastructure/windows_startup.py`, `desktop/startup_configuration.py`, `tests/application/test_startup.py`, `tests/infrastructure/test_windows_startup.py`, `tests/desktop/test_startup_configuration.py`.

- [x] Write failing fake-store tests for lazy read, opt-in/out, conflicting entry and failures.
- [x] Write fake-winreg tests for missing keys, exact HKCU value operations, value-type rejection, sanitized failure and preserved unrelated values.
- [x] Write command tests for space/apostrophe/metacharacter paths, missing runtime, source/compiled modes, no argv inclusion and lazy store composition.
- [x] Implement minimum code; run focused tests.

## Task 2: Tray composition and validation

Modify `desktop/tray.py`, `desktop/app.py`, add `tests/desktop/test_startup_tray.py`.

- [x] RED fake-service tests for menu-open read, toggle write, signal-blocked refresh, failures/recovery and no startup access on construction.
- [x] Implement lazy menu action and app composition; rerun focused and lifecycle tests.
- [x] Update README, roadmap and stage task record with actual manual acceptance limits.
- [x] Full pytest, compileall, pip check, diff/secret checks; independent review; fix Important issues and rerun.
- [ ] Commit stage separately and push normally only after all checks. No real Run entry created.
