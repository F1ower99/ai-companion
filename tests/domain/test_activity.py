import importlib
import importlib.util

import pytest

from companion.domain.errors import ValidationError


def _activity_domain():
    spec = importlib.util.find_spec("companion.domain.activity")
    assert spec is not None
    return importlib.import_module("companion.domain.activity")


def test_activity_awareness_preferences_default_to_disabled():
    preferences = _activity_domain().ActivityAwarenessPreferences()
    assert preferences.enabled is False


@pytest.mark.parametrize("value", [0, 1, "true", None])
def test_activity_awareness_preferences_reject_non_boolean_values(value):
    preferences = _activity_domain().ActivityAwarenessPreferences
    with pytest.raises(ValidationError):
        preferences(enabled=value)
