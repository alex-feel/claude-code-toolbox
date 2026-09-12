"""E2E tests for the strict-mode MCP scope warning on the golden configuration.

The golden configuration mixes profile-scoped servers with servers registered
only at user, project and local scope. Because the profile servers make the
launcher start Claude Code with --strict-mcp-config, the non-profile-only
servers are reachable from a bare ``claude`` session but not from the isolated
commands, which the run reports per server.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from scripts import setup_environment
from scripts.setup_environment import configure_all_mcp_servers


def _warning_lines(output: str) -> list[str]:
    """Return the strict-mode warning lines from captured output."""
    return [line for line in output.splitlines() if 'will not load' in line]


class TestGoldenConfigStrictScopeWarning:
    """The golden config's scope mix drives the warning end to end."""

    def test_golden_isolated_run_names_every_hidden_server(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Every non-profile-only golden server is reported, and no other one is."""
        artifact_base_dir = e2e_isolated_home['claude_dir'] / golden_config['command-names'][0]
        artifact_base_dir.mkdir(parents=True, exist_ok=True)

        _, profile_servers, stats = configure_all_mcp_servers(
            servers=golden_config['mcp-servers'],
            profile_mcp_config_path=artifact_base_dir / 'mcp.json',
            artifact_base_dir=artifact_base_dir,
            command_names=golden_config['command-names'],
        )

        # e2e-http-profile-server, e2e-stdio-server and e2e-combined-scope-server
        assert len(profile_servers) == 3
        assert stats['strict_hidden_count'] == 3

        warnings = _warning_lines(capsys.readouterr().out)
        assert len(warnings) == 3
        joined = '\n'.join(warnings)
        assert 'e2e-http-server (scope: user)' in joined
        assert 'e2e-sse-server (scope: project)' in joined
        assert 'e2e-npx-server (scope: local)' in joined
        # A combined scope keeps the server visible to the isolated commands
        assert 'e2e-combined-scope-server' not in joined

    def test_golden_warning_names_all_commands_and_the_fix(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The warning tells the user which sessions are affected and how to fix it."""
        artifact_base_dir = e2e_isolated_home['claude_dir'] / golden_config['command-names'][0]
        artifact_base_dir.mkdir(parents=True, exist_ok=True)

        configure_all_mcp_servers(
            servers=golden_config['mcp-servers'],
            profile_mcp_config_path=artifact_base_dir / 'mcp.json',
            artifact_base_dir=artifact_base_dir,
            command_names=golden_config['command-names'],
        )

        joined = '\n'.join(_warning_lines(capsys.readouterr().out))
        assert 'e2e-test-cmd, e2e-test-alias sessions' in joined
        assert '--strict-mcp-config' in joined
        assert 'scope: [user, profile]' in joined
        assert 'scope: [project, profile]' in joined
        assert 'scope: [local, profile]' in joined

    def test_golden_non_isolated_variant_stays_silent(
        self,
        e2e_isolated_home: dict[str, Path],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The no-command-names golden variant has no launcher, so nothing is hidden."""
        del e2e_isolated_home
        config_path = Path(__file__).parent / 'golden_config_no_command_names.yaml'
        with config_path.open('r', encoding='utf-8') as handle:
            config: dict[str, Any] = yaml.safe_load(handle)

        _, profile_servers, stats = configure_all_mcp_servers(
            servers=config['mcp-servers'],
            profile_mcp_config_path=None,
            command_names=None,
        )

        assert profile_servers == []
        assert stats['strict_hidden_count'] == 0
        assert _warning_lines(capsys.readouterr().out) == []


class TestMainReportsHiddenServersInSummary:
    """A full run threads the count into the completion summary."""

    def test_summary_counts_hidden_servers(
        self,
        e2e_isolated_home: dict[str, Path],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The isolated run reports how many servers its sessions will not load."""
        del e2e_isolated_home
        config: dict[str, Any] = {
            'name': 'Strict Scope Summary',
            'command-names': ['claude-strict'],
            'mcp-servers': [
                {'name': 'profile-server', 'scope': 'profile',
                 'transport': 'http', 'url': 'http://localhost:3000/profile'},
                {'name': 'user-server', 'scope': 'user',
                 'transport': 'http', 'url': 'http://localhost:3001/user'},
            ],
        }

        with (
            patch('scripts.setup_environment.load_config_from_source',
                  return_value=(config, 'test.yaml')),
            patch('scripts.setup_environment.validate_all_config_files',
                  return_value=(True, [])),
            patch('scripts.setup_environment.install_dependencies', return_value=[]),
            patch('scripts.setup_environment.is_admin', return_value=True),
            patch('scripts.setup_environment.register_global_command', return_value=True),
            patch('scripts.setup_environment.find_command', return_value='claude'),
            patch('scripts.setup_environment.run_command',
                  return_value=subprocess.CompletedProcess([], 0, '', '')),
            patch('sys.argv', ['setup_environment.py', 'test', '--yes', '--skip-install']),
            patch('sys.exit') as mock_exit,
        ):
            setup_environment.main()
            mock_exit.assert_not_called()

        combined = ''.join(capsys.readouterr())
        assert 'MCP servers not loaded in isolated sessions (--strict-mcp-config): 1' in combined
        assert 'user-server (scope: user)' in combined
