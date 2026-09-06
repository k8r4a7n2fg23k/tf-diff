from collections.abc import Iterator

from tfdiff.model.findings import Evidence, Finding, Severity
from tfdiff.model.plan import Action
from tfdiff.rules.rule import Context, Rule, finding

ID = "destroy-production-resource"


def evaluate(context: Context) -> Iterator[Finding]:
    change = context.change
    # a deposed delete is the tail of create_before_destroy: expected cleanup, not a loss
    if change.action is not Action.DELETE or change.deposed:
        return
    if not context.is_production:
        return
    evidence = [Evidence("terraform reason", change.reason)] if change.reason else []
    yield finding(
        context,
        ID,
        Severity.CRITICAL,
        "Production resource destroyed",
        f"{change.resource.type} is deleted in a production environment",
        evidence,
    )


RULE = Rule(ID, "Resource deleted in production", Severity.CRITICAL, evaluate)
