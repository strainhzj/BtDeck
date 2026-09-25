# -*- coding: utf-8 -*-
"""统计报表服务（统计报表 W3，PLANS/statistics-reports.md §3.4/§3.5）。

扁平单文件，模块内分区：常量 / overview / trends / seeding / tracker_stats /
fun / speed。口径总则：

- 活跃种子口径 ``dr=0 AND deleted_at IS NULL``；回收站 ``deleted_at IS NOT
  NULL AND dr=0``；彻底删除（dr=1）不在任何口径（A1 脚注）。
- tracker 行口径 ``tracker_info.dr=0`` 且 JOIN 活跃种子。
- 五桶判定（决策 7）：错误桶优先（status='error' OR has_tracker_error）→
  四主桶按 torrent_stats_cache 模块级常量（W2 提升）→ 其他。
- 聚合均为 Python 内存聚合（万级行；tags/save_path 超 5 万行再议 json_each）。
- 空库语义：聚合返回空数组/零值，不抛错。
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.runtime_context import RuntimeContext
from app.downloader.torrent_stats_cache import DOWNLOADING_STATES, PAUSED_STATES, SEEDING_STATES

logger = logging.getLogger(__name__)

# =============================================================================
# 常量（§3.4：蓝光 40GB、高清电影 8GB、剧集一季 30GB；勋章阈值决策 9 半开区间）
# =============================================================================

BYTES_PER_BLURAY = 40 * 1024**3
BYTES_PER_HD_MOVIE = 8 * 1024**3
BYTES_PER_TV_SEASON = 30 * 1024**3

# 勋章半开区间 [lo, hi) TB：[0,1) 铜 / [1,10) 银 / [10,50) 金 / [50,200) 白金 / [200,∞) 钻
BADGE_TIERS: List[Tuple[str, float, float]] = [
    ("bronze", 0.0, 1.0),
    ("silver", 1.0, 10.0),
    ("gold", 10.0, 50.0),
    ("platinum", 50.0, 200.0),
    ("diamond", 200.0, float("inf")),
]

# 分享率直方图半开区间 [lo, hi)（C10；NULL ratio 排除并由 ratioNullCount 呈现）
RATIO_BUCKETS: List[Tuple[str, float, float]] = [
    ("<0.5", 0.0, 0.5),
    ("0.5-1", 0.5, 1.0),
    ("1-2", 1.0, 2.0),
    ("2-5", 2.0, 5.0),
    ("5-10", 5.0, 10.0),
    ("10+", 10.0, float("inf")),
]

# 库龄结构（B8）：以天为界的半开区间；未知 = added_date IS NULL
AGE_BUCKET_DAYS: List[Tuple[str, Optional[float]]] = [
    ("under7d", 7.0),
    ("to30d", 30.0),
    ("to90d", 90.0),
    ("to180d", 180.0),
    ("to1y", 365.0),
    ("over1y", None),  # 哨兵：>365 天
]
AGE_UNKNOWN_KEY = "unknown"

# 速度历史窗口（B9）
SPEED_RANGES = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}

SEEDING_BUCKET = "seeding"


# =============================================================================
# 内部工具
# =============================================================================


def _status_bucket(status: Optional[str], has_tracker_error: Optional[int]) -> str:
    """五桶判定（决策 7）：错误桶优先 → 四主桶常量 → 其他。"""
    if (status or "").lower() == "error" or bool(has_tracker_error):
        return "error"
    s = (status or "").lower()
    if s in DOWNLOADING_STATES:
        return "downloading"
    if s in SEEDING_STATES:
        return "seeding"
    if s in PAUSED_STATES:
        return "paused"
    return "other"


def _normalize_host(host: Optional[str]) -> str:
    """站点归一：去端口取 hostname（D14——qB 侧 host 含端口会分裂站点）。

    IPv6 ``[::1]:8080`` 形态保留 ``[::1]``；仅当末段为纯数字端口时剥离。
    """
    if not host:
        return ""
    value = host.strip().lower()
    if value.startswith("[") and "]" in value:
        return value.split("]", 1)[0] + "]"
    head, sep, tail = value.rpartition(":")
    if sep and tail.isdigit():
        return head
    return value


def _save_path_root(path: Optional[str]) -> str:
    """目录占用归一（A4）：取前两段非空路径段（如 /downloads/movies）。

    少于两段时取现有段；空路径归 "(未分类)" 哨兵由调用方过滤。
    """
    if not path or not path.strip():
        return ""
    normalized = path.strip().replace("\\", "/")
    parts = [p for p in normalized.split("/") if p]
    if not parts:
        return ""
    prefix = "/" if normalized.startswith("/") else ""
    if len(parts) == 1:
        return prefix + parts[0]
    return prefix + "/".join(parts[:2])


def _bucket_of_ratio(ratio: float) -> Optional[str]:
    for label, lo, hi in RATIO_BUCKETS:
        if lo <= ratio < hi:
            return label
    return None  # 负值等异常不归桶（由 ratioNullCount 之外的口径排除）


def _badge_tier(total_bytes: float) -> Tuple[str, Optional[str], Optional[float]]:
    """上传量勋章（决策 9 半开区间）。

    Returns:
        (当前档位 key, 下一档 key 或 None, 下一档所需 TB 数或 None)
    """
    tb = total_bytes / 1024**4
    for idx, (key, lo, hi) in enumerate(BADGE_TIERS):
        if lo <= tb < hi:
            next_key = BADGE_TIERS[idx + 1][0] if idx + 1 < len(BADGE_TIERS) else None
            next_tb = BADGE_TIERS[idx + 1][1] if idx + 1 < len(BADGE_TIERS) else None
            return key, next_key, next_tb
    # tb < 0 不可能（估算非负）；兜底归铜
    return "bronze", "silver", 1


def _split_tags(tags: Optional[str]) -> List[str]:
    if not tags:
        return []
    return [t.strip() for t in tags.split(",") if t.strip()]


async def _load_active_torrent_rows(db: AsyncSession) -> List[Dict[str, Any]]:
    """一次加载活跃种子轻量行（Python 内存聚合基础）。

    列：info_id/hash/name/size/status/has_tracker_error/category/tags/
    save_path/downloader_id/added_date/completed_date/ratio/auxiliary_seed_count。
    """
    sql = text(
        "SELECT info_id, hash, name, size, status, has_tracker_error, category, tags, "
        "save_path, downloader_id, downloader_name, added_date, completed_date, ratio, auxiliary_seed_count "
        "FROM torrent_info WHERE dr = 0 AND deleted_at IS NULL"
    )
    result = await db.execute(sql)
    rows = [dict(row._mapping) for row in result.fetchall()]
    for r in rows:
        r["added_date"] = _as_dt(r["added_date"])
        r["completed_date"] = _as_dt(r["completed_date"])
    return rows


async def _load_downloader_map(db: AsyncSession) -> Dict[str, Dict[str, Any]]:
    """bt_downloaders 全量映射（含 dr=1，供 removed 标注；UUID 主键无复用风险）。"""
    sql = text("SELECT downloader_id, nickname, downloader_type, dr FROM bt_downloaders")
    result = await db.execute(sql)
    return {
        str(row.downloader_id): {
            "nickname": row.nickname or str(row.downloader_id),
            "type": int(row.downloader_type or 0),
            "removed": int(row.dr or 0) == 1,
        }
        for row in result.fetchall()
    }


def _as_dt(value: Any) -> Optional[datetime]:
    """裸 text() SQL 返回的 DATETIME 是存储字符串，统一解析为 datetime（含/不含微秒）。"""
    if isinstance(value, datetime):
        return value
    if not value or not isinstance(value, str):
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _iso(value: Any) -> Optional[str]:
    parsed = _as_dt(value)
    return parsed.isoformat(sep=" ") if parsed else None


# =============================================================================
# 总览（A1-A5 + 实时速度）
# =============================================================================


async def get_overview(db: AsyncSession, ctx: RuntimeContext) -> Dict[str, Any]:
    """A1 库存总览 / A2 五桶 / A3 分类标签 / A4 目录 / A5 下载器对比 + 实时速度。"""
    rows = await _load_active_torrent_rows(db)
    downloader_map = await _load_downloader_map(db)

    total_count = len(rows)
    total_size = sum(float(r["size"] or 0) for r in rows)
    recycle_bin_size = await _recycle_bin_size(db)

    # A1 largest TOP10
    largest = [
        {"hash": r["hash"] or "", "name": r["name"] or "", "sizeBytes": float(r["size"] or 0)}
        for r in sorted(rows, key=lambda x: float(x["size"] or 0), reverse=True)[:10]
        if float(r["size"] or 0) > 0
    ]

    # A2 五桶（错误桶优先）
    status_dist = _aggregate_status_dist(rows)

    # A3 分类与标签（数量 + 体积双维度；空 category 归 "" 桶，前端 i18n 为"未分类"）
    categories = _aggregate_by_names(rows, lambda r: [r["category"] or ""])
    tag_map: Dict[str, Dict[str, float]] = {}
    for r in rows:
        for tag in _split_tags(r["tags"]):
            entry = tag_map.setdefault(tag, {"count": 0, "sizeBytes": 0.0})
            entry["count"] += 1
            entry["sizeBytes"] += float(r["size"] or 0)
    tags: List[Dict[str, Any]] = [
        {"name": k, "count": int(v["count"]), "sizeBytes": v["sizeBytes"]} for k, v in tag_map.items()
    ]
    tags.sort(key=lambda x: (-x["count"], x["name"]))

    # A4 目录占用（根前缀聚合；空路径不参与）
    path_map: Dict[str, Dict[str, float]] = {}
    for r in rows:
        root = _save_path_root(r["save_path"])
        if not root:
            continue
        entry = path_map.setdefault(root, {"count": 0, "sizeBytes": 0.0})
        entry["count"] += 1
        entry["sizeBytes"] += float(r["size"] or 0)
    paths: List[Dict[str, Any]] = [
        {"path": k, "count": int(v["count"]), "sizeBytes": v["sizeBytes"]} for k, v in path_map.items()
    ]
    paths.sort(key=lambda x: -x["sizeBytes"])

    # A5 下载器对比（LEFT JOIN 标注已移除）
    by_downloader: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        by_downloader.setdefault(str(r["downloader_id"]), []).append(r)
    downloaders: List[Dict[str, Any]] = []
    for dl_id, dl_rows in by_downloader.items():
        info = downloader_map.get(dl_id)
        downloaders.append(
            {
                "downloaderId": dl_id,
                "nickname": info["nickname"] if info else (dl_rows[0].get("downloader_name") or dl_id),
                "type": info["type"] if info else None,
                "removed": info["removed"] if info else True,
                "count": len(dl_rows),
                "sizeBytes": sum(float(x["size"] or 0) for x in dl_rows),
                "statusDist": _aggregate_status_dist(dl_rows),
            }
        )
    downloaders.sort(key=lambda x: -x["sizeBytes"])

    return {
        "totals": {
            "count": total_count,
            "sizeBytes": total_size,
            "avgSizeBytes": (total_size / total_count) if total_count else 0.0,
            "recycleBinSizeBytes": recycle_bin_size,
        },
        "largest": largest,
        "statusDist": status_dist,
        "categories": categories,
        "tags": tags,
        "paths": paths,
        "downloaders": downloaders,
        "liveSpeed": _live_speed(ctx),
    }


def _aggregate_status_dist(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    buckets: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        bucket = _status_bucket(r["status"], r["has_tracker_error"])
        entry = buckets.setdefault(bucket, {"bucket": bucket, "count": 0, "sizeBytes": 0.0})
        entry["count"] += 1
        entry["sizeBytes"] += float(r["size"] or 0)
    return sorted(buckets.values(), key=lambda x: -x["count"])


def _aggregate_by_names(rows: List[Dict[str, Any]], key_fn) -> List[Dict[str, Any]]:
    agg: Dict[str, Dict[str, float]] = {}
    for r in rows:
        for name in key_fn(r):
            entry = agg.setdefault(name, {"count": 0, "sizeBytes": 0.0})
            entry["count"] += 1
            entry["sizeBytes"] += float(r["size"] or 0)
    items: List[Dict[str, Any]] = [
        {"name": k, "count": int(v["count"]), "sizeBytes": v["sizeBytes"]} for k, v in agg.items()
    ]
    items.sort(key=lambda x: -x["count"])
    return items


async def _recycle_bin_size(db: AsyncSession) -> float:
    result = await db.execute(
        text("SELECT COALESCE(SUM(size), 0) FROM torrent_info WHERE dr = 0 AND deleted_at IS NOT NULL")
    )
    return float(result.scalar() or 0)


def _live_speed(ctx: RuntimeContext) -> Dict[str, Any]:
    """实时速度卡：仅读 store 快照（严禁新建下载器客户端）。"""
    items: List[Dict[str, Any]] = []
    total_down = 0
    total_up = 0
    if ctx.store is not None:
        try:
            snapshot = ctx.store.get_snapshot_sync()
        except Exception as exc:  # noqa: BLE001 - 快照失败降级零值，不阻断报表
            logger.warning(f"[REPORTS] live speed snapshot failed: {exc}")
            snapshot = []
        for vo in snapshot or []:
            online = getattr(vo, "is_online", False) is True
            dl = int(getattr(vo, "download_speed", 0) or 0) * 1024 if online else 0
            ul = int(getattr(vo, "upload_speed", 0) or 0) * 1024 if online else 0
            if online:
                total_down += dl
                total_up += ul
            items.append(
                {
                    "downloaderId": str(getattr(vo, "downloader_id", "") or ""),
                    "nickname": getattr(vo, "nickname", "") or "",
                    "online": online,
                    "downloadSpeed": dl,
                    "uploadSpeed": ul,
                }
            )
    return {"totalDownloadSpeed": total_down, "totalUploadSpeed": total_up, "items": items}


# =============================================================================
# 趋势（B6/B7/B8 + B9 默认 24h）
# =============================================================================


async def get_trends(db: AsyncSession, period: str = "month", limit: int = 12) -> Dict[str, Any]:
    """B6 新增趋势（月/周桶）/ B7 完成趋势 / B8 库龄结构 / B9 速度历史（默认 24h）。"""
    rows = await _load_active_torrent_rows(db)
    return {
        "added": _time_buckets(rows, "added_date", period, limit),
        "completed": _time_buckets(rows, "completed_date", period, limit),
        "ageBuckets": _age_buckets(rows),
        "speedHistory": await get_speed_history(db, "24h"),
    }


def _bucket_key(value: datetime, period: str) -> str:
    if period == "week":
        # 周桶 %Y-%W（Python 侧分桶；SQLite strftime 无 ISO 周）
        return value.strftime("%Y-%W")
    return value.strftime("%Y-%m")


def _time_buckets(rows: List[Dict[str, Any]], field: str, period: str, limit: int) -> List[Dict[str, Any]]:
    """按月/周分桶（NULL 过滤；B6/B7 做种态添加种子 completed 恒空属预期覆盖面）。"""
    agg: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        value = r[field]
        if not isinstance(value, datetime):
            continue  # NULL 行过滤（脚注口径）
        key = _bucket_key(value, period)
        entry = agg.setdefault(key, {"key": key, "count": 0, "sizeBytes": 0.0})
        entry["count"] += 1
        entry["sizeBytes"] += float(r["size"] or 0)
    buckets = sorted(agg.values(), key=lambda x: x["key"])
    return buckets[-limit:] if limit > 0 else buckets


def _age_buckets(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """库龄结构（B8）：<7d/30/90/180/1y/更久/未知（NULL 桶）。"""
    now = datetime.now()
    agg: Dict[str, Dict[str, Any]] = {name: {"name": name, "count": 0, "sizeBytes": 0.0} for name, _ in AGE_BUCKET_DAYS}
    agg[AGE_UNKNOWN_KEY] = {"name": AGE_UNKNOWN_KEY, "count": 0, "sizeBytes": 0.0}
    for r in rows:
        value = r["added_date"]
        size = float(r["size"] or 0)
        if not isinstance(value, datetime):
            agg[AGE_UNKNOWN_KEY]["count"] += 1
            agg[AGE_UNKNOWN_KEY]["sizeBytes"] += size
            continue
        days = (now - value).total_seconds() / 86400.0
        for name, bound in AGE_BUCKET_DAYS:
            if bound is None or days < bound:
                agg[name]["count"] += 1
                agg[name]["sizeBytes"] += size
                break
    order = [name for name, _ in AGE_BUCKET_DAYS] + [AGE_UNKNOWN_KEY]
    return [agg[name] for name in order]


# =============================================================================
# 做种（C10/C11/C12）
# =============================================================================


async def get_seeding(db: AsyncSession) -> Dict[str, Any]:
    rows = await _load_active_torrent_rows(db)

    bucket_agg: Dict[str, Dict[str, Any]] = {
        label: {"bucket": label, "count": 0, "sizeBytes": 0.0} for label, _, _ in RATIO_BUCKETS
    }
    ratio_null_count = 0
    for r in rows:
        ratio = r["ratio"]
        size = float(r["size"] or 0)
        if ratio is None:
            ratio_null_count += 1
            continue
        label = _bucket_of_ratio(float(ratio))
        if label is None:
            ratio_null_count += 1  # 负值等异常并入 NULL 计数口径
            continue
        bucket_agg[label]["count"] += 1
        bucket_agg[label]["sizeBytes"] += size

    slackers = [
        {
            "hash": r["hash"] or "",
            "name": r["name"] or "",
            "sizeBytes": float(r["size"] or 0),
            "ratio": float(r["ratio"]),
        }
        for r in sorted(
            (
                x
                for x in rows
                if x["ratio"] is not None and float(x["ratio"]) < 0.5 and isinstance(x["completed_date"], datetime)
            ),
            key=lambda x: float(x["size"] or 0),
            reverse=True,
        )[:20]
    ]

    total_count = len(rows)
    cross_seed_rows = [r for r in rows if int(r["auxiliary_seed_count"] or 1) > 1]
    top_aux = [
        {
            "hash": r["hash"] or "",
            "name": r["name"] or "",
            "auxiliarySeedCount": int(r["auxiliary_seed_count"] or 1),
            "sizeBytes": float(r["size"] or 0),
        }
        for r in sorted(cross_seed_rows, key=lambda x: int(x["auxiliary_seed_count"] or 1), reverse=True)[:10]
    ]
    auxiliary = {
        "totalTorrents": total_count,
        "crossSeedCount": len(cross_seed_rows),
        "crossSeedRate": (len(cross_seed_rows) / total_count) if total_count else 0.0,
        "top10": top_aux,
    }

    return {
        "ratioBuckets": [bucket_agg[label] for label, _, _ in RATIO_BUCKETS],
        "ratioNullCount": ratio_null_count,
        "slackers": slackers,
        "auxiliary": auxiliary,
    }


# =============================================================================
# Tracker（D14/D15/D16）
# =============================================================================


async def _load_tracker_rows(db: AsyncSession) -> List[Dict[str, Any]]:
    """tracker 行（dr=0）JOIN 活跃种子（站点体积/健康/冷热共用行源）。"""
    sql = text(
        "SELECT t.tracker_host AS host, t.status AS status, t.seeder_count AS seeder, "
        "t.leecher_count AS leecher, t.download_count AS downloaded, "
        "ti.size AS size, ti.info_id AS info_id "
        "FROM tracker_info t JOIN torrent_info ti ON t.torrent_info_id = ti.info_id "
        "WHERE t.dr = 0 AND ti.dr = 0 AND ti.deleted_at IS NULL"
    )
    result = await db.execute(sql)
    return [dict(row._mapping) for row in result.fetchall()]


async def get_tracker_stats(db: AsyncSession) -> Dict[str, Any]:
    rows = await _load_tracker_rows(db)

    # D14 站点构成（host 去端口归一；辅种跨站重复计体积——CaliberNotes 脚注）
    site_map: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        host = _normalize_host(r["host"])
        entry = site_map.setdefault(host, {"host": host, "count": 0, "sizeBytes": 0.0})
        entry["count"] += 1
        entry["sizeBytes"] += float(r["size"] or 0)

    # D15 站点健康榜（error 率；分母排除 status='unknown'）+ D16 冷热（均值排除 NULL）
    health_map: Dict[str, Dict[str, Any]] = {}
    supply_map: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        host = _normalize_host(r["host"])
        h = health_map.setdefault(host, {"host": host, "errorRows": 0, "denominatorRows": 0, "errorTorrents": set()})
        status = (r["status"] or "").lower()
        if status == "error":
            h["errorRows"] += 1
            h["errorTorrents"].add(r["info_id"])
        if status != "unknown":
            h["denominatorRows"] += 1
        s = supply_map.setdefault(
            host,
            {
                "host": host,
                "seederSum": 0.0,
                "seederN": 0,
                "leecherSum": 0.0,
                "leecherN": 0,
                "downloadSum": 0.0,
                "downloadN": 0,
            },
        )
        if r["seeder"] is not None:
            s["seederSum"] += float(r["seeder"])
            s["seederN"] += 1
        if r["leecher"] is not None:
            s["leecherSum"] += float(r["leecher"])
            s["leecherN"] += 1
        if r["downloaded"] is not None:
            s["downloadSum"] += float(r["downloaded"])
            s["downloadN"] += 1

    sites = sorted(site_map.values(), key=lambda x: -x["sizeBytes"])
    health = [
        {
            "host": v["host"],
            "errorRate": (v["errorRows"] / v["denominatorRows"]) if v["denominatorRows"] else 0.0,
            "affectedCount": len(v["errorTorrents"]),
        }
        for v in sorted(
            health_map.values(), key=lambda x: -(x["errorRows"] / x["denominatorRows"] if x["denominatorRows"] else 0.0)
        )
    ]
    supply_demand = [
        {
            "host": v["host"],
            "avgSeeders": (v["seederSum"] / v["seederN"]) if v["seederN"] else 0.0,
            "avgLeechers": (v["leecherSum"] / v["leecherN"]) if v["leecherN"] else 0.0,
            "avgDownloads": (v["downloadSum"] / v["downloadN"]) if v["downloadN"] else 0.0,
            "count": max(v["seederN"], v["leecherN"], v["downloadN"]),
        }
        for v in supply_demand_sorted(supply_map)
    ]
    return {"sites": sites, "health": health, "supplyDemand": supply_demand}


def supply_demand_sorted(supply_map: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """冷热榜排序：有效行数降序（count=有效行数，均值排除 NULL 行）。"""
    return sorted(supply_map.values(), key=lambda v: -max(v["seederN"], v["leecherN"], v["downloadN"]))


# =============================================================================
# 趣味（24/25/27 汇总 + 26 年度）
# =============================================================================


async def _guardian(rows: List[Dict[str, Any]], db: AsyncSession) -> Dict[str, Any]:
    """24 火种守护者：每种子 trackers 最小非 NULL seeder_count；≤2 即火种。

    无任何非 NULL tracker 计数的种子排除（激活前存量三列 NULL，数据自激活日起
    积累——脚注同 B9 冷启动）。-1 已在 W2 归一为 NULL，不会误判火种。
    """
    sql = text("SELECT torrent_info_id, seeder_count FROM tracker_info " "WHERE dr = 0 AND seeder_count IS NOT NULL")
    result = await db.execute(sql)
    min_map: Dict[str, int] = {}
    for row in result.fetchall():
        info_id = str(row.torrent_info_id)
        value = int(row.seeder_count)
        if info_id not in min_map or value < min_map[info_id]:
            min_map[info_id] = value

    fire_rows: List[Dict[str, Any]] = []
    considered = 0
    for r in rows:
        info_id = str(r["info_id"])
        if info_id not in min_map:
            continue
        considered += 1
        min_seeders = min_map[info_id]
        if min_seeders <= 2:
            fire_rows.append(
                {
                    "hash": r["hash"] or "",
                    "name": r["name"] or "",
                    "sizeBytes": float(r["size"] or 0),
                    "minSeeders": min_seeders,
                }
            )
    fire_rows.sort(key=lambda x: (x["minSeeders"], -x["sizeBytes"]))
    return {
        "fireCount": len(fire_rows),
        "totalConsidered": considered,
        "excludedCount": len(rows) - considered,
        "top10": fire_rows[:10],
    }


def _upload_estimate(rows: List[Dict[str, Any]]) -> float:
    """25 上传量估算：Σ(size × ratio)，做种桶种子且 ratio 非 NULL（决策 7 同套桶定义）。"""
    total = 0.0
    for r in rows:
        if _status_bucket(r["status"], r["has_tracker_error"]) != SEEDING_BUCKET:
            continue
        if r["ratio"] is None:
            continue
        total += float(r["size"] or 0) * float(r["ratio"])
    return total


def _badges(total_bytes: float) -> Dict[str, Any]:
    tier, next_tier, next_tb = _badge_tier(total_bytes)
    return {
        "uploadedBytes": total_bytes,
        "currentTier": tier,
        "nextTier": next_tier,
        "nextTierAtTB": next_tb,
        "equivalents": {
            "movies": int(total_bytes // BYTES_PER_HD_MOVIE),
            "blurays": int(total_bytes // BYTES_PER_BLURAY),
            "tvSeasons": int(total_bytes // BYTES_PER_TV_SEASON),
        },
    }


async def get_fun_summary(db: AsyncSession) -> Dict[str, Any]:
    rows = await _load_active_torrent_rows(db)
    with_ratio = [r for r in rows if r["ratio"] is not None]
    shame = [
        {
            "hash": r["hash"] or "",
            "name": r["name"] or "",
            "ratio": float(r["ratio"]),
            "sizeBytes": float(r["size"] or 0),
        }
        for r in sorted(with_ratio, key=lambda x: float(x["ratio"]))[:10]
    ]
    pride = [
        {
            "hash": r["hash"] or "",
            "name": r["name"] or "",
            "ratio": float(r["ratio"]),
            "sizeBytes": float(r["size"] or 0),
        }
        for r in sorted(with_ratio, key=lambda x: float(x["ratio"]), reverse=True)[:10]
    ]
    return {
        "guardian": await _guardian(rows, db),
        "badges": _badges(_upload_estimate(rows)),
        "shame": shame,
        "pride": pride,
    }


async def get_fun_yearly(db: AsyncSession, year: int) -> Dict[str, Any]:
    """26 种库年度报告（Spotify Wrapped 式；added_date NULL 行全部排除）。"""
    now = datetime.now()
    year_start = datetime(year, 1, 1)
    year_end = datetime(year + 1, 1, 1)
    rows = await _load_active_torrent_rows(db)

    added_rows = [r for r in rows if isinstance(r["added_date"], datetime) and year_start <= r["added_date"] < year_end]

    month_map: Dict[str, int] = {}
    day_map: Dict[str, int] = {}
    for r in added_rows:
        mk = r["added_date"].strftime("%Y-%m")
        dk = r["added_date"].strftime("%Y-%m-%d")
        month_map[mk] = month_map.get(mk, 0) + 1
        day_map[dk] = day_map.get(dk, 0) + 1
    busiest_month = max(month_map.items(), key=lambda kv: (kv[1], kv[0]), default=None)
    busiest_day = max(day_map.items(), key=lambda kv: (kv[1], kv[0]), default=None)

    # 体积占比最高站点（本年添加种子的 tracker JOIN；跨站重复计体积脚注）
    site_size: Dict[str, float] = {}
    if added_rows:
        added_ids = {str(r["info_id"]) for r in added_rows}
        tracker_rows = await _load_tracker_rows(db)
        for tr in tracker_rows:
            if str(tr["info_id"]) in added_ids:
                host = _normalize_host(tr["host"])
                site_size[host] = site_size.get(host, 0.0) + float(tr["size"] or 0)
    top_site = max(site_size.items(), key=lambda kv: (kv[1], kv[0]), default=None)

    # 元老：最早添加仍在做种（全库口径，含做种天数）
    seeding_rows = [
        r
        for r in rows
        if isinstance(r["added_date"], datetime)
        and _status_bucket(r["status"], r["has_tracker_error"]) == SEEDING_BUCKET
    ]
    elder_row = min(seeding_rows, key=lambda x: x["added_date"], default=None)
    elder = None
    if elder_row is not None:
        seeding_days = max(0.0, (now - elder_row["added_date"]).total_seconds() / 86400.0)
        elder = {
            "hash": elder_row["hash"] or "",
            "name": elder_row["name"] or "",
            "addedDate": _iso(elder_row["added_date"]),
            "seedingDays": int(seeding_days),
        }

    guardian = await _guardian(rows, db)
    return {
        "year": year,
        "yearAdded": {"count": len(added_rows), "sizeBytes": sum(float(r["size"] or 0) for r in added_rows)},
        "busiestMonth": {"key": busiest_month[0], "count": busiest_month[1]} if busiest_month else None,
        "busiestDay": {"key": busiest_day[0], "count": busiest_day[1]} if busiest_day else None,
        "topSite": {"host": top_site[0], "sizeBytes": top_site[1]} if top_site else None,
        "elder": elder,
        "fireCount": guardian["fireCount"],
        "uploadEstimate": _badges(_upload_estimate(rows)),
    }


# =============================================================================
# 速度历史（B9）
# =============================================================================


async def get_speed_history(
    db: AsyncSession, range_key: str = "24h", downloader_id: Optional[str] = None
) -> Dict[str, Any]:
    """B9 速度历史：24h 纯 raw 分钟级；7d/30d hourly 主体 + raw 尾段拼接。

    - 断点语义：断点仅后端停机时段（该小时无样本 → 分组不存在 → 前端
      breakLine 不补 0）；下载器离线 = 0 速数据点；下载器增删 = 序列起止边界。
    - avg 语义（审批 P2-4）：hourly 点 avg_* = 在线样本均值（分母
      online_count；online_count=0 的小时输出 0），行携带 sampleCount/
      onlineCount 供前端区分"全离线小时"与"停机无行"；onlineRatio =
      online_count/sample_count = 「采样期间在线率」（停机无样本属断点，
      不参与比率）。
    """
    window = SPEED_RANGES.get(range_key, timedelta(hours=24))
    now = datetime.now()
    window_start = now - window

    downloader_map = await _load_downloader_map(db)

    # 冷启动观测：全局首个样本时间（无样本 → null；samplingActive 恒 true——
    # 采样循环随应用常驻，W1 注册）
    first_result = await db.execute(text("SELECT MIN(sampled_at) FROM downloader_speed_sample"))
    first_sample = _as_dt(first_result.scalar())

    # 单条参数化 SQL（BTD305 合规：不做字符串拼接；可选下载器过滤用
    # ``:dl_id IS NULL OR`` 谓词表达，参数不参与 SQL 文本）
    params: Dict[str, Any] = {
        "start": window_start.strftime("%Y-%m-%d %H:%M:%S"),
        "dl_id": downloader_id,
    }

    points_by_dl: Dict[str, List[Dict[str, Any]]] = {}

    if range_key == "24h":
        raw_sql = text(
            "SELECT downloader_id, sampled_at, download_speed, upload_speed, online "
            "FROM downloader_speed_sample "
            "WHERE sampled_at >= :start AND (:dl_id IS NULL OR downloader_id = :dl_id) "
            "ORDER BY sampled_at"
        )
        for row in (await db.execute(raw_sql, params)).fetchall():
            points_by_dl.setdefault(str(row.downloader_id), []).append(
                {
                    "ts": _iso(row.sampled_at),
                    "downloadSpeed": int(row.download_speed or 0),
                    "uploadSpeed": int(row.upload_speed or 0),
                    "online": bool(row.online),
                }
            )
    else:
        hourly_sql = text(
            "SELECT downloader_id, stat_hour, avg_download_speed, max_download_speed, "
            "avg_upload_speed, max_upload_speed, sample_count, online_count "
            "FROM downloader_speed_hourly "
            "WHERE stat_hour >= :start AND (:dl_id IS NULL OR downloader_id = :dl_id) "
            "ORDER BY stat_hour"
        )
        for row in (await db.execute(hourly_sql, params)).fetchall():
            points_by_dl.setdefault(str(row.downloader_id), []).append(
                {
                    "ts": _iso(row.stat_hour),
                    "downloadSpeed": int(row.avg_download_speed or 0),
                    "uploadSpeed": int(row.avg_upload_speed or 0),
                    "sampleCount": int(row.sample_count or 0),
                    "onlineCount": int(row.online_count or 0),
                }
            )
        # raw 尾段拼接：定位 hourly 最大 stat_hour H → raw >= H+1h；无 hourly → raw 全窗口
        max_hour_result = await db.execute(
            text(
                "SELECT MAX(stat_hour) FROM downloader_speed_hourly " "WHERE (:dl_id IS NULL OR downloader_id = :dl_id)"
            ),
            params,
        )
        max_hour = _as_dt(max_hour_result.scalar())
        if max_hour is not None:
            tail_start = (max_hour + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        else:
            tail_start = params["start"]
        raw_sql = text(
            "SELECT downloader_id, sampled_at, download_speed, upload_speed, online "
            "FROM downloader_speed_sample "
            "WHERE sampled_at >= :start AND (:dl_id IS NULL OR downloader_id = :dl_id) "
            "ORDER BY sampled_at"
        )
        for row in (await db.execute(raw_sql, {**params, "start": tail_start})).fetchall():
            points_by_dl.setdefault(str(row.downloader_id), []).append(
                {
                    "ts": _iso(row.sampled_at),
                    "downloadSpeed": int(row.download_speed or 0),
                    "uploadSpeed": int(row.upload_speed or 0),
                    "online": bool(row.online),
                }
            )

    series = []
    for dl_id, points in points_by_dl.items():
        info = downloader_map.get(dl_id)
        series.append(
            {
                "downloaderId": dl_id,
                "nickname": info["nickname"] if info else dl_id,
                "removed": info["removed"] if info else True,
                "points": points,
            }
        )
    series.sort(key=lambda x: x["downloaderId"])

    return {
        "range": range_key,
        "series": series,
        "samplingActive": True,
        "firstSampleAt": _iso(first_sample),
    }
