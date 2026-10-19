# Stage 7E: explicit recording and background transcription

## Intent and authorization

Connect Stage 7D capture to Stage 7C offline STT in the compact companion chat. The user authorized autonomous spec/plan/review/implementation; normal human checkpoints are waived. Preserve deterministic reminders and local privacy. This is architectural work because synchronous VoiceSession currently combines thread-affine capture.stop and blocking STT.

## Approach

Split VoiceSession into capture release and a single-use transcription job. Keep stop_capture as a synchronous compatibility wrapper. Alternatives are a second voice coordinator (duplicate lifecycle) or cross-thread blocking Qt calls (deadlock/lifetime risk); neither is selected.

No new dashboard, persistence migration, voice engine, TTS, resampler, global hotkey or automatic command execution. Chinese base-model quality remains unapproved. No real microphone or private audio in automated development.

## Application boundary

`VoiceSession.prepare_transcription()` executes capture.stop on its caller thread and returns a single-use `TranscriptionJob` or None on safe failure. Its run method performs only STT/validation/status work; it never calls capture/Qt. Existing stop_capture delegates prepare then run synchronously. The Qt-free session continues to reject overlapping operations and non-local providers.

The job owns the transferred AudioChunk. Success, failure or cancellation clears owned bytes. Cancelling a not-yet-running job clears immediately and releases session reservation; queued execution then returns None. Cancelling an executing job sets the token and suppresses late results, retaining the buffer until native work exits to avoid mutation races. Native operations remain cooperatively cancellable. Completion callbacks only release the job's own reservation and cannot reset a newer operation. Close cancels pending/running jobs and disables the session.

## Desktop controller

`VoiceController` is a small QObject: injected VoiceSession, capture source, permission requester, preflight and optional thread pool. It owns UI operation IDs, permission generations and worker references. All recording/permission/cancel actions run on its Qt thread. ChatWorker executes the job through QThreadPool; a QObject Slot receives results on the UI thread. No raw worker errors reach logs or widgets.

Press starts a permission request after model preflight, never before user action. Permission denial produces a safe message. Release while permission is pending invalidates that request; a later grant cannot start recording. Duplicate permission callbacks are ignored. Granted permission while still held starts capture. Release while listening releases the device on the UI thread, then submits STT. At the adapter's limit, stop/transcribe occurs once even if the button is still held; a later release is ignored. Capture failures cancel/discard, with no automatic retry.

State is idle / permission / listening / transcribing / cancelling / error / unavailable. A separate Cancel voice action cancels permission, recording or STT. During a cancelled running worker, new capture stays blocked until the old worker exits; the UI explains the wait. Pending worker launch failure cleans up the unrun job. Late results after cancellation, close/hide or shutdown are discarded. No callback retries recording automatically.

ChatWindow receives an optional controller and keeps voice widgets small: existing press-to-talk, separate cancel, safe recording status, disabled future Speak. Listening/permission preserve button release handling; blocking STT never runs on the UI thread. Typing remains usable; transcript handoff fills only an empty editable composer, never overwrites a draft, never sends or saves. Hiding/closing chat cancels voice, and reopening permits a new explicit action. Application quit closes the controller.

## Opt-in configuration

First developer activation uses `AI_COMPANION_STT_MODEL_DIR`, an explicit absolute local multilingual Whisper model directory. Without it, recording stays disabled. Missing voice/stt optional modules disable recording with an explanatory reason; checking module availability must not import Qt Multimedia or enumerate devices. A lazy LocalWhisperSTT model preflight on press verifies local directory metadata before permission/capture; it never loads weights or downloads files. Invalid/network paths fail before microphone access.

This reversible environment setting avoids adding premature database/settings UI. Cost: the setting must be supplied at launch and no model chooser exists. Install optional dependencies separately; no app-time installation/download. Stage 7D's existing exact PCM/device requirements remain. This slice may provide opt-in wiring without claiming native/device acceptance if optional installation remains unavailable.

## Privacy/failures

No audio files, microphone identifiers, transcripts or voice state in repositories, provider context or telemetry. Only explicit Send moves a draft into existing chat persistence/disclosure. Raw filesystem/device/provider exceptions are sanitized. Permission API is used only after a press; callback context is the controller QObject to bind lifetime. Resource release stays on the UI thread. No system-time queries in core logic.

## Tests and acceptance

Fake ports prove split caller/worker thread boundaries, pending/running cancellation, duplicate job execution, cleanup, no overlap and unchanged synchronous/TTS behavior. Fake permission/capture/pool tests prove delayed grant after release/cancel, duplicate grants, async limit/failure, launch failure, typed errors and stale worker suppression. A real QThreadPool test with fake STT checks thread separation and event-loop responsiveness. Qt chat tests prove controls/status/empty-draft handoff/hide cleanup and no send. Composition tests verify default-off, module preflight and environment opt-in without hardware. Run all old/new tests, compileall, pip check and diff review; one independent final review and RED/GREEN fixes precede commit.

Real Windows permission/device support, microphone interruptions, Chinese accuracy, accessibility/press-release ergonomics, TTS and executable packaging require manual/future acceptance. No real-device pass is inferred from fakes.

Self-review: captured PCM changes ownership once; Qt capture never crosses into workers; cancellation never clears actively consumed PCM; existing core and privacy boundaries remain. No unresolved owner choice is needed.

Reference: [Qt permission request](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QCoreApplication.html#PySide6.QtCore.QCoreApplication.requestPermission); installed 6.11.2 signature requires permission, context QObject, functor.
