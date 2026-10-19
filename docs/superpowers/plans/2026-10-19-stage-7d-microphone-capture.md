# Stage 7D microphone capture implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Implement an optional, bounded, thread-affine microphone capture adapter without activating hardware.

**Architecture:** Qt-only adapter and lazy Qt Multimedia backend. Main-thread lifecycle; injected fake backend; no application-service or UI composition changes.

**Tech Stack:** Python 3.10+, existing Qt Essentials/Addons 6.11.2, pytest-qt.

**Spec:** `docs/superpowers/specs/2026-10-19-stage-7d-microphone-capture-design.md`

## Global constraints

- PCM16 mono 16 kHz; 1,920,000 bytes and 60,000 ms limits; request 3,200-byte native buffer.
- No hardware in tests, no recording on startup, no persistence/network/LLM, no raw exceptions or device identifiers.
- Default input only; reject unsupported exact format; permission must already be granted.
- Source lifecycle on owner Qt thread; no worker integration this slice.

## Review focus

1. A late backend signal must not stop a newer recording: generation test.
2. A device that emits no data still releases at deadline: timer test.
3. Teardown failure must not publish PCM: stop-exception test.
4. Missing permission must not enumerate hardware: default-backend test.
5. Completed-but-unclaimed PCM must prevent overwrite: busy test.

## Task 1: bounded adapter

- [x] Add failing tests in `tests/infrastructure/test_qt_microphone.py` for fake-backend transfer/limits/error/cancel/thread behavior. Observe RED.
- [x] Implement `src/companion/infrastructure/qt_microphone.py` with lazy backend factory, owner-thread checks, generation lifecycle, bounded PCM and timer, safe errors. Observe GREEN.

## Task 2: actual backend and evidence

- [x] Add failing fake Qt Multimedia boundary tests in the same test file for permission, device, format, start, reads and stop. Observe RED.
- [x] Implement lazy `QtAudioInput` backend; inspect local official 6.11.2 type signatures without device discovery. Observe GREEN. Native import/runtime validation deferred: optional download did not finish; ruling in execution record.
- [x] Run full regression, compileall, pip check and inspect diff/secrets; obtain one independent fresh review; Important/Critical fixes get one RED/GREEN pass, Minors recorded.
- [x] Update Stage 7/overnight reports, README and execution ledger with actual limits/tests/remaining integration. Commit stage independently; keep branch, no merge or force push.
