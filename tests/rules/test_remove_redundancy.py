import pytest

from factories import context, resource_change
from tfdiff.model.findings import Confidence
from tfdiff.rules.generic.capacity import redundancy

ZONES = ["us-east-1a", "us-east-1b", "us-east-1c"]


@pytest.mark.parametrize(
    ("actions", "after", "fires"),
    [
        (("update",), ZONES[:1], True),
        (("update",), [], True),
        (("update",), ZONES[:2], False),
        (("update",), ZONES, False),
        # deleting the group is the destroy rule's business, not lost redundancy
        (("delete",), None, False),
    ],
    ids=["three-to-one", "three-to-none", "three-to-two", "unchanged", "deleted"],
)
def test_zone_spread_falling_to_one(
    actions: tuple[str, ...], after: list[str] | None, fires: bool
) -> None:
    raw = resource_change(
        "aws_autoscaling_group.web",
        actions=actions,
        before={"availability_zones": ZONES},
        after=None if after is None else {"availability_zones": after},
    )
    titles = [item.title for item in redundancy(context(raw))]
    assert titles == (["Redundancy removed"] if fires else [])


def test_nested_spread_is_named_by_its_full_path() -> None:
    raw = resource_change(
        "aws_lambda_function.api",
        before={"vpc_config": [{"subnet_ids": ["subnet-1", "subnet-2"]}]},
        after={"vpc_config": [{"subnet_ids": ["subnet-1"]}]},
    )
    (found,) = redundancy(context(raw))
    assert found.reason == "vpc_config[0].subnet_ids drops from 2 entries to 1"


def test_unknown_spread_is_low_confidence() -> None:
    raw = resource_change(
        "aws_eks_node_group.main",
        before={"subnet_ids": ["subnet-1", "subnet-2"]},
        after={},
        after_unknown={"subnet_ids": True},
    )
    (found,) = redundancy(context(raw))
    assert found.confidence is Confidence.LOW


@pytest.mark.parametrize(
    ("before", "after", "fires"),
    [(True, False, True), ("true", "false", True), (False, True, False), (None, False, False)],
)
def test_multi_az_turned_off(before: object, after: object, fires: bool) -> None:
    raw = resource_change(
        "aws_db_instance.main", before={"multi_az": before}, after={"multi_az": after}
    )
    assert [item.title for item in redundancy(context(raw))] == (
        ["Multi-AZ disabled"] if fires else []
    )


def test_other_lists_shrinking_are_not_redundancy() -> None:
    raw = resource_change(
        "aws_instance.web",
        before={"security_groups": ["sg-1", "sg-2"]},
        after={"security_groups": ["sg-1"]},
    )
    assert list(redundancy(context(raw))) == []


def test_multi_az_after_other_changes() -> None:
    raw = resource_change(
        "aws_db_instance.main",
        before={"allocated_storage": 100, "multi_az": True},
        after={"allocated_storage": 200, "multi_az": False},
    )
    assert [item.title for item in redundancy(context(raw))] == ["Multi-AZ disabled"]


@pytest.mark.parametrize(
    ("after", "expected"),
    [
        (ZONES, []),
        (
            ZONES[:1],
            [
                (
                    Confidence.LOW,
                    "subnets spans 3 entries now and changes to a redacted value",
                    "3 -> <sensitive>",
                )
            ],
        ),
    ],
    ids=["unchanged", "changed"],
)
def test_sensitive_spread_hides_its_length(
    after: list[str], expected: list[tuple[Confidence, str, str]]
) -> None:
    # the list now comes from a sensitive variable, which marks it whole: no length to count
    raw = resource_change(
        "aws_lb.web",
        before={"subnets": ZONES},
        after={"subnets": after},
        after_sensitive={"subnets": True},
    )
    found = redundancy(context(raw))
    assert [(item.confidence, item.reason, item.evidence[-1].text) for item in found] == expected


def test_every_spread_list_is_checked() -> None:
    # a single-entry list sorted first must not stop the walk
    raw = resource_change(
        "aws_lb.web",
        before={"availability_zones": ZONES[:1], "subnets": ["a", "b", "c"]},
        after={"availability_zones": ZONES[:1], "subnets": ["a"]},
    )
    assert [item.title for item in redundancy(context(raw))] == ["Redundancy removed"]


def test_unchanged_sensitive_spread_does_not_stop_the_walk() -> None:
    raw = resource_change(
        "aws_lb.web",
        before={"availability_zones": ZONES, "subnets": ["a", "b", "c"]},
        after={"availability_zones": ZONES, "subnets": ["a"]},
        after_sensitive={"availability_zones": True},
    )
    assert [item.title for item in redundancy(context(raw))] == ["Redundancy removed"]
