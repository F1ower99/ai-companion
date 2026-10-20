import pytest

from companion.application.startup import StartupError
from companion.desktop.chat_window import ChatWindow
from companion.desktop.pet_window import PetWindow
from companion.desktop.tray import TrayController


class Service:
    def __init__(self):
        self.enabled, self.calls, self.failure = False, [], False

    def is_enabled(self):
        self.calls.append('read')
        if self.failure:
            raise StartupError()
        return self.enabled

    def set_enabled(self, enabled):
        self.calls.append(('write', enabled))
        if self.failure:
            raise StartupError()
        self.enabled = enabled


@pytest.fixture
def tray(qtbot, monkeypatch):
    from PySide6.QtWidgets import QSystemTrayIcon
    monkeypatch.setattr(QSystemTrayIcon, 'isSystemTrayAvailable', staticmethod(lambda: False))
    chat = ChatWindow()
    pet = PetWindow(chat)
    qtbot.addWidget(chat)
    qtbot.addWidget(pet)
    service = Service()
    controller = TrayController(pet, chat, startup_service=service)
    qtbot.addWidget(controller.menu)
    return controller, service


def test_startup_menu_construction_is_lazy_and_refresh_never_writes(tray):
    controller, service = tray
    assert service.calls == []
    assert not controller.startup_action.isChecked()
    service.enabled = True
    controller.menu.aboutToShow.emit()
    assert controller.startup_action.isChecked()
    assert service.calls == ['read']
    controller.menu.aboutToShow.emit()
    assert service.calls == ['read', 'read']


def test_explicit_toggle_enables_and_disables_startup(tray):
    controller, service = tray
    controller.menu.aboutToShow.emit()
    controller.startup_action.trigger()
    assert service.enabled and controller.startup_action.isChecked()
    controller.startup_action.trigger()
    assert not service.enabled and not controller.startup_action.isChecked()
    assert [call for call in service.calls if isinstance(call, tuple)] == [('write', True), ('write', False)]


def test_startup_read_failure_disables_and_recovers_on_next_menu_open(tray):
    controller, service = tray
    service.failure = True
    controller.menu.aboutToShow.emit()
    assert not controller.startup_action.isEnabled()
    assert not controller.startup_action.isChecked()
    service.failure = False
    controller.menu.aboutToShow.emit()
    assert controller.startup_action.isEnabled()
    assert service.calls == ['read', 'read']


def test_write_failure_is_not_displayed_as_success(tray):
    controller, service = tray
    controller.menu.aboutToShow.emit()
    service.failure = True
    controller.startup_action.trigger()
    assert not controller.startup_action.isChecked()
    assert not controller.startup_action.isEnabled()
    assert not service.enabled
