from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from math import inf

from companion.domain.errors import ValidationError
from companion.domain.models import Goal, Priority, Task, TaskStatus
from companion.domain.reminders import (
    ActivitySnapshot,
    ActivityState,
    ReminderCategory,
    ReminderDisplayMode,
    ReminderPreferences,
    TaskReminderState,
    remaining_minutes,
)


class DecisionKind(str, Enum):
    SHOW_REMINDER = "show_reminder"
    WAIT = "wait"
    SILENT = "silent"


class ReasonCode(str, Enum):
    NO_ELIGIBLE_TASK = "no_eligible_task"
    BEFORE_PLANNED_START = "before_planned_start"
    PLANNED_START_LATE = "planned_start_late"
    HARD_START_NOT_REACHED = "hard_start_not_reached"
    DEADLINE_RISK = "deadline_risk"
    DEADLINE_MISSED = "deadline_missed"
    PLAN_OVER_CAPACITY = "plan_over_capacity"
    REMAINING_TIME_LOW = "remaining_time_low"
    FOCUS_GRACE = "focus_grace"
    IDLE_USER = "idle_user"
    ACTIVITY_UNKNOWN = "activity_unknown"
    QUIET_HOURS = "quiet_hours"
    GLOBAL_COOLDOWN = "global_cooldown"
    TASK_COOLDOWN = "task_cooldown"
    USER_SNOOZE = "user_snooze"
    EXTENSION_PENDING = "extension_pending"
    EXTENSION_DUE = "extension_due"
    SKIPPED_TODAY = "skipped_today"
    REMINDERS_DISABLED = "reminders_disabled"
    LOW_PRIORITY_WHILE_FOCUSED = "low_priority_while_focused"
    NO_RISK_SIGNAL = "no_risk_signal"
    USER_ACTION = "user_action"
    ACTION_ALREADY_RECORDED = "action_already_recorded"
    STORAGE_UNAVAILABLE = "storage_unavailable"
    TIME_CONTEXT_UNAVAILABLE = "time_context_unavailable"


@dataclass(frozen=True)
class DecisionContext:
    now_utc: datetime
    local_now: datetime
    local_date: date
    local_day_start_utc: datetime
    next_local_day_start_utc: datetime
    tonight_quiet_start_utc: datetime
    quiet_period_end_utc: datetime
    quiet_hours_active: bool
    tasks: tuple[Task, ...]
    goals: tuple[Goal, ...]
    activity: ActivitySnapshot
    reminder_states: tuple[TaskReminderState, ...]
    last_global_shown_at: datetime | None
    preferences: ReminderPreferences

    def __post_init__(self) -> None:
        for name in (
            "now_utc", "local_now", "local_day_start_utc", "next_local_day_start_utc",
            "tonight_quiet_start_utc", "quiet_period_end_utc",
        ):
            value = getattr(self, name)
            if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
                raise ValidationError(f"{name} must include a timezone.")
            object.__setattr__(self, name, value.astimezone(timezone.utc) if name != "local_now" else value)
        if not isinstance(self.local_date, date) or isinstance(self.local_date, datetime):
            raise ValidationError("local_date must be a date.")
        if self.local_now.date() != self.local_date:
            raise ValidationError("local_date must match local_now.")
        if self.local_now.astimezone(timezone.utc) != self.now_utc:
            raise ValidationError("local_now and now_utc must describe the same instant.")
        if type(self.quiet_hours_active) is not bool:
            raise ValidationError("quiet_hours_active must be a boolean.")
        if self.last_global_shown_at is not None:
            value = self.last_global_shown_at
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValidationError("last_global_shown_at must include a timezone.")
            object.__setattr__(self, "last_global_shown_at", value.astimezone(timezone.utc))
        for name in ("tasks", "goals", "reminder_states"):
            object.__setattr__(self, name, tuple(getattr(self, name)))


@dataclass(frozen=True)
class Decision:
    kind: DecisionKind
    generated_at: datetime
    reason_codes: tuple[ReasonCode, ...]
    task_id: str | None = None
    next_evaluate_at: datetime | None = None
    display_mode: ReminderDisplayMode = ReminderDisplayMode.NORMAL
    category: ReminderCategory | None = None

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "kind", DecisionKind(self.kind))
        except (TypeError, ValueError) as error:
            raise ValidationError("Decision kind is not supported.") from error
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValidationError("generated_at must include a timezone.")
        object.__setattr__(self, "generated_at", self.generated_at.astimezone(timezone.utc))
        if self.next_evaluate_at is not None:
            if self.next_evaluate_at.tzinfo is None or self.next_evaluate_at.utcoffset() is None:
                raise ValidationError("next_evaluate_at must include a timezone.")
            object.__setattr__(self, "next_evaluate_at", self.next_evaluate_at.astimezone(timezone.utc))
        if self.kind is DecisionKind.SHOW_REMINDER and not self.task_id:
            raise ValidationError("A shown reminder must identify one task.")
        if self.kind is DecisionKind.SHOW_REMINDER and self.category is None:
            raise ValidationError("A shown reminder must identify its category.")
        if self.kind is not DecisionKind.SHOW_REMINDER and self.task_id is not None:
            raise ValidationError("Only a shown reminder may identify a task.")
        if not self.reason_codes:
            raise ValidationError("A decision must include at least one reason code.")
        object.__setattr__(self, "reason_codes", tuple(ReasonCode(value) for value in self.reason_codes))
        object.__setattr__(self, "display_mode", ReminderDisplayMode(self.display_mode))
        if self.category is not None:
            object.__setattr__(self, "category", ReminderCategory(self.category))


@dataclass(frozen=True)
class _Candidate:
    task: Task
    goal: Goal
    remaining: int
    signals: tuple[ReasonCode, ...]
    state: TaskReminderState | None
    hard_slack_minutes: float | None
    deadline_is_future: bool
    missed_hard_end: bool


def _minutes_between(end: datetime, start: datetime) -> float:
    return (end - start).total_seconds() / 60


def _is_imminent_feasible_p0(task: Task, remaining: int, now: datetime) -> bool:
    if task.priority is not Priority.P0 or task.hard_end is None or task.hard_end <= now:
        return False
    minutes_until_deadline = _minutes_between(task.hard_end, now)
    if not 0 < minutes_until_deadline <= 30:
        return False
    earliest_start = max(now, task.hard_start or now)
    return earliest_start + timedelta(minutes=remaining) <= task.hard_end


def _valid_activity(activity: ActivitySnapshot, now: datetime) -> ActivityState:
    observed = activity.observed_at
    state_since = activity.state_since
    if observed > now or state_since > now or now - observed > timedelta(minutes=2):
        return ActivityState.UNKNOWN
    return activity.state


def _candidate_key(candidate: _Candidate):
    task = candidate.task
    if candidate.deadline_is_future and candidate.hard_slack_minutes is not None:
        risk_deadline = (0, candidate.hard_slack_minutes)
    else:
        risk_deadline = (1, 0)
    overdue_hard_end = 0 if candidate.missed_hard_end else 1
    future_deadline = (
        task.hard_end.timestamp()
        if task.hard_end is not None and not candidate.missed_hard_end
        else inf
    )
    planned = task.planned_start_at.timestamp() if task.planned_start_at else inf
    return (
        risk_deadline,
        int(task.priority),
        overdue_hard_end,
        future_deadline,
        planned,
        int(candidate.goal.priority),
        task.created_at.timestamp(),
        task.id,
    )


def decide(context: DecisionContext) -> Decision:
    """Choose at most one reminder using only explicit, immutable inputs."""
    now = context.now_utc
    if not context.preferences.enabled:
        return Decision(DecisionKind.SILENT, now, (ReasonCode.REMINDERS_DISABLED,))
    if context.quiet_hours_active:
        return Decision(
            DecisionKind.SILENT, now, (ReasonCode.QUIET_HOURS,),
            next_evaluate_at=context.quiet_period_end_utc,
        )

    goals = {goal.id: goal for goal in context.goals}
    states = {
        state.task_id: state
        for state in context.reminder_states
        if state.local_date == context.local_date
    }
    day_minutes = max(0, int(_minutes_between(context.tonight_quiet_start_utc, now)))
    provisional: list[tuple[Task, Goal, TaskReminderState | None, int, bool]] = []
    skipped_seen = False
    for task in context.tasks:
        goal = goals.get(task.goal_id)
        if task.status is not TaskStatus.OPEN or goal is None or not goal.active:
            continue
        remaining = remaining_minutes(task)
        if remaining <= 0:
            continue
        planned_today = (
            task.planned_start_at is not None
            and context.local_day_start_utc <= task.planned_start_at < context.next_local_day_start_utc
        )
        if task.due_date > context.local_date and not planned_today:
            continue
        state = states.get(task.id)
        if state is not None and state.skipped_today:
            skipped_seen = True
            continue
        if task.hard_start is not None and task.hard_start > now:
            provisional.append((task, goal, state, remaining, True))
            continue
        provisional.append((task, goal, state, remaining, False))

    if not provisional:
        reason = ReasonCode.SKIPPED_TODAY if skipped_seen else ReasonCode.NO_ELIGIBLE_TASK
        return Decision(DecisionKind.SILENT, now, (reason,))

    total_remaining = sum(item[3] for item in provisional)
    overloaded = total_remaining > day_minutes
    candidates: list[_Candidate] = []
    wait_reasons: set[ReasonCode] = set()
    wait_times: list[datetime] = []
    activity = _valid_activity(context.activity, now)
    focused_minutes = max(0, _minutes_between(now, context.activity.state_since))
    for task, goal, state, remaining, hard_start_blocked in provisional:
        signals: list[ReasonCode] = []
        if hard_start_blocked:
            wait_reasons.add(ReasonCode.HARD_START_NOT_REACHED)
            wait_times.append(task.hard_start)
            continue
        future_deadline = task.hard_end is not None and task.hard_end > now
        missed_hard_end = task.hard_end is not None and task.hard_end <= now
        if missed_hard_end:
            wait_reasons.add(ReasonCode.DEADLINE_MISSED)
        slack: float | None = None
        if future_deadline:
            available_from = max(now, task.hard_start or now)
            slack = _minutes_between(task.hard_end, available_from) - remaining
            if slack <= 30:
                signals.append(ReasonCode.DEADLINE_RISK)
        if overloaded:
            signals.append(ReasonCode.PLAN_OVER_CAPACITY)
        if task.planned_start_at is not None:
            grace_end = task.planned_start_at + timedelta(minutes=5)
            if now < grace_end:
                urgent_hard_deadline = _is_imminent_feasible_p0(task, remaining, now)
                independent_risk = any(
                    signal in (ReasonCode.DEADLINE_RISK, ReasonCode.PLAN_OVER_CAPACITY)
                    for signal in signals
                )
                if not urgent_hard_deadline and not independent_risk:
                    wait_reasons.add(ReasonCode.BEFORE_PLANNED_START)
                    wait_times.append(grace_end)
                    continue
            elif now >= task.planned_start_at + timedelta(minutes=30):
                signals.append(ReasonCode.PLANNED_START_LATE)
        remaining_boundary = context.tonight_quiet_start_utc
        if future_deadline and task.hard_end < remaining_boundary:
            remaining_boundary = task.hard_end
        available_minutes = max(0, _minutes_between(remaining_boundary, now))
        if task.planned_start_at is None and available_minutes <= remaining:
            signals.append(ReasonCode.REMAINING_TIME_LOW)
        candidates.append(_Candidate(
            task=task,
            goal=goal,
            remaining=remaining,
            signals=tuple(dict.fromkeys(signals)),
            state=state,
            hard_slack_minutes=slack,
            deadline_is_future=future_deadline and slack is not None and slack <= 30,
            missed_hard_end=missed_hard_end,
        ))

    if not candidates:
        next_at = min(wait_times) if wait_times else None
        reasons = tuple(sorted(wait_reasons or {ReasonCode.NO_ELIGIBLE_TASK}, key=lambda x: x.value))
        return Decision(DecisionKind.WAIT, now, reasons, next_evaluate_at=next_at)

    candidates.sort(key=_candidate_key)
    available: list[tuple[_Candidate, ReminderDisplayMode, tuple[ReasonCode, ...]]] = []
    for candidate in candidates:
        task = candidate.task
        state = candidate.state
        if state is not None and state.snooze_until is not None and state.snooze_until > now:
            wait_reasons.add(ReasonCode.USER_SNOOZE)
            wait_times.append(state.snooze_until)
            continue
        if state is not None and state.extension_until is not None and state.extension_until > now:
            wait_reasons.add(ReasonCode.EXTENSION_PENDING)
            wait_times.append(state.extension_until)
            continue
        if (
            state is not None
            and state.next_evaluate_at is not None
            and state.next_evaluate_at > now
            and state.snooze_until is None
            and state.extension_until is None
        ):
            wait_reasons.add(ReasonCode.TASK_COOLDOWN)
            wait_times.append(state.next_evaluate_at)
            continue
        extension_due = state is not None and state.extension_until is not None and state.extension_until <= now
        snooze_due = state is not None and state.snooze_until is not None and state.snooze_until <= now
        action_due = extension_due or snooze_due
        signal_codes = list(candidate.signals)
        if not signal_codes:
            if (
                task.planned_start_at is not None
                and now >= task.planned_start_at + timedelta(minutes=5)
                and now < task.planned_start_at + timedelta(minutes=30)
            ):
                wait_reasons.add(ReasonCode.FOCUS_GRACE)
                wait_times.append(task.planned_start_at + timedelta(minutes=30))
            else:
                wait_reasons.add(ReasonCode.NO_RISK_SIGNAL)
            continue
        if extension_due:
            signal_codes.append(ReasonCode.EXTENSION_DUE)
        urgent_p0 = _is_imminent_feasible_p0(task, candidate.remaining, now)
        if activity is ActivityState.IDLE:
            wait_reasons.add(ReasonCode.IDLE_USER)
            continue
        if activity is ActivityState.UNKNOWN:
            if not urgent_p0:
                wait_reasons.add(ReasonCode.ACTIVITY_UNKNOWN)
                continue
            mode = ReminderDisplayMode.SILENT_NON_MODAL
        elif focused_minutes < 120:
            if not urgent_p0:
                wait_reasons.add(ReasonCode.FOCUS_GRACE)
                wait_times.append(context.activity.state_since + timedelta(minutes=120))
                continue
            mode = ReminderDisplayMode.SILENT_NON_MODAL
        else:
            if task.priority is Priority.P2:
                wait_reasons.add(ReasonCode.LOW_PRIORITY_WHILE_FOCUSED)
                continue
            mode = ReminderDisplayMode.NORMAL
        if state is not None and state.last_shown_at is not None and not extension_due and not action_due:
            task_ready = state.last_shown_at + timedelta(minutes=context.preferences.task_cooldown_minutes)
            if task_ready > now:
                wait_reasons.add(ReasonCode.TASK_COOLDOWN)
                wait_times.append(task_ready)
                continue
        available.append((candidate, mode, tuple(dict.fromkeys(signal_codes)) or (ReasonCode.EXTENSION_DUE,)))

    if available:
        candidate, mode, reasons = available[0]
        if candidate.missed_hard_end and ReasonCode.DEADLINE_MISSED not in reasons:
            reasons = (*reasons, ReasonCode.DEADLINE_MISSED)
        if context.last_global_shown_at is not None:
            global_ready = context.last_global_shown_at + timedelta(minutes=context.preferences.global_cooldown_minutes)
            if global_ready > now:
                return Decision(
                    DecisionKind.WAIT, now, (ReasonCode.GLOBAL_COOLDOWN,),
                    next_evaluate_at=global_ready,
                )
        if any(reason in (ReasonCode.DEADLINE_RISK, ReasonCode.DEADLINE_MISSED) for reason in reasons):
            category = ReminderCategory.DEADLINE
        elif any(reason in (ReasonCode.PLAN_OVER_CAPACITY, ReasonCode.REMAINING_TIME_LOW) for reason in reasons):
            category = ReminderCategory.CAPACITY
        elif ReasonCode.EXTENSION_DUE in reasons:
            category = ReminderCategory.FOLLOW_UP
        else:
            category = ReminderCategory.SCHEDULE
        return Decision(
            DecisionKind.SHOW_REMINDER,
            now,
            reasons,
            task_id=candidate.task.id,
            display_mode=mode,
            category=category,
        )

    if wait_reasons == {ReasonCode.ACTIVITY_UNKNOWN}:
        return Decision(DecisionKind.SILENT, now, (ReasonCode.ACTIVITY_UNKNOWN,))
    if wait_reasons:
        reasons = tuple(sorted(wait_reasons, key=lambda reason: reason.value))
        future_times = [value for value in wait_times if value is not None and value > now]
        return Decision(
            DecisionKind.WAIT,
            now,
            reasons,
            next_evaluate_at=min(future_times) if future_times else None,
        )
    return Decision(DecisionKind.SILENT, now, (ReasonCode.NO_RISK_SIGNAL,))
