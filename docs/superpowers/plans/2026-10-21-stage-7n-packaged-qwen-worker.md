# Stage 7N packaged Qwen worker implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Inline execution follows the standing autonomous user instruction.

**Goal:** Explicit Qwen synthesis works with a compiled desktop while preserving isolation and default-off behavior.
**Architecture:** Deterministic allowlisted first-party ZIP, hash embedded into staged compiled code, fixed adjacent resolver, existing external Python transport.
**Tech Stack:** Python3.10+, stdlib ZIP/hash/path utilities, pinned Qt6.11.2/Nuitka4.1.1, existing Qwen runtime.
**Spec:** docs/superpowers/specs/2026-10-21-stage-7n-packaged-qwen-worker-design.md

## Global constraints
- No audio autoplay, microphone, private data, new model/runtime download, cloud/provider access or source/output deletion.
- Core decision scheduling unchanged; source behavior and compiled Kokoro guard retained.
- Bundle contains only required first-party source; external runtime/model remain explicit and local.

## Review focus
- Compiled source paths are not importable by external Python: use only verified adjacent ZIP.
- Tampering/missing/linked ancestor/network bundle fails before launching a child.
- Packaging output names and locations must match the real Qt/Nuitka build.
- Cancellation and malformed bounded PCM preserve existing cleanup.
- Missing optional Multimedia must remain unavailable without probing hardware.

## Task 1: Hash-bound bundle and integration
- [x] Add failing fixture/resolver/transport/UI tests and observe RED.
- [x] Implement minimal bundle builder, staged digest and runtime resolver; preserve existing interfaces.
- [x] Run focused tests, review code, fix, full regression.

## Task 2: Real compiled evidence and integration
- [x] Explicitly install pinned voice extra only in E build environment if required.
- [x] Build and verify public no-playback compiled synthesis/cancellation, then app default clean-profile smoke.
- [x] Independent review, fix, full regression, inspect secret/artifact diff and documentation.
- [x] Commit/push under standing authorization: f02369d, remote main readback matched.
