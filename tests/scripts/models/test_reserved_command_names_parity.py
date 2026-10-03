"""Parity tests: the reserved command names must match in both scripts.

environment_config.py duplicates RESERVED_COMMAND_NAMES from
setup_environment.py (standalone script policy prevents cross-import), so a
configuration the model accepts is never refused at runtime for its command
names, and the reverse.
"""

from __future__ import annotations

import argparse

import pytest
from pydantic import ValidationError

from scripts.models.environment_config import RESERVED_COMMAND_NAMES as MODEL_RESERVED_COMMAND_NAMES
from scripts.models.environment_config import EnvironmentConfig
from scripts.setup_environment import RESERVED_COMMAND_NAMES
from scripts.setup_environment import resolve_command_names


def _runtime_errors(name: str) -> list[str]:
    """Return the runtime validation errors for a configuration naming one command."""
    args = argparse.Namespace(command_names=None, profile=None, origins={})
    _resolved, errors = resolve_command_names(args, {'command-names': [name]})
    return errors


def _model_accepts(name: str) -> bool:
    """Report whether the model accepts a configuration naming one command."""
    try:
        EnvironmentConfig.model_validate({'name': 'x', 'command-names': [name], 'command-defaults': {}})
    except ValidationError:
        return False
    return True


def test_reserved_command_names_match_between_scripts() -> None:
    """Both RESERVED_COMMAND_NAMES copies must be identical sets."""
    assert RESERVED_COMMAND_NAMES == MODEL_RESERVED_COMMAND_NAMES, (
        f'RESERVED_COMMAND_NAMES out of sync between scripts.\n'
        f'Only in setup_environment.py: {sorted(RESERVED_COMMAND_NAMES - MODEL_RESERVED_COMMAND_NAMES)}\n'
        f'Only in environment_config.py: {sorted(MODEL_RESERVED_COMMAND_NAMES - RESERVED_COMMAND_NAMES)}'
    )


def test_reserved_names_are_stored_in_lowercase() -> None:
    """Matching casefolds the candidate, so every entry must already be lowercase."""
    assert all(name == name.casefold() for name in RESERVED_COMMAND_NAMES)


@pytest.mark.parametrize('name', sorted(RESERVED_COMMAND_NAMES) + ['ALL', 'Projects'])
def test_both_layers_refuse_every_reserved_name(name: str) -> None:
    """The model and the runtime give the same verdict on each reserved name."""
    assert not _model_accepts(name)
    assert _runtime_errors(name)


@pytest.mark.parametrize('name', ['claude-personal', 'all-in-one', 'my-projects', 'baseline'])
def test_both_layers_accept_ordinary_names(name: str) -> None:
    """Names that only contain a reserved word pass both layers."""
    assert _model_accepts(name)
    assert _runtime_errors(name) == []
