# -*- coding: utf-8 -*-
"""
数据库迁移模块（四轨治理后统一入口）

提供 migrate_database() 作为唯一的 schema 迁移入口：
- 空库自动建全表（alembic upgrade head）
- 已有库增量升级
- 历史"幽灵版本"库自动救援（KNOWN_GHOST_VERSIONS）
- 迁移前自动备份（支持回滚）
- DEV 模式向调用方返回失败、生产模式抛错；所有应用入口都会 fail-fast

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
from app.core.db_backup import MigrationBackupError, backup_before_migration

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
    """读取数据库的 alembic_version；无表/无文件返回 None（SQLite 方言）。"""
    if not Path(db_path).exists():
        return None
    try:
        conn = sqlite3.connect(db_path)
        try:
            has_table = conn.execute(
                "SELECT name FROM sqlite_master " "WHERE type='table' AND name='alembic_version'"
            ).fetchone()
            if not has_table:
                return None
            row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
            return row[0] if row else None
        finally:
            conn.close()
    except sqlite3.OperationalError:
        return None


def _read_db_version_dispatch(db_path: str) -> Optional[str]:
    """按方言分发版本读取（v1.0.8 任务1.7）：PG 走引擎连接读（契约 §3）。"""
    if settings.DATABASE_DIALECT == "postgresql":
        from app.core.pg_baseline import read_pg_version_standalone

        return read_pg_version_standalone()
    return _read_db_version(db_path)


def _build_alembic_config(db_path: str) -> Config:
    """构造指向指定 DB 的 Alembic Config。

    关键：设 DATABASE_PATH 环境变量，env.py 会优先读它（防串库）。
    同时动态设置 script_location 为绝对路径（frozen 下 cwd 不可靠）。
    """
    # 设环境变量，让 env.py 与 config.py 消费同一来源（B3：config.py property 也读此变量）；
    # 仅 SQLite 方言（PG 不消费文件路径，v1.0.8 契约 §2.1）
    if settings.DATABASE_DIALECT == "sqlite":
        os.environ["DATABASE_PATH"] = db_path

    root_path = settings.ROOT_PATH
    # frozen（PyInstaller）模式下 ROOT_PATH 解析到 _MEIPASS，alembic 目录已打包至此
    ini_path = root_path / "alembic.ini"
    script_location = str(root_path / "alembic")

    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", script_location)
    return cfg


def _rescue_or_warn_version(
    cfg: Config,
    db_path: str,
    current: Optional[str],
    heads: list,
) -> Optional[bool]:
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
        return True  # 空库

    if current in KNOWN_GHOST_VERSIONS:
        target = KNOWN_GHOST_VERSIONS[current]
        # 防御：黑名单映射的 target 必须在迁移链中，否则 command.stamp 会抛 CommandError
        sd = ScriptDirectory.from_config(cfg)
        valid_revs = {r.revision for r in sd.walk_revisions()}
        if target not in valid_revs:
            logger.error(
                f"幽灵版本 {current} 的映射目标 {target} 不在迁移链中（配置错误），"
                f"拒绝 stamp。请检查 KNOWN_GHOST_VERSIONS 配置。"
            )
            return False
        logger.warning(
            f"检测到历史幽灵版本 {current}（production schema 初始化遗留），"
            f"自动 stamp 到对应真实版本 {target}（schema 已匹配，仅应用后续增量迁移）。"
        )
        # 注意：command.stamp 会校验当前版本是否在迁移链，幽灵版本不在链中会抛
        # CommandError。这里用 purge=True 先清空 alembic_version 再 stamp，
        # 绕过对旧版本的校验。stamp 到 target（非 head），让 upgrade 应用增量迁移。
        command.stamp(cfg, target, purge=True)
        return True

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
        return None
    elif current not in heads:
        logger.info(f"数据库版本 {current} 落后于 head {heads[0]}，将执行 upgrade")
    else:
        logger.info(f"数据库已是最新版本 {current}")
    return True


def _migrate_database_pg() -> bool:
    """PG 方言迁移编排（v1.0.8 任务1.7，契约 §3）。

    - 导入未完成标记 → 拒绝启动（三状态规则）
    - 空库 → initialize_pg_baseline（共享基线函数，不 seed）
    - 已 stamp → 正常增量 upgrade；未知版本告警不降级（与 SQLite 口径一致）
    - 备份：PG 无文件备份链，显式日志提示外部备份职责（任务3.2）
    - ghost 救援：仅 SQLite 历史快照语义，PG 不启用（契约 §3 规则 7）
    """
    from app.core.pg_baseline import (
        get_import_state,
        initialize_pg_baseline,
        pg_sync_engine,
        read_pg_alembic_version,
        validate_pg_server,
    )

    db_path = str(settings.DATABASE_PATH)  # 仅作日志上下文；PG 不消费
    cfg = _build_alembic_config(db_path)
    cfg.attributes["configure_logger"] = False

    sd = ScriptDirectory.from_config(cfg)
    heads = sd.get_heads()
    if not heads:
        raise RuntimeError("迁移链无 head revision，请检查 alembic/versions/")
    if len(heads) > 1:
        raise RuntimeError(f"迁移链有 {len(heads)} 个 head（分叉）：{heads}。请先合并分叉（alembic merge）再启动。")
    head = heads[0]

    engine = pg_sync_engine()
    try:
        with engine.connect() as conn:
            validate_pg_server(conn)
            import_state = get_import_state(conn)
            if import_state is not None:
                raise RuntimeError(
                    f"检测到 SQLite→PG 导入未完成标记（migration_id={import_state['migration_id']}），"
                    "拒绝启动以防后台任务修改半成品数据；请重跑迁移工具或人工处理（契约 §3 三状态规则）"
                )
            current = read_pg_alembic_version(conn)
    finally:
        engine.dispose()

    if current is None:
        # 空库（或有表无版本 → 基线函数内部 fail-fast；连接失败 → 基线函数抛真实错误）
        logger.info("PG 库无 alembic_version：走 squash 基线初始化（契约 §3）")
        initialize_pg_baseline(cfg, head)
    else:
        valid_revs = {r.revision for r in sd.walk_revisions()}
        if current not in valid_revs:
            logger.warning(
                "PG 库版本 %s 不在当前代码迁移链中（可能回滚或数据损坏）；保留现状不降级（与 SQLite 口径一致）",
                current,
            )
            return True
        if current != head:
            logger.info(f"执行 PG 增量迁移（当前版本={current}，目标={head}）；备份由外部机制负责（任务3.2）")
            command.upgrade(cfg, "head")
        else:
            logger.info(f"PG 数据库已是最新版本 {current}")

    final_version = _read_db_version_dispatch(db_path)
    if final_version != head:
        raise RuntimeError(f"PG 迁移后版本仍为 {final_version}，预期 {head}")
    logger.info("PG 数据库迁移完成")
    return True


def migrate_database() -> bool:
    """
    统一数据库迁移入口。

    执行顺序（B2 修正：备份在救援前）：
    1. 读当前版本
    2. 若 current != head（含幽灵版本）：迁移前备份
    3. 版本救援/告警（黑名单逻辑）
    4. alembic upgrade head

    失败处理：
    - 迁移前备份失败：所有环境无条件终止，禁止绕过恢复点
    - DEV=True：捕获异常并返回 False；生命周期入口仍必须停止启动
    - DEV=False：向上抛出（生产终止）

    Raises:
        RuntimeError: 生产环境（DEV=False）迁移失败时
    """
    try:
        if settings.DATABASE_DIALECT == "postgresql":
            return _migrate_database_pg()
        db_path = str(settings.DATABASE_PATH)
        cfg = _build_alembic_config(db_path)
        # 应用启动期间不得让 Alembic fileConfig 覆盖 app.* 的 stdout handler，
        # 否则迁移首个异常会从 docker logs 中消失，只剩后续 ORM 二次错误。
        cfg.attributes["configure_logger"] = False

        sd = ScriptDirectory.from_config(cfg)
        heads = sd.get_heads()
        if not heads:
            raise RuntimeError("迁移链无 head revision，请检查 alembic/versions/")
        if len(heads) > 1:
            # 多 head（迁移链分叉）是危险状态，upgrade head 会报错。
            # 显式抛错而非隐式取 heads[0]，避免指向错误目标。
            raise RuntimeError(
                f"迁移链有 {len(heads)} 个 head（分叉）：{heads}。" f"请先合并分叉（alembic merge）再启动。"
            )
        head = heads[0]

        # 1. 读当前版本（在备份和救援前）
        current = _read_db_version_dispatch(db_path)

        # 2. 迁移前备份（current != head 时，含幽灵版本 9aea... != head）
        if current != head and Path(db_path).exists():
            backup_path = backup_before_migration(db_path)
            if not backup_path:
                raise RuntimeError("existing database has no validated pre-migration backup")

        # 3. 版本救援/告警
        version_action = _rescue_or_warn_version(cfg, db_path, current, heads)
        if version_action is False:
            raise RuntimeError(f"数据库版本 {current} 的救援配置无效，拒绝继续启动")
        if version_action is None:
            logger.warning(
                "数据库版本 %s 高于或不属于当前代码迁移链；保留现状以兼容显式代码回滚",
                current,
            )
            return True

        # 4. 升级
        logger.info(f"执行数据库迁移（当前版本={current}，目标={head}）")
        command.upgrade(cfg, "head")

        final_version = _read_db_version_dispatch(db_path)
        if final_version != head:
            raise RuntimeError(f"Alembic upgrade 返回后版本仍为 {final_version}，预期 {head}")

        logger.info("数据库迁移完成")
        return True

    except MigrationBackupError:
        # A destructive migration must never continue when its recovery point
        # cannot be trusted, including in DEV mode.
        logger.exception("迁移前备份未通过验证，已无条件阻止迁移")
        raise
    except Exception as e:
        error_msg = f"数据库迁移失败: {e}"
        logger.exception(error_msg)
        if not settings.DEV:
            # 生产环境必须终止（保证数据一致性）
            raise RuntimeError(f"Database migration failed in production: {e}")
        # 开发模式保留异常返回，便于工具调用方诊断；应用生命周期必须据此停止启动。
        logger.warning(f"开发模式：迁移失败，调用方必须拒绝启动依赖新 schema 的服务（{e}）")
        return False
