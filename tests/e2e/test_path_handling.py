"""E2E tests for tilde path expansion verification.

These tests verify that all paths containing tildes are properly expanded
across all configuration files and launcher scripts.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts import setup_environment
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

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-specific tilde expansion')
    def test_user_settings_paths_expanded_on_windows(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify settings.json paths have no unexpanded tildes on Windows.

        On Windows, tilde-expansion keys (apiKeyHelper, awsCredentialExport)
        should have tildes fully expanded to absolute paths.
        """
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']
        user_settings = golden_config.get('user-settings', {})

        if not user_settings:
            return

        write_user_settings(user_settings, claude_dir)
        settings_path = claude_dir / 'settings.json'

        data = json.loads(settings_path.read_text())

        tilde_keys = ['apiKeyHelper', 'awsCredentialExport']
        errors: list[str] = []

        for key in tilde_keys:
            if key in data and isinstance(data[key], str):
                errors.extend(validate_path_expanded(data[key], f'settings.json {key}'))

        assert not errors, 'settings.json paths contain unexpanded tildes:\n' + '\n'.join(errors)

    @pytest.mark.skipif(sys.platform == 'win32', reason='Unix-specific tilde preservation')
    def test_user_settings_paths_preserved_on_unix(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify settings.json tilde paths are preserved on Unix/WSL.

        On non-Windows platforms, tilde-expansion keys (apiKeyHelper,
        awsCredentialExport) should preserve tildes because Claude Code
        resolves ~ to the correct home directory at runtime.
        """
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']
        user_settings = golden_config.get('user-settings', {})

        if not user_settings:
            return

        write_user_settings(user_settings, claude_dir)
        settings_path = claude_dir / 'settings.json'

        data = json.loads(settings_path.read_text())

        tilde_keys = ['apiKeyHelper', 'awsCredentialExport']
        errors: list[str] = []

        for key in tilde_keys:
            if key not in user_settings:
                continue
            original_value = user_settings[key]
            actual_value = data.get(key)
            if actual_value is None:
                errors.append(f'settings.json {key}: missing (expected preserved value)')
            elif actual_value != original_value:
                errors.append(
                    f'settings.json {key}: expected tilde preserved '
                    f'{original_value!r}, got {actual_value!r}',
                )

        assert not errors, (
            'settings.json tilde paths should be preserved on Unix:\n' + '\n'.join(errors)
        )

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

    def test_expand_tilde_keys_preserves_on_linux(self) -> None:
        """Verify _expand_tilde_keys_in_settings preserves tildes on Linux/macOS.

        The function should return settings UNCHANGED on non-Windows platforms,
        because Claude Code resolves ~ at runtime on Unix.
        """
        settings = {
            'apiKeyHelper': 'uv run --no-project --python 3.12 ~/.claude/scripts/helper.py',
            'awsCredentialExport': '~/.aws/credentials',
            'language': 'english',
            'theme': 'dark',
        }

        with patch('sys.platform', 'linux'):
            result = setup_environment._expand_tilde_keys_in_settings(settings)

        # Tilde keys must be preserved exactly
        assert result['apiKeyHelper'] == settings['apiKeyHelper'], (
            f'apiKeyHelper tilde should be preserved on Linux: {result["apiKeyHelper"]}'
        )
        assert result['awsCredentialExport'] == settings['awsCredentialExport'], (
            f'awsCredentialExport tilde should be preserved on Linux: {result["awsCredentialExport"]}'
        )
        # Non-tilde keys must also be unchanged
        assert result['language'] == 'english'
        assert result['theme'] == 'dark'

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-specific tilde expansion')
    def test_expand_tilde_keys_expands_on_windows(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Verify _expand_tilde_keys_in_settings expands tildes on Windows.

        On Windows, Claude Code does NOT resolve ~ at runtime, so setup must
        expand tildes to absolute paths.
        """
        settings = {
            'apiKeyHelper': 'uv run --no-project --python 3.12 ~/.claude/scripts/helper.py',
            'language': 'english',
        }

        # sys.platform is already 'win32' on Windows, no patch needed
        result = setup_environment._expand_tilde_keys_in_settings(settings)

        # apiKeyHelper must NOT contain tilde
        assert '~' not in result['apiKeyHelper'], (
            f'apiKeyHelper should have tilde expanded on Windows: {result["apiKeyHelper"]}'
        )
        # Must contain the home directory path
        home_str = str(e2e_isolated_home['home'])
        assert (
            home_str in result['apiKeyHelper']
            or home_str.replace('\\', '/') in result['apiKeyHelper']
        ), (
            f'apiKeyHelper should contain home dir ({home_str}): {result["apiKeyHelper"]}'
        )
        # Non-tilde keys must be unchanged
        assert result['language'] == 'english'

    @pytest.mark.skipif(sys.platform == 'win32', reason='Unix-specific backslash check')
    def test_settings_json_no_backslashes_on_linux(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify settings.json does not contain Windows backslash paths on Linux.

        On Linux/WSL, settings.json values for tilde-expansion keys must not
        contain Windows-style backslash paths or drive letters.
        """
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']
        user_settings = golden_config.get('user-settings', {})

        if not user_settings:
            return

        write_user_settings(user_settings, claude_dir)
        settings_path = claude_dir / 'settings.json'

        data = json.loads(settings_path.read_text())

        tilde_keys = {'apiKeyHelper', 'awsCredentialExport'}
        errors: list[str] = []

        for key in tilde_keys:
            if key not in data or not isinstance(data[key], str):
                continue
            value = data[key]
            # Check for Windows-style backslash paths
            if '\\' in value:
                errors.append(
                    f'settings.json {key} contains backslash '
                    f'(Windows path contamination): {value}',
                )
            # Check for drive letters (C:, D:, etc.)
            if re.search(r'[A-Za-z]:[/\\]', value):
                errors.append(
                    f'settings.json {key} contains Windows drive letter on Linux: {value}',
                )

        assert not errors, (
            'settings.json contains Windows path contamination on Linux:\n'
            + '\n'.join(errors)
        )

    @pytest.mark.skipif(sys.platform == 'win32', reason='Unix-specific tilde preservation')
    def test_command_prefix_preserved_with_tilde(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Verify command-prefix strings with tildes are preserved entirely on Linux.

        The apiKeyHelper value containing a command prefix before a tilde path
        must be preserved EXACTLY as-is on Linux/macOS.
        """
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']

        original_value = (
            'uv run --no-project --python 3.12 ~/.claude/scripts/api-key-helper.py'
        )
        user_settings = {'apiKeyHelper': original_value, 'language': 'english'}

        write_user_settings(user_settings, claude_dir)
        settings_path = claude_dir / 'settings.json'

        data = json.loads(settings_path.read_text())

        assert data.get('apiKeyHelper') == original_value, (
            f'apiKeyHelper should be preserved exactly on Unix: '
            f'expected {original_value!r}, got {data.get("apiKeyHelper")!r}'
        )

    @pytest.mark.skipif(sys.platform == 'win32', reason='Linux-specific WSL test')
    def test_wsl_home_not_contaminating_linux_paths(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Verify Windows USERPROFILE does not contaminate paths on Linux/WSL.

        In WSL, USERPROFILE may be set to a Windows path. The setup must use
        the Linux HOME, not USERPROFILE, when processing paths on non-Windows.
        Since tildes are preserved on Linux, there should be NO path expansion
        at all, preventing any HOME contamination.
        """
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']

        original_value = (
            'uv run --no-project --python 3.12 ~/.claude/scripts/helper.py'
        )
        user_settings = {'apiKeyHelper': original_value}

        write_user_settings(user_settings, claude_dir)
        settings_path = claude_dir / 'settings.json'

        data = json.loads(settings_path.read_text())

        value = data.get('apiKeyHelper', '')
        # Must NOT contain any absolute path (should be preserved tilde)
        assert value == original_value, (
            f'apiKeyHelper should preserve tilde on Linux (no HOME expansion): '
            f'expected {original_value!r}, got {value!r}'
        )
        # Extra safety: must NOT contain USERPROFILE value
        userprofile = os.environ.get('USERPROFILE', '')
        if userprofile:
            assert userprofile not in value, (
                f'apiKeyHelper contains USERPROFILE ({userprofile}) on Linux: {value}'
            )
