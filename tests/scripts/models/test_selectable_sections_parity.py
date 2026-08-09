"""Parity tests: components schema duplicates in both scripts must match.

The components schema in environment_config.py necessarily duplicates two
pieces of setup_environment.py (standalone script policy prevents
cross-import): the SELECTABLE_SECTIONS frozenset and the files-to-download
selector identity computation (_download_selector_identity mirrors
_files_download_identity). These tests enforce strict parity and the
structural invariants the components registry relies on.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from scripts.models.environment_config import SELECTABLE_SECTIONS as MODEL_SELECTABLE_SECTIONS
from scripts.models.environment_config import Component
from scripts.models.environment_config import _download_selector_identity
from scripts.setup_environment import KNOWN_CONFIG_KEYS
from scripts.setup_environment import MERGEABLE_CONFIG_KEYS
from scripts.setup_environment import SELECTABLE_SECTIONS
from scripts.setup_environment import _files_download_identity


def test_selectable_sections_match_between_scripts() -> None:
    """Both SELECTABLE_SECTIONS copies must be identical sets."""
    assert SELECTABLE_SECTIONS == MODEL_SELECTABLE_SECTIONS, (
        f'SELECTABLE_SECTIONS out of sync between scripts.\n'
        f'Only in setup_environment.py: {sorted(SELECTABLE_SECTIONS - MODEL_SELECTABLE_SECTIONS)}\n'
        f'Only in environment_config.py: {sorted(MODEL_SELECTABLE_SECTIONS - SELECTABLE_SECTIONS)}'
    )


def test_selectable_sections_subset_of_known_config_keys() -> None:
    """Every selectable section must be a real top-level config key."""
    unknown = SELECTABLE_SECTIONS - KNOWN_CONFIG_KEYS
    assert not unknown, (
        f'SELECTABLE_SECTIONS contains keys not in KNOWN_CONFIG_KEYS: {sorted(unknown)}'
    )


def test_components_key_registered_but_not_selectable() -> None:
    """The components registry itself is a known, mergeable, non-selectable key."""
    assert 'components' in KNOWN_CONFIG_KEYS
    assert 'components' in MERGEABLE_CONFIG_KEYS
    assert 'components' not in SELECTABLE_SECTIONS


def test_component_includes_accepts_every_selectable_section() -> None:
    """The Component includes validator must accept every runtime section key."""
    for section in SELECTABLE_SECTIONS:
        component = Component.model_validate({'name': 'probe', 'includes': {section: ['x']}})
        assert section in component.includes


def test_component_includes_rejects_non_selectable_key() -> None:
    """The Component includes validator must reject keys outside the allowlist."""
    with pytest.raises(ValidationError, match='not selectable'):
        Component.model_validate({'name': 'probe', 'includes': {'command-names': ['x']}})


@pytest.mark.parametrize(
    ('source', 'dest'),
    [
        ('files/f.txt', '~/.claude/f.txt'),
        ('files/f.txt', '~/.claude/dir/'),
        ('files/f.txt', '~/.claude/dir\\'),
        ('https://example.com/a/b.txt?x=1', '~/.claude/dir/'),
        ('some\\path\\file.py', '~/.claude/dir/'),
        (
            'https://gitlab.com/api/v4/projects/123/repository/files/sub%2Ffile.py/raw?ref=main',
            '~/.claude/dir/',
        ),
    ],
)
def test_download_selector_identity_matches_runtime(source: str, dest: str) -> None:
    """The model's selector identity must equal the runtime merge identity."""
    assert _download_selector_identity(source, dest) == _files_download_identity(
        {'source': source, 'dest': dest},
    )
