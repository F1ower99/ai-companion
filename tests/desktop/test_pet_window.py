from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from companion.desktop.chat_window import ChatWindow
from companion.desktop.pet_window import PetWindow
from companion.desktop.tray import TrayController


def make_windows(qtbot):
    chat = ChatWindow()
    pet = PetWindow(chat)
    qtbot.addWidget(chat)
    qtbot.addWidget(pet)
    pet.show()
    return pet, chat


def test_pet_window_is_translucent_frameless_and_always_on_top(qtbot):
    pet, _ = make_windows(qtbot)

    assert pet.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert pet.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert pet.windowFlags() & Qt.WindowType.WindowStaysOnTopHint


def test_click_without_drag_opens_chat(qtbot):
    pet, chat = make_windows(qtbot)
    assert not chat.isVisible()

    QTest.mouseClick(pet, Qt.MouseButton.LeftButton, pos=pet.rect().center())

    assert chat.isVisible()


def test_drag_moves_pet_window(qtbot):
    pet, chat = make_windows(qtbot)
    start = pet.pos()
    press_at = QPoint(24, 24)

    QTest.mousePress(pet, Qt.MouseButton.LeftButton, pos=press_at)
    QTest.mouseMove(pet, QPoint(52, 48), delay=20)
    QTest.mouseRelease(pet, Qt.MouseButton.LeftButton, pos=QPoint(52, 48))

    assert pet.pos() != start
    assert not chat.isVisible()


def test_subthreshold_pointer_jitter_opens_chat_without_dragging(qtbot):
    pet, chat = make_windows(qtbot)
    start = pet.pos()
    press_at = QPoint(24, 24)
    release_at = press_at + QPoint(2, 1)
    assert (release_at - press_at).manhattanLength() < QApplication.startDragDistance()

    QTest.mousePress(pet, Qt.MouseButton.LeftButton, pos=press_at)
    QTest.mouseMove(pet, release_at, delay=20)
    QTest.mouseRelease(pet, Qt.MouseButton.LeftButton, pos=release_at)

    assert pet.pos() == start
    assert chat.isVisible()


def test_pet_initial_position_uses_primary_screen_available_area(qtbot):
    pet, _ = make_windows(qtbot)
    screen = QApplication.primaryScreen()
    assert screen is not None
    area = screen.availableGeometry()

    assert pet.pos() == QPoint(
        area.right() - pet.width() - 17,
        area.bottom() - pet.height() - 17,
    )


def test_click_through_can_be_toggled_without_hiding_the_pet(qtbot):
    pet, _ = make_windows(qtbot)

    pet.set_click_through(True)

    assert pet.isVisible()
    assert pet.windowFlags() & Qt.WindowType.WindowTransparentForInput

    pet.set_click_through(False)

    assert pet.isVisible()
    assert not pet.windowFlags() & Qt.WindowType.WindowTransparentForInput


def test_pet_context_menu_can_reopen_chat_and_request_exit(qtbot):
    from PySide6.QtTest import QSignalSpy

    pet, chat = make_windows(qtbot)
    exit_requested = QSignalSpy(pet.exitRequested)
    menu = pet._create_context_menu()
    actions = {action.text(): action for action in menu.actions()}

    actions["打开聊天"].trigger()
    assert chat.isVisible()

    actions["退出"].trigger()
    assert exit_requested.count() == 1


def test_tray_menu_toggles_pet_input_transparency(qtbot):
    pet, chat = make_windows(qtbot)
    controller = TrayController(pet, chat)
    qtbot.addWidget(controller.menu)
    action = controller.toggle_click_through

    action.trigger()
    assert pet.windowFlags() & Qt.WindowType.WindowTransparentForInput
    assert action.isChecked()

    action.trigger()
    assert not pet.windowFlags() & Qt.WindowType.WindowTransparentForInput
    assert not action.isChecked()
