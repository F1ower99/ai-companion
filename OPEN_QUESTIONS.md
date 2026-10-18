# Open Product Questions

## Stage 7: Local speech stack

Resolved direction, 2026-10-18: the user selected bundled/local offline models. The earlier Windows-built-in versus bundled-model product choice is closed.

- Windows built-in speech APIs and installed voices: smaller app payload, but recognition language availability, Windows setup, and voice quality vary by machine.
- Bundled local models: more predictable offline behavior and language support, with a larger download, model-license review, and more CPU/RAM use.

Stage 7C implements the first local STT adapter using faster-whisper and local multilingual Whisper models; CPU int8 is the baseline. TTS model/runtime selection follows in a separate technical slice with model-license and Chinese-language validation. Runtime microphone controls remain disabled until capture and UI wiring are tested. Cloud audio remains excluded; neither startup nor transcription may download models automatically.
