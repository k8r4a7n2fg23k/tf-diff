"""Unknown deciding values: only an attribute the author sets earns a low-confidence finding.

A computed attribute turns unknown on every replace whatever it will hold, so it proves nothing.
"""

from collections.abc import Callable, Iterator
from typing import TypeAlias

import pytest

from factories import configuration, context, resource_change
from tfdiff.model.findings import Confidence, Finding
from tfdiff.rules.aws import rds, s3
from tfdiff.rules.generic import capacity, encryption
from tfdiff.rules.rule import Context

Evaluate: TypeAlias = Callable[[Context], Iterator[Finding]]

CASES = [
    pytest.param(capacity.reduce, "aws_autoscaling_group.web", {"min_size": 4}, id="capacity"),
    pytest.param(capacity.redundancy, "aws_lb.web", {"subnets": ["a", "b"]}, id="spread"),
    pytest.param(capacity.redundancy, "aws_db_instance.main", {"multi_az": True}, id="multi-az"),
    pytest.param(
        encryption.evaluate, "aws_rds_cluster.main", {"storage_encrypted": True}, id="encryption"
    ),
    pytest.param(rds.public, "aws_db_instance.main", {"publicly_accessible": False}, id="public"),
    pytest.param(
        rds.backup, "aws_db_instance.main", {"backup_retention_period": 7}, id="retention"
    ),
    pytest.param(
        rds.backup, "aws_rds_cluster.main", {"skip_final_snapshot": False}, id="final-snapshot"
    ),
    pytest.param(
        rds.backup,
        "aws_dynamodb_table.orders",
        {"point_in_time_recovery": [{"enabled": True}]},
        id="dynamodb-pitr",
    ),
    pytest.param(
        s3.evaluate,
        "aws_s3_bucket_public_access_block.main",
        {"block_public_acls": True},
        id="s3",
    ),
]


def _confidences(
    evaluate: Evaluate, address: str, before: dict[str, object], *configured: str
) -> list[Confidence]:
    ((attribute, value),) = before.items()
    # a block keeps its shape and only its leaves go unknown, as Terraform plans it
    block = value[0] if isinstance(value, list) and isinstance(value[0], dict) else None
    raw = resource_change(
        address,
        actions=("delete", "create"),
        before=before,
        after={attribute: [{}]} if block is not None else {},
        after_unknown={attribute: [dict.fromkeys(block, True)] if block is not None else True},
    )
    found = evaluate(context(raw, configuration=configuration(raw, "other", *configured)))
    return [item.confidence for item in found]


@pytest.mark.parametrize(("evaluate", "address", "before"), CASES)
def test_configured_unknown_is_low_confidence(
    evaluate: Evaluate, address: str, before: dict[str, object]
) -> None:
    assert _confidences(evaluate, address, before, *before) == [Confidence.LOW]


@pytest.mark.parametrize(("evaluate", "address", "before"), CASES)
def test_computed_unknown_is_silent(
    evaluate: Evaluate, address: str, before: dict[str, object]
) -> None:
    assert _confidences(evaluate, address, before) == []
