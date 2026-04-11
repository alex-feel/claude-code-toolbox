"""E2E tests for automatic auto-update management.

Validates that version pinning correctly injects auto-update disable controls
across all four targets, and that latest/absent versions do not inject controls.
"""

from __future__ import annotations

import json
from pathlib import Path
from subprocess import CompletedProcess
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

        # Write global config with dual-write when command-names is present
        primary_command = config.get('command-names', [None])[0]
        artifact_dir = home / '.claude' / primary_command if primary_command else None
        if artifact_dir:
            artifact_dir.mkdir(parents=True, exist_ok=True)

        if gc is not None:
            setup_environment.write_global_config(
                gc, artifact_base_dir=artifact_dir,
            )

        errors = validate_auto_update_controls(
            home, pinned=True, command_name=primary_command,
        )
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
        setup_environment.create_profile_config({'env': ev}, config_dir)

        config_json = config_dir / 'config.json'
        assert config_json.exists()
        data = json.loads(config_json.read_text())
        assert data['env']['DISABLE_AUTOUPDATER'] == '1'
        assert data['env']['TEST_VAR'] == 'value'


class TestNullAsDeleteTarget2:
    """Verify _remove_auto_update_controls Target 2 uses None for RFC 7396 merge."""

    def test_remove_uses_null_as_delete_for_settings_env(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """When unpinning, DISABLE_AUTOUPDATER is removed from disk via merge."""
        home = e2e_isolated_home['home']
        claude_dir = home / '.claude'

        # Pre-populate settings.json with stale DISABLE_AUTOUPDATER
        settings_path = claude_dir / 'settings.json'
        settings_path.write_text(json.dumps({
            'env': {'DISABLE_AUTOUPDATER': '1', 'OTHER_VAR': 'keep'},
        }))

        # Apply with no version pin (triggers removal path)
        gc, us, ev, osev, _, _ = setup_environment.apply_auto_update_settings(
            None, {}, {'env': {'DISABLE_AUTOUPDATER': '1', 'OTHER_VAR': 'keep'}}, {}, {},
        )

        # user_settings Target 2 should have None (null-as-delete), not absent
        assert us is not None
        assert us['env']['DISABLE_AUTOUPDATER'] is None, \
            'Target 2 must use None (not del) for RFC 7396 null-as-delete'
        assert us['env']['OTHER_VAR'] == 'keep'

        # Write via merge to verify disk effect
        setup_environment.write_user_settings(us, claude_dir)

        # Verify disk: DISABLE_AUTOUPDATER removed, OTHER_VAR preserved
        data = json.loads(settings_path.read_text())
        assert 'DISABLE_AUTOUPDATER' not in data.get('env', {}), \
            'DISABLE_AUTOUPDATER should be removed from disk via null-as-delete merge'
        assert data['env']['OTHER_VAR'] == 'keep'


class TestCrossLocationStaleCleanup:
    """Verify cleanup helpers sweep all settings.json and .claude.json locations."""

    def test_unpinned_cleans_all_settings_json(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Not pinned: removes DISABLE_AUTOUPDATER from ALL settings.json locations."""
        home = e2e_isolated_home['home']
        claude_dir = home / '.claude'

        # Create stale DISABLE_AUTOUPDATER in multiple locations
        for subdir_name in ['', 'aegis', 'myenv']:
            target_dir = claude_dir / subdir_name if subdir_name else claude_dir
            target_dir.mkdir(parents=True, exist_ok=True)
            settings_path = target_dir / 'settings.json'
            settings_path.write_text(json.dumps({
                'env': {'DISABLE_AUTOUPDATER': '1'},
            }))

        # Call helpers directly (not mocked by conftest)
        setup_environment._cleanup_settings_json_autoupdater(claude_dir / 'settings.json')
        for subdir in claude_dir.iterdir():
            if subdir.is_dir():
                s = subdir / 'settings.json'
                if s.exists():
                    setup_environment._cleanup_settings_json_autoupdater(s)

        # Verify all locations cleaned
        for subdir_name in ['', 'aegis', 'myenv']:
            target_dir = claude_dir / subdir_name if subdir_name else claude_dir
            settings_path = target_dir / 'settings.json'
            if settings_path.exists():
                data = json.loads(settings_path.read_text())
                assert 'DISABLE_AUTOUPDATER' not in data.get('env', {}), \
                    f'Stale DISABLE_AUTOUPDATER in {settings_path}'

    def test_cleanup_removes_empty_env_object(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Empty env: {} is cleaned up after DISABLE_AUTOUPDATER removal."""
        home = e2e_isolated_home['home']
        claude_dir = home / '.claude'

        settings_path = claude_dir / 'settings.json'
        settings_path.write_text(json.dumps({
            'env': {'DISABLE_AUTOUPDATER': '1'},
        }))

        setup_environment._cleanup_settings_json_autoupdater(settings_path)

        data = json.loads(settings_path.read_text())
        assert 'env' not in data, 'Empty env: {} should be cleaned up after removal'

    def test_pinned_cleans_only_bare_session_settings(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Pinned: only cleans bare session ~/.claude/settings.json."""
        home = e2e_isolated_home['home']
        claude_dir = home / '.claude'

        # Create stale in both global and isolated locations
        claude_dir.mkdir(parents=True, exist_ok=True)
        (claude_dir / 'settings.json').write_text(json.dumps({
            'env': {'DISABLE_AUTOUPDATER': '1'},
        }))

        isolated_dir = claude_dir / 'myenv'
        isolated_dir.mkdir(parents=True, exist_ok=True)
        (isolated_dir / 'settings.json').write_text(json.dumps({
            'env': {'DISABLE_AUTOUPDATER': '1'},
        }))

        # Pinned: only cleans bare session location
        setup_environment._cleanup_settings_json_autoupdater(claude_dir / 'settings.json')

        # Verify global settings cleaned
        data = json.loads((claude_dir / 'settings.json').read_text())
        assert 'DISABLE_AUTOUPDATER' not in data.get('env', {})

        # Isolated is NOT cleaned by this call (only when called for that path)
        data = json.loads((isolated_dir / 'settings.json').read_text())
        assert data.get('env', {}).get('DISABLE_AUTOUPDATER') == '1'


class TestGlobalConfigDualWrite:
    """Verify write_global_config() dual-writes when command-names is present."""

    def test_dual_write_creates_both_files(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Both home and isolated .claude.json are written."""
        home = e2e_isolated_home['home']
        artifact_dir = home / '.claude' / 'test-cmd'
        artifact_dir.mkdir(parents=True, exist_ok=True)

        global_config: dict[str, Any] = {'autoConnectIde': True, 'editorMode': 'vim'}

        result = setup_environment.write_global_config(
            global_config, artifact_base_dir=artifact_dir,
        )

        assert result is True

        # Verify BOTH files exist with matching content
        home_json = json.loads((home / '.claude.json').read_text())
        isolated_json = json.loads((artifact_dir / '.claude.json').read_text())

        assert home_json['autoConnectIde'] is True
        assert home_json['editorMode'] == 'vim'
        assert isolated_json['autoConnectIde'] is True
        assert isolated_json['editorMode'] == 'vim'

    def test_no_dual_write_without_artifact_base_dir(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """No isolated .claude.json when artifact_base_dir is None."""
        home = e2e_isolated_home['home']
        global_config: dict[str, Any] = {'showTurnDuration': True}

        result = setup_environment.write_global_config(global_config)

        assert result is True
        assert (home / '.claude.json').exists()
        # No isolated .claude.json should be created
        claude_dir = home / '.claude'
        if claude_dir.is_dir():
            for subdir in claude_dir.iterdir():
                if subdir.is_dir():
                    assert not (subdir / '.claude.json').exists()

    def test_auto_updates_false_in_both_files_when_pinned(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Pinned version: autoUpdates: false appears in both locations."""
        home = e2e_isolated_home['home']
        artifact_dir = home / '.claude' / 'test-cmd'
        artifact_dir.mkdir(parents=True, exist_ok=True)

        gc, _, _, _, _, _ = setup_environment.apply_auto_update_settings(
            '2.1.85', {'editorMode': 'vim'}, {}, {}, {},
        )
        assert gc is not None
        setup_environment.write_global_config(gc, artifact_base_dir=artifact_dir)

        home_json = json.loads((home / '.claude.json').read_text())
        isolated_json = json.loads((artifact_dir / '.claude.json').read_text())
        assert home_json['autoUpdates'] is False
        assert isolated_json['autoUpdates'] is False

    def test_dual_write_skips_when_artifact_base_dir_equals_home(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Degenerate case: artifact_base_dir == home_dir skips dual-write.

        When artifact_base_dir equals the home directory, dual-write is
        skipped to avoid writing the same ~/.claude.json file twice.
        """
        home = e2e_isolated_home['home']

        global_config: dict[str, Any] = {'autoConnectIde': True, 'editorMode': 'vim'}

        # Pass home as artifact_base_dir (degenerate case)
        result = setup_environment.write_global_config(
            global_config, artifact_base_dir=home,
        )

        assert result is True

        # Home .claude.json should exist with correct content
        home_json = json.loads((home / '.claude.json').read_text())
        assert home_json['autoConnectIde'] is True
        assert home_json['editorMode'] == 'vim'

        # No separate .claude.json should appear in home directory itself
        # (the guard prevents writing home/.claude.json a second time)
        # Verify by checking that .claude subdirectories have no .claude.json
        claude_dir = home / '.claude'
        if claude_dir.is_dir():
            for subdir in claude_dir.iterdir():
                if subdir.is_dir():
                    assert not (subdir / '.claude.json').exists(), \
                        f'Unexpected .claude.json in {subdir}'


class TestStaleAutoUpdatesFalseCleanup:
    """Verify cleanup of stale autoUpdates: false from .claude.json files."""

    def test_no_global_config_cleans_stale(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Stale autoUpdates: false on disk is cleaned by helper."""
        home = e2e_isolated_home['home']
        claude_json = home / '.claude.json'
        claude_json.write_text(json.dumps({
            'autoUpdates': False, 'userID': 'test-user',
        }))

        # Call helper directly (not mocked)
        setup_environment._cleanup_claude_json_auto_updates(claude_json)

        data = json.loads(claude_json.read_text())
        assert 'autoUpdates' not in data, 'Stale autoUpdates: false should be removed'
        assert data['userID'] == 'test-user', 'Other keys should be preserved'

    def test_global_config_without_autoupdates_cleans_stale(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Stale autoUpdates: false cleaned when no autoUpdates key in YAML."""
        home = e2e_isolated_home['home']
        claude_json = home / '.claude.json'
        claude_json.write_text(json.dumps({
            'autoUpdates': False, 'editorMode': 'vim',
        }))

        setup_environment._cleanup_claude_json_auto_updates(claude_json)

        data = json.loads(claude_json.read_text())
        assert 'autoUpdates' not in data
        assert data['editorMode'] == 'vim'

    def test_preserves_autoupdates_true(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """User-set autoUpdates: true must NOT be removed."""
        home = e2e_isolated_home['home']
        claude_json = home / '.claude.json'
        claude_json.write_text(json.dumps({'autoUpdates': True}))

        setup_environment._cleanup_claude_json_auto_updates(claude_json)

        data = json.loads(claude_json.read_text())
        assert data['autoUpdates'] is True

    def test_cleans_all_isolated_claude_json(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Cleanup sweeps ~/.claude/*/.claude.json too."""
        home = e2e_isolated_home['home']
        for name in ['aegis', 'myenv']:
            isolated_dir = home / '.claude' / name
            isolated_dir.mkdir(parents=True, exist_ok=True)
            (isolated_dir / '.claude.json').write_text(json.dumps({
                'autoUpdates': False, 'userID': f'{name}-user',
            }))

        for name in ['aegis', 'myenv']:
            path = home / '.claude' / name / '.claude.json'
            setup_environment._cleanup_claude_json_auto_updates(path)

        for name in ['aegis', 'myenv']:
            data = json.loads(
                (home / '.claude' / name / '.claude.json').read_text(),
            )
            assert 'autoUpdates' not in data
            assert data['userID'] == f'{name}-user'


class TestMcpClaudeConfigDirPropagation:
    """Verify CLAUDE_CONFIG_DIR is passed to MCP subprocess when isolated."""

    def test_http_propagates_config_dir(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """run_bash_command receives CLAUDE_CONFIG_DIR in extra_env."""
        from unittest.mock import patch

        home = e2e_isolated_home['home']
        artifact_dir = home / '.claude' / 'test-cmd'
        artifact_dir.mkdir(parents=True, exist_ok=True)

        captured_extra_envs: list[dict[str, str] | None] = []

        def mock_run_bash(
            command: str,
            capture_output: bool = True,
            login_shell: bool = False,
            extra_env: dict[str, str] | None = None,
        ) -> CompletedProcess[str]:
            _ = capture_output, login_shell
            captured_extra_envs.append(extra_env)
            return CompletedProcess(args=command, returncode=0, stdout='', stderr='')

        claude_path = str(home / '.local' / 'bin' / 'claude')
        with (
            patch.object(setup_environment, 'run_bash_command', side_effect=mock_run_bash),
            patch.object(
                setup_environment, 'find_command',
                side_effect=lambda cmd: claude_path if cmd == 'claude' else None,
            ),
            patch('platform.system', return_value='Windows'),
        ):
            server: dict[str, Any] = {
                'name': 'test-server',
                'transport': 'http',
                'url': 'http://localhost:3000',
                'scope': 'user',
            }

            setup_environment.configure_mcp_server(
                server, artifact_base_dir=artifact_dir,
            )

        # Verify at least one captured extra_env contains CLAUDE_CONFIG_DIR
        envs_with_config_dir = [
            env for env in captured_extra_envs
            if env is not None and 'CLAUDE_CONFIG_DIR' in env
        ]
        assert envs_with_config_dir, \
            'CLAUDE_CONFIG_DIR should be propagated to subprocess via extra_env'
        assert envs_with_config_dir[0]['CLAUDE_CONFIG_DIR'] == str(artifact_dir)

    def test_no_config_dir_without_artifact_base_dir(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """No CLAUDE_CONFIG_DIR when artifact_base_dir is None."""
        from unittest.mock import patch

        home = e2e_isolated_home['home']

        captured_extra_envs: list[dict[str, str] | None] = []

        def mock_run_bash(
            command: str,
            capture_output: bool = True,
            login_shell: bool = False,
            extra_env: dict[str, str] | None = None,
        ) -> CompletedProcess[str]:
            _ = capture_output, login_shell
            captured_extra_envs.append(extra_env)
            return CompletedProcess(args=command, returncode=0, stdout='', stderr='')

        claude_path = str(home / '.local' / 'bin' / 'claude')
        with (
            patch.object(setup_environment, 'run_bash_command', side_effect=mock_run_bash),
            patch.object(
                setup_environment, 'find_command',
                side_effect=lambda cmd: claude_path if cmd == 'claude' else None,
            ),
            patch('platform.system', return_value='Windows'),
        ):
            server: dict[str, Any] = {
                'name': 'test-server',
                'transport': 'http',
                'url': 'http://localhost:3000',
                'scope': 'user',
            }

            setup_environment.configure_mcp_server(server)

        # No extra_env should contain CLAUDE_CONFIG_DIR
        for env in captured_extra_envs:
            if env is not None:
                assert 'CLAUDE_CONFIG_DIR' not in env, \
                    'CLAUDE_CONFIG_DIR should NOT be set without artifact_base_dir'
