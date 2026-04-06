"""Parity test: InheritEntry's inline mergeable frozenset must match MERGEABLE_CONFIG_KEYS.

The InheritEntry model in environment_config.py necessarily duplicates the
MERGEABLE_CONFIG_KEYS frozenset from setup_environment.py (standalone script
policy prevents cross-import). This test enforces strict parity.
"""

from __future__ import annotations

from scripts.models.environment_config import InheritEntry
from scripts.setup_environment import MERGEABLE_CONFIG_KEYS


def _get_inherit_entry_mergeable_keys() -> frozenset[str]:
    """Extract the set of keys accepted by InheritEntry's merge-keys validator.

    Validates each key from MERGEABLE_CONFIG_KEYS individually against
    InheritEntry to determine which keys the inline frozenset accepts.

    Returns:
        frozenset of key names that InheritEntry accepts as valid merge-keys.
    """
    valid_keys: set[str] = set()
    for key in MERGEABLE_CONFIG_KEYS:
        try:
            entry = InheritEntry.model_validate({'config': 'test.yaml', 'merge-keys': [key]})
            if entry.merge_keys:
                valid_keys.update(entry.merge_keys)
        except Exception:
            pass  # Key rejected -- will be caught by assertion
    return frozenset(valid_keys)


def test_inherit_entry_accepts_all_mergeable_keys() -> None:
    """InheritEntry must accept every key in MERGEABLE_CONFIG_KEYS."""
    accepted = _get_inherit_entry_mergeable_keys()
    missing = MERGEABLE_CONFIG_KEYS - accepted
    assert not missing, (
        f'InheritEntry rejects keys that are in MERGEABLE_CONFIG_KEYS: {sorted(missing)}. '
        f'Update the inline mergeable frozenset in InheritEntry.validate_merge_keys().'
    )


def test_inherit_entry_rejects_non_mergeable_keys() -> None:
    """InheritEntry must reject keys NOT in MERGEABLE_CONFIG_KEYS."""
    fake_keys = ['nonexistent-key', 'fake-key', 'bogus']
    for key in fake_keys:
        try:
            InheritEntry.model_validate({'config': 'test.yaml', 'merge-keys': [key]})
            raise AssertionError(f'InheritEntry should reject non-mergeable key: {key}')
        except AssertionError:
            raise
        except Exception:
            pass  # Expected rejection


def test_environment_config_mergeable_matches_inherit_entry() -> None:
    """EnvironmentConfig.validate_merge_keys inline set must match InheritEntry's."""
    from scripts.models.environment_config import EnvironmentConfig

    # Extract from EnvironmentConfig by attempting validation
    ec_valid: set[str] = set()
    for key in MERGEABLE_CONFIG_KEYS:
        try:
            EnvironmentConfig.model_validate({
                'name': 'test',
                'merge-keys': [key],
            })
            ec_valid.add(key)
        except Exception:
            pass

    ie_valid = _get_inherit_entry_mergeable_keys()
    assert ec_valid == ie_valid, (
        f'EnvironmentConfig and InheritEntry have different mergeable key sets.\n'
        f'Only in EnvironmentConfig: {sorted(ec_valid - ie_valid)}\n'
        f'Only in InheritEntry: {sorted(ie_valid - ec_valid)}'
    )


def test_mergeable_keys_match_runtime_constant() -> None:
    """Both inline frozensets must exactly match MERGEABLE_CONFIG_KEYS."""
    ie_valid = _get_inherit_entry_mergeable_keys()
    assert ie_valid == MERGEABLE_CONFIG_KEYS, (
        f'InheritEntry mergeable keys differ from MERGEABLE_CONFIG_KEYS.\n'
        f'Only in MERGEABLE_CONFIG_KEYS: {sorted(MERGEABLE_CONFIG_KEYS - ie_valid)}\n'
        f'Only in InheritEntry: {sorted(ie_valid - MERGEABLE_CONFIG_KEYS)}'
    )
