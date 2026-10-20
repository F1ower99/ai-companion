# Local STT smoke: partial-frame rejection

Bounded follow-up to the Stage 7C review's dangling-byte finding, under the user's autonomous authorization. Only the explicit public-fixture WAV smoke tool changes; no capture, model or application behavior changes.

Cause: Python's wave reader floors the frame count when a PCM16 data chunk has an odd byte count. Reading exactly that many frames silently discarded the dangling byte. Probe fixtures with 3 and 17 data bytes reproduced acceptance; the one-byte fixture already failed because its frame count is zero.

Fix: request one extra frame, still bounded to the validated limit plus two bytes, and retain the exact expected-length check. Invalid PCM is cleared and returns the existing sanitized capture-failed code. Valid WAV ancillary chunks remain outside the wave data reader.

TDD: three parameterized fixtures; two RED failures before the fix, all 12 smoke-tool tests GREEN after. Full regression: **645 passed in 10.76 seconds** on real Windows with temporary data and fake devices. Compileall, pip check and diff check passed. Independent review found no actionable issues and independently passed all 12 smoke-tool tests. No personal audio, microphone or network was used.
