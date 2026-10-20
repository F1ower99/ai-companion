# Natural Chinese voice feasibility spike

## Question and user requirement

Can an isolated offline Qwen3-TTS CustomVoice evaluation produce a naturally soft Chinese female voice acceptable to the user, without changing the stable companion runtime? Current Kokoro default and three alternative Chinese female sids6/26/48 failed listening acceptance despite working routing/playback. The user's goal is conversation-friendly prosody/timbre, not more similar voice IDs. Existing autonomous authorization permits a reversible prototype; model/provider integration requires evidence first.

## Candidate and alternatives

Evaluate official Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice with built-in Serena, described upstream as a warm gentle native-Chinese female speaker. The1.7B CustomVoice supports style instructions;0.6B CustomVoice has the same preset speaker selection but is documented without instruction control. Prefer the former for this specific prosody problem, subject to measured memory/latency. CosyVoice3 remains an alternative, but its extra setup/reference-audio concerns make it a less simple first probe. No voice cloning or personal reference audio.

Metadata verified2026-10-20: qwen-tts0.1.1 requires Python>=3.9, transformers4.57.3, accelerate1.12.0 and audio/runtime packages. Official setup recommends a separate Python3.12 environment. Model revision0c0e3051f131929182e2c023b9537f8b1c68adfe; all files4,520,218,951 bytes, including model.safetensors3,833,402,552 bytes SHA25638b1d5971bdbd982b561cccec982669a53b0537c3cf5e9bd4778ed07bb2f5137 and bundled speech_tokenizer/model.safetensors682,293,092 bytes SHA256836b7b357f5ea43e889936a3709af68dfe3751881acefe4ecf0dbd30ba571258. Model card declares Apache2; dependency/notices review remains separate. Runtime files/weights are not committed or redistributed.

## Probe boundaries

Use a dedicated environment and caches outside the current venv/profile, and a dedicated verified model directory. Do not upgrade PySide6, change existing dependencies or install system compilers/drivers. First inspect wheel compatibility; prefer prebuilt CUDA/SDPA support without FlashAttention compilation. Query CUDA and free memory before loading; measured fit is not guaranteed merely by GPU capacity. No cloud API, remote inference, telemetry, microphone, embeddings or scheduling changes.

Download public official pinned assets only after a suitable storage root is available, verify hashes/size before use, and record software/model provenance. No trust_remote_code or pickle model files. Actual synthesis must load local files with offline flags; block network in the probe where feasible. Use fixed public short Chinese sentences and bounded generation. Start with Serena and a restrained natural/gentle instruction; include neutral versus instructed comparison. Do not assume slower speed means more natural.

Output and process lifetimes remain bounded; no private conversation context, device identity or recordings enter logs/reports. Audition playback is explicit and on the user-selected output, with cancellation/PCM cleanup as already verified. Record timing, output rate/duration, peak device memory and failure states. Ask the user for listening judgment; code success is insufficient. Do not make this the app's default until quality, performance and cleanup are measured and an integration spec exists.

## Storage decision and execution boundary

The initial workspace-volume check found less than1GiB free. The user then explicitly selected E drive for the new model. Use E:/AICompanionVoiceLab for weights, isolated runtime, caches, temporary files and evidence; filesystem access was granted. Reserve at least15GiB headroom before setup. Existing project dependencies remain unchanged. qwen-tts0.1.1 wheel SHA25611a290d8dabc7ef91a90c54478c8ab19b3edb1d85c0882313721892bdc4af15d verified from official PyPI. Acquisition and public-fixture synthesis subsequently completed; see `docs/offline-qwen-voice-probe-2026-10-21.md`. Listening acceptance and production integration remain pending.

## Sources

- https://github.com/QwenLM/Qwen3-TTS (preset descriptions, model capability matrix, isolated setup)
- https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice (license and pinned metadata)
- https://pypi.org/pypi/qwen-tts/json (version/dependency metadata)
- https://github.com/QwenAudio/CosyVoice (alternative setup/reference boundary)
