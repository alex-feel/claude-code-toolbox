"""
Cross-platform Python environment setup for Claude Code.
Downloads and configures Python development tools for Claude Code.
"""

import argparse
import contextlib
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
CONTEXT7_MCP_URL = 'https://mcp.context7.com/mcp'

# List of subagents mentioned in python-developer.md
AGENTS = [
    'code-reviewer',
    'doc-writer',
    'implementation-guide',
    'performance-optimizer',
    'refactoring-assistant',
    'security-auditor',
    'test-generator',
]

# List of slash commands from slash-commands/examples/
COMMANDS = [
    'commit',
    'debug',
    'document',
    'refactor',
    'review',
    'test',
]


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


def header() -> None:
    """Print setup header."""
    print()
    print(f'{Colors.BLUE}========================================================================{Colors.NC}')
    print(f'{Colors.BLUE}     Claude Code Python Environment Setup{Colors.NC}')
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


def download_file(url: str, destination: Path, force: bool = False) -> bool:
    """Download a file from URL to destination."""
    filename = destination.name

    # Check if file exists and handle force parameter
    if destination.exists() and not force:
        info(f'File already exists: {filename} (use --force to overwrite)')
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


def configure_mcp_server() -> bool:
    """Configure Context7 MCP server."""
    info('Configuring Context7 MCP server...')

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
        # Run the MCP configuration using the full path to claude
        info(f'Running MCP configuration with: {claude_cmd}')

        if system == 'Windows':
            # On Windows, we need to spawn a completely new shell process
            # Use start /wait to spawn a new cmd window and wait for it
            ps_script = f'''
$userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
$machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
$env:Path = $userPath + ";" + $machinePath
& "{claude_cmd}" mcp add --scope user --transport http context7 {CONTEXT7_MCP_URL}
$LASTEXITCODE
'''
            result = run_command([
                'powershell', '-NoProfile', '-Command', ps_script,
            ], capture_output=True)

            # Also try with direct execution
            if result.returncode != 0:
                info('Trying direct execution...')
                result = run_command([
                    str(claude_cmd), 'mcp', 'add',
                    '--transport', 'http',
                    'context7', CONTEXT7_MCP_URL,
                ], capture_output=True)
        else:
            # On Unix, spawn new bash with updated PATH
            parent_dir = Path(claude_cmd).parent
            bash_cmd = (
                f'export PATH="{parent_dir}:$PATH" && '
                f'{claude_cmd} mcp add --scope user --transport http context7 {CONTEXT7_MCP_URL}'
            )
            result = run_command([
                'bash', '-l', '-c', bash_cmd,
            ], capture_output=True)

        # Check if successful
        if result.returncode == 0:
            success('Context7 MCP server configured successfully!')
            return True
        if result.stderr and 'already exists' in result.stderr.lower():
            success('Context7 MCP server already configured!')
            return True
        # If it still fails, try one more time with a delay
        info('First attempt failed, waiting 2 seconds and retrying...')
        time.sleep(2)

        # Direct execution with full path
        result = run_command([
            str(claude_cmd), 'mcp', 'add',
            '--transport', 'http',
            'context7', CONTEXT7_MCP_URL,
        ], capture_output=False)  # Show output for debugging

        if result.returncode == 0:
            success('Context7 MCP server configured successfully!')
            return True
        error(f'MCP configuration failed with exit code: {result.returncode}')
        if result.stderr:
            error(f'Error: {result.stderr}')
        return False

    except Exception as e:
        error(f'Failed to configure MCP server: {e}')
        return False


def create_launcher_script(claude_user_dir: Path) -> Path | None:
    """Create launcher script for starting Claude with Python prompt."""
    launcher_path = claude_user_dir / 'start-python-claude'

    system = platform.system()

    try:
        if system == 'Windows':
            # PowerShell launcher
            launcher_path = launcher_path.with_suffix('.ps1')
            launcher_content = '''# Claude Code Python Environment Launcher
# This script starts Claude Code with the Python developer system prompt

$claudeUserDir = Join-Path $env:USERPROFILE ".claude"
$promptPath = Join-Path $claudeUserDir "prompts\\python-developer.md"

if (-not (Test-Path $promptPath)) {
    Write-Host "Error: Python developer prompt not found at $promptPath" -ForegroundColor Red
    Write-Host "Please run setup-python-environment.py first" -ForegroundColor Yellow
    exit 1
}

Write-Host "Starting Claude Code with Python developer configuration..." -ForegroundColor Green
& claude --append-system-prompt "@$promptPath" $args
'''
            launcher_path.write_text(launcher_content)

            # Also create a batch file wrapper
            batch_path = claude_user_dir / 'start-python-claude.cmd'
            batch_content = f'@echo off\npowershell -NoProfile -ExecutionPolicy Bypass -File "{launcher_path}" %*'
            batch_path.write_text(batch_content)

        else:
            # Bash launcher
            launcher_path = launcher_path.with_suffix('.sh')
            launcher_content = '''#!/usr/bin/env bash
# Claude Code Python Environment Launcher
# This script starts Claude Code with the Python developer system prompt

CLAUDE_USER_DIR="$HOME/.claude"
PROMPT_PATH="$CLAUDE_USER_DIR/prompts/python-developer.md"

if [ ! -f "$PROMPT_PATH" ]; then
    echo -e "\\033[0;31mError: Python developer prompt not found at $PROMPT_PATH\\033[0m"
    echo -e "\\033[1;33mPlease run setup-python-environment.py first\\033[0m"
    exit 1
fi

echo -e "\\033[0;32mStarting Claude Code with Python developer configuration...\\033[0m"
claude --append-system-prompt "@$PROMPT_PATH" "$@"
'''
            launcher_path.write_text(launcher_content)
            launcher_path.chmod(0o755)

        success('Created launcher script')
        return launcher_path

    except Exception as e:
        warning(f'Failed to create launcher script: {e}')
        return None


def register_global_command(launcher_path: Path) -> bool:
    """Register global claude-python command."""
    info('Registering global claude-python command...')

    system = platform.system()

    try:
        if system == 'Windows':
            # Create batch file in .local/bin
            local_bin = Path.home() / '.local' / 'bin'
            local_bin.mkdir(parents=True, exist_ok=True)

            batch_path = local_bin / 'claude-python.cmd'
            batch_content = f'@echo off\npowershell -NoProfile -ExecutionPolicy Bypass -File "{launcher_path}" %*'
            batch_path.write_text(batch_content)

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

            symlink_path = local_bin / 'claude-python'
            if symlink_path.exists():
                symlink_path.unlink()
            symlink_path.symlink_to(launcher_path)

            # Ensure ~/.local/bin is in PATH
            info('Make sure ~/.local/bin is in your PATH')
            info('Add this to your ~/.bashrc or ~/.zshrc if needed:')
            info('  export PATH="$HOME/.local/bin:$PATH"')

        success('Created global command: claude-python')
        return True

    except Exception as e:
        warning(f'Failed to register global command: {e}')
        return False


def main() -> None:
    """Main setup flow."""
    parser = argparse.ArgumentParser(description='Setup Python development environment for Claude Code')
    parser.add_argument('--skip-install', action='store_true',
                        help='Skip Claude Code installation')
    parser.add_argument('--force', action='store_true',
                        help='Force overwrite existing files')
    args = parser.parse_args()

    header()

    system = platform.system()

    # Set up directories
    home = Path.home()
    claude_user_dir = home / '.claude'
    agents_dir = claude_user_dir / 'agents'
    commands_dir = claude_user_dir / 'commands'
    prompts_dir = claude_user_dir / 'prompts'

    try:
        # Step 1: Install Claude Code if needed
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
        for dir_path in [claude_user_dir, agents_dir, commands_dir, prompts_dir]:
            if dir_path.mkdir(parents=True, exist_ok=True):
                success(f'Created: {dir_path}')

        # Step 3: Download subagents
        print()
        print(f'{Colors.CYAN}Step 3: Downloading Python-optimized subagents...{Colors.NC}')
        for agent in AGENTS:
            url = f'{REPO_BASE_URL}/agents/examples/{agent}.md'
            destination = agents_dir / f'{agent}.md'
            download_file(url, destination, args.force)

        # Step 4: Download slash commands
        print()
        print(f'{Colors.CYAN}Step 4: Downloading slash commands...{Colors.NC}')
        for command in COMMANDS:
            url = f'{REPO_BASE_URL}/slash-commands/examples/{command}.md'
            destination = commands_dir / f'{command}.md'
            download_file(url, destination, args.force)

        # Step 5: Download Python developer system prompt
        print()
        print(f'{Colors.CYAN}Step 5: Downloading Python developer system prompt...{Colors.NC}')
        prompt_url = f'{REPO_BASE_URL}/system-prompts/examples/python-developer.md'
        prompt_path = prompts_dir / 'python-developer.md'
        download_file(prompt_url, prompt_path, args.force)

        # Step 6: Configure Context7 MCP server
        print()
        print(f'{Colors.CYAN}Step 6: Configuring Context7 MCP server...{Colors.NC}')
        mcp_configured = configure_mcp_server()

        # Step 7: Create launcher script
        print()
        print(f'{Colors.CYAN}Step 7: Creating launcher script...{Colors.NC}')
        launcher_path = create_launcher_script(claude_user_dir)

        # Step 8: Register global command
        if launcher_path:
            print()
            print(f'{Colors.CYAN}Step 8: Registering global claude-python command...{Colors.NC}')
            register_global_command(launcher_path)

        # Final message
        print()
        print(f'{Colors.GREEN}========================================================================{Colors.NC}')
        print(f'{Colors.GREEN}                    Setup Complete!{Colors.NC}')
        print(f'{Colors.GREEN}========================================================================{Colors.NC}')
        print()

        print(f'{Colors.YELLOW}Summary:{Colors.NC}')
        print(f"   * Claude Code installation: {'Skipped' if args.skip_install else 'Completed'}")
        print(f'   * Python subagents: {len(AGENTS)} installed')
        print(f'   * Slash commands: {len(COMMANDS)} installed')
        print('   * System prompt: Configured')
        if 'mcp_configured' in locals() and mcp_configured:
            print('   * MCP server: Context7 configured')
        else:
            print('   * MCP server: Manual configuration needed (see instructions above)')
        print('   * Global command: claude-python registered')

        print()
        print(f'{Colors.YELLOW}Quick Start:{Colors.NC}')
        print('   * Global command: claude-python')
        if launcher_path:
            if system == 'Windows':
                print(f"   * Full path: powershell -File '{launcher_path}'")
            else:
                print(f'   * Full path: {launcher_path}')
        print(f"   * Manual: claude --append-system-prompt '@{prompt_path}'")

        print()
        print(f"{Colors.YELLOW}What's Installed:{Colors.NC}")
        print('   * 7 Python-optimized subagents (code review, testing, docs, etc.)')
        print('   * 6 custom slash commands (/commit, /debug, /test, etc.)')
        if 'mcp_configured' in locals() and mcp_configured:
            print('   * Context7 MCP server for up-to-date library documentation')
        else:
            print('   * Context7 MCP server (pending manual configuration)')
        print('   * Comprehensive Python development system prompt')

        print()
        print(f'{Colors.YELLOW}Available Commands (after starting Claude):{Colors.NC}')
        print('   * /help - See all available commands')
        print('   * /agents - List available subagents')
        print('   * /commit - Smart Git commits')

        print()
        print(f'{Colors.YELLOW}Examples:{Colors.NC}')
        print('   claude-python')
        print('   > Create a FastAPI app with async SQLAlchemy and pytest')
        print()
        print('   claude-python')
        print('   > /commit fix: resolve database connection pooling issue')

        print()
        print(f'{Colors.YELLOW}Documentation:{Colors.NC}')
        print('   * Python Setup Guide: https://github.com/alex-feel/claude-code-toolbox/blob/main/docs/python-setup.md')
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
