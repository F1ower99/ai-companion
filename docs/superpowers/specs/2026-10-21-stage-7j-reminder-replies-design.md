# Stage 7J: Deterministic contextual reminder replies

Purpose: implement the original “再给我半小时” interaction as a narrow, offline follow-up to Stage 3's deferred natural-language actions and the MVP's final reminder acceptance scenario. Do not add LLM scheduling or infer task actions from general chat. Existing autonomous authorization covers spec self-review, implementation and tests.

## Selected design

The automatic ReminderCard remains a non-modal, non-focus-taking window. Add one NoFocus “回复提醒…” button alongside existing actions. Only clicking that button opens a small keyboard-accepting reply panel. No input focus is taken by automatic reminder display, and no global keyboard/microphone monitoring is introduced.

A Qt-free parser accepts a deliberately limited complete-utterance grammar and returns an immutable structured proposal: NOW, LATER, EXTEND(minutes), SKIP_TODAY or DONE. Chinese/fullwidth normalization, ordinary spaces and terminal exclamation/full-stop punctuation are allowed; questions, negations, mixed commands, unsupported durations, control/format characters and oversized text are rejected. No substring matching, fuzzy intent, time-of-day scheduling or network fallback. The public UI examples describe this limited support.

Support exact action phrases such as 现在做/现在就做/马上做, 稍后/稍后提醒, 今天跳过 and 已完成/完成了/做完了. Extension verbs are 再给我/延长/再延长, optional 请 and 吧, followed by 1–120 minutes in Arabic/fullwidth or canonical Chinese numerals, or explicit half/one/one-and-half/two-hour forms. “稍后20分钟” is rejected rather than silently confusing configurable snooze with the one-time extension.

## Proposal and application lifecycle

1. Typing/Enter/preview only parses and displays an action summary. No repository or reminder-service write occurs.
2. User explicitly confirms the preview. Changing text invalidates the proposal. Unknown input keeps confirmation disabled.
3. Forward only enum/minutes through the existing ReminderCard submit/respond path. Existing injected Clock, hard deadlines, quiet hours, one-extension-per-day, cooldown, task status and idempotent state transitions remain authoritative. Parsing acceptance never promises the extension will be allowed.
4. Parent card dismissal/replacement/hiding invalidates and closes the reply panel. A stale/hidden panel cannot apply an action. Cancelling the reply closes only the reply panel, not the reminder itself.
5. Busy/double-click safeguards ensure one response. Service validation/storage errors remain sanitized and visible for retry; successful application closes the card and panel as before.

## Boundaries and privacy

Parser has no Qt, clock, repository or provider dependency. UI renders the proposal; scheduling policy stays in the existing service. Commands are bounded to 128 characters; the input holds at most 129 code units as an overflow sentinel, so a long paste cannot be silently truncated to an accepted ordinary command. Text and undo history are cleared on hide, and raw replies never enter chat/LLM, logs, SQLite events or memory. Only existing structured actions are persisted. General conversation semantics and voice-draft Send behavior are unchanged. No automatic speech or new dependency/schema.

## Verification

- Pure grammar tests: all five actions, 半小时, minutes/Chinese numerals, fullwidth, punctuation/space, 1/120 bounds, ambiguity/questions/negation/multi-action/control/oversize rejection.
- Qt tests: parent never requests keyboard focus; reply opens only on click; preview/Enter do not apply; explicit confirmation sends exact enum/minutes once; edited/stale/hidden/cancelled replies never mutate; existing service errors do not leak raw details.
- Fake-clock/temporary-SQLite acceptance: parsed 半小时 uses existing extension rules, persists once and re-enters decision evaluation after the deadline instead of mechanically repeating the old card.
- Full regression, compileall, pip check, diff/secret inspection and fresh independent review.

Self-review: a limited command grammar with preview is more reversible and testable than free chat interception or an LLM. Context is exactly the current reminder card. Deferred: arbitrary Chinese conversation, multi-task references, global chat actions, voice-to-action routing, time-of-day requests and LLM understanding. No product-owner decision needed to retain these boundaries.
