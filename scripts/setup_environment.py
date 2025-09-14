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
import urllib.request
from pathlib import Path
from typing import Any
from urllib.request import Request
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
            return response.status == 200
        except urllib.error.URLError as e:
            if 'SSL' in str(e) or 'certificate' in str(e).lower():
                # Try with unverified SSL context
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                response = urlopen(request, context=ctx)
                return response.status == 200
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
    files_to_check = []
    results = []

    # Get authentication headers if needed
    auth_headers = None
    if config_source.startswith('http'):
        auth_headers = get_auth_headers(config_source, auth_param)

    # Collect all files that need to be validated
    base_url = config.get('base-url')

    # Agents
    for agent in config.get('agents', []) or []:
        resolved_path, is_remote = resolve_resource_path(agent, config_source, base_url)
        files_to_check.append(('agent', agent, resolved_path, is_remote))

    # Slash commands
    for cmd in config.get('slash-commands', []) or []:
        resolved_path, is_remote = resolve_resource_path(cmd, config_source, base_url)
        files_to_check.append(('slash_command', cmd, resolved_path, is_remote))

    # Output styles
    for style in config.get('output-styles', []) or []:
        resolved_path, is_remote = resolve_resource_path(style, config_source, base_url)
        files_to_check.append(('output_style', style, resolved_path, is_remote))

    # System prompts from command-defaults
    command_defaults = config.get('command-defaults', {})
    if command_defaults and command_defaults.get('system-prompt'):
        prompt = command_defaults['system-prompt']
        resolved_path, is_remote = resolve_resource_path(prompt, config_source, base_url)
        files_to_check.append(('system_prompt', prompt, resolved_path, is_remote))

    # Hooks files
    hooks = config.get('hooks', {})
    if hooks:
        for hook_file in hooks.get('files', []) or []:
            resolved_path, is_remote = resolve_resource_path(hook_file, config_source, base_url)
            files_to_check.append(('hook', hook_file, resolved_path, is_remote))

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
            path = base_url[domain_end + 1:]  # Skip the /
        elif base_url.startswith('http://'):
            domain_end = base_url.index('/', 7)  # Find end of domain after http://
            domain = base_url[:domain_end]
            path = base_url[domain_end + 1:]  # Skip the /
        else:
            return url  # Unknown format

        # Split the path by /-/raw/
        parts = path.split('/-/raw/')
        if len(parts) != 2:
            return url  # Unexpected format

        project_path = parts[0]  # e.g., "ai/claude-code-configs"
        remainder = parts[1]     # e.g., "main/environments/library/file.yaml"

        # Split remainder into branch and file path
        # The branch is the first part before /
        branch_end = remainder.find('/')
        if branch_end == -1:
            # No file path, just branch
            branch = remainder
            file_path = ''
        else:
            branch = remainder[:branch_end]
            file_path = remainder[branch_end + 1:]

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
    tokens_checked = []

    # Check repo-specific tokens first
    if repo_type == 'gitlab':
        token = os.environ.get('GITLAB_TOKEN')
        tokens_checked.append('GITLAB_TOKEN')
        if token:
            info('Using GitLab token from GITLAB_TOKEN environment variable')
            return {'PRIVATE-TOKEN': token}
    elif repo_type == 'github':
        token = os.environ.get('GITHUB_TOKEN')
        tokens_checked.append('GITHUB_TOKEN')
        if token:
            info('Using GitHub token from GITHUB_TOKEN environment variable')
            return {'Authorization': f'Bearer {token}'}

    # Check generic REPO_TOKEN as fallback
    token = os.environ.get('REPO_TOKEN')
    tokens_checked.append('REPO_TOKEN')
    if token:
        info('Using token from REPO_TOKEN environment variable')
        if repo_type == 'gitlab':
            return {'PRIVATE-TOKEN': token}
        if repo_type == 'github':
            return {'Authorization': f'Bearer {token}'}

    # Method 3: Auth config file (future expansion)
    # auth_file = Path.home() / '.claude' / 'auth.yaml'
    # if auth_file.exists():
    #     # Implementation for auth file would go here
    #     pass

    # Method 4: Interactive prompt (only if repo type detected and terminal is interactive)
    if repo_type and sys.stdin.isatty():
        warning(f'Private {repo_type.title()} repository detected but no authentication found')
        info(f'Checked environment variables: {", ".join(tokens_checked)}')
        info('You can provide authentication by:')
        info(f'  1. Setting environment variable: {tokens_checked[0]}')
        info('  2. Using --auth parameter: --auth "token_here"')

        # Ask if they want to enter it now
        try:
            response = input('Would you like to enter the token now? (y/N): ').strip().lower()
            if response == 'y':
                import getpass
                token = getpass.getpass(f'Enter {repo_type.title()} token (will not echo): ')
                if token:
                    if repo_type == 'gitlab':
                        return {'PRIVATE-TOKEN': token}
                    if repo_type == 'github':
                        return {'Authorization': f'Bearer {token}'}
        except (KeyboardInterrupt, EOFError):
            print()  # New line after Ctrl+C
    elif repo_type:
        # Non-interactive terminal but auth might be needed
        info(f'Private {repo_type.title()} repository detected')
        info(f'If authentication is required, set one of: {", ".join(tokens_checked)}')

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
            warning('⚠️  Loading configuration from remote URL')
            warning('⚠️  Only use configs from trusted sources!')

        try:
            content = fetch_url_with_auth(config_spec, auth_param=auth_param)
            config = yaml.safe_load(content)
            success(f'Configuration loaded from URL: {config.get("name", "Remote Config")}')
            return config, config_spec
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
        success(f'Configuration loaded: {config.get("name", config_spec)}')
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
        return response.read().decode('utf-8')
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
                    return response.read().decode('utf-8')
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
            return response.read().decode('utf-8')
        raise


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


def install_claude() -> bool:
    """Install Claude Code if needed."""
    info('Installing Claude Code...')

    system = platform.system()

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
            result = run_command([
                'powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                '-File', temp_installer,
            ], capture_output=False)

        elif system == 'Darwin':  # macOS
            installer_url = 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/install-claude-macos.sh'
            result = run_command([
                'bash', '-c',
                f'curl -fsSL {installer_url} | bash',
            ], capture_output=False)

        else:  # Linux
            installer_url = 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/install-claude-linux.sh'
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
    command_name: str,
    output_style: str | None = None,
    mcp_servers: list[dict[str, Any]] | None = None,
    model: str | None = None,
    permissions: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
    config_source: str | None = None,
    base_url: str | None = None,
    auth_param: str | None = None,
) -> bool:
    """Create {command_name}-additional-settings.json with environment-specific settings.

    This file is always overwritten to avoid duplicate hooks when re-running the installer.
    It's loaded via --settings flag when launching Claude.

    Args:
        hooks: Hooks configuration dictionary with 'files' and 'events' keys
        claude_user_dir: Path to Claude user directory
        command_name: Name of the command for the environment-specific settings file
        output_style: Optional output style filename (without extension) to set as default
        mcp_servers: Optional list of MCP server configurations to pre-allow
        model: Optional model alias or custom model name
        permissions: Optional permissions configuration dict
        env: Optional environment variables dict

    Returns:
        bool: True if successful, False otherwise.
    """
    info(f'Creating {command_name}-additional-settings.json...')

    # Create fresh settings structure for this environment
    settings = {}

    # Add model if specified
    if model:
        settings['model'] = model
        info(f'Setting model: {model}')

    # Add output style if specified
    if output_style:
        # Remove .md extension if present
        style_name = output_style.replace('.md', '')
        settings['outputStyle'] = style_name
        info(f'Setting default output style: {style_name}')

    # Handle permissions with smart MCP server auto-allowing
    final_permissions = {}

    # Start with env config permissions if provided
    if permissions:
        final_permissions = permissions.copy()
        info('Using permissions from environment configuration')

    # Auto-allow MCP servers if not explicitly mentioned in permissions
    if mcp_servers:
        # Get existing allow list from env config (or create empty)
        existing_allow = final_permissions.get('allow', [])
        existing_deny = final_permissions.get('deny', [])

        # Convert to sets for efficient lookups
        allow_set = set(existing_allow) if isinstance(existing_allow, list) else set()

        for server in mcp_servers:
            if isinstance(server, dict) and 'name' in server:
                server_permission = f"mcp__{server['name']}"

                # Check if this server is explicitly mentioned anywhere in permissions
                server_mentioned = False

                # Check in allow list
                if any(server_permission in str(item) for item in existing_allow):
                    server_mentioned = True
                    info(f'MCP server {server["name"]} already in allow list')

                # Check in deny list
                if any(server_permission in str(item) for item in existing_deny):
                    server_mentioned = True
                    warning(f'MCP server {server["name"]} is in deny list - not auto-allowing')

                # Check in ask list
                existing_ask = final_permissions.get('ask', [])
                if any(server_permission in str(item) for item in existing_ask):
                    server_mentioned = True
                    info(f'MCP server {server["name"]} is in ask list - not auto-allowing')

                # Only auto-allow if not mentioned anywhere
                if not server_mentioned:
                    allow_set.add(server_permission)
                    info(f'Auto-allowing MCP server: {server["name"]}')

        # Update allow list if we added any
        if allow_set:
            final_permissions['allow'] = list(allow_set)

    # Add permissions to settings if we have any
    if final_permissions:
        settings['permissions'] = final_permissions

    # Add environment variables if specified
    if env:
        settings['env'] = env
        info(f'Setting {len(env)} environment variables')
        for key in env:
            info(f'  - {key}')

    # Handle hooks if present
    hook_files = []
    hook_events = []

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
            # Strip query parameters from command if present
            clean_command = command.split('?')[0] if '?' in command else command
            hook_path = claude_user_dir / 'hooks' / Path(clean_command).name

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
    parser.add_argument('--auth', type=str,
                        help='Authentication for private repos (e.g., "token" or "header:token")')
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

        environment_name = config.get('name', 'Development')
        command_name = config.get('command-name', 'claude-env')
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
            prompt_filename = Path(clean_prompt).name
            prompt_path = prompts_dir / prompt_filename
            handle_resource(system_prompt, prompt_path, config_source, base_url, args.auth)
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
        create_additional_settings(
            hooks, claude_user_dir, command_name, output_style, mcp_servers, model, permissions, env_variables,
            config_source, base_url, args.auth,
        )

        # Step 10: Create launcher script
        print()
        print(f'{Colors.CYAN}Step 10: Creating launcher script...{Colors.NC}')
        # Strip query parameters from system prompt filename (must match download logic)
        if system_prompt:
            clean_prompt = system_prompt.split('?')[0] if '?' in system_prompt else system_prompt
            prompt_filename = Path(clean_prompt).name
        else:
            prompt_filename = None
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
        if model:
            print(f'   * Model: {model}')
        print(f'   * MCP servers: {len(mcp_servers)} configured')
        if permissions:
            perm_items = []
            if 'defaultMode' in permissions:
                perm_items.append(f"defaultMode={permissions['defaultMode']}")
            if 'allow' in permissions:
                perm_items.append(f"{len(permissions['allow'])} allow rules")
            if 'deny' in permissions:
                perm_items.append(f"{len(permissions['deny'])} deny rules")
            if 'ask' in permissions:
                perm_items.append(f"{len(permissions['ask'])} ask rules")
            if perm_items:
                print(f'   * Permissions: {", ".join(perm_items)}')
        if env_variables:
            print(f'   * Environment variables: {len(env_variables)} configured')
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
