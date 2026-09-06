import pytest

from factories import context, resource_change
from tfdiff.model.findings import Severity
from tfdiff.rules.generic import destroy

BUCKET = {"bucket": "logs.example.com"}


def test_prod_delete_is_critical() -> None:
    raw = resource_change(
        "aws_s3_bucket.logs",
        actions=("delete",),
        before=BUCKET,
        reason="delete_because_no_resource_config",
    )
    (found,) = destroy.evaluate(context(raw, environment="Production"))
    assert found.severity is Severity.CRITICAL
    assert found.reason == "aws_s3_bucket is deleted in a production environment"
    assert ("terraform reason", "delete_because_no_resource_config") in [
        (item.label, item.text) for item in found.evidence
    ]


@pytest.mark.parametrize(
    ("actions", "environment", "deposed"),
    [
        (("delete",), "staging", None),
        (("delete",), None, None),
        (("delete", "create"), "production", None),
        (("delete",), "production", "00000001"),
    ],
    ids=["staging", "no-environment", "replace", "deposed-cleanup"],
)
def test_silent_outside_plain_prod_delete(
    actions: tuple[str, ...], environment: str | None, deposed: str | None
) -> None:
    after = None if actions == ("delete",) else BUCKET
    raw = resource_change(
        "aws_s3_bucket.logs", actions=actions, before=BUCKET, after=after, deposed=deposed
    )
    assert list(destroy.evaluate(context(raw, environment=environment))) == []
