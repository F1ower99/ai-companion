from __future__ import annotations

import sys
from collections.abc import Sequence

from PySide6.QtWidgets import QApplication

from companion.desktop.chat_window import ChatWindow
from companion.desktop.pet_window import PetWindow
from companion.desktop.tray import TrayController


class CompanionApplication(QApplication):
    def __init__(self, argv: Sequence[str]) -> None:
        super().__init__(list(argv))
        self.setApplicationName("AI Companion")
        self.setQuitOnLastWindowClosed(False)

        self.chat_window = ChatWindow()
        self.pet_window = PetWindow(self.chat_window)
        self.tray_controller = TrayController(self.pet_window, self.chat_window)
        self.pet_window.exitRequested.connect(self.quit)
        if self.tray_controller.icon is None:
            self.pet_window.closeRequested.connect(self.quit)
        self.pet_window.show()


def create_application(argv: Sequence[str]) -> QApplication:
    return CompanionApplication(argv)


def main(argv: Sequence[str] | None = None) -> int:
    app = create_application(sys.argv if argv is None else argv)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
