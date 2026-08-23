from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter

from tfdiff.model.errors import InputError


@dataclass(frozen=True, slots=True)
class Graph:
    """Resource dependencies. Edges point from a dependency to its dependents."""

    dependents: dict[str, frozenset[str]]
    dependencies: dict[str, frozenset[str]]


@dataclass(frozen=True, slots=True)
class BlastRadius:
    direct: tuple[str, ...]
    indirect: tuple[str, ...]

    @property
    def total(self) -> int:
        return len(self.direct) + len(self.indirect)


def build(nodes: Iterable[str], edges: Iterable[tuple[str, str]]) -> Graph:
    """Build from (dependency, dependent) pairs; raises InputError on a dangling edge or a cycle."""
    dependents: dict[str, set[str]] = {node: set() for node in nodes}
    dependencies: dict[str, set[str]] = {node: set() for node in dependents}
    for source, target in edges:
        if source not in dependents or target not in dependents:
            raise InputError(f"dependency {source} -> {target} names a resource not in the plan")
        dependents[source].add(target)
        dependencies[target].add(source)
    try:
        TopologicalSorter(dependencies).prepare()
    except CycleError as error:
        cycle: list[str] = error.args[1]
        raise InputError(f"dependency cycle: {' -> '.join(cycle)}") from None
    return Graph(
        dependents={node: frozenset(targets) for node, targets in sorted(dependents.items())},
        dependencies={node: frozenset(sources) for node, sources in sorted(dependencies.items())},
    )


def _walk(edges: dict[str, frozenset[str]], start: str) -> dict[str, int]:
    # breadth first, so the first visit of a node is its shortest distance
    distance: dict[str, int] = {}
    queue = deque([(start, 0)])
    while queue:
        node, depth = queue.popleft()
        for neighbour in edges[node]:
            # no cycles (build checks), so `start` is never its own neighbour
            if neighbour not in distance:
                distance[neighbour] = depth + 1
                queue.append((neighbour, depth + 1))
    return distance


def ancestors(graph: Graph, address: str) -> tuple[str, ...]:
    return tuple(sorted(_walk(graph.dependencies, address)))


def blast_radius(graph: Graph, address: str) -> BlastRadius:
    distance = _walk(graph.dependents, address)
    return BlastRadius(
        direct=tuple(sorted(node for node, depth in distance.items() if depth == 1)),
        indirect=tuple(sorted(node for node, depth in distance.items() if depth > 1)),
    )


def path(graph: Graph, source: str, target: str) -> tuple[str, ...]:
    """Shortest dependency chain from `source` to `target`, empty when there is none."""
    previous: dict[str, str] = {}
    queue = deque([source])
    while queue:
        node = queue.popleft()
        if node == target:
            chain = [node]
            while chain[-1] != source:
                chain.append(previous[chain[-1]])
            return tuple(reversed(chain))
        for neighbour in sorted(graph.dependents[node]):
            if neighbour not in previous:
                previous[neighbour] = node
                queue.append(neighbour)
    return ()
