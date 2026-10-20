from contextlib import contextmanager

import pytest

from companion.application.startup import StartupError
from companion.infrastructure.windows_startup import WindowsStartupStore


class Registry:
    HKEY_CURRENT_USER, KEY_READ, KEY_SET_VALUE, REG_SZ = 'HKCU', 1, 2, 3

    def __init__(self):
        self.values, self.calls, self.failure = {'unrelated': ('keep', 3)}, [], False

    @contextmanager
    def OpenKey(self, hive, key, reserved, access):
        assert hive == 'HKCU' and key == r'Software\Microsoft\Windows\CurrentVersion\Run'
        assert reserved == 0
        self.calls.append(('open', access))
        if self.failure:
            raise PermissionError('private registry detail')
        yield 'key'

    CreateKeyEx = OpenKey

    def QueryValueEx(self, key, name):
        assert key == 'key' and name == 'AICompanion'
        if name not in self.values:
            raise FileNotFoundError()
        return self.values[name]

    def SetValueEx(self, key, name, reserved, kind, value):
        assert key == 'key' and name == 'AICompanion' and reserved == 0 and kind == self.REG_SZ
        self.values[name] = (value, kind)

    def DeleteValue(self, key, name):
        assert key == 'key' and name == 'AICompanion'
        if name not in self.values:
            raise FileNotFoundError()
        del self.values[name]


def test_registry_only_accesses_its_own_current_user_value():
    registry = Registry()
    store = WindowsStartupStore(registry=registry)
    assert registry.calls == []
    assert store.read() is None
    store.write('expected')
    assert store.read() == 'expected'
    store.write(None)
    store.write(None)
    assert registry.values == {'unrelated': ('keep', 3)}


def test_missing_run_key_is_harmless_for_read_and_disable():
    registry = Registry()
    def missing(*args):
        raise FileNotFoundError()
    registry.OpenKey = missing
    store = WindowsStartupStore(registry=registry)
    assert store.read() is None
    store.write(None)
    assert registry.values == {'unrelated': ('keep', 3)}


@pytest.mark.parametrize('value,kind', [('expanded', 2), (123, 3)])
def test_unexpected_registry_value_type_is_rejected(value, kind):
    registry = Registry()
    registry.values['AICompanion'] = value, kind
    with pytest.raises(StartupError):
        WindowsStartupStore(registry=registry).read()


def test_registry_access_failures_are_sanitized():
    registry = Registry()
    registry.failure = True
    store = WindowsStartupStore(registry=registry)
    for operation in (store.read, lambda: store.write('command'), lambda: store.write(None)):
        with pytest.raises(StartupError) as error:
            operation()
        assert 'private' not in str(error.value)
