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

    # Keys that undergo tilde expansion during write_user_settings()
    # Platform-conditional behavior:
    # - Windows: tildes are expanded to absolute paths (Windows shell doesn't resolve ~)
    # - Linux/macOS/WSL: tildes are PRESERVED (Claude Code resolves ~ at runtime)
    tilde_keys = {'apiKeyHelper', 'awsCredentialExport'}

    # Validate user-settings are merged correctly
    user_settings = config.get('user-settings', {})
    for key, expected_value in user_settings.items():
        # RFC 7396: null-valued keys should be ABSENT from output
        if expected_value is None:
            if key in data:
                errors.append(
                    f"settings.json key '{key}': expected ABSENT (null-as-delete), "
                    f"but found {data[key]!r}",
                )
            continue
        actual_value = data.get(key)
        if key in tilde_keys:
            if sys.platform == 'win32':
                # Windows: verify tildes are expanded
                if actual_value is None:
                    errors.append(f"settings.json key '{key}': missing (expected expanded form)")
                elif isinstance(actual_value, str) and '~' in actual_value:
                    errors.append(
                        f"settings.json key '{key}' contains unexpanded tilde: {actual_value}",
                    )
            else:
                # Unix/WSL: verify tildes are PRESERVED (value unchanged)
                if actual_value is None:
                    errors.append(f"settings.json key '{key}': missing (expected preserved form)")
                elif actual_value != expected_value:
                    errors.append(
                        f"settings.json key '{key}': expected tilde preserved "
                        f"{expected_value!r}, got {actual_value!r}",
                    )
        elif actual_value != expected_value:
            errors.append(
                f"settings.json key '{key}': expected {expected_value!r}, got {actual_value!r}",
            )

    # Also check for unexpanded tildes in tilde-expansion keys not in user-settings
    # (only on Windows - on Unix, tildes are expected to remain)
    if sys.platform == 'win32':
        errors.extend(
            f"settings.json key '{key}' contains unexpanded tilde: {data[key]}"
            for key in tilde_keys
            if key in data
            and key not in user_settings
            and isinstance(data[key], str)
            and '~' in data[key]
        )

    return errors


def _is_profile_scoped(server: dict[str, Any]) -> bool:
    """Check if a server configuration includes 'profile' in its scope.

    Handles both string scope ('profile') and list scope (['user', 'profile']).

    Args:
        server: MCP server configuration dictionary from YAML.

    Returns:
        True if the server has profile scope, False otherwise.
    """
    scope = server.get('scope', 'user')
    if isinstance(scope, str):
        return scope == 'profile'
    if isinstance(scope, list):
        return 'profile' in scope
    return False


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

    # Non-Windows: cmd /c wrapper must NOT be present
    # This catches bugs where Windows-specific wrapping is incorrectly applied on Unix
    if sys.platform != 'win32':
        command = server.get('command', '')
        if command == 'cmd':
            args = server.get('args', [])
            if args and len(args) >= 2 and args[0] == '/c':
                errors.append(
                    f"Server '{name}': Windows-specific 'cmd /c' wrapper found on Unix. "
                    "This indicates a cross-platform bug in MCP server configuration.",
                )

    # Validate headers field for HTTP/SSE servers in profile config
    # When created by create_mcp_config_file(), headers are stored as a dict
    if 'headers' in server:
        headers = server['headers']
        if not isinstance(headers, dict):
            errors.append(
                f"Server '{name}': 'headers' must be a dict, got {type(headers).__name__}",
            )
        else:
            for hdr_key, hdr_value in headers.items():
                if not isinstance(hdr_key, str) or not isinstance(hdr_value, str):
                    errors.append(
                        f"Server '{name}': header key/value must be strings: "
                        f'{hdr_key!r}={hdr_value!r}',
                    )

    # Validate transport-specific fields
    server_type = server.get('type', '')
    if server_type in ('http', 'sse') and 'url' not in server:
        errors.append(f"Server '{name}': {server_type} transport requires 'url'")
    elif server_type == 'stdio' and 'command' not in server:
        errors.append(f"Server '{name}': stdio transport requires 'command'")

    return errors


def validate_settings(path: Path, config: dict[str, Any]) -> list[str]:
    """Validate profile configuration (config.json).

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
    - effortLevel matches config if specified
    - companyAnnouncements are present if specified
    - statusLine structure is correct if specified

    Args:
        path: Path to the settings.json file
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
            errors.append("Missing 'permissions' block in settings.json")
        else:
            perm_errors = _validate_permissions(data['permissions'], config['permissions'])
            errors.extend(perm_errors)

    # Environment variables
    config_env = config.get('env-variables', {})
    for key, expected_value in config_env.items():
        actual = data.get('env', {}).get(key)
        # Production code coerces env values to strings via str(v)
        expected_str = str(expected_value)
        if actual != expected_str:
            errors.append(
                f"Env var '{key}': expected {expected_str!r}, got {actual!r}",
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

    # effortLevel
    if 'effort-level' in config:
        expected = config['effort-level']
        actual = data.get('effortLevel')
        if actual != expected:
            errors.append(
                f'effortLevel: expected {expected!r}, got {actual!r}',
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

    # Check defaultMode (YAML key: default-mode, JSON key: defaultMode)
    if 'default-mode' in expected and actual.get('defaultMode') != expected['default-mode']:
        errors.append(
            f"permissions.defaultMode: expected {expected['default-mode']!r}, "
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

    # Check additionalDirectories (YAML key: additional-directories, JSON key: additionalDirectories)
    if 'additional-directories' in expected:
        expected_dirs = expected['additional-directories']
        actual_dirs = actual.get('additionalDirectories', [])
        if actual_dirs != expected_dirs:
            errors.append(
                f'permissions.additionalDirectories: expected {expected_dirs!r}, '
                f'got {actual_dirs!r}',
            )

    return errors


def _validate_hooks_structure(actual: dict[str, Any], config: dict[str, Any]) -> list[str]:
    """Validate hooks structure in settings.json.

    The hooks structure in the generated file is:
    {
        "EventName": [
            {"matcher": "pattern", "hooks": [{"type": "command", "command": "..."}]}
        ]
    }

    Supports all 4 hook types: command, http, prompt, agent.
    Also validates common fields (if, status-message, once, timeout) pass-through.

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
                    for hook in inner_hooks:
                        if hook.get('type') != hook_type:
                            errors.append(
                                f'Hook type mismatch for {event_name}: expected {hook_type!r}',
                            )

                        # Validate type-specific fields
                        if hook_type == 'command':
                            command = hook.get('command', '')
                            command_file = event_config.get('command', '')
                            command_file_lower = command_file.lower()

                            # Check Python prefix
                            if (
                                command_file_lower.endswith(('.py', '.pyw'))
                                and 'uv run' not in command
                            ):
                                errors.append(
                                    f"Python hook '{command_file}' missing 'uv run' prefix "
                                    f'in command: {command}',
                                )

                            # Check JavaScript prefix
                            elif (
                                command_file_lower.endswith(('.js', '.mjs', '.cjs'))
                                and not command.startswith('node ')
                            ):
                                errors.append(
                                    f"JavaScript hook '{command_file}' missing 'node' prefix "
                                    f'in command: {command}',
                                )

                            # Validate command-specific optional fields pass-through
                            if event_config.get('async') is not None and hook.get('async') != event_config['async']:
                                errors.append(
                                    f"Hook '{event_name}' async field mismatch: "
                                    f"expected {event_config['async']!r}, got {hook.get('async')!r}",
                                )
                            if event_config.get('shell') is not None and hook.get('shell') != event_config['shell']:
                                errors.append(
                                    f"Hook '{event_name}' shell field mismatch: "
                                    f"expected {event_config['shell']!r}, got {hook.get('shell')!r}",
                                )

                        elif hook_type == 'http':
                            if not hook.get('url'):
                                errors.append(
                                    f"HTTP hook '{event_name}' missing 'url' field",
                                )
                            if event_config.get('headers') is not None and hook.get('headers') != event_config['headers']:
                                errors.append(
                                    f"HTTP hook '{event_name}' headers mismatch",
                                )
                            expected_env_vars = event_config.get('allowed-env-vars')
                            if expected_env_vars is not None and hook.get('allowedEnvVars') != expected_env_vars:
                                errors.append(
                                    f"HTTP hook '{event_name}' allowedEnvVars mismatch",
                                )

                        elif hook_type in ('prompt', 'agent'):
                            if not hook.get('prompt'):
                                errors.append(
                                    f"{hook_type.capitalize()} hook '{event_name}' missing 'prompt' field",
                                )
                            expected_model = event_config.get('model')
                            if expected_model is not None and hook.get('model') != expected_model:
                                errors.append(
                                    f"{hook_type.capitalize()} hook '{event_name}' model mismatch: "
                                    f"expected {expected_model!r}, got {hook.get('model')!r}",
                                )

                        # Validate common fields pass-through for all types
                        # YAML uses kebab-case (status-message), JSON uses camelCase (statusMessage)
                        yaml_to_json_common = {'status-message': 'statusMessage'}
                        for yaml_field in ('if', 'status-message', 'once', 'timeout'):
                            json_field = yaml_to_json_common.get(yaml_field, yaml_field)
                            expected_val = event_config.get(yaml_field)
                            if expected_val is not None and hook.get(json_field) != expected_val:
                                errors.append(
                                    f"Hook '{event_name}' common field '{json_field}' mismatch: "
                                    f"expected {expected_val!r}, "
                                    f"got {hook.get(json_field)!r}",
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
    - Unix (Linux/macOS): launch.sh in ~/.claude/{cmd}/
    - Windows: launch.sh (shared POSIX), {cmd}.ps1, {cmd}.cmd, {cmd} (Git Bash)

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
        if 'launch.sh' not in content and command_name not in content:
            errors.append(f'PowerShell wrapper {path.name} missing reference to launcher or command')

    elif suffix == '.cmd':
        # CMD wrapper
        if '@echo off' not in content.lower():
            errors.append(f"CMD wrapper {path.name} lacks '@echo off'")
        # Should call bash with the launcher script
        if 'bash' not in content.lower():
            errors.append(f'CMD wrapper {path.name} missing bash invocation')

    elif suffix == '.sh' or suffix == '':
        # Shared POSIX script (launch.sh) or Git Bash wrapper
        if not content.strip().startswith('#!'):
            errors.append(f'Script {path.name} missing shebang')
        if 'claude' not in content.lower():
            errors.append(f'Script {path.name} missing claude invocation')

    return errors


def _validate_unix_launcher(path: Path, content: str, command_name: str) -> list[str]:
    """Validate Unix launcher script (launch.sh in ~/.claude/{cmd}/).

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

    # Should reference the settings file via --settings flag
    if '--settings' not in content:
        errors.append(f'Unix launcher {path.name} for {command_name} missing --settings flag reference')

    return errors


def validate_version_detection_pattern(content: str, script_name: str) -> list[str]:
    """Validate that script uses cross-platform version detection pattern.

    Checks that the script uses POSIX ERE (grep -oE) instead of PCRE (grep -oP)
    for compatibility with macOS BSD grep.

    Args:
        content: Script content to validate
        script_name: Name of the script for error messages

    Returns:
        List of error strings (empty if validation passes)
    """
    errors: list[str] = []

    # Check for forbidden PCRE patterns
    if 'grep -oP' in content:
        errors.append(
            f'{script_name}: Contains grep -oP (PCRE) which is not supported on macOS. '
            'Use grep -oE (POSIX ERE) instead.',
        )

    if 'grep -P' in content:
        errors.append(
            f'{script_name}: Contains grep -P (PCRE) which is not supported on macOS. '
            'Use grep -E (POSIX ERE) instead.',
        )

    # Check for PCRE digit shorthand in grep context
    # Look for patterns like: grep ... '\\d+' or grep ... "\\d+"
    if 'grep' in content and ('\\\\d+' in content or "'\\d+" in content):
        errors.append(
            f'{script_name}: Contains \\d+ (PCRE digit) which is not supported on macOS. '
            'Use [0-9]+ (POSIX) instead.',
        )

    # Verify correct pattern is present (if version detection is used)
    if 'get_claude_version' in content:
        if 'grep -oE' not in content:
            errors.append(
                f'{script_name}: Version detection function exists but grep -oE not found. '
                'Version detection must use POSIX ERE for cross-platform compatibility.',
            )
        if '[0-9]+' not in content:
            errors.append(
                f'{script_name}: Version detection function exists but [0-9]+ pattern not found. '
                'Must use POSIX digit class for cross-platform compatibility.',
            )

    return errors


def validate_path_separator_consistency(path_str: str, context: str = '') -> list[str]:
    """Verify path has consistent separators (no mixed forward/back slashes).

    On Windows: paths should use only backslashes after normpath normalization.
    On Unix: paths should use only forward slashes (backslashes are not path separators).

    This validator detects paths that were expanded (e.g. via os.path.expanduser)
    but not normalized via os.path.normpath, which can result in mixed separators
    like ``C:\\Users\\user/.claude/scripts/file.py`` on Windows.

    Args:
        path_str: The path string to validate
        context: Optional context for error message (e.g., "statusLine.command")

    Returns:
        List with error if mixed separators found, empty list otherwise
    """
    errors: list[str] = []
    if sys.platform == 'win32':
        # On Windows, after normpath, a path that contains a drive letter
        # or backslash should not also contain forward slash
        if ('\\' in path_str or ':' in path_str) and '/' in path_str:
            ctx_msg = f' {context}' if context else ''
            errors.append(f'Mixed path separators on Windows{ctx_msg}: {path_str}')
    else:
        # On Unix, a path containing both forward and backslash is mixed
        if '\\' in path_str and '/' in path_str:
            ctx_msg = f' {context}' if context else ''
            errors.append(f'Mixed path separators on Unix{ctx_msg}: {path_str}')
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


def validate_no_windows_path_contamination(
    data: dict[str, Any],
    context: str = '',
) -> list[str]:
    """Validate that settings do not contain Windows path contamination on Unix.

    Checks for Windows-specific path patterns (backslashes, drive letters)
    in tilde-expansion keys on non-Windows platforms.

    Args:
        data: Parsed JSON data (e.g., settings.json content)
        context: Optional context for error messages (e.g., 'settings.json')

    Returns:
        List of error strings (empty if no contamination found)
    """
    import re

    if sys.platform != 'win32':
        errors: list[str] = []
        tilde_keys = {'apiKeyHelper', 'awsCredentialExport'}
        ctx_prefix = f'{context} ' if context else ''

        for key in tilde_keys:
            if key not in data or not isinstance(data[key], str):
                continue
            value = data[key]

            # Check for Windows backslash paths
            if '\\' in value:
                errors.append(
                    f'{ctx_prefix}{key} contains backslash (Windows path contamination): {value}',
                )

            # Check for Windows drive letters (C:\, D:\, etc.)
            if re.search(r'[A-Za-z]:[/\\]', value):
                errors.append(
                    f'{ctx_prefix}{key} contains Windows drive letter on Unix: {value}',
                )

        return errors
    # Not applicable on Windows
    return []


def validate_tilde_preservation_on_unix(
    data: dict[str, Any],
    original_settings: dict[str, Any],
    context: str = '',
) -> list[str]:
    """Validate that tilde-expansion keys are preserved on Unix platforms.

    On Linux/macOS/WSL, Claude Code resolves ~ at runtime, so settings.json
    should contain the original tilde paths unchanged.

    Args:
        data: Parsed JSON data from settings.json
        original_settings: Original user-settings from config (before processing)
        context: Optional context for error messages

    Returns:
        List of error strings (empty if preservation is correct)
    """
    if sys.platform != 'win32':
        errors: list[str] = []
        tilde_keys = {'apiKeyHelper', 'awsCredentialExport'}
        ctx_prefix = f'{context} ' if context else ''

        for key in tilde_keys:
            if key not in original_settings:
                continue
            original = original_settings[key]
            actual = data.get(key)

            if actual is None:
                errors.append(f'{ctx_prefix}{key}: missing (expected preserved tilde value)')
            elif actual != original:
                errors.append(
                    f'{ctx_prefix}{key}: tilde not preserved - '
                    f'expected {original!r}, got {actual!r}',
                )

        return errors
    # Not applicable on Windows
    return []


def validate_manifest(path: Path, config: dict[str, Any]) -> list[str]:
    """Validate {cmd}-manifest.json structure and content.

    Validates the installation manifest file that records configuration metadata.

    Validates:
    - File exists and is valid JSON
    - Required fields are present: name, version, config_source, config_source_url,
      config_source_type, installed_at, last_checked_at, command_names
    - version matches config['version'] if present
    - config_source_type is one of: url, local, repo
    - command_names is a non-empty list
    - installed_at is a valid ISO timestamp string
    - last_checked_at is None (freshly created)
    - name matches the primary command name

    Args:
        path: Path to the manifest JSON file
        config: Golden configuration dictionary

    Returns:
        List of error strings (empty if validation passes)
    """
    data, file_errors = validate_json_file(path)
    if file_errors:
        return file_errors

    assert data is not None

    # Required fields check
    required_fields = [
        'name', 'version', 'config_source', 'config_source_url',
        'config_source_type', 'installed_at', 'last_checked_at', 'command_names',
    ]
    errors = [
        f"Manifest missing required field: '{field}'"
        for field in required_fields
        if field not in data
    ]

    if errors:
        return errors  # Cannot validate content without required fields

    # Version check
    expected_version = config.get('version')
    if expected_version is not None:
        expected_version_str = str(expected_version).strip()
        if data['version'] != expected_version_str:
            errors.append(
                f"Manifest version: expected {expected_version_str!r}, got {data['version']!r}",
            )
    elif data['version'] is not None:
        errors.append(
            f"Manifest version: expected None (no version in config), got {data['version']!r}",
        )

    # config_source_type validation
    valid_types = {'url', 'local', 'repo'}
    if data['config_source_type'] not in valid_types:
        errors.append(
            f"Manifest config_source_type: expected one of {valid_types}, "
            f"got {data['config_source_type']!r}",
        )

    # command_names validation
    if not isinstance(data['command_names'], list) or len(data['command_names']) == 0:
        errors.append('Manifest command_names: expected non-empty list')

    # installed_at must be a string (ISO timestamp)
    if not isinstance(data['installed_at'], str):
        errors.append(
            f"Manifest installed_at: expected ISO timestamp string, "
            f"got {type(data['installed_at']).__name__}",
        )

    # last_checked_at must be None for fresh manifest
    if data['last_checked_at'] is not None:
        errors.append(
            f"Manifest last_checked_at: expected None for fresh manifest, "
            f"got {data['last_checked_at']!r}",
        )

    # name should match primary command name
    cmd_names = config.get('command-names')
    expected_cmd = cmd_names[0] if isinstance(cmd_names, list) and cmd_names else ''
    if expected_cmd and data['name'] != expected_cmd:
        errors.append(
            f"Manifest name: expected {expected_cmd!r}, got {data['name']!r}",
        )

    return errors


def validate_global_config_output(
    home_dir: Path,
    golden_config: dict[str, Any],
) -> list[str]:
    """Validate ~/.claude.json contains merged global-config values.

    Validates:
    - File exists and is valid JSON
    - All global-config keys from golden config are present
    - Values match expected values

    Args:
        home_dir: Path to the home directory (e.g., tmp_path)
        golden_config: Golden configuration dictionary

    Returns:
        List of error strings (empty if validation passes)
    """
    errors: list[str] = []
    claude_json = home_dir / '.claude.json'

    global_config = golden_config.get('global-config')
    if not global_config:
        return errors

    if not claude_json.exists():
        errors.append(f'Expected {claude_json} to exist')
        return errors

    try:
        content = json.loads(claude_json.read_text(encoding='utf-8'))
    except json.JSONDecodeError as e:
        errors.append(f'Invalid JSON in {claude_json}: {e}')
        return errors

    for key, expected_value in global_config.items():
        # RFC 7396: null-valued keys should be ABSENT from output
        if expected_value is None:
            if key in content:
                errors.append(
                    f'Key {key!r} should be ABSENT from ~/.claude.json '
                    f'(null-as-delete), but found {content[key]!r}',
                )
            continue
        if key not in content:
            errors.append(f'Missing key {key!r} in ~/.claude.json')
        elif content[key] != expected_value:
            errors.append(
                f'Key {key!r}: expected {expected_value!r}, got {content[key]!r}',
            )

    return errors


def validate_auto_update_controls(
    home_dir: Path, pinned: bool, command_name: str | None = None,
) -> list[str]:
    """Validate auto-update controls are correctly set or absent.

    When pinned=True, expects:
    - ~/.claude.json has autoUpdates: false
    - settings.json (wherever written) has env.DISABLE_AUTOUPDATER: "1"

    When pinned=True AND command_name is provided, additionally expects:
    - ~/.claude/{command_name}/.claude.json has autoUpdates: false

    When pinned=False, expects:
    - No autoUpdates key injected in ~/.claude.json (or None for null-as-delete)
    - No DISABLE_AUTOUPDATER in settings env section

    Args:
        home_dir: Isolated home directory path
        pinned: Whether a specific version is pinned
        command_name: Command name for isolated environment check, or None

    Returns:
        List of error strings (empty = all validations passed)
    """
    errors: list[str] = []

    # Check ~/.claude.json
    claude_json_path = home_dir / '.claude.json'
    if claude_json_path.exists():
        data, json_errors = validate_json_file(claude_json_path)
        errors.extend(json_errors)
        if data is not None:
            if pinned:
                if 'autoUpdates' not in data:
                    errors.append('Pinned version: autoUpdates missing from ~/.claude.json')
                elif data['autoUpdates'] is not False:
                    errors.append(
                        f'Pinned version: autoUpdates should be false, got {data["autoUpdates"]!r}',
                    )
            else:
                if 'autoUpdates' in data and data['autoUpdates'] is False:
                    errors.append(
                        'Latest/absent version: autoUpdates=false should not be injected',
                    )
    elif pinned:
        errors.append('Pinned version: ~/.claude.json does not exist')

    # Check isolated .claude.json when command_name provided
    if command_name and pinned:
        isolated_json = home_dir / '.claude' / command_name / '.claude.json'
        if isolated_json.exists():
            data, json_errors = validate_json_file(isolated_json)
            errors.extend(json_errors)
            if data is not None:
                if 'autoUpdates' not in data:
                    errors.append(
                        f'Pinned: autoUpdates missing from isolated {isolated_json}',
                    )
                elif data['autoUpdates'] is not False:
                    errors.append(
                        f'Pinned: autoUpdates in {isolated_json} should be false, '
                        f'got {data["autoUpdates"]!r}',
                    )
        else:
            errors.append(f'Pinned: isolated {isolated_json} does not exist')

    return errors


def validate_ide_extension_controls(
    home_dir: Path, pinned: bool, command_name: str | None = None,
) -> list[str]:
    """Validate IDE extension auto-install controls are correctly set or absent.

    When pinned=True, expects:
    - ~/.claude.json has autoInstallIdeExtension: false
    - settings.json has env.CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL: "1"

    When pinned=True AND command_name is provided, additionally expects:
    - ~/.claude/{command_name}/.claude.json has autoInstallIdeExtension: false

    When pinned=False, expects:
    - No autoInstallIdeExtension key injected
    - No CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL in settings env section

    Args:
        home_dir: Isolated home directory path
        pinned: Whether a specific version is pinned
        command_name: Command name for isolated environment check, or None

    Returns:
        List of error strings (empty = all validations passed)
    """
    errors: list[str] = []

    # Check ~/.claude.json
    claude_json_path = home_dir / '.claude.json'
    if claude_json_path.exists():
        data, json_errors = validate_json_file(claude_json_path)
        errors.extend(json_errors)
        if data is not None:
            if pinned:
                if 'autoInstallIdeExtension' not in data:
                    errors.append('Pinned version: autoInstallIdeExtension missing from ~/.claude.json')
                elif data['autoInstallIdeExtension'] is not False:
                    errors.append(
                        f'Pinned version: autoInstallIdeExtension should be false, '
                        f'got {data["autoInstallIdeExtension"]!r}',
                    )
            else:
                if 'autoInstallIdeExtension' in data and data['autoInstallIdeExtension'] is False:
                    errors.append(
                        'Latest/absent version: autoInstallIdeExtension=false should not be injected',
                    )
    elif pinned:
        errors.append('Pinned version: ~/.claude.json does not exist')

    # Check isolated .claude.json when command_name provided
    if command_name and pinned:
        isolated_json = home_dir / '.claude' / command_name / '.claude.json'
        if isolated_json.exists():
            data, json_errors = validate_json_file(isolated_json)
            errors.extend(json_errors)
            if data is not None:
                if 'autoInstallIdeExtension' not in data:
                    errors.append(
                        f'Pinned: autoInstallIdeExtension missing from isolated {isolated_json}',
                    )
                elif data['autoInstallIdeExtension'] is not False:
                    errors.append(
                        f'Pinned: autoInstallIdeExtension in {isolated_json} should be false, '
                        f'got {data["autoInstallIdeExtension"]!r}',
                    )
        else:
            errors.append(f'Pinned: isolated {isolated_json} does not exist')

    return errors


def validate_global_config_dual_write(
    home_dir: Path,
    global_config: dict[str, Any],
    command_name: str | None = None,
) -> list[str]:
    """Validate that global-config is dual-written when command-names is present.

    Args:
        home_dir: Isolated home directory path.
        global_config: Expected global config key-value pairs.
        command_name: Command name for isolated environment, or None.

    Returns:
        List of error strings (empty = all validations passed).
    """
    errors: list[str] = []

    # Check home .claude.json
    home_json_path = home_dir / '.claude.json'
    if home_json_path.exists():
        data, json_errors = validate_json_file(home_json_path)
        errors.extend(json_errors)
        if data is not None:
            for key, value in global_config.items():
                if value is None:
                    # Null-as-delete: key should be absent
                    if key in data:
                        errors.append(f'Home .claude.json: {key} should be deleted (null)')
                elif key not in data:
                    errors.append(f'Home .claude.json: missing key {key}')
                elif data[key] != value:
                    errors.append(
                        f'Home .claude.json: {key} expected {value!r}, got {data[key]!r}',
                    )
    else:
        errors.append('Home .claude.json does not exist')

    # Check isolated .claude.json when command-names present
    if command_name:
        isolated_path = home_dir / '.claude' / command_name / '.claude.json'
        if isolated_path.exists():
            data, json_errors = validate_json_file(isolated_path)
            errors.extend(json_errors)
            if data is not None:
                for key, value in global_config.items():
                    if value is None:
                        if key in data:
                            errors.append(f'Isolated .claude.json: {key} should be deleted')
                    elif key not in data:
                        errors.append(f'Isolated .claude.json: missing key {key}')
                    elif data[key] != value:
                        errors.append(
                            f'Isolated .claude.json: {key} expected {value!r}, got {data[key]!r}',
                        )
        else:
            errors.append(f'Isolated .claude.json does not exist at {isolated_path}')

    return errors


def validate_env_loader_files(
    claude_dir: Path,
    os_env_vars: dict[str, str | None],
    command_name: str | None = None,
) -> list[str]:
    """Validate env loader files exist with correct content.

    Checks that generate_env_loader_files() produced the expected shell-specific
    loader files containing ONLY non-None os-env-variables with proper syntax.

    Validates:
    - Global toolbox-env.sh exists in ~/.claude/
    - Per-command env.sh exists in ~/.claude/{cmd}/ (when command_name provided)
    - File content contains correct export syntax for each shell type
    - None-valued (deletion) variables are excluded from loader files
    - Header comment is present

    Args:
        claude_dir: Path to the ~/.claude directory
        os_env_vars: OS env vars dict from config (None values = deletions)
        command_name: Command name for per-command file checks, or None

    Returns:
        List of error strings (empty if validation passes)
    """
    errors: list[str] = []

    # Determine which vars should appear (non-None only)
    active_vars = {k: str(v) for k, v in os_env_vars.items() if v is not None}
    deletion_vars = [k for k, v in os_env_vars.items() if v is None]

    if not active_vars:
        # No active vars means no files should be generated
        global_sh = claude_dir / 'toolbox-env.sh'
        if global_sh.exists():
            errors.append(
                f'toolbox-env.sh exists but no active os-env-variables: {global_sh}',
            )
        return errors

    # --- Global convenience files ---
    global_sh = claude_dir / 'toolbox-env.sh'
    if not global_sh.exists():
        errors.append(f'Global env loader not found: {global_sh}')
    else:
        sh_content = global_sh.read_text(encoding='utf-8')
        errors.extend(_validate_sh_loader_content(sh_content, active_vars, deletion_vars, 'toolbox-env.sh'))

    # Global PS1 on Windows
    if sys.platform == 'win32':
        global_ps1 = claude_dir / 'toolbox-env.ps1'
        if not global_ps1.exists():
            errors.append(f'Global PS1 env loader not found on Windows: {global_ps1}')
        else:
            ps1_content = global_ps1.read_text(encoding='utf-8')
            errors.extend(
                _validate_ps1_loader_content(ps1_content, active_vars, deletion_vars, 'toolbox-env.ps1'),
            )

    # Global CMD on Windows
    if sys.platform == 'win32':
        global_cmd = claude_dir / 'toolbox-env.cmd'
        if not global_cmd.exists():
            errors.append(f'Global CMD env loader not found on Windows: {global_cmd}')
        else:
            cmd_content = global_cmd.read_text(encoding='utf-8')
            errors.extend(
                _validate_cmd_loader_content(cmd_content, active_vars, deletion_vars, 'toolbox-env.cmd'),
            )

    # --- Per-command files ---
    if command_name:
        cmd_dir = claude_dir / command_name
        cmd_sh = cmd_dir / 'env.sh'
        if not cmd_sh.exists():
            errors.append(f'Per-command env loader not found: {cmd_sh}')
        else:
            sh_content = cmd_sh.read_text(encoding='utf-8')
            errors.extend(_validate_sh_loader_content(sh_content, active_vars, deletion_vars, 'env.sh'))

        if sys.platform == 'win32':
            cmd_ps1 = cmd_dir / 'env.ps1'
            if not cmd_ps1.exists():
                errors.append(f'Per-command PS1 env loader not found on Windows: {cmd_ps1}')
            else:
                ps1_content = cmd_ps1.read_text(encoding='utf-8')
                errors.extend(
                    _validate_ps1_loader_content(ps1_content, active_vars, deletion_vars, 'env.ps1'),
                )

        if sys.platform == 'win32':
            cmd_cmd = cmd_dir / 'env.cmd'
            if not cmd_cmd.exists():
                errors.append(f'Per-command CMD env loader not found on Windows: {cmd_cmd}')
            else:
                cmd_content = cmd_cmd.read_text(encoding='utf-8')
                errors.extend(
                    _validate_cmd_loader_content(cmd_content, active_vars, deletion_vars, 'env.cmd'),
                )

    return errors


def _validate_sh_loader_content(
    content: str,
    active_vars: dict[str, str],
    deletion_vars: list[str],
    filename: str,
) -> list[str]:
    """Validate Bash/Zsh env loader file content.

    Args:
        content: File content
        active_vars: Variables that should be present (name -> value, non-None only)
        deletion_vars: Variable names that must NOT appear
        filename: Filename for error messages

    Returns:
        List of error strings
    """
    errors: list[str] = []

    # Header check
    if not content.startswith('# Auto-generated by claude-code-toolbox'):
        errors.append(f'{filename}: missing header comment')

    # Each active var should have an export line
    errors.extend(
        f'{filename}: missing export for {name}'
        for name in active_vars
        if f'export {name}=' not in content
    )

    # Deletion vars must NOT appear
    errors.extend(
        f'{filename}: deletion var {name} should not appear'
        for name in deletion_vars
        if f'export {name}=' in content
    )

    return errors


def _validate_ps1_loader_content(
    content: str,
    active_vars: dict[str, str],
    deletion_vars: list[str],
    filename: str,
) -> list[str]:
    """Validate PowerShell env loader file content.

    Args:
        content: File content
        active_vars: Variables that should be present (name -> value, non-None only)
        deletion_vars: Variable names that must NOT appear
        filename: Filename for error messages

    Returns:
        List of error strings
    """
    errors: list[str] = []

    # Header check
    if not content.startswith('# Auto-generated by claude-code-toolbox'):
        errors.append(f'{filename}: missing header comment')

    # Each active var should have a $env: line
    errors.extend(
        f'{filename}: missing $env:{name} assignment'
        for name in active_vars
        if f'$env:{name} =' not in content
    )

    # Deletion vars must NOT appear
    errors.extend(
        f'{filename}: deletion var {name} should not appear'
        for name in deletion_vars
        if f'$env:{name} =' in content
    )

    return errors


def _validate_cmd_loader_content(
    content: str,
    active_vars: dict[str, str],
    deletion_vars: list[str],
    filename: str,
) -> list[str]:
    """Validate CMD batch env loader file content.

    Args:
        content: File content
        active_vars: Variables that should be present (name -> value, non-None only)
        deletion_vars: Variable names that must NOT appear
        filename: Filename for error messages

    Returns:
        List of error strings
    """
    errors: list[str] = []

    # Header check
    if not content.startswith('@echo off'):
        errors.append(f'{filename}: missing @echo off header')

    # Each active var should have a SET line
    errors.extend(
        f'{filename}: missing SET for {name}'
        for name in active_vars
        if f'SET "{name}=' not in content
    )

    # Deletion vars must NOT appear
    errors.extend(
        f'{filename}: deletion var {name} should not appear'
        for name in deletion_vars
        if f'SET "{name}=' in content
    )

    return errors


def validate_launcher_env_sourcing(
    launcher_path: Path,
) -> list[str]:
    """Validate that a launcher script contains env loader source guard.

    Checks that create_launcher_script() injected the guarded source line
    for loading OS-level environment variables from the per-command env file.

    Validates:
    - Bash/POSIX launchers contain file-existence guard and source command
    - PowerShell launchers contain Test-Path guard and dot-source command
    - CMD batch launchers contain if exist guard and call to env.cmd

    Args:
        launcher_path: Path to the launcher script

    Returns:
        List of error strings (empty if validation passes)
    """
    errors: list[str] = []

    if not launcher_path.exists():
        return [f'Launcher script not found: {launcher_path}']

    try:
        content = launcher_path.read_text(encoding='utf-8')
    except OSError as e:
        return [f'Failed to read launcher {launcher_path}: {e}']

    suffix = launcher_path.suffix.lower()

    if suffix == '.ps1':
        # PowerShell: expect Test-Path guard and dot-source
        if 'env.ps1' not in content:
            errors.append(
                f'{launcher_path.name}: missing env.ps1 reference in PowerShell launcher',
            )
        if 'Test-Path' not in content:
            errors.append(
                f'{launcher_path.name}: missing Test-Path guard for env.ps1',
            )
    elif suffix == '.cmd':
        # CMD batch: expect if exist guard and call to env.cmd
        if 'env.cmd' not in content:
            errors.append(
                f'{launcher_path.name}: missing env.cmd reference in CMD launcher',
            )
        if 'if exist' not in content:
            errors.append(
                f'{launcher_path.name}: missing if exist guard for env.cmd',
            )
        if 'call' not in content:
            errors.append(
                f'{launcher_path.name}: missing call command for env.cmd',
            )
    elif suffix in ('.sh', ''):
        # Bash/POSIX: expect file-existence guard and source/dot-source
        if 'env.sh' not in content:
            errors.append(
                f'{launcher_path.name}: missing env.sh reference in shell launcher',
            )
        # Check for file-existence guard ([ -f ... ] pattern)
        if '[ -f' not in content and '[-f' not in content:
            errors.append(
                f'{launcher_path.name}: missing file-existence guard for env.sh',
            )

    return errors
