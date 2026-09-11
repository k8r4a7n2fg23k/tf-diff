from collections.abc import Iterator
from dataclasses import dataclass

from tfdiff.model.findings import Evidence, Finding, Severity
from tfdiff.model.plan import Action
from tfdiff.model.values import Attributes, Known, Path, Value, flag, show, show_path, value_at
from tfdiff.rules.rule import Context, Rule, finding, transition

ID = "stateful-data-loss"

# deleting or replacing these loses the data that lives only there, unless a snapshot or a
# guard keeps it
TYPES = frozenset(
    {
        "aws_db_instance",
        "aws_docdb_cluster",
        "aws_dynamodb_table",
        "aws_ebs_volume",
        "aws_efs_file_system",
        "aws_elasticache_cluster",
        "aws_elasticache_replication_group",
        "aws_elasticache_serverless_cache",
        "aws_kinesis_stream",
        "aws_neptune_cluster",
        "aws_opensearch_domain",
        "aws_rds_cluster",
        "aws_redshift_cluster",
        "aws_s3_bucket",
    }
)


@dataclass(frozen=True, slots=True)
class _Guard:
    path: Path
    # the value, before the change, that keeps the data
    keeps: bool | None
    effect: str


SNAPSHOT = _Guard(("skip_final_snapshot",), keeps=False, effect="a final snapshot is taken first")
PROTECTION = _Guard(
    ("deletion_protection",), keeps=True, effect="the provider refuses to delete it"
)
# a set identifier makes the provider snapshot first; checked by presence, not by flag
NAMED_SNAPSHOT = _Guard(
    ("final_snapshot_identifier",), keeps=None, effect="a final snapshot is taken first"
)
# guards are read from the state before the change: the provider deletes with those values
GUARDS: dict[str, tuple[_Guard, ...]] = {
    "aws_db_instance": (SNAPSHOT, PROTECTION),
    "aws_rds_cluster": (SNAPSHOT, PROTECTION),
    "aws_docdb_cluster": (SNAPSHOT, PROTECTION),
    "aws_neptune_cluster": (SNAPSHOT, PROTECTION),
    "aws_redshift_cluster": (SNAPSHOT,),
    "aws_dynamodb_table": (
        _Guard(
            ("deletion_protection_enabled",), keeps=True, effect="the provider refuses to delete it"
        ),
    ),
    "aws_elasticache_cluster": (NAMED_SNAPSHOT,),
    "aws_elasticache_replication_group": (NAMED_SNAPSHOT,),
    "aws_s3_bucket": (
        _Guard(
            ("force_destroy",),
            keeps=False,
            effect="the provider refuses to delete it while it holds objects",
        ),
    ),
}
# without an identifier the provider fails the delete instead of taking the snapshot
UNNAMED_SNAPSHOT = "the provider refuses to delete it without final_snapshot_identifier"
# the data lives elsewhere: a replica copies its source, memcached keeps nothing on disk
COPIES: dict[str, tuple[Path, str | None, str]] = {
    "aws_db_instance": (("replicate_source_db",), None, "a read replica of"),
    "aws_rds_cluster": (("replication_source_identifier",), None, "a replica of"),
    "aws_elasticache_cluster": (("engine",), "memcached", "a memcached cache"),
    "aws_elasticache_serverless_cache": (("engine",), "memcached", "a memcached cache"),
}
VERB = {Action.DELETE: "deleted", Action.REPLACE: "replaced"}


def evaluate(context: Context) -> Iterator[Finding]:
    change = context.change
    # a deposed delete is the tail of create_before_destroy: flagged when it was replaced
    if change.action not in VERB or change.deposed or change.resource.type not in TYPES:
        return
    if _holds_no_data(change.resource.type, change.before):
        return
    verb = VERB[change.action]
    if change.action is Action.REPLACE:
        paths = ", ".join(show_path(path) for path in change.replace_paths)
        cause = f"{paths} forces a new one" if paths else "Terraform plans a new one"
        evidence = [
            transition(attribute.path, attribute.before, attribute.after)
            for attribute in context.attributes
            if attribute.is_forcing
        ]
    else:
        cause = "it is removed"
        evidence = [Evidence("terraform reason", change.reason)] if change.reason else []
    kept = [
        guard
        for guard in GUARDS.get(change.resource.type, ())
        if _keeps(guard, value_at(change.before, guard.path))
    ]
    if kept:
        severity = Severity.HIGH if context.is_production else Severity.MEDIUM
        states = [
            (
                show_path(guard.path),
                show(value_at(change.before, guard.path)),
                _effect(guard, change.before),
            )
            for guard in kept
        ]
        outcome = "but " + "; ".join(
            f"{path} = {state}: {effect}" for path, state, effect in states
        )
        evidence += [Evidence(path, state) for path, state, _ in states]
    else:
        severity = Severity.CRITICAL if context.is_production else Severity.HIGH
        outcome = "existing data is lost"
    yield finding(
        context,
        ID,
        severity,
        f"Data store {verb}",
        f"{change.resource.type} holds data; {cause}, {outcome}",
        evidence,
    )


def _holds_no_data(kind: str, before: Attributes) -> bool:
    """Whether the object only copies data kept elsewhere; unknown counts as holding data."""
    if kind not in COPIES:
        return False
    path, expected, _ = COPIES[kind]
    value = value_at(before, path)
    if not isinstance(value, Known) or not isinstance(value.value, str):
        return False
    return value.value == expected if expected else bool(value.value)


def _effect(guard: _Guard, before: Attributes) -> str:
    if guard is SNAPSHOT and not _keeps(NAMED_SNAPSHOT, value_at(before, NAMED_SNAPSHOT.path)):
        return UNNAMED_SNAPSHOT
    return guard.effect


def _keeps(guard: _Guard, value: Value) -> bool:
    if guard.keeps is None:
        return isinstance(value, Known) and isinstance(value.value, str) and bool(value.value)
    return flag(value) is guard.keeps


RULE = Rule(
    ID,
    "Data store is deleted or replaced: critical in production, high elsewhere; "
    "one step lower when a final snapshot or deletion guard keeps the data",
    Severity.CRITICAL,
    evaluate,
)
