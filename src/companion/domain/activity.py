from dataclasses import dataclass

from companion.domain.errors import ValidationError


@dataclass(frozen=True)
class ActivityAwarenessPreferences:
    enabled: bool = False

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise ValidationError("Activity awareness enabled must be a boolean.")
