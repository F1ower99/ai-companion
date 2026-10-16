import importlib
import importlib.util
from datetime import datetime, timedelta, timezone

import pytest

from companion.domain.reminders import ActivityState


UTC = timezone.utc
START = datetime(2026, 10, 12, 10, 0, tzinfo=UTC)


def _adapter():
    spec = importlib.util.find_spec("companion.infrastructure.windows_activity")
    assert spec is not None
    return importlib.import_module("companion.infrastructure.windows_activity")


class FakeIdleReader:
    available = True

    def __init__(self, value):
        self.value = value
        self.calls = 0
        self.failure = None

    def idle_seconds(self):
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        return self.value


@pytest.mark.parametrize(
    ("idle_seconds", "expected"),
    [(299.999, ActivityState.FOCUSED), (300, ActivityState.IDLE)],
)
def test_five_minute_idle_threshold(idle_seconds, expected):
    module = _adapter()
    source = module.WindowsIdleActivitySource(FakeIdleReader(idle_seconds))
    assert source.snapshot(START).state is expected


def test_activity_source_tracks_state_transitions_without_restarting_same_interval():
    reader = FakeIdleReader(0)
    source = _adapter().WindowsIdleActivitySource(reader)
    first = source.snapshot(START)
    active_again = source.snapshot(START + timedelta(minutes=1))
    reader.value = 300
    idle = source.snapshot(START + timedelta(minutes=2))
    idle_again = source.snapshot(START + timedelta(minutes=3))

    assert first.state is ActivityState.FOCUSED
    assert first.state_since == START
    assert active_again.state_since == START
    assert idle.state is ActivityState.IDLE
    assert idle.state_since == START + timedelta(minutes=2)
    assert idle_again.state_since == idle.state_since


def test_long_sampling_gap_resets_focused_duration():
    source = _adapter().WindowsIdleActivitySource(FakeIdleReader(0))
    source.snapshot(START)

    resumed = source.snapshot(START + timedelta(minutes=5, seconds=1))

    assert resumed.state is ActivityState.FOCUSED
    assert resumed.state_since == resumed.observed_at


def test_reset_starts_a_new_state_interval():
    source = _adapter().WindowsIdleActivitySource(FakeIdleReader(0))
    source.snapshot(START)
    source.reset()

    next_sample = source.snapshot(START + timedelta(minutes=1))

    assert next_sample.state_since == next_sample.observed_at


def test_reader_failure_returns_unknown_and_restarts_state_tracking():
    reader = FakeIdleReader(0)
    source = _adapter().WindowsIdleActivitySource(reader)
    source.snapshot(START)
    reader.failure = OSError("private OS detail")

    failed = source.snapshot(START + timedelta(minutes=1))
    reader.failure = None
    recovered = source.snapshot(START + timedelta(minutes=2))

    assert failed.state is ActivityState.UNKNOWN
    assert recovered.state is ActivityState.FOCUSED
    assert recovered.state_since == recovered.observed_at


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), True, "300"])
def test_invalid_idle_values_return_unknown(value):
    source = _adapter().WindowsIdleActivitySource(FakeIdleReader(value))
    assert source.snapshot(START).state is ActivityState.UNKNOWN


def test_unsupported_source_returns_unknown_without_querying_reader():
    reader = FakeIdleReader(0)
    source = _adapter().WindowsIdleActivitySource(reader, available=False)

    assert source.snapshot(START).state is ActivityState.UNKNOWN
    assert reader.calls == 0


def test_win32_tick_wrap_is_handled_and_future_tick_is_rejected():
    reader_type = _adapter().WindowsIdleDurationReader
    wrapped = reader_type(
        supported=True,
        last_input_tick=lambda: 0xFFFFFFE0,
        tick_count=iter([0xFFFFFFF0, 0x1_00000014]).__next__,
    )
    future = reader_type(
        supported=True,
        last_input_tick=lambda: 21,
        tick_count=lambda: 20,
    )

    assert wrapped.idle_seconds() == pytest.approx(0.016)
    assert wrapped.idle_seconds() == pytest.approx(0.052)
    with pytest.raises(OSError):
        future.idle_seconds()


def test_non_monotonic_last_input_tick_is_rejected():
    last_input_ticks = iter([100_000, 99_999])
    current_ticks = iter([200_000, 200_001])
    reader = _adapter().WindowsIdleDurationReader(
        supported=True,
        last_input_tick=lambda: next(last_input_ticks),
        tick_count=lambda: next(current_ticks),
    )

    assert reader.idle_seconds() == pytest.approx(100)
    with pytest.raises(OSError):
        reader.idle_seconds()


def test_tick_age_is_ambiguous_when_reader_starts_after_one_tick_cycle():
    reader = _adapter().WindowsIdleDurationReader(
        supported=True,
        last_input_tick=lambda: 500,
        tick_count=lambda: 0x1_000003E8,
    )

    with pytest.raises(OSError, match="ambiguous"):
        reader.idle_seconds()


def test_stale_input_does_not_appear_recent_after_a_full_tick_cycle():
    current_ticks = iter([1_000, 0x1_000003F2])
    reader = _adapter().WindowsIdleDurationReader(
        supported=True,
        last_input_tick=lambda: 500,
        tick_count=current_ticks.__next__,
    )

    assert reader.idle_seconds() == pytest.approx(0.5)
    with pytest.raises(OSError, match="implausible|ambiguous"):
        reader.idle_seconds()


def test_new_input_after_half_tick_cycle_is_anchored_from_64_bit_uptime():
    start = 1_000
    after_long_idle = start + (1 << 31) + 1_000
    after_input = after_long_idle + 1_000
    current_ticks = iter([start, after_long_idle, after_input])
    last_input_ticks = iter([start, start, (after_input & 0xFFFFFFFF) - 100])
    reader = _adapter().WindowsIdleDurationReader(
        supported=True,
        last_input_tick=last_input_ticks.__next__,
        tick_count=current_ticks.__next__,
    )

    assert reader.idle_seconds() == pytest.approx(0)
    assert reader.idle_seconds() == pytest.approx(((1 << 31) + 1_000) / 1000)
    assert reader.idle_seconds() == pytest.approx(0.1)
