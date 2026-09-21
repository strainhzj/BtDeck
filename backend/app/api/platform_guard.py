"""FastAPI 入口的主机能力门禁。

能力判定仍由 ``app.core.platform_capabilities`` 维护；本模块只负责把认证依赖
与能力检查组合起来，供整组路由复用。服务层仍需保留同一能力的二次检查。
"""

from typing import Callable

from fastapi import Depends

from app.auth.dependencies import require_authenticated_user
from app.core.platform_capabilities import require_capability


def capability_dependency(capability: str, operation: str | None = None) -> Callable:
    """构造一个先认证、再检查平台能力的 FastAPI 依赖。"""

    async def _guard(_user=Depends(require_authenticated_user)) -> None:
        require_capability(capability, operation)

    return _guard
