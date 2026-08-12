"""Machine-readable advanced-search contract consumed by backend and frontend."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, FrozenSet

_CONTRACT_PATH = Path(__file__).with_name("advanced_search_contract.json")
ADVANCED_SEARCH_CONTRACT: Dict[str, Any] = json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))
SEARCH_FIELD_CONTRACT: Dict[str, Dict[str, Any]] = ADVANCED_SEARCH_CONTRACT["fields"]
NULL_SEARCH_OPERATORS: FrozenSet[str] = frozenset(ADVANCED_SEARCH_CONTRACT.get("nullOperators", []))
SUPPORTED_SEARCH_OPERATORS: FrozenSet[str] = (
    frozenset(operator for field in SEARCH_FIELD_CONTRACT.values() for operator in field["operators"])
    | NULL_SEARCH_OPERATORS
)
MAX_REGEX_CONDITIONS = int(ADVANCED_SEARCH_CONTRACT["maxRegexConditions"])
MAX_REGEX_PATTERN_LENGTH = int(ADVANCED_SEARCH_CONTRACT["maxRegexPatternLength"])
FRONTEND_TO_BACKEND_OPERATOR: Dict[str, str] = {
    str(item["value"]): str(item["backendValue"])
    for group in ADVANCED_SEARCH_CONTRACT["operatorGroups"].values()
    for item in group
}
NEGATED_SEARCH_OPERATORS: Dict[str, str] = {
    str(operator): str(negated) for operator, negated in ADVANCED_SEARCH_CONTRACT["negatedOperators"].items()
}


def allowed_operators_for_field(field: str) -> FrozenSet[str]:
    config = SEARCH_FIELD_CONTRACT.get(field)
    if not config:
        return frozenset()
    return frozenset(config["operators"])


def field_kind(field: str) -> str | None:
    config = SEARCH_FIELD_CONTRACT.get(field)
    return str(config["kind"]) if config else None
