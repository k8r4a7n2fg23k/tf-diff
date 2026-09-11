import pytest

from factories import Raw, context, evidence, resource_change
from tfdiff.model.findings import Severity
from tfdiff.rules.aws import stateful


def _replace(address: str, **state: object) -> Raw:
    return resource_change(
        address,
        actions=("delete", "create"),
        before={"storage_type": "gp2", **state},
        after={"storage_type": "io2", **state},
        replace_paths=[["storage_type"]],
    )


def _delete(address: str, **state: object) -> Raw:
    return resource_change(address, actions=("delete",), before=state)


@pytest.mark.parametrize(
    ("environment", "severity"), [("production", Severity.CRITICAL), (None, Severity.HIGH)]
)
def test_database_replacement(environment: str | None, severity: Severity) -> None:
    raw = _replace("module.db.aws_db_instance.primary")
    (found,) = stateful.evaluate(context(raw, environment=environment))
    assert (found.severity, found.title) == (severity, "Data store replaced")
    assert found.reason == (
        "aws_db_instance holds data; storage_type forces a new one, existing data is lost"
    )
    assert evidence(found)["storage_type"] == '"gp2" -> "io2"'


@pytest.mark.parametrize(
    ("environment", "severity"), [("staging", Severity.HIGH), (None, Severity.HIGH)]
)
def test_deletion_outside_production_loses_data_too(
    environment: str | None, severity: Severity
) -> None:
    raw = _delete("aws_dynamodb_table.orders", deletion_protection_enabled=False)
    (found,) = stateful.evaluate(context(raw, environment=environment))
    assert (found.severity, found.title) == (severity, "Data store deleted")
    assert found.reason == "aws_dynamodb_table holds data; it is removed, existing data is lost"


def test_deletion_in_production_is_critical() -> None:
    raw = _delete("aws_ebs_volume.data")
    (found,) = stateful.evaluate(context(raw, environment="production"))
    assert found.severity is Severity.CRITICAL


SNAPSHOT_FIRST = "a final snapshot is taken first"
REFUSED = "the provider refuses to delete it"


@pytest.mark.parametrize(
    ("kind", "state", "effect"),
    [
        (
            "aws_db_instance",
            {"skip_final_snapshot": False, "final_snapshot_identifier": "last"},
            SNAPSHOT_FIRST,
        ),
        # the provider fails the delete rather than skip the snapshot
        (
            "aws_db_instance",
            {"skip_final_snapshot": False, "final_snapshot_identifier": None},
            "the provider refuses to delete it without final_snapshot_identifier",
        ),
        ("aws_rds_cluster", {"deletion_protection": True}, REFUSED),
        ("aws_dynamodb_table", {"deletion_protection_enabled": True}, REFUSED),
        ("aws_elasticache_cluster", {"final_snapshot_identifier": "last"}, SNAPSHOT_FIRST),
        (
            "aws_s3_bucket",
            {"force_destroy": False},
            "the provider refuses to delete it while it holds objects",
        ),
    ],
)
def test_a_guard_that_keeps_the_data_lowers_the_severity(
    kind: str, state: dict[str, object], effect: str
) -> None:
    path = next(iter(state))
    for raw, environment, severity in [
        (_delete(f"{kind}.main", **state), "production", Severity.HIGH),
        (_replace(f"{kind}.main", **state), None, Severity.MEDIUM),
    ]:
        (found,) = stateful.evaluate(context(raw, environment=environment))
        assert found.severity is severity
        shown = evidence(found)[path]
        assert found.reason.endswith(f", but {path} = {shown}: {effect}")


@pytest.mark.parametrize(
    ("kind", "state"),
    [
        ("aws_db_instance", {"skip_final_snapshot": True, "deletion_protection": False}),
        ("aws_elasticache_cluster", {"final_snapshot_identifier": ""}),
        ("aws_elasticache_cluster", {"final_snapshot_identifier": None}),
        ("aws_s3_bucket", {"force_destroy": True}),
    ],
)
def test_a_guard_that_is_off_keeps_nothing(kind: str, state: dict[str, object]) -> None:
    (found,) = stateful.evaluate(context(_delete(f"{kind}.main", **state), environment=None))
    assert found.severity is Severity.HIGH
    assert found.reason.endswith("existing data is lost")


def test_every_guard_that_holds_is_listed() -> None:
    raw = _delete(
        "aws_db_instance.main",
        skip_final_snapshot=False,
        final_snapshot_identifier="last",
        deletion_protection=True,
    )
    (found,) = stateful.evaluate(context(raw))
    assert found.reason == (
        "aws_db_instance holds data; it is removed, but "
        "skip_final_snapshot = false: a final snapshot is taken first; "
        "deletion_protection = true: the provider refuses to delete it"
    )


def test_terraform_reason_for_a_deletion_is_evidence() -> None:
    raw = resource_change(
        "aws_s3_bucket.logs",
        actions=("delete",),
        before={},
        reason="delete_because_no_resource_config",
    )
    (found,) = stateful.evaluate(context(raw))
    assert evidence(found)["terraform reason"] == "delete_because_no_resource_config"


def test_deposed_deletion_is_silent() -> None:
    raw = resource_change("aws_db_instance.main", actions=("delete",), before={}, deposed="ab12")
    assert list(stateful.evaluate(context(raw, environment="production"))) == []


@pytest.mark.parametrize(
    "raw",
    [
        _replace("aws_instance.web"),
        _delete("aws_instance.web"),
        resource_change("aws_db_instance.main", before={"a": 1}, after={"a": 2}),
        resource_change("aws_db_instance.main", actions=("create",), after={}),
    ],
)
def test_stateless_types_and_other_actions_are_silent(raw: Raw) -> None:
    assert list(stateful.evaluate(context(raw, environment="production"))) == []


@pytest.mark.parametrize(
    ("kind", "state"),
    [
        ("aws_db_instance", {"replicate_source_db": "primary"}),
        ("aws_rds_cluster", {"replication_source_identifier": "arn:aws:rds:x:1:cluster:main"}),
        ("aws_elasticache_cluster", {"engine": "memcached"}),
        ("aws_elasticache_serverless_cache", {"engine": "memcached"}),
    ],
)
def test_a_copy_of_data_kept_elsewhere_is_silent(kind: str, state: dict[str, object]) -> None:
    for raw in (_delete(f"{kind}.main", **state), _replace(f"{kind}.main", **state)):
        assert list(stateful.evaluate(context(raw, environment="production"))) == []


@pytest.mark.parametrize(
    ("kind", "state"),
    [
        ("aws_db_instance", {"replicate_source_db": ""}),
        ("aws_db_instance", {"replicate_source_db": None}),
        ("aws_elasticache_cluster", {"engine": "redis"}),
        ("aws_elasticache_serverless_cache", {"engine": "valkey"}),
    ],
)
def test_a_store_that_keeps_its_own_data_is_flagged(kind: str, state: dict[str, object]) -> None:
    (found,) = stateful.evaluate(context(_delete(f"{kind}.main", **state), environment=None))
    assert found.severity is Severity.HIGH
