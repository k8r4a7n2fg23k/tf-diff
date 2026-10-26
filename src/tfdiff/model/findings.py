from dataclasses import dataclass

from tfdiff.model.enums import StrEnum


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return list(Severity).index(self)


class Confidence(StrEnum):
    # low: the deciding value is unknown until apply
    LOW = "low"
    HIGH = "high"

    @property
    def rank(self) -> int:
        return list(Confidence).index(self)


@dataclass(frozen=True, slots=True)
class Evidence:
    label: str
    text: str


@dataclass(frozen=True, slots=True)
class Finding:
    rule: str
    severity: Severity
    address: str
    title: str
    reason: str
    evidence: tuple[Evidence, ...]
    confidence: Confidence


def order(finding: Finding) -> tuple[int, str, str]:
    """Report order: severity desc, then address, then rule id."""
    return (-finding.severity.rank, finding.address, finding.rule)
