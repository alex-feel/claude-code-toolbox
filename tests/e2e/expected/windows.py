"""Windows-specific expected outputs for E2E testing.

This module defines the files and paths expected to be created by
setup_environment.py when running on Windows systems.

Windows creates additional wrapper scripts for cross-shell compatibility:
- PowerShell wrapper (.ps1) in local_bin
- CMD wrapper (.cmd) in local_bin
- Git Bash wrapper (no extension) in local_bin
- Shared POSIX script ({cmd}/launch.sh) in claude_dir
- PowerShell launcher ({cmd}/start.ps1) in claude_dir
- CMD launcher ({cmd}/start.cmd) in claude_dir

Path templates use fixture key placeholders:
    - {claude_dir}: ~/.claude directory
    - {local_bin}: ~/.local/bin directory
    - {localappdata_claude}: AppData/Local/Claude directory
    - {cmd}: Command name from golden_config (e.g., e2e-test-cmd)
"""

from typing import Final

# Expected files created on Windows
# Paths use fixture key references that will be resolved at test runtime
EXPECTED_FILES: Final[list[str]] = [
    # Shared POSIX launcher script (executed by Git Bash)
    '{claude_dir}/{cmd}/launch.sh',
    # PowerShell launcher script
    '{claude_dir}/{cmd}/start.ps1',
    # CMD launcher script
    '{claude_dir}/{cmd}/start.cmd',
    # Profile config in artifact base dir
    '{claude_dir}/{cmd}/config.json',
    # MCP config in artifact base dir
    '{claude_dir}/{cmd}/mcp.json',
    # Wrapper scripts in local_bin for PATH accessibility
    '{local_bin}/{cmd}.cmd',
    '{local_bin}/{cmd}.ps1',
    '{local_bin}/{cmd}',
]

# Expected paths mapping logical names to path templates
# Uses fixture keys that will be resolved at test runtime
EXPECTED_PATHS: Final[dict[str, str]] = {
    'launcher_script_posix': '{claude_dir}/{cmd}/launch.sh',
    'launcher_script_ps1': '{claude_dir}/{cmd}/start.ps1',
    'launcher_script_cmd': '{claude_dir}/{cmd}/start.cmd',
    'settings': '{claude_dir}/{cmd}/config.json',
    'mcp_config': '{claude_dir}/{cmd}/mcp.json',
    'command_wrapper_cmd': '{local_bin}/{cmd}.cmd',
    'command_wrapper_ps1': '{local_bin}/{cmd}.ps1',
    'command_wrapper_bash': '{local_bin}/{cmd}',
    'hooks_dir': '{claude_dir}/{cmd}/hooks',
    'agents_dir': '{claude_dir}/{cmd}/agents',
    'commands_dir': '{claude_dir}/{cmd}/commands',
    'skills_dir': '{claude_dir}/{cmd}/skills',
}
