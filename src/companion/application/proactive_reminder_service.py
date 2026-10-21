from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from companion.application.task_service import TaskService
from companion.domain.decisions import Decision, DecisionContext, DecisionKind, ReasonCode, decide
from companion.domain.errors import NotFoundError, StorageError, ValidationError
from companion.domain.models import TaskStatus
from companion.domain.reminders import (
    ActivitySnapshot,
    ActivityState,
    ReminderAction,
    ReminderEvent,
    ReminderEventKind,
    ReminderPreferences,
    TaskReminderState,
    remaining_minutes,
)
from companion.ports.activity import ActivitySource
from companion.ports.clock import Clock, ClockSnapshot
from companion.ports.reminders import ReminderPreferencesRepository, ReminderRepository


class UnknownActivitySource:
    """Privacy-preserving Stage 3 source; it never inspects Windows activity."""

    def snapshot(self, at: datetime) -> ActivitySnapshot:
        return ActivitySnapshot(ActivityState.UNKNOWN, at, at)


class ProactiveReminderService:
    def __init__(
        self,
        clock: Clock,
        tasks: TaskService,
        reminders: ReminderRepository,
        preferences: ReminderPreferencesRepository,
        activity: ActivitySource | None = None,
    ) -> None:
        self.clock = clock
        self.tasks = tasks
        self.reminders = reminders
        self.preferences = preferences
        self.activity = activity or UnknownActivitySource()

    def evaluate(self) -> Decision:
        try:
            preferences = self.preferences.get_preferences()
        except StorageError:
            return self._silent(ReasonCode.STORAGE_UNAVAILABLE)
        try:
            clock = self.clock.snapshot(preferences)
        except Exception:
            return self._silent(ReasonCode.TIME_CONTEXT_UNAVAILABLE)
        if not preferences.enabled:
            # The disabled consumer needs no task data or activity sampling.
            return Decision(
                DecisionKind.SILENT, clock.now_utc, (ReasonCode.REMINDERS_DISABLED,),
            )
        try:
            decision = self._evaluate_at(clock, preferences)
        except StorageError:
            return Decision(
                DecisionKind.SILENT,
                clock.now_utc,
                (ReasonCode.STORAGE_UNAVAILABLE,),
            )
        if decision.kind is not DecisionKind.SHOW_REMINDER:
            return decision
        try:
            task = self.tasks.get_task(decision.task_id)
            if task is None or task.status is not TaskStatus.OPEN:
                return Decision(
                    DecisionKind.WAIT,
                    clock.now_utc,
                    (ReasonCode.NO_ELIGIBLE_TASK,),
                )
            states = self.reminders.get_task_states(clock.local_date)
            state = next((item for item in states if item.task_id == task.id), None)
            if state is None:
                state = TaskReminderState(task.id, clock.local_date)
            explicit_action_deadline = (
                state.snooze_until if state.last_action is ReminderAction.LATER else
                state.extension_until if state.last_action is ReminderAction.EXTEND else None
            )
            action_deadline_due = (
                explicit_action_deadline is not None
                and explicit_action_deadline <= clock.now_utc
                and state.next_evaluate_at == explicit_action_deadline
            )
            shown_state = replace(
                state,
                next_evaluate_at=clock.now_utc + timedelta(minutes=preferences.task_cooldown_minutes),
                last_shown_at=clock.now_utc,
                snooze_until=None,
                extension_until=None,
            )
            event = ReminderEvent(
                kind=ReminderEventKind.DISPLAYED,
                task_id=task.id,
                occurred_at=clock.now_utc,
                local_date=clock.local_date,
                reason_code=decision.reason_codes[0].value,
                idempotency_key=f"display:{uuid4()}",
            )
            saved = self.reminders.save_state_and_event(
                shown_state,
                event,
                global_last_shown_at=clock.now_utc,
                global_cooldown_minutes=preferences.global_cooldown_minutes,
                task_cooldown_minutes=preferences.task_cooldown_minutes,
                bypass_task_cooldown=action_deadline_due,
            )
        except StorageError:
            return Decision(
                DecisionKind.SILENT,
                clock.now_utc,
                (ReasonCode.STORAGE_UNAVAILABLE,),
            )
        if not saved:
            try:
                latest_global = self.reminders.get_last_global_shown_at()
                latest_states = self.reminders.get_task_states(clock.local_date)
            except StorageError:
                return self._silent(ReasonCode.STORAGE_UNAVAILABLE)
            latest_state = next((item for item in latest_states if item.task_id == task.id), None)
            reasons = []
            wake_times = []
            if latest_global is not None:
                global_ready = latest_global + timedelta(minutes=preferences.global_cooldown_minutes)
                if global_ready > clock.now_utc:
                    reasons.append(ReasonCode.GLOBAL_COOLDOWN)
                    wake_times.append(global_ready)
            if latest_state is not None and latest_state.last_shown_at is not None:
                task_ready = latest_state.last_shown_at + timedelta(
                    minutes=preferences.task_cooldown_minutes
                )
                if task_ready > clock.now_utc:
                    reasons.append(ReasonCode.TASK_COOLDOWN)
                    wake_times.append(task_ready)
            if not reasons:
                reasons.append(ReasonCode.ACTION_ALREADY_RECORDED)
                wake_times.append(clock.now_utc + timedelta(seconds=1))
            return Decision(
                DecisionKind.WAIT,
                clock.now_utc,
                tuple(reasons),
                next_evaluate_at=max(wake_times),
            )
        return decision

    def respond(
        self,
        task_id: str,
        action: ReminderAction | str,
        minutes: int | None = None,
        idempotency_key: str | None = None,
    ) -> Decision:
        try:
            action = ReminderAction(action)
        except (TypeError, ValueError) as error:
            raise ValidationError("Reminder action is not supported.") from error
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ValidationError("An action idempotency key is required.")
        previous = self.reminders.get_event_by_key(idempotency_key)
        if previous is not None:
            return Decision(
                DecisionKind.WAIT,
                previous.occurred_at,
                (ReasonCode.ACTION_ALREADY_RECORDED,),
            )
        preferences = self.preferences.get_preferences()
        clock = self.clock.snapshot(preferences)
        task = self.tasks.get_task(task_id)
        if task is None:
            raise NotFoundError("Task not found.")
        if task.status is not TaskStatus.OPEN and action not in (
            ReminderAction.DONE, ReminderAction.CLOSE,
        ):
            raise ValidationError("This task is no longer open.")
        state = next(
            (item for item in self.reminders.get_task_states(clock.local_date) if item.task_id == task_id),
            TaskReminderState(task_id, clock.local_date),
        )
        if action is ReminderAction.EXTEND:
            self._validate_extension(task, state, clock, minutes)

        snooze_until = None
        extension_until = None
        next_evaluate_at = None
        skipped_today = state.skipped_today
        extension_count = state.extension_count
        if action is ReminderAction.NOW:
            next_evaluate_at = clock.now_utc + timedelta(minutes=preferences.task_cooldown_minutes)
        elif action is ReminderAction.LATER:
            snooze_until = clock.now_utc + timedelta(minutes=preferences.later_minutes)
            next_evaluate_at = snooze_until
        elif action is ReminderAction.EXTEND:
            extension_until = clock.now_utc + timedelta(minutes=minutes)
            next_evaluate_at = extension_until
            extension_count += 1
        elif action is ReminderAction.SKIP_TODAY:
            skipped_today = True
        elif action is ReminderAction.CLOSE:
            next_evaluate_at = clock.now_utc + timedelta(minutes=preferences.task_cooldown_minutes)

        if action is ReminderAction.DONE and task.status is TaskStatus.OPEN:
            self.tasks.mark_completed(task_id)

        event_kind = {
            ReminderAction.NOW: ReminderEventKind.NOW,
            ReminderAction.LATER: ReminderEventKind.LATER,
            ReminderAction.EXTEND: ReminderEventKind.EXTENDED,
            ReminderAction.SKIP_TODAY: ReminderEventKind.SKIPPED,
            ReminderAction.DONE: ReminderEventKind.COMPLETED,
            ReminderAction.CLOSE: ReminderEventKind.CLOSED,
        }[action]
        updated = replace(
            state,
            last_action=action,
            next_evaluate_at=next_evaluate_at,
            extension_count=extension_count,
            skipped_today=skipped_today,
            snooze_until=snooze_until,
            extension_until=extension_until,
        )
        event = ReminderEvent(
            kind=event_kind,
            task_id=task_id,
            occurred_at=clock.now_utc,
            local_date=clock.local_date,
            reason_code=ReasonCode.USER_ACTION.value,
            idempotency_key=idempotency_key,
        )
        if not self.reminders.save_state_and_event(updated, event):
            return Decision(
                DecisionKind.WAIT,
                clock.now_utc,
                (ReasonCode.ACTION_ALREADY_RECORDED,),
            )
        if action in (ReminderAction.DONE, ReminderAction.SKIP_TODAY):
            return self.evaluate()
        if action is ReminderAction.EXTEND:
            return Decision(
                DecisionKind.WAIT,
                clock.now_utc,
                (ReasonCode.EXTENSION_PENDING,),
                next_evaluate_at=extension_until,
            )
        if action is ReminderAction.LATER:
            return Decision(
                DecisionKind.WAIT,
                clock.now_utc,
                (ReasonCode.USER_SNOOZE,),
                next_evaluate_at=snooze_until,
            )
        return Decision(
            DecisionKind.WAIT,
            clock.now_utc,
            (ReasonCode.TASK_COOLDOWN,),
            next_evaluate_at=next_evaluate_at,
        )

    def update_preferences(self, preferences: ReminderPreferences) -> None:
        if not isinstance(preferences, ReminderPreferences):
            raise ValidationError("Validated reminder preferences are required.")
        self.preferences.save_preferences(preferences, self.clock.now_utc())

    def get_preferences(self) -> ReminderPreferences:
        return self.preferences.get_preferences()

    def _evaluate_at(
        self,
        clock: ClockSnapshot,
        preferences: ReminderPreferences,
    ) -> Decision:
        tasks = self.tasks.list_for_decisions(
            clock.local_date,
            clock.local_day_start_utc,
            clock.next_local_day_start_utc,
        )
        goals = self.tasks.list_active_goals()
        states = self.reminders.get_task_states(clock.local_date)
        last_shown = self.reminders.get_last_global_shown_at()
        activity = self._activity_at(clock.now_utc)
        return decide(DecisionContext(
            now_utc=clock.now_utc,
            local_now=clock.local_now,
            local_date=clock.local_date,
            local_day_start_utc=clock.local_day_start_utc,
            next_local_day_start_utc=clock.next_local_day_start_utc,
            tonight_quiet_start_utc=clock.tonight_quiet_start_utc,
            quiet_period_end_utc=clock.quiet_period_end_utc,
            quiet_hours_active=clock.quiet_hours_active,
            tasks=tuple(tasks),
            goals=tuple(goals),
            activity=activity,
            reminder_states=tuple(states),
            last_global_shown_at=last_shown,
            preferences=preferences,
        ))

    def _activity_at(self, at: datetime) -> ActivitySnapshot:
        try:
            snapshot = self.activity.snapshot(at)
            if not isinstance(snapshot, ActivitySnapshot):
                raise ValidationError("Activity source returned an invalid snapshot.")
            return snapshot
        except Exception:
            return ActivitySnapshot(ActivityState.UNKNOWN, at, at)

    def _validate_extension(
        self,
        task,
        state: TaskReminderState,
        clock: ClockSnapshot,
        minutes: int | None,
    ) -> None:
        if type(minutes) is not int or not 1 <= minutes <= 120:
            raise ValidationError("Extension must be a whole number from 1 to 120 minutes.")
        if state.extension_count >= 1:
            raise ValidationError("Only one extension is allowed for this task today.")
        if clock.quiet_hours_active:
            raise ValidationError("An extension cannot be accepted during quiet hours.")
        if task.hard_end is not None and task.hard_end <= clock.now_utc:
            raise ValidationError("The hard deadline has already passed.")
        requested_at = clock.now_utc + timedelta(minutes=minutes)
        if requested_at >= clock.tonight_quiet_start_utc:
            raise ValidationError("The extension would reach quiet hours.")
        start_at = max(requested_at, task.hard_start or requested_at)
        finish_at = start_at + timedelta(minutes=remaining_minutes(task))
        if task.hard_end is not None and task.hard_end <= clock.tonight_quiet_start_utc:
            if finish_at > task.hard_end:
                raise ValidationError("The extension leaves too little time before the hard deadline.")
        elif finish_at > clock.tonight_quiet_start_utc:
            raise ValidationError("The extension leaves too little time before quiet hours.")
        elif task.hard_end is not None and finish_at > task.hard_end:
            raise ValidationError("The extension leaves too little time before the hard deadline.")

    def _silent(self, reason: ReasonCode) -> Decision:
        now = self.clock.now_utc()
        return Decision(DecisionKind.SILENT, now, (reason,))
