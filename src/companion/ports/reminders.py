from datetime import date, datetime
from typing import Protocol

from companion.domain.reminders import ReminderEvent, ReminderPreferences, TaskReminderState


class ReminderRepository(Protocol):
    def get_task_states(self, local_date: date) -> list[TaskReminderState]: ...
    def get_last_global_shown_at(self) -> datetime | None: ...
    def get_event_by_key(self, idempotency_key: str) -> ReminderEvent | None: ...
    def save_state_and_event(
        self,
        state: TaskReminderState,
        event: ReminderEvent,
        global_last_shown_at: datetime | None = None,
        global_cooldown_minutes: int | None = None,
        task_cooldown_minutes: int | None = None,
        bypass_task_cooldown: bool = False,
    ) -> bool: ...


class ReminderPreferencesRepository(Protocol):
    def get_preferences(self) -> ReminderPreferences: ...
    def save_preferences(self, preferences: ReminderPreferences, updated_at: datetime) -> None: ...
