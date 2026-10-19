# Stage 7D: bounded local microphone capture

## Intent and scope

Continue Stage 7's offline voice path with a real, independently testable Qt capture adapter. The user authorized autonomous spec, plan, implementation and review; ordinary approval checkpoints are waived. Existing stages and deterministic reminders remain unchanged.

This slice implements capture only. No production UI enables recording yet. No microphone is accessed during development or automated tests. The following slice must connect explicit permission interaction, visible recording state and worker transcription before claiming interactive voice works. Chinese base-model output has a known substantive sample error; retain editable draft confirmation and do not dispatch commands from STT output.

## Options and decision

Use Qt Multimedia's pull-mode QAudioSource with a bounded application buffer. A push-mode QIODevice introduces callback-thread coordination; a new native audio dependency adds another runtime. Neither is necessary here. Use the existing optional PySide6-Addons 6.11.2 dependency, imported only on start. The base app remains usable without it.

## Contracts

`QtMicrophoneCapture` is a QObject implementing AudioCaptureSource's start/stop/cancel. All lifecycle calls run on its owning Qt thread. It emits `captureFinished()` when a duration/data limit has released the device and PCM can be retrieved using stop, and `captureFailed(code)` after asynchronous cleanup. Construction, imports, cancellation before start, and tests never enumerate devices.

Start is an explicit caller action. The default backend checks QMicrophonePermission and refuses denied or undetermined permission before device discovery; it does not request permission itself. The later controller requests permission following the user's action, then calls start only if granted. Windows OS privacy errors can still surface as safe capture failures. Device descriptions/IDs and raw exceptions are never exposed or persisted.

Only the default input device and exactly 16,000 Hz, mono, signed PCM16 are supported. Unsupported format, missing device or missing optional dependency fails safely. No silent format substitution/resampling in this slice. This deliberately bounds scope; real-device format compatibility is a manual acceptance item.

Start reserves one recording; another start while recording or while completed PCM is awaiting stop fails BUSY. Successful stop releases the device first and transfers a validated AudioChunk; cancel releases the device and clears owned bytes. Stop without data, incomplete final frames or capture errors fails safely and clears buffers. Repeated cancel is safe; a subsequent explicit start may retry. No automatic retry loop.

The application PCM bytearray is capped at 1,920,000 bytes (60 seconds). A single-shot 60,000 ms Qt timer also ends capture even if the device produces no bytes. Pull reads are bounded and stop at the cap; completed capture cannot grow further. Native audio buffers are requested at 3,200 bytes, with no claim about OS internal allocation or memory zeroization. Owned mutable bytes are cleared on cancel/failure; successful transfer makes the caller responsible for clearing. Internal/immutable native copies cannot be guaranteed zeroized.

Queued ready/failure callbacks from a previous recording are ignored using a generation number. Stop/cancel/error teardown disconnects by retiring the backend, stops the timer, closes the stream and schedules QObject deletion. Cleanup failures yield safe capture errors and no transcript; retained mutable audio is cleared.

## Architecture boundary

The Qt adapter is infrastructure, with no SQLite, LLM, chat or decision dependency. An injectable backend factory allows tests to simulate permission, device formats, reads, errors and release without loading Qt Multimedia. The real backend exclusively owns QAudioSource and QIODevice. Lifecycle is thread-affine: **do not call VoiceSession.stop_capture on a worker with this adapter**, since it currently invokes capture.stop there. The next integration design must split main-thread capture release from worker STT; this slice does not alter the already-tested synchronous VoiceSession contract.

## Verification and acceptance

Tests cover lazy construction, bounded transfer, exact byte/duration limits, timer finish, permission/start/read/stop errors, empty and odd PCM, cancellation zeroing, repeated cancel, busy/retry, stale callbacks and wrong-thread rejection. Fake Qt Multimedia tests cover default backend permission-before-discovery, exact format rejection, start failures and stream teardown. Full old/new regression, compileall, pip check, diff/secret review and fresh independent review precede the stage commit.

No real capture/permission UX, device compatibility, Chinese accuracy, transcription UI, TTS or packaged microphone acceptance is claimed. No schema or persistence changes, audio files, background listening, global shortcuts, cloud audio, device logs or automatic startup recording.

References: [QAudioSource](https://doc.qt.io/qtforpython-6/PySide6/QtMultimedia/QAudioSource.html), [QMicrophonePermission](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QMicrophonePermission.html). API bindings must be checked against the installed 6.11.2 optional wheel before user activation.

Self-review: the adapter-only boundary keeps Qt thread affinity explicit; no working UI or real-device acceptance is implied. A future controller is required, so this is a Stage 7 sub-slice rather than completion of voice support.
