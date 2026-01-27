"""E2E tests for tilde path expansion verification.

These tests verify that all paths containing tildes are properly expanded
across all configuration files and launcher scripts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.setup_environment import configure_all_mcp_servers
from scripts.setup_environment import create_additional_settings
from scripts.setup_environment import create_mcp_config_file
from scripts.setup_environment import write_user_settings
from tests.e2e.validators import validate_all_paths_expanded
from tests.e2e.validators import validate_path_expanded


class TestTildeExpansion:
    """Test tilde path expansion across all configuration files."""

    def test_mcp_server_paths_expanded(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify MCP server paths have no unexpanded tildes.

        Checks that command, args, and env fields in MCP server
        configurations have properly expanded paths.
        """
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']
        mcp_path = claude_dir / f'{cmd}-mcp.json'

        # Configure MCP servers
        _, profile_servers, _ = configure_all_mcp_servers(
            servers=golden_config.get('mcp-servers', []),
            profile_mcp_config_path=mcp_path,
        )

        # Create the MCP config file
        create_mcp_config_file(
            servers=profile_servers,
            config_path=mcp_path,
        )

        # Load and validate
        if not mcp_path.exists():
            # No MCP servers configured, skip
            return

        data = json.loads(mcp_path.read_text())
        servers = data.get('mcpServers', {})

        errors: list[str] = []
        for name, config in servers.items():
            # Check command
            if 'command' in config:
                errors.extend(validate_path_expanded(config['command'], f'server {name} command'))

            # Check args
            for idx, arg in enumerate(config.get('args', [])):
                if isinstance(arg, str):
                    errors.extend(validate_path_expanded(arg, f'server {name} args[{idx}]'))

            # Check env
            env = config.get('env', {})
            if isinstance(env, dict):
                for env_key, env_value in env.items():
                    if isinstance(env_value, str):
                        errors.extend(
                            validate_path_expanded(env_value, f'server {name} env[{env_key}]'),
                        )

        assert not errors, 'MCP server paths contain unexpanded tildes:\n' + '\n'.join(errors)

    def test_additional_settings_paths_expanded(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify additional-settings.json paths have no unexpanded tildes.

        Checks that any path-like values in additional-settings.json
        are properly expanded.
        """
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        # Create additional settings
        create_additional_settings(
            hooks=golden_config.get('hooks', {}),
            claude_user_dir=claude_dir,
            command_name=cmd,
            model=golden_config.get('model'),
            permissions=golden_config.get('permissions'),
            env=golden_config.get('env-variables'),
            include_co_authored_by=None,
            always_thinking_enabled=golden_config.get('always-thinking-enabled'),
            company_announcements=golden_config.get('company-announcements'),
            attribution=golden_config.get('attribution'),
            status_line=golden_config.get('status-line'),
        )

        # File is written to claude_user_dir (= claude_dir)
        settings_path = claude_dir / f'{cmd}-additional-settings.json'

        data = json.loads(settings_path.read_text())

        # Check known path-containing fields
        # Note: 'env' is excluded because environment variables may intentionally
        # contain tildes that get expanded at runtime by the shell
        path_keys = ['statusLine', 'hooks']
        errors = validate_all_paths_expanded(data, path_keys)

        assert not errors, 'additional-settings.json paths contain unexpanded tildes:\n' + '\n'.join(
            errors,
        )

    def test_user_settings_paths_expanded(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify settings.json paths have no unexpanded tildes.

        Checks tilde expansion in user-settings that may contain paths
        like apiKeyHelper and awsCredentialExport.
        """
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']
        user_settings = golden_config.get('user-settings', {})

        if not user_settings:
            # No user settings to test
            return

        # Write user settings
        write_user_settings(user_settings, claude_dir)
        settings_path = claude_dir / 'settings.json'

        data = json.loads(settings_path.read_text())

        # Check known tilde-expansion keys
        tilde_keys = ['apiKeyHelper', 'awsCredentialExport']
        errors: list[str] = []

        for key in tilde_keys:
            if key in data and isinstance(data[key], str):
                errors.extend(validate_path_expanded(data[key], f'settings.json {key}'))

        assert not errors, 'settings.json paths contain unexpanded tildes:\n' + '\n'.join(errors)

    def test_hooks_command_paths_expanded(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify hook command paths have no unexpanded tildes.

        Checks that hooks.events[].command paths in additional-settings
        are properly expanded.
        """
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        hooks_config = golden_config.get('hooks', {})
        if not hooks_config.get('events'):
            # No hooks to test
            return

        # Create additional settings with hooks
        create_additional_settings(
            hooks=hooks_config,
            claude_user_dir=claude_dir,
            command_name=cmd,
            model=None,
            permissions=None,
            env=None,
            include_co_authored_by=None,
            always_thinking_enabled=None,
            company_announcements=None,
            attribution=None,
            status_line=None,
        )

        # File is written to claude_user_dir (= claude_dir)
        settings_path = claude_dir / f'{cmd}-additional-settings.json'

        data = json.loads(settings_path.read_text())
        hooks = data.get('hooks', {})

        errors: list[str] = []
        for event_name, event_hooks in hooks.items():
            if not isinstance(event_hooks, list):
                continue
            for idx, hook_group in enumerate(event_hooks):
                inner_hooks = hook_group.get('hooks', [])
                for hook_idx, hook in enumerate(inner_hooks):
                    if 'command' in hook and isinstance(hook['command'], str):
                        errors.extend(
                            validate_path_expanded(
                                hook['command'],
                                f'hooks[{event_name}][{idx}].hooks[{hook_idx}].command',
                            ),
                        )

        assert not errors, 'Hook command paths contain unexpanded tildes:\n' + '\n'.join(errors)

    def test_status_line_command_expanded(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify statusLine command path has no unexpanded tilde.

        The statusLine.command field may contain a path to a status script.
        """
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        status_line_config = golden_config.get('status-line')
        if not status_line_config:
            # No status line to test
            return

        # Create additional settings with status line
        create_additional_settings(
            hooks={},
            claude_user_dir=claude_dir,
            command_name=cmd,
            model=None,
            permissions=None,
            env=None,
            include_co_authored_by=None,
            always_thinking_enabled=None,
            company_announcements=None,
            attribution=None,
            status_line=status_line_config,
        )

        # File is written to claude_user_dir (= claude_dir)
        settings_path = claude_dir / f'{cmd}-additional-settings.json'

        data = json.loads(settings_path.read_text())
        status_line = data.get('statusLine', {})

        errors: list[str] = []
        if 'command' in status_line and isinstance(status_line['command'], str):
            errors.extend(
                validate_path_expanded(status_line['command'], 'statusLine.command'),
            )

        assert not errors, 'statusLine.command contains unexpanded tilde:\n' + '\n'.join(errors)
