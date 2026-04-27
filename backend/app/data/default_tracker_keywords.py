"""
Tracker关键词池默认数据
包含成功池、失败池、忽略池的初始关键词数据
"""

from datetime import datetime
from typing import List, Dict, Any


def get_default_tracker_keywords() -> List[Dict[str, Any]]:
    """
    获取默认的tracker关键词配置

    Returns:
        包含keyword_type、keyword、description等字段的数据列表
    """
    return [
        # ========== 成功池 ==========
        {
            "keyword_type": "success",
            "keyword": "Success",
            "description": "Tracker连接成功"
        },

        # ========== 失败池 ==========
        {
            "keyword_type": "failed",
            "keyword": "Bad Gateway",
            "description": "网关错误"
        },
        {
            "keyword_type": "failed",
            "keyword": "Could not connect to tracker",
            "description": "无法连接到tracker"
        },
        {
            "keyword_type": "failed",
            "keyword": "Forbidden",
            "description": "禁止访问"
        },
        {
            "keyword_type": "failed",
            "keyword": "Internal Server Error",
            "description": "服务器内部错误"
        },
        {
            "keyword_type": "failed",
            "keyword": "Invalid credentials 3! Re-download the .torrent",
            "description": "凭据无效，需要重新下载种子"
        },
        {
            "keyword_type": "failed",
            "keyword": "Not Found",
            "description": "资源未找到"
        },
        {
            "keyword_type": "failed",
            "keyword": "Please delete this tracker!",
            "description": "请删除此tracker"
        },
        {
            "keyword_type": "failed",
            "keyword": "Request too frequent(h)",
            "description": "请求过于频繁"
        },
        {
            "keyword_type": "failed",
            "keyword": "Require passkey",
            "description": "需要passkey"
        },
        {
            "keyword_type": "failed",
            "keyword": "There is a minimum announce time lock, please wait another 10 seconds.",
            "description": "最小announce时间间隔限制"
        },
        {
            "keyword_type": "failed",
            "keyword": "There is a minimum announce time lock, please wait another 33 seconds.",
            "description": "最小announce时间间隔限制"
        },
        {
            "keyword_type": "failed",
            "keyword": "There is a minimum announce time lock, please wait another 57 seconds.",
            "description": "最小announce时间间隔限制"
        },
        {
            "keyword_type": "failed",
            "keyword": "There is a minimum announce time lock, please wait another 8 seconds.",
            "description": "最小announce时间间隔限制"
        },
        {
            "keyword_type": "failed",
            "keyword": "There is a minimum announce time of 300 seconds",
            "description": "最小announce时间间隔为300秒"
        },
        {
            "keyword_type": "failed",
            "keyword": "This torrent has other active clients on this IP.",
            "description": "此IP上已有其他活动客户端"
        },
        {
            "keyword_type": "failed",
            "keyword": "Torrent not exists",
            "description": "种子不存在"
        },
        {
            "keyword_type": "failed",
            "keyword": "Torrent not exists (0.001339384)",
            "description": "种子不存在"
        },
        {
            "keyword_type": "failed",
            "keyword": "Torrent not exists (0.001526497)",
            "description": "种子不存在"
        },
        {
            "keyword_type": "failed",
            "keyword": "Torrent not exists (0.001741931)",
            "description": "种子不存在"
        },
        {
            "keyword_type": "failed",
            "keyword": "Torrent not exists (0.001883446)",
            "description": "种子不存在"
        },
        {
            "keyword_type": "failed",
            "keyword": "Torrent not found.",
            "description": "种子未找到"
        },
        {
            "keyword_type": "failed",
            "keyword": "Torrent not registered with this tracker",
            "description": "种子未在此tracker注册"
        },
        {
            "keyword_type": "failed",
            "keyword": "Tracker HTTP response 0 (No Response)",
            "description": "Tracker无响应"
        },
        {
            "keyword_type": "failed",
            "keyword": "Tracker HTTP response 301 (Moved Permanently)",
            "description": "Tracker永久重定向"
        },
        {
            "keyword_type": "failed",
            "keyword": "Tracker HTTP response 302 (Found)",
            "description": "Tracker临时重定向"
        },
        {
            "keyword_type": "failed",
            "keyword": "Tracker HTTP response 403 (Forbidden)",
            "description": "Tracker禁止访问"
        },
        {
            "keyword_type": "failed",
            "keyword": "Tracker HTTP response 404 (Not Found)",
            "description": "Tracker未找到"
        },
        {
            "keyword_type": "failed",
            "keyword": "Tracker HTTP response 408 (Request Timeout)",
            "description": "Tracker请求超时"
        },
        {
            "keyword_type": "failed",
            "keyword": "Tracker HTTP response 429 (Unknown Error)",
            "description": "Tracker请求过多"
        },
        {
            "keyword_type": "failed",
            "keyword": "Tracker HTTP response 468 (Unknown Error)",
            "description": "Tracker未知错误"
        },
        {
            "keyword_type": "failed",
            "keyword": "Tracker HTTP response 500 (Internal Server Error)",
            "description": "Tracker服务器内部错误"
        },
        {
            "keyword_type": "failed",
            "keyword": "Tracker HTTP response 502 (Bad Gateway)",
            "description": "Tracker网关错误"
        },
        {
            "keyword_type": "failed",
            "keyword": "Tracker HTTP response 503 (Service Unavailable)",
            "description": "Tracker服务不可用"
        },
        {
            "keyword_type": "failed",
            "keyword": "Tracker HTTP response 504 (Gateway Timeout)",
            "description": "Tracker网关超时"
        },
        {
            "keyword_type": "failed",
            "keyword": "Tracker HTTP response 520 (Unknown Error)",
            "description": "Tracker未知错误"
        },
        {
            "keyword_type": "failed",
            "keyword": "Tracker HTTP response 521 (Unknown Error)",
            "description": "Tracker未知错误"
        },
        {
            "keyword_type": "failed",
            "keyword": "Tracker HTTP response 522 (Unknown Error)",
            "description": "Tracker未知错误"
        },
        {
            "keyword_type": "failed",
            "keyword": "Tracker HTTP response 525 (Unknown Error)",
            "description": "Tracker未知错误"
        },
        {
            "keyword_type": "failed",
            "keyword": "Tracker HTTP response 530 (Unknown Error)",
            "description": "Tracker未知错误"
        },
        {
            "keyword_type": "failed",
            "keyword": "Tracker did not respond",
            "description": "Tracker未响应"
        },
        {
            "keyword_type": "failed",
            "keyword": "Tracker in system maintaining",
            "description": "Tracker系统维护中"
        },
        {
            "keyword_type": "failed",
            "keyword": "You already are downloading the same torrent. You may only leech from one location at a time.",
            "description": "已在其他位置下载相同种子"
        },
        {
            "keyword_type": "failed",
            "keyword": "You already are uploading the same torrent. You may only seed from one location at a time.",
            "description": "已在其他位置做种相同种子"
        },
        {
            "keyword_type": "failed",
            "keyword": "You are seeding or downloading this torrent from other location.[17146][12026] (0.001436151)",
            "description": "已在其他位置做种或下载"
        },
        {
            "keyword_type": "failed",
            "keyword": "You are seeding or downloading this torrent from other location.[17168][12026] (0.001817757)",
            "description": "已在其他位置做种或下载"
        },
        {
            "keyword_type": "failed",
            "keyword": "You are seeding or downloading this torrent from other location.[17195][12026] (0.001425084)",
            "description": "已在其他位置做种或下载"
        },
        {
            "keyword_type": "failed",
            "keyword": "You cannot seed the same torrent from more than 1 location.",
            "description": "不能从多个位置做种相同种子"
        },
        {
            "keyword_type": "failed",
            "keyword": "You cannot seed the same torrent from more than 1 locations.",
            "description": "不能从多个位置做种相同种子"
        },
        {
            "keyword_type": "failed",
            "keyword": "You cannot seed the same torrent from more than 3 locations.",
            "description": "不能从超过3个位置做种相同种子"
        },
        {
            "keyword_type": "failed",
            "keyword": "You cannot seed the same torrent in the same location from more than 1 client.",
            "description": "不能在同一位置从多个客户端做种相同种子"
        },
        {
            "keyword_type": "failed",
            "keyword": "Your account is not enabled! ( Current `Disabled` )",
            "description": "账户未启用"
        },
        {
            "keyword_type": "failed",
            "keyword": "Your account is not enabled. (Current: disabled).",
            "description": "账户未启用"
        },
        {
            "keyword_type": "failed",
            "keyword": "[err req too frequently] wait for 4 seconds and try announce again",
            "description": "请求过于频繁，等待4秒后重试"
        },
        {
            "keyword_type": "failed",
            "keyword": "[err req too frequently] wait for 9 seconds and try announce again",
            "description": "请求过于频繁，等待9秒后重试"
        },
        {
            "keyword_type": "failed",
            "keyword": "err torrent banned",
            "description": "种子被禁止"
        },
        {
            "keyword_type": "failed",
            "keyword": "err torrent deleted due to dupe, related torrent: /details.php?id=279136",
            "description": "种子因重复被删除"
        },
        {
            "keyword_type": "failed",
            "keyword": "err torrent deleted due to dupe, related torrent: /details.php?id=30613",
            "description": "种子因重复被删除"
        },
        {
            "keyword_type": "failed",
            "keyword": "err torrent deleted due to dupe, related torrent: /details.php?id=36854",
            "description": "种子因重复被删除"
        },
        {
            "keyword_type": "failed",
            "keyword": "err torrent deleted due to dupe, related torrent: /details.php?id=50119",
            "description": "种子因重复被删除"
        },
        {
            "keyword_type": "failed",
            "keyword": "err torrent deleted due to dupe, related torrent: /details.php?id=50128",
            "description": "种子因重复被删除"
        },
        {
            "keyword_type": "failed",
            "keyword": "err torrent deleted due to other",
            "description": "种子因其他原因被删除"
        },
        {
            "keyword_type": "failed",
            "keyword": "err torrent not registered with this tracker",
            "description": "种子未在此tracker注册"
        },
        {
            "keyword_type": "failed",
            "keyword": "err: You cannot seed the same torrent from more than 3 locations",
            "description": "不能从超过3个位置做种相同种子"
        },
        {
            "keyword_type": "failed",
            "keyword": "skipping tracker announce (unreachable)",
            "description": "跳过tracker announce（无法访问）"
        },
        {
            "keyword_type": "failed",
            "keyword": "torrent banned",
            "description": "种子被禁止"
        },
        {
            "keyword_type": "failed",
            "keyword": "torrent error A",
            "description": "种子错误A"
        },
        {
            "keyword_type": "failed",
            "keyword": "torrent not exists",
            "description": "种子不存在"
        },
        {
            "keyword_type": "failed",
            "keyword": "torrent not registered with this tracker",
            "description": "种子未在此tracker注册"
        },
        {
            "keyword_type": "failed",
            "keyword": "torrent not registered with this tracker (destroyed)",
            "description": "种子未在此tracker注册（已销毁）"
        },
        {
            "keyword_type": "failed",
            "keyword": "torrent not registered with this tracker 2022.1",
            "description": "种子未在此tracker注册 2022.1"
        },
        {
            "keyword_type": "failed",
            "keyword": "torrent not registered with this tracker 2022.2",
            "description": "种子未在此tracker注册 2022.2"
        },
        {
            "keyword_type": "failed",
            "keyword": "unregistered torrent",
            "description": "未注册的种子"
        },
        {
            "keyword_type": "failed",
            "keyword": "you should announce to: https://tracker.ptskit.org/announce.php",
            "description": "应该announce到指定URL"
        },
        {
            "keyword_type": "failed",
            "keyword": "您不能在同一位置从多个客户端同时上传同一个种子",
            "description": "不能在同一位置从多个客户端同时上传"
        },
        {
            "keyword_type": "failed",
            "keyword": "您已在 www.hdkylin.top 汇报过了",
            "description": "已在其他站点汇报过"
        },
        {
            "keyword_type": "failed",
            "keyword": "您已经在一个客户端做种。一次只能从一个位置做种种子.",
            "description": "已在一个客户端做种"
        },
        {
            "keyword_type": "failed",
            "keyword": "种子已被删除或尚未发布",
            "description": "种子已被删除或尚未发布"
        },
        {
            "keyword_type": "failed",
            "keyword": "该种子已被禁止。",
            "description": "种子已被禁止"
        },
        {
            "keyword_type": "failed",
            "keyword": "该种子没有在我们的 Tracker 上注册.",
            "description": "种子未在Tracker上注册"
        },
        {
            "keyword_type": "failed",
            "keyword": "除发布者和补种外不允许多重客户端上传。",
            "description": "除发布者和补种外不允许多重客户端上传"
        },

        # ========== 忽略池 ==========
        {
            "keyword_type": "ignored",
            "keyword": "<none>",
            "description": "空消息，忽略处理"
        },
    ]


def init_default_tracker_keywords(db) -> None:
    """
    初始化默认的tracker关键词配置

    只插入缺失的关键词，使用keyword字段作为唯一标识

    Args:
        db: 数据库会话
    """
    from app.torrents.models import TrackerKeywordConfig
    import uuid

    # 获取默认关键词列表
    default_keywords = get_default_tracker_keywords()

    # 查询数据库中已存在的关键词
    existing_keywords = {kw.keyword for kw in db.query(TrackerKeywordConfig.keyword).filter(
        TrackerKeywordConfig.dr == 0
    ).all()}

    # 统计
    inserted_count = 0
    skipped_count = 0

    # 插入缺失的关键词
    now = datetime.now()
    for kw_data in default_keywords:
        if kw_data["keyword"] not in existing_keywords:
            keyword = TrackerKeywordConfig(
                keyword_type=kw_data["keyword_type"],
                keyword=kw_data["keyword"],
                description=kw_data.get("description"),
                priority=100,
                enabled=True,
                create_time=now,
                update_time=now,
                create_by="system",
                update_by="system",
                dr=0
            )
            db.add(keyword)
            inserted_count += 1
        else:
            skipped_count += 1

    if inserted_count > 0:
        db.commit()
        print(f"[OK] Tracker keywords initialized: added {inserted_count}, skipped {skipped_count}")
    else:
        print(f"[INFO] Tracker keywords data complete ({len(default_keywords)}), skip initialization")
