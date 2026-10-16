from datetime import datetime

from companion.domain.activity import ActivityAwarenessPreferences
from companion.domain.errors import StorageError, ValidationError
from companion.domain.reminders import ActivitySnapshot, ActivityState
from companion.ports.activity import ActivityPreferencesRepository, ResettableActivitySource


class ActivityAwarenessService:
    """Apply the user's local activity-awareness preference to one source."""

    def __init__(
        self,
        source: ResettableActivitySource,
        preferences: ActivityPreferencesRepository,
    ) -> None:
        self.source = source
        self.preferences = preferences
        self._preferences = ActivityAwarenessPreferences()
        self._enabled = False
        try:
            stored = self.preferences.get()
            if isinstance(stored, ActivityAwarenessPreferences):
                self._preferences = stored
                self._enabled = stored.enabled and self._source_available()
        except Exception:
            # A failed settings read must never start activity sensing.
            self._preferences = ActivityAwarenessPreferences()
            self._enabled = False

    @property
    def available(self) -> bool:
        return self._source_available()

    def get_preferences(self) -> ActivityAwarenessPreferences:
        preferences = self.preferences.get()
        if not isinstance(preferences, ActivityAwarenessPreferences):
            raise StorageError("Stored activity awareness preference is invalid.")
        if preferences != self._preferences:
            self._apply(preferences)
        return preferences

    def set_enabled(self, enabled: bool) -> ActivityAwarenessPreferences:
        updated = ActivityAwarenessPreferences(enabled=enabled)
        if updated.enabled and not self._source_available():
            raise ValidationError("Activity awareness is unavailable on this device.")
        previous = self._preferences
        self.preferences.save(updated)
        try:
            self._apply(updated)
        except StorageError:
            try:
                self.preferences.save(previous)
            finally:
                self._preferences = previous
                self._enabled = previous.enabled and self._source_available()
            raise
        return updated

    def snapshot(self, at: datetime) -> ActivitySnapshot:
        if not self._enabled or not self._source_available():
            return ActivitySnapshot(ActivityState.UNKNOWN, at, at)
        try:
            snapshot = self.source.snapshot(at)
            if not isinstance(snapshot, ActivitySnapshot):
                raise ValidationError("Activity source returned an invalid snapshot.")
            return snapshot
        except Exception:
            if not self._reset_source():
                self._enabled = False
            return ActivitySnapshot(ActivityState.UNKNOWN, at, at)

    def _apply(self, preferences: ActivityAwarenessPreferences) -> None:
        effective_enabled = preferences.enabled and self._source_available()
        if effective_enabled != self._enabled:
            if not self._reset_source():
                if effective_enabled:
                    raise StorageError("Activity awareness could not be reset safely.")
                effective_enabled = False
        self._preferences = preferences
        self._enabled = effective_enabled

    def _source_available(self) -> bool:
        try:
            return self.source.available is True
        except Exception:
            return False

    def _reset_source(self) -> bool:
        try:
            self.source.reset()
            return True
        except Exception:
            return False
