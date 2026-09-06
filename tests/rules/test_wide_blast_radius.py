import pytest

from factories import context, evidence, resource_change
from tfdiff.model.graph import BlastRadius
from tfdiff.model.settings import Settings
from tfdiff.rules.generic import blast


def _radius(direct: int, indirect: int) -> BlastRadius:
    return BlastRadius(
        tuple(f"aws_instance.d{i}" for i in range(direct)),
        tuple(f"aws_instance.i{i}" for i in range(indirect)),
    )


@pytest.mark.parametrize(
    ("actions", "direct", "indirect", "fires"),
    [
        (("delete", "create"), 3, 2, True),
        (("delete",), 12, 0, True),
        (("delete", "create"), 2, 2, False),
        (("update",), 10, 10, False),
    ],
    ids=["replace-at-threshold", "delete-many", "below-threshold", "update"],
)
def test_many_dependents_of_destructive_change(
    actions: tuple[str, ...], direct: int, indirect: int, fires: bool
) -> None:
    after = None if actions == ("delete",) else {"ami": "b"}
    raw = resource_change("aws_vpc.main", actions=actions, before={"ami": "a"}, after=after)
    found = list(blast.evaluate(context(raw, blast=_radius(direct, indirect))))
    assert [item.title for item in found] == (["Wide blast radius"] if fires else [])


def test_long_dependent_list_is_cut() -> None:
    raw = resource_change("aws_vpc.main", actions=("delete",), before={"cidr": "10.0.0.0/16"})
    (found,) = blast.evaluate(context(raw, blast=_radius(15, 0)))
    affected = evidence(found)["affected"]
    assert affected.endswith("and 5 more")


def test_threshold_comes_from_settings() -> None:
    raw = resource_change("aws_vpc.main", actions=("delete",), before={"cidr": "10.0.0.0/16"})
    settings = Settings(thresholds={blast.ID: 3})
    (found,) = blast.evaluate(context(raw, blast=_radius(3, 0), settings=settings))
    assert found.reason == "3 resources depend on it (threshold 3)"


def test_list_at_the_cut_is_complete() -> None:
    raw = resource_change("aws_vpc.main", actions=("delete",), before={"cidr": "10.0.0.0/16"})
    (found,) = blast.evaluate(context(raw, blast=_radius(blast.SHOWN, 0)))
    affected = evidence(found)["affected"]
    assert "more" not in affected
    assert affected.count("aws_instance.d") == blast.SHOWN
