from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum, IntEnum

from companion.domain.errors import ValidationError


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_id(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field_name} must not be blank.")


def _require_aware_utc(value: datetime | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError(f"{field_name} must include a timezone.")
    return value.astimezone(timezone.utc)


class Priority(IntEnum):
    P0 = 0
    P1 = 1
    P2 = 2


class TaskStatus(str, Enum):
    OPEN = "open"
    COMPLETED = "completed"


class MemoryKind(str, Enum):
    PROFILE = "profile"
    PREFERENCE = "preference"
    BEHAVIORAL = "behavioral"
    EPISODIC = "episodic"
    CONVERSATION = "conversation"


@dataclass(frozen=True)
class Goal:
    id: str
    name: str
    target: str | None = None
    priority: Priority = Priority.P1
    active: bool = True
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        _require_id(self.id, "id")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValidationError("Goal name must not be blank.")
        object.__setattr__(self, "name", self.name.strip())
        if self.target is not None and not isinstance(self.target, str):
            raise ValidationError("Goal target must be text or None.")
        try:
            priority = Priority(self.priority)
        except (TypeError, ValueError) as error:
            raise ValidationError("Goal priority must be P0, P1, or P2.") from error
        object.__setattr__(self, "priority", priority)
        if not isinstance(self.active, bool):
            raise ValidationError("Goal active must be a boolean.")
        object.__setattr__(self, "created_at", _require_aware_utc(self.created_at, "created_at"))


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    goal_id: str
    due_date: date
    planned_minutes: int
    priority: Priority
    completed_units: int = 0
    target_units: int | None = None
    hard_start: datetime | None = None
    hard_end: datetime | None = None
    status: TaskStatus = TaskStatus.OPEN
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        _require_id(self.id, "id")
        _require_id(self.goal_id, "goal_id")
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValidationError("Task title must not be blank.")
        object.__setattr__(self, "title", self.title.strip())
        if not isinstance(self.due_date, date) or isinstance(self.due_date, datetime):
            raise ValidationError("Task due_date must be a calendar date.")
        if type(self.planned_minutes) is not int or self.planned_minutes < 0:
            raise ValidationError("planned_minutes must be a non-negative integer.")
        if type(self.completed_units) is not int or self.completed_units < 0:
            raise ValidationError("completed_units must be a non-negative integer.")
        if self.target_units is not None and (
            type(self.target_units) is not int or self.target_units <= 0
        ):
            raise ValidationError("target_units must be a positive integer when provided.")
        if self.target_units is not None and self.completed_units > self.target_units:
            raise ValidationError("completed_units cannot exceed target_units.")
        try:
            object.__setattr__(self, "priority", Priority(self.priority))
        except (TypeError, ValueError) as error:
            raise ValidationError("Task priority must be P0, P1, or P2.") from error
        try:
            object.__setattr__(self, "status", TaskStatus(self.status))
        except (TypeError, ValueError) as error:
            raise ValidationError("Task status must be open or completed.") from error
        start = _require_aware_utc(self.hard_start, "hard_start")
        end = _require_aware_utc(self.hard_end, "hard_end")
        object.__setattr__(self, "hard_start", start)
        object.__setattr__(self, "hard_end", end)
        if start is not None and end is not None and end < start:
            raise ValidationError("hard_end cannot be earlier than hard_start.")
        object.__setattr__(self, "created_at", _require_aware_utc(self.created_at, "created_at"))


@dataclass(frozen=True)
class Memory:
    id: str
    kind: MemoryKind
    content: str
    source: str | None = None
    importance: int = 0
    created_at: datetime = field(default_factory=utc_now)
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_id(self.id, "id")
        try:
            object.__setattr__(self, "kind", MemoryKind(self.kind))
        except (TypeError, ValueError) as error:
            raise ValidationError("Memory kind is not supported.") from error
        if not isinstance(self.content, str) or not self.content.strip():
            raise ValidationError("Memory content must not be blank.")
        object.__setattr__(self, "content", self.content.strip())
        if self.source is not None and not isinstance(self.source, str):
            raise ValidationError("Memory source must be text or None.")
        if type(self.importance) is not int or not 0 <= self.importance <= 5:
            raise ValidationError("Memory importance must be an integer from 0 to 5.")
        object.__setattr__(self, "created_at", _require_aware_utc(self.created_at, "created_at"))
        object.__setattr__(self, "expires_at", _require_aware_utc(self.expires_at, "expires_at"))


@dataclass(frozen=True)
class MemoryQuery:
    text: str | None = None
    kind: MemoryKind | None = None
    source: str | None = None
    include_expired: bool = False

    def __post_init__(self) -> None:
        if self.text is not None and not isinstance(self.text, str):
            raise ValidationError("Memory query text must be text or None.")
        if self.kind is not None:
            try:
                object.__setattr__(self, "kind", MemoryKind(self.kind))
            except (TypeError, ValueError) as error:
                raise ValidationError("Memory query kind is not supported.") from error
        if self.source is not None and not isinstance(self.source, str):
            raise ValidationError("Memory query source must be text or None.")
        if not isinstance(self.include_expired, bool):
            raise ValidationError("include_expired must be a boolean.")
