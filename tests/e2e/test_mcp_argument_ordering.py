"""E2E tests for MCP server CLI argument ordering.

Tests verify that configure_all_mcp_servers() generates CLI commands
with correct argument ordering per Claude CLI (Commander.js) syntax:
- Non-variadic options (--transport, --env) precede positional arguments (name, url)
- Variadic --header option comes AFTER positional arguments (name, url)

Placing --header after positionals prevents Commander.js from greedily
consuming positional arguments as additional header values, which causes
'error: missing required argument name' failures.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from scripts import setup_environment
from scripts.setup_environment import configure_all_mcp_servers


def _find_mcp_add_call(call_args_list: list[Any], server_name: str) -> str | None:
    """Find the 'mcp add' bash command for a specific server in captured calls.

    Args:
        call_args_list: List of call_args from mock.call_args_list
        server_name: MCP server name to search for

    Returns:
        The bash command string containing 'mcp add' for the server, or None
    """
    for call in call_args_list:
        cmd = call[0][0]  # First positional arg
        if isinstance(cmd, str) and 'mcp add' in cmd and server_name in cmd:
            return cmd
    return None


# Whether a usable bash is unavailable on this host, evaluated once at collection time.
# The real-shell MCP test needs Git Bash on Windows (run_bash_command) or native bash on
# Unix; skip it cleanly when neither is present rather than failing.
_BASH_UNAVAILABLE: bool = (
    setup_environment.find_bash_windows() is None
    if sys.platform == 'win32'
    else shutil.which('bash') is None
)


class TestMCPArgumentOrdering:
    """E2E tests for CLI argument ordering in MCP server configuration."""

    def test_http_with_header_options_precede_positionals_unix(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify HTTP transport places variadic --header after positional args on Unix."""
        mock_bash = MagicMock(
            return_value=subprocess.CompletedProcess([], 0, '', ''),
        )
        mock_run = MagicMock(
            return_value=subprocess.CompletedProcess([], 0, '', ''),
        )

        with (
            patch('platform.system', return_value='Linux'),
            patch.object(
                setup_environment, 'find_command',
                return_value='/usr/local/bin/claude',
            ),
            patch.object(setup_environment, 'run_bash_command', mock_bash),
            patch.object(setup_environment, 'run_command', mock_run),
        ):
            profile_mcp_path = e2e_isolated_home['claude_dir'] / 'mcp.json'
            configure_all_mcp_servers(
                servers=golden_config.get('mcp-servers', []),
                profile_mcp_config_path=profile_mcp_path,
            )

        # Find the 'mcp add' call for e2e-http-server (HTTP with header, user scope)
        bash_cmd = _find_mcp_add_call(mock_bash.call_args_list, 'e2e-http-server')
        assert bash_cmd is not None, (
            'No mcp add command found for e2e-http-server in run_bash_command calls'
        )

        # Verify non-variadic options precede positional arguments
        transport_pos = bash_cmd.index('--transport')
        header_pos = bash_cmd.index('--header')
        name_pos = bash_cmd.index('e2e-http-server')
        url_pos = bash_cmd.index('http://localhost:3000/api')

        assert transport_pos < name_pos, (
            '--transport must precede server name positional argument'
        )
        assert name_pos < url_pos, (
            'server name must precede url positional argument'
        )
        # Variadic --header must come AFTER positional arguments
        assert header_pos > url_pos, (
            '--header must come after url (variadic option prevents greedy consumption)'
        )

    def test_http_with_header_options_precede_positionals_windows(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify HTTP transport places variadic --header after positional args on Windows."""
        mock_bash = MagicMock(
            return_value=subprocess.CompletedProcess([], 0, '', ''),
        )
        mock_run = MagicMock(
            return_value=subprocess.CompletedProcess([], 0, '', ''),
        )

        with (
            patch('platform.system', return_value='Windows'),
            patch.object(
                setup_environment, 'find_command',
                return_value=r'C:\Users\Test\AppData\Roaming\npm\claude.CMD',
            ),
            patch.object(setup_environment, 'run_bash_command', mock_bash),
            patch.object(setup_environment, 'run_command', mock_run),
            patch('pathlib.Path.exists', return_value=False),
        ):
            profile_mcp_path = e2e_isolated_home['claude_dir'] / 'mcp.json'
            configure_all_mcp_servers(
                servers=golden_config.get('mcp-servers', []),
                profile_mcp_config_path=profile_mcp_path,
            )

        # Find the 'mcp add' call for e2e-http-server (HTTP with header, user scope)
        bash_cmd = _find_mcp_add_call(mock_bash.call_args_list, 'e2e-http-server')
        assert bash_cmd is not None, (
            'No mcp add command found for e2e-http-server in run_bash_command calls'
        )

        # Verify non-variadic options precede positional arguments in bash_cmd string
        transport_pos = bash_cmd.index('--transport')
        header_pos = bash_cmd.index('--header')
        name_pos = bash_cmd.index('e2e-http-server')
        url_pos = bash_cmd.index('http://localhost:3000/api')

        assert transport_pos < name_pos, (
            '--transport must precede server name positional argument on Windows'
        )
        assert name_pos < url_pos, (
            'server name must precede url positional argument on Windows'
        )
        # Variadic --header must come AFTER positional arguments
        assert header_pos > url_pos, (
            '--header must come after url on Windows (variadic option prevents greedy consumption)'
        )

    def test_http_with_env_and_header_all_options_precede_positionals(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify HTTP transport with --env and --header: non-variadic before positionals, variadic after."""
        mock_bash = MagicMock(
            return_value=subprocess.CompletedProcess([], 0, '', ''),
        )
        mock_run = MagicMock(
            return_value=subprocess.CompletedProcess([], 0, '', ''),
        )

        with (
            patch('platform.system', return_value='Linux'),
            patch.object(
                setup_environment, 'find_command',
                return_value='/usr/local/bin/claude',
            ),
            patch.object(setup_environment, 'run_bash_command', mock_bash),
            patch.object(setup_environment, 'run_command', mock_run),
        ):
            profile_mcp_path = e2e_isolated_home['claude_dir'] / 'mcp.json'
            configure_all_mcp_servers(
                servers=golden_config.get('mcp-servers', []),
                profile_mcp_config_path=profile_mcp_path,
            )

        # e2e-http-server has BOTH env ("E2E_HTTP_TOKEN") and header ("X-API-Key: test-key")
        bash_cmd = _find_mcp_add_call(mock_bash.call_args_list, 'e2e-http-server')
        assert bash_cmd is not None, (
            'No mcp add command found for e2e-http-server in run_bash_command calls'
        )

        # Non-variadic options (--env, --transport) must precede name and url
        name_pos = bash_cmd.index('e2e-http-server')
        url_pos = bash_cmd.index('http://localhost:3000/api')
        assert bash_cmd.index('--env') < name_pos, (
            '--env must precede server name positional argument'
        )
        assert bash_cmd.index('--transport') < name_pos, (
            '--transport must precede server name positional argument'
        )
        assert name_pos < url_pos, (
            'server name must precede url positional argument'
        )
        # Variadic --header must come AFTER positional arguments
        assert bash_cmd.index('--header') > url_pos, (
            '--header must come after url (variadic option prevents greedy consumption)'
        )

    def test_http_without_header_argument_order_unchanged(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Regression test: HTTP/SSE transport without header maintains correct argument order."""
        mock_bash = MagicMock(
            return_value=subprocess.CompletedProcess([], 0, '', ''),
        )
        mock_run = MagicMock(
            return_value=subprocess.CompletedProcess([], 0, '', ''),
        )

        with (
            patch('platform.system', return_value='Linux'),
            patch.object(
                setup_environment, 'find_command',
                return_value='/usr/local/bin/claude',
            ),
            patch.object(setup_environment, 'run_bash_command', mock_bash),
            patch.object(setup_environment, 'run_command', mock_run),
        ):
            profile_mcp_path = e2e_isolated_home['claude_dir'] / 'mcp.json'
            configure_all_mcp_servers(
                servers=golden_config.get('mcp-servers', []),
                profile_mcp_config_path=profile_mcp_path,
            )

        # e2e-sse-server is SSE transport with no header (project scope)
        bash_cmd = _find_mcp_add_call(mock_bash.call_args_list, 'e2e-sse-server')
        assert bash_cmd is not None, (
            'No mcp add command found for e2e-sse-server in run_bash_command calls'
        )

        # --transport must still precede server name, and name must precede url
        transport_pos = bash_cmd.index('--transport')
        name_pos = bash_cmd.index('e2e-sse-server')
        url_pos = bash_cmd.index('http://localhost:3001/events')

        assert transport_pos < name_pos, (
            '--transport must precede server name positional argument'
        )
        assert name_pos < url_pos, (
            'server name must precede url positional argument'
        )

        # --header should NOT be present in this command
        assert '--header' not in bash_cmd, (
            'SSE server without header config should not have --header option'
        )

    def test_combined_scope_dispatches_user_and_profile(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify combined scope [user, profile] dispatches to both user scope and profile config."""
        mock_bash = MagicMock(
            return_value=subprocess.CompletedProcess([], 0, '', ''),
        )
        mock_run = MagicMock(
            return_value=subprocess.CompletedProcess([], 0, '', ''),
        )

        with (
            patch('platform.system', return_value='Linux'),
            patch.object(
                setup_environment, 'find_command',
                return_value='/usr/local/bin/claude',
            ),
            patch.object(setup_environment, 'run_bash_command', mock_bash),
            patch.object(setup_environment, 'run_command', mock_run),
        ):
            profile_mcp_path = e2e_isolated_home['claude_dir'] / 'mcp.json'
            _, profile_servers, stats = configure_all_mcp_servers(
                servers=golden_config.get('mcp-servers', []),
                profile_mcp_config_path=profile_mcp_path,
            )

        # Verify the combined-scope server was dispatched via claude mcp add
        # for the user scope (non-profile scopes use run_bash_command)
        bash_cmd = _find_mcp_add_call(
            mock_bash.call_args_list, 'e2e-combined-scope-server',
        )
        assert bash_cmd is not None, (
            'No mcp add command found for e2e-combined-scope-server '
            '(should be dispatched for user scope via run_bash_command)'
        )

        # Verify --scope user is used (not profile, which goes to JSON config)
        assert '--scope user' in bash_cmd, (
            f'Combined-scope server should use --scope user for the '
            f'non-profile scope dispatch, got: {bash_cmd}'
        )

        # Verify the server also appears in profile_servers (for JSON config)
        profile_server_names = [s['name'] for s in profile_servers]
        assert 'e2e-combined-scope-server' in profile_server_names, (
            'Combined-scope server should appear in profile_servers for JSON config'
        )

        # Verify stats reflect the combined scope
        assert stats['combined_count'] >= 1, (
            f'Expected at least 1 combined-scope server in stats, got: {stats}'
        )


class TestMCPHeaderEnvVarPlaceholder:
    """E2E tests: a ${VAR} header placeholder is preserved literally for runtime expansion.

    The setup script must NOT expand ${VAR} at install time. It single-quotes the header so
    `claude mcp add` stores the literal placeholder; Claude Code expands it from the
    environment when a session starts. These tests cover both the generated command string
    and -- on the real platform shell -- the value that actually reaches `claude mcp add`.
    """

    def test_http_header_env_var_placeholder_single_quoted_unix(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """The generated Unix bash command single-quotes a ${VAR} header (no setup-time expansion)."""
        mock_bash = MagicMock(
            return_value=subprocess.CompletedProcess([], 0, '', ''),
        )
        mock_run = MagicMock(
            return_value=subprocess.CompletedProcess([], 0, '', ''),
        )

        server = {
            'name': 'e2e-envheader-server',
            'scope': 'user',
            'transport': 'http',
            'url': 'https://api.example.com/mcp',
            'header': 'Authorization: Bearer ${E2E_YT_TOKEN}',
        }

        with (
            patch('platform.system', return_value='Linux'),
            patch.object(
                setup_environment, 'find_command',
                return_value='/usr/local/bin/claude',
            ),
            patch.object(setup_environment, 'run_bash_command', mock_bash),
            patch.object(setup_environment, 'run_command', mock_run),
        ):
            profile_mcp_path = e2e_isolated_home['claude_dir'] / 'mcp.json'
            configure_all_mcp_servers(
                servers=[server],
                profile_mcp_config_path=profile_mcp_path,
            )

        bash_cmd = _find_mcp_add_call(mock_bash.call_args_list, 'e2e-envheader-server')
        assert bash_cmd is not None, (
            'No mcp add command found for e2e-envheader-server in run_bash_command calls'
        )

        # The placeholder must be single-quoted (literal), never double-quoted (which would
        # let bash expand ${E2E_YT_TOKEN} at setup time instead of preserving it for Claude).
        assert "--header 'Authorization: Bearer ${E2E_YT_TOKEN}'" in bash_cmd, (
            f'Header must be single-quoted to preserve the placeholder, got: {bash_cmd}'
        )
        assert '--header "' not in bash_cmd, (
            f'Header must NOT be double-quoted (would expand ${{VAR}} at setup time), got: {bash_cmd}'
        )
        assert '${E2E_YT_TOKEN}' in bash_cmd, (
            'The literal ${VAR} placeholder must be present in the generated command'
        )

    @pytest.mark.skipif(_BASH_UNAVAILABLE, reason='bash/Git Bash not available on this host')
    def test_http_header_env_var_placeholder_survives_real_shell(
        self,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Real cross-OS: the literal ${VAR} placeholder reaches `claude mcp add` through the actual shell.

        Drives configure_mcp_server end-to-end through the real run_bash_command on whatever
        OS the test runs (native bash on Linux/macOS, Git Bash on Windows). A fake `claude`
        records the exact argv it receives. With the auth env var SET to a sentinel at setup
        time, the recorded --header must still be the literal ${VAR} placeholder -- proving the
        installer shell does not expand it (Claude Code expands it later, at session start).
        """
        # A fake `claude` that records the exact argv of every invocation, then succeeds.
        local_bin = e2e_isolated_home['local_bin']
        fake_claude = local_bin / 'claude'
        fake_claude.write_text(
            '#!/usr/bin/env bash\n'
            'for arg in "$@"; do printf "%s\\n" "$arg" >> "$CLAUDE_E2E_RECORD"; done\n'
            'printf "INVOCATION_END\\n" >> "$CLAUDE_E2E_RECORD"\n'
            'exit 0\n',
            encoding='utf-8',
        )
        fake_claude.chmod(0o755)

        record_path = e2e_isolated_home['home'] / 'mcp_add_record.txt'
        # Git Bash needs a POSIX-style path for the redirection target.
        if sys.platform == 'win32':
            record_env_value = setup_environment.convert_to_unix_path(str(record_path))
        else:
            record_env_value = str(record_path)
        monkeypatch.setenv('CLAUDE_E2E_RECORD', record_env_value)

        # Set the auth variable at SETUP time. If the installer wrongly expanded ${VAR}
        # (the old double-quote bug), this sentinel would leak into the recorded header.
        monkeypatch.setenv('E2E_YT_TOKEN', 'LEAKED_AT_SETUP')

        # Point find_command('claude') at the fake recorder, overriding the autouse mock
        # (which returns None). Other command lookups pass through.
        original_find = setup_environment.find_command

        def fake_find(cmd: str) -> str | None:
            if cmd == 'claude':
                return str(fake_claude)
            return original_find(cmd)

        monkeypatch.setattr(setup_environment, 'find_command', fake_find)

        server = {
            'name': 'e2e-envheader-server',
            'scope': 'user',
            'transport': 'http',
            'url': 'https://api.example.com/mcp',
            'header': 'Authorization: Bearer ${E2E_YT_TOKEN}',
        }

        # No platform.system / run_bash_command mocking: exercise the real OS shell.
        result = setup_environment.configure_mcp_server(server)
        assert result is True, (
            'configure_mcp_server should succeed with the fake claude recorder'
        )

        assert record_path.exists(), (
            f'Fake claude recorded nothing at {record_path}; the add command did not run'
        )
        recorded = record_path.read_text(encoding='utf-8').splitlines()

        # `claude mcp add ... --header <value>` -> --header and its value are separate argv
        # elements, so the value is the line immediately after the --header line.
        header_value = None
        for i, line in enumerate(recorded):
            if line == '--header' and i + 1 < len(recorded):
                header_value = recorded[i + 1]
                break

        assert header_value is not None, (
            f'No --header argument reached claude. Recorded argv: {recorded}'
        )
        assert header_value == 'Authorization: Bearer ${E2E_YT_TOKEN}', (
            'The real shell must pass the literal ${VAR} placeholder to claude, '
            f'got: {header_value!r}'
        )
        assert 'LEAKED_AT_SETUP' not in header_value, (
            'The setup-time value of E2E_YT_TOKEN must NOT leak into the stored header '
            '(it must be expanded by Claude Code at runtime, not by the installer shell)'
        )


class TestMCPProfileHeaderConfig:
    """E2E tests for profile-scoped MCP servers with header in JSON config."""

    def test_profile_http_server_with_header_in_json(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify profile-scoped HTTP server with header is correctly written to MCP JSON config."""
        mock_bash = MagicMock(
            return_value=subprocess.CompletedProcess([], 0, '', ''),
        )
        mock_run = MagicMock(
            return_value=subprocess.CompletedProcess([], 0, '', ''),
        )

        with (
            patch('platform.system', return_value='Linux'),
            patch.object(
                setup_environment, 'find_command',
                return_value='/usr/local/bin/claude',
            ),
            patch.object(setup_environment, 'run_bash_command', mock_bash),
            patch.object(setup_environment, 'run_command', mock_run),
        ):
            profile_mcp_path = e2e_isolated_home['claude_dir'] / 'mcp.json'
            _, profile_servers, _ = configure_all_mcp_servers(
                servers=golden_config.get('mcp-servers', []),
                profile_mcp_config_path=profile_mcp_path,
            )

        # Verify e2e-http-profile-server is in profile servers
        profile_names = [s['name'] for s in profile_servers]
        assert 'e2e-http-profile-server' in profile_names, (
            'e2e-http-profile-server should be in profile servers list'
        )

        # Verify the JSON file was created with correct header structure
        import json
        assert profile_mcp_path.exists(), (
            f'Profile MCP config file not created: {profile_mcp_path}'
        )
        data = json.loads(profile_mcp_path.read_text(encoding='utf-8'))
        assert 'mcpServers' in data
        assert 'e2e-http-profile-server' in data['mcpServers']

        server_config = data['mcpServers']['e2e-http-profile-server']
        assert server_config['type'] == 'http'
        assert server_config['url'] == 'http://localhost:3002/profile-api'

        # Header should be parsed into a dict
        assert 'headers' in server_config, (
            'Profile HTTP server should have headers dict in JSON config'
        )
        assert isinstance(server_config['headers'], dict)
        assert server_config['headers'].get('Authorization') == 'Bearer profile-token', (
            f"Expected 'Bearer profile-token', got {server_config['headers']}"
        )

    def test_combined_scope_server_in_profile_json(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify combined scope [user, profile] server is written to profile MCP JSON."""
        mock_bash = MagicMock(
            return_value=subprocess.CompletedProcess([], 0, '', ''),
        )
        mock_run = MagicMock(
            return_value=subprocess.CompletedProcess([], 0, '', ''),
        )

        with (
            patch('platform.system', return_value='Linux'),
            patch.object(
                setup_environment, 'find_command',
                return_value='/usr/local/bin/claude',
            ),
            patch.object(setup_environment, 'run_bash_command', mock_bash),
            patch.object(setup_environment, 'run_command', mock_run),
        ):
            profile_mcp_path = e2e_isolated_home['claude_dir'] / 'mcp.json'
            configure_all_mcp_servers(
                servers=golden_config.get('mcp-servers', []),
                profile_mcp_config_path=profile_mcp_path,
            )

        # Verify the MCP JSON file was created
        import json
        assert profile_mcp_path.exists(), (
            f'Profile MCP config file not created: {profile_mcp_path}'
        )
        data = json.loads(profile_mcp_path.read_text(encoding='utf-8'))
        assert 'mcpServers' in data

        # Verify the combined-scope server is present in the JSON config
        assert 'e2e-combined-scope-server' in data['mcpServers'], (
            'Combined-scope server should appear in profile MCP JSON config. '
            f'Found servers: {list(data["mcpServers"].keys())}'
        )

        # Verify its config is correct
        server_config = data['mcpServers']['e2e-combined-scope-server']
        assert server_config['type'] == 'http'
        assert server_config['url'] == 'http://localhost:3003/combined-api'
