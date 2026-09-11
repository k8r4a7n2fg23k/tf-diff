import pytest

from factories import context, resource_change
from tfdiff.rules.aws import rds


@pytest.mark.parametrize(
    ("actions", "before", "after", "fires"),
    [
        (("update",), {"publicly_accessible": False}, {"publicly_accessible": True}, True),
        (("create",), None, {"publicly_accessible": True}, True),
        (("update",), {"publicly_accessible": True}, {"publicly_accessible": True}, False),
        (("update",), {"publicly_accessible": False}, {"publicly_accessible": False}, False),
    ],
    ids=["turned-on", "created-public", "already-public", "private"],
)
def test_public_endpoint(
    actions: tuple[str, ...], before: object, after: object, fires: bool
) -> None:
    raw = resource_change("aws_db_instance.main", actions=actions, before=before, after=after)
    found = list(rds.public(context(raw)))
    assert [item.title for item in found] == (
        ["Database becomes publicly accessible"] if fires else []
    )


def test_other_types_are_ignored() -> None:
    raw = resource_change(
        "aws_instance.web",
        before={"publicly_accessible": False},
        after={"publicly_accessible": True},
    )
    assert list(rds.public(context(raw))) == []
