"""Field-level schema diagnostics for artifact and draft validation.

This module is deliberately leaf-level: it imports nothing from the contract
layer, so both layers can use it without a dependency cycle. The canonical
validator (the hand-written checker in the contract canon) is the oracle; this
walker only locates and explains failures. The contract module registers the
oracle once at import time.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Callable

DraftIssue = dict[str, str]

_registered_validator: list[Callable[[dict[str, Any], object, dict[str, Any]], bool]] = []


def register_schema_validator(
    implementation: Callable[[dict[str, Any], object, dict[str, Any]], bool],
) -> None:
    del _registered_validator[:]
    _registered_validator.append(implementation)


def _oracle(schema: dict[str, Any], value: object, root: dict[str, Any]) -> bool:
    if not _registered_validator:
        raise RuntimeError(
            "schema diagnostics require the canonical validator; import the contract "
            "module before schema_issues"
        )
    return _registered_validator[0](schema, value, root)


def _compact(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def _list(value: object) -> list[Any]:
    return cast("list[Any]", value)


def _dict(value: object) -> dict[str, Any]:
    return cast("dict[str, Any]", value)


def is_dict(value: object) -> bool:
    return isinstance(value, dict)


# Compact expectation text for diagnostics: names the type, required fields,
# and allowed values instead of dumping the schema document.
def expectation(schema: dict[str, Any]) -> str:
    parts: list[str] = []
    reference = schema.get("$ref")
    if isinstance(reference, str):
        return reference.removeprefix("#/$defs/")
    if "const" in schema:
        parts.append(f"exactly {_compact(schema['const'])}")
    elif isinstance(schema.get("enum"), list):
        parts.append("one of " + ", ".join(_compact(item) for item in _list(schema["enum"])))
    elif isinstance(schema.get("type"), list):
        parts.append(" or ".join(str(item) for item in _list(schema["type"])))
    elif isinstance(schema.get("type"), str):
        parts.append(str(schema["type"]))
    required = schema.get("required")
    if isinstance(required, list) and len(required) > 0:
        parts.append("with required fields " + ", ".join(str(item) for item in _list(required)))
    if isinstance(schema.get("additionalProperties"), dict) and is_dict(schema.get("properties")):
        parts.append("with only the fields " + ", ".join(_dict(schema["properties"]).keys()))
    min_length = schema.get("minLength")
    if isinstance(min_length, (int, float)) and not isinstance(min_length, bool):
        parts.append("non-empty")
    min_items = schema.get("minItems")
    if isinstance(min_items, (int, float)) and not isinstance(min_items, bool):
        parts.append(f"at least {min_items} items")
    return "; ".join(parts) if parts else "a value matching the input schema"


def _js_typeof(value: object) -> str:
    # The compatibility clause mirrors the TypeScript `branch.type === typeof value`
    # comparison, including `typeof null === "object"`.
    if value is None or isinstance(value, (dict, list)):
        return "object"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return "string"


# The canonical validator decides validity; this walker only locates and
# explains failures. ``root`` must be the schema document that $ref pointers
# resolve against.
def schema_issues(
    schema: dict[str, Any], value: object, path: str, root: dict[str, Any]
) -> list[DraftIssue]:
    if _oracle(schema, value, root):
        return []
    reference = schema.get("$ref")
    if isinstance(reference, str):
        definitions = root.get("$defs")
        definition = (
            definitions.get(reference.removeprefix("#/$defs/"))
            if isinstance(definitions, dict)
            else None
        )
        return (
            schema_issues(definition, value, path, root)
            if isinstance(definition, dict)
            else [{"path": path, "message": "Unknown schema reference"}]
        )
    errors: list[DraftIssue] = []
    if isinstance(value, dict):
        properties = schema.get("properties")
        property_map = properties if isinstance(properties, dict) else {}
        required = schema.get("required")
        for key in _list(required) if isinstance(required, list) else []:
            if key not in value:
                expected = property_map.get(key)
                declared = (
                    _compact(expected)
                    if isinstance(expected, dict)
                    else "the field declared by the input schema"
                )
                errors.append(
                    {
                        "path": f"{path}.{key}",
                        "message": f"Required field is missing; expected {declared}",
                    }
                )
        for key, item in value.items():
            nested = property_map.get(key)
            if isinstance(nested, dict):
                errors.extend(schema_issues(nested, item, f"{path}.{key}", root))
            elif schema.get("additionalProperties") is False:
                errors.append(
                    {
                        "path": f"{path}.{key}",
                        "message": (
                            "Unknown field; allowed fields are "
                            + (", ".join(property_map.keys()) or "none")
                        ),
                    }
                )
    items_schema = schema.get("items")
    if isinstance(value, list) and isinstance(items_schema, dict):
        for index, item in enumerate(value):
            errors.extend(schema_issues(items_schema, item, f"{path}[{index}]", root))
    all_of = schema.get("allOf")
    if isinstance(all_of, list):
        for branch in _list(all_of):
            if isinstance(branch, dict):
                errors.extend(schema_issues(branch, value, path, root))
    condition = schema.get("if")
    if isinstance(condition, dict):
        branch = schema.get("then") if _oracle(condition, value, root) else schema.get("else")
        if isinstance(branch, dict):
            errors.extend(schema_issues(branch, value, path, root))
    for keyword in ("anyOf", "oneOf"):
        branches = schema.get(keyword)
        if not isinstance(branches, list) or any(
            isinstance(branch, dict) and _oracle(branch, value, root) for branch in branches
        ):
            continue
        dict_branches = [branch for branch in _list(branches) if isinstance(branch, dict)]
        alternatives = [schema_issues(branch, value, path, root) for branch in dict_branches]
        compatible = [
            branch
            for branch in dict_branches
            if "type" not in branch
            or (branch["type"] == "object" and isinstance(value, dict))
            or (branch["type"] == "array" and isinstance(value, list))
            or branch["type"] == _js_typeof(value)
            or (branch["type"] == "null" and value is None)
        ]
        candidates = (
            [schema_issues(branch, value, path, root) for branch in compatible]
            if compatible
            else alternatives
        )
        candidates.sort(key=len)
        errors.extend(candidates[0])
    if not errors:
        errors.append({"path": path, "message": f"Expected {expectation(schema)}"})
    return errors
