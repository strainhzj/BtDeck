"""协议无关运行时上下文。

服务层不再接收 FastAPI ``app``/``Request`` 对象，改为注入本上下文持有的
运行时依赖（下载器缓存 store / 种子统计 / 启动时间）。HTTP 端点经
``RuntimeContext.from_app(request.app)`` 构造；未来 MCP 侧由父应用
运行时构造同一上下文（见 PLANS/mcp-service-capabilities.md §4.1/§10.3）。
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

# 三态哨兵：app.state.torrent_stats「属性不存在」与「属性存在但为 None」在原
# DashboardService 中行为不同（前者返回零值字典、后者原样返回 None，被
# test_dashboard_api 钉为 known behavior），RuntimeContext 必须保留该区分。
TORRENT_STATS_ABSENT = object()


@dataclass
class RuntimeContext:
    """跨协议共享的应用运行时依赖快照。

    仅保存引用：torrent_stats 是 app.state 上的同一 dict 引用，
    构造时读取属性、调用期取值，与原 ``self.app.state.*`` 语义一致。
    """

    store: Any = None
    torrent_stats: Any = TORRENT_STATS_ABSENT
    start_time: Optional[float] = None

    @classmethod
    def from_app(cls, app: Any) -> "RuntimeContext":
        """从 FastAPI 应用实例（或任意带 ``state`` 的对象）提取运行时依赖。

        属性缺失时 store/start_time 保持 None（使用方按原语义降级）；
        torrent_stats 保持 ABSENT 哨兵（见模块头注释的三态语义）。
        """
        state = getattr(app, "state", None)
        if state is None:
            return cls()
        return cls(
            store=getattr(state, "store", None),
            torrent_stats=getattr(state, "torrent_stats", TORRENT_STATS_ABSENT),
            start_time=getattr(state, "start_time", None),
        )
