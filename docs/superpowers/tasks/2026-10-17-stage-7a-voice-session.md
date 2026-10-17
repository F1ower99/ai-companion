# Stage 7A execution record

Plan: `docs/superpowers/plans/2026-10-17-stage-7a-voice-session.md`

Base: `76878f1`.

Pre-flight: Task 1's voice values/ports agree with Task 2 and Task 3's consumers.

Ruling: keep this tracked execution record instead of the skill's scratch ledger. The existing `.superpowers/sdd` directory rejects writes in this environment; no permission expansion is needed for implementation. Cost: manual progress recording.

Task 1: complete; 15 initial domain tests passed, full suite 385 passed.

Task 2: complete; fake-provider lifecycle and cleanup verified, full suite 407 passed.

Task 3: complete; disabled controls and draft-only handoff verified. Additional author regression tests fixed memoryview cleanup, recovery after TTS error, and capture cleanup overlap. Full suite 413 passed. Feature commit: `8cc74fa`.

Fresh independent reviewer found two Important concurrency issues: premature speech ownership release and a gap before reserving capture. Both reproduced with failing tests, then fixed in one pass. Speech worker/cleanup ownership is now retained separately; capture reserves its transition before stopping playback; old cancelled failures cannot stop replacements or overwrite current capture state. Full suite after fixes: 423 passed (includes eight concurrent Stage 7B tooling tests). No Critical or Minor findings.

Ruling: serialize replacement speech until the interrupted worker returns, while permitting capture after successful TTS stop. This prevents an old worker's cleanup reaching newer playback. Cost: an uncooperative provider can delay another speech request; real provider integration still needs device testing.

Ruling: expose synchronous status rather than a state-observer callback, and retain the existing transcript pane with a disabled latest-reply speech action. Current runtime has no voice provider. Cost: real audio integration will need worker/status wiring and may add per-reply UI actions.

Reviewer-set-aside rulings: real microphone permission, automatic 60-second stopping/device release/recognition quality and live Qt recording/playback are explicitly deferred with the engine/adapters; shipping them requires local engine choice and human hardware acceptance. Packaging is reviewed separately under Stage 7B. Cost: Stage 7A is a tested foundation, not usable end-to-end voice.

Privacy: no hardware calls, voice persistence, network audio, new runtime dependency, or schema changes. All provider tests use fakes. Build tooling tests use temporary trees. No push or merge.
