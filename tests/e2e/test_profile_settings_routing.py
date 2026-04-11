"""E2E tests for profile-settings routing in non-command-names mode.

Verifies that when `command-names` is absent, all profile-owned keys
(model, permissions, env, attribution, alwaysThinkingEnabled, effortLevel,
companyAnnouncements, statusLine, hooks) are correctly routed to
~/.claude/settings.json via write_profile_settings_to_settings(), which
applies a conditional top-level replace: keys present in the delta are
overwritten (or deleted when set to None), and keys not present in the
delta are preserved unchanged.

Test coverage matrix:
- Happy path: all 9 profile-owned keys routed correctly
- Partial config: only subset of keys declared, rest omitted
- Preservation: pre-existing settings.json keys survive
- Step 14/18 interaction: user-settings contributions preserved
- Conflict detection: warnings fire in non-command-names mode
- Re-invocation across configurations: a second invocation updates values
  written by the first invocation when keys are re-declared
- Stale-key preservation: when an invocation omits a previously-written
  key, the existing value is left in place
- Profile-scoped MCP validation: exit 1 with 4-option message
- System-prompt warning: warning emitted, setup continues
- Empty profile delta: settings.json untouched when no profile keys
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from scripts.setup_environment import PROFILE_OWNED_KEYS
from scripts.setup_environment import _build_profile_settings
from scripts.setup_environment import detect_settings_conflicts
from scripts.setup_environment import write_profile_settings_to_settings

if TYPE_CHECKING:
    from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Test Class 1: Conditional Top-Level Replace Filesystem Semantics
# ---------------------------------------------------------------------------


class TestConditionalReplaceWriterFilesystem:
    """Filesystem-level tests of write_profile_settings_to_settings().

    Verifies the conditional top-level replace semantics on the real
    filesystem: only keys present in the delta are written; keys not in
    the delta are preserved unchanged; None values delete keys.
    """

    def test_happy_path_all_nine_keys(self, tmp_path: Path) -> None:
        """All nine PROFILE_OWNED_KEYS routed to settings.json correctly."""
        hooks_dir = tmp_path / 'hooks'
        hooks_dir.mkdir()

        delta = _build_profile_settings(
            hooks={'events': [{'event': 'PreToolUse', 'matcher': 'Bash',
                               'type': 'command', 'command': 'test.sh'}]},
            hooks_dir=hooks_dir,
            model='sonnet',
            permissions={'allow': ['Read'], 'deny': ['Bash(rm -rf)']},
            env={'FOO': 'bar'},
            always_thinking_enabled=True,
            company_announcements=['Welcome'],
            attribution={'commit': 'cm', 'pr': 'pr'},
            status_line={'file': 'status.py'},
            effort_level='high',
        )

        write_profile_settings_to_settings(delta, tmp_path)
        content = json.loads((tmp_path / 'settings.json').read_text(encoding='utf-8'))
        assert set(content.keys()) == PROFILE_OWNED_KEYS

    def test_partial_delta_only_specified_keys_written(self, tmp_path: Path) -> None:
        """YAML with only model and permissions writes only those two keys."""
        delta = _build_profile_settings(
            hooks={}, hooks_dir=tmp_path / 'hooks',
            model='sonnet',
            permissions={'allow': ['Read']},
        )
        write_profile_settings_to_settings(delta, tmp_path)
        content = json.loads((tmp_path / 'settings.json').read_text(encoding='utf-8'))
        assert set(content.keys()) == {'model', 'permissions'}

    def test_unrelated_keys_preserved(self, tmp_path: Path) -> None:
        """Non-profile keys in existing settings.json are preserved."""
        settings_file = tmp_path / 'settings.json'
        settings_file.write_text(json.dumps({
            'language': 'english',
            'includeGitInstructions': False,
            'apiKeyHelper': '/tmp/key.sh',
            'cleanupPeriodDays': 30,
        }), encoding='utf-8')

        delta = _build_profile_settings(hooks={}, hooks_dir=tmp_path / 'hooks', model='sonnet')
        write_profile_settings_to_settings(delta, tmp_path)
        content = json.loads(settings_file.read_text(encoding='utf-8'))
        assert content['language'] == 'english'
        assert content['includeGitInstructions'] is False
        assert content['apiKeyHelper'] == '/tmp/key.sh'
        assert content['cleanupPeriodDays'] == 30
        assert content['model'] == 'sonnet'

    def test_omitted_profile_key_preserved_when_yaml_does_not_declare_it(
        self, tmp_path: Path,
    ) -> None:
        """A profile key that the new delta does not declare survives unchanged.

        The shared settings.json is a user-facing file, so the writer must
        not silently scrub previously-written profile keys when the current
        configuration omits them. To delete a key, the user must declare it
        explicitly as None in the delta or remove it manually.
        """
        settings_file = tmp_path / 'settings.json'
        settings_file.write_text(json.dumps({
            'model': 'sonnet',
            'permissions': {'allow': ['Read']},
            'effortLevel': 'high',
        }), encoding='utf-8')

        # New invocation declares ONLY model (permissions and effortLevel omitted)
        delta = _build_profile_settings(hooks={}, hooks_dir=tmp_path / 'hooks', model='opus')
        write_profile_settings_to_settings(delta, tmp_path)
        content = json.loads(settings_file.read_text(encoding='utf-8'))

        # Model updated
        assert content['model'] == 'opus'
        # Omitted keys PRESERVED unchanged
        assert content['permissions'] == {'allow': ['Read']}
        assert content['effortLevel'] == 'high'

    def test_explicit_null_deletes_key(self, tmp_path: Path) -> None:
        """Explicit None value in delta deletes the key from settings.json."""
        settings_file = tmp_path / 'settings.json'
        settings_file.write_text(json.dumps({
            'model': 'sonnet',
            'permissions': {'allow': ['Read']},
        }), encoding='utf-8')

        # Note: _build_profile_settings() does not currently emit None values
        # for profile keys (it omits None inputs). For null-as-delete coverage,
        # construct the delta directly.
        write_profile_settings_to_settings({'model': None}, tmp_path)
        content = json.loads(settings_file.read_text(encoding='utf-8'))
        assert 'model' not in content
        # Unrelated profile key PRESERVED
        assert content['permissions'] == {'allow': ['Read']}

    def test_top_level_replace_not_deep_merge(self, tmp_path: Path) -> None:
        """The writer fully replaces a delta key value (no deep-merge).

        When a profile-owned key already exists in settings.json and the
        delta provides a new value for it, the writer must overwrite the
        entire top-level value rather than recursively merging the two
        dicts. Sub-keys not present in the new value disappear from disk.
        """
        settings_file = tmp_path / 'settings.json'
        settings_file.write_text(json.dumps({
            'permissions': {
                'allow': ['Read', 'Write', 'Glob'],
                'deny': ['Bash(rm -rf)'],
                'ask': ['Edit'],
            },
        }), encoding='utf-8')

        # YAML declares narrower permissions
        delta: dict[str, Any] = {'permissions': {'allow': ['Read']}}
        write_profile_settings_to_settings(delta, tmp_path)
        content = json.loads(settings_file.read_text(encoding='utf-8'))

        # Full replacement (not merge): 'deny' and 'ask' are GONE
        assert content['permissions'] == {'allow': ['Read']}


# ---------------------------------------------------------------------------
# Test Class 2: Step 14 / Step 18 Interaction (user-settings + profile delta)
# ---------------------------------------------------------------------------


class TestStep14Step18Interaction:
    """Verify write_user_settings() contributions survive Step 18 writes.

    Step 14 (write_user_settings) runs first and deep-merges the
    user-settings YAML section into settings.json. Step 18
    (write_profile_settings_to_settings) runs second and applies the
    profile delta. Step 18 must not delete keys that Step 14 wrote
    when those keys are absent from the profile delta.
    """

    def test_user_settings_permissions_preserved_when_no_root_permissions(
        self, tmp_path: Path,
    ) -> None:
        """user-settings.permissions survives when YAML has no root-level permissions.

        Step 14 write_user_settings() runs first and writes
        user-settings.permissions into settings.json via deep-merge. Step
        18 write_profile_settings_to_settings() then runs against an
        empty profile delta (root YAML has no permissions). The Step 14
        permissions entry must remain in the file because the writer
        only touches keys present in its own delta.
        """
        # Simulate Step 14 having written user-settings.permissions
        settings_file = tmp_path / 'settings.json'
        settings_file.write_text(json.dumps({
            'permissions': {'allow': ['Read', 'Write']},
            'language': 'english',
        }), encoding='utf-8')

        # Step 18: delta has NO 'permissions' (YAML root lacks it)
        delta = _build_profile_settings(hooks={}, hooks_dir=tmp_path / 'hooks', model='sonnet')
        assert 'permissions' not in delta

        write_profile_settings_to_settings(delta, tmp_path)
        content = json.loads(settings_file.read_text(encoding='utf-8'))

        # user-settings.permissions PRESERVED
        assert content['permissions'] == {'allow': ['Read', 'Write']}
        # user-settings.language PRESERVED
        assert content['language'] == 'english'
        # Profile delta model ADDED
        assert content['model'] == 'sonnet'

    def test_root_permissions_wins_over_user_settings_permissions(
        self, tmp_path: Path,
    ) -> None:
        """Root-level permissions REPLACES user-settings.permissions via step order."""
        # Step 14 wrote user-settings.permissions
        settings_file = tmp_path / 'settings.json'
        settings_file.write_text(json.dumps({
            'permissions': {'allow': ['Read']},
        }), encoding='utf-8')

        # Step 18 has root-level permissions (takes precedence)
        delta = _build_profile_settings(
            hooks={}, hooks_dir=tmp_path / 'hooks',
            permissions={'allow': ['Write', 'Edit']},
        )
        write_profile_settings_to_settings(delta, tmp_path)
        content = json.loads(settings_file.read_text(encoding='utf-8'))

        # Root-level won (full replace)
        assert content['permissions'] == {'allow': ['Write', 'Edit']}


# ---------------------------------------------------------------------------
# Test Class 3: Conflict Detection in Non-Command-Names Mode
# ---------------------------------------------------------------------------


class TestConflictDetectionInNonCommandNamesMode:
    """Verify detect_settings_conflicts() fires when command-names is absent.

    The function runs unconditionally in both isolated and non-isolated modes
    and reports keys declared at both YAML root level and under user-settings.
    """

    def test_conflict_detected_in_non_command_names_mode(self) -> None:
        """Conflict between user-settings and root fires in non-command-names mode."""
        user_settings = {'model': 'claude-opus-4'}
        root_config = {'model': 'claude-sonnet-4'}  # NO command-names

        conflicts = detect_settings_conflicts(user_settings, root_config)
        assert conflicts == [('model', 'claude-opus-4', 'claude-sonnet-4')]

    def test_kebab_to_camel_key_mapped(self) -> None:
        """kebab-case root keys mapped to camelCase user-settings keys."""
        user_settings = {'alwaysThinkingEnabled': True}
        root_config = {'always-thinking-enabled': False}

        conflicts = detect_settings_conflicts(user_settings, root_config)
        assert conflicts == [('alwaysThinkingEnabled', True, False)]

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
    def test_conflict_warning_emitted_via_main_without_command_names(
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
        """Warning is emitted via main() when root-level and user-settings conflict without command-names."""
        del mock_mkdir, mock_is_admin, mock_find_cmd, mock_skills, mock_resources
        del mock_deps, e2e_isolated_home
        mock_load.return_value = (
            {
                'name': 'Conflict Test',
                # NO command-names
                'model': 'claude-sonnet-4',
                'user-settings': {'model': 'claude-opus-4'},
            },
            'test.yaml',
        )
        mock_validate.return_value = (True, [])
        mock_install.return_value = True
        mock_mcp.return_value = (True, [], {'global_count': 0, 'profile_count': 0, 'combined_count': 0})

        from scripts import setup_environment

        with patch('sys.argv', ['setup_environment.py', 'test', '--yes', '--skip-install']), \
             patch('sys.exit') as mock_exit, \
             patch.object(setup_environment, 'write_user_settings', return_value=True), \
             patch.object(setup_environment, 'write_profile_settings_to_settings', return_value=True):
            setup_environment.main()
            mock_exit.assert_not_called()

        captured = capsys.readouterr()
        # Warning text identifies the conflicting key and both surfaces
        assert "Key 'model' specified in both root level and user-settings" in captured.out
        # Precedence message indicates Step 18 writes last, so the root-level value wins
        assert 'Root-level value takes precedence (written last in Step 18)' in captured.out


# ---------------------------------------------------------------------------
# Test Class 4: Profile-Scoped MCP Validation Error
# ---------------------------------------------------------------------------


class TestProfileMcpValidationError:
    """Verify exit 1 with 4-option fix-up message for profile MCP without command-names."""

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
    def test_profile_scope_alone_triggers_error(
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
        """Scope 'profile' without command-names -> exit 1 with actionable message."""
        del mock_mkdir, mock_is_admin, mock_find_cmd, mock_skills, mock_resources
        del mock_deps, e2e_isolated_home
        mock_load.return_value = (
            {
                'name': 'Profile MCP No Command',
                # NO command-names
                'mcp-servers': [
                    {
                        'name': 'profile-server',
                        'scope': 'profile',
                        'transport': 'http',
                        'url': 'http://localhost:3000',
                    },
                ],
            },
            'test.yaml',
        )
        mock_validate.return_value = (True, [])
        mock_install.return_value = True
        mock_mcp.return_value = (True, [], {'global_count': 0, 'profile_count': 0, 'combined_count': 0})

        from scripts import setup_environment

        with patch('sys.argv', ['setup_environment.py', 'test', '--yes', '--skip-install']), \
             pytest.raises(SystemExit) as excinfo:
            setup_environment.main()

        # sys.exit(1) was called
        assert excinfo.value.code == 1

        # error() messages go to stderr
        captured = capsys.readouterr()
        assert "MCP server 'profile-server' declares scope: profile" in captured.err
        assert 'command-names is not specified' in captured.err

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
    def test_combined_user_profile_scope_triggers_error(
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
        """Scope [user, profile] without command-names -> exit 1."""
        del mock_mkdir, mock_is_admin, mock_find_cmd, mock_skills, mock_resources
        del mock_deps, e2e_isolated_home
        mock_load.return_value = (
            {
                'name': 'Combined Profile MCP No Command',
                'mcp-servers': [
                    {
                        'name': 'combined-server',
                        'scope': ['user', 'profile'],
                        'transport': 'http',
                        'url': 'http://localhost:3000',
                    },
                ],
            },
            'test.yaml',
        )
        mock_validate.return_value = (True, [])
        mock_install.return_value = True
        mock_mcp.return_value = (True, [], {'global_count': 0, 'profile_count': 0, 'combined_count': 0})

        from scripts import setup_environment

        with patch('sys.argv', ['setup_environment.py', 'test', '--yes', '--skip-install']), \
             pytest.raises(SystemExit) as excinfo:
            setup_environment.main()

        assert excinfo.value.code == 1

        captured = capsys.readouterr()
        # error() messages go to stderr
        assert "MCP server 'combined-server' declares scope: profile" in captured.err

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
    def test_error_message_contains_4_options(
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
        """Error message enumerates all 4 fix-up options."""
        del mock_mkdir, mock_is_admin, mock_find_cmd, mock_skills, mock_resources
        del mock_deps, e2e_isolated_home
        mock_load.return_value = (
            {
                'name': 'Profile MCP 4 Options Test',
                'mcp-servers': [
                    {
                        'name': 'any-profile-server',
                        'scope': 'profile',
                        'transport': 'http',
                        'url': 'http://localhost:3000',
                    },
                ],
            },
            'test.yaml',
        )
        mock_validate.return_value = (True, [])
        mock_install.return_value = True
        mock_mcp.return_value = (True, [], {'global_count': 0, 'profile_count': 0, 'combined_count': 0})

        from scripts import setup_environment

        with patch('sys.argv', ['setup_environment.py', 'test', '--yes', '--skip-install']), \
             pytest.raises(SystemExit):
            setup_environment.main()

        captured = capsys.readouterr()
        # error() messages go to stderr - all four options enumerated in the error message
        assert '1. Add "command-names: [your-name]"' in captured.err
        assert '2. Change scope to "user"' in captured.err
        assert '3. Change scope to "local"' in captured.err
        assert '4. Change scope to "project"' in captured.err


# ---------------------------------------------------------------------------
# Test Class 5: System-Prompt Warning Without Command-Names
# ---------------------------------------------------------------------------


class TestSystemPromptWarning:
    """Verify warning emitted when command-defaults.system-prompt is set without command-names."""

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
    def test_warning_emitted(
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
        """Warning is printed; setup continues successfully."""
        del mock_mkdir, mock_is_admin, mock_find_cmd, mock_skills, mock_resources
        del mock_deps, e2e_isolated_home
        mock_load.return_value = (
            {
                'name': 'System Prompt Warning Test',
                # NO command-names
                'command-defaults': {
                    'system-prompt': 'prompts/my-prompt.md',
                    'mode': 'replace',
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
             patch.object(setup_environment, 'handle_resource', return_value=True), \
             patch.object(setup_environment, 'download_hook_files', return_value=True), \
             patch.object(setup_environment, 'write_profile_settings_to_settings', return_value=True):
            setup_environment.main()
            mock_exit.assert_not_called()

        captured = capsys.readouterr()
        # warning() messages go to stdout
        assert 'command-defaults.system-prompt' in captured.out
        assert 'but command-names is not specified' in captured.out
        assert 'there is no launcher' in captured.out
        assert 'system prompt will NOT be applied' in captured.out


# ---------------------------------------------------------------------------
# Test Class 6: Golden Config (No Command-Names) End-to-End Integration
# ---------------------------------------------------------------------------


@pytest.fixture
def golden_config_no_command_names() -> dict[str, Any]:
    """Load the no-command-names variant of golden_config.yaml."""
    config_path = Path(__file__).parent / 'golden_config_no_command_names.yaml'
    with config_path.open('r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    result: dict[str, Any] = config
    return result


class TestGoldenConfigNoCommandNames:
    """End-to-end integration test using golden_config_no_command_names.yaml."""

    def test_golden_config_absence_of_command_names(
        self,
        golden_config_no_command_names: dict[str, Any],
    ) -> None:
        """Verify golden_config_no_command_names.yaml does not declare command-names."""
        assert 'command-names' not in golden_config_no_command_names

    def test_golden_config_has_all_profile_keys(
        self,
        golden_config_no_command_names: dict[str, Any],
    ) -> None:
        """Verify the golden config declares every profile-owned key at root level."""
        cfg = golden_config_no_command_names
        assert 'model' in cfg
        assert 'permissions' in cfg
        assert 'env-variables' in cfg
        assert 'attribution' in cfg
        assert 'always-thinking-enabled' in cfg
        assert 'effort-level' in cfg
        assert 'company-announcements' in cfg
        assert 'status-line' in cfg
        assert 'hooks' in cfg

    def test_golden_config_no_profile_scoped_mcp(
        self,
        golden_config_no_command_names: dict[str, Any],
    ) -> None:
        """Verify NO mcp-server in the fixture uses scope 'profile'.

        Profile-scoped servers without command-names trigger an error; the
        no-command-names fixture must avoid them for happy-path coverage.
        """
        for server in golden_config_no_command_names.get('mcp-servers', []):
            scope = server.get('scope')
            if isinstance(scope, str):
                assert scope != 'profile'
            elif isinstance(scope, list):
                assert 'profile' not in scope

    def test_all_profile_keys_in_settings_json(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config_no_command_names: dict[str, Any],
    ) -> None:
        """After building delta + writing, all 9 profile-owned keys appear in settings.json."""
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']
        hooks_dir = claude_dir / 'hooks'
        hooks_dir.mkdir(parents=True, exist_ok=True)

        cfg = golden_config_no_command_names

        delta = _build_profile_settings(
            hooks=cfg.get('hooks', {}),
            hooks_dir=hooks_dir,
            model=cfg.get('model'),
            permissions=cfg.get('permissions'),
            env=cfg.get('env-variables'),
            always_thinking_enabled=cfg.get('always-thinking-enabled'),
            company_announcements=cfg.get('company-announcements'),
            attribution=cfg.get('attribution'),
            status_line=cfg.get('status-line'),
            effort_level=cfg.get('effort-level'),
        )

        write_profile_settings_to_settings(delta, claude_dir)

        settings_path = claude_dir / 'settings.json'
        assert settings_path.exists()
        content = json.loads(settings_path.read_text(encoding='utf-8'))

        # All 9 profile keys present
        assert set(content.keys()) == PROFILE_OWNED_KEYS

    def test_hooks_in_settings_not_config_json(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config_no_command_names: dict[str, Any],
    ) -> None:
        """Hooks key appears in settings.json; no config.json is created."""
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']
        hooks_dir = claude_dir / 'hooks'
        hooks_dir.mkdir(parents=True, exist_ok=True)

        cfg = golden_config_no_command_names

        delta = _build_profile_settings(
            hooks=cfg.get('hooks', {}),
            hooks_dir=hooks_dir,
            model=cfg.get('model'),
        )
        write_profile_settings_to_settings(delta, claude_dir)

        settings_path = claude_dir / 'settings.json'
        content = json.loads(settings_path.read_text(encoding='utf-8'))
        assert 'hooks' in content
        assert 'PostToolUse' in content['hooks']
        # Non-isolated mode: NO config.json anywhere
        assert not (claude_dir / 'config.json').exists()

    def test_status_line_absolute_path_in_settings(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config_no_command_names: dict[str, Any],
    ) -> None:
        """statusLine.command has absolute POSIX path under ~/.claude/hooks/."""
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']
        hooks_dir = claude_dir / 'hooks'
        hooks_dir.mkdir(parents=True, exist_ok=True)

        cfg = golden_config_no_command_names

        delta = _build_profile_settings(
            hooks=cfg.get('hooks', {}),
            hooks_dir=hooks_dir,
            status_line=cfg.get('status-line'),
        )
        write_profile_settings_to_settings(delta, claude_dir)

        settings_path = claude_dir / 'settings.json'
        content = json.loads(settings_path.read_text(encoding='utf-8'))
        sl = content['statusLine']
        assert sl['type'] == 'command'
        expected_path = (hooks_dir / 'e2e_statusline.py').as_posix()
        assert expected_path in sl['command']
        # Python script -> uv run prefix
        assert 'uv run' in sl['command']
        # Config file embedded in command string
        expected_cfg = (hooks_dir / 'e2e-statusline-config.yaml').as_posix()
        assert expected_cfg in sl['command']


# ---------------------------------------------------------------------------
# Test Class 7: Behavior Across Repeated Invocations With Evolving Content
# ---------------------------------------------------------------------------


class TestRepeatedInvocationSemantics:
    """Verify behavior across multiple invocations with evolving YAML content."""

    def test_initial_invocation_populates_declared_keys(self, tmp_path: Path) -> None:
        """First invocation against an empty file writes all declared keys."""
        delta = _build_profile_settings(
            hooks={}, hooks_dir=tmp_path / 'hooks',
            model='sonnet', permissions={'allow': ['Read']},
        )
        write_profile_settings_to_settings(delta, tmp_path)
        content = json.loads((tmp_path / 'settings.json').read_text(encoding='utf-8'))
        assert content == {'model': 'sonnet', 'permissions': {'allow': ['Read']}}

    def test_re_declaration_overwrites_previous_value(self, tmp_path: Path) -> None:
        """Re-declaring a key with a new value overwrites the previous value."""
        # First invocation
        delta1 = _build_profile_settings(
            hooks={}, hooks_dir=tmp_path / 'hooks',
            model='sonnet', permissions={'allow': ['Read']},
        )
        write_profile_settings_to_settings(delta1, tmp_path)

        # Second invocation (same keys, different values)
        delta2 = _build_profile_settings(
            hooks={}, hooks_dir=tmp_path / 'hooks',
            model='opus', permissions={'allow': ['Write']},
        )
        write_profile_settings_to_settings(delta2, tmp_path)
        content = json.loads((tmp_path / 'settings.json').read_text(encoding='utf-8'))
        assert content['model'] == 'opus'
        assert content['permissions'] == {'allow': ['Write']}

    def test_omitting_key_preserves_previous_value(self, tmp_path: Path) -> None:
        """Omitting a key on a later invocation preserves the previous value.

        The shared settings.json is a user-facing file, so the writer
        does not delete profile-owned keys when the current invocation
        does not declare them. To delete a key, the user must declare it
        explicitly as None or remove it manually.
        """
        # First invocation: both model and permissions
        delta1 = _build_profile_settings(
            hooks={}, hooks_dir=tmp_path / 'hooks',
            model='sonnet', permissions={'allow': ['Read']},
        )
        write_profile_settings_to_settings(delta1, tmp_path)

        # Second invocation: only model (permissions omitted)
        delta2 = _build_profile_settings(
            hooks={}, hooks_dir=tmp_path / 'hooks',
            model='opus',
        )
        write_profile_settings_to_settings(delta2, tmp_path)
        content = json.loads((tmp_path / 'settings.json').read_text(encoding='utf-8'))

        # Model updated, permissions PRESERVED from previous invocation
        assert content['model'] == 'opus'
        assert content['permissions'] == {'allow': ['Read']}

    def test_multiple_invocations_accumulate_distinct_keys(self, tmp_path: Path) -> None:
        """Multiple invocations with different subsets preserve accumulated state."""
        # First invocation: model + permissions
        write_profile_settings_to_settings(
            _build_profile_settings(
                hooks={}, hooks_dir=tmp_path / 'hooks',
                model='sonnet', permissions={'allow': ['Read']},
            ),
            tmp_path,
        )

        # Second invocation: add env (model re-declared, permissions omitted)
        write_profile_settings_to_settings(
            _build_profile_settings(
                hooks={}, hooks_dir=tmp_path / 'hooks',
                model='opus', env={'FOO': 'bar'},
            ),
            tmp_path,
        )

        # Third invocation: add effort_level (previous keys all omitted)
        write_profile_settings_to_settings(
            _build_profile_settings(
                hooks={}, hooks_dir=tmp_path / 'hooks',
                effort_level='high',
            ),
            tmp_path,
        )

        content = json.loads((tmp_path / 'settings.json').read_text(encoding='utf-8'))
        # Accumulated: permissions from the first invocation, env from the
        # second, effortLevel from the third. Model was re-declared in the
        # second invocation, so it ends up as 'opus'.
        assert content['model'] == 'opus'
        assert content['permissions'] == {'allow': ['Read']}
        assert content['env'] == {'FOO': 'bar'}
        assert content['effortLevel'] == 'high'


# ---------------------------------------------------------------------------
# Test Class 8: Auto-Update Target 2 Survival (regression)
# ---------------------------------------------------------------------------


class TestAutoUpdateTarget2Survival:
    """Verify the Target 2 auto-update injection survives the profile settings write.

    When version pinning is active, apply_auto_update_settings() injects
    DISABLE_AUTOUPDATER into user_settings.env (its Target 2). Step 14
    then writes that entry to settings.json.env. The subsequent Step 18
    profile-settings write must not destroy that entry when the YAML
    root has no env-variables declaration.
    """

    def test_disable_autoupdater_preserved_when_no_root_env(self, tmp_path: Path) -> None:
        """DISABLE_AUTOUPDATER in settings.json.env survives the profile write.

        Set up settings.json.env containing DISABLE_AUTOUPDATER (the state
        Step 14 leaves behind for a pinned-version configuration), then
        run the profile-settings writer with a delta that contains no
        'env' key. The writer must leave the existing 'env' value alone.
        """
        # Simulate Step 14 having written user_settings with env DISABLE_AUTOUPDATER
        settings_file = tmp_path / 'settings.json'
        settings_file.write_text(json.dumps({
            'env': {'DISABLE_AUTOUPDATER': '1'},
        }), encoding='utf-8')

        # Step 18: delta has no 'env' key (YAML has no env-variables)
        delta = _build_profile_settings(hooks={}, hooks_dir=tmp_path / 'hooks', model='sonnet')
        assert 'env' not in delta

        write_profile_settings_to_settings(delta, tmp_path)
        content = json.loads(settings_file.read_text(encoding='utf-8'))
        assert content['env']['DISABLE_AUTOUPDATER'] == '1'
        assert content['model'] == 'sonnet'

    def test_root_env_variables_replace_existing_env_value(self, tmp_path: Path) -> None:
        """When YAML declares env-variables, root-level env replaces the existing 'env' value."""
        settings_file = tmp_path / 'settings.json'
        settings_file.write_text(json.dumps({
            'env': {'DISABLE_AUTOUPDATER': '1', 'STALE': 'x'},
        }), encoding='utf-8')

        # The delta carries a root-level env value
        delta = _build_profile_settings(
            hooks={}, hooks_dir=tmp_path / 'hooks',
            env={'FOO': 'bar'},
        )
        write_profile_settings_to_settings(delta, tmp_path)
        content = json.loads(settings_file.read_text(encoding='utf-8'))
        # Full replacement
        assert content['env'] == {'FOO': 'bar'}


# ---------------------------------------------------------------------------
# Test Class 9: No Profile Keys = No File I/O
# ---------------------------------------------------------------------------


class TestEmptyDeltaNoOp:
    """Verify writer does not touch settings.json when delta is empty."""

    def test_empty_delta_does_not_create_file(self, tmp_path: Path) -> None:
        """Empty delta -> no file created."""
        write_profile_settings_to_settings({}, tmp_path)
        assert not (tmp_path / 'settings.json').exists()

    def test_empty_delta_does_not_modify_existing(self, tmp_path: Path) -> None:
        """Empty delta -> existing settings.json unchanged."""
        settings_file = tmp_path / 'settings.json'
        original = {'language': 'english', 'model': 'sonnet'}
        settings_file.write_text(json.dumps(original), encoding='utf-8')

        write_profile_settings_to_settings({}, tmp_path)

        content = json.loads(settings_file.read_text(encoding='utf-8'))
        assert content == original
