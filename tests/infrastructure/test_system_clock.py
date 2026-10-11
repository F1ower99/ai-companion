from datetime import date, datetime, time, timedelta, timezone

import pytest

from companion.domain.errors import ValidationError
from companion.domain.reminders import ReminderPreferences
from companion.infrastructure.system_clock import HostLocalTimeResolver, SystemClock


LOCAL = timezone(timedelta(hours=8))


class FixedResolver:
    def __init__(self, local_now):
        self.value = local_now

    def now_local(self):
        return self.value

    def resolve_local(self, day, local_time):
        return datetime.combine(day, local_time).replace(tzinfo=LOCAL).astimezone(timezone.utc)


def test_snapshot_uses_one_local_time_value_and_resolves_day_and_quiet_bounds():
    local_now = datetime(2026, 9, 26, 20, 10, tzinfo=LOCAL)
    clock = SystemClock(FixedResolver(local_now))
    snapshot = clock.snapshot(ReminderPreferences())
    assert snapshot.now_utc == datetime(2026, 9, 26, 12, 10, tzinfo=timezone.utc)
    assert snapshot.local_now == local_now
    assert snapshot.local_date == date(2026, 9, 26)
    assert snapshot.local_day_start_utc == datetime(2026, 9, 25, 16, tzinfo=timezone.utc)
    assert snapshot.next_local_day_start_utc == datetime(2026, 9, 26, 16, tzinfo=timezone.utc)
    assert not snapshot.quiet_hours_active
    assert snapshot.tonight_quiet_start_utc == datetime(2026, 9, 26, 14, tzinfo=timezone.utc)
    assert snapshot.quiet_period_end_utc == datetime(2026, 9, 27, 0, tzinfo=timezone.utc)


def test_local_date_comes_from_the_injected_local_time_resolver():
    clock = SystemClock(FixedResolver(datetime(2026, 10, 11, 0, 5, tzinfo=LOCAL)))
    assert clock.local_date() == date(2026, 10, 11)


def test_snapshot_marks_overnight_quiet_hours_and_resolves_end_today():
    clock = SystemClock(FixedResolver(datetime(2026, 9, 27, 5, 0, tzinfo=LOCAL)))
    snapshot = clock.snapshot(ReminderPreferences())
    assert snapshot.quiet_hours_active
    assert snapshot.tonight_quiet_start_utc == datetime(2026, 9, 26, 14, tzinfo=timezone.utc)
    assert snapshot.quiet_period_end_utc == datetime(2026, 9, 27, 0, tzinfo=timezone.utc)


def test_wall_time_round_trips_through_host_rules():
    day = date(2026, 9, 26)
    wall = time(12, 34, 56)
    instant = HostLocalTimeResolver().resolve_local(day, wall)
    round_trip = datetime.fromtimestamp(instant.timestamp()).replace(tzinfo=None)
    assert round_trip == datetime.combine(day, wall)


@pytest.mark.parametrize("wall", [time(2, 30), time(1, 30)])
def test_resolver_rejection_of_ambiguous_or_nonexistent_time_is_propagated(wall):
    class TransitionResolver(FixedResolver):
        def resolve_local(self, day, local_time):
            if local_time == wall:
                raise ValidationError("ambiguous or nonexistent local time")
            return super().resolve_local(day, local_time)

    clock = SystemClock(TransitionResolver(datetime(2026, 9, 26, 12, tzinfo=LOCAL)))
    with pytest.raises(ValidationError, match="ambiguous or nonexistent"):
        clock.resolve_local(date(2026, 10, 25), wall)
