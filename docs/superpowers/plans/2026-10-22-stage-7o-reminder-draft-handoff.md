# Stage 7O implementation plan

> Execute inline with superpowers:executing-plans; user authorized autonomous checkpoints.

Goal: explicitly pull a local voice/chat draft into the current reminder's existing preview/confirm flow.

Architecture: optional read-only callback from ChatWindow through ReminderCard to ReminderReplyDialog. No change to voice routing, parser, service, clock or storage. PySide6 only; no dependencies.

## One bounded deliverable

- [x] Add failing tests in `tests/desktop/test_reminder_reply_dialog.py` for lazy optional pull, no action/preview on fill, length/type/error rejection, preservation and invalidation. Add ChatWindow/VoiceTranscript-to-card integration using existing fake task/reminder services.
- [x] Observe RED before implementation.
- [x] Extend `ReminderReplyDialog.__init__` with keyword-only `draft_source=None`; optional contextual button, plain help copy and guarded `_fill_from_draft`. Preserve text, reject unsuitable values before setText; never parse automatically.
- [x] Extend `ReminderCard.__init__` with keyword-only `draft_source=None` and pass it only when constructing the panel. In `ChatWindow.show_decision`, supply its existing composer `toPlainText` callback.
- [x] Run targeted then complete real-Windows offscreen regression; review diff and independent review; repair and repeat only as needed.
- [x] Update roadmap/report/acceptance ledger honestly; commit and normal push after verified checks. No new compiled-build acceptance is implied by prior artifacts.

Verification: 11 new cases first failed for missing callback/button; minimal three-file implementation passed the41 targeted reminder cases. Two additional lifecycle/privacy cases added. Full regression904 passed,1 skipped (symlink privilege unavailable),16.26s; compileall/diff check passed. Fresh-context branch review: no actionable findings. Public-example offscreen panel rendering inspected using the installed Windows Chinese font only in the QA harness; no font installed/bundled or product default changed. Formal desktop build passed in602.859s; new-profile default-off startup/integrity/lock checks passed. No real microphone or playback.

Integration: stage commit f83b9196d16f6211352a3a72d84b6e8d617065ca normally pushed to the stage branch and main; remote main hash verified. No force push or binary release.
