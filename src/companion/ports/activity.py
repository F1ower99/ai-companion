from datetime import datetime
from typing import Protocol

from companion.domain.reminders import ActivitySnapshot


class ActivitySource(Protocol):
    def snapshot(self, at: datetime) -> ActivitySnapshot: ...
