"""MCP 工具处理器注册入口（feature mcp-service-capabilities W3）。

server.py 构造服务束时调用 ``register_all()``，把已实现工具挂入
``catalog.TOOL_HANDLERS``（幂等：重复调用不重复注册）。W3 分三批接入：

- W3-①（只读 + 唯一 DB 写）：torrent_advanced_search、
  advanced_search_template_create、dashboard_get；
- W3-②（写/高风险）：torrent_mark_pending_delete（等级 4 标签）、
  cron_task_trigger（内置任务白名单触发）；
- W3-③：torrent_add_file（TorrentAddService 共用边界收尾后）。
"""

import logging

from app.mcp.catalog import TOOL_HANDLERS

logger = logging.getLogger(__name__)


def register_all() -> None:
    """注册当前批次已实现的工具处理器（幂等）。"""
    from app.mcp.tools.cron import handle_cron_trigger
    from app.mcp.tools.dashboard import handle_dashboard_get
    from app.mcp.tools.search_templates import handle_template_create
    from app.mcp.tools.torrents import handle_advanced_search, handle_mark_pending_delete

    for tool_name, handler in (
        ("torrent_advanced_search", handle_advanced_search),
        ("advanced_search_template_create", handle_template_create),
        ("dashboard_get", handle_dashboard_get),
        ("torrent_mark_pending_delete", handle_mark_pending_delete),
        ("cron_task_trigger", handle_cron_trigger),
    ):
        if TOOL_HANDLERS.get(tool_name) is None:
            TOOL_HANDLERS.register(tool_name, handler)
    logger.info("MCP 工具处理器已注册: %s", TOOL_HANDLERS.registered_names())
