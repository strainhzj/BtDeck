"""Strict boundary tests for advanced-search requests and templates."""

import copy

import pytest
from pydantic import ValidationError

from app.api.models.advanced_search import (
    EnhancedAdvancedSearchRequest,
    SearchCondition,
    SearchTemplateCreate,
    validate_template_conditions_payload,
)
from app.data.default_search_templates import DEFAULT_SEARCH_TEMPLATES


def _advanced_template(condition: dict) -> dict:
    return {
        "source": "advanced",
        "version": 1,
        "condition_groups": [
            {
                "id": "g1",
                "logic": "and",
                "conditions": [
                    {
                        "id": "c1",
                        "mode": "include",
                        **condition,
                    }
                ],
            }
        ],
        "sort_by": "added_time",
        "sort_order": "desc",
    }


def test_one_sided_between_is_preserved():
    condition = SearchCondition(
        field="ratio",
        operator="between",
        value={"min": 1, "max": None},
    )
    assert condition.value == {"min": 1.0, "max": None}


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, True])
def test_invalid_numeric_values_are_rejected(value):
    with pytest.raises(ValidationError):
        SearchCondition(field="ratio", operator="eq", value=value)


def test_group_logic_count_is_exact():
    group = {
        "logic": "AND",
        "conditions": [{"field": "name", "operator": "eq", "value": "x"}],
    }
    with pytest.raises(ValidationError, match="between_group_logics length"):
        EnhancedAdvancedSearchRequest(
            condition_groups=[group, group],
            between_group_logics=[],
        )


def test_template_exclude_mode_is_validated_using_negated_operator():
    payload = _advanced_template(
        {
            "field": "tags",
            "operator": "contains_any",
            "value": ["movie"],
            "mode": "exclude",
        }
    )
    validate_template_conditions_payload(payload)


def test_template_exclude_mode_preserves_the_positive_operator():
    payload = _advanced_template(
        {
            "field": "ratio",
            "operator": "greater_than",
            "value": 2,
            "mode": "exclude",
        }
    )

    validated = validate_template_conditions_payload(payload)

    condition = validated["condition_groups"][0]["conditions"][0]
    assert condition["operator"] == "greater_than"
    assert condition["mode"] == "exclude"


def test_null_operators_are_limited_to_fields_that_declare_them():
    assert SearchCondition(field="ratio_limit", operator="is_null", value=None).value is None
    with pytest.raises(ValidationError, match="not allowed for field"):
        SearchCondition(field="name", operator="is_null", value=None)


@pytest.mark.parametrize(
    ("operator", "expected"),
    [("contains", "contains_any"), ("eq", "contains_any"), ("ne", "not_contains_any")],
)
def test_legacy_tag_scalar_operators_normalize_to_token_semantics(operator, expected):
    condition = SearchCondition(field="tags", operator=operator, value="辅种")
    assert condition.operator == expected
    assert condition.value == ["辅种"]


def test_template_rejects_exclude_mode_without_exact_negation():
    payload = _advanced_template(
        {
            "field": "name",
            "operator": "regex",
            "value": {"pattern": "^x$", "caseSensitive": True},
            "mode": "exclude",
        }
    )
    with pytest.raises(ValueError, match="does not support exclude mode"):
        validate_template_conditions_payload(payload)


def test_template_requires_explicit_group_and_between_group_logic():
    payload = _advanced_template(
        {"field": "name", "operator": "eq", "value": "x"}
    )
    del payload["condition_groups"][0]["logic"]
    with pytest.raises(ValueError, match="requires explicit logic"):
        validate_template_conditions_payload(payload)

    payload = _advanced_template(
        {"field": "name", "operator": "eq", "value": "x"}
    )
    second = copy.deepcopy(payload["condition_groups"][0])
    second["id"] = "g2"
    payload["condition_groups"].append(second)
    with pytest.raises(ValueError, match="betweenGroupLogic"):
        validate_template_conditions_payload(payload)


def test_template_rejects_unknown_condition_keys():
    payload = _advanced_template(
        {
            "field": "name",
            "operator": "eq",
            "value": "x",
            "silentlyIgnored": True,
        }
    )
    with pytest.raises(ValueError, match="unknown keys"):
        validate_template_conditions_payload(payload)


def test_all_bundled_default_templates_satisfy_runtime_validation():
    for template in DEFAULT_SEARCH_TEMPLATES:
        SearchTemplateCreate(
            name=template["name"],
            description=template["description"],
            conditions=template["conditions"],
        )
