# Stage 7F execution record

Base `eb1ccef`; existing isolated codex/stage3-proactive-engine worktree. Autonomous approval applies. No merge/push, real devices or private content.

Ruling: separate synthesis from device output; add SpeechSynthesizer rather than pretend the existing playback-oriented TTSProvider is implemented. Cost: Speak remains disabled until a distinct Qt playback/controller slice. This respects small complete roadmap increments.

Ruling: pinned native code can emit original text on tokenization failure despite debug=false. Use a short-lived worker with stderr DEVNULL, stdin JSON and checked binary stdout, no source text/path in command arguments and no GUI-wide logging mutation. Cost: per-request model reload and a future standalone-helper packaging design. Direct Python module launching is a source-runtime baseline, not a packaged-executable claim.

Task 1 RED: parent tests failed on missing adapter. GREEN: lazy validation, local/file/tree/delimiter limits, bounded PCM protocol, overlap, pre/post-worker cancellation, sanitized failures, fake Popen timeout/cancel kill/reap and argv/stderr privacy. Additional green policy coverage checks outside-root resolution and excessive stat size without writing huge files.

Task 2 RED: native-worker tests failed on missing module. GREEN: fake native config/CPU/thread/voice, waveform conversion, nonfinite/empty/oversize/shape rejection, callback duration stop, protocol-only output and PCM clear. Optional sherpa-onnx/core 1.13.8 installed from official PyPI, API signatures inspected without loading model/devices. numpy explicitly included in optional tts extra; base dependencies unchanged.

Focused synthesis tests: 50 passed. Fresh full regression on 2026-10-20: 582 passed in 10.04 seconds; compileall, pip check and diff check passed.

Full regression before review: 582 passed; compileall and pip check passed. Model retry succeeded with exact publisher hash; all 365 files verified. Actual muted-worker synthesis of a fixed public Chinese sentence produced 3.407 s / 24kHz mono PCM16 in 5.255 s, without files/devices, with Python network connects blocked in the worker. Exact provenance/limits are in docs/offline-tts-assets-2026-10-20.md. No intelligibility/quality claim.

Acquisition: pinned public bundle metadata selected 365 files / 194,382,580 bytes, verified 364 successfully. Initial model.int8.onnx response failed size/hash verification and was not saved/used; official resolve download=true retry subsequently matched the exact publisher SHA-256; acquisition is resolved. No credentials, mirrors or lowered verification.

Limits/costs: 200 normalized characters, 60-second returned PCM, 90-second helper lifetime; cancellation can terminate/reap helper. Native intermediate allocations, immutable text/pipe copies and OS memory zeroization are not guaranteed. Models are trusted developer assets, not arbitrary hostile ONNX extensions. eSpeak/phonemizer/dictionary notices and binary redistribution review remain separate from Apache model/runtime declarations.

Review status: first independent reviewer failed before producing findings because its model usage limit was reached. A fresh reviewer using the session default is pending. No independent-review acceptance is claimed. Self-inspection covered request validation, safe errors, buffer ownership, kill/reap, metadata limits and optional dependency boundaries.

Final independent review: fallback reviewer found one Important: communicate() accumulated unbounded stdout before validation. RED regression reproduced missing rejection of oversized output. Replaced communicate with bounded pipe reader (header + MAX_PCM_BYTES, one sentinel byte), bounded stdin writer and polling cancellation/timeout; overflow kills/reaps. Worker pipes use daemon I/O threads joined after child exit; owned receive buffer is cleared. No additional Critical/Minor findings. Review fix verified without claiming a second review.

Final regression: 583 passed in 11.05 seconds; compileall, pip check and diff check passed. Revised real source-runtime helper produced 163514 bytes / 3.40654 seconds at 24kHz for the same public fixed sentence; no device/file access. This rerun did not install a network-block hook; the earlier explicitly network-blocked run remains separately recorded. Last few samples may vary between native runs; no quality acceptance claim.
