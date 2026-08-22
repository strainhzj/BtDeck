"""Canonical ratio/ratio-limit normalization for torrent persistence.

Downloader payloads have three materially different states:

* a finite, non-negative numeric value;
* an explicit downloader sentinel meaning that no per-torrent numeric limit
  exists (qBittorrent ``-1``/``-2``);
* missing or malformed data that must not overwrite an existing good value.

Keeping those states separate prevents a transient downloader/client failure
from clearing previously persisted values while still allowing new rows to use
``NULL`` when no trustworthy value is available.
"""

from __future__ import annotations

import math
import logging
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict


class RatioValueState(str, Enum):
    VALUE = "value"
    EXPLICIT_NULL = "explicit_null"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class NormalizedRatioValue:
    state: RatioValueState
    value: float | None = None

    def value_for_insert(self) -> float | None:
        """Return the persisted value for a newly created row."""
        return self.value if self.state is RatioValueState.VALUE else None


MISSING_RATIO_VALUE = object()


@dataclass
class RatioNormalizationStats:
    """Aggregate downloader ratio observations for one synchronization batch."""

    rows: int = 0
    counts: Dict[str, Counter[RatioValueState]] = field(
        default_factory=lambda: {
            "ratio": Counter(),
            "ratio_limit": Counter(),
        }
    )

    def observe(self, outcomes: Dict[str, RatioValueState]) -> None:
        self.rows += 1
        for ratio_field, state in outcomes.items():
            if ratio_field in self.counts:
                self.counts[ratio_field][state] += 1

    @property
    def unavailable_count(self) -> int:
        return sum(field_counts[RatioValueState.UNAVAILABLE] for field_counts in self.counts.values())

    def as_dict(self) -> Dict[str, Any]:
        return {
            "rows": self.rows,
            "fields": {
                ratio_field: {state.value: field_counts[state] for state in RatioValueState}
                for ratio_field, field_counts in self.counts.items()
            },
        }

    def log_summary(self, batch_logger: logging.Logger, *, context: str) -> None:
        """Emit one structured summary instead of one log line per torrent."""
        log_method = batch_logger.warning if self.unavailable_count else batch_logger.debug
        log_method(
            "ratio normalization summary: context=%s rows=%s fields=%s",
            context,
            self.rows,
            self.as_dict()["fields"],
        )


def _finite_non_negative(value: Any) -> NormalizedRatioValue:
    if value is MISSING_RATIO_VALUE or value is None or isinstance(value, bool):
        return NormalizedRatioValue(RatioValueState.UNAVAILABLE)
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return NormalizedRatioValue(RatioValueState.UNAVAILABLE)
    if not math.isfinite(numeric) or numeric < 0:
        return NormalizedRatioValue(RatioValueState.UNAVAILABLE)
    return NormalizedRatioValue(RatioValueState.VALUE, numeric)


def normalize_ratio(value: Any = MISSING_RATIO_VALUE) -> NormalizedRatioValue:
    """Normalize an observed upload ratio without inventing a replacement."""
    return _finite_non_negative(value)


def normalize_ratio_limit(value: Any = MISSING_RATIO_VALUE) -> NormalizedRatioValue:
    """Normalize a per-torrent ratio limit.

    qBittorrent uses ``-1`` (unlimited) and ``-2`` (inherit global setting).
    The current schema intentionally projects both to ``NULL``, whose meaning
    is "no explicit per-torrent numeric limit"; it must not be used to write a
    setting back to the downloader.
    """
    if value is not MISSING_RATIO_VALUE and not isinstance(value, bool):
        try:
            numeric = float(value)
        except (TypeError, ValueError, OverflowError):
            numeric = None
        if numeric in (-1.0, -2.0):
            return NormalizedRatioValue(RatioValueState.EXPLICIT_NULL)
    return _finite_non_negative(value)


def apply_normalized_ratio_fields(
    mapping: Dict[str, Any],
    *,
    raw_ratio: Any = MISSING_RATIO_VALUE,
    raw_ratio_limit: Any = MISSING_RATIO_VALUE,
    is_insert: bool,
) -> Dict[str, RatioValueState]:
    """Apply canonical values to an ORM bulk mapping.

    For updates, unavailable fields are deliberately omitted so SQLAlchemy does
    not overwrite an existing good value. For inserts, unavailable fields are
    represented as ``NULL``.

    Returns the observed state for each supplied field so callers can aggregate
    telemetry without logging once per torrent.
    """
    outcomes: Dict[str, RatioValueState] = {}
    values = {
        "ratio": normalize_ratio(raw_ratio),
        "ratio_limit": normalize_ratio_limit(raw_ratio_limit),
    }
    for ratio_field, normalized in values.items():
        outcomes[ratio_field] = normalized.state
        if normalized.state is RatioValueState.VALUE:
            mapping[ratio_field] = normalized.value
        elif normalized.state is RatioValueState.EXPLICIT_NULL or is_insert:
            mapping[ratio_field] = None
        else:
            mapping.pop(ratio_field, None)
    return outcomes
