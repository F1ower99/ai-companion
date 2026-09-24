from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Callable

from PySide6.QtWidgets import QApplication

from companion.application.task_service import TaskService
from companion.domain.errors import StorageError
from companion.desktop.chat_window import ChatWindow
from companion.desktop.pet_window import PetWindow
from companion.desktop.tray import TrayController
from companion.infrastructure.sqlite.database import SQLiteDatabase, default_database_path
from companion.infrastructure.sqlite.repositories import (
    SQLiteGoalRepository,
    SQLiteTaskRepository,
)


def build_task_service(database: SQLiteDatabase) -> TaskService:
    return TaskService(
        SQLiteGoalRepository(database),
        SQLiteTaskRepository(database),
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

        factory = database_factory or SQLiteDatabase
        try:
            database = factory(default_database_path())
            database.initialize()
            self.task_service: TaskService | None = build_task_service(database)
            storage_error = None
        except StorageError:
            self.task_service = None
            storage_error = "本地数据暂时不可用，任务功能已停用。"

        self.chat_window = ChatWindow(self.task_service, storage_error)
        self.pet_window = PetWindow(self.chat_window)
        self.tray_controller = TrayController(self.pet_window, self.chat_window)
        self.pet_window.exitRequested.connect(self.quit)
        if self.tray_controller.icon is None:
            self.pet_window.closeRequested.connect(self.quit)
        self.pet_window.show()


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
