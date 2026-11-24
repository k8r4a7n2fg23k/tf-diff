from collections import Counter
from dataclasses import dataclass
from datetime import date

from tfdiff.model.diff import AttributeChange
from tfdiff.model.findings import Confidence, Finding, Severity
from tfdiff.model.graph import BlastRadius
from tfdiff.model.plan import Action, Change


@dataclass(frozen=True, slots=True)
class Score:
    """0-100 ordering aid, not a probability: the factors are the point."""

    value: int
    confidence: Confidence
    factors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Assessment:
    change: Change
    environment: str | None
    why: tuple[str, ...]
    attributes: tuple[AttributeChange, ...]
    dependencies: tuple[str, ...]
    blast: BlastRadius
    findings: tuple[Finding, ...]
    score: Score | None

    @property
    def severity(self) -> Severity | None:
        return max(
            (finding.severity for finding in self.findings),
            key=lambda level: level.rank,
            default=None,
        )


@dataclass(frozen=True, slots=True)
class Suppressed:
    finding: Finding
    reason: str
    until: date | None


@dataclass(frozen=True, slots=True)
class Report:
    format_version: str
    terraform_version: str | None
    tool: str | None
    environment: str | None
    rules_version: str
    inspected: int
    assessments: tuple[Assessment, ...]
    findings: tuple[Finding, ...]
    ignored: tuple[str, ...]
    # muted by the config: reported apart, never counted or failing `check`
    suppressed: tuple[Suppressed, ...]
    warnings: tuple[str, ...]


def action_counts(report: Report) -> dict[Action, int]:
    counts = Counter(assessment.change.action for assessment in report.assessments)
    return {action: counts[action] for action in Action if counts[action]}


def severity_counts(report: Report) -> dict[Severity, int]:
    counts = Counter(finding.severity for finding in report.findings)
    return {severity: counts[severity] for severity in reversed(Severity)}
