# AI Companion

An experimental, local-first Windows companion for study planning and supportive conversation.

## Development setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m companion.desktop.app
```

The desktop shell provides a draggable, always-on-top pet and a chat panel. Right-click the pet to open chat or exit when Windows has no system tray; closing the pet exits the app, while closing chat leaves the pet running. The chat panel includes a **Today's Tasks** entry for local goals and tasks.

## Local data and privacy

Goals, tasks, and basic memories are stored in SQLite at `%LOCALAPPDATA%\AICompanion\companion.sqlite3` (normally under your Windows user profile). If the local database cannot be opened, the pet and chat shell still start, and the task entry is disabled with a status message. Conversation, settings, and reminder tables are present for later milestones, but this release does not persist chats, schedule reminders, collect app activity, or connect to an LLM. No data is sent to a service.

## Tests

From PowerShell, activate the development environment and run:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q
python -m compileall -q src tests
python -m pip check
```

The current stage has 85 passing tests. Activity monitoring, provider-backed chat, reminders, voice, and semantic memory search remain future work.
