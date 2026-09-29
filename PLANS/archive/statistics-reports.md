# 统计数据与报表（Statistics & Reports）

> **状态**：v4——已过两轮三路子代理独立审查 + 用户审批修订（2026-09-24）；v4 合入审批四项：在线标记改 is_online、采样基准改 DB 有效清单、backup tracker 保留行置 NULL、在线率口径改「采样期间」，待实施
> **工作分支**：`feature/reports`（worktree `/srv/workspaces/BtDeck-reports`，基于 dev@521b073）
> **实现清单**：`feature_list.json` 的 `statistics-reports-2026-09`（**W1 开工前先建目**；W7 仅补 evidence 与 status）
> **本文档为唯一实施依据，实现会话开始前须按根 AGENTS.md 启动工作流读完约束文档**

## 0. 决策记录（已拍板，不再复议）

| # | 决策 |
|---|---|
| 1 | 范围 = 正式报表 A1-A5、B6-B8、C10-C12、D14-D16（4 页签 13 项）+ 趣味报表 24/25/26/27 |
| 2 | 趣味报表为**独立沉浸式报告**（翻页卡片流），不与正式报表混排 |
| 3 | 接受引入 **echarts**（按需 + 懒加载，**精确钉版 `5.5.1`**，降级阶梯 5.4.1/5.3.3，W4 首步实测 TS 4.2 兼容后锁死） |
| 4 | 顶级菜单名 **「统计数据」**；子项：总览 / 趋势 / 做种 / Tracker / 趣味报告 |
| 5 | 速度时间采样**本期实施**（新表 + 采样任务，数据从上线起积累） |
| 6 | **tracker 计数字段本期激活**（v3 修正键名）：qB 取 trackers 负载 **`num_seeds/num_leeches/num_downloaded`**（第二轮三重证据实测：该负载中 num_* 即 scrape 群体计数，已连接数是 `num_peers`；`tracker_mapper.py:184-197` 文档注释语义标错，W2 顺手修正）；统一归一 **`-1/None → NULL`**（qB num_* 未知时为 -1 哨兵）；TR 取 `trackerStats` 三列，**backup 条目（`is_backup=True`）保留记录与 URL、仅三列计数置 NULL**（审批 P1-3：批量同步 Step4 会把本批缺失的 tracker 标 dr=1——torrents_async.py:960-972 元组 IN 语义，直接排除会误删现有展示与健康统计；陈旧计数不可信故置 NULL，也不压低火种 min 判定）。W2 首步打印真机负载复核键名 |
| 7 | **状态归并**（v3 修正落地方式）：先把 `torrent_stats_cache.py` 的三个方法内局部集合**提升为模块级常量**（`get_stats()` 行为不变，文件列入 W2）；**PAUSED_STATES 扩充含 `"paused"`**（TR stopped 映射后的 DB 值，当前缺它导致 TR 暂停种子落 other 桶——此变更连带修正 dashboard 统计，回归适配）；`queuedDL/checkingDL` 照常量归**下载桶**；**错误桶优先级最高**（`status='error' OR has_tracker_error` 先判，再归四主桶，与列表页筛选语义一致）；余下未覆盖值归"其他" |
| 8 | **TR added_date 时区写路径修复**（v3 修正）：用 **`_parse_qb_epoch(torrent_info.fields["addedDate"])`**（与 qB L2086 完全同构的 naive 本地，勿走 done_date aware 转换）；**两处写入路径都改**（全量 `~L1442` + info-only `~L3964`）；迁移②回填 **JOIN 去掉 `dr=0`**（软删下载器的 TR 存量行同样错位且无自愈路径） |
| 9 | **勋章阈值半开区间**：[0,1)TB 铜 / [1,10) 银 / [10,50) 金 / [50,200) 白金 / [200,∞) 钻（消除 v2 的 200-500 空档） |
| 10 | **沉浸层实现约束**：z-index **1200**（有效区间 1002-2000：>1001 盖 sidebar、<2001 不压 Element 弹层）；**根元素即覆盖层，禁止外包 wrapper**（fade-transform 的祖先 transform 会使 fixed 塌陷）；**状态走 route query 持久化**（`?mode=&year=&slide=`，全仓无 keep-alive，返回必重挂载）；W6 开工前 15 分钟对比 `el-drawer direction="btt" size="100%"` 替代方案（免费获得 z-index/滚动锁管理） |

**默认假设**（用户未另行指示）：
- 本期仅桌面 Web，移动端 `/m/` 不做统计页（守卫兜底跳 `/m/dashboard`，移动版另立项）。
- 首期不做 CSV/Excel 导出（另立项）。
- 双语 i18n parity 为强制门禁（项目既有要求）。

## 1. 范围

### 1.1 正式报表（4 页签）

| 页签 | 编号 | 报表 | 数据源 | 形态 |
|---|---|---|---|---|
| 总览 | A1 | 库存总览：总种子数/总体积/平均体积/**最大 TOP10**/回收站现占体积 | torrent_info | 数字卡 + 条形 |
| 总览 | A2 | 状态分布（**五桶**，判定顺序：错误桶优先 → 四主桶按提升后常量 → 其他，见决策 7） | status + has_tracker_error | 饼图 |
| 总览 | A3 | 分类与标签分布（数量 + 体积双维度；TR 无分类→"未分类"桶并脚注） | category / tags | 条形（双轴切换） |
| 总览 | A4 | 目录占用排行（save_path 根前缀聚合） | save_path | 条形 |
| 总览 | A5 | 下载器对比：种子数/体积/状态构成（含已移除下载器存量，LEFT JOIN 标注） | downloader_id | 堆叠柱 |
| 趋势 | B6 | 新增趋势：按月/周（**周桶 = `%Y-%W` Python 侧分桶**，SQLite strftime 无 ISO 周），种子数与体积；过滤 `added_date IS NULL` | added_date | 柱 + 折线 |
| 趋势 | B7 | 完成趋势（completed_date NULL 覆盖面大——做种态添加的种子恒空，脚注；TR 侧 done_date 经 venv astimezone 本地转换与 qB 同口径，W2 顺带实测确认） | completed_date | 柱 |
| 趋势 | B8 | 库龄结构：<7天/30/90/180/1年/更久/**未知**（added_date NULL 桶）体积占比 | added_date | 环形 |
| 趋势 | B9* | 速度历史曲线（上/下行，按下载器，24h/7d/30d） | 新采样表 | 折线（多系列） |
| 做种 | C10 | 分享率分布直方图：<0.5/0.5-1/1-2/2-5/5-10/10+（NULL ratio 排除并脚注——TR 做种态添加的种子 ratio 恒 NULL） | ratio | 柱 |
| 做种 | C11 | 摸鱼象限：**TOP20** 体积降序，过滤 `ratio<0.5 AND completed_date IS NOT NULL` | size × ratio | 散点 + 表 |
| 做种 | C12 | 辅种网络：辅种率、TOP10 辅种种子 | auxiliary_seed_count | 数字卡 + 条形 |
| Tracker | D14 | 站点构成：按 tracker_host 聚合（**报表侧去端口归一取 hostname**——qB 侧 host 含端口会分裂站点） | tracker_info JOIN | 条形 |
| Tracker | D15 | 站点健康榜：每站 error 率（**分母排除 `status='unknown'`**；tracker 行过滤 `dr=0`） | tracker_info.status | 表 + 进度条 |
| Tracker | D16 | 站点冷热：平均 seeder/leecher 比、平均 download_count（依赖决策 6；**均值排除 NULL 行，count=有效行数**） | seeder_count 等 | 散点 + 表 |

\* B9 冷启动见 §5。**断点语义脚注**：断点仅出现在后端停机时段；下载器离线是 0 速数据点而非断点（采样循环含离线行）。

### 1.2 趣味报表（独立沉浸页 `/statistics/fun-report`）

| 编号 | 卡片 | 内容 | 数据源 |
|---|---|---|---|
| 24 | 🔥 火种守护者 | 每种子取其 trackers 中**最小非 NULL** `seeder_count`；≤2 即"火种"；无任何非 NULL tracker 计数的种子排除；**激活前存量三列为 NULL，数据自激活日起积累**（脚注同 B9 冷启动） | tracker_info + torrent_info（依赖决策 6） |
| 25 | 🏅 上传量勋章 | 累计上传估算 `Σ(size × ratio)`（做种桶种子且 ratio 非 NULL；"做种桶"用决策 7 同一套桶定义；TR 做种态添加种子系统性缺位，脚注注明估算口径与覆盖面）→ 决策 9 半开区间勋章，附"相当于上传了 N 部电影" | torrent_info |
| 26 | 📅 种库年度报告 | Spotify Wrapped 式翻页卡（year 参数，默认今年）：开场卡 → 今年添加 N 种子/X TB → 最忙月份+最忙一天 → 体积占比最高站点 → 元老（最早添加仍在做种，含做种天数）→ 火种 → 上传估算 → 结尾卡。added_date NULL 行全部排除 | 同上 |
| 27 | ⚖️ 白嫖 vs 慈善榜 | ratio 最低 TOP10 vs 最高 TOP10，各附体积；NULL ratio 排除 | torrent_info |

趣味页结构：「战报」（24/25/27）+「年度报告」（26 翻页流，年份 2024–当前）。单页两子模式，状态走 route query（决策 10）。

### 1.3 非目标（本期不做）

- 移动端统计页、导出 CSV/Excel、通知集成、删除审计报表（E18/E22/E23）、同步健康报表、消息词云（D17）。
- 下载器延迟历史（只采速度与在线状态）。
- 彻底删除（dr=1）种子历史累计体积（A1 脚注说明"已彻底删除数据不在库存口径"）。

## 2. 架构与数据流

```
torrent_info / tracker_info / bt_downloaders (既有表)
        │                ▲ 决策6：同步写入激活 seeder/leecher/download 三列
        │                │   （行构造×3处 + upsert set_×2处，见 §3.3）
        │                ▲ 决策8：TR added_date 改 _parse_qb_epoch 同构本地时间（×2处）+ 回填迁移
        ▼                │
ReportService (app/services/report_service.py 扁平单文件，对齐既有惯例)
        │  ── 聚合 SQL/内存计算 ──▶ /reports/* 端点
        ▲
app.state.store.get_snapshot()  ──(仅总览页"实时速度"卡)──┘

app.state.store 快照 + bt_downloaders 有效清单 ──(每 60s)──▶ SpeedSamplerJob
        │                       （写库遵守 sync-db-write-governance：
        │                         db_write_scope() + 每轮 add_all 单次 commit）
        │                          │
        │          downloader_speed_sample (原始, 保留 14 天)
        │                          │ 每小时聚合 + 每日清理
        └─────────────────────────▶ downloader_speed_hourly (长期, 保留 730 天)
                                   │
                                   ▼
                     /reports/trends 的 B9 速度历史
```

关键约束遵守：
- **下载器连接管理**：采样任务只读 `app.state.store` 缓存快照（与 `DashboardStatsJob` 同模式），严禁新建下载器客户端。
- **sync-db-write-governance（强制）**：`db_write_scope()`（Semaphore(1) 写者串行化，默认启用）+ 批量单 commit；`SYNC_DB_COMMIT_BATCH_SIZE=200` 对每轮下载器数（≪200）天然满足；append-only 时序数据不触发 2.1 变更检测条款（测试内注明理由防误判）；`test_speed_sampler.py` 参照 `test_heavy_task_db_write_governance.py:35-60` 的 `_ScopeSpy` 模式断言。
- **响应格式**：全部 `CommonResponse`；聚合端点不分页，凡需分页处严格 `list/total/pageSize`。
- **迁移**：两个迁移，`down_revision` 链 `a1f7c9e3d2b4 → b7d8e9f0a1c2 → c9e0f1a2b3c4`（两轮实测确认当前单 HEAD）。

## 3. 后端设计

### 3.1 数据库迁移（两个，W1/W2 各一）

**迁移 ① `b7d8e9f0a1c2_speed_samples.py`**（down_revision=`a1f7c9e3d2b4`）：

```python
class DownloaderSpeedSample(Base):      # backend/app/models/speed_sample.py
    __tablename__ = "downloader_speed_sample"
    id / downloader_id / sampled_at (联合 idx_speed_sample_dl_time)
    download_speed / upload_speed: int  # bytes/s（缓存 KB/s × 1024，对齐 dashboard_service 写法）
    online: bool    # 取缓存对象 is_online 标记（downloader_status_polling_task 经
                    # _set_online_status 维护，initialization.py:1560-1572）；
                    # fail_time 为过时字段——断网时可能仍为 0，禁止作为采样依据（审批 P1-1）

class DownloaderSpeedHourly(Base):
    __tablename__ = "downloader_speed_hourly"
    id / downloader_id / stat_hour(整点截断, 联合唯一 uq_speed_hourly_dl_hour)
    avg_dl / max_dl / avg_ul / max_ul: int   # avg 分母 = online_count（在线期间均值）
    sample_count / online_count: int          # onlineRatio = online_count/sample_count
```

**迁移 ② `c9e0f1a2b3c4_normalize_tr_added_date.py`**（down_revision=`b7d8e9f0a1c2`）：
- 定位：`JOIN bt_downloaders ON downloader_id WHERE downloader_type=1 AND added_date IS NOT NULL`——**不带 `dr=0`**（软删下载器的 TR 存量行同样错位且无自愈路径；downloader_id 是 UUID 主键无复用风险；torrent_info 侧不过滤 deleted_at——回收站行同样需要回填）。
- **三段式结构**（单条 JOIN UPDATE 做不了 Python 侧转换，仓内亦无先例）：SELECT JOIN 取 `(info_id, downloader_id, added_date)` → Python `stored.replace(tzinfo=utc).astimezone().replace(tzinfo=None)` → 按复合 PK 批量 UPDATE。
- 容错与警示：参照 `a1f7c9e3d2b4` 惯例 `inspect(op.get_bind()).get_table_names()` 存在性守卫；文件尾"不可重复执行（二次偏移）"警示；downgrade 反向偏移；DST 历史偏移按当前时区近似（CN 无 DST）；TZ=UTC 部署下为无害 no-op。

**迁移连带维护（实测锚点，缺一即 CI 红）**：
- `tests/core/test_db_migration.py:210,809` 表数 `== 35` → `37`（两处）+ `:191` docstring。
- `docs/constraints/database-migration.md` HEAD 声明两处字面量（`:65` `← 当前 HEAD` 行、`:77` `必须输出且只输出` 行）替换为 `c9e0f1a2b3c4` + 链尾注释块（`test_db_migration.py:44-63`）。
- `alembic/env.py` 模型 import 补 `speed_sample`；`app/models/__init__.py` 导出。
- `tests/core/test_db_migration.py` EXPECTED_HEAD 前移两步。
- `tests/core/test_startup_migration_guard.py:52-58` android monkeypatch 名单补采样循环函数名（否则 android lifespan 测试真启动采样循环）。
- 已排查 `tests/core/alembic_head.py` 为动态读取，无隐藏锚点。

### 3.2 采样任务 `backend/app/tasks/scheduler/speed_sampler.py`

仿 `DashboardStatsJob`（`lifecycle.py:106-121` 注册 + `:535-536` 创建 + `:655-670` 取消清理，新循环三处都要动）：

- **采样循环（60s）**：**以 DB 有效下载器清单为基准**（`bt_downloaders WHERE enabled=1 AND dr=0`），与 `store.get_snapshot()` 按 downloader_id 对齐——在缓存且 `is_online=True` → 记实时速度 `online=1`；不在缓存（含被 `downloader_cache_sync` 剔除者：`_OFFLINE_EVICT_SECONDS=300s`，downloader_cache_sync.py:16/207-230）或 `is_online=False` → **仍记 `online=0, 速度 0` 行**（审批 P1-2：仅遍历缓存在下载器被剔除后会断线，违背离线记零承诺；缓存缺失≠已删除，恢复在线自动回缓存）。全部行 `add_all` **单次 commit**；commit 包 `db_write_scope()`；异常仅 log 不中断。
- **聚合循环（每 5min 检查）**：对"已完整结束且 hourly 不存在该 `(downloader_id, hour)`"的分组聚合（AVG 分母=online_count、MAX、COUNT），INSERT OR IGNORE 幂等。
- **清理（每日）**：raw `< now-14d`；hourly `< now-730d`。
- 下载器删除后历史行保留（LEFT JOIN `bt_downloaders` 取昵称，取不到回退 `downloader_id` 标"已移除"）。
- 体量：每下载器 1440 行/天，14 天 ≈ 2 万行；SQLite WAL 无压力。

### 3.3 数据激活与口径修复（W2，决策 6/7/8 落地）

| 项 | 改动点（v3 全量锚点） |
|---|---|
| **W2 首步** | 打印真机 qB trackers 负载复核键名（预期 `num_seeds/num_leeches/num_downloaded/num_peers/msg`，以实测为准）；顺带实测 TR `done_date` 落库口径（venv 证据为本地转换，若有出入同批修复） |
| tracker 计数·行构造 ×3 | ① `sync_add_tracker_async`（`torrents_async.py:1017-1073`，qB+TR 两分支）；② **`extract_tracker_rows_from_torrent`（`:733-827`，tracker-only 批量同步唯一行源，漏改则增量路径三列不落）**；③ 遗留 `torrent_sync.py:621-700`（`_legacy_full_sync_impl` 外无调用方，**不改但在代码注释声明**） |
| tracker 计数·upsert set_ ×2 | ① batch 路径 `sync_trackers_batch_async`（`:935-948`）；② **`sync_add_tracker_async` 自带 set_（`:1140-1153`，漏改则全量同步 update 场景不落）** |
| 计数取值与归一 | qB ← trackers 负载 `num_seeds/num_leeches/num_downloaded`；TR ← `trackerStats` 同名属性（venv `torrent.py:156/220/240`），**`is_backup=True` 条目保留行与 URL、仅三列计数置 NULL**（防 Step4 批量 mark_removed 误删，见决策 6）；统一归一函数 `-1/None → NULL`，正值原样 |
| 变更检测白名单 | `sync_db_write.py:124-131` `_TRACKER_CHANGE_FIELDS` **代码元组**补三列（`:122-123` 注释同步改）；存量 NULL→值 即判变更，**一个同步周期自动回填**（qB 受游标/预算限制可能多周期） |
| TR added_date 本地化 ×2 | 全量 `:1442` 与 info-only `:3964` 都改为 `_parse_qb_epoch(torrent_info.fields["addedDate"])`（naive 本地，与 qB `:2086-2087` 完全同构） |
| 状态常量提升 | `torrent_stats_cache.py:141-160` 三个方法内局部集合 → **模块级常量**（`get_stats()` 引用之，行为除下项外不变）；**PAUSED_STATES 扩充 `"paused"`**（TR 映射值）——连带修正 dashboard 暂停计数，相关回归测试适配 |
| 文档注释修正 | `tracker_mapper.py:184-197` qB tracker dict 语义标注纠错（num_* 为 scrape 群体计数，已连接数是 num_peers） |

### 3.4 报表服务 `backend/app/services/report_service.py`（扁平单文件）

模块内分区：overview / trends / seeding / tracker_stats / fun / 常量（蓝光 40GB、高清电影 8GB、剧集一季 30GB；勋章阈值见决策 9）。

- 种子口径 `dr=0 AND deleted_at IS NULL`；回收站 `deleted_at IS NOT NULL AND dr=0`；tracker 行口径 `tracker_info.dr=0`。
- B6/B7/年度报告 SQL 过滤时间列 NULL；B8 增"未知"桶。
- `tags` 逗号串、`save_path` 根前缀：万级行 Python 内存聚合（超 5 万行预案 json_each）。
- 复用：前端 `utils/formatters.ts`（`formatFileSize`/`formatSpeed` 实测存在）；速度换算对齐 `dashboard_service.py` 写法。
- 口径脚注集中 i18n（`statistics.calibers.*`），含"时间口径随部署时区（Docker 默认 TZ=UTC 时无偏移）"。

### 3.5 API 端点 `backend/app/api/endpoints/reports.py`

注册：`api.py` → `include_router(reports.router, prefix="/reports", tags=["reports"])`；鉴权全部 `Depends(get_current_user)`。

| 端点 | 参数 | 返回 data（摘要，v3 补全缺口） |
|---|---|---|
| `GET /reports/overview` | — | `totals{count,sizeBytes,avgSizeBytes,recycleBinSizeBytes}`、**`largest[]{hash,name,sizeBytes}`（TOP10）**、`statusDist[]{bucket,count,sizeBytes}`（五桶）、`categories[]`、`tags[]`、`paths[]`、`downloaders[]{downloaderId,nickname,type,removed,count,sizeBytes,statusDist}`、`liveSpeed{...}` |
| `GET /reports/trends` | `period=month\|week`, `limit=12` | `added[]`、`completed[]`、`ageBuckets[]`、`speedHistory{...}`（默认 24h） |
| `GET /reports/seeding` | — | `ratioBuckets[]`、`ratioNullCount`、`slackers[]{...}`（**TOP20**）、`auxiliary{...}` |
| `GET /reports/trackers` | — | `sites[]{host,count,sizeBytes}`（去端口，D14）；**`health[]{host,errorRate,affectedCount}`（D15，errorRate 分母排除 unknown）**；`supplyDemand[]{host,avgSeeders,avgLeechers,avgDownloads,count}`（D16，均值排除 NULL、count=有效行数） |
| `GET /reports/fun/summary` | — | `guardian{...}`、`badges{...}`、`shame[]`、`pride[]` |
| `GET /reports/fun/yearly` | `year=YYYY` | 见 §1.2 编号 26 |
| `GET /reports/speed/history` | `range=24h\|7d\|30d`, `downloaderId?` | 同 trends.speedHistory |

空数据语义：聚合返回空数组/零值；速度历史无样本时 `series=[]` + `samplingActive:true, firstSampleAt:null`。

## 4. 前端设计

### 4.1 图表基建 `src/components/charts/EChart.vue`

- **Options API 约束**：class 风格（`@Component`，与 query-templates 同款）；禁 Composition API/script setup。
- Props：`option`、`height`、`loading`。**echarts 精确钉版 `5.5.1`**（caret 会漂移到 5.6.x，与"W4 实测通过的版本"失锚）。
- **类型策略（TS 4.2 + 门禁盲区）**：`types/reports.ts` **禁止 import echarts 类型**（纯 JSON 契约形状，避免把 echarts d.ts 拖进 tsc 解析面）；EChart.vue 内如需 echarts 类型，**只允许整句 `import type { X } from 'echarts/core'`**（TS 3.8+ 语法），**明令禁止 inline `import { type X }`**（TS 4.5+ 才支持，4.2 直接解析失败）。注意 fork-ts-checker `vue.enabled=false` + tsc 不编译 .vue——SFC 内类型不进 CI，契约类型全放 .ts。
- echarts 按需 + 懒加载：`echarts/core` + Bar/Line/Pie/Scatter + Grid/Tooltip/Legend/DataZoom/Title + CanvasRenderer，全部动态 import **且每处带相同 `/* webpackChunkName: "echarts" */`**。
- 竞态：import 完成后若 option 已就绪立即 setOption；父组件传新对象引用，watch 浅比较。
- 生命周期：mounted init → `ResizeObserver` → `setOption(new, {notMerge:true})` → beforeDestroy dispose + disconnect。
- 空态插槽：无数据占位。

### 4.2 路由与菜单

```
/statistics (Layout, redirect → overview, meta: { titleKey: 'navigation.routes.statisticsGroup',
             icon: 'bar-chart-3' })   ← 父级组图标拍板：与 overview 复用，已注册
  ├─ overview    总览    bar-chart-3   （已注册）
  ├─ trends      趋势    trending-up   （已注册）
  ├─ seeding     做种    sprout        （需注册；lucide 无 seedling，备选 leaf；W4 实测）
  ├─ trackers    Tracker radar        （需注册；备选 orbit/gauge——均已注册零成本）
  └─ fun-report  趣味报告 sparkles    （已注册）
```

- **图标注册**：`src/components/common/LucideIcon.vue` 具名 import + `ICONS` 表补条目（不存在 entry.ts）。
- **移动端守卫真拦截点**：`src/permission.ts:31-57` `uiModeRedirectPath()` 加 `to.path === '/statistics' || to.path.startsWith('/statistics/')`；`utils/ui-mode.ts toMobilePath()` 同步加映射（保持文件内注释同步惯例）。
- 懒加载 `webpackChunkName` 照 router.ts 惯例；`demo/types.ts:481 DEMO_ROUTE_MATRIX` 补 5 行（照 demo-config.spec `.some()` 断言先例补 category 断言）。
- **沉浸式**：按决策 10（fixed 覆盖层 / z-index 1200 / 根元素即覆盖层 / route query 状态）；W6 开工前 15 分钟对比 `el-drawer btt 100%` 方案后定稿。

### 4.3 页面结构 `src/views/statistics/`

```
statistics/
  overview/index.vue      数字卡行 + 五桶饼图 + 条形×3 + 实时速度卡（30s 轮询 +
                          beforeDestroy 清理，照 dashboard/index.vue:380-389 惯例）
  trends/index.vue        period 切换 + B6/B7 组合图 + B8 环形 + B9 速度曲线(range 切换)
  seeding/index.vue       C10 柱 + C11 散点+表 + C12 卡+条
  trackers/index.vue      D14 条形 + D15 表 + D16 散点+表 + 口径脚注区
  fun-report/index.vue    沉浸翻页流（决策 10 约束）
  components/             StatCard.vue、CaliberNotes.vue（W5 前 created，四页签共用）
                          FunSlide.vue、YearPicker.vue（W6，fun-report 专属）
```

### 4.4 API 模块与类型

- 契约类型 `src/types/reports.ts`（纯 JSON 形状，禁 echarts 类型 import）；`src/api/reports.ts` 照 `dashboard.ts` 惯例（信封 `{status,msg,code,data}`，页面按 `res.code === '200' && res.data` 消费）。
- `demo/types.ts` 从 `@/types/reports` 复用（`@/` 别名三处齐备：jest moduleNameMapper/tsconfig paths/vue-cli 默认，实测可行；demo 引入后间接触达该模块属预期）。

### 4.5 i18n（强制双语）

- 新包 `zh-CN/statistics.ts` + `en/statistics.ts`；`navigation.ts` **6 键 ×2**（`statisticsGroup` + 5 子键，照 `torrentsGroup` 惯例）。
- **聚合根接线**：`zh-CN/index.ts` 与 `en/index.ts` 两处 import + messages 挂载。
- 门禁语义（v3 纠正）：`i18n-message-parity` 是全树键集硬对比——**单侧漏挂会大声失败**；真正静默的是**双侧漏挂/漏建包**，W4 自查清单必须含"两聚合根对照挂载"。
- `i18n-leftover-guard`：statistics 视图默认入扫描，趣味道文案全走 i18n 键（`src/demo` 在排除清单内）。

### 4.6 Demo 层

- `demo/fixtures/`：`DEMO_REPORT_*`（含空态与多数据形态；速度历史 24h 假曲线）。
- `demo-request.ts`：`/reports/*` 7 个 GET 分支（照 `:490` 先例，query 经 `readInput`）。
- `demo-store.ts` getter：能推导的从 DEMO 种子推导，推导不了的静态 fixture 注明。
- demo 模式下趣味报告完整翻页可演示。

## 5. 速度采样冷启动

- 部署后 B9 空态："采样已于 X 启动"（`samplingActive` + `firstSampleAt`）。
- 拼接（服务端封装）：定位 hourly 最大 `stat_hour` H → raw 取 `sampled_at >= H+1h`；hourly 无行 → raw 全窗口；24h 内纯 raw，更长窗口 hourly 主体。
- **断点语义**：断点仅后端停机时段（该小时无样本 → 分组不存在 → 曲线 breakLine 不补 0）；下载器离线 = 0 速数据点；下载器增删 = 序列起止边界，均属预期。
- 口径（审批 P2-4 修订）：`avg_*` = 在线样本均值（分母 online_count；**online_count=0 的小时输出 0**，行携带 sample_count/online_count 供前端区分“全离线小时”与“停机无行”）；`onlineRatio` = online_count/sample_count，语义为**「采样期间在线率」**（后端停机时段无样本、属断点，不参与比率——非“含停机”）；tooltip 与脚注按此表述。
- **tracker 计数冷启动同款**：决策 6 激活后存量 NULL 在同步周期内自动回填，D16/趣味 24 页脚注"数据自激活日起积累"。

## 6. 测试计划

### 后端（pytest）

| 文件 | 覆盖 |
|---|---|
| `tests/api/test_reports_overview.py` | A1-A5 五桶归并（错误桶优先级断言：seeding+has_tracker_error 落错误桶）、largest TOP10、回收站条件、tags/save_path、孤儿下载器标注、空库、401；fixture 仿 `test_dashboard_api.py`（dependency_overrides + app.state 注入） |
| `tests/api/test_reports_trends.py` | 月桶边界、周桶 `%Y-%W` Python 分桶、NULL 过滤、未知桶、B9 拼接缝（含整点后无样本断点）、**onlineRatio「采样期间」语义 + online_count=0 时 avg=0 输出** |
| `tests/api/test_reports_seeding.py` | ratio 分桶、NULL 计数、slackers（ratio<0.5 AND completed_date 非空，TOP20）、辅种率 |
| `tests/api/test_reports_trackers.py` | host 去端口、dr=0 过滤、errorRate 排除 unknown、supplyDemand 均值排除 NULL/-1 |
| `tests/api/test_reports_fun.py` | 勋章半开区间边界（1/10/50/200 断点两侧）、蓝光换算、火种 min 非 NULL + 全 NULL 排除 + **-1 不误判火种**、上传估算 NULL 剔除、年度 NULL 排除 |
| `tests/tasks/test_speed_sampler.py` | 采样插入（含离线行）、**DB 基准清单对齐：下载器被 300s 剔除缓存后仍持续记零（断网采样）、is_online 判定不受 fail_time 残留值影响**、**db_write_scope _ScopeSpy 断言**、单轮单 commit、聚合幂等、清理（含 online_count=0 → avg=0）、store 缺失 skip；注明 append-only 不适用 2.1 变更检测的理由 |
| `tests/core/test_db_migration.py` | EXPECTED_HEAD 前移、表数 37 两处、迁移②三段式回填（**软删下载器行也回填**、UTC→本地单向、downgrade 反向、inspect 守卫） |
| `tests/`（既有扩展） | 决策 6：qB 断言 **num_*** 键 + -1→NULL、TR trackerStats 三列 + **is_backup 保留行置 NULL、主备切换回归（backup↔primary 角色互换后 URL 不被 Step4 标 dr=1、计数按新角色取值）**、三处行构造/两处 set_ 全覆盖、白名单翻转后存量回填收敛；决策 7：常量提升回归 + **dashboard TR paused 计数变化适配**；决策 8：TR 两条路径 added_date 本地化断言；`test_startup_migration_guard.py` android 名单 |

### 前端（Jest）

- `jest.config.js:23`：改为 **`'<rootDir>/node_modules/(?!lucide|echarts)'`**（保留 `<rootDir>/node_modules/` 锚定——照字面 `/(?!lucide|echarts)/` 替换会灾难性破坏全项目转译；如遇 zrender 意外防御性扩 `(?!lucide|echarts|zrender)`）。
- `views/statistics/__tests__/`：4 页签渲染（mock `@/api/reports`）+ 空态 + period/range 切换。
- `components/charts/__tests__/EChart.spec.ts`：mock echarts + **stub ResizeObserver**，验证生命周期与 import 竞态。
- `fun-report`：翻页/子模式/年份交互、**route query 状态恢复**（重挂载后进度不丢）、覆盖层 z-index 断言（盖 navbar 1000/sidebar 1001，不盖 Element Message ≥2001）。
- `permission` 守卫回归：mobile 模式 `/statistics*` → `/m/dashboard`。
- `demo-request.spec.ts`：/reports/* 分支。

### 门禁

后端 mypy/black/flake8 + 全量 pytest；前端 typecheck + lint --max-warnings 0 + 全量 Jest + build（echarts 单一 chunk，gz <200KB）；根 `./init.sh` 退出码 0。

## 7. 实施波次（feature_list 条目 W1 开工前建目）

| 波次 | 内容 | 主要文件 |
|---|---|---|
| W1 采样数据层 | 速度两表 + 迁移① + SpeedSamplerJob（治理合规）+ 注册（含 android 守卫名单）+ 全部锚点维护 + 测试 | `models/speed_sample.py`、`alembic/versions/b7d8e9f0a1c2_*.py`、`tasks/scheduler/speed_sampler.py`、`startup/lifecycle.py`、`alembic/env.py`、`models/__init__.py`、`docs/constraints/database-migration.md`、`tests/core/{test_db_migration,test_startup_migration_guard}.py`、`tests/tasks/test_speed_sampler.py` |
| W2 数据激活与口径修复 | **首步实测 qB 负载键名 + TR done_date 口径**；tracker 计数（行构造×3 + set_×2 + 归一 + backup 保留行、三列计数置 NULL + 白名单）；TR added_date ×2 路径本地化 + 迁移②；状态常量提升 + PAUSED 扩充 + dashboard 回归适配；mapper 文档纠错 | `api/endpoints/torrents_async.py`、`services/sync_db_write.py`、`downloader/torrent_stats_cache.py`、`alembic/versions/c9e0f1a2b3c4_*.py`、`core/tracker_mapper.py`、`api/endpoints/torrent_sync.py`（仅注释声明）、`tests/` |
| W3 报表服务与端点 | report_service（含 host 去端口归一、五桶判定、勋章半开区间）+ reports.py + 注册 + 测试 | `services/report_service.py`、`api/endpoints/reports.py`、`api/api.py`、`tests/api/test_reports_*.py` |
| W4 前端基建 | echarts **5.5.1** 钉版 + TS 4.2 实测；EChart 封装；**路由/菜单/i18n 变更与 W5 首个提交同批合入**（或 W4 只交依赖/EChart/i18n 文件、路由放 W5，避免侧栏指向不存在组件）；types/reports.ts + api/reports.ts + jest.config 豁免 | `package.json`、`components/charts/EChart.vue`、`router.ts`、`permission.ts`、`utils/ui-mode.ts`、`components/common/LucideIcon.vue`、`i18n/locales/{zh-CN,en}/{statistics.ts,index.ts,navigation.ts}`、`types/reports.ts`、`api/reports.ts`、`jest.config.js` |
| W5 四个正式页签 | 四页 + **components/（StatCard/CaliberNotes 先行创建）** + 测试 | `views/statistics/{overview,trends,seeding,trackers}/`、`views/statistics/components/` |
| W6 趣味报告 | el-drawer vs fixed 对比实测定稿 + fun-report（query 持久化 + z-index）+ FunSlide/YearPicker + 测试 | `views/statistics/fun-report/`、`views/statistics/components/` |
| W7 Demo 与收口 | demo 四件套 + 全量验证 + 文档同步 + **补 evidence 与 status** | `demo/*`、roadmap、feature_list.json、progress.md、session-handoff.md、PLANS/README.md |

W1/W2 最先合入；W3-W6 可并行（W4 路由与 W5 合批约束见上）。

## 8. 完成定义（DoD）

- [ ] §1.1/§1.2 全部报表可视且数据正确
- [ ] qB 真机负载键名实测记录在案（W2 首步），三列双路同步落库且**存量回填完成**（含 batch/add 两路、-1/None→NULL、is_backup 保留行置 NULL、主备切换回归）
- [ ] TR added_date 两条写入路径均本地时间、历史行（含软删下载器）已回填
- [ ] 状态常量已提升模块级、TR paused 归暂停桶、dashboard 回归适配通过
- [ ] 采样任务稳定运行（DB 基准清单、离线持续记零、is_online 判定、raw/hourly、聚合幂等、清理、db_write_scope 合规）
- [ ] 后端 mypy/black/flake8 净 + 全量 pytest（锚点 37、约束文档 HEAD、android 守卫名单）
- [ ] 前端 typecheck/lint/build；echarts 单一 chunk gz <200KB；jest 豁免正则保留锚定
- [ ] i18n 双语成对（6 键 + 包 + 两聚合根对照自查）
- [ ] demo 模式统计页与趣味报告完整可演示；fun-report query 状态恢复 + z-index 断言通过
- [ ] 移动端守卫回归（/statistics* → /m/dashboard）
- [ ] roadmap、feature_list（evidence）、progress、session-handoff 同步；`./init.sh` 退出码 0

## 9. 风险与对策

| 风险 | 对策 |
|---|---|
| qB 负载键名与桩证据不符（真机版本差异） | W2 首步打印实测，以真机为准修正映射并记录 |
| PAUSED_STATES 扩充改变 dashboard 统计口径 | 有意为之的修正（TR 暂停种子原落 other）；回归测试同步适配，进度记录说明 |
| tags/save_path 内存聚合超大库变慢 | 首期接受；预留 json_each 优化 |
| ratio×size 估算偏差 + TR NULL 缺位 | 仅趣味报表；脚注注明 |
| D14 辅种跨站重复计体积 | CaliberNotes 脚注 |
| echarts 体积失控 | 按需 + 统一 chunk 名 + build 门禁 |
| TS 4.2 与 echarts d.ts 不兼容 | 钉 5.5.1 + W4 实测；降级阶梯 5.4.1/5.3.3；SFC 类型不进 CI（契约类型全放 .ts） |
| `sprout`/`radar` 在 lucide@1.27 缺失 | W4 实测；备选 leaf、**orbit/gauge（已注册零成本）**；seedling 非法名已剔除 |
| fun-report 过渡期 fixed 塌陷 | 决策 10 明令根元素即覆盖层禁 wrapper；W6 测试断言 |
| TR added_date 回填不可重复执行 | alembic 单次执行语义 + 注释警示 + downgrade 反向 + inspect 守卫 |
| tracker 计数激活增加同步写入量 | 并入既有 upsert 批量路径无新增 commit；白名单防抖 |
| Docker TZ=UTC 与桌面本地时区行为差异 | 回填 no-op 自洽；CaliberNotes 注明时间口径随部署时区 |
| 与主工作区 RSS（未提交）迁移链冲突 | 无表交集；合并时按拓扑重挂 |

## 10. 后续展望（不在本期）

移动端统计页、CSV 导出、同步健康报表、tracker 消息词云（D17）、精确上传量（qB session stats 持久化）、删除/转移审计报表（E18/E22/E23）；审查发现候选：删除入库趋势、接近 `ratio_limit` 清单、完成耗时分布、僵尸下载清单、跨下载器冗余体积、错误原因分布下钻。
