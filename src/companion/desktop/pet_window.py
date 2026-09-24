from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QColor,
    QContextMenuEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from companion.desktop.chat_window import ChatWindow


class PetWindow(QWidget):
    """Small, transparent, draggable pet window that opens the chat panel."""

    exitRequested = Signal()
    closeRequested = Signal()
    _MARGIN = 18

    def __init__(self, chat_window: ChatWindow) -> None:
        super().__init__()
        self.chat_window = chat_window
        self._press_global: QPoint | None = None
        self._window_origin = QPoint()
        self._dragged = False
        self._context_menu: QMenu | None = None

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setFixedSize(128, 148)
        self.setMouseTracking(True)
        self._place_at_bottom_right()

    def set_click_through(self, enabled: bool) -> None:
        """Pass pointer input through the pet window when enabled."""
        enabled = bool(enabled)
        current = bool(self.windowFlags() & Qt.WindowType.WindowTransparentForInput)
        if current == enabled:
            return

        was_visible = self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, enabled)
        if was_visible:
            self.show()

    def _create_context_menu(self) -> QMenu:
        if self._context_menu is not None:
            return self._context_menu

        menu = QMenu(self)
        open_chat = QAction("打开聊天", menu)
        open_chat.triggered.connect(self._show_chat)
        menu.addAction(open_chat)
        menu.addSeparator()
        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(self.exitRequested.emit)
        menu.addAction(quit_action)
        self._context_menu = menu
        return self._context_menu

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802
        self._create_context_menu().exec(event.globalPos())
        event.accept()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.closeRequested.emit()
        super().closeEvent(event)

    def _show_chat(self) -> None:
        self.chat_window.show()
        self.chat_window.raise_()
        self.chat_window.activateWindow()

    def _place_at_bottom_right(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.move(
            area.right() - self.width() - self._MARGIN + 1,
            area.bottom() - self.height() - self._MARGIN + 1,
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._window_origin = self.pos()
            self._dragged = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._press_global is None:
            super().mouseMoveEvent(event)
            return

        current = event.globalPosition().toPoint()
        delta = current - self._press_global
        if not self._dragged and delta.manhattanLength() >= QApplication.startDragDistance():
            self._dragged = True
        if self._dragged:
            self.move(self._window_origin + delta)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._press_global is not None:
            open_chat = not self._dragged
            self._press_global = None
            self._dragged = False
            if open_chat:
                self._show_chat()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt event override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        # Soft ground shadow keeps the vector character grounded on any wallpaper.
        painter.setBrush(QColor(34, 61, 57, 42))
        painter.drawEllipse(QRectF(25, 130, 78, 11))

        # Ears sit behind the head.
        ear_color = QColor("#bf7755")
        left_ear = QPainterPath()
        left_ear.moveTo(23, 46)
        left_ear.lineTo(29, 9)
        left_ear.lineTo(55, 34)
        left_ear.closeSubpath()
        right_ear = QPainterPath()
        right_ear.moveTo(73, 34)
        right_ear.lineTo(101, 9)
        right_ear.lineTo(105, 48)
        right_ear.closeSubpath()
        painter.setBrush(ear_color)
        painter.drawPath(left_ear)
        painter.drawPath(right_ear)
        painter.setBrush(QColor("#f1b7a3"))
        inner_left = QPainterPath()
        inner_left.moveTo(31, 35)
        inner_left.lineTo(34, 17)
        inner_left.lineTo(48, 33)
        inner_left.closeSubpath()
        inner_right = QPainterPath()
        inner_right.moveTo(81, 33)
        inner_right.lineTo(96, 18)
        inner_right.lineTo(98, 36)
        inner_right.closeSubpath()
        painter.drawPath(inner_left)
        painter.drawPath(inner_right)

        # Body, head, and face are drawn in code so the MVP has no unlicensed assets.
        painter.setBrush(QColor("#6f9e91"))
        painter.drawRoundedRect(QRectF(29, 86, 70, 50), 28, 28)
        painter.setBrush(QColor("#e6aa79"))
        painter.drawEllipse(QRectF(13, 24, 102, 91))
        painter.setBrush(QColor("#f8e7d2"))
        painter.drawEllipse(QRectF(35, 57, 59, 51))

        painter.setBrush(QColor("#344947"))
        painter.drawEllipse(QRectF(43, 55, 7, 10))
        painter.drawEllipse(QRectF(78, 55, 7, 10))
        painter.setBrush(QColor("#d99186"))
        painter.drawEllipse(QRectF(31, 75, 13, 7))
        painter.drawEllipse(QRectF(84, 75, 13, 7))
        painter.setPen(QPen(QColor("#344947"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(QRectF(58, 72, 13, 10), 205 * 16, 130 * 16)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#f0d28a"))
        painter.drawRoundedRect(QRectF(53, 89, 23, 8), 4, 4)
