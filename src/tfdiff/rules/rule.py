from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass

from tfdiff.model.diff import AttributeChange
from tfdiff.model.findings import Confidence, Evidence, Finding, Severity
from tfdiff.model.graph import BlastRadius
from tfdiff.model.plan import Change
from tfdiff.model.settings import Settings
from tfdiff.model.values import Path, Value, show, show_path


def is_production(environment: str | None, settings: Settings) -> bool:
    return environment is not None and environment.casefold() in settings.production_names


@dataclass(frozen=True, slots=True)
class Context:
    """Everything a rule may look at. Rules never see plan JSON."""

    change: Change
    attributes: tuple[AttributeChange, ...]
    environment: str | None
    blast: BlastRadius
    settings: Settings

    @property
    def is_production(self) -> bool:
        return is_production(self.environment, self.settings)

    def is_configured(self, path: Path) -> bool:
        """Whether the author sets the attribute; True when the plan has no configuration.

        A computed attribute turns unknown on every replace, so only a configured unknown is
        worth a low-confidence finding.
        """
        configured = self.change.configured
        return configured is None or path[0] in configured

    def threshold(self, rule: str, default: int) -> int:
        return self.settings.thresholds.get(rule, default)


@dataclass(frozen=True, slots=True)
class Rule:
    id: str
    title: str
    severity: Severity
    evaluate: Callable[[Context], Iterator[Finding]]
    threshold: int | None = None


def finding(  # noqa: PLR0913, PLR0917  - one argument per part of a Finding
    context: Context,
    rule: str,
    severity: Severity,
    title: str,
    reason: str,
    evidence: Iterable[Evidence] = (),
    confidence: Confidence = Confidence.HIGH,
) -> Finding:
    """Build a finding that leads with action, environment and dependents."""
    change = context.change
    common = (
        Evidence("action", change.action_label),
        Evidence("environment", context.environment or "not set"),
        Evidence(
            "dependents",
            f"{len(context.blast.direct)} direct, {len(context.blast.indirect)} indirect",
        ),
    )
    return Finding(
        rule=rule,
        severity=severity,
        address=change.address,
        title=title,
        reason=reason,
        evidence=(*common, *evidence),
        confidence=confidence,
    )


def transition(path: Path, before: Value, after: Value) -> Evidence:
    return Evidence(show_path(path), f"{show(before)} -> {show(after)}")


def leaf(path: Path) -> str:
    """Last named segment: `ingress[0].cidr_blocks[1]` -> `cidr_blocks`."""
    return next(part for part in reversed(path) if isinstance(part, str))
