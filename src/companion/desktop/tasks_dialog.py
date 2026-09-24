from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from companion.domain.models import Priority, Task, TaskStatus


class TodayTasksDialog(QDialog):
    def __init__(self, task_service, today: date | None = None) -> None:
        super().__init__()
        self.task_service = task_service
        self.today = today or date.today()
        self.setWindowTitle("今日任务")
        self.resize(460, 560)

        heading = QLabel("今日任务")
        heading.setObjectName("tasksTitle")
        self.storage_hint = QLabel(self.today.strftime("%Y年%m月%d日"))
        self.storage_hint.setObjectName("tasksDate")

        goal_row = QHBoxLayout()
        goal_row.addWidget(QLabel("关联目标"))
        self.goal_combo = QComboBox()
        self.goal_combo.setObjectName("goalCombo")
        goal_row.addWidget(self.goal_combo, 1)
        self.toggle_goal_button = QPushButton("新增目标")
        self.toggle_goal_button.setObjectName("toggleGoalButton")
        goal_row.addWidget(self.toggle_goal_button)

        self.goal_form = QGroupBox("创建目标")
        goal_form_layout = QFormLayout(self.goal_form)
        self.goal_name_input = QLineEdit()
        self.goal_name_input.setObjectName("goalNameInput")
        self.goal_name_input.setPlaceholderText("例如：完成课程复习")
        self.goal_target_input = QLineEdit()
        self.goal_target_input.setObjectName("goalTargetInput")
        self.goal_target_input.setPlaceholderText("可选")
        self.add_goal_button = QPushButton("保存目标")
        self.add_goal_button.setObjectName("addGoalButton")
        goal_form_layout.addRow("目标名称", self.goal_name_input)
        goal_form_layout.addRow("目标说明", self.goal_target_input)
        goal_form_layout.addRow(self.add_goal_button)
        self.goal_form.hide()

        self.goal_hint_label = QLabel("请先创建一个目标，再添加任务。")
        self.goal_hint_label.setWordWrap(True)

        task_form = QGroupBox("添加任务")
        task_form_layout = QFormLayout(task_form)
        self.title_input = QLineEdit()
        self.title_input.setObjectName("titleInput")
        self.title_input.setPlaceholderText("要完成什么？")
        self.minutes_input = QSpinBox()
        self.minutes_input.setObjectName("minutesInput")
        self.minutes_input.setRange(0, 24 * 60)
        self.minutes_input.setValue(30)
        self.priority_combo = QComboBox()
        self.priority_combo.setObjectName("priorityCombo")
        for priority in Priority:
            self.priority_combo.addItem(priority.name, priority)
        self.priority_combo.setCurrentIndex(self.priority_combo.findData(Priority.P1))
        self.target_input = QSpinBox()
        self.target_input.setObjectName("targetInput")
        self.target_input.setRange(0, 1_000_000)
        self.target_input.setSpecialValueText("不设置数量目标")
        task_form_layout.addRow("任务名称", self.title_input)
        task_form_layout.addRow("计划分钟", self.minutes_input)
        task_form_layout.addRow("优先级", self.priority_combo)
        task_form_layout.addRow("数量目标", self.target_input)
        self.add_task_button = QPushButton("添加任务")
        self.add_task_button.setObjectName("addTaskButton")
        task_form_layout.addRow(self.add_task_button)

        self.task_list = QListWidget()
        self.task_list.setObjectName("taskList")
        self.empty_label = QLabel("今天还没有任务。添加一项任务开始吧。")
        self.empty_label.setObjectName("emptyTasksLabel")
        self.empty_label.setWordWrap(True)

        action_row = QHBoxLayout()
        self.complete_button = QPushButton("完成所选任务")
        self.complete_button.setObjectName("completeTaskButton")
        self.progress_input = QSpinBox()
        self.progress_input.setObjectName("progressInput")
        self.progress_input.setRange(1, 1_000_000)
        self.progress_input.setValue(1)
        self.progress_button = QPushButton("记录数量进度")
        self.progress_button.setObjectName("progressTaskButton")
        action_row.addWidget(self.complete_button)
        action_row.addWidget(self.progress_input)
        action_row.addWidget(self.progress_button)

        self.status_label = QLabel()
        self.status_label.setObjectName("taskStatus")
        self.status_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(self.storage_hint)
        layout.addLayout(goal_row)
        layout.addWidget(self.goal_form)
        layout.addWidget(self.goal_hint_label)
        layout.addWidget(task_form)
        layout.addWidget(self.empty_label)
        layout.addWidget(self.task_list, 1)
        layout.addLayout(action_row)
        layout.addWidget(self.status_label)

        self.toggle_goal_button.clicked.connect(self._toggle_goal_form)
        self.add_goal_button.clicked.connect(self.add_goal)
        self.add_task_button.clicked.connect(self.add_task)
        self.complete_button.clicked.connect(self.complete_selected)
        self.progress_button.clicked.connect(self.record_progress)

        self.setStyleSheet(
            "QDialog { background: #f7f5f1; color: #253c3b; }"
            "QGroupBox { font-weight: 600; border: 1px solid #d7dfda; border-radius: 8px; margin-top: 8px; padding: 8px; }"
            "QLineEdit, QComboBox, QSpinBox, QListWidget { padding: 6px; border: 1px solid #d7dfda; border-radius: 6px; background: white; }"
            "QPushButton { padding: 7px 10px; border: 0; border-radius: 7px; background: #98b9aa; }"
            "QLabel#tasksDate, QLabel#taskStatus { color: #607270; }"
        )
        self.refresh()

    def _toggle_goal_form(self) -> None:
        self.goal_form.setVisible(not self.goal_form.isVisible())

    def _show_error(self) -> None:
        self.status_label.setText("本地任务暂时不可用，请检查后重试。")

    def refresh(self, selected_goal_id: str | None = None) -> None:
        self.refresh_goals(selected_goal_id)
        self.refresh_tasks()

    def refresh_goals(self, selected_goal_id: str | None = None) -> None:
        try:
            goals = self.task_service.list_active_goals()
        except Exception:
            self._show_error()
            goals = []
        self.goal_combo.clear()
        for goal in goals:
            self.goal_combo.addItem(goal.name, goal.id)
        if selected_goal_id is not None:
            index = self.goal_combo.findData(selected_goal_id)
            if index >= 0:
                self.goal_combo.setCurrentIndex(index)
        has_goals = self.goal_combo.count() > 0
        self.goal_combo.setEnabled(has_goals)
        self.goal_hint_label.setVisible(not has_goals)
        self.add_task_button.setEnabled(has_goals)
        self.goal_form.setVisible(not has_goals or self.goal_form.isVisible())

    def refresh_tasks(self) -> None:
        self.task_list.clear()
        try:
            tasks = self.task_service.list_for_day(self.today)
        except Exception:
            self._show_error()
            tasks = []
        for task in tasks:
            status = "已完成" if task.status is TaskStatus.COMPLETED else "待完成"
            progress = (
                f" · {task.completed_units}/{task.target_units}"
                if task.target_units is not None
                else ""
            )
            item = f"{task.title} · P{int(task.priority)} · {status}{progress}"
            self.task_list.addItem(item)
            self.task_list.item(self.task_list.count() - 1).setData(
                Qt.ItemDataRole.UserRole, task.id
            )
        is_empty = self.task_list.count() == 0
        self.empty_label.setVisible(is_empty)

    def add_goal(self) -> None:
        name = self.goal_name_input.text()
        target_text = self.goal_target_input.text().strip()
        try:
            goal = self.task_service.add_goal(
                name=name,
                target=target_text or None,
                priority=Priority.P1,
            )
            self.refresh_goals(selected_goal_id=goal.id)
            self.goal_form.hide()
            self.goal_name_input.clear()
            self.goal_target_input.clear()
            self.status_label.setText("目标已保存。")
        except Exception:
            self._show_error()

    def add_task(self) -> None:
        goal_id = self.goal_combo.currentData()
        if goal_id is None:
            self.goal_hint_label.show()
            return
        try:
            self.task_service.add_task(
                title=self.title_input.text(),
                goal_id=goal_id,
                due_date=self.today,
                planned_minutes=self.minutes_input.value(),
                priority=self.priority_combo.currentData(),
                target_units=self.target_input.value() or None,
            )
            self.status_label.setText("任务已添加。")
            self.refresh_tasks()
        except Exception:
            self._show_error()

    def _selected_task_id(self) -> str | None:
        item = self.task_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def complete_selected(self) -> None:
        task_id = self._selected_task_id()
        if task_id is None:
            self.status_label.setText("请先选择一项任务。")
            return
        try:
            self.task_service.mark_completed(task_id)
            self.status_label.setText("任务已完成。")
            self.refresh_tasks()
        except Exception:
            self._show_error()

    def record_progress(self) -> None:
        task_id = self._selected_task_id()
        if task_id is None:
            self.status_label.setText("请先选择一项任务。")
            return
        try:
            self.task_service.complete_units(task_id, self.progress_input.value())
            self.status_label.setText("进度已记录。")
            self.refresh_tasks()
        except Exception:
            self._show_error()
