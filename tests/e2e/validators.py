"""Composable validation functions for E2E tests.

All validators return list[str] of errors (empty = success).
This pattern allows collecting ALL validation failures, not just the first.

Design principles:
- Each validator is small and focused on one concern
- Validators are composable - combine multiple for comprehensive checks
- Platform-specific logic uses sys.platform checks
- All errors are descriptive with context (file path, field name, expected vs actual)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def validate_json_file(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    """Load and validate JSON file.

    Utility function that loads a JSON file and returns parsed data with any errors.
    Use this before content validation to ensure file exists and is valid JSON.

    Args:
        path: Path to the JSON file to load

    Returns:
        Tuple of (parsed_data, errors).
        If file doesn't exist or JSON is invalid, data is None and errors contains description.
        If successful, data contains parsed JSON and errors is empty list.

    Example:
        data, errors = validate_json_file(path)
        if errors:
            return errors  # File-level errors, skip content validation
        # Continue with content validation using data
    """
    if not path.exists():
        return None, [f'File not found: {path}']

    try:
        content = path.read_text(encoding='utf-8')
        data = json.loads(content)
        return data, []
    except json.JSONDecodeError as e:
        return None, [f'Invalid JSON in {path}: {e}']
    except OSError as e:
        return None, [f'Failed to read {path}: {e}']


def validate_settings_json(path: Path, config: dict[str, Any]) -> list[str]:
    """Validate settings.json against expected values from config.

    Validates that settings.json (user settings file at ~/.claude/settings.json)
    contains expected values from the 'user-settings' section of the golden config.

    Validates:
    - File exists and is valid JSON
    - Values from config['user-settings'] are present

    Note: settings.json uses deep merge, so this validates that expected keys
    are present, not that the file contains ONLY these keys.

    Args:
        path: Path to settings.json file
        config: Golden configuration dictionary

    Returns:
        List of error strings (empty if validation passes)
    """
    errors: list[str] = []

    data, file_errors = validate_json_file(path)
    if file_errors:
        return file_errors

    assert data is not None  # For type checker

    # Validate user-settings are merged correctly
    user_settings = config.get('user-settings', {})
    for key, expected_value in user_settings.items():
        actual_value = data.get(key)
        if actual_value != expected_value:
            errors.append(
                f"settings.json key '{key}': expected {expected_value!r}, got {actual_value!r}",
            )

    # Check for unexpanded tildes in known tilde-expansion keys
    tilde_keys = {'apiKeyHelper', 'awsCredentialExport'}
    errors.extend(
        f"settings.json key '{key}' contains unexpanded tilde: {data[key]}"
        for key in tilde_keys
        if key in data and isinstance(data[key], str) and '~' in data[key]
    )

    return errors


def validate_mcp_json(path: Path, config: dict[str, Any]) -> list[str]:
    """Validate MCP configuration JSON structure and content.

    Validates the {cmd}-mcp.json file that contains profile-scoped MCP servers.
    This file uses the format: {"mcpServers": {"server-name": {...}, ...}}

    Validates:
    - File exists and is valid JSON
    - 'mcpServers' key exists
    - Expected profile-scoped servers are present
    - No unexpanded tildes in command/args/url fields
    - Windows: npx commands are wrapped with cmd /c
    - Server configs have required fields based on transport type

    Args:
        path: Path to the MCP config JSON file
        config: Golden configuration dictionary

    Returns:
        List of error strings (empty if validation passes)
    """
    errors: list[str] = []

    data, file_errors = validate_json_file(path)
    if file_errors:
        return file_errors

    assert data is not None  # For type checker

    # Validate mcpServers key exists
    if 'mcpServers' not in data:
        errors.append(f"Missing 'mcpServers' key in {path.name}")
        return errors

    servers = data['mcpServers']
    if not isinstance(servers, dict):
        errors.append(f"'mcpServers' must be a dict, got {type(servers).__name__}")
        return errors

    # Get profile-scoped servers from config (only profile-scoped go to {cmd}-mcp.json)
    expected_profile_servers: set[str] = set()
    for server in config.get('mcp-servers', []):
        scope = server.get('scope', 'user')
        # Handle both string and list scope formats
        if isinstance(scope, str):
            scopes = [scope]
        elif isinstance(scope, list):
            scopes = scope
        else:
            scopes = ['user']

        if 'profile' in scopes:
            expected_profile_servers.add(server['name'])

    actual_servers = set(servers.keys())

    # Check for missing servers
    missing = expected_profile_servers - actual_servers
    if missing:
        errors.append(f'Missing profile MCP servers in {path.name}: {missing}')

    # Validate each server's configuration
    for name, server_config in servers.items():
        server_errors = _validate_mcp_server_config(name, server_config)
        errors.extend(server_errors)

    return errors


def _validate_mcp_server_config(name: str, server: dict[str, Any]) -> list[str]:
    """Validate individual MCP server configuration.

    Internal helper that validates a single MCP server's configuration.

    Args:
        name: Server name for error messages
        server: Server configuration dictionary

    Returns:
        List of error strings
    """
    errors: list[str] = []

    # Check for unexpanded tildes in all string fields
    tilde_fields = ['command', 'url']
    errors.extend(
        f"Server '{name}': unexpanded tilde in {field}: {server[field]}"
        for field in tilde_fields
        if field in server and isinstance(server[field], str) and '~' in server[field]
    )

    # Check args array for unexpanded tildes
    for idx, arg in enumerate(server.get('args', [])):
        if isinstance(arg, str) and '~' in arg:
            errors.append(f"Server '{name}': unexpanded tilde in args[{idx}]: {arg}")

    # Check env for unexpanded tildes - handle both dict and list formats
    env = server.get('env', {})
    if isinstance(env, dict):
        for env_key, env_value in env.items():
            if isinstance(env_value, str) and '~' in env_value:
                errors.append(
                    f"Server '{name}': unexpanded tilde in env[{env_key}]: {env_value}",
                )
    elif isinstance(env, list):
        # Handle list format like ["KEY=value", "KEY2=value2"]
        for idx, env_item in enumerate(env):
            if isinstance(env_item, str) and '~' in env_item:
                errors.append(
                    f"Server '{name}': unexpanded tilde in env[{idx}]: {env_item}",
                )

    # Windows-specific: npx must be wrapped with cmd /c
    if sys.platform == 'win32':
        command = server.get('command', '')
        if command == 'npx':
            errors.append(
                f"Server '{name}': npx not wrapped with 'cmd /c' on Windows. "
                "Expected command to be 'cmd' with args starting with '/c', 'npx'",
            )

    # Validate transport-specific fields
    server_type = server.get('type', '')
    if server_type in ('http', 'sse') and 'url' not in server:
        errors.append(f"Server '{name}': {server_type} transport requires 'url'")
    elif server_type == 'stdio' and 'command' not in server:
        errors.append(f"Server '{name}': stdio transport requires 'command'")

    return errors


def validate_additional_settings(path: Path, config: dict[str, Any]) -> list[str]:
    """Validate {cmd}-additional-settings.json.

    Validates the environment-specific settings file that is loaded via --settings flag.
    Contains: model, permissions, env, hooks, attribution, statusLine, etc.

    Validates:
    - File exists and is valid JSON
    - Model matches config if specified
    - Permissions structure is correct
    - MCP server permissions are auto-added to allow list
    - Hooks structure is correct if present
    - Environment variables are present
    - alwaysThinkingEnabled matches config if specified
    - companyAnnouncements are present if specified
    - statusLine structure is correct if specified

    Args:
        path: Path to the additional-settings.json file
        config: Golden configuration dictionary

    Returns:
        List of error strings (empty if validation passes)
    """
    errors: list[str] = []

    data, file_errors = validate_json_file(path)
    if file_errors:
        return file_errors

    assert data is not None  # For type checker

    # Model verification
    if 'model' in config and data.get('model') != config['model']:
        errors.append(
            f"Model mismatch: expected {config['model']!r}, got {data.get('model')!r}",
        )

    # Permissions validation
    if 'permissions' in config:
        if 'permissions' not in data:
            errors.append("Missing 'permissions' block in additional-settings.json")
        else:
            perm_errors = _validate_permissions(data['permissions'], config['permissions'])
            errors.extend(perm_errors)

    # Environment variables
    config_env = config.get('env-variables', {})
    for key, expected_value in config_env.items():
        actual = data.get('env', {}).get(key)
        if actual != expected_value:
            errors.append(
                f"Env var '{key}': expected {expected_value!r}, got {actual!r}",
            )

    # Hooks structure validation
    hooks_config = config.get('hooks', {})
    events = hooks_config.get('events', [])
    if events:
        if 'hooks' not in data:
            errors.append("Missing 'hooks' block (expected due to hooks.events in config)")
        else:
            hooks_errors = _validate_hooks_structure(data['hooks'], hooks_config)
            errors.extend(hooks_errors)

    # alwaysThinkingEnabled
    if 'always-thinking-enabled' in config:
        expected = config['always-thinking-enabled']
        actual = data.get('alwaysThinkingEnabled')
        if actual != expected:
            errors.append(
                f'alwaysThinkingEnabled: expected {expected!r}, got {actual!r}',
            )

    # companyAnnouncements
    if 'company-announcements' in config:
        if 'companyAnnouncements' not in data:
            errors.append("Missing 'companyAnnouncements' (expected due to config)")
        else:
            expected_count = len(config['company-announcements'])
            actual_count = len(data.get('companyAnnouncements', []))
            if actual_count != expected_count:
                errors.append(
                    f'companyAnnouncements count: expected {expected_count}, got {actual_count}',
                )

    # statusLine
    if 'status-line' in config:
        if 'statusLine' not in data:
            errors.append("Missing 'statusLine' (expected due to config)")
        else:
            status_errors = _validate_status_line(data['statusLine'], config['status-line'])
            errors.extend(status_errors)

    # attribution
    if 'attribution' in config:
        if 'attribution' not in data:
            errors.append("Missing 'attribution' (expected due to config)")
        else:
            for key in ['commit', 'pr']:
                if key in config['attribution']:
                    expected = config['attribution'][key]
                    actual = data['attribution'].get(key)
                    if actual != expected:
                        errors.append(
                            f'attribution.{key}: expected {expected!r}, got {actual!r}',
                        )

    return errors


def _validate_permissions(actual: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    """Validate permissions structure.

    Args:
        actual: Actual permissions dict from generated file
        expected: Expected permissions dict from config

    Returns:
        List of error strings
    """
    errors: list[str] = []

    # Check defaultMode
    if 'defaultMode' in expected and actual.get('defaultMode') != expected['defaultMode']:
        errors.append(
            f"permissions.defaultMode: expected {expected['defaultMode']!r}, "
            f"got {actual.get('defaultMode')!r}",
        )

    # Check allow list
    actual_allow = actual.get('allow', [])
    errors.extend(
        f'Missing in permissions.allow: {item!r}'
        for item in expected.get('allow', [])
        if item not in actual_allow
    )

    # Check deny list
    actual_deny = actual.get('deny', [])
    errors.extend(
        f'Missing in permissions.deny: {item!r}'
        for item in expected.get('deny', [])
        if item not in actual_deny
    )

    # Check ask list
    actual_ask = actual.get('ask', [])
    errors.extend(
        f'Missing in permissions.ask: {item!r}'
        for item in expected.get('ask', [])
        if item not in actual_ask
    )

    return errors


def _validate_hooks_structure(actual: dict[str, Any], config: dict[str, Any]) -> list[str]:
    """Validate hooks structure in additional-settings.json.

    The hooks structure in the generated file is:
    {
        "EventName": [
            {"matcher": "pattern", "hooks": [{"type": "command", "command": "..."}]}
        ]
    }

    Args:
        actual: Actual hooks dict from generated file
        config: Hooks config from golden_config.yaml

    Returns:
        List of error strings
    """
    errors: list[str] = []

    events = config.get('events', [])
    for event_config in events:
        event_name = event_config.get('event', '')
        if not event_name:
            continue

        if event_name not in actual:
            errors.append(f'Missing hook event: {event_name}')
            continue

        event_hooks = actual[event_name]
        if not isinstance(event_hooks, list):
            errors.append(f"Hook event '{event_name}' must be a list")
            continue

        # Check matcher exists in one of the hook groups
        expected_matcher = event_config.get('matcher', '')
        found_matcher = False
        for hook_group in event_hooks:
            if hook_group.get('matcher') == expected_matcher:
                found_matcher = True
                # Validate the hook type
                hook_type = event_config.get('type', 'command')
                inner_hooks = hook_group.get('hooks', [])
                if not inner_hooks:
                    errors.append(
                        f"Hook event '{event_name}' matcher '{expected_matcher}' has empty hooks list",
                    )
                else:
                    errors.extend(
                        f'Hook type mismatch for {event_name}: expected {hook_type!r}'
                        for hook in inner_hooks
                        if hook.get('type') != hook_type
                    )
                break

        if not found_matcher and expected_matcher:
            errors.append(
                f"Hook event '{event_name}' missing matcher '{expected_matcher}'",
            )

    return errors


def _validate_status_line(actual: dict[str, Any], config: dict[str, Any]) -> list[str]:
    """Validate statusLine configuration.

    Args:
        actual: Actual statusLine dict from generated file
        config: status-line config from golden_config.yaml

    Returns:
        List of error strings
    """
    errors: list[str] = []

    # statusLine must have type: command
    if actual.get('type') != 'command':
        errors.append(f"statusLine.type: expected 'command', got {actual.get('type')!r}")

    # Must have a command
    if 'command' not in actual:
        errors.append("statusLine missing 'command' field")
    else:
        # Command should contain the script filename
        script_file = config.get('file', '')
        if script_file:
            # Extract just the filename (without query params)
            filename = script_file.split('?')[0].split('/')[-1]
            if filename not in actual['command']:
                errors.append(
                    f"statusLine.command should contain '{filename}', got: {actual['command']}",
                )
        # Check for unexpanded tilde
        if '~' in actual['command']:
            errors.append(f"statusLine.command contains unexpanded tilde: {actual['command']}")

    # Check padding if specified
    if 'padding' in config and actual.get('padding') != config['padding']:
        errors.append(
            f"statusLine.padding: expected {config['padding']!r}, got {actual.get('padding')!r}",
        )

    return errors


def validate_file_exists(path: Path, description: str) -> list[str]:
    """Verify a file exists.

    Simple existence check with descriptive error message.

    Args:
        path: Path to check
        description: Human-readable description for error message

    Returns:
        List with single error if file missing, empty list if exists
    """
    if not path.exists():
        return [f'{description} not found: {path}']
    return []


def validate_path_expanded(path_str: str, context: str = '') -> list[str]:
    """Verify path has no unexpanded tildes.

    Checks that a path string has been properly expanded (no ~ or ~user patterns).

    Args:
        path_str: The path string to validate
        context: Optional context for error message (e.g., "in MCP server args")

    Returns:
        List with error if unexpanded tilde found, empty list otherwise
    """
    if '~' in path_str:
        ctx_msg = f' {context}' if context else ''
        return [f'Path contains unexpanded tilde{ctx_msg}: {path_str}']
    return []


def validate_launcher_script(
    path: Path,
    command_name: str,
    platform: str | None = None,
) -> list[str]:
    """Validate launcher script content.

    Validates the launcher scripts created for starting Claude Code with the environment.
    Different scripts are created per platform:
    - Unix (Linux/macOS): start-{cmd}.sh or launcher script in ~/.local/bin/{cmd}
    - Windows: launch-{cmd}.sh (shared POSIX), {cmd}.ps1, {cmd}.cmd, {cmd} (Git Bash)

    Args:
        path: Path to the launcher script
        command_name: The command name (used for validation)
        platform: Platform override for testing (defaults to sys.platform)

    Returns:
        List of error strings (empty if validation passes)
    """
    # Use provided platform or detect
    current_platform = platform or sys.platform

    if not path.exists():
        return [f'Launcher script not found: {path}']

    try:
        content = path.read_text(encoding='utf-8')
    except OSError as e:
        return [f'Failed to read launcher script {path}: {e}']

    if current_platform == 'win32':
        return _validate_windows_launcher(path, content, command_name)
    return _validate_unix_launcher(path, content, command_name)


def _validate_windows_launcher(path: Path, content: str, command_name: str) -> list[str]:
    """Validate Windows launcher script.

    Args:
        path: Path to the launcher script
        content: Script content
        command_name: Command name for validation

    Returns:
        List of error strings
    """
    errors: list[str] = []
    suffix = path.suffix.lower()

    if suffix == '.ps1':
        # PowerShell wrapper
        if '& ' not in content and 'Invoke-Expression' not in content:
            errors.append(f'PowerShell wrapper {path.name} lacks invocation (& or Invoke-Expression)')
        # Should reference the launcher script
        if f'launch-{command_name}.sh' not in content and command_name not in content:
            errors.append(f'PowerShell wrapper {path.name} missing reference to launcher or command')

    elif suffix == '.cmd':
        # CMD wrapper
        if '@echo off' not in content.lower():
            errors.append(f"CMD wrapper {path.name} lacks '@echo off'")
        # Should call bash with the launcher script
        if 'bash' not in content.lower():
            errors.append(f'CMD wrapper {path.name} missing bash invocation')

    elif suffix == '.sh' or suffix == '':
        # Shared POSIX script (launch-{cmd}.sh) or Git Bash wrapper
        if not content.strip().startswith('#!'):
            errors.append(f'Script {path.name} missing shebang')
        if 'claude' not in content.lower():
            errors.append(f'Script {path.name} missing claude invocation')

    return errors


def _validate_unix_launcher(path: Path, content: str, command_name: str) -> list[str]:
    """Validate Unix launcher script.

    Args:
        path: Path to the launcher script
        content: Script content
        command_name: Command name for validation

    Returns:
        List of error strings
    """
    errors: list[str] = []

    # Must have shebang
    if not content.strip().startswith('#!'):
        errors.append(f'Unix launcher {path.name} missing shebang')

    # Must reference claude
    if 'claude' not in content.lower():
        errors.append(f'Unix launcher {path.name} missing claude invocation')

    # Should reference the additional-settings file
    settings_pattern = f'{command_name}-additional-settings.json'
    if settings_pattern not in content:
        errors.append(f'Unix launcher {path.name} missing reference to {settings_pattern}')

    return errors


def validate_all_paths_expanded(data: dict[str, Any], path_keys: list[str]) -> list[str]:
    """Validate that specified keys in a dict have expanded paths (no tildes).

    Recursively checks nested dicts and lists for unexpanded tildes.

    Args:
        data: Dictionary to validate
        path_keys: List of keys that are known to contain paths

    Returns:
        List of error strings for any unexpanded paths
    """
    errors: list[str] = []

    def check_value(value: object, key_path: str) -> None:
        if isinstance(value, str) and '~' in value:
            errors.append(f'Unexpanded tilde in {key_path}: {value}')
        elif isinstance(value, dict):
            for k, v in value.items():
                check_value(v, f'{key_path}.{k}')
        elif isinstance(value, list):
            for idx, item in enumerate(value):
                check_value(item, f'{key_path}[{idx}]')

    for key in path_keys:
        if key in data:
            check_value(data[key], key)

    return errors
