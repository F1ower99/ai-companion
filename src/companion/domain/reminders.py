from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from enum import Enum

from companion.domain.errors import ValidationError


def _aware_utc(value: datetime | None, name: str, *, optional: bool = False) -> datetime | None:
    if value is None and optional:
        return None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError(f"{name} must include a timezone.")
    return value.astimezone(timezone.utc)


class ActivityState(str, Enum):
    IDLE = "idle"
    FOCUSED = "focused"
    UNKNOWN = "unknown"


class ReminderAction(str, Enum):
    NOW = "now"
    LATER = "later"
    EXTEND = "extend"
    SKIP_TODAY = "skip_today"
    DONE = "done"
    CLOSE = "close"


class ReminderEventKind(str, Enum):
    DISPLAYED = "displayed"
    NOW = "now"
    LATER = "later"
    EXTENDED = "extended"
    SKIPPED = "skipped"
    COMPLETED = "completed"
    CLOSED = "closed"


class ReminderDisplayMode(str, Enum):
    NORMAL = "normal"
    SILENT_NON_MODAL = "silent_non_modal"


class ReminderCategory(str, Enum):
    SCHEDULE = "schedule"
    DEADLINE = "deadline"
    CAPACITY = "capacity"
    FOLLOW_UP = "follow_up"


@dataclass(frozen=True)
class ActivitySnapshot:
    state: ActivityState
    observed_at: datetime
    state_since: datetime

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "state", ActivityState(self.state))
        except (TypeError, ValueError) as error:
            raise ValidationError("Activity state is not supported.") from error
        observed = _aware_utc(self.observed_at, "observed_at")
        since = _aware_utc(self.state_since, "state_since")
        if since is not None and observed is not None and since > observed:
            raise ValidationError("state_since cannot be later than observed_at.")
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(self, "state_since", since)


@dataclass(frozen=True)
class ReminderPreferences:
    enabled: bool = True
    quiet_start: time = time(22, 0)
    quiet_end: time = time(8, 0)
    global_cooldown_minutes: int = 10
    task_cooldown_minutes: int = 30
    later_minutes: int = 15

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValidationError("Reminder enabled must be a boolean.")
        for name in ("quiet_start", "quiet_end"):
            value = getattr(self, name)
            if not isinstance(value, time) or value.tzinfo is not None:
                raise ValidationError(f"{name} must be a local wall-clock time.")
        if self.quiet_start == self.quiet_end:
            raise ValidationError("Quiet-hours start and end must differ.")
        for name, minimum, maximum in (
            ("global_cooldown_minutes", 0, 24 * 60),
            ("task_cooldown_minutes", 0, 24 * 60),
            ("later_minutes", 1, 120),
        ):
            value = getattr(self, name)
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValidationError(f"{name} is outside its supported range.")


@dataclass(frozen=True)
class TaskReminderState:
    task_id: str
    local_date: date
    last_action: ReminderAction | None = None
    next_evaluate_at: datetime | None = None
    extension_count: int = 0
    last_shown_at: datetime | None = None
    skipped_today: bool = False
    snooze_until: datetime | None = None
    extension_until: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.task_id, str) or not self.task_id.strip():
            raise ValidationError("task_id must not be blank.")
        if not isinstance(self.local_date, date) or isinstance(self.local_date, datetime):
            raise ValidationError("local_date must be a date.")
        if self.last_action is not None:
            try:
                object.__setattr__(self, "last_action", ReminderAction(self.last_action))
            except (TypeError, ValueError) as error:
                raise ValidationError("Reminder action is not supported.") from error
        if type(self.extension_count) is not int or self.extension_count not in (0, 1):
            raise ValidationError("extension_count must be 0 or 1 per local date.")
        if not isinstance(self.skipped_today, bool):
            raise ValidationError("skipped_today must be a boolean.")
        for name in ("next_evaluate_at", "last_shown_at", "snooze_until", "extension_until"):
            object.__setattr__(self, name, _aware_utc(getattr(self, name), name, optional=True))


@dataclass(frozen=True)
class ReminderEvent:
    kind: ReminderEventKind
    task_id: str | None
    occurred_at: datetime
    local_date: date
    reason_code: str
    idempotency_key: str

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "kind", ReminderEventKind(self.kind))
        except (TypeError, ValueError) as error:
            raise ValidationError("Reminder event kind is not supported.") from error
        if self.task_id is not None and (not isinstance(self.task_id, str) or not self.task_id.strip()):
            raise ValidationError("task_id must be non-blank or None.")
        if not isinstance(self.local_date, date) or isinstance(self.local_date, datetime):
            raise ValidationError("local_date must be a date.")
        if not isinstance(self.reason_code, str) or not self.reason_code.strip():
            raise ValidationError("reason_code must not be blank.")
        if not isinstance(self.idempotency_key, str) or not self.idempotency_key.strip():
            raise ValidationError("idempotency_key must not be blank.")
        object.__setattr__(self, "occurred_at", _aware_utc(self.occurred_at, "occurred_at"))


def remaining_minutes(task) -> int:
    """Return the rounded-up remaining estimate; never report negative work."""
    if task.status.value == "completed":
        return 0
    if task.target_units is None:
        return max(0, task.planned_minutes)
    remaining_units = max(task.target_units - task.completed_units, 0)
    if remaining_units == 0:
        return 0
    numerator = task.planned_minutes * remaining_units
    return (numerator + task.target_units - 1) // task.target_units
