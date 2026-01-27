"""Linux-specific expected outputs for E2E testing.

This module defines the files and paths expected to be created by
setup_environment.py when running on Linux systems.

Path templates use fixture key placeholders:
    - {claude_dir}: ~/.claude directory
    - {local_bin}: ~/.local/bin directory
    - {config_claude}: ~/.config/claude directory
    - {cmd}: Command name from golden_config (e.g., e2e-test-cmd)
"""

from typing import Final

# Expected files created on Linux
# Paths use fixture key references that will be resolved at test runtime
EXPECTED_FILES: Final[list[str]] = [
    # Launcher script in claude_dir
    '{claude_dir}/start-{cmd}.sh',
    # Additional settings in claude_dir (written to claude_user_dir by create_additional_settings)
    '{claude_dir}/{cmd}-additional-settings.json',
    # MCP config in claude_dir
    '{claude_dir}/{cmd}-mcp.json',
    # Symlink in local_bin
    '{local_bin}/{cmd}',
]

# Expected paths mapping logical names to path templates
# Uses fixture keys that will be resolved at test runtime
EXPECTED_PATHS: Final[dict[str, str]] = {
    'launcher_script': '{claude_dir}/start-{cmd}.sh',
    'additional_settings': '{claude_dir}/{cmd}-additional-settings.json',
    'mcp_config': '{claude_dir}/{cmd}-mcp.json',
    'command_symlink': '{local_bin}/{cmd}',
    'hooks_dir': '{claude_dir}/hooks',
    'agents_dir': '{claude_dir}/agents',
    'commands_dir': '{claude_dir}/commands',
    'skills_dir': '{claude_dir}/skills',
}
