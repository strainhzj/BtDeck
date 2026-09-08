"""MCP 服务模块（feature mcp-service-capabilities-2026-08-28）。

W0 批次仅交付框架无关契约层（``contracts`` / ``errors``）；同进程挂载、
统一认证接入与脱敏运行时在 W2 落地，六项工具在 W3 接入。任何新增子模块
必须遵守计划 §3/§4：不调用 HTTP endpoint、不新建下载器客户端、不绕过
``app.state.store`` 与全局执行器。
"""
