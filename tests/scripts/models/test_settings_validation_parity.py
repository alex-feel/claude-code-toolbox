"""Parity test: settings-validation constants must match across both modules.

setup_environment.py and scripts/models/environment_config.py each define the
same set of constants that drive user-settings and global-config validation.
The standalone script policy forbids a cross-import, so the two definitions are
deliberate duplicates. This test enforces strict equality between them: every
shared constant, plus the two excluded-key frozensets, must be identical in both
modules.

If this test fails, a validation constant was changed in one module but not the
other. Fix: update BOTH modules so the constants match exactly.
"""

from __future__ import annotations

from scripts.models import environment_config as model_mod
from scripts.setup_environment import EFFORT_LEVEL_VALUES as SETUP_EFFORT_LEVEL_VALUES
from scripts.setup_environment import ENV_VAR_NAME_PATTERN as SETUP_ENV_VAR_NAME_PATTERN
from scripts.setup_environment import GLOBAL_CONFIG_EXCLUDED_KEYS as SETUP_GLOBAL_CONFIG_EXCLUDED_KEYS
from scripts.setup_environment import GLOBAL_CONFIG_SETTINGS_ONLY_KEYS as SETUP_GLOBAL_CONFIG_SETTINGS_ONLY_KEYS
from scripts.setup_environment import MAX_EFFORT_MODEL_MARKERS as SETUP_MAX_EFFORT_MODEL_MARKERS
from scripts.setup_environment import PERMISSIONS_DEFAULT_MODE_VALUES as SETUP_PERMISSIONS_DEFAULT_MODE_VALUES
from scripts.setup_environment import PERMISSIONS_KEBAB_KEY_CORRECTIONS as SETUP_PERMISSIONS_KEBAB_KEY_CORRECTIONS
from scripts.setup_environment import USER_SETTINGS_EXCLUDED_KEYS as SETUP_USER_SETTINGS_EXCLUDED_KEYS
from scripts.setup_environment import USER_SETTINGS_GLOBAL_ONLY_KEYS as SETUP_USER_SETTINGS_GLOBAL_ONLY_KEYS
from scripts.setup_environment import USER_SETTINGS_KEBAB_KEY_CORRECTIONS as SETUP_USER_SETTINGS_KEBAB_KEY_CORRECTIONS
from scripts.setup_environment import USER_SETTINGS_ROOT_ONLY_KEYS as SETUP_USER_SETTINGS_ROOT_ONLY_KEYS
from scripts.setup_environment import XHIGH_EFFORT_MODEL_MARKERS as SETUP_XHIGH_EFFORT_MODEL_MARKERS


def test_xhigh_effort_model_markers_parity() -> None:
    """XHIGH_EFFORT_MODEL_MARKERS is identical in both modules."""
    assert SETUP_XHIGH_EFFORT_MODEL_MARKERS == model_mod.XHIGH_EFFORT_MODEL_MARKERS


def test_max_effort_model_markers_parity() -> None:
    """MAX_EFFORT_MODEL_MARKERS is identical in both modules."""
    assert SETUP_MAX_EFFORT_MODEL_MARKERS == model_mod.MAX_EFFORT_MODEL_MARKERS


def test_effort_level_values_parity() -> None:
    """EFFORT_LEVEL_VALUES is identical in both modules."""
    assert SETUP_EFFORT_LEVEL_VALUES == model_mod.EFFORT_LEVEL_VALUES


def test_permissions_default_mode_values_parity() -> None:
    """PERMISSIONS_DEFAULT_MODE_VALUES is identical in both modules."""
    assert SETUP_PERMISSIONS_DEFAULT_MODE_VALUES == model_mod.PERMISSIONS_DEFAULT_MODE_VALUES


def test_user_settings_kebab_key_corrections_parity() -> None:
    """USER_SETTINGS_KEBAB_KEY_CORRECTIONS is identical in both modules."""
    assert SETUP_USER_SETTINGS_KEBAB_KEY_CORRECTIONS == model_mod.USER_SETTINGS_KEBAB_KEY_CORRECTIONS


def test_permissions_kebab_key_corrections_parity() -> None:
    """PERMISSIONS_KEBAB_KEY_CORRECTIONS is identical in both modules."""
    assert SETUP_PERMISSIONS_KEBAB_KEY_CORRECTIONS == model_mod.PERMISSIONS_KEBAB_KEY_CORRECTIONS


def test_user_settings_root_only_keys_parity() -> None:
    """USER_SETTINGS_ROOT_ONLY_KEYS is identical in both modules."""
    assert SETUP_USER_SETTINGS_ROOT_ONLY_KEYS == model_mod.USER_SETTINGS_ROOT_ONLY_KEYS


def test_user_settings_global_only_keys_parity() -> None:
    """USER_SETTINGS_GLOBAL_ONLY_KEYS is identical in both modules."""
    assert SETUP_USER_SETTINGS_GLOBAL_ONLY_KEYS == model_mod.USER_SETTINGS_GLOBAL_ONLY_KEYS


def test_global_config_settings_only_keys_parity() -> None:
    """GLOBAL_CONFIG_SETTINGS_ONLY_KEYS is identical in both modules."""
    assert SETUP_GLOBAL_CONFIG_SETTINGS_ONLY_KEYS == model_mod.GLOBAL_CONFIG_SETTINGS_ONLY_KEYS


def test_env_var_name_pattern_parity() -> None:
    """ENV_VAR_NAME_PATTERN compiles the same source in both modules."""
    assert SETUP_ENV_VAR_NAME_PATTERN.pattern == model_mod.ENV_VAR_NAME_PATTERN.pattern


def test_user_settings_excluded_keys_parity() -> None:
    """USER_SETTINGS_EXCLUDED_KEYS holds the same keys in both modules."""
    assert set(SETUP_USER_SETTINGS_EXCLUDED_KEYS) == set(model_mod.USER_SETTINGS_EXCLUDED_KEYS)


def test_global_config_excluded_keys_parity() -> None:
    """GLOBAL_CONFIG_EXCLUDED_KEYS is identical in both modules."""
    assert SETUP_GLOBAL_CONFIG_EXCLUDED_KEYS == model_mod.GLOBAL_CONFIG_EXCLUDED_KEYS
