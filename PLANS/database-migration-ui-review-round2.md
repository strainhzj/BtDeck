# 数据库迁移 UI v3：第二轮计划审查

> **日期**：2026-10-28
> **审查对象**：`PLANS/database-migration-ui.md` v3；源码基线 `dev@8d67da3`，以本次工作树实际文件为准。
> **结论**：**REQUEST_CHANGES（需修改后执行）**。合并去重后 **4 P0 / 9 P1 / 5 P2**；本文所有问题均为 OPEN，不把建议登记为已修复。
> **冻结需求**：SQLite ↔ PostgreSQL 双向页面迁移；**A 指引 + B 一键切换均保留**；不创建 PG 服务、支持 Docker 同堆栈；**安卓不支持 PostgreSQL**。
> **历史说明**：本文保留对 v3 的原始结论及 OPEN 状态；2026-10-28 已按用户要求修订 [v4 主计划](./database-migration-ui.md)，设计处置映射与定向复核见其 §13/§16。设计条款补齐不代表实现或测试通过。

## 1. 方法与边界

- `plan-reviewer`：B 轨配置、启动校验、契约演进及反向迁移审查。
- `acceptance-reviewer-gpt`：停写屏障、启动重入、线程取消、崩溃一致性及清理安全专项。原 `reliability-reviewer` 遇供应商 429 限额后由此代理替代，并已返回完整报告。
- 主会话复核了关键源码：`core/migration.py` 的增量升级；`pg_baseline.py` 的标记删除；删除任务终态后的通知写入；GET 能力查询的 INSERT；`lifecycle.py` 的启动写入顺序；`init_config_file` 直接覆盖 YAML；`DATABASE_PATH` 的 env 优先；Docker `exec uvicorn` 与 restart 声明。
- **本轮仅静态审查**：未运行 pytest、构建、故障注入或真实部署。下文测试均为应补验收，不是已通过的结果。
- 本文的计划行号基于审查时 v3；后续修订可能漂移，以节名与源码实测为准。

## 2. P0：实施前必须闭合的设计阻断

### P0-1 每次启动要求版本等于 head，会阻断正常升级

**计划证据**：§3-D2B / §4.5（v3 L96、L189）规定 `版本≠head → fail-fast`。

**源码证据**：`backend/app/core/migration.py:198-215` 已支持合法旧版本执行 `command.upgrade(cfg, "head")`。

**轨迹**：B 激活目标版本 H → 升级应用到新增迁移 X → 新校验链在 Alembic 前拒绝 H≠X → 容器反复拒启。清记录又可能回到旧 env 源库，不能作为常规升级办法。

**所需修订**：区分“首次激活严格核验”和“已激活库日常启动”。首次激活核对切换时 revision/凭据；已激活库允许当前迁移链的合法祖先交给 Alembic 升级，未知/未来版本与显式降级按明确兼容策略处理，不能简单以 `!=head` 拒启。

**验收**：带 active 记录的 H 库升级到 X 成功且数据保留；首次激活凭据不符拒启；未知版本不静默回落到其他库。

### P0-2 migration_id 没有目标侧持久凭据可核对

**计划证据**：§3-D2B / §4.5 承诺启动检查 migration_id。

**源码证据**：`backend/scripts/migrate_sqlite_to_pg.py:673-676` finalize 调用清标记；`backend/app/core/pg_baseline.py:129-133` 实际 DROP `_btdeck_import_state`。当前没有成功迁移的持久 receipt。

**轨迹**：迁移完成删除标记 → B 写 active → 重启时找不到目标侧 migration_id。若跳过检查，连错同 revision 的数据库也无法识别。

**所需修订**：区分“未完成导入标记”和“完成/激活凭据”；设计目标数据库身份、独立 attempt/ownership nonce、迁移 receipt、首次激活确认。新增持久表/辅助对象须明确 Alembic 或辅助表契约，及正向 precheck 表集合、基线、对账的包含/排除规则，不能新增表后又被现有全表校验误拒绝。

**验收**：同 head 错误目标、篡改 ID、缺 receipt 均拒绝激活；完成凭据在清导入标记后仍可核验；激活后正常升级不受阻。

### P0-3 bool gate 与“无活跃任务”检查不构成静止屏障

**计划证据**：D1-1 / D1-2（v3 L48-64）、start 端点（L170）。

**源码证据**：
- `backend/app/services/async_deletion_executor.py:140-180` 先登记终态，再在独立 session 中发完成通知；`deletion_task_manager.py:248-254` 在终态释放活动标识。
- `backend/app/services/sync_db_write.py:270-292` 按批持锁、批间让行，并非覆盖整个应用操作的冻结锁。
- `backend/app/mcp/server.py:183-228` 已准入请求仍会继续 await handler，拒绝新请求不会排空旧请求。

**轨迹**：请求通过 gate 后尚未登记任务 → start 查到无活跃任务并快照 → 原请求继续提交；或删除已标终态但其通知在快照后提交。快照与目标本身可对账成功，仍会丢掉快照后提交。

**所需修订**：定义 `PREPARING → DRAINING → FROZEN`。关闭新准入与登记共用原子临界区；排空所有获准 HTTP/MCP、后台子任务、线程、事务、通知/审计/finally 收尾后才快照。保留“遇活跃重任务拒绝”策略，但必须先封住新准入，且安全撤销准备态。

**验收**：在准入/任务登记/最后业务提交/完成通知之间设置确定性屏障；未排空前禁止进入 FROZEN，覆盖真实 MCP 挂载入口。

### P0-4 B 轨跨文件切换没有持久提交与激活确认协议

**计划证据**：§3-D2B 流程 2-5（v3 L101-104）：归档三文件、移动产物、写 active、退出、重启核验及清维护 flag，均为独立操作。

**源码证据**：`backend/btdeck_startup.sh:118-146` exec uvicorn、`docker-compose.yml:78` restart 声明支持进程拉起，但不会恢复应用自己的多文件事务。

**轨迹**：归档一部分或产物落位后，active 写入/rename 失败或掉电；重启无法凭只有 ID/阶段/时间的 flag 唯一确定各文件属于哪个切换代次、该续做还是回滚。单个 YAML 的 rename 原子性不等于整体事务原子性。

**所需修订**：扩展持久 manifest，至少定义 `PREPARED → COMMITTED → ACTIVATED_ACK`，保存源/目标身份、配置代次、产物摘要、精确归档路径及每步结果。文件与父目录持久化，任何失败保持维护。新进程在普通写入前核身份并持久确认后才解除维护；旧进程不得提前解除。

**验收**：每个文件操作、配置提交、退出、验证、ACK、删 flag 前后注入中断；结果只能是明确旧库、明确新库或 fail-closed，禁止静默选库/重复归档覆盖。

## 3. P1：设计须补条款，实施验收必须覆盖

### P1-1 GET、审计与鉴权仍可写源库；令牌过期后控制面失联

- **证据**：`api/endpoints/downloader_capabilities.py:92-176` 的 GET 可 `create_if_not_exists=True`；`services/downloader_capabilities_manager.py:193-195` 提交 INSERT。`api/endpoints/mcp_settings.py:248-276` 的 GET 写审计；`services/audit_service.py:133-135` 直接提交。`api/endpoints/login.py:49-134、178-228` 登录/刷新也写库。
- **轨迹**：维护只挡非安全 HTTP 方法，GET 仍落库；database 前缀被豁免但控制审计改变快照后源库。反过来，全挡登录/refresh 后长迁移令牌过期，管理员无法取消/切换。
- **修订**：按实际副作用分类并禁止隐式创建/同步；提供不写源库的维护鉴权路径；控制审计写受保护的本地恢复日志，激活/放弃后按归属归档，不能直接丢审计或简单豁免现有登录。
- **验收**：GET 隐式创建与审计均不改变源库；令牌过期、新浏览器重新认证仍可安全管理迁移。

### P1-2 flag 重入必须早于启动 seed/迁移/恢复写入

- **证据**：`startup/lifecycle.py:413-535` 顺序为 init_config → migrate_database → init_db → 密码加密回写 → orphan 修复 → cron 状态更新；`database.py:308、390、434` 存在 seed 提交。`downloader/initialization.py:729-749、837-840` 启动子任务的 TaskLogger 经 `tasks/logger.py:50-67` 也可提交。
- **轨迹**：维护崩溃重启，仅暂停末尾后台循环仍会先改库。
- **修订**：独立维护启动分支，在任何源库写入前读/验恢复状态；重入时只读身份/schema，禁止普通迁移、seed、密码回写、恢复更新及普通启动日志落库。损坏状态 fail-closed。
- **验收**：真实 lifespan 放入缺 seed、running 状态、明文密码等哨兵，维护重启后内容不变、普通任务不启动。

### P1-3 重启恢复材料、取消确认与结果有效期不完整

- **证据**：D1-3 flag 只有 ID/阶段/时间，D4 密码仅内存，却承诺自动连接目标恢复；D1-2、cancel/leave 会解除停写。既有 `cron_executor.py:958-964、1094-1096` 明确取消等待后底层线程仍可能继续。
- **轨迹**：重启丢目标地址/凭据；取消协程后线程继续提交，已允许清理或新任务；leave 后源继续变化，旧 finalized 结果仍可能被误用于切换。
- **修订**：持久不含密码的目标描述，缺凭据进入 `NEEDS_CREDENTIALS`；`CANCELLING → CANCELLED` 需 worker 确认停止、事务结束与 checkpoint/连接收尾屏障；带 attempt/维护 epoch，解除停写即撤销旧切换资格。
- **验收**：丢凭据重启、阻塞线程取消、旧回调晚到、源同主键同计数 UPDATE、旧页面操作新 attempt 均有确定拒绝/恢复结果。保留现有 CLI source_digest 不匹配拒恢复守卫。

### P1-4 连接记录和文件发布须支持真实路径、TLS 与文件系统边界

- **证据**：`core/config.py:477-483` 支持 env `DATABASE_PATH`；计划记录没有 `sqlite_path` / `ssl_root_cert`，反向固定 CONFIG_DIR 落位；`database.py:115-139` 开启 WAL。
- **轨迹**：自定义路径重启仍读旧库；verify-ca 缺 CA；跨挂载 rename EXDEV、磁盘满、产物 WAL 未 checkpoint 即发布主文件。
- **修订**：完整目标参数与解析优先级（含 SQLite 绝对路径/CA）；在最终目录同 filesystem staging 或先复制校验并持久化；归档/落位纳入 manifest，关闭句柄并核 WAL；限制 UI 文件名，检测链接、同 inode、同源目标误指，不破坏合法自定义路径。
- **验收**：自定义 DATABASE_PATH、verify-ca、EXDEV、ENOSPC、rename 失败、WAL 非空、路径别名；失败不提交 active、不解除维护。1.5×空间估算仅为启发式，不能替代 ENOSPC 恢复。

### P1-5 config.yaml 其他写入者可破坏 active 原子性

- **证据**：`database.py:449-535` 的 `init_config_file` 每次启动会直接 `open(...,"w")` 覆盖 YAML；读取失败还会尝试重建默认配置。正常 RMW 会保留未知节，但写窗口不具备持久原子性。
- **轨迹**：active 原子写成功，下一次启动直接覆盖期间掉电或写满 → 记录丢失/配置损坏 → 误回 env 或进入破坏性的默认配置重建。
- **修订**：统一所有相关 YAML 写入的互斥、合并、原子替换和持久化；对已激活环境的损坏/缺失拒绝自动默认重建。若改为独立活跃记录文件，须作为明确设计修订记录，不默认为已获本轮验证。
- **验收**：在所有配置写窗口注入失败/并发更新，记录与安全密钥不丢、未知节保留，绝不静默回 env。

### P1-6 A+B 共存与 clear 会导向过时源库

- **证据**：§3-D2B 记录优先于 env；clear 仅“维护态或无迁移任务”约束；A 指引未说明已有 active 的处理。
- **轨迹**：PG 已运行数周，清记录后重启 env=sqlite 读旧 app.db；A 用户改 env 而旧 active 仍生效，实际上没切换。
- **修订**：clear 视为有风险的切换准备操作，展示 env 解析出的目标身份/版本/路径及数据过时风险，维护态下校验与二次确认；A 指引按当前 active 状态生成安全的配置交接步骤，不得只给通用改 env 命令。
- **验收**：非维护/无确认拒绝；已有 active 时 A 步骤不被旧记录覆盖；过时目标风险清晰提示，不能宣称无损。

### P1-7 discard-target 缺目标所有权边界

- **证据**：计划 §4.2-7 允许恢复失败后清理 PG；`pg_baseline.py:77-125` 标记仅有来源摘要/工具/checkpoint，migration_id 又来自 source_digest（`migrate_sqlite_to_pg.py:566-567`），不证明目标归本次操作所有。
- **轨迹**：连错带标记的另一个 PG，或目标已有外部新增表/行，用户确认清理会误删非本次数据。
- **修订**：独立校验部署/attempt nonce、数据库身份与对象 manifest，排除当前源库，防检查后替换竞态；仅清理明确归属对象，未知对象/数据则拒绝。禁止 `DROP SCHEMA CASCADE`。清理失败不是扩大删除范围的授权。
- **验收**：外部表/行、复制标记、错误数据库均拒绝；合法本次目标仍可放弃重建。

### P1-8 反向预检缺非有限浮点

- **证据**：§4.6 未列 Float NaN/Infinity；正向 `check_source_schema_and_values` 已用 `math.isfinite` 校验（`migrate_sqlite_to_pg.py`）。PG double 可表示非有限数。
- **轨迹**：PG 脏值反向绑定 SQLite 时发生拒绝或 NaN→NULL 等语义改变，直到 verify 才难定位地失败。
- **修订**：预检逐 Float 列扫描 NaN/Infinity，按表/列/记录定位报告并在建目标前拒绝。
- **验收**：真 PG 非有限数夹具在 precheck 阶段报错且不创建目标。具体驱动行为需实验，不将其静态推断当成已测事实。

### P1-9 安卓“无 PostgreSQL”须在引导层强制

- **证据**：D6 仅说明端点/前端守卫，B 在 `Settings.__init__` 就读 active 决定引擎；`core/platform_capabilities.py` 已有 android 识别路径。
- **轨迹**：复制服务端 config 到 Android，PG active 在页面守卫之前被消费，可能尝试加载 PG 驱动/连接 PG。
- **修订**：在读取配置/创建引擎前拒绝 Android 的 PG env 或 active；不尝试 PG、不静默改用新 SQLite 空库。安卓 UI 作为第二层隐藏，而非唯一防线。
- **验收**：Android+PG env、Android+PG active 在引导层明确拒绝且零 PG 连接；Android 正常 SQLite 不回归。

## 4. P2：建议与验证细化

1. **临时引擎方言断言**：`pg_baseline.validate_pg_server`（L47-49）对非 PG 会跳过；参数化后必须显式防错引擎，测试将 SQLite 传给 PG 初始化会在任何 DDL 前拒绝。
2. **所有配置消费者同源**：shell `detect_backend_type` / `core/startup_guard.resolve_database_url` 仍读 env。当前两方言都单 worker，暂未证明引发功能错误；应明确外层 worker 检查与最终有效配置的职责，状态/日志不能误报运行库。
3. **重启响应时序**：当前 Docker `exec uvicorn` 和 restart 声明为 B 提供可行挂点，但须在响应 flush/持久提交后调度退出，非 Docker 或无已知托管能力则提示手动重启；真实行为留 W5 验证。
4. **标识算法版本**：明确双向 attempt ID、source_digest 算法版本与 `sqlite-/pg-` 方向前缀，不能用可重复来源摘要代替独立 ownership nonce。
5. **零写入测试 oracle**：表计数不能发现 UPDATE；SQLite data_version 必须使用同一持续连接比较，现有 NullPool 默认连接不可直接作跨调用数值比较（`database.py:104-106、156-160`）。补 DML/提交观测和内容对照、PG 独立探针，并用同主键同计数 UPDATE 作阳性对照。

## 5. 第一轮问题复核

- env.py 目标 URL 覆盖、SQLite 未完成导入拒启、反向内容摘要、MCP 整体停用等**已写入设计要求**，但尚无实现/测试证据，不能记为代码层关闭。
- 第一轮“补全写面清单”只解决枚举问题，未解决准入排空与 GET/审计副作用；**停写保证仍 OPEN**（P0-3 / P1-1 / P1-2）。
- flag 持久化只写了存在性，没有启动早期分支与激活 ACK；**恢复仍 OPEN**（P0-4 / P1-2 / P1-3）。
- WAL 三件套归档有方案条款，但整体发布未定义故障状态；**崩溃一致性仍 OPEN**（P0-4 / P1-4）。
- B 轨是第一轮审查后的新增设计，升级、receipt、clear、配置多写者等本轮新问题必须显式修订，不能用“实施时测试兜底”替代设计不变量。

## 6. 下一版所需最小交付物

不改变用户已确认的 A+B 与安卓限制，下一版至少补齐：

1. 停写准入/排空/冻结状态机，以及维护期只读启动、鉴权与审计路径。
2. attempt/数据库身份/完成 receipt 与首次激活 ACK，及正常 Alembic 升级规则。
3. 跨文件事务 manifest、逐步恢复矩阵和故障注入验收表。
4. 全量有效配置（路径/TLS/优先级）及 A↔B 交接/清记录风险约束。
5. 带凭据重输的中断恢复、线程停止确认、epoch 作废与目标所有权清理约束。
6. 安卓引导层拒 PG 与 PG→SQLite 非有限数预检。

**本轮到此仅给出审查与修改要求；不启动实现，不把报告建议自动认定为修复完成。**
