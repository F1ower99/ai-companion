# Compiled TTS source-worker safety

Bounded packaging-safety follow-up, branch `codex/compiled-tts-safety`, base `0aa8b03`, under the user's continuing autonomous authorization. Design: fail closed for the existing source-only helper in Nuitka/frozen runtimes, both at UI composition and the direct subprocess boundary. No replacement packaged speech backend or compiler installation.

Cause: run_tts_worker used `sys.executable -m companion.infrastructure.tts_worker` unconditionally. In a compiled desktop application, sys.executable is the desktop executable, not a Python interpreter; invoking it as a worker could open another application instance or block until timeout. Existing docs acknowledged missing packaged helper support, but code did not enforce it.

TDD: Nuitka/frozen tests at both boundaries failed before implementation (four RED failures). Added source_tts_supported using module compiled marker/frozen status, disabled configured TTS with a concise packaged-runtime reason before optional module/device setup, and returned NOT_CONFIGURED from direct calls before Popen. Cancellation still takes precedence. All 27 focused worker/configuration tests passed. The new forbidden-process test suppresses traceback payloads so a failing test cannot dump inherited environment values.

The source-runtime behavior, independent microphone path and existing synthesis/playback protocol remain unchanged. This is not a claim that an actual binary was built. Full regression: **701 passed in 13.25 seconds**. Compileall, pip check and diff check passed. Independent review found no actionable findings and independently passed 18 runtime/configuration tests.

Primary references: [Nuitka runtime detection](https://nuitka.net/user-documentation/tips.html) and [compiled executable behavior](https://nuitka.net/user-documentation/common-issue-solutions.html). Actual packaged execution remains a separate release gate; these tests simulate supported compilation markers without starting a desktop subprocess.
