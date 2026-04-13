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
import concurrent.futures
import contextlib
import glob as glob_module
import http.client
import json
import os
import platform
import random
import re
import shlex
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field
from datetime import UTC
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import NamedTuple
from typing import TextIO
from typing import TypeVar
from typing import cast
from urllib.request import Request
from urllib.request import urlopen
from urllib.request import urlretrieve

import yaml

# Import pwd module for Unix-like systems (used for detecting real user home under sudo)
# The import happens here but pwd is used in get_real_user_home() function
if sys.platform != 'win32':
    pass  # Used in get_real_user_home() for resolving sudo user's home directory

# Configuration inheritance constants
MAX_INHERITANCE_DEPTH = 10
INHERIT_KEY = 'inherit'
MERGE_KEYS_KEY = 'merge-keys'

# Keys eligible for selective merge during configuration inheritance.
# Only these top-level keys can be listed in the `merge-keys` directive.
MERGEABLE_CONFIG_KEYS: frozenset[str] = frozenset({
    'dependencies',
    'agents',
    'slash-commands',
    'rules',
    'skills',
    'files-to-download',
    'hooks',
    'mcp-servers',
    'global-config',
    'user-settings',
    'env-variables',
    'os-env-variables',
})

# Config keys containing file references (paths or URLs) that require
# resolution and validation. Used as a single source of truth for maintenance.
# Dot notation indicates nested keys (e.g., 'hooks.files' = hooks['files']).
#
# Access patterns differ per key type (simple list, dict-nested list,
# dict-nested scalar), so this constant serves as a registry, not a
# dispatch mechanism. validate_all_config_files() and
# _resolve_config_file_paths() handle type-specific extraction logic.
FILE_REFERENCE_KEYS: frozenset[str] = frozenset({
    'agents',                        # list[str] -- simple string list
    'slash-commands',                 # list[str] -- simple string list
    'rules',                         # list[str] -- simple string list
    'hooks.files',                   # list[str] -- nested under hooks dict
    'files-to-download',             # list[dict] -- each dict has 'source' key
    'skills',                        # list[dict] -- each dict has 'base' key
    'command-defaults.system-prompt',  # str -- nested scalar under command-defaults
})

# Node.js installation constants (standalone -- no imports from install_claude.py)
MIN_NODE_VERSION = '18.0.0'
NODE_LTS_API = 'https://nodejs.org/dist/index.json'

# All valid top-level configuration keys for unknown key detection
KNOWN_CONFIG_KEYS: frozenset[str] = frozenset({
    'name',
    'version',
    'inherit',
    'merge-keys',
    'command-names',
    'base-url',
    'claude-code-version',
    'install-nodejs',
    'dependencies',
    'description',
    'agents',
    'slash-commands',
    'rules',
    'skills',
    'files-to-download',
    'global-config',
    'hooks',
    'mcp-servers',
    'model',
    'permissions',
    'post-install-notes',
    'env-variables',
    'os-env-variables',
    'command-defaults',
    'user-settings',
    'always-thinking-enabled',
    'effort-level',
    'company-announcements',
    'attribution',
    'status-line',
})

# Path prefixes indicating sensitive filesystem destinations
SENSITIVE_PATH_PREFIXES: tuple[str, ...] = (
    '~/.ssh/',
    '~/.gnupg/',
    '~/.bashrc',
    '~/.bash_profile',
    '~/.profile',
    '~/.zshrc',
    '~/.config/',
)

# Mapping from platform.system() return values to dependency config keys.
# Used by collect_installation_plan(), install_dependencies(), and check_admin_needed()
# to determine which platform-specific dependencies apply to the current OS.
PLATFORM_SYSTEM_TO_CONFIG_KEY: dict[str, str] = {
    'Windows': 'windows',
    'Darwin': 'macos',
    'Linux': 'linux',
}

# OS environment variables constants
OS_ENV_VARIABLES_KEY = 'os-env-variables'
ENV_VAR_MARKER_START = '# >>> claude-code-toolbox >>>'
ENV_VAR_MARKER_END = '# <<< claude-code-toolbox <<<'

# Per-path union whitelist used ONLY by the YAML inheritance layer
# (_resolve_single_key at lines 4331 and 4337) for child-overrides-parent
# composition semantics. On-disk writers (write_user_settings(),
# write_profile_settings_to_settings(), write_global_config()) use the
# default universal union-all-arrays semantics via
# _write_merged_json(array_union_keys=None) -- every array at every depth
# is unioned with structural dedupe, matching Claude Code CLI's
# cross-scope merge behavior.
DEFAULT_ARRAY_UNION_KEYS: set[str] = {
    'permissions.allow',
    'permissions.deny',
    'permissions.ask',
}

# Keys that contain shell commands requiring tilde expansion
# These keys may reference file paths that need ~ expanded to absolute paths
# Uses expand_tildes_in_command() for consistent expansion (DRY with commit 46a086b)
TILDE_EXPANSION_KEYS: set[str] = {
    'apiKeyHelper',
    'awsCredentialExport',
}

# Keys that are NOT allowed in the user-settings section
# These keys have path resolution issues or are inherently profile-specific
USER_SETTINGS_EXCLUDED_KEYS: set[str] = {
    'hooks',       # Hooks require dedicated write logic with path resolution and type processing
    'statusLine',  # Path resolution issues; profile-specific display config
}

# Keys that are NOT allowed in the global-config section
# OAuth credentials must not appear in version-controlled YAML files
GLOBAL_CONFIG_EXCLUDED_KEYS: frozenset[str] = frozenset({
    'oauthAccount',
})

# Mapping from root-level YAML keys to their user-settings equivalents
# Used for conflict detection between profile settings and user settings
# Root keys use kebab-case, user-settings uses camelCase (matching JSON schema)
ROOT_TO_USER_SETTINGS_KEY_MAP: dict[str, str] = {
    'model': 'model',                           # Same in both
    'permissions': 'permissions',               # Same in both
    'attribution': 'attribution',               # Same in both
    'always-thinking-enabled': 'alwaysThinkingEnabled',
    'company-announcements': 'companyAnnouncements',
    'env-variables': 'env',                     # Different names
    'effort-level': 'effortLevel',              # Adaptive reasoning effort
}

# Keys that are owned and written by the profile-settings subsystem.
# These keys are extracted from YAML root level and routed via
# create_profile_config() (isolated mode -> config.json) or
# write_profile_settings_to_settings() (non-isolated mode -> settings.json).
#
# Both writers are fed by the shared pure builder _build_profile_settings(),
# which performs kebab-to-camel translation. Values below are the POST-TRANSLATION
# camelCase keys as they appear in settings.json / config.json on disk.
#
# In non-isolated mode, write_profile_settings_to_settings() deep-merges the
# builder's delta into the shared ~/.claude/settings.json via
# _write_merged_json(), inheriting: deep-merge for nested dicts, array-union
# for permissions.allow/deny/ask, RFC 7396 null-as-delete for top-level and
# nested None values, and preservation for keys omitted from the delta.
# Keys not declared at YAML root level are PRESERVED in
# ~/.claude/settings.json (unchanged by this writer), including any
# prior-run contributions and any keys written by Step 14
# write_user_settings() under user-settings:.
PROFILE_OWNED_KEYS: frozenset[str] = frozenset({
    'model',
    'permissions',
    'env',
    'attribution',
    'alwaysThinkingEnabled',
    'effortLevel',
    'companyAnnouncements',
    'statusLine',
    'hooks',
})

# Mapping from YAML root kebab-case key names to their on-disk camelCase
# equivalents for the 9 profile-owned keys. Used by main() to build the
# profile_config dict passed to _build_profile_settings(): dict membership
# encodes the "declared-vs-absent" distinction (which is lost by
# config.get() alone), and a YAML-level `model: null` declaration passes
# through as `profile_config['model'] = None`, which the builder forwards
# to the writer so _write_merged_json() can apply RFC 7396 null-as-delete
# to the shared settings.json.
#
# The mapping order matches PROFILE_OWNED_KEYS for visual clarity. It is
# SEPARATE from ROOT_TO_USER_SETTINGS_KEY_MAP (which covers 7 keys and
# drives detect_settings_conflicts()): this map intentionally includes
# `status-line` and `hooks` because they are profile-owned keys that
# participate in the null-as-delete contract even though they are
# excluded from the user-settings conflict surface.
_YAML_TO_CAMEL_PROFILE_KEYS: dict[str, str] = {
    'model': 'model',
    'permissions': 'permissions',
    'env-variables': 'env',
    'attribution': 'attribution',
    'always-thinking-enabled': 'alwaysThinkingEnabled',
    'effort-level': 'effortLevel',
    'company-announcements': 'companyAnnouncements',
    'status-line': 'statusLine',
    'hooks': 'hooks',
}


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


# Parallel execution helpers
# Type variable for generic parallel execution
T = TypeVar('T')
R = TypeVar('R')

# Type alias for JSON-compatible values used in deep merge operations
# Recursive type representing dict, list, or primitive values
type JsonValue = str | int | float | bool | None | list['JsonValue'] | dict[str, 'JsonValue']


# Default number of parallel workers - can be overridden via CLAUDE_CODE_TOOLBOX_PARALLEL_WORKERS env var
# Reduced from 5 to 2 to decrease likelihood of hitting GitHub secondary rate limits
DEFAULT_PARALLEL_WORKERS = int(os.environ.get('CLAUDE_CODE_TOOLBOX_PARALLEL_WORKERS', '2'))


def is_parallel_mode_enabled() -> bool:
    """Check if parallel execution is enabled.

    Returns:
        True if parallel mode is enabled (default), False if CLAUDE_CODE_TOOLBOX_SEQUENTIAL_MODE=1
    """
    sequential_mode = os.environ.get('CLAUDE_CODE_TOOLBOX_SEQUENTIAL_MODE', '').lower()
    return sequential_mode not in ('1', 'true', 'yes')


def execute_parallel(
    items: list[T],
    func: Callable[[T], R],
    max_workers: int = DEFAULT_PARALLEL_WORKERS,
    stagger_delay: float = 0.0,
) -> list[R]:
    """Execute a function on items in parallel with error isolation.

    Processes items using ThreadPoolExecutor when parallel mode is enabled,
    or sequentially when CLAUDE_CODE_TOOLBOX_SEQUENTIAL_MODE=1.

    Args:
        items: List of items to process
        func: Function to apply to each item
        max_workers: Maximum number of parallel workers (default: 2)
        stagger_delay: Delay in seconds between task submissions to prevent
            thundering herd on rate-limited APIs (default: 0.0)

    Returns:
        List of results in the same order as input items.
        If an item raises an exception, that exception is stored in the result list
        and re-raised after all items are processed.
    """
    import operator

    if not items:
        return []

    # Sequential mode fallback
    if not is_parallel_mode_enabled():
        debug_log('Sequential mode enabled, processing items sequentially')
        return [func(item) for item in items]

    # Parallel execution
    debug_log(f'Parallel mode enabled, processing {len(items)} items with {max_workers} workers')
    results_with_index: list[tuple[int, R | BaseException]] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit tasks with optional stagger delay to prevent thundering herd
        future_to_index: dict[concurrent.futures.Future[R], int] = {}
        for idx, item in enumerate(items):
            future_to_index[executor.submit(func, item)] = idx
            if stagger_delay > 0 and idx < len(items) - 1:
                time.sleep(stagger_delay)

        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_index):
            idx = future_to_index[future]
            try:
                result = future.result()
                results_with_index.append((idx, result))
            except Exception as task_exc:
                # Store exception to maintain order and allow partial results
                results_with_index.append((idx, task_exc))

    # Sort by original index to maintain order
    results_with_index.sort(key=operator.itemgetter(0))

    # Extract results, re-raising any exceptions
    final_results: list[R] = []
    exceptions: list[tuple[int, BaseException]] = []
    for idx, result_or_exc in results_with_index:
        if isinstance(result_or_exc, BaseException):
            exceptions.append((idx, result_or_exc))
        else:
            final_results.append(result_or_exc)

    # If there were exceptions, raise the first one after logging all
    if exceptions:
        for exc_idx, stored_exc in exceptions:
            debug_log(f'Item {exc_idx} raised exception: {stored_exc}')
        # Re-raise the first exception
        raise exceptions[0][1]

    return final_results


def execute_parallel_safe(
    items: list[T],
    func: Callable[[T], R],
    default_on_error: R,
    max_workers: int = DEFAULT_PARALLEL_WORKERS,
    stagger_delay: float = 0.0,
) -> list[R]:
    """Execute a function on items in parallel with error handling.

    Unlike execute_parallel, this function catches exceptions and returns
    a default value for failed items, allowing partial success.

    Args:
        items: List of items to process
        func: Function to apply to each item
        default_on_error: Value to return for items that raise exceptions
        max_workers: Maximum number of parallel workers (default: 2)
        stagger_delay: Delay in seconds between task submissions to prevent
            thundering herd on rate-limited APIs (default: 0.0)

    Returns:
        List of results in the same order as input items.
        Failed items return default_on_error instead of their result.
    """
    if not items:
        return []

    def safe_func(item: T) -> R:
        try:
            return func(item)
        except Exception as exc:
            debug_log(f'Item processing failed: {exc}')
            return default_on_error

    return execute_parallel(items, safe_func, max_workers, stagger_delay=stagger_delay)


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
            'CLAUDE_CODE_TOOLBOX_ENV_CONFIG',
            'GITHUB_TOKEN',
            'GITLAB_TOKEN',
            'REPO_TOKEN',
            'CLAUDE_CODE_TOOLBOX_VERSION',
            'CLAUDE_CODE_TOOLBOX_CONFIRM_INSTALL',
            'CLAUDE_CODE_TOOLBOX_DRY_RUN',
            'CLAUDE_CODE_TOOLBOX_SKIP_INSTALL',
            'CLAUDE_CODE_TOOLBOX_NO_ADMIN',
            'CLAUDE_CODE_TOOLBOX_ENV_AUTH',
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
        # Check current platform + common dependencies
        current_platform_key = PLATFORM_SYSTEM_TO_CONFIG_KEY.get(platform.system())
        platform_deps = dependencies.get(current_platform_key, []) if current_platform_key else []
        common_deps = dependencies.get('common', [])
        all_deps = list(platform_deps) + list(common_deps)

        for dep in all_deps:
            # Check for commands that typically need admin
            if 'winget' in dep and '--scope machine' in dep:
                return True
            if 'npm install -g' in dep:
                # Global npm installs may need admin depending on Node.js installation
                return True

    return False


# ANSI color codes for pretty output


@dataclass(frozen=True)
class InheritanceChainEntry:
    """Single entry in the configuration inheritance chain."""

    source: str
    source_type: str  # 'url', 'local', 'repo'
    name: str


@dataclass
class InstallationPlan:
    """Structured representation of what the setup will install.

    Separates data collection from display logic, enabling testability
    and reuse between pre-install summary and post-install report.
    """

    # Config metadata
    config_name: str
    config_source: str
    config_source_type: str  # 'url', 'local', 'repo'
    config_version: str | None
    config_description: str | None = None

    # Inheritance chain (root ancestor first, current config last)
    inheritance_chain: list[InheritanceChainEntry] = field(
        default_factory=lambda: list[InheritanceChainEntry](),
    )

    # Resources by category
    agents: list[str] = field(default_factory=lambda: list[str]())
    slash_commands: list[str] = field(default_factory=lambda: list[str]())
    rules: list[str] = field(default_factory=lambda: list[str]())
    skills: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())
    files_to_download: list[dict[str, Any]] = field(
        default_factory=lambda: list[dict[str, Any]](),
    )
    hooks_files: list[str] = field(default_factory=lambda: list[str]())
    hooks_events: list[dict[str, Any]] = field(
        default_factory=lambda: list[dict[str, Any]](),
    )
    mcp_servers: list[dict[str, Any]] = field(
        default_factory=lambda: list[dict[str, Any]](),
    )

    # Dependency commands by platform
    dependency_commands: dict[str, list[str]] = field(
        default_factory=lambda: dict[str, list[str]](),
    )

    # Settings
    model: str | None = None
    system_prompt: str | None = None
    system_prompt_mode: str = 'replace'
    command_names: list[str] = field(default_factory=lambda: list[str]())
    claude_code_version: str | None = None
    install_nodejs: bool = False
    skip_install: bool = False
    permissions: dict[str, Any] | None = None
    env_variables: dict[str, str] | None = None
    os_env_variables: dict[str, Any] | None = None
    user_settings: dict[str, Any] | None = None
    global_config: dict[str, Any] | None = None
    always_thinking_enabled: bool | None = None
    effort_level: str | None = None
    company_announcements: list[str] | None = None
    attribution: dict[str, str] | None = None
    status_line: dict[str, Any] | None = None

    # Security analysis
    unknown_keys: list[str] = field(default_factory=lambda: list[str]())
    sensitive_paths: list[str] = field(default_factory=lambda: list[str]())

    # Auto-injected items (auto-update controls)
    auto_injected_items: list[str] = field(default_factory=lambda: list[str]())

    @property
    def total_resources(self) -> int:
        """Total count of downloadable resources."""
        return (
            len(self.agents)
            + len(self.slash_commands)
            + len(self.rules)
            + len(self.skills)
            + len(self.files_to_download)
            + len(self.hooks_files)
            + len(self.mcp_servers)
        )

    @property
    def has_security_concerns(self) -> bool:
        """Whether any security attention items exist."""
        return bool(
            self.dependency_commands
            or self.unknown_keys
            or self.sensitive_paths
            or self.hooks_events,
        )


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
            # Use setattr for dynamic attribute assignment on class variables
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


def find_command(cmd: str, fallback_paths: list[str] | None = None) -> str | None:
    """Find a command with robust platform-specific fallback search.

    For the 'claude' command, checks the native installer target path first
    to ensure the native binary is preferred over npm even when PATH ordering
    would resolve to the npm binary first.

    Args:
        cmd: Command name to find (e.g., 'claude', 'node')
        fallback_paths: Optional list of additional paths to check

    Returns:
        Full path to command if found, None otherwise
    """
    # For 'claude' command: check native installer target FIRST
    # This ensures the native binary is preferred over npm even when
    # PATH ordering would resolve to the npm binary first.
    if cmd == 'claude':
        if sys.platform == 'win32':
            native_path = get_real_user_home() / '.local' / 'bin' / 'claude.exe'
        else:
            native_path = get_real_user_home() / '.local' / 'bin' / 'claude'
        try:
            if native_path.exists() and native_path.stat().st_size > 1000:
                return str(native_path)
        except (OSError, ValueError, TypeError):
            pass  # Path inaccessible or invalid

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
                # Native installer target (checked first for correct precedence)
                str(get_real_user_home() / '.local' / 'bin' / 'claude'),
                str(get_real_user_home() / '.npm-global' / 'bin' / 'claude'),
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

    # Check CLAUDE_CODE_TOOLBOX_GIT_BASH_PATH env var first
    env_path = os.environ.get('CLAUDE_CODE_TOOLBOX_GIT_BASH_PATH')
    debug_log(f'CLAUDE_CODE_TOOLBOX_GIT_BASH_PATH={env_path}')
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
    bash_path = shutil.which('bash.exe')
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
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Execute command via bash (Git Bash on Windows, native bash on Unix).

    Provides consistent cross-platform behavior for CLI command execution.
    Uses Git Bash on Windows and native bash on Unix systems.

    Args:
        command: The bash command string to execute
        capture_output: Whether to capture stdout/stderr
        login_shell: Whether to use login shell (-l flag)
        extra_env: Additional environment variables to merge into the subprocess
            environment. When provided, these values override any existing
            environment variables (e.g., passing PATH replaces the inherited PATH).

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

    # Disable MSYS path conversion on Windows to preserve /c flags and other arguments
    # that would otherwise be incorrectly converted to Windows drive paths (e.g., /c -> C:/)
    env = os.environ.copy()
    if sys.platform == 'win32':
        env['MSYS_NO_PATHCONV'] = '1'

    # Merge additional environment variables (e.g., PATH for MCP server configuration)
    if extra_env:
        env.update(extra_env)

    try:
        result = subprocess.run(args, capture_output=capture_output, text=True, env=env)
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

    # Strip surrounding double quotes from Windows registry PATH entries
    windows_path = windows_path.strip('"')

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


def is_wsl() -> bool:
    """Detect if running inside Windows Subsystem for Linux.

    Checks /proc/version for Microsoft/WSL indicators, which is the
    standard detection method for WSL environments.

    Uses EAFP (try/except) for robust cross-platform detection
    without platform-specific guards.

    Returns:
        True if running in WSL, False otherwise
    """
    try:
        version_info = Path('/proc/version').read_text(encoding='utf-8').lower()
        return 'microsoft' in version_info or 'wsl' in version_info
    except OSError:
        return False


def normalize_tilde_path(path: str, resolve: bool = False) -> str:
    """Normalize a path by expanding tildes, environment variables, and separators.

    This is the SINGLE SOURCE OF TRUTH for tilde/env-var expansion.
    All path expansion MUST go through this function (DRY compliance).

    Key invariant: A tilde path (~...) is ALWAYS local, never a URL.
    After expansion, tilde paths become absolute local paths.

    Uses get_real_user_home() for tilde expansion instead of os.path.expanduser()
    to avoid WSL HOME contamination, where os.path.expanduser() may
    return a Windows home path (C:\\Users\\user) instead of the correct
    Linux home (/home/user).

    Path separators are normalized via os.path.normpath() to ensure
    platform-consistent separators (backslashes on Windows, forward
    slashes on Unix). This also resolves '.' and '..' components.

    Args:
        path: Path string (may contain ~, $VAR, %VAR%)
        resolve: If True, also resolve to absolute path via Path.resolve()

    Returns:
        Normalized path with tildes and env vars expanded

    Examples:
        >>> normalize_tilde_path("~/.claude/agent.md")  # Unix
        '/home/user/.claude/agent.md'

        >>> normalize_tilde_path("~/.claude/agent.md")  # Windows
        'C:\\\\Users\\\\user\\\\.claude\\\\agent.md'

        >>> normalize_tilde_path("$HOME/config.yaml")
        '/home/user/config.yaml'

        >>> normalize_tilde_path("./relative/path", resolve=True)
        '/absolute/path/to/relative/path'
    """
    if not path:
        return path

    # Step 1: Expand tilde (~, ~username) using get_real_user_home() for reliability
    if path.startswith('~'):
        if path == '~' or path.startswith(('~/', '~\\')):
            # Current user's home directory - use get_real_user_home() to avoid
            # WSL HOME contamination from os.path.expanduser()
            home_str = str(get_real_user_home())
            # path[2:] skips the ~/ or ~\ prefix (no-op when path == '~')
            expanded = home_str if path == '~' else str(Path(home_str) / path[2:])
        else:
            # ~username case (rare) - fall back to os.path.expanduser
            expanded = os.path.expanduser(path)
    else:
        expanded = path

    # Step 2: Expand environment variables ($VAR, %VAR%)
    expanded = os.path.expandvars(expanded)

    # Step 3: Normalize path separators and resolve .. / . components
    # Skip normpath for URLs - it would corrupt the :// scheme separator
    if not expanded.startswith(('http://', 'https://')):
        expanded = os.path.normpath(expanded)

    # Step 4: Optionally resolve to absolute path
    if resolve:
        path_obj = Path(expanded)
        if not path_obj.is_absolute():
            expanded = str(path_obj.resolve())

    return expanded


def expand_tildes_in_command(command: str) -> str:
    """Expand tilde paths in a shell command.

    When commands are executed via subprocess with shell=False or wrapped in bash -c,
    the shell's tilde expansion doesn't occur. This function explicitly expands
    tilde paths to their absolute equivalents.

    Uses normalize_tilde_path() internally for DRY compliance.

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
        """Expand a single tilde path match using central function."""
        path = match.group(1)
        # DRY: Use central normalization function
        expanded = normalize_tilde_path(path)
        # Only return expanded path if expansion actually occurred
        # This prevents expanding tildes in strings like "~test" that aren't paths
        if expanded != path:
            return expanded
        return path

    return re.sub(tilde_pattern, expand_match, command)


def _deep_copy_value(value: JsonValue) -> JsonValue:
    """Create a deep copy of a JSON-compatible value.

    Args:
        value: A JSON-compatible value (dict, list, or primitive).

    Returns:
        A deep copy of the value.
    """
    if isinstance(value, dict):
        return {k: _deep_copy_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_deep_copy_value(item) for item in value]
    # Primitives (str, int, float, bool, None) are immutable
    return value


def _merge_recursive(
    target: dict[str, JsonValue],
    source: dict[str, JsonValue],
    array_union_keys: set[str] | None,
    current_path: str,
) -> None:
    """Recursively merge source into target in-place.

    Null-as-delete (RFC 7396): When a source value is None, the
    corresponding key is removed from target (no-op if absent).
    This applies only to object keys -- None values inside arrays
    are not treated as deletion signals.

    Array merge policy:
    - array_union_keys is None (default): every list is unioned with the
      existing list, preserving order-of-first-appearance and
      deduplicating elements via Python structural equality. This matches
      Claude Code's cross-scope merge semantics: "arrays are concatenated
      and deduplicated, not replaced".
    - array_union_keys is a set[str]: per-path whitelist -- only the
      dot-notation paths in the set are unioned; all other lists are
      replaced wholesale. This mode is preserved for the YAML inheritance
      layer (_resolve_single_key -> deep_merge_settings) which has
      different trust semantics from on-disk writers.
    - array_union_keys is set() (empty): no paths are unioned; every list
      is replaced. Used by the YAML inheritance layer for global-config
      child-replaces-parent composition.

    Args:
        target: Target dict to merge into (mutated in-place).
        source: Source dict to merge from.
        array_union_keys: None to union every list at any depth, or a
            set of dot-notation paths to restrict union behavior.
        current_path: Current dot-notation path for tracking nested location.
    """
    for key, value in source.items():
        # Build dot-notation path for this key
        key_path = f'{current_path}.{key}' if current_path else key

        # RFC 7396: null values signal key deletion
        if value is None:
            target.pop(key, None)
        elif key not in target:
            # Key doesn't exist in target - add it (deep copy)
            target[key] = _deep_copy_value(value)
        elif isinstance(value, dict) and isinstance(target[key], dict):
            # Both are dicts - recurse
            _merge_recursive(
                cast(dict[str, JsonValue], target[key]),
                value,
                array_union_keys,
                key_path,
            )
        elif isinstance(value, list) and isinstance(target[key], list):
            # Lists: union when array_union_keys is None (universal default)
            # or when key_path is in the explicit whitelist.
            should_union = (
                array_union_keys is None
                or key_path in array_union_keys
            )
            if should_union:
                existing = cast(list[JsonValue], target[key])
                new_items = value
                combined = existing + [
                    item for item in new_items if item not in existing
                ]
                target[key] = combined
            else:
                target[key] = _deep_copy_value(value)
        else:
            # Scalar or type mismatch - update wins (deep copy)
            target[key] = _deep_copy_value(value)


def deep_merge_settings(
    base: dict[str, Any],
    updates: dict[str, Any],
    array_union_keys: set[str] | None = None,
) -> dict[str, Any]:
    """Deep merge updates into base dict with universal array-union.

    Performs recursive merging where nested dicts are merged (not
    replaced), arrays are unioned and deduplicated at every depth (by
    default), scalars are overwritten on conflict, and RFC 7396
    null-as-delete is honored.

    Key behaviors:
    - Keys NOT in updates: PRESERVED unchanged from base.
    - Keys IN updates: UPDATED or ADDED.
    - Keys with None value in updates: DELETED from result (RFC 7396).
    - Nested dicts: Recursively merged (not replaced entirely).
    - Arrays: Union with structural dedupe when array_union_keys is None
      (the default). Matches Claude Code CLI's cross-scope merge
      semantics: "arrays are concatenated and deduplicated, not replaced".

    Args:
        base: Existing settings dict to merge into. Not modified.
        updates: New settings values to merge.
        array_union_keys: None (default) unions every array at every
            depth. A set of dot-notation paths restricts union to those
            paths and replaces all other arrays (per-path whitelist
            preserved for the YAML inheritance layer). An empty set
            disables union entirely (all arrays replaced).

    Returns:
        New merged dict with base keys preserved and updates applied.

    Examples:
        >>> base = {"permissions": {"allow": ["Read"], "deny": ["Bash(rm *)"]}}
        >>> updates = {"permissions": {"allow": ["Write"]}}
        >>> deep_merge_settings(base, updates)
        {'permissions': {'allow': ['Read', 'Write'], 'deny': ['Bash(rm *)']}}

        >>> base = {"companyAnnouncements": ["Welcome"]}
        >>> updates = {"companyAnnouncements": ["Welcome", "Maintenance Sunday"]}
        >>> deep_merge_settings(base, updates)
        {'companyAnnouncements': ['Welcome', 'Maintenance Sunday']}

        >>> base = {"a": 1, "b": 2}
        >>> updates = {"b": None}
        >>> deep_merge_settings(base, updates)
        {'a': 1}
    """
    # Create a fresh result dict (do not mutate base)
    result: dict[str, JsonValue] = {}

    # Start with all keys from base (deep copied)
    for key, value in base.items():
        result[key] = _deep_copy_value(cast(JsonValue, value))

    # Merge in updates. None means "union every array at every depth";
    # explicit set[str] restricts union to those paths (whitelist);
    # set() disables union entirely.
    _merge_recursive(result, cast(dict[str, JsonValue], updates), array_union_keys, '')

    return cast(dict[str, Any], result)


def _expand_tilde_keys_in_settings(settings: dict[str, Any]) -> dict[str, Any]:
    """Expand tilde paths in settings keys that contain shell commands.

    Platform-conditional behavior:
    - Windows: Tildes are expanded to absolute paths because Windows shell
      does not resolve ~ in paths. Uses expand_tildes_in_command() for
      DRY compliance with commit 46a086b.
    - Linux/macOS/WSL: Tildes are PRESERVED. Claude Code resolves ~ to the
      correct home directory at runtime, and preserving tildes keeps paths
      portable across environments (avoids WSL HOME contamination).

    Args:
        settings: User settings dict (not modified)

    Returns:
        New dict with tilde paths expanded (Windows) or preserved (Unix)
    """
    result = settings.copy()
    if sys.platform == 'win32':
        # Windows: Claude Code does NOT expand tildes, must pre-expand
        for key in TILDE_EXPANSION_KEYS:
            if key in result and isinstance(result[key], str):
                original = result[key]
                expanded = expand_tildes_in_command(original)
                if expanded != original:
                    debug_log(f'Expanded tilde in {key}: {original} -> {expanded}')
                result[key] = expanded
    else:
        # Linux/macOS/WSL: Keep tildes for portability
        # Claude Code resolves ~ to the correct home directory at runtime
        debug_log('Preserving tildes in settings keys (non-Windows platform)')
    return result


def _write_merged_json(
    target_file: Path,
    new_settings: dict[str, Any],
    array_union_keys: set[str] | None = None,
    *,
    ensure_parent: bool = True,
) -> tuple[bool, dict[str, Any]]:
    """Read-merge-write JSON file with universal deep merge.

    Implements the three-step merge process:
    1. READ existing JSON file (or empty dict if not exists/invalid)
    2. DEEP MERGE new settings into existing via deep_merge_settings()
    3. WRITE merged result back to file

    Merge semantics (default, array_union_keys=None):
    - Nested dicts: recursive deep merge.
    - Lists: union with structural dedupe at every depth (matches Claude
      Code CLI's cross-scope merge: "arrays are concatenated and
      deduplicated, not replaced").
    - Scalars: update wins.
    - None values: RFC 7396 null-as-delete (top-level and nested).
    - Keys absent from new_settings: preserved unchanged in target.

    Args:
        target_file: Path to the JSON file to update.
        new_settings: New settings to deep-merge into existing content.
        array_union_keys: None (default) unions every array at every
            depth. Pass an explicit set[str] only when the caller needs
            the per-path whitelist behavior (currently only the YAML
            inheritance layer at lines 4331 and 4337). Pass set() to
            disable union entirely (every array replaced).
        ensure_parent: If True, create parent directories if needed.

    Returns:
        Tuple of (success, merged_dict). success is True if settings were
        written successfully, False on write failure. merged_dict contains
        the merged content (useful for post-write checks).
    """
    # Step 1: READ existing settings
    existing: dict[str, Any] = {}
    if target_file.exists():
        try:
            file_content = target_file.read_text(encoding='utf-8')
            if file_content.strip():
                parsed = json.loads(file_content)
                if isinstance(parsed, dict):
                    existing = cast(dict[str, Any], parsed)
                else:
                    warning(f'Existing {target_file} is not a dict, starting fresh')
        except json.JSONDecodeError as e:
            warning(f'Invalid JSON in {target_file}: {e}, starting fresh')

    # Step 2: DEEP MERGE new settings into existing
    merged = deep_merge_settings(existing, new_settings, array_union_keys=array_union_keys)

    # Step 3: WRITE merged result back to file
    try:
        if ensure_parent:
            target_file.parent.mkdir(parents=True, exist_ok=True)

        target_file.write_text(
            json.dumps(merged, indent=2, ensure_ascii=False) + '\n',
            encoding='utf-8',
        )
        return True, merged
    except OSError as e:
        warning(f'Failed to write to {target_file}: {e}')
        return False, merged


def write_user_settings(
    settings: dict[str, Any],
    claude_user_dir: Path,
) -> bool:
    """Write user settings to ~/.claude/settings.json with deep merge.

    Implements the three-step merge process via _write_merged_json():
    1. READ existing ~/.claude/settings.json (or empty dict if not exists)
    2. DEEP MERGE new settings values into existing
    3. WRITE merged result back to file

    Before merging, applies platform-conditional tilde handling:
    - Windows: Expands tilde paths in command keys (apiKeyHelper, awsCredentialExport)
    - Linux/macOS/WSL: Preserves tildes for runtime resolution by Claude Code

    Args:
        settings: User settings dict from YAML user-settings section
        claude_user_dir: Path to ~/.claude directory

    Returns:
        True if settings were written successfully, False on write failure.
    """
    settings_file = claude_user_dir / 'settings.json'

    # Step 0: Platform-conditional tilde handling in command keys
    expanded_settings = _expand_tilde_keys_in_settings(settings)

    # Delegate to shared READ-MERGE-WRITE helper.
    # Uses default array_union_keys=None: every list is unioned with
    # structural dedupe at every depth. This preserves contributions
    # from the Claude Code CLI, prior toolbox runs with other YAML
    # configs, manual user edits, and other writers. permissions.allow,
    # permissions.deny, permissions.ask, permissions.additionalDirectories,
    # companyAnnouncements, hooks.<EventName>, sandbox.filesystem.*,
    # disabledMcpjsonServers, and every other list-valued key compose
    # additively across runs.
    ok, merged = _write_merged_json(settings_file, expanded_settings)

    if ok:
        success(f'Wrote user settings to {settings_file}')

        # Warn about potential WSL path issues
        if is_wsl():
            for key in TILDE_EXPANSION_KEYS:
                if key in merged and isinstance(merged[key], str):
                    value = merged[key]
                    # Check for Windows path patterns (e.g., C:\, D:\)
                    if re.search(r'[A-Za-z]:\\', value):
                        warning(
                            f'WSL detected: {key} contains Windows-style path: {value}. '
                            'This may not work in the Linux environment. '
                            'Consider re-running setup from within WSL.',
                        )
                        break
    else:
        warning(f'Failed to write user settings to {settings_file}')

    return ok


def validate_user_settings(user_settings: dict[str, Any]) -> list[str]:
    """Validate user-settings section for excluded keys.

    Checks that the user-settings section does not contain keys that are
    not allowed (hooks, statusLine) due to path resolution or profile-specific
    behavior issues.

    Args:
        user_settings: Dict from YAML user-settings section.

    Returns:
        List of error messages. Empty list if validation passes.

    Examples:
        >>> validate_user_settings({'language': 'russian', 'model': 'claude-opus-4'})
        []

        >>> validate_user_settings({'hooks': {'events': []}})
        ["Key 'hooks' is not allowed in user-settings (profile-specific only)"]

        >>> validate_user_settings({'statusLine': {'file': 'script.py'}})
        ["Key 'statusLine' is not allowed in user-settings (profile-specific only)"]
    """
    return [
        f"Key '{key}' is not allowed in user-settings (profile-specific only)"
        for key in user_settings
        if key in USER_SETTINGS_EXCLUDED_KEYS
    ]


def validate_global_config(global_config: dict[str, Any]) -> list[str]:
    """Validate global-config section for excluded keys.

    Checks that the global-config section does not contain non-null OAuth
    credential values. Null values are allowed to support clearing
    authentication state (e.g., oauthAccount: null).

    Args:
        global_config: Dict from YAML global-config section.

    Returns:
        List of error messages. Empty list if validation passes.
    """
    return [
        f"Key '{key}' cannot be set to a non-null value in global-config "
        '(OAuth credentials)'
        for key in global_config
        if key in GLOBAL_CONFIG_EXCLUDED_KEYS and global_config[key] is not None
    ]


def write_global_config(
    global_config: dict[str, Any],
    artifact_base_dir: Path | None = None,
) -> bool:
    """Write global configuration to ~/.claude.json with universal deep merge.

    Implements asymmetric dual-write: always writes to ~/.claude.json
    (machine baseline for bare claude sessions), and additionally writes
    to artifact_base_dir/.claude.json when command-names creates an
    isolated environment (since Claude Code CLI resolves
    getGlobalClaudeFile() via CLAUDE_CONFIG_DIR with no fallback to the
    home directory).

    ~/.claude.json is a collaborative surface managed by the Claude Code
    CLI at runtime (OAuth tokens, per-project trust decisions,
    user-scoped MCP server approvals via /mcp approve, enabledPlugins,
    enabledMcpjsonServers, disabledMcpjsonServers, etc.). The writer
    MUST NOT destroy these contributions, so it delegates to
    _write_merged_json() with the default universal union-all-arrays
    merge policy -- exactly the same semantics as write_user_settings()
    and write_profile_settings_to_settings().

    Args:
        global_config: Global config dict from YAML global-config section.
        artifact_base_dir: Isolated config directory path, or None.

    Returns:
        True if config was written successfully to all targets, False on
        any failure.
    """
    home_dir = get_real_user_home()
    config_file = home_dir / '.claude.json'

    ok, _ = _write_merged_json(config_file, global_config)

    if ok:
        success(f'Wrote global config to {config_file}')
    else:
        warning(f'Failed to write global config to {config_file}')

    # Dual-write to isolated environment when command-names is present
    if artifact_base_dir is not None and artifact_base_dir != home_dir:
        isolated_config_file = artifact_base_dir / '.claude.json'
        iso_ok, _ = _write_merged_json(isolated_config_file, global_config)
        if iso_ok:
            success(f'Wrote global config to {isolated_config_file}')
        else:
            warning(f'Failed to write global config to {isolated_config_file}')
        ok = ok and iso_ok

    return ok


# Constants for auto-update management (used for value parity with install_claude.py)
AUTO_UPDATE_KEY = 'autoUpdates'
AUTO_UPDATE_DISABLED_VALUE = False
DISABLE_AUTOUPDATER_KEY = 'DISABLE_AUTOUPDATER'
DISABLE_AUTOUPDATER_VALUE = '1'

# Constants for IDE extension version management
IDE_AUTO_INSTALL_KEY = 'autoInstallIdeExtension'
IDE_AUTO_INSTALL_DISABLED_VALUE = False
IDE_SKIP_AUTO_INSTALL_KEY = 'CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL'
IDE_SKIP_AUTO_INSTALL_VALUE = '1'
IDE_EXTENSION_ID = 'anthropic.claude-code'
IDE_EXTENSION_PUBLISHER = 'anthropic'
IDE_EXTENSION_NAME = 'claude-code'
VSIX_DOWNLOAD_URL_PRIMARY = (
    'https://{publisher}.gallery.vsassets.io/_apis/public/gallery/'
    'publisher/{publisher}/extension/{extension}/{version}/'
    'assetbyname/Microsoft.VisualStudio.Services.VSIXPackage'
)
VSIX_DOWNLOAD_URL_FALLBACK = (
    'https://marketplace.visualstudio.com/_apis/public/gallery/'
    'publishers/{publisher}/vsextensions/{extension}/{version}/vspackage'
)
# VS Code family IDE CLIs to detect for extension installation
VSCODE_FAMILY_CLI_NAMES = ('code', 'code-insiders', 'cursor', 'windsurf', 'codium')


def apply_auto_update_settings(
    claude_code_version_normalized: str | None,
    global_config: dict[str, Any] | None,
    user_settings: dict[str, Any] | None,
    env_variables: dict[str, str] | None,
    os_env_variables: dict[str, str | None] | None,
) -> tuple[
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, str] | None,
    dict[str, str | None] | None,
    list[str],
    list[str],
]:
    """Apply automatic auto-update settings based on version pinning.

    When a specific version is pinned, disables auto-updates across all
    four available targets. When version is None (latest/absent), removes
    auto-injected controls.

    Operates on in-memory dicts ONLY -- has no knowledge of command-names,
    file paths, or environment isolation. The existing write routing
    infrastructure handles which files get created.

    Args:
        claude_code_version_normalized: Pinned version string, or None for latest.
        global_config: Global config dict (may be None).
        user_settings: User settings dict (may be None).
        env_variables: Environment variables dict (may be None).
        os_env_variables: OS-level environment variables dict (may be None).

    Returns:
        Tuple of (global_config, user_settings, env_variables, os_env_variables,
        warnings, auto_injected_items).
    """
    warnings_list: list[str] = []
    auto_injected: list[str] = []

    if claude_code_version_normalized is not None:
        # Pinned version: inject auto-update disable controls
        global_config, user_settings, env_variables, os_env_variables = (
            _inject_auto_update_controls(
                global_config, user_settings, env_variables, os_env_variables,
                warnings_list, auto_injected,
            )
        )
    else:
        # Latest/absent: remove auto-injected controls
        global_config, user_settings, env_variables, os_env_variables = (
            _remove_auto_update_controls(
                global_config, user_settings, env_variables, os_env_variables,
                warnings_list,
            )
        )

    return global_config, user_settings, env_variables, os_env_variables, warnings_list, auto_injected


def _inject_auto_update_controls(
    global_config: dict[str, Any] | None,
    user_settings: dict[str, Any] | None,
    env_variables: dict[str, str] | None,
    os_env_variables: dict[str, str | None] | None,
    warnings_list: list[str],
    auto_injected: list[str],
) -> tuple[
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, str] | None,
    dict[str, str | None] | None,
]:
    """Inject auto-update disable controls into all four target dicts."""
    # Target 1: global_config.autoUpdates = False
    if global_config is None:
        global_config = {}
    current_auto = global_config.get(AUTO_UPDATE_KEY)
    if current_auto is None:
        global_config[AUTO_UPDATE_KEY] = AUTO_UPDATE_DISABLED_VALUE
        auto_injected.append(f'global-config.{AUTO_UPDATE_KEY}: false')
    elif current_auto == AUTO_UPDATE_DISABLED_VALUE:
        pass  # Already matches intent
    else:
        warnings_list.append(
            f'User set global-config.{AUTO_UPDATE_KEY} to {current_auto!r} '
            f'(auto-update intent is {AUTO_UPDATE_DISABLED_VALUE!r} for pinned version). '
            f'Respecting user value.',
        )

    # Target 2: user_settings.env.DISABLE_AUTOUPDATER = "1"
    if user_settings is None:
        user_settings = {}
    env_raw = user_settings.get('env')
    if not isinstance(env_raw, dict):
        env_raw = {}
        user_settings['env'] = env_raw
    env_section = cast(dict[str, Any], env_raw)
    current_disable: object = env_section.get(DISABLE_AUTOUPDATER_KEY)
    if current_disable is None:
        env_section[DISABLE_AUTOUPDATER_KEY] = DISABLE_AUTOUPDATER_VALUE
        auto_injected.append(f'user-settings.env.{DISABLE_AUTOUPDATER_KEY}: "{DISABLE_AUTOUPDATER_VALUE}"')
    elif str(current_disable) == DISABLE_AUTOUPDATER_VALUE:
        pass  # Already matches intent
    else:
        warnings_list.append(
            f'User set user-settings.env.{DISABLE_AUTOUPDATER_KEY} to {current_disable!r} '
            f'(auto-update intent is {DISABLE_AUTOUPDATER_VALUE!r} for pinned version). '
            f'Respecting user value.',
        )

    # Target 3: env_variables.DISABLE_AUTOUPDATER = "1"
    if env_variables is None:
        env_variables = {}
    current_env = env_variables.get(DISABLE_AUTOUPDATER_KEY)
    if current_env is None:
        env_variables[DISABLE_AUTOUPDATER_KEY] = DISABLE_AUTOUPDATER_VALUE
        auto_injected.append(f'env-variables.{DISABLE_AUTOUPDATER_KEY}: "{DISABLE_AUTOUPDATER_VALUE}"')
    elif str(current_env) == DISABLE_AUTOUPDATER_VALUE:
        pass  # Already matches intent
    else:
        warnings_list.append(
            f'User set env-variables.{DISABLE_AUTOUPDATER_KEY} to {current_env!r} '
            f'(auto-update intent is {DISABLE_AUTOUPDATER_VALUE!r} for pinned version). '
            f'Respecting user value.',
        )

    # Target 4: os_env_variables.DISABLE_AUTOUPDATER = "1"
    if os_env_variables is None:
        os_env_variables = {}
    current_os_env = os_env_variables.get(DISABLE_AUTOUPDATER_KEY)
    if current_os_env is None:
        os_env_variables[DISABLE_AUTOUPDATER_KEY] = DISABLE_AUTOUPDATER_VALUE
        auto_injected.append(f'os-env-variables.{DISABLE_AUTOUPDATER_KEY}: "{DISABLE_AUTOUPDATER_VALUE}"')
    elif str(current_os_env) == DISABLE_AUTOUPDATER_VALUE:
        pass  # Already matches intent
    else:
        warnings_list.append(
            f'User set os-env-variables.{DISABLE_AUTOUPDATER_KEY} to {current_os_env!r} '
            f'(auto-update intent is {DISABLE_AUTOUPDATER_VALUE!r} for pinned version). '
            f'Respecting user value.',
        )

    return global_config, user_settings, env_variables, os_env_variables


def _remove_auto_update_controls(
    global_config: dict[str, Any] | None,
    user_settings: dict[str, Any] | None,
    env_variables: dict[str, str] | None,
    os_env_variables: dict[str, str | None] | None,
    warnings_list: list[str],
) -> tuple[
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, str] | None,
    dict[str, str | None] | None,
]:
    """Remove auto-injected auto-update controls from all four target dicts."""
    # Target 1: Remove autoUpdates from global_config (only if False)
    if global_config is not None and AUTO_UPDATE_KEY in global_config:
        current_val = global_config[AUTO_UPDATE_KEY]
        if current_val == AUTO_UPDATE_DISABLED_VALUE:
            # Set to None for RFC 7396 null-as-delete
            global_config[AUTO_UPDATE_KEY] = None
        elif current_val is True:
            warnings_list.append(
                f'User explicitly set global-config.{AUTO_UPDATE_KEY} to True. '
                f'Respecting user value (not removing).',
            )

    # Target 2: Remove DISABLE_AUTOUPDATER from user_settings.env
    # Uses None for RFC 7396 null-as-delete: _write_merged_json() ->
    # _merge_recursive() requires None to trigger target.pop(key, None)
    # on disk. Using del only removes from in-memory dict; absent key
    # is preserved during merge. (Target 3 uses del correctly because
    # create_profile_config() writes atomically, not via merge.)
    if user_settings is not None:
        env_section = user_settings.get('env')
        if isinstance(env_section, dict) and DISABLE_AUTOUPDATER_KEY in env_section:
            env_section[DISABLE_AUTOUPDATER_KEY] = None

    # Target 3: Remove DISABLE_AUTOUPDATER from env_variables
    if env_variables is not None and DISABLE_AUTOUPDATER_KEY in env_variables:
        del env_variables[DISABLE_AUTOUPDATER_KEY]

    # Target 4: Set os_env_variables DISABLE_AUTOUPDATER to None (triggers deletion)
    if os_env_variables is not None and DISABLE_AUTOUPDATER_KEY in os_env_variables:
        os_env_variables[DISABLE_AUTOUPDATER_KEY] = None

    return global_config, user_settings, env_variables, os_env_variables


def cleanup_stale_auto_update_controls(
    home_dir: Path,
    is_pinned: bool,
) -> None:
    """Remove stale auto-update controls from all filesystem locations.

    Implements write-remove symmetry: writes go to specific locations
    via scope-based routing, but removal sweeps ALL locations
    unconditionally to clean up artifacts from prior configurations.

    Called AFTER all write steps in main() as a post-write cleanup pass.

    Args:
        home_dir: User home directory.
        is_pinned: Whether a specific Claude Code version is pinned.
    """
    claude_dir = home_dir / '.claude'

    if not is_pinned:
        # When NOT pinned: remove auto-update controls from EVERYWHERE

        # 1. Clean DISABLE_AUTOUPDATER from ~/.claude/settings.json
        _cleanup_settings_json_autoupdater(claude_dir / 'settings.json')

        # 2. Clean DISABLE_AUTOUPDATER from ALL ~/.claude/*/settings.json
        if claude_dir.is_dir():
            for subdir in claude_dir.iterdir():
                if subdir.is_dir():
                    settings_path = subdir / 'settings.json'
                    if settings_path.exists():
                        _cleanup_settings_json_autoupdater(settings_path)

        # 3. Clean autoUpdates: false from ~/.claude.json
        _cleanup_claude_json_auto_updates(home_dir / '.claude.json')

        # 4. Clean autoUpdates: false from ALL ~/.claude/*/.claude.json
        if claude_dir.is_dir():
            for subdir in claude_dir.iterdir():
                if subdir.is_dir():
                    claude_json_path = subdir / '.claude.json'
                    if claude_json_path.exists():
                        _cleanup_claude_json_auto_updates(claude_json_path)

    else:
        # When pinned WITH command-names: clean stale DISABLE_AUTOUPDATER
        # from ~/.claude/settings.json (bare sessions must not inherit
        # isolated environment restrictions)
        _cleanup_settings_json_autoupdater(claude_dir / 'settings.json')


def _cleanup_settings_json_autoupdater(settings_path: Path) -> None:
    """Remove stale DISABLE_AUTOUPDATER from a settings.json file via merge."""
    if not settings_path.exists():
        return
    try:
        content = json.loads(settings_path.read_text(encoding='utf-8'))
        env_section = content.get('env')
        if isinstance(env_section, dict) and DISABLE_AUTOUPDATER_KEY in env_section:
            # Use _write_merged_json with null-as-delete
            cleanup_dict: dict[str, Any] = {'env': {DISABLE_AUTOUPDATER_KEY: None}}
            ok, merged = _write_merged_json(settings_path, cleanup_dict)
            if ok and merged.get('env') == {}:
                # Clean empty env: {} after removal
                merged.pop('env')
                settings_path.write_text(
                    json.dumps(merged, indent=2, ensure_ascii=False) + '\n',
                    encoding='utf-8',
                )
            if ok:
                info(f'Cleaned stale {DISABLE_AUTOUPDATER_KEY} from {settings_path}')
    except (OSError, json.JSONDecodeError, ValueError):
        pass  # Best-effort cleanup; non-fatal


def _cleanup_claude_json_auto_updates(claude_json_path: Path) -> None:
    """Remove stale autoUpdates: false from a .claude.json file.

    Only removes when value is false (auto-injected by toolbox).
    Preserves autoUpdates: true (explicit user preference).
    """
    if not claude_json_path.exists():
        return
    try:
        content = json.loads(claude_json_path.read_text(encoding='utf-8'))
        if content.get(AUTO_UPDATE_KEY) is False:
            # Use _write_merged_json with null-as-delete
            cleanup_dict: dict[str, Any] = {AUTO_UPDATE_KEY: None}
            ok, _ = _write_merged_json(claude_json_path, cleanup_dict)
            if ok:
                info(f'Cleaned stale {AUTO_UPDATE_KEY}: false from {claude_json_path}')
    except (OSError, json.JSONDecodeError, ValueError):
        pass  # Best-effort cleanup; non-fatal


def _run_stale_controls_cleanup(claude_code_version_normalized: str | None) -> None:
    """Execute Step 16: cleanup stale auto-update and IDE extension controls."""
    print()
    print(f'{Colors.CYAN}Step 16: Cleaning stale auto-update and IDE extension controls...{Colors.NC}')
    home = get_real_user_home()
    is_pinned = claude_code_version_normalized is not None
    cleanup_stale_auto_update_controls(home_dir=home, is_pinned=is_pinned)
    cleanup_stale_ide_extension_controls(home_dir=home, is_pinned=is_pinned)


def apply_ide_extension_settings(
    claude_code_version_normalized: str | None,
    global_config: dict[str, Any] | None,
    user_settings: dict[str, Any] | None,
    env_variables: dict[str, str] | None,
    os_env_variables: dict[str, str | None] | None,
) -> tuple[
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, str] | None,
    dict[str, str | None] | None,
    list[str],
    list[str],
]:
    """Apply automatic IDE extension auto-install settings based on version pinning.

    When a specific version is pinned, disables IDE extension auto-installation
    across all four available targets. When version is None (latest/absent),
    removes auto-injected controls.

    Operates on in-memory dicts ONLY -- has no knowledge of command-names,
    file paths, or environment isolation. The existing write routing
    infrastructure handles which files get created.

    Args:
        claude_code_version_normalized: Pinned version string, or None for latest.
        global_config: Global config dict (may be None).
        user_settings: User settings dict (may be None).
        env_variables: Environment variables dict (may be None).
        os_env_variables: OS-level environment variables dict (may be None).

    Returns:
        Tuple of (global_config, user_settings, env_variables, os_env_variables,
        warnings, auto_injected_items).
    """
    warnings_list: list[str] = []
    auto_injected: list[str] = []

    if claude_code_version_normalized is not None:
        # Pinned version: inject IDE extension auto-install disable controls
        global_config, user_settings, env_variables, os_env_variables = (
            _inject_ide_extension_controls(
                global_config, user_settings, env_variables, os_env_variables,
                warnings_list, auto_injected,
            )
        )
    else:
        # Latest/absent: remove auto-injected controls
        global_config, user_settings, env_variables, os_env_variables = (
            _remove_ide_extension_controls(
                global_config, user_settings, env_variables, os_env_variables,
                warnings_list,
            )
        )

    return global_config, user_settings, env_variables, os_env_variables, warnings_list, auto_injected


def _inject_ide_extension_controls(
    global_config: dict[str, Any] | None,
    user_settings: dict[str, Any] | None,
    env_variables: dict[str, str] | None,
    os_env_variables: dict[str, str | None] | None,
    warnings_list: list[str],
    auto_injected: list[str],
) -> tuple[
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, str] | None,
    dict[str, str | None] | None,
]:
    """Inject IDE extension auto-install disable controls into all four target dicts."""
    # Target 1: global_config.autoInstallIdeExtension = False
    if global_config is None:
        global_config = {}
    current_auto = global_config.get(IDE_AUTO_INSTALL_KEY)
    if current_auto is None:
        global_config[IDE_AUTO_INSTALL_KEY] = IDE_AUTO_INSTALL_DISABLED_VALUE
        auto_injected.append(f'global-config.{IDE_AUTO_INSTALL_KEY}: false')
    elif current_auto == IDE_AUTO_INSTALL_DISABLED_VALUE:
        pass  # Already matches intent
    else:
        warnings_list.append(
            f'User set global-config.{IDE_AUTO_INSTALL_KEY} to {current_auto!r} '
            f'(auto-install intent is {IDE_AUTO_INSTALL_DISABLED_VALUE!r} for pinned version). '
            f'Respecting user value.',
        )

    # Target 2: user_settings.env.CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL = "1"
    if user_settings is None:
        user_settings = {}
    env_raw = user_settings.get('env')
    if not isinstance(env_raw, dict):
        env_raw = {}
        user_settings['env'] = env_raw
    env_section = cast(dict[str, Any], env_raw)
    current_disable: object = env_section.get(IDE_SKIP_AUTO_INSTALL_KEY)
    if current_disable is None:
        env_section[IDE_SKIP_AUTO_INSTALL_KEY] = IDE_SKIP_AUTO_INSTALL_VALUE
        auto_injected.append(f'user-settings.env.{IDE_SKIP_AUTO_INSTALL_KEY}: "{IDE_SKIP_AUTO_INSTALL_VALUE}"')
    elif str(current_disable) == IDE_SKIP_AUTO_INSTALL_VALUE:
        pass  # Already matches intent
    else:
        warnings_list.append(
            f'User set user-settings.env.{IDE_SKIP_AUTO_INSTALL_KEY} to {current_disable!r} '
            f'(auto-install intent is {IDE_SKIP_AUTO_INSTALL_VALUE!r} for pinned version). '
            f'Respecting user value.',
        )

    # Target 3: env_variables.CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL = "1"
    if env_variables is None:
        env_variables = {}
    current_env = env_variables.get(IDE_SKIP_AUTO_INSTALL_KEY)
    if current_env is None:
        env_variables[IDE_SKIP_AUTO_INSTALL_KEY] = IDE_SKIP_AUTO_INSTALL_VALUE
        auto_injected.append(f'env-variables.{IDE_SKIP_AUTO_INSTALL_KEY}: "{IDE_SKIP_AUTO_INSTALL_VALUE}"')
    elif str(current_env) == IDE_SKIP_AUTO_INSTALL_VALUE:
        pass  # Already matches intent
    else:
        warnings_list.append(
            f'User set env-variables.{IDE_SKIP_AUTO_INSTALL_KEY} to {current_env!r} '
            f'(auto-install intent is {IDE_SKIP_AUTO_INSTALL_VALUE!r} for pinned version). '
            f'Respecting user value.',
        )

    # Target 4: os_env_variables.CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL = "1"
    if os_env_variables is None:
        os_env_variables = {}
    current_os_env = os_env_variables.get(IDE_SKIP_AUTO_INSTALL_KEY)
    if current_os_env is None:
        os_env_variables[IDE_SKIP_AUTO_INSTALL_KEY] = IDE_SKIP_AUTO_INSTALL_VALUE
        auto_injected.append(f'os-env-variables.{IDE_SKIP_AUTO_INSTALL_KEY}: "{IDE_SKIP_AUTO_INSTALL_VALUE}"')
    elif str(current_os_env) == IDE_SKIP_AUTO_INSTALL_VALUE:
        pass  # Already matches intent
    else:
        warnings_list.append(
            f'User set os-env-variables.{IDE_SKIP_AUTO_INSTALL_KEY} to {current_os_env!r} '
            f'(auto-install intent is {IDE_SKIP_AUTO_INSTALL_VALUE!r} for pinned version). '
            f'Respecting user value.',
        )

    return global_config, user_settings, env_variables, os_env_variables


def _remove_ide_extension_controls(
    global_config: dict[str, Any] | None,
    user_settings: dict[str, Any] | None,
    env_variables: dict[str, str] | None,
    os_env_variables: dict[str, str | None] | None,
    warnings_list: list[str],
) -> tuple[
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, str] | None,
    dict[str, str | None] | None,
]:
    """Remove auto-injected IDE extension auto-install controls from all four target dicts."""
    # Target 1: Remove autoInstallIdeExtension from global_config (only if False)
    if global_config is not None and IDE_AUTO_INSTALL_KEY in global_config:
        current_val = global_config[IDE_AUTO_INSTALL_KEY]
        if current_val == IDE_AUTO_INSTALL_DISABLED_VALUE:
            # Set to None for RFC 7396 null-as-delete
            global_config[IDE_AUTO_INSTALL_KEY] = None
        elif current_val is True:
            warnings_list.append(
                f'User explicitly set global-config.{IDE_AUTO_INSTALL_KEY} to True. '
                f'Respecting user value (not removing).',
            )

    # Target 2: Remove CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL from user_settings.env
    # Uses None for RFC 7396 null-as-delete: _write_merged_json() ->
    # _merge_recursive() requires None to trigger target.pop(key, None)
    # on disk. Using del only removes from in-memory dict; absent key
    # is preserved during merge. (Target 3 uses del correctly because
    # create_profile_config() writes atomically, not via merge.)
    if user_settings is not None:
        env_section = user_settings.get('env')
        if isinstance(env_section, dict) and IDE_SKIP_AUTO_INSTALL_KEY in env_section:
            env_section[IDE_SKIP_AUTO_INSTALL_KEY] = None

    # Target 3: Remove CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL from env_variables
    if env_variables is not None and IDE_SKIP_AUTO_INSTALL_KEY in env_variables:
        del env_variables[IDE_SKIP_AUTO_INSTALL_KEY]

    # Target 4: Set os_env_variables CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL to None (triggers deletion)
    if os_env_variables is not None and IDE_SKIP_AUTO_INSTALL_KEY in os_env_variables:
        os_env_variables[IDE_SKIP_AUTO_INSTALL_KEY] = None

    return global_config, user_settings, env_variables, os_env_variables


def _cleanup_settings_json_ide_skip(settings_path: Path) -> None:
    """Remove stale CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL from a settings.json file via merge."""
    if not settings_path.exists():
        return
    try:
        content = json.loads(settings_path.read_text(encoding='utf-8'))
        env_section = content.get('env')
        if isinstance(env_section, dict) and IDE_SKIP_AUTO_INSTALL_KEY in env_section:
            # Use _write_merged_json with null-as-delete
            cleanup_dict: dict[str, Any] = {'env': {IDE_SKIP_AUTO_INSTALL_KEY: None}}
            ok, merged = _write_merged_json(settings_path, cleanup_dict)
            if ok and merged.get('env') == {}:
                # Clean empty env: {} after removal
                merged.pop('env')
                settings_path.write_text(
                    json.dumps(merged, indent=2, ensure_ascii=False) + '\n',
                    encoding='utf-8',
                )
            if ok:
                info(f'Cleaned stale {IDE_SKIP_AUTO_INSTALL_KEY} from {settings_path}')
    except (OSError, json.JSONDecodeError, ValueError):
        pass  # Best-effort cleanup; non-fatal


def _cleanup_claude_json_ide_auto_install(claude_json_path: Path) -> None:
    """Remove stale autoInstallIdeExtension: false from a .claude.json file.

    Only removes when value is false (auto-injected by toolbox).
    Preserves autoInstallIdeExtension: true (explicit user preference).
    """
    if not claude_json_path.exists():
        return
    try:
        content = json.loads(claude_json_path.read_text(encoding='utf-8'))
        if content.get(IDE_AUTO_INSTALL_KEY) is False:
            # Use _write_merged_json with null-as-delete
            cleanup_dict: dict[str, Any] = {IDE_AUTO_INSTALL_KEY: None}
            ok, _ = _write_merged_json(claude_json_path, cleanup_dict)
            if ok:
                info(f'Cleaned stale {IDE_AUTO_INSTALL_KEY}: false from {claude_json_path}')
    except (OSError, json.JSONDecodeError, ValueError):
        pass  # Best-effort cleanup; non-fatal


def cleanup_stale_ide_extension_controls(
    home_dir: Path,
    is_pinned: bool,
) -> None:
    """Remove stale IDE extension auto-install controls from all filesystem locations.

    Implements write-remove symmetry: writes go to specific locations
    via scope-based routing, but removal sweeps ALL locations
    unconditionally to clean up artifacts from prior configurations.

    Called AFTER all write steps in main() as a post-write cleanup pass.

    Args:
        home_dir: User home directory.
        is_pinned: Whether a specific Claude Code version is pinned.
    """
    claude_dir = home_dir / '.claude'

    if not is_pinned:
        # When NOT pinned: remove IDE extension controls from EVERYWHERE

        # 1. Clean CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL from ~/.claude/settings.json
        _cleanup_settings_json_ide_skip(claude_dir / 'settings.json')

        # 2. Clean CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL from ALL ~/.claude/*/settings.json
        if claude_dir.is_dir():
            for subdir in claude_dir.iterdir():
                if subdir.is_dir():
                    settings_path = subdir / 'settings.json'
                    if settings_path.exists():
                        _cleanup_settings_json_ide_skip(settings_path)

        # 3. Clean autoInstallIdeExtension: false from ~/.claude.json
        _cleanup_claude_json_ide_auto_install(home_dir / '.claude.json')

        # 4. Clean autoInstallIdeExtension: false from ALL ~/.claude/*/.claude.json
        if claude_dir.is_dir():
            for subdir in claude_dir.iterdir():
                if subdir.is_dir():
                    claude_json_path = subdir / '.claude.json'
                    if claude_json_path.exists():
                        _cleanup_claude_json_ide_auto_install(claude_json_path)

    else:
        # When pinned WITH command-names: clean stale CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL
        # from ~/.claude/settings.json (bare sessions must not inherit
        # isolated environment restrictions)
        _cleanup_settings_json_ide_skip(claude_dir / 'settings.json')


def install_ide_extensions(
    version: str,
) -> bool:
    """Install pinned-version IDE extensions into all detected VS Code family IDEs.

    Uses a three-tier fallback chain:
    1. Bundled VSIX from CLI package tree (no download needed)
    2. VSIX download from marketplace CDN (auto-update disabled by VS Code v1.92+)
    3. Marketplace @version syntax as last resort (with warning about auto-update)

    Non-fatal: returns False on failure but does not raise.

    Args:
        version: Pinned Claude Code version string (e.g. "2.1.92").

    Returns:
        True if at least one IDE had the extension installed successfully,
        or if no IDEs were detected (no-op success).
    """
    # Detect installed VS Code family IDEs
    detected_ides: list[tuple[str, str]] = []
    for cli_name in VSCODE_FAMILY_CLI_NAMES:
        cli_path = shutil.which(cli_name)
        if cli_path:
            detected_ides.append((cli_name, cli_path))

    if not detected_ides:
        info('No VS Code family IDEs detected, skipping extension installation')
        return True

    ide_names = ', '.join(name for name, _ in detected_ides)
    info(f'Detected VS Code family IDEs: {ide_names}')

    # Resolve VSIX source using three-tier fallback chain
    vsix_path: str | None = None
    use_marketplace_syntax = False
    temp_vsix_path: str | None = None

    try:
        # Tier 1: Check bundled VSIX from CLI package tree
        bundled_vsix = (
            get_real_user_home() / '.claude' / 'local' / 'node_modules'
            / '@anthropic-ai' / 'claude-code' / 'vendor' / 'claude-code.vsix'
        )
        if bundled_vsix.exists() and bundled_vsix.stat().st_size > 1000:
            vsix_path = str(bundled_vsix)
            info(f'Using bundled VSIX: {vsix_path}')
        else:
            # Tier 2: Download VSIX from marketplace CDN
            primary_url = VSIX_DOWNLOAD_URL_PRIMARY.format(
                publisher=IDE_EXTENSION_PUBLISHER,
                extension=IDE_EXTENSION_NAME,
                version=version,
            )
            fallback_url = VSIX_DOWNLOAD_URL_FALLBACK.format(
                publisher=IDE_EXTENSION_PUBLISHER,
                extension=IDE_EXTENSION_NAME,
                version=version,
            )

            vsix_data: bytes | None = None
            for url in (primary_url, fallback_url):
                try:
                    vsix_data = fetch_url_bytes_with_auth(url)
                    if vsix_data:
                        break
                except Exception:
                    continue

            if vsix_data:
                # Write to temp file
                tmp_fd, tmp_name = tempfile.mkstemp(suffix='.vsix')
                try:
                    os.write(tmp_fd, vsix_data)
                    os.close(tmp_fd)
                    vsix_path = tmp_name
                    temp_vsix_path = tmp_name
                    info(f'Downloaded VSIX ({len(vsix_data)} bytes) to {vsix_path}')
                except Exception:
                    with contextlib.suppress(OSError):
                        os.close(tmp_fd)
                    with contextlib.suppress(OSError):
                        Path(tmp_name).unlink(missing_ok=True)
            else:
                # Tier 3: Fall back to marketplace @version syntax
                use_marketplace_syntax = True
                warning(
                    'Using marketplace @version syntax. '
                    'VS Code may auto-update this extension. '
                    'To prevent auto-updates: in VS Code Extensions view, '
                    'right-click the Claude Code extension and set '
                    '"Auto Update" to off.',
                )

        # Install into each detected IDE
        any_success = False
        for cli_name, cli_path in detected_ides:
            try:
                if use_marketplace_syntax:
                    cmd = [cli_path, '--install-extension', f'{IDE_EXTENSION_ID}@{version}']
                else:
                    install_target = vsix_path or f'{IDE_EXTENSION_ID}@{version}'
                    cmd = [cli_path, '--install-extension', install_target, '--force']
                result = run_command(cmd)
                if result.returncode == 0:
                    success(f'Installed {IDE_EXTENSION_ID} v{version} into {cli_name}')
                    any_success = True
                else:
                    stderr_msg = result.stderr.strip() if result.stderr else 'unknown error'
                    warning(f'Failed to install extension into {cli_name}: {stderr_msg}')
            except Exception as exc:
                warning(f'Failed to install extension into {cli_name}: {exc}')

        return any_success

    finally:
        # Cleanup downloaded VSIX temp file
        if temp_vsix_path:
            with contextlib.suppress(OSError):
                Path(temp_vsix_path).unlink(missing_ok=True)


def detect_settings_conflicts(
    user_settings: dict[str, Any],
    root_config: dict[str, Any],
) -> list[tuple[str, Any, Any]]:
    """Detect conflicts where same setting appears in both sections.

    Identifies keys that are specified in both the user-settings section
    and at the root level of the config. When using a profile command,
    root-level values take precedence over user-settings values.

    Args:
        user_settings: Dict from YAML user-settings section.
        root_config: The full root-level config dict.

    Returns:
        List of (user_settings_key, user_value, root_value) tuples for conflicts.
        Empty list if no conflicts found.

    Examples:
        >>> user = {'model': 'claude-opus-4'}
        >>> root = {'model': 'claude-sonnet-4', 'command-names': ['myenv']}
        >>> detect_settings_conflicts(user, root)
        [('model', 'claude-opus-4', 'claude-sonnet-4')]

        >>> user = {'alwaysThinkingEnabled': True}
        >>> root = {'always-thinking-enabled': False}
        >>> detect_settings_conflicts(user, root)
        [('alwaysThinkingEnabled', True, False)]

        >>> user = {'language': 'russian'}
        >>> root = {'model': 'claude-opus-4'}
        >>> detect_settings_conflicts(user, root)
        []
    """
    conflicts: list[tuple[str, Any, Any]] = []

    # Build reverse mapping: user-settings key -> root key
    user_to_root_map: dict[str, str] = {
        v: k for k, v in ROOT_TO_USER_SETTINGS_KEY_MAP.items()
    }

    for user_key, user_value in user_settings.items():
        # Find corresponding root key (may be same or different name)
        root_key = user_to_root_map.get(user_key, user_key)

        # Check if this key exists at root level
        if root_key in root_config:
            root_value = root_config[root_key]
            conflicts.append((user_key, user_value, root_value))

    return conflicts


def build_platform_aware_command(command: str) -> list[str]:
    """Build command list with platform-appropriate wrapping.

    On Windows, wraps npx/npm commands with 'cmd /c' to enable proper PATH
    resolution. On Unix, returns command parts directly.

    Args:
        command: The command string to process

    Returns:
        List of command parts ready for execution or config generation
    """
    try:
        parts = shlex.split(command)
    except ValueError:
        # Fallback for malformed commands
        parts = command.split()

    if not parts:
        return [command] if command.strip() else []

    executable = parts[0]
    args = parts[1:] if len(parts) > 1 else []

    # Windows-specific handling for npx/npm commands
    if platform.system() == 'Windows' and any(
        npm_cmd in executable.lower() for npm_cmd in ['npx', 'npm']
    ):
        return ['cmd', '/c', executable] + args

    return [executable] + args


def _command_starts_with_npx(command: str) -> bool:
    """Check if a command's first token is 'npx'.

    Uses shell-aware tokenization to avoid false positives from
    substring matching (e.g., 'run_npx_wrapper.py' does not match).

    Args:
        command: MCP server command string.

    Returns:
        True if the first executable token is 'npx'.
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    return bool(tokens) and tokens[0] == 'npx'


def parse_mcp_command(command_str: str) -> dict[str, Any]:
    """Parse MCP command string into official MCP JSON schema format.

    Converts a shell command string into the structured format expected by
    Claude Code's MCP configuration. Handles:
    - Tilde path expansion to absolute paths
    - Shell-aware splitting with shlex
    - Windows npx/npm wrapper with cmd /c (via build_platform_aware_command)
    - POSIX path format for arguments (cross-platform compatibility)

    Args:
        command_str: Full command string from YAML config

    Returns:
        Dict with 'command' (executable) and 'args' (argument array) keys
    """
    # Step 1: Expand tilde paths using existing function (DRY principle)
    expanded = expand_tildes_in_command(command_str)

    # Step 2: Convert backslashes to forward slashes BEFORE shlex.split
    # This prevents shlex from interpreting backslashes as escape characters
    # and ensures consistent POSIX path format in the output
    expanded = expanded.replace('\\', '/')

    # Step 3: Build platform-aware command using shared helper
    cmd_parts = build_platform_aware_command(expanded)
    if not cmd_parts:
        return {'command': expanded, 'args': []}

    return {
        'command': cmd_parts[0],
        'args': cmd_parts[1:] if len(cmd_parts) > 1 else [],
    }


# Maximum length for PATH environment variable value on Windows.
# Windows limits each environment variable's "name=value" string to 32767 chars.
# For PATH: 32767 - len("PATH") - len("=") = 32762 max value chars.
_WIN_PATH_VALUE_MAX_LENGTH = 32762


def _broadcast_wm_settingchange() -> None:
    """Broadcast WM_SETTINGCHANGE to notify GUI applications of environment changes.

    Uses a dummy setx+reg-delete trick to trigger the broadcast.
    Only affects new windows opened from Explorer; does NOT update
    existing CLI terminal sessions (cmd, PowerShell, Git Bash).
    """
    if sys.platform == 'win32':
        subprocess.run(
            ['setx', 'CLAUDE_CODE_TOOLBOX_TEMP', 'temp'],
            capture_output=True, check=False,
        )
        subprocess.run(
            ['reg', 'delete', r'HKCU\Environment', '/v', 'CLAUDE_CODE_TOOLBOX_TEMP', '/f'],
            capture_output=True, check=False,
        )


def _is_temp_path(path: str) -> bool:
    """Check if a path belongs to a temporary directory.

    Detects paths under the user's TEMP/TMP directories, including paths
    with Windows 8.3 short filename format mismatches. Also detects pytest
    temp directories.

    Args:
        path: The file system path to check (will be lowercased internally).

    Returns:
        True if the path is in a temporary directory, False otherwise.
    """
    if sys.platform != 'win32':
        return False

    path_lower = path.lower()

    # Resolve TEMP/TMP to long form to handle Windows 8.3 short name format
    # (e.g., 'afilip~1' vs 'afilippov')
    for env_var in ('TEMP', 'TMP'):
        temp_dir = os.environ.get(env_var, '')
        if temp_dir:
            try:
                temp_dir_resolved = str(Path(temp_dir).resolve()).lower()
            except (OSError, ValueError):
                temp_dir_resolved = temp_dir.lower()
            if temp_dir_resolved and temp_dir_resolved in path_lower:
                return True
            # Also check the raw (possibly 8.3) form
            if temp_dir.lower() in path_lower:
                return True

    # Defense-in-depth: catch pytest temp dirs and generic tmp* subdirectories
    # regardless of TEMP variable resolution
    return (
        r'\appdata\local\temp\pytest-of-' in path_lower
        or r'\appdata\local\temp\tmp' in path_lower
    )


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
            if _is_temp_path(normalized_dir):
                return (
                    False,
                    f'Refusing to add temporary directory to PATH: {normalized_dir}',
                )

            # Validate it's the expected .local\bin directory
            normalized_lower = normalized_dir.lower()
            expected_local_bin = str(get_real_user_home() / '.local' / 'bin')
            if normalized_dir != expected_local_bin and not normalized_lower.startswith(str(get_real_user_home()).lower()):
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
                    new_session_path = f'{normalized_dir};{session_path}'
                    if len(new_session_path) <= _WIN_PATH_VALUE_MAX_LENGTH:
                        os.environ['PATH'] = new_session_path
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
            new_session_path = f'{normalized_dir};{os.environ.get("PATH", "")}'
            if len(new_session_path) <= _WIN_PATH_VALUE_MAX_LENGTH:
                os.environ['PATH'] = new_session_path
            else:
                warning(
                    f'Session PATH would exceed Windows limit '
                    f'({len(new_session_path)} > {_WIN_PATH_VALUE_MAX_LENGTH} chars). '
                    f'Registry updated but current session PATH not refreshed. '
                    f'Restart your terminal to apply changes.',
                )

            # Broadcast WM_SETTINGCHANGE to notify GUI applications
            _broadcast_wm_settingchange()

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

    local_bin = get_real_user_home() / '.local' / 'bin'
    local_bin.mkdir(parents=True, exist_ok=True)

    path_success, path_message = add_directory_to_windows_path(str(local_bin))

    if path_success and 'already in PATH' not in path_message:
        info('Pre-configured .local/bin in PATH for tool installations')


def cleanup_temp_paths_from_registry() -> tuple[int, list[str]]:
    """Remove temporary directory paths from Windows PATH registry.

    This function scans the user's PATH environment variable and removes any
    entries that point to temporary directories. These paths are typically
    added by mistake when scripts execute from temporary locations.
    Also removes literal %PATH% self-references that cause recursive expansion.

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
                # Check if this is a temporary directory path or a self-reference
                should_remove = _is_temp_path(path_entry)

                # Also remove %PATH% self-references that cause recursive expansion
                if path_entry.strip() == '%PATH%':
                    should_remove = True

                if should_remove:
                    removed_paths.append(path_entry)
                else:
                    clean_components.append(path_entry)

            # Update PATH if any temp paths were found
            if removed_paths:
                new_path = ';'.join(clean_components)
                winreg.SetValueEx(reg_key, 'PATH', 0, winreg.REG_EXPAND_SZ, new_path)

                # Broadcast WM_SETTINGCHANGE to notify GUI applications
                _broadcast_wm_settingchange()

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
                if len(new_path) > _WIN_PATH_VALUE_MAX_LENGTH:
                    warning(
                        f'Combined registry PATH ({len(new_path)} chars) exceeds '
                        f'Windows limit ({_WIN_PATH_VALUE_MAX_LENGTH} chars). '
                        f'Keeping current session PATH.',
                    )
                    info(
                        'Consider cleaning up unused PATH entries in '
                        'System Properties > Environment Variables',
                    )
                    return True  # Not a failure - PATH stays as-is
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

    def __init__(self, auth_param: str | None = None, auth_cache: 'AuthHeaderCache | None' = None) -> None:
        """Initialize FileValidator.

        Args:
            auth_param: Optional auth parameter in format "header:value" or "header=value"
                       or just a token (will auto-detect header based on URL)
            auth_cache: Optional shared auth header cache for origin-level caching.
                       When provided, validation results populate the cache for
                       reuse by the download phase.
        """
        self.auth_param = auth_param
        self.auth_cache = auth_cache
        self._validation_results: list[tuple[str, str, bool, str]] = []

    def validate_remote_url(self, url: str) -> tuple[bool, str]:
        """Validate a remote URL with per-URL authentication.

        Generates authentication headers specific to this URL (GitHub vs GitLab)
        and attempts validation using HEAD request, then Range request as fallback.
        When an auth_cache is provided, uses cached headers to avoid redundant
        resolution and populates the cache for downstream consumers.

        Args:
            url: Remote URL to validate

        Returns:
            Tuple of (is_valid, method_used)
            method_used is 'HEAD', 'Range', or 'None'
        """
        # ARCHITECTURAL NOTE: URL domain asymmetry between validation and download
        #
        # Validation uses raw.githubusercontent.com URLs for GitHub (only GitLab
        # web URLs are converted to API format here). The download phase in
        # _fetch_url_core() additionally converts GitHub raw URLs to
        # api.github.com/repos/.../contents/... format. This asymmetry is benign:
        # - Validation needs only HEAD/Range requests, which work on raw URLs
        # - Downloads need the Contents API for auth + Accept header control
        # - AuthHeaderCache.get_origin() normalizes both URL forms to the same
        #   cache key (github.com/owner/repo), so auth cached during validation
        #   is correctly reused during download.
        #
        # Convert GitLab web URLs to API format
        original_url = url
        if detect_repo_type(url) == 'gitlab' and '/-/raw/' in url:
            url = convert_gitlab_url_to_api(url)
            if url != original_url:
                info(f'Using API URL for validation: {url}')

        # Generate auth headers for THIS specific URL, using cache when available
        if self.auth_cache is not None:
            is_cached, cached_headers = self.auth_cache.get_cached_headers(url)
            if is_cached:
                auth_headers = cached_headers
            else:
                auth_headers = get_auth_headers(url, self.auth_param)
                # Cache the result for the download phase
                self.auth_cache.cache_headers(url, auth_headers or None)
        else:
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


def _collect_simple_list_files(
    config: dict[str, Any],
    config_key: str,
    file_type: str,
    config_source: str,
    base_url: str | None,
) -> list[tuple[str, str, str, bool]]:
    """Collect files from a simple list config key for validation.

    Handles the common pattern of extracting string items from a list-type
    config key and resolving their paths for file validation.

    Args:
        config: Environment configuration dictionary.
        config_key: The YAML key to read (e.g., 'agents', 'slash-commands', 'rules').
        file_type: Label for validation results (e.g., 'agent', 'slash_command', 'rule').
        config_source: Source of the configuration (URL or path).
        base_url: Optional base URL override from config.

    Returns:
        List of (file_type, original_path, resolved_path, is_remote) tuples.
    """
    files: list[tuple[str, str, str, bool]] = []
    raw = config.get(config_key, [])
    if isinstance(raw, list):
        items = cast(list[object], raw)
        for item in items:
            if isinstance(item, str):
                resolved_path, is_remote = resolve_resource_path(item, config_source, base_url)
                files.append((file_type, item, resolved_path, is_remote))
    return files


def validate_all_config_files(
    config: dict[str, Any],
    config_source: str,
    auth_param: str | None = None,
    auth_cache: 'AuthHeaderCache | None' = None,
) -> tuple[bool, list[tuple[str, str, bool, str]]]:
    """Validate all files in the configuration (both remote and local).

    Validates accessibility of all file references across config keys defined
    in FILE_REFERENCE_KEYS.

    Args:
        config: Environment configuration dictionary
        config_source: Source of the configuration (URL or path)
        auth_param: Optional authentication parameter
        auth_cache: Optional shared auth header cache for origin-level caching.
            When provided, validation results populate the cache for reuse
            by the download phase.

    Returns:
        Tuple of (all_valid, validation_results)
        validation_results is a list of (file_type, path, is_valid, method) tuples
    """
    files_to_check: list[tuple[str, str, str, bool]] = []
    results: list[tuple[str, str, bool, str]] = []

    # Create shared auth cache if not provided
    if auth_cache is None:
        auth_cache = AuthHeaderCache(auth_param)

    # Create file validator - generates authentication per-URL for proper
    # handling of mixed repositories (e.g., GitHub + GitLab files)
    validator = FileValidator(auth_param, auth_cache)

    # Collect all files that need to be validated
    base_url = config.get('base-url')

    # Agents
    files_to_check.extend(
        _collect_simple_list_files(config, 'agents', 'agent', config_source, base_url),
    )

    # Slash commands
    files_to_check.extend(
        _collect_simple_list_files(config, 'slash-commands', 'slash_command', config_source, base_url),
    )

    # Rules
    files_to_check.extend(
        _collect_simple_list_files(config, 'rules', 'rule', config_source, base_url),
    )

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
            # Cast to typed list for type safety
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

    # Validate each file using parallel execution
    info(f'Validating {len(files_to_check)} files...')

    def validate_single_file(
        file_info: tuple[str, str, str, bool],
    ) -> tuple[str, str, bool, str]:
        """Validate a single file and return result tuple."""
        file_type, original_path, resolved_path, is_remote = file_info
        is_valid, method = validator.validate(resolved_path, is_remote)
        return (file_type, original_path, is_valid, method)

    # Execute validation in parallel (or sequential if CLAUDE_CODE_TOOLBOX_SEQUENTIAL_MODE=1)
    results = execute_parallel(files_to_check, validate_single_file)

    # Process results and print status messages
    all_valid = True
    for file_type, original_path, is_valid, method in results:
        if is_valid:
            # Find the resolved_path for this item (for error messages)
            is_remote = method != 'Local'
            if is_remote:
                info(f'  [OK] {file_type}: {original_path} (remote, validated via {method})')
            else:
                info(f'  [OK] {file_type}: {original_path} (local file exists)')
        else:
            # Find resolved_path for error message
            resolved_path = original_path
            for ft, op, rp, _ir in files_to_check:
                if ft == file_type and op == original_path:
                    resolved_path = rp
                    break
            is_remote = method != 'Local'
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
        remainder = parts[1]  # e.g., "main/configs/my-config.yaml"

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
        return {'Authorization': auth_value}

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
            return {'PRIVATE-TOKEN': env_token}
    elif repo_type == 'github':
        env_token = os.environ.get('GITHUB_TOKEN')
        tokens_checked.append('GITHUB_TOKEN')
        if env_token:
            return build_github_headers(env_token)

    # Check generic REPO_TOKEN as fallback
    env_token = os.environ.get('REPO_TOKEN')
    tokens_checked.append('REPO_TOKEN')
    if env_token:
        if repo_type == 'gitlab':
            return {'PRIVATE-TOKEN': env_token}
        if repo_type == 'github':
            return build_github_headers(env_token)

    # Method 3: Interactive prompt (only if repo type detected and terminal is interactive)
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
    1. Normalize path FIRST (expand tildes and environment variables)
    2. If normalized path is a full URL, return as-is (remote)
    3. If normalized path is ABSOLUTE, return as local (critical fix for tilde paths)
    4. If base_url is configured, combine with resource_path (remote)
    5. If config was loaded from URL, derive base from it (remote)
    6. Otherwise, resolve relative path locally

    Args:
        resource_path: The resource path from config (URL or local path)
        config_source: Where the config was loaded from (URL or local path)
        base_url: Optional base URL override from config

    Returns:
        tuple[str, bool]: (resolved_path, is_remote)
            - resolved_path: Full URL or absolute local path
            - is_remote: True if URL, False if local path
    """
    # CRITICAL FIX: Normalize FIRST (handles ~, $VAR, %VAR%)
    # This ensures tilde paths become absolute BEFORE any URL derivation logic
    normalized_path = normalize_tilde_path(resource_path)

    # 1. If full URL, return as-is (remote)
    if normalized_path.startswith(('http://', 'https://')):
        return normalized_path, True

    # CRITICAL FIX: Check if normalized path is ABSOLUTE
    # Tilde paths (~/.claude/file) become absolute after normalization (/home/user/.claude/file)
    # Absolute paths are DEFINITIONALLY local - they must NOT go through URL derivation
    path_obj = Path(normalized_path)
    if path_obj.is_absolute():
        return str(path_obj.resolve()), False

    # 2. If base-url configured, use it (RELATIVE PATHS ONLY reach here)
    # Use forward slashes for URL path components (normpath may produce backslashes on Windows)
    url_path = normalized_path.replace('\\', '/')
    if base_url:
        # Auto-append {path} if not present
        if '{path}' not in base_url:
            # Add {path} placeholder appropriately
            base_url = base_url + '{path}' if base_url.endswith('/') else base_url + '/{path}'

        # Handle GitLab URL encoding for paths
        if '/api/v4/projects/' in base_url and '/repository/files/' in base_url:
            # URL encode the path for GitLab API
            encoded_path = urllib.parse.quote(url_path, safe='')
            return base_url.replace('{path}', encoded_path), True
        # For other URLs, just replace the placeholder
        return base_url.replace('{path}', url_path), True

    # 3. If config from URL, derive base from it (RELATIVE PATHS ONLY)
    if config_source.startswith(('http://', 'https://')):
        derived_base = derive_base_url(config_source)
        # Handle GitLab URL encoding
        if '/api/v4/projects/' in derived_base and '/repository/files/' in derived_base:
            encoded_path = urllib.parse.quote(url_path, safe='')
            return derived_base.replace('{path}', encoded_path), True
        return derived_base.replace('{path}', url_path), True

    # 4. Relative path with local config - resolve relative to config location
    config_path = Path(config_source)
    # Config source might be just a name from repo library
    # In this case, paths should be resolved relative to current directory
    config_dir = config_path.parent if config_path.is_file() else Path.cwd()

    # Resolve the resource path relative to config directory
    resource_full_path = (config_dir / normalized_path).resolve()
    return str(resource_full_path), False


def _resolve_config_file_paths(config: dict[str, Any], config_source: str) -> dict[str, Any]:
    """Resolve all relative file paths in a config dict using its own source.

    Converts relative file paths to absolute URLs or paths so that after merging,
    each file reference is self-contained and does not depend on the leaf config's
    source for resolution.

    Only resolves paths that are RELATIVE. Absolute paths and full URLs are
    left unchanged (resolve_resource_path passes them through).

    See FILE_REFERENCE_KEYS for the complete list of config keys containing
    file references.

    Args:
        config: Configuration dictionary containing file references.
        config_source: The source URL or path where this config was loaded from.

    Returns:
        A new config dict with file paths resolved. The original dict is not modified.
    """
    result = config.copy()
    base_url = config.get('base-url')

    # --- Simple list keys: agents, slash-commands, rules ---
    for key in ('agents', 'slash-commands', 'rules'):
        items = result.get(key)
        if isinstance(items, list):
            resolved_items = []
            for item in items:
                if isinstance(item, str):
                    resolved_path, _ = resolve_resource_path(item, config_source, base_url)
                    resolved_items.append(resolved_path)
                else:
                    resolved_items.append(item)
            result[key] = resolved_items

    # --- hooks.files ---
    hooks = result.get('hooks')
    if isinstance(hooks, dict):
        hooks = hooks.copy()
        hook_files = hooks.get('files')
        if isinstance(hook_files, list):
            resolved_files = []
            for item in hook_files:
                if isinstance(item, str):
                    resolved_path, _ = resolve_resource_path(item, config_source, base_url)
                    resolved_files.append(resolved_path)
                else:
                    resolved_files.append(item)
            hooks['files'] = resolved_files
        result['hooks'] = hooks

    # --- files-to-download[].source ---
    ftd = result.get('files-to-download')
    if isinstance(ftd, list):
        resolved_ftd = []
        for item in ftd:
            if isinstance(item, dict):
                item = item.copy()
                source = item.get('source')
                if isinstance(source, str):
                    resolved_path, _ = resolve_resource_path(source, config_source, base_url)
                    item['source'] = resolved_path
            resolved_ftd.append(item)
        result['files-to-download'] = resolved_ftd

    # --- skills[].base (uses None for base_url to match validate_all_config_files behavior) ---
    skills = result.get('skills')
    if isinstance(skills, list):
        resolved_skills = []
        for item in skills:
            if isinstance(item, dict):
                item = item.copy()
                skill_base = item.get('base')
                if isinstance(skill_base, str):
                    resolved_path, _ = resolve_resource_path(skill_base, config_source, None)
                    item['base'] = resolved_path
            resolved_skills.append(item)
        result['skills'] = resolved_skills

    # --- command-defaults.system-prompt ---
    cmd_defaults = result.get('command-defaults')
    if isinstance(cmd_defaults, dict):
        cmd_defaults = cmd_defaults.copy()
        sys_prompt = cmd_defaults.get('system-prompt')
        if isinstance(sys_prompt, str):
            resolved_path, _ = resolve_resource_path(sys_prompt, config_source, base_url)
            cmd_defaults['system-prompt'] = resolved_path
        result['command-defaults'] = cmd_defaults

    return result


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

    config_url = f'https://raw.githubusercontent.com/alex-feel/claude-code-artifacts-public/main/{config_spec}'
    info(f'Loading configuration from repository: {config_spec}')

    try:
        # Use the same fetch function for consistency
        content = fetch_url_with_auth(config_url, auth_param=auth_param)
        config = yaml.safe_load(content)
        success(f"Configuration loaded: {config.get('name', config_spec)}")
        return config, config_url
    except urllib.error.HTTPError as e:
        if e.code == 404:
            error(f'Configuration not found in repository: {config_spec}')
            info('Configuration not found in the configurations repository.')
            info('Browse available configurations at:')
            info('  https://github.com/alex-feel/claude-code-artifacts-public')
            info('')
            info('You can also:')
            info('  - Use a local file: ./my-config.yaml')
            info('  - Use a URL: https://example.com/config.yaml')
            raise Exception(f'Configuration not found: {config_spec}') from None
        error(f'Failed to load repository configuration: {e}')
        raise
    except Exception as e:
        if 'Configuration not found' not in str(e):
            error(f'Failed to load repository configuration: {e}')
        raise


def classify_config_source(config_source: str) -> str:
    """Classify the configuration source type.

    Determines how the configuration was loaded based on the source string
    returned by load_config_from_source().

    Args:
        config_source: The source path/URL returned by load_config_from_source()

    Returns:
        One of: "url", "local", "repo"
    """
    if config_source.startswith(('http://', 'https://')):
        return 'url'
    # Local files are resolved to absolute paths by load_config_from_source()
    if os.path.isabs(config_source) or os.sep in config_source or '/' in config_source:
        return 'local'
    return 'repo'


def resolve_config_source_url(config_source: str, config_source_type: str) -> str | None:
    """Resolve the fetch URL for a configuration source.

    For remote sources, returns the URL that can be used to re-fetch the config.
    For local sources, returns None (no remote to check against).

    Args:
        config_source: The source path/URL from load_config_from_source()
        config_source_type: The classified type ("url", "local", "repo")

    Returns:
        The fetchable URL, or None for local sources.
    """
    if config_source_type == 'url':
        return config_source
    if config_source_type == 'repo':
        # Reconstruct the GitHub raw URL (same logic as load_config_from_source)
        name = config_source
        if not name.endswith('.yaml'):
            name += '.yaml'
        return (
            f'https://raw.githubusercontent.com/alex-feel/'
            f'claude-code-artifacts-public/main/{name}'
        )
    # Local sources have no remote URL
    return None


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


def _merge_string_list(
    parent_list: list[str],
    child_list: list[str],
) -> list[str]:
    """Merge two string lists with deduplication, parent items first.

    Args:
        parent_list: Base list of strings.
        child_list: Override list of strings to append.

    Returns:
        Merged list with parent order preserved and new child items appended.
    """
    seen: set[str] = set()
    result: list[str] = []
    for item in parent_list:
        if item not in seen:
            seen.add(item)
            result.append(item)
    for item in child_list:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _merge_named_list(
    parent_list: list[dict[str, Any]],
    child_list: list[dict[str, Any]],
    identity_key: str,
) -> list[dict[str, Any]]:
    """Merge named lists with in-position replacement for matching identities.

    Child items sharing a parent item's identity replace it at the parent's
    original position. New child items (no matching parent) are appended.

    Args:
        parent_list: Base list of dicts.
        child_list: Override list of dicts.
        identity_key: Dict key used as the identity for matching.

    Returns:
        Merged list preserving parent ordering with child overrides and appends.
    """
    child_by_id: dict[str, dict[str, Any]] = {}
    for item in child_list:
        key = item.get(identity_key)
        if key is not None:
            child_by_id[str(key)] = item

    consumed: set[str] = set()
    result: list[dict[str, Any]] = []

    for parent_item in parent_list:
        parent_key = str(parent_item.get(identity_key, ''))
        if parent_key in child_by_id:
            result.append(child_by_id[parent_key])
            consumed.add(parent_key)
        else:
            result.append(parent_item)

    for item in child_list:
        key = str(item.get(identity_key, ''))
        if key not in consumed:
            result.append(item)

    return result


def _merge_hooks(
    parent_hooks: dict[str, Any],
    child_hooks: dict[str, Any],
) -> dict[str, Any]:
    """Merge hooks: files with dedup, events concatenated.

    Args:
        parent_hooks: Parent hooks configuration.
        child_hooks: Child hooks configuration.

    Returns:
        Merged hooks with deduplicated files and concatenated events.
    """
    parent_files = parent_hooks.get('files', [])
    child_files = child_hooks.get('files', [])
    seen_files: set[str] = set()
    merged_files: list[str] = []
    for f in parent_files:
        if f not in seen_files:
            seen_files.add(f)
            merged_files.append(f)
    for f in child_files:
        if f not in seen_files:
            seen_files.add(f)
            merged_files.append(f)

    parent_events = parent_hooks.get('events', [])
    child_events = child_hooks.get('events', [])
    merged_events = list(parent_events) + list(child_events)

    return {'files': merged_files, 'events': merged_events}


def _merge_dependencies(
    parent_deps: dict[str, list[str]],
    child_deps: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Merge dependency dicts per platform with deduplication.

    Args:
        parent_deps: Parent per-platform dependency commands.
        child_deps: Child per-platform dependency commands.

    Returns:
        Merged dependencies with per-platform list concatenation and dedup.
    """
    all_platforms = set(parent_deps.keys()) | set(child_deps.keys())
    result: dict[str, list[str]] = {}
    for plat in sorted(all_platforms):
        parent_cmds = parent_deps.get(plat, [])
        child_cmds = child_deps.get(plat, [])
        result[plat] = _merge_string_list(parent_cmds, child_cmds)
    return result


def _merge_config_key(
    key: str,
    parent_value: object,
    child_value: object,
) -> object:
    """Dispatch merge for a single key based on its type semantics.

    Args:
        key: The configuration key name.
        parent_value: The parent's value for this key.
        child_value: The child's value for this key.

    Returns:
        The merged value using the appropriate strategy for the key type.
    """
    # String list keys: concat + dedup, parent-first order
    if key in ('agents', 'slash-commands', 'rules'):
        p_list = cast(list[str], parent_value) if isinstance(parent_value, list) else []
        c_list = cast(list[str], child_value) if isinstance(child_value, list) else []
        return _merge_string_list(p_list, c_list)

    # Named list keys with identity by 'name'
    if key in ('mcp-servers', 'skills'):
        p_named = cast(list[dict[str, object]], parent_value) if isinstance(parent_value, list) else []
        c_named = cast(list[dict[str, object]], child_value) if isinstance(child_value, list) else []
        return _merge_named_list(p_named, c_named, 'name')

    # Named list key with identity by 'dest'
    if key == 'files-to-download':
        p_files = cast(list[dict[str, object]], parent_value) if isinstance(parent_value, list) else []
        c_files = cast(list[dict[str, object]], child_value) if isinstance(child_value, list) else []
        return _merge_named_list(p_files, c_files, 'dest')

    # Dependencies: per-platform merge
    if key == 'dependencies':
        p_deps = cast(dict[str, list[str]], parent_value) if isinstance(parent_value, dict) else {}
        c_deps = cast(dict[str, list[str]], child_value) if isinstance(child_value, dict) else {}
        return _merge_dependencies(p_deps, c_deps)

    # Hooks: composite merge (files dedup + events concat)
    if key == 'hooks':
        p_hooks = cast(dict[str, Any], parent_value) if isinstance(parent_value, dict) else {}
        c_hooks = cast(dict[str, Any], child_value) if isinstance(child_value, dict) else {}
        return _merge_hooks(p_hooks, c_hooks)

    # Global-config: deep merge with no array union
    if key == 'global-config':
        p_gc = cast(dict[str, Any], parent_value) if isinstance(parent_value, dict) else {}
        c_gc = cast(dict[str, Any], child_value) if isinstance(child_value, dict) else {}
        return deep_merge_settings(p_gc, c_gc, array_union_keys=set())

    # User-settings: deep merge with default array union keys
    if key == 'user-settings':
        p_us = cast(dict[str, Any], parent_value) if isinstance(parent_value, dict) else {}
        c_us = cast(dict[str, Any], child_value) if isinstance(child_value, dict) else {}
        return deep_merge_settings(p_us, c_us, array_union_keys=DEFAULT_ARRAY_UNION_KEYS)

    # Env-variables and os-env-variables: shallow dict merge, null deletes
    if key in ('env-variables', 'os-env-variables'):
        p_env = cast(dict[str, str | None], parent_value) if isinstance(parent_value, dict) else {}
        c_env = cast(dict[str, str | None], child_value) if isinstance(child_value, dict) else {}
        merged_env: dict[str, str | None] = dict(p_env)
        for env_k, env_v in c_env.items():
            if env_v is None:
                merged_env.pop(env_k, None)
            else:
                merged_env[env_k] = env_v
        return merged_env

    # Fallback: replace semantics
    return child_value


def _merge_configs(
    parent: dict[str, Any],
    child: dict[str, Any],
    merge_keys: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Merge parent and child configs with optional per-key merge semantics.

    When merge_keys is None (default), child values completely replace parent
    values (backward-compatible behavior). When merge_keys is provided, keys
    listed in it are merged using type-aware strategies instead of replaced.

    Args:
        parent: The parent configuration (base).
        child: The child configuration (overrides parent).
        merge_keys: Optional set of key names to merge instead of replace.

    Returns:
        Merged configuration with inherit and merge-keys stripped.
    """
    result = parent.copy()

    for key, value in child.items():
        if key in (INHERIT_KEY, MERGE_KEYS_KEY):
            continue
        if (
            merge_keys is not None
            and key in merge_keys
            and key in result
        ):
            result[key] = _merge_config_key(key, result[key], value)
        else:
            result[key] = value

    # Defensive strip of meta-keys from result
    result.pop(INHERIT_KEY, None)
    result.pop(MERGE_KEYS_KEY, None)

    return result


def _validate_merge_keys(
    merge_keys_value: object,
    context: str = '',
) -> frozenset[str] | None:
    """Validate and return a frozenset of merge-keys, or None if not present.

    Args:
        merge_keys_value: The raw value from config.get(MERGE_KEYS_KEY).
        context: Label for error messages (e.g., 'inherit[1]' or '').

    Returns:
        Validated frozenset of merge key names, or None if merge_keys_value is None.

    Raises:
        ValueError: If merge_keys_value is invalid.
    """
    if merge_keys_value is None:
        return None

    prefix = f'{context}: ' if context else ''

    if not isinstance(merge_keys_value, list):
        error(f"{prefix}Invalid 'merge-keys' value: expected list, got {type(merge_keys_value).__name__}")
        raise ValueError(
            f"{prefix}The 'merge-keys' key must be a list of strings, "
            f"got {type(merge_keys_value).__name__}: {merge_keys_value!r}",
        )

    merge_keys_list = cast(list[object], merge_keys_value)

    for i, entry in enumerate(merge_keys_list):
        if not isinstance(entry, str):
            error(f'{prefix}Invalid merge-keys[{i}]: expected string, got {type(entry).__name__}')
            raise ValueError(f'{prefix}merge-keys[{i}] must be a string, got {type(entry).__name__}')

    merge_keys_str = cast(list[str], merge_keys_list)
    invalid_keys = [k for k in merge_keys_str if k not in MERGEABLE_CONFIG_KEYS]
    if invalid_keys:
        error(f'{prefix}Invalid merge-keys: {invalid_keys}')
        raise ValueError(
            f'{prefix}Invalid keys in merge-keys: {invalid_keys}. '
            f'Valid mergeable keys: {sorted(MERGEABLE_CONFIG_KEYS)}',
        )

    return frozenset(merge_keys_str)


def _resolve_list_inherit(
    config: dict[str, Any],
    inherit_list: list[str | dict[str, Any]],
    source: str,
    auth_param: str | None,
    visited: set[str],
    chain: list[InheritanceChainEntry],
) -> tuple[dict[str, Any], list[InheritanceChainEntry]]:
    """Resolve list-based inheritance via flat left-to-right composition.

    When inherit is a list, each entry is loaded raw, its own 'inherit' and
    'merge-keys' keys are stripped (Rules 1 and 3), and entries are composed
    left-to-right using per-entry merge-keys specified in the leaf config's
    structured inherit entries.

    Args:
        config: The leaf configuration (contains the list inherit).
        inherit_list: List of inherit entries (strings or structured dicts/InheritEntry).
        source: Source path/URL of the leaf config.
        auth_param: Optional authentication parameter for private repositories.
        visited: Set of already-visited sources for circular dependency detection.
        chain: Accumulator for the inheritance chain entries.

    Returns:
        Tuple of (merged_config, inheritance_chain).

    Raises:
        ValueError: If circular dependency detected or entry loading fails.
        FileNotFoundError: If a listed config file is not found.
    """
    accumulated: dict[str, Any] | None = None

    for i, entry_raw in enumerate(inherit_list):
        # Extract entry_value (config source) and override_merge_keys from entry
        if isinstance(entry_raw, str):
            entry_value = entry_raw.strip()
            override_merge_keys: list[str] | None = None
        elif isinstance(entry_raw, dict):
            entry_value = str(entry_raw.get('config', '')).strip()
            override_merge_keys = entry_raw.get('merge-keys')
        else:
            # InheritEntry object (from model validation)
            entry_value = entry_raw.config.strip()
            override_merge_keys = entry_raw.merge_keys

        # Resolve path relative to leaf source
        entry_source = _resolve_inherit_path(entry_value, source)

        # Normalize for circular dependency detection
        normalized = _normalize_source_for_comparison(entry_source)
        if normalized in visited:
            cycle_path = ' -> '.join(list(visited) + [normalized])
            error(f'Circular dependency detected at inherit[{i}]')
            error(f'Cycle: {cycle_path}')
            raise ValueError(
                f'Circular dependency detected: {normalized} was already visited. '
                f'Inheritance chain: {cycle_path}',
            )
        visited.add(normalized)

        # Load raw config
        info(f'Loading inherit[{i}]: {entry_value}')
        try:
            entry_config, actual_source = load_config_from_source(
                entry_source, auth_param,
            )
        except FileNotFoundError:
            error(f'Configuration not found at inherit[{i}]: {entry_value}')
            error(f'Resolved path: {entry_source}')
            raise
        except Exception as e:
            error(f'Failed to load inherit[{i}]: {entry_value}')
            error(f'Error: {e}')
            raise

        # Resolve entry's file paths using its own source before composition
        entry_config = _resolve_config_file_paths(entry_config, actual_source)

        # Rule 1: Strip own inherit from entry (completely ignored)
        own_inherit = entry_config.get(INHERIT_KEY)
        if own_inherit is not None:
            info(f"inherit[{i}]: own 'inherit' key stripped (list composition mode)")

        # Rule 3 (per-entry from leaf): Strip and IGNORE entry's own merge-keys.
        # Per-entry merge behavior comes from the leaf's structured entries.
        own_merge_keys = entry_config.get(MERGE_KEYS_KEY)
        if own_merge_keys is not None:
            info(f"inherit[{i}]: own 'merge-keys' stripped (leaf controls merge semantics)")

        # Validate override merge-keys from the structured entry (if provided)
        validated_override = _validate_merge_keys(
            override_merge_keys,
            context=f'inherit[{i}]',
        )

        # Add entry to inheritance chain
        chain.append(InheritanceChainEntry(
            source=actual_source,
            source_type=classify_config_source(actual_source),
            name=entry_config.get('name', entry_value),
        ))

        if accumulated is None:
            # First entry becomes the base; merge-keys are moot (no predecessor).
            # Defense-in-depth: strip meta-keys here even though _merge_configs also
            # strips them, because first entry bypasses _merge_configs entirely.
            accumulated = {
                k: v for k, v in entry_config.items()
                if k not in (INHERIT_KEY, MERGE_KEYS_KEY)
            }
            if validated_override is not None:
                debug_log(f'inherit[{i}]: per-entry merge-keys ignored (first entry, no predecessor)')
        else:
            # Subsequent entries: compose with accumulated using leaf-specified per-entry merge-keys
            accumulated = _merge_configs(accumulated, entry_config, merge_keys=validated_override)

        success(f'Loaded inherit[{i}]: {entry_value}')

    # Final: merge leaf config on top of accumulated base (Rule 4)
    assert accumulated is not None
    leaf_merge_keys = _validate_merge_keys(config.get(MERGE_KEYS_KEY))
    merged = _merge_configs(accumulated, config, merge_keys=leaf_merge_keys)

    return merged, chain


def resolve_config_inheritance(
    config: dict[str, Any],
    source: str,
    auth_param: str | None = None,
    visited: set[str] | None = None,
    depth: int = 0,
    chain: list[InheritanceChainEntry] | None = None,
) -> tuple[dict[str, Any], list[InheritanceChainEntry]]:
    """Resolve configuration inheritance by loading and merging parent configs.

    Implements top-level key override semantics by default: child config values
    completely replace parent values for the same key. When 'merge-keys' is
    specified, listed keys are merged using type-aware strategies instead.

    Supports two modes of inheritance:
    - Single string: recursive chain resolution (child -> parent -> grandparent)
    - List of strings/objects: flat left-to-right composition where each entry's
      own 'inherit' and 'merge-keys' keys are stripped, and per-entry merge-keys
      are specified via structured {config: ..., merge-keys: [...]} entries

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
        chain: Accumulator for the inheritance chain entries.
            Used internally. Callers should not provide this.

    Returns:
        Tuple of (merged_config, inheritance_chain) where merged_config is the
        configuration with inheritance resolved and inheritance_chain is the
        list of InheritanceChainEntry from root ancestor to immediate parent.

    Raises:
        ValueError: If circular dependency is detected, maximum inheritance
            depth is exceeded, or inherit value is invalid.
        FileNotFoundError: If parent config file not found (propagated from
            load_config_from_source).

    Examples:
        >>> # Simple inheritance
        >>> child = {'inherit': 'base.yaml', 'name': 'Child'}
        >>> resolved, chain = resolve_config_inheritance(child, 'child.yaml')
        >>> # resolved contains parent's keys + child's 'name' override

        >>> # List inheritance (flat composition)
        >>> child = {'inherit': ['base.yaml', 'ext.yaml'], 'model': 'opus'}
        >>> resolved, chain = resolve_config_inheritance(child, 'child.yaml')
        >>> # entries composed left-to-right, each entry's own inherit stripped
    """
    # Initialize visited set for circular dependency detection
    if visited is None:
        visited = set()

    # Initialize chain accumulator
    if chain is None:
        chain = []

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
        # Warn if merge-keys present without inherit
        if config.get(MERGE_KEYS_KEY) is not None:
            warning(
                "Warning: 'merge-keys' has no effect without 'inherit'. "
                "Did you mean to add an 'inherit' key?",
            )
        # No inheritance - return config as-is (without meta-keys)
        return {k: v for k, v in config.items() if k not in (INHERIT_KEY, MERGE_KEYS_KEY)}, chain

    # Handle list inherit
    if isinstance(inherit_value, list):
        if not inherit_value:
            error("Empty 'inherit' list in configuration")
            raise ValueError("The 'inherit' list cannot be empty")

        # Validate all entries are strings or structured dicts
        for i, entry in enumerate(inherit_value):
            if isinstance(entry, str):
                stripped = entry.strip()
                if not stripped:
                    error(f'Empty string in inherit[{i}]')
                    raise ValueError(f'inherit[{i}] cannot be empty or whitespace-only')
            elif isinstance(entry, dict):
                if 'config' not in entry:
                    error(f'inherit[{i}]: structured entry missing required "config" key')
                    raise ValueError(
                        f'inherit[{i}] structured entry must have a "config" key',
                    )
            elif hasattr(entry, 'config'):
                # InheritEntry object from model validation
                pass
            else:
                error(f'Invalid inherit[{i}]: expected string or {{config: ...}}, got {type(entry).__name__}')
                raise ValueError(
                    f'inherit[{i}] must be a string or {{config: ..., merge-keys: [...]}} object, '
                    f'got {type(entry).__name__}: {entry!r}',
                )

        # Single-element list handling
        if len(inherit_value) == 1:
            single = inherit_value[0]
            if isinstance(single, str):
                # Plain string: normalize to string, use recursive chain
                inherit_value = single.strip()
                # Fall through to the string path below
            else:
                # Structured entry: route to _resolve_list_inherit (composition mode).
                # Preserves per-entry merge-keys and strips loaded config's own merge-keys.
                return _resolve_list_inherit(
                    config=config,
                    inherit_list=inherit_value,
                    source=source,
                    auth_param=auth_param,
                    visited=visited,
                    chain=chain,
                )
        else:
            # Multi-element list: flat composition (Rules 1, 2, 3, 4)
            return _resolve_list_inherit(
                config=config,
                inherit_list=inherit_value,
                source=source,
                auth_param=auth_param,
                visited=visited,
                chain=chain,
            )
    elif not isinstance(inherit_value, str):
        error(f"Invalid 'inherit' value: expected string or list, got {type(inherit_value).__name__}")
        raise ValueError(
            f"The 'inherit' key must be a string or list of strings/objects, "
            f"got {type(inherit_value).__name__}: {inherit_value!r}",
        )

    # --- String path (single inherit) ---

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

    # Recursively resolve parent's inheritance (chain accumulates ancestors)
    resolved_parent, chain = resolve_config_inheritance(
        parent_config,
        actual_parent_source,
        auth_param=auth_param,
        visited=visited,
        depth=depth + 1,
        chain=chain,
    )

    # Resolve parent's file paths using parent's own source before merging
    resolved_parent = _resolve_config_file_paths(resolved_parent, actual_parent_source)

    # Append the parent entry to the chain after recursion resolves deeper ancestors
    chain.append(InheritanceChainEntry(
        source=actual_parent_source,
        source_type=classify_config_source(actual_parent_source),
        name=parent_config.get('name', inherit_value),
    ))

    # Extract and validate merge-keys from child config
    validated_merge_keys = _validate_merge_keys(config.get(MERGE_KEYS_KEY))

    # Merge: parent first, then child overrides
    merged = _merge_configs(resolved_parent, config, merge_keys=validated_merge_keys)

    success(f'Inherited from: {inherit_value}')

    return merged, chain


def collect_installation_plan(
    config: dict[str, Any],
    config_source: str,
    config_name: str,
    config_version: str | None,
    inheritance_chain: list[InheritanceChainEntry],
    args: argparse.Namespace,
) -> InstallationPlan:
    """Collect all installation artifacts into a structured plan.

    Extracts resource lists, dependency commands, settings, and security
    analysis from the fully resolved configuration without executing
    any installation steps.

    Args:
        config: Fully resolved configuration dictionary (inheritance merged).
        config_source: Source path/URL of the configuration.
        config_name: Original config name as specified by user.
        config_version: Pre-extracted config version from the root config
            (before inheritance resolution). None if root config has no version.
        inheritance_chain: Resolved inheritance chain entries.
        args: Parsed CLI arguments.

    Returns:
        InstallationPlan containing all artifacts to be installed.
    """
    config_source_type = classify_config_source(config_source)

    # Extract resources
    hooks_dict: dict[str, Any] = config.get('hooks') or {}
    hooks_files: list[str] = hooks_dict.get('files') or []
    hooks_events_list: list[Any] = hooks_dict.get('events') or []
    hooks_events: list[dict[str, Any]] = [
        cast(dict[str, Any], e) for e in hooks_events_list if isinstance(e, dict)
    ]

    # Extract files-to-download
    ftd_raw: list[Any] = config.get('files-to-download') or []
    files_to_download: list[dict[str, Any]] = [
        cast(dict[str, Any], f) for f in ftd_raw if isinstance(f, dict)
    ]

    # Extract skills
    skills_raw: list[Any] = config.get('skills') or []
    skills_list: list[dict[str, Any]] = [
        cast(dict[str, Any], s) for s in skills_raw if isinstance(s, dict)
    ]

    # Extract MCP servers
    mcp_raw: list[Any] = config.get('mcp-servers') or []
    mcp_servers: list[dict[str, Any]] = [
        cast(dict[str, Any], s) for s in mcp_raw if isinstance(s, dict)
    ]

    # Extract dependency commands for current OS only
    dependency_commands: dict[str, list[str]] = {}
    deps_raw: dict[str, Any] = config.get('dependencies') or {}
    current_platform_key = PLATFORM_SYSTEM_TO_CONFIG_KEY.get(platform.system())
    relevant_keys = ['common']
    if current_platform_key:
        relevant_keys.append(current_platform_key)
    for platform_key in relevant_keys:
        dep_cmds: list[Any] = deps_raw.get(platform_key) or []
        if dep_cmds:
            dependency_commands[platform_key] = [str(c) for c in dep_cmds]

    # Extract command defaults
    cmd_defaults: dict[str, Any] = config.get('command-defaults') or {}
    system_prompt: str | None = cmd_defaults.get('system-prompt')
    system_prompt_mode: str = cmd_defaults.get('mode') or 'replace'

    # Extract command names
    command_names_raw = config.get('command-names')
    command_names: list[str] = []
    if isinstance(command_names_raw, str):
        command_names = [command_names_raw]
    elif isinstance(command_names_raw, list):
        command_names = [str(item) for item in cast(list[object], command_names_raw)]

    # Unknown key detection
    unknown_keys = sorted(k for k in config if k not in KNOWN_CONFIG_KEYS)

    # Sensitive path detection
    sensitive_paths: list[str] = []
    for ftd in files_to_download:
        dest = ftd.get('dest', '')
        if isinstance(dest, str):
            for prefix in SENSITIVE_PATH_PREFIXES:
                if dest.startswith(prefix):
                    sensitive_paths.append(dest)
                    break

    return InstallationPlan(
        config_name=config.get('name', config_name),
        config_source=config_source,
        config_source_type=config_source_type,
        config_version=config_version,
        config_description=config.get('description'),
        inheritance_chain=inheritance_chain,
        agents=config.get('agents', []) or [],
        slash_commands=config.get('slash-commands', []) or [],
        rules=config.get('rules', []) or [],
        skills=skills_list,
        files_to_download=files_to_download,
        hooks_files=hooks_files,
        hooks_events=hooks_events,
        mcp_servers=mcp_servers,
        dependency_commands=dependency_commands,
        model=config.get('model'),
        system_prompt=system_prompt,
        system_prompt_mode=system_prompt_mode,
        command_names=command_names,
        claude_code_version=config.get('claude-code-version'),
        install_nodejs=bool(config.get('install-nodejs')),
        skip_install=args.skip_install,
        permissions=config.get('permissions'),
        env_variables=config.get('env-variables'),
        os_env_variables=config.get('os-env-variables'),
        user_settings=config.get('user-settings'),
        global_config=config.get('global-config'),
        always_thinking_enabled=config.get('always-thinking-enabled'),
        effort_level=config.get('effort-level'),
        company_announcements=config.get('company-announcements'),
        attribution=config.get('attribution'),
        status_line=config.get('status-line'),
        unknown_keys=unknown_keys,
        sensitive_paths=sensitive_paths,
    )


def _suggest_known_key(unknown_key: str) -> str | None:
    """Suggest the closest KNOWN_CONFIG_KEYS match for an unknown key.

    Uses difflib.get_close_matches with a 0.6 cutoff for fuzzy matching.
    Returns the best match, or None if no close match exists.

    Args:
        unknown_key: The unrecognized configuration key.

    Returns:
        The closest matching known key, or None.
    """
    import difflib
    matches = difflib.get_close_matches(unknown_key, KNOWN_CONFIG_KEYS, n=1, cutoff=0.6)
    return matches[0] if matches else None


def display_installation_summary(
    plan: InstallationPlan,
    output: TextIO | None = None,
) -> None:
    """Display a human-readable installation summary.

    Renders the installation plan as a formatted terminal summary with
    color-coded sections. When stdout is piped, output goes to stderr
    so users still see the summary.

    Args:
        plan: The installation plan to display.
        output: Output stream. If None, uses stderr when stdout is piped,
            otherwise stdout.
    """
    out = output if output is not None else (
        sys.stderr if not sys.stdout.isatty() else sys.stdout
    )

    def _print(*args: object) -> None:
        print(*args, file=out)

    _print()
    _print(f'{Colors.CYAN}========================================================================{Colors.NC}')
    _print(f'{Colors.CYAN}                    Installation Summary{Colors.NC}')
    _print(f'{Colors.CYAN}========================================================================{Colors.NC}')
    _print()

    # Config metadata
    _print(f'{Colors.BOLD}Configuration:{Colors.NC} {plan.config_name}')
    if plan.config_description:
        for line in plan.config_description.splitlines():
            _print(f'  {line}')
    _print(f'{Colors.BOLD}Source:{Colors.NC} {plan.config_source} ({plan.config_source_type})')
    _print(f'{Colors.BOLD}Version:{Colors.NC} {plan.config_version or "not specified"}')

    # Inheritance chain
    if len(plan.inheritance_chain) > 1:
        _print()
        _print(f'{Colors.BOLD}Inheritance Chain:{Colors.NC}')
        for i, entry in enumerate(plan.inheritance_chain, 1):
            marker = '  <-- current' if i == len(plan.inheritance_chain) else ''
            _print(f'  {i}. {entry.name} ({entry.source_type}){marker}')

    # Resources
    _print()
    _print(f'{Colors.BOLD}Resources:{Colors.NC}')
    _print(f'  * Agents: {len(plan.agents)}')
    _print(f'  * Slash commands: {len(plan.slash_commands)}')
    _print(f'  * Rules: {len(plan.rules)}')
    _print(f'  * Skills: {len(plan.skills)}')
    _print(f'  * Files to download: {len(plan.files_to_download)}')
    _print(f'  * Hook files: {len(plan.hooks_files)}')
    _print(f'  * Hook events: {len(plan.hooks_events)}')
    if plan.hooks_events:
        type_counts: dict[str, int] = {}
        for evt in plan.hooks_events:
            t = evt.get('type', 'command')
            type_counts[t] = type_counts.get(t, 0) + 1
        type_parts = [f'{count} {name}' for name, count in sorted(type_counts.items())]
        _print(f'    ({", ".join(type_parts)})')
    _print(f'  * MCP servers: {len(plan.mcp_servers)}')

    # Claude Code installation
    _print()
    if plan.skip_install:
        _print('  * Claude Code: skip (--skip-install)')
    else:
        version_str = plan.claude_code_version or 'latest'
        _print(f'  * Claude Code: install (version: {version_str})')
    if plan.install_nodejs:
        _print('  * Node.js: install if needed')

    # Settings
    settings_items: list[str] = []
    if plan.model:
        settings_items.append(f'Model: {plan.model}')
    if plan.system_prompt:
        settings_items.append(f'System prompt: {plan.system_prompt_mode}')
    if plan.permissions:
        perm_parts: list[str] = []
        if 'default-mode' in plan.permissions:
            perm_parts.append(f"default-mode={plan.permissions['default-mode']}")
        if 'allow' in plan.permissions:
            perm_parts.append(f"{len(plan.permissions['allow'])} allow")
        if 'deny' in plan.permissions:
            perm_parts.append(f"{len(plan.permissions['deny'])} deny")
        if 'ask' in plan.permissions:
            perm_parts.append(f"{len(plan.permissions['ask'])} ask")
        settings_items.append(f"Permissions: {', '.join(perm_parts)}")
    if plan.env_variables:
        settings_items.append(f'Environment variables: {len(plan.env_variables)}')
    if plan.os_env_variables:
        settings_items.append(f'OS environment variables: {len(plan.os_env_variables)}')
    if plan.effort_level:
        settings_items.append(f'Effort level: {plan.effort_level}')
    if plan.always_thinking_enabled is not None:
        settings_items.append(f'Always thinking: {plan.always_thinking_enabled}')
    if plan.user_settings:
        null_keys = [k for k, v in plan.user_settings.items() if v is None]
        set_keys = [k for k, v in plan.user_settings.items() if v is not None]
        parts: list[str] = []
        if set_keys:
            parts.append(f'{len(set_keys)} set')
        if null_keys:
            parts.append(f'{len(null_keys)} delete')
        settings_items.append(f"User settings: {', '.join(parts)}")
        settings_items.extend(
            f'  {Colors.RED}[DELETE]{Colors.NC} {k}' for k in null_keys
        )
    if plan.global_config:
        null_keys = [k for k, v in plan.global_config.items() if v is None]
        set_keys = [k for k, v in plan.global_config.items() if v is not None]
        parts = []
        if set_keys:
            parts.append(f'{len(set_keys)} set')
        if null_keys:
            parts.append(f'{len(null_keys)} delete')
        settings_items.append(f"Global config: {', '.join(parts)}")
        settings_items.extend(
            f'  {Colors.RED}[DELETE]{Colors.NC} {k}' for k in null_keys
        )
    if plan.company_announcements:
        settings_items.append(f'Company announcements: {len(plan.company_announcements)}')
    if plan.command_names:
        settings_items.append(f"Command names: {', '.join(plan.command_names)}")

    if settings_items:
        _print()
        _print(f'{Colors.BOLD}Settings:{Colors.NC}')
        for item in settings_items:
            _print(f'  * {item}')

    # Dependency commands (highlighted in yellow -- most dangerous)
    if plan.dependency_commands:
        _print()
        _print(f'{Colors.YELLOW}{Colors.BOLD}Dependencies (shell commands):{Colors.NC}')
        for platform_key, cmds in plan.dependency_commands.items():
            _print(f'  {Colors.YELLOW}[{platform_key}]{Colors.NC}')
            for cmd in cmds:
                _print(f'    $ {cmd}')

    # Auto-injected items section (green)
    if plan.auto_injected_items:
        _print()
        _print(f'{Colors.GREEN}{Colors.BOLD}Auto-update controls (version pinned):{Colors.NC}')
        for item in plan.auto_injected_items:
            _print(f'  {Colors.GREEN}[auto] {item}{Colors.NC}')

    # Attention section (red)
    has_attention = plan.sensitive_paths or plan.unknown_keys
    if has_attention:
        _print()
        _print(f'{Colors.RED}{Colors.BOLD}[!] ATTENTION:{Colors.NC}')
        for path in plan.sensitive_paths:
            _print(f'  {Colors.RED}[!] Sensitive path: {path}{Colors.NC}')
        for key in plan.unknown_keys:
            suggestion = _suggest_known_key(key)
            if suggestion:
                _print(f'  {Colors.YELLOW}[?] Unknown config key: {key!r} (did you mean {suggestion!r}?){Colors.NC}')
            else:
                _print(f'  {Colors.YELLOW}[?] Unknown config key: {key!r}{Colors.NC}')


def _dev_tty_available() -> bool:
    """Check if /dev/tty is available for interactive input."""
    if sys.platform != 'win32':
        try:
            with open('/dev/tty'):
                return True
        except OSError:
            pass
    return False


def _get_user_confirmation(prompt: str) -> str:
    """Get user input with /dev/tty fallback for piped stdin.

    On Unix systems, when stdin is not a TTY (e.g., curl | bash),
    attempts to read from /dev/tty as a best-effort fallback. This is
    a standard pattern used by sudo, ssh, and gpg.

    Args:
        prompt: The prompt string to display.

    Returns:
        User's input string (stripped), or empty string on EOF/error.
    """
    # Try stdin first if it's a TTY
    if sys.stdin.isatty():
        try:
            return input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            return ''

    # Best-effort /dev/tty fallback (Unix only)
    if sys.platform != 'win32':
        try:
            with open('/dev/tty') as tty:
                # Write prompt to stderr (stdout may be piped)
                sys.stderr.write(prompt)
                sys.stderr.flush()
                return tty.readline().strip()
        except (OSError, EOFError):
            pass

    # No interactive input available
    return ''


def confirm_installation(
    plan: InstallationPlan,
    auto_confirm: bool = False,
    dry_run: bool = False,
) -> bool:
    """Gate installation execution on explicit user consent.

    Implements the confirmation flow:
    1. --dry-run or CLAUDE_CODE_TOOLBOX_DRY_RUN=1: display summary, return False (caller exits 0)
    2. --yes or CLAUDE_CODE_TOOLBOX_CONFIRM_INSTALL=1: display summary, return True
    3. Interactive TTY: prompt user with [y/N]
    4. /dev/tty available: prompt via /dev/tty
    5. Non-interactive: display summary + guidance, return False (caller exits 1)

    Args:
        plan: The installation plan to confirm.
        auto_confirm: Whether to auto-confirm (--yes flag or env var).
        dry_run: Whether this is a dry-run (show plan, do not install).

    Returns:
        True if installation should proceed, False otherwise.
    """
    # Always display summary (audit trail for auto-confirm, info for dry-run)
    display_installation_summary(plan)

    # Dry run: show summary and signal caller to exit 0
    if dry_run:
        print()
        info('Dry run complete. No changes were made.')
        return False

    # Auto-confirm: show summary, proceed
    if auto_confirm:
        print()
        info('Auto-confirmed via --yes flag or CLAUDE_CODE_TOOLBOX_CONFIRM_INSTALL=1')
        return True

    # Check if ANY interactive input is possible
    can_interact = sys.stdin.isatty()

    # Try /dev/tty fallback on Unix when stdin is piped
    can_tty_fallback = False
    if not can_interact and sys.platform != 'win32':
        can_tty_fallback = _dev_tty_available()

    if not can_interact and not can_tty_fallback:
        # Non-interactive mode: refuse with guidance
        print()
        error('Cannot proceed: no interactive terminal available')
        print()
        info('To auto-confirm in non-interactive mode, use one of:')
        info('  1. Pass --yes flag: setup_environment.py <config> --yes')
        info('  2. Set environment variable: CLAUDE_CODE_TOOLBOX_CONFIRM_INSTALL=1')
        info('  3. Preview only: setup_environment.py <config> --dry-run')
        info('  4. Set environment variable: CLAUDE_CODE_TOOLBOX_DRY_RUN=1')
        info('')
        info('Additional environment variables for piped invocations:')
        info('  CLAUDE_CODE_TOOLBOX_SKIP_INSTALL=1  Skip Claude Code installation')
        info('  CLAUDE_CODE_TOOLBOX_NO_ADMIN=1      Do not request admin elevation')
        info('  CLAUDE_CODE_TOOLBOX_ENV_AUTH=<val>   Authentication (header:value)')
        return False

    # Interactive confirmation
    print()
    response = _get_user_confirmation(
        f'{Colors.YELLOW}Proceed with installation? [y/N]: {Colors.NC}',
    )

    if response.lower() in ('y', 'yes'):
        return True

    info('Installation cancelled by user.')
    return False


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
        if platform.system() == 'Linux' and not shutil.which('zsh'):
            config_files = [f for f in config_files if not f.name.startswith('.zsh')]

        # On both Linux and macOS, only include fish config if fish is installed
        if not shutil.which('fish'):
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
                    # reg delete does not broadcast WM_SETTINGCHANGE (unlike setx)
                    _broadcast_wm_settingchange()
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

        # Fish universal variables: propagate immediately to all running Fish instances
        # config.fish (set -gx) remains the durable persistence mechanism;
        # set -Ux provides instant propagation to open Fish sessions
        if shutil.which('fish'):
            try:
                if value is None:
                    subprocess.run(
                        ['fish', '-c', f'set -Ue {name}'],
                        capture_output=True, check=False, timeout=5,
                    )
                else:
                    subprocess.run(
                        ['fish', '-c', f'set -Ux {name} "{value}"'],
                        capture_output=True, check=False, timeout=5,
                    )
            except (OSError, subprocess.TimeoutExpired):
                pass  # Non-critical: config.fish write is the durable mechanism

    return all_success


def set_os_env_variable(name: str, value: str | None) -> bool:
    """Set or delete an OS-level persistent environment variable.

    This function sets environment variables that persist across shell sessions
    AND updates the current process environment for immediate effect.
    - On Windows: Uses setx (set) or registry (delete) + os.environ
    - On macOS/Linux: Writes to all shell config files + os.environ

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

    # Update current process environment for immediate effect
    # This ensures child processes (e.g., Claude Code) see the change
    if result:
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value

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
    deleted_names: list[str] = []

    for name, value in env_vars.items():
        if value is None:
            # Delete the variable
            info(f'Deleting environment variable: {name}')
            if set_os_env_variable(name, None):
                delete_count += 1
                deleted_names.append(name)
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

    # Print unset guidance for deleted variables on Unix
    if sys.platform != 'win32' and deleted_names:
        info('To remove deleted variable(s) from your current shell session, run:')
        for var_name in deleted_names:
            print(f'  unset {var_name}')
        if shutil.which('fish'):
            info('For Fish shell:')
            for var_name in deleted_names:
                print(f'  set -e {var_name}')

    # Broadcast WM_SETTINGCHANGE after all env var operations (Windows)
    if sys.platform == 'win32' and (set_count > 0 or delete_count > 0):
        _broadcast_wm_settingchange()

    return failed_count == 0


def generate_env_loader_files(
    os_env_vars: dict[str, str | None],
    command_names: list[str] | None,
    config_base_dir: Path | None,
) -> dict[str, Path]:
    """Generate shell-specific env loader files for OS environment variables.

    Creates Rustup-pattern env files that can be sourced by launchers
    and users. Contains ONLY os-env-variables (NOT env-variables,
    which are handled by Claude Code's config.json env key).

    Per-command files (when command_names provided):
        ~/.claude/{cmd}/env.sh      (Bash/Zsh)
        ~/.claude/{cmd}/env.fish    (Fish, if Fish installed)
        ~/.claude/{cmd}/env.ps1     (PowerShell, Windows only)
        ~/.claude/{cmd}/env.cmd     (CMD batch, Windows only)

    Args:
        os_env_vars: Dict of env var names to values. None values = deletions
                     (excluded from loader files since the var should not exist).
        command_names: List of command names, or None for non-command configs.
        config_base_dir: Base dir for per-command files (e.g., ~/.claude/{cmd}/).

    Returns:
        Dict mapping file type to generated Path (e.g., {"sh": Path(...)}).
    """
    # Filter to only non-None values (deletions are excluded from loader files)
    active_vars = {k: str(v) for k, v in os_env_vars.items() if v is not None}

    if not active_vars:
        return {}

    generated: dict[str, Path] = {}

    # Build file content for each shell type
    sh_header = '# Auto-generated by claude-code-toolbox -- do not edit manually\n'
    sh_header += '# Re-run setup to update. Source this file to load OS env vars.\n'

    fish_header = '# Auto-generated by claude-code-toolbox -- do not edit manually\n'
    fish_header += '# Re-run setup to update. Source this file to load OS env vars.\n'

    ps1_header = '# Auto-generated by claude-code-toolbox -- do not edit manually\n'
    ps1_header += '# Re-run setup to update. Dot-source this file to load OS env vars.\n'

    # Bash/Zsh content
    sh_lines = [sh_header]
    for name, value in active_vars.items():
        # Escape special characters for double-quoted bash strings
        escaped = value.replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$').replace('`', '\\`')
        sh_lines.append(f'export {name}="{escaped}"')
    sh_content = '\n'.join(sh_lines) + '\n'

    # Fish content
    fish_lines = [fish_header]
    for name, value in active_vars.items():
        # Escape special characters for double-quoted fish strings
        escaped = value.replace('\\', '\\\\').replace('"', '\\"')
        fish_lines.append(f'set -gx {name} "{escaped}"')
    fish_content = '\n'.join(fish_lines) + '\n'

    # PowerShell content
    ps1_lines = [ps1_header]
    for name, value in active_vars.items():
        # Single-quote for literal PowerShell strings; double internal single-quotes
        escaped = value.replace("'", "''")
        ps1_lines.append(f"$env:{name} = '{escaped}'")
    ps1_content = '\n'.join(ps1_lines) + '\n'

    # CMD batch content (Windows only)
    cmd_header = '@echo off\n'
    cmd_header += 'REM Auto-generated by claude-code-toolbox -- do not edit manually\n'
    cmd_header += 'REM Re-run setup to update. Call this file to load OS env vars.\n'

    cmd_lines = [cmd_header]
    for name, value in active_vars.items():
        # Double percent signs for batch files (% -> %%)
        escaped = value.replace('%', '%%')
        cmd_lines.append(f'SET "{name}={escaped}"')
    cmd_content = '\n'.join(cmd_lines) + '\n'

    has_fish = bool(shutil.which('fish'))

    def _write_loader(
        directory: Path,
        sh_name: str,
        fish_name: str | None,
        ps1_name: str | None,
        cmd_name: str | None,
    ) -> None:
        """Write loader files into the given directory."""
        directory.mkdir(parents=True, exist_ok=True)

        sh_path = directory / sh_name
        sh_path.write_text(sh_content, newline='\n')
        generated[f'sh:{sh_path}'] = sh_path

        if fish_name and has_fish:
            fish_path = directory / fish_name
            fish_path.write_text(fish_content, newline='\n')
            generated[f'fish:{fish_path}'] = fish_path

        if ps1_name and sys.platform == 'win32':
            ps1_path = directory / ps1_name
            ps1_path.write_text(ps1_content)
            generated[f'ps1:{ps1_path}'] = ps1_path

        if cmd_name and sys.platform == 'win32':
            cmd_path = directory / cmd_name
            cmd_path.write_text(cmd_content)
            generated[f'cmd:{cmd_path}'] = cmd_path

    # Per-command files
    if command_names and config_base_dir:
        _write_loader(config_base_dir, 'env.sh', 'env.fish', 'env.ps1', 'env.cmd')

    return generated


# --- Standalone Node.js installation functions ---
# These functions provide Node.js installation capability without importing
# from install_claude.py. Both scripts MUST be fully standalone.


def _parse_node_version(version_str: str) -> tuple[int, int, int] | None:
    """Parse version string to tuple."""
    match = re.match(r'v?(\d+)\.(\d+)\.(\d+)', version_str)
    if match:
        major = int(match.group(1))
        minor = int(match.group(2))
        patch = int(match.group(3))
        return (major, minor, patch)
    return None


def _compare_node_versions(current: str, required: str) -> bool:
    """Check if current version meets required version."""
    current_tuple = _parse_node_version(current)
    required_tuple = _parse_node_version(required)
    if not current_tuple or not required_tuple:
        return False
    return current_tuple >= required_tuple


def _get_node_version() -> str | None:
    """Get installed Node.js version."""
    node_path = shutil.which('node')
    if not node_path:
        return None

    result = run_command([node_path, '--version'])
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def _check_winget_available() -> bool:
    """Check if winget is available on Windows."""
    return shutil.which('winget') is not None


def _install_nodejs_winget(scope: str = 'user') -> bool:
    """Install Node.js using winget on Windows."""
    if not _check_winget_available():
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


def _install_nodejs_direct() -> bool:
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
                saved_opener = getattr(urllib.request, '_opener', None) or urllib.request.build_opener()
                urllib.request.install_opener(opener)
                try:
                    urlretrieve(installer_url, temp_path)
                finally:
                    urllib.request.install_opener(saved_opener)
            else:
                raise

        # Install based on OS
        if system == 'Windows':
            # Create log directory for MSI installation
            log_dir = Path(tempfile.gettempdir()) / 'claude-installer-logs'
            log_dir.mkdir(exist_ok=True)
            log_file = log_dir / f'nodejs-install-{int(time.time())}.log'

            info('Installing Node.js silently...')

            result = run_command([
                'msiexec',
                '/i',
                temp_path,
                '/qn',
                '/norestart',
                '/l*v',
                str(log_file),
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
                error(f'Node.js installer exited with code {result.returncode}')

                if log_file.exists():
                    warning(f'Installation log available at: {log_file}')
                    try:
                        log_content = log_file.read_text(encoding='utf-16-le', errors='ignore')
                        lines = log_content.splitlines()
                        if lines:
                            error_context = '\n'.join(lines[-50:])
                            info('Last 50 lines of installation log:')
                            print(error_context)
                    except Exception as e:
                        warning(f'Could not read log file: {e}')

                info('Troubleshooting steps:')
                info('1. Check if Node.js is already partially installed')
                info('2. Remove Node.js from Control Panel if present')
                info('3. Clear Node.js entries from registry (regedit)')
                info('4. Remove Node.js from PATH environment variable')
                info('5. Rerun installer as Administrator')

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


def _install_nodejs_homebrew() -> bool:
    """Install Node.js LTS using Homebrew on macOS."""
    if not shutil.which('brew'):
        info('Installing Homebrew first...')
        result = run_command([
            '/bin/bash',
            '-c',
            '$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)',
        ])
        if result.returncode != 0:
            return False

    info('Installing Node.js LTS (v22) using Homebrew...')
    run_command(['brew', 'update'])
    result = run_command(['brew', 'install', 'node@22'])

    if result.returncode != 0:
        return False

    # node@22 is keg-only; create symlinks so node is available in PATH
    link_result = run_command(['brew', 'link', '--force', '--overwrite', 'node@22'])
    if link_result.returncode != 0:
        warning('brew link failed for node@22; node may not be in PATH')

    success('Node.js LTS installed via Homebrew')
    return True


def _install_nodejs_apt() -> bool:
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


def _verify_nodejs_version() -> bool:
    """Verify installed Node.js meets minimum version requirements.

    Returns:
        True if Node.js version is acceptable, False otherwise.
    """
    node_version = _get_node_version()
    if not node_version:
        return False
    return _compare_node_versions(node_version, MIN_NODE_VERSION)


def _ensure_nodejs() -> bool:
    """Ensure Node.js is installed and meets minimum version.

    Provides standalone Node.js installation for general purposes
    (e.g., npx-based MCP servers). Does not check Claude Code npm
    compatibility since this script does not install Claude Code.

    Returns:
        True if Node.js is installed and meets requirements, False otherwise.
    """
    info('Checking Node.js installation...')

    # On Windows, check standard installation location even if not in PATH
    if platform.system() == 'Windows':
        nodejs_path = r'C:\Program Files\nodejs'
        if Path(nodejs_path).exists():
            current_path = os.environ.get('PATH', '')
            if nodejs_path not in current_path:
                os.environ['PATH'] = f'{nodejs_path};{current_path}'
                info(f'Found Node.js at {nodejs_path}, adding to PATH')

    current_version = _get_node_version()
    if current_version:
        info(f'Node.js {current_version} found')

        if _compare_node_versions(current_version, MIN_NODE_VERSION):
            success(f'Node.js version meets minimum requirement (>= {MIN_NODE_VERSION})')
            return True
        warning(f'Node.js {current_version} is below minimum required version {MIN_NODE_VERSION}')
    else:
        info('Node.js not found')

    # Install Node.js based on OS
    system = platform.system()

    if system == 'Windows':
        # Try winget first
        if _check_winget_available():
            if _install_nodejs_winget('user'):
                time.sleep(2)
                # Update PATH after winget installation
                nodejs_path = r'C:\Program Files\nodejs'
                if Path(nodejs_path).exists():
                    current_path = os.environ.get('PATH', '')
                    if nodejs_path not in current_path:
                        os.environ['PATH'] = f'{nodejs_path};{current_path}'
                        info(f'Added {nodejs_path} to PATH after winget installation')

                if _verify_nodejs_version():
                    return True

            if is_admin() and _install_nodejs_winget('machine'):
                time.sleep(2)
                # Update PATH after winget installation (machine scope)
                nodejs_path = r'C:\Program Files\nodejs'
                if Path(nodejs_path).exists():
                    current_path = os.environ.get('PATH', '')
                    if nodejs_path not in current_path:
                        os.environ['PATH'] = f'{nodejs_path};{current_path}'
                        info(f'Added {nodejs_path} to PATH after winget installation')

                if _verify_nodejs_version():
                    return True

        # Fallback to direct download
        if _install_nodejs_direct():
            time.sleep(2)
            # After installation, check standard location on Windows
            if platform.system() == 'Windows':
                nodejs_path = r'C:\Program Files\nodejs'
                if Path(nodejs_path).exists():
                    current_path = os.environ.get('PATH', '')
                    if nodejs_path not in current_path:
                        os.environ['PATH'] = f'{nodejs_path};{current_path}'
                        info(f'Added {nodejs_path} to PATH after installation')

            if _verify_nodejs_version():
                return True

    elif system == 'Darwin':
        # Try Homebrew first
        if _install_nodejs_homebrew() and _verify_nodejs_version():
            return True

        # Fallback to direct download
        if _install_nodejs_direct():
            time.sleep(2)
            if _verify_nodejs_version():
                return True

    else:  # Linux
        # Detect distro and use package manager
        if (
            Path('/etc/debian_version').exists()
            and _install_nodejs_apt()
            and _verify_nodejs_version()
        ):
            return True
        warning('Unsupported Linux distribution - please install Node.js manually')
        return False

    error(f'Could not install Node.js >= {MIN_NODE_VERSION}')
    return False


def install_nodejs_if_requested(config: dict[str, Any]) -> bool:
    """Install Node.js LTS if requested in configuration.

    Checks the 'install-nodejs' config parameter and installs Node.js
    if set to True. Uses the standalone _ensure_nodejs() function which:
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

    # Check if any dependencies on the current platform need admin
    if platform.system() == 'Windows' and not is_admin():
        platform_key = PLATFORM_SYSTEM_TO_CONFIG_KEY.get(platform.system())
        platform_deps = dependencies.get(platform_key, []) if platform_key else []
        common_deps = dependencies.get('common', [])
        all_deps = list(platform_deps) + list(common_deps)

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
    current_platform_key = PLATFORM_SYSTEM_TO_CONFIG_KEY.get(system)

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
                # Expand tildes before execution (PowerShell doesn't expand ~ natively)
                expanded_dep = expand_tildes_in_command(dep)
                result = run_command(['powershell', '-NoProfile', '-Command', expanded_dep], capture_output=False)
        else:
            if parts[0] == 'uv' and len(parts) >= 3 and parts[1] == 'tool' and parts[2] == 'install':
                dep_with_force = dep.replace('uv tool install', 'uv tool install --force')
                # Apply tilde expansion consistently (same as other commands)
                expanded_dep = expand_tildes_in_command(dep_with_force)
                result = run_command(['bash', '-c', expanded_dep], capture_output=False)
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


class RateLimitCoordinator:
    """Thread-safe coordinator for cross-thread rate-limit state.

    Maintains a global earliest-retry-time that any thread can update
    when receiving a rate-limit response. Uses time.monotonic() for
    clock-jump immunity.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._earliest_retry_time: float = 0.0

    def report_rate_limit(self, wait_seconds: float) -> None:
        """Update global rate-limit floor.

        Args:
            wait_seconds: Duration in seconds to wait from now.
        """
        with self._lock:
            new_earliest = time.monotonic() + wait_seconds
            self._earliest_retry_time = max(self._earliest_retry_time, new_earliest)

    def get_wait_time(self) -> float:
        """Return seconds to wait before next request.

        Returns:
            Non-negative float: remaining wait time.
        """
        with self._lock:
            remaining = self._earliest_retry_time - time.monotonic()
            return max(0.0, remaining)


class AuthHeaderCache:
    """Thread-safe per-origin cache for resolved authentication headers.

    Caches auth headers by normalized URL origin (e.g., 'github.com/org/repo')
    to avoid redundant unauthenticated probes for files from the same repository.
    The first request to each origin tries unauthenticated; on auth resolution,
    subsequent requests reuse the cached headers.

    Modeled after RateLimitCoordinator for thread-safe cross-thread sharing.

    Attributes:
        auth_param: Raw authentication parameter (token or header:value format).
    """

    def __init__(self, auth_param: str | None = None) -> None:
        self._lock = threading.Lock()
        self._cache: dict[str, dict[str, str] | None] = {}
        self.auth_param = auth_param

    def get_origin(self, url: str) -> str:
        """Extract normalized origin key from URL.

        For GitHub: 'github.com/{owner}/{repo}'
        For GitLab: '{host}/api/v4/projects/{id}' or '{host}/{namespace}/{project}'
        For others: '{host}'

        Args:
            url: URL to extract origin from.

        Returns:
            Normalized origin string for cache keying.
        """
        from urllib.parse import urlparse

        parsed = urlparse(url)
        host = parsed.hostname or ''
        path_parts = [p for p in parsed.path.split('/') if p]

        # GitHub: normalize raw.githubusercontent.com/owner/repo,
        # github.com/owner/repo, and api.github.com/repos/owner/repo to the
        # same cache key (github.com/owner/repo). This cross-domain sharing is
        # intentional: the validation phase resolves auth headers against
        # raw.githubusercontent.com URLs, while _fetch_url_core() converts
        # those same URLs to api.github.com for download. Normalizing both
        # forms to one key ensures auth cached during validation is reused
        # during download without redundant token resolution.
        if 'github.com' in host or 'raw.githubusercontent.com' in host:
            if 'api.github.com' in host and len(path_parts) >= 3 and path_parts[0] == 'repos':
                return f'github.com/{path_parts[1]}/{path_parts[2]}'
            if len(path_parts) >= 2:
                return f'github.com/{path_parts[0]}/{path_parts[1]}'

        # GitLab API: /api/v4/projects/{id}/...
        if '/api/v4/projects/' in url and len(path_parts) >= 4:
            return f'{host}/api/v4/projects/{path_parts[3]}'

        # GitLab web: host/namespace/project
        if 'gitlab' in host.lower() and len(path_parts) >= 2:
            return f'{host}/{path_parts[0]}/{path_parts[1]}'

        # Fallback: host only
        return host

    def get_cached_headers(self, url: str) -> tuple[bool, dict[str, str] | None]:
        """Look up cached auth headers for the origin of this URL.

        Args:
            url: URL to look up.

        Returns:
            Tuple of (is_cached, headers).
            is_cached=False means this origin has not been seen yet.
            is_cached=True, headers=None means origin was probed and needs no auth.
            is_cached=True, headers={...} means cached auth headers.
        """
        origin = self.get_origin(url)
        with self._lock:
            if origin in self._cache:
                return (True, self._cache[origin])
            return (False, None)

    def cache_headers(self, url: str, headers: dict[str, str] | None) -> None:
        """Cache resolved auth headers for this URL's origin.

        Args:
            url: URL whose origin to cache for.
            headers: Resolved auth headers, or None if origin needs no auth.
        """
        origin = self.get_origin(url)
        with self._lock:
            self._cache[origin] = headers

    def resolve_and_cache(self, url: str) -> dict[str, str]:
        """Resolve auth headers for a URL, using cache if available.

        Thread-safe resolution that avoids redundant get_auth_headers() calls.
        Uses double-checked locking pattern.

        Args:
            url: URL to resolve auth for.

        Returns:
            Resolved auth headers dict (may be empty if no auth available).
        """
        origin = self.get_origin(url)
        with self._lock:
            if origin in self._cache:
                return self._cache[origin] or {}

        # Resolve outside lock (get_auth_headers may do I/O including interactive prompts)
        headers = get_auth_headers(url, self.auth_param)

        with self._lock:
            # Only cache if not already set by another thread
            if origin not in self._cache:
                self._cache[origin] = headers or None
            return self._cache.get(origin) or {}


def fetch_with_retry[T](
    request_func: Callable[[], T],
    url: str,
    max_retries: int = 10,
    base_delay: float = 1.0,
    additive_increment: float = 2.0,
    max_delay: float = 60.0,
    rate_limiter: RateLimitCoordinator | None = None,
) -> T:
    """Execute a fetch operation with retry logic for rate limiting.

    Implements linear additive backoff with jitter. Respects Retry-After and
    x-ratelimit-reset headers as a minimum floor (never overrides a larger
    calculated backoff). A shared RateLimitCoordinator propagates rate-limit
    state across concurrent download threads.

    Args:
        request_func: Function that performs the actual request and returns result.
        url: URL being fetched (for logging purposes).
        max_retries: Maximum number of retry attempts (default: 10).
        base_delay: Base delay in seconds for the first retry (default: 1.0).
        additive_increment: Seconds added per subsequent attempt (default: 2.0).
        max_delay: Maximum delay cap in seconds before jitter (default: 60.0).
        rate_limiter: Optional coordinator sharing rate-limit state across threads.

    Returns:
        Result from request_func.

    Raises:
        HTTPError: If all retry attempts fail.
        RuntimeError: If an unexpected state is reached (should never occur).
    """
    last_exception: urllib.error.HTTPError | None = None

    for attempt in range(max_retries + 1):
        # Respect cross-thread rate-limit floor before each request
        if rate_limiter is not None:
            coord_wait = rate_limiter.get_wait_time()
            if coord_wait > 0:
                time.sleep(coord_wait)

        try:
            return request_func()
        except urllib.error.HTTPError as e:
            if e.code in (429, 403):
                # Check if it's a rate limit error
                retry_after = e.headers.get('retry-after') if e.headers else None
                reset_time = e.headers.get('x-ratelimit-reset') if e.headers else None
                remaining = e.headers.get('x-ratelimit-remaining') if e.headers else None

                # Only retry if it looks like rate limiting
                if e.code == 403 and remaining != '0' and not retry_after:
                    # 403 but not rate limiting - re-raise
                    raise

                if attempt < max_retries:
                    # Per-thread linear additive backoff
                    per_thread_delay = base_delay + (attempt * additive_increment)

                    # Parse header value as floor (not override)
                    header_wait: float | None = None
                    if retry_after:
                        with contextlib.suppress(ValueError):
                            header_wait = float(retry_after)
                    elif reset_time:
                        with contextlib.suppress(ValueError):
                            header_wait = max(0.0, int(reset_time) - time.time())

                    # Header is a floor: use the larger of header and calculated backoff
                    wait_time = max(header_wait, per_thread_delay) if header_wait is not None else per_thread_delay

                    # Cap before jitter
                    wait_time = min(wait_time, max_delay)

                    # Add jitter to all retries (0-25% of wait time)
                    wait_time += random.uniform(0, wait_time * 0.25)

                    # Report to coordinator so other threads respect this floor
                    if rate_limiter is not None:
                        rate_limiter.report_rate_limit(wait_time)

                    filename = url.split('/')[-1].split('?')[0]
                    info(f'Rate limited, retrying {filename} in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})')
                    time.sleep(wait_time)
                    continue

                last_exception = e
            else:
                raise

    if last_exception:
        raise last_exception
    # Satisfy type checker - this should never be reached
    msg = 'Unexpected state in fetch_with_retry'
    raise RuntimeError(msg)


def _fetch_url_core(
    url: str,
    *,
    as_text: bool = True,
    auth_headers: dict[str, str] | None = None,
    auth_param: str | None = None,
    auth_cache: AuthHeaderCache | None = None,
    rate_limiter: RateLimitCoordinator | None = None,
) -> str | bytes:
    """Fetch URL content with auth resolution, caching, and retry logic.

    Handles URL conversion (GitLab/GitHub API), authentication with
    origin-level caching, SSL fallback, and rate-limit retry.

    Args:
        url: URL to fetch.
        as_text: If True, decode response as UTF-8 text. If False, return raw bytes.
        auth_headers: Pre-computed auth headers (highest priority, skips probing).
        auth_param: Raw auth parameter for header resolution.
        auth_cache: Shared auth header cache for origin-level caching.
        rate_limiter: Shared rate-limit coordinator for cross-thread backoff.

    Returns:
        str if as_text=True, bytes if as_text=False.
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

    # GitHub Contents API requires specific headers to return raw content
    # instead of JSON metadata. These are transport-level headers independent
    # of auth headers and must be applied to every Request construction.
    github_api_headers: dict[str, str] = {}
    if 'api.github.com' in url:
        github_api_headers = {
            'Accept': 'application/vnd.github.raw+json',
            'X-GitHub-Api-Version': '2022-11-28',
        }

    def _read_response(response: http.client.HTTPResponse) -> str | bytes:
        """Read response data in the appropriate format."""
        if as_text:
            return str(response.read().decode('utf-8'))
        return bytes(response.read())

    # Resolve effective auth headers via priority chain:
    # 1. Explicit auth_headers parameter (highest priority)
    # 2. Cached headers from auth_cache
    # 3. Try unauthenticated, then resolve on 401/403/404
    effective_headers = auth_headers

    if effective_headers is None and auth_cache is not None:
        is_cached, cached = auth_cache.get_cached_headers(url)
        if is_cached:
            effective_headers = cached

    # Use mutable container to allow inner function to modify auth_headers
    auth_state: dict[str, dict[str, str] | None] = {'headers': effective_headers}

    def _build_request(auth_headers: dict[str, str] | None = None) -> Request:
        """Build a Request with GitHub API headers and optional auth."""
        request = Request(url)
        for header, value in github_api_headers.items():
            request.add_header(header, value)
        if auth_headers:
            for header, value in auth_headers.items():
                request.add_header(header, value)
        return request

    def _do_fetch() -> str | bytes:
        """Internal fetch logic wrapped for retry."""
        # Skip unauthenticated attempt when auth headers are already known
        if auth_state['headers']:
            try:
                return _read_response(urlopen(_build_request(auth_state['headers'])))
            except urllib.error.URLError as e:
                if 'SSL' in str(e) or 'certificate' in str(e).lower():
                    warning('SSL certificate verification failed, trying with unverified context')
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    return _read_response(urlopen(_build_request(auth_state['headers']), context=ctx))
                raise

        # Try without auth first (for public repos)
        try:
            return _read_response(urlopen(_build_request()))
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 404):
                # Authentication might be needed
                if not auth_state['headers']:
                    # Get auth headers if not already provided
                    auth_state['headers'] = get_auth_headers(url, auth_param)

                if auth_state['headers']:
                    # Populate cache on successful auth discovery
                    if auth_cache is not None:
                        auth_cache.cache_headers(url, auth_state['headers'])

                    # Retry with authentication
                    info('Retrying with authentication...')
                    try:
                        return _read_response(urlopen(_build_request(auth_state['headers'])))
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
                return _read_response(urlopen(
                    _build_request(auth_state['headers'] or None),
                    context=ctx,
                ))
            raise

    # Wrap with retry logic for rate limiting
    return fetch_with_retry(_do_fetch, url, rate_limiter=rate_limiter)


def fetch_url_with_auth(
    url: str,
    auth_headers: dict[str, str] | None = None,
    auth_param: str | None = None,
    rate_limiter: RateLimitCoordinator | None = None,
    auth_cache: AuthHeaderCache | None = None,
) -> str:
    """Fetch URL content as text with auth caching and retry logic.

    Includes retry logic with linear additive backoff for rate limiting (HTTP 429).
    May raise HTTPError if the request fails after authentication and retry attempts,
    or URLError if there's a network error (including SSL issues).

    Args:
        url: URL to fetch
        auth_headers: Optional pre-computed auth headers
        auth_param: Optional auth parameter for getting headers
        rate_limiter: Optional coordinator sharing rate-limit state across threads
        auth_cache: Optional shared auth header cache for origin-level caching

    Returns:
        str: Content of the URL
    """
    result = _fetch_url_core(
        url, as_text=True, auth_headers=auth_headers, auth_param=auth_param,
        auth_cache=auth_cache, rate_limiter=rate_limiter,
    )
    return str(result)


def fetch_url_bytes_with_auth(
    url: str,
    auth_headers: dict[str, str] | None = None,
    auth_param: str | None = None,
    rate_limiter: RateLimitCoordinator | None = None,
    auth_cache: AuthHeaderCache | None = None,
) -> bytes:
    """Fetch URL content as bytes with auth caching and retry logic.

    Similar to fetch_url_with_auth but returns raw bytes without decoding.
    Use this for binary files like .tar.gz, .zip, images, etc.
    Includes retry logic with linear additive backoff for rate limiting (HTTP 429).
    May raise HTTPError if the request fails after authentication and retry attempts,
    or URLError if there's a network error (including SSL issues).

    Args:
        url: URL to fetch
        auth_headers: Optional pre-computed auth headers
        auth_param: Optional auth parameter for getting headers
        rate_limiter: Optional coordinator sharing rate-limit state across threads
        auth_cache: Optional shared auth header cache for origin-level caching

    Returns:
        bytes: Raw content of the URL
    """
    result = _fetch_url_core(
        url, as_text=False, auth_headers=auth_headers, auth_param=auth_param,
        auth_cache=auth_cache, rate_limiter=rate_limiter,
    )
    assert isinstance(result, bytes)
    return result


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
            # Cast to typed dict for type safety
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
    rate_limiter: RateLimitCoordinator | None = None,
    auth_cache: AuthHeaderCache | None = None,
) -> bool:
    """Handle a resource - either download from URL or copy from local path.

    Args:
        resource_path: Resource path from config (URL or local path)
        destination: Local destination path
        config_source: Where the config was loaded from
        base_url: Optional base URL from config
        auth_param: Optional auth parameter for private repos
        rate_limiter: Optional coordinator sharing rate-limit state across threads
        auth_cache: Optional shared auth header cache for origin-level caching

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
                content_bytes = fetch_url_bytes_with_auth(
                    resolved_path, auth_param=auth_param, rate_limiter=rate_limiter, auth_cache=auth_cache,
                )
                destination.write_bytes(content_bytes)
            else:
                # Text file - fetch as text and write text
                content = fetch_url_with_auth(
                    resolved_path, auth_param=auth_param, rate_limiter=rate_limiter, auth_cache=auth_cache,
                )
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
    auth_cache: AuthHeaderCache | None = None,
) -> bool:
    """Process resources (download from URL or copy from local) based on configuration.

    Uses parallel execution when CLAUDE_CODE_TOOLBOX_SEQUENTIAL_MODE is not set.

    Args:
        resources: List of resource paths from config
        destination_dir: Directory to save resources
        resource_type: Type of resources (for logging)
        config_source: Where the config was loaded from
        base_url: Optional base URL from config
        auth_param: Optional auth parameter for private repos
        auth_cache: Optional shared auth header cache for origin-level caching

    Returns:
        bool: True if all successful
    """
    if not resources:
        info(f'No {resource_type} to process')
        return True

    info(f'Processing {resource_type}...')

    # Create shared auth cache if not provided
    if auth_cache is None:
        auth_cache = AuthHeaderCache(auth_param)

    # Prepare download tasks
    download_tasks: list[tuple[str, Path]] = []
    for resource in resources:
        # Strip query parameters from URL to get clean filename
        clean_resource = resource.split('?')[0] if '?' in resource else resource
        filename = Path(clean_resource).name
        destination = destination_dir / filename
        download_tasks.append((resource, destination))

    # Per-batch coordinator shares rate-limit state across download threads
    rate_limiter = RateLimitCoordinator()

    def download_single_resource(task: tuple[str, Path]) -> bool:
        """Download a single resource and return success status."""
        resource, destination = task
        return handle_resource(resource, destination, config_source, base_url, auth_param, rate_limiter, auth_cache)

    # Execute downloads in parallel with stagger delay to avoid rate limiting
    results = execute_parallel_safe(download_tasks, download_single_resource, False, stagger_delay=0.5)
    return all(results)


def process_file_downloads(
    file_specs: list[dict[str, Any]],
    config_source: str,
    base_url: str | None = None,
    auth_param: str | None = None,
    auth_cache: AuthHeaderCache | None = None,
) -> bool:
    """Process file downloads/copies from configuration.

    Downloads files from URLs or copies from local paths to specified destinations.
    Supports cross-platform path expansion using ~ and environment variables.
    Uses parallel execution when CLAUDE_CODE_TOOLBOX_SEQUENTIAL_MODE is not set.

    Args:
        file_specs: List of file specifications with 'source' and 'dest' keys.
                   Each spec is a dict: {'source': 'path/to/file', 'dest': '~/destination'}
        config_source: Where the config was loaded from (for resolving relative paths)
        base_url: Optional base URL override from config
        auth_param: Optional auth parameter for private repos
        auth_cache: Optional shared auth header cache for origin-level caching

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

    # Create shared auth cache if not provided
    if auth_cache is None:
        auth_cache = AuthHeaderCache(auth_param)

    # Pre-validate file specs and prepare download tasks
    valid_downloads: list[tuple[str, Path]] = []
    invalid_count = 0

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
            invalid_count += 1
            continue

        # Expand destination path using normalize_tilde_path for WSL-safe tilde expansion
        expanded_dest = normalize_tilde_path(str(dest))
        dest_path = Path(expanded_dest)

        # Handle both file and directory destinations
        # If dest ends with separator or is existing directory, append source filename
        dest_str = str(dest)
        if dest_str.endswith(('/', '\\')) or (dest_path.exists() and dest_path.is_dir()):
            # Extract filename from source (remove query params if present)
            clean_source = str(source).split('?')[0]
            filename = Path(clean_source).name
            dest_path = dest_path / filename

        valid_downloads.append((str(source), dest_path))

    # Per-batch coordinator shares rate-limit state across download threads
    rate_limiter = RateLimitCoordinator()

    def download_single_file(download_info: tuple[str, Path]) -> bool:
        """Download a single file and return success status."""
        source, dest_path = download_info
        return handle_resource(source, dest_path, config_source, base_url, auth_param, rate_limiter, auth_cache)

    # Execute downloads in parallel with stagger delay to avoid rate limiting
    if valid_downloads:
        download_results = execute_parallel_safe(valid_downloads, download_single_file, False, stagger_delay=0.5)
        success_count = sum(1 for result in download_results if result)
        failed_count = len(download_results) - success_count + invalid_count
    else:
        success_count = 0
        failed_count = invalid_count

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
    rate_limiter: RateLimitCoordinator | None = None,
    auth_cache: AuthHeaderCache | None = None,
) -> bool:
    """Process and install a single skill.

    Downloads or copies all files specified in the skill configuration to the
    skill's directory, preserving the relative directory structure.

    Args:
        skill_config: Skill configuration dict with 'name', 'base', and 'files' keys
        skills_dir: Base skills directory (.claude/skills/)
        config_source: Where the config was loaded from
        auth_param: Optional authentication parameter for private repos
        rate_limiter: Optional coordinator sharing rate-limit state across threads
        auth_cache: Optional shared auth header cache for origin-level caching

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
                    content_bytes = fetch_url_bytes_with_auth(
                        source_url, auth_param=auth_param, rate_limiter=rate_limiter, auth_cache=auth_cache,
                    )
                    destination.write_bytes(content_bytes)
                else:
                    # Text file - fetch as text and write text
                    content = fetch_url_with_auth(
                        source_url, auth_param=auth_param, rate_limiter=rate_limiter, auth_cache=auth_cache,
                    )
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
    auth_cache: AuthHeaderCache | None = None,
) -> bool:
    """Process all skills from configuration.

    Iterates through all skill configurations and installs each one to the
    skills directory. Uses parallel execution when CLAUDE_CODE_TOOLBOX_SEQUENTIAL_MODE is not set.

    Args:
        skills_config: List of skill configuration dictionaries
        skills_dir: Base skills directory (.claude/skills/)
        config_source: Where the config was loaded from
        auth_param: Optional authentication parameter for private repos
        auth_cache: Optional shared auth header cache for origin-level caching

    Returns:
        bool: True if all skills installed successfully, False otherwise
    """
    if not skills_config:
        info('No skills configured')
        return True

    info(f'Processing {len(skills_config)} skill(s)...')

    # Create shared auth cache if not provided
    if auth_cache is None:
        auth_cache = AuthHeaderCache(auth_param)

    # Per-batch coordinator shares rate-limit state across skill download threads
    rate_limiter = RateLimitCoordinator()

    def install_single_skill(skill_config: dict[str, Any]) -> bool:
        """Install a single skill and return success status."""
        return process_skill(skill_config, skills_dir, config_source, auth_param, rate_limiter, auth_cache)

    # Execute skill installations in parallel with stagger delay to avoid rate limiting
    results = execute_parallel_safe(skills_config, install_single_skill, False, stagger_delay=0.5)
    return all(results)


def install_claude(version: str | None = None) -> bool:
    """Install Claude Code if needed.

    When a local copy of install_claude.py exists in the same directory
    (typical when launched from setup-environment.sh), it is used directly
    to avoid redundant downloads. Otherwise, the platform bootstrap script
    is downloaded and executed.

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
        os.environ['CLAUDE_CODE_TOOLBOX_VERSION'] = version
    else:
        info('Installing Claude Code (latest version)...')

    system = platform.system()
    temp_installer: str | None = None

    try:
        # Check for local copy of install_claude.py (available when launched
        # from setup-environment.sh, which downloads both scripts to an
        # ephemeral $TEMP_DIR created fresh on every run)
        local_installer = Path(__file__).resolve().parent / 'install_claude.py'
        if system != 'Windows' and local_installer.is_file():
            info('Using local installer script')
            uv_cmd = shutil.which('uv')
            if not uv_cmd:
                warning('uv not found in PATH, falling back to bootstrap download')
            else:
                result = run_command(
                    [uv_cmd, 'run', '--no-project', '--python', '3.12', str(local_installer)],
                    capture_output=False,
                )
                if result.returncode == 0:
                    success('Claude Code installation complete')
                    return True
                raise Exception(f'Installation failed with exit code: {result.returncode}')

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


def verify_nodejs_available() -> str | None:
    """Verify Node.js is available before MCP configuration.

    Uses shutil.which() to find Node.js in PATH, supporting all installation methods
    (official installer, nvm, fnm, volta, scoop, chocolatey, etc.).

    Returns:
        Parent directory of the verified Node.js executable, or None if not found.
    """
    if platform.system() != 'Windows':
        node_path = shutil.which('node')
        if node_path:
            return str(Path(node_path).parent)
        warning('Node.js not found in PATH - npx-based MCP servers may fail at runtime')
        return None

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
                return str(Path(node_path).parent)
        except (subprocess.TimeoutExpired, OSError):
            pass

    # Secondary: Try find_command with common installation paths
    node_path = find_command('node')
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
                return str(Path(node_path).parent)
        except (subprocess.TimeoutExpired, OSError):
            pass

    error('Node.js not found in PATH')
    return None


def validate_scope_combination(scopes: list[str]) -> tuple[bool, str | None]:
    """Validate scope combination for MCP server configuration.

    Validates that the provided scope combination is valid according to these rules:
    - Single scope values are always valid (user, local, project, profile)
    - Combined scopes MUST include 'profile' for meaningful combination
    - Pure non-profile combinations are INVALID (they overlap at runtime)
    - Profile + multiple non-profile scopes trigger a WARNING (valid but unusual)

    Args:
        scopes: List of normalized scope values (lowercase)

    Returns:
        Tuple of (is_valid, message_or_none)
        - If is_valid is False, message contains the ERROR description
        - If is_valid is True and message is not None, it is a WARNING
        - If is_valid is True and message is None, combination is fully valid
    """
    valid_scopes = {'user', 'local', 'project', 'profile'}
    non_profile_scopes = {'user', 'local', 'project'}

    # Check for invalid scope values
    invalid = set(scopes) - valid_scopes
    if invalid:
        return False, f'Invalid scope values: {invalid}. Valid scopes: {valid_scopes}'

    # Check for duplicate values
    if len(scopes) != len(set(scopes)):
        return False, 'Duplicate scope values not allowed'

    # Single scope is always valid
    if len(scopes) == 1:
        return True, None

    has_profile = 'profile' in scopes
    non_profile = [s for s in scopes if s in non_profile_scopes]

    # Multiple non-profile scopes WITHOUT profile -> ERROR
    # These scopes overlap at runtime (all config files are read and merged)
    if not has_profile and len(non_profile) > 1:
        return False, (
            f"Cannot combine {non_profile} - these scopes overlap at runtime "
            "(all config files are read and merged). Use ONE of user/local/project, "
            "or combine with 'profile' for isolated profile sessions."
        )

    # Profile + multiple non-profile -> WARNING (valid but unusual)
    if has_profile and len(non_profile) > 1:
        return True, (
            f'In profile mode, only profile config is used. In normal mode, '
            f'servers from {non_profile} will all be loaded. Ensure server names '
            'do not conflict across these locations.'
        )

    # Profile + one other scope (or just profile) -> VALID
    return True, None


def normalize_scope(scope_value: str | list[str] | None) -> list[str]:
    """Normalize scope to list format with case normalization.

    Supports multiple input formats for flexibility:
    - None -> ['user'] (default behavior, backward compatible)
    - 'user' -> ['user'] (single string)
    - 'User' -> ['user'] (case normalization)
    - 'user, profile' -> ['user', 'profile'] (comma-separated string)
    - ['user', 'profile'] -> ['user', 'profile'] (list passthrough)
    - ['User', 'PROFILE'] -> ['user', 'profile'] (list with case normalization)

    Args:
        scope_value: Raw scope value from YAML config (string, list, or None)

    Returns:
        List of normalized scope strings (lowercase, deduplicated)

    Raises:
        ValueError: If scope combination is invalid per validate_scope_combination()
    """
    if scope_value is None:
        return ['user']

    if isinstance(scope_value, str):
        scopes = (
            [s.strip().lower() for s in scope_value.split(',')]
            if ',' in scope_value
            else [scope_value.strip().lower()]
        )
    else:
        # scope_value is list[str] at this point per type hint
        scopes = [str(s).strip().lower() for s in scope_value]

    # Remove empty strings and duplicates while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for s in scopes:
        if s and s not in seen:
            seen.add(s)
            result.append(s)

    if not result:
        return ['user']

    # Validate combination
    is_valid, message = validate_scope_combination(result)
    if not is_valid:
        raise ValueError(f'Invalid scope configuration: {message}')

    # Log warning if applicable
    if message:
        warning(f'Combined scope warning: {message}')

    return result


class _WindowsBashEnv(NamedTuple):
    """Pre-computed Windows Git Bash environment for MCP server configuration.

    Encapsulates PATH construction with Node.js injection and Claude command
    resolution for Git Bash execution.
    """

    unix_explicit_path: str
    unix_claude_cmd: str


def _prepare_windows_bash_env(
    claude_cmd: str | Path,
    nodejs_dir: str | None,
) -> _WindowsBashEnv:
    """Prepare Windows Git Bash environment for MCP server subprocess execution.

    Builds a Unix-style PATH with Node.js directory prepended (if available)
    and resolves the Claude command to a Git Bash-compatible path.

    Args:
        claude_cmd: Path to the Claude CLI executable.
        nodejs_dir: Verified Node.js directory path, or None if not verified.

    Returns:
        _WindowsBashEnv with unix_explicit_path and unix_claude_cmd.
    """
    current_path = os.environ.get('PATH', '')
    if nodejs_dir and Path(nodejs_dir).exists() and nodejs_dir not in current_path:
        windows_explicit_path = f'{nodejs_dir};{current_path}'
    else:
        windows_explicit_path = current_path

    unix_explicit_path = convert_path_env_to_unix(windows_explicit_path)
    bash_preferred_cmd = get_bash_preferred_command(str(claude_cmd))
    unix_claude_cmd = convert_to_unix_path(bash_preferred_cmd)

    return _WindowsBashEnv(
        unix_explicit_path=unix_explicit_path,
        unix_claude_cmd=unix_claude_cmd,
    )


def configure_mcp_server(
    server: dict[str, Any],
    nodejs_dir: str | None = None,
    artifact_base_dir: Path | None = None,
) -> bool:
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
    claude_cmd = find_command('claude')

    if not claude_cmd:
        error('Claude command not accessible after installation!')
        error('This may indicate a PATH synchronization issue between installation and configuration steps.')
        error('Try running the command again or opening a new terminal session.')
        return False

    try:
        # Remove existing MCP server from all scopes to avoid conflicts
        # When servers with the same name exist at multiple scopes, local-scoped servers
        # take precedence, followed by project, then user - so we remove from all scopes
        # Best-effort removal: Claude CLI returns non-zero if server doesn't exist in a scope,
        # which is expected behavior, not an error - we simply attempt removal from all scopes
        info(f'Removing existing MCP server {name} from all scopes (best-effort)...')

        if system == 'Windows':
            # Windows: Use bash execution for consistency with add operation
            # This ensures removal uses the same environment (PATH, shell, MSYS settings)
            # as the add operation, preventing "not found" errors due to asymmetric execution
            env = _prepare_windows_bash_env(claude_cmd, nodejs_dir)

            remove_extra_env: dict[str, str] = {'PATH': env.unix_explicit_path}
            if artifact_base_dir is not None:
                remove_extra_env['CLAUDE_CONFIG_DIR'] = str(artifact_base_dir)

            for remove_scope in ['user', 'local', 'project']:
                bash_cmd = (
                    f'"{env.unix_claude_cmd}" mcp remove --scope {remove_scope} {name}'
                )
                # Best-effort: ignore exit code, server may not exist in this scope
                run_bash_command(
                    bash_cmd, capture_output=True, login_shell=True,
                    extra_env=remove_extra_env,
                )
        else:
            # Unix: Direct subprocess execution
            remove_env: dict[str, str] | None = None
            if artifact_base_dir is not None:
                remove_env = {**os.environ, 'CLAUDE_CONFIG_DIR': str(artifact_base_dir)}

            for remove_scope in ['user', 'local', 'project']:
                remove_cmd = [str(claude_cmd), 'mcp', 'remove', '--scope', remove_scope, name]
                # Best-effort: ignore exit code, server may not exist in this scope
                run_command(remove_cmd, capture_output=True, env=remove_env)

        # Profile-scoped servers are configured via create_mcp_config_file(), not claude mcp add
        if scope == 'profile':
            info(f'MCP server {name} has scope: profile (will be configured via --strict-mcp-config)')
            return True

        # Build the base command
        base_cmd = [str(claude_cmd), 'mcp', 'add']

        if scope:
            base_cmd.extend(['--scope', scope])

        # Handle different transport types
        if transport and url:
            # HTTP or SSE transport
            # Non-variadic options precede positional arguments per Claude CLI syntax.
            # EXCEPTION: Variadic --header MUST come AFTER positional arguments (name, url)
            # to prevent Commander.js from consuming positionals as additional header values.
            # See: https://github.com/anthropics/claude-code/issues/2341
            for env_var in env_list:
                base_cmd.extend(['--env', env_var])
            base_cmd.extend(['--transport', transport])
            base_cmd.extend((name, url))
            if header:
                base_cmd.extend(['--header', header])

            # Windows HTTP transport - use bash for consistent cross-platform behavior
            # This eliminates PowerShell's exit code quirks and CMD escaping issues
            if system == 'Windows':
                debug_log(f'=== MCP Server Configuration: {name} ===')
                debug_log(f'claude_cmd: {claude_cmd}')

                env = _prepare_windows_bash_env(claude_cmd, nodejs_dir)
                debug_log(f'unix_claude_cmd: {env.unix_claude_cmd}')
                explicit_path = env.unix_explicit_path
                path_preview = explicit_path[:200] + '...' if len(explicit_path) > 200 else explicit_path
                debug_log(f'unix_explicit_path: {path_preview}')

                env_flags = ' '.join(f'--env "{e}"' for e in env_list) if env_list else ''
                env_part = f' {env_flags}' if env_flags else ''
                header_part = f' --header "{header}"' if header else ''

                bash_cmd = (
                    f'"{env.unix_claude_cmd}" mcp add --scope {scope}{env_part} '
                    f'--transport {transport} {name} "{url}"{header_part}'
                )

                bash_cmd_preview = bash_cmd[:300] + '...' if len(bash_cmd) > 300 else bash_cmd
                debug_log(f'First attempt bash_cmd: {bash_cmd_preview}')
                http_win_extra_env: dict[str, str] = {'PATH': env.unix_explicit_path}
                if artifact_base_dir is not None:
                    http_win_extra_env['CLAUDE_CONFIG_DIR'] = str(artifact_base_dir)
                result = run_bash_command(
                    bash_cmd, capture_output=True, login_shell=True,
                    extra_env=http_win_extra_env,
                )
                debug_log(f'First attempt result: returncode={result.returncode}')
                if result.returncode != 0:
                    debug_log(f'First attempt failed! stdout={result.stdout}, stderr={result.stderr}')
            else:
                # On Unix, use bash with updated PATH (consistent with Windows)
                parent_dir = Path(claude_cmd).parent
                env_flags = ' '.join(f'--env {shlex.quote(e)}' for e in env_list) if env_list else ''
                env_part = f' {env_flags}' if env_flags else ''
                # Use double quotes for header to allow ${VAR} expansion in bash
                header_part = f' --header "{header}"' if header else ''
                bash_cmd = (
                    f'{shlex.quote(str(claude_cmd))} mcp add --scope {shlex.quote(scope)}{env_part} '
                    f'--transport {shlex.quote(transport)} {shlex.quote(name)} {shlex.quote(url)}{header_part}'
                )
                current_path = os.environ.get('PATH', '')
                parent_str = str(parent_dir)
                extra_path = f'{parent_str}:{current_path}' if parent_str not in current_path else current_path
                http_unix_extra_env: dict[str, str] = {'PATH': extra_path}
                if artifact_base_dir is not None:
                    http_unix_extra_env['CLAUDE_CONFIG_DIR'] = str(artifact_base_dir)
                result = run_bash_command(
                    bash_cmd, capture_output=True, login_shell=True,
                    extra_env=http_unix_extra_env,
                )
        elif command:
            # Stdio transport (command)

            # When args is provided separately, combine command + args into full command string
            args_list = server.get('args')
            if args_list and isinstance(args_list, list):
                command = command + ' ' + ' '.join(shlex.quote(str(a)) for a in args_list)

            # Build the command properly
            base_cmd.append(name)  # Add name FIRST, before post-name options
            # Add all environment variables
            for env_var in env_list:
                base_cmd.extend(['--env', env_var])
            base_cmd.extend(['--'])

            # Build platform-aware command using shared helper
            base_cmd.extend(build_platform_aware_command(command))

            # Windows STDIO transport - use bash for consistent cross-platform behavior
            # This unifies STDIO with HTTP transport (both use run_bash_command)
            if system == 'Windows':
                debug_log(f'=== MCP Server Configuration (STDIO): {name} ===')
                debug_log(f'claude_cmd: {claude_cmd}')

                env = _prepare_windows_bash_env(claude_cmd, nodejs_dir)
                debug_log(f'unix_claude_cmd: {env.unix_claude_cmd}')
                explicit_path = env.unix_explicit_path
                path_preview = explicit_path[:200] + '...' if len(explicit_path) > 200 else explicit_path
                debug_log(f'unix_explicit_path: {path_preview}')

                env_flags = ' '.join(f'--env "{e}"' for e in env_list) if env_list else ''
                env_part = f' {env_flags}' if env_flags else ''

                # Build command string for STDIO
                # npx needs cmd /c wrapper on Windows even in bash
                # Expand tildes using Python (produces C:\Users\...) and convert to forward slashes
                # This prevents Git Bash from expanding ~ to /c/Users/... (Unix format)
                expanded_command = expand_tildes_in_command(command).replace('\\', '/')
                command_str = f'cmd /c {expanded_command}' if 'npx' in expanded_command else expanded_command

                bash_cmd = (
                    f'"{env.unix_claude_cmd}" mcp add --scope {scope} {name}{env_part} '
                    f'-- {command_str}'
                )

                bash_cmd_preview = bash_cmd[:300] + '...' if len(bash_cmd) > 300 else bash_cmd
                debug_log(f'STDIO bash_cmd: {bash_cmd_preview}')

                info(f'Configuring stdio MCP server {name}...')
                stdio_win_extra_env: dict[str, str] = {'PATH': env.unix_explicit_path}
                if artifact_base_dir is not None:
                    stdio_win_extra_env['CLAUDE_CONFIG_DIR'] = str(artifact_base_dir)
                result = run_bash_command(
                    bash_cmd, capture_output=True, login_shell=True,
                    extra_env=stdio_win_extra_env,
                )
                debug_log(f'STDIO result: returncode={result.returncode}')
                if result.returncode != 0:
                    debug_log(f'STDIO failed! stdout={result.stdout}, stderr={result.stderr}')
            else:
                # Unix-like systems - expand tildes and execute
                info(f'Configuring stdio MCP server {name}...')

                # Apply tilde expansion to command (same as Windows path)
                # This ensures ~/ paths in MCP server commands work on macOS/Linux
                if command:
                    expanded_command = expand_tildes_in_command(command)
                    # Rebuild base_cmd with expanded command if tilde was expanded
                    # base_cmd structure: [..., '--', command_parts...]
                    if expanded_command != command and '--' in [str(arg) for arg in base_cmd]:
                        separator_idx = [str(arg) for arg in base_cmd].index('--')
                        base_cmd = list(base_cmd[:separator_idx + 1]) + expanded_command.split()

                stdio_unix_env: dict[str, str] | None = None
                if artifact_base_dir is not None:
                    stdio_unix_env = {**os.environ, 'CLAUDE_CONFIG_DIR': str(artifact_base_dir)}
                result = run_command(base_cmd, capture_output=True, env=stdio_unix_env)
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
            error('npm-installed Claude Code is not yet compatible with Node.js v25+')
            info('Node.js v25 removed the SlowBuffer API that npm-installed Claude Code depends on')
            info('Please downgrade to Node.js v22 or v20 (LTS)')

        return False

    except Exception as e:
        error(f'Failed to configure MCP server {name}: {e}')
        return False


def configure_all_mcp_servers(
    servers: list[dict[str, Any]],
    profile_mcp_config_path: Path | None = None,
    nodejs_dir: str | None = None,
    artifact_base_dir: Path | None = None,
) -> tuple[bool, list[dict[str, Any]], dict[str, int]]:
    """Configure all MCP servers from configuration.

    Handles combined scope configurations where servers can be added to multiple
    locations simultaneously. For example, `scope: [user, profile]` adds the server
    to both ~/.claude.json (for global access) and the profile MCP config file
    (for isolated profile sessions).

    Args:
        servers: List of MCP server configurations from YAML
        profile_mcp_config_path: Path for profile-scoped servers JSON file
        nodejs_dir: Verified Node.js directory path, or None if not verified.

    Returns:
        Tuple of (success: bool, profile_servers: list, stats: dict)
        stats contains:
            - global_count: Number of servers with any non-profile scope
            - profile_count: Number of servers with profile scope
            - combined_count: Number of servers with BOTH global AND profile scopes
    """
    if not servers:
        info('No MCP servers to configure')
        return True, [], {'global_count': 0, 'profile_count': 0, 'combined_count': 0}

    info('Configuring MCP servers...')

    # Collect servers for profile config
    profile_servers: list[dict[str, Any]] = []

    # Track statistics for accurate summary display
    stats = {
        'global_count': 0,      # Servers with any non-profile scope
        'profile_count': 0,     # Servers with profile scope
        'combined_count': 0,    # Servers with BOTH global AND profile scopes
    }

    for server in servers:
        server_name = server.get('name', 'unnamed')
        scope_value = server.get('scope', 'user')

        try:
            scopes = normalize_scope(scope_value)
        except ValueError as e:
            error(f'Server {server_name}: {e}')
            continue  # Skip invalid server configuration

        has_profile = 'profile' in scopes
        non_profile_scopes = [s for s in scopes if s != 'profile']
        has_global = len(non_profile_scopes) > 0

        # Update statistics
        if has_profile:
            stats['profile_count'] += 1
        if has_global:
            stats['global_count'] += 1
        if has_profile and has_global:
            stats['combined_count'] += 1

        # Add to profile config if profile scope present
        if has_profile:
            profile_servers.append(server)
            # For profile-only servers, call configure_mcp_server to trigger removal
            # from all scopes (user, local, project). The function will early-return
            # after removal since scope == 'profile', skipping the claude mcp add.
            if not has_global:
                server_copy = server.copy()
                server_copy['scope'] = 'profile'
                configure_mcp_server(
                    server_copy, nodejs_dir=nodejs_dir,
                    artifact_base_dir=artifact_base_dir,
                )

        # Configure for each non-profile scope via claude mcp add
        for scope in non_profile_scopes:
            server_copy = server.copy()
            server_copy['scope'] = scope
            configure_mcp_server(
                server_copy, nodejs_dir=nodejs_dir,
                artifact_base_dir=artifact_base_dir,
            )

    # Create profile MCP config file if there are profile-scoped servers
    if profile_servers and profile_mcp_config_path:
        info(f'Creating profile MCP config with {len(profile_servers)} server(s)...')
        create_mcp_config_file(profile_servers, profile_mcp_config_path)
    elif profile_mcp_config_path and profile_mcp_config_path.exists():
        # Remove stale profile MCP config file when no profile servers are configured
        info(f'Removing stale profile MCP config: {profile_mcp_config_path.name}')
        try:
            profile_mcp_config_path.unlink()
            success(f'Removed stale profile MCP config: {profile_mcp_config_path.name}')
        except OSError as e:
            warning(f'Failed to remove stale profile MCP config: {e}')

    return True, profile_servers, stats


def create_mcp_config_file(
    servers: list[dict[str, Any]],
    config_path: Path,
) -> bool:
    """Create MCP server configuration JSON file for profile-scoped servers.

    Generates a JSON file in .mcp.json format with mcpServers key.
    This file is loaded via --strict-mcp-config --mcp-config at runtime,
    making these servers visible ONLY in the profile session.

    Args:
        servers: List of MCP server configurations with scope: profile
        config_path: Path where the JSON file will be written

    Returns:
        bool: True if successful, False otherwise
    """
    if not servers:
        return True

    mcp_config: dict[str, Any] = {'mcpServers': {}}

    for server in servers:
        name = server.get('name')
        if not name:
            warning('MCP server missing name, skipping')
            continue

        server_config: dict[str, Any] = {}

        # HTTP/SSE transport
        transport = server.get('transport')
        url = server.get('url')
        if transport and url:
            server_config['type'] = transport
            server_config['url'] = url
            header = server.get('header')
            # Parse header string to dict (format: "Key: Value")
            if header and ':' in header:
                key, _, value = header.partition(':')
                server_config['headers'] = {key.strip(): value.strip()}

        # Stdio transport - with proper command + args format
        command = server.get('command')
        if command:
            server_config['type'] = 'stdio'
            args_from_yaml = server.get('args')
            if args_from_yaml and isinstance(args_from_yaml, list):
                # Explicit command + args format from YAML (no parsing needed)
                expanded_cmd = expand_tildes_in_command(command).replace('\\', '/')
                server_config['command'] = expanded_cmd
                server_config['args'] = [str(a) for a in args_from_yaml]
            else:
                # Parse command string into command + args
                parsed = parse_mcp_command(command)
                server_config['command'] = parsed['command']
                if parsed['args']:
                    server_config['args'] = parsed['args']
            server_config['env'] = {}  # Format consistency with claude mcp add

        # Environment variables (override default empty env)
        env_config = server.get('env')
        if env_config:
            env_dict: dict[str, str] = {}
            if isinstance(env_config, str):
                # Single env var format: "KEY=VALUE"
                if '=' in env_config:
                    key, _, value = env_config.partition('=')
                    env_dict[key] = value
            elif isinstance(env_config, list):
                for item in cast(list[object], env_config):
                    if isinstance(item, str) and '=' in item:
                        key, _, value = item.partition('=')
                        env_dict[key] = value
            if env_dict:
                server_config['env'] = env_dict

        mcp_config['mcpServers'][name] = server_config

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(mcp_config, indent=2), encoding='utf-8')
        success(f'Created profile MCP config: {config_path.name}')
        return True
    except PermissionError:
        error(f'Permission denied writing to {config_path}')
        return False
    except Exception as e:
        error(f'Failed to create MCP config file: {e}')
        return False


# Pattern matching EnvironmentConfig.validate_command_names behavior:
# first character must be alphanumeric; subsequent characters may be alphanumeric, hyphens, or underscores
_SAFE_COMMAND_NAME_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]*$')


def validate_command_name_for_path(name: str) -> bool:
    """Validate that a command name is safe for use as a directory name.

    Rejects names containing path separators, traversal patterns, or
    characters outside the allowed set (alphanumeric, hyphens, underscores).
    The first character must be alphanumeric (no leading hyphens/underscores).

    Args:
        name: Command name to validate.

    Returns:
        True if safe, False otherwise.
    """
    if not name or not name.strip():
        return False
    if '/' in name or '\\' in name or '..' in name:
        return False
    if name.startswith('.'):
        return False
    return bool(_SAFE_COMMAND_NAME_PATTERN.match(name))


def download_hook_files(
    hooks: dict[str, Any],
    claude_user_dir: Path,
    config_source: str,
    base_url: str | None = None,
    auth_param: str | None = None,
    hooks_base_dir: Path | None = None,
    auth_cache: AuthHeaderCache | None = None,
) -> bool:
    """Download hook files from configuration.

    Extracts the file list from hooks configuration and delegates
    download/parallel logic to process_resources().

    Args:
        hooks: Hooks configuration dictionary with 'files' key
        claude_user_dir: Path to Claude user directory
        config_source: Config source for resolving resource paths
        base_url: Optional base URL for resolving resources
        auth_param: Optional authentication parameter
        hooks_base_dir: Optional base directory for hook files.
            When provided, hook files are downloaded to this directory
            instead of claude_user_dir / 'hooks'.
        auth_cache: Optional shared auth header cache for origin-level caching

    Returns:
        bool: True if all downloads successful, False otherwise.
    """
    hook_files = hooks.get('files', [])

    if not hook_files:
        info('No hook files to download')
        return True

    hooks_dir = hooks_base_dir if hooks_base_dir is not None else claude_user_dir / 'hooks'
    return process_resources(hook_files, hooks_dir, 'hook files', config_source, base_url, auth_param, auth_cache)


def _apply_common_hook_fields(
    hook_config: dict[str, Any],
    hook: dict[str, Any],
) -> None:
    """Apply common hook fields to the hook configuration dict.

    Passes through common fields (if, status-message, once, timeout) from
    the YAML hook event configuration to the output settings.json hook dict.
    Fields with None/missing values are skipped.

    Args:
        hook_config: The output hook configuration dict being built.
        hook: The source YAML hook event dict.
    """
    if hook.get('if') is not None:
        hook_config['if'] = hook['if']
    if hook.get('status-message') is not None:
        hook_config['statusMessage'] = hook['status-message']
    if hook.get('once') is not None:
        hook_config['once'] = hook['once']
    if hook.get('timeout') is not None:
        hook_config['timeout'] = hook['timeout']


def _build_hooks_json(
    hooks: dict[str, Any],
    hooks_dir: Path,
) -> dict[str, Any]:
    """Build hooks JSON structure from YAML configuration.

    Converts YAML hook event definitions into Claude Code's JSON hooks format.
    Generates absolute POSIX paths for hook file references. Supports all four
    hook types: command, http, prompt, agent.

    Used by create_profile_config() (per-environment config.json, atomic
    overwrite in isolated mode) and indirectly by
    write_profile_settings_to_settings() via _build_profile_settings()
    (shared ~/.claude/settings.json in non-isolated mode, deep-merged via
    _write_merged_json()).

    Args:
        hooks: Hooks configuration dictionary with optional 'events' key.
        hooks_dir: Directory containing downloaded hook files.

    Returns:
        Dictionary with hook event names as keys and matcher/hooks arrays
        as values. Empty dict if no hook events defined.
    """
    result: dict[str, Any] = {}

    hook_events = hooks.get('events', [])
    if not hook_events:
        return result

    for hook in hook_events:
        event = hook.get('event')
        matcher = hook.get('matcher', '')
        hook_type = hook.get('type', 'command')
        command = hook.get('command')
        config = hook.get('config')  # Optional config file reference

        if not event:
            warning('Invalid hook configuration: missing event, skipping')
            continue

        # Validate required fields per hook type
        if hook_type == 'command' and not command:
            warning('Invalid command hook: missing command, skipping')
            continue
        if hook_type == 'http' and not hook.get('url'):
            warning('Invalid http hook: missing url, skipping')
            continue
        if hook_type in ('prompt', 'agent') and not hook.get('prompt'):
            warning(f'Invalid {hook_type} hook: missing prompt, skipping')
            continue

        # Add to result
        if event not in result:
            result[event] = []

        # Find or create matcher group
        matcher_group: dict[str, Any] | None = None
        hooks_list_raw = result[event]
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
            hooks_event_list_raw = result[event]
            if isinstance(hooks_event_list_raw, list):
                hooks_event_list: list[dict[str, Any]] = cast(list[dict[str, Any]], hooks_event_list_raw)
                hooks_event_list.append(matcher_group)

        # Build hook configuration based on hook type
        hook_config: dict[str, Any]

        if hook_type == 'command':
            # Command hooks require file path processing
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
                is_python_script = clean_command.lower().endswith(('.py', '.pyw'))

                # Determine if this is a JavaScript/Node.js script (case-insensitive check)
                is_javascript_script = clean_command.lower().endswith(('.js', '.mjs', '.cjs'))

                if is_python_script:
                    # Python script - use uv run for cross-platform execution
                    hook_path = hooks_dir / Path(clean_command).name
                    hook_path_str = hook_path.as_posix()
                    full_command = f'uv run --no-project --python 3.12 {hook_path_str}'

                    # Append config file path if specified
                    if config:
                        clean_config = config.split('?')[0] if '?' in config else config
                        config_path = hooks_dir / Path(clean_config).name
                        config_path_str = config_path.as_posix()
                        full_command = f'{full_command} {config_path_str}'

                elif is_javascript_script:
                    # JavaScript script - use node for cross-platform execution
                    hook_path = hooks_dir / Path(clean_command).name
                    hook_path_str = hook_path.as_posix()
                    full_command = f'node {hook_path_str}'

                    # Append config file path if specified
                    if config:
                        clean_config = config.split('?')[0] if '?' in config else config
                        config_path = hooks_dir / Path(clean_config).name
                        config_path_str = config_path.as_posix()
                        full_command = f'{full_command} {config_path_str}'

                else:
                    # Other file - build absolute path and use as-is
                    hook_path = hooks_dir / Path(clean_command).name
                    hook_path_str = hook_path.as_posix()
                    full_command = hook_path_str

                    # Append config file path if specified
                    if config:
                        clean_config = config.split('?')[0] if '?' in config else config
                        config_path = hooks_dir / Path(clean_config).name
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
            # Pass through command-specific optional fields
            if hook.get('async') is not None:
                hook_config['async'] = hook['async']
            if hook.get('shell') is not None:
                hook_config['shell'] = hook['shell']

        elif hook_type == 'http':
            # HTTP hooks: pure pass-through, no file-path processing
            hook_config = {
                'type': hook_type,
                'url': hook.get('url', ''),
            }
            if hook.get('headers') is not None:
                hook_config['headers'] = hook['headers']
            if hook.get('allowed-env-vars') is not None:
                hook_config['allowedEnvVars'] = hook['allowed-env-vars']

        elif hook_type == 'prompt':
            # Prompt hooks: pass-through for prompt and model
            hook_config = {
                'type': hook_type,
                'prompt': hook.get('prompt', ''),
            }
            if hook.get('model') is not None:
                hook_config['model'] = hook['model']

        elif hook_type == 'agent':
            # Agent hooks: same structure as prompt but type is 'agent'
            hook_config = {
                'type': hook_type,
                'prompt': hook.get('prompt', ''),
            }
            if hook.get('model') is not None:
                hook_config['model'] = hook['model']

        else:
            warning(f'Unknown hook type: {hook_type}, skipping')
            continue

        # Apply common fields to ALL hook types
        _apply_common_hook_fields(hook_config, hook)

        if matcher_group and 'hooks' in matcher_group:
            matcher_hooks_raw = matcher_group['hooks']
            if isinstance(matcher_hooks_raw, list):
                matcher_hooks_list = cast(list[object], matcher_hooks_raw)
                matcher_hooks_list.append(hook_config)

    return result


def write_profile_settings_to_settings(
    settings_delta: dict[str, Any],
    settings_dir: Path,
) -> bool:
    """Deep-merge profile-owned settings delta into ~/.claude/settings.json.

    The shared ~/.claude/settings.json is a user-facing file written to
    by the toolbox, the Claude Code CLI, prior toolbox runs with other
    YAMLs, and (optionally) direct user edits. The writer MUST preserve
    any key outside the current delta. It MUST NOT destroy nested
    sub-keys or list elements that other contributors supplied. And it
    MUST honor RFC 7396 null-as-delete so that users can explicitly
    remove keys via YAML-level null.

    Delegates to ``_write_merged_json()`` to inherit all semantics from
    the same helper that powers ``write_user_settings()`` and
    ``write_global_config()``:

    - Deep-merge for nested dicts (dispatched per-key to
      ``_merge_recursive()``).
    - **Array-union with structural dedupe for EVERY list at every depth**
      (matches Claude Code CLI's cross-scope merge: "arrays are
      concatenated and deduplicated, not replaced"). Two hook matcher
      groups with the same ``matcher`` string from different
      contributions coexist as separate entries -- matches Claude Code's
      native concatenation; the runtime then dedupes by command string
      (for command hooks) and URL (for HTTP hooks) per the Claude Code
      hooks documentation.
    - RFC 7396 null-as-delete for any key whose value is ``None``
      (top-level or nested).
    - Preservation for keys omitted from ``settings_delta``.

    The delta is expected to be the output of
    ``_build_profile_settings()``, which contains one entry per
    YAML-declared profile-owned key (value for present-with-value keys,
    ``None`` for present-with-null keys, no entry for absent keys).

    IMPORTANT: This function is called ONLY in non-command-names mode.
    In command-names mode, profile settings are routed to the isolated
    ~/.claude/{cmd}/config.json via ``create_profile_config()`` with
    atomic overwrite semantics (isolated config is fully toolbox-owned).

    Args:
        settings_delta: Dict of profile-owned keys to write (output of
            ``_build_profile_settings()``). May be empty, in which case
            no file I/O occurs and the function returns ``True``.
        settings_dir: Directory containing settings.json (typically
            ~/.claude/).

    Returns:
        True on successful write or no-op (empty delta),
        False on read or write failure.
    """
    if not settings_delta:
        info('No profile settings to write to settings.json')
        return True

    settings_file = settings_dir / 'settings.json'
    info('Writing profile settings to settings.json...')

    # Delegate to the shared READ-MERGE-WRITE helper. Uses the default
    # array_union_keys=None (every array at every depth is unioned with
    # structural dedupe) and ensure_parent=True (creates settings_dir
    # if missing).
    ok, _ = _write_merged_json(settings_file, settings_delta)

    if ok:
        success(f'Wrote profile settings to {settings_file}')
    else:
        warning(f'Failed to write profile settings to {settings_file}')

    return ok


def _build_profile_settings(
    profile_config: dict[str, Any],
    hooks_dir: Path,
) -> dict[str, Any]:
    """Build profile settings dict from a per-key profile_config dict (pure, zero I/O).

    The ``profile_config`` parameter is a dict whose keys are the nine
    camelCase on-disk names (``model``, ``permissions``, ``env``,
    ``attribution``, ``alwaysThinkingEnabled``, ``effortLevel``,
    ``companyAnnouncements``, ``statusLine``, ``hooks``). Dict MEMBERSHIP
    encodes the YAML declaration state (present-with-value, present-with-null,
    or absent) which is intentionally preserved end-to-end so that the
    downstream writer can apply RFC 7396 null-as-delete to the shared
    ``settings.json`` for top-level YAML nulls.

    Three cases per key:

    - **Key absent** -- the builder OMITS the key from its output dict. The
      writer preserves the existing on-disk value (if any).
    - **Key present with value None** -- the builder emits
      ``settings[key] = None`` verbatim. The writer deletes the on-disk key
      via RFC 7396 null-as-delete semantics in ``_merge_recursive()``.
    - **Key present with a non-None value** -- the builder performs the
      usual truthy/empty handling (kebab-to-camel translation for
      ``permissions``, command-string construction for ``statusLine``,
      ``_build_hooks_json()`` delegation for ``hooks``) and emits the
      processed value. Empty dicts or empty lists remain as-is (so an
      empty ``attribution`` dict is still stored explicitly).

    The ``hooks`` value in ``profile_config`` is either ``None`` (YAML null),
    absent (YAML omitted), or the full YAML hooks configuration dict with
    ``files`` / ``events`` keys (which is then processed via
    ``_build_hooks_json()``).

    Args:
        profile_config: Dict of profile-owned keys to build settings from.
            Keys use camelCase on-disk names. Values correspond directly to
            the YAML-declared values (with pre-translation for ``permissions``
            kebab-case nested keys and pre-processing for ``statusLine``
            file references handled inside this function).
        hooks_dir: Absolute directory path where downloaded hook files reside.
            For isolated mode: ``~/.claude/{cmd}/hooks/``.
            For non-isolated mode: ``~/.claude/hooks/``.

    Returns:
        Dict containing only the keys that were present in ``profile_config``.
        Keys present with None values propagate through as ``settings[key] =
        None`` for downstream null-as-delete handling. Keys absent from
        ``profile_config`` are absent from the result.

    Examples:
        >>> _build_profile_settings({'model': 'sonnet'}, Path('/tmp/hooks'))
        {'model': 'sonnet'}

        >>> _build_profile_settings(
        ...     {'permissions': {'default-mode': 'ask', 'allow': ['Read']}},
        ...     Path('/tmp/hooks'),
        ... )
        {'permissions': {'defaultMode': 'ask', 'allow': ['Read']}}

        >>> _build_profile_settings({}, Path('/tmp/hooks'))
        {}

        >>> _build_profile_settings({'model': None}, Path('/tmp/hooks'))
        {'model': None}
    """
    settings: dict[str, Any] = {}

    # model
    if 'model' in profile_config:
        model = profile_config['model']
        if model is None:
            settings['model'] = None
            info('Deleting model via explicit null')
        elif model:
            settings['model'] = model
            info(f'Setting model: {model}')

    # permissions (kebab-to-camel translation for nested keys)
    if 'permissions' in profile_config:
        permissions = profile_config['permissions']
        if permissions is None:
            settings['permissions'] = None
            info('Deleting permissions via explicit null')
        elif permissions:
            final_permissions = permissions.copy()
            if 'default-mode' in final_permissions:
                final_permissions['defaultMode'] = final_permissions.pop('default-mode')
            if 'additional-directories' in final_permissions:
                final_permissions['additionalDirectories'] = final_permissions.pop('additional-directories')
            info('Using permissions from environment configuration')
            settings['permissions'] = final_permissions

    # env (values stringified)
    if 'env' in profile_config:
        env = profile_config['env']
        if env is None:
            settings['env'] = None
            info('Deleting env via explicit null')
        elif env:
            settings['env'] = {k: str(v) for k, v in env.items()}
            info(f'Setting {len(env)} environment variables')
            for key in env:
                info(f'  - {key}')

    # attribution (empty dict is explicit and kept)
    if 'attribution' in profile_config:
        attribution = profile_config['attribution']
        if attribution is None:
            settings['attribution'] = None
            info('Deleting attribution via explicit null')
        else:
            settings['attribution'] = attribution
            commit_preview = repr(attribution.get('commit', ''))[:30]
            pr_preview = repr(attribution.get('pr', ''))[:30]
            info(f'Setting attribution: commit={commit_preview}, pr={pr_preview}')

    # alwaysThinkingEnabled (False is explicit and kept)
    if 'alwaysThinkingEnabled' in profile_config:
        always_thinking_enabled = profile_config['alwaysThinkingEnabled']
        if always_thinking_enabled is None:
            settings['alwaysThinkingEnabled'] = None
            info('Deleting alwaysThinkingEnabled via explicit null')
        else:
            settings['alwaysThinkingEnabled'] = always_thinking_enabled
            info(f'Setting alwaysThinkingEnabled: {always_thinking_enabled}')

    # effortLevel
    if 'effortLevel' in profile_config:
        effort_level = profile_config['effortLevel']
        if effort_level is None:
            settings['effortLevel'] = None
            info('Deleting effortLevel via explicit null')
        else:
            settings['effortLevel'] = effort_level
            info(f'Setting effortLevel: {effort_level}')

    # companyAnnouncements
    if 'companyAnnouncements' in profile_config:
        company_announcements = profile_config['companyAnnouncements']
        if company_announcements is None:
            settings['companyAnnouncements'] = None
            info('Deleting companyAnnouncements via explicit null')
        else:
            settings['companyAnnouncements'] = company_announcements
            info(f'Setting companyAnnouncements: {len(company_announcements)} announcement(s)')

    # statusLine (command-string construction)
    if 'statusLine' in profile_config:
        status_line = profile_config['statusLine']
        if status_line is None:
            settings['statusLine'] = None
            info('Deleting statusLine via explicit null')
        elif isinstance(status_line, dict):
            status_line_file = status_line.get('file')
            if status_line_file:
                # Build absolute path to the hook file in hooks directory
                # Strip query parameters from filename
                clean_filename = status_line_file.split('?')[0] if '?' in status_line_file else status_line_file
                filename = Path(clean_filename).name
                hook_path = hooks_dir / filename
                hook_path_str = hook_path.as_posix()

                # Extract optional config file reference
                status_line_config_file = status_line.get('config')

                # Determine command based on file extension
                if filename.lower().endswith(('.py', '.pyw')):
                    # Python script - use uv run
                    status_line_command = f'uv run --no-project --python 3.12 {hook_path_str}'

                    # Append config file path if specified
                    if status_line_config_file:
                        # Strip query parameters from config filename
                        clean_config = (
                            status_line_config_file.split('?')[0]
                            if '?' in status_line_config_file
                            else status_line_config_file
                        )
                        config_path = hooks_dir / Path(clean_config).name
                        config_path_str = config_path.as_posix()
                        status_line_command = f'{status_line_command} {config_path_str}'
                else:
                    # Other file - use path directly
                    status_line_command = hook_path_str

                    # Append config file path if specified
                    if status_line_config_file:
                        # Strip query parameters from config filename
                        clean_config = (
                            status_line_config_file.split('?')[0]
                            if '?' in status_line_config_file
                            else status_line_config_file
                        )
                        config_path = hooks_dir / Path(clean_config).name
                        config_path_str = config_path.as_posix()
                        status_line_command = f'{status_line_command} {config_path_str}'

                status_line_built: dict[str, Any] = {
                    'type': 'command',
                    'command': status_line_command,
                }

                # Add optional padding
                padding = status_line.get('padding')
                if padding is not None:
                    status_line_built['padding'] = padding

                settings['statusLine'] = status_line_built
                info(f'Setting statusLine: {filename}')

    # hooks (delegates to _build_hooks_json for non-null, non-empty values)
    if 'hooks' in profile_config:
        hooks = profile_config['hooks']
        if hooks is None:
            settings['hooks'] = None
            info('Deleting hooks via explicit null')
        elif hooks:
            hooks_json = _build_hooks_json(hooks, hooks_dir)
            if hooks_json:
                settings['hooks'] = hooks_json

    return settings


def create_profile_config(
    profile_config: dict[str, Any],
    config_base_dir: Path,
    hooks_base_dir: Path | None = None,
) -> bool:
    """Create config.json (profile configuration) for the isolated environment.

    Delegates to the pure builder _build_profile_settings() and atomically
    writes the result to ~/.claude/{cmd}/config.json. This file is always
    overwritten on re-run, so YAML removals of keys cleanly propagate to the
    isolated profile (isolated-mode atomic rebuild semantics).

    In isolated mode, the on-disk config.json is fully toolbox-owned: each
    invocation rebuilds the file from scratch, so the distinction between
    "YAML key absent" and "YAML key set to null" is cosmetic -- both cases
    produce a config.json without the key (absent keys are omitted by the
    builder, and null-valued keys serialize as ``"key": null`` in JSON,
    which is equivalent to absent for Claude Code's priority-resolution).

    Args:
        profile_config: Dict of profile-owned keys (camelCase on-disk names).
            Keys present with values are written; keys present with None are
            written as JSON null; keys absent are omitted. For the ``hooks``
            key, the value is the full YAML hooks configuration dict with
            ``files`` / ``events`` keys.
        config_base_dir: Path to the isolated environment directory
            (e.g., ~/.claude/{cmd}/).
        hooks_base_dir: Optional base directory for hook files.
            When provided, hook file paths are resolved relative to this directory
            instead of config_base_dir / 'hooks'.

    Returns:
        bool: True if successful, False otherwise.
    """
    # Determine hooks directory: use hooks_base_dir if provided, else default
    hooks_dir = hooks_base_dir if hooks_base_dir is not None else config_base_dir / 'hooks'

    info('Creating config.json...')

    # Build the profile settings dict via the shared pure builder
    settings = _build_profile_settings(profile_config, hooks_dir)

    # Save settings (always overwrite) - atomic rebuild semantics
    settings_path = config_base_dir / 'config.json'
    try:
        config_base_dir.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(settings, indent=2), encoding='utf-8')
        success('Created config.json')
        return True
    except Exception as e:
        error(f'Failed to save config.json: {e}')
        return False


def write_manifest(
    config_base_dir: Path,
    command_name: str,
    config_version: str | None,
    config_source: str,
    config_source_type: str,
    config_source_url: str | None,
    command_names: list[str],
) -> bool:
    """Write installation manifest for the environment configuration.

    Creates manifest.json containing metadata about the installed
    configuration. Used by version checking hooks to determine if updates are available.

    Args:
        config_base_dir: Path to the isolated environment directory (e.g., ~/.claude/{cmd}/)
        command_name: Primary command name
        config_version: Optional semantic version from config (e.g., "1.3.0")
        config_source: Raw config source as provided by user
        config_source_type: Classified source type ("url", "local", "repo")
        config_source_url: Resolved fetch URL, or None for local sources
        command_names: List of all command names (primary + aliases)

    Returns:
        True if manifest was written successfully, False otherwise.
    """
    manifest_path = config_base_dir / 'manifest.json'

    manifest: dict[str, Any] = {
        'name': command_name,
        'version': config_version,
        'config_source': config_source,
        'config_source_url': config_source_url,
        'config_source_type': config_source_type,
        'installed_at': datetime.now(UTC).isoformat(),
        'last_checked_at': None,
        'command_names': command_names,
    }

    try:
        config_base_dir.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        success('Created manifest.json')
        return True
    except Exception as e:
        warning(f'Failed to write manifest: {e}')
        return False


def cleanup_stale_marker(config_base_dir: Path) -> None:
    """Remove stale update-available marker file during re-installation.

    When setup_environment.py runs, any existing update marker is no longer valid
    because the user is actively installing/updating the configuration.

    Args:
        config_base_dir: Path to the isolated environment directory (e.g., ~/.claude/{cmd}/)
    """
    marker_path = config_base_dir / 'update-available.json'
    if marker_path.exists():
        try:
            marker_path.unlink()
            info(f'Removed stale update marker: {marker_path.name}')
        except OSError as e:
            warning(f'Failed to remove stale update marker: {e}')


def _get_update_check_snippet(update_marker_path: str, command_name: str = '') -> str:
    """Generate bash snippet for configuration update notification.

    Produces a shell script fragment that checks for the update marker file
    and prints a colored warning if a new configuration version is available.

    Args:
        update_marker_path: Shell-evaluable path to the update marker file
            (e.g., "$HOME/.claude/mycmd/update-available.json")
        command_name: Optional command name for display in the notification

    Returns:
        Bash script snippet that checks for update marker file.
    """
    display_name = f'the {command_name} ' if command_name else ''
    return f'''# Check for configuration update notification
UPDATE_MARKER="{update_marker_path}"
if [ -f "$UPDATE_MARKER" ]; then
  echo -e "\\\\033[1;33m[UPDATE] A new version of {display_name}configuration is available.\\\\033[0m"
  echo -e "\\\\033[1;33m         Re-run the installer to update.\\\\033[0m"
fi

'''


def create_launcher_script(
    config_base_dir: Path,
    command_name: str,
    system_prompt_file: str | None = None,
    mode: str = 'replace',
    has_profile_mcp_servers: bool = False,
) -> tuple[Path, Path] | None:
    """Create launcher script for starting Claude with optional system prompt.

    On Windows, creates three files inside config_base_dir:
      - start.ps1 (PowerShell wrapper)
      - start.cmd (CMD wrapper)
      - launch.sh (shared POSIX launcher -- the actual launcher)

    On Unix, creates one file inside config_base_dir:
      - launch.sh (the launcher, entry point for symlinks)

    Args:
        config_base_dir: Path to the isolated environment directory (e.g., ~/.claude/{cmd}/)
        command_name: Name of the command to create launcher for
        system_prompt_file: Optional system prompt filename (if None, only settings are used)
        mode: System prompt mode ('append' or 'replace'), defaults to 'replace'
        has_profile_mcp_servers: Whether profile-scoped MCP servers exist (enables --strict-mcp-config)

    Returns:
        Tuple of (main_launcher_path, launch_script_path) if created successfully,
        None otherwise. On Windows, main_launcher_path is start.ps1 and
        launch_script_path is launch.sh. On Unix, both are launch.sh.
    """
    # Log if profile MCP servers will be configured via --strict-mcp-config
    if has_profile_mcp_servers:
        info('Launcher will use --strict-mcp-config for profile MCP isolation')

    system = platform.system()

    # Will hold the shared POSIX launch script path (Windows only; on Unix, same as launcher_path)
    shared_sh: Path | None = None

    try:
        config_base_dir.mkdir(parents=True, exist_ok=True)
        if system == 'Windows':
            # Create PowerShell wrapper for Windows
            launcher_path = config_base_dir / 'start.ps1'
            launcher_content = f'''# Claude Code Environment Launcher
# This script starts Claude Code with the configured environment

$claudeUserDir = Join-Path $env:USERPROFILE ".claude"

# Source OS-level environment variables (if configured)
$envFile = Join-Path (Join-Path $claudeUserDir "{command_name}") "env.ps1"
if (Test-Path $envFile) {{ . $envFile }}

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

# Call the shared launch script
$scriptPath = Join-Path (Join-Path $claudeUserDir "{command_name}") "launch.sh"

if ($args.Count -gt 0) {{
    Write-Host "Passing additional arguments: $args" -ForegroundColor Cyan
    & $bashPath --login $scriptPath @args
}} else {{
    & $bashPath --login $scriptPath
}}
'''
            launcher_path.write_text(launcher_content)

            # Also create a CMD batch file wrapper
            batch_path = config_base_dir / 'start.cmd'
            batch_content = f'''@echo off
REM Claude Code Environment Launcher for CMD
REM This script starts Claude Code with the configured environment

REM Source OS-level environment variables (if configured)
set "ENV_FILE=%USERPROFILE%\\.claude\\{command_name}\\env.cmd"
if exist "%ENV_FILE%" call "%ENV_FILE%"

echo Starting Claude Code with {command_name} configuration...

REM Call shared script
set "BASH_EXE=C:\\Program Files\\Git\\bin\\bash.exe"
if not exist "%BASH_EXE%" set "BASH_EXE=C:\\Program Files (x86)\\Git\\bin\\bash.exe"

set "SCRIPT_WIN=%USERPROFILE%\\.claude\\{command_name}\\launch.sh"

if "%~1"=="" (
    "%BASH_EXE%" --login "%SCRIPT_WIN%"
) else (
    echo Passing additional arguments: %*
    "%BASH_EXE%" --login "%SCRIPT_WIN%" %*
)
'''
            batch_path.write_text(batch_content)

            # Create shared POSIX script that actually launches Claude
            shared_sh = config_base_dir / 'launch.sh'

            # Build the exec command based on whether system prompt is provided
            if system_prompt_file:
                # Load prompt file first (common for both modes)
                shared_sh_content = f'''#!/usr/bin/env bash
set -euo pipefail

# Set isolated environment directory
export CLAUDE_CONFIG_DIR="$HOME/.claude/{command_name}"

# Source OS-level environment variables (if configured)
ENV_FILE="$HOME/.claude/{command_name}/env.sh"
[ -f "$ENV_FILE" ] && . "$ENV_FILE"

# Get Windows path for settings
SETTINGS_WIN="$(cygpath -m "$HOME/.claude/{command_name}/config.json" 2>/dev/null ||
  echo "$HOME/.claude/{command_name}/config.json")"

# MCP configuration for profile-scoped servers
MCP_CONFIG_PATH="$HOME/.claude/{command_name}/mcp.json"
MCP_FLAGS=""
if [ -f "$MCP_CONFIG_PATH" ]; then
  MCP_WIN="$(cygpath -m "$MCP_CONFIG_PATH" 2>/dev/null || echo "$MCP_CONFIG_PATH")"
  MCP_FLAGS="--strict-mcp-config --mcp-config $MCP_WIN"
fi

PROMPT_PATH="$HOME/.claude/{command_name}/prompts/{system_prompt_file}"
if [ ! -f "$PROMPT_PATH" ]; then
  echo "Error: System prompt not found at $PROMPT_PATH" >&2
  exit 1
fi

# Version detection function
get_claude_version() {{
  claude --version 2>/dev/null | grep -oE '[0-9]+\\.[0-9]+\\.[0-9]+' | head -1
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
                # Inject update check snippet before mode-specific logic
                shared_sh_content += _get_update_check_snippet(
                    f'$HOME/.claude/{command_name}/update-available.json', command_name,
                )

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
  exec claude $MCP_FLAGS --system-prompt-file "$PROMPT_PATH" "$@" --settings "$SETTINGS_WIN"
elif [ "$HAS_CONTINUE" = true ]; then
  # Legacy workaround for v < 2.0.64: use --append-system-prompt for continuation
  # Continuation: use --append-system-prompt-file if available (v2.0.34+)
  if version_ge "$CLAUDE_VERSION" "2.0.34"; then
    exec claude $MCP_FLAGS --append-system-prompt-file "$PROMPT_PATH" "$@" --settings "$SETTINGS_WIN"
  else
    # For Claude < 2.0.34: check prompt size to avoid "Argument list too long"
    PROMPT_SIZE=$(get_file_size "$PROMPT_PATH")
    if [ "$PROMPT_SIZE" -lt "$SAFE_PROMPT_SIZE" ]; then
      # Small prompt: safe to use content-based flag
      PROMPT_CONTENT=$(cat "$PROMPT_PATH")
      exec claude $MCP_FLAGS --append-system-prompt "$PROMPT_CONTENT" "$@" --settings "$SETTINGS_WIN"
    else
      # Large prompt: skip to prevent error
      echo "Warning: System prompt too large ($PROMPT_SIZE bytes) for Claude < 2.0.34" >&2
      echo "Skipping prompt to prevent 'Argument list too long' error" >&2
      echo "Solutions: 1) Upgrade to Claude v2.0.34+, 2) Reduce prompt to <4KB" >&2
      exec claude $MCP_FLAGS "$@" --settings "$SETTINGS_WIN"
    fi
  fi
else
  # New session: use --system-prompt-file (available in v2.0.14+)
  if version_ge "$CLAUDE_VERSION" "2.0.14"; then
    exec claude $MCP_FLAGS --system-prompt-file "$PROMPT_PATH" "$@" --settings "$SETTINGS_WIN"
  else
    # Fallback to content-based flag for very old versions
    PROMPT_CONTENT=$(cat "$PROMPT_PATH")
    exec claude $MCP_FLAGS --system-prompt "$PROMPT_CONTENT" "$@" --settings "$SETTINGS_WIN"
  fi
fi
'''
                else:  # mode == 'append'
                    # Append mode: use --append-system-prompt-file if available
                    shared_sh_content += '''# Append mode: use --append-system-prompt-file if available (v2.0.34+)
if version_ge "$CLAUDE_VERSION" "2.0.34"; then
  exec claude $MCP_FLAGS --append-system-prompt-file "$PROMPT_PATH" "$@" --settings "$SETTINGS_WIN"
else
  # For Claude < 2.0.34: check prompt size to avoid "Argument list too long"
  PROMPT_SIZE=$(get_file_size "$PROMPT_PATH")
  if [ "$PROMPT_SIZE" -lt "$SAFE_PROMPT_SIZE" ]; then
    # Small prompt: safe to use content-based flag
    PROMPT_CONTENT=$(cat "$PROMPT_PATH")
    exec claude $MCP_FLAGS --append-system-prompt "$PROMPT_CONTENT" "$@" --settings "$SETTINGS_WIN"
  else
    # Large prompt: skip to prevent error
    echo "Warning: System prompt too large ($PROMPT_SIZE bytes) for Claude < 2.0.34" >&2
    echo "Skipping prompt to prevent 'Argument list too long' error" >&2
    echo "Solutions: 1) Upgrade to Claude v2.0.34+, 2) Reduce prompt to <4KB" >&2
    exec claude $MCP_FLAGS "$@" --settings "$SETTINGS_WIN"
  fi
fi
'''
            else:
                # No system prompt, only settings
                update_snippet = _get_update_check_snippet(
                    f'$HOME/.claude/{command_name}/update-available.json', command_name,
                )
                shared_sh_content = f'''#!/usr/bin/env bash
set -euo pipefail

# Set isolated environment directory
export CLAUDE_CONFIG_DIR="$HOME/.claude/{command_name}"

# Source OS-level environment variables (if configured)
ENV_FILE="$HOME/.claude/{command_name}/env.sh"
[ -f "$ENV_FILE" ] && . "$ENV_FILE"

# Get Windows path for settings
SETTINGS_WIN="$(cygpath -m "$HOME/.claude/{command_name}/config.json" 2>/dev/null ||
  echo "$HOME/.claude/{command_name}/config.json")"

# MCP configuration for profile-scoped servers
MCP_CONFIG_PATH="$HOME/.claude/{command_name}/mcp.json"
MCP_FLAGS=""
if [ -f "$MCP_CONFIG_PATH" ]; then
  MCP_WIN="$(cygpath -m "$MCP_CONFIG_PATH" 2>/dev/null || echo "$MCP_CONFIG_PATH")"
  MCP_FLAGS="--strict-mcp-config --mcp-config $MCP_WIN"
fi

{update_snippet}exec claude $MCP_FLAGS "$@" --settings "$SETTINGS_WIN"
'''
            shared_sh.write_text(shared_sh_content, newline='\n')
            # Make it executable for bash
            with contextlib.suppress(Exception):
                shared_sh.chmod(0o755)

        else:
            # Create bash launcher for Unix-like systems
            launcher_path = config_base_dir / 'launch.sh'

            if system_prompt_file:
                # Load prompt file first (common for both modes)
                launcher_content = f'''#!/usr/bin/env bash
# Claude Code Environment Launcher
# This script starts Claude Code with the configured environment

# Set isolated environment directory
export CLAUDE_CONFIG_DIR="$HOME/.claude/{command_name}"

# Source OS-level environment variables (if configured)
ENV_FILE="$HOME/.claude/{command_name}/env.sh"
[ -f "$ENV_FILE" ] && . "$ENV_FILE"

SETTINGS_PATH="$HOME/.claude/{command_name}/config.json"
PROMPT_PATH="$HOME/.claude/{command_name}/prompts/{system_prompt_file}"

# MCP configuration for profile-scoped servers
MCP_CONFIG_PATH="$HOME/.claude/{command_name}/mcp.json"
MCP_FLAGS=""
if [ -f "$MCP_CONFIG_PATH" ]; then
  MCP_FLAGS="--strict-mcp-config --mcp-config $MCP_CONFIG_PATH"
fi

if [ ! -f "$PROMPT_PATH" ]; then
    echo -e "\\033[0;31mError: System prompt not found at $PROMPT_PATH\\033[0m"
    echo -e "\\033[1;33mPlease run setup_environment.py first\\033[0m"
    exit 1
fi

# Version detection function
get_claude_version() {{
  claude --version 2>/dev/null | grep -oE '[0-9]+\\.[0-9]+\\.[0-9]+' | head -1
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
                # Inject update check snippet before mode-specific logic
                launcher_content += _get_update_check_snippet(
                    f'$HOME/.claude/{command_name}/update-available.json', command_name,
                )

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
  claude $MCP_FLAGS --system-prompt-file "$PROMPT_PATH" "$@" --settings "$SETTINGS_PATH"
elif [ "$HAS_CONTINUE" = true ]; then
  echo -e "\\033[0;32mResuming Claude Code session with {command_name} configuration...\\033[0m"
  # Legacy workaround for v < 2.0.64: use --append-system-prompt for continuation
  # Continuation: use --append-system-prompt-file if available (v2.0.34+)
  if version_ge "$CLAUDE_VERSION" "2.0.34"; then
    claude $MCP_FLAGS --append-system-prompt-file "$PROMPT_PATH" "$@" --settings "$SETTINGS_PATH"
  else
    # For Claude < 2.0.34: check prompt size to avoid "Argument list too long"
    PROMPT_SIZE=$(get_file_size "$PROMPT_PATH")
    if [ "$PROMPT_SIZE" -lt "$SAFE_PROMPT_SIZE" ]; then
      # Small prompt: safe to use content-based flag
      PROMPT_CONTENT=$(cat "$PROMPT_PATH")
      claude $MCP_FLAGS --append-system-prompt "$PROMPT_CONTENT" "$@" --settings "$SETTINGS_PATH"
    else
      # Large prompt: skip to prevent error
      echo "Warning: System prompt too large ($PROMPT_SIZE bytes) for Claude < 2.0.34" >&2
      echo "Skipping prompt to prevent 'Argument list too long' error" >&2
      echo "Solutions: 1) Upgrade to Claude v2.0.34+, 2) Reduce prompt to <4KB" >&2
      claude $MCP_FLAGS "$@" --settings "$SETTINGS_PATH"
    fi
  fi
else
  echo -e "\\033[0;32mStarting Claude Code with {command_name} configuration...\\033[0m"
  # New session: use --system-prompt-file (available in v2.0.14+)
  if version_ge "$CLAUDE_VERSION" "2.0.14"; then
    claude $MCP_FLAGS --system-prompt-file "$PROMPT_PATH" "$@" --settings "$SETTINGS_PATH"
  else
    # Fallback to content-based flag for very old versions
    PROMPT_CONTENT=$(cat "$PROMPT_PATH")
    claude $MCP_FLAGS --system-prompt "$PROMPT_CONTENT" "$@" --settings "$SETTINGS_PATH"
  fi
fi
'''
                else:  # mode == 'append'
                    # Append mode: use --append-system-prompt-file if available
                    launcher_content += f'''# Append mode: use --append-system-prompt-file if available (v2.0.34+)
echo -e "\\033[0;32mStarting Claude Code with {command_name} configuration...\\033[0m"
if version_ge "$CLAUDE_VERSION" "2.0.34"; then
  claude $MCP_FLAGS --append-system-prompt-file "$PROMPT_PATH" "$@" --settings "$SETTINGS_PATH"
else
  # For Claude < 2.0.34: check prompt size to avoid "Argument list too long"
  PROMPT_SIZE=$(get_file_size "$PROMPT_PATH")
  if [ "$PROMPT_SIZE" -lt "$SAFE_PROMPT_SIZE" ]; then
    # Small prompt: safe to use content-based flag
    PROMPT_CONTENT=$(cat "$PROMPT_PATH")
    claude $MCP_FLAGS --append-system-prompt "$PROMPT_CONTENT" "$@" --settings "$SETTINGS_PATH"
  else
    # Large prompt: skip to prevent error
    echo "Warning: System prompt too large ($PROMPT_SIZE bytes) for Claude < 2.0.34" >&2
    echo "Skipping prompt to prevent 'Argument list too long' error" >&2
    echo "Solutions: 1) Upgrade to Claude v2.0.34+, 2) Reduce prompt to <4KB" >&2
    claude $MCP_FLAGS "$@" --settings "$SETTINGS_PATH"
  fi
fi
'''
            else:
                update_snippet_unix = _get_update_check_snippet(
                    f'$HOME/.claude/{command_name}/update-available.json', command_name,
                )
                launcher_content = f'''#!/usr/bin/env bash
# Claude Code Environment Launcher
# This script starts Claude Code with the configured environment

# Set isolated environment directory
export CLAUDE_CONFIG_DIR="$HOME/.claude/{command_name}"

# Source OS-level environment variables (if configured)
ENV_FILE="$HOME/.claude/{command_name}/env.sh"
[ -f "$ENV_FILE" ] && . "$ENV_FILE"

SETTINGS_PATH="$HOME/.claude/{command_name}/config.json"

# MCP configuration for profile-scoped servers
MCP_CONFIG_PATH="$HOME/.claude/{command_name}/mcp.json"
MCP_FLAGS=""
if [ -f "$MCP_CONFIG_PATH" ]; then
  MCP_FLAGS="--strict-mcp-config --mcp-config $MCP_CONFIG_PATH"
fi

{update_snippet_unix}echo -e "\\033[0;32mStarting Claude Code with {command_name} configuration...\\033[0m"

# Pass any additional arguments to Claude
claude $MCP_FLAGS "$@" --settings "$SETTINGS_PATH"
'''
            launcher_path.write_text(launcher_content)
            launcher_path.chmod(0o755)

        success('Created launcher script')

        if system == 'Windows':
            assert shared_sh is not None  # Always set in Windows branch above
            return (launcher_path, shared_sh)
        return (launcher_path, launcher_path)

    except Exception as e:
        warning(f'Failed to create launcher script: {e}')
        return None


def register_global_command(
    launcher_path: Path,
    command_name: str,
    additional_names: list[str] | None = None,
    launch_script_path: Path | None = None,
) -> bool:
    """Register global command(s) in ~/.local/bin/.

    On Windows, creates wrappers for PowerShell (.ps1), CMD (.cmd), and Git Bash
    in ~/.local/bin/. PowerShell wrappers reference launcher_path (start.ps1);
    CMD and Git Bash wrappers reference launch_script_path (launch.sh).

    On Unix, creates symlinks in ~/.local/bin/ pointing to launcher_path.

    Args:
        launcher_path: Path to the main launcher script (start.ps1 on Windows,
            launch.sh on Unix).
        command_name: Primary command name (used for file naming).
        additional_names: Optional list of additional command names (aliases).
        launch_script_path: Path to the shared POSIX launch script (launch.sh).
            Required on Windows for CMD and Git Bash wrappers. On Unix this
            parameter is not used (symlinks point to launcher_path directly).

    Returns:
        True if registration succeeded, False otherwise.
    """
    info(f'Registering global {command_name} command...')

    system = platform.system()

    try:
        if system == 'Windows':
            # Create batch file in .local/bin
            local_bin = get_real_user_home() / '.local' / 'bin'
            local_bin.mkdir(parents=True, exist_ok=True)

            # Derive shell-format paths for the launch script
            if launch_script_path is not None:
                home_str = str(get_real_user_home())
                # Windows CMD path: convert to %USERPROFILE% form
                launch_sh_str = str(launch_script_path).replace('/', '\\')
                cmd_script_path = launch_sh_str.replace(home_str, '%USERPROFILE%')
                # Git Bash path: convert to $HOME form
                bash_script_path = str(launch_script_path).replace('\\', '/')
                bash_home = home_str.replace('\\', '/')
                bash_script_path = bash_script_path.replace(bash_home, '$HOME')
            else:
                # Fallback for backward compatibility
                cmd_script_path = f'%USERPROFILE%\\.claude\\{command_name}\\launch.sh'
                bash_script_path = f'$HOME/.claude/{command_name}/launch.sh'

            # Create wrappers for all Windows shells
            # CMD wrapper
            batch_path = local_bin / f'{command_name}.cmd'
            batch_content = f'''@echo off
REM Global {command_name} command for CMD
REM Source OS-level environment variables (if configured)
set "ENV_FILE=%USERPROFILE%\\.claude\\{command_name}\\env.cmd"
if exist "%ENV_FILE%" call "%ENV_FILE%"
set "BASH_EXE=C:\\Program Files\\Git\\bin\\bash.exe"
if not exist "%BASH_EXE%" set "BASH_EXE=C:\\Program Files (x86)\\Git\\bin\\bash.exe"
set "SCRIPT_WIN={cmd_script_path}"
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

            # Git Bash wrapper - call the shared launch script
            bash_wrapper_path = local_bin / command_name
            bash_content = f'''#!/bin/bash
# Bash wrapper for {command_name} to work in Git Bash

# Call the shared launch script
exec "{bash_script_path}" "$@"
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
REM Source OS-level environment variables (if configured)
set "ENV_FILE=%USERPROFILE%\\.claude\\{command_name}\\env.cmd"
if exist "%ENV_FILE%" call "%ENV_FILE%"
set "BASH_EXE=C:\\Program Files\\Git\\bin\\bash.exe"
if not exist "%BASH_EXE%" set "BASH_EXE=C:\\Program Files (x86)\\Git\\bin\\bash.exe"
set "SCRIPT_WIN={cmd_script_path}"
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
exec "{bash_script_path}" "$@"
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
            local_bin = get_real_user_home() / '.local' / 'bin'
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
            info('Add this to your shell config if needed:')
            info('  Bash/Zsh: export PATH="$HOME/.local/bin:$PATH"')
            info('  Fish: fish_add_path ~/.local/bin')

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
        print(f"[DEBUG] CLAUDE_CODE_TOOLBOX_ENV_CONFIG: {os.environ.get('CLAUDE_CODE_TOOLBOX_ENV_CONFIG', 'NOT SET')}")
        print(f'[DEBUG] Was elevated via UAC: {was_elevated_via_uac}')

    return remaining_args, was_elevated_via_uac


def resolve_args(args: argparse.Namespace) -> argparse.Namespace:
    """Merge CLI flags with environment variable equivalents.

    CLI flags take precedence over environment variables. For boolean
    flags (store_true), argparse defaults to False when the flag is
    absent, so the env var acts as a fallback for piped invocations
    where CLI flags cannot be passed.

    Called immediately after parse_args() and before any flag-dependent
    logic (admin checks, confirmation gates, installation flow).

    Args:
        args: Parsed command-line arguments from argparse.

    Returns:
        Modified args namespace with environment variables merged.
    """
    args.yes = args.yes or os.environ.get('CLAUDE_CODE_TOOLBOX_CONFIRM_INSTALL') == '1'
    args.dry_run = args.dry_run or os.environ.get('CLAUDE_CODE_TOOLBOX_DRY_RUN') == '1'
    args.skip_install = args.skip_install or os.environ.get('CLAUDE_CODE_TOOLBOX_SKIP_INSTALL') == '1'
    args.no_admin = args.no_admin or os.environ.get('CLAUDE_CODE_TOOLBOX_NO_ADMIN') == '1'
    if not args.auth:
        args.auth = os.environ.get('CLAUDE_CODE_TOOLBOX_ENV_AUTH')
    return args


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
            print(f"[DEBUG] Config from env: {os.environ.get('CLAUDE_CODE_TOOLBOX_ENV_CONFIG', 'NOT SET')}")
            print(f'[DEBUG] Was elevated via UAC: {was_elevated_via_uac}')

        # Show that we're running elevated (only if via UAC)
        if was_elevated_via_uac:
            print()
            print(f'{Colors.GREEN}========================================================================{Colors.NC}')
            print(f'{Colors.GREEN}     Running with Administrator Privileges{Colors.NC}')
            print(f'{Colors.GREEN}========================================================================{Colors.NC}')
            print()

    # Refuse to run as root on Unix unless explicitly allowed
    if platform.system() != 'Windows':
        geteuid = getattr(os, 'geteuid', None)
        if geteuid is not None and geteuid() == 0 and os.environ.get('CLAUDE_CODE_TOOLBOX_ALLOW_ROOT') != '1':
            error('This script should NOT be run as root or with sudo')
            print()
            warning('Running as root creates configuration under /root/,')
            warning('not for the regular user you intend to configure.')
            print()
            info('Instead, run as your regular user:')
            info('  curl -fsSL https://raw.githubusercontent.com/alex-feel/'
                 'claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash')
            print()
            info('The installer will request sudo only when needed (e.g., npm).')
            info('To force root execution: CLAUDE_CODE_TOOLBOX_ALLOW_ROOT=1 <command>')
            sys.exit(1)

    parser = argparse.ArgumentParser(description='Setup development environment for Claude Code')
    parser.add_argument('config', nargs='?', help='Configuration file name (e.g., python.yaml)')
    parser.add_argument('--skip-install', action='store_true', help='Skip Claude Code installation')
    parser.add_argument('--auth', type=str, help='Authentication for private repos (e.g., "token" or "header:token")')
    parser.add_argument('--no-admin', action='store_true', help='Do not request admin elevation even if needed')
    parser.add_argument(
        '--yes', '-y',
        action='store_true',
        help='Auto-confirm installation (skip interactive confirmation)',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show installation plan and exit without installing',
    )
    args = parser.parse_args()
    resolve_args(args)

    # Get configuration from args or environment
    config_name = args.config or os.environ.get('CLAUDE_CODE_TOOLBOX_ENV_CONFIG')

    if not config_name:
        error('No configuration specified!')
        info('Usage: setup_environment.py <config_name>')
        info('   or: CLAUDE_CODE_TOOLBOX_ENV_CONFIG=<config_name> setup_environment.py')
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

        # Extract version from root config BEFORE inheritance resolution.
        # The version field identifies THIS specific config file's version,
        # not a behavioral setting inherited from parent configs.
        config_version: str | None = None
        raw_version = config.get('version')
        if raw_version is not None:
            version_str = str(raw_version).strip()
            if version_str:
                config_version = version_str
                info(f'Configuration version: {config_version}')

        # Resolve configuration inheritance if present
        inheritance_chain: list[InheritanceChainEntry] = []
        if INHERIT_KEY in config:
            info('Configuration uses inheritance, resolving parent configs...')
            config, inheritance_chain = resolve_config_inheritance(
                config, config_source, auth_param=args.auth,
            )
            # Append current config as the last entry in the chain
            inheritance_chain.append(InheritanceChainEntry(
                source=config_source,
                source_type=classify_config_source(config_source),
                name=config.get('name', config_name),
            ))
            success('Configuration inheritance resolved successfully')
        else:
            inheritance_chain = [InheritanceChainEntry(
                source=config_source,
                source_type=classify_config_source(config_source),
                name=config.get('name', config_name),
            )]

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

        # Extract command-names
        command_names_raw = config.get('command-names')

        # Normalize to list
        command_names: list[str] | None = None
        if command_names_raw is not None:
            if isinstance(command_names_raw, str):
                command_names = [command_names_raw]
            elif isinstance(command_names_raw, list):
                # Convert all items to strings (handles mixed types from YAML)
                command_names = [str(item) for item in cast(list[object], command_names_raw)]
            else:
                error(f'Invalid command-names value: expected string or list, got {type(command_names_raw).__name__}')
                sys.exit(1)

        # Validate command names
        if command_names:
            for cmd_name in command_names:
                if not cmd_name.strip():
                    error('Invalid command name: empty or whitespace-only name')
                    sys.exit(1)
                if ' ' in cmd_name:
                    error(f'Invalid command name: "{cmd_name}" contains spaces')
                    sys.exit(1)
                # Validate path safety (rejects path separators, traversal, leading dots)
                if not validate_command_name_for_path(cmd_name):
                    error(f'Invalid command name for isolation: "{cmd_name}"')
                    error('Command names must contain only alphanumeric characters, hyphens, and underscores.')
                    error('Leading dots, path separators, and traversal patterns are not allowed.')
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
        env_variables: dict[str, str] | None = config.get('env-variables')

        # Extract OS-level environment variables configuration
        os_env_variables = config.get('os-env-variables')

        # Extract company_announcements configuration (still consumed by
        # the summary printout below; profile_config is rebuilt from `config`
        # directly via _YAML_TO_CAMEL_PROFILE_KEYS in Step 18).
        company_announcements = config.get('company-announcements')

        # Extract status_line configuration (still consumed by the summary
        # printout and by download_hook_files() path selection below).
        status_line = config.get('status-line')

        # Extract and validate effort_level configuration. When the value is
        # invalid, remove it from the config dict so that the profile_config
        # builder (which reads `config` via dict-membership) omits the key
        # from both the isolated config.json and the shared settings.json.
        effort_level = config.get('effort-level')
        if effort_level is not None:
            valid_effort_levels = ('low', 'medium', 'high', 'max')
            if effort_level not in valid_effort_levels:
                warning(
                    f'Invalid effort-level value: {effort_level!r}. '
                    f'Valid values: {", ".join(valid_effort_levels)}. Skipping.',
                )
                effort_level = None
                config.pop('effort-level', None)

        # Extract user-settings configuration (global user-level settings)
        user_settings = config.get('user-settings')

        # Extract global-config configuration (global Claude Code settings)
        global_config = config.get('global-config')

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

        # Set process env early to prevent CLI auto-install during installation
        if claude_code_version_normalized is not None:
            os.environ[IDE_SKIP_AUTO_INSTALL_KEY] = IDE_SKIP_AUTO_INSTALL_VALUE

        # Apply automatic auto-update settings based on version pinning
        (
            global_config,
            user_settings,
            env_variables,
            os_env_variables,
            auto_update_warnings,
            auto_injected_items,
        ) = apply_auto_update_settings(
            claude_code_version_normalized,
            global_config,
            user_settings,
            env_variables,
            os_env_variables,
        )
        for warn_msg in auto_update_warnings:
            warning(warn_msg)

        # Apply automatic IDE extension auto-install settings based on version pinning
        (
            global_config,
            user_settings,
            env_variables,
            os_env_variables,
            ide_ext_warnings,
            ide_ext_auto_injected,
        ) = apply_ide_extension_settings(
            claude_code_version_normalized,
            global_config,
            user_settings,
            env_variables,
            os_env_variables,
        )
        for warn_msg in ide_ext_warnings:
            warning(warn_msg)
        # Merge auto-injected items from both auto-update and IDE extension management
        auto_injected_items.extend(ide_ext_auto_injected)

        # Validate user-settings section for excluded keys
        if user_settings:
            user_settings_errors = validate_user_settings(user_settings)
            if user_settings_errors:
                for err in user_settings_errors:
                    error(err)
                sys.exit(1)

        # Validate global-config section for excluded keys
        if global_config:
            global_config_errors = validate_global_config(global_config)
            if global_config_errors:
                for err in global_config_errors:
                    error(err)
                sys.exit(1)

        # Detect conflicts between user-settings and root-level settings.
        # Warnings fire in BOTH modes (isolated and non-isolated). In non-
        # isolated mode, write_profile_settings_to_settings() also applies
        # root-level precedence for profile-owned keys via Step 14 / Step 18
        # ordering, so the conflict is meaningful in both branches.
        if user_settings:
            conflicts = detect_settings_conflicts(user_settings, config)
            for user_key, user_value, root_value in conflicts:
                warning(f"Key '{user_key}' specified in both root level and user-settings.")
                warning(f'  user-settings value: {user_value}')
                warning(f'  root-level value: {root_value}')
                warning(
                    '  Under deep merge semantics, root-level values overwrite '
                    'user-settings values for scalar keys. For dict keys, '
                    'user-settings and root-level values are deep-merged. '
                    'For ALL array-valued keys at any depth, array union with '
                    "structural dedupe applies (matching Claude Code CLI's "
                    'cross-scope merge: "arrays are concatenated and '
                    'deduplicated, not replaced").',
                )

        # Validate: profile-scoped MCP servers require command-names (launcher)
        # In non-command-names mode, profile-scoped servers have no launcher
        # to consume --mcp-config, so they would be silently dropped. This is
        # a hard error with 4-option actionable fix-up message.
        if not primary_command_name:
            mcp_servers_raw_for_validation = config.get('mcp-servers', [])
            if isinstance(mcp_servers_raw_for_validation, list):
                profile_mcp_names: list[str] = []
                for server in mcp_servers_raw_for_validation:
                    if not isinstance(server, dict):
                        continue
                    scope_raw = server.get('scope')
                    # scope may be str or list[str]; check for 'profile' membership
                    if isinstance(scope_raw, str):
                        scopes_set = {scope_raw}
                    elif isinstance(scope_raw, list):
                        scopes_set = {s for s in scope_raw if isinstance(s, str)}
                    else:
                        scopes_set = set()
                    if 'profile' in scopes_set:
                        server_name = server.get('name', '<unnamed>')
                        profile_mcp_names.append(str(server_name))
                if profile_mcp_names:
                    for server_name_out in profile_mcp_names:
                        error(
                            f"MCP server '{server_name_out}' declares scope: profile "
                            f'but command-names is not specified.',
                        )
                    error(
                        'Profile-scoped MCP servers require a launcher script '
                        'with --mcp-config flag, which is only created when '
                        'command-names is present in your YAML configuration.',
                    )
                    error('')
                    error('Fix one of:')
                    error('  1. Add "command-names: [your-name]" to enable isolated environment (preferred)')
                    error('  2. Change scope to "user" to install globally via ~/.claude.json')
                    error('  3. Change scope to "local" to install in project-specific .mcp.json')
                    error('  4. Change scope to "project" to install in shared project .mcp.json')
                    sys.exit(1)

        header(environment_name)

        # Create shared auth cache (validation phase populates, download phase reuses)
        auth_cache = AuthHeaderCache(args.auth)

        # Validate all downloadable files before proceeding
        print()
        print(f'{Colors.CYAN}Validating configuration files...{Colors.NC}')
        all_valid, validation_results = validate_all_config_files(config, config_source, args.auth, auth_cache)

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

        # Collect installation plan and confirm
        plan = collect_installation_plan(
            config=config,
            config_source=config_source,
            config_name=config_name,
            config_version=config_version,
            inheritance_chain=inheritance_chain,
            args=args,
        )
        plan.auto_injected_items = auto_injected_items

        auto_confirm = args.yes
        dry_run = args.dry_run

        # Confirmation gate
        confirmed = confirm_installation(
            plan=plan,
            auto_confirm=auto_confirm,
            dry_run=dry_run,
        )

        if not confirmed:
            if dry_run:
                sys.exit(0)
            # Interactive cancellation: exit 0 (user's deliberate choice)
            # Non-interactive refusal: exit 1 (missing prerequisite)
            if sys.stdin.isatty() or _dev_tty_available():
                sys.exit(0)
            sys.exit(1)

        # Set up directories
        home = get_real_user_home()
        claude_user_dir = home / '.claude'

        # Compute artifact base directory for environment isolation
        # When command-names is set, artifacts are isolated in ~/.claude/{primary_command_name}/
        # When not set, artifacts go to the standard ~/.claude/ directory
        isolated_config_dir: Path | None = None
        artifact_base_dir: Path

        if primary_command_name:
            # Check if user explicitly set CLAUDE_CONFIG_DIR in env-variables
            user_config_dir = env_variables.get('CLAUDE_CONFIG_DIR') if env_variables else None
            if user_config_dir:
                # User overrides isolation path -- use their value
                info('Using user-specified CLAUDE_CONFIG_DIR for artifact isolation')
                if user_config_dir.startswith('~'):
                    isolated_config_dir = Path(user_config_dir).expanduser()
                else:
                    isolated_config_dir = Path(user_config_dir)
                artifact_base_dir = isolated_config_dir
                # Remove CLAUDE_CONFIG_DIR from env_variables -- the launcher export
                # is the sole authoritative source. Keeping it in config.json env
                # section would create a redundant, potentially stale second source.
                if env_variables and 'CLAUDE_CONFIG_DIR' in env_variables:
                    env_variables.pop('CLAUDE_CONFIG_DIR')
            else:
                # Auto-compute isolation directory from primary command name
                isolated_config_dir = claude_user_dir / primary_command_name
                artifact_base_dir = isolated_config_dir
        else:
            artifact_base_dir = claude_user_dir

        # Derive all artifact directories from artifact_base_dir
        agents_dir = artifact_base_dir / 'agents'
        commands_dir = artifact_base_dir / 'commands'
        rules_dir = artifact_base_dir / 'rules'
        prompts_dir = artifact_base_dir / 'prompts'
        hooks_dir = artifact_base_dir / 'hooks'
        skills_dir = artifact_base_dir / 'skills'

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

        # Step 2: Install IDE extensions (version-pinned)
        if claude_code_version_normalized is not None and not args.skip_install:
            print()
            print(f'{Colors.CYAN}Step 2: Installing IDE extensions...{Colors.NC}')
            if not install_ide_extensions(claude_code_version_normalized):
                warning('IDE extension installation failed (non-fatal)')
        else:
            print()
            if claude_code_version_normalized is None:
                print(f'{Colors.CYAN}Step 2: Skipping IDE extensions (no version pinned){Colors.NC}')
            else:
                print(f'{Colors.CYAN}Step 2: Skipping IDE extensions (skip-install mode){Colors.NC}')

        # Step 3: Create base configuration directory
        print()
        print(f'{Colors.CYAN}Step 3: Creating base configuration directory...{Colors.NC}')
        claude_user_dir.mkdir(parents=True, exist_ok=True)
        success(f'Created: {claude_user_dir}')
        if artifact_base_dir != claude_user_dir:
            artifact_base_dir.mkdir(parents=True, exist_ok=True)
            success(f'Created: {artifact_base_dir}')
        # Subdirectories (agents, commands, rules, prompts, hooks, skills)
        # are created on-demand by their respective processing functions
        # only when files are actually placed into them.

        # Ensure .local/bin is in PATH early to prevent uv tool warnings
        ensure_local_bin_in_path()

        # Track download failures across all steps for final error reporting
        download_failures: list[str] = []

        # Step 4: Download/copy custom files
        print()
        print(f'{Colors.CYAN}Step 4: Processing file downloads...{Colors.NC}')
        files_to_download = config.get('files-to-download', [])
        if files_to_download:
            if not process_file_downloads(files_to_download, config_source, base_url, args.auth, auth_cache):
                download_failures.append('file downloads')
        else:
            info('No custom files to download')

        # Step 5: Install Node.js if requested (before dependencies)
        print()
        print(f'{Colors.CYAN}Step 5: Checking Node.js installation...{Colors.NC}')
        if not install_nodejs_if_requested(config):
            raise Exception('Node.js installation failed')

        # Step 6: Install dependencies (after Claude Code which provides tools)
        print()
        print(f'{Colors.CYAN}Step 6: Installing dependencies...{Colors.NC}')
        dependencies = config.get('dependencies', {})
        install_dependencies(dependencies)

        # Step 7: Set OS environment variables
        print()
        print(f'{Colors.CYAN}Step 7: Setting OS environment variables...{Colors.NC}')
        if os_env_variables:
            set_all_os_env_variables(os_env_variables)
        else:
            info('No OS environment variables to configure')

        # Generate env loader files for OS environment variables
        generated_env_files: dict[str, Path] = {}
        if os_env_variables:
            generated_env_files = generate_env_loader_files(
                os_env_variables, command_names, artifact_base_dir if command_names else None,
            )
            if generated_env_files:
                success(f'Generated {len(generated_env_files)} env loader file(s)')

        # Step 8: Process agents
        print()
        print(f'{Colors.CYAN}Step 8: Processing agents...{Colors.NC}')
        agents = config.get('agents', [])
        if agents:
            if not process_resources(agents, agents_dir, 'agents', config_source, base_url, args.auth, auth_cache):
                download_failures.append('agents')
        else:
            info('No agents to process')

        # Step 9: Process slash commands
        print()
        print(f'{Colors.CYAN}Step 9: Processing slash commands...{Colors.NC}')
        commands = config.get('slash-commands', [])
        if commands:
            if not process_resources(commands, commands_dir, 'slash commands', config_source, base_url, args.auth, auth_cache):
                download_failures.append('slash commands')
        else:
            info('No slash commands to process')

        # Step 10: Process rules
        print()
        print(f'{Colors.CYAN}Step 10: Processing rules...{Colors.NC}')
        rules = config.get('rules', [])
        if rules:
            if not process_resources(rules, rules_dir, 'rules', config_source, base_url, args.auth, auth_cache):
                download_failures.append('rules')
        else:
            info('No rules to process')

        # Step 11: Process skills
        print()
        print(f'{Colors.CYAN}Step 11: Processing skills...{Colors.NC}')
        skills_raw = config.get('skills', [])
        # Convert to properly typed list using cast and list comprehension
        skills: list[dict[str, Any]] = (
            [cast(dict[str, Any], s) for s in cast(list[object], skills_raw) if isinstance(s, dict)]
            if isinstance(skills_raw, list)
            else []
        )
        if skills:
            if not process_skills(skills, skills_dir, config_source, args.auth, auth_cache):
                download_failures.append('skills')
        else:
            info('No skills configured')

        # Step 12: Process system prompt (if specified)
        print()
        print(f'{Colors.CYAN}Step 12: Processing system prompt...{Colors.NC}')
        prompt_path = None
        if system_prompt:
            # Strip query parameters from URL to get clean filename
            clean_prompt = system_prompt.split('?')[0] if '?' in system_prompt else system_prompt
            sys_prompt_filename = Path(clean_prompt).name
            prompt_path = prompts_dir / sys_prompt_filename
            if not handle_resource(system_prompt, prompt_path, config_source, base_url, args.auth, auth_cache=auth_cache):
                download_failures.append('system prompt')
        else:
            info('No additional system prompt configured')

        # Step 13: Configure MCP servers
        print()
        print(f'{Colors.CYAN}Step 13: Configuring MCP servers...{Colors.NC}')
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
            _command_starts_with_npx(str(server.get('command', '')))
            for server in mcp_servers
            if server.get('command')
        )

        nodejs_dir: str | None = None
        if needs_nodejs:
            nodejs_dir = verify_nodejs_available()
            if not nodejs_dir:
                warning('Node.js not available - npx-based MCP servers may fail')
                warning('Please ensure Node.js is installed and in PATH')
                # Don't fail hard, let user see the issue

        # Calculate profile MCP config path for profile-scoped servers
        profile_mcp_config_path: Path | None = None
        if primary_command_name:
            profile_mcp_config_path = artifact_base_dir / 'mcp.json'

        _, profile_servers, mcp_stats = configure_all_mcp_servers(
            mcp_servers, profile_mcp_config_path, nodejs_dir=nodejs_dir,
            artifact_base_dir=artifact_base_dir if primary_command_name else None,
        )
        has_profile_mcp_servers = len(profile_servers) > 0

        # Step 14: Write user settings
        print()
        print(f'{Colors.CYAN}Step 14: Writing user settings...{Colors.NC}')
        if user_settings:
            settings_target_dir = artifact_base_dir if primary_command_name else claude_user_dir
            if write_user_settings(user_settings, settings_target_dir):
                success('User settings configured successfully')
            else:
                warning('Failed to write user settings (non-fatal)')
        else:
            info('No user settings to configure')

        # Step 15: Write global config
        print()
        print(f'{Colors.CYAN}Step 15: Writing global config...{Colors.NC}')
        if global_config:
            if write_global_config(
                global_config,
                artifact_base_dir=artifact_base_dir if primary_command_name else None,
            ):
                success('Global config written successfully')
            else:
                warning('Failed to write global config (non-fatal)')
        else:
            info('No global config to write')

        # Step 16: Cleanup stale auto-update and IDE extension controls
        _run_stale_controls_cleanup(claude_code_version_normalized)

        # Check if command creation is needed
        if primary_command_name:
            # Step 17: Download hooks
            print()
            print(f'{Colors.CYAN}Step 17: Downloading hooks...{Colors.NC}')
            hooks = config.get('hooks', {})
            hooks_base_dir_arg = hooks_dir if isolated_config_dir else None
            if not download_hook_files(hooks, claude_user_dir, config_source, base_url, args.auth,
                                       hooks_base_dir=hooks_base_dir_arg, auth_cache=auth_cache):
                download_failures.append('hook files')

            # Step 18: Create profile configuration
            print()
            print(f'{Colors.CYAN}Step 18: Creating profile configuration...{Colors.NC}')

            # Build profile_config dict from YAML using dict membership to
            # preserve the "declared-vs-absent" distinction end-to-end. In
            # isolated mode the distinction is cosmetic (atomic overwrite),
            # but the uniform construction pattern keeps the two branches
            # aligned and makes the null-as-delete semantics explicit in
            # the data flow.
            profile_config_isolated: dict[str, Any] = {
                camel_key: config[yaml_key]
                for yaml_key, camel_key in _YAML_TO_CAMEL_PROFILE_KEYS.items()
                if yaml_key in config
            }

            create_profile_config(
                profile_config_isolated,
                artifact_base_dir,
                hooks_base_dir=hooks_base_dir_arg,
            )

            # Step 19: Write installation manifest
            print()
            print(f'{Colors.CYAN}Step 19: Writing installation manifest...{Colors.NC}')
            cleanup_stale_marker(artifact_base_dir)
            config_source_type = classify_config_source(config_source)
            config_source_url = resolve_config_source_url(config_source, config_source_type)
            write_manifest(
                config_base_dir=artifact_base_dir,
                command_name=primary_command_name,
                config_version=config_version,
                config_source=config_name,
                config_source_type=config_source_type,
                config_source_url=config_source_url,
                command_names=command_names or [primary_command_name],
            )

            # Step 20: Create launcher script
            print()
            print(f'{Colors.CYAN}Step 20: Creating launcher script...{Colors.NC}')
            # Strip query parameters from system prompt filename (must match download logic)
            prompt_filename: str | None = None
            if system_prompt:
                clean_prompt = system_prompt.split('?')[0] if '?' in system_prompt else system_prompt
                prompt_filename = Path(clean_prompt).name
            launcher_result = create_launcher_script(
                artifact_base_dir, primary_command_name, prompt_filename, mode, has_profile_mcp_servers,
            )

            # Step 21: Register global command(s)
            if launcher_result:
                main_launcher, launch_script = launcher_result
                print()
                if additional_command_names:
                    all_names = ', '.join(command_names) if command_names else primary_command_name
                    print(f'{Colors.CYAN}Step 21: Registering global commands: {all_names}...{Colors.NC}')
                else:
                    print(f'{Colors.CYAN}Step 21: Registering global {primary_command_name} command...{Colors.NC}')
                register_global_command(
                    main_launcher, primary_command_name, additional_command_names,
                    launch_script_path=launch_script,
                )
            else:
                warning('Launcher script was not created')
        else:
            # No command-names: route all profile-owned YAML keys to the
            # shared ~/.claude/settings.json via deep-merge with RFC 7396
            # null-as-delete. This achieves full feature parity for model,
            # permissions, env, attribution, alwaysThinkingEnabled,
            # effortLevel, companyAnnouncements, statusLine, and hooks
            # between command-names present/absent modes.
            hooks = config.get('hooks', {})

            # Warn about command-defaults.system-prompt without command-names.
            # System prompts are applied by the launcher via --system-prompt /
            # --append-system-prompt CLI flags; without command-names there is
            # no launcher to consume the prompt file, so it would be silently
            # unused at runtime.
            if system_prompt:
                warning(
                    f"command-defaults.system-prompt is set to '{system_prompt}' "
                    f'but command-names is not specified.',
                )
                warning(
                    'System prompts are applied by the launcher; without command-names '
                    'there is no launcher, so the system prompt will NOT be applied.',
                )
                warning(
                    "Add 'command-names: [your-name]' to enable isolated environment "
                    'with launcher-based system prompt injection.',
                )

            # Step 17: Download hooks (and status-line file + config) to
            # ~/.claude/hooks/. The status-line file and its config must be
            # listed in hooks.files per the EnvironmentConfig schema Rule 3,
            # so download_hook_files() handles both automatically.
            has_hook_events = bool(hooks and hooks.get('events'))
            has_status_line_file = bool(
                status_line
                and isinstance(status_line, dict)
                and status_line.get('file'),
            )
            hook_files_list = hooks.get('files') if isinstance(hooks, dict) else None
            has_hook_files = bool(hook_files_list)

            if has_hook_events or has_status_line_file or has_hook_files:
                print()
                print(f'{Colors.CYAN}Step 17: Downloading hooks...{Colors.NC}')
                if not download_hook_files(hooks, claude_user_dir, config_source, base_url, args.auth,
                                           auth_cache=auth_cache):
                    download_failures.append('hook files')
            else:
                print()
                print(f'{Colors.CYAN}Step 17: Skipping hooks download (none configured)...{Colors.NC}')

            # Step 18: Deep-merge profile settings delta into the shared
            # settings.json. Unlike isolated mode (which uses atomic
            # overwrite of a toolbox-owned config.json), the shared
            # settings.json is a user-facing file that may contain keys
            # contributed by prior YAMLs, manual user edits, or the
            # Claude Code CLI itself, so the writer uses deep-merge with
            # RFC 7396 null-as-delete (via _write_merged_json()) to
            # preserve non-delta keys while allowing explicit YAML null
            # to remove keys.
            print()
            print(f'{Colors.CYAN}Step 18: Writing profile settings to settings.json...{Colors.NC}')

            # Build profile_config dict from YAML using dict membership to
            # preserve the "declared-vs-absent" distinction. A YAML-level
            # `key: null` declaration becomes `profile_config[camel_key] =
            # None`, which the builder forwards as `settings_delta[camel_key]
            # = None`, which in turn triggers RFC 7396 null-as-delete inside
            # _write_merged_json() against the shared settings.json.
            profile_config_shared: dict[str, Any] = {
                camel_key: config[yaml_key]
                for yaml_key, camel_key in _YAML_TO_CAMEL_PROFILE_KEYS.items()
                if yaml_key in config
            }

            # Build the profile settings delta (pure, no I/O)
            settings_delta = _build_profile_settings(profile_config_shared, hooks_dir)

            write_profile_settings_to_settings(settings_delta, claude_user_dir)

            # Steps 19-21: Skip command creation
            print()
            print(f'{Colors.CYAN}Steps 19-21: Skipping command creation (no command-names specified)...{Colors.NC}')
            info('Environment configuration completed successfully')
            info('To create custom commands, add "command-names: [name1, name2]" to your config')

        # Check for download failures and report accordingly
        if download_failures:
            print()
            print(f'{Colors.RED}========================================================================{Colors.NC}')
            print(f'{Colors.RED}              Setup Completed with Errors{Colors.NC}')
            print(f'{Colors.RED}========================================================================{Colors.NC}')
            print()
            error('The following resources failed to download:')
            for failure in download_failures:
                error(f'  - {failure}')
            print()
            error('Configuration steps were completed, but some files are missing.')
            error('Please check your network connection and authentication, then re-run the setup.')
            print()

            # If running elevated via UAC, add a pause so user can see the error
            if was_elevated_via_uac and not is_running_in_pytest():
                print()
                print(f'{Colors.RED}========================================================================{Colors.NC}')
                print(f'{Colors.RED}     Setup Completed with Download Errors{Colors.NC}')
                print(f'{Colors.RED}========================================================================{Colors.NC}')
                print()
                input('Press Enter to exit...')

            sys.exit(1)

        # Final message - success (no download failures)
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
        print(f'   * Rules: {len(rules)} installed')
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
        if mcp_stats['combined_count'] > 0:
            # Servers with BOTH global AND profile scope
            profile_only = mcp_stats['profile_count'] - mcp_stats['combined_count']
            if profile_only > 0:
                print(f"   * MCP servers: {mcp_stats['global_count']} global "
                      f"({mcp_stats['combined_count']} also in profile), "
                      f"{profile_only} profile-only")
            else:
                print(f"   * MCP servers: {mcp_stats['global_count']} global "
                      f"(all {mcp_stats['combined_count']} also in profile)")
        elif profile_servers:
            # Servers with ONLY profile scope (no global scope)
            print(f"   * MCP servers: {mcp_stats['global_count']} global, "
                  f"{mcp_stats['profile_count']} profile-only")
        else:
            print(f'   * MCP servers: {len(mcp_servers)} configured')
        if permissions:
            perm_items: list[str] = []
            if 'default-mode' in permissions:
                perm_items.append(f"default-mode={permissions['default-mode']}")
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
        if effort_level:
            print(f'   * Effort level: {effort_level}')
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
        if user_settings:
            print('   * User settings: configured in ~/.claude/settings.json')
        if global_config:
            print('   * Global config: configured in ~/.claude.json')
        if claude_code_version_normalized is not None:
            print(f'   * IDE extensions: {IDE_EXTENSION_ID} v{claude_code_version_normalized} (auto-install disabled)')
        # Show hooks count with routing information
        hooks = config.get('hooks', {})
        hook_event_count = len(hooks.get('events', [])) if hooks else 0
        if command_names:
            print(f'   * Hooks: {hook_event_count} configured (in config.json)')
            if len(command_names) > 1:
                print(f'   * Global commands: {", ".join(command_names)} registered')
            else:
                print(f'   * Global command: {primary_command_name} registered')
        else:
            if hook_event_count > 0:
                print(f'   * Hooks: {hook_event_count} configured (in settings.json)')
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

        # Environment guidance based on what was configured
        if os_env_variables:
            active_env_count = sum(1 for v in os_env_variables.values() if v is not None)
            if active_env_count > 0:
                if command_names:
                    print(f'   * Environment: Commands auto-load {active_env_count} OS env var(s)')
                else:
                    print(f'   * Environment: {active_env_count} OS env var(s) configured')
                    print('     Open a new terminal for automatic loading')

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

        # Post-install notes from configuration author
        post_install_notes = config.get('post-install-notes')
        if post_install_notes and isinstance(post_install_notes, str) and post_install_notes.strip():
            print(f'{Colors.YELLOW}Notes from the configuration author:{Colors.NC}')
            for line in post_install_notes.splitlines():
                print(f'  {line}')
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
