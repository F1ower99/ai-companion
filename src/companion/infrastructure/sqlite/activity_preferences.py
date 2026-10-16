from companion.domain.activity import ActivityAwarenessPreferences
from companion.domain.errors import StorageError, ValidationError
from companion.infrastructure.sqlite.database import SQLiteDatabase
from companion.ports.activity import ActivityPreferencesRepository


class SQLiteActivityPreferencesRepository(ActivityPreferencesRepository):
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def get(self) -> ActivityAwarenessPreferences:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT enabled FROM activity_preferences WHERE id = 1"
            ).fetchone()
        if row is None:
            return ActivityAwarenessPreferences()
        enabled = row["enabled"]
        if type(enabled) is not int or enabled not in (0, 1):
            raise StorageError("Stored activity awareness preference is invalid.")
        return ActivityAwarenessPreferences(enabled=bool(enabled))

    def save(self, preferences: ActivityAwarenessPreferences) -> None:
        if not isinstance(preferences, ActivityAwarenessPreferences):
            raise ValidationError("Validated activity awareness preferences are required.")
        with self.database.connection() as connection:
            connection.execute(
                "INSERT INTO activity_preferences(id, enabled) VALUES (1, ?) "
                "ON CONFLICT(id) DO UPDATE SET enabled = excluded.enabled",
                (int(preferences.enabled),),
            )
