# Stage 7D execution record

Base: `790e161`; spec/plan dated 2026-10-19. User's autonomous approval applies. Reuse existing non-main isolated worktree; no merge or push.

Ruling: implement capture adapter as its own Stage 7 slice before interactive wiring. Qt lifecycle requires its owning thread; existing VoiceSession.stop_capture also runs synchronous STT. Cost: microphone UI stays disabled until a separate split-phase integration is implemented and tested.

Task 1 RED: new fake-backend tests failed on missing module. GREEN: bounded transfer, cancellation/zeroing, busy/retry, exact 60-second byte cap, real accelerated timer events, empty/odd PCM, typed failure cleanup, stale callbacks and thread checks pass. A reproducible multi-test Qt abort (cancel test followed by event-loop timer test) disappeared after explicitly disconnecting closure callbacks before deferred QObject deletion; keep this lifecycle regression in the suite.

Task 2 RED: six default-backend tests failed for the absent native boundary. GREEN: lazy optional runtime, permission before discovery, exact format, bounded native buffer, read forwarding, state errors and failed-start release tested with a fake multimedia module. No real microphone enumeration or sampling.

Self-review RED/GREEN: two reentrant completion tests exposed an old deadline stopping the recording started by a completion handler and an explicit stop emitting automatic completion. Recheck generation after draining and suppress automatic notifications for explicit stop. All 22 capture tests pass.

Full baseline plus initial adapter suite: sandbox run had 11 pre-existing STT temporary-directory PermissionError failures; approved local regression run passed all 490 tests. No production path/model checks were relaxed. Two self-review tests were added afterward; final full count pending.

Ruling: unsupported 16-kHz mono PCM16 devices fail safely rather than introducing resampling now. Cost: compatibility needs user-led hardware validation before activation. No Chinese accuracy sign-off, TTS or packaged acceptance is claimed.

Final independent review: two Important findings, no Critical/Minor. Both reproduced with three failing tests: a failed start retired a failure-handler retry; a failed read appended old PCM to the retry, or its old exception retired the retry. One fix pass now guards startup cleanup, each read result/exception and explicit-stop cleanup with recording generation/driver ownership. All 25 capture tests pass after fixes; final full regression follows.

Review rulings: the normal byte/frame/cancel/busy/timer/stale callback/thread/permission/format/error paths are supported and tested. Externally deleting private Qt objects is outside the adapter lifecycle; accepting arbitrary extensions would need additional defensive ownership rules. Native importability, device compatibility, permission UX, OS buffering, hardware teardown and timer latency under a blocked event loop require runtime/manual validation; a Qt timer is not a hard real-time device cutoff, while the application PCM byte cap remains enforced. UI/worker integration, Chinese accuracy, resampling, TTS, packaging and persistence stay in separate slices. Cost: voice controls cannot yet be enabled or claimed usable.

Binding inspection: local official QtMultimedia.pyi confirms QAudioSource constructor/start/read lifecycle, setBufferSize and QtAudio.Error names for the pinned Qt series; no devices were queried. Optional PySide6-Addons 6.11.2 download (168 MB) remained unfinished after six minutes and its exact task-owned pip processes were stopped. No package installation success or native importability claimed. Existing installed metadata was not changed; pip check is repeated below.

Final verification after the one review fix pass: **495 tests passed**, including 25 new capture tests; compileall (src/scripts/tests), pip check and staged whitespace checks passed. Staged files inspected: no secrets, model weights, temporary files, debug output, network/SQLite coupling or hardware activation. Implementation and evidence committed independently; exact hash is in Git and the Stage 7 report follow-up. No remaining reviewer Minor for this slice; prior Stage 7C WAV-tail Minor remains deferred.
