"""Behavioral tests for downloader ratio persistence boundaries."""

import math
import logging

import pytest

from app.services.torrent_ratio_values import (
    MISSING_RATIO_VALUE,
    RatioNormalizationStats,
    RatioValueState,
    apply_normalized_ratio_fields,
    normalize_ratio,
    normalize_ratio_limit,
)


@pytest.mark.parametrize(
    "raw",
    [
        None,
        MISSING_RATIO_VALUE,
        "",
        "garbage",
        ValueError("client parse failure"),
        True,
        False,
        -0.1,
        -1,
        float("nan"),
        float("inf"),
        float("-inf"),
        "1e309",
    ],
)
def test_ratio_rejects_missing_malformed_negative_and_non_finite_values(raw):
    result = normalize_ratio(raw)
    assert result.state is RatioValueState.UNAVAILABLE
    assert result.value is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0, 0.0),
        ("0", 0.0),
        (" 2.5 ", 2.5),
        ("1e3", 1000.0),
        (3, 3.0),
    ],
)
def test_ratio_accepts_finite_non_negative_values(raw, expected):
    result = normalize_ratio(raw)
    assert result.state is RatioValueState.VALUE
    assert result.value == expected
    assert math.isfinite(result.value)


@pytest.mark.parametrize("raw", [-1, -2, "-1", "-2.0"])
def test_ratio_limit_maps_qb_sentinels_to_explicit_null(raw):
    result = normalize_ratio_limit(raw)
    assert result.state is RatioValueState.EXPLICIT_NULL
    assert result.value is None


def test_unavailable_update_preserves_existing_columns_by_omitting_keys():
    update_mapping = {"info_id": "i1", "ratio": 2.5, "ratio_limit": 3.0}

    outcomes = apply_normalized_ratio_fields(
        update_mapping,
        raw_ratio=ValueError("temporary client failure"),
        raw_ratio_limit=None,
        is_insert=False,
    )

    assert outcomes == {
        "ratio": RatioValueState.UNAVAILABLE,
        "ratio_limit": RatioValueState.UNAVAILABLE,
    }
    assert "ratio" not in update_mapping
    assert "ratio_limit" not in update_mapping


def test_insert_uses_null_for_unavailable_values():
    insert_mapping = {"info_id": "i1"}

    apply_normalized_ratio_fields(
        insert_mapping,
        raw_ratio=ValueError("temporary client failure"),
        raw_ratio_limit=None,
        is_insert=True,
    )

    assert insert_mapping["ratio"] is None
    assert insert_mapping["ratio_limit"] is None


def test_explicit_null_clears_existing_ratio_limit_on_update():
    update_mapping = {"info_id": "i1", "ratio_limit": 3.0}

    apply_normalized_ratio_fields(
        update_mapping,
        raw_ratio=MISSING_RATIO_VALUE,
        raw_ratio_limit=-2,
        is_insert=False,
    )

    assert "ratio" not in update_mapping
    assert update_mapping["ratio_limit"] is None


def test_batch_stats_report_each_tristate_without_per_row_logging(caplog):
    stats = RatioNormalizationStats()
    mappings = [{}, {}, {}]

    stats.observe(
        apply_normalized_ratio_fields(
            mappings[0],
            raw_ratio=1.5,
            raw_ratio_limit=2,
            is_insert=False,
        )
    )
    stats.observe(
        apply_normalized_ratio_fields(
            mappings[1],
            raw_ratio=None,
            raw_ratio_limit=-1,
            is_insert=False,
        )
    )
    stats.observe(
        apply_normalized_ratio_fields(
            mappings[2],
            raw_ratio="invalid",
            raw_ratio_limit=float("nan"),
            is_insert=True,
        )
    )

    assert stats.as_dict() == {
        "rows": 3,
        "fields": {
            "ratio": {
                "value": 1,
                "explicit_null": 0,
                "unavailable": 2,
            },
            "ratio_limit": {
                "value": 1,
                "explicit_null": 1,
                "unavailable": 1,
            },
        },
    }
    assert stats.unavailable_count == 3

    with caplog.at_level(logging.WARNING):
        stats.log_summary(logging.getLogger("ratio-test"), context="test-batch")
    assert len(caplog.records) == 1
    assert "context=test-batch" in caplog.text
    assert "unavailable" in caplog.text


def test_batch_stats_use_debug_when_all_values_are_available(caplog):
    stats = RatioNormalizationStats()
    stats.observe(
        apply_normalized_ratio_fields(
            {},
            raw_ratio=0,
            raw_ratio_limit=-2,
            is_insert=False,
        )
    )

    with caplog.at_level(logging.DEBUG):
        stats.log_summary(logging.getLogger("ratio-test"), context="healthy")
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.DEBUG
