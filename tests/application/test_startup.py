import pytest

from companion.application.startup import StartupError, StartupService


class Store:
    def __init__(self, value=None):
        self.value, self.calls, self.failure = value, [], False

    def read(self):
        self.calls.append('read')
        if self.failure:
            raise OSError('private registry detail')
        return self.value

    def write(self, value):
        self.calls.append(('write', value))
        if self.failure:
            raise OSError('private registry detail')
        self.value = value


def test_startup_is_lazy_and_only_explicit_actions_write():
    store = Store()
    service = StartupService(store, '"C:\\Companion\\app.exe"')
    assert store.calls == []
    assert service.is_enabled() is False and store.calls == ['read']
    service.set_enabled(True)
    assert service.is_enabled() is True
    service.set_enabled(False)
    assert store.value is None and service.is_enabled() is False


def test_conflicting_command_is_never_overwritten_or_deleted():
    store = Store('other installation')
    service = StartupService(store, 'expected')
    for operation in (service.is_enabled, lambda: service.set_enabled(True), lambda: service.set_enabled(False)):
        with pytest.raises(StartupError) as error:
            operation()
        assert 'other installation' not in str(error.value)
    assert store.value == 'other installation' and store.calls == ['read'] * 3


def test_read_and_write_failures_are_sanitized():
    store = Store()
    service = StartupService(store, 'expected')
    store.failure = True
    with pytest.raises(StartupError, match='开机启动') as error:
        service.set_enabled(True)
    assert 'private' not in str(error.value)
    store.failure = False
    def fail_write(value):
        raise OSError('private write detail')
    store.write = fail_write
    with pytest.raises(StartupError) as error:
        service.set_enabled(True)
    assert 'private' not in str(error.value)


@pytest.mark.parametrize('command', ['', 'x' * 261, '\x00evil', 'x' * 259 + '😀'])
def test_invalid_or_overlong_run_command_is_rejected(command):
    with pytest.raises(StartupError):
        StartupService(Store(), command)


def test_idempotent_actions_do_not_write_and_bool_is_required():
    store = Store()
    service = StartupService(store, 'expected')
    service.set_enabled(False)
    assert store.calls == ['read']
    service.set_enabled(True)
    store.calls.clear()
    service.set_enabled(True)
    assert store.calls == ['read']
    with pytest.raises(StartupError):
        service.set_enabled('false')
