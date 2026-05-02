"""RFC 6902 JSON Patch application (restricted subset) for starter tools."""

from __future__ import annotations

import copy
import json
from typing import Any


class JsonPatchError(ValueError):
    """Invalid patch document or operation failed validation."""


def _unescape_segment(seg: str) -> str:
    return seg.replace("~1", "/").replace("~0", "~")


def parse_json_pointer(path: str) -> list[str]:
    if path == "":
        return []
    if not path.startswith("/"):
        raise JsonPatchError("JSON Pointer must be empty or start with '/'.")
    parts = path.split("/")[1:]
    return [_unescape_segment(p) for p in parts]


def _traverse_to_parent(
    doc: Any, parts: list[str], *, create_missing: bool
) -> tuple[Any, str]:
    if not parts:
        raise JsonPatchError("JSON Pointer has no segments.")
    cur = doc
    for seg in parts[:-1]:
        if isinstance(cur, dict):
            if seg not in cur:
                if create_missing:
                    cur[seg] = {}
                else:
                    raise JsonPatchError(f"Path segment {seg!r} does not exist.")
            cur = cur[seg]
        elif isinstance(cur, list):
            try:
                idx = int(seg)
            except ValueError as exc:
                raise JsonPatchError(f"Invalid array index {seg!r}.") from exc
            if idx < 0 or idx >= len(cur):
                raise JsonPatchError(f"Array index {idx} out of range.")
            cur = cur[idx]
        else:
            raise JsonPatchError("Cannot traverse through non-container.")
    return cur, parts[-1]


def _apply_add(doc: Any, parts: list[str], value: Any) -> None:
    parent, last = _traverse_to_parent(doc, parts, create_missing=True)
    if isinstance(parent, dict):
        parent[last] = copy.deepcopy(value)
        return
    if isinstance(parent, list):
        if last == "-":
            parent.append(copy.deepcopy(value))
            return
        try:
            idx = int(last)
        except ValueError as exc:
            raise JsonPatchError(f"Invalid array index {last!r}.") from exc
        if idx < 0 or idx > len(parent):
            raise JsonPatchError(f"Add index {idx} out of range for array length {len(parent)}.")
        parent.insert(idx, copy.deepcopy(value))
        return
    raise JsonPatchError("add target parent must be an object or array.")


def _apply_remove(doc: Any, parts: list[str]) -> None:
    parent, last = _traverse_to_parent(doc, parts, create_missing=False)
    if isinstance(parent, dict):
        if last not in parent:
            raise JsonPatchError(f"Path does not exist: key {last!r}.")
        del parent[last]
        return
    if isinstance(parent, list):
        if last == "-":
            raise JsonPatchError("Cannot remove array index '-'.")
        idx = int(last)
        if idx < 0 or idx >= len(parent):
            raise JsonPatchError(f"Array index {idx} out of range.")
        del parent[idx]
        return
    raise JsonPatchError("remove target parent must be an object or array.")


def _apply_replace(doc: Any, parts: list[str], value: Any) -> None:
    parent, last = _traverse_to_parent(doc, parts, create_missing=False)
    if isinstance(parent, dict):
        if last not in parent:
            raise JsonPatchError(f"Path does not exist: key {last!r}.")
        parent[last] = copy.deepcopy(value)
        return
    if isinstance(parent, list):
        idx = int(last)
        if idx < 0 or idx >= len(parent):
            raise JsonPatchError(f"Array index {idx} out of range.")
        parent[idx] = copy.deepcopy(value)
        return
    raise JsonPatchError("replace target parent must be an object or array.")


def _apply_test(doc: Any, parts: list[str], value: Any) -> None:
    parent, last = _traverse_to_parent(doc, parts, create_missing=False)
    if isinstance(parent, dict):
        if last not in parent:
            raise JsonPatchError(f"test failed: key {last!r} missing.")
        if parent[last] != value:
            raise JsonPatchError("test failed: value mismatch.")
        return
    if isinstance(parent, list):
        idx = int(last)
        if idx < 0 or idx >= len(parent):
            raise JsonPatchError("test failed: index out of range.")
        if parent[idx] != value:
            raise JsonPatchError("test failed: value mismatch.")
        return
    raise JsonPatchError("test target parent must be an object or array.")


def _apply_one(doc: Any, op: dict[str, Any]) -> None:
    try:
        name = op["op"]
        path = op["path"]
    except KeyError as exc:
        raise JsonPatchError("Each patch operation requires 'op' and 'path'.") from exc
    if not isinstance(name, str) or not isinstance(path, str):
        raise JsonPatchError("'op' and 'path' must be strings.")

    parts = parse_json_pointer(path)
    if name == "add":
        if "value" not in op:
            raise JsonPatchError("'add' requires 'value'.")
        _apply_add(doc, parts, op["value"])
        return
    if name == "remove":
        _apply_remove(doc, parts)
        return
    if name == "replace":
        if "value" not in op:
            raise JsonPatchError("'replace' requires 'value'.")
        _apply_replace(doc, parts, op["value"])
        return
    if name == "test":
        if "value" not in op:
            raise JsonPatchError("'test' requires 'value'.")
        _apply_test(doc, parts, op["value"])
        return
    raise JsonPatchError(
        f"Unsupported operation {name!r}. Supported: add, remove, replace, test."
    )


def parse_patch_document(raw: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise JsonPatchError(f"Patch is not valid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise JsonPatchError("JSON Patch document must be a JSON array.")
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise JsonPatchError(f"Patch operation at index {i} must be an object.")
        extra = set(item) - {"op", "path", "value", "from"}
        if extra:
            raise JsonPatchError(
                f"Patch operation at index {i} has unknown keys: {sorted(extra)}."
            )
    return data  # type: ignore[return-value]


def apply_patch_document(doc: Any, operations: list[dict[str, Any]]) -> Any:
    """Return a deep copy of doc with operations applied in order."""

    work = copy.deepcopy(doc)
    for i, op in enumerate(operations):
        try:
            _apply_one(work, op)
        except JsonPatchError:
            raise
        except Exception as exc:
            raise JsonPatchError(f"Operation {i} failed: {exc}") from exc
    return work
