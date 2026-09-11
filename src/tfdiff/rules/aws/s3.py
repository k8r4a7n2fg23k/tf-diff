from collections.abc import Iterator

from tfdiff.model.findings import Confidence, Evidence, Finding, Severity
from tfdiff.model.plan import Action
from tfdiff.model.values import Path, Unknown, flag, value_at
from tfdiff.rules.rule import Context, Rule, finding, transition

ID = "s3-public-access-weakened"

TYPES = frozenset({"aws_s3_bucket_public_access_block", "aws_s3_account_public_access_block"})
FLAGS: tuple[Path, ...] = (
    ("block_public_acls",),
    ("block_public_policy",),
    ("ignore_public_acls",),
    ("restrict_public_buckets",),
)


def evaluate(context: Context) -> Iterator[Finding]:
    change = context.change
    if change.resource.type not in TYPES:
        return
    # a deposed delete is create_before_destroy cleanup: the new block is already in place
    if change.action is Action.DELETE and not change.deposed:
        yield finding(
            context,
            ID,
            Severity.HIGH,
            "S3 public access block removed",
            "deleting the block lets bucket policies and ACLs make data public",
            [Evidence("resource", change.resource.type)],
        )
        return
    if change.action not in {Action.UPDATE, Action.REPLACE}:
        return
    guards = [(path, value_at(change.before, path), value_at(change.after, path)) for path in FLAGS]
    was_on = [guard for guard in guards if flag(guard[1]) is True]
    weakened = [transition(*guard) for guard in was_on if flag(guard[2]) is False]
    unknown = [
        transition(*guard)
        for guard in was_on
        if isinstance(guard[2], Unknown) and context.is_configured(guard[0])
    ]
    if weakened:
        yield finding(
            context,
            ID,
            Severity.HIGH,
            "S3 public access block weakened",
            f"{len(weakened)} public access guard(s) turn off",
            weakened,
        )
    if unknown:
        yield finding(
            context,
            ID,
            Severity.HIGH,
            "S3 public access block may weaken",
            f"{len(unknown)} public access guard(s) unknown until apply",
            unknown,
            Confidence.LOW,
        )


RULE = Rule(ID, "S3 public access block is turned off or deleted", Severity.HIGH, evaluate)
