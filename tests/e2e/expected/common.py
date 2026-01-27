"""Common expected values shared across all platforms.

These values represent files and JSON keys that are identical regardless
of the operating system.

Note: The actual additional-settings.json location differs by platform:
- Linux/macOS: {config_claude}/{cmd}-additional-settings.json
- Windows: {localappdata_claude}/{cmd}-additional-settings.json

The MCP config file is always in {claude_dir}/{cmd}-mcp.json.
"""

from typing import Final

# Files created on ALL platforms (these are just the common JSON files)
# The actual location varies by platform, so platform modules define full paths
COMMON_FILES: Final[list[str]] = [
    # MCP server configuration (always in claude_dir)
    '{claude_dir}/{cmd}-mcp.json',
]

# Expected keys in generated JSON files
EXPECTED_JSON_KEYS: Final[dict[str, list[str]]] = {
    'additional-settings': [
        'permissions',
        'env',
        'hooks',
        'model',
        'alwaysThinkingEnabled',
        'companyAnnouncements',
        'attribution',
        'statusLine',
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
}
