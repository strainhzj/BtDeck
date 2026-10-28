# -*- coding: utf-8 -*-
"""数据库迁移协议元数据模型（database-migration-ui W1-1，PLANS §3.2/§3.3）。

三张受 Alembic 管理的协议元数据表（区别于业务表）：

- ``bt_database_identity``：库自身随机 UUID 单例——**不可在导入时从源复制
  给目标**，也不能用 host/revision 代替；现有库经新增 revision 生成身份。
- ``bt_database_migration_receipt``：迁移完成凭据（ownership），分离于会被
  DROP 的 ``_btdeck_import_state`` 标记——首表导入前即持久（IMPORTING），
  finalize 在目标同一事务更新为 VERIFIED 并清标记；激活后记录 generation。
- ``bt_database_migration_events``：本地审计回放去重行（与正式审计日志
  同事务归档；摘要不得含密码/令牌/完整连接 URL/TOTP）。

表名/状态常量在 ``app.core.database_protocol``（纯模块，无引擎副作用）；
本模块 import ORM 基类，仅供模型注册完成后使用。业务数据范围 =
``business_tables()``（metadata.sorted_tables 排除三协议表，§3.2）。
"""

from __future__ import annotations

from datetime import datetime
from typing import List

from sqlalchemy import JSON, CheckConstraint, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database_protocol import (
    DIGEST_VERSION_CANONICAL_V1,
    IDENTITY_TABLE,
    PROTOCOL_SCHEMA_VERSION,
    PROTOCOL_TABLE_NAMES,
    RECEIPT_TABLE,
    RECEIPT_STATUSES,
    EVENTS_TABLE,
)
from app.database import Base


def business_tables() -> List:
    """业务表清单 = metadata.sorted_tables − 三张协议元数据表（§3.2）。

    调用前提：``register_all_models()`` 已执行（模型已注册）。
    本函数不递归注册、不创建引擎——调用方负责注册时机。
    """
    return [t for t in Base.metadata.sorted_tables if t.name not in PROTOCOL_TABLE_NAMES]


class BtDatabaseIdentity(Base):
    """库身份单例：一行（id=1），database_id 为随机 UUID。

    - 导入目标库**生成自己的** identity，不从源复制（§3.2）；
    - 禁止在 FROZEN 后补 seed（本行由 revision/基线事务创建，运行期只读）。
    """

    __tablename__ = IDENTITY_TABLE
    __table_args__ = (CheckConstraint("id = 1", name="ck_bt_database_identity_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False, comment="单例主键，恒为 1")
    database_id: Mapped[str] = mapped_column(
        String(36), nullable=False, comment="库自身随机 UUID（uuid4；导入不可从源复制）"
    )
    schema_version: Mapped[str] = mapped_column(
        String(16), nullable=False, comment=f"协议表结构版本（当前 {PROTOCOL_SCHEMA_VERSION}）"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="身份创建时间（UTC）")


class BtDatabaseMigrationReceipt(Base):
    """迁移完成凭据（ownership receipt，§3.3）。

    状态机：IMPORTING（首表导入前持久）→ VERIFIED（finalize 同事务原子更新，
    并清未完成标记）→ ACTIVATED（首次激活写入 generation/activated_at）；
    STALE（epoch 失效）/ ABANDONED（显式放弃）为失效态。
    ``origin_epoch`` 不可变；``eligible_epoch`` 可撤销（重绑协议 CAS 目标）。
    """

    __tablename__ = RECEIPT_TABLE

    attempt_id: Mapped[str] = mapped_column(
        String(96), primary_key=True, comment="sqlite-to-pg/<uuid> | pg-to-sqlite/<uuid> | handoff/<uuid>"
    )
    operation_kind: Mapped[str] = mapped_column(String(32), nullable=False, comment="MIGRATE | HANDOFF_SAME_DB")
    source_database_id: Mapped[str] = mapped_column(
        String(36), nullable=True, comment="源库 database_id（源无身份时为 NULL）"
    )
    target_database_id: Mapped[str] = mapped_column(
        String(36), nullable=False, comment="目标库 database_id（目标自身身份）"
    )
    deployment_id: Mapped[str] = mapped_column(
        String(64), nullable=True, comment="配置卷部署标识（首次使用管理功能时持久创建；早期可为 NULL）"
    )
    ownership_nonce: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="随机 ownership nonce（清理/切换授权核对）"
    )
    revision_at_import: Mapped[str] = mapped_column(String(64), nullable=False, comment="导入时迁移链 revision")
    digest_version: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=DIGEST_VERSION_CANONICAL_V1,
        comment=f"内容摘要算法版本（当前 {DIGEST_VERSION_CANONICAL_V1}）",
    )
    table_counts: Mapped[dict] = mapped_column(
        JSON, nullable=True, comment="全业务表行数清单 {表名: 行数}（verify 通过后写入）"
    )
    table_digests: Mapped[dict] = mapped_column(
        JSON, nullable=True, comment="全业务表内容摘要清单 {表名: sha256}（verify 通过后写入）"
    )
    schema_fingerprint: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="schema 指纹（表/列清单排序摘要）"
    )
    origin_epoch: Mapped[str] = mapped_column(String(64), nullable=False, comment="创建本次导入的冻结代次（不可变）")
    eligible_epoch: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="当前切换资格代次（可撤销；重绑协议 CAS 目标）"
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, comment=" | ".join(sorted(RECEIPT_STATUSES)))
    activation_generation: Mapped[str] = mapped_column(
        String(64), nullable=True, comment="激活时的配置 generation（ACTIVATED 后写入）"
    )
    activated_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="首次激活时间（UTC）")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="receipt 创建时间（UTC）")
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="最近更新时间（UTC）")


class BtDatabaseMigrationEvent(Base):
    """本地审计回放去重行（§3.2）。

    事件先落本地受保护 jsonl，恢复后按 event_id 去重与正式审计日志同事务
    归档到最终服务库；``summary`` 为脱敏摘要（不含密码/令牌/连接 URL）。
    """

    __tablename__ = EVENTS_TABLE

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="事件唯一 ID（uuid4）")
    attempt_id: Mapped[str] = mapped_column(
        String(96), nullable=False, index=True, comment="所属 attempt（逻辑引用 receipt.attempt_id）"
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False, comment="attempt 内单调序号")
    summary: Mapped[str] = mapped_column(String(512), nullable=False, comment="事件摘要（脱敏）")
    archived_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=True, comment="归档到正式审计日志的时间；NULL=未归档"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="事件时间（UTC）")
