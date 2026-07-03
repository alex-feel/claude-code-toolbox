"""
Pydantic models for environment configuration validation.
Defines the schema for Claude Code environment YAML files.
"""

import re
from typing import Any
from typing import Literal
from typing import cast
from urllib.parse import urlparse

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator

# Type alias for MCP server scope - can be single value, list, or comma-separated
ScopeValue = str | list[str]
VALID_SCOPES = frozenset({'user', 'local', 'project', 'profile'})

# Keys that are NOT allowed in user-settings due to path resolution issues
# These keys are profile-specific and should be configured at root level
USER_SETTINGS_EXCLUDED_KEYS: frozenset[str] = frozenset({
    'hooks',       # Path resolution issues; profile-specific event handlers
    'statusLine',  # Path resolution issues; profile-specific display config
})

# Keys that are NOT allowed in global-config section
# OAuth credentials must not appear in version-controlled YAML files
GLOBAL_CONFIG_EXCLUDED_KEYS: frozenset[str] = frozenset({
    'oauthAccount',
})

# Model family markers whose presence (case-insensitive substring) in the model
# identifier indicates support for the extended effort levels: 'xhigh' is
# supported on Opus 4.7/4.8 and Fable 5; 'max' on Opus 4.6+, Sonnet 4.6+, and
# Fable 5. Substring matching covers aliases ('opus', 'fable'), full model IDs
# ('claude-fable-5'), and provider-prefixed IDs ('us.anthropic.claude-opus-4-8').
XHIGH_EFFORT_MODEL_MARKERS: tuple[str, ...] = ('opus', 'fable')
MAX_EFFORT_MODEL_MARKERS: tuple[str, ...] = ('opus', 'fable', 'sonnet')

# Valid values for the settings.json effortLevel key
EFFORT_LEVEL_VALUES: frozenset[str] = frozenset({'low', 'medium', 'high', 'xhigh', 'max'})

# Valid values for the settings.json permissions.defaultMode key.
# 'delegate' appears in the published JSON schema but not in the prose
# documentation; it is accepted to avoid rejecting valid configurations.
PERMISSIONS_DEFAULT_MODE_VALUES: frozenset[str] = frozenset({
    'default',
    'acceptEdits',
    'plan',
    'auto',
    'dontAsk',
    'bypassPermissions',
    'delegate',
})

# user-settings is raw settings.json content and uses camelCase keys.
# These kebab-case spellings are common mistakes carried over from the
# root-level YAML naming convention; each maps to its camelCase correction.
USER_SETTINGS_KEBAB_KEY_CORRECTIONS: dict[str, str] = {
    'always-thinking-enabled': 'alwaysThinkingEnabled',
    'company-announcements': 'companyAnnouncements',
    'effort-level': 'effortLevel',
    'env-variables': 'env',
}

# Nested permissions keys also use camelCase inside user-settings
PERMISSIONS_KEBAB_KEY_CORRECTIONS: dict[str, str] = {
    'default-mode': 'defaultMode',
    'additional-directories': 'additionalDirectories',
}

# Root-level YAML keys that are not settings.json keys and therefore
# never valid inside user-settings
USER_SETTINGS_ROOT_ONLY_KEYS: frozenset[str] = frozenset({
    'status-line',
    'os-env-variables',
})

# Keys that live in ~/.claude.json (global-config), not in settings.json;
# declaring them in user-settings would be a silent no-op at runtime
USER_SETTINGS_GLOBAL_ONLY_KEYS: frozenset[str] = frozenset({
    'autoUpdates',
    'installMethod',
    'autoConnectIde',
    'autoInstallIdeExtension',
    'externalEditorContext',
    'teammateDefaultModel',
    'oauthAccount',
})

# Keys that live in settings.json (user-settings), not in ~/.claude.json;
# declaring them in global-config would be a silent no-op at runtime
GLOBAL_CONFIG_SETTINGS_ONLY_KEYS: frozenset[str] = frozenset({
    'model',
    'permissions',
    'env',
    'attribution',
    'alwaysThinkingEnabled',
    'effortLevel',
    'companyAnnouncements',
    'statusLine',
    'hooks',
    'availableModels',
    'enforceAvailableModels',
})

# Environment variable names: letters, digits, underscores; no leading digit
ENV_VAR_NAME_PATTERN: re.Pattern[str] = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def _extract_basename(path_or_url: str) -> str:
    """Extract the basename from a URL or file path.

    Handles:
    - Full URLs: https://example.com/path/to/script.py -> script.py
    - Windows paths: C:\\Users\\script.py -> script.py
    - Unix paths: /home/user/script.py -> script.py
    - Plain filenames: script.py -> script.py

    Args:
        path_or_url: The URL or path to extract basename from.

    Returns:
        The basename (filename) without path components.
    """
    # Handle URLs by extracting path component
    if path_or_url.startswith(('http://', 'https://')):
        parsed = urlparse(path_or_url)
        path_or_url = parsed.path

    # Split on both / and \ to handle all cases
    parts = path_or_url.replace('\\', '/').split('/')
    return parts[-1] if parts else path_or_url


def _normalize_scope(scope_value: str | list[str] | None) -> list[str]:
    """Normalize scope value to a list of lowercase scope strings.

    Supports multiple input formats:
    - None -> ['user'] (default, backward compatible)
    - 'user' -> ['user'] (single string)
    - 'User' -> ['user'] (case normalization)
    - 'user, profile' -> ['user', 'profile'] (comma-separated string)
    - ['user', 'profile'] -> ['user', 'profile'] (list passthrough)
    - ['User', 'PROFILE'] -> ['user', 'profile'] (list with case normalization)

    Args:
        scope_value: The scope value to normalize.

    Returns:
        List of normalized scope strings.

    Raises:
        ValueError: If any scope value is invalid.
    """
    if scope_value is None:
        return ['user']

    if isinstance(scope_value, str):
        # Handle comma-separated string
        if ',' in scope_value:
            scopes = [s.strip().lower() for s in scope_value.split(',') if s.strip()]
        else:
            scopes = [scope_value.strip().lower()]
    else:
        # scope_value is list[str] after type narrowing (str and None already handled)
        scopes = [s.strip().lower() for s in scope_value if s.strip()]

    # Validate individual scope values
    for scope in scopes:
        if scope not in VALID_SCOPES:
            raise ValueError(
                f"Invalid scope '{scope}'. Valid scopes are: {sorted(VALID_SCOPES)}",
            )

    # Check for duplicates
    if len(scopes) != len(set(scopes)):
        raise ValueError(f'Duplicate scope values are not allowed: {scopes}')

    return scopes


def _validate_scope_combination(scopes: list[str]) -> tuple[bool, str | None]:
    """Validate scope combinations.

    Rules:
    - Single scope values always valid
    - Combined scopes MUST include 'profile' for meaningful combination
    - Pure non-profile combinations are INVALID (they overlap at runtime)
    - Profile + multiple non-profile scopes trigger a WARNING

    Args:
        scopes: List of normalized scope strings.

    Returns:
        Tuple of (is_valid, message_or_none):
        - False + message = ERROR description
        - True + message = WARNING
        - True + None = fully valid
    """
    if len(scopes) <= 1:
        return True, None

    # Combined scopes must include profile
    if 'profile' not in scopes:
        non_profile = [s for s in scopes if s != 'profile']
        return False, (
            f'Combined scopes {scopes} are invalid. '
            f'Non-profile scopes ({non_profile}) overlap at runtime. '
            "Include 'profile' scope for meaningful combination."
        )

    # Profile + multiple non-profile scopes: valid but warn
    non_profile = [s for s in scopes if s != 'profile']
    if len(non_profile) > 1:
        return True, (
            f'Combined scopes {scopes} include multiple non-profile scopes ({non_profile}). '
            'These scopes may overlap at runtime.'
        )

    return True, None


def _validate_effort_level_entry(effort_level: object, model: object) -> list[str]:
    """Validate the user-settings effortLevel value and its model support.

    The 'xhigh' level requires an Opus or Fable model; 'max' requires an
    Opus, Sonnet, or Fable model. The exact alias 'best' (which resolves to
    Fable 5 or the latest Opus model) satisfies both. Claude Code gracefully
    downgrades an unsupported level at runtime, but declaring one in the
    profile is almost always a configuration mistake, so it is rejected.

    Args:
        effort_level: The declared effortLevel value (non-null).
        model: The declared user-settings model value, or None when absent.

    Returns:
        List of error messages. Empty list if the entry is valid.
    """
    if effort_level not in EFFORT_LEVEL_VALUES:
        return [
            (
                f'user-settings.effortLevel must be one of '
                f'{sorted(EFFORT_LEVEL_VALUES)}, got {effort_level!r}.'
            ),
        ]

    if effort_level not in ('xhigh', 'max'):
        return []

    markers = XHIGH_EFFORT_MODEL_MARKERS if effort_level == 'xhigh' else MAX_EFFORT_MODEL_MARKERS
    families = 'Opus and Fable models' if effort_level == 'xhigh' else 'Opus, Sonnet, and Fable models'

    if not isinstance(model, str) or not model.strip():
        return [
            (
                f"user-settings.effortLevel '{effort_level}' requires user-settings.model "
                f'to be specified. This effort level is only available for {families}.'
            ),
        ]

    model_lower = model.lower()
    # The 'best' alias is matched exactly, not as a substring, so arbitrary
    # model names that merely contain 'best' are not accepted.
    if model_lower != 'best' and not any(marker in model_lower for marker in markers):
        return [
            (
                f"user-settings.effortLevel '{effort_level}' is only available for "
                f"{families}, but model is set to '{model}'. "
                "Use 'low', 'medium', or 'high' for other models."
            ),
        ]

    return []


def _validate_permissions_entry(permissions: object) -> list[str]:
    """Validate the structure of the user-settings permissions value.

    Known sub-keys are checked (camelCase naming, defaultMode enum, list
    shapes); unknown sub-keys pass through untouched for forward
    compatibility with new Claude Code permissions options.

    Args:
        permissions: The declared permissions value (non-null).

    Returns:
        List of error messages. Empty list if the value is valid.
    """
    if not isinstance(permissions, dict):
        return ['user-settings.permissions must be a mapping.']

    errors: list[str] = []
    permissions_dict = cast(dict[str, object], permissions)

    for kebab, camel in PERMISSIONS_KEBAB_KEY_CORRECTIONS.items():
        if kebab in permissions_dict:
            errors.append(
                f'user-settings.permissions uses camelCase keys: '
                f"use '{camel}' instead of '{kebab}'.",
            )

    default_mode = permissions_dict.get('defaultMode')
    if 'defaultMode' in permissions_dict and default_mode is not None and default_mode not in PERMISSIONS_DEFAULT_MODE_VALUES:
        errors.append(
            f'user-settings.permissions.defaultMode must be one of '
            f'{sorted(PERMISSIONS_DEFAULT_MODE_VALUES)}, got {default_mode!r}.',
        )

    for list_key in ('allow', 'deny', 'ask', 'additionalDirectories'):
        value = permissions_dict.get(list_key)
        if list_key in permissions_dict and value is not None:
            value_list = cast(list[object], value) if isinstance(value, list) else None
            if value_list is None or any(not isinstance(item, str) for item in value_list):
                errors.append(f'user-settings.permissions.{list_key} must be a list of strings.')

    return errors


def _validate_env_entry(env: object) -> list[str]:
    """Validate the structure of the user-settings env value.

    settings.json requires env to be a mapping of string names to string
    values. A null entry value is a deletion request and carries no content
    to check.

    Args:
        env: The declared env value (non-null).

    Returns:
        List of error messages. Empty list if the value is valid.
    """
    if not isinstance(env, dict):
        return ['user-settings.env must be a mapping of environment variable names to string values.']

    errors: list[str] = []
    for name, value in cast(dict[object, object], env).items():
        if not isinstance(name, str) or not ENV_VAR_NAME_PATTERN.match(name):
            errors.append(
                f'user-settings.env: invalid environment variable name {name!r}. '
                'Must start with letter or underscore, followed by letters, digits, or underscores.',
            )
            continue
        if value is None:
            continue
        if not isinstance(value, str):
            errors.append(
                f'user-settings.env.{name} must be a string '
                '(quote the value in YAML) or null to delete the variable.',
            )
        elif '\x00' in value:
            errors.append(f'user-settings.env.{name} value cannot contain null bytes.')

    return errors


def validate_user_settings_values(data: dict[str, object]) -> list[str]:
    """Validate known settings.json keys inside a user-settings mapping.

    user-settings is free-form: unknown keys pass through untouched so new
    Claude Code settings work without a toolbox update. Known built-in keys,
    however, are validated fail-fast, because Claude Code silently ignores
    malformed or misplaced entries at runtime and the misconfiguration would
    otherwise go unnoticed. A null value for any key is a deletion request
    and is always allowed.

    Checks:
    - Root-level YAML keys ('status-line', 'os-env-variables') are rejected.
    - Kebab-case spellings of known camelCase keys are rejected with the
      camelCase correction.
    - Keys that belong in global-config (~/.claude.json) are rejected.
    - Value shapes for model, env, permissions, attribution,
      alwaysThinkingEnabled, companyAnnouncements, and effortLevel
      (including the effortLevel/model support cross-check).

    Args:
        data: The user-settings mapping from YAML.

    Returns:
        List of error messages. Empty list if validation passes.
    """
    errors: list[str] = [
        f"Key '{key}' is not allowed in user-settings. "
        'It is a root-level YAML key, not a settings.json key.'
        for key in sorted(USER_SETTINGS_ROOT_ONLY_KEYS & set(data))
    ]

    errors.extend(
        f"Key '{kebab}' is not a settings.json key. "
        f"user-settings holds raw settings.json content with camelCase keys: use '{camel}' instead."
        for kebab, camel in USER_SETTINGS_KEBAB_KEY_CORRECTIONS.items()
        if kebab in data
    )

    errors.extend(
        f"Key '{key}' belongs in global-config (~/.claude.json), "
        'not in user-settings (settings.json).'
        for key in sorted(USER_SETTINGS_GLOBAL_ONLY_KEYS & set(data))
    )

    model = data.get('model')
    if 'model' in data and model is not None and (not isinstance(model, str) or not model.strip()):
        errors.append('user-settings.model must be a non-empty string.')

    env = data.get('env')
    if 'env' in data and env is not None:
        errors.extend(_validate_env_entry(env))

    permissions = data.get('permissions')
    if 'permissions' in data and permissions is not None:
        errors.extend(_validate_permissions_entry(permissions))

    attribution = data.get('attribution')
    if 'attribution' in data and attribution is not None:
        if not isinstance(attribution, dict):
            errors.append('user-settings.attribution must be a mapping.')
        else:
            attribution_dict = cast(dict[str, object], attribution)
            for sub in ('commit', 'pr'):
                value = attribution_dict.get(sub)
                if sub in attribution_dict and value is not None and not isinstance(value, str):
                    errors.append(
                        f'user-settings.attribution.{sub} must be a string '
                        '(empty string hides attribution).',
                    )

    always_thinking = data.get('alwaysThinkingEnabled')
    if 'alwaysThinkingEnabled' in data and always_thinking is not None and not isinstance(always_thinking, bool):
        errors.append('user-settings.alwaysThinkingEnabled must be a boolean.')

    announcements = data.get('companyAnnouncements')
    if 'companyAnnouncements' in data and announcements is not None:
        announcements_list = cast(list[object], announcements) if isinstance(announcements, list) else None
        if announcements_list is None or any(not isinstance(item, str) for item in announcements_list):
            errors.append('user-settings.companyAnnouncements must be a list of strings.')

    effort_level = data.get('effortLevel')
    if 'effortLevel' in data and effort_level is not None:
        errors.extend(_validate_effort_level_entry(effort_level, model))

    return errors


def validate_global_config_values(data: dict[str, object]) -> list[str]:
    """Validate known key placement inside a global-config mapping.

    global-config is free-form: unknown keys pass through untouched. Known
    settings.json keys, however, are rejected because ~/.claude.json is not
    a settings file and Claude Code would silently ignore them at runtime.

    Args:
        data: The global-config mapping from YAML.

    Returns:
        List of error messages. Empty list if validation passes.
    """
    errors: list[str] = []
    for key in sorted(GLOBAL_CONFIG_SETTINGS_ONLY_KEYS & set(data)):
        if key in ('statusLine', 'hooks'):
            root_key = 'status-line' if key == 'statusLine' else 'hooks'
            errors.append(
                f"Key '{key}' is not valid in global-config (~/.claude.json). "
                f"Configure it via the root-level '{root_key}' YAML key.",
            )
        else:
            errors.append(
                f"Key '{key}' is a settings.json key and is not valid in "
                'global-config (~/.claude.json). Move it to user-settings.',
            )
    return errors


class UserSettings(BaseModel):
    """User settings configuration holding raw settings.json content.

    Free-form model that accepts any keys supported by Claude Code's
    settings.json schema, using camelCase key names exactly as they appear
    on disk. Unknown keys pass through without validation for forward
    compatibility.

    Structural guards:
    - 'hooks' and 'statusLine' are excluded (profile-specific, configured
      via root-level YAML keys with dedicated download and path resolution).
    - Known built-in keys are validated fail-fast via
      validate_user_settings_values(): value shapes, camelCase naming, and
      section placement (settings.json vs ~/.claude.json).
    """

    model_config = ConfigDict(extra='allow')

    @model_validator(mode='before')
    @classmethod
    def check_excluded_keys(cls, data: dict[str, object]) -> dict[str, object]:
        """Validate that excluded keys are not present."""
        for key in USER_SETTINGS_EXCLUDED_KEYS:
            if key in data:
                raise ValueError(
                    f"Key '{key}' is not allowed in user-settings (profile-specific only). "
                    'Configure this in the root level of your environment YAML instead.',
                )
        return data

    @model_validator(mode='before')
    @classmethod
    def check_known_key_values(cls, data: dict[str, object]) -> dict[str, object]:
        """Validate values and placement of known built-in settings keys."""
        errors = validate_user_settings_values(data)
        if errors:
            raise ValueError('\n'.join(errors))
        return data


class GlobalConfig(BaseModel):
    """Global configuration for ~/.claude.json.

    Free-form model that accepts any keys supported by Claude Code's
    global configuration schema. Unknown keys pass through without
    validation for forward compatibility.

    Structural guards:
    - The OAuth credential key (oauthAccount) is rejected for non-null
      values to prevent credential exposure in version-controlled YAML
      files. Null values are allowed to support clearing authentication
      state.
    - Known settings.json keys are rejected via
      validate_global_config_values() because ~/.claude.json is not a
      settings file and misplaced keys are silent no-ops at runtime.
    """

    model_config = ConfigDict(extra='allow')

    @model_validator(mode='before')
    @classmethod
    def check_excluded_keys(cls, data: dict[str, object]) -> dict[str, object]:
        """Reject non-null values for excluded OAuth keys; null values are allowed for clearing auth state."""
        for key in GLOBAL_CONFIG_EXCLUDED_KEYS:
            if key in data and data[key] is not None:
                raise ValueError(
                    f"Key '{key}' cannot be set to a non-null value in global-config "
                    '(OAuth credentials). Set to null to clear authentication state, '
                    'or omit the key entirely.',
                )
        return data

    @model_validator(mode='before')
    @classmethod
    def check_known_key_placement(cls, data: dict[str, object]) -> dict[str, object]:
        """Reject known settings.json keys misplaced into global-config."""
        errors = validate_global_config_values(data)
        if errors:
            raise ValueError('\n'.join(errors))
        return data


# MCP Server Models


class MCPServerHTTP(BaseModel):
    """MCP server configuration with HTTP/SSE transport."""

    name: str = Field(..., description='Server name')
    scope: str | list[str] = Field('user', description='Scope of the server (user, local, project, profile, or combined)')
    transport: Literal['http', 'sse'] = Field(..., description='Transport type')
    url: str = Field(..., description='Server URL')
    header: str | None = Field(None, description='Optional authentication header')
    env: str | list[str] | None = Field(None, description='Optional environment variables (string or list)')

    @field_validator('scope')
    @classmethod
    def validate_scope(cls, v: str | list[str]) -> str | list[str]:
        """Validate and normalize scope value."""
        scopes = _normalize_scope(v)
        is_valid, message = _validate_scope_combination(scopes)
        if not is_valid:
            raise ValueError(message)
        # Return original format for backward compatibility (single string if single scope)
        return scopes[0] if len(scopes) == 1 else scopes


class MCPServerStdio(BaseModel):
    """MCP server configuration with stdio transport."""

    name: str = Field(..., description='Server name')
    scope: str | list[str] = Field('user', description='Scope of the server (user, local, project, profile, or combined)')
    command: str = Field(..., description='Command to execute')
    args: list[str] | None = Field(None, description='Optional argument list for the command')
    env: str | list[str] | None = Field(None, description='Optional environment variables (string or list)')

    @field_validator('scope')
    @classmethod
    def validate_scope(cls, v: str | list[str]) -> str | list[str]:
        """Validate and normalize scope value."""
        scopes = _normalize_scope(v)
        is_valid, message = _validate_scope_combination(scopes)
        if not is_valid:
            raise ValueError(message)
        # Return original format for backward compatibility (single string if single scope)
        return scopes[0] if len(scopes) == 1 else scopes


class HookEvent(BaseModel):
    """Hook event configuration.

    Supports four hook types matching the official Claude Code hooks specification:
    - command: Executes a shell command (requires 'command' field)
    - http: Sends HTTP POST request (requires 'url' field)
    - prompt: Uses single-turn LLM evaluation (requires 'prompt' field)
    - agent: Spawns a subagent with tool access (requires 'prompt' field)
    """

    model_config = ConfigDict(populate_by_name=True)

    event: str = Field(..., description='Event name (e.g., PreToolUse, PostToolUse, Notification)')
    matcher: str | None = Field('', description='Regex pattern for matching')
    type: Literal['command', 'http', 'prompt', 'agent'] = Field(
        'command',
        description='Hook type: command, http, prompt, or agent',
    )

    # Common fields (all hook types)
    if_condition: str | None = Field(
        None,
        alias='if',
        description='Permission rule syntax filter for when hook runs (e.g., "Bash(git *)", "Edit(*.ts)")',
    )
    status_message: str | None = Field(
        None,
        alias='status-message',
        description='Custom spinner message displayed while hook runs',
    )
    once: bool | None = Field(
        None,
        description='If true, runs only once per session then is removed (skills only)',
    )
    timeout: int | None = Field(
        None,
        description='Timeout in seconds (default varies by type: 600 for command, 30 for prompt, 60 for agent)',
    )

    # Command hook fields
    command: str | None = Field(
        None,
        description='Command to execute (required for command hooks)',
    )
    config: str | None = Field(
        None,
        description='Optional config file reference to pass as argument to hook command',
    )
    async_execution: bool | None = Field(
        None,
        alias='async',
        description='If true, runs command in background without blocking',
    )
    shell: Literal['bash', 'powershell'] | None = Field(
        None,
        description='Shell to use for command execution: "bash" (default) or "powershell"',
    )

    # HTTP hook fields
    url: str | None = Field(
        None,
        description='URL to send HTTP POST request to (required for http hooks)',
    )
    headers: dict[str, str] | None = Field(
        None,
        description='Additional HTTP headers as key-value pairs. Values support $VAR_NAME env var interpolation',
    )
    allowed_env_vars: list[str] | None = Field(
        None,
        alias='allowed-env-vars',
        description='Environment variable names permitted for interpolation into header values',
    )

    # Prompt/Agent hook fields
    prompt: str | None = Field(
        None,
        description='Prompt text for LLM evaluation (required for prompt and agent hooks)',
    )
    model: str | None = Field(
        None,
        description='Model to use for prompt or agent hook evaluation',
    )

    @model_validator(mode='after')
    def validate_hook_type_fields(self) -> 'HookEvent':
        """Validate that fields match the hook type per official Claude Code spec.

        Field Matrix:
        | Field            | command   | http       | prompt    | agent     |
        |------------------|-----------|------------|-----------|-----------|
        | command          | REQUIRED  | FORBIDDEN  | FORBIDDEN | FORBIDDEN |
        | config           | Optional  | FORBIDDEN  | FORBIDDEN | FORBIDDEN |
        | async            | Optional  | FORBIDDEN  | FORBIDDEN | FORBIDDEN |
        | shell            | Optional  | FORBIDDEN  | FORBIDDEN | FORBIDDEN |
        | url              | FORBIDDEN | REQUIRED   | FORBIDDEN | FORBIDDEN |
        | headers          | FORBIDDEN | Optional   | FORBIDDEN | FORBIDDEN |
        | allowed-env-vars | FORBIDDEN | Optional   | FORBIDDEN | FORBIDDEN |
        | prompt           | FORBIDDEN | FORBIDDEN  | REQUIRED  | REQUIRED  |
        | model            | FORBIDDEN | FORBIDDEN  | Optional  | Optional  |

        Returns:
            The validated HookEvent instance.

        Raises:
            ValueError: If field requirements are not met for the hook type.
        """
        # Fields exclusive to each type group (typed as object for type checker compatibility)
        _command_only_fields: dict[str, object] = {
            'command': self.command,
            'config': self.config,
            'async': self.async_execution,
            'shell': self.shell,
        }
        _http_only_fields: dict[str, object] = {
            'url': self.url,
            'headers': self.headers,
            'allowed-env-vars': self.allowed_env_vars,
        }
        _prompt_agent_fields: dict[str, object] = {
            'prompt': self.prompt,
            'model': self.model,
        }

        if self.type == 'command':
            if not self.command:
                raise ValueError(
                    "Hook type 'command' requires 'command' field. "
                    "Either provide a command or change type to 'http', 'prompt', or 'agent'.",
                )
            for field_name, value in _http_only_fields.items():
                if value is not None:
                    raise ValueError(
                        f"Hook type 'command' cannot have '{field_name}' field. "
                        f"Use type 'http' for HTTP webhook hooks.",
                    )
            if self.prompt is not None:
                raise ValueError(
                    "Hook type 'command' cannot have 'prompt' field. "
                    "Use type 'prompt' or 'agent' for LLM-based hooks.",
                )
            if self.model is not None:
                raise ValueError(
                    "Hook type 'command' cannot have 'model' field. "
                    "Use type 'prompt' or 'agent' for LLM-based hooks.",
                )

        elif self.type == 'http':
            if not self.url:
                raise ValueError(
                    "Hook type 'http' requires 'url' field. "
                    "Provide the URL to send the HTTP POST request to.",
                )
            for field_name, value in _command_only_fields.items():
                if value is not None:
                    raise ValueError(
                        f"Hook type 'http' cannot have '{field_name}' field. "
                        f"Use type 'command' for script-based hooks.",
                    )
            if self.prompt is not None:
                raise ValueError(
                    "Hook type 'http' cannot have 'prompt' field. "
                    "Use type 'prompt' or 'agent' for LLM-based hooks.",
                )
            if self.model is not None:
                raise ValueError(
                    "Hook type 'http' cannot have 'model' field. "
                    "Use type 'prompt' or 'agent' for LLM-based hooks.",
                )

        elif self.type == 'prompt':
            if not self.prompt:
                raise ValueError(
                    "Hook type 'prompt' requires 'prompt' field. "
                    "Either provide a prompt or change type to 'command'.",
                )
            for field_name, value in _command_only_fields.items():
                if value is not None:
                    raise ValueError(
                        f"Hook type 'prompt' cannot have '{field_name}' field. "
                        f"Use type 'command' for script-based hooks.",
                    )
            for field_name, value in _http_only_fields.items():
                if value is not None:
                    raise ValueError(
                        f"Hook type 'prompt' cannot have '{field_name}' field. "
                        f"Use type 'http' for HTTP webhook hooks.",
                    )

        elif self.type == 'agent':
            if not self.prompt:
                raise ValueError(
                    "Hook type 'agent' requires 'prompt' field. "
                    "Provide the prompt for the subagent evaluation.",
                )
            for field_name, value in _command_only_fields.items():
                if value is not None:
                    raise ValueError(
                        f"Hook type 'agent' cannot have '{field_name}' field. "
                        f"Use type 'command' for script-based hooks.",
                    )
            for field_name, value in _http_only_fields.items():
                if value is not None:
                    raise ValueError(
                        f"Hook type 'agent' cannot have '{field_name}' field. "
                        f"Use type 'http' for HTTP webhook hooks.",
                    )

        return self


class FileToDownload(BaseModel):
    """File download/copy configuration."""

    source: str = Field(..., description='URL or path to the file to download/copy')
    dest: str = Field(..., description='Destination path where the file will be saved')

    @field_validator('source', 'dest')
    @classmethod
    def validate_paths(cls, v: str) -> str:
        """Validate source and destination paths for security issues.

        Allows:
        - Full URLs (http://, https://)
        - Local absolute paths (C:\\, /, ~/...)
        - Local relative paths (./file, ../file, file)
        - Environment variables (%VAR%, $VAR)

        Prevents:
        - Empty paths
        - Paths with null bytes

        Args:
            v: Path string to validate.

        Returns:
            The validated path.

        Raises:
            ValueError: If path is empty or contains null bytes.
        """
        if not v or not v.strip():
            raise ValueError('Path cannot be empty')

        # Check for null bytes (security risk)
        if '\x00' in v:
            raise ValueError('Path cannot contain null bytes')

        return v


class Skill(BaseModel):
    """Skill configuration for Claude Code skills installation."""

    name: str = Field(..., min_length=1, description='Skill name/identifier')
    base: str = Field(..., min_length=1, description='Base URL or local path for skill files')
    files: list[str] = Field(..., min_length=1, description='List of files to download/copy')

    @field_validator('base')
    @classmethod
    def validate_base_path(cls, v: str) -> str:
        """Validate base path for security issues.

        Args:
            v: Base path string to validate.

        Returns:
            The validated base path.

        Raises:
            ValueError: If base path is empty or contains null bytes.
        """
        if not v or not v.strip():
            raise ValueError('base cannot be empty')
        if '\x00' in v:
            raise ValueError('base cannot contain null bytes')
        return v

    @field_validator('files')
    @classmethod
    def validate_files_list(cls, v: list[str]) -> list[str]:
        """Validate files list contains SKILL.md and no empty entries.

        Args:
            v: List of file paths to validate.

        Returns:
            The validated list of file paths.

        Raises:
            ValueError: If SKILL.md is missing, or any file is empty/contains null bytes.
        """
        if 'SKILL.md' not in v:
            raise ValueError('SKILL.md is required in the files list for every skill')
        for i, file_path in enumerate(v):
            if not file_path or not file_path.strip():
                raise ValueError(f'files[{i}] cannot be empty')
            if '\x00' in file_path:
                raise ValueError(f'files[{i}] cannot contain null bytes')
        return v


class StatusLine(BaseModel):
    """Status line configuration for custom status display."""

    file: str = Field(..., description='Script file path to download to ~/.claude/hooks/')
    padding: int | None = Field(None, description='Optional padding value for the status line')
    config: str | None = Field(
        None,
        description='Optional config file reference to download and append as command argument',
    )

    @field_validator('file')
    @classmethod
    def validate_file(cls, v: str) -> str:
        """Validate file path is not empty and has no null bytes."""
        if not v or not v.strip():
            raise ValueError('file cannot be empty')
        if '\x00' in v:
            raise ValueError('file cannot contain null bytes')
        return v

    @field_validator('config')
    @classmethod
    def validate_config(cls, v: str | None) -> str | None:
        """Validate config file path if provided."""
        if v is None:
            return v
        if not v or not v.strip():
            raise ValueError('config cannot be empty when specified')
        if '\x00' in v:
            raise ValueError('config cannot contain null bytes')
        return v


class Hooks(BaseModel):
    """Hooks configuration."""

    files: list[str] = Field(default_factory=lambda: [], description='Hook script files to download')
    events: list[HookEvent] = Field(default_factory=lambda: [], description='Hook event configurations')


class CommandDefaults(BaseModel):
    """Command launch configuration."""

    system_prompt: str | None = Field(
        None,
        alias='system-prompt',
        description='System prompt configuration (behavior depends on mode field)',
    )
    mode: Literal['append', 'replace'] = Field(
        'replace',
        description='System prompt mode: "append" adds to default prompt, "replace" replaces it entirely',
    )

    @field_validator('mode')
    @classmethod
    def validate_mode(cls, v: str) -> str:
        """Validate mode field has correct value."""
        if v not in ['append', 'replace']:
            raise ValueError('mode must be either "append" or "replace"')
        return v


class InheritEntry(BaseModel):
    """Structured entry for list-based inheritance with per-entry merge control.

    Specifies a configuration source and optional per-entry merge-keys that
    control how that entry's values compose with the accumulated base.
    merge-keys are a property of the relationship between the leaf config
    and the listed entry, not an intrinsic property of the listed config.

    Attributes:
        config: Configuration source (URL, file path, or repo name).
        merge_keys: Optional list of top-level keys to merge (extend) instead
            of replace when composing this entry with the accumulated base.
    """

    model_config = ConfigDict(extra='forbid', populate_by_name=True)

    config: str
    merge_keys: list[str] | None = Field(None, alias='merge-keys')

    @field_validator('config')
    @classmethod
    def validate_config(cls, v: str) -> str:
        """Validate config source is non-empty and contains no null bytes."""
        if not v or not v.strip():
            raise ValueError('config cannot be empty or whitespace-only')
        if '\x00' in v:
            raise ValueError('config cannot contain null bytes')
        return v

    @field_validator('merge_keys')
    @classmethod
    def validate_merge_keys(cls, v: list[str] | None) -> list[str] | None:
        """Validate merge-keys against the set of mergeable configuration keys."""
        if v is None:
            return v

        # Inline definition avoids circular import from setup_environment.py
        mergeable: frozenset[str] = frozenset({
            'dependencies', 'agents', 'slash-commands', 'rules', 'skills',
            'files-to-download', 'hooks', 'mcp-servers',
            'global-config', 'user-settings', 'os-env-variables',
        })
        invalid = [k for k in v if k not in mergeable]
        if invalid:
            raise ValueError(
                f'Invalid merge-keys: {invalid}. '
                f'Valid mergeable keys: {sorted(mergeable)}',
            )
        return v


class EnvironmentConfig(BaseModel):
    """Complete environment configuration model."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    name: str = Field(..., description='Display name for the environment')
    description: str | None = Field(
        None,
        description='Description of the environment configuration, shown in the installation summary.',
    )
    post_install_notes: str | None = Field(
        None,
        alias='post-install-notes',
        description='Notes displayed after successful installation. '
        'Supports multiline content via YAML literal block (|) or folded block (>) scalars.',
    )
    command_names: list[str] | None = Field(
        default_factory=lambda: [],
        alias='command-names',
        description='List of command names/aliases. First name is primary, others are aliases.',
    )
    base_url: str | None = Field(None, alias='base-url', description='Base URL for relative paths')
    dependencies: dict[str, list[str]] = Field(
        default_factory=lambda: {
            'common': list[str](),
            'windows': list[str](),
            'macos': list[str](),
            'linux': list[str](),
        },
        description='Platform-specific dependency commands',
    )
    agents: list[str] | None = Field(default_factory=lambda: [], description='Agent markdown files')
    mcp_servers: list[dict[str, Any]] | None = Field(
        default_factory=lambda: [],
        alias='mcp-servers',
        description='MCP server configurations',
    )
    slash_commands: list[str] | None = Field(
        default_factory=lambda: [],
        alias='slash-commands',
        description='Slash command files',
    )
    rules: list[str] | None = Field(
        default_factory=lambda: [],
        description='Rule markdown files placed in ~/.claude/rules/ (user-scope)',
    )
    skills: list[Skill] | None = Field(
        default_factory=lambda: [],
        description='Skill configurations for Claude Code skills',
    )
    files_to_download: list[FileToDownload] | None = Field(
        default_factory=lambda: [],
        alias='files-to-download',
        description='Files to download during environment setup',
    )
    hooks: Hooks | None = Field(None, description='Hook configurations')
    command_defaults: CommandDefaults | None = Field(
        None,
        alias='command-defaults',
        description='Command launch defaults',
    )
    status_line: StatusLine | None = Field(
        None,
        alias='status-line',
        description='Status line configuration with script file and optional padding',
    )
    install_nodejs: bool | None = Field(
        None,
        alias='install-nodejs',
        description='Whether to install Node.js LTS before processing dependencies (default: False)',
    )
    link_projects_dir: bool | None = Field(
        None,
        alias='link-projects-dir',
        description="When true (isolated profiles only), link the isolated profile's "
        'projects/ directory to the base ~/.claude/projects/ so the isolated and base '
        'Claude share session history. Default False keeps them separate. Requires command-names.',
    )
    claude_code_version: str | None = Field(
        None,
        alias='claude-code-version',
        description='Specific Claude Code version to install (e.g., "1.0.124"). If not specified, installs latest.',
    )
    version: str | None = Field(
        None,
        description='Configuration version for update checking. '
        'Semantic versioning string (e.g., "1.0.0"). Optional; configs without '
        'this field skip all version checking.',
    )
    inherit: str | list[str | InheritEntry] | None = Field(
        None,
        description='Parent configuration(s) to inherit from. '
        'Accepts a single string (URL, path, or repo name), a list of strings '
        'for composition chains, or a list mixing strings and structured entries '
        '{config: str, merge-keys: list[str]} for per-entry merge control. '
        'Single-element plain-string list normalizes to string for recursive resolution. '
        'Single-element structured list routes to composition mode.',
    )
    merge_keys: list[str] | None = Field(
        None,
        alias='merge-keys',
        description='List of top-level keys to merge (extend) from parent during inheritance. '
        'Only applicable with inherit. Keys not listed here use replace semantics.',
    )
    os_env_variables: dict[str, str | None] | None = Field(
        None,
        alias='os-env-variables',
        description='OS-level persistent environment variables. '
        'Set value to null to delete the variable.',
    )
    user_settings: UserSettings | None = Field(
        None,
        alias='user-settings',
        description='Raw settings.json content (camelCase keys). Written to '
        '~/.claude/settings.json via deep merge in non-isolated mode, or built '
        "into the isolated profile's config.json (delivered via --settings) "
        'when command-names is present.',
    )
    global_config: GlobalConfig | None = Field(
        None,
        alias='global-config',
        description='Global configuration written to ~/.claude.json. '
        'These settings apply to Claude Code globally across all profiles.',
    )

    @field_validator('command_names')
    @classmethod
    def validate_command_names(cls, v: list[str] | None) -> list[str] | None:
        """Validate command names format."""
        if not v:
            return v
        for i, name in enumerate(v):
            if not name or not name.strip():
                raise ValueError(f'command_names[{i}] cannot be empty or whitespace-only')
            if ' ' in name:
                raise ValueError(f'command_names[{i}] cannot contain spaces: "{name}"')
            if not name.replace('-', '').replace('_', '').isalnum():
                raise ValueError(
                    f'command_names[{i}] must contain only alphanumeric characters, hyphens, and underscores: "{name}"',
                )
        return v

    @field_validator('dependencies')
    @classmethod
    def validate_dependencies_structure(cls, v: object) -> dict[str, list[str]]:
        """Validate dependencies have correct structure."""
        if v is None:
            return {'common': [], 'windows': [], 'macos': [], 'linux': []}

        if not isinstance(v, dict):
            raise ValueError('dependencies must be a dictionary')

        # Cast to dict for type checking
        deps_dict = cast(dict[str, object], v)

        valid_keys = {'common', 'windows', 'macos', 'linux'}
        invalid_keys = set(deps_dict.keys()) - valid_keys

        if invalid_keys:
            raise ValueError(
                f'Invalid platform keys in dependencies: {invalid_keys}. Valid keys are: {valid_keys}',
            )

        # Build validated result
        result: dict[str, list[str]] = {}

        # Validate each platform's dependencies
        for platform_key in valid_keys:
            if platform_key not in deps_dict:
                result[platform_key] = []
                continue

            commands = deps_dict[platform_key]
            if not isinstance(commands, list):
                raise ValueError(f'dependencies.{platform_key} must be a list')

            # Cast to list[object] for type checking
            commands_list = cast(list[object], commands)
            validated_commands: list[str] = []
            for idx, cmd in enumerate(commands_list):
                if not isinstance(cmd, str):
                    raise ValueError(f'dependencies.{platform_key}[{idx}] must be a string')
                validated_commands.append(cmd)

            result[platform_key] = validated_commands

        return result

    @field_validator('base_url')
    @classmethod
    def validate_base_url(cls, v: str | None) -> str | None:
        """Validate base URL format."""
        if v and not v.startswith(('http://', 'https://')):
            raise ValueError('base-url must start with http:// or https://')
        return v

    @field_validator('mcp_servers')
    @classmethod
    def validate_mcp_servers(cls, v: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        """Validate MCP server configurations."""
        if not v:
            return v

        validated: list[dict[str, Any]] = []
        for server in v:
            if 'name' not in server:
                raise ValueError("MCP server must have a 'name' field")

            # Validate based on transport type or presence of command
            if 'transport' in server:
                if server['transport'] in ['http', 'sse']:
                    MCPServerHTTP(**server)  # Validate structure
                else:
                    raise ValueError(f"Unknown transport type: {server['transport']}")
            elif 'command' in server:
                MCPServerStdio(**server)  # Validate structure
            else:
                raise ValueError("MCP server must have either 'transport' or 'command' field")

            validated.append(server)  # Keep original dict for compatibility

        return validated

    @field_validator('claude_code_version')
    @classmethod
    def validate_claude_code_version(cls, v: str | None) -> str | None:
        """Validate Claude Code version format (semantic versioning or 'latest')."""
        if v is None:
            return v

        # Allow 'latest' as a special value
        if v.lower() == 'latest':
            return v

        # Basic semantic version validation (X.Y.Z format)
        # Pattern allows for version formats like: 1.0.0, 1.0.128, 2.1.0-beta.1, etc.
        version_pattern = r'^(\d+)\.(\d+)\.(\d+)(?:-[\w\.\-]+)?(?:\+[\w\.\-]+)?$'
        if not re.match(version_pattern, v):
            raise ValueError(
                f'claude-code-version must be "latest" or a valid semantic version '
                f'(e.g., "1.0.128", "2.0.0-beta.1"). Got: {v}',
            )
        return v

    @field_validator('version')
    @classmethod
    def validate_version(cls, v: str | None) -> str | None:
        """Validate configuration version format (semantic versioning)."""
        if v is None:
            return v

        version_pattern = r'^(\d+)\.(\d+)\.(\d+)(?:-[\w\.\-]+)?(?:\+[\w\.\-]+)?$'
        if not re.match(version_pattern, v):
            raise ValueError(
                f'version must be a valid semantic version '
                f'(e.g., "1.0.0", "2.1.0-beta.1"). Got: {v}',
            )
        return v

    @field_validator('inherit', mode='before')
    @classmethod
    def validate_inherit(
        cls, v: str | list[str | dict[str, Any] | InheritEntry] | None,
    ) -> str | list[str | InheritEntry] | None:
        """Validate inherit value: string, list of strings/structured entries, or None.

        When a list is provided:
        - Must be non-empty
        - Elements can be strings (plain inherit) or dicts (structured with per-entry merge-keys)
        - Dict entries are coerced to InheritEntry via model_validate()
        - All string entries must be non-empty, non-blank
        - No null bytes allowed

        Args:
            v: Inherit path/URL string, list of strings/dicts, or None.

        Returns:
            The validated inherit value with dicts coerced to InheritEntry.

        Raises:
            ValueError: If inherit value is invalid.
        """
        if v is None:
            return v

        if isinstance(v, str):
            if not v or not v.strip():
                raise ValueError('inherit cannot be empty string')
            if '\x00' in v:
                raise ValueError('inherit cannot contain null bytes')
            return v

        if isinstance(v, list):
            if not v:
                raise ValueError('inherit list cannot be empty')
            result: list[str | InheritEntry] = []
            for i, entry in enumerate(v):
                if isinstance(entry, str):
                    if not entry or not entry.strip():
                        raise ValueError(f'inherit[{i}] cannot be empty or whitespace-only')
                    if '\x00' in entry:
                        raise ValueError(f'inherit[{i}] cannot contain null bytes')
                    result.append(entry)
                elif isinstance(entry, dict):
                    try:
                        result.append(InheritEntry.model_validate(entry))
                    except Exception as e:
                        raise ValueError(f'inherit[{i}]: {e}') from e
                elif isinstance(entry, InheritEntry):
                    result.append(entry)
                else:
                    raise ValueError(
                        f'inherit[{i}] must be a string or {{config: ..., merge-keys: [...]}} object, '
                        f'got {type(entry).__name__}',
                    )
            return result

        raise ValueError(
            f"The 'inherit' key must be a string or list of strings/objects, "
            f"got {type(v).__name__}: {v!r}",
        )

    @field_validator('merge_keys')
    @classmethod
    def validate_merge_keys(cls, v: list[str] | None) -> list[str] | None:
        """Validate merge-keys entries against the set of mergeable configuration keys.

        Args:
            v: List of key names to validate.

        Returns:
            The validated list, or None.

        Raises:
            ValueError: If any key is not in the set of mergeable keys.
        """
        if v is None:
            return v

        # Inline definition avoids circular import from setup_environment.py
        mergeable: frozenset[str] = frozenset({
            'dependencies', 'agents', 'slash-commands', 'rules', 'skills',
            'files-to-download', 'hooks', 'mcp-servers',
            'global-config', 'user-settings', 'os-env-variables',
        })
        invalid = [k for k in v if k not in mergeable]
        if invalid:
            raise ValueError(
                f'Invalid merge-keys: {invalid}. '
                f'Valid mergeable keys: {sorted(mergeable)}',
            )
        return v

    @field_validator('os_env_variables')
    @classmethod
    def validate_os_env_variables(cls, v: dict[str, str | None] | None) -> dict[str, str | None] | None:
        """Validate OS environment variables configuration.

        Args:
            v: Dictionary of environment variable names to values.

        Returns:
            The validated dictionary.

        Raises:
            ValueError: If variable names are invalid or values contain null bytes.
        """
        if v is None:
            return v

        env_var_pattern = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

        for name, value in v.items():
            if not env_var_pattern.match(name):
                raise ValueError(
                    f'Invalid environment variable name: {name}. '
                    'Must start with letter or underscore, followed by letters, digits, or underscores.',
                )

            if value is not None and '\x00' in str(value):
                raise ValueError(f'Environment variable {name} value cannot contain null bytes')

        return v

    @model_validator(mode='after')
    def validate_command_names_and_defaults(self) -> 'EnvironmentConfig':
        """Ensure command-names and command-defaults are both present or both absent."""
        has_command_names = bool(self.command_names)  # Empty list or None is falsy
        has_command_defaults = self.command_defaults is not None

        if has_command_names != has_command_defaults:
            if has_command_names and not has_command_defaults:
                raise ValueError(
                    'command-names requires command-defaults to be specified. '
                    'Either provide both command-names and command-defaults, or omit both.',
                )
            raise ValueError(
                'command-defaults requires command-names to be specified. '
                'Either provide both command-names and command-defaults, or omit both.',
            )

        return self

    @model_validator(mode='after')
    def validate_version_requires_command_names(self) -> 'EnvironmentConfig':
        """Validate that version requires command-names to be present.

        The version field controls update checking via manifest.json and
        launcher scripts, which are only created when command-names is
        specified. Without command-names, version has no functional effect.

        Returns:
            The validated EnvironmentConfig instance.

        Raises:
            ValueError: If version is set without command-names.
        """
        if self.version is not None and not self.command_names:
            raise ValueError(
                'version requires command-names to be specified. '
                'The version field controls update checking via manifest.json '
                'and launcher scripts, which are only created when command-names '
                'is present. Either add command-names or remove version.',
            )
        return self

    @model_validator(mode='after')
    def validate_link_projects_dir_requires_command_names(self) -> 'EnvironmentConfig':
        """Validate that link-projects-dir requires command-names to be present.

        The base ~/.claude/projects/ is already what the non-isolated Claude uses,
        so linking only makes sense for an isolated profile (created only when
        command-names is specified).

        Returns:
            The validated EnvironmentConfig instance.

        Raises:
            ValueError: If link-projects-dir is truthy without command-names.
        """
        if self.link_projects_dir and not self.command_names:
            raise ValueError(
                'link-projects-dir requires command-names to be specified. '
                'The projects/ link binds an isolated profile to the base '
                '~/.claude/projects/, and isolated profiles exist only when '
                'command-names is present. Either add command-names or remove '
                'link-projects-dir.',
            )
        return self

    @model_validator(mode='after')
    def validate_merge_keys_requires_inherit(self) -> 'EnvironmentConfig':
        """Validate that merge-keys requires inherit to be present.

        The merge-keys directive controls which keys use merge (extend)
        semantics during inheritance resolution. Without inherit, there is
        no parent configuration to merge from, making merge-keys meaningless.

        An empty merge-keys list is treated as a no-op and does not require
        inherit.

        Returns:
            The validated EnvironmentConfig instance.

        Raises:
            ValueError: If non-empty merge-keys is set without inherit.
        """
        if self.merge_keys and self.inherit is None:
            raise ValueError(
                'merge-keys requires inherit to be specified. '
                'The merge-keys directive controls merge semantics during inheritance. '
                'Without inherit, merge-keys has no effect. '
                'Either add inherit or remove merge-keys.',
            )
        return self

    @model_validator(mode='after')
    def validate_profile_mcp_requires_command_names(self) -> 'EnvironmentConfig':
        """Validate that profile-scoped MCP servers require command-names.

        Profile-scoped MCP servers need a launcher script with --mcp-config
        flag, which is only created when command-names is present. Without
        command-names, profile-scoped servers would be silently dropped.

        Returns:
            The validated EnvironmentConfig instance.

        Raises:
            ValueError: If profile-scoped servers exist without command-names.
        """
        if self.command_names or not self.mcp_servers:
            return self

        profile_server_names: list[str] = []
        for server in self.mcp_servers:
            scope_raw = server.get('scope', 'user')
            if isinstance(scope_raw, str):
                scopes = [scope_raw]
            elif isinstance(scope_raw, list):
                scopes = [s for s in scope_raw if isinstance(s, str)]
            else:
                scopes = []
            if 'profile' in scopes:
                profile_server_names.append(str(server.get('name', '<unnamed>')))

        if profile_server_names:
            names_str = ', '.join(f"'{n}'" for n in profile_server_names)
            raise ValueError(
                f'Profile-scoped MCP server(s) {names_str} require command-names. '
                'Profile-scoped servers need a launcher script with --mcp-config flag, '
                'which is only created when command-names is present. '
                'Either add command-names or change the server scope to user/local/project.',
            )
        return self

    @model_validator(mode='after')
    def validate_hooks_files_consistency(self) -> 'EnvironmentConfig':
        """Validate that hooks files, events, and status-line are consistent.

        Ensures:
        1. Each file in hooks.files is used somewhere (events or status-line)
        2. Each file referenced in hooks.events (command hooks only) exists in hooks.files
        3. The status-line.file (if configured) exists in hooks.files

        Note: Prompt hooks (type='prompt') do not use command or config files,
        so they are excluded from file consistency validation.

        Returns:
            The validated EnvironmentConfig instance.

        Raises:
            ValueError: If hooks files consistency rules are violated.
        """
        # Skip validation if hooks is not configured
        if self.hooks is None:
            # If status_line is configured but hooks is None, that's an error
            if self.status_line is not None:
                raise ValueError(
                    f'status-line.file "{self.status_line.file}" requires hooks.files to be configured. '
                    'Add the status-line script to hooks.files.',
                )
            return self

        # Build set of available file basenames from hooks.files
        available_files: set[str] = set()
        for file_path in self.hooks.files:
            basename = _extract_basename(file_path)
            if basename:
                available_files.add(basename)

        # Track which files are used
        used_files: set[str] = set()

        # Rule 2: Check that each command hook's command and config exists in hooks.files
        # Only command hooks use file references; http/prompt/agent hooks are excluded
        for event in self.hooks.events:
            # Skip non-command hooks - only command hooks reference files
            if event.type in ('prompt', 'http', 'agent'):
                continue

            # For command hooks, validate command and config files
            if event.command:
                command_file = event.command.strip()
                if command_file:
                    if command_file not in available_files:
                        raise ValueError(
                            f'hooks.events command "{command_file}" not found in hooks.files. '
                            f'Available files: {sorted(available_files) if available_files else "none"}',
                        )
                    used_files.add(command_file)

            # Check config file reference if present
            if event.config:
                config_file = event.config.strip()
                # Strip query parameters from config filename (same as setup_environment.py)
                clean_config = config_file.split('?')[0] if '?' in config_file else config_file
                config_basename = _extract_basename(clean_config)
                if config_basename:
                    if config_basename not in available_files:
                        raise ValueError(
                            f'hooks.events config "{config_file}" not found in hooks.files. '
                            f'Available files: {sorted(available_files) if available_files else "none"}',
                        )
                    used_files.add(config_basename)

        # Rule 3: Check that status-line.file exists in hooks.files
        if self.status_line is not None:
            status_file = self.status_line.file.strip()
            if status_file:
                if status_file not in available_files:
                    raise ValueError(
                        f'status-line.file "{status_file}" not found in hooks.files. '
                        f'Available files: {sorted(available_files) if available_files else "none"}',
                    )
                used_files.add(status_file)

            # Also check status-line.config if specified
            if self.status_line.config:
                config_file = self.status_line.config.strip()
                # Strip query parameters from config filename (same as setup_environment.py)
                clean_config = config_file.split('?')[0] if '?' in config_file else config_file
                config_basename = _extract_basename(clean_config)
                if config_basename:
                    if config_basename not in available_files:
                        raise ValueError(
                            f'status-line.config "{config_file}" not found in hooks.files. '
                            f'Available files: {sorted(available_files) if available_files else "none"}',
                        )
                    used_files.add(config_basename)

        # Rule 1: Check that each file in hooks.files is used somewhere
        unused_files = available_files - used_files
        if unused_files:
            raise ValueError(
                f'hooks.files contains unused files: {sorted(unused_files)}. '
                'Each file must be referenced by a hook event or status-line.',
            )

        return self

    @field_validator('agents', 'slash_commands', 'rules')
    @classmethod
    def validate_file_paths(cls, v: list[str] | None) -> list[str] | None:
        """Validate file paths for security issues.

        Allows:
        - Full URLs (http://, https://)
        - Local absolute paths (C:\\, /, ~/...)
        - Local relative paths (./file, ../file, file)

        Prevents:
        - Path traversal attacks in URLs only

        Returns:
            The validated list of file paths.
        """
        if not v:
            return v

        for path in v:
            # Full URLs are always allowed
            if path.startswith(('http://', 'https://')):
                continue

            # For local paths, just check for obvious security issues
            # We allow .. in paths since users might legitimately reference parent dirs
            # The OS will handle actual file access permissions

        return v
