import importlib
import importlib.util
from datetime import datetime, timezone

import pytest

from companion.domain.activity import ActivityAwarenessPreferences
from companion.domain.errors import StorageError, ValidationError
from companion.domain.reminders import ActivitySnapshot, ActivityState


NOW = datetime(2026, 10, 12, 11, 0, tzinfo=timezone.utc)


def _service_type():
    spec = importlib.util.find_spec("companion.application.activity_awareness_service")
    assert spec is not None
    return importlib.import_module("companion.application.activity_awareness_service").ActivityAwarenessService


class FakeSource:
    def __init__(self, available=True):
        self.available = available
        self.calls = 0
        self.resets = 0
        self.failure = None
        self.reset_failure = False
        self.value = ActivitySnapshot(ActivityState.FOCUSED, NOW, NOW)

    def snapshot(self, at):
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        return self.value

    def reset(self):
        self.resets += 1
        if self.reset_failure:
            raise OSError("private reset detail")


class FakePreferences:
    def __init__(self, enabled=False):
        self.value = ActivityAwarenessPreferences(enabled=enabled)
        self.fail_read = False
        self.fail_save = False
        self.saves = 0

    def get(self):
        if self.fail_read:
            raise StorageError("private preference path")
        return self.value

    def save(self, preferences):
        self.saves += 1
        if self.fail_save:
            raise StorageError("private preference path")
        self.value = preferences


def test_disabled_awareness_returns_unknown_without_querying_source():
    source = FakeSource()
    service = _service_type()(source, FakePreferences())

    snapshot = service.snapshot(NOW)

    assert snapshot.state is ActivityState.UNKNOWN
    assert source.calls == 0


def test_enabled_awareness_forwards_the_current_source_snapshot():
    source = FakeSource()
    repository = FakePreferences()
    service = _service_type()(source, repository)
    service.set_enabled(True)

    snapshot = service.snapshot(NOW)

    assert snapshot == source.value
    assert source.calls == 1
    assert repository.value.enabled is True


def test_pause_and_resume_persist_before_reset_and_sampling():
    source = FakeSource()
    service = _service_type()(source, FakePreferences(enabled=True))
    service.snapshot(NOW)

    service.set_enabled(False)
    paused = service.snapshot(NOW)
    service.set_enabled(True)
    resumed = service.snapshot(NOW)

    assert paused.state is ActivityState.UNKNOWN
    assert resumed.state is ActivityState.FOCUSED
    assert source.calls == 2
    assert source.resets == 2


def test_failed_preference_write_preserves_effective_state_and_source_interval():
    source = FakeSource()
    repository = FakePreferences(enabled=True)
    service = _service_type()(source, repository)
    repository.fail_save = True

    with pytest.raises(StorageError):
        service.set_enabled(False)

    assert service.snapshot(NOW).state is ActivityState.FOCUSED
    assert source.resets == 0
    assert repository.value.enabled is True


def test_unsupported_source_cannot_be_enabled():
    source = FakeSource(available=False)
    repository = FakePreferences()
    service = _service_type()(source, repository)

    with pytest.raises(ValidationError):
        service.set_enabled(True)

    assert repository.saves == 0
    assert service.snapshot(NOW).state is ActivityState.UNKNOWN


def test_source_failure_resets_and_degrades_to_unknown():
    source = FakeSource()
    service = _service_type()(source, FakePreferences(enabled=True))
    source.failure = OSError("private OS detail")

    snapshot = service.snapshot(NOW)

    assert snapshot.state is ActivityState.UNKNOWN
    assert source.resets == 1


def test_preference_load_failure_starts_disabled_and_fails_closed():
    source = FakeSource()
    repository = FakePreferences(enabled=True)
    repository.fail_read = True
    service = _service_type()(source, repository)

    snapshot = service.snapshot(NOW)

    assert snapshot.state is ActivityState.UNKNOWN
    assert source.calls == 0


def test_reset_failure_keeps_awareness_disabled():
    source = FakeSource()
    source.reset_failure = True
    service = _service_type()(source, FakePreferences())

    with pytest.raises(StorageError):
        service.set_enabled(True)
    snapshot = service.snapshot(NOW)

    assert snapshot.state is ActivityState.UNKNOWN
    assert source.calls == 0
    assert service.get_preferences().enabled is False
