# Lint 技术债基线（2026-06-21）

> 本文档记录 lint 门禁建立时豁免的历史问题，作为后续逐步清理的清单。
> 门禁策略：历史问题豁免（见 .flake8 extend-ignore），**新增代码必须通过门禁**。

## 清理进度（2026-06-26 更新）

| 规则 | 建立时数量 | 当前数量 | 状态 |
|------|-----------|---------|------|
| **Pydantic `example=`** | 177 | 0 | ✅ **已全部清理**（app/models/ 11 处 + 全仓 166 处，`example=X`→`examples=[X]`，补全被忽略的 OpenAPI schema 示例值） |
| **F541** | 74 | 0 | ✅ **已全部清理 + 进门禁**（26 文件 74 处无占位符 f-string，2 处多行拼接手工处理） |
| **F821/F824** | 17 | 0 | ✅ **已全部修复 + 进门禁**（6 文件 17 处真实 bug，per-file-ignores 已移除） |
| **F401** | 327 | 9 | ✅ **已清理 + 进门禁**（autoflake 清 310 个，9 个 database.py ORM 注册 import 保留） |
| mypy app/models/ | 145 | 133 | 🔶 清了 12 个真实 bug（11 个 Pydantic v2 `example=` + 1 个 `by_alias` 死键），剩 133 个归 ORM 债 |

## flake8 豁免规则（.flake8 extend-ignore）

| 规则 | 说明 | 数量（建立时） | 清理方式 |
|------|------|---------------|---------|
| E203 | 冒号前空格（与 black 冲突） | 11 | 永久忽略（black 官方推荐） |
| E402 | 模块级 import 不在顶部 | 18 | 逐步重构 import 顺序 |
| E501 | 行太长（历史 SQL/URL 字符串） | 34 | 逐步拆分长字符串 |
| E711/E712 | 与 None/False 比较 | 47 | 逐步改 is/is not |
| E722 | 裸 except | 2 | 改为具体异常 |
| E741 | 模糊变量名 l | 2 | 重命名 |
| ~~F401~~ | ~~未使用 import~~ | ~~327~~ | ✅ **2026-06-25 已清理**（321→9，F401 已从 extend-ignore 移除进入门禁，仅 database.py 9 个 ORM 注册 import 走 per-file-ignore） |
| ~~F541~~ | ~~f-string 无占位符~~ | ~~74~~ | ✅ **2026-06-26 已清理**（74→0，从 extend-ignore 移除进入门禁） |
| F811 | 重定义（条件 import） | 30 | 逐步重构 |
| F841 | 局部变量赋值未用 | 44 | 逐步删除 |
| W503/W504 | 二元运算符换行 | — | 永久忽略（与 black 冲突） |
| W605 | 无效转义序列 | 4 | 改 raw string |

## ~~真实 bug（F821/F824，per-file-ignores 豁免）~~ ✅ 2026-06-26 已全部修复

原 17 处 undefined name / global 误用已全部修复并清零，per-file-ignores 已移除，
F821/F824 现进入全仓门禁。修复明细：

| 文件 | 问题 | 修复方式 |
|------|------|---------|
| app/utils/audit_logger.py | F821: `desc`/`logger` 未定义（5 处） | 补 `from sqlalchemy import desc` + 模块级 `logger = logging.getLogger(__name__)` |
| app/api/endpoints/torrent_crud.py | F821: `req.app` 未定义（2 处） | 函数加 `request: Request = None` 参数，`req.app` → `request.app` |
| app/api/endpoints/torrent_deletion.py | F821: `request` 未定义 | 函数加 `request: Request = None` 参数 |
| app/services/tag_service.py | F821: `tags` 未定义 | 删除 except return 后的孤儿死代码（unreachable） |
| app/downloader/initialization.py | F821: `app` 未定义（3 处）+ F824: 无用 global（4 处） | 2 个后台任务函数加 `app: FastAPI` 参数（原调用已注释=死代码）+ 删除 4 处纯 dict 操作的无用 global |
| app/core/security.py | F824: 无用 global（1 处） | 删除 `_decryption_key_cache.clear()` 的无用 global |

## mypy 历史问题

mypy 1649 个错误（历史类型标注缺失）。当前配置宽松（`check_untyped_defs=false`）。
清理策略：新增代码逐步补全类型标注，最终收紧 strict。优先清理的模块：
- app/models/（ORM 模型，类型相对清晰）
- app/core/（核心逻辑，类型安全价值高）
- app/services/（业务逻辑）

### app/models/ 清理记录（2026-06-25）

**修复前 145 errors → 修复后 133 errors（-12）**。

| 类别 | 数量 | 处理 | 说明 |
|------|------|------|------|
| Pydantic v2 API 误用 `example=` | 11 | ✅ 已修 | `example=X` → `examples=[X]`（v1→v2 API 变更，原写法被静默忽略导致 OpenAPI schema 无示例值）。涉及 setting_templates_vo.py(8)、downloader_capabilities_vo.py(3) |
| Pydantic v2 死配置 `ConfigDict(by_alias=)` | 1 | ✅ 已修 | `by_alias` 是序列化方法参数非 ConfigDict 键，移除（默认行为本就用字段名，不变） |
| ORM 描述符 `assignment`（Column 赋值冲突） | 117 | 🔶 ORM 债 | 根因 `Base = declarative_base()`（SQLAlchemy 1.4 风格），mypy 不识别 `class X(Base)` 为合法类型 |
| ORM 描述符 `return-value`（返回 Column 当标量） | 10 | 🔶 ORM 债 | 同上，`self.bool_col` 返回 `Column[bool]` 而非 `bool` |
| ORM 描述符 `arg-type`（json.loads(Column)） | 4 | 🔶 ORM 债 | 同上 |
| ORM 描述符 `var-annotated`（SQLEnum 推断失败） | 2 | 🔶 ORM 债 | 同上，`Column(SQLEnum(...))` 泛型推断失败 |

> **更新（2026-06-26）**：全仓剩余 166 处 v1 `example=` 已统一清理（正则方案，
> `app/downloader/`、`app/torrents/`、`app/tracker/`、`app/user/`、`app/api/models/` 等 10 文件），
> 加上 app/models/ 的 11 处，Pydantic `example=` 技术债全部清零（177→0）。

**ORM 债的根因与解法**：133 个剩余错误 100% 源于 SQLAlchemy 1.4 风格的 `Base = declarative_base()`。
现代 SQLAlchemy 2.0 写法 `class Base(DeclarativeBase): pass` + 字段改 `Mapped[bool]` / `mapped_column()` 可批量消除，
但这是全仓 200+ 字段的大改造，属于独立技术债任务（**SQLAlchemy 2.0 声明式迁移**），不混入 lint 清理。

**代码异味（dangling expression，约 15 处，非缺陷）**：autoflake 把"赋值后未读的局部变量"重写为裸表达式
（如 `connect_status = "x"` → `"x"`）。功能等价无运行时错误，但属 dead code，建议后续随 F841 门禁一并清理。

## 清理优先级

1. ~~**P0**：F821/F824 真实 bug（运行时潜在崩溃）~~ ✅ **2026-06-26 已完成（17→0）**
2. ~~**P1**：F401 未用 import（autoflake 一键清理，最大收益）~~ ✅ **2026-06-25 已完成**
3. **P2**：F841 未用变量（简单删除，含 autoflake 留下的 ~15 处 dangling expression）
4. ~~**P3**：F541 f-string（简单替换）~~ ✅ **2026-06-26 已完成（74→0）**
5. **P4**：E711/E712/E722（风格改进，E711/E712 需区分 Python 比较与 ORM 查询）
6. ~~**P5**：Pydantic v2 `example=` 全仓统一~~ ✅ **2026-06-26 已完成（177→0，含 app/models/ 11 处 + 全仓 166 处）**
7. **长期**：mypy 类型标注补全（app/models/ 真实 bug 已清，剩余 ORM 债待 SQLAlchemy 2.0 迁移）
