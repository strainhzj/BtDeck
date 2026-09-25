# 下载器 RSS 订阅 Phase 2（qB 原生代理 + 自动规则 + 定时调度 + 统一管理入口）

> **feature**: `rss-subscription-phase2-2026-09-24`
> **状态**: ✅ 已交付（2026-09-24；代码+测试+文档全绿，待真实 qB/TR 联调与 Git 提交）
> **前置**: Phase 1（feature `rss-subscription-2026-09-24`）已交付，见 [rss-subscription.md](./rss-subscription.md)

## 范围（用户确认 2026-09-24）

1. **qB 原生 RSS 代理管理**：订阅源/文件夹/下载规则/RSS 偏好透传 + 文章浏览/已读标记（qB 为事实源，BtDeck 不落库）。
2. **按下载器的模式切换**：`btdeck`（默认，BtDeck 引擎）/ `qb_native`（qB 自身管理），仅 qB 可选后者。
3. **BtDeck 引擎自动下载规则**：关键词 include/exclude + 正则开关 + 目标下载器/savePath/tags。
4. **定时刷新调度**：全局 cron 任务 + 每源刷新间隔覆盖。
5. **按规则选择推送的目标下载器**（target_downloader_id，null=归属下载器）。
6. **RSS 管理统一入口**：下载器管理菜单下新增「RSS 管理」子菜单，跨下载器统一管理；与下载器设置弹窗 rssSubscription 页签多入口并存，共享组件。

## 关键决策（用户拍板）

| 决策点 | 结论 |
|---|---|
| 规则↔源绑定粒度 | 多选源（`bt_rss_rule_feeds` 关联表），**空关联=归属下载器全部源** |
| 规则保存后回填 | **保存即对存量 pending 匹配并自动推送**（对齐 qB 直觉），配 match-preview 先看再存 |
| 每源刷新间隔 | 支持：`bt_rss_feeds.refresh_interval_minutes` 可空列（null=跟全局节奏） |
| 能力矩阵 | **加 `rss_management` 键**（extended_capabilities JSON：qB=true / TR=false 默认；读取缺键回退按类型；DB 覆盖优先） |
| qB 原生文章浏览 | **做**：rss_items(with_data=True) 文章投影 + 源级/单篇 mark-as-read |
| 规则 DSL v1 | include/exclude + use_regex + 目标下载器/savePath/tags；不加大小/分类过滤 |
| 双模式护栏 | 目标下载器 qb_native → 自动推送 skip+计数、手动推送 409 `RSS_MODE_CONFLICT`；源绑定下载器 qb_native → 调度跳过（引擎冻结不删数据）；护栏只看目标 |
| 统一入口 | `/downloader` 改双 children（index + rss），新页 `views/rss/index.vue`；移动端 `/m/rss` 整页；与设置弹窗页签共享面板组件 |

## 后端设计

### 数据层（1 个 Alembic 迁移，head 8fabba8687b0 → 新 rev）

- **`bt_rss_modes` 新表**：downloader_id UNIQUE / mode(20)∈`btdeck`\|`qb_native` / created_at / updated_at / dr；行惰性创建（首次 PUT 落行），GET 无行=btdeck。
- **`bt_rss_rules` 新表**：rule_id UUID PK / downloader_id（归属下载器，规则在其 RSS 入口管理）/ name(200) / enabled int / include_keywords Text（逗号分隔，任一命中 OR）/ exclude_keywords Text?（全不命中 AND NOT）/ use_regex int（0=大小写不敏感子串，1=re.search）/ target_downloader_id?（null=归属下载器）/ save_path?(500) / tags?(200) / match_count int / last_matched_at? / created_at / updated_at / dr。
- **`bt_rss_rule_feeds` 新表**：rule_id + feed_id，UNIQUE(rule_id, feed_id)；空关联=全部源。
- **`bt_rss_articles` 加列**：`added_rule_id`(36)?（自动规则命中事实，手动推送为 null）。
- **`bt_rss_feeds` 加列**：`refresh_interval_minutes` int?（null=全局节奏）。
- **锚点四处同步**：迁移文件 / `docs/constraints/database-migration.md` HEAD / `tests/core/test_db_migration.py::EXPECTED_HEAD` / 空库表计数 37→**40**。

### qB 原生代理（`services/rss_qb_proxy_service.py` + 端点挂 `/api/v1/rss/qb/{downloaderId}/...`）

- 全部走 store 缓存客户端 + `call_downloader_api(INTERACTIVE)`；仅门控 `downloader_type==0`（不校验 mode——mode 只管引擎侧行为，代理随时可调）。
- **源/文件夹**：GET items（树投影，含 unreadCount）、POST feeds（path+url → rss_add_feed）、POST folders（path → rss_add_folder）、PUT feed-url（rss_set_feed_url）、DELETE item（源或文件夹，rss_remove_item）、POST refresh（itemPath 可空=全部）、POST move-item（rss_move_item）、POST mark-read（itemPath + 可选 articleId → rss_mark_as_read）。
- **文章**：GET articles?feedPath（rss_items(with_data=True) 投影：articleId(uid)/title/published/link(torrentURL→link→magnetURI 优先级)/isRead）。
- **规则**：GET rules（rss_rules）、POST rule（rss_set_rule，ruleDef 透传+基本校验）、DELETE rule、PUT rename-rule、GET matching-articles（rss_matching_articles，规则预览）。
- **偏好**：GET preferences（app_preferences 只投影四键：rss_processing_enabled / rss_auto_downloading_enabled / rss_refresh_interval / rss_max_articles_per_feed）；PUT preferences（setPreferences **白名单硬校验**，越键 400 `RSS_QB_PREF_KEY_REJECTED`）。

### 模式端点（BtDeck 侧）

- `GET /api/v1/rss/mode?downloaderId` → `{mode}`。
- `PUT /api/v1/rss/mode`：`qb_native` 仅 type==0，否则 400 `RSS_MODE_TYPE_UNSUPPORTED`；切 qb_native 响应携带提示 data（引擎侧源与规则冻结不删除，切回即恢复）。

### 引擎规则端点与匹配

- `GET/POST/PUT/DELETE /api/v1/rss/rules`（分页 list/total/pageSize；POST/PUT 后立即回填匹配+自动推送并返回命中数）。
- `POST /rules/{id}/match-preview`：对存量 pending 匹配预览，不推送。
- 匹配语义：include OR + exclude AND NOT；默认 ci 子串；use_regex=1 时 re.search（非法正则保存 400）；匹配字段=文章 title。
- 自动推送：命中 pending → 复用 `add_article_to_downloader` 全链路（INTERACTIVE 推送 + status=added + added_rule_id）；目标 = target_downloader_id ?? 归属下载器。

### 定时刷新调度

- 任务 `app/tasks/scheduler/rss_refresh_task.py`（execute(**kwargs) + self.app 注入拿 store）；注册 `default_scheduled_tasks.py`：task_code=`bt_rss_refresh`，cron **`13,43 * * * *`**（30 分钟 + 错峰），timeout 900s，max_retry 0。
- 任务体：enabled 源 → 过滤（绑定下载器在线 / 非 qb_native / 满足 per-feed 覆盖间隔 `now - last_fetch_at >= interval`）→ 逐源 refresh_feed（单源失败不中断）→ 每源刷新后规则匹配+自动推送 → 汇总 `{refreshed, skipped_offline, skipped_mode, new_articles, auto_added, auto_skipped_mode, errors}`（错误列表有界，对齐 OOM 治理约束）。
- android-server：注册即跳过（外网抓取不可用，平台门控惯例）；轻量不入 task_profiles。

### 能力矩阵

- `extended_capabilities` JSON 增 `rss_management`：qB 默认 true、TR/RT 默认 false；读取缺键回退按类型判定；DB 手动覆盖优先（既有 manual_override 机制）。
- 能力端点投影与前端类型同步；前端 qB 面板/模式选项按能力门控。

### 审计与错误码

- 审计枚举新增：RSS_RULE_ADD/UPDATE/DELETE、RSS_MODE_SWITCH、RSS_QB_FEED_ADD/DELETE/REFRESH、RSS_QB_RULE_ADD/UPDATE/DELETE、RSS_QB_PREF_UPDATE（best-effort 同 Phase 1）。
- RSS_* reasonCode 新键（mode/rule/qb 三组 + `RSS_MODE_CONFLICT`/`RSS_QB_PREF_KEY_REJECTED` 等），zh/en errors.byCode 成对。

## 前端设计

- **组件拆分**（RssSubscriptionTab 828 行不再膨胀）：
  - `RssSubscriptionTab.vue` 保留为设置弹窗页签壳：模式单选（qB 显示，切换确认弹窗）+ 引擎区/qB 面板条件渲染；
  - 新 `RssRulesPanel.vue`（规则表格 + 编辑弹窗：名称/include/exclude/正则/feed 多选/目标下载器/savePath/tags/启用 + 匹配预览抽屉）；
  - 新 `RssQbNativePanel.vue`（qB 源树/列表 + 刷新/已读/删除/改址/移动 + qB 规则表格/编辑弹窗（mustMatch/mustNotMatch/affectedFeeds/savedPath/category/addPaused）+ 偏好卡四键 + 文章抽屉（含单篇已读））。
- **统一管理入口**（#7）：`/downloader` 路由改组（parent meta 下载器管理 + redirect），children：`index`（原列表）+ `rss`（新 `views/rss/index.vue`：下载器选择器 + 同一套面板组件，跨下载器统一管理）；navigation i18n zh/en 增路由键；移动端 `/m/rss` 整页复用，入口在移动端下载器页；demo DEMO_ROUTE_MATRIX 同步。
- `api/rss.ts` 扩展：mode 2 / rules 5 / qb 代理 13 接口 + 类型；demo 同形分支（fixtures 增 rules/qb 数据）。
- Options API class 风格；≤780 移动适配沿用抽屉全宽/工具栏堆叠；i18n zh/en 全量成对。

## 验收

- 后端：mypy/black/flake8 + 相关 pytest；迁移 upgrade/downgrade 对称，四处锚点同步。
- 前端：typecheck/lint/build + Jest；i18n 门禁成对。
- 仓库：`./init.sh` 通过；真实 qB/TR 联调（与 Phase 1 遗留合并：双模式切换、qB 原生源/规则/偏好、自动规则推送、磁链/直链两形态）。

## 任务拆分（feature_list 登记）

| # | 任务 | 范围 |
|---|---|---|
| rss2.1 | 后端数据层+迁移+模式端点+规则 CRUD/匹配引擎 | 3 表 2 列、锚点四处、能力键默认、匹配语义单测 |
| rss2.2 | 后端 qB 原生代理服务+端点+偏好白名单+文章浏览 | 13 接口、fake qB client 透传断言 |
| rss2.3 | 后端定时刷新任务+自动推送管线+护栏 | 注册表、错峰、跳过/跳闸/汇总断言 |
| rss2.4 | 前端：api+设置弹窗页签重构（模式壳+双面板+规则 UI） | 共享组件抽取、i18n、demo |
| rss2.5 | 前端：RSS 管理统一入口（桌面子菜单+移动端） | /downloader/rss + /m/rss、路由/i18n/demo |
| rss2.6 | 验证与文档收口 | 全量门禁、roadmap、PLANS、progress、handoff |

## 实施记录（2026-09-24）

- **数据层（rss2.1）**：`models/rss_subscription.py` 扩五表——bt_rss_modes（downloader_id PK 惰性建行）/bt_rss_rules/bt_rss_rule_feeds（复合主键）+ added_rule_id/refresh_interval_minutes 两列；迁移 `d4a7f1c9e2b6`（head 前移，has_table+列存在双幂等守卫 + 对称 downgrade；锚点四处：约束文档 HEAD/EXPECTED_HEAD/表计数 37→40/hash 继任链断言改链回溯）。
- **规则与模式服务（rss2.1）**：`rss_rule_service.py`——模式读写（qb_native 仅 qB + `supports_rss_management` 能力键（extended JSON qB=true/TR=false 默认+缺键回退+DB 覆盖优先））；规则 CRUD 校验（关键词非空/正则编译/重名 409/跨下载器源/目标类型 0·1）；匹配引擎 include OR + exclude AND NOT（ci 子串或 re.search，字段=title）；`find_matching_pending` 有界扫描（yield_per 200 + 命中即停 + _SCAN_LIMIT 5000 硬上限）；match-preview 只读；回填拆分——create/update 同步落库、端点层 await `apply_rule_to_pending`（复用 add_article_to_downloader 增 rule_id 事实，护栏目标 qb_native skip+计数）；响应 backfill 计数 camelCase 投影（matched/pushed/failed/skippedMode）。
- **推送护栏（rss2.1）**：`rss_feed_service.get_effective_mode/is_qb_native` 模块级助手（rss_rule_service 引用它，防循环依赖）；add_article_to_downloader 目标 qb_native→409 `RSS_MODE_CONFLICT`（手动+自动同拦）；update_feed 扩 refresh_interval_minutes（provided 区分显式 null=恢复全局，5-1440 校验）。
- **qB 代理（rss2.2）**：`rss_qb_proxy_service.py` `_with_client` 统一包装（store 快照+fail_time+type==0 门控+INTERACTIVE lane+异常归一 RSS_QB_PROXY_FAILED）；源树 `_walk_items`（feed 判定+未读数；**空 feed/空 folder qB API 都返 {} 无法区分，按 folder 投影**，已文档化）；文章路径游走投影（torrentURL>link>magnetURI + published 倒序 + onlyUnread）；规则 set 轻校验；偏好四键白名单（GET 投影/PUT 边界 1-9999·1-5000·布尔/空更新 RSS_QB_PREF_KEY_REJECTED/回读确认）。端点 `rss_qb_proxy.py` 15 接口（/api/v1/rss/qb/{id}/...；DELETE/query 传 path 防反斜杠路径段；android 拒写 GET 放行）。
- **定时调度（rss2.3）**：`rss_refresh_task.py` 注册 default_scheduled_tasks（bt_rss_refresh，cron `13,43 * * * *` 错峰，timeout 900，max_retry 0）；三态过滤（离线/qb_native 冻结/每源间隔未到期，全局兜底下限 10min 防 cron 调密打爆）；单源失败不中断（错误 ≤20 有界）；刷新后按源执行作用域规则（bound 过滤+无 pending 短路）；android-server 跳过。
- **审计**：+12 枚举（RSS_RULE_*×3/RSS_MODE_SWITCH/RSS_QB_*×8，60→72 校准）。
- **前端（rss2.4）**：api/rss.ts 扩 20 接口+类型；RssSubscriptionTab 重构双模式壳（qB 模式单选+确认弹窗，qbNativeAvailable 门控；TR 恒引擎）；新 RssRulesPanel（规则表格/编辑弹窗/匹配预览抽屉，backfill 计数转译提示）+ RssQbNativePanel（el-tree 源树/规则/命中预览/偏好卡/文章抽屉含单篇已读）；zh/en 全量成对（mode/rules 子树 + downloader.rss.qb 子树 + downloader.rssManager + errors.byCode RSS_* 32 新键）；demo 同形分支（七组新 fixtures + store 方法（回填匹配语义与后端一致）+ 路由分支含 qb 类型门禁/能力投影）。
- **统一入口（rss2.5）**：/downloader 路由改组（parent meta downloaderGroup + redirect，children index+rss）；`views/rss/index.vue`（下载器选择器+复用 RssSubscriptionTab，keepAlive）；navigation i18n 增 downloaderGroup/rssManagement/downloaderList；移动 `/m/rss` 整页 + 下载器页工具区入口 + `toMobilePath` 精确映射（/downloader/rss→/m/rss，其余 /downloader 不误伤）；DEMO_ROUTE_MATRIX 登记。
- **测试**：后端 test_rss_rules_mode 21 + test_rss_qb_proxy 20 + test_rss_refresh_task 10；迁移/枚举校准 4 处；前端 rss-phase2-panels 14（模式壳/规则面板/qB 面板）+ rss-manager-entry 8（路由契约/多入口共享/toMobilePath/DEMO_ROUTE_MATRIX）+ demo-request 扩 6。
- **验证**：后端全量 5332 passed/18 skipped（cov 67.70%）+ mypy 301 文件 0 错 + black/flake8 净；前端 typecheck/lint（含 contract:check --max-warnings 0）/build/全量 Jest 130 套 1899 例；根 ./init.sh 通过。
- **坑**：①RssSubscriptionTab 的 LucideIcon 是全局注册（main.ts），本地 `components: { LucideIcon }` 引用了未导入标识符直接 ReferenceError——组件注册前先确认 import 存在；②正则重排参数脚本会误伤同文件内的普通辅助函数（`request: Request` 被搬到带默认值参数后→语法错误），批量脚本改后必须语法检查；③vue 文件脚本里 `@/utils/errorMessage` 不存在，正确路径 `@/utils/formatters`；④qB rss_items 空 feed/空 folder 同形（{}）无法区分——按 folder 投影并在代码与 roadmap 文档化；⑤回填计数先按 snake_case 返回后在端点层补 camelCase 投影（对齐 API 契约一致性），测试键同步。

## 待办

- 真实 qB/TR 联调（与 Phase 1 遗留合并：双模式切换、qB 原生源/规则/偏好、自动规则推送、磁链/直链两形态）。
- Git 提交待用户指示。
- 部署：远端 unraid 192.168.5.51 可作联调环境（构建期容器 DNS 失败用 DOCKER_BUILDKIT=0 重跑）。
