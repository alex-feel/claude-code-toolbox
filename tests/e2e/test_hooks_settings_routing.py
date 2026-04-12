"""E2E tests for hooks routing to settings.json when command-names is absent.

These tests verify the dual hooks routing behavior:
- When command-names IS present: hooks written to config.json (existing behavior)
- When command-names is ABSENT: hooks written to settings.json (new behavior)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from unittest.mock import patch

if TYPE_CHECKING:
    from unittest.mock import MagicMock

import pytest

from scripts.setup_environment import _build_hooks_json
from scripts.setup_environment import _build_profile_settings
from scripts.setup_environment import create_profile_config
from scripts.setup_environment import write_profile_settings_to_settings
from tests.e2e.validators import _validate_hooks_structure

# ---------------------------------------------------------------------------
# Inline YAML-like configs (dicts) for tests WITHOUT command-names
# ---------------------------------------------------------------------------


def _hooks_with_user_settings_config() -> dict[str, Any]:
    """Config with hooks AND user-settings but NO command-names."""
    return {
        'name': 'Hooks with User Settings',
        'user-settings': {
            'language': 'english',
            'theme': 'dark',
        },
        'hooks': {
            'files': ['hooks/e2e_test_hook.py'],
            'events': [
                {
                    'event': 'PostToolUse',
                    'matcher': 'Write',
                    'type': 'command',
                    'command': 'e2e_test_hook.py',
                },
            ],
        },
        # NO command-names
    }


def _no_hooks_no_commands_config() -> dict[str, Any]:
    """Config with NO hooks and NO command-names."""
    return {
        'name': 'Minimal',
        'user-settings': {
            'language': 'russian',
        },
        # NO hooks, NO command-names
    }


# ---------------------------------------------------------------------------
# E2E Test Class: Hooks routing to settings.json (no command-names)
# ---------------------------------------------------------------------------


class TestHooksToConfigJsonRegression:
    """Regression tests: hooks routed to config.json when command-names IS present."""

    def test_hooks_in_config_json_with_command_names(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify hooks are written to config.json when command-names is present."""
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']
        cmd = golden_config['command-names'][0]
        artifact_dir = claude_dir / cmd
        artifact_dir.mkdir(parents=True, exist_ok=True)

        hooks = golden_config.get('hooks', {})
        create_profile_config(
            {
                'hooks': hooks,
                'model': golden_config.get('model'),
                'permissions': golden_config.get('permissions'),
                'env': golden_config.get('env-variables'),
                'alwaysThinkingEnabled': golden_config.get('always-thinking-enabled'),
                'companyAnnouncements': golden_config.get('company-announcements'),
                'attribution': golden_config.get('attribution'),
                'statusLine': golden_config.get('status-line'),
                'effortLevel': golden_config.get('effort-level'),
            },
            artifact_dir,
        )

        config_path = artifact_dir / 'config.json'
        assert config_path.exists(), 'config.json not created'

        data = json.loads(config_path.read_text())
        assert 'hooks' in data, 'config.json missing hooks key'

        errors = _validate_hooks_structure(data['hooks'], hooks)
        assert not errors, 'Hooks in config.json validation failed:\n' + '\n'.join(errors)

    def test_settings_json_no_hooks_with_command_names(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify settings.json does NOT contain hooks when command-names is present.

        When command-names is present, hooks go to config.json only.
        write_user_settings should not write hooks (it's in USER_SETTINGS_EXCLUDED_KEYS).
        """
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']

        user_settings = golden_config.get('user-settings')
        if user_settings:
            from scripts.setup_environment import write_user_settings
            write_user_settings(user_settings, claude_dir)

        settings_path = claude_dir / 'settings.json'
        if settings_path.exists():
            data = json.loads(settings_path.read_text())
            assert 'hooks' not in data, (
                'settings.json should NOT contain hooks when command-names is present'
            )


class TestHooksAndUserSettingsCoexistence:
    """Test hooks + user-settings co-existence in settings.json."""

    def test_hooks_and_user_settings_coexist(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Verify settings.json contains both user-settings and hooks."""
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']
        hooks_dir = claude_dir / 'hooks'
        hooks_dir.mkdir(parents=True, exist_ok=True)

        config = _hooks_with_user_settings_config()

        # Simulate Step 14: write user settings
        from scripts.setup_environment import write_user_settings
        write_user_settings(config['user-settings'], claude_dir)

        # Simulate Step 18: write profile settings (including hooks) to settings.json
        delta = _build_profile_settings({'hooks': config['hooks']}, hooks_dir)
        write_profile_settings_to_settings(delta, claude_dir)

        settings_path = claude_dir / 'settings.json'
        assert settings_path.exists()

        data = json.loads(settings_path.read_text())

        # User settings preserved
        assert data.get('language') == 'english', 'language setting lost'
        assert data.get('theme') == 'dark', 'theme setting lost'

        # Hooks present
        assert 'hooks' in data, 'hooks key missing'
        assert 'PostToolUse' in data['hooks'], 'PostToolUse event missing'

    def test_hooks_do_not_corrupt_user_settings(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Verify hooks write does not alter non-hooks keys in settings.json."""
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']
        hooks_dir = claude_dir / 'hooks'
        hooks_dir.mkdir(parents=True, exist_ok=True)

        # Pre-populate with rich user settings
        settings_file = claude_dir / 'settings.json'
        original_settings = {
            'language': 'english',
            'permissions': {'allow': ['Read', 'Write']},
            'theme': 'dark',
            'nested': {'key1': 'val1', 'key2': [1, 2, 3]},
        }
        settings_file.write_text(json.dumps(original_settings))

        hooks = {
            'events': [
                {'event': 'PostToolUse', 'matcher': 'Write', 'type': 'command',
                 'command': 'hook.py'},
            ],
        }
        delta = _build_profile_settings({'hooks': hooks}, hooks_dir)
        write_profile_settings_to_settings(delta, claude_dir)

        data = json.loads(settings_file.read_text())

        # All original keys preserved exactly
        assert data['language'] == 'english'
        # Under universal union, permissions.allow with no new entries
        # is a no-op (the hooks-only delta contributes no permissions)
        assert data['permissions'] == {'allow': ['Read', 'Write']}
        assert data['theme'] == 'dark'
        assert data['nested'] == {'key1': 'val1', 'key2': [1, 2, 3]}

        # Hooks added
        assert 'hooks' in data

    def test_two_matcher_groups_with_same_matcher_coexist(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Two runs with the same matcher string + different commands produce TWO matcher groups.

        Naive structural dedupe keeps both groups because the inner
        'hooks' arrays differ. This matches Claude Code's native
        cross-scope merge behavior and its runtime dedupe by command
        string (documented at https://code.claude.com/docs/en/hooks).
        """
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']
        hooks_dir = claude_dir / 'hooks'
        hooks_dir.mkdir(parents=True, exist_ok=True)

        hooks_a = {
            'events': [
                {'event': 'PreToolUse', 'matcher': 'Bash', 'type': 'command', 'command': 'a.sh'},
            ],
        }
        delta_a = _build_profile_settings({'hooks': hooks_a}, hooks_dir)
        write_profile_settings_to_settings(delta_a, claude_dir)

        hooks_b = {
            'events': [
                {'event': 'PreToolUse', 'matcher': 'Bash', 'type': 'command', 'command': 'b.sh'},
            ],
        }
        delta_b = _build_profile_settings({'hooks': hooks_b}, hooks_dir)
        write_profile_settings_to_settings(delta_b, claude_dir)

        settings = json.loads((claude_dir / 'settings.json').read_text())
        pre_tool = settings['hooks']['PreToolUse']
        assert len(pre_tool) == 2
        commands = sorted(g['hooks'][0]['command'] for g in pre_tool)
        # Both scripts are absolute POSIX paths, so sort alphabetically
        assert len(commands) == 2


class TestNoHooksNoCommandNames:
    """Test the skip scenario: no hooks, no command-names."""

    def test_settings_json_no_hooks_key(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Verify settings.json does NOT contain hooks when none configured."""
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']

        config = _no_hooks_no_commands_config()

        # Write user settings only (simulates the no-hooks path)
        from scripts.setup_environment import write_user_settings
        if config.get('user-settings'):
            write_user_settings(config['user-settings'], claude_dir)

        settings_path = claude_dir / 'settings.json'
        if settings_path.exists():
            data = json.loads(settings_path.read_text())
            assert 'hooks' not in data, 'hooks key should not be present when none configured'

    def test_explicit_null_hooks_removes_stale_events(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Verify explicit RFC 7396 null removes stale hooks from settings.json.

        Under the universal deep-merge + union-all-arrays contract, the
        only way to delete stale hooks from ~/.claude/settings.json is
        to declare ``hooks: null`` in YAML (or ``{'hooks': None}`` in
        the profile delta). Under union semantics, omitting the hooks
        key leaves existing hooks in place.
        """
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']
        hooks_dir = claude_dir / 'hooks'
        hooks_dir.mkdir(parents=True, exist_ok=True)

        # Pre-populate with stale hooks
        settings_file = claude_dir / 'settings.json'
        settings_file.write_text(json.dumps({
            'hooks': {'OldEvent': []},
            'language': 'russian',
        }))

        # Explicit null removes hooks block (simulates YAML: hooks: null)
        delta = _build_profile_settings({'hooks': None}, hooks_dir)
        write_profile_settings_to_settings(delta, claude_dir)

        data = json.loads(settings_file.read_text())
        assert 'hooks' not in data, 'Stale hooks key should be removed by explicit null'
        assert data['language'] == 'russian', 'Other settings should be preserved'


class TestSummaryOutputRouting:
    """Test summary output distinguishes hooks routing target."""

    @patch('scripts.setup_environment.load_config_from_source')
    @patch('scripts.setup_environment.validate_all_config_files')
    @patch('scripts.setup_environment.install_claude')
    @patch('scripts.setup_environment.install_dependencies')
    @patch('scripts.setup_environment.process_resources')
    @patch('scripts.setup_environment.process_skills')
    @patch('scripts.setup_environment.configure_all_mcp_servers')
    @patch('scripts.setup_environment.find_command', return_value='/usr/bin/claude')
    @patch('scripts.setup_environment.is_admin', return_value=True)
    @patch('pathlib.Path.mkdir')
    def test_summary_shows_settings_json_routing(
        self,
        mock_mkdir: MagicMock,
        mock_is_admin: MagicMock,
        mock_find_cmd: MagicMock,
        mock_mcp: MagicMock,
        mock_skills: MagicMock,
        mock_resources: MagicMock,
        mock_deps: MagicMock,
        mock_install: MagicMock,
        mock_validate: MagicMock,
        mock_load: MagicMock,
        e2e_isolated_home: dict[str, Path],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Verify summary shows 'in settings.json' when no command-names."""
        del mock_mkdir, mock_is_admin, mock_find_cmd, mock_skills, mock_resources
        del mock_deps, e2e_isolated_home
        mock_load.return_value = (
            {
                'name': 'Hooks Test',
                'hooks': {
                    'files': ['hooks/hook.py'],
                    'events': [
                        {'event': 'PostToolUse', 'matcher': 'Write',
                         'type': 'command', 'command': 'hook.py'},
                    ],
                },
                # NO command-names
            },
            'test.yaml',
        )
        mock_validate.return_value = (True, [])
        mock_install.return_value = True
        mock_mcp.return_value = (True, [], {'global_count': 0, 'profile_count': 0, 'combined_count': 0})

        from scripts import setup_environment

        with patch('sys.argv', ['setup_environment.py', 'test', '--yes', '--skip-install']), \
             patch('sys.exit') as mock_exit, \
             patch.object(setup_environment, 'download_hook_files', return_value=True), \
             patch.object(setup_environment, 'write_profile_settings_to_settings', return_value=True):
            setup_environment.main()
            mock_exit.assert_not_called()

        captured = capsys.readouterr()
        assert 'Hooks: 1 configured (in settings.json)' in captured.out

    @patch('scripts.setup_environment.load_config_from_source')
    @patch('scripts.setup_environment.validate_all_config_files')
    @patch('scripts.setup_environment.install_claude')
    @patch('scripts.setup_environment.install_dependencies')
    @patch('scripts.setup_environment.process_resources')
    @patch('scripts.setup_environment.process_skills')
    @patch('scripts.setup_environment.configure_all_mcp_servers')
    @patch('scripts.setup_environment.write_user_settings')
    @patch('scripts.setup_environment.create_profile_config')
    @patch('scripts.setup_environment.create_launcher_script')
    @patch('scripts.setup_environment.register_global_command')
    @patch('scripts.setup_environment.find_command', return_value='/usr/bin/claude')
    @patch('scripts.setup_environment.is_admin', return_value=True)
    @patch('pathlib.Path.mkdir')
    def test_summary_shows_config_json_routing(
        self,
        mock_mkdir: MagicMock,
        mock_is_admin: MagicMock,
        mock_find_cmd: MagicMock,
        mock_register: MagicMock,
        mock_launcher: MagicMock,
        mock_profile: MagicMock,
        mock_write_settings: MagicMock,
        mock_mcp: MagicMock,
        mock_skills: MagicMock,
        mock_resources: MagicMock,
        mock_deps: MagicMock,
        mock_install: MagicMock,
        mock_validate: MagicMock,
        mock_load: MagicMock,
        e2e_isolated_home: dict[str, Path],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Verify summary shows 'in config.json' when command-names is present."""
        del mock_mkdir, mock_is_admin, mock_find_cmd, mock_skills, mock_resources
        del mock_deps, e2e_isolated_home, mock_register, mock_profile, mock_write_settings
        mock_load.return_value = (
            {
                'name': 'Hooks Test with Command',
                'command-names': ['test-cmd'],
                'hooks': {
                    'files': ['hooks/hook.py'],
                    'events': [
                        {'event': 'PostToolUse', 'matcher': 'Write',
                         'type': 'command', 'command': 'hook.py'},
                        {'event': 'PreToolUse', 'matcher': 'Bash',
                         'type': 'prompt', 'prompt': 'check safety'},
                    ],
                },
            },
            'test.yaml',
        )
        mock_validate.return_value = (True, [])
        mock_install.return_value = True
        mock_mcp.return_value = (True, [], {'global_count': 0, 'profile_count': 0, 'combined_count': 0})

        from scripts import setup_environment

        mock_launcher.return_value = (Path('/fake/launcher.sh'), Path('/fake/launch.sh'))

        with patch('sys.argv', ['setup_environment.py', 'test', '--yes', '--skip-install']), \
             patch('sys.exit') as mock_exit, \
             patch.object(setup_environment, 'download_hook_files', return_value=True):
            setup_environment.main()
            mock_exit.assert_not_called()

        captured = capsys.readouterr()
        assert 'Hooks: 2 configured (in config.json)' in captured.out


class TestHooksSettingsRoutingStepOutput:
    """Test that step output messages are correct for hooks routing."""

    @patch('scripts.setup_environment.load_config_from_source')
    @patch('scripts.setup_environment.validate_all_config_files')
    @patch('scripts.setup_environment.install_claude')
    @patch('scripts.setup_environment.install_dependencies')
    @patch('scripts.setup_environment.process_resources')
    @patch('scripts.setup_environment.process_skills')
    @patch('scripts.setup_environment.configure_all_mcp_servers')
    @patch('scripts.setup_environment.find_command', return_value='/usr/bin/claude')
    @patch('scripts.setup_environment.is_admin', return_value=True)
    @patch('pathlib.Path.mkdir')
    def test_steps_17_18_run_when_hooks_present(
        self,
        mock_mkdir: MagicMock,
        mock_is_admin: MagicMock,
        mock_find_cmd: MagicMock,
        mock_mcp: MagicMock,
        mock_skills: MagicMock,
        mock_resources: MagicMock,
        mock_deps: MagicMock,
        mock_install: MagicMock,
        mock_validate: MagicMock,
        mock_load: MagicMock,
        e2e_isolated_home: dict[str, Path],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Verify Steps 17-18 run when hooks are present without command-names."""
        del mock_mkdir, mock_is_admin, mock_find_cmd, mock_skills, mock_resources
        del mock_deps, e2e_isolated_home
        mock_load.return_value = (
            {
                'name': 'Hooks Only',
                'hooks': {
                    'events': [
                        {'event': 'PostToolUse', 'matcher': 'Write',
                         'type': 'command', 'command': 'hook.py'},
                    ],
                },
            },
            'test.yaml',
        )
        mock_validate.return_value = (True, [])
        mock_install.return_value = True
        mock_mcp.return_value = (True, [], {'global_count': 0, 'profile_count': 0, 'combined_count': 0})

        from scripts import setup_environment

        with patch('sys.argv', ['setup_environment.py', 'test', '--yes', '--skip-install']), \
             patch('sys.exit') as mock_exit, \
             patch.object(setup_environment, 'download_hook_files', return_value=True), \
             patch.object(setup_environment, 'write_profile_settings_to_settings', return_value=True):
            setup_environment.main()
            mock_exit.assert_not_called()

        captured = capsys.readouterr()
        assert 'Step 17: Downloading hooks' in captured.out
        # Step 18 writes the full profile-owned delta (not just hooks) to
        # the shared settings.json in non-command-names mode.
        assert 'Step 18: Writing profile settings to settings.json' in captured.out
        assert 'Steps 19-21: Skipping command creation' in captured.out

    @patch('scripts.setup_environment.load_config_from_source')
    @patch('scripts.setup_environment.validate_all_config_files')
    @patch('scripts.setup_environment.install_claude')
    @patch('scripts.setup_environment.install_dependencies')
    @patch('scripts.setup_environment.process_resources')
    @patch('scripts.setup_environment.process_skills')
    @patch('scripts.setup_environment.configure_all_mcp_servers')
    @patch('scripts.setup_environment.find_command', return_value='/usr/bin/claude')
    @patch('scripts.setup_environment.is_admin', return_value=True)
    @patch('pathlib.Path.mkdir')
    def test_steps_17_18_skipped_when_no_hooks(
        self,
        mock_mkdir: MagicMock,
        mock_is_admin: MagicMock,
        mock_find_cmd: MagicMock,
        mock_mcp: MagicMock,
        mock_skills: MagicMock,
        mock_resources: MagicMock,
        mock_deps: MagicMock,
        mock_install: MagicMock,
        mock_validate: MagicMock,
        mock_load: MagicMock,
        e2e_isolated_home: dict[str, Path],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Verify Steps 17-18 are skipped when no hooks and no command-names."""
        del mock_mkdir, mock_is_admin, mock_find_cmd, mock_skills, mock_resources
        del mock_deps, e2e_isolated_home
        mock_load.return_value = (
            {
                'name': 'No Hooks',
                # No hooks, no command-names
            },
            'test.yaml',
        )
        mock_validate.return_value = (True, [])
        mock_install.return_value = True
        mock_mcp.return_value = (True, [], {'global_count': 0, 'profile_count': 0, 'combined_count': 0})

        from scripts import setup_environment

        with patch('sys.argv', ['setup_environment.py', 'test', '--yes', '--skip-install']), \
             patch('sys.exit') as mock_exit, \
             patch.object(setup_environment, 'write_profile_settings_to_settings', return_value=True):
            setup_environment.main()
            mock_exit.assert_not_called()

        captured = capsys.readouterr()
        # In non-command-names mode, Step 17 skips the download when no
        # hooks are configured, and Step 18 still runs (the empty profile
        # delta makes the writer a no-op).
        assert 'Step 17: Skipping hooks download (none configured)' in captured.out
        assert 'Step 18: Writing profile settings to settings.json' in captured.out
        assert 'Steps 19-21: Skipping command creation' in captured.out


class TestBuildHooksJsonParity:
    """E2E parity tests: _build_hooks_json matches create_profile_config output."""

    def test_golden_config_hooks_parity(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify _build_hooks_json produces identical output to create_profile_config.

        Uses the full golden config hooks section for comprehensive parity.
        """
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']
        artifact_dir = claude_dir / 'test-parity'
        artifact_dir.mkdir(parents=True, exist_ok=True)
        hooks_dir = artifact_dir / 'hooks'

        hooks = golden_config.get('hooks', {})

        # Generate via create_profile_config
        create_profile_config({'hooks': hooks}, artifact_dir)
        config_data = json.loads((artifact_dir / 'config.json').read_text())
        config_hooks = config_data.get('hooks', {})

        # Generate via _build_hooks_json
        direct_hooks = _build_hooks_json(hooks, hooks_dir)

        assert direct_hooks == config_hooks, (
            'Parity failure: _build_hooks_json output differs from create_profile_config'
        )
