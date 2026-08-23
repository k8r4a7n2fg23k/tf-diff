from collections.abc import Mapping
from dataclasses import dataclass, field

from tfdiff.model.findings import Confidence, Severity


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str | None = None
    fail_on: Severity = Severity.HIGH
    # a finding below this confidence is reported but does not fail `check`
    fail_on_confidence: Confidence = Confidence.HIGH
    disabled: frozenset[str] = frozenset()
    severities: Mapping[str, Severity] = field(default_factory=dict[str, Severity])
    thresholds: Mapping[str, int] = field(default_factory=dict[str, int])
    ignore: tuple[str, ...] = ()
