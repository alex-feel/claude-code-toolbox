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

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

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
                setup_environment, 'find_command_robust',
                return_value='/usr/local/bin/claude',
            ),
            patch.object(setup_environment, 'run_bash_command', mock_bash),
            patch.object(setup_environment, 'run_command', mock_run),
        ):
            profile_mcp_path = e2e_isolated_home['claude_dir'] / 'test-mcp.json'
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
                setup_environment, 'find_command_robust',
                return_value=r'C:\Users\Test\AppData\Roaming\npm\claude.CMD',
            ),
            patch.object(setup_environment, 'run_bash_command', mock_bash),
            patch.object(setup_environment, 'run_command', mock_run),
            patch('pathlib.Path.exists', return_value=False),
        ):
            profile_mcp_path = e2e_isolated_home['claude_dir'] / 'test-mcp.json'
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
                setup_environment, 'find_command_robust',
                return_value='/usr/local/bin/claude',
            ),
            patch.object(setup_environment, 'run_bash_command', mock_bash),
            patch.object(setup_environment, 'run_command', mock_run),
        ):
            profile_mcp_path = e2e_isolated_home['claude_dir'] / 'test-mcp.json'
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
                setup_environment, 'find_command_robust',
                return_value='/usr/local/bin/claude',
            ),
            patch.object(setup_environment, 'run_bash_command', mock_bash),
            patch.object(setup_environment, 'run_command', mock_run),
        ):
            profile_mcp_path = e2e_isolated_home['claude_dir'] / 'test-mcp.json'
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


class TestMCPHeaderEnvVarExpansion:
    """E2E tests for header environment variable expansion using double quotes."""

    def test_http_header_with_env_var_uses_double_quotes_unix(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify Unix HTTP transport wraps header in double quotes for ${VAR} expansion.

        Single quotes (from shlex.quote) prevent bash variable expansion.
        Header values containing ${VAR} patterns must use double quotes so
        bash resolves environment variables at runtime.
        """
        mock_bash = MagicMock(
            return_value=subprocess.CompletedProcess([], 0, '', ''),
        )
        mock_run = MagicMock(
            return_value=subprocess.CompletedProcess([], 0, '', ''),
        )

        with (
            patch('platform.system', return_value='Linux'),
            patch.object(
                setup_environment, 'find_command_robust',
                return_value='/usr/local/bin/claude',
            ),
            patch.object(setup_environment, 'run_bash_command', mock_bash),
            patch.object(setup_environment, 'run_command', mock_run),
        ):
            profile_mcp_path = e2e_isolated_home['claude_dir'] / 'test-mcp.json'
            configure_all_mcp_servers(
                servers=golden_config.get('mcp-servers', []),
                profile_mcp_config_path=profile_mcp_path,
            )

        # e2e-http-server has header "X-API-Key: test-key"
        bash_cmd = _find_mcp_add_call(mock_bash.call_args_list, 'e2e-http-server')
        assert bash_cmd is not None, (
            'No mcp add command found for e2e-http-server in run_bash_command calls'
        )

        # Header must be wrapped in double quotes (not single quotes)
        assert '--header "' in bash_cmd, (
            f'Header must use double quotes for ${{VAR}} expansion, got: {bash_cmd}'
        )
        # Verify single quotes are NOT used around the header value
        assert "--header '" not in bash_cmd, (
            'Header must NOT use single quotes (blocks ${VAR} expansion)'
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
                setup_environment, 'find_command_robust',
                return_value='/usr/local/bin/claude',
            ),
            patch.object(setup_environment, 'run_bash_command', mock_bash),
            patch.object(setup_environment, 'run_command', mock_run),
        ):
            profile_mcp_path = e2e_isolated_home['claude_dir'] / 'test-mcp.json'
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
