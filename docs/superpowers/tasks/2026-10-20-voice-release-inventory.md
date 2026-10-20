# Voice release inventory execution record

Scope: bounded extension of the existing Stage 7B metadata inventory while the isolated natural-voice experiment downloads. The user authorized continuing independent work. No new application subsystem, dependencies, model integration, microphone access or settings changes.

Design: repeatable `--extra` selects declared project extras alongside base requirements. Evaluate root markers in the project context, then preserve child-owned extras for transitive traversal. Reject unknown extras and mutually exclusive explicit requirements before writing output. Keep default inventory base-only.

TDD: added five tests; four failed on the absent selection helper/CLI, while the incompatible-options rejection already failed closed. Implemented selection; all 16 inventory tests passed. Cases cover normalization/deduplication, exclusion of unselected development requirements, platform markers, transitive extras, unknown names, CLI output preservation and incompatible flags.

The current shared editable installation has older project metadata without `stt`/`tts`. The new CLI correctly rejected that mismatch. Rather than changing the shared environment, generated `docs/THIRD_PARTY_NOTICES_VOICE.md` using the five explicit current pyproject runtime roots documented in README. It contains 36 installed distributions and preserves missing/unparseable licensing review flags. It excludes the isolated Qwen experiment, model assets, interpreter and native-library release certification. This is not redistribution approval.

Validation on 2026-10-20:

- Full regression: **642 passed in 11.03 seconds**, real Windows process, offscreen Qt, temporary profiles and fake devices.
- Sandboxed full regression: 620 passed, 22 failed in local model-directory checks on sandbox drive paths. Reran outside the sandbox without weakening model location checks; all passed. Sandbox interpreter shutdown also emitted a pyreadline console-handle diagnostic; the real Windows run exited cleanly.
- `compileall -q src tests scripts`, `pip check` and `git diff --check` passed.
- Actual build preflight failed safely: missing `cl`, `dumpbin`, Nuitka 4.1.1, ordered-set and zstandard. No build tools installed and no binary produced.
- README corrected outdated statements about playback and manual voice acceptance.

Independent review: no actionable findings. Reviewer independently ran all 16 inventory tests successfully; exit code 0 with the documented sandbox pyreadline shutdown diagnostic. Base and voice inventories were regenerated in memory and compared byte-for-byte with the checked-in text. Diff and credential-pattern checks passed; only the five release-inventory files are included in this commit.

Remaining release gates: compiler/build environment, actual standalone build, packaged helper compatibility, model/native dependency redistribution review, isolated-profile GUI acceptance, microphone UX and Chinese recognition quality. Existing headphone playback works but its naturalness was rejected by the user. The E-drive Qwen download is an experiment, not completed product integration.
