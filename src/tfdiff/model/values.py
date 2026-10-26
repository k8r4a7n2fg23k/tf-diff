import json
import math
import re
from dataclasses import dataclass
from typing import TypeAlias

Scalar: TypeAlias = str | int | float | bool
Path: TypeAlias = tuple[str | int, ...]


@dataclass(frozen=True, slots=True)
class Known:
    value: Scalar


@dataclass(frozen=True, slots=True)
class Unknown:
    """Known only after apply."""


@dataclass(frozen=True, slots=True)
class Null:
    """Null or absent: Terraform does not tell the two apart either."""


@dataclass(frozen=True, slots=True)
class Sensitive:
    """Redacted by the parser. Whether the value changed is all that survives of it."""

    is_changed: bool


Value: TypeAlias = Known | Unknown | Null | Sensitive

# Flattened attribute tree: one entry per scalar leaf, sorted by path. An Unknown or Sensitive
# entry stands for its whole subtree.
Attributes: TypeAlias = tuple[tuple[Path, Value], ...]

NULL = Null()
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
_NUMBER = re.compile(r"-?\d+(\.\d+)?([eE][-+]?\d+)?")


def is_blank(value: object) -> bool:
    """Null or a zero value, which mean the same for an attribute.

    SDKv2 providers store an unset attribute as "", false, 0 or [], and the plan shows it as null.
    """
    return value is None or value in ("", 0, [], {})


def path_key(path: Path) -> tuple[tuple[int, int, str], ...]:
    """Sort key: list indexes numerically, map keys as strings."""
    return tuple((0, part, "") if isinstance(part, int) else (1, 0, part) for part in path)


def value_at(attributes: Attributes, path: Path) -> Value:
    """Value at `path`, or the Unknown / Sensitive marker covering it."""
    for key, value in attributes:
        if key == path:
            return value
        if isinstance(value, Unknown | Sensitive) and key == path[: len(key)]:
            return value
    return NULL


def indexes(attributes: Attributes, prefix: Path) -> tuple[int, ...]:
    """List indexes present directly under `prefix`."""
    depth = len(prefix)
    found = {
        key[depth]
        for key, _ in attributes
        if len(key) > depth and key[:depth] == prefix and isinstance(key[depth], int)
    }
    return tuple(sorted(int(index) for index in found))


def number(value: Value) -> float | None:
    """Numeric reading of a Known value; providers send 10 or "10" for the same thing."""
    match value:
        case Known(value=bool()):
            return None
        case Known(value=int() | float() as figure):
            return _finite(figure)
        case Known(value=str(text)) if _NUMBER.fullmatch(text):
            return _finite(text)
    return None


def _finite(figure: float | str) -> float | None:
    # a 400-digit integer does not fit a float; no capacity or port is that large
    try:
        reading = float(figure)
    except OverflowError:
        return None
    return reading if math.isfinite(reading) else None


def flag(value: Value) -> bool | None:
    """Boolean reading of a Known value; "true" and true are the same to Terraform."""
    match value:
        case Known(value=bool(state)):
            return state
        case Known(value="true"):
            return True
        case Known(value="false"):
            return False
    return None


def show(value: Value) -> str:
    match value:
        case Known(value=scalar):
            return json.dumps(scalar, ensure_ascii=False)
        case Unknown():
            return "(known after apply)"
        case Sensitive():
            return "<sensitive>"
        case Null():
            return "null"


def show_path(path: Path) -> str:
    parts: list[str] = []
    for part in path:
        if isinstance(part, int):
            parts.append(f"[{part}]")
        elif _IDENTIFIER.fullmatch(part):
            parts.append(f".{part}" if parts else part)
        else:
            parts.append(f"[{json.dumps(part, ensure_ascii=False)}]")
    return "".join(parts)
