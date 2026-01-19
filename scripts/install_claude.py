"""
Cross-platform Claude Code installer.
Handles Git Bash (Windows), Node.js, and Claude Code CLI installation.
"""

import contextlib
import json
import os
import platform
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.request import urlopen
from urllib.request import urlretrieve


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


# Configuration
MIN_NODE_VERSION = '18.0.0'
NODE_LTS_API = 'https://nodejs.org/dist/index.json'
GIT_WINDOWS_URL = 'https://git-scm.com/downloads/win'
GIT_GITHUB_API = 'https://api.github.com/repos/git-for-windows/git/releases/latest'
CLAUDE_NPM_PACKAGE = '@anthropic-ai/claude-code'
CLAUDE_INSTALLER_URL = 'https://claude.ai/install.ps1'


# Logging functions
def info(msg: str) -> None:
    """Print info message."""
    print(f'{Colors.CYAN}[INFO]{Colors.NC} {msg}')


def success(msg: str) -> None:
    """Print success message."""
    print(f'{Colors.GREEN}[OK]{Colors.NC} {msg}')


def warning(msg: str) -> None:
    """Print warning message."""
    print(f'{Colors.YELLOW}[WARN]{Colors.NC} {msg}')


def error(msg: str) -> None:
    """Print error message."""
    print(f'{Colors.RED}[FAIL]{Colors.NC} {msg}', file=sys.stderr)


def banner() -> None:
    """Print installation banner."""
    os_name = platform.system()
    print()
    print(f'{Colors.CYAN}============================================{Colors.NC}')
    print(f'{Colors.CYAN}  Claude Code {os_name} Installer{Colors.NC}')
    print(f'{Colors.CYAN}============================================{Colors.NC}')
    print()


def run_command(cmd: list[str], capture_output: bool = True, **kwargs: Any) -> subprocess.CompletedProcess[str]:
    """Run a command and return the result with robust encoding handling.

    Uses UTF-8 encoding with 'replace' error handling to prevent UnicodeDecodeError
    on Windows when subprocess output contains characters not in the system codepage.

    Returns:
        subprocess.CompletedProcess[str]: The completed process result with decoded output.
    """
    try:
        # Debug: print command being run if not capturing output
        if not capture_output:
            info(f"Executing: {', '.join(cmd)}")
        return subprocess.run(
            cmd,
            capture_output=capture_output,
            encoding='utf-8',
            errors='replace',
            **kwargs,
        )
    except FileNotFoundError as e:
        error(f'Command not found: {cmd[0]} - {e}')
        return subprocess.CompletedProcess(cmd, 1, '', f'Command not found: {cmd[0]}')
    except Exception as e:
        error(f'Error running command {cmd[0]}: {e}')
        return subprocess.CompletedProcess(cmd, 1, '', str(e))


def is_admin() -> bool:
    """Check if running with admin/sudo privileges."""
    if platform.system() == 'Windows':
        try:
            import ctypes

            # Use getattr to handle platform-specific attributes
            windll = getattr(ctypes, 'windll', None)
            if windll is not None:
                return bool(windll.shell32.IsUserAnAdmin())
            return False
        except Exception:
            return False
    else:
        # Only available on Unix-like systems
        try:
            # Use getattr to safely access geteuid (Unix-only)
            geteuid = getattr(os, 'geteuid', None)
            if geteuid is not None:
                return bool(geteuid() == 0)
            return False
        except Exception:
            return False


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
    import time

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
                r'C:\Program Files\nodejs\node.exe',
                r'C:\Program Files (x86)\nodejs\node.exe',
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
        if Path(expanded).exists():
            return str(Path(expanded).resolve())

    # Tertiary: Custom fallback paths
    if fallback_paths:
        for path in fallback_paths:
            expanded = os.path.expandvars(path)
            if Path(expanded).exists():
                return str(Path(expanded).resolve())

    return None


def verify_claude_installation() -> tuple[bool, str | None, str]:
    """Verify Claude installation with source detection and explicit file existence checks.

    This function performs robust verification by checking actual file existence,
    not just PATH availability. It distinguishes between different installation sources
    to prevent false positives when native installer fails but npm installation exists.

    Returns:
        Tuple of (is_installed, path, source) where:
        - is_installed: True if Claude exists and is accessible
        - path: Full path to Claude executable (or None if not found)
        - source: Installation source ('native', 'npm', 'winget', 'unknown', 'none')

    Note:
        Minimum file size check (1KB) ensures the file is not empty or corrupted.
    """
    result: tuple[bool, str | None, str]

    if sys.platform == 'win32':
        # Check native installer location first
        native_path = Path.home() / '.local' / 'bin' / 'claude.exe'
        if native_path.exists() and native_path.stat().st_size > 1000:
            result = (True, str(native_path), 'native')
        else:
            # Check npm global installation locations
            npm_cmd = Path(os.path.expandvars(r'%APPDATA%\npm\claude.cmd'))
            if npm_cmd.exists():
                result = (True, str(npm_cmd), 'npm')
            else:
                npm_exe = Path(os.path.expandvars(r'%APPDATA%\npm\claude'))
                if npm_exe.exists():
                    result = (True, str(npm_exe), 'npm')
                else:
                    # Check winget installation location
                    winget_path = Path(os.path.expandvars(r'%LOCALAPPDATA%\Programs\claude\claude.exe'))
                    if winget_path.exists() and winget_path.stat().st_size > 1000:
                        result = (True, str(winget_path), 'winget')
                    else:
                        # Fallback to PATH search (with source detection)
                        claude_path = find_command_robust('claude')
                        if claude_path:
                            source = 'unknown'
                            claude_lower = claude_path.lower()
                            if 'npm' in claude_lower or 'roaming' in claude_lower:
                                source = 'npm'
                            elif '.local\\bin' in claude_lower:
                                source = 'native'
                            elif 'programs\\claude' in claude_lower:
                                source = 'winget'
                            result = (True, claude_path, source)
                        else:
                            result = (False, None, 'none')
    else:
        # Non-Windows platforms
        claude_path = find_command_robust('claude')
        if claude_path:
            if 'npm' in claude_path or '.npm-global' in claude_path:
                result = (True, claude_path, 'npm')
            else:
                result = (True, claude_path, 'unknown')
        else:
            result = (False, None, 'none')

    return result


def parse_version(version_str: str) -> tuple[int, int, int] | None:
    """Parse version string to tuple."""
    match = re.match(r'v?(\d+)\.(\d+)\.(\d+)', version_str)
    if match:
        # Explicitly return as a 3-element tuple for type checker
        major = int(match.group(1))
        minor = int(match.group(2))
        patch = int(match.group(3))
        return (major, minor, patch)
    return None


def compare_versions(current: str, required: str) -> bool:
    """Check if current version meets required version."""
    current_tuple = parse_version(current)
    required_tuple = parse_version(required)
    if not current_tuple or not required_tuple:
        return False
    return current_tuple >= required_tuple


# Windows-specific functions
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
    # Check CLAUDE_CODE_GIT_BASH_PATH env var first
    env_path = os.environ.get('CLAUDE_CODE_GIT_BASH_PATH')
    if env_path and Path(env_path).exists():
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

    for path in common_paths:
        expanded = os.path.expandvars(path)
        if Path(expanded).exists():
            return str(Path(expanded).resolve())

    # Fall back to PATH search (may find Git Bash if installed elsewhere)
    bash_path = find_command('bash.exe')
    if bash_path:
        # Skip WSL bash in System32/SysWOW64
        bash_lower = bash_path.lower()
        if 'system32' not in bash_lower and 'syswow64' not in bash_lower:
            return bash_path
        # WSL bash found - don't use it, return None instead

    return None


def check_winget() -> bool:
    """Check if winget is available on Windows."""
    return find_command('winget') is not None


def install_git_windows_winget(scope: str = 'user') -> bool:
    """Install Git for Windows using winget."""
    if not check_winget():
        return False

    info(f'Installing Git for Windows via winget, scope: {scope}')
    result = run_command([
        'winget',
        'install',
        '--id',
        'Git.Git',
        '-e',
        '--source',
        'winget',
        '--accept-package-agreements',
        '--accept-source-agreements',
        '--silent',
        '--disable-interactivity',
        '--scope',
        scope,
    ])

    if result.returncode == 0:
        success('Git for Windows installed via winget')
        return True
    warning(f'winget exited with code {result.returncode}')
    return False


def check_github_rate_limit() -> dict[str, int] | None:
    """Check current GitHub API rate limit status.

    Uses GITHUB_TOKEN environment variable for authentication if available.
    Provides diagnostic information about remaining API quota.

    Returns:
        Dict with 'limit', 'remaining', 'reset' (Unix timestamp) keys,
        or None on error.
    """
    try:
        github_token = os.environ.get('GITHUB_TOKEN')
        request = urllib.request.Request('https://api.github.com/rate_limit')
        request.add_header('User-Agent', 'claude-code-toolbox-installer')
        if github_token:
            request.add_header('Authorization', f'Bearer {github_token}')

        with urlopen(request) as response:
            data = json.loads(response.read())
            core = data.get('resources', {}).get('core', {})
            return {
                'limit': core.get('limit', 0),
                'remaining': core.get('remaining', 0),
                'reset': core.get('reset', 0),
            }
    except Exception:
        return None


def get_git_installer_url_from_github() -> str | None:
    """Get Git for Windows installer URL from GitHub releases API.

    Uses the official git-for-windows GitHub repository to find the latest
    64-bit Windows installer. Uses GITHUB_TOKEN environment variable for
    authentication if available, increasing rate limit from 60/hour to 5000/hour.

    Returns:
        Direct download URL for Git-{version}-64-bit.exe, or None if unavailable.
        Returns None on any error for graceful fallback to other download methods.
    """
    try:
        # Build request with optional authentication
        request = urllib.request.Request(GIT_GITHUB_API)
        request.add_header('User-Agent', 'claude-code-toolbox-installer')

        # Use GITHUB_TOKEN if available for higher rate limits
        github_token = os.environ.get('GITHUB_TOKEN')
        if github_token:
            request.add_header('Authorization', f'Bearer {github_token}')
            request.add_header('X-GitHub-Api-Version', '2022-11-28')

        # Fetch GitHub releases API (with SSL fallback pattern)
        try:
            with urlopen(request) as response:
                data = json.loads(response.read())
        except urllib.error.URLError as e:
            if 'SSL' in str(e) or 'certificate' in str(e).lower():
                warning('SSL certificate verification failed, trying with unverified context')
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with urlopen(request, context=ctx) as response:
                    data = json.loads(response.read())
            else:
                # Non-SSL error, return None for fallback
                warning(f'Error fetching Git installer from GitHub API: {e}')
                return None

        # Find 64-bit installer in assets
        for asset in data.get('assets', []):
            name = asset.get('name', '')
            if name.endswith('-64-bit.exe') and 'Git-' in name:
                download_url = asset.get('browser_download_url')
                if download_url and isinstance(download_url, str):
                    return str(download_url)

        warning('No 64-bit installer found in GitHub release assets')
        return None

    except Exception as e:
        warning(f'Error fetching Git installer from GitHub API: {e}')
        return None


def get_git_installer_with_retry(max_retries: int = 3) -> str | None:
    """Get Git installer URL with retry logic for rate limiting.

    Implements exponential backoff as recommended by GitHub API documentation.
    Checks rate limit headers and Retry-After for optimal retry timing.

    Args:
        max_retries: Maximum number of retry attempts (default: 3).

    Returns:
        Git installer URL or None if all attempts fail.
    """
    for attempt in range(max_retries):
        try:
            # Build request with optional authentication
            request = urllib.request.Request(GIT_GITHUB_API)
            request.add_header('User-Agent', 'claude-code-toolbox-installer')

            # Use GITHUB_TOKEN if available for higher rate limits
            github_token = os.environ.get('GITHUB_TOKEN')
            if github_token:
                request.add_header('Authorization', f'Bearer {github_token}')
                request.add_header('X-GitHub-Api-Version', '2022-11-28')

            with urlopen(request) as response:
                data = json.loads(response.read())

            # Find 64-bit installer in assets
            for asset in data.get('assets', []):
                name = asset.get('name', '')
                if name.endswith('-64-bit.exe') and 'Git-' in name:
                    download_url = asset.get('browser_download_url')
                    if download_url and isinstance(download_url, str):
                        return str(download_url)

            warning('No 64-bit installer found in GitHub release assets')
            return None

        except urllib.error.HTTPError as e:
            if e.code == 403:
                # Check if it's rate limiting
                retry_after = e.headers.get('retry-after')
                reset_time = e.headers.get('x-ratelimit-reset')

                if retry_after:
                    wait_time = int(retry_after)
                elif reset_time:
                    wait_time = max(0, int(reset_time) - int(time.time()))
                else:
                    # Exponential backoff: 1, 2, 4 seconds
                    wait_time = 2**attempt

                if attempt < max_retries - 1:
                    # Cap wait time at 60 seconds
                    wait_time = min(wait_time, 60)
                    info(f'Rate limited, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})')
                    time.sleep(wait_time)
                    continue

                # Final attempt failed
                warning(f'GitHub API rate limit exceeded after {max_retries} attempts')
                return None

            # Non-rate-limit HTTP error
            warning(f'HTTP error {e.code}: {e.reason}')
            return None

        except urllib.error.URLError as e:
            if 'SSL' in str(e) or 'certificate' in str(e).lower():
                # SSL errors - try fallback without retry
                warning('SSL certificate verification failed')
                return get_git_installer_url_from_github()

            warning(f'Network error: {e}')
            if attempt < max_retries - 1:
                wait_time = 2**attempt
                info(f'Retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})')
                time.sleep(wait_time)
                continue
            return None

        except Exception as e:
            warning(f'Error fetching Git installer: {e}')
            return None

    return None


def install_git_windows_download() -> bool:
    """Install Git for Windows by direct download.

    Tries multiple download sources in order:
    1. GitHub API with retry and GITHUB_TOKEN authentication (primary method)
    2. git-scm.com scraping (legacy fallback)

    Uses GITHUB_TOKEN environment variable for authentication if available,
    which increases rate limit from 60/hour to 5000/hour.

    Returns:
        True if installation succeeded, False otherwise.

    Raises:
        urllib.error.URLError: Network errors (caught internally, returns False).
        Exception: General errors during download/install (caught internally, returns False).

    Note:
        All exceptions are caught and handled internally - this function never
        propagates exceptions to callers.
    """
    try:
        installer_url = None

        # Method 1: GitHub API with retry logic and authentication
        info('Attempting to download Git via GitHub API...')
        github_token = os.environ.get('GITHUB_TOKEN')
        if github_token:
            info('Using GITHUB_TOKEN for authenticated GitHub API access')
        installer_url = get_git_installer_with_retry()

        if not installer_url:
            # Method 2: Legacy scraping (existing code as fallback)
            info('GitHub API unavailable, trying git-scm.com download page...')

            # Get the download page (with SSL fallback) - EXISTING CODE
            try:
                with urlopen(GIT_WINDOWS_URL) as response:
                    html = response.read().decode('utf-8')
            except urllib.error.URLError as e:
                if 'SSL' in str(e) or 'certificate' in str(e).lower():
                    warning('SSL certificate verification failed, trying with unverified context')
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    with urlopen(GIT_WINDOWS_URL, context=ctx) as response:
                        html = response.read().decode('utf-8')
                else:
                    raise

            # Find the installer link - EXISTING CODE
            match = re.search(r'href="([^"]+Git-[\d.]+-64-bit\.exe)"', html)
            if match:
                installer_url = match.group(1)
                if not installer_url.startswith('http'):
                    installer_url = f'https://github.com{installer_url}'

        if not installer_url:
            raise Exception('Could not find Git installer from any source')

        # Download and install - EXISTING CODE
        with tempfile.NamedTemporaryFile(suffix='.exe', delete=False) as tmp:
            temp_path = tmp.name

        info(f'Downloading {installer_url}')
        try:
            urlretrieve(installer_url, temp_path)
        except urllib.error.URLError as e:
            if 'SSL' in str(e) or 'certificate' in str(e).lower():
                warning('SSL certificate verification failed, trying with unverified context')
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
                urllib.request.install_opener(opener)
                urlretrieve(installer_url, temp_path)
            else:
                raise

        # Run installer silently - EXISTING CODE
        info('Running Git installer silently...')
        result = run_command([
            temp_path,
            '/VERYSILENT',
            '/NORESTART',
            '/NOCANCEL',
            '/SP-',
            '/CLOSEAPPLICATIONS',
            '/RESTARTAPPLICATIONS',
            '/COMPONENTS="icons,ext\\reg\\shellhere,assoc,assoc_sh"',
        ])

        # Clean up
        with contextlib.suppress(Exception):
            os.unlink(temp_path)

        if result.returncode == 0:
            success('Git for Windows installed via direct download')
            return True
        error(f'Git installer exited with code {result.returncode}')
        return False

    except Exception as e:
        error(f'Failed to install Git by download: {e}')

        # Check if this might be a rate limit issue and provide helpful info
        if 'rate limit' in str(e).lower() or '403' in str(e):
            rate_limit = check_github_rate_limit()
            if rate_limit:
                if rate_limit['remaining'] == 0:
                    reset_time = time.strftime('%H:%M:%S', time.localtime(rate_limit['reset']))
                    error(f'GitHub API rate limit exhausted (resets at {reset_time})')
                else:
                    info(f'GitHub API rate limit: {rate_limit["remaining"]}/{rate_limit["limit"]} remaining')

            if not os.environ.get('GITHUB_TOKEN'):
                info('Tip: Set GITHUB_TOKEN environment variable for higher rate limits (5000/hour vs 60/hour)')

        error('This may be a network issue or service unavailability')
        info('Manual installation options:')
        info('  1. Install winget: https://learn.microsoft.com/windows/package-manager/winget/')
        info('  2. Download Git manually: https://gitforwindows.org/')
        info('  3. Set CLAUDE_CODE_GIT_BASH_PATH to existing Git installation')
        return False


def ensure_git_bash_windows() -> str | None:
    """Ensure Git Bash is installed on Windows."""
    bash_path = find_bash_windows()
    if bash_path:
        success(f'Git Bash found at: {bash_path}')
        return bash_path

    info('Git Bash not found, installing...')

    # Check winget availability
    winget_available = check_winget()
    if not winget_available:
        info('winget is not available, using direct download method')

    # Try user-scope winget install first
    if winget_available and install_git_windows_winget('user'):
        time.sleep(2)
        bash_path = find_bash_windows()
        if bash_path:
            success(f'Git Bash installed for current user: {bash_path}')
            return bash_path

    # Try machine-scope (requires admin)
    if not is_admin():
        warning('Machine-wide installation requires administrator privileges')
        info('Please run this installer as administrator for machine-wide installation')
    else:
        if winget_available and install_git_windows_winget('machine'):
            time.sleep(2)
            bash_path = find_bash_windows()
            if bash_path:
                success(f'Git Bash installed machine-wide: {bash_path}')
                return bash_path

    # Last resort: direct download
    if install_git_windows_download():
        time.sleep(2)
        bash_path = find_bash_windows()
        if bash_path:
            success(f'Git Bash installed via direct download: {bash_path}')
            return bash_path

    error('Could not install or detect Git Bash')
    return None


def set_windows_env_var(name: str, value: str) -> None:
    """Set Windows environment variable."""
    try:
        # Set for current process
        os.environ[name] = value

        # Set persistently for user
        if platform.system() == 'Windows':
            run_command(
                [
                    'setx',
                    name,
                    value,
                ],
                capture_output=False,
            )
            success(f'Set environment variable: {name}')
    except Exception as e:
        warning(f'Could not set environment variable {name}: {e}')


def set_disable_autoupdater() -> None:
    """Set DISABLE_AUTOUPDATER environment variable to prevent auto-updates."""
    info('Setting DISABLE_AUTOUPDATER environment variable to prevent auto-updates...')

    if platform.system() == 'Windows':
        set_windows_env_var('DISABLE_AUTOUPDATER', '1')
    else:
        # For Unix-like systems, add to shell profile files
        home = Path.home()
        env_line = '\n# Disable Claude Code auto-updates\nexport DISABLE_AUTOUPDATER=1\n'

        # List of shell profile files to update
        profile_files = [
            home / '.bashrc',
            home / '.zshrc',
            home / '.profile',
        ]

        updated_files: list[Path] = []
        for profile_file in profile_files:
            if profile_file.exists():
                try:
                    content = profile_file.read_text()
                    if 'DISABLE_AUTOUPDATER' not in content:
                        profile_file.write_text(content + env_line)
                        updated_files.append(profile_file)
                except Exception as e:
                    warning(f'Could not update {profile_file}: {e}')

        if updated_files:
            success(f"Added DISABLE_AUTOUPDATER to: {', '.join(str(f) for f in updated_files)}")
            info('Please restart your shell or run: export DISABLE_AUTOUPDATER=1')
        else:
            warning('No shell profile files were updated')


def configure_powershell_policy() -> None:
    """Configure PowerShell execution policy for npm scripts.

    This function checks the current PowerShell execution policy before attempting
    to set it. If the policy is already RemoteSigned or less restrictive, no action
    is needed. This prevents unnecessary warnings in environments where the policy
    is already configured or restricted by Group Policy.

    Note: PowerShell execution policy primarily affects .ps1 scripts. NPM global
    commands use .cmd files which bypass PowerShell restrictions, so Claude will
    work correctly even if this configuration fails.
    """
    if platform.system() == 'Windows':
        info('Checking PowerShell execution policy...')

        # Check current execution policy
        check_result = run_command([
            'powershell',
            '-Command',
            'Get-ExecutionPolicy -Scope CurrentUser',
        ])

        if check_result.returncode == 0:
            current_policy = check_result.stdout.strip()

            # Only set if not already RemoteSigned or less restrictive
            # Policy hierarchy (least to most restrictive): Bypass < Unrestricted < RemoteSigned < AllSigned < Restricted
            if current_policy in ['RemoteSigned', 'Unrestricted', 'Bypass']:
                success(f'PowerShell execution policy already configured ({current_policy})')
                return

        info('Configuring PowerShell execution policy...')

        # Try to set for current user
        result = run_command([
            'powershell',
            '-Command',
            'Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force',
        ])

        if result.returncode == 0:
            success('PowerShell execution policy configured for current user')
        else:
            # Improved warning message with actionable guidance
            warning('Could not set PowerShell execution policy (may be restricted by Group Policy)')
            info('This warning can be safely ignored - Claude will still work correctly')
            info('NPM global commands use .cmd files which bypass PowerShell restrictions')


# Node.js functions
def get_node_version() -> str | None:
    """Get installed Node.js version."""
    node_path = find_command('node')
    if not node_path:
        return None

    result = run_command([node_path, '--version'])
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def check_nodejs_compatibility() -> bool:
    """Check if Node.js version is compatible with Claude Code.

    Node.js v25+ removed the SlowBuffer API that Claude Code depends on,
    causing TypeError when running MCP servers and other operations.

    Returns:
        True if Node.js version is compatible, False otherwise.
    """
    node_version = get_node_version()
    if not node_version:
        return False

    version_match = re.match(r'v?(\d+)\.(\d+)\.(\d+)', node_version)
    if not version_match:
        return False

    major = int(version_match.group(1))

    # Node.js v25+ is incompatible due to SlowBuffer removal (DEP0030)
    if major >= 25:
        error(f'Node.js {node_version} is incompatible with Claude Code')
        error('Node.js v25+ removed the SlowBuffer API that Claude Code depends on')
        info('Please downgrade to Node.js v22 or v20 (LTS)')
        if platform.system() == 'Darwin':
            info('On Mac: brew uninstall node && brew install node@22 && brew link --force --overwrite node@22')
        elif platform.system() == 'Linux':
            info('On Linux: Use nvm or n to install Node.js 22')
            info('  nvm install 22 && nvm use 22')
        elif platform.system() == 'Windows':
            info('On Windows: Download Node.js 22 from https://nodejs.org/')
        return False

    if major < 18:
        error(f'Node.js {node_version} is too old (minimum v18 required)')
        return False

    return True


def install_nodejs_winget(scope: str = 'user') -> bool:
    """Install Node.js using winget on Windows."""
    if not check_winget():
        return False

    info(f'Installing Node.js LTS via winget, scope: {scope}')
    result = run_command([
        'winget',
        'install',
        '--id',
        'OpenJS.NodeJS.LTS',
        '-e',
        '--source',
        'winget',
        '--accept-package-agreements',
        '--accept-source-agreements',
        '--silent',
        '--disable-interactivity',
        '--scope',
        scope,
    ])

    if result.returncode == 0:
        success('Node.js LTS installed via winget')
        return True
    warning(f'winget exited with code {result.returncode}')
    return False


def install_nodejs_direct() -> bool:
    """Install Node.js by direct download."""
    try:
        info('Downloading Node.js LTS installer...')

        # Get LTS version info (with SSL fallback)
        try:
            with urlopen(NODE_LTS_API) as response:
                versions = json.loads(response.read())
        except urllib.error.URLError as e:
            if 'SSL' in str(e) or 'certificate' in str(e).lower():
                warning('SSL certificate verification failed, trying with unverified context')
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with urlopen(NODE_LTS_API, context=ctx) as response:
                    versions = json.loads(response.read())
            else:
                raise

        lts_version = None
        for v in versions:
            if v.get('lts'):
                lts_version = v['version']
                break

        if not lts_version:
            raise Exception('Could not determine LTS version')

        # Determine installer URL based on OS
        system = platform.system()
        machine = platform.machine().lower()

        if system == 'Windows':
            ext = 'msi'
            arch = 'x64' if machine in ['amd64', 'x86_64'] else 'x86'
            installer_url = f'https://nodejs.org/dist/{lts_version}/node-{lts_version}-{arch}.{ext}'
        elif system == 'Darwin':  # macOS
            arch = 'arm64' if machine == 'arm64' else 'x64'
            ext = 'pkg'
            installer_url = f'https://nodejs.org/dist/{lts_version}/node-{lts_version}-darwin-{arch}.{ext}'
        else:  # Linux
            arch = 'x64' if machine in ['amd64', 'x86_64'] else 'armv7l'
            ext = 'tar.xz'
            installer_url = f'https://nodejs.org/dist/{lts_version}/node-{lts_version}-linux-{arch}.{ext}'

        # Download installer
        with tempfile.NamedTemporaryFile(suffix=f'.{ext}', delete=False) as tmp:
            temp_path = tmp.name

        info(f'Downloading {installer_url}')
        try:
            urlretrieve(installer_url, temp_path)
        except urllib.error.URLError as e:
            if 'SSL' in str(e) or 'certificate' in str(e).lower():
                warning('SSL certificate verification failed, trying with unverified context')
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
                urllib.request.install_opener(opener)
                urlretrieve(installer_url, temp_path)
            else:
                raise

        # Install based on OS
        if system == 'Windows':
            # Create log directory for MSI installation
            log_dir = Path(tempfile.gettempdir()) / 'claude-installer-logs'
            log_dir.mkdir(exist_ok=True)
            log_file = log_dir / f'nodejs-install-{int(time.time())}.log'

            info('Installing Node.js silently...')

            # Enhanced MSI command with verbose logging for truly silent installation
            result = run_command([
                'msiexec',
                '/i',
                temp_path,
                '/qn',  # No UI (truly silent installation)
                '/norestart',  # Don't restart automatically
                '/l*v',
                str(log_file),  # Verbose logging for diagnostics
                # Node.js MSI installs to C:\Program Files\nodejs by default
            ])

            # After MSI installation, add Node.js to PATH for current process
            if result.returncode == 0:
                nodejs_path = r'C:\Program Files\nodejs'
                if Path(nodejs_path).exists():
                    current_path = os.environ.get('PATH', '')
                    if nodejs_path not in current_path:
                        os.environ['PATH'] = f'{nodejs_path};{current_path}'
                        info(f'Added {nodejs_path} to PATH for current session')
            else:
                # Provide diagnostic information for MSI failures
                error(f'Node.js installer exited with code {result.returncode}')

                if log_file.exists():
                    warning(f'Installation log available at: {log_file}')
                    # Read last 50 lines of log for immediate diagnostics
                    try:
                        # MSI logs are typically UTF-16 LE encoded
                        log_content = log_file.read_text(encoding='utf-16-le', errors='ignore')
                        lines = log_content.splitlines()
                        if lines:
                            error_context = '\n'.join(lines[-50:])
                            info('Last 50 lines of installation log:')
                            print(error_context)
                    except Exception as e:
                        warning(f'Could not read log file: {e}')

                # Provide troubleshooting suggestions
                info('Troubleshooting steps:')
                info('1. Check if Node.js is already partially installed')
                info('2. Remove Node.js from Control Panel if present')
                info('3. Clear Node.js entries from registry (regedit)')
                info('4. Remove Node.js from PATH environment variable')
                info('5. Rerun installer as Administrator')

                # Return early to maintain existing flow
                return False
        elif system == 'Darwin':
            info('Installing Node.js (may require password)...')
            result = run_command(['sudo', 'installer', '-pkg', temp_path, '-target', '/'])
        else:
            error('Direct Linux installation not yet implemented - use package manager')
            return False

        # Clean up
        with contextlib.suppress(Exception):
            os.unlink(temp_path)

        if result.returncode == 0:
            success('Node.js installed via direct download')
            return True
        error(f'Node.js installer exited with code {result.returncode}')
        return False

    except Exception as e:
        error(f'Failed to install Node.js by download: {e}')
        return False


def install_nodejs_homebrew() -> bool:
    """Install Node.js using Homebrew on macOS."""
    if not find_command('brew'):
        info('Installing Homebrew first...')
        result = run_command([
            '/bin/bash',
            '-c',
            '$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)',
        ])
        if result.returncode != 0:
            return False

    info('Installing Node.js LTS using Homebrew...')
    run_command(['brew', 'update'])
    result = run_command(['brew', 'install', 'node'])

    if result.returncode == 0:
        success('Node.js installed via Homebrew')
        return True
    return False


def install_nodejs_apt() -> bool:
    """Install Node.js using apt on Debian/Ubuntu."""
    info('Installing Node.js LTS for Debian/Ubuntu...')

    # Update and install prerequisites
    run_command(['sudo', 'apt-get', 'update'])
    run_command(['sudo', 'apt-get', 'install', '-y', 'ca-certificates', 'curl', 'gnupg'])

    # Add NodeSource repository
    result = run_command([
        'bash',
        '-c',
        'curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -',
    ])

    if result.returncode != 0:
        return False

    # Install Node.js
    result = run_command(['sudo', 'apt-get', 'install', '-y', 'nodejs'])

    if result.returncode == 0:
        success('Node.js installed via NodeSource')
        return True
    return False


def ensure_nodejs() -> bool:
    """Ensure Node.js is installed and meets minimum version."""
    info('Checking Node.js installation...')

    # On Windows, check standard installation location even if not in PATH
    if platform.system() == 'Windows':
        nodejs_path = r'C:\Program Files\nodejs'
        if Path(nodejs_path).exists():
            current_path = os.environ.get('PATH', '')
            if nodejs_path not in current_path:
                os.environ['PATH'] = f'{nodejs_path};{current_path}'
                info(f'Found Node.js at {nodejs_path}, adding to PATH')

    current_version = get_node_version()
    if current_version:
        info(f'Node.js {current_version} found')

        # Check for Node.js compatibility (v25+ incompatibility)
        if not check_nodejs_compatibility():
            error('Node.js version is incompatible with Claude Code')
            return False

        if compare_versions(current_version, MIN_NODE_VERSION):
            success(f'Node.js version meets minimum requirement (>= {MIN_NODE_VERSION})')
            return True
        warning(f'Node.js {current_version} is below minimum required version {MIN_NODE_VERSION}')
    else:
        info('Node.js not found')

    # Install Node.js based on OS
    system = platform.system()

    if system == 'Windows':
        # Try winget first
        if check_winget():
            if install_nodejs_winget('user'):
                time.sleep(2)
                # Update PATH after winget installation
                nodejs_path = r'C:\Program Files\nodejs'
                if Path(nodejs_path).exists():
                    current_path = os.environ.get('PATH', '')
                    if nodejs_path not in current_path:
                        os.environ['PATH'] = f'{nodejs_path};{current_path}'
                        info(f'Added {nodejs_path} to PATH after winget installation')

                node_version = get_node_version()
                if node_version and compare_versions(node_version, MIN_NODE_VERSION):
                    return True

            if is_admin() and install_nodejs_winget('machine'):
                time.sleep(2)
                # Update PATH after winget installation (machine scope)
                nodejs_path = r'C:\Program Files\nodejs'
                if Path(nodejs_path).exists():
                    current_path = os.environ.get('PATH', '')
                    if nodejs_path not in current_path:
                        os.environ['PATH'] = f'{nodejs_path};{current_path}'
                        info(f'Added {nodejs_path} to PATH after winget installation')

                node_version = get_node_version()
                if node_version and compare_versions(node_version, MIN_NODE_VERSION):
                    return True

        # Fallback to direct download
        if install_nodejs_direct():
            time.sleep(2)
            # After installation, check standard location on Windows
            if platform.system() == 'Windows':
                nodejs_path = r'C:\Program Files\nodejs'
                if Path(nodejs_path).exists():
                    current_path = os.environ.get('PATH', '')
                    if nodejs_path not in current_path:
                        os.environ['PATH'] = f'{nodejs_path};{current_path}'
                        info(f'Added {nodejs_path} to PATH after installation')

            version = get_node_version()
            if version and compare_versions(version, MIN_NODE_VERSION):
                return True

    elif system == 'Darwin':
        # Try Homebrew first
        if install_nodejs_homebrew():
            node_version = get_node_version()
            if node_version and compare_versions(node_version, MIN_NODE_VERSION):
                return True

        # Fallback to direct download
        if install_nodejs_direct():
            time.sleep(2)
            node_version = get_node_version()
            if node_version and compare_versions(node_version, MIN_NODE_VERSION):
                return True

    else:  # Linux
        # Detect distro and use package manager
        if Path('/etc/debian_version').exists() and install_nodejs_apt():
            node_version = get_node_version()
            if node_version and compare_versions(node_version, MIN_NODE_VERSION):
                return True
        warning('Unsupported Linux distribution - please install Node.js manually')
        return False

    error(f'Could not install Node.js >= {MIN_NODE_VERSION}')
    return False


# Claude Code installation
def get_claude_version() -> str | None:
    """Get installed Claude Code version."""
    claude_path = find_command_robust('claude')
    if not claude_path:
        return None

    result = run_command([claude_path, '--version'])
    if result.returncode == 0:
        # Parse version from output like "claude, version 0.7.7" or "@anthropic-ai/claude-code/0.7.7"
        output = result.stdout.strip()
        # Try to extract version number
        match = re.search(r'(\d+\.\d+\.\d+)', output)
        if match:
            return match.group(1)
        return output  # Return full string if can't parse
    return None


def get_latest_claude_version() -> str | None:
    """Get the latest available Claude Code version from npm.

    Returns:
        Latest version string (e.g., "1.0.135") or None if cannot determine.
    """
    npm_path = find_command_robust('npm')
    if not npm_path:
        return None

    # Query npm for latest version
    cmd = [npm_path, 'view', f'{CLAUDE_NPM_PACKAGE}@latest', 'version']
    result = run_command(cmd, capture_output=True)

    if result.returncode == 0:
        version = result.stdout.strip()
        # Remove quotes if present
        return version.strip("\"'")
    return None


def needs_sudo_for_npm() -> bool:
    """Check if npm global directory requires sudo on Unix-like systems.

    Returns:
        True if sudo is needed for npm global installation, False otherwise.
    """
    if platform.system() == 'Windows':
        return False

    npm_path = find_command('npm')
    if not npm_path:
        return False

    # Get npm global installation directory
    result = run_command([npm_path, 'config', 'get', 'prefix'], capture_output=True)
    if result.returncode == 0:
        prefix_path = Path(result.stdout.strip()) / 'lib' / 'node_modules'
        # Check if we have write access to the directory
        try:
            return not os.access(prefix_path, os.W_OK)
        except Exception:
            return False
    return False


def install_claude_npm(upgrade: bool = False, version: str | None = None) -> bool:
    """Install Claude Code using npm.

    Args:
        upgrade: Whether this is an upgrade operation.
        version: Specific version to install (e.g., "1.0.128"). If None, installs latest.

    Returns:
        True if installation succeeded, False otherwise.
    """
    # On Windows, check if npm is in Program Files even if not in PATH
    if platform.system() == 'Windows':
        nodejs_path = r'C:\Program Files\nodejs'
        if Path(nodejs_path).exists():
            current_path = os.environ.get('PATH', '')
            if nodejs_path not in current_path:
                os.environ['PATH'] = f'{nodejs_path};{current_path}'
                info(f'Added {nodejs_path} to PATH for npm access')

        # Also check for npm.cmd specifically on Windows
        npm_cmd = Path(nodejs_path) / 'npm.cmd'
        if npm_cmd.exists():
            info(f'Found npm.cmd at {npm_cmd}')

    npm_path = find_command_robust('npm')
    if not npm_path:
        # On Windows, try to find npm.cmd explicitly
        if platform.system() == 'Windows':
            npm_cmd_path = Path(r'C:\Program Files\nodejs\npm.cmd')
            if npm_cmd_path.exists():
                npm_path = str(npm_cmd_path)
                info(f'Using npm.cmd at {npm_path}')
            else:
                error('npm not found. Please install Node.js with npm')
                return False
        else:
            error('npm not found. Please install Node.js with npm')
            return False

    # Validate npm path before execution
    if npm_path:
        npm_path_obj = Path(npm_path)
        if not npm_path_obj.exists():
            error(f'npm executable not found at: {npm_path}')
            error('This usually indicates a PATH synchronization issue')
            return False

        # On Windows, ensure we're using the .cmd version
        if platform.system() == 'Windows' and not npm_path.lower().endswith('.cmd'):
            # Check if .cmd version exists
            npm_cmd_path_str = npm_path if npm_path.lower().endswith('.cmd') else npm_path + '.cmd'
            if Path(npm_cmd_path_str).exists():
                warning(f'Using {npm_cmd_path_str} instead of {npm_path}')
                npm_path = npm_cmd_path_str
            else:
                error(f'npm.cmd not found. Found non-executable: {npm_path}')
                error('This file cannot be executed directly on Windows')
                return False

        info(f'Validated npm executable: {npm_path}')

    action = 'Upgrading' if upgrade else 'Installing'

    # Determine version to install
    if version:
        package_spec = f'{CLAUDE_NPM_PACKAGE}@{version}'
        info(f'{action} Claude Code CLI version {version} via npm (npm path: {npm_path})...')

        # Check if specified version exists
        info(f'Verifying that version {version} exists...')
        check_cmd = [npm_path, 'view', f'{CLAUDE_NPM_PACKAGE}@{version}', 'version']
        check_result = run_command(check_cmd, capture_output=True)

        if check_result.returncode != 0:
            warning(f'Version {version} not found. Installing latest version instead.')
            package_spec = f'{CLAUDE_NPM_PACKAGE}@latest'
            version = None  # Reset version to indicate we're installing latest
    else:
        package_spec = f'{CLAUDE_NPM_PACKAGE}@latest'
        info(f'{action} Claude Code CLI (latest version) via npm (npm path: {npm_path})...')

    # Check if sudo will be needed on Unix-like systems
    will_need_sudo = platform.system() != 'Windows' and needs_sudo_for_npm()
    if will_need_sudo:
        info('Global npm directory requires elevated permissions')

    # Try without sudo first (show output for debugging)
    cmd = [npm_path, 'install', '-g', package_spec]
    info(f"Running command: {' '.join(cmd)}")
    result = run_command(cmd, capture_output=False)

    if result.returncode == 0:
        success(f"Claude Code {'upgraded' if upgrade else 'installed'} successfully")

        # If specific version was installed, set DISABLE_AUTOUPDATER
        if version:
            set_disable_autoupdater()

        return True

    # Try with sudo on Unix systems
    if platform.system() != 'Windows':
        warning('Trying with sudo...')
        result = run_command(['sudo', 'npm', 'install', '-g', package_spec], capture_output=False)
        if result.returncode == 0:
            success(f"Claude Code {'upgraded' if upgrade else 'installed'} successfully")

            # If specific version was installed, set DISABLE_AUTOUPDATER
            if version:
                set_disable_autoupdater()

            return True

    error(f"Failed to {'upgrade' if upgrade else 'install'} Claude Code via npm")
    return False


def install_claude_native_windows(version: str | None = None) -> bool:
    """Install Claude Code using native installer on Windows.

    Downloads and executes the official PowerShell installer script from claude.ai.
    The native installer places the executable at %USERPROFILE%\\.local\bin\\claude.exe
    and automatically updates the Windows PATH registry.

    Args:
        version: Specific version to install (e.g., "2.0.14", "latest", "stable").
                 If None, installs stable channel. Supports semantic versions
                 and pre-release tags (e.g., "2.0.0-beta").

    Returns:
        True if installation succeeded and was verified, False otherwise.

    Raises:
        urllib.error.URLError: Network errors (caught internally, returns False).

    Note:
        Windows only. Returns False on other platforms (should not be called).
    """
    if platform.system() != 'Windows':
        return False

    try:
        info('Trying official native installer...')

        # Download installer script (with SSL fallback)
        try:
            with urlopen(CLAUDE_INSTALLER_URL) as response:
                installer_script = response.read().decode('utf-8')
        except urllib.error.URLError as e:
            if 'SSL' in str(e) or 'certificate' in str(e).lower():
                # Fallback: create unverified SSL context for corporate environments
                warning('SSL certificate verification failed, trying with unverified context')
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with urlopen(CLAUDE_INSTALLER_URL, context=ctx) as response:
                    installer_script = response.read().decode('utf-8')
            else:
                raise

        # Save to temp file and execute
        with tempfile.NamedTemporaryFile(suffix='.ps1', delete=False, mode='w') as tmp:
            tmp.write(installer_script)
            temp_path = tmp.name

        # Build command with optional version parameter
        cmd = [
            'powershell',
            '-NoProfile',
            '-ExecutionPolicy',
            'Bypass',
            '-File',
            temp_path,
        ]

        # CRITICAL: Always pass version argument to bypass Anthropic installer bug
        # See: https://github.com/anthropics/claude-code/issues/14942
        # Bug: installer skips copying when running version == target version,
        # even if target file doesn't exist (fresh installations)
        # Fix: pass "latest" when no specific version requested
        version_arg = version or 'latest'
        cmd.append(version_arg)

        version_msg = f' version {version}' if version else ''
        info(f'Installing Claude Code{version_msg} via native installer...')
        result = run_command(cmd, capture_output=False)

        # Clean up
        with contextlib.suppress(Exception):
            os.unlink(temp_path)

        if result.returncode == 0:
            success('Claude Code installed via native installer')

            # CRITICAL: Ensure ~/.local/bin is in PATH after native installation
            info('Updating PATH for native installation...')
            ensure_local_bin_in_path_windows()

            # Give Windows time to process PATH update
            time.sleep(1)

            # Verify installation with source detection
            is_installed, claude_path, source = verify_claude_installation()
            if is_installed and source == 'native':
                success(f'Native installation verified at: {claude_path}')
                return True
            if is_installed:
                warning(f'Claude found but from {source} source at: {claude_path}')
                warning('Native installer did not create expected file at ~/.local/bin/claude.exe')
                error('Native installation failed - file not created at expected location')
                info('This indicates the native installer completed but did not install correctly')
                return False
            warning('Native installation failed - no Claude executable found')
            error('Claude not accessible after native installer execution')
            info('You may need to restart your terminal or run in a new session')
            return False

    except Exception as e:
        error(f'Native installer failed: {e}')

    return False


def install_claude_native_macos(version: str | None = None) -> bool:
    """Install Claude Code using native installer on macOS.

    Downloads and executes the official shell installer script from claude.ai.
    The native installer places the executable at /usr/local/bin/claude
    and handles PATH configuration automatically.

    Args:
        version: Specific version to install (e.g., "2.0.14"). If None,
                 installs latest stable version. Supports semantic versions
                 and pre-release tags.

    Returns:
        True if installation succeeded and was verified, False otherwise.

    Raises:
        urllib.error.URLError: Network errors (caught internally, returns False).

    Note:
        macOS only. Returns False on other platforms (should not be called).
    """
    if sys.platform == 'darwin':
        try:
            info('Trying official native installer for macOS...')

            # Download installer script (with SSL fallback)
            installer_url = 'https://claude.ai/install.sh'
            try:
                with urlopen(installer_url) as response:
                    installer_script = response.read().decode('utf-8')
            except urllib.error.URLError as e:
                if 'SSL' in str(e) or 'certificate' in str(e).lower():
                    warning('SSL certificate verification failed, trying with unverified context')
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    with urlopen(installer_url, context=ctx) as response:
                        installer_script = response.read().decode('utf-8')
                else:
                    raise

            # Save to temp file and execute
            with tempfile.NamedTemporaryFile(suffix='.sh', delete=False, mode='w') as tmp:
                tmp.write(installer_script)
                temp_path = tmp.name

            # Make executable
            os.chmod(temp_path, 0o755)

            # Execute installer with optional version argument
            cmd = ['bash', temp_path]
            if version:
                cmd.append(version)  # Shell script accepts version as $1

            version_msg = f' for version {version}' if version else ''
            info(f'Running native installer{version_msg} (may require password)...')
            result = run_command(cmd, capture_output=False)

            # Clean up
            with contextlib.suppress(Exception):
                os.unlink(temp_path)

            if result.returncode == 0:
                success('Claude Code installed via native installer')

                # Give system time to complete installation
                time.sleep(1)

                # Verify installation
                is_installed, claude_path, source = verify_claude_installation()
                if is_installed:
                    success(f'Native installation verified at: {claude_path} (source: {source})')
                    return True
                warning('Native installation completed but Claude executable not found')
                error('Installation verification failed')
                info('You may need to restart your terminal or run in a new session')
                return False

            error(f'Native installer exited with code {result.returncode}')
            return False

        except Exception as e:
            error(f'Native installer failed: {e}')
            return False
    return False


def install_claude_native_linux(version: str | None = None) -> bool:
    """Install Claude Code using native installer on Linux.

    Downloads and executes the official shell installer script from claude.ai.
    The native installer places the executable at /usr/local/bin/claude
    or ~/.local/bin/claude depending on permissions.

    Supports: Ubuntu 20.04+, Debian 10+, and other modern Linux distributions.

    Args:
        version: Specific version to install (e.g., "2.0.14"). If None,
                 installs latest stable version. Supports semantic versions.

    Returns:
        True if installation succeeded and was verified, False otherwise.

    Raises:
        urllib.error.URLError: Network errors (caught internally, returns False).

    Note:
        Linux only. Returns False on other platforms (should not be called).
    """
    if sys.platform == 'linux':
        try:
            info('Trying official native installer for Linux...')

            # Download installer script (with SSL fallback)
            installer_url = 'https://claude.ai/install.sh'
            try:
                with urlopen(installer_url) as response:
                    installer_script = response.read().decode('utf-8')
            except urllib.error.URLError as e:
                if 'SSL' in str(e) or 'certificate' in str(e).lower():
                    warning('SSL certificate verification failed, trying with unverified context')
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    with urlopen(installer_url, context=ctx) as response:
                        installer_script = response.read().decode('utf-8')
                else:
                    raise

            # Save to temp file and execute
            with tempfile.NamedTemporaryFile(suffix='.sh', delete=False, mode='w') as tmp:
                tmp.write(installer_script)
                temp_path = tmp.name

            # Make executable
            os.chmod(temp_path, 0o755)

            # Execute installer with optional version argument
            cmd = ['bash', temp_path]
            if version:
                cmd.append(version)  # Shell script accepts version as $1

            version_msg = f' for version {version}' if version else ''
            info(f'Running native installer{version_msg} (may require password)...')
            result = run_command(cmd, capture_output=False)

            # Clean up
            with contextlib.suppress(Exception):
                os.unlink(temp_path)

            if result.returncode == 0:
                success('Claude Code installed via native installer')

                # Give system time to complete installation
                time.sleep(1)

                # Verify installation
                is_installed, claude_path, source = verify_claude_installation()
                if is_installed:
                    success(f'Native installation verified at: {claude_path} (source: {source})')
                    return True
                warning('Native installation completed but Claude executable not found')
                error('Installation verification failed')
                info('You may need to restart your terminal or run in a new session')
                return False

            error(f'Native installer exited with code {result.returncode}')
            return False

        except Exception as e:
            error(f'Native installer failed: {e}')
            # Fall through to final return
    return False


def install_claude_native_cross_platform(version: str | None = None) -> bool:
    """Install Claude Code using native installer (cross-platform dispatcher).

    Dispatches to platform-specific native installation functions based on
    the current operating system. This is the unified entry point for native
    installation across all supported platforms.

    Supported platforms:
        - Windows: Uses PowerShell installer script
        - macOS: Uses shell installer script
        - Linux: Uses shell installer script

    Args:
        version: Specific version to install. If None, installs stable version.
                 Supports semantic versions (x.y.z) and pre-release tags.
                 Passed to platform-specific installer scripts.

    Returns:
        True if installation succeeded, False otherwise.

    Note:
        This function automatically detects the platform and calls the
        appropriate platform-specific installer.
    """
    system = platform.system()

    if system == 'Windows':
        return install_claude_native_windows(version)
    if system == 'Darwin':
        return install_claude_native_macos(version)
    # Linux and other Unix-like systems
    return install_claude_native_linux(version)


def ensure_claude() -> bool:
    """Ensure Claude Code is installed (native-first, npm fallback).

    Installation method can be controlled via CLAUDE_INSTALL_METHOD environment variable:
    - 'auto' (default): Try native first, fall back to npm if needed
    - 'native': Only use native installer, no npm fallback
    - 'npm': Only use npm installer

    Specific versions can only be installed via npm (set CLAUDE_VERSION environment variable).

    Returns:
        True if Claude Code is installed successfully, False otherwise.
    """
    info('Checking Claude Code CLI...')

    # Check installation method preference
    install_method = os.environ.get('CLAUDE_INSTALL_METHOD', 'auto').lower()
    if install_method not in ['auto', 'native', 'npm']:
        warning(f'Invalid CLAUDE_INSTALL_METHOD "{install_method}", using "auto"')
        install_method = 'auto'

    # Check if a specific version is requested
    requested_version = os.environ.get('CLAUDE_VERSION')

    # Check if already installed
    current_version = get_claude_version()

    if current_version:
        if requested_version:
            # Specific version requested - check if it matches
            if current_version != requested_version:
                info(f'Claude Code version {current_version} is installed, but version {requested_version} is requested')

                # Try installation based on method preference
                if install_method == 'npm':
                    # NPM-only mode
                    info(f'Installing Claude Code version {requested_version} via npm (method: npm)...')
                    if install_claude_npm(upgrade=False, version=requested_version):
                        new_version = get_claude_version()
                        if new_version:
                            success(f'Claude Code version {new_version} installed successfully')
                        return True
                    error(f'Failed to install specific version {requested_version}')
                    return False

                if install_method == 'native':
                    # Native-only mode with version support
                    info(f'Installing Claude Code version {requested_version} via native installer (method: native)...')
                    if install_claude_native_cross_platform(version=requested_version):
                        return True
                    error('Native installation failed and npm fallback is disabled (method: native)')
                    return False

                # 'auto'
                # Auto mode: Try native first with version, npm fallback
                info(f'Trying native installation for version {requested_version} (method: auto)...')
                if install_claude_native_cross_platform(version=requested_version):
                    return True

                warning('Native installation failed, falling back to npm...')
                if install_claude_npm(upgrade=False, version=requested_version):
                    new_version = get_claude_version()
                    if new_version:
                        success(f'Claude Code version {new_version} installed successfully via npm fallback')
                    return True

                error(f'Failed to install specific version {requested_version} with all methods')
                return False
            success(f'Claude Code version {current_version} is already installed (matches requested version)')
            # Set DISABLE_AUTOUPDATER since a specific version was requested
            set_disable_autoupdater()

            # Check if migration from npm to native is beneficial (even when version matches)
            # Only auto-migrate if: (1) auto mode, (2) currently npm
            if install_method == 'auto':
                is_installed, claude_path, source = verify_claude_installation()

                if is_installed and source == 'npm':
                    info(f'Detected npm installation at: {claude_path}')
                    info('Attempting migration to native installer for better stability...')

                    # Store current version before migration
                    pre_migration_version = current_version

                    # Try native installation WITH the requested version
                    if install_claude_native_cross_platform(version=requested_version):
                        # Verify native installation succeeded
                        post_install, _, post_source = verify_claude_installation()

                        if post_install and post_source == 'native':
                            success('Successfully migrated from npm to native installation')
                            info(f'Version maintained: {requested_version}')
                            info('The npm installation can be removed with: npm uninstall -g @anthropic-ai/claude-code')
                            return True
                        warning('Migration attempted but native installation not detected')
                        warning(f'Continuing with npm installation at: {claude_path}')
                        return True  # Don't fail, npm still works
                    warning('Native installation failed during migration')
                    info(f'Continuing with existing npm installation at: {claude_path}')
                    return True  # Don't fail, npm still works

            return True

        # Check if migration from npm to native is beneficial
        # Only auto-migrate if: (1) auto mode, (2) no specific version, (3) currently npm
        if install_method == 'auto':
            is_installed, claude_path, source = verify_claude_installation()

            if is_installed and source == 'npm':
                info(f'Detected npm installation at: {claude_path}')
                info('Attempting migration to native installer for better stability...')

                # Store current version before migration
                pre_migration_version = current_version

                # Try native installation (will install latest stable)
                if install_claude_native_cross_platform(version=None):
                    # Verify native installation succeeded
                    post_install, _, post_source = verify_claude_installation()

                    if post_install and post_source == 'native':
                        success('Successfully migrated from npm to native installation')
                        info(f'Previous version: {pre_migration_version}')
                        new_version = get_claude_version()
                        info(f'Current version: {new_version}')
                        info('The npm installation can be removed with: npm uninstall -g @anthropic-ai/claude-code')
                        return True
                    warning('Migration attempted but native installation not detected')
                    warning(f'Continuing with npm installation at: {claude_path}')
                    return True  # Don't fail, npm still works
                warning('Native installation failed during migration')
                info(f'Continuing with existing npm installation at: {claude_path}')
                return True  # Don't fail, npm still works

        # No specific version requested - check if update needed
        latest_version = get_latest_claude_version()
        if latest_version:
            if compare_versions(current_version, latest_version):
                # Current version is >= latest
                success(f'Claude Code version {current_version} is already up-to-date (latest: {latest_version})')
                return True
            # Current version is older - upgrade via npm
            info(f'Claude Code version {current_version} is installed, but {latest_version} is available')
            info(f'Upgrading to latest version {latest_version} via npm...')
            if install_claude_npm(upgrade=True, version=latest_version):
                new_version = get_claude_version()
                if new_version:
                    success(f'Claude Code upgraded to version {new_version}')
                return True
            warning('Upgrade failed, continuing with current version')
            return True  # Don't fail the entire installation

        # Cannot determine latest version - keep current
        warning('Cannot determine latest version from npm')
        success(f'Claude Code version {current_version} is already installed')
        return True

    # Fresh installation - Claude not found
    info('Claude Code not found, installing...')

    # Installation logic based on method
    if install_method == 'npm':
        # npm-only mode
        info('Using npm installation (method: npm)...')
        if install_claude_npm(upgrade=False, version=requested_version):
            # Verify with retries to handle PATH synchronization delays
            for attempt in range(3):
                claude_path = find_command_robust('claude')
                if claude_path:
                    new_version = get_claude_version()
                    if new_version:
                        success(f'Claude Code version {new_version} installed successfully')
                    return True
                if attempt < 2:
                    info(f'Waiting for PATH synchronization... (attempt {attempt + 1}/3)')
                    time.sleep(2)

        error('npm installation failed')
        return False

    if install_method == 'native':
        # native-only mode
        info('Using native installation (method: native)...')
        if install_claude_native_cross_platform(version=requested_version):
            return True

        error('Native installation failed and npm fallback is disabled (method: native)')
        info('To enable npm fallback, use: export CLAUDE_INSTALL_METHOD=auto')
        return False

    # auto mode (default) - try native first, npm fallback
    info('Trying native installation first (method: auto)...')
    if install_claude_native_cross_platform(version=requested_version):
        return True

    warning('Native installation failed, falling back to npm...')
    if install_claude_npm(upgrade=False, version=requested_version):
        # Verify with retries to handle PATH synchronization delays
        for attempt in range(3):
            claude_path = find_command_robust('claude')
            if claude_path:
                new_version = get_claude_version()
                if new_version:
                    success(f'Claude Code version {new_version} installed successfully via npm fallback')
                return True
            if attempt < 2:
                info(f'Waiting for PATH synchronization... (attempt {attempt + 1}/3)')
                time.sleep(2)

    # All methods failed
    error('Claude Code installation failed with all methods')
    info('Please try manual installation:')
    if platform.system() == 'Windows':
        info(f'  Native: irm {CLAUDE_INSTALLER_URL} | iex')
        info(f'  NPM: npm install -g {CLAUDE_NPM_PACKAGE}')
    else:
        info('  Native: curl -fsSL https://claude.ai/install.sh | bash')
        info(f'  NPM: npm install -g {CLAUDE_NPM_PACKAGE}')

    return False


def update_path() -> None:
    """Update PATH environment variable."""
    if platform.system() != 'Windows':
        return

    # Add npm global path to PATH if not already there
    npm_path = os.path.expandvars(r'%APPDATA%\npm')
    if Path(npm_path).exists():
        current_path = os.environ.get('PATH', '')
        if npm_path not in current_path:
            os.environ['PATH'] = f'{npm_path};{current_path}'
            info(f'Added {npm_path} to PATH')


def ensure_local_bin_in_path_windows() -> bool:
    """Ensure ~/.local/bin is in PATH on Windows after Claude installation.

    This function updates both the Windows registry (for persistence across sessions)
    and the current process environment (for immediate availability).

    Returns:
        True if PATH was updated or already correct, False on error.
    """
    success = True
    if sys.platform == 'win32':
        try:
            local_bin = Path.home() / '.local' / 'bin'
            local_bin.mkdir(parents=True, exist_ok=True)

            # Import winreg here to avoid import errors on non-Windows platforms
            import winreg

            # Open registry key for user environment variables
            reg_key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r'Environment',
                0,
                winreg.KEY_READ | winreg.KEY_WRITE,
            )

            try:
                current_path, _ = winreg.QueryValueEx(reg_key, 'PATH')
            except FileNotFoundError:
                current_path = ''

            local_bin_str = str(local_bin)

            # Check if already in PATH (case-insensitive)
            path_components = [p.strip() for p in current_path.split(';') if p.strip()]
            already_in_path = any(p.lower() == local_bin_str.lower() for p in path_components)

            if not already_in_path:
                # Add to PATH
                new_path = f'{local_bin_str};{current_path}' if current_path else local_bin_str

                # Check PATH length limit (setx has a 1024 character limit)
                if len(new_path) > 1024:
                    warning(f'PATH too long ({len(new_path)} chars, limit 1024). Manual intervention needed.')
                    winreg.CloseKey(reg_key)
                    success = False
                else:
                    # Update registry
                    winreg.SetValueEx(reg_key, 'PATH', 0, winreg.REG_EXPAND_SZ, new_path)
                    info(f'Added {local_bin_str} to Windows PATH registry')

                    # Broadcast WM_SETTINGCHANGE to notify other processes
                    # Use setx with a temporary variable to trigger the broadcast
                    run_command(['setx', 'CLAUDE_TOOLBOX_TEMP', 'temp'], capture_output=True)
                    run_command(
                        ['reg', 'delete', r'HKCU\Environment', '/v', 'CLAUDE_TOOLBOX_TEMP', '/f'],
                        capture_output=True,
                    )

            if success:
                winreg.CloseKey(reg_key)

                # CRITICAL: Update current process PATH immediately for same-session availability
                current_env_path = os.environ.get('PATH', '')
                if local_bin_str.lower() not in current_env_path.lower():
                    os.environ['PATH'] = f'{local_bin_str};{current_env_path}'
                    info(f'Updated current session PATH with {local_bin_str}')

        except Exception as e:
            warning(f'Failed to update PATH: {e}')
            success = False

    return success


def main() -> None:
    """Main installation flow."""
    banner()

    system = platform.system()

    try:
        # Step 1: Check Git Bash (Windows only)
        if system == 'Windows':
            info('Step 1/4: Checking Git Bash...')
            bash_path = ensure_git_bash_windows()
            if not bash_path:
                raise Exception('Git Bash unavailable after installation attempts')

            # Set CLAUDE_CODE_GIT_BASH_PATH if bash not in PATH
            if not find_command('bash.exe'):
                info('bash.exe is not on PATH, configuring CLAUDE_CODE_GIT_BASH_PATH...')
                set_windows_env_var('CLAUDE_CODE_GIT_BASH_PATH', bash_path)

        # Step 2: Check/Install Node.js (only if npm method will be used)
        step_num = '2/4' if system == 'Windows' else '1/3'
        info(f'Step {step_num}: Checking Node.js...')

        # Determine if we'll need Node.js based on installation method
        install_method = os.environ.get('CLAUDE_INSTALL_METHOD', 'auto').lower()
        will_need_nodejs = install_method == 'npm'

        if will_need_nodejs:
            info(f'Node.js will be needed for npm installation method (minimum version: {MIN_NODE_VERSION})')
            if not ensure_nodejs():
                error('Node.js installation failed')
                raise Exception(f'Node.js >= {MIN_NODE_VERSION} unavailable after installation attempts')
        else:
            info('Skipping Node.js installation (native method will be used)')

        # Step 3: Configure environment (Windows only)
        if system == 'Windows':
            info('Step 3/4: Configuring environment...')
            configure_powershell_policy()
            update_path()

        # Step 4: Install Claude Code
        step_num = '4/4' if system == 'Windows' else '3/3' if system == 'Darwin' else '3/3'
        info(f'Step {step_num}: Installing Claude Code CLI...')
        if not ensure_claude():
            raise Exception('Claude Code installation failed with all methods')

        # Success!
        print()
        print(f'{Colors.GREEN}============================================{Colors.NC}')
        print(f'{Colors.GREEN}  Installation Complete!{Colors.NC}')
        print(f'{Colors.GREEN}============================================{Colors.NC}')
        print()

        info('You can now start using Claude by running: claude')
        info('If claude command is not found, please open a new terminal.')

        if system == 'Windows' and not is_admin():
            print()
            warning('IMPORTANT: Not installed as administrator')
            info("If you get 'cannot be loaded' errors in PowerShell, run:")
            info('  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser')

    except Exception as e:
        print()
        error(str(e))
        print()
        print(f'{Colors.RED}Installation failed. Please check the error above.{Colors.NC}')
        print(f'{Colors.YELLOW}For help, visit: https://github.com/alex-feel/claude-code-toolbox{Colors.NC}')
        print()
        sys.exit(1)


if __name__ == '__main__':
    main()
