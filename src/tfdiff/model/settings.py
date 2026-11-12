from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date

from tfdiff.model.findings import Confidence, Severity

# tag keys as the user writes them, matched in any case; earlier wins when a resource has several
ENVIRONMENT_TAGS = ("Environment", "env")
# casefolded
PRODUCTION_NAMES = frozenset({"production", "prod", "prd"})


@dataclass(frozen=True, slots=True)
class Suppression:
    """One rule muted on matching resources, with the reason and the last day it holds."""

    rule: str
    # full address, `*` and `?` are wildcards, as in `ignore`
    resource: str
    reason: str
    until: date | None = None


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str | None = None
    environment_tags: tuple[str, ...] = ENVIRONMENT_TAGS
    production_names: frozenset[str] = PRODUCTION_NAMES
    fail_on: Severity = Severity.HIGH
    # a finding below this confidence is reported but does not fail `check`
    fail_on_confidence: Confidence = Confidence.HIGH
    disabled: frozenset[str] = frozenset()
    severities: Mapping[str, Severity] = field(default_factory=dict[str, Severity])
    thresholds: Mapping[str, int] = field(default_factory=dict[str, int])
    ignore: tuple[str, ...] = ()
    suppress: tuple[Suppression, ...] = ()
    # cli.py passes the date in; None means no `until` has passed
    today: date | None = None
