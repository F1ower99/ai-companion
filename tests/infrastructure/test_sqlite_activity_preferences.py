import importlib
import importlib.util
import sqlite3

import pytest

from companion.domain.errors import StorageError
from companion.infrastructure.sqlite.database import SQLiteDatabase


def _repository_type():
    spec = importlib.util.find_spec("companion.infrastructure.sqlite.activity_preferences")
    assert spec is not None
    module = importlib.import_module("companion.infrastructure.sqlite.activity_preferences")
    return module.SQLiteActivityPreferencesRepository


def test_activity_preferences_default_and_persist_after_reopen(tmp_path):
    database = SQLiteDatabase(tmp_path / "activity.sqlite3")
    database.initialize()
    repository_type = _repository_type()
    repository = repository_type(database)

    assert repository.get().enabled is False
    preferences_type = importlib.import_module("companion.domain.activity").ActivityAwarenessPreferences
    repository.save(preferences_type(enabled=True))

    reopened = repository_type(SQLiteDatabase(database.path))
    assert reopened.get().enabled is True


def test_activity_preferences_table_rejects_more_than_one_row(tmp_path):
    database = SQLiteDatabase(tmp_path / "single-activity-preference.sqlite3")
    database.initialize()

    with pytest.raises(StorageError):
        with database.connection() as connection:
            connection.execute(
                "INSERT INTO activity_preferences(id, enabled) VALUES (2, 1)"
            )
