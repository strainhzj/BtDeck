"""hash_lowercase_normalization

【数据迁移；downgrade 为 no-op（单向口径归一，见文件尾说明）】种子 hash 统一小写口径（P0-D，rTorrent 接入前置）。

背景：
- qBittorrent 同步路径落库前已强制 ``.lower()``，但 Transmission 路径原样
  落库大写 ``hashString``，导致 ``torrent_info.hash`` 存量大小写混存；
  ``idx_torrent_hash_unique (hash, downloader_id)`` 与运行时复合键
  ``(downloader_id, hash)``（速度终态收敛 / RuntimeListMembershipTracker /
  /runtime-state/reconcile）均为大小写敏感比较，同一种子在不同下载器
  侧会形成两套身份。
- rTorrent 返回大写 hash，接入前必须统一口径：全链路落库/匹配一律小写。

本迁移对存量数据一次性归一（SQLite 幂等）：
1. ``torrent_info.hash``：小写化。唯一部分索引 idx_torrent_hash_unique
   (hash, downloader_id) 在同一下载器同时存在大小写两行的脏数据场景下会
   冲突，使用 ``UPDATE OR IGNORE`` 保留先扫描到的一行（正常数据不会触发）。
2. ``torrent_file_backup.info_hash``：小写化（全局唯一索引；qB 小写与
   TR 大写的重复备份行 lower 化后冲突时保留其一，属预期去重）。
3. ``sync_checkpoints.cursor_value``：小写化。qB cursor 本就小写（幂等）；
   TR cursor 为大写字典序，代码侧已切换小写字典序后必须同步归一，否则
   续跑比较 ``hash > cursor`` 永假导致同步全量重扫。

不动的历史/审计表（保留原始事实，不参与功能匹配）：
- ``torrent_deletion_audit_log.torrent_hash``、``seed_transfer_audit_log.info_hash``
- ``tracker_info.torrent_info_id``（存的是种子 info_id UUID，非 hash）

Revision ID: a1f7c9e3d2b4
Revises: 053003337878
Create Date: 2026-09-23

"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "a1f7c9e3d2b4"
down_revision: Union[str, Sequence[str], None] = "053003337878"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """存量 hash 数据一次性小写归一（幂等，可安全重复执行）。

    容错说明：生产漂移库（version 标记正常但部分业务表缺失，见
    tests/core/test_orphan_schema_repair_migration.py 模拟形态）升级时，
    缺失的目标表直接跳过（后续 restart 自愈流程负责补建 schema 后，
    下一轮迁移/同步会以小写口径写入新数据，无需重跑本迁移）。
    """
    existing_tables = set(inspect(op.get_bind()).get_table_names())
    if "torrent_info" in existing_tables:
        op.execute(
            "UPDATE OR IGNORE torrent_info " "SET hash = lower(hash) " "WHERE hash IS NOT NULL AND hash != lower(hash)"
        )
    if "torrent_file_backup" in existing_tables:
        op.execute(
            "UPDATE OR IGNORE torrent_file_backup "
            "SET info_hash = lower(info_hash) "
            "WHERE info_hash IS NOT NULL AND info_hash != lower(info_hash)"
        )
    if "sync_checkpoints" in existing_tables:
        op.execute(
            "UPDATE OR IGNORE sync_checkpoints "
            "SET cursor_value = lower(cursor_value) "
            "WHERE cursor_value IS NOT NULL AND cursor_value != lower(cursor_value)"
        )


def downgrade() -> None:
    """no-op（保持迁移链可 downgrade）：

    小写化是单向数据口径归一，无法从 lower 值恢复原始大小写；但本项目
    迁移链测试/回滚演练要求 downgrade 可执行（参照基线迁移 e2a02abcf912
    的"可执行但危险"模式）。此处 no-op 不破坏 schema，仅放弃恢复大小写。
    真正回滚请参考 docs/operations/rollback-guide.md（备份恢复路径）。
    """
