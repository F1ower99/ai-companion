# Stage 5 Design Spec: Local Conversation and Optional Text Provider

Date: 2026-10-11
Status: Authorized for autonomous implementation in the overnight development session

## Purpose

Stage 5 turns the existing disabled chat shell into a persistent text conversation with an optional, explicitly configured OpenAI-compatible provider. Conversation storage remains local. No provider is called until the user configures a provider and secret, reviews what may be sent, and presses Send. Provider-backed language never decides reminders, changes task state, or gets tools that can perform actions.

This design follows the existing roadmap while narrowing its proposed automatic “summary event”: Stage 5 stores conversation messages locally but does not promote chat text into permanent Memory records. Automatic summaries and memory extraction need the importance, source, expiry, deduplication, replacement, and deletion policy already required by the product’s memory principles; they are deferred rather than silently creating durable personal memories.

## Goals

- Persist a resumable text conversation in the existing `conversations` and `messages` tables.
- Define provider-neutral chat request, response, cancellation, and typed error interfaces.
- Add one OpenAI-compatible HTTP provider using standard-library HTTPS, with bounded timeouts and sanitized failures.
- Store provider settings and personality preferences in ordinary local settings; store the provider secret only in Windows Credential Manager.
- Let the user choose whether recent conversation, up to five relevant memories, and today’s task/course summary are sent with each message.
- Keep Qt responsive while a provider call is running; test all behavior offline with fake providers and mocked transport.
- Preserve dependency direction: domain/application do not import Qt, SQLite, Windows APIs, or provider SDKs.

## Non-goals

- No live API call, account authorization, API-key acquisition, or cloud upload during this development session.
- No LLM-based reminder decisions, task mutations, tool/function calling, voice, streaming, activity monitoring, or calendar synchronization.
- No automatic conversation summarization, memory extraction, vector database, or full-history upload.
- No conversation list/search UI; the desktop resumes one active conversation and lets the user clear it.
- No non-HTTPS remote endpoint or embedded username/password in a provider URL. Local-model transports are a later adapter.

## Existing architecture and constraints

- `ChatWindow` is a small Qt dialog with a disabled `QLineEdit` and no transcript. It already hosts Today Tasks and Reminder Settings.
- SQLite migration v1 already creates `conversations(id, created_at, updated_at)` and `messages(id, conversation_id, role, content, created_at)`; these tables are empty and have no repositories yet.
- `settings` is for non-secret values and its v1 CHECK rejects keys containing `api_key`, `token`, `secret`, or `password`.
- `SQLiteMemoryRepository.search` currently reads `datetime.now()` to filter expiry. ChatService must pass its injected UTC instant into memory search; it must not rely on repository wall time.
- Stage 1–4 migration statements are published and immutable. Any conversation delivery state requires additive migration v4.
- Stage 3 remains the sole authority for reminder choices, hard deadlines, cooldowns, and extensions. Stage 5 supplies no model-to-action bridge.

## Design decisions

1. **Keep `ChatService.send` synchronous and run it off the UI thread.** The application service stays directly testable with fake repositories/provider/clock. A Qt worker owns the synchronous call, reports a typed result through signals, and never blocks the event loop. The UI allows one in-flight turn per conversation.
2. **Use the Chat Completions wire shape for the first OpenAI-compatible adapter.** It is broadly implemented by compatible providers and matches this text-only MVP. The transport sends one non-streaming completion, no tools, and no remote conversation ID. The adapter can later add a Responses implementation behind the same port. OpenAI currently recommends Responses for new OpenAI-only projects, while its documented Chat Completions endpoint accepts a message array and returns `choices[].message`; this project’s compatibility target is the reason for this choice. [OpenAI Chat Completions API reference](https://platform.openai.com/docs/api-reference/chat/object?lang=ruby)
3. **Local transcript is the source of conversation continuity.** Only the most recent 12 prior messages may be sent, and only when the user enables that context option. There is no remote conversation-state API or full-history upload.
4. **Context sharing is explicit and separate by category.** The current message is sent only after a visible disclosure/consent gate. Recent transcript, retrieved memories, and today’s task/course summary each have independent opt-in switches, defaulting off. The local response-language, tone, and principles settings are always included in provider instructions and are named alongside the current host and selected categories near Send and in consent.
5. **Do not auto-write chat into Memory.** Existing user-authored memory may be retrieved by lexical search, up to five items, only when the memory-sharing switch is enabled. Stage 5 does not generate or retain a conversation summary.
6. **A failed or interrupted turn remains visible locally.** User messages enter SQLite as `pending`, then transition to `sent` or `failed`. A crash-recovered pending message is shown as “delivery status unknown”; it is not automatically resent. Retry is a separate user action and may incur a second provider request if the first request completed remotely but its response was lost.
7. **Keep cleared conversations fresh and failed turns retryable.** Clear creates a new local conversation even if older conversation rows remain; its update timestamp advances by one millisecond when necessary because SQLite `julianday` ordering does not reliably distinguish adjacent microseconds. Transcript refresh exposes the latest failed user row for retry, including rows recovered after restart, and exposes earlier failed rows as later retries resolve.
8. **Recover interrupted sends only in one application process.** The Qt composition root holds a per-user-data-directory `QLockFile` before database initialization or pending-message recovery. A second process stops before touching the database, so it cannot mark a live provider request as crashed. The lock releases when the application exits.

## Domain and port model

### Conversation records

- `Conversation(id, created_at, updated_at)` is an immutable local record.
- `ChatMessage(id, conversation_id, role, content, created_at, delivery_state)` is immutable. `role` is `user` or `assistant`; delivery state is `pending`, `sent`, or `failed`.
- IDs are generated by an injected ID factory. UTC timestamps come from the injected `Clock`; the service never calls the operating-system clock directly.
- Add `Clock.local_date() -> date`, implemented from the existing local-time resolver, so prompt context uses the user’s local day without calling `date.today()`.
- One active conversation is resumed at startup. “Clear conversation” deletes that conversation and its messages locally, then creates a fresh empty conversation.

### Personality and context

- `PersonalityProfile` contains a response language, tone, and short set of principles. It is stored in local settings and rendered into provider instructions; it does not change deterministic decision behavior.
- `ChatContextPreferences` contains independent booleans for recent history, saved memories, and today’s plan. All default to `False`.
- `DailyChatContext` is a bounded, read-only snapshot built from the local task and calendar repositories for the injected local date and UTC instant. It includes only open tasks, estimated remaining minutes, hard-deadline status, and matching course names/times. It contains no application activity, window title, screen, keystroke, or raw database data.
- `ChatRequest` contains configured model, a bounded ordered message list, timeout, and a cancellation token. The provider receives no repository, task mutation service, reminder service, or desktop object.
- `ChatResponse` contains validated non-empty assistant text and optional non-sensitive model metadata. Raw HTTP response bodies and provider diagnostics are not returned to the UI or logs.
- `LLMProvider.complete(request) -> ChatResponse` may raise typed `ProviderError` subtypes: not configured, cancelled, timeout, authentication, rate limited, unavailable, invalid response, and configuration error.
- `ConversationRepository`, `SettingsRepository`, `MemoryRepository`, `SecretStore`, and `Clock` are protocols; `ChatService` depends on these abstractions only.

## Inputs and prompt bounds

`ChatService.send(conversation_id, user_text)` validates a nonblank message with a maximum of 8,000 Unicode characters, verifies that provider configuration and the secret exist, and reads one injected UTC instant and local date. No user message is persisted when provider setup is missing or invalid.

The prompt contains:

- one developer/instructions message rendered from the local personality profile and a clear rule that the model may only reply with text;
- the current user message;
- at most 12 prior sent user/assistant messages when recent-history sharing is enabled;
- at most 5 lexical memory matches when memory sharing is enabled, using the same injected UTC instant to exclude expired memories;
- at most 12 open tasks and 8 course occurrences when today-plan sharing is enabled.

The current user message is limited to 8,000 characters. To bound the whole request to 48,000 characters, each prior transcript item is limited to 2,000 characters, each memory excerpt to 500 characters, task titles to 200 characters, and course names to 120 characters. Any excerpt shortened for these limits carries an explicit truncation marker in the prompt; the consent disclosure also describes the same limits. Excluded context is never silently added elsewhere. The prompt builder is pure and tested with fixed inputs. It does not append the full SQLite transcript or entire memory table.

## Send and retry lifecycle

1. The UI displays the configured provider host and which context switches are active next to Send. The first send after provider configuration requires an explicit disclosure confirmation naming the current message, enabled context categories, and the always-included local reply-language, tone, and principles settings. Changing provider host or enabled context categories requires the disclosure to be shown again.
2. If configuration/secret is absent, the UI preserves the draft and opens Provider Settings. No network call and no transcript write occurs.
3. ChatService validates the request, snapshots clock and selected local context, creates a `pending` user message, and commits it locally before provider execution.
4. The provider makes one HTTPS request with a finite configured timeout, no retries, no streaming, and no tools. A cancellation token is checked before send and after the bounded blocking request; cancellation does not promise to abort an already-blocked socket immediately. If cancellation is observed, the user row is persisted as failed/possibly delivered and no assistant turn is stored. A result that finishes after the chat window closes refreshes local state without replacing any newer request.
5. On success, one repository transaction marks the user message `sent`, stores the assistant message as `sent`, and updates `conversations.updated_at`.
6. On a typed provider failure, the service marks the user message `failed` and returns a safe error code. It does not expose the key, raw response body, prompt, URL query, or local database path. The UI preserves the draft and offers an explicit retry. Failed user rows remain retryable after unrelated sends; the single Retry action selects the most recent failed row, then exposes the next one after it resolves.
7. If the process restarts with `pending` messages, repository recovery changes them to `failed`; transcript refresh exposes them to the same explicit retry action and explains that remote delivery is uncertain.
8. No automatic retry, memory write, reminder change, task mutation, or remote conversation persistence occurs.

## Persistence changes

- Migration v4 adds `messages.delivery_state TEXT NOT NULL DEFAULT 'sent' CHECK(delivery_state IN ('pending', 'sent', 'failed'))`, preserving all v1–v3 migration definitions and existing rows.
- `SQLiteConversationRepository` creates/loads the most recent conversation, appends and lists messages in stable `(created_at, id)` order, updates delivery state, performs atomic successful-turn updates, recovers pending sends, and clears only the requested conversation. ChatService creates a fresh conversation after clear and advances its logical update timestamp by one millisecond if needed so another remaining row cannot immediately become active again under SQLite ordering precision.
- Settings use namespaced non-secret keys for model, HTTPS base URL, timeout, context switches, consent fingerprint, and personality fields. The consent fingerprint binds approval to the normalized provider host plus enabled context categories.
- `WindowsCredentialStore` uses a stable product-scoped Credential Manager target name. The secret is never copied to SQLite/settings, logs, error text, prompts, or test fixtures. Replacing/deleting affects only this product’s target.
- `MemoryRepository.search` accepts an optional explicit `as_of_utc`; ChatService always supplies it. Existing callers remain source-compatible.

## HTTP provider boundary

- The endpoint is constructed from a validated HTTPS base URL and a fixed `/chat/completions` path. Reject URL user-info, query, fragment, non-HTTPS scheme, and malformed host/path. Display the normalized hostname before the first send.
- Send only JSON request content, `Authorization: Bearer ...`, and `Content-Type: application/json`. Redirects to another host are rejected so credentials cannot be forwarded to an unreviewed destination.
- Bound request body and response bytes; use the configured finite timeout. Map 401/403, 429, network/5xx, timeout, malformed JSON, missing `choices`, and empty assistant content to typed safe errors. Do not log request or response bodies.
- Provider transport is injectable for tests. No test calls an external endpoint; HTTP behavior is verified with a mocked transport and fake payloads.

## UI interaction

- Keep the existing character-first chat window compact. Add a small scrollable transcript, multiline composer, Send/Cancel/Retry state, Provider Settings, and Clear Conversation. No task dashboard is added.
- Provider Settings edits endpoint, model, timeout, context-sharing switches, and personality; the API key control is password-masked and cleared after saving. A “test connection” action is excluded because it would send a network request outside an explicit chat send.
- Without a saved secret, the composer can hold a draft but Send opens settings and explains that nothing was sent. The reminder/task entry points remain available if chat configuration fails.
- A worker result is applied only if it matches the active conversation and request ID; closing the chat panel does not stop the pet or mutate task/reminder state.
- The application acquires a single-instance lock before startup recovery. If another process owns the data directory, the second process exits before running recovery.
- Clearing chat requires a local confirmation and does not touch goals, tasks, memories, provider settings, or Windows credentials.

## Failure handling

- SQLite open/write errors follow existing `StorageError` degradation: pet and task/reminder UI remain available; chat becomes disabled with a safe local-storage message.
- Credential Manager unavailable, unsupported platform, or secret read/write failure returns typed settings errors and never falls back to plaintext storage.
- Failure to acquire the single-instance lock blocks startup before pending-send recovery; it never takes ownership or edits another process's lock.
- Missing key, invalid endpoint/model, cancellation, timeout, auth rejection, rate limit, malformed response, and empty response have distinct safe UI messages. A failed turn remains locally retryable.
- Provider exceptions are sanitized at the adapter boundary; logs contain only a stable error code and request ID.

## Privacy boundaries

- This autonomous development session performs zero provider calls and transmits no conversation/task/memory data to an external service.
- At runtime, only a user-configured host receives data. The current message, always-included local reply-language/tone/principles settings, and the three independently controlled context categories are visible in the persistent send-area summary and consent disclosure; the optional categories default off.
- Conversation rows and settings stay in the existing local SQLite database. No raw transcript is written to logs, memories, crash messages, or cloud storage by this app.
- The app cannot promise how a selected provider handles received content; its host is displayed and the user must explicitly confirm before the first send for a given consent fingerprint.
- API keys remain in Windows Credential Manager. Tests use fake secrets only and never a real key.

## Test strategy

- Domain tests cover message/profile/config validation, role/state enums, prompt size limits, bounded context, stable ordering, aware time, and consent fingerprint invalidation.
- ChatService tests use fake clock, fake IDs, repositories, memory, context builder, secret store, and provider; cover success, missing key no-write/no-call, message persist ordering, memory cap/expiry time injection, timeout/auth/empty response, cancellation, retry without duplicate user row, recovery of pending messages, and no task/reminder mutations.
- Migration/repository tests cover v4 upgrade from a populated v3 database, unchanged v1–v3 statement tuples, defaults for existing message rows, atomic successful turn, failure state, stable ordering, clear cascade, and reopen persistence.
- Credential Manager tests stub Win32 APIs and cover read/write/replace/delete/error sanitization without touching a real credential store.
- HTTP adapter tests mock transport and cover URL validation, Authorization header without logging, request shape, response parsing, redirects, timeout, status mapping, malformed/empty response, and response-size limits.
- Qt tests cover missing-secret configuration prompt with zero provider calls, responsive pending/cancel/retry states, safe sanitized errors, persistent host/context/personality disclosure, retry after restart and unrelated successful sends, conversation clear, single-instance lock ownership before recovery, and that reminder/task controls still work.
- Full Stage 1–4 regression, compileall, pip check, diff whitespace check, secret scan, and independent read-only review run before the Stage 5 commit.

## Acceptance criteria

1. The active conversation and user/assistant messages survive app restart and can be cleared locally without affecting other data.
2. No key means no message persistence for a new send and zero provider calls; the composer draft remains available.
3. A configured send persists a local pending user message, then atomically records the successful user/assistant turn; failure is safe, visible, and explicitly retryable.
4. At most 12 prior messages, 5 memories, 12 tasks, and 8 courses enter a request, and each category is excluded unless opted in.
5. Clock, ID generation, repositories, and provider are injectable; application/domain tests require no Qt, SQLite, system clock, Windows API, external network, or LLM.
6. Qt stays responsive during provider work; cancellation/error/late worker results do not mutate reminder/task state or show secrets.
7. Provider secrets appear only in Windows Credential Manager. The host and all outgoing payload classes, including reply-personality settings, are visible and explicitly confirmed before sending.
8. Stage 1–4 behavior remains intact and all tests pass.

## Deferred work

Live credential entry and real provider UX testing, additional provider APIs (including Responses), local model adapters, streaming, conversation list/search/export, automatic summary and memory extraction, tool/function calling, LLM-based reminder wording, voice, activity awareness, embeddings, and cloud sync remain deferred. A real provider call requires the user to supply a credential and deliberately test sending their own chosen message/context; this session will stop before that action.
