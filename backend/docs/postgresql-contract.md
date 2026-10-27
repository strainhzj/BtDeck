# PostgreSQL 数据源契约（v1.0.8 双数据库架构）

> **状态**: P0 契约与基线交付物（2026-09-28，基线 dev@c7bf20b）
> **计划**: `PLANS/v1.0.8.md` v7（五轮审查 + 基线刷新）
> **性质**: 实施期契约文档；P1-P4 实施与本文件冲突时以计划审查结论为准并回改本文件

---

## 1. 版本与运行边界

| 项 | 契约 |
|----|------|
| PG 最低版本 | **16+**（启动/迁移入口实测版本；PG<16 拒绝启动） |
| 应用实例 | **单应用实例、单 worker**；PG 模式多 worker **fail-fast 拒绝启动**（现有仅 scheduler 警告） |
| 不承诺 | 多实例调度治理、写入并发收益（`db_write_scope` 串行写语义不变） |
| 桌面/伴侣模式 | 发行版无环境变量注入机制，恒 SQLite；与 `DEV` 无关（`DEV=false` 是生产安全配置，Docker 同样使用） |

## 2. 配置契约

### 2.1 优先级与取值

```
DB_TYPE（唯一方言判定入口，settings.DATABASE_DIALECT 归一化）
  ├─ sqlite（默认，零变化）：路径由 DATABASE_PATH 决定（env > CONFIG_PATH/app.db）
  ├─ postgresql（别名 postgres/pg 归一）：消费 DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME
  └─ 其他取值：启动 fail-fast（防静默回落造成数据错位）
DATABASE_URL：废弃路径——startup_guard.py / btdeck_startup.sh 判据迁至 DB_TYPE（P1 任务1.5）
URL 构造：sqlalchemy.engine.URL.create（结构化，凭据转义；特殊字符 % @ / : 空格 单测覆盖）；**禁用 str(URL)**——SQLAlchemy 2.0 会把密码掩码为 `***`，引擎将拿到字面 *** 密码认证失败（P4 真 PG 实测抓出，用 render_as_string(hide_password=False)）
```

### 2.2 连接池

| 引擎 | 池 | 参数 |
|------|-----|------|
| sync（psycopg2） | QueuePool | `DB_POOL_SIZE`/`DB_MAX_OVERFLOW`/`pool_timeout`/`pool_pre_ping` |
| async（asyncpg） | AsyncAdaptedQueuePool（默认，勿传普通 QueuePool） | 同上 |
| 连接预算 | `(sync pool+overflow)+(async pool+overflow)` 必须 ≤ PG `max_connections` 规划值 | 文档化 |

### 2.3 TLS 逐模式映射（默认 `prefer`）

| 模式 | psycopg2（sync） | asyncpg（async） |
|------|------------------|------------------|
| disable | URL `sslmode=disable` | `connect_args["ssl"]=False`（**不可不传 ssl**——缺省即 prefer） |
| prefer | URL `sslmode=prefer` | asyncpg 模式串（允许回退明文） |
| require | URL `sslmode=require` | asyncpg `ssl="require"`（不校验 CA） |
| verify-ca | `sslmode=verify-ca` + root cert | SSLContext（加载 `DB_SSL_ROOT_CERT`） |
| verify-full | `sslmode=verify-full` | 同上 + 主机名校验 |

实测要求双向：无 TLS 服务端双驱动行为一致；**有 TLS 服务端验证 disable 实际建立非 TLS 连接**。
边界：支持"客户端验证服务器证书"；"客户端证书认证"（DB 端要求客户端证书）本期边界外。

## 3. 基线策略七规则（演进式建库）

1. **空库判定**：无 `alembic_version` **且无业务表**（information_schema 白名单）；有表无版本 → fail-fast 人工介入
2. **模型注册**：`app/core/model_registry.py` 单点集中 import；create_all 不依赖 API import 顺序
3. **原子性**：`create_all + stamp` 同一连接同一事务（`Config.attributes["connection"]` 共享连接，env.py 优先复用）；附"建表后、stamp 前故障"回滚测试
4. **新装数据覆盖**：见 §5 审计矩阵（全部免重放成立）
5. **最低可降级 revision**：PG 库 downgrade 下限 = PG 支持落地 head；禁入 SQLite 专属历史迁移
6. **CLI 一致性**：合法初始化入口 = 应用启动（`migrate_database`）+ 迁移工具（共享基线函数）；`env.py` 空库守卫拒绝手工 `alembic upgrade head`
7. **ghost 版本**：`KNOWN_GHOST_VERSIONS` 仅 sqlite 方言启用

**目标库三状态**（迁移工具）：全新→共享基线函数（只 schema+stamp，不 seed 不起任务）；导入未完成→校验迁移 ID/快照摘要/工具版本/检查点后恢复，应用遇标记拒启动；已有数据/来源不明→拒绝。
**源库停写**：最终快照前停写并保持至切换完成；在线快照仅预演。
**无损回退窗口**：仅限导入完成后、应用首次正常启动前的离线核对；首次启动即结束。DB 只读会话仅额外保护。
**sequence 校准**：仅整数自增 PK 表（含 `downloader_speed_sample/hourly`）；空表 `setval(seq,1,false)`。

## 4. 双方言语义契约

### 4.1 大小写匹配（LIKE）

- SQLite：现状零变化（原生 ASCII-only 折叠）
- PG：列值与搜索值应用**同一 A–Z→a–z 折叠函数**（`translate`，构造性 locale 无关）+ 各自 LIKE 模式（contains/startswith/endswith，`autoescape=True` 保留）；**不用 ILIKE、不改 `=`、不做大小写互换**
- 非 ASCII 折叠：允许差异（登记 §6）

### 4.2 正则搜索

- SQLite：`bt_regexp` 自定义函数（Python `regex` VERSION1 全语法，零变化）
- PG：`~`/`~*`，仅承诺**共同语法子集**；PG 请求前置语法校验，子集外表达式执行前 4xx 拒绝
- 查询预算：请求级 deadline；每条 SQL `SET LOCAL statement_timeout`=剩余预算；**剩余 ≤0 直接终止不发 SQL**（禁写 0 值）；超时→rollback + 明确错误响应

### 4.3 JSON 字段契约（按字段）

| 字段 | 元素类型 | 可空性 |
|------|---------|--------|
| `orphan_purge_job.orphan_ids_json` | 整数（排除布尔+范围校验） | CLEANUP 数组 / **PURGE 合法 NULL** |
| `orphan_purge_job.canonical_paths_json` | 字符串路径 | PURGE 数组 / CLEANUP `"[]"` |
| 活动删除 `active_deletion_ids` | 字符串 info_id | **内联 literal 非持久化列**（应用自构造，无损坏面） |

- 迁移预检：非数组/类型不符默认拒绝；**仅允许与字段元素类型匹配的裸标量**包裹（出报告）；对象/错误类型拒绝
- PG 运行时：`cast(... AS jsonb)` + `jsonb_array_elements_text` 实现数组守卫；非法文本或非数组 fail-fast（SQL NULL 按适用性允许）
- SQLite 行为零变化（非法文本→空集宽容，登记 §6）

### 4.4 布尔裸 SQL（P0.3 实测清单，P2 任务2.3 改造范围）

| 位置 | 列（类型） | 现状 |
|------|-----------|------|
| `default_templates.py:256` | `setting_templates.is_system_default`（Boolean） | `WHERE ... = 1` |
| `speed_sampler.py:38` | `bt_downloaders.enabled`（Boolean） | `WHERE enabled = 1` |
| `speed_sampler.py` 聚合 SQL | `downloader_speed_sample.online`（Boolean） | `CASE WHEN online = 1` |
| `batch_class_validator.py:217` | `cron_task.enabled`（Boolean） | `SET enabled = 0`（修复路径） |

**甄别排除**（Integer 列，双库合法，勿误改）：`search_templates.is_default/is_public`（`Mapped[int]`）、`torrent_info.dr`/`tracker_info.dr`（Integer 0/1）、`default_search_templates.py:145,168`（Integer 列）、`report_service` 各处 `dr = 0`。

## 5. 历史数据迁移审计矩阵（P0.2，37 迁移全量）

**方法**：全迁移 grep 数据操作（`op.execute` 写操作/UPDATE/INSERT/DELETE）→ 13 个命中逐条分类；其余 24 个纯 DDL。

| Revision | 数据操作 | 新装 PG 免重放依据 |
|----------|---------|-------------------|
| a1f7c9e3d2b4 | hash/info_hash/cursor_value 小写回填 | 写入路径已统一小写（df6b8c0 P0-D）✅ |
| 6132b66d14a7 | ratio String→Float 清洗 + printf 格式化 | 新装列直接 Float，无存量 ✅ |
| 7b2c9d4e6f10 | orphan_scan_result/current_candidate 回填 | 运行时扫描生成，新代码写入即正确 ✅ |
| a7b8c9d0e1f2 | disabled_by='user' 回填 + datetime('now') | 运行时路径直接写正确值 ✅ |
| 4c1d8e7a2b90 | cron_task 错峰计划回填 | seed `default_scheduled_tasks` 已含错峰值 ✅ |
| a1b2c3d4e5f6 | canonical_path 回填 | 扫描代码插入时即计算 ✅ |
| f2a7c91b4d6e | candidate→resolved 状态回填 | 历史状态修复，新装无此数据 ✅ |
| d4e5f6a7b8c9 | orphan_file 副本数快照 UPDATE | 运行时生成 ✅ |
| c1d2e3f4a5b6 | orphan_current_detail_id 漂移修复 | 一次性修复 ✅ |
| d1e2f3a4b5c6 | setting_templates preset_key 回填 | seed 直接带 preset_key ✅ |
| b3e5f7a9c1d2 | search_templates preset_key 回填 | seed 直接带 preset_key ✅ |
| 8f4c2d1a9b7e | ratio 二次清洗 | 无存量 ✅ |
| c9e0f1a2b3c4 | TR added_date 时区回填（Python 三段式） | 写入路径 W2 已修复（`_parse_qb_epoch`）✅ |

**结论：13/13 免重放成立**——全部为存量数据回填/修复，新装 PG 由 seed 与现行写入路径保证正确值。**演进式基线（跳过全部历史迁移）语义安全。**

## 6. 允许差异登记表（初始）

| # | 差异项 | SQLite | PG | 依据 |
|---|--------|--------|-----|------|
| 1 | JSON 非法文本宽容 | `json_valid` 守卫→空集 | 契约违规 fail-fast | 字段由应用恒以数组写入（§4.3） |
| 2 | JSON 对象/标量展开 | `json_each` 展开对象值/标量为单元素 | 顶层数组契约拒绝 | 同上；预检+裸标量包裹覆盖历史数据 |
| 3 | 非 ASCII 大小写折叠 | 原样 | 折叠表达式构造性排除（A–Z only） | §4.1 |
| 4 | 正则语法域 | Python regex VERSION1 全语法 | 共同子集（前置校验拦截） | §4.2 |
| 5 | ratio CHECK 约束形式 | 迁移链中 typeof() 守卫（防 TEXT 残留，8f4c2d1a9b7e） | ORM 中立数值边界（PG 列类型拒非数值）；SQLite 生产 schema 由链负责，ORM 双方言中立形式仅 PG 基线 create_all 消费 | P1 任务1.3（torrents/models.py 注释） |

## 7. P0.3 类型与 SQL 盘点结果

### 7.1 类型普查（mapped_column 全量）

`String 234（其中无长度 43 处——PG VARCHAR 无长度合法，不阻断）｜Integer 115｜DateTime 91｜Text 41｜Boolean 38｜DATETIME 18（**实测修正**：大写 `sqlalchemy.DATETIME` 在 PG 渲染为字面 DATETIME 类型导致 create_all 失败——P4 真 PG 集成实测抓出，已全量换 `DateTime`，SQLite 渲染两者同为 DATETIME 零变化）｜BigInteger 8｜Float 4｜SQLEnum 2`

- JSON 列 4 处（v1 盘点确认，SQLite/PG 序列化由 SQLAlchemy JSON 类型统一承担）
- server_default 26 处：`"0"`×12、`func.now()`×6、`"1"`×6、`"purge"`、`"[]"`——全部双方言可移植（func.now()→PG now()）
- 模型层唯一 PG 阻断项（typeof() CHECK / sqlite_where 单声明）已列 P1 任务1.3

### 7.2 SQL 盘点（扩展维度）

| 维度 | 结果 |
|------|------|
| upsert（ORM `on_conflict_do_*`） | 5 处：speed_sampler:224、torrents_async:905/1002/1223、torrent_sync:747 |
| upsert（裸 SQL `ON CONFLICT`） | tracker_message_logger:231/692、torrent_sync partial index 场景 |
| `sqlite_insert` 导入 | 7 文件（speed_sampler/torrents_async×2 处/torrent_sync） |
| 布尔裸 SQL | §4.4 清单（4 处真实 + 甄别排除项） |
| 日期裸 SQL | `datetime('now')` 5 处；`strftime` SQL 层 2 处（speed_sampler）+ `datetime()` JOIN 1 处 |
| savepoint | 全仓无 `begin_nested` 使用——异常路径 rollback 语义在 P2 改造时逐处确认（裸 SQL 执行失败的 rollback 完整性） |
| 默认值来源 | Python 侧 default 为主 + 26 处 server_default（可移植）；无 SQLite 专属函数默认值 |

## 8. P0.4 数据风险预检（静态评估）与排期重估

**静态风险清单**（真实预检需生产库副本，P4 迁移工具预检模式复用）：
1. SQLite 类型亲和残留：数值列历史文本值（6132/8f4c2 已清洗，预检兜底校验）
2. 布尔存储：SQLite int 0/1 → PG Boolean 需显式 cast 导入
3. DATETIME 文本格式：微秒/非微秒双格式（report_service `_as_dt` 兼容为证）→ PG timestamp 隐式转换 + 预检格式校验
4. 高体量表：`downloader_speed_sample`（14 天 × 每下载器 1440 行/天）分批尺寸与时长单独预估
5. 软删同键（合法保留，仅报告）；canonical_path 反斜杠变体（迁移按原样拷贝，语义由应用层统一）

**排期重估**：维持 8-12 人日粗估——基线刷新新增量（speed_sampler 清扫 + speed 两表迁移 ≈ +0.5-1 人日）被清洁确认（report_service/RSS 免改造）部分抵消；**P1 结束后二次校准**（引擎工厂+模型双方言化的实际复杂度）。

---

**维护**: 本文件随 P1-P4 实施更新；允许差异登记表新增条目须注明依据与审查轮次。


## 9. 独立验收补充（2026-10-03）

完整证据与复现命令见 `PLANS/postgresql-acceptance.md`（仓库根）。
基线对拍现覆盖默认值、独立唯一约束和外键目标/删除行为，并在真实 PG
上用 Alembic introspection 对比 metadata。缺失的服务端默认值归位模型，
SQLite 生产 schema 仍由原迁移链管理。

正则共同子集：普通字面量、转义元字符、非嵌套字符类、分组/非捕获分组、
选择、锚点和界限不超过 255 的重复；拒绝扩展分组、反向引用、集合运算、
不兼容转义及超界重复。请求校验与迁移模板扫描共用校验器。
PG 谓词转换 dot 与 `$`，对齐默认换行/尾锚点；NULL 匹配为 false。
请求预算覆盖 count、list 和结果转换中的所有 SQL；结束成功时恢复原 timeout，
取消/耗尽时回滚，禁止将 0 作为剩余预算下发。

迁移工具 1.1.0 的同源配置、备份可达性、一致性快照和恢复边界详见
`docs/database-setup.md`（仓库根）。导入标记与基线原子创建；数据与每表检查点
原子提交。工具拒绝旧版检查点，避免继续旧版非原子导入状态。

验收补充（2026-10-03）：PG CLI 在无版本记录（含空 alembic_version 表）时拒绝重放历史链；应用也拒绝自动修复空版本表。最终证据见 `PLANS/postgresql-acceptance.md`。
