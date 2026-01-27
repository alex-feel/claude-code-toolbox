"""Windows-specific expected outputs for E2E testing.

This module defines the files and paths expected to be created by
setup_environment.py when running on Windows systems.

Windows creates additional wrapper scripts for cross-shell compatibility:
- PowerShell wrapper (.ps1) in local_bin
- CMD wrapper (.cmd) in local_bin
- Git Bash wrapper (no extension) in local_bin
- Shared POSIX script (launch-{cmd}.sh) in claude_dir
- PowerShell launcher (start-{cmd}.ps1) in claude_dir
- CMD launcher (start-{cmd}.cmd) in claude_dir

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
    '{claude_dir}/launch-{cmd}.sh',
    # PowerShell launcher script
    '{claude_dir}/start-{cmd}.ps1',
    # CMD launcher script
    '{claude_dir}/start-{cmd}.cmd',
    # Additional settings in claude_dir (written to claude_user_dir by create_additional_settings)
    '{claude_dir}/{cmd}-additional-settings.json',
    # MCP config in claude_dir
    '{claude_dir}/{cmd}-mcp.json',
    # Wrapper scripts in local_bin for PATH accessibility
    '{local_bin}/{cmd}.cmd',
    '{local_bin}/{cmd}.ps1',
    '{local_bin}/{cmd}',
]

# Expected paths mapping logical names to path templates
# Uses fixture keys that will be resolved at test runtime
EXPECTED_PATHS: Final[dict[str, str]] = {
    'launcher_script_posix': '{claude_dir}/launch-{cmd}.sh',
    'launcher_script_ps1': '{claude_dir}/start-{cmd}.ps1',
    'launcher_script_cmd': '{claude_dir}/start-{cmd}.cmd',
    'additional_settings': '{claude_dir}/{cmd}-additional-settings.json',
    'mcp_config': '{claude_dir}/{cmd}-mcp.json',
    'command_wrapper_cmd': '{local_bin}/{cmd}.cmd',
    'command_wrapper_ps1': '{local_bin}/{cmd}.ps1',
    'command_wrapper_bash': '{local_bin}/{cmd}',
    'hooks_dir': '{claude_dir}/hooks',
    'agents_dir': '{claude_dir}/agents',
    'commands_dir': '{claude_dir}/commands',
    'skills_dir': '{claude_dir}/skills',
}
