from __future__ import annotations

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon

from companion.desktop.chat_window import ChatWindow
from companion.desktop.pet_window import PetWindow


class TrayController(QObject):
    """Owns the system tray icon and the pet/chat visibility actions."""

    def __init__(self, pet_window: PetWindow, chat_window: ChatWindow) -> None:
        super().__init__()
        self.pet_window = pet_window
        self.chat_window = chat_window
        self.icon: QSystemTrayIcon | None = None
        self.menu = self._create_menu()

        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        icon = QSystemTrayIcon(self)
        icon.setIcon(
            QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        )
        icon.setToolTip("AI Companion")

        icon.setContextMenu(self.menu)
        icon.activated.connect(self._on_activated)
        icon.show()
        self.icon = icon

    def _create_menu(self) -> QMenu:
        menu = QMenu(self.pet_window)
        open_chat = QAction("打开聊天", menu)
        open_chat.triggered.connect(self.show_chat)
        menu.addAction(open_chat)

        self.toggle_pet = QAction("隐藏桌宠", menu)
        self.toggle_pet.triggered.connect(self.toggle_pet_visibility)
        menu.addAction(self.toggle_pet)

        self.toggle_click_through = QAction("鼠标穿透", menu)
        self.toggle_click_through.setCheckable(True)
        self.toggle_click_through.toggled.connect(self.pet_window.set_click_through)
        menu.addAction(self.toggle_click_through)
        menu.addSeparator()

        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(quit_action)
        return menu

    def show_chat(self) -> None:
        self.chat_window.show()
        self.chat_window.raise_()
        self.chat_window.activateWindow()

    def toggle_pet_visibility(self) -> None:
        if self.pet_window.isVisible():
            self.pet_window.hide()
            self.toggle_pet.setText("显示桌宠")
        else:
            self.pet_window.show()
            self.toggle_pet.setText("隐藏桌宠")

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_chat()
