import pytest

from tfdiff.model.values import NULL, Known, Sensitive, Unknown, Value, indexes, value_at


@pytest.mark.parametrize(
    "marker", [Unknown(), Sensitive(is_changed=True)], ids=["unknown", "sensitive"]
)
def test_marker_on_a_block_covers_every_path_below_it(marker: Value) -> None:
    # rules read pitr[0].enabled under a redacted or unknown block: hidden, not absent
    attributes = ((("pitr",), marker), (("tags", "env"), Known("prod")))
    assert value_at(attributes, ("pitr", 0, "enabled")) == marker
    assert value_at(attributes, ("tags", "env")) == Known("prod")
    assert value_at(attributes, ("tags", "owner")) == NULL
    assert indexes(attributes, ("pitr",)) == ()


def test_known_leaf_does_not_cover_paths_below_it() -> None:
    # a scalar where a map was expected says nothing about the map's keys
    attributes = ((("tags",), Known("none")),)
    assert value_at(attributes, ("tags", "env")) == NULL
