from enum import Enum

from typing_extensions import override


class StrEnum(str, Enum):
    """`enum.StrEnum` for 3.10: members print as their value."""

    # a bare (str, Enum) gives "Severity.HIGH" from str(), and from 3.11 in f-strings too,
    # which would leak into every report; Enum.__format__ goes through __str__
    @override
    def __str__(self) -> str:
        return str.__str__(self)
