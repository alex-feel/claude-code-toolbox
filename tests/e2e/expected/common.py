"""Common expected values shared across all platforms.

These values represent files and JSON keys that are identical regardless
of the operating system.

All isolated environment files use generic names inside {claude_dir}/{cmd}/:
- config.json (profile settings, Priority 2)
- settings.json (user settings, Priority 5)
- mcp.json (MCP server configuration)
- manifest.json (installation metadata)
"""

from typing import Final

# Files created on ALL platforms (these are just the common JSON files)
# The actual location varies by platform, so platform modules define full paths
COMMON_FILES: Final[list[str]] = [
    # MCP server configuration (inside isolated directory)
    '{claude_dir}/{cmd}/mcp.json',
    # Installation manifest (inside isolated directory)
    '{claude_dir}/{cmd}/manifest.json',
]

# Expected keys in generated JSON files
EXPECTED_JSON_KEYS: Final[dict[str, list[str]]] = {
    'settings': [
        'permissions',
        'env',
        'hooks',
        'model',
        'alwaysThinkingEnabled',
        'companyAnnouncements',
        'attribution',
        'statusLine',
        'effortLevel',
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
        'config_source',
        'config_source_url',
        'config_source_type',
        'installed_at',
        'last_checked_at',
        'command_names',
    ],
}
