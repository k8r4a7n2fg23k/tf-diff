from tfdiff.model.diff import AttributeChange, Kind
from tfdiff.model.plan import Action, Change
from tfdiff.model.text import shortlist
from tfdiff.model.values import show_path

SHOWN = 5

# Terraform's action_reason values, in words a reviewer reads without the docs open
REASONS = {
    "replace_because_tainted": "the resource is tainted",
    "replace_because_cannot_update": "the provider cannot update it in place",
    "replace_by_request": "replacement was requested with -replace",
    "replace_by_triggers": "replace_triggered_by changed",
    "delete_because_no_resource_config": "the resource was removed from configuration",
    "delete_because_no_module": "its module was removed from configuration",
    "delete_because_wrong_repetition": "count / for_each was added or removed",
    "delete_because_count_index": "its count index is out of range now",
    "delete_because_each_key": "its for_each key is gone",
    "delete_because_no_move_target": "the moved block target does not exist",
    "read_because_config_unknown": "the data source config is unknown until apply",
    "read_because_dependency_pending": "a dependency has pending changes",
    "read_because_check_nested": "a check block reads it",
}


def why(change: Change, attributes: tuple[AttributeChange, ...]) -> tuple[str, ...]:
    """Plain-language reasons for the planned action, most decisive first."""
    lines: list[str] = []
    if change.reason:
        lines.append(REASONS.get(change.reason, change.reason))
    match change.action:
        case Action.CREATE:
            lines.append("new resource")
        case Action.REPLACE:
            forcing = [show_path(path) for path in change.replace_paths]
            if forcing:
                lines.append(f"{', '.join(forcing)} forces replacement")
            if change.actions[0] == "create":
                lines.append("create_before_destroy: the new object exists before the old one goes")
        case Action.FORGET:
            lines.append("removed from state only; the real object is left in place")
    changed = [
        attribute
        for attribute in attributes
        if attribute.kind is not Kind.UNKNOWN and not attribute.is_forcing
    ]
    if changed:
        names = shortlist([show_path(attribute.path) for attribute in changed], SHOWN)
        lines.append(f"{len(changed)} attribute(s) change: {names}")
    # one unknown block hides every old leaf under it: count the blocks, as terraform shows them
    after = dict(change.after)
    unknown = {
        next(
            (
                attribute.path[:depth]
                for depth in range(len(attribute.path))
                if attribute.path[:depth] in after
            ),
            attribute.path,
        )
        for attribute in attributes
        if attribute.kind is Kind.UNKNOWN
    }
    if unknown:
        lines.append(f"{len(unknown)} attribute(s) known only after apply")
    return tuple(lines)
