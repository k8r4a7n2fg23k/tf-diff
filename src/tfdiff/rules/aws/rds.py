from collections.abc import Iterator

from tfdiff.model.findings import Confidence, Finding, Severity
from tfdiff.model.plan import Action
from tfdiff.model.values import Path, Unknown, Value, flag, number, show_path, value_at
from tfdiff.rules.rule import Context, Rule, finding, transition

PUBLIC = "public-database"
BACKUP = "backup-disabled"

PUBLIC_TYPES = frozenset({"aws_db_instance", "aws_rds_cluster_instance"})
RETENTION_TYPES = frozenset(
    {"aws_db_instance", "aws_docdb_cluster", "aws_neptune_cluster", "aws_rds_cluster"}
)
SNAPSHOT_TYPES = frozenset({"aws_db_instance", "aws_rds_cluster"})
PUBLICLY_ACCESSIBLE: Path = ("publicly_accessible",)
RETENTION: Path = ("backup_retention_period",)
SKIP_SNAPSHOT: Path = ("skip_final_snapshot",)
PITR: Path = ("point_in_time_recovery", 0, "enabled")
CHANGED = frozenset({Action.CREATE, Action.UPDATE, Action.REPLACE})


def public(context: Context) -> Iterator[Finding]:
    change = context.change
    if change.resource.type not in PUBLIC_TYPES or change.action not in CHANGED:
        return
    before, after = (
        value_at(change.before, PUBLICLY_ACCESSIBLE),
        value_at(change.after, PUBLICLY_ACCESSIBLE),
    )
    if flag(before) is True:
        return
    evidence = [transition(PUBLICLY_ACCESSIBLE, before, after)]
    if flag(after) is True:
        yield finding(
            context,
            PUBLIC,
            Severity.CRITICAL,
            "Database becomes publicly accessible",
            "publicly_accessible turns on: the endpoint resolves to a public IP",
            evidence,
        )
    elif isinstance(after, Unknown) and context.is_configured(PUBLICLY_ACCESSIBLE):
        yield finding(
            context,
            PUBLIC,
            Severity.CRITICAL,
            "Database may become public",
            "publicly_accessible is unknown until apply",
            evidence,
            Confidence.LOW,
        )


def backup(context: Context) -> Iterator[Finding]:
    change = context.change
    if change.action not in {Action.UPDATE, Action.REPLACE}:
        return
    for path in _backup_paths(change.resource.type):
        before, after = value_at(change.before, path), value_at(change.after, path)
        if not _is_on(path, before):
            continue
        evidence = [transition(path, before, after)]
        if _is_off(path, after):
            yield finding(
                context,
                BACKUP,
                Severity.HIGH,
                "Backups disabled",
                f"{show_path(path)} removes the way back after data loss",
                evidence,
            )
        elif isinstance(after, Unknown) and context.is_configured(path):
            yield finding(
                context,
                BACKUP,
                Severity.HIGH,
                "Backups may be disabled",
                f"{show_path(path)} is unknown until apply",
                evidence,
                Confidence.LOW,
            )


def _backup_paths(kind: str) -> list[Path]:
    found = []
    if kind in RETENTION_TYPES:
        found.append(RETENTION)
    if kind in SNAPSHOT_TYPES:
        found.append(SKIP_SNAPSHOT)
    if kind == "aws_dynamodb_table":
        found.append(PITR)
    return found


def _is_on(path: Path, value: Value) -> bool:
    if path == RETENTION:
        days = number(value)
        return days is not None and days > 0
    if path == SKIP_SNAPSHOT:
        return flag(value) is False
    return flag(value) is True


def _is_off(path: Path, value: Value) -> bool:
    if path == RETENTION:
        return number(value) == 0
    if path == SKIP_SNAPSHOT:
        return flag(value) is True
    return flag(value) is False


PUBLIC_RULE = Rule(PUBLIC, "RDS instance becomes publicly accessible", Severity.CRITICAL, public)
BACKUP_RULE = Rule(
    BACKUP,
    "Backup retention, final snapshot or point-in-time recovery is turned off",
    Severity.HIGH,
    backup,
)
