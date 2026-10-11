import sqlite3
from datetime import datetime, timezone


LATEST_SCHEMA_VERSION = 4

CREATE_SCHEMA_MIGRATIONS_TABLE = (
    "CREATE TABLE IF NOT EXISTS schema_migrations ("
    "version INTEGER PRIMARY KEY CHECK(version > 0), applied_at TEXT NOT NULL)"
)

CREATE_GOALS = (
    "CREATE TABLE goals ("
    "id TEXT PRIMARY KEY, "
    "name TEXT NOT NULL CHECK(length(trim(name)) > 0), "
    "target TEXT, "
    "priority INTEGER NOT NULL CHECK(typeof(priority) = 'integer' AND priority BETWEEN 0 AND 2), "
    "active INTEGER NOT NULL CHECK(typeof(active) = 'integer' AND active IN (0, 1)), "
    "created_at TEXT NOT NULL)"
)

CREATE_TASKS = (
    "CREATE TABLE tasks ("
    "id TEXT PRIMARY KEY, "
    "title TEXT NOT NULL CHECK(length(trim(title)) > 0), "
    "goal_id TEXT NOT NULL REFERENCES goals(id) ON DELETE RESTRICT, "
    "due_date TEXT NOT NULL, "
    "planned_minutes INTEGER NOT NULL "
    "CHECK(typeof(planned_minutes) = 'integer' AND planned_minutes >= 0), "
    "completed_units INTEGER NOT NULL "
    "CHECK(typeof(completed_units) = 'integer' AND completed_units >= 0), "
    "target_units INTEGER CHECK(target_units IS NULL OR "
    "(typeof(target_units) = 'integer' AND target_units > 0)), "
    "priority INTEGER NOT NULL "
    "CHECK(typeof(priority) = 'integer' AND priority BETWEEN 0 AND 2), "
    "hard_start TEXT, hard_end TEXT, "
    "status TEXT NOT NULL CHECK(status IN ('open', 'completed')), "
    "created_at TEXT NOT NULL, "
    "CHECK(target_units IS NULL OR completed_units <= target_units), "
    "CHECK(hard_end IS NULL OR hard_start IS NULL OR hard_end >= hard_start))"
)

CREATE_MEMORIES = (
    "CREATE TABLE memories ("
    "id TEXT PRIMARY KEY, "
    "kind TEXT NOT NULL CHECK(kind IN "
    "('profile', 'preference', 'behavioral', 'episodic', 'conversation')), "
    "content TEXT NOT NULL CHECK(length(trim(content)) > 0), "
    "source TEXT, "
    "importance INTEGER NOT NULL "
    "CHECK(typeof(importance) = 'integer' AND importance BETWEEN 0 AND 5), "
    "created_at TEXT NOT NULL, expires_at TEXT)"
)

CREATE_CONVERSATIONS = (
    "CREATE TABLE conversations ("
    "id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
)

CREATE_MESSAGES = (
    "CREATE TABLE messages ("
    "id TEXT PRIMARY KEY, "
    "conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE, "
    "role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL)"
)

CREATE_SETTINGS = (
    "CREATE TABLE settings ("
    "key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL, "
    "CHECK(instr(lower(key), 'api_key') = 0 AND "
    "instr(lower(key), 'token') = 0 AND instr(lower(key), 'secret') = 0 AND "
    "instr(lower(key), 'password') = 0))"
)

CREATE_REMINDERS = (
    "CREATE TABLE reminders ("
    "id TEXT PRIMARY KEY, reason TEXT NOT NULL, created_at TEXT NOT NULL, "
    "cooldown_until TEXT NOT NULL, extension_deadline TEXT NOT NULL, status TEXT NOT NULL)"
)

CREATE_TASK_INDEXES = (
    "CREATE INDEX idx_tasks_day_priority_deadline_created "
    "ON tasks(due_date, priority, hard_end, created_at, id)",
)
CREATE_MEMORY_INDEXES = (
    "CREATE INDEX idx_memories_kind_source_importance_created "
    "ON memories(kind, source, importance DESC, created_at DESC, id)",
    "CREATE INDEX idx_memories_expires_at ON memories(expires_at)",
)

VERSION_ONE_STATEMENTS = (
    CREATE_GOALS,
    CREATE_TASKS,
    CREATE_MEMORIES,
    CREATE_CONVERSATIONS,
    CREATE_MESSAGES,
    CREATE_SETTINGS,
    CREATE_REMINDERS,
    *CREATE_TASK_INDEXES,
    *CREATE_MEMORY_INDEXES,
)
VERSION_TWO_STATEMENTS = (
    "ALTER TABLE tasks ADD COLUMN planned_start_at TEXT",
    "CREATE TABLE task_reminder_state ("
    "task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE, "
    "local_date TEXT NOT NULL, last_action TEXT, next_evaluate_at TEXT, "
    "extension_count INTEGER NOT NULL DEFAULT 0 "
    "CHECK(typeof(extension_count) = 'integer' AND extension_count IN (0, 1)), "
    "last_shown_at TEXT, skipped_today INTEGER NOT NULL DEFAULT 0 "
    "CHECK(typeof(skipped_today) = 'integer' AND skipped_today IN (0, 1)), "
    "snooze_until TEXT, extension_until TEXT, PRIMARY KEY(task_id, local_date))",
    "CREATE TABLE reminder_runtime_state ("
    "id INTEGER PRIMARY KEY CHECK(id = 1), last_shown_at TEXT)",
    "INSERT INTO reminder_runtime_state(id, last_shown_at) VALUES (1, NULL)",
    "CREATE TABLE reminder_events ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL, "
    "local_date TEXT NOT NULL, occurred_at TEXT NOT NULL, kind TEXT NOT NULL, "
    "reason_code TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE)",
    "CREATE INDEX idx_tasks_planned_start ON tasks(planned_start_at)",
    "CREATE INDEX idx_reminder_events_local_date ON reminder_events(local_date, occurred_at)",
)
VERSION_THREE_STATEMENTS = (
    "CREATE TABLE academic_terms ("
    "id TEXT PRIMARY KEY CHECK(length(trim(id)) > 0), "
    "name TEXT NOT NULL CHECK(length(trim(name)) > 0), "
    "start_date TEXT NOT NULL CHECK(date(start_date, '+0 days') IS NOT NULL AND date(start_date, '+0 days') = start_date), "
    "end_date TEXT NOT NULL CHECK(date(end_date, '+0 days') IS NOT NULL AND date(end_date, '+0 days') = end_date), "
    "week_one_start TEXT NOT NULL CHECK(date(week_one_start, '+0 days') IS NOT NULL AND date(week_one_start, '+0 days') = week_one_start), "
    "CHECK(end_date >= start_date), "
    "CHECK(week_one_start <= start_date), "
    "CHECK(julianday(end_date) - julianday(week_one_start) < 371))",
    "CREATE TABLE course_rules ("
    "id TEXT PRIMARY KEY CHECK(length(trim(id)) > 0), "
    "term_id TEXT NOT NULL REFERENCES academic_terms(id) ON DELETE CASCADE, "
    "weekday INTEGER NOT NULL CHECK(typeof(weekday) = 'integer' AND weekday BETWEEN 0 AND 6), "
    "start_week INTEGER NOT NULL CHECK(typeof(start_week) = 'integer' AND start_week BETWEEN 1 AND 53), "
    "end_week INTEGER NOT NULL CHECK(typeof(end_week) = 'integer' AND end_week BETWEEN start_week AND 53), "
    "week_parity TEXT NOT NULL CHECK(week_parity IN ('all', 'odd', 'even')), "
    "start_time TEXT NOT NULL CHECK(time(start_time) IS NOT NULL AND time(start_time) = start_time "
    "AND substr(start_time, 1, 2) BETWEEN '00' AND '23'), "
    "end_time TEXT NOT NULL CHECK(time(end_time) IS NOT NULL AND time(end_time) = end_time "
    "AND substr(end_time, 1, 2) BETWEEN '00' AND '23'), "
    "course_name TEXT NOT NULL CHECK(length(trim(course_name)) > 0), "
    "CHECK(end_time > start_time))",
    "CREATE TABLE calendar_exceptions ("
    "term_id TEXT NOT NULL REFERENCES academic_terms(id) ON DELETE CASCADE, "
    "day TEXT NOT NULL CHECK(date(day, '+0 days') IS NOT NULL AND date(day, '+0 days') = day), "
    "kind TEXT NOT NULL CHECK(kind IN ('holiday', 'rest', 'makeup')), "
    "replacement_weekday INTEGER, note TEXT, "
    "PRIMARY KEY(term_id, day), "
    "CHECK((kind = 'makeup' AND typeof(replacement_weekday) = 'integer' "
    "AND replacement_weekday BETWEEN 0 AND 6) OR "
    "(kind IN ('holiday', 'rest') AND replacement_weekday IS NULL)))",
    "CREATE INDEX idx_academic_terms_dates ON academic_terms(start_date, end_date, id)",
    "CREATE INDEX idx_course_rules_schedule ON course_rules(term_id, weekday, start_week, week_parity, start_time, id)",
)
VERSION_FOUR_STATEMENTS = (
    "ALTER TABLE messages ADD COLUMN delivery_state TEXT NOT NULL DEFAULT 'sent' "
    "CHECK(delivery_state IN ('pending', 'sent', 'failed'))",
)
MIGRATIONS = (
    (1, VERSION_ONE_STATEMENTS),
    (2, VERSION_TWO_STATEMENTS),
    (3, VERSION_THREE_STATEMENTS),
    (4, VERSION_FOUR_STATEMENTS),
)


def read_schema_version(connection: sqlite3.Connection) -> int:
    return connection.execute(
        "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
    ).fetchone()[0]


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def apply_migrations(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute(CREATE_SCHEMA_MIGRATIONS_TABLE)
        current = read_schema_version(connection)
        for version, statements in MIGRATIONS:
            if version > current:
                for statement in statements:
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (version, utc_timestamp()),
                )
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
