import sqlite3
from dataclasses import replace
from datetime import date, datetime, timezone

from companion.domain.errors import NotFoundError, ValidationError
from companion.domain.models import Goal, Memory, MemoryKind, MemoryQuery, Priority, Task, TaskStatus
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
                    "completed_units, target_units, priority, hard_start, hard_end, status, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        task.id, task.title, task.goal_id, task.due_date.isoformat(),
                        task.planned_minutes, task.completed_units, task.target_units,
                        int(task.priority), _encode_time(task.hard_start), _encode_time(task.hard_end),
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
