"""种子添加辅助函数（服务层共享，feature mcp-service-capabilities W3-③）。

从 ``app/api/endpoints/torrent_helpers.py`` 原样迁移（PLANS/mcp-service-capabilities
§11.1 分层债收尾）：单种子添加（TorrentAddService）、批量添加
（TorrentBatchAddService）与状态端点共用的 info hash 计算、添加后统一
「轮询定位 + 落库/刷新 + tracker 刷新」（TorrentLookupService 消费方）与审计写入辅助。服务层依赖 HTTP endpoint 层会阻断
MCP 共用边界（G0 禁 app/mcp import app.api 的口径下同款约束），
故归属到服务层；HTTP 端点（torrent_status.py）改为正向依赖本模块。

守卫登记：本模块是架构守卫对象（tests/architecture/test_async_downloader_calls.py），
模块级客户端库 import 不允许出现（先例：recycle_bin_service 同款处理）。
2026-10-08 二期起另承载：SQLite 锁重试四件套、添加后统一「轮询定位 + 落库/刷新」
（wait_and_upsert_torrent_row）与 tracker 立即刷新（refresh_trackers_after_add，
注册表倒置注入 endpoints 层实现）；原 get_transmission_torrent_info /
create_*_torrent_record 已随消费方收敛删除。
"""

import asyncio
import hashlib
import logging
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Tuple

from sqlalchemy.exc import OperationalError

import bencodepy

from app.database import AsyncSessionLocal
from app.models.setting_templates import DownloaderTypeEnum
from app.services.audit_service import get_audit_service
from app.services.downloader_api_runtime import DownloadLane, call_downloader_api
from app.services.torrent_ratio_values import normalize_ratio
from app.torrents.models import TorrentInfo as torrentInfoModel

logger = logging.getLogger(__name__)


async def calculate_info_hash(torrent_file_path: str) -> str:
    """计算种子文件的info_hash"""
    try:
        # 将文件读取和解析操作放到线程池中执行
        def read_and_decode_file(file_path):
            with open(file_path, "rb") as f:
                file_content = f.read()
            return bencodepy.decode(file_content)

        torrent_data = await asyncio.to_thread(read_and_decode_file, torrent_file_path)

        # 获取info部分并计算SHA1哈希
        info_data = bencodepy.encode(torrent_data[b"info"])
        info_hash = hashlib.sha1(info_data).hexdigest()

        return info_hash
    except Exception as e:
        raise Exception(f"计算info_hash失败: {str(e)}")


# ==================== 添加后统一落库与刷新（feature torrent-lookup-service-2026-10-08 二期） ====================

# 添加后轮询下载器出现新种子的次数与间隔（对齐被替换的 30×1s 手写轮询语义）；
# 模块级常量供测试置零加速（patch 后函数内读取即时生效）
ADD_POLL_RETRIES = 30
ADD_POLL_INTERVAL = 1.0

# 刷新实时字段白名单：仅覆盖随下载器状态变化的字段；create_*/auxiliary_seed_count/
# torrent_file/dr/deleted_at 等身份与管理字段不碰（由同步链路或删除链路维护）
_REFRESH_FIELDS_NOTE = (
    "name/size/status/error_reason/progress/ratio/save_path/tags/category/completed_date/update_time/update_by"
)


_SQLITE_BUSY_ERROR_CODES = (5, 517, 518)
# 写锁冲突有界重试：5 次 × 0.2s 起步线性退避，总等待约 3s，远小于 busy_timeout=15s 兜底。
_LOCKED_RETRY_MAX = 5
_LOCKED_RETRY_BASE_DELAY_SECONDS = 0.2


def _sqlite_error_code(exc: BaseException) -> Optional[int]:
    """提取 sqlite3 原生错误码（Python>=3.11 经 exc.orig.sqlite_errorcode 暴露）。

    用于事后鉴别锁冲突类型（BUSY=5 与 BUSY_SNAPSHOT=518），旧运行时无该属性时返回 None。
    """
    orig = getattr(exc, "orig", None)
    code = getattr(orig, "sqlite_errorcode", None)
    if code is None:
        return None
    try:
        return int(code)
    except (TypeError, ValueError):
        return None


def _is_sqlite_locked_error(exc: BaseException) -> bool:
    """判定是否为 SQLite 写锁冲突（决定是否走有界重试）。"""
    if not isinstance(exc, OperationalError):
        return False
    code = _sqlite_error_code(exc)
    if code is not None:
        return code in _SQLITE_BUSY_ERROR_CODES
    return "database is locked" in str(exc).lower()


async def _insert_torrent_record_with_retry(db: Any, record_factory: Callable[[], Any]) -> Any:
    """以短事务插入单条新种子记录，对 SQLite 写锁冲突做有界重试。

    WAL 模式下，若会话携带有已陈旧的读事务（期间其他连接提交过写入），commit 升级
    写事务会立即返回 BUSY_SNAPSHOT（"database is locked"，busy_timeout 不生效）；
    正确处置是 rollback 丢弃陈旧快照后重开事务重试。每次重试用 record_factory 重建
    ORM 实例：rollback 会 expunge 尚未提交的 pending 对象，复用旧实例会因带主键被
    视作 persistent 而静默不产生 INSERT。非锁冲突错误不重试，直接上抛。
    """
    db_torrent: Any = None
    for attempt in range(1, _LOCKED_RETRY_MAX + 1):
        db_torrent = record_factory()
        db.add(db_torrent)
        try:
            db.commit()
            break
        except OperationalError as exc:
            db.rollback()
            if not _is_sqlite_locked_error(exc) or attempt == _LOCKED_RETRY_MAX:
                raise
            logger.warning(
                "新种子记录落库遇到 SQLite 写锁冲突，回滚后重试（第 %s/%s 次，sqlite_errorcode=%s）",
                attempt,
                _LOCKED_RETRY_MAX,
                _sqlite_error_code(exc),
            )
            await asyncio.sleep(_LOCKED_RETRY_BASE_DELAY_SECONDS * attempt)
    db.refresh(db_torrent)
    return db_torrent


def _epoch_to_datetime(epoch: Any, *, default: Any = None) -> Any:
    """epoch 秒 → datetime；非法/非正值返回 default（0=未知，qB sentinel 已在上游归零）。"""
    try:
        value = int(epoch or 0)
    except (TypeError, ValueError):
        return default
    if value <= 0:
        return default
    return datetime.fromtimestamp(value)


def _build_row_from_vo(downloader: Any, info_hash: str, vo: Dict[str, Any], operator: str) -> torrentInfoModel:
    """按统一 VO 创建种子行（字段形态对齐被替换的 create_*_torrent_record）。

    - torrent_id：qB/TR 统一用 info_hash（TR 数字 id 不持久化，TorrentFetcher 同款决策）；
    - added_date 非法/为 0 时以本地时间兑底（种子刚添加，入库时间即添加时间）；
    - qB torrent_file 按 BT_backup 约定路径推导（原 create_qbittorrent_torrent_record 同款）。
    """
    downloader_type = DownloaderTypeEnum.normalize(getattr(downloader, "downloader_type", None))
    now = datetime.now()
    is_qb = downloader_type == DownloaderTypeEnum.QBITTORRENT.value
    torrent_file = (
        "/config/qbittorrent/BT_backup/" + info_hash + ".torrent" if is_qb else (vo.get("torrent_file") or "")
    )
    return torrentInfoModel(
        id_=str(uuid.uuid4()),
        downloader_id=str(downloader.downloader_id),
        downloader_name=downloader.nickname,
        torrent_id=info_hash,
        hash=info_hash,
        name=vo.get("name") or info_hash,
        save_path=vo.get("download_path") or "",
        size=float(vo.get("size") or 0),
        status=vo.get("state") or "downloading",
        error_reason=vo.get("error_reason"),
        progress=float(vo.get("progress") or 0),
        torrent_file=torrent_file,
        added_date=_epoch_to_datetime(vo.get("addition_date"), default=now),
        completed_date=_epoch_to_datetime(vo.get("completion_date")),
        ratio=normalize_ratio(vo.get("ratio")).value_for_insert(),
        # VO 不含单种比率限制（qB 投影/TR seedRatioLimit 均未取）；NULL=无显式限制，
        # 真实值由同步链路补齐（与既有 create_* 的 ratio_limit 语义一致）
        ratio_limit=None,
        tags=str(vo.get("tags") or ""),
        category=str(vo.get("category") or ""),
        super_seeding="",
        enabled=1,
        create_time=now,
        create_by=operator,
        update_time=now,
        update_by=operator,
        dr=0,
    )


def _apply_vo_refresh(row: torrentInfoModel, vo: Dict[str, Any], operator: str) -> None:
    """按 VO 刷新既有行的实时字段白名单（重复添加/重建场景：不等下一轮定时同步）。"""
    row.name = vo.get("name") or row.name
    # 防御：size/progress/ratio 转换异常时保留旧值（单字段脏数据不炸整行刷新）
    try:
        row.size = float(vo.get("size") or 0)
    except (TypeError, ValueError):
        pass
    try:
        row.progress = float(vo.get("progress") or 0)
    except (TypeError, ValueError):
        pass
    row.status = vo.get("state") or row.status
    # TR 种子级错误独立于 status：error_reason 随 VO 同步（恢复时 VO 为 None → 清空历史原因）
    row.error_reason = vo.get("error_reason")
    try:
        row.ratio = normalize_ratio(vo.get("ratio")).value_for_insert()
    except (TypeError, ValueError):
        pass
    row.save_path = vo.get("download_path") or row.save_path
    row.tags = str(vo.get("tags") or "")
    row.category = str(vo.get("category") or "")
    completed = _epoch_to_datetime(vo.get("completion_date"))
    if completed is not None:
        row.completed_date = completed
    row.update_time = datetime.now()
    row.update_by = operator


async def wait_and_upsert_torrent_row(
    db: Any,
    store: Any,
    downloader: Any,
    info_hash: str,
    *,
    operator: str = "admin",
    poll_retries: Optional[int] = None,
    poll_interval: Optional[float] = None,
) -> Tuple[Optional[torrentInfoModel], bool, Optional[str]]:
    """添加成功后统一「轮询定位 + 落库/刷新」种子行（单/批量添加共用）。

    流程：
    1. TorrentLookupService.get_by_hash 轮询（命中即停；远程异常也重试，
       瞬时故障不直接判死）；
    2. upsert：无行→按 VO 创建（SQLite 写锁重试，锁四件套内联本模块）；
       有行→刷新实时字段白名单（{_REFRESH_FIELDS_NOTE}）。

    Returns:
        (种子行, 是否新建, err)：err 非空表示轮询超时/落库失败（行为 None）。
    """
    from app.services.torrent_lookup_service import TorrentLookupService  # noqa: PLC0415

    # 锁重试已内联本模块（原批量模块四件套迁移）：helpers 属 MCP 共享闭包，
    # 不得反向依赖含 fastapi import 的批量模块（service purity 守卫）

    retries = ADD_POLL_RETRIES if poll_retries is None else poll_retries
    interval = ADD_POLL_INTERVAL if poll_interval is None else poll_interval

    lookup = TorrentLookupService(store)
    downloader_id = str(downloader.downloader_id)
    vo: Optional[Dict[str, Any]] = None
    last_err: Optional[str] = None
    for _ in range(max(1, retries)):
        vo, err = await lookup.get_by_hash(downloader_id, info_hash)
        if err is not None:
            last_err = err
        if vo is not None:
            break
        await asyncio.sleep(max(0.0, interval))

    if vo is None:
        return None, False, last_err or "下载器中未出现该种子（轮询超时）"

    # 落库异常不捕获：向上抛给调用方既有 except 链——批量路径依赖它提取
    # sqlite_errorcode 做锁复发鉴别（_add_one_torrent 错误格式化），单添加路径
    # 依赖 except Exception 兑底防冒泡（prod-hotfix-2026-07-19 语义）
    existing = (
        db.query(torrentInfoModel)
        .filter(torrentInfoModel.hash == info_hash)
        .filter(torrentInfoModel.dr == 0)
        .filter(torrentInfoModel.downloader_id == downloader_id)
        .first()
    )
    if existing is not None:
        # 刷新路径与 insert 路径对称的锁重试（验收 P2 修复）：BUSY 5/517/518 回滚后
        # 重新应用刷新再提交（rollback 会丢弃未提交的字段变更，须重放 _apply_vo_refresh）；
        # 非锁冲突不重试直接上抛
        for attempt in range(1, _LOCKED_RETRY_MAX + 1):
            _apply_vo_refresh(existing, vo, operator=operator)
            try:
                db.commit()
                break
            except OperationalError as exc:
                db.rollback()
                if not _is_sqlite_locked_error(exc) or attempt == _LOCKED_RETRY_MAX:
                    raise
                logger.warning(
                    "刷新既有种子行遇到 SQLite 写锁冲突，回滚后重试（第 %s/%s 次，sqlite_errorcode=%s）",
                    attempt,
                    _LOCKED_RETRY_MAX,
                    _sqlite_error_code(exc),
                )
                await asyncio.sleep(_LOCKED_RETRY_BASE_DELAY_SECONDS * attempt)
        db.refresh(existing)
        return existing, False, None
    row = await _insert_torrent_record_with_retry(db, lambda: _build_row_from_vo(downloader, info_hash, vo, operator))
    return row, True, None


# tracker 同步钩子注册表（依赖倒置）：提取/批量写入函数位于 endpoint 层
# （torrents_async.py），共享 service 层禁止 import endpoint 层（MCP service
# purity 守卫）——由 torrents_async 模块加载时经 register_tracker_sync_hooks
# 注册实现，运行时主应用必然已加载该模块；未注册时（单测/极简启动）跳过刷新。
_TrackerRowExtractor = Callable[[Any, str, str, Any], "tuple[list, set]"]
_TrackerBatchWriter = Callable[[Any, list, Any], Any]
_tracker_row_extractor: Optional[_TrackerRowExtractor] = None
_tracker_batch_writer: Optional[_TrackerBatchWriter] = None


def register_tracker_sync_hooks(row_extractor: _TrackerRowExtractor, batch_writer: _TrackerBatchWriter) -> None:
    """注册 endpoint 层的 tracker 提取/批量写入实现（torrents_async 加载时调用）。"""
    global _tracker_row_extractor, _tracker_batch_writer
    _tracker_row_extractor = row_extractor
    _tracker_batch_writer = batch_writer


async def refresh_trackers_after_add(store: Any, downloader: Any, info_hash: str, torrent_info_id: str) -> bool:
    """添加成功后立即刷新种子的 tracker 行（best-effort，失败仅 warning 不影响添加结果）。

    复用同步链路的纯提取函数（过滤 DHT/PeX/LSD + 污染 URL 拦截）与批量 upsert
    （软删恢复/物理删/变更检测 upsert/mark_removed 四步），经注册表注入：

    - qB: torrents_trackers(hash)（经 INTERACTIVE lane）；
    - TR: get_torrents(ids, arguments=["trackerStats"])（原生 TrackerStats 对象
      与提取函数的 TR 分支字段访问完全匹配）。
    """
    if _tracker_row_extractor is None or _tracker_batch_writer is None:
        logger.debug("tracker 同步钩子未注册，跳过添加后 tracker 刷新")
        return False

    downloader_id = str(downloader.downloader_id)
    downloader_type = DownloaderTypeEnum.normalize(getattr(downloader, "downloader_type", None))
    now = datetime.now()
    try:
        if downloader_type == DownloaderTypeEnum.QBITTORRENT.value:
            trackers = await call_downloader_api(
                downloader_id,
                DownloadLane.INTERACTIVE,
                downloader.client.torrents_trackers,
                args=(info_hash,),
                operation="add_refresh_qb_trackers",
            )
            torrent_info: Any = {"hash": info_hash, "trackers": trackers or []}
            dl_name = "qbittorrent"
        else:
            torrents = await call_downloader_api(
                downloader_id,
                DownloadLane.INTERACTIVE,
                downloader.client.get_torrents,
                kwargs={"ids": [info_hash], "arguments": ["trackerStats"]},
                operation="add_refresh_tr_trackers",
            )
            if not torrents:
                return False
            torrent_info = torrents[0]
            dl_name = "transmission"

        rows, _current_urls = _tracker_row_extractor(torrent_info, torrent_info_id, dl_name, now)
        if not rows:
            return False
        async with AsyncSessionLocal() as async_db:
            await _tracker_batch_writer(async_db, rows, now)
            await async_db.commit()
        return True
    except Exception as exc:  # noqa: BLE001 - best-effort：tracker 刷新失败不影响添加结果
        logger.warning("添加后刷新 tracker 失败 downloader_id=%s hash=%s: %s", downloader_id, info_hash, exc)
        return False


# ==================== 审计日志辅助函数 ====================


async def _write_audit_log_async(
    operation_type: str,
    operator: str,
    torrent_info_id: str,
    operation_detail: Dict[str, Any],
    torrent_name: Optional[str],
    torrent_hash: Optional[str],
    downloader_id: str,
    operation_result: str,
    error_message: Optional[str] = None,
    new_value: Optional[Dict[str, Any]] = None,
    old_value: Optional[Dict[str, Any]] = None,
    audit_info: Optional[Dict[str, str]] = None,
):
    """异步写入审计日志的辅助函数"""
    try:
        async with AsyncSessionLocal() as async_db:
            audit_service = await get_audit_service(async_db)

            # 构建完整的操作详情
            full_detail = operation_detail.copy()
            if torrent_name:
                full_detail["torrent_name"] = torrent_name
            if torrent_hash:
                full_detail["torrent_hash"] = torrent_hash

            await audit_service.log_operation(
                operation_type=operation_type,
                operator=operator,
                torrent_info_id=torrent_info_id,
                operation_detail=full_detail,
                old_value=old_value,
                new_value=new_value,
                operation_result=operation_result,
                error_message=error_message,
                downloader_id=downloader_id,
                **(audit_info or {}),
            )
    except Exception as audit_error:
        logging.error(f"记录审计日志失败: {str(audit_error)}", exc_info=True)


def _safe_write_audit_log(
    operation_type: str,
    operator: str,
    torrent_info_id: str = "",
    operation_detail: Optional[Dict[str, Any]] = None,
    torrent_name: Optional[str] = None,
    torrent_hash: Optional[str] = None,
    downloader_id: str = "",
    operation_result: str = "success",
    error_message: Optional[str] = None,
    new_value: Optional[Dict[str, Any]] = None,
    old_value: Optional[Dict[str, Any]] = None,
    audit_info: Optional[Dict[str, str]] = None,
):
    """
    安全地写入审计日志（带异常处理和日志记录）

    修复CRITICAL #4: asyncio.create_task的异常会被静默忽略
    使用此包装函数确保审计日志异常不会丢失，同时记录到日志文件中
    """
    operation_detail = operation_detail or {}
    try:
        asyncio.create_task(
            _write_audit_log_async(
                operation_type=operation_type,
                operator=operator,
                torrent_info_id=torrent_info_id,
                operation_detail=operation_detail,
                torrent_name=torrent_name,
                torrent_hash=torrent_hash,
                downloader_id=downloader_id,
                operation_result=operation_result,
                error_message=error_message,
                new_value=new_value,
                old_value=old_value,
                audit_info=audit_info,
            )
        )
    except Exception as e:
        # 记录创建任务失败（极少发生）
        logging.error(
            f"创建审计日志任务失败 [operation_type={operation_type}, torrent_info_id={torrent_info_id}]: {str(e)}",
            exc_info=True,
        )
