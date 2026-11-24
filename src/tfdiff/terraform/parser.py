"""`terraform show -json` plan -> model.Plan. The only module that knows Terraform's JSON shape."""

import gc
import json
import math
import re
from collections.abc import Iterator
from itertools import pairwise

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from tfdiff.model.errors import SHOWN_ERRORS, CompatibilityError, InputError
from tfdiff.model.graph import build
from tfdiff.model.plan import QUIET, Action, Change, Plan, Resource
from tfdiff.model.text import shortlist
from tfdiff.model.values import (
    Attributes,
    Known,
    Null,
    Path,
    Sensitive,
    Unknown,
    Value,
    is_blank,
    path_key,
    show_path,
)
from tfdiff.terraform.references import MAX_NESTING, Configuration, config_address, read

MAX_SIZE = 512 * 1024 * 1024
SUPPORTED_FORMAT = (1, 2)
# below these keys a validation error location is made of plan data (map keys of a secret, say)
VALUE_KEYS = frozenset(
    {"before", "after", "after_unknown", "before_sensitive", "after_sensitive", "configuration"}
)

# TF marks sensitivity per provider schema and loses it on copies (terraform_data.output keeps
# the password in clear), so names are a second line of defence
SECRET_NAME = re.compile(
    r"password|passwd|passphrase|(^|_)pass$|secret|token|private_key|api_?key|access_key"
    r"|credential|connection_string",
    re.IGNORECASE,
)

ACTIONS: dict[tuple[str, ...], Action] = {
    ("no-op",): Action.NOOP,
    ("create",): Action.CREATE,
    ("read",): Action.READ,
    ("update",): Action.UPDATE,
    ("delete",): Action.DELETE,
    ("delete", "create"): Action.REPLACE,
    ("create", "delete"): Action.REPLACE,
    ("forget",): Action.FORGET,
}
# addresses a warning names before it says how many more
EXAMPLES = 3
# what a quiet change still has to say: the environment the plan is in
TAG_KEYS = ("tags", "tags_all")


class _Tolerant(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class RawDiff(_Tolerant):
    actions: list[str]
    before: JsonValue = None
    after: JsonValue = None
    after_unknown: JsonValue = None
    before_sensitive: JsonValue = None
    after_sensitive: JsonValue = None
    replace_paths: list[list[str | int]] | None = None


class RawResourceChange(_Tolerant):
    address: str = Field(min_length=1)
    mode: str
    type: str = Field(min_length=1)
    provider_name: str
    deposed: str | None = None
    action_reason: str | None = None
    change: RawDiff


class RawPlan(_Tolerant):
    format_version: str
    terraform_version: str | None = None
    errored: bool = False
    complete: bool = True
    resource_changes: list[RawResourceChange] = []
    configuration: JsonValue = None


def parse(text: str) -> Plan:
    """Parse plan JSON; raises InputError (or CompatibilityError) and nothing else on bad input."""
    # millions of new objects and no cycles among them: collection passes free nothing and took
    # a third of the time on a 10k-resource plan
    collecting = gc.isenabled()
    gc.disable()
    try:
        return _parse(text)
    finally:
        if collecting:
            gc.enable()


def _parse(text: str) -> Plan:
    if len(text) > MAX_SIZE:
        raise InputError(f"plan is longer than {MAX_SIZE} characters")
    try:
        document = json.loads(text, parse_constant=_not_finite, parse_float=_finite)
    except json.JSONDecodeError as error:
        raise InputError(f"not JSON: line {error.lineno} column {error.colno}") from None
    except RecursionError:
        raise InputError("JSON nesting is too deep") from None
    except ValueError:
        # Python refuses to convert integer literals over 4300 digits
        raise InputError("plan JSON holds a number with too many digits") from None
    if not isinstance(document, dict):
        raise InputError("plan JSON must be an object")
    version = document.get("format_version")
    if not isinstance(version, str):
        raise InputError("format_version: missing or not a string")
    # before validation: a newer major format fails on its version, not on a renamed field
    minor = _minor(version)
    raw = _validate(document)
    warnings = _check_format(raw, minor)
    nodes = {resource.address for resource in raw.resource_changes}
    if raw.configuration is None:
        warnings.append("plan has no configuration: dependency graph is empty")
        configuration = Configuration([], {})
    else:
        configuration = read(raw.configuration, nodes)
        if users := configuration.through_locals:
            warnings.append(
                f"{len(users)} resource(s) or module call(s) read locals "
                f"({shortlist(users, EXAMPLES)}): the plan JSON "
                "does not say what a local refers to, so dependencies through them are missing "
                "and blast radius may be low"
            )
    changes = tuple(
        sorted(
            (_change(resource, configuration.configured) for resource in raw.resource_changes),
            key=_identity,
        )
    )
    _check_unique(changes)
    graph = build(nodes, configuration.edges)
    return Plan(
        format_version=raw.format_version,
        terraform_version=raw.terraform_version,
        tool=_tool(changes),
        changes=changes,
        graph=graph,
        warnings=tuple(warnings),
    )


def _tool(changes: tuple[Change, ...]) -> str | None:
    """Which binary wrote the plan. The JSON never says; the provider registry does.

    OpenTofu resolves `hashicorp/aws` to its own registry, Terraform to registry.terraform.io.
    Versions overlap (both ship 1.6-1.13), and built-in providers like terraform_data are
    `terraform.io/builtin/...` in both, so a plan of those alone stays unknown.
    """
    hosts = {change.resource.provider.split("/", 1)[0] for change in changes}
    if "registry.opentofu.org" in hosts:
        return "OpenTofu"
    if "registry.terraform.io" in hosts:
        return "Terraform"
    return None


def _finite(text: str) -> float:
    number = float(text)
    if not math.isfinite(number):
        raise InputError("plan JSON holds a number too large for a float")
    return number


def _not_finite(text: str) -> float:
    raise InputError(f"plan JSON holds {text}, which is not valid JSON")


def _validate(document: dict[str, object]) -> RawPlan:
    try:
        return RawPlan.model_validate(document)
    except ValidationError as error:
        # include_input=False: the offending value may be a secret; so may keys deeper in loc
        problems = dict.fromkeys(
            f"{_location(issue['loc'])}: {issue['msg']}"
            for issue in error.errors(include_input=False, include_url=False)
        )
        raise InputError("invalid plan JSON: " + "; ".join(list(problems)[:SHOWN_ERRORS])) from None
    except RecursionError:
        raise InputError("JSON nesting is too deep") from None


def _location(loc: tuple[int | str, ...]) -> str:
    parts: list[str] = []
    for part in loc:
        parts.append(str(part))
        if part in VALUE_KEYS:
            break
    return ".".join(parts)


def _minor(version: str) -> int:
    match = re.fullmatch(r"(\d+)\.(\d+)", version)
    if match is None:
        raise CompatibilityError("format_version is not MAJOR.MINOR")
    if int(match[1]) != SUPPORTED_FORMAT[0]:
        raise CompatibilityError(
            f"plan format {version} is not supported, expected {SUPPORTED_FORMAT[0]}.x"
        )
    return int(match[2])


def _check_format(raw: RawPlan, minor: int) -> list[str]:
    if raw.errored:
        raise InputError("terraform reported errors while planning: the plan is not usable")
    warnings: list[str] = []
    if minor > SUPPORTED_FORMAT[1]:
        warnings.append(
            f"plan format {raw.format_version} is newer than tested {SUPPORTED_FORMAT[0]}."
            f"{SUPPORTED_FORMAT[1]}: unknown fields are ignored"
        )
    if not raw.complete:
        warnings.append("plan is incomplete (deferred changes): more changes follow next run")
    return warnings


def _identity(change: Change) -> tuple[str, str]:
    return (change.address, change.deposed or "")


def _check_unique(changes: tuple[Change, ...]) -> None:
    for previous, current in pairwise(changes):
        if _identity(previous) == _identity(current):
            raise InputError(f"{current.address}: listed twice in resource_changes")


def _change(raw: RawResourceChange, declared: dict[str, frozenset[str]]) -> Change:
    actions = tuple(raw.change.actions)
    if actions not in ACTIONS:
        raise CompatibilityError(f"{raw.address}: unsupported action list {list(actions)}")
    action = ACTIONS[actions]
    before, after = raw.change.before, raw.change.after
    unknown = raw.change.after_unknown
    if action in QUIET:
        # only known tags are read from them
        before, after = _tags(raw.address, before), _tags(raw.address, after)
        unknown = None
    return Change(
        resource=Resource(
            address=raw.address,
            mode=raw.mode,
            type=raw.type,
            provider=raw.provider_name,
        ),
        action=action,
        actions=actions,
        before=_attributes(raw.address, before, None, raw.change.before_sensitive, after),
        after=_attributes(raw.address, after, unknown, raw.change.after_sensitive, before),
        replace_paths=tuple(
            sorted((tuple(path) for path in raw.change.replace_paths or ()), key=path_key)
        ),
        reason=raw.action_reason,
        deposed=raw.deposed,
        configured=declared.get(config_address(raw.address)),
    )


def _tags(address: str, value: JsonValue) -> JsonValue:
    if not isinstance(value, dict | None):
        raise InputError(f"{address}: before/after must be an object or null")
    return value and {key: value[key] for key in TAG_KEYS if key in value}


def _attributes(
    address: str,
    value: JsonValue,
    unknown: JsonValue,
    sensitive: JsonValue,
    other: JsonValue,
) -> Attributes:
    if not isinstance(value, dict | None):
        raise InputError(f"{address}: before/after must be an object or null")
    # a mask of `true` on the whole object covers each top-level attribute
    keys = sorted({*_keys(value), *_keys(other)})
    unknown = dict.fromkeys(keys, True) if unknown is True else unknown
    sensitive = dict.fromkeys(keys, True) if sensitive is True else sensitive
    leaves = dict(_flatten(address, value, unknown, sensitive, other, ()))
    return tuple(sorted(leaves.items(), key=lambda entry: path_key(entry[0])))


def _flatten(  # noqa: PLR0913, PLR0917  - the value and its three masks walk in lockstep, splitting them hides that
    address: str,
    value: JsonValue,
    unknown: JsonValue,
    sensitive: JsonValue,
    other: JsonValue,
    path: Path,
) -> Iterator[tuple[Path, Value]]:
    if len(path) > MAX_NESTING:
        raise InputError(
            f"{address}: attributes nested deeper than {MAX_NESTING} at {show_path(path)}"
        )
    if unknown is True:
        # nothing to redact: the value does not exist yet
        yield path, Unknown()
        return
    if sensitive is True or _is_secret(path):
        # only the comparison survives; the value itself stops here
        yield (
            path,
            Sensitive(is_changed=value != other and not (is_blank(value) and is_blank(other))),
        )
        return
    keys: list[str | int]
    if isinstance(value, dict) or isinstance(unknown, dict):
        keys = sorted({*_keys(value), *_keys(unknown)}, key=str)
    elif isinstance(value, list) or isinstance(unknown, list):
        keys = list(range(max(len(_items(value)), len(_items(unknown)))))
    elif value is None:
        if path:
            yield path, Null()
        return
    else:
        yield path, Known(value)
        return
    for key in keys:
        yield from _flatten(
            address,
            _child(value, key),
            _child(unknown, key),
            _child(sensitive, key),
            _child(other, key),
            (*path, key),
        )


def _is_secret(path: Path) -> bool:
    return bool(path) and isinstance(path[-1], str) and SECRET_NAME.search(path[-1]) is not None


def _keys(node: JsonValue) -> list[str]:
    return list(node) if isinstance(node, dict) else []


def _items(node: JsonValue) -> list[JsonValue]:
    return node if isinstance(node, list) else []


def _child(node: JsonValue, key: str | int) -> JsonValue:
    if isinstance(node, dict) and isinstance(key, str):
        return node.get(key)
    if isinstance(node, list) and isinstance(key, int) and key < len(node):
        return node[key]
    return None
