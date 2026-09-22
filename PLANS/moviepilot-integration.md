# MoviePilot 整理联动（BtDeckBridge）

> **状态**: 🚧 第一版闭环已落地（代码+自动化测试），真实宿主联调未执行
> **feature**: `moviepilot-integration-2026-09-09`
> **分支**: dev1.0.7
> **创建**: 2026-09-09

## 1. 目标与非目标

建立 **MoviePilot 整理关系 → BtDeck 只读镜像 → BT 任务关联** 的闭环，帮助用户识别并保留需要的媒体库文件、源数据与种子任务。

**非目标（后续迭代）**：保留标记、辅种识别、删除影响预览、文件名相似候选匹配（hash 缺失只标记 unassociated，不做候选推断）、事件触发同步（先周期+手动）。

## 2. 架构与关键决策

```
MoviePilot V2 + BtDeckBridge 插件                BtDeck
┌─────────────────────────────┐   HTTPS/令牌   ┌──────────────────────────────┐
│ sync_job(BackgroundScheduler│ ─────────────► │ /api/v1/moviepilot/handshake │
│  线程池, 同步函数)           │  BtDeck 用户   │ /api/v1/moviepilot/sync/…    │
│ adapter: 自调用宿主 API      │  令牌体系      │  (instance,historyId) 幂等    │
│  /api/v1/history/transfer   │                │  content_hash 判 skip/update  │
│ engine: 水位+断点+重试       │                │ 映射解析→bt_downloader_id     │
└─────────────────────────────┘                │ 关联查询: 正向/反向 join       │
                                               │  torrent_info(hash,dl)        │
                                               └──────────────────────────────┘
```

| 决策 | 结论 | 理由 |
|------|------|------|
| 插件凭据 | **复用 BtDeck 登录+刷新令牌**（专用集成账号） | 零新增认证面；刷新令牌 7 天轮换、插件自动续期，失效回退重登录 |
| 取数方式 | 插件**自调用 MoviePilot 宿主 API**（apikey 鉴权） | 版本隔离、不触 MP 数据库；V2 该端点 date 倒序分页、无 ID 范围查询 |
| 增量策略 | **水位 + 周期全量重扫 + 断点续跑** | 需求明确"不仅依赖最大历史 ID"：重整理/字段更新不改 id，只能全量重扫捕获 |
| 幂等身份 | `(instance_id, history_id)` 唯一 + 服务端算 content_hash | 信任边界：不信任客户端哈希；同内容 skip、变更 update |
| 关联模型 | 查询时按 `(bt_downloader_id, download_hash)` 精确 join；写入时按实例映射解析冗余列 | 同 hash 多下载器天然不串联；路径只存 MP 原值不做自动换算 |
| 实例身份 | 插件生成 UUID 持久化；BtDeck 首握手注册并绑定首个认证账号 | 防其他有效账号冒名写入；绑定账号失效允许改绑 |
| 全局开关 | configs 版本化键 `moviepilot.integration.v1`（默认关，fail-closed+CAS） | 照抄 mcp.runtime.v1 先例；集成面默认不开放 |
| 分发形态 | **已公开发布为独立仓库** [https://github.com/strainhzj/MoviePilot-Plugins-BtDeck](https://github.com/strainhzj/MoviePilot-Plugins-BtDeck)（2026-09-10，GPL-3.0）：市场安装=仓库地址加入 PLUGIN_MARKET（索引 raw main 分支，未声明 release 走文件列表安装）；本地开发联调仍可挂载仓库目录为 PLUGIN_LOCAL_REPO_PATHS | v2 源码实证：本地仓库=扫描 package.v2.json → 市场标"本地" → `install_local` 复制安装，无需 PLUGIN_MARKET；远程市场必须 GitHub 仓库（raw main 分支拉索引），`release` 字段仅是 Release 版本化安装能力位 |

## 3. 组件与文件

**BtDeck 后端**（纯新增 + 追加式注册）：
- 模型：`app/models/moviepilot_instance.py`、`moviepilot_transfer_history.py`
- 服务：`app/services/moviepilot_settings_service.py`（开关 CAS）、`moviepilot_integration_service.py`（握手/幂等同步/映射重解析/双向查询）
- 端点：`app/api/endpoints/moviepilot.py`（`/api/v1/moviepilot/*`；集成/管理面走 principal 内核依赖，查询面走 require_authenticated_user）
- 迁移：`alembic/versions/053003337878_add_moviepilot_integration_tables.py`（【可回滚】，head c1d2e3f4a5b6 → 053003337878，两表+索引）
- 审计枚举 +3：`moviepilot_settings_update / moviepilot_instance_update / moviepilot_sync`

**BtDeck 前端**：
- `api/moviepilot.ts`；`views/settings/components/MoviePilotPanel.vue`（开关 CAS/实例卡片/映射编辑/反查卡）+ 设置页签
- 种子详情卡「媒体库」页签：`detailTabsData.ts` media 分支 + `TrackerDetailCard.vue` 渲染 + 两视图传参

**插件**（独立仓库 `C:\software\claude_code_full_stack\MoviePilot-Plugins-BtDeck` = [https://github.com/strainhzj/MoviePilot-Plugins-BtDeck](https://github.com/strainhzj/MoviePilot-Plugins-BtDeck)，2026-09-10 自 BtDeck 仓库根 `moviepilot-plugin/` 拆出发布；也可挂载为 PLUGIN_LOCAL_REPO_PATHS）：
- `plugins.v2/btdeckbridge/{__init__.py, moviepilot_adapter.py, btdeck_client.py, sync.py}` + `package.v2.json` + `tests/`（38 项）

## 4. 协议 v1

同步条目字段（camelCase，对齐 MP TransferHistory）：`historyId, srcStorage/srcPath/srcFileitem, destStorage/destPath/destFileitem, transferMode, mediaType, title, year, seasons, episodes, tmdbId, doubanId, mediaSource, mediaId, mpDownloader, downloadHash, status, errmsg, recordedAt, files`；批量上限 200；`syncMode ∈ {full, incremental}`。

错误语义：全局关/实例禁用/绑定冲突 → 403；未握手实例 → 404；协议版本不符/载荷非法 → 400；CAS 冲突 → 409。

## 5. 测试证据（已执行）

- 后端：`tests/api/test_moviepilot_integration.py` 28 项（认证矩阵/幂等三态/映射重解析/多下载器不串联/反查前缀/审计/信封分页）；迁移链 upgrade→downgrade→upgrade 对称 + 空库 35 表 + 单 head；路由鉴权覆盖登记；相邻回归 tests/api+core+架构约束 1225 passed（19 失败=回收站 a2cb083 存量基线）；black/flake8/mypy 绿。
- 前端：moviepilot-panel.spec 8 项 + detail-tabs-data 新增 4 项（合 32 项含相邻）绿；typecheck/lint 绿（有意不跑 build，保护 demo dist）。
- 插件：38 项（客户端令牌轮换/脱敏纪律、引擎水位断点/幂等/停止、适配器映射、装配防重复）绿。

**未执行（不得宣称通过）**：真实 MoviePilot V2 宿主联调、真实下载器关联验证、Docker 形态端到端。

## 6. 待办（下一批）

1. **联调**（task .4，阻塞于用户部署信息）：MP V2 完整版本号、部署方式、插件目录挂载与 PLUGIN_LOCAL_REPO_PATHS/PLUGIN_AUTO_RELOAD 可行性、BtDeck 地址容器内可达性。插件安装走本地市场仓库通道（见 §2 分发形态决策），无需新建/发布任何仓库。
2. 保留标记/辅种识别/删除影响预览（关联数据齐备后的上层功能）。
3. 事件触发同步（MP TransferCompleted 事件 → 即时增量）。
4. 实例数据库重建（MP 重装后 id 空间重置）的实例轮换流程文档化。
5. ~~公开发布~~ **已完成**（2026-09-10 用户授权）：独立仓库已建并推送 main（ed828bb，package.v2.json 含 history v1.0.0，线上索引经 GitHub API 验证）；后续如需 Release 版本化安装，再补 `release: true` 与 `BtDeckBridge_v<版本>` tag 流程。

## 7. 坑位记录

- MP `plugins.v2` 目录名含点：宿主把该目录并入 `app.plugins.__path__` 后以 `app.plugins.<pid>` 导入；插件单测须还原该机制（见插件 tests/conftest.py），直接 `import plugins.v2.x` 不可行。
- BtDeck 登录/刷新信封 `data` 是**单元素数组**；刷新令牌使用即轮换（并发双刷新只有一个成功）。
- MP `/history/transfer` 无 ID 范围查询且按 date 倒序——增量只能页游走，全量重扫是正确性兜底而非优化。
- 本批曾对上会话未提交的 MCP W2 文件做两处最小修复（catalog.py 定义顺序 NameError、补 `spec_by_tool_name`），使 tests/mcp 从 4 失败恢复至 1 失败（剩余 `test_concurrent_snapshot_switch_never_tears` 为 W3 未竟工作，非本批引入）。
