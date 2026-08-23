# Session Handoff - BtDeck 全栈项目

## 2026-08-23 交接（十）：Phase 2 真机验证通过 + Phase 4 M1 第一片（移动 UI 壳）

### 结论

伴侣模式真机验证通过（lan-cleartext APK，WebView 正常进入服务器前端，含视口/缩放兜底）。Phase 3 被 Phase 0 闸门阻塞，Phase 4 先行：M1 第一片交付移动布局壳（底部 Tab）+ 模式切换 + 移动登录/仪表盘/种子卡片列表/通知中心，全部复用现有 API 与 user store。

### 变更（未提交）

- frontend：src/utils/ui-mode.ts（偏好+视口+登录分流）、src/layout/mobile/index.vue（Tab 壳+桌面版出口）、src/views/mobile/{login,dashboard,torrents,notifications}.vue、router.ts /m/* 懒加载组、permission.ts 守卫模式分流+4 处登录跳转模式化（强制改密/瞬时失败语义未动）。
- 测试：tests/unit/ui-mode.spec.ts（11）+ mobile-shell.spec.ts（5）；守卫回归 31、前端全量 704 全绿；tsc/lint/build 通过；m-* chunk 实证。
- 惯例：class 组件用 vue-property-decorator 导入（Jest 下 vue-class-component 直用 Vue 为 undefined）。

### 生效与下一步

- 手机上生效需把新 frontend/dist 部署到服务器（或 npm run serve 开发机验证）；auto 模式窄视口自动进移动版，移动版头部可切桌面版。
- M1 余项：种子详情页/更多操作、下拉刷新、通知未读角标、桌面侧栏手动切移动版入口；M2 未动。
- android-wheels 推送仍等用户指令；Git 提交待用户指示。

## 2026-08-23 交接（十一）：孤儿 Schema 漂移重启自愈

### 结论

已针对新快照中的 `no such column: orphan_current_candidate.current_detail_id` 实施代码修复。根因是运行库的 `alembic_version` 可能已经是 `975dad435c03`，但物理表缺少历史迁移应创建的列；启动迁移因此 no-op，随后启动对账才报错。新增 `c1d2e3f4a5b6` 修复迁移后，所有用户重启后端都会在对账和调度器启动前自动补齐 Schema。

### 变更

- 新增 `backend/alembic/versions/c1d2e3f4a5b6_repair_orphan_current_detail_id.py`：幂等补列、按最近扫描/路径回填 `current_detail_id`、补齐必要索引；健康库 no-op；修复失败保持 fail-fast。
- 新增 `backend/tests/core/test_orphan_schema_repair_migration.py`：缺列漂移库与健康库回归。
- 更新迁移 head 断言、数据库迁移约束与 `docs/roadmap/` 记录；`feature_list.json` 登记证据。

### 验证

- 修复迁移回归：2 passed。
- 迁移链/回滚/生产形状回归：37 passed；启动迁移守卫、孤儿任务生命周期和查询状态回归：17 passed。
- flake8、mypy（新增迁移/测试）、Black `--diff`、`scripts/lint_btdeck.py`、JSON 解析和 `git diff --check` 通过。
- `alembic heads`：仅 `c1d2e3f4a5b6`。
- 用户提供的 `E:\Users\huangzj\Desktop\app.db` 仍只读分析，未写入。
- 根 `bash ./init.sh` 受当前 Windows/WSL `E_ACCESSDENIED` 环境阻断，非本次测试代码失败。

### 后续

代码与定向验证已完成；等待用户决定是否提交/推送。

## 2026-08-23 交接（十）：同步资源占用观测增强

### 结论

用户要求开始实施此前制定的观测方案。已完成一期只读观测增强：下一次 `ADMISSION_SKIP` 可定位 heavy_sync 的占用 task/run/phase/年龄/进程实例；长时间 Python 内部类任务会输出生命周期心跳和超时告警。未改变资源参数、调度行为、取消语义或数据库写入，也未修改 `E:\Users\huangzj\Desktop\app.db`。

### 变更

- `backend/app/tasks/resource_guard.py`：holder 快照、blocked_by 诊断、resource_lifecycle 事件、release 持有时长。
- `backend/app/tasks/cron_executor.py`：Cron run_id 关联、task_lifecycle start/heartbeat/timeout_warning/end；超时只告警。
- `backend/app/services/sync_coordinator.py`：活动同步 phase/elapsed/last-progress、sync_phase 事件和 holder 阶段刷新。
- `backend/app/services/sync_observability.py`、`backend/app/core/config.py`：结构化事件白名单、worker PID/实例标识、心跳间隔配置。
- `backend/tests/tasks/test_resource_guard.py`、`backend/tests/tasks/test_cron_executor_admission.py`：holder/生命周期回归。
- `docs/roadmap/`、`feature_list.json`、`progress.md`：同步路线图与证据。

### 验证

- 观测/同步核心套件 92 passed；Cron executor + health 回归 28 passed。
- mypy 目标文件无错误；flake8 通过；Black `--diff` 确认受影响 Python 文件无需格式化。

### 下一步

部署后检索 `event=resource_lifecycle`、`event=task_lifecycle`、`event=sync_phase`。重点确认 `blocked_by_task_code`、`blocked_by_sync_run_id`、`holder_phase` 和 `holder_age_ms`，再决定是否实施实际超时/恢复修复。Git 提交等待用户指示。

## 2026-08-23 交接（九）：android/ 首次编译验证通过（BUILD SUCCESSFUL）

### 结论

用户指令"开始首次编译验证"。本机无 Android 环境，搭便携工具链（IntelliJ JBR21 + Gradle 8.9 腾讯镜像 + cmdline-tools 安装 platform 35/build-tools 35.0.0，全在 C:\software\android-build-env\ 可整体删除）后完成首次编译：**编译 + 11 个 JVM 单测 + APK 打包全部通过**，双 NSC 明文变体经 aapt2 实证按设计切换。Phase 2 MVP 从"未编译脚手架"升级为"本机可复现构建"。

### 首次编译发现并修复（3 项）

1. AGP 8.5.2 → **8.7.3**（8.5 不支持 compileSdk 35；Gradle 8.9 为其最低要求）。
2. ServerListActivity：ListView `apply{}` 内未限定 `adapter` 被 Kotlin 解析到 ListView.getAdapter()（平台属性遮蔽）——改显式局部变量。
3. `onItemClickListener = { }` 属性赋值不做 SAM 推断——改 `AdapterView.OnItemClickListener{}` 构造器。

### 产物与验证

- `:app:testDebugUnitTest` 11 用例 0 失败；`:app:assembleDebug` BUILD SUCCESSFUL。
- app-debug.apk ~6.0MB，apksigner verify 通过；badging：com.btdeck.companion 0.1.0-mvp / targetSdk 35 / 权限仅 INTERNET+ACCESS_NETWORK_STATE。
- NSC：默认变体 manifest→@0x7f110000（严格版）；`-Pbtdeck.lanCleartext=true`→@0x7f110001（LAN 明文版）。
- android/README.md 构建节已改为已验证流程+工具链表；feature_list task .3 evidence、progress.md 第三批已同步。

### 下一步

1. 真机/模拟器人工冒烟（本机有 BlueStacks 未驱动）；仪表化测试与设备矩阵 Phase 5。
2. android-wheels 建远端推送仍等用户"整体打包完成"指令。
3. Git 提交待用户指示。

## 2026-08-23 交接（八）：Phase 1 收口 + Phase 2 伴侣模式 MVP 脚手架

### 结论

用户指令"继续下一步，整体打包完成后再推送 android-wheels"。本批完成：Monaco 审计（Phase 1 第 6 项，**Phase 1 七项全部收口**）；Phase 2 伴侣模式 MVP 的 android/ 工程完整脚手架 + health version 字段（按登记原则标 in-progress，未编译验证不标 done）。android-wheels 远端创建/推送/Actions 全部顺延至整体打包完成。

### 变更（BtDeck 主仓，未提交）

- **Monaco 审计**：docs/android/monaco-audit.md（实测数据：首屏 app 75KB+vendors 1.06MB，Monaco 隔离于异步 chunk 2.94MB+按需 worker，零首屏成本）；删除死组件 frontend/src/components/MonacoEditor.vue（静态 import 版，零消费方零测试引用）；webpack plugin 与组件层均判定不改。
- **health version**：health.py 的 /health/live、/health/ready（含 503 分支）data 增加 version（常量无 I/O）；test_health.py 10 用例锁定；tests/api 全量 1004 passed。
- **android/ 工程全新**（Kotlin+AGP 8.5.2+minSdk 24/target 35）：向导/服务器 profile 管理/HealthClient（live→ready+版本+TLS 可辨识）/同源 WebView（超时重试、外链交系统浏览器、切换 profile 清 cookie+storage 隔离令牌、版本副标题）/自签证书指纹信任流程（记录作用域，绝不无条件 proceed）/明文 HTTP 双层防线（NSC 默认全禁+应用层 LanHostPolicy 私有字面量+显式同意；LAN 明文需 -Pbtdeck.lanCleartext=true 构建变体）/LanHostPolicyTest JVM 单测。
- roadmap：api README health 行、根 README android 分支、元信息；feature_list.json（task .2 补 Monaco evidence、task .3 → in-progress）；progress.md 第二批已记。

### 验证

后端 mypy 247 文件零错、black/flake8、tests/api 1004 passed；前端 typecheck + tasks 相关 30 用例通过；根 ./init.sh 通过。

### 诚实边界

本机无 Android SDK/JDK17——android/ 未做 Gradle 编译验证（代码按正确性审查交付）；OkHttp 健康检查不消费 WebView 信任指纹（自签 https 显"证书错误"）为已知 MVP 边界，两项均已写入 android/README.md 与 feature_list evidence。

### 下一步

1. 【用户】具备 JDK17+Android SDK 的环境（或 CI）跑 android/ 首次 `gradlew :app:testDebugUnitTest` + `assembleDebug`。
2. 整体打包完成后：android-wheels 建 GitHub 远端并推送（Phase 0 闸门验证）。
3. Phase 3 服务端壳工程待 Phase 0 闸门；桌面伴侣模式可复用本批 profile/健康检查设计。
4. Git 提交待用户指示。

## 2026-08-23 交接（七）：安卓适配改造启动——Phase 0A/0B 脚手架 + Phase 1 主体落地

### 结论

按 PLANS/dual-mode-client.md 启动安卓适配：Phase 1 平台无关改造的第 1/3/4/5/7 项完成并全量验证，第 2 项完成文档契约与测试（LAN 重绑留 Phase 3）；Phase 0A 决策文档与 Phase 0B android-wheels 独立仓库脚手架就绪（本地 git 仓库，未推送）。Phase 0 闸门未验证（无 CI 实跑），按计划不得启动 Phase 3；Phase 2 伴侣模式可独立先行。

### 变更（BtDeck 主仓，未提交）

- **统一 TCP probe**：新增 `backend/app/utils/connectivity.py`；`downloader.py` get_delay_async/get_delay 与 `initialization.py` _update_downloader_status 三处 ping3 直调替换为"loopback 短路→桌面可选 ICMP（失败/PermissionError 全捕获回退）→TCP connect 计时"；安卓环境自动禁 ICMP。顺带修复延迟异常分支 `delay` 未绑定的 UnboundLocalError 潜伏 bug（原代码整个状态更新会 return False）。
- **依赖瘦身**：两审计服务 Excel 导出改 openpyxl 直写；pandas/numpy/sympy/common 从三份 requirements 移除（零 import 核实）；两份 PyInstaller spec excludes 加 'pandas'/'numpy'。
- **文档**：docs/android/ 四份——target-matrix.md（Phase 0A 目标矩阵+FGS 决策）、toolchain-matrix.md、config-and-paths.md（注入契约+HOST≠ALLOWED_HOSTS）、host-capability-matrix.md。
- **测试**：新增 5 个文件 54 例——test_connectivity.py(23)、test_delay_probe_callchains.py(8)、test_audit_excel_export.py(7)、test_writable_roots.py(6)、test_packaging_contract.py(10)。
- feature_list.json（dual-mode-client → in-progress，task .1/.2 带 evidence）、progress.md 已同步。

### android-wheels 独立仓库（本地 C:\software\claude_code_full_stack\android-wheels，commit ee65481）

构建 workflow（四 ABI cargo-ndk+maturin abi3 cp312+sdist sha256 固定）、check-wheel-tag.py（tag+ELF 校验）、make-simple-index.py（PEP 503+sha256）、import-matrix.yml（模拟器 API 34/35，full-graph 阶段 2 显式 fail 待接入真实资源）、最小 Chaquopy17 testapp、docs/gate.md 闸门模板、versions.env（hash/tag TBD 首次 CI 回填）。

### 验证

后端 mypy 247 文件零错误、black/flake8 通过、pytest 全量 **3927 passed + 7 skipped**；根 `./init.sh`（ci）通过（此前 WSL E_ACCESSDENIED 已不复现）。

### 下一步（按优先级）

1. 【用户】创建 android-wheels GitHub 远端并推送 → 首次 Actions 运行 → 回填 versions.env sha256/platform tag → import-matrix。
2. Monaco chunk/首屏收益实测（Phase 1 第 6 项，唯一未完成项）。
3. Phase 2 伴侣模式 MVP（独立可先行）。
4. Git 提交待用户指示（主仓 + android-wheels 两处）。

## 2026-08-23 交接（六）：双模式客户端计划评审修订与 v1.0.6 清单登记

### 结论

安卓服务端继续定位为轻量/临时服务端，伴侣模式可独立先行。计划已按依赖 wheel、Play/FGS、安全、存储、Doze、打包资源、能力降级和真实设备验收重新收敛；当前只有计划入册，未开始 Android 实现。

### 变更

- `PLANS/dual-mode-client.md`：评审修订版，补全风险闸门、平台无关改造、伴侣 WebView MVP、Chaquopy/FGS 壳、移动 UI、桌面对齐及发布 DoD。
- `feature_list.json`：新增 `v1.0.6-dual-mode-client`（7 个 pending tasks），保留原 `v1.0.6` 孤儿文件功能的 `done` 状态和 `PLANS/v1.0.6.md` 链接。
- `progress.md`：记录本次计划入册与验证结果。

### 下一步

1. 先完成 Phase 0A 的 Play/FGS/target API/备份安全预审。
2. 在独立 `btdeck/android-wheels` 仓库完成 pydantic-core 四 ABI 构建，并从最小工程推进到 BtDeck 完整导入图。
3. wheel 门禁通过前可独立实现伴侣模式；服务端模式不得跳过门禁进入 APK 工程。

### 验证与工作区

- `feature_list.json` JSON 解析通过；`git diff --check` 通过。
- 根 `./init.sh --ci` 仍受本机 Windows/WSL `E_ACCESSDENIED` 影响，未作为本次计划变更的有效门禁。
- 未执行 Git stage/commit；已有 `.release-build-v1.0.5/` 未跟踪目录保持不动。

## 2026-08-22 交接（五）：v1.0.5 发布前修正 GitHub 仓库地址

### 结论

已从已合并的 `origin/master` 建立 `codex/release-v1.0.5-repo-url` 发布修复分支。运行时更新检查和所有版本 Release 链接已统一使用正式仓库 `strainhzj/BtDeck`。

### 变更

- `backend/app/services/notification_service.py`：默认 GitHub 仓库改为 `strainhzj/BtDeck`。
- `backend/app/tasks/cron_executor.py`：定时版本检查的显式仓库改为 `strainhzj/BtDeck`。
- `backend/app/version.py`：v1.0.3/v1.0.4/v1.0.5 历史 Release URL 改为正式地址。
- `backend/scripts/add_welcome_and_update_notifications.py`、`README.md`：同步正式 Release 地址。
- `docs/roadmap/`：已核对，只有同一行内的配置值变化，无模块、方法或行号漂移，无需改动。

### 验证

- 后端定向任务测试：42 passed。
- 目标 Python 文件编译、`git diff --check` 和旧地址全仓搜索均通过。

### 后续

1. 将该修复分支合并到 `master`。
2. 在合并后的提交上创建并推送 `v1.0.5` tag，再创建 GitHub Release。
3. 确认 Docker 镜像 digest 与该发布提交对应。
4. 已部署 v1.0.4 的旧程序无法被 v1.0.5 反向修复；只有升级到包含本修复的版本后，更新检查才会访问正确仓库。

## 2026-08-21 交接（四）：按 v1.0.5 更新日志同步根 README.md

### 结论

v1.0.5 已于 2026-08-21 正式发布（`backend/app/version.py` CURRENT_VERSION=1.0.5），根 README.md 原先仍停留在发布前口径（核心特性缺新功能、版本历史标「本次发布」），本次已按 version.py 中的 v1.0.5 更新日志完成同步。

### 变更

- 根 `README.md`：
  - 「核心特性」新增三条：高级搜索与查询模板、孤儿文件管理（置信度/忽视名单/隔离区）、Tracker 异常识别。
  - 「版本历史」表加「发布日期」列；v1.0.5 状态改「已发布」、主题与 version.py summary 对齐。
  - 新增「v1.0.5 更新亮点」小节（七类精简摘录 + Release 链接 + 数据库自动迁移提示）。
- `progress.md` 已同步记录（2026-08-21 第五批）。

### 验证

- 纯 Markdown 文档变更，无代码路径影响；未提交（按仓库规范，Git 提交仅在用户要求时执行）。

### 工作区注意事项

- 工作区仍有后端 mypy 清零批次的未提交改动（见第四批记录），与本次 README 变更相互独立，提交拆分待用户决定。

## 2026-08-21 交接（三）：任务日志/孤儿文件统计卡片折叠与持久化

### 结论

已按用户确认完成两个页签统计卡片的收缩/展开：复用全局 `CollapsiblePanel`，并为任务日志、孤儿文件分别绑定独立的 localStorage 键，默认展开，刷新后恢复用户上次状态。

### 变更

- `frontend/src/views/tasks/index.vue`：日志统计摘要接入 `btdeck_task_log_stats_collapsed`。
- `frontend/src/views/orphan-files/index.vue`：扫描统计摘要接入 `btdeck_orphan_file_stats_collapsed`。
- `frontend/tests/unit/management-pages-ui.spec.ts`：增加两个页签的面板、统计内容和键隔离契约。
- `feature_list.json`、`progress.md`、`docs/roadmap/` 已同步。

### 验证

- `management-pages-ui.spec.ts`：14 passed。
- 变更 Vue/测试文件 ESLint 通过，前端 `npm run typecheck`、`npm run lint`、`npm run build` 通过；生产构建有 58 条既有 Sass/资源体积类 warning，无编译错误。
- 根目录经 Git Bash 执行 `./init.sh --ci` 通过；本次修改已提交为 `9647556`（`feat(frontend): persist collapsible management stats`）。

### 工作区注意事项

- 工作区原有大量 backend 未提交修改及临时文件，本次未触碰；这些修改仍保持未提交状态。

## 2026-08-21 交接（二）：列宽拖拽两缺陷修复——名称列手柄 + 传统模式手柄整体失效

### 结论

上一批"双模式可调列宽"功能用户实测反馈两问题，均已修复（未提交）：①名称列无拖曳手柄——按用户决策改为 **qBittorrent 风格严格列宽**，名称列登记默认宽（列表 400px/传统 200px）并渲染手柄；②传统模式所有列手柄不出现——根因是手柄样式只存在于 `torrent-theme.scss`，而它仅被 index.vue **scoped** 引入，TraditionalView 的 `traditional-view-theme.scss` 无任何手柄规则（span 零样式不可见）。

### 关键变更（7 文件：1 新增 + 6 修改）

- 新增 `frontend/src/styles/torrent-column-resize.scss`：手柄全套样式 + `th:not(.action-column){position:relative}` 定位基准 + `body.column-resizing` 拖拽态 + 传统浅色表头 hover 反馈条改 `var(--color-primary)`（白色条在浅色表头不可见）；在 `styles/index.scss` **全局引入**。防回归要点已写进文件头注释：两视图样式块均 scoped，手柄样式必须全局引入。
- `torrent-theme.scss`：移除已抽走的手柄规则（含 `body.column-resizing`——它在 scoped 引入下编译成 `body[data-v-x]` 从未生效过，属顺带修复的隐藏 bug）。
- 两视图：名称 th 加 `columnWidthStyle('name')` + 手柄；`defaultColumnWidths` 登记 name；`tableMinWidth` 计入 name 去掉 `+200`；表格内联 `width=minWidth=列宽总和` 双绑定（覆盖类里 `width:100%`，该规则仅 DuplicateTorrentsDialog 等未定宽场景继续用）。

### 行为变化（用户已确认）

名称列不再随窗口变宽自动填满；所有列严格按设定宽渲染、拖拽全程 1:1；视口比列宽总和宽时表格右侧留白。旧 localStorage 无 name 键自动落回默认宽。

### 验证

变更文件 ESLint 0 错误、全量 npm run lint 通过、column-resize-mixin.spec 8 用例 + 全量 59 suites/906 passed（含新增回归 7 用例）、生产 build 通过。feature_list.json（torrent-column-width-fixes-2026-08-21，4 tasks）、progress.md 已同步；已按用户指示提交。

### 回归保护（同会话第三批）

- 新增 `tests/unit/column-resize-regression.spec.ts` 5 组静态契约：**手柄样式唯一来源 torrent-column-resize.scss 且必须经 index.scss 全局引入**、两份 scoped 主题不得再携带 `.column-resizer`/`body.column-resizing`（传统模式手柄整体失效根因的防回归锚点）、传统表头反馈条主题色、名称列登记宽度+手柄绑定、tableMinWidth 计入 name 无 +200、严格定宽双绑定、名称省略跟随列宽（无 300px 硬编码）。
- 两视图组件 spec 各 +1 运行时用例（表级 width=minWidth=tableMinWidth、名称 th 内联宽、手柄拖拽会话→落盘视图独立 key）。全量 59 suites/906 passed。

### 追加（同会话）：名称过长省略号定性 + 跟随列宽

用户反馈"名称过长显示...，要求前端处理而非后端截断"。排查定性：**后端从未截断**（VO 原样返回/同步全量写库/前端 API 直传），`...` 是前端 CSS；真缺陷是列表模式 `.torrent-name-text` 硬编码 `max-width: 300px`——名称列可拖宽后仍在 300px 截断。已改为省略号跟随列边界（flex:1 + min-width:0，悬停 title 全名）；传统模式 `.torrent-name-cell` 补缺失的省略样式（td 兜底只裁剪不出 `...`）。traditional-view-component.spec 30 passed、build 通过。

### 遗留

- 已提交（未推送/未部署）；部署需重新构建前端产物。建议浏览器实测：传统模式手柄 hover 反馈条可见性（主题色 vs 浅色表头）、宽屏留白观感、名称列拖拽与省略号跟随列宽。
- roadmap 第三层文档涉及两视图行号的未同步（本次改动两视图各 +15 行左右，未新增/删除方法）。

## 2026-08-21 交接：合并 origin/dev 全量冲突解决 + 种子列表双模式可调列宽

### 结论

两件事：①仓库搁置的 `git pull`（origin/dev → dev）合并冲突全部解决并提交（合并提交 **afc3c34**，181 文件 / 981 处冲突标记，后端全量 3874 passed、前端 891 passed 验证）；②新功能"种子列表双模式可调列宽 + localStorage 持久化"实现完成并验证。

### 合并决策（后续维护需知）

- 辅种异常排查取**远端表格内嵌版**；本地弹窗版 6 文件已删（组件/spec/端点/服务/测试/API 文档），api.py 注册已摘除。
- Tracker 详情面板全链取远端共享 `TrackerDetailCard`（带 layout/activeTab/reannounce），本地 index.vue 内联卡片与 TraditionalView detail-panel-trad 悬浮面板已下线。
- 合并顺手治本 4 处：975dad435c03 迁移 inspect 幂等守卫（远端自认的存量 duplicate column）、verify_password 截断哈希结构校验（bcrypt Rust panic）、resolve_external_path POSIX isabs 兼容（Windows 桌面版受影响）、enhanced_python_executor.py 死代码删除（BTD301）。
- `.agents/`、`.codex/`、`.code-graph/`、`PLANS/orphan-files-state-consistency-fix/` 等本地未跟踪目录**未入库**（.gitignore 未收录，是否纳入由维护者决定）。

### 列宽功能（本次新功能，未提交）

- 共享 mixin `src/views/torrents/mixins/columnResize.ts`：拖拽夹取 [40,600]px、mouseup 写一次 localStorage（`btdeck_torrents_column_widths` / `btdeck_traditional_column_widths`）、双击恢复单列、菜单"重置列宽"、监听/拖拽态类成对清理。**注意：vue-class-component 下类字段箭头函数 this 指向构造期临时实例，监听器必须用方法 + 存储绑定引用**（mixin 注释已写明）。
- 两视图 th 全部改 `columnWidthStyle()` 绑定 + 手柄；表级 min-width 改 computed（可见列宽和 + 名称列 200px）；`.torrent-table` 全局 `table-layout: fixed`（传统表远端已自带，实际改变的是列表模式）+ td 溢出省略；手柄样式在 torrent-theme.scss。
- 验证：column-resize-mixin.spec 8 用例 + 全量 58 suites / 899 passed、tsc、lint、build 全过。feature_list.json（torrent-column-width-resize-2026-08-21）、progress.md 已同步。

### 遗留与建议

- `table-layout: fixed` 对列表模式是布局行为变化：内容超列宽改省略号截断（此前撑宽横向滚动）。建议浏览器实测两视图窄屏/宽屏视觉（尤其进度条、Tracker异常标签、操作列按钮）。
- 列宽存储未按登录用户隔离（与项目既有 visibility key 一致的全局 key）。
- 本次功能改动未提交；工作区另有 `.agents/` 等未跟踪目录保持原样。

## 2026-08-20 交接：展示对齐判定——Tracker 异常可见化与 Announce 状态覆写

### 结论

`status=error` 筛选（口径 `status='error' OR has_tracker_error=True`）此前会查出 UI 上毫无错误迹象的种子。定性：Transmission 对 PT 站「HTTP 200 + bencode failure reason」上报成功布尔（状态码 2=工作中），判定任务按消息文本判错置 has_tracker_error=1——判定对、展示错信布尔。本次让展示与判定同口径，经两轮独立子代理审查后实施。

### 实施结果（未提交，23 文件）

- 后端：新增 `core/tracker_keyword_map.py` 共享关键词池加载器（判定任务 `_load_keywords` 委托，方法名是治理测试锚点）；`tracker_status_policy.py` 新增 `tracker_message_failed`/`tracker_display_failed`（中性码 qb==1/tr∈{0,1} 残留消息不覆写）；TorrentInfoVO 透传 `has_tracker_error`；getList/duplicates 的 announce/scrape 文本在消息精确命中失败池时覆写"工作失败"；duplicates error 筛选口径补 OR has_tracker_error（与 getList 一致）。
- 前端：`torrentBatch.ts` 新增 hasTrackerError/showTrackerErrorTag/getTorrentErrorReason 共享 helper（两视图旧重复实现改委托）；两视图状态列叠加红色"Tracker异常"小标签 + tooltip 回退链 + 图标 title；TraditionalView col-status 90→145px、表 min-width 1435px；TrackerOperationDialog 修复 `'True'` 字面量判断恒显异常的既有 bug。

### 验证

- 后端全量 pytest 3884 passed / 7 skipped / 1 failed（失败项经 stash 干净树复现为存量迁移问题，与本次无关）；新增 test_tracker_error_display_alignment 24 用例（含判定任务委托链路、判定↔展示一致性契约矩阵、advanced_search 同源集成）+ policy 扩充；5 个 fixture 补 TrackerKeywordConfig 表；black/flake8 过，mypy 净增 +2（与同构造 60 个既有字段同类的旧模型误报）。
- 前端 57 suites / 891 passed（含两视图组件级标签渲染与 TrackerOperationDialog 契约 spec）；lint/build/init.sh 通过。
- feature_list.json（tracker-error-display-alignment-2026-08-20）、progress.md、docs/roadmap（core/api/tasks/frontend-views 四分支 + 根 README 元信息）已同步。

### 遗留与边界

- has_tracker_error 由判定任务约 30 分钟重算，关键词池编辑后覆写即时生效而 flag 滞后——既有语义，不放大矛盾。
- 展示覆写不落库（同步位点 5 处未动，保留 Transmission 原始归一码）。
- 未执行 Git 提交；未部署（需重新打包后端镜像/安装包才在线上生效）。

## 2026-08-20 交接：Linux 安装包全链路验证（容器模拟）与三项仓库修复

### 结论

Docker（node:18.20.1-slim/Bookworm + python3.11 + fpm）完整跑通 build-linux.sh：PyInstaller 二进制 + fpm deb/rpm 全部产出并验证；deb 在全新容器 dpkg -i 成功、以 btdeck 用户 + systemd 等价环境启动健康（health/SPA 200）。产物已回传仓库 dist/（btdeck-linux、BtDeck-v1.0.9-linux-amd64.deb/.rpm）。

### 本会话修复（未提交）

- deploy/verify-package.py + analyze-package-size.py：find_archive_viewer 改 sys.prefix 优先（Linux venv 软链导致 resolve 跳 /usr/bin）。
- deploy/btdeck.service + build-linux.sh postinst：ALLOWED_HOSTS 改 JSON 数组格式（pydantic-settings 对 List[str] 强制 JSON 解析，逗号格式安装即崩——A/B 实证）。
- deploy/build-linux.sh：fpm 加 --force（重复构建不再 fatal）。
- 本地工作区：build-linux.sh/start.sh/btdeck.service 强制重检出为 LF（陈旧 CRLF 检出隐患，索引本 LF）。

### 注意

二进制 glibc 2.36（Debian12+）；spec 的 transmissionrpc 旧条目告警可删；build-linux.sh 缺 binutils/libpython3.11/fpm 预检；List[str] env 强制 JSON 与 .env.example 逗号指引的深层矛盾待评估。验证容器已清理。

## 2026-08-20 交接：种子信息同步辅种数量

### 用户确认语义

- 匹配键仅是 `name + size`，跨下载器、跨同步任务全局统计；`.torrent` 文件名和下载路径差异不影响同组判断。
- 不在列表查询时实时计算，由种子信息同步任务全量计算；无有效辅种数据时显示 1。
- 外部库 `E:\Users\huangzj\Desktop\app.db` 只读实证：该名称 45 条记录中 31 条有效，当前有效缓存全部为 1；`torrent_file` 45 个均不同，故不能参与匹配，按 `name + size` 应刷新为 31。

### 实施结果

- 新增 `torrent_info.auxiliary_seed_count` 与可回滚 Alembic `975dad435c03`。
- 同步任务对有效种子全量校正；等级 1/2/3 删除、种子转移成功删除源行、回收站还原做分组增量维护，异常状态由下次同步自愈。
- 后端 VO/API 与普通/传统种子列表均接入“辅种数量”列，前端兼容 camelCase 与 snake_case。

### 验证

- 补充回归后：辅种服务+种子转移 24 passed；删除等级1/2/3+回收站还原 42 passed；同步任务+列表 API 52 passed（后端定向合计 118 passed）；迁移/回滚/生产库形状 35 passed；前端普通/传统列表渲染回归加入后，选定单元测试 102 passed。
- 新增回归保护覆盖无效键、不同 `.torrent` 文件同 `name + size`、等级3移动失败回滚、回收站还原、同步任务失败分支/校正异常和列表 camelCase 字段。
- backend flake8、frontend typecheck/lint、生产 build、`git diff --check` 通过；mypy 仍受转移服务既有 SQLAlchemy/异步 Session 类型基线错误影响，未新增辅种相关错误。
- 本轮将完成 Git 提交并推送；未部署。
- 未执行 Git 提交、推送或部署；工作区原有的打包脚本、路由及相关文档修改均保留。

## 2026-08-19 交接（三）：桌面版 "Redirected ... via a navigation guard" 杂音根因与修复

### 根因

vue-router 3.1+ 将守卫改道以 rejected promise 结算；强制改密守卫（must_change_password=1，DB 实证）把登录后的 /dashboard 改道到 /settings/index，login/index.vue:214-220 的统一 try/catch 把该 NavigationFailure 当登录错误 $message.error 弹出。导航本身正常，纯杂音。后端零 30x、前端无该渲染字符串（全量扫描排除）；低概率假设（端口冲突/代理/外部页面）现场排除。

### 修复与验证

frontend/src/router.ts 扩展既有实例级补丁：push/replace 以 isNavigationFailure 全类型判定（原仅 NavigationDuplicated 且无 replace），导航失败 resolve、真实异常上抛。新增 tests/unit/router-navigation-failure.spec.ts 3 用例（注意：模拟守卫需白名单放行目标路由，否则自指循环路由停原地）；4 套件 34 用例全绿 + typecheck + lint；exe 已重打包（20:09）。**用户正在运行的旧实例需重启 exe 生效**。

### 关联

强制改密流程本身正常（设计行为）：完成"修改密码"即解锁全站；UX 改进建议（落点默认"修改密码"标签/常驻横幅）仍待用户拍板。

## 2026-08-19 交接（二）：Windows 桌面发行版打包实测——契约数据缺失修复 + 前后端入包/独立窗口双验证

### 结论

- 完整跑通 deploy/build-windows.bat（Inno Setup 未装，setup.exe 步骤按设计跳过；产物 dist/btdeck.exe 64.9MB；安装包格式为 Inno setup.exe 非 MSI）。
- 实测发现并修复桌面打包真实缺陷：app/contracts/advanced_search.py import 期读取 advanced_search_contract.json，spec 未打包 → frozen 启动即崩；两 spec datas 已补（contracts JSON + production_complete_schema.sql），重建归档确认。
- **前后端均在包内**：归档 287 个 frontend_dist 条目；运行时 /health/live 200、/ 返回 SPA 首页、chunk-vendors.js/app.css 200，6 秒就绪（前端由 _MEIPASS/frontend_dist 服务）。
- **前端为独立窗口**：pywebview 原生窗口 1280×820；Get-Process 实测 MainWindowTitle="BtDeck"（句柄非零）；BTDECK_DESKTOP_WINDOW=0/false 可切无窗纯服务模式（NSSM 服务场景靠 SESSIONNAME=services 自动判别）。
- 安全对齐实证：打包 venv 解析 starlette 0.41.3 + fastapi 0.115.14（CVE 修复版）。

### 未提交变更（待用户指示）

deploy/btdeck-windows.spec、deploy/btdeck.spec（datas 补运行时数据文件）+ 本批文档。

### 遗留

安装 Inno Setup 6 后可产出 setup.exe；前端 sourcemap 入包致体积偏大（ts.worker.js.map 未压缩 13MB），可关 productionSourceMap 或剔除 .map；测试产生的 dist/ 残留已清理。


## 2026-08-19 交接：打包脚本全链路审计与修复

### 背景与结论

用户要求检查"各系统的打包脚本"并验证，随后指定子代理验证、授权动手修复。三并行子代理独立审计四套打包体系（Docker×2 入口、桌面 PyInstaller/Inno、fpm），发现 8 项异常，本会话全部修复（未提交）。通过项：语法/引用/compose/健康链路/tar 完整性/版本一致性/W12 落实/hiddenimports 对齐。

### 修复明细

- `build-and-export-images.bat`：①SSH 密码+hostkey 移入 gitignore 的 `.btdeck-deploy-credentials.bat`（本地已创建含原值，双击部署流程不变；模板 `.btdeck-deploy-credentials.bat.example`）②镜像重试链官方源兜底（原 2→3 即止；现 2→3→1，START=1 时 1→2→3，双标志防回环——首版有回环 bug，经"从真实 bat 抽取 :build_image/:apply_profile 的仿真"捕获后修正）③`--unraid host --compose f` 不再把 --compose 误吞为 REMOTE_DIR。
- `deploy/verify-package.py` + `deploy/analyze-package-size.py`：新增 `find_archive_viewer()`，优先 `sys.executable` 同目录——修复打包 venv 未激活时 `[FAIL] pyi-archive_viewer not found` 中断（Windows 阻断 Inno 步骤/Linux 阻断 fpm 步骤）；临时 venv 复现 not found→found。
- `deploy/btdeck.iss`：nssm remove 移到 usUninstall（原 usPostUninstall 时 nssm.exe 已删，Exec 必失败留孤儿服务）。
- `deploy/requirements-{windows,linux}-package.txt`：fastapi~=0.115.6 + starlette~=0.41.3（修 CVE-2024-47874 内嵌；backend/requirements.txt:18-22 注明 fastapi 0.115.6+ 才放行 starlette 0.41.x）+ bcrypt~=5.0.0。
- `backend/.env.example`：SECRET_KEY 真随机样值→REPLACE_WITH_RANDOM_SECRET。
- 删除：`.docker_temp_482561487`（566MB）、`deploy/dist`、`deploy/build`（后两者为 6/21 W12 前构建，TOC 实证内嵌旧 config.yaml 密钥+app.db）。

### 验证

- 高保真仿真三链路 + 参数组合；verify-package 复现场景前后对照；AST×2；bat --help 实跑；git grep 跟踪文件零凭据；前端 npm run build 与 ./init.sh 本会话早前已实跑通过。

### 2026-08-19 补记：git 历史清洗（已执行）

- git-filter-repo 双分支（master+dev）改写：移除 bat 密码/hostkey（replace-text）与 backend/config/config.yaml 全路径（7/8 历史版本含真实 secret_key/login_status_secret，自根提交起）；435→434（空提交 e8e7784 剪除），全部哈希改变；改写前备份 bundle 于 ../BtDeck-pre-history-clean-20260819.bundle。
- 验证：--all 范围内密码/hostkey/config.yaml 零命中，旧对象（c603b0d/8fe877d）已 gc 不可达；force push master+dev。
- ⚠️ 未解除事项：root 密码与历史 secret_key 仍需轮换（历史清洗≠未泄露）；既有 clone 需重拉；GitHub 服务端旧 SHA 在 GC 前可访问，可联系 support 加速；备份 bundle 含泄露内容，确认后删除。

### 下一步（需用户决策/人工）

1. 轮换 192.168.5.51 root 密码（GitHub origin/dev 历史已暴露）；2. git filter-repo 清洗后 force push（与既有密钥清洗遗留合并）；3. 开 Docker Desktop 后跑一次 `build-and-export-images.bat --quick`（注意默认 DEPLOY_ENABLED=1 会直连生产）；4. 桌面打包跑一次 `deploy/build-windows.bat` 实测 Inno 全链；5. 版本号硬编码两处建议统一动态解析；6. Git 提交待用户指示（8 文件修改 + 1 新增模板）。

## 2026-08-18 交接：跨标签令牌续期竞态修复（三态续期 + ExpireSession + 后端原子轮换）

### 问题与定性

- 用户报告：令牌过期后无自动续期，操作中突然请求失败。两轮排查 + 双子代理复核确认：单标签 401→续期→重放链路完整（8-17 修复后），根因是**多标签共享 refresh cookie + 后端使用即轮换 + 前端任何刷新失败都清空共享 cookie**——竞态败者/网络抖动一次即杀死全浏览器续期能力，此后每 60 分钟（access 周期）强制登出。次要根因：改密后端撤销全部 refresh token 但前端不清 cookie（"access 活 refresh 死"窗口）。
- 计划独立审查采纳 2 必改：rejected 路径不得清共享 refresh cookie（"败者先读、胜者后写"残余竞态）；守卫 next(false) 分支必须手动 NProgress.done()（afterEach 不触发，进度条悬挂）。

### 变更

- `frontend/src/utils/token-refresh.ts`：三态 RefreshOutcome（renewed/rejected/transient）+ isDefiniteFailure 依赖 + definite 失败后重读 cookie 追他标签轮换新值有限重试（上限 3）。
- `frontend/src/utils/request.ts`：handleUnauthorized 三分支（transient 不清 token 不跳转待自愈）；redirectToLogin 改用 ExpireSession。
- `frontend/src/store/modules/user.ts`：新增 ExpireSession（被动登出保留 refresh cookie）；GetUserInfo 网络错误 ApiError 原样上抛。
- `frontend/src/permission.ts`：守卫三态分流 + abortNavigation（next(false)+提示+手动 NProgress.done）+ GetUserInfo 网络错误不杀会话。
- `frontend/src/views/settings/index.vue`：改密成功 ResetToken + push('/login')（forceChange query 清理段删除）。
- `backend/app/api/endpoints/login.py`：/auth/refresh 条件 UPDATE 原子轮换（rowcount=0 即 401）+ record 空值防御 + request.client ASGI None 防护。
- 测试 4 个前端 spec 重写/扩展 + 后端 +1 用例；feature_list.json（token-refresh-race-fix-2026-08-18）、progress.md、roadmap（utils-types/entry/store/views/backend-api/根 README 元信息）同步。

### 验证

- 前端全量 55 套件 **866** 用例通过（含回归加固 +5：store-user ExpireSession/GetUserInfo 上抛契约 4、request-auth transient 自愈闭环 1；permission-guard/session 补断言）；npm run lint（含 contract:check/lint-vuex-action）+ typecheck 通过。
- 后端 test_auth_refresh **8** 用例（+1 旧 token 复用投影：再刷 401 且不签发新记录）+ test_login_throttle_and_change_password 12 用例全绿；black/flake8 通过；mypy stash 基线对比 13→13（新增 0）。

### 后续与边界

- 未执行 Git 提交（用户未要求）。**部署提醒：前后端均有变更，需重新构建前端产物（frontend/dist 当前为 08-17 构建，不含本批修复）并重启后端**；桌面打包（deploy/*.spec）捆绑 frontend/dist，发布前需重新 build。
- 残余竞态语义（有意保留）：竞态败者误判 rejected 时仅本标签被踢登录页，他标签令牌不受影响（refresh cookie 不清）；死 token 残留 cookie 无害，重登录时 Login 覆盖。
- 改密后行为变化：成功后强制跳登录页用新密码重登（原为留在设置页）——用户已确认此口径。
- 测试技巧：api 函数 mock 边界在拦截器之后，后端明确拒绝应以 ApiError(401) 拒绝形态提供（resolve 401 信封会走契约错误分支）；beforeEach 先 ResetToken 再 clearAllMocks；mockResolvedValueOnce 队列需显式 mockReset。

## 2026-08-18 交接：辅种异常排查语义修订（v1.0.6.40，状态/Tracker 改组内显示筛选）

### 问题与定性

- 生产查询 `same_content_only=true&name_like=老男孩&status=error` 返回 total=0。用生产副本库（E:\Users\huangzj\Desktop\app.db，schema 已在 head）+ 真实 `get_torrent_infos` 复现：老男孩 20 条同名同大小不同 hash 中仅 1 条 status=error，旧口径“普通筛选先参与候选判定”使组内仅剩 1 hash，`HAVING COUNT(DISTINCT hash)>=2` 不成立 → 整组丢弃。
- 用户确认语义修订口径：status + tracker_like/tracker_domain 均为行级属性，改为**组内显示筛选**；关键字/下载器/路径/大小/时间/标签/分类/活动种子仍参与成组判定。

### 变更

- `backend/app/api/endpoints/torrent_helpers.py`：三类筛选收进 `_apply_row_display_filters` 闭包（L171，逻辑逐字保留）；普通列表原位应用行为不变，`same_content_only` 延后到分组 join 后应用（L307-310 附近）。
- `backend/tests/api/test_same_content_inspection_api.py`：+2 用例（status 显示级过滤复刻生产场景；tracker_like/tracker_domain 显示级）。既有 9 用例零修改仍通过。
- `backend/docs/api/same-content-inspection.md`：两类筛选口径重写。
- feature_list.json 新增 v1.0.6.40；progress.md/roadmap（根 README 功能域行+元信息、backend/api/README.md L43）同步。

### 验证

- 专用套件 11 passed + 普通列表回归 35 passed；flake8/black/py_compile 通过；mypy 58 条 stash 基线对比零新增；根 init.sh 通过；git diff --check 干净。
- 生产副本库只读实测：目标查询 0 → 1（hash cfcb51db 错误行）；同内容+老男孩仍 20；普通+老男孩+error 仍 1。

### 后续与边界

- 未执行 Git 提交（用户未要求）。**部署提醒：生产实例需更新后端代码并重启后生效**；前端无需变更。
- 附带发现未处理：仓库内 `backend/config/app.db`（开发库）落后 10 迁移缺 error_reason，当前代码直连会全量 500，需 `alembic upgrade head`；`data/backend/config/app.db`（compose 挂载部署库）全空且落后 20+ 迁移。
- `has_tracker_error` 未暴露到 VO/前端，“做种中但 tracker 全挂”的种子在 UI 不可见（潜在 UX 增强项）。

# Session Handoff - BtDeck 全栈项目

## 2026-08-16 交接：进度精度/转移落库/审计 IP 三项修复

### 当前结果

- **进度精度**：`torrents_async.py::_normalize_progress_value` 统一 `round(2)`（全部 8 处同步写路径汇聚点）。存量脏值（99.556946664657%）无需迁移，下次同步自愈（0.5 阈值保留舍入值 + has_torrent_info_changes 精确比较 + 全量同步无条件写回）。
- **转移落库**：`seed_transfer_service.py` 验证成功后 `_upsert_target_torrent_row` 立即 upsert 目标下载器行（字段对齐 info-only 同步 insert dict；downloader_name=当前昵称保证后续 bulk_update 三列主键命中；(hash, downloader_id) WHERE dr=0 唯一索引保证与后续同步同一条）；显式 commit、IntegrityError 竞态转 update、异常吞掉仅 warning（目标已添加成功是既成事实，报错会诱导重试）。delete_source 成功时 `_mark_source_row_transferred` 源行 dr=1（同步删除语义，不进回收站）。另加 source==target 服务层兜底防御。
- **审计 IP**：转移两端点加 request，`_log_transfer_audit` 传 ip_address/user_agent；孤儿 5 项手动操作（cleanup/purge/restore/ignore/hardlink-copy-delete）全部补齐——同步端点直接 `extract_audit_info_from_request` 透传，后台任务链经 `orphan_purge_job.ip_address` 新列（迁移 `ab68fe061d5b`，串接 ff42d3402df5）在提交时持久化、execute_job 读 job 会话内取出传入服务层；5 个服务函数加 ip_address 形参 + 4 处租约递归 + 5 处审计调用点；4 个提交入口全加参。
- 问题 4（IP 全 192.168.5.60）经拓扑核实为正常：docker nginx 反代 + XFF 链路，.60 为访问端电脑；宿主机实为 .51。

### 验证

- 定向：progress_rounding 9 + seed_transfer fixes 10 + batch fixes 5 + orphan job 15 + orphan api 70 + w2_3d 19 + migration 链 25 + rollback 10 + production_shape + governance（tests/core 全目录 458）全部通过。
- 全量 pytest：见下（第二批全量结果见 progress.md；第一批全量 5 失败均为本次改动牵连的版本常量/mock 队列，已全部修复）。
- black/flake8 干净；mypy 新增错误种类 0（stash 基线对比）；EXPECTED_HEAD/REV_HEAD 三处测试常量与 `docs/constraints/database-migration.md` HEAD 标注同步为 ab68fe061d5b（原文档标 c8d9e0f1a2b3 已过期 5 个版本）。

### 后续与边界

- 未执行 Git 提交（用户未要求）；部署后首日观察：进度脏值应在 10 分钟同步周期后消失；转移完成后列表立即可见目标行。
- 遗留待用户决定：`extract_audit_info_from_request` 取 XFF 首值可被客户端伪造（nginx 追加真实 IP 在末尾），如需收紧改为取尾值/X-Real-IP/直接 client.host。
- 预插行 status/size/ratio/torrent_file 与目标下载器真实状态短暂不一致（torrent_file 跨类型转移指向源路径），下次同步覆盖，属预期行为。
- 孤儿后台任务（auto_cleanup/scan 审计、cleanup_executor L3/L4）仍无 IP（无 request 上下文，审查确认边界合理）；手动扫描 `submit_scan` 提交时捕获 IP 属可选增强未做。

# Session Handoff - BtDeck 全栈项目

## 2026-08-16 交接：副本位置弹窗行级删除硬链接副本

### 当前结果

- 副本位置弹窗每个副本行新增「删除」danger 文字按钮：`$confirm(type=error)` 二次确认（文案说明仅移除该路径链接、数据仍由源文件保留、种子目录内副本会被拒绝）→ `POST /orphan-files/hardlink-copies/delete`（`{orphan_id, copy_paths:[path]}`）→ 成功后就地刷新列表行 `hardlink_copy_count`（含文件夹 children；`located` 筛选开启时改走 `refreshPageData` 整页刷新）+ 重查弹窗位置。
- 后端 `delete_hardlink_copies`（`orphan_file_service.py:871`）逐路径 fail-closed：租约互斥 → 候选 `status=candidate`/`operation_state=stable` 门禁 → 源 stat 身份 + 预扫描结果行 → 共享 inode 拒绝集（源路径 + 同身份全部候选 canonical_path）→ 种子目录白名单（`collect_torrent_directory_whitelist` 全量，加载失败整体拒绝）→ copies 原始字符串成员判定 + 隔离区/回收站标记 + 符号链接拒绝 → tombstone 三段式（rename→身份复核→remove，复核失败回滚）。成功后 setattr payload 同步结果行，主事务 commit 后写审计（新枚举 `orphan_hardlink_copy_delete`）。
- 响应形态：状态类拒绝一律 HTTP 200 + `failed_list[{copy_path, reason}]`；租约 busy 返回 `rejected=true`；Pydantic 参数失败 422。无 schema 变更。
- 经 3 个只读子代理独立审查修订的关键点：审计事务冲突（改 restore 模式，commit 后写）；共享 inode 漏洞（同身份候选拒绝集）；tombstone 删除保护；Vue2 `$set/$delete`；弹窗重开竞态（删除回调 seq 快照 + `hardlinkLocationDialogVisible` 双重校验后才重查）；重查 `keepResult=true` 保留旧数据仅列表区局部遮罩。

### 验证

- 后端：detection 33 passed（TestHardlinkCopyDelete 13 用例，真实 os.link 临时硬链接）/ api 44 passed / enums 283 passed；`tests/services+tests/api` 1983 passed、`tests/core+tasks+enums` 1075 passed；black/flake8/ruff/lint_btdeck 通过；mypy 1563=基线（stash 对比零新增）。
- 前端：orphan-files.spec.ts 99 passed（新增 7 用例）；全量 44 suites/754 passed；typecheck + 三个改动文件 ESLint 零问题。
- 文档：roadmap 三层（根 README + services README + `orphan_file_service.md` 行号实测 3809 行 + api README）；feature_list.json 新增 `orphan-hardlink-copy-delete`（3 tasks）；progress.md 已更新；`./init.sh` ci 通过。

### 后续与边界

- 未执行 Git 提交/推送/部署；工作区原有未跟踪产物保持不动。
- 种子目录保护为 DB 目录级（save 根 + 种子子目录），非实时 manifest 文件级——交互请求内不构建实时清单（成本考虑）；在线下载器 expected 文件级保护不覆盖此场景，目录级可能过拒（位于种子目录内但非种子文件的副本无法通过此功能删除），属用户确认的 fail-closed 取向。
- 结果行与预扫描任务的写竞态：删除提交后若预扫描轮次已在遍历同身份，下一轮会自愈覆盖；`truncated`/`scan_note`/`scanned_at` 保留原值。
- 前端 `audit.vue` typeMap 未加新枚举文案（缺省回退显示原始值，与既有 6 个 orphan 枚举一致）。

## 2026-08-15 交接：已定位副本快捷筛选 + 预扫描范围收紧

### 当前结果

- 孤儿页"快捷操作"新增"筛选已定位副本"：一键切换 `hardlink_copies=located` 筛选并回第一页（再点取消；激活态显示勾选图标与取消文案，不落入前缀对话框流程）；筛选区同步新增"已定位副本"复选框（tooltip 注明按每日预扫描结果过滤）。列表/文件夹聚合/子项展开三条查询链共用同一筛选口径。
- 后端筛选实现：`_build_orphan_conditions(hardlink_copies="located")` 追加 EXISTS——候选表最近扫描的 `(device_id, inode)`（inode 字符串列 CAST 整数）命中 `orphan_hardlink_copy_result` 且 `found_count > 1`（含源路径口径，与弹框 copies 剔除源路径一致；NULL 身份/未扫描不命中，fail-closed）；`/list` 与 `/folders/children` 新增同名 Query 参数。无 schema 变更。
- 预扫描范围核查与收紧（用户确认方案）：原 `status != "resolved"` 未排除已忽视（is_ignored 独立列、status 保持 candidate），且包含 quarantined/purged 候选（文件已移动/删除 → 线上 stat_failed=101 主因）。现收紧为 `status == "candidate" AND is_ignored == False`；取消忽视/隔离恢复经 reconcile 重置回 candidate 自动恢复扫描；游标基于 OrphanFile.id 不受影响；被排除身份旧结果行由 30 天保留期正常清理。预期部署后 stat_failed 显著下降。
- 决策记录：实现前经独立子代理审查计划，修正三处（spec 的 listQuery 整对象 toEqual 必挂、handleQuickAction 需先分支、found_count>1 在 budget 截断轮的 fail-closed 漏报可接受并注明）。

### 验证

- 后端相关三文件 92 passed（API 两处精确断言更新 + 3 透传用例；服务层 +4 筛选用例含 CAST/正交/文件夹一致性；扫描排除 +1 用例）；EXISTS 经 SQLite 方言 compile 实测；black/flake8 通过；mypy 与改动前基线一致（149 存量，零新增）。
- 前端 orphan-files.spec.ts 88 passed（新增 5 用例）；本次文件 lint 干净（完整 lint 仍被 keyword 相关 spec 的 5 条 dev 分支存量 warning 拦截，与本次无关）。
- roadmap 行号实测同步（并修正 4da8115 时第三层文档已漂移 3161→实际 3449）；feature_list.json 新增 feature `orphan-located-copies-filter-and-scan-scope`（4 tasks）；progress.md 已更新。

### 回归加固（第三批：+7 后端 / +4 前端，最终 99 / 92 passed，生产代码零改动）

- located 筛选边界：截断行（truncated=1）与共享同一 inode 的两个孤儿明细均命中；身份列脏数据（非数字 inode 字符串/单侧 NULL）fail-closed 不抛错不误命中；scanned_at 过期未清理的行仍可筛出；与 confidence AND 叠加返回交集。
- API 宽松契约：`hardlink_copies=bogus` 原样透传（无 API 层校验，与 status/confidence 口径一致）。
- 扫描收紧交互（最关键）：`stat_limit=1` 两轮间 keyset 游标越过被排除候选不消耗 stat 尝试（`stat_inspected` 断言可分辨排除是否失效），`stat_failed` 只来自在范围内文件；被排除候选既有结果行本轮不删除/不覆盖，保留期任务负责清理。
- 前端：快捷操作切换保留既有筛选一并提交；refreshPageData 保留 located 快照；文件夹视图与 located 同时提交；子表默认不带参数。

### 后续与边界

- 未执行 Git 提交/推送/部署；工作区原有未跟踪产物保持不动。
- 筛选基于候选表最近一次扫描的 (device_id, inode) join 预扫描结果：文件重建（inode 变化）窗口期内可能误命中旧结果；budget_exceeded 截断轮次个别行可能漏报（均 fail-closed 方向，tooltip/注释已注明）。
- 已忽视/已隔离文件不再被预扫描覆盖——用户在"已忽视"视图点开副本数量可能显示"待预扫描"，属预期（历史已扫结果在保留期内仍可用）。

## 2026-08-15 交接：两批改动回归加固完成

### 当前结果

- 本轮对话全部修改已补齐回归保护：备份补偿 12 用例（复用/双源/失败/回滚/筛选排序/映射回退/UUID 仓储-schema-store 链）、协调器 29 用例（full 触发/tracker 不触发/失败不阻断+details）、预扫描 19 用例（中途截止/截断优先级/resolved 跳过/新鲜度排序/budget 落行/任务注册契约/护栏默认值/包装器）、查库契约服务+端点双层符号断言、前端截断提示。
- 关键防回归锚点：交互链路（服务与端点模块）不得 import 遍历函数；任务必须登记 heavy_sync；timeout 必须大于遍历预算；五项 ORPHAN_HARDLINK_SCAN_* 与 TORRENT_BACKUP_RECONCILE_BATCH_SIZE 默认正值；补偿失败不得改变信息同步 outcome；旧结果 scanned_at 不得被未遍历轮覆盖。

### 验证

- 后端 services+api+tasks 全量 2285 passed / 6 skipped；前端全量 738 passed + typecheck + 目标文件 ESLint 0 warning。
- feature_list.json 两个 feature 任务 evidence 已追加回归加固记录；progress.md 与 roadmap 测试计数已更新。
- 本批仅测试与文档，未提交（含上一批预扫描功能实现共 28 个跟踪文件待用户指令提交）。

## 2026-08-15 交接：副本定位改为定时预扫描落库，前端只读结果

### 当前结果

- 用户明确：整体查找副本在文件系统过大时耗时不可控，不能在点击请求里执行。副本位置查找已改为定时任务 `orphan_hardlink_copy_scan`（每日 04:00）后台预扫描落库，`POST /orphan-files/hardlink-copies` 只读库（模块级测试断言服务不再 import 遍历函数），仅保留每文件廉价 stat 复核实时 `st_nlink - 1` 总数。
- 结果表 `orphan_hardlink_copy_result` 按 `(device_id, inode_id)` 唯一存最近一轮结果（含 scanned_at/truncated/scan_note），`orphan_hardlink_scan_state` 单行 keyset 游标跨轮推进避免大库每轮从头 stat。迁移 `c8d9e0f1a2b3`（当前 head，纯增量可回滚）。`device_id` 为 String(32)：Windows `st_dev` 无符号卷号可超 SQLite 有符号 64 位。
- 性能护栏（Settings 可配）：stat 限量 2000/轮、遍历 200 inode/轮、单调时钟预算 300s（os.walk 目录间检查，超时保留部分结果）、单 inode 路径上限 100、结果保留 30 天、写库分批 200 行短事务、遍历单线程串行、heavy_sync 互斥（与其它孤儿/同步任务排队）。
- 遍历语义：未遍历的多副本身份不覆盖旧结果（deferred，接口显示待预扫描）；平凡 0 副本直写；walk 找到的路径包含孤儿源路径本身，接口按请求文件过滤。`find_hardlink_paths_bounded` 提供带预算遍历，原 `find_hardlink_paths` 保留为无界包装（隔离诊断等旧调用方不变）。
- 前端弹框：说明文案、待预扫描计数/标签、扫描时间、等待提示与截断提示；API 类型同步 `scanned_at/pending_scan/result_truncated/scanned_count/pending_scan_count`（移除 `searched_root_count`）。

### 验证

- 后端：`test_orphan_hardlink_copy_scan.py` 10 用例（deadline 部分结果/路径截断/无界对等/deferral/游标推进回绕/幂等更新/保留期清理/单链接不遍历/stat 预算）；`TestHardlinkCopyLocations` 查库契约重写；迁移 34 passed（两表可建可回滚、唯一身份 INSERT 拒绝、全量表 32）；`tests/services + tests/api` 1930 passed 6 skipped；`tests/tasks` 含 profiles 漂移守卫更新后全过；black/flake8 通过。
- 前端：orphan-files.spec.ts 82 passed；全量 737 passed；typecheck/严格 ESLint/build 通过。
- 过程修复：async flush 未 await 致游标挂空、Windows 测试真实收集盘根致全盘遍历（测试 patch 根收集器）、monotonic 15.6ms 分辨率致 budget=0 测试不确定（受控时钟）。

### 后续与边界

- 未执行 Git 提交/推送/部署；工作区原有未跟踪产物保持不动。
- 部署后首轮预扫描前，弹框内多副本文件会显示"待预扫描"——属预期；可在任务管理页手动运行 `orphan_hardlink_copy_scan` 立即补扫（同样受预算约束）。
- 大库收敛速度参考：每轮 stat 2000 个文件；只有 `nlink>1` 的文件进入遍历（每轮 200 个 inode、300s 预算），全量覆盖后游标回绕按结果新旧滚动刷新。若需加快可调大 `ORPHAN_HARDLINK_SCAN_STAT_BATCH_SIZE/MAX_TARGETS`，代价是单轮 IO 更重。
- 任务默认每日 04:00 执行；调度计划可在任务管理页按 Cron 语义调整。

## 2026-08-15 交接：种子文件备份补偿、孤儿副本整体定位与筛选下拉提示语

### 当前结果

- "种子文件管理 6 月 7 日后无变动"根因确认：6 月初同步拆分 info-only 后不再执行种子文件备份（本地库 1042 条备份最新停在 2026-05-29，活跃种子 2.1 万+ 无备份记录）。修复：`sync_coordinator` 在 info-only 与 full 路径单下载器完成后调用 `_reconcile_torrent_file_backups`（L1435），`reconcile_missing_backups`（torrent_file_backup_manager.py L151）按 `TORRENT_BACKUP_RECONCILE_BATCH_SIZE`（默认 200，config.py）限量增量补齐；支持复用已有备份/项目内旧文件、qB `<hash>.torrent` 与 Transmission `<name>.<hash>.torrent` 源文件名；逻辑删除墓碑不自动重建；失败只记 error 不阻断信息同步。
- 连带缺陷修复：备份表 `downloader_id` 为 Integer 但下载器主键是 UUID 字符串，导致按下载器筛选/手动备份/批量导入失效。模型/仓储/schema/端点/前端类型全部改为 String；新增迁移 `b6e1c4d9a2f7`（幂等类型探测 + batch 临时表恢复；downgrade 遇不可无损转整数的 UUID 文本时 raise 拒绝执行——修复测试发现的 SQLite 数值亲和力会把 `550e8400-…` 截断成 `550` 的数据破坏）。迁移链单 head 已验证。
- 孤儿"查找副本"按用户确认口径改为"当前运行环境可访问目录整体查找"：`collect_runtime_accessible_roots`（orphan_quarantine.py L311）不再读下载器映射清单，Linux 读 `/proc/self/mountinfo` 当前进程挂载命名空间、其它平台回退源路径同设备祖先、Windows 枚举盘符；硬链接不跨文件系统，按目标 `st_dev` 严格剪枝 + `os.walk` 跳过符号链接与异设备目录。
- 种子页三个筛选下拉提示语改为"请选择下载器/请选择种子状态/请选择tracker"：`AdvancedMultiSelect` 新增 `placeholder` prop（默认"请选择"），仅改提示不改筛选逻辑；传统视图 Tracker 主域名下拉同批更新。

### 验证

- 后端：新增 `test_torrent_file_backup_reconcile.py` 3 passed（限量/幂等收敛/两种文件名/墓碑/源不可用）；`tests/services` 全量 1061 passed 1 skipped；`tests/api + tests/core` 1250 passed 5 skipped；black/flake8 通过；mypy 错误种类分布与 HEAD 完全一致（新代码 cast 清理后仅 1 处与全仓库惯例相同的 ORM 直接赋值）。
- 前端：全量 44 suites / 737 passed；typecheck、变更文件严格 ESLint 0 warning、生产 build 成功；完整 lint 仍被无关 `keywords-board.spec.ts` 5 条既有 warning 拦截（本次文件 0 warning）。
- 过程中修复：①迁移 downgrade 破坏性回滚拒绝（见上）；②新测试 stub 选择器（vue-test-utils v1 驼峰名不转 kebab，实际为 `advancedmultiselect-stub`）；③HEAD 既有失败的 `torrent-error-reason-ui.spec.ts` 契约漂移（锚点随 5c297b5 迁入 TrackerDetailCard，契约改为扫描卡片源码 + 视图 `:error-reason` 透传）。
- 已同步 roadmap（services/orphan_file_service.md 第三层/infra/frontend/tests/test-coverage/根元信息，行号全部实测）、feature_list.json（新 feature 4 tasks）、progress.md、session-handoff.md。

### 后续与边界

- 未执行 Git 提交/推送/部署；工作区原有未跟踪产物（数据库备份、镜像 tar、tools/ 等）保持不动。
- 2.1 万历史缺口的补齐依赖定时同步逐轮推进（每下载器每轮 200 条），可通过 `TORRENT_BACKUP_RECONCILE_BATCH_SIZE` 调节；建议部署后观察 task 详情 `torrent_file_backup` 统计的 pending 递减。
- 生产部署走正常迁移流程到 `b6e1c4d9a2f7`；如需回滚该迁移且备份表已含 UUID 数据，须从 pre-migration 备份恢复（downgrade 会主动拒绝）。

## 2026-08-14 交接：Tracker 主域名筛选与错误单种排查

### 当前结果

- 复用定时 Tracker 同步任务已经写入的 `TrackerInfo` 数据，新增主机域名列表接口和种子列表 `tracker_domain` 筛选；主机值按 URL hostname 归一，不把端口/路径带入筛选项。
- 列表模式、传统模式均支持 Tracker 主域名多选和“错误单种排查”快捷入口。排查只读调用现有列表接口，要求任务处于错误状态且全局可见的同名同大小内容只有一个任务；同一任务有多个 Tracker 服务不会被误判为重复。
- 列表模式和传统模式现在共用 `views/torrents/components/TrackerDetailCard.vue` 的完整 Tracker 详情弹框，标题、关闭按钮、Tracker/文件/Peers 页签、内容区、错误提示、5 列表格、状态判断和单条汇报事件不再各自维护；组件内部引用 `_tracker-table.scss` 统一字号、间距、状态色、URL 截断和操作列冻结样式，父页面只传入 `list`/`traditional` 定位属性；跨视图切换会保留错误单种排查模式及查询条件。
- 新增/加强 `tracker-detail-card.spec.ts` 与 `traditional-view-component.spec.ts` 运行时和静态回归，锁定完整弹框骨架、两种 layout、列结构、snake/camel 字段、错误/中性状态、汇报事件和按钮 loading，配合父页面静态契约防止两种模式重新出现不同 Tracker 卡片代码。

### 验证与后续

- 后端列表 API 定向回归 `35 passed`；前端目标 4 个 Jest 套件 `44 passed`；`npm run typecheck`、目标 ESLint、生产构建通过；完整 `npm run lint` 仍被 3 个无关关键词测试文件的 5 条既有 warning 阻断；真实 30475 条 Tracker 数据域名提取 5 次为 `231.515–262.118ms`，低于 1 秒，未引入内存缓存。
- 已同步 `feature_list.json`、`progress.md` 与三层路线图；本轮未提交、未推送、未部署。工作区原有未跟踪文件未触碰。

## 2026-08-14 交接：超量扫描改为可关闭提醒

### 当前结果

- 用户确认超量扫描仅作为提醒，页面可手动关闭，不再要求填写核查说明或完成双重核查。
- 前端移除双重核查按钮/输入流程，超量提醒改为 warning 类型并按当前 `scan_id` 可关闭；新批次重新显示。
- 后端移除 `cleanup_review_required` 对清理放行的阻断；保留历史字段和兼容 `/guardrail-review` 接口，不再依赖复核记录。手动、快捷和定时清理继续执行 completed/scan_id、实时 manifest、路径授权和文件身份校验。
- 新增参数化后端回归，锁定超量批次在清理预览、前缀快捷、手动和定时四条入口均不被提醒拒绝；前端回归同时锁定历史复核时间字段不再影响提醒/清理语义。

### 验证与后续

- 已更新前后端回归、`feature_list.json`、`progress.md` 与三层路线图；后端相关套件 `333 passed, 1 skipped`，前端 orphan/API 套件 `118 passed`，类型检查、目标 ESLint、生产构建、Python 编译和 `git diff --check` 已通过。
- 本轮准备提交，未推送或部署；任务前已有未跟踪文件保持不动。

## 2026-08-14 交接：孤儿文件页面视图模式与嵌套表头修复

### 当前结果

- 已修复扁平模式仍显示左侧展开按钮：主表的 `expand` 列现在只在 `folderView` 开启时注册。
- 已修复文件夹模式展开后出现第二套列头：懒加载子表显式关闭表头；普通文件行的 Element UI 展开箭头隐藏规则也已移到正确的页面作用域。
- 根因是页面结构条件未覆盖表格列/子表渲染，且原箭头 CSS 规则被嵌套在不匹配的 `.hardlink-location-summary` 作用域；后端接口、文件夹聚合、懒加载分页和选择逻辑未改动。
- 已同步 `docs/roadmap/`、`feature_list.json` 和 `progress.md`；本轮已获授权提交并推送，仍不部署，工作区原有未跟踪文件保持不动。

### 验证与已知基线

- `frontend/tests/unit/orphan-files.spec.ts` 定向回归 `81 passed`，覆盖模式动态切换、普通文件行展开 class/懒加载事件，以及子表隐藏表头后仍保留数据行和选择事件；TypeScript、改动文件 ESLint、生产 build、`git diff --check` 通过。
- 生产 build 仍有仓库既有 51 条 Sass/Element UI/Browserslist warning；完整前端 lint 被 3 个无关关键词测试文件的既有 5 条 warning 阻断，无本次文件错误。
- 根 `./init.sh --ci` 在当前 Windows 主机因找不到 `/bin/bash` 未能执行；此次未修改后端。

## 2026-08-14 继续交接：孤儿扫描定时入口已回接 Cron

### 当前结果

- 修复 `OrphanScanTask` 只提交 queued 就返回 success 的回归：定时入口提交后等待同一 `OrphanScanDispatcher` 的扫描+自动清理终态；扫描失败/超时、部分清理失败和超量门禁拒绝均不再伪造 success。
- dispatcher 返回 `scan_result`、`cleanup_result` 和阶段摘要；Cron 内部类执行器透传业务 outcome，并把阶段摘要、scan_id 和终态写入现有 `task_logs`，没有新增独立孤儿日志体系。
- HTTP/手动扫描仍立即返回 `scan_id/task_id/status=queued`，页面轮询接口与 120100 条安全门禁没有改变；路径映射与孤儿样本复核前未执行清理。

### 验证与后续

- 定向回归 `39 passed`，`backend/tests/tasks` `331 passed`，目标 Python 文件编译通过。
- 本轮源码、测试、路线图和项目记录已提交为 `d0d2a9e` 并推送到 `origin/dev`；提交只包含本轮跟踪文件，工作区既有未跟踪目录保持不动。Black 在当前 Windows 进程中仍会超时，Flake8、`py_compile`、`git diff --check` 与定向回归已通过。

## 2026-08-14 交接：孤儿迁移中断恢复与大库回填修复

### 当前结果

- 后端重部署报 `no such column orphan_current_candidate.current_detail_id` 的首因不是对账逻辑，而是上一轮 Alembic 迁移没有完成：1.02GB 旧库留有 `_alembic_tmp_orphan_scan_result`，重启重试会先报临时表冲突；继续后原回填 SQL 又因索引选择退化。
- revision `7b2c9d4e6f10` 已支持残留 batch 表幂等恢复、原表缺失 fail-closed、原生快速加列和 canonical_path 索引强制回填；大表 downgrade 也合并为单次 batch。
- 迁移入口现在保留真实异常日志并校验最终 head；FastAPI lifespan、`main.py` 直接运行及桌面入口都会在迁移失败时终止，ORM 对账不会再把首因掩盖成缺列错误。
- 原始 `E:\Users\huangzj\Desktop\app.db` 与线上库均只读，未改动；没有对任何 120100/120219 条历史批次执行清理。超 50000 条批次仍需路径映射和孤儿样本双复核。

### 验证与后续发布

- 用户真实库的工作区副本从 `4c1d8e7a2b90` 升到 `7b2c9d4e6f10` 约 4.97 秒；202669/202669 候选完成稳定明细绑定，完整性、外键、唯一索引和超量门禁均通过。
- 定向回归 `66 passed`（含假成功版本校验）；compileall、Flake8、目标 mypy 通过。Black 对涉及文件已实际重排，但 Windows 退出卡住导致命令超时，后续检查未发现格式相关编译/lint 问题。
- 当前代码尚未提交、推送或重新部署。发布时应先保留并验证迁移前备份，只启动单个新后端实例，确认日志显示迁移到 `7b2c9d4e6f10` 后再开放流量；不得手工 stamp 或清理 `_alembic_tmp_*`/孤儿数据。

## 2026-08-13 交接：孤儿扫描后台化、稳定明细与超量清理门禁

### 当前结果

- 扫描 POST 已改为立即返回持久化 `scan_id/task_id`，页面只轮询单批次轻量状态；调度器串行执行、恢复 queued，启动把遗留 running 标记 failed。
- 文件系统每轮仍会重新核查，这是 resolved/路径变更判定所必需；“不再扫描同样 12 万条”的落地语义是已知路径复用 `current_detail_id`，不再按扫描批次重复插入 12 万条明细，生命周期仍照常更新。
- 生命周期 query/update/resolved、可清理查询及启动稳定明细对账均分批，并让每批完整进入 `db_write_scope`。文件夹展开后才加载独立分页子项，硬链接实时统计仅处理当前可见文件。
- 迁移 `7b2c9d4e6f10` 是当前单 head。超 50000 条批次及其仍有活跃候选的未复核后续链全部拒绝预览、手动清理和自动清理；需显式完成路径映射+孤儿样本双重核查并记录说明。
- 本次没有执行任何清理。因此日志中的 120100 条数据当前应保持原状，部署后也会先被迁移门禁锁定。

### 验证与已知基线

- 孤儿后端套件最终 `369 passed, 1 skipped`（包含门禁传递、迁移/生命周期、存量候选即时绑定稳定明细与真实文件 SQLite 120100 条争用回归）；12 万用例验证无重复明细且状态 API P95/最大分别 `<1s`/`<3s`，单跑约 42 秒。
- 前端 `2 suites / 112 tests`、typecheck、改动文件 ESLint、生产 build 通过；后端 Flake8、compileall、新增后台任务/API/startup/task 文件 mypy 通过；根 `init.sh` 通过。
- 生产 build 仍报告既有 51 条 Sass/Browserslist warning；全任务 mypy 在历史 SQLAlchemy 1.x ORM `Column` 标注上有 203 条既有错误。
- 已更新 feature_list、progress、session handoff、迁移约束和三层代码路线图；未提交、未推送、未部署，工作区中的其它未跟踪文件未触碰。

## 2026-08-13 交接：辅种异常排查改为当前列表分页

### 当前结果

- 最新提交 `ea5a5f3` 的独立排查弹窗/端点/诊断服务已移除；当前入口不会打开新窗口或弹窗。
- 两种种子视图均通过现有 `GET /api/v1/torrents/getList` 发送 `same_content_only=true`，继续复用普通筛选、排序、刷新、每页条数和 `skip/limit` 行级分页。
- 当前表格上方显示排查状态与退出入口；切换列表/传统视图会保留 `showingSameContent`。
- 同内容判定为“名称相同 + 大小相同 + 至少两个不同规范化 InfoHash”，普通筛选先参与候选判定；只加载当前页关联数据，无数据库迁移。

### 验证与已知基线

- 后端定向回归 `40 passed`（同内容专用 9 用例），覆盖组合筛选、活动删除/活动快照、复合主键稳定分页、低 SQLite 变量上限大页与仅当前页 Tracker 预取；前端 `3 suites / 36 tests passed`，覆盖列表操作保持模式及切换其它查询源清理模式；TypeScript、改动文件 ESLint、生产 build、Black、Flake8、py_compile 与 `git diff --check` 通过。
- 根 `init.sh` 经 `E:\\Git\\bin\\bash.exe` 运行完成，前端子脚本有既有 warning。
- 最终全量回归：后端 `3376 passed, 7 skipped`；前端 `43 suites / 719 tests passed`。
- 完整前端 lint 仍被 3 个无关关键词测试文件 5 条既有 warning 阻断；后端 mypy 的 64 条既有 ORM/Pydantic 类型错误未在本任务扩大修复。
- API 文档、路线图、feature_list 与 progress 已同步；本轮修改已纳入同一提交范围，未推送、未部署。

## 2026-08-13 交接：同名同大小种子只读异常排查（已被上方方案替代）

### 当前结果

- 列表模式与传统模式的“快捷操作”均可打开“辅种异常排查”；两者复用 `SameContentInspectionDialog.vue`。
- 后端按名称、大小精确相等且规范化 InfoHash 至少两个不同值分组，不要求跨下载器，因此能覆盖用户提供的“同一下载器内多个站点、不同 Hash”数据形态。
- 弹窗支持完整结果与仅错误种子；错误联合任务状态/原因/聚合标记、Tracker 持久化状态、原始失败码与启用失败关键词。结果按组分页，完整模式含健康成员，仅错误模式只含错误成员。
- 接口是纯 DB 只读查询，不调用下载器且没有写操作。Tracker 只返回 host，URL 路径、query、passkey/token 等凭据均不返回或已脱敏。
- 新端点：`POST /api/v1/torrents/same-content-inspection`；无数据库 Schema 或 Alembic 迁移。

### 验证与已知基线

- 后端新 API `4 passed`；相关回归 `48 passed`；新增后端文件 mypy、Black、Flake8、py_compile 通过。
- 前端 `3 suites / 36 tests passed`，typecheck、改动文件 ESLint、生产 build 通过；build 仅有既有 warning。
- 完整前端 lint 仍受任务前已有的高级搜索生成契约漂移与 3 个关键词测试文件 5 条 warning 阻断，本次文件 0 warning。
- 大型后端回归并行执行时超时，未把未完成运行记为通过；直接相关回归已改为顺序执行并全部通过。
- 路线图、API 说明、feature_list 与 progress 已同步。用户已授权仅提交并推送本功能相关文件；任务前已有未跟踪目录均未触碰，未部署。

## 2026-08-13 交接：最新提交 Tracker 策略回归加固

### 当前结果

- 已查看最新提交 `625c1e3d0c423c56ac40a28828a3a96378d061dd`，确认其修复 Tracker Working 空消息判定。
- 新增 `backend/tests/core/test_tracker_status_policy.py`，为共享策略纯函数补充 30 个直接回归用例，覆盖 Working 空消息、非空消息优先、announce/scrape 双消息、匹配模式和证据聚合。
- 未修改业务实现；原有未跟踪技能、工具和计划目录保持不变。

### 验证与环境说明

- 新增测试 `30 passed`；服务层/种子级相关回归 `115 passed`；同步协调器回归 `26 passed`。
- 新测试可编译，代码行长度检查与 `git diff --check` 通过。
- 根 `init.sh` 受 Windows WSL `E_ACCESSDENIED` 阻止；Black `--diff` 确认文件无需改写，但 `--check` 在当前主机超时。
- Git 提交范围仅包含本次测试与配套记录，并推送至 `origin/dev`；未执行部署。

## 2026-08-12 交接：Tracker Working 空消息行级残留完整修复

### 当前结果

- 最新快照证明部署仍是旧版本：Alembic 为 `de898cb28172`，判断 Cron 为旧 `0 */5 * * *`；本地分支
  仍比 `origin/dev` 多提交 `196a530`，因此上一轮修复和 `4c1d8e7a2b90` 迁移尚未进入部署来源。
- 已补齐真正遗留缺陷：Tracker 行级状态同步不再跳过 `Working(2) + None/空白消息`，会按行清理历史
  `error/失败`；种子级与行级统一复用 `tracker_status_policy.py` 的状态码+关键词证据语义。
- Working 空消息仅修复当前 Tracker 行，不作为 host 全局正常证据，避免同站点不同种子相互掩盖；
  非空消息仍优先，announce/scrape 都参与，未知消息保留原值，全部明确失败才判错。
- 独立状态判断任务仍为 `20,50 * * * *`，位于 Tracker 同步 `10,40 * * * *` 后 10 分钟；既有迁移
  `4c1d8e7a2b90` 在新镜像真正包含代码并启动后才会落库。

### 快照与验证

- `E:\Users\huangzj\Desktop\app.db` 全程只读且 `quick_check=ok`。zimiao 域名相关 359 行中恰有
  152 行 `Working + 空消息 + error/失败`，行级重放只恢复这 152 行；种子级会清理 294 个历史错误，
  并把 2 个“全部明确失败”的旧正常标记纠正为错误。
- 行级 `40 passed`、种子级 `75 passed`、同步协调器 `26 passed`（含成功后执行、失败时跳过）；最终
  后端全量 `3337 passed, 7 skipped`。目标 mypy、Flake8、Ruff、Black（变更源码/行级测试，
  `--no-cache`）、compileall、
  BtDeck 架构门禁、单 head `4c1d8e7a2b90`、feature JSON 与 `git diff --check` 通过。
- 根 `init.sh` 仍因 Windows WSL `E_ACCESSDENIED` 无法启动；已按脚本内容完成 harness、后端环境及
  前端 Node/配置等价检查。PowerShell 的 `npm.ps1` 受本机执行策略限制，但本次无前端变更。
- 当前新增修复尚未提交、未推送、未部署；任务前已有备份、镜像、缓存及工具未跟踪文件未触碰。

## 2026-08-12 交接：Tracker Working 空消息判定与独立 Cron 错峰

### 当前结果

- 状态判断仍联合使用下载器状态码和关键词：Working 且 announce/scrape 消息均为空时明确正常；
  有非空消息时关键词继续生效，未知消息保持原值，未联系/发送中仍为中性。
- 独立状态判断任务改为 `20,50 * * * *`，在 `10,40 * * * *` 的 Tracker 状态同步后 10 分钟；
  新 head `4c1d8e7a2b90` 只迁移未自定义的系统旧值，并支持对称 downgrade。
- `E:\Users\huangzj\Desktop\app.db` 始终只读。346 个 zimiao 样例重放为 316 正常、30 明确错误、
  0 未知；293 个历史错误标记会由下一轮状态判断清除。
- 新增 36 组 zimiao 双 Tracker 顺序/下载器类型/空消息矩阵，并覆盖真实 SQLite 写回、软删除、
  同步/判断重任务互斥和迁移幂等/自定义值保护。
- 按用户要求仅提交本次相关文件，不推送、不部署；任务前已有的备份、镜像、缓存及工具未跟踪文件未触碰。

### 验证与环境说明

- 判断+迁移定向 `80 passed`；迁移/回滚/任务准入相关 `130 passed`；后端全量
  `3316 passed, 7 skipped`（3323 collected）。
- 目标 mypy、Flake8、Ruff、Black API check、compileall、BtDeck 架构门禁、单 Alembic head、
  feature_list JSON 解析和 `git diff --check` 通过。
- 根 `init.sh` 因 Windows WSL `E_ACCESSDENIED` 未运行，已用后端全量及分项工具完成等价校验。

## 2026-08-12 交接：高级搜索跨字段回归矩阵加固

### 当前结果

- 功能修复先独立提交为 `99ccf65`；其后以独立测试提交承载第二批纯测试/证据修改，覆盖跨字段
  补集、空值分区、Tracker 关系边界和前端模板请求协议，并随 `dev` 推送 `origin/dev`。
- 新增后端 20 个参数化实例、前端 29 个 Jest 实例；未修改业务实现或数据库 Schema。
- 任务开始前的未跟踪备份、镜像、缓存与工具目录未加入暂存，也未修改。

### 验证

- 后端重点 `162 passed`，全量 `3253 passed, 7 skipped`；Black/Flake8 通过。
- 前端重点 `2 suites, 111 passed`，全量 `43 suites, 715 passed`；TypeScript 通过。
- 前端全量存在既有 Vue 浅渲染告警/Browserslist 提示，但退出码为 0；静默复跑确认总数。

## 2026-08-12 交接：高级搜索全字段语义修复

### 当前结果

- 已完成状态字段之外的 20 字段审计与修复：Tracker 关系否定采用 `NOT EXISTS`；文本 `%`/`_`
  字面匹配；标签完整 token；下载器稳定 ID + 新旧 nickname 兼容；超级做种是/否/不支持三态；
  完成时间/比率/比率限制/标签/分类提供字段级空值查询；回收站不再进入高级搜索基础集。
- 前端 Builder 只展示字段契约允许的操作符；空值条件不显示输入框；下载器显示 nickname 但提交
  ID；模板旧布尔/标签操作符可兼容回填。
- `mode=exclude` 现在作为独立协议字段贯穿 Builder、模板、`torrentBatch`、Pydantic 与 ORM，
  操作符不再提前翻转，后端取严格补集并正确包含 NULL/未设置值。
- 用户原始结构 `tracker_url contains azusa` + `status in [error]` 已用真实内存 SQLite 验证，
  返回 `total=1`。
- 无数据库迁移；功能修复已提交为 `99ccf65`。此前未跟踪的备份、镜像、缓存与工具目录均未触碰。

### 验证与环境说明

- 后端全量 `3233 passed, 7 skipped`，相关套件 `235 passed`、语义重点 `142 passed`；前端全量
  `43 suites, 686 passed`，相关 4 suites/`119 passed`、重点契约 2 suites/`82 passed`。
- Ruff、Flake8、目标 ESLint、TypeScript、`contract:check`、生产 build、`git diff --check` 通过。
- 根 `./init.sh` 在当前 Windows 环境无法启动：默认 WSL 返回 `E_ACCESSDENIED`，提权运行环境无
  `/bin/bash`；本轮采用分端等价校验。完整前端 lint 仍只受 3 个无关关键词测试文件的 5 条既有
  warning 影响。

## 2026-08-12 交接：种子文件、任务日志、高级搜索与错误原因七项修复及回归加固

### 当前结果

- 后续三项修正已完成：高级搜索“添加条件”居中并改主按钮，“添加条件组”改次按钮；组间
  AND/OR 位于条件组卡片外。`error` 高级搜索现与普通列表同义，可命中
  `status='error'` 或 `has_tracker_error=True`，用户提供的 azusa 组合载荷已有真实 DB 回归。
- Tracker“未联系”误归类的根因已修复：Transmission 不再把成功布尔值当状态码写库，
  announce/scrape 按联系、成功、超时和活动状态归一；定时判定将 qB 未联系及 Transmission
  未联系/发送中视为中性，仅全部明确失败时设置 `has_tracker_error=True`。
- 种子文件管理的下载器列由列表 API 单次批量解析并返回当前 nickname；刷新列表会反映改名，
  无逐行动态请求，缺失下载器显示 `-`。搜索区已统一为项目 management-page 风格。
- 任务日志导出/清理按钮使用项目标准成功/警告样式。从任务列表查看日志会显示当前任务筛选；
  “清空”同时清除 task_id、普通筛选和日期并立即加载全部日志。
- 高级搜索 `status` 已改为与下载器相同的 `AdvancedMultiSelect` 精确多选控件，不允许创建
  自定义值；旧模板标量及 equals/not_equals 会兼容归一为数组和 in/not_in。
- 组内“添加条件”位于条件列表底部，全局“添加条件组”在其下方，降低误触。
- `torrent_info.error_reason` 已通过可回滚 Alembic `de898cb28172` 增加。Transmission FULL、
  INFO-ONLY、legacy 和新增记录路径同步 errorString；错误原因变化可单独触发更新，恢复后清空。
- API 以 `errorReason` 输出；列表/传统两视图都在名称 hover tooltip 与 Tracker 卡片显示原因。
- 功能修复已独立提交为 `82ceed8`；后续测试与项目记录作为独立回归加固提交交付。
- 路线图、迁移清单、测试矩阵、功能状态与进度记录已同步；未 push/deploy。

### 验证与已知基线

- 回归加固新增 33 项后端和 2 项前端用例，覆盖高级搜索运算符真值表、Transmission 新旧 RPC
  与四类写库入口、定时任务真实 SQLite 批量更新、多条件组连接器顺序/删除收敛及前端中性边界。
- 后端全量：`3215 passed, 7 skipped`；前端全量 `43 suites, 676 tests`；typecheck、生产 build、
  变更文件严格 ESLint、目标 Ruff/Flake8、Git Bash 根 `./init.sh --ci` 与 `git diff --check` 通过。
- 完整前端 lint 仍仅有 3 个无关关键词测试文件的 5 条既有 warning（0 error）；Windows Black
  目标检查复现超时，未重排存量测试文件。
- 后端全量：`3171 passed, 7 skipped`；相关定向 88 passed；修改文件 Flake8 与
  `git diff --check`、Git Bash 根 `./init.sh` 通过。
- 前端全量：`43 suites, 672 tests`；typecheck、生产 build、修改文件严格 ESLint 通过。
- 本地浏览器实测文件管理布局、任务按钮、任务日志 2→6 条清空恢复、状态多选与添加按钮层级；
  临时浏览器/服务/QA 数据库均已关闭或删除。
- 完整前端 lint 只剩 3 个无关关键词测试文件中的 5 条既有 warning；目标 mypy 为仓库既有
  SQLAlchemy/Pydantic 类型债 142 条；Windows Black 26.5.1 检查存在超时，Flake8 无错误。
- 工作区任务前已有的未跟踪备份、镜像、缓存与工具目录均未触碰。
- `roadmap-maintain` 技能包未附带说明中提到的漂移脚本，已用源码关键符号行号、文件末行、
  测试文件计数及链接回读替代；本轮未 stage/commit/push/deploy。

## 2026-08-11 交接：种子重复查询、任务页与管理界面六项修复

### 当前结果

- 列表模式与传统模式的“查找重复任务”均为默认关闭的页面级开关，开启态绿色；开启后筛选、排序、分页、分页大小和刷新保持重复查询数据源，跨视图切换也保留模式。
- 重复查询默认按添加时间倒序，支持安全列排序、分类/标签及活动快照筛选；活动大集合通过连接级临时表过滤。
- 定时任务页面已通过 Vue 实例方法暴露 `getTaskOutcomeMeta` / stale helper，控制台缺失函数错误已修复。
- 回收站搜索区与孤儿文件管理页使用同一 UI 结构；查询模板行操作改为带 tooltip/ARIA 的 Lucide 极简图标。
- 高级搜索新增左侧已保存配置栏，可筛选、选择回填、新建、覆盖更新和删除；系统/他人公开模板只读，两种种子视图共用同一工作区。
- 已补充充分回归保护：重复 API 非法排序/完整组/活动快照边界、两种视图真实绿色开关点击与跨视图状态、高级搜索单次重置/竞态/校验、任务 helper AST 实例方法，以及管理页 UI 细节契约。
- 路线图、功能清单与进度已同步；无 Schema/Alembic 变更。

### 验证与已知基线

- 后端：重复查询 `40 passed`；全量 `3163 passed, 7 skipped`；目标 Black、Flake8、mypy 通过。
- 前端：高风险相关 `6 suites/69 tests`，全量 `41 suites/657 tests`；typecheck、修改文件严格 ESLint、生产 build 通过。
- 完整前端 lint 仅剩 3 个无关关键词测试文件的 5 条既有 warning；build 仅有既有 Sass/Browserslist/体积 warning。
- 最终 Git Bash 根 `./init.sh`、`git diff --check`、feature_list JSON 解析与路线图陈旧模式扫描均通过；前端 init 仅保留既有 null-byte warning。用户已授权仅提交本次相关文件，不 push/deploy。
- 工作区任务前已有的未跟踪备份、镜像、缓存与工具目录未触碰。

## 2026-08-11 交接：硬链接副本数量可点击核对位置（含回归加固）

### 当前结果

- 孤儿文件表中副本数量大于 `0` 时可点击；`0` 与未知值不可点击。点击后懒加载位置，不增加列表阶段的目录扫描。
- 后端在全部已配置可扫描下载目录中批量查找其它硬链接；同一请求的多个 inode 只遍历一次扫描根，并去重重叠根、物理路径和符号链接。
- 弹框按源文件展示完整路径和复制按钮，同时显示文件系统总副本数、已定位数、未定位数、未知源文件及扫描错误；配置目录以外或不可访问的链接会明确计入未定位。
- 文件夹聚合行只提交其中副本数量大于 `0` 的子文件，并在同一弹框中分组展示。
- 新增认证端点 `POST /api/v1/orphan-files/hardlink-copies`，沿用统一响应格式；无数据库 Schema 或 Alembic 变更。
- 用户验证交互通过后新增 7 个回归用例，覆盖多 inode 单次扫描、重复 ID、扫描失败降级、HTTP 批量边界、前端过期响应隔离与异常状态释放。
- 路线图、功能清单和进度记录均已同步。

### 验证与已知基线

- 后端服务/API 定向 `53 passed`；后端全量 `3153 passed, 7 skipped`；目标 Flake8、py_compile 和新增 Black 检查通过。
- 前端全量 `39 suites, 643 passed`；typecheck、修改文件严格 ESLint、生产 build 通过。
- 全量前端 lint 仅剩 5 条无关既有 warning；目标 mypy 仅剩大服务既有 149 条 SQLAlchemy Column 类型债，本次均零新增。
- Git Bash `./init.sh` 与 `git diff --check` 通过；用户已授权在根目录提交，不执行 push/deploy。
- 分支 `dev` 在任务前已领先 `origin/dev` 1 个提交；本次仅提交功能相关跟踪文件，工作区原有 13 个未跟踪备份、镜像和工具产物不纳入提交。

## 2026-08-11 交接：孤儿文件硬链接副本数量已显示

### 当前结果

- 孤儿文件列表 API 实时返回 `hardlink_copy_count = max(st_nlink - 1, 0)`；计算不包含当前文件自身。
- 普通文件返回 `0`；文件在扫描后已消失或 `stat` 失败时返回 `null`，前端显示 `-`，不伪装成无副本。
- 文件夹折叠行在所有子文件可读时返回副本数合计，任一子项未知则合计为 `null`。
- 文件系统读取经 `asyncio.to_thread` 移出事件循环并顺序执行，避免列表请求阻塞 loop 或并发打满 NAS。
- 前端孤儿文件表新增“副本数量”列；API 类型、扁平行和文件夹行契约均已同步。
- 本次没有数据库字段或 Alembic 迁移。

### 验证与已知基线

- 后端孤儿相关：`345 passed, 1 skipped`；定向列表/文件夹/API 组合 `82 passed`。
- 前端：`orphan-files.spec.ts` 72 passed；typecheck、修改文件严格 ESLint、生产 build 通过。
- 全量前端 lint 仍被关键词测试的 5 条既有 warning 拦截；目标 mypy 仍为大服务既有 149 条 SQLAlchemy Column 类型债，本次均零新增。
- Git Bash `./init.sh` 通过；未 stage/commit/push/deploy。
- 工作区原有 13 个未跟踪备份、镜像和工具产物未触碰。

## 2026-08-11 交接：按报告完成 P0/P1/P2 修复（生产门待执行）

### 实施结果

- `torrents_async.py` 的 qB/TR info/full、`torrent_sync.py` legacy 与 `sync-single` 全部复用
  `app.state.store` 缓存客户端；缓存缺失明确失败；sync-single 使用 AsyncSession 异步查询。
- qB Tracker durable cursor 只跨连续成功且已提交前缀；远程 enrich/Tracker 提取/批提交失败均不跨游标。
- qB/TR info 支持稳定 hash cursor、单轮预算后的 durable progress callback；存在 cursor 时强制完整快照，
  防止增量列表遗漏 cursor 前的变更。
- WAL 观测接入 PASSIVE checkpoint（busy_count/checkpoint_busy）；同步健康端点增加有界 DB 查询超时。
- 新增生产止血手册：[`backend/docs/operations/sync-stopgap-runbook.md`](backend/docs/operations/sync-stopgap-runbook.md)。

### 验证与剩余门禁

- 定向：83 passed；coordinator/checkpoint/governance/metadata/legacy 70 passed、5 skipped；
  memory-bound/file contention 18 passed、1 skipped；health 10 passed；ruff/diff-check 通过。
- 后端全量 pytest：`3142 passed, 7 skipped`（3149 collected）；修复后大档基准 30 轮/600 探针
  无超时、最终 BUSY=0、SLO 4/4 PASS，JSON 位于临时目录
  `C:\Users\huangzj\AppData\Local\Temp\btdeck-sync-fix-20260811`。
- 未对本地 `backend/config/app.db` 执行 Alembic 迁移；未执行生产 cron 暂停/恢复演练；30 轮发布基线需归档。
- Black 全文件检查在 Windows 环境超时并提示既有格式债。未 stage/commit/push/deploy。

## 2026-08-10 交接：W0-W4-2 从头实现验证完成（发布门仍有缺口）

本轮不是只复核 W4-2，而是从 W0 到 W4-2 独立审计实现、测试和运行证据。详细结果见 [`backend/docs/operations/database-blocking-and-sync-verification-2026-08.md`](backend/docs/operations/database-blocking-and-sync-verification-2026-08.md)。本轮未修改业务代码、未执行 Alembic 迁移、未 stage/commit/push。

### 已复核证据

- 后端全量 pytest 摘要：`3135 passed, 7 skipped`；pytest 已输出最终摘要，Windows 包装命令之后因 300 秒超时返回 124。
- 真实文件型 SQLite 大档：22000 torrents / 30000 trackers / 30 轮，600 次探针无超时、BUSY=0、SLO 4/4 PASS。
- `health.py` mypy、flake8 和 `git diff --check` 通过；系统 `bash.exe`/WSL `E_ACCESSDENIED`，所以 `./init.sh --ci` 未能在本环境执行。

### 必须先处理的缺口

1. **P0**：`SyncCoordinator` 的 info/full canonical 路径在缓存客户端为空时仍 fallback 自建 qB/TR 客户端；`sync-single` async handler 直接同步 `db.query`，SQLite 锁等待可能阻塞事件循环。扩展架构扫描覆盖 `torrents_async.py`/`torrent_sync.py`。
2. **P1**：qB Tracker 游标可越过未处理 hash。复现：预算 2、批大小 1000、5 个 hash，只调用前 2 个却返回最后 hash 的游标。info-only 部分运行没有记录级 cursor。
3. **P2/W4-1**：运行时 `busy_count`、`checkpoint_busy` 仍为 `None`；W0 专用生产止血 Runbook 和暂停/恢复演练证据缺失。
4. 当前本地 `app.db` 迁移为 `f9a1b2c3d4e5`，仓库 head 为 `f5e6d7c8b9a0`；真实 `/health/ready`/同步健康验证需在受控迁移后进行。

### 后续顺序

先修 P0 连接/DB 边界，再修 P1 durable cursor 与 info 续跑语义，随后补 W4-1 SQLite busy/checkpoint 观测和 W0 运维演练；修复后重新跑全量测试、大档 30 轮基准、迁移后健康接口和发布门复核。

## 2026-08-10 交接：W4-2 实施完成（liveness/readiness/同步业务健康接口）

当前任务：`PLANS/sync-database-blocking-remediation.md` 的 W4-2（G4 门）已完成，代码与测试已亲跑通过；分支 `dev`，未执行 stage/commit/push/deploy。

### 本次改动

- 新增 `backend/app/api/endpoints/health.py`：
  - `/health/live` 仅响应进程存活，不访问 DB/下载器。
  - `/health/ready` 严格超时执行只读 `SELECT 1`，复用 `startup_guard` 的 SQLite 单 Worker 校验和 `EventLoopLagSampler`；失败为 503 统一响应体，原因只返回稳定 `reasonCodes`。
  - `/api/v1/health/sync` 受认证保护，返回任务 outcome/freshness、active run/phase、checkpoint age，并以缓存下载器状态生成业务告警；下载器离线不影响 readiness。
- `sync_coordinator.py` 增加进程内只读 active-run 快照，贯穿 admission/backup/sync/tracker_status/done，不在健康检查中写业务事实。
- 根路由与 `/api/v1/health/*` 别名已接线；`backend/Dockerfile`、`docker-compose.yml` 健康检查从 `/docs` 改为 `/health/ready`，Compose `start_period` 保持 5 分钟。
- 已按 `roadmap-maintain` 最小范围同步 `docs/roadmap/deploy/README.md` 的健康检查路径；W5 再做路线图全量收口。
- 为 Windows 测试环境修正 Git Bash 选择顺序，并显式按 UTF-8 解码启动脚本输出；不改变生产启动脚本。

### 验证证据

- `python -m pytest tests/api/test_health.py -q`：9 passed。
- `python -m pytest tests/core/test_sqlite_worker_guard.py -q`：53 passed。
- 同步 Coordinator/观测回归 59 passed；cron/auth 回归 76 passed。
- 后端全量 `python -m pytest -q`：**3135 passed, 7 skipped, 0 failed**（3142 collected）。
- `./init.sh --ci`、health.py mypy、修改文件 black/flake8 通过。
- 无 Schema 变更，不新增 Alembic 迁移；当前迁移 head 仍按计划为 `f5e6d7c8b9a0`。`feature_list.json` 与 `progress.md` 已更新。

### 后续工作

1. G4：将大档 `--assert-slo` 接入发布门/nightly，完成告警阈值两周基线校准与 runbook 联动。
2. W5：Tracker 指纹、DBWriteQueue ADR（先观察 7 天指标）、PostgreSQL 计划重写条件演进、roadmap/文档全量收口。
3. 上线前执行 Alembic 迁移（head `f5e6d7c8b9a0`）。

## 2026-08-09 交接：W4-1 实施完成（阶段级结构化观测与核心指标）

当前任务：修复计划 W4-1（P1-06/P2-05）实施完成，拆两部分子代理执行 + 主代理逐项审查通过

分支：dev
状态：W4-1 代码与测试完成；未提交、未推送。

### 本次改动（backend 8 文件 + 2 测试文件）

- **新 `app/services/sync_observability.py`**：稳定事件名（EVENT_SYNC_RUN_START/ADMISSION/BATCH_COMMIT/CHECKPOINT/DOWNLOADER_CALL/LOOP_LAG/WAL_SNAPSHOT）+ EVENT_FIELDS 白名单 + `log_event`（key=value + 脱敏：敏感 key 遮蔽/URL 去 query/userinfo/hash 前 8 位，复用 log_sanitizer）+ `EventLoopLagSampler`（call_at 漂移法，p95/p99/max，异常恢复，`SYNC_LAG_SAMPLER_ENABLED` 开关）+ `snapshot_wal_stats`（只读）。
- **`_attach_done_stats` 修复**：cancelled future 先 `fut.cancelled()` 判断 + `except BaseException`（CancelledError 不再泄漏）。
- **run_id contextvars 贯穿**：set_run_id/clear_run_id + log_event 自动附加；coordinator/sync_db_write/downloader_api_runtime/tracker_status_sync 全部接入；lifecycle 挂载 lag 采样器 + WAL 快照；阈值告警（lag 单次>500ms/P99>100ms、commit>500ms → WARNING）。
- **主代理修复**：阶段顺序测试 caplog 断言受 alembic fileConfig 干扰 → 改 spy 断言；删除子代理 DIAG 残留。

### 验证（主代理亲自复跑）

- 全量 `pytest`：**3126 passed, 7 skipped, 0 failed**（249.8s）。
- 新增：test_sync_observability 26 + coordinator 阶段顺序 2；black/flake8 通过。

### 下一步

1. **W4-2**：liveness/readiness/同步业务健康接口（GET /health/live、/health/ready 严格超时 SELECT 1 + SQLite 单 Worker 合规 + lag 近期状态；Docker/Compose 健康检查从 /docs 改 /health/ready；受保护同步健康端点返回各任务 outcome/freshness/checkpoint age）。
2. **G4 门剩余**：大档 `--assert-slo` 接入发布门流水线/nightly；告警阈值与 runbook 联动（两周基线校准）。
3. **W5**：DBWriteQueue ADR（需 7 天指标）、PostgreSQL 计划重写、Tracker 指纹（数据支撑后）、文档/feature_list/roadmap 全量收口。
4. 上线前 Alembic 迁移（head f5e6d7c8b9a0）。

### 变更边界

- 本次改 backend app/services + lifecycle + config + 测试；未改 Schema（W4-1 无迁移）；未执行 Git stage/commit/push。

## 2026-08-09 交接：W3-4 实施完成（任务 outcome/skip/freshness 六态语义，W3 收官）

当前任务：修复计划 W3-4（P1-05）实施完成，后端/前端并行子代理执行 + 主代理逐项审查通过

分支：dev
状态：W3 全部完成（W3-1/W3-2/W3-3/W3-4）；G3 门剩余：真实 RSS 基准（需 psutil 环境）、大档 --assert-slo 接入发布门；未提交、未推送。

### 本次改动（后端 12 文件 + 前端 4 文件）

- **后端**：新迁移 `f5e6d7c8b9a0`（task_logs.outcome/skip_reason + cron_task 5 个 freshness 列，全部可空）；executor 六态落库（skipped 不丢弃/重入记录 [REENTRANT_SKIP]/[ADMISSION_SKIP] 保持）；last_success_at 仅 success/partial/no_action 推进；新 `cron_freshness.py`（APScheduler 解析 cron_plan，2 周期阈值 + `CRON_STALE_THRESHOLD_SECONDS=7200` 兜底）；API 增补 lastOutcome/freshnessSeconds/stale + logs outcome 过滤 + CSV 同步。
- **前端**：TaskOutcome 六态类型 + 映射工具（无 any）；任务列表 outcome tag + 数据陈旧告警；日志表/详情/复制六态（旧数据回退）；tasks-sync-freshness.spec.ts 18 用例 + api-contracts +2。
- 迁移防护期望更新（EXPECTED_HEAD/REV_HEAD=f5e6d7c8b9a0）。

### 验证（主代理亲自复跑）

- 后端全量 `pytest`：**3085 passed, 7 skipped, 0 failed**（200.9s）。
- 前端：test:unit 635 passed；typecheck 0 错误；build 成功；lint 0 errors。
- 注：子代理报告曾见 2 个 orphan_scanner 失败（其环境瞬时状态），主代理全量复跑未复现。

### 下一步

1. **G3 发布门**：真实 RSS 基准（psutil 环境）；大档 `--assert-slo` 接入发布门流水线/nightly。
2. **W4-1**：结构化日志收口（`_attach_done_stats` CancelledError 缺口修复、event loop lag 采样器、run_id 贯穿校验）。
3. **W4-2**：liveness/readiness/同步业务健康接口（Docker 健康检查从 /docs 改 /health/ready）。
4. **W5**：P2 决策与文档收口（DBWriteQueue ADR、PostgreSQL 计划重写、feature_list/roadmap 全量核对）。
5. 上线前 Alembic 迁移（head f5e6d7c8b9a0）。

### 变更边界

- 本次改 backend（迁移/executor/freshness/API/测试）+ frontend（tasks.ts/index.vue/测试）；未执行 Git stage/commit/push。

## 2026-08-09 交接：W3-3 实施完成（info-only 有界并发与分阶段流水线）

当前任务：修复计划 W3-3（P1-02/P1-04）实施完成，拆两部分由子代理执行 + 主代理逐项审查通过

分支：dev
状态：W3-3 代码与测试完成（G3 门剩余：W3-4 outcome/freshness、真实 RSS 基准）；未提交、未推送。

### 本次改动（backend 4 文件 + 2 测试文件）

- **W3-3a**：新配置 `INFO_SYNC_DOWNLOADER_CONCURRENCY=1`（SQLite 默认串行）/ `DB_READ_PAGE_SIZE=500` / `MAX_TORRENTS_PER_RUN=10000` / `RUN_BUDGET_SECONDS=300` / `MAX_BUFFERED_ROWS=2000`；`torrent_info_sync_task` max_concurrent 配置化；existing 记录分页读取 + 每页让行；预算（count|time）+ 缓冲上限 flush；phase_ms/rows_buffered 观测。
- **W3-3b**：新 `tests/integration/test_sync_memory_bound.py` 9 用例（fetch 不持写锁/write 无下载器调用、并发符合配置 4×10k、内存峰值有界、部分失败不阻塞、RID 确认仅 durable commit 后、增量异常回退受预算限制）——**生产代码零改动**（RID 顺序验证已正确）。

### 验证（主代理亲自复跑）

- 全量 `pytest`：**3061 passed, 7 skipped, 0 failed**（208.4s）。
- 新增：info_budget 8 + memory_bound 9；integration 22 passed + 1 skip；black/flake8 通过。

### 下一步

1. **W3-4**：outcome/skip/freshness 六态语义（task_logs 增补可空字段 run_id/outcome/skip_reason/rows_changed/phase_summary_json + API + 前端任务页）。
2. G3 发布门：真实 RSS 基准（需 psutil 环境）；大档 `--assert-slo` 接入发布门。
3. 上线前 Alembic 迁移（head f0e1d2c3b4a5）。
4. 工作区未提交内容较多（W4-3/W3-2/W3-1/W3-3 + 文档），建议 W3-4 完成后统一提交。

### 变更边界

- 本次改 backend app/（torrents_async.py、torrent_info_sync_task.py、config.py、.env.example）+ 2 测试文件；未改 Schema；未执行 Git stage/commit/push。

## 2026-08-09 交接：W3-1 实施完成（qB Tracker 有界队列 + 持久化 cursor 续跑）

当前任务：修复计划 W3-1（P1-01/P1-04）实施完成，拆分两部分由子代理执行 + 主代理逐项审查通过

分支：dev
状态：W3-1 代码与测试完成（G3 门剩余：W3-3 info 流水线、W3-4 outcome/freshness）；未提交、未推送。

### 本次改动（backend 4 文件 + 1 测试文件扩展）

- **W3-1a** `torrents_async.py::_enrich_qb_torrents_with_trackers` 重写：有界 Queue + worker 池（10k hash 活跃任务 ≤ worker+2，禁止全量 create_task）；新配置 `QB_TRACKER_WORKER_COUNT=2` / `MAX_TORRENTS_PER_RUN=1000` / `RUN_BUDGET_SECONDS=120` / `PER_CALL_TIMEOUT=30`；数量硬上限 + 时间软上限，`budget_reason` 观测。
- **W3-1b**：稳定排序 + cursor（JSON last_hash 存 checkpoint `cursor_value`）+ 仅 durable commit 后推进（批失败停驻，测试验证第 2 批失败 cursor=h000004）+ cycle 语义（last_full_sync_at + 清 cursor）+ `SyncRequest.deadline/record_budget` 透传（partial outcome）+ RID 确认点验证（已正确无需改）。
- 测试：`tests/api/test_torrents_async_tracker_budget.py` 12 项。

### 合并处理（并行会话）

- 外部会话 6 个提交（orphan API 升级 + 前端）已合并：orphan 测试 29 passed、迁移链 3a4b5c6d7e8f→f9a1b2c3d4e5→f0e1d2c3b4a5 完整、`REV_HEAD` 更新至 f0e1d2c3b4a5。
- 子代理模型连续 3 次故障（大文件读取超上下文）——拆分任务 + 限制 `torrents_async.py` 读取区间后成功（经验：3600 行大文件禁止子代理读全文）。

### 验证（主代理亲自复跑）

- 全量 `pytest`：**3044 passed, 7 skipped, 0 failed**（209.1s）。
- 相关：tracker_budget 12 / coordinator 20 / checkpoint 13 / governance 7；black/flake8 通过；mypy 未新增错误。

### 下一步

1. **W3-3**：info-only 有界下载器并发与分阶段流水线（SQLite 默认 downloader_concurrency=1）。
2. **W3-4**：outcome/skip/freshness 六态语义（task_logs 增补字段 + 前端任务页）。
3. 上线前 Alembic 迁移（head f0e1d2c3b4a5）。
4. 后续子代理任务如涉及大文件，先拆分并限制读取区间。

### 变更边界

- 本次改 backend app/（torrents_async.py、sync_coordinator.py、config.py、.env.example）+ 测试；未改 Schema；未执行 Git stage/commit/push。

## 2026-08-09 交接：异步操作条目占用完成

当前任务：解决前端刷新后可对同一数据重复提交异步操作的问题。

状态：实现和相关回归完成；未提交、未推送。

### 已完成

- 种子批量删除/重复种子快捷删除：进程内活动 ID 原子占用，普通列表、重复查询、快捷预览和高级搜索排除 pending/running；终态释放。
- 孤儿主动清理/隔离区彻底删除：基于 `orphan_purge_job` 的持久化条目占用，列表与操作入口排除活动项，混合提交跳过，全部占用不派发。
- 前端四条操作链提交即刷新；`task_id=null` 不轮询；混合提交提示跳过数。
- `feature_list.json` 新增 `v1.0.6.38` evidence，`docs/roadmap/` 已按 2026-08-09 源码实测行号更新。

### 验证与已知外部状态

- 相关后端 249 passed；前端定向 Jest/typecheck/改动文件 ESLint/build 通过；核心服务 mypy 与后端改动文件 flake8 通过。
- 完整后端套件的本次相关测试均通过；当前无关 `test_sqlite_worker_guard.py` 因 subprocess mock 的 `stdout=None` 失败。完整前端 lint 被无关关键词测试文件 5 条既有 warning 拦截。
- 工作区同时存在未提交的同步治理/checkpoint/benchmark 改动及构建产物，本任务未覆盖或清理这些文件。

### 后续建议

1. 如需跨后端进程重启保留种子删除占用，可将当前进程内 `DeletionTaskManager` 迁移为持久化任务表；当前需求仅针对前端刷新，已满足。
2. 提交前按业务范围分组审查 dirty worktree，避免把并行同步治理改动与本功能误混在同一提交。

## 2026-08-09 交接：W3-2 实施完成（持久化同步检查点）

当前任务：修复计划 W3-2（P1-03）实施完成，1 个子代理执行 + 主代理逐项审查通过

分支：dev
状态：W3-2 代码与测试完成（G3 门剩余：W3-1 有界队列/预算、W3-3 流水线、W3-4 outcome/freshness）；未提交、未推送。

### 本次改动（backend 新增 4 文件 + 扩展 5 文件）

- **新 `app/models/sync_checkpoint.py`**：sync_checkpoints 表（13 列按计划 Schema，唯一约束 downloader_id+sync_type，version 乐观锁，detail_json 白名单清洗防敏感数据，outcome 六态）。
- **新 Alembic 迁移 `3a4b5c6d7e8f_add_sync_checkpoints.py`**（down=d8e9f0a1b2c3，往返完整）；alembic/env.py 注册；test_db_migration / test_db_rollback_scenarios 的 head 期望更新。
- **sync_coordinator.py 集成**：SyncCheckpointStore（独立短事务 + 乐观锁单调合并）；run_sync 初始化/推进/终态/取消；cursor 不超前于数据；push_sync_progress 预留 W3-1；SyncResult.checkpoint 实际值。
- **测试**：test_sync_checkpoint_migration（2）+ test_sync_checkpoint（13）+ conftest 隔离 fixture。
- **主代理修复**：test_db_rollback_scenarios REV_HEAD 漏更新（子代理只更新了 test_db_migration）。

### 验证（主代理亲自复跑）

- 全量 `pytest`：**2980 passed, 2 failed**。
- ⚠️ **2 个失败（orphan cleanup）为工作区并行会话的外部改动所致**（orphan_files.py 等升级为 submit_cleanup_job API + 前端多处改动，测试仍 patch 旧 create_cleanup_job）——经 git stash 二分确认与 W3-2 无关，未代修；需外部会话同步其测试或协调处理。
- W3-2 相关全部通过：checkpoint 迁移 2 + checkpoint 13 + coordinator 20 + rollback 8 + migration 11；black/mypy/flake8 通过。

### 下一步

1. **W3-1**：qB Tracker 同步有界队列与单轮预算（worker 池/时间预算/游标推进——用 W3-2 的 push_sync_progress 与 cursor_value）。
2. **W3-3**：info-only 有界下载器并发与分阶段流水线（SQLite 默认 downloader_concurrency=1）。
3. **W3-4**：outcome/skip/freshness 六态语义（task_logs 增补字段 + 前端任务页）。
4. 上线前先执行 Alembic 迁移（dev app.db 仍停旧 head，运行时自动迁移会处理）。
5. 外部并行会话的 orphan API 改动需同步测试并提交。

### 变更边界

- 本次改 backend 模型/迁移/coordinator/测试；未改其他业务代码；未执行 Git stage/commit/push。

## 2026-08-09 交接：W4-3 实施完成（真实文件型 SQLite 争用基准与响应性验收）

当前任务：修复计划 W4-3（P1-07）实施完成，2 个子代理执行 + 主代理逐项审查通过

分支：dev
状态：W4-3 代码与测试完成（G4 门剩余：W4-1 结构化日志/lag 采样器、W4-2 健康接口）；未提交、未推送。

### 本次改动（backend 新增 3 文件 + 扩展 2 测试文件）

- **新 `scripts/sync_contention_benchmark.py`**（1506 行）：真实文件型 SQLite 争用基准——三档数据（large 22k torrents/30k trackers 生成 1.1s）、场景 A/B/C（真实 bulk_upsert_with_retry / 真实 sync_tracker_status_from_keywords 两遍验证零变化零 DML / 批量 UPDATE）、请求探针、fake 下载器经 call_downloader_api 真实调用、故障注入（busy/cancel/slow-downloader）、`--assert-slo` 发布门、JSON 对比输出（`benchmark_results/sync_contention_<ts>.json`，无敏感数据）。
- **新 `tests/integration/test_sync_api_responsiveness.py`**：4 用例（info 写期间只读 P95<1.5s 实测 30.6ms、tracker 更新期间写 P95<2.5s 实测 35.5ms、慢下载器事件循环心跳 P99<100ms 实测 16ms、连续 BUSY 无雪崩）。
- **扩展 `test_sqlite_sync_contention.py`**：4 故障注入用例（连续 BUSY 重试、300ms 持锁排队、慢下载器超时心跳、取消整批保留）。
- **新 `docs/operations/sync-contention-runbook.md`**：命令/三档/故障注入/验收矩阵/JSON 对比/CI 接入/校准系数方法。
- **测试基建修复**：`_find_git_bash` 补 E:/Git、D:/Git 常见安装位置；两个集成测试文件加 autouse patch（慢下载器用例不依赖可被 TestClient lifespan 关闭的全局 runtime 单例，改用 asyncio 默认 executor + wait_for 超时语义）。

### 验证（主代理亲自复跑）

- 全量 `pytest`：**2967 passed, 7 skipped, 0 failed**（248.1s）。
- 基准：small 档 `--assert-slo` 4/4 PASS、busy 故障注入 3/3 PASS；**大档 SLO 全 PASS（只读 P95=31.76ms/写 P95=33.32ms/超时 0/BUSY 0），无需校准系数**。
- black/flake8 通过；JSON/日志无敏感数据。

### 下一步

1. **W4-1**：阶段级结构化日志收口（`_attach_done_stats` 的 CancelledError 缺口修复、event loop lag 采样器、run_id 贯穿校验）——runbook 第 9 节已记录候选。
2. **W4-2**：liveness/readiness/同步业务健康接口（Docker 健康检查从 /docs 改 /health/ready）。
3. **G4 发布门**：大档 `--assert-slo` 接入发布门流水线/nightly；告警阈值与 runbook 联动。
4. 之后进入 W3（有界队列/checkpoint/outcome 六态）或按计划顺序（W3 在 W4 之前，但 W4-3 已先行完成——剩余 W4-1/W4-2 与 W3 无依赖，可并行）。

### 变更边界

- 本次改 backend/scripts、backend/docs/operations、backend/tests/integration（各 1 个新文件 + 1 个扩展）；未改 app/ 生产代码、未改 pytest.ini；未执行 Git stage/commit/push。

## 2026-08-08 交接：W2 分批实施完成（sync-database-blocking-remediation G2 代码完成）

当前任务：修复计划第二批 W2（P0 同步路径与请求响应性）实施完成，6 个子代理执行 + 主代理逐项审查通过

分支：dev
状态：W2 代码与测试完成（G2 门剩余：运行观测类验收——CRUD P95/P99 SLO、event loop lag，需发布观察/W4 基准数据）；未提交、未推送。

### 本次改动（backend app/ 16+ 文件 + tests/ 10+ 文件）

- **W2-1** 新 `app/services/sync_coordinator.py`（756 行）：SyncRequest/SyncResult + run_sync 阶段编排（准入→备份 hook→下载器解析→sync→tracker_status）；手动入口与定时任务统一走 Coordinator；`torrent_sync_db_async` 改 legacy adapter（`SYNC_CANONICAL_COORDINATOR_ENABLED` 开关回退）；旧全量内嵌 `_bulk_write_with_retry` 收编到统一写入器；文件备份段保留（"同步后置短事务"边界）。
- **W2-2** `downloader_api_runtime.py`：两级信号量（total=2 + background=1，TRACKER/SYNC 后台最多占 1 槽，INTERACTIVE 恒留 1 槽）；删除 priority 参数；queue_wait_ms/remote_call_ms 日志；矛盾组合自动降级。
- **W2-3** 5 个垂直切片（tracker 漏 await×4 修复 / crud+status / tag+downloader+settings / reannounce+recycle_bin+seed_transfer / deletion adapters→to_thread）；新 AST 架构测试 `tests/architecture/test_async_downloader_calls.py`（30 项）。
- **W2-4** 新 `app/core/startup_guard.py`：SQLite 多 Worker fail-fast（main.py 模块加载期 + btdeck_startup.sh shell 双接线 + scheduler 纵深防御），PostgreSQL 不误杀。
- **测试基建修复**：test_reannounce_service 加 autouse patch（TestClient lifespan 关闭全局 runtime 单例的污染，仓库既有约定同款）。

### 验证（主代理亲自复跑）

- 全量 `pytest`：**2959 passed, 7 skipped, 0 failed**（254.9s）。
- 新测试：sync_coordinator 20 / runtime 34 / worker_guard 53 / AST 架构 30 / 各切片 24+31+19+22。
- black/flake8 通过；mypy 关键模块无错误；tag_management/downloader_settings black 存量债务经 HEAD 验证为历史遗留。

### 下一步

1. **G2 发布观察**：一个完整 info/Tracker 周期 + 手动单下载器同步 + 高峰交互时段；核对 CRUD 只读 P95<1s / 写 P95<2s / 超时率<0.1% / event loop lag P99<100ms（代码层阻塞路径已清除，量化验收待运行数据）。
2. **W3（P1）**：有界队列与单轮预算（qB Tracker workers/预算）、持久化 checkpoint（Alembic 迁移 + sync_checkpoints 表）、info 有界流水线（SQLite 默认 downloader_concurrency=1）、outcome/freshness 六态语义（task_logs 增补字段）。
3. W3 有 Schema 变更：先执行 Alembic 再启用 checkpoint；验证历史 task_logs 兼容。
4. 发布门记录与 roadmap 更新（roadmap-maintain 规则实测行号）。

### 变更边界

- 本次改 backend app/ 与 tests/（清单见 feature_list.json sync-database-blocking-remediation-w2）；未改 Schema/迁移/运行配置（W2-4 仅加启动校验与注释）；未执行 Git stage/commit/push。

## 2026-08-08 交接：W1 分批实施完成（sync-database-blocking-remediation G1 代码完成）

当前任务：修复计划第一批 W1（P0 数据库事务修复）实施完成，4 个子代理执行 + 主代理逐项审查通过

分支：dev
状态：W1 代码与测试完成（G1 发布门剩余：发布观察 + 22k/30k 压测定批大小最终值）；未提交、未推送。

### 本次改动（backend app/ 5 文件 + tests/ 7 文件 + .env.example）

- **W1-1** `app/services/sync_db_write.py`：`bulk_upsert_with_retry` 真实分批提交（每批独立 commit，批间让行），`WriteStats` / `ChunkedWriteError`（部分进度 + 异常链），锁冲突按 SQLite 错误码分类（5/6/261/262/266/517），退避=指数+抖动且单批总睡眠 ≤ 2s；新配置 `SYNC_CHUNKED_COMMIT_ENABLED` / `SYNC_DB_LOCK_RETRY_COUNT=3` / `SYNC_DB_RETRY_MAX_BACKOFF_SECONDS=2.0`。
- **W1-2** 新 `app/services/tracker_status_sync.py`：判定规则逐行保持的增量写（变化检测，零变化零 DML 不 commit）；`torrent_sync.py::update_tracker_status_from_keywords` 改兼容包装（调用方零改动）；新配置 `SYNC_TRACKER_STATUS_INCREMENTAL_ENABLED`。注意：重复关键词实际保留"先读取的"值（与原注释不符，按规则保持未改）。
- **W1-3** `torrents_async.py::_mark_qb_removed_torrents`：事务外算 ID → 统一写入器更新（三列复合主键 info_id/downloader_id/downloader_name），空变更零 commit；架构测试追加同步模块 DML 准入断言。
- 新 `tests/integration/test_sqlite_sync_contention.py`：真实文件型 SQLite 争用回归（交互写穿插分批同步、真实 BUSY 错误码、短事务锁释放、零变化不持锁），22k 基准以 perf marker + skip 预留。

### 验证（主代理亲自复跑）

- 全量 `pytest`：**2699 passed, 7 skipped, 0 failed**。
- 新测试：test_sync_db_write 31 / test_tracker_status_sync 21 / test_qb_removed_mark_governance 9 / 争用回归 5+1skip / 架构约束 22。
- black（10 文件）通过；mypy sync_db_write + tracker_status_sync 无错误；flake8 通过；torrents_async mypy 15 错误为存量基线（stash 复测 HEAD 同数）。
- 4 个测试文件经 black 格式化后复跑 83 passed。

### 下一步

1. **G1 发布观察**：一个完整 info/Tracker 周期；22k/30k 真实压测确定 `SYNC_DB_COMMIT_BATCH_SIZE` 最终值（当前 200，压测数据决定 200~500）。
2. **W2（第二批 P0）**：统一 SyncCoordinator 收编手动同步与旧全量旁路写者（qb/tr_add_torrents_async、sync_add_tracker_async、mark_removed_trackers_*）；DownloaderApiRuntime 交互容量保留（background_capacity，SQLite 默认 1）；async 端点同步下载器调用迁移 + 漏 await 架构扫描；SQLite 多 Worker fail-fast。
3. 每个发布门记录测试命令/结果/性能报告路径；源码行号变化后按 roadmap-maintain 规则更新 docs/roadmap。
4. 回滚：`SYNC_CHUNKED_COMMIT_ENABLED=false` + `SYNC_TRACKER_STATUS_INCREMENTAL_ENABLED=false` 即回旧写回行为（开关最多保留两个稳定版本），无 Schema 变更。

### 变更边界

- 本次仅改 backend app/（sync_db_write.py、tracker_status_sync.py 新、torrents_async.py、torrent_sync.py、config.py）、tests/（7 文件）、.env.example、progress.md、session-handoff.md、feature_list.json；未改 Schema/迁移/运行配置。
- 未执行 Git stage/commit/push。

## 2026-08-08 交接：同步任务数据库阻塞详细修复计划

当前任务：根据数据库阻塞评估创建可执行修复计划

分支：dev
状态：计划文档完成；未实施业务修复，未提交、未推送。

### 产物

- [同步任务数据库阻塞与接口超时修复计划](PLANS/sync-database-blocking-remediation.md)
- [数据库阻塞与同步问题评估](backend/docs/operations/database-blocking-and-sync-issues-2026-08.md)

### 计划决策

- P0 分两批发布：G1 先缩短 SQLite 事务并消除无变化全表写；G2 再统一手动/定时同步路径、为交互请求保留下载器容量、清理 async 端点阻塞并强制 SQLite 单 Worker。
- P1 引入有界队列、运行预算、durable checkpoint、明确 outcome/freshness，并用真实文件型 SQLite DML 与并发 CRUD 验收。
- P2 不预设引入 DBWriteQueue 或切换 PostgreSQL；先收集至少 7 天指标并通过 ADR 决策。旧 v1.0.8 计划后续必须移除与 app.state.store 约束冲突的下载器连接池设想。
- 健康检查分为 liveness、readiness 和受保护的同步业务健康；高频 readiness 只做有超时的只读检查，不用写探针制造额外锁。

### 下一步

1. 实施 W0 基线与止血手册。
2. 创建 W1 实施任务，优先修改 sync_db_write、Tracker 状态更新和 qB removed 标记。
3. 使用真实临时 SQLite 文件执行最小争用回归，通过 G1 后独立发布观察。
4. 实施启动时在 feature_list.json 建立对应任务/evidence，并按源码变更更新 docs/roadmap。

### 变更边界

- 本次仅改动 PLANS/sync-database-blocking-remediation.md、PLANS/README.md、progress.md 和 session-handoff.md。
- 源评估与计划的 19 个风险编号逐项一致；计划链接检查、git diff --check 和 ./init.sh --ci 通过，前端 init 仅有既有 null-byte warning。
- 未修改业务源码、Schema、迁移或运行配置；未执行 Git stage、commit 或 push。

## 2026-08-08 交接：同步任务数据库阻塞与接口超时风险登记

当前任务：运行问题评估文档整理

分支：`dev`
状态：文档完成；未提交、未推送。

### 产物

- [数据库阻塞与同步问题评估](backend/docs/operations/database-blocking-and-sync-issues-2026-08.md)

### 核心结论

- 默认 Tracker/info 任务前后出现卡顿和接口超时与当前代码一致，问题应按 P0 生产可用性缺陷处理。
- 关键根因包括 Tracker 状态全表重写、info-only 单大事务、手动/旧版同步旁路、异步端点直接执行同步下载器 API、后台 Tracker 占满每下载器容量以及 SQLite 进程内锁无法覆盖多 Worker/旁路写者。
- 文档给出 P0/P1/P2 问题登记、无代码止损、分阶段修复、日志/指标/告警和真实文件型 SQLite 压测验收标准。

### 验证与边界

- 只读核对本地 `app.db` 和历史 `task_logs`；本地库约 2.2 万种子、3 万 Tracker，历史 Tracker 任务最长 1161 秒。
- 相关治理测试 75 项通过；测试和 benchmark 仍未证明真实磁盘/WAL/索引并发下的接口 SLO。
- 本次未修改业务源码、数据库或运行配置；未执行 Git stage、commit 或 push。工作区原有修改和未跟踪文件保持不动。

## 2026-08-08 交接：列表模式删除等级入口 Lucide 同步

当前任务: v1.0.6.37
分支: dev
状态: 实现完成并通过验证；未提交、未推送。

### 实现

- 列表模式 frontend/src/views/torrents/index.vue 的工具栏批量删除和每行删除两组菜单，四级入口统一使用 tag、trash-2、trash、alert-triangle 四个 LucideIcon。
- 保留原有删除命令、menu-icon 间距样式、等级 1 的 danger 标识及下拉交互。
- frontend/tests/unit/torrent-list-view-component.spec.ts 新增两组菜单的 Lucide SVG、name、样式类和危险等级回归；同步更新视图路线图与 feature_list.json。

### 验证

- 全量 npm run test:unit 通过；传统/列表目标套件 2 suites / 26 tests 通过；typecheck、改动文件 lint、Vuex action lint、生产 build 通过。
- 完整 npm run lint 只被其他测试文件已有 5 条 ESLint warning 拦截，本次改动文件无 warning；build 仅有既有 56 条 Sass/资源 warning。
- E:\Git\bin\bash.exe ./init.sh --ci 通过，前端 init 仅有既有 null-byte warning；git diff --check 通过。

### 交接边界

- 未执行 Git stage、commit 或 push。
- 工作区中既有 Docker 远端部署改动及未跟踪文件均保留，未纳入本次任务。

## 2026-08-08 交接：Docker 远端部署后端健康检查等待修复

**当前任务**: `v1.0.9.6`
**分支**: `dev`
**状态**: 实现完成并通过静态/配置验证；未提交、未推送、未实际部署。

### 根因与决策

- 远端后端启动时的孤儿文件隔离状态对账耗时约 162.6 秒，超过原 Compose 健康检查窗口，导致 `frontend` 的 `service_healthy` 依赖报错。
- 不移动或跳过对账逻辑，采用部署编排层等待：先启动 backend 并轮询健康状态，healthy 后再启动 frontend。
- 远端 Compose 文件包含 Unraid 下载目录挂载，未用本地 Compose 覆盖；helper 只上传并执行部署等待逻辑。

### 变更文件

- `build-and-export-images.bat`
- `.btdeck-remote-deploy.sh`
- `docker-compose.yml`
- `backend/Dockerfile`
- `feature_list.json`
- `progress.md`
- `session-handoff.md`

### 验证与后续

- `.btdeck-remote-deploy.sh` 通过 `sh -n`。
- `docker compose -f docker-compose.yml config --quiet` 通过。
- 根 `E:\Git\bin\bash.exe ./init.sh --ci` 通过；仅有既有前端 npm null-byte warning。
- Docker Desktop 本机引擎仍因 Windows 管道权限不可用，未本地构建；需要下一步重新运行 `build-and-export-images.bat` 做实际远端部署验证。


## 2026-08-03 交接：孤儿全选当前筛选、隔离区表头对齐、剪贴板回退与操作日志布局

**当前任务**: `v1.0.6.36`
**分支**: `dev`
**状态**: 实现、回归、静态检查和生产构建完成；已提交并合并推送。

### 本次修改

- 孤儿列表表头复选框改为独立选择模型（`select_all` + `excluded_orphan_ids` + 当前筛选快照），不再依赖被虚拟窗口截断的 Element selection 列；已选计数按服务端 `total` 计算，全选时显示“当前筛选全部”。
- 后端新增 `OrphanSelectionRequest` 与 `resolve_orphan_selection`，清理/忽视提交时按与列表完全一致的 `_build_orphan_conditions` 把筛选快照解析为稳定 ID 集；大批量 ID 按 500/批切块，清理预览截断为前 200 条明细并返回 `items_truncated`。
- 隔离区页签接入共享 `management-table` 表头类，与孤儿页签表头布局、颜色、间距及固定方式一致。
- 新增共享 `copyTextToClipboard`（优先 Clipboard API，非安全上下文/权限拒绝回退 textarea + `execCommand`），操作日志 JSON 复制与任务详情复制统一接入。
- 操作日志搜索栏与操作栏拆为独立响应式布局，查询/重置/操作逻辑不变；前端补 `torrent_name` 查询参数对齐后端已有模糊搜索。

### 验证

- 后端孤儿全套：229 passed / 1 skipped（含新增 select_all 快照解析用例）；变更文件 Flake8、`git diff --check` 通过。
- 前端全量 Jest：31 suites / 527 tests；typecheck、定向严格 ESLint、生产 build 通过；build 仅保留既有 warning。
- 全量 mypy 仍为孤儿历史 SQLAlchemy 模块既有 Column 类型债务，新增选择解析辅助代码无新增命中。

### 工作区边界

- 无 Schema、迁移或依赖变化；已提交并合并远程 `origin/dev`（并行会话 `5725797` 同主题实现，见下一条）。
- 会话开始前已有的未跟踪临时目录、数据库备份、调试脚本、镜像归档和工具文件均保持不动。

## 2026-08-03 交接：孤儿列表固定表头、忽视身份与大页性能修复

**当前任务**: `v1.0.6.35`
**分支**: `dev`
**状态**: 实现、回归、静态检查和生产构建完成；已随 `v1.0.6.36` 一并提交。

### 本次修改

- 忽视与清理候选定位统一使用 `canonical_path`，下载器 ID 仅作为可随成功扫描修正的归属元数据；保留 scan_id、candidate/stable 等安全门禁。
- 忽视失败会在后端记录原因计数、样例与异常堆栈，API 保留逐项 `failed_list`；页面会明确显示全失败或部分失败及具体原因。
- 孤儿表改用 Element Table 内部滚动和原生固定表头；1000 条大页通过定高可视窗口及上下占位行渲染，单批 API/自定义输入上限统一为 1000。

### 验证

- 后端孤儿全套：226 passed / 1 skipped；忽视/生命周期/API 定向：52 passed；Flake8 通过。
- 前端孤儿页面：24 tests；全量：30 suites / 516 tests；typecheck、定向 ESLint、生产 build 通过。
- `git diff --check` 与 Git Bash 根 `./init.sh --ci` 通过；build 仅保留既有警告，根验证保留 Windows/npm null-byte 环境 warning。全量 mypy 的 169 条报告为孤儿历史 SQLAlchemy Column 类型债务；Black CLI 在 Windows 上仍有完成后不退出的既有环境问题。

### 工作区边界

- 无 Schema、迁移或依赖变化；会话开始前已有的未跟踪临时目录、数据库备份、调试脚本、镜像归档和工具文件均保持不动。

## 2026-08-03 交接：孤儿文件列表表头与大分页批量操作修复（并行会话实现）

**当前任务**: `v1.0.6.35`（并行会话）
**分支**: `dev`
**状态**: 已由并行会话实现并推送到 `origin/dev`（`5725797`），合并时保留其隔离区 mtime/状态/置信度列等功能点。

### 本次修改（远程 `5725797`）

- `frontend/src/views/orphan-files/index.vue`：孤儿/隔离区统一八列结构；固定高度滚动容器与 sticky 表头；孤儿表使用首尾占位行的虚拟窗口；自维护选择状态保证大分页全选和批量忽视不依赖 Element UI 全量行渲染。
- `frontend/src/api/orphan-files.ts`、`backend/app/services/orphan_file_service.py`：隔离区列表补充 `mtime`，用于统一“修改时间”列。
- `backend/app/services/orphan_file_service.py`：`set_ignored` 的明细/候选查询和 flush 按 200 条分块，按明细 ID O(1) 映射候选。
- `backend/tests/services/test_orphan_ignore_and_filters.py`、`frontend/tests/unit/orphan-files.spec.ts`：新增 401 条大批量忽视、2000 条虚拟窗口/全选回归。

### 验证结果

- 后端：`tests/services/test_orphan_ignore_and_filters.py tests/api/test_orphan_files_api.py` 共 37 passed；Flake8 通过。
- 前端：孤儿页面 20 tests passed；全量 Jest 30 suites / 512 tests passed；`typecheck`、全量 Vue ESLint、Vuex action lint、`build` 通过。
- 已知环境阻断：`npm run lint` 的既有 advanced-search contract 漂移、Black Windows 进程超时、根 `./init.sh --ci` 的 WSL `E_ACCESSDENIED`。

## 2026-08-03 交接：种子实时进度与孤儿列表交互修复

**当前任务**: `v1.0.6.34`
**分支**: `dev`
**状态**: 实现与定向验证完成；未提交、未推送、未部署。

### 本次修改

- `torrent_batch_add_service.py` 生成的异步完成通知正文带失败文件/原因；通知抽屉详情渲染 `failed_list`，批量添加同步响应提示也保留具体原因。
- `torrent_speed.py` 在实时轮询后统一异步同步活跃/补查进度，使用下载器 ID + hash 复合键、变更检测、分批 commit 和 `db_write_scope`，避免同 hash 跨下载器串台。
- 孤儿文件 API/服务新增 `confidence` 筛选并将 high 排序在前；前端固定高度滚动列表触底懒加载，筛选/刷新从第一页替换数据。

### 验证

- 后端相关回归：81 passed（含架构门禁）。
- 前端全量 Jest：30 suites / 511 tests；`orphan-files.spec.ts`：19 tests；`typecheck`、直接 Vue ESLint、Vuex action lint 和生产构建均通过。
- 完整前端 lint 被既有 advanced-search 生成契约漂移拦截；Black 在当前 Windows Python 环境命令超时未退出；根 `./init.sh --ci` 受 Windows/WSL `E_ACCESSDENIED` 阻断。

### 工作区边界

- 未执行 Git stage、commit、push 或部署；会话开始前已有的未跟踪目录、备份、镜像归档与工具文件保持不动。

## 2026-08-02 交接：批量添加异步化、tr 路径映射排查与分时段限速修复

**当前任务**: `v1.0.6.33`
**分支**: `dev`
**状态**: 实现与定向验证完成；未提交、未推送、未部署。

### 关键结论

- 只读查询 `E:/Users/huangzj/Desktop/app.db` 的 `nickname=tr`：221 条映射中 182 条 `external` 为空，集中于 `/Downloads/bangumi`（181）和 `/Downloads/movie/`（1）；现有 13 条 `path_mapping_rules` 未覆盖这两个前缀。外部数据库未修改，实际目标路径需按容器挂载确认后在应用内补规则。
- `/torrents/add-batch` 现在不限制文件数量，流式暂存上传文件后返回 `202/task_id`；后台使用 `app.state.store` 缓存客户端处理，结束时创建通知中心 `system` 通知，包含总数、成功数、失败数和失败文件。
- 分时段限速现在严格过滤星期，停用调度会恢复全局基线，启动/缓存就绪后立即同步，调度任务配置 `max_instances=1/coalesce=True`；设置应用接口启用调度时按当前有效规则应用。

### 变更文件

- 后端：`backend/app/api/endpoints/torrent_crud.py`、`backend/app/services/torrent_batch_add_service.py`、`backend/app/services/speed_schedule_service.py`、`backend/app/api/endpoints/downloader_settings.py`、`backend/app/tasks/cron_executor.py`、`backend/app/downloader/initialization.py`、`backend/app/startup/lifecycle.py`。
- 前端：`frontend/src/views/torrents/components/TorrentAddDialog.vue`、`frontend/src/api/torrents.ts`、`frontend/src/api/notification.ts`、`frontend/src/utils/error-normalize.ts`（将 202 受理码纳入成功白名单）。
- 测试/记录：批量接口测试、限速测试、`feature_list.json`、`progress.md`、本文件。

### 验证

- 后端批量/限速/设置定向测试：36 passed；compileall 通过。前端 `error-normalize.spec.ts`：34 passed。
- 前端 `npm.cmd run typecheck`、`npm.cmd run lint`、`npm.cmd run build` 通过；build 仅有既有 Sass/Browserslist/资源体积 warning。
- 根 `bash ./init.sh --ci` 因当前 Windows/WSL `E_ACCESSDENIED` 无法执行；会话开始前已有未跟踪目录、备份、镜像归档和工具文件保持不动。

---

## 2026-08-02 交接：下载器设置四项运行时问题修复与回归加固

**当前任务**: `downloader-control-room-ui-redesign.3`
**分支**: `dev`
**状态**: 根因经子代理独立验证、修复和回归测试完成；本次提交并推送。

### 本次修改

- `DownloaderSettingsDialog.vue`：关闭详情异步回填期间的规则自动校验；编辑模式测试连接允许空密码，由后端读取已保存凭据；将详情规则传入路径映射子组件。
- `PathManagementTab.vue` / `PathMappingTab.vue`：补齐规则 prop 数据流，抽取最长前缀规则解析，空 `external` 自动生成后参与保存。
- `SpeedSettingsTab.vue`：补齐限速控件的 `min-width`/flex 收缩约束和窄视口单列布局。
- 新增连接 guard、路径规则纯函数及后端路径映射更新回归；扩展下载器 UI 契约测试。

### 验证

- 前端相关回归：3 suites / 37 tests passed。
- 后端相关回归：58 passed。
- `npm.cmd run typecheck`、`npm.cmd run lint`、`npm.cmd run build` 通过。
- `git diff --check` 通过；构建仅保留仓库既有 Sass/Browserslist/资源体积 warning。

### 当前工作区边界

- 仅提交本次下载器设置修复、回归测试和项目记录；会话开始前已有的未跟踪临时目录、数据库备份、镜像归档、调试脚本和工具目录保持不动。

## 2026-08-02 交接：下载器管理页顶部裁剪与页签左对齐修正

**当前任务**: `downloader-control-room-ui-redesign` 后续 UI 修正
**分支**: dev
**状态**: 已完成 Chrome 实测定位、表单左对齐修正与前端回归，并已提交（`fix(frontend): fit downloader tab forms`）。

### 本次修改

- `frontend/src/views/downloader/index.vue`：移除顶部“节点控制台” hero、简介和指标区，页面从“状态链路已建立”工具栏开始；保留节点筛选、列表、卡片操作和响应式样式。
- `frontend/src/views/downloader/components/DownloaderSettingsDialog.vue`：为下载器设置/新增共用卡片移除旧的水平页签规则，建立固定左侧导航、可收缩内容区、明确的左对齐和最小宽度盒模型。
- `DownloaderSettingsDialog.vue` / `SpeedSettingsTab.vue`：Chrome 实测发现固定 `label-width=140px` 会把窄认证卡片的输入区压缩至约 55px；改为顶部左对齐标签、控件满宽和内容区零左边距，新增与编辑共用生效。
- `SpeedSettingsTab.vue`、`PathManagementTab.vue`、`PathMappingTab.vue`、`DownloaderPathManagement.vue`、`TagManagementTab.vue`：统一根容器宽度约束与左对齐；路径映射移除重复内边距，路径子页签改为左起布局。
- `frontend/tests/unit/downloader-control-room-ui.spec.ts`：增加顶部裁剪、设置/新增共用页签弹性布局和路径页签左对齐契约。

### 验证

- 定向 UI 契约：22 passed。
- 前端全量 Jest：29 suites / 498 tests passed。
- `npm.cmd run typecheck`、`npm.cmd run lint`、`npm.cmd run build` 均通过。
- 使用 `E:\\Git\\bin\\bash.exe ./init.sh --ci`：全栈环境验证通过；前端子脚本保留当前 Windows/npm 的 null-byte warning，后端虚拟环境未激活为提示。

### 当前工作区边界

- 本次提交仅包含上述相关的已跟踪文件；会话开始前已有的大量未跟踪临时目录、数据库备份、镜像归档和调试脚本保持不动，不执行 push 或部署。
- 会话开始前已有的大量未跟踪临时目录、数据库备份、镜像归档和调试脚本未触碰。

---

## 2026-08-02 交接：下载器控制室 UI 重绘与导航 Lucide 化

**当前任务**: `downloader-control-room-ui-redesign`
**分支**: dev
**状态**: 实现、全量回归、生产构建、真实浏览器桌面/移动端验收和项目记录均已完成；尚未提交。

### 本次交付

- `views/downloader/index.vue` 与 `DownloaderCard.vue` 已改造成高密度节点控制室和遥测卡片矩阵，所有原管理动作保持可用。
- `DownloaderSettingsDialog.vue` 已成为新增/编辑共用的顶层全屏配置工作区；速度、路径、标签与模板子页使用同一信息架构。新增模式只允许完成基础连接配置，依赖已有节点的页签明确锁定。
- 设置工作区必须保留 `append-to-body`：这是防止布局堆叠上下文导致 `v-modal` 覆盖弹窗的必要修复。
- 路由侧栏、Navbar、ThemeSwitcher、NotificationDrawer 和下载器页面的应用图标已统一到共享 `LucideIcon`；新增注册图标由 `LucideIcon.spec.ts` 覆盖。
- 新增 `frontend/tests/unit/downloader-control-room-ui.spec.ts`，锁定页面骨架、原业务方法、新增模式页签约束，以及无内联 SVG、Element icon 属性和表情符号的模板契约。

### 验证与边界

- typecheck、严格 lint、定向 110 tests、全量 29 suites / 498 tests、生产 build 均通过；build 仅保留仓库既有 48 条 warning。
- Git Bash 根 `./init.sh` 退出 0；前端 init 子脚本仅有当前 Windows/npm 环境的 null-byte warning。
- 浏览器验收覆盖 1280x720 与 390x844；管理页、新增页、编辑速度/路径/标签页无页面级横向溢出，弹窗层级与点击命中正常。
- 浏览器验收使用的临时免登录入口、401 跳转保护和三节点样例数据均已删除；源码中不存在 `visualQa`/`loadVisualQaFixture` 残留。
- 未修改 API、后端、数据库 Schema、Alembic 或依赖；未执行 Git stage / commit / push / 部署。
- 会话开始前已有的 `.docker_temp_482561487`、`.pnpm-store/`、`.spec-workflow/`、`.zcode/`、数据库备份、调试脚本、镜像归档、批处理和 `tools/` 均保持不动。

---

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

---

## 2026-08-05 交接：孤儿文件筛选交互优化与通知大小格式化

三项用户诉求已完成（经 3 轮子代理独立审查修订）：

1. **去除最小大小筛选**：删除 `orphan-files/index.vue` 的 min_size 共6处；删除 `api/orphan-files.ts` 死类型字段。后端 `min_size` 保留兼容（记 backlog）。
2. **通知释放空间自适应单位**：新建公共 `backend/app/utils/format_size.py`（2位小数 + B/KB/MB/GB/TB/PB 自动选单位）；`orphan_notification._format_size` 与 `orphan_purge_job_service` 释放空间行复用。验证：57286409241 → 53.35 GB ✅。
3. **筛选下拉换 AdvancedMultiSelect（多选）**：后端 `_build_orphan_conditions` 对 downloader_id/confidence 支持 `in_`；**status 因三态互斥保持单选**（避免 or_ 退化为恒真）；前端 downloader_id/confidence 换 AdvancedMultiSelect，修复空数组提交判断 bug，status 保持 el-select。

### 关键决策

- **status 多选陷阱**：审查发现 pending/ignored/deleted 互斥，同时多选会让 `or_()` 退化为恒真。用户授权"用最佳判断处理"，故 status 保持单选。
- **format_size 抽公共 utils** 而非跨服务依赖私有下划线函数。

### 验证

- 前端：56 passed；build/lint 通过；vue-tsc 2735 ≤ 基线 2736（未引入新错误）。
- 后端：181 passed；black/flake8 通过；mypy 仅修 1 个自引入错误。
- 未执行 Git stage/commit/push/deploy。

### backlog

- `orphan_purge_job.py:42 total_size: Integer` → 应改 BigInteger（已存在隐患）。
- 后端 `min_size` 死参数长期清理。
- `docs/roadmap/backend/services/orphan_file_service.md` 已更新本次触及符号行号，但存在历史漂移（非本次引入）。

## 2026-08-08 - Transmission 等级2删除超时修复

- 用户已确认问题为后端 `AsyncDeletionExecutor` 单种子 30 秒超时，目标为 Transmission 且任务存在。
- 已移除 `TransmissionDeleteAdapter` 删除流程前的全量 `get_torrents()` 预查询，改为直接按本地已确认的稳定 hash 调用 `remove_torrent()`。
- 保留目标任务 `get_torrent_info()`，继续提供安全告警；未改变删除文件选项。
- 新增回归测试 `backend/tests/services/test_transmission_delete_adapter.py`；相关 35 项 pytest 全部通过，目标 flake8/新增测试 black check 通过。
- 后续若仍超时，应分别测量目标 `get_torrent()` 与 `remove_torrent()` 的耗时；当前 `remove_torrent()` 仍是同步 SDK 调用，尚未在本次范围内改造为统一 runtime/to_thread。
- 未执行 Git stage/commit/push/deploy；全栈 `init.sh` 仍受当前 Windows/WSL `E_ACCESSDENIED` 环境限制。

## 2026-08-18 交接：W9 强制改密路由死锁（根因定位 → 回归重现 → 完整修复）

### 当前结果

- **根因四层**（两端回归测试实证）：init_db 启动自检置位默认口令标志（database.py:185-192，保留不动）→ 标志仅随登录响应下发、7 天 refresh token 窗口掩盖 → 守卫重定向/白名单写父路径 /settings 而真实改密页在 /settings/index（落点内容区 <!----> 白屏、真实路径与菜单均被弹回 = 死锁）→ 守卫 GetUserInfo 分支首导航放行缺口（双代理审查发现）。
- **修复 6+1 处**：router.ts /settings 加 redirect:'/settings/index'；permission.ts 守卫目标/白名单改子路由 + GetUserInfo 分支补拦截（抽 isForceChangeBlocked/forceChangeRedirect）+ 拦截弹 Message.warning"请先修改密码：完成修改前仅可访问系统设置页"（3 秒节流——拦截重定向回同一路径时设置页不重新挂载，点其它菜单被弹回原本无任何反馈；设置页 mounted 旧提示移除避免双弹）；cuser.py /user/info 下发 mustChangePassword（双前缀）；users.ts UserInfoData 类型；user.ts GetUserInfo 同步（undefined 不写防滚动部署误清）；settings/index.vue 改密成功清 forceChange query。
- **发布约束**：router redirect 与守卫白名单必须原子交付（单发前者 → /settings ↔ /settings/index 无限重定向循环，vue-router 3 无环检测已实证）。
- **生产解困 runbook** 在 PLANS/force-change-deadlock-fix.md 第四节（含 SQL 路径、会话残留必须重登、SQLite 先停后写、bcrypt 哈希生成命令）。

### 验证

- 后端：test_login_throttle_and_change_password（12，含 /users/info 两态新用例）+ test_w9_force_change_reproduction（4）+ test_auth_protection_extended 共 97 passed；black/flake8 通过；mypy 44 errors 为既有基线（stash 对比零新增）。
- 前端：permission-force-change-deadlock.spec 6/6（拦截落点可达/首导航拦截/父 redirect/直达放行/改密闭环/对照）；user-store-must-change-password.spec 7/7（GetUserInfo 三态）；permission-guard/store-user/api-contracts/request-auth 回归 60 passed；改动文件 eslint 通过；npm run typecheck 通过。
- 文档：PLANS/force-change-deadlock-fix.md 新建并在 PLANS/README 注册；progress.md/feature_list.json（force-change-deadlock-fix-2026-08-18，2 tasks）已更新；roadmap 同步（entry README 路由表行号实测重测+permission 小节补拦截描述、frontend README 行数、backend api README cuser 行、test-coverage 补登与扩展、根 README 元信息）；./init.sh 通过。

### 回归保护矩阵（本事故全部修改点，2026-08-18 补齐）

- deadlock spec 8 用例：router redirect、守卫目标/白名单、首导航拦截、提示+节流；user-store spec 9 用例：Login/GetUserInfo 全解析分支；settings-change-password spec 4 用例：改密成功双解锁（组件级，含 API btoa 契约）；后端 /users/info 两态 + init_db 置位 4 用例。相关 7 套件 80 用例全绿。

### 测试技术备忘（后续写路由测试会用到）

- jest.mock 工厂必须 `__esModule: true` + default 组件对象，否则 ts-jest interop 把包裹对象当组件 → 渲染空占位。
- router 是模块级单例且 push 修补吞 NavigationDuplicated：每个重定向用例须从与目标 fullPath 互异的当前路由出发（spec 的 startFrom helper），否则守卫不执行、断言空转。
- `/torrents/index` 路由挂的真实组件是 TorrentViewSwitcher.vue（非 torrents/index.vue，后者不在该路由上）。
- mock 懒加载视图时 target 文件须与 router.ts import 路径完全一致，放行导航会真实解析组件。

### 后续与边界

- 未执行 Git 提交（用户未要求）；如提交建议：fix(frontend)+fix(backend) 或合并 fix，router.ts 与 permission.ts 必须同一提交。
- 遗留：长会话不刷新标签页无法实时感知标志（GetUserInfo 唯一调用点是守卫 roles=[] 分支，彻底消除需挂周期端点）；其他父路由（/downloader、/tasks 等）缺 redirect 的手输空白 UX 问题待统一补。
- 部署后被困用户自动解锁路径：登录 → 落 /settings/index?forceChange=1 真实改密页 → 改密即清两端标志。


## 2026-08-22 交接：docs/roadmap 全量对账刷新（B 档）

### 结论

roadmap 与代码的漂移已全量修复：26 个文件中 23 个存在漂移的均已按"行号实测"原则重校（基准 HEAD 348c700），变更范围恰为 docs/roadmap/ 下 26 个文件，未触碰任何源码。根 README 元信息已补记 2026-08-22 增量（含此前遗漏的 04c8ec6 mypy/ORM Mapped 批次）。

### 漂移三大根因（已全部消解）

1. 04c8ec6（mypy 清零/ORM Mapped 迁移，143 个后端文件）在 e6c5036 最后同步之后落地——行号 +1~+26 漂移。
2. 更早落地但从未同步的行为变更——批种添加 202 后台化（torrent_batch_add_service）、孤儿副本数快照列（_enrich_items）、SDK 直调改 call_downloader_api。
3. 汇总计数长期失更 + 文档内部自相矛盾（endpoints 37/38、api 模块 12/13、tests/README 49/48 等）。

### 关键实测基准（后续会话可直接引用）

- endpoints 37；frontend api 模块 12；store 4 个 getModule + downloaderSettings 传统 namespaced
- alembic 28 个 revision，head `975dad435c03`（链尾 …→ ff42d3402df5 → ab68fe061d5b → 975dad435c03）
- 后端 test_*.py 180 个；前端 spec 59 个（tests/unit 48 + 内嵌 11）；torrents __tests__ 7 spec 共 2637 行
- AuditOperationType 47 个成员（AST 实测，非早前估算的 41）
- 第三层基准：torrent_crud.py 727 行、orphan_file_service.py 3902 行

### 未竟事项

- Git 未提交（等用户指令；提交建议 `docs: roadmap 全量对账刷新——计数重校 + 29 项补录 + 第三层行为描述重写`）。
- 后续源码变更仍需按 roadmap-maintain 技能增量同步；本次刷新后任何大重构（如再遇全库迁移类提交）建议再次全量对账。

## 2026-08-22 交接：Docker 后端 Python 3.11 f-string 启动修复

### 当前结果

- 修复 backend/app/tasks/cleanup_executor.py:272 的 Python 3.11 不兼容 f-string 引号嵌套；仅将表达式内双引号空字符串改为单引号，清理逻辑不变。
- 已使用修复后的源码构建 btdeck-backend:latest，镜像 digest：sha256:c0074bf5c36b78506f7a79fceee5d49f731646cb0f67625d2943659a4b134560。
- Python 3.11.15 镜像 import app.main、目标文件编译均通过；真实容器启动后 healthy，GET /health/ready 返回 200。

### 验证

- test_orphan_scan_task.py：18 passed。
- 调度器回归（test_cron_executor.py、test_cron_executor_admission.py、test_cron_executor_security.py）：38 passed。
- backend/app 全量 compileall、git diff --check、docker compose config --quiet 通过。
- 根 bash ./init.sh --ci 受当前 Windows WSL E_ACCESSDENIED 阻断。

### 后续

- 未提交 Git；部署时使用当前 btdeck-backend:latest 导出/加载并重启后端即可。
- docs/roadmap/ 未改：本次未改变模块职责、文件路径或路线图行号。
