from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Callable

from PySide6.QtWidgets import QApplication

from companion.application.proactive_reminder_service import ProactiveReminderService
from companion.application.task_service import TaskService
from companion.domain.errors import StorageError
from companion.desktop.chat_window import ChatWindow
from companion.desktop.pet_window import PetWindow
from companion.desktop.reminder_scheduler import ReminderScheduler
from companion.desktop.tray import TrayController
from companion.infrastructure.system_clock import SystemClock
from companion.infrastructure.sqlite.database import SQLiteDatabase, default_database_path
from companion.infrastructure.sqlite.repositories import (
    SQLiteGoalRepository,
    SQLiteReminderPreferencesRepository,
    SQLiteReminderRepository,
    SQLiteTaskRepository,
)


def build_task_service(database: SQLiteDatabase, clock: SystemClock) -> TaskService:
    return TaskService(
        SQLiteGoalRepository(database),
        SQLiteTaskRepository(database),
        clock,
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
        try:
            database = factory(default_database_path())
            database.initialize()
            self.task_service: TaskService | None = build_task_service(database, self.clock)
            self.reminder_service: ProactiveReminderService | None = ProactiveReminderService(
                self.clock,
                self.task_service,
                SQLiteReminderRepository(database),
                SQLiteReminderPreferencesRepository(database),
            )
            storage_error = None
        except StorageError:
            self.task_service = None
            self.reminder_service = None
            storage_error = "本地数据暂时不可用，任务功能已停用。"

        self.chat_window = ChatWindow(
            self.task_service,
            storage_error,
            clock=self.clock,
            reminder_service=self.reminder_service,
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
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
