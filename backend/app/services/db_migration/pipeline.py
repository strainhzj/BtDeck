# -*- coding: utf-8 -*-
"""双向迁移管线共享编排（database-migration-ui W1-5，PLANS §3.3/§5.1/§6.1/§6.4）。

两个方向（sqlite_to_pg / pg_to_sqlite）共用的：

- ``PipelineContext``：attempt/ownership/epoch 绑定 + 进度与协作取消回调
  （取消仅请求 worker 协作停止；W2 manager 接管 CANCELLING→CANCELLED 状态机，
  W1 落实"可协作取消/进度接口"与持久字段，PLANS §12 复核意见 4）；
- checkpoint 载体：``_btdeck_import_state.checkpoint`` JSON 与 receipt 同步
  携带 attempt/nonce/epoch 绑定（§3.3：不等 finalize 才首次存 nonce）；
- 恢复校验：检查点必须是依赖序完整前缀 + 每表行数对账 + 协议版本一致；
  旧 1.1.0 checkpoint（无 ownership 绑定）明确拒绝，不伪装兼容（§6.3）。

六阶段：precheck → baseline → import → calibrate → verify → finalize
（顺序固定；每表数据+checkpoint 同事务提交；finalize 同事务 receipt VERIFIED
+清 marker——落 pg_baseline 协议操作）。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from app.core.database_protocol import (
    ATTEMPT_PREFIX_PG_TO_SQLITE,
    ATTEMPT_PREFIX_SQLITE_TO_PG,
    DIGEST_VERSION_CANONICAL_V1,
    OPERATION_MIGRATE,
)

# 新协议工具版本：2.0.0 起引入 ownership receipt/epoch/nonce 绑定；
# 1.1.0 checkpoint 无这些绑定——明确拒绝恢复（不伪装兼容，PLANS §6.3）
TOOL_VERSION = "2.0.0"

ProgressCallback = Callable[[str, int, int], None]  # (phase, done, total)
CancelCheck = Callable[[], None]  # 协作边界调用；需取消时抛 MigrationCancelled


class MigrationCancelled(RuntimeError):
    """协作取消信号（仅在批/表边界检查；worker 收尾语义由 W2 manager 接管）。"""


@dataclass
class PipelineContext:
    """一次迁移尝试的身份/凭据绑定与协作接口。"""

    attempt_id: str
    operation_kind: str = OPERATION_MIGRATE
    ownership_nonce: str = field(default_factory=lambda: uuid.uuid4().hex)
    origin_epoch: str = field(default_factory=lambda: f"epoch-{uuid.uuid4().hex[:16]}")
    eligible_epoch: str = ""  # 缺省同 origin（首次冻结即唯一资格代次）
    digest_version: str = DIGEST_VERSION_CANONICAL_V1
    deployment_id: Optional[str] = None
    source_database_id: Optional[str] = None
    progress: Optional[ProgressCallback] = None
    cancel_check: Optional[CancelCheck] = None

    def __post_init__(self) -> None:
        if not self.eligible_epoch:
            self.eligible_epoch = self.origin_epoch

    def check_cancel(self) -> None:
        if self.cancel_check is not None:
            self.cancel_check()

    def report(self, phase: str, done: int, total: int) -> None:
        if self.progress is not None:
            self.progress(phase, done, total)

    def checkpoint_payload(self, completed: Mapping[str, int]) -> Dict[str, Any]:
        """checkpoint JSON：与 receipt 同步的 ownership 绑定 + 完成表行数。"""
        return {
            "attempt_id": self.attempt_id,
            "ownership_nonce": self.ownership_nonce,
            "origin_epoch": self.origin_epoch,
            "eligible_epoch": self.eligible_epoch,
            "tool_version": TOOL_VERSION,
            "digest_version": self.digest_version,
            "completed": dict(completed),
        }


def make_attempt_id(direction: str) -> str:
    """按方向生成 attempt_id（前缀+UUID，§3.1；目录映射用 UUID 尾段）。"""
    prefix = {
        "sqlite-to-pg": ATTEMPT_PREFIX_SQLITE_TO_PG,
        "pg-to-sqlite": ATTEMPT_PREFIX_PG_TO_SQLITE,
    }[direction]
    return f"{prefix}{uuid.uuid4()}"


def validate_checkpoint_prefix(
    checkpoint: Mapping[str, Any],
    table_names: Sequence[str],
    *,
    ctx_attempt_id: str,
    ctx_nonce: str,
) -> Dict[str, int]:
    """恢复校验：绑定匹配 + 协议版本 + 依赖序完整前缀；返回 completed 行数表。

    拒绝面（exit 码语义由 CLI/服务层翻译）：
    - 旧 1.1.0 checkpoint（无 attempt/nonce 绑定）→ 明确不兼容；
    - attempt/nonce 与本次上下文不符 → 拒绝（复制/伪造不构成授权）；
    - completed 键集不是依赖序前缀 → 拒绝。
    """
    if not isinstance(checkpoint, Mapping):
        raise CheckpointIncompatible("检查点格式非法（非对象）")
    if not checkpoint.get("attempt_id") or not checkpoint.get("ownership_nonce"):
        raise CheckpointIncompatible(
            "旧协议 checkpoint（1.1.0，无 ownership 绑定）与新工具不兼容：" "请评估目标库后重新开始迁移（PLANS §6.3）"
        )
    if checkpoint.get("attempt_id") != ctx_attempt_id or checkpoint.get("ownership_nonce") != ctx_nonce:
        raise CheckpointIncompatible("checkpoint 绑定（attempt/nonce）与本次恢复上下文不符——拒绝")
    if checkpoint.get("tool_version") != TOOL_VERSION:
        raise CheckpointIncompatible(
            f"checkpoint 工具版本 {checkpoint.get('tool_version')!r} ≠ {TOOL_VERSION}——拒绝恢复"
        )
    completed = checkpoint.get("completed")
    if not isinstance(completed, Mapping):
        raise CheckpointIncompatible("检查点缺少 completed 表")
    keys = list(completed.keys())
    if set(keys) != set(table_names[: len(keys)]) or keys != table_names[: len(keys)]:
        raise CheckpointIncompatible("检查点不是依赖序的完整前缀——拒绝恢复")
    for name, count in completed.items():
        if type(count) is not int or count < 0:
            raise CheckpointIncompatible(f"检查点行数非法：{name}={count!r}")
    return dict(completed)


class CheckpointIncompatible(RuntimeError):
    """checkpoint 不兼容/不合法（恢复拒绝；调用方按目标库状态非法处理）。"""


def read_marker_state(conn: Any) -> Optional[Dict[str, Any]]:
    """读取导入标记（经 pg_baseline；无表/无行 None）。"""
    from app.core.pg_baseline import get_import_state

    return get_import_state(conn)


def resume_row_counts_match(
    conn: Any, completed: Mapping[str, int], tables_by_name: Mapping[str, Any]
) -> Optional[str]:
    """恢复前逐表行数对账（ORM 构造，无字符串 SQL）；返回首个不匹配表名（None=全部一致）。

    ``tables_by_name``：业务表名 → Table 对象（依赖序清单构建；completed 的键
    已由 validate_checkpoint_prefix 校验为该清单前缀）。
    """
    from sqlalchemy import func, select

    for table_name, expected in completed.items():
        table = tables_by_name[table_name]
        actual = conn.execute(select(func.count()).select_from(table)).scalar()
        if actual != expected:
            return table_name
    return None
