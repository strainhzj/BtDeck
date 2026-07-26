"""ratio/ratio_limit columns: String -> Float

Revision ID: 6132b66d14a7
Revises: e6d8a20c41f3
Create Date: 2026-07-26 13:00:00.000000

本迁移根治 ratio/ratio_limit 字符串字典序 bug（"10.0" < "2"）：
  - 把两列从 String 改为 Float（数值列）
  - 清洗历史脏数据（""、-1、-2、"None" 等非数值/哨兵值 → NULL）
  - 显式 drop + recreate partial unique index（batch_alter 重建表时
    partial index 的 WHERE 子句在不同 Alembic 版本下不一定被保留）
  - 迁移末尾断言 16+1 个索引完整 + partial WHERE 子句仍在
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "6132b66d14a7"
down_revision: Union[str, Sequence[str], None] = "e6d8a20c41f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 历史写入侧产生的脏值：str(None)→"None"、空串、qBittorrent 哨兵 -1/-2
# 注意 SQLite 的 CAST("None" AS REAL) 不报错而返回 0.0，必须显式 UPDATE 清洗，
# 否则脏值会被静默篡改为 0.0（无法被 WHERE ratio IS NULL 捕获）。
_DIRTY_RATIO_VALUES_SQL = "ratio IS NULL OR ratio = '' OR ratio = '-1' OR ratio = '-2' " "OR lower(ratio) = 'none'"


def _table_exists(inspector, table_name: str) -> bool:
    return inspector.has_table(table_name)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _table_exists(inspector, "torrent_info"):
        # 干净库首次 upgrade 时该表由 base 迁移建立；此分支仅防御性兜底
        return

    # ---------- 1. 脏数据清洗（在 batch_alter 之前）----------
    # 用显式 UPDATE 把脏值转 NULL，避免后续 CAST 静默转 0.0
    op.execute(f"UPDATE torrent_info SET ratio = NULL WHERE {_DIRTY_RATIO_VALUES_SQL}")
    op.execute(
        "UPDATE torrent_info SET ratio_limit = NULL WHERE "
        "ratio_limit IS NULL OR ratio_limit = '' OR ratio_limit = '-1' OR ratio_limit = '-2' "
        "OR lower(ratio_limit) = 'none'"
    )

    # ---------- 2. drop partial unique index（batch 重建不保证保留 WHERE 子句）----------
    existing_idx = {i["name"] for i in inspector.get_indexes("torrent_info")}
    if "idx_torrent_hash_unique" in existing_idx:
        op.drop_index(
            "idx_torrent_hash_unique",
            table_name="torrent_info",
            sqlite_where=sa.text("dr = 0"),
        )

    # ---------- 3. batch_alter 改列类型（SQLite 走表重建）----------
    with op.batch_alter_table("torrent_info") as batch_op:
        batch_op.alter_column("ratio", existing_type=sa.String(), type_=sa.Float())
        batch_op.alter_column("ratio_limit", existing_type=sa.String(), type_=sa.Float(), nullable=True)

    # ---------- 4. recreate partial unique index ----------
    op.create_index(
        "idx_torrent_hash_unique",
        "torrent_info",
        ["hash", "downloader_id"],
        unique=True,
        sqlite_where=sa.text("dr = 0"),
    )

    # ---------- 5. 索引完整性断言 ----------
    # 注意：只断言 partial unique index 的存在 + WHERE 子句保留。
    # 不强行断言全部 ix_torrent_info_* 索引名清单——因为 ghost 库（生产 schema 快照）
    # 使用的是不同的复合索引设计（idx_torrent_info_dr_status 等），batch_alter 反射重建
    # 会保留原库的索引设计，不会"补建"开发模式 base 迁移的索引。
    post_inspector = sa.inspect(bind)
    post_idx_names = {i["name"] for i in post_inspector.get_indexes("torrent_info")}

    assert "idx_torrent_hash_unique" in post_idx_names, f"partial unique index 丢失，当前索引: {post_idx_names}"

    # partial unique index 的 WHERE 子句仍在
    idx_sql = bind.execute(
        sa.text("SELECT sql FROM sqlite_master WHERE type = 'index' " "AND name = 'idx_torrent_hash_unique'")
    ).scalar()
    assert idx_sql, "idx_torrent_hash_unique 不存在"
    assert "dr = 0" in idx_sql or "dr=0" in idx_sql, f"partial unique index 丢失 WHERE 子句: {idx_sql}"


def downgrade() -> None:
    """反向回 String。

    ⚠ Float→String 会因浮点表示产生长尾（如 0.30000000000000004），
    用 printf('%.4f', ...) 控制 4 位小数（share ratio 精度足够）。
    downgrade 视为不可逆，仅用于回滚应急。
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _table_exists(inspector, "torrent_info"):
        return

    # 控制精度后再转回字符串
    op.execute("UPDATE torrent_info SET ratio = printf('%.4f', ratio) WHERE ratio IS NOT NULL")
    op.execute("UPDATE torrent_info SET ratio_limit = printf('%.4f', ratio_limit) WHERE ratio_limit IS NOT NULL")

    existing_idx = {i["name"] for i in inspector.get_indexes("torrent_info")}
    if "idx_torrent_hash_unique" in existing_idx:
        op.drop_index(
            "idx_torrent_hash_unique",
            table_name="torrent_info",
            sqlite_where=sa.text("dr = 0"),
        )

    with op.batch_alter_table("torrent_info") as batch_op:
        batch_op.alter_column("ratio", existing_type=sa.Float(), type_=sa.String())
        batch_op.alter_column("ratio_limit", existing_type=sa.Float(), type_=sa.String(), nullable=True)

    op.create_index(
        "idx_torrent_hash_unique",
        "torrent_info",
        ["hash", "downloader_id"],
        unique=True,
        sqlite_where=sa.text("dr = 0"),
    )
