# -*- coding: utf-8 -*-
"""
tests/api 共享测试基础设施

提供 API 级回归测试共用的工具函数（非 fixture）。pytest 会自动发现本文件中的
fixture；普通函数需在各测试文件显式 import：`from tests.api.conftest import make_torrent`。

make_torrent —— 构造真 ORM TorrentInfo 的工厂
----------------------------------------------
TorrentInfo.__init__ 有 29 个位置参数（其中前 24 个是业务字段，且 has_tracker_error
是 NOT NULL 但 __init__ 未赋值），直接在测试里手写 24 个位置参数极易出错（顺序错位、
漏设 has_tracker_error 导致 commit 时 IntegrityError）。

本工厂把这些陷阱集中收口：调用方只用业务关键字段（info_id/downloader_id/hash_/name 等），
其余位置参数走合理默认值。已收敛 test_duplicate_torrents_api / test_torrent_list_api /
test_recycle_bin_api 三个文件原本各自维护的重复 _make_torrent 定义。
"""

from datetime import datetime

from app.torrents.models import TorrentInfo


def make_torrent(
    db,
    *,
    info_id,
    downloader_id,
    hash_,
    name,
    downloader_name="dl",
    size=0,
    status="seeding",
    error_reason=None,
    dr=0,
    progress=0.0,
    added_date=None,
    completed_date=None,
    has_tracker_error=False,
    deleted_at=None,
    torrent_id=None,
    ratio="0",
    ratio_limit="0",
    tags="",
    category="",
    super_seeding="否",
    enabled=True,
    save_path="/path",
):
    """构造真 ORM TorrentInfo 并写入 db（按位置传 24 个业务字段）。

    Args:
        db: 已打开的（同步）Session，函数内会 add + commit。
        info_id: 种子业务 ID（必填）。
        downloader_id: 下载器 ID（必填）。
        hash_: 种子 hash（必填）。
        name: 种子名称（必填）。
        downloader_name: 下载器名称，默认 "dl"。
        size: 种子大小，默认 0。
        status: 种子状态，默认 "seeding"。
        dr: 软删除标识，0=未删除 / 1=已彻底删除，默认 0。
        progress: 进度（0.0~100.0），默认 0.0。
        added_date: 添加时间，默认 datetime(2026,1,1,12,0,0)。
        completed_date: 完成时间，默认 None。
        has_tracker_error: 是否有 tracker 错误，默认 False。
            ⚠ 该列 NOT NULL 但 __init__ 未赋值，必须显式设，否则 commit 时 IntegrityError。
        deleted_at: 软删除时间（回收站种子用），默认 None。
            非空 + dr=0 表示回收站种子；为空表示活跃种子。
        torrent_id: 下载器内部 torrent id，默认 None。
        ratio: 分享比率（字符串列），默认 "0"。
        ratio_limit: 比率限制（字符串列），默认 "0"。
        tags: 标签（逗号分隔字符串列），默认 ""。
        category: 分类（单值字符串列），默认 ""。
        super_seeding: 超级做种，默认 "否"。
        enabled: 启用状态，默认 True。
        save_path: 保存路径，默认 "/path"。

    Returns:
        已 commit 的 TorrentInfo 实例（可继续读其属性）。
    """
    if added_date is None:
        added_date = datetime(2026, 1, 1, 12, 0, 0)
    t = TorrentInfo(
        info_id,  # id_
        downloader_id,  # downloader_id
        downloader_name,  # downloader_name
        torrent_id,  # torrent_id
        hash_,  # hash
        name,  # name
        save_path,  # save_path
        size,  # size
        status,  # status
        progress,  # progress
        None,  # torrent_file
        added_date,  # added_date
        completed_date,  # completed_date
        ratio,  # ratio
        ratio_limit,  # ratio_limit
        tags,  # tags
        category,  # category
        super_seeding,  # super_seeding
        enabled,  # enabled
        added_date,  # create_time
        "tester",  # create_by
        added_date,  # update_time
        "tester",  # update_by
        dr,  # dr
    )
    t.has_tracker_error = has_tracker_error  # NOT NULL，__init__ 未赋值
    t.error_reason = error_reason
    if deleted_at is not None:
        t.deleted_at = deleted_at
    db.add(t)
    db.commit()
    return t
