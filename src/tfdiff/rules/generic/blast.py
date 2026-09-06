from collections.abc import Iterator

from tfdiff.model.findings import Evidence, Finding, Severity
from tfdiff.model.plan import Action
from tfdiff.model.text import shortlist
from tfdiff.rules.rule import Context, Rule, finding

ID = "wide-blast-radius"
DEFAULT_DEPENDENTS = 5
SHOWN = 10


def evaluate(context: Context) -> Iterator[Finding]:
    if context.change.action not in {Action.DELETE, Action.REPLACE}:
        return
    limit = context.threshold(ID, DEFAULT_DEPENDENTS)
    blast = context.blast
    if blast.total < limit:
        return
    yield finding(
        context,
        ID,
        Severity.MEDIUM,
        "Wide blast radius",
        f"{blast.total} resources depend on it (threshold {limit})",
        [Evidence("affected", shortlist((*blast.direct, *blast.indirect), SHOWN))],
    )


RULE = Rule(
    ID,
    "Destroyed or replaced resource has many dependents",
    Severity.MEDIUM,
    evaluate,
    DEFAULT_DEPENDENTS,
)
