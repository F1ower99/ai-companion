# Autonomous Development Report

报告整理日期：2026-10-16
后续开发追加：2026-10-17；见文末 Stage 7 状态及独立交接报告。
开发分支：`codex/stage3-proactive-engine`
起点：Stage 2 已完成并通过测试，Stage 3 规格已审核通过。

## 完成阶段

### Stage 3：确定性主动决策与提醒闭环

- 实现本地确定性的 Agent Decision Engine；核心逻辑不依赖 Qt、SQLite 或 LLM，时间和活动快照由调用方注入。
- 综合任务优先级、硬开始/结束时间、计划耗时、完成状态、当天剩余任务、长期目标和活动状态生成提醒决策。
- 完成 reminder lifecycle、cooldown、延期/延长/跳过/完成操作；延长到期后重新进入全量决策，不做机械重复提醒。
- 通过 SQLite 追加迁移保存提醒状态与事件，桌面端以非模态提醒卡展示决策。
- Commit：`e2e2943f6bbed8c3f312e5cdd2084904e2e9091b` — `feat: add deterministic proactive reminders`

Stage 3 的计划记录了完整回归通过，但没有保留原始测试总数。之后对该提交的重建运行得到 196 项通过、4 个应用启动子进程测试在原 4 秒限制下超时；后续将启动测试隔离到临时 `LOCALAPPDATA` 并延长超时。当前完整测试套件 370 项通过。

### Stage 4：本地课程日历与学习计划

- 增加学期、单双周课程规则、节假日/调休/休息日例外和确定性课程查询。
- 增加当天学习计划摘要，汇总剩余任务、预计分钟数和硬截止；业务逻辑不读取隐式系统日期。
- SQLite schema v3 采用追加迁移并验证旧数据保留和失败回滚。
- Stage 4 全量回归：245 项通过。
- Commit：`663f431b714757cb07790880f9f9084b30d16372` — `feat: add local academic calendar and study plan`

### Stage 5：本地对话与可选文字 Provider

- 增加本地对话和消息投递状态持久化、Qt-free ChatService、有限上下文构造、用户同意失效检测、取消、重试和启动恢复。
- 增加可选 OpenAI-compatible HTTPS adapter：有限超时和响应大小、拒绝跨 host redirect、不自动重试、不提供 streaming 或 tools。
- Provider 凭据只通过 Windows Credential Manager 保存；没有明文回退。
- 发送前界面说明 provider host 和实际发送的可选上下文；未配置凭据时保留草稿且不发网络请求。
- Stage 5 全量回归：329 项通过；Stage 5/UI focused run：65 项通过。真实 Provider 尚未用用户凭据人工体验。
- Commit：`8f95f78a2d86e06a9fc6f27ae33b0af2f361600a` — `feat: add local conversations and optional text provider`

### Stage 6：最小本地活动感知

- 增加默认关闭的 idle/recent-input 信号，状态为 `idle` / `focused` / `unknown`；仅在用户显式启用后读取当前 Windows 会话的最近输入时间。
- Win32 adapter 使用 `GetLastInputInfo` 和 `GetTickCount64`，对不明确的 tick epoch、API 失败和不支持平台 fail closed 为 `unknown`。
- SQLite schema v5 只保存一个 opt-in 布尔设置；活动状态和时间只在内存中存在，不进入聊天上下文或 Provider 请求。
- Reminder Settings 增加隐私说明和启停控制；写入成功后恰好触发一次提醒重评估，保存失败会恢复原设置。
- Stage 6 全量回归：370 项通过（功能提交后 4.96 秒）；Windows adapter 测试 17 项通过。另有 compileall、`pip check`、Git whitespace 检查、secret/debug/activity API 范围扫描通过。
- 独立复审发现并修复了 32 位输入 tick 长周期歧义；修复覆盖了跨 32 位周期的新输入与短 rollover。复审后无剩余行为问题。
- Commit：`afa34dd7fc64f5b4e3320fb710d4b88c1480cb04` — `feat: add opt-in local activity awareness`

## 关键架构决策

- 基础调度和 reminder lifecycle 保持确定性、本地运行；不把任务计划或 deadline 交给 LLM 决定。
- Decision Engine 与 Qt、SQLite 解耦；系统时间、仓库和活动来源通过接口注入，逻辑使用 fake clock/repository 测试。
- 学期课程采用本地 wall time；课程规则和例外按固定优先级计算，不自动改写任务计划。
- 自动活动感知保持 opt-in、默认关闭。没有应用名称、窗口标题、按键内容、屏幕、剪贴板或活动历史采集；不将活动状态保存到数据库。
- Provider 网络只发生在用户设置凭据、检查发送摘要并主动发送之后。没有使用真实凭据或向 Provider 发送真实消息。
- 启动测试使用独立临时 `LOCALAPPDATA`，避免触碰用户真实配置目录或与运行中的实例锁冲突。
- 一次 auto-review 曾拒绝临时移除 SQLite 单例约束的测试改动；最终保留并验证 schema 不变量，没有削弱实现。

## Stage 3–6 结束时的状态（2026-10-16）

- Stage 3–6 已有各自的独立 feature commit；当前分支为 `codex/stage3-proactive-engine`，没有合并到 `main`。
- 未 push。此前 push 因 `SEC_E_NO_CREDENTIALS` 失败；当前虽配置了 `origin`，仍没有可用 Git 凭据，因此没有重试。
- 仓库中没有 `OPEN_QUESTIONS.md`，目前没有等待产品 owner 选择的重大架构分叉。
- Stage 5 的真实 Provider 流程仍需要用户配置自己的凭据并主动选择测试内容；Stage 6 的真实 Windows idle 转换尚未在用户机器上体验。
- 下一阶段是 roadmap 中的 Stage 7：基础语音、Windows 打包与首版验收。它需要用户体验按键说话、麦克风状态/隐私行为、打断语音以及 Windows 包的真实启动；若采用云端 STT/TTS，还需要明确 Provider 和发送数据。因此在用户手动体验 Stage 3–6 之前不继续实现 Stage 7。

## 醒来后建议先体验

1. 在 Windows 上启动应用，确认桌宠、任务和本地对话仍可正常使用。
2. 设置一个带计划时间和优先级的任务，验证提醒卡的“现在做 / 稍后 / 延长 / 今天跳过 / 已完成”操作；重点看延长到期后是否重新评估。
3. 打开提醒设置，确认活动感知默认关闭；若愿意，可启用后体验 `focused`/`idle` 变化，再暂停确认它回到 `unknown`。
4. 确认未配置 Provider 时本地聊天可保存，且不会因打开聊天或设置而发出网络请求。若之后配置 Provider，先核对发送摘要再发送自己选择的测试消息。
5. 检查默认隐私边界：应用不会显示或保存你正在使用的程序、窗口标题、键盘内容或屏幕内容。

## 2026-10-17 后续进展

用户随后授权开始 Stage 7。已完成 Stage 7A 的 provider-neutral 本地语音会话基础和独立审查修复（`8cc74fa`、`4f933ea`），真实设备与语音引擎仍未接入，按钮保持禁用。

Stage 7B 已提交 Windows standalone 配置、独立构建 staging、preflight 和依赖许可清单（`9355167`）。当前缺少 MSVC 与部署依赖，尚未执行部署 dry-run/编译或生成 exe，实际打包及人工启动验收仍未完成。

2026-10-18 已完成打包审查修复（`0636c25`），最新全量自动回归 430 项通过。现已存在 `OPEN_QUESTIONS.md`，待选择本地离线 STT/TTS 方案；云端音频不在当前批准范围。没有 push/merge。详细文件、验证、架构决策和推荐体验项见 [Stage 7 交接报告](stage7-report-2026-10-17.md)。

用户随后确认采用离线模型。Stage 7C 已增加本地 Whisper 识别（`cdbb7ec`、`22eb195`），实际公开英文样例的断网 CPU 推理通过，最新全套 470 项通过；离线方向问题已关闭。中文效果、麦克风、朗读及实际打包仍待完成；中文测试资源下载暂因审批服务额度耗尽而未执行。完整后续状态已追加到 Stage 7 交接报告。

2026-10-19 继续：中文公开样本下载已恢复，真实断网推理运行成功但出现错字，未通过中文质量验收（`c9e2c02`）。Stage 7D 增加最多 60 秒的可选 Qt 麦克风采集适配器及 25 项假设备测试；独立审查的两处失败回调重入问题已修复。录音 UI、工作线程桥接、本地 TTS 与实际打包仍未完成。未启用真实麦克风、未上传音频、未 push/merge。详细证据及最终提交/测试数量见 [Stage 7 交接报告](stage7-report-2026-10-17.md) 和 Stage 7D execution record。

2026-10-20 继续：Stage 7E 增加显式 opt-in 录音 UI 与工作线程桥接，停止/释放麦克风在 Qt 主线程，STT 在后台。权限晚到、取消/隐藏后迟到结果、草稿覆盖及通知回调重入均有假设备回归；真实硬件与中文效果仍待人工验收。可选原生 Qt 语音模块现已安装并完成无设备访问的导入/启动核对。未采集真实音频、未自动发送文字、未 push/merge。启动步骤、剩余限制和最终提交/测试结果见 README、Stage 7 交接报告及 Stage 7E execution record。

## 2026-10-20：Stage 7F 离线合成后端

增加 Qt-free SpeechSynthesizer、本地 Kokoro 适配器和静默短生命周期子进程。文本不进入命令参数或错误日志；取消/超时终止并回收进程。输入最多 200 字符，返回最多 60 秒 PCM；不接设备、不自动朗读、不联网下载。模型目录及输出协议均有确定性测试。

新增 50 项测试，全量 582 项通过（10.04 秒），compileall / pip check / diff check 通过。固定公开中文句子真实本地合成得到 3.407 秒音频，含模型加载耗时 5.255 秒；未播放声音，因此不宣称听感验收通过。365 个忽略目录中的模型文件已核验来源哈希。

独立审查首次因模型账户额度失败；替代审查发现父进程 stdout 无流式上限，已通过 RED/GREEN 修复。最终 583 项测试通过（11.05 秒），真实固定句子合成再次通过；未进行听感或设备验收。当前分支 codex/stage3-proactive-engine，未 push / merge。下一阶段为显式朗读交互及 Qt 播放适配器，真实录音/中文识别/朗读听感、MSVC 编译打包仍待验收。

Stage 7F 独立实现提交：`bd51dc88cdc91e6a09eae314295db8373a3bfa0e`。离线生成 PCM 完成；朗读交互仍未实现。

## 2026-10-20：合并既有阶段并完成 Stage 7G 显式朗读

按用户“push合并继续推进”授权，开发分支及42个阶段提交正常推送，GitHub main 快进到 a4eb9fb。Git 未继承 Windows 系统代理造成443超时；仅在子进程环境使用现有系统代理后成功，未改全局配置或凭据。GitHub连接器创建PR返回403，因此没有PR；已认证Git正常完成快进。原主工作区及其未跟踪计划原样保留。

新分支 codex/stage7g-explicit-playback 完成单次合成任务所有权、Qt线程内存播放、独立SpeechController、AI_COMPANION_TTS_MODEL_DIR显式配置及聊天入口。点击后才朗读最新成功回复，长文本提前标明“朗读前200字”；不自动播放、不改对话、不读草稿。停止/隐藏窗口取消，按住录音前先停止输出；停止失败不启用麦克风。启动不加载模型或发现设备。

独立审查发现对象直接销毁时的活动输出/PCM清理缺口，已用3项RED/GREEN回归修复；没有其他Critical/Important/Minor。新增52项，全量635项测试通过（9.63秒），compileall / pip check / diff check通过。已配置源码应用在临时profile中启动/退出通过，禁止了模型/设备入口，真实凭据使用假实现；未触碰私人profile或设备。

尚待真实Windows验收：朗读听感、设备格式/中断、录音权限及中文识别质量、停止后再录音的回声体验。MSVC编译和独立可执行helper仍未完成；不宣称exe可用。模型文件、音频、数据库和secret未纳入提交。推荐首先体验：默认关闭启动；显式配置后点击朗读/停止；长回复前200字提示；朗读时按住录音；合成或播放时隐藏再打开窗口不会自动重播。下一步优先做这些体验验收，再决定识别效果、设备兼容与打包的优化。

Stage 7G 实现提交 `6f4434fd7f8c70303a010d409ce7951f8f069264` 已正常推送到开发分支并快进合并 GitHub main。当前开发分支 `codex/stage7g-explicit-playback`；保留所有历史，无 force push、无 PR（连接器权限不足）、无工作区删除。最终 635 项自动测试通过；未进行实际硬件验收。

## 2026-10-20：真实耳机播放兼容修复与听感反馈

用户指定耳机进行真实输出测试。首次本地公开句子测试发现 PySide6 6.11.2 的原生QAudio::State参数转换失败，导致正常结束回调缺失；看门狗仍能停止并清理。改用零参数回调：输出在身份检查后查询sink.state()，输入错误回调仅查source.error()，避免同类参数转换。无依赖升级或权限边界变化。

2项无设备回归已先RED后GREEN；完整637项通过（11.06秒），compileall/pipcheck/diffcheck通过。真实输出复测验证自然结束、750毫秒主动停止及两段PCM清理成功，未启用麦克风、未保存音频。用户确认听到，但认为语调/音色生硬；输出链路确认，音质验收未通过。下一步先比较现有离线中文音色，再考虑是否需要其他模型，不宣称当前声音已自然可用。设备名称/ID和音频不进入提交。

复核补充：独立审查无兼容修复代码问题，但适配器组合测试暴露原生Qt对象清理时序崩溃，已复现并清理测试独有回调引用环、在测试边界处理延迟删除；没有关闭GC或删除断言。相同顺序正常GC下多次通过，独立复验42项通过；最终全量637项通过（10.51秒）。三种现有中文女声试听均被评价为仍生硬，保持音质未验收。替代模型只查了官方元数据，尚未安装或下载。
