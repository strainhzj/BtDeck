# 数据库迁移 UI（SQLite ↔ PostgreSQL 双向页面迁移）

> **版本/状态**：v4，2026-10-28 修订完成，**二审问题定向设计复核完成，未实施**（见 §16）。不得把设计处置或本文验收清单登记为功能测试/整体验收通过。
> **冻结决策**：D1/D3/D4/D5 认可；**D2=A 指引+B 一键切换均保留**；**D6 安卓不支持 PostgreSQL**。不创建 PG 服务，支持 Docker 同堆栈。
> **关联**：[v1.0.8 基础](./v1.0.8.md)、[已有 PG 验收](./postgresql-acceptance.md)、[v3 二审原报告](./database-migration-ui-review-round2.md)；现行契约 `backend/docs/postgresql-contract.md`。
> **feature id**：`database-migration-ui-2026-10-28`（仅设计阶段；W0 设计修订/定向复核 done，W1–W6 均 pending）。

## 1. 目标、边界与本轮修订

### 1.1 交付目标

- 设置页填写目标 PostgreSQL 的 host/port/user/password/database/TLS，支持测试连接、预检、进度、取消、恢复及双向全量迁移。
- 当前库为 SQLite 时迁到 PG；当前库为 PG 时生成独立 SQLite 文件。保留主键、软删数据、Text/JSON 字段契约及解密配置；全业务数据逐表对账。
- **A 轨**：页面生成与当前有效配置相符的切换步骤，用户修改宿主 env/重启；已有 B 记录时也可安全交接到 A。
- **B 轨**：用户确认后持久提交有效配置，通过已确认的进程托管能力重启；其他运行方式完成配置提交后提示手动重启，不冒充可自动重启。
- PG 服务/数据库及账号由用户预建；工具只在其空目标库内建应用表，不创建服务、数据库、角色，不需要超级用户权限。Docker 同堆栈填写服务名（例如 `postgres:5432`），测试从 backend 发起；`localhost` 指 backend 容器本身。

### 1.2 硬边界

- 单应用实例、单 worker；暂停涵盖下载器远端操作、后台线程及其通知/审计收尾，不仅是 SQL 提交。
- 不支持边迁移边双写、增量追赶、自动合并两个已有业务库；外部脚本/DBA 直接写源或目标不属于正常支持边界，发现变化必须中止，不能靠一次对账宣称无损。
- 安卓本机服务不加载/连接 PG、不提供迁移入口。安卓伴侣不配置本机 PG；数据库能力由所连接服务端报告，安卓客户端自身不因此获得本机 PG 支持。
- frozen 桌面本期不提供迁移；demo 禁用。普通移动浏览器访问 NAS Web 页面不等于 Android 本机服务，仍按服务端能力矩阵决定。
- 业务数据库写入恢复后，无损回退窗口结束；此后不能通过删配置或回旧文件冒充无损回退。

### 1.3 v3 → v4 的安全收口

1. bool flag 升为**关准入→排空→冻结**屏障；维护时默认拒绝普通业务 API，包括带副作用的 GET。
2. 分离未完成导入标记、完成 receipt、数据库身份、首次激活 ACK；已激活库允许正常 Alembic 增量升级。
3. 持久 manifest 记录跨文件提交，先作出持久决定，再发布配置；新进程确认前绝不恢复普通写入。
4. 保持 D3 独立新文件：B 直接用完整 `sqlite_path` 激活新文件，**不再覆盖/拆分归档旧 app.db/-wal/-shm**。A 同样优先设新文件路径；旧库原位保留即回退留档。若运维必须使用旧文件名，另在应用停止后按三件套指引手工处理，不属于自动切换路径。
5. 密码在迁移阶段仅内存；重启需要时重新输入。只有明确确认 B 配置提交时，才允许凭据作为受保护配置候选/正式配置持久化。

## 2. 已有基线与实际改造挂点

| 现有资产 | v4 改造边界 |
|---|---|
| `backend/scripts/migrate_sqlite_to_pg.py` 工具 1.1.0 | 抽取服务层，保留 CLI 参数/0、1、2、3 退出码；新版本 checkpoint 不伪装兼容旧工具 |
| `core/pg_baseline.py` 基线/导入标记 | 引擎显式参数化、强制 PG 方言；新增持久 receipt 与身份，不再只靠会被 DROP 的标记 |
| `core/migration.py` / `alembic/env.py` | 正常升级保留；新增显式目标 URL/连接优先级、SQLite 半成品拒启、维护只读分支 |
| `core/config.py` / `core/startup_guard.py` | 统一 EffectiveDatabaseConfig；不再让 `DATABASE_PATH` property 绕过有效记录直接取 env |
| `database.py:init_config_file` | 所有相关 YAML 写入共用锁/原子持久化；受管环境配置损坏不得自动重建默认文件 |
| `startup/lifecycle.py` | 在配置修复、迁移、seed、密码回写、状态修复之前分流维护恢复；关闭阶段亦不得补写源库 |
| cron、同步/删除/orphan dispatcher、TaskLogger | 操作级 lease 与子任务交接，最终通知/日志完成才释放 |
| settings 页签、移动 settings 包装、demo、平台矩阵 | 复用既有 Vue 2 组件/样式/API 信封，不引入 Composition API 或 any |
| Docker `exec uvicorn`、restart policy | 可作为托管适配器挂点；必须验证响应发送/持久提交/退出时序，不能仅凭 is_docker 推断 |

源码位置以实施时实测为准。旧审查引用的 `sync_db_write.py` 实际位于 `app/services/`；WORKERS 与调度范围校验在 `app/core/startup_guard.py`。

## 3. 身份、schema 与业务数据范围

### 3.1 标识不变量

- `deployment_id`：配置卷部署标识；首次使用管理功能时持久创建。
- `database_id`：数据库自身随机 UUID，单例、不可在导入时从源复制给目标；不能用 host 或 revision 代替。
- `operation_kind`：`MIGRATE` 或 `HANDOFF_SAME_DB`；attempt_id 分别为 `sqlite-to-pg/<uuid>`、`pg-to-sqlite/<uuid>`、`handoff/<uuid>`，与来源内容摘要独立；另生成随机 ownership nonce。
- `maintenance_epoch`：每次冻结窗口的代次；`state_version`：单调状态版本，修改操作 CAS 检查。
- `config_generation`：有效配置代次；`digest_version=btdeck-canonical-v1` 明确内容编码/排序规则。
- 数据库 ID + attempt nonce + 本地 manifest 中的目标描述/对象清单共同核对。复制一个旧 marker、相同 head 或相同源摘要均不构成清理/切换授权。管理员完整克隆并替换服务的恶意行为不在自动辨别承诺内。

### 3.2 新增三个受 Alembic 管理的元数据表

| 表（拟） | 用途/关键字段 |
|---|---|
| `bt_database_identity` | 单例 database_id、创建时间、schema_version；现有库经新增 revision 生成身份，禁止在 FROZEN 后补 seed |
| `bt_database_migration_receipt` | attempt_id、source/target database_id、deployment_id、ownership_nonce、revision_at_import、digest_version、全表 counts/digests、schema_fingerprint、不可变 origin_epoch、可撤销 eligible_epoch、状态、activation_generation、activated_at |
| `bt_database_migration_events` | 本地审计回放去重：event_id 主键、attempt_id、序号、事件摘要、归档时间；与正式审计日志同事务写入 |

- 模型注册与唯一 revision 同批交付；SQLite 走原生链；PG 空库仍只经已有 squash 白名单 `create_all+stamp`，同事务初始化其**自己的** identity，不运行业务 seed。
- 表/列/索引新增全部走 Alembic；不直接手工建上述表。既有临时 `_btdeck_import_state` 的特殊机制保留为兼容边界，若需要扩字段也必须明确迁移/版本规则，不能随意增加原生 DDL 旁路。
- `BUSINESS_TABLES = metadata.sorted_tables - 上述三个协议元数据表`，是导入、全列摘要及计数的显式版本化清单；`alembic_version` 只 stamp，不拷贝；`sqlite_*` 系统对象不拷贝。
- 源库元数据须验证结构与状态，但不复制其身份/receipt/event 去重行到目标。用户业务审计记录仍属于 BUSINESS_TABLES，不丢弃；新 attempt 的冻结后审计在激活后单独归档。
- precheck、baseline 空库判定、unknown-table 检测、schema 对拍、CLI 与双方向 verify 共用这份分类。**不是**“忽略所有 `_btdeck_*`”：未知对象仍拒绝。源存在未完成 import marker 必须先报错，不能当合法来源。

### 3.3 完成凭据与拒启标记分离

- **首表导入前即有 ownership 凭据**：PG baseline 同事务建 schema+stamp、生成目标 identity、插入 `IMPORTING` receipt 与初始 marker/checkpoint。receipt 含 deployment/attempt/nonce、源/目标 ID、origin_epoch、eligible_epoch、协议版本；checkpoint JSON 同步这些绑定，不等 finalize 才首次存 nonce。
- SQLite 先以 O_EXCL 在受保护目录创建专属 staging，持久本地 manifest+相邻 ownership sidecar（attempt/nonce、路径/inode/创建记录），才运行原生链。链到 head 后、任何业务行导入前，同事务插入 IMPORTING receipt+marker。链中断尚无协议表时，仅凭匹配的本地 manifest/sidecar/inode及合法 bootstrap 对象清单识别归属，可放弃专属 staging 后新建；不承诺续跑任意半完成 DDL。归属缺失或对象不明即隔离拒删。启动检查也识别 pending sidecar，不能因 marker 尚不存在就 seed 该产物。
- 每表数据+该表 checkpoint 在同事务提交，保存已完成表的行数/主键/内容摘要及 schema 清单。receipt 状态至少有 IMPORTING/VERIFIED/ACTIVATED/STALE/ABANDONED，配置提交阶段另由 manifest 管理。
- finalize 在目标**同一事务**将既有 IMPORTING receipt 更新为 `VERIFIED` 并清未完成标记。事务失败仍是半成品；SQLite 显式事务性 DDL 配置需测试覆盖。receipt 保留，供首次激活核对。
- `VERIFIED` 不等于永久有切换资格。源解除冻结、epoch 变化或目标变化时，本地 switch 资格立即失效；旧产物只能按 §6.3 重新取得本轮资格，不能直接把旧 epoch 当新 epoch。

## 4. 配置、持久文件与引导顺序

### 4.1 完整有效配置（A+B 均使用）

```yaml
database:
  active:
    version: 1
    generation: "<uuid>"
    dialect: postgresql        # sqlite | postgresql
    sqlite_path: null          # SQLite 为已验证的绝对路径
    postgresql:               # SQLite 时必须为空，禁止混入另一方言字段
      host: postgres
      port: 5432
      user: btdeck
      password: "<protected-config-secret>"
      database: btdeck
      schema: public
      sslmode: prefer
      ssl_root_cert: null
      pool_size: 10
      max_overflow: 20
      pool_timeout: 30
    expected_database_id: "<uuid>"
    receipt_attempt_id: "sqlite-to-pg/<uuid>"
    revision_at_import: "<revision>"
    switched_at: "<UTC>"
    switched_by: "<administrator>"
```

- 无 active、无未完成受管切换时保留原 env 行为；active 存在则完整覆盖相应方言配置，包括 `sqlite_path`/CA，不能混用旧 env 的路径或 TLS 参数。
- 参数均结构化 URL.create；密码特殊字符转义；禁止 `str(URL)` 将掩码密码当真实密码。状态接口只返回脱敏摘要。
- 启动、引擎、Alembic、健康状态和日志共用 EffectiveDatabaseConfig。显式 migration Config 的共享 connection/target URL 只作用于该次操作，优先于服务有效配置，不修改全局 settings 或 os.environ。
- shell 只做环境/单 worker 检查，不宣称 env 方言就是正在运行的方言；Python startup_guard 消费有效配置。env 与 active 冲突记录不含凭据的 WARNING。

### 4.2 本地协议文件（不是新的可选连接配置源）

- `CONFIG_DIR/db-migration/control.json`：deployment_id、受管模式/有效 generation 与摘要、pending_attempt。用于检测配置丢失/代次冲突，不独立提供 host/password，也不能自行选择另一数据库。
- `attempts/<attempt_id>/manifest.json`：方向、源/目标身份与不含密码的连接描述、epoch、state_version、工具/摘要版本、source_snapshot 摘要、对象清单、staging/final 路径、cutover commit_phase、候选/前代配置摘要与每步进度。
- 受保护候选/前代 YAML：只在用户确认切换准备后创建，必要时包含 B 记录凭据；与正式 config.yaml 同级敏感。
- `audit/<attempt_id>.jsonl`：带唯一 event_id 的有界本地追加审计，不记录密码、令牌、完整连接 URL、TOTP。
- 保留命名仅含安全 UUID 的目录映射；不直接把带 `/` 的 attempt_id 当任意路径。

所有相关写入：部署互斥锁+代次 CAS→同目录临时文件→flush/fsync→原子 replace→父目录 fsync。先持久管理锚点/intent，才允许对目标产生副作用。候选和父目录权限分别 0600/0700，创建时即限权；归档含密钥同样保护。

`init_config_file` 与 activation/clear/安全密钥补齐必须共用配置仓储锁和 RMW；已有受管证据而 YAML/control/manifest 缺失、损坏或代次不符，**禁止重建默认配置或回 env**。如文件系统无法证明所需锁/原子替换/持久化能力，B 不可用并说明原因，不以“看起来 rename 成功”降级保证。

### 4.3 早期只读引导

引入不依赖 database.py 的轻量 bootstrap：

1. 先判定主机平台；安卓发现 PG env 或 PG active 即明确拒绝，发生在 PG 驱动加载和建引擎之前，不静默新建 SQLite。
2. 取得部署级单实例锁；只读解析 config/control/manifest，完成缺失/损坏/代次检测；识别是否需要维护恢复或首次激活。
3. 维护/恢复时，源 SQLite 必须存在且以只读方式打开，避免丢文件后隐式创建空库；验证 pinned database_id。PG 连接亦不得创建数据库。
4. **恢复维护分支**：不调用配置修复、migrate_database、init_db、密码加密回写、orphan/cron 修复、启动 TaskLogger 或普通后台循环；仅提供只读控制面。维护关闭分支同样只释放资源，不补写源状态。
5. **首次激活分支**：依 §7 核 receipt/commit 并完成 ACK，再进入所选目标正常启动。
6. **普通启动分支**：有效配置解析后沿用 Alembic+seed+任务流程；不是承诺“所有 init_db 零改动”。

维护恢复期间升级代码不允许擅自升级冻结源库。pending attempt 要求同一协议/工具兼容版本；否则保持 recovery-only，使用兼容版本恢复或显式放弃。该限制仅针对未完迁移，不阻止已激活库日常升级。

### 4.4 正常升级规则

- MIGRATE 首次激活：要求 receipt、database_id、generation、attempt/eligible_epoch、导入 revision 与当前准备的工具版本一致，全业务摘要未变，且无半成品标记。HANDOFF_SAME_DB 只核当前已激活身份、旧 generation 与本次交接的当前 schema/配置，不拿历史导入摘要或旧导入 head 限制合法业务变化，见 §7.3。
- 已完成 ACK 的普通启动：核身份与激活凭据；**合法旧 revision 是升级输入，不是拒启理由**，交 `migrate_database` 升至新 head；receipt 的历史导入 revision 不随每次 head 比较。
- 未知/未来 revision 不自动降级、不 stamp、不选另一库；正常非迁移场景沿用已有显式代码回滚兼容约束。身份/凭据/schema 无法核实的切换恢复则拒绝正常启动，并提供只读恢复/离线指引，不能靠删记录解决升级。

## 5. 可证明的停写与维护控制面

### 5.1 操作级 lease 与状态机

`NORMAL → PREPARING → DRAINING → FROZEN → IMPORTING → VERIFYING → READY_TO_SWITCH`。

- 准入判定与 lease 计数共享一个线程/协程安全临界区。PREPARING 先持久 intent 并关闭新普通准入，再检查重任务；有不可等待重任务则安全撤销本次准备并报 409，不能先检查后关门。
- 普通 HTTP、MCP、cron、后台恢复/同步/采样等从入口持操作级 lease，直至远端动作、所有 DB 事务、finally、通知、审计完成。不能以任务终态或 torrent 活动集合为空代替 lease 已释放。
- 子线程/子任务在脱离父执行流前原子继承/转移计数；父已准入可在排空阶段登记其子工作，但全部收尾之前计数不可降零。禁止裸 create_task/to_thread 绕过登记，静态扫描白名单+运行时观测兜底。
- 排空超时保持未冻结、未快照；若未进行目标副作用可撤销准备；若不能确认 worker 已停则保持 HELD，禁止抢先恢复业务。
- 只有计数为零、DB 事务/线程收尾完成、源保护锁取得且指纹固定后才进入 FROZEN。

### 5.2 实际写面与数据库保护

涵盖 cron 普通/内部 job、speed_sampler、dashboard、版本通知、orphan 两 dispatcher、backfill、下载器初始化与 TaskLogger、GET 隐式能力创建、审计/登录刷新、MCP 在途调用、启动及关闭回写。WAL/内存观测无业务写入者可暂停或保持纯只读，不能偷偷发任务日志。

- 维护时默认拒绝**全部普通业务 API（含 GET）**及新 MCP/业务 WebSocket，返回实际 HTTP 503+CommonResponse；不再以 HTTP method 推断安全。
- 显式允许 health、静态前端与经独立依赖认证的 database 控制端点。后者也不是“豁免后随便写源库”；查询使用只读连接，写目标/协议文件必须通过管理器能力检查。
- 源普通 session/原生连接增加冻结保护；源 SQLite 排空后由专用连接持 `BEGIN IMMEDIATE` 阻止新写者，另用只读连接做 backup；PG 按固定顺序取得业务及协议表的 SHARE 锁，设有界 lock_timeout，阻止普通 DML，并使用 REPEATABLE READ 读取快照。
- MIGRATE 的源 fence 连接只允许锁/读/释放，不允许业务 DML；其他源连接在维护中强制 query_only/只读事务。全局事件钩子与原生 DBAPI 入口均需覆盖，异库迁移的目标引擎须验证与源不同。唯一同库例外是 §7.3 已登记的 HANDOFF_SAME_DB：旧进程不写 receipt，新进程在专用受限 fence/ACK 事务中只更新同库协议元数据，绝不允许业务表 DML；不能用普通 pass-through flag 任意绕过。
- 锁/连接丢失、发现漏写或未知 writer 即 HELD/失效，不继续宣称冻结。进程重启后必须重新取 fence 并核源内容，不能认为旧锁仍在。

### 5.3 维护认证与审计

- start 前使用现有认证并检查实际管理员权限、启用状态及强制改密限制；不能把 `require_authenticated_user` 的“有 token”当管理员。
- 新 `maintenance/auth` / `maintenance/auth/renew`：复用纯读取的账户、密码和已启用 TOTP 校验，连接 manifest 中已核身份的源；COMMITTED 后可用已验证且完整的目标。禁止调用普通 login/refresh 的日志写入、密码升级或 token 行更新路径。
- 签发独立 audience/scope 的短期维护 token，绑定 deployment/attempt/epoch，不能用它访问普通业务 API；普通 access 过期后仍可在新浏览器重新认证。失败限流/会话撤销/必要重放防护落本地受保护状态，不降低既有密码/2FA 安全。两端均不可达时不绕过鉴权，转离线恢复。
- 控制动作和认证事件写本地审计，关键副作用前审计事件先持久化；审计磁盘满时拒绝新的危险动作而非丢日志。恢复后将 event_id 去重行与正式审计同事务归档到最终服务库，ACK 前不写源/业务日志；放弃后归档到恢复的源。不能把“清理目标”确认或密码记进日志。

### 5.4 存活、就绪与页面可用

- `/health/live` 表示进程存活；`/health/ready` 在维护时返回业务不可用（503），不绕过现有发布身份门禁。
- 新 `/health/control-ready` 在纯控制面可安全响应时返回 200 与 `businessReady=false`；普通模式沿用现有健康条件。仅暴露粗粒度状态，不泄露数据库/凭据。
- 现 compose 前端依赖 backend service_healthy；实施时须改为可独立提供静态维护页面（service_started），backend 容器探针采用 control-ready 区分维护与死锁，防整栈重启后前端因业务 readiness 永远起不来。无已验证恢复面时仍不得伪报健康。

## 6. 双向管线、恢复、取消与清理

### 6.1 六阶段与预检

在线预检只作预演；正式 start 在冻结后重新验证。两方向均检查源唯一工具 head、schema/表列集合、约束/外键/NULL/范围、SM4 同源与备份可读、原样路径语义、目标不是当前源或其别名。

1. snapshot/precheck：SQLite backup 包含已提交 WAL，快照只读，修复选项只改副本且出报告；PG 固定快照。逆向 Float 必须 `math.isfinite`，时间亦拒绝 infinity/不可表示值，报告表/列/主键；不等到导入后才发现 NaN→NULL。
2. baseline：PG16+、空目标、显式目标引擎强断言 PG，复用原子 squash；SQLite 经显式 Config target URL/connection 重放原生链，禁止修改全局 env/settings、禁止 SQLite create_all。无业务 seed，源 PG 零 DDL。
3. import：依赖序逐表、500 行有界批读；每表事务原子提交 checkpoint，取消仅在协作边界处理；协议元数据不从源复制。
4. calibrate：PG 整数自增序列空表 `setval(seq,1,false)`，非空按 max；SQLite 探测实际 AUTOINCREMENT 对象，当前链无该类表则报告跳过，普通 INTEGER PK 验证后续生成不冲突。
5. verify：全业务表行数+PK 集合+全列类型归一摘要+外键/关联；JSON SQL NULL 与 JSON null 区分，Text JSON 不重编码；时间按现有 UTC 契约，字符串 PK 固定跨库排序，双向共用版本化 canonical 算法。
6. finalize：receipt VERIFIED+清 marker 原子提交；管理器保留冻结。切换前再次全量校验源/目标业务摘要与 schema、取得对应保护，不以抽样或“刚才成功”代替。

PG 版本、TLS 五档/CA/连接预算沿用既有契约。1.5×容量仅预估；分别计入快照、SQLite staging、事务/WAL、候选配置和审计余量。ENOSPC、statement/lock timeout、断连必须有界失败并保持安全状态，禁止无条件重试不确定提交。

### 6.2 SQLite 文件发布

- 默认 final 为解析后的 SQLite 目标父目录内 `app.db.<attempt_uuid>.sqlite`；UI 默认不接收任意绝对路径，使用预核目录+安全文件名。合法自定义 DATABASE_PATH 的目录受支持，不固定 CONFIG_DIR。
- staging 与 final 同 filesystem；若不得不跨设备，先复制到 final 同目录的唯一临时文件，校验+fsync，随后 rename，绝不先删除/改名旧库。
- 发布前目标所有连接关闭，确认 WAL 已 checkpoint、integrity_check/foreign_key_check/摘要通过；无残留未处理 WAL。使用不覆盖的唯一目标，校验目录链接/同 inode/源目标别名和路径遍历，避免 check 后替换。
- 旧 app.db/-wal/-shm 三件保持原位，B active.sqlite_path 指向 final。人工确需换回约定名称时先停所有应用、只读校验、整体留档旧三件，禁止把新主文件配旧 WAL。

### 6.3 重启恢复与凭据

- manifest 保存不含密码的源/目标描述、身份、snapshot/digest 和 checkpoint 线索；缺密码显示 `NEEDS_CREDENTIALS`，认证后重输，验证目标身份再连接。不能根据 attempt_id 猜目标或宣称零凭据自动恢复。
- 已确认 B 准备产生的受保护候选配置可用于该次恢复，但不扩大到未确认阶段持久存储密码；config 快照作为敏感数据限权保存。
- 恢复必须重新冻结、取得源 fence、核源摘要/工具/分类版本、目标 ownership/schema/checkpoint 前缀及每表内容。源漂移不强行续传；保留旧目标为隔离产物，可安全放弃或另建空目标。
- **epoch 重绑协议**（仅未 COMMITTED）：重新冻结生成新 epoch 与 worker_generation；源全量摘要必须等于固定 snapshot，目标未完则核完成前缀摘要/未导入表为空，已 VERIFIED 则核全表摘要。先持久 `REBIND_PREPARED(old,new,proof_hash)`，再在目标事务 CAS 更新 receipt.eligible_epoch 与存续 marker/checkpoint 的 epoch，最后持久 `REBIND_ACK`。ACK 前不进入 READY，也不发给 worker 新写权限；origin_epoch 不改。
- 重绑中断后先保持 HELD，核本地已记录 old/new 与目标实际 eligible_epoch；出现第三个未知代次拒绝。进程/锁丢失仍须重新冻结、重新全量核验并分配新的 epoch，不以旧 proof 直接补发资格。迟到回调同时核 attempt、epoch、worker_generation。已 VERIFIED 产物可在全量复核后重绑复用；漂移拒绝，已 COMMITTED 只按原决定 redo，绝不重绑。
- CLI 保留 `--source-config/--target-config/--backup-root` 原资产语义及退出码；新协议拒绝不兼容 1.1.0 checkpoint，给明确原因。无 active 的旧 env 用法保持；存在 active 且隐式目标有歧义时要求受保护 `--connection-profile` 显式指定，不将原 `--target-config` 偷换成连接参数，也不在命令行要求明文密码。

### 6.4 取消、失败与结果作废

- `CANCELLING` 仅请求 worker 协作停止；`asyncio.to_thread` 协程被 cancel/超时不等于线程结束。
- 只有 worker ACK、事务完成或回滚、checkpoint 持久化、连接/文件句柄关闭后才可 `CANCELLED`；此前禁止 leave/discard/switch/new start。无法确认则 HELD，UI 提示等待/受控重启，不能硬杀后自动当成功。
- 取消/失败若尚未 COMMITTED 且已安全收尾，可按既有 D1 自动恢复源业务，但必须先持久撤销 switch_eligible 并推进 epoch。其他故障保持维护。leave 同样如此，不删除恢复线索。
- 源恢复写入、代码/摘要协议不兼容、任何源/目标漂移后，旧页面的 finalized 产物不能切换；所有修改请求要求 attemptId+epoch+stateVersion+idempotencyKey。

### 6.5 放弃目标的最小删除授权

- discard 仅操作 manifest 固定目标，不接受临时换 host/path；须维护认证、worker 已停、尚未 COMMITTED、目标不是当前有效/源库，且 deployment/attempt nonce/database_id/schema/对象清单全部相符。
- 恢复失败或存在 marker 本身**不是删除授权**。核已提交表内容及对象清单，有外部表/行/修改/未知依赖则拒绝，不能扩大清理范围。
- PG 在有界锁和事务中逐个清理本次拥有的已列对象，顺序明确，**禁止 DROP DATABASE / DROP SCHEMA CASCADE**；新出现外部对象不得被删除。清理后状态不符合空库则隔离拒重建。
- SQLite 只清本次专属 staging/产物（核 identity、hash、inode、句柄关闭）；不删任意路径、当前 active、源或旧三件。合法清理事务失败保留线索，不能自动升级为更强删除。

## 7. A+B 切换提交、ACK 与故障恢复

### 7.1 统一提交不变量

- MIGRATE 的 READY_TO_SWITCH 仅在同 eligible_epoch 冻结有效、worker 收尾、源/目标全量复核、身份/ownership 相符且无待确认重绑时存在；HANDOFF_SAME_DB 的 READY 依 §7.3 当前身份/配置检查，不执行异库或历史导入摘要条件。
- 不论 A/B，先持久生成候选配置/前代备份和 manifest，后发布选择。A 不直接提供一个可立即删记录的危险按钮。
- `commit_phase = NONE → PREPARED → COMMITTED → ACTIVATED_ACK`；COMMITTED 是本地持久决定，之前可显式放弃，之后只能按该目标重做发布/恢复，不自动回旧库。
- 已选库不可达/校验失败：拒绝正常启动，不新建库、不回 env；可证明安全的控制面只读恢复，否则离线指引。不得以删除 manifest/control 掩盖故障。

### 7.2 提交顺序

1. 管理器锁/CAS；MIGRATE 核 source/target ID、全量摘要、schema、epoch、配置代次；HANDOFF_SAME_DB 按 §7.3 核当前同库身份与配置；业务准入继续关闭。
2. MIGRATE 发布完整独立 SQLite final（如适用，§6.2），写目标 receipt 的 generation 准备身份。两类操作均持久候选/前代配置及 PREPARED manifest；HANDOFF_SAME_DB 只读取现有已激活 receipt，不在旧进程源 fence 持有时跨连接写 receipt，也不发布数据文件。
3. **fsync 持久 COMMITTED 决定**（含候选 hash/目标/模式/operation_kind）；此刻尚未解除源维护。后续配置更新按决定幂等 redo。
4. B：原子发布新的 active；A：原子发布去除旧 active 的候选（如有），manifest 固定期望 env 非密码字段/目标 ID；更新 control 代次，记录 RESTART_PENDING。MIGRATE 可补 receipt 的提交信息；HANDOFF_SAME_DB 的 receipt 仍保持原 generation，等新进程 ACK。
5. 响应发送完成且所有关键文件持久化后，已知托管适配器可调度本进程优雅退出；无适配器不发杀进程命令，提示手动重启。不假设 systemd Restart=on-failure 会重启正常退出，也不盲目给 PID1 发信号。
6. 新进程**普通写入前**读取 COMMITTED 并幂等完成配置发布；MIGRATE 核 receipt/导入 revision/全业务摘要，HANDOFF_SAME_DB 核当前 ID/旧 receipt generation/当前合法 schema，不使用历史导入摘要。A 的 env 尚未匹配时只读恢复，不运行源的 seed/修复/任务。
7. 按操作类型取得目标 ACK 事务（同库专用连接规则见 §7.3），先写目标 activated_at/generation ACK，再持久本地 ACTIVATED_ACK/control。两边一致才允许正常 Alembic/seed/审计归档/后台启动。目标 ACK 已写而本地未写时幂等补同一 ACK，不能再换库。
8. 正常目标启动成功后归档 pending intent；保留控制锚点、历史 manifest/receipt 和旧库路径，不清空所有证据。MIGRATE 第一次正常目标业务写入结束无损回退窗口；同库交接不产生新的数据回退窗口。

### 7.3 A 轨交接与清记录

- 页面生成当前配置专属步骤：展示记录优先级、期望 target database_id/路径/TLS/版本以及需要修改的宿主 env 字段；密码只给占位提示，不落审计或公开日志。
- **clear = 受控交接到 env，不是直接删节**：创建独立 `HANDOFF_SAME_DB` attempt，维护态下核 env 候选与当前身份，二次确认，复用文件 commit/ACK，但不复用异库导入条件。
- 该分支必须 source.database_id == target.database_id；无导入、无 staging/丢弃动作，不核历史导入内容摘要或要求旧导入 revision 等于新 head，因此正常业务变化及合法升级后仍可交接。
- 旧进程排空并持源 fence，**仅操作本地候选/manifest/control，不修改同库 receipt**；manifest 钉住既有 ACTIVATED receipt 的 attempt 与旧 generation。退出只关闭/释放 fence，不能以另一连接等待自己持有的写锁。
- 新进程取得部署单实例锁、保持普通准入关闭，核当前库与既有 receipt；使用一个受限同库 fence/ACK 连接事务完成“核旧 generation → CAS 新 generation → 提交”。SQLite 在同一 `BEGIN IMMEDIATE` 连接完成，PG 在同一连接所持锁内完成，避免跨连接自锁。该能力仅授权身份/receipt 协议元数据，不允许业务 DML；本地 ACK 持久后才释放业务准入。目标先 ACK、本地后 ACK 的重启按幂等规则补齐。
- 常规 clear 仅允许 env 指向**同一当前服务库**，作为把 B 管理交还 A，不回到几周前的旧库。若要换到不同库，必须使用新迁移或已验证同 epoch 的迁移产物；历史旧库灾难回退只能走明确离线、有数据损失告知的恢复流程，不伪装 clear。
- 未取得宿主 env 的新值时由用户在页面填期望非密码配置，真正重启后重新验证；确认不一致保持维护。已有 active 的 A 指引包含上述交接，不只写“改 .env 后重启”。

### 7.4 中断恢复矩阵（必须故障注入）

| 中断点 | 启动/恢复结果 |
|---|---|
| 关闭准入前/初始 intent 未持久 | 未允许目标副作用；不把孤立临时文件当合法目标，保留线索 |
| DRAINING / IMPORTING / VERIFYING | 只读维护启动；重新取 fence；缺凭据 NEEDS_CREDENTIALS；核 digest 后恢复或隔离 |
| REBIND_PREPARED / 目标 eligible_epoch 已改而本地未 ACK | 禁止 READY；核已知 old/new，重新冻结与全量验证后完成新的重绑，不承认失去 fence 的旧 proof |
| receipt VERIFIED 后、尚未准备切换 | 不自动激活；核 epoch/源目标摘要，旧资格失效则重做 |
| final rename/copy 完成、配置候选未齐 | 原库不动；按 manifest 核产物，保持维护，补准备或显式放弃 |
| PREPARED、未 COMMITTED | 不发布新配置；只读恢复，允许确认继续或放弃，不能自行当已提交 |
| COMMITTED、config/control/receipt 任一步未完成 | 按持久决定 redo 同一目标；候选缺失/损坏则 fail-closed，不能回 env |
| 已发送响应但旧进程未退出 | 重复 switch 返回同一状态；仍冻结，不再生成新切换代次 |
| A 重启时 env 未匹配 | 仅控制面提示差异，不运行源的 seed/修复/任务 |
| 目标 ACK 后、本地 ACK 前 | 幂等核对并补同一 ACK，普通写入仍关闭 |
| 双 ACK 后、seed/审计回放/任务启动失败 | 保持选择的目标，幂等重试；绝不自动回旧库；回放 event_id 去重 |
| YAML/control/manifest/hash/身份损坏 | 禁止默认配置重建，拒绝普通启动；只读诊断或离线恢复 |

## 8. API 契约（拟）

所有响应用 CommonResponse，reasonCode 位于 data，HTTP 401/403/409/503 与信封 code 对齐。普通管理员认证与维护 scope 分离；分页严格 list/total/pageSize。状态不暴露凭据、完整路径清单或敏感审计给未认证用户。

| 端点（均 `/api/v1/database` 前缀） | 方法 | 约束 |
|---|---|---|
| `/status`、`/migration/status` | GET | 已认证，只读状态/脱敏有效配置/attempt/phase/epoch/stateVersion/可用动作 |
| `/test-connection` | POST | 管理员；显式目标、超时、PG16+/TLS/权限/三状态；不建 schema、不保存密码 |
| `/migration/precheck` | POST | 预演快照，非正式切换凭据；异步有界进度，start 后需重检 |
| `/migration/start` | POST | 管理器单飞行+CAS，关准入并排空后才快照 |
| `/migration/credentials`、`/migration/resume` | POST | 维护 token、匹配 attempt/epoch；只接收绑定目标的凭据，不临时换目标 |
| `/migration/cancel` | POST | 发请求后先 CANCELLING，worker ACK 前不报 CANCELLED |
| `/migration/leave` | POST | 已安全停止、未 COMMITTED；先撤销资格/推进 epoch 再恢复源 |
| `/migration/discard-target` | POST | §6.5 ownership、对象/内容检查与双确认；不传任意新目标 |
| `/target-readiness` | GET | 只读；switch 的全量复核仍在管理器执行，不能据历史 GET 结果越权 |
| `/migration/switch` | POST | mode=A/B、READY_TO_SWITCH、确认与幂等键；执行 §7 |
| `/activation/clear` | POST | 仅 §7.3 的同库交接，不提供裸删除行为 |
| `/maintenance/auth`、`/maintenance/auth/renew` | POST | 只读密码/2FA+本地限流，独立 audience/attempt scope |

新增 reasonCode 至少覆盖 IN_PROGRESS、DRAINING、ACTIVE_TASKS、STATE_CONFLICT、NEEDS_CREDENTIALS、SOURCE_CHANGED、TARGET_CHANGED、OWNERSHIP_MISMATCH、WORKER_NOT_STOPPED、CONFIG_CONFLICT、RECOVERY_REQUIRED、RESTART_REQUIRED、INVALID_SOURCE/TARGET、TARGET_NOT_EMPTY。鉴权注册表、审计枚举、errors.byCode 双语同步；平台拒绝沿用 PLATFORM_CAPABILITY_UNSUPPORTED。

## 9. UI、平台与敏感信息

- 设置「数据库」面板复用 settings-panel.scss，Vue 2 Options/class 风格、完整 TS 类型。展示当前**有效**库、配置来源、记录优先级和部署/托管能力，不把 env 当运行实况。
- PG 表单含五档 TLS 与 CA 路径校验；SQLite 显示最终路径与留档源路径，不隐藏自定义 DATABASE_PATH。
- 维护页展示 PREPARING/DRAINING/FROZEN/worker 收尾、NEEDS_CREDENTIALS、READY/提交/等待重启/恢复原因，不能用“100%”掩盖尚未激活。
- A/B 两种入口均保留；B 未知重启能力明确提示“配置提交，需手动重启”；A 给适配当前 active 的交接步骤。清记录展示同库目标，异库选择引导新迁移。
- 维护 token 独立组件/客户端通道，普通 axios 503 不无限 refresh、不注销维护会话；定时器 beforeDestroy 清理、刷新页面从服务端重建状态，密码不写 localStorage/URL。
- `db_migration` 能力在服务端注册；Android 本机从 bootstrap→API→页面三层拒 PG/迁移。移动浏览器按服务端矩阵；demo 不接真实目标，提供明确禁用/只读样例。
- 状态与日志统一脱敏；应用日志 filter 覆盖异常、URL、参数和连接失败路径，不能只复用 MCP 输出 canary。config/候选/前代备份含凭据，绝不加入导出证据、Git 或任务结果。

## 10. 模块划分与复用

```
app/core/database_bootstrap.py           # 无引擎导入的有效配置/平台/恢复分流
app/models/database_migration.py         # 三个 Alembic 管理元数据模型
app/services/db_migration/
  manager.py                            # 单飞行、状态/CAS/epoch/worker ACK
  maintenance.py                        # 准入 lease、排空、fence、生命周期适配
  maintenance_auth.py                    # 只读认证、独立维护 scope
  journal.py                            # manifest/control/审计持久化与恢复
  activation.py                         # A/B 提交与 ACK、托管重启适配
  pipeline.py / sqlite_to_pg.py / pg_to_sqlite.py
  canonical.py / target_params.py        # 双向摘要、完整目标参数
```

`database.py` 的 URL/连接构造、配置 RMW、审计事务工具先检查复用；共用 schema 分类/事务帮助器，不平行复制另一套 URL/TLS 或业务鉴权。旧 CLI 是薄壳但其兼容测试不得省略。所有新模块进入 roadmap/feature task files 的实际交付清单。

## 11. 验收矩阵（均未执行）

| ID | 必须通过的用例 |
|---|---|
| T01 | B 已激活 H→新 head X 正常升级；首次激活不匹配拒启；未知版本不改选库 |
| T02 | baseline/首表导入前后 IMPORTING ownership 已持久；SQLite schema 中断 sidecar 路径可核归属；finalize 原子更新 receipt+清 marker；错误 nonce/目标拒绝；协议表分类不破坏再次双向迁移 |
| T03 | 确定性屏障覆盖准入→登记、最后业务提交→通知/审计、MCP 在途、线程子任务；未排空不能快照 |
| T04 | 每个 manifest/fsync/rename/config/control/receipt/ACK/退出点注入 kill/IO 故障，满足 §7.4 |
| T05 | GET 能力默认创建、密钥 GET 审计、普通 login/refresh、控制审计在维护中源零写；令牌过期/新浏览器安全再认证 |
| T06 | 真实 lifespan/关闭路径带缺 seed/running/明文密码/TaskLogger 哨兵，维护重入与退出无普通写入 |
| T07 | 重启丢密码→NEEDS_CREDENTIALS；阻塞线程取消等待 ACK；晚回调/旧页面拒绝；新冻结无漂移可重绑，漂移拒绝；REBIND 各中断点恢复不继承旧资格，COMMITTED 禁重绑 |
| T08 | 自定义 DATABASE_PATH、verify-ca/full、CA 不可读、路径链接/同 inode/穿越、EXDEV、ENOSPC、WAL 非空；旧库不被改动 |
| T09 | 所有 YAML RMW 原子/锁/未知节保留/配置及密钥不丢，受管文件损坏不得自动默认化 |
| T10 | SQLite/PG 在业务已变化或合法升级后 B→A 同库交接成功；单连接 fence/ACK 无自锁；各 ACK 中断可恢复；A 有旧 active 的交接正确，裸 clear/异库目标拒绝 |
| T11 | discard 遇外部表/行/依赖、错误目标、复制标记、active/源/未知文件均拒；合法本次目标能清理 |
| T12 | 真 PG Float NaN/Infinity、时间 infinity 在预检拒绝且不建目标；双向 JSON NULL/Text/时间/大整数语义 |
| T13 | Android PG env/active 在加载驱动前拒绝且零 PG 连接；Android SQLite、NAS 移动浏览器、demo/frozen 门控不回归 |
| T14 | PG 专用初始化误收 SQLite 引擎在任何 DDL 前拒绝；反向 Alembic 在 PG 运行态只改新 SQLite，源零 DDL |
| T15 | Settings/startup_guard/Alembic/健康/日志同源；shell 单 worker 检查不误报方言 |
| T16 | switch 响应 flush 后退出；已知 Docker 托管真实重启；未知托管仅提示，不能丢掉已提交状态 |
| T17 | attempt/nonce/digest_version、epoch/CAS/幂等冲突矩阵；1.1 checkpoint 明确拒新版本恢复 |
| T18 | 源写观测使用同一 SQLite 连接的 data_version+DML/commit+内容核对，PG 独立观测；同主键同计数 UPDATE 必须令测试失败 |
| T19 | SQLite→真 PG→新 SQLite 全业务摘要全等；重复正反向不复制身份/协议表；schema 对拍+空表自增+FK |
| T20 | CLI 参数/资产检查/退出码/--resume 兼容；旧 env 与有 active 的显式 profile 均测 |
| T21 | health live/business ready/control ready、整栈维护重启前端可用、axios 503/维护认证无刷新死循环 |
| T22 | 本地审计在双方向激活/放弃后去重回放，故障及容量上限不丢事件、不泄露密码/TOTP/token |

后端全量 pytest 顺序执行，另跑真 PG 集成/TLS；mypy、black --check app/、flake8 app/、架构扫描；前端 typecheck/lint/全量 Jest/build；`./init.sh --ci`。无 PG 实库环境的 skip 不能登记为 T19/T12 通过，W6 需真实同堆栈与托管验证。

## 12. 实施批次与进入门禁

| 批次 | 内容 | 状态/出口 |
|---|---|---|
| W0 | v4 设计、状态/恢复矩阵、二审逐项映射及定向独立复核 | done（仅设计）；复核补出的3处矛盾已再次设计闭合，见 §16；本轮不自动启动 W1 |
| W1 | 显式配置/URL与服务抽取、三表 Alembic/身份/receipt 分类、双向管线/CLI、目标拒启 | pending；T01/T02/T12/T14/T19/T20 + 后端门禁 |
| W2 | 准入排空/fence、只读引导及关闭、维护鉴权/本地审计/取消 epoch | pending；T03/T05/T06/T07/T13/T18/T22 |
| W3 | journal/config 仓储、A+B commit/ACK、同库 clear、ownership discard、健康与托管 API | pending；T04/T08/T09/T10/T11/T15/T16/T17/T21 |
| W4 | 设置面板、维护独立客户端、A/B、平台/demo/i18n/移动、Jest | pending；前端门禁与 API 联调；不先开放未受屏障保护的端点 |
| W5 | 全量/真 PG CI/故障注入、契约/API/runbook/roadmap 同步与证据 | pending；不得把普通单测替代故障/实库证据 |
| W6 | unraid 真实同堆栈双向、已知托管重启、A/B交接、掉电/磁盘故障场景 | pending；经用户授权的隔离测试数据，不碰生产库演练 |

新增 schema 与配置优先级契约在对应实现批次同改，不推迟到最后才对齐：§2.1 有效配置+受管锚点；§3 暂停/receipt/ACK/回退窗口；database-migration.md 三协议表分类及维护只读启动；平台矩阵、MCP 维护整体停用、health/compose 与运维恢复步骤。

## 13. 二审问题 → v4 修订/验收映射

以下为**设计处置**，统一状态 `DESIGN_REVIEWED_IMPLEMENTATION_PENDING`（§16 定向复核），不是实现或实验层 CLOSED；二审原报告保留 v3 的原结论，不重写历史。

| 二审项 | v4 对应条款 | 验收 |
|---|---|---|
| P0-1 升级被 head 相等阻断 | §4.3–4.4 首次激活/正常升级分流 | T01 |
| P0-2 无目标持久 receipt | §3 三表/身份/分类与原子 finalize | T02/T19 |
| P0-3 停写无准入排空屏障 | §5.1–5.2 lease/子任务/fence | T03/T18 |
| P0-4 跨文件无持久提交 ACK | §4.2、§7 提交及恢复矩阵 | T04 |
| P1-1 GET/审计/鉴权写与过期失联 | §5.2–5.3 默认拒普通 API、只读认证/本地审计 | T05/T22 |
| P1-2 维护启动仍 seed/回写 | §4.3、§5 维护启动与关闭分支 | T06 |
| P1-3 恢复/取消/有效期 | §6.3–6.4 NEEDS_CREDENTIALS/worker ACK/epoch | T07 |
| P1-4 路径/TLS/跨盘/WAL | §4.1、§6.2 独立 final 与完整目标配置 | T08 |
| P1-5 YAML 多写者破坏 active | §4.2 共用仓储锁/持久化/受管损坏拒绝默认化 | T09 |
| P1-6 clear/A+B 回旧库 | §7.3 同库交接，不裸删记录 | T10 |
| P1-7 discard 缺所有权 | §3.1、§6.5 最小清理授权 | T11 |
| P1-8 非有限浮点 | §6.1 双向严格预检 | T12 |
| P1-9 安卓引导拒 PG | §1.2、§4.3、§9 三层平台门控 | T13 |
| P2-1 临时引擎错方言 | §2、§6.1 强断言+显式 Config | T14 |
| P2-2 配置消费者不同源 | §4.1 EffectiveDatabaseConfig | T15 |
| P2-3 重启响应时序 | §7.2 托管适配/持久提交/响应 flush | T16 |
| P2-4 标识算法版本 | §3.1、§6.3 独立 ID/nonce/版本 | T17 |
| P2-5 零写 oracle 不足 | §11 固定连接+DML/commit/内容与阳性对照 | T18 |

## 14. 用户决策、历史与剩余边界

- 2026-10-28 D1/D3/D4/D5 认可；D2 A+B；D6 安卓不支持 PostgreSQL。v4 没有删 B、缩成单向或放宽安卓。
- 第一轮提出 2P0/5P1/4P2，v2/v3 写入条款但未验证关闭；第二轮 [原报告](./database-migration-ui-review-round2.md) 给出 4P0/9P1/5P2。v4 已落实状态机/规则/验收映射并完成 §16 的定向设计复核；实现与实验验证仍待 W1–W6。
- D3 的执行收口为**直接激活独立 SQLite 路径，不覆盖旧三件**；D1 自动退出仅限 worker 安全收尾且未 COMMITTED，无法确认时继续维护。两者是为已认可的独立产物/停写目标提供安全实现，不改变迁移方向与用户操作入口。
- 对外部直接写库、恶意管理员改控制文件、存储不提供要求的持久化语义不作自动无损承诺；需要本机权限的离线灾难恢复明确告知数据丢失边界。
- 本轮未改业务代码、未创建 revision/PG 服务、未执行迁移/故障注入。不能用文档检查通过宣称功能完成。

## 15. 本轮已执行检查

- 轻量 `./init.sh --ci`：根 exit=0，两端脚本完成但有环境告警；当前 shell 未激活后端 venv，Alembic/mypy/black/flake8/pytest 命令缺失，sqlite3 CLI 不可用；前端 ESLint/TS/API 地址识别不完整。未安装依赖，也未用根 exit=0 声称质量门全绿。
- **已通过文档/追踪检查**：22组验收ID连续完整、18项二审映射齐全、相关相对链接存在、feature_list JSON合法/ID唯一/仅W0 done且W1–W6 pending、原有features内容未变；tracked diff与新计划/报告的whitespace检查通过。
- 功能测试/真 PG/故障注入/构建/部署均 NOT RUN。

## 16. v4 定向设计复核记录（2026-10-28）

acceptance-reviewer-gpt 对照二审18项定向复核：15项已有实质条款，另提出3处设计矛盾。修订后再次只读复核这3项，结论均为**设计层已补**：

| 补项 | 修订与复核结果 | 实现验收 |
|---|---|---|
| 同库 clear 套异库约束/跨连接自锁 | §5.2、§7.3 独立 HANDOFF_SAME_DB，不核历史导入摘要；旧进程不写 receipt，新进程同连接 fence/CAS/ACK | T10 NOT RUN |
| finalize 前 nonce 无目标持久落点 | §3.3 baseline 即 IMPORTING receipt；SQLite schema 引导前 sidecar 归属和中断边界 | T02 NOT RUN |
| 新冻结与旧 receipt epoch 无重绑规则 | §6.3 PREPARED→目标 CAS→本地 ACK；失 fence 重新冻结/核验，COMMITTED 禁重绑 | T07 NOT RUN |

这是设计条款复核，不代表整份软件的功能、安全或发布验收；未修改业务代码、未运行测试。
