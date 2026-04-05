"""E2E tests for IDE extension version pinning management.

Validates that version pinning correctly injects IDE extension auto-install
disable controls, and that latest/absent versions do not inject controls.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from scripts import setup_environment
from tests.e2e.validators import validate_ide_extension_controls


def _load_fixture_config(name: str) -> dict[str, Any]:
    """Load a fixture YAML config by name."""
    fixture_path = Path(__file__).parent / 'fixtures' / name
    with fixture_path.open('r', encoding='utf-8') as f:
        result: dict[str, Any] = yaml.safe_load(f)
    return result


class TestPinnedVersionInjectsIdeControls:
    """Verify that pinned version injects IDE extension controls into all targets."""

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

        # Apply IDE extension settings
        gc, us, ev, osev, warns, auto = setup_environment.apply_ide_extension_settings(
            claude_code_version_normalized,
            global_config, user_settings, env_variables, os_env_variables,
        )

        # Verify all 4 targets injected
        assert gc is not None
        assert gc.get('autoInstallIdeExtension') is False
        assert us is not None
        assert us.get('env', {}).get('CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL') == '1'
        assert ev is not None
        assert ev.get('CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL') == '1'
        assert osev is not None
        assert osev.get('CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL') == '1'

        # Write global config with dual-write when command-names is present
        primary_command = config.get('command-names', [None])[0]
        artifact_dir = home / '.claude' / primary_command if primary_command else None
        if artifact_dir:
            artifact_dir.mkdir(parents=True, exist_ok=True)

        if gc is not None:
            setup_environment.write_global_config(
                gc, artifact_base_dir=artifact_dir,
            )

        errors = validate_ide_extension_controls(
            home, pinned=True, command_name=primary_command,
        )
        assert not errors, '\n'.join(errors)


class TestLatestVersionNoIdeControls:
    """Verify that latest/absent version does not inject IDE extension controls."""

    def test_latest_version_does_not_inject(self) -> None:
        gc, us, ev, osev, _, auto = setup_environment.apply_ide_extension_settings(
            None, None, None, None, None,
        )
        assert not auto

    def test_absent_version_does_not_inject(self) -> None:
        gc, us, ev, osev, _, auto = setup_environment.apply_ide_extension_settings(
            None, None, None, None, None,
        )
        assert not auto


class TestIdeAutoMarkerInDryRun:
    """Verify [auto] markers for IDE extension items in auto_injected list."""

    def test_auto_marker_items_present(self) -> None:
        config = _load_fixture_config('pinned_version_config.yaml')
        version_str = str(config.get('claude-code-version', '')).strip()
        claude_code_version_normalized = None if version_str.lower() == 'latest' else version_str

        _, _, _, _, _, auto = setup_environment.apply_ide_extension_settings(
            claude_code_version_normalized,
            config.get('global-config'), config.get('user-settings'),
            config.get('env-variables'), config.get('os-env-variables'),
        )
        assert len(auto) == 4
        assert any('autoInstallIdeExtension' in item for item in auto)
        assert any('CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL' in item for item in auto)

    def test_no_auto_marker_when_latest(self) -> None:
        _, _, _, _, _, auto = setup_environment.apply_ide_extension_settings(
            None, None, None, None, None,
        )
        assert len(auto) == 0


class TestIdeUserConflictRespected:
    """Verify user-explicit autoInstallIdeExtension: true is preserved."""

    def test_user_autoinstall_true_respected(self) -> None:
        gc = {'autoInstallIdeExtension': True}
        gc_out, _, _, _, warns, auto = setup_environment.apply_ide_extension_settings(
            '2.1.85', gc, None, None, None,
        )
        assert gc_out is not None
        assert gc_out['autoInstallIdeExtension'] is True
        assert any('Respecting user value' in w for w in warns)
        # Other targets still get injected
        assert len(auto) == 3  # T2, T3, T4 only


class TestIdeStaleCleanup:
    """Verify stale IDE extension controls are cleaned when switching to latest."""

    def test_unpinned_cleans_all(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        home = e2e_isolated_home['home']
        claude_dir = home / '.claude'
        cmd_dir = claude_dir / 'test-cmd'
        cmd_dir.mkdir(parents=True, exist_ok=True)

        # Pre-populate stale controls
        settings = claude_dir / 'settings.json'
        settings.write_text(json.dumps({
            'env': {'CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL': '1'},
        }))
        cmd_settings = cmd_dir / 'settings.json'
        cmd_settings.write_text(json.dumps({
            'env': {'CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL': '1'},
        }))
        claude_json = home / '.claude.json'
        claude_json.write_text(json.dumps({'autoInstallIdeExtension': False}))
        cmd_claude_json = cmd_dir / '.claude.json'
        cmd_claude_json.write_text(json.dumps({'autoInstallIdeExtension': False}))

        # Run cleanup with not-pinned
        setup_environment.cleanup_stale_ide_extension_controls(home, is_pinned=False)

        # Verify all cleaned
        errors = validate_ide_extension_controls(home, pinned=False)
        assert not errors, '\n'.join(errors)
