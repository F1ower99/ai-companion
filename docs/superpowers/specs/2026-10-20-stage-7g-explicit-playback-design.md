# Stage 7G: explicit offline reply playback (draft)

## Goal and boundaries

Continue the approved offline Stage 7 voice roadmap: the user explicitly chooses to read the latest successfully persisted assistant reply, can stop playback, and push-to-talk interrupts playback before recording begins. No automatic speech on reply arrival, background monitoring, model downloads, conversation mutation, or cloud audio. Existing reminders, chat disclosure and manual Send are unchanged. This draft does not claim implementation or human acceptance.

## Architecture

Keep synthesis Qt-free. Add a single-use application SynthesisJob which owns generated AudioChunk until a Qt controller explicitly takes it. Cancellation clears a completed waiting result; an active synthesis finishes or notices its token, then clears any late result. Do not transport PCM in queued Qt signals: controller destruction must not orphan an uncleared queued audio result. Worker completion carries only an operation ID and a safe error code.

A separate SpeechController owns the synthesis lifecycle: unavailable, idle, synthesizing, playing, cancelling, error. Inject the local-only SpeechSynthesizer, a playback port, worker pool and metadata preflight. Generation checks surround notifications and external calls, including synchronous reentrant callbacks. A cancelled request cannot publish sound. Keep a worker reservation until it actually exits; do not start overlapping helpers. Closing the app cancels the job and stops the sink.

QtAudioPlayback is a Qt-thread-only infrastructure adapter. Construction does not discover devices. Explicit play checks the default output device supports exact 24kHz mono signed PCM16, then starts a QAudioSink reading memory. Unsupported/no device fails safely, without conversion or fallback. The adapter owns and clears the AudioChunk on finish, stop, failure and close. Qt/native buffer copies cannot be certified zeroized. No WAV or temporary audio files.

## Interaction

TTS is independently opt-in via an absolute local AI_COMPANION_TTS_MODEL_DIR and optional tts/voice dependencies; STT configuration is not required. Show a disabled-state explanation when absent. No model loading or device access at startup. Validate bundle metadata on explicit Speak, run synthesis in the background, and open the output device only after a current result is ready.

Select only the latest sent assistant reply. Normalize whitespace for speech, leaving persisted text intact. For more than 200 normalized characters, the button must explicitly say it reads the first 200 characters; disclose that bound before the click, never silently truncate. Empty/non-speech replies stay disabled. No reading of unsent drafts or failed/user messages. No automatic replay or retry.

Stop cancels pending synthesis and stops current output. Hiding/closing chat stops speech. Push-to-talk first stops playback on the Qt thread; if stopping fails, do not start microphone capture. A late synthesized result remains rejected while recording. Speak stays disabled during capture/transcription, and becomes available again only after voice work is idle. Preserve the character-first compact interface; use existing small controls/status rather than a dashboard.

## Failures, privacy and persistence

Expose typed safe errors only. Preserve conversation and composer on synthesis/output failure. No text, audio, device names, model paths or native exceptions in app logs or SQLite. No new schema. Never enumerate devices for default-off startup or automated tests. Source-runtime child launching is not a compiled-executable helper strategy; packaged integration remains deferred.

## Validation and acceptance

Use fake synthesizers, clocks where needed, worker pools and audio sinks. Test single-use ownership, cancel before/after synthesis, close before queued delivery, cancelled old completion, reentrant callbacks, pool rejection and safe errors. Test output format/no-device/error cleanup, natural completion, repeated stop and thread affinity. UI tests cover default-off, latest assistant selection, explicit bounded excerpt label, no autoplay, hide cancellation, and PTT stop ordering including stop failure. Run all prior tests, compileall, pip check, staged diff/secret inspection and independent review before marking complete.

Actual Windows listening, interruption and microphone echo behavior require user-led device acceptance; fake tests and valid PCM are insufficient. Deferred: long-reply segmentation, streaming, voice selection UI, automatic companion speech, packaged helper, voice cloning and cloud providers. Self-review: this is one explicit synthesis-to-device path; deterministic scheduling and conversation consent remain independent.
