"""Parity test: the AutoUpdate model and validate_auto_update() give the same verdicts.

The model validates a configuration file ahead of time; the runtime twin in
setup_environment.py validates the resolved configuration the setup applies.
Both carry an inline copy of the time pattern, and both must accept and
reject the same values.
"""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from scripts.models import environment_config
from scripts.models.environment_config import EnvironmentConfig
from scripts.setup_environment import _AUTO_UPDATE_TIME_PATTERN
from scripts.setup_environment import validate_auto_update

VALUES: list[object] = [
    {'time': '03:30'},
    {'time': '00:00'},
    {'time': '23:59'},
    {'time': '03:30', 'command': 'my-update --quiet'},
    {'time': '3:30'},
    {'time': '24:00'},
    {'time': '03:60'},
    {'time': '03:30', 'command': ''},
    {'time': '03:30', 'command': '   '},
    {'time': '03:30', 'weekday': 'mon'},
    {'command': 'my-update'},
]


def _model_accepts(value: object) -> bool:
    try:
        EnvironmentConfig.model_validate({'name': 'x', 'auto-update': value})
    except ValidationError:
        return False
    return True


def test_time_patterns_are_identical() -> None:
    """Both files carry the same time pattern."""
    assert isinstance(environment_config.AUTO_UPDATE_TIME_PATTERN, re.Pattern)
    assert environment_config.AUTO_UPDATE_TIME_PATTERN.pattern == _AUTO_UPDATE_TIME_PATTERN.pattern


@pytest.mark.parametrize('value', VALUES, ids=repr)
def test_model_and_runtime_agree(value: object) -> None:
    """The model accepts a value exactly when the runtime twin reports no error."""
    assert _model_accepts(value) == (validate_auto_update({'auto-update': value}) == [])


def test_both_accept_the_absent_key() -> None:
    """A configuration without auto-update is valid on both sides."""
    assert _model_accepts(None)
    assert validate_auto_update({}) == []
