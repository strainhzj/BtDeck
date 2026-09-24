# 下载器 RSS 订阅（BtDeck 引擎 Phase 1）

> **feature**: `rss-subscription-2026-09-24`
> **状态**: ✅ Phase 1 已交付（2026-09-24；代码+测试+文档全绿，待真实 qB/TR 联调与 Git 提交）；Phase 2 未启动
> **登记**: 2026-09-24（用户确认两决策：feedparser 依赖 + 添加参数含保存路径/标签；后期支持按类型选择推送下载器）

## 背景与目标

为下载器新增 RSS 订阅功能，最终形态双模式并存：

- **BtDeck 模式**：BtDeck 自建订阅引擎（抓取/文章列表/推送下载），qB/TR 均可用；qB 也可选择此模式。
- **qB 原生模式**（Phase 2）：代理管理 qBittorrent 自身 RSS 源与下载规则，按下载器二选一。

**Phase 1 = 最简 RSS 订阅（本文档范围）**：
- 订阅源管理（CRUD + 手动刷新）；
- 文章浏览（分页）；
- 手动推送文章到下载器（支持保存路径/标签参数，可选目标下载器覆盖——为 Phase 2 按类型路由预留）。

不做（后续阶段）：自动下载规则、定时刷新调度、qB 原生代理与模式切换、HTML 页面链接解析（仅 magnet 与直链 .torrent URL）、按类型选择推送下载器。

## 关键决策

| 决策 | 结论 |
|---|---|
| RSS/Atom 解析 | 新增 `feedparser` 依赖（用户确认 2026-09-24）；httpx 抓取（已在依赖内） |
| 推送方式 | 链接直传下载器（qB `torrents_add(urls=)` / TR `add_torrent(torrent=link)`，两者原生支持 magnet+URL）；不服务端下载 .torrent；不即时写 torrent_info（依赖既有周期同步） |
| 添加参数 | save_path + tags（qB=tags / TR=labels）；请求可带 `downloaderId` 覆盖（默认订阅源绑定下载器） |
| 入口 | 下载器设置弹窗新增 `rssSubscription` 页签（type 0/1 显示；rTorrent 待适配后放开） |
| 移动端 | 复用弹窗自动受益 + ≤780 适配验证与专项测试 |

## 后端设计

- **模型** `app/models/rss_subscription.py`：`bt_rss_feeds`（feed_id UUID PK / downloader_id / name / url / enabled / last_fetch_at / last_fetch_status(never·ok·failed) / last_error / created_at / updated_at / dr）+ `bt_rss_articles`（article_id UUID PK / feed_id / guid / title / link / published_at / fetched_at / status(pending·added) / added_at / added_downloader_id / created_at，UNIQUE(feed_id,guid)）。
- **迁移**：Alembic 单迁移新增两表（head: a1f7c9e3d2b4 →）。
- **服务** `app/services/rss_feed_service.py`：
  - feed CRUD（软删）、refresh（httpx 超时 15s + 响应 ≤2MB + feedparser 解析 + guid 去重入库）、分页文章查询；
  - add_article：store 缓存客户端校验（fail_time 门控）→ `call_downloader_api(INTERACTIVE)` 链接添加 → 文章置 added；审计（best-effort）。
- **端点** `app/api/endpoints/rss_subscriptions.py`（`/api/v1/rss`）：
  - `GET /feeds?downloaderId&page&pageSize`、`POST /feeds`、`PUT /feeds/{id}`、`DELETE /feeds/{id}`、`POST /feeds/{id}/refresh`、`GET /feeds/{id}/articles`、`POST /articles/{id}/add`；
  - 统一响应（分页 `list/total/pageSize`）、失败路径 `data.reasonCode`（`RSS_*` 固定 msg，动态 str(e) 只进日志）；
  - android-server 伴侣形态跳过外网抓取（对齐既有门控惯例）。
- **审计**：`AuditOperationType` 新增 RSS_FEED_ADD/UPDATE/DELETE/REFRESH、RSS_ARTICLE_ADD。
- **测试**：`tests/api/test_rss_subscriptions.py` + 服务级解析 fixture 测试。

## 前端设计

- **API** `src/api/rss.ts`（类型 + 七接口）；demo 模式同形分支（demo-request/demo-store/fixtures 惯例）。
- **组件** `views/downloader/components/RssSubscriptionTab.vue`：订阅源表格（名称/URL/状态/最近抓取/待添加数 + 编辑/刷新/删除）+ 添加源弹窗 + 文章抽屉（分页列表 + 添加参数（保存路径/标签/目标下载器）+ 推送按钮，已添加态置灰）。
- **弹窗**：`DownloaderSettingsDialog.vue` 新增页签 `rssSubscription`（rss 图标；`!isEdit` 锁定态对齐其他页签）。
- **i18n**：`downloader.rss` 子树 + `downloader.tabs.rss*` zh/en 成对；`errors.byCode` 扩 `RSS_*`。
- **测试**：Jest（组件渲染/交互、api 模块、demo 分支、≤780 移动布局）。

## 验收

- 后端：mypy/black/flake8 + 相关 pytest 通过；迁移 upgrade/downgrade 对称可回滚。
- 前端：typecheck/lint/build + Jest 通过；zh/en 双语成对（i18n 门禁）。
- 仓库：`./init.sh` 通过；真实 qB/TR 手动联调（种子可添加、文章去重、刷新状态正确）。

## 后续阶段（不在本期）

Phase 2：qB 原生 RSS 代理（源/规则/偏好）+ 按下载器模式切换 + 自动下载规则 + 定时刷新调度 + 按类型选择推送下载器。

## Phase 1 实施记录（2026-09-24）

- **依赖**：feedparser==6.0.14（+传递 feedparser-sgmllib==2.1.0）入 requirements.txt 与 requirements-lock.txt（哈希手锁，check_dependencies PASS）。
- **数据层**：`models/rss_subscription.py`（RssFeed/RssArticle）+ 迁移 `8fabba8687b0`（head a1f7c9e3d2b4→8fabba8687b0；has_table 幂等守卫对齐 moviepilot 惯例；downgrade 对称 drop）。约束文档 HEAD 声明与 test_db_migration EXPECTED_HEAD 同步；表计数 35→37；hash 迁移 head 断言改「继任链 down_revision 挂载」语义。
- **服务**：`services/rss_feed_service.py`——CRUD（同下载器 URL 去重）/refresh（httpx 15s+2MB+feedparser，bittorrent enclosure 优先取链）/分页/add_article_to_downloader（store 缓存客户端 + INTERACTIVE lane；qB `torrents_add(urls=)` 校验 "Ok."、TR `add_torrent(torrent=link)`（重复返回 None 按成功）；成功置 added 不即时写 torrent_info，依赖周期同步）。
- **端点**：`api/endpoints/rss_subscriptions.py`（`/api/v1/rss`：feeds CRUD/refresh/articles 分页/文章推送）；RSS_* reasonCode 25 键；审计 RSS_FEED_ADD/UPDATE/DELETE/REFRESH + RSS_ARTICLE_ADD（best-effort，AsyncSessionLocal）；android-server 拒写；请求体 camelCase alias。
- **前端**：`api/rss.ts`；`RssSubscriptionTab.vue`（828 行：源表格/enabled 开关/状态三态/待添加徽标/新增编辑弹窗/文章抽屉状态筛选分页/推送参数弹窗——目标下载器覆盖（getList 懒加载过滤 qB/TR）+savePath+tags；≤780 抽屉全宽+工具栏堆叠）；设置弹窗 `rssSubscription` 页签（`rssTabAvailable` 类型 0/1 门控）；LucideIcon 补 rss/external-link；zh/en `downloader.rss` 子树 + tabs 六键 + `errors.byCode` RSS_* 24 键成对。
- **demo**：fixtures `rssFeeds` 两组（含 failed 状态投影与已推送文章）+ types/DemoFixtureBundle + demo-store 七方法（刷新幂等补一篇/推送一次性）+ demo-request `/rss/*` 路由分支 + fixtures README 登记。
- **测试**：后端 `tests/api/test_rss_subscriptions.py` 20 例；存量校准 3 处（枚举计数 55→60、表计数 35→37、hash head 语义）；前端 `rss-subscription-tab.spec.ts` 7 例 + `rss-tab-integration.spec.ts` 3 例 + `demo-request.spec.ts` 扩 5 例。
- **验证**：后端全量 5281 passed/18 skipped（cov 67.15%）+ mypy 297 文件 0 错 + black/flake8 净；前端 typecheck/lint/build 净 + 全量 Jest 128 套 1871 例；根 ./init.sh 通过。
- **坑**：①服务 refresh 的 `content` 未预初始化，抓取异常分支 UnboundLocalError——异常路径必须先赋默认值；②`patch.object(类, "方法", new=普通函数)` 会触发方法绑定，替身需接住 `_self`；③autogenerate 产生大量既有漂移噪音（refresh_tokens 可空性/索引命名/orphan 硬链表），必须手写收敛为新表专属迁移；④既有空库全链重升级测试（stamp 回退）要求新表迁移必须带 has_table 守卫；⑤前端 mock 需包完整 ApiEnvelope 信封，仅 mock data 内层会走组件 catch 静默；⑥模板表达式不支持 TS 类型标注（buble），事件回调用裸箭头。

## 待办（随 Phase 2 或用户指示）

- 真实 qB/TR 浏览器联调（添加参数/磁链直链两种链接形态）。
- Phase 2：qB 原生 RSS 代理 + 按下载器模式切换 + 自动下载规则 + 定时刷新调度 + 按类型选择推送下载器。
