"""
Unit tests for idempotent MCP server configuration.

Covers the pure decision layer that lets configure_all_mcp_servers() skip
the `claude mcp remove`/`claude mcp add` cycle for servers whose live
configuration already matches the declared one: expected-entry prediction,
live-entry reading, entry comparison, project-key matching, and action
planning. The remove/add cycle matters because `claude mcp remove` clears
stored MCP OAuth tokens of http/sse servers.
"""

import contextlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))


import setup_environment


class TestBuildExpectedMcpEntry:
    """Tests for _build_expected_mcp_entry()."""

    @patch('platform.system', return_value='Linux')
    def test_stdio_simple_unix(self, mock_system: MagicMock) -> None:
        del mock_system
        server = {'name': 'srv', 'command': 'uvx my-server'}
        entry = setup_environment._build_expected_mcp_entry(server)
        assert entry == {'type': 'stdio', 'command': 'uvx', 'args': ['my-server'], 'env': {}}

    @patch('platform.system', return_value='Linux')
    def test_stdio_with_args_and_env_unix(self, mock_system: MagicMock) -> None:
        del mock_system
        server = {
            'name': 'srv',
            'command': 'uvx my-server',
            'args': ['--flag', 'value with space'],
            'env': ['FOO=bar', 'BAZ=${QUX}'],
        }
        entry = setup_environment._build_expected_mcp_entry(server)
        assert entry == {
            'type': 'stdio',
            'command': 'uvx',
            'args': ['my-server', '--flag', 'value with space'],
            'env': {'FOO': 'bar', 'BAZ': '${QUX}'},
        }

    @patch('platform.system', return_value='Linux')
    def test_stdio_env_string_form_unix(self, mock_system: MagicMock) -> None:
        del mock_system
        server = {'name': 'srv', 'command': 'uvx my-server', 'env': 'KEY=value'}
        entry = setup_environment._build_expected_mcp_entry(server)
        assert entry is not None
        assert entry['env'] == {'KEY': 'value'}

    @patch('platform.system', return_value='Windows')
    def test_stdio_npx_gets_cmd_wrapper_on_windows(self, mock_system: MagicMock) -> None:
        del mock_system
        server = {'name': 'srv', 'command': 'npx -y some-pkg --flag val'}
        entry = setup_environment._build_expected_mcp_entry(server)
        assert entry == {
            'type': 'stdio',
            'command': 'cmd',
            'args': ['/c', 'npx', '-y', 'some-pkg', '--flag', 'val'],
            'env': {},
        }

    @patch('platform.system', return_value='Windows')
    def test_stdio_non_npx_no_wrapper_on_windows(self, mock_system: MagicMock) -> None:
        del mock_system
        server = {'name': 'srv', 'command': 'uv run server.py'}
        entry = setup_environment._build_expected_mcp_entry(server)
        assert entry == {'type': 'stdio', 'command': 'uv', 'args': ['run', 'server.py'], 'env': {}}

    @patch('platform.system', return_value='Linux')
    def test_http_with_header_unix(self, mock_system: MagicMock) -> None:
        del mock_system
        server = {
            'name': 'srv',
            'transport': 'http',
            'url': 'https://example.invalid/mcp',
            'header': 'Authorization: Bearer ${TOK}',
        }
        entry = setup_environment._build_expected_mcp_entry(server)
        assert entry == {
            'type': 'http',
            'url': 'https://example.invalid/mcp',
            'headers': {'Authorization': 'Bearer ${TOK}'},
        }

    @patch('platform.system', return_value='Linux')
    def test_sse_without_header(self, mock_system: MagicMock) -> None:
        del mock_system
        server = {'name': 'srv', 'transport': 'sse', 'url': 'https://example.invalid/sse'}
        entry = setup_environment._build_expected_mcp_entry(server)
        assert entry == {'type': 'sse', 'url': 'https://example.invalid/sse'}

    def test_missing_url_and_command_returns_none(self) -> None:
        assert setup_environment._build_expected_mcp_entry({'name': 'srv'}) is None

    def test_invalid_env_type_returns_none(self) -> None:
        server = {'name': 'srv', 'command': 'uvx x', 'env': {'FOO': 'bar'}}
        assert setup_environment._build_expected_mcp_entry(server) is None


class TestMcpEntriesEqual:
    """Tests for _mcp_entries_equal()."""

    def test_identical_entries_match(self) -> None:
        expected = {'type': 'stdio', 'command': 'uvx', 'args': ['x'], 'env': {}}
        live = {'type': 'stdio', 'command': 'uvx', 'args': ['x'], 'env': {}}
        assert setup_environment._mcp_entries_equal(live, expected)

    def test_absent_keys_equal_empty_collections(self) -> None:
        expected = {'type': 'sse', 'url': 'https://x/sse'}
        live = {'type': 'sse', 'url': 'https://x/sse', 'headers': {}, 'env': {}, 'args': []}
        assert setup_environment._mcp_entries_equal(live, expected)

    def test_unknown_live_fields_are_ignored(self) -> None:
        expected = {'type': 'http', 'url': 'https://x/mcp'}
        live = {'type': 'http', 'url': 'https://x/mcp', 'someFutureField': 'value'}
        assert setup_environment._mcp_entries_equal(live, expected)

    def test_differing_args_do_not_match(self) -> None:
        expected = {'type': 'stdio', 'command': 'uvx', 'args': ['a'], 'env': {}}
        live = {'type': 'stdio', 'command': 'uvx', 'args': ['b'], 'env': {}}
        assert not setup_environment._mcp_entries_equal(live, expected)

    def test_differing_env_do_not_match(self) -> None:
        expected = {'type': 'stdio', 'command': 'uvx', 'args': [], 'env': {'A': '1'}}
        live = {'type': 'stdio', 'command': 'uvx', 'args': [], 'env': {'A': '2'}}
        assert not setup_environment._mcp_entries_equal(live, expected)

    def test_differing_url_do_not_match(self) -> None:
        expected = {'type': 'http', 'url': 'https://x/mcp'}
        live = {'type': 'http', 'url': 'https://y/mcp'}
        assert not setup_environment._mcp_entries_equal(live, expected)

    def test_non_dict_live_does_not_match(self) -> None:
        assert not setup_environment._mcp_entries_equal('garbage', {'type': 'http', 'url': 'u'})
        assert not setup_environment._mcp_entries_equal(None, {'type': 'http', 'url': 'u'})


class TestProjectKeyMatching:
    """Tests for _normalize_project_dir_key() and _find_project_entry()."""

    @patch('platform.system', return_value='Windows')
    def test_windows_key_matching_is_case_insensitive(self, mock_system: MagicMock) -> None:
        del mock_system
        projects: dict[str, Any] = {'C:/Users/Dev/proj': {'mcpServers': {}}}
        entry = setup_environment._find_project_entry(projects, Path('c:/users/dev/proj'))
        assert entry == {'mcpServers': {}}

    @patch('platform.system', return_value='Windows')
    def test_windows_backslashes_and_trailing_slash_normalized(self, mock_system: MagicMock) -> None:
        del mock_system
        projects: dict[str, Any] = {'C:/Users/Dev/proj': {'mcpServers': {'a': {}}}}
        entry = setup_environment._find_project_entry(projects, Path(r'C:\Users\Dev\proj'))
        assert entry == {'mcpServers': {'a': {}}}
        assert setup_environment._normalize_project_dir_key('C:/Users/Dev/proj/') == 'c:/users/dev/proj'

    @patch('platform.system', return_value='Linux')
    def test_linux_key_matching_is_case_sensitive(self, mock_system: MagicMock) -> None:
        del mock_system
        projects: dict[str, Any] = {'/home/dev/proj': {'mcpServers': {}}}
        assert setup_environment._find_project_entry(projects, Path('/home/dev/proj')) == {'mcpServers': {}}
        assert setup_environment._find_project_entry(projects, Path('/home/Dev/proj')) is None

    @patch('platform.system', return_value='Linux')
    def test_no_match_returns_none(self, mock_system: MagicMock) -> None:
        del mock_system
        assert setup_environment._find_project_entry({}, Path('/home/dev/proj')) is None

    @pytest.mark.skipif(sys.platform == 'win32', reason='symlink creation requires privileges on Windows')
    def test_symlinked_key_matches_physical_directory(self, tmp_path: Path) -> None:
        # A key recorded through a symlinked path (macOS /var vs
        # /private/var) must still match the physical working directory
        real_dir = tmp_path / 'real'
        real_dir.mkdir()
        link = tmp_path / 'link'
        link.symlink_to(real_dir, target_is_directory=True)
        projects: dict[str, Any] = {str(link): {'mcpServers': {'a': {}}}}
        entry = setup_environment._find_project_entry(projects, real_dir)
        assert entry == {'mcpServers': {'a': {}}}


class TestReadJsonObject:
    """Tests for _read_json_object()."""

    def test_missing_file_is_empty_object(self, tmp_path: Path) -> None:
        assert setup_environment._read_json_object(tmp_path / 'absent.json') == {}

    def test_invalid_json_is_none(self, tmp_path: Path) -> None:
        target = tmp_path / 'broken.json'
        target.write_text('{not json', encoding='utf-8')
        assert setup_environment._read_json_object(target) is None

    def test_non_object_json_is_none(self, tmp_path: Path) -> None:
        target = tmp_path / 'list.json'
        target.write_text('[1, 2]', encoding='utf-8')
        assert setup_environment._read_json_object(target) is None

    def test_valid_object_is_returned(self, tmp_path: Path) -> None:
        target = tmp_path / 'ok.json'
        target.write_text('{"a": 1}', encoding='utf-8')
        assert setup_environment._read_json_object(target) == {'a': 1}


class TestReadLiveMcpEntries:
    """Tests for _read_live_mcp_entries()."""

    def test_reads_all_three_scopes(self, tmp_path: Path) -> None:
        project_dir = tmp_path / 'proj'
        project_dir.mkdir()
        user_entry = {'type': 'stdio', 'command': 'uvx', 'args': ['u'], 'env': {}}
        local_entry = {'type': 'stdio', 'command': 'uvx', 'args': ['l'], 'env': {}}
        project_entry = {'type': 'stdio', 'command': 'uvx', 'args': ['p'], 'env': {}}
        (tmp_path / '.claude.json').write_text(json.dumps({
            'mcpServers': {'srv': user_entry},
            'projects': {str(project_dir).replace('\\', '/'): {'mcpServers': {'srv': local_entry}}},
        }), encoding='utf-8')
        (project_dir / '.mcp.json').write_text(json.dumps({
            'mcpServers': {'srv': project_entry},
        }), encoding='utf-8')

        with contextlib.chdir(project_dir):
            live = setup_environment._read_live_mcp_entries('srv', tmp_path)

        assert live == {'user': user_entry, 'local': local_entry, 'project': project_entry}

    def test_absent_name_yields_all_none(self, tmp_path: Path) -> None:
        project_dir = tmp_path / 'proj'
        project_dir.mkdir()
        with contextlib.chdir(project_dir):
            live = setup_environment._read_live_mcp_entries('srv', tmp_path)
        assert live == {'user': None, 'local': None, 'project': None}

    def test_unreadable_global_config_yields_none(self, tmp_path: Path) -> None:
        project_dir = tmp_path / 'proj'
        project_dir.mkdir()
        (tmp_path / '.claude.json').write_text('{broken', encoding='utf-8')
        with contextlib.chdir(project_dir):
            assert setup_environment._read_live_mcp_entries('srv', tmp_path) is None

    def test_unreadable_project_file_yields_none(self, tmp_path: Path) -> None:
        project_dir = tmp_path / 'proj'
        project_dir.mkdir()
        (project_dir / '.mcp.json').write_text('{broken', encoding='utf-8')
        with contextlib.chdir(project_dir):
            assert setup_environment._read_live_mcp_entries('srv', tmp_path) is None

    def test_env_var_resolves_config_dir_when_no_artifact_dir(self, tmp_path: Path) -> None:
        project_dir = tmp_path / 'proj'
        project_dir.mkdir()
        user_entry = {'type': 'http', 'url': 'https://x/mcp'}
        (tmp_path / '.claude.json').write_text(json.dumps({
            'mcpServers': {'srv': user_entry},
        }), encoding='utf-8')
        env = {'CLAUDE_CONFIG_DIR': str(tmp_path)}
        with patch.dict(os.environ, env), contextlib.chdir(project_dir):
            live = setup_environment._read_live_mcp_entries('srv', None)
        assert live is not None
        assert live['user'] == user_entry


class TestPlanMcpServerAction:
    """Tests for _plan_mcp_server_action()."""

    def _write_global(self, config_dir: Path, payload: dict[str, Any]) -> None:
        (config_dir / '.claude.json').write_text(json.dumps(payload), encoding='utf-8')

    def test_fresh_server_adds_without_removal(self, tmp_path: Path) -> None:
        with contextlib.chdir(tmp_path):
            plan = setup_environment._plan_mcp_server_action(
                {'name': 'srv', 'command': 'uvx x', 'scope': 'user'}, 'user', tmp_path,
            )
        assert plan.action == 'reconfigure'
        assert plan.remove_scopes == []
        assert plan.clears_oauth is False

    @patch('platform.system', return_value='Linux')
    def test_matching_entry_skips(self, mock_system: MagicMock, tmp_path: Path) -> None:
        del mock_system
        self._write_global(tmp_path, {
            'mcpServers': {'srv': {'type': 'stdio', 'command': 'uvx', 'args': ['x'], 'env': {}}},
        })
        with contextlib.chdir(tmp_path):
            plan = setup_environment._plan_mcp_server_action(
                {'name': 'srv', 'command': 'uvx x', 'scope': 'user'}, 'user', tmp_path,
            )
        assert plan.action == 'skip'
        assert plan.remove_scopes == []

    @patch('platform.system', return_value='Linux')
    def test_matching_entry_with_stale_local_removes_only_local(
        self, mock_system: MagicMock, tmp_path: Path,
    ) -> None:
        del mock_system
        self._write_global(tmp_path, {
            'mcpServers': {'srv': {'type': 'stdio', 'command': 'uvx', 'args': ['x'], 'env': {}}},
            'projects': {str(tmp_path).replace('\\', '/'): {
                'mcpServers': {'srv': {'type': 'stdio', 'command': 'other', 'args': [], 'env': {}}},
            }},
        })
        with contextlib.chdir(tmp_path):
            plan = setup_environment._plan_mcp_server_action(
                {'name': 'srv', 'command': 'uvx x', 'scope': 'user'}, 'user', tmp_path,
            )
        assert plan.action == 'skip'
        assert plan.remove_scopes == ['local']

    @patch('platform.system', return_value='Linux')
    def test_matching_config_at_wrong_scope_is_not_a_match(
        self, mock_system: MagicMock, tmp_path: Path,
    ) -> None:
        del mock_system
        # The declared scope is local, but the matching entry lives at user
        # scope: the plan must reconfigure (removing the user entry), never
        # treat the wrong-scope match as already-configured
        self._write_global(tmp_path, {
            'mcpServers': {'srv': {'type': 'stdio', 'command': 'uvx', 'args': ['x'], 'env': {}}},
        })
        with contextlib.chdir(tmp_path):
            plan = setup_environment._plan_mcp_server_action(
                {'name': 'srv', 'command': 'uvx x', 'scope': 'local'}, 'local', tmp_path,
            )
        assert plan.action == 'reconfigure'
        assert plan.remove_scopes == ['user']

    @patch('platform.system', return_value='Linux')
    def test_changed_http_entry_reconfigures_and_clears_oauth(
        self, mock_system: MagicMock, tmp_path: Path,
    ) -> None:
        del mock_system
        self._write_global(tmp_path, {
            'mcpServers': {'srv': {'type': 'http', 'url': 'https://old.invalid/mcp'}},
        })
        with contextlib.chdir(tmp_path):
            plan = setup_environment._plan_mcp_server_action(
                {'name': 'srv', 'transport': 'http', 'url': 'https://new.invalid/mcp', 'scope': 'user'},
                'user', tmp_path,
            )
        assert plan.action == 'reconfigure'
        assert plan.remove_scopes == ['user']
        assert plan.clears_oauth is True

    @patch('platform.system', return_value='Linux')
    def test_changed_stdio_entry_does_not_clear_oauth(
        self, mock_system: MagicMock, tmp_path: Path,
    ) -> None:
        del mock_system
        self._write_global(tmp_path, {
            'mcpServers': {'srv': {'type': 'stdio', 'command': 'old', 'args': [], 'env': {}}},
        })
        with contextlib.chdir(tmp_path):
            plan = setup_environment._plan_mcp_server_action(
                {'name': 'srv', 'command': 'uvx x', 'scope': 'user'}, 'user', tmp_path,
            )
        assert plan.action == 'reconfigure'
        assert plan.remove_scopes == ['user']
        assert plan.clears_oauth is False

    @patch('platform.system', return_value='Linux')
    def test_profile_scope_removes_only_present_scopes(
        self, mock_system: MagicMock, tmp_path: Path,
    ) -> None:
        del mock_system
        self._write_global(tmp_path, {
            'mcpServers': {'srv': {'type': 'stdio', 'command': 'uvx', 'args': ['x'], 'env': {}}},
        })
        with contextlib.chdir(tmp_path):
            plan = setup_environment._plan_mcp_server_action(
                {'name': 'srv', 'command': 'uvx x', 'scope': 'profile'}, 'profile', tmp_path,
            )
        assert plan.action == 'skip'
        assert plan.remove_scopes == ['user']

    def test_profile_scope_with_no_entries_removes_nothing(self, tmp_path: Path) -> None:
        with contextlib.chdir(tmp_path):
            plan = setup_environment._plan_mcp_server_action(
                {'name': 'srv', 'command': 'uvx x', 'scope': 'profile'}, 'profile', tmp_path,
            )
        assert plan.action == 'skip'
        assert plan.remove_scopes == []

    def test_unreadable_config_falls_back_to_full_reconfigure(self, tmp_path: Path) -> None:
        (tmp_path / '.claude.json').write_text('{broken', encoding='utf-8')
        with contextlib.chdir(tmp_path):
            plan = setup_environment._plan_mcp_server_action(
                {'name': 'srv', 'command': 'uvx x', 'scope': 'user'}, 'user', tmp_path,
            )
        assert plan.action == 'reconfigure'
        assert plan.remove_scopes == list(setup_environment.MCP_CLI_SCOPES)

    def test_missing_name_falls_back_to_full_reconfigure(self, tmp_path: Path) -> None:
        with contextlib.chdir(tmp_path):
            plan = setup_environment._plan_mcp_server_action(
                {'command': 'uvx x', 'scope': 'user'}, 'user', tmp_path,
            )
        assert plan.action == 'reconfigure'
        assert plan.remove_scopes == list(setup_environment.MCP_CLI_SCOPES)

    def test_invalid_spec_falls_back_to_full_reconfigure(self, tmp_path: Path) -> None:
        # No url and no command: the expected entry cannot be built, so the
        # plan must not skip (configure_mcp_server reports the error)
        with contextlib.chdir(tmp_path):
            plan = setup_environment._plan_mcp_server_action(
                {'name': 'srv', 'scope': 'user'}, 'user', tmp_path,
            )
        assert plan.action == 'reconfigure'
        assert plan.remove_scopes == list(setup_environment.MCP_CLI_SCOPES)


class TestConfigureMcpServerRemoveScopes:
    """Tests for the remove_scopes parameter of configure_mcp_server()."""

    @patch('platform.system', return_value='Linux')
    @patch('setup_environment.find_command', return_value='claude')
    @patch('setup_environment.run_command')
    def test_empty_remove_scopes_skips_removal_entirely(
        self, mock_run: MagicMock, mock_find: MagicMock, mock_system: MagicMock,
    ) -> None:
        del mock_find, mock_system
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')
        server = {'name': 'srv', 'command': 'uvx x', 'scope': 'user'}

        result = setup_environment.configure_mcp_server(server, remove_scopes=[])

        assert result is True
        assert mock_run.call_count == 1
        assert 'add' in mock_run.call_args_list[0][0][0]
        assert 'remove' not in mock_run.call_args_list[0][0][0]

    @patch('platform.system', return_value='Linux')
    @patch('setup_environment.find_command', return_value='claude')
    @patch('setup_environment.run_command')
    def test_default_removes_from_all_cli_scopes(
        self, mock_run: MagicMock, mock_find: MagicMock, mock_system: MagicMock,
    ) -> None:
        del mock_find, mock_system
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')
        server = {'name': 'srv', 'command': 'uvx x', 'scope': 'user'}

        result = setup_environment.configure_mcp_server(server)

        assert result is True
        removal_scopes = [
            call[0][0][call[0][0].index('--scope') + 1]
            for call in mock_run.call_args_list
            if 'remove' in call[0][0]
        ]
        assert removal_scopes == list(setup_environment.MCP_CLI_SCOPES)

    @patch('platform.system', return_value='Linux')
    @patch('setup_environment.find_command', return_value='claude')
    @patch('setup_environment.run_command')
    def test_subset_remove_scopes_removes_only_those(
        self, mock_run: MagicMock, mock_find: MagicMock, mock_system: MagicMock,
    ) -> None:
        del mock_find, mock_system
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')
        server = {'name': 'srv', 'command': 'uvx x', 'scope': 'user'}

        result = setup_environment.configure_mcp_server(server, remove_scopes=['local'])

        assert result is True
        removal_scopes = [
            call[0][0][call[0][0].index('--scope') + 1]
            for call in mock_run.call_args_list
            if 'remove' in call[0][0]
        ]
        assert removal_scopes == ['local']
