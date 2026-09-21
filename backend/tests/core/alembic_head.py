# -*- coding: utf-8 -*-
"""Alembic head 单一真相源（测试用）。

背景：`c1d2e3f4a5b6` 曾在 4 个测试文件里硬编码为「当前 head」，
P3-2 新增 `b3e5f7a9c1d2`（search_templates.preset_key）后未同步，
导致远端 CI 自那时起后端 job 长期变红（干净检出即可复现）。

约定：
- **「当前 head」一律用 `current_head()` 动态读取**，不在测试里写死字符串；
- 「链上某个历史 revision」（如迁移前置版本）可以写常量，但注释必须写明
  它是历史锚点而非 head；
- 唯一允许把 head 写死的地方是 `tests/core/test_db_migration.py::EXPECTED_HEAD`
  ——那是**故意的漂移检测器**（新增迁移时必须显式更新，从而强制作者确认
  链路变更），并由该文件断言它与 `current_head()` 一致；
  约束文档 `backend/docs/constraints/database-migration.md` 的 HEAD 声明
  同样由该文件校验（防文档漂移）。
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


def build_alembic_config(db_path: str | None = None) -> Config:
    """构造 Alembic 配置；传入 db_path 时设置 DATABASE_PATH 环境变量。

    注意：调用方需自行管理 DATABASE_PATH 的清理（仓内测试以 autouse fixture 处理）。
    """
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    cfg.attributes["configure_logger"] = False
    if db_path is not None:
        import os

        os.environ["DATABASE_PATH"] = str(db_path)
    return cfg


def current_head() -> str:
    """从迁移脚本目录动态读取当前唯一 head（不依赖数据库连接）。

    多 head 视为配置错误直接抛错（与 app/core/migration.py 的启动行为一致）。
    """
    sd = ScriptDirectory.from_config(build_alembic_config())
    heads = sd.get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"迁移链应恰好 1 个 head，实际 {heads}")
    return heads[0]


def revision_count() -> int:
    """迁移链 revision 总数（供文档/元信息一致性校验）。"""
    sd = ScriptDirectory.from_config(build_alembic_config())
    return len(list(sd.walk_revisions()))
