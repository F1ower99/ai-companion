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

Stage 7A provides a Qt-free local voice-session foundation: bounded transient PCM, local-only provider ports, explicit transcription/speech operations, cancellation, and interruption. Later slices add optional local recognition/capture and explicit opt-in UI wiring; default startup still does not access a microphone. A validated transcript can enter an empty editable draft; sending still requires the existing explicit Send action. Audio and transient voice state never enter SQLite or provider context. The offline speech direction is recorded in `OPEN_QUESTIONS.md`.

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

Stage 7E connects this adapter to explicit press-to-talk. VoiceSession.prepare_transcription releases capture on the UI thread and transfers a single-use PCM job to a worker; the synchronous stop_capture compatibility API must not be called from a worker when using Qt capture. Pending cancellation clears PCM immediately; already-running native recognition clears it when the worker exits and cannot publish a cancelled result. Tests use fake devices; real permission/device compatibility, recording ergonomics, Chinese recognition quality, TTS and packaged voice still require acceptance. Missing optional runtime or unsupported devices fail safely.

## Explicit offline recording (developer opt-in)

Recording is disabled unless an absolute local model directory is explicitly supplied. Install the optional modules separately, then launch this checkout:

```powershell
python -m pip install -e ".[dev,voice,stt]"
$env:PYTHONPATH = (Resolve-Path .\src).Path
$env:AI_COMPANION_STT_MODEL_DIR = (Resolve-Path .\.models\whisper-base).Path
python -m companion.desktop.app
```

Models must already be downloaded and complete as described above. The app never installs modules, downloads weights, requests microphone permission or starts recording on startup. The model path is a launch setting; it is not saved to SQLite. Without the environment setting or optional modules the button explains what is missing. To disable this launch setting, remove `Env:AI_COMPANION_STT_MODEL_DIR` before launching again.

Open chat and **hold** the recording button. Permission is requested following that action. Releasing while a permission prompt is pending cancels this recording; if permission is granted later, hold again to start a new one. While listening, release to stop/release the device and recognize in the background. A separate Cancel voice action discards the operation. Hiding/closing chat cancels it too; reopening never starts recording. A cancelled active decode must exit before another recording, with a visible waiting status. At 60 seconds the adapter releases the device and submits the captured portion once.

The result fills only an empty editable draft. Existing typed text stays intact, and no voice result is sent or persisted until you explicitly press Send under the existing text-provider disclosure. Chinese Whisper base output has a known sample error; inspect/edit the draft. Natural-language task actions are not implemented. Explicit synthesized playback is described below. The optional Qt 6.11.2 native module has been imported successfully, but actual Windows microphone permission, device-format support and interruptions remain user-led manual acceptance; automated tests never use a microphone.

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

Verify pet dragging/chat opening, task creation, local reminder controls, the database under `$smokeProfile\AICompanion`, and tray exit. Temporary LOCALAPPDATA isolates SQLite, **not Windows Credential Manager**. Do not open provider settings or send messages in this smoke run; use a separate Windows test account for credential/provider UX acceptance. Leave voice opt-ins unset for this baseline smoke; packaged voice remains unverified and startup-on-login is unimplemented. No installer, signature, automatic update, or release publication is included.

Dependency inventories must match the components intended for the build. The default [base inventory](THIRD_PARTY_NOTICES.md) covers the desktop core; the [voice inventory](docs/THIRD_PARTY_NOTICES_VOICE.md) also covers the optional recording, Whisper and Kokoro runtimes. Neither includes model licenses or certifies redistribution. For a current editable installation, select extras explicitly:

```powershell
python scripts/write_third_party_notices.py --extra voice --extra stt --extra tts --output docs/THIRD_PARTY_NOTICES_VOICE.md
```

Unknown extras fail before writing output. The tool reads installed project metadata: an older editable installation can lack newly declared extras. Refresh that installation from this checkout, or inventory the current `pyproject.toml` runtime roots explicitly without changing the shared environment:

```powershell
python scripts/write_third_party_notices.py --requirement 'PySide6-Essentials==6.11.2' --requirement 'PySide6-Addons==6.11.2' --requirement 'faster-whisper==1.2.1' --requirement 'sherpa-onnx==1.13.8' --requirement 'numpy>=2,<3' --output docs/THIRD_PARTY_NOTICES_VOICE.md
```

`--extra` and `--requirement` are mutually exclusive; development/build extras are excluded unless explicitly selected. Qwen voice experiments use a separate environment and are not part of this app inventory.

## Inspect and delete saved memories (Stage 7I)

Open “模型与隐私设置” → “管理本地记忆” to inspect existing local memories. Search by literal content, filter the five memory categories, and browse 50 records per page. Expired records are visible by default in this management panel; normal chat retrieval still excludes them. Opening the panel does not save provider form edits or access credentials/network services.

Select a record to inspect its content, source, importance and expiration. “删除选中记忆” asks for confirmation with No as the default, then deletes only that record. Hiding or refreshing the panel invalidates a pending confirmation; closing the panel clears its displayed records. Deletion affects subsequent memory retrieval. Requests already started and conversation messages containing similar text remain separate; use “清空对话” for the transcript. No automatic memory extraction, editing, bulk delete or physical secure-erasure guarantee is added.

## Optional login startup (Stage 7H)

The tray menu includes “开机启动（当前用户）”. It creates no startup entry by default and reads only this app's Run value when the menu opens. Only an explicit checkbox action enables or disables it. Disabling removes this application's `AICompanion` value from current-user Run; other entries remain untouched. No administrator access, service or scheduled task is used.

Missing runtimes, unsupported platforms, an entry pointing to a different installation, access failures or a command exceeding Windows' 260-character limit show “开机启动暂不可用”. A long source checkout may be unavailable until installed at a shorter path. Source mode needs its Pythonw executable and checkout to stay present; packaged mode uses the current executable. Neither stores current command-line arguments, credentials or model environment settings. Close/reopen the tray menu to retry a temporary read failure. Moving an enabled installation requires manual handling of its old entry; no automatic migration is attempted.

Tests use fake stores and never enable real login startup. Actual logon behavior and the compiled command need user-led validation after packaging. Startup may be delayed by Windows.

## Tests

From PowerShell, activate the development environment and run:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q
python -m compileall -q src tests
python -m pip check
```

The regression suite covers deterministic task decisions, SQLite migrations and reminder/calendar/chat/activity-preference persistence, local-time resolution, the compact Qt reminder UI, course-week rules, calendar exceptions, study-plan summaries, fake activity sensing, offline provider request/error handling, and local voice lifecycle/adapters with fake devices. Full verification commands are listed above. Manual Windows idle behavior, live provider UX, microphone acceptance, natural Chinese voice quality, standalone packaging, and semantic memory search remain unverified or deferred.

## Offline synthesis backend (Stage 7F, developer baseline)

The optional `tts` extra adds pinned sherpa-onnx 1.13.8 and numpy. `LocalKokoroSynthesizer` accepts a verified absolute local Kokoro v1.1-zh bundle and produces owned 24kHz mono PCM16; callers must clear the returned AudioChunk. That backend alone does not play sound; Stage 7G adds explicit opt-in UI/device playback separately. The source-runtime helper receives text through stdin, suppresses native stderr, and is terminated on cancellation/timeout. No runtime model downloads occur.

Inputs are limited to 200 normalized characters; output to 60 seconds. Model provenance, a fixed public Chinese synthesis smoke and redistribution limitations are recorded in [offline TTS evidence](docs/offline-tts-assets-2026-10-20.md). Models are ignored developer assets. Default-headphone playback, natural completion and explicit stopping were exercised on Windows. The user heard the output but found its prosody/timbre stiff; natural voice quality is not accepted. Compiled-app helper integration remains unverified.

## Explicit offline reply playback (Stage 7G)

From the source checkout, opt in independently of microphone recognition:

```powershell
python -m pip install -e ".[voice,tts]"
$env:PYTHONPATH = (Resolve-Path src).Path
$env:AI_COMPANION_TTS_MODEL_DIR = (Resolve-Path .models/kokoro-int8-v1_1).Path
python -m companion.desktop.app
```

Acquire and verify the trusted local bundle separately using the provenance in [TTS evidence](docs/offline-tts-assets-2026-10-20.md); the app never downloads it. With a saved assistant reply, click “朗读最新回复”. Replies longer than 200 normalized characters explicitly show “朗读前200字”; stored text stays unchanged. There is no autoplay. “取消语音” stops pending synthesis/playback; hiding chat also stops it. PTT stops output before microphone permission/capture; a failed stop blocks recording.

Only exact 24kHz mono PCM16 output devices are supported. Missing/unsupported devices fail safely; no resampling fallback. Physical speaker quality, actual interruption/echo, accessibility and microphone UX need Windows user acceptance. The helper requires a Python source runtime: compiled/frozen applications explicitly disable this TTS route before probing optional modules/devices, and direct helper calls fail before spawning a process. A compiled desktop executable is never treated as a Python `-m` interpreter. Packaged playback and redistribution remain separate release gates. Default-off startup does not load models, prompt for permissions or enumerate devices.
