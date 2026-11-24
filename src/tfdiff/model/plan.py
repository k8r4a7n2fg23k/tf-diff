from dataclasses import dataclass

from tfdiff.model.enums import StrEnum
from tfdiff.model.graph import Graph
from tfdiff.model.values import Attributes, Path


class Action(StrEnum):
    NOOP = "no-op"
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    REPLACE = "replace"
    FORGET = "forget"


# nothing assesses these; most of a large plan is no-op
QUIET = frozenset({Action.NOOP, Action.READ})


@dataclass(frozen=True, slots=True)
class Resource:
    address: str
    mode: str
    type: str
    provider: str


@dataclass(frozen=True, slots=True)
class Change:
    resource: Resource
    action: Action
    # raw order kept: ("create", "delete") is create_before_destroy, the derived Action loses it
    actions: tuple[str, ...]
    # a no-op or read change keeps only its tags: nothing else of it is assessed
    before: Attributes
    after: Attributes
    replace_paths: tuple[Path, ...]
    reason: str | None
    deposed: str | None
    # top-level attributes the configuration sets; None when the plan does not say
    configured: frozenset[str] | None

    @property
    def address(self) -> str:
        return self.resource.address

    @property
    def action_label(self) -> str:
        """`REPLACE (create, delete)`: the raw order is the create_before_destroy signal."""
        label = self.action.upper()
        return f"{label} ({', '.join(self.actions)})" if len(self.actions) > 1 else label

    @property
    def label(self) -> str:
        """Address for people: a deposed object is not the live one at the same address."""
        return f"{self.address} (deposed {self.deposed})" if self.deposed else self.address


@dataclass(frozen=True, slots=True)
class Plan:
    format_version: str
    terraform_version: str | None
    # "Terraform", "OpenTofu", or None when the plan does not say
    tool: str | None
    changes: tuple[Change, ...]
    graph: Graph
    warnings: tuple[str, ...]
