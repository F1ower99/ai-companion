# AI Companion MVP 实施计划

> **For agentic workers:** 本计划按小阶段逐项执行。每个阶段完成后运行该阶段的测试与构建，再进入下一阶段。

**目标：** 在 Windows 上交付一个本地优先的 Companion MVP，能理解当天任务和粗粒度的 idle/recently-active 状态，在合适时机提醒、协商一次延期，并通过文本和基础语音交流。

**架构：** 使用 PySide6 做桌面外壳；Agent、计划、记忆、日历和策略放在无 UI 依赖的 Python 包；Windows、SQLite、LLM、STT 和 TTS 都由适配器实现。首版的打断策略为确定性本地逻辑，LLM 只负责语言交互。

**技术栈：** Python 3.10+、PySide6 Essentials、SQLite、pytest、Pyright；Windows 使用 `ctypes` 系统 API；provider 通过 Python Protocol 隔离。阶段 7 再安装 PySide6 Addons 提供 Qt Multimedia。

**设计文档：** [architecture-decision.md](architecture-decision.md)

## 全局约束

- 目标平台：Windows 10/11 x64。
- 个人计划、记忆、对话和活动感知开关保存在本地 SQLite；当前不持久化活动状态或活动历史。
- 活动感知仅可选读取当前 Windows 会话最近输入的时间差，不读取应用名称、窗口标题、输入内容、屏幕截图或聊天内容。
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

### 阶段 3 之后延期：细粒度 Windows 活动感知

阶段 6 已提供最小的可选 idle/recently-active 来源；按应用类别统计、活动历史和任务推断仍延期，不读取窗口标题、键盘内容或屏幕画面。

### 阶段 4：任务计划和学期日历（已完成）

**文件：**

- 新建 `src/companion/domain/calendar.py`、`study_plan.py`。
- 修改 schema migrations/repositories，新增 academic_terms/course_rules/calendar_exceptions。
- 新建 `tests/domain/test_calendar.py`、`test_study_plan.py`。

**接口：**

- `CourseRule(weekday: int, start_week: int, end_week: int, week_parity: Literal['all','odd','even'], start_time: time, end_time: time, course_name: str)`。
- `CalendarException(day: date, kind: Literal['holiday','makeup','rest'], replacement_weekday: int | None)`。
- `courses_for_day(day: date, term: AcademicTerm, rules: Sequence[CourseRule], exceptions: Sequence[CalendarException]) -> list[CourseOccurrence]`。
- 日期 exception 优先于规则；`makeup` 根据 replacement weekday 选课；周次从 term.week_one_start 计算。

- [x] 写教学周锚点、学期 inclusive 边界、单双周、节假日覆盖、周末调休补课和排序测试。
- [x] 实现纯函数和 SQLite repository；输入日期不属于 term 时返回空列表。
- [x] Study Planner 提供调用方选定的当天剩余任务、预计剩余分钟与硬截止摘要。
- [x] 运行 domain/repository 测试；异常优先级固定，核心逻辑没有隐式本机日期依赖。
- [x] schema v3 以追加迁移保存学期、周期课程和日期异常，并验证 v2 数据保留与失败回滚。
- [x] 全量回归、compileall、pip check、差异与 secret 检查通过；Stage 4 独立提交。

Stage 4 spec 和 implementation plan：[`Stage 4 design spec`](../docs/superpowers/specs/2026-09-26-stage-4-academic-calendar-design.md)、[`Stage 4 implementation plan`](../docs/superpowers/plans/2026-09-26-stage-4-academic-calendar.md)。课程时间保留为本地 wall time；当前没有日历 UI、导入/同步或自动调整任务。

### 阶段 5：本地对话与可选文字 provider（实现完成；真实 provider 体验待人工验证）

Stage 5 已实现本地可测试的文字对话路径和可选的 OpenAI-compatible HTTPS adapter。调用真实 provider 尚未人工体验；在用户配置自己的密钥并选择要发送的内容前，本阶段只用 fake provider/mock transport 测试，没有外部请求。

- [x] 使用 migration v4 保存 conversation、message delivery state 和非 secret provider settings；启动时恢复 pending 消息为状态不确定的 failed 消息。
- [x] 增加 Qt-free ChatService、明确注入的 clock/repositories/provider、受限上下文构造、同一消息重试、取消和持久化恢复。
- [x] 增加不跟随跨 host redirect、不自动重试、不 streaming、不启用 tools 的标准库 HTTPS provider adapter；测试只走 mock transport。
- [x] 将 provider credential 存入 Windows Credential Manager；不支持的平台和凭据 API 错误不会回退到明文存储。
- [x] 每次发送旁显示当前 host、已启用的近期对话/记忆/今日计划类别和会随请求发送的人格设置；未配置 secret 时保留草稿并且零网络请求。
- [x] 覆盖 consent 失效、取消、provider 错误、重启恢复重试、多个失败消息依次重试和清空后新建活动对话。
- [x] Stage 1–4 + Stage 5 全量测试 329 项通过；compileall、pip check、diff 检查及 secret pattern scan 通过；Stage 5 独立提交。

spec 和 plan：[`Stage 5 design spec`](../docs/superpowers/specs/2026-10-11-stage-5-conversation-and-provider-design.md)、[`Stage 5 implementation plan`](../docs/superpowers/plans/2026-10-11-stage-5-conversation-and-provider.md)。真实 provider UX 需要人工配置凭据、审核隐私摘要并发送用户主动选择的测试消息，仍待验证。

### 阶段 6：最小本地活动感知（实现完成；等待 Windows 手动体验）

Stage 3 已完成旧阶段号里的决策与延期模型；Stage 6 实现仅凭当前 Windows 会话最近输入时间产生 `idle / focused / unknown`。功能默认关闭，五分钟无输入归为 idle；持久化只有一个开关，状态和时间不保存。提醒设置可单独启停，未启用、API 失败或不支持平台都退化为 `unknown`。不记录进程/应用名称、窗口标题、输入或屏幕内容。

规格与计划：[`Stage 6 design`](../docs/superpowers/specs/2026-10-12-stage-6-minimal-activity-awareness-design.md)、[`Stage 6 implementation plan`](../docs/superpowers/plans/2026-10-12-stage-6-minimal-activity-awareness.md)。真实 Windows 空闲行为仍待用户在设置中主动启用并手动体验；没有测试通过读取真实输入状态完成。

### 阶段 7：基础语音、打包和首版验收

Stage 7A 已实现 provider-neutral 本地语音会话基础：PCM/转写校验、local-only ports、取消/打断及迟到结果隔离，Qt 转写只交接到空草稿。后续 7C–7G 已接入本地识别、受限采集和显式朗读；默认不配置模型时语音保持关闭。云端语音不属于当前批准范围。

Stage 7B 已建立 standalone 配置、无删除的构建入口、独立构建目录和依赖许可元数据清单。当前环境缺少 MSVC 与构建依赖，preflight 已正确阻止构建；未生成 exe，部署 dry-run 与真实打包/启动验收均未完成。说明见 README；临时 LOCALAPPDATA 不能隔离 Credential Manager，凭据验收需要单独 Windows 测试账号。

Stage 7C 已按用户选择的离线模型方向实现可选 faster-whisper CPU/int8 识别适配器和受限 WAV smoke 工具；Whisper base 的固定发布版本与文件哈希已核验。公开英文样例已通过离线识别；中文样例已实际运行但有明显识别错误，尚未验收。WAV 工具的奇数尾字节问题已修复并通过回归测试。真实测试记录见 `docs/offline-stt-assets-2026-10-18.md`。

Stage 7D/E 已实现受限 Qt 采集与后台识别交接：按住录音、60 秒上限、取消/隐藏释放、迟到结果隔离，草稿不会自动发送。自动测试只用假设备，真实麦克风体验仍待验收。

Stage 7F/G 已实现本地 Kokoro 合成、显式朗读、停止与录音前打断。耳机实际播放/自然结束/停止已验证；用户认为默认及三种备选音色仍生硬，因此自然度未通过。Qwen Serena 是 E 盘隔离实验，尚未接入产品。发布清单已覆盖 36 个语音运行依赖；实际编译与许可证发行复核仍待完成。

Stage 7H 增加默认不写入的当前用户开机启动选项：托盘打开时读取自己的 Run 值，用户勾选才写入；冲突值、无运行环境或过长命令时保持不可用。自动测试不访问真实注册表，实际登录与编译包启动仍待验收。

**文件：**

- `src/companion/ports/voice.py`、`application/voice_session.py`、`application/voice_synthesis.py`。
- `src/companion/infrastructure/local_whisper.py`、`local_kokoro.py`、`qt_microphone.py`、`qt_playback.py` 与 desktop voice/speech controllers。
- 添加 `pysidedeploy.spec`、许可清单和 Windows 构建说明。

**接口：**

- `STTProvider.transcribe(audio: AudioChunk, cancel: CancellationToken) -> Transcript`。
- `TTSProvider.speak(text: str, cancel: CancellationToken) -> None`，`stop() -> None`。
- `VoiceSession.start_push_to_talk() -> None`、`stop_capture() -> None`、`interrupt_output() -> None`。
- 录音仅在按住/点击麦克风控件后开始；UI 显示 Listening/Talking 状态；用户打断立即停止当前 TTS。

- [x] 写 fake-provider voice session 测试：停录送 STT、取消不送出、用户插话调用 TTS.stop、错误码、音频清理及并发隔离。
- [x] 选择离线引擎并实现可选 Qt Multimedia 采集/播放；真实麦克风和自然中文质量另行验收，不接入云端语音。
- [ ] 运行全量测试和 `python -m companion.desktop.app`；构建 Windows 包后在新用户配置目录启动一次。
- [ ] 完整复核私密数据目录、暂停监测、暂停麦克风、删除记忆、清除历史、关闭主动提醒五项控制。
- [x] 添加默认不写入的开机启动设置，只操作当前用户本应用的 Run 值；真实登录和编译包验收仍未完成。

## 最终验收脚本

1. 创建三个通用任务：短时记忆练习、优先课程学习和个人项目。
2. 启动应用后，桌宠出现在主屏右下角；可拖动；点击打开聊天窗；托盘可退出。
3. 在提醒设置中主动启用活动感知。最近有输入时为 `focused`，五分钟无输入后为 `idle`；暂停后下一次评估为 `unknown`。数据中没有应用名称或活动历史。
4. recent activity 连续维持 120 分钟且高优先级任务未完成时，检查 Agent 是否按已有原因码决定提醒。
5. 通过提醒卡选择延长 20 分钟；系统根据剩余计划决定是否接受。若接受，保存 one-time deadline，不改项目 hard deadline。自然语言动作解析尚未实现。
6. deadline 到达后重新评估一次。完成高优先级任务后持续与桌宠交互，确认不会重复打扰。
7. 暂停监测、暂停麦克风、删除记忆、清除对话和关闭提醒都能立即生效；日志里不出现 API Key。

## 当前阶段边界

阶段 1 桌面壳、阶段 2 本地数据基础、阶段 3 确定性主动决策/提醒闭环、阶段 4 任务计划/学期日历、阶段 5 本地对话/provider adapter 和阶段 6 可选 idle/recently-active 感知均已实现。Stage 5 真实 provider 与 Stage 6 Windows 空闲行为尚未人工体验；前者需用户自己的凭据和主动选择的测试内容，后者需用户在 UI 里主动启用。阶段 7 语音、打包和 MVP 验收将依赖用户体验测试，其中任何云端语音 provider 都需单独明示。自动语义记忆和跨设备同步仍未实现，整体 MVP 尚未完成。Stage 3/4/5/6 的阶段记录写入 `docs/overnight-report-2026-09-26.md`。
