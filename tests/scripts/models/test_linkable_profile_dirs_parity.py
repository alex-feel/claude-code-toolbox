"""Parity tests: the linkable profile directories must match in both scripts.

environment_config.py duplicates LINKABLE_PROFILE_DIRS from
setup_environment.py (standalone script policy prevents cross-import), so a
link-dirs value the model accepts is never refused at runtime, and the
reverse.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from scripts.models.environment_config import LINKABLE_PROFILE_DIRS as MODEL_LINKABLE_PROFILE_DIRS
from scripts.models.environment_config import EnvironmentConfig
from scripts.setup_environment import LINKABLE_PROFILE_DIRS
from scripts.setup_environment import RESERVED_COMMAND_NAMES
from scripts.setup_environment import parse_link_dirs


def _model_accepts(value: list[str]) -> bool:
    """Report whether the model accepts a configuration with the given link-dirs."""
    try:
        EnvironmentConfig.model_validate({'name': 'x', 'link-dirs': value})
    except ValidationError:
        return False
    return True


def _runtime_accepts(value: list[str]) -> bool:
    """Report whether the runtime parser accepts the same link-dirs value."""
    _entries, errors = parse_link_dirs(value, 'link-dirs')
    return not errors


def test_linkable_profile_dirs_match_between_scripts() -> None:
    """Both LINKABLE_PROFILE_DIRS copies must be identical, order included."""
    assert LINKABLE_PROFILE_DIRS == MODEL_LINKABLE_PROFILE_DIRS, (
        f'LINKABLE_PROFILE_DIRS out of sync between scripts.\n'
        f'setup_environment.py: {LINKABLE_PROFILE_DIRS}\n'
        f'environment_config.py: {MODEL_LINKABLE_PROFILE_DIRS}'
    )


def test_linkable_profile_dirs_are_the_eight_entries_in_display_order() -> None:
    """The entries are the directories of a Claude Code configuration home a profile can link."""
    assert LINKABLE_PROFILE_DIRS == (
        'skills', 'agents', 'commands', 'rules', 'hooks', 'output-styles', 'prompts', 'projects',
    )


def test_every_linkable_entry_is_a_reserved_command_name() -> None:
    """A profile named after an entry would install into that entry of the base ~/.claude."""
    assert set(LINKABLE_PROFILE_DIRS) <= RESERVED_COMMAND_NAMES


@pytest.mark.parametrize(
    'value',
    [['all'], ['none'], ['projects'], ['skills', 'projects'], list(LINKABLE_PROFILE_DIRS), ['ALL'], ['Projects']],
)
def test_both_layers_accept_every_valid_value(value: list[str]) -> None:
    """The model and the runtime give the same verdict on each valid link-dirs value."""
    assert _model_accepts(value)
    assert _runtime_accepts(value)


@pytest.mark.parametrize(
    'value',
    [['settings'], ['all', 'skills'], ['none', 'projects'], ['skills', 'skills'], [''], ['all', 'none']],
)
def test_both_layers_refuse_every_invalid_value(value: list[str]) -> None:
    """An unknown entry, a sentinel beside an entry, a duplicate, or an empty name is refused by both."""
    assert not _model_accepts(value)
    assert not _runtime_accepts(value)
