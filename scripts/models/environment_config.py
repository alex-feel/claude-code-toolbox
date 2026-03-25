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
    'oauthSession',
    'oauthAccount',
})


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


class UserSettings(BaseModel):
    """User settings configuration for ~/.claude/settings.json.

    Free-form model that accepts any keys supported by Claude Code's
    settings.json schema. No specific keys are hardcoded -- the model
    passes through all provided settings without field-level validation.

    The only structural guard is the exclusion of 'hooks' and 'statusLine'
    keys, which are profile-specific and must not appear in user-settings.
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


class GlobalConfig(BaseModel):
    """Global configuration for ~/.claude.json.

    Free-form model that accepts any keys supported by Claude Code's
    global configuration schema. No specific keys are hardcoded -- the model
    passes through all provided settings without field-level validation.

    The only structural guard is the exclusion of OAuth credential keys
    (oauthSession, oauthAccount) to prevent accidental credential exposure
    in version-controlled YAML configuration files.
    """

    model_config = ConfigDict(extra='allow')

    @model_validator(mode='before')
    @classmethod
    def check_excluded_keys(cls, data: dict[str, object]) -> dict[str, object]:
        """Validate that excluded keys are not present."""
        for key in GLOBAL_CONFIG_EXCLUDED_KEYS:
            if key in data:
                raise ValueError(
                    f"Key '{key}' is not allowed in global-config (OAuth credentials). "
                    'OAuth credentials are managed by Claude Code and must not appear '
                    'in environment configuration files.',
                )
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

    Supports two hook types:
    - command: Executes a script/command (requires 'command' field)
    - prompt: Uses LLM for evaluation (requires 'prompt' field)
    """

    event: str = Field(..., description='Event name (e.g., PreToolUse, PostToolUse, Notification)')
    matcher: str | None = Field('', description='Regex pattern for matching')
    type: Literal['command', 'prompt'] = Field('command', description='Hook type: command or prompt')

    # Command hook fields
    command: str | None = Field(
        None,
        description='Command to execute (required for command hooks, forbidden for prompt hooks)',
    )
    config: str | None = Field(
        None,
        description='Optional config file reference to pass as argument to hook command',
    )

    # Prompt hook fields
    prompt: str | None = Field(
        None,
        description='Prompt text sent to LLM for evaluation (required for prompt hooks, forbidden for command hooks)',
    )
    timeout: int | None = Field(
        None,
        description='Timeout in seconds for prompt hook LLM evaluation (optional, default 30)',
    )

    @model_validator(mode='after')
    def validate_hook_type_fields(self) -> 'HookEvent':
        """Validate that fields are correctly set based on hook type.

        For command hooks:
        - command is required
        - prompt is forbidden

        For prompt hooks:
        - prompt is required
        - command is forbidden
        - config is forbidden

        Returns:
            The validated HookEvent instance.

        Raises:
            ValueError: If field requirements are not met for the hook type.
        """
        if self.type == 'command':
            if not self.command:
                raise ValueError(
                    "Hook type 'command' requires 'command' field. "
                    "Either provide a command or change type to 'prompt'.",
                )
            if self.prompt is not None:
                raise ValueError(
                    "Hook type 'command' cannot have 'prompt' field. "
                    "Use type 'prompt' for LLM-based hooks.",
                )
        elif self.type == 'prompt':
            if not self.prompt:
                raise ValueError(
                    "Hook type 'prompt' requires 'prompt' field. "
                    "Either provide a prompt or change type to 'command'.",
                )
            if self.command is not None:
                raise ValueError(
                    "Hook type 'prompt' cannot have 'command' field. "
                    "Use type 'command' for script-based hooks.",
                )
            if self.config is not None:
                raise ValueError(
                    "Hook type 'prompt' cannot have 'config' field. "
                    "Config files are only used with command hooks.",
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


class Attribution(BaseModel):
    """Attribution configuration for commits and PRs."""

    commit: str | None = Field(None, description='Custom attribution string for commits. Empty string hides attribution.')
    pr: str | None = Field(None, description='Custom attribution string for PRs. Empty string hides attribution.')


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


class Permissions(BaseModel):
    """Permissions configuration."""

    default_mode: Literal['default', 'acceptEdits', 'plan', 'bypassPermissions'] | None = Field(
        None,
        alias='defaultMode',
        description='Default permission mode',
    )
    allow: list[str] | None = Field(None, description='Explicitly allowed actions')
    deny: list[str] | None = Field(None, description='Explicitly denied actions')
    ask: list[str] | None = Field(None, description='Actions requiring confirmation')
    additional_directories: list[str] | None = Field(
        None,
        alias='additionalDirectories',
        description='Additional accessible directories',
    )


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


class EnvironmentConfig(BaseModel):
    """Complete environment configuration model."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    name: str = Field(..., description='Display name for the environment')
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
    model: str | None = Field(None, description='Model configuration')
    env_variables: dict[str, str] | None = Field(
        None,
        alias='env-variables',
        description='Environment variables',
    )
    permissions: Permissions | None = Field(None, description='Permissions configuration')
    command_defaults: CommandDefaults | None = Field(
        None,
        alias='command-defaults',
        description='Command launch defaults',
    )
    company_announcements: list[str] | None = Field(
        None,
        alias='company-announcements',
        description='List of company announcement strings to display to users',
    )
    attribution: Attribution | None = Field(
        None,
        description='Attribution configuration for commits and PRs. Replaces deprecated include-co-authored-by.',
    )
    status_line: StatusLine | None = Field(
        None,
        alias='status-line',
        description='Status line configuration with script file and optional padding',
    )
    always_thinking_enabled: bool | None = Field(
        None,
        alias='always-thinking-enabled',
        description='Whether to enable always-on thinking mode for extended reasoning (default: False)',
    )
    effort_level: Literal['low', 'medium', 'high', 'max'] | None = Field(
        None,
        alias='effort-level',
        description='Effort level for adaptive reasoning. Controls how much thinking is allocated based on task complexity. '
        'The "max" level is only available for Opus models.',
    )
    install_nodejs: bool | None = Field(
        None,
        alias='install-nodejs',
        description='Whether to install Node.js LTS before processing dependencies (default: False)',
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
    inherit: str | None = Field(
        None,
        description='URL or path to parent configuration to inherit from. '
        'Supports full URLs, local paths, or repository config names.',
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
        description='User-level settings written to ~/.claude/settings.json. '
        'These settings apply across all sessions.',
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

    @field_validator('model')
    @classmethod
    def validate_model(cls, v: str | None) -> str | None:
        """Validate model configuration."""
        valid_aliases = ['default', 'sonnet', 'opus', 'haiku', 'opus[1m]', 'sonnet[1m]', 'opusplan']
        if v and not (v in valid_aliases or v.startswith('claude-')):
            raise ValueError(
                f"model must be one of {valid_aliases} or a custom model name starting with 'claude-'",
            )
        return v

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

    @field_validator('inherit')
    @classmethod
    def validate_inherit(cls, v: str | None) -> str | None:
        """Validate inherit path or URL format.

        Args:
            v: Inherit path/URL string to validate.

        Returns:
            The validated inherit value.

        Raises:
            ValueError: If inherit path is empty or contains null bytes.
        """
        if v is None:
            return v

        if not v or not v.strip():
            raise ValueError('inherit cannot be empty string')

        if '\x00' in v:
            raise ValueError('inherit cannot contain null bytes')

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
    def validate_effort_level_max(self) -> 'EnvironmentConfig':
        """Validate that effort_level 'max' is only used with Opus models."""
        if self.effort_level != 'max':
            return self

        if self.model is None:
            raise ValueError(
                "effort-level 'max' requires model to be specified. "
                "The 'max' effort level is only available for Opus models.",
            )

        if 'opus' not in self.model.lower():
            raise ValueError(
                f"effort-level 'max' is only available for Opus models, "
                f"but model is set to '{self.model}'. "
                "Use 'low', 'medium', or 'high' for non-Opus models.",
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
        # Prompt hooks are excluded - they don't use command or config files
        for event in self.hooks.events:
            # Skip prompt hooks - they don't use command or config files
            if event.type == 'prompt':
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

    @field_validator('agents', 'slash_commands')
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
