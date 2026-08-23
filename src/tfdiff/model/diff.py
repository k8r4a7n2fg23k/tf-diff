from dataclasses import dataclass
from enum import StrEnum

from tfdiff.model.values import Path, Value


class Kind(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    UNKNOWN = "unknown"
    SENSITIVE = "sensitive"


@dataclass(frozen=True, slots=True)
class AttributeChange:
    path: Path
    kind: Kind
    before: Value
    after: Value
    is_forcing: bool
