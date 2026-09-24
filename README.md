# AI Companion

An experimental, local-first Windows companion for study planning, activity awareness, and supportive conversation.

## Development setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m companion.desktop.app
```

The first milestone provides a draggable desktop pet, a system tray menu with mouse click-through, and a chat window shell. If Windows has no system tray, right-click the pet to open chat or exit; closing the pet exits the app, while closing chat leaves the pet running. Activity monitoring, LLM providers, tasks, memory, and voice will arrive in later milestones; nothing is collected in this stage.
