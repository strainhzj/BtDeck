# -*- coding: utf-8 -*-
"""通用种子定位服务（qBittorrent / Transmission 统一 hash 精确匹配）。

设计目标：为后续消费方（DB 多条件查询、MCP 工具、批量校验等）提供毫秒级
"按 info_hash 定位种子并获取实时信息"的底层通用方法。

核心机制：
1. hash 精确匹配走下载器服务端索引（双端唯一 O(1) 能力）：
   - qB: ``client.torrents_info(torrent_hashes=[...])`` —— 服务端按 hash 索引，
     多 hash 由 SDK 以 ``|`` 连接，单次请求（qbittorrent-api 2025.2.0 实测签名）。
   - TR: ``client.get_torrents(ids=[...], arguments=最小投影)`` —— 服务端按
     ids 索引；``ids`` 接受数字 id 或 40 位 hex infohash（RPC 规范双形态，本项目
     全链路用 hash：数字 id 不持久化，重启即变）；``arguments`` 字段投影避免 TR
     默认全字段（含 peers/trackers/files）大载荷（transmission-rpc 7.0.11 会
     自动补 ``id``/``hashString``，str 形态强制 40 位 hex 校验——64 位 v2 hash
     在 SDK 层拋 ValueError 归一为 err，与 TR 服务端不支持纯 v2 种子一致）。
2. 批量分块：qB 每块 ≤100（torrents/info 的 hashes 走 GET query，防 URL 超长）；
   TR 每块 ≤200（对齐 TorrentFetcher 既定批次大小）。
3. 统一 VO 口径（与删除适配器 get_torrent_info 的 13 字段对齐并修复双端不一致）：
   - ``hash`` 小写（P0-D 口径）；``state`` 经 TorrentStatusMapper 归一 + ``raw_state`` 原始值；
   - ``progress`` 统一 0~100（qB 原生 0~1 ×100；TR SDK 原生 0~100 透传）；
   - ``completion_date``/``addition_date`` 统一 epoch 秒 int（0=未知；qB 未完成
     sentinel -8640000000000 归 0；TR datetime 转 timestamp）。
4. 远程调用一律经 ``call_downloader_api`` INTERACTIVE lane（P0-04 修复约定：
   单种子查询类轻量交互不与 SYNC/TRACKER 后台任务抢容量）。
5. 客户端只从 ``app.state.store`` 快照获取（downloader-connection 强制约束）。

错误语义：
- 返回 ``(result, err)`` 元组；``err`` 非空表示调用层错误（此时批量结果可能是部分数据）；
- ``err`` 为 None 且单查结果为 None / 批量结果缺键，表示种子确实不存在
  （双端对未知 hash 均返回空列表、不报错，seed_transfer_service 已验证）。
"""

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.core.runtime_context import RuntimeContext
from app.core.torrent_status_mapper import TorrentStatusMapper
from app.models.setting_templates import DownloaderTypeEnum
from app.services.downloader_api_runtime import DownloadLane, call_downloader_api

logger = logging.getLogger(__name__)

# qB 批量分块上限：torrents/info 的多 hash 经 GET query（a|b|c...）下发，
# 单 hash 41 字节，100 个 ≈ 4.1KB，防 URL 超长被 4xx 拒绝。
_QB_HASH_CHUNK = 100
# TR 批量分块上限：POST body 无 URL 限制，对齐 TorrentFetcher.TR_BATCH_SIZE。
_TR_HASH_CHUNK = 200

# 合法 hash 长度：BT v1=40 位 hex；BitTorrent v2=64 位 hex（向前兼容）。
_VALID_HASH_LENGTHS = (40, 64)
_HASH_HEX_CHARS = frozenset("0123456789abcdef")

# TR 最小字段投影（transmission-rpc 原生 camelCase field 名；SDK 自动补 id/hashString，
# 故此处不列）。集合必须完整覆盖 VO 所需属性，缺失 field 的属性访问会抛 KeyError。
# torrentFile 仅添加后落库链路消费（种子文件路径）。
_TR_FIELDS: Tuple[str, ...] = (
    "name",
    "totalSize",
    "status",
    "percentDone",
    "uploadRatio",
    "downloadedEver",
    "uploadedEver",
    "downloadDir",
    "doneDate",
    "addedDate",
    "labels",
    "torrentFile",
    # error/errorString：种子级错误独立于 status（error>=2 归 "error" 态，
    # errorString 同步为 error_reason，对齐同步链路 resolve/extract 口径）
    "error",
    "errorString",
)


class TorrentLookupService:
    """通用种子定位服务（协议无关，qB / TR 双端统一入口）。

    构造注入 ``store``（``app.state.store``）或经 ``from_context`` 从
    RuntimeContext 提取（HTTP 端点 / MCP 侧共用，见 runtime_context 模块头注释）。
    """

    def __init__(self, store: Any = None) -> None:
        self.store = store

    @classmethod
    def from_context(cls, context: RuntimeContext) -> "TorrentLookupService":
        """从 RuntimeContext 构造（跨协议共享依赖注入模式）。"""
        return cls(store=context.store)

    async def get_by_hash(
        self, downloader_id: str, info_hash: str, *, timeout: Optional[float] = None
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """按单个 info_hash 精确定位种子并获取实时信息。

        Args:
            downloader_id: 下载器标识（store 快照中的 downloader_id）。
            info_hash: 种子 info_hash（40/64 位 hex；大小写不敏感，内部归一小写）。
            timeout: 单次远程调用预算秒数；None 取全局默认。

        Returns:
            (VO, err) 二元组：
            - (vo, None)：命中，vo 为统一口径 14 字段字典；
            - (None, None)：下载器正常但种子不存在；
            - (None, err)：下载器不可用 / hash 非法 / 远程调用失败。
        """
        found, err = await self.get_by_hashes(downloader_id, [info_hash], timeout=timeout)
        if err is not None:
            return None, err
        if not found:
            return None, None
        return next(iter(found.values())), None

    async def get_by_hashes(
        self, downloader_id: str, info_hashes: Sequence[str], *, timeout: Optional[float] = None
    ) -> Tuple[Dict[str, Dict[str, Any]], Optional[str]]:
        """按 info_hash 批量定位种子（分块合并单请求，毫秒级服务端索引）。

        Args:
            downloader_id: 下载器标识。
            info_hashes: 种子 hash 列表（去重保序；任一非法即整体快速失败不发请求）。
            timeout: 单次远程调用预算秒数（逐块计）。

        Returns:
            (mapping, err) 二元组：
            - mapping: {hash(小写): VO}；请求过但不在 mapping 中的 hash 即不存在；
            - err: None=全部块成功；非空=存在失败块（mapping 为已成功的部分数据，
              语义上部分成功仍可用，调用方按需取舍）。
        """
        try:
            normalized = self._normalize_hashes(info_hashes)
        except ValueError as exc:
            return {}, f"hash 校验失败: {exc}"

        if not normalized:
            return {}, None

        resolved, err = await self._resolve_client(downloader_id)
        if err is not None or resolved is None:
            return {}, err if err is not None else "下载器解析失败"
        client, downloader_type = resolved

        chunk_size = _QB_HASH_CHUNK if downloader_type == DownloaderTypeEnum.QBITTORRENT else _TR_HASH_CHUNK
        results: Dict[str, Dict[str, Any]] = {}
        first_error: Optional[str] = None

        for i in range(0, len(normalized), chunk_size):
            chunk = normalized[i : i + chunk_size]
            try:
                if downloader_type == DownloaderTypeEnum.QBITTORRENT:
                    torrents = await call_downloader_api(
                        downloader_id,
                        DownloadLane.INTERACTIVE,
                        client.torrents_info,
                        kwargs={"torrent_hashes": chunk},
                        timeout=timeout,
                        operation="torrent_lookup_qb",
                    )
                    to_dict = self._qb_to_vo
                else:
                    torrents = await call_downloader_api(
                        downloader_id,
                        DownloadLane.INTERACTIVE,
                        client.get_torrents,
                        kwargs={"ids": chunk, "arguments": list(_TR_FIELDS)},
                        timeout=timeout,
                        operation="torrent_lookup_tr",
                    )
                    to_dict = self._tr_to_vo
            except Exception as exc:  # noqa: BLE001 - 远程异常归一为 err，保留已成功块
                logger.warning("种子定位远程调用失败 downloader_id=%s 块=%d: %s", downloader_id, i // chunk_size, exc)
                if first_error is None:
                    first_error = f"下载器查询失败: {exc}"
                break

            for torrent in torrents or []:
                vo = to_dict(torrent)
                if vo is not None:
                    results[vo["hash"]] = vo

        return results, first_error

    async def _resolve_client(self, downloader_id: str) -> Tuple[Optional[Tuple[Any, int]], Optional[str]]:
        """从 store 快照解析可用客户端（downloader-connection 强制约束）。

        Returns:
            ((client, downloader_type), None) 或 (None, err)。
        """
        if self.store is None:
            return None, "下载器缓存未初始化"
        try:
            snapshot = await self.store.get_snapshot()
        except Exception as exc:  # noqa: BLE001 - 缓存实现异常归一为可读错误
            return None, f"读取下载器缓存失败: {exc}"

        downloader = next(
            (item for item in snapshot if str(getattr(item, "downloader_id", "")) == str(downloader_id)),
            None,
        )
        if downloader is None:
            return None, f"下载器不在缓存中: {downloader_id}"
        if int(getattr(downloader, "fail_time", 0) or 0) > 0:
            return None, f"下载器当前不可用: {downloader_id}"
        client = getattr(downloader, "client", None)
        if client is None:
            return None, f"下载器缓存中没有可用客户端: {downloader_id}"

        # normalize 返回 int（None 兼容归 0=qB，见 DownloaderTypeEnum.normalize）
        downloader_type = DownloaderTypeEnum.normalize(getattr(downloader, "downloader_type", None))
        if downloader_type not in (DownloaderTypeEnum.QBITTORRENT.value, DownloaderTypeEnum.TRANSMISSION.value):
            return None, f"该下载器类型暂不支持种子定位: {DownloaderTypeEnum.from_value(downloader_type).to_name()}"
        return (client, downloader_type), None

    @staticmethod
    def _normalize_hashes(info_hashes: Sequence[str]) -> List[str]:
        """hash 归一化：strip + 小写 + 去重保序 + 格式校验。

        Raises:
            ValueError: 任一 hash 非法（长度非 40/64 或含非 hex 字符）。
        """
        seen: set = set()
        ordered: List[str] = []
        for raw in info_hashes:
            value = str(raw or "").strip().lower()
            if not value or len(value) not in _VALID_HASH_LENGTHS or not _HASH_HEX_CHARS.issuperset(value):
                raise ValueError(f"无效的种子hash: {raw!r}")
            if value not in seen:
                seen.add(value)
                ordered.append(value)
        return ordered

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        """数值字段容错提取：异常对象/不可转值（qB API 异常态字段）返回默认值。

        对齐被替换的 create_*_torrent_record 对 str/数值包裹字段的防御语义
        （prod-hotfix-2026-07-19：qB 异常态可能返回 ValueError 实例字段）。
        """
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _qb_to_vo(torrent: Any) -> Optional[Dict[str, Any]]:
        """qBittorrent TorrentDictionary → 统一 VO（单条转换异常跳过不炸批量）。"""
        try:
            raw_state = str(getattr(torrent, "state", "") or "")
            completion_raw = TorrentLookupService._safe_int(getattr(torrent, "completion_on", None))
            added_raw = TorrentLookupService._safe_int(getattr(torrent, "added_on", None))
            return {
                "hash": str(getattr(torrent, "hash", "") or "").strip().lower(),
                "name": str(getattr(torrent, "name", "") or ""),
                "size": TorrentLookupService._safe_int(getattr(torrent, "size", None)),
                "state": TorrentStatusMapper.convert_qbittorrent_status(raw_state),
                "raw_state": raw_state,
                "error_reason": None,
                "progress": round(TorrentLookupService._safe_float(getattr(torrent, "progress", None)) * 100.0, 2),
                "ratio": TorrentLookupService._safe_float(getattr(torrent, "ratio", None)),
                "downloaded": TorrentLookupService._safe_int(getattr(torrent, "downloaded", None)),
                "uploaded": TorrentLookupService._safe_int(getattr(torrent, "uploaded", None)),
                "download_path": str(getattr(torrent, "save_path", "") or ""),
                # qB 未完成时 completion_on 为 libtorrent sentinel -8640000000000，统一归 0
                "completion_date": completion_raw if completion_raw > 0 else 0,
                "addition_date": added_raw,
                "category": str(getattr(torrent, "category", "") or ""),
                "tags": str(getattr(torrent, "tags", "") or ""),
                # qB 种子文件路径不在 torrents/info 响应中，消费方按需推导
                # （如添加后落库链路的 BT_backup 约定路径）
                "torrent_file": None,
            }
        except Exception:  # noqa: BLE001 - 脏数据单条跳过，批量语义不受影响
            logger.warning("qB 种子 VO 转换失败，跳过该条: %s", TorrentLookupService._safe_hash_hint(torrent, "hash"))
            return None

    @staticmethod
    def _tr_to_vo(torrent: Any) -> Optional[Dict[str, Any]]:
        """transmission_rpc Torrent → 统一 VO（单条转换异常跳过不炸批量）。

        注意 status 是 ``Status(str, Enum)``：``str()`` 会得到 "Status.seeding"，
        必须经 ``.lower()``（str 子类方法）取值，与删除适配器既有写法一致。
        """
        try:
            # pylint: disable-next=unnecessary-dunder-call
            raw_status = (getattr(torrent, "status", "") or "").lower()
            tr_error = getattr(torrent, "error", None)
            # 种子级错误联合判定（error>=2 归 "error"）；非 int（缺失/MagicMock）
            # 由 resolve 内部守卫按 0 处理回退查表
            state = TorrentStatusMapper.resolve_transmission_status(raw_status, tr_error)
            error_reason: Optional[str] = None
            if isinstance(tr_error, int) and tr_error >= TorrentStatusMapper.TR_ERROR_THRESHOLD:
                raw_reason = getattr(torrent, "error_string", None)
                if isinstance(raw_reason, str) and raw_reason.strip():
                    error_reason = raw_reason.strip()
            labels = list(getattr(torrent, "labels", None) or [])
            added_date = getattr(torrent, "added_date", None)
            done_date = getattr(torrent, "done_date", None)
            return {
                "hash": str(getattr(torrent, "hash_string", "") or "").strip().lower(),
                "name": str(getattr(torrent, "name", "") or ""),
                "size": TorrentLookupService._safe_int(getattr(torrent, "total_size", None)),
                "state": state,
                "raw_state": raw_status,
                "error_reason": error_reason,
                "progress": round(TorrentLookupService._safe_float(getattr(torrent, "progress", None)), 2),
                "ratio": TorrentLookupService._safe_float(getattr(torrent, "ratio", None)),
                "downloaded": TorrentLookupService._safe_int(getattr(torrent, "downloaded_ever", None)),
                "uploaded": TorrentLookupService._safe_int(getattr(torrent, "uploaded_ever", None)),
                "download_path": str(getattr(torrent, "download_dir", "") or ""),
                # TR done_date 未完成为 None，统一 epoch 秒 int（0=未知）
                "completion_date": int(done_date.timestamp()) if done_date else 0,
                "addition_date": int(added_date.timestamp()) if added_date else 0,
                "category": " ".join(labels),
                "tags": ",".join(labels),
                "torrent_file": str(getattr(torrent, "torrent_file", "") or ""),
            }
        except Exception:  # noqa: BLE001 - 脏数据单条跳过，批量语义不受影响
            logger.warning(
                "TR 种子 VO 转换失败，跳过该条: %s", TorrentLookupService._safe_hash_hint(torrent, "hash_string")
            )
            return None

    @staticmethod
    def _safe_hash_hint(torrent: Any, attr: str) -> str:
        """日志用 hash 提示：提取失败（属性本身抛异常）时回退类型名，避免日志再抛。"""
        try:
            return str(getattr(torrent, attr, "?"))
        except Exception:  # noqa: BLE001 - 仅日志提示，不可因日志参数求值失败再次抛出
            return type(torrent).__name__
