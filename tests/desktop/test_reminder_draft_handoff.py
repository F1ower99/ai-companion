import pytest

from companion.desktop.chat_window import ChatWindow
from companion.desktop.reminder_card import ReminderCard
from companion.desktop.reminder_reply_dialog import ReminderReplyDialog
from companion.domain.reminders import ReminderAction
from companion.domain.voice import VoiceTranscript
from test_reminder_card import FakeTaskService, FakeReminderService, make_decision


def test_source_is_optional_and_not_read_until_explicit_fill(qtbot):
    reads, actions = [], []
    def source():
        reads.append(True)
        return '再给我半小时'
    panel = ReminderReplyDialog('Vocabulary', actions.append, draft_source=source)
    qtbot.addWidget(panel)
    panel.begin()
    assert reads == [] and not panel.confirm_button.isEnabled()
    panel.draft_button.click()
    assert reads == [True] and panel.reply_input.text() == '再给我半小时'
    assert actions == [] and not panel.confirm_button.isEnabled()
    assert panel.preview_label.text() == ''
    panel.preview_button.click()
    assert actions == [] and panel.confirm_button.isEnabled()


@pytest.mark.parametrize('draft', ['', '   ', None, 42, '已完成' + ' ' * 200])
def test_unsuitable_draft_is_not_truncated_or_echoed(qtbot, draft):
    panel = ReminderReplyDialog('Task', lambda _: None, draft_source=lambda: draft)
    qtbot.addWidget(panel)
    panel.begin()
    panel.draft_button.click()
    assert panel.reply_input.text() == '' and not panel.confirm_button.isEnabled()
    assert panel.status_label.text()


def test_failure_is_generic_and_existing_reply_prevents_source_read(qtbot):
    reads = []
    def source():
        reads.append(True)
        raise RuntimeError('private draft and path')
    panel = ReminderReplyDialog('Task', lambda _: None, draft_source=source)
    qtbot.addWidget(panel)
    panel.begin()
    panel.reply_input.setText('已完成')
    panel.draft_button.click()
    assert reads == [] and panel.reply_input.text() == '已完成'
    panel.reply_input.setText('')
    panel.draft_button.click()
    assert reads == [True] and panel.status_label.text()
    assert 'private' not in panel.status_label.text()


def test_hidden_or_invalidated_panel_cannot_pull_draft(qtbot):
    reads = []
    panel = ReminderReplyDialog('Task', lambda _: None, draft_source=lambda: reads.append(True))
    qtbot.addWidget(panel)
    panel._fill_from_draft()
    panel.begin()
    panel.invalidate()
    panel._fill_from_draft()
    assert reads == [] and panel.reply_input.text() == ''


def test_absent_source_has_no_draft_control(qtbot):
    panel = ReminderReplyDialog('Task', lambda _: None)
    qtbot.addWidget(panel)
    panel.begin()
    assert panel.draft_button is None


def test_voice_draft_reaches_current_card_only_after_pull_preview_confirm(qtbot):
    tasks, service = FakeTaskService(), FakeReminderService()
    window = ChatWindow(tasks, reminder_service=service)
    qtbot.addWidget(window)
    assert window.accept_voice_transcript(VoiceTranscript('再给我半小时'))
    window.show_decision(make_decision())
    card = window.reminder_card
    qtbot.addWidget(card)
    card.open_reply()
    panel = card.reply_dialog
    assert panel.reply_input.text() == '' and service.calls == []
    panel.draft_button.click()
    assert window.composer.toPlainText() == '再给我半小时'
    assert service.calls == [] and not panel.confirm_button.isEnabled()
    panel.preview_button.click()
    assert service.calls == []
    panel.confirm_button.click()
    assert len(service.calls) == 1
    assert service.calls[0][:3] == ('task-1', ReminderAction.EXTEND, 30)
    assert window.composer.toPlainText() == '再给我半小时'
    assert panel.reply_input.text() == '' and not panel.isVisible()


def test_dismissed_card_does_not_read_or_apply_the_chat_draft(qtbot):
    reads, service = [], FakeReminderService()
    card = ReminderCard(FakeTaskService(), service, make_decision(),
                        draft_source=lambda: reads.append(True))
    qtbot.addWidget(card)
    card.show()
    card.open_reply()
    panel = card.reply_dialog
    card.dismiss()
    panel._fill_from_draft()
    panel._confirm()
    assert reads == [] and service.calls == []


def test_source_invalidation_during_pull_cannot_restore_cleared_text(qtbot):
    def source():
        panel.invalidate()
        return '已完成'
    panel = ReminderReplyDialog('Task', lambda _: pytest.fail('unexpected action'), draft_source=source)
    qtbot.addWidget(panel)
    panel.begin()
    panel.draft_button.click()
    assert not panel.isVisible() and panel.reply_input.text() == ''
    assert not panel.confirm_button.isEnabled()


def test_unrecognized_draft_is_only_a_preview_error_and_cancel_preserves_source(qtbot):
    text = 'private unrelated conversation'
    actions = []
    panel = ReminderReplyDialog('Task', actions.append, draft_source=lambda: text)
    qtbot.addWidget(panel)
    panel.begin()
    panel.draft_button.click()
    panel.preview_button.click()
    assert not panel.confirm_button.isEnabled() and actions == []
    assert 'private' not in panel.status_label.text()
    panel.cancel_button.click()
    assert panel.reply_input.text() == '' and text == 'private unrelated conversation'
