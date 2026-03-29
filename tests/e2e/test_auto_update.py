"""E2E tests for automatic auto-update management.

Validates that version pinning correctly injects auto-update disable controls
across all four targets, and that latest/absent versions do not inject controls.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from scripts import setup_environment
from tests.e2e.validators import validate_auto_update_controls


def _load_fixture_config(name: str) -> dict[str, Any]:
    """Load a fixture YAML config by name."""
    fixture_path = Path(__file__).parent / 'fixtures' / name
    with fixture_path.open('r', encoding='utf-8') as f:
        result: dict[str, Any] = yaml.safe_load(f)
    return result


class TestPinnedVersionInjectsControls:
    """Verify that pinned version injects auto-update controls into all targets."""

    def test_pinned_version_injects_all_targets(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        home = e2e_isolated_home['home']
        config = _load_fixture_config('pinned_version_config.yaml')

        # Extract config sections
        global_config = config.get('global-config')
        user_settings = config.get('user-settings')
        env_variables = config.get('env-variables')
        os_env_variables = config.get('os-env-variables')

        # Normalize version
        version_str = str(config.get('claude-code-version', '')).strip()
        claude_code_version_normalized = None if version_str.lower() == 'latest' else version_str

        # Apply auto-update settings
        gc, us, ev, osev, warns, auto = setup_environment.apply_auto_update_settings(
            claude_code_version_normalized,
            global_config, user_settings, env_variables, os_env_variables,
        )

        # Verify all 4 targets injected
        assert gc is not None
        assert gc.get('autoUpdates') is False
        assert us is not None
        assert us.get('env', {}).get('DISABLE_AUTOUPDATER') == '1'
        assert ev is not None
        assert ev.get('DISABLE_AUTOUPDATER') == '1'
        assert osev is not None
        assert osev.get('DISABLE_AUTOUPDATER') == '1'

        # Write global config and verify file output
        if gc is not None:
            setup_environment.write_global_config(gc)
        errors = validate_auto_update_controls(home, pinned=True)
        assert not errors, '\n'.join(errors)

    def test_pinned_version_shows_auto_injected_items(self) -> None:
        config = _load_fixture_config('pinned_version_config.yaml')
        version_str = str(config.get('claude-code-version', '')).strip()
        claude_code_version_normalized = None if version_str.lower() == 'latest' else version_str

        _, _, _, _, _, auto = setup_environment.apply_auto_update_settings(
            claude_code_version_normalized,
            config.get('global-config'), config.get('user-settings'),
            config.get('env-variables'), config.get('os-env-variables'),
        )
        assert len(auto) == 4
        assert any('global-config' in item for item in auto)
        assert any('user-settings' in item for item in auto)
        assert any('env-variables' in item for item in auto)
        assert any('os-env-variables' in item for item in auto)


class TestLatestVersionNoControls:
    """Verify that latest/absent version does not inject controls."""

    def test_latest_version_does_not_inject(
        self, golden_config: dict[str, Any],
    ) -> None:
        version = golden_config.get('claude-code-version')
        version_str = str(version).strip() if version else ''
        normalized = None if not version_str or version_str.lower() == 'latest' else version_str

        gc, us, ev, osev, _, auto = setup_environment.apply_auto_update_settings(
            normalized,
            golden_config.get('global-config'),
            golden_config.get('user-settings'),
            golden_config.get('env-variables'),
            golden_config.get('os-env-variables'),
        )

        assert not auto
        # Global config should not have autoUpdates injected
        if gc is not None:
            assert gc.get('autoUpdates') is not False

    def test_absent_version_does_not_inject(self) -> None:
        gc, us, ev, osev, _, auto = setup_environment.apply_auto_update_settings(
            None, None, None, None, None,
        )
        assert not auto


class TestAutoMarkerInDryRun:
    """Verify [auto] markers appear in dry-run output for pinned versions."""

    def test_auto_marker_shown_in_plan_display(self) -> None:
        import io

        plan = setup_environment.InstallationPlan(
            config_name='Test',
            config_source='test',
            config_source_type='repo',
            config_version='1.0',
            auto_injected_items=[
                'global-config.autoUpdates: false',
                'user-settings.env.DISABLE_AUTOUPDATER: "1"',
                'env-variables.DISABLE_AUTOUPDATER: "1"',
                'os-env-variables.DISABLE_AUTOUPDATER: "1"',
            ],
        )
        buf = io.StringIO()
        setup_environment.display_installation_summary(plan, output=buf)
        output = buf.getvalue()
        assert '[auto]' in output
        assert 'autoUpdates' in output
        assert 'DISABLE_AUTOUPDATER' in output

    def test_no_auto_marker_when_no_items(self) -> None:
        import io

        plan = setup_environment.InstallationPlan(
            config_name='Test',
            config_source='test',
            config_source_type='repo',
            config_version='1.0',
        )
        buf = io.StringIO()
        setup_environment.display_installation_summary(plan, output=buf)
        output = buf.getvalue()
        assert '[auto]' not in output


class TestUserConflictRespected:
    """Verify user conflicts are respected with warnings."""

    def test_user_autoupdates_true_respected(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        home = e2e_isolated_home['home']
        global_config: dict[str, Any] = {'autoUpdates': True, 'editorMode': 'vim'}

        gc, _, _, _, warns, _ = setup_environment.apply_auto_update_settings(
            '2.1.85', global_config, {}, {}, {},
        )
        assert gc is not None
        assert gc['autoUpdates'] is True
        assert len(warns) >= 1
        assert any('Respecting user value' in w for w in warns)

        # Write and verify file preserves user value
        setup_environment.write_global_config(gc)
        claude_json = home / '.claude.json'
        data = json.loads(claude_json.read_text())
        assert data['autoUpdates'] is True


class TestPinnedVersionProfileConfig:
    """Verify that env_variables injection flows to create_profile_config."""

    def test_env_variables_flow_to_profile_config(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        home = e2e_isolated_home['home']
        config_dir = home / '.claude' / 'auto-update-test'
        config_dir.mkdir(parents=True, exist_ok=True)

        env_variables: dict[str, str] = {'TEST_VAR': 'value'}

        # Apply auto-update injection
        _, _, ev, _, _, _ = setup_environment.apply_auto_update_settings(
            '2.1.85', {}, {}, env_variables, {},
        )

        # Create profile config with injected env_variables
        assert ev is not None
        setup_environment.create_profile_config(
            hooks={},
            config_base_dir=config_dir,
            env=ev,
        )

        config_json = config_dir / 'config.json'
        assert config_json.exists()
        data = json.loads(config_json.read_text())
        assert data['env']['DISABLE_AUTOUPDATER'] == '1'
        assert data['env']['TEST_VAR'] == 'value'
