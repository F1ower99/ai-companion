# Stage 7I: Local memory inspection and deletion

Purpose: complete the existing MVP privacy-control requirement to inspect/delete saved memories. Stage 2 already persists five memory kinds and Stage 5 can explicitly include saved memories in provider context; the desktop currently exposes no inspection/deletion surface. User autonomous authorization covers this focused follow-up.

## Chosen approach

Use a temporary dialog opened from the existing model/privacy settings. Avoid another main-window toolbar control or a dashboard. Reuse the memory repository and injected clock via a Qt-free MemoryManagementService. No schema migration, dependency, automatic extraction, embedding, cloud access, memory creation/editing or bulk deletion.

## Domain/service and persistence

MemoryPage is an immutable snapshot of at most 50 Memory records, an aware UTC observation time, an offset and a has-next flag. Service list_page validates query/offset, samples its injected clock once and requests 51 rows for bounded lookahead. Search uses existing literal text/kind filtering; management includes expired records by default so expiration never hides stored data from deletion.

Add a backward-compatible keyword-only `offset=0` to MemoryRepository.search and its SQLite implementation. Validate nonnegative integer offsets, retain deterministic importance/created_at/id ordering, and parameterize LIMIT/OFFSET. Existing chat calls keep offset zero and their existing expiry rules. No decision or UI logic enters SQLite.

Deletion targets only the captured selected record ID. User must confirm one item; default answer is No. NotFound means already gone, followed by refresh; storage failure retains a truthful failure state. Deletion affects subsequent context construction, not requests already started, conversation messages that may quote a memory, external copies or physical SQLite erasure.

## UI

The provider settings has an independent “管理本地记忆” button enabled only with a memory service. It opens a compact search/list/detail dialog, with kind filter, include-expired toggle, previous/next paging and one delete button. Loading occurs only on explicit opening/refresh/search; no background polling. Filtering resets the page. Source/content are always plain text, never rich HTML. Metadata exposes kind, source, importance and expiration without logging them.

Reload clears previous selection/details before reading. Delete failures do not claim success; a concurrently missing item is refreshed. If deletion empties a nonzero page, return to page zero. Hide clears the in-memory list/details; reopen fetches fresh state. Hiding settings also hides the memory dialog. No actual personal database is used in development/tests.

App composition injects MemoryManagementService with the existing SQLiteMemoryRepository and Clock. UI never imports SQLite or calls the system time. Missing storage/service disables inspection safely. Existing provider form edits are not saved by opening or deleting memories; no credential read or network request is needed.

## Tests and acceptance

- Repository pagination is deterministic, parameterized and rejects invalid offsets; existing retrieval semantics remain unchanged.
- Fake clock/repository prove fixed-size lookahead, expiry options, query propagation, page state, invalid clock/input and targeted/idempotent deletion.
- Qt tests cover explicit loading, plain-text details, paging/filter reset, cancel/confirm, stable selected ID, errors, missing records, hide clearing/reopen and settings composition.
- Temporary SQLite integration proves deletion persists after reopen and removed rows do not enter later saved-memory provider context; expired management visibility does not alter chat expiry filtering.
- Full regression, compileall, pip check, diff/secret checks and independent review pass. No actual memory is deleted and no microphone/network/provider is accessed.

Deferred: adding/editing memories, auto extraction/dedup/replacement, semantic search, export, forensic secure erase, retention rules and batch deletion. Self-review: this is user-controlled local inspection of existing data, not a new automatic memory system. The old provider-context consent still governs any future send.
