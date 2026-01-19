"""
Cross-platform environment setup for Claude Code.
Downloads and configures development tools for Claude Code based on YAML configuration.
"""

# /// script
# dependencies = [
#   "pyyaml",
# ]
# ///

import argparse
import contextlib
import glob as glob_module
import json
import os
import platform
import re
import shlex
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import cast
from urllib.request import Request
from urllib.request import urlopen

import yaml

# Import pwd module for Unix-like systems (used for detecting real user home under sudo)
# The import happens here but pwd is used in get_real_user_home() function
if sys.platform != 'win32':
    pass  # Used in get_real_user_home() for resolving sudo user's home directory

# Configuration inheritance constants
MAX_INHERITANCE_DEPTH = 10
INHERIT_KEY = 'inherit'

# OS environment variables constants
OS_ENV_VARIABLES_KEY = 'os-env-variables'
ENV_VAR_MARKER_START = '# >>> claude-code-toolbox >>>'
ENV_VAR_MARKER_END = '# <<< claude-code-toolbox <<<'

# Platform-specific imports with proper type checking support
if sys.platform == 'win32':
    import winreg
elif TYPE_CHECKING:
    # This allows type checkers on non-Windows platforms to understand winreg types
    import winreg  # noqa: F401


# Helper function to detect if we're running in pytest
def is_running_in_pytest() -> bool:
    """Check if the script is running under pytest.

    Returns:
        True if running under pytest, False otherwise.
    """
    return 'pytest' in sys.modules or 'py.test' in sys.argv[0]


def is_debug_enabled() -> bool:
    """Check if debug logging is enabled via environment variable.

    Returns:
        True if CLAUDE_CODE_TOOLBOX_DEBUG is set to '1', 'true', or 'yes' (case-insensitive)
    """
    debug_value = os.environ.get('CLAUDE_CODE_TOOLBOX_DEBUG', '').lower()
    return debug_value in ('1', 'true', 'yes')


def debug_log(message: str) -> None:
    """Log debug message if debug mode is enabled.

    Args:
        message: Debug message to log
    """
    if is_debug_enabled():
        # Use distinct prefix for easy filtering
        print(f'  [DEBUG] {message}', file=sys.stderr)


# Windows UAC elevation helper functions
def is_admin() -> bool:
    """Check if running with admin privileges on Windows.

    Returns:
        True if running as admin or not on Windows, False otherwise.
    """
    if platform.system() != 'Windows':
        return True  # Not Windows, no admin check needed

    try:
        import ctypes

        # Use getattr to access Windows-specific attributes dynamically
        # This prevents type checkers from failing on non-Windows platforms
        windll = getattr(ctypes, 'windll', None)
        if windll is None:
            return False
        shell32 = getattr(windll, 'shell32', None)
        if shell32 is None:
            return False
        is_user_admin = getattr(shell32, 'IsUserAnAdmin', None)
        if is_user_admin is None:
            return False
        return bool(is_user_admin())
    except Exception:
        return False


def request_admin_elevation(script_args: list[str] | None = None) -> None:
    """Re-launch script with UAC elevation on Windows.

    Args:
        script_args: Optional list of arguments to pass to elevated script.
    """
    if platform.system() != 'Windows':
        return

    try:
        import ctypes

        # Collect critical environment variables to pass to elevated process
        env_vars_to_pass: list[str] = []
        critical_env_vars = [
            'CLAUDE_ENV_CONFIG',
            'GITHUB_TOKEN',
            'GITLAB_TOKEN',
            'REPO_TOKEN',
            'CLAUDE_VERSION',
        ]

        for var_name in critical_env_vars:
            var_value = os.environ.get(var_name)
            if var_value:
                # Don't escape here - we'll handle escaping when building the params string
                env_vars_to_pass.append(f'--env-{var_name}={var_value}')

        # Build command line with script path, environment variables, then original arguments
        # Important: sys.argv[0] is the script path, sys.argv[1:] are the actual arguments
        # Add special flag to indicate UAC elevation created a new window
        uac_flag = ['--elevated-via-uac']
        if script_args:
            # When script_args is provided, use it instead of sys.argv[1:]
            all_args = [sys.argv[0]] + env_vars_to_pass + uac_flag + script_args
        else:
            # Use original arguments (excluding script path)
            all_args = [sys.argv[0]] + env_vars_to_pass + uac_flag + sys.argv[1:]

        # Build parameters string with proper quoting for Windows
        # Quote each argument that contains spaces or special characters
        params_list: list[str] = []
        for arg in all_args:
            # Always quote arguments with = to ensure proper parsing
            if ' ' in arg or '"' in arg or '=' in arg or arg.startswith('--env-'):
                # For Windows command line, we need to escape quotes properly
                # Use \" for quotes inside quoted strings
                escaped_arg = arg.replace('"', '\\"')
                quoted_arg = f'"{escaped_arg}"'
                params_list.append(quoted_arg)
            else:
                params_list.append(arg)
        params = ' '.join(params_list)

        # Use getattr to access Windows-specific attributes dynamically
        windll = getattr(ctypes, 'windll', None)
        if windll is None:
            return
        shell32 = getattr(windll, 'shell32', None)
        if shell32 is None:
            return
        shell_execute_w = getattr(shell32, 'ShellExecuteW', None)
        if shell_execute_w is None:
            return

        # Request elevation
        result = shell_execute_w(
            None,
            'runas',
            sys.executable,
            params,
            None,
            1,
        )

        # Exit current process if elevation was requested
        if result > 32:  # Success
            # Show message that elevated window is opening
            print()
            info('Administrator privileges granted!')
            info('A new window is opening with elevated privileges...')
            info('Please check the new window to see the setup progress.')
            print()

            # Wait briefly to ensure elevated process starts
            time.sleep(1.0)
            # Exit the non-elevated process so only the elevated one continues
            sys.exit(0)
        else:
            # Elevation was denied or failed
            error('Administrator elevation was denied')
            error('Installation cannot proceed without administrator privileges')
            error('')
            error('Please run this script as administrator manually:')
            error('  1. Right-click on your terminal')
            error('  2. Select "Run as administrator"')
            error('  3. Run the setup command again')
            sys.exit(1)

    except Exception as e:
        # If elevation fails due to an error, report it
        error(f'Failed to request elevation: {e}')
        error('Please run this script as administrator manually')
        sys.exit(1)


def check_admin_needed(config: dict[str, Any], args: argparse.Namespace) -> bool:
    """Check if admin rights are needed for the current operation.

    Args:
        config: Configuration dictionary.
        args: Command line arguments.

    Returns:
        True if admin needed, False otherwise.
    """
    if platform.system() != 'Windows':
        return False

    # Check if Claude Code installation is needed
    if not args.skip_install:
        # Installing Node.js and Git typically requires admin on Windows
        return True

    # Check for dependencies that need admin
    dependencies = config.get('dependencies', {})
    if dependencies:
        # Check Windows-specific dependencies
        win_deps = dependencies.get('windows', [])
        common_deps = dependencies.get('common', [])
        all_deps = win_deps + common_deps

        for dep in all_deps:
            # Check for commands that typically need admin
            if 'winget' in dep and '--scope machine' in dep:
                return True
            if 'npm install -g' in dep:
                # Global npm installs may need admin depending on Node.js installation
                return True

    return False


# ANSI color codes for pretty output
class Colors:
    """ANSI color codes for terminal output."""

    _RED = '\033[0;31m'
    _GREEN = '\033[0;32m'
    _YELLOW = '\033[1;33m'
    _BLUE = '\033[0;34m'
    _CYAN = '\033[0;36m'
    _NC = '\033[0m'  # No Color
    _BOLD = '\033[1m'

    # Check if colors should be disabled
    _NO_COLOR = platform.system() == 'Windows' and not os.environ.get('WT_SESSION')

    # Public color attributes (computed properties)
    RED = '' if _NO_COLOR else _RED
    GREEN = '' if _NO_COLOR else _GREEN
    YELLOW = '' if _NO_COLOR else _YELLOW
    BLUE = '' if _NO_COLOR else _BLUE
    CYAN = '' if _NO_COLOR else _CYAN
    NC = '' if _NO_COLOR else _NC
    BOLD = '' if _NO_COLOR else _BOLD

    @classmethod
    def strip(cls) -> None:
        """Strip ANSI color codes for environments that don't support them."""
        if platform.system() == 'Windows' and not os.environ.get('WT_SESSION'):
            # Use setattr to avoid pyright's constant redefinition error
            for attr in ['RED', 'GREEN', 'YELLOW', 'BLUE', 'CYAN', 'NC', 'BOLD']:
                setattr(cls, attr, '')


# Logging functions
def info(msg: str) -> None:
    """Print info message."""
    print(f'  {Colors.YELLOW}INFO:{Colors.NC} {msg}')


def success(msg: str) -> None:
    """Print success message."""
    print(f'  {Colors.GREEN}OK:{Colors.NC} {msg}')


def warning(msg: str) -> None:
    """Print warning message."""
    print(f'  {Colors.YELLOW}WARN:{Colors.NC} {msg}')


def error(msg: str) -> None:
    """Print error message."""
    print(f'  {Colors.RED}ERROR:{Colors.NC} {msg}', file=sys.stderr)


def header(environment_name: str = 'Development') -> None:
    """Print setup header."""
    print()
    print(f'{Colors.BLUE}========================================================================{Colors.NC}')
    print(f'{Colors.BLUE}     Claude Code {environment_name} Environment Setup{Colors.NC}')
    print(f'{Colors.BLUE}========================================================================{Colors.NC}')
    print()


def run_command(cmd: list[str], capture_output: bool = True, **kwargs: Any) -> subprocess.CompletedProcess[str]:
    """Run a command and return the result."""
    try:
        # On Windows, resolve batch files (.cmd, .bat) to their full path
        # This is necessary because subprocess.run() with shell=False cannot find
        # batch files directly - it only finds .exe files
        if sys.platform == 'win32' and cmd:
            resolved = shutil.which(cmd[0])
            if resolved:
                cmd = [resolved] + cmd[1:]

        return subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            **kwargs,
        )
    except FileNotFoundError:
        return subprocess.CompletedProcess(cmd, 1, '', f'Command not found: {cmd[0]}')


def find_command(cmd: str) -> str | None:
    """Find a command in PATH."""
    return shutil.which(cmd)


def find_command_robust(cmd: str, fallback_paths: list[str] | None = None) -> str | None:
    """Find a command with robust platform-specific fallback search.

    Args:
        cmd: Command name to find (e.g., 'claude', 'node')
        fallback_paths: Optional list of additional paths to check

    Returns:
        Full path to command if found, None otherwise
    """
    # Primary: Use standard PATH search with retry for PATH synchronization
    for attempt in range(2):
        cmd_path = shutil.which(cmd)
        if cmd_path:
            # Normalize extension case on Windows for Git Bash compatibility
            # shutil.which() uses Windows PATHEXT which has uppercase extensions (.EXE)
            # but Git Bash is case-sensitive and needs lowercase (.exe)
            if sys.platform == 'win32':
                path_obj = Path(cmd_path)
                ext = path_obj.suffix
                if ext.upper() in ['.EXE', '.CMD', '.BAT', '.COM'] and ext != ext.lower():
                    cmd_path = str(path_obj.with_suffix(ext.lower()))
            return cmd_path

        # Brief delay for PATH synchronization (especially on Windows)
        if attempt == 0:
            time.sleep(0.5)

    # Secondary: Platform-specific common locations
    system = platform.system()
    common_paths: list[str] = []

    if system == 'Windows':
        if cmd == 'claude':
            common_paths = [
                # Native installer location (checked first)
                os.path.expandvars(r'%USERPROFILE%\.local\bin\claude.exe'),
                os.path.expandvars(r'%USERPROFILE%\.local\bin\claude'),
                # npm global installation paths
                os.path.expandvars(r'%APPDATA%\npm\claude.cmd'),
                os.path.expandvars(r'%APPDATA%\npm\claude'),
                os.path.expandvars(r'%ProgramFiles%\nodejs\claude.cmd'),
                os.path.expandvars(r'%LOCALAPPDATA%\Programs\claude\claude.exe'),
            ]
        elif cmd == 'node':
            common_paths = [
                # Official installer paths
                r'C:\Program Files\nodejs\node.exe',
                r'C:\Program Files (x86)\nodejs\node.exe',
                # nvm-windows: %APPDATA%\nvm\<version>\node.exe
                os.path.expandvars(r'%APPDATA%\nvm'),
                # fnm: %LOCALAPPDATA%\fnm_multishells\<id>\node.exe
                os.path.expandvars(r'%LOCALAPPDATA%\fnm_multishells'),
                # volta: %USERPROFILE%\.volta\bin\node.exe
                os.path.expandvars(r'%USERPROFILE%\.volta\bin\node.exe'),
                # scoop: %USERPROFILE%\scoop\apps\nodejs\current\node.exe
                os.path.expandvars(r'%USERPROFILE%\scoop\apps\nodejs\current\node.exe'),
                # scoop (alternative): %USERPROFILE%\scoop\shims\node.exe
                os.path.expandvars(r'%USERPROFILE%\scoop\shims\node.exe'),
                # chocolatey: C:\ProgramData\chocolatey\bin\node.exe
                r'C:\ProgramData\chocolatey\bin\node.exe',
            ]
        elif cmd == 'npm':
            common_paths = [
                r'C:\Program Files\nodejs\npm.cmd',
                r'C:\Program Files (x86)\nodejs\npm.cmd',
            ]
    else:
        # Unix-like systems
        if cmd == 'claude':
            common_paths = [
                str(Path.home() / '.npm-global' / 'bin' / 'claude'),
                '/usr/local/bin/claude',
                '/usr/bin/claude',
            ]
        elif cmd == 'node':
            common_paths = [
                '/usr/local/bin/node',
                '/usr/bin/node',
            ]
        elif cmd == 'npm':
            common_paths = [
                '/usr/local/bin/npm',
                '/usr/bin/npm',
            ]

    # Check common locations

    for path in common_paths:
        expanded = os.path.expandvars(path)
        expanded_path = Path(expanded)

        # Direct file check
        if expanded_path.exists() and expanded_path.is_file():
            return str(expanded_path.resolve())

        # Directory-based search for version managers (nvm, fnm)
        # These store node.exe in subdirectories like: nvm/<version>/node.exe
        if expanded_path.exists() and expanded_path.is_dir() and cmd == 'node':
            # Search for node.exe in subdirectories (one level deep)
            pattern = str(expanded_path / '*' / 'node.exe')
            matches = glob_module.glob(pattern)
            if matches:
                # Return the most recently modified (likely active version)
                matches.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                return str(Path(matches[0]).resolve())

    # Tertiary: Custom fallback paths
    if fallback_paths:
        for path in fallback_paths:
            expanded = os.path.expandvars(path)
            if Path(expanded).exists():
                return str(Path(expanded).resolve())

    return None


def find_bash_windows() -> str | None:
    """Find Git Bash on Windows.

    Git Bash is required for Claude Code on Windows and provides consistent
    cross-platform bash behavior for CLI command execution.

    Returns:
        Full path to bash.exe if found, None otherwise.

    Note:
        Prioritizes Git Bash locations over PATH search to avoid
        accidentally finding WSL's bash.exe at C:\\Windows\\System32.
    """
    debug_log('find_bash_windows() called')

    # Check CLAUDE_CODE_GIT_BASH_PATH env var first
    env_path = os.environ.get('CLAUDE_CODE_GIT_BASH_PATH')
    debug_log(f'CLAUDE_CODE_GIT_BASH_PATH={env_path}')
    if env_path and Path(env_path).exists():
        debug_log(f'Found via env var: {env_path}')
        return str(Path(env_path).resolve())

    # Check Git Bash common locations FIRST (before PATH search)
    # This prevents accidentally finding WSL's bash.exe in System32
    common_paths = [
        r'C:\Program Files\Git\bin\bash.exe',
        r'C:\Program Files\Git\usr\bin\bash.exe',
        r'C:\Program Files (x86)\Git\bin\bash.exe',
        r'C:\Program Files (x86)\Git\usr\bin\bash.exe',
        os.path.expandvars(r'%LOCALAPPDATA%\Programs\Git\bin\bash.exe'),
        os.path.expandvars(r'%LOCALAPPDATA%\Programs\Git\usr\bin\bash.exe'),
    ]

    for i, path in enumerate(common_paths):
        expanded = os.path.expandvars(path)
        exists = Path(expanded).exists()
        debug_log(f'Common path [{i}]: {expanded} - exists={exists}')
        if exists:
            debug_log(f'Found via common path: {expanded}')
            return str(Path(expanded).resolve())

    # Fall back to PATH search (may find Git Bash if installed elsewhere)
    bash_path = find_command('bash.exe')
    debug_log(f'PATH search result: {bash_path}')
    if bash_path:
        # Skip WSL bash in System32/SysWOW64
        bash_lower = bash_path.lower()
        is_wsl = 'system32' in bash_lower or 'syswow64' in bash_lower
        debug_log(f'Is WSL bash: {is_wsl}')
        if not is_wsl:
            debug_log(f'Returning PATH bash: {bash_path}')
            return bash_path
        debug_log('Skipping WSL bash')

    debug_log('No suitable bash found, returning None')
    return None


def run_bash_command(
    command: str,
    capture_output: bool = True,
    login_shell: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Execute command via bash (Git Bash on Windows, native bash on Unix).

    Provides consistent cross-platform behavior for CLI command execution.
    Uses Git Bash on Windows and native bash on Unix systems.

    Args:
        command: The bash command string to execute
        capture_output: Whether to capture stdout/stderr
        login_shell: Whether to use login shell (-l flag)

    Returns:
        subprocess.CompletedProcess with the result
    """
    debug_log('run_bash_command() called')
    cmd_preview = command[:200] + '...' if len(command) > 200 else command
    debug_log(f'  command: {cmd_preview}')
    debug_log(f'  capture_output: {capture_output}')
    debug_log(f'  login_shell: {login_shell}')

    if sys.platform == 'win32':
        bash_path = find_bash_windows()
    else:
        bash_path = shutil.which('bash')

    debug_log(f'bash_path resolved to: {bash_path}')

    if not bash_path:
        error('Bash not found!')
        debug_log('ERROR: Returning early - bash not found')
        return subprocess.CompletedProcess([], 1, '', 'bash not found')

    args = [bash_path]
    if login_shell:
        args.append('-l')
    args.extend(['-c', command])

    debug_log(f'Executing: {args}')

    try:
        result = subprocess.run(args, capture_output=capture_output, text=True)
        debug_log(f'Exit code: {result.returncode}')
        if capture_output:
            stdout_preview = result.stdout[:500] if result.stdout else '(empty)'
            stderr_preview = result.stderr[:500] if result.stderr else '(empty)'
            debug_log(f'stdout: {stdout_preview}')
            debug_log(f'stderr: {stderr_preview}')
        return result
    except FileNotFoundError as e:
        debug_log(f'FileNotFoundError: {e}')
        return subprocess.CompletedProcess(args, 1, '', f'bash not found: {bash_path}')


def convert_to_unix_path(windows_path: str) -> str:
    """Convert a Windows path to Git Bash (MSYS2/Cygwin) Unix-style path.

    Git Bash uses Unix-style paths where drive letters are represented as
    /driveletter (lowercase). This function converts Windows paths like
    'C:\\Users\\name\\file.exe' to '/c/Users/name/file.exe'.

    Args:
        windows_path: A Windows-style path (may contain backslashes and drive letters)

    Returns:
        Unix-style path suitable for Git Bash execution

    Examples:
        >>> convert_to_unix_path(r'C:\\Users\\Name\\.local\\bin\\claude.EXE')
        '/c/Users/Name/.local/bin/claude.EXE'
        >>> convert_to_unix_path(r'C:\\Program Files\\nodejs')
        '/c/Program Files/nodejs'
        >>> convert_to_unix_path('/already/unix/path')
        '/already/unix/path'
    """
    if not windows_path:
        return windows_path

    # If already a Unix path (starts with / and no drive letter), return as-is
    if windows_path.startswith('/') and len(windows_path) > 1 and windows_path[1] != ':':
        return windows_path

    # Normalize backslashes to forward slashes
    path = windows_path.replace('\\', '/')

    # Handle drive letter (e.g., C: -> /c)
    if len(path) >= 2 and path[1] == ':':
        drive_letter = path[0].lower()
        path = f'/{drive_letter}{path[2:]}'

    return path


def convert_path_env_to_unix(windows_path_env: str) -> str:
    """Convert Windows PATH environment variable to Git Bash Unix-style format.

    Windows PATH uses semicolon (;) as separator and Windows-style paths.
    Git Bash PATH uses colon (:) as separator and Unix-style paths.

    Args:
        windows_path_env: Windows PATH string (semicolon-separated)

    Returns:
        Unix-style PATH string (colon-separated) suitable for Git Bash

    Examples:
        >>> convert_path_env_to_unix(r'C:\\Windows;C:\\Program Files\\nodejs')
        '/c/Windows:/c/Program Files/nodejs'
    """
    if not windows_path_env:
        return windows_path_env

    # Split by semicolon (Windows PATH separator)
    paths = windows_path_env.split(';')

    # Convert each path to Unix format
    unix_paths = [convert_to_unix_path(p.strip()) for p in paths if p.strip()]

    # Join with colon (Unix PATH separator)
    return ':'.join(unix_paths)


def get_bash_preferred_command(cmd_path: str) -> str:
    """Get the preferred command path for Git Bash execution on Windows.

    When running commands through Git Bash on Windows, .cmd/.bat files can cause
    issues with special characters in arguments (like & in URLs) because CMD.exe
    parses these characters as command separators before the batch script receives them.

    npm typically creates both a .cmd file and an extensionless shell script in the
    global bin directory. This function checks if an extensionless version exists
    and returns it instead of the .cmd version for Git Bash compatibility.

    Args:
        cmd_path: Path to a command (may be .cmd/.bat or extensionless)

    Returns:
        Path to the preferred command for Git Bash execution:
        - If input is .cmd/.bat and extensionless version exists, return extensionless
        - Otherwise return original path unchanged

    Examples:
        >>> get_bash_preferred_command(r'C:\\Users\\name\\AppData\\Roaming\\npm\\claude.cmd')
        'C:\\\\Users\\\\name\\\\AppData\\\\Roaming\\\\npm\\\\claude'  # if 'claude' exists
        >>> get_bash_preferred_command(r'C:\\Users\\name\\.local\\bin\\claude.exe')
        'C:\\\\Users\\\\name\\.local\\\\bin\\\\claude.exe'  # unchanged (not .cmd)
    """
    if not cmd_path:
        return cmd_path

    path_obj = Path(cmd_path)
    suffix_lower = path_obj.suffix.lower()

    # Only process .cmd and .bat files (Windows batch files)
    if suffix_lower not in ['.cmd', '.bat']:
        return cmd_path

    # Check if extensionless version exists in the same directory
    extensionless_path = path_obj.with_suffix('')

    if extensionless_path.exists() and extensionless_path.is_file():
        debug_log(f'Preferring extensionless script over {suffix_lower}: {extensionless_path}')
        return str(extensionless_path)

    # No extensionless alternative found, return original
    return cmd_path


def expand_tildes_in_command(command: str) -> str:
    """Expand tilde paths in a shell command.

    When commands are executed via subprocess with shell=False or wrapped in bash -c,
    the shell's tilde expansion doesn't occur. This function explicitly expands
    tilde paths to their absolute equivalents using os.path.expanduser.

    Args:
        command: Shell command that may contain tilde paths

    Returns:
        Command with expanded tilde paths

    Examples:
        >>> expand_tildes_in_command("sed -i '/pattern/d' ~/.bashrc")
        "sed -i '/pattern/d' /home/user/.bashrc"

        >>> expand_tildes_in_command("echo 'text' >> ~/.config/file")
        "echo 'text' >> /home/user/.config/file"
    """

    # Pattern matches ~ and ~username paths
    # Matches: ~ followed by optional username, then slash and path components
    # Examples: ~/.bashrc, ~/dir/file, ~user/.config
    tilde_pattern = r'(~[^/\s]*(?:/[^\s]*)?)'

    def expand_match(match: re.Match[str]) -> str:
        """Expand a single tilde path match."""
        path = match.group(1)
        try:
            # os.path.expanduser handles both ~ and ~username
            expanded = os.path.expanduser(path)
            # Only return expanded path if expansion actually occurred
            # This prevents expanding tildes in strings like "~test" that aren't paths
            if expanded != path:
                return expanded
            return path
        except Exception:
            # If expansion fails for any reason, return original path
            return path

    return re.sub(tilde_pattern, expand_match, command)


def add_directory_to_windows_path(directory: str) -> tuple[bool, str]:
    """Add a directory to the Windows user PATH environment variable.

    This function properly reads the current PATH from the Windows registry,
    checks if the directory is already present, and adds it if needed.
    It handles PATH length limits and provides detailed error messages.

    Args:
        directory: The directory path to add to PATH (will be normalized)

    Returns:
        tuple[bool, str]: (success, message) - success status and detailed message

    Note:
        - Only works on Windows (returns False, error message on other platforms)
        - Modifies the user PATH variable (HKEY_CURRENT_USER), not system PATH
        - Updates both the registry and current session's os.environ['PATH']
        - Windows has a 1024-character limit for environment variables via setx
        - New terminals must be restarted to see the persistent changes
    """
    if sys.platform == 'win32':
        try:
            # Normalize the directory path
            normalized_dir = str(Path(directory).resolve())

            # CRITICAL: Prevent adding temporary directory paths to PATH
            # Temporary directories cause PATH pollution and don't persist
            temp_dir_env = os.environ.get('TEMP', '').lower()
            temp_dir_alt = os.environ.get('TMP', '').lower()
            normalized_lower = normalized_dir.lower()

            # Check if path is in a temp directory
            if temp_dir_env and temp_dir_env in normalized_lower:
                return (
                    False,
                    f'Refusing to add temporary directory to PATH: {normalized_dir}',
                )
            if temp_dir_alt and temp_dir_alt in normalized_lower:
                return (
                    False,
                    f'Refusing to add temporary directory to PATH: {normalized_dir}',
                )

            # Additional check for common temp path patterns
            if r'\appdata\local\temp\tmp' in normalized_lower:
                return (
                    False,
                    f'Refusing to add temporary directory to PATH: {normalized_dir}',
                )

            # Validate it's the expected .local\bin directory
            expected_local_bin = str(Path.home() / '.local' / 'bin')
            if normalized_dir != expected_local_bin and not normalized_lower.startswith(str(Path.home()).lower()):
                # Allow only paths under user's home directory
                return (
                    False,
                    f'Refusing to add non-home directory to PATH: {normalized_dir}',
                )

            # Open the registry key for user environment variables
            # HKEY_CURRENT_USER\Environment contains user-level environment variables
            reg_key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r'Environment',
                0,
                winreg.KEY_READ | winreg.KEY_WRITE,
            )

            try:
                # Read current PATH value from registry
                current_path, _ = winreg.QueryValueEx(reg_key, 'PATH')
            except FileNotFoundError:
                # PATH variable doesn't exist in user registry, create it
                current_path = ''

            # Split PATH into components and normalize them for comparison
            # Windows PATH separator is semicolon
            path_components = [p.strip() for p in current_path.split(';') if p.strip()]
            normalized_components = [str(Path(p).resolve()) if Path(p).exists() else p for p in path_components]

            # Check if directory is already in PATH (case-insensitive on Windows)
            normalized_dir_lower = normalized_dir.lower()
            already_in_path = any(comp.lower() == normalized_dir_lower for comp in normalized_components)

            if already_in_path:
                winreg.CloseKey(reg_key)
                # Still update current session in case it's not there yet
                session_path = os.environ.get('PATH', '')
                if normalized_dir not in session_path:
                    os.environ['PATH'] = f'{normalized_dir};{session_path}'
                return True, f'Directory already in PATH: {normalized_dir}'

            # Add directory to PATH (prepend for higher priority)
            new_path = f'{normalized_dir};{current_path}' if current_path else normalized_dir

            # Check PATH length limit (setx has 1024 character limit)
            # Registry itself can hold longer values, but setx command is limited
            if len(new_path) > 1024:
                winreg.CloseKey(reg_key)
                return (
                    False,
                    (
                        f'PATH too long ({len(new_path)} chars, limit 1024). '
                        f'Please manually add: {normalized_dir}'
                    ),
                )

            # Write new PATH to registry
            winreg.SetValueEx(reg_key, 'PATH', 0, winreg.REG_EXPAND_SZ, new_path)
            winreg.CloseKey(reg_key)

            # Update current session's PATH
            os.environ['PATH'] = f'{normalized_dir};{os.environ.get("PATH", "")}'

            # Broadcast WM_SETTINGCHANGE to notify other processes
            # This is done via setx which broadcasts the change
            # We use a dummy variable to trigger the broadcast without modifying anything
            subprocess.run(['setx', 'CLAUDE_TOOLBOX_TEMP', 'temp'], capture_output=True, check=False)
            subprocess.run(
                ['reg', 'delete', r'HKCU\Environment', '/v', 'CLAUDE_TOOLBOX_TEMP', '/f'],
                capture_output=True,
                check=False,
            )

            return True, f'Successfully added to PATH: {normalized_dir}'

        except PermissionError:
            return False, 'Permission denied. Try running with administrator privileges.'
        except Exception as e:
            return False, f'Failed to update PATH: {e}'
    else:
        return False, 'This function only works on Windows'


def ensure_local_bin_in_path() -> None:
    """Ensure .local/bin is in PATH for Windows systems.

    This is called early to prevent uv tool warnings about PATH.
    On Windows, .local/bin must be added to PATH before installing dependencies
    with 'uv tool install', otherwise uv displays warnings.

    Note:
        - Only runs on Windows (no-op on other platforms)
        - Creates .local/bin directory if it doesn't exist
        - Adds directory to Windows registry PATH
        - Updates current session's os.environ['PATH']
        - Provides user feedback only if PATH was newly added
    """
    if platform.system() != 'Windows':
        return

    local_bin = Path.home() / '.local' / 'bin'
    local_bin.mkdir(parents=True, exist_ok=True)

    path_success, path_message = add_directory_to_windows_path(str(local_bin))

    if path_success and 'already in PATH' not in path_message:
        info('Pre-configured .local/bin in PATH for tool installations')


def cleanup_temp_paths_from_registry() -> tuple[int, list[str]]:
    """Remove temporary directory paths from Windows PATH registry.

    This function scans the user's PATH environment variable and removes any
    entries that point to temporary directories. These paths are typically
    added by mistake when scripts execute from temporary locations.

    Returns:
        tuple[int, list[str]]: (count of removed paths, list of removed path strings)

    Note:
        - Only works on Windows (returns (0, []) on other platforms)
        - Modifies the user PATH variable (HKEY_CURRENT_USER), not system PATH
        - Preserves the correct ~/.local/bin path
        - Automatically detects temp paths using TEMP/TMP environment variables
        - Also removes paths matching common temp patterns
    """
    if sys.platform == 'win32':
        try:
            removed_paths: list[str] = []
            temp_dir_env = os.environ.get('TEMP', '').lower()
            temp_dir_alt = os.environ.get('TMP', '').lower()

            # Open the registry key for user environment variables
            reg_key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r'Environment',
                0,
                winreg.KEY_READ | winreg.KEY_WRITE,
            )

            try:
                current_path, _ = winreg.QueryValueEx(reg_key, 'PATH')
            except FileNotFoundError:
                # PATH variable doesn't exist, nothing to clean
                winreg.CloseKey(reg_key)
                return 0, []

            # Split PATH into components
            path_components = [p.strip() for p in current_path.split(';') if p.strip()]
            clean_components: list[str] = []

            for path_entry in path_components:
                path_lower = path_entry.lower()

                # Check if this is a temporary directory path
                is_temp_path = False

                # Check against TEMP environment variable
                if temp_dir_env and temp_dir_env in path_lower:
                    is_temp_path = True

                # Check against TMP environment variable
                if temp_dir_alt and temp_dir_alt in path_lower:
                    is_temp_path = True

                # Check for common temp path patterns
                if r'\appdata\local\temp\tmp' in path_lower:
                    is_temp_path = True

                if is_temp_path:
                    removed_paths.append(path_entry)
                else:
                    clean_components.append(path_entry)

            # Update PATH if any temp paths were found
            if removed_paths:
                new_path = ';'.join(clean_components)
                winreg.SetValueEx(reg_key, 'PATH', 0, winreg.REG_EXPAND_SZ, new_path)

                # Broadcast WM_SETTINGCHANGE to notify other processes
                subprocess.run(['setx', 'CLAUDE_TOOLBOX_TEMP', 'temp'], capture_output=True, check=False)
                subprocess.run(
                    ['reg', 'delete', r'HKCU\Environment', '/v', 'CLAUDE_TOOLBOX_TEMP', '/f'],
                    capture_output=True,
                    check=False,
                )

            winreg.CloseKey(reg_key)
            return (len(removed_paths), removed_paths)

        except Exception as e:
            # Log error but don't fail the entire setup
            warning(f'Failed to clean temporary paths from registry: {e}')
            return 0, []
    else:
        return 0, []


def refresh_path_from_registry() -> bool:
    """Refresh os.environ['PATH'] from Windows registry.

    Reads both system and user PATH values from the Windows registry and
    updates os.environ['PATH'] with the combined value. This addresses
    the Windows PATH propagation bug where installations (e.g., winget)
    update the registry but running processes don't see the changes.

    Registry sources:
        - System PATH: HKEY_LOCAL_MACHINE\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Environment
        - User PATH: HKEY_CURRENT_USER\\Environment

    Returns:
        True if PATH was successfully refreshed, False otherwise.

    Note:
        - Only works on Windows (returns True on other platforms as no-op)
        - Handles REG_EXPAND_SZ values with environment variable expansion
        - Combines system PATH + user PATH (system first for security)
        - Logs info message when PATH is refreshed
    """
    if sys.platform == 'win32':
        try:

            def expand_env_vars(value: str) -> str:
                """Expand environment variables like %USERPROFILE% in registry values."""
                # Use os.path.expandvars which handles %VAR% on Windows
                return os.path.expandvars(value)

            system_path = ''
            user_path = ''

            # Read system PATH from HKEY_LOCAL_MACHINE
            try:
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
                    0,
                    winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                ) as key:
                    raw_value, reg_type = winreg.QueryValueEx(key, 'Path')
                    if raw_value:
                        # Expand environment variables if REG_EXPAND_SZ
                        system_path = expand_env_vars(raw_value) if reg_type == winreg.REG_EXPAND_SZ else raw_value
            except FileNotFoundError:
                # System PATH key doesn't exist (very unusual)
                pass
            except PermissionError:
                # May not have permission to read system PATH
                warning('Permission denied reading system PATH from registry')
            except OSError as e:
                warning(f'Failed to read system PATH from registry: {e}')

            # Read user PATH from HKEY_CURRENT_USER
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r'Environment',
                    0,
                    winreg.KEY_READ,
                ) as key:
                    raw_value, reg_type = winreg.QueryValueEx(key, 'Path')
                    if raw_value:
                        # Expand environment variables if REG_EXPAND_SZ
                        user_path = expand_env_vars(raw_value) if reg_type == winreg.REG_EXPAND_SZ else raw_value
            except FileNotFoundError:
                # User PATH doesn't exist (possible on fresh systems)
                pass
            except PermissionError:
                warning('Permission denied reading user PATH from registry')
            except OSError as e:
                warning(f'Failed to read user PATH from registry: {e}')

            # Combine paths: system PATH first, then user PATH
            # This matches Windows behavior where system PATH takes precedence
            if system_path and user_path:
                new_path = f'{system_path};{user_path}'
            elif system_path:
                new_path = system_path
            elif user_path:
                new_path = user_path
            else:
                # No PATH found in registry, keep current
                warning('No PATH found in registry, keeping current os.environ PATH')
                return False

            # Update os.environ with the refreshed PATH
            old_path = os.environ.get('PATH', '')
            if new_path != old_path:
                os.environ['PATH'] = new_path
                info('Refreshed PATH from Windows registry')
                return True
            # PATH unchanged, no need to log
            return True

        except Exception as e:
            warning(f'Failed to refresh PATH from registry: {e}')
            return False
    else:
        # Non-Windows platforms: no-op, return True
        return True


class FileValidator:
    """Validates file availability for both remote URLs and local paths.

    Handles authentication automatically based on the URL being validated,
    supporting GitHub and GitLab private repositories. For remote files,
    attempts HEAD request first, then falls back to Range request.

    Attributes:
        auth_param: Optional authentication parameter. Accepts token value
            (auto-detects header based on URL) or explicit header:value format.
    """

    def __init__(self, auth_param: str | None = None) -> None:
        """Initialize FileValidator.

        Args:
            auth_param: Optional auth parameter in format "header:value" or "header=value"
                       or just a token (will auto-detect header based on URL)
        """
        self.auth_param = auth_param
        self._validation_results: list[tuple[str, str, bool, str]] = []

    def validate_remote_url(self, url: str) -> tuple[bool, str]:
        """Validate a remote URL with per-URL authentication.

        Generates authentication headers specific to this URL (GitHub vs GitLab)
        and attempts validation using HEAD request, then Range request as fallback.

        Args:
            url: Remote URL to validate

        Returns:
            Tuple of (is_valid, method_used)
            method_used is 'HEAD', 'Range', or 'None'
        """
        # Convert GitLab web URLs to API format
        original_url = url
        if detect_repo_type(url) == 'gitlab' and '/-/raw/' in url:
            url = convert_gitlab_url_to_api(url)
            if url != original_url:
                info(f'Using API URL for validation: {url}')

        # Generate auth headers for THIS specific URL
        auth_headers = get_auth_headers(url, self.auth_param)

        # Try HEAD request first
        if self._check_with_head(url, auth_headers):
            return (True, 'HEAD')

        # Fallback to Range request
        if self._check_with_range(url, auth_headers):
            return (True, 'Range')

        return (False, 'None')

    def validate_local_path(self, path: str) -> tuple[bool, str]:
        """Validate a local file path.

        Args:
            path: Local file path to validate

        Returns:
            Tuple of (is_valid, 'Local')
        """
        local_path = Path(path)
        if local_path.exists() and local_path.is_file():
            return (True, 'Local')
        return (False, 'Local')

    def validate(self, url_or_path: str, is_remote: bool) -> tuple[bool, str]:
        """Validate a file, automatically choosing remote or local validation.

        Args:
            url_or_path: URL or local path to validate
            is_remote: True if this is a remote URL, False if local path

        Returns:
            Tuple of (is_valid, method_used)
        """
        if is_remote:
            return self.validate_remote_url(url_or_path)
        return self.validate_local_path(url_or_path)

    def _check_with_head(self, url: str, auth_headers: dict[str, str] | None) -> bool:
        """Check URL availability using HEAD request.

        Args:
            url: URL to check
            auth_headers: Optional authentication headers

        Returns:
            True if file is accessible, False otherwise
        """
        try:
            request = Request(url, method='HEAD')
            if auth_headers:
                for header, value in auth_headers.items():
                    request.add_header(header, value)

            try:
                response = urlopen(request)
                return bool(response.status == 200)
            except urllib.error.URLError as e:
                if 'SSL' in str(e) or 'certificate' in str(e).lower():
                    # Try with unverified SSL context
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    response = urlopen(request, context=ctx)
                    return bool(response.status == 200)
                return False
        except (urllib.error.HTTPError, Exception):
            return False

    def _check_with_range(self, url: str, auth_headers: dict[str, str] | None) -> bool:
        """Check URL availability using Range request.

        Args:
            url: URL to check
            auth_headers: Optional authentication headers

        Returns:
            True if file is accessible, False otherwise
        """
        try:
            request = Request(url)
            request.add_header('Range', 'bytes=0-0')
            if auth_headers:
                for header, value in auth_headers.items():
                    request.add_header(header, value)

            try:
                response = urlopen(request)
                # Accept both 200 (full content) and 206 (partial content)
                return response.status in (200, 206)
            except urllib.error.URLError as e:
                if 'SSL' in str(e) or 'certificate' in str(e).lower():
                    # Try with unverified SSL context
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    response = urlopen(request, context=ctx)
                    return response.status in (200, 206)
                return False
        except (urllib.error.HTTPError, Exception):
            return False

    @property
    def results(self) -> list[tuple[str, str, bool, str]]:
        """Get accumulated validation results."""
        return self._validation_results

    def add_result(self, file_type: str, original_path: str, is_valid: bool, method: str) -> None:
        """Record a validation result.

        Args:
            file_type: Type of file (agent, skill, hook, etc.)
            original_path: Original path from config
            is_valid: Whether validation passed
            method: Validation method used
        """
        self._validation_results.append((file_type, original_path, is_valid, method))

    def clear_results(self) -> None:
        """Clear accumulated validation results."""
        self._validation_results.clear()


def validate_all_config_files(
    config: dict[str, Any],
    config_source: str,
    auth_param: str | None = None,
) -> tuple[bool, list[tuple[str, str, bool, str]]]:
    """Validate all files in the configuration (both remote and local).

    Args:
        config: Environment configuration dictionary
        config_source: Source of the configuration (URL or path)
        auth_param: Optional authentication parameter

    Returns:
        Tuple of (all_valid, validation_results)
        validation_results is a list of (file_type, path, is_valid, method) tuples
    """
    files_to_check: list[tuple[str, str, str, bool]] = []
    results: list[tuple[str, str, bool, str]] = []

    # Create file validator - generates authentication per-URL for proper
    # handling of mixed repositories (e.g., GitHub + GitLab files)
    validator = FileValidator(auth_param)

    # Collect all files that need to be validated
    base_url = config.get('base-url')

    # Agents
    agents_raw = config.get('agents', [])
    if isinstance(agents_raw, list):
        # Cast to typed list for pyright
        agents_list = cast(list[object], agents_raw)
        for agent_item in agents_list:
            if isinstance(agent_item, str):
                resolved_path, is_remote = resolve_resource_path(agent_item, config_source, base_url)
                files_to_check.append(('agent', agent_item, resolved_path, is_remote))

    # Slash commands
    commands_raw = config.get('slash-commands', [])
    if isinstance(commands_raw, list):
        # Cast to typed list for pyright
        commands_list = cast(list[object], commands_raw)
        for cmd_item in commands_list:
            if isinstance(cmd_item, str):
                resolved_path, is_remote = resolve_resource_path(cmd_item, config_source, base_url)
                files_to_check.append(('slash_command', cmd_item, resolved_path, is_remote))

    # System prompts from command-defaults
    command_defaults = config.get('command-defaults', {})
    if command_defaults and command_defaults.get('system-prompt'):
        prompt = command_defaults['system-prompt']
        resolved_path, is_remote = resolve_resource_path(prompt, config_source, base_url)
        files_to_check.append(('system_prompt', prompt, resolved_path, is_remote))

    # Hooks files
    hooks = config.get('hooks', {})
    if isinstance(hooks, dict):
        hooks_typed = cast(dict[str, Any], hooks)
        hook_files_raw = hooks_typed.get('files', [])
        if isinstance(hook_files_raw, list):
            # Cast to typed list for pyright
            hook_files_list = cast(list[object], hook_files_raw)
            for hook_file_item in hook_files_list:
                if isinstance(hook_file_item, str):
                    resolved_path, is_remote = resolve_resource_path(hook_file_item, config_source, base_url)
                    files_to_check.append(('hook', hook_file_item, resolved_path, is_remote))

    # Files to download
    files_to_download_raw = config.get('files-to-download', [])
    if isinstance(files_to_download_raw, list):
        files_list = cast(list[object], files_to_download_raw)
        for file_item in files_list:
            if isinstance(file_item, dict):
                file_dict = cast(dict[str, Any], file_item)
                source = file_dict.get('source')
                if source and isinstance(source, str):
                    resolved_path, is_remote = resolve_resource_path(source, config_source, base_url)
                    files_to_check.append(('file_download', source, resolved_path, is_remote))

    # Skills
    skills_raw = config.get('skills', [])
    if isinstance(skills_raw, list):
        skills_list = cast(list[object], skills_raw)
        for skill_item in skills_list:
            if isinstance(skill_item, dict):
                skill_dict = cast(dict[str, Any], skill_item)
                skill_base = skill_dict.get('base', '')
                skill_files = skill_dict.get('files', [])

                if isinstance(skill_files, list):
                    skill_files_list = cast(list[object], skill_files)
                    for skill_file_item in skill_files_list:
                        if isinstance(skill_file_item, str):
                            # Build full path for validation
                            if skill_base.startswith(('http://', 'https://')):
                                # Convert tree/blob URLs to raw URLs for validation
                                raw_base = convert_to_raw_url(skill_base)
                                full_url = f"{raw_base.rstrip('/')}/{skill_file_item}"
                                files_to_check.append(('skill', full_url, full_url, True))
                            else:
                                resolved_base, _ = resolve_resource_path(skill_base, config_source, None)
                                full_path = str(Path(resolved_base) / skill_file_item)
                                files_to_check.append(('skill', full_path, full_path, False))

    # Validate each file
    info(f'Validating {len(files_to_check)} files...')
    all_valid = True

    for file_type, original_path, resolved_path, is_remote in files_to_check:
        # Use FileValidator for unified validation with per-URL authentication
        is_valid, method = validator.validate(resolved_path, is_remote)
        results.append((file_type, original_path, is_valid, method))

        if is_valid:
            if is_remote:
                info(f'  [OK] {file_type}: {original_path} (remote, validated via {method})')
            else:
                info(f'  [OK] {file_type}: {original_path} (local file exists)')
        else:
            if is_remote:
                error(f'  [FAIL] {file_type}: {original_path} (remote, not accessible)')
            else:
                error(f'  [FAIL] {file_type}: {original_path} (local file not found at {resolved_path})')
            all_valid = False

    return all_valid, results


def download_file(url: str, destination: Path, force: bool = True) -> bool:
    """Download a file from URL to destination."""
    filename = destination.name

    # Always overwrite by default unless force is explicitly False
    if destination.exists() and not force:
        info(f'File already exists: {filename} (skipping)')
        return True

    try:
        try:
            response = urlopen(url)
            content = response.read()
        except urllib.error.URLError as e:
            if 'SSL' in str(e) or 'certificate' in str(e).lower():
                warning('SSL certificate verification failed, trying with unverified context')
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                response = urlopen(url, context=ctx)
                content = response.read()
            else:
                raise

        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        success(f'Downloaded: {filename}')
        return True
    except Exception as e:
        error(f'Failed to download {filename}: {e}')
        return False


# Frozen set of binary file extensions (immutable for safety)
BINARY_EXTENSIONS: frozenset[str] = frozenset([
    # Archives
    '.tar.gz', '.tgz', '.gz', '.zip', '.7z', '.rar',
    '.tar', '.bz2', '.xz', '.lz4', '.zst',
    # Images
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.webp', '.svg',
    # Documents
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    # Executables
    '.exe', '.dll', '.so', '.dylib',
    # Python
    '.whl', '.pyc', '.pyo',
])


def is_binary_file(file_path: str | Path) -> bool:
    """Check if a file is binary based on its extension.

    Args:
        file_path: Path to the file (can be URL, local path, or filename)

    Returns:
        bool: True if the file extension indicates a binary file
    """
    path_str = str(file_path).lower()
    return any(path_str.endswith(ext) for ext in BINARY_EXTENSIONS)


def detect_repo_type(url: str) -> str | None:
    """Detect the repository type from URL.

    Returns:
        'gitlab' for GitLab URLs
        'github' for GitHub URLs
        None for other URLs
    """
    url_lower = url.lower()

    # GitLab detection (including self-hosted)
    if 'gitlab' in url_lower or '/api/v4/projects/' in url:
        return 'gitlab'

    # GitHub detection - includes raw.githubusercontent.com
    if 'github.com' in url_lower or 'api.github.com' in url_lower or 'raw.githubusercontent.com' in url_lower:
        return 'github'

    # Bitbucket detection (future expansion)
    if 'bitbucket' in url_lower:
        return 'bitbucket'

    return None


def convert_to_raw_url(url: str) -> str:
    """Convert GitHub/GitLab web UI URLs to raw content URLs.

    Transforms repository web interface URLs (tree/blob views) to their raw
    content equivalents that can be downloaded directly.

    Supports:
    - GitHub: tree/blob URLs -> raw.githubusercontent.com
    - GitLab: tree/blob URLs -> raw URLs (works with self-hosted instances)

    Args:
        url: URL to convert (may be a web UI URL, raw URL, or local path)

    Returns:
        Raw content URL if conversion was possible, otherwise the original URL unchanged.

    Examples:
        >>> convert_to_raw_url("https://github.com/org/repo/tree/main/path")
        'https://raw.githubusercontent.com/org/repo/main/path'

        >>> convert_to_raw_url("https://gitlab.com/ns/proj/-/tree/main/path")
        'https://gitlab.com/ns/proj/-/raw/main/path'

        >>> convert_to_raw_url("https://raw.githubusercontent.com/org/repo/main/path")
        'https://raw.githubusercontent.com/org/repo/main/path'

        >>> convert_to_raw_url("./local/path")
        './local/path'
    """
    # Return unchanged if not a URL
    if not url.startswith(('http://', 'https://')):
        return url

    # Already a raw URL - return unchanged
    if 'raw.githubusercontent.com' in url:
        return url

    # GitHub transformation
    # Pattern: github.com/{owner}/{repo}/(tree|blob)/{branch}/{path}
    # Also handles refs/heads/ prefix in branch name
    github_pattern = r'https://github\.com/([^/]+)/([^/]+)/(tree|blob)/(.+)'
    github_match = re.match(github_pattern, url.rstrip('/'))
    if github_match:
        owner, repo, _, branch_and_path = github_match.groups()
        # Handle refs/heads/ prefix if present
        branch_and_path = branch_and_path.removeprefix('refs/heads/')
        return f'https://raw.githubusercontent.com/{owner}/{repo}/{branch_and_path}'

    # GitLab transformation (works with self-hosted instances)
    # Pattern: any URL containing /-/tree/ or /-/blob/
    if '/-/tree/' in url:
        return url.replace('/-/tree/', '/-/raw/')
    if '/-/blob/' in url:
        return url.replace('/-/blob/', '/-/raw/')

    # Return unchanged if no transformation applied
    return url


def convert_gitlab_url_to_api(url: str) -> str:
    """Convert GitLab web UI URL to API URL for authentication.

    GitLab web UI URLs don't accept API tokens via headers.
    We need to use the API endpoint for private repo access.

    Converts:
    - From: https://gitlab.com/namespace/project/-/raw/branch/path/to/file
    - To: https://gitlab.com/api/v4/projects/namespace%2Fproject/repository/files/path%2Fto%2Ffile/raw?ref=branch

    Args:
        url: GitLab web UI raw URL

    Returns:
        GitLab API URL that accepts PRIVATE-TOKEN header
    """
    # Check if it's already an API URL
    if '/api/v4/projects/' in url:
        return url

    # Check if it's a GitLab web UI raw URL
    if '/-/raw/' not in url:
        return url  # Not a GitLab raw URL, return as-is

    # Parse the URL to extract components
    # Format: https://gitlab.com/namespace/project/-/raw/branch/path/to/file?query
    try:
        # Split off query parameters first
        base_url, _, query = url.partition('?')

        # Extract the domain and path
        if base_url.startswith('https://'):
            domain_end = base_url.index('/', 8)  # Find end of domain after https://
            domain = base_url[:domain_end]
            path = base_url[domain_end + 1 :]  # Skip the /
        elif base_url.startswith('http://'):
            domain_end = base_url.index('/', 7)  # Find end of domain after http://
            domain = base_url[:domain_end]
            path = base_url[domain_end + 1 :]  # Skip the /
        else:
            return url  # Unknown format

        # Split the path by /-/raw/
        parts = path.split('/-/raw/')
        if len(parts) != 2:
            return url  # Unexpected format

        project_path = parts[0]  # e.g., "ai/claude-code-configs"
        remainder = parts[1]  # e.g., "main/environments/library/file.yaml"

        # Split remainder into branch and file path
        # The branch is the first part before /
        branch_end = remainder.find('/')
        if branch_end == -1:
            # No file path, just branch
            branch = remainder
            file_path = ''
        else:
            branch = remainder[:branch_end]
            file_path = remainder[branch_end + 1 :]

        # URL-encode the project path for API (namespace/project -> namespace%2Fproject)
        encoded_project = urllib.parse.quote(project_path, safe='')

        # URL-encode the file path for API
        encoded_file = urllib.parse.quote(file_path, safe='')

        # Extract ref parameter from query if present (it overrides branch)
        ref = branch
        if query:
            # Parse query parameters
            params = urllib.parse.parse_qs(query)
            # Check for ref or ref_type parameters
            if 'ref' in params:
                ref = params['ref'][0]
            elif 'ref_type' in params and branch:
                # ref_type is just metadata, use the branch from path
                ref = branch

        # Build the API URL
        api_url = f'{domain}/api/v4/projects/{encoded_project}/repository/files/{encoded_file}/raw?ref={ref}'

        info('Converted GitLab URL to API format for authentication')
        return api_url

    except (ValueError, IndexError) as e:
        warning(f'Could not convert GitLab URL to API format: {e}')
        return url  # Return original if conversion fails


def convert_github_raw_to_api(url: str) -> str:
    """Convert raw.githubusercontent.com URL to GitHub API URL for authentication.

    GitHub raw.githubusercontent.com does not support Bearer token authentication
    for private repositories. This function converts to the Contents API endpoint
    which properly supports authentication.

    Converts:
        https://raw.githubusercontent.com/owner/repo/branch/path/to/file
        -> https://api.github.com/repos/owner/repo/contents/path/to/file?ref=branch

    Also handles refs/heads/ prefix format:
        https://raw.githubusercontent.com/owner/repo/refs/heads/branch/path/to/file
        -> https://api.github.com/repos/owner/repo/contents/path/to/file?ref=branch

    Args:
        url: GitHub raw URL

    Returns:
        GitHub API URL that accepts Bearer token authentication
    """
    # Check if already an API URL
    if 'api.github.com' in url:
        return url

    # Only convert raw.githubusercontent.com URLs
    if 'raw.githubusercontent.com' not in url:
        return url

    try:
        parsed = urllib.parse.urlparse(url)
        path_parts = parsed.path.strip('/').split('/')

        if len(path_parts) < 4:
            return url  # Not enough parts to parse

        owner = path_parts[0]
        repo = path_parts[1]

        # Handle refs/heads/ prefix format
        if len(path_parts) >= 5 and path_parts[2] == 'refs' and path_parts[3] == 'heads':
            ref = path_parts[4]
            file_path = '/'.join(path_parts[5:]) if len(path_parts) > 5 else ''
        else:
            # Standard format: branch is path_parts[2]
            ref = path_parts[2]
            file_path = '/'.join(path_parts[3:])

        if not file_path:
            return url  # No file path specified

        api_url = f'https://api.github.com/repos/{owner}/{repo}/contents/{file_path}?ref={ref}'

        info('Converted GitHub raw URL to API format for authentication')
        return api_url

    except (ValueError, IndexError) as e:
        warning(f'Could not convert GitHub URL to API format: {e}')
        return url


def get_auth_headers(url: str, auth_param: str | None = None) -> dict[str, str]:
    """Get authentication headers using multiple fallback methods.

    Precedence order:
    1. Command-line --auth parameter
    2. Environment variables (GITLAB_TOKEN, GITHUB_TOKEN, REPO_TOKEN)
    3. Auth config file (~/.claude/auth.yaml) - future expansion
    4. Interactive prompt (if terminal is interactive)

    Args:
        url: The URL to authenticate for
        auth_param: Optional auth parameter in format "header:value" or "header=value"

    Returns:
        Dictionary of headers to use for authentication
    """
    repo_type = detect_repo_type(url)

    # Helper function to build GitHub headers with Accept and API version
    def build_github_headers(token: str) -> dict[str, str]:
        # Handle Bearer prefix - avoid duplication if already present
        auth_value = token if token.startswith('Bearer ') else f'Bearer {token}'
        headers = {'Authorization': auth_value}
        # Add headers required for GitHub API to return raw content
        if 'api.github.com' in url:
            headers['Accept'] = 'application/vnd.github.raw+json'
            headers['X-GitHub-Api-Version'] = '2022-11-28'
        return headers

    # Method 1: Command-line parameter (highest priority)
    if auth_param:
        # Support both : and = as separators
        if ':' in auth_param:
            header_name, token = auth_param.split(':', 1)
        elif '=' in auth_param:
            header_name, token = auth_param.split('=', 1)
        else:
            # Assume it's just a token, use default header based on repo type
            token = auth_param
            if repo_type == 'gitlab':
                header_name = 'PRIVATE-TOKEN'
            elif repo_type == 'github':
                info('Using authentication from command-line parameter')
                return build_github_headers(token)
            else:
                error('Cannot determine auth header type. Use format: --auth "header:value"')
                return {}

        info('Using authentication from command-line parameter')
        return {header_name: token}

    # Method 2: Environment variables
    tokens_checked: list[str] = []

    # Check repo-specific tokens first
    if repo_type == 'gitlab':
        env_token = os.environ.get('GITLAB_TOKEN')
        tokens_checked.append('GITLAB_TOKEN')
        if env_token:
            info('Using GitLab token from GITLAB_TOKEN environment variable')
            return {'PRIVATE-TOKEN': env_token}
    elif repo_type == 'github':
        env_token = os.environ.get('GITHUB_TOKEN')
        tokens_checked.append('GITHUB_TOKEN')
        if env_token:
            info('Using GitHub token from GITHUB_TOKEN environment variable')
            return build_github_headers(env_token)

    # Check generic REPO_TOKEN as fallback
    env_token = os.environ.get('REPO_TOKEN')
    tokens_checked.append('REPO_TOKEN')
    if env_token:
        info('Using token from REPO_TOKEN environment variable')
        if repo_type == 'gitlab':
            return {'PRIVATE-TOKEN': env_token}
        if repo_type == 'github':
            return build_github_headers(env_token)

    # Method 3: Auth config file (future expansion)
    # auth_file = Path.home() / '.claude' / 'auth.yaml'
    # if auth_file.exists():
    #     # Implementation for auth file would go here
    #     pass

    # Method 4: Interactive prompt (only if repo type detected and terminal is interactive)
    if repo_type and sys.stdin.isatty():
        warning(f'Private {repo_type.title()} repository detected but no authentication found')
        info(f"Checked environment variables: {', '.join(tokens_checked)}")
        info('You can provide authentication by:')
        info(f'  1. Setting environment variable: {tokens_checked[0]}')
        info('  2. Using --auth parameter: --auth "token_here"')

        # Ask if they want to enter it now
        try:
            response = input('Would you like to enter the token now? (y/N): ').strip().lower()
            if response == 'y':
                import getpass

                input_token = getpass.getpass(f'Enter {repo_type.title()} token (will not echo): ')
                if input_token:
                    if repo_type == 'gitlab':
                        return {'PRIVATE-TOKEN': input_token}
                    if repo_type == 'github':
                        return build_github_headers(input_token)
        except (KeyboardInterrupt, EOFError):
            print()  # New line after Ctrl+C
    elif repo_type:
        # Non-interactive terminal but auth might be needed
        info(f'Private {repo_type.title()} repository detected')
        info(f"If authentication is required, set one of: {', '.join(tokens_checked)}")

    return {}


def derive_base_url(config_source: str) -> str:
    """Derive base URL from a configuration source URL.

    For example:
    - https://gitlab.company.com/api/v4/projects/123/repository/files/configs%2Fenv.yaml/raw?ref=main
      -> https://gitlab.company.com/api/v4/projects/123/repository/files/{path}/raw?ref=main
    - https://raw.githubusercontent.com/user/repo/main/configs/env.yaml
      -> https://raw.githubusercontent.com/user/repo/main/{path}

    Args:
        config_source: The configuration source URL

    Returns:
        Base URL with {path} placeholder
    """
    # GitLab API pattern
    if '/api/v4/projects/' in config_source and '/repository/files/' in config_source:
        # Extract everything before the encoded path
        parts = config_source.split('/repository/files/')
        if len(parts) == 2:
            base = parts[0] + '/repository/files/'
            # Extract the ref parameter if present
            if '/raw?' in parts[1]:
                ref_part = parts[1].split('/raw?')[1]
                return base + '{path}/raw?' + ref_part
            return base + '{path}/raw'

    # GitHub raw content pattern
    if 'raw.githubusercontent.com' in config_source:
        # Remove the specific file path, keeping up to branch/tag
        # Example: https://raw.githubusercontent.com/user/repo/main/configs/env.yaml
        #       -> https://raw.githubusercontent.com/user/repo/main/{path}
        parts = config_source.split('/')
        if len(parts) >= 7:  # Must have at least: https, '', raw.githubusercontent.com, user, repo, branch, path
            # Keep everything up to and including the branch/tag (index 5, which is 6 elements)
            base_parts = parts[:6]
            return '/'.join(base_parts) + '/{path}'
        # Fallback to removing last component
        parts = config_source.rsplit('/', 1)
        if len(parts) == 2:
            return parts[0] + '/{path}'

    # GitHub API pattern
    if 'api.github.com' in config_source and '/repos/' in config_source and '/contents/' in config_source:
        # Extract base up to /contents/
        parts = config_source.split('/contents/')
        if len(parts) == 2:
            return parts[0] + '/contents/{path}'

    # Generic pattern - remove last path component
    parts = config_source.rsplit('/', 1)
    if len(parts) == 2:
        return parts[0] + '/{path}'

    return config_source


def resolve_resource_path(resource_path: str, config_source: str, base_url: str | None = None) -> tuple[str, bool]:
    """Resolve a resource path to either a URL or local path.

    Priority:
    1. If resource_path is already a full URL, return as-is (remote)
    2. If base_url is configured, combine with resource_path (remote)
    3. If config was loaded from URL, derive base from it (remote)
    4. Otherwise, treat as local path (absolute or relative)

    Args:
        resource_path: The resource path from config (URL or local path)
        config_source: Where the config was loaded from (URL or local path)
        base_url: Optional base URL override from config

    Returns:
        tuple[str, bool]: (resolved_path, is_remote)
            - resolved_path: Full URL or absolute local path
            - is_remote: True if URL, False if local path
    """
    # 1. If full URL, return as-is
    if resource_path.startswith(('http://', 'https://')):
        return resource_path, True

    # 2. If base-url configured, use it (always remote)
    if base_url:
        # Auto-append {path} if not present
        if '{path}' not in base_url:
            # Add {path} placeholder appropriately
            base_url = base_url + '{path}' if base_url.endswith('/') else base_url + '/{path}'

        # Handle GitLab URL encoding for paths
        if '/api/v4/projects/' in base_url and '/repository/files/' in base_url:
            # URL encode the path for GitLab API
            encoded_path = urllib.parse.quote(resource_path, safe='')
            return base_url.replace('{path}', encoded_path), True
        # For other URLs, just replace the placeholder
        return base_url.replace('{path}', resource_path), True

    # 3. If config from URL, derive base from it
    if config_source.startswith(('http://', 'https://')):
        derived_base = derive_base_url(config_source)
        # Handle GitLab URL encoding
        if '/api/v4/projects/' in derived_base and '/repository/files/' in derived_base:
            encoded_path = urllib.parse.quote(resource_path, safe='')
            return derived_base.replace('{path}', encoded_path), True
        return derived_base.replace('{path}', resource_path), True

    # 4. Treat as local path (absolute or relative)
    # Handle home directory expansion (~)
    if resource_path.startswith('~'):
        resource_path = os.path.expanduser(resource_path)

    # Handle environment variables (e.g., %USERPROFILE%, $HOME)
    resource_path = os.path.expandvars(resource_path)

    # Convert to Path object for proper handling
    path_obj = Path(resource_path)

    # Check if it's already an absolute path
    if path_obj.is_absolute():
        return str(path_obj.resolve()), False

    # It's a relative path - resolve relative to config location
    config_path = Path(config_source)
    # Config source might be just a name from repo library
    # In this case, paths should be resolved relative to current directory
    config_dir = config_path.parent if config_path.is_file() else Path.cwd()

    # Resolve the resource path relative to config directory
    resource_full_path = (config_dir / resource_path).resolve()
    return str(resource_full_path), False


def load_config_from_source(config_spec: str, auth_param: str | None = None) -> tuple[dict[str, Any], str]:
    """Load configuration from URL, local path, or repository.

    Supports three sources:
    1. Direct URL: http://... or https://...
    2. Local file: ./config.yaml, ../configs/env.yaml, /absolute/path.yaml
    3. Repository config: just a name like 'python'

    Args:
        config_spec: Configuration specification (URL, path, or name)
        auth_param: Optional authentication parameter for private repos

    Returns:
        tuple[dict[str, Any], str]: Parsed YAML configuration and source path/URL.

    Raises:
        FileNotFoundError: If local file doesn't exist.
        urllib.error.HTTPError: If HTTP request fails.
        Exception: If configuration is not found or parsing fails.
    """

    # Source 1: Direct URL
    if config_spec.startswith(('http://', 'https://')):
        info(f'Loading configuration from URL: {config_spec}')

        # Check if it's a known private repo pattern
        repo_type = detect_repo_type(config_spec)
        if repo_type:
            info(f'Detected {repo_type.title()} repository URL')
        else:
            warning('Loading configuration from remote URL')
            warning('Only use configs from trusted sources!')

        try:
            content = fetch_url_with_auth(config_spec, auth_param=auth_param)
            config = yaml.safe_load(content)
            success(f"Configuration loaded from URL: {config.get('name', 'Remote Config')}")
            return config, config_spec
        except Exception as e:
            error(f'Failed to load configuration from URL: {e}')
            raise

    # Source 2: Local file (has path separators, starts with . or exists)
    if (
        '/' in config_spec
        or '\\' in config_spec
        or config_spec.startswith(('./', '.\\', '../', '..\\'))
        or os.path.isabs(config_spec)
        or os.path.exists(config_spec)
    ):
        # Normalize path
        config_path = Path(config_spec).resolve()

        if not config_path.exists():
            error(f'Local configuration file not found: {config_spec}')
            info('Make sure the file path is correct and the file exists.')
            raise FileNotFoundError(f'Configuration not found: {config_spec}')

        info(f'Loading local configuration: {config_path}')

        try:
            with open(config_path, encoding='utf-8') as f:
                config = yaml.safe_load(f)
            success(f"Configuration loaded: {config.get('name', config_path.name)}")
            return config, str(config_path)
        except Exception as e:
            error(f'Failed to load local configuration: {e}')
            raise

    # Source 3: Repository config (just a name)
    if not config_spec.endswith('.yaml'):
        config_spec += '.yaml'

    config_url = f'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/environments/library/{config_spec}'
    info(f'Loading configuration from repository: {config_spec}')

    try:
        # Use the same fetch function for consistency
        content = fetch_url_with_auth(config_url, auth_param=auth_param)
        config = yaml.safe_load(content)
        success(f"Configuration loaded: {config.get('name', config_spec)}")
        return config, config_spec
    except urllib.error.HTTPError as e:
        if e.code == 404:
            error(f'Configuration not found in repository: {config_spec}')
            info('Available configurations:')
            info('  - python: Python development environment')
            info('')
            info('You can also:')
            info('  - Create custom configs in environments/library/')
            info('  - Use a local file: ./my-config.yaml')
            info('  - Use a URL: https://example.com/config.yaml')
            raise Exception(f'Configuration not found: {config_spec}') from None
        error(f'Failed to load repository configuration: {e}')
        raise
    except Exception as e:
        if 'Configuration not found' not in str(e):
            error(f'Failed to load repository configuration: {e}')
        raise


def _normalize_source_for_comparison(source: str) -> str:
    """Normalize a source path/URL for circular dependency comparison.

    Args:
        source: The source path or URL.

    Returns:
        str: Normalized source for comparison.
    """
    # For local paths, resolve to absolute
    if not source.startswith(('http://', 'https://')):
        try:
            return str(Path(source).resolve())
        except Exception:
            return source

    # For URLs, normalize by removing trailing slashes
    # But keep the essential parts for accurate cycle detection
    return source.rstrip('/')


def _resolve_inherit_path(inherit_value: str, current_source: str) -> str:
    """Resolve the inherit path relative to current config source.

    Args:
        inherit_value: The value of the 'inherit' key (URL, path, or name).
        current_source: Source path/URL of the current config.

    Returns:
        str: Resolved path/URL for the parent config.
    """
    # If inherit_value is already a full URL, use as-is
    if inherit_value.startswith(('http://', 'https://')):
        return inherit_value

    # If inherit_value is an absolute path, use as-is
    if os.path.isabs(inherit_value):
        return inherit_value

    # If current source is a URL, resolve relative to it
    if current_source.startswith(('http://', 'https://')):
        # Get the directory part of the URL
        base_url = current_source.rsplit('/', 1)[0]
        return f'{base_url}/{inherit_value}'

    # If current source is a local path, resolve relative to it
    if os.path.exists(current_source) or '/' in current_source or '\\' in current_source:
        current_path = Path(current_source)
        parent_dir = current_path.parent if current_path.is_file() else Path(current_source).parent
        resolved = (parent_dir / inherit_value).resolve()
        return str(resolved)

    # Current source is a repo config name (e.g., 'python')
    # Inherit value should also be treated as a repo config name
    return inherit_value


def _merge_configs(parent: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
    """Merge parent and child configs with top-level key override semantics.

    Child values completely replace parent values for the same key.
    No deep merging is performed.

    Args:
        parent: The parent configuration (base).
        child: The child configuration (overrides parent).

    Returns:
        dict[str, Any]: Merged configuration.
    """
    # Start with parent's keys
    result = parent.copy()

    # Override with child's keys (excluding 'inherit')
    for key, value in child.items():
        if key != INHERIT_KEY:
            result[key] = value

    return result


def resolve_config_inheritance(
    config: dict[str, Any],
    source: str,
    auth_param: str | None = None,
    visited: set[str] | None = None,
    depth: int = 0,
) -> dict[str, Any]:
    """Resolve configuration inheritance by loading and merging parent configs.

    Implements top-level key override semantics: child config values completely
    replace parent values for the same key. No deep merging is performed.

    The inheritance chain is resolved recursively:
    1. If config has 'inherit' key, load the parent config
    2. If parent also has 'inherit', load its parent (recursive)
    3. Merge configs from oldest ancestor to newest child

    Args:
        config: The configuration dictionary to resolve inheritance for.
        source: Source path/URL where this config was loaded from.
            Used to resolve relative inherit paths.
        auth_param: Optional authentication parameter for private repositories.
            Passed through the inheritance chain.
        visited: Set of already-visited sources for circular dependency detection.
            Used internally for recursion tracking. Callers should not provide this.
        depth: Current recursion depth for safety limits.
            Used internally. Callers should not provide this.

    Returns:
        dict[str, Any]: Merged configuration with inheritance resolved.
            The 'inherit' key is removed from the result.

    Raises:
        ValueError: If circular dependency is detected, maximum inheritance
            depth is exceeded, or inherit value is invalid.
        FileNotFoundError: If parent config file not found (propagated from
            load_config_from_source).

    Examples:
        >>> # Simple inheritance
        >>> child = {'inherit': 'base.yaml', 'name': 'Child'}
        >>> resolved = resolve_config_inheritance(child, 'child.yaml')
        >>> # resolved contains parent's keys + child's 'name' override

        >>> # Chain: grandparent -> parent -> child
        >>> child = {'inherit': 'parent.yaml', 'model': 'claude-3'}
        >>> resolved = resolve_config_inheritance(child, 'child.yaml')
        >>> # resolved contains all ancestors' keys, child overrides take precedence
    """
    # Initialize visited set for circular dependency detection
    if visited is None:
        visited = set()

    # Check for maximum depth exceeded
    if depth > MAX_INHERITANCE_DEPTH:
        error(f'Maximum inheritance depth ({MAX_INHERITANCE_DEPTH}) exceeded')
        error('This may indicate a very deep inheritance chain or a logic error')
        raise ValueError(
            f'Maximum inheritance depth ({MAX_INHERITANCE_DEPTH}) exceeded. '
            f'Check your configuration inheritance chain.',
        )

    # Check if this config has inheritance
    inherit_value = config.get(INHERIT_KEY)
    if inherit_value is None:
        # No inheritance - return config as-is (without the inherit key if present)
        return {k: v for k, v in config.items() if k != INHERIT_KEY}

    # Validate inherit value is a string
    if not isinstance(inherit_value, str):
        error(f"Invalid 'inherit' value: expected string, got {type(inherit_value).__name__}")
        raise ValueError(
            f"The 'inherit' key must be a string (URL or path), "
            f"got {type(inherit_value).__name__}: {inherit_value!r}",
        )

    # Validate inherit value is not empty
    inherit_value = inherit_value.strip()
    if not inherit_value:
        error("Empty 'inherit' value in configuration")
        raise ValueError("The 'inherit' key cannot be empty")

    # Resolve the parent path (could be URL, local path, or repo name)
    parent_source = _resolve_inherit_path(inherit_value, source)

    # Normalize source for circular dependency detection
    normalized_source = _normalize_source_for_comparison(parent_source)

    # Check for circular dependency
    if normalized_source in visited:
        cycle_path = ' -> '.join(list(visited) + [normalized_source])
        error('Circular dependency detected in configuration inheritance')
        error(f'Cycle: {cycle_path}')
        raise ValueError(
            f'Circular dependency detected: {normalized_source} was already visited. '
            f'Inheritance chain: {cycle_path}',
        )

    # Add current source to visited set
    visited.add(normalized_source)

    # Log inheritance resolution
    info(f'Resolving inheritance from: {inherit_value}')

    # Load parent configuration
    try:
        parent_config, actual_parent_source = load_config_from_source(
            parent_source, auth_param,
        )
    except FileNotFoundError:
        error(f'Parent configuration not found: {inherit_value}')
        error(f'Resolved path: {parent_source}')
        raise
    except Exception as e:
        error(f'Failed to load parent configuration: {inherit_value}')
        error(f'Error: {e}')
        raise

    # Recursively resolve parent's inheritance
    resolved_parent = resolve_config_inheritance(
        parent_config,
        actual_parent_source,
        auth_param=auth_param,
        visited=visited,
        depth=depth + 1,
    )

    # Merge: parent first, then child overrides (top-level key override)
    merged = _merge_configs(resolved_parent, config)

    success(f'Inherited from: {inherit_value}')

    return merged


def get_real_user_home() -> Path:
    """Get the real user's home directory, even when running under sudo.

    On Linux/macOS, when running with sudo, the HOME environment variable
    and Path.home() return /root instead of the actual user's home.
    This function detects the real user via SUDO_USER and returns their home.

    Returns:
        Path: The real user's home directory.
    """
    if sys.platform != 'win32':
        # Check if running under sudo (Unix-only)
        sudo_user = os.environ.get('SUDO_USER')
        if sudo_user:
            try:
                # Get the home directory of the user who invoked sudo
                # pwd is imported at module level for non-Windows platforms
                import pwd as pwd_module

                return Path(pwd_module.getpwnam(sudo_user).pw_dir)
            except KeyError:
                # User not found in password database, fall back
                warning(f'Could not find home directory for sudo user: {sudo_user}')

    # Windows or not running under sudo - use default home
    return Path.home()


def get_all_shell_config_files() -> list[Path]:
    """Get all shell configuration files to update for environment variables.

    Returns files for all common shells to ensure environment variables
    are available regardless of which shell the user opens.

    Returns:
        list[Path]: List of shell config file paths that exist or should be created.
    """
    # Windows uses registry, not shell config files
    config_files: list[Path] = []

    if sys.platform != 'win32':
        # Unix-like systems - get all shell config files
        home = get_real_user_home()

        # All possible shell config files for environment variables
        # Listed in order of preference/importance
        config_files = [
            # Bash files
            home / '.bashrc',       # Interactive bash shells (most common on Linux)
            home / '.bash_profile',  # Login bash shells (macOS Terminal.app, SSH)
            home / '.profile',      # Fallback for sh/dash (Ubuntu default login shell)
            # Zsh files
            home / '.zshenv',       # All zsh instances (recommended for env vars)
            home / '.zprofile',     # Zsh login shells (macOS default since Catalina)
            home / '.zshrc',        # Interactive zsh shells
            # Fish files
            home / '.config' / 'fish' / 'config.fish',  # Fish shell config
        ]

        # On Linux, only include zsh files if zsh is installed
        if platform.system() == 'Linux':
            zsh_path = shutil.which('zsh')
            if not zsh_path:
                # Filter out zsh-specific files if zsh is not installed
                config_files = [f for f in config_files if not f.name.startswith('.zsh')]

            # Only include fish config if fish is installed
            fish_path = shutil.which('fish')
            if not fish_path:
                config_files = [f for f in config_files if 'fish' not in str(f)]

    return config_files


def _get_export_line(config_file: Path, name: str, value: str) -> str:
    """Generate the appropriate export line for the shell type.

    Args:
        config_file: Path to the shell config file.
        name: Environment variable name.
        value: Environment variable value.

    Returns:
        str: The export line in the appropriate syntax for the shell.
    """
    # Fish shell uses different syntax
    if 'fish' in str(config_file):
        return f'set -gx {name} "{value}"'
    # Bash/Zsh use export
    return f'export {name}="{value}"'


def _get_export_prefix(config_file: Path, name: str) -> str:
    """Get the line prefix to match for an existing export.

    Args:
        config_file: Path to the shell config file.
        name: Environment variable name.

    Returns:
        str: The prefix to match (e.g., 'export NAME=' or 'set -gx NAME ').
    """
    # Fish shell uses different syntax
    if 'fish' in str(config_file):
        return f'set -gx {name} '
    # Bash/Zsh use export
    return f'export {name}='


def add_export_to_file(config_file: Path, name: str, value: str) -> bool:
    """Add or update an environment variable export in a shell config file.

    Uses markers to manage a block of exports set by claude-code-toolbox.
    Updates existing variables within the block, or adds new ones.
    Automatically uses the correct syntax for the shell type (bash/zsh vs fish).

    Args:
        config_file: Path to the shell config file.
        name: Environment variable name.
        value: Environment variable value.

    Returns:
        bool: True if successful, False otherwise.
    """
    export_line = _get_export_line(config_file, name, value)
    export_prefix = _get_export_prefix(config_file, name)

    try:
        # Read existing content
        if config_file.exists():
            content = config_file.read_text(encoding='utf-8')
        else:
            # Create the file if it doesn't exist
            config_file.parent.mkdir(parents=True, exist_ok=True)
            content = ''

        # Check if our marker block exists
        if ENV_VAR_MARKER_START in content:
            # Extract the block between markers
            start_idx = content.find(ENV_VAR_MARKER_START)
            end_idx = content.find(ENV_VAR_MARKER_END)

            if end_idx == -1:
                # Malformed block, append end marker
                end_idx = len(content)
                content = content + '\n' + ENV_VAR_MARKER_END + '\n'

            # Get content before, in, and after the block
            before = content[:start_idx]
            block = content[start_idx : end_idx + len(ENV_VAR_MARKER_END)]
            after = content[end_idx + len(ENV_VAR_MARKER_END) :]

            # Parse existing exports in the block
            block_lines = block.split('\n')
            new_block_lines = [ENV_VAR_MARKER_START]
            found = False

            for line in block_lines:
                if line in (ENV_VAR_MARKER_START, ENV_VAR_MARKER_END):
                    continue
                if line.strip().startswith(export_prefix):
                    # Update existing variable
                    new_block_lines.append(export_line)
                    found = True
                elif line.strip():
                    new_block_lines.append(line)

            if not found:
                # Add new variable
                new_block_lines.append(export_line)

            new_block_lines.append(ENV_VAR_MARKER_END)

            # Reconstruct content
            new_content = before + '\n'.join(new_block_lines) + after
        else:
            # No marker block exists, create one at the end
            if content and not content.endswith('\n'):
                content += '\n'
            new_content = (
                content
                + '\n'
                + ENV_VAR_MARKER_START
                + '\n'
                + export_line
                + '\n'
                + ENV_VAR_MARKER_END
                + '\n'
            )

        # Write back
        config_file.write_text(new_content, encoding='utf-8')
        return True

    except OSError as e:
        warning(f'Could not write to {config_file}: {e}')
        return False


def _is_bash_zsh_export_line(line: str, name: str) -> bool:
    """Check if a line is a bash/zsh export for the given variable name.

    Matches patterns:
    - export NAME="value"
    - export NAME='value'
    - export NAME=value
    - NAME="value" (without export keyword)

    Does NOT match:
    - Comments containing the variable name
    - Lines where the variable name is part of another word

    Args:
        line: The line to check.
        name: The environment variable name.

    Returns:
        bool: True if line exports the variable, False otherwise.
    """
    stripped = line.strip()

    # Skip comments
    if stripped.startswith('#'):
        return False

    # Match "export NAME=" or "NAME=" patterns
    # Must be at start of line (after stripping) to avoid partial matches
    return stripped.startswith((f'export {name}=', f'{name}='))


def _is_fish_set_line(line: str, name: str) -> bool:
    """Check if a line is a fish shell set command for the given variable name.

    Matches patterns:
    - set -gx NAME "value"
    - set -gx NAME 'value'
    - set -Ux NAME "value"
    - set NAME "value"
    - And variations with different flag orders

    Does NOT match:
    - Comments containing the variable name
    - Lines where the variable name is part of another word

    Args:
        line: The line to check.
        name: The environment variable name.

    Returns:
        bool: True if line sets the variable, False otherwise.
    """
    stripped = line.strip()

    # Skip comments
    if stripped.startswith('#'):
        return False

    # Fish shell set pattern: set [-flags] NAME value
    # Pattern matches: set (with optional flags like -gx, -Ux, etc.) followed by NAME and value
    fish_pattern = rf'^set\s+(?:-[gGxXUu]+\s+)*{re.escape(name)}\s+'
    return bool(re.match(fish_pattern, stripped))


def _is_env_var_line(config_file: Path, line: str, name: str) -> bool:
    """Check if a line sets the given environment variable (any shell syntax).

    Detects the shell type from the config file path and checks accordingly.

    Args:
        config_file: Path to the shell config file.
        line: The line to check.
        name: The environment variable name.

    Returns:
        bool: True if line sets the variable, False otherwise.
    """
    # Check if this is a fish config file
    is_fish = 'fish' in str(config_file)

    if is_fish:
        return _is_fish_set_line(line, name)
    return _is_bash_zsh_export_line(line, name)


def remove_export_from_file(config_file: Path, name: str) -> bool:
    """Remove an environment variable export from a shell config file.

    Removes the variable from:
    1. The claude-code-toolbox marker block (if exists)
    2. ALSO from anywhere else in the file (legacy/manual additions)

    If the marker block becomes empty after removal, removes the entire block.

    Args:
        config_file: Path to the shell config file.
        name: Environment variable name to remove.

    Returns:
        bool: True if successful (or file doesn't exist), False on error.
    """
    if not config_file.exists():
        return True

    try:
        content = config_file.read_text(encoding='utf-8')
        original_content = content
        lines = content.split('\n')
        new_lines: list[str] = []

        # First pass: Remove the variable from ANYWHERE in the file
        for line in lines:
            if _is_env_var_line(config_file, line, name):
                # Skip this line (remove the variable)
                continue
            new_lines.append(line)

        new_content = '\n'.join(new_lines)

        # Clean up empty marker blocks
        if ENV_VAR_MARKER_START in new_content:
            start_idx = new_content.find(ENV_VAR_MARKER_START)
            end_idx = new_content.find(ENV_VAR_MARKER_END)

            if end_idx != -1:
                before = new_content[:start_idx]
                block = new_content[start_idx : end_idx + len(ENV_VAR_MARKER_END)]
                after = new_content[end_idx + len(ENV_VAR_MARKER_END) :]

                # Check if block is empty (only markers and whitespace)
                block_lines = block.split('\n')
                has_content = False
                for block_line in block_lines:
                    if block_line in (ENV_VAR_MARKER_START, ENV_VAR_MARKER_END):
                        continue
                    if block_line.strip():
                        has_content = True
                        break

                if not has_content:
                    # Block is empty, remove it entirely
                    new_content = before.rstrip('\n') + '\n' + after.lstrip('\n')
                    # Handle edge case where file becomes only newlines
                    if new_content.strip() == '':
                        new_content = ''

        # Only write if content changed
        if new_content != original_content:
            config_file.write_text(new_content, encoding='utf-8')
        return True

    except OSError as e:
        warning(f'Could not modify {config_file}: {e}')
        return False


def set_os_env_variable_windows(name: str, value: str | None) -> bool:
    """Set or delete an OS environment variable on Windows.

    Uses setx for setting and REG delete for removing.
    Changes affect new processes only.

    Args:
        name: Environment variable name.
        value: Value to set, or None to delete the variable.

    Returns:
        bool: True if successful, False otherwise.
    """
    success = False

    if sys.platform == 'win32':
        try:
            if value is None:
                # Delete the variable using registry
                result = subprocess.run(
                    ['reg', 'delete', r'HKCU\Environment', '/v', name, '/f'],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0 and 'unable to find' not in result.stderr.lower():
                    # Only warn if it's not a "not found" error
                    warning(f'Could not delete environment variable {name}: {result.stderr}')
                else:
                    success = True
            else:
                # Set the variable using setx
                result = subprocess.run(
                    ['setx', name, value],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    warning(f'Could not set environment variable {name}: {result.stderr}')
                else:
                    success = True

        except OSError as e:
            warning(f'Error setting environment variable {name}: {e}')

    return success


def set_os_env_variable_unix(name: str, value: str | None) -> bool:
    """Set or delete an OS environment variable on Unix-like systems.

    Writes to all shell config files for maximum compatibility.

    Args:
        name: Environment variable name.
        value: Value to set, or None to delete the variable.

    Returns:
        bool: True if all operations succeeded, False if any failed.
    """
    # Windows doesn't use shell config files
    all_success = False

    if sys.platform != 'win32':
        config_files = get_all_shell_config_files()
        all_success = True

        for config_file in config_files:
            if value is None:
                # Delete the variable
                if not remove_export_from_file(config_file, name):
                    all_success = False
            else:
                # Set the variable
                if not add_export_to_file(config_file, name, value):
                    all_success = False

    return all_success


def set_os_env_variable(name: str, value: str | None) -> bool:
    """Set or delete an OS-level persistent environment variable.

    This function sets environment variables that persist across shell sessions.
    - On Windows: Uses setx (set) or registry (delete)
    - On macOS/Linux: Writes to all shell config files

    Args:
        name: Environment variable name.
        value: Value to set, or None to delete the variable.

    Returns:
        bool: True if successful, False otherwise.
    """
    result = False
    if sys.platform == 'win32':
        result = set_os_env_variable_windows(name, value)
    else:
        result = set_os_env_variable_unix(name, value)
    return result


def set_all_os_env_variables(env_vars: dict[str, str | None]) -> bool:
    """Set or delete all OS environment variables from configuration.

    Args:
        env_vars: Dictionary of variable names to values.
                  None values indicate the variable should be deleted.

    Returns:
        bool: True if all operations succeeded, False if any failed.
    """
    if not env_vars:
        info('No OS environment variables to configure')
        return True

    set_count = 0
    delete_count = 0
    failed_count = 0

    for name, value in env_vars.items():
        if value is None:
            # Delete the variable
            info(f'Deleting environment variable: {name}')
            if set_os_env_variable(name, None):
                delete_count += 1
            else:
                failed_count += 1
        else:
            # Set the variable
            info(f'Setting environment variable: {name}')
            if set_os_env_variable(name, str(value)):
                set_count += 1
            else:
                failed_count += 1

    # Summary
    if set_count > 0:
        success(f'Set {set_count} environment variable(s)')
    if delete_count > 0:
        success(f'Deleted {delete_count} environment variable(s)')
    if failed_count > 0:
        warning(f'Failed to configure {failed_count} environment variable(s)')

    # Provide reload instructions for Unix systems
    if sys.platform != 'win32' and (set_count > 0 or delete_count > 0):
        info('Note: Open a new terminal or run "source ~/.bashrc" to apply changes')

    return failed_count == 0


def install_nodejs_if_requested(config: dict[str, Any]) -> bool:
    """Install Node.js LTS if requested in configuration.

    Checks the 'install-nodejs' config parameter and installs Node.js
    if set to True. Uses the existing ensure_nodejs() function which:
    - Checks if Node.js is already installed (prevents duplicate installation)
    - Tries multiple installation methods with fallbacks
    - Updates PATH after installation

    Args:
        config: Environment configuration dictionary

    Returns:
        True if Node.js is installed or not requested, False if installation fails.
    """
    install_nodejs_flag = config.get('install-nodejs', False)

    if not install_nodejs_flag:
        info('Node.js installation not requested (install-nodejs: false or not set)')
        return True

    info('Node.js installation requested (install-nodejs: true)')

    # Late import to avoid circular dependency (install_claude imports from setup_environment)
    from install_claude import ensure_nodejs as _ensure_nodejs

    if not _ensure_nodejs():
        error('Node.js installation failed')
        return False

    # Refresh PATH from registry on Windows to pick up new installation
    if platform.system() == 'Windows':
        refresh_path_from_registry()

    success('Node.js is available')
    return True


def install_dependencies(dependencies: dict[str, list[str]] | None) -> bool:
    """Install dependencies from configuration."""
    if not dependencies:
        info('No dependencies to install')
        return True

    # Type annotation already ensures dependencies is a dict
    # Runtime type check removed as it's redundant with proper typing

    info('Installing dependencies...')

    # Check if any Windows dependencies need admin
    if platform.system() == 'Windows' and not is_admin():
        win_deps = dependencies.get('windows', [])
        common_deps = dependencies.get('common', [])
        all_deps = win_deps + common_deps

        admin_needed_deps = [dep for dep in all_deps if 'winget' in dep and '--scope machine' in dep]

        if admin_needed_deps:
            warning('Some dependencies require administrator privileges:')
            for dep in admin_needed_deps:
                warning(f'  - {dep}')
            info('')
            info('Requesting administrator elevation...')
            request_admin_elevation()
            # If we reach here, elevation was denied
            error('Administrator elevation was denied')
            error('System-wide dependency installation cannot proceed without administrator privileges')
            error('')
            error('Options:')
            error('  1. Run this script as administrator')
            error('  2. Modify dependencies to use --scope user instead')
            error('  3. Use --no-admin flag to skip admin-required dependencies')
            return False

    # Get system platform
    system = platform.system()

    # Platform mapping: platform.system() returns -> config key
    platform_map = {
        'Windows': 'windows',
        'Darwin': 'mac',  # macOS
        'Linux': 'linux',
    }

    current_platform_key = platform_map.get(system)

    if not current_platform_key:
        warning(f'Unknown platform: {system}. Skipping platform-specific dependencies.')
        current_platform_key = None

    # Collect dependencies: platform-specific first, then common
    # This ensures platform runtimes (e.g., Node.js) are installed before
    # common tools that depend on them (e.g., npm packages)
    platform_deps_list: list[str] = []
    common_deps_list: list[str] = []

    # Collect platform-specific dependencies (e.g., Node.js runtime)
    if current_platform_key:
        platform_deps = dependencies.get(current_platform_key, [])
        if platform_deps:
            info(f'Found {len(platform_deps)} {current_platform_key}-specific dependencies')
            platform_deps_list = list(platform_deps)

    # Collect common dependencies (e.g., npm packages that need Node.js)
    common_deps = dependencies.get('common', [])
    if common_deps:
        info(f'Found {len(common_deps)} common dependencies')
        common_deps_list = list(common_deps)

    if not platform_deps_list and not common_deps_list:
        info('No dependencies to install for this platform')
        return True

    # Helper function to execute a single dependency
    def execute_dependency(dep: str) -> bool:
        """Execute a single dependency command. Returns True on success."""
        info(f'Running: {dep}')
        parts = dep.split()

        if system == 'Windows':
            if parts[0] in ['winget', 'npm', 'pip', 'pipx']:
                result = run_command(parts, capture_output=False)
            elif parts[0] == 'uv' and len(parts) >= 3 and parts[1] == 'tool' and parts[2] == 'install':
                parts_with_force = parts[:3] + ['--force'] + parts[3:]
                result = run_command(parts_with_force, capture_output=False)
            else:
                # Windows dependencies are PowerShell commands (user-provided in YAML)
                # This is different from MCP server config which uses bash for generated commands
                result = run_command(['powershell', '-NoProfile', '-Command', dep], capture_output=False)
        else:
            if parts[0] == 'uv' and len(parts) >= 3 and parts[1] == 'tool' and parts[2] == 'install':
                dep_with_force = dep.replace('uv tool install', 'uv tool install --force')
                result = run_command(['bash', '-c', dep_with_force], capture_output=False)
            else:
                expanded_dep = expand_tildes_in_command(dep)
                result = run_command(['bash', '-c', expanded_dep], capture_output=False)

        if result.returncode != 0:
            error(f'Failed to install dependency: {dep}')
            if system == 'Windows' and not is_admin() and 'winget' in dep and '--scope machine' in dep:
                warning('This may have failed due to lack of admin rights')
                info('Try: 1) Run as administrator, or 2) Use --scope user instead')
            warning('Continuing with other dependencies...')
            return False
        return True

    # Phase 1: Execute platform-specific dependencies
    for dep in platform_deps_list:
        execute_dependency(dep)

    # Phase 2: Refresh PATH from registry on Windows
    # This picks up any PATH changes from platform-specific installations (e.g., Node.js)
    if system == 'Windows' and platform_deps_list:
        refresh_path_from_registry()

    # Phase 3: Execute common dependencies
    for dep in common_deps_list:
        execute_dependency(dep)

    return True


def fetch_url_with_auth(url: str, auth_headers: dict[str, str] | None = None, auth_param: str | None = None) -> str:
    """Fetch URL content, trying without auth first, then with auth if needed.

    Args:
        url: URL to fetch
        auth_headers: Optional pre-computed auth headers
        auth_param: Optional auth parameter for getting headers

    Returns:
        str: Content of the URL

    Raises:
        HTTPError: If the HTTP request fails after authentication attempts
        URLError: If there's a URL/network error (including SSL issues)
    """
    # Convert GitLab web URLs to API URLs for authentication
    original_url = url
    if detect_repo_type(url) == 'gitlab' and '/-/raw/' in url:
        url = convert_gitlab_url_to_api(url)
        if url != original_url:
            info(f'Using API URL: {url}')

    # Convert GitHub raw URLs to API URLs for authentication
    if detect_repo_type(url) == 'github' and 'raw.githubusercontent.com' in original_url:
        url = convert_github_raw_to_api(original_url)
        if url != original_url:
            info(f'Using API URL: {url}')

    # First try without auth (for public repos)
    try:
        request = Request(url)
        response = urlopen(request)
        content: str = response.read().decode('utf-8')
        return content
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 404):
            # Authentication might be needed
            if not auth_headers:
                # Get auth headers if not already provided
                auth_headers = get_auth_headers(url, auth_param)

            if auth_headers:
                # Retry with authentication
                info('Retrying with authentication...')
                request = Request(url)
                for header, value in auth_headers.items():
                    request.add_header(header, value)
                try:
                    response = urlopen(request)
                    result: str = response.read().decode('utf-8')
                    return result
                except urllib.error.HTTPError as auth_e:
                    if auth_e.code == 401:
                        error('Authentication failed. Check your token.')
                    elif auth_e.code == 403:
                        error('Access forbidden. Token may lack permissions.')
                    elif auth_e.code == 404:
                        error('Resource not found. Check URL and permissions.')
                    raise
            elif e.code == 404:
                # 404 without auth headers available - likely just not found
                raise
            else:
                # 401/403 but no auth headers available
                warning('Authentication may be required for this URL')
                raise
        else:
            raise
    except urllib.error.URLError as e:
        if 'SSL' in str(e) or 'certificate' in str(e).lower():
            warning('SSL certificate verification failed, trying with unverified context')
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            request = Request(url)
            if auth_headers:
                for header, value in auth_headers.items():
                    request.add_header(header, value)

            response = urlopen(request, context=ctx)
            ctx_result: str = response.read().decode('utf-8')
            return ctx_result
        raise


def fetch_url_bytes_with_auth(
    url: str,
    auth_headers: dict[str, str] | None = None,
    auth_param: str | None = None,
) -> bytes:
    """Fetch URL content as bytes, trying without auth first, then with auth if needed.

    Similar to fetch_url_with_auth but returns raw bytes without decoding.
    Use this for binary files like .tar.gz, .zip, images, etc.

    Args:
        url: URL to fetch
        auth_headers: Optional pre-computed auth headers
        auth_param: Optional auth parameter for getting headers

    Returns:
        bytes: Raw content of the URL

    Raises:
        HTTPError: If the HTTP request fails after authentication attempts
        URLError: If there's a URL/network error (including SSL issues)
    """
    # Convert GitLab web URLs to API URLs for authentication
    original_url = url
    if detect_repo_type(url) == 'gitlab' and '/-/raw/' in url:
        url = convert_gitlab_url_to_api(url)
        if url != original_url:
            info(f'Using API URL: {url}')

    # Convert GitHub raw URLs to API URLs for authentication
    if detect_repo_type(url) == 'github' and 'raw.githubusercontent.com' in original_url:
        url = convert_github_raw_to_api(original_url)
        if url != original_url:
            info(f'Using API URL: {url}')

    # First try without auth (for public repos)
    try:
        request = Request(url)
        response = urlopen(request)
        content: bytes = response.read()
        return content
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 404):
            # Authentication might be needed
            if not auth_headers:
                auth_headers = get_auth_headers(url, auth_param)

            if auth_headers:
                info('Retrying with authentication...')
                request = Request(url)
                for header, value in auth_headers.items():
                    request.add_header(header, value)
                try:
                    response = urlopen(request)
                    result: bytes = response.read()
                    return result
                except urllib.error.HTTPError as auth_e:
                    if auth_e.code == 401:
                        error('Authentication failed. Check your token.')
                    elif auth_e.code == 403:
                        error('Access forbidden. Token may lack permissions.')
                    elif auth_e.code == 404:
                        error('Resource not found. Check URL and permissions.')
                    raise
            elif e.code == 404:
                raise
            else:
                warning('Authentication may be required for this URL')
                raise
        else:
            raise
    except urllib.error.URLError as e:
        if 'SSL' in str(e) or 'certificate' in str(e).lower():
            warning('SSL certificate verification failed, trying with unverified context')
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            request = Request(url)
            if auth_headers:
                for header, value in auth_headers.items():
                    request.add_header(header, value)

            response = urlopen(request, context=ctx)
            ctx_result: bytes = response.read()
            return ctx_result
        raise


def extract_front_matter(file_path: Path) -> dict[str, Any] | None:
    """Extract YAML front matter from a Markdown file.

    Args:
        file_path: Path to the markdown file

    Returns:
        dict: Parsed front matter data, or None if no front matter found
    """
    try:
        content = file_path.read_text(encoding='utf-8')

        # Check if file starts with front matter delimiter
        if not content.startswith('---'):
            return None

        # Find the closing delimiter
        end_match = content.find('\n---\n', 4)  # Start after first ---
        if end_match == -1:
            # Try alternative format with just --- at end of line
            end_match = content.find('\n---', 4)
            if end_match == -1:
                return None

        # Extract and parse the YAML content
        front_matter_text = content[4:end_match].strip()
        result = yaml.safe_load(front_matter_text)
        # Explicitly type check and return properly typed dict
        if isinstance(result, dict):
            # Cast to typed dict to satisfy pyright
            return cast(dict[str, Any], result)
        return None

    except Exception as e:
        warning(f'Failed to parse front matter from {file_path}: {e}')
        return None


def handle_resource(
    resource_path: str,
    destination: Path,
    config_source: str,
    base_url: str | None = None,
    auth_param: str | None = None,
) -> bool:
    """Handle a resource - either download from URL or copy from local path.

    Args:
        resource_path: Resource path from config (URL or local path)
        destination: Local destination path
        config_source: Where the config was loaded from
        base_url: Optional base URL from config
        auth_param: Optional auth parameter for private repos

    Returns:
        bool: True if successful, False otherwise
    """
    # Resolve the path
    resolved_path, is_remote = resolve_resource_path(resource_path, config_source, base_url)
    filename = destination.name

    # Check if destination already exists
    if destination.exists():
        info(f'File already exists: {filename} (overwriting)')

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)

        if is_remote:
            # Download from URL
            if is_binary_file(resolved_path):
                # Binary file - fetch as bytes and write bytes
                content_bytes = fetch_url_bytes_with_auth(resolved_path, auth_param=auth_param)
                destination.write_bytes(content_bytes)
            else:
                # Text file - fetch as text and write text
                content = fetch_url_with_auth(resolved_path, auth_param=auth_param)
                destination.write_text(content, encoding='utf-8')
            success(f'Downloaded: {filename}')
        else:
            # Copy from local path
            source_path = Path(resolved_path)
            if not source_path.exists():
                error(f'Local file not found: {resolved_path}')
                return False

            # Copy the file
            shutil.copy2(source_path, destination)
            success(f'Copied: {filename} from {source_path}')

        return True
    except Exception as e:
        error(f'Failed to handle {filename}: {e}')
        return False


def process_resources(
    resources: list[str],
    destination_dir: Path,
    resource_type: str,
    config_source: str,
    base_url: str | None = None,
    auth_param: str | None = None,
) -> bool:
    """Process resources (download from URL or copy from local) based on configuration.

    Args:
        resources: List of resource paths from config
        destination_dir: Directory to save resources
        resource_type: Type of resources (for logging)
        config_source: Where the config was loaded from
        base_url: Optional base URL from config
        auth_param: Optional auth parameter for private repos

    Returns:
        bool: True if all successful
    """
    if not resources:
        info(f'No {resource_type} to process')
        return True

    info(f'Processing {resource_type}...')

    for resource in resources:
        # Strip query parameters from URL to get clean filename
        clean_resource = resource.split('?')[0] if '?' in resource else resource
        filename = Path(clean_resource).name
        destination = destination_dir / filename
        handle_resource(resource, destination, config_source, base_url, auth_param)

    return True


def process_file_downloads(
    file_specs: list[dict[str, Any]],
    config_source: str,
    base_url: str | None = None,
    auth_param: str | None = None,
) -> bool:
    """Process file downloads/copies from configuration.

    Downloads files from URLs or copies from local paths to specified destinations.
    Supports cross-platform path expansion using ~ and environment variables.

    Args:
        file_specs: List of file specifications with 'source' and 'dest' keys.
                   Each spec is a dict: {'source': 'path/to/file', 'dest': '~/destination'}
        config_source: Where the config was loaded from (for resolving relative paths)
        base_url: Optional base URL override from config
        auth_param: Optional auth parameter for private repos

    Returns:
        True if all files processed successfully, False if any failed.

    Example:
        file_specs = [
            {'source': 'configs/settings.json', 'dest': '~/.config/app/'},
            {'source': 'https://example.com/file.txt', 'dest': '~/downloads/file.txt'}
        ]
        process_file_downloads(file_specs, config_source, base_url, auth)
    """
    if not file_specs:
        info('No files to download configured')
        return True

    info(f'Processing {len(file_specs)} file downloads...')
    success_count = 0
    failed_count = 0

    for file_spec in file_specs:
        source = file_spec.get('source')
        dest = file_spec.get('dest')

        if not source or not dest:
            # Emit a specific warning for missing keys
            if not source:
                warning(f'Invalid file specification: missing source ({file_spec})')
            elif not dest:
                warning(f'Invalid file specification: missing dest ({file_spec})')
            else:
                warning(f'Invalid file specification: {file_spec} (missing source or dest)')
            failed_count += 1
            continue

        # Expand destination path (~ and environment variables)
        # This makes it work cross-platform: ~/.config, %USERPROFILE%\bin, $HOME/.local
        expanded_dest = os.path.expanduser(str(dest))
        expanded_dest = os.path.expandvars(expanded_dest)
        dest_path = Path(expanded_dest)

        # Handle both file and directory destinations
        # If dest ends with separator or is existing directory, append source filename
        dest_str = str(dest)
        if dest_str.endswith(('/', '\\')) or (dest_path.exists() and dest_path.is_dir()):
            # Extract filename from source (remove query params if present)
            clean_source = str(source).split('?')[0]
            filename = Path(clean_source).name
            dest_path = dest_path / filename

        # Use existing handle_resource function for download/copy
        # This handles: URL downloads, local file copying, overwriting, directory creation
        if handle_resource(str(source), dest_path, config_source, base_url, auth_param):
            success_count += 1
        else:
            failed_count += 1

    # Print summary
    print()  # Blank line for readability
    if failed_count > 0:
        warning(f'File downloads: {success_count} succeeded, {failed_count} failed')
        return False

    success(f'All {success_count} files downloaded/copied successfully')
    return True


def process_skill(
    skill_config: dict[str, Any],
    skills_dir: Path,
    config_source: str,
    auth_param: str | None = None,
) -> bool:
    """Process and install a single skill.

    Downloads or copies all files specified in the skill configuration to the
    skill's directory, preserving the relative directory structure.

    Args:
        skill_config: Skill configuration dict with 'name', 'base', and 'files' keys
        skills_dir: Base skills directory (.claude/skills/)
        config_source: Where the config was loaded from
        auth_param: Optional authentication parameter for private repos

    Returns:
        bool: True if skill installed successfully, False otherwise
    """
    skill_name = skill_config.get('name')
    base = skill_config.get('base', '')
    files = skill_config.get('files', [])

    if not skill_name:
        error("Skill configuration missing 'name' field")
        return False

    if not files:
        error(f"Skill '{skill_name}': No files specified")
        return False

    # Create skill directory
    skill_dir = skills_dir / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)

    info(f'Installing skill: {skill_name}')

    success_count = 0
    for file_path in files:
        if not isinstance(file_path, str):
            continue

        # Destination preserves relative path structure (e.g., scripts/fill_form.py)
        destination = skill_dir / file_path

        # Check if destination already exists (consistent with handle_resource)
        if destination.exists():
            info(f'  File already exists: {file_path} (overwriting)')

        destination.parent.mkdir(parents=True, exist_ok=True)

        # Build source path
        if base.startswith(('http://', 'https://')):
            # Remote source - convert tree/blob URLs to raw URLs for download
            raw_base = convert_to_raw_url(base)
            source_url = f"{raw_base.rstrip('/')}/{file_path}"
            try:
                if is_binary_file(file_path):
                    # Binary file - fetch as bytes and write bytes
                    content_bytes = fetch_url_bytes_with_auth(source_url, auth_param=auth_param)
                    destination.write_bytes(content_bytes)
                else:
                    # Text file - fetch as text and write text
                    content = fetch_url_with_auth(source_url, auth_param=auth_param)
                    destination.write_text(content, encoding='utf-8')
                success(f'  Downloaded: {file_path}')
                success_count += 1
            except Exception as e:
                error(f'  Failed to download {file_path}: {e}')
        else:
            # Local source - copy file
            resolved_base, _ = resolve_resource_path(base, config_source, None)
            source_path = Path(resolved_base) / file_path

            if not source_path.exists():
                error(f'  Local file not found: {source_path}')
                continue

            try:
                shutil.copy2(source_path, destination)
                success(f'  Copied: {file_path}')
                success_count += 1
            except Exception as e:
                error(f'  Failed to copy {file_path}: {e}')

    # Verify SKILL.md was installed (required for a valid skill)
    skill_md = skill_dir / 'SKILL.md'
    if not skill_md.exists():
        error(f"Skill '{skill_name}': SKILL.md was not installed - skill may be invalid")
        return False

    success(f"Skill '{skill_name}' installed ({success_count}/{len(files)} files)")
    return success_count == len(files)


def process_skills(
    skills_config: list[dict[str, Any]],
    skills_dir: Path,
    config_source: str,
    auth_param: str | None = None,
) -> bool:
    """Process all skills from configuration.

    Iterates through all skill configurations and installs each one to the
    skills directory.

    Args:
        skills_config: List of skill configuration dictionaries
        skills_dir: Base skills directory (.claude/skills/)
        config_source: Where the config was loaded from
        auth_param: Optional authentication parameter for private repos

    Returns:
        bool: True if all skills installed successfully, False otherwise
    """
    if not skills_config:
        info('No skills configured')
        return True

    info(f'Processing {len(skills_config)} skill(s)...')
    all_success = True

    for skill_config in skills_config:
        if not process_skill(skill_config, skills_dir, config_source, auth_param):
            all_success = False

    return all_success


def install_claude(version: str | None = None) -> bool:
    """Install Claude Code if needed.

    Args:
        version: Specific Claude Code version to install (e.g., "1.0.128").
                If None, installs the latest version.

    Returns:
        True if installation succeeded, False otherwise.

    Raises:
        Exception: If installation fails with exit code.
        URLError: If there's an error downloading the installer script.
    """
    # Check if admin rights needed for Windows installation
    if platform.system() == 'Windows' and not is_admin():
        warning('Installing Claude Code requires administrator privileges on Windows')
        warning('This includes installing Node.js and Git if not already present')
        info('')
        info('Requesting administrator elevation...')
        request_admin_elevation()
        # If we reach here, elevation was denied
        error('Administrator elevation was denied')
        error('Installation cannot proceed without administrator privileges')
        error('')
        error('Please run this script as administrator manually:')
        error('  1. Right-click on your terminal')
        error('  2. Select "Run as administrator"')
        error('  3. Run the setup command again')
        return False

    if version:
        info(f'Installing Claude Code version {version}...')
        # Set environment variable for the installer scripts to use
        os.environ['CLAUDE_VERSION'] = version
    else:
        info('Installing Claude Code (latest version)...')

    system = platform.system()
    temp_installer: str | None = None

    try:
        # Download the appropriate installer script
        if system == 'Windows':
            installer_url = 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/install-claude-windows.ps1'
            with tempfile.NamedTemporaryFile(suffix='.ps1', delete=False, mode='w') as tmp:
                try:
                    response = urlopen(installer_url)
                    content = response.read().decode('utf-8')
                except urllib.error.URLError as e:
                    if 'SSL' in str(e) or 'certificate' in str(e).lower():
                        warning('SSL certificate verification failed, trying with unverified context')
                        ctx = ssl.create_default_context()
                        ctx.check_hostname = False
                        ctx.verify_mode = ssl.CERT_NONE
                        response = urlopen(installer_url, context=ctx)
                        content = response.read().decode('utf-8')
                    else:
                        raise
                tmp.write(content)
                temp_installer = tmp.name

            # Run PowerShell installer
            result = run_command(
                [
                    'powershell',
                    '-NoProfile',
                    '-ExecutionPolicy',
                    'Bypass',
                    '-File',
                    temp_installer,
                ],
                capture_output=False,
            )

        elif system == 'Darwin':  # macOS
            installer_url = (
                'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/install-claude-macos.sh'
            )
            result = run_command(
                [
                    'bash',
                    '-c',
                    f'curl -fsSL {installer_url} | bash',
                ],
                capture_output=False,
            )

        else:  # Linux
            installer_url = (
                'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/install-claude-linux.sh'
            )
            result = run_command(
                [
                    'bash',
                    '-c',
                    f'curl -fsSL {installer_url} | bash',
                ],
                capture_output=False,
            )

        # Clean up temp file on Windows
        if system == 'Windows' and temp_installer:
            with contextlib.suppress(Exception):
                os.unlink(temp_installer)

        if result.returncode == 0:
            success('Claude Code installation complete')
            return True
        raise Exception(f'Installation failed with exit code: {result.returncode}')

    except Exception as e:
        error(f'Failed to install Claude Code: {e}')
        info('You can retry manually or use --skip-install if Claude Code is already installed')
        return False


def verify_nodejs_available() -> bool:
    """Verify Node.js is available before MCP configuration.

    Uses shutil.which() to find Node.js in PATH, supporting all installation methods
    (official installer, nvm, fnm, volta, scoop, chocolatey, etc.).

    Returns:
        True if Node.js is available, False otherwise.
    """
    if platform.system() != 'Windows':
        return True  # Assume available on Unix

    # Primary: Use shutil.which for proper PATH-based detection
    node_path = shutil.which('node')
    if node_path:
        # Verify node actually works
        try:
            result = subprocess.run(
                [node_path, '--version'],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                success(f'Node.js verified at: {node_path} ({result.stdout.strip()})')
                return True
        except (subprocess.TimeoutExpired, OSError):
            pass

    # Secondary: Try find_command_robust with common installation paths
    node_path = find_command_robust('node')
    if node_path:
        # Verify node actually works
        try:
            result = subprocess.run(
                [node_path, '--version'],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                # Add to PATH if not already there
                node_dir = str(Path(node_path).parent)
                current_path = os.environ.get('PATH', '')
                if node_dir.lower() not in current_path.lower():
                    os.environ['PATH'] = f'{node_dir};{current_path}'
                    info(f'Added {node_dir} to PATH')
                success(f'Node.js verified at: {node_path} ({result.stdout.strip()})')
                return True
        except (subprocess.TimeoutExpired, OSError):
            pass

    error('Node.js not found in PATH')
    return False


def configure_mcp_server(server: dict[str, Any]) -> bool:
    """Configure a single MCP server."""
    name = server.get('name')
    scope = server.get('scope', 'user')
    transport = server.get('transport')
    url = server.get('url')
    command = server.get('command')
    header = server.get('header')
    env_config = server.get('env')

    # Normalize env to list for consistent handling (supports both string and list syntax)
    env_list: list[str] = []
    if env_config:
        if isinstance(env_config, str):
            # Single env var (backward compatibility)
            env_list = [env_config]
        elif isinstance(env_config, list):
            # Multiple env vars (new functionality)
            for item in cast(list[object], env_config):
                env_list.append(str(item))
        else:
            error(f'Invalid env format for {name}: expected string or list')
            return False

    if not name:
        error('MCP server configuration missing name')
        return False

    info(f'Configuring MCP server: {name}')
    system = platform.system()
    claude_cmd = None

    # Use robust command discovery with built-in retry and fallback paths
    claude_cmd = find_command_robust('claude')

    if not claude_cmd:
        error('Claude command not accessible after installation!')
        error('This may indicate a PATH synchronization issue between installation and configuration steps.')
        error('Try running the command again or opening a new terminal session.')
        return False

    try:
        # Remove existing MCP server from all scopes to avoid conflicts
        # When servers with the same name exist at multiple scopes, local-scoped servers
        # take precedence, followed by project, then user - so we remove from all scopes
        info(f'Removing existing MCP server {name} from all scopes if present...')
        scopes_removed: list[str] = []
        for remove_scope in ['user', 'local', 'project']:
            remove_cmd = [str(claude_cmd), 'mcp', 'remove', '--scope', remove_scope, name]
            result = run_command(remove_cmd, capture_output=True)
            # Check if removal was successful (exit code 0)
            if result.returncode == 0:
                scopes_removed.append(remove_scope)

        if scopes_removed:
            info(f"Removed MCP server {name} from scope(s): {', '.join(scopes_removed)}")
        else:
            info(f'MCP server {name} was not found in any scope')

        # Build the base command
        base_cmd = [str(claude_cmd), 'mcp', 'add']

        if scope:
            base_cmd.extend(['--scope', scope])

        # Note: Don't add name here - it must be added after options for correct argument order

        # Handle different transport types
        if transport and url:
            # HTTP or SSE transport
            base_cmd.append(name)  # Add name here for HTTP/SSE transport
            # Add all environment variables
            for env_var in env_list:
                base_cmd.extend(['--env', env_var])
            base_cmd.extend(['--transport', transport, url])
            if header:
                base_cmd.extend(['--header', header])

            # Windows HTTP transport - use bash for consistent cross-platform behavior
            # This eliminates PowerShell's exit code quirks and CMD escaping issues
            if system == 'Windows':
                debug_log(f'=== MCP Server Configuration: {name} ===')
                debug_log(f'claude_cmd: {claude_cmd}')

                # Build explicit PATH including Node.js location
                nodejs_path = r'C:\Program Files\nodejs'
                current_path = os.environ.get('PATH', '')

                # Build Windows PATH first, then convert to Unix format
                if Path(nodejs_path).exists() and nodejs_path not in current_path:
                    windows_explicit_path = f'{nodejs_path};{current_path}'
                else:
                    windows_explicit_path = current_path

                # Convert Windows paths to Git Bash Unix-style paths
                unix_explicit_path = convert_path_env_to_unix(windows_explicit_path)
                # Prefer shell script over .cmd for Git Bash to avoid CMD.exe & parsing issues
                bash_preferred_cmd = get_bash_preferred_command(str(claude_cmd))
                unix_claude_cmd = convert_to_unix_path(bash_preferred_cmd)

                debug_log(f'unix_claude_cmd: {unix_claude_cmd}')
                path_preview = unix_explicit_path[:200] + '...' if len(unix_explicit_path) > 200 else unix_explicit_path
                debug_log(f'unix_explicit_path: {path_preview}')

                env_flags = ' '.join(f'--env "{e}"' for e in env_list) if env_list else ''
                env_part = f' {env_flags}' if env_flags else ''
                header_part = f' --header "{header}"' if header else ''

                bash_cmd = (
                    f'export PATH="{unix_explicit_path}:$PATH" && '
                    f'"{unix_claude_cmd}" mcp add --scope {scope} {name}{env_part} '
                    f'--transport {transport}{header_part} "{url}"'
                )

                bash_cmd_preview = bash_cmd[:300] + '...' if len(bash_cmd) > 300 else bash_cmd
                debug_log(f'First attempt bash_cmd: {bash_cmd_preview}')
                result = run_bash_command(bash_cmd, capture_output=True, login_shell=True)
                debug_log(f'First attempt result: returncode={result.returncode}')
                if result.returncode != 0:
                    debug_log(f'First attempt failed! stdout={result.stdout}, stderr={result.stderr}')
            else:
                # On Unix, use bash with updated PATH (consistent with Windows)
                parent_dir = Path(claude_cmd).parent
                bash_cmd = f'export PATH="{parent_dir}:$PATH" && ' + ' '.join(shlex.quote(str(arg)) for arg in base_cmd)
                result = run_bash_command(bash_cmd, capture_output=True, login_shell=True)
        elif command:
            # Stdio transport (command)

            # Build the command properly
            base_cmd.append(name)  # Add name FIRST, before post-name options
            # Add all environment variables
            for env_var in env_list:
                base_cmd.extend(['--env', env_var])
            base_cmd.extend(['--'])

            # Special handling for npx (needs cmd /c wrapper on Windows)
            if 'npx' in command:
                base_cmd.extend(['cmd', '/c', command])
            else:
                base_cmd.extend(command.split())

            # Windows STDIO transport - use bash for consistent cross-platform behavior
            # This unifies STDIO with HTTP transport (both use run_bash_command)
            if system == 'Windows':
                debug_log(f'=== MCP Server Configuration (STDIO): {name} ===')
                debug_log(f'claude_cmd: {claude_cmd}')

                # Build explicit PATH including Node.js location
                nodejs_path = r'C:\Program Files\nodejs'
                current_path = os.environ.get('PATH', '')

                # Build Windows PATH first, then convert to Unix format
                if Path(nodejs_path).exists() and nodejs_path not in current_path:
                    windows_explicit_path = f'{nodejs_path};{current_path}'
                else:
                    windows_explicit_path = current_path

                # Convert Windows paths to Git Bash Unix-style paths
                unix_explicit_path = convert_path_env_to_unix(windows_explicit_path)
                # Prefer shell script over .cmd for Git Bash to avoid CMD.exe & parsing issues
                bash_preferred_cmd = get_bash_preferred_command(str(claude_cmd))
                unix_claude_cmd = convert_to_unix_path(bash_preferred_cmd)

                debug_log(f'unix_claude_cmd: {unix_claude_cmd}')
                path_preview = unix_explicit_path[:200] + '...' if len(unix_explicit_path) > 200 else unix_explicit_path
                debug_log(f'unix_explicit_path: {path_preview}')

                env_flags = ' '.join(f'--env "{e}"' for e in env_list) if env_list else ''
                env_part = f' {env_flags}' if env_flags else ''

                # Build command string for STDIO
                # npx needs cmd /c wrapper on Windows even in bash
                command_str = f'cmd /c {command}' if 'npx' in command else command

                bash_cmd = (
                    f'export PATH="{unix_explicit_path}:$PATH" && '
                    f'"{unix_claude_cmd}" mcp add --scope {scope} {name}{env_part} '
                    f'-- {command_str}'
                )

                bash_cmd_preview = bash_cmd[:300] + '...' if len(bash_cmd) > 300 else bash_cmd
                debug_log(f'STDIO bash_cmd: {bash_cmd_preview}')

                info(f'Configuring stdio MCP server {name}...')
                result = run_bash_command(bash_cmd, capture_output=True, login_shell=True)
                debug_log(f'STDIO result: returncode={result.returncode}')
                if result.returncode != 0:
                    debug_log(f'STDIO failed! stdout={result.stdout}, stderr={result.stderr}')
            else:
                # Unix-like systems - direct execution
                info(f'Configuring stdio MCP server {name}...')
                result = run_command(base_cmd, capture_output=True)
        else:
            error(f'MCP server {name} missing url or command')
            return False

        # Check if successful
        if result.returncode == 0:
            success(f'MCP server {name} configured successfully!')
            return True

        # Configuration failed - log detailed error information
        error(f'MCP configuration failed: exit code {result.returncode}')
        if result.stderr:
            error(f'Error details: {result.stderr}')
        if result.stdout:
            info(f'Output: {result.stdout}')

        # Check for Node.js v25 incompatibility signature
        stderr_text = str(result.stderr) if result.stderr else ''
        if 'TypeError' in stderr_text and 'prototype' in stderr_text:
            error('This appears to be a Node.js v25 incompatibility issue')
            error('Claude Code is not yet compatible with Node.js v25+')
            info('Node.js v25 removed the SlowBuffer API that Claude Code depends on')
            info('Please downgrade to Node.js v22 or v20 (LTS)')

        return False

    except Exception as e:
        error(f'Failed to configure MCP server {name}: {e}')
        return False


def configure_all_mcp_servers(servers: list[dict[str, Any]]) -> bool:
    """Configure all MCP servers from configuration."""
    if not servers:
        info('No MCP servers to configure')
        return True

    info('Configuring MCP servers...')

    for server in servers:
        configure_mcp_server(server)

    return True


def download_hook_files(
    hooks: dict[str, Any],
    claude_user_dir: Path,
    config_source: str | None = None,
    base_url: str | None = None,
    auth_param: str | None = None,
) -> bool:
    """Download hook files from configuration.

    Args:
        hooks: Hooks configuration dictionary with 'files' key
        claude_user_dir: Path to Claude user directory
        config_source: Optional config source for resolving resource paths
        base_url: Optional base URL for resolving resources
        auth_param: Optional authentication parameter

    Returns:
        bool: True if successful, False otherwise.
    """
    hook_files = hooks.get('files', [])

    if not hook_files:
        info('No hook files to download')
        return True

    hooks_dir = claude_user_dir / 'hooks'
    hooks_dir.mkdir(parents=True, exist_ok=True)

    for file in hook_files:
        # Strip query parameters from URL to get clean filename
        clean_file = file.split('?')[0] if '?' in file else file
        filename = Path(clean_file).name
        destination = hooks_dir / filename
        # Handle hook files (download or copy)
        if config_source:
            handle_resource(file, destination, config_source, base_url, auth_param)
        else:
            # This shouldn't happen, but handle gracefully
            error(f'No config source provided for hook file: {file}')
            return False

    return True


def create_additional_settings(
    hooks: dict[str, Any],
    claude_user_dir: Path,
    command_name: str,
    model: str | None = None,
    permissions: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
    include_co_authored_by: bool | None = None,
    always_thinking_enabled: bool | None = None,
    company_announcements: list[str] | None = None,
    attribution: dict[str, str] | None = None,
    status_line: dict[str, Any] | None = None,
) -> bool:
    """Create {command_name}-additional-settings.json with environment-specific settings.

    This file is always overwritten to avoid duplicate hooks when re-running the installer.
    It's loaded via --settings flag when launching Claude.

    Args:
        hooks: Hooks configuration dictionary with 'files' and 'events' keys
        claude_user_dir: Path to Claude user directory
        command_name: Name of the command for the environment-specific settings file
        model: Optional model alias or custom model name
        permissions: Optional permissions configuration dict
        env: Optional environment variables dict
        include_co_authored_by: DEPRECATED - Optional flag to include co-authored-by in commits.
            Use 'attribution' parameter instead.
        always_thinking_enabled: Optional flag to enable always-on thinking mode
        company_announcements: Optional list of company announcement strings
        attribution: Optional dict with 'commit' and 'pr' keys for custom attribution strings.
            Empty strings hide attribution. Takes precedence over include_co_authored_by.
        status_line: Optional dict with 'file' key for status line script path, optional
            'padding' key, and optional 'config' key for config file reference.
            Both the script and config file are downloaded to ~/.claude/hooks/ and
            the config path is appended as a command line argument.

    Returns:
        bool: True if successful, False otherwise.
    """
    info(f'Creating {command_name}-additional-settings.json...')

    # Create fresh settings structure for this environment
    settings: dict[str, Any] = {}

    # Add model if specified
    if model:
        settings['model'] = model
        info(f'Setting model: {model}')

    # Handle permissions from configuration
    final_permissions = {}

    # Use permissions from env config if provided
    if permissions:
        final_permissions = permissions.copy()
        info('Using permissions from environment configuration')

    # Add permissions to settings if we have any
    if final_permissions:
        settings['permissions'] = final_permissions

    # Add environment variables if specified
    if env:
        settings['env'] = env
        info(f'Setting {len(env)} environment variables')
        for key in env:
            info(f'  - {key}')

    # Handle attribution settings (new format takes precedence)
    if attribution is not None:
        settings['attribution'] = attribution
        commit_preview = repr(attribution.get('commit', ''))[:30]
        pr_preview = repr(attribution.get('pr', ''))[:30]
        info(f'Setting attribution: commit={commit_preview}, pr={pr_preview}')
        if include_co_authored_by is not None:
            warning('Both "attribution" and deprecated "include-co-authored-by" specified. Using "attribution".')
    elif include_co_authored_by is not None:
        # DEPRECATED: Convert to new format
        warning('Config key "include-co-authored-by" is deprecated. Use "attribution" instead.')
        if include_co_authored_by is False:
            # false -> hide attribution
            settings['attribution'] = {'commit': '', 'pr': ''}
            info('Setting attribution: hiding all (converted from include-co-authored-by: false)')
        # Note: true -> don't set anything, let Claude Code use defaults
        else:
            info('include-co-authored-by: true -> using Claude Code defaults (no attribution override)')

    # Add alwaysThinkingEnabled if explicitly set (None means not configured, leave as default)
    if always_thinking_enabled is not None:
        settings['alwaysThinkingEnabled'] = always_thinking_enabled
        info(f'Setting alwaysThinkingEnabled: {always_thinking_enabled}')

    # Add companyAnnouncements if explicitly set (None means not configured, leave as default)
    if company_announcements is not None:
        settings['companyAnnouncements'] = company_announcements
        info(f'Setting companyAnnouncements: {len(company_announcements)} announcement(s)')

    # Add statusLine if explicitly set (None means not configured, leave as default)
    if status_line is not None:
        status_line_file = status_line.get('file')
        if status_line_file:
            # Build absolute path to the hook file in .claude/hooks/
            # Strip query parameters from filename
            clean_filename = status_line_file.split('?')[0] if '?' in status_line_file else status_line_file
            filename = Path(clean_filename).name
            hook_path = claude_user_dir / 'hooks' / filename
            hook_path_str = hook_path.as_posix()

            # Extract optional config file reference
            config = status_line.get('config')

            # Determine command based on file extension
            if filename.lower().endswith(('.py', '.pyw')):
                # Python script - use uv run
                status_line_command = f'uv run --no-project --python 3.12 {hook_path_str}'

                # Append config file path if specified
                if config:
                    # Strip query parameters from config filename
                    clean_config = config.split('?')[0] if '?' in config else config
                    config_path = claude_user_dir / 'hooks' / Path(clean_config).name
                    config_path_str = config_path.as_posix()
                    status_line_command = f'{status_line_command} {config_path_str}'
            else:
                # Other file - use path directly
                status_line_command = hook_path_str

                # Append config file path if specified
                if config:
                    # Strip query parameters from config filename
                    clean_config = config.split('?')[0] if '?' in config else config
                    config_path = claude_user_dir / 'hooks' / Path(clean_config).name
                    config_path_str = config_path.as_posix()
                    status_line_command = f'{status_line_command} {config_path_str}'

            status_line_config: dict[str, Any] = {
                'type': 'command',
                'command': status_line_command,
            }

            # Add optional padding
            padding = status_line.get('padding')
            if padding is not None:
                status_line_config['padding'] = padding

            settings['statusLine'] = status_line_config
            info(f'Setting statusLine: {filename}')

    # Handle hooks if present
    hook_events: list[dict[str, Any]] = []

    if hooks:
        settings['hooks'] = {}
        # Extract events from the hooks configuration (files are downloaded separately)
        hook_events = hooks.get('events', [])

    # Process each hook event
    for hook in hook_events:
        event = hook.get('event')
        matcher = hook.get('matcher', '')
        hook_type = hook.get('type', 'command')
        command = hook.get('command')
        config = hook.get('config')  # Optional config file reference

        if not event:
            warning('Invalid hook configuration: missing event, skipping')
            continue

        # For command hooks, command is required; for prompt hooks, prompt is required
        if hook_type == 'command' and not command:
            warning('Invalid command hook: missing command, skipping')
            continue
        if hook_type == 'prompt' and not hook.get('prompt'):
            warning('Invalid prompt hook: missing prompt, skipping')
            continue

        # Add to settings
        if event not in settings['hooks']:
            settings['hooks'][event] = []

        # Find or create matcher group
        matcher_group: dict[str, Any] | None = None
        hooks_list_raw = cast(Any, settings['hooks'][event])  # Cast for pyright
        if isinstance(hooks_list_raw, list):
            hooks_list: list[dict[str, Any]] = cast(list[dict[str, Any]], hooks_list_raw)
            for group_item in hooks_list:
                if group_item.get('matcher') == matcher:
                    matcher_group = group_item
                    break

        if not matcher_group:
            matcher_group = {
                'matcher': matcher,
                'hooks': [],
            }
            hooks_event_list_raw = cast(Any, settings['hooks'][event])  # Cast for pyright
            if isinstance(hooks_event_list_raw, list):
                hooks_event_list: list[dict[str, Any]] = cast(list[dict[str, Any]], hooks_event_list_raw)
                hooks_event_list.append(matcher_group)

        # Build hook configuration based on hook type
        hook_config: dict[str, Any]

        if hook_type == 'command':
            # Command hooks require file path processing
            # command is guaranteed to be non-None here due to validation above
            assert command is not None

            # Build the proper command based on file type
            # Strip query parameters from command if present
            clean_command = command.split('?')[0] if '?' in command else command

            # Check if this looks like a file reference or a direct command
            # File references typically don't contain spaces (just the filename)
            # Direct commands like 'echo "test"' contain spaces
            is_file_reference = ' ' not in clean_command

            if is_file_reference:
                # Determine if this is a Python script (case-insensitive check)
                # Supports both .py and .pyw extensions
                is_python_script = clean_command.lower().endswith(('.py', '.pyw'))

                if is_python_script:
                    # Python script - use uv run for cross-platform execution
                    # Build absolute path to the hook file in .claude/hooks/
                    hook_path = claude_user_dir / 'hooks' / Path(clean_command).name
                    # Use POSIX-style path (forward slashes) for cross-platform compatibility
                    # This works on Windows, macOS, and Linux, and avoids JSON escaping issues
                    hook_path_str = hook_path.as_posix()
                    # Use uv run with Python 3.12 - works cross-platform without PATH dependency
                    # uv automatically downloads Python 3.12 if not installed
                    # For .pyw files on Windows, uv automatically uses pythonw
                    # Use --no-project flag to prevent uv from detecting and applying project Python requirements
                    full_command = f'uv run --no-project --python 3.12 {hook_path_str}'

                    # Append config file path if specified
                    if config:
                        # Strip query parameters from config filename
                        clean_config = config.split('?')[0] if '?' in config else config
                        config_path = claude_user_dir / 'hooks' / Path(clean_config).name
                        config_path_str = config_path.as_posix()
                        full_command = f'{full_command} {config_path_str}'
                else:
                    # Other file - build absolute path and use as-is
                    # System will handle execution based on file extension (.sh, .bat, .cmd, .ps1, etc.)
                    hook_path = claude_user_dir / 'hooks' / Path(clean_command).name
                    hook_path_str = hook_path.as_posix()
                    full_command = hook_path_str

                    # Append config file path if specified
                    if config:
                        # Strip query parameters from config filename
                        clean_config = config.split('?')[0] if '?' in config else config
                        config_path = claude_user_dir / 'hooks' / Path(clean_config).name
                        config_path_str = config_path.as_posix()
                        full_command = f'{full_command} {config_path_str}'
            else:
                # Direct command with spaces - use as-is
                full_command = command

            # Add hook configuration for command hook
            hook_config = {
                'type': hook_type,
                'command': full_command,
            }
        else:
            # Prompt hook - no file processing needed, use inline prompt
            hook_config = {
                'type': hook_type,
                'prompt': hook.get('prompt', ''),
            }
            # Include timeout if specified
            if hook.get('timeout'):
                hook_config['timeout'] = hook.get('timeout')

        if matcher_group and 'hooks' in matcher_group:
            matcher_hooks_raw = matcher_group['hooks']
            if isinstance(matcher_hooks_raw, list):
                # Cast to typed list for pyright
                matcher_hooks_list = cast(list[object], matcher_hooks_raw)
                matcher_hooks_list.append(hook_config)

    # Save additional settings (always overwrite)
    additional_settings_path = claude_user_dir / f'{command_name}-additional-settings.json'
    try:
        with open(additional_settings_path, 'w') as f:
            json.dump(settings, f, indent=2)
        success(f'Created {command_name}-additional-settings.json')
        return True
    except Exception as e:
        error(f'Failed to save {command_name}-additional-settings.json: {e}')
        return False


def create_launcher_script(
    claude_user_dir: Path,
    command_name: str,
    system_prompt_file: str | None = None,
    mode: str = 'replace',
) -> Path | None:
    """Create launcher script for starting Claude with optional system prompt.

    Args:
        claude_user_dir: Path to Claude user directory
        command_name: Name of the command to create launcher for
        system_prompt_file: Optional system prompt filename (if None, only settings are used)
        mode: System prompt mode ('append' or 'replace'), defaults to 'replace'

    Returns:
        Path to launcher script if created successfully, None otherwise
    """
    launcher_path = claude_user_dir / f'start-{command_name}'

    system = platform.system()

    try:
        if system == 'Windows':
            # Create PowerShell launcher for Windows
            launcher_path = launcher_path.with_suffix('.ps1')
            launcher_content = f'''# Claude Code Environment Launcher
# This script starts Claude Code with the configured environment

$claudeUserDir = Join-Path $env:USERPROFILE ".claude"

Write-Host "Starting Claude Code with {command_name} configuration..." -ForegroundColor Green

# Find Git Bash (required for Claude Code on Windows)
$bashPath = $null
if (Test-Path "C:\\Program Files\\Git\\bin\\bash.exe") {{
    $bashPath = "C:\\Program Files\\Git\\bin\\bash.exe"
}} elseif (Test-Path "C:\\Program Files (x86)\\Git\\bin\\bash.exe") {{
    $bashPath = "C:\\Program Files (x86)\\Git\\bin\\bash.exe"
}} else {{
    Write-Host "Error: Git Bash not found! Please install Git for Windows." -ForegroundColor Red
    exit 1
}}

# Call the shared script
$scriptPath = Join-Path $claudeUserDir "launch-{command_name}.sh"

if ($args.Count -gt 0) {{
    Write-Host "Passing additional arguments: $args" -ForegroundColor Cyan
    & $bashPath --login $scriptPath @args
}} else {{
    & $bashPath --login $scriptPath
}}
'''
            launcher_path.write_text(launcher_content)

            # Also create a CMD batch file wrapper
            batch_path = claude_user_dir / f'start-{command_name}.cmd'
            batch_content = f'''@echo off
REM Claude Code Environment Launcher for CMD
REM This script starts Claude Code with the configured environment

echo Starting Claude Code with {command_name} configuration...

REM Call shared script
set "BASH_EXE=C:\\Program Files\\Git\\bin\\bash.exe"
if not exist "%BASH_EXE%" set "BASH_EXE=C:\\Program Files (x86)\\Git\\bin\\bash.exe"

set "SCRIPT_WIN=%USERPROFILE%\\.claude\\launch-{command_name}.sh"

if "%~1"=="" (
    "%BASH_EXE%" --login "%SCRIPT_WIN%"
) else (
    echo Passing additional arguments: %*
    "%BASH_EXE%" --login "%SCRIPT_WIN%" %*
)
'''
            batch_path.write_text(batch_content)

            # Create shared POSIX script that actually launches Claude
            shared_sh = claude_user_dir / f'launch-{command_name}.sh'

            # Build the exec command based on whether system prompt is provided
            if system_prompt_file:
                # Load prompt file first (common for both modes)
                shared_sh_content = f'''#!/usr/bin/env bash
set -euo pipefail

# Get Windows path for settings
SETTINGS_WIN="$(cygpath -m "$HOME/.claude/{command_name}-additional-settings.json" 2>/dev/null ||
  echo "$HOME/.claude/{command_name}-additional-settings.json")"

PROMPT_PATH="$HOME/.claude/prompts/{system_prompt_file}"
if [ ! -f "$PROMPT_PATH" ]; then
  echo "Error: System prompt not found at $PROMPT_PATH" >&2
  exit 1
fi

# Version detection function
get_claude_version() {{
  claude --version 2>/dev/null | grep -oP '\\d+\\.\\d+\\.\\d+' | head -1
}}

# Version comparison function (checks if version1 >= version2)
version_ge() {{
  local version1="$1"
  local version2="$2"

  # If version detection failed, return false (fallback to safe defaults)
  if [ -z "$version1" ]; then
    return 1
  fi

  # Try using sort -V if available (most reliable)
  if command -v sort >/dev/null 2>&1 && echo | sort -V >/dev/null 2>&1; then
    [ "$(printf '%s\\n' "$version1" "$version2" | sort -V | tail -n1)" = "$version1" ]
  else
    # Manual comparison fallback
    local IFS='.'
    local i ver1=($version1) ver2=($version2)
    # Fill empty positions with zeros
    for ((i=0; i<3; i++)); do
      ver1[i]=${{ver1[i]:-0}}
      ver2[i]=${{ver2[i]:-0}}
    done
    # Compare each component
    for ((i=0; i<3; i++)); do
      if ((10#${{ver1[i]}} > 10#${{ver2[i]}})); then
        return 0
      elif ((10#${{ver1[i]}} < 10#${{ver2[i]}})); then
        return 1
      fi
    done
    return 0
  fi
}}

# Detect Claude Code version
CLAUDE_VERSION=$(get_claude_version)

# File size detection function (cross-platform)
get_file_size() {{
  local file="$1"
  # Try GNU/Linux syntax
  if stat -c %s "$file" 2>/dev/null; then
    return 0
  # Try BSD/macOS syntax
  elif stat -f %z "$file" 2>/dev/null; then
    return 0
  # Universal fallback
  else
    wc -c < "$file" | tr -d ' '
  fi
}}

# Safe prompt size threshold (4KB)
SAFE_PROMPT_SIZE=4096

'''
                # Add mode-specific logic
                if mode == 'replace':
                    # Replace mode: Check for continuation flags and use appropriate flag
                    shared_sh_content += '''# Replace mode: Check for continuation flags
HAS_CONTINUE=false
for arg in "$@"; do
  if [[ "$arg" == "--continue" || "$arg" == "-c" || "$arg" == "--resume" || "$arg" == "-r" ]]; then
    HAS_CONTINUE=true
    break
  fi
done

# For v2.0.64+: bug #11641 is fixed, --system-prompt works correctly with --continue/--resume
if version_ge "$CLAUDE_VERSION" "2.0.64"; then
  # Fixed in v2.0.64: always use --system-prompt-file (no need for workaround)
  exec claude --system-prompt-file "$PROMPT_PATH" "$@" --settings "$SETTINGS_WIN"
elif [ "$HAS_CONTINUE" = true ]; then
  # Legacy workaround for v < 2.0.64: use --append-system-prompt for continuation
  # Continuation: use --append-system-prompt-file if available (v2.0.34+)
  if version_ge "$CLAUDE_VERSION" "2.0.34"; then
    exec claude --append-system-prompt-file "$PROMPT_PATH" "$@" --settings "$SETTINGS_WIN"
  else
    # For Claude < 2.0.34: check prompt size to avoid "Argument list too long"
    PROMPT_SIZE=$(get_file_size "$PROMPT_PATH")
    if [ "$PROMPT_SIZE" -lt "$SAFE_PROMPT_SIZE" ]; then
      # Small prompt: safe to use content-based flag
      PROMPT_CONTENT=$(cat "$PROMPT_PATH")
      exec claude --append-system-prompt "$PROMPT_CONTENT" "$@" --settings "$SETTINGS_WIN"
    else
      # Large prompt: skip to prevent error
      echo "Warning: System prompt too large ($PROMPT_SIZE bytes) for Claude < 2.0.34" >&2
      echo "Skipping prompt to prevent 'Argument list too long' error" >&2
      echo "Solutions: 1) Upgrade to Claude v2.0.34+, 2) Reduce prompt to <4KB" >&2
      exec claude "$@" --settings "$SETTINGS_WIN"
    fi
  fi
else
  # New session: use --system-prompt-file (available in v2.0.14+)
  if version_ge "$CLAUDE_VERSION" "2.0.14"; then
    exec claude --system-prompt-file "$PROMPT_PATH" "$@" --settings "$SETTINGS_WIN"
  else
    # Fallback to content-based flag for very old versions
    PROMPT_CONTENT=$(cat "$PROMPT_PATH")
    exec claude --system-prompt "$PROMPT_CONTENT" "$@" --settings "$SETTINGS_WIN"
  fi
fi
'''
                else:  # mode == 'append'
                    # Append mode: use --append-system-prompt-file if available
                    shared_sh_content += '''# Append mode: use --append-system-prompt-file if available (v2.0.34+)
if version_ge "$CLAUDE_VERSION" "2.0.34"; then
  exec claude --append-system-prompt-file "$PROMPT_PATH" "$@" --settings "$SETTINGS_WIN"
else
  # For Claude < 2.0.34: check prompt size to avoid "Argument list too long"
  PROMPT_SIZE=$(get_file_size "$PROMPT_PATH")
  if [ "$PROMPT_SIZE" -lt "$SAFE_PROMPT_SIZE" ]; then
    # Small prompt: safe to use content-based flag
    PROMPT_CONTENT=$(cat "$PROMPT_PATH")
    exec claude --append-system-prompt "$PROMPT_CONTENT" "$@" --settings "$SETTINGS_WIN"
  else
    # Large prompt: skip to prevent error
    echo "Warning: System prompt too large ($PROMPT_SIZE bytes) for Claude < 2.0.34" >&2
    echo "Skipping prompt to prevent 'Argument list too long' error" >&2
    echo "Solutions: 1) Upgrade to Claude v2.0.34+, 2) Reduce prompt to <4KB" >&2
    exec claude "$@" --settings "$SETTINGS_WIN"
  fi
fi
'''
            else:
                # No system prompt, only settings
                shared_sh_content = f'''#!/usr/bin/env bash
set -euo pipefail

# Get Windows path for settings
SETTINGS_WIN="$(cygpath -m "$HOME/.claude/{command_name}-additional-settings.json" 2>/dev/null ||
  echo "$HOME/.claude/{command_name}-additional-settings.json")"

exec claude "$@" --settings "$SETTINGS_WIN"
'''
            shared_sh.write_text(shared_sh_content, newline='\n')
            # Make it executable for bash
            with contextlib.suppress(Exception):
                shared_sh.chmod(0o755)

        else:
            # Create bash launcher for Unix-like systems
            launcher_path = launcher_path.with_suffix('.sh')

            if system_prompt_file:
                # Load prompt file first (common for both modes)
                launcher_content = f'''#!/usr/bin/env bash
# Claude Code Environment Launcher
# This script starts Claude Code with the configured environment

CLAUDE_USER_DIR="$HOME/.claude"
SETTINGS_PATH="$CLAUDE_USER_DIR/{command_name}-additional-settings.json"
PROMPT_PATH="$CLAUDE_USER_DIR/prompts/{system_prompt_file}"

if [ ! -f "$PROMPT_PATH" ]; then
    echo -e "\\033[0;31mError: System prompt not found at $PROMPT_PATH\\033[0m"
    echo -e "\\033[1;33mPlease run setup_environment.py first\\033[0m"
    exit 1
fi

# Version detection function
get_claude_version() {{
  claude --version 2>/dev/null | grep -oP '\\d+\\.\\d+\\.\\d+' | head -1
}}

# Version comparison function (checks if version1 >= version2)
version_ge() {{
  local version1="$1"
  local version2="$2"

  # If version detection failed, return false (fallback to safe defaults)
  if [ -z "$version1" ]; then
    return 1
  fi

  # Try using sort -V if available (most reliable)
  if command -v sort >/dev/null 2>&1 && echo | sort -V >/dev/null 2>&1; then
    [ "$(printf '%s\\n' "$version1" "$version2" | sort -V | tail -n1)" = "$version1" ]
  else
    # Manual comparison fallback
    local IFS='.'
    local i ver1=($version1) ver2=($version2)
    # Fill empty positions with zeros
    for ((i=0; i<3; i++)); do
      ver1[i]=${{ver1[i]:-0}}
      ver2[i]=${{ver2[i]:-0}}
    done
    # Compare each component
    for ((i=0; i<3; i++)); do
      if ((10#${{ver1[i]}} > 10#${{ver2[i]}})); then
        return 0
      elif ((10#${{ver1[i]}} < 10#${{ver2[i]}})); then
        return 1
      fi
    done
    return 0
  fi
}}

# Detect Claude Code version
CLAUDE_VERSION=$(get_claude_version)

# File size detection function (cross-platform)
get_file_size() {{
  local file="$1"
  # Try GNU/Linux syntax
  if stat -c %s "$file" 2>/dev/null; then
    return 0
  # Try BSD/macOS syntax
  elif stat -f %z "$file" 2>/dev/null; then
    return 0
  # Universal fallback
  else
    wc -c < "$file" | tr -d ' '
  fi
}}

# Safe prompt size threshold (4KB)
SAFE_PROMPT_SIZE=4096

'''
                # Add mode-specific logic
                if mode == 'replace':
                    # Replace mode: Check for continuation flags and use appropriate flag
                    launcher_content += f'''# Replace mode: Check for continuation flags
HAS_CONTINUE=false
for arg in "$@"; do
  if [[ "$arg" == "--continue" || "$arg" == "-c" || "$arg" == "--resume" || "$arg" == "-r" ]]; then
    HAS_CONTINUE=true
    break
  fi
done

# For v2.0.64+: bug #11641 is fixed, --system-prompt works correctly with --continue/--resume
if version_ge "$CLAUDE_VERSION" "2.0.64"; then
  if [ "$HAS_CONTINUE" = true ]; then
    echo -e "\\033[0;32mResuming Claude Code session with {command_name} configuration...\\033[0m"
  else
    echo -e "\\033[0;32mStarting Claude Code with {command_name} configuration...\\033[0m"
  fi
  # Fixed in v2.0.64: always use --system-prompt-file (no need for workaround)
  claude --system-prompt-file "$PROMPT_PATH" "$@" --settings "$SETTINGS_PATH"
elif [ "$HAS_CONTINUE" = true ]; then
  echo -e "\\033[0;32mResuming Claude Code session with {command_name} configuration...\\033[0m"
  # Legacy workaround for v < 2.0.64: use --append-system-prompt for continuation
  # Continuation: use --append-system-prompt-file if available (v2.0.34+)
  if version_ge "$CLAUDE_VERSION" "2.0.34"; then
    claude --append-system-prompt-file "$PROMPT_PATH" "$@" --settings "$SETTINGS_PATH"
  else
    # For Claude < 2.0.34: check prompt size to avoid "Argument list too long"
    PROMPT_SIZE=$(get_file_size "$PROMPT_PATH")
    if [ "$PROMPT_SIZE" -lt "$SAFE_PROMPT_SIZE" ]; then
      # Small prompt: safe to use content-based flag
      PROMPT_CONTENT=$(cat "$PROMPT_PATH")
      claude --append-system-prompt "$PROMPT_CONTENT" "$@" --settings "$SETTINGS_PATH"
    else
      # Large prompt: skip to prevent error
      echo "Warning: System prompt too large ($PROMPT_SIZE bytes) for Claude < 2.0.34" >&2
      echo "Skipping prompt to prevent 'Argument list too long' error" >&2
      echo "Solutions: 1) Upgrade to Claude v2.0.34+, 2) Reduce prompt to <4KB" >&2
      claude "$@" --settings "$SETTINGS_PATH"
    fi
  fi
else
  echo -e "\\033[0;32mStarting Claude Code with {command_name} configuration...\\033[0m"
  # New session: use --system-prompt-file (available in v2.0.14+)
  if version_ge "$CLAUDE_VERSION" "2.0.14"; then
    claude --system-prompt-file "$PROMPT_PATH" "$@" --settings "$SETTINGS_PATH"
  else
    # Fallback to content-based flag for very old versions
    PROMPT_CONTENT=$(cat "$PROMPT_PATH")
    claude --system-prompt "$PROMPT_CONTENT" "$@" --settings "$SETTINGS_PATH"
  fi
fi
'''
                else:  # mode == 'append'
                    # Append mode: use --append-system-prompt-file if available
                    launcher_content += f'''# Append mode: use --append-system-prompt-file if available (v2.0.34+)
echo -e "\\033[0;32mStarting Claude Code with {command_name} configuration...\\033[0m"
if version_ge "$CLAUDE_VERSION" "2.0.34"; then
  claude --append-system-prompt-file "$PROMPT_PATH" "$@" --settings "$SETTINGS_PATH"
else
  # For Claude < 2.0.34: check prompt size to avoid "Argument list too long"
  PROMPT_SIZE=$(get_file_size "$PROMPT_PATH")
  if [ "$PROMPT_SIZE" -lt "$SAFE_PROMPT_SIZE" ]; then
    # Small prompt: safe to use content-based flag
    PROMPT_CONTENT=$(cat "$PROMPT_PATH")
    claude --append-system-prompt "$PROMPT_CONTENT" "$@" --settings "$SETTINGS_PATH"
  else
    # Large prompt: skip to prevent error
    echo "Warning: System prompt too large ($PROMPT_SIZE bytes) for Claude < 2.0.34" >&2
    echo "Skipping prompt to prevent 'Argument list too long' error" >&2
    echo "Solutions: 1) Upgrade to Claude v2.0.34+, 2) Reduce prompt to <4KB" >&2
    claude "$@" --settings "$SETTINGS_PATH"
  fi
fi
'''
            else:
                launcher_content = f'''#!/usr/bin/env bash
# Claude Code Environment Launcher
# This script starts Claude Code with the configured environment

CLAUDE_USER_DIR="$HOME/.claude"
SETTINGS_PATH="$CLAUDE_USER_DIR/{command_name}-additional-settings.json"

echo -e "\\033[0;32mStarting Claude Code with {command_name} configuration...\\033[0m"

# Pass any additional arguments to Claude
claude "$@" --settings "$SETTINGS_PATH"
'''
            launcher_path.write_text(launcher_content)
            launcher_path.chmod(0o755)

        success('Created launcher script')
        return launcher_path

    except Exception as e:
        warning(f'Failed to create launcher script: {e}')
        return None


def register_global_command(
    launcher_path: Path,
    command_name: str,
    additional_names: list[str] | None = None,
) -> bool:
    """Register global command(s).

    Args:
        launcher_path: Path to the launcher script.
        command_name: Primary command name (used for file naming).
        additional_names: Optional list of additional command names (aliases).

    Returns:
        True if registration succeeded, False otherwise.
    """
    info(f'Registering global {command_name} command...')

    system = platform.system()

    try:
        if system == 'Windows':
            # Create batch file in .local/bin
            local_bin = Path.home() / '.local' / 'bin'
            local_bin.mkdir(parents=True, exist_ok=True)

            # Create wrappers for all Windows shells
            # CMD wrapper
            batch_path = local_bin / f'{command_name}.cmd'
            batch_content = f'''@echo off
REM Global {command_name} command for CMD
set "BASH_EXE=C:\\Program Files\\Git\\bin\\bash.exe"
if not exist "%BASH_EXE%" set "BASH_EXE=C:\\Program Files (x86)\\Git\\bin\\bash.exe"
set "SCRIPT_WIN=%USERPROFILE%\\.claude\\launch-{command_name}.sh"
if "%~1"=="" (
    "%BASH_EXE%" --login "%SCRIPT_WIN%"
) else (
    "%BASH_EXE%" --login "%SCRIPT_WIN%" %*
)
'''
            batch_path.write_text(batch_content)

            # PowerShell wrapper (as a simple forwarder to the PS1 launcher)
            ps1_wrapper_path = local_bin / f'{command_name}.ps1'
            ps1_wrapper_content = f'''# Global {command_name} command for PowerShell
& "{launcher_path}" @args
'''
            ps1_wrapper_path.write_text(ps1_wrapper_content)

            # Git Bash wrapper - simply call the shared launch script
            bash_wrapper_path = local_bin / command_name
            bash_content = f'''#!/bin/bash
# Bash wrapper for {command_name} to work in Git Bash

# Call the shared launch script
exec "$HOME/.claude/launch-{command_name}.sh" "$@"
'''
            bash_wrapper_path.write_text(bash_content, newline='\n')  # Use Unix line endings
            # Make it executable (Git Bash respects this even on Windows)
            bash_wrapper_path.chmod(0o755)

            info('Created wrappers for all Windows shells (PowerShell, CMD, Git Bash)')

            # Create additional command wrappers for aliases (Windows)
            if additional_names:
                for alias_name in additional_names:
                    # CMD wrapper for alias
                    alias_batch_path = local_bin / f'{alias_name}.cmd'
                    alias_batch_content = f'''@echo off
REM Global {alias_name} command for CMD (alias for {command_name})
set "BASH_EXE=C:\\Program Files\\Git\\bin\\bash.exe"
if not exist "%BASH_EXE%" set "BASH_EXE=C:\\Program Files (x86)\\Git\\bin\\bash.exe"
set "SCRIPT_WIN=%USERPROFILE%\\.claude\\launch-{command_name}.sh"
if "%~1"=="" (
    "%BASH_EXE%" --login "%SCRIPT_WIN%"
) else (
    "%BASH_EXE%" --login "%SCRIPT_WIN%" %*
)
'''
                    alias_batch_path.write_text(alias_batch_content)

                    # PowerShell wrapper for alias
                    alias_ps1_path = local_bin / f'{alias_name}.ps1'
                    alias_ps1_content = f'''# Global {alias_name} command for PowerShell (alias for {command_name})
& "{launcher_path}" @args
'''
                    alias_ps1_path.write_text(alias_ps1_content)

                    # Git Bash wrapper for alias
                    alias_bash_path = local_bin / alias_name
                    alias_bash_content = f'''#!/bin/bash
# Bash wrapper for {alias_name} (alias for {command_name})
exec "$HOME/.claude/launch-{command_name}.sh" "$@"
'''
                    alias_bash_path.write_text(alias_bash_content, newline='\n')
                    alias_bash_path.chmod(0o755)

                info(f'Created {len(additional_names)} alias command(s): {", ".join(additional_names)}')

            # Add .local/bin to PATH using the robust registry-based function
            local_bin_str = str(local_bin)
            path_success, path_message = add_directory_to_windows_path(local_bin_str)

            if path_success:
                if 'already in PATH' in path_message:
                    info(path_message)
                else:
                    success(path_message)
                    info('You may need to restart your terminal for PATH changes to take effect')
            else:
                warning(f'Failed to add directory to PATH: {path_message}')
                info('')
                info('To manually add to PATH:')
                info('1. Open System Properties > Environment Variables')
                info('2. Edit the User PATH variable')
                info(f'3. Add: {local_bin_str}')
                info('4. Click OK and restart your terminal')

        else:
            # Create symlink in ~/.local/bin
            local_bin = Path.home() / '.local' / 'bin'
            local_bin.mkdir(parents=True, exist_ok=True)

            symlink_path = local_bin / command_name
            if symlink_path.exists():
                symlink_path.unlink()
            symlink_path.symlink_to(launcher_path)

            # Create additional symlinks for aliases (Linux/macOS)
            if additional_names:
                for alias_name in additional_names:
                    alias_symlink_path = local_bin / alias_name
                    if alias_symlink_path.exists():
                        alias_symlink_path.unlink()
                    alias_symlink_path.symlink_to(launcher_path)

                info(f'Created {len(additional_names)} alias symlink(s): {", ".join(additional_names)}')

            # Ensure ~/.local/bin is in PATH
            info('Make sure ~/.local/bin is in your PATH')
            info('Add this to your ~/.bashrc or ~/.zshrc if needed:')
            info('  export PATH="$HOME/.local/bin:$PATH"')

        if system == 'Windows':
            if additional_names:
                all_names = [command_name, *additional_names]
                success(f'Created global commands: {", ".join(all_names)} (works in PowerShell, CMD, and Git Bash)')
            else:
                success(f'Created global command: {command_name} (works in PowerShell, CMD, and Git Bash)')
            info('The command now works in all Windows shells!')
        else:
            if additional_names:
                all_names = [command_name, *additional_names]
                success(f'Created global commands: {", ".join(all_names)}')
            else:
                success(f'Created global command: {command_name}')
        return True

    except Exception as e:
        warning(f'Failed to register global command: {e}')
        return False


def restore_env_vars_from_args() -> tuple[list[str], bool]:
    """Restore environment variables from command-line arguments.

    When running elevated on Windows, environment variables are not inherited.
    This function restores them from special --env-* arguments.

    Returns:
        Tuple of (remaining arguments after removing --env-* and special flags,
                  whether --elevated-via-uac flag was present).
    """
    remaining_args: list[str] = []
    was_elevated_via_uac = False

    # Debug logging to track what we're processing
    if '--debug-elevation' in sys.argv:
        print(f'[DEBUG] Original sys.argv: {sys.argv}')
        print(f'[DEBUG] Running as admin: {is_admin()}')

    # sys.argv[0] is always the script path, keep it
    remaining_args.append(sys.argv[0])

    # Process the rest of the arguments
    i = 1  # Start from index 1 to skip script path
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == '--debug-elevation':
            # Skip debug flag
            i += 1
            continue
        if arg == '--elevated-via-uac':
            # Track that we were elevated via UAC (new window was opened)
            was_elevated_via_uac = True
            i += 1
            continue
        if arg.startswith('--env-'):
            # Parse --env-VAR_NAME=value format
            if '=' in arg:
                var_part = arg[6:]  # Remove '--env-' prefix
                var_name, var_value = var_part.split('=', 1)

                # No unescaping needed - values are passed as-is

                os.environ[var_name] = var_value

                if '--debug-elevation' in sys.argv:
                    if len(var_value) > 50:
                        print(f'[DEBUG] Restored env var: {var_name}={var_value[:50]}...')
                    else:
                        print(f'[DEBUG] Restored env var: {var_name}={var_value}')
            i += 1
        else:
            remaining_args.append(arg)
            i += 1

    if '--debug-elevation' in sys.argv:
        print(f'[DEBUG] Cleaned sys.argv: {remaining_args}')
        print(f"[DEBUG] CLAUDE_ENV_CONFIG: {os.environ.get('CLAUDE_ENV_CONFIG', 'NOT SET')}")
        print(f'[DEBUG] Was elevated via UAC: {was_elevated_via_uac}')

    return remaining_args, was_elevated_via_uac


def main() -> None:
    """Main setup flow."""
    # Track if we were elevated via UAC (new window opened) for better UX
    was_elevated_via_uac = False

    # Restore environment variables if running elevated on Windows
    if platform.system() == 'Windows' and is_admin():
        # Replace sys.argv with cleaned arguments (without --env-* args)
        # and check if we were elevated via UAC
        original_argv = sys.argv.copy()
        sys.argv, was_elevated_via_uac = restore_env_vars_from_args()

        # Debug output to understand what's happening in elevated process
        if '--debug-elevation' in original_argv:
            print('[DEBUG] Elevated process started successfully')
            print(f'[DEBUG] Admin status: {is_admin()}')
            print(f"[DEBUG] Config from env: {os.environ.get('CLAUDE_ENV_CONFIG', 'NOT SET')}")
            print(f'[DEBUG] Was elevated via UAC: {was_elevated_via_uac}')

        # Show that we're running elevated (only if via UAC)
        if was_elevated_via_uac:
            print()
            print(f'{Colors.GREEN}========================================================================{Colors.NC}')
            print(f'{Colors.GREEN}     Running with Administrator Privileges{Colors.NC}')
            print(f'{Colors.GREEN}========================================================================{Colors.NC}')
            print()

    parser = argparse.ArgumentParser(description='Setup development environment for Claude Code')
    parser.add_argument('config', nargs='?', help='Configuration file name (e.g., python.yaml)')
    parser.add_argument('--skip-install', action='store_true', help='Skip Claude Code installation')
    parser.add_argument('--auth', type=str, help='Authentication for private repos (e.g., "token" or "header:token")')
    parser.add_argument('--no-admin', action='store_true', help='Do not request admin elevation even if needed')
    args = parser.parse_args()

    # Get configuration from args or environment
    config_name = args.config or os.environ.get('CLAUDE_ENV_CONFIG')

    if not config_name:
        error('No configuration specified!')
        info('Usage: setup_environment.py <config_name>')
        info('   or: CLAUDE_ENV_CONFIG=<config_name> setup_environment.py')
        info('Example: setup_environment.py python')
        sys.exit(1)

    # Clean up any temporary directory paths from Windows PATH registry
    # This must run early to remove pollution from previous script executions
    if platform.system() == 'Windows':
        removed_count, removed_paths = cleanup_temp_paths_from_registry()
        if removed_count > 0:
            print()
            print(f'{Colors.YELLOW}========================================================================{Colors.NC}')
            print(f'{Colors.YELLOW}     PATH Cleanup{Colors.NC}')
            print(f'{Colors.YELLOW}========================================================================{Colors.NC}')
            print()
            success(f'Removed {removed_count} temporary directory path(s) from Windows PATH')
            for path in removed_paths:
                info(f'  Removed: {path}')
            print()

    try:
        # Load configuration from source (URL, local file, or repository)
        config, config_source = load_config_from_source(config_name, args.auth)

        # Resolve configuration inheritance if present
        if INHERIT_KEY in config:
            info('Configuration uses inheritance, resolving parent configs...')
            config = resolve_config_inheritance(config, config_source, auth_param=args.auth)
            success('Configuration inheritance resolved successfully')

        # Check if admin rights are needed for this configuration
        if platform.system() == 'Windows' and not args.no_admin and check_admin_needed(config, args) and not is_admin():
            print()
            print(f'{Colors.YELLOW}========================================================================{Colors.NC}')
            print(f'{Colors.YELLOW}     Administrator Privileges Required{Colors.NC}')
            print(f'{Colors.YELLOW}========================================================================{Colors.NC}')
            print()
            info('This configuration requires administrator privileges for:')

            if not args.skip_install:
                info('  - Installing Claude Code (includes Node.js and Git)')

            # Check dependencies
            dependencies = config.get('dependencies', {})
            if dependencies:
                win_deps = dependencies.get('windows', [])
                common_deps = dependencies.get('common', [])
                all_deps = win_deps + common_deps

                for dep in all_deps:
                    if 'winget' in dep and '--scope machine' in dep:
                        info(f'  - System-wide installation: {dep}')
                    elif 'npm install -g' in dep:
                        info(f'  - Global npm package: {dep}')

            print()
            info('Requesting administrator elevation...')
            info('A new window will open with administrator privileges.')
            info('Please look for the UAC dialog and click "Yes" to continue.')
            print()
            request_admin_elevation()
            # If we reach here, elevation was denied
            error('Administrator elevation was denied')
            error('Please run this script as administrator manually:')
            error('  1. Right-click on your terminal')
            error('  2. Select "Run as administrator"')
            error('  3. Run the setup command again')
            error('')
            error('Alternatively, use --no-admin flag to skip elevation')
            sys.exit(1)

        environment_name = config.get('name', 'Development')

        # Extract command-names (new format, array)
        command_names_raw = config.get('command-names')

        # Handle deprecated command-name (singular)
        command_name_deprecated = config.get('command-name')

        # Normalize to list and handle deprecation
        command_names: list[str] | None = None
        if command_names_raw is not None:
            # New format: ensure it's a list
            if isinstance(command_names_raw, str):
                command_names = [command_names_raw]
            elif isinstance(command_names_raw, list):
                # Convert all items to strings (handles mixed types from YAML)
                command_names = [str(item) for item in cast(list[object], command_names_raw)]
            else:
                error(f'Invalid command-names value: expected string or list, got {type(command_names_raw).__name__}')
                sys.exit(1)
            if command_name_deprecated is not None:
                warning('Both "command-names" and deprecated "command-name" specified. Using "command-names".')
        elif command_name_deprecated is not None:
            # DEPRECATED: Convert singular to list
            warning('Config key "command-name" is deprecated. Use "command-names" (array) instead.')
            command_names = [str(command_name_deprecated)]

        # Validate command names
        if command_names:
            for cmd_name in command_names:
                if not cmd_name.strip():
                    error('Invalid command name: empty or whitespace-only name')
                    sys.exit(1)
                if ' ' in cmd_name:
                    error(f'Invalid command name: "{cmd_name}" contains spaces')
                    sys.exit(1)

        # Get primary command name (first in list) for file naming
        primary_command_name = command_names[0] if command_names else None
        additional_command_names = command_names[1:] if command_names and len(command_names) > 1 else None

        base_url = config.get('base-url')  # Optional base URL override from config

        # Extract command defaults
        command_defaults = config.get('command-defaults', {})
        system_prompt = command_defaults.get('system-prompt')
        mode = command_defaults.get('mode', 'replace')  # Default to 'replace'

        # Validate mode value
        if mode not in ['append', 'replace']:
            error(f"Invalid mode value: {mode}. Must be 'append' or 'replace'")
            sys.exit(1)

        # Extract model configuration
        model = config.get('model')

        # Extract permissions configuration
        permissions = config.get('permissions')

        # Extract environment variables configuration
        env_variables = config.get('env-variables')

        # Extract OS-level environment variables configuration
        os_env_variables = config.get('os-env-variables')

        # Extract include_co_authored_by configuration
        include_co_authored_by = config.get('include-co-authored-by')

        # Extract always_thinking_enabled configuration
        always_thinking_enabled = config.get('always-thinking-enabled')

        # Extract company_announcements configuration
        company_announcements = config.get('company-announcements')

        # Extract attribution configuration (new format, takes precedence over include-co-authored-by)
        attribution = config.get('attribution')

        # Extract status_line configuration
        status_line = config.get('status-line')

        # Extract claude-code-version configuration
        claude_code_version = config.get('claude-code-version')
        claude_code_version_normalized = None  # Default to latest

        if claude_code_version is not None:
            # Convert to string to handle YAML numeric values (e.g., 1.0 becomes "1.0")
            claude_code_version_str = str(claude_code_version).strip()

            # Handle empty strings
            if not claude_code_version_str:
                warning('Empty claude-code-version value, using latest')
                claude_code_version_normalized = None
            # Handle "latest" value (case-insensitive)
            elif claude_code_version_str.lower() == 'latest':
                info(f'Claude Code version specified: {claude_code_version} (will install latest available)')
                claude_code_version_normalized = None
            # Specific version specified
            else:
                info(f'Claude Code version specified: {claude_code_version_str}')
                claude_code_version_normalized = claude_code_version_str

        header(environment_name)

        # Validate all downloadable files before proceeding
        print()
        print(f'{Colors.CYAN}Validating configuration files...{Colors.NC}')
        all_valid, validation_results = validate_all_config_files(config, config_source, args.auth)

        if not all_valid:
            print()
            error('Configuration validation failed!')
            error('The following files are not accessible:')
            for file_type, path, is_valid, _method in validation_results:
                if not is_valid:
                    error(f'  - {file_type}: {path}')
            print()
            error('Please check:')
            error('  1. The URLs are correct')
            error('  2. The files exist at the specified locations')
            error('  3. You have necessary permissions (authentication tokens)')
            error('  4. Network connectivity to the sources')
            sys.exit(1)
        else:
            success('All configuration files validated successfully!')

        # Set up directories
        home = Path.home()
        claude_user_dir = home / '.claude'
        agents_dir = claude_user_dir / 'agents'
        commands_dir = claude_user_dir / 'commands'
        prompts_dir = claude_user_dir / 'prompts'
        hooks_dir = claude_user_dir / 'hooks'
        skills_dir = claude_user_dir / 'skills'

        # Step 1: Install Claude Code if needed (MUST be first - provides uv, git bash, node)
        if not args.skip_install:
            print(f'{Colors.CYAN}Step 1: Installing Claude Code...{Colors.NC}')
            if not install_claude(claude_code_version_normalized):
                raise Exception('Claude Code installation failed')
        else:
            print(f'{Colors.CYAN}Step 1: Skipping Claude Code installation (already installed){Colors.NC}')

            # Verify Claude Code is available
            if not find_command_robust('claude'):
                error('Claude Code is not available in PATH')
                info('Please install Claude Code first or remove the --skip-install flag')
                raise Exception('Claude Code not found')

        # Step 2: Create directories
        print()
        print(f'{Colors.CYAN}Step 2: Creating configuration directories...{Colors.NC}')
        for dir_path in [claude_user_dir, agents_dir, commands_dir, prompts_dir, hooks_dir, skills_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
            success(f'Created: {dir_path}')

        # Ensure .local/bin is in PATH early to prevent uv tool warnings
        ensure_local_bin_in_path()

        # Step 3: Download/copy custom files
        print()
        print(f'{Colors.CYAN}Step 3: Processing file downloads...{Colors.NC}')
        files_to_download = config.get('files-to-download', [])
        if files_to_download:
            process_file_downloads(files_to_download, config_source, base_url, args.auth)
        else:
            info('No custom files to download')

        # Step 4: Install Node.js if requested (before dependencies)
        print()
        print(f'{Colors.CYAN}Step 4: Checking Node.js installation...{Colors.NC}')
        if not install_nodejs_if_requested(config):
            raise Exception('Node.js installation failed')

        # Step 5: Install dependencies (after Claude Code which provides tools)
        print()
        print(f'{Colors.CYAN}Step 5: Installing dependencies...{Colors.NC}')
        dependencies = config.get('dependencies', {})
        install_dependencies(dependencies)

        # Step 6: Set OS environment variables
        print()
        print(f'{Colors.CYAN}Step 6: Setting OS environment variables...{Colors.NC}')
        if os_env_variables:
            set_all_os_env_variables(os_env_variables)
        else:
            info('No OS environment variables to configure')

        # Step 7: Process agents
        print()
        print(f'{Colors.CYAN}Step 7: Processing agents...{Colors.NC}')
        agents = config.get('agents', [])
        process_resources(agents, agents_dir, 'agents', config_source, base_url, args.auth)

        # Step 8: Process slash commands
        print()
        print(f'{Colors.CYAN}Step 8: Processing slash commands...{Colors.NC}')
        commands = config.get('slash-commands', [])
        process_resources(commands, commands_dir, 'slash commands', config_source, base_url, args.auth)

        # Step 9: Process skills
        print()
        print(f'{Colors.CYAN}Step 9: Processing skills...{Colors.NC}')
        skills_raw = config.get('skills', [])
        # Convert to properly typed list using cast and list comprehension
        skills: list[dict[str, Any]] = (
            [cast(dict[str, Any], s) for s in cast(list[object], skills_raw) if isinstance(s, dict)]
            if isinstance(skills_raw, list)
            else []
        )
        process_skills(skills, skills_dir, config_source, args.auth)

        # Step 10: Process system prompt (if specified)
        print()
        print(f'{Colors.CYAN}Step 10: Processing system prompt...{Colors.NC}')
        prompt_path = None
        if system_prompt:
            # Strip query parameters from URL to get clean filename
            clean_prompt = system_prompt.split('?')[0] if '?' in system_prompt else system_prompt
            sys_prompt_filename = Path(clean_prompt).name
            prompt_path = prompts_dir / sys_prompt_filename
            handle_resource(system_prompt, prompt_path, config_source, base_url, args.auth)
        else:
            info('No additional system prompt configured')

        # Step 11: Configure MCP servers
        print()
        print(f'{Colors.CYAN}Step 11: Configuring MCP servers...{Colors.NC}')
        mcp_servers_raw = config.get('mcp-servers', [])
        # Convert to properly typed list for type safety
        mcp_servers: list[dict[str, Any]] = (
            [cast(dict[str, Any], s) for s in cast(list[object], mcp_servers_raw) if isinstance(s, dict)]
            if isinstance(mcp_servers_raw, list)
            else []
        )

        # Refresh PATH from registry to pick up any installation changes
        if platform.system() == 'Windows':
            refresh_path_from_registry()

        # Check if any MCP server needs Node.js (npx-based stdio transport)
        # HTTP/SSE transport servers do NOT require Node.js
        needs_nodejs = any(
            'npx' in str(server.get('command', ''))
            for server in mcp_servers
            if server.get('command')
        )

        if needs_nodejs and platform.system() == 'Windows' and not verify_nodejs_available():
            warning('Node.js not available - npx-based MCP servers may fail')
            warning('Please ensure Node.js is installed and in PATH')
            # Don't fail hard, let user see the issue

        configure_all_mcp_servers(mcp_servers)

        # Check if command creation is needed
        if primary_command_name:
            # Step 12: Download hooks
            print()
            print(f'{Colors.CYAN}Step 12: Downloading hooks...{Colors.NC}')
            hooks = config.get('hooks', {})
            download_hook_files(hooks, claude_user_dir, config_source, base_url, args.auth)

            # Step 13: Configure settings
            print()
            print(f'{Colors.CYAN}Step 13: Configuring settings...{Colors.NC}')
            # Cast status_line for type safety
            status_line_arg: dict[str, Any] | None = None
            if status_line is not None and isinstance(status_line, dict):
                status_line_arg = cast(dict[str, Any], status_line)

            create_additional_settings(
                hooks,
                claude_user_dir,
                primary_command_name,
                model,
                permissions,
                env_variables,
                include_co_authored_by,
                always_thinking_enabled,
                company_announcements,
                attribution,
                status_line_arg,
            )

            # Step 14: Create launcher script
            print()
            print(f'{Colors.CYAN}Step 14: Creating launcher script...{Colors.NC}')
            # Strip query parameters from system prompt filename (must match download logic)
            prompt_filename: str | None = None
            if system_prompt:
                clean_prompt = system_prompt.split('?')[0] if '?' in system_prompt else system_prompt
                prompt_filename = Path(clean_prompt).name
            launcher_path = create_launcher_script(claude_user_dir, primary_command_name, prompt_filename, mode)

            # Step 15: Register global command(s)
            if launcher_path:
                print()
                if additional_command_names:
                    all_names = ', '.join(command_names) if command_names else primary_command_name
                    print(f'{Colors.CYAN}Step 15: Registering global commands: {all_names}...{Colors.NC}')
                else:
                    print(f'{Colors.CYAN}Step 15: Registering global {primary_command_name} command...{Colors.NC}')
                register_global_command(launcher_path, primary_command_name, additional_command_names)
            else:
                warning('Launcher script was not created')
        else:
            # Skip command creation
            print()
            print(f'{Colors.CYAN}Steps 12-15: Skipping command creation (no command-names specified)...{Colors.NC}')
            info('Environment configuration completed successfully')
            info('To create custom commands, add "command-names: [name1, name2]" to your config')

        # Final message
        print()
        print(f'{Colors.GREEN}========================================================================{Colors.NC}')
        print(f'{Colors.GREEN}                    Setup Complete!{Colors.NC}')
        print(f'{Colors.GREEN}========================================================================{Colors.NC}')
        print()

        print(f'{Colors.YELLOW}Summary:{Colors.NC}')
        print(f'   * Environment: {environment_name}')
        print(f"   * Claude Code installation: {'Skipped' if args.skip_install else 'Completed'}")
        print(f'   * Agents: {len(agents)} installed')
        print(f'   * Slash commands: {len(commands)} installed')
        print(f'   * Skills: {len(skills)} installed')
        if files_to_download:
            print(f'   * Files downloaded: {len(files_to_download)} processed')
        if system_prompt:
            if mode == 'append':
                print('   * System prompt: appending to default')
            else:  # mode == 'replace'
                print('   * System prompt: replacing default')
        if model:
            print(f'   * Model: {model}')
        print(f'   * MCP servers: {len(mcp_servers)} configured')
        if permissions:
            perm_items: list[str] = []
            if 'defaultMode' in permissions:
                perm_items.append(f"defaultMode={permissions['defaultMode']}")
            if 'allow' in permissions:
                perm_items.append(f"{len(permissions['allow'])} allow rules")
            if 'deny' in permissions:
                perm_items.append(f"{len(permissions['deny'])} deny rules")
            if 'ask' in permissions:
                perm_items.append(f"{len(permissions['ask'])} ask rules")
            if perm_items:
                print(f"   * Permissions: {', '.join(perm_items)}")
        if env_variables:
            print(f'   * Environment variables: {len(env_variables)} configured')
        if company_announcements:
            print(f'   * Company announcements: {len(company_announcements)} configured')
        if status_line and isinstance(status_line, dict):
            status_line_dict = cast(dict[str, Any], status_line)
            status_line_file_val = status_line_dict.get('file', '')
            if status_line_file_val and isinstance(status_line_file_val, str):
                if '?' in status_line_file_val:
                    clean_name = Path(status_line_file_val.split('?')[0]).name
                else:
                    clean_name = Path(status_line_file_val).name
                print(f'   * Status line: {clean_name}')
        if os_env_variables:
            set_vars = sum(1 for v in os_env_variables.values() if v is not None)
            del_vars = sum(1 for v in os_env_variables.values() if v is None)
            if set_vars > 0:
                print(f'   * OS environment variables: {set_vars} configured')
            if del_vars > 0:
                print(f'   * OS environment variables: {del_vars} deleted')
        # Only show hooks count if command was specified (hooks was defined)
        if command_names:
            hooks = config.get('hooks', {})
            print(f"   * Hooks: {len(hooks.get('events', [])) if hooks else 0} configured")
            if len(command_names) > 1:
                print(f'   * Global commands: {", ".join(command_names)} registered')
            else:
                print(f'   * Global command: {primary_command_name} registered')
        else:
            print('   * Custom command: Not created (no command-names specified)')

        print()
        print(f'{Colors.YELLOW}Quick Start:{Colors.NC}')
        if command_names:
            if len(command_names) > 1:
                print(f'   * Global commands: {", ".join(command_names)}')
            else:
                print(f'   * Global command: {primary_command_name}')
        else:
            print('   * Use "claude" to start Claude Code with configured environment')

        print()
        print(f'{Colors.YELLOW}Available Commands (after starting Claude):{Colors.NC}')
        print('   * /help - See all available commands')
        print('   * /agents - Manage subagents')
        print('   * /hooks - Manage hooks')
        print('   * /mcp - Manage MCP servers')
        print('   * /skills - Manage skills')
        print('   * /<slash-command> - Run specific slash command')

        print()
        print(f'{Colors.YELLOW}Examples:{Colors.NC}')
        print(f'   {primary_command_name or "claude"}')
        print(f'   > Start working with {environment_name} environment')

        print()
        print(f'{Colors.YELLOW}Documentation:{Colors.NC}')
        print('   * Setup Guide: https://github.com/alex-feel/claude-code-toolbox')
        print('   * Claude Code Docs: https://code.claude.com/docs')
        print()

        # If running elevated via UAC, add a pause so user can see the results
        if was_elevated_via_uac and not is_running_in_pytest():
            print()
            print(f'{Colors.GREEN}========================================================================{Colors.NC}')
            print(f'{Colors.GREEN}     Setup Completed Successfully!{Colors.NC}')
            print(f'{Colors.GREEN}========================================================================{Colors.NC}')
            print()
            print(f'{Colors.YELLOW}The environment has been configured successfully.{Colors.NC}')
            print(f'{Colors.YELLOW}You can now close this window and use the configured environment.{Colors.NC}')
            print()
            input('Press Enter to exit...')

    except Exception as e:
        print()
        error(str(e))
        print()
        print(f'{Colors.RED}Setup failed. Please check the error above.{Colors.NC}')
        print(f'{Colors.YELLOW}For help, visit: https://github.com/alex-feel/claude-code-toolbox{Colors.NC}')
        print()

        # If running elevated via UAC, add a pause so user can see the error
        if was_elevated_via_uac and not is_running_in_pytest():
            print()
            print(f'{Colors.RED}========================================================================{Colors.NC}')
            print(f'{Colors.RED}     Setup Failed{Colors.NC}')
            print(f'{Colors.RED}========================================================================{Colors.NC}')
            print()
            input('Press Enter to exit...')

        sys.exit(1)


if __name__ == '__main__':
    main()
