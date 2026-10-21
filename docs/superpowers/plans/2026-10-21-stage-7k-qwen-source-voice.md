# Stage 7K implementation plan

Implement inline in the existing isolated worktree, following the approved autonomous spec workflow.

1. Asset/runtime policy and adapter: add public pinned manifest metadata, `infrastructure/qwen_assets.py` and `local_qwen.py`. Write failing small-fixture tests for local path/shape/hash integrity and adapter text/cancellation/protocol ownership; implement lazy fast preflight and child-side full verification. No real model dependency in tests.
2. Owned helper: preserve `run_tts_worker` public semantics while extracting its bounded transport for the fixed external Qwen command. Add `qwen_tts_worker.py`, offline/cache configuration, native-output muting, guarded local BF16 inference and PCM conversion. RED tests for command/environment/deadline, worker loader/network/output/cleanup; implement with fake backend/runtime and fake processes. Run existing Kokoro/worker tests alongside new cases.
3. Explicit composition: add validated engine selection in `voice_configuration.py` with no default change, parent native model imports or fallback. Add RED config tests, implement selection, document E-drive invocation and experimental latency/quality boundary. Run controller and clear-conversation privacy tests.
4. Validate/review: run the complete suite in real Windows offscreen mode, compileall, pip check and diff/secret checks. Run actual E-runtime public-text adapter synthesis and owned cancellation only; no playback/private text. Independently review, fix findings, rerun affected/full tests, commit Stage 7K and normally push/merge under renewed user authorization.

Each implementation task follows RED → GREEN and updates an execution record with exact evidence. No actual model/runtime binaries enter Git. If a substantive integration assumption fails, retain the stable default and record that failure rather than silently relaxing privacy or local-path guards.
