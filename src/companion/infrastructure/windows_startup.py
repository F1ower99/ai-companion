"""Lazy access to exactly one current-user Run value."""
from companion.application.startup import StartupError, validate_command

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
VALUE_NAME = 'AICompanion'


class WindowsStartupStore:
    def __init__(self, registry=None):
        self._registry = registry

    def _api(self):
        if self._registry is not None:
            return self._registry
        import winreg
        return winreg

    def read(self) -> str | None:
        try:
            registry = self._api()
            with registry.OpenKey(registry.HKEY_CURRENT_USER, RUN_KEY, 0, registry.KEY_READ) as key:
                value, kind = registry.QueryValueEx(key, VALUE_NAME)
            if kind != registry.REG_SZ or not isinstance(value, str):
                raise StartupError()
            return value
        except FileNotFoundError:
            return None
        except Exception:
            raise StartupError() from None

    def write(self, command: str | None) -> None:
        try:
            registry = self._api()
            if command is None:
                try:
                    with registry.OpenKey(registry.HKEY_CURRENT_USER, RUN_KEY, 0, registry.KEY_SET_VALUE) as key:
                        registry.DeleteValue(key, VALUE_NAME)
                except FileNotFoundError:
                    pass
            else:
                validate_command(command)
                with registry.CreateKeyEx(registry.HKEY_CURRENT_USER, RUN_KEY, 0, registry.KEY_SET_VALUE) as key:
                    registry.SetValueEx(key, VALUE_NAME, 0, registry.REG_SZ, command)
        except Exception:
            raise StartupError() from None
