from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Protocol

from companion.domain.errors import ValidationError
from companion.domain.reminders import ReminderPreferences


@dataclass(frozen=True)
class ClockSnapshot:
    now_utc: datetime
    local_now: datetime
    local_date: date
    local_day_start_utc: datetime
    next_local_day_start_utc: datetime
    quiet_hours_active: bool
    tonight_quiet_start_utc: datetime
    quiet_period_end_utc: datetime

    def __post_init__(self) -> None:
        for name in (
            "now_utc", "local_now", "local_day_start_utc", "next_local_day_start_utc",
            "tonight_quiet_start_utc", "quiet_period_end_utc",
        ):
            value = getattr(self, name)
            if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
                raise ValidationError(f"{name} must include a timezone.")
            if name != "local_now":
                object.__setattr__(self, name, value.astimezone(timezone.utc))
        if not isinstance(self.local_date, date) or self.local_now.date() != self.local_date:
            raise ValidationError("local_date must match local_now.")
        if self.local_now.astimezone(timezone.utc) != self.now_utc:
            raise ValidationError("local_now and now_utc must describe the same instant.")
        if self.next_local_day_start_utc <= self.local_day_start_utc:
            raise ValidationError("Local day bounds must be increasing.")
        if self.quiet_period_end_utc <= self.tonight_quiet_start_utc:
            raise ValidationError("Quiet-hours bounds must be increasing.")
        if type(self.quiet_hours_active) is not bool:
            raise ValidationError("quiet_hours_active must be a boolean.")


class Clock(Protocol):
    def now_utc(self) -> datetime: ...
    def local_date(self) -> date: ...
    def snapshot(self, preferences: ReminderPreferences) -> ClockSnapshot: ...
    def resolve_local(self, day: date, local_time: time) -> datetime: ...
