"""MCP 运行时（feature mcp-service-capabilities-2026-08-28 W2）。

职责（计划 §4.1/§10.3-W2）：

- 持有父应用注入的运行时依赖：``app.state`` 引用（store/torrent_stats/start_time
  的**惰性只读探测**，与 ``RuntimeContext`` 同语义）、同步/异步双会话工厂
  （AdvancedSearchService 同步 Session、DashboardService 异步 AsyncSession）；
- 就绪/关闭状态机：``mark_ready``/``mark_closed`` 由父应用 lifespan 驱动；
  未就绪或关闭中对工具调用稳定拒绝 ``RUNTIME_NOT_READY``，绝不自建下载器
  连接或第二个调度器（G0/G9）；
- 配置快照供给：每次 tools/list 与 tools/call 经 ``McpSettingsService``
  读取一份 fail-closed 快照——PUT 提交后下一次调用立即看到新 revision，
  无需重启（G2 热更新）；读取异常同样回落默认全关（G1）。

本模块不 import MCP SDK、不 import app.main/app.factory/app.api（G0 静态门禁
扫描对象）；``state`` 以 ``Any`` 引用持有，禁止在此反查全局应用实例。
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.runtime_context import TORRENT_STATS_ABSENT, RuntimeContext
from app.mcp.contracts import DEFAULT_CAPABILITY_STATES
from app.mcp.errors import McpErrorCode, McpToolError
from app.services.mcp_settings_service import McpRuntimeSettings

logger = logging.getLogger(__name__)

# 会话工厂类型：0 参调用返回一个新会话（SessionLocal / AsyncSessionLocal 形态）
SyncSessionFactory = Callable[[], Session]
AsyncSessionFactory = Callable[[], AsyncSession]
# 配置快照供给器：0 参调用返回一份原子快照
SettingsProvider = Callable[[], McpRuntimeSettings]


def _default_settings_provider() -> McpRuntimeSettings:
    """生产默认供给器：短会话读 configs.mcp.runtime.v1，任何异常回落默认全关。"""
    from app.database import SessionLocal
    from app.services.mcp_settings_service import McpSettingsService

    try:
        db = SessionLocal()
        try:
            return McpSettingsService(db).get_settings()
        finally:
            db.close()
    except Exception:
        logger.exception("MCP 配置快照读取失败，fail-closed 回落默认全关")
        return McpRuntimeSettings(
            enabled=False,
            capabilities=dict(DEFAULT_CAPABILITY_STATES),
            revision=0,
            updated_at=None,
            updated_by=None,
        )


@dataclass
class McpRuntime:
    """同进程 MCP 服务的运行时依赖束（由父应用构造并注入 server 层）。"""

    # 父应用 state 引用（只读探测 store/torrent_stats/start_time；G0：不持 app 实例）
    state: Any = None
    session_factory: Optional[SyncSessionFactory] = None
    async_session_factory: Optional[AsyncSessionFactory] = None
    settings_provider: SettingsProvider = field(default=_default_settings_provider)

    _ready: bool = field(default=False, compare=False)
    _closed: bool = field(default=False, compare=False)

    @classmethod
    def from_state(
        cls,
        state: Any,
        session_factory: Optional[SyncSessionFactory] = None,
        async_session_factory: Optional[AsyncSessionFactory] = None,
        settings_provider: Optional[SettingsProvider] = None,
    ) -> "McpRuntime":
        """从父应用 state 构造（会话工厂缺省取 app.database 的全局工厂）。"""
        if session_factory is None or async_session_factory is None:
            from app.database import AsyncSessionLocal, SessionLocal

            session_factory = session_factory or SessionLocal
            async_session_factory = async_session_factory or AsyncSessionLocal
        return cls(
            state=state,
            session_factory=session_factory,
            async_session_factory=async_session_factory,
            settings_provider=settings_provider or _default_settings_provider,
        )

    # ------------------------------------------------------------------ 生命周期

    def mark_ready(self) -> None:
        """父应用 lifespan 完成启动（迁移/初始数据/调度器启动）后调用。"""
        self._ready = True
        self._closed = False

    def mark_closed(self) -> None:
        """父应用 lifespan 进入关闭段调用；此后一切工具调用稳定拒绝。"""
        self._closed = True

    @property
    def is_ready(self) -> bool:
        return self._ready and not self._closed

    @property
    def is_closed(self) -> bool:
        return self._closed

    def require_ready(self) -> None:
        """G9：未就绪/关闭中稳定拒绝（固定文案，不区分内部原因）。"""
        if not self.is_ready:
            raise McpToolError(McpErrorCode.RUNTIME_NOT_READY)

    def require_store(self) -> Any:
        """需要下载器缓存的工具入口：store 未初始化同样 RUNTIME_NOT_READY。

        返回 store 引用（调用方继续只用缓存连接，禁自建客户端——G0）。
        """
        self.require_ready()
        store = getattr(self.state, "store", None) if self.state is not None else None
        if store is None:
            raise McpToolError(McpErrorCode.RUNTIME_NOT_READY)
        return store

    # ------------------------------------------------------------------ 配置快照

    def settings_snapshot(self) -> McpRuntimeSettings:
        """同步读取一份 fail-closed 配置快照（供给器内部兜底，不向上抛异常）。"""
        try:
            return self.settings_provider()
        except Exception:
            logger.exception("MCP 配置供给器异常，fail-closed 回落默认全关")
            return McpRuntimeSettings(
                enabled=False,
                capabilities=dict(DEFAULT_CAPABILITY_STATES),
                revision=0,
                updated_at=None,
                updated_by=None,
            )

    async def settings_snapshot_async(self) -> McpRuntimeSettings:
        """异步侧入口：SQLite 读走工作线程，不占事件循环（WAL RCA 纪律）。"""
        return await asyncio.to_thread(self.settings_snapshot)

    # ------------------------------------------------------------------ 惰性探测

    @property
    def context(self) -> RuntimeContext:
        """按当前 state 惰性构造 RuntimeContext（W3 工具注入 DashboardService 等）。

        保留 ``torrent_stats`` 的三态语义（ABSENT 哨兵 ≠ None，见
        app/core/runtime_context.py 模块注释）。
        """
        state = self.state
        if state is None:
            return RuntimeContext()
        return RuntimeContext(
            store=getattr(state, "store", None),
            torrent_stats=getattr(state, "torrent_stats", TORRENT_STATS_ABSENT),
            start_time=getattr(state, "start_time", None),
        )

    def sync_session(self) -> Session:
        """打开一个同步会话（调用方负责 close）；工厂缺失即运行时未接线。"""
        if self.session_factory is None:
            raise McpToolError(McpErrorCode.RUNTIME_NOT_READY)
        return self.session_factory()

    def async_session(self) -> AsyncSession:
        """打开一个异步会话（调用方负责 close）。"""
        if self.async_session_factory is None:
            raise McpToolError(McpErrorCode.RUNTIME_NOT_READY)
        return self.async_session_factory()

    def settings_summary_for_log(self, snapshot: McpRuntimeSettings) -> Dict[str, Any]:
        """日志允许面（§4.5 tool_payload_in_logs）：revision/开关态，无参数无 payload。"""
        return {
            "enabled": snapshot.effective_enabled,
            "revision": snapshot.revision,
            "capabilities_on": sorted(code for code, on in snapshot.capabilities.items() if on),
        }
