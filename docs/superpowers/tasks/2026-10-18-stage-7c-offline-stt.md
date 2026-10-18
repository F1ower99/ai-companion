# Stage 7C execution record

Plan: `docs/superpowers/plans/2026-10-18-stage-7c-offline-stt.md`; base `5e15fe8`.

Pre-flight: the existing STTProvider consumes AudioChunk/CancellationToken and returns VoiceTranscript; the adapter and smoke CLI match those signatures. Normal app composition does not import this optional adapter.

Task 1: tests failed for missing adapter, then passed after local-only CPU adapter implementation. On checking the actual pinned publisher model, corrected the fixture and required vocabulary filename from vocabulary.json to vocabulary.txt; watched tests fail then pass with the corrected format. Runtime imported successfully; unit tests use controlled native boundaries.

Task 2: generated WAV tests failed for missing CLI, then passed. Validates format/duration before reading payload, detects truncation, clears PCM and reports only counts/runtime by default.

Ruling: implement recognition first, leaving synthesis and microphone/UI integration as separate roadmap slices. This creates a real independently testable STT path without coupling two native speech runtimes. Cost: interactive voice remains unavailable until the remaining slices are implemented and manually tested.

Ruling: use the existing tracked task record in place of the protected skill scratch directory, as in Stage 7A/B. Cost: manual progress bookkeeping.

Ruling: keep numpy/faster-whisper optional. Model-dependent adapter tests skip when numpy is absent; default UI/core tests remain available with .[dev]. Run all tests in the explicitly installed .[stt] environment for this stage. Cost: CI needs the optional extra to exercise native-array conversion coverage.

Task 3: optional faster-whisper 1.2.1 runtime installed into the development venv. Public model acquisition and real smoke verification are in progress; no real microphone or private audio has been used. Full suite before final review: 465 passed.
