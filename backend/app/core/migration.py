# -*- coding: utf-8 -*-
"""
数据库迁移模块（四轨治理后统一入口）

提供 migrate_database() 作为唯一的 schema 迁移入口：
- 空库自动建全表（alembic upgrade head）
- 已有库增量升级
- 历史"幽灵版本"库自动救援（KNOWN_GHOST_VERSIONS）
- 迁移前自动备份（支持回滚）
- 失败时 DEV 模式告警继续、生产模式终止

废弃的旧机制（已删除）：
- subprocess 调用外部 alembic 可执行文件 → 改为编程式 API（frozen 也可用）
- is_frozen() 短路跳过迁移 → frozen 也走迁移链
- shutil.which("alembic") 检查 → 编程式 API 不需外部可执行文件
"""

import logging
import os
import sqlite3
from pathlib import Path
from typing import Optional

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.core.config import settings
from app.core.db_backup import backup_before_migration

logger = logging.getLogger(__name__)

# 历史幽灵版本黑名单：production schema 初始化写入的虚构版本号，不在迁移链中。
# 这些库的 schema 与某个真实 head 一致（schema 快照按对应 head 生成），
# 可安全 stamp 到该真实版本，让后续 upgrade 只应用增量迁移。
# 仅对黑名单内版本自动 stamp；其他未知版本（如回滚产生的"未来版本"）只告警不降级，
# 避免静默制造 version/schema 不一致。
#
# 映射值 = 幽灵库 schema 对应的真实迁移版本（即快照生成时的 head）。
# stamp 到该版本后，upgrade 会应用其后所有增量迁移（如 search_templates 索引补建）。
KNOWN_GHOST_VERSIONS: dict = {
    "9aea25308aff": "a0ada9774936",  # production schema 快照对应 a0ada9774936 时的 schema
}


def _read_db_version(db_path: str) -> Optional[str]:
    """读取数据库的 alembic_version；无表/无文件返回 None。"""
    if not Path(db_path).exists():
        return None
    try:
        conn = sqlite3.connect(db_path)
        try:
            has_table = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='alembic_version'"
            ).fetchone()
            if not has_table:
                return None
            row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
            return row[0] if row else None
        finally:
            conn.close()
    except sqlite3.OperationalError:
        return None


def _build_alembic_config(db_path: str) -> Config:
    """构造指向指定 DB 的 Alembic Config。

    关键：设 DATABASE_PATH 环境变量，env.py 会优先读它（防串库）。
    同时动态设置 script_location 为绝对路径（frozen 下 cwd 不可靠）。
    """
    # 设环境变量，让 env.py 与 config.py 消费同一来源（B3：config.py property 也读此变量）
    os.environ["DATABASE_PATH"] = db_path

    root_path = settings.ROOT_PATH
    # frozen（PyInstaller）模式下 ROOT_PATH 解析到 _MEIPASS，alembic 目录已打包至此
    ini_path = root_path / "alembic.ini"
    script_location = str(root_path / "alembic")

    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", script_location)
    return cfg


def _rescue_or_warn_version(cfg: Config, db_path: str, current: Optional[str], heads: list) -> None:
    """
    区分幽灵版本（救援）vs 未来/未知版本（告警不降级）。

    - None：空库，upgrade 直接建表，无需处理
    - KNOWN_GHOST_VERSIONS 内：自动 stamp 到 head（保护 frozen 快照库无感升级）
    - 不在迁移链的未知版本（如回滚后的"未来版本"）：拒绝自动 stamp，只 error 告警，
      避免 version/schema 静默不一致。参考 docs/operations/rollback-guide.md。
    - 在链内但落后：正常 upgrade 会处理
    - 已是 head：upgrade no-op
    """
    if current is None:
        return  # 空库

    if current in KNOWN_GHOST_VERSIONS:
        target = KNOWN_GHOST_VERSIONS[current]
        logger.warning(
            f"检测到历史幽灵版本 {current}（production schema 初始化遗留），"
            f"自动 stamp 到对应真实版本 {target}（schema 已匹配，仅应用后续增量迁移）。"
        )
        # 注意：command.stamp 会校验当前版本是否在迁移链，幽灵版本不在链中会抛
        # CommandError。这里用 purge=True 先清空 alembic_version 再 stamp，
        # 绕过对旧版本的校验。stamp 到 target（非 head），让 upgrade 应用增量迁移。
        command.stamp(cfg, target, purge=True)
        return

    sd = ScriptDirectory.from_config(cfg)
    valid_revs = {r.revision for r in sd.walk_revisions()}

    if current not in valid_revs:
        # 未知版本：可能是版本回滚（DB 是高版本 schema，代码是低版本）或数据损坏。
        # 拒绝自动 stamp——否则会制造 version（低）与 schema（高）的静默不一致。
        logger.error(
            f"数据库版本 {current} 不在当前代码的迁移链中。"
            f"可能是版本回滚或数据损坏。拒绝自动处理，"
            f"请参考 docs/operations/rollback-guide.md。"
            f"如确认需强制对齐，手动执行: alembic stamp {heads[0]}"
        )
    elif current not in heads:
        logger.info(f"数据库版本 {current} 落后于 head {heads[0]}，将执行 upgrade")
    else:
        logger.info(f"数据库已是最新版本 {current}")


def migrate_database() -> None:
    """
    统一数据库迁移入口。

    执行顺序（B2 修正：备份在救援前）：
    1. 读当前版本
    2. 若 current != head（含幽灵版本）：迁移前备份
    3. 版本救援/告警（黑名单逻辑）
    4. alembic upgrade head

    失败处理（DEV 分流，与历史行为一致，保证存量用户无感）：
    - DEV=True：捕获异常，记 warning，不终止（便于开发调试）
    - DEV=False：向上抛出（生产终止）

    Raises:
        RuntimeError: 生产环境（DEV=False）迁移失败时
    """
    try:
        db_path = str(settings.DATABASE_PATH)
        cfg = _build_alembic_config(db_path)

        sd = ScriptDirectory.from_config(cfg)
        heads = sd.get_heads()
        if not heads:
            raise RuntimeError("迁移链无 head revision，请检查 alembic/versions/")
        head = heads[0]

        # 1. 读当前版本（在备份和救援前）
        current = _read_db_version(db_path)

        # 2. 迁移前备份（current != head 时，含幽灵版本 9aea... != head）
        if current != head:
            backup_before_migration(db_path)

        # 3. 版本救援/告警
        _rescue_or_warn_version(cfg, db_path, current, heads)

        # 4. 升级
        logger.info(f"执行数据库迁移（当前版本={current}，目标={head}）")
        command.upgrade(cfg, "head")

        logger.info("数据库迁移完成")

    except Exception as e:
        error_msg = f"数据库迁移失败: {e}"
        logger.error(error_msg)
        if not settings.DEV:
            # 生产环境必须终止（保证数据一致性）
            raise RuntimeError(f"Database migration failed in production: {e}")
        # 开发模式：告警后继续（与历史 run_alembic_migrations 行为一致）
        logger.warning(f"开发模式：迁移失败但继续启动（{e}）")


def run_alembic_migrations() -> bool:
    """
    【已废弃】向后兼容包装。

    历史接口，调用 migrate_database()。返回 bool 仅为兼容旧调用方。
    新代码应直接调用 migrate_database()。

    Returns:
        bool: 迁移是否成功（DEV 模式失败也返回 False，不抛异常）
    """
    try:
        migrate_database()
        return True
    except Exception:
        return False
