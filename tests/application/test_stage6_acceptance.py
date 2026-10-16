from datetime import datetime, timezone

from companion.application.activity_awareness_service import ActivityAwarenessService
from companion.domain.activity import ActivityAwarenessPreferences
from companion.domain.reminders import ActivitySnapshot, ActivityState
from companion.infrastructure.sqlite.activity_preferences import SQLiteActivityPreferencesRepository
from companion.infrastructure.sqlite.database import SQLiteDatabase


NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)


class FakeActivitySource:
    available = True

    def __init__(self):
        self.calls = 0
        self.resets = 0

    def snapshot(self, at):
        self.calls += 1
        return ActivitySnapshot(ActivityState.FOCUSED, at, at)

    def reset(self):
        self.resets += 1


def test_activity_awareness_survives_pause_and_restart_without_history(tmp_path):
    database = SQLiteDatabase(tmp_path / "stage6.sqlite3")
    database.initialize()
    preferences = SQLiteActivityPreferencesRepository(database)
    first_source = FakeActivitySource()
    awareness = ActivityAwarenessService(first_source, preferences)

    assert awareness.get_preferences() == ActivityAwarenessPreferences(enabled=False)
    assert awareness.snapshot(NOW).state is ActivityState.UNKNOWN
    assert first_source.calls == 0

    awareness.set_enabled(True)
    assert awareness.snapshot(NOW).state is ActivityState.FOCUSED
    assert first_source.calls == 1

    awareness.set_enabled(False)
    assert awareness.snapshot(NOW).state is ActivityState.UNKNOWN
    assert first_source.calls == 1

    restarted_source = FakeActivitySource()
    restarted = ActivityAwarenessService(restarted_source, SQLiteActivityPreferencesRepository(database))
    assert restarted.get_preferences().enabled is False
    assert restarted.snapshot(NOW).state is ActivityState.UNKNOWN
    assert restarted_source.calls == 0

    with database.connection() as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(activity_preferences)")}
        row = connection.execute("SELECT enabled FROM activity_preferences WHERE id = 1").fetchone()
    assert columns == {"id", "enabled"}
    assert row[0] == 0