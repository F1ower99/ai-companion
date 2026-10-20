# Stage 7H: Explicit current-user startup setting

Approved direction: the existing roadmap requires configurable, default-off login startup. The user's autonomous authorization permits spec self-review, inline implementation and independent review without routine approval waits.

## Scope and alternatives

Implement one tray checkbox, backed by this application's named value in HKCU Run. No scheduled tasks, services, machine-wide configuration, installer, elevated permissions or new dependency. Registry source-of-truth is simpler than duplicating an operating-system setting in SQLite. Defer installer-managed startup until an installer exists.

## Behavior and boundaries

- Constructing the service or tray never reads or writes registry settings. Query only when the user opens the tray menu. With no value, show unchecked. Never enable automatically.
- Clicking the checkbox is the only write path. Enable stores a quoted launch command as REG_SZ under `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`, value `AICompanion`. Disable deletes only that value, never a key or any other value.
- A Qt-free application service accepts an injected store with `read() -> str | None` and `write(str | None)`. Only absent or exactly matching commands may be changed. A different existing command or non-string registry type fails closed; do not overwrite another installation's entry.
- Infrastructure lazily imports standard-library winreg. Read errors, write errors and conflicting entries become a sanitized StartupError; no command, filesystem path or registry content is logged or shown.
- On error the tray action is unchecked/disabled for the current menu display and shows a concise unavailable label. A later menu open retries the read. No modal dialog or automatic retry loop.
- Build source-mode launch from an existing absolute Pythonw executable and source root. Use a fixed `-c` bootstrap that inserts the trusted source path and calls the app main; quote with Windows command-line rules. Do not inherit current argv or persist API keys, model paths or environment settings. This avoids stale shared editable metadata pointing at another checkout.
- For compiled mode use only the current absolute executable, detected by Nuitka's module-level `__compiled__` marker (or frozen marker). No Python bootstrap. Compiled startup remains subject to actual package validation.
- Run commands must fit the documented 260-character limit, conservatively counted as UTF-16 code units. Reject longer commands, control characters and unencodable text before composing a service. A long source checkout may therefore show unavailable until installed at a shorter path; do not write a command known to exceed the OS contract.
- Source startup requires the installed runtime and checkout to stay present. Launch does not download modules/models and voice remains opt-in per launch environment. No startup switch is written during this development session.

## Privacy and failure handling

Only the one app-owned Run value is accessed, after tray-menu interaction. Credentials, conversations, microphone, activity history and other startup entries are never inspected. Automated tests use a fake registry and isolated Qt processes; creating an application must remain side-effect free for startup configuration. Unsupported platforms or missing Pythonw report unavailable. No database migration.

## Acceptance and tests

1. Fake store proves construction is lazy, disabled by default, explicit opt-in/out roundtrips and conflicting entries are preserved.
2. Fake winreg proves only HKCU and the exact key/value/type are touched; missing key/value is harmless, access errors sanitized, other values preserved.
3. Paths with spaces, quotes and metacharacters remain a single Windows executable argument; generated bootstrap roundtrips via Python AST and includes no current argv/secrets. Compiled mode has no bootstrap.
4. Qt fake service proves menu-open reads, checkbox writes only after action, refresh never writes, errors disable safely and can recover on next open. Existing app lifecycle tests never access real registry.
5. Full regression, compileall, pip check, diff inspection and independent review pass before stage commit.

Manual login behavior and compiled-executable startup remain unverified until user-led acceptance. Autostart is not enabled as a test. Deferred: startup arguments/model configuration UI, entry migration after installation moves, signing, installer/uninstaller and startup delay.

Windows Run has no compare-and-set value API used here. The service rechecks ownership for each action, and the application already has a single-instance lock, but an unrelated external process can race between read and write. Do not claim transactional protection from concurrent external registry editing.

Primary reference: [Microsoft Run and RunOnce registry keys](https://learn.microsoft.com/en-us/windows/win32/setupapi/run-and-runonce-registry-keys) (current-user Run behavior, command length and possible delayed execution).

Self-review: scope is one OS setting with lazy UI access; no ambiguity requiring a product fork. A different existing command is deliberately unavailable rather than overwritten. Default-off means no automatic creation, not forcibly deleting a user's existing enabled value.
