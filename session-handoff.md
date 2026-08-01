# Session Handoff - BtDeck 全栈项目

## 2026-07-31 交接：孤儿文件管理增强（别名/置信度/忽视/多条件搜索）

**当前任务**: `orphan-files-management-enhancement`
**分支**: dev
**状态**: 前后端实现、回归与静态检查、项目记录均已完成；尚未提交。

### 本次交付四项需求

1. 日志/界面显示下载器所属时使用**别名**（复用 `BtDownloaders.nickname`，后端批量 JOIN 注入 `downloader_name`，nickname 空则回退掩码 ID）。
2. 孤儿列表增加**置信度列**（high=在线精筛/绿 tag，low=离线降级粗筛/灰 tag，含 tooltip 语义说明）。
3. 增加**忽视功能**：被忽视的孤儿受保护——定时任务（`get_purgeable_candidates`）不自动删除、手动清理（`cleanup_preview`/`cleanup_orphans`）也拒绝，但仍可在列表查询（status=ignored）。存 `OrphanCurrentCandidate`（跨扫描持久），resolved→candidate 重新出现时重置。
4. 增加路径/下载器/状态/**多条件搜索与分页**（`/list` 加 path_like/status/min_size/downloader_id；前端四字段搜索栏 + 重置 + 分页）。

### 关键技术决策（经子代理独立审查）

- **status=ignored 联表问题**：`normalize_path` 是 Python 函数无法下推 SQL。解决方案：给 `orphan_file` 加冗余列 `canonical_path`（+索引+存量回填，落库时已可得），使 ignored 过滤变成纯 SQL `WHERE canonical_path IN (...)`。迁移 `a1b2c3d4e5f6`。
- 前端交互采用**统一选中矩阵**：pending+ignored 均可勾选、deleted 禁勾，批量按钮按选中主导状态动态启停，混选禁用——替代原计划自相矛盾的"禁勾+预拦截"。

### 验证

- 后端：alembic 单 head（无分叉）；新增 11 测试全过；孤儿专项 192 passed/1 skipped；全量 2461 passed/6 skipped；black+flake8 干净。
- 前端：typecheck/eslint/build 干净；orphan-files.spec 16 passed（新增 4）；全量 Jest 24 suites/352 passed。
- 根 `init.sh --ci` 退出 0，无 error/warn。

### 当前工作区

- 后端改动：迁移 1 个、模型 1 个、服务 3 个（scanner/lifecycle/file_service）、API 1 个、审计枚举 1 个、测试 6 个。
- 前端改动：`api/orphan-files.ts`、`views/orphan-files/index.vue`、`tests/unit/orphan-files.spec.ts`。
- 项目记录：feature_list.json（新 feature + last_updated）、progress.md、session-handoff.md 已更新。
- 未执行 Git stage / commit / push。

---

## 2026-07-30 交接：孤儿扫描空 external 映射绕过严格校验修复

**当前任务**: `orphan-scan-path-scope-mapping-fix`（回归补丁）
**分支**: dev
**状态**: 已修复、回归与静态检查通过；尚未提交。

### 关键结论

- 现象：重建镜像后 `orphan_scan_cleanup` 报「扫描根不存在或非目录: /Downloads/bangumi」，整批 failed。
- 根因：tr/tr_lpan/tr_kpan 的自动发现映射 `external` 全为空；`PathMappingService` 未命中时原样返回输入路径，旧 `resolve_external_path` 只校验前缀命中 + isabs，把它误判为有效映射选成扫描根，而该路径在 BtDeck 容器内不存在 → `_walk_all_roots` fail-closed。
- 修复：`resolve_external_path` 前缀初筛改为只纳入 `external`/`target` 非空的显式映射；external 全空 → 返回 None → 走既有 `path_mapping_not_found` 软跳过。不误伤 `internal==external` 的合法恒等映射。
- 不新增数据库结构、不修改下载器路径映射配置；历史 failed 批次保留不动。下次扫描会把 tr 系未回填 external 的路径计入 `total_paths_skipped`/`warnings`，任务以 completed 结束。

### 验证

- orphan 专项回归：70 passed；Ruff / Flake8 / py_compile / `scripts/lint_btdeck.py` 通过。
- 真实 app.db 复跑：`/Downloads/bangumi` 及子路径返回 None；`external=/mnt/bangumi` 正例仍正常解析。

### 当前工作区

- 改动 2 个文件：`backend/app/services/orphan_manifest.py`、`backend/tests/services/test_orphan_manifest.py`。
- 待补：progress.md / session-handoff.md 已更新，feature_list.json 待补 evidence。
- 未执行 Git stage / commit / push。

---

## 2026-07-30 交接：孤儿扫描有效路径筛选与严格映射修复

**当前任务**: `orphan-scan-path-scope-mapping-fix`
**分支**: dev
**状态**: 实现、专项/全量回归、静态检查和项目记录已完成；尚未提交。

### 关键结论

- 扫描目录不再来自所有 `dr=0` torrent 或所有 path_mapping external：查询现同时过滤种子 `enabled=true/deleted_at IS NULL/dr=0`、下载器 `enabled=true/dr=0`，并排除维护表中明确停用的路径。
- `torrent_info.save_path` 被视为下载器内部路径；只有显式映射规则真实命中且结果为 BtDeck 可访问的绝对路径时，才会进入扫描根。
- 缺少映射不会让整批任务失败：路径按 `path_mapping_not_found` 记录、跳过，任务继续；全部未映射时也以 completed + 零扫描根结束。
- warnings 和 `total_paths_skipped` 会进入扫描响应、审计详情和定时任务结果/日志；内容明确提醒补全下载器映射，并声明任务不会自动修复。
- 生命周期 resolved 对账和实时清理授权限定在成功扫描根内；空范围和跳过目录下的历史候选保持原状态。

### 验证

- 全部 orphan 回归：133 passed / 1 skipped；后端全量：2406 passed / 6 skipped。
- Ruff、Flake8、py_compile、`scripts/lint_btdeck.py`、`git diff --check` 和 Git Bash 根 `init.sh --ci` 通过。
- `orphan_manifest.py`、`orphan_scan_task.py` 目标 mypy 通过；组合 mypy 的报告为既有 SQLAlchemy Column 类型债。
- HEAD 与当前版本的同组 9 个 Python 文件均被现有 Black 配置判定需重排，本轮未扩大无关格式化差异。

### 当前工作区

- 本轮修改 5 个后端实现文件、4 个回归测试文件、2 个代码路线图和 3 个根项目记录；无前端、依赖、Schema 或迁移变更。
- 未执行 Git stage、commit 或 push。
- 会话开始前已有的路径映射校验改动未被覆盖；路线图只同步本轮孤儿模块条目，工具目录、镜像归档与批处理文件保持不动。

---

## 2026-07-30 交接：下载器路径映射真实目录验证修复

**当前任务**: `v1.0.6.32`
**分支**: dev
**状态**: 实现、回归、全量验证和项目记录均已完成；本轮按用户要求提交，不推送。

### 关键结论

- 误判根因是测试端点只验证 JSON/字段/路径格式，从未访问实际目录。
- 新服务对每条映射同时验证两侧：BtDeck 侧 external 做有界本地目录/权限检查；下载器侧 internal 只复用 `app.state.store` 缓存客户端。
- Transmission 通过 `free_space(path)` 直接探测；qBittorrent 通过默认保存路径磁盘空间或状态可用的现有种子路径取证，无法确认时明确失败。
- 任一侧失败即整体 `valid=false`，`path_checks` 和 `errors` 可定位到具体映射与原因；保存流程和数据库结构未改变。

### 验证

- 新增回归：10 passed；受影响 API：47 passed；后端全量：2403 passed / 6 skipped。
- 前端全量：24 suites / 348 tests；完整 lint、TypeScript typecheck、生产 build 通过。
- Ruff、Flake8、py_compile、新增 service/schema 目标 mypy、`git diff --check` 与 Git Bash 根 `init.sh` 通过；`downloader.py` 的 18 条 mypy 报告为既有类型债务，未落在修改行。
- 新增 Python 文件已由 Black 单 worker 格式化，formatter 复核均返回 `NothingChanged`；当前 Windows 环境仍存在 Black CLI 完成后进程退出挂起。

### 当前工作区

- 本轮新增 2 个后端文件，修改后端端点/schema、前端 API/类型及项目记录/路线图；无依赖、迁移或 Schema 变更。
- 仅提交本任务文件，未执行 push。
- 会话开始前已有的 `.docker_temp_482561487`、`.pnpm-store/`、`.zcode/`、两个镜像归档、`build-and-export-images.bat` 与 `tools/` 均保持不动。

---

## 2026-07-30 交接：孤儿扫描 Transmission Torrent 文件清单解析修复

**当前任务**: `orphan-transmission-torrent-files-fix`
**分支**: dev
**状态**: 修复、真实 SDK 回归、后端全量回归与项目记录均已完成，尚未提交。

### 关键结论

- 根因位于共享 `TorrentManifestBuilder`，不是定时器、数据库或扫描目录本身：`transmission-rpc 7.0.11` 的 `Torrent` 不可迭代，文件清单存放在 `fields["files"]`；旧逻辑漏判后错误地迭代整个 Torrent。
- `orphan_manifest.py` 现统一解析真实 `Torrent` 与兼容形态，并在库存内已有文件时跳过逐种子 `get_torrent`；详情回退路径仍保留。
- `orphan_scanner.py` 的旧 Transmission 解析入口改为复用共享实现；错误形态现在返回带下载器/种子上下文的 `ManifestBuildError`。
- 回归测试已换用真实 `transmission_rpc.Torrent`，覆盖内嵌文件、详情回退和错误库存形态。

### 验证

- manifest/scanner 专项：46 passed。
- 全部 orphan 回归：130 passed / 1 skipped。
- 后端全量：2393 passed / 6 skipped。
- Flake8、Ruff、py_compile、`git diff --check` 通过。
- 目标 mypy 的 3 条错误均为修改前已有、且不在本次修改行的 SQLAlchemy `Column` 类型问题。
- Black 在 HEAD 与当前版本上对同一目标文件均报告既有格式差异，未为本热修复重排整份文件。
- 根 `init.sh` 在当前 Windows 环境因 WSL `E_ACCESSDENIED` 无法执行。

### 当前工作区

- 本轮修改 7 个文件：2 个后端服务、2 个后端测试、3 个根项目记录。
- 未新增依赖、迁移或 API；未执行 Git stage、commit 或 push。
- 会话开始前已有的 `.docker_temp_482561487`、`.pnpm-store/`、`.zcode/`、两个镜像归档、`build-and-export-images.bat` 与 `tools/` 均保持不动。

---

## 2026-07-30 交接：孤儿文件扫描、统计与刷新状态一致性修复

**当前任务**: `orphan-files-state-consistency-fix`
**分支**: dev
**状态**: 三项问题及配套清理事务/恢复一致性已实施；专项与全量回归通过，仓库既有门禁例外已记录，尚未提交。

### 关键结果

- 失败扫描不再清空页面：展示最近成功批次的剩余数据，同时明确提示最近失败原因并禁止清理；运行中扫描仍按确认契约显示空列表和零统计。
- 列表响应新增统一 `scan_context`，区分 `latest_attempt`、`display_scan` 与动态 `remaining_count/remaining_size`；扫描原始统计不被清理流程改写。
- 顶部刷新与全部页面刷新路径统一为一次分页请求，原子更新列表、统计、扫描状态和清理门禁；并发旧响应不能覆盖新状态。
- 手动/自动隔离和恢复成功会同步标记对应扫描明细；候选最终化与明细更新同事务提交，pending journal、lease 复核及 fail-closed manifest 安全规则保持生效。
- 应用启动在调度器前幂等对账历史稳定隔离候选，严格匹配批次、下载器和规范化路径，不新增 Schema 或迁移。

### 验证

- 后端专项：77 passed / 1 skipped；全量：2391 passed / 6 skipped。
- 前端专项：3 suites / 48 tests；全量：24 suites / 348 tests。
- TypeScript、严格 Vue ESLint、Vuex action lint、生产 build、Flake8、Ruff、BtDeck 架构检查及变更文件 Black 均通过。
- 变更应用文件 Mypy 为 89 条，修改前同口径 90 条，零新增；全量 Mypy 1468 条为既有类型债。
- 根 `init.sh` 退出 0；Git Bash 前端子脚本未发现 Node，但通过指定 Node 18 独立完成全部前端测试、类型检查、lint 与构建。
- 完整 `npm run lint` 仍被既有高级搜索生成契约漂移拦截；全量 Black 仍命中 10 个未修改文件。两项均未伪报通过，也未越界修改无关文件。

### 当前工作区

- 本轮修改孤儿文件后端 API/服务/启动流程、前端 API/页面、专项测试、任务计划、代码路线图及项目记录。
- 没有新增 Alembic 迁移，没有修改 `package.json`/lockfile，没有执行 Git commit、stage 或 push。
- `.agents/`、`.claude/`、`.code-graph/`、`.codex/`、`.spec-workflow/`、`.zcode/` 为会话前已有未跟踪工具目录，保持不动。
- 当前无剩余的孤儿文件修复代码事项；若要求仓库所有全量门禁全绿，应另开范围处理高级搜索生成契约漂移与 10 个既有 Black 格式文件。

---

## 2026-07-27 交接：传统保存路径列与列表排序图标

**当前任务**: `v1.0.6.31`
**分支**: dev
**状态**: 实现、追加回归、静态检查、生产构建与根初始化检查完成；按功能与测试拆分提交，尚未推送。

### 关键结果

- 传统模式新增可配置“保存路径”列，位于“分类/标签”与“添加时间”之间；兼容驼峰/蛇形字段，空值显示 `-`，悬停可查看完整路径。
- 表格最小宽度保护名称列，窄视口继续使用表格容器内部横向滚动；虚拟滚动 colspan 会随列设置自动更新。
- 列表模式五个可排序表头均显示 Lucide 图标：未排序双向箭头，当前排序按升/降序显示单向箭头。
- 图标是装饰性信息，表头原有 `aria-sort`、键盘操作、焦点反馈及 API 排序参数全部保留。
- 追加回归覆盖旧列偏好迁移、显式隐藏的表格列计数，以及 Space 键图标切换与字符箭头防回退。

### 验证

- 目标回归 3 suites / 30 tests；追加目标回归 2 suites / 24 tests；前端全量 Jest 23 suites / 330 tests 全绿。
- TypeScript、严格 Vue ESLint、Vuex action lint、生产 build 通过。
- build 保留 48 条既有 Sass/资源体积 warning；`git diff --check` 通过。
- 根 `init.sh` 在 Git Bash 下退出 0，识别 Node v18.20.8 / npm 10.8.2。
- 完整 `npm run lint` 的 `contract:check` 命中任务开始前已有的生成契约漂移；本任务未修改高级搜索契约。

### 当前工作区

- 本轮涉及 10 个文件：4 个前端实现/样式文件、3 个测试文件、3 个项目记录文件。
- 已按功能实现与追加回归保护拆分为两个 Git commit，尚未 push；6 个未跟踪工具目录未纳入本轮修改。
- `package.json`、`package-lock.json` 与后端均无变更。

---

## 2026-07-27 交接：种子列表分页组件与列头排序对齐

**当前任务**: `v1.0.6.30`
**分支**: dev
**状态**: 实现、独立组件回归、集成回归、静态检查、生产构建与根初始化检查完成；按功能与测试拆分提交，尚未推送。

### 关键结果

- 列表模式和传统模式现在共用 `PageSizeCombobox.vue`：预设均为 20/50/100/500/1000，支持 1–100000 自定义输入，选择、Enter 或失焦应用后回到第 1 页。
- 列表模式的名称、大小、状态、比率、添加时间五个列头支持排序；首次默认降序，同字段再次操作切换方向。
- 排序列头支持鼠标、Enter、Space、`aria-sort` 和可见焦点；分页组件在移动端仍可用。
- 后端接口及 `sort_by/sort_order` 契约未变，传统模式的分页、虚拟滚动和重复任务逻辑未变。

### 验证

- 共享分页组件独立回归 1 suite / 4 tests，覆盖默认预设、公共事件、ARIA 状态与程序化聚焦。
- 列表视图集成回归 1 suite / 2 tests；前端全量 Jest 23 suites / 323 tests 全绿。
- TypeScript、严格 Vue ESLint、Vuex action lint、生产 build 通过。
- build 保留 48 条既有 Sass/资源体积 warning；`git diff --check` 通过。
- 根 `init.sh` 在 Git Bash 下退出 0，识别 Node v18.20.8 / npm 10.8.2。
- 完整 `npm run lint` 的 `contract:check` 命中任务开始前已有的生成契约漂移；本任务不涉及高级搜索协议，未更新该无关文件。

### 当前工作区

- 本轮共涉及 11 个文件：5 个前端实现/样式文件、3 个测试文件、3 个项目记录文件。
- 已按功能实现与独立回归保护拆分为两个 Git commit；未 push，既有 6 个未跟踪工具目录保持不动。
- `package.json` 与 `package-lock.json` 无变更。

---

## 2026-07-27 交接：高级搜索视觉密度与多选条件行高修正

**当前任务**: `advanced-search-ui-revamp.4`
**版本记录**: `v1.0.6.29`
**分支**: dev
**状态**: 实现、组件回归、静态检查和生产构建完成；尚未提交。

### 关键结果

- 高级多选默认态由常驻大型面板改为 32px 紧凑触发器，与字段/操作符的 `size="small"` 控件等高；完整多选功能在点击浮层中保留。
- 触发器显示首项摘要与选中数量，并补齐焦点、ARIA、自动聚焦搜索及 Esc 关闭行为。
- 高级搜索构建器正文/控件字号与组、条件、操作区间距整体收紧；种子列表高级搜索标题改为 16px 图标 + 15px 文字。
- 搜索协议、状态结构、公共 props、虚拟滚动及 `input/change` 事件载荷均未改变。

### 验证

- 高级搜索组件集：4 suites / 70 tests 全绿（新增 2 个紧凑触发器用例）。
- 全量 Vue ESLint 0 error、`tsc --noEmit`、Vuex action lint、生产 build 通过。
- build 保留 48 条既有 Sass/体积 warning；`git diff --check` 通过。
- 根 `init.sh` 在 Git Bash 下退出 0，识别 Node v18.20.8 / npm 10.8.2。
- 完整 `npm run lint` 的 `contract:check` 命中任务开始前已有的生成契约漂移；本任务不涉及协议，未更新该无关文件。

### 当前工作区

- 本轮共修改 10 个文件：4 个前端实现/测试文件、3 个项目记录文件、3 个 roadmap 文件。
- 未执行 Git commit/push；既有 6 个未跟踪工具目录保持不动。
- `package.json` 与 `package-lock.json` 无变更；仅在 `node_modules` 补齐 lockfile 已声明的 lucide。

---

## 2026-07-26 交接：最近三次提交红队加固实施（v1.0.6.27）

**当前任务**: `v1.0.6.27`
**分支**: dev
**状态**: 实现、自动化验证和运维文档完成；尚未提交，也未迁移真实本地数据库。

### 审查范围与结论

审查对象为 `0b83ac8`、`b894ca2`、`0b447df`。红队验证确认原修改仍可能在写入路径、已执行迁移、备份恢复和前后端协议漂移场景下失效，因此按 3 个子代理的独立方案审查结果完成根因加固，而非仅增加局部断言。

### 关键改动

- ratio 三态归一化覆盖同步、异步详情、CRUD 和遗留写路径；更新时区分明确 `NULL` 与暂不可用保留旧值。
- 严格修正 6132，并增加 follower revision `8f4c2d1a9b7e`、数据库 CHECK、旧 schema 入口同步。
- 迁移前备份升级为完整性、版本、SHA-256 硬门禁；新增只读数据库/备份诊断 CLI。
- 修复诊断生成 SQLite sidecar 以及保留策略误计 sidecar 的红队实跑缺陷。
- 高级搜索改为后端 JSON 单一契约、严格 422、无静默 fallback、有界真实 regex 和查询预算。
- 前端生成契约、集中状态与共用严格请求构造器覆盖模板、即时搜索和两种列表视图。
- 运维文档补充两阶段发布、零值对账和确定性恢复步骤。

### 验证结果

- 后端全量：2378 passed、6 skipped、0 failed（2384 collected）。
- 前端全量：20 suites、306 tests；lint、typecheck、contract check、build 通过。
- Flake8、BtDeck 架构门禁、Black、目标 mypy、`git diff --check` 通过。
- 全量 mypy 的 1481 个错误为既有类型债务，未纳入本轮，也未掩盖。
- 根 `init.sh` 因 Windows 仅有不可用 WSL bash 无法运行；后端与前端关键子验证均已单独完成。

### 受控发布顺序

1. 在目标环境运行：
   `python backend/scripts/ratio_migration_report.py --database <db> --expected-version 8f4c2d1a9b7e --json`
2. 对历史 `0` 做业务数据源对账；不要自动把所有 `0` 改成 `NULL`。
3. 先发布后端并允许硬门禁备份与 Alembic migration 完成，再复跑诊断确认 schema、约束和 revision。
4. 后端稳定后发布前端；观察 422、regex timeout、ratio unavailable 和备份验证指标。
5. 需要恢复时，先停写并保留故障库，再校验指定主备份：
   `python backend/scripts/ratio_migration_report.py --database <db> --backup <backup> --file-only --expected-backup-version <revision> --json`
   按 `backend/docs/operations/rollback-guide.md` 恢复，禁止直接跨 6132 downgrade。

### 当前工作区

- 真实 `backend/config/app.db` 仅做只读诊断，仍处于旧 revision `e6d8a20c41f3`，没有被迁移。
- 最新已验证主备份为 `app.db.pre-migration-20260711-194949-098`，SHA-256 为 `9db1a367892825ef296d0717d5fd806048186c1bdbd2fa4133a23a26839b7ae0`。
- 本轮没有 Git commit；用户原有未跟踪文件/目录未修改或清理。

---

## 2026-07-26 交接：高级搜索操作符前后端契约守卫测试（v1.0.6.26）

**当前任务**: `v1.0.6.26`
**分支**: dev
**状态**: 前端契约测试实现、lint、全量 unit test 完成；尚未提交。

### 起因

v1.0.6.25 后端补了 TestOperatorContractGuard，但前端无对偶守卫。本次补齐前端 Jest 契约测试，确保前端 operatorGroups 与后端 allowed_operators 双向对齐。

### 关键改动

- 新建 `frontend/tests/unit/operator-contract.spec.ts`（16 用例 4 类）
- 用源码字符串解析范式（不 mount Vue），与 field-types-consistency.spec.ts 一致
- 三层契约：backendValue 集合（含后端源码同步校验）+ value 结构对齐 + formatParamValue 输出类型
- 含降级策略 fallback 一致性检查

### 关键技术坑

- ts-jest 顶层 `/g` 正则 lastIndex 残留 → 改逐行 split + 单行 match
- 后端注释含 `{}` 字符 → 改 `indexOf` 定位结束边界
- 注释里的字符串字面量被误读 → 剔除 `#` 注释行后再提取

### 验证

- 前端 `npm run test:unit` 全量 **314 passed**（含新增 16）
- 前端 `npm run lint --max-warnings 0` 通过

### 后续与工作区

- 本轮未提交；如需提交，纳入 4 个文件（operator-contract.spec.ts + feature_list.json + progress.md + session-handoff.md）
- 防回归价值：若后端误删 allowed_operators 的 between/regex/last_days/date_range，或前端新增操作符未登记，本 spec 立即失败
- 浏览器手测待用户本地完成

---

## 2026-07-26 交接：ratio/ratio_limit 列治本（String→Float）+ 4 操作符后端实现（v1.0.6.25）

**当前任务**: `v1.0.6.25`
**分支**: dev
**状态**: 全部实现、测试、静态门禁完成；尚未提交。

### 起因

用户要求红队审查 v1.0.5.15 提交是否治标不治本。红队坐实 3 处同根 bug 未修（ratio_limit filter、ratio sort、ratio_limit sort）+ between/regex/last_days/date_range 是 422 硬失败。3 子代理独立审查方案 v1 又坐实 6 处阻断项，修订为 v2 后用户两轮决策确认范围。

### 关键改动

- **Schema 治本**：ratio/ratio_limit 列 String→Float；Alembic 迁移 `6132b66d14a7`（脏数据清洗 + batch_alter + partial unique index drop/recreate + WHERE 子句断言）
- **服务层简化**：移除 cast、新增 `NUMERIC_FIELDS = {"ratio","ratio_limit"}`、显式 `float(value)` 兜底
- **4 操作符后端实现**：between/regex/last_days/date_range（Pydantic allowed_operators 扩展 + value 接受 dict + service 层 4 套解构）
- **写入侧清理 8 处**：torrent_helpers QB/TR（含 TR 错位修复）/ torrent_sync QB 哨兵 / torrent_crud_service 默认值；新增 `_safe_float` helper 兜底 ValueError
- **前端 numberRange UI**：ConditionValueInput 模板+handler+watcher+normalizeValue+getDefaultValue；AdvancedSearchBuilder formatParamValue number+between 对象分支
- **类型契约同步**：VO schema、两份 Torrent 接口、TorrentDetailDialog 0 值修复用 formatRatio

### 验证

- Alembic 迁移实证：脏数据（""/-1/-2/"None"/"none"）全部转 NULL、partial index WHERE dr=0 保真、upgrade/downgrade 对称
- 后端全量 pytest **2315 passed**（基线 2286 + 新增 29：7 sort + 3 ratio_limit filter + 8 new operators + 1 contract guard + 4 migration + 既有断言更新）
- 后端 flake8 0；black 通过；mypy 改动区域 0 新增
- 前端 npm run lint + npm run build 通过；vue-tsc type error 2472→2473（基线抖动）
- 手动：PRAGMA table_info(torrent_info) ratio 列 FLOAT、idx_torrent_hash_unique 含 WHERE dr=0

### 后续与工作区

- 本轮未提交；如需提交，应在仓库根目录纳入本任务 16 个文件（10 后端含迁移 + 5 前端 + feature_list.json）+ progress.md + session-handoff.md
- **明确不修的边界**（独立技术债）：
  - env.py 未开 `render_as_batch`（offline SQL 生成场景，不在本次范围）
  - 前端 ratio/date 的 between UI 仅复用 sizeRange 范式补 numberRange，完整 UX 优化另议
  - torrents_async.py:1387/3125 把 `seed_ratio_limit` 映到响应 dict `ratio_limit` 键的命名习惯（与 DB 列无关）
  - CompactTable.vue 是 dead component，未删
- 浏览器手测待用户在本地完成（重点验证：种子列表按"比率"列排序、高级搜索选"比率限制"between 范围、TorrentDetailDialog ratio=0 显示）

---

## 2026-07-26 交接：高级搜索完备回归测试 + ratio bug 修复 + 死代码清理

**当前任务**: `v1.0.6.24`
**分支**: dev
**状态**: 前端实现、契约测试、静态门禁、生产构建与桌面/移动端实际渲染检查完成；尚未提交。

### 关键结果

- 两页统一使用共享管理列表页骨架，页头、筛选、数据区、表格和分页的宽度、间距、层级与现有页面对齐。
- 查询模板页将刷新/新建统一放入页头，补充筛选标签、列表说明、数量信息和空状态。
- 孤儿文件页统一四项统计卡，扫描/刷新移至页头，清理操作与已选数量收纳到数据面板，移动端统计卡自动改单列。
- 仅改 UI 结构与样式；原查询、模板 CRUD、扫描、清理、分页、API 和权限逻辑均未改动。

### 验证

- UI 契约 1 suite / 7 tests、TypeScript、完整 ESLint 与生产 build 均通过。
- build 保留既有 48 条 Sass/资源体积 warning，无新增编译错误。
- 浏览器实测 1440×900 和 390×844；两页无文档级横向溢出，移动端宽表由内部容器承接滚动。
- 根 `./init.sh` 通过；仅有 Git 工作区、jq、虚拟环境和 Git Bash Node 探测等环境提示。

### 后续与工作区

- 本轮未提交；如需提交，应在仓库根目录仅纳入本任务 8 个文件（5 个前端实现/测试文件及 3 个项目记录文件）。
- 临时 UI 验证服务、数据库与日志已清理；既有 `.agents/`、`.claude/`、`.code-graph/`、`.codex/`、`.spec-workflow/`、`.zcode/` 未跟踪目录保持不动。

---

## 2026-07-18 交接：传统分页预设与展开箭头修正完成

**当前任务**: `v1.0.6.22`
**分支**: dev
**状态**: 前端实现、回归测试、静态门禁与生产构建完成；已提交、尚未推送。

### 关键结果

- 分页组合框展开后固定显示 20/50/100/500/1000，不再因当前值是 `20` 而只显示一个候选项。
- 保持 1–100,000 手动输入与原分页行为不变。
- 右侧箭头可点击或键盘操作，向下表示收起、向上表示展开；聚焦、失焦及选择预设会同步箭头状态。
- 组件回归覆盖当前值过滤场景、完整预设列表与箭头双向切换。

### 验证

- 目标回归 3 suites/18 tests；全量 Jest 14 suites/253 tests。
- `tsc --noEmit`、完整 ESLint、Vuex lint、生产 build 与 `git diff --check` 均通过；build 仅有既有 48 条 Sass/资源体积 warning。
- 根 `init.sh` 因当前 Windows 无 WSL 无法运行。

### 后续与工作区

- 本轮已提交、尚未推送；如用户要求，可在仓库根目录推送 `dev`。
- `dev` 相对 `origin/dev` ahead 5；既有未跟踪目录、tar、批处理及 `tools/` 未纳入提交。

---

## 2026-07-18 交接：传统分页组合框与虚拟滚动完成

**当前任务**: `v1.0.6.21`
**分支**: dev
**状态**: 前端实现、回归测试、静态门禁与生产构建完成；已提交、尚未推送。

### 关键结果

- 传统模式分页大小现在只有一个可输入组合框：下拉提供 10/20/50/100，也可手工输入 1–100,000；选择、Enter、失焦语义一致。
- 传统页面锁定到视口高度，表格容器固定占据剩余空间并独立滚动，不再由当前页种子数量决定高度。
- 超长当前页使用 32px 固定行高虚拟窗口，仅渲染可视行与上下缓冲行；上下占位行保持滚动条总高度和表格列结构。
- 视口尺寸由 `ResizeObserver` 更新，滚动由 `requestAnimationFrame` 合帧；分页、筛选、排序及重复任务切换会回到顶部，服务端分页行为不变。

### 验证

- 目标回归 3 suites/18 tests；1000 条、320px 视口仅渲染 26 条可视/缓冲记录。
- 全量 Jest 14 suites/253 tests；Statements 52.48%、Branches 44.34%、Functions 44.75%、Lines 51.89%。
- `tsc --noEmit`、完整 ESLint、Vuex lint、生产 build 与 `git diff --check` 均通过；build 仅有既有 48 条 Sass/资源体积 warning。
- 根 `init.sh` 因当前 Windows 无 WSL 无法运行；浏览器可加载本地生产构建，但未登录环境被路由守卫停在登录页。

### 后续与工作区

- 本轮已提交、尚未推送；如用户要求，可在仓库根目录推送 `dev`。
- `dev` 相对 `origin/dev` ahead 4；既有未跟踪目录、tar、批处理及 `tools/` 未纳入提交。

---

## 2026-07-18 交接：传统种子页回归覆盖补强完成

**当前任务**: `v1.0.6.20`
**分支**: dev
**状态**: 回归测试补强、覆盖率核算、静态门禁与生产构建完成；已提交、尚未推送。

### 关键结果

- `TraditionalView` 现在有 7 项组件级回归，覆盖唯一“删除”下拉、Tracker/文件/Peers 页签、完整分类标签、自定义分页边界、重复任务模式保持及关键布局契约。
- `TraditionalView.vue` 已纳入 Jest 覆盖率采集；模板可选链仅改为等价显式判空，以兼容 Vue 2 Jest 模板编译。
- qB 增量详情的分批、去重、正常与重试分支，以及 Transmission 实时元数据和失败降级均有服务级回归。
- 重复任务端点补充两下载器同 hash 的 Transmission 集成用例；分类/标签聚合确认软删除和回收站数据不会混入结果。

### 验证

- 前端组件回归 7/7；全量 Jest 13 suites/246 tests，Statements 51.91%、Branches 43.26%、Functions 44.63%、Lines 51.34%。
- 后端受影响专项 78/78；`torrents_async.py` 本次新增可执行行 9/9，`torrent_metadata.py` 本次新增可执行行 157/199（78.9%）。
- `tsc --noEmit`、完整 ESLint、Vuex lint、后端目标 flake8、Ruff 格式检查、前端生产 build 与 `git diff --check` 均通过。
- 浏览器确认本地生产构建可加载；无登录/API 环境，被路由守卫停在登录页，真实种子页布局由组件与静态布局契约回归兜底。

### 后续与工作区

- 本轮补充已提交、尚未推送；如用户要求，可在仓库根目录推送 `dev`。
- `dev` 相对 `origin/dev` ahead 3；既有未跟踪目录、tar、批处理及 `tools/` 未纳入提交。

---

## 2026-07-18 交接：传统元数据悬浮窗与自定义分页完成

**当前任务**: `v1.0.6.19`
**分支**: dev
**状态**: 前后端实现、边界测试、静态门禁与生产构建完成；尚未提交。

### 关键结果

- 传统模式元数据面板现在悬浮覆盖在分页栏上方，不再作为列表下方的布局区域；面板开关不会挤压列表或分页。
- 分页栏保留预设选项，并支持手工输入每页数量；Enter/失焦生效，合法范围 1–100,000，应用后回到第 1 页。
- 普通列表与重复任务接口均接受 100,000，并拒绝 100,001，前后端限制一致。
- 重复任务模式仍保持独立翻页、改页大小和刷新，不会意外回到普通列表。

### 验证

- 后端受影响专项 71/71；flake8、目标 Ruff 格式通过；新增重复元数据端点/服务目标 mypy 无错误。
- 前端目标测试 7/7、全量 Jest 12 suites/239 tests；`tsc --noEmit`、完整 ESLint、Vuex lint、生产 build 通过。
- `git diff --check` 通过；生产构建可由浏览器加载，但无登录/API 环境只能到登录页。
- 全文件 Ruff/mypy 仍会命中 `torrent_crud.py`、`torrents_async.py`、`tag_management.py` 的历史格式/类型债务，本轮未做无关整文件重排或债务扩展。

### 后续与工作区

- 本轮未提交或推送；若用户要求，需在根目录仅暂存本任务及前序同批任务文件和三份项目记录。
- `dev` 相对 `origin/dev` 仍 ahead 1；既有未跟踪目录、tar、批处理及 `tools/` 不纳入提交。

---

## 2026-07-18 交接：传统种子页四项调整完成

**当前任务**: `v1.0.6.18`
**分支**: dev
**状态**: 前后端实现、专项测试与静态门禁完成；尚未提交。

### 关键结果

- 传统模式仅保留等级删除下拉，入口文案为“删除”，四个等级及其原有处理链路保持不变。
- 左侧过滤区可随视口纵向滚动；分类与标签列表合并管理数据和活动种子实际使用数据，避免未登记但已在使用的项缺失。
- 重复任务响应对空数据库记录先做同 hash 固有字段回填，再使用缓存下载器连接补齐完整元数据；连接不可用时退化为数据库结果。
- qB 增量同步会在写库前将部分 delta 水合为完整详情，阻止后续把完整字段重新覆盖为空。
- 元数据面板位于列表下方，移除“常规”，默认 Tracker；重复任务翻页、改页大小和刷新不会跳回普通列表。

### 验证

- 后端专项 40/40；目标 flake8、mypy、`ruff format --check` 通过。
- 前端目标测试 3/3；`tsc --noEmit`、完整 ESLint、Vuex lint、生产 build 通过。
- `git diff --check` 通过；根 `init.sh` 因当前 Windows 无 WSL 无法执行。
- 本地生产构建可在浏览器加载，但无登录/API 环境只能到登录页，未完成真实种子页面交互核验。

### 后续与工作区

- 本轮未提交或推送；如用户要求，需在根目录仅暂存本任务文件及三份项目记录，再提交。
- `dev` 相对 `origin/dev` 仍 ahead 1（此前提交）；既有未跟踪目录、tar、批处理及 `tools/` 不纳入提交。

---

## 2026-07-18 交接：传统模式活动筛选迁移完成

**当前任务**: `v1.0.6.17`
**分支**: dev
**状态**: 实现与前端全量验证完成；本次 Git 操作仅包含下述任务文件与项目记录。

### 关键结果

- 传统模式工具栏顶部不再显示“活动”复选框。
- 左侧状态过滤器现在按“全部 → 活动中 → 做种中”排列，其余状态顺序保持不变。
- “活动中”仍复用既有 `showActiveOnly → active_only` 请求链路；与普通状态选项互斥，不改变列表模式。
- 状态构建、选中值还原和选择解析已提取为纯函数，并由 3 项契约测试覆盖。

### 验证

- 目标测试：3/3 passed；前端全量：11 suites / 235 tests。
- `tsc --noEmit`、完整 ESLint、Vuex lint、生产 build、`git diff --check` 均通过。
- 根 `init.sh` 已尝试，但当前 Windows 环境没有 WSL，系统 `bash.exe` 无法运行脚本；前端各门禁已通过项目本地 CLI 逐项执行。

---

## 2026-07-17 交接：下载器设置端点 mypy 11 项债务清零

**当前任务**: `v1.0.6.16`
**分支**: dev
**状态**: 类型修复与全量验证完成，待本地提交；网络推送受安全策略阻止。

### 关键结果

- `downloader_settings.py` 目标 mypy 从 11 errors 降至 0。
- 11 项按四类收敛：SQLAlchemy 标量/游标结果、FastAPI Request 注入、响应字典注解、两种下载器 SDK 客户端变量隔离。
- API 路径、CommonResponse 结构、下载器连接与测试连接业务流程均未改变。

### 验证

- `mypy app/api/endpoints/downloader_settings.py`：Success，无错误。
- 下载器设置与认证专项：33/33 passed。
- 后端全量：2111 passed / 1 skipped。
- 变更文件 flake8、`git diff --check` 通过。

### Git 与推送

- 限速修复已提交为 `2e03ce4`。
- 自动推送 `origin/dev` 被安全策略硬性拒绝；用户已知情确认，但审核明确说明确认不能覆盖，未进行任何绕过。
- 完成本轮提交后，用户可在本机执行 `git push origin dev` 一次性推送两个提交。

---

## 2026-07-17 交接：下载器全局限速同步应用修复完成

**当前任务**: `v1.0.6.15`
**分支**: dev
**状态**: 根因修复与全量验证完成，尚未提交。

### 关键结果

- 保存接口不再让分时段规则变量覆盖全局上传/下载限速，合法的 0 值也不会被回退字段吞掉。
- 原始 SQL 返回的速度单位字符串 `"0"/"1"`、SQLAlchemy Enum 名和 KB/s/MB/s 表示已统一归一化；qBittorrent 与 Transmission 的单位换算均由端到端 mock 应用断言覆盖。
- 定时调度以全局限速为基线：无生效规则恢复全局值，规则中未启用的单方向继续保留对应全局值。
- 前端保留 `enable_schedule` 的真实持久化状态，不再因历史规则存在而错误重启调度。
- 原 15 项测试中的错误预期已纠正，调度服务 15/15 通过；新增下载器双适配器和前端状态契约回归。

### 验证

- 后端：最终专项回归 48/48（设置 API 17、枚举 16、调度 15）；全量 pytest 2111 passed / 1 skipped。
- 前端：10 suites / 232 tests；`tsc --noEmit`、完整 ESLint、Vuex lint、生产 build 均通过。
- 变更文件 flake8、`git diff --check`、根 `init.sh` 通过。
- 当前环境的 `black 24.10.0` 连 `--version` 都会卡住超时，未能执行；mypy 的 11 项输出均是历史端点既有类型债务。

### 工作区说明

- 本轮未执行 Git 提交。
- `.agents/`、`.claude/`、`.codex/`、`.spec-workflow/`、`.zcode/` 为会话开始前已有未跟踪目录；`.code-graph/` 是本轮排查按技能生成的代码图谱缓存，均未纳入业务修改。

---

## 2026-07-17 交接：种子同步添加时间显示 1970 修复完成

**当前任务**: `v1.0.6.14`
**分支**: dev
**状态**: 根因定位、最小修复和回归验证均已完成，尚未提交。

### 关键结果

- 数据同步与 API ISO 8601 序列化正常；问题位于前端共享 `formatDate`。
- 旧逻辑把 ISO 字符串 `2026-07-17T10:20:30` 用 `parseInt` 截成 `2026` 秒，稳定复现 `1970-01-01 08:33:46`。
- 现仅把完全为数字的字符串当时间戳，ISO 日期字符串整体解析；数字秒时间戳字符串继续兼容。
- 共享工具回归测试已拆分，覆盖本地 ISO、带 `Z`/显式时区偏移的小数秒 ISO，以及秒级/毫秒级数值字符串。

### 验证

- 目标测试：Asia/Shanghai、UTC、America/New_York 三时区均为 42 passed。
- 全量前端：9 suites / 229 tests；四项覆盖率均通过 40% 门禁。
- TypeScript、ESLint、Vuex lint、生产 build、`git diff --check` 均通过。
- 生产 build 的 48 条 Sass/资源告警均为既有告警。

---

## 2026-07-16 交接：前端覆盖率门禁与关键测试整改完成

**当前任务**: `v1.0.6.13`
**分支**: dev
**状态**: 实现与验证完成，尚未提交。

### 关键结果

- 测试从 4 suites / 142 tests 提升到 8 suites / 222 tests。
- 有效覆盖率：Statements 50.03%、Branches 42.01%、Functions 43.04%、Lines 49.47%。
- Jest 四项全局阈值均为 40%；CI 运行 `test:coverage` 并上传 HTML/LCOV artifact。
- 覆盖率口径覆盖全部业务 TS 和两个已测试关键 SFC，排除声明、生成图标和启动入口。
- 新增 API 契约、共享工具、Vuex、高级搜索组件回归；修复规范化覆盖顺序和 `queuedDL` 两个真实缺陷。

### 验证

- `vue-cli-service test:unit --runInBand --coverage --silent`：222 passed，覆盖率门禁通过。
- `tsc --noEmit`：通过。
- 目标 ESLint：0 error（6 条既有 warning）。
- 生产 build：通过（48 条既有 warning）。
- `git diff --check`：通过。

### 后续边界

- 其余历史 Vue SFC 尚未全部进入覆盖率分母；应按关键页面组件测试逐步纳入，不能直接全量采集后忽略 Vue 2 模板编译失败。
- 浏览器 E2E、真实前后端集成链路仍待后续专项。
- `.zcode/`、镜像 tar、旧 pytest 目录、个人 `tools/` 等无关未跟踪文件继续保持不动。

---

## 2026-07-16 交接：全栈回归测试质量 P0 整改完成

**当前任务**: `v1.0.6.12`
**分支**: dev
**状态**: 实现与验证完成；本次会话提交并推送。

### 关键结果

- pytest 进程级独立数据库 + 真实 Alembic，禁止访问开发业务库；`OrphanScanner` session factory 可注入。
- 活动种子快照采用五态语义；非权威快照返回 206，权威空快照返回 200；前端保留列表、刷新后受控重试。
- 大活动集合通过 SQLite TEMP 表复合键联接；600 键在变量限制降到 50 时仍通过且无临时表泄漏。
- Jest 组件测试恢复收集，TypeScript 请求契约补齐；根级 GitHub Actions 统一前后端回归门禁。

### 验证

- 后端：2089 passed, 1 skipped；coverage 40.58%；架构检查通过。
- 前端：4 suites / 142 tests；`tsc --noEmit`；生产 build 通过。
- 变更文件 black/flake8 与 `git diff --check` 通过。
- `backend/config/app.db` 测试前后 SHA256 `FBC031EF2CC021D34AE86218A0F6482CC60E917F8EB0A1D3B1627BF93A081A94`、大小与 mtime 均不变。
- 根 `init.sh` 在 Git Bash 下退出 0；Git Bash PATH 的 Node 警告由独立 Node 门禁覆盖。

### 已知技术债

- 全仓 mypy 基线：1534 errors / 123 files。
- 全量测试目录 flake8 仍有既有债务；本次变更文件为 0 错误。
- Vue SFC 历史语义类型债务未纳入本次 P0；`.ts/.tsx` 严格门禁、SFC 编译与组件测试均已启用。

### 未纳入提交

- `.zcode/`、镜像 tar、旧 pytest 输出目录、个人 `tools/`、`.docker_temp_482561487` 等用户未跟踪文件。

---

## 2026-07-12 交接：v1.0.6 孤儿文件安全闭环修复完成

**当前任务**: `v1.0.6.11`
**状态**: 实现与验证完成，尚未提交（用户未要求 commit）。

### 关键结果

- 实时下载器 inventory 是扫描与清理的唯一权威 manifest；不完整即拒绝。
- 手动/自动清理都只做可恢复隔离，不直接删除源文件；到期 purge 采用 tombstone 二次复核。
- scan_id、授权扫描根、完整文件身份、统一维护 lease 和操作 journal 构成清理门禁。
- 扫描最终 DB 写入已事务化；通知失败由每小时补偿任务重试；隔离区由每日任务清除。
- 新迁移：`e6d8a20c41f3_orphan_operation_journal.py`，接在已发布的 `b075727f7182` 后。

### 验证

- 后端相关：152 passed, 1 skipped
- 后端全量：2068 passed, 1 skipped
- flake8 / git diff --check：通过
- 前端目标 eslint / 生产 build：通过（仅既有 warning）
- 根 `init.sh`：当前 Windows 环境缺少 Git Bash/WSL，未执行

### 注意

- 未触碰用户文件：`.zcode/`、`btdeck-backend.latest.tar`、`btdeck-frontend.latest.tar`。
- 工作区内遗留若干 pytest 临时目录因 Windows ACL 无法普通删除；均为未跟踪测试产物，不应提交。

---

## 2026-07-10 交接：v1.0.6 孤儿文件管理与路径维护完成

**当前任务**: `v1.0.6`（合并原 v1.0.6 孤儿文件 + v1.0.7 路径扫描增强 + v1.1.0 自动清理）
**状态**: done。6 阶段全部完成。
**计划文件**: `PLANS/v1.0.6.md`（基于代码现状重写，废弃 2024-04-22 旧计划）
**分支**: dev

### 本轮完成

合并三版本为一个功能集群，实现孤儿文件发现→清理→自动化完整链路：

1. **后端数据模型**：OrphanScanResult + OrphanFile 两表 + Alembic 迁移 c3f1a8b7d902（含 inspect 守卫）+ 4 项配置
2. **扫描引擎**：OrphanScanner（路径收集 to_thread + 文件清单 call_downloader_api INTERACTIVE + inode 去重 + 遍历判定 + db_write_scope 批量写入）
3. **清理服务**：OrphanFileService（分页查询/预览/手动清理/自动清理超期，文件删除参考 recycle_bin_service UNC 兼容 + 审计日志）
4. **API 端点**：5 端点（latest/list/scan/cleanup-preview/cleanup），require_authenticated_user 认证 + CommonResponse 响应
5. **定时任务**：OrphanScanTask 每周日 2 点扫描+清理合一，task_profiles 三处同步（orphan_scan_cleanup heavy_sync wait_timeout=60）
6. **bug 修复**：CleanupTaskExecutor _query_level3/4_torrents 未定义方法补全（task_type=5 触发路径原会 AttributeError）
7. **前端**：orphan-files.ts API + index.vue 管理页（class 风格 Options API + 统计卡片 + el-table + el-pagination + 清理两步确认）+ 路由注册

### 验证结果

- 新增 46 测试全 pass（扫描器 19 + API 认证 14 + 任务治理 13）
- 全量 pytest **1997 passed, 0 failed**（基线 1937→1997 净增 60，零回归）
- black/flake8 通过；./init.sh 通过
- 前端 eslint 0 error + build 成功（tsc 通过，orphan-files chunk 生成）

### 关键设计决策

1. **合并三版本**：v1.0.6+v1.0.7+v1.1.0 本质一个功能集群，拆三版本导致接口割裂
2. **复用 cron_executor**：不新建 AutomationService（与现有调度框架重复）
3. **实时调下载器 API**：复用 QBittorrentDeleteAdapter/TransmissionDeleteAdapter 的 get_torrent_files，经 INTERACTIVE lane 受 per-downloader 限流
4. **治理合规**：to_thread 移出同步操作 + db_write_scope 串行化 + task_profiles 三处同步
5. **迁移 inspect 守卫**：orphan_file_tables 迁移加 inspect 守卫（表已存在时 no-op），与 search_templates 迁移风格一致

### 快速恢复

```bash
cd backend
# 跑本轮新测试
python -m pytest tests/services/test_orphan_scanner.py tests/api/test_orphan_files_api.py tests/tasks/test_orphan_scan_task.py -v
# 全量回归
python -m pytest tests/ -q
# 前端验证
cd ../frontend && npx eslint src/api/orphan-files.ts src/views/orphan-files/index.vue && npx vue-cli-service build
```

### 下一步可选方向

1. **v1.0.8 数据库升级（PostgreSQL）**：推迟中，先验证 sync-resource-governance 治理效果。若治理后无 DB 瓶颈可无限期推迟
2. **真实环境压测**：孤儿文件扫描在真实多下载器 + 大量种子场景的性能验证（文件清单获取是瓶颈，受 per-downloader 并发限制）
3. **P3 已知技术债**：全量同步 + API 触发路径接入 db_write_scope（sync-resource-governance 遗留）
4. **前端 index.vue 4 等级删除迁移**（traditional-view-align 遗留技术债）

---

## 历史交接（按时间倒序，精简归档）

### 2026-07-10 - SQLite 写锁治理完善（to_thread 止血 + db_write_scope 收尾）

- 4 个重型任务（judge/message_logger/reannounce/path_scan）的 execute() 体内阻塞式 SessionLocal/HTTP 调用改 to_thread 移出循环 + db_write_scope 串行化。
- busy_timeout 30000→15000 + sync/async engine timeout 30→15。

### 2026-07-05 - sync-resource-governance code review 修复轮完成

- 4 项治理机制缺陷修复（threading.Semaphore + 速度接口接入 INTERACTIVE lane + 日志聚合 + lifecycle shutdown）。
- 全量 1937 passed 0 failed。

修复 sync-resource-governance code review 发现的 4 项治理机制缺陷：

1. **DownloaderApiRuntime 超时突破真实 per-downloader 并发上限**
   - `asyncio.Semaphore` → `threading.Semaphore`（由 executor 内 wrapper 线程自身 acquire/release），
     确保"同步线程实际结束前不释放容量"。超时后底层线程仍持有令牌，新调用阻塞直到 release。
   - 新增 `test_timeout_does_not_break_real_concurrency_cap`（mutation 反向验证：buggy 实现并发达 5 突破 limit=2）。
2. **实时速度接口绕过 runtime 旁路限流**
   - `torrent_speed.py` 删除独立 `_speed_executor`，`_call_with_timeout` 接入 `DownloadLane.INTERACTIVE` +
     `timeout=_DOWNLOADER_TIMEOUT`，复用 per-downloader 限流避免前端 1s 轮询成为旁路压力源。
3. **日志/flush 节流落地**
   - 新增 `_CallStatsAggregator` 按 `(lane, method, downloader_id)` 窗口聚合（落地
     `SYNC_DISK_FLUSH_INTERVAL_SECONDS`）。成功路径不逐条 info；失败路径 runtime 层降级 debug
     （避免与业务侧 error 双重放大）；shutdown 强制 flush。**不动** DB 写治理（`SYNC_DB_COMMIT_BATCH_SIZE`）。
4. **runtime.shutdown 接入生命周期**
   - `lifecycle.py` finally 块调用 `downloader_api_runtime.shutdown()`（关闭三 lane executor + flush 统计），
     删除已废弃的 `_speed_executor.shutdown` 引用。

### 验证结果

- 相关测试（runtime + speed + architecture）：60 passed
- 全量 `pytest tests/`：**1937 passed, 0 failed**（基线 1926→1937，净增 11 测试，零回归）
- black / flake8：通过
- `./init.sh`：通过
- mutation 反向验证：问题1（buggy 并发达 5）、问题4（删 shutdown AST 报红）均验证测试有效

### sync-resource-governance 整体完成度

| 阶段 | 内容 | 状态 |
|------|------|------|
| 0+1 | TaskAdmissionController（heavy_sync 背压 + 同类去重） | ✅ |
| 2 | DownloaderApiRuntime（三 lane 隔离 + per-downloader 限流 + qB tracker 并发治理） | ✅ |
| 2.5 | DB 写入治理（变更检测 + 批量 upsert + db_write_scope 串行化） | ✅ |
| 3 | 验证与证据归档（架构约束 + 行为契约 + 压测脚本） | ✅ |
| 4 | code review 修复轮（超时并发 + 速度旁路 + 日志节流 + 生命周期） | ✅ |

### 已知技术债（留 P3）

- `qb_add_torrents_async`/`tr_add_torrents_async` 全量同步仍调单种子版 sync_add_tracker_async，不经 db_write_scope。
- `torrent_sync.py` API 手动触发路径不经 db_write_scope。
- 真实生产环境的压测（含真实多下载器 + 真实 qB/TR 实例 + 真实种子规模）需运维用 sync_resource_benchmark.py 跑。

### 快速恢复

```bash
cd backend
# 跑本轮新测试
python -m pytest tests/services/test_downloader_api_runtime.py tests/api/test_torrent_speed_regression.py tests/test_architecture_constraints.py -v
# 全量回归
python -m pytest tests/ -q
```

### 下一步可选方向

sync-resource-governance 任务已全部完成（含 code review 修复）。剩余可选方向：
1. **P3 已知技术债**：全量同步 + API 触发路径接入 db_write_scope
2. **真实环境压测**：运维在 staging/生产用 sync_resource_benchmark.py 跑，对比部署前后
3. **DBWriteQueue**（后续独立版本）：当前任务完成后若仍显示 DB 写锁等待，作为独立版本重新设计
4. 切换到其它任务

---

## 历史交接（按时间倒序，精简归档）

### 2026-07-04 - sync-resource-governance 阶段 3 完成（验证与证据归档）

- 架构约束测试（请求探针模块不碰治理锁）+ 3 行为契约测试 + 压测脚本（6 场景，P50/P95<1ms）。
- 阶段 0/1/2/2.5/3 全部完成（code review 修复前的状态）。

### 2026-07-04 - sync-resource-governance 阶段 2.5 完成（DB 写入治理）

- sync_db_write.py 公共工具（变更检测 + 批量 upsert + db_write_scope）。
- 28 个新单测（21 纯函数+mock + 7 真实 SQLite 部分索引集成测试）。

### 2026-07-04 - sync-resource-governance 阶段 2 完成（下载器 API 调用隔离）

- DownloaderApiRuntime 三 lane 独立 ThreadPoolExecutor + per-downloader Semaphore + call_downloader_api 统一封装。
- torrents_async.py 16 处 asyncio.to_thread 全量迁移。

### 2026-07-04 - sync-resource-governance 阶段 0+1 完成（调度器资源背压）

- TaskAdmissionController（heavy_sync 全局令牌 + per-task_code 运行/排队登记 + 同类去重跳过）。
- 39 个新单测 + 5 处 mutation 反向验证。

### 2026-06-28 - 后端回归测试补全专项

- 为 6 个零覆盖接口补 API 级回归测试（审计日志/仪表盘/种子删除/cron安全/种子转移/下载器设置）。
- 14 commit，+135 测试，全量 tests/api/ 462 passed。

---

## 会话信息

**当前分支**: dev
**当前开发版本**: sync-resource-governance（已 done）
**最后更新**: 2026-07-05
---

## 2026-07-10 交接：质量门禁可信化（前端 warning 已清零）
**当前任务**：`quality-gate-hardening`

- 已完成：根/后端/前端 init 的 lint 吞错修复；后端 Black/Flake8/Ruff/custom lint 接入；自定义架构 lint 全规则负向样例；前端 Vuex action lint 可测试化；前端 129 条 ESLint warning 清零。
- 已验证：`backend/tests/test_architecture_constraints.py` 21 passed；后端 Black/Flake8/Ruff 通过；`frontend npm run lint` 通过且执行 `lint-vuex-action`；`npm run test:unit -- lint-vuex-action.spec.ts` 2 passed。
- 仍需独立处理：`python -m mypy app` 暴露历史类型债务，当前严格入口会真实失败；不要恢复 `|| echo`、不要降低 warning 阈值、不要关闭自定义规则。
- 下一步建议：把 Mypy 债务拆成独立 SQLAlchemy/Pydantic 类型治理任务，避免混进 lint 可信化修复。

---

## 2026-07-18 交接：传统模式 code review 修复完成

**当前分支**：`dev`

**当前任务**：传统模式十万分页、元数据补全、qB RID 原子性及同 hash 跨下载器行身份修复

**状态**：实现与回归完成，尚未提交或推送

### 已完成

- qB 首次/增量/重试同步只在持久化成功后推进 RID，失败时保留差量重试机会。
- qB/Transmission 元数据批处理、批次故障隔离、有界缓存及轮转补全已落地。
- 重复任务与高级搜索支持 100000 分页而不产生超大 `IN` 或 N+1 查询，排序具有稳定唯一键。
- 传统模式同 hash 不同下载器的选择、详情、删除、速度及高亮完全隔离；活动排序覆盖 100000 条性能场景。
- 分页组合框、过滤按钮、请求竞争和虚拟列表生命周期的组件回归已补齐。

### 验证

- 后端全量：`2154 passed, 1 skipped`。
- 前端全量：`16 suites, 265 tests`；TypeScript、严格 ESLint、Vuex lint、生产 build 通过。
- 变更文件 Flake8、Ruff、Black API 格式校验和 `git diff --check` 通过。
- 根 `init.sh`：当前 Windows 环境无可用 WSL，无法直接执行。
- Mypy：元数据独立模块目标检查通过；`torrent_helpers.py`、`torrents_async.py` 与高级搜索服务仍暴露项目既有 SQLAlchemy/VO 类型债务。

### 工作区注意事项

- 本轮未执行 Git 提交或推送。
- `.pnpm-store/` 是本轮前端验证产生的 8 KB 未跟踪缓存；清理操作因工具审批额度限制未执行。其余既有未跟踪文件均未改动。

---

## 2026-08-01 交接：隔离区页签刷新渲染错误修复

**当前分支**：`dev`

**本轮任务**：修复孤儿文件页面隔离区页签刷新后 `formatFileSize is not a function`。

### 已完成

- 根因确认：提交 `9891b84` 的隔离区大小列调用了未暴露为组件实例方法的 `formatFileSize`；组件已有 `formatSize` 包装方法。
- `frontend/src/views/orphan-files/index.vue` 已改为调用 `formatSize(row.file_size)`。
- `frontend/tests/unit/orphan-files.spec.ts` 新增隔离区 scoped slot 渲染回归测试，并补齐隔离区 API mock。
- `frontend/tests/unit/api-contracts.spec.ts` 同步 `9891b84` 已交付的 cleanup 300000ms 超时契约断言。

### 验证

- `npm.cmd run test:unit -- orphan-files.spec.ts`：17 passed。
- 前端全量 Jest：27 suites / 405 tests passed。
- `npm.cmd run typecheck`：通过。
- `npm.cmd run lint`：通过。
- `npm.cmd run build`：通过；仅有既有 Sass/Element UI 弃用警告。
- 根 `bash ./init.sh --ci`：当前 Windows 沙箱调用 `C:\Windows\System32\bash.exe` 返回 `E_ACCESSDENIED`，未执行脚本内容。

### 工作区注意事项

- 本轮未执行 Git 提交、推送或实际部署。
- 保留工作区原有未跟踪文件；本轮仅修改前端视图、前端单测、API 契约测试及根进度记录文件。

---

## 2026-08-01 交接：隔离区彻底删除异步化与 ID 空目录修复

**当前分支**：`dev`

**用户确认的实现口径**：持久化任务 + HTTP 立即返回 + 进程重启恢复；结果以总数/成功/失败/失败明细写入通知中心；目录治理仅删除记录隔离根内的空 UUID/scan-id 目录，禁止递归删除。

### 已完成

- 新增 Alembic `c7d8e9f0a1b2` 和 `OrphanPurgeJob`，迁移表/索引幂等且可 downgrade。
- 新增 `OrphanPurgeJobService`/`OrphanPurgeJobDispatcher`：落库、原子领取、串行后台执行、重启恢复、幂等通知和关闭取消。
- `POST /api/v1/orphan-files/purge` 只提交任务；新增 `GET /api/v1/orphan-files/purge-jobs/{task_id}`。
- 通知补偿任务已扩展到彻底删除终态，dedupe key 为 `orphan_purge:{task_id}`。
- 前端提交后立即解除 loading，显示任务 ID 并告知用户在通知中心查收；取消 purge 的 300000ms 等待。
- 已证实目录增长根因：原 UUID 目录 + 每次新建 tombstone UUID 目录都未在文件移走/删除后 `rmdir`，单次从 1 变 2；预写失败和重试会继续放大。
- 现在 quarantine/restore/expired purge/manual purge/recovery 全部回收空操作目录，并在启动和任务后扫描数据库仍可追溯根下的历史空 UUID 目录。

### 安全边界

- 仅用 `os.rmdir`；非空、符号链接、越界、权限失败均保留并记录，不会删除全局 `.btdeck_quarantine` 父目录。
- 未放宽原有 manifest、下载器授权、身份字段、lease 和 TOCTOU 安全检查。

### 验证

- 后端全量：`2514 passed, 6 skipped`。
- 前端全量：`27 suites, 407 tests passed`；typecheck/lint/build 通过，build 仅既有 Sass/Element UI 弃用警告。
- 新任务模型+服务 mypy 通过；本次后端实现文件 Black 通过，`flake8 app` 全量通过；`git diff --check` 通过。
- 全量 mypy 仍有仓库既有 1533 个错误，全量 Black 仍有 9 个未修改旧文件的格式差异。
- 根 `bash ./init.sh` 在当前 Windows 环境被 `Bash/Service/CreateInstance/E_ACCESSDENIED` 阻断。

### 工作区注意事项

- 未执行 Git 提交、推送或部署。
- 未跟踪的备份 DB、镜像 tar、调试脚本、工具目录等均为任务前已有，本轮保留不动。

---

## 2026-08-01 交接：部署后旧 SPA 路由 ChunkLoadError 修复

**当前分支**：`dev`

**本轮任务**：修复重新部署后打开孤儿文件页面时，旧 `app` runtime 请求已删除路由 chunk 导致的 404 / `ChunkLoadError`。

### 根因证据

- 报错标签页运行 `app.64d1d8fb.js`，请求旧 `orphan-files.15d0574e.js` / `475718e4.css`。
- 线上当前 index 已是 `app.e237e2cd.js`，其当前 orphan JS/CSS 映射均返回 200；旧哈希返回 404。因此当前容器构建完整，主因是部署前已打开 SPA 没有重新加载入口。
- Docker Compose 是单前端容器，静态 HTML 无 volume 覆盖，排除了多副本与宿主目录混写。
- `/service-worker.js` 原先也被缓存一年且预缓存 app shell；当前入口未主动注册它，但历史 worker 是需治理的版本驻留放大因素。

### 已完成

- 新增 `frontend/src/utils/deployment-recovery.ts`：chunk 错误识别、保留 hash 路由的一次整页恢复、query/session 60 秒防循环、成功后 query 清理，以及历史根作用域 Workbox 注册/cache 精确清退。
- `router.ts` 接入 `router.onError`；`main.ts` 启动清退旧 worker，并在初始路由成功后清理恢复 query。
- `nginx.conf` 只对 `/assets/` 哈希资源设置一年 immutable；`service-worker.js` 改为 no-store，旧 chunk 保持真实 404。
- 新增 11 项部署恢复与 nginx 契约回归。

### 验证

- 前端全量：`28 suites / 418 tests passed`；typecheck、lint、生产 build 通过。
- `nginx -t` 通过；一次性容器 HTTP 实测 index/service-worker no-store、当前哈希资源 200 immutable、旧 chunk 404。
- 根 `bash ./init.sh` 被本机 WSL `E_ACCESSDENIED` 阻断。

### 工作区注意事项

- 未提交、未推送、未部署；要让当前已打开的旧页面恢复，首次部署本修复后仍需人工刷新一次，此后版本切换由客户端自动恢复。
- 任务开始前已有的后端修改、镜像 tar、备份数据库、调试脚本和工具目录均保留未动。

---

## 2026-08-01 交接：隔离区彻底删除误用原始路径映射修复

### 用户确认的语义

隔离文件已经移动到 `.btdeck_quarantine`；彻底删除必须使用隔离记录中的实际文件路径，不能再次通过下载器路径映射推导物理删除路径。原始 `canonical_path` 只作为候选主键、展示信息和“是否重新被种子引用”的复核依据。

### 根因与修复

- `purge_expired_quarantine`、手动 `purge_quarantine_now` 及 `purge_pending` 恢复分支原先调用 `_path_authorized(candidate, manifest)`，该方法会用原始 `canonical_path` 对当前下载器映射后的扫描根做授权。
- 当原始内部路径形成 `/Downloads/ipan/Downloads/...` 重复前缀，或当前映射与隔离时不同，文件虽然仍在 `.btdeck_quarantine`，却被误报“路径未授权或身份字段不完整”。
- 新增 `_quarantine_path_authorized`：仅校验实时下载器清单完整，以及持久化 `quarantine_path` 位于持久化 `quarantine_root` 内；物理删除/tombstone/恢复均不通过下载器映射寻找隔离文件。
- 保留 manifest 引用复核、size/mtime/inode 身份复核、隔离根逃逸、tombstone、TOCTOU 和维护 lease；原始文件的隔离前流程仍继续使用 `_path_authorized`。

### 变更文件

- `backend/app/services/orphan_file_service.py`
- `backend/tests/services/test_orphan_cleanup_safety.py`
- `feature_list.json`
- `progress.md`

### 验证与交付状态

- 隔离安全回归：35 passed / 1 skipped。
- manifest/API/异步任务回归：49 passed。
- 后端全量：2515 passed / 6 skipped。
- 目标代码 Black 行范围、Flake8 通过；全量 mypy 的 SQLAlchemy Column 类型错误为既有债务。
- 未提交、未推送、未部署。根 `bash ./init.sh` 仍受 Windows WSL `E_ACCESSDENIED` 阻断。

---

## 2026-08-01 交接：隔离区删除失败二次修复与旧镜像包识别

### 最终根因判断

当前源码已经不再包含旧的“隔离区路径未授权或身份字段不完整，拒绝删除”物理删除分支；但工作区 `btdeck-backend.latest.tar` 仍包含该旧文案，且其导出时间早于本轮源码修改。因此此前“重新部署后仍报错”最符合的原因是部署加载了旧后端 tar/镜像，而不是当前修复逻辑再次把隔离文件映射回原始下载路径。

### 当前实现语义

- `purge_quarantine_now`、自动到期 purge、`purge_pending` 恢复只使用数据库候选记录的 `quarantine_path`；`quarantine_root` 负责绝对路径、根边界和符号链接安全校验。
- 下载器实时 manifest 不再授权或推导隔离文件的物理路径；仅可选复核原始 `canonical_path` 是否重新被种子引用。
- 旧隔离记录缺少身份字段时，先在隔离根校验通过后按实际隔离文件补齐缺失字段；已有字段不匹配、文件身份变化仍拒绝删除。
- 异步任务失败通知同时输出 `canonical_path` 与 `quarantine_path`，方便确认是否仍错误使用 `/Downloads/ipan/Downloads/...`。

### 本轮验证

- `test_orphan_cleanup_safety.py`：40 passed / 1 skipped。
- 选定后端回归（隔离安全、manifest、API、异步任务、忽视态、扫描任务）：126 passed / 1 skipped。
- 目标后端 Flake8、Black diff、`git diff --check` 通过；前端 typecheck、lint、unit、build 通过。
- 后端全量：2511 passed / 6 skipped / 5 failed；失败集中在全量测试顺序下孤儿维护 lease/任务状态污染，相关孤儿服务选定顺序通过，需后续单独治理测试隔离。

### 部署注意

- 当前 Docker engine 不可用，未重新构建/导出镜像，也未进行远程部署。
- 部署前必须用当前源码重新构建后端并覆盖旧 `btdeck-backend.latest.tar`，再在目标机 `docker load` 后重建/重启容器；不能只加载现有旧 tar 或使用 `up --no-build` 复用旧镜像。
- 本轮未执行 Git 提交、推送或部署；根 `bash ./init.sh` 仍受 Windows WSL `E_ACCESSDENIED` 阻断。

---

## 2026-08-01 交接：通知时间修正与主动清理异步化

### 当前实现

- 新增 `backend/app/utils/datetime_utils.py`，将数据库 UTC 无时区时间序列化为带 `Z` 的 ISO-8601；通知中心不再把 UTC 误按本地时间显示为 8 小时前，隔离区任务状态时间也使用同一规则。
- 扩展 `orphan_purge_job`：`operation_type=purge/cleanup`、`scan_id`、`orphan_ids_json`、`total_size`，新增 Alembic `d8e9f0a1b2c3`，保留既有彻底删除任务兼容性。
- `POST /api/v1/orphan-files/cleanup` 现在只创建 pending 任务并提交现有 dispatcher；后台复用 `OrphanFileService.cleanup_orphans()` 的实时 manifest、身份、路径和 lease 安全校验。完成/部分完成/失败均写入 `orphan_cleanup:{task_id}` 通知，通知事件为 `orphan_cleanup_completed`。
- 新增 `GET /api/v1/orphan-files/cleanup-jobs/{task_id}`；前端 API 删除 300 秒超时，确认后立即关闭弹窗并提示任务 ID，用户从通知中心查看最终结果。

### 验证

- 后端相关回归 58 passed，数据库回滚 8 passed，目标 Flake8 通过。
- 前端相关 Jest 48 passed，`typecheck`、`lint`、生产 `build` 通过；build 仅报告仓库既有 Sass/Element UI 弃用与体积警告。
- 未执行 Git stage/commit/push/deploy。工作区中的 `.pnpm-store/`、tar、备份、诊断脚本等未跟踪文件均为用户既有产物，禁止纳入本轮提交。
