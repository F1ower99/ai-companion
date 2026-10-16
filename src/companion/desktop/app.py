from __future__ import annotations

import sys
from collections.abc import Sequence
from uuid import uuid4
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QMessageBox

from companion.application.chat_context import DailyChatContextBuilder
from companion.application.chat_service import ChatService
from companion.application.activity_awareness_service import ActivityAwarenessService
from companion.application.proactive_reminder_service import ProactiveReminderService
from companion.application.task_service import TaskService
from companion.domain.errors import StorageError
from companion.desktop.chat_window import ChatWindow
from companion.desktop.pet_window import PetWindow
from companion.desktop.reminder_scheduler import ReminderScheduler
from companion.desktop.tray import TrayController
from companion.infrastructure.system_clock import SystemClock
from companion.infrastructure.openai_compatible import OpenAICompatibleProvider
from companion.infrastructure.sqlite.chat_repositories import (
    SQLiteChatSettingsRepository,
    SQLiteConversationRepository,
)
from companion.infrastructure.sqlite.activity_preferences import SQLiteActivityPreferencesRepository
from companion.infrastructure.sqlite.database import SQLiteDatabase, default_database_path
from companion.infrastructure.sqlite.repositories import (
    SQLiteCalendarRepository,
    SQLiteMemoryRepository,
    SQLiteGoalRepository,
    SQLiteReminderPreferencesRepository,
    SQLiteReminderRepository,
    SQLiteTaskRepository,
)
from companion.infrastructure.windows_credentials import WindowsCredentialStore
from companion.infrastructure.windows_activity import WindowsIdleActivitySource


def build_task_service(database: SQLiteDatabase, clock: SystemClock) -> TaskService:
    return TaskService(
        SQLiteGoalRepository(database),
        SQLiteTaskRepository(database),
        clock,
    )


def build_chat_service(database: SQLiteDatabase, clock: SystemClock) -> ChatService:
    tasks = SQLiteTaskRepository(database)
    calendar = SQLiteCalendarRepository(database)
    return ChatService(
        conversations=SQLiteConversationRepository(database),
        settings=SQLiteChatSettingsRepository(database),
        memories=SQLiteMemoryRepository(database),
        tasks=tasks,
        calendar=calendar,
        clock=clock,
        provider=OpenAICompatibleProvider(),
        secrets=WindowsCredentialStore(),
        id_factory=lambda: uuid4().hex,
        context_builder=DailyChatContextBuilder(tasks, calendar, clock),
    )


class CompanionApplication(QApplication):
    def __init__(
        self,
        argv: Sequence[str],
        database_factory: Callable[[Path], SQLiteDatabase] | None = None,
    ) -> None:
        super().__init__(list(argv))
        self.setApplicationName("AI Companion")
        self.setQuitOnLastWindowClosed(False)

        self.clock = SystemClock()
        factory = database_factory or SQLiteDatabase
        self.instance_lock: QLockFile | None = None
        self.startup_error: str | None = None
        database_path = default_database_path()
        try:
            database_path.parent.mkdir(parents=True, exist_ok=True)
            instance_lock = QLockFile(
                str(database_path.with_name("companion.instance.lock"))
            )
            if not instance_lock.tryLock(0):
                self.startup_error = "AI Companion 已在运行；为保护本地对话，请使用已有窗口。"
                return
            self.instance_lock = instance_lock
            self.aboutToQuit.connect(instance_lock.unlock)
        except Exception:
            self.startup_error = "无法安全取得本地数据锁；已阻止重复启动。"
            return

        self.chat_service: ChatService | None = None
        self.activity_awareness_service: ActivityAwarenessService | None = None
        chat_storage_error = None
        try:
            database = factory(database_path)
            database.initialize()
            self.task_service: TaskService | None = build_task_service(database, self.clock)
            self.activity_awareness_service = ActivityAwarenessService(
                WindowsIdleActivitySource(),
                SQLiteActivityPreferencesRepository(database),
            )
            self.reminder_service: ProactiveReminderService | None = ProactiveReminderService(
                self.clock,
                self.task_service,
                SQLiteReminderRepository(database),
                SQLiteReminderPreferencesRepository(database),
                activity=self.activity_awareness_service,
            )
            storage_error = None
        except StorageError:
            self.task_service = None
            self.reminder_service = None
            storage_error = "本地数据暂时不可用，任务功能已停用。"
        else:
            try:
                self.chat_service = build_chat_service(database, self.clock)
                self.chat_service.recover_pending()
            except StorageError:
                self.chat_service = None
                chat_storage_error = "本地对话存储暂时不可用。"

        self.chat_window = ChatWindow(
            self.task_service,
            storage_error,
            clock=self.clock,
            reminder_service=self.reminder_service,
            activity_awareness_service=self.activity_awareness_service,
            chat_service=self.chat_service,
        )
        if chat_storage_error:
            self.chat_window.status_label.setText(
                "本地对话存储暂时不可用；任务与提醒仍可继续。"
            )
        self.pet_window = PetWindow(self.chat_window)
        self.tray_controller = TrayController(self.pet_window, self.chat_window)
        self.pet_window.exitRequested.connect(self.quit)
        if self.tray_controller.icon is None:
            self.pet_window.closeRequested.connect(self.quit)
        self.pet_window.show()
        self.reminder_scheduler: ReminderScheduler | None = None
        if self.reminder_service is not None:
            self.reminder_scheduler = ReminderScheduler(self.reminder_service, self)
            self.reminder_scheduler.decisionReady.connect(self.chat_window.show_decision)
            self.chat_window.taskStateChanged.connect(self.reminder_scheduler.evaluate_now)
            self.chat_window.reminderEvaluationRequested.connect(self.reminder_scheduler.evaluate_now)
            self.reminder_scheduler.start()


def create_application(
    argv: Sequence[str],
    database_factory: Callable[[Path], SQLiteDatabase] | None = None,
) -> QApplication:
    return CompanionApplication(argv, database_factory=database_factory)


def main(argv: Sequence[str] | None = None) -> int:
    app = create_application(sys.argv if argv is None else argv)
    if getattr(app, "startup_error", None):
        QMessageBox.information(None, "AI Companion", app.startup_error)
        return 0
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
