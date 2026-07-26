# Progress Log - BtDeck 全栈项目

## 2026-07-26 - 高级搜索完备回归测试 + ratio 字典序 bug 修复 + *_multi 死代码清理

**任务 ID**: `v1.0.5.15`（v1.0.5 高级搜索功能回归保护与缺陷修复；当前 dev 版本 v1.0.6）
**分支**: dev
**范围**: 全栈。后端 ratio 双路径字典序 bug 修复 + apply_multi_select_conditions 死代码删除 + 完备回归测试；前端同步删除 *_multi 类型声明。

### 现象与根因

用户要求"为高级搜索功能增加完备的回归测试，测试各种组合下的查询是否能达到预期结果"。在用 3 个独立子代理对实施计划做证伪审查时，发现 3 项阻断性问题：

1. **ratio 字符串字典序比较 bug（双路径）**：`TorrentInfo.ratio` 是 String 列，但 `apply_basic_filters:180-184` 用 `TorrentInfo.ratio >= str(value)` 做字符串字典序比较，导致 `ratio_min=2` 让 `ratio="10.0"` 漏匹配（"10.0" < "2"）。同一 bug 在 condition_groups 路径也存在：`_build_condition_filter` 走 `OPERATOR_MAPPING` 的 `gt/gte/lt/lte` 对 ratio 也做字符串比较。
2. **修复计划误改死代码路径**：原计划"修复 tags_multi 整串匹配 bug"目标错误——`apply_multi_select_conditions` 及 `EnhancedAdvancedSearchRequest` 的 4 个 `*_multi` 字段是前端从不调用的死代码路径（前端 `AdvancedSearchBuilder.vue:1093-1098` 明确将 multiSelect 字段走 condition_groups + contains_any）。tags 子串语义已在 v1.0.5.14 通过 condition_groups 的 contains_any 正确修复。
3. **测试设计多处假绿风险**：种子数据日期用非 ISO 格式、NULL 排序盲区、category NULL 三值逻辑污染、xfail 无法对照两路径。

### 关键决策与证据

- **ratio 修复用 `cast(col, Float)`**：经技术正确性子代理实证，`sqlalchemy.cast(TorrentInfo.ratio, Float)` 在 SQLite 生成标准 `CAST(... AS FLOAT)`。NULL→NULL（WHERE 过滤，不误命中）；"" /"abc"→0.0（入库点 `torrents_async.py` 不会写这些异常值）；"2.5"→2.5。比"列改 Float 类型"（破坏性，需 Alembic 迁移）和"Python 层过滤"（性能差）都更优。
- **双路径统一修复**：`apply_basic_filters` 用 cast 替换 str 比较；`_build_condition_filter` 在 size/date 特殊处理块后加 ratio 分支（`column = cast(column, Float)`），保证两路径语义一致。
- **死代码路径整段删除**：删除 `apply_multi_select_conditions` 方法 + `search_torrents` 中的调用 + `MultiSelectCondition` 类 + `EnhancedAdvancedSearchRequest` 的 4 个 `*_multi` 字段 + 前端 `torrents.ts`/`torrent.ts` 的对应类型声明。前端 grep 实证无任何 `.vue` 业务代码赋值这些字段。
- **回归测试用真实内存 SQLite + StaticPool**：复刻 `test_advanced_search_batching.py` 范式，建 3 表（TorrentInfo/TrackerInfo/BtDownloaders），6 颗种子覆盖所有边界（status/category/tags/size/ratio/date/dr/tracker 全维度差异化）。

### 三代理独立审查（证伪优先）

计划经 3 个 general-purpose 子代理审查（技术正确性 / 测试有效性 / 范围回归），**坐实 3 项阻断性问题**，全部采纳修正：
1. 修复 1 漏 condition_groups 路径（三代理一致发现）→ 双路径都修
2. 修复 2 改死代码（范围代理硬证据：前端 `*.vue` 从不赋值 `*_multi`）→ 改为删除死代码
3. 测试设计 3 处假绿风险（种子日期非 ISO / NULL 排序盲区 / category NULL 三值逻辑）→ 修复种子数据 + 精确集合断言

驳回 1 项不成立的初版质疑（xfail NULL 对照），重新设计为独立 characterization test。

### 改动文件

| 文件 | 改动 |
|---|---|
| `backend/app/services/advanced_search.py` | import 加 `cast, Float`；ratio 基础过滤改数值比较；_build_condition_filter 加 ratio cast 分支；删除 apply_multi_select_conditions 方法 + search_torrents 调用 + MultiSelectCondition import；清理 added_date_max 死代码 pass |
| `backend/app/api/models/advanced_search.py` | 删除 MultiSelectCondition 类 + EnhancedAdvancedSearchRequest 的 4 个 *_multi 字段 |
| `backend/tests/services/test_advanced_search.py` | 删除 MultiSelectCondition import + TestApplyMultiSelectConditions 类（4 mock 测试）+ TestMultiValueOperatorsAgainstRealDb 类（7 真实 DB 测试，迁入新文件 B 类）+ 清理未用 PropertyMock import |
| `backend/tests/api/conftest.py` | 扩展 make_torrent 支持 tags/category/ratio/ratio_limit/torrent_id/super_seeding/enabled/save_path 关键字参数 |
| `backend/tests/services/test_advanced_search_regression.py` | **新建**：82 用例 8 类完备回归测试（A 基础过滤 / B 全22操作符 / C 条件组组合 / D *_multi 删除守卫 / E tracker 子查询 / F 排序分页 / G 端到端 / H NULL 边界） |
| `frontend/src/api/torrents.ts` | 删除 4 个 *_multi 字段声明 |
| `frontend/src/types/torrent.ts` | 删除 4 个 *_multi 字段 + MultiSelectField 接口 |

### 回归测试抓到的实现缺陷

TDD 红阶段验证 bug 存在（2 用例失败）→ 修复后转绿（2 用例通过）。关键证据：
- `ratio_min=2` 基础过滤：修复前只命中 t1(2.5)，t3(10.0) 因 "10.0" < "2" 字典序漏匹配；修复后命中 t1+t3
- 条件组 `ratio >= 2`：修复前同样漏 t3；修复后命中 t1+t3
- `ratio_max=999` 不误命中 ratio=NULL 的 t4（CAST(NULL AS FLOAT) <= 999 → NULL → WHERE 排除）

### 验证结果

| 验证项 | 结果 |
|---|---|
| 新增回归测试 `test_advanced_search_regression.py` | ✅ 82/82 通过 |
| advanced_search 全量相关测试（8 文件） | ✅ 188 passed |
| 含 auth_protection 扩展回归 | ✅ 269 passed |
| flake8（5 改动文件） | ✅ 0 error |
| black --check（5 改动文件） | ✅ 通过（新测试文件已 reformat） |
| mypy（2 源文件） | ✅ 与 baseline 一致（29 errors 全在既有 delete_torrents_batch/get_search_statistics 方法，本次 cast/ratio 改动行 0 新增） |
| 前端 typecheck（tsc --noEmit） | ✅ 通过 |
| 前端 lint（eslint --max-warnings 0） | ✅ 0 error |

### 明确不修的边界（已记入 evidence）

- NULL 安全语义差异（顶层 OPERATOR_MAPPING vs `_build_text_filter`）：作用于不同列集合（前者 name/tags/category，后者仅 tracker_url/tracker_msg），是 SQL 实现必需的安全处理而非语义 bug。本任务用 H 类 characterization test 钉死现状，独立技术债任务统一。
- `ratio_limit` 也是 String 列，理论上有同类字典序 bug 但前端无 API 暴露，本次不动。
- search-preview 端点 conditions_json 永远是单 AND 组：既有设计。
- `_build_text_filter` 对非文本操作符 fallback to contains：既有行为，仅测试覆盖。

### 工作区说明

- 本轮未执行 Git 提交。
- 浏览器手测待用户在本地环境完成（CI 已覆盖 pytest + flake8 + black + mypy + typecheck + lint 全门禁）。

---

## 2026-07-25 - 高级搜索分类/标签/下载器字段 options 注入补全

**任务 ID**: `v1.0.5.13`（v1.0.5 高级搜索功能的遗漏补丁；当前 dev 版本 v1.0.6）
**分支**: dev
**范围**: 仅前端。不新增后端端点。

### 现象与根因

用户报告种子列表高级搜索对话框中：① 分类、标签、下载器下拉框没有选项；② 标签用的组件不是下拉框。

经溯源（前端 + 后端源码坐实），两个现象是**同一根因**：`AdvancedSearchBuilder.vue` 对 `category / tags / downloader_name` 三字段只声明了空 `options: []` 占位（注释"将通过API动态获取"），但从未接入数据源——`getFieldOptions()` 对三字段返回 `[]`、`created()` 没调任何接口、顶部 imports 无 `@/api/*`。分类/下载器（原生 `el-select`）下拉因此为空；标签（`AdvancedMultiSelect`，本就允许自由输入）options 为空，只剩"手敲创建"一种交互，让用户感觉"不是下拉框"。

### 关键决策与证据

- **字段口径**（后端源码坐实）：`downloader_name` 匹配 `TorrentInfo.downloader_name` 列，入库点（`torrent_sync.py:1220` 等）全部写 `downloader.nickname`，故前端 value 取 `nickname`（非 `downloader_id`）；`category` 匹配 `TorrentInfo.category`（`==` 精确）；`tags` 匹配 `TorrentInfo.tags`（`LIKE`）。
- **数据源语义**：后端 `tag_management.py:_merge_assigned_filter_names` 已把"配置表 ∪ 种子实际 distinct 值"合并去重，选项必然命中至少一条种子，无"选了搜不到"的语义错配。
- **方案选型**：采用"构建器自拉接口"。经审查验证不违反复用原则——全仓无 options provider/mixin/composable/vuex 模块可复用；`index.vue` 根本没有 category/tag 数据；`ConditionValueInput` 的 `fieldOptions` prop 机制表明数据流设计意图就是"builder 维护 options"。
- **刷新策略**：用户决策为"每次打开对话框重新拉取"。新增公开方法 `refreshFieldOptions()`，由两父视图在打开对话框时经 `$nextTick` + `$refs` 调用（el-dialog 默认 `destroy-on-close=false`，组件常驻，`created()` 只触发一次）。

### 三代理独立审查（证伪优先）

计划经 3 个独立 general-purpose 子代理审查（技术正确性 / 测试有效性 / 根因与方案选型），采纳全部 5 个阻断性修正：
1. `extractErrorMessage` import 来源 `@/utils/formatters`（非 `error-normalize`）；
2. API 返回 `ApiResponse` envelope，必须解 `.data` + 校验 `code === '200'`；
3. spec mock 改为显式列举 exports（不用 `requireActual`，全仓零先例）；
4. 项目无 `flushPromises`，复用 `traditional-view-component.spec.ts` 的 `flushLifecycle` 三段式；
5. B2 用例明确 mount/shallowMount 策略。
驳回 3 个不成立的质疑（响应式需 `$set`、Promise.allSettled 兼容性、构建器自拉违反复用原则——经验证均不成立）。原 B3 源码字符串契约 spec 因过度耦合实现细节、与行为测试 100% 重叠而删除。

### 改动文件

| 文件 | 改动 |
|---|---|
| `frontend/src/components/torrents/AdvancedSearchBuilder.vue` | 加 import + 三 options 状态字段 + `loadFieldOptions`（`Promise.allSettled` 并发，解 envelope，部分失败静默/全失败告警，销毁防护）+ 公开 `refreshFieldOptions` + `getFieldOptions` switch 三 case |
| `frontend/src/views/torrents/index.vue` | `@click` 改 `openAdvancedSearch`，nextTick 调 `refreshFieldOptions` |
| `frontend/src/views/torrents/TraditionalView.vue` | 同上 |
| `frontend/src/components/torrents/__tests__/AdvancedSearchBuilder.spec.ts` | 扩展：mock 三 api + `flushLifecycle` + 6 用例（首次加载/部分失败/全失败/refresh/value 透传/dialog 复用语义） |
| `frontend/src/components/torrents/__tests__/ConditionValueInput.spec.ts` | 新建：4 用例（select 渲染 el-option / multiSelect options 透传 / 空选项不崩 / emit input+change） |

### 回归测试抓到的实现缺陷

B1「部分失败降级」「全失败」用例失败，暴露真实缺陷：`loadFieldOptions` 失败时未清空旧 options，导致"上次成功 + 本次失败"时残留旧数据误导用户。修正为每次刷新前重置三数组为空，语义更清晰。

### 验证结果

| 验证项 | 结果 |
|---|---|
| ESLint（6 变更文件） | ✅ 通过（自动修复 9 条格式问题后 0 error） |
| `tsc --noEmit` | ✅ 通过 |
| `test:coverage`（全量） | ✅ 18 suites / 283 tests 全绿（含新增 10 用例）；Branches 44.46%（>40% 门禁） |
| `npm run build` | ✅ 通过（仅项目既有 Sass/资源体积 warning） |
| `feature_list.json` JSON 合法性 | ✅ node 解析通过 |

### 明确不修的边界（已记入 evidence）

- 下载器改名导致的历史种子 `downloader_name` 漂移 → 单独立项。
- 抽 `torrentFieldOptions` composable 做跨组件缓存 → 后续优化。
- `category` 的 `==` 精确匹配对大小写/空格敏感 → 后端既有语义，本次不动。
- select 字段 `in/not_in` 操作符当前传单值字符串 → 既有行为，非本次引入，仅注释说明。

### 工作区说明

- 本轮未执行 Git 提交。
- 浏览器手测待用户在本地环境完成（CI 已覆盖 lint/typecheck/test/build 全门禁）。

---

## 2026-07-25 - 高级搜索三字段统一多选 + 操作符语义修正（全栈）

**任务 ID**: `v1.0.5.14`（v1.0.5.13 的延续；当前 dev 版本 v1.0.6）
**分支**: dev
**范围**: 全栈。后端扩操作符白名单 + OPERATOR_MAPPING；前端三表同步 + 两份 formatParamValue 同步 + 操作符按字段过滤 + 旧模板归一化。

### 需求

v1.0.5.13 修复了三字段下拉无选项后，用户进一步要求：标签选择器改用与分类一样的下拉框，且**分类和标签都要支持多选**。经澄清：三字段（category/tags/downloader_name）统一用 AdvancedMultiSelect 多选。

### 第二轮 3 子代理独立审查（证伪优先）

计划经 3 个 general-purpose 子代理审查（技术正确性 / 测试有效性 / 向后兼容），**坐实两个致命缺陷**，推翻了初版"前端零改后端"的前提：

1. **tags 的 in 语义对逗号串列是错的**（代理 C 发现）：`TorrentInfo.tags` 是逗号分隔单字符串列（如 `"movie,4k"`）。`column.in_(['movie'])` 只匹配整串等于 `'movie'`，`tags='movie,4k'` 不命中。→ tags 必须用 `contains_any`（OR(LIKE)），category/downloader_name 单值列才用 in。
2. **后端 Pydantic 白名单拒旧操作符**（代理 A/C 发现）：`validate_operator` 白名单不含 contains_any 等，旧模板请求 422。→ 后端白名单 + OPERATOR_MAPPING 双扩。
3. **遗漏第三份字段表**（代理 A/B 发现）：`torrentBatch.ts:541-561 ADVANCED_FIELD_TYPES` 是模板路径的字段类型表，category 是 select 且缺 downloader_name。→ 三表同步。
4. **两份 formatParamValue 副本**（代理 B 发现）：`AdvancedSearchBuilder.vue` 与 `torrentBatch.ts` 各一份，只改一份会导致即时搜索与模板搜索输出形态矛盾。→ 两份同步数组化。

驳回"前端零改后端"的不成立前提；采纳全部修正。

### 关键设计（字段 × 操作符 × value 矩阵）

| 字段 | 列类型 | 后端操作符 | SQLAlchemy 实现 | 前端 value |
|---|---|---|---|---|
| category | 单值 String | in/not_in | column.in_(list) | string[] |
| downloader_name | 单值 String | in/not_in | column.in_(list) | string[]（nickname） |
| tags | 逗号串 String | contains_any/not_contains_any | or_(*[column.contains(v)]) | string[] |

### 改动

**后端（2 文件 + 1 测试）**：
- `models/advanced_search.py`：`validate_operator` 白名单加 contains_any/all/not_contains_any/not_contains_all
- `services/advanced_search.py`：补 `not_` import；加模块函数 `_normalize_multi_value`（数组/逗号串/单值归一化）；OPERATOR_MAPPING 加 4 个 lambda（or_/and_/not_ 组合 column.contains）
- `tests/services/test_advanced_search.py`：+33 用例（TestNormalizeMultiValue 7 + TestOperatorWhitelistAcceptsMultiValue 6 + TestMultiValueOperatorsAgainstRealDb 7 真实 SQLite 端到端语义验证 + 既有保留）

**前端（3 源文件 + 4 测试）**：
- 三表同步：category/downloader_name 的 type select→multiSelect（AdvancedSearchBuilder.statusFields / ConditionValueInput.fieldTypeMap / torrentBatch.ADVANCED_FIELD_TYPES，后者补 downloader_name 条目）
- `operatorGroups.multiSelect` 重构为含全部 4 操作符；`getOperatorGroups` 按 `matchMode`（exact/substring）过滤——单值列只暴露 in/not_in，逗号串列只暴露 contains_*
- SearchField 接口加 `matchMode?: 'exact' | 'substring'`；category/downloader_name=exact，tags=substring
- 两份 formatParamValue 的 multiSelect 分支：`join(',')` → 返回数组
- `onFieldChange`：multiSelect 字段初始化 value=[]，其它 null
- `applyTemplateGroups`：加载旧模板时归一化（单值列的 contains_* 转 in/not_in；逗号串 value 拆数组）
- `buildSearchParams` 扁平 fallback：multiSelect 字段不生成扁平参数（避免 apply_basic_filters 的 == 误用数组）
- 测试：AdvancedSearchBuilder.spec.ts 重写用例⑤ + 新增 4 用例；ConditionValueInput.spec.ts 用例① 参数化（it.each 三字段）；torrent-batch.spec.ts 更新 tags 断言；新建 field-types-consistency.spec.ts（三表一致性守卫，10 用例）

### 回归测试抓到的语义

后端真实 DB 测试验证（最有价值的回归保护）：
- `tags='movie,4k'` 被 `contains_any(['movie'])` 命中（IN 整串匹配做不到）——证明 tags 必须用 contains_any
- `category in(['电影'])` 精确匹配 `category='电影'`，`in(['电'])` 不命中（单值列 in 是精确非子串）
- `not_contains_any(['movie'])` 对 `tags=NULL` 不命中（SQL NULL 语义：NOT(NULL LIKE) 为 unknown）

### 验证结果

| 验证项 | 结果 |
|---|---|
| 后端 pytest（advanced_search 相关） | ✅ 77/77 通过（含新增 33 用例） |
| 后端 mypy | ✅ 与 baseline 一致（29 errors，0 新增） |
| 后端 black/flake8 | ✅ 通过（PropertyMock F401 为既有 baseline，非本次引入） |
| 前端 ESLint（变更文件） | ✅ 0 error 0 warning |
| 前端 tsc --noEmit | ✅ 通过 |
| 前端 test:coverage | ✅ 19 suites / 298 tests 全绿；Branches 44.46%（>40% 门禁） |
| 前端 npm run build | ✅ 通过 |

### 明确不修的边界（已记入 evidence）

- `apply_multi_select_conditions`（*_multi 顶层字段）路径的 tags 整串语义 bug 是既有问题，前端不走该路径，本次不动。
- `contains_all`（AND 语义）UI 不暴露（避免与 in 混淆），后端保留以兼容旧模板。
- PropertyMock F401 是既有 baseline，非本次引入，不越权修。

### 工作区说明

- 本轮未执行 Git 提交。
- 浏览器手测待用户在本地完成（CI 全门禁已覆盖）。

---

## 2026-07-22 - 查询模板与孤儿文件页面 UI 对齐

**任务 ID**: `v1.0.6.24`
**分支**: dev
**范围**: 仅调整查询模板与孤儿文件两个前端页面的排布、视觉层级与响应式表现，不修改业务逻辑、API、权限和清理流程。

### 完成内容

- 新增 `management-list-page.scss`，基于项目现有主题变量沉淀管理列表页共用骨架：最大内容宽度、页头、筛选面板、数据面板、表格滚动、分页、统计卡片及移动端断点。
- 查询模板页统一为“标题说明 + 页头操作 + 带标签筛选 + 列表元信息 + 数据表格”的页面结构；刷新与新建模板操作归入页头。
- 孤儿文件页使用与仪表盘/管理页一致的统计卡视觉，扫描与刷新归入页头，清理操作与选中状态归入数据面板，分页收纳到同一面板。
- 两页补充语义化标题、区域标签、明确的空状态；保留原有查询、扫描、清理、创建、编辑、删除等方法与调用链。
- 新增 `management-pages-ui.spec.ts`，以 7 项契约覆盖共用页面骨架、操作分组、统计区、分页归属、响应式样式与全局样式入口。

### 验证结果

- UI 契约测试：1 suite / 7 tests 全部通过。
- `npm run typecheck`：通过。
- 完整 `npm run lint` 与变更文件 ESLint：通过。
- `npm run build`：通过；仅有项目既有 48 条 Sass/资源体积 warning。
- 本地隔离环境浏览器验证：1440×900 桌面视口下两页内容和操作区对齐；390×844 移动视口下文档宽度等于视口宽度，宽表在内部滚动，四张统计卡改单列。
- 根 `./init.sh`：通过；仅保留 Git 工作区、jq、未激活后端虚拟环境及 Git Bash 未发现 Node 的环境提示，前端已通过 Windows Node 独立完成上述门禁。

### 工作区说明

- 本轮未执行 Git 提交。
- 启动的临时前后端验证服务及隔离数据库均已关闭并清理；既有未跟踪工具目录未改动。

---

## 2026-07-19 - 生产环境三连报错根因修复

**任务 ID**: `prod-hotfix-2026-07-19`
**分支**: dev
**范围**: 针对生产环境日志中的三类报错（连接泄漏 SAWarning / 审计日志 AttributeError / transmission-rpc v7 API）做根因分析 + 独立审查 + 修复 + 提交推送。

### 方法

3 个并行子代理对**同一份报错日志**独立做"形成结论 → 证伪/证实原假设"审查，每个假设都附反证排查清单。审查结束后再派 3 个独立 general-purpose 子代理对**我的分析结论**做独立证伪测试，重点寻找被遗漏的反证。

### 三连报错与根因（含审查修正）

**报错 1：`'Client' object has no attribute 'get_session_variables'`（WARNI 循环）**
- 根因：transmission-rpc v7.0 intentional major breaking 移除 `Client.get_session_variables()`，替代为 `client.get_session()` 返回 Session 对象，字段用 snake_case 属性（`session.download_dir`）而非旧版 dict key `"download-dir"`。
- 项目 pin `transmission-rpc~=7.0.11`，`downloader_path_scan.py:680` 是唯一遗留旧 API 调用点（其它 7 处 Transmission 调用均已用新 API）。
- 审查代理运行时验证：`hasattr(Client, 'get_session_variables')==False`、`hasattr(Client, 'get_session')==True`，结论坐实。

**报错 2：`记录审计日志失败: name`（ERROR 偶发）**
- 根因：`torrent_crud.py` 四处种子存在性查询用 `db.query(TorrentInfo.info_id).first()` 返回只含单列的 Row；hash 冲突分支 `db_torrent` 被赋值为该 Row，审计日志构造时访问 `.name/.hash/.size` 触发 SQLAlchemy 2.0 `Row.__getattr__`，`str(AttributeError)` 恰为裸名 `'name'`。
- 偶发原因：仅 hash 冲突分支触发；`.info_id` 因是选中列不报错，`.name` 是首个失败点。
- 独立审查代理用 SQLAlchemy 2.0.47 实测端到端复现：`str(Row.__getattr__('name'))=='name'`，并排除普通 NameError/AttributeError/KeyError（str 格式都不匹配）。

**报错 3：`SAWarning: garbage collector cleaning up non-checked-in connection`（traceback 误指 transmission_rpc/torrent.py:259）**
- 根因：三个 Service 类自建 `SessionLocal/AsyncSessionLocal` 从不 close；`NullPool+aiosqlite` 下连接由 GC 周期性回收，恰好命中 Transmission RPC JSON 解析循环栈帧 → traceback 误指 `super().__init__(fields=fields)`。
- **审查关键修正**：原分析把三个 Service 并列为"本次报错的根因"，但 `recycle_bin_service` 是**同步** `SessionLocal`（同步 sqlite 方言 `is_async=False`），按 `pool/base.py:952` 不进入该 SAWarning 分支；**直接元凶是 `SeedTransferService` 内嵌 `TorrentFileBackupManagerService` 自建的 async session**。`recycle_bin_service` 的同步泄漏是另一类问题（`database is locked` 风险），需单独修。
- **NullPool 不豁免该警告**：审查代理读 `sqlalchemy/pool/base.py:951-952` 源码确认判定只看方言 `is_async`，与 pool 类型无关。

### 修复（7 文件）

| 修复点 | 文件 | 设计 |
|--------|------|------|
| P0-1 `TorrentFileBackupManagerService.aclose()` | `services/torrent_file_backup_manager.py` | `_owns_db`（仅自建才关）+ `_closed`（幂等）双标志 |
| P0-2 `SeedTransferService.aclose()` | `services/seed_transfer_service.py` | 删除死代码 `self.async_db`（无任何方法读取）+ `aclose()` 级联关闭 backup_manager |
| P0-3 seed_transfer 2 端点 try/finally | `api/endpoints/seed_transfer.py` | 调用 `service.aclose()` |
| P0-4 `RecycleBinService.close()` | `services/recycle_bin_service.py` | 同步版双标志 close() |
| P0-5 recycle_bin 4 端点 try/finally | `api/endpoints/recycle_bin.py` | 调用 `service.close()` |
| P1 torrent_crud 4 处 query | `api/endpoints/torrent_crud.py` | `db.query(TorrentInfo.info_id)` → `db.query(TorrentInfo)` |
| P2 transmission-rpc v7 API | `tasks/scheduler/downloader_path_scan.py` | `get_session_variables()+['download-dir']` → `get_session()+.download_dir` |

**为何用 `_owns_db`/`_closed` 标志而非 `self.db = None`**：避免误关闭外部传入的共享 session + 保证幂等；同时 `self.db = None` 会触发 mypy `None → Session` 类型错误（`_closed: bool` 无此问题）。

### 验证结果

| 验证项 | 结果 |
|---|---|
| flake8（7 文件） | ✅ 通过 |
| black（7 文件） | ✅ 通过 |
| mypy（3 service 文件） | ✅ **92 errors，与 baseline 完全一致（0 新增）** |
| 相关 pytest（5 套件 / 55 用例） | ✅ 55 全通过 |
| 全量 pytest（排除 master 同样 hang 的文件） | ✅ **2146 passed, 1 skipped, 0 failed**（189s） |
| `test_torrent_sync_review.py::test_cached_client_exception_handled` | ⚠️ 已 git stash 验证 master baseline 同样 hang，与本次修改无关 |

### Git 状态

- 3 个独立 commit 已推送至 `origin/dev`（`3348016..7c4caee`）：
  - `62404e7` P0 连接泄漏修复（5 文件，+217/-124）
  - `fc04ab8` P1 审计日志 AttributeError（1 文件，+16/-4）
  - `7c4caee` P2 transmission-rpc v7 API 升级（1 文件，+8/-5）
- 本轮文档（progress.md + feature_list.json + .gitignore）将单独成 1 个 commit。

### 副带修复

- `backend/.gitignore` 补 `.pytest-*/` 规则：pytest 中断留下的临时目录（`.pytest-final-all-*` / `.pytest-p1-close-*`）此前未被忽略，且因 Docker Desktop WSL2 挂载锁无法物理删除；通过 gitignore 规则避免污染 git status 与误纳提交。

### 遗留技术债（本次不动）

- 约 92 个 mypy 历史错误（项目预存在，与本次修改无关）。
  - **订正（2026-07-19 code review 后）**：92 是 3 个 service 文件局部口径；实测同口径已降到 **81**，全量 `mypy app` 实为 **1484 错误 / 120 文件**（约 60% 是 SQLAlchemy typed Column 噪声，非真 bug）。后续 hotfix 沿用"修改文件 mypy 数 ≤ baseline"局部守则即可，**不引入**全量 mypy CI 门禁。
- ~~`cron_executor.py:80` 的 `db = SessionLocal()` 是否 finally close 需独立排查~~ **已核实（2026-07-19）**：第 80-107 行有完整 `try/finally: db.close()`，结构安全无泄漏。该审查项是预防性提示，已闭环。
- 真实环境压测（连接泄漏消除验证）需运维监控 SAWarning 在长时间运行后是否复现。

---

## 2026-07-19 - prod-hotfix code review 后续 issue 跟踪清单

**任务 ID**: `prod-hotfix-2026-07-19-followup`
**分支**: dev
**范围**: 3 个独立子代理对 prod-hotfix 完成 code review 后，再派 2 个独立评估代理对剩余 11 项（A-K）做 ROI 分级，挑选值得作为后续 issue 跟踪的项；低成本闭环项立即执行。

### 方法

- **评估代理 1**（代码层）：评估 A-E 五项，实证（grep + 读源码）后给出"建议跟踪 / 不跟踪 / 调研后再定"分级 + 工作量估算
- **评估代理 2**（测试/技术债层）：评估 F-K 六项，实证（实跑 pytest + mypy）后给出同分级
- 两个代理结论高度趋同，未出现矛盾判断

### 立即执行的低成本闭环（本次会话已做）

| 项 | 处理 | commit |
|----|------|--------|
| **C** seed_transfer_service.py:384 变量名遮蔽 | 改名为 `local_backup_manager` | 本次 |
| **B** torrent_backup.py:549 死代码（构造即丢弃） | 删除 | 本次 |
| **I** mypy 历史债务 | progress.md 订正度量口径（92 → 81 局部 / 1484 全量） | 本次 |
| **E/K** cron_executor.py:80 排查 | 实证已正确 close，progress.md 标记闭环 | 本次 |

### 推荐立项跟踪（按优先级）

| 优先级 | Issue 标题 | 工作量 | 价值 |
|--------|-----------|--------|------|
| **P1** | `[test] 启用 test_torrent_sync_review.py 5 个 skip 测试` | 0.5-1 天 | ROI 最高；patch `qbClient/trClient` fallback 路径让 ConnectionError 立即 raise，根治 hang；启用后多 5 个真实回归锚点（fallback 建连异常处理） |
| **P2** | `[torrent-crud] hash 冲突分支审计语义 + 下载器重复调用` | 半天 | 真实业务影响：用户上传已存在 hash 种子时仍调 `add_torrent`（网络/认证开销）+ 审计写 `{"status":"added"}` 但实际可能未新增；运维审计会反复质问 |
| **P2** | `[test] 补 DownloaderPathScanTask.execute() 主流程测试` | 0.5-1 天 | 841 行任务类除 `_get_default_path_from_downloader` 外零覆盖；`_update_path_mapping`/`_sync_default_path` 已接入 `db_write_scope`（sync-resource-governance.2.6）但无锚点；目标：happy path + db_write_scope 行为 + 1-2 个 fallback 分支，不做端到端真实 RPC |
| **P3** | `[backup-manager] aclose 后访问 repository 加防御` | 1-2 小时 | 治理闭环：当前 `aclose()` 关 self.db 但不清 self.repository，close 后访问会触发 SAWarning（SQLAlchemy 自动重开无归属连接）；生产路径不触发但 API 不安全；建议方案 A：`aclose` 中 `self.repository = None` |
| **P3** | `[test] recycle_bin fixture 加真实 Session 守卫` | 0.5 天 | 防御性：当前 `patch("app.database.SessionLocal", return_value=db_session)` 若被改成 MagicMock，9 个测试会"全绿但什么都没测"；加 1 个断言 fixture 注入真实 Session 的守卫测试 |

### 明确不立项（含理由）

| 项 | 不立项理由 |
|----|-----------|
| **B** torrent_backup/torrents_async 12 处统一 close | `torrent_backup.py` 用 `async with AsyncSessionLocal()`（自动关），`torrents_async.py` 4 处 `_owns_db=False`（aclose 本就是 no-op）；**当下不泄漏**，"未来风险"建议转文档约定而非改 12 处代码 |
| **F** torrent_crud /add /add-batch 端点 e2e | 核心 bug 已被 `test_torrent_crud_query.py` 5 用例 + mutation 反向锚定直接覆盖；端点 e2e 需 mock 5 个外部依赖 + 跑 30 秒重试循环，1.5-2 周换不到新回归类型；备注：待 TestClient 基础设施沉淀后再做 |
| **I（治理）** mypy 全量治理 | 1484 错误 60% 是 SQLAlchemy typed Column 噪声非真 bug；消除需 declarative → Mapped 全量重构（数周-数月），收益不抵成本；仅订正 progress.md 口径 |
| **K（排查）** cron_executor.py:80 | 已实证第 80-107 行有完整 `try/finally: db.close()`，无泄漏；审查提示是预防性，已闭环 |

### 评估方法学说明

两个评估代理的关键反证（避免后续审查踩坑）：
- **J 的 skip 数量**：实测 5 个（class 级 skip 覆盖 2 个 method + 3 个 method 级 skip），不是 4 个。
- **I 的 mypy 口径**：progress.md 的"92"是 **3 service 文件局部口径**（实测现 81），全量是 1484——评估时必须区分。
- **K 的代码现状**：第 80 行 `db = SessionLocal()` 配套第 107 行 `finally: db.close()`，结构安全。
- **H 的真实风险**：本次新增 `test_service_close_endpoint.py` 已用 `wraps=` spy 范式绕开脆弱性；残留风险是"fixture 被改成 MagicMock"，加守卫测试即可，无需重写 fixture。

---

## 2026-07-18 - 传统分页预设与展开箭头修正

**任务 ID**: `v1.0.6.22`
**分支**: dev
**范围**: 修复传统模式分页组合框只显示当前值的问题，补充大分页预设并增加展开/收起箭头。

### 完成内容

- 定位到 `el-autocomplete` 聚焦时用当前输入值 `20` 过滤候选，导致下拉只剩一个预设；候选函数改为始终返回完整预设。
- 分页预设调整为 20/50/100/500/1000，继续支持 1–100,000 手动输入、Enter/失焦生效及普通/重复任务数据源保持。
- 组合框右侧增加方向箭头：收起时向下、展开时向上，可用鼠标、Enter 或 Space 切换；聚焦、失焦和选择预设时同步状态。
- 扩展组件桩与回归断言，直接以当前值 `20` 查询并验证五个预设，覆盖箭头展开、收起、再次展开以及选择预设后的分页请求。

### 验证结果

| 验证项 | 结果 |
|---|---|
| 目标分页/组件/虚拟窗口回归 | ✅ 3 suites / 18 tests |
| 前端全量 Jest | ✅ 14 suites / 253 tests |
| TypeScript / 完整 ESLint / Vuex lint | ✅ 通过 |
| 前端生产构建 | ✅ 通过（仅既有 48 条 Sass/资源体积 warning） |
| 根 `init.sh` | ⚠️ 当前 Windows 无 WSL，系统 `bash.exe` 无法执行 |
| `git diff --check` | ✅ 通过 |

### Git 状态

- 本轮修改已随当前任务提交、尚未推送；`dev` 相对 `origin/dev` ahead 5。
- 工作区既有未跟踪目录、镜像 tar、脚本与个人 `tools/` 均保持不动。

---

## 2026-07-18 - 传统种子页分页组合框与虚拟滚动

**任务 ID**: `v1.0.6.21`
**分支**: dev
**范围**: 合并传统模式的预设/手动分页输入，并将列表锁定为固定视口，超长当前页采用虚拟滚动。

### 完成内容

- 分页栏改为单个 `el-autocomplete`：聚合 10/20/50/100 预设和 1–100,000 自定义输入，选择预设、按 Enter 或失焦均走同一归一化入口。
- 改分页大小后统一回到第 1 页；普通列表和重复任务仍分别使用原有数据源与服务端分页，不自动跨页加载。
- 传统页高度与列表模式对齐为 `calc(100vh - 84px)`；表格容器通过 `flex: 1 1 0`、`height: 0` 锁定剩余可视高度，内容仅在容器内部滚动。
- 新增表格专用虚拟窗口：固定 32px 行高、上下各 8 行缓冲，使用语义化占位行维持完整滚动高度，只切片渲染当前可视窗口。
- 通过 `ResizeObserver` 同步真实视口高度，滚动更新由 `requestAnimationFrame` 合帧；分页、筛选、排序和切换重复任务时重置到列表顶部。
- 新增 4 项纯函数边界回归，并扩展组件测试覆盖单一分页框、预设/自定义输入、100,000 上限、重复任务数据源保持和 1000 条长列表虚拟窗口。

### 验证结果

| 验证项 | 结果 |
|---|---|
| 目标分页/组件/虚拟窗口回归 | ✅ 3 suites / 18 tests |
| 长列表窗口 | ✅ 1000 条、320px 视口仅渲染 26 条可视/缓冲记录 |
| 前端全量 Jest + coverage | ✅ 14 suites / 253 tests；Statements 52.48%、Branches 44.34%、Functions 44.75%、Lines 51.89% |
| TypeScript / 完整 ESLint / Vuex lint | ✅ 通过 |
| 前端生产构建 | ✅ 通过（仅既有 48 条 Sass/资源体积 warning） |
| 浏览器本地核验 | ⚠️ 生产构建可加载，但无登录/API 环境，被路由守卫停在登录页 |
| 根 `init.sh` | ⚠️ 当前 Windows 无 WSL，系统 `bash.exe` 无法执行 |
| `git diff --check` | ✅ 通过 |

### Git 状态

- 本轮修改已随当前任务提交、尚未推送；`dev` 相对 `origin/dev` ahead 4。
- 工作区既有未跟踪目录、镜像 tar、脚本与个人 `tools/` 均保持不动。

---

## 2026-07-18 - 传统种子页回归覆盖补强

**任务 ID**: `v1.0.6.20`
**分支**: dev
**范围**: 对传统种子页近期交互、布局、分页和元数据补全改动补充组件级与后端分支回归。

### 完成内容

- 新增 `TraditionalView` 挂载测试，直接覆盖仅保留“删除”四级下拉、元数据默认 Tracker 且无“常规”页签，以及完整分类/标签映射。
- 覆盖自定义分页 Enter/失焦生效、100,001 钳制到 100,000、应用后回到第 1 页；验证重复任务模式翻页、改页大小和刷新均不会退回普通列表请求。
- 增加悬浮详情层位于分页上方、关闭后不接收指针事件，以及左侧分类/标签区可纵向滚动的布局契约。
- 将 `TraditionalView.vue` 纳入 Jest 覆盖率采集；为兼容 Vue 2 测试模板编译器，将模板中的可选链改为等价显式判空，运行行为不变。
- 后端覆盖 qB hash 归一化、去重及 100 条分批，正常/重试增量详情水合，Transmission 缓存客户端实时元数据，以及缓存快照或下载器 API 失败时返回空结果的降级路径。
- 重复任务 API 新增 Transmission 两下载器同 hash 元数据集成断言；分类/标签聚合新增 `dr=1` 与 `deleted_at` 记录排除回归。

### 验证结果

| 验证项 | 结果 |
|---|---|
| 前端 `TraditionalView` 组件回归 | ✅ 7/7 passed |
| 前端全量 Jest + coverage | ✅ 13 suites / 246 tests；Statements 51.91%、Branches 43.26%、Functions 44.63%、Lines 51.34% |
| 后端重复任务/标签聚合/元数据专项 | ✅ 78/78 passed |
| 后端本次新增可执行行 | ✅ `torrents_async.py` 9/9；`torrent_metadata.py` 157/199（78.9%） |
| 后端 flake8 / 目标 Ruff 格式 | ✅ 通过 |
| TypeScript / 完整 ESLint / Vuex lint | ✅ 通过 |
| 前端生产构建 | ✅ 通过（仅既有 Sass/资源体积 warning） |
| 浏览器本地核验 | ⚠️ 生产构建可加载，但无登录/API 环境，被路由守卫停在登录页 |
| `git diff --check` | ✅ 通过 |

### Git 状态

- 本轮补充已随当前任务提交、尚未推送；`dev` 相对 `origin/dev` ahead 3。
- 工作区既有未跟踪目录、镜像 tar、脚本与个人 `tools/` 均保持不动。

---

## 2026-07-18 - 传统种子页悬浮元数据与自定义分页大小

**任务 ID**: `v1.0.6.19`
**分支**: dev
**范围**: 纠正传统模式元数据面板位置，并为普通列表与重复任务统一增加最大 100,000 的自定义分页大小。

### 完成内容

- 元数据面板改为表格区域内的绝对定位悬浮层，底边固定在分页栏上方；打开时覆盖列表底部而不改变表格或分页布局，关闭时不占空间且不接收指针事件。
- 分页栏保留 10/20/50/100 预设，新增“每页 [输入框] 条”；按 Enter 或失焦生效，并回到第 1 页。
- 自定义值统一归一化为整数 1–100,000：空值或非数字保持当前值，越界值自动钳制。
- 普通种子列表 `limit` 与重复任务 `pageSize` 的后端上限同步放宽至 100,000，避免前端填写后被接口 422 拒绝。
- 新增前端纯函数边界测试，以及两个后端接口的 100,000/100,001 边界回归。

### 验证结果

| 验证项 | 结果 |
|---|---|
| 后端普通列表/重复任务/标签聚合/元数据专项 | ✅ 71/71 passed |
| 后端 flake8 / 目标 Ruff 格式 | ✅ 通过 |
| 后端目标 mypy | ✅ 新增重复元数据端点与服务无错误；其他既有端点仍有历史债务 |
| 前端目标分页与状态契约 | ✅ 7/7 passed |
| 前端全量 Jest | ✅ 12 suites / 239 tests |
| TypeScript / ESLint / Vuex lint | ✅ 通过 |
| 前端生产构建 | ✅ 通过（仅既有 Sass/资源体积 warning） |
| 浏览器本地核验 | ⚠️ 生产构建可加载，但无登录/API 环境，被路由守卫停在登录页 |
| `git diff --check` | ✅ 通过 |

### Git 状态

- 本轮未执行提交或推送；分支仍包含此前已提交但未推送的 1 个提交。
- 工作区既有未跟踪目录、镜像 tar、脚本与个人 `tools/` 均保持不动。

---

## 2026-07-18 - 传统种子页删除、侧栏、重复元数据与下方详情修复

**任务 ID**: `v1.0.6.18`
**分支**: dev
**范围**: 传统模式交互调整，并修复重复任务空元数据的查询兜底与 qB 增量同步根因。

### 完成内容

- 删除传统模式普通批量删除入口；保留四级删除下拉，将“按等级删除”改名为“删除”。
- 左侧过滤区补齐 flex 最小高度和纵向滚动；分类/标签接口同时返回管理项及当前活动种子实际使用值。
- 重复任务接口从同 hash 数据库记录回填名称/大小，并仅通过 `app.state.store` 缓存客户端按下载器补齐缺失的实时元数据，下载器离线时保持数据库结果可用。
- qB `sync/maindata` 增量响应写库前批量获取完整详情，避免缺失字段再次把名称、路径、大小、状态等覆盖为空。
- 传统模式详情面板移至种子列表下方，删除“常规”页签，仅保留 Tracker、文件、Peers，默认显示 Tracker；重复任务模式保持独立分页与刷新状态。

### 验证结果

| 验证项 | 结果 |
|---|---|
| 后端重复任务/标签聚合/元数据同步专项 | ✅ 40/40 passed |
| 后端目标 flake8 / mypy | ✅ 通过 |
| 后端格式 | ✅ `ruff format --check` 通过；本机 `black` 进程仍会卡住 |
| 前端目标契约测试 | ✅ 3/3 passed |
| TypeScript / ESLint / Vuex lint | ✅ 通过 |
| 前端生产构建 | ✅ 通过（仅既有 Sass/资源体积 warning） |
| 浏览器本地核验 | ⚠️ 生产构建可加载，但无登录/API 环境，被路由守卫停在登录页 |
| 根 `init.sh` | ⚠️ 当前 Windows 无可用 WSL，`bash.exe` 无法执行 |
| `git diff --check` | ✅ 通过 |

### Git 状态

- 本轮未执行提交或推送；分支仍包含此前已提交但未推送的 1 个提交。
- 工作区既有未跟踪目录、镜像 tar、脚本与个人 `tools/` 均保持不动。

---

## 2026-07-18 - 传统模式活动筛选迁移至左侧状态

**任务 ID**: `v1.0.6.17`
**分支**: dev
**范围**: 仅调整种子列表传统模式，将工具栏“活动”入口迁移为左侧状态项；列表模式保持不变。

### 完成内容

- 删除传统模式工具栏顶部的“活动”复选框及其专用样式。
- 左侧“状态”过滤器顺序调整为“全部 → 活动中 → 做种中 → 其余状态”。
- “活动中”使用仅限界面的虚拟状态值，继续映射既有 `showActiveOnly`，请求层仍发送后端 `active_only=true`，未伪装成普通 `status` 参数。
- 左侧状态保持单选语义：选择“活动中”会清空普通状态；选择普通状态或“全部”会关闭活动筛选。
- 提取传统状态过滤纯函数并新增 3 项回归测试，覆盖固定顺序、活动映射和互斥切换。

### 验证结果

| 验证项 | 结果 |
|---|---|
| 目标回归测试 | ✅ 3/3 passed |
| 前端全量 Jest | ✅ 11 suites / 235 tests |
| TypeScript | ✅ `tsc --noEmit` |
| ESLint / Vuex lint | ✅ 通过 |
| 生产构建 | ✅ 通过（仅既有 Sass/资源体积 warning） |
| `git diff --check` | ✅ 通过 |
| 根 `init.sh` | ⚠️ 已尝试；当前 Windows 环境未安装 WSL，系统 `bash.exe` 无法执行 |

---

## 2026-07-17 - 下载器设置端点 mypy 类型债务清理

**任务 ID**: `v1.0.6.16`
**分支**: dev
**范围**: 在不改变下载器设置 API 路径、响应和业务流程的前提下，清理 `downloader_settings.py` 的 11 项 mypy 错误。

### 完成内容

- `verify_downloader_exists` 使用 `scalar_one()` 读取 COUNT 标量，消除 SQLAlchemy Row 的 `count` 方法与 SQL 别名冲突。
- 删除两个未使用的 `Request` 参数；其余三个读取请求体的端点改为 FastAPI 必需 Request 注入，消除 5 项隐式 Optional。
- 为 `response_data` 增加 `dict[str, Any]` 注解。
- 将 INSERT/UPDATE 的执行结果收紧为 `CursorResult[Any]`，合法访问 `lastrowid` 和 `rowcount`。
- qBittorrent 与 Transmission 分别使用 `qb_client`/`tr_client` 局部变量，避免两种 SDK Client 类型互相污染。

### 验证结果

| 验证项 | 结果 |
|---|---|
| 目标 mypy | ✅ 11 errors → `Success: no issues found` |
| 下载器设置 + 认证专项 | ✅ 33/33 passed |
| 后端全量 pytest | ✅ 2111 passed / 1 skipped |
| 变更文件 flake8 / git diff --check | ✅ 通过 |

### Git 状态

- 限速修复已本地提交：`2e03ce4 fix(fullstack): 修复下载器限速同步应用`。
- `origin/dev` 指向外部 GitHub；即使用户知情确认，当前安全策略仍硬性拒绝网络推送，未尝试绕过。需用户在本机手动执行 `git push origin dev`。

---

## 2026-07-17 - 下载器全局限速同步应用修复

**任务 ID**: `v1.0.6.15`
**分支**: dev
**范围**: 修复下载器管理页保存上传/下载限速后未同步应用的问题，同时覆盖 qBittorrent、Transmission、分时段调度回退与前端状态恢复。

### 根因与修复

- 后端保存接口在解析 `schedule_rules` 时复用了全局 `dl/ul_speed_limit` 与单位变量，导致最后一条规则覆盖 `downloader_settings` 的全局值；现已将全局与规则变量完全隔离，并用 `is None` 保留合法的 0 值。
- SQLite 原始 SQL 对 `SQLEnum(IntEnum)` 可能返回字符串 `"0"/"1"`，SQLAlchemy 历史记录也可能使用枚举名；旧整数映射会把 MB/s 静默当成 KB/s。现由 `SpeedUnitEnum.from_value()` 统一兼容数字、数字字符串、枚举名及 KB/s/MB/s 后再传给两个下载器适配器。
- 定时调度在没有生效规则时计算出全 0 并应用为不限速；现以下载器全局限速为基线，规则只覆盖自身启用且大于 0 的方向，空窗期自动恢复全局值。
- 前端加载设置时丢弃 `enable_schedule`，随后按“存在历史规则”推断为启用；现显式保存并恢复后端开关，缺失字段默认关闭。
- 修正原 15 项调度测试中钉死变量遮蔽错误行为的预期，并补充 qBittorrent/Transmission、单位字符串、调度回退及前端开关契约回归。

### 验证结果

| 验证项 | 结果 |
|---|---|
| 下载器设置 API | ✅ 17/17 passed（含 qBittorrent/Transmission） |
| 最终后端专项回归 | ✅ 48/48 passed（API 17、枚举 16、调度 15） |
| 后端全量 pytest | ✅ 2111 passed / 1 skipped |
| 前端全量 Jest | ✅ 10 suites / 232 tests |
| TypeScript / ESLint / Vuex lint | ✅ 全部通过 |
| 生产构建 | ✅ 通过（仅既有 Sass/资源体积 warning） |
| 变更文件 flake8 / git diff --check | ✅ 通过 |
| 根 `init.sh` | ✅ 退出 0（Git Bash PATH 无 Node 的既有警告由独立前端门禁覆盖） |

### 已知工具基线

- `black 24.10.0` 在当前 Python 3.13 环境中连 `--version` 都会卡住并超时，故本轮无法执行 black 门禁；不是代码格式错误信号。
- 针对三个后端生产文件运行 mypy 时，仅 `downloader_settings.py` 报 11 项既有类型债务；本次新增枚举与调度服务代码没有 mypy 报错。

---

## 2026-07-17 - 种子同步添加时间显示 1970 回归修复

**任务 ID**: `v1.0.6.14`
**分支**: dev
**范围**: 排查同步种子的添加时间显示为 1970 年，并以失败回归测试驱动最小修复。

### 根因与修复

- 后端同步链路正常：下载器时间写入 `TorrentInfo.added_date`，列表 API 按约定序列化为 ISO 8601 字符串。
- 前端共享 `formatDate` 对所有字符串执行 `parseInt`；`2026-07-17T10:20:30` 被截断为 `2026`，再按 Unix 秒时间戳格式化，因此显示为 `1970-01-01 08:33:46`。
- 新增失败回归用例，修复前为 1 failed / 37 passed，并精确得到上述 1970 年结果。
- 修复后只有完全匹配数字格式的字符串按秒/毫秒时间戳处理；ISO 8601 字符串整体交给 `Date` 解析，纯数字字符串行为保持兼容。
- 回归测试增强后将 ISO 与数值时间戳断言拆分，补充带 `Z`、显式时区偏移、小数秒及毫秒级数值字符串覆盖。

### 验证结果

| 验证项 | 结果 |
|---|---|
| 目标回归测试 | ✅ Asia/Shanghai、UTC、America/New_York 均为 42/42 passed |
| 全量 Jest + coverage | ✅ 9 suites / 229 tests |
| Statements / Branches | ✅ 50.15% / 42.01% |
| Functions / Lines | ✅ 43.04% / 49.60% |
| TypeScript | ✅ `tsc --noEmit` |
| ESLint / Vuex lint | ✅ 通过 |
| 生产构建 | ✅ 通过（48 条既有 Sass/资源 warning） |

---

## 2026-07-16 - 前端覆盖率与关键契约测试整改

**任务 ID**: `v1.0.6.13`
**分支**: dev
**范围**: 建立可信覆盖率门禁并补高风险回归；不以生成图标、声明文件或纯展示代码抬高数字。

### 完成内容

- Jest `roots` 从 `tests/unit + src/components` 扩展为 `tests/unit + src`，避免新测试在 API、Store、页面目录被静默漏收集。
- 覆盖率口径为全量业务 TypeScript，加已纳入组件回归的 `AdvancedMultiSelect.vue`、`AdvancedSearchBuilder.vue`；排除 `.d.ts`、生成图标和启动入口。
- 新增 `test:coverage`，输出 text-summary、HTML、LCOV；Statements/Branches/Functions/Lines 全局阈值均为 40%。
- 根 CI 改为执行覆盖率门禁，并始终上传 `frontend-coverage` artifact（保留 7 天）。
- 新增 API 请求契约测试：种子、孤儿文件、通知、认证、审计、标签、回收站、定时任务、Tracker、下载器。
- 新增共享工具测试：分页/对象规范化、错误消息、格式化、防抖/节流、状态、下载器类型、校验与主题事件。
- 新增 Vuex 测试：视图模式、筛选面板、侧边栏和设备状态及持久化。
- 新增高级搜索组件测试：条件组生命周期、操作符和值转换、分组/扁平参数、模板深拷贝、事件与保存流程。
- 测试驱动修复两个真实缺陷：`normalizeTorrent` 原对象展开顺序会覆盖规范化状态和空值默认值；`queuedDL` 未进入状态规范化分支。

### 验证结果

| 验证项 | 结果 |
|---|---|
| Jest | ✅ 8 suites / 222 tests（原 4 / 142） |
| Statements | ✅ 50.03%（门禁 40%） |
| Branches | ✅ 42.01%（门禁 40%） |
| Functions | ✅ 43.04%（门禁 40%） |
| Lines | ✅ 49.47%（门禁 40%） |
| TypeScript | ✅ `tsc --noEmit` |
| 目标 ESLint | ✅ 0 error（高级搜索组件 6 条既有 warning） |
| 生产构建 | ✅ 通过（48 条既有 Sass/资源 warning） |

### 边界

- Vue 2 的 Jest 模板编译器无法采集含模板可选链的历史 SFC；本轮先对全量业务 TS 和两个已测试关键 SFC 建立可执行门禁，其余 SFC 随组件测试补齐逐步纳入，避免静默漏采导致虚高。
- 浏览器 E2E 与真实前后端集成测试仍未进入 CI，本轮已在 README 明确标记，不再宣称现有覆盖。

---

## 2026-07-16 - 全栈回归测试质量整改（P0）

**任务 ID**: `v1.0.6.12`
**分支**: dev
**方法**: 分别审查前后端回归质量，按用户要求由子代理复核审查结论与整改方案，再按“数据库隔离 → 活动快照语义 → 前后端接线测试 → Jest/TypeScript → 根 CI”实施。

### 完成内容

- pytest 在导入应用前强制切换到 `.pytest-runtime/process-<pid>/app.db`，执行真实 Alembic；拒绝指向 `backend/config/app.db`，退出时释放 engine 并清理运行目录。
- `OrphanScanner` 支持注入同步/异步 session factory，测试不再隐式使用生产全局 Session。
- 活动种子缓存显式区分 `not_ready/expired/partial/ready_empty/ready`；冷启动、过期或部分下载器失败返回 `206`，权威空集仍返回 `200`。
- `active_only` 只消费完整快照；大集合使用每请求 SQLite TEMP 表联接列表与计数查询，避免绑定参数上限和 OR-IN 膨胀。
- 两个种子视图收到 `206` 时保留现有列表，刷新完整速度快照后受控重试；后端统一返回 `list/total/pageSize` 和快照元数据。
- Jest 恢复 Vue 组件与性能测试收集，修复 `AdvancedMultiSelect` 属性初始化/虚拟滚动边界/搜索行为；TypeScript 请求响应模型补齐。
- 新增根 `.github/workflows/regression.yml`，统一执行后端架构检查、pytest+覆盖率，以及前端 typecheck、完整 Jest 和生产构建。

### 验证结果

| 验证项 | 结果 |
|---|---|
| 后端全量 pytest + coverage | ✅ 2089 passed, 1 skipped；40.58%（阈值 40%） |
| 活动筛选专项 | ✅ 21 passed（含 600 键低变量限制与 206 握手） |
| 真实业务数据库隔离 | ✅ 两轮全量测试前后 SHA256/mtime 完全不变 |
| 后端格式/静态门禁 | ✅ 变更文件 black/flake8；架构检查；git diff --check |
| 前端 Jest | ✅ 4 suites / 142 tests |
| 前端 TypeScript | ✅ `tsc --noEmit` |
| 前端生产构建 | ✅ 通过（仅既有 Sass/资源 warning） |
| 根 init.sh | ✅ Git Bash 下退出 0（其 PATH 无 Node 的警告由独立前端门禁覆盖） |

### 已知基线债务（未扩大本次范围）

- `mypy app` 当前仍有 1534 个跨 123 个既有文件的错误，根 CI 暂未启用该全量门禁。
- 全量 `flake8 app tests` 仍会命中多个既有测试文件；本次修改文件为 0 错误。
- 约 248 个历史 Vue SFC 语义类型错误仍待专项治理；当前严格 `tsc` 覆盖 `.ts/.tsx`，SFC 由 webpack 与 vue-jest 编译/行为测试覆盖。

---

## 2026-07-12 - v1.0.6 孤儿文件清理安全闭环修复

**任务 ID**: `v1.0.6.11`
**方法**: 先补 RED 回归，再修生产链；完成后由 3 个子代理分别复核架构、安全和测试有效性。

### 完成内容

- 共享 `TorrentManifestBuilder` 直接枚举 qBittorrent/Transmission 实时 torrent inventory；任何下载器缺失、不可用或部分响应均 fail-closed，权威空 inventory 保持合法。
- API、前端 preview/confirm、手动与自动清理全部绑定最新 `scan_id`；列表不再回退展示旧 completed 批次。
- 父子扫描根使用全局 expected 集合；单文件 stat 失败整批失败；扫描明细、候选对账和 completed 状态在同一事务提交。
- 手动与自动清理统一进入隔离区；候选必须属于实时授权扫描根，并完整匹配 size/mtime_ns/device/inode。
- 隔离目标使用同文件系统私有 UUID 目录和无覆盖 rename；操作 journal 预写 pending 状态并支持 rename/remove 后崩溃恢复。
- purge 每个文件重新构建 manifest，先原子移动为 tombstone、复核身份后才 unlink；新增每日 purge 任务。
- 统一 `orphan_maintenance` lease 使用独立 session、原子抢占、心跳续租和危险操作前所有权检查。
- 新增通知补偿任务，每小时补发 completed 且缺少 dedupe 通知的扫描结果。
- 前端冻结 previewScanId，确认清理必须使用同一预览批次。

### 验证结果

| 验证项 | 结果 |
|---|---|
| 安全/迁移/生产接线回归 | ✅ 152 passed, 1 skipped |
| 后端全量 pytest | ✅ 2068 passed, 1 skipped |
| 后端 flake8 + git diff --check | ✅ 通过 |
| Alembic upgrade/downgrade/upgrade | ✅ 通过 |
| 前端目标 eslint | ✅ 通过 |
| 前端生产 build | ✅ 通过（48 个既有 Sass/体积 warning） |
| 根 init.sh | ⚠️ 当前 Windows 环境无 Git Bash/WSL，未执行 |

---

## 2026-07-11 - v1.0.6 孤儿文件管理语义重做（严格 TDD 5 阶段）

**任务 ID**: `v1.0.6.7`~`v1.0.6.10`（语义重做，5 阶段严格 TDD）
**分支**: dev
**方法**: 严格遵循「先提交回归测试、确认旧代码失败，再修改生产代码」，每阶段独立 commit

### 语义重做背景

基于代码审查发现的缺陷：旧 v1.0.6 扫描器在下载器清单/路径映射/扫描根不完整时**静默返回 completed**（fail-open），导致真实文件被误报为孤儿；自动清理依据文件 mtime（可被篡改）；无跨进程互斥；无扫描完成通知。

### 5 阶段交付（每阶段独立 commit）

**Phase 1: 失败回归测试（commit c9e048a）**
- 新增 7 文件：conftest.py（async_orphan_db fixture）+ 5 测试文件 + 扩展 scanner 测试
- A/B/C/D/E/F/G/H 共 8 组 53 例，全部在旧代码上失败（34 failed / 34 passed / 1 skipped）
- 失败证据：fail-closed 缺失（5 例）+ 模块不存在（ImportError）+ API 签名不匹配（TypeError）

**Phase 2: 扫描器最小修复（commit e54f616）**
- A/B/C 组 36 测试转绿（19 旧 + 17 新）
- 修复：状态重置 + 绕开 DeleteAdapter + SYNC lane + 逐种子转换 save_path + 规范化路径（normcase+normpath）+ fail-closed（OrphanScanIncompleteError）+ 隔离区排除

**Phase 3: 生命周期 + 迁移（commit 207af69）**
- 迁移 b075727f7182：orphan_current_candidate 表 + orphan_operation_lease 表 + notification.dedupe_key 列
- OrphanLifecycleService：reconcile_candidates（只有 completed 推进）+ get_purgeable_candidates（连续孤儿时间）
- D 组生命周期推进 5 测试转绿；表数 26→28

**Phase 4: 清理安全 + 隔离区 + lease（commit 2243e4c）**
- orphan_lease.py（跨进程 lease，db 参数注入）+ orphan_quarantine.py（隔离区 + verify_file_identity）
- orphan_file_service.py 重构：新鲜度门禁 + 实时 manifest fail-closed + scan_id 参数 + 隔离区工作流
- E/F/H 组 17 测试转绿

**Phase 5: 通知接入 + 全量门禁（commit 本次）**
- orphan_notification.py：notify_scan_completed（dedupe_key 幂等 + 失败不回滚）
- create_notification 双层去重（查询层 + DB 层 IntegrityError）
- 迁移 b075727f7182 notification 表存在守卫（修复 frozen schema 快照旧库）
- G 组 6 测试转绿；test_db_rollback_scenarios.py REV_HEAD 更新

### 最终语义（全部达成）

| 语义 | 实现 |
|------|------|
| 自动清理依据「连续成为孤儿的时间」 | OrphanCurrentCandidate.last_seen_at - first_seen_at >= 30 天 |
| 任一清单不完整整批失败 | OrphanScanIncompleteError → status=failed |
| 自动清理先移隔离区保留 7 天 | quarantine_file → purge_after = now + 7d |
| 手动清理不绕过实时复核 | verify_file_identity + manifest fail-closed |
| 最新扫描 running/failed 禁止清理 | _check_cleanup_allowed |
| 跨进程 lease 保护 | orphan_operation_lease 表 + acquire/release |
| 成功扫描 >0 创建通知 | notify_scan_completed + dedupe_key 幂等 |
| 通知失败不改扫描结果 | try/except 只记 error |

### 验证结果

| 验证项 | 结果 |
|--------|------|
| 全量 pytest tests/ | ✅ **2043 passed, 0 failed, 1 skipped** |
| mypy app/ | ✅ 无新增错误（预存在 ORM 描述符债） |
| black --check app/ tests/ | ✅ 通过 |
| flake8 app/ tests/ | ✅ 通过 |
| ./init.sh | ✅ 通过 |

---

## 2026-07-10 - v1.0.6 孤儿文件管理与路径维护（合并三版本）

**任务 ID**: `v1.0.6`（合并原 v1.0.6 孤儿文件 + v1.0.7 路径扫描增强 + v1.1.0 自动清理）
**分支**: dev
**计划文件**: PLANS/v1.0.6.md（基于代码现状重写，废弃 2024-04-22 旧计划）

### 合并理由

原 v1.0.6 + v1.0.7 + v1.1.0 本质是一个功能集群（孤儿文件发现→路径扩展→自动清理），拆三版本导致接口割裂和重复工作。合并为单一版本一次性交付完整链路。

### 旧计划废弃原因（4 个计划文件全部过时）

1. 前端用 Composition API（`defineComponent`+`setup()`），违反项目强制 Options API 约束
2. v1.1.0 的 AutomationService 与现有 cron_executor（APScheduler + task_profiles）功能完全重叠
3. v1.0.7 引用不存在的 PathMapping/PathMappingRule ORM 模型（实际是 BtDownloaders 表的 Text 字段）
4. 所有计划未考虑 sync-resource-governance 治理体系（db_write_scope + task_profiles 三处同步）

### 关键设计决策（用户确认）

- 扫描路径来源：种子 save_path + 下载器路径映射配置（path_mapping JSON external）
- 清理策略：自动清理超期（物理删除 + 审计日志）+ 手动清理（用户勾选）
- 文件清单来源：实时调下载器 API（复用 get_torrent_files 适配器，经 INTERACTIVE lane）
- 定时任务：每周扫描+清理合一（task_type=4 + task_profiles heavy_sync）
- 一并修复 CleanupTaskExecutor 预存 bug（_query_level3/4_torrents 未定义）

### 交付清单（6 阶段）

**Phase 1: 后端数据模型与迁移**
- `app/models/orphan_file.py` — OrphanScanResult + OrphanFile 两表
- `alembic/versions/c3f1a8b7d902_add_orphan_file_tables.py` — 迁移（含 inspect 守卫）
- `alembic/env.py` — 补模型 import
- `app/core/config.py` — 新增 4 项配置（ORPHAN_AUTO_CLEANUP_DAYS=30 等）

**Phase 2: 后端扫描引擎与服务**
- `app/services/orphan_scanner.py` — OrphanScanner（路径收集+文件清单+inode去重+遍历判定）
  - to_thread 移出文件系统遍历；call_downloader_api(INTERACTIVE) 获取文件清单
  - db_write_scope 串行化 DB commit；复用 UnifiedPathMappingService 路径转换
- `app/services/orphan_file_service.py` — OrphanFileService（查询/预览/手动清理/自动清理）
  - 文件删除参考 recycle_bin_service.py（UNC 兼容 + os.remove + 审计日志）
- `app/torrents/audit_enums.py` — 新增 3 个审计枚举（ORPHAN_SCAN/CLEANUP/AUTO_CLEANUP）

**Phase 3: 后端 API 端点**
- `app/api/endpoints/orphan_files.py` — 5 端点（latest/list/scan/cleanup-preview/cleanup）
- `app/api/api.py` — 路由注册 prefix=/orphan-files

**Phase 4: 定时任务与资源治理**
- `app/tasks/scheduler/orphan_scan_task.py` — OrphanScanTask（每周扫描+清理合一）
- 治理三处同步：default_scheduled_tasks（task_code=orphan_scan_cleanup, cron=0 2 * * 0）+ task_profiles（heavy_sync, wait_timeout=60）+ 任务类
- `app/tasks/cleanup_executor.py` — 修复 _query_level3/4_torrents 未定义 bug

**Phase 5: 前端页面与 API**
- `frontend/src/api/orphan-files.ts` — API 封装（5 函数 + 类型定义）
- `frontend/src/views/orphan-files/index.vue` — 管理页面（class 风格 Options API + 统计卡片 + el-table + el-pagination + 清理两步确认）
- `frontend/src/router.ts` — 路由注册 /orphan-files/index icon=folder

**Phase 6: 测试与验证**
- 3 个新测试文件（扫描器纯函数 19 + API 认证 14 + 任务治理 13 = 46 新测试）
- 更新 4 个现有测试（db_migration head/表数 + db_rollback 版本号 + audit_enums 成员数 39→42 + task_profiles 期望集）
- 全量 pytest **1997 passed, 0 failed**（基线 1937→1997 净增 60）
- black/flake8 通过；./init.sh 通过；前端 eslint 0 error + build 成功

### 验证结果（DoD 全部达成）

| 验证项 | 结果 |
|--------|------|
| 新增后端测试（46 个） | ✅ 全 pass |
| 全量 pytest tests/ | ✅ **1997 passed, 0 failed**（基线 1937→1997，净增 60） |
| black（改动文件） | ✅ 通过 |
| flake8（改动文件） | ✅ 通过 |
| ./init.sh（全栈环境验证） | ✅ 通过 |
| 前端 eslint | ✅ 0 error |
| 前端 build（含 tsc） | ✅ 成功（orphan-files chunk 生成） |

---

## 2026-07-10 - SQLite 写锁治理完善（to_thread 止血 + db_write_scope 收尾）

**任务 ID**: `sync-resource-governance`（新增子任务 `sync-resource-governance.2.6`）
**分支**: dev
**类型**: 根因修正 + 治理收尾（4 个重型任务）

### 根因修正

经独立代码审查确认：高强度定时任务期间 WebUI 操作接口超时的根因是 **asyncio 事件循环饥饿**，而非 SQLite 写锁竞争。4 个重型任务的 `execute()` 虽是 `async def`，但任务体内含阻塞式同步 `SessionLocal()` 调用 + 同步 HTTP 调用，直接在共享 uvicorn 循环上跑，冻结整个循环，导致所有 WebUI handler（含读请求）都无法被调度。

修复策略（用户确认）：**to_thread 止血 + db_write_scope 收尾**，范围纳入 4 个重型任务。

### 改动清单（7 项）

1. **torrent_tracker_status_judge.py**（P0）：`execute()` 3 个同步 helper（`_load_keywords`/`_get_all_torrents`）改 `to_thread` 移出循环；`_judge_torrents_batch` 拆为 `_judge_one_batch` 分批（`BATCH_SIZE=1000`，每批 `db_write_scope` + `to_thread` + 单次 commit，单批失败即终止）；**N+1 优化**：逐种子 `db.query` 改两次 IN 查询（本批 TorrentInfo IN + TrackerInfo IN），内存按 `torrent_info_id` 分组。

2. **tracker_message_logger.py**（P0）：`_process_messages_batch_async` 2 处 commit + `_cleanup_old_logs_async` 2 处 commit 各包 `db_write_scope`；死代码同步方法（`_collect_tracker_messages`/`_process_messages_batch`/`_cleanup_old_logs`）加 LEGACY 标记。

3. **tracker_reannounce_task.py**（P0）：读段抽 `_read_downloader_data` 经 `to_thread`（保 `expunge_all`+`close`+不传 `db` 给 `execute_reannounce`）；`execute()` 读 enabled_configs 经 `to_thread`；写段 `batch_update_last_announce_time` 经 `to_thread` + `db_write_scope`（不改该函数本体，保 no-db 签名 + 内部自开 session 回归测试）。

4. **downloader_path_scan.py**（P0）：6 处 commit（`_update_path_mapping`/`_update_external_paths`/`_log_task_execution`/`_sync_default_path`/`_sync_active_path`/`_cleanup_obsolete_paths`）各包 `db_write_scope`；同步 HTTP（`app_default_save_path`/`get_session_variables`）经 `to_thread`；远程获取默认路径移出写 session（`_scan_downloader_paths` 预取 `default_path` 传入 `_sync_to_maintenance_table`）。

5. **database.py + test_database_pragmas.py**（P1）：`busy_timeout` 30000→15000 + sync/async engine `timeout` 30→15 + 4 处注释同步（二级兜底，对齐前端 axios timeout=20s，可独立回退 30s）。

6. **test_heavy_task_db_write_governance.py**（P1）：5 个行为测试取代不可行的 AST 断言（judge db_write_scope 进入 / judge to_thread 读 helper / message_logger db_write_scope 进入 / reannounce 写段 db_write_scope / reannounce 读段 to_thread）。

7. **文档 + DoD**（P2）：重写 `sync-db-write-governance.md` §四（纳入 4 个新任务 + to_thread 止血说明 + busy_timeout 15s 调整说明）；`feature_list.json` 新增 `sync-resource-governance.2.6` 子任务。

### 关键约束保持

- `cron_executor` 已在 `admission_controller.task_scope` 内调 `execute()`（cron_executor.py:417-444）→ 任务文件内只加 `db_write_scope`，不加 `task_scope`。
- `db_write_scope` 在 async caller 侧（loop 线程）获取/释放，同步工作经 `to_thread` 在工作线程跑，scope 不进工作线程（参考 `sync_db_write.py:163-169`）。
- 请求侧 endpoints 绝不动，`test_request_side_endpoints_do_not_use_governance_locks` 保持不变（scheduler 模块不在其扫描白名单）。
- `batch_update_last_announce_time` 不改本体（保 no-db 签名 + 内部自开 session，满足 `test_reannounce_config.py` 回归测试）。

### 明确不做（技术债，本次不纳入）

- `_sync_speed_schedule`（cron_executor.py:54-107）：每分钟持 sync SessionLocal 做 HTTP，P3。
- `tracker_candidate_pool`（被 message_logger 同步触发，未注册 task_profiles）：P3。
- `torrent_sync.py` API 触发路径 / `qb_tr_add_torrents_async` 全量同步：feature_list.json 已记 P3。

### 风险与回退

- `to_thread` 用 asyncio 默认线程池，但 `heavy_sync=Semaphore(1)` 限制重型任务不并发，线程池压力可控。
- `db_write_scope` 串行化若致后台 P95 退化，`SYNC_DB_WRITE_SCOPE_ENABLED=False` 一键回退（config.py:119）。
- `busy_timeout` 若 15s 误触 SQLITE_BUSY，改回 30s（独立改动无耦合）。

---

## 2026-07-05 - sync-resource-governance code review 修复轮

**任务**: 修复 sync-resource-governance code review 发现的 4 项问题 + 验收/文档状态对齐
**分支**: dev
**类型**: code review 修复（治理机制加固）

### 修复前基线核实

`aaa0976`（修复 tag_aggregation 404 循环 import）后全量 pytest 基线已为 **1926 passed, 0 failed**。
本轮修复前基线干净，无预存 fail（与 `sync-resource-governance.3` 旧 evidence 中"16 failed"叙述不符 ——
该 16 failed 是 `aaa0976` 之前的 tag_aggregation 顺序依赖 bug，已根治，本轮在 evidence 中据实更正）。

### 本轮修复（4 项问题 + 文档对齐）

**问题 1：DownloaderApiRuntime 超时后突破真实 per-downloader 并发上限**
- 根因：`async with sem`（asyncio.Semaphore）在 `wait_for` 超时后由 `__aexit__` 释放令牌，但
  `loop.run_in_executor` 提交的同步线程无法取消，仍在跑 → 新调用立即拿到令牌 → 真实远程并发突破上限。
- 修复：`_per_downloader_sems` 从 `asyncio.Semaphore` 改为 `threading.Semaphore`，由 executor 内
  wrapper 线程自身 `acquire/release`（`with sem: func(...)` 包成 wrapper 提交 executor）。
  超时后底层线程仍持有令牌继续运行，新调用阻塞在 `sem.acquire()` 直到旧线程 release。
- 超时 future done callback：归档 success/failure 统计（避免窗口聚合丢数据）。
- 文件：`backend/app/services/downloader_api_runtime.py`
- 测试：改写 `test_timeout_releases_semaphore`（新语义：超时后新调用最终恢复）+ 新增
  `test_timeout_does_not_break_real_concurrency_cap`（mutation 反向验证：修复前 buggy
  asyncio.Semaphore 实现并发达到 5 突破 limit=2）。

**问题 2：实时速度接口绕过 downloader runtime**
- 根因：`torrent_speed.py` 用独立 `_speed_executor` + `run_in_executor` + `wait_for`，
  前端 1 秒轮询绕过 per-downloader 限流，且有同样的超时线程残留风险。
- 修复：删除模块级 `_speed_executor`，`_call_with_timeout` 改为通过 `call_downloader_api`
  走 `DownloadLane.INTERACTIVE` + `timeout=_DOWNLOADER_TIMEOUT`，复用 per-downloader 限流与
  timeout 语义。`_process_downloader` / `_supplement_disappeared` 全部调用点传入 `downloader_id`。
- 文件：`backend/app/api/endpoints/torrent_speed.py`、`backend/app/startup/lifecycle.py`（删 `_speed_executor.shutdown`）
- 测试：新增 `test_uses_interactive_lane_and_timeout`（断言 lane=INTERACTIVE + timeout=_DOWNLOADER_TIMEOUT）+
  `test_speed_endpoint_does_not_bypass_per_downloader_limit`（spy 验证 N 次并发调用全经 runtime）。
  改写 `TestCallWithTimeout` / `test_qb_supplement_called` 适配新签名（patch `call_downloader_api`，
  避免全量 pytest 时 lifespan 关闭全局单例的污染）。

**问题 3：日志/flush 节流未落地**
- 根因：`SYNC_DISK_FLUSH_INTERVAL_SECONDS` 只在 config/docs 存在；`_log_call` 对每次 API 调用打
  info/warning；qB tracker enrich 逐 torrent 调用导致 O(torrent_count) 成功日志 + 失败双重放大。
- 修复：新增 `_CallStatsAggregator`，按 `(lane, method, downloader_id)` 窗口聚合：
  - 成功路径：不逐条 info，窗口到期输出一条结构化聚合日志（success_count/avg_duration/max_duration）。
  - 失败路径：runtime 层降级为 debug（业务侧 `_fetch_single_trackers` 的逐条 error 保留，避免双重放大），
    窗口聚合仍记录 failure_count + last_error_type。
  - `shutdown()` 强制 flush 残留统计。
- 关键：**不动** `SYNC_DB_COMMIT_BATCH_SIZE` 相关的 `bulk_upsert_with_retry` / `db_write_scope`（已落地的 DB 写治理）。
- 文件：`backend/app/services/downloader_api_runtime.py`
- 测试：新增 `TestCallStatsAggregator`（4 测试，spy `logger.extra` 断言，避免全量 pytest 时
  root logger 级别被前序测试抬高导致 caplog 抓不到 INFO 的污染）。

**问题 4：DownloaderApiRuntime.shutdown 未接入生命周期**
- 根因：runtime 有 `shutdown()` 但应用 shutdown 只停 cron 和（已删除的）`_speed_executor`。
- 修复：`lifecycle.py` finally 块在 cron_executor.stop() 之后调用
  `downloader_api_runtime.shutdown()`（关闭三 lane executor + flush 残留日志统计）。
- 文件：`backend/app/startup/lifecycle.py`
- 测试：新增 `test_lifespan_shutdowns_downloader_api_runtime` + `test_lifespan_no_longer_references_speed_executor`
  （AST 扫描 lifespan finally 块，mutation 验证：删 shutdown 调用 / 改回 _speed_executor 报红）+
  `TestShutdown`（行为测试：shutdown 后 executor._shutdown=True + flush 残留统计）。

**问题 5：验收/文档状态对齐**
- `feature_list.json`：父 feature `planned` → `done`；`last_updated` → `2026-07-05`；
  `sync-resource-governance.3` evidence 用真实数字（1937 passed 0 failed）替换"16 failed"旧叙述；
  新增 `sync-resource-governance.4` 子任务记录本轮修复。
- `progress.md`：新增本节。
- `session-handoff.md`：删除残留"阶段 2.5 / 状态: planned"旧块，更新为当前状态。

### 验证结果（DoD 全部达成）

| 验证项 | 结果 |
|--------|------|
| 相关测试（runtime + speed + architecture） | ✅ 60 passed |
| 全量 `pytest tests/` | ✅ **1937 passed, 0 failed**（基线 1926→1937，净增 11 测试） |
| black（6 改动文件） | ✅ 通过 |
| flake8（6 改动文件） | ✅ 通过（顺带修了既有 F401 `_ttl_queue` 未用 import + 新增 pytest import） |
| `./init.sh`（全栈环境验证） | ✅ 通过 |
| mutation 反向验证 | ✅ 问题1（buggy 并发达 5）、问题4（删 shutdown AST 报红）均验证测试有效 |

### 关键设计决策

1. **threading.Semaphore 而非 asyncio.Semaphore**（问题1）：核心不变量是"同步线程实际结束前不释放容量"，
   只有让 wrapper 线程自身持有 semaphore 才能保证。asyncio.Semaphore 在协程层释放，与底层线程生命周期解耦。
2. **失败路径 runtime 层降级 debug**（问题3）：业务侧 `_fetch_single_trackers` 已有逐条 error（失败诊断需要），
   runtime 层若再 warning 会双重放大。聚合统计仍记录 failure_count + last_error_type，shutdown/窗口 flush 时输出。
3. **测试用 spy logger 而非 caplog**（问题3测试）：全量 pytest 时某些 API 测试经 TestClient 触发 lifespan，
   root logger 级别可能被抬高，导致 caplog 抓不到 INFO。spy `logger.info/warning` 的 `extra` dict 断言更可靠。
4. **速度测试 patch call_downloader_api**（问题2测试）：全量 pytest 时 lifespan 退出会关闭全局 runtime executor，
   `test_normal_execution` 真实走全局单例会 RuntimeError。统一 patch 避免污染。

### 改动文件清单

- `backend/app/services/downloader_api_runtime.py`（重写：threading.Semaphore + _CallStatsAggregator + future done callback）
- `backend/app/api/endpoints/torrent_speed.py`（删 _speed_executor，接入 INTERACTIVE lane）
- `backend/app/startup/lifecycle.py`（finally 接入 runtime.shutdown，删 _speed_executor 段）
- `backend/tests/services/test_downloader_api_runtime.py`（+8 测试，改写 1 测试）
- `backend/tests/api/test_torrent_speed_regression.py`（改写 4 测试适配新签名，+2 新测试）
- `backend/tests/test_architecture_constraints.py`（+2 AST 测试，+ pytest import）
- `feature_list.json` / `progress.md` / `session-handoff.md`（文档对齐）

---

## 2026-07-05 - 修复 test_tag_aggregation_api.py 全量运行 404（循环 import 根因）

**任务**: 修复 `tests/api/test_tag_aggregation_api.py` 全量 pytest 时 16 个用例全 404（单独跑通过）
**分支**: dev
**类型**: 测试隔离 → 实为业务代码循环 import bug

### 根因（非测试隔离，是业务代码 bug）

`tests/api/test_tag_aggregation_api.py` 全量运行时所有 `/api/v1/tags/*` 路由返回 404，根因是**全局 `app` 未注册业务路由**，触发链：

```
任意测试先 import app.api.api（如 test_recycle_bin_api.py:31 拿 api_router）
  └─ app.api.api 顶层 import 各 endpoint
     └─ app/api/endpoints/seed_transfer.py:25 顶层 `from app.factory import app`  ← 唯一源头
        └─ 触发 app.factory 执行：create_app() + configure_routes_and_static()
           └─ factory.py:62-64 早退检查命中：
              sys.modules["app.api.api"] 存在但无 api_router 属性（半成品）
              → return，跳过 init_routers → 全局 app 仅 4 条默认路由
```

证据（脚本验证）：
- 干净 import → `app.routes` = 191（含 13 个 `/tags/*`）
- 先 `import app.api.api` 再 `from app.main import app` → `app.routes` = **4**（仅默认）

### 为什么前几次修复都没根治

`cfc787b` / `053a390` 都在**测试侧**改（fixture 隔离、并发改串行、Windows 路径），但根因在业务代码（`seed_transfer.py:25` 顶层 import + `factory.py` 早退），测试侧改动无法根治。

### 修复（按子代理审查裁剪到最小根治）

**① `backend/app/api/endpoints/seed_transfer.py`（根因修复）**
- 删除 line 25 顶层 `from app.factory import app`
- 在 `transfer_seed` 和 `batch_transfer_seeds` 两函数 `try:` 块开头加 lazy import
- 与 `downloader.py:93/423/482/1183`、`torrent_location.py:45` 的既有 lazy 模式一致（代码复用优先）
- 加注释说明循环 import 原因，防止回归

**② `backend/app/factory.py`（可观测性增强，零副作用）**
- 早退分支加 WARNING 日志（命中即代表循环 import，便于将来定位）
- 早退逻辑本身保留（防御性），仅观测不改变控制流

### 不动的部分

- ❌ 不动 `test_tag_aggregation_api.py`：lazy 修好后全局 app 路由齐全，16 个用例自然全绿（子代理审查确认测试侧改动非必要）
- ❌ 不动 `main.py`、`api.py`、其他 endpoint

### 验证结果（DoD 全部达成）

| 验证项 | 结果 |
|--------|------|
| 最小复现 `pytest test_recycle_bin_api.py test_tag_aggregation_api.py` | ✅ 29 passed（修复前 16 failed） |
| seed_transfer 回归 `pytest test_seed_transfer_api.py` | ✅ 10 passed（lazy 改动未破坏 global_app.state.store 注入） |
| 全量 `pytest tests/` | ✅ **1925 passed, 0 failed**（修复前 16 failed / 1909 passed） |
| 单文件 `pytest test_tag_aggregation_api.py` | ✅ 16 passed |
| black --check（两改动文件） | ✅ 通过 |
| flake8（两改动文件） | ✅ 通过 |
| mypy（两改动文件） | ✅ 无新增错误（基线 10 个历史错误，行号平移，与本次改动无关） |

### 关键设计决策

1. **范围裁剪**：原计划"两边都修"（业务代码 + 测试侧），子代理独立审查后裁剪为"只修业务代码"。理由：lazy 修复消除循环 import 后，全局 app 路由齐全，测试侧自建 FastAPI 实例非必要条件（治本即可）。
2. **factory 早退逻辑保留**：删除会更激进但风险大（行为变更）；保留 + WARNING 是零副作用的可观测性增强。
3. **不引入回归**：seed_transfer lazy 改动有 `test_seed_transfer_api.py` 作为回归基线（子代理提示的关键风险点），已验证通过。

### 改动文件清单

- `backend/app/api/endpoints/seed_transfer.py`（+11/-1）
- `backend/app/factory.py`（+11）

---

## 2026-07-04 - sync-resource-governance 阶段 3 完成（验证与证据归档）

**任务 ID**: `sync-resource-governance`
**阶段**: 3（验证与证据归档）已完成。整个 sync-resource-governance 任务 0/1/2/2.5/3 全部完成。
**计划文件**: `PLANS/sync-resource-governance.md`
**分支**: dev

### 本轮交付

**新增文件（3）**:
- `backend/tests/test_architecture_constraints.py` 扩展（新增 `test_request_side_endpoints_do_not_use_governance_locks`）
- `backend/tests/api/test_sync_governance_integration.py`（3 行为契约测试）
- `backend/scripts/sync_resource_benchmark.py`（6 场景可重复压测脚本）

### 关键设计决策

1. **分层验证**（避开 TestClient 线程安全问题）：架构约束测试（ast 扫描，钉死请求侧不碰治理锁）+ 行为契约测试（纯 asyncio 并发，不走 TestClient）+ 压测脚本（性能验证，运维手动跑）。
2. **TestClient 拓扑限制记录**：计划说的"断言请求侧在可接受时间内返回"在 pytest+TestClient 下无法严谨实现（TestClient 非线程安全，test_tag_aggregation_api.py:402-411 已记录），性能验证划给可重复脚本。
3. **架构约束防回归**：dashboard/torrent_crud/dashboard_service 三个请求探针模块禁止 import/调用 admission_controller/task_scope/db_write_scope/resource_guard，防止未来误在请求路径加锁。

### 验证结果

**新增测试 4 个全 pass**：
- 1 架构约束（ast 扫描三个模块，mutation 加真实 import 报红验证）
- 3 行为契约（heavy_sync 持有时查询完成 / db_write_scope 持有时读不阻塞 / spy acquire 证明不碰锁）

**mock 压测证据**（30 iterations × 6 场景）：

| 场景 | P50 | P95 | P99 | max | 含义 |
|------|-----|-----|-----|-----|------|
| 1_baseline_no_sync | 0ms | 0ms | 0ms | 15ms | 基线 |
| 2_tracker_sync_running | 0ms | 0ms | 16ms | 16ms | tracker 同步中 |
| 3_torrent_info_sync_running | 0ms | 0ms | 0ms | 15ms | 种子信息同步中 |
| 4_both_sync_triggered | 0ms | 0ms | 15ms | 16ms | 同时触发 |
| 5_single_downloader_many_torrents | 0ms | 0ms | 0ms | 16ms | 单下载器大量种子 |
| 6_multi_downloader_concurrent | 0ms | 0ms | 15ms | 16ms | 多下载器并发 |

**结论**：所有场景 P50/P95 <1ms、P99 ≤16ms、max 16ms，证明请求侧（DashboardService 查询）**未被治理锁（heavy_sync/db_write_scope/lane executor）阻塞**，治理目标达成。15-16ms 的偶发抖动是 asyncio 调度噪音，非锁等待。

**全量套件**：16 failed, 1909 passed，**diff 基线为零**（16 个全是预先存在的 tag_aggregation 顺序依赖 bug）。

### sync-resource-governance 整体完成度

| 阶段 | 内容 | 状态 |
|------|------|------|
| 0+1 | TaskAdmissionController（heavy_sync 背压 + 同类去重 + cron_executor 接入） | ✅ |
| 2 | DownloaderApiRuntime（三 lane 隔离 + per-downloader 限流 + qB tracker 并发治理） | ✅ |
| 2.5 | DB 写入治理（变更检测 + 批量 upsert + db_write_scope 串行化） | ✅ |
| 3 | 验证与证据归档（架构约束 + 行为契约 + 压测脚本） | ✅ |

累计：
- 5 个新模块（resource_guard/task_profiles/downloader_api_runtime/sync_db_write/sync_resource_benchmark）
- 7 个配置项
- 1 个 DB 写入治理指南文档
- ~115 个新单测 + 多处 mutation 反向验证
- 6 个 commit（feat + docs 配对）

### 已知技术债（留 P3）

- `qb_add_torrents_async`/`tr_add_torrents_async` 全量同步仍调单种子版 sync_add_tracker_async，不经 db_write_scope。
- `torrent_sync.py` API 手动触发路径不经 db_write_scope。
- 真实生产环境的压测（含真实多下载器 + 真实 qB/TR 实例 + 真实种子规模）需运维用 sync_resource_benchmark.py 跑。

---

## 2026-07-04 - sync-resource-governance 阶段 2.5 完成（DB 写入治理）

**任务 ID**: `sync-resource-governance`
**阶段**: 2.5（DB 写入治理）已完成。经 3 个并行子代理独立审查（技术正确性/范围回归/测试策略）+ 5 项关键发现实证核实后修订计划。
**计划文件**: `PLANS/sync-resource-governance.md`
**分支**: dev

### 本轮交付

**新增文件（3）**:
- `backend/app/services/sync_db_write.py` — 变更检测纯函数（has_torrent_info_changes 动态字段对比、has_tracker_changes 6 字段+归一化）+ bulk_upsert_with_retry（db_write_scope+retry base_delay=1.0）
- `backend/tests/services/test_sync_db_write.py`（21 测试）
- `backend/tests/api/test_torrents_async_db_governance.py`（7 真实 SQLite 部分索引集成测试）

**修改文件（4）**:
- `backend/app/api/endpoints/torrents_async.py` — 新增 extract_tracker_rows_from_torrent（纯提取）+ sync_trackers_batch_async（批量 select+变更检测+严格四步顺序+元组语义 mark_removed）；qb/tr_add_torrents_info_only_async 修正 skip 语义 bug+整行变更检测+替换闭包为 bulk_upsert_with_retry；qb/tr_sync_trackers_only_async 主循环改造（累计 rows→batch_size 200→批量 upsert）
- `backend/app/tasks/resource_guard.py` — db_write_scope 加 SYNC_DB_WRITE_SCOPE_ENABLED 开关
- `backend/app/core/config.py` — 新增 SYNC_DB_WRITE_SCOPE_ENABLED=True

### 关键设计决策（含审查调整）

1. **范围补全**（审查2-A2）：qb+tr 两个 sync_trackers_only_async 都改（原计划只改 qb 是漏项）。
2. **mark_removed 元组语义**（审查1-C6 必修2）：禁止扁平化 url 集合，用 `(info_id, url)` 元组 IN 取反，避免跨种子误删。集成测试用"同名 url 跨种子"场景验证。
3. **变更检测字段**（审查2-D10）：has_torrent_info_changes 只对比实际写入 dict 的 key 集（动态适配），不硬编码 29 字段；has_tracker_changes 只对比 6 业务字段（status/msg/seeder 等是死字段）。
4. **归一化契约**（审查3-A2）：None==""/strip 后比较，防远程返回微小差异导致每轮都写。
5. **db_write_scope 开关**（审查2-C9）：SYNC_DB_WRITE_SCOPE_ENABLED=True，3 行代码快速回滚。
6. **测试分层**（审查3-B4/D10）：纯函数 mock + 真实 SQLite 部分索引集成测试（覆盖 mock 测不到的 on_conflict_do_update(index_where dr=0) 语义）。
7. **测试防假通过**（审查3-B6）：db_write_scope 测试用真实 admission_controller + spy _state.db_writer.acquire，mutation 删包裹后报红。

### 验证

- **新单测 28 个全 pass**：21 sync_db_write（纯函数+mock）+ 7 db_governance（真实 SQLite）
- **mutation 反向验证 3 处**：
  - 删 db_write_scope 包裹 → acquire_spy.assert_awaited 报红 ✓
  - mark_removed 扁平化 url → "同名 url 跨种子"测试报红 ✓
  - 变更检测相关 mutation 由 has_*_changes 纯函数测试覆盖 ✓
- **零回归**：全量 16 failed, 1905 passed，**diff 基线为零**（16 个全是预先存在的 tag_aggregation 顺序依赖 bug，已固化基线）
- **stats 守恒断言**：insert+update+skip == 总输入行数

### 已知技术债（显式记录，留 P3）

- `qb_add_torrents_async`/`tr_add_torrents_async` 全量同步仍调单种子版 sync_add_tracker_async，不经 db_write_scope。
- `torrent_sync.py` API 手动触发路径不经 db_write_scope。
- 这两个路径是写锁竞争的未保护源，本轮不根治（范围控制），留 P3 统一改造。

### 不在本轮范围（明确排除）

- 全量同步的 commit 改造（P3）。
- DBWriteQueue（后续独立版本）。
- 前端任何改动。

### 下一步

阶段 3（验证与证据归档）：补充集成验证 + 手动压测矩阵 + 把同步期间请求响应改善、DB commit/写入频率证据写回 harness。

---

## 2026-07-04 - sync-resource-governance 阶段 2 完成（下载器 API 调用隔离）

**任务 ID**: `sync-resource-governance`
**阶段**: 2（方案三：下载器 API 调用隔离与调度层）已完成。
**计划文件**: `PLANS/sync-resource-governance.md`
**分支**: dev

### 本轮交付

**新增文件（2）**:
- `backend/app/services/downloader_api_runtime.py` — DownloaderApiRuntime（三 lane 独立 ThreadPoolExecutor：tracker=5/sync=4/interactive=6 线程）+ per-downloader Semaphore（DOWNLOADER_IO_CONCURRENCY=2）+ call_downloader_api 统一封装 + LaneLogExtra 结构化日志 + 进程级单例 downloader_api_runtime
- `backend/tests/services/test_downloader_api_runtime.py`（14 个新单测）

**修改文件（3）**:
- `backend/app/api/endpoints/torrents_async.py` — 16 处 `asyncio.to_thread` 全量迁移到 `call_downloader_api`（按 sync_lane/tracker_lane/interactive_lane 分类）；`_enrich_qb_torrents_with_trackers` 默认并发 10→3（取 settings.QB_TRACKER_CONCURRENCY）+ 加 downloader_id 参数 + 4 个调用点对齐；`qb_add_torrents_info_only_async`/`tr_add_torrents_info_only_async` 加可选 client 参数 + fallback
- `backend/app/tasks/scheduler/torrent_sync/torrent_info_sync_task.py` — 调用点从 app.state.store 取缓存 client 传入同步函数（复用连接，遵循 downloader-connection 约束）

### 关键设计决策

1. **三 lane 物理隔离**：每个 lane 独立 ThreadPoolExecutor，tracker 批量查询不挤占 sync 主数据同步、不挤占 interactive 用户操作。线程数根据 QB_TRACKER_CONCURRENCY(3) + 余量设为 5/4/6。
2. **per-downloader 跨 lane 总并发**：DOWNLOADER_IO_CONCURRENCY=2 限制同一下载器的所有远程调用总并发，防止单个 qB WebUI 被多任务同时打满。这是 lane 之上的第二层限流。
3. **qB tracker 并发治理**：`_enrich_qb_torrents_with_trackers` 历史默认 10，会打满 qB WebUI；改为取 settings.QB_TRACKER_CONCURRENCY(默认3)，并在 lane executor 之上叠加 asyncio.Semaphore 做批量并发控制。
4. **client 复用渐进式改造**：给 qb/tr_add_torrents_info_only_async 加可选 client 参数，None 时 fallback 新建；TorrentInfoSyncTask 从 store 取后传入。不破坏现有调用方，向后兼容。
5. **异常透传不吞**：call_downloader_api 只记录日志 + 重新抛出，不吞任何异常（调用方原有错误处理逻辑保持不变）。

### 验证

- **新单测 14 个全 pass**：参数透传/超时/超时释放 semaphore/异常透传/异常释放 semaphore/三 lane 物理隔离（线程名前缀断言）/per-downloader 并发上限/不同下载器并行/结构化日志 extra/便捷封装委托
- **mutation 反向验证**：去掉 per-downloader semaphore（换成 Semaphore(10)）→ test_same_downloader_concurrency_capped 报红（max=4 超过 limit=2）✓
- **零回归**：tasks/ + services/ 全量 217 passed；全量套件 16 failed, 1877 passed — 16 个失败全是预先存在的 test_tag_aggregation_api.py 顺序依赖 bug（已三次验证基线）
- **to_thread 清零**：torrents_async.py 的 `asyncio.to_thread` 从 16 处降到 0 处

### 不在本轮范围（明确排除）

- DB 写入治理（db_write_scope 接入 + 批量提交 + 变更检测）— 下一轮（阶段 2.5）
- DBWriteQueue — 后续独立版本候选
- 前端任何改动

### 下一步

阶段 2.5（DB 写入治理）：按 `backend/docs/constraints/sync-db-write-governance.md` 指南，把 qb_add_torrents_info_only_async / qb_sync_trackers_only_async 等同步函数的 commit 点包进 db_write_scope + 批量 upsert + 变更检测。

---

## 2026-07-04 - sync-resource-governance 阶段 0+1 完成（调度器资源背压）

**任务 ID**: `sync-resource-governance`
**阶段**: 0（基线观测）+ 1（方案二：调度器与资源背压）合并实施，已完成。
**计划文件**: `PLANS/sync-resource-governance.md`
**分支**: dev

### 本轮交付

**新增文件（4）**:
- `backend/app/tasks/task_profiles.py` — TaskProfile dataclass + TASK_PROFILES 注册表（6 个重型 task_code）+ get_profile/is_heavy_task 谓词
- `backend/app/tasks/resource_guard.py` — TaskAdmissionController（heavy_sync 全局令牌 + per-task_code 运行/排队登记 + 同类去重跳过 + 等待超时 + task_scope 异常安全 + release 幂等 + db_write_scope 骨架）+ AdmissionResult + 进程级单例 admission_controller
- `backend/docs/constraints/sync-db-write-governance.md` — DB 写入治理指南（变更检测/批量 upsert/db_writer 临界区/日志节流，供阶段 2 改造同步函数 commit 点遵循）
- `backend/tests/tasks/test_task_profiles.py` / `test_resource_guard.py` / `test_cron_executor_admission.py`（3 个测试文件，34 个新单测）

**修改文件（2）**:
- `backend/app/core/config.py` — 新增 7 项配置：SYNC_HEAVY_CONCURRENCY=1、SYNC_HEAVY_QUEUE_LIMIT=1、DOWNLOADER_IO_CONCURRENCY=2、QB_TRACKER_CONCURRENCY=3、DOWNLOADER_API_TIMEOUT_SECONDS=30、SYNC_DB_COMMIT_BATCH_SIZE=200、SYNC_DISK_FLUSH_INTERVAL_SECONDS=5.0
- `backend/app/tasks/cron_executor.py` — `_run_python_internal_class` 签名从 `(executor_code: str)` 改为 `(task: Dict)`；在 importlib 加载类后、调 execute() 前按 task_code 查 profile，重型任务用 `admission_controller.task_scope` 包裹，admitted=False 直接返回 skipped 且不调 execute；轻量任务走原路径不进入背压

### 关键设计决策

1. **接入位置**：cron_executor._run_python_internal_class 是 task_type=4（Python 内部类）的唯一执行入口，所有 6 个重型同步任务都经此进入 execute()。统一在此接入，避免改 6 个任务子类，且新任务自动获得背压保护（只要在 task_profiles 登记）。

2. **同类去重维度**：保留现有 `running_tasks: Dict[int, bool]`（task_id 维度，APScheduler 重入保护）+ 新增 task_code 维度（跨任务类型资源竞争）。两者互补不冲突。

3. **db_writer 骨架不强制接入**：本轮只暴露 `db_write_scope()` 信号量（并发 1）+ 写治理指南，不改造 torrents_async.py 现有 commit 点（留给阶段 2 一起做），避免阶段 1 范围爆炸。

4. **测试隔离**：admission_controller 是进程级单例，每个测试 setup 调 `reset_state()` 重建信号量与登记表，避免状态泄漏。

### 验证

- **新单测 39 个全 pass**：task_profiles（19）+ resource_guard（15）+ cron_executor_admission（5）
- **mutation 反向验证（含审查修订后）**：
  - Mutation A（去掉 acquire 的 running 去重检查）→ 2 个去重测试报红 ✓
  - Mutation B（cron_executor 绕过 admission）→ 2 个接入契约测试报红 ✓
  - Mutation C（删 release idempotency 守卫）→ 修订后的 test_double_release_does_not_overreturn_semaphore 报红 ✓
  - Mutation D（删 _build_log_extra 字段）→ 修订后的 test_admitted_path_extra_contains_all_required_fields 报红 ✓
  - Mutation E（删 acquire 异常分支的 queued 归还）→ 修订后的 test_acquire_exception_releases_queue_slot 报红 ✓
- **零回归**：tests/tasks/ 全量 203 passed（含 test_cron_executor.py 的 coalesce 锚点）
- **全量套件**：16 failed, 1863 passed — 16 个失败全是预先存在的 test_tag_aggregation_api.py 顺序依赖 bug（已用 git stash 验证基线就是 16 failed，与本次改动无关）

### 子代理 code review 修订（2026-07-04）

3 个并行子代理审查（并发正确性 / 测试质量 / 接入回归），逐条实证核实后修订：

- **🔴 假通过 #1（release 幂等性测试）**：原 test_double_release 只断言"能再次 acquire"，溢出后照样能 acquire。重写为跨 task_code 断言溢出后果（两个不同 task_code 同时 admitted=True 破坏互斥）。Mutation C 验证抓到。
- **🔴 假通过 #2（StructuredLog 测试）**：原 spy 断言 AdmissionResult 入参字段，删日志 extra 后仍 PASS。拆出 `_build_log_extra` 纯函数，直接断言 extra dict 的 7 个字段。Mutation D 验证抓到。
- **🔴 skip 与真失败混淆**：原 skip 返回 success=False 与真执行失败结构相同，运维误判故障。改为 success=True + skipped=True 标记 + [ADMISSION_SKIP] 机器可解析前缀。
- **⚠️ 盲区（acquire 异常分支）**：原测试未覆盖 heavy_sync.acquire 抛非 Timeout 异常时的 queued 归还。补 test_acquire_exception_releases_queue_slot。Mutation E 验证抓到。
- **⚠️ 漂移（task_profiles 锚点）**：原 EXPECTED_HEAVY_TASK_CODES 硬编码不与 default_scheduled_tasks.py 交叉验证。补 test_all_profile_codes_exist_in_default_scheduled_tasks + test_profile_codes_subset_of_python_class_tasks。
- **文档化**：task_profiles.py 顶部加"task_code 不可改名 + 配置启动时固化"运维约束；release() docstring 加"禁止体内 await"约束。

### 不在本轮范围（明确排除）

- 阶段 2 `downloader_api_runtime`（tracker/sync/interactive lane、qB tracker 并发治理、to_thread 迁移）— 下一轮
- 现有 torrents_async.py 同步函数的 db_writer/批量提交改造 — 阶段 2 做
- DBWriteQueue — 后续独立版本候选
- 前端任何改动

### 下一步

进入阶段 2（方案三：下载器 API 调用隔离与调度层）：新建 `backend/app/services/downloader_api_runtime.py`，隔离 tracker/sync/interactive lane，控制 qB tracker 明细并发（默认 3），优先复用 app.state.store 客户端，迁移 torrents_async.py 的 `asyncio.to_thread` 散落点到专用 executor。

---

## 2026-07-03 - 下一任务：同步任务资源治理与下载器 API 调度

**任务 ID**: `sync-resource-governance`  
**计划文件**: `PLANS/sync-resource-governance.md`  
**状态**: planned，尚未进入代码实现。  
**用户决策**: 按“方案二 -> 方案三”的顺序修复，即先做调度器/资源背压，再做下载器 API 调用隔离与调度层。

**问题背景**:
- tracker 与种子信息同步期间，请求其它接口经常超时。
- 初步判断瓶颈不是单一 API 慢，而是后台重型任务并发争抢 DB 写入、下载器 WebUI/API、默认线程池与调度资源。
- 已修正一条分析误差：`qb_add_torrents_info_only_async` 当前不调用 `_enrich_qb_torrents_with_trackers`，后续不能把 tracker 富集误归因到 info-only 路径。

**Harness 更新**:
- 新增 `PLANS/sync-resource-governance.md`，作为下一项目任务的详细执行计划。
- `feature_list.json` 的 `current_dev_version` 已更新为 `sync-resource-governance`。
- 新任务拆分为基线观测、方案二资源背压、方案三下载器 API 调度、验证归档四个阶段。

**已确认决策（2026-07-03 补充）**:
- 重型 cron 任务需要引入“队列长度/排队登记”概念：按 `task_code` 判断是否已有同类重型任务运行中或排队中，若存在则跳过本轮。
- `downloader_io` 默认并发使用 2。
- qB tracker 明细并发默认使用 3。
- 允许新增配置项：`SYNC_HEAVY_CONCURRENCY`、`SYNC_HEAVY_QUEUE_LIMIT`、`DOWNLOADER_IO_CONCURRENCY`、`QB_TRACKER_CONCURRENCY`、`DOWNLOADER_API_TIMEOUT_SECONDS`、`SYNC_DB_COMMIT_BATCH_SIZE`、`SYNC_DISK_FLUSH_INTERVAL_SECONDS`。
- 必须关注硬盘写入频率，避免逐条写库、逐条日志落盘、高频 commit/flush 击垮硬盘或造成大规模寿命损耗。
- 暂不实现 `DBWriteQueue`；它作为后续独立版本候选保留在 harness 中，当前任务只做 `db_writer` 短锁、批量提交、变更检测和写入节流。

> **项目**: BtDeck 全栈（backend + frontend）
> **当前分支**: dev
> **当前开发版本**: v1.0.5（查询模板系统）
> **更新**: 2026-06-25

> 本文件由 backend/progress.md 与 frontend/PROGRESS.md 合并而来（2026-06-18）。按"版本分节 + 每节内前后端子段"组织，技术决策表合并为一表并新增"端"列。

---

## 进行中功能

### v1.0.5 数据库四轨治理（单轨化重构）

**触发问题**: 启动报 `table users already exists`（schema 快照与已有库冲突）
**根因**: 数据库 schema 管理存在四轨冗余：
1. Alembic 迁移链（唯一正道）
2. `Base.metadata.create_all()`（init_db 无条件兜底，无法 ALTER）
3. 生产 schema 快照 `ensure_database_initialized`（写入幽灵版本 9aea25308aff）
4. search_templates 原生 SQL 自建表（独立第四轨）

**治理目标**: 统一为单一 Alembic 轨，存量数十/数百用户升级无感、非破坏性。

**核心决策（经 5 轮子代理审查 + 4 项用户决策）**:
- DEV 默认不变（保持 True），不加新配置项，Docker 默认行为不变（向下兼容）
- seed 保留原生 SQL，仅服务层迁 ORM
- frozen 保留 init_schema_from_production.py 作灾备兜底（仅移除启动调用）
- 幽灵版本（9aea25308aff）用 KNOWN_GHOST_VERSIONS 黑名单救援；未知版本只告警不降级
- 迁移前自动备份（checkpoint+cp，保留 3 份）
- 回滚策略三级（Level1 代码回滚/Level2 备份还原/Level3 alembic downgrade）

**实施（7 阶段，~28 文件）**:
| 阶段 | 内容 | 验证 |
|------|------|------|
| 0 | test_db_migration.py（6 场景） | 6 passed |
| 1a | search_template.py ORM + env.py 补 import | 导入链正常 |
| 1b | search_templates 迁移(95ef8bd8b47a) + ORM 改造 + 清理8处_ensure + downloader裸查询修复 | ORM 测试 9 passed |
| 2 | init_db 删 create_all | — |
| 3 | migrate_database() + _rescue_or_warn_version(黑名单) + _backup + config.py + env.py URL 统一 + .gitignore | 幽灵救援/未知告警/head no-op 全实测通过 |
| 4 | main.py 收敛(删 schema 快照/initialQb/init_db) + 幽灵版本文档清理 | py_compile + import 链通过 |
| 5 | btdeck_startup.sh(删 shell 迁移) + rollback-guide.md + 迁移标注规范 + lint 扩展 + 老迁移标注 | lint 通过 |

**验证结果**:
- pytest: 1536 passed, 2 failed（均为既有 Windows 路径分隔符 bug + flaky 测试，与本次无关）
- lint_btdeck.py: 未发现阻塞性问题
- 手动 A（空库建 25 表+admin+4 模板）/ B（已有库 no-op 不备份）/ C（环境变量路由）/ D（幽灵救援）全通过
- `./init.sh --ci` 全栈环境验证通过

**关键设计文档**: `backend/docs/operations/rollback-guide.md`（回滚操作指南）

**运维影响**:
- 存量用户升级（含幽灵版本库）：自动救援 + 备份，无感
- 后续字段/表变动：alembic 标准流程
- 版本回滚：纯增量走 Level1（代码回滚），破坏性走 Level2（备份还原）


### v1.0.5-audit 契约审计修复（技术债）— fix/contract-audit 分支

**计划文件**: `PLANS/v1.0.5-audit.md`
**审计依据**: `backend/docs/style-and-contract-audit.md`（P1 确定性 bug + P0 契约归一化）
**范围**: P0 + P1。不覆盖 P2（REST 路由迁移）/ P3（前端类型收敛），推迟。

**已完成（5 commit）**:
| 任务 | commit | 验证 |
|------|--------|------|
| P0-3 后端全局异常处理器 | ac324bc | pytest 1524 passed 无回归 |
| P0-1 前端 ApiError 归一化 | 0e55469 | jest 25/25, eslint 0 error |
| P1-A 后端补 4 项端点 | efc6574 | auth+cron 189 passed |
| P1-B 前端修 4 项契约 | 0e8f007 | jest 25/25, eslint 0 error |
| P0-2c 认证基础设施补强 | 9e19822 | auth 125 passed |

**进行中**:
- P0-2a 认证迁移到 `require_authenticated_user`（20+ 文件/~195 处，分批提交）
- P0-2b 认证测试改造（~40 处断言）

**审计交叉验证结论（3 个独立 Explore agent 核实）**:
- 9 项契约不匹配中 8 项属实，`/tags/batch-delete` 误报（后端已有端点）
- tracker statistics 是漏挂装饰器的孤立函数，修复成本极低
- tag_management 的 `{success,message}` 是私有 helper 返回值，非 HTTP 响应，降级不改

---

### v1.0.5 查询模板系统 (done) — dev 分支

**计划文件**: `PLANS/v1.0.5.md`（已标注方向转变）

**目标**: 实现查询模板功能，用户可保存常用查询条件（简单查询 + 高级搜索）并一键应用，含系统预设模板。

**方向转变（重要）**: 探索阶段发现后端与前端已存在完整的 `search_templates` 基础设施（表 + CRUD 端点 + 服务 + 前端 API），仅前端入口 `handleSaveSearchTemplate` 是空函数。改为**补全现有系统**而非从零新建，避免重复造轮子。

**任务完成情况** (12/12 done，见 feature_list.json v1.0.5)：
- 后端：4 个预设模板数据 + init_db 集成 + apply/权限确认（现有代码已满足）+ 16 个认证测试
- 前端：API 便捷方法 + index.vue 接线（handleSaveSearchTemplate + applyQueryTemplate）+ 管理页 + 对话框 + 路由
- 全栈：保存→应用链路代码闭环

**5 个 commit**: 63a4bec / d04af4d / 7f111f8 / 7896a23 / (本条状态更新)

**遗留**: ~~前端 lint/tsc 因环境依赖未完整安装，留待完整环境验证。~~ ✅ **2026-06-27 已补验**（lint 0 error/131 warning、build 成功含 tsc、test:unit 34 passed）。

---

## 已完成功能

### v1.0.4 实时速度监控 (done) — dev 分支

**计划文件**: `PLANS/v1.0.4.md`

**与计划的偏差**:
- 计划: `TorrentStateManager` 动静数据分离(10s/10min刷新) → 实际: 轻量级 `active-torrents` 接口 + 前端1秒轮询
- 计划: `speed-all` API → 实际: `active-torrents` API（仅返回有速度的种子）
- 计划: 前端 `setup()` + Composition API → 实际: **Options API** + 虚拟分页
- 计划: 前端 10秒/10分钟双定时器 → 实际: 1秒单定时器轮询
- 额外完成: 种子完成后自动更新数据库状态、活跃种子进度字段

#### 后端（11 个任务全部 done）

| 任务 | 说明 |
|------|------|
| 活跃种子速度接口 | `torrent_speed.py`, qB用status_filter, tr仅查速度字段 |
| 路由注册 | `/torrents/active-torrents` |
| 线程池泄漏修复 | commit 25c59aa |
| 速度单位转换修复 | commit d79040d |
| Transmission空列表修复 | commit b4ddde2 |
| 活跃种子进度字段 | commit a568aa9, progress字段(0-100百分比) |
| 种子完成后自动更新状态 | commit f8b0185, progress达100%自动更新为completed |
| 性能测试 | 4下载器并发平均543ms |
| 场景测试 | 8个验收场景通过 |

#### 前端（2 个任务 done）

| 任务 | 说明 |
|------|------|
| 前端 API 封装 | `torrents.ts` getActiveTorrents() |
| 前端种子列表改造 | Options API + 虚拟分页 + 1秒轮询 + beforeDestroy清理 |

**关键实现**: `activeSpeedMap` 缓存速度数据；虚拟分页算法（活跃种子优先排列）；防抖 + 版本控制避免重复请求。

**结论**: v1.0.4 前后端开发完成。

---

### v1.0.9 一键部署 (done，提前完成) — dev 分支

**说明**: v1.0.9 早于 v1.0.5~v1.0.8 提前完成落地。

| 任务 | 说明 |
|------|------|
| 全栈 monorepo 整合 | commit c7ce2f4，前后端合并为单一仓库 |
| PyInstaller 打包 | deploy/btdeck.spec，前后端合一单可执行文件 |
| Inno Setup Windows 安装包 | deploy/btdeck.iss |
| fpm Linux 安装包 | deploy/build-linux.sh，.deb/.rpm |
| Docker Compose 全栈部署 | docker-compose.yml |

**部署修复系列**: 5e4baf8 / 6f8e3e0 / 78033bc / fb380b9 / b80a7f6（Inno Setup 语言包、PyInstaller 路径、pandas/numpy/openpyxl hiddenimport、PIL 排除、systemd 目录预创建等）。

---

## 计划外已完成功能

### 通知中心 (done) — dev 分支

**后端**: `notification.py`(模型) + `notification_service.py`(版本检查、未读计数) + `notifications.py`(GET/PUT/DELETE 端点)。单向信箱模式，仅系统写入。
**前端**: `NotificationDrawer/index.vue`(全局右侧抽屉) + `NotificationItem.vue` + `store/modules/notification.ts`(Vuex) + `api/notification.ts`。60秒未读计数轮询。

### Tracker关键词池初始化 (done) — dev 分支

`tracker_keywords_pools.py` 关键词池管理，默认数据自动初始化，集成到 `init_db()` 统一初始化流程。

### 统一初始化重构 (done) — dev 分支

所有初始数据初始化统一到 `init_db()`，集成到后端启动流程。commit 22a89c8。

---

## 待开发功能（按计划顺序）

| 版本 | 名称 | 计划文件 | 状态 |
|------|------|----------|------|
| v1.0.6 | 孤儿文件管理 | PLANS/v1.0.6.md | pending |
| v1.0.7 | 路径扫描增强 | PLANS/v1.0.7.md | pending |
| v1.0.8 | 数据库升级 | PLANS/v1.0.8.md | pending |
| v1.1.0 | 自动化运维 | PLANS/v1.1.0.md | pending |

---

## 技术决策记录

| 日期 | 端 | 决策 | 理由 |
|------|----|------|------|
| 2026-04-22 | backend | 轻量级active-torrents替代动静分离 | 更简单，前端1秒轮询仅查有速度种子 |
| 2026-04-22 | frontend | Options API 而非 Composition API | 项目技术栈约定 |
| 2026-04-22 | frontend | 前端虚拟分页 | 已有查询逻辑，前端合并更灵活 |
| 2026-04-22 | frontend | 防抖+版本控制 | 避免1秒轮询导致重复请求和页面卡顿 |
| 2026-04-22 | backend | 专用线程池 | 避免阻塞默认executor |
| 2026-04-22 | backend | 统一初始化到 init_db() | 集中管理初始数据 |
| 2026-06-18 | fullstack | harness 体系合并到根目录 | 全栈 monorepo 统一状态追踪，消除端级重复 |
| 2026-06-18 | fullstack | v1.0.5 补全 search_templates 而非新建 query_templates | 探索发现已有完整基础设施，避免重复造轮子 |
| 2026-06-18 | fullstack | User 不加 relationship（用 created_by 整数列） | 遵循既有约定（SettingTemplate 同模式），避免触发 User 表迁移 |
| 2026-06-18 | fullstack | query_config 用 source=simple/advanced 双分支 | 1:1 还原两种查询状态（listQuery / condition_groups），应用时按 source 分流 |
| 2026-06-19 | fullstack | 审计修复用独立 feature 块 v1.0.5-audit 而非 v1.0.5.1 | v1.0.5.1 子任务号已被 done 占用，撞号；用 -audit 后缀避开数字子任务号空间 |
| 2026-06-19 | fullstack | 实施顺序 P0-3→P0-1→P1→P0-2c→P0-2a/b | 异常处理器先做兜底；前端归一化在后端 401 之前避免破损窗口；认证基础设施先于迁移避免 user_id 断链 |
| 2026-06-19 | backend | 认证统一用 require_authenticated_user（HTTP 401），login.py 豁免 | login 的 code=401 是密码错误业务语义，非认证失效，前端登录页依赖此分支不跳转 |
| 2026-06-19 | backend | 不把 user_id 加入 verify_access_token required_fields | 避免现有未过期 token 全部失效（强制全员重登），改为 AuthenticatedUserInfo 兜底解析 |
| 2026-06-19 | frontend | ApiError extends Error + 兼容 msg/response getter | 降低约 33 个存量 catch 块的回归（e.msg / e.response.data.msg 链式读取仍可用） |
| 2026-06-19 | frontend | 成功码白名单 {200,206,207} | 206(需确认路径映射)/207(Multi-Status 部分成功) 是业务级成功，不归一化为错误 |
| 2026-06-19 | fullstack | apply 改前端对齐后端 Path 参数 | 后端 Path 更 RESTful，且 override=True 硬编码使 override_local 无效 |
| 2026-06-19 | fullstack | torrents/detail 不补后端端点，删前端死代码 | getTorrentDetail 从未被调用，补后端会引入语义模糊(hash可能重复)的未用功能 |

---

## 当前会话

> **2026-06-28**: 后端回归测试补全（续）——为"纯 DB 操作、业务逻辑零测试覆盖"的接口补充 API 级回归测试，每个接口经"子代理审查 → 实证核实 → 修订 → 反向验证"闭环。共 10 个 commit，+86 个回归测试，全量 tests/api/ 413 passed 无回归。
>
> **本次覆盖的 3 个接口 + 1 个基础设施重构**：
>
> 1. **审计日志查询接口**（commit 545fad4 + 8197567，41 测试）
>    - POST /audit-logs/query（11 维过滤 + 子查询 count + LIKE 模糊 + 分页）
>    - GET /audit-logs/statistics（内存聚合 + unknown 桶）
>    - GET /audit-logs/operation-types（39 枚举展开）
>    - 范式：aiosqlite 异步内存库 + AsyncSession + 覆盖 get_async_db
>    - 子代理审查修订（+7）：排序完整序列断言、count 解耦 offset 验证、msg 排除断言防 service 吞异常假通过、401 body 断言、枚举 value 集合相等、LIKE 通配符已知行为、download-export 约定差异
>
> 2. **仪表盘统计接口**（commit 39e4b97 + 1485986 + 399b68b + 1c05d16，23 测试）
>    - GET /dashboard（裸 SQL 聚合 cron_task/torrent_audit_log + 内存缓存 store/torrent_stats）
>    - 范式：aiosqlite 异步内存库 + SimpleNamespace FakeStore 注入 app.state
>    - 经 **4 轮子代理审查**完全收敛：第1轮发现 1 真 flaky（60秒窗口）+ 1 假通过（dr 方向）；第2-4轮逐轮确认上轮到位 + 补覆盖盲区（dict 计数 vs set、keyword_rule 归一化路径、torrent_stats=None 已知行为）
>    - 关键修复：时间断言用绝对时间/身份标记避免 flaky；降级场景加 msg 断言防假通过
>
> 3. **种子删除 L4 接口**（commit 1e9a10f + 4ac69af，22 测试）
>    - DELETE /torrents/delete-with-level（L4 待删除标签路径）
>    - **设计转折**：原计划 HTTP e2e 经子代理审查发现 3 个 🔴 致命缺陷（同步/异步库不可共享内存库、响应字段缺失、store 未挂载），**重设计为 service 级测试**绕开三缺陷
>    - 范式：同步内存库 + mock request（挂 store）+ mock audit（AsyncMock 记录调用）
>    - 子代理审查修订（+4）：补 delete_batch_by_level 降级编排测试（L3→L4，service 核心复杂度零覆盖）、audit 身份锁定断言、OR 断言收窄、脏数据边界
>
> 4. **测试基础设施去重**（commit c881d69，重构）
>    - 提取 make_torrent 工厂到 tests/api/conftest.py（3 文件去重 → 1 共享工厂，13 业务 kwarg 超集签名）
>    - 设计决策：普通函数（非 fixture，接 db 参数多次调用）；test_torrent_models 的 MagicMock 工厂不合并（不同关注点）
>
> **关键测试质量教训（多轮审查沉淀）**：
> - **flaky 防护**：时间断言用绝对时间/足够裕度/身份标记，不用"恰好当前时间"
> - **防假通过**：降级/空数据场景加 msg 排除断言（防 service 吞异常返回空结构仍 code=200）
> - **身份锁定**：过滤测试断"返回哪条"而非"返回几条"（防方向写反）；audit 断 torrent_info_id
> - **完整序列 + 计数**：排序用完整顺序断言（非首尾比较）；分类用 dict 计数（set 漏计数）
> - **service 级 vs HTTP e2e**：当 endpoint 有同步/异步双 session + 响应字段裁剪时，service 级测试绕开共享库与字段缺失问题，且能测到完整返回字典
>
> **子代理审查的工作流价值**：每轮审查都实证核实（不盲信），发现真问题（flaky/假通过/盲区）也否决误报（如"len==len 恒真"实际能抓到）。4 轮审查收敛性：第1轮发现最多（质量基线），后续轮次确认到位 + 补越来越细的盲区。
>
> ---

> **2026-06-27（续）**: 收尾——v1.0.5-audit 标 done + 前端验证补遗 + 残留分支清理。
>
> **v1.0.5-audit 契约审计收尾** ✅
> - feature_list.json 中 v1.0.5-audit 的 8 个子任务（P0-1~P0-3 / P0-2a-d / P1-A/B）全 done，范围明确（P0+P1 完成，P2/P3 推迟有记录）。feature 顶层 status 从 `in_progress` 标为 `done`
> - **残留分支清理**：原独立分支 `fix/contract-audit` 的所有 commit 已 100% 合并入 dev（`git log dev..fix/contract-audit` 为空，dev 领先 29 commit）。删除本地 + 远端 `fix/contract-audit`（用户决策"删本地+远端"）。远端现仅剩 `origin/dev` + `origin/master`
>   - 注：`git branch -d` 因本地相对上游 `origin/fix/contract-audit` 的保守判断报"未完全合并"，但相对 dev 实际已无独有 commit，改用 `-D` 强制删除（reflog 可恢复）
>
> **前端验证补遗（清除 progress.md 既有遗留）** ✅
> - 既有遗留"前端 lint/tsc 因环境依赖未完整安装"（progress.md:99）现环境就绪，补跑：
>   - `npm run lint`：**0 errors**（131 warnings，全是 no-unused-vars 非阻塞）
>   - `npx vue-cli-service build`：**成功**（含 tsc 类型检查，dist 生成）
>   - `npm run test:unit`：**34 passed**（含契约审计的 ApiError 归一化测试）
> - progress.md:99 遗留标记为已补验
>
> ---

> **2026-06-27**: 高风险 lint 技术债 3 类清理（F811 + E711/E712 + mypy ORM 债评估）——lint 技术债清理第七轮。
>
> **任务 A：F811 高风险残留清理（5→0）** ✅
> - cuser.py：两个 `twofa_verify` 绑不同路由路径（/2faVerifyQrCode/ 与 /2faVerifyCode/），FastAPI 按路径注册故路由正常工作，仅模块级变量被后者覆盖（无调用点）。改名为 `twofa_verify_qrcode`/`twofa_verify_code` 消除 F811（无害变量重定义，**非 bug**）
> - torrents_async.py：`qb/tr_add_torrents_info_only_async` 各定义 3 次。经 **AST 对比 + git 历史追溯（初始 commit 8fe877d）** 确认：tr 三份 IDENTICAL（copy-paste 死代码）；qb 前两份一致（含 tracker 富集），第三份（生效版，Python 后定义覆盖前定义）**从 day 1 起就不含 tracker 富集**（富集只在 tracker-only 同步函数 `qb_sync_trackers_only_async` 里）。三份重复定义自项目诞生即存在，生效版始终是第三份。删除前两组死代码副本（**-678 行**），保留生效版。调用方仅 `torrent_info_sync_task.py`，行为不变
> - **审查教训（子代理发现）**：首版 commit ba8689b 把"第三份去掉富集"误归因到 73df90c。`git log -S "_enrich_..."` 命中 73df90c 是因为它**新增**的 tracker-only 函数含此调用，而非从 info_only **删除**。`git log -S` 只说明该 commit 涉及该字符串，**不能推断增删方向**，必须看 hunk 的 +/- 行（73df90c 的 hunk `@@ -3142,3 +3142,222 @@` 证明只在文件末尾追加、未动 info_only）。已更正文档
> - **门禁收紧**：F811 从 .flake8 extend-ignore 移除，进入全仓门禁。commit ba8689b
>
> **任务 B：E711/E712 全量清理（47→0，最高风险）** ✅
> - **逐个甄别 47 处** == None / == True / == False，区分 ORM 查询（保留语义）与 Python 条件（改 is），**不盲改**避免破坏 SQLAlchemy 查询生成
> - 44 处 ORM `.filter()`/`.where()`/`or_()`/`case()` 内的 `== True/False` → SQLAlchemy 官方推荐的 `.is_(True)`/`.is_(False)`（生成 IS true/false，对 NOT NULL boolean 列与 `==` 语义等价）
> - 3 处 Python 条件：`torrent_sync.py:712 create_time==None→is None`；`torrent_sync.py:1165 downloader.enabled!=True→not downloader.enabled`（已加载实例属性，三态完全等价）
> - 4 处 `downloader.py delay==False`：**0==False 真值陷阱**（ping3.ping 返回值可能是数值/False/None，改 is False 会改变 delay=0 真值）→ **用户决策**加 inline `# noqa: E712` 保留==
> - **子代理 code review（修复者盲点防护）补充修复 3 处**：tracker_messages:90 + cron_crud:418/420 是历史 ORM noqa 顶替（应做 .is_() 而非 noqa），扫描时被默认 noqa 掩盖漏报，一并修正
> - **门禁收紧**：E711/E712 从 .flake8 extend-ignore 移除，进入全仓门禁。commit 7a21718
>
> **任务 C：mypy app/models/ ORM 债评估（133 处，只评估不实施）** ✅
> - 133 errors（117 assignment + 10 return-value + 4 arg-type + 2 var-annotated，9 文件）**100% 归因 ORM 描述符类型推断失败**（`Base=declarative_base()` 1.4 风格），非真实 bug
> - **SQLAlchemy 已是 2.0.47**（无需升级依赖），但未启用 mypy 插件
> - 三方案评估：A 迁移 `DeclarativeBase`+`Mapped[]`（长期最优，17文件146字段，2-3会话）/ B 启用 mypy 插件（短期过渡降噪）/ C 保持现状
> - 评估报告写入 `backend/docs/tech-debt-lint-baseline.md`，**不实施代码改动**，建议作为独立技术债任务单独立项
>
> **验证**：每任务后 pytest（A: 1619 passed；B: 1619 passed）；flake8 全仓 0 错误；F811/E711/E712 isolated 全 0；历史修复全完好。
>
> **lint 技术债清理里程碑**：7 轮清理后，`.flake8` extend-ignore 仅剩 E203/E402/E501/W503/W504/W605 六项（风格/格式类），所有进入豁免的历史 F/E 规则（F401/F541/F811/F821/F824/F841/E711/E712/E722/E741）已全部清零进门禁。剩余仅 mypy ORM 债（架构级，待 SQLAlchemy 2.0 迁移独立立项）。
>
> ---

> **2026-06-26（续4）**: F811 重复 import + E722/E741 风格清理——lint 技术债清理第六轮。
>
> **任务：F811 重复 import（部分）+ E722 + E741** ✅
> - F811：15→5（清 10 处：7 模块级重复 import 删除 + 3 函数内局部 import 加 noqa；剩 5 处是高风险项单独记录）
> - E722：2→0（裸 except 改 except Exception，避免误捕 KeyboardInterrupt）
> - E741：2→0（列表推导式变量 l 改 label）
> - **门禁收紧**：E722/E741 从 `.flake8` extend-ignore 移除（F811 保留豁免，仍有 5 处残留）
>
> **F811 调研发现 2 个真实 bug（高风险，单独记录未修）**：
> - `torrents_async.py`：`qb/tr_add_torrents_info_only_async` 各定义 3 次（copy-paste 残留），需验证内容一致性
> - `cuser.py`：`twofa_verify` 同名函数定义两次绑不同路由。FastAPI 按路径注册故两条路由正常工作，仅模块级变量被后者覆盖（无害），建议改函数名消除 F811（子代理审查修正：非"路由 bug"，是"无害变量重定义"）

> **子代理审查后修正（91140f3）**：
> - 3 处 noqa: F811 的注释从误导性的"与另一函数不冲突"改为准确的"与上方冗余，保留以降低独立 try 块对顶部 import 顺序的耦合"（实为同一函数内冗余 import，功能无害）
> - cuser 判断从"潜在路由 bug"修正为"无害变量重定义"（两函数绑不同路径，路由正常工作）
>
> **验证**：pytest 1619 passed（0 失败）；flake8 全仓 0 错误；E722/E741 isolated 0；历史修复全完好。
>
> **剩余 lint 债**：F811 高风险 5 处（重复函数/同名 bug）、E711/E712 高风险 47 处（ORM 甄别）、mypy ORM 债 133（SQLAlchemy 2.0 迁移）。
>
> ---

> **2026-06-26（续3）**: P2 F841 未用变量清理（23→0）——lint 技术债清理第五轮。
>
> **任务：F841 局部变量赋值未用全部清理 + 进门禁** ✅
> - 8 文件 23 处：
>   - 16 个 `except ... as e:`（e 未用）→ `except ...:`（保留异常类型去绑定）
>   - 5 个 `torrents = client.xxx()` 连接健康检查 → `client.xxx()`（**保留调用去赋值**，调用是健康检查不能丢）
>   - 1 个 `manager = Service(db)` → `Service(db)`（保留调用）
>   - 1 个 `module = importlib.import_module()` → `importlib.import_module()`（保留导入副作用）
> - **门禁收紧**：F841 从 `.flake8` extend-ignore 移除，进入全仓门禁
>
> **过程中的脚本踩坑（已解决）**：
> - 首版正则 ` as e:\s*$` 的 `\s*$` 吞了行尾换行符，把 except 行和下一行合并成一行（IndentationError）
> - 已 `git checkout HEAD` 回滚，修正为 `line.replace(' as e:', ':')` 只替换子串不碰换行
> - **教训**：处理含换行的文本时，正则的 `$`/`\s*$` 会跨行，应用 `str.replace` 精确替换子串
>
> **验证**：pytest 1619 passed（0 失败）；flake8 全仓 0 错误；F541/F821/F824/F401/example= 均无回退；py_compile 全部通过。
>
> ---

> **2026-06-26（续2）**: P5 Pydantic example= 全仓统一（177→0）——lint 技术债清理第四轮。
>
> **任务：Pydantic v1 `example=` → v2 `examples=[]` 全仓清理** ✅
> - 10 文件 166 处（含 app/models/ 之前清的 11 处，共 177→0）：`example=X` → `examples=[X]`
> - 正则方案（字符串/数字/bool/None/空列表 4 类字面量精确匹配），修复后 example= 全清零
> - 补全被 Pydantic v2 静默忽略的 OpenAPI schema 示例值
> - **意外收益**：pytest warnings 865→713（`example=` 的 PydanticDeprecationWarning 消失）
>
> **过程中的脚本踩坑（已解决）**：
> - AST 脚本因 col_offset 是 UTF-8 字节偏移（含中文行与字符索引不一致）导致插入位置错误，损坏 api/responseVO.py
> - 已 `git checkout HEAD` 回滚，改用正则方案（不依赖字节偏移），165 处全清零无误
> - **教训**：Python ast 的 col_offset 对非 ASCII 行是字节偏移，不能直接用于字符串切片
>
> **验证**：pytest 1619 passed（0 失败）；flake8 全仓 0 错误；F541/F821/F824/F401 均无回退；schema examples 生成验证通过。
>
> ---

> **2026-06-26（续）**: P3 F541 f-string 清理（74→0）——lint 技术债清理第三轮。
>
> **任务：F541 无占位符 f-string 全部清理 + 进门禁** ✅
> - 26 文件 74 处 `f"无占位符"` → 普通字符串（72 处脚本批量 + 2 处多行拼接手工）
> - 修复前 AST 分析确认 74 处全部是纯字面量、无 `{{}}` 转义，可安全去 `f` 前缀
> - **门禁收紧**：F541 从 `.flake8` extend-ignore 移除，进入全仓门禁
>
> **⚠️ 过程中的工作树污染事故（已恢复）**：
> - 发现本地 dev ref 被某操作重置回 eaf677a（丢失 f867b09 P0 修复），导致在无 P0 修复的旧基础上误跑 F541 脚本
> - 症状诡异：`git diff HEAD` 显示无差异（被 autocrlf=true 掩盖），但工作树文件实际是旧内容
> - 根因定位：`git log` 发现 HEAD 是 eaf677a 而非 f867b09；`origin/dev` 仍有 f867b09
> - 恢复：`git reset --hard origin/dev` 对齐远端，P0 修复完好确认后在干净基础上重跑
> - **教训**：开始工作前必须 `git log` 确认 HEAD 状态，不能假设；`git diff` 在 autocrlf 下可能有假象，用 `git status` + hash 对比更可靠
>
> **验证**：pytest 1619 passed（0 失败）；flake8 全仓 0 错误；F541 isolated 0；F821/F824 仍 0（P0 完好）。
>
> **剩余 lint 债**：P2 F841（23）、P4 E711/E712（47，需甄别 ORM 查询）、P5 example=（166）、F811（15）、mypy ORM 债（133）。
>
> ---

> **2026-06-26**: P0 真实 bug 修复（F821/F824，17→0）——lint 技术债清理第二轮。
>
> **任务：F821/F824 真实 bug 全部修复 + 进门禁** ✅
> - 6 文件 17 处 undefined name / global 误用全部修复：
>   - audit_logger.py（5 处）：补模块级 `logger` + `desc` import
>   - torrent_crud.py / torrent_deletion.py（3 处）：函数加 `request: Request` 参数（原 `req.app`/`request` undefined 会 NameError 崩溃）
>   - initialization.py（7 处）：2 个后台任务函数加 `app: FastAPI` 参数（原调用已注释=死代码）+ 删 4 处纯 dict 操作的无用 `global`
>   - tag_service.py（1 处）：删除 except return 后的孤儿死代码（含 undefined `tags`）
>   - security.py（1 处）：删 `_decryption_key_cache.clear()` 的无用 `global`
> - **门禁收紧**：6 文件的 F821/F824 per-file-ignores 全部移除，F821/F824 现进入全仓门禁
> - **教训**：torrent_crud.py 加 `request: Request`（无默认值）放在 `_user=Depends()`（有默认值）之后触发 SyntaxError，导致 180 个测试 setup ERROR；pytest 立即捕获，改为 `request: Request = None` 修复
>
> **验证**：pytest 1619 passed（0 失败）；flake8 全仓 0 错误；F821/F824 isolated 0 残留；init.sh 通过。
>
> **剩余 lint 债**：P2 F841（23）、P3 F541（74）、P4 E711/E712（47，需甄别 ORM 查询）、P5 example=（166）、mypy ORM 债（133，待 SQLAlchemy 2.0 迁移）。

---

> **2026-06-25**: lint 技术债清理（F401 + mypy app/models/ 渐进）——两项独立技术债任务。
>
> **任务 1：F401 未用 import 清理（基线 P1，最大单项收益）** ✅
> - autoflake 保守参数清理：**321 → 9**（清掉 310 个未用 import）
> - **陷阱规避**：autoflake 会误删 `database.py` 的 9 个 ORM 模型注册 import（防御性注册，注释明确意图），手工恢复 + 加 `.flake8` per-file-ignore
> - **附带修复**：`app/models/__init__.py` 的 `__all__` 拼写 bug（`TRANSER_STATUS_SUCCESS` → `TRANSFER_STATUS_SUCCESS`，导致重导出名不副实）
> - **门禁收紧**：F401 从 `.flake8` extend-ignore 移除 → 新增代码未用 import 现已进入门禁
> - black 修复 autoflake 删 import 后的空行副作用（E303/E302）
>
> **任务 2：mypy app/models/ 渐进清理** 🔶（部分完成，剩余归 ORM 债）
> - 修复前 145 errors → 修复后 133 errors（-12）
> - **修了 12 个真实类型 bug**：Pydantic v2 API 误用（`example=` → `examples=[]`，11 个；`ConfigDict(by_alias=)` 死键，1 个）。原 v1 写法被静默忽略导致 OpenAPI schema 无示例值
> - **剩余 133 个 100% 归因 ORM 描述符**：根因 `Base = declarative_base()`（SQLAlchemy 1.4 风格），mypy 不识别 `class X(Base)` 为合法类型。117 assignment + 10 return-value + 4 arg-type + 2 var-annotated。**解法是 SQLAlchemy 2.0 声明式迁移**（`DeclarativeBase` + `Mapped[]`），属独立大任务，不混入 lint 清理
> - **review 发现的遗漏**：全仓另有 166 处同型 v1 `example=` 写法（10 个文件，downloader/torrents/tracker/user/api 等），本次只清了 app/models/ 的 2 个 vo 文件，其余留作 P5 后续项
>
> **验证**：pytest 1589 passed（0 失败，0 回归）；flake8 项目配置 0 错误；mypy app/models/ 145→133；init.sh 全栈验证通过。
>
> **下一步建议**：F401 已彻底闭环。mypy 剩余的 133 个 ORM 债 + 全仓其他模块需等 SQLAlchemy 2.0 迁移（独立任务）。
>
> ---
>
> **2026-06-20**: v1.0.5-audit P0-2 认证统一全部完成——本会话完成 P0-2a（24 文件迁移，分 4 批）+ P0-2b（测试断言改造）+ P0-2d（弃用 verify_token_dependency），共 6 commit。
>
> **调研修正**：交接文档预估 ~21 文件 + ~102 处测试断言。实际调研发现：24 个文件；测试改造仅 32 处 inline 断言（因 test_auth_protection_extended.py 的 62 处走 _is_auth_rejected helper 已兼容 HTTP 401）。这改变了"必须原子配对"的前提，改为按风险分 4 批，每批 commit + 跑针对性 pytest。
>
> **完成清单**：
> - Batch A（10 token-only）+ Batch B（downloader/cron_tasks/tracker/torrent_crud/sync，最大 cron_tasks 20 endpoint）
> - Batch C（3 user_id 文件，advanced_search 旧 token 缺 user_id → HTTP 401 兜底，用户确认对齐 torrent_location 模板）
> - Batch D（4 mixed 部分迁移文件）
> - P0-2b：5 测试文件断言改造（含 tag_management mock_auth 改用 dependency_overrides）
> - P0-2d：verify_token_dependency 加 DeprecationWarning，cron_tasks.verify_token 已删除
>
> **附带修复**：多处预存在的"不安全 try/except 认证"（verify_access_token 失败返回 None 而非抛异常，旧代码 try/except 形同虚设，torrent_sync/tracker_messages/cuser 2FA 端点）。
>
> **验证**：后端 pytest 1523 passed（2 个预存在失败：test_unified_token_expiry 路径分隔符 bug + test_concurrent_requests flaky，均与本次无关）；init.sh 全栈验证通过。
>
> **下一步**：P0-2 全部完成。剩余 P2/P3 均为推迟项（REST 路由迁移、前端 any 治理、OpenAPI schema、分页字段统一、API 对照表 CI）。可选收尾：彻底删除 verify_token_dependency 定义。

---

### 传统模式 bug 修复 + 防回归基础设施 + 功能对齐（2026-06-28）

**目标**：传统模式(TraditionalView.vue)相对列表模式(index.vue)全面对齐——先修 bug，再建防回归基础设施，最后补齐缺失功能。

**方法论**：全程「子代理对抗审查 + 用户决策修订」循环——每个方案先用 Explore 子代理独立审查挑毛病，修正阻断项后再实施。

#### 阶段 1：Bug 修复（8 个，commit 含于防回归提交）
子代理精准审查 + API 签名亲核（deleteTorrents 后端只认 info_id/delete_data/id_recycle；token 存 Cookie 非 localStorage）。
- Bug#4 删除参数错误（hashes→info_id）、Bug#3 速度轮询（原生fetch+错token→getActiveTorrents封装）
- Bug#1 删除计数（字符串长度→逐种子）、Bug#2 文案语义（下载器组数vs种子数）
- Bug#8 选中状态重置、Bug#7 排序键（!!map→速度>0）、Bug#6 单条删除错误收敛、Bug#9 未用import

#### 阶段 2：三层防回归基础设施（commit 52ff81e）
子代理对抗审查修正 3 处阻断：AST selector 静默失效（firstArgument→arguments.0.value 实测）、L3 正则脚本对 index.vue 误报、L2/L3 scope 冲突。
- **L1 ESLint**：no-restricted-syntax 禁原生 fetch/token（esquery 1.7.0 实测 selector），no-unused-vars（warn 避免117历史债阻断CI），FileManagement.vue 文件级豁免
- **L2 纯函数+mixin**：utils/torrentBatch.ts（5纯函数，API依赖注入便于单测）+ mixins/torrentBatch.ts（薄封装），两视图删除~280行重复实现
- **L3 jest 单测**：行为契约断言（不怕等价重写）。反向验证：改回Bug#7原始形态→2测试变红，fetch规则实测拦截

#### 阶段 3：功能对齐（13项，分 P0/P1/P2 三批）
子代理审查修正 4 处阻断：toolbar布局缺失、4等级删除下沉硬伤（上帝mixin）、sort_by跨视图bug、下沉边界偏乐观。

| 批次 | commit | 内容 |
|------|--------|------|
| P0 | c286b7e | 活动开关/刷新/改路径/转移/Tracker操作·汇报·全局替换/详情Tracker增强（9项，对话框全复用） |
| P1 | c82a321 | 高级搜索/查询模板/查找重复 + sort_by统一修复（addedDate→added_date对齐后端ORM字段名） |
| P2 | 5df3ce8 | 4等级删除（纯函数+mixin分层，只做TraditionalView）+ 列设置（10列可隐藏） |

#### 验证
- eslint: 全程 0 error（123 warning 全为历史债，no-unused-vars 降为 warn）
- jest: 53 → 81 passed（净增28行为契约单测）
- mixin/utils 文件 0 TS 错误；两视图 template 噪音是项目既有 vue-tsc 推断问题

#### 关键设计决策
- **下沉边界清晰**：无副作用→utils纯函数（可单测）；Vue实例方法($loading/$message)→mixin；UI接线→视图。不造上帝mixin
- **4等级删除分层**：纯函数(构造/解析)+mixin(入口/轮询/loading+beforeDestroy清理)+视图(dropdown)，解决this.$loading/this.tableData/长轮询生命周期三矛盾
- **列设置独立key**：traditional_columns_visibility 与列表分开（两视图列结构不同）
- **查询模板路由**：traditional模式下index.vue未挂载，apply_template_id必须在本视图处理

#### 诚实边界（未做）
- index.vue 的4等级删除迁移（单独立项，P2只做TraditionalView）
- 详情面板「文件/Peers」占位tab（需后端API，属另一功能）
- showActiveOnly分页失真（标known-issue，对齐列表既有缺陷未根治）
- 主题切换不在对齐范围（传统模式用固定scss主题）

---

**最后更新**: 2026-06-28
---

### 质量门禁可信化（2026-07-10 续）

本轮继续修复前后端 lint/测试“假通过”问题：根 `init.sh --full` 与前后端 `scripts/init.sh --check` 已改为真实传播失败退出码；后端严格入口接入 Black、Flake8、Ruff、Mypy 与自定义架构 lint；前端 `npm run lint` 改为 `vue-cli-service lint --max-warnings 0 && node scripts/lint-vuex-action.js`。

已完成验证：
- 后端自定义架构 lint 的独立负向样例补齐，`pytest backend/tests/test_architecture_constraints.py` 为 21 passed。
- 后端 Black/Flake8/Ruff 基线通过；自定义 lint 已纳入 init/Makefile。
- 前端历史 129 条 ESLint warning 已清零，`npm run lint` 通过，并实际执行 Vuex `@Action({ rawError: true })` 自定义检查。
- Vuex lint 脚本新增可测试导出与正反例单测，`npm run test:unit -- lint-vuex-action.spec.ts` 为 2 passed。

仍保持真实阻断：`mypy app` 存在历史类型债务，严格入口会失败，不做吞错、不做“赋值通过”。后续应作为独立类型治理任务处理。

**最后更新**: 2026-07-10

---

### 传统模式 code review 修复与回归闭环（2026-07-18）

本轮按三个子代理的后端同步、后端分页/元数据和前端传统模式审查结果，修复全部已确认的 P1/P2 问题。

- qB 增量同步改为数据库写入和提交成功后才推进 RID；完整水合为空、部分返回、超时或写库失败时保留旧 RID，并补齐删除路径和首次同步失败回归。
- 元数据补全支持 qB/Transmission 分下载器、分批调用与批次级故障隔离；新增有界正负缓存和轮转游标，避免大数据量在缓存淘汰下长期补不到后续记录。
- 重复任务十万分页改用分页子查询联接，稳定排序加入唯一键；高级搜索和普通列表的 Tracker/下载器数据统一批量预取，并动态遵守 SQLite 变量上限，消除逐行查询。
- 传统模式用 `downloader_id + hash` 作为跨下载器行身份，修复选中、高亮、详情、删除和速度映射串行；活动排序改为线性建索引后排序，覆盖 100000 条数据。
- 普通、重复、高级和模板查询各自保持分页来源，以请求序列丢弃过期响应；分页组合框、过滤按钮及虚拟列表补齐键盘、ARIA、焦点和生命周期回归。

验证结果：后端全量 `pytest tests -q` 为 **2154 passed、1 skipped、0 failed**；前端全量 Jest 为 **16 suites / 265 tests**，TypeScript、严格 ESLint、Vuex lint 和生产构建均通过；变更文件 Flake8、Ruff、Black API 格式校验及 `git diff --check` 通过。根 `init.sh` 因当前 Windows 无可用 WSL 无法执行；Mypy 仍存在项目既有 SQLAlchemy/VO 类型债务，未通过本次任务掩盖或降级。

**最后更新**: 2026-07-18
