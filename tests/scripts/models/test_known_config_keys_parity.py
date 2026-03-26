"""Parity test: KNOWN_CONFIG_KEYS must match EnvironmentConfig.model_fields exactly.

Strict bidirectional check with ZERO exceptions.
If this test fails, it means either:
1. A new field was added to EnvironmentConfig but not to KNOWN_CONFIG_KEYS
2. A new key was added to KNOWN_CONFIG_KEYS but not to EnvironmentConfig
3. An alias was changed causing a mismatch

Fix: Update BOTH KNOWN_CONFIG_KEYS and EnvironmentConfig simultaneously.
"""

from __future__ import annotations

from scripts.models.environment_config import EnvironmentConfig
from scripts.setup_environment import KNOWN_CONFIG_KEYS


def _get_yaml_keys_from_model() -> frozenset[str]:
    """Extract YAML-level key names from EnvironmentConfig model fields.

    For each field:
    - If the field has an alias, use the alias (this is the YAML key)
    - If the field has no alias, use the field name (Python name = YAML key)

    Returns:
        frozenset of YAML key names.
    """
    yaml_keys: set[str] = set()
    for field_name, field_info in EnvironmentConfig.model_fields.items():
        alias = field_info.alias
        yaml_keys.add(alias or field_name)
    return frozenset(yaml_keys)


def test_known_config_keys_match_model_fields_forward() -> None:
    """Every KNOWN_CONFIG_KEYS entry must correspond to an EnvironmentConfig field."""
    model_yaml_keys = _get_yaml_keys_from_model()
    extra_in_known = KNOWN_CONFIG_KEYS - model_yaml_keys
    assert not extra_in_known, (
        f'KNOWN_CONFIG_KEYS contains keys not in EnvironmentConfig: {sorted(extra_in_known)}. '
        f'Remove from KNOWN_CONFIG_KEYS or add to EnvironmentConfig.'
    )


def test_model_fields_match_known_config_keys_reverse() -> None:
    """Every EnvironmentConfig field must have a corresponding KNOWN_CONFIG_KEYS entry."""
    model_yaml_keys = _get_yaml_keys_from_model()
    extra_in_model = model_yaml_keys - KNOWN_CONFIG_KEYS
    assert not extra_in_model, (
        f'EnvironmentConfig has fields not in KNOWN_CONFIG_KEYS: {sorted(extra_in_model)}. '
        f'Add to KNOWN_CONFIG_KEYS or remove from EnvironmentConfig.'
    )


def test_bidirectional_exact_match() -> None:
    """KNOWN_CONFIG_KEYS and EnvironmentConfig model fields must be identical sets."""
    model_yaml_keys = _get_yaml_keys_from_model()
    assert model_yaml_keys == KNOWN_CONFIG_KEYS, (
        f'KNOWN_CONFIG_KEYS and EnvironmentConfig are out of sync.\n'
        f'In KNOWN_CONFIG_KEYS only: {sorted(KNOWN_CONFIG_KEYS - model_yaml_keys)}\n'
        f'In EnvironmentConfig only: {sorted(model_yaml_keys - KNOWN_CONFIG_KEYS)}'
    )
