# Stage 7I execution record

Spec/plan: `2026-10-20-stage-7i-memory-controls-design.md` and `2026-10-20-stage-7i-memory-controls.md`. Branch `codex/stage7i-memory-controls`, base `1ec63e9`; reuse existing isolated worktree. The roadmap explicitly requires local-memory deletion among privacy controls. User autonomous authorization permits inline execution without routine checkpoints.

Task 1: five repository tests failed on the missing offset parameter before implementation. Added backward-compatible keyword-only pagination, parameterized LIMIT/OFFSET and nonnegative integer validation. Existing ordering/default expiry behavior retained. Added Qt-free bounded MemoryManagementService/MemoryPage with one injected clock observation, 51-row lookahead for 50-row pages and targeted/idempotent deletion. Service tests first failed on the missing module, then passed with repository tests: 34 total.

Task 2: dialog tests first failed on the absent view. Implemented explicit opening, content/kind/expiry filters, paging, plain-text metadata/details, default-No single-record confirmation and clear-on-hide. Two added RED cases showed confirmation could survive hiding or refreshing; generation/visibility checks now cancel those stale operations. Row selection changes during confirmation cannot change the captured target ID. Storage errors are sanitized without falsely clearing a failed deletion.

Settings composition tests failed before the memory button/wiring existed, then passed. The button lives inside existing privacy settings; opening does not save unsaved provider edits or use credentials. App composition injects the existing repository/clock. Hiding chat hides settings and the memory panel, clearing displayed memory references.

Temporary SQLite/fake-provider integration verifies a deleted memory stays absent after reopening and cannot enter a subsequent saved-memory context. Management can see expired rows; chat still excludes expired rows. Initial fixture query did not match the repository's literal content search; corrected the test message to the common public keyword rather than weakening search semantics. All 69 targeted service/repository/chat/UI/lifecycle tests passed.

Ruling: use bounded offset pages with deterministic existing order, not an unbounded full-memory scan. Concurrent external edits can move page boundaries; refreshing recovers, and IDs—not row positions—select deletions. Empty nonzero pages return to page zero. Cost: this is not a cross-page transactional snapshot.

Ruling: existing conversations/provider copies are independent of memory deletion. Do not claim retrospective removal, physical SQLite erasure or automatic cleanup of already-started provider calls. No automatic memory creation or new SQLite migration.

Full regression: **696 passed in 12.98 seconds**, real Windows process with temporary data and fake devices. Compileall, pip check, diff and credential-pattern checks passed. Independent final review found no actionable findings and independently passed 46 service/dialog/repository tests. No personal database, private memory, microphone, credential store or network service was accessed by these tests.

Visual check: an initial sandbox/offscreen screenshot lacked CJK font glyphs. Rendered the same fixed-public-fixture panel through Windows Qt with WA_DontShowOnScreen (no desktop window displayed), then inspected the image: Chinese labels, list, detail, paging and delete/close controls fit the 460×540 panel. Used installed system fonts without redistributing them. No product font workaround was added for a test-environment limitation.

Stage commit `0aa8b0332a0b5e4420ddfd1468b9d75242137eea` normally pushed to `codex/stage7i-memory-controls` and fast-forwarded to main; remote hash verified. No private memory/database or screenshot was published; public-fixture visual artifacts remain local.
