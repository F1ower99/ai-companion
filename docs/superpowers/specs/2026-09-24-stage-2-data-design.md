# Stage 2 Design: Local Goals, Tasks, and Memory

Date: 2026-09-24

## Goal and boundaries

Stage 2 adds durable local records for long-term goals, daily tasks, and the five memory categories. The desktop shell will expose a small Today Tasks view backed by application services. SQLite remains an infrastructure detail; domain and application code do not import Qt or sqlite3.

Schema version 1 creates the seven tables named in the approved MVP roadmap: goals, tasks, memories, conversations, messages, settings, and reminders, plus a schema_migrations table. The latter tracks applied migrations. Conversations, messages, settings, and reminders are storage foundations only in this stage; their user-facing behavior is deferred to later stages.

All personal records stay on the local machine. The default database lives under the current user's LOCALAPPDATA directory in an AICompanion folder. Tests use temporary database files. Settings may contain ordinary preferences, never provider credentials. No activity monitoring, cloud sync, embeddings, or semantic search is added here.

## Approaches considered

1. Create only goals, tasks, and memories, then add other tables later. This minimizes unused schema.
2. Create all seven roadmap tables in migration 1, but implement repositories and UI only for goals, tasks, and memories. This keeps the published phase plan and persistence foundation aligned without pretending future behavior is already implemented.

The selected approach is option 2, matching the user's choice to follow the complete roadmap schema.

## Components and dependencies

- Domain models: immutable Goal, Task, and Memory data classes; Priority and MemoryKind enums; MemoryQuery filter value.
- Application service: TaskService validates task creation and progress changes and delegates persistence through repository interfaces.
- SQLite infrastructure: connection factory, ordered schema migrations, and repositories for goals, tasks, and memories.
- Desktop UI: a Today Tasks entry opens a task list and simple add/complete controls. The UI calls TaskService only; it contains no SQL and does not own business rules.
- Tests: domain/service tests use fake repositories where useful; repository and migration tests use temporary SQLite files and reopened connections.

## Version 1 schema

All identifiers are text UUIDs. Dates use ISO 8601 calendar dates. Timestamps use ISO 8601 UTC strings. Boolean values are stored as integers with checks. Foreign keys are enabled on every connection.

| Table | Fields and constraints | Stage 2 behavior |
|---|---|---|
| goals | id primary key; name required; target optional; priority 0–2; active boolean; created_at | Add, get, and list active goals. A task must reference an existing goal. |
| tasks | id primary key; title required; goal_id foreign key to goals; due_date; planned_minutes non-negative; completed_units non-negative; target_units optional and positive when present; priority 0–2; hard_start and hard_end optional with hard_end not before hard_start; status open/completed; created_at | Add, get, list for a date, update progress, and mark complete. |
| memories | id primary key; kind constrained to profile, preference, behavioral, episodic, or conversation; content required; source; importance 0–5; created_at; expires_at optional | Add, filter/search, and delete. Expired items are excluded from search by default. |
| conversations | id primary key; created_at; updated_at | Schema only. |
| messages | id primary key; conversation_id foreign key with cascade delete; role; content; created_at | Schema only; no chat transcript is written in Stage 2. |
| settings | key primary key; value; updated_at | Schema only for non-secret preferences. |
| reminders | id primary key; reason; created_at; cooldown_until; extension_deadline; status | Schema only; no reminder scheduler is implemented in Stage 2. |
| schema_migrations | version primary key; applied_at | Records each successful migration. |

The migration runs transactionally and is safe to call on every database open. A version already applied is not rerun. If migration fails, the transaction rolls back, leaving the previous schema intact. Future schema changes use new numbered migrations and never rewrite an already-published migration.

## Domain and service behavior

- Priority order is P0, P1, P2.
- Tasks for a day are ordered by priority, then deadline, then creation time, then id for deterministic ties. Tasks with no hard deadline sort after tasks with a deadline at the same priority.
- TaskService.add_task rejects blank titles, unknown goals, negative planned minutes, invalid time ranges, and invalid targets.
- TaskService.complete_units accepts a positive increment for a count-based task, rejects negative or zero increments, and clamps the result at target_units. It never changes another task's progress.
- TaskService.mark_completed completes a binary task directly and sets a count-based task's completed_units to target_units.
- Memory search supports optional text, kind, and source filters using SQLite text matching; results are ordered by importance and recency with an explicit limit. This is lexical filtering, not embedding search.
- Repository writes use transactions. Missing records raise a documented not-found error for mutation operations; add operations reject duplicate ids and invalid foreign keys with domain-facing errors.

## Error handling and privacy

Opening the database creates its parent directory and applies migrations. SQLite errors are translated at the repository boundary into stable application errors without including record contents or secrets in logs. If the database cannot be opened, the app remains usable and reports a clear local-storage error instead of crashing the desktop shell.

The database path and values are not logged. The settings table must reject reserved credential-like keys such as api_key or token; actual secrets will be handled by the later Windows Credential Manager adapter. Messages are not populated in this milestone. Deleting a goal with tasks is rejected; deleting a conversation cascades only to its messages.

## Acceptance criteria

1. Opening a fresh temporary database applies version 1 once and creates all seven roadmap tables plus migration metadata.
2. Reopening a second connection preserves goals, tasks, and memories.
3. Tasks cannot reference missing goals; progress updates affect only the addressed task; counts stay within 0 and target_units.
4. Day task lists have deterministic priority/deadline/creation ordering.
5. Memory searches honor kind, source, text, limit, and expiration; deletion removes only the addressed memory.
6. Every connection enforces foreign keys; migration failure rolls back.
7. The Today Tasks UI can add, display, and complete a task using TaskService. UI modules contain no SQL.
8. Existing desktop shell tests still pass; new domain and SQLite tests pass.

## Deferred work

Agent decisions, activity monitoring, reminders and extension scheduling, chat persistence behavior, provider keys, voice, academic calendar rules, cloud sync, embeddings, and semantic memory retrieval remain outside Stage 2.
