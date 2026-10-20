from datetime import datetime, timedelta, timezone

import pytest

from companion.application.memory_management import MemoryPage, PAGE_SIZE
from companion.desktop.memory_dialog import MemoryDialog
from companion.domain.models import Memory, MemoryKind

NOW = datetime(2026, 10, 20, tzinfo=timezone.utc)


class Service:
    def __init__(self):
        self.items = [Memory('one', MemoryKind.PROFILE, '<b>literal content</b>', source='<img src="private">', created_at=NOW),
                      Memory('two', MemoryKind.PREFERENCE, 'second public item', created_at=NOW, expires_at=NOW - timedelta(days=1))]
        self.calls, self.deleted = [], []
        self.fail_list = self.fail_delete = False

    def list_page(self, text='', kind=None, include_expired=True, offset=0):
        self.calls.append((text, kind, include_expired, offset))
        if self.fail_list:
            raise RuntimeError('private storage detail')
        items = [item for item in self.items if text in item.content and (kind is None or item.kind == kind)
                 and (include_expired or item.expires_at is None or item.expires_at > NOW)]
        return MemoryPage(tuple(items[offset:offset + PAGE_SIZE]), NOW, offset, len(items) > offset + PAGE_SIZE)

    def delete(self, memory_id):
        if self.fail_delete:
            raise RuntimeError('private delete detail')
        self.deleted.append(memory_id)
        existed = any(item.id == memory_id for item in self.items)
        self.items = [item for item in self.items if item.id != memory_id]
        return existed


def dialog(qtbot, *, confirm=False):
    service = Service()
    widget = MemoryDialog(service, confirmation_handler=lambda: confirm)
    qtbot.addWidget(widget)
    return widget, service


def test_open_is_explicit_details_are_plain_and_hide_clears_state(qtbot):
    from PySide6.QtCore import Qt
    widget, service = dialog(qtbot)
    assert service.calls == []
    widget.show()
    assert widget.list_widget.count() == 2
    widget.list_widget.setCurrentRow(0)
    assert widget.detail.toPlainText() == '<b>literal content</b>'
    assert '<img src="private">' in widget.metadata.text()
    assert widget.metadata.textFormat() == Qt.TextFormat.PlainText
    widget.hide()
    assert widget.list_widget.count() == 0 and widget.detail.toPlainText() == ''
    assert not widget.delete_button.isEnabled()
    widget.show()
    assert len(service.calls) == 2


def test_expired_visibility_and_kind_filter_are_user_controlled(qtbot):
    widget, service = dialog(qtbot)
    widget.show()
    assert '已过期' in widget.list_widget.item(1).text()
    widget.include_expired.setChecked(False)
    assert widget.list_widget.count() == 1 and service.calls[-1][2] is False
    widget.kind_combo.setCurrentIndex(widget.kind_combo.findData(MemoryKind.PREFERENCE))
    assert widget.list_widget.count() == 0


def test_paging_and_new_search_reset_offset(qtbot):
    widget, service = dialog(qtbot)
    service.items = [Memory(str(i), MemoryKind.PROFILE, f'public item {i}', created_at=NOW) for i in range(51)]
    widget.show()
    assert widget.next_button.isEnabled() and not widget.previous_button.isEnabled()
    widget.next_button.click()
    assert widget.list_widget.count() == 1 and service.calls[-1][-1] == 50
    assert not widget.next_button.isEnabled() and widget.previous_button.isEnabled()
    widget.search_input.setText('item 3')
    widget.search_button.click()
    assert service.calls[-1] == ('item 3', None, True, 0)
    assert widget.list_widget.count() == 11


def test_delete_cancel_and_confirm_only_selected_record(qtbot):
    widget, service = dialog(qtbot)
    widget.show()
    widget.list_widget.setCurrentRow(0)
    widget.delete_button.click()
    assert service.deleted == [] and widget.list_widget.count() == 2
    widget.confirmation_handler = lambda: True
    widget.delete_button.click()
    assert service.deleted == ['one'] and widget.list_widget.count() == 1
    assert widget.detail.toPlainText() == '' and not widget.delete_button.isEnabled()


def test_confirmation_reentry_cannot_change_the_deletion_target(qtbot):
    widget, service = dialog(qtbot)
    widget.show()
    widget.list_widget.setCurrentRow(0)
    def confirm():
        widget.list_widget.setCurrentRow(1)
        return True
    widget.confirmation_handler = confirm
    widget.delete_button.click()
    assert service.deleted == ['one']


def test_deleting_last_row_on_later_page_returns_to_first_page(qtbot):
    widget, service = dialog(qtbot, confirm=True)
    service.items = [Memory(str(i), MemoryKind.PROFILE, f'item {i}', created_at=NOW) for i in range(51)]
    widget.show()
    widget.next_button.click()
    widget.list_widget.setCurrentRow(0)
    widget.delete_button.click()
    assert service.deleted == ['50'] and widget.list_widget.count() == 50
    assert service.calls[-1][-1] == 0


def test_errors_are_sanitized_and_do_not_claim_delete_success(qtbot):
    widget, service = dialog(qtbot, confirm=True)
    widget.show()
    widget.list_widget.setCurrentRow(0)
    service.fail_delete = True
    widget.delete_button.click()
    assert service.deleted == [] and widget.list_widget.count() == 2
    assert 'private' not in widget.status_label.text()
    service.fail_list = True
    widget.search_button.click()
    assert widget.list_widget.count() == 0 and widget.detail.toPlainText() == ''
    assert not widget.delete_button.isEnabled()
    assert 'private' not in widget.status_label.text()


@pytest.mark.parametrize('change', ['hide', 'refresh'])
def test_confirmation_cannot_delete_after_view_is_hidden_or_reloaded(qtbot, change):
    widget, service = dialog(qtbot)
    widget.show()
    widget.list_widget.setCurrentRow(0)
    def confirm():
        widget.hide() if change == 'hide' else widget.reload()
        return True
    widget.confirmation_handler = confirm
    widget.delete_button.click()
    assert service.deleted == []


def test_settings_opens_memory_panel_without_saving_form_or_accessing_credentials(qtbot):
    from types import SimpleNamespace
    from companion.desktop.provider_settings_dialog import ProviderSettingsDialog
    from companion.domain.chat import ChatSettings
    def forbidden(*args):
        raise AssertionError('Unexpected save or credential operation')
    service = Service()
    settings = SimpleNamespace(get=lambda: ChatSettings(), save=forbidden)
    secrets = SimpleNamespace(get=forbidden, set=forbidden, delete=forbidden)
    widget = ProviderSettingsDialog(settings, secrets, SimpleNamespace(now_utc=lambda: NOW), memory_service=service)
    qtbot.addWidget(widget)
    assert service.calls == []
    widget.show()
    widget.model_input.setText('unsaved form change')
    widget.memory_button.click()
    panel = widget.memory_dialog
    assert panel.isVisible() and len(service.calls) == 1
    panel.list_widget.setCurrentRow(0)
    widget.hide()
    assert not panel.isVisible() and panel.list_widget.count() == 0
    widget.show()
    widget.memory_button.click()
    assert widget.memory_dialog is panel and len(service.calls) == 2
    assert widget.model_input.text() == 'unsaved form change'


def test_settings_disables_memory_management_without_service(qtbot):
    from types import SimpleNamespace
    from companion.desktop.provider_settings_dialog import ProviderSettingsDialog
    from companion.domain.chat import ChatSettings
    widget = ProviderSettingsDialog(SimpleNamespace(get=lambda: ChatSettings()), None, None)
    qtbot.addWidget(widget)
    assert not widget.memory_button.isEnabled()


def test_concurrently_removed_record_is_refreshed_without_deleting_another(qtbot):
    widget, service = dialog(qtbot)
    widget.show()
    widget.list_widget.setCurrentRow(0)
    def confirm():
        service.items = [item for item in service.items if item.id != 'one']
        return True
    widget.confirmation_handler = confirm
    widget.delete_button.click()
    assert [item.id for item in service.items] == ['two']
    assert widget.list_widget.count() == 1 and widget.detail.toPlainText() == ''
