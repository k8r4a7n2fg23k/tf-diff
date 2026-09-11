import pytest

from factories import context, resource_change
from tfdiff.model.findings import Confidence
from tfdiff.rules.aws import s3

ADDRESS = "aws_s3_bucket_public_access_block.logs"
LOCKED = {"block_public_acls": True, "block_public_policy": True}


@pytest.mark.parametrize(
    ("actions", "after", "titles"),
    [
        (
            ("update",),
            {"block_public_acls": False, "block_public_policy": True},
            ["S3 public access block weakened"],
        ),
        (("delete",), None, ["S3 public access block removed"]),
        (("update",), {"block_public_acls": True, "block_public_policy": True}, []),
    ],
    ids=["flag-off", "deleted", "unchanged"],
)
def test_public_access_guard(actions: tuple[str, ...], after: object, titles: list[str]) -> None:
    raw = resource_change(ADDRESS, actions=actions, before=LOCKED, after=after)
    assert [item.title for item in s3.evaluate(context(raw))] == titles


def test_creating_an_open_block_is_silent() -> None:
    raw = resource_change(ADDRESS, actions=("create",), after={"block_public_acls": False})
    assert list(s3.evaluate(context(raw))) == []


def test_unknown_guard_is_low_confidence() -> None:
    raw = resource_change(
        ADDRESS,
        before=LOCKED,
        after={"block_public_acls": True},
        after_unknown={"block_public_policy": True},
    )
    (found,) = s3.evaluate(context(raw))
    assert (found.confidence, found.evidence[-1].label) == (Confidence.LOW, "block_public_policy")


def test_deposed_block_cleanup_is_silent() -> None:
    # create_before_destroy: the new block is already in place when the old one goes
    raw = resource_change(ADDRESS, actions=("delete",), before=LOCKED, deposed="0a1b")
    assert list(s3.evaluate(context(raw))) == []
