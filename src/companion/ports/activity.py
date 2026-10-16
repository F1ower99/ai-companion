from datetime import datetime
from typing import Protocol

from companion.domain.activity import ActivityAwarenessPreferences
from companion.domain.reminders import ActivitySnapshot


class ActivitySource(Protocol):
    def snapshot(self, at: datetime) -> ActivitySnapshot: ...


class ResettableActivitySource(ActivitySource, Protocol):
    @property
    def available(self) -> bool: ...

    def reset(self) -> None: ...


class ActivityPreferencesRepository(Protocol):
    def get(self) -> ActivityAwarenessPreferences: ...
    def save(self, preferences: ActivityAwarenessPreferences) -> None: ...


class IdleDurationReader(Protocol):
    def idle_seconds(self) -> float: ...
