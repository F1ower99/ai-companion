# Isolated natural Chinese voice probe

This is development evidence, not a new production provider or listening-quality approval. The user rejected Kokoro's default and three alternative Chinese female voices as stiff, requested a natural gentle female voice, and selected E drive for the larger offline candidate.

## Verified acquisition and isolation

- Official model: `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice`, revision `0c0e3051f131929182e2c023b9537f8b1c68adfe`.
- All 13 files verified against pinned publisher Git/LFS hashes; total **4,520,218,951 bytes**. The probe rechecked current file hashes before loading.
- Main model SHA256: `38b1d5971bdbd982b561cccec982669a53b0537c3cf5e9bd4778ed07bb2f5137`.
- Speech tokenizer SHA256: `836b7b357f5ea43e889936a3709af68dfe3751881acefe4ecf0dbd30ba571258`.
- `qwen-tts==0.1.1` wheel SHA256: `11a290d8dabc7ef91a90c54478c8ab19b3edb1d85c0882313721892bdc4af15d`.
- Separate E-drive Python 3.10 environment: torch/torchaudio 2.9.1 CUDA 12.6, transformers 4.57.3, accelerate 1.12.0. Isolated pip check passed; version inventory retained locally.
- Weights, runtime, caches, temporary files and evidence all under `E:/AICompanionVoiceLab`, approximately **9.5 GB** after installation. Existing project environment and GPU driver were not upgraded.
- A pre-existing cached torch wheel failed comparison with the official artifact hash; it was not reused. Partial official model downloads were resumed, never loaded before complete verification.

Model card declares Apache-2.0; package/model/native dependency redistribution review remains separate. Neither the model nor isolated runtime is committed or redistributed.

## Offline synthesis

Used built-in Serena, bfloat16 and SDPA, local files only, safe tensors and no trust_remote_code. Both offline/telemetry flags and Python socket connection blocking were active. No server, microphone, private conversation or reference voice was used. Fixed public sentence:

> 你好，今天辛苦了。先休息一下，我们慢慢来。

Generated neutral and gentle-instruction variants with fixed seed and bounded generation. Audio was finite, nonzero, 24kHz mono PCM16, and within duration limits. Only these public synthetic samples were saved locally for a later user-led audition; **no automatic playback** occurred.

| Observation | Result on this one development machine |
| --- | --- |
| Model load, after Python imports | 6.56 seconds |
| Neutral synthesis | 10.60 seconds for 3.76 seconds of audio |
| Gentle synthesis | 10.16 seconds for 4.16 seconds of audio |
| Peak PyTorch allocated GPU memory | 4,278,283,264 bytes |

These are single-run observations, not general latency or total VRAM requirements. Peak PyTorch allocation excludes other GPU/runtime allocations. The observed synthesis is slower than real time and needs a later interaction/performance decision if listening quality is accepted. Missing optional FlashAttention and SoX executable warnings did not prevent this CustomVoice path from succeeding; neither was installed to silence warnings.

## Owned-process cancellation

A separate offline, fixed-public-text child loaded the model and started generation. After 0.75 seconds of generation, only that child was terminated and reaped; termination took about 0.0024 seconds in this observation. GPU free-memory snapshots were 6,217 MiB before and 6,261 MiB after; these snapshots include unrelated system variation and are not a general leak proof. No unrelated application was stopped. No audio was played or captured.

## Public-sample recognition sanity check

The same two public synthetic samples were resampled from 24kHz to 16kHz and passed to the existing local Whisper base CPU recognizer with networking blocked. Neutral returned “你好今天辛苦了先休息一下我们慢慢来” (1.80 seconds); gentle returned “也好今天辛苦了先休息一下我们慢慢来” (0.59 seconds). The small Chinese recognizer already has known errors. These observations do not establish pronunciation or naturalness, and do not replace user listening. No microphone, private recording or playback was involved.

## Remaining gates

Naturalness, pronunciation and user preference have **not** been accepted. No app default, provider composition or scheduling rule changed. Production integration needs its own source/packaged helper protocol, bounded model/session lifetime, cancellation/error handling, runtime selection, latency UX and release review. The stable app still uses its existing optional Kokoro path.

Primary references: [Qwen3-TTS upstream](https://github.com/QwenLM/Qwen3-TTS), [pinned model](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice/tree/0c0e3051f131929182e2c023b9537f8b1c68adfe), [PyPI package metadata](https://pypi.org/pypi/qwen-tts/0.1.1/json), [PyTorch version matrix](https://pytorch.org/get-started/previous-versions/).

Subsequent Stage 7K adds an explicit experimental source-runtime adapter, documented in its separate design/execution record and README. Public-sentence adapter runs and owned cancellation passed; default Kokoro, pending listening acceptance and unsupported packaged/release boundaries remain unchanged. The statements above describe the original isolated probe, not a claim of production quality acceptance.
