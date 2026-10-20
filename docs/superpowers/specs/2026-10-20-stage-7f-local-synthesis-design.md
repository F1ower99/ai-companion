# Stage 7F: bounded offline Chinese speech synthesis

## Intent and scope

Continue the approved offline voice roadmap with a real CPU text-to-PCM backend. User authorization permits autonomous spec/plan/implementation/review. This architectural slice separates synthesis from Qt audio-device playback. It does not enable the Speak button yet; the next playback/controller slice consumes synthesized PCM. No microphone/speaker is opened in development, no private text/audio or credentials are used.

## Selection and alternatives

Use optional `sherpa-onnx==1.13.8` and numpy, with the converter's Kokoro int8 v1.1-zh bundle. PyPI provides a Python 3.10 Windows x64 wheel and separate matching core package. Original Kokoro PyTorch/Misaki adds substantially more runtime and language dependencies; Windows installed voices do not follow the selected model direction.

Sources: [Sherpa wheel](https://pypi.org/project/sherpa-onnx/1.13.8/), [original Chinese model](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh), [converter and speaker mapping](https://k2-fsa.github.io/sherpa/onnx/tts/all/Chinese-English/kokoro-multi-lang-v1_1.html). Original weights declare Apache 2.0, Chinese/English, 103 voices; select Chinese female speaker 3 (`zf_001`) by default, 24 kHz mono. Runtime/model notices do not cover all eSpeak/phonemizer/dictionary release obligations. Keep weights/data ignored and record upstream notices; binary redistribution still needs license review.

Pinned converter repository: `csukuangfj/kokoro-int8-multi-lang-v1_1`, revision `155831f1b4ba23b1f5c058be6a61df90cefb2a37`. Require model.int8.onnx, voices.bin, tokens.txt, lexicon-us-en.txt, lexicon-zh.txt, date/number/phone-zh.fst and complete espeak-ng-data. This runtime no longer needs external dict_dir. Separate asset acquisition verifies publisher hashes; app execution never downloads models/data or installs packages.

## Isolation and API

Add a Qt-free `SpeechSynthesizer` port with `local_only is True` and `synthesize(text, cancellation_token) -> AudioChunk`. Existing TTSProvider speaks through a device and remains unchanged; synthesis alone must never imply playback.

`LocalKokoroSynthesizer` is lazy and nonblocking with respect to construction: no imports of native TTS, weights, device or network. On explicit synthesize it validates configuration/input, reserves a single operation and runs a short-lived worker subprocess. One process per request trades loading latency for isolation, simple cancellation and bounded lifetime. This is a source-runtime baseline; standalone packaging will need an explicit helper strategy, not re-launch a compiled app with Python -m.

Pinned upstream [native code](https://github.com/k2-fsa/sherpa-onnx/blob/v1.13.8/sherpa-onnx/csrc/offline-tts-kokoro-impl.h) can log the original text on tokenization failure even with debug false. Therefore the worker's stderr is DEVNULL, stdout is a private bounded binary protocol, and stdin carries transient JSON; no text/model paths in command arguments or app logs. No process-wide stderr redirection in the GUI. Subprocess creation uses shell=False and CREATE_NO_WINDOW on Windows. Runtime errors become safe VoiceOperationError codes, never raw child output.

## Bounds and cancellation

Validate nonblank Unicode text at most 200 characters after whitespace normalization; reject NUL/control/surrogate input and strings without alphanumeric speech content. Reject invalid speaker (only integer 0–102), threads (integer 1–8), relative/URL/UNC/mapped remote locations and model paths containing comma (native lexicon delimiter). Defaults speaker 3, CPU threads 2, speed 1.0, max_num_sentences 1, debug false. No personality or voice cloning.

Validate local directory/root confinement before native loading, required nonempty files and a bounded espeak data tree (at most 1,000 files, total bundle at most 256 MiB). Reject links escaping the model root. This is a trusted developer model bundle, not a sandbox for arbitrary malicious ONNX packages.

Worker validates model metadata (24 kHz, 103 speakers), generates no more than 60 seconds of mono PCM16, rejects empty, nonfinite, malformed or oversized samples rather than returning a truncated utterance. Callback limits and final validation enforce application output bounds; native temporary allocation is not certified. Output is magic ACV1 + little-endian sample-rate/byte-length header + exact PCM payload, at most 2,880,000 bytes. Parent checks header/length/format before transferring a mutable AudioChunk. Owned worker arrays/PCM are cleared; OS pipes, native/immutable copies cannot be guaranteed zeroized.

Parent uses bounded pipe-reading/writing threads and polls process completion/cancellation and a 90-second overall infrastructure timeout; cancellation or timeout kills and reaps the worker, returns no partial audio. Timeouts live in the infrastructure runner, not deterministic task scheduling. Cancellation is checked before configuration, launch and publication. Concurrent synthesize fails BUSY without affecting the active request. Injected runner/native loader permit deterministic tests.

## Acceptance

TDD tests cover lazy behavior, local path/file/tree checks, controls/text limits, overlap, cancellation before/during/after subprocess work, protocol errors, safe exceptions, native configuration, waveform validation/conversion and cleanup. Run full old/new regression, compileall, pip check, diff/secret inspection and one independent review with a RED/GREEN fix pass.

Acquire verified public model files, install optional runtime explicitly, then synthesize a fixed public Chinese sentence in memory with Python network connects blocked. Record exact asset hashes, duration/rate/processing evidence and whether execution actually succeeded. This proves execution, not intelligibility. No audio file, speaker playback or real user text. If acquisition fails, report that limitation without claiming a real synthesis pass.

Deferred: Qt QAudioSink/controller integration, Speak-latest-reply interaction and PTT interruption of playback, real listening/quality/accessibility acceptance, packaged helper, model chooser and richer voices. No task/memory/database/LLM/consent changes. Self-review: synthesis is independently callable/testable, error text stays inside a muted child, and no enabled UI misrepresents playback readiness.
