from random import Random

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tfdiff.model.errors import InputError
from tfdiff.model.graph import ancestors, blast_radius, build, path

# RDS -> API -> (Deployment -> HPA), RDS -> Worker, RDS -> Analytics
EDGES = [
    ("rds", "api"),
    ("rds", "worker"),
    ("rds", "analytics"),
    ("api", "deployment"),
    ("deployment", "hpa"),
]
NODES = ["rds", "api", "worker", "analytics", "deployment", "hpa", "lonely"]


def test_blast_radius_splits_direct_and_indirect() -> None:
    radius = blast_radius(build(NODES, EDGES), "rds")
    assert radius.direct == ("analytics", "api", "worker")
    assert radius.indirect == ("deployment", "hpa")


def test_queries_on_hand_checked_graph() -> None:
    graph = build(NODES, EDGES)
    assert ancestors(graph, "hpa") == ("api", "deployment", "rds")
    assert blast_radius(graph, "lonely").total == 0
    assert path(graph, "rds", "hpa") == ("rds", "api", "deployment", "hpa")
    assert path(graph, "worker", "rds") == ()


def test_cycle_names_the_loop() -> None:
    with pytest.raises(InputError, match=r"dependency cycle: .*a.*b"):
        build(["a", "b", "c"], [("a", "b"), ("b", "a"), ("b", "c")])


def test_dangling_edge_is_input_error() -> None:
    with pytest.raises(InputError, match="ghost"):
        build(["a"], [("a", "ghost")])


@st.composite
def dags(draw: st.DrawFn) -> tuple[list[str], list[tuple[str, str]]]:
    size = draw(st.integers(1, 12))
    nodes = [f"n{i}" for i in range(size)]
    pairs = [(i, j) for i in range(size) for j in range(i + 1, size)]
    chosen = draw(st.lists(st.sampled_from(pairs), max_size=30) if pairs else st.just([]))
    order = draw(st.permutations(nodes))
    return order, [(nodes[i], nodes[j]) for i, j in chosen]


@given(dags())
def test_dependents_and_dependencies_mirror(dag: tuple[list[str], list[tuple[str, str]]]) -> None:
    nodes, edges = dag
    graph = build(nodes, edges)
    for source, targets in graph.dependents.items():
        assert all(source in graph.dependencies[target] for target in targets)


@given(dags())
def test_descendants_are_transitive(dag: tuple[list[str], list[tuple[str, str]]]) -> None:
    nodes, edges = dag
    graph = build(nodes, edges)

    def below(node: str) -> set[str]:
        radius = blast_radius(graph, node)
        return {*radius.direct, *radius.indirect}

    for node in nodes:
        assert node not in below(node)
        for child in below(node):
            assert below(child) <= below(node)
        assert set(blast_radius(graph, node).direct) == graph.dependents[node]


@given(dags(), st.randoms())
def test_input_order_does_not_change_the_graph(
    dag: tuple[list[str], list[tuple[str, str]]], shuffler: Random
) -> None:
    nodes, edges = dag
    shuffled = list(edges)
    shuffler.shuffle(shuffled)
    first, second = build(nodes, edges), build(sorted(nodes), shuffled)
    assert first == second
    # dict equality ignores key order, and the key order is what reports walk
    assert list(first.dependents) == list(second.dependents)
    assert list(first.dependencies) == list(second.dependencies)


@given(dags(), st.data())
def test_any_back_edge_is_a_cycle(
    dag: tuple[list[str], list[tuple[str, str]]], data: st.DataObject
) -> None:
    nodes, edges = dag
    graph = build(nodes, edges)
    reachable = [
        (start, end)
        for start in nodes
        for end in (*blast_radius(graph, start).direct, *blast_radius(graph, start).indirect)
    ]
    pair = data.draw(st.sampled_from(reachable) if reachable else st.just((nodes[0], nodes[0])))
    # an edge from a dependent back to its dependency (or a node to itself) closes a loop
    with pytest.raises(InputError, match="dependency cycle"):
        build(nodes, [*edges, (pair[1], pair[0])])
