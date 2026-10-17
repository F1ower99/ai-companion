# Stage 7A Voice Session Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-only, provider-neutral voice lifecycle with bounded transient audio, cancellation, and explicit transcript handoff.

**Architecture:** Domain values and ports isolate capture and local STT/TTS. A synchronous Qt-free application coordinator uses operation generations and cancellation tokens to discard late results. Real adapters remain deferred; the chat exposes disabled controls and a tested draft handoff.

**Tech Stack:** Python 3.10+, existing CancellationFlag, PySide6 Essentials 6.11.2, pytest/pytest-qt; no additional runtime dependency.

**Spec:** `docs/superpowers/specs/2026-10-16-stage-7-local-voice-and-packaging-design.md`

## Global Constraints

- No real microphone, speaker, speech engine, network audio, SQLite voice state, or system-clock calls.
- Providers must declare `local_only is True`; audio is at most 60 seconds of PCM in mutable process memory.
- Transcripts contain 1–8,000 characters after trimming and enter an editable composer without sending.
- Missing providers disable voice at startup without device queries or permission prompts.
- Capturing adapters must enforce the 60-second limit and permission gate on explicit start; no adapter ships in this slice.
- Existing task/reminder/chat consent behavior and SQLite migrations remain unchanged.

## Review Focus

- Cancellation during provider execution must discard late transcripts and clear audio (Task 2).
- Stop/cancel/start failures must release capture and expose only safe error codes (Task 2).
- Invalid PCM metadata, partial frames, oversized audio, and blank/oversized transcripts must be rejected (Task 1).
- Remote/malformed provider declarations must be rejected before any operation (Task 2).
- UI transcript handoff must preserve an existing typed draft and never trigger Send (Task 3).

---

### Task 1: Bounded Voice Values and Ports

**Files:** Create `src/companion/domain/voice.py`, `src/companion/ports/voice.py`; test `tests/domain/test_voice.py`.

**Interfaces:** `VoiceState`, `VoiceErrorCode`, safe `VoiceOperationError(code)`, `VoiceStatus(state, error_code=None)`, `AudioChunk(pcm: bytearray, sample_rate_hz: int, channels: int, sample_width_bytes: int)` with derived `duration_seconds` and `clear()`, `VoiceTranscript(text: str)`. Ports: capture `start()->None`, `stop()->AudioChunk`, `cancel()->None`; STT `local_only: bool`, `transcribe(audio, cancellation_token)->VoiceTranscript`; TTS `local_only: bool`, `speak(text, cancellation_token)->None`, `stop()->None`. Capture start owns permission gating and bounded buffering.

- [ ] Write validation tests for PCM ownership/type, positive format values, complete frames, exactly 60 seconds, >60 seconds, cleared data, redacted repr, and transcript boundaries.
- [ ] Run `python -m pytest tests/domain/test_voice.py -q`; verify missing voice model is the failure.
- [ ] Implement the values/ports; use existing `ValidationError`; never include audio/transcript in repr or errors.
- [ ] Run the focused tests and full suite with `QT_QPA_PLATFORM=offscreen`; inspect results.

### Task 2: Local Voice Session Coordinator

**Files:** Create `src/companion/application/voice_session.py`; test `tests/application/test_voice_session.py`.

**Consumes:** Task 1 ports/values and existing `CancellationFlag`.
**Produces:** `VoiceSession(capture=None, stt=None, tts=None)`, read-only `status`, `can_capture`, `can_speak`; `start_push_to_talk()->VoiceStatus`, `stop_capture()->VoiceTranscript|None`, `cancel_capture()->VoiceStatus`, `speak(text: str)->VoiceStatus`, `interrupt_output()->VoiceStatus`, `close()->None`. `stop_capture` and `speak` are blocking and future callers must schedule them off the Qt thread. Generation checks prevent cancelled/replaced operations publishing results. State access is protected with a lock; provider work occurs outside it.

- [ ] Write fake-port tests for unavailable no-op; local-only enforcement; start/stop/transcript; cancel without STT; chunk clearing after success/error/cancel; safe permission/capture/STT failures; reentrant cancellation and replacement rejecting late results; explicit TTS and PTT interruption; invalid operation ordering; close cleanup.
- [ ] Run `python -m pytest tests/application/test_voice_session.py -q` and verify failure before implementation.
- [ ] Implement the coordinator. Cancel marks the token before adapter cleanup; cleanup errors never mask the safe primary failure. Starting while transcription/capture is active returns a safe busy state; cancelled old work never overwrites a newer status. No transcript/audio is retained by the service after return.
- [ ] Run focused tests and the full suite; inspect audio cleanup and absence of storage/network imports.

### Task 3: Disabled Voice Controls and Explicit Draft Handoff

**Files:** Modify `src/companion/desktop/chat_window.py`; test `tests/desktop/test_chat_window.py`; update README, roadmap, and `docs/superpowers/tasks/2026-10-17-stage-7a-voice-session.md`.

**Consumes:** `VoiceTranscript` from Task 1. **Produces:** disabled `push_to_talk_button` and `speak_reply_button` with missing-local-provider explanations; `accept_voice_transcript(transcript)->bool` puts text in an empty composer, refuses to overwrite a non-empty draft, and never sends or persists it. Keep the existing single-pane transcript; the compact speech action targets the latest reply when a future provider is composed.

- [ ] Write Qt tests for disabled controls, editable transcript handoff, preservation of typed drafts, and zero chat writes/provider calls before explicit Send.
- [ ] Run the focused Qt tests and verify the new attributes/handoff are missing.
- [ ] Add disabled controls and draft handoff. Do not enable a fake or stub provider in runtime composition. Document what is implemented versus deferred.
- [ ] Run full pytest, compileall, pip check, and `git diff --check`; inspect diff and secrets/temp artifacts.
- [ ] Commit all Stage 7A feature/test changes as an independent stage commit, then record actual results in its task record.

## Completion Review

Self-review: all provider/model/audio-adapter selection remains in OPEN_QUESTIONS; actual permission/time-limit enforcement is an adapter obligation, tested here only through its contract. No live-voice acceptance is claimed. Request a fresh whole-stage reviewer after implementation; resolve important findings with RED→GREEN tests and run full regression before the documentation commit.
