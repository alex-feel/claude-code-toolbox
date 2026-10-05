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
import re
import sys
from pathlib import Path
from typing import Any
from typing import cast

from tests.e2e.expected import EXPECTED_JSON_KEYS


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


def validate_merged_value(actual: object, expected: object, label: str) -> list[str]:
    """Compare a written JSON value against its YAML declaration.

    Mirrors RFC 7396 null-as-delete at every depth: a member declared
    ``null`` in YAML must be ABSENT from the written object, never present
    as a JSON null, because Claude Code copies a null env member into the
    process environment as the string ``'null'``. Non-null members must be
    present with the declared value; nested objects are compared member by
    member so that extra members contributed by other writers are tolerated.

    Args:
        actual: Value read from the written JSON file.
        expected: Value declared in the golden YAML (may contain nulls).
        label: Human-readable path used as the error prefix.

    Returns:
        List of error strings (empty if the value matches).
    """
    if not isinstance(expected, dict):
        if actual != expected:
            return [f'{label}: expected {expected!r}, got {actual!r}']
        return []
    if not isinstance(actual, dict):
        return [f'{label}: expected an object, got {actual!r}']
    actual_obj = cast(dict[str, object], actual)
    errors: list[str] = []
    for key, expected_member in cast(dict[str, object], expected).items():
        member_label = f'{label}.{key}'
        if expected_member is None:
            if key in actual_obj:
                errors.append(
                    f'{member_label}: expected ABSENT (null-as-delete), '
                    f'but found {actual_obj[key]!r}',
                )
            continue
        if key not in actual_obj:
            errors.append(f'{member_label}: missing')
            continue
        errors.extend(validate_merged_value(actual_obj[key], expected_member, member_label))
    return errors


def validate_settings_json(path: Path, config: dict[str, Any]) -> list[str]:
    """Validate settings.json against expected values from config.

    Validates that settings.json (user settings file at ~/.claude/settings.json)
    contains expected values from the 'user-settings' section of the golden config.

    Validates:
    - File exists and is valid JSON
    - Values from config['user-settings'] are present
    - Members declared null at any depth are absent (RFC 7396)

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
        elif key not in data:
            errors.append(f"settings.json key '{key}': missing")
        else:
            errors.extend(
                validate_merged_value(actual_value, expected_value, f"settings.json key '{key}'"),
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
    """Validate the isolated profile configuration (config.json).

    The isolated profile's config.json is loaded via the launcher's --settings
    flag. It carries the profile's complete settings.json content: the
    user-settings section (raw settings.json keys, camelCase) plus the
    toolbox-built statusLine and hooks entries. The two sources are disjoint
    by construction because 'statusLine' and 'hooks' are rejected inside
    user-settings.

    Validates:
    - File exists and is valid JSON
    - Every non-null top-level user-settings key is present verbatim
    - The user-settings env block has null entries stripped and non-null
      string values preserved
    - The user-settings permissions block is present verbatim (camelCase)
    - Hooks structure (from the root-level hooks key) is correct if present
    - statusLine structure (from the root-level status-line key) is correct
      if specified

    Args:
        path: Path to the config.json file
        config: Golden configuration dictionary

    Returns:
        List of error strings (empty if validation passes)
    """
    errors: list[str] = []

    data, file_errors = validate_json_file(path)
    if file_errors:
        return file_errors

    assert data is not None  # For type checker

    user_settings = config.get('user-settings', {})

    # Keys handled by dedicated validators below (env and permissions carry
    # transform semantics) or verified structurally elsewhere.
    specially_handled = {'env', 'permissions'}

    # Keys that undergo platform-conditional tilde handling during the write.
    # Windows expands ~ to an absolute path (the shell cannot resolve ~);
    # Linux/macOS/WSL preserve the tilde for Claude Code to resolve at runtime.
    tilde_keys = {'apiKeyHelper', 'awsCredentialExport'}

    for key, expected_value in user_settings.items():
        if key in specially_handled:
            continue
        # RFC 7396: null-valued keys are stripped from the atomically rebuilt
        # config.json (deletion-by-absence), never written as a JSON null.
        if expected_value is None:
            if key in data:
                errors.append(
                    f"config.json key '{key}': expected ABSENT (null-as-delete), "
                    f'but found {data[key]!r}',
                )
            continue
        actual_value = data.get(key)
        if key in tilde_keys:
            if sys.platform == 'win32':
                # Windows: the tilde must have been expanded to an absolute path
                if actual_value is None:
                    errors.append(f"config.json key '{key}': missing (expected expanded form)")
                elif isinstance(actual_value, str) and actual_value.startswith('~'):
                    errors.append(
                        f"config.json key '{key}' contains unexpanded tilde: {actual_value}",
                    )
            elif actual_value is None:
                errors.append(f"config.json key '{key}': missing (expected preserved form)")
            elif actual_value != expected_value:
                # Unix/WSL: the tilde is preserved verbatim
                errors.append(
                    f"config.json key '{key}': expected tilde preserved "
                    f'{expected_value!r}, got {actual_value!r}',
                )
        elif actual_value != expected_value:
            errors.append(
                f"config.json key '{key}': expected {expected_value!r}, got {actual_value!r}",
            )

    # env block: null entries stripped, non-null values preserved verbatim
    # (production writes string values as-is; the golden config quotes them).
    config_env = user_settings.get('env')
    if config_env is not None:
        env_block = data.get('env') or {}
        for key, expected_value in config_env.items():
            if expected_value is None:
                if key in env_block:
                    errors.append(
                        f"config.json env '{key}': expected ABSENT (null-as-delete), "
                        f'but found {env_block[key]!r}',
                    )
                continue
            actual = env_block.get(key)
            if actual != expected_value:
                errors.append(
                    f"config.json env '{key}': expected {expected_value!r}, got {actual!r}",
                )

    # Permissions validation (camelCase subkeys, no translation)
    config_permissions = user_settings.get('permissions')
    if config_permissions is not None:
        if 'permissions' not in data:
            errors.append("Missing 'permissions' block in config.json")
        else:
            errors.extend(_validate_permissions(data['permissions'], config_permissions))

    # Hooks structure validation (from the root-level hooks key)
    hooks_config = config.get('hooks', {})
    events = hooks_config.get('events', [])
    if events:
        if 'hooks' not in data:
            errors.append("Missing 'hooks' block (expected due to hooks.events in config)")
        else:
            errors.extend(_validate_hooks_structure(data['hooks'], hooks_config))

    # statusLine (from the root-level status-line key)
    if 'status-line' in config:
        if 'statusLine' not in data:
            errors.append("Missing 'statusLine' (expected due to config)")
        else:
            errors.extend(_validate_status_line(data['statusLine'], config['status-line']))

    return errors


def _validate_permissions(actual: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    """Validate permissions structure.

    Reads expectations from the user-settings permissions block, whose
    sub-keys already use camelCase (defaultMode, additionalDirectories), so
    no key translation is applied.

    Args:
        actual: Actual permissions dict from generated file
        expected: Expected permissions dict from user-settings

    Returns:
        List of error strings
    """
    errors: list[str] = []

    # Check defaultMode (camelCase in both sides)
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

    # Check additionalDirectories (camelCase in both sides)
    if 'additionalDirectories' in expected:
        expected_dirs = expected['additionalDirectories']
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

    Supports all 5 hook types: command, http, prompt, agent, mcp_tool.
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

                            if event_config.get('args') is not None:
                                # Exec form: the launcher is the executable and
                                # the script path plus user args live in 'args'
                                actual_args = hook.get('args')
                                if not isinstance(actual_args, list):
                                    errors.append(
                                        f"Exec-form hook '{event_name}' missing 'args' list",
                                    )
                                else:
                                    if command_file_lower.endswith(('.py', '.pyw')) and command != 'uv':
                                        errors.append(
                                            f"Exec-form Python hook '{command_file}' must spawn 'uv', "
                                            f'got: {command}',
                                        )
                                    elif (
                                        command_file_lower.endswith(('.js', '.mjs', '.cjs'))
                                        and command != 'node'
                                    ):
                                        errors.append(
                                            f"Exec-form JavaScript hook '{command_file}' must spawn 'node', "
                                            f'got: {command}',
                                        )
                                    expected_tail = [str(a) for a in event_config['args']]
                                    if expected_tail and actual_args[-len(expected_tail):] != expected_tail:
                                        errors.append(
                                            f"Exec-form hook '{event_name}' args tail mismatch: "
                                            f'expected {expected_tail!r}, got {actual_args!r}',
                                        )
                            else:
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

                                if event_config.get('shell') is not None and hook.get('shell') != event_config['shell']:
                                    errors.append(
                                        f"Hook '{event_name}' shell field mismatch: "
                                        f"expected {event_config['shell']!r}, got {hook.get('shell')!r}",
                                    )

                            # Validate command-specific optional fields pass-through
                            if event_config.get('async') is not None and hook.get('async') != event_config['async']:
                                errors.append(
                                    f"Hook '{event_name}' async field mismatch: "
                                    f"expected {event_config['async']!r}, got {hook.get('async')!r}",
                                )
                            expected_rewake = event_config.get('async-rewake')
                            if expected_rewake is not None and hook.get('asyncRewake') != expected_rewake:
                                errors.append(
                                    f"Hook '{event_name}' asyncRewake field mismatch: "
                                    f"expected {expected_rewake!r}, got {hook.get('asyncRewake')!r}",
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
                            expected_cob = event_config.get('continue-on-block')
                            if expected_cob is not None and hook.get('continueOnBlock') != expected_cob:
                                errors.append(
                                    f"Prompt hook '{event_name}' continueOnBlock mismatch: "
                                    f"expected {expected_cob!r}, got {hook.get('continueOnBlock')!r}",
                                )

                        elif hook_type == 'mcp_tool':
                            if hook.get('server') != event_config.get('server'):
                                errors.append(
                                    f"MCP tool hook '{event_name}' server mismatch: "
                                    f"expected {event_config.get('server')!r}, got {hook.get('server')!r}",
                                )
                            if hook.get('tool') != event_config.get('tool'):
                                errors.append(
                                    f"MCP tool hook '{event_name}' tool mismatch: "
                                    f"expected {event_config.get('tool')!r}, got {hook.get('tool')!r}",
                                )
                            expected_input = event_config.get('input')
                            if expected_input is not None and hook.get('input') != expected_input:
                                errors.append(
                                    f"MCP tool hook '{event_name}' input mismatch: "
                                    f"expected {expected_input!r}, got {hook.get('input')!r}",
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
        errors = _validate_windows_launcher(path, content, command_name)
    else:
        errors = _validate_unix_launcher(path, content, command_name)
    errors.extend(validate_launcher_has_no_update_check(path))
    return errors


# Text a configuration-update check would put into a generated launcher: the
# marker file name, its shell variable, and the notice it prints.
UPDATE_CHECK_FRAGMENTS: tuple[str, ...] = (
    'update-available',
    'UPDATE_MARKER',
    '[UPDATE]',
    'configuration is available',
    'Re-run the installer',
)


def validate_launcher_has_no_update_check(path: Path) -> list[str]:
    """Validate that a generated launcher or wrapper carries no update check.

    Profile launchers start Claude Code directly; no file in the profile
    directory changes what they print.

    Args:
        path: Path to a generated launcher, shell wrapper, or command wrapper

    Returns:
        List of error strings (empty if validation passes)
    """
    try:
        content = path.read_text(encoding='utf-8')
    except OSError as e:
        return [f'Failed to read launcher script {path}: {e}']
    return [
        f'Launcher {path} contains update-check text {fragment!r}'
        for fragment in UPDATE_CHECK_FRAGMENTS
        if fragment in content
    ]


def validate_launcher_keeps_slash_arguments(launch_sh: Path, *, windows: bool) -> list[str]:
    """Validate how launch.sh hands arguments that start with a slash to Claude Code.

    Git Bash converts an argument that looks like a POSIX path when it starts
    the native claude.exe, so the Windows launch.sh lists each argument that
    starts with a single slash and names no existing path in
    MSYS2_ARG_CONV_EXCL before any line that starts claude. Linux and macOS
    convert nothing, and their launch.sh carries no such list.

    Args:
        launch_sh: The generated launch.sh.
        windows: Whether launch_sh is the Windows launcher.

    Returns:
        List of error strings (empty if validation passes)
    """
    try:
        content = launch_sh.read_text(encoding='utf-8')
    except OSError as e:
        return [f'Failed to read launcher {launch_sh}: {e}']
    if not windows:
        if 'MSYS2_ARG_CONV_EXCL' in content:
            return [f'{launch_sh}: the Unix launcher sets MSYS2_ARG_CONV_EXCL']
        return []

    markers = ('[ -e "$arg" ]', 'export MSYS2_ARG_CONV_EXCL=')
    errors = [
        f'{launch_sh}: expected {marker!r} exactly once, found {content.count(marker)}'
        for marker in markers
        if content.count(marker) != 1
    ]
    starts = [index for index in range(len(content)) if content.startswith('exec claude ', index)]
    if not starts:
        errors.append(f'{launch_sh}: no line starts claude')
    elif not errors and any(start < content.index(markers[-1]) for start in starts):
        errors.append(f'{launch_sh}: claude starts before slash arguments are listed in MSYS2_ARG_CONV_EXCL')
    return errors


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


def validate_resolved_config(profile_dir: Path, expected_snapshot: dict[str, Any]) -> list[str]:
    """Validate the resolved-config.yaml a run writes beside its manifest.

    Validates:
    - The file exists and parses as a YAML mapping
    - command-names is absent (the snapshot names what a profile installs,
      never which profile)
    - The content equals the expected snapshot, null-as-delete entries of
      user-settings, global-config and os-env-variables, hooks and
      components included
    - Its sha256 equals the config_digest the manifest beside it records

    Args:
        profile_dir: The profile directory holding manifest.json and
            resolved-config.yaml
        expected_snapshot: resolved_config_snapshot() of the configuration
            the run installed, after component selection

    Returns:
        List of error strings (empty if validation passes)
    """
    import yaml

    from scripts.setup_environment import MANIFEST_FILENAME
    from scripts.setup_environment import RESOLVED_CONFIG_FILENAME
    from scripts.setup_environment import config_digest_of

    resolved_path = profile_dir / RESOLVED_CONFIG_FILENAME
    if not resolved_path.is_file():
        return [f'{resolved_path} does not exist']
    text = resolved_path.read_text(encoding='utf-8')
    try:
        content = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return [f'{resolved_path} is not valid YAML: {exc}']
    if not isinstance(content, dict):
        return [f'{resolved_path} does not hold a mapping']
    errors: list[str] = []
    if 'command-names' in content:
        errors.append(f'{RESOLVED_CONFIG_FILENAME} carries command-names, which names the profile, not the configuration')
    errors.extend(
        f'{RESOLVED_CONFIG_FILENAME} key {key!r}: expected {expected_snapshot.get(key)!r}, got {content.get(key)!r}'
        for key in sorted(set(content) | set(expected_snapshot))
        if content.get(key) != expected_snapshot.get(key)
    )
    manifest, manifest_errors = validate_json_file(profile_dir / MANIFEST_FILENAME)
    if manifest_errors:
        errors.extend(manifest_errors)
    elif manifest is not None and manifest.get('config_digest') != config_digest_of(text):
        errors.append(f'Manifest config_digest does not equal the sha256 of {RESOLVED_CONFIG_FILENAME}')
    return errors


def _link_record_errors(link: object, yaml_values: object, config: dict[str, Any]) -> list[str]:
    """Validate the manifest's link record and recorded link values against the configuration's link keys.

    A configuration that declares link-dirs expects a record naming those
    entries (all expands to every linkable entry) with the yaml origin, and
    the link-from source with the yaml origin when the key is declared (base
    with the default origin otherwise); a configuration without link-dirs
    expects None. yaml_values must carry the configuration's own link-dirs
    entries and link-from value, None for an absent key.

    Args:
        link: The manifest's link field.
        yaml_values: The manifest's yaml_values field.
        config: The configuration the profile was installed from.

    Returns:
        List of error strings (empty if the record matches).
    """
    from scripts.setup_environment import LINKABLE_PROFILE_DIRS
    from scripts.setup_environment import parse_link_dirs

    raw_dirs = config.get('link-dirs')
    expected_dirs, parse_errors = parse_link_dirs(raw_dirs, 'link-dirs') if raw_dirs is not None else ([], [])
    if parse_errors:
        return [f'Golden link-dirs is invalid: {parse_errors}']
    raw_source = config.get('link-from')
    errors: list[str] = []
    if isinstance(yaml_values, dict):
        expected_values = {
            'link_dirs': expected_dirs if raw_dirs is not None else None,
            'link_from': str(raw_source) if raw_source is not None else None,
        }
        recorded_values = {key: yaml_values.get(key) for key in expected_values}
        if recorded_values != expected_values:
            errors.append(f'Manifest yaml_values link keys: expected {expected_values!r}, got {recorded_values!r}')
    if not expected_dirs:
        return errors if link is None else [*errors, f'Manifest link: expected None, got {link!r}']
    if not isinstance(link, dict):
        return [*errors, f'Manifest link: expected a record for {expected_dirs}, got {link!r}']
    if set(link) != {'dirs', 'source', 'origins'}:
        errors.append(f'Manifest link: expected dirs, source and origins, got {sorted(link)}')
        return errors
    if link['dirs'] != expected_dirs:
        errors.append(f"Manifest link.dirs: expected {expected_dirs}, got {link['dirs']!r}")
    if any(entry not in LINKABLE_PROFILE_DIRS for entry in link['dirs']):
        errors.append(f"Manifest link.dirs names an unknown entry: {link['dirs']!r}")
    expected_source = str(raw_source or 'base')
    if link['source'] != expected_source:
        errors.append(f"Manifest link.source: expected {expected_source!r}, got {link['source']!r}")
    expected_origins = {'dirs': 'yaml', 'source': 'yaml' if raw_source is not None else 'default'}
    if link['origins'] != expected_origins:
        errors.append(f"Manifest link.origins: expected {expected_origins!r}, got {link['origins']!r}")
    return errors


def validate_manifest(path: Path, config: dict[str, Any]) -> list[str]:
    """Validate manifest.json structure and content.

    Validates the installation manifest file that records configuration
    metadata for one toolbox-managed profile.

    Validates:
    - File exists and is valid JSON
    - The field set is exactly EXPECTED_JSON_KEYS['manifest']
    - version matches config['version'] if present
    - claude_code_version matches the normalized config pin ('latest' and an
      absent key both normalize to None)
    - config_source_type is one of: url, local, repo
    - config_identity is the identity of config_source, and config_digest
      is the sha256 of the resolved-config.yaml beside the manifest, which
      every written manifest has (a None digest or a missing file is an
      error)
    - command_names and name match the profile shape: the primary command
      name and a non-empty list for an isolated profile, None and an empty
      list for the base profile
    - origins maps command_names and components to an origin, yaml_values
      and the written records have their declared shapes, yaml_values
      carries the configuration's own link-dirs and link-from, and link
      matches the configuration's link keys with the yaml origins (None
      without link-dirs)
    - installed_at is a valid ISO timestamp string

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

    expected_fields = EXPECTED_JSON_KEYS['manifest']
    errors = [
        f"Manifest missing required field: '{field}'"
        for field in expected_fields
        if field not in data
    ]
    errors.extend(
        f"Manifest has unexpected field: '{field}'"
        for field in data
        if field not in expected_fields
    )

    if errors:
        return errors  # Cannot validate content without the expected field set

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

    # Claude Code version pin check: the manifest records the NORMALIZED pin,
    # so 'latest' and an absent key both land as None.
    raw_pin = config.get('claude-code-version')
    pin_str = str(raw_pin).strip() if raw_pin is not None else ''
    expected_pin = None if not pin_str or pin_str.lower() == 'latest' else pin_str
    if data['claude_code_version'] != expected_pin:
        errors.append(
            f'Manifest claude_code_version: expected {expected_pin!r}, '
            f"got {data['claude_code_version']!r}",
        )

    # config_source_type validation
    valid_types = {'url', 'local', 'repo'}
    if data['config_source_type'] not in valid_types:
        errors.append(
            f"Manifest config_source_type: expected one of {valid_types}, "
            f"got {data['config_source_type']!r}",
        )

    # Identity and digest: the identity derives from the recorded source, the
    # digest from the resolved-config.yaml written beside the manifest
    from scripts.setup_environment import RESOLVED_CONFIG_FILENAME
    from scripts.setup_environment import config_digest_of
    from scripts.setup_environment import config_identity_of

    expected_identity = config_identity_of(str(data['config_source']))
    if data['config_identity'] != expected_identity:
        errors.append(
            f"Manifest config_identity: expected {expected_identity!r}, got {data['config_identity']!r}",
        )
    resolved_path = path.parent / RESOLVED_CONFIG_FILENAME
    if not resolved_path.is_file():
        errors.append(f'{RESOLVED_CONFIG_FILENAME} is absent beside the manifest')
    elif data['config_digest'] is None:
        errors.append(f'Manifest config_digest is None although {RESOLVED_CONFIG_FILENAME} exists')
    elif data['config_digest'] != config_digest_of(resolved_path.read_text(encoding='utf-8')):
        errors.append(f'Manifest config_digest does not match {RESOLVED_CONFIG_FILENAME}')

    # Remembered values and their origins
    origins = data['origins']
    if not isinstance(origins, dict) or set(origins) != {'command_names', 'components'}:
        errors.append(f'Manifest origins: expected command_names and components, got {origins!r}')
    else:
        if origins['command_names'] not in ('cli', 'env', 'yaml', 'default', None):
            errors.append(f"Manifest origins.command_names: unexpected value {origins['command_names']!r}")
        if origins['components'] not in ('cli', 'env', 'yaml'):
            errors.append(f"Manifest origins.components: unexpected value {origins['components']!r}")
    components = data['components']
    if components is not None and (
        not isinstance(components, dict) or set(components) != {'select', 'with', 'without'}
    ):
        errors.append(f'Manifest components: expected None or the three selector values, got {components!r}')
    if not isinstance(data['yaml_values'], dict):
        errors.append(f"Manifest yaml_values: expected an object, got {data['yaml_values']!r}")
    errors.extend(_link_record_errors(data['link'], data['yaml_values'], config))
    record_keys = ('machine_wide_destinations', 'os_env_written', 'settings_keys_written', 'mcp_servers', 'files_written')
    errors.extend(
        f'Manifest {record_key}: expected a list, got {data[record_key]!r}'
        for record_key in record_keys
        if not isinstance(data[record_key], list)
    )
    destinations = data['machine_wide_destinations'] if isinstance(data['machine_wide_destinations'], list) else []
    errors.extend(
        f'Manifest machine_wide_destinations entry: expected dest, source and sha256, got {record!r}'
        for record in destinations
        if not isinstance(record, dict) or set(record) != {'dest', 'source', 'sha256'}
    )
    servers = data['mcp_servers'] if isinstance(data['mcp_servers'], list) else []
    errors.extend(
        f'Manifest mcp_servers entry: expected name and scopes, got {record!r}'
        for record in servers
        if not isinstance(record, dict) or set(record) != {'name', 'scopes'}
    )

    # command_names validation: an isolated profile lists its command names,
    # the base profile lists none.
    cmd_names = config.get('command-names')
    is_isolated = isinstance(cmd_names, list) and bool(cmd_names)
    if not isinstance(data['command_names'], list):
        errors.append('Manifest command_names: expected list')
    elif is_isolated and len(data['command_names']) == 0:
        errors.append('Manifest command_names: expected non-empty list for an isolated profile')
    elif not is_isolated and len(data['command_names']) != 0:
        errors.append(
            f"Manifest command_names: expected empty list for the base profile, "
            f"got {data['command_names']!r}",
        )

    # installed_at must be a string (ISO timestamp)
    if not isinstance(data['installed_at'], str):
        errors.append(
            f"Manifest installed_at: expected ISO timestamp string, "
            f"got {type(data['installed_at']).__name__}",
        )

    # name should match the primary command name, or be None for the base profile
    expected_name = cmd_names[0] if isinstance(cmd_names, list) and cmd_names else None
    if data['name'] != expected_name:
        errors.append(
            f"Manifest name: expected {expected_name!r}, got {data['name']!r}",
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
        else:
            errors.extend(
                validate_merged_value(content[key], expected_value, f'~/.claude.json key {key!r}'),
            )

    return errors


def _validate_false_control_in_claude_json(
    home_dir: Path, key: str, pinned: bool, command_name: str | None,
) -> list[str]:
    """Validate a pin's false-valued control in the .claude.json a run writes.

    A run writes exactly one .claude.json: ~/.claude/{command_name}/.claude.json
    for an isolated run, ~/.claude.json for a base run. When pinned, that
    file must hold ``key: false``; when unpinned, it must not hold
    ``key: false``. An isolated run must also leave the base file alone: a
    pinned isolated run that created or changed ~/.claude.json's control is
    an error.

    Args:
        home_dir: Isolated home directory path.
        key: The .claude.json control key (autoUpdates or
            autoInstallIdeExtension).
        pinned: Whether a specific version is pinned.
        command_name: Command name for an isolated run, or None for a base run.

    Returns:
        List of error strings (empty = all validations passed).
    """
    errors: list[str] = []
    target = home_dir / '.claude' / command_name / '.claude.json' if command_name else home_dir / '.claude.json'

    if target.exists():
        data, json_errors = validate_json_file(target)
        errors.extend(json_errors)
        if data is not None:
            if pinned:
                if key not in data:
                    errors.append(f'Pinned version: {key} missing from {target}')
                elif data[key] is not False:
                    errors.append(f'Pinned version: {key} in {target} should be false, got {data[key]!r}')
            elif data.get(key) is False:
                errors.append(f'Latest/absent version: {key}=false should not be injected into {target}')
    elif pinned:
        errors.append(f'Pinned version: {target} does not exist')

    if command_name and pinned:
        base_json = home_dir / '.claude.json'
        if base_json.exists():
            data, json_errors = validate_json_file(base_json)
            errors.extend(json_errors)
            if data is not None and data.get(key) is False:
                errors.append(f'Isolated run wrote {key}: false into the base {base_json}')

    return errors


def validate_auto_update_controls(
    home_dir: Path, pinned: bool, command_name: str | None = None,
) -> list[str]:
    """Validate the autoUpdates control in the .claude.json a run writes.

    Covers the global-config autoUpdates write only; the
    env.DISABLE_AUTOUPDATER and env.DISABLE_UPDATES contribution is asserted
    in test_auto_update.py (in memory) and test_profile_settings_routing.py
    (settings.json). See _validate_false_control_in_claude_json() for the
    single-file contract.

    Args:
        home_dir: Isolated home directory path
        pinned: Whether a specific version is pinned
        command_name: Command name for an isolated run, or None

    Returns:
        List of error strings (empty = all validations passed)
    """
    return _validate_false_control_in_claude_json(home_dir, 'autoUpdates', pinned, command_name)


def validate_ide_extension_controls(
    home_dir: Path, pinned: bool, command_name: str | None = None,
) -> list[str]:
    """Validate the autoInstallIdeExtension control in the .claude.json a run writes.

    Covers the global-config autoInstallIdeExtension write only; the
    env.CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL settings.json contribution is
    validated by validate_settings. See
    _validate_false_control_in_claude_json() for the single-file contract.

    Args:
        home_dir: Isolated home directory path
        pinned: Whether a specific version is pinned
        command_name: Command name for an isolated run, or None

    Returns:
        List of error strings (empty = all validations passed)
    """
    return _validate_false_control_in_claude_json(home_dir, 'autoInstallIdeExtension', pinned, command_name)


def validate_json_arrays(
    path: Path,
    expected: dict[tuple[str, ...], list[object] | None],
) -> list[str]:
    """Validate the arrays a JSON file holds at the given key paths.

    Each expected array is compared exactly, element order included: a
    writer that unions arrays keeps the elements the file already held
    first and appends only the elements it did not hold, so the order
    tells a union apart from a replacement. A ``None`` expectation
    requires the final key to be absent (deleted by a YAML null).

    Args:
        path: Path to the JSON file to inspect.
        expected: Mapping from a key path (one tuple element per nesting
            level, so keys containing dots stay unambiguous) to the exact
            expected array, or ``None`` when the key must be absent.

    Returns:
        List of error strings (empty if every key path matches).
    """
    data, errors = validate_json_file(path)
    if data is None:
        return errors

    for key_path, expected_value in expected.items():
        label = f'{path.name}:{".".join(key_path)}'
        node: object = data
        for key in key_path[:-1]:
            if not isinstance(node, dict) or key not in node:
                node = None
                break
            node = cast(dict[str, object], node)[key]
        if not isinstance(node, dict):
            errors.append(f'{label}: parent object missing')
            continue
        parent = cast(dict[str, object], node)
        final_key = key_path[-1]
        if expected_value is None:
            if final_key in parent:
                errors.append(f'{label}: expected ABSENT, got {parent[final_key]!r}')
            continue
        if final_key not in parent:
            errors.append(f'{label}: missing, expected {expected_value!r}')
        elif parent[final_key] != expected_value:
            errors.append(f'{label}: expected {expected_value!r}, got {parent[final_key]!r}')

    return errors


def validate_env_loader_files(
    claude_dir: Path,
    os_env_vars: dict[str, str | None],
    command_name: str | None = None,
    *,
    expect_fish: bool = False,
) -> list[str]:
    """Validate env loader files exist with correct content.

    Checks that generate_env_loader_files() produced the expected shell-specific
    loader files: an export line for every non-None os-env-variables entry and
    an unset line for every None (deletion) entry, in each shell's syntax.

    Validates:
    - Per-command env.sh exists in ~/.claude/{cmd}/ (when command_name provided)
    - Per-command env.fish is validated whenever it exists, and required when
      expect_fish is set (the generator writes it only when fish is installed)
    - File content contains correct export syntax for each shell type
    - None-valued (deletion) variables are rendered as unset lines, never exports
    - Header comment is present

    Args:
        claude_dir: Path to the ~/.claude directory
        os_env_vars: OS env vars dict from config (None values = deletions)
        command_name: Command name for per-command file checks, or None
        expect_fish: Whether env.fish must exist (fish was detected during the run)

    Returns:
        List of error strings (empty if validation passes)
    """
    errors: list[str] = []

    # Determine which vars are exported and which are unset
    active_vars = {k: str(v) for k, v in os_env_vars.items() if v is not None}
    deletion_vars = [k for k, v in os_env_vars.items() if v is None]

    if not os_env_vars:
        return errors

    # --- Per-command files ---
    if command_name:
        cmd_dir = claude_dir / command_name
        cmd_sh = cmd_dir / 'env.sh'
        if not cmd_sh.exists():
            errors.append(f'Per-command env loader not found: {cmd_sh}')
        else:
            sh_content = cmd_sh.read_text(encoding='utf-8')
            errors.extend(_validate_sh_loader_content(sh_content, active_vars, deletion_vars, 'env.sh'))

        cmd_fish = cmd_dir / 'env.fish'
        if cmd_fish.exists():
            fish_content = cmd_fish.read_text(encoding='utf-8')
            errors.extend(_validate_fish_loader_content(fish_content, active_vars, deletion_vars, 'env.fish'))
        elif expect_fish:
            errors.append(f'Per-command Fish env loader not found although fish is installed: {cmd_fish}')

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
        deletion_vars: Variable names that must appear as unset lines, never exports
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

    # Deletion vars are unset lines and never exports
    errors.extend(
        f'{filename}: deletion var {name} must not be exported'
        for name in deletion_vars
        if f'export {name}=' in content
    )
    errors.extend(
        f'{filename}: missing unset line for deletion var {name}'
        for name in deletion_vars
        if f'unset {name}\n' not in content
    )

    return errors


def _validate_fish_loader_content(
    content: str,
    active_vars: dict[str, str],
    deletion_vars: list[str],
    filename: str,
) -> list[str]:
    """Validate Fish env loader file content.

    Args:
        content: File content
        active_vars: Variables that should be present (name -> value, non-None only)
        deletion_vars: Variable names that must appear as erase lines, never exports
        filename: Filename for error messages

    Returns:
        List of error strings
    """
    errors: list[str] = []

    # Header check
    if not content.startswith('# Auto-generated by claude-code-toolbox'):
        errors.append(f'{filename}: missing header comment')

    # Each active var should have a global export line carrying its value
    errors.extend(
        f'{filename}: missing set -gx for {name}'
        for name, value in active_vars.items()
        if f'set -gx {name} "{value}"\n' not in content
    )

    # Deletion vars are guarded erase lines and never exports
    errors.extend(
        f'{filename}: deletion var {name} must not be exported'
        for name in deletion_vars
        if f'set -gx {name} ' in content
    )
    errors.extend(
        f'{filename}: missing erase line for deletion var {name}'
        for name in deletion_vars
        if f'set -q {name}; and set -e {name}\n' not in content
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
        deletion_vars: Variable names that must appear as Remove-Item lines, never assignments
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

    # Deletion vars are Remove-Item lines and never assignments
    errors.extend(
        f'{filename}: deletion var {name} must not be assigned'
        for name in deletion_vars
        if f'$env:{name} =' in content
    )
    errors.extend(
        f'{filename}: missing Remove-Item line for deletion var {name}'
        for name in deletion_vars
        if f'Remove-Item -Path Env:{name} -ErrorAction SilentlyContinue' not in content
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
        deletion_vars: Variable names that must appear as empty SET lines, never with a value
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

    # Deletion vars are empty SET lines (which delete the variable), never valued ones
    errors.extend(
        f'{filename}: missing SET "{name}=" line for deletion var {name}'
        for name in deletion_vars
        if f'SET "{name}="\n' not in content
    )

    return errors


def validate_launcher_env_sourcing(
    launcher_path: Path,
) -> list[str]:
    """Validate where a generated script applies the profile's env loader.

    Only launch.sh sources a loader, inside the bash process that runs
    Claude Code. A PowerShell or CMD launcher runs in the calling shell
    ($env: is process-wide; a batch file executes in the cmd.exe that runs
    it), so a loader sourced there would stay in that shell after the
    session ends.

    Validates:
    - Bash/POSIX launchers contain file-existence guard and source command
    - PowerShell launchers reference no env.ps1 and no $envFile
    - CMD batch launchers reference no env.cmd and no ENV_FILE, and open
      with setlocal so their own variables stay out of the calling shell

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
        # PowerShell: a dot-sourced loader would change the calling shell
        errors.extend(
            f'{launcher_path.name}: references {fragment}; a PowerShell launcher applies no loader'
            for fragment in ('env.ps1', '$envFile')
            if fragment in content
        )
    elif suffix == '.cmd':
        # CMD batch: a called loader would change the calling shell
        errors.extend(
            f'{launcher_path.name}: references {fragment}; a CMD launcher applies no loader'
            for fragment in ('env.cmd', 'ENV_FILE')
            if fragment in content
        )
        if not content.startswith('@echo off\nsetlocal\n'):
            errors.append(f'{launcher_path.name}: does not open with setlocal, so its variables reach the calling shell')
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


def validate_hooks_in_settings_json(path: Path, config: dict[str, Any]) -> list[str]:
    """Validate hooks structure in settings.json (no-command-names flow).

    Reads the settings.json file and validates the hooks structure against
    the YAML hooks configuration. Delegates structural validation to the
    existing _validate_hooks_structure helper.

    Args:
        path: Path to settings.json file
        config: Hooks configuration dictionary (the 'hooks' section from YAML)

    Returns:
        List of error strings (empty if validation passes)
    """
    errors: list[str] = []
    data, file_errors = validate_json_file(path)
    if file_errors:
        return file_errors
    assert data is not None
    hooks_data = data.get('hooks', {})
    if not hooks_data:
        errors.append('settings.json missing hooks key')
        return errors
    errors.extend(_validate_hooks_structure(hooks_data, config))
    return errors


def validate_hook_helpers_installed(hooks_dir: Path, config: dict[str, Any]) -> list[str]:
    """Validate hooks.helpers land beside the hook scripts.

    Every helper declared in the YAML must exist under the hooks directory
    the hook scripts themselves install into, so a script reaches it as a
    sibling import.

    Args:
        hooks_dir: Directory hook files and helpers install into
        config: Full YAML configuration dictionary

    Returns:
        List of error strings (empty if validation passes)
    """
    from scripts import setup_environment

    errors: list[str] = []
    hooks = config.get('hooks') or {}
    for helper in hooks.get('helpers') or []:
        basename = setup_environment._hook_file_basename(str(helper))
        helper_path = hooks_dir / basename
        if not helper_path.is_file():
            errors.append(f'Hook helper {basename!r} missing from {hooks_dir}')
    return errors


def validate_hook_helpers_absent_from_json(
    hooks_json: dict[str, Any],
    status_line: dict[str, Any] | None,
    config: dict[str, Any],
) -> list[str]:
    """Validate no helper basename reaches the generated hooks or statusLine.

    Helpers are imported by hook scripts, never launched by Claude Code, so
    their names must not appear in any generated command or status-line entry.

    Args:
        hooks_json: The generated hooks mapping (event name -> matcher groups)
        status_line: The generated statusLine entry, or None when absent
        config: Full YAML configuration dictionary

    Returns:
        List of error strings (empty if validation passes)
    """
    from scripts import setup_environment

    errors: list[str] = []
    hooks = config.get('hooks') or {}
    helper_names = [
        setup_environment._hook_file_basename(str(helper))
        for helper in hooks.get('helpers') or []
    ]
    if not helper_names:
        return errors

    rendered = json.dumps({'hooks': hooks_json, 'statusLine': status_line})
    errors.extend(
        f'Hook helper {basename!r} leaked into the generated hooks/statusLine JSON'
        for basename in helper_names
        if basename in rendered
    )
    return errors


def validate_selected_artifacts(
    config: dict[str, Any],
    components: list[dict[str, Any]],
    selected: list[str],
) -> list[str]:
    """Validate a component-filtered config against its selection.

    For every selector any component claims, the referenced item must be
    present in the filtered config iff at least one SELECTED component
    claims it. Presence is checked through the runtime identity computation
    so directory dests, hook ids, and hook file paths all resolve the same
    way the filter resolved them.

    Args:
        config: The config dict AFTER apply_component_selection().
        components: The component entries the selection was resolved from.
        selected: The selected component names.

    Returns:
        List of errors; empty when the filtered config matches the selection.
    """
    from scripts import setup_environment

    errors: list[str] = []
    selected_set = set(selected)
    claim_map: dict[tuple[str, str], set[str]] = {}
    for comp in components:
        name = str(comp.get('name', '')).strip()
        includes = comp.get('includes') or {}
        if not isinstance(includes, dict):
            continue
        for section, selectors in includes.items():
            for selector in selectors or []:
                claim_map.setdefault((section, str(selector).strip()), set()).add(name)

    for (section, selector), claimers in sorted(claim_map.items()):
        present = selector in setup_environment._component_section_identities(config, section)
        should_be_present = bool(claimers & selected_set)
        if should_be_present and not present:
            errors.append(
                f'{section}: selected item {selector!r} missing from filtered config '
                f'(claimed by {sorted(claimers)})',
            )
        elif not should_be_present and present:
            errors.append(
                f'{section}: deselected item {selector!r} still present in filtered config '
                f'(claimed by {sorted(claimers)})',
            )
    return errors


def validate_launcher_profile_spelling(
    profile_dir: Path,
    *,
    posix_dir: str,
    cmd_dir: str,
    powershell_parent: str,
    windows_launchers: bool,
    local_bin: Path | None = None,
    wrapper_names: tuple[str, ...] = (),
) -> list[str]:
    """Validate that launchers and wrappers name the profile directory.

    Every path a generated script reads -- the exported CLAUDE_CONFIG_DIR,
    config.json, mcp.json, the system prompt, the env.sh loader and launch.sh
    -- must be spelled from profile_dir: home-relative ($HOME, %USERPROFILE%,
    $env:USERPROFILE) when profile_dir lies below the home directory, absolute
    otherwise. No other home-relative path may appear, and no CMD or
    PowerShell script names a loader, because those run in the calling shell.

    Args:
        profile_dir: The profile directory the scripts must name.
        posix_dir: Its expected spelling inside a double-quoted bash string.
        cmd_dir: Its expected spelling inside a CMD ``set`` assignment.
        powershell_parent: The expected PowerShell expression of its parent.
        windows_launchers: Whether start.ps1 and start.cmd were generated.
        local_bin: Directory holding the global wrappers, when checked.
        wrapper_names: Command names whose Windows wrappers are checked.

    Returns:
        List of error strings (empty if validation passes)
    """
    errors: list[str] = []

    def read(path: Path) -> str | None:
        if not path.exists():
            errors.append(f'{path} not found')
            return None
        return path.read_text(encoding='utf-8')

    def expect(content: str, path: Path, fragments: list[str]) -> None:
        errors.extend(f'{path.name} lacks {fragment!r}' for fragment in fragments if fragment not in content)

    def expect_only_profile(content: str, path: Path, prefix: str, spelled: str) -> None:
        if not spelled.startswith(prefix):
            if prefix in content:
                errors.append(f'{path.name} names {prefix} although the profile lies outside the home directory')
        elif content.count(prefix) != content.count(spelled):
            errors.append(f'{path.name} names a {prefix} path other than the profile directory {spelled}')

    launch_sh = profile_dir / 'launch.sh'
    content = read(launch_sh)
    if content is not None:
        expect(content, launch_sh, [
            f'export CLAUDE_CONFIG_DIR="{posix_dir}"',
            f'ENV_FILE="{posix_dir}/env.sh"',
            f'"{posix_dir}/config.json"',
            f'MCP_CONFIG_PATH="{posix_dir}/mcp.json"',
        ])
        if 'PROMPT_PATH=' in content:
            expect(content, launch_sh, [f'PROMPT_PATH="{posix_dir}/prompts/'])
        expect_only_profile(content, launch_sh, '$HOME', posix_dir)

    def expect_no_loader(content: str, path: Path, loader: str) -> None:
        if loader in content:
            errors.append(f'{path.name} names {loader}, which would apply the loader to the calling shell')

    if windows_launchers:
        start_cmd = profile_dir / 'start.cmd'
        content = read(start_cmd)
        if content is not None:
            expect(content, start_cmd, [f'set "SCRIPT_WIN={cmd_dir}\\launch.sh"'])
            expect_no_loader(content, start_cmd, 'env.cmd')
            expect_only_profile(content, start_cmd, '%USERPROFILE%', cmd_dir)
        start_ps1 = profile_dir / 'start.ps1'
        content = read(start_ps1)
        if content is not None:
            leaf = f'(Join-Path $claudeUserDir "{profile_dir.name}")'
            expect(content, start_ps1, [
                f'$claudeUserDir = {powershell_parent}\n',
                f'{leaf} "launch.sh"',
            ])
            expect_no_loader(content, start_ps1, 'env.ps1')

    if local_bin is not None:
        for name in wrapper_names:
            cmd_wrapper = local_bin / f'{name}.cmd'
            content = read(cmd_wrapper)
            if content is not None:
                expect(content, cmd_wrapper, [f'set "SCRIPT_WIN={cmd_dir}\\launch.sh"'])
                expect_no_loader(content, cmd_wrapper, 'env.cmd')
                expect_only_profile(content, cmd_wrapper, '%USERPROFILE%', cmd_dir)
            ps1_wrapper = local_bin / f'{name}.ps1'
            content = read(ps1_wrapper)
            if content is not None:
                expect(content, ps1_wrapper, [f'& "{profile_dir / "start.ps1"}" @args'])
            bash_wrapper = local_bin / name
            content = read(bash_wrapper)
            if content is not None:
                expect(content, bash_wrapper, [f'exec "{posix_dir}/launch.sh" "$@"'])
                expect_only_profile(content, bash_wrapper, '$HOME', posix_dir)

    return errors


_ANSI_SEQUENCE = re.compile(r'\x1b\[[0-9;]*m')
_NPM_SHADOWING_MARKER = 'in the npm global prefix runs instead of the npm'


def _npm_shadowing_lines(
    prefix_version: str, prefix_dir: Path, bundled_version: str, bundled_dir: Path,
) -> list[str]:
    """The lines a run prints for an npm copy shadowing the bundled one, in order."""
    return [
        f'npm {prefix_version} {_NPM_SHADOWING_MARKER} {bundled_version} bundled with Node.js',
        f'Global prefix copy: {prefix_dir}',
        f'Bundled copy: {bundled_dir}',
        'To run the bundled copy, remove the global prefix copy: npm uninstall -g npm',
        f'Or update the global prefix copy to the bundled version: npm install -g npm@{bundled_version}',
    ]


def _missing_in_order(text: str, lines: list[str], where: str) -> list[str]:
    """Report each line that does not follow the previous one in the text."""
    errors: list[str] = []
    position = 0
    for line in lines:
        found = text.find(line, position)
        if found < 0:
            errors.append(f'{where}: missing (in order) {line!r}')
            continue
        position = found + len(line)
    return errors


def validate_npm_shadowing_report(
    output: str,
    *,
    prefix_version: str,
    prefix_dir: Path,
    bundled_version: str,
    bundled_dir: Path,
) -> list[str]:
    """Validate that a run reported an npm copy in the global prefix shadowing the bundled npm.

    Step 5 (the text between the Step 5 and Step 6 headers) must warn with
    both versions, both package directories and the commands that remove or
    update the prefix copy, and state that setup left both copies unchanged.
    The block that closes the run -- the success summary, or the errors block
    of a run that completed with errors -- must repeat every line.

    Args:
        output: The run's combined stdout and stderr.
        prefix_version: The version of the global-prefix copy.
        prefix_dir: The global-prefix copy's package directory.
        bundled_version: The version of the bundled npm.
        bundled_dir: The bundled npm's package directory.

    Returns:
        Every missing or misplaced line, empty when the report is complete.
    """
    text = _ANSI_SEQUENCE.sub('', output)
    lines = _npm_shadowing_lines(prefix_version, prefix_dir, bundled_version, bundled_dir)
    errors: list[str] = []
    step_start = text.find('Step 5: Checking Node.js installation')
    step_end = text.find('Step 6: Installing dependencies')
    if step_start < 0 or step_end < step_start:
        return [f'Step 5 and Step 6 headers not found in order in the output:\n{text}']
    step = text[step_start:step_end]
    errors.extend(_missing_in_order(step, lines, 'Step 5'))
    if f'WARN: {lines[0]}' not in step:
        errors.append(f'Step 5: the headline is not a warning: {lines[0]!r}')
    if 'Setup leaves both copies unchanged' not in step:
        errors.append('Step 5: missing the note that setup leaves both copies unchanged')
    closing = max(text.rfind('Setup Complete!'), text.rfind('Setup Completed with Errors'))
    if closing < step_end:
        errors.append('closing block not found after Step 6')
        return errors
    errors.extend(_missing_in_order(text[closing:], lines, 'closing block'))
    return errors


def validate_no_npm_shadowing_report(output: str) -> list[str]:
    """Validate that a run printed no npm shadowing warning anywhere.

    Args:
        output: The run's combined stdout and stderr.

    Returns:
        An error quoting each line that reports a shadowing npm.
    """
    text = _ANSI_SEQUENCE.sub('', output)
    return [
        f'unexpected npm shadowing report: {line.strip()!r}'
        for line in text.splitlines()
        if _NPM_SHADOWING_MARKER in line or 'npm uninstall -g npm' in line
    ]
