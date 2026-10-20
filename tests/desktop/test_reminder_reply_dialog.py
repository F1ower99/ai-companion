import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from companion.desktop.reminder_card import ReminderCard
from companion.domain.errors import StorageError, ValidationError
from companion.domain.reminders import ReminderAction
from test_reminder_card import FakeTaskService, FakeReminderService, make_decision


@pytest.fixture
def card(qtbot):
    service = FakeReminderService()
    widget = ReminderCard(FakeTaskService(), service, make_decision())
    qtbot.addWidget(widget)
    widget.show()
    yield widget, service


def open_reply(card):
    widget, _ = card
    widget.reply_button.click()
    return widget.reply_dialog


def test_automatic_card_stays_no_focus_and_reply_requires_explicit_open(card):
    widget, service = card
    assert widget.reply_dialog is None
    assert widget.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    assert widget.reply_button.focusPolicy() == Qt.FocusPolicy.NoFocus
    panel = open_reply(card)
    assert panel.isVisible() and not panel.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    assert panel.windowModality() == Qt.WindowModality.NonModal
    assert service.calls == []


def test_preview_and_enter_do_not_apply_but_confirm_forwards_half_hour_once(card):
    widget, service = card
    panel = open_reply(card)
    panel.reply_input.setText('再给我半小时')
    panel.preview_button.click()
    panel.reply_input.returnPressed.emit()
    assert service.calls == [] and '30' in panel.preview_label.text()
    assert panel.confirm_button.isEnabled()
    panel.confirm_button.click()
    panel.confirm_button.click()
    assert len(service.calls) == 1
    assert service.calls[0][:3] == ('task-1', ReminderAction.EXTEND, 30)
    assert not widget.isVisible() and not panel.isVisible() and panel.reply_input.text() == ''


def test_editing_invalidates_previous_proposal(card):
    _, service = card
    panel = open_reply(card)
    panel.reply_input.setText('已完成')
    panel.preview_button.click()
    assert panel.confirm_button.isEnabled()
    panel.reply_input.setText('今天跳过')
    assert not panel.confirm_button.isEnabled()
    panel._confirm()
    assert service.calls == []
    panel.preview_button.click()
    panel.confirm_button.click()
    assert service.calls[0][1] is ReminderAction.SKIP_TODAY


@pytest.mark.parametrize('text', ['已完成？', 'private unrecognized reply', '已完成' + ' ' * 200])
def test_unknown_or_overlong_reply_does_not_create_action_or_echo_input(card, text):
    _, service = card
    panel = open_reply(card)
    panel.reply_input.setText(text)
    panel.preview_button.click()
    assert not panel.confirm_button.isEnabled() and service.calls == []
    assert 'private' not in panel.status_label.text()


def test_cancelling_reply_clears_text_and_keeps_reminder_open(card):
    widget, service = card
    panel = open_reply(card)
    panel.reply_input.setText('再给我半小时')
    panel.preview_button.click()
    panel.cancel_button.click()
    assert widget.isVisible() and not panel.isVisible() and panel.reply_input.text() == ''
    assert service.calls == []
    widget.reply_button.click()
    assert widget.reply_dialog is panel and not panel.confirm_button.isEnabled()


def test_dismissed_parent_invalidates_pending_reply_without_action(card):
    widget, service = card
    panel = open_reply(card)
    panel.reply_input.setText('已完成')
    panel.preview_button.click()
    widget.dismiss()
    panel._confirm()
    assert service.calls == [] and not panel.isVisible() and panel.reply_input.text() == ''


@pytest.mark.parametrize('error', [ValidationError('private deadline detail'), StorageError('private database path')])
def test_service_rejection_is_safe_and_does_not_claim_success(card, error):
    widget, service = card
    service.error = error
    panel = open_reply(card)
    panel.reply_input.setText('延长30分钟')
    panel.preview_button.click()
    panel.confirm_button.click()
    assert widget.isVisible() and panel.isVisible() and len(service.calls) == 1
    assert 'private' not in panel.status_label.text() and panel.status_label.text()
    assert panel.confirm_button.isEnabled()


def test_reentrant_confirmation_never_sends_a_second_action(card):
    _, service = card
    panel = open_reply(card)
    original = service.respond
    def reentrant(*args, **kwargs):
        panel._confirm()
        return original(*args, **kwargs)
    service.respond = reentrant
    panel.reply_input.setText('现在做')
    panel.preview_button.click()
    panel.confirm_button.click()
    assert len(service.calls) == 1


def test_keyboard_enter_previews_without_clicking_dialog_confirmation(card):
    _, service = card
    panel = open_reply(card)
    panel.reply_input.setText('已完成')
    QTest.keyClick(panel.reply_input, Qt.Key.Key_Return)
    QTest.keyClick(panel.reply_input, Qt.Key.Key_Return)
    assert panel.confirm_button.isEnabled() and service.calls == []


def test_cancelled_text_cannot_be_restored_with_undo_after_reopen(card):
    widget, _ = card
    panel = open_reply(card)
    panel.reply_input.setText('再给')
    panel.reply_input.insert('我半小时')
    assert panel.reply_input.isUndoAvailable()
    panel.cancel_button.click()
    widget.reply_button.click()
    panel.reply_input.undo()
    assert panel.reply_input.text() == ''


def test_existing_quick_action_invalidates_a_pending_text_proposal(card):
    widget, service = card
    panel = open_reply(card)
    panel.reply_input.setText('延长30分钟')
    panel.preview_button.click()
    widget.now_button.click()
    panel._confirm()
    assert len(service.calls) == 1 and service.calls[0][1] is ReminderAction.NOW
    assert not panel.isVisible() and panel.reply_input.text() == ''
