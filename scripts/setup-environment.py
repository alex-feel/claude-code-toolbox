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
import json
import os
import platform
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

import yaml


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
REPO_BASE_URL = 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main'


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


def run_command(cmd: list, capture_output: bool = True, **kwargs: Any) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    try:
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


def load_config_from_source(config_spec: str) -> dict[str, Any]:
    """Load configuration from URL, local path, or repository.

    Supports three sources:
    1. Direct URL: http://... or https://...
    2. Local file: ./config.yaml, ../configs/env.yaml, /absolute/path.yaml
    3. Repository config: just a name like 'python'

    Returns:
        dict[str, Any]: Parsed YAML configuration.

    Raises:
        FileNotFoundError: If local file doesn't exist.
        urllib.error.URLError: If URL download fails.
        urllib.error.HTTPError: If HTTP request fails.
        Exception: If configuration is not found or parsing fails.
    """

    # Source 1: Direct URL
    if config_spec.startswith(('http://', 'https://')):
        info(f'Loading configuration from URL: {config_spec}')
        warning('⚠️  Loading configuration from remote URL')
        warning('⚠️  Only use configs from trusted sources!')

        try:
            try:
                response = urlopen(config_spec)
                content = response.read().decode('utf-8')
            except urllib.error.URLError as e:
                if 'SSL' in str(e) or 'certificate' in str(e).lower():
                    warning('SSL certificate verification failed, trying with unverified context')
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    response = urlopen(config_spec, context=ctx)
                    content = response.read().decode('utf-8')
                else:
                    raise

            config = yaml.safe_load(content)
            success(f'Configuration loaded from URL: {config.get("name", "Remote Config")}')
            return config
        except Exception as e:
            error(f'Failed to load configuration from URL: {e}')
            raise

    # Source 2: Local file (has path separators, starts with . or exists)
    if ('/' in config_spec or '\\' in config_spec or
        config_spec.startswith(('./', '.\\', '../', '..\\')) or
        os.path.isabs(config_spec) or os.path.exists(config_spec)):

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
            success(f'Configuration loaded: {config.get("name", config_path.name)}')
            return config
        except Exception as e:
            error(f'Failed to load local configuration: {e}')
            raise

    # Source 3: Repository config (just a name)
    if not config_spec.endswith('.yaml'):
        config_spec += '.yaml'

    config_url = f'{REPO_BASE_URL}/environments/examples/{config_spec}'
    info(f'Loading configuration from repository: {config_spec}')

    try:
        try:
            response = urlopen(config_url)
            content = response.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            if e.code == 404:
                error(f'Configuration not found in repository: {config_spec}')
                info('Available configurations:')
                info('  - python: Python development environment')
                info('')
                info('You can also:')
                info('  - Create custom configs in environments/examples/')
                info('  - Use a local file: ./my-config.yaml')
                info('  - Use a URL: https://example.com/config.yaml')
                raise Exception(f'Configuration not found: {config_spec}') from None
            raise
        except urllib.error.URLError as e:
            if 'SSL' in str(e) or 'certificate' in str(e).lower():
                warning('SSL certificate verification failed, trying with unverified context')
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                response = urlopen(config_url, context=ctx)
                content = response.read().decode('utf-8')
            else:
                raise

        config = yaml.safe_load(content)
        success(f'Configuration loaded: {config.get("name", config_spec)}')
        return config
    except Exception as e:
        if 'Configuration not found' not in str(e):
            error(f'Failed to load repository configuration: {e}')
        raise


def install_dependencies(dependencies: list[str]) -> bool:
    """Install dependencies from configuration."""
    if not dependencies:
        return True

    info('Installing dependencies...')
    system = platform.system()

    for dep in dependencies:
        info(f'Running: {dep}')

        # Parse the command
        parts = dep.split()

        # Handle platform-specific commands
        if system == 'Windows':
            if parts[0] in ['winget', 'npm', 'pip', 'pipx']:
                result = run_command(parts, capture_output=False)
            elif parts[0] == 'uv' and parts[1] == 'tool' and parts[2] == 'install':
                # For uv tool install, add --force to update if already installed
                parts_with_force = parts[:3] + ['--force'] + parts[3:]
                result = run_command(parts_with_force, capture_output=False)
            else:
                # Try PowerShell for other commands
                result = run_command(['powershell', '-Command', dep], capture_output=False)
        else:
            # Unix-like systems
            if parts[0] == 'uv' and len(parts) >= 3 and parts[1] == 'tool' and parts[2] == 'install':
                # For uv tool install, add --force to update if already installed
                dep_with_force = dep.replace('uv tool install', 'uv tool install --force')
                result = run_command(['bash', '-c', dep_with_force], capture_output=False)
            else:
                result = run_command(['bash', '-c', dep], capture_output=False)

        if result.returncode != 0:
            error(f'Failed to install dependency: {dep}')
            warning('Continuing with other dependencies...')

    return True


def download_resources(resources: list[str], destination_dir: Path, resource_type: str) -> bool:
    """Download resources (agents, commands, output-styles) from configuration."""
    if not resources:
        return True

    info(f'Downloading {resource_type}...')

    for resource in resources:
        url = f'{REPO_BASE_URL}/{resource}'
        filename = Path(resource).name
        destination = destination_dir / filename
        download_file(url, destination)

    return True


def install_claude() -> bool:
    """Install Claude Code if needed."""
    info('Installing Claude Code...')

    system = platform.system()

    try:
        # Download the appropriate installer script
        if system == 'Windows':
            installer_url = f'{REPO_BASE_URL}/scripts/windows/install-claude-windows.ps1'
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
            result = run_command([
                'powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                '-File', temp_installer,
            ], capture_output=False)

        elif system == 'Darwin':  # macOS
            installer_url = f'{REPO_BASE_URL}/scripts/macos/install-claude-macos.sh'
            result = run_command([
                'bash', '-c',
                f'curl -fsSL {installer_url} | bash',
            ], capture_output=False)

        else:  # Linux
            installer_url = f'{REPO_BASE_URL}/scripts/linux/install-claude-linux.sh'
            result = run_command([
                'bash', '-c',
                f'curl -fsSL {installer_url} | bash',
            ], capture_output=False)

        # Clean up temp file on Windows
        if system == 'Windows' and 'temp_installer' in locals():
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


def configure_mcp_server(server: dict[str, Any]) -> bool:
    """Configure a single MCP server."""
    name = server.get('name')
    scope = server.get('scope', 'user')
    transport = server.get('transport')
    url = server.get('url')
    command = server.get('command')
    header = server.get('header')
    env = server.get('env')

    if not name:
        error('MCP server configuration missing name')
        return False

    info(f'Configuring MCP server: {name}')

    system = platform.system()
    claude_cmd = None

    # First try to find claude in PATH
    claude_cmd = find_command('claude')

    # If not in PATH, look for it where npm installs it
    if not claude_cmd:
        if system == 'Windows':
            # On Windows, npm installs to %APPDATA%\npm
            npm_path = Path(os.environ.get('APPDATA', '')) / 'npm'
            claude_cmd_path = npm_path / 'claude.cmd'
            if claude_cmd_path.exists():
                claude_cmd = str(claude_cmd_path)
                info(f'Found claude at: {claude_cmd}')
            else:
                # Also check without .cmd extension
                claude_path = npm_path / 'claude'
                if claude_path.exists():
                    claude_cmd = str(claude_path)
                    info(f'Found claude at: {claude_cmd}')
        else:
            # On Unix, check common npm global locations
            possible_paths = [
                Path.home() / '.npm-global' / 'bin' / 'claude',
                Path('/usr/local/bin/claude'),
                Path('/usr/bin/claude'),
            ]
            for path in possible_paths:
                if path.exists():
                    claude_cmd = str(path)
                    info(f'Found claude at: {claude_cmd}')
                    break

    if not claude_cmd:
        error('Claude command not found even after installation!')
        error('This should not happen. Something went wrong with npm installation.')
        return False

    try:
        # Build the base command
        base_cmd = [str(claude_cmd), 'mcp', 'add']

        if scope:
            base_cmd.extend(['--scope', scope])

        base_cmd.append(name)

        # Handle different transport types
        if transport and url:
            # HTTP or SSE transport
            base_cmd.extend(['--transport', transport, url])
            if header:
                base_cmd.extend(['--header', header])

            # Try with PowerShell environment reload on Windows
            if system == 'Windows':
                # On Windows, we need to spawn a completely new shell process
                ps_script = f'''
$userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
$machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
$env:Path = $userPath + ";" + $machinePath
& "{claude_cmd}" mcp add --scope {scope} --transport {transport} {name} {url}
$LASTEXITCODE
'''
                if header:
                    ps_script = f'''
$userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
$machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
$env:Path = $userPath + ";" + $machinePath
& "{claude_cmd}" mcp add --scope {scope} --transport {transport} --header "{header}" {name} {url}
$LASTEXITCODE
'''
                result = run_command([
                    'powershell', '-NoProfile', '-Command', ps_script,
                ], capture_output=True)

                # Also try with direct execution
                if result.returncode != 0:
                    info('Trying direct execution...')
                    result = run_command(base_cmd, capture_output=True)
            else:
                # On Unix, spawn new bash with updated PATH
                parent_dir = Path(claude_cmd).parent
                bash_cmd = (
                    f'export PATH="{parent_dir}:$PATH" && '
                    f'{" ".join(base_cmd)}'
                )
                result = run_command([
                    'bash', '-l', '-c', bash_cmd,
                ], capture_output=True)
        elif command:
            # Stdio transport (command)
            if env:
                base_cmd.extend(['--env', env])
            base_cmd.append('--')

            # Platform-specific command handling
            if system == 'Windows' and 'npx' in command:
                # Windows needs cmd /c wrapper for npx
                base_cmd.extend(['cmd', '/c', command])
            else:
                # Unix-like systems can run command directly
                base_cmd.extend(command.split())

            result = run_command(base_cmd, capture_output=True)
        else:
            error(f'MCP server {name} missing url or command')
            return False

        # Check if successful
        if result.returncode == 0:
            success(f'MCP server {name} configured successfully!')
            return True
        if result.stderr and 'already exists' in result.stderr.lower():
            success(f'MCP server {name} already configured!')
            return True

        # If it still fails, try one more time with a delay
        info('First attempt failed, waiting 2 seconds and retrying...')
        time.sleep(2)

        # Direct execution with full path
        result = run_command(base_cmd, capture_output=False)  # Show output for debugging

        if result.returncode == 0:
            success(f'MCP server {name} configured successfully!')
            return True
        error(f'MCP configuration failed with exit code: {result.returncode}')
        if result.stderr:
            error(f'Error: {result.stderr}')
        return False

    except Exception as e:
        error(f'Failed to configure MCP server {name}: {e}')
        return False


def configure_all_mcp_servers(servers: list[dict[str, Any]]) -> bool:
    """Configure all MCP servers from configuration."""
    if not servers:
        return True

    info('Configuring MCP servers...')

    for server in servers:
        configure_mcp_server(server)

    return True


def create_additional_settings(
    hooks: dict[str, Any],
    claude_user_dir: Path,
    output_style: str | None = None,
    mcp_servers: list[dict[str, Any]] | None = None,
) -> bool:
    """Create additional-settings.json with environment-specific hooks, output style, and permissions.

    This file is always overwritten to avoid duplicate hooks when re-running the installer.
    It's loaded via --settings flag when launching Claude.

    Args:
        hooks: Hooks configuration dictionary with 'files' and 'events' keys
        claude_user_dir: Path to Claude user directory
        output_style: Optional output style filename (without extension) to set as default
        mcp_servers: Optional list of MCP server configurations to pre-allow

    Returns:
        bool: True if successful, False otherwise.
    """
    info('Creating additional-settings.json...')

    # Create fresh settings structure for this environment
    settings = {}

    # Add output style if specified
    if output_style:
        # Remove .md extension if present
        style_name = output_style.replace('.md', '')
        settings['outputStyle'] = style_name
        info(f'Setting default output style: {style_name}')

    # Add MCP server permissions if specified
    if mcp_servers:
        permissions_allow = []
        for server in mcp_servers:
            if isinstance(server, dict) and 'name' in server:
                # Format as mcp__servername for permissions
                server_permission = f"mcp__{server['name']}"
                permissions_allow.append(server_permission)
                info(f'Pre-allowing MCP server: {server["name"]}')

        if permissions_allow:
            settings['permissions'] = {
                'allow': permissions_allow,
            }

    # Handle hooks if present
    hook_files = []
    hook_events = []

    if hooks:
        settings['hooks'] = {}
        # Extract files and events from the hooks configuration
        hook_files = hooks.get('files', [])
        hook_events = hooks.get('events', [])

    # Download all hook files first
    if hook_files:
        hooks_dir = claude_user_dir / 'hooks'
        hooks_dir.mkdir(parents=True, exist_ok=True)
        for file in hook_files:
            url = f'{REPO_BASE_URL}/{file}'
            filename = Path(file).name
            destination = hooks_dir / filename
            download_file(url, destination)

    # Process each hook event
    for hook in hook_events:

        event = hook.get('event')
        matcher = hook.get('matcher', '')
        hook_type = hook.get('type', 'command')
        command = hook.get('command')

        if not event or not command:
            warning('Invalid hook configuration, skipping')
            continue

        # Add to settings
        if event not in settings['hooks']:
            settings['hooks'][event] = []

        # Find or create matcher group
        matcher_group = None
        for group in settings['hooks'][event]:
            if group.get('matcher') == matcher:
                matcher_group = group
                break

        if not matcher_group:
            matcher_group = {
                'matcher': matcher,
                'hooks': [],
            }
            settings['hooks'][event].append(matcher_group)

        # Build the proper command based on OS and file type
        if command.endswith('.py'):
            # Python script - need to handle cross-platform execution
            # Use the absolute path to the downloaded hook file
            hook_path = claude_user_dir / 'hooks' / Path(command).name

            if platform.system() == 'Windows':
                # Windows needs explicit Python interpreter
                # Use 'py' which is more reliable on Windows, fallback to 'python'
                python_cmd = 'py' if shutil.which('py') else 'python'
                # Use forward slashes for the path (works on Windows and avoids JSON escaping issues)
                hook_path_str = hook_path.as_posix()
                full_command = f'{python_cmd} {hook_path_str}'
            else:
                # Unix-like systems can use shebang directly
                # Make script executable
                if hook_path.exists():
                    hook_path.chmod(0o755)
                full_command = str(hook_path)
        else:
            # Not a Python script, use command as-is
            full_command = command

        # Add hook configuration
        hook_config = {
            'type': hook_type,
            'command': full_command,
        }
        matcher_group['hooks'].append(hook_config)

    # Save additional settings (always overwrite)
    additional_settings_path = claude_user_dir / 'additional-settings.json'
    try:
        with open(additional_settings_path, 'w') as f:
            json.dump(settings, f, indent=2)
        success('Created additional-settings.json with environment hooks')
        return True
    except Exception as e:
        error(f'Failed to save additional-settings.json: {e}')
        return False


def create_launcher_script(
    claude_user_dir: Path,
    command_name: str,
    system_prompt_file: str | None = None,
) -> Path | None:
    """Create launcher script for starting Claude with optional system prompt.

    Args:
        claude_user_dir: Path to Claude user directory
        command_name: Name of the command to create launcher for
        system_prompt_file: Optional system prompt filename (if None, only settings are used)

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
                shared_sh_content = f'''#!/usr/bin/env bash
set -euo pipefail

# Get Windows path for settings
SETTINGS_WIN="$(cygpath -m "$HOME/.claude/additional-settings.json" 2>/dev/null ||
  echo "$HOME/.claude/additional-settings.json")"

# Read and prepare system prompt
PROMPT_PATH="$HOME/.claude/prompts/{system_prompt_file}"
if [ ! -f "$PROMPT_PATH" ]; then
  echo "Error: System prompt not found at $PROMPT_PATH" >&2
  exit 1
fi

# Read prompt and remove Windows CRLF
PROMPT_CONTENT=$(tr -d '\\r' < "$PROMPT_PATH")

exec claude --append-system-prompt "$PROMPT_CONTENT" --settings "$SETTINGS_WIN" "$@"
'''
            else:
                # No system prompt, only settings
                shared_sh_content = '''#!/usr/bin/env bash
set -euo pipefail

# Get Windows path for settings
SETTINGS_WIN="$(cygpath -m "$HOME/.claude/additional-settings.json" 2>/dev/null ||
  echo "$HOME/.claude/additional-settings.json")"

exec claude --settings "$SETTINGS_WIN" "$@"
'''
            shared_sh.write_text(shared_sh_content, newline='\n')
            # Make it executable for bash
            with contextlib.suppress(Exception):
                shared_sh.chmod(0o755)

        else:
            # Create bash launcher for Unix-like systems
            launcher_path = launcher_path.with_suffix('.sh')

            if system_prompt_file:
                launcher_content = f'''#!/usr/bin/env bash
# Claude Code Environment Launcher
# This script starts Claude Code with the configured environment

CLAUDE_USER_DIR="$HOME/.claude"
PROMPT_PATH="$CLAUDE_USER_DIR/prompts/{system_prompt_file}"

if [ ! -f "$PROMPT_PATH" ]; then
    echo -e "\\033[0;31mError: System prompt not found at $PROMPT_PATH\\033[0m"
    echo -e "\\033[1;33mPlease run setup-environment.py first\\033[0m"
    exit 1
fi

echo -e "\\033[0;32mStarting Claude Code with {command_name} configuration...\\033[0m"

# Read the prompt content
PROMPT_CONTENT=$(cat "$PROMPT_PATH")
SETTINGS_PATH="$CLAUDE_USER_DIR/additional-settings.json"

# Pass any additional arguments to Claude
if [ $# -gt 0 ]; then
    echo -e "\\033[0;36mPassing additional arguments: $@\\033[0m"
    claude --append-system-prompt "$PROMPT_CONTENT" --settings "$SETTINGS_PATH" "$@"
else
    claude --append-system-prompt "$PROMPT_CONTENT" --settings "$SETTINGS_PATH"
fi
'''
            else:
                launcher_content = f'''#!/usr/bin/env bash
# Claude Code Environment Launcher
# This script starts Claude Code with the configured environment

CLAUDE_USER_DIR="$HOME/.claude"
SETTINGS_PATH="$CLAUDE_USER_DIR/additional-settings.json"

echo -e "\\033[0;32mStarting Claude Code with {command_name} configuration...\\033[0m"

# Pass any additional arguments to Claude
if [ $# -gt 0 ]; then
    echo -e "\\033[0;36mPassing additional arguments: $@\\033[0m"
    claude --settings "$SETTINGS_PATH" "$@"
else
    claude --settings "$SETTINGS_PATH"
fi
'''
            launcher_path.write_text(launcher_content)
            launcher_path.chmod(0o755)

        success('Created launcher script')
        return launcher_path

    except Exception as e:
        warning(f'Failed to create launcher script: {e}')
        return None


def register_global_command(launcher_path: Path, command_name: str) -> bool:
    """Register global command."""
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

            # Add .local/bin to PATH if not already there
            user_path = os.environ.get('PATH', '')
            local_bin_str = str(local_bin)
            if local_bin_str not in user_path:
                # Update current session
                os.environ['PATH'] = f'{local_bin_str};{user_path}'

                # Update persistent user PATH (Windows only)
                run_command(['setx', 'PATH', f'{local_bin_str};%PATH%'], capture_output=True)
                success(f'Added {local_bin_str} to PATH')
                info('You may need to restart your terminal for PATH changes to take effect')

        else:
            # Create symlink in ~/.local/bin
            local_bin = Path.home() / '.local' / 'bin'
            local_bin.mkdir(parents=True, exist_ok=True)

            symlink_path = local_bin / command_name
            if symlink_path.exists():
                symlink_path.unlink()
            symlink_path.symlink_to(launcher_path)

            # Ensure ~/.local/bin is in PATH
            info('Make sure ~/.local/bin is in your PATH')
            info('Add this to your ~/.bashrc or ~/.zshrc if needed:')
            info('  export PATH="$HOME/.local/bin:$PATH"')

        if system == 'Windows':
            success(f'Created global command: {command_name} (works in PowerShell, CMD, and Git Bash)')
            info('The command now works in all Windows shells!')
        else:
            success(f'Created global command: {command_name}')
        return True

    except Exception as e:
        warning(f'Failed to register global command: {e}')
        return False


def main() -> None:
    """Main setup flow."""
    parser = argparse.ArgumentParser(description='Setup development environment for Claude Code')
    parser.add_argument('config', nargs='?',
                        help='Configuration file name (e.g., python.yaml)')
    parser.add_argument('--skip-install', action='store_true',
                        help='Skip Claude Code installation')
    parser.add_argument('--force', action='store_true',
                        help='Force overwrite existing files')
    args = parser.parse_args()

    # Get configuration from args or environment
    config_name = args.config or os.environ.get('CLAUDE_ENV_CONFIG')

    if not config_name:
        error('No configuration specified!')
        info('Usage: setup-environment.py <config_name>')
        info('   or: CLAUDE_ENV_CONFIG=<config_name> setup-environment.py')
        info('Example: setup-environment.py python')
        sys.exit(1)

    try:
        # Load configuration from source (URL, local file, or repository)
        config = load_config_from_source(config_name)

        environment_name = config.get('name', 'Development')
        command_name = config.get('command-name', 'claude-env')

        # Extract command defaults
        command_defaults = config.get('command-defaults', {})
        output_style = command_defaults.get('output-style')
        system_prompt = command_defaults.get('system-prompt')

        header(environment_name)

        # Set up directories
        home = Path.home()
        claude_user_dir = home / '.claude'
        agents_dir = claude_user_dir / 'agents'
        commands_dir = claude_user_dir / 'commands'
        prompts_dir = claude_user_dir / 'prompts'
        output_styles_dir = claude_user_dir / 'output-styles'
        hooks_dir = claude_user_dir / 'hooks'

        # Step 1: Install Claude Code if needed (MUST be first - provides uv, git bash, node)
        if not args.skip_install:
            print(f'{Colors.CYAN}Step 1: Installing Claude Code...{Colors.NC}')
            if not install_claude():
                raise Exception('Claude Code installation failed')
        else:
            print(f'{Colors.CYAN}Step 1: Skipping Claude Code installation (already installed){Colors.NC}')

            # Verify Claude Code is available
            if not find_command('claude'):
                error('Claude Code is not available in PATH')
                info('Please install Claude Code first or remove the --skip-install flag')
                raise Exception('Claude Code not found')

        # Step 2: Create directories
        print()
        print(f'{Colors.CYAN}Step 2: Creating configuration directories...{Colors.NC}')
        for dir_path in [claude_user_dir, agents_dir, commands_dir, prompts_dir, output_styles_dir, hooks_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
            success(f'Created: {dir_path}')

        # Step 3: Install dependencies (after Claude Code which provides tools)
        print()
        print(f'{Colors.CYAN}Step 3: Installing dependencies...{Colors.NC}')
        dependencies = config.get('dependencies', [])
        install_dependencies(dependencies)

        # Step 4: Download agents
        print()
        print(f'{Colors.CYAN}Step 4: Downloading agents...{Colors.NC}')
        agents = config.get('agents', [])
        download_resources(agents, agents_dir, 'agents')

        # Step 5: Download slash commands
        print()
        print(f'{Colors.CYAN}Step 5: Downloading slash commands...{Colors.NC}')
        commands = config.get('slash-commands', [])
        download_resources(commands, commands_dir, 'slash commands')

        # Step 6: Download output styles
        print()
        print(f'{Colors.CYAN}Step 6: Downloading output styles...{Colors.NC}')
        output_styles = config.get('output-styles', [])
        if output_styles:
            download_resources(output_styles, output_styles_dir, 'output styles')
        else:
            info('No output styles configured')

        # Step 7: Download system prompt (if specified)
        print()
        print(f'{Colors.CYAN}Step 7: Downloading system prompt...{Colors.NC}')
        prompt_path = None
        if system_prompt:
            prompt_url = f'{REPO_BASE_URL}/{system_prompt}'
            prompt_filename = Path(system_prompt).name
            prompt_path = prompts_dir / prompt_filename
            download_file(prompt_url, prompt_path)
        else:
            info('No additional system prompt configured')

        # Step 8: Configure MCP servers
        print()
        print(f'{Colors.CYAN}Step 8: Configuring MCP servers...{Colors.NC}')
        mcp_servers = config.get('mcp-servers', [])
        configure_all_mcp_servers(mcp_servers)

        # Step 9: Configure hooks and output style
        print()
        print(f'{Colors.CYAN}Step 9: Configuring hooks and settings...{Colors.NC}')
        hooks = config.get('hooks', {})
        create_additional_settings(hooks, claude_user_dir, output_style, mcp_servers)

        # Step 10: Create launcher script
        print()
        print(f'{Colors.CYAN}Step 10: Creating launcher script...{Colors.NC}')
        prompt_filename = Path(system_prompt).name if system_prompt else None
        launcher_path = create_launcher_script(claude_user_dir, command_name, prompt_filename)

        # Step 11: Register global command
        if launcher_path:
            print()
            print(f'{Colors.CYAN}Step 11: Registering global {command_name} command...{Colors.NC}')
            register_global_command(launcher_path, command_name)
        else:
            warning('Launcher script was not created')

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
        print(f'   * Output styles: {len(output_styles) if output_styles else 0} installed')
        if output_style:
            print(f'   * Default output style: {output_style}')
        if system_prompt:
            print('   * Additional system prompt: Configured')
        print(f'   * MCP servers: {len(mcp_servers)} configured')
        print(f'   * Hooks: {len(hooks.get("events", [])) if hooks else 0} configured')
        print(f'   * Global command: {command_name} registered')

        print()
        print(f'{Colors.YELLOW}Quick Start:{Colors.NC}')
        print(f'   * Global command: {command_name}')

        print()
        print(f'{Colors.YELLOW}Available Commands (after starting Claude):{Colors.NC}')
        print('   * /help - See all available commands')
        print('   * /agents - Manage subagents')
        print('   * /hooks - Manage hooks')
        print('   * /mcp - Manage MCP servers')
        print('   * /output-style - Choose or manage output styles')
        print('   * /<slash-command> - Run specific slash command')

        print()
        print(f'{Colors.YELLOW}Examples:{Colors.NC}')
        print(f'   {command_name}')
        print(f'   > Start working with {environment_name} environment')

        print()
        print(f'{Colors.YELLOW}Documentation:{Colors.NC}')
        print('   * Setup Guide: https://github.com/alex-feel/claude-code-toolbox')
        print('   * Claude Code Docs: https://docs.anthropic.com/claude-code')
        print()

    except Exception as e:
        print()
        error(str(e))
        print()
        print(f'{Colors.RED}Setup failed. Please check the error above.{Colors.NC}')
        print(f'{Colors.YELLOW}For help, visit: https://github.com/alex-feel/claude-code-toolbox{Colors.NC}')
        print()
        sys.exit(1)


if __name__ == '__main__':
    main()
