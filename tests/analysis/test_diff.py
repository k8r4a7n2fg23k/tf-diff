import pytest
from hypothesis import given
from hypothesis import strategies as st

from factories import one, resource_change
from tfdiff.analysis.diff import classify, diff, same
from tfdiff.model.diff import Kind
from tfdiff.model.values import Known, Null, Sensitive, Unknown, Value, show_path


def _changes(
    before: object,
    after: object,
    unknown: object = None,
    sensitive: object = None,
    actions: tuple[str, ...] = ("update",),
) -> list[tuple[str, Kind]]:
    raw = resource_change(
        "aws_instance.web",
        actions=actions,
        before=before,
        after=after,
        after_unknown=unknown,
        before_sensitive=sensitive,
        after_sensitive=sensitive,
    )
    return [(show_path(item.path), item.kind) for item in diff(one(raw))]


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        ({"size": "10"}, {"size": 10}, []),
        ({"size": 10}, {"size": 10.0}, []),
        ({"on": "true"}, {"on": True}, []),
        ({"on": 1}, {"on": True}, [("on", Kind.MODIFIED)]),
        ({"on": True}, {"on": "yes"}, [("on", Kind.MODIFIED)]),
        ({"size": "10"}, {"size": "10.5"}, [("size", Kind.MODIFIED)]),
        ({"name": None}, {"name": "a"}, [("name", Kind.ADDED)]),
        ({"name": "a"}, {}, [("name", Kind.REMOVED)]),
        ({"tags": None}, {"tags": {"Team": "x"}}, [("tags.Team", Kind.ADDED)]),
        ({"zones": ["a", "b"]}, {"zones": ["a"]}, [("zones[1]", Kind.REMOVED)]),
        ({"weird key": 1}, {"weird key": 2}, [('["weird key"]', Kind.MODIFIED)]),
        ({"x": [1]}, {"x": {"k": 1}}, [("x[0]", Kind.REMOVED), ("x.k", Kind.ADDED)]),
        ({"profile": "", "protect": False, "iops": 0}, {}, []),
        ({"name": None}, {"name": ""}, []),
        ({"protect": True}, {}, [("protect", Kind.REMOVED)]),
    ],
    ids=[
        "string-vs-int",
        "int-vs-float",
        "string-bool",
        "int-is-not-bool",
        "bool-vs-word",
        "real-number-change",
        "added",
        "removed",
        "null-to-map",
        "list-shrinks",
        "quoted-key",
        "list-becomes-map",
        "state-zero-values-are-unset",
        "null-to-empty",
        "true-to-null",
    ],
)
def test_known_values(before: object, after: object, expected: list[tuple[str, Kind]]) -> None:
    assert _changes(before, after) == expected


def test_unknown_subtree_is_diffed_per_known_leaf() -> None:
    changes = _changes(
        {"output": {"a": 1, "b": 2}, "id": "x"}, {"id": "x"}, unknown={"output": True}
    )
    assert changes == [("output.a", Kind.UNKNOWN), ("output.b", Kind.UNKNOWN)]


def test_unknown_is_neither_changed_nor_unchanged() -> None:
    (item,) = diff(
        one(
            resource_change(
                "aws_instance.web",
                before={"ip": "203.0.113.1"},
                after={},
                after_unknown={"ip": True},
            )
        )
    )
    assert (item.kind, item.before, item.after) == (Kind.UNKNOWN, Known("203.0.113.1"), Unknown())


@pytest.mark.parametrize(
    ("after", "expected"),
    [("CANARY-2", [("users[0].secret", Kind.SENSITIVE)]), ("CANARY-1", [])],
    ids=["changed", "same"],
)
def test_nested_sensitive_reports_change_not_value(
    after: str, expected: list[tuple[str, Kind]]
) -> None:
    mask = {"users": [{"secret": True}]}
    assert (
        _changes(
            {"users": [{"secret": "CANARY-1"}]}, {"users": [{"secret": after}]}, sensitive=mask
        )
        == expected
    )


def test_secret_names_are_redacted_without_a_mask() -> None:
    change = one(
        resource_change(
            "aws_instance.web",
            before={"db_password": "CANARY-1"},
            after={"db_password": "CANARY-2"},
        )
    )
    (item,) = diff(change)
    assert (item.before, item.after) == (Sensitive(is_changed=True), Sensitive(is_changed=True))


def test_replace_paths_mark_forcing_leaves() -> None:
    raw = resource_change(
        "aws_instance.web",
        actions=("delete", "create"),
        before={"root": [{"size": 8}], "name": "a"},
        after={"root": [{"size": 16}], "name": "b"},
        replace_paths=[["root"]],
    )
    assert [(show_path(item.path), item.is_forcing) for item in diff(one(raw))] == [
        ("name", False),
        ("root[0].size", True),
    ]


@pytest.mark.parametrize("actions", [("create",), ("delete",), ("no-op",)])
def test_only_updates_and_replacements_are_diffed(actions: tuple[str, ...]) -> None:
    before = None if actions == ("create",) else {"a": 1}
    after = None if actions == ("delete",) else {"a": 2}
    assert _changes(before, after, actions=actions) == []


JSON = st.recursive(
    st.none() | st.booleans() | st.integers() | st.text(max_size=5),
    lambda inner: (
        st.lists(inner, max_size=3) | st.dictionaries(st.text(max_size=4), inner, max_size=3)
    ),
    max_leaves=12,
)


@given(tree=st.dictionaries(st.text(max_size=4), JSON, max_size=5))
def test_identical_sides_have_no_changes(tree: dict[str, object]) -> None:
    assert _changes(tree, tree) == []


KEYS = st.sampled_from(["a", "b", "password", "tags"])
TREES = st.dictionaries(
    KEYS,
    st.recursive(
        st.none() | st.booleans() | st.integers(-3, 3) | st.sampled_from(["1", "x", "true"]),
        lambda inner: st.lists(inner, max_size=2) | st.dictionaries(KEYS, inner, max_size=2),
        max_leaves=6,
    ),
    max_size=3,
)
MASKS = st.dictionaries(KEYS, st.booleans(), max_size=3)


@given(before=TREES, after=TREES, unknown=MASKS, sensitive=MASKS)
def test_every_change_is_a_real_difference(
    before: dict[str, object],
    after: dict[str, object],
    unknown: dict[str, bool],
    sensitive: dict[str, bool],
) -> None:
    raw = resource_change(
        "aws_instance.web",
        before=before,
        after=after,
        after_unknown=unknown,
        before_sensitive=sensitive,
        after_sensitive=sensitive,
    )
    change = one(raw)
    found = {item.path: item for item in diff(change)}
    old_side, new_side = dict(change.before), dict(change.after)
    # oracle from the parsed sides: a known leaf on both sides is reported exactly when it
    # differs, with its own two values (not swapped, not a neighbour's)
    for path in old_side.keys() & new_side.keys():
        old, new = old_side[path], new_side[path]
        if isinstance(old, Known) and isinstance(new, Known):
            assert (path in found) is not same(old.value, new.value)
            if path in found:
                assert (found[path].before, found[path].after) == (old, new)


@pytest.mark.parametrize(
    ("before", "after", "kind"),
    [
        (Null(), Sensitive(is_changed=True), Kind.SENSITIVE),
        (Sensitive(is_changed=True), Null(), Kind.SENSITIVE),
        (Sensitive(is_changed=False), Sensitive(is_changed=False), None),
        (Null(), Unknown(), Kind.UNKNOWN),
        # an unknown secret is pending, not changed: low confidence downstream
        (Sensitive(is_changed=True), Unknown(), Kind.UNKNOWN),
        (Known(1), Unknown(), Kind.UNKNOWN),
        (Null(), Null(), None),
    ],
)
def test_marker_pairs(before: Value, after: Value, kind: Kind | None) -> None:
    assert classify(before, after) is kind
