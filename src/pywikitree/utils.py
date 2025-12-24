from __future__ import annotations

from typing import Any, Mapping, Sequence


def join_csv(value: str | Sequence[str] | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return ",".join(value)


def to_int_bool(value: bool | None) -> int | None:
    if value is None:
        return None
    return int(value)


def compact_params(params: Mapping[str, Any]) -> dict[str, Any]:
    """Drop None values and normalize booleans to ints.

    WikiTree API examples commonly use 1/0 flags.
    """

    cleaned: dict[str, Any] = {}
    for key, val in params.items():
        if val is None:
            continue
        if isinstance(val, bool):
            cleaned[key] = int(val)
        else:
            cleaned[key] = val
    return cleaned


def ensure_comma_delimited(value: str | Sequence[str]) -> str:
    if isinstance(value, str):
        return value
    return ",".join(value)


def ensure_ignore_ids(value: None | str | int | Sequence[int]) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    return ",".join(str(v) for v in value)


def is_success_status(value: Any) -> bool:
    """Interpret the heterogeneous ``status`` field used across endpoints."""

    if value is None:
        return True
    if value == 0:
        return True
    if value == "":
        return True
    return False


def extract_status_errors(payload: Any) -> list[str]:
    """Collect human-readable status errors from a WikiTree API response.

    Responses are often a list with a single dict, but not always.
    """

    errors: list[str] = []

    def walk(obj: Any, depth: int) -> None:
        if depth <= 0:
            return
        if isinstance(obj, dict):
            if "status" in obj and not is_success_status(obj.get("status")):
                errors.append(str(obj.get("status")))
            for val in obj.values():
                walk(val, depth - 1)
        elif isinstance(obj, list):
            for item in obj:
                walk(item, depth - 1)

    walk(payload, depth=12)
    return errors
