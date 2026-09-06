import pytest

from factories import context, resource_change
from tfdiff.model.findings import Confidence, Severity
from tfdiff.rules.generic import encryption


@pytest.mark.parametrize(
    ("before", "after", "fires"),
    [
        (True, False, True),
        ("true", "false", True),
        (False, True, False),
        (True, True, False),
        # dropped from the config: null says nothing about what the provider will do
        (True, None, False),
    ],
    ids=["off", "string-off", "on", "unchanged", "dropped"],
)
def test_encryption_turned_off(before: object, after: object, fires: bool) -> None:
    raw = resource_change(
        "aws_ebs_volume.data", before={"encrypted": before}, after={"encrypted": after}
    )
    expected = [(Severity.CRITICAL, Confidence.HIGH)] if fires else []
    assert [
        (item.severity, item.confidence) for item in encryption.evaluate(context(raw))
    ] == expected


def test_nested_flag_unknown_after_apply_is_low_confidence() -> None:
    raw = resource_change(
        "aws_elasticache_replication_group.cache",
        before={"settings": [{"at_rest_encryption_enabled": True}]},
        after={"settings": [{}]},
        after_unknown={"settings": [{"at_rest_encryption_enabled": True}]},
    )
    (found,) = encryption.evaluate(context(raw))
    assert found.confidence is Confidence.LOW
    assert found.reason == "settings[0].at_rest_encryption_enabled is unknown until apply"


@pytest.mark.parametrize(
    ("address", "block"),
    [
        ("aws_dynamodb_table.orders", "server_side_encryption"),
        ("aws_opensearch_domain.search", "encrypt_at_rest"),
        ("aws_opensearch_domain.search", "node_to_node_encryption"),
    ],
)
def test_encryption_block_switched_off(address: str, block: str) -> None:
    raw = resource_change(
        address, before={block: [{"enabled": True}]}, after={block: [{"enabled": False}]}
    )
    (found,) = encryption.evaluate(context(raw))
    assert found.reason == f"{block}[0].enabled turns off"


def test_other_enabled_flags_are_not_encryption() -> None:
    raw = resource_change(
        "aws_dynamodb_table.orders",
        before={"ttl": [{"enabled": True}]},
        after={"ttl": [{"enabled": False}]},
    )
    assert list(encryption.evaluate(context(raw))) == []
