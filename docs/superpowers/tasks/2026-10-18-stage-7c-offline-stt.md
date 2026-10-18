# Stage 7C execution record

Plan: `docs/superpowers/plans/2026-10-18-stage-7c-offline-stt.md`; base `5e15fe8`.

Pre-flight: the existing STTProvider consumes AudioChunk/CancellationToken and returns VoiceTranscript; the adapter and smoke CLI match those signatures. Normal app composition does not import this optional adapter.

Task 1: tests failed for missing adapter, then passed after local-only CPU adapter implementation. On checking the actual pinned publisher model, corrected the fixture and required vocabulary filename from vocabulary.json to vocabulary.txt; watched tests fail then pass with the corrected format. Runtime imported successfully; unit tests use controlled native boundaries.

Task 2: generated WAV tests failed for missing CLI, then passed. Validates format/duration before reading payload, detects truncation, clears PCM and reports only counts/runtime by default.

Ruling: implement recognition first, leaving synthesis and microphone/UI integration as separate roadmap slices. This creates a real independently testable STT path without coupling two native speech runtimes. Cost: interactive voice remains unavailable until the remaining slices are implemented and manually tested.

Ruling: use the existing tracked task record in place of the protected skill scratch directory, as in Stage 7A/B. Cost: manual progress bookkeeping.

Ruling: keep numpy/faster-whisper optional. Model-dependent adapter tests skip when numpy is absent; default UI/core tests remain available with .[dev]. Run all tests in the explicitly installed .[stt] environment for this stage. Cost: CI needs the optional extra to exercise native-array conversion coverage.

Task 3: optional faster-whisper 1.2.1 runtime installed into the development venv. Public model acquisition and real smoke verification are in progress; no real microphone or private audio has been used. Full suite before final review: 465 passed.

Final verification: 470 tests passed with the stt runtime installed; compileall, pip check and Git whitespace checks passed. Feature commit `cdbb7ec`; review fix commit recorded by Git. Actual public English CPU inference and the full WAV CLI both passed with Python socket connections blocked: 11 seconds input, 106 recognized characters, 0.951/0.76 seconds processing. Publisher revision and asset hashes are in `docs/offline-stt-assets-2026-10-18.md`.

Fresh independent review: two Important findings reproduced with four failing tests, then fixed in one pass. Cancellation now precedes each lazy decode advance as well as following it. Raw and resolved model locations are checked; Windows GetDriveTypeW rejects mapped remote/unknown drive roots before model access. No Critical findings.

Final: minor (deferred): the developer WAV smoke CLI can accept an odd-byte PCM data chunk by ignoring its incomplete final sample; it is not the app capture path. Future fixture hardening should explicitly reject this malformed tail.

Final: Ruling: user-supplied model directories and injected test factories are trusted developer boundaries; hostile concurrent file replacement or factories altering cleanup behavior are not a sandbox threat model here. Cost: these cases need a separate hardening design before accepting untrusted model packages/extensions.

Final: Ruling: owned float waveform buffers are cleared, but native-library internal/immutable copies have no zeroization guarantee; cancellation does not preempt an already running native operation. Cost: native inference latency and memory behavior still require device-level acceptance. The fixes do prevent starting new decode work after cancellation is already known.

Reviewer-set-aside rulings: real English inference is now verified, Chinese quality remains pending; mic/TTS/Qt composition/packaging stay deferred to their own slices. Cost: there is still no interactive voice UI, and no Chinese usability claim.

Chinese public fixture download was blocked before execution by automatic approval review service usage exhaustion, not by an unsafe-action determination. All unaffected local verification was completed; no approval bypass or private audio use. Source-checkout smoke commands explicitly set PYTHONPATH=src because the existing shared editable install points to the parent checkout; a no-build-isolation editable reinstall failed due missing bdist_wheel. The existing installed app metadata was not altered by that failed attempt.
