from collections.abc import Iterator

from tfdiff.model.diff import Kind
from tfdiff.model.findings import Confidence, Finding, Severity
from tfdiff.model.values import Path, flag, show_path
from tfdiff.rules.rule import Context, Rule, finding, leaf, transition

ID = "encryption-disabled"

ENCRYPTION = frozenset(
    {
        "at_rest_encryption_enabled",
        "enable_encryption",
        "encrypted",
        "encryption_enabled",
        "kms_encrypted",
        "storage_encrypted",
        "transit_encryption_enabled",
    }
)
# blocks whose `enabled` flag is the encryption switch (DynamoDB, OpenSearch)
ENCRYPTION_BLOCKS = frozenset(
    {"encrypt_at_rest", "node_to_node_encryption", "server_side_encryption"}
)


def evaluate(context: Context) -> Iterator[Finding]:
    for attribute in context.attributes:
        if not _is_switch(attribute.path) or flag(attribute.before) is not True:
            continue
        evidence = [transition(attribute.path, attribute.before, attribute.after)]
        name = show_path(attribute.path)
        if flag(attribute.after) is False:
            yield finding(
                context, ID, Severity.CRITICAL, "Encryption disabled", f"{name} turns off", evidence
            )
        elif attribute.kind is Kind.UNKNOWN and context.is_configured(attribute.path):
            yield finding(
                context,
                ID,
                Severity.CRITICAL,
                "Encryption may be disabled",
                f"{name} is unknown until apply",
                evidence,
                Confidence.LOW,
            )


def _is_switch(path: Path) -> bool:
    match path:
        case (*_, str(block), int(), "enabled"):
            return block in ENCRYPTION_BLOCKS
    return leaf(path) in ENCRYPTION


RULE = Rule(ID, "Encryption flag goes from true to false", Severity.CRITICAL, evaluate)
