# Stage 7 自主开发交接报告

日期：2026-10-17（北京时间）
最终验证更新：2026-10-18（北京时间）
分支：`codex/stage3-proactive-engine`
起点：Stage 1–6 已实现，Stage 7 本地语音/打包规格已提交；原回归套件为 370 项。

## 已交付

### Stage 7A：本地语音会话基础

- 新增 Qt-free `VoiceSession`，用 capture/STT/TTS Protocol 隔离设备和引擎；构造时不查询设备，不请求麦克风权限。
- PCM 仅在内存中、校验完整帧及 60 秒上限；完成、失败、取消后清理。保留 memoryview 时原缓冲区内容也会被清空覆盖；不承诺 Python/OS 级物理内存零化。
- 提供明确的录音开始/停止、转写、取消、朗读、中断和关闭操作；远程或不明确的 local_only provider 在构造时被拒绝。
- 取消使迟到转写无效；录音转换先预留所有权，TTS 工作与停止清理分别跟踪，避免旧操作影响新操作。
- Qt 展示禁用的语音按钮和缺少本地引擎说明；转写只能放入空的可编辑草稿，保护已有输入且不会自动发送或写入会话。
- 新增 45 项自动测试。独立 reviewer 发现两个 Important 并发缺陷，已先复现失败、再修复并完整回归；无剩余 Minor。
- 功能提交：`8cc74fa`；审查修复与记录：`4f933ea`。

本阶段完成的是可测试的语音基础。尚无真实本地 STT/TTS、Qt 音频适配器或实时录音 UI；自动 60 秒停录是未来设备适配器的义务，当前只校验交接的 PCM。不能据此宣称语音产品已完成。

### Stage 7B：Windows 打包基线

- 新增 `pysidedeploy.spec`、PowerShell 一键入口和 Python preflight，检查虚拟环境、Qt/Nuitka、MSVC 工具。
- 每次构建使用独立源代码 staging 和独立输出目录，保留既有产物及诊断文件，不递归清理原项目。
- 通过已安装 Qt 6.11.2 源码确认空 packages 列表跳过安装；构建不会自动安装依赖或编译器。
- 输出预期为 `dist/build-<id>/AICompanion.dist/app.exe`，除退出码外也检查实际 exe，防止上游吞掉编译错误产生假成功。
- 新增依赖许可元数据清单生成器和 `THIRD_PARTY_NOTICES.md`，仅记录已安装 runtime 依赖的真实版本/声明，不猜测缺失许可。
- 新增 15 项工具测试；基线提交：`9355167`。独立审查发现一个 Important 元数据校验缺口，七项新增测试先复现失败，再修复包名/版本/SPDX 校验及未知许可证标记，提交 `0636c25`。无剩余 Critical/Important/Minor 问题。

真实 preflight 因缺少 `cl`、`dumpbin`、Nuitka 4.1.1、ordered-set 和 zstandard 正确终止。未安装系统工具，未执行部署 dry-run/实际编译，未生成 exe，未进行打包启动验收。Stage 7B 的实际构建验收仍未完成。

## 验证

- 最新完整 pytest：430 项通过，`QT_QPA_PLATFORM=offscreen`、禁用 pytest cache（2026-10-18）。
- `compileall` 通过，字节码写到测试临时目录；`pip check` 无依赖冲突；Git whitespace 检查通过。
- 测试使用 fake 语音 provider、临时构建目录、临时数据目录；没有真实录音/播放、私人 SQLite、Credential Manager 或云端请求。
- Git 没有 push、merge、force push 或发布二进制。之前凭据不可用的远端状态未被绕过。

## 主要修改文件

- `src/companion/domain/voice.py`、`ports/voice.py`、`application/voice_session.py`。
- `src/companion/desktop/chat_window.py` 及 domain/application/desktop 的语音测试。
- `scripts/build_windows.ps1`、`windows_build.py`、`write_third_party_notices.py`、`pysidedeploy.spec`、`THIRD_PARTY_NOTICES.md`、`tests/tooling/`。
- `README.md`、roadmap、Stage 7A/7B specs/plans/task records、`OPEN_QUESTIONS.md`。

## 决策与边界

- 保留同步、无 Qt 的服务接口，由后续 UI worker 安排阻塞调用；当前仅交付禁用的最新回复朗读入口。代价：真实音频集成仍需要状态与 worker wiring。
- 被中断的朗读 worker 返回前不允许替代朗读，但成功停止 TTS 后可录音。代价：不响应取消的 provider 会延迟下一次朗读。
- 使用当前 Essentials 自带部署工具；Qt 6.11 的安装/清理行为通过空 package list 与全新 staging 隔离。代价：保留更多构建文件，Qt 升级要重新检查。
- 技能 scratch 路径拒绝写入，使用已提交 task record 记录进展。代价：手动维护进度。
- 保留现有分支与 worktree，未合并 main。

## OPEN_QUESTIONS 与停止原因

`OPEN_QUESTIONS.md` 仍待决定第一个本地语音栈：Windows 自带语音能力或随应用分发的离线模型。语言支持、安装体积与硬件需求会显著不同，未自行选择。云端音频不在当前许可范围。

下一步先选择本地引擎并准备 MSVC 环境，然后完成真实打包、设备适配器和用户体验测试。没有继续虚构新阶段或把未测试的语音/发布能力标记完成。

## 醒来后建议检查

1. 源码启动桌宠和聊天，确认两个语音按钮禁用且原因明确。
2. 检查今日任务、提醒卡及延长后重新评估的原有闭环。
3. 确认打开聊天不会启动麦克风，也不会因语音入口自动发送文字。
4. 阅读 `OPEN_QUESTIONS.md`，确定首个本地语音引擎方向。
5. 阅读 README 的构建与临时 profile 步骤。临时 LOCALAPPDATA 只隔离 SQLite，不隔离 Windows Credential Manager；涉及凭据的人工验收使用单独 Windows 测试账号。

## 2026-10-18 离线模型后续

用户已选择离线模型，原本的 Windows 自带语音/离线模型产品分叉已关闭。Stage 7C 增加真实本地 faster-whisper CPU/int8 adapter 和受限 WAV 验证工具（`cdbb7ec`），独立审查的取消/网络模型路径问题已修复（`22eb195`），全量 470 项测试通过。

固定版本 Whisper base 已下载并校验发布方哈希；真实 11 秒公开英文样例和 CLI 测试均通过，推理时 Python 网络连接被阻断。中文质量仍未验证：下载中文公开样例的操作因自动审批服务额度耗尽而未执行，属于审核服务失败而非安全拒绝；未绕过审批。详细来源、版本、测量及限制见 [离线识别验证记录](offline-stt-assets-2026-10-18.md)。

目前首版 MVP 约 70% 是基于可用功能/验收剩余量的工程估算，不是按阶段数平分。剩余主要是中文真实体验、麦克风/Qt 语音交互、本地 TTS、Windows 编译打包及人工验收。没有宣称完整语音产品或 exe 已完成。审查保留一个 Minor：开发用 WAV 工具的奇数字节尾部校验可继续加强。

## 2026-10-19 后续验证与采集适配器

- 中文公开音频已下载并校验哈希；关闭 Python 网络连接后，5.616 秒样本在 0.949 秒完成本地识别。输出包含实质性错字，因此只确认执行成功，未通过中文质量验收。证据提交 `c9e2c02`。
- Stage 7D 规格/计划提交 `790e161`，实现可选 Qt 采集适配器：启动前检查权限、只支持 16kHz 单声道 PCM16、内存最多 60 秒、超时释放设备、取消清理、旧回调隔离及线程归属检查。
- 这是采集层，不是完整语音交互。聊天录音按钮继续禁用；还需要将 UI 线程的设备释放与工作线程的识别分离。未启动真实麦克风或扬声器。
- 已读取本地 QtMultimedia 官方类型签名核对 API。可选 168 MB Addons 下载六分钟未完成，已停止本任务下载进程，未宣称原生运行时安装成功。
- 新增 25 项假设备测试；独立审查提出的两处失败回调重入问题已用三项 RED/GREEN 回归修复。最终回归、提交及详细决策见 Stage 7D execution record。
- 保留当前 `codex/stage3-proactive-engine` 分支，未 push、未 merge、未产生 exe。下一步仍为线程安全的录音/识别 UI 集成、中文质量改进、本地 TTS 和打包/人工验收。

Stage 7D 最终实现提交：`7ac7b341d102ca3e591cbe5bf0b331ad781e0c4d`。审查修复后完整回归 **495 项通过**，compileall（src/scripts/tests）、pip check 和 Git staged diff check 均通过；工作区干净后继续保留开发分支。无待定产品方向问题。

建议先检查：1）启动/打开聊天不访问麦克风；2）录音与朗读仍禁用且说明准确；3）今日任务与提醒延长后重评估未退化；4）已有输入草稿不会被语音结果覆盖；5）阅读中文真实样本错字记录，不将离线运行成功理解为识别质量合格。真实录音需要后续显式操作界面和设备验收，当前不能直接体验端到端语音。

## 2026-10-20：Stage 7E 录音 UI 与后台识别

规格/计划提交 `cf47bd4`，本次实现将 Qt 主线程的麦克风停止/释放与后台 STT 分离。VoiceSession 保留同步兼容接口，新增 prepare_transcription 和单次转写任务；正在解码的 PCM 只由工作线程清理，取消会阻止迟到结果。待执行任务取消后立即清理。

聊天增加按住录音、松开识别、取消与状态提示。权限响应晚于松手/隐藏窗口时不会开始录音；达到上限仅提交一次。结果只进入空的可编辑草稿，手动输入保留，不自动发消息或执行任务动作。关闭/隐藏聊天取消语音；退出应用永久关闭该控制器。

默认关闭，只有显式设置绝对本地 `AI_COMPANION_STT_MODEL_DIR` 且可选 voice/stt 依赖可用时才启用入口；README 记录启动步骤。目录元数据在用户按下后、请求权限之前检查。没有新增数据库字段、音频文件、后台监听或云端音频。

官方 PyPI 的 PySide6-Addons 6.11.2 安装及原生模块导入成功。独立临时 SQLite profile 的已配置应用启动/退出检查通过，测试中禁止了权限 API、设备发现与模型预检，确认启动未触发它们。独立复审两项 Important 通过四项 RED/GREEN 回归修复；无 Critical 或新 Minor。

尚未完成：真实 Windows 麦克风/权限/设备中断体验、中文质量改善、本地 TTS、编译打包。先完成录音的人机体验验证再扩展朗读；本次没有擅自采集私人音频。原 Stage 7C WAV 工具奇数尾字节 Minor 仍留在记录中。完整最终测试数和提交见下方后续记录及 Stage 7E execution record。

Stage 7E 最终提交：`b3b6ef053019d90effd3e853fd2822f3944c85af`。审查修复后 **532 项测试通过**（本阶段新增 37 项），compileall / pip check / staged diff check 通过。当前分支 `codex/stage3-proactive-engine`，未 push、未 merge；没有剩余的本阶段 Important/Critical 问题。

建议接下来人工体验 5 项：1）不设置语音环境变量启动时入口禁用、无权限提示；2）按 README 显式配置模型后，短按/松开与权限允许/拒绝/晚到都符合说明；3）短句识别只进入草稿，编辑后才手动发送；4）识别中继续输入、取消或隐藏窗口不会被迟到结果覆盖；5）原有任务提醒与“延长后重新评估”仍正常。请先评价录音操作和中文效果，再扩展 TTS；当前不宣称真实设备或中文质量已通过验收。

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
