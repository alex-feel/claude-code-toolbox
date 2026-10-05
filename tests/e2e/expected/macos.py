"""macOS-specific expected outputs for E2E testing.

This module defines the files and paths expected to be created by
setup_environment.py when running on macOS systems.

Note: macOS uses the same file structure as Linux (Unix-like behavior).

Path templates use fixture key placeholders:
    - {claude_dir}: ~/.claude directory
    - {local_bin}: ~/.local/bin directory
    - {config_claude}: ~/.config/claude directory
    - {cmd}: Command name from golden_config (e.g., e2e-test-cmd)
"""

from typing import Final

# Expected files created on macOS
# Paths use fixture key references that will be resolved at test runtime
EXPECTED_FILES: Final[list[str]] = [
    # Launcher script in claude_dir
    '{claude_dir}/{cmd}/launch.sh',
    # Profile config in artifact base dir
    '{claude_dir}/{cmd}/config.json',
    # MCP config in artifact base dir
    '{claude_dir}/{cmd}/mcp.json',
    # Symlink in local_bin
    '{local_bin}/{cmd}',
]

# Expected paths mapping logical names to path templates
# Uses fixture keys that will be resolved at test runtime
EXPECTED_PATHS: Final[dict[str, str]] = {
    'launcher_script': '{claude_dir}/{cmd}/launch.sh',
    'settings': '{claude_dir}/{cmd}/config.json',
    'mcp_config': '{claude_dir}/{cmd}/mcp.json',
    'command_symlink': '{local_bin}/{cmd}',
    'hooks_dir': '{claude_dir}/{cmd}/hooks',
    'agents_dir': '{claude_dir}/{cmd}/agents',
    'commands_dir': '{claude_dir}/{cmd}/commands',
    'skills_dir': '{claude_dir}/{cmd}/skills',
}

# Where a Node.js installation and the npm global prefix keep their npm copies:
# node and the bundled npm's bin/npm entry sit in {node_root}/bin with the bundled
# npm in {node_root}/lib/node_modules; npm install -g npm writes its copy into
# {npm_prefix}/lib/node_modules and links {npm_prefix}/bin/npm to it, so that copy
# runs when {npm_prefix}/bin comes first on PATH
EXPECTED_NPM_LAYOUT: Final[dict[str, str]] = {
    'node_bin_dir': '{node_root}/bin',
    'bundled_npm': '{node_root}/lib/node_modules/npm',
    'prefix_bin_dir': '{npm_prefix}/bin',
    'prefix_npm': '{npm_prefix}/lib/node_modules/npm',
}
