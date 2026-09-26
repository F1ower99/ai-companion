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

### 阶段 2：SQLite、目标、任务和基础记忆（已完成）

**交付文件：**

- `src/companion/domain/models.py` 和 `errors.py`：不可变的 Goal、Task、Memory、筛选对象及校验。
- `src/companion/ports/repositories.py`：目标、任务和记忆仓储 Protocol。
- `src/companion/application/task_service.py`：目标和任务用例。
- `src/companion/infrastructure/sqlite/database.py`、`migrations.py`、`repositories.py`：本地路径、事务、迁移及持久化实现。
- `src/companion/desktop/tasks_dialog.py`：今日任务界面；`chat_window.py` 和 `app.py` 提供入口、装配与存储故障降级。
- 领域、仓储、迁移、UI 和应用生命周期测试。

**已交付接口：**

- `GoalRepository` 支持新增、读取、列出启用目标和删除；存在关联任务时拒绝删除。
- `TaskRepository` 支持新增、读取、按日稳定排序、更新进度及标记完成；两种完成操作返回更新后的 Task。
- `MemoryRepository.search(query, limit=5)` 支持文本、类别、来源、过期筛选及按重要性/新近程度排序。
- `TaskService.complete_units(task_id, count)` 只接受正增量并将进度封顶；目标必须存在且启用。
- schema version 1 创建七张路线图业务表和 `schema_migrations` 元数据表。

- [x] 为领域对象和服务写入输入边界、进度封顶、关联目标和相邻任务隔离测试。
- [x] 建立版本化 SQLite 迁移，覆盖七张业务表、约束、外键、级联删除及迁移失败回滚。
- [x] 实现本地数据库路径、外键启用、事务、目标/任务/记忆仓储与稳定排序。
- [x] 通过重新打开数据库连接验证数据持久化，并验证记忆筛选、过期排除、limit 和按 id 删除。
- [x] 增加“今日任务”界面、添加/完成/进度操作、应用装配及存储不可用降级。
- [x] 运行 `python -m pytest -q`：85 项通过；`compileall` 和 `pip check` 通过。

### 阶段 3：主动决策与提醒引擎（已完成）

**设计与实现：**

- 规格：[`2026-09-24-stage-3-proactive-decision-design.md`](../docs/superpowers/specs/2026-09-24-stage-3-proactive-decision-design.md)。
- 计划：[`2026-09-26-stage-3-proactive-decision.md`](../docs/superpowers/plans/2026-09-26-stage-3-proactive-decision.md)。
- `src/companion/domain/decisions.py` 提供无 Qt、SQLite、网络和系统时钟依赖的确定性 decision engine。
- `src/companion/ports/clock.py`、`infrastructure/system_clock.py` 注入 UTC、本地日期、本地日界和安静时段；`ports/activity.py` 只定义粗粒度 idle/focused/unknown 接口。
- schema v2 以追加迁移方式保存软计划时间、提醒状态、全局冷却、事件和提醒偏好；v1 `reminders` 占位表保持不变。
- `application/proactive_reminder_service.py` 负责组装快照、提交提醒/用户动作并重新评估；`desktop/reminder_scheduler.py`、`reminder_card.py` 和 `reminder_settings_dialog.py` 只处理调度和展示。
- Today Tasks 可选填写本地计划开始日期/时间；提醒卡提供“现在做、稍后、延长、今天跳过、已完成”和关闭动作。

**行为边界：**

- 规则涵盖 P0/P1/P2、Goal 启用状态、剩余数量估算、软计划宽限、hard_start/hard_end、晚间容量、全局/单任务冷却、稍后、每日一次延期和本地日跳过。
- 默认提醒开启，安静时段 22:00–08:00；提醒开关和安静时段是绝对静默门控。
- Stage 3 的活动来源默认为 `unknown`，不采集进程/窗口/键盘/屏幕信息；普通提醒在未知活动时保持安静，只有满足可完成条件的 P0 近截止任务可显示无声音非模态卡片。
- 延期不会改写硬截止；到期后重新读取任务进度和活动快照，完整运行 decision engine。

- [x] 添加时间、活动和提醒领域模型及可重复的规则 decision engine 测试。
- [x] 增加 Clock/local-time resolver 和 TaskService 时间注入，覆盖本地日界及 DST 无效/歧义输入边界。
- [x] 用 SQLite schema v2 追加计划时间和提醒持久化，覆盖迁移回滚、幂等键、事务原子性及重启读取。
- [x] 实现提醒应用服务、动作生命周期、延期/稍后/跳过语义、错误降级与安全的 unknown activity 默认值。
- [x] 接入紧凑设置入口、非模态提醒卡、60 秒调度器和任务计划日期/时间输入。
- [x] 验收 19:30 计划不会机械弹出；20:10 连续专注 130 分钟后重评晚间任务；延期后重新加载进度/活动。
- [x] 全量测试、compileall、pip check 和 Stage 独立提交通过；Windows 原生活动监测仍按隐私边界延期。

### 阶段 3 之后延期：Windows 活动感知

当前 `ActivitySource` 的正式默认实现返回 `unknown`。只有未来明确提供粗粒度、可暂停的状态来源后，普通 focused-task 提醒才会启用。此工作另立阶段，不读取窗口标题、键盘内容或屏幕画面。

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

### 阶段 6：Agent 决策、提醒、延期协商（旧计划已由阶段 3 取代）

原计划中的 `InterventionContext`、基础阈值和 `NegotiationService` 已被阶段 3 的更完整确定性决策模型、提醒生命周期、持久化和 UI 取代，不再重复实现。进入本阶段编号前需根据阶段 4/5 的实际交付重新规划剩余 Companion/Agent 集成；LLM 仍不得决定基础调度、deadline、cooldown、snooze 或 extension。

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

阶段 1 桌面壳、阶段 2 本地数据基础和阶段 3 确定性主动决策/提醒闭环已交付。Stage 3 全量套件包含 200 项通过测试，compileall 和 pip check 通过；Windows 原生活动感知尚未接入，所以未知活动下普通提醒保持安静。下一阶段沿用原路线图中的阶段 4：任务计划和学期日历。LLM 对话、语音、打包、语义记忆和跨设备同步仍未实现，整体 MVP 尚未完成。
