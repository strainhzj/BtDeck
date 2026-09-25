"""normalize_tr_added_date

【数据迁移；可回滚（downgrade 反向偏移）；⚠️ 不可重复执行——见文件尾警示】
TR added_date 时区口径回填（统计报表 W2 决策 8，PLANS/statistics-reports.md §3.1）。

背景：
- Transmission 同步路径此前直接落库 transmission_rpc 的 ``Torrent.added_date``
  属性，该属性在库内为 ``datetime.fromtimestamp(epoch, timezone.utc)`` ——
  aware UTC；ORM DateTime 落库取其墙钟 → DB 存的是 **UTC 墙钟**。
- qB 路径（``_parse_qb_epoch``，naive 本地）与 TR ``done_date``（库内
  ``fromtimestamp(epoch).astimezone()`` aware 本地）均为**本地墙钟**——
  TR added_date 比两者偏 8h（CN 部署）。
- W2 已把两条写入路径（全量 ``tr_add_torrents_async`` / info-only）改为
  ``_parse_qb_epoch(torrent_info.fields["addedDate"])``；本迁移对存量行
  一次性 UTC→本地回填（软删下载器与回收站行同样错位且无自愈路径，一并回填）。

三段式结构（单条 JOIN UPDATE 做不了 Python 侧时区转换，仓内无先例）：
1. SELECT JOIN 取 (info_id, downloader_id, downloader_name, added_date)；
2. Python 侧 ``stored.replace(tzinfo=utc).astimezone().replace(tzinfo=None)``；
3. 按复合 PK (info_id, downloader_id, downloader_name) 批量 UPDATE。

定位口径（审批 P1 决策 8）：
- JOIN ``bt_downloaders ON torrent_info.downloader_id = bt_downloaders.downloader_id``
  ``WHERE downloader_type = 1 AND added_date IS NOT NULL``；
- **两侧均不带 dr=0**：软删下载器（dr=1）的 TR 存量行同样错位且无自愈路径；
  downloader_id 为 UUID 主键无复用风险；torrent_info 侧回收站行（deleted_at
  非空）同样回填。
- DST 历史偏移按当前时区近似（CN 无 DST）。
- TZ=UTC 部署下转换为无害 no-op（UTC 墙钟 == 本地墙钟）。

Revision ID: c9e0f1a2b3c4
Revises: b7d8e9f0a1c2
Create Date: 2026-09-24

⚠️ 不可重复执行（二次偏移）：本迁移假定存量值是 UTC 墙钟。重复执行会把已
回填的本地墙钟再当 UTC 偏移一次（CN 部署下 +8h×2）。Alembic 版本戳保证
单次执行；严禁手工对本迁移已完成升级的库重放（回滚后重升除外）。
"""

from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect, text


# revision identifiers, used by Alembic.
revision: str = "c9e0f1a2b3c4"
down_revision: Union[str, Sequence[str], None] = "b7d8e9f0a1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SELECT_SQL = text(
    "SELECT t.info_id AS info_id, t.downloader_id AS downloader_id, "
    "t.downloader_name AS downloader_name, t.added_date AS added_date "
    "FROM torrent_info t "
    "JOIN bt_downloaders d ON t.downloader_id = d.downloader_id "
    "WHERE d.downloader_type = 1 AND t.added_date IS NOT NULL"
)

_UPDATE_SQL = text(
    "UPDATE torrent_info SET added_date = :added_date "
    "WHERE info_id = :info_id AND downloader_id = :downloader_id "
    "AND downloader_name = :downloader_name"
)

# 与 SQLAlchemy sqlite DATETIME 落库格式一致（带 6 位微秒）
_STORE_FMT = "%Y-%m-%d %H:%M:%S.%f"


def _parse_stored(value: object) -> "datetime | None":
    """容错解析存储字符串（带/不带微秒两种形态）。"""
    if not value or not isinstance(value, str):
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def upgrade() -> None:
    """存量 TR added_date：UTC 墙钟 → 本地墙钟（naive）一次性回填。"""
    existing = set(inspect(op.get_bind()).get_table_names())
    if "torrent_info" not in existing or "bt_downloaders" not in existing:
        # 漂移形态库：缺表直接跳过（参照 a1f7c9e3d2b4 容错惯例）
        return

    conn = op.get_bind()
    rows = conn.execute(_SELECT_SQL).fetchall()

    local_tz = datetime.now().astimezone().tzinfo
    params = []
    for row in rows:
        stored = _parse_stored(row.added_date)
        if stored is None:
            continue
        local_naive = stored.replace(tzinfo=timezone.utc).astimezone(local_tz).replace(tzinfo=None)
        params.append(
            {
                "info_id": row.info_id,
                "downloader_id": row.downloader_id,
                "downloader_name": row.downloader_name,
                "added_date": local_naive.strftime(_STORE_FMT),
            }
        )

    if params:
        conn.execute(_UPDATE_SQL, params)


def downgrade() -> None:
    """反向偏移：本地墙钟 → UTC 墙钟（naive）。

    警告：仅在 upgrade 后未发生新写入的前提下偏移可逆；若升级后已有
    TR 同步写入新的本地时间行，downgrade 会把它们错误推向 UTC。
    真正回滚请优先参考 docs/operations/rollback-guide.md（备份恢复路径）。
    """
    existing = set(inspect(op.get_bind()).get_table_names())
    if "torrent_info" not in existing or "bt_downloaders" not in existing:
        return

    conn = op.get_bind()
    rows = conn.execute(_SELECT_SQL).fetchall()

    local_tz = datetime.now().astimezone().tzinfo
    params = []
    for row in rows:
        stored = _parse_stored(row.added_date)
        if stored is None:
            continue
        utc_naive = stored.replace(tzinfo=local_tz).astimezone(timezone.utc).replace(tzinfo=None)
        params.append(
            {
                "info_id": row.info_id,
                "downloader_id": row.downloader_id,
                "downloader_name": row.downloader_name,
                "added_date": utc_naive.strftime(_STORE_FMT),
            }
        )

    if params:
        conn.execute(_UPDATE_SQL, params)
