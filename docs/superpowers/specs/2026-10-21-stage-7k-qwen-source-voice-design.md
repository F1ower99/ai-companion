# Stage 7K: Explicit experimental Qwen source-runtime speech

## Goal and boundaries

Make the successfully measured E-drive Qwen Serena candidate usable through the existing explicit Speak/Stop UI, without replacing Kokoro or claiming listening acceptance. The user requested a naturally soft offline female voice and authorized autonomous work and E-drive storage. Public-fixture synthesis and owned-process cancellation already succeeded; integration is a reversible, opt-in next slice on the Stage 7 voice roadmap.

No automatic playback, model download, voice cloning, microphone access, cloud requests, default switch, resident GPU service, compiled-app support, new shared-environment dependency or model redistribution. Scheduling remains deterministic and unrelated to the speech model. Naturalness and latency remain manual acceptance gates.

## Alternatives and selected architecture

Loading torch into the desktop process changes its dependency/GPU lifetime and weakens hard cancellation. A persistent service is faster but adds protocol/session lifecycle complexity. Select one owned child per explicit utterance using the existing isolated E-drive Python environment. Cold starts are slower; process exit releases the model and makes cancellation bounded. Preserve existing SpeechController generation handling and Qt playback unchanged.

Add a Qt-free LocalQwenSynthesizer implementing the same local-only text-to-PCM port as Kokoro. Source-only opt-in configuration selects `AI_COMPANION_TTS_ENGINE=qwen` plus absolute local paths `AI_COMPANION_QWEN_PYTHON`, `AI_COMPANION_QWEN_MODEL_DIR`, and `AI_COMPANION_QWEN_WORK_DIR`. Default/explicit `kokoro` keeps current configuration. Unknown engine or incomplete/invalid configuration fails closed, without trying another engine or discovering devices/models. The Qwen runtime is explicitly trusted executable code selected by the developer/user, not a downloaded executable launched automatically.

Reuse the bounded source-worker transport with an internal explicit command/environment/timeout boundary, leaving the public Kokoro runner's behavior and tests intact. Qwen launches only the selected interpreter with the fixed project worker module, no shell. Strip unrelated inherited application/provider environment; supply required Windows runtime variables, trusted source path, and offline/cache/temp configuration under the selected work root. Worker stdout is exclusively the existing ACV1/24kHz mono PCM16 frame; imports/native output are muted. No text/path/native exception logging. Input is bounded to the existing 200-character speech policy; output is at most 60 seconds, and parent timeout is 120 seconds including verification/import/model load. Cancellation kills and reaps only the owned child; no global process/device cleanup.

## Assets and inference

Support only the already verified pinned Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice revision `0c0e3051f131929182e2c023b9537f8b1c68adfe`. Check absolute local-drive paths and bounded, non-linked bundle shape/expected sizes with no native imports at UI preflight. Hash every asset against committed public manifest metadata inside the child before model loading. Do not trust a user-supplied “verified” flag. Only safetensors and the fixed configuration/tokenizer assets are accepted; extra linked/executable/pickle files are rejected. Large hashing and imports stay off the UI thread.

Worker sets offline/telemetry flags and blocks Python socket connections before importing the model. Load local files with `trust_remote_code=False`, `local_files_only=True`, `use_safetensors=True`, BF16 CUDA and SDPA, as validated by the feasibility probe. Require supported CUDA/BF16 and at least 5 GiB free before loading; do not stop other applications or fall back to an unbounded CPU run. Fixed Serena/Chinese and restrained gentle style; no custom instructions or reference audio. Bound generated tokens, validate finite/nonzero 24kHz mono samples and duration, convert clipped PCM16 and clear owned buffers. No private audio is written to disk. Cache/temp may contain runtime artifacts, never explicit transcript/audio persistence.

## Failure and interaction

Use existing NOT_CONFIGURED/CANCELLED/BUSY/SPEECH_FAILED codes and sanitized UI text. No fallback/retry that can restart cancelled speech. Config/model/GPU/runtime failure leaves task/chat/reminder functionality intact. Hide, clear-conversation, Stop, recording interruption and late-result rejection continue through existing controllers. Cold synthesis may be slower than real time; docs label the option experimental. Existing configured output device continues to determine playback; no automatic audio audition in development.

## Verification and acceptance

TDD tests cover missing/local/linked/oversized/modified assets, pinned manifest hashes using small fixtures, invalid runtime/work paths, cancelled/busy calls, bounded binary protocol and buffer cleanup, exact child command/env/timeout, worker local-only loader options and invalid waveform handling, and config engine selection without parent torch imports/device probes. Full old/new regression, compileall, pip check, diff/secret inspection and fresh independent review precede integration. Run a bounded real public-sentence synthesis using the actual E runtime through the new adapter, with no playback, and verify cancellation/reaping. Manual voice preference, microphone interaction and packaged execution remain unclaimed.

Self-review: source-only experimental configuration is reversible and does not bypass listening acceptance or change the existing default. The isolated environment/model already exist; no installation or credentials are required. The per-request cold-start tradeoff is recorded rather than hidden by premature caching. No product-owner fork is needed to expose an opt-in candidate.
