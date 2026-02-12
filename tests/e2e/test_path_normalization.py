"""E2E tests for path normalization and separator consistency.

These tests verify that paths written to output files have correct format:

1. Paths that go through normalize_tilde_path() (e.g., apiKeyHelper in
   settings.json) should have platform-consistent separators after the
   os.path.normpath fix (backslashes on Windows, forward slashes on Unix).

2. Hook and status-line command strings in additional-settings.json use
   POSIX-style paths (forward slashes) by design via Path.as_posix(),
   which avoids JSON backslash escaping issues. These tests verify that
   POSIX consistency is maintained.

3. MCP config paths should have consistent separators.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.setup_environment import configure_all_mcp_servers
from scripts.setup_environment import create_additional_settings
from scripts.setup_environment import create_mcp_config_file
from scripts.setup_environment import write_user_settings
from tests.e2e.validators import validate_path_separator_consistency


def _extract_paths_from_command(command_str: str) -> list[str]:
    """Extract filesystem path tokens from a compound command string.

    Hook commands look like:
        'uv run --no-project --python 3.12 C:/path/to/file.py C:/path/to/config.yaml'
        'node C:/path/to/hook.js'

    This helper splits on spaces and returns tokens that look like paths
    (contain '/' or '\\' and are not flags like '--no-project').

    Args:
        command_str: The full command string

    Returns:
        List of path-like tokens extracted from the command
    """
    paths: list[str] = []
    for token in command_str.split():
        # Skip flags, plain commands, and version numbers
        if token.startswith(('-', '--')):
            continue
        # A path-like token contains separators and is not just a word
        if '/' in token or '\\' in token:
            paths.append(token)
    return paths


class TestPathSeparatorConsistency:
    """Test path separator consistency across all output files."""

    def test_user_settings_path_separators(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify settings.json paths have consistent separators.

        Paths in settings.json (e.g., apiKeyHelper) go through
        normalize_tilde_path() which applies os.path.normpath().
        On Windows these should be all backslashes, on Unix all forward slashes.
        """
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']
        user_settings = golden_config.get('user-settings', {})

        if not user_settings:
            return

        # Write user settings (this triggers tilde expansion + normpath)
        write_user_settings(user_settings, claude_dir)
        settings_path = claude_dir / 'settings.json'

        data = json.loads(settings_path.read_text())

        errors: list[str] = []
        # Check known path-containing keys
        path_keys = ['apiKeyHelper', 'awsCredentialExport']
        for key in path_keys:
            if key in data and isinstance(data[key], str):
                errors.extend(
                    validate_path_separator_consistency(
                        data[key],
                        f'settings.json {key}',
                    ),
                )

        assert not errors, (
            'settings.json paths have inconsistent separators:\n' + '\n'.join(errors)
        )

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-specific tilde expansion')
    def test_user_settings_apikey_path_normalized_on_windows(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify apiKeyHelper tilde path is fully expanded and normalized on Windows.

        The golden config contains apiKeyHelper: "~/.claude/scripts/api-key-helper.py"
        On Windows, after write_user_settings(), this should be expanded to an absolute
        path with platform-consistent separators and no tilde.
        """
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']
        home = paths['home']
        user_settings = golden_config.get('user-settings', {})

        if 'apiKeyHelper' not in user_settings:
            return

        write_user_settings(user_settings, claude_dir)
        settings_path = claude_dir / 'settings.json'

        data = json.loads(settings_path.read_text())
        api_key_helper = data.get('apiKeyHelper', '')

        errors: list[str] = []

        # Must not contain unexpanded tilde
        if '~' in api_key_helper:
            errors.append(f'apiKeyHelper contains unexpanded tilde: {api_key_helper}')

        # Must contain the home directory path
        home_str = str(home)
        if home_str not in api_key_helper and home_str.replace('\\', '/') not in api_key_helper:
            errors.append(
                f'apiKeyHelper does not contain home directory ({home_str}): {api_key_helper}',
            )

        # Must have consistent separators
        errors.extend(
            validate_path_separator_consistency(
                api_key_helper,
                'settings.json apiKeyHelper',
            ),
        )

        assert not errors, (
            'apiKeyHelper path normalization issues:\n' + '\n'.join(errors)
        )

    @pytest.mark.skipif(sys.platform == 'win32', reason='Unix-specific tilde preservation')
    def test_user_settings_apikey_path_preserved_on_unix(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify apiKeyHelper tilde path is preserved on Unix/Linux/WSL.

        On non-Windows platforms, tildes are preserved in settings.json because
        Claude Code resolves ~ to the correct home directory at runtime.
        """
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']
        user_settings = golden_config.get('user-settings', {})

        if 'apiKeyHelper' not in user_settings:
            return

        write_user_settings(user_settings, claude_dir)
        settings_path = claude_dir / 'settings.json'

        data = json.loads(settings_path.read_text())
        api_key_helper = data.get('apiKeyHelper', '')

        errors: list[str] = []

        # On Unix, the tilde must be preserved (value should be unchanged)
        original_value = user_settings['apiKeyHelper']
        if api_key_helper != original_value:
            errors.append(
                f'apiKeyHelper should be preserved on Unix: '
                f'expected {original_value!r}, got {api_key_helper!r}',
            )

        assert not errors, (
            'apiKeyHelper tilde preservation issues:\n' + '\n'.join(errors)
        )

    def test_mcp_config_path_separators(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify MCP config paths have consistent separators.

        Configures MCP servers with the golden config and validates that
        command, args, and env path values have platform-consistent separators.
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

        if not mcp_path.exists():
            # No profile MCP servers configured, skip
            return

        data = json.loads(mcp_path.read_text())
        servers = data.get('mcpServers', {})

        errors: list[str] = []
        for name, config in servers.items():
            # Check command path
            if 'command' in config and isinstance(config['command'], str):
                cmd_val = config['command']
                # Only check paths that look like filesystem paths
                # (contain separators or drive letters, skip plain commands like "python")
                if '/' in cmd_val or '\\' in cmd_val or ':' in cmd_val:
                    errors.extend(
                        validate_path_separator_consistency(
                            cmd_val,
                            f'mcp server {name} command',
                        ),
                    )

            # Check args
            for idx, arg in enumerate(config.get('args', [])):
                if isinstance(arg, str) and ('/' in arg or '\\' in arg):
                    errors.extend(
                        validate_path_separator_consistency(
                            arg,
                            f'mcp server {name} args[{idx}]',
                        ),
                    )

            # Check env values
            env = config.get('env', {})
            if isinstance(env, dict):
                for env_key, env_value in env.items():
                    if isinstance(env_value, str) and ('/' in env_value or '\\' in env_value):
                        errors.extend(
                            validate_path_separator_consistency(
                                env_value,
                                f'mcp server {name} env[{env_key}]',
                            ),
                        )

        assert not errors, (
            'MCP config paths have inconsistent separators:\n' + '\n'.join(errors)
        )

    def test_hooks_use_posix_paths(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify hook command paths use POSIX-style forward slashes.

        Hook commands in additional-settings.json are built using
        Path.as_posix() by design to avoid JSON backslash escaping issues.
        All path tokens within hook commands should use forward slashes
        consistently, even on Windows.
        """
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        hooks_config = golden_config.get('hooks', {})
        if not hooks_config.get('events'):
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
                    if 'command' not in hook or not isinstance(hook['command'], str):
                        continue
                    command_str = hook['command']

                    # Extract path tokens from the compound command
                    path_tokens = _extract_paths_from_command(command_str)
                    # Hook paths should use POSIX-style (forward slashes)
                    # because create_additional_settings uses .as_posix()
                    errors.extend(
                        f'hooks[{event_name}][{idx}].hooks[{hook_idx}].command '
                        f'contains backslash in path token: {path_token}'
                        for path_token in path_tokens
                        if '\\' in path_token
                    )

        assert not errors, (
            'Hook command paths should use POSIX-style forward slashes:\n'
            + '\n'.join(errors)
        )

    def test_status_line_uses_posix_paths(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify statusLine command path uses POSIX-style forward slashes.

        Status line commands in additional-settings.json are built using
        Path.as_posix() by design, same as hooks.
        """
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        status_line_config = golden_config.get('status-line')
        if not status_line_config:
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

        settings_path = claude_dir / f'{cmd}-additional-settings.json'
        data = json.loads(settings_path.read_text())
        status_line = data.get('statusLine', {})

        errors: list[str] = []
        if 'command' in status_line and isinstance(status_line['command'], str):
            command_str = status_line['command']
            path_tokens = _extract_paths_from_command(command_str)
            # Status line paths should use POSIX-style (forward slashes)
            errors.extend(
                f'statusLine.command contains backslash in path token: {path_token}'
                for path_token in path_tokens
                if '\\' in path_token
            )

        assert not errors, (
            'statusLine.command should use POSIX-style forward slashes:\n'
            + '\n'.join(errors)
        )

    def test_additional_settings_all_paths_consistent(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Comprehensive check: all path tokens in additional-settings are consistent.

        Hook/status-line paths use POSIX-style (forward slashes) by design.
        This test creates full additional settings and verifies each path token
        within compound command strings uses forward slashes consistently.
        """
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        # Create full additional settings
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

        settings_path = claude_dir / f'{cmd}-additional-settings.json'
        data = json.loads(settings_path.read_text())

        errors: list[str] = []

        def check_command_paths(obj: object, key_path: str) -> None:
            """Recursively find 'command' keys and verify path tokens use POSIX style."""
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k == 'command' and isinstance(v, str):
                        path_tokens = _extract_paths_from_command(v)
                        errors.extend(
                            f'{key_path}.{k} contains backslash in '
                            f'path token: {path_token}'
                            for path_token in path_tokens
                            if '\\' in path_token
                        )
                    else:
                        check_command_paths(v, f'{key_path}.{k}')
            elif isinstance(obj, list):
                for idx, item in enumerate(obj):
                    check_command_paths(item, f'{key_path}[{idx}]')

        # Check hooks and statusLine sections
        for section in ['hooks', 'statusLine']:
            if section in data:
                check_command_paths(data[section], section)

        platform_name = 'Windows' if sys.platform == 'win32' else 'Unix'
        assert not errors, (
            f'Path consistency issues in additional-settings on {platform_name}:\n'
            + '\n'.join(errors)
        )
