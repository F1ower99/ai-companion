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
