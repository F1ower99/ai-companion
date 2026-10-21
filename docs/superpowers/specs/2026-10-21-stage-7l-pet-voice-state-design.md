# Stage 7L: Character-first voice state feedback

Bounded continuation of Stage 7's Listening/Talking UI requirement and the approved character-first product direction. The existing vector pet stays the same size, position, identity and interaction; this is state feedback, not a visual redesign or new activity monitor. Current voice state is visible only in the chat labels. Let the companion itself reflect an explicit voice operation without opening another panel.

## Selected design

A tiny Qt-free reducer maps existing controller state strings to four ephemeral PetActivity values: IDLE, LISTENING, PROCESSING, SPEAKING. Actual capture `listening` wins; speech `playing` is next; STT `transcribing` or TTS `synthesizing` means PROCESSING. Permission, cancellation, error, unavailable and unknown states return IDLE. Pending permission must never look like actual recording. Cancellation stops the cue immediately even if an owned worker is still winding down.

A desktop QObject bridge connects optional voice/speech controller stateChanged signals to PetWindow.set_activity, reads initial state, and removes a destroyed controller before recomputing. It never starts/stops devices, reads speech content or drives scheduling. Application composition owns the bridge with the pet; existing controller lifecycle remains authoritative. Controller absence/default-off leaves the pet idle.

On pet destruction, explicitly disconnect source signals and release controller/pet wrapper references before Qt destroys the child bridge. Do not rely solely on parented QObject cleanup when the Python wrapper retains source references. Late callbacks see the detached guard and cannot touch the disposed character.

Keep the current vector artwork and idle appearance. Use a subtle collar cue for listening/processing and a small mouth change for speaking, with a static plain-text tooltip identifying the state. A low-frequency 150ms Qt timer advances only the visual frame while a non-idle pet is visible. Idle/hide stops that timer; show resumes only an active state. Animation never moves/resizes/raises the window, changes input transparency, opens chat, plays sound or creates notifications. It has no clock/repository/native audio dependency and stores no history.

Alternatives: a separate status window adds UI clutter; broad animation/assets work would exceed this slice. Reuse the existing vector paint path and a pure state reducer. This is independently reversible and does not bypass microphone or voice-quality acceptance.

## Acceptance and plan

Write RED tests for reducer precedence/permission/cancel/error fallback; actual pet state/timer behavior and visible rendered differences; bridge initial/live/destroyed optional controllers. Implement minimally, then wire the bridge in the real app and add a fake-controller/temp-profile composition check. Verify idle/hide use no animation timer and existing drag/click/tray behavior remains intact. Inspect public vector renders only, run complete regression/compileall/pip check/diff-secret checks, independent review, commit and normal push/merge under renewed authorization.

No microphone, speaker, model, window-title/input/screen monitoring, chat content, persistence, model download, automatic reminder speech or new dependency. Native microphone/quality/packaging experience remains a manual gate. Autonomous authorization covers the normal bounded-design checkpoint.
