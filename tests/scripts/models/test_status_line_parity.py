"""Parity test: the StatusLine model and validate_status_line() give the same verdicts.

The model validates a configuration file ahead of time; the runtime twin in
setup_environment.py validates the resolved configuration the setup applies
(the standalone script policy prevents a cross-import, so the two are
deliberate duplicates). Both must accept and reject the same
refresh-interval values and know the same status-line keys.

The one deliberate asymmetry is an unknown key: the model forbids it, while
the runtime twin warns about it and ignores it, the way _build_hooks_json()
treats a key a hook type does not support.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from scripts.models.environment_config import EnvironmentConfig
from scripts.models.environment_config import StatusLine
from scripts.setup_environment import STATUS_LINE_YAML_KEYS
from scripts.setup_environment import validate_status_line

ABSENT = object()

VALUES: list[object] = [60, 1, 0, -1, 1.5, 60.0, '60', True, False, None, ABSENT]


def _status_line(value: object) -> dict[str, Any]:
    status_line: dict[str, Any] = {'file': 'status.py'}
    if value is not ABSENT:
        status_line['refresh-interval'] = value
    return status_line


def _model_accepts(status_line: dict[str, Any]) -> bool:
    try:
        EnvironmentConfig.model_validate({
            'name': 'x',
            'hooks': {'files': ['hooks/status.py'], 'events': []},
            'status-line': status_line,
        })
    except ValidationError:
        return False
    return True


def test_both_know_the_same_keys() -> None:
    """The runtime's accepted keys are the model's field aliases."""
    model_keys = {field.alias or name for name, field in StatusLine.model_fields.items()}
    assert model_keys == STATUS_LINE_YAML_KEYS


@pytest.mark.parametrize('value', VALUES, ids=lambda v: 'absent' if v is ABSENT else repr(v))
def test_model_and_runtime_agree(value: object) -> None:
    """The model accepts a refresh-interval exactly when the runtime twin reports no error."""
    status_line = _status_line(value)
    assert _model_accepts(status_line) == (validate_status_line({'status-line': status_line}) == [])


@pytest.mark.parametrize('key', ['refreshInterval', 'refresh_interval'])
def test_unknown_key_rejected_by_model_and_warned_by_runtime(key: str, capsys: pytest.CaptureFixture[str]) -> None:
    """An unknown key fails the model, while the runtime warns and reports no error."""
    status_line = {'file': 'status.py', key: 60}
    assert not _model_accepts(status_line)
    assert validate_status_line({'status-line': status_line}) == []
    assert f'ignoring unknown key(s): {key} ' in capsys.readouterr().out
