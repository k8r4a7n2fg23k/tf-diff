from collections.abc import Iterator

from tfdiff.model.findings import Evidence, Finding, Severity
from tfdiff.model.plan import Action
from tfdiff.model.values import show_path
from tfdiff.rules.rule import Context, Rule, finding, transition

ID = "replace-resource"


def evaluate(context: Context) -> Iterator[Finding]:
    change = context.change
    if change.action is not Action.REPLACE:
        return
    paths = [show_path(path) for path in change.replace_paths]
    if paths:
        reason = f"{', '.join(paths)} cannot be updated in place"
    else:
        reason = f"Terraform plans replacement ({change.reason or 'no reason given'})"
    order = (
        "create before destroy"
        if change.actions[0] == "create"
        else "destroy before create: unavailable until the new one is up"
    )
    forcing = [attribute for attribute in context.attributes if attribute.is_forcing]
    yield finding(
        context,
        ID,
        Severity.MEDIUM if context.is_production else Severity.LOW,
        "Resource replaced",
        reason,
        [
            Evidence("order", order),
            *(
                transition(attribute.path, attribute.before, attribute.after)
                for attribute in forcing
            ),
        ],
    )


RULE = Rule(
    ID,
    "Resource is destroyed and recreated (medium in production, low elsewhere)",
    Severity.MEDIUM,
    evaluate,
)
