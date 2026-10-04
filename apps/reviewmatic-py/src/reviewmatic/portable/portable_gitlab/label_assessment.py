"""Exhaustive evidence-bound label assessment shared by MR workflows."""

from typing import Any, cast

from . import contract as portable


def label_catalog(evidence: dict[str, Any]) -> list[dict[str, str | None]]:
    component = evidence.get("labels")
    if not isinstance(component, dict) or component.get("complete") is not True:
        raise portable.WorkflowError("project label catalog is incomplete")
    catalog: list[dict[str, str | None]] = []
    names: set[str] = set()
    folded: set[str] = set()
    for value in cast("list[object]", component.get("items", [])):
        if not isinstance(value, dict) or not portable.nonempty_string(value.get("name")):
            raise portable.WorkflowError("project label catalog entry is invalid")
        name = cast("str", value["name"])
        description = value.get("description")
        if description is not None and not isinstance(description, str):
            raise portable.WorkflowError("project label description is invalid")
        if name in names or name.casefold() in folded:
            raise portable.WorkflowError("project label catalog contains duplicate names")
        names.add(name)
        folded.add(name.casefold())
        catalog.append({"name": name, "description": description})
    return sorted(catalog, key=lambda item: (cast("str", item["name"]).casefold(), item["name"]))


def validate_label_assessments(
    evidence: dict[str, Any], value: object, semver_impact: str
) -> dict[str, Any]:
    catalog = label_catalog(evidence)
    catalog_by_name = {cast("str", item["name"]): item for item in catalog}
    if not isinstance(value, list):
        raise portable.WorkflowError("label assessments must be an array")
    assessments: dict[str, dict[str, Any]] = {}
    for item in value:
        if (
            not isinstance(item, dict)
            or set(item) != {"name", "status", "rationale"}
            or not portable.nonempty_string(item.get("name"))
            or item.get("status") not in {"applicable", "inapplicable", "unresolved"}
            or not portable.nonempty_string(item.get("rationale"))
            or item["name"] in assessments
        ):
            raise portable.WorkflowError("label assessment is invalid")
        assessments[cast("str", item["name"])] = cast("dict[str, Any]", item)
    if set(assessments) != set(catalog_by_name):
        raise portable.WorkflowError("label assessments must cover the complete project catalog")
    compatibility: dict[str, list[str]] = {"major": [], "minor": [], "patch": []}
    for item in cast("list[dict[str, Any]]", evidence["labels"]["items"]):
        semantics = portable.label_semantics(item)
        if semantics is not None and semantics[0] == "compatibility":
            compatibility[semantics[1]].append(cast("str", item["name"]))
    selected: str | None = None
    if semver_impact in compatibility:
        candidates = sorted(compatibility[semver_impact], key=str.casefold)
        if len(candidates) == 1:
            selected = candidates[0]
            if assessments[selected]["status"] != "applicable":
                raise portable.WorkflowError(
                    "SemVer impact requires the matching compatibility label"
                )
        elif len(candidates) > 1 and any(
            assessments[name]["status"] != "unresolved" for name in candidates
        ):
            raise portable.WorkflowError(
                "ambiguous SemVer compatibility labels must remain unresolved"
            )
        for impact, names in compatibility.items():
            if impact != semver_impact and any(
                assessments[name]["status"] == "applicable" for name in names
            ):
                raise portable.WorkflowError(
                    "an incompatible SemVer label cannot be assessed as applicable"
                )
    object_value = evidence.get("object")
    current_value = object_value.get("labels") if isinstance(object_value, dict) else None
    if not isinstance(current_value, list) or not all(
        isinstance(item, str) for item in current_value
    ):
        raise portable.WorkflowError("current MR labels are unavailable")
    current = sorted(set(cast("list[str]", current_value)), key=str.casefold)
    if len(current) != len(current_value) or not set(current).issubset(catalog_by_name):
        raise portable.WorkflowError("current MR labels do not match the complete catalog")
    entries = [
        {
            **assessments[cast("str", item["name"])],
            "description": item["description"],
            "current": item["name"] in current,
        }
        for item in catalog
    ]
    add = sorted(
        [
            cast("str", item["name"])
            for item in entries
            if item["status"] == "applicable" and item["name"] not in current
        ],
        key=str.casefold,
    )
    remove = sorted(
        [
            cast("str", item["name"])
            for item in entries
            if item["status"] == "inapplicable" and item["name"] in current
        ],
        key=str.casefold,
    )
    return {
        "complete": True,
        "catalog_sha256": portable.digest(catalog),
        "catalog": catalog,
        "assessments": entries,
        "current": current,
        "add": add,
        "remove": remove,
        "proposed": sorted((set(current) - set(remove)) | set(add), key=str.casefold),
        "unresolved": [
            cast("str", item["name"]) for item in entries if item["status"] == "unresolved"
        ],
        "semver": {
            "impact": semver_impact,
            "candidates": sorted(compatibility.get(semver_impact, []), key=str.casefold),
            "selected": selected,
        },
    }
