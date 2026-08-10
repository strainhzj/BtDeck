# -*- coding: utf-8 -*-
"""
Tracker 关键词状态同步服务（W1-2 只写变化行）

背景（P0-02）：端点层 update_tracker_status_from_keywords 每轮扫描全表
TrackerInfo 并按关键词池判定后无差别写回，即使判定结果无变化也制造大量
UPDATE、WAL 增长与写锁时间。本服务将判定与写回整体从端点层搬迁至此，
并改为"只写变化行"：

1. 判定规则与端点层原实现逐行一致（精确匹配优先 → 部分匹配 → unknown；
   全部 failed → error / 有 success|ignored → normal / 其他 → unknown）。
2. 变化检测：判定出的 (status, status_msg) 与库中现有 (status, msg) 做
   strip 归一化对比（复用 sync_db_write._normalize_str 语义），一致计入
   unchanged，不一致进入变化集。
3. 零变化零 DML：变化集为空时不进 db_write_scope、不执行 UPDATE、不 commit。
4. 变化集走 W1-1 统一分批写入 bulk_upsert_with_retry（每批独立真实 commit，
   锁冲突只重试当前批），禁止逐行 commit、禁止全表无条件 UPDATE。
5. 配置开关 SYNC_TRACKER_STATUS_INCREMENTAL_ENABLED=False 时回退旧逻辑：
   跳过变化检测，所有匹配 tracker 全部进变化集写回（判定规则不变）。

接入对象：app/api/endpoints/torrent_sync.py（兼容包装，供 torrent_sync_async
与定时任务 tracker_sync_task 调用，两个调用方零改动）。
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, cast
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.sync_db_write import _normalize_str, bulk_upsert_with_retry
from app.services.sync_observability import EVENT_TRACKER_STATUS, log_event
from app.torrents.models import TrackerInfo, TrackerKeywordConfig

logger = logging.getLogger(__name__)


@dataclass
class TrackerStatusStats:
    """Tracker 关键词状态同步统计（W1-2）。

    - scanned: 参与判定的 tracker 行数（无 host / 空消息被跳过的行不计入）。
    - changed: 实际写入（判定结果有变化）的行数。
    - unchanged: 判定结果与库中现有状态一致、未写入的行数。
    - batches: 真实 commit 批次数（零变化时为 0）。
    - duration_ms: 整个同步耗时（毫秒，含关键词加载/判定/写回）。
    - total_hosts: 参与判定的 tracker_host 数（兼容包装 total_hosts 字段）。
    - reason: 提前返回原因（"no_keywords" / "no_trackers" / None），
      供兼容包装还原原返回消息语义。
    """

    scanned: int = 0
    changed: int = 0
    unchanged: int = 0
    batches: int = 0
    duration_ms: float = 0.0
    total_hosts: int = 0
    reason: Optional[str] = None


async def sync_tracker_status_from_keywords(
    db: AsyncSession,
    *,
    batch_size: Optional[int] = None,
    label: str = "tracker_status",
) -> TrackerStatusStats:
    """根据关键词看板增量更新 tracker 状态（只写变化行）。

    判定规则（与端点层原实现逐行一致，禁止改写语义）：
    - 精确匹配优先（msg in keyword_map，其次 msg.strip() in keyword_map）；
    - 否则部分匹配（keyword.lower() in msg.lower()，取第一个命中）；
    - 否则 unknown。
    - 每个 host 的状态应用到该 host 下所有 tracker：
      全部 failed → status='error'/msg='失败'；
      有 success 或 ignored → 'normal'/'正常'；
      其他 → 'unknown'/'未知'。

    关键词为空 / 无 tracker / 判定结果零变化时，不写库不 commit
    （changed=0 且 batches=0）。

    Args:
        db: 异步数据库会话（由调用方传入，便于未来统一协调器复用）。
        batch_size: 真实提交批大小；None 时取 settings.SYNC_DB_COMMIT_BATCH_SIZE。
        label: 写入日志标签（溯源用）。

    Returns:
        TrackerStatusStats 统计对象。
    """
    start_ts = time.perf_counter()

    # Step 1: 加载所有启用的关键词到内存
    result = await db.execute(
        select(TrackerKeywordConfig).filter(TrackerKeywordConfig.enabled.is_(True), TrackerKeywordConfig.dr == 0)
    )
    keywords = result.scalars().all()

    # 构建关键词字典 {keyword: keyword_type}
    # 注意：legacy 模型属性对 mypy 是 Column[str]，此处 cast 为业务值
    keyword_map: Dict[str, str] = {}
    for kw in keywords:
        keyword = cast(str, kw.keyword)
        keyword_type = cast(str, kw.keyword_type)
        if keyword not in keyword_map:
            keyword_map[keyword] = keyword_type
        # 如果重复，保留后读取的（通常priority更高）——注意实际代码保留先读取的

    logger.debug(f"加载关键词: {len(keyword_map)}条")

    if not keyword_map:
        # 无关键词：提前返回，不入库不 commit（保持原返回语义）
        stats = TrackerStatusStats(reason="no_keywords")
        stats.duration_ms = (time.perf_counter() - start_ts) * 1000.0
        logger.info(
            "tracker_status no_change: tracker_status_scanned=0 tracker_status_changed=0 "
            "change_ratio=0.0 classification_ms=%.1f write_ms=0.0 commit_batches=0 reason=no_keywords",
            stats.duration_ms,
        )
        _emit_tracker_status_done(stats)
        return stats

    # Step 2: 查询所有tracker信息（只查询需要的字段；追加 status/msg 用于变化检测）
    result = await db.execute(
        select(
            TrackerInfo.tracker_id,
            TrackerInfo.tracker_url,
            TrackerInfo.last_announce_msg,
            TrackerInfo.last_scrape_msg,
            TrackerInfo.tracker_host,
            TrackerInfo.status,
            TrackerInfo.msg,
        ).filter(TrackerInfo.dr == 0)
    )
    trackers = result.all()

    if not trackers:
        # 无 tracker：提前返回，不入库不 commit（保持原返回语义）
        stats = TrackerStatusStats(reason="no_trackers")
        stats.duration_ms = (time.perf_counter() - start_ts) * 1000.0
        logger.info(
            "tracker_status no_change: tracker_status_scanned=0 tracker_status_changed=0 "
            "change_ratio=0.0 classification_ms=%.1f write_ms=0.0 commit_batches=0 reason=no_trackers",
            stats.duration_ms,
        )
        _emit_tracker_status_done(stats)
        return stats

    logger.debug(f"发现tracker记录: {len(trackers)}条")

    # Step 3: 按tracker_host分组，提取消息
    tracker_host_msgs: Dict[str, List[Dict[str, Any]]] = {}  # {tracker_host: [{tracker_id, msg}, ...]}
    # 库中现有状态 {tracker_id: (status, msg)}，用于变化检测
    existing_state: Dict[str, Tuple[Optional[str], Optional[str]]] = {}

    for tracker in trackers:
        tracker_id = tracker.tracker_id
        tracker_url = tracker.tracker_url
        announce_msg = tracker.last_announce_msg
        scrape_msg = tracker.last_scrape_msg
        tracker_host = tracker.tracker_host

        # 如果tracker_host为空，尝试从URL提取
        if not tracker_host and tracker_url:
            try:
                parsed = urlparse(tracker_url)
                if parsed and parsed.hostname:
                    tracker_host = parsed.hostname
                    logger.debug(f"从URL提取tracker_host: {tracker_host}")
            except Exception as e:
                logger.debug(f"解析tracker URL失败: {tracker_url}, 错误: {e}")

        if not tracker_host:
            logger.debug(f"跳过无tracker_host的记录: tracker_id={tracker_id}")
            continue

        # 优先使用announce消息，为空则使用scrape消息
        msg = announce_msg or scrape_msg or ""

        # 过滤空消息
        if not msg or not msg.strip():
            continue

        existing_state[tracker_id] = (tracker.status, tracker.msg)

        if tracker_host not in tracker_host_msgs:
            tracker_host_msgs[tracker_host] = []

        tracker_host_msgs[tracker_host].append({"tracker_id": tracker_id, "msg": msg.strip()})

    logger.debug(f"按tracker_host分组后: {len(tracker_host_msgs)}个host")

    # Step 4: 判断每个tracker_host的状态
    tracker_status_map: Dict[str, Tuple[str, str]] = {}  # {tracker_id: (status, msg)}

    for tracker_host, msg_list in tracker_host_msgs.items():
        # 判断每条消息的类型
        msg_types: List[str] = []
        for item in msg_list:
            msg = item["msg"]

            # 精确匹配关键词（优先级高）
            exact_match: Optional[str] = None
            if msg in keyword_map:
                exact_match = keyword_map[msg]
            elif msg.strip() in keyword_map:  # 去除前后空格后再匹配
                exact_match = keyword_map[msg.strip()]

            if exact_match:
                msg_types.append(exact_match)
            else:
                # 尝试部分匹配（关键词包含在消息中）
                partial_match: Optional[str] = None
                for keyword, keyword_type in keyword_map.items():
                    if keyword.lower() in msg.lower():
                        partial_match = keyword_type
                        break

                if partial_match:
                    msg_types.append(partial_match)
                    logger.debug(f"部分匹配成功: msg='{msg[:50]}...' keyword='{partial_match}'")
                else:
                    msg_types.append("unknown")

        # 判断规则
        if all(t == "failed" for t in msg_types):
            # 全部失败 → error
            status = "error"
            status_msg = "失败"
        elif any(t in ["success", "ignored"] for t in msg_types):
            # 有成功或忽略 → normal
            status = "normal"
            status_msg = "正常"
        else:
            # 其他情况 → unknown
            status = "unknown"
            status_msg = "未知"

        # 将状态应用到该host下的所有tracker
        for item in msg_list:
            tracker_status_map[item["tracker_id"]] = (status, status_msg)

        logger.debug(f"Tracker Host: {tracker_host} | 状态: {status} | 消息类型: {msg_types}")

    classification_ms = (time.perf_counter() - start_ts) * 1000.0

    # Step 5: 变化检测 —— 判定结果与库中现有 (status, msg) 对比，只收集变化行。
    # 增量开关关闭时回退旧逻辑：跳过对比，所有匹配 tracker 全部判定为变化
    # （只改变写回策略，不改变判定规则）。
    incremental = bool(settings.SYNC_TRACKER_STATUS_INCREMENTAL_ENABLED)
    now = datetime.now()
    changes: List[Dict[str, Any]] = []
    unchanged = 0

    for tracker_id, (status, status_msg) in tracker_status_map.items():
        if incremental:
            old_status, old_msg = existing_state.get(tracker_id, (None, None))
            # strip 归一化对比（None/""/尾空格均视为等价），参照 sync_db_write._normalize_str 语义
            same_status = _normalize_str(old_status) == _normalize_str(status)
            same_msg = _normalize_str(old_msg) == _normalize_str(status_msg)
            if same_status and same_msg:
                unchanged += 1
                continue
        changes.append({"tracker_id": tracker_id, "status": status, "msg": status_msg, "update_time": now})

    scanned = len(tracker_status_map)
    if not changes:
        # 零变化零 DML：不进 db_write_scope、不执行 UPDATE、不 commit
        stats = TrackerStatusStats(scanned=scanned, unchanged=unchanged, total_hosts=len(tracker_host_msgs))
        stats.duration_ms = (time.perf_counter() - start_ts) * 1000.0
        logger.info(
            "tracker_status no_change: tracker_status_scanned=%d tracker_status_changed=0 "
            "change_ratio=0.0 classification_ms=%.1f write_ms=0.0 commit_batches=0",
            scanned,
            classification_ms,
        )
        _emit_tracker_status_done(stats)
        return stats

    # Step 6: 变化集走统一分批写入（W1-1：每批独立真实 commit，锁冲突只重试当前批）
    write_start = time.perf_counter()
    write_stats = await bulk_upsert_with_retry(
        db,
        [],
        changes,
        model=TrackerInfo,
        label=label,
        batch_size=batch_size,
    )
    write_ms = (time.perf_counter() - write_start) * 1000.0

    stats = TrackerStatusStats(
        scanned=scanned,
        changed=write_stats.changed,
        unchanged=unchanged,
        batches=write_stats.batches,
        total_hosts=len(tracker_host_msgs),
    )
    stats.duration_ms = (time.perf_counter() - start_ts) * 1000.0

    ratio = stats.changed / scanned if scanned else 0.0
    logger.info(
        "tracker_status done: tracker_status_scanned=%d tracker_status_changed=%d change_ratio=%.3f "
        "classification_ms=%.1f write_ms=%.1f commit_batches=%d unchanged=%d",
        stats.scanned,
        stats.changed,
        ratio,
        classification_ms,
        write_ms,
        stats.batches,
        stats.unchanged,
    )
    _emit_tracker_status_done(stats)
    return stats


def _emit_tracker_status_done(stats: TrackerStatusStats) -> None:
    """发射 tracker 状态同步完成事件（W4-1 第二部分）。

    事件选择说明：使用独立事件 EVENT_TRACKER_STATUS 而非 EVENT_CHECKPOINT——
    EVENT_CHECKPOINT 语义是检查点游标推进（position/state/cursor），而本服务是
    数据写回统计（scanned/changed/unchanged/batches），字段集不同，混入会污染
    游标语义还原。事件名/白名单见 sync_observability.EVENT_FIELDS。
    """
    log_event(
        EVENT_TRACKER_STATUS,
        outcome="no_change" if stats.changed == 0 else "done",
        skip_reason=stats.reason,
        scanned=stats.scanned,
        changed=stats.changed,
        unchanged=stats.unchanged,
        batches=stats.batches,
        duration_ms=round(stats.duration_ms, 1),
    )
