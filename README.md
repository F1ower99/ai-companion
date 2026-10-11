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

Goals, tasks, basic memories, reminder preferences, reminder state, reason-code events, academic terms, course rules, calendar exceptions, conversations, and provider settings are stored in SQLite at `%LOCALAPPDATA%\AICompanion\companion.sqlite3` (normally under your Windows user profile). Provider credentials are stored separately in Windows Credential Manager. If the local database cannot be opened, the pet and task/reminder controls remain available safely; chat is disabled when its storage is unavailable. Stage 3 adds a deterministic local decision engine, planned task times, quiet hours, cooldowns, snooze/extension/skip/completion actions, and a small non-modal reminder card. Activity sensing currently defaults to `unknown`; by design, ordinary reminders stay quiet until a future coarse activity source is added. Only a feasible, imminent P0 hard deadline may surface while activity is unknown. Stage 4 adds local academic-calendar persistence, deterministic course lookup with holiday/rest/makeup overrides, and a read-only study-day summary; it does not add calendar UI or import/sync. Stage 5 adds a local transcript and an optional OpenAI-compatible text provider. No request is made until the user configures an HTTPS provider and local credential, reviews the visible host and outgoing content, and sends a message. Recent conversation, saved memories, and today's plan are independently opt-in; reply language, tone, and principles are included with provider requests. The app does not collect app names, window titles, keystrokes, or screen contents.

## Tests

From PowerShell, activate the development environment and run:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q
python -m compileall -q src tests
python -m pip check
```

The regression suite covers deterministic task decisions, SQLite migrations and reminder/calendar/chat persistence, local-time resolution, the compact Qt reminder UI, course-week rules, calendar exceptions, study-plan summaries, and offline provider request/error handling. Full verification commands are listed above. Live provider UX testing, minimal activity awareness, voice, packaging, and semantic memory search remain future work.
