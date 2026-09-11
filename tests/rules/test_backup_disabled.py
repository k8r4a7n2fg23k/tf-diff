import pytest

from factories import context, resource_change
from tfdiff.rules.aws import rds


@pytest.mark.parametrize(
    ("address", "before", "after", "fires"),
    [
        (
            "aws_db_instance.main",
            {"backup_retention_period": 7},
            {"backup_retention_period": 0},
            True,
        ),
        (
            "aws_db_instance.main",
            {"backup_retention_period": 7},
            {"backup_retention_period": 1},
            False,
        ),
        (
            "aws_db_instance.main",
            {"backup_retention_period": 1},
            {"backup_retention_period": 0},
            True,
        ),
        (
            "aws_rds_cluster.main",
            {"skip_final_snapshot": False},
            {"skip_final_snapshot": True},
            True,
        ),
        (
            "aws_dynamodb_table.orders",
            {"point_in_time_recovery": [{"enabled": True}]},
            {"point_in_time_recovery": [{"enabled": False}]},
            True,
        ),
        ("aws_instance.web", {"backup_retention_period": 7}, {"backup_retention_period": 0}, False),
        (
            "aws_rds_cluster.main",
            {"skip_final_snapshot": True, "x": 1},
            {"skip_final_snapshot": True, "x": 2},
            False,
        ),
        (
            "aws_db_instance.main",
            {"backup_retention_period": 0, "x": 1},
            {"backup_retention_period": 0, "x": 2},
            False,
        ),
    ],
    ids=[
        "retention-seven-to-zero",
        "retention-seven-to-one",
        "retention-one-to-zero",
        "final-snapshot",
        "dynamodb-pitr",
        "other-type",
        "snapshot-already-skipped",
        "retention-already-zero",
    ],
)
def test_backups_turned_off(address: str, before: object, after: object, fires: bool) -> None:
    raw = resource_change(address, before=before, after=after)
    assert [item.rule for item in rds.backup(context(raw))] == (
        ["backup-disabled"] if fires else []
    )
