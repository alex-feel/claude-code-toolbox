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
import urllib.parse
from pathlib import Path
from typing import Any
from typing import cast
from urllib.request import Request
from urllib.request import urlopen

import yaml


# Helper function to detect if we're running in pytest
def is_running_in_pytest() -> bool:
    """Check if the script is running under pytest.

    Returns:
        True if running under pytest, False otherwise.
    """
    return 'pytest' in sys.modules or 'py.test' in sys.argv[0]


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


def check_file_with_head(url: str, auth_headers: dict[str, str] | None = None) -> bool:
    """Check if file exists using HEAD request.

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


def check_file_with_range(url: str, auth_headers: dict[str, str] | None = None) -> bool:
    """Check if file exists using Range request (first byte only).

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


def validate_file_availability(url: str, auth_headers: dict[str, str] | None = None) -> tuple[bool, str]:
    """Validate file availability using HEAD first, then Range as fallback.

    Args:
        url: URL to check
        auth_headers: Optional authentication headers

    Returns:
        Tuple of (is_available, method_used)
    """
    # Convert GitLab web URLs to API URLs for accurate validation
    # (same as done in fetch_url_with_auth during download)
    original_url = url
    if detect_repo_type(url) == 'gitlab' and '/-/raw/' in url:
        url = convert_gitlab_url_to_api(url)
        if url != original_url:
            info(f'Using API URL for validation: {url}')

    # Try HEAD request first
    if check_file_with_head(url, auth_headers):
        return (True, 'HEAD')

    # Fallback to Range request
    if check_file_with_range(url, auth_headers):
        return (True, 'Range')

    return (False, 'None')


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

    # Get authentication headers if needed
    auth_headers = None
    if config_source.startswith('http'):
        auth_headers = get_auth_headers(config_source, auth_param)

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

    # Output styles
    styles_raw = config.get('output-styles', [])
    if isinstance(styles_raw, list):
        # Cast to typed list for pyright
        styles_list = cast(list[object], styles_raw)
        for style_item in styles_list:
            if isinstance(style_item, str):
                resolved_path, is_remote = resolve_resource_path(style_item, config_source, base_url)
                files_to_check.append(('output_style', style_item, resolved_path, is_remote))

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

    # Validate each file
    info(f'Validating {len(files_to_check)} files...')
    all_valid = True

    for file_type, original_path, resolved_path, is_remote in files_to_check:
        if is_remote:
            # Validate remote URL
            is_valid, method = validate_file_availability(resolved_path, auth_headers)
            results.append((file_type, original_path, is_valid, method))

            if is_valid:
                info(f'  ✓ {file_type}: {original_path} (remote, validated via {method})')
            else:
                error(f'  ✗ {file_type}: {original_path} (remote, not accessible)')
                all_valid = False
        else:
            # Validate local file
            local_path = Path(resolved_path)
            if local_path.exists() and local_path.is_file():
                results.append((file_type, original_path, True, 'Local'))
                info(f'  ✓ {file_type}: {original_path} (local file exists)')
            else:
                results.append((file_type, original_path, False, 'Local'))
                error(f'  ✗ {file_type}: {original_path} (local file not found at {resolved_path})')
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

    # GitHub detection
    if 'github.com' in url_lower or 'api.github.com' in url_lower:
        return 'github'

    # Bitbucket detection (future expansion)
    if 'bitbucket' in url_lower:
        return 'bitbucket'

    return None


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
                header_name = 'Authorization'
                token = f'Bearer {token}' if not token.startswith('Bearer ') else token
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
            return {'Authorization': f'Bearer {env_token}'}

    # Check generic REPO_TOKEN as fallback
    env_token = os.environ.get('REPO_TOKEN')
    tokens_checked.append('REPO_TOKEN')
    if env_token:
        info('Using token from REPO_TOKEN environment variable')
        if repo_type == 'gitlab':
            return {'PRIVATE-TOKEN': env_token}
        if repo_type == 'github':
            return {'Authorization': f'Bearer {env_token}'}

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
                        return {'Authorization': f'Bearer {input_token}'}
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


def detect_user_shell() -> str:
    """Detect the user's configured shell.

    Returns:
        str: Shell name (e.g., 'bash', 'zsh', 'sh')
    """
    shell_path = os.environ.get('SHELL', '/bin/bash')
    return os.path.basename(shell_path)


def get_shell_config_file(shell_name: str, dual_shell: bool = False) -> Path | list[Path]:
    """Get the appropriate config file for shell environment variables.

    Args:
        shell_name: Name of the shell (e.g., 'bash', 'zsh')
        dual_shell: If True, return both bash and zsh config files for compatibility

    Returns:
        Path | list[Path]: Path to the appropriate shell config file(s)
    """
    home = Path.home()

    if dual_shell:
        # Return both bash and zsh config files for maximum compatibility
        return [home / '.bash_profile', home / '.zprofile']

    if shell_name == 'zsh':
        # Use .zprofile for environment variables in zsh
        # Note: .zprofile is loaded for login shells which is what Terminal.app opens
        return home / '.zprofile'
    if shell_name in ['bash', 'sh']:
        # Use .bash_profile for bash on macOS (Terminal.app opens login shells)
        return home / '.bash_profile'
    # Fallback for unknown shells
    return home / '.profile'


def translate_shell_commands(commands: list[str], target_shell: str | None = None, dual_shell: bool = False) -> list[str]:
    """Translate shell configuration commands to target shell config file.

    This function handles the translation of shell-specific commands, particularly
    for macOS where the user's actual shell might differ from what the configuration
    assumes (e.g., config writes to ~/.zshrc but user is using bash).

    Args:
        commands: List of shell commands to translate
        target_shell: Target shell name (auto-detected if None)
        dual_shell: If True, write to both bash and zsh config files for compatibility

    Returns:
        list[str]: Translated commands appropriate for the target shell
    """
    if target_shell is None:
        target_shell = detect_user_shell()

    config_files = get_shell_config_file(target_shell, dual_shell=dual_shell)
    if not isinstance(config_files, list):
        config_files = [config_files]

    translated: list[str] = []

    for cmd in commands:
        # Handle environment variable exports written to shell config files
        if any(pattern in cmd for pattern in ['>> ~/.zshrc', '>> ~/.zprofile', '>> ~/.bashrc', '>> ~/.bash_profile']):
            # For dual shell mode, write to all config files
            if dual_shell:
                for config_file in config_files:
                    # Extract the content being written
                    if '>>' in cmd:
                        parts = cmd.split('>>')
                        if len(parts) == 2:
                            content = parts[0].strip()
                            translated_cmd = f'{content} >> {config_file}'
                            translated.append(translated_cmd)
                            info(f'Writing to shell config: {config_file}')
            else:
                # Single shell mode - write to appropriate config file
                config_file = config_files[0]
                translated_cmd = cmd
                for pattern in ['~/.zshrc', '~/.zprofile', '~/.bashrc', '~/.bash_profile']:
                    translated_cmd = translated_cmd.replace(f'>> {pattern}', f'>> {config_file}')
                translated.append(translated_cmd)
                info(f'Translated shell config write to: {config_file}')
        elif 'exec zsh -l' in cmd:
            # Replace shell reload with appropriate command
            if dual_shell:
                # For dual shell, reload current shell
                translated.append(f'exec {target_shell} -l')
                info(f'Shell reload command for current shell: exec {target_shell} -l')
            elif target_shell == 'zsh':
                translated.append('exec zsh -l')
            elif target_shell == 'bash':
                translated.append('exec bash -l')
                info('Translated shell reload: exec zsh -l -> exec bash -l')
            else:
                translated.append(f'exec {target_shell} -l')
                info(f'Translated shell reload to: exec {target_shell} -l')
        elif 'exec bash -l' in cmd:
            # Handle bash reload commands
            if dual_shell:
                # For dual shell, reload current shell
                translated.append(f'exec {target_shell} -l')
                info(f'Shell reload command for current shell: exec {target_shell} -l')
            elif target_shell == 'zsh':
                translated.append('exec zsh -l')
                info('Translated shell reload: exec bash -l -> exec zsh -l')
            elif target_shell == 'bash':
                translated.append('exec bash -l')
            else:
                translated.append(f'exec {target_shell} -l')
                info(f'Translated shell reload to: exec {target_shell} -l')
        elif any(
            pattern in cmd
            for pattern in ['source ~/.zshrc', 'source ~/.zprofile', 'source ~/.bashrc', 'source ~/.bash_profile']
        ):
            # Handle source commands
            if dual_shell:
                # Source the current shell's config
                single_config = get_shell_config_file(target_shell, dual_shell=False)
                # Type guard: when dual_shell=False, it always returns a single Path
                assert isinstance(single_config, Path)
                translated.append(f'source {single_config}')
                info(f'Source command for current shell: source {single_config}')
            else:
                config_file = config_files[0]
                translated.append(f'source {config_file}')
                info(f'Translated source command to: source {config_file}')
        else:
            # Keep command as-is for non-shell-specific commands
            translated.append(cmd)

    return translated


def install_dependencies(dependencies: dict[str, list[str]] | None) -> bool:
    """Install dependencies from configuration."""
    if not dependencies:
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

    # Collect dependencies: common first, then platform-specific
    deps_to_install: list[str] = []

    # Add common dependencies
    common_deps = dependencies.get('common', [])
    if common_deps:
        info(f'Found {len(common_deps)} common dependencies')
        deps_to_install.extend(common_deps)

    # Add platform-specific dependencies
    if current_platform_key:
        platform_deps = dependencies.get(current_platform_key, [])
        if platform_deps:
            info(f'Found {len(platform_deps)} {current_platform_key}-specific dependencies')
            deps_to_install.extend(platform_deps)

    if not deps_to_install:
        info('No dependencies to install for this platform')
        return True

    # Execute all collected dependencies
    for dep in deps_to_install:
        info(f'Running: {dep}')
        result = None  # Initialize result for each dependency

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
                # For macOS, translate shell-specific commands based on user's actual shell
                if system == 'Darwin' and current_platform_key == 'mac':
                    # Detect if this is a shell config command that needs translation
                    if any(
                        pattern in dep
                        for pattern in [
                            '>> ~/.zshrc',
                            '>> ~/.zprofile',
                            '>> ~/.bashrc',
                            '>> ~/.bash_profile',
                            'exec zsh',
                            'exec bash',
                            'source ~/.zshrc',
                            'source ~/.bashrc',
                            'source ~/.zprofile',
                            'source ~/.bash_profile',
                        ]
                    ):
                        # Use dual-shell approach for better compatibility
                        # This writes to both bash and zsh config files
                        user_shell = detect_user_shell()
                        info(f'Detected user shell: {user_shell}')
                        info('Using dual-shell approach for maximum compatibility')
                        translated_deps = translate_shell_commands([dep], user_shell, dual_shell=True)
                        # Execute all translated commands (may be multiple for dual-shell)
                        for translated_dep in translated_deps:
                            info(f'Running: {translated_dep}')
                            result = run_command(['bash', '-c', translated_dep], capture_output=False)
                            if result.returncode != 0:
                                error(f'Failed to execute: {translated_dep}')
                                warning('Continuing with other dependencies...')
                    else:
                        # Non-shell config command, execute normally
                        result = run_command(['bash', '-c', dep], capture_output=False)
                else:
                    result = run_command(['bash', '-c', dep], capture_output=False)

        if result and result.returncode != 0:
            error(f'Failed to install dependency: {dep}')
            # Check if it failed due to admin rights on Windows
            if system == 'Windows' and not is_admin() and 'winget' in dep and '--scope machine' in dep:
                warning('This may have failed due to lack of admin rights')
                info('Try: 1) Run as administrator, or 2) Use --scope user instead')
            warning('Continuing with other dependencies...')

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


def resolve_output_style_name(
    output_style_ref: str,
    output_styles_dir: Path,
) -> str:
    """Resolve the actual output style name from the file's front matter.

    Args:
        output_style_ref: Reference to output style (filename without extension or style name)
        output_styles_dir: Directory containing output style files

    Returns:
        str: The actual style name from front matter, or cleaned reference as fallback
    """
    # Remove .md extension if present
    base_name = output_style_ref.replace('.md', '')

    # Try to find the output style file
    possible_files = [
        output_styles_dir / f'{base_name}.md',
        output_styles_dir / base_name,  # In case it's already a full filename
    ]

    for file_path in possible_files:
        if file_path.exists():
            # Try to extract name from front matter
            front_matter = extract_front_matter(file_path)
            if front_matter and 'name' in front_matter:
                resolved_name = front_matter['name']
                if resolved_name != base_name:
                    info(f'Resolved output style name: {base_name} → {resolved_name}')
                return str(resolved_name)
            warning(f'No front matter or name field in {file_path}, using filename')
            return base_name

    # File not found, return cleaned reference
    warning(f'Output style file not found for "{output_style_ref}", using as-is')
    return base_name


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
        return True

    info(f'Processing {resource_type}...')

    for resource in resources:
        # Strip query parameters from URL to get clean filename
        clean_resource = resource.split('?')[0] if '?' in resource else resource
        filename = Path(clean_resource).name
        destination = destination_dir / filename
        handle_resource(resource, destination, config_source, base_url, auth_param)

    return True


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

    This function addresses the Windows 10+ PATH propagation bug where MSI
    installations update the registry but the changes don't propagate to
    running processes immediately. We explicitly check for Node.js and
    update the current process PATH if needed.

    Returns:
        True if Node.js is available, False otherwise.
    """
    if platform.system() != 'Windows':
        return True  # Assume available on Unix

    nodejs_path = r'C:\Program Files\nodejs'
    node_exe = Path(nodejs_path) / 'node.exe'

    # Check binary exists
    if not node_exe.exists():
        error(f'Node.js binary not found at {node_exe}')
        return False

    # Check if node command works (3 attempts with 2s delay)
    for attempt in range(3):
        try:
            # Try with 'node' command
            result = subprocess.run(
                ['node', '--version'],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                success(f'Node.js verified: {result.stdout.strip()}')
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # Try with full path
            try:
                result = subprocess.run(
                    [str(node_exe), '--version'],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    # Works with full path, add to PATH
                    current_path = os.environ.get('PATH', '')
                    if nodejs_path not in current_path:
                        os.environ['PATH'] = f'{nodejs_path};{current_path}'
                        info(f'Added {nodejs_path} to PATH')
                    success(f'Node.js verified: {result.stdout.strip()}')
                    return True
            except Exception:
                pass

        if attempt < 2:
            info(f'Node.js not ready, waiting 2s... (attempt {attempt + 1}/3)')
            time.sleep(2)

    error('Node.js is not available')
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

        base_cmd.append(name)

        # Handle different transport types
        if transport and url:
            # HTTP or SSE transport
            base_cmd.extend(['--transport', transport, url])
            if header:
                base_cmd.extend(['--header', header])

            # Try with PowerShell environment reload on Windows
            if system == 'Windows':
                # Build explicit PATH including Node.js location
                # This fixes Windows 10+ PATH propagation bug where MSI registry updates
                # don't propagate to running processes via WM_SETTINGCHANGE
                nodejs_path = r'C:\Program Files\nodejs'
                current_path = os.environ.get('PATH', '')

                # Ensure Node.js is in PATH
                if Path(nodejs_path).exists() and nodejs_path not in current_path:
                    explicit_path = f'{nodejs_path};{current_path}'
                else:
                    explicit_path = current_path

                # On Windows, we need to spawn a completely new shell process
                # Use explicit PATH instead of reading from registry
                ps_script = f'''
$env:Path = "{explicit_path}"
& "{claude_cmd}" mcp add --scope {scope} --transport {transport} {name} {url}
$LASTEXITCODE
'''
                if header:
                    ps_script = f'''
$env:Path = "{explicit_path}"
& "{claude_cmd}" mcp add --scope {scope} --transport {transport} --header "{header}" {name} {url}
$LASTEXITCODE
'''
                result = run_command(
                    [
                        'powershell',
                        '-NoProfile',
                        '-Command',
                        ps_script,
                    ],
                    capture_output=True,
                )

                # Also try with direct execution
                if result.returncode != 0:
                    info('Trying direct execution...')
                    result = run_command(base_cmd, capture_output=True)
            else:
                # On Unix, spawn new bash with updated PATH
                parent_dir = Path(claude_cmd).parent
                bash_cmd = f'export PATH="{parent_dir}:$PATH" && {" ".join(base_cmd)}'
                result = run_command(
                    [
                        'bash',
                        '-l',
                        '-c',
                        bash_cmd,
                    ],
                    capture_output=True,
                )
        elif command:
            # Stdio transport (command)

            # Try with PowerShell environment reload on Windows
            if system == 'Windows':
                # Build explicit PATH including Node.js location
                # This fixes Windows 10+ PATH propagation bug where MSI registry updates
                # don't propagate to running processes via WM_SETTINGCHANGE
                nodejs_path = r'C:\Program Files\nodejs'
                current_path = os.environ.get('PATH', '')

                # Ensure Node.js is in PATH
                if Path(nodejs_path).exists() and nodejs_path not in current_path:
                    explicit_path = f'{nodejs_path};{current_path}'
                else:
                    explicit_path = current_path

                # Build command string with proper escaping for PowerShell
                # PowerShell uses backtick for escaping
                command_escaped = command.replace('"', '`"')

                # Special handling for npx (needs cmd /c wrapper on Windows)
                command_str = f'cmd /c {command_escaped}' if 'npx' in command else command_escaped

                # Build PowerShell script with explicit PATH
                if env:
                    ps_script = f'''
$env:Path = "{explicit_path}"
& "{claude_cmd}" mcp add --scope {scope} --env {env} {name} -- {command_str}
$LASTEXITCODE
'''
                else:
                    ps_script = f'''
$env:Path = "{explicit_path}"
& "{claude_cmd}" mcp add --scope {scope} {name} -- {command_str}
$LASTEXITCODE
'''
                result = run_command(
                    [
                        'powershell',
                        '-NoProfile',
                        '-Command',
                        ps_script,
                    ],
                    capture_output=True,
                )

                # Fallback to direct execution if PowerShell fails
                if result.returncode != 0:
                    info('PowerShell execution failed, trying direct execution...')
                    fallback_cmd = [str(claude_cmd), 'mcp', 'add', '--scope', scope]
                    if env:
                        fallback_cmd.extend(['--env', env])
                    fallback_cmd.extend([name, '--'])
                    fallback_cmd.extend(command.split())
                    result = run_command(fallback_cmd, capture_output=True)
            else:
                # Unix-like systems - direct execution
                base_cmd.extend(['--env', env] if env else [])
                base_cmd.extend([name, '--'])
                base_cmd.extend(command.split())
                result = run_command(base_cmd, capture_output=True)
        else:
            error(f'MCP server {name} missing url or command')
            return False

        # Check if successful
        if result.returncode == 0:
            success(f'MCP server {name} configured successfully!')
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
    command_name: str,
    output_style: str | None = None,
    model: str | None = None,
    permissions: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
    config_source: str | None = None,
    base_url: str | None = None,
    auth_param: str | None = None,
    output_styles_dir: Path | None = None,
    include_co_authored_by: bool | None = None,
) -> bool:
    """Create {command_name}-additional-settings.json with environment-specific settings.

    This file is always overwritten to avoid duplicate hooks when re-running the installer.
    It's loaded via --settings flag when launching Claude.

    Args:
        hooks: Hooks configuration dictionary with 'files' and 'events' keys
        claude_user_dir: Path to Claude user directory
        command_name: Name of the command for the environment-specific settings file
        output_style: Optional output style filename (without extension) to set as default
        model: Optional model alias or custom model name
        permissions: Optional permissions configuration dict
        env: Optional environment variables dict

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

    # Add output style if specified
    if output_style:
        # Resolve the actual style name from front matter
        if output_styles_dir:
            style_name = resolve_output_style_name(output_style, output_styles_dir)
        else:
            # If directory not provided, just strip .md extension
            style_name = output_style.replace('.md', '')

        settings['outputStyle'] = style_name
        info(f'Setting default output style: {style_name}')

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

    # Add includeCoAuthoredBy if explicitly set (None means not configured, leave as default)
    if include_co_authored_by is not None:
        settings['includeCoAuthoredBy'] = include_co_authored_by
        info(f'Setting includeCoAuthoredBy: {include_co_authored_by}')

    # Handle hooks if present
    hook_files: list[str] = []
    hook_events: list[dict[str, Any]] = []

    if hooks:
        settings['hooks'] = {}
        # Extract files and events from the hooks configuration
        hook_files = hooks.get('files', [])
        hook_events = hooks.get('events', [])

    # Process all hook files first
    if hook_files:
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
                full_command = f'uv run --python 3.12 {hook_path_str}'
            else:
                # Other file - build absolute path and use as-is
                # System will handle execution based on file extension (.sh, .bat, .cmd, .ps1, etc.)
                hook_path = claude_user_dir / 'hooks' / Path(clean_command).name
                hook_path_str = hook_path.as_posix()
                full_command = hook_path_str
        else:
            # Direct command with spaces - use as-is
            full_command = command

        # Add hook configuration
        hook_config: dict[str, str] = {
            'type': hook_type,
            'command': full_command,
        }
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
        success(f'Created {command_name}-additional-settings.json with environment hooks')
        return True
    except Exception as e:
        error(f'Failed to save {command_name}-additional-settings.json: {e}')
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
SETTINGS_WIN="$(cygpath -m "$HOME/.claude/{command_name}-additional-settings.json" 2>/dev/null ||
  echo "$HOME/.claude/{command_name}-additional-settings.json")"

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
                shared_sh_content = f'''#!/usr/bin/env bash
set -euo pipefail

# Get Windows path for settings
SETTINGS_WIN="$(cygpath -m "$HOME/.claude/{command_name}-additional-settings.json" 2>/dev/null ||
  echo "$HOME/.claude/{command_name}-additional-settings.json")"

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
    echo -e "\\033[1;33mPlease run setup_environment.py first\\033[0m"
    exit 1
fi

echo -e "\\033[0;32mStarting Claude Code with {command_name} configuration...\\033[0m"

# Read the prompt content
PROMPT_CONTENT=$(cat "$PROMPT_PATH")
SETTINGS_PATH="$CLAUDE_USER_DIR/{command_name}-additional-settings.json"

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
SETTINGS_PATH="$CLAUDE_USER_DIR/{command_name}-additional-settings.json"

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
                result = run_command(['setx', 'PATH', f'{local_bin_str};%PATH%'], capture_output=True)
                if result.returncode == 0:
                    success(f'Added {local_bin_str} to PATH')
                    info('You may need to restart your terminal for PATH changes to take effect')
                else:
                    warning(f'Failed to update PATH with setx: {result.stderr}')
                    if not is_admin():
                        info('This may be due to lack of admin rights or PATH length limits')
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

    try:
        # Load configuration from source (URL, local file, or repository)
        config, config_source = load_config_from_source(config_name, args.auth)

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
        command_name = config.get('command-name')  # No default - returns None if not present
        base_url = config.get('base-url')  # Optional base URL override from config

        # Extract command defaults
        command_defaults = config.get('command-defaults', {})
        output_style = command_defaults.get('output-style')
        system_prompt = command_defaults.get('system-prompt')

        # Extract model configuration
        model = config.get('model')

        # Extract permissions configuration
        permissions = config.get('permissions')

        # Extract environment variables configuration
        env_variables = config.get('env-variables')

        # Extract include_co_authored_by configuration
        include_co_authored_by = config.get('include-co-authored-by')

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
        output_styles_dir = claude_user_dir / 'output-styles'
        hooks_dir = claude_user_dir / 'hooks'

        # Step 1: Install Claude Code if needed (MUST be first - provides uv, git bash, node)
        if not args.skip_install:
            print(f'{Colors.CYAN}Step 1: Installing Claude Code...{Colors.NC}')
            if not install_claude(claude_code_version_normalized):
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
        dependencies = config.get('dependencies', {})
        install_dependencies(dependencies)

        # Step 4: Process agents
        print()
        print(f'{Colors.CYAN}Step 4: Processing agents...{Colors.NC}')
        agents = config.get('agents', [])
        process_resources(agents, agents_dir, 'agents', config_source, base_url, args.auth)

        # Step 5: Process slash commands
        print()
        print(f'{Colors.CYAN}Step 5: Processing slash commands...{Colors.NC}')
        commands = config.get('slash-commands', [])
        process_resources(commands, commands_dir, 'slash commands', config_source, base_url, args.auth)

        # Step 6: Process output styles
        print()
        print(f'{Colors.CYAN}Step 6: Processing output styles...{Colors.NC}')
        output_styles = config.get('output-styles', [])
        if output_styles:
            process_resources(output_styles, output_styles_dir, 'output styles', config_source, base_url, args.auth)
        else:
            info('No output styles configured')

        # Step 7: Process system prompt (if specified)
        print()
        print(f'{Colors.CYAN}Step 7: Processing system prompt...{Colors.NC}')
        prompt_path = None
        if system_prompt:
            # Strip query parameters from URL to get clean filename
            clean_prompt = system_prompt.split('?')[0] if '?' in system_prompt else system_prompt
            sys_prompt_filename = Path(clean_prompt).name
            prompt_path = prompts_dir / sys_prompt_filename
            handle_resource(system_prompt, prompt_path, config_source, base_url, args.auth)
        else:
            info('No additional system prompt configured')

        # Step 8: Configure MCP servers
        print()
        print(f'{Colors.CYAN}Step 8: Configuring MCP servers...{Colors.NC}')
        mcp_servers = config.get('mcp-servers', [])

        # Verify Node.js is available before configuring MCP servers
        # This ensures Node.js PATH is properly set after MSI installation
        if mcp_servers and platform.system() == 'Windows' and not verify_nodejs_available():
            warning('Node.js not available - MCP server configuration may fail')
            warning('Please ensure Node.js is installed and in PATH')
            # Don't fail hard, let user see the issue

        configure_all_mcp_servers(mcp_servers)

        # Check if command creation is needed
        if command_name:
            # Step 9: Configure hooks and output style
            print()
            print(f'{Colors.CYAN}Step 9: Configuring hooks and settings...{Colors.NC}')
            hooks = config.get('hooks', {})
            create_additional_settings(
                hooks,
                claude_user_dir,
                command_name,
                output_style,
                model,
                permissions,
                env_variables,
                config_source,
                base_url,
                args.auth,
                output_styles_dir,
                include_co_authored_by,
            )

            # Step 10: Create launcher script
            print()
            print(f'{Colors.CYAN}Step 10: Creating launcher script...{Colors.NC}')
            # Strip query parameters from system prompt filename (must match download logic)
            prompt_filename: str | None = None
            if system_prompt:
                clean_prompt = system_prompt.split('?')[0] if '?' in system_prompt else system_prompt
                prompt_filename = Path(clean_prompt).name
            launcher_path = create_launcher_script(claude_user_dir, command_name, prompt_filename)

            # Step 11: Register global command
            if launcher_path:
                print()
                print(f'{Colors.CYAN}Step 11: Registering global {command_name} command...{Colors.NC}')
                register_global_command(launcher_path, command_name)
            else:
                warning('Launcher script was not created')
        else:
            # Skip command creation
            print()
            print(f'{Colors.CYAN}Steps 9-11: Skipping command creation (no command-name specified)...{Colors.NC}')
            info('Environment configuration completed successfully')
            info('To create a custom command, add "command-name: your-command-name" to your config')

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
        # Only show hooks count if command_name was specified (hooks was defined)
        if command_name:
            hooks = config.get('hooks', {})
            print(f"   * Hooks: {len(hooks.get('events', [])) if hooks else 0} configured")
            print(f'   * Global command: {command_name} registered')
        else:
            print('   * Custom command: Not created (no command-name specified)')

        print()
        print(f'{Colors.YELLOW}Quick Start:{Colors.NC}')
        if command_name:
            print(f'   * Global command: {command_name}')
        else:
            print('   * Use "claude" to start Claude Code with configured environment')

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
