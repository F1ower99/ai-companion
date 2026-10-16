# Stage 7A Design Spec: Local Voice Session Foundation and Windows Packaging

Date: 2026-10-16
Status: Approved for autonomous Stage 7A work under the user's overnight-development authorization

## Purpose

Stage 7 starts the voice and Windows release work already listed in the roadmap. This first slice establishes a testable voice-session boundary and a repeatable Windows standalone build without choosing or enabling a speech-recognition engine. It preserves the user's local-first privacy rule: microphone access requires an explicit user action, raw audio stays in memory, recognized text is not sent automatically, and the app will not upload audio to a cloud service.

The local STT engine is a product choice with meaningful effects on language support, bundle size, quality, and Windows requirements. It is recorded in `OPEN_QUESTIONS.md`; the independently useful voice lifecycle and packaging work can proceed without choosing it.

## Goals

- Define a Qt-free, injectable `VoiceSession` state machine for push-to-talk, transcription, transcript handoff, explicit speech playback, cancellation, and interruption.
- Keep audio and transcript transient in the voice layer. A final transcript is placed in the chat composer for the user to inspect; only the existing Send action may send text to a configured chat provider.
- Require voice providers to declare local execution. The service rejects network-backed providers in this stage.
- Request microphone permission only after the user invokes push-to-talk. Denied permission, unavailable hardware, and provider errors return a safe visible state without crashing chat or reminders.
- Add a compact voice affordance to the existing companion chat, disabled with a clear explanation until a local STT provider is selected and composed.
- Add a reproducible Windows standalone deployment configuration and build guide using Qt for Python's deployment tool.
- Keep build and automated tests isolated from the user's real SQLite profile, credentials, and Windows startup settings.

## Non-goals

- No cloud STT/TTS, streaming audio, network speech provider, credential entry for voice, or audio upload.
- No STT/TTS engine implementation until the local engine question is resolved. The Stage 7A runtime must clearly report voice unavailable rather than pretend to transcribe.
- No automatic speech playback. The user must explicitly request playback for an assistant reply; pressing push-to-talk interrupts current playback.
- No audio files, voice transcripts, microphone identifiers, or voice activity history are persisted.
- No global hotkey, background microphone access, always-on listening, wake word, speech analytics, or automatic memory extraction.
- No automatic start-on-login or Windows Run registry changes in Stage 7A. These require a separate settings and uninstall design.
- No installer signing, store publication, auto-update, or final user-machine release certification.

## Existing architecture and constraints

- Stage 5's `ChatService` is synchronous, Qt-free, and runs through a `QThreadPool` worker. The chat composer sends only after the user presses Send.
- Stage 6's activity source is opt-in, disabled by default, and exposes no detailed application or input data.
- The app uses Python 3.10+, PySide6 Essentials 6.11.2, and SQLite migrations v1–v5. PySide6 Addons 6.11.2 is already an optional `voice` extra, intended for Qt Multimedia.
- Existing repository guidance and roadmap select `pyside6-deploy`/Nuitka for deployment and require a license inventory.
- Stage 7A must not change reminder decision rules, chat consent semantics, or the Stage 2/3/4/5/6 migration history.

## Approaches considered

1. **Cloud speech provider:** would produce an end-to-end voice demo quickly, but sends personal audio to a remote service and requires a provider choice and credential. It conflicts with the user's instruction not to upload private data, so it is excluded.
2. **Bundle a local speech model now:** preserves privacy but commits to a model/runtime, language profile, distribution size, and model licensing before the user has selected one. Defer until the local speech-engine question is answered.
3. **Provider-neutral local session plus Windows packaging:** creates the stable lifecycle and release baseline, exercises all session behavior with fakes, and leaves real microphone capture/transcription disabled until a local provider exists. This is the selected Stage 7A scope.

## Domain and application model

- `VoiceState`: `unavailable`, `idle`, `listening`, `transcribing`, `transcript_ready`, `speaking`, and `error`.
- `AudioChunk`: bounded, in-memory PCM data plus format metadata. It has no file path, serialization method, or repository representation. Python cannot guarantee physical memory zeroization; cleanup drops references and clears mutable capture buffers.
- `VoiceTranscript`: validated non-empty text returned by the injected local STT provider.
- `VoiceStatus`: current state and a safe user-facing error code; it contains no audio, provider secret, or raw exception text.
- `AudioCaptureSource`: start, stop-and-return-memory-chunk, and cancel/discard operations.
- `STTProvider`: `local_only is True`; transcribes an in-memory chunk with a cancellation token and returns a transcript.
- `TTSProvider`: `local_only is True`; speaks explicitly selected text, exposes `stop()`, and accepts cancellation.
- `VoiceSession`: Qt-free coordinator with injected capture/STT/TTS ports and a state observer. It owns one operation at a time and does not depend on ChatService, SQLite, Qt, or the system clock.

## Voice lifecycle

1. At startup, the app does not query microphone devices or request permission. Without a local STT provider, the voice control remains disabled and says that local speech recognition is not configured.
2. When configured, a user invokes push-to-talk. The adapter checks/request microphone permission in response to that action, interrupts any active TTS, and starts capture. No audio is sampled before permission is granted.
3. Stop ends capture and releases the device before transcription. Capture is capped at 60 seconds; reaching the cap stops the device and begins local transcription with a visible maximum-duration notice. The service drops audio references and clears mutable capture buffers after the local provider returns or fails.
4. A successful transcript moves to `transcript_ready` and is passed to the UI composer. It is never sent to ChatService automatically. The user may edit, discard, or press Send under Stage 5's existing disclosure flow.
5. Cancel discards buffered audio and any unsent transcript created by the active capture. Cancellation never invokes STT or ChatService.
6. Assistant speech starts only from an explicit per-reply Speak control. Starting push-to-talk calls `TTSProvider.stop()` immediately. A TTS error does not alter or delete the text reply.
7. Each operation returns to `idle` or `unavailable`; typed failures produce safe state codes and release microphone resources in `finally` cleanup.

## UI interaction

- Keep the character and compact chat window primary. Place a small push-to-talk control beside the composer and a small Speak action on assistant replies.
- Push-to-talk is visibly disabled when no local STT provider exists; Speak is independently disabled when no local TTS provider exists. Each disabled action explains which local capability is missing. No microphone permission is requested until an enabled push-to-talk action.
- While recording, show a clear `Listening` state and a Stop action. Cancellation is separate from stopping-and-transcribing.
- Show the resulting transcript in the normal composer, where it can be edited before sending.
- Never show a voice control as active when the microphone is denied, unavailable, or the provider failed.

## Privacy and persistence boundaries

- No microphone access until the explicit push-to-talk action and successful permission check.
- Capture buffers are bounded to 60 seconds and process-memory-only; cleanup drops references and clears mutable buffers on stop, cancel, provider failure, and application close. The implementation does not promise operating-system-level memory zeroization.
- Voice state, transcript text, microphone/device names, and audio content do not enter SQLite, logs, activity snapshots, provider contexts, or crash diagnostics.
- `local_only` is required by the voice application service. A future network provider requires a separate spec, explicit disclosure/consent, and a user-approved change to the no-cloud-audio boundary.
- Automated tests inject fake ports and never touch a real microphone or speaker.

## Windows packaging

- Use the existing Qt for Python deployment tool with an explicit standalone mode and `src/companion/desktop/app.py` as entry point; the output is a folder containing the executable and runtime dependencies.
- Keep release output under ignored `dist/`; keep Nuitka/build work in ignored build directories. Build scripts must not delete directories or touch `%LOCALAPPDATA%`, Credential Manager, or registry values.
- Add a PowerShell preflight that checks Windows, the project virtual environment, deployment tool, and Microsoft `dumpbin` availability before starting a build.
- Add a third-party license inventory with package name, version, declared license metadata, and license-file path when available. Missing metadata is called out for review; the inventory is not legal advice or a substitute for release review.
- Document launch from a clean temporary `LOCALAPPDATA` profile, database placement, credential behavior, and the requirement to test the extracted standalone directory before publishing an installer.
- The manual acceptance run must verify a clean-profile launch and basic desktop/chat/reminder behavior. It must not create a user's login-start entry.

The selected deploy tool wraps Nuitka and its default mode varies by Qt for Python version, so the project configuration explicitly pins `standalone`. The official documentation describes the deployment tool and its Windows `dumpbin` prerequisite: [Qt for Python: pyside6-deploy](https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-deploy.html). Qt Multimedia exposes the audio device/source/sink APIs, and microphone access uses Qt's permission API: [Qt for Python: Qt Multimedia](https://doc.qt.io/qtforpython-6.11/PySide6/QtMultimedia/index.html), [Qt for Python: QMicrophonePermission](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QMicrophonePermission.html).

## Failure handling

- Permission denied: remain usable; show a concise microphone-permission message and provide no automatic retry loop.
- No microphone or capture failure: reset/close the source, discard the buffer, return to `idle`, and preserve the existing text conversation.
- STT/TTS unavailable or failure: return a typed safe status; do not log raw audio, transcript, provider exceptions, or OS detail.
- Cancellation: stop capture/playback promptly, discard unsent session data, and make late worker results no-ops using an operation ID.
- Build preflight failure: stop before modifying output and name the missing tool; do not silently install compilers or system components.
- Packaged startup failure: retain the build artifact and diagnostics in the build output, not in the user's application data folder.

## Test strategy

- Domain/application tests with fake capture, local STT, TTS, and cancellation: permission denial path, start/stop, transcript not auto-sent, cancel discards audio, TTS stop on PTT, failed provider cleanup, bounded capture, and stale worker result rejection.
- Qt tests inject a fake `VoiceSession`; assert disabled controls request no permission, recording state is visible, transcript only fills the composer, and Send stays an explicit action.
- Packaging checks validate `pysidedeploy.spec`, preflight diagnostics, output ignore rules, and license inventory parser without running a destructive build in automated tests.
- Run the complete existing suite with `QT_QPA_PLATFORM=offscreen`, `compileall`, `pip check`, staged diff/secret checks, and a `pyside6-deploy --dry-run` when the build tool is available.
- A human Windows acceptance run is still required for microphone permission, a real local speech engine, packaged startup in a clean profile, and device interruption behavior. Stage 7A will not claim those manual tests passed.

## Acceptance criteria

- The Qt-free voice lifecycle can be fully tested with fake dependencies and has no Qt, SQLite, network, Windows API, or system-clock dependency.
- A completed fake transcription reaches the composer but makes no provider request or conversation write until Send is pressed.
- Pressing push-to-talk stops active speech; cancel discards data; all error paths release capture and leave chat/reminders usable.
- No local speech engine means the voice controls are disabled without microphone enumeration or permission prompts.
- The Windows build configuration selects the existing app entry point and standalone output; preflight is safe and docs explain clean-profile testing.
- Third-party package/license inventory and unresolved local STT engine choice are recorded.
- Existing Stage 1–6 tests remain green. Feature and documentation receive separate commits; no push, merge, or installer publication is part of Stage 7A.

## Deferred work

Selecting and implementing a local STT/TTS engine, real QAudioSource/QAudioSink wiring, user-led microphone testing, the Windows standalone build on the target toolchain, installer creation/signing, start-on-login setting, automatic memory, semantic search, cloud voice, and release publication are deferred beyond the autonomous Stage 7A implementation. The speech-engine choice remains in `OPEN_QUESTIONS.md`.
