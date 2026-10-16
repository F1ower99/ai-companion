# Open Product Questions

## Stage 7: Local speech stack

Which offline speech stack should be the first shipped engine (speech recognition and speech output)?

- Windows built-in speech APIs and installed voices: smaller app payload, but recognition language availability, Windows setup, and voice quality vary by machine.
- Bundled local models: more predictable offline behavior and language support, with a larger download, model-license review, and more CPU/RAM use.

Stage 7A proceeds with a provider-neutral voice lifecycle; Stage 7B prepares the Windows packaging baseline. Runtime voice remains disabled until a local engine is selected and tested. Cloud speech is excluded by the current privacy instruction against uploading private data.
