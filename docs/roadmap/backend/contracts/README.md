# backend/contracts — 前后端共享契约

> 新增于 v1.0.6.27（commit `eef3eea`）。本目录存放**前后端共享的、机器可读的领域契约**，作为单一真相源（single source of truth），消除"后端枚举/操作符列表"与"前端下拉选项"重复维护导致的漂移。
> 定位方式：`Grep -i <功能词> docs/roadmap/backend/contracts/README.md`，命中行即含文件 + 职责，无需 Read 全文。

## 关键词速查

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 契约加载器 contract-loader | `advanced_search.py`（38 行） | 高级搜索契约加载器：把 JSON 解析为模块级常量（`SEARCH_FIELD_CONTRACT` / `SUPPORTED_SEARCH_OPERATORS` / `FRONTEND_TO_BACKEND_OPERATOR` / `NEGATED_SEARCH_OPERATORS` 等）；`allowed_operators_for_field(field)` 严格返回该字段声明的白名单，不再把全局空值操作符注入所有字段 |
| 机器可读契约 contract-json | `advanced_search_contract.json`（100 行，v3） | **机器可读契约**：20 字段 → kind/operators/negated 映射、nullOperators、正则上限及 operatorGroups；完成时间/比率/比率限制/标签/分类声明“未设置/已设置”，`status`/下载器为精确多选，超级做种为是/否/不支持三态 `select` |

## 设计动机

高级搜索在历史上存在三处操作符/字段语义的真相：

1. 后端 `app/api/models/advanced_search.py`（Pydantic 校验 + 字段类型）
2. 后端 `app/services/advanced_search.py`（SQL/ORM 执行）
3. 前端 `AdvancedSearchBuilder.vue` / `ConditionValueInput.vue`（下拉选项 + 校验文案）

三处任一改动都可能让前后端契约不一致（典型 bug：前端可选 `not_contains`，后端不支持）。
本目录通过一份 JSON 契约 + Python 加载器，让**前端构建期与后端运行期读取同一份定义**，从而把"漂移"从运行时错误降级为编译期/启动期错误。

## 关键常量（`advanced_search.py`，模块级）

| 常量 | 类型 | 含义 |
|------|------|------|
| `ADVANCED_SEARCH_CONTRACT` | `Dict[str, Any]` | 整份 JSON 反序列化结果 |
| `SEARCH_FIELD_CONTRACT` | `Dict[str, Dict]` | 字段级配置（kind + operators） |
| `NULL_SEARCH_OPERATORS` | `FrozenSet[str]` | 空值类操作符（`is_null` / `is_not_null`） |
| `SUPPORTED_SEARCH_OPERATORS` | `FrozenSet[str]` | 所有字段的操作符并集 ∪ null 操作符 |
| `FRONTEND_TO_BACKEND_OPERATOR` | `Dict[str, str]` | 前端语义名 → 后端执行名（如 `not_contains` → `not_contains`，预留别名映射位） |
| `NEGATED_SEARCH_OPERATORS` | `Dict[str, str]` | 操作符与其否定形式对应表 |
| `MAX_REGEX_CONDITIONS` / `MAX_REGEX_PATTERN_LENGTH` | `int` | 正则条件数量与单条 pattern 长度上限 |

## 消费方

| 消费者 | 用途 |
|--------|------|
| `app/api/models/advanced_search.py` | Pydantic 校验器引用 `SUPPORTED_SEARCH_OPERATORS` / `allowed_operators_for_field`，请求期拒绝非法操作符；`SearchCondition.mode` 独立保存 include/exclude，旧标签标量操作符归一为 token 操作符 |
| `backend/tests/services/test_advanced_search_regression.py` / `test_advanced_search_models_strict.py` | 契约与真实 SQLite 守卫：字段白名单、模板模式、空值、标签、Tracker、下载器改名与三态查询 |

> 前端通过 `frontend/scripts/generate-advanced-search-contract.js` 从本 JSON 生成 `advancedSearch.generated.ts`，`operator-contract.spec.ts` 再逐项校验生成结果与源 JSON 完全一致；`npm run contract:check` 阻止漂移。生成/比较均按 LF 规范化（autocrlf=true 的 CRLF 检出不再误判 stale，语义漂移仍拦截；`advanced-search-contract.spec.ts` 回归，2026-09-04）。

---

## 关键观察

- **单一真相原则的落地实例**：本目录是 `perspectives/conventions.md` 中"避免双份真相"的代码级实现 —— 把"枚举/操作符"从散落定义收敛为一份机器可读文件
- **加载时机**：`contracts/advanced_search.py` 在 import 时即 `json.loads`，常量在进程级缓存，无运行时 IO 开销
- **契约演进**：修改字段 kind/操作符需同步生成 `frontend/src/contracts/advancedSearch.generated.ts`，并由 Pydantic/前端字段类型与操作符契约测试共同守卫（见 [test-coverage.md](../../perspectives/test-coverage.md)）

## 第三层详情

- 本分支文件少（3 个）且职责单一，通常不需要第三层方法签名详情；如需扩展，按"新增 `<domain>_contract.json` + `<domain>.py` 加载器"模式复制即可
