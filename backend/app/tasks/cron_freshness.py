# -*- coding: utf-8 -*-
"""
定时任务数据新鲜度轻量计算（W3-4 / P1-05，PLANS/sync-database-blocking-remediation.md）

覆盖问题：P1-05（调度成功、跳过和数据新鲜度语义混乱）。

核心语义：
- freshnessSeconds = now - last_success_at（无记录返回 None）；
- stale = last_success_at 为 null 或 freshnessSeconds > 阈值；
- 阈值按“2 个调度周期”近似：cron_plan（5 段：分 时 日 月 周）能解析出最短
  重复间隔 interval 时取 2 × interval；解析失败时回退配置默认
  CRON_STALE_THRESHOLD_SECONDS（默认 7200 秒 = 2 小时兜底）。

解析策略（轻量，不引入 croniter）：
- 直接用项目已依赖的 APScheduler CronTrigger 计算最近两次触发时间，取间隔
  作为最短重复周期（对 */N、具体分钟、区间、列表、周/月限定等均能给出合理值，
  如 "0 3 * * *" → 86400s，"30 3 * * 1" → 604800s，"*/5 * * * *" → 300s）；
- 非法表达式/解析异常 → None → 走配置兜底阈值（与 cron_executor 注册失败
  时任务根本不运行的行为自洽）。

偏差说明：间隔只依赖 cron_plan，未按 task_type 细分（任务类型当前不改变
调度周期；如后续出现按类型定制阈值，可在 compute_freshness 增加参数）。
"""

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings

# 时区与 cron_executor._parse_cron_plan 保持一致（Asia/Shanghai）
_CRON_TZ = "Asia/Shanghai"


def estimate_cron_interval_seconds(cron_plan: str) -> Optional[float]:
    """估算 5 段 cron 表达式（分 时 日 月 周）的最短重复间隔（秒）。

    用 APScheduler CronTrigger 计算最近两次触发时间之差作为重复周期：
    - 可解析且能算出两次触发 → 返回间隔秒数；
    - 表达式非法/无法计算（如无下一次触发）→ 返回 None（调用方用配置兜底）。
    """
    if not cron_plan or not isinstance(cron_plan, str):
        return None
    try:
        parts = cron_plan.split()
        if len(parts) != 5:
            return None
        minute, hour, day, month, day_of_week = parts
        trigger = CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
            timezone=_CRON_TZ,
        )
        now = datetime.now().astimezone()
        first = trigger.get_next_fire_time(None, now)
        if first is None:
            return None
        second = trigger.get_next_fire_time(first, first + timedelta(seconds=1))
        if second is None:
            return None
        interval = (second - first).total_seconds()
        return interval if interval > 0 else None
    except Exception:  # noqa: BLE001 - 任何解析异常一律回退配置兜底
        return None


def compute_freshness(cron_plan: str, last_success_at: Any) -> Dict[str, Any]:
    """计算任务数据新鲜度。

    Args:
        cron_plan: 5 段 cron 表达式（分 时 日 月 周）。
        last_success_at: 最近一次数据成功时间（datetime 或 None）。

    Returns:
        {"freshness_seconds": Optional[int], "stale": bool}：
        - 无 last_success_at → freshness_seconds=None、stale=True；
        - 有记录 → freshness_seconds=now-last_success_at 秒数（int），
          stale = freshness_seconds > 阈值（阈值 = 2 × 最短重复间隔，
          解析失败用 CRON_STALE_THRESHOLD_SECONDS 兜底）。
    """
    if not isinstance(last_success_at, datetime):
        return {"freshness_seconds": None, "stale": True}

    now = datetime.now()
    freshness_seconds = int((now - last_success_at).total_seconds())

    interval = estimate_cron_interval_seconds(cron_plan)
    if interval is not None:
        threshold = 2 * interval
    else:
        threshold = settings.CRON_STALE_THRESHOLD_SECONDS

    return {"freshness_seconds": freshness_seconds, "stale": freshness_seconds > threshold}
