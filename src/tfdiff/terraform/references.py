"""Dependency edges from the plan's `configuration` block.

Terraform records references per expression and keeps an index only when it is a literal.
Each traversal of a resource is listed with every prefix of it: `aws_x.y["a"].id` comes out as
`aws_x.y["a"].id`, `aws_x.y["a"]`, `aws_x.y`; the whole resource (`aws_x.y`, `length(aws_x.y)`,
`aws_x.y[each.key]`, `aws_x.y[2 - count.index]`) as `aws_x.y` alone. Edges are resolved between
config addresses, then narrowed to instances only where that is certain:
- an expression that reaches a resource through literal indexes only depends on those instances
  (the bare address is listed no more often than the indexed ones);
- `for_each = aws_x.y` and nothing else hands each instance the dependency instance of its key,
  provided every key of the dependent exists on the dependency;
- a reference inside a module stays inside that module instance.
Anything else links every instance to every instance, the way Terraform orders them: an index
computed from `each.key` or `count.index` (the JSON cannot tell `x[each.key]` from
`x[var.peer[each.key]]`), `count`, `depends_on`, module outputs and variables, data sources the
plan does not list, and any data source as the dependent (Terraform defers its read when any
instance it names changes). Locals and `replace_triggered_by` are not in the JSON: a dependency
routed through them is invisible here.
"""

import re
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import TypeAlias

from pydantic import JsonValue

from tfdiff.model.errors import InputError

MAX_NESTING = 64
# a hop is one module output or variable; each recurses a few frames deep
MAX_HOPS = 128
IGNORED = frozenset({"local", "each", "count", "path", "terraform", "self"})

_INDEX = r'\[(?:"(?:[^"\\]|\\.)*"|[^\]]*)\]'
_INDEXES = re.compile(_INDEX)
_DATA = re.compile(r"data\.([^.\[]+)\.([^.\[]+)")
_MODULE = re.compile(rf"module\.([^.\[]+)(?:{_INDEX})?(?:\.([^.\[]+))?")
_VAR = re.compile(r"var\.([^.\[]+)")
_RESOURCE = re.compile(r"([^.\[]+)\.([^.\[]+)")
_DIRECT = re.compile(rf"((?:data\.)?[^.\[]+\.[^.\[]+)({_INDEX})?")
_INSTANCE = re.compile(
    rf"((?:module\.[^.\[]+(?:{_INDEX})?\.)*)(?:data\.)?[^.\[]+\.[^.\[]+({_INDEX})?"
)

Module: TypeAlias = tuple[str, ...]
Node: TypeAlias = dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class Configuration:
    # (dependency, dependent) pairs between instance addresses
    edges: list[tuple[str, str]]
    # config address -> top-level attributes the configuration sets
    configured: dict[str, frozenset[str]]
    # resources and module calls that read a local: what the local refers to is not in the JSON
    through_locals: list[str] = field(default_factory=list[str])


def read(configuration: JsonValue, nodes: Iterable[str]) -> Configuration:
    """Read dependency edges and configured attributes for the addresses in `nodes`."""
    resolver = _Resolver(_object(configuration, "configuration"))
    return Configuration(_edges(resolver, nodes), _configured(resolver), _through_locals(resolver))


@dataclass(frozen=True, slots=True)
class _Link:
    """A config-level edge and what the configuration says about the instances it joins."""

    dependency: str
    dependent: str
    # a reference within one module: it joins resources of the same module instance only
    local: bool = False
    # literal index of the dependency instance, as `["a"]` or `[0]`
    index: str | None = None
    # `for_each = <dependency>`: instance by instance, by key
    keyed: bool = False


def _edges(resolver: "_Resolver", nodes: Iterable[str]) -> list[tuple[str, str]]:
    instances: dict[str, list[str]] = {}
    for node in sorted(nodes):
        instances.setdefault(config_address(node), []).append(node)
    links = list(resolver.links())
    dependents: dict[str, set[str]] = {}
    for link in links:
        dependents.setdefault(link.dependency, set()).add(link.dependent)
    pairs: set[tuple[str, str]] = set()
    for link in links:
        if link.dependency not in instances:
            continue
        if link.dependent in instances:
            pairs.update(_instance_pairs(link, instances))
            continue
        # through data sources the plan does not list: no telling which instance feeds what
        for dependent in _through_absent(dependents, link.dependent, instances):
            pairs.update(
                (source, target)
                for source in instances[link.dependency]
                for target in instances[dependent]
            )
    return sorted(pairs)


def _instance_pairs(link: _Link, instances: dict[str, list[str]]) -> Iterator[tuple[str, str]]:
    sources = [(_scope(link, source), source) for source in instances[link.dependency]]
    targets = [(_scope(link, target), target) for target in instances[link.dependent]]
    # a dependent key missing on the dependency: `aws_x.y[upper(each.key)]`, not the key itself
    keyed = link.keyed and {key for key, _ in targets} <= {key for key, _ in sources}
    scopes: dict[str, list[tuple[str, str]]] = {}
    for (scope, index), source in sources:
        scopes.setdefault(scope, []).append((index, source))
    for (module, own), target in targets:
        candidates = scopes.get(module, [])
        if link.index is not None:
            chosen = [source for index, source in candidates if index == link.index]
        elif keyed:
            chosen = [source for index, source in candidates if index == own]
        else:
            chosen = []
        # nothing narrower known, or a literal index with no such instance: the whole resource
        yield from ((source, target) for source in chosen or [source for _, source in candidates])


def _scope(link: _Link, address: str) -> tuple[str, str]:
    """Split an instance address into the module instance the link stays in and its own index."""
    found = _INSTANCE.fullmatch(address)
    module, index = (found[1], found[2] or "") if found else ("", "")
    return (module if link.local else "", index)


def _through_absent(
    dependents: dict[str, set[str]], start: str, present: dict[str, list[str]]
) -> set[str]:
    """Dependents in the plan of `start`, which the plan does not list, through others like it.

    Terraform leaves data sources it reads during planning out of `resource_changes`, yet
    `aws_vpc.main -> data.aws_subnets.x -> aws_instance.app` still ties the instance to the VPC.
    """
    found: set[str] = set()
    seen = {start}
    stack = [start]
    while stack:
        for dependent in dependents.get(stack.pop(), ()):
            if dependent in seen:
                continue
            seen.add(dependent)
            if dependent in present:
                found.add(dependent)
            else:
                stack.append(dependent)
    return found


def _configured(resolver: "_Resolver") -> dict[str, frozenset[str]]:
    # an attribute missing here is computed or defaulted by the provider: on a replace Terraform
    # marks every such attribute unknown, so its unknown says nothing about what the author wants
    return {
        address: frozenset(_object(resource.get("expressions") or {}, f"{address}.expressions"))
        for module in resolver.resources.values()
        for address, resource in module.items()
    }


def _through_locals(resolver: "_Resolver") -> list[str]:
    users = [
        address
        for module in resolver.resources.values()
        for address, resource in module.items()
        if _reads_local(resource)
    ]
    calls = [
        "".join(f"module.{name}." for name in path).removesuffix(".")
        for path, call in resolver.calls.items()
        if _reads_local(call)
    ]
    return sorted([*users, *calls])


def _reads_local(node: Node) -> bool:
    return any(
        ref.startswith("local.")
        for key in ("expressions", "count_expression", "for_each_expression")
        for ref in _references(node.get(key))
    )


def config_address(address: str) -> str:
    """`module.a["x"].aws_y.z[0]` -> `module.a.aws_y.z`."""
    return _INDEXES.sub("", address)


def _references(expression: JsonValue) -> Iterator[str]:
    for refs in _expressions(expression):
        yield from refs


def _expressions(expression: JsonValue) -> Iterator[list[str]]:
    """Yield the `references` of each expression, nested blocks included."""
    stack: list[tuple[JsonValue, int]] = [(expression, 0)]
    while stack:
        node, depth = stack.pop()
        if depth > MAX_NESTING:
            raise InputError(f"configuration expressions nested deeper than {MAX_NESTING}")
        if isinstance(node, dict):
            found = node.get("references")
            if isinstance(found, list):
                yield [ref for ref in found if isinstance(ref, str)]
            stack.extend((child, depth + 1) for key, child in node.items() if key != "references")
        elif isinstance(node, list):
            stack.extend((child, depth + 1) for child in node)


def _specific(refs: list[str]) -> list[str]:
    """Drop `module.x` when `module.x.out` is also listed: TF names both, the bare one is noise."""
    return [
        ref for ref in refs if not any(other.startswith((f"{ref}.", f"{ref}[")) for other in refs)
    ]


def _object(node: JsonValue, where: str) -> Node:
    if not isinstance(node, dict):
        raise InputError(f"{where}: expected an object")
    return node


def _objects(node: JsonValue, where: str) -> list[Node]:
    if node is None:
        return []
    if not isinstance(node, list):
        raise InputError(f"{where}: expected a list")
    return [_object(child, where) for child in node]


def _text(node: Node, key: str, where: str) -> str:
    value = node.get(key)
    if not isinstance(value, str):
        raise InputError(f"{where}.{key}: expected a string")
    return value


def _prefix(module: Module) -> str:
    return "".join(f"module.{name}." for name in module)


class _Resolver:
    def __init__(self, configuration: Node) -> None:
        self.modules: dict[Module, Node] = {}
        self.calls: dict[Module, Node] = {}
        self.resources: dict[Module, dict[str, Node]] = {}
        self._memo: dict[tuple[Module, str], frozenset[str]] = {}
        self._active: set[tuple[Module, str]] = set()
        root = configuration.get("root_module")
        self._collect((), _object(root, "configuration.root_module") if root is not None else {})

    def _collect(self, module: Module, node: Node) -> None:
        if len(module) > MAX_NESTING:
            raise InputError(f"modules nested deeper than {MAX_NESTING}")
        self.modules[module] = node
        self.resources[module] = self._index(module, node)
        calls = node.get("module_calls")
        for name, call in sorted(_object(calls, "module_calls").items() if calls else ()):
            child = (*module, name)
            where = f"{_prefix(module)}module_calls.{name}"
            self.calls[child] = _object(call, where)
            inner = self.calls[child].get("module")
            self._collect(child, _object(inner, f"{where}.module") if inner is not None else {})

    @staticmethod
    def _index(module: Module, node: Node) -> dict[str, Node]:
        found: dict[str, Node] = {}
        where = f"{_prefix(module)}resources"
        for resource in _objects(node.get("resources"), where):
            kind = _text(resource, "type", where)
            name = _text(resource, "name", where)
            data = "data." if _text(resource, "mode", where) == "data" else ""
            found[f"{_prefix(module)}{data}{kind}.{name}"] = resource
        return found

    def links(self) -> Iterator[_Link]:
        for module in sorted(self.modules):
            inherited = self._inherited(module)
            for address, resource in sorted(self.resources[module].items()):
                yield from (_Link(dependency, address) for dependency in sorted(inherited))
                narrow = resource.get("mode") != "data"
                for refs in _expressions(resource.get("expressions")):
                    yield from self._expression(module, address, refs, narrow=narrow)
                yield from self._for_each(module, address, resource, narrow=narrow)
                for refs in _expressions(resource.get("count_expression")):
                    yield from self._expression(module, address, refs, narrow=False)
                yield from self._expression(
                    module, address, self._depends_on(resource), narrow=False
                )

    def _for_each(
        self, module: Module, address: str, resource: Node, *, narrow: bool
    ) -> Iterator[_Link]:
        refs = list(_references(resource.get("for_each_expression")))
        match refs:
            case [ref] if narrow and self._direct(module, ref) == (ref, None):
                yield _Link(f"{_prefix(module)}{ref}", address, local=True, keyed=True)
            case _:
                yield from self._expression(module, address, refs, narrow=False)

    def _expression(
        self, module: Module, address: str, refs: list[str], *, narrow: bool
    ) -> Iterator[_Link]:
        """Links of one expression; narrowed to literal instances when it names nothing else."""
        bare: Counter[str] = Counter()
        indexes: dict[str, list[str]] = {}
        others: list[str] = []
        for ref in refs:
            match self._direct(module, ref):
                case (str(dependency), None) if dependency == ref:
                    bare[dependency] += 1
                case (str(dependency), str(index)) if f"{dependency}{index}" == ref:
                    indexes.setdefault(dependency, []).append(index)
                case (str(dependency), _):
                    # `x.id`, `x["a"].id`: Terraform lists `x` / `x["a"]` next to it
                    bare.setdefault(dependency, 0)
                case _:
                    others.append(ref)
        for local in sorted(bare.keys() | indexes.keys()):
            dependency = f"{_prefix(module)}{local}"
            found = indexes.get(local, [])
            if narrow and found and bare[local] <= len(found):
                yield from (
                    _Link(dependency, address, local=True, index=index)
                    for index in sorted(set(found))
                )
            else:
                yield _Link(dependency, address, local=True)
        for ref in _specific(others):
            yield from (
                _Link(dependency, address) for dependency in sorted(self._resolve(module, ref))
            )

    def _direct(self, module: Module, ref: str) -> tuple[str, str | None] | None:
        """`(aws_x.y, ["a"])` for a reference to a resource of this module, else None."""
        direct = _DIRECT.match(ref)
        if not direct or ref.split(".", 1)[0] in {*IGNORED, "module", "var"}:
            return None
        if f"{_prefix(module)}{direct[1]}" not in self.resources[module]:
            return None
        return direct[1], direct[2]

    def _depends_on(self, node: Node) -> list[str]:
        found = node.get("depends_on")
        if found is None:
            return []
        refs = [ref for ref in found if isinstance(ref, str)] if isinstance(found, list) else []
        if not isinstance(found, list) or len(refs) != len(found):
            raise InputError("configuration depends_on: expected a list of strings")
        return refs

    def _inherited(self, module: Module) -> frozenset[str]:
        """Dependencies a module call's depends_on / count / for_each put on all its resources."""
        found: set[str] = set()
        for depth in range(1, len(module) + 1):
            call = self.calls[module[:depth]]
            refs = [
                *_references(call.get("count_expression")),
                *_references(call.get("for_each_expression")),
                *self._depends_on(call),
            ]
            found.update(*(self._resolve(module[: depth - 1], ref) for ref in refs))
        return frozenset(found)

    def _resolve(self, module: Module, ref: str) -> frozenset[str]:
        key = (module, ref)
        if key in self._memo:
            return self._memo[key]
        if key in self._active:
            return frozenset()
        if len(self._active) > MAX_HOPS:
            raise InputError(f"references chained through more than {MAX_HOPS} module values")
        self._active.add(key)
        resolved = self._lookup(module, ref)
        self._active.discard(key)
        self._memo[key] = resolved
        return resolved

    def _lookup(self, module: Module, ref: str) -> frozenset[str]:
        head = ref.split(".", 1)[0]
        if head in IGNORED:
            return frozenset()
        if head == "data" and (found := _DATA.match(ref)):
            return self._existing(module, f"data.{found[1]}.{found[2]}")
        if head == "module" and (found := _MODULE.match(ref)):
            return self._output(module, found[1], found[2])
        if head == "var" and (found := _VAR.match(ref)):
            return self._variable(module, found[1])
        if found := _RESOURCE.match(ref):
            return self._existing(module, f"{found[1]}.{found[2]}")
        return frozenset()

    def _existing(self, module: Module, local: str) -> frozenset[str]:
        address = f"{_prefix(module)}{local}"
        return frozenset({address}) if address in self.resources[module] else frozenset()

    def _output(self, module: Module, call: str, output: str | None) -> frozenset[str]:
        child = (*module, call)
        if child not in self.modules:
            return frozenset()
        outputs = self.modules[child].get("outputs")
        node = _object(outputs, "outputs").get(output or "") if outputs is not None else None
        if node is None:
            return self._subtree(child)
        where = f"{_prefix(child)}outputs.{output}"
        expression = _object(node, where)
        refs = [*_references(expression.get("expression")), *self._depends_on(expression)]
        return frozenset().union(*(self._resolve(child, ref) for ref in _specific(refs)))

    def _variable(self, module: Module, name: str) -> frozenset[str]:
        if not module:
            return frozenset()
        expressions = self.calls[module].get("expressions")
        expression = _object(expressions, "expressions").get(name) if expressions else None
        refs = list(_references(expression))
        return frozenset().union(*(self._resolve(module[:-1], ref) for ref in _specific(refs)))

    def _subtree(self, module: Module) -> frozenset[str]:
        return frozenset(
            address
            for path in self.modules
            if path[: len(module)] == module
            for address in self.resources[path]
        )
