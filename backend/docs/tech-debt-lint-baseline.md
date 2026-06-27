# Lint 技术债基线（2026-06-21）

> 本文档记录 lint 门禁建立时豁免的历史问题，作为后续逐步清理的清单。
> 门禁策略：历史问题豁免（见 .flake8 extend-ignore），**新增代码必须通过门禁**。

## 清理进度（2026-06-27 更新）

| 规则 | 建立时数量 | 当前数量 | 状态 |
|------|-----------|---------|------|
| **Pydantic `example=`** | 177 | 0 | ✅ **已全部清理**（app/models/ 11 处 + 全仓 166 处，`example=X`→`examples=[X]`，补全被忽略的 OpenAPI schema 示例值） |
| **E722/E741** | 4 | 0 | ✅ **已全部清理 + 进门禁**（2 裸 except 改 except Exception + 2 模糊变量名 l 改 label） |
| **F811** | 15 | 0 | ✅ **已全部清理 + 进门禁**（第七轮：cuser.py 同名 twofa_verify 改名 + torrents_async.py 删 678 行 copy-paste 过期副本） |
| **E711/E712** | 47 | 0 | ✅ **已全部清理 + 进门禁**（第七轮：44 处 ORM 改 `.is_()` + 3 处 Python 条件改 `is`/直接判断；downloader.py 4 处 `delay==False` 因 0==False 真值陷阱用 inline noqa 保留==） |
| **F841** | 23 | 0 | ✅ **已全部清理 + 进门禁**（8 文件 23 处：16 except as e 去绑定 + 5 torrents 健康检查去赋值保调用 + manager/module 去赋值保调用） |
| **F541** | 74 | 0 | ✅ **已全部清理 + 进门禁**（26 文件 74 处无占位符 f-string，2 处多行拼接手工处理） |
| **F821/F824** | 17 | 0 | ✅ **已全部修复 + 进门禁**（6 文件 17 处真实 bug，per-file-ignores 已移除） |
| **F401** | 327 | 9 | ✅ **已清理 + 进门禁**（autoflake 清 310 个，9 个 database.py ORM 注册 import 保留） |
| mypy app/models/ | 145 | 133 | 🔶 清了 12 个真实 bug（11 个 Pydantic v2 `example=` + 1 个 `by_alias` 死键），剩 133 个归 ORM 债（评估报告见下） |

## flake8 豁免规则（.flake8 extend-ignore）

| 规则 | 说明 | 数量（建立时） | 清理方式 |
|------|------|---------------|---------|
| E203 | 冒号前空格（与 black 冲突） | 11 | 永久忽略（black 官方推荐） |
| E402 | 模块级 import 不在顶部 | 18 | 逐步重构 import 顺序 |
| E501 | 行太长（历史 SQL/URL 字符串） | 34 | 逐步拆分长字符串 |
| ~~E711/E712~~ | ~~与 None/False 比较~~ | ~~47~~ | ✅ **2026-06-27 已清理**（47→0，44 处 ORM 改 `.is_()` + 3 处 Python 条件；4 处 `delay==False` 因 0==False 真值陷阱 inline noqa 保留==，从 extend-ignore 移除进入门禁） |
| ~~E722~~ | ~~裸 except~~ | ~~2~~ | ✅ **2026-06-26 已清理**（2→0，改 except Exception，进入门禁） |
| ~~E741~~ | ~~模糊变量名 l~~ | ~~2~~ | ✅ **2026-06-26 已清理**（2→0，l 改 label，进入门禁） |
| ~~F401~~ | ~~未使用 import~~ | ~~327~~ | ✅ **2026-06-25 已清理**（321→9，F401 已从 extend-ignore 移除进入门禁，仅 database.py 9 个 ORM 注册 import 走 per-file-ignore） |
| ~~F541~~ | ~~f-string 无占位符~~ | ~~74~~ | ✅ **2026-06-26 已清理**（74→0，从 extend-ignore 移除进入门禁） |
| ~~F811~~ | ~~重定义（条件 import）~~ | ~~30~~ | ✅ **2026-06-27 已清理**（15→0，cuser 改名 + torrents_async 删过期副本，从 extend-ignore 移除进入门禁） |
| ~~F841~~ | ~~局部变量赋值未用~~ | ~~44~~ | ✅ **2026-06-26 已清理**（23→0，从 extend-ignore 移除进入门禁；含 except as e 去绑定、torrents 健康检查去赋值保调用） |
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
3. ~~**P2**：F841 未用变量~~ ✅ **2026-06-26 已完成（23→0）**
4. ~~**P3**：F541 f-string（简单替换）~~ ✅ **2026-06-26 已完成（74→0）**
5. ~~**P4**：E711/E712~~ ✅ **2026-06-27 已完成（47→0，44 处 ORM 改 `.is_()` + 3 处 Python 条件，进入门禁）**
6. ~~**P5**：Pydantic v2 `example=` 全仓统一~~ ✅ **2026-06-26 已完成（177→0，含 app/models/ 11 处 + 全仓 166 处）**
7. ~~**P6**：E722 裸 except + E741 模糊变量名~~ ✅ **2026-06-26 已完成（4→0，进入门禁）**
8. ~~**P7**：F811 重定义~~ ✅ **2026-06-27 已完成（15→0，cuser 改名 + torrents_async 删过期副本，进入门禁）**
9. **长期**：mypy 类型标注补全（app/models/ 真实 bug 已清，剩余 133 ORM 债待 SQLAlchemy 2.0 迁移，评估报告见下）

## ~~高风险遗留项（需单独处理，不混入常规 lint 清理）~~ ✅ 2026-06-27 F811 + E711/E712 已全部完成

| 项 | 位置 | 问题 | 风险 | 状态 |
|----|------|------|------|------|
| ~~F811 重复函数定义~~ | `app/api/endpoints/torrents_async.py` | `qb/tr_add_torrents_info_only_async` 各定义 3 次。经 AST 对比 + git 历史追溯（73df90c）确认：tr 三份完全一致（IDENTICAL），qb 前两份一致（含 tracker 富集）、第三份有意去掉富集（tracker 同步已拆分到 `qb_sync_trackers_only_async`），第三份才是生效版。删除前两组过期副本（-678 行） | 高（删错改变行为） | ✅ **2026-06-27 已完成** |
| ~~F811 同名函数~~ | `app/api/endpoints/cuser.py` | `twofa_verify` 定义两次（115/150），分别绑不同路由路径。FastAPI 按路径注册故两条都正常工作，仅模块级变量被后者覆盖（无调用点）。改名为 `twofa_verify_qrcode`/`twofa_verify_code` 消除 F811 | 低（无害，改名） | ✅ **2026-06-27 已完成** |
| ~~E711/E712 ORM 查询~~ | 全仓 47 处 | `== None`/`== True`/`== False` 中 ORM `.filter()` 里是合法表达式（生成 IS 语句），盲改 `is` 会破坏查询。逐个甄别：44 处 ORM 改 `.is_()` + 3 处 Python 条件改 `is`/直接判断；4 处 `delay==False` 因 0==False 真值陷阱 inline noqa 保留==（用户决策） | 高（需逐个甄别） | ✅ **2026-06-27 已完成** |

> **lint 技术债清理总览（7 轮，2026-06-25 ~ 2026-06-27）**：除 W605（4 处无效转义序列）、E402/E501（风格类永久/逐步项）、mypy ORM 债（架构级，见下评估）外，所有进入 extend-ignore 的历史问题已全部清理并进入全仓门禁。`.flake8` 的 extend-ignore 现仅剩 E203/E402/E501/W503/W504/W605 六项（均为风格/格式类）。

---

## mypy app/models/ ORM 债评估报告（2026-06-27，任务 C，只评估不实施）

> 本节是 lint 技术债清理第七轮任务 C 的产出。按项目要求**只做评估、不实施代码改动**，
> 结论交付用户决策是否单独立项。

### 一、现状快照

- **错误数**：`mypy app/models/` 报 **133 errors in 9 files**（checked 17 source files）
- **类别分布**：
  | 类别 | 数量 | 占比 |
  |------|------|------|
  | `assignment` | 117 | 87.9% |
  | `return-value` | 10 | 7.5% |
  | `arg-type` | 4 | 3.0% |
  | `var-annotated` | 2 | 1.5% |
- **错误文件分布**（9 个文件）：
  | 文件 | 错误数 |
  |------|--------|
  | torrent_deletion_audit_log.py | 26 |
  | seed_transfer_audit_log.py | 25 |
  | downloader_capabilities.py | 19 |
  | downloader_path_maintenance.py | 17 |
  | torrent_file_backup.py | 16 |
  | torrent_tags.py | 13 |
  | search_template.py | 8 |
  | notification.py | 7 |
  | downloader_settings.py | 2 |
- **依赖现状**：**SQLAlchemy 已是 2.0.47**（无需升级依赖），但**未启用 mypy 插件**
  （`pyproject.toml` 无 `plugins = sqlalchemy.ext.mypy.plugin`，未装 sqlalchemy2-stubs）

### 二、根因分析

133 个错误 **100% 源于 ORM 描述符类型推断失败**，非真实运行时 bug：

1. **`assignment`（117，最大头）**：`Base = declarative_base()`（SQLAlchemy 1.4 风格，
   定义在 `app/database.py:47`）下，`class X(Base)` 内的字段定义为
   `name = Column(String)`，mypy 把 `name` 的类型推断为 `Column[str]`（描述符对象），
   而非运行时的标量 `str`。于是构造函数 `__init__`/实例赋值
   `obj.name = "x"`（字符串赋值给 `Column[str]`）触发类型冲突。

2. **`return-value`（10）**：`@property` 方法声明 `-> bool` 返回值，
   但函数体 `return self.deletion_status == X` 中 `Column.__eq__` 返回
   `ColumnElement[bool]`，与声明的标量 `bool` 不兼容。
   （如 `torrent_deletion_audit_log.py:296/305/314/323`）

3. **`arg-type`（4）**：`json.loads(self.config_json)` 把 `Column[str]` 传给
   期望 `str` 的函数。

4. **`var-annotated`（2）**：`Column(SQLEnum(...))` 的泛型推断失败。

**这 133 个都是"类型工具看不懂 ORM 魔法"的假阳性，运行时行为完全正确。**

### 三、可行方案对比

| 方案 | 工作量 | 收益 | 风险 | 推荐度 |
|------|--------|------|------|--------|
| **A. 迁移到 SQLAlchemy 2.0 声明式**（`DeclarativeBase` + `Mapped[]`/`mapped_column()`） | 高（17 文件 146 字段 + 25 个类的 `__init__`/构造调用面） | 彻底消除 133 错误，获得完整类型安全，跟随官方现代写法 | 中（需逐字段标注类型，构造函数签名要配套调整，跨 39 处引用点需回归测试） | ⭐⭐⭐⭐ 长期最优 |
| **B. 启用 sqlalchemy mypy 插件**（`plugins = sqlalchemy.ext.mypy.plugin`） | 低（改 pyproject 配置） | 插件能识别 `declarative_base()` 模式，自动推断描述符为标量，**可批量消除大部分错误** | 低-中（插件已被 SQLAlchemy 2.0 标记 deprecated，推荐用方案 A 的 Mapped 取代；过渡方案） | ⭐⭐⭐ 短期过渡 |
| **C. 保持现状（当前）** | 0 | 0 | 低（133 个假阳性噪音，掩盖真实类型问题） | ⭐⭐ 不作为 |

### 四、方案 A（推荐，长期）工作量评估

若实施 SQLAlchemy 2.0 声明式迁移：

1. **核心改动**：
   - `app/database.py`：`Base = declarative_base()` → `class Base(DeclarativeBase): pass`
   - 17 个模型文件、25 个类、**146 个 Column 字段**改为 `Mapped[T]` + `mapped_column()`
2. **配套调整**：
   - 各模型自定义 `__init__`（如 downloader/models.py:36）需与新声明式兼容
   - 39 个引用模型文件的模块需回归测试（构造、查询、属性访问）
   - Alembic 迁移文件（app/migrations/，已 exclude）不受影响（用 metadata）
3. **建议拆分**（降低单次风险）：
   - 阶段 1：`Base` 声明改造 + 1-2 个简单模型试点（downloader_settings.py 2 错误最少）
   - 阶段 2：按错误数从少到多逐文件迁移，每文件 commit + pytest
   - 阶段 3：启用 mypy 严格化（`check_untyped_defs` 等）
4. **预估**：纯工作量约 2-3 个完整会话，需配套测试覆盖。

### 五、本次结论与建议

- **本次不实施**（遵照任务 C 要求），评估报告已交付。
- **建议**：作为**独立技术债任务单独立项**（SQLAlchemy 2.0 声明式迁移），
  不混入 lint 清理。优先级低于功能开发，可在 v1.0.8「数据库升级」版本周期内安排。
- **若要快速降噪**：可临时启用方案 B（mypy 插件），在 pyproject.toml 加
  `plugins = sqlalchemy.ext.mypy.plugin`，低成本消除大部分假阳性，作为方案 A 落地前的过渡。
  （需先验证插件对该代码库的实际效果，再决定是否采用。）
