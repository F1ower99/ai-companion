# Stage 7C: Local Whisper Speech Recognition

Status: self-reviewed for autonomous implementation under the user's continuing authorization. On 2026-10-18 the user selected offline models.

## Intent and scope

Turn the Stage 7A STT port into a real local inference adapter, with a reproducible CPU smoke check using public test audio. Preserve the companion's explicit speech/draft/send boundary and local deterministic reminder engine. Chinese is the default recognition language; no GPU is assumed. Model quality and microphone UX remain empirical acceptance questions, not claims from synthetic tests.

This independently testable slice includes local model validation, optional runtime dependencies, an STT adapter, a bounded WAV smoke CLI, and model acquisition/notice instructions. It does not enable microphone controls, change SQLite, collect personal audio, add automatic downloads, implement TTS, or change basic scheduling. Real Qt capture/worker UI and local TTS follow as separate slices.

## Alternatives and selection

- sherpa-onnx unifies recognition and synthesis under an ONNX runtime and supports Windows. Candidate Chinese SenseVoice weights have a custom model license, distinct from the runtime's Apache license; do not assume they share licensing.
- faster-whisper with multilingual Whisper base provides a CPU/int8 path and a clear local-directory API. Its code and the selected Systran base model card declare MIT licensing. It requires separate TTS integration and native runtime dependencies.
- Windows built-in recognition is not selected: the user explicitly chose offline models.

Select faster-whisper 1.2.1 as an optional `stt` extra, with a local multilingual base model as the first smoke candidate. Larger models may later use the same adapter after measurement. Do not bundle weights into Git. Runtime defaults remain unaffected when the extra is absent.

## Model and network boundaries

- `LocalWhisperSTT(model_directory, language='zh', cpu_threads=4, model_factory=None)` implements existing STTProvider with `local_only=True`; no imports, model loads, hardware, environment mutation, or network calls at construction.
- On first transcription validate an existing absolute local directory; reject URLs, repository identifiers, UNC/network paths, missing/empty files, and required files resolving outside that directory.
- Require `model.bin`, `config.json`, `tokenizer.json`, and `vocabulary.json`. Limit their combined size to 1 GiB. These are data files, never Python code, pickle, or remote-code providers. Record publisher/revision/hash in the development smoke record; distributing actual weights requires preserving their applicable license.
- Pass an absolute directory and `local_files_only=True`, `device='cpu'`, `compute_type='int8'`, one worker and 1–8 CPU threads (default 4). Missing tokenizer must fail before importing/loading the backend: the pinned upstream otherwise falls back to downloading one.
- Model acquisition is a separate explicit developer action against public publisher assets. Inference never downloads assets, discovers credentials, or sends audio/transcripts. Do not add a downloader to app startup.

## Audio and output

- Accept the existing bounded AudioChunk, restricted here to 16,000 Hz mono signed little-endian PCM16. Reject any other format without silently resampling or calling ffmpeg.
- Convert PCM to an owned float32 waveform; clear it in finally on success, failure or cancellation. Stage 7A continues to own clearing the original PCM.
- All-zero audio returns a safe no-transcription failure before loading the model; do not generate hallucinated text from digital silence.
- Request transcription, not translation; default language `zh`, optional `en` for the public smoke fixture. Use beam size 1, temperature 0, no previous-text conditioning, no VAD/model downloads, no word timestamps or progress output.
- Consume the lazy segment iterator, checking cancellation before model load, after load, and between segments. Reject blank text, non-text segment contents, more than 256 segments, or combined output over 8,000 characters. Return VoiceTranscript only after completion and a final cancellation check.
- One call per adapter at a time; reject overlap safely. Loading/inference can only be cancelled cooperatively between native operations; do not promise immediate interruption of a native decoder. The caller schedules blocking work off the Qt thread.
- Convert backend/import/file failures to stable VoiceOperationError codes; do not log raw provider exceptions, input audio, transcript, or private file paths.

## Smoke CLI and persistence

`scripts/smoke_local_stt.py --model-dir ABSOLUTE_PATH --wav FILE --language zh|en` accepts only <=60-second 16k mono PCM16 WAV, uses the same adapter/session ports, reports success/runtime and transcript character count but no recognized text by default. A deliberate `--show-transcript` developer option permits inspecting a public fixture only. It does not access microphone, UI, SQLite, Credential Manager or network. Validate WAV header/frame size before reading the bounded payload; never load arbitrary files through a media auto-decoder.

There is no persistence change. Weights live in an ignored model directory outside source control. Public smoke recordings are test assets outside Git; private recordings are never used automatically. No transcript is sent to ChatService.

## Tests and acceptance

- Fake backend tests exercise path completeness, missing tokenizer before factory call, format/PCM normalization, local CPU flags, lazy segment iteration, output limits, native exceptions, overlapping calls and cancellation at each cooperative boundary; retained waveform arrays must be zero after return.
- WAV CLI tests use generated temporary PCM and controlled fake providers; test duration/header limits and no default transcript printing.
- Install the optional runtime only into the project environment, then use a verified public model/sample for a real CPU smoke run with Python network calls blocked. Keep automated unit tests independent of installed weights and audio hardware.
- Run full existing suite, compileall, pip check, diff/secret checks, fresh independent review, RED→GREEN fixes and commit. Record real model revision/hashes, results, and limitations without equating one sample with Chinese UX validation.
- Completion requires real inference if runtime/assets are available. If model acquisition is blocked, report that exact gap; do not claim fake tests prove recognition quality.

## Deferred

Qt microphone permission/capture/60-second timer, actual voice controls and worker wiring, local TTS (including Chinese voice/model license review), GPU support, VAD, streaming, arbitrary resampling, installers and MSVC setup. No owner decision remains on cloud versus offline speech.

## Primary sources

- [faster-whisper 1.2.1](https://pypi.org/project/faster-whisper/1.2.1/), [pinned model constructor](https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/faster_whisper/transcribe.py)
- [Systran multilingual base model card](https://huggingface.co/Systran/faster-whisper-base), [Whisper license](https://github.com/openai/whisper/blob/main/LICENSE)
- [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx), [SenseVoice model card](https://huggingface.co/FunAudioLLM/SenseVoiceSmall)
