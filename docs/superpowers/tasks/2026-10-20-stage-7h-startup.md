# Stage 7H execution record

Spec and plan: `2026-10-20-stage-7h-startup-design.md` and `2026-10-20-stage-7h-startup.md`. The existing roadmap explicitly requested default-off current-user startup. Execution uses the previously isolated stage2-local-data worktree, branch `codex/stage7h-startup-setting`, under the user's autonomous authorization. No repeated approval checkpoint.

Task 1: new tests initially failed on missing modules. Implemented Qt-free StartupService, an injected/lazy single-value WindowsStartupStore and quoted source/compiled launch composition. All 17 core tests passed, covering opt-in/out, conflict preservation, sanitized errors, exact HKCU scope, UTF-16 length limit and missing runtimes. No real registry access.

Task 2: four Qt tests initially failed on missing tray integration. Implemented a menu-open read and explicit checkbox write. Programmatic refresh is signal-blocked, and error states disable without dialogs and can recover when reopening. Added lifecycle guard proving app construction never accesses the injected startup store, plus Nuitka/frozen command composition tests. All 38 initial targeted tests and subsequent 20 lifecycle/composition/tray checks passed.

Ruling: enforce the Windows Run 260-character contract using UTF-16 code units; long source checkout commands show unavailable rather than creating a broken login entry. Cost: current deep development checkout may need a shorter installation path before this switch is usable. No source files or runtimes are moved automatically.

Ruling: conflict means a different existing command at the exact AICompanion value; preserve it and fail closed. Current-user registry operations do not provide a compare-and-set transaction here, so concurrent external registry editing is not guaranteed atomic. Existing single-instance protection prevents normal duplicate-app writers. Cost: moving an enabled installation requires manual cleanup/migration, deferred to installer design.

Validation: **669 tests passed in 12.74 seconds** in a real Windows process, offscreen Qt, temporary data and fake devices/stores. Compileall, pip check and diff check passed. No actual login startup was enabled, disabled or read for acceptance; manual logon and compiled startup are still unverified. README and roadmap now distinguish implemented source voice from naturalness, microphone and packaging gates.

Independent final review: no actionable findings; reviewer independently passed all 23 core/configuration/tray tests. No dependencies, database migration, system service, scheduled task, administrator setting or microphone action added. Credential-pattern scan and final staged diff review passed. The actual user startup setting remains untouched.
