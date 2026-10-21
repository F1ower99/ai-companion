# Stage 7N: Explicit packaged Qwen worker

## Purpose and boundaries

The actual Windows GUI executable works, but it cannot yet use the accepted offline architecture for explicit speech: its frozen modules cannot be imported by the separate Python runtime. Continue the roadmap's packaged-voice gate with a small, replaceable extension to Stage 7K. Preserve the default engine and source behavior. No automatic playback, microphone access, model/runtime downloads, GPU residency, voice cloning, credentials or cloud requests. Naturalness, microphone UX and manual packaged experience remain unaccepted.

## Selected design

Retain the explicitly configured external Qwen Python/model/work directories. At build time create a deterministic ZIP containing only the worker's required first-party Python modules and package initializers. Embed the ZIP's SHA-256 in a generated module in the staged source, and include the ZIP beside the executable as data. The checked-in placeholder contains no digest, so an unprepared compiled build remains unavailable. Neither the source tree nor existing outputs are rewritten.

A Qt-free resolver returns the normal source root in source execution. In a compiled process it locates only the fixed adjacent ZIP, rejects missing/oversized/linked/non-local paths (including ancestors), hashes its bounded contents, and compares against the compiled expected digest. No arbitrary environment-provided source path or self-reported manifest is trusted. External Python runs in isolated mode (-I), with a fixed -c stdlib bootstrap adding only the verified ZIP before running the fixed worker module. Python3.10 is supported; do not rely on newer -P. The isolated interpreter ignores PYTHONPATH and inherited CWD/user-site, and -X pycache_prefix keeps bytecode on E. Minimal offline environment and the existing bounded stdin/stdout protocol remain. Source execution uses the same isolated bootstrap with its fixed source root. Model verification, cancellation, timeout and owned-process reaping stay unchanged. Source execution keeps its current source root; no code is extracted to model/cache/profile directories.

Kokoro's compiled guard remains unchanged. Qwen's controller permits a compiled environment only when this worker ZIP is verified and Qt Multimedia is actually present. Missing bundle/runtime/model/Multimedia fails closed without a process or fallback. The build environment may explicitly add the already pinned voice extra on E; base builds still work without it and report voice unavailable. Bundled worker code is project code, not model weights or third-party runtime binaries.

## Alternatives and self-review

Recompiling torch into the desktop would greatly increase dependencies and compromise process isolation; installing a full project into the voice runtime would mix environments and require external mutable source. A small hash-bound ZIP is simpler, deterministic and removable. The external interpreter is still an explicitly trusted runtime; hashes ensure release code consistency, not protection against an attacker able to replace the whole executable. No product-owner choice, paid account or system installation is required. Existing autonomous approval covers this design and inline implementation plan.

## Acceptance

Build fixture tests verify deterministic ZIP bytes, exact allowlist, staged embedded hash, fresh artifact placement and rejection of missing/linked inputs. Resolver tests cover modified/missing/oversized/linked ancestor/non-local ZIPs, absent digest, source fallback, and compiled fixed child command/env without leaking inherited secrets. Cancellation precedes resolution and never starts work. UI tests preserve compiled Kokoro failure, allow only verified compiled Qwen, and never probe torch or devices at construction.

Run old and new tests, independent review and real standalone rebuild. Use a public fixed sentence through a separately compiled verification entry point sharing the exact resolver/ZIP/adapter, produce only bounded PCM evidence without playback, and verify cancellation/reaping. Then repeat the actual app's default empty-profile headless smoke. Do not claim manual speech quality or automatic voice readiness merely because compilation passes. No model/runtime/binary publication. Record all remaining gates accurately.
