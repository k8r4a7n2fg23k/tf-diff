from tfdiff.rules.aws import rds, s3, security_group, stateful
from tfdiff.rules.generic import blast, capacity, destroy, encryption, replace, sensitive
from tfdiff.rules.rule import Rule

# bump with any change to a rule's logic or severity
RULES_VERSION = "1"

RULES: tuple[Rule, ...] = (
    rds.BACKUP_RULE,
    destroy.RULE,
    encryption.RULE,
    rds.PUBLIC_RULE,
    capacity.REDUCE_RULE,
    capacity.REDUNDANCY_RULE,
    replace.RULE,
    stateful.RULE,
    s3.RULE,
    security_group.RULE,
    sensitive.RULE,
    blast.RULE,
)

BY_ID: dict[str, Rule] = {rule.id: rule for rule in RULES}
