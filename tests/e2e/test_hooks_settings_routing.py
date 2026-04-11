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
from scripts.setup_environment import create_profile_config
from scripts.setup_environment import write_hooks_to_settings
from tests.e2e.validators import _validate_hooks_structure
from tests.e2e.validators import validate_hooks_in_settings_json

# ---------------------------------------------------------------------------
# Inline YAML-like configs (dicts) for tests WITHOUT command-names
# ---------------------------------------------------------------------------


def _hooks_only_config() -> dict[str, Any]:
    """Minimal config with hooks but NO command-names."""
    return {
        'name': 'Hooks Only',
        'hooks': {
            'files': ['hooks/e2e_test_hook.py'],
            'events': [
                {
                    'event': 'PostToolUse',
                    'matcher': 'Write',
                    'type': 'command',
                    'command': 'e2e_test_hook.py',
                },
                {
                    'event': 'PostToolUse',
                    'matcher': 'Read',
                    'type': 'http',
                    'url': 'http://localhost:8080/hooks',
                    'headers': {'Authorization': 'Bearer $TOKEN'},
                    'allowed-env-vars': ['TOKEN'],
                    'timeout': 15,
                    'status-message': 'Sending webhook...',
                },
                {
                    'event': 'PreToolUse',
                    'matcher': 'Bash',
                    'type': 'prompt',
                    'prompt': 'Check safety before bash execution',
                    'timeout': 30,
                },
                {
                    'event': 'PreToolUse',
                    'matcher': 'Bash(rm *)',
                    'type': 'agent',
                    'prompt': 'Verify security of: $ARGUMENTS',
                    'model': 'sonnet',
                    'once': True,
                },
            ],
        },
        # NO command-names
    }


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


class TestHooksToSettingsJson:
    """Tests for hooks routing to settings.json when command-names is absent."""

    def test_hooks_written_to_settings_json(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Verify hooks are written to settings.json when command-names is absent.

        Uses write_hooks_to_settings directly with a hooks-only config.
        Validates hook structure, all four hook types, and path expansion.
        """
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']
        hooks_dir = claude_dir / 'hooks'

        config = _hooks_only_config()
        hooks = config['hooks']

        result = write_hooks_to_settings(hooks, hooks_dir, claude_dir)
        assert result is True

        settings_path = claude_dir / 'settings.json'
        assert settings_path.exists(), 'settings.json not created'

        errors = validate_hooks_in_settings_json(settings_path, hooks)
        assert not errors, 'Hooks in settings.json validation failed:\n' + '\n'.join(errors)

    def test_all_four_hook_types_in_settings_json(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Verify all four hook types (command, http, prompt, agent) in settings.json."""
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']
        hooks_dir = claude_dir / 'hooks'

        config = _hooks_only_config()
        hooks = config['hooks']

        write_hooks_to_settings(hooks, hooks_dir, claude_dir)

        data = json.loads((claude_dir / 'settings.json').read_text())
        hooks_data = data['hooks']

        # Verify PostToolUse has command and http hooks
        post_tool_groups = hooks_data['PostToolUse']
        hook_types_found: set[str] = set()
        for group in post_tool_groups:
            hook_types_found.update(hook['type'] for hook in group.get('hooks', []))
        assert 'command' in hook_types_found, 'command hook type missing'
        assert 'http' in hook_types_found, 'http hook type missing'

        # Verify PreToolUse has prompt and agent hooks
        pre_tool_groups = hooks_data['PreToolUse']
        pre_types: set[str] = set()
        for group in pre_tool_groups:
            pre_types.update(hook['type'] for hook in group.get('hooks', []))
        assert 'prompt' in pre_types, 'prompt hook type missing'
        assert 'agent' in pre_types, 'agent hook type missing'

    def test_hook_paths_expanded_in_settings_json(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Verify hook command paths are absolute POSIX with no unexpanded tildes."""
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']
        hooks_dir = claude_dir / 'hooks'

        hooks = {
            'events': [
                {'event': 'PostToolUse', 'matcher': 'Write', 'type': 'command',
                 'command': 'e2e_test_hook.py'},
                {'event': 'PostToolUse', 'matcher': 'Read', 'type': 'command',
                 'command': 'e2e_test_hook.js'},
            ],
        }

        write_hooks_to_settings(hooks, hooks_dir, claude_dir)

        data = json.loads((claude_dir / 'settings.json').read_text())
        hooks_data = data['hooks']

        for event_groups in hooks_data.values():
            for group in event_groups:
                for hook in group.get('hooks', []):
                    if hook.get('type') == 'command':
                        cmd = hook.get('command', '')
                        assert '~' not in cmd, f'Unexpanded tilde in command: {cmd}'
                        # Python hooks should have uv run prefix
                        if 'e2e_test_hook.py' in cmd:
                            assert 'uv run' in cmd, f'Missing uv run prefix: {cmd}'
                        # JS hooks should have node prefix
                        if 'e2e_test_hook.js' in cmd:
                            assert cmd.startswith('node '), f'Missing node prefix: {cmd}'

    def test_stale_hooks_removed_on_rerun(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Verify stale hook events from prior runs are removed on re-run."""
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']
        hooks_dir = claude_dir / 'hooks'

        # First run: create hooks with event A
        hooks_v1 = {
            'events': [
                {'event': 'OldEvent', 'matcher': 'Write', 'type': 'command',
                 'command': 'old.py'},
            ],
        }
        write_hooks_to_settings(hooks_v1, hooks_dir, claude_dir)

        data_v1 = json.loads((claude_dir / 'settings.json').read_text())
        assert 'OldEvent' in data_v1['hooks'], 'First run: OldEvent should be present'

        # Second run: create hooks with different event
        hooks_v2 = {
            'events': [
                {'event': 'PostToolUse', 'matcher': 'Write', 'type': 'command',
                 'command': 'new.py'},
            ],
        }
        write_hooks_to_settings(hooks_v2, hooks_dir, claude_dir)

        data_v2 = json.loads((claude_dir / 'settings.json').read_text())
        assert 'OldEvent' not in data_v2['hooks'], 'Second run: OldEvent should be removed'
        assert 'PostToolUse' in data_v2['hooks'], 'Second run: PostToolUse should be present'

    def test_config_json_not_created_without_command_names(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Verify config.json is NOT created when command-names is absent."""
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']
        hooks_dir = claude_dir / 'hooks'

        config = _hooks_only_config()
        write_hooks_to_settings(config['hooks'], hooks_dir, claude_dir)

        # config.json should NOT exist (no command-names means no isolated environment)
        config_json = claude_dir / 'config.json'
        assert not config_json.exists(), 'config.json should not be created without command-names'


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

        config = _hooks_with_user_settings_config()

        # Simulate Step 14: write user settings
        from scripts.setup_environment import write_user_settings
        write_user_settings(config['user-settings'], claude_dir)

        # Simulate Step 18: write hooks to settings.json
        write_hooks_to_settings(config['hooks'], hooks_dir, claude_dir)

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
        write_hooks_to_settings(hooks, hooks_dir, claude_dir)

        data = json.loads(settings_file.read_text())

        # All original keys preserved exactly
        assert data['language'] == 'english'
        assert data['permissions'] == {'allow': ['Read', 'Write']}
        assert data['theme'] == 'dark'
        assert data['nested'] == {'key1': 'val1', 'key2': [1, 2, 3]}

        # Hooks added
        assert 'hooks' in data


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

    def test_empty_hooks_cleans_up(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Verify write_hooks_to_settings with empty hooks removes stale hooks key."""
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']
        hooks_dir = claude_dir / 'hooks'

        # Pre-populate with stale hooks
        settings_file = claude_dir / 'settings.json'
        settings_file.write_text(json.dumps({
            'hooks': {'OldEvent': []},
            'language': 'russian',
        }))

        # Write empty hooks (simulates config with no hook events)
        write_hooks_to_settings({}, hooks_dir, claude_dir)

        data = json.loads(settings_file.read_text())
        assert 'hooks' not in data, 'Stale hooks key should be removed'
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
