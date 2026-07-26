"""Harden ratio values for databases that already ran revision 6132.

Revision ID: 8f4c2d1a9b7e
Revises: 6132b66d14a7
Create Date: 2026-07-26 18:00:00.000000

This revision is intentionally idempotent with the corrected 6132 migration:
newly upgraded databases already have the checks, while databases that ran the
older lossy revision receive the checks here. Values that the old revision
already collapsed to 0.0 cannot be inferred and require backup/downloader
reconciliation; this migration never guesses by clearing all zeroes.

DESTRUCTIVE_MIGRATION_ROLLBACK: restore the validated pre-migration backup or
apply a forward repair. Downgrade only removes the new CHECK constraints and
cannot reconstruct historical malformed text.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "8f4c2d1a9b7e"
down_revision: Union[str, Sequence[str], None] = "6132b66d14a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RATIO_CHECK_NAME = "ck_torrent_info_ratio_finite_nonnegative"
_RATIO_LIMIT_CHECK_NAME = "ck_torrent_info_ratio_limit_finite_nonnegative"
_RATIO_CHECK = (
    "ratio IS NULL OR ("
    "typeof(ratio) IN ('integer', 'real') "
    "AND ratio >= 0 "
    "AND ratio <= 1.7976931348623157e308"
    ")"
)
_RATIO_LIMIT_CHECK = (
    "ratio_limit IS NULL OR ("
    "typeof(ratio_limit) IN ('integer', 'real') "
    "AND ratio_limit >= 0 "
    "AND ratio_limit <= 1.7976931348623157e308"
    ")"
)


def _strict_optional_ratio(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(numeric) or numeric < 0:
        return None
    return numeric


def _clean_current_invalid_values(bind) -> None:
    rows = bind.execute(
        sa.text("SELECT info_id, downloader_id, downloader_name, ratio, ratio_limit " "FROM torrent_info")
    ).mappings()
    updates: List[Dict[str, Any]] = []
    for row in rows:
        updates.append(
            {
                "info_id": row["info_id"],
                "downloader_id": row["downloader_id"],
                "downloader_name": row["downloader_name"],
                "ratio": _strict_optional_ratio(row["ratio"]),
                "ratio_limit": _strict_optional_ratio(row["ratio_limit"]),
            }
        )
    if updates:
        bind.execute(
            sa.text(
                "UPDATE torrent_info SET ratio=:ratio, ratio_limit=:ratio_limit "
                "WHERE info_id=:info_id AND downloader_id=:downloader_id "
                "AND downloader_name=:downloader_name"
            ),
            updates,
        )


def _check_names(inspector) -> set[str]:
    return {item["name"] for item in inspector.get_check_constraints("torrent_info") if item.get("name")}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("torrent_info"):
        return

    _clean_current_invalid_values(bind)
    existing = _check_names(inspector)
    if _RATIO_CHECK_NAME in existing and _RATIO_LIMIT_CHECK_NAME in existing:
        return

    with op.batch_alter_table("torrent_info") as batch_op:
        if _RATIO_CHECK_NAME not in existing:
            batch_op.create_check_constraint(_RATIO_CHECK_NAME, _RATIO_CHECK)
        if _RATIO_LIMIT_CHECK_NAME not in existing:
            batch_op.create_check_constraint(_RATIO_LIMIT_CHECK_NAME, _RATIO_LIMIT_CHECK)

    post = _check_names(sa.inspect(bind))
    missing = {_RATIO_CHECK_NAME, _RATIO_LIMIT_CHECK_NAME} - post
    if missing:
        raise RuntimeError(f"ratio CHECK constraints were not created: {sorted(missing)}")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("torrent_info"):
        return
    existing = _check_names(inspector)
    if not ({_RATIO_CHECK_NAME, _RATIO_LIMIT_CHECK_NAME} & existing):
        return
    with op.batch_alter_table("torrent_info") as batch_op:
        if _RATIO_CHECK_NAME in existing:
            batch_op.drop_constraint(_RATIO_CHECK_NAME, type_="check")
        if _RATIO_LIMIT_CHECK_NAME in existing:
            batch_op.drop_constraint(_RATIO_LIMIT_CHECK_NAME, type_="check")
