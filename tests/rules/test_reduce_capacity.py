import pytest

from factories import context, resource_change
from tfdiff.model.findings import Confidence, Severity
from tfdiff.model.settings import Settings
from tfdiff.rules.generic.capacity import REDUCE, reduce


def _service(before: object, after: object, unknown: bool = False) -> dict[str, object]:
    return resource_change(
        "module.api.aws_ecs_service.api",
        before={"desired_count": before},
        after={} if unknown else {"desired_count": after},
        after_unknown={"desired_count": True} if unknown else {},
    )


@pytest.mark.parametrize(
    ("before", "after", "fires"),
    [
        (6, 2, True),
        (10, 7, True),
        (10, 8, False),
        ("10", 7, True),
        (10, "10", False),
        (2, 5, False),
        (0, 0, False),
        (0, 2, False),
        (1, 0, True),
        (1000, 701, False),
        (None, 3, False),
    ],
    ids=[
        "66pct",
        "30pct-boundary",
        "20pct",
        "string-before",
        "type-noise",
        "increase",
        "zero",
        "from-zero",
        "one-to-zero",
        "just-under-threshold",
        "added",
    ],
)
def test_capacity_drop_against_default_threshold(
    before: object, after: object, fires: bool
) -> None:
    found = list(reduce(context(_service(before, after))))
    assert [(item.rule, item.severity) for item in found] == (
        [(REDUCE, Severity.HIGH)] if fires else []
    )


@pytest.mark.parametrize(
    ("before", "after", "threshold"), [(100, 43, 57), (100, 71, 29), (50, 21, 58)]
)
def test_drop_exactly_at_threshold_fires(before: int, after: int, threshold: int) -> None:
    settings = Settings(thresholds={REDUCE: threshold})
    (found,) = reduce(context(_service(before, after), settings=settings))
    assert found.reason.endswith(f"(threshold {threshold}%)")
    stricter = Settings(thresholds={REDUCE: threshold + 1})
    assert list(reduce(context(_service(before, after), settings=stricter))) == []


@pytest.mark.parametrize(("before", "expected"), [(4, [Confidence.LOW]), (0, [])], ids=["4", "0"])
def test_unknown_capacity_is_low_confidence(before: int, expected: list[Confidence]) -> None:
    # nothing to lose from zero, whatever it becomes
    found = list(reduce(context(_service(before, None, unknown=True))))
    assert [item.confidence for item in found] == expected
    assert all("desired_count is unknown" in item.reason for item in found)


def test_capacity_too_large_for_a_float_is_skipped() -> None:
    # json holds integers of any size; float() of 400 digits overflows
    assert list(reduce(context(_service(10**400, 1)))) == []
