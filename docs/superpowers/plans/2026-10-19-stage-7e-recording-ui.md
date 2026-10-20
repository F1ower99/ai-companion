# Stage 7E recording UI implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline, task by task.

**Goal:** Explicit opt-in press-to-talk creates editable drafts through a thread-safe capture/STT boundary.

**Architecture:** VoiceSession prepares a single-use Qt-free transcription job on the capture thread; VoiceController requests permission, owns generations and dispatches that job through ChatWorker/QThreadPool. ChatWindow displays state and accepts drafts; app composition is opt-in.

**Tech Stack:** Python 3.10+, existing PySide6 6.11.2, optional local faster-whisper, pytest-qt. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-19-stage-7e-recording-ui-design.md`

## Global constraints

- Preserve 16kHz mono PCM16 / 60 second capture cap and local-only models/providers.
- No hardware tests, audio files, cloud audio, auto send, schema changes or automatic downloads.
- Capture lifecycle on Qt thread; worker code STT only; time remains injected in deterministic core.
- Default off; explicit `AI_COMPANION_STT_MODEL_DIR`; optional modules checked lazily without loading hardware.

## Review focus

1. Permission arrives after release/close: no capture.
2. Pending job cancelled before pool runs: immediate PCM cleanup and no later STT.
3. Cancelled running decode returns late: no draft/new-operation state mutation.
4. User types while decoding: preserve their draft and no auto-send.
5. Pool submission fails or capture reaches limit during start: release device/PCM once without blocking Qt.

## Task 1: split application operation

- [x] Add failing tests to `tests/application/test_voice_session.py` for prepare/run, thread identity, single execution, pending/running cancellation, close and failure cleanup; observe RED.
- [x] Add `src/companion/application/voice_transcription.py`; modify VoiceSession to expose prepare_transcription and retain synchronous wrapper; observe GREEN with all existing voice tests.

## Task 2: desktop controller

- [x] Add `tests/desktop/test_voice_controller.py` failing fake permission/capture/pool and actual QThreadPool tests for the lifecycle/review-focus cases; observe RED.
- [x] Implement `src/companion/desktop/voice_controller.py`, including Qt microphone permission requester, safe states/errors, worker dispatch and close/cancel; observe GREEN.

## Task 3: opt-in composition and UI

- [x] Add failing Qt integration/composition/model-preflight tests in `tests/desktop/test_chat_window.py`, new `tests/desktop/test_voice_configuration.py` and existing STT tests; observe RED.
- [x] Implement lazy local model preflight in LocalWhisperSTT, environment/module checks in new `desktop/voice_configuration.py`, optional ChatWindow controls and app lifecycle composition. No recording during tests. Observe GREEN.
- [x] Full regression, compileall, pip check, staged diff/secret checks. Fresh independent review; one Critical/Important RED/GREEN fix pass, Minors recorded.
- [x] Update README, Stage 7/overnight report and execution ledger with actual evidence/limitations. Commit stage, preserve branch; no main merge/force push.
