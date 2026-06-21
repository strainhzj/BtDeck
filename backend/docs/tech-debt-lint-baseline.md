# Lint 技术债基线（2026-06-21）

> 本文档记录 lint 门禁建立时豁免的历史问题，作为后续逐步清理的清单。
> 门禁策略：历史问题豁免（见 .flake8 extend-ignore），**新增代码必须通过门禁**。

## flake8 豁免规则（.flake8 extend-ignore）

| 规则 | 说明 | 数量（建立时） | 清理方式 |
|------|------|---------------|---------|
| E203 | 冒号前空格（与 black 冲突） | 11 | 永久忽略（black 官方推荐） |
| E402 | 模块级 import 不在顶部 | 18 | 逐步重构 import 顺序 |
| E501 | 行太长（历史 SQL/URL 字符串） | 34 | 逐步拆分长字符串 |
| E711/E712 | 与 None/False 比较 | 47 | 逐步改 is/is not |
| E722 | 裸 except | 2 | 改为具体异常 |
| E741 | 模糊变量名 l | 2 | 重命名 |
| F401 | 未使用 import | 327 | `autoflake --remove-all` 批量清 |
| F541 | f-string 无占位符 | 74 | 逐步改普通字符串 |
| F811 | 重定义（条件 import） | 30 | 逐步重构 |
| F841 | 局部变量赋值未用 | 44 | 逐步删除 |
| W503/W504 | 二元运算符换行 | — | 永久忽略（与 black 冲突） |
| W605 | 无效转义序列 | 4 | 改 raw string |

## 真实 bug（F821/F824，per-file-ignores 豁免）

这些是 undefined name / global 误用，在异常/边界路径，平时不触发但应修复：

| 文件 | 行 | 问题 | 修复方向 |
|------|-----|------|---------|
| app/utils/audit_logger.py | 437,444,534,537,541 | F821: `desc`/`logger` 未定义 | 补 `from sqlalchemy import desc` + `logger = logging.getLogger(__name__)` |
| app/api/endpoints/torrent_crud.py | 99,103 | F821: `req` 应为 `request` | 改为 FastAPI 标准的 `request` |
| app/api/endpoints/torrent_deletion.py | 654 | F821: `request` 未定义 | 确认参数来源 |
| app/services/tag_service.py | 223 | F821: `tags` 可能未定义 | 初始化默认值 |
| app/downloader/initialization.py | 960,983,1390 | F821: `app` 未定义 | 补 import 或改引用方式 |
| app/downloader/initialization.py | 1022,1061,1093,1126 | F824: global 未赋值 | 删除无用的 global 声明 |
| app/core/security.py | 256 | F824: global 未赋值 | 删除无用的 global 声明 |

## mypy 历史问题

mypy 1649 个错误（历史类型标注缺失）。当前配置宽松（`check_untyped_defs=false`）。
清理策略：新增代码逐步补全类型标注，最终收紧 strict。优先清理的模块：
- app/models/（ORM 模型，类型相对清晰）
- app/core/（核心逻辑，类型安全价值高）
- app/services/（业务逻辑）

## 清理优先级

1. **P0**：F821 真实 bug（运行时潜在崩溃）
2. **P1**：F401 未用 import（autoflake 一键清理，最大收益）
3. **P2**：F841 未用变量（简单删除）
4. **P3**：F541 f-string（简单替换）
5. **P4**：E711/E712/E722（风格改进）
6. **长期**：mypy 类型标注补全
