# Open Product Questions

## Stage 7: Local speech stack

Resolved direction, 2026-10-18: the user selected bundled/local offline models. The earlier Windows-built-in versus bundled-model product choice is closed.

- Windows built-in speech APIs and installed voices: smaller app payload, but recognition language availability, Windows setup, and voice quality vary by machine.
- Bundled local models: more predictable offline behavior and language support, with a larger download, model-license review, and more CPU/RAM use.

Stage 7C implements the first local STT adapter using faster-whisper and local multilingual Whisper models; CPU int8 is the baseline. Stage 7D/E adds bounded capture and explicit opt-in recording UI/worker wiring, tested with fake devices. Default recording stays disabled unless local modules and AI_COMPANION_STT_MODEL_DIR are provided. Real-device UX and Chinese recognition quality remain unapproved. TTS model/runtime selection follows in a separate technical slice with model-license and Chinese-language validation. Cloud audio remains excluded; neither startup nor transcription may download models automatically.


## Post-Stage 7 acceptance and foreground-awareness scope (2026-10-22)

The original concept mentioned foreground application names and usage duration. The approved current roadmap and Stage 6 privacy contract explicitly exclude both. Idle/recent-input sensing does not satisfy that original capability. Any future application-awareness stage requires a separate written privacy specification and review; existing activity consent must never silently expand. Leave implementation deferred until this product direction is resolved. No collection or schema change was made during the autonomous session.

Outstanding human acceptance: real microphone/GUI recognition, Qwen soft-female naturalness and latency, desktop/tray/login interaction, and the recording-draft-to-reminder confirmation experience. Public fixtures, headless startup and green automated tests are independent evidence, not substitutes for these checks. See `docs/first-desktop-experience.md`. No credential or device authorization is requested while the user is asleep.
