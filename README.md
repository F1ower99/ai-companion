# AI Companion

An experimental, local-first Windows companion for study planning and supportive conversation.

## Development setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m companion.desktop.app
```

The desktop shell provides a draggable, always-on-top pet and a chat panel. Right-click the pet to open chat or exit when Windows has no system tray; closing the pet exits the app, while closing chat leaves the pet running. The chat panel includes **Today's Tasks** and compact **Reminder Settings** entries.

## Local data and privacy

Goals, tasks, basic memories, reminder preferences, reminder state, reason-code events, academic terms, course rules, and calendar exceptions are stored in SQLite at `%LOCALAPPDATA%\AICompanion\companion.sqlite3` (normally under your Windows user profile). If the local database cannot be opened, the pet and chat shell still start, and task/reminder controls are disabled safely. Stage 3 adds a deterministic local decision engine, planned task times, quiet hours, cooldowns, snooze/extension/skip/completion actions, and a small non-modal reminder card. Activity sensing currently defaults to `unknown`; by design, ordinary reminders stay quiet until a future coarse activity source is added. Only a feasible, imminent P0 hard deadline may surface while activity is unknown. Stage 4 adds local academic-calendar persistence, deterministic course lookup with holiday/rest/makeup overrides, and a read-only study-day summary; it does not add calendar UI or import/sync. The app does not collect app names, window titles, keystrokes, or screen contents, and it does not connect to an LLM or send data to a service.

## Tests

From PowerShell, activate the development environment and run:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q
python -m compileall -q src tests
python -m pip check
```

The regression suite covers deterministic task decisions, SQLite migrations and reminder/calendar persistence, local-time resolution, the compact Qt reminder UI, course-week rules, calendar exceptions, and study-plan summaries. Full verification commands are listed above. Minimal activity awareness, provider-backed conversation, voice, packaging, and semantic memory search remain future work.
