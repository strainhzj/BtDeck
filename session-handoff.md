# Session Handoff - BtDeck 全栈项目

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
