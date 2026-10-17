# Stage 7B Design Spec: Windows Standalone Packaging Baseline

Date: 2026-10-16
Status: Approved for autonomous Stage 7B work under the user's overnight-development authorization

## Purpose

Prepare a repeatable Windows standalone build of the current AI Companion app, so a clean Windows profile can be used to validate startup, local SQLite placement, the desktop pet, chat, and reminders. This spec is independent from selecting a local speech engine; it packages only the features currently composed into the app.

## Goals

- Configure the existing Qt for Python deployment tool to package `src/companion/desktop/app.py` into an explicit Windows standalone directory.
- Add a safe PowerShell build preflight that checks Windows, the project virtual environment, `pyside6-deploy`, and MSVC `dumpbin` before starting the build.
- Keep generated output and compiler work in ignored `dist/` and build directories. The build script must not delete existing user data or write to `%LOCALAPPDATA%`, Credential Manager, or the registry.
- Record shipped Python package versions, declared license metadata, and license-file paths when available; flag missing metadata for review.
- Document how to launch the standalone app with a temporary `LOCALAPPDATA` profile and how to verify that the database remains in the expected per-user directory.
- Keep the current source-run workflow available and avoid adding an installer, signing, auto-update, or auto-start behavior.

## Non-goals

- No real microphone/STT/TTS integration, speech models, or voice provider.
- No installer signing or publishing, GitHub release, store upload, registry changes, auto-start, or data migration from another profile.
- No pruning of package imports by speculative exclusions. The first build favors correctness and reviewable output over minimum size.
- No changes to SQLite schemas, task/reminder behavior, credential storage, or provider consent.

## Existing constraints and approach

- Python 3.10+, PySide6 Essentials 6.11.2, optional Addons 6.11.2, and a working source entry point in `src/companion/desktop/app.py`.
- `outputs/architecture-decision.md` already selects `pyside6-deploy`/Nuitka and requires a third-party license inventory.
- Qt for Python documents `pyside6-deploy` as a Nuitka wrapper. It supports a standalone directory and requires the Windows `dumpbin` tool from MSVC. The project configuration will set `mode = standalone` explicitly because the tool's default can change between Qt releases. See [Qt deployment documentation](https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-deploy.html).
- Use the existing virtual environment's full PySide6 deployment tooling. Building must not silently install compiler/system software; if preflight fails, show the missing prerequisite and stop.
- The first deliverable is an unpackaged standalone directory, not a single-file executable or installer. This makes missing Qt plugins/resources easier to inspect and test.

## Build and license inventory

- `pysidedeploy.spec` names the app, project directory, source entry point, and explicit standalone mode. The wrapper stages each invocation in a fresh `build/windows/build-<id>` directory and writes output under `dist/build-<id>/AICompanion.dist/app.exe`; previous builds are preserved.
- `scripts/build_windows.ps1` verifies all prerequisites before invoking `pyside6-deploy`, uses the current virtual environment, and never performs recursive cleanup. Existing build output is retained unless the user explicitly removes it.
- Installed Qt 6.11.2 has no `--no-install` flag and performs pre-build cleanup even in dry-run mode. Its empty `python.packages` field explicitly skips package installation; the wrapper requires already installed deployment packages and invokes the tool only in a fresh staging tree. No compiler/download confirmation is supplied. A changed Qt version requires revalidation.
- `scripts/write_third_party_notices.py` reads installed distribution metadata from the active interpreter and writes a deterministic inventory of packages included by the app's declared dependencies. It records package/version/license expression and license files when present; it reports packages with absent/unparseable metadata instead of inventing a license.
- `THIRD_PARTY_NOTICES.md` is generated only from verified metadata and checked in alongside the build configuration.
- `README.md` explains prerequisites, build command, standalone output path, clean-profile launch, data/credential locations, and the remaining manual review required before redistribution.

## Data and failure boundaries

- Automated packaging checks do not launch the application against the real user profile. Clean-profile smoke tests set `LOCALAPPDATA` to a test-owned temporary directory.
- Build and license commands do not read application SQLite contents or Credential Manager secrets.
- Missing MSVC/dumpbin, deployment tool, or license metadata produces a concise actionable failure; no system installation or account authorization is attempted.
- Build output remains local. No binary is pushed or released during this stage.

## Test strategy

- Unit-test the preflight's prerequisite reporting and license inventory parsing with temporary metadata fixtures.
- Test the deployment config's app name, entry point, output folder, and standalone mode as plain configuration values.
- Run source regression suite, compileall, pip check, whitespace/secret checks, and `pyside6-deploy --dry-run` when available.
- Attempt a real standalone build only if the toolchain is already installed and the configured build can run without modifying system state. Keep all output local and ignored.
- Human Windows acceptance is still required to launch the standalone folder in a clean temporary profile and verify pet, local database creation, chat settings, task controls, reminders, tray exit, and no accidental start-on-login.

## Acceptance criteria

- A developer can run one documented PowerShell command to preflight and build the standalone directory with no destructive cleanup.
- A clean temporary-profile smoke run does not read or alter the user's existing profile or credentials.
- The license inventory is deterministic and flags missing metadata without guessing.
- Existing source-run and all Stage 1–7A tests remain green.
- The docs distinguish automated build success from manual Windows launch acceptance. No installer or release is claimed complete before that manual run.

## Deferred work

Local speech engine selection, installer/signing, auto-start, auto-update, publication, package-size optimization, and user-led release acceptance remain deferred. This stage does not alter the speech-stack question in `OPEN_QUESTIONS.md`.
