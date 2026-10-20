# Stage 7F local synthesis implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline, task by task.

**Goal:** Produce bounded offline Chinese PCM safely, without hardware playback or text leakage to logs.

**Architecture:** Qt-free synthesizer port and lazy parent adapter; a muted, short-lived native worker exchanges stdin JSON / stdout binary PCM. Existing UI/core voice contracts remain intact.

**Tech Stack:** Python 3.10+, optional sherpa-onnx/core 1.13.8, numpy, Kokoro int8 v1.1-zh.

**Spec:** `docs/superpowers/specs/2026-10-20-stage-7f-local-synthesis-design.md`

## Global constraints

- 200 text characters; 24kHz mono PCM16; max 60 seconds / 2,880,000 bytes; max bundle 256MiB / 1,000 files; 90s process timeout.
- Default voice 3, CPU threads2; validated voice0–102 / threads1–8; local absolute models only; no app-time downloads.
- No Qt/devices/network/SQLite/LLM in synthesis; no raw child output, text command arguments, recordings or private data tests.

## Review focus

1. Native failure logs contain text: stderr discarded and malformed stdout never surfaced.
2. Cancel after valid output but before publication: clear/discard rather than return audio.
3. Process timeout/cancel: kill and reap, no orphan helper or partial publication.
4. Model auxiliaries point outside root or have excessive tree size: reject before native loading.
5. Sample output invalid/too long: no truncated utterance, buffer cleanup on error.

## Tasks

- [ ] Task 1 RED: parent adapter/path/protocol/runner tests in `tests/infrastructure/test_local_kokoro.py`; observe failure. Implement `local_kokoro.py`, bounded model validation and `tts_process.py`; add SpeechSynthesizer port. GREEN including fake Popen cancellation/timeout.
- [ ] Task 2 RED: fake-native waveform/config/input/protocol tests in `tests/infrastructure/test_tts_worker.py`; observe failure. Implement `tts_worker.py`, lazy native imports and safe stdout protocol. GREEN; add optional tts extra, explicitly install and inspect pinned bindings.
- [ ] Task 3: verify/acquire ignored public model bundle, run public in-memory Chinese synthesis without network/device calls, record actual results and license provenance. Full regression, compileall, pip check; one independent review and Important/Critical RED/GREEN fix pass.
- [ ] Update README, Stage7/overnight reports and execution record; inspect staged diff/secrets; commit stage independently on existing branch. No merge, force push or release.
