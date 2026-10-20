from __future__ import annotations

from PySide6.QtCore import QObject, QSignalBlocker, Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon

from companion.desktop.chat_window import ChatWindow
from companion.desktop.pet_window import PetWindow
from companion.application.startup import StartupError


class TrayController(QObject):
    """Owns the system tray icon and the pet/chat visibility actions."""

    def __init__(self, pet_window: PetWindow, chat_window: ChatWindow, *, startup_service=None) -> None:
        super().__init__()
        self.pet_window = pet_window
        self.chat_window = chat_window
        self.startup_service = startup_service
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

        self.startup_action = QAction('开机启动（当前用户）', menu)
        self.startup_action.setCheckable(True)
        self.startup_action.setEnabled(self.startup_service is not None)
        self.startup_action.triggered.connect(self._set_startup_enabled)
        menu.addAction(self.startup_action)
        menu.aboutToShow.connect(self._refresh_startup)
        menu.addSeparator()

        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(quit_action)
        return menu

    def _startup_unavailable(self) -> None:
        with QSignalBlocker(self.startup_action):
            self.startup_action.setChecked(False)
        self.startup_action.setEnabled(False)
        self.startup_action.setText('开机启动暂不可用')

    def _refresh_startup(self) -> None:
        if self.startup_service is None:
            self._startup_unavailable()
            return
        try:
            enabled = self.startup_service.is_enabled()
        except StartupError:
            self._startup_unavailable()
            return
        with QSignalBlocker(self.startup_action):
            self.startup_action.setChecked(enabled)
        self.startup_action.setText('开机启动（当前用户）')
        self.startup_action.setEnabled(True)

    def _set_startup_enabled(self, enabled: bool) -> None:
        if self.startup_service is None:
            self._startup_unavailable()
            return
        try:
            self.startup_service.set_enabled(enabled)
        except StartupError:
            self._startup_unavailable()
            return
        self._refresh_startup()

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
