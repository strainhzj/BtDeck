"""MCP 服务密钥（API key）服务（feature mcp-service-capabilities-2026-08-28 W5）。

计划 §4.2-2/§4.4-2：为外部 agent 对接 MCP 服务提供长期有效的专用密钥，
与 Web 会话 JWT 并存（transport 按 ``btdmcp_`` 前缀路由，见 app/mcp/auth.py）。

存储（复用 ``configs`` 表第二个版本化 JSON 键 ``mcp.apikey.v1``，不新建表、
不走 Alembic——与 mcp.runtime.v1 / moviepilot.integration.v1 同模式）：

- ``keyHash``：SHA-256 十六进制摘要，**认证校验的唯一事实源**；
- ``keyEncrypted``：SM4 加密的明文副本，**仅控制面「查看」出口解密**
  （与下载器密码同存储模式；威胁模型已登记「app.db + secret_key 泄露 ⇒
  密钥可离线还原」，UI 明示该风险）；
- ``revision``/``createdAt``/``createdBy``/``updatedAt``/``updatedBy``：
  CAS 与归属追溯（rotate 后归属=操作者，旧密钥立即失效）。

fail-closed 语义（G1）：

- 行缺失/JSON 损坏/schemaVersion 未知/关键字段缺失 ⇒ 视图态 ``absent``，
  认证校验拒绝（哈希无从比对）；
- 解密失败或明文不符合 ``btdmcp_`` 格式（如 secret_key 轮换后存量密文
  集体失效，而 ``decrypt()`` 失败会原样返回密文）⇒ 视图态 ``unreadable``：
  **查看拒绝但认证不受影响**（哈希仍有效），引导用户 rotate 自愈；
- 任何异常不向上抛（除 CAS 冲突/载荷非法两类受控异常），由端点映射
  CommonResponse + data.reasonCode。

本服务只依赖同步 ``Session`` 与协议无关模块（contracts/encryption），
不 import FastAPI/Request——HTTP 控制面与 MCP transport 共用同一实例语义。
"""

import hmac
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.auth.models import Config
from app.mcp.contracts import (
    MCP_APIKEY_CONFIG_KEY,
    MCP_APIKEY_PREFIX,
    MCP_APIKEY_SCHEMA_VERSION,
    generate_mcp_api_key,
    hash_mcp_api_key,
    is_mcp_api_key_format,
)
from app.utils.encryption import decrypt_password, encrypt_password

logger = logging.getLogger(__name__)

MCP_APIKEY_DESCRIPTION = "MCP 服务密钥（API key）版本化配置（W5；SHA-256 哈希 + SM4 加密副本 + revision CAS）"

# 视图态（GET 出口与前端引导分流用）
STATUS_ABSENT = "absent"  # 从未生成（或行损坏至无从解析）
STATUS_ACTIVE = "active"  # 已生成且明文可查看
STATUS_UNREADABLE = "unreadable"  # 已生成但明文不可查看（secret_key 轮换/密文损坏）


class McpApiKeyStateError(ValueError):
    """密钥载荷非法（HTTP 侧映射 400 + reasonCode MCP_APIKEY_INVALID）。"""


class McpApiKeyRevisionConflict(RuntimeError):
    """expectedRevision 与库中 revision 不一致（CAS 冲突），HTTP 侧映射 409。"""

    def __init__(self, current_revision: int):
        super().__init__(f"密钥已被其他会话变更（当前 revision={current_revision}）")
        self.current_revision = current_revision


@dataclass(frozen=True)
class McpApiKeyState:
    """密钥元数据快照（不含明文；keyPrefix 供 UI 展示格式提示）。"""

    status: str = STATUS_ABSENT
    revision: int = 0
    created_at: Optional[str] = None
    created_by: Optional[str] = None
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None

    @property
    def exists(self) -> bool:
        """行存在性（active 与 unreadable 均已生成；absent 从未生成）。"""
        return self.status in (STATUS_ACTIVE, STATUS_UNREADABLE)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "exists": self.exists,
            "revision": self.revision,
            "createdAt": self.created_at,
            "createdBy": self.created_by,
            "updatedAt": self.updated_at,
            "updatedBy": self.updated_by,
            "keyPrefix": MCP_APIKEY_PREFIX,
        }


@dataclass(frozen=True)
class McpApiKeyReveal:
    """查看/刷新出口：元数据 + 明文密钥（全链路仅此一处返回明文）。"""

    key: str
    state: McpApiKeyState

    def to_payload(self) -> Dict[str, Any]:
        payload = self.state.to_payload()
        payload["key"] = self.key
        return payload


class McpApiKeyService:
    """mcp.apikey.v1 的读写、查看与认证校验（协议无关，同步 Session）。"""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ 读（控制面）

    def get_view(self) -> Dict[str, Any]:
        """GET /mcp/apikey 出口：active 带明文，absent/unreadable 不带（引导生成/刷新）。"""
        payload = self._load_valid_payload()
        if payload is None:
            return McpApiKeyState(status=STATUS_ABSENT).to_payload()
        state = self._to_state(payload)
        plaintext = self._decrypt_plaintext(payload)
        if plaintext is None:
            return McpApiKeyState(status=STATUS_UNREADABLE, revision=state.revision).to_payload()
        return McpApiKeyReveal(key=plaintext, state=state).to_payload()

    # ------------------------------------------------------------------ 写（控制面）

    def rotate(self, rotated_by: str, expected_revision: int) -> McpApiKeyReveal:
        """生成新密钥并原子替换（CAS：expectedRevision 必须等于当前 revision）。

        无密钥行时当前 revision 视为 0（expectedRevision=0 建行，与
        mcp.runtime.v1 的 CAS 语义一致）。加密失败（SM4 密钥缺失）时
        fail-closed 抛 McpApiKeyStateError——禁止明文落库。
        """
        if not isinstance(expected_revision, int) or isinstance(expected_revision, bool) or expected_revision < 0:
            raise McpApiKeyStateError("expectedRevision 必须为非负整数")
        if not rotated_by or not isinstance(rotated_by, str):
            raise McpApiKeyStateError("操作者不能为空")

        current = self._load_valid_payload()
        current_revision = self._stored_revision(current)
        if expected_revision != current_revision:
            raise McpApiKeyRevisionConflict(current_revision)

        key = generate_mcp_api_key()
        try:
            encrypted = encrypt_password(key)
        except Exception as exc:  # SM4 未初始化/加密异常：拒绝落库，不产出无效行
            logger.error("MCP 服务密钥加密失败，拒绝生成（fail-closed）: %s", exc)
            raise McpApiKeyStateError("服务密钥加密组件不可用，已拒绝生成") from exc

        now = datetime.now(timezone.utc).isoformat()
        new_revision = current_revision + 1
        # createdAt/createdBy 保留首次生成信息（rotate 只更新 updated* 与 revision）
        created_at = current.get("createdAt") if isinstance(current, dict) else None
        created_by = current.get("createdBy") if isinstance(current, dict) else None
        payload: Dict[str, Any] = {
            "schemaVersion": MCP_APIKEY_SCHEMA_VERSION,
            "keyHash": hash_mcp_api_key(key),
            "keyEncrypted": encrypted,
            "revision": new_revision,
            "createdAt": created_at if isinstance(created_at, str) else now,
            "createdBy": created_by if isinstance(created_by, str) else rotated_by,
            "updatedAt": now,
            "updatedBy": rotated_by,
        }
        row = self.db.query(Config).filter(Config.key == MCP_APIKEY_CONFIG_KEY).first()
        if row is None:
            self.db.add(
                Config(
                    key=MCP_APIKEY_CONFIG_KEY,
                    value=json.dumps(payload, ensure_ascii=False),
                    description=MCP_APIKEY_DESCRIPTION,
                )
            )
        else:
            row.value = json.dumps(payload, ensure_ascii=False)
            if not row.description:
                row.description = MCP_APIKEY_DESCRIPTION
        self.db.commit()
        return McpApiKeyReveal(key=key, state=self._to_state(payload))

    # ------------------------------------------------------------------ 读（transport 认证）

    def resolve_owner(self, token: str) -> Optional[str]:
        """密钥 → 归属用户名的认证校验（哈希恒定比对）；无效/缺失返回 None。

        只信 keyHash：密文不可解密（unreadable）不影响认证——加密副本仅服务
        查看面。行损坏/ schemaVersion 未知一律 None（fail-closed）。
        """
        payload = self._load_valid_payload()
        if payload is None:
            return None
        stored_hash = payload.get("keyHash")
        if not isinstance(stored_hash, str) or not stored_hash:
            return None
        if not hmac.compare_digest(hash_mcp_api_key(token), stored_hash):
            return None
        owner = payload.get("updatedBy") or payload.get("createdBy")
        return owner if isinstance(owner, str) and owner else None

    # ------------------------------------------------------------------ 内部

    def _load_valid_payload(self) -> Optional[Dict[str, Any]]:
        """读取并结构校验库中 JSON；缺失/损坏/版本未知返回 None（fail-closed）。"""
        row = self.db.query(Config).filter(Config.key == MCP_APIKEY_CONFIG_KEY).first()
        if row is None or not row.value:
            return None
        try:
            payload = json.loads(row.value)
        except (TypeError, json.JSONDecodeError) as exc:
            logger.warning("MCP 服务密钥 JSON 损坏，fail-closed 视为未生成: %s", exc)
            return None
        if not isinstance(payload, dict):
            logger.warning("MCP 服务密钥 JSON 非对象，fail-closed 视为未生成")
            return None
        if payload.get("schemaVersion") != MCP_APIKEY_SCHEMA_VERSION:
            logger.warning(
                "MCP 服务密钥 schemaVersion 未知（%r），fail-closed 视为未生成",
                payload.get("schemaVersion"),
            )
            return None
        if not isinstance(payload.get("keyHash"), str) or not payload.get("keyHash"):
            return None
        if not isinstance(payload.get("keyEncrypted"), str) or not payload.get("keyEncrypted"):
            return None
        return payload

    def _decrypt_plaintext(self, payload: Dict[str, Any]) -> Optional[str]:
        """解密并做格式自检；失败/格式不符返回 None（视图态 unreadable）。

        decrypt() 失败时原样返回密文（encryption.py 兼容通道语义），因此必须
        以 is_mcp_api_key_format 复核，防止把 sm4:hex... 当密钥返回。
        """
        try:
            plaintext = decrypt_password(payload["keyEncrypted"])
        except Exception as exc:  # 解密组件异常不外泄细节
            logger.warning("MCP 服务密钥解密异常，视图态置 unreadable: %s", exc)
            return None
        if not is_mcp_api_key_format(plaintext):
            logger.warning("MCP 服务密钥解密结果不符合密钥格式（secret_key 可能已轮换），视图态置 unreadable")
            return None
        return plaintext

    def _stored_revision(self, payload: Optional[Dict[str, Any]]) -> int:
        """库中当前 revision（无记录/不可解析=0，与视图态 absent 一致）。"""
        if payload is None:
            return 0
        revision = payload.get("revision")
        if isinstance(revision, int) and not isinstance(revision, bool) and revision >= 0:
            return revision
        return 0

    def _to_state(self, payload: Dict[str, Any]) -> McpApiKeyState:
        """载荷 → 元数据快照（调用方已保证结构合法）。"""
        created_at = payload.get("createdAt")
        created_by = payload.get("createdBy")
        updated_at = payload.get("updatedAt")
        updated_by = payload.get("updatedBy")
        return McpApiKeyState(
            status=STATUS_ACTIVE,
            revision=self._stored_revision(payload),
            created_at=created_at if isinstance(created_at, str) else None,
            created_by=created_by if isinstance(created_by, str) else None,
            updated_at=updated_at if isinstance(updated_at, str) else None,
            updated_by=updated_by if isinstance(updated_by, str) else None,
        )
