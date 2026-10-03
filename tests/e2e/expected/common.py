"""Common expected values shared across all platforms.

These values represent files and JSON keys that are identical regardless
of the operating system.

All isolated environment files use generic names inside {claude_dir}/{cmd}/:
- config.json (profile settings, Priority 2)
- mcp.json (MCP server configuration)
- manifest.json (installation metadata)
- resolved-config.yaml (the configuration the run installed, whose sha256
  the manifest records as config_digest)

A run without command-names writes its own {claude_dir}/manifest.json and
{claude_dir}/resolved-config.yaml for the base profile, with the same key set.
"""

from typing import Final

# Files created on ALL platforms (these are just the common JSON and YAML files)
# The actual location varies by platform, so platform modules define full paths
COMMON_FILES: Final[list[str]] = [
    # MCP server configuration (inside isolated directory)
    '{claude_dir}/{cmd}/mcp.json',
    # Installation manifest (inside isolated directory)
    '{claude_dir}/{cmd}/manifest.json',
    # The installed configuration beside the manifest (inside isolated directory)
    '{claude_dir}/{cmd}/resolved-config.yaml',
    # The base profile's own manifest and installed configuration
    '{claude_dir}/manifest.json',
    '{claude_dir}/resolved-config.yaml',
]

# Expected keys in generated JSON files
EXPECTED_JSON_KEYS: Final[dict[str, list[str]]] = {
    # Top-level camelCase keys expected in the isolated config.json: the
    # toolbox-built statusLine and hooks entries plus every non-null
    # top-level key declared in the golden user-settings section.
    'settings': [
        'language',
        'theme',
        'apiKeyHelper',
        'model',
        'permissions',
        'env',
        'alwaysThinkingEnabled',
        'effortLevel',
        'companyAnnouncements',
        'attribution',
        'statusLine',
        'hooks',
    ],
    'mcp-config': [
        'mcpServers',
    ],
    'permissions': [
        'defaultMode',
        'allow',
        'deny',
        'ask',
    ],
    'manifest': [
        'name',
        'version',
        'claude_code_version',
        'config_source',
        'config_source_url',
        'config_source_type',
        'config_identity',
        'config_digest',
        'installed_at',
        'command_names',
        'components',
        'link',
        'origins',
        'yaml_values',
        'machine_wide_destinations',
        'os_env_written',
        'settings_keys_written',
        'mcp_servers',
        'files_written',
    ],
}
