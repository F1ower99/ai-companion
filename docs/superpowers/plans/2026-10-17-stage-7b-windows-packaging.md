# Stage 7B Windows Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide a safe, inspectable standalone Windows build path and verified dependency license inventory.

**Architecture:** A PowerShell entry point preflights the selected virtual environment and MSVC tools before running Qt deployment. A Python metadata utility reports the installed runtime dependency closure and unknown licenses. Build output remains local and ignored.

**Tech Stack:** Python 3.10+, PowerShell, existing PySide6 6.11.2, optional deployment tooling, pytest.

**Spec:** `docs/superpowers/specs/2026-10-16-stage-7b-windows-packaging-design.md`

## Global Constraints

- Use explicit standalone mode; no installer, publication, registry writes, or destructive cleanup.
- Tool installation is explicit and separate from build; build must not silently install compilers or packages.
- Never launch against the real profile during automated checks; no credentials or SQLite content are read.
- Missing toolchain produces an actionable preflight failure; do not claim an executable exists without building it.
- Generated compiler/output directories remain ignored.

## Review Focus

- Spaces in workspace and virtual-environment paths survive process invocation (Task 2).
- Missing venv, deployment tool, or dumpbin stops before deployment (Task 2).
- Missing/unparseable distribution metadata is flagged, never replaced by guessed licensing (Task 1).
- Dependency traversal handles cycles and environment markers deterministically (Task 1).
- A dry run does not install packages or launch the application (Task 2).

---

### Task 1: Runtime Dependency License Inventory

**Files:** Create `scripts/write_third_party_notices.py`, `tests/tooling/test_third_party_notices.py`, `THIRD_PARTY_NOTICES.md`; modify optional development dependencies only if parser dependencies are necessary.

**Interfaces:** `collect_notices(requirements: list[str], distribution_lookup=importlib.metadata.distribution)->list[PackageNotice]`; `render_notices(notices)->str`. CLI reads runtime requirements from installed `ai-companion` metadata or explicit requirement arguments, traverses applicable Requires-Dist entries, records name/version/license-expression-or-license/license-file paths, sorts by normalized name, and fails with clear missing metadata diagnostics. No current-time stamp or absolute machine paths in generated output.

- [x] Write fixture-metadata tests for deterministic ordering, cyclic requirements, environment markers, license expression precedence, missing license flags, and missing distributions.
- [x] Run focused tests and verify missing utility failure.
- [x] Implement the metadata utility; use a declared development parser dependency if required rather than a custom requirement parser.
- [x] Run focused tests; generate notices from this interpreter's installed runtime closure and inspect actual metadata.

### Task 2: Deployment Configuration and Safe Preflight

**Files:** Create `pysidedeploy.spec`, `scripts/build_windows.ps1`, a testable preflight helper if needed, and `tests/tooling/test_windows_build.py`; modify `pyproject.toml` for an explicit optional deploy extra if required.

**Interfaces:** `build_windows.ps1 [-VenvPath PATH] [-PreflightOnly] [-DryRun]`; default venv is repo `.venv`, while `-VenvPath` supports this existing shared development environment. Validate Windows, virtual-environment identity, pyside6-deploy and dumpbin before deployment. Invoke deployment with config, explicit standalone mode and `--no-install` only if supported by installed 6.11.2; otherwise fail closed or construct an equivalent offline invocation after inspecting that version. Output under `dist/`; preserve compiler artifacts. Do not install system/build tools automatically.

- [x] Add executable controlled-input preflight tests for missing prerequisites and paths containing spaces; validate config through its parser, not substring checks.
- [x] Run tests and confirm absent build interface fails.
- [x] Implement config/preflight, inspect installed tool's actual CLI/template, and align documented standalone output with actual tool behavior. Record any version-specific ruling.
- [x] Run preflight; run deployment dry-run only if available without installation. Attempt a real build only with an already functional toolchain; accurately record any blocker.

### Task 3: Build Guide, Review, and Stage Commit

**Files:** Update README, roadmap and `docs/superpowers/tasks/2026-10-17-stage-7b-windows-packaging.md`.

- [x] Document exact prerequisite install command, build/preflight command, actual output path, temporary LOCALAPPDATA launch, credential boundary, and manual pet/chat/reminder/tray checks.
- [x] Run full pytest, compileall, pip check, and diff/secret checks. Review the stage with a fresh reviewer and fix important issues with tests.
- [x] Commit the packaging stage independently and record actual verification/toolchain limitations. No push/merge or public binary release.

## Completion Review

Self-review: metadata inventory is a build baseline, not a redistribution license certification; package license files and manual clean-profile UX acceptance remain required. The toolchain may block binary creation without blocking tested preflight/configuration work. Do not substitute a dry run for a real build in the completion report.
