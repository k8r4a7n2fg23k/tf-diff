"""Builders for synthetic plans. They go through the real parser, so tests see what users see."""

import json
import re
from pathlib import Path
from typing import TypeAlias

from tfdiff.analysis.diff import diff
from tfdiff.model.findings import Finding
from tfdiff.model.graph import BlastRadius
from tfdiff.model.plan import Change
from tfdiff.model.settings import Settings
from tfdiff.rules.rule import Context
from tfdiff.terraform.parser import parse

ROOT = Path(__file__).parent
GOLDEN = ROOT / "golden"
NO_BLAST = BlastRadius((), ())

Raw: TypeAlias = dict[str, object]


def resource_change(  # noqa: PLR0913  - mirrors the fields of a resource change
    address: str,
    *,
    actions: tuple[str, ...] = ("update",),
    before: object = None,
    after: object = None,
    after_unknown: object = None,
    before_sensitive: object = None,
    after_sensitive: object = None,
    replace_paths: list[list[str | int]] | None = None,
    reason: str | None = None,
    mode: str = "managed",
    deposed: str | None = None,
) -> Raw:
    change: Raw = {
        "actions": list(actions),
        "before": before,
        "after": after,
        "after_unknown": after_unknown if after_unknown is not None else {},
        # terraform writes false for the mask of a missing side
        "before_sensitive": _mask(before_sensitive, before),
        "after_sensitive": _mask(after_sensitive, after),
    }
    if replace_paths is not None:
        change["replace_paths"] = [list(path) for path in replace_paths]
    raw: Raw = {
        "address": address,
        "mode": mode,
        "type": _type_and_name(address)[0],
        "provider_name": "registry.terraform.io/hashicorp/aws",
        "change": change,
    }
    if reason is not None:
        raw["action_reason"] = reason
    if deposed is not None:
        raw["deposed"] = deposed
    return raw


def _type_and_name(address: str) -> tuple[str, str]:
    """`module.a["x"].aws_y.z[0]` -> ("aws_y", "z")."""
    kind, name = re.sub(r"\[[^\]]*\]", "", address).split(".")[-2:]
    return kind, name


def _mask(mask: object, side: object) -> object:
    if mask is not None:
        return mask
    return {} if side is not None else False


def plan_text(*changes: Raw, configuration: object = None, **extra: object) -> str:
    document: Raw = {
        "format_version": "1.2",
        "terraform_version": "1.16.0",
        "resource_changes": list(changes),
        **extra,
    }
    if configuration is not None:
        document["configuration"] = configuration
    return json.dumps(document)


def configuration(raw: Raw, *attributes: str) -> Raw:
    """Root-module configuration that sets exactly `attributes` on the resource in `raw`."""
    data = "data." if raw["mode"] == "data" else ""
    kind, name = _type_and_name(str(raw["address"]))
    resource: Raw = {
        "address": f"{data}{kind}.{name}",
        "mode": raw["mode"],
        "type": kind,
        "name": name,
        "expressions": {name: {"constant_value": None} for name in attributes},
    }
    return {"root_module": {"resources": [resource]}}


def evidence(found: Finding) -> dict[str, str]:
    """Evidence of a finding by label."""
    return {item.label: item.text for item in found.evidence}


def one(raw: Raw, configuration: Raw | None = None) -> Change:
    (change,) = parse(plan_text(raw, configuration=configuration)).changes
    return change


def context(
    raw: Raw,
    *,
    environment: str | None = None,
    blast: BlastRadius = NO_BLAST,
    settings: Settings | None = None,
    configuration: Raw | None = None,
) -> Context:
    change = one(raw, configuration)
    return Context(
        change=change,
        attributes=diff(change),
        environment=environment,
        blast=blast,
        settings=settings or Settings(),
    )
