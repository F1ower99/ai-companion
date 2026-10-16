from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _run_app_script(tmp_path: Path, code: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["AI_COMPANION_TEST_DB"] = str(tmp_path / "stage5.sqlite3")
    env["LOCALAPPDATA"] = str(tmp_path / "local-app-data")
    source_root = str(Path(__file__).resolve().parents[2] / "src")
    env["PYTHONPATH"] = source_root + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
        check=False,
    )


def test_application_composes_local_chat_and_recovers_pending_without_resending(tmp_path):
    code = r'''
import os
from datetime import datetime, timezone
from pathlib import Path
from PySide6.QtWidgets import QSystemTrayIcon
QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: False)
from companion.application.chat_context import DailyChatContextBuilder
from companion.application.chat_service import ChatService
from companion.desktop.app import create_application
from companion.domain.chat import ChatMessage, ChatRole, Conversation, DeliveryState
from companion.infrastructure.openai_compatible import OpenAICompatibleProvider
from companion.infrastructure.sqlite.chat_repositories import SQLiteChatSettingsRepository, SQLiteConversationRepository
from companion.infrastructure.sqlite.database import SQLiteDatabase
from companion.infrastructure.sqlite.repositories import SQLiteCalendarRepository, SQLiteMemoryRepository, SQLiteTaskRepository
from companion.infrastructure.windows_credentials import WindowsCredentialStore

path = Path(os.environ["AI_COMPANION_TEST_DB"])
database = SQLiteDatabase(path)
database.initialize()
now = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
conversations = SQLiteConversationRepository(database)
conversations.add_conversation(Conversation("existing", now, now))
conversations.append_pending(ChatMessage(
    "pending", "existing", ChatRole.USER, "local pending body", now, DeliveryState.PENDING
))
app = create_application(["stage5-acceptance"], database_factory=lambda _path: SQLiteDatabase(path))
service = app.chat_service
assert isinstance(service, ChatService)
assert isinstance(service.conversations, SQLiteConversationRepository)
assert isinstance(service.settings, SQLiteChatSettingsRepository)
assert isinstance(service.memories, SQLiteMemoryRepository)
assert isinstance(service.tasks, SQLiteTaskRepository)
assert isinstance(service.calendar, SQLiteCalendarRepository)
assert isinstance(service.context_builder, DailyChatContextBuilder)
assert isinstance(service.provider, OpenAICompatibleProvider)
assert isinstance(service.secrets, WindowsCredentialStore)
assert app.chat_window.chat_service is service
assert service.conversations.get_message("pending").delivery_state is DeliveryState.FAILED
assert app.task_service is not None and app.reminder_service is not None
app.pet_window.close()
'''
    result = _run_app_script(tmp_path, code)
    assert result.returncode == 0, result.stderr


def test_chat_repository_failure_does_not_disable_tasks_or_reminders(tmp_path):
    code = r'''
from PySide6.QtWidgets import QSystemTrayIcon
QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: False)
import companion.desktop.app as app_module
from companion.domain.errors import StorageError
from companion.desktop.app import create_application

class BrokenConversationRepository:
    def __init__(self, _database):
        raise StorageError("private path and content must not appear")

app_module.SQLiteConversationRepository = BrokenConversationRepository
app = create_application(["stage5-chat-storage-failure"])
assert app.chat_service is None
assert app.task_service is not None
assert app.reminder_service is not None
assert app.chat_window.tasks_button.isEnabled()
assert app.chat_window.reminder_settings_button.isEnabled()
assert not app.chat_window.send_button.isEnabled()
assert "private path" not in app.chat_window.status_label.text()
app.pet_window.close()
'''
    result = _run_app_script(tmp_path, code)
    assert result.returncode == 0, result.stderr
