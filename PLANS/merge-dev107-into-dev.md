# 计划：dev1.0.7 → dev 合并（含 Alembic 迁移链重挂）

> **任务**: 将 `origin/dev1.0.7`（MCP 服务 + MoviePilot 集成线）合并入 `dev`（桌面双语完成线）
> **类型**: Git 语义合并 + 迁移链修复 + 门禁适配
> **状态**: 待执行（已获准策略，本文为详细执行计划）
> **制定**: 2026-09-22
> **合并基**: `b067ba5`（fix: chaquopy pyc 三开关钉死）
> **两侧尖端**: dev=`9318adf` / dev1.0.7=`53119be`

---

## 1. 背景与分叉本质

| 维度 | dev（ours） | dev1.0.7（theirs） |
|---|---|---|
| 主线工作 | 桌面双语 **P1→P6-5 全量完成**（P7 收口准备就绪）+ v1.0.6 发布收尾 + 动态 head 测试方案（`tests/core/alembic_head.py`） | **MCP 服务 W0→W4-d 全量** + **MoviePilot 整理联动** + 双语仅 P0/P1（旧键结构） |
| Alembic 链尾 | `c1d2e3f4a5b6 → b3e5f7a9c1d2(search_templates.preset_key) → d1e2f3a4b5c6(setting_templates.preset_key)` HEAD | `c1d2e3f4a5b6 → 053003337878(moviepilot 两表)` HEAD |
| i18n 键结构 | `navigation.navbar.*`（P6 后结构，键包 339/65/66 行） | `navbar.*`（P1 期结构，键包 226/33/34 行） |
| settings 页 | 含「主机能力」页签（已全量 i18n 化） | **移除主机能力页签**（282f494）+ 新增 MCP/MoviePilot 页签（中文硬编码） |

**同一工作双线演进**（非 cherry-pick，patch-id 不同）：
- 双语 P1 在两分支独立提交（dev=`f7f1b81` / dev1.0.7=`788d657`），dev 侧继续演进至 P6-5；
- head 漂移测试债两侧各自修复（dev=集中式 helper / dev1.0.7=各文件局部 `_current_head()`）；
- PLANS 归档（dev1.0.7=`b86c57f` 归档 14 份）与双语计划文档两侧各自维护。

**试合并结果**：37 个冲突文件（merge-tree `a4dddb1` 实测；详见 §3 分类清单，已对账无遗漏）。

> **独立审查**: 本计划已经 reviewer 子代理独立核验（2026-09-22，8 项事实断言 F1~F8 + 全树冲突对账），
> 审查发现的 2 处门禁缺口、1 处计数错误、2 处测试必改点已全部吸收进正文（标 🔧 处）。
> 核验结论摘要见附录 A。

---

## 2. 总体策略（四条原则）

1. **i18n 取 dev 完成态**：双语相关文件一律取 dev 侧（P6-5 完成结构），dev1.0.7 的 P1 期版本弃用；
2. **删除决定取 dev1.0.7**：主机能力面板按 282f494 的刻意移除执行（组件+spec+页签+引用全清）；
3. **功能语义两侧并集**：torrent_add_service（dev 错误契约 + dev1.0.7 MCP 字段）、迁移链（dev preset_key + dev1.0.7 moviepilot）等逐文件手工合并；
4. **MCP/MoviePilot 双语化不在本次范围**：新功能面暂入 i18n 审计门禁排除清单（照「移动端保持中文，另立项」先例），双语化另立项。

---

## 3. 冲突解决清单（37 文件，按策略分四类）

### 类 A：取 dev 侧（i18n 完成态）——13 个

| 文件 | 说明 |
|---|---|
| `frontend/src/i18n/index.ts` | 339 行完成态 vs 226 行 P1 期 |
| `frontend/src/i18n/locales/en/index.ts` | 65 vs 33 行 |
| `frontend/src/i18n/locales/zh-CN/index.ts` | 66 vs 34 行 |
| `frontend/src/i18n/locales/en/navigation.ts` | dev 多 `sidebar.*` 键（P1 壳层补译） |
| `frontend/src/i18n/locales/zh-CN/navigation.ts` | 同上 |
| `frontend/src/layout/components/Navbar/index.vue` | dev 用 `navigation.navbar.*` 新键 |
| `frontend/src/permission.ts` | dev 引入 `translate`（动态标题双语） |
| `frontend/src/utils/formatters.ts` | dev 含 HTTP 兜底文案 i18n 化（64 差异行） |
| `frontend/src/views/login/index.vue` | dev 含语言胶囊与顶栏重构（169 差异行） |
| `frontend/tests/unit/navbar-language-switcher.spec.ts` | add/add 冲突，取 dev（新键结构） |
| `frontend/tests/unit/shared-utils.spec.ts` | dev 断言 `nameKey`/主题键（P6-5 契约） |
| `PLANS/desktop-bilingual.md` | dev 版记录到 P6-5（228 行）vs dev1.0.7 版（221 行，仅 P0/P1） |
| `PLANS/bilingual/error-contract.md` | dev 版 67 行（含 E13~E17 扩展）vs 53 行 |

### 类 B：按 dev1.0.7 删除决定执行——2 个

| 文件 | 动作 |
|---|---|
| `frontend/src/components/settings/PlatformCapabilityPanel.vue` | **删除**（dev 侧的 i18n 改造 13a1ee2 随之丢弃；键可达性门禁为「代码→语言包」方向，删除组件不产生悬空引用，语言包残留键不违门禁，后续清扫批再清） |
| `frontend/tests/unit/platform-capability-panel.spec.ts` | **删除**（modify/delete 冲突，dev 侧 i18n 修改丢弃） |

### 类 C：手工语义合并——核心 7 个

| 文件 | 合并方案 |
|---|---|
| `frontend/src/views/settings/index.vue`（221 差异行） | 以 dev 全量 i18n 版为基底：① 摘除主机能力页签（template `el-tab-pane` + import + components 注册）；② 增补 dev1.0.7 的 MCP 服务/MoviePilot 页签（含 Demo 模式渲染逻辑 282f494、`McpSettingsPanel`/`MoviePilotPanel` import 与注册）；③ 页签 label 沿用 dev1.0.7 中文硬编码（**ALLOWLIST 行级登记**，见 P4.2；**禁整文件排除**——设置页其余部分是 dev P6 双语成果，必须在审计覆盖内） |
| `backend/app/services/torrent_add_service.py`（50 差异行） | ① import 取 dev1.0.7 新位置 `app.services.torrent_add_helpers`（分层债收尾产物，新模块随合并干净并入）；② dev 的 `reason_code` 字段 + 全部失败路径赋值 + 固定 msg（`添加种子失败，请稍后重试`，动态 `str(e)` 只进日志）**保留**；③ dev1.0.7 的 MCP 领域字段（`info_hash/info_id/name/downloader_nickname/created`）+ `db_torrent_created` 追踪 + 末尾领域事实回填**并入**；④ 🔧 保留 dev 现行形态 `except Exception:` + `logging.exception(...)`（**不恢复 `as e`**——dev 已移除该用法，恢复会触发 flake8 F841 且 F841 已进门禁） |
| `backend/tests/core/test_db_migration.py` | 以 dev 版为基底：① 🔧 `EXPECTED_HEAD` **显式改值**为 `"053003337878"`（dev 版有专职门禁 `test_pinned_expected_head_matches_chain` 断言 `EXPECTED_HEAD == current_head()`，且注释明言「本仓唯一 head 写死点」——重挂后必须改值，不能去钉死化）；② 🔧 表计数断言 `test_empty_db_upgrade_head_builds_full_schema` 33 → **35**（moviepilot 两表并入），docstring「26 张业务表」一并更正；③ 链注释补 `053003337878(moviepilot integration tables)`；④ 并入 dev1.0.7 的 moviepilot 迁移幂等守卫用例 |
| `backend/tests/core/test_db_rollback_scenarios.py` | dev 版为基底（`REV_HEAD = current_head()` 集中式方案）；**注意语义差异**：dev1.0.7 版把 `REV_HEAD` 重定义为「旧代码环境模拟钉住版本」（刻意钉死 c1d2e3f4a5b6，真实 head 走 `_current_head()`）——逐用例核对 dev 版对 `REV_HEAD` 的使用是 mock 身份还是升级目标，mock 身份语义处保留 dev 动态方案是否等价，不等价处参照 dev1.0.7 语义调整 |
| `backend/tests/core/test_orphan_migration_production_shape.py` | dev 版为基底（`EXPECTED_HEAD = current_head()`）；dev1.0.7 的局部 `_current_head()` 弃用（统一走 `tests/core/alembic_head.py`） |
| `backend/tests/core/test_orphan_schema_repair_migration.py` | dev 版为基底：**必须保留** dev 的 search_templates/setting_templates fixture 建表（合并链的 preset_key 迁移会向两表加列，缺表 upgrade 即 NoSuchTableError）；局部 `_current_head()` 统一为集中式 helper |
| `.gitignore` | 并集：dev 的部署凭据/构建脚本/`deploy/docker`/`deploy/iscc`/迁移包忽略 + dev1.0.7 的 `/data/` 运行时数据忽略（顺带覆盖当前工作区未跟踪的 `data/` 目录） |

### 类 D：并集/追加型文档——15 个

| 文件组 | 处理 |
|---|---|
| `feature_list.json` | 两侧任务条目并集；dev 的双语任务（终态）+ dev1.0.7 的 MCP/MoviePilot 任务（终态）全保留；新增本次合并任务条目（evidence 指向合并提交） |
| `progress.md` | 两侧会话记录并集（按日期序交错保留），追加本次合并会话记录 |
| `session-handoff.md` | 两侧交接条目并集，追加本次合并交接段 |
| `PLANS/README.md`（80 差异行） | 手工合并：dev 的活跃计划（desktop-bilingual 线）+ dev1.0.7 的归档索引与 mcp/moviepilot 新计划条目 |
| `PLANS/bilingual/copy-catalog.json` | 取 dev 版（28689 行，与 dev 执行线一致；dev1.0.7 版 29554 行是其独立 P0 快照，弃用） |
| `docs/roadmap/README.md`（24）| 手工行级合并：dev 的 i18n 功能域行 + dev1.0.7 的 MCP/MoviePilot 行、生成日期取合并日 |
| `docs/roadmap/backend/api/README.md`（38） | 同上（mcp_settings/moviepilot 两端点行并入） |
| `docs/roadmap/backend/api/endpoints/torrent_crud.md`（176） | 行号两侧各自实测过 → 合并后源码行号再次漂移：先取 dev 版结构 + dev1.0.7 的 MCP 注记，**随后按 §6-P6 重实测** |
| `docs/roadmap/backend/data-models/README.md`（8） | 并入 moviepilot 两表行 |
| `docs/roadmap/backend/services/README.md`（13） | 并入 MCP 服务/moviepilot 集成服务/torrent_add_helpers 行 |
| `docs/roadmap/frontend/api/README.md`（8） | 并入 mcp-settings.ts/moviepilot.ts 行 |
| `docs/roadmap/frontend/components-layout/README.md`（51） | dev 侧删除 PlatformCapabilityPanel 行（对应类 B）+ 并入 MCP/MoviePilot 面板行 |
| `docs/roadmap/frontend/entry/README.md`（2） | 小差异，取合并后实测 |
| `docs/roadmap/frontend/utils-types/README.md`（22） | 行级并集 |
| `docs/roadmap/frontend/views/README.md`（134） | 同 torrent_crud.md 处理（先结构合并，后重实测） |

### 类 E：随合并干净并入（无冲突，验收时确认）——代表文件

- 后端：`app/api/endpoints/mcp_settings.py`、`app/api/endpoints/moviepilot.py`、`app/services/torrent_add_helpers.py`、`app/services/moviepilot_*`、`alembic/versions/053003337878_*.py`、MCP W0~W4 全线模块、`tests/api/test_mcp_*`/`test_moviepilot*`、`scripts/mcp_local_verify.py`
- 前端：`views/settings/components/McpSettingsPanel.vue`（39 行中文）、`MoviePilotPanel.vue`（102 行中文）、`api/mcp-settings.ts`、`api/moviepilot.ts`、种子详情「媒体库」页签（9442d5c）
- PLANS：`mcp-service-capabilities.md`（更新）、`moviepilot-integration.md`（新）、14 份归档 `PLANS/archive/*`
- 测试：`navbar-language-switcher.spec.ts` 之外的 5 用例修复（4b2d66a，media 页签断言 + CRLF 归一化）

---

## 4. 阶段化执行步骤

### P0 前置保障（~5 min）

1. 确认工作区干净（未跟踪项仅 `data/` 与本计划文件 `PLANS/merge-dev107-into-dev.md`——前者将被新 `.gitignore` 覆盖，后者按 P8.3 提交，均不阻塞）；
2. 记录回滚锚点：`git rev-parse dev` → `ORIG_DEV`（9318adf）；
3. `git merge --no-commit --no-ff origin/dev1.0.7` 发起合并（**预期 37 个冲突**，与 §3 清单逐一对账后再动手解决；若数量或名单不符，停止并重新对账）。

### P1 类 A/B 批量解决（~15 min）

```bash
# 类 A：13 个取 dev
git checkout --ours -- <A 组 13 文件路径>
# 类 B：2 个删除
git rm frontend/src/components/settings/PlatformCapabilityPanel.vue \
       frontend/tests/unit/platform-capability-panel.spec.ts
git add <A 组 13 文件路径>
```

### P2 Alembic 迁移链重挂（🔴 本次合并最高风险项，~20 min）

1. **重挂父节点**：`backend/alembic/versions/053003337878_add_moviepilot_integration_tables.py`
   - `down_revision: "c1d2e3f4a5b6"` → `"d1e2f3a4b5c6"`
   - 同步修订文件头链注释（如有）；
2. **约束文档同步**：`backend/docs/constraints/database-migration.md`
   - 该文件**仅 dev 侧改过**（dev1.0.7 相对合并基 diff 为空，审查 F6 已证）→ 自动合并结果 = dev 版原样，只需改 HEAD 声明：
   - 链尾行：`... → c1d2e3f4a5b6 → b3e5f7a9c1d2 → d1e2f3a4b5c6 → 053003337878 ← 当前 HEAD`
   - `alembic heads` 必须输出且只输出 `053003337878`（约束文档门禁测试 `test_constraint_doc_head_matches_chain` 依赖这两处标记）；
3. **安全性论证**（记录进 progress.md）：moviepilot 迁移仅新建两表+索引，不依赖 preset_key 迁移的列变更，也不被其依赖——重挂仅改变执行顺序，无数据兼容风险；
4. **即时验证**：
   ```bash
   cd backend && python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; \
     cfg=Config('alembic.ini'); cfg.set_main_option('script_location','alembic'); \
     assert len(ScriptDirectory.from_config(cfg).get_heads())==1"
   ```

### P3 后端语义合并（~30 min）

1. `torrent_add_service.py` 按 §3-类 C 方案手工合并（重点：dev 固定 msg/reason_code 不回退为 `str(e)` 动态文案——这是双语 P4 防泄露契约）；
2. 4 个 `tests/core/test_db_*.py`：dev 版为基底 + moviepilot 守卫用例并入 + `test_orphan_schema_repair_migration.py` 保留 dev 的 search/setting_templates fixture 建表（合并链升级必需）；
3. 后端即时验证：
   ```bash
   cd backend && mypy app services 2>/dev/null || mypy app
   pytest tests/core/test_db_migration.py tests/core/test_db_rollback_scenarios.py \
          tests/core/test_orphan_migration_production_shape.py \
          tests/core/test_orphan_schema_repair_migration.py -q
   pytest tests/api -q -k "torrent_add or mcp or moviepilot"
   ```

### P4 前端语义合并 + 门禁适配（~40 min）

1. `settings/index.vue` 按 §3-类 C 方案手工合并（i18n 基底 − 主机能力 + MCP/MoviePilot 页签 + Demo 模式渲染）；
2. 🔧 **i18n 遗留审计门禁 spec 自身改写**（审查 Critical-1）：`frontend/tests/unit/i18n-leftover-guard.spec.ts` B 节含契约用例 `readFileSync('src/components/settings/PlatformCapabilityPanel.vue')`——类 B 删除组件后该用例 **ENOENT 必崩**。删除/改写该用例（连同其 describe 块内相关 it）；
3. 🔧 **门禁登记落地为具体清单**（审查 Critical-2；机制经查为 `EXCLUDED_DIRS` 前缀级 + `EXCLUDED_FILE_PATTERNS` 正则级 + ALLOWLIST file+contains 行级）：
   - **EXCLUDED_FILE_PATTERNS**（整文件排除，v1.0.7 新功能面，双语另立项）：
     - `src/api/mcp-settings.ts`、`src/api/moviepilot.ts`
     - `src/views/settings/components/McpSettingsPanel.vue`（39 行中文）、`MoviePilotPanel.vue`（102 行中文）
   - **ALLOWLIST 行级登记**（保留文件审计覆盖，仅放行指定中文）——**确定性红灯，非条件项**（合并树实测）：
     - `src/views/torrents/components/TrackerDetailCard.vue`：媒体库页签段（~15 行：媒体标题/季/集/整理方式/媒体库路径/源文件路径/实例/整理失败/刷新 + tab label「媒体库」）
     - `src/views/torrents/mixins/detailTabsData.ts`：媒体库 tab 定义与 `获取媒体库关联失败` 兜底
     - `src/views/settings/index.vue`：「MCP 服务」「MoviePilot」页签 label
4. 前端即时验证：
   ```bash
   cd frontend && npm run lint
   npx jest tests/unit/i18n-leftover-guard.spec.ts tests/unit/shared-utils.spec.ts \
              tests/unit/navbar-language-switcher.spec.ts tests/unit/tracker-detail-card.spec.ts
   npm run build
   ```

### P5 追踪文档并集（~30 min）

按 §3-类 D 清单逐文件并集合并；`feature_list.json` 追加合并任务条目；`progress.md`/`session-handoff.md` 追加本次会话记录。

🔧 顺手核对（审查 Suggestion）：`AGENTS.md`、`HARNESS_GUIDE.md`、`.github/workflows/release-gate.yml` 随 dev1.0.7 的 b86c57f 归档路径联动干净并入——检查合并后版本中的 PLANS 路径引用与 dev 主线叙事是否一致。

### P6 Roadmap 重实测同步（~30 min，按 roadmap-maintain 技能规范）

1. 对合并后行号漂移的第三层文件（torrent_crud.md、orphan 系列、views 涉及 settings/torrents 的行）逐一 `wc -l`/grep 实测重标；
2. 第二层 README 补 MCP/MoviePilot 文件行、删 PlatformCapabilityPanel 行（根 `docs/roadmap/README.md` 与 `components-layout/README.md` **两处都要删**——审查 W5）；
3. 根 README 生成日期与「本次新增」更新；
4. 若工作量过大，本阶段可拆为合并提交后的独立 `docs(roadmap)` 提交（见 §5 提交策略备选）。

### P7 全量验证门禁（~40 min）

```bash
# 基数先行（审查 Suggestion：先取合并后用例基数，再与基线比对）
cd backend && pytest --collect-only -q | tail -1
cd frontend && npx jest --listTests | wc -l
# 后端全量（dev 侧基线 4832 passed）
cd backend && pytest -q
# 后端静态三件套
mypy app && black --check . && flake8
# 前端全量（dev 侧基线 124 套 1814 例）
cd frontend && npx jest
# 全栈环境验证
./init.sh
```

**验收标准**（全部满足才算完成）：
- [ ] `alembic` 单 HEAD = 053003337878；空库 upgrade 建全 schema；幂等 upgrade 通过
- [ ] 后端 pytest 全绿（≥ dev 基线用例数 + dev1.0.7 新增用例数）
- [ ] mypy/black/flake8 通过
- [ ] 前端 jest 全绿（含 i18n 门禁 B 节改写后通过、键可达性、MCP/MoviePilot 新 spec、TrackerDetailCard/detailTabsData/settings ALLOWLIST 生效）
- [ ] `npm run lint` + `npm run build` 通过
- [ ] settings 页四态检查：主机能力页签消失 / MCP 页签渲染 / MoviePilot 页签渲染 / 其余页签双语正常（人工或截图）
- [ ] `./init.sh` 通过
- [ ] feature_list/progress/session-handoff/roadmap 已更新

### P8 提交与收尾（~10 min）

1. **提交策略**（主方案）：单一合并提交，自包含全绿
   ```bash
   git commit -m "merge: dev1.0.7 合入 dev——MCP+MoviePilot 线并入双语主干
   - 迁移链重挂：053003337878 挂至 d1e2f3a4b5c6（单 HEAD）
   - 双语完成态保留为主干（i18n 取 dev P6-5）
   - 主机能力面板按 282f494 移除；MCP/MoviePilot 面入 i18n 排除清单
   - torrent_add_service：reasonCode 契约 + MCP 领域字段并存"
   ```
2. 备选：若 §6-P6 roadmap 重实测体量大，拆「合并提交（含最小正确 roadmap 占位）+ 独立 `docs(roadmap)` 重实测提交」两笔；
3. 本计划文件 `PLANS/merge-dev107-into-dev.md` 以独立 `docs(plans)` 提交（或并入合并提交，执行时定）；
4. **不推送**——按项目规约 Git 推送仅在用户要求时执行；
5. `session-handoff.md` 补记合并提交号与验证证据。

---

## 5. 风险与对策

| # | 风险 | 等级 | 对策 |
|---|---|---|---|
| R1 | 迁移链双 HEAD（必然发生，若不重挂） | 🔴 | §4-P2 重挂 + P2.4 即时断言 + `test_migration_chain_has_single_head` 门禁兜底 |
| R2 | torrent_add_service 手工合并回退防泄露契约（`str(e)` 进 msg） | 🔴 | P3.1 明确保留 dev 固定文案；`test_reason_contract` 系列用例兜底 |
| R3 | settings/index.vue 手工合并丢 Demo 模式渲染或 i18n 结构 | 🟠 | 对照两侧 blame 逐段核对；jest settings 相关 spec + build 兜底 |
| R4 | 干净自动合并文件的语义冲突（如 torrent_crud.py 双侧都改但未冲突） | 🟠 | P3/P7 全量 pytest 兜底；重点跑 `test_reason_contract_p*` 与 mcp/moviepilot 端点用例 |
| R5 | i18n 门禁对 MCP/MoviePilot 新面打红 | 🟡 | §4-P4.2 排除清单（有先例：移动端/生成契约），双语另立项 |
| R6 | 键可达性门禁误伤（MCP 组件引用了 dev 键包中不存在的键） | 🟢 已消解 | 审查 F3 实证：dev1.0.7 侧独有的 9 个前端改动文件零 `$t` 引用；旧键引用仅存在于类 A 冲突文件（Navbar/formatters，均取 dev）；router.ts 双侧同 blob，21 个 titleKey 全可达 |
| R9 | 审计门禁 spec 自身含对被删组件的源码契约（readFileSync） | 🔴 | 🔧 已转为 P4.2 显式步骤：改写 i18n-leftover-guard.spec.ts B 节（审查 Critical-1） |
| R10 | 干净并入文件含新增中文硬编码（TrackerDetailCard/detailTabsData） | 🔴 | 🔧 已转为 P4.3 ALLOWLIST 行级登记（审查 Critical-2），且 settings 页禁整文件排除 |
| R7 | CRLF 差异（dev1.0.7 曾做 CRLF 归一化） | 🟡 | 合并后 `git diff --check`；lint/build 兜底 |
| R8 | PLANS 归档重叠（dev1.0.7 归档了 dev 侧仍活跃的计划） | 🟡 | §3-类 D 手工合并 PLANS/README.md 时逐份核对活跃状态 |

## 6. 回滚预案

- **提交前**：`git merge --abort`（任意阶段可回到 dev=9318adf 干净态）；
- **提交后未推送**：`git reset --hard ORIG_DEV`（合并提交仅本地，无远端影响）；
- **推送后**：`git revert -m 1 <merge-commit>`（生成反向提交，无需强推）。

## 7. 工作量估算

| 阶段 | 估时 |
|---|---|
| P0~P1 发起+批量 | 20 min |
| P2 迁移链重挂 | 20 min |
| P3 后端语义合并 | 30 min |
| P4 前端语义合并 | 40 min |
| P5 追踪文档 | 30 min |
| P6 roadmap 重实测 | 30 min |
| P7 全量验证 | 40 min |
| P8 提交收尾 | 10 min |
| **合计** | **~3.5 h**（全量测试含等待） |

## 8. 明确不在本次范围（另立项）

1. MCP/MoviePilot 前端界面双语化（键包扩 `mcp`/`moviepilot` 模块、面板文案键化）；
2. MCP/MoviePilot 后端端点 reasonCode 双语契约（对齐 dev P4 模式）；
3. 语言包中主机能力残留键的清扫（无门禁压力，随双语清扫批处理）；
4. 双语 P7 收口（合并后 dev 主线继续，见 PLANS/desktop-bilingual.md）。

---

## 附录 A：独立审查核验结论（reviewer 子代理，2026-09-22）

对 F1~F8 八项事实断言的只读核验结果：

| # | 断言 | 结论 |
|---|---|---|
| F1 | 迁移链分叉/重挂安全 | ✅ 053003337878 仅建表+索引、无外键、零依赖 preset_key；反向亦无依赖；自带 has_table 幂等守卫 |
| F2 | 冲突清单完整性 | ⚠️ 实测 37（非 35）；3 个 core 测试文件未入 §3 → 🔧 已修正（类 C 7 个） |
| F3 | 键可达性无影响（R6） | ✅ dev1.0.7 独有改动零 `$t` 引用；router.ts 双侧同 blob |
| F4 | torrent_add_service 差异全覆盖 | ✅ 双侧 diff 可完全分解为计划①②③；④措辞与 dev 现行代码不符（`as e` 会触发 F841）→ 🔧 已修正 |
| F5 | 主机能力刻意移除 | ✅ 刻意（提交说明明示）；但 guard spec B 节契约用例漏处置 → 🔧 已转 P4.2 |
| F6 | 约束文档事后改可行 | ✅ 成立且前提被精确化：该文件仅 dev 侧改过，自动合并=dev 版原样 |
| F7 | 文件级排除可行性 | ✅ 机制支持（EXCLUDED_FILE_PATTERNS 正则级 + ALLOWLIST 行级）→ 🔧 P4.3 据此落地 |
| F8 | 双改未冲突文件语义安全 | ⚠️ 大体安全（main.ts/store/router/api.py/env.py/package-lock 等逐一验证）；TrackerDetailCard +22 中文行、detailTabsData +6 中文行确定性打红门禁 → 🔧 已转 P4.3 ALLOWLIST |

**审查总体结论**：需修订后执行。必改项 ①~⑤ 已全部吸收进本计划正文（P0.3 / §3 类C④ / P3.2 / P4.2 / P4.3）。
