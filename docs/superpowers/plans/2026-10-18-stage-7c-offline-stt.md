# Stage 7C Offline STT Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recognize bounded PCM using an explicitly supplied local Whisper model on CPU without inference downloads.

**Architecture:** An optional lazy infrastructure adapter implements Stage 7A's STT port. Strict local model/audio checks precede imports and native calls; the adapter serializes calls and clears owned float audio. A separate bounded WAV CLI makes real public-fixture verification reproducible.

**Tech Stack:** Python 3.10+, faster-whisper 1.2.1 optional extra, numpy via that extra, pytest; current Qt shell unchanged.

**Spec:** `docs/superpowers/specs/2026-10-18-stage-7c-offline-stt-design.md`

## Global Constraints

- Only existing complete absolute local model directories, <=1 GiB required files; no runtime downloads or model identifiers.
- Only <=60-second 16kHz mono PCM16 input; output <=8,000 chars and <=256 segments.
- Lazy CPU/int8 initialization, 1–8 threads, local_files_only True; no microphone/Qt/SQLite dependency.
- Waveform cleared in finally; original PCM owned by VoiceSession; no raw logs or automatic transcript printing.
- Cancellation cooperative; no promise to interrupt native calls immediately.

## Review Focus

- Missing tokenizer must fail before upstream's potential network fallback (Task 1).
- Cancelled/incomplete lazy output must never produce a transcript (Task 1).
- Mutable waveform copies must be cleared even on generator failure (Task 1).
- WAV headers must be bounded before reading payload; truncated files rejected (Task 2).
- Runtime extras/models must remain optional and absent from normal startup (Task 3).

---

### Task 1: Local Model STT Adapter

**Files:** Create `src/companion/infrastructure/local_whisper.py`, `tests/infrastructure/test_local_whisper.py`; modify optional dependencies in `pyproject.toml`.

**Interfaces:** `LocalWhisperSTT(model_directory: Path, language: str='zh', cpu_threads: int=4, model_factory=None)` with `local_only=True`, `.transcribe(audio: AudioChunk, cancellation_token: CancellationToken)->VoiceTranscript`. Factory receives complete local path and CPU/int8/local-only options, returns the pinned WhisperModel API. PCM conversion is inside the adapter; factory injection only replaces the slow/native boundary, not model validation or output processing.

- [ ] Write failing tests for complete local paths, missing files/URLs/relative paths, PCM format validation/normalization, safe import/backend errors, output/segment limits, silence, cancellation before/after load/during iteration, overlap rejection and waveform cleanup.
- [ ] Run tests and confirm missing adapter failure; implement minimal adapter and optional stt extra.
- [ ] Run focused tests and full suite; inspect network/log/persistence boundaries.

### Task 2: Bounded Public-Fixture Smoke CLI

**Files:** Create `scripts/smoke_local_stt.py`, `tests/tooling/test_smoke_local_stt.py`.

**Interfaces:** `read_pcm_wav(path: Path)->AudioChunk`; `main(argv=None, provider_factory=LocalWhisperSTT)->int`. WAV validates uncompressed 16k/mono/2-byte frames and 1–960,000 frames before reading; actual byte length must match header. Default stdout reports only status/duration/character count; `--show-transcript` explicit. Always clear returned AudioChunk after inference.

- [ ] Write failing generated-WAV tests for valid PCM, oversized header, truncated payload, wrong format, safe errors, no default transcript leak and clearing on provider errors.
- [ ] Run tests, implement CLI, run focused/full tests.

### Task 3: Runtime Verification, Documentation and Stage Commit

**Files:** README, roadmap, `.gitignore`, `docs/superpowers/tasks/2026-10-18-stage-7c-offline-stt.md`, optional model-license record.

- [ ] Install optional runtime in existing project venv if network access is available; download only explicitly selected public model/sample assets to ignored local directories; record source revision and hashes.
- [ ] Run actual CPU inference with Python network calls blocked; report exact sample/language/time and limitations. No microphone/private audio.
- [ ] Run full tests/compileall/pip check/diff scans; fresh independent code review; fix important findings with RED→GREEN and full regression.
- [ ] Document local model setup, memory/CPU/cancellation limitations and still-disabled microphone/TTS controls; commit stage separately and preserve branch.

## Self-review

Inputs/outputs match existing STTProvider and VoiceTranscript. Model acquisition stays separate from app runtime. No hidden TTS implementation or UI consent change. All Review Focus items have tests in their owning task; native inference/quality is separately reported, never inferred from fake tests. Existing autonomous approval supplies execution method and normal checkpoint authorization.
