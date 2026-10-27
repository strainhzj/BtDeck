# -*- coding: utf-8 -*-
"""
qB 原生 RSS 代理服务（feature rss-subscription-phase2-2026-09-24）

职责：把 qBittorrent 自身 RSS（订阅源/文件夹/下载规则/偏好/文章）透传给
BtDeck 前端。qB 为事实源，BtDeck 不落库（代理只做投影与轻校验）。

调用链路：app.state.store 缓存客户端（CL-16）+ call_downloader_api
（INTERACTIVE lane），与 Phase 1 推送链路同口径。

已知 qB API 限制：
- rss_items 对「空 feed」与「空 folder」都返回 {}，无法区分——本代理统一
  按 folder 投影（空 feed 无文章可浏览，功能无损；文章端点按 path 直取
  仍返回空列表）；
- rss_items 不返回 feed 的 URL（改址走 rss_set_feed_url 透传，不回显）。

安全口径：
- 偏好写入白名单硬校验：仅 rss_processing_enabled / rss_auto_downloading_enabled /
  rss_refresh_interval / rss_max_articles_per_feed 四键，其余键一律拒绝
  （RSS_QB_PREF_KEY_REJECTED），绝不透传任意偏好；
- 仅 downloader_type==0（qB）可用；代理不校验 RSS 模式（模式只管 BtDeck
  引擎侧行为，代理随时可调）。
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from app.services.downloader_api_runtime import DownloadLane, call_downloader_api
from app.services.rss_feed_service import RssServiceResult

logger = logging.getLogger(__name__)

_DOWNLOADER_CALL_TIMEOUT = 30.0
_ITEMS_CALL_TIMEOUT = 45.0

# qB RSS 偏好白名单（request 投影键 → qB 偏好键）
_QB_RSS_PREF_WHITELIST: Tuple[Tuple[str, str], ...] = (
    ("rssProcessingEnabled", "rss_processing_enabled"),
    ("rssAutoDownloadingEnabled", "rss_auto_downloading_enabled"),
    ("rssRefreshInterval", "rss_refresh_interval"),
    ("rssMaxArticlesPerFeed", "rss_max_articles_per_feed"),
)

# 文章节点判定字段（qB RSS article dict 的稳定子集）
_ARTICLE_FIELDS = frozenset({"title", "isRead", "torrentURL", "link", "magnetURI", "published"})


def _is_feed_node(value: Any) -> bool:
    """判定 rss_items 子树是否为 feed（其值为 articleId→article 映射）。"""
    if not isinstance(value, dict) or not value:
        return False
    return any(isinstance(article, dict) and _ARTICLE_FIELDS & set(article.keys()) for article in value.values())


def _project_article(article_id: Any, article: Dict[str, Any]) -> Dict[str, Any]:
    """qB article → 前端投影（链接取 torrentURL > link > magnetURI）。"""
    link = article.get("torrentURL") or article.get("link") or article.get("magnetURI") or ""
    return {
        "articleId": str(article_id),
        "title": article.get("title") or "",
        "link": link,
        "published": article.get("published"),
        "isRead": bool(article.get("isRead", False)),
    }


class RssQbProxyService:
    """qB 原生 RSS 代理领域服务（协议无关，HTTP 端点为薄壳）。"""

    def __init__(self, db: Any = None, store: Any = None):
        """
        Args:
            db: 数据库会话（保留参数对齐服务惯例；代理不落库）
            store: 下载器缓存（app.state.store；必填才能调用下载器）
        """
        self.db = db
        self.store = store

    # ========== 客户端解析 ==========

    def _resolve_from_snapshot(
        self, snapshot: List[Any], downloader_id: str
    ) -> Tuple[Optional[Any], Optional[RssServiceResult]]:
        vo = next((d for d in snapshot if d.downloader_id == downloader_id), None)
        if vo is None:
            return None, RssServiceResult(
                ok=False, code="404", msg="目标下载器不存在或未连接", reason_code="RSS_DOWNLOADER_NOT_FOUND"
            )
        if getattr(vo, "fail_time", 0) > 0:
            return None, RssServiceResult(
                ok=False, code="503", msg="目标下载器当前不可用", reason_code="RSS_DOWNLOADER_OFFLINE"
            )
        if getattr(vo, "downloader_type", None) != 0:
            return None, RssServiceResult(
                ok=False,
                code="422",
                msg="仅 qBittorrent 下载器支持原生 RSS 管理",
                reason_code="RSS_QB_TYPE_UNSUPPORTED",
            )
        client = getattr(vo, "client", None)
        if client is None:
            return None, RssServiceResult(
                ok=False, code="500", msg="目标下载器客户端连接不存在", reason_code="RSS_DOWNLOADER_CONNECTION_MISSING"
            )
        return client, None

    async def _call(
        self,
        downloader_id: str,
        func: Any,
        kwargs: Dict[str, Any],
        operation: str,
        timeout: float = _DOWNLOADER_CALL_TIMEOUT,
    ) -> Any:
        """INTERACTIVE lane 透传调用（异常归一由端点层捕获映射）。"""
        return await call_downloader_api(
            downloader_id,
            DownloadLane.INTERACTIVE,
            func,
            kwargs=kwargs,
            timeout=timeout,
            operation=operation,
        )

    async def _with_client(
        self,
        downloader_id: str,
        operation: str,
        func_name: str,
        kwargs: Dict[str, Any],
        timeout: float = _DOWNLOADER_CALL_TIMEOUT,
    ) -> RssServiceResult:
        """解析客户端 + 透传调用 + 异常归一的通用包装。"""
        snapshot = await self.store.get_snapshot() if self.store is not None else []
        client, error = self._resolve_from_snapshot(snapshot, downloader_id)
        if error is not None:
            return error
        try:
            result = await self._call(downloader_id, getattr(client, func_name), kwargs, operation, timeout)
        except Exception:
            logger.exception("qB 原生 RSS 代理调用失败 [downloader_id=%s operation=%s]", downloader_id, operation)
            return RssServiceResult(
                ok=False, code="502", msg="qBittorrent RSS 操作失败，请稍后重试", reason_code="RSS_QB_PROXY_FAILED"
            )
        return RssServiceResult(data={"raw": result})

    # ========== 源/文件夹 ==========

    async def list_feeds(self, downloader_id: str) -> RssServiceResult:
        """列出 qB RSS 源树（with_data 以区分 feed/folder 并附未读数）。"""
        result = await self._with_client(
            downloader_id, "rss_qb_items", "rss_items", {"include_feed_data": True}, timeout=_ITEMS_CALL_TIMEOUT
        )
        if not result.ok:
            return result
        items = result.data.get("raw") or {}
        tree: List[Dict[str, Any]] = []
        _walk_items(items, "", tree)
        return RssServiceResult(data={"list": tree})

    async def add_feed(self, downloader_id: str, path: str, url: str) -> RssServiceResult:
        path = (path or "").strip()
        url = (url or "").strip()
        if not path or len(path) > 500:
            return RssServiceResult(
                ok=False, code="400", msg="订阅源路径不能为空且不超过500字符", reason_code="RSS_QB_FEED_PATH_INVALID"
            )
        if not url.startswith(("http://", "https://")) or len(url) > 1000:
            return RssServiceResult(
                ok=False,
                code="400",
                msg="订阅源地址必须是合法的 http/https 链接",
                reason_code="RSS_QB_FEED_URL_INVALID",
            )
        result = await self._with_client(
            downloader_id, "rss_qb_add_feed", "rss_add_feed", {"url": url, "item_path": path}
        )
        return result

    async def add_folder(self, downloader_id: str, path: str) -> RssServiceResult:
        path = (path or "").strip()
        if not path or len(path) > 500:
            return RssServiceResult(
                ok=False, code="400", msg="文件夹路径不能为空且不超过500字符", reason_code="RSS_QB_FEED_PATH_INVALID"
            )
        return await self._with_client(downloader_id, "rss_qb_add_folder", "rss_add_folder", {"folder_path": path})

    async def set_feed_url(self, downloader_id: str, path: str, url: str) -> RssServiceResult:
        path = (path or "").strip()
        url = (url or "").strip()
        if not path:
            return RssServiceResult(
                ok=False, code="400", msg="订阅源路径不能为空", reason_code="RSS_QB_FEED_PATH_INVALID"
            )
        if not url.startswith(("http://", "https://")) or len(url) > 1000:
            return RssServiceResult(
                ok=False,
                code="400",
                msg="订阅源地址必须是合法的 http/https 链接",
                reason_code="RSS_QB_FEED_URL_INVALID",
            )
        return await self._with_client(
            downloader_id, "rss_qb_set_feed_url", "rss_set_feed_url", {"url": url, "item_path": path}
        )

    async def remove_item(self, downloader_id: str, path: str) -> RssServiceResult:
        path = (path or "").strip()
        if not path:
            return RssServiceResult(
                ok=False, code="400", msg="项目路径不能为空", reason_code="RSS_QB_FEED_PATH_INVALID"
            )
        return await self._with_client(downloader_id, "rss_qb_remove_item", "rss_remove_item", {"origin_path": path})

    async def move_item(self, downloader_id: str, origin_path: str, dest_path: str) -> RssServiceResult:
        origin_path = (origin_path or "").strip()
        dest_path = (dest_path or "").strip()
        if not origin_path or not dest_path:
            return RssServiceResult(
                ok=False, code="400", msg="移动源/目标路径不能为空", reason_code="RSS_QB_FEED_PATH_INVALID"
            )
        return await self._with_client(
            downloader_id,
            "rss_qb_move_item",
            "rss_move_item",
            {"origin_path": origin_path, "dest_path": dest_path},
        )

    async def refresh_item(self, downloader_id: str, path: Optional[str]) -> RssServiceResult:
        """刷新 qB RSS 项（path 为空 = 刷新全部）。"""
        return await self._with_client(
            downloader_id, "rss_qb_refresh_item", "rss_refresh_item", {"item_path": (path or "").strip() or None}
        )

    async def mark_as_read(self, downloader_id: str, path: str, article_id: Optional[str]) -> RssServiceResult:
        path = (path or "").strip()
        if not path:
            return RssServiceResult(
                ok=False, code="400", msg="项目路径不能为空", reason_code="RSS_QB_FEED_PATH_INVALID"
            )
        return await self._with_client(
            downloader_id,
            "rss_qb_mark_as_read",
            "rss_mark_as_read",
            {"item_path": path, "article_id": article_id},
        )

    # ========== 文章 ==========

    async def list_articles(self, downloader_id: str, path: str, only_unread: bool = False) -> RssServiceResult:
        """列出 qB 某 feed 的文章（with_data 直取该路径子树）。"""
        path = (path or "").strip()
        if not path:
            return RssServiceResult(
                ok=False, code="400", msg="订阅源路径不能为空", reason_code="RSS_QB_FEED_PATH_INVALID"
            )
        result = await self._with_client(
            downloader_id, "rss_qb_items", "rss_items", {"include_feed_data": True}, timeout=_ITEMS_CALL_TIMEOUT
        )
        if not result.ok:
            return result
        items = result.data.get("raw") or {}
        node: Any = items
        for segment in path.split("\\"):
            if not isinstance(node, dict) or segment not in node:
                return RssServiceResult(
                    ok=False, code="404", msg="订阅源路径不存在", reason_code="RSS_QB_FEED_NOT_FOUND"
                )
            node = node[segment]
        if not _is_feed_node(node):
            # 空 feed（qB 返回 {} 无法区分 folder）按空文章列表处理
            return RssServiceResult(data={"list": [], "total": 0, "unreadCount": 0})
        articles = [
            _project_article(article_id, article) for article_id, article in node.items() if isinstance(article, dict)
        ]
        if only_unread:
            articles = [a for a in articles if not a["isRead"]]
        articles.sort(key=lambda a: a.get("published") or "", reverse=True)
        unread = sum(1 for a in articles if not a["isRead"])
        return RssServiceResult(data={"list": articles, "total": len(articles), "unreadCount": unread})

    # ========== 规则 ==========

    @staticmethod
    def _validate_rule_def(rule_def: Dict[str, Any]) -> Optional[str]:
        """qB 规则透传轻校验（返回错误 msg 或 None）。"""
        if not isinstance(rule_def, dict):
            return "规则定义必须是对象"
        if "enabled" in rule_def and not isinstance(rule_def["enabled"], bool):
            return "enabled 必须是布尔值"
        if "addPaused" in rule_def and not isinstance(rule_def["addPaused"], bool):
            return "addPaused 必须是布尔值"
        if "affectedFeeds" in rule_def and not isinstance(rule_def["affectedFeeds"], list):
            return "affectedFeeds 必须是数组"
        for field in ("mustContain", "mustNotContain", "savePath", "assignedCategory"):
            if field in rule_def and rule_def[field] is not None and not isinstance(rule_def[field], str):
                return f"{field} 必须是字符串"
        return None

    async def list_rules(self, downloader_id: str) -> RssServiceResult:
        result = await self._with_client(downloader_id, "rss_qb_rules", "rss_rules", {})
        if not result.ok:
            return result
        rules = result.data.get("raw") or {}
        items = []
        for name, rule_def in rules.items():
            item = dict(rule_def) if isinstance(rule_def, dict) else {}
            item["name"] = name
            items.append(item)
        items.sort(key=lambda r: r.get("name") or "")
        return RssServiceResult(data={"list": items, "total": len(items)})

    async def set_rule(self, downloader_id: str, name: str, rule_def: Dict[str, Any]) -> RssServiceResult:
        name = (name or "").strip()
        if not name or len(name) > 200:
            return RssServiceResult(
                ok=False, code="400", msg="规则名称不能为空且不超过200字符", reason_code="RSS_QB_RULE_NAME_INVALID"
            )
        error = self._validate_rule_def(rule_def)
        if error:
            return RssServiceResult(ok=False, code="400", msg=error, reason_code="RSS_QB_RULE_DEF_INVALID")
        return await self._with_client(
            downloader_id, "rss_qb_set_rule", "rss_set_rule", {"rule_name": name, "rule_def": rule_def}
        )

    async def rename_rule(self, downloader_id: str, name: str, new_name: str) -> RssServiceResult:
        name = (name or "").strip()
        new_name = (new_name or "").strip()
        if not name or not new_name or len(new_name) > 200:
            return RssServiceResult(
                ok=False, code="400", msg="规则名称不能为空且不超过200字符", reason_code="RSS_QB_RULE_NAME_INVALID"
            )
        return await self._with_client(
            downloader_id,
            "rss_qb_rename_rule",
            "rss_rename_rule",
            {"orig_rule_name": name, "new_rule_name": new_name},
        )

    async def remove_rule(self, downloader_id: str, name: str) -> RssServiceResult:
        name = (name or "").strip()
        if not name:
            return RssServiceResult(
                ok=False, code="400", msg="规则名称不能为空", reason_code="RSS_QB_RULE_NAME_INVALID"
            )
        return await self._with_client(downloader_id, "rss_qb_remove_rule", "rss_remove_rule", {"rule_name": name})

    async def matching_articles(self, downloader_id: str, name: str) -> RssServiceResult:
        """规则命中文章预览（返回 feed → articles 投影）。"""
        name = (name or "").strip()
        if not name:
            return RssServiceResult(
                ok=False, code="400", msg="规则名称不能为空", reason_code="RSS_QB_RULE_NAME_INVALID"
            )
        result = await self._with_client(
            downloader_id, "rss_qb_matching_articles", "rss_matching_articles", {"rule_name": name}
        )
        if not result.ok:
            return result
        raw = result.data.get("raw") or {}
        feeds = []
        for feed_path, articles in raw.items():
            projected = [
                _project_article(article_id, article)
                for article_id, article in (articles or {}).items()
                if isinstance(article, dict)
            ]
            projected.sort(key=lambda a: a.get("published") or "", reverse=True)
            feeds.append({"feedPath": feed_path, "articles": projected})
        feeds.sort(key=lambda f: f["feedPath"])
        return RssServiceResult(data={"feeds": feeds})

    # ========== 偏好（白名单） ==========

    async def get_preferences(self, downloader_id: str) -> RssServiceResult:
        result = await self._with_client(
            downloader_id, "rss_qb_preferences", "app_preferences", {}, timeout=_ITEMS_CALL_TIMEOUT
        )
        if not result.ok:
            return result
        prefs = result.data.get("raw") or {}
        projected = {proj_key: prefs.get(qb_key) for proj_key, qb_key in _QB_RSS_PREF_WHITELIST}
        return RssServiceResult(data={"preferences": projected})

    async def update_preferences(
        self,
        downloader_id: str,
        updates: Dict[str, Any],
    ) -> RssServiceResult:
        """更新 qB RSS 偏好（仅白名单四键；数值边界校验）。

        updates 为「已按投影键过滤」的待更新字段（None 表示未提供）。
        """
        payload: Dict[str, Any] = {}
        refresh_interval = updates.get("rssRefreshInterval")
        if refresh_interval is not None:
            if (
                not isinstance(refresh_interval, int)
                or isinstance(refresh_interval, bool)
                or not (1 <= refresh_interval <= 9999)
            ):
                return RssServiceResult(
                    ok=False,
                    code="400",
                    msg="RSS 刷新间隔必须是 1-9999 的整数（分钟）",
                    reason_code="RSS_QB_PREF_VALUE_INVALID",
                )
            payload["rss_refresh_interval"] = refresh_interval
        max_articles = updates.get("rssMaxArticlesPerFeed")
        if max_articles is not None:
            if not isinstance(max_articles, int) or isinstance(max_articles, bool) or not (1 <= max_articles <= 5000):
                return RssServiceResult(
                    ok=False,
                    code="400",
                    msg="每源文章上限必须是 1-5000 的整数",
                    reason_code="RSS_QB_PREF_VALUE_INVALID",
                )
            payload["rss_max_articles_per_feed"] = max_articles
        for proj_key, qb_key in (
            ("rssProcessingEnabled", "rss_processing_enabled"),
            ("rssAutoDownloadingEnabled", "rss_auto_downloading_enabled"),
        ):
            value = updates.get(proj_key)
            if value is not None:
                if not isinstance(value, bool):
                    return RssServiceResult(
                        ok=False, code="400", msg=f"{proj_key} 必须是布尔值", reason_code="RSS_QB_PREF_VALUE_INVALID"
                    )
                payload[qb_key] = value
        if not payload:
            return RssServiceResult(
                ok=False, code="400", msg="没有可更新的偏好字段", reason_code="RSS_QB_PREF_KEY_REJECTED"
            )
        result = await self._with_client(
            downloader_id, "rss_qb_set_preferences", "app_set_preferences", {"prefs": payload}
        )
        if not result.ok:
            return result
        # 回读投影（qB setPreferences 无返回；回读确认最终值）
        return await self.get_preferences(downloader_id)


def _walk_items(node: Dict[str, Any], path: str, out: List[Dict[str, Any]]) -> None:
    """递归投影 rss_items 树（feed 附文章数/未读数；空节点按 folder）。"""
    for name, value in node.items():
        child_path = f"{path}\\{name}" if path else name
        if _is_feed_node(value):
            articles = [a for a in value.values() if isinstance(a, dict)]
            out.append(
                {
                    "type": "feed",
                    "name": name,
                    "path": child_path,
                    "articleCount": len(articles),
                    "unreadCount": sum(1 for a in articles if not a.get("isRead")),
                }
            )
        else:
            children: List[Dict[str, Any]] = []
            if isinstance(value, dict) and value:
                _walk_items(value, child_path, children)
            out.append({"type": "folder", "name": name, "path": child_path, "children": children})
