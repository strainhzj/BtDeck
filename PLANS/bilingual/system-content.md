# 系统内容清单：预设身份 / 通知事件 / 时间约定 / 生成契约（P0）

> 生成：2026-09-18。覆盖主计划 §3.3「API 与系统内容」的 P0 核对项：生成契约源文件、历史时间约定、预设身份与迁移方案。

## 1. 查询模板系统预设（search_templates）

**现状（实测 `app/data/default_search_templates.py` + `app/models/search_template.py`）**：
- 4 个预设：`活跃种子` / `错误状态` / `已暂停` / `大文件`；`user_id="system"`、`is_default=1`、`is_public=1`。
- **幂等身份 = 中文名 + `is_default=1`**（`SELECT name FROM search_templates WHERE is_default=1` 去重）；id 为随机 UUID，无唯一约束。
- `conditions` JSON 内含中文：`大文件` 预设的 `condition_groups[0].name="大文件"`（前端展示用组名）；其余查询值/字段/操作符为英文枚举。
- 时间：初始化用 `datetime.now()`（本地时间）写 `created_time/updated_time`（模型列默认 `datetime.utcnow`，见 §4）。

**迁移方案提案（P4 实施，走 Alembic）**：
1. 新增列 `preset_key VARCHAR(64) NULL` + 普通索引；不做唯一约束（避免旧库脏数据阻塞升级），幂等由 init 逻辑保证。
2. 稳定身份：`active_torrents` / `error_status` / `paused` / `large_files`（代码常量 `DEFAULT_SEARCH_TEMPLATE_KEYS`，与名称解耦）。
3. 回填（一次性迁移辅助，符合主计划「中文旧名称最多作为一次性迁移证据」）：
   - `UPDATE ... SET preset_key=:key WHERE is_default=1 AND preset_key IS NULL AND name=:中文名`（四条，逐一对应）；
   - 命中 0 行或 >1 行的记录**不猜**：保持 NULL 并记日志（歧义保留，B02）。
4. `init_default_search_templates` 改为按 `preset_key` 幂等（先查 key，再退化查旧中文名做首启兼容）；新建记录直接写 key。
5. 展示层翻译：前端按 `preset_key` 取本地化名称/描述（新增 `search.presets.*` 键）；**不改用户可见的存储值**——旧库中文名在 API 响应中保留，仅展示映射（Q02：用户同名/复制/改名不覆盖）。
6. `conditions` 内组名：新增预设改存 `nameKey`（或按 `id: preset_large_files` 稳定标识映射）；已入库旧 JSON **不改写**，前端按 id 识别预设组名并本地化，非预设组保持原文。

## 2. 下载器设置模板（setting_templates）

**现状（`app/data/default_templates.py`）**：5 个预设，中文名 `qBittorrent标准模板` / `qBittorrent高性能模板` / `Transmission标准模板` / `Transmission高性能模板` / `夜间不限速模板`；幂等 `filter_by(name=...)`（:225）。描述含参数明细中文长句。

**方案**：与 §1 同构——`preset_key`（`qb_standard` / `qb_highperf` / `tr_standard` / `tr_highperf` / `night_unlimited`）+ 一次性名称回填 + 展示层按键翻译；description 的参数句改为参数化模板（速度/连接数走插值，不硬编码中文数值句）。归属 **M2**（主计划矩阵：设置模板 M2），P4 先落 key 契约，翻译随 P6。

## 3. 系统通知事件

**模型（`app/models/notification.py`）**：`type/title/content/priority/is_read/extra_data(Text JSON)/dedupe_key/created_at(utcnow)/read_at`。title/content 为产生时的**中文自由文本**；extra_data 可承载结构化参数。

**已核实的产生源（M1 壳层需理解的两个）**：
| 事件 | 源 | 现状 | 结构化程度 |
|---|---|---|---|
| `orphan_scan_completed` | `orphan_notification.py` | title=`孤儿文件扫描完成`，content=中文句（N 个孤儿/大小/护栏提示） | **extra_data 已含 event/scan_id/scan_type/orphan_count/orphan_size/route** ✅ |
| 批量添加完成 | `torrent_batch_add_service.py:397` | title=`批量添加种子完成`，content=中文汇总 | ❌ 无 event 键，参数在正文里（需 P4 补 extra_data：total/success/failed + event） |

**方案**：
- 通知表**不加列**：按主计划「读取/展示时翻译，不按产生语言永久保存」——前端 NotificationDrawer 按 `extra_data.event` 已知事件映射本地化 title/content 模板（插值用 extra_data 参数）；未知 event 或无 extra_data 的**历史/自由文本通知原文展示**（E03）。
- P4 增量为：①补齐批量添加事件的 extra_data 结构（新通知才有，旧通知不改写）；②事件键登记表（本文件维护）：`orphan_scan_completed`、`torrent_batch_add_completed`（提案名）、版本更新类通知（P4 时盘点 `notifications.py`/升级检查源，M1 只需壳层不误译历史文本）。
- dedupe_key 语义不变。

## 4. 时间约定核对（结论：混用存在，翻译不触碰）

- 模型列默认：`search_template.created_time`、`notification.created_at` 等用 `datetime.utcnow`（naive UTC）。
- 写入路径：`default_search_templates.py` 初始化用 `datetime.now()`（本地）；`audit_service.py` `operation_time=datetime.now()`（本地）。
- 工具层：`app/utils/datetime_utils.py` 约定 naive→按 UTC 处理；`audit_logger.py:144` 计算本地时区偏移。
- **结论**：存储与展示链路同时存在 naive-UTC 与 naive-本地两种写入口径，属既有行为——**双语化不改变任何时间语义**；P1 的集中日期格式化仅做「格式 + 措辞」本地化，时区处理维持原链路；「先核对无时区时间约定」项标记为：已核对、存在混用、语义冻结（改动须另行立项，不属于本 feature）。

## 5. 生成契约链（高级搜索）

```
backend/app/contracts/advanced_search_contract.json   ← 唯一源（39 处中文：字段 label/操作符分组等）
        │  frontend/scripts/generate-advanced-search-contract.js
        ▼
frontend/src/contracts/advancedSearch.generated.ts     ← 生成产物（22 条中文），文件头 DO NOT EDIT
        │  import
        ▼
components/torrents/advancedSearchFields.ts            ← 展示字段装配（label/UI 文案）
```

**P3 规则**：字段/操作符/摘要的翻译改在 **json 源**（双语 label 结构，如 `label: {"zh-CN": "...", "en": "..."}`——具体形态 P3 定）→ 重新生成 → fields.ts 消费；**严禁直改 generated.ts**；`field/operator/value` 与生成契约版本（`ADVANCED_SEARCH_CONTRACT_VERSION=3`）语义不变（T01：同输入同参数）。若双语 label 改变 json 结构，需同步 bump 生成器与契约版本并回归 `npm run contract:check`。

## 6. 其余系统内容（M2 批次登记）

- `downloaders` 名称/标签/分类：用户数据，永不翻译（Q02）。
- 审计日志：字段/枚举翻译，历史 `detail` 自由文本不改写（logs/audit M2）。
- 定时任务类型标签（`types/scheduled-tasks.ts` 88 处）：常量映射按语言取值，M2 随 tasks 页。
- MoviePilot/MCP 设置面板文案：M2 随 P6（settings partial 拆分）。
