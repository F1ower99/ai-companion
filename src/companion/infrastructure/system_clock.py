from datetime import date, datetime, time, timedelta, timezone
import time as host_time
from typing import Protocol

from companion.domain.errors import ValidationError
from companion.domain.reminders import ReminderPreferences
from companion.ports.clock import ClockSnapshot


class LocalTimeResolver(Protocol):
    def now_local(self) -> datetime: ...
    def resolve_local(self, day: date, local_time: time) -> datetime: ...


class HostLocalTimeResolver:
    """Use the operating system's configured local time zone without IANA data."""

    def now_local(self) -> datetime:
        return datetime.now().astimezone()

    def resolve_local(self, day: date, local_time: time) -> datetime:
        if not isinstance(day, date) or isinstance(day, datetime):
            raise ValidationError("day must be a calendar date.")
        if not isinstance(local_time, time) or local_time.tzinfo is not None:
            raise ValidationError("local_time must be a naive local wall time.")
        wall = datetime.combine(day, local_time)
        candidates: dict[float, datetime] = {}
        for is_dst in (-1, 0, 1):
            try:
                stamp = host_time.mktime((
                    wall.year, wall.month, wall.day, wall.hour, wall.minute,
                    wall.second, -1, -1, is_dst,
                )) + wall.microsecond / 1_000_000
                round_trip = datetime.fromtimestamp(stamp).replace(tzinfo=None)
            except (OverflowError, OSError, ValueError):
                continue
            if round_trip == wall:
                candidates[stamp] = datetime.fromtimestamp(stamp, timezone.utc)
        if not candidates:
            raise ValidationError("That local time does not exist because of a clock change.")
        if len(candidates) > 1:
            raise ValidationError("That local time occurs twice because of a clock change.")
        return next(iter(candidates.values()))


class SystemClock:
    def __init__(self, resolver: LocalTimeResolver | None = None) -> None:
        self.resolver = resolver or HostLocalTimeResolver()

    def now_utc(self) -> datetime:
        return self.resolver.now_local().astimezone(timezone.utc)

    def local_date(self) -> date:
        local_now = self.resolver.now_local()
        if local_now.tzinfo is None or local_now.utcoffset() is None:
            raise ValidationError("The local-time resolver returned a naive current time.")
        return local_now.date()

    def resolve_local(self, day: date, local_time: time) -> datetime:
        value = self.resolver.resolve_local(day, local_time)
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("The local-time resolver returned a naive instant.")
        return value.astimezone(timezone.utc)

    def snapshot(self, preferences: ReminderPreferences) -> ClockSnapshot:
        local_now = self.resolver.now_local()
        if local_now.tzinfo is None or local_now.utcoffset() is None:
            raise ValidationError("The local-time resolver returned a naive current time.")
        now_utc = local_now.astimezone(timezone.utc)
        today = local_now.date()
        tomorrow = today + timedelta(days=1)
        yesterday = today - timedelta(days=1)
        wall = local_now.timetz().replace(tzinfo=None)

        today_start = self.resolve_local(today, time.min)
        tomorrow_start = self.resolve_local(tomorrow, time.min)
        start = preferences.quiet_start
        end = preferences.quiet_end
        crosses_midnight = start > end
        if crosses_midnight:
            quiet_active = wall >= start or wall < end
            if wall >= start:
                quiet_start_day = today
                quiet_end_day = tomorrow
            elif wall < end:
                quiet_start_day = yesterday
                quiet_end_day = today
            else:
                quiet_start_day = today
                quiet_end_day = tomorrow
        else:
            quiet_active = start <= wall < end
            if quiet_active:
                quiet_start_day = today
                quiet_end_day = today
            elif wall < start:
                quiet_start_day = today
                quiet_end_day = today
            else:
                quiet_start_day = tomorrow
                quiet_end_day = tomorrow
        quiet_start_utc = self.resolve_local(quiet_start_day, start)
        quiet_end_utc = self.resolve_local(quiet_end_day, end)
        return ClockSnapshot(
            now_utc=now_utc,
            local_now=local_now,
            local_date=today,
            local_day_start_utc=today_start,
            next_local_day_start_utc=tomorrow_start,
            quiet_hours_active=quiet_active,
            tonight_quiet_start_utc=quiet_start_utc,
            quiet_period_end_utc=quiet_end_utc,
        )
