# 8 项已验证问题修复计划

> 状态：✅ 已批准（2026-08-16，审查修正版：根因经 4 个子代理验证，方案经 3 个子代理独立审查并修正）
> 创建日期：2026-08-16
> 问题来源：用户反馈 8 项问题 + 主代理分析 + 子代理验证 + 子代理审查
> 验证基线：frontend 源码与部署镜像（btdeck-frontend.latest.tar）比对；backend/config/app.db（22277 条种子）实证
> 预计总工作量：8～12 个工程日，按 5 个发布门分批交付
> 计划边界：本文定义修复方案与发布门；用户已确认全部 8 项一次性实施、令牌续期采用**双令牌 refresh 体系**；W4-1 需新增 `disabled_by` 迁移字段、W6-1 需新增 `refresh_tokens` 表迁移；新增后端端点走统一响应格式

---

## 1. 目标与成功标准

### 1.1 目标

修复用户反馈的 8 项问题，每项修复以"根因→改动→回归"闭环交付：

1. `/torrents/active-torrents` 只在种子列表界面轮询；种子详情页不轮询；后台标签页暂停轮询。
2. 下载器设置-标签/分类页签：创建（及重命名）标签/分类同步到下载器（qB 立即创建，Transmission 按设计跳过）。
3. 新添加种子的"添加时间"不再为空：插入路径兜底 + 首轮快照水合 + 存量 NULL 回填。
4. 路径同步不再"误删"历史路径：种子回来自动重新启用 + 清理加宽限期。
5. 种子转移不再假成功：检查添加返回值、目标查重、批量失败语义修正；转移操作日志在操作日志页面可见。
6. 前端令牌双令牌续期：登录签发 access + refresh；401 先静默刷新并重放请求，刷新失败才登出；登出撤销 refresh。
7. 4 种删除操作的审计日志记录操作 IP/UA/真实操作者。
8. 除首页统计卡片外，各页面提供展开/收缩按钮，折叠偏好持久化到 localStorage。

### 1.2 非目标

- 不引入 Redis/Celery 等额外基础设施；不切换数据库。
- 不为路径清理新增时间类字段（复用 `last_updated_time` + 新增 `disabled_by` 来源字段区分自动/用户禁用）。
- 不改动 dashboard 统计卡片（按用户要求除外）。
- 不迁移既有 localStorage 键名（新增统一封装，存量键兼容读取）。
- 不重写 seed_transfer_audit_log 表结构（转移明细表保留，操作日志另写 torrent_audit_log）。
- 标签重命名不做种子归属迁移（qB 无改名 API，本期仅创建新名，局限见 W2-2）。

### 1.3 关键不变量

- 下载器客户端只能来自 `app.state.store`；所有下载器调用经 `call_downloader_api`（含 lane）。
- 同步类批量写入保持 db_write_scope + 分批提交。
- 新 API 保持统一响应格式（list/total/pageSize；CommonResponse）。
- 前端保持 Vue 2 Options API，新增 TypeScript 类型禁止 any。
- 审计日志统一走 `AuditLogService.log_operation` + `extract_audit_info_from_request`。
- 前端偏好统一 `btdeck_` 前缀 localStorage 键。
- refresh token 落库存 SHA-256 哈希（不存明文）；使用即轮换；登出撤销。

---

## 2. 问题→根因（已验证）→交付项映射

| # | 问题摘要 | 验证后根因（证据） | 主要交付项 |
|---|---|---|---|
| 1 | active-torrents 任意界面轮询 | 代码无全局轮询（仅 index.vue/TraditionalView 两处，created 启动/beforeDestroy 停止）；`/torrents/detail/:hash` 挂载整个 index.vue 列表视图（router.ts:108）导致详情页也轮询；keepAlive meta 是死配置 | W1-1 详情路由独立化；W1-2 后台暂停；W1-3 清理死配置 |
| 2 | 标签/分类不同步下载器 | create_tag 被"架构调整"注释刻意摘除同步（tag_management.py:448-450）；`_sync_tag_to_downloader`（:1019）与 adapter `create_tag`（qbittorrent_adapter.py:115）均死代码；update_tag 同样缺同步 | W2-1 创建同步恢复（qB/TR 分流）；W2-2 重命名同步 |
| 3 | 新种子添加时间为空 | 所有写入路径 added_on 无效即写 NULL（torrents_async.py:3297/3348、torrent_helpers.py:862、torrent_sync.py:824）；首轮 rid=0 maindata 快照不水合（:3113-3123）；无兜底无回填（生产库 22277 条 0 空值，仅新添加路径命中） | W3-1 首轮快照水合；W3-2 UI 添加本地时间兜底；W3-3 存量 NULL 回填 |
| 4 | 路径同步误删历史路径 | `_cleanup_obsolete_paths` 无宽限期立即禁用（downloader_path_scan.py:826-831）；`_sync_active_path` 永不重新启用（:777-782）；生产库 id 38 实证：2 条活种子、count 持续更新、is_enabled 恒为 0。审查修正：模型无"自动/用户禁用"区分字段，重新启用须防推翻用户手动禁用 | W4-1 新增 disabled_by 字段（迁移）+ 仅恢复 auto 来源；W4-2 宽限期（settings 配置，默认 30 天）；W4-3 前端历史路径展示 |
| 5 | 转移假成功/无日志 | qB `torrents_add` 返回 "Fails." 不抛异常且返回值被忽略（seed_transfer_service.py:342-349）；`_verify_transfer` 按 hash 查旧种子即判成功（:584-586）；批量端点固定 code=200（seed_transfer.py:251-256）；审计写 seed_transfer_audit_log 无读取 API；端点硬编码 admin | W5-1 返回值检查；W5-2 目标查重（duplicate 状态）；W5-3 批量失败语义+前端展示；W5-4 审计并入 torrent_audit_log+真实用户 |
| 6 | 令牌不自动续期 | 后端只签单个 60 分钟 access_token（login.py:61-69、config.py:100），无 refresh 端点；前端 request.ts 401 直接 redirectToLogin（:126-128/:152-155），无重试无刷新。用户已确认采用双令牌 refresh 体系 | W6-1 后端 refresh_tokens 表（迁移）+ /auth/refresh + 登出撤销；W6-2 前端 401 单飞刷新+重放+登录/登出链路 |
| 7 | 删除日志无 IP | 4 个删除端点从不调用 extract_audit_info_from_request；torrent_deletion_service.py:527 硬编码 ip_address=None（TODO）；by_level 8 处 log_operation 不传 IP；写对 IP 的 _log_deletion_operation_async 是死代码 | W7-1 端点提取 audit_info；W7-2 服务层透传（Deletion/ByLevel/AsyncExecutor/RecycleBin）；W7-3 operator 真实化+死代码清理 |
| 8 | 缺展开/收缩与习惯记录 | 无通用折叠面板组件；偏好散落硬编码 localStorage 键（4+ 处）；dashboard 完全静态（按要求除外）；viewMode 实际已持久化（btdeck_view_mode），仅注释误导 | W8-1 CollapsiblePanel 通用组件；W8-2 各页面接入；W8-3 偏好封装统一（可选演进） |

---

## 3. 分阶段实施

### Phase 1：种子列表与轮询（问题 1）— 0.5~1 天

**W1-1 详情路由独立化（主修复）**
- `frontend/src/router.ts:108-114`：`/torrents/detail/:hash` 改为懒加载新建轻量组件 `views/torrents/detail.vue`（只读详情 + 不启动轮询）；或最小改动：`index.vue` 按 `this.$route.name === 'torrent-detail'` 跳过 `startSpeedPolling()`（:967）。
- 评估：新建组件更干净，但需迁移详情相关展示逻辑；若详情视图目前依赖列表组件大量逻辑，采用"路由守卫跳过轮询"方案。

**W1-2 后台标签暂停轮询**
- `index.vue` 轮询循环（:2302-2314）与 `TraditionalView.vue`（:1255-1274）：监听 `document visibilitychange`，`document.hidden` 时置 `speedPollingActive = false` 并清 timer；恢复可见后若组件仍挂载则重启轮询并立即刷新一次。
- 统一抽到 `views/torrents/utils/torrentBatch.ts` 的纯函数/混合（两视图逐字重复，已有合并先例注释）。

**W1-3 清理死配置**
- `frontend/src/router.ts`：删除全部 `keepAlive: true` meta（无 `<keep-alive>` 支撑）。

**测试**：Jest 新增路由切换停轮询、visibility 暂停/恢复用例；`npm run typecheck` + lint。

### Phase 2：标签同步与路径清理（问题 2、4）— 2 天

**W2-1 创建同步恢复**
- `backend/app/api/endpoints/tag_management.py:446` return 前调用 `_sync_tag_to_downloader`（:1019，按 downloader 遍历）：
  - qB：`torrent_categories.create_category` / `torrent_tags.create_tags`（复用现成 helper 分支，1088-1104 行）。
  - Transmission：跳过（TR 无独立创建 API，标签在使用时创建——保留该设计语义）。
- 同步失败不阻断 DB 写入：捕获异常记 warning，响应附 `sync_warning` 字段（可选）。

**W2-2 重命名同步**
- `update_tag`（:469-518）：标签改名后同步（TR 跳过；qB 按需 create+rename 或 delete+create）。

**W2-3 注释与死代码**
- 更新 :448-450 注释为"qB 创建时同步；TR 使用时创建"；`:1086` 死代码自标注移除。

**W4-1 重新启用（审查修正：需新增 disabled_by 迁移字段）**
- 模型 `downloader_path_maintenance` 新增 `disabled_by` 字段（NULL=从未禁用 / 'auto'=清理禁用 / 'user'=用户禁用），Alembic 迁移（inspect 守卫样板，链到实际 HEAD `d4e5f6a7b8c9`，并纠正 backend/docs/constraints/database-migration.md:57 的 HEAD 漂移）；存量 is_enabled=0 记录迁移默认标 'user'（保守：不推翻任何现存禁用状态）。
- `path_maintenance_service.delete_path`（:374-399）与 PUT 禁用端点（:229-276）标 'user'；`_cleanup_obsolete_paths` 标 'auto'；`_sync_active_path`（:777-782）仅当 `disabled_by='auto'` 时写回 `is_enabled=True`——用户手动禁用永不被扫描推翻。

**W4-2 宽限期**
- `backend/app/core/config.py`：新增 `PATH_CLEANUP_GRACE_DAYS: int = 30`。
- `_cleanup_obsolete_paths`（:826-831）：禁用条件改为 `(now - coalesce(last_updated_time, created_at, updated_at)).days > grace_days`（last_updated_time 可空必须 coalesce）；仅对 `disabled_by IS NULL OR ='auto'` 的记录生效；迁移时把当前仍有种子的路径 last_updated_time 刷新为 now（防存量老记录部署后首轮批量禁用）。

**W4-3 前端展示（可选）**
- 下载器设置-路径管理页：禁用路径显示"历史路径"分组 + 最后使用时间，支持手动启用（复用 `path_maintenance_service` 既有端点）。

**测试**：pytest——create_tag qB mock 断言 create_category/create_tags 调用且 await；TR 跳过；update_tag 同步；`_sync_active_path` 重新启用；`_cleanup_obsolete_paths` 宽限期参数化（30 天内不禁用/超期禁用/重新启用后不再禁用，当前该类无任何测试）。

### Phase 3：添加时间与转移（问题 3、5）— 2.5~3 天

**W3-1 首轮快照水合**
- `torrents_async.py:3113-3123`（info_only 首轮）与 `:1758-1776`（旧函数首轮）：rid=0 分支同样调用 `_hydrate_qb_incremental_torrents`，从 `torrents_info` 取全量字段（含 added_on），消除对 maindata 字段完整性的依赖。

**W3-2 UI 添加兜底**
- `torrent_helpers.py:862-866` `create_qbittorrent_torrent_record`：`added_on` 无效时 `added_date = datetime.now()`（种子刚添加，本地时间即添加时间）；`:877-887` create_time/update_time 同步兜底。

**W3-3 存量回填**
- 启动任务（`backend/app/startup/lifecycle.py` 或一次性命令）：`UPDATE torrent_info SET added_date=? WHERE added_date IS NULL`，按 downloader 分组、以 hash 批量调 `torrents_info` 拉取 added_on 回填；受既有 db_write_scope 约束分批。

**W5-1 添加返回值检查**
- `seed_transfer_service.py:342-349`：接收 `torrents_add` 返回值，`"Fails."`（含 Fails 子串）→ 返回明确失败（"目标下载器拒绝添加（可能已存在相同种子）"）。

**W5-2 目标查重**
- `transfer_seed` 添加前先查目标下载器是否已有该 hash → 已存在则 `transfer_status="duplicate"`、`success=False`，返回"目标已存在相同种子"；`_verify_transfer` 保持仅验证本次新添加（添加前确认不存在）。

**W5-3 批量失败语义与前端**
- `seed_transfer.py:251-256`：`failed_count > 0` 时 `status="error"`、code=400（数据仍返回 results）。
- `BatchTransferDialog.vue:367/396-404`：按 results 逐条展示；`resultFailed > 0` 时不 emit success、不触发删除源种子。

**W5-4 审计并入统一表**
- 新增 `AuditOperationType.TRANSFER`（`backend/app/torrents/audit_enums.py`）；`transfer_seed` 成功/失败经 `AuditLogService.log_operation` 写 `torrent_audit_log`（operation_detail 含源/目标下载器、路径、hash）；`seed_transfer_audit_log` 保留为明细。
- `seed_transfer.py:90-91/196-197`：`user_id/username` 改用 `_user` 依赖的真实用户。

**测试**：pytest——torrents_add 返回 "Fails." → 失败；目标已有 hash → duplicate 且不删源；批量全失败 → code 400；审计出现在 torrent_audit_log 且 operator 真实；首轮快照无 added_on 水合后插入有值；added_on=0 本地兜底；存量回填（构建 NULL 行 → 回填断言）。Jest——BatchTransferDialog 失败不 emit success。

### Phase 4：双令牌 refresh 体系（问题 6，用户已确认）+ 删除日志 IP（问题 7）— 3~3.5 天

**W6-1 后端双令牌**
- Alembic 迁移新增 `refresh_tokens` 表（id、user_id、token_hash SHA-256、expires_at、revoked_at、created_at、ip_address、user_agent），链到实际 HEAD `d4e5f6a7b8c9`（database-migration.md:57 声称的 c8d9e0f1a2b3 已漂移，一并纠正）；env.py 注册模型；inspect 守卫样板；test_db_migration.py EXPECTED_HEAD 同步。
- `login.py`：登录签发 access_token（60 分钟，不变）+ refresh_token（7 天，随机串、DB 存哈希、payload 带 `token_type="refresh"`）；响应 data 增加 refresh_token 字段。
- 新增 `POST /auth/refresh`（login.py router 内，最终 `/api/v1/auth/refresh`，无需改 api.py）：**独立校验函数**（`verify_access_token` 的 60 分钟最大年龄硬检查 utils.py:100 会拒 7 天 token，必须绕过/参数化）；校验存在+未过期+未撤销+token_type → 换发新 access+refresh（使用即轮换：删旧行插新行）；XFF→X-Real-IP→client.host 记录（复用 extract_audit_info_from_request 级联）。
- 登出撤销：cuser.py POST /users/logout（现为空操作 :24-40）改为撤销该用户全部 refresh 行。
- API 文档：/auth/refresh 入 backend/docs/style-and-contract-audit.md 端点统计与 docs/roadmap/backend/api/（DoD 要求）。

**W6-2 前端**
- `store/modules/user.ts`：新增公开 `SetToken` action（私有 SET_TOKEN mutation :32-35 只改内存不写 cookie，action 内补 setToken）；Login action（:68-89）接住 refresh_token 存 cookie（cookies.ts 新增 refreshTokenKey）；ResetToken/LogOut 清 refresh cookie。
- `api/users.ts:14-18` LoginResponseItem 增加 refresh_token 字段。
- `request.ts` 响应拦截器：401（业务码或 HTTP）且非登录/登出/refresh 请求 → 单飞刷新（模块级共享 refreshPromise，并发 401 复用）→ 成功 SetToken + 用原 config 重放一次（请求拦截器 :75-78 自动带新 token）；刷新失败才 redirectToLogin；`isLoginRequest`（error-normalize.ts:69-72）增加 /auth/refresh 豁免，刷新请求自身 401 绝不进入刷新循环；刷新编排抽成可注入依赖的纯模块（仿 error-normalize 先例，便于单测）。

**W7-1 端点提取**
- `torrent_deletion.py` 4 个端点（:130-131/:397-400/:618-626/:769-771）调用 `extract_audit_info_from_request`，将 audit_info 传入服务层。

**W7-2 服务层透传**
- `torrent_deletion_service.py:211` 构造函数加 `audit_info` 参数（**带默认值 None，防既有直接构造服务的测试必破**）；`:527-528` 用其填充 ip_address/user_agent/request_id/session_id，移除 TODO。
- `torrent_deletion_by_level.py`：构造函数已持 request（:41-74），内部提取；8 处 `log_operation`（:323/347/422/446/542/572/903/958）补传 ip/user_agent。
- `async_deletion_executor.py`（request 已传入）与 `recycle_bin_service.py`（restore 已收 request；manual_cleanup 补参数）：同法。
- **operator 防伪造（审查新增）**：with-level（:624）与 async 批量（:765）的 operator 目前来自请求参数默认 "admin"，任何用户可伪造——统一取 `_user`/`request.state.user_info`，替换硬编码与请求参数来源。

**W7-3 死代码清理**
- 接入或删除 `_log_deletion_operation_async`（torrent_deletion.py:505）。

**测试**：pytest——refresh 换发/轮换/过期/已撤销/伪造/verify_secret 不匹配；登出撤销；迁移升降级；4 个删除端点审计断言 ip_address/user_agent 非空且 operator=认证用户（同步 test_torrent_deletion_by_level_api.py:316 等 kwargs 断言）；Jest——401 单飞刷新重放、刷新失败登出、error-normalize 补 refresh 豁免。

### Phase 5：折叠面板（问题 8）— 1.5~2 天

**W8-1 通用组件**
- `frontend/src/components/CollapsiblePanel.vue`：标题栏 + 折叠按钮（Lucide chevron）+ `v-model` 折叠态 + props `storageKey` 持久化；复用 `utils/cookies.ts` 的 `getStorage/setStorage`；键统一 `btdeck_` 前缀；样式并入 `styles/management-list-page.scss` 扩展 `.management-panel`。

**W8-2 各页面接入**
- 种子列表筛选面板、下载器设置各页签、日志/回收站/孤儿文件/查询模板/任务页的 `.management-panel`；dashboard 统计卡片除外。

**W8-3 偏好封装统一（可选演进）**
- 新键走统一封装；存量键（columns_visibility 等）保留兼容读取。

**测试**：Jest——CollapsiblePanel 折叠态持久化、多实例键隔离、初始值回退；各页面接入冒烟。

---

## 4. 测试计划

| 层级 | 内容 | 门禁 |
|---|---|---|
| 后端单测 | 各 Phase 新增/修改 pytest（见各 Phase 测试小节） | 定向套件全绿；目标 Black/Flake8/mypy 通过 |
| 后端回归 | 全量 pytest（当前基线 3163 passed/7 skipped） | 零新增失败 |
| 前端单测 | 新增 Jest（轮询生命周期、折叠组件、401 刷新、转移弹窗） | 定向套件全绿；typecheck 通过 |
| 前端回归 | 全量 Jest（41 suites/657 tests 基线）+ 生产 build | 零新增失败；build 仅既有 warning |
| 数据实证 | 问题 4：以生产库副本验证 id 38 路径在"种子存在"场景下恢复 is_enabled=1；问题 3：NULL 行回填脚本 dry-run | 副本库验证，不写生产 |

## 5. 验收标准（发布门 G1~G5）

- **G1（Phase 1）**：手动直接访问 `/torrents/detail/:hash`（死路由，无站内入口）无 active-torrents 请求；后台标签页无轮询流量；DevTools Network 验证。
- **G2（Phase 2）**：下载器设置创建标签/分类后 qB 侧立即可见（TR 侧按设计不出现）；路径清空 30 天内不禁用、种子回归 1 小时内自动恢复启用（时间尺度用 pytest 参数化 + 配置调短验证）；用户手动禁用的路径不被扫描重新启用。
- **G3（Phase 3）**：新添加种子列表"添加时间"非空；重复转移返回"目标已存在"；操作日志页面可见转移记录（含真实操作者）。
- **G4（Phase 4）**：token 过期瞬间自动续期不退出（连续操作 60 分钟以上验证）；登出后 refresh 撤销生效；删除操作审计日志含 IP/UA。
- **G5（Phase 5）**：各页面折叠状态刷新后保持；dashboard 统计卡片无折叠按钮。
- 全部：`./init.sh` 通过；feature_list.json/progress.md 更新；按 AGENTS.md 完成证据记录。

## 6. 风险与回滚

| 风险 | 应对 |
|---|---|
| W3-1 首轮快照水合增加首轮同步耗时 | 宽松模式（strict=False，缺 hash 不抛错）；仅 info_only 预算路径启用；legacy 首轮不动；必要时仅对缺 added_on 的行水合 |
| W4-1 迁移对存量禁用记录来源归属 | 存量 is_enabled=0 默认标 'user'（保守，不推翻现状）；历史自动禁用路径需手动启用一次，之后自动恢复生效 |
| W4-2 宽限期默认 30 天 | 配置可调（0=立即禁用，保持旧行为）；迁移刷新有种子路径的 last_updated_time 防首轮批量禁用 |
| W5-3 HTTP 200 + code=400 | 与单条端点现状一致；前端经 ApiError.rawResponse 取载荷；不污染全局 SUCCESS_CODES |
| W6 双令牌体系 | refresh 落库 SHA-256 哈希防盗库；使用即轮换；登出撤销；verify_access_token 60 分钟年龄检查需独立校验函数绕过；刷新重放仅一次防死循环；/auth/refresh 自身 401 不进刷新循环 |
| 前端 401 重放二次失败 | 重试仅一次；失败走原登出流程，无死循环 |

**回滚策略**：各 Phase 独立提交；W4-2 宽限期、W6-1 新增表均为增量变更，配置默认值不改变旧行为即可回退；W4-1/W6-1 迁移提供 downgrade（删除新增列/表）。

---

**维护者**: BtDeck 开发团队
**最后更新**: 2026-08-16
