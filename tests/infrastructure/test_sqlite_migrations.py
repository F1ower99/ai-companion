import sqlite3
from pathlib import Path

import pytest

import companion.infrastructure.sqlite.migrations as migrations_module
from companion.infrastructure.sqlite.migrations import LATEST_SCHEMA_VERSION, apply_migrations
from companion.infrastructure.sqlite.database import SQLiteDatabase, default_database_path
from companion.domain.errors import StorageError


@pytest.fixture
def migrated_connection(tmp_path):
    connection = sqlite3.connect(tmp_path / "companion.sqlite3")
    connection.execute("PRAGMA foreign_keys = ON")
    apply_migrations(connection)
    try:
        yield connection
    finally:
        connection.close()


def add_goal(connection, goal_id="g1"):
    connection.execute(
        "INSERT INTO goals(id, name, target, priority, active, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (goal_id, "Study", None, 1, 1, "2026-09-24T00:00:00+00:00"),
    )


def add_task(connection, task_id="t1", goal_id="g1"):
    connection.execute(
        "INSERT INTO tasks(id, title, goal_id, due_date, planned_minutes, "
        "completed_units, target_units, priority, hard_start, hard_end, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            task_id, "Read", goal_id, "2026-09-24", 30, 0, None, 1,
            None, None, "open", "2026-09-24T00:00:00+00:00",
        ),
    )


def test_latest_schema_creates_stage_two_three_and_reminder_tables(migrated_connection):
    names = {
        row[0]
        for row in migrated_connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert {
        "goals", "tasks", "memories", "conversations", "messages",
        "settings", "reminders", "schema_migrations",
    } <= names
    assert {"task_reminder_state", "reminder_runtime_state", "reminder_events"} <= names
    assert {"academic_terms", "course_rules", "calendar_exceptions"} <= names
    assert migrated_connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 4
    assert LATEST_SCHEMA_VERSION == 4


def test_migration_is_idempotent(migrated_connection):
    apply_migrations(migrated_connection)
    assert migrated_connection.execute(
        "SELECT COUNT(*) FROM schema_migrations WHERE version = 2"
    ).fetchone()[0] == 1


def test_v1_data_upgrades_to_v4_with_stage_two_three_and_placeholder_preserved(tmp_path):
    connection = sqlite3.connect(tmp_path / "v1.sqlite3")
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        connection.execute(migrations_module.CREATE_SCHEMA_MIGRATIONS_TABLE)
        for statement in migrations_module.VERSION_ONE_STATEMENTS:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (1, ?)",
            ("2026-09-24T00:00:00+00:00",),
        )
        add_goal(connection)
        add_task(connection)
        connection.execute(
            "INSERT INTO reminders(id, reason, created_at, cooldown_until, extension_deadline, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("legacy", "placeholder", "2026-09-24T00:00:00+00:00", "later", "later", "pending"),
        )
        connection.commit()
        apply_migrations(connection)
        assert migrations_module.read_schema_version(connection) == 4
        columns = {row[1] for row in connection.execute("PRAGMA table_info(tasks)")}
        assert "planned_start_at" in columns
        assert connection.execute("SELECT planned_start_at FROM tasks WHERE id='t1'").fetchone()[0] is None
        assert connection.execute("SELECT reason FROM reminders WHERE id='legacy'").fetchone()[0] == "placeholder"
        names = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {
            "task_reminder_state", "reminder_runtime_state", "reminder_events",
            "academic_terms", "course_rules", "calendar_exceptions",
        } <= names
    finally:
        connection.close()


def test_v2_upgrade_preserves_task_reminder_rows_and_existing_table_definitions(
    tmp_path, monkeypatch,
):
    connection = sqlite3.connect(tmp_path / "v2-upgrade.sqlite3")
    connection.execute("PRAGMA foreign_keys = ON")
    original_migrations = migrations_module.MIGRATIONS
    try:
        monkeypatch.setattr(migrations_module, "MIGRATIONS", original_migrations[:2])
        apply_migrations(connection)
        add_goal(connection)
        add_task(connection)
        connection.execute(
            "INSERT INTO task_reminder_state(task_id, local_date, last_action, next_evaluate_at, "
            "extension_count, last_shown_at, skipped_today, snooze_until, extension_until) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("t1", "2026-09-24", "later", "2026-09-24T13:00:00+00:00", 0,
             "2026-09-24T12:00:00+00:00", 0, "2026-09-24T13:00:00+00:00", None),
        )
        connection.execute(
            "INSERT INTO reminder_events(task_id, local_date, occurred_at, kind, reason_code, idempotency_key) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("t1", "2026-09-24", "2026-09-24T12:00:00+00:00", "displayed", "deadline_risk", "keep-event"),
        )
        connection.commit()
        v1_statements = migrations_module.VERSION_ONE_STATEMENTS
        v2_statements = migrations_module.VERSION_TWO_STATEMENTS
        monkeypatch.setattr(migrations_module, "MIGRATIONS", original_migrations)
        apply_migrations(connection)
        assert migrations_module.read_schema_version(connection) == 4
        assert connection.execute("SELECT title FROM tasks WHERE id='t1'").fetchone()[0] == "Read"
        assert connection.execute(
            "SELECT snooze_until FROM task_reminder_state WHERE task_id='t1'"
        ).fetchone()[0] == "2026-09-24T13:00:00+00:00"
        assert connection.execute(
            "SELECT idempotency_key FROM reminder_events WHERE idempotency_key='keep-event'"
        ).fetchone()[0] == "keep-event"
        assert migrations_module.VERSION_ONE_STATEMENTS == v1_statements
        assert migrations_module.VERSION_TWO_STATEMENTS == v2_statements
    finally:
        connection.close()


def test_v3_conversation_rows_upgrade_with_sent_delivery_state(tmp_path, monkeypatch):
    connection = sqlite3.connect(tmp_path / "v3-chat.sqlite3")
    connection.execute("PRAGMA foreign_keys = ON")
    original_migrations = migrations_module.MIGRATIONS
    try:
        monkeypatch.setattr(migrations_module, "MIGRATIONS", original_migrations[:3])
        apply_migrations(connection)
        connection.execute(
            "INSERT INTO conversations(id, created_at, updated_at) VALUES (?, ?, ?)",
            ("c1", "2026-10-11T04:00:00+00:00", "2026-10-11T04:00:00+00:00"),
        )
        connection.execute(
            "INSERT INTO messages(id, conversation_id, role, content, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("m1", "c1", "user", "legacy", "2026-10-11T04:01:00+00:00"),
        )
        connection.commit()

        monkeypatch.setattr(migrations_module, "MIGRATIONS", original_migrations)
        apply_migrations(connection)
        assert migrations_module.read_schema_version(connection) == 4
        assert connection.execute(
            "SELECT delivery_state FROM messages WHERE id = 'm1'"
        ).fetchone()[0] == "sent"
        columns = {row[1] for row in connection.execute("PRAGMA table_info(messages)")}
        assert "delivery_state" in columns
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO messages(id, conversation_id, role, content, created_at, delivery_state) "
                "VALUES ('bad', 'c1', 'user', 'bad', '2026-10-11T04:02:00+00:00', 'unknown')"
            )
    finally:
        connection.close()


def test_failed_v3_migration_rolls_back_all_v3_tables_to_v2(tmp_path, monkeypatch):
    connection = sqlite3.connect(tmp_path / "v3-broken-upgrade.sqlite3")
    try:
        existing_migrations = migrations_module.MIGRATIONS
        v2_migrations = existing_migrations[:2]
        monkeypatch.setattr(migrations_module, "MIGRATIONS", v2_migrations)
        apply_migrations(connection)
        monkeypatch.setattr(
            migrations_module,
            "MIGRATIONS",
            (*v2_migrations, (3, (
                "CREATE TABLE academic_terms (id TEXT PRIMARY KEY)",
                "CREATE TABLE invalid_v3 (",
            ))),
        )
        with pytest.raises(sqlite3.OperationalError):
            apply_migrations(connection)
        assert migrations_module.read_schema_version(connection) == 2
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='academic_terms'"
        ).fetchone() is None
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='task_reminder_state'"
        ).fetchone() is not None
    finally:
        connection.close()


def test_v3_constraints_cover_week_rules_exception_shapes_and_term_cascade(migrated_connection):
    migrated_connection.execute(
        "INSERT INTO academic_terms(id, name, start_date, end_date, week_one_start) "
        "VALUES (?, ?, ?, ?, ?)",
        ("fall", "Fall", "2026-09-01", "2026-12-31", "2026-08-31"),
    )
    with pytest.raises(sqlite3.IntegrityError):
        migrated_connection.execute(
            "INSERT INTO academic_terms(id, name, start_date, end_date, week_one_start) "
            "VALUES (?, ?, ?, ?, ?)",
            ("bad-date", "Bad date", "invalid", "invalid", "invalid"),
        )
    with pytest.raises(sqlite3.IntegrityError):
        migrated_connection.execute(
            "INSERT INTO academic_terms(id, name, start_date, end_date, week_one_start) "
            "VALUES (?, ?, ?, ?, ?)",
            ("impossible-date", "Impossible date", "2026-02-30", "2026-03-30", "2026-02-23"),
        )
    with pytest.raises(sqlite3.IntegrityError):
        migrated_connection.execute(
            "INSERT INTO course_rules(id, term_id, weekday, start_week, end_week, week_parity, "
            "start_time, end_time, course_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("bad-weekday", "fall", 7, 1, 16, "all", "09:00:00", "10:00:00", "Math"),
        )
    with pytest.raises(sqlite3.IntegrityError):
        migrated_connection.execute(
            "INSERT INTO calendar_exceptions(term_id, day, kind, replacement_weekday, note) "
            "VALUES (?, ?, ?, ?, ?)",
            ("fall", "2026-09-05", "makeup", None, None),
        )
    with pytest.raises(sqlite3.IntegrityError):
        migrated_connection.execute(
            "INSERT INTO calendar_exceptions(term_id, day, kind, replacement_weekday, note) "
            "VALUES (?, ?, ?, ?, ?)",
            ("fall", "invalid", "rest", None, None),
        )
    with pytest.raises(sqlite3.IntegrityError):
        migrated_connection.execute(
            "INSERT INTO calendar_exceptions(term_id, day, kind, replacement_weekday, note) "
            "VALUES (?, ?, ?, ?, ?)",
            ("fall", "2026-02-30", "rest", None, None),
        )
    with pytest.raises(sqlite3.IntegrityError):
        migrated_connection.execute(
            "INSERT INTO course_rules(id, term_id, weekday, start_week, end_week, week_parity, "
            "start_time, end_time, course_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("bad-time", "fall", 0, 1, 16, "all", "09:00:00x", "09:00:00y", "Math"),
        )
    with pytest.raises(sqlite3.IntegrityError):
        migrated_connection.execute(
            "INSERT INTO course_rules(id, term_id, weekday, start_week, end_week, week_parity, "
            "start_time, end_time, course_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("bad-hour", "fall", 0, 1, 16, "all", "23:00:00", "24:00:00", "Math"),
        )
    migrated_connection.execute(
        "INSERT INTO calendar_exceptions(term_id, day, kind, replacement_weekday, note) "
        "VALUES (?, ?, ?, ?, ?)",
        ("fall", "2026-09-05", "makeup", 0, None),
    )
    with pytest.raises(sqlite3.IntegrityError):
        migrated_connection.execute(
            "INSERT INTO calendar_exceptions(term_id, day, kind, replacement_weekday, note) "
            "VALUES (?, ?, ?, ?, ?)",
            ("fall", "2026-09-05", "rest", None, "duplicate date"),
        )
    assert migrated_connection.execute(
        "PRAGMA foreign_key_list(course_rules)"
    ).fetchone()[6] == "CASCADE"
    migrated_connection.execute(
        "INSERT INTO course_rules(id, term_id, weekday, start_week, end_week, week_parity, "
        "start_time, end_time, course_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("math", "fall", 0, 1, 16, "all", "09:00:00", "10:00:00", "Math"),
    )
    migrated_connection.execute("DELETE FROM academic_terms WHERE id = 'fall'")
    assert migrated_connection.execute("SELECT COUNT(*) FROM course_rules").fetchone()[0] == 0
    assert migrated_connection.execute("SELECT COUNT(*) FROM calendar_exceptions").fetchone()[0] == 0


def test_failed_v2_migration_rolls_back_to_v1(tmp_path, monkeypatch):
    connection = sqlite3.connect(tmp_path / "v1-broken-upgrade.sqlite3")
    try:
        monkeypatch.setattr(migrations_module, "MIGRATIONS", ((1, migrations_module.VERSION_ONE_STATEMENTS),))
        apply_migrations(connection)
        monkeypatch.setattr(
            migrations_module,
            "MIGRATIONS",
            (
                (1, migrations_module.VERSION_ONE_STATEMENTS),
                (2, ("ALTER TABLE tasks ADD COLUMN planned_start_at TEXT", "CREATE TABLE broken (")),
            ),
        )
        with pytest.raises(sqlite3.OperationalError):
            apply_migrations(connection)
        assert migrations_module.read_schema_version(connection) == 1
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'"
        ).fetchone() is not None
        columns = {row[1] for row in connection.execute("PRAGMA table_info(tasks)")}
        assert "planned_start_at" not in columns
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='task_reminder_state'"
        ).fetchone() is None
    finally:
        connection.close()


@pytest.mark.parametrize(
    "sql, parameters",
    [
        (
            "INSERT INTO goals(id, name, priority, active, created_at) VALUES (?, ?, ?, ?, ?)",
            ("g2", "Bad priority", 3, 1, "2026-09-24T00:00:00+00:00"),
        ),
        (
            "INSERT INTO goals(id, name, priority, active, created_at) VALUES (?, ?, ?, ?, ?)",
            ("g2", " ", 1, 1, "2026-09-24T00:00:00+00:00"),
        ),
    ],
)
def test_goal_check_constraints_reject_invalid_rows(migrated_connection, sql, parameters):
    with pytest.raises(sqlite3.IntegrityError):
        migrated_connection.execute(sql, parameters)


def test_task_check_constraints_and_goal_foreign_key(migrated_connection):
    add_goal(migrated_connection)
    with pytest.raises(sqlite3.IntegrityError):
        add_task(migrated_connection, goal_id="missing")
    with pytest.raises(sqlite3.IntegrityError):
        migrated_connection.execute(
            "INSERT INTO tasks(id, title, goal_id, due_date, planned_minutes, completed_units, "
            "target_units, priority, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("bad", "Bad", "g1", "2026-09-24", -1, 0, 1, 1, "open", "now"),
        )
    with pytest.raises(sqlite3.IntegrityError):
        migrated_connection.execute(
            "INSERT INTO tasks(id, title, goal_id, due_date, planned_minutes, completed_units, "
            "target_units, priority, hard_start, hard_end, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "bad-time", "Bad", "g1", "2026-09-24", 1, 0, 1, 1,
                "2026-09-24T12:00:00+00:00", "2026-09-24T11:00:00+00:00",
                "open", "2026-09-24T00:00:00+00:00",
            ),
        )


def test_goal_delete_is_restricted_while_task_exists(migrated_connection):
    add_goal(migrated_connection)
    add_task(migrated_connection)
    with pytest.raises(sqlite3.IntegrityError):
        migrated_connection.execute("DELETE FROM goals WHERE id = ?", ("g1",))


def test_message_delete_cascades_with_conversation(migrated_connection):
    migrated_connection.execute(
        "INSERT INTO conversations(id, created_at, updated_at) VALUES (?, ?, ?)",
        ("c1", "2026-09-24T00:00:00+00:00", "2026-09-24T00:00:00+00:00"),
    )
    migrated_connection.execute(
        "INSERT INTO messages(id, conversation_id, role, content, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("m1", "c1", "user", "hello", "2026-09-24T00:00:00+00:00"),
    )
    migrated_connection.execute("DELETE FROM conversations WHERE id = ?", ("c1",))
    assert migrated_connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0


@pytest.mark.parametrize("key", ["API_KEY", "model.token", "mySecret", "PASSWORD"])
def test_settings_reject_credential_key_names(migrated_connection, key):
    with pytest.raises(sqlite3.IntegrityError):
        migrated_connection.execute(
            "INSERT INTO settings(key, value, updated_at) VALUES (?, ?, ?)",
            (key, "redacted", "2026-09-24T00:00:00+00:00"),
        )


def test_failed_migration_rolls_back_ddl_and_version(tmp_path, monkeypatch):
    connection = sqlite3.connect(tmp_path / "broken.sqlite3")
    connection.execute("CREATE TABLE legacy (id TEXT PRIMARY KEY, value TEXT)")
    connection.execute("INSERT INTO legacy VALUES (?, ?)", ("existing", "preserved"))
    connection.commit()
    try:
        monkeypatch.setattr(
            migrations_module,
            "MIGRATIONS",
            (
                (
                    1,
                    (
                        migrations_module.CREATE_GOALS,
                        migrations_module.CREATE_TASKS,
                        "CREATE TABLE incomplete (",
                    ),
                ),
            ),
        )
        with pytest.raises(sqlite3.OperationalError):
            apply_migrations(connection)
        names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert names == {"legacy"}
        assert connection.execute("SELECT * FROM legacy").fetchall() == [("existing", "preserved")]
    finally:
        connection.close()


def test_default_database_path_uses_localappdata(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert default_database_path() == tmp_path / "AICompanion" / "companion.sqlite3"


def test_default_database_path_falls_back_to_user_local(monkeypatch):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert default_database_path() == Path.home() / "AppData" / "Local" / "AICompanion" / "companion.sqlite3"


def test_connection_enables_foreign_keys_and_reopens(tmp_path):
    db = SQLiteDatabase(tmp_path / "AICompanion" / "companion.sqlite3")
    with db.connection() as first:
        first.execute(
            "INSERT INTO goals(id, name, priority, active, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("g1", "Study", 1, 1, "2026-09-24T00:00:00+00:00"),
        )
        assert first.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert first.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    with db.connection() as second:
        assert second.execute(
            "SELECT name FROM goals WHERE id = ?", ("g1",)
        ).fetchone()["name"] == "Study"


def test_connection_rolls_back_and_preserves_business_error(tmp_path):
    db = SQLiteDatabase(tmp_path / "companion.sqlite3")
    with pytest.raises(RuntimeError, match="business failure"):
        with db.connection() as connection:
            connection.execute(
                "INSERT INTO goals(id, name, priority, active, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                ("g1", "Study", 1, 1, "2026-09-24T00:00:00+00:00"),
            )
            raise RuntimeError("business failure")
    with db.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM goals").fetchone()[0] == 0


def test_database_open_error_is_sanitized(tmp_path):
    path_is_a_directory = tmp_path / "not-a-file.sqlite3"
    path_is_a_directory.mkdir()
    db = SQLiteDatabase(path_is_a_directory)
    with pytest.raises(StorageError) as error:
        db.initialize()
    assert str(path_is_a_directory) not in str(error.value)
