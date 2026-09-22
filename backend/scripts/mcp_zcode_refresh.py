"""ZCode MCP 连接令牌刷新助手（feature mcp-service-capabilities-2026-08-28 配套工具）。

背景：BtDeck MCP 走主站统一认证（Bearer 访问令牌），令牌 TTL 60 分钟
（ACCESS_TOKEN_EXPIRE_MINUTES），静态写进 ZCode 配置的令牌会每小时过期。
本脚本登录换取新令牌并就地更新 ``~/.zcode/cli/config.json`` 的
``mcp.servers.<name>.headers.Authorization``，其余配置键原样保留。

前置条件：后端已运行（默认 http://127.0.0.1:5001），账号具备登录能力，
MCP 能力开关已在设置页开启（GET /api/v1/mcp/settings effectiveEnabled=true）。

用法：

  python mcp_zcode_refresh.py --username admin --password <pwd> \
      [--base http://127.0.0.1:5001] [--server-name btdeck] \
      [--config ~/.zcode/cli/config.json]

凭据也可经环境变量提供：BTDECK_MCP_USER / BTDECK_MCP_PASS（参数优先）。
令牌过期后重跑本脚本即可；新会话启动时 ZCode 自动按配置连接。
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Tuple


def login(base: str, username: str, password: str) -> str:
    req = urllib.request.Request(
        f"{base}/api/v1/auth/login",
        method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps({"username": username, "password": password}).encode(),
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    data = body.get("data") or []
    if body.get("code") != "200" or not data:
        raise SystemExit(f"登录失败: {body.get('msg')}")
    return data[0]["access_token"]


def token_expiry(token: str) -> datetime:
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload))
    return datetime.fromtimestamp(claims["exp"])


def update_config(config_path: Path, server_name: str, url: str, token: str, timeout_ms: int) -> None:
    config: Dict[str, Any] = {}
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
    servers = config.setdefault("mcp", {}).setdefault("servers", {})
    servers[server_name] = {
        "type": "http",
        "url": url,
        "headers": {"Authorization": f"Bearer {token}"},
        "timeoutMs": timeout_ms,
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="刷新 ZCode MCP 连接的 BtDeck 访问令牌")
    parser.add_argument("--base", default="http://127.0.0.1:5001", help="后端根地址")
    parser.add_argument("--username", default=os.environ.get("BTDECK_MCP_USER"))
    parser.add_argument("--password", default=os.environ.get("BTDECK_MCP_PASS"))
    parser.add_argument("--server-name", default="btdeck", help="ZCode 配置中的服务名")
    parser.add_argument("--config", default=str(Path.home() / ".zcode" / "cli" / "config.json"))
    parser.add_argument("--timeout-ms", type=int, default=60000)
    args = parser.parse_args()

    if not args.username or not args.password:
        parser.error("需要 --username/--password 或环境变量 BTDECK_MCP_USER/BTDECK_MCP_PASS")

    token = login(args.base, args.username, args.password)
    config_path = Path(args.config)
    update_config(config_path, args.server_name, f"{args.base}/mcp/", token, args.timeout_ms)
    print(f"已更新 {config_path} -> mcp.servers.{args.server_name}")
    print(f"端点: {args.base}/mcp/ | 令牌有效期至: {token_expiry(token):%Y-%m-%d %H:%M:%S}（TTL 60 分钟，过期重跑本脚本）")


if __name__ == "__main__":
    main()
