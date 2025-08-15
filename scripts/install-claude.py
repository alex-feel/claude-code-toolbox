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
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    CYAN = '\033[0;36m'
    NC = '\033[0m'  # No Color
    BOLD = '\033[1m'

    @staticmethod
    def strip():
        """Strip colors for Windows cmd that doesn't support ANSI."""
        if platform.system() == 'Windows' and not os.environ.get('WT_SESSION'):
            Colors.RED = Colors.GREEN = Colors.YELLOW = Colors.BLUE = Colors.CYAN = Colors.NC = Colors.BOLD = ''


# Initialize colors based on terminal support
Colors.strip()

# Configuration
MIN_NODE_VERSION = '18.0.0'
NODE_LTS_API = 'https://nodejs.org/dist/index.json'
GIT_WINDOWS_URL = 'https://git-scm.com/downloads/win'
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


def run_command(cmd: list, capture_output: bool = True, **kwargs: Any) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    try:
        # Debug: print command being run if not capturing output
        if not capture_output:
            info(f'Executing: {", ".join(cmd)}')
        return subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
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
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False
    else:
        return os.geteuid() == 0


def find_command(cmd: str) -> str | None:
    """Find a command in PATH."""
    return shutil.which(cmd)


def parse_version(version_str: str) -> tuple[int, int, int] | None:
    """Parse version string to tuple."""
    match = re.match(r'v?(\d+)\.(\d+)\.(\d+)', version_str)
    if match:
        return tuple(map(int, match.groups()))
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
    """Find Git Bash on Windows."""
    # Check CLAUDE_CODE_GIT_BASH_PATH env var
    env_path = os.environ.get('CLAUDE_CODE_GIT_BASH_PATH')
    if env_path and Path(env_path).exists():
        return str(Path(env_path).resolve())

    # Check if bash is in PATH
    bash_path = find_command('bash.exe')
    if bash_path:
        return bash_path

    # Check common locations
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
        'winget', 'install',
        '--id', 'Git.Git',
        '-e',
        '--source', 'winget',
        '--accept-package-agreements',
        '--accept-source-agreements',
        '--silent',
        '--disable-interactivity',
        '--scope', scope,
    ])

    if result.returncode == 0:
        success('Git for Windows installed via winget')
        return True
    warning(f'winget exited with code {result.returncode}')
    return False


def install_git_windows_download() -> bool:
    """Install Git for Windows by direct download."""
    try:
        info('Downloading Git for Windows installer...')

        # Get the download page (with SSL fallback)
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

        # Find the installer link
        match = re.search(r'href="([^"]+Git-[\d.]+-64-bit\.exe)"', html)
        if not match:
            raise Exception('Could not find Git installer link')

        installer_url = match.group(1)
        if not installer_url.startswith('http'):
            installer_url = f'https://github.com{installer_url}'

        # Download installer
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

        # Run installer silently
        info('Running Git installer silently...')
        result = run_command([
            temp_path,
            '/VERYSILENT', '/NORESTART', '/NOCANCEL', '/SP-',
            '/CLOSEAPPLICATIONS', '/RESTARTAPPLICATIONS',
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
            run_command([
                'setx', name, value,
            ], capture_output=False)
            success(f'Set environment variable: {name}')
    except Exception as e:
        warning(f'Could not set environment variable {name}: {e}')


def configure_powershell_policy() -> None:
    """Configure PowerShell execution policy for npm scripts."""
    if platform.system() != 'Windows':
        return

    info('Configuring PowerShell execution policy...')

    # Try to set for current user
    result = run_command([
        'powershell', '-Command',
        'Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force',
    ])

    if result.returncode == 0:
        success('PowerShell execution policy configured for current user')
    else:
        warning('Could not set PowerShell execution policy (may be restricted by Group Policy)')


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


def install_nodejs_winget(scope: str = 'user') -> bool:
    """Install Node.js using winget on Windows."""
    if not check_winget():
        return False

    info(f'Installing Node.js LTS via winget, scope: {scope}')
    result = run_command([
        'winget', 'install',
        '--id', 'OpenJS.NodeJS.LTS',
        '-e',
        '--source', 'winget',
        '--accept-package-agreements',
        '--accept-source-agreements',
        '--silent',
        '--disable-interactivity',
        '--scope', scope,
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
            info('Installing Node.js silently...')
            result = run_command(['msiexec', '/i', temp_path, '/quiet', '/norestart'])

            # After MSI installation, add Node.js to PATH for current process
            if result.returncode == 0:
                nodejs_path = r'C:\Program Files\nodejs'
                if Path(nodejs_path).exists():
                    current_path = os.environ.get('PATH', '')
                    if nodejs_path not in current_path:
                        os.environ['PATH'] = f'{nodejs_path};{current_path}'
                        info(f'Added {nodejs_path} to PATH for current session')
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
            '/bin/bash', '-c',
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
        'bash', '-c',
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
                if get_node_version() and compare_versions(get_node_version(), MIN_NODE_VERSION):
                    return True

            if is_admin() and install_nodejs_winget('machine'):
                time.sleep(2)
                if get_node_version() and compare_versions(get_node_version(), MIN_NODE_VERSION):
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
        if install_nodejs_homebrew() and get_node_version() and compare_versions(get_node_version(), MIN_NODE_VERSION):
            return True

        # Fallback to direct download
        if install_nodejs_direct():
            time.sleep(2)
            if get_node_version() and compare_versions(get_node_version(), MIN_NODE_VERSION):
                return True

    else:  # Linux
        # Detect distro and use package manager
        if (
            Path('/etc/debian_version').exists()
            and install_nodejs_apt()
            and get_node_version()
            and compare_versions(get_node_version(), MIN_NODE_VERSION)
        ):
            return True
        warning('Unsupported Linux distribution - please install Node.js manually')
        return False

    error(f'Could not install Node.js >= {MIN_NODE_VERSION}')
    return False


# Claude Code installation
def install_claude_npm() -> bool:
    """Install Claude Code using npm."""
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

    npm_path = find_command('npm')
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

    info(f'Installing Claude Code CLI via npm (npm path: {npm_path})...')

    # Try without sudo first (show output for debugging)
    cmd = [npm_path, 'install', '-g', CLAUDE_NPM_PACKAGE]
    info(f'Running command: {" ".join(cmd)}')
    result = run_command(cmd, capture_output=False)

    if result.returncode == 0:
        success('Claude Code installed successfully')
        return True

    # Try with sudo on Unix systems
    if platform.system() != 'Windows':
        warning('Trying with sudo...')
        result = run_command(['sudo', 'npm', 'install', '-g', CLAUDE_NPM_PACKAGE], capture_output=False)
        if result.returncode == 0:
            success('Claude Code installed successfully')
            return True

    error('Failed to install Claude Code via npm')
    return False


def install_claude_native() -> bool:
    """Install Claude Code using native installer."""
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

        # Execute installer (show output for debugging)
        result = run_command([
            'powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
            '-File', temp_path,
        ], capture_output=False)

        # Clean up
        with contextlib.suppress(Exception):
            os.unlink(temp_path)

        if result.returncode == 0:
            success('Claude Code installed via native installer')
            return True

    except Exception as e:
        error(f'Native installer failed: {e}')

    return False


def ensure_claude() -> bool:
    """Ensure Claude Code is installed."""
    info('Installing Claude Code CLI...')

    # Check if already installed
    if find_command('claude'):
        success('Claude Code is already installed')
        return True

    # Check common locations on Windows
    if platform.system() == 'Windows':
        common_paths = [
            os.path.expandvars(r'%APPDATA%\npm\claude.cmd'),
            os.path.expandvars(r'%APPDATA%\npm\claude'),
            os.path.expandvars(r'%ProgramFiles%\nodejs\claude.cmd'),
            os.path.expandvars(r'%LOCALAPPDATA%\Programs\claude\claude.exe'),
        ]

        for path in common_paths:
            if Path(path).exists():
                success(f'Claude Code already installed at: {path}')
                return True

    # Try npm installation
    if install_claude_npm():
        return True

    # Try native installer on Windows
    if platform.system() == 'Windows' and install_claude_native():
        return True

    error('Claude Code installation failed with all methods')
    info('Please try manual installation:')
    info(f'  npm install -g {CLAUDE_NPM_PACKAGE}')
    if platform.system() == 'Windows':
        info('  or')
        info(f'  irm {CLAUDE_INSTALLER_URL} | iex')

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

        # Step 2: Check/Install Node.js
        step_num = '2/4' if system == 'Windows' else '1/3'
        info(f'Step {step_num}: Checking Node.js (minimum version: {MIN_NODE_VERSION})...')
        if not ensure_nodejs():
            raise Exception(f'Node.js >= {MIN_NODE_VERSION} unavailable after installation attempts')

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
