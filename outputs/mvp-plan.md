# AI Companion MVP 实施计划

> **For agentic workers:** 本计划按小阶段逐项执行。每个阶段完成后运行该阶段的测试与构建，再进入下一阶段。

**目标：** 在 Windows 上交付一个本地优先的 Companion MVP，能理解当天任务和应用使用情况，在合适时机提醒、协商一次延期，并通过文本和基础语音交流。

**架构：** 使用 PySide6 做桌面外壳；Agent、计划、记忆、日历和策略放在无 UI 依赖的 Python 包；Windows、SQLite、LLM、STT 和 TTS 都由适配器实现。首版的打断策略为确定性本地逻辑，LLM 只负责语言交互。

**技术栈：** Python 3.10+、PySide6 Essentials、SQLite、pytest、Pyright；Windows 使用 `ctypes` 系统 API；provider 通过 Python Protocol 隔离。阶段 7 再安装 PySide6 Addons 提供 Qt Multimedia。

**设计文档：** [architecture-decision.md](architecture-decision.md)

## 全局约束

- 目标平台：Windows 10/11 x64。
- 个人计划、活动、记忆与对话默认保存在本地 SQLite。
- 活动数据只含 App Name、Start Time、End Time、Duration、Category；不采集按键、窗口标题、屏幕截图或聊天内容作为活动遥测。
- 活动监测、麦克风、主动提醒均可独立暂停；麦克风默认 push-to-talk。
- API Key 只能存 Windows Credential Manager，不能写配置文件、SQLite、日志或源代码。
- `domain` 不依赖 Qt、Windows API、数据库驱动实现或厂商 SDK。
- LLM 不决定打断，也不能改写硬截止；Agent Decision Loop 必须留下原因码。
- 每个数据 schema 变化都通过带版本的 SQLite migration。
- 不复制候选桌宠项目代码或素材；若以后引入外部角色包，逐项记录版权和许可证。

## 评审重点

1. 监测暂停或 Windows API 失败时，活动采集必须停止并保持应用可用；覆盖 activity adapter 和设置开关测试。
2. idle、休眠、锁屏、应用切换不能把空闲时间错误算作某个应用的专注时长；覆盖 session 分段测试。
3. 周次边界、单双周、节假日和调休同日出现时，按日期 exception 优先；覆盖日历纯函数测试。
4. 用户请求延长超过剩余可用时间或跨硬截止时，延期不得悄悄覆盖原 deadline；覆盖 decision service 测试。
5. provider 超时、无麦克风、API Key 不存在或远端返回错误时，UI 不挂起、secret 不写日志；覆盖 provider error path 测试。

---

### 阶段 1：桌宠运行壳（本轮开始）

**文件：**

- 新建 `pyproject.toml`、`.gitignore`、`README.md`。
- 新建 `src/companion/desktop/app.py`、`pet_window.py`、`chat_window.py`、`tray.py`。
- 新建 `tests/desktop/test_pet_window.py`、`test_app_lifecycle.py`。

**接口：**

- `PetWindow(chat_window: ChatWindow)`：透明、无边框、置顶；启动时放在主屏可用区右下角；按住并移动时拖动，点击而未拖动时显示聊天窗；`set_click_through(enabled: bool) -> None` 切换输入穿透。系统托盘不可用时，右键菜单可打开聊天或退出；关闭桌宠退出程序，关闭聊天保留桌宠。
- `ChatWindow()`：可聚焦的小型聊天面板；此阶段只构建 UI 和事件边界，不假装已经连接模型。
- `create_application(argv: Sequence[str]) -> QApplication`：构建桌宠、聊天窗和托盘并运行。

- [x] 建立 Python 包元数据，首阶段使用 `PySide6-Essentials==6.11.2`（桌宠 UI 所需 Qt 模块），开发依赖包含 `pytest>=8,<9` 和 `pytest-qt>=4.4,<5`；Qt Multimedia Addons 留到阶段 7。
- [x] 为 PetWindow 写 QtTest，验证 translucent/frameless/stays-on-top flags、输入穿透开关、点击显示 ChatWindow、拖动后位置变化、亚阈值鼠标抖动和主屏初始位置；增加无托盘事件循环的子进程回归测试。
- [x] 建立 `.venv` 并安装项目与测试依赖；先运行 `python -m pytest tests/desktop/test_pet_window.py -q`，确认功能断言失败。
- [x] 实现宠物矢量绘制、右下角初始位置、点击/拖动判定、聊天面板、托盘退出/显示和鼠标穿透开关；无托盘时提供宠物右键菜单与明确退出路径。
- [x] 运行 `python -m pytest -q` 和计时关闭的 offscreen 应用启动冒烟；检查启动无异常、聊天窗可开关、退出后进程结束。
- [x] 记录 milestone 1 的运行方式、测试结果与当前限制。

### 阶段 2：SQLite、目标、任务和基础记忆

**文件：**

- 新建 `src/companion/domain/models.py`、`memory.py`、`application/task_service.py`。
- 新建 `src/companion/infrastructure/sqlite/database.py`、`migrations.py`、`repositories.py`。
- 新建 `tests/domain/test_task_service.py`、`tests/infrastructure/test_sqlite_repositories.py`。

**接口：**

- `Task(id: str, title: str, goal_id: str, due_date: date, planned_minutes: int, priority: Priority, completed_units: int = 0, target_units: int | None = None, hard_start: datetime | None = None, hard_end: datetime | None = None)`。
- `TaskRepository.add(task) -> None`，`get(task_id) -> Task | None`，`list_for_day(day) -> list[Task]`，`mark_completed(task_id) -> None`。
- `MemoryRepository.add(memory) -> None`，`search(query: MemoryQuery, limit: int = 5) -> list[Memory]`，`delete(memory_id) -> None`。
- `TaskService.complete_units(task_id, count: int) -> Task`：拒绝负数并把完成量限制到 target。

- [ ] 写任务完成量、目标隔离、记忆类别筛选和删除的失败测试。
- [ ] 建立 schema version 1，迁移创建 goals/tasks/memories/conversations/messages/settings/reminders 表和外键。
- [ ] 实现 SQLite repository，所有写入使用事务；列表固定按优先级、deadline、创建顺序排序。
- [ ] 运行 `python -m pytest tests/domain tests/infrastructure -q`；重启新 connection 后确认写入仍存在。
- [ ] 增加聊天 UI 的任务列表入口，仅调用 TaskService，不把 SQL 写在 UI。

### 阶段 3：Windows 活动感知

**文件：**

- 新建 `src/companion/ports/activity.py`、`src/companion/adapters/windows/foreground.py`、`idle.py`、`activity_monitor.py`。
- 新建 `src/companion/application/activity_service.py`。
- 新建 `tests/adapters/test_activity_monitor.py` 和 Windows API mock 测试。

**接口：**

- `ActivitySnapshot(app_name: str | None, category: str | None, idle_seconds: int, observed_at: datetime)`。
- `ActivitySource.snapshot() -> ActivitySnapshot`。
- `ActivityMonitor.sample(snapshot, at) -> ActivitySessionDelta | None`；同应用合并连续片段，idle 超阈值、监测暂停、休眠恢复和进程切换时关闭当前片段。
- 默认采样周期 5 秒；默认 idle 阈值 300 秒；设置可更改。

- [ ] 用假 ActivitySource 写切换应用、unknown app、idle 到阈值、暂停/恢复的测试。
- [ ] 通过 `GetForegroundWindow` 和 `GetWindowThreadProcessId` 获取 PID，通过进程 API 读取 exe basename；仅返回 basename，不读取窗口标题。
- [ ] 通过 `GetLastInputInfo` 获取 session idle 秒数；API 失败返回明确 error 状态，不伪造有效活动。
- [ ] 将 session 变更写入 activity_sessions，并以最小化的本地 UI 开关控制采样。
- [ ] 运行 activity adapter 测试；Windows 上验证 VS Code 30 分钟模拟片段和 idle 分段。

### 阶段 4：任务计划和学期日历

**文件：**

- 新建 `src/companion/domain/calendar.py`、`study_plan.py`。
- 修改 schema migrations/repositories，新增 academic_terms/course_rules/calendar_exceptions。
- 新建 `tests/domain/test_calendar.py`、`test_study_plan.py`。

**接口：**

- `CourseRule(weekday: int, start_week: int, end_week: int, week_parity: Literal['all','odd','even'], start_time: time, end_time: time, course_name: str)`。
- `CalendarException(day: date, kind: Literal['holiday','makeup','rest'], replacement_weekday: int | None)`。
- `courses_for_day(day: date, term: AcademicTerm, rules: Sequence[CourseRule], exceptions: Sequence[CalendarException]) -> list[CourseOccurrence]`。
- 日期 exception 优先于规则；`makeup` 根据 replacement weekday 选课；周次从 term.week_one_start 计算。

- [ ] 写教学周第一天、学期起止边界、单双周、节假日覆盖、周末调休补课测试。
- [ ] 实现纯函数和 repository query；输入日期不属于 term 时返回空列表。
- [ ] Study Planner 提供当天剩余任务、计划分钟与硬截止摘要。
- [ ] 运行 domain/repository 测试，检查 exception 优先级固定且无隐式本机日期依赖。

### 阶段 5：LLM provider、人格和文字聊天

**文件：**

- 新建 `src/companion/ports/llm.py`、`providers/openai_compatible.py`、`application/chat_service.py`。
- 新建 `src/companion/adapters/windows/secrets.py`、`settings_service.py`。
- 修改聊天窗加入 provider 设置与发送状态；新增 `tests/application/test_chat_service.py`、`test_secret_store.py`。

**接口：**

- `LLMProvider.complete(request: ChatRequest) -> ChatResponse`，取消与超时返回类型化错误。
- `SecretStore.get(key: str) -> str | None`，`set(key: str, secret: str) -> None`，`delete(key: str) -> None`。
- `ChatService.send(conversation_id: str, user_text: str) -> ChatResponse`：先保存用户消息，再按需检索最多 5 条记忆，调用 provider，保存回答和摘要事件。
- `PersonalityProfile` 独立保存语气、原则、提醒偏好；prompt builder 只渲染 persona + 当天上下文，不拼全部历史。

- [ ] 写 mock provider 测试：对话保存、记忆上限、timeout、401 和空响应。
- [ ] 实现 provider Protocol 与一种 OpenAI-compatible HTTP provider；其他厂商和本地模型保持可替换接口。
- [ ] 实现 Windows secret adapter；验证取回、覆盖、删除和日志无 secret。
- [ ] 运行应用级测试；无 Key 时 UI 显示配置提示，不发网络请求。

### 阶段 6：Agent 决策、提醒、延期协商

**文件：**

- 新建 `src/companion/domain/decisions.py`、`application/agent_loop.py`、`reminder_service.py`。
- 新建 `tests/domain/test_decisions.py`、`tests/application/test_agent_loop.py`、`test_reminder_service.py`。

**接口：**

- `InterventionContext(now, activity, tasks, recent_reminders, preferences, relevant_memories)`。
- `Decision(kind: Literal['interrupt','wait','stay_silent'], reason_codes: tuple[str, ...], proposed_message: str | None)`。
- `decide(context: InterventionContext) -> Decision` 为纯函数；基础阈值为 100 分钟后评估，120 分钟且高优先级任务未完成时提醒；30 分钟时不提醒。
- `NegotiationService.request_extension(task_id: str, minutes: int, now: datetime) -> ExtensionResult`：不改 hard_end，延期到期时产生一次 ReminderEvent。

- [ ] 写 acceptance 测试：专注应用使用 30 分钟静默；120 分钟且高优先级任务未完成时提醒；主要任务完成可继续；冷却期不重复提醒。
- [ ] 写延期边界测试：剩余计划允许则接受 20 分钟；超过硬截止则拒绝或给出可选重排；二次 reminder 只发一次。
- [ ] 实现规则型 Decision Service，LLM 只可润色已批准的通知文案，不影响 Decision.kind 或 deadline。
- [ ] 连接桌宠 Warning 状态、聊天卡片、通知和用户的“暂停提醒/今天不再提醒”。
- [ ] 运行完整测试并端到端演练 30 分钟静默、120 分钟提醒、20 分钟延期和到期复提醒。

### 阶段 7：基础语音、打包和首版验收

**文件：**

- 新建 `src/companion/ports/voice.py`、`adapters/voice/push_to_talk.py`、`tts.py`、`stt_provider.py`。
- 新建 `src/companion/desktop/settings_window.py`、`tests/application/test_voice_session.py`。
- 添加 `pysidedeploy.spec`、许可清单和 Windows 构建说明。

**接口：**

- `STTProvider.transcribe(audio: AudioChunk, cancel: CancellationToken) -> Transcript`。
- `TTSProvider.speak(text: str, cancel: CancellationToken) -> None`，`stop() -> None`。
- `VoiceSession.start_push_to_talk() -> None`、`stop_capture() -> None`、`interrupt_output() -> None`。
- 录音仅在按住/点击麦克风控件后开始；UI 显示 Listening/Talking 状态；用户打断立即停止当前 TTS。

- [ ] 写 voice session 测试：停录送 STT、取消不送出、用户插话调用 TTS.stop、麦克风不可用有清晰错误。
- [ ] 安装 `.[voice]`（其中 `PySide6-Addons==6.11.2` 与 Essentials 匹配），以 Qt Multimedia 采集/播放音频；第一 provider 可使用用户显式配置的云端 STT/TTS，上传前 UI 显示 provider 和数据类型。
- [ ] 运行全量测试和 `python -m companion.desktop.app`；构建 Windows 包后在新用户配置目录启动一次。
- [ ] 完整复核私密数据目录、暂停监测、暂停麦克风、删除记忆、清除历史、关闭主动提醒五项控制。
- [ ] 添加开机启动设置，默认关闭；只写当前用户 Run 项，用户关闭时删除本应用自己的条目。

## 最终验收脚本

1. 创建三个通用任务：短时记忆练习、优先课程学习和个人项目。
2. 启动应用后，桌宠出现在主屏右下角；可拖动；点击打开聊天窗；托盘可退出。
3. 选择开始监测并打开专注应用。前 30 分钟没有提醒，活动记录只有 app name、时间、时长和分类。
4. 模拟/等待个人项目连续活动到 120 分钟且高优先级任务未完成；Agent 给出原因明确的提醒。
5. 回复“再给我 20 分钟”；系统根据剩余计划决定是否接受。若接受，保存 one-time deadline，不改项目 hard deadline。
6. deadline 到达后提醒一次。完成高优先级任务后继续使用专注应用，不再重复打扰。
7. 暂停监测、暂停麦克风、删除记忆、清除对话和关闭提醒都能立即生效；日志里不出现 API Key。

## 当前阶段边界

阶段 1 已交付桌宠运行壳与可运行方式：全量测试 10 项通过，依赖和语法检查通过，计时关闭的 offscreen 启动冒烟通过，独立审阅没有遗留问题。原生 Windows 鼠标穿透、托盘恢复和焦点行为仍需手工实机验收。聊天 UI 尚未接入模型；阶段 2–7 未完成，因此整体 MVP 尚未验收通过。
