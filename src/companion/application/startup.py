"""Explicit startup-setting policy; no Qt, registry or database dependency."""
from typing import Protocol


class StartupError(Exception):
    def __init__(self):
        super().__init__('开机启动设置暂不可用。')


def validate_command(command: str) -> str:
    try:
        if (not isinstance(command, str) or not command.strip()
                or any(ord(char) < 32 for char in command)
                or len(command.encode('utf-16-le')) > 520):
            raise ValueError()
    except (ValueError, UnicodeError):
        raise StartupError() from None
    return command


class StartupStore(Protocol):
    def read(self) -> str | None: ...
    def write(self, command: str | None) -> None: ...


class StartupService:
    def __init__(self, store: StartupStore, command: str):
        self._store = store
        self._command = validate_command(command)

    def is_enabled(self) -> bool:
        try:
            current = self._store.read()
            if current is not None and current != self._command:
                raise StartupError()
            return current is not None
        except Exception:
            raise StartupError() from None

    def set_enabled(self, enabled: bool) -> None:
        if type(enabled) is not bool:
            raise StartupError()
        if self.is_enabled() == enabled:
            return
        try:
            self._store.write(self._command if enabled else None)
        except Exception:
            raise StartupError() from None
