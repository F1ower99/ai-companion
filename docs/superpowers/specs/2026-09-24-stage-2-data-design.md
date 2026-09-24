# 阶段 2 设计：本地目标、任务与记忆

日期：2026-09-24

## 目标与范围

阶段 2 为长期目标、每日任务和五类基础记忆增加本地持久化记录。桌面外壳会提供一个简洁的“今日任务”视图，数据由应用服务提供。SQLite 只属于基础设施实现；领域层和应用层不得导入 Qt 或 sqlite3。

版本 1 的数据库迁移会创建 MVP 路线图指定的七张表：goals、tasks、memories、conversations、messages、settings 和 reminders，并额外创建 schema_migrations 表记录已应用的迁移。conversations、messages、settings 和 reminders 在本阶段只建立存储结构；对应的用户功能留待后续阶段实现。

所有个人记录都留在本机。默认数据库存放在当前用户的 LOCALAPPDATA 目录下的 AICompanion 文件夹中。测试使用临时数据库文件。settings 可以保存普通偏好设置，不得保存模型或服务凭据。本阶段不增加活动监测、云同步、向量嵌入或语义检索。

## 方案比较

1. 只创建 goals、tasks 和 memories，其他表在后续阶段按需增加。这样可以减少暂时未使用的数据库结构。
2. 按已确认的 MVP 路线图，在第一个迁移中创建全部七张表，但本阶段只实现 goals、tasks 和 memories 的存储接口及界面。这样既符合完整路线图，也不会把尚未实现的后续功能误认为已经完成。

用户已选择方案 2，以完整路线图作为本阶段的数据库基础。

## 组件与依赖关系

- 领域模型：不可变的 Goal、Task 和 Memory 数据类；Priority 和 MemoryKind 枚举；MemoryQuery 筛选条件对象。
- 应用服务：TaskService 校验任务创建和进度变更，并通过仓储接口委托数据持久化。
- SQLite 基础设施：连接工厂、按顺序执行的 schema 迁移，以及 goals、tasks、memories 的仓储实现。
- 桌面界面：“今日任务”入口打开任务列表，并提供简单的添加和完成操作。对话框复用时需刷新数据；跨越本地午夜后，日期标签、列表和新任务日期都应切换到当天，同时保留用户当前选择的目标。显式注入的 today 固定为该日期；默认日期由本地时钟驱动。界面只调用 TaskService，不直接执行 SQL，也不承担业务规则。
- 测试：适合的领域和服务测试使用伪仓储；仓储与迁移测试使用临时 SQLite 文件，并通过重新打开连接验证数据。

## 版本 1 数据库结构

所有标识符均为文本 UUID。日期使用 ISO 8601 日历日期格式；时间戳使用 ISO 8601 UTC 字符串。每个数据库连接都必须启用外键。

| 表 | 字段与约束 | 阶段 2 行为 |
|---|---|---|
| goals | id 主键；name 必填；target 可选；priority 为 0–2；active 布尔值；created_at | 添加、读取目标并列出启用中的目标。任务必须关联已有目标。 |
| tasks | id 主键；title 必填；goal_id 外键关联 goals；due_date；planned_minutes 不得为负；completed_units 不得为负；target_units 可选且存在时必须为正数；priority 为 0–2；hard_start、hard_end 可选且 hard_end 不得早于 hard_start；status 为 open 或 completed；created_at | 添加、读取、按日期列出任务，更新进度并标记完成。 |
| memories | id 主键；kind 限定为 profile、preference、behavioral、episodic、conversation；content 必填；source；importance 为 0–5；created_at；expires_at 可选 | 添加、筛选/搜索和删除记忆。默认不返回已过期记忆。 |
| conversations | id 主键；created_at；updated_at | 本阶段只建表。 |
| messages | id 主键；conversation_id 外键关联 conversations，并在会话删除时级联删除；role；content；created_at | 本阶段只建表，不写入聊天记录。 |
| settings | key 主键；value；updated_at | 本阶段只建表，用于非敏感的普通偏好设置。 |
| reminders | id 主键；reason；created_at；cooldown_until；extension_deadline；status | 本阶段只建表，不实现提醒调度器。 |
| schema_migrations | version 主键；applied_at | 记录已成功执行的迁移。 |

迁移必须在事务中执行，并且每次打开数据库时都可以安全调用。已应用的版本不会重复执行。迁移失败时事务回滚，数据库保留之前的结构。后续变更通过新的编号迁移实现，不能修改已经发布的迁移。

## 领域与服务行为

- 优先级顺序为 P0、P1、P2。
- 某日任务按优先级、截止时间、创建时间排序；完全相同时再按 id 排序，确保结果稳定。同一优先级下，没有明确硬截止时间的任务排在有截止时间的任务之后。
- TaskService.add_task 拒绝空白标题、不存在的目标、负数计划时长、无效时间范围和无效完成目标。
- TaskService.complete_units 用于有数量目标的任务，只接受正数增量；拒绝负数或零，并在 target_units 处封顶。仓储必须在数据库端原子递增，避免并发调用丢失进度更新；更新不得影响其他任务的进度。
- TaskService.mark_completed 直接完成无数量目标的任务；若任务有数量目标，则将 completed_units 设为 target_units。
- 记忆搜索支持可选的文本、类别和来源筛选，使用 SQLite 文本匹配；结果按重要性和新近程度排序，并遵守明确的数量上限。这是词面匹配，不是向量语义搜索。
- 仓储写操作使用事务。更新或删除时找不到记录应抛出有明确说明的 not-found 错误；添加时应把重复 id 和无效外键转换为领域层可理解的错误。

## 错误处理与隐私

打开数据库时创建所需的父目录并应用迁移。如果数据库无法打开，应用仍应保持可用，并显示清楚的本地存储错误，而不是让桌面外壳崩溃。SQLite 错误在仓储边界转换为稳定的应用错误；日志不得包含记录正文或秘密。

数据库路径和值不得写入日志。settings 表应拒绝 api_key、token 等保留的凭据类键名；真实凭据留待后续 Windows Credential Manager 适配器处理。本阶段不填充 messages 表。若某个 goal 仍有任务，删除操作应被拒绝；删除 conversation 时，只级联删除其 messages。

## 验收标准

1. 打开全新的临时数据库时，只应用一次版本 1 迁移，并创建七张路线图表及迁移元数据表。
2. 使用第二个连接重新打开数据库后，目标、任务和记忆仍然存在。
3. 任务不得关联不存在的目标；进度变更只影响指定任务；完成量始终处于 0 和 target_units 之间。
4. 某日任务列表按优先级、截止时间和创建顺序稳定排序。
5. 记忆搜索正确遵循类别、来源、文本、数量上限和过期筛选；删除只移除指定记忆。
6. 每个连接都启用外键；迁移失败时事务回滚。
7. “今日任务”界面可以通过 TaskService 添加、显示和完成任务；界面模块不包含 SQL。
8. 现有桌面外壳测试继续通过；新增领域测试和 SQLite 测试通过。

## 暂不实现的内容

Agent 决策、活动监测、提醒与延期调度、聊天持久化行为、模型凭据、语音、校历规则、云同步、向量嵌入和语义记忆检索均不属于阶段 2。
