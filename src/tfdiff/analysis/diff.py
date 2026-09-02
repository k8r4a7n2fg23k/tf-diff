from tfdiff.model.diff import AttributeChange, Kind
from tfdiff.model.plan import Action, Change
from tfdiff.model.values import (
    NULL,
    Known,
    Null,
    Path,
    Scalar,
    Sensitive,
    Unknown,
    Value,
    flag,
    is_blank,
    number,
    path_key,
)

DIFFED = frozenset({Action.UPDATE, Action.REPLACE})


def diff(change: Change) -> tuple[AttributeChange, ...]:
    """Attribute-level changes of an update or replace; empty for every other action."""
    if change.action not in DIFFED:
        return ()
    before, after = dict(change.before), dict(change.after)
    parents = _parents(before) | _parents(after)
    found: list[AttributeChange] = []
    for path in sorted({*before, *after}, key=path_key):
        # a leaf on one side with a subtree on the other (null -> map, map -> unknown) is
        # diffed through the subtree's leaves, each against the covering value
        if path in parents:
            continue
        old, new = _at(before, path), _at(after, path)
        kind = classify(old, new)
        if kind is not None:
            found.append(
                AttributeChange(path, kind, old, new, _is_forcing(path, change.replace_paths))
            )
    return tuple(found)


def classify(before: Value, after: Value) -> Kind | None:
    match before, after:
        case _, Unknown():
            return Kind.UNKNOWN
        case (Sensitive() as marker, _) | (_, Sensitive() as marker):
            return Kind.SENSITIVE if marker.is_changed else None
        case Known(value=old), Known(value=new):
            return None if same(old, new) else Kind.MODIFIED
        case Null(), Known(value=new):
            return None if is_blank(new) else Kind.ADDED
        case Known(value=old), Null():
            return None if is_blank(old) else Kind.REMOVED
    return None


def same(before: Scalar, after: Scalar) -> bool:
    """Equal up to provider type noise: "10" == 10, "true" == true, but 1 != true."""
    if type(before) is type(after):
        return before == after
    if isinstance(before, bool) or isinstance(after, bool):
        old, new = flag(Known(before)), flag(Known(after))
        return old is not None and old == new
    old_number, new_number = number(Known(before)), number(Known(after))
    return old_number is not None and old_number == new_number


def _is_forcing(path: Path, replace_paths: tuple[Path, ...]) -> bool:
    return any(path[: len(rp)] == rp or rp[: len(path)] == path for rp in replace_paths)


def _parents(leaves: dict[Path, Value]) -> set[Path]:
    return {path[:depth] for path in leaves for depth in range(len(path))}


def _at(leaves: dict[Path, Value], path: Path) -> Value:
    if path in leaves:
        return leaves[path]
    # the parser never yields the empty path, so a mutant that starts at depth 0 is equivalent
    for depth in reversed(range(1, len(path))):  # pragma: no mutate
        marker = leaves.get(path[:depth])
        if marker is not None:
            return marker
    return NULL
