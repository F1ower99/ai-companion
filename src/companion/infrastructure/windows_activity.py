from __future__ import annotations

import ctypes
import math
import os
from datetime import datetime
from typing import Callable

from companion.domain.reminders import ActivitySnapshot, ActivityState
from companion.ports.activity import IdleDurationReader, ResettableActivitySource


_UINT32_MAX = 0xFFFFFFFF
_UINT64_MAX = 0xFFFFFFFFFFFFFFFF
_MAX_PLAUSIBLE_IDLE_MS = 30 * 24 * 60 * 60 * 1000
_INPUT_TICK_JITTER_MS = 1000


class WindowsIdleDurationReader(IdleDurationReader):
    """Read only the elapsed time since input in the current Windows session."""

    def __init__(
        self,
        *,
        supported: bool | None = None,
        last_input_tick: Callable[[], int] | None = None,
        tick_count: Callable[[], int] | None = None,
    ) -> None:
        self._supported = os.name == "nt" if supported is None else supported
        self._last_input_tick_reader = last_input_tick or self._read_last_input_tick
        self._tick_count_reader = tick_count or self._read_tick_count
        self._last_observed_input_tick: int | None = None
        self._last_observed_uptime_ms: int | None = None
        self._extended_last_input_ms: int | None = None

    @property
    def available(self) -> bool:
        return self._supported

    def idle_seconds(self) -> float:
        if not self.available:
            raise OSError("Windows input idle detection is unavailable.")
        last_input = self._last_input_tick_reader()
        current = self._tick_count_reader()
        if (
            type(last_input) is not int
            or type(current) is not int
            or not 0 <= last_input <= _UINT32_MAX
            or not 0 <= current <= _UINT64_MAX
        ):
            raise OSError("Windows input idle detection returned an invalid tick.")

        current_low = current & _UINT32_MAX
        elapsed_ms = (current_low - last_input) & _UINT32_MAX
        previous_input = self._last_observed_input_tick
        previous_uptime = self._last_observed_uptime_ms

        if previous_uptime is not None and current < previous_uptime:
            raise OSError("Windows input idle detection returned a non-monotonic uptime.")

        if previous_input is None:
            self._last_observed_input_tick = last_input
            self._last_observed_uptime_ms = current
            if current > _UINT32_MAX:
                raise OSError("Windows input tick epoch is ambiguous after counter rollover.")
            if elapsed_ms > _MAX_PLAUSIBLE_IDLE_MS:
                raise OSError("Windows input idle detection returned an implausible interval.")
            self._extended_last_input_ms = current - elapsed_ms
            return elapsed_ms / 1000.0

        input_changed = last_input != previous_input

        if previous_uptime is None or current - previous_uptime > _MAX_PLAUSIBLE_IDLE_MS:
            self._last_observed_input_tick = last_input
            self._last_observed_uptime_ms = current
            self._extended_last_input_ms = None
            raise OSError("Windows input tick epoch is ambiguous after a long sampling gap.")

        if input_changed:
            if elapsed_ms > current - previous_uptime + _INPUT_TICK_JITTER_MS:
                raise OSError("Windows input tick is inconsistent with the observed interval.")
            input_timestamp = current - elapsed_ms
            if (
                self._extended_last_input_ms is not None
                and input_timestamp < self._extended_last_input_ms
            ):
                raise OSError("Windows input detection returned a non-monotonic timestamp.")
            self._extended_last_input_ms = input_timestamp
        elif self._extended_last_input_ms is None:
            self._last_observed_uptime_ms = current
            raise OSError("Windows input tick epoch remains ambiguous.")

        if self._extended_last_input_ms is None:
            raise OSError("Windows input tick epoch is ambiguous.")
        elapsed_ms = current - self._extended_last_input_ms
        if elapsed_ms < 0 or elapsed_ms > _MAX_PLAUSIBLE_IDLE_MS:
            raise OSError("Windows input idle detection returned an implausible interval.")

        self._last_observed_input_tick = last_input
        self._last_observed_uptime_ms = current
        return elapsed_ms / 1000.0

    @staticmethod
    def _read_last_input_tick() -> int:
        from ctypes import wintypes

        class LastInputInfo(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        get_last_input_info = user32.GetLastInputInfo
        get_last_input_info.argtypes = [ctypes.POINTER(LastInputInfo)]
        get_last_input_info.restype = wintypes.BOOL

        info = LastInputInfo()
        info.cbSize = ctypes.sizeof(LastInputInfo)
        if not get_last_input_info(ctypes.byref(info)):
            raise OSError("Windows input idle detection failed.")
        return int(info.dwTime)

    @staticmethod
    def _read_tick_count() -> int:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        get_tick_count = kernel32.GetTickCount64
        get_tick_count.argtypes = []
        get_tick_count.restype = ctypes.c_ulonglong
        return int(get_tick_count())


class WindowsIdleActivitySource(ResettableActivitySource):
    IDLE_THRESHOLD_SECONDS = 300.0
    MAX_SAMPLE_GAP_SECONDS = 300.0

    def __init__(
        self,
        reader: IdleDurationReader | None = None,
        *,
        available: bool | None = None,
        idle_threshold_seconds: float = IDLE_THRESHOLD_SECONDS,
        max_sample_gap_seconds: float = MAX_SAMPLE_GAP_SECONDS,
    ) -> None:
        self.reader = reader or WindowsIdleDurationReader()
        self._available = (
            bool(getattr(self.reader, "available", True))
            if available is None
            else available
        )
        self.idle_threshold_seconds = idle_threshold_seconds
        self.max_sample_gap_seconds = max_sample_gap_seconds
        self.reset()

    @property
    def available(self) -> bool:
        return self._available

    def reset(self) -> None:
        self._last_state: ActivityState | None = None
        self._last_observed_at: datetime | None = None
        self._state_since: datetime | None = None

    def snapshot(self, at: datetime) -> ActivitySnapshot:
        if not self.available:
            self.reset()
            return ActivitySnapshot(ActivityState.UNKNOWN, at, at)

        try:
            idle_seconds = self.reader.idle_seconds()
            if (
                type(idle_seconds) not in (int, float)
                or not math.isfinite(idle_seconds)
                or idle_seconds < 0
            ):
                raise ValueError("Invalid idle duration.")
            state = (
                ActivityState.IDLE
                if idle_seconds >= self.idle_threshold_seconds
                else ActivityState.FOCUSED
            )
            gap = (
                None
                if self._last_observed_at is None
                else (at - self._last_observed_at).total_seconds()
            )
            if (
                self._last_state is None
                or state is not self._last_state
                or self._state_since is None
                or gap is None
                or gap < 0
                or gap > self.max_sample_gap_seconds
            ):
                self._state_since = at
            snapshot = ActivitySnapshot(state, at, self._state_since)
            self._last_state = state
            self._last_observed_at = at
            return snapshot
        except Exception:
            self.reset()
            return ActivitySnapshot(ActivityState.UNKNOWN, at, at)
