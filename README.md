# AI Companion

An experimental, local-first Windows companion for study planning and supportive conversation.

## Development setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m companion.desktop.app
```

The desktop shell provides a draggable, always-on-top pet and a chat panel. Right-click the pet to open chat or exit when Windows has no system tray; closing the pet exits the app, while closing chat leaves the pet running. The chat panel includes **Today's Tasks** and compact **Reminder Settings** entries.

## Local data and privacy

Goals, tasks, basic memories, reminder preferences, reminder state, reason-code events, academic terms, course rules, calendar exceptions, conversations, provider settings, and the activity-awareness toggle are stored in SQLite at `%LOCALAPPDATA%\AICompanion\companion.sqlite3` (normally under your Windows user profile). Activity snapshots and timestamps are never persisted. Provider credentials are stored separately in Windows Credential Manager. If the local database cannot be opened, the pet and task/reminder controls remain available safely; chat is disabled when its storage is unavailable. Stage 3 adds a deterministic local decision engine, planned task times, quiet hours, cooldowns, snooze/extension/skip/completion actions, and a small non-modal reminder card. Stage 6 adds an optional, disabled-by-default signal that checks only whether the current Windows session received input within five minutes. It does not read app names or input content; pausing it returns the activity state to `unknown`. Ordinary reminders remain quiet while activity is unknown, except for a feasible, imminent P0 hard deadline. Stage 4 adds local academic-calendar persistence, deterministic course lookup with holiday/rest/makeup overrides, and a read-only study-day summary; it does not add calendar UI or import/sync. Stage 5 adds a local transcript and an optional OpenAI-compatible text provider. No request is made until the user configures an HTTPS provider and local credential, reviews the visible host and outgoing content, and sends a message. Recent conversation, saved memories, and today's plan are independently opt-in; reply language, tone, and principles are included with provider requests. The app does not collect app names, window titles, keystrokes, or screen contents.

Stage 7A provides a Qt-free local voice-session foundation: bounded transient PCM, local-only provider ports, explicit transcription/speech operations, cancellation, and interruption. Real speech engines and hardware adapters are not configured, so voice buttons remain disabled and startup does not access a microphone. A validated transcript can enter an empty editable draft; sending still requires the existing explicit Send action. Audio and transient voice state never enter SQLite or provider context. The local speech-stack choice is recorded in `OPEN_QUESTIONS.md`.

## Offline speech recognition

Stage 7C adds optional **local CPU speech recognition** using faster-whisper 1.2.1 and an explicitly supplied complete model directory. Install with `python -m pip install -e ".[dev,stt]"`. The default is Chinese transcription with CPU int8 and four threads. Runtime accepts 16kHz mono PCM16 only, checks cancellation between native operations, and never downloads models. A complete local multilingual Whisper base bundle requires `model.bin`, `config.json`, `tokenizer.json`, and `vocabulary.txt`; repository IDs, URLs, UNC shares and Windows mapped network drives are rejected.

Download the data files separately from the [pinned publisher revision](https://huggingface.co/Systran/faster-whisper-base/tree/ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66), preserving model notices. Keep models under ignored `.models/` or another local directory. The model bundle is about 148 MB; installed dependencies and native inference require additional space/RAM. Exact model hashes and real smoke evidence are in [the Stage 7C asset record](docs/offline-stt-assets-2026-10-18.md).

For a deliberately selected public test WAV (not personal recordings), run:

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
python scripts/smoke_local_stt.py --model-dir (Resolve-Path .\.models\whisper-base).Path --wav 'C:\public-fixtures\sample-16k-mono.wav' --language zh
```

The CLI prints processing time and character count; recognized text requires the explicit `--show-transcript` option. It has no microphone access. A real 11-second public English fixture passed on CPU with Python socket connections blocked (0.76–0.95 seconds in this development run, including model setup; not a general benchmark). A 5.616-second public Chinese fixture also ran offline, but produced a substantive recognition error; Chinese usability is not signed off. Native calls can only be cancelled cooperatively at their boundaries. This slice does not change reminders or chat consent.

## Optional microphone capture adapter

Stage 7D adds `QtMicrophoneCapture`, a lazy Qt Multimedia adapter for the existing optional `voice` extra. Lifecycle calls must run on its owning Qt thread. Construction does not query devices. An explicit start requires already-granted microphone permission and supports only a default input with 16kHz mono PCM16. Buffered PCM is capped at 60 seconds; a timer also releases silent/stalled capture, and cancellation clears owned bytes. Audio is never written to disk or sent over the network.

This adapter is **not wired to the chat controls yet**: recording remains disabled in the app. The current synchronous VoiceSession must not invoke this Qt adapter's stop method from a worker; a separate integration slice must release capture on the UI thread and run recognition in a worker. Tests use fake devices; real permission/device compatibility, visible recording controls, TTS and packaged voice still require implementation/acceptance. Missing optional runtime or unsupported devices fail safely.

## Windows standalone build baseline

Use a Windows x64 Native Tools prompt with MSVC `cl` and `dumpbin` already on PATH, then activate the project virtual environment. Install build dependencies explicitly:

```powershell
python -m pip install -e ".[dev,deploy]"
.\scripts\build_windows.ps1 -PreflightOnly
.\scripts\build_windows.ps1 -DryRun
.\scripts\build_windows.ps1
```

For an existing shared environment, add `-VenvPath 'C:\path with spaces\to\.venv'`. The wrapper checks the pinned Qt/Nuitka versions and prerequisites before creating output. It stages code in a fresh ignored `build/windows/build-<id>` directory, keeps compiler files, and reports the standalone folder `dist/build-<id>/AICompanion.dist` with `app.exe`. Prior output is retained. The Qt 6.11.2 tool has no `--no-install`; an empty package-install list plus preflight prevents implicit dependency installation. The wrapper supplies no download confirmation and never installs MSVC. Invoke the wrapper rather than running the checked-in spec directly.

Regenerate the runtime metadata inventory with `python scripts/write_third_party_notices.py`. `THIRD_PARTY_NOTICES.md` records verified installed versions and declared licenses, including missing metadata flags. It is not a complete redistribution package: Python, native Qt components/plugins, applicable LGPL/GPL license texts and release obligations still need review. The installed wheels currently list a commercial-license file while declaring LGPL/GPL alternatives; review and include the selected applicable texts before redistribution.

No executable has been produced on this development machine: preflight currently reports missing MSVC `cl`/`dumpbin` and deployment packages. Automated tests cover the wrapper and controlled build inputs; neither a deployment dry run nor a real build nor manual packaged launch is claimed passed.

After a successful build, use a temporary data profile for pet/tasks/reminders/tray smoke checks:

```powershell
$smokeProfile = Join-Path $env:TEMP ('AICompanion-smoke-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $smokeProfile | Out-Null
$previousLocalAppData = $env:LOCALAPPDATA
try {
    $env:LOCALAPPDATA = $smokeProfile
    Start-Process -FilePath '.\dist\<build-id>\AICompanion.dist\app.exe' -Wait
} finally {
    $env:LOCALAPPDATA = $previousLocalAppData
}
```

Verify pet dragging/chat opening, task creation, local reminder controls, the database under `$smokeProfile\AICompanion`, and tray exit. Temporary LOCALAPPDATA isolates SQLite, **not Windows Credential Manager**. Do not open provider settings or send messages in this smoke run; use a separate Windows test account for credential/provider UX acceptance. Voice and startup-on-login remain disabled/unimplemented. No installer, signature, automatic update, or release publication is included.

## Tests

From PowerShell, activate the development environment and run:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q
python -m compileall -q src tests
python -m pip check
```

The regression suite covers deterministic task decisions, SQLite migrations and reminder/calendar/chat/activity-preference persistence, local-time resolution, the compact Qt reminder UI, course-week rules, calendar exceptions, study-plan summaries, fake activity sensing, and offline provider request/error handling. Full verification commands are listed above. Manual Windows idle behavior, live provider UX, voice, packaging, and semantic memory search remain future work.
