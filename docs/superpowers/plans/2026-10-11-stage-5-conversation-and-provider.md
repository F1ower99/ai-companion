# Stage 5 Conversation and Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the disabled chat shell into a locally persisted, privacy-gated text conversation with an optional OpenAI-compatible provider.

**Architecture:** Keep domain/application code independent of Qt, SQLite, Win32, and HTTP. Add ports and deterministic services, then SQLite, HTTP, and Windows Credential Manager adapters; the Qt shell composes these adapters and runs synchronous chat sends on a worker.

**Tech Stack:** Python 3.10+, standard library, SQLite, PySide6 Essentials, pytest/pytest-qt; no new runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-10-11-stage-5-conversation-and-provider-design.md`

## Global Constraints

- No live provider call, credential acquisition, account authorization, or cloud upload during this session.
- Messages and settings stay in local SQLite; provider secrets stay only in Windows Credential Manager.
- Context switches for recent conversation, saved memories, and today’s plan default to off.
- The provider receives at most 12 prior messages, 5 memories, 12 open tasks, and 8 course occurrences.
- A request is at most 48,000 characters; prior messages are capped at 2,000 characters, memories at 500, task titles at 200, and course names at 120, with truncation identified in the prompt and consent disclosure.
- Stage 1–4 migration statements and deterministic task/reminder behavior remain unchanged.
- Domain/application code does not import Qt, SQLite, Win32, or provider SDKs.
- The HTTP adapter uses HTTPS, bounded requests/responses, a finite timeout, no redirects, no retries, no tools, and no streaming.

## Review Focus

- A restart during an in-flight send must not silently resend a possibly delivered user message; test pending recovery as failed/uncertain.
- A provider host or enabled context-category change must invalidate consent; test fingerprint changes and zero-call behavior until reconfirmed.
- URL redirects and malformed endpoints must not forward the API credential; test redirect rejection and URL validation.
- Cancellation after a blocking HTTP response must not append a late assistant turn; test service and Qt worker result handling.
- Unsupported Windows Credential Manager access must fail safely without plaintext fallback; test injected credential backend errors.

---

### Task 1: Chat Domain, Ports, and Injected Time

**Files:**
- Create: `src/companion/domain/chat.py`
- Create: `src/companion/ports/chat.py`
- Modify: `src/companion/ports/clock.py`
- Modify: `src/companion/ports/repositories.py`
- Modify: `src/companion/infrastructure/system_clock.py`
- Test: `tests/domain/test_chat.py`
- Test: `tests/infrastructure/test_system_clock.py`

**Interfaces:**
- Produce validated `Conversation`, `ChatMessage`, `ProviderConfiguration`, `ChatSettings`, `ChatContextPreferences`, `PersonalityProfile`, `PromptMessage`, `ChatRequest`, `ProviderCall`, `ChatResponse`, `ConsentDisclosure`, `ChatSendResult`, and typed chat/provider errors.
- `Clock.local_date() -> date` derives the date from the resolver’s current local aware datetime.
- `MemoryRepository.search(query, limit=5, *, as_of_utc=None) -> list[Memory]` keeps older callers compatible.
- Ports define conversation/settings/secret/provider protocols; provider call credentials are excluded from repr.

- [x] **Step 1: Write failing domain/port tests** for enums and validation, config timeout bounds, consent fingerprint determinism, secret-safe repr, and local-date forwarding. Memory expiry behavior is verified with the SQLite adapter in Task 2.
- [x] **Step 2: Run** `pytest tests/domain/test_chat.py tests/infrastructure/test_system_clock.py -q` and confirm the new assertions fail.
- [x] **Step 3: Implement** the domain values and protocols; add `SystemClock.local_date()` using `resolver.now_local().date()` and extend the MemoryRepository protocol.
- [x] **Step 4: Run** the focused tests and confirm they pass.

### Task 2: Additive SQLite v4 and Local Chat Repositories

**Files:**
- Modify: `src/companion/infrastructure/sqlite/migrations.py`
- Modify: `src/companion/infrastructure/sqlite/repositories.py`
- Create: `src/companion/infrastructure/sqlite/chat_repositories.py`
- Modify: `src/companion/infrastructure/sqlite/repositories.py` (memory expiry query)
- Test: `tests/infrastructure/test_sqlite_migrations.py`
- Create: `tests/infrastructure/test_sqlite_chat_repositories.py`
- Modify: `tests/infrastructure/test_sqlite_repositories.py`

**Interfaces:**
- `SQLiteConversationRepository.get_latest() -> Conversation | None` and `add_conversation(conversation) -> None`; `ChatService` creates IDs/timestamps through injected factories.
- `list_messages(conversation_id, *, limit=None, sent_only=False) -> list[ChatMessage]`
- `get_message(message_id) -> ChatMessage | None`, `append_pending(message)`, `mark_retry_pending(user_message_id)`, `complete_turn(user_message_id, assistant_message, updated_at)`, `mark_failed(user_message_id, updated_at)`, `recover_pending(updated_at)`, and `clear_conversation(conversation_id)`.
- `SQLiteChatSettingsRepository.get() -> ChatSettings` and `save(settings, updated_at) -> None`; secret values are rejected by the settings boundary.

- [x] **Step 1: Write failing migration/repository tests** for populated v3 upgrade, unchanged v1–v3 statements, default delivery state, atomic success, failure, stable order, pending recovery, clear cascade, settings round trip, and memory expiry using injected `as_of_utc`.
- [x] **Step 2: Run** the focused SQLite tests and confirm the new assertions fail.
- [x] **Step 3: Implement** additive migration v4 and repository methods using existing `SQLiteDatabase.connection()` transaction boundaries; do not modify v1–v3 statements.
- [x] **Step 4: Run** the focused SQLite tests and confirm they pass.

### Task 3: Deterministic Chat Service and Bounded Local Context

**Files:**
- Create: `src/companion/application/chat_service.py`
- Create: `src/companion/application/chat_context.py`
- Create: `src/companion/application/cancellation.py`
- Test: `tests/application/test_chat_service.py`
- Create: `tests/application/test_chat_context.py`

**Interfaces:**
- `ChatService.active_conversation() -> Conversation`, `consent_disclosure() -> ConsentDisclosure`, `grant_current_consent() -> None`, `send(conversation_id, user_text, cancellation_token) -> ChatSendResult`, `retry(user_message_id, cancellation_token) -> ChatSendResult`, and `clear(conversation_id) -> Conversation`.
- `retry()` moves the original failed user row back to pending and never creates a second user row; repository transitions reject retrying a row from another conversation or a non-failed state.
- `DailyChatContextBuilder.build(day: date, now_utc: datetime) -> DailyChatContext` uses task/calendar ports and the injected `Clock`; it includes at most 12 open tasks and 8 resolved course occurrences.
- `CancellationToken` is a thread-safe application abstraction without Qt.

- [x] **Step 1: Write failing fake-based tests** for no-secret/no-consent zero message writes and calls, success write ordering, explicit context opt-ins and bounds, expiry time injection, safe provider failures, same-row retry, pending recovery, cancellation after provider return, clear, and no reminder/task mutations.
- [x] **Step 2: Run** the focused application tests and confirm the new assertions fail.
- [x] **Step 3: Implement** pure prompt construction and `ChatService`; read one aware UTC instant and one injected local date per turn and pass the same instant to memory search.
- [x] **Step 4: Run** the focused application tests and confirm they pass.

### Task 4: Mockable OpenAI-Compatible HTTPS Adapter

**Files:**
- Create: `src/companion/infrastructure/openai_compatible.py`
- Test: `tests/infrastructure/test_openai_compatible.py`

**Interfaces:**
- `HttpTransport.post(url, headers, body, timeout, max_response_bytes) -> bytes` is injectable.
- `OpenAICompatibleProvider.complete(call: ProviderCall) -> ChatResponse` validates endpoint and payload, then maps all transport/provider errors to typed safe errors.

- [x] **Step 1: Write failing mocked-transport tests** for valid Chat Completions request shape, malformed/non-HTTPS/userinfo/query/fragment endpoints, response-size bounds, rejected redirects, status mapping, timeout, malformed/empty responses, and absence of credential/body in repr/errors.
- [x] **Step 2: Run** the focused provider tests and confirm the new assertions fail.
- [x] **Step 3: Implement** fixed-path HTTPS requests with a no-redirect urllib transport; never log request/response content.
- [x] **Step 4: Run** the focused provider tests and confirm they pass without network access.

### Task 5: Windows Credential Manager Adapter

**Files:**
- Create: `src/companion/infrastructure/windows_credentials.py`
- Test: `tests/infrastructure/test_windows_credentials.py`

**Interfaces:**
- `WindowsCredentialStore.get() -> str | None`, `set(secret) -> None`, and `delete() -> None` implement the `SecretStore` port through an injectable Win32 backend.

- [x] **Step 1: Write failing fake-backend tests** for missing credential, read/write/replace/delete, unsupported platform, Win32 error sanitization, and no plaintext fallback.
- [x] **Step 2: Run** the focused credential tests and confirm the new assertions fail.
- [x] **Step 3: Implement** generic Credential Manager calls under a stable product-scoped target; import/use Win32 APIs only in this adapter.
- [x] **Step 4: Run** the focused tests against fakes; do not touch a real credential target.

### Task 6: Provider Settings and Asynchronous Chat UI

**Files:**
- Create: `src/companion/desktop/provider_settings_dialog.py`
- Create: `src/companion/desktop/chat_worker.py`
- Modify: `src/companion/desktop/chat_window.py`
- Test: `tests/desktop/test_chat_window.py`
- Modify: `tests/desktop/test_tasks_dialog.py`
- Modify: `tests/desktop/test_reminder_card.py` only if shared-window setup requires assertions to move.

**Interfaces:**
- `ProviderSettingsDialog` edits base URL, model, timeout, independent context switches, personality, and password-masked secret; saving clears the secret field.
- `ChatWorker` runs one synchronous service call in `QThreadPool` and emits request ID plus typed result/error.
- `ChatWindow` takes optional chat service/settings dependencies, keeps a multiline draft, and ignores late results for cancelled/closed request IDs.

- [x] **Step 1: Write failing Qt tests** for missing-secret draft preservation and zero provider calls, explicit consent disclosure, pending/success/error/retry/cancel states, persistent payload summary, retry after restart and newer sends, clear confirmation, settings secret clearing, late-result suppression, and task/reminder control availability.
- [x] **Step 2: Run** the focused desktop tests and confirm the new assertions fail.
- [x] **Step 3: Implement** the compact transcript/composer, settings dialog, worker signals, and safe Chinese error copy without adding a dashboard.
- [x] **Step 4: Run** focused Qt tests with mocked providers and confirm the event loop remains responsive.

### Task 7: Application Composition and End-to-End Regression

**Files:**
- Modify: `src/companion/desktop/app.py`
- Modify: `tests/desktop/test_app_lifecycle.py`
- Create: `tests/application/test_stage5_acceptance.py`

- [x] **Step 1: Write failing wiring tests** for database-backed conversation/settings repositories, platform secret-store selection, single-instance locking before recover-pending, and chat storage failure not disabling task/reminder UI.
- [x] **Step 2: Run** the focused composition tests and confirm the new assertions fail.
- [x] **Step 3: Wire** all adapters in the application composition root; on non-Windows systems use a typed unavailable Credential Manager adapter and preserve all non-chat functionality.
- [x] **Step 4: Run** the focused composition tests and then the full suite: `pytest -q`.

### Task 8: Review, Verification, and Stage Commit

**Files:**
- Review: all Stage 5 changes and docs.
- Create: `docs/superpowers/tasks/2026-10-11-stage-5-conversation-and-provider.md`

- [x] **Step 1: Review** the full diff for spec coverage, dependency direction, consent invalidation, message delivery ambiguity, key leakage, migration immutability, and Qt result races; fix findings, including SQLite timestamp precision on clear, retry discovery after restart, and single-instance safety before crash recovery.
- [x] **Step 2: Run** `pytest -q`, `python -m compileall -q src tests`, `python -m pip check`, `git diff --check`, and a focused secret/debug artifact scan.
- [x] **Step 3: Review** staged diff and `git status`; verify no real credentials, private user data, or temporary artifacts are included.
- [ ] **Step 4: Commit** with `feat: add local conversations and optional text provider`.
- [ ] **Step 5: Record** the Stage 5 result in the overnight report and pause before live provider UX testing, which requires a real credential and deliberate user-sent content.
