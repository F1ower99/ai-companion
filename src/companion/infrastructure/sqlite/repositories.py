import sqlite3
from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone

from companion.domain.errors import NotFoundError, StorageError, ValidationError
from companion.domain.models import Goal, Memory, MemoryKind, MemoryQuery, Priority, Task, TaskStatus
from companion.domain.reminders import (
    ReminderAction,
    ReminderEvent,
    ReminderEventKind,
    ReminderPreferences,
    TaskReminderState,
)
from companion.ports.reminders import ReminderPreferencesRepository, ReminderRepository
from companion.infrastructure.sqlite.database import SQLiteDatabase


def _encode_time(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _decode_time(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValidationError("Stored timestamp is missing a timezone.")
    return parsed.astimezone(timezone.utc)


def _goal_from_row(row: sqlite3.Row) -> Goal:
    return Goal(
        id=row["id"],
        name=row["name"],
        target=row["target"],
        priority=Priority(row["priority"]),
        active=bool(row["active"]),
        created_at=_decode_time(row["created_at"]),
    )


def _task_from_row(row: sqlite3.Row) -> Task:
    return Task(
        id=row["id"],
        title=row["title"],
        goal_id=row["goal_id"],
        due_date=date.fromisoformat(row["due_date"]),
        planned_minutes=row["planned_minutes"],
        completed_units=row["completed_units"],
        target_units=row["target_units"],
        priority=Priority(row["priority"]),
        planned_start_at=_decode_time(row["planned_start_at"]),
        hard_start=_decode_time(row["hard_start"]),
        hard_end=_decode_time(row["hard_end"]),
        status=TaskStatus(row["status"]),
        created_at=_decode_time(row["created_at"]),
    )


def _memory_from_row(row: sqlite3.Row) -> Memory:
    return Memory(
        id=row["id"],
        kind=MemoryKind(row["kind"]),
        content=row["content"],
        source=row["source"],
        importance=row["importance"],
        created_at=_decode_time(row["created_at"]),
        expires_at=_decode_time(row["expires_at"]),
    )


class SQLiteGoalRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def add(self, goal: Goal) -> None:
        with self.database.connection() as connection:
            try:
                connection.execute(
                    "INSERT INTO goals(id, name, target, priority, active, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        goal.id, goal.name, goal.target, int(goal.priority),
                        int(goal.active), _encode_time(goal.created_at),
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise ValidationError("The goal could not be saved.") from error

    def get(self, goal_id: str) -> Goal | None:
        with self.database.connection() as connection:
            row = connection.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
            return _goal_from_row(row) if row is not None else None

    def list_active(self) -> list[Goal]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM goals WHERE active = 1 ORDER BY priority, created_at, id"
            ).fetchall()
            return [_goal_from_row(row) for row in rows]

    def delete(self, goal_id: str) -> None:
        with self.database.connection() as connection:
            try:
                cursor = connection.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
            except sqlite3.IntegrityError as error:
                raise ValidationError("The goal could not be deleted while it has tasks.") from error
            if cursor.rowcount == 0:
                raise NotFoundError("Goal not found.")


class SQLiteTaskRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def add(self, task: Task) -> None:
        with self.database.connection() as connection:
            try:
                connection.execute(
                    "INSERT INTO tasks(id, title, goal_id, due_date, planned_minutes, "
                    "completed_units, target_units, priority, planned_start_at, hard_start, "
                    "hard_end, status, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        task.id, task.title, task.goal_id, task.due_date.isoformat(),
                        task.planned_minutes, task.completed_units, task.target_units,
                        int(task.priority), _encode_time(task.planned_start_at),
                        _encode_time(task.hard_start), _encode_time(task.hard_end),
                        task.status.value, _encode_time(task.created_at),
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise ValidationError("The task could not be saved.") from error

    def get(self, task_id: str) -> Task | None:
        with self.database.connection() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            return _task_from_row(row) if row is not None else None

    def list_for_day(self, day: date) -> list[Task]:
        if not isinstance(day, date) or isinstance(day, datetime):
            raise ValidationError("Task listing requires a calendar date.")
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM tasks WHERE due_date = ? "
                "ORDER BY priority, CASE WHEN hard_end IS NULL THEN 1 ELSE 0 END, "
                "hard_end, created_at, id",
                (day.isoformat(),),
            ).fetchall()
            return [_task_from_row(row) for row in rows]

    def list_for_decisions(
        self, day: date, day_start_utc: datetime, next_day_start_utc: datetime
    ) -> list[Task]:
        if not isinstance(day, date) or isinstance(day, datetime):
            raise ValidationError("Task listing requires a calendar date.")
        start = _encode_time(day_start_utc)
        end = _encode_time(next_day_start_utc)
        if start is None or end is None or day_start_utc >= next_day_start_utc:
            raise ValidationError("Task listing requires an increasing aware UTC day range.")
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM tasks WHERE due_date <= ? OR "
                "(planned_start_at >= ? AND planned_start_at < ?) "
                "ORDER BY priority, CASE WHEN hard_end IS NULL THEN 1 ELSE 0 END, "
                "hard_end, created_at, id",
                (day.isoformat(), start, end),
            ).fetchall()
            return [_task_from_row(row) for row in rows]

    def set_completed_units(self, task_id: str, value: int) -> Task:
        if type(value) is not int or value < 0:
            raise ValidationError("completed_units must be a non-negative integer.")
        with self.database.connection() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                raise NotFoundError("Task not found.")
            updated = replace(_task_from_row(row), completed_units=value)
            connection.execute(
                "UPDATE tasks SET completed_units = ? WHERE id = ?", (value, task_id)
            )
            return updated

    def increment_completed_units(self, task_id: str, count: int) -> Task:
        if type(count) is not int or count <= 0:
            raise ValidationError("Progress increment must be a positive integer.")
        with self.database.connection() as connection:
            cursor = connection.execute(
                "UPDATE tasks SET completed_units = MIN(completed_units + ?, target_units) "
                "WHERE id = ? AND target_units IS NOT NULL",
                (count, task_id),
            )
            if cursor.rowcount == 0:
                row = connection.execute(
                    "SELECT target_units FROM tasks WHERE id = ?", (task_id,)
                ).fetchone()
                if row is None:
                    raise NotFoundError("Task not found.")
                raise ValidationError("This task has no unit target.")
            row = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            return _task_from_row(row)

    def mark_completed(self, task_id: str) -> Task:
        with self.database.connection() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                raise NotFoundError("Task not found.")
            task = _task_from_row(row)
            units = task.target_units if task.target_units is not None else task.completed_units
            updated = replace(task, completed_units=units, status=TaskStatus.COMPLETED)
            connection.execute(
                "UPDATE tasks SET completed_units = ?, status = ? WHERE id = ?",
                (updated.completed_units, updated.status.value, task_id),
            )
            return updated


class SQLiteMemoryRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def add(self, memory: Memory) -> None:
        with self.database.connection() as connection:
            try:
                connection.execute(
                    "INSERT INTO memories(id, kind, content, source, importance, created_at, expires_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        memory.id, memory.kind.value, memory.content, memory.source,
                        memory.importance, _encode_time(memory.created_at),
                        _encode_time(memory.expires_at),
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise ValidationError("The memory could not be saved.") from error

    def search(self, query: MemoryQuery, limit: int = 5) -> list[Memory]:
        if not isinstance(query, MemoryQuery):
            raise ValidationError("A memory query is required.")
        if type(limit) is not int or limit <= 0:
            raise ValidationError("Memory search limit must be a positive integer.")

        clauses: list[str] = []
        parameters: list[object] = []
        if query.text and query.text.strip():
            clauses.append("instr(lower(content), lower(?)) > 0")
            parameters.append(query.text.strip())
        if query.kind is not None:
            clauses.append("kind = ?")
            parameters.append(query.kind.value)
        if query.source is not None:
            clauses.append("source = ?")
            parameters.append(query.source)
        if not query.include_expired:
            clauses.append("(expires_at IS NULL OR expires_at > ?)")
            parameters.append(datetime.now(timezone.utc).isoformat())
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        parameters.append(limit)
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM memories" + where +
                " ORDER BY importance DESC, created_at DESC, id LIMIT ?",
                parameters,
            ).fetchall()
            return [_memory_from_row(row) for row in rows]

    def delete(self, memory_id: str) -> None:
        with self.database.connection() as connection:
            cursor = connection.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            if cursor.rowcount == 0:
                raise NotFoundError("Memory not found.")


class SQLiteReminderRepository(ReminderRepository):
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def get_task_states(self, local_date: date) -> list[TaskReminderState]:
        if not isinstance(local_date, date) or isinstance(local_date, datetime):
            raise ValidationError("Reminder state listing requires a local date.")
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM task_reminder_state WHERE local_date = ? ORDER BY task_id",
                (local_date.isoformat(),),
            ).fetchall()
        return [
            TaskReminderState(
                task_id=row["task_id"],
                local_date=date.fromisoformat(row["local_date"]),
                last_action=ReminderAction(row["last_action"]) if row["last_action"] else None,
                next_evaluate_at=_decode_time(row["next_evaluate_at"]),
                extension_count=row["extension_count"],
                last_shown_at=_decode_time(row["last_shown_at"]),
                skipped_today=bool(row["skipped_today"]),
                snooze_until=_decode_time(row["snooze_until"]),
                extension_until=_decode_time(row["extension_until"]),
            )
            for row in rows
        ]

    def get_last_global_shown_at(self) -> datetime | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT last_shown_at FROM reminder_runtime_state WHERE id = 1"
            ).fetchone()
        return _decode_time(row["last_shown_at"]) if row is not None else None

    def get_event_by_key(self, idempotency_key: str) -> ReminderEvent | None:
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ValidationError("idempotency_key must not be blank.")
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM reminder_events WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
        if row is None:
            return None
        return ReminderEvent(
            kind=ReminderEventKind(row["kind"]),
            task_id=row["task_id"],
            occurred_at=_decode_time(row["occurred_at"]),
            local_date=date.fromisoformat(row["local_date"]),
            reason_code=row["reason_code"],
            idempotency_key=row["idempotency_key"],
        )

    def save_state_and_event(
        self,
        state: TaskReminderState,
        event: ReminderEvent,
        global_last_shown_at: datetime | None = None,
        global_cooldown_minutes: int | None = None,
        task_cooldown_minutes: int | None = None,
        bypass_task_cooldown: bool = False,
    ) -> bool:
        if event.task_id != state.task_id or event.local_date != state.local_date:
            raise ValidationError("Reminder state and event must reference the same task date.")
        if global_cooldown_minutes is not None and (
            type(global_cooldown_minutes) is not int or global_cooldown_minutes < 0
        ):
            raise ValidationError("global_cooldown_minutes must be a non-negative integer.")
        if event.kind is ReminderEventKind.DISPLAYED and (
            global_last_shown_at is None
            or global_cooldown_minutes is None
            or task_cooldown_minutes is None
        ):
            raise ValidationError("Displayed events require atomic global and task cooldown claims.")
        if task_cooldown_minutes is not None and (
            type(task_cooldown_minutes) is not int or task_cooldown_minutes < 0
        ):
            raise ValidationError("task_cooldown_minutes must be a non-negative integer.")
        if type(bypass_task_cooldown) is not bool:
            raise ValidationError("bypass_task_cooldown must be a boolean.")
        if event.kind is ReminderEventKind.EXTENDED and state.extension_count != 1:
            raise ValidationError("An extension event must set the daily extension count to one.")
        with self.database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if event.kind is ReminderEventKind.DISPLAYED:
                state_row = connection.execute(
                    "SELECT last_action, last_shown_at, next_evaluate_at, snooze_until, extension_until "
                    "FROM task_reminder_state "
                    "WHERE task_id = ? AND local_date = ?",
                    (state.task_id, state.local_date.isoformat()),
                ).fetchone()
                if state_row is not None and state_row["last_shown_at"] is not None:
                    task_last_shown = _decode_time(state_row["last_shown_at"])
                    if bypass_task_cooldown:
                        last_action = state_row["last_action"]
                        if last_action == ReminderAction.LATER.value:
                            explicit_deadline = _decode_time(state_row["snooze_until"])
                        elif last_action == ReminderAction.EXTEND.value:
                            explicit_deadline = _decode_time(state_row["extension_until"])
                        else:
                            explicit_deadline = None
                        next_evaluate_at = _decode_time(state_row["next_evaluate_at"])
                        if (
                            explicit_deadline is None
                            or explicit_deadline > global_last_shown_at
                            or next_evaluate_at != explicit_deadline
                        ):
                            connection.rollback()
                            return False
                    elif (
                        task_last_shown + timedelta(minutes=task_cooldown_minutes)
                        > global_last_shown_at
                    ):
                        connection.rollback()
                        return False
            if event.kind is ReminderEventKind.EXTENDED:
                row = connection.execute(
                    "SELECT extension_count FROM task_reminder_state "
                    "WHERE task_id = ? AND local_date = ?",
                    (state.task_id, state.local_date.isoformat()),
                ).fetchone()
                if row is not None and row["extension_count"] >= 1:
                    connection.rollback()
                    return False
            if global_last_shown_at is not None and global_cooldown_minutes is not None:
                row = connection.execute(
                    "SELECT last_shown_at FROM reminder_runtime_state WHERE id = 1"
                ).fetchone()
                current = _decode_time(row["last_shown_at"]) if row is not None else None
                if (
                    current is not None
                    and current + timedelta(minutes=global_cooldown_minutes) > global_last_shown_at
                ):
                    connection.rollback()
                    return False
            cursor = connection.execute(
                "INSERT OR IGNORE INTO reminder_events(task_id, local_date, occurred_at, kind, "
                "reason_code, idempotency_key) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    event.task_id, event.local_date.isoformat(), _encode_time(event.occurred_at),
                    event.kind.value, event.reason_code, event.idempotency_key,
                ),
            )
            if cursor.rowcount == 0:
                return False
            connection.execute(
                "INSERT INTO task_reminder_state(task_id, local_date, last_action, next_evaluate_at, "
                "extension_count, last_shown_at, skipped_today, snooze_until, extension_until) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(task_id, local_date) DO UPDATE SET "
                "last_action=excluded.last_action, next_evaluate_at=excluded.next_evaluate_at, "
                "extension_count=excluded.extension_count, last_shown_at=excluded.last_shown_at, "
                "skipped_today=excluded.skipped_today, snooze_until=excluded.snooze_until, "
                "extension_until=excluded.extension_until",
                (
                    state.task_id, state.local_date.isoformat(),
                    state.last_action.value if state.last_action else None,
                    _encode_time(state.next_evaluate_at), state.extension_count,
                    _encode_time(state.last_shown_at), int(state.skipped_today),
                    _encode_time(state.snooze_until), _encode_time(state.extension_until),
                ),
            )
            if global_last_shown_at is not None:
                connection.execute(
                    "UPDATE reminder_runtime_state SET last_shown_at = ? WHERE id = 1",
                    (_encode_time(global_last_shown_at),),
                )
            return True


class SQLiteReminderPreferencesRepository(ReminderPreferencesRepository):
    PREFIX = "reminders."

    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def get_preferences(self) -> ReminderPreferences:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT key, value FROM settings WHERE key LIKE ?", (self.PREFIX + "%",)
            ).fetchall()
        values = {row["key"][len(self.PREFIX):]: row["value"] for row in rows}
        if not values:
            return ReminderPreferences()
        try:
            enabled_value = values.get("enabled", "true")
            if enabled_value not in {"true", "false"}:
                raise ValidationError("Stored reminder enabled value is invalid.")
            return ReminderPreferences(
                enabled=enabled_value == "true",
                quiet_start=time.fromisoformat(values.get("quiet_start", "22:00:00")),
                quiet_end=time.fromisoformat(values.get("quiet_end", "08:00:00")),
                global_cooldown_minutes=int(values.get("global_cooldown_minutes", "10")),
                task_cooldown_minutes=int(values.get("task_cooldown_minutes", "30")),
                later_minutes=int(values.get("later_minutes", "15")),
            )
        except (ValueError, ValidationError) as error:
            raise StorageError("Stored reminder preferences are invalid.") from error

    def save_preferences(self, preferences: ReminderPreferences, updated_at: datetime) -> None:
        if not isinstance(preferences, ReminderPreferences):
            raise ValidationError("Validated reminder preferences are required.")
        if updated_at.tzinfo is None or updated_at.utcoffset() is None:
            raise ValidationError("updated_at must include a timezone.")
        timestamp = _encode_time(updated_at)
        values = {
            "enabled": "true" if preferences.enabled else "false",
            "quiet_start": preferences.quiet_start.isoformat(),
            "quiet_end": preferences.quiet_end.isoformat(),
            "global_cooldown_minutes": str(preferences.global_cooldown_minutes),
            "task_cooldown_minutes": str(preferences.task_cooldown_minutes),
            "later_minutes": str(preferences.later_minutes),
        }
        with self.database.connection() as connection:
            connection.executemany(
                "INSERT INTO settings(key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                [
                    (self.PREFIX + key, value, timestamp)
                    for key, value in values.items()
                ],
            )
