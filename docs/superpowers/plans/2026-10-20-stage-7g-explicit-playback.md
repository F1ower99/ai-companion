# Stage 7G explicit playback implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline, task by task.

**Goal:** Explicitly play a bounded latest assistant reply using local synthesis, with stop and PTT interruption.

**Architecture:** Qt-free single-use result-owning synthesis job; separate Qt speech controller; lazy Qt audio output adapter; opt-in composition and compact chat controls.

**Tech Stack:** Existing Python/PySide6, optional QtMultimedia, Stage 7F SpeechSynthesizer.

**Spec:** docs/superpowers/specs/2026-10-20-stage-7g-explicit-playback-design.md

## Global constraints

200 normalized characters; explicit first-200 label for excerpts; 24kHz mono PCM16; 60-second audio bound. No autoplay, runtime downloads, files, cloud audio, SQL changes or real devices in tests. Exact output format only. Default off and no device discovery until explicit playback. Record acceptance limits honestly.

## Review focus

1. Cancel after synthesis before queued delivery must clear PCM rather than retain it in a Qt event.
2. Reentrant state notification must not let old generations start or stop new work.
3. PTT must stop output successfully before capture begins; late synthesis cannot play over recording.
4. Missing/unsupported/erroring device must clear ownership and preserve conversation/draft.
5. Latest failed/user message must not become speech; a long reply excerpt must be visible before clicking.

## Tasks

- [ ] Task 1: create application/voice_synthesis.py and tests/application/test_voice_synthesis.py. RED tests for single-use run/take, cancel pending/running/completed, failed provider and buffer cleanup. Implement minimal SynthesisJob with CancellationFlag, lock and transferred ownership; GREEN.
- [ ] Task 2: create infrastructure/qt_playback.py and tests/infrastructure/test_qt_playback.py. RED fake backend tests for lazy construction, exact format, no-device/error cleanup, natural completion, idempotent stop, wrong thread and stale callbacks. Implement injected Qt-thread adapter and lazy native QAudioSink backend; GREEN, no hardware.
- [ ] Task 3: create desktop/speech_controller.py and tests/desktop/test_speech_controller.py. RED tests for background job reservation, result taking, cancellation before queued delivery, hide/close, pool rejection, notifications reentry and safe errors. Use existing ChatWorker without PCM signal payload; GREEN.
- [ ] Task 4: add independent opt-in builder in desktop/voice_configuration.py; wire desktop/app.py and chat_window.py. Tests in tests/desktop/test_voice_configuration.py and test_chat_window.py prove default-off/no startup model or device access, latest sent assistant only, bounded excerpt label, no autoplay, stop/PTT order including stop failure and preservation of typed drafts. GREEN.
- [ ] Run full regression, compileall, pip check and diff inspection. One independent review; fix Important/Critical with RED/GREEN, rerun full suite. Document no real device/listening acceptance and packaged helper limitation; update Stage7/overnight reports and commit independently. No merge/force push/release.

## Execution status

Spec prepared under existing autonomous authorization. Implementation has not started; Stage 7F feature is committed separately. Do not infer playback readiness from the existence of this plan.
