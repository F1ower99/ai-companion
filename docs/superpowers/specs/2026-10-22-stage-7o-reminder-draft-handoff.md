# Stage 7O: Explicit voice-draft handoff to a reminder

Status: autonomous session design; self-reviewed against Stage 7A/D/E/J and the original spoken-extension scenario.

## Intent and scope

Connect the existing local voice draft to the existing deterministic reminder proposal without changing capture ownership or creating an always-listening agent. The user records through the existing chat control, opens the current reminder's reply panel, explicitly chooses to fill it from the chat draft, previews the parsed action, then confirms. This is an incremental user-controlled bridge, not hands-free spoken command acceptance.

Goals: support the same draft whether dictated or typed; keep the task title visible; never parse or execute ordinary conversation automatically; retain hard-deadline, cooldown, extension and idempotency rules in ReminderService. Domain, Clock, repository and audio worker contracts remain unchanged.

Non-goals: new microphone controls in reminder windows, shared-controller routing, wake words, automatic speech, LLM command parsing, transcript persistence, application monitoring or improved Chinese STT accuracy.

## Options and choice

Routing an in-flight recording between chat and reminders requires ownership tokens, cancellation and cross-window lifetime changes. A separate reminder microphone introduces competing capture sessions. Prefer a pull of the existing draft only after a dedicated click: no new recording path, no asynchronous recipient ambiguity and no new dependency. This deliberately retains explicit preview and confirmation.

## UI and data flow

ChatWindow supplies a read-only draft callback to each ReminderCard; the card passes it to its transient ReminderReplyDialog. The optional callback defaults to absent for existing constructors. Only the explicit “填入聊天草稿” button invokes it. Creating/showing/closing a card or panel does not read the draft.

The button is absent when no callback exists. Help text explains that dictated text first appears in chat and filling does not send it. The original chat draft remains unchanged. Existing reminder reply text is preserved rather than overwritten; the user can clear it to request another fill. A non-string, empty/whitespace-only, over128-character value or callback failure gives a generic message without quoting draft or exception details. Validate length before assigning to the129-character QLineEdit, so an overlong transcript cannot be truncated into a valid command. Filling never parses, enables confirmation or submits an action. The user must choose Preview and Confirm using the existing parser and service.

The click handler requires an active visible non-busy panel; a dismissed/replaced parent invalidates it through existing lifecycle hooks. Edits continue to invalidate a prior proposal. No draft, transcript, callback error or audio is logged, saved to memory, sent to a provider or added to reminder events. Only the existing confirmed action is persisted.

## Failure and acceptance

Unavailable speech uses typed drafts. Speech errors and permission handling remain unchanged. An unrecognized draft receives the existing safe parser message after Preview; a service rejection retains the panel and task. Closing or replacing the reminder clears its temporary copy. The original chat draft survives transfer/cancellation and is only sent if the user later explicitly sends it.

Tests must prove lazy reads; preserved chat/existing reply drafts; empty/non-string/overlong/failing source rejection without truncation or private error echo; no action on fill or preview; explicit half-hour confirmation targets the displayed task once; dismissal prevents later pulls/actions; and an integration using VoiceTranscript through ChatWindow reaches the real panel without provider calls. Run existing reminder/voice/privacy tests and full regression, inspect diff, independent review, fix, commit. Actual microphone, Chinese accuracy and hands-free experience remain unaccepted.

Self-review: a pull does not broaden microphone consent, cannot redirect a late worker result, and leaves scheduling deterministic. The added control stays inside the temporary contextual panel rather than expanding the main dashboard. No schema or dependency change.

Implementation verified: thirteen new tests; full real-Windows suite904 passed,1 skipped,16.26s. Fresh-context review found no actionable findings. New standalone build completed in602.859s; `E:/AICompanionVoiceLab/build-lab/dist/build-9r__qov6/AICompanion.dist/app.exe` SHA-256 `d22847a4b1e4b705db14dbad34a963b29e01847242fc765c57094be32b59209b`. Fresh E-profile offscreen startup passed GUI subsystem2,16 tables,SQLite integrity and instance-lock checks; owned process terminated/reaped. No actual microphone, playback, normal-exit or GUI-driven action acceptance is inferred from this startup check. Source integration tests exercise the full draft-to-confirm path.
