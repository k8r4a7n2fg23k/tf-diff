from collections.abc import Iterator

from tfdiff.model.diff import Kind
from tfdiff.model.findings import Confidence, Evidence, Finding, Severity
from tfdiff.model.values import Sensitive, show_path
from tfdiff.rules.rule import Context, Rule, finding

ID = "sensitive-value-changed"


def evaluate(context: Context) -> Iterator[Finding]:
    # a secret the provider generates reads as changed on every replace; only a configured one
    # tells dependents to expect a new value
    configured = [
        attribute for attribute in context.attributes if context.is_configured(attribute.path)
    ]
    changed = [
        show_path(attribute.path) for attribute in configured if attribute.kind is Kind.SENSITIVE
    ]
    # a configured secret fed by a resource being replaced is unknown until apply
    pending = [
        show_path(attribute.path)
        for attribute in configured
        if attribute.kind is Kind.UNKNOWN and isinstance(attribute.before, Sensitive)
    ]
    if changed:
        yield finding(
            context,
            ID,
            Severity.INFO,
            "Sensitive value changes",
            "a secret or credential changes; dependents must pick up the new value",
            [Evidence("paths", ", ".join(changed))],
        )
    elif pending:
        yield finding(
            context,
            ID,
            Severity.INFO,
            "Sensitive value may change",
            "a secret or credential is unknown until apply",
            [Evidence("paths", ", ".join(pending))],
            Confidence.LOW,
        )


RULE = Rule(ID, "Sensitive attribute changes (the value is never shown)", Severity.INFO, evaluate)
