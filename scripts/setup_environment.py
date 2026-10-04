"""
Cross-platform environment setup for Claude Code.
Downloads and configures development tools for Claude Code based on YAML configuration.
"""

# /// script
# dependencies = [
#   "pyyaml",
#   "questionary",
# ]
# ///

import argparse
import concurrent.futures
import contextlib
import glob as glob_module
import gzip
import hashlib
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
import zipfile
import zlib
from collections.abc import Callable
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass
from dataclasses import field
from datetime import UTC
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Literal
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
    'components',
    'global-config',
    'user-settings',
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
    'hooks.helpers',                 # list[str] -- nested under hooks dict
    'files-to-download',             # list[dict] -- each dict has 'source' key
    'skills',                        # list[dict] -- each dict has 'base' key
    'command-defaults.system-prompt',  # str -- nested scalar under command-defaults
})

# Node.js installation constants (standalone -- no imports from install_claude.py)
MIN_NODE_VERSION = '18.0.0'
NODE_LTS_API = 'https://nodejs.org/dist/index.json'

# All valid top-level configuration keys for unknown key detection.
# Claude Code settings.json content is declared via 'user-settings' and
# ~/.claude.json content via 'global-config'; only keys that require
# toolbox-side processing (status-line, hooks, os-env-variables) or that
# drive the setup process itself live at the YAML root level.
KNOWN_CONFIG_KEYS: frozenset[str] = frozenset({
    'name',
    'version',
    'inherit',
    'merge-keys',
    'command-names',
    'base-url',
    'claude-code-version',
    'install-nodejs',
    'link-dirs',
    'link-from',
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
    'components',
    'post-install-notes',
    'os-env-variables',
    'command-defaults',
    'user-settings',
    'status-line',
})

# Sections whose items may be claimed by entries in the top-level
# `components:` registry. Any other key inside a component's `includes`
# mapping is rejected. Inline copy of SELECTABLE_SECTIONS in
# scripts/models/environment_config.py (standalone script policy prevents
# cross-import); parity enforced by
# tests/scripts/models/test_selectable_sections_parity.py.
SELECTABLE_SECTIONS: frozenset[str] = frozenset({
    'agents',
    'slash-commands',
    'rules',
    'skills',
    'files-to-download',
    'mcp-servers',
    'dependencies',
    'hooks',
})

# Component names reserved as --select sentinels ('--select all' selects
# every component, '--select none' selects no component)
RESERVED_COMPONENT_NAMES: frozenset[str] = frozenset({'all', 'none'})

# Component names: lowercase letters, digits, dots, underscores, hyphens;
# must start with a letter or digit
COMPONENT_NAME_PATTERN: re.Pattern[str] = re.compile(r'^[a-z0-9][a-z0-9._-]*$')

# Command names no profile may take, compared without regard to case: none,
# base and all are reserved words of the profile interface, and the rest are
# entries of a Claude Code configuration directory, so a profile named after
# one would install into that entry of the base ~/.claude. Inline copy of
# RESERVED_COMMAND_NAMES in scripts/models/environment_config.py (standalone
# script policy prevents cross-import); parity enforced by
# tests/scripts/models/test_reserved_command_names_parity.py.
RESERVED_COMMAND_NAMES: frozenset[str] = frozenset({
    'none',
    'base',
    'all',
    'skills',
    'agents',
    'commands',
    'rules',
    'hooks',
    'output-styles',
    'prompts',
    'projects',
})

# The entries of a Claude Code configuration home an isolated profile can take
# through a directory link from another profile, in display order. Every entry
# but projects holds installed content; projects holds sessions and auto-memory.
# Inline copy of LINKABLE_PROFILE_DIRS in scripts/models/environment_config.py
# (standalone script policy prevents cross-import); parity enforced by
# tests/scripts/models/test_linkable_profile_dirs_parity.py.
LINKABLE_PROFILE_DIRS: tuple[str, ...] = (
    'skills',
    'agents',
    'commands',
    'rules',
    'hooks',
    'output-styles',
    'prompts',
    'projects',
)

# The linkable entry that holds sessions and auto-memory rather than installed
# content; it links to any source, needs no manifest there, and leaves the
# component selection to the profile
SESSIONS_PROFILE_DIR = 'projects'
SKILLS_PROFILE_DIR = 'skills'

# The linkable entries that hold installed content; they link only between
# installs of one configuration, and a profile that links one takes its
# configuration and component selection from the source
CONTENT_PROFILE_DIRS: tuple[str, ...] = tuple(
    entry for entry in LINKABLE_PROFILE_DIRS if entry != SESSIONS_PROFILE_DIR
)

# The link-dirs values that stand for every linkable entry and for none
LINK_ALL_TOKEN = 'all'
LINK_NONE_TOKEN = 'none'

# The link-from value that names the base profile ~/.claude, and its default
LINK_SOURCE_BASE = 'base'

# Hook event names recognized by Claude Code 2.1.238; Claude Code rejects any
# other name at configuration load time. _build_hooks_json() warns (rather
# than errors) on names outside this set so a configuration written for a
# newer Claude Code release keeps installing. Inline copy of
# HOOK_EVENT_NAMES in scripts/models/environment_config.py (standalone
# script policy prevents cross-import); parity enforced by
# tests/scripts/models/test_hook_event_names_parity.py.
HOOK_EVENT_NAMES: frozenset[str] = frozenset({
    'ConfigChange',
    'CwdChanged',
    'DirectoryAdded',
    'Elicitation',
    'ElicitationResult',
    'FileChanged',
    'InstructionsLoaded',
    'MessageDisplay',
    'Notification',
    'PermissionDenied',
    'PermissionRequest',
    'PostCompact',
    'PostToolBatch',
    'PostToolUse',
    'PostToolUseFailure',
    'PreCompact',
    'PreToolUse',
    'SessionEnd',
    'SessionStart',
    'Setup',
    'Stop',
    'StopFailure',
    'SubagentStart',
    'SubagentStop',
    'TaskCompleted',
    'TaskCreated',
    'TeammateIdle',
    'UserPromptExpansion',
    'UserPromptSubmit',
    'WorktreeCreate',
    'WorktreeRemove',
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
# Used by collect_installation_plan(), install_dependencies(), and admin_elevation_reasons()
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

# Per-path union whitelist used ONLY by the YAML inheritance layer:
# _merge_config_key() composes a child's user-settings onto its parent's
# with these arrays unioned and every other array replaced by the child's
# (global-config composes with an empty whitelist, so every one of its
# arrays is replaced). The on-disk merge writers (write_user_settings(),
# write_profile_settings_to_settings(), write_global_config()) go through
# _write_merged_json(), which unions every array at every depth with the
# array the target file already holds, matching Claude Code CLI's
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

# The .claude.json keys that identify the account a profile is signed in
# with. A global-config null for one of them signs that account out of the
# profile whose .claude.json the run writes, so the installation summary
# warns before consent whenever the target file holds a value for it.
GLOBAL_CONFIG_ACCOUNT_KEYS: tuple[str, ...] = ('oauthAccount', 'userID')

# Model family markers whose presence (case-insensitive substring) in the model
# identifier indicates support for the extended effort levels: 'xhigh' is
# supported on Opus 4.7/4.8 and Fable 5; 'max' on Opus 4.6+, Sonnet 4.6+, and
# Fable 5. Substring matching covers aliases ('opus', 'fable'), full model IDs
# ('claude-fable-5'), and provider-prefixed IDs ('us.anthropic.claude-opus-4-8').
# Intentionally identical to scripts/models/environment_config.py (parity-tested).
XHIGH_EFFORT_MODEL_MARKERS: tuple[str, ...] = ('opus', 'fable')
MAX_EFFORT_MODEL_MARKERS: tuple[str, ...] = ('opus', 'fable', 'sonnet')

# Valid values for the settings.json effortLevel key
EFFORT_LEVEL_VALUES: frozenset[str] = frozenset({'low', 'medium', 'high', 'xhigh', 'max'})

# Valid values for the settings.json permissions.defaultMode key.
# 'delegate' appears in the published JSON schema but not in the prose
# documentation; it is accepted to avoid rejecting valid configurations.
PERMISSIONS_DEFAULT_MODE_VALUES: frozenset[str] = frozenset({
    'default',
    'acceptEdits',
    'plan',
    'auto',
    'dontAsk',
    'bypassPermissions',
    'delegate',
})

# user-settings is raw settings.json content and uses camelCase keys.
# These kebab-case spellings are common mistakes carried over from the
# root-level YAML naming convention; each maps to its camelCase correction.
USER_SETTINGS_KEBAB_KEY_CORRECTIONS: dict[str, str] = {
    'always-thinking-enabled': 'alwaysThinkingEnabled',
    'company-announcements': 'companyAnnouncements',
    'effort-level': 'effortLevel',
    'env-variables': 'env',
}

# Nested permissions keys also use camelCase inside user-settings
PERMISSIONS_KEBAB_KEY_CORRECTIONS: dict[str, str] = {
    'default-mode': 'defaultMode',
    'additional-directories': 'additionalDirectories',
}

# Root-level YAML keys that are not settings.json keys and therefore
# never valid inside user-settings
USER_SETTINGS_ROOT_ONLY_KEYS: frozenset[str] = frozenset({
    'status-line',
    'os-env-variables',
})

# Keys that live in ~/.claude.json (global-config), not in settings.json;
# declaring them in user-settings would be a silent no-op at runtime
USER_SETTINGS_GLOBAL_ONLY_KEYS: frozenset[str] = frozenset({
    'autoUpdates',
    'installMethod',
    'autoConnectIde',
    'autoInstallIdeExtension',
    'externalEditorContext',
    'teammateDefaultModel',
    'oauthAccount',
})

# Keys that live in settings.json (user-settings), not in ~/.claude.json;
# declaring them in global-config would be a silent no-op at runtime
GLOBAL_CONFIG_SETTINGS_ONLY_KEYS: frozenset[str] = frozenset({
    'model',
    'permissions',
    'env',
    'attribution',
    'alwaysThinkingEnabled',
    'effortLevel',
    'companyAnnouncements',
    'statusLine',
    'hooks',
    'availableModels',
    'enforceAvailableModels',
})

# Environment variable names: letters, digits, underscores; no leading digit
ENV_VAR_NAME_PATTERN: re.Pattern[str] = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

# Keys that are owned and written by the profile-settings subsystem.
# These keys are extracted from YAML root level and routed via
# create_profile_config() (isolated mode -> config.json) or
# write_profile_settings_to_settings() (non-isolated mode -> settings.json).
# They require toolbox-side processing (file download, absolute-path command
# construction) and are therefore excluded from the free-form user-settings
# section (USER_SETTINGS_EXCLUDED_KEYS).
#
# Both writers are fed by the shared pure builder _build_profile_settings().
# Values below are the on-disk camelCase keys as they appear in
# settings.json / config.json.
#
# In non-isolated mode, write_profile_settings_to_settings() deep-merges the
# builder's delta into the shared ~/.claude/settings.json via
# _write_merged_json(), inheriting: deep-merge for nested dicts, array-union
# for every list at every depth, RFC 7396 null-as-delete for top-level and
# nested None values, and preservation for keys omitted from the delta.
PROFILE_OWNED_KEYS: frozenset[str] = frozenset({
    'statusLine',
    'hooks',
})

# Mapping from YAML root kebab-case key names to their on-disk camelCase
# equivalents for the profile-owned keys. Used by main() to build the
# profile_config dict passed to _build_profile_settings(): dict membership
# encodes the "declared-vs-absent" distinction (which is lost by
# config.get() alone), and a YAML-level `hooks: null` declaration passes
# through as `profile_config['hooks'] = None`, which the builder forwards
# to the writer so _write_merged_json() can apply RFC 7396 null-as-delete
# to the shared settings.json.
_YAML_TO_CAMEL_PROFILE_KEYS: dict[str, str] = {
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


# Default number of parallel workers; 2 keeps GitHub secondary rate limits at bay
DEFAULT_PARALLEL_WORKERS = 2


def _parallel_workers_from_env() -> int:
    """Resolve the worker count from CLAUDE_CODE_TOOLBOX_PARALLEL_WORKERS.

    Read at call time (not import time) so --env overrides applied in
    resolve_args take effect. An invalid value falls back to the default
    with a warning.

    Returns:
        The configured worker count, or DEFAULT_PARALLEL_WORKERS.
    """
    raw = os.environ.get('CLAUDE_CODE_TOOLBOX_PARALLEL_WORKERS')
    if not raw:
        return DEFAULT_PARALLEL_WORKERS
    try:
        return int(raw)
    except ValueError:
        warning(
            f"Invalid CLAUDE_CODE_TOOLBOX_PARALLEL_WORKERS value '{raw}'; "
            f'using {DEFAULT_PARALLEL_WORKERS}',
        )
        return DEFAULT_PARALLEL_WORKERS


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
    max_workers: int | None = None,
    stagger_delay: float = 0.0,
) -> list[R]:
    """Execute a function on items in parallel with error isolation.

    Processes items using ThreadPoolExecutor when parallel mode is enabled,
    or sequentially when CLAUDE_CODE_TOOLBOX_SEQUENTIAL_MODE=1.

    Args:
        items: List of items to process
        func: Function to apply to each item
        max_workers: Maximum number of parallel workers; None resolves
            CLAUDE_CODE_TOOLBOX_PARALLEL_WORKERS at call time (default: 2)
        stagger_delay: Delay in seconds between task submissions to prevent
            thundering herd on rate-limited APIs (default: 0.0)

    Returns:
        List of results in the same order as input items.
        If an item raises an exception, that exception is stored in the result list
        and re-raised after all items are processed.
    """
    import operator

    if max_workers is None:
        max_workers = _parallel_workers_from_env()

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
    max_workers: int | None = None,
    stagger_delay: float = 0.0,
) -> list[R]:
    """Execute a function on items in parallel with error handling.

    Unlike execute_parallel, this function catches exceptions and returns
    a default value for failed items, allowing partial success.

    Args:
        items: List of items to process
        func: Function to apply to each item
        default_on_error: Value to return for items that raise exceptions
        max_workers: Maximum number of parallel workers; None resolves
            CLAUDE_CODE_TOOLBOX_PARALLEL_WORKERS at call time (default: 2)
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


class EnvTwin(NamedTuple):
    """A CLAUDE_CODE_TOOLBOX_* environment variable that stands in for an argument.

    Attributes:
        variable: Environment variable name.
        dest: argparse destination the variable fills when the argument is
            absent.
        kind: 'switch' for a store_true flag that only the exact value '1'
            turns on; 'value' for a string argument that any non-empty value
            fills.
    """

    variable: str
    dest: str
    kind: Literal['switch', 'value']


# Every environment variable that stands in for a command-line argument. This
# table is the single source for the fallbacks resolve_args() applies and for
# the variables request_admin_elevation() forwards: the elevated process does
# not inherit the environment of the process that requested elevation.
ENV_TWINS: tuple[EnvTwin, ...] = (
    EnvTwin('CLAUDE_CODE_TOOLBOX_ENV_CONFIG', 'config', 'value'),
    EnvTwin('CLAUDE_CODE_TOOLBOX_CONFIRM_INSTALL', 'yes', 'switch'),
    EnvTwin('CLAUDE_CODE_TOOLBOX_DRY_RUN', 'dry_run', 'switch'),
    EnvTwin('CLAUDE_CODE_TOOLBOX_SKIP_INSTALL', 'skip_install', 'switch'),
    EnvTwin('CLAUDE_CODE_TOOLBOX_NO_ADMIN', 'no_admin', 'switch'),
    EnvTwin('CLAUDE_CODE_TOOLBOX_ENV_AUTH', 'auth', 'value'),
    EnvTwin('CLAUDE_CODE_TOOLBOX_SELECT', 'select', 'value'),
    EnvTwin('CLAUDE_CODE_TOOLBOX_WITH', 'with_', 'value'),
    EnvTwin('CLAUDE_CODE_TOOLBOX_WITHOUT', 'without', 'value'),
    EnvTwin('CLAUDE_CODE_TOOLBOX_COMMAND_NAMES', 'command_names', 'value'),
    EnvTwin('CLAUDE_CODE_TOOLBOX_PROFILE', 'profile', 'value'),
    EnvTwin('CLAUDE_CODE_TOOLBOX_SWITCH_CONFIG', 'switch_config', 'switch'),
    EnvTwin('CLAUDE_CODE_TOOLBOX_LINK_DIRS', 'link_dirs', 'value'),
    EnvTwin('CLAUDE_CODE_TOOLBOX_LINK_FROM', 'link_from', 'value'),
)

# Twins a child run started by --profile all keeps: the repository credential
# names nothing in the child's own arguments, while every other twin would
# change what the child installs
CHILD_RUN_INHERITED_TWINS: frozenset[str] = frozenset({'CLAUDE_CODE_TOOLBOX_ENV_AUTH'})

# Variables the elevated process needs that no argument stands in for: the
# repository credentials and the Claude Code version the installer pins.
UAC_FORWARDED_ENV_VARS: tuple[str, ...] = (
    'GITHUB_TOKEN',
    'GITLAB_TOKEN',
    'REPO_TOKEN',
    'CLAUDE_CODE_TOOLBOX_VERSION',
)


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


def _elevation_launch_args(module_name: str, argv0: str) -> list[str]:
    """Build the program-launch portion of the UAC relaunch command line.

    Direct invocations (the curl | bash bootstrap, ``uv run setup_environment.py``,
    ``python setup_environment.py``) leave ``argv0`` pointing at this file, so the
    elevated process can re-run that path directly. When this module runs from an
    installed package behind a console-script entry point, ``argv0`` is a launcher
    executable that ``python.exe`` cannot execute, so the relaunch goes through the
    package's CLI module with the ``setup`` subcommand instead.

    Args:
        module_name: The ``__name__`` of this module at the call site.
        argv0: The process's ``sys.argv[0]``.

    Returns:
        Program-launch arguments that precede the forwarded flags.
    """
    module_package = module_name.rpartition('.')[0]
    if module_package and Path(argv0).suffix.lower() != '.py':
        return ['-m', f'{module_package}.cli', 'setup']
    return [argv0]


def request_admin_elevation(script_args: list[str] | None = None) -> None:
    """Re-launch script with UAC elevation on Windows.

    Args:
        script_args: Optional list of arguments to pass to elevated script.
    """
    if platform.system() != 'Windows':
        return

    try:
        import ctypes

        # The elevated process does not inherit this environment, so every
        # argument twin and every credential travels as an --env-VAR=value
        # argument that restore_env_vars_from_args() puts back
        env_vars_to_pass: list[str] = []
        forwarded_env_vars = [twin.variable for twin in ENV_TWINS] + list(UAC_FORWARDED_ENV_VARS)

        for var_name in forwarded_env_vars:
            var_value = os.environ.get(var_name)
            if var_value:
                # Don't escape here - we'll handle escaping when building the params string
                env_vars_to_pass.append(f'--env-{var_name}={var_value}')

        # Build command line with the program launch, environment variables, then original arguments
        # Add special flag to indicate UAC elevation created a new window
        uac_flag = ['--elevated-via-uac']
        forwarded_args = script_args or sys.argv[1:]
        all_args = _elevation_launch_args(__name__, sys.argv[0]) + env_vars_to_pass + uac_flag + forwarded_args

        # subprocess.list2cmdline implements the MSVCRT/CommandLineToArgvW
        # quoting rules (backslash doubling before quotes and at the end of
        # a quoted token), so every argument -- including --env values with
        # trailing backslashes -- round-trips into the elevated process intact
        params = subprocess.list2cmdline(all_args)

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


def _hold_elevated_window(title: str, color: str, notes: tuple[str, ...] = ()) -> None:
    """Keep the window a UAC relaunch opened on screen until the user presses Enter.

    An elevated process runs in a console of its own that closes the moment
    the process exits, so the outcome is shown under a banner and the
    process waits for Enter. Under pytest the function returns at once.

    Args:
        title: The banner title.
        color: The banner color.
        notes: Lines printed below the banner.
    """
    if is_running_in_pytest():
        return
    print()
    print(f'{color}========================================================================{Colors.NC}')
    print(f'{color}     {title}{Colors.NC}')
    print(f'{color}========================================================================{Colors.NC}')
    print()
    for note in notes:
        print(f'{Colors.YELLOW}{note}{Colors.NC}')
    if notes:
        print()
    input('Press Enter to exit...')


def _is_global_npm_install(dep: str) -> bool:
    """Check if a dependency command is a global npm package installation.

    Global npm installs write to the npm global prefix, which may require
    elevated privileges (admin on Windows, sudo on Unix-like systems).

    Args:
        dep: Dependency command string from the configuration.

    Returns:
        True if the command installs an npm package globally.
    """
    return 'npm install -g' in dep


def _contains_shell_control_chars(command: str) -> bool:
    """Check if a command string contains shell control characters.

    Commands containing these characters can chain commands, redirect
    output, or expand variables, so they must never be re-executed with
    elevated privileges.

    Args:
        command: Shell command string to inspect.

    Returns:
        True if the command contains any shell control character.
    """
    return any(char in command for char in ';&|<>$`\n')


def admin_elevation_reasons(config: dict[str, Any], args: argparse.Namespace) -> list[str]:
    """List the operations of this run that need administrator rights on Windows.

    Args:
        config: Configuration dictionary.
        args: Command line arguments.

    Returns:
        One description per operation that needs elevation, in installation
        order; empty off Windows or when no operation needs it.
    """
    if platform.system() != 'Windows':
        return []

    reasons: list[str] = []
    if not args.skip_install:
        # Installing Node.js and Git typically requires admin on Windows
        reasons.append('Installing Claude Code (includes Node.js and Git)')

    dependencies = config.get('dependencies', {})
    if dependencies:
        # Current platform + common dependencies, in the order they install
        current_platform_key = PLATFORM_SYSTEM_TO_CONFIG_KEY.get(platform.system())
        platform_deps = dependencies.get(current_platform_key, []) if current_platform_key else []
        common_deps = dependencies.get('common', [])
        for dep in list(platform_deps) + list(common_deps):
            if 'winget' in dep and '--scope machine' in dep:
                reasons.append(f'System-wide installation: {dep}')
            elif _is_global_npm_install(dep):
                # Global npm installs may need admin depending on Node.js installation
                reasons.append(f'Global npm package: {dep}')

    return reasons


def request_admin_elevation_if_needed(config: dict[str, Any], args: argparse.Namespace) -> None:
    """Relaunch through UAC when this run needs administrator rights it lacks.

    This is the only place a run requests elevation: the installation steps
    run in whatever process reaches them. A dry run never relaunches: it lists
    what the real run would elevate for and returns, so the preview continues
    to the installation summary. ``--no-admin`` turns the check off for both
    kinds of run.

    Args:
        config: Configuration dictionary.
        args: Command line arguments.
    """
    if args.no_admin:
        return
    reasons = admin_elevation_reasons(config, args)
    if not reasons or is_admin():
        return

    if args.dry_run:
        print()
        info('Dry run: administrator elevation is not requested.')
        info('A real run requests administrator privileges for:')
        for reason in reasons:
            info(f'  - {reason}')
        print()
        return

    print()
    print(f'{Colors.YELLOW}========================================================================{Colors.NC}')
    print(f'{Colors.YELLOW}     Administrator Privileges Required{Colors.NC}')
    print(f'{Colors.YELLOW}========================================================================{Colors.NC}')
    print()
    info('This configuration requires administrator privileges for:')
    for reason in reasons:
        info(f'  - {reason}')
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


# ANSI color codes for pretty output


@dataclass(frozen=True)
class InheritanceChainEntry:
    """Single entry in the configuration inheritance chain."""

    source: str
    source_type: str  # 'url', 'local', 'repo'
    name: str


@dataclass
class ComponentSelection:
    """Resolved component selection state threaded into the installation plan.

    is_active is False when the configuration defines no components, in
    which case every other field is empty and no filtering occurs.
    """

    is_active: bool = False
    # Component names in registry order
    available: list[str] = field(default_factory=lambda: list[str]())
    # Display label per component name (falls back to the name itself)
    labels: dict[str, str] = field(default_factory=lambda: dict[str, str]())
    # Final selected names (after selectors and closures), registry order
    selected: list[str] = field(default_factory=lambda: list[str]())
    # Names added by the hard requires closure, mapped to their cause
    auto_included: dict[str, str] = field(default_factory=lambda: dict[str, str]())
    # Copy-pasteable --select flag reproducing this selection
    replay: str = ''
    # The --select, --with and --without values the selection came from (a
    # picker choice that changed the set is recorded in the same form), or
    # None when the author defaults applied
    delta: dict[str, str | None] | None = None
    # 'cli', 'env' or 'yaml' (the author defaults); for a remembered delta,
    # the origin the manifest recorded
    origin: str = 'yaml'
    # Whether the delta came from the profile's manifest
    remembered: bool = False
    # Component names the author selects by default, registry order
    defaults: list[str] = field(default_factory=lambda: list[str]())

    @property
    def skipped(self) -> list[str]:
        """Component names not selected, in registry order."""
        selected_set = set(self.selected)
        return [name for name in self.available if name not in selected_set]


class StaleControlCopy(NamedTuple):
    """Stale update controls found in a profile the running one does not own.

    Attributes:
        profile: Display name of the profile holding the controls ('base'
            for the base profile, the directory name for an isolated one).
        file: The settings.json or .claude.json holding them.
        keys: The control keys present in that file.
    """

    profile: str
    file: Path
    keys: tuple[str, ...]


class RerootedPath(NamedTuple):
    """One configuration value ConfigHomeReroot rewrote into the profile directory.

    Attributes:
        section: 'files-to-download', 'dependencies' or 'user-settings'.
        label: The dependency platform key or the settings key; empty for a
            destination.
        original: The value as the configuration spells it.
        rewritten: The value the run uses.
    """

    section: str
    label: str
    original: str
    rewritten: str


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
    hooks_helpers: list[str] = field(default_factory=lambda: list[str]())
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
    system_prompt: str | None = None
    system_prompt_mode: str = 'replace'
    # The resolved command-defaults section (empty when not declared)
    command_defaults: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    command_names: list[str] = field(default_factory=lambda: list[str]())
    # 'cli', 'env', 'yaml' or 'default' (see CommandNames); None without command names
    command_names_origin: str | None = None
    # Whether the command names came from the profile's manifest
    command_names_remembered: bool = False
    claude_code_version: str | None = None
    # What this run's version pin does to the binary other profiles use
    pin_effect: str | None = None
    install_nodejs: bool = False
    skip_install: bool = False
    keep_installed_claude: bool = False
    claude_install_reason: str | None = None
    claude_install_warning: str | None = None
    os_env_variables: dict[str, Any] | None = None
    user_settings: dict[str, Any] | None = None
    global_config: dict[str, Any] | None = None
    status_line: dict[str, Any] | None = None

    # Security analysis
    unknown_keys: list[str] = field(default_factory=lambda: list[str]())
    sensitive_paths: list[str] = field(default_factory=lambda: list[str]())

    # Auto-injected items (auto-update controls)
    auto_injected_items: list[str] = field(default_factory=lambda: list[str]())

    # Component selection (inactive when the config defines no components)
    component_selection: ComponentSelection | None = None

    # Removal plan for deselected components (empty lists when nothing is dropped)
    deselected_items: dict[str, list[Any]] | None = None

    # The links of an isolated run and what Step 3 does to them; None for a
    # base run
    link_spec: 'LinkSpec | None' = None
    link_plan: 'LinkPlan | None' = None
    # The entries the configuration's own link-dirs names, so the summary
    # can say that a typed, environment or remembered none sets them aside
    configured_link_dirs: list[str] | None = None
    # The profile whose resolved-config.yaml this run applies, when the run
    # links content; its component selection is the source's
    linked_from: str | None = None
    # The profiles that link content from this one, refreshed after the run
    dependents: list[str] = field(default_factory=lambda: list[str]())
    # files-to-download destinations inside a linked entry, each with the
    # entry: the source's run wrote them, so this run leaves them to the link
    linked_downloads: list[tuple[str, str]] = field(default_factory=lambda: list[tuple[str, str]]())

    # Writes of an isolated run that reach beyond its profile directory,
    # each named before consent
    machine_wide_writes: list[str] = field(default_factory=lambda: list[str]())

    # global-config deletions that sign an account out of the .claude.json
    # this run writes
    account_key_warnings: list[str] = field(default_factory=lambda: list[str]())

    # Stale update controls other installed profiles hold; listed, never edited
    stale_controls_elsewhere: list[StaleControlCopy] = field(
        default_factory=lambda: list[StaleControlCopy](),
    )

    # Destinations outside ~/.claude that a profile of another configuration
    # recorded from a different source
    destination_warnings: list[str] = field(default_factory=lambda: list[str]())

    # Base config-home paths an isolated run rewrote into its profile
    # directory, each marked [re-rooted] in the summary
    rerooted_paths: list[RerootedPath] = field(default_factory=lambda: list[RerootedPath]())

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
            + len(self.hooks_helpers)
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

    @property
    def command_defaults_isolated_only(self) -> bool:
        """Whether the run declares command-defaults that no launcher of it applies.

        Only the launcher of an isolated profile passes the system prompt to
        Claude Code, so in a run without command names the prompt file is
        installed but never reaches Claude Code.
        """
        return bool(self.command_defaults) and not self.command_names


# Printed by both installation summaries for a run whose command-defaults
# no launcher applies (InstallationPlan.command_defaults_isolated_only).
COMMAND_DEFAULTS_ISOLATED_ONLY_NOTE = (
    'command-defaults applies only to isolated installs, whose launcher passes the '
    'system prompt to Claude Code; this run has no command names'
)


def system_prompt_completion_line(mode: str, *, isolated: bool) -> str:
    """Render the system prompt row of the closing summary.

    Args:
        mode: The command-defaults mode, 'append' or 'replace'.
        isolated: Whether the run installs an isolated profile, whose
            launcher applies the system prompt.

    Returns:
        The row text, without its bullet.
    """
    if not isolated:
        return f'System prompt: not applied ({COMMAND_DEFAULTS_ISOLATED_ONLY_NOTE})'
    if mode == 'append':
        return 'System prompt: appending to default'
    return 'System prompt: replacing default'


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


def _prefer_windows_executable(cmd: str, resolved: str | None) -> str | None:
    """Prefer a launchable Windows wrapper over an extensionless shim.

    ``shutil.which()`` can resolve a command to the extensionless Unix shell
    shim that Node.js ships beside its Windows wrapper (for example the ``npm``
    script next to ``npm.cmd``). ``subprocess.run(..., shell=False)`` launches
    resolved paths through ``CreateProcess``, which cannot execute such a shim
    and fails with ``OSError`` ``[WinError 193] %1 is not a valid Win32
    application``. On Python builds before the gh-109590 fix (Windows
    ``shutil.which`` on CPython 3.12.0 and every 3.11-or-earlier release), the
    bare command name is probed ahead of the PATHEXT variants, so the shim
    wins. When ``resolved`` lacks an executable extension, fall back to the
    ``.exe``/``.cmd``/``.bat``/``.com`` sibling that Windows can launch.

    Args:
        cmd: The command name originally passed to ``shutil.which()``.
        resolved: The path ``shutil.which(cmd)`` returned (possibly ``None``).

    Returns:
        A launchable executable path when one is found, otherwise ``resolved``.
    """
    executable_suffixes = ('.exe', '.cmd', '.bat', '.com')
    if resolved and Path(resolved).suffix.lower() in executable_suffixes:
        return resolved
    # ``resolved`` is missing or a non-launchable shim. Probe each executable
    # extension explicitly: appending a PATHEXT extension makes shutil.which()
    # return the direct wrapper match on every Python version.
    for suffix in executable_suffixes:
        wrapper = shutil.which(cmd + suffix)
        if wrapper:
            return wrapper
    return resolved


def run_command(cmd: list[str], capture_output: bool = True, **kwargs: Any) -> subprocess.CompletedProcess[str]:
    """Run a command and return the result."""
    try:
        # On Windows, resolve the executable to a full path that CreateProcess
        # can launch. subprocess.run(shell=False) cannot run a command by bare
        # name, and shutil.which() may resolve npm/npx to the extensionless Unix
        # shim shipped beside the .cmd wrapper -- launching that shim raises
        # WinError 193. _prefer_windows_executable() returns the .cmd/.exe
        # wrapper instead so batch-based tools (npm, npx) run correctly.
        if sys.platform == 'win32' and cmd:
            resolved = _prefer_windows_executable(cmd[0], shutil.which(cmd[0]))
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
    except OSError as exc:
        # A non-launchable executable (e.g. WinError 193 from a stray shim) must
        # not abort the whole setup: report it as a failed command so callers
        # can continue and record the failure, mirroring the FileNotFoundError
        # handling above.
        return subprocess.CompletedProcess(cmd, 1, '', f'Failed to run {cmd[0]}: {exc}')


def _dev_tty_sudo_available() -> bool:
    """Check if sudo can acquire credentials via /dev/tty in non-interactive mode.

    When stdin is piped (e.g., curl | bash), sudo cannot prompt via stdin.
    However, if /dev/tty is available, sudo can be invoked with stdin
    redirected from /dev/tty to prompt the user directly on the terminal.

    Returns:
        True if /dev/tty is available and sudo can be used through it,
        False otherwise.
    """
    if sys.platform != 'win32':
        try:
            with open('/dev/tty'):
                return True
        except OSError:
            pass
    return False


def _run_with_sudo_fallback(
    cmd: list[str],
    *,
    capture_output: bool = True,
    timeout: int = 30,
    tty_timeout: int = 60,
) -> subprocess.CompletedProcess[str] | None:
    """Run a command with sudo, using a three-tier fallback strategy.

    Tier 1: Interactive mode (stdin is a TTY) -- sudo prompts directly.
    Tier 2: Cached credentials (sudo -n true succeeds) -- sudo without prompt.
    Tier 3: /dev/tty available -- sudo with stdin redirected from /dev/tty.

    If all tiers fail, returns None without running the command.

    Args:
        cmd: Command to execute with sudo prepended
             (e.g., ['npm', 'uninstall', '-g', 'pkg']).
        capture_output: Whether to capture stdout/stderr.
        timeout: Timeout in seconds for Tier 1 and Tier 2 attempts.
        tty_timeout: Timeout for Tier 3 (/dev/tty) attempt. Longer because
                     the user may need time to type their password.

    Returns:
        CompletedProcess if sudo was attempted (check returncode for success),
        None if no sudo mechanism was available.
    """
    if sys.platform != 'win32':
        sudo_cmd = ['sudo'] + cmd

        # Tier 1: Interactive mode -- user can enter password at stdin
        if sys.stdin.isatty():
            try:
                return subprocess.run(
                    sudo_cmd,
                    capture_output=capture_output,
                    encoding='utf-8',
                    errors='replace',
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired:
                warning(f'Sudo command timed out after {timeout} seconds')
                return None
            except FileNotFoundError:
                warning('sudo command not found')
                return None

        # Tier 2: Non-interactive with cached credentials
        try:
            cred_check = subprocess.run(
                ['sudo', '-n', 'true'],
                capture_output=True,
                timeout=5,
            )
            if cred_check.returncode == 0:
                try:
                    return subprocess.run(
                        sudo_cmd,
                        capture_output=capture_output,
                        encoding='utf-8',
                        errors='replace',
                        timeout=timeout,
                    )
                except subprocess.TimeoutExpired:
                    warning(f'Sudo command timed out after {timeout} seconds')
                    return None
                except FileNotFoundError:
                    return None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Tier 3: /dev/tty available -- redirect sudo stdin from terminal
        if _dev_tty_sudo_available():
            info('Terminal available via /dev/tty - attempting sudo with terminal prompt...')
            try:
                with open('/dev/tty') as tty:
                    return subprocess.run(
                        sudo_cmd,
                        stdin=tty,
                        capture_output=capture_output,
                        encoding='utf-8',
                        errors='replace',
                        timeout=tty_timeout,
                    )
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                pass

    # Windows or all tiers exhausted
    return None


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
        if sys.platform == 'win32':
            # shutil.which() can resolve a command to the extensionless Unix
            # shim shipped beside its Windows wrapper (e.g. 'npm' next to
            # 'npm.cmd'); subprocess.run(shell=False) cannot launch that shim
            # and raises WinError 193. Prefer the executable wrapper instead.
            cmd_path = _prefer_windows_executable(cmd, cmd_path)
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


# A path naming the base config home or a ~/.claude.json sibling in any
# spelling: the home token (~, $HOME, ${HOME}, "$HOME", $env:USERPROFILE,
# %USERPROFILE%), a separator, .claude, then either a .json sibling suffix
# or a boundary. A sibling suffix accepts the shell globs a cleanup line
# spells (.claude.json.corrupted.*, .claude.json.backup.*), so the glob
# moves into the profile with the path. The lookbehind keeps a token glued
# to a preceding path or word (foo~/.claude, /x/$HOME) from matching; the
# lookahead keeps ~/.claude-backup and ~/.claudex out.
_CONFIG_HOME_PATTERN = re.compile(
    r'(?<![\w/\\.\-])'
    r'(?P<home>"\$HOME"|\$\{HOME\}|\$HOME|\$env:USERPROFILE|%USERPROFILE%|~)'
    r'(?P<sep>[\\/])\.claude'
    r'(?P<sibling>\.json(?:\.[\w*?-]+)*)?'
    r'(?![\w.\-])',
)
_PATH_COMPONENT_PATTERN = re.compile(r'[\\/]([^\\/\s"\']+)')


class ConfigHomeReroot:
    """Rewrite paths that name the base config home into an isolated run's profile directory.

    A configuration written for the base profile spells its files-to-download
    destinations, its dependency commands and its apiKeyHelper against
    ``~/.claude``. Installed as an isolated profile, every such path is
    rewritten to the same path inside the profile directory, keeping the
    author's home token and separator (``~/.claude/x`` becomes
    ``~/.claude/NAME/x``, ``$env:USERPROFILE\\.claude\\x`` becomes
    ``$env:USERPROFILE\\.claude\\NAME\\x``), so the shell and the tilde
    expansion that follow still resolve it. A profile directory below the
    home is spelled home-relative; one outside the home is spelled absolute.
    The ``~/.claude.json`` siblings (``~/.claude.json``, ``.backup``,
    ``.corrupted.*``) move into the profile directory too. A path that names
    an installed profile's directory or this run's own profile stays as
    written, which also makes the rewrite idempotent, and a path outside the
    config home is never touched. A base run builds no rerooter.
    """

    def __init__(self, profile_dir: Path, home_dir: Path, profile_names: Iterable[str]) -> None:
        """Bind the rewrite to a profile directory.

        Args:
            profile_dir: The directory the isolated run installs into.
            home_dir: The user's home directory.
            profile_names: This run's primary command name and the directory
                names of the installed isolated profiles, whose directories
                stay as written.
        """
        directory = Path(os.path.abspath(profile_dir))
        self._relative = _relative_inside(directory, Path(os.path.abspath(home_dir)))
        self._absolute_posix = directory.as_posix()
        self._absolute_windows = str(directory).replace('/', '\\')
        self._profile_names = {name.casefold() for name in profile_names}

    def rewrite(self, value: str) -> str:
        """Return the value with every config-home path moved into the profile directory.

        Args:
            value: A destination, a shell command or a settings value.

        Returns:
            The rewritten value, or the value itself when it names nothing
            inside the base config home.
        """
        return _CONFIG_HOME_PATTERN.sub(lambda match: self._replacement(match, value), value)

    def _replacement(self, match: re.Match[str], value: str) -> str:
        sep = match.group('sep')
        sibling = match.group('sibling')
        if sibling is None:
            component = _PATH_COMPONENT_PATTERN.match(value, match.end())
            if component is not None and component.group(1).casefold() in self._profile_names:
                return match.group(0)
        if self._relative is not None:
            profile = match.group('home') + sep + sep.join(self._relative.parts)
        else:
            profile = self._absolute_posix if sep == '/' else self._absolute_windows
        if sibling is None:
            return profile
        return f'{profile}{sep}.claude{sibling}'

    def apply(
        self,
        config: dict[str, Any],
        deselected: dict[str, list[Any]] | None = None,
    ) -> list[RerootedPath]:
        """Rewrite the resolved configuration in place.

        Rewrites every files-to-download destination, every dependency
        command of every platform list and every TILDE_EXPANSION_KEYS value
        of user-settings, and the destinations of the deselected
        files-to-download entries, so the removal plan resolves the same
        files the install wrote.

        Args:
            config: The resolved, component-selected configuration.
            deselected: The removal plan of collect_deselected_items(), or
                None.

        Returns:
            One record per rewritten configuration value, in configuration
            order; the removal plan contributes no record.
        """
        records: list[RerootedPath] = []
        self._rewrite_destinations(config.get('files-to-download'), records)
        dependencies = config.get('dependencies')
        if isinstance(dependencies, dict):
            for platform_key, commands in cast(dict[str, Any], dependencies).items():
                if not isinstance(commands, list):
                    continue
                command_list = cast(list[Any], commands)
                for index, command in enumerate(command_list):
                    if isinstance(command, str):
                        rewritten = self.rewrite(command)
                        if rewritten != command:
                            command_list[index] = rewritten
                            records.append(RerootedPath('dependencies', str(platform_key), command, rewritten))
        user_settings = config.get('user-settings')
        if isinstance(user_settings, dict):
            settings_dict = cast(dict[str, Any], user_settings)
            for key in sorted(TILDE_EXPANSION_KEYS):
                setting = settings_dict.get(key)
                if isinstance(setting, str):
                    rewritten = self.rewrite(setting)
                    if rewritten != setting:
                        settings_dict[key] = rewritten
                        records.append(RerootedPath('user-settings', key, setting, rewritten))
        if deselected is not None:
            self._rewrite_destinations(deselected.get('files-to-download'), None)
        return records

    def _rewrite_destinations(self, entries: object, records: list[RerootedPath] | None) -> None:
        if not isinstance(entries, list):
            return
        for entry in cast(list[object], entries):
            if not isinstance(entry, dict):
                continue
            entry_dict = cast(dict[str, Any], entry)
            dest = entry_dict.get('dest')
            if not isinstance(dest, str):
                continue
            rewritten = self.rewrite(dest)
            if rewritten != dest:
                entry_dict['dest'] = rewritten
                if records is not None:
                    records.append(RerootedPath('files-to-download', '', dest, rewritten))


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
    *,
    preserve_nulls: bool = False,
) -> None:
    """Recursively merge source into target in-place.

    Null handling (object members only; None elements inside arrays are
    data, never deletion signals) depends on which layer is merging:

    - preserve_nulls=False -- RFC 7396 JSON Merge Patch APPLICATION, used
      by every on-disk writer. A None source value removes the key from
      target (no-op if absent) and is never stored. A source dict that
      lands on a key target lacks, or whose target value is not a dict,
      is merged into a fresh empty dict exactly as the RFC prescribes, so
      None-valued members at any depth are dropped rather than copied
      into the file as literal JSON nulls.
    - preserve_nulls=True -- merge-patch COMPOSITION, used by the YAML
      inheritance layer. The result is itself a patch applied to disk
      later, so a None source value is stored as None (the child's
      deletion request survives composition whatever the parent
      declared) and a source dict landing on a key target lacks is
      copied verbatim, None members included.

    Array merge policy:
    - array_union_keys is None (default): every list is unioned with the
      existing list, preserving order-of-first-appearance and
      deduplicating elements via Python structural equality. This matches
      Claude Code's cross-scope merge semantics: "arrays are concatenated
      and deduplicated, not replaced".
    - array_union_keys is a set[str]: per-path whitelist -- only the
      dot-notation paths in the set are unioned; all other lists are
      replaced wholesale. This mode is preserved for the YAML inheritance
      layer (_merge_config_key -> deep_merge_settings) which has
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
        preserve_nulls: False applies the patch (None deletes and is never
            stored); True composes patches (None survives).
    """
    for key, value in source.items():
        # Build dot-notation path for this key
        key_path = f'{current_path}.{key}' if current_path else key

        if value is None:
            # RFC 7396: null signals deletion when applying; when
            # composing, the deletion request is carried forward.
            if preserve_nulls:
                target[key] = None
            else:
                target.pop(key, None)
        elif isinstance(value, dict):
            existing = target.get(key)
            if isinstance(existing, dict):
                # Both are dicts - recurse
                _merge_recursive(
                    existing,
                    value,
                    array_union_keys,
                    key_path,
                    preserve_nulls=preserve_nulls,
                )
            elif preserve_nulls:
                # Composition: the subtree is patch content, copied verbatim
                target[key] = _deep_copy_value(value)
            else:
                # RFC 7396: a missing or non-object target member is
                # replaced by an empty object before the patch recurses,
                # which strips None-valued members at every depth.
                fresh: dict[str, JsonValue] = {}
                _merge_recursive(fresh, value, array_union_keys, key_path)
                target[key] = fresh
        elif key not in target:
            # Key doesn't exist in target - add it (deep copy)
            target[key] = _deep_copy_value(value)
        elif isinstance(value, list) and isinstance(target[key], list):
            # Lists: union when array_union_keys is None (universal default)
            # or when key_path is in the explicit whitelist.
            should_union = (
                array_union_keys is None
                or key_path in array_union_keys
            )
            if should_union:
                existing_list = cast(list[JsonValue], target[key])
                new_items = value
                combined = existing_list + [
                    item for item in new_items if item not in existing_list
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
    *,
    preserve_nulls: bool = False,
) -> dict[str, Any]:
    """Deep merge updates into base dict with universal array-union.

    Performs recursive merging where nested dicts are merged (not
    replaced), arrays are unioned and deduplicated at every depth (by
    default), scalars are overwritten on conflict, and RFC 7396
    null-as-delete is honored.

    Key behaviors:
    - Keys NOT in updates: PRESERVED unchanged from base.
    - Keys IN updates: UPDATED or ADDED.
    - Keys with None value in updates: DELETED from result (RFC 7396)
      and never stored, at any depth -- a subtree that base does not
      hold is applied onto an empty object, so its None members are
      dropped too. With preserve_nulls=True the None is stored instead,
      which is what the YAML inheritance layer needs: the composed
      result is a patch applied later, and the deletion request must
      survive composition whatever base declared.
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
        preserve_nulls: False (default) applies updates as an RFC 7396
            merge patch. True composes two patches, carrying None values
            forward instead of deleting.

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

        >>> deep_merge_settings({}, {"env": {"TOKEN": None, "KEEP": "1"}})
        {'env': {'KEEP': '1'}}

        >>> deep_merge_settings({"env": {"TOKEN": "x"}}, {"env": {"TOKEN": None}}, preserve_nulls=True)
        {'env': {'TOKEN': None}}
    """
    # Create a fresh result dict (do not mutate base)
    result: dict[str, JsonValue] = {}

    # Start with all keys from base (deep copied)
    for key, value in base.items():
        result[key] = _deep_copy_value(cast(JsonValue, value))

    # Merge in updates. None means "union every array at every depth";
    # explicit set[str] restricts union to those paths (whitelist);
    # set() disables union entirely.
    _merge_recursive(
        result,
        cast(dict[str, JsonValue], updates),
        array_union_keys,
        '',
        preserve_nulls=preserve_nulls,
    )

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
    *,
    ensure_parent: bool = True,
) -> tuple[bool, dict[str, Any]]:
    """Read-merge-write JSON file with universal deep merge.

    Implements the three-step merge process:
    1. READ existing JSON file (or empty dict if not exists/invalid)
    2. DEEP MERGE new settings into existing via deep_merge_settings()
    3. WRITE merged result back to file

    Merge semantics:
    - Nested dicts: recursive deep merge.
    - Lists: every list at every depth is unioned with the list the file
      already holds -- existing elements first, new elements appended,
      duplicates dropped by structural equality (matches Claude Code
      CLI's cross-scope merge: "arrays are concatenated and
      deduplicated, not replaced"). A list in new_settings therefore
      never removes an element from the file.
    - Scalars: update wins.
    - None values: RFC 7396 null-as-delete (top-level and nested), so a
      None deletes a whole list.
    - Keys absent from new_settings: preserved unchanged in target.

    Args:
        target_file: Path to the JSON file to update.
        new_settings: New settings to deep-merge into existing content.
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
    merged = deep_merge_settings(existing, new_settings)

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

    Used in non-isolated mode only: when command-names is present, the
    user-settings section is built into the isolated profile's config.json
    via create_profile_config() instead.

    Args:
        settings: User settings dict from YAML user-settings section
        claude_user_dir: Path to ~/.claude directory

    Returns:
        True if settings were written successfully, False on write failure.
    """
    settings_file = claude_user_dir / 'settings.json'

    # Step 0: Platform-conditional tilde handling in command keys
    expanded_settings = _expand_tilde_keys_in_settings(settings)

    # Delegate to shared READ-MERGE-WRITE helper, which unions every list
    # with structural dedupe at every depth. This preserves contributions
    # from the Claude Code CLI, prior toolbox runs with other YAML
    # configs, manual user edits, and other writers. permissions.allow,
    # permissions.deny, permissions.ask, permissions.additionalDirectories,
    # companyAnnouncements, hooks.<EventName>, sandbox.filesystem.*,
    # disabledMcpjsonServers, and every other list-valued key compose
    # additively across runs.
    ok, merged = _write_merged_json(settings_file, expanded_settings)

    if ok:
        success(f'Wrote user settings to {settings_file}')
        _warn_wsl_windows_paths(merged)
    else:
        warning(f'Failed to write user settings to {settings_file}')

    return ok


def _validate_effort_level_entry(effort_level: object, model: object) -> list[str]:
    """Validate the user-settings effortLevel value and its model support.

    The 'xhigh' level requires an Opus or Fable model; 'max' requires an
    Opus, Sonnet, or Fable model. The exact alias 'best' (which resolves to
    Fable 5 or the latest Opus model) satisfies both. Claude Code gracefully
    downgrades an unsupported level at runtime, but declaring one in the
    profile is almost always a configuration mistake, so it is rejected.

    Args:
        effort_level: The declared effortLevel value (non-null).
        model: The declared user-settings model value, or None when absent.

    Returns:
        List of error messages. Empty list if the entry is valid.
    """
    if effort_level not in EFFORT_LEVEL_VALUES:
        return [
            f'user-settings.effortLevel must be one of '
            f'{sorted(EFFORT_LEVEL_VALUES)}, got {effort_level!r}.',
        ]

    if effort_level not in ('xhigh', 'max'):
        return []

    markers = XHIGH_EFFORT_MODEL_MARKERS if effort_level == 'xhigh' else MAX_EFFORT_MODEL_MARKERS
    families = 'Opus and Fable models' if effort_level == 'xhigh' else 'Opus, Sonnet, and Fable models'

    if not isinstance(model, str) or not model.strip():
        return [
            f"user-settings.effortLevel '{effort_level}' requires user-settings.model "
            f'to be specified. This effort level is only available for {families}.',
        ]

    model_lower = model.lower()
    # The 'best' alias is matched exactly, not as a substring, so arbitrary
    # model names that merely contain 'best' are not accepted.
    if model_lower != 'best' and not any(marker in model_lower for marker in markers):
        return [
            f"user-settings.effortLevel '{effort_level}' is only available for "
            f"{families}, but model is set to '{model}'. "
            "Use 'low', 'medium', or 'high' for other models.",
        ]

    return []


def _validate_permissions_entry(permissions: object) -> list[str]:
    """Validate the structure of the user-settings permissions value.

    Known sub-keys are checked (camelCase naming, defaultMode enum, list
    shapes); unknown sub-keys pass through untouched for forward
    compatibility with new Claude Code permissions options.

    Args:
        permissions: The declared permissions value (non-null).

    Returns:
        List of error messages. Empty list if the value is valid.
    """
    if not isinstance(permissions, dict):
        return ['user-settings.permissions must be a mapping.']

    errors: list[str] = []
    permissions_dict = cast(dict[str, Any], permissions)

    errors.extend(
        f"user-settings.permissions uses camelCase keys: use '{camel}' instead of '{kebab}'."
        for kebab, camel in PERMISSIONS_KEBAB_KEY_CORRECTIONS.items()
        if kebab in permissions_dict
    )

    default_mode = permissions_dict.get('defaultMode')
    if 'defaultMode' in permissions_dict and default_mode is not None and default_mode not in PERMISSIONS_DEFAULT_MODE_VALUES:
        errors.append(
            f'user-settings.permissions.defaultMode must be one of '
            f'{sorted(PERMISSIONS_DEFAULT_MODE_VALUES)}, got {default_mode!r}.',
        )

    for list_key in ('allow', 'deny', 'ask', 'additionalDirectories'):
        value = permissions_dict.get(list_key)
        if list_key in permissions_dict and value is not None:
            value_list = cast(list[Any], value) if isinstance(value, list) else None
            if value_list is None or any(not isinstance(item, str) for item in value_list):
                errors.append(f'user-settings.permissions.{list_key} must be a list of strings.')

    return errors


def _validate_env_entry(env: object) -> list[str]:
    """Validate the structure of the user-settings env value.

    settings.json requires env to be a mapping of string names to string
    values. A null entry value is a deletion request and carries no content
    to check.

    Args:
        env: The declared env value (non-null).

    Returns:
        List of error messages. Empty list if the value is valid.
    """
    if not isinstance(env, dict):
        return ['user-settings.env must be a mapping of environment variable names to string values.']

    errors: list[str] = []
    for name, value in cast(dict[Any, Any], env).items():
        if not isinstance(name, str) or not ENV_VAR_NAME_PATTERN.match(name):
            errors.append(
                f'user-settings.env: invalid environment variable name {name!r}. '
                'Must start with letter or underscore, followed by letters, digits, or underscores.',
            )
            continue
        if value is None:
            continue
        if not isinstance(value, str):
            errors.append(
                f'user-settings.env.{name} must be a string '
                '(quote the value in YAML) or null to delete the variable.',
            )
        elif '\x00' in value:
            errors.append(f'user-settings.env.{name} value cannot contain null bytes.')

    return errors


def validate_user_settings(user_settings: dict[str, Any]) -> list[str]:
    """Validate the user-settings section (excluded keys and known key values).

    user-settings is free-form raw settings.json content: unknown keys pass
    through untouched so new Claude Code settings work without a toolbox
    update. Known built-in keys, however, are validated fail-fast, because
    Claude Code silently ignores malformed or misplaced entries at runtime
    and the misconfiguration would otherwise go unnoticed. A null value for
    any key is a deletion request and is always allowed.

    Checks:
    - 'hooks' and 'statusLine' are excluded (profile-specific, configured
      via root-level YAML keys with dedicated download and path resolution).
    - Root-level YAML keys ('status-line', 'os-env-variables') are rejected.
    - Kebab-case spellings of known camelCase keys are rejected with the
      camelCase correction.
    - Keys that belong in global-config (~/.claude.json) are rejected.
    - Value shapes for model, env, permissions, attribution,
      alwaysThinkingEnabled, companyAnnouncements, and effortLevel
      (including the effortLevel/model support cross-check).

    Args:
        user_settings: Dict from YAML user-settings section.

    Returns:
        List of error messages. Empty list if validation passes.

    Examples:
        >>> validate_user_settings({'language': 'russian', 'model': 'claude-opus-4'})
        []

        >>> validate_user_settings({'hooks': {'events': []}})
        ["Key 'hooks' is not allowed in user-settings (profile-specific only)"]
    """
    errors: list[str] = [
        f"Key '{key}' is not allowed in user-settings (profile-specific only)"
        for key in user_settings
        if key in USER_SETTINGS_EXCLUDED_KEYS
    ]

    errors.extend(
        f"Key '{key}' is not allowed in user-settings. "
        'It is a root-level YAML key, not a settings.json key.'
        for key in sorted(USER_SETTINGS_ROOT_ONLY_KEYS & set(user_settings))
    )

    errors.extend(
        f"Key '{kebab}' is not a settings.json key. "
        f"user-settings holds raw settings.json content with camelCase keys: use '{camel}' instead."
        for kebab, camel in USER_SETTINGS_KEBAB_KEY_CORRECTIONS.items()
        if kebab in user_settings
    )

    errors.extend(
        f"Key '{key}' belongs in global-config (~/.claude.json), "
        'not in user-settings (settings.json).'
        for key in sorted(USER_SETTINGS_GLOBAL_ONLY_KEYS & set(user_settings))
    )

    model = user_settings.get('model')
    if 'model' in user_settings and model is not None and (not isinstance(model, str) or not model.strip()):
        errors.append('user-settings.model must be a non-empty string.')

    env = user_settings.get('env')
    if 'env' in user_settings and env is not None:
        errors.extend(_validate_env_entry(env))

    permissions = user_settings.get('permissions')
    if 'permissions' in user_settings and permissions is not None:
        errors.extend(_validate_permissions_entry(permissions))

    attribution = user_settings.get('attribution')
    if 'attribution' in user_settings and attribution is not None:
        if not isinstance(attribution, dict):
            errors.append('user-settings.attribution must be a mapping.')
        else:
            attribution_dict = cast(dict[str, Any], attribution)
            for sub in ('commit', 'pr'):
                value = attribution_dict.get(sub)
                if sub in attribution_dict and value is not None and not isinstance(value, str):
                    errors.append(
                        f'user-settings.attribution.{sub} must be a string '
                        '(empty string hides attribution).',
                    )

    always_thinking = user_settings.get('alwaysThinkingEnabled')
    if 'alwaysThinkingEnabled' in user_settings and always_thinking is not None and not isinstance(always_thinking, bool):
        errors.append('user-settings.alwaysThinkingEnabled must be a boolean.')

    announcements = user_settings.get('companyAnnouncements')
    if 'companyAnnouncements' in user_settings and announcements is not None:
        announcements_list = cast(list[Any], announcements) if isinstance(announcements, list) else None
        if announcements_list is None or any(not isinstance(item, str) for item in announcements_list):
            errors.append('user-settings.companyAnnouncements must be a list of strings.')

    effort_level = user_settings.get('effortLevel')
    if 'effortLevel' in user_settings and effort_level is not None:
        errors.extend(_validate_effort_level_entry(effort_level, model))

    return errors


def validate_global_config(global_config: dict[str, Any]) -> list[str]:
    """Validate the global-config section (excluded keys and key placement).

    global-config is free-form ~/.claude.json content: unknown keys pass
    through untouched. Non-null OAuth credential values are rejected (null
    values are allowed to support clearing authentication state), and known
    settings.json keys are rejected because ~/.claude.json is not a settings
    file and Claude Code would silently ignore them at runtime.

    Args:
        global_config: Dict from YAML global-config section.

    Returns:
        List of error messages. Empty list if validation passes.
    """
    errors: list[str] = [
        f"Key '{key}' cannot be set to a non-null value in global-config "
        '(OAuth credentials)'
        for key in global_config
        if key in GLOBAL_CONFIG_EXCLUDED_KEYS and global_config[key] is not None
    ]

    for key in sorted(GLOBAL_CONFIG_SETTINGS_ONLY_KEYS & set(global_config)):
        if key in ('statusLine', 'hooks'):
            root_key = 'status-line' if key == 'statusLine' else 'hooks'
            errors.append(
                f"Key '{key}' is not valid in global-config (~/.claude.json). "
                f"Configure it via the root-level '{root_key}' YAML key.",
            )
        else:
            errors.append(
                f"Key '{key}' is a settings.json key and is not valid in "
                'global-config (~/.claude.json). Move it to user-settings.',
            )

    return errors


def _component_item_keys(section: str, item: object) -> set[str]:
    """Compute the identity keys a component selector can match for one item.

    Mirrors each section's merge identity: the exact string for agents,
    slash-commands, rules, and dependencies; the entry name for skills and
    mcp-servers; and both the raw dest and the normalized final file path
    (via _files_download_identity) for files-to-download. Hook events and
    hook files are handled by _component_section_identities because hooks
    is a composite section. Keys are whitespace-stripped to match the
    Pydantic model's str_strip_whitespace behavior.

    Args:
        section: Selectable section name.
        item: One item from that section.

    Returns:
        Set of identity keys; empty when the item has no identity (such
        items are mandatory and never claimable).
    """
    if section in ('agents', 'slash-commands', 'rules', 'dependencies'):
        return {str(item).strip()}
    if section in ('skills', 'mcp-servers'):
        if isinstance(item, dict):
            name = cast(dict[str, Any], item).get('name')
            if name is not None:
                return {str(name).strip()}
        return set()
    if section == 'files-to-download':
        if not isinstance(item, dict):
            return set()
        entry = cast(dict[str, Any], item)
        keys: set[str] = set()
        dest = entry.get('dest')
        if dest is not None:
            keys.add(str(dest).strip())
        identity = _files_download_identity(entry)
        if identity:
            keys.add(identity.strip())
        return keys
    return set()


def _component_section_identities(config: dict[str, Any], section: str) -> set[str]:
    """Compute all claimable item identities for a selectable section.

    Args:
        config: Fully resolved configuration dictionary.
        section: Selectable section name.

    Returns:
        Set of identity strings component selectors may reference.
    """
    keys: set[str] = set()
    if section == 'hooks':
        hooks_raw = config.get('hooks')
        if isinstance(hooks_raw, dict):
            hooks_dict = cast(dict[str, Any], hooks_raw)
            keys.update(str(file_path).strip() for file_path in hooks_dict.get('files') or [])
            keys.update(
                str(cast(dict[str, Any], event)['id']).strip()
                for event in hooks_dict.get('events') or []
                if isinstance(event, dict) and cast(dict[str, Any], event).get('id') is not None
            )
        return keys
    if section == 'dependencies':
        deps_raw = config.get('dependencies')
        if isinstance(deps_raw, dict):
            for commands in cast(dict[str, Any], deps_raw).values():
                if isinstance(commands, list):
                    for command in cast(list[object], commands):
                        keys |= _component_item_keys(section, command)
        return keys
    section_raw = config.get(section)
    if isinstance(section_raw, list):
        for item in cast(list[object], section_raw):
            keys |= _component_item_keys(section, item)
    return keys


def _warn_hook_claim_asymmetry(
    config: dict[str, Any],
    components: list[dict[str, Any]],
) -> None:
    """Warn when claimed hooks files are not covered by their events' claims.

    A command hook event references its script by basename. When a hooks
    file is claimed by components that do not also cover every event
    referencing it, a selection can drop the file while a surviving event
    still needs it, breaking the hook at runtime. This is a soft warning,
    not an error, because the asymmetry can also be a deliberate author
    choice.

    Args:
        config: Fully resolved configuration dictionary.
        components: Component entries from the configuration.
    """
    hooks_raw = config.get('hooks')
    if not isinstance(hooks_raw, dict):
        return
    hooks_dict = cast(dict[str, Any], hooks_raw)
    files = [str(f).strip() for f in hooks_dict.get('files') or []]
    events = [
        cast(dict[str, Any], e)
        for e in hooks_dict.get('events') or []
        if isinstance(e, dict)
    ]
    if not files or not events:
        return

    file_claims: dict[str, set[str]] = {f: set() for f in files}
    event_claims: dict[str, set[str]] = {}
    for comp in components:
        comp_name = str(comp.get('name', '')).strip()
        includes_raw = comp.get('includes')
        if not isinstance(includes_raw, dict):
            continue
        selectors_raw = cast(dict[str, Any], includes_raw).get('hooks')
        if not isinstance(selectors_raw, list):
            continue
        selectors = {str(s).strip() for s in cast(list[object], selectors_raw)}
        for file_path in file_claims:
            if file_path in selectors:
                file_claims[file_path].add(comp_name)
        for event in events:
            event_id = event.get('id')
            if event_id is not None and str(event_id).strip() in selectors:
                event_claims.setdefault(str(event_id).strip(), set()).add(comp_name)

    status_line_refs: set[str] = set()
    status_line_raw = config.get('status-line')
    if isinstance(status_line_raw, dict):
        for ref_key in ('file', 'config'):
            ref = cast(dict[str, Any], status_line_raw).get(ref_key)
            if ref:
                status_line_refs.add(Path(str(ref).split('?')[0]).name)

    for file_path, file_claimers in file_claims.items():
        if not file_claimers:
            continue
        file_basename = Path(file_path.split('?')[0]).name
        if file_basename in status_line_refs:
            warning(
                f"hooks file '{file_path}' is claimed by component(s) "
                f'{sorted(file_claimers)} but the status line references it, and '
                f'status-line is not selectable; deselecting the file would break '
                f'the status line. Leave the file unclaimed (mandatory) instead.',
            )
        for event in events:
            if event.get('type', 'command') != 'command':
                continue
            # An event references a hooks file through its command (skipped
            # for compound command strings) and through its config file;
            # deselecting either file breaks the generated command line
            command = str(event.get('command') or '').split('?')[0]
            referenced = {Path(command).name} if command and ' ' not in command else set()
            config_file = str(event.get('config') or '').split('?')[0]
            if config_file:
                referenced.add(Path(config_file).name)
            if file_basename not in referenced:
                continue
            event_id = event.get('id')
            claimers = event_claims.get(str(event_id).strip(), set()) if event_id is not None else set()
            if not claimers or claimers - file_claimers:
                warning(
                    f"hooks file '{file_path}' is claimed by component(s) "
                    f'{sorted(file_claimers)} but a hook event referencing it is not '
                    f'covered by the same component(s); deselecting the file could '
                    f'break that event. Claim the file and its events together.',
                )


def validate_components(config: dict[str, Any]) -> list[str]:
    """Validate the components registry against the resolved configuration.

    Runtime twin of the Pydantic components validation in
    scripts/models/environment_config.py (standalone script policy prevents
    importing the model). Checks component entry shape, name format and
    reserved literals, includes keys against SELECTABLE_SECTIONS, selector
    resolution against the config's actual items, requires/bundles
    references, duplicate component names, and duplicate hook event ids
    (the id check runs even without components, matching the model). Emits
    a hook-claim asymmetry warning as a side effect; never raises.

    Args:
        config: Fully resolved configuration dictionary.

    Returns:
        List of error messages; empty when the registry is valid.
    """
    import difflib

    errors: list[str] = []

    hooks_raw = config.get('hooks')
    seen_ids: set[str] = set()
    if isinstance(hooks_raw, dict):
        for event in cast(dict[str, Any], hooks_raw).get('events') or []:
            if not isinstance(event, dict):
                continue
            event_id = cast(dict[str, Any], event).get('id')
            if event_id is None:
                continue
            if not isinstance(event_id, str):
                errors.append(f'hooks.events id {event_id!r} must be a string')
                continue
            id_str = event_id.strip()
            if id_str in seen_ids:
                errors.append(
                    f"Duplicate hook event id '{id_str}'. Hook ids must be unique across events.",
                )
            seen_ids.add(id_str)

    components_raw = config.get('components') or []
    if not isinstance(components_raw, list):
        errors.append("'components' must be a list of component entries")
        return errors

    allowed_fields = {'name', 'label', 'description', 'default', 'requires', 'bundles', 'includes'}
    component_entries: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for index, entry_raw in enumerate(cast(list[object], components_raw)):
        if not isinstance(entry_raw, dict):
            errors.append(f'components[{index}] must be a mapping')
            continue
        entry = cast(dict[str, Any], entry_raw)
        component_entries.append(entry)

        name_raw = entry.get('name')
        name = name_raw.strip() if isinstance(name_raw, str) else ''
        display = name or f'components[{index}]'
        if name_raw is not None and not isinstance(name_raw, str):
            errors.append(f'components[{index}]: name must be a string')
        elif not name:
            errors.append(f'components[{index}] requires a name')
        elif name in RESERVED_COMPONENT_NAMES:
            errors.append(
                f"Component name '{name}' is reserved (used as a --select sentinel). "
                f'Choose another name.',
            )
        elif not COMPONENT_NAME_PATTERN.match(name):
            errors.append(
                f"Component name '{name}' is invalid. Names must use lowercase letters, "
                f'digits, dots, underscores, and hyphens, and start with a letter or digit.',
            )
        if name:
            if name in seen_names:
                errors.append(
                    f"Duplicate component name '{name}'. Component names must be unique.",
                )
            seen_names.add(name)

        unknown_fields = sorted(set(entry) - allowed_fields)
        if unknown_fields:
            errors.append(f"Component '{display}': unknown field(s): {', '.join(unknown_fields)}")
        label_raw = entry.get('label')
        if label_raw is not None and not isinstance(label_raw, str):
            errors.append(f"Component '{display}': label must be a string")
        description_raw = entry.get('description')
        if description_raw is not None and not isinstance(description_raw, str):
            errors.append(f"Component '{display}': description must be a string")
        # Key-presence (not None-ness) distinguishes an omitted default
        # (allowed, means true) from an explicit bare 'default:' (rejected,
        # matching the model; a tolerated null would silently read as
        # not-default at resolution time)
        if 'default' in entry and not isinstance(entry.get('default'), bool):
            errors.append(f"Component '{display}': default must be a boolean")

        includes_raw = entry.get('includes')
        if not isinstance(includes_raw, dict) or not includes_raw:
            errors.append(
                f"Component '{display}': includes must claim at least one item. "
                f'Selectable sections: {sorted(SELECTABLE_SECTIONS)}',
            )
            continue
        for section, selectors in cast(dict[str, Any], includes_raw).items():
            if section not in SELECTABLE_SECTIONS:
                close = difflib.get_close_matches(
                    str(section), sorted(SELECTABLE_SECTIONS), n=1, cutoff=0.6,
                )
                hint = f' (did you mean {close[0]!r}?)' if close else ''
                errors.append(
                    f"Component '{display}': includes key '{section}' is not selectable{hint}. "
                    f'Selectable sections: {sorted(SELECTABLE_SECTIONS)}',
                )
                continue
            if not isinstance(selectors, list) or not selectors:
                errors.append(
                    f"Component '{display}': includes.{section} must list at least one selector",
                )
                continue
            available = _component_section_identities(config, section)
            for selector in cast(list[object], selectors):
                if not isinstance(selector, str):
                    errors.append(
                        f"Component '{display}': includes.{section} selectors must be strings",
                    )
                    continue
                selector_str = selector.strip()
                if not selector_str:
                    errors.append(
                        f"Component '{display}': includes.{section} contains an empty selector",
                    )
                elif selector_str not in available:
                    errors.append(
                        f"Component '{display}': includes.{section} selector "
                        f"'{selector_str}' matches no item in {section}",
                    )

    for entry in component_entries:
        display = str(entry.get('name') or '').strip() or '<unnamed>'
        for edge_key, verb in (('requires', 'requires'), ('bundles', 'bundles')):
            if edge_key not in entry:
                continue
            # An explicit bare 'requires:'/'bundles:' parses to None and
            # falls through to the list check, matching the model's
            # rejection of null edge lists
            edges_raw = entry.get(edge_key)
            if not isinstance(edges_raw, list):
                errors.append(f"Component '{display}': {edge_key} must be a list of component names")
                continue
            for ref in cast(list[object], edges_raw):
                if not isinstance(ref, str):
                    errors.append(f"Component '{display}': {edge_key} entries must be strings")
                elif ref.strip() not in seen_names:
                    errors.append(f"Component '{display}': {verb} unknown component '{ref.strip()}'")

    # Distinct files-to-download entries deploying to the same final path
    # make component selectors ambiguous (one selector would claim both),
    # silently defeating deselection. Only relevant when components exist;
    # without them the inheritance merge layer handles duplicates itself.
    if component_entries:
        ftd_raw = config.get('files-to-download')
        if isinstance(ftd_raw, list):
            identity_owners: dict[str, int] = {}
            for item_index, item in enumerate(cast(list[object], ftd_raw)):
                if not isinstance(item, dict):
                    continue
                identity = _files_download_identity(cast(dict[str, Any], item))
                if identity is None:
                    continue
                identity = identity.strip()
                if identity in identity_owners:
                    errors.append(
                        f'files-to-download entries {identity_owners[identity]} and '
                        f"{item_index} share the final path '{identity}', making component "
                        f'selectors ambiguous. Give them distinct destinations.',
                    )
                else:
                    identity_owners[identity] = item_index

    if not errors:
        _warn_hook_claim_asymmetry(config, component_entries)
    return errors


def _hook_file_basename(path_or_url: str) -> str:
    """Extract the basename from a hooks.files or hooks.helpers URL or file path.

    Runtime twin of _extract_basename() in scripts/models/environment_config.py
    (standalone script policy prevents importing the model; parity enforced by
    tests/scripts/models/test_hooks_consistency_parity.py). Handles full URLs,
    Windows paths, Unix paths, and plain filenames, matching the on-disk name
    process_resources() gives a downloaded hook file.

    Args:
        path_or_url: The URL or path to extract the basename from.

    Returns:
        The basename (filename) without path components.
    """
    if path_or_url.startswith(('http://', 'https://')):
        parsed = urllib.parse.urlparse(path_or_url)
        path_or_url = parsed.path

    parts = path_or_url.replace('\\', '/').split('/')
    return parts[-1] if parts else path_or_url


def _hook_helper_overlap_message(overlapping: set[str]) -> str:
    """Build the error for a basename declared in both hooks lists.

    Runtime twin of the helper of the same name in
    scripts/models/environment_config.py (standalone script policy prevents
    importing the model; verdict parity is enforced by
    tests/scripts/models/test_hooks_consistency_parity.py).

    Args:
        overlapping: Basenames present in both hooks.files and hooks.helpers.

    Returns:
        The error message.
    """
    return (
        f'hooks.helpers duplicates hooks.files entries: {sorted(overlapping)}. '
        'Both lists install into the same hooks directory, so each basename '
        'belongs to exactly one of them.'
    )


def _hook_helper_reference_message(reference_kind: str, reference: str) -> str:
    """Build the error for a reference that resolves only to a helper.

    Runtime twin of the helper of the same name in
    scripts/models/environment_config.py (standalone script policy prevents
    importing the model; verdict parity is enforced by
    tests/scripts/models/test_hooks_consistency_parity.py).

    Args:
        reference_kind: Where the reference was written, such as
            'hooks.events command' or 'status-line.file'.
        reference: The reference value as the author wrote it.

    Returns:
        The error message.
    """
    return (
        f'{reference_kind} "{reference}" is declared in hooks.helpers. '
        'Referenced scripts and configs belong in hooks.files; hooks.helpers '
        'carries only the shared modules those scripts import.'
    )


def validate_hooks_files_consistency(
    config: dict[str, Any],
    *,
    require_all_files_used: bool = True,
) -> list[str]:
    """Validate hooks files, events, and status-line consistency at runtime.

    Runtime twin of the Pydantic validate_hooks_files_consistency model
    validator in scripts/models/environment_config.py (standalone script
    policy prevents importing the model; parity enforced by
    tests/scripts/models/test_hooks_consistency_parity.py). The model skips
    these cross-reference checks for inherit-declaring configs because they
    are decidable only on the resolved composition; this twin runs on the
    RESOLVED configuration at the main() choke point, so a composition whose
    hook events or status-line reference a missing hook file fails at setup
    time instead of at hook execution. Checks:

    1. Each file in hooks.files is used by a command hook event or status-line
    2. Each command hook's command and config exists in hooks.files
    3. The status-line file and config (if configured) exist in hooks.files
    4. No basename is declared in both hooks.files and hooks.helpers

    hooks.helpers entries are shared modules the hook scripts import at run
    time. They are never referenced as a command, config, or status-line file,
    so rule 1 does not reach them and a reference resolving only to a helper
    basename is reported as a misplaced declaration.

    Prompt, http, agent, and mcp_tool hooks do not reference files and are
    excluded. Structural errors (non-mapping hooks or events, non-string entries)
    suppress the unused-files check because its verdict is only meaningful on
    a well-formed configuration. Never raises.

    Args:
        config: Fully resolved configuration dictionary.
        require_all_files_used: When False, the unused-files check (rule 1)
            is skipped. Used for the post-selection recheck in main(): a
            deselected component may legitimately strand a hooks.files entry
            its claims covered asymmetrically (the hook-claim asymmetry
            warning covers authoring), while a dangling event or status-line
            reference is always an error.

    Returns:
        List of error messages; empty when hooks references are consistent.
    """
    errors: list[str] = []

    status_line_raw = config.get('status-line')
    if status_line_raw is not None and not isinstance(status_line_raw, dict):
        errors.append("'status-line' must be a mapping with a 'file' entry")
        status_line_raw = None
    status_line = cast(dict[str, Any] | None, status_line_raw)

    hooks_raw = config.get('hooks')
    if hooks_raw is None:
        # A status-line without hooks has no hooks.files to carry its script
        if status_line is not None:
            status_file_raw = status_line.get('file', '')
            errors.append(
                f'status-line.file "{status_file_raw}" requires hooks.files to be configured. '
                'Add the status-line script to hooks.files.',
            )
        return errors
    if not isinstance(hooks_raw, dict):
        errors.append("'hooks' must be a mapping with 'files' and 'events' entries")
        return errors
    hooks = cast(dict[str, Any], hooks_raw)

    files_raw = hooks.get('files') or []
    if not isinstance(files_raw, list):
        errors.append("'hooks.files' must be a list of file paths or URLs")
        return errors
    helpers_raw = hooks.get('helpers') or []
    if not isinstance(helpers_raw, list):
        errors.append("'hooks.helpers' must be a list of file paths or URLs")
        return errors
    events_raw = hooks.get('events') or []
    if not isinstance(events_raw, list):
        errors.append("'hooks.events' must be a list of event mappings")
        return errors

    structure_broken = False

    # Build set of available file basenames from hooks.files
    available_files: set[str] = set()
    for file_index, file_path in enumerate(cast(list[object], files_raw)):
        if not isinstance(file_path, str):
            errors.append(f'hooks.files[{file_index}] must be a string path or URL')
            structure_broken = True
            continue
        basename = _hook_file_basename(file_path)
        if basename:
            available_files.add(basename)

    # Helpers install into the same directory as the hook scripts, so one
    # basename cannot be both a referenced script and an unreferenced helper
    helper_files: set[str] = set()
    for helper_index, helper_path in enumerate(cast(list[object], helpers_raw)):
        if not isinstance(helper_path, str):
            errors.append(f'hooks.helpers[{helper_index}] must be a string path or URL')
            structure_broken = True
            continue
        basename = _hook_file_basename(helper_path)
        if basename:
            helper_files.add(basename)

    # Rule 4: a basename belongs to exactly one of the two lists
    overlapping = available_files & helper_files
    if overlapping:
        errors.append(_hook_helper_overlap_message(overlapping))

    available_display = sorted(available_files) if available_files else 'none'

    # Track which files are used
    used_files: set[str] = set()

    # Rule 2: Check that each command hook's command and config exists in
    # hooks.files. Only command hooks use file references; http/prompt/agent
    # hooks are excluded.
    for event_index, event_raw in enumerate(cast(list[object], events_raw)):
        if not isinstance(event_raw, dict):
            errors.append(f'hooks.events[{event_index}] must be a mapping')
            structure_broken = True
            continue
        event = cast(dict[str, Any], event_raw)
        if event.get('type') in ('prompt', 'http', 'agent', 'mcp_tool'):
            continue

        # For command hooks, validate command and config files
        command_raw = event.get('command')
        if command_raw:
            if not isinstance(command_raw, str):
                errors.append(f'hooks.events[{event_index}] command must be a string')
                structure_broken = True
            else:
                command_file = command_raw.strip()
                if command_file:
                    if command_file not in available_files:
                        errors.append(
                            _hook_helper_reference_message('hooks.events command', command_file)
                            if command_file in helper_files
                            else f'hooks.events command "{command_file}" not found in hooks.files. '
                                 f'Available files: {available_display}',
                        )
                    else:
                        used_files.add(command_file)

        # Check config file reference if present
        config_raw = event.get('config')
        if config_raw:
            if not isinstance(config_raw, str):
                errors.append(f'hooks.events[{event_index}] config must be a string')
                structure_broken = True
            else:
                config_file = config_raw.strip()
                # Strip query parameters from the config filename (same as
                # the command-string construction in _build_hooks_json)
                clean_config = config_file.split('?')[0] if '?' in config_file else config_file
                config_basename = _hook_file_basename(clean_config)
                if config_basename:
                    if config_basename not in available_files:
                        errors.append(
                            _hook_helper_reference_message('hooks.events config', config_file)
                            if config_basename in helper_files
                            else f'hooks.events config "{config_file}" not found in hooks.files. '
                                 f'Available files: {available_display}',
                        )
                    else:
                        used_files.add(config_basename)

    # Rule 3: Check that the status-line file and config exist in hooks.files.
    # The value checks mirror the StatusLine field validators in the model
    # (file required and non-empty, config non-empty when specified, no null
    # bytes), which run even for inherit-declaring configs, so a resolved
    # composition can never legitimately carry these shapes.
    if status_line is not None:
        status_file_raw = status_line.get('file')
        if status_file_raw is not None and not isinstance(status_file_raw, str):
            errors.append('status-line.file must be a string')
            structure_broken = True
        elif status_file_raw is None or not status_file_raw.strip():
            errors.append('status-line.file cannot be empty')
            structure_broken = True
        elif '\x00' in status_file_raw:
            errors.append('status-line.file cannot contain null bytes')
            structure_broken = True
        else:
            status_file = status_file_raw.strip()
            if status_file not in available_files:
                errors.append(
                    _hook_helper_reference_message('status-line.file', status_file)
                    if status_file in helper_files
                    else f'status-line.file "{status_file}" not found in hooks.files. '
                         f'Available files: {available_display}',
                )
            else:
                used_files.add(status_file)

        status_config_raw = status_line.get('config')
        if status_config_raw is not None and not isinstance(status_config_raw, str):
            errors.append('status-line.config must be a string')
            structure_broken = True
        elif isinstance(status_config_raw, str) and not status_config_raw.strip():
            errors.append('status-line.config cannot be empty when specified')
            structure_broken = True
        elif isinstance(status_config_raw, str) and '\x00' in status_config_raw:
            errors.append('status-line.config cannot contain null bytes')
            structure_broken = True
        elif isinstance(status_config_raw, str):
            config_file = status_config_raw.strip()
            clean_config = config_file.split('?')[0] if '?' in config_file else config_file
            config_basename = _hook_file_basename(clean_config)
            if config_basename:
                if config_basename not in available_files:
                    errors.append(
                        _hook_helper_reference_message('status-line.config', config_file)
                        if config_basename in helper_files
                        else f'status-line.config "{config_file}" not found in hooks.files. '
                             f'Available files: {available_display}',
                    )
                else:
                    used_files.add(config_basename)

    # Rule 1: Check that each file in hooks.files is used somewhere
    if require_all_files_used and not structure_broken:
        unused_files = available_files - used_files
        if unused_files:
            errors.append(
                f'hooks.files contains unused files: {sorted(unused_files)}. '
                'Each file must be referenced by a hook event or status-line.',
            )

    return errors


def _parse_csv(value: str | None) -> list[str] | None:
    """Parse a comma-separated flag or environment value, distinguishing absent from empty.

    Args:
        value: Raw flag or environment variable value, or None when absent.

    Returns:
        None when the input is absent; otherwise the list of non-empty,
        whitespace-stripped tokens (possibly empty).
    """
    if value is None:
        return None
    return [token.strip() for token in value.split(',') if token.strip()]


def _validate_component_selector_args(
    component_names: list[str],
    args: argparse.Namespace,
) -> list[str]:
    """Validate --select/--with/--without values against the registry.

    Args:
        component_names: Known component names from the configuration.
        args: Parsed CLI arguments (after resolve_args env merging).

    Returns:
        List of error messages; empty when every selector is valid.
    """
    import difflib

    errors: list[str] = []
    known = set(component_names)
    for flag, raw in (
        ('--select', args.select),
        ('--with', args.with_),
        ('--without', args.without),
    ):
        tokens = _parse_csv(raw)
        if tokens is None:
            continue
        if not tokens:
            sentinel_hint = ' or a sentinel (all, none)' if flag == '--select' else ''
            errors.append(f'{flag} requires at least one component name{sentinel_hint}')
            continue
        for token in tokens:
            if token in RESERVED_COMPONENT_NAMES:
                if flag != '--select':
                    errors.append(
                        f"{flag} does not accept the sentinel '{token}' (only --select does)",
                    )
                elif len(tokens) > 1:
                    errors.append(
                        f"--select sentinel '{token}' cannot be combined with other names",
                    )
                continue
            if token not in known:
                close = difflib.get_close_matches(token, sorted(known), n=1, cutoff=0.6)
                hint = f" (did you mean '{close[0]}'?)" if close else ''
                errors.append(f"{flag}: unknown component '{token}'{hint}")
    return errors


def _bundle_closure(seed: list[str], bundles_map: dict[str, list[str]]) -> set[str]:
    """Expand a selection along soft bundle edges to a fixpoint.

    Breadth-first over the ordered seed so traversal is deterministic;
    cycles are tolerated via the visited set.

    Args:
        seed: Initially selected component names in registry order.
        bundles_map: Component name to its bundled component names.

    Returns:
        The seed expanded with every transitively bundled name.
    """
    result = set(seed)
    queue = list(seed)
    index = 0
    while index < len(queue):
        current = queue[index]
        index += 1
        for bundled in bundles_map.get(current, []):
            if bundled not in result:
                result.add(bundled)
                queue.append(bundled)
    return result


def _requires_closure(
    seed: list[str],
    requires_map: dict[str, list[str]],
) -> tuple[set[str], dict[str, str]]:
    """Expand a selection along hard requires edges, recording causes.

    Breadth-first over the ordered seed so that when several selected
    components require the same target, the recorded cause is always the
    earliest requester in registry order (a set-seeded traversal would make
    the [auto: ...] summary text vary between identical runs). Cycles are
    tolerated via the visited set.

    Args:
        seed: Selected component names in registry order.
        requires_map: Component name to its required component names.

    Returns:
        Tuple of (expanded name set, auto-included name to requester map).
    """
    result = set(seed)
    causes: dict[str, str] = {}
    queue = list(seed)
    index = 0
    while index < len(queue):
        current = queue[index]
        index += 1
        for required in requires_map.get(current, []):
            if required not in result:
                result.add(required)
                causes[required] = current
                queue.append(required)
    return result, causes


def resolve_component_selection(
    components: list[dict[str, Any]],
    args: argparse.Namespace,
    picker: Callable[[list[str]], list[str] | None] | None = None,
) -> ComponentSelection:
    """Resolve which components are selected for this run.

    Selection inputs in precedence order: author defaults, then the
    --select/--with/--without selectors (env var equivalents already merged
    by resolve_args), then the interactive picker. --select replaces the
    default set entirely (with the sentinels all/none); --with adds to it;
    bundle edges softly expand the seeded set; --without then removes
    names; the picker (when supplied) lets the user edit that set; the hard
    requires closure runs last and wins over --without with a warning.

    The picker runs only when no selector was supplied and neither --yes
    nor --dry-run is set (explicit selectors and non-interactive modes make
    the run deterministic); a picker returning None keeps the
    non-interactive set.

    Args:
        components: Component entries from the validated configuration.
        args: Parsed CLI arguments (after resolve_args env merging).
        picker: Optional callable receiving the pre-selected names in
            registry order and returning the user's selection, or None
            when no interaction was possible.

    Returns:
        ComponentSelection describing the final selection; inactive when
        the configuration defines no components.
    """
    if not components:
        return ComponentSelection()

    names = [str(c.get('name', '')).strip() for c in components]
    labels = {
        name: str(c.get('label') or '').strip() or name
        for name, c in zip(names, components, strict=True)
    }
    bundles_map = {
        name: [str(b).strip() for b in c.get('bundles') or []]
        for name, c in zip(names, components, strict=True)
    }
    requires_map = {
        name: [str(r).strip() for r in c.get('requires') or []]
        for name, c in zip(names, components, strict=True)
    }

    defaults = [name for name, c in zip(names, components, strict=True) if c.get('default', True)]
    select_tokens = _parse_csv(args.select)
    with_tokens = _parse_csv(args.with_) or []
    without_set = set(_parse_csv(args.without) or [])

    if select_tokens is not None:
        if select_tokens == ['all']:
            base = set(names)
        elif select_tokens == ['none']:
            base = set()
        else:
            base = set(select_tokens)
    else:
        base = set(defaults)

    base |= set(with_tokens)
    expanded = _bundle_closure([name for name in names if name in base], bundles_map)
    trimmed = expanded - without_set

    selectors_given = any(
        value is not None for value in (args.select, args.with_, args.without)
    )
    picker_changed = False
    if picker is not None and not selectors_given and not args.yes and not args.dry_run:
        picked = picker([name for name in names if name in trimmed])
        if picked is not None:
            known_names = set(names)
            before_picker = trimmed
            trimmed = {name for name in picked if name in known_names}
            picker_changed = trimmed != before_picker

    final, causes = _requires_closure([name for name in names if name in trimmed], requires_map)

    for name in sorted(final & without_set):
        warning(
            f"--without '{name}' overridden: component "
            f"'{causes.get(name, '?')}' requires it",
        )

    selected = [name for name in names if name in final]
    skipped = [name for name in names if name not in final]
    # --select alone does not round-trip: feeding the final selection back
    # re-runs the bundle closure, re-adding bundle targets the user
    # deselected. Appending --without for every skipped component pins the
    # exact set: bundle re-expansions are stripped again and the requires
    # closure is idempotent on the already-closed selection, so no
    # override warning fires on replay.
    replay = '--select ' + (','.join(selected) if selected else 'none')
    if selected and skipped:
        replay += ' --without ' + ','.join(skipped)

    # The delta a later run replays: the selectors as given, or the exact
    # set a picker choice produced; the author defaults leave no delta
    origins: dict[str, str] = getattr(args, 'origins', {})
    selector_origins = {
        origins.get(dest)
        for dest in ('select', 'with_', 'without')
        if getattr(args, dest, None) is not None
    }
    delta: dict[str, str | None] | None = None
    origin = 'yaml'
    remembered = False
    if selectors_given:
        delta = {'select': args.select, 'with': args.with_, 'without': args.without}
        if 'remembered' in selector_origins:
            remembered = True
            origin = origins.get('components') or 'cli'
        elif 'env' in selector_origins and 'cli' not in selector_origins:
            origin = 'env'
        else:
            origin = 'cli'
    elif picker_changed:
        delta = {
            'select': ','.join(selected) if selected else 'none',
            'with': None,
            'without': ','.join(skipped) if selected and skipped else None,
        }
        origin = 'cli'
    return ComponentSelection(
        is_active=True,
        available=names,
        labels=labels,
        selected=selected,
        auto_included={name: f"required by '{cause}'" for name, cause in causes.items()},
        replay=replay,
        delta=delta,
        origin=origin,
        remembered=remembered,
        defaults=defaults,
    )


def remembered_component_delta(manifest: dict[str, Any] | None) -> tuple[dict[str, str | None] | None, str | None]:
    """Read the component delta a profile manifest remembers.

    A manifest remembers its delta only when the selectors were typed for
    the run or came from the environment; the author defaults are read
    from the configuration again on every run.

    Args:
        manifest: The profile manifest, or None when the profile is new.

    Returns:
        The remembered --select, --with and --without values and their
        recorded origin, or (None, None).
    """
    if manifest is None:
        return None, None
    origins = manifest.get('origins')
    origin = origins.get('components') if isinstance(origins, dict) else None
    delta = manifest.get('components')
    if origin not in ('cli', 'env') or not isinstance(delta, dict):
        return None, None
    values = {
        key: str(value) if isinstance(value, str) and value else None
        for key, value in cast(dict[str, Any], delta).items()
        if key in ('select', 'with', 'without')
    }
    if not any(values.values()):
        return None, None
    return values, str(origin)


def apply_remembered_component_delta(
    args: argparse.Namespace,
    manifest: dict[str, Any] | None,
    component_names: list[str],
    *,
    profile_name: str,
    manifest_path: Path | None,
) -> list[str]:
    """Fill the selectors of a run that gave none from the profile's remembered delta.

    A remembered delta counts as supplied selectors: the picker does not
    run, and the summary marks the selection [remembered]. The recorded
    origin is kept in args.origins['components'] so the manifest records it
    again. The delta is checked against the configuration's current
    components before the selector validation sees it, because nobody typed
    it for this run: a remembered --without naming a component the
    configuration no longer declares has no install effect, so the name is
    dropped with a warning and the cleaned delta is what the manifest
    records next; a remembered --select or --with naming one would change
    what gets installed, so the run refuses and names the manifest.

    Args:
        args: Arguments after resolve_args().
        manifest: The manifest of the profile the run installs into, or
            None when the profile is new.
        component_names: The names the configuration's components declare.
        profile_name: The profile's display name.
        manifest_path: The manifest the delta came from, named in an error.

    Returns:
        The errors a remembered --select or --with produced, empty when the
        delta applies.
    """
    if any(getattr(args, dest) is not None for dest in ('select', 'with_', 'without')):
        return []
    delta, origin = remembered_component_delta(manifest)
    if delta is None:
        return []
    known = set(component_names) | RESERVED_COMPONENT_NAMES
    errors: list[str] = []
    cleaned: dict[str, str | None] = {}
    for key, flag in (('select', '--select'), ('with', '--with'), ('without', '--without')):
        tokens = _parse_csv(delta.get(key)) or []
        unknown = [token for token in tokens if token not in known]
        if not unknown:
            cleaned[key] = delta.get(key)
        elif key == 'without':
            for name in unknown:
                warning(
                    f"components: the remembered selection of profile {profile_name} names '{name}', "
                    'which the configuration no longer declares; dropped [remembered]',
                )
            kept = [token for token in tokens if token in known]
            cleaned[key] = ','.join(kept) if kept else None
        else:
            names = ', '.join(f"'{name}'" for name in unknown)
            errors.append(
                f'components: the remembered selection of profile {profile_name} (recorded in {manifest_path}) '
                f'names {names} in {flag}, which the configuration no longer declares; pass {flag} explicitly '
                'to replace the remembered selection, or --select all.',
            )
    if errors:
        return errors
    for key, dest in (('select', 'select'), ('with', 'with_'), ('without', 'without')):
        value = cleaned.get(key)
        if value:
            setattr(args, dest, value)
            args.origins[dest] = 'remembered'
    if any(cleaned.values()):
        args.origins['components'] = origin
    return []


def _component_claim_sets(
    config: dict[str, Any],
    selection: ComponentSelection,
) -> tuple[dict[str, set[str]], dict[str, set[str]]] | None:
    """Compute per-section claimed and kept selector sets for a selection.

    Args:
        config: Fully resolved configuration dictionary.
        selection: The resolved component selection.

    Returns:
        Tuple of (claimed, kept) selector sets keyed by selectable section,
        or None when the configuration defines no components or the
        selection is inactive.
    """
    components = [
        cast(dict[str, Any], c)
        for c in config.get('components') or []
        if isinstance(c, dict)
    ]
    if not components or not selection.is_active:
        return None

    selected = set(selection.selected)
    claimed: dict[str, set[str]] = {section: set() for section in SELECTABLE_SECTIONS}
    kept: dict[str, set[str]] = {section: set() for section in SELECTABLE_SECTIONS}
    for comp in components:
        includes_raw = comp.get('includes')
        if not isinstance(includes_raw, dict):
            continue
        is_selected = str(comp.get('name', '')).strip() in selected
        for section, selectors in cast(dict[str, Any], includes_raw).items():
            if section not in SELECTABLE_SECTIONS or not isinstance(selectors, list):
                continue
            selector_set = {str(s).strip() for s in cast(list[object], selectors)}
            claimed[section] |= selector_set
            if is_selected:
                kept[section] |= selector_set
    return claimed, kept


def collect_deselected_items(
    config: dict[str, Any],
    selection: ComponentSelection,
) -> dict[str, list[Any]]:
    """Collect the concrete items a selection drops, per section.

    Runs on the UNFILTERED configuration (before apply_component_selection
    mutates it in place), so the removal plan is derived entirely from the
    current configuration and needs no on-disk state: the config itself
    names every claimed item, and an item is deselected when it is claimed
    by at least one component and kept by none of the selected ones.
    Dependencies are excluded by design: arbitrary install commands cannot
    be reversed.

    Args:
        config: Fully resolved, unfiltered configuration dictionary.
        selection: The resolved component selection.

    Returns:
        Mapping of section name to dropped item list, with the composite
        hooks section split into 'hooks-files' and 'hooks-events'. All
        lists are empty when nothing is deselected.
    """
    result: dict[str, list[Any]] = {
        'agents': [], 'slash-commands': [], 'rules': [], 'skills': [],
        'mcp-servers': [], 'files-to-download': [],
        'hooks-files': [], 'hooks-events': [],
    }
    claim_sets = _component_claim_sets(config, selection)
    if claim_sets is None:
        return result
    claimed, kept = claim_sets

    def _dropped(section: str, keys: set[str]) -> bool:
        return bool(keys) and bool(keys & claimed[section]) and not (keys & kept[section])

    for section in ('agents', 'slash-commands', 'rules', 'skills', 'mcp-servers', 'files-to-download'):
        section_raw = config.get(section)
        if isinstance(section_raw, list):
            result[section] = [
                item for item in cast(list[object], section_raw)
                if _dropped(section, _component_item_keys(section, item))
            ]

    hooks_raw = config.get('hooks')
    if isinstance(hooks_raw, dict):
        hooks_dict = cast(dict[str, Any], hooks_raw)
        result['hooks-files'] = [
            file_path for file_path in cast(list[object], hooks_dict.get('files') or [])
            if _dropped('hooks', {str(file_path).strip()})
        ]
        for event in cast(list[object], hooks_dict.get('events') or []):
            if isinstance(event, dict):
                event_id = cast(dict[str, Any], event).get('id')
                if event_id is not None and _dropped('hooks', {str(event_id).strip()}):
                    result['hooks-events'].append(event)
    return result


def has_deselected_items(deselected: dict[str, list[Any]]) -> bool:
    """Report whether a removal plan contains any item.

    Args:
        deselected: Mapping produced by collect_deselected_items().

    Returns:
        True when at least one section lists a dropped item.
    """
    return any(items for items in deselected.values())


# Output grammar of _build_file_command(): optional launcher prefix, quoted
# script path, optional quoted config path. Only commands of this shape may
# be compared quote-insensitively; in a direct command, quotes are literal
# shell syntax and stripping them would conflate distinct commands.
_BUILT_FILE_COMMAND_PATTERN = re.compile(
    r'(?:uv run --no-project --python 3\.12 |node )?"[^"]*"(?: "[^"]*")?',
)


def _hook_entries_equal(built: dict[str, Any], existing: object) -> bool:
    """Compare a freshly built hook entry against an on-disk hook entry.

    Every field is compared by equality except ``command``: when the built
    command matches the _build_file_command() output grammar, it is compared
    with double quotes stripped from both sides, because entries written
    before path quoting existed carry the same file-reference command
    unquoted. A direct command (passed through verbatim by
    _build_hooks_json()) keeps its quotes as literal content and is compared
    exactly, so two direct commands differing only in quoting never match.

    Args:
        built: Hook entry dict produced by _build_hooks_json().
        existing: Candidate entry from the on-disk settings JSON.

    Returns:
        True when the entries describe the same hook.
    """
    if not isinstance(existing, dict):
        return False
    built_rest = {k: v for k, v in built.items() if k != 'command'}
    existing_rest = {k: v for k, v in cast(dict[str, Any], existing).items() if k != 'command'}
    if built_rest != existing_rest:
        return False
    built_command = built.get('command')
    existing_command = cast(dict[str, Any], existing).get('command')
    if built_command == existing_command:
        return True
    if (
        isinstance(built_command, str)
        and isinstance(existing_command, str)
        and _BUILT_FILE_COMMAND_PATTERN.fullmatch(built_command)
    ):
        return built_command.replace('"', '') == existing_command.replace('"', '')
    return False


def _strip_hooks_from_settings(
    settings_path: Path,
    deselected_events: list[dict[str, Any]],
    hooks_dir: Path,
) -> int:
    """Remove deselected hook entries from a shared settings.json file.

    The shared-settings merge is a list union that never drops an existing
    entry, so hook events written by an earlier run survive deselection
    there. This builds the exact JSON the deselected events generate (via
    the same builder the writer uses) and removes matching entries from the
    file: hook dicts are matched inside same-matcher groups via
    _hook_entries_equal() (quote-insensitive on the command, so entries
    written before path quoting existed still match), emptied groups and
    event keys are dropped.

    Args:
        settings_path: Path to the shared settings.json file.
        deselected_events: Raw hook event dicts dropped by the selection.
        hooks_dir: Directory hook file references resolve against.

    Returns:
        Number of hook entries removed; 0 when the file or matches are absent.
    """
    if not deselected_events or not settings_path.exists():
        return 0
    try:
        settings = json.loads(settings_path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError) as e:
        warning(f'Cannot reconcile hooks in {settings_path.name}: {e}')
        return 0
    hooks_json = settings.get('hooks')
    if not isinstance(hooks_json, dict):
        return 0

    to_remove = _build_hooks_json({'events': deselected_events}, hooks_dir)
    removed = 0
    for event_name, remove_groups in to_remove.items():
        existing_groups = hooks_json.get(event_name)
        if not isinstance(existing_groups, list):
            continue
        for remove_group in cast(list[dict[str, Any]], remove_groups):
            for existing_group in cast(list[Any], existing_groups):
                if not isinstance(existing_group, dict):
                    continue
                group = cast(dict[str, Any], existing_group)
                if group.get('matcher', '') != remove_group.get('matcher', ''):
                    continue
                group_hooks = group.get('hooks')
                if not isinstance(group_hooks, list):
                    continue
                for hook_entry in cast(list[Any], remove_group.get('hooks') or []):
                    match = next(
                        (
                            candidate for candidate in cast(list[Any], group_hooks)
                            if _hook_entries_equal(cast(dict[str, Any], hook_entry), candidate)
                        ),
                        None,
                    )
                    if match is not None:
                        group_hooks.remove(match)
                        removed += 1
        hooks_json[event_name] = [
            g for g in cast(list[Any], existing_groups)
            if not isinstance(g, dict) or cast(dict[str, Any], g).get('hooks')
        ]
        if not hooks_json[event_name]:
            hooks_json.pop(event_name)

    if removed:
        try:
            settings_path.write_text(
                json.dumps(settings, indent=2, ensure_ascii=False) + '\n',
                encoding='utf-8',
            )
        except OSError as e:
            warning(f'Cannot write reconciled {settings_path.name}: {e}')
            return 0
    return removed


def _installed_resource_name(item: object) -> str:
    """Compute the on-disk filename process_resources() installs an item under.

    Args:
        item: Resource path or URL as declared in the configuration.

    Returns:
        The plain query-stripped basename, exactly as the installer names it.
    """
    return Path(str(item).split('?')[0]).name


def execute_deselection_cleanup(
    deselected: dict[str, list[Any]],
    surviving_config: dict[str, Any],
    *,
    agents_dir: Path,
    commands_dir: Path,
    rules_dir: Path,
    skills_dir: Path,
    hooks_dir: Path,
    is_isolated: bool,
    linked_entries: frozenset[str] = frozenset(),
) -> None:
    """Remove previously installed artifacts of deselected components.

    Mirrors each installer's target-path resolution so a re-run that
    deselects a component uninstalls what an earlier run installed. A
    removal target that a surviving item of the same section also installs
    to (a basename collision) is skipped with a notice, so cleanup never
    deletes a file the current run keeps. A section whose directory is a
    link to another profile is skipped whole, because its files belong to
    that profile. Every removal is tolerant: absent targets are skipped
    silently (a first run has nothing to remove) and failures degrade to
    warnings.

    Args:
        deselected: Removal plan from collect_deselected_items(). In an
            isolated run its files-to-download destinations have been
            through ConfigHomeReroot.apply() together with the installed
            ones, so the download-target resolution below removes the file
            the install wrote into the profile, never the base copy.
        surviving_config: The filtered configuration (after
            apply_component_selection), used to protect surviving targets.
        agents_dir: Directory agent files install into.
        commands_dir: Directory slash-command files install into.
        rules_dir: Directory rule files install into.
        skills_dir: Directory skill directories install into.
        hooks_dir: Directory hook files install into.
        is_isolated: Whether the run targets an isolated command profile.
            The isolated config.json is rebuilt atomically each run, so
            hook reconciliation applies only to the shared settings.json
            of non-isolated runs.
        linked_entries: The profile entries that are links to another
            profile; nothing inside them is removed.
    """
    import shutil as _shutil

    def _remove_file(path: Path, description: str) -> None:
        try:
            if path.is_file():
                path.unlink()
                success(f'Removed deselected {description}: {path.name}')
        except OSError as e:
            warning(f'Cannot remove {path}: {e}')

    def _surviving_names(section: str) -> set[str]:
        if section == 'hooks-files':
            hooks_raw = surviving_config.get('hooks')
            items = cast(dict[str, Any], hooks_raw).get('files') or [] if isinstance(hooks_raw, dict) else []
        else:
            items = surviving_config.get(section) or []
        return {_installed_resource_name(item) for item in cast(list[object], items)}

    for section, target_dir, description, entry in (
        ('agents', agents_dir, 'agent', 'agents'),
        ('slash-commands', commands_dir, 'slash command', 'commands'),
        ('rules', rules_dir, 'rule', 'rules'),
        ('hooks-files', hooks_dir, 'hook file', 'hooks'),
    ):
        if entry in linked_entries and deselected[section]:
            info(f'Keeping the {description} files: {entry}/ is linked to another profile')
            continue
        surviving = _surviving_names(section)
        for item in deselected[section]:
            name = _installed_resource_name(item)
            if name in surviving:
                info(f"Keeping {description} '{name}': a selected item installs the same file")
                continue
            _remove_file(target_dir / name, description)

    def _download_target(entry: dict[str, Any]) -> Path | None:
        identity = _files_download_identity(entry)
        if not identity:
            return None
        target = Path(normalize_tilde_path(identity.strip()))
        # process_file_downloads() also treats an EXISTING directory as a
        # directory-form dest even without a trailing separator
        if target.is_dir():
            target = target / _source_filename(str(entry.get('source', '')))
        return target

    surviving_targets = {
        resolved for resolved in (
            _download_target(cast(dict[str, Any], item))
            for item in cast(list[object], surviving_config.get('files-to-download') or [])
            if isinstance(item, dict)
        ) if resolved is not None
    }
    linked_dirs = [skills_dir.parent / name for name in linked_entries]
    for entry in deselected['files-to-download']:
        if isinstance(entry, dict):
            target = _download_target(cast(dict[str, Any], entry))
            if target is None:
                continue
            if target in surviving_targets:
                info(f"Keeping file '{target.name}': a selected entry deploys to the same path")
                continue
            if any(_relative_inside(target, linked_dir) is not None for linked_dir in linked_dirs):
                info(f"Keeping file '{target.name}': it lies inside an entry linked to another profile")
                continue
            _remove_file(target, 'file')

    if 'skills' in linked_entries and deselected['skills']:
        info('Keeping the skill directories: skills/ is linked to another profile')
    for skill in deselected['skills'] if 'skills' not in linked_entries else []:
        if isinstance(skill, dict):
            name = str(cast(dict[str, Any], skill).get('name') or '').strip()
            if name:
                skill_dir = skills_dir / name
                try:
                    if skill_dir.is_dir():
                        _shutil.rmtree(skill_dir)
                        success(f'Removed deselected skill: {name}')
                except OSError as e:
                    warning(f'Cannot remove skill directory {skill_dir}: {e}')

    claude_cmd = find_command('claude') if deselected['mcp-servers'] else None
    for server in deselected['mcp-servers']:
        if not isinstance(server, dict):
            continue
        server_dict = cast(dict[str, Any], server)
        name = str(server_dict.get('name') or '').strip()
        if not name:
            continue
        try:
            scopes = normalize_scope(server_dict.get('scope', 'user'))
        except ValueError:
            scopes = ['user']
        for scope in scopes:
            if scope == 'profile':
                # The profile mcp.json is rebuilt from the filtered list
                # every run, so a deselected profile server is already gone
                continue
            if not claude_cmd:
                warning(f"Cannot remove MCP server '{name}': claude command not found")
                break
            result = run_command(
                [claude_cmd, 'mcp', 'remove', name, '--scope', scope],
                capture_output=True,
            )
            if result.returncode == 0:
                success(f'Removed deselected MCP server: {name} (scope: {scope})')
            else:
                stderr = (result.stderr or '').strip()
                # A missing server is the healthy first-run case. The claude
                # CLI reports it as 'No user-scoped MCP server found with
                # name: <name>' (or the project/local variants), so the
                # shared marker is 'found with name'
                if 'found with name' not in stderr.lower():
                    warning(
                        f"Cannot remove MCP server '{name}' (scope: {scope}): "
                        f'exit code {result.returncode}'
                        + (f' -- {stderr}' if stderr else ''),
                    )

    if not is_isolated and deselected['hooks-events']:
        settings_path = get_real_user_home() / '.claude' / 'settings.json'
        removed = _strip_hooks_from_settings(
            settings_path, deselected['hooks-events'], hooks_dir,
        )
        if removed:
            success(f'Removed {removed} deselected hook entr{"y" if removed == 1 else "ies"} from settings.json')


def apply_component_selection(
    config: dict[str, Any],
    selection: ComponentSelection,
) -> None:
    """Filter the resolved config in place according to the selection.

    Per section: an item is dropped iff at least one component claims it
    and no selected component claims it. Items claimed by no component are
    mandatory and always survive, as do items without an identity. Section
    keys are never deleted; emptied lists stay in place preserving shape.

    Args:
        config: Fully resolved configuration dictionary (mutated in place).
        selection: The resolved component selection.
    """
    claim_sets = _component_claim_sets(config, selection)
    if claim_sets is None:
        return
    claimed, kept = claim_sets

    def _survives(section: str, keys: set[str]) -> bool:
        return not keys or not (keys & claimed[section]) or bool(keys & kept[section])

    for section in ('agents', 'slash-commands', 'rules', 'skills', 'mcp-servers', 'files-to-download'):
        section_raw = config.get(section)
        if isinstance(section_raw, list):
            config[section] = [
                item for item in cast(list[object], section_raw)
                if _survives(section, _component_item_keys(section, item))
            ]

    deps_raw = config.get('dependencies')
    if isinstance(deps_raw, dict):
        deps_dict = cast(dict[str, Any], deps_raw)
        for platform_key, commands in deps_dict.items():
            if isinstance(commands, list):
                deps_dict[platform_key] = [
                    command for command in cast(list[object], commands)
                    if _survives('dependencies', _component_item_keys('dependencies', command))
                ]

    hooks_raw = config.get('hooks')
    if isinstance(hooks_raw, dict):
        hooks_dict = cast(dict[str, Any], hooks_raw)
        files_raw = hooks_dict.get('files')
        if isinstance(files_raw, list):
            hooks_dict['files'] = [
                file_path for file_path in cast(list[object], files_raw)
                if _survives('hooks', {str(file_path).strip()})
            ]
        events_raw = hooks_dict.get('events')
        if isinstance(events_raw, list):
            kept_events: list[object] = []
            for event in cast(list[object], events_raw):
                event_id = cast(dict[str, Any], event).get('id') if isinstance(event, dict) else None
                event_keys = {str(event_id).strip()} if event_id is not None else set[str]()
                if _survives('hooks', event_keys):
                    kept_events.append(event)
            hooks_dict['events'] = kept_events


def display_component_registry(components: list[dict[str, Any]]) -> None:
    """Print the component registry for --list-components.

    Args:
        components: Component entries from the validated configuration.
    """
    print()
    print(f'{Colors.BOLD}Components:{Colors.NC}')
    if not components:
        info('This configuration defines no components; every item is mandatory.')
        return
    for comp in components:
        name = str(comp.get('name', '')).strip()
        label = str(comp.get('label') or '').strip()
        default_marker = ' [default]' if comp.get('default', True) else ''
        title = name + (f' -- {label}' if label and label != name else '') + default_marker
        print(f'  * {title}')
        description = str(comp.get('description') or '').strip()
        if description:
            print(f'      {description}')
        requires = [str(r).strip() for r in comp.get('requires') or []]
        if requires:
            print(f'      requires: {", ".join(requires)}')
        bundles = [str(b).strip() for b in comp.get('bundles') or []]
        if bundles:
            print(f'      bundles: {", ".join(bundles)}')
        includes_raw = comp.get('includes')
        if isinstance(includes_raw, dict):
            counts = ', '.join(
                f'{len(cast(list[object], selectors))} {section}'
                for section, selectors in cast(dict[str, Any], includes_raw).items()
                if isinstance(selectors, list)
            )
            if counts:
                print(f'      includes: {counts}')


def _prompt_component_selection_numbered(
    names: list[str],
    labels: dict[str, str],
    seed: list[str],
) -> list[str] | None:
    """Numbered toggle-loop fallback picker (Tier 2).

    Uses _read_user_input, which falls back to /dev/tty for piped stdin
    on Unix. Ctrl-C exits the setup with code 0, mirroring the questionary
    tier; a confirmation-style swallow would silently install the partial
    selection the user was abandoning.

    Args:
        names: Component names in registry order.
        labels: Display label per component name.
        seed: Pre-checked component names.

    Returns:
        Selected names in registry order, or None when input is unavailable
        (the caller keeps the non-interactive selection).
    """
    # The questionary tier can fail MID-render (mintty's console error)
    # after its terminal queries went out, so replies may be queued AFTER
    # the pre-tier flush; discard them before the first read, where an
    # empty line means confirm
    _flush_pending_terminal_input()

    selected = set(seed)
    while True:
        print()
        print(f'{Colors.BOLD}Components:{Colors.NC}')
        for number, name in enumerate(names, 1):
            mark = '[x]' if name in selected else '[ ]'
            print(f'  {number}. {mark} {labels.get(name, name)}')
        try:
            response = _read_user_input(
                "Toggle by number, 'a' = all, 'n' = none, Enter = confirm: ",
            ).strip().lower()
        except KeyboardInterrupt:
            print()
            info('Selection cancelled.')
            sys.exit(0)
        except (EOFError, OSError):
            return None
        if not response:
            return [name for name in names if name in selected]
        if response == 'a':
            selected = set(names)
        elif response == 'n':
            selected = set()
        elif response.isdigit() and 1 <= int(response) <= len(names):
            name = names[int(response) - 1]
            if name in selected:
                selected.discard(name)
            else:
                selected.add(name)
        else:
            warning(f"Invalid input '{response}'. Enter a number, 'a', 'n', or press Enter.")


def prompt_component_selection(
    components: list[dict[str, Any]],
    seed: list[str],
    environment_name: str,
    config_source: str,
) -> list[str] | None:
    """Interactively pick components, degrading gracefully across three tiers.

    Tier 1 uses a questionary checkbox (lazy import so the standalone
    script works without the dependency); any failure to import or drive
    the interactive console falls back to Tier 2, the numbered toggle loop
    (the catch is deliberately broad because mintty's
    NoConsoleScreenBufferError is not an OSError). Tier 3 is the numbered
    picker returning None when input is unavailable, which keeps the
    non-interactive selection. Prints a two-line context banner first
    because the main header() renders later in the flow.

    Args:
        components: Component entries from the validated configuration.
        seed: Pre-checked component names in registry order.
        environment_name: Environment display name for the context banner.
        config_source: Config source path or URL for the context banner.

    Returns:
        Selected component names in registry order, or None when no
        interaction was possible.
    """
    names = [str(c.get('name', '')).strip() for c in components]
    labels = {
        name: str(c.get('label') or '').strip() or name
        for name, c in zip(names, components, strict=True)
    }
    descriptions = {
        name: str(c.get('description') or '').strip()
        for name, c in zip(names, components, strict=True)
    }

    print()
    print(f'{Colors.BOLD}Environment:{Colors.NC} {environment_name}')
    print(f'{Colors.BOLD}Source:{Colors.NC} {config_source}')

    # Discard bytes queued before the picker renders (stray terminal
    # reports, accidental type-ahead) so they never register as the first
    # answer. The flush runs once before the tiers, not per loop
    # iteration, because type-ahead BETWEEN toggle prompts is legitimate;
    # in-loop contamination is neutralized by the sanitizing read.
    _flush_pending_terminal_input()

    try:
        import questionary

        seed_set = set(seed)
        choices = [
            questionary.Choice(
                title=labels[name],
                value=name,
                checked=name in seed_set,
                description=descriptions[name] or None,
            )
            for name in names
        ]
        result = questionary.checkbox(
            'Select components to install (space toggles, enter confirms)',
            choices=choices,
        ).ask()
        if result is None:
            info('Selection cancelled.')
            sys.exit(0)
        picked = {str(name) for name in cast(list[object], result)}
        return [name for name in names if name in picked]
    except ImportError:
        info('questionary is not installed; using the numbered fallback picker.')
    except Exception as exc:
        warning(
            f'Interactive picker unavailable ({exc.__class__.__name__}); '
            f'using the numbered fallback picker.',
        )

    return _prompt_component_selection_numbered(names, labels, seed)


def global_config_target_file(artifact_base_dir: Path | None) -> Path:
    """Resolve the one .claude.json a run's global-config write targets.

    An isolated run writes its profile's own file, because the Claude Code
    CLI resolves getGlobalClaudeFile() through CLAUDE_CONFIG_DIR with no
    fallback to the home directory and because the base file belongs to
    the base profile. A base run writes ~/.claude.json. A profile directory
    equal to the home directory is the base file.

    Args:
        artifact_base_dir: Isolated profile directory, or None for the base
            profile.

    Returns:
        Path to the .claude.json the run writes.
    """
    home_dir = get_real_user_home()
    if artifact_base_dir is not None and artifact_base_dir != home_dir:
        return artifact_base_dir / '.claude.json'
    return home_dir / '.claude.json'


def write_global_config(
    global_config: dict[str, Any],
    artifact_base_dir: Path | None = None,
) -> bool:
    """Write global configuration to the run's own .claude.json with universal deep merge.

    Writes exactly one file: ~/.claude/{cmd}/.claude.json when command-names
    creates an isolated environment, ~/.claude.json otherwise (see
    global_config_target_file()). An isolated run never touches the base
    file, so a configuration that deletes account keys signs out only the
    profile it installs.

    A .claude.json is a collaborative surface managed by the Claude Code
    CLI at runtime (OAuth tokens, per-project trust decisions,
    user-scoped MCP server approvals via /mcp approve, enabledPlugins,
    enabledMcpjsonServers, disabledMcpjsonServers, etc.). The writer
    MUST NOT destroy these contributions, so it delegates to
    _write_merged_json() -- exactly the same semantics as
    write_user_settings() and write_profile_settings_to_settings(): the
    target file is merged in place, and every array at every depth is
    unioned with the array that file already holds (existing elements
    first, new ones appended, duplicates dropped). A YAML array therefore
    only adds elements; a None value deletes the whole key.

    The YAML inheritance layer composes global-config before this writer
    runs and treats arrays the other way: with global-config in
    merge-keys, a child's array replaces the parent's at every depth
    (see _merge_config_key()).

    Args:
        global_config: Global config dict from YAML global-config section.
        artifact_base_dir: Isolated profile directory, or None for the base
            profile.

    Returns:
        True if the file was written successfully, False on failure.
    """
    config_file = global_config_target_file(artifact_base_dir)

    ok, _ = _write_merged_json(config_file, global_config)

    if ok:
        success(f'Wrote global config to {config_file}')
    else:
        warning(f'Failed to write global config to {config_file}')

    return ok


def _propagate_install_method(
    global_config: dict[str, Any] | None,
    primary_command_name: str | None,
    auto_injected_items: list[str],
) -> dict[str, Any] | None:
    """Propagate installMethod from the base ~/.claude.json into global_config.

    install_claude.py records installMethod only in the base ~/.claude.json,
    while isolated sessions resolve their global config exclusively through
    CLAUDE_CONFIG_DIR. Injecting the machine-baseline value into the
    global-config dict lets the Step 15 write carry it to the profile's own
    .claude.json, so the CLI sees the correct installation type in isolated
    sessions.

    WARN-but-Respect: a user-declared YAML global-config value wins with a
    warning when it differs from the baseline. When the base file or the key
    is absent, nothing is propagated (no fabrication).

    Args:
        global_config: Global config dict from the YAML global-config section,
            or None when the YAML lacks the section.
        primary_command_name: Primary command name when command-names creates
            an isolated environment, or None. Without isolation the base file
            already holds the value, so nothing is propagated.
        auto_injected_items: Mutable list recording auto-injected control
            values for the run. Propagation runs at the global-config write
            step, after the pre-confirmation summary has already rendered, so
            the propagated value is announced with an info message here and
            appended to this list for the run record rather than shown in that
            summary.

    Returns:
        The global_config dict with installMethod injected (created when the
        YAML lacks the section), or the unchanged input when nothing is
        propagated.
    """
    if not primary_command_name:
        return global_config

    base_config_file = get_real_user_home() / '.claude.json'
    if not base_config_file.exists():
        return global_config
    try:
        base_content = json.loads(base_config_file.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError, ValueError):
        return global_config
    if not isinstance(base_content, dict):
        return global_config

    base_value = base_content.get(INSTALL_METHOD_KEY)
    if base_value is None:
        return global_config

    if global_config is not None and INSTALL_METHOD_KEY in global_config:
        user_value = global_config[INSTALL_METHOD_KEY]
        if user_value != base_value:
            warning(
                f'User set global-config.{INSTALL_METHOD_KEY} to {user_value!r} '
                f'but the base {base_config_file} records {base_value!r}. '
                f'Respecting user value.',
            )
        return global_config

    if global_config is None:
        global_config = {}
    global_config[INSTALL_METHOD_KEY] = base_value
    auto_injected_items.append(f'global-config.{INSTALL_METHOD_KEY}: {base_value}')
    info(f'Propagating installMethod {base_value!r} into the isolated environment configuration')
    return global_config


# Constants for auto-update management
AUTO_UPDATE_KEY = 'autoUpdates'
AUTO_UPDATE_DISABLED_VALUE = False
DISABLE_AUTOUPDATER_KEY = 'DISABLE_AUTOUPDATER'
DISABLE_AUTOUPDATER_VALUE = '1'
DISABLE_UPDATES_KEY = 'DISABLE_UPDATES'
DISABLE_UPDATES_VALUE = '1'
# Environment controls a version pin writes, in injection order.
# DISABLE_AUTOUPDATER stops the background updater; DISABLE_UPDATES also
# blocks manual `claude update` and `claude install`. Both are written
# because Claude Code releases before 2.1.118 recognize only
# DISABLE_AUTOUPDATER.
AUTO_UPDATE_ENV_CONTROLS: tuple[tuple[str, str], ...] = (
    (DISABLE_AUTOUPDATER_KEY, DISABLE_AUTOUPDATER_VALUE),
    (DISABLE_UPDATES_KEY, DISABLE_UPDATES_VALUE),
)
# Values Claude Code reads as enabling an environment control (compared
# case-insensitively after trimming), so a user value in this set already
# matches the pin's intent.
ENV_CONTROL_TRUTHY_VALUES = frozenset({'1', 'true', 'yes', 'on'})

# Installation manifest written once per toolbox-managed profile: the base
# profile writes ~/.claude/manifest.json and each isolated profile writes
# ~/.claude/{cmd}/manifest.json. MANIFEST_VERSION_PIN_KEY records the Claude
# Code version that profile pinned, so any later run can tell whether another
# profile still needs the machine-global auto-update controls.
MANIFEST_FILENAME = 'manifest.json'
MANIFEST_VERSION_PIN_KEY = 'claude_code_version'

# Key recorded by install_claude.py in the base ~/.claude.json identifying how
# Claude Code was installed. Isolated profiles resolve their global config via
# CLAUDE_CONFIG_DIR with no fallback to the home directory, so the value must
# be propagated into ~/.claude/{cmd}/.claude.json for the CLI to see it there.
INSTALL_METHOD_KEY = 'installMethod'

# Constants for the claude.ai skill sync: a profile whose skills/ directory
# is a link into another profile must not let Claude Code sync claude.ai
# skills into it, because every file the sync writes lands in the source.
SKILLS_SYNC_KEY = 'syncClaudeAiSkills'
SKILLS_SYNC_DISABLED_VALUE = False

# Constants for IDE extension version management
IDE_AUTO_INSTALL_KEY = 'autoInstallIdeExtension'
IDE_AUTO_INSTALL_DISABLED_VALUE = False
IDE_SKIP_AUTO_INSTALL_KEY = 'CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL'
IDE_SKIP_AUTO_INSTALL_VALUE = '1'
# The environment controls that hold the one Claude Code binary this
# machine has: the two auto-update controls and the IDE extension control.
# They are machine-wide from any run, so an isolated run writes them to the
# OS environment while every other os-env-variables entry of that run goes
# to the profile's env loader files only. Every place that handles the
# three together reads this tuple.
MACHINE_WIDE_ENV_CONTROLS: tuple[str, ...] = (
    *(key for key, _ in AUTO_UPDATE_ENV_CONTROLS),
    IDE_SKIP_AUTO_INSTALL_KEY,
)
# The .claude.json controls a version pin sets to false; the Step 16 sweep
# removes a false value the YAML does not declare.
MACHINE_WIDE_JSON_CONTROLS: tuple[str, ...] = (AUTO_UPDATE_KEY, IDE_AUTO_INSTALL_KEY)
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
# VS Code Marketplace targetPlatform architecture identifiers by machine name
VSCODE_TARGET_PLATFORM_ARCHES = {
    'amd64': 'x64',
    'x86_64': 'x64',
    'arm64': 'arm64',
    'aarch64': 'arm64',
}
# Marker file identifying musl-based Alpine Linux, which requires the
# dedicated 'alpine' targetPlatform instead of the glibc 'linux' build
ALPINE_RELEASE_MARKER = Path('/etc/alpine-release')
# Magic prefixes used to validate downloaded VSIX payloads
GZIP_MAGIC = b'\x1f\x8b'
ZIP_MAGIC = b'PK\x03\x04'


class _ProfilePin(NamedTuple):
    """One profile manifest's answer to the machine-wide pin question.

    Attributes:
        name: Profile display name recorded in the manifest, None for the
            base profile.
        pinned: Whether the profile records a Claude Code version pin.
        undetermined: Whether the manifest exists but could not be read or
            parsed, leaving that profile's pin unknown.
        version: The pinned Claude Code version, None when the profile does
            not pin one or its pin is unknown.
    """

    name: str | None
    pinned: bool
    undetermined: bool
    version: str | None


# A manifest that exists but cannot be read or parsed carries no name and no
# readable pin, so it answers the pin question with "unknown" instead of "no".
_UNDETERMINED_PIN = _ProfilePin(name=None, pinned=False, undetermined=True, version=None)


class _ProfilePinScan(NamedTuple):
    """What the installed-profile manifests say about version pinning.

    Attributes:
        pinned_profiles: Sorted display names of the OTHER installed
            profiles that pin a Claude Code version ('base' for the base
            profile).
        undetermined: Whether any part of the registry could not be read,
            leaving at least one profile's pin unknown.
        pinned_versions: Sorted distinct Claude Code versions those
            profiles pin.
    """

    pinned_profiles: list[str]
    undetermined: bool
    pinned_versions: list[str]

    @property
    def other_profile_pinned(self) -> bool:
        """Whether another profile still needs the machine-global controls.

        An incomplete read counts as pinned: the controls are machine-global,
        so removing them on a registry this run could not read in full can
        break a pin it never saw.
        """
        return bool(self.pinned_profiles) or self.undetermined


def _read_profile_pin(manifest_path: Path) -> _ProfilePin | None:
    """Classify one profile manifest for the machine-wide pin question.

    Args:
        manifest_path: Path to a profile's manifest.json.

    Returns:
        The profile's pin state, _UNDETERMINED_PIN when the file exists but
        cannot be read or parsed as a JSON object, or None when no manifest
        exists at the path (no profile is recorded there).
    """
    try:
        raw = manifest_path.read_text(encoding='utf-8')
    except FileNotFoundError:
        return None
    except OSError:
        return _UNDETERMINED_PIN

    try:
        content = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return _UNDETERMINED_PIN
    if not isinstance(content, dict):
        return _UNDETERMINED_PIN

    name_raw = content.get('name')
    name = name_raw.strip() or None if isinstance(name_raw, str) else None
    pin = content.get(MANIFEST_VERSION_PIN_KEY)
    version = pin.strip() or None if isinstance(pin, str) else None
    return _ProfilePin(
        name=name,
        pinned=version is not None,
        undetermined=False,
        version=version,
    )


def _other_profile_pins(home_dir: Path, primary_command_name: str | None) -> _ProfilePinScan:
    """Read which installed profiles OTHER than this run's pin a Claude Code version.

    One machine has one Claude Code binary, so the controls that hold it at
    a pinned version (DISABLE_AUTOUPDATER, DISABLE_UPDATES, autoUpdates, and
    their IDE extension counterparts) are machine-global. A run may
    therefore remove them only when no installed profile still needs them.

    Every toolbox-managed profile records its own pin in a manifest: the
    base profile in ~/.claude/manifest.json, each isolated profile in
    ~/.claude/{cmd}/manifest.json. A manifest belongs to this run when its
    'name' field matches primary_command_name (None identifies the base
    profile), so a profile relocated by a user-set CLAUDE_CONFIG_DIR is
    recognized as its own rather than counted as another profile.

    An absent manifest records no profile and counts as unpinned, as does a
    manifest that carries no pin. A manifest or profile directory that
    exists but cannot be read leaves the answer undetermined, which the
    scan reports so the caller keeps the controls in force.

    Args:
        home_dir: User home directory.
        primary_command_name: This run's primary command name, or None when
            the run configures the base profile.

    Returns:
        The registry scan result.
    """
    claude_dir = home_dir / '.claude'
    manifest_paths = [claude_dir / MANIFEST_FILENAME]
    undetermined = False
    try:
        if claude_dir.is_dir():
            manifest_paths.extend(
                subdir / MANIFEST_FILENAME
                for subdir in sorted(claude_dir.iterdir())
                if subdir.is_dir()
            )
    except OSError:
        # The profile directories could not be listed, so an isolated
        # profile's pin may be invisible to this run.
        undetermined = True

    pinned: set[str] = set()
    versions: set[str] = set()
    for manifest_path in manifest_paths:
        profile = _read_profile_pin(manifest_path)
        if profile is None:
            continue
        if profile.undetermined:
            undetermined = True
            continue
        if profile.name == primary_command_name:
            continue  # This run's own profile
        if profile.pinned and profile.version is not None:
            pinned.add(profile.name or 'base')
            versions.add(profile.version)
    return _ProfilePinScan(sorted(pinned), undetermined, sorted(versions))


def _pinned_elsewhere_message(scan: _ProfilePinScan) -> str:
    """Explain why an unpinned run leaves the machine-global controls in place.

    Args:
        scan: Registry scan reporting other_profile_pinned as True.

    Returns:
        Info message naming the profiles that keep the controls in force,
        or stating that the registry could not be read in full.
    """
    if scan.pinned_profiles:
        names = ', '.join(f"'{name}'" for name in scan.pinned_profiles)
        reason = f'Another installed profile pins a Claude Code version ({names})'
    else:
        reason = (
            'An installed profile manifest could not be read, so a version '
            'pin on another profile cannot be ruled out'
        )
    return f'{reason}; auto-update and IDE extension controls are left in place.'


def _installed_claude_version() -> str | None:
    """Report the version of the Claude Code installation that actually runs.

    Resolves claude the way every other step does and runs 'claude
    --version'. A binary that is missing, cannot execute on this machine
    (corrupt file or architecture mismatch), times out, exits with a
    failure code, or prints no version is not a working installation, and
    None is returned for it. The version is extracted exactly as
    install_claude.py extracts it, so passing it back as the requested
    version matches the installed binary.

    Returns:
        The installed Claude Code version, or None without a working
        installation.
    """
    claude_path = find_command('claude')
    if claude_path is None:
        return None
    try:
        result = subprocess.run(
            [claude_path, '--version'],
            capture_output=True,
            encoding='utf-8',
            errors='replace',
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    match = re.search(r'(\d+\.\d+\.\d+)', result.stdout or '')
    return match.group(1) if match else None


class _ClaudeInstallDecision(NamedTuple):
    """What Step 1 installs for this run on the machine's one Claude Code binary.

    Attributes:
        version: Version Step 1 hands the installer, None for the latest
            release.
        kept: Whether version is the version already installed, so the
            installer leaves the binary where it is.
        reason: Why another profile's pin governs this unpinned run
            ('another installed profile pins a version' or 'a profile
            manifest could not be read'), None when it does not.
        note: Explanation to print with Step 1 and in the installation
            summary, None when there is nothing to explain.
        note_is_warning: Whether note is printed as a warning.
    """

    version: str | None
    kept: bool
    reason: str | None
    note: str | None
    note_is_warning: bool


def _decide_claude_install(
    claude_code_version_normalized: str | None,
    scan: _ProfilePinScan,
    *,
    installed_version: str | None,
) -> _ClaudeInstallDecision:
    """Decide what Step 1 installs on the one Claude Code binary this machine has.

    A pinned run installs its own pin, and an unpinned run on a machine
    where no other profile pins a version installs or upgrades to the
    latest release. An unpinned run while another installed profile pins
    a version (or a profile manifest could not be read) must not move the
    binary off that pin: a working installation is kept by requesting its
    own version, so the installer changes nothing about the version while
    still repairing what it always repairs, and a missing or non-working
    one is installed at the pinned version when exactly one is known. With
    no known pinned version, or several, no version can be chosen for the
    other profiles, and the latest release is installed with a warning.

    Args:
        claude_code_version_normalized: This run's pinned version, or None.
        scan: Registry scan of the OTHER installed profiles.
        installed_version: Version of the working Claude Code installation
            from _installed_claude_version(), None without one.

    Returns:
        The Step 1 decision.
    """
    if claude_code_version_normalized is not None or not scan.other_profile_pinned:
        return _ClaudeInstallDecision(
            version=claude_code_version_normalized, kept=False, reason=None, note=None, note_is_warning=False,
        )

    names = ', '.join(f"'{name}'" for name in scan.pinned_profiles)
    if scan.pinned_profiles:
        reason = 'another installed profile pins a version'
        context = f'Another installed profile pins a Claude Code version ({names})'
    else:
        reason = 'a profile manifest could not be read'
        context = (
            'An installed profile manifest could not be read, so a version '
            'pin on another profile cannot be ruled out'
        )
    unreadable = (
        ' An installed profile manifest could not be read, so another pin cannot be ruled out.'
        if scan.undetermined and scan.pinned_profiles
        else ''
    )

    if installed_version is not None:
        return _ClaudeInstallDecision(
            version=installed_version,
            kept=True,
            reason=reason,
            note=f'{context}; keeping the installed Claude Code {installed_version} instead of upgrading it.',
            note_is_warning=False,
        )

    if len(scan.pinned_versions) == 1:
        pinned = scan.pinned_versions[0]
        return _ClaudeInstallDecision(
            version=pinned,
            kept=False,
            reason=reason,
            note=(
                f'No working Claude Code installation was found; installing version {pinned}, '
                f'which another installed profile pins ({names}).{unreadable}'
            ),
            note_is_warning=scan.undetermined,
        )

    if scan.pinned_versions:
        cause = f"the installed profiles pin different versions ({', '.join(scan.pinned_versions)})"
    else:
        cause = 'an installed profile manifest could not be read'
    return _ClaudeInstallDecision(
        version=None,
        kept=False,
        reason=reason,
        note=f'No working Claude Code installation was found and {cause}; installing the latest release.',
        note_is_warning=True,
    )


def apply_auto_update_settings(
    claude_code_version_normalized: str | None,
    global_config: dict[str, Any] | None,
    user_settings: dict[str, Any] | None,
    os_env_variables: dict[str, str | None] | None,
    *,
    other_profile_pinned: bool,
) -> tuple[
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, str | None] | None,
    list[str],
    list[str],
]:
    """Apply automatic auto-update settings based on version pinning.

    When this run pins a specific version, blocks both the background
    updater and manual updates across all three available targets:
    autoUpdates in global-config, plus DISABLE_AUTOUPDATER and
    DISABLE_UPDATES in user-settings.env and os-env-variables. When
    nothing on the machine pins a version, removes the controls the YAML
    does not keep, whoever set them.
    When another installed profile pins a version, the machine-global
    controls stay in force and no removal is scheduled, because that
    profile shares the one Claude Code binary this machine has.

    Operates on in-memory dicts ONLY -- has no knowledge of command-names,
    file paths, or environment isolation. The existing write routing
    infrastructure handles which files get created.

    Args:
        claude_code_version_normalized: Pinned version string, or None for latest.
        global_config: Global config dict (may be None).
        user_settings: User settings dict (may be None).
        os_env_variables: OS-level environment variables dict (may be None).
        other_profile_pinned: Whether another installed profile pins a
            Claude Code version, as reported by
            _ProfilePinScan.other_profile_pinned.

    Returns:
        Tuple of (global_config, user_settings, os_env_variables,
        warnings, auto_injected_items).
    """
    warnings_list: list[str] = []
    auto_injected: list[str] = []

    if claude_code_version_normalized is not None:
        # Pinned version: inject auto-update disable controls
        global_config, user_settings, os_env_variables = (
            _inject_auto_update_controls(
                global_config, user_settings, os_env_variables,
                warnings_list, auto_injected,
            )
        )
    elif not other_profile_pinned:
        # Nothing on the machine pins a version: preserve user declarations,
        # schedule OS-level cleanup
        global_config, user_settings, os_env_variables = (
            _remove_auto_update_controls(
                global_config, user_settings, os_env_variables,
            )
        )

    return global_config, user_settings, os_env_variables, warnings_list, auto_injected


def _env_control_enabled(value: object) -> bool:
    """Report whether Claude Code reads an environment-control value as enabled.

    Args:
        value: User-declared value; None (a deletion request) is never enabled.

    Returns:
        True when the trimmed, lowercased value is in ENV_CONTROL_TRUTHY_VALUES.
    """
    return value is not None and str(value).strip().lower() in ENV_CONTROL_TRUTHY_VALUES


def _inject_auto_update_controls(
    global_config: dict[str, Any] | None,
    user_settings: dict[str, Any] | None,
    os_env_variables: dict[str, str | None] | None,
    warnings_list: list[str],
    auto_injected: list[str],
) -> tuple[
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, str | None] | None,
]:
    """Inject auto-update disable controls into all three target dicts.

    global-config receives autoUpdates; user-settings.env and
    os-env-variables each receive every AUTO_UPDATE_ENV_CONTROLS key, in
    tuple order. Injection is gated on key MEMBERSHIP, not on value, per
    key: an explicit user null (a YAML deletion request, legal in every
    target) is a user declaration and is respected with a warning
    (WARN-but-Respect), never overwritten. A user environment-control value
    Claude Code reads as enabled (any ENV_CONTROL_TRUTHY_VALUES spelling)
    already matches the intent and produces no warning.

    Returns:
        Tuple of (global_config, user_settings, os_env_variables) with
        controls injected into absent keys.
    """
    # Target 1: global_config.autoUpdates = False
    if global_config is None:
        global_config = {}
    if AUTO_UPDATE_KEY not in global_config:
        global_config[AUTO_UPDATE_KEY] = AUTO_UPDATE_DISABLED_VALUE
        auto_injected.append(f'global-config.{AUTO_UPDATE_KEY}: false')
    elif global_config[AUTO_UPDATE_KEY] == AUTO_UPDATE_DISABLED_VALUE:
        pass  # Already matches intent
    else:
        warnings_list.append(
            f'User set global-config.{AUTO_UPDATE_KEY} to {global_config[AUTO_UPDATE_KEY]!r} '
            f'(auto-update intent is {AUTO_UPDATE_DISABLED_VALUE!r} for pinned version). '
            f'Respecting user value.',
        )

    # Target 2: user_settings.env.<key> = "1" for each environment control
    if user_settings is None:
        user_settings = {}
    env_raw = user_settings.get('env')
    if not isinstance(env_raw, dict):
        env_raw = {}
        user_settings['env'] = env_raw
    env_section = cast(dict[str, Any], env_raw)
    for key, value in AUTO_UPDATE_ENV_CONTROLS:
        if key not in env_section:
            env_section[key] = value
            auto_injected.append(f'user-settings.env.{key}: "{value}"')
        elif _env_control_enabled(env_section[key]):
            pass  # Already matches intent
        else:
            warnings_list.append(
                f'User set user-settings.env.{key} to {env_section[key]!r} '
                f'(auto-update intent is {value!r} for pinned version). '
                f'Respecting user value.',
            )

    # Target 3: os_env_variables.<key> = "1" for each environment control
    if os_env_variables is None:
        os_env_variables = {}
    for key, value in AUTO_UPDATE_ENV_CONTROLS:
        if key not in os_env_variables:
            os_env_variables[key] = value
            auto_injected.append(f'os-env-variables.{key}: "{value}"')
        elif _env_control_enabled(os_env_variables[key]):
            pass  # Already matches intent
        else:
            warnings_list.append(
                f'User set os-env-variables.{key} to {os_env_variables[key]!r} '
                f'(auto-update intent is {value!r} for pinned version). '
                f'Respecting user value.',
            )

    return global_config, user_settings, os_env_variables


def _remove_auto_update_controls(
    global_config: dict[str, Any] | None,
    user_settings: dict[str, Any] | None,
    os_env_variables: dict[str, str | None] | None,
) -> tuple[
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, str | None] | None,
]:
    """Handle auto-update controls when nothing on the machine pins a version.

    Called only when neither this run nor any other installed profile pins
    a Claude Code version. Nothing has been auto-injected into the
    in-memory dicts, so every control key present comes from the user's
    YAML and is PRESERVED (the removal counterpart of WARN-but-Respect on
    the write side). On-disk controls the YAML does not keep are removed
    by the Step 16 stale-controls sweep instead, whoever set them.

    The OS-level variables have no filesystem sweep, so for each
    AUTO_UPDATE_ENV_CONTROLS key the user does not declare in
    os-env-variables, a deletion entry (None) is scheduled here and
    set_all_os_env_variables() removes the OS-level variable, whoever set
    it. Deleting an absent variable is a safe no-op on all platforms.

    Returns:
        Tuple of (global_config, user_settings, os_env_variables) with the
        OS-level deletion entries scheduled.
    """
    if os_env_variables is None:
        os_env_variables = {}
    for key, _ in AUTO_UPDATE_ENV_CONTROLS:
        if key not in os_env_variables:
            os_env_variables[key] = None

    return global_config, user_settings, os_env_variables


def _collect_user_declared_control_keys(
    user_settings: dict[str, Any] | None,
    *,
    global_config: dict[str, Any] | None,
) -> frozenset[str]:
    """Identify which managed control keys the resolved YAML itself declares.

    Must be called BEFORE apply_auto_update_settings() and
    apply_ide_extension_settings() so that auto-injected values are not
    mistaken for user declarations. The Step 16 unpinned sweep preserves
    an environment key user-settings.env sets to a value in settings.json
    files and a global-config key the YAML sets to false in .claude.json
    files (the removal counterpart of WARN-but-Respect on the write side).
    A null environment key is a deletion request, and false is the only
    value the .claude.json sweeps remove, so neither a null nor a
    global-config value other than false keeps the sweeps from clearing
    stale copies.

    Args:
        user_settings: User settings dict from the YAML user-settings section.
        global_config: Global config dict from the YAML global-config section.

    Returns:
        Frozen set containing each managed environment control key (every
        AUTO_UPDATE_ENV_CONTROLS key plus CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL)
        that user-settings.env sets to a non-null value and each managed
        global-config key (autoUpdates, autoInstallIdeExtension) that
        global-config sets to false.
    """
    declared: set[str] = set()
    env_section = user_settings.get('env') if user_settings is not None else None
    for key in MACHINE_WIDE_ENV_CONTROLS:
        if isinstance(env_section, dict) and env_section.get(key) is not None:
            declared.add(key)
    for key in MACHINE_WIDE_JSON_CONTROLS:
        if global_config is not None and global_config.get(key) is False:
            declared.add(key)
    return frozenset(declared)


def _profile_control_files(home_dir: Path, profile_dir: Path | None) -> tuple[Path, Path]:
    """Resolve the settings.json and .claude.json a profile owns.

    Args:
        home_dir: User home directory.
        profile_dir: Isolated profile directory, or None for the base
            profile.

    Returns:
        The (settings.json, .claude.json) pair: ~/.claude/settings.json and
        ~/.claude.json for the base profile, the two files inside the
        profile directory for an isolated one.
    """
    if profile_dir is None:
        return home_dir / '.claude' / 'settings.json', home_dir / '.claude.json'
    return profile_dir / 'settings.json', profile_dir / '.claude.json'


def _stale_control_keys(user_declared_keys: frozenset[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split the managed controls into the keys an unpinned sweep removes.

    Args:
        user_declared_keys: Control keys the sweeps keep, as returned by
            _collect_user_declared_control_keys().

    Returns:
        The environment control keys a settings.json sweep removes and the
        .claude.json control keys whose false value a .claude.json sweep
        removes, each decided independently of the others.
    """
    env_keys = tuple(key for key in MACHINE_WIDE_ENV_CONTROLS if key not in user_declared_keys)
    json_keys = tuple(key for key in MACHINE_WIDE_JSON_CONTROLS if key not in user_declared_keys)
    return env_keys, json_keys


def _present_env_controls(settings_path: Path, keys: tuple[str, ...]) -> tuple[str, ...]:
    """Report which of the given environment controls a settings.json holds.

    Args:
        settings_path: Path to a settings.json file.
        keys: Environment control keys to look for.

    Returns:
        The keys present in the file's env object, in the given order;
        empty for a missing, unreadable, or non-object file.
    """
    content = _read_json_object(settings_path)
    if not content:
        return ()
    env_section = content.get('env')
    if not isinstance(env_section, dict):
        return ()
    return tuple(key for key in keys if key in env_section)


def _present_false_controls(claude_json_path: Path, keys: tuple[str, ...]) -> tuple[str, ...]:
    """Report which of the given .claude.json controls a file holds as false.

    Args:
        claude_json_path: Path to a .claude.json file.
        keys: Control keys whose false value counts.

    Returns:
        The keys the file holds with the value false, in the given order;
        empty for a missing, unreadable, or non-object file. A true value is
        a user preference and never counts.
    """
    content = _read_json_object(claude_json_path)
    if not content:
        return ()
    return tuple(key for key in keys if content.get(key) is False)


def find_stale_controls_in_other_profiles(
    home_dir: Path,
    *,
    profile_dir: Path | None,
    machine_pinned: bool,
    user_declared_keys: frozenset[str],
) -> list[StaleControlCopy]:
    """List the stale update controls other installed profiles hold.

    The Step 16 sweeps edit only the running profile's files, so a control
    a previous pinned run left in another profile stays where it is. This
    read-only scan names such copies under the same two gates the sweeps
    apply -- nothing counts while any installed profile pins a version, and
    a key the current YAML declares is not stale -- so the report lists
    exactly what the sweeps would have removed had the file belonged to the
    running profile. Nothing is edited; re-running the owning profile's
    install removes the copies.

    Args:
        home_dir: User home directory.
        profile_dir: The running profile's directory, or None for the base
            profile.
        machine_pinned: Whether any installed profile pins a Claude Code
            version -- this run's own pin or another profile's.
        user_declared_keys: Control keys the sweeps keep, as returned by
            _collect_user_declared_control_keys().

    Returns:
        One entry per file holding at least one stale control, base profile
        first, then the isolated profiles in directory order.
    """
    if machine_pinned:
        return []

    env_keys, json_keys = _stale_control_keys(user_declared_keys)
    claude_dir = home_dir / '.claude'
    own_dir_key = _normalize_config_dir_key(str(profile_dir if profile_dir is not None else claude_dir))

    profiles: list[tuple[str, Path]] = [('base', claude_dir)]
    try:
        if claude_dir.is_dir():
            profiles.extend(
                (subdir.name, subdir)
                for subdir in sorted(claude_dir.iterdir())
                if subdir.is_dir()
            )
    except OSError:
        pass  # Unlisted profiles cannot be reported; the sweeps never touch them

    found: list[StaleControlCopy] = []
    for name, directory in profiles:
        if _normalize_config_dir_key(str(directory)) == own_dir_key:
            continue
        settings_path, claude_json_path = _profile_control_files(
            home_dir, None if name == 'base' else directory,
        )
        env_present = _present_env_controls(settings_path, env_keys)
        if env_present:
            found.append(StaleControlCopy(name, settings_path, env_present))
        json_present = _present_false_controls(claude_json_path, json_keys)
        if json_present:
            found.append(StaleControlCopy(name, claude_json_path, json_present))
    return found


def _stale_control_copy_line(copy: StaleControlCopy) -> str:
    """Render one stale-control report entry.

    Args:
        copy: The stale controls found in another profile's file.

    Returns:
        A one-line description naming the profile, the file, and the keys.
    """
    return f'{copy.profile}: {copy.file} ({", ".join(copy.keys)}) -- re-run with --profile {copy.profile}'


def _rerooted_path_line(item: RerootedPath) -> str:
    """Render one re-rooted path of the installation summary.

    Args:
        item: The rewritten configuration value.

    Returns:
        A one-line description naming the section, the dependency platform
        or settings key, the original value and the rewritten one.
    """
    if item.section == 'dependencies':
        where = f'{item.section} [{item.label}]'
    elif item.label:
        where = f'{item.section} {item.label}'
    else:
        where = item.section
    return f'{where}: {item.original} -> {item.rewritten}'


def _linked_download_line(dest: str, entry: str, source: str) -> str:
    """Render one files-to-download destination a link provides.

    Args:
        dest: The destination as the run resolves it (re-rooted into the
            profile when it named the base config home).
        entry: The linked entry the destination lies inside.
        source: The display name of the profile the entry is linked from.

    Returns:
        A one-line description naming the destination, the entry and the
        source profile; Step 4 prints the same explanation when it skips
        the download.
    """
    return f'{dest}: {entry}/ is linked from profile "{source}"'


STALE_CONTROLS_RERUN_NOTE = (
    'This run edits only its own profile; re-run each listed profile with --profile <name> to remove them.'
)


def cleanup_stale_auto_update_controls(
    home_dir: Path,
    machine_pinned: bool,
    *,
    user_declared_keys: frozenset[str],
    profile_dir: Path | None,
) -> None:
    """Remove stale auto-update controls from the running profile's files.

    Implements write-remove symmetry inside one profile: a pinned run writes
    its controls into the profile's own files, and an unpinned run removes
    them from the same two files -- ~/.claude/settings.json and
    ~/.claude.json for the base profile, settings.json and .claude.json
    inside the profile directory for an isolated one. Other profiles' files
    are never edited; find_stale_controls_in_other_profiles() reports the
    copies they hold. Three guards bound the sweep:

    - The sweep runs only when NO installed profile pins a version. The
      controls are machine-global, so while this run or any other profile
      recorded in the profile manifests pins a version, every location
      keeps its controls.
    - settings.json additionally keeps each AUTO_UPDATE_ENV_CONTROLS key
      (DISABLE_AUTOUPDATER, DISABLE_UPDATES) the current YAML sets to a
      non-null value in user-settings.env (the removal counterpart of
      WARN-but-Respect on the write side). Each key is decided
      independently: declaring one never keeps or removes the other.
    - .claude.json likewise keeps autoUpdates: false when the current YAML
      sets it to false in global-config.

    Called AFTER all write steps in main() as a post-write cleanup pass.

    Args:
        home_dir: User home directory.
        machine_pinned: Whether any installed profile pins a Claude Code
            version -- this run's own pin or another profile's.
        user_declared_keys: Control keys the sweep keeps, as returned by
            _collect_user_declared_control_keys().
        profile_dir: The running profile's directory, or None for the base
            profile.
    """
    if machine_pinned:
        return

    settings_path, claude_json_path = _profile_control_files(home_dir, profile_dir)
    stale_env_keys = tuple(
        key for key, _ in AUTO_UPDATE_ENV_CONTROLS if key not in user_declared_keys
    )

    if stale_env_keys:
        _cleanup_settings_json_env_controls(settings_path, stale_env_keys)

    if AUTO_UPDATE_KEY not in user_declared_keys:
        _cleanup_claude_json_auto_updates(claude_json_path)


def _cleanup_settings_json_env_controls(settings_path: Path, keys: tuple[str, ...]) -> None:
    """Remove stale environment controls from a settings.json file via merge.

    Every listed key present in the file's env section is deleted in one
    null-as-delete merge write, and an env section left empty is dropped.

    Args:
        settings_path: Path to the settings.json file.
        keys: Environment control keys to remove.
    """
    if not settings_path.exists():
        return
    try:
        content = json.loads(settings_path.read_text(encoding='utf-8'))
        if not isinstance(content, dict):
            return
        env_section = content.get('env')
        if not isinstance(env_section, dict):
            return
        present = [key for key in keys if key in env_section]
        if not present:
            return
        # Use _write_merged_json with null-as-delete
        cleanup_dict: dict[str, Any] = {'env': dict.fromkeys(present)}
        ok, merged = _write_merged_json(settings_path, cleanup_dict)
        if ok and merged.get('env') == {}:
            # Clean empty env: {} after removal
            merged.pop('env')
            settings_path.write_text(
                json.dumps(merged, indent=2, ensure_ascii=False) + '\n',
                encoding='utf-8',
            )
        if ok:
            info(f'Cleaned stale {", ".join(present)} from {settings_path}')
    except (OSError, json.JSONDecodeError, ValueError):
        pass  # Best-effort cleanup; non-fatal


def _cleanup_claude_json_auto_updates(claude_json_path: Path) -> None:
    """Remove stale autoUpdates: false from a .claude.json file.

    Only removes a false value, whoever set it (the caller skips this
    sweep when the YAML sets the key to false in global-config).
    Preserves autoUpdates: true (explicit user preference).
    """
    if not claude_json_path.exists():
        return
    try:
        content = json.loads(claude_json_path.read_text(encoding='utf-8'))
        if isinstance(content, dict) and content.get(AUTO_UPDATE_KEY) is False:
            # Use _write_merged_json with null-as-delete
            cleanup_dict: dict[str, Any] = {AUTO_UPDATE_KEY: None}
            ok, _ = _write_merged_json(claude_json_path, cleanup_dict)
            if ok:
                info(f'Cleaned stale {AUTO_UPDATE_KEY}: false from {claude_json_path}')
    except (OSError, json.JSONDecodeError, ValueError):
        pass  # Best-effort cleanup; non-fatal


def _run_stale_controls_cleanup(
    machine_pinned: bool,
    user_declared_keys: frozenset[str],
    profile_dir: Path | None,
) -> list[StaleControlCopy]:
    """Execute Step 16: cleanup stale auto-update and IDE extension controls.

    Sweeps the running profile's own settings.json and .claude.json, then
    reports -- without editing -- the stale controls other installed
    profiles still hold.

    Args:
        machine_pinned: Whether any installed profile pins a Claude Code
            version -- this run's own pin or another profile's.
        user_declared_keys: Control keys both sweeps keep, computed before
            injection by _collect_user_declared_control_keys().
        profile_dir: The running profile's directory, or None for the base
            profile.

    Returns:
        The stale controls found in other profiles, for the final summary.
    """
    print()
    print(f'{Colors.CYAN}Step 16: Cleaning stale auto-update and IDE extension controls...{Colors.NC}')
    home = get_real_user_home()
    cleanup_stale_auto_update_controls(
        home_dir=home,
        machine_pinned=machine_pinned,
        user_declared_keys=user_declared_keys,
        profile_dir=profile_dir,
    )
    cleanup_stale_ide_extension_controls(
        home_dir=home,
        machine_pinned=machine_pinned,
        user_declared_keys=user_declared_keys,
        profile_dir=profile_dir,
    )
    stale_elsewhere = find_stale_controls_in_other_profiles(
        home,
        profile_dir=profile_dir,
        machine_pinned=machine_pinned,
        user_declared_keys=user_declared_keys,
    )
    if stale_elsewhere:
        warning('Stale update controls remain in other profiles (not edited by this run):')
        for copy in stale_elsewhere:
            warning(f'  {_stale_control_copy_line(copy)}')
        warning(f'  {STALE_CONTROLS_RERUN_NOTE}')
    return stale_elsewhere


def apply_ide_extension_settings(
    claude_code_version_normalized: str | None,
    global_config: dict[str, Any] | None,
    user_settings: dict[str, Any] | None,
    os_env_variables: dict[str, str | None] | None,
    *,
    other_profile_pinned: bool,
) -> tuple[
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, str | None] | None,
    list[str],
    list[str],
]:
    """Apply automatic IDE extension auto-install settings based on version pinning.

    When this run pins a specific version, disables IDE extension
    auto-installation across all three available targets. When nothing on
    the machine pins a version, removes the controls the YAML does not
    keep, whoever set them. When
    another installed profile pins a version, the machine-global controls
    stay in force and no removal is scheduled, because that profile shares
    the one Claude Code installation this machine has.

    Operates on in-memory dicts ONLY -- has no knowledge of command-names,
    file paths, or environment isolation. The existing write routing
    infrastructure handles which files get created.

    Args:
        claude_code_version_normalized: Pinned version string, or None for latest.
        global_config: Global config dict (may be None).
        user_settings: User settings dict (may be None).
        os_env_variables: OS-level environment variables dict (may be None).
        other_profile_pinned: Whether another installed profile pins a
            Claude Code version, as reported by
            _ProfilePinScan.other_profile_pinned.

    Returns:
        Tuple of (global_config, user_settings, os_env_variables,
        warnings, auto_injected_items).
    """
    warnings_list: list[str] = []
    auto_injected: list[str] = []

    if claude_code_version_normalized is not None:
        # Pinned version: inject IDE extension auto-install disable controls
        global_config, user_settings, os_env_variables = (
            _inject_ide_extension_controls(
                global_config, user_settings, os_env_variables,
                warnings_list, auto_injected,
            )
        )
    elif not other_profile_pinned:
        # Nothing on the machine pins a version: preserve user declarations,
        # schedule OS-level cleanup
        global_config, user_settings, os_env_variables = (
            _remove_ide_extension_controls(
                global_config, user_settings, os_env_variables,
            )
        )

    return global_config, user_settings, os_env_variables, warnings_list, auto_injected


def _inject_ide_extension_controls(
    global_config: dict[str, Any] | None,
    user_settings: dict[str, Any] | None,
    os_env_variables: dict[str, str | None] | None,
    warnings_list: list[str],
    auto_injected: list[str],
) -> tuple[
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, str | None] | None,
]:
    """Inject IDE extension auto-install disable controls into all three target dicts.

    Injection is gated on key MEMBERSHIP, not on value: an explicit user
    null (a YAML deletion request, legal in every target) is a user
    declaration and is respected with a warning (WARN-but-Respect), never
    overwritten. A user CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL value Claude Code
    reads as enabled (any ENV_CONTROL_TRUTHY_VALUES spelling) already
    matches the intent and produces no warning.

    Returns:
        Tuple of (global_config, user_settings, os_env_variables) with
        controls injected into absent keys.
    """
    # Target 1: global_config.autoInstallIdeExtension = False
    if global_config is None:
        global_config = {}
    if IDE_AUTO_INSTALL_KEY not in global_config:
        global_config[IDE_AUTO_INSTALL_KEY] = IDE_AUTO_INSTALL_DISABLED_VALUE
        auto_injected.append(f'global-config.{IDE_AUTO_INSTALL_KEY}: false')
    elif global_config[IDE_AUTO_INSTALL_KEY] == IDE_AUTO_INSTALL_DISABLED_VALUE:
        pass  # Already matches intent
    else:
        warnings_list.append(
            f'User set global-config.{IDE_AUTO_INSTALL_KEY} to {global_config[IDE_AUTO_INSTALL_KEY]!r} '
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
    if IDE_SKIP_AUTO_INSTALL_KEY not in env_section:
        env_section[IDE_SKIP_AUTO_INSTALL_KEY] = IDE_SKIP_AUTO_INSTALL_VALUE
        auto_injected.append(f'user-settings.env.{IDE_SKIP_AUTO_INSTALL_KEY}: "{IDE_SKIP_AUTO_INSTALL_VALUE}"')
    elif _env_control_enabled(env_section[IDE_SKIP_AUTO_INSTALL_KEY]):
        pass  # Already matches intent
    else:
        warnings_list.append(
            f'User set user-settings.env.{IDE_SKIP_AUTO_INSTALL_KEY} to {env_section[IDE_SKIP_AUTO_INSTALL_KEY]!r} '
            f'(auto-install intent is {IDE_SKIP_AUTO_INSTALL_VALUE!r} for pinned version). '
            f'Respecting user value.',
        )

    # Target 3: os_env_variables.CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL = "1"
    if os_env_variables is None:
        os_env_variables = {}
    if IDE_SKIP_AUTO_INSTALL_KEY not in os_env_variables:
        os_env_variables[IDE_SKIP_AUTO_INSTALL_KEY] = IDE_SKIP_AUTO_INSTALL_VALUE
        auto_injected.append(f'os-env-variables.{IDE_SKIP_AUTO_INSTALL_KEY}: "{IDE_SKIP_AUTO_INSTALL_VALUE}"')
    elif _env_control_enabled(os_env_variables[IDE_SKIP_AUTO_INSTALL_KEY]):
        pass  # Already matches intent
    else:
        warnings_list.append(
            f'User set os-env-variables.{IDE_SKIP_AUTO_INSTALL_KEY} to {os_env_variables[IDE_SKIP_AUTO_INSTALL_KEY]!r} '
            f'(auto-install intent is {IDE_SKIP_AUTO_INSTALL_VALUE!r} for pinned version). '
            f'Respecting user value.',
        )

    return global_config, user_settings, os_env_variables


def _remove_ide_extension_controls(
    global_config: dict[str, Any] | None,
    user_settings: dict[str, Any] | None,
    os_env_variables: dict[str, str | None] | None,
) -> tuple[
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, str | None] | None,
]:
    """Handle IDE extension controls when nothing on the machine pins a version.

    Called only when neither this run nor any other installed profile pins
    a Claude Code version. Nothing has been auto-injected into the
    in-memory dicts, so every control key present comes from the user's
    YAML and is PRESERVED (the removal counterpart of WARN-but-Respect on
    the write side). On-disk controls the YAML does not keep are removed
    by the Step 16 stale-controls sweep instead, whoever set them.

    The OS-level variable has no filesystem sweep, so when the user does
    not declare CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL in os-env-variables, a
    deletion entry (None) is scheduled here and set_all_os_env_variables()
    removes the OS-level variable, whoever set it. Deleting an absent
    variable is a safe no-op on all platforms.

    Returns:
        Tuple of (global_config, user_settings, os_env_variables) with the
        OS-level deletion entry scheduled.
    """
    if os_env_variables is None:
        os_env_variables = {}
    if IDE_SKIP_AUTO_INSTALL_KEY not in os_env_variables:
        os_env_variables[IDE_SKIP_AUTO_INSTALL_KEY] = None

    return global_config, user_settings, os_env_variables


def apply_skills_sync_settings(
    user_settings: dict[str, Any] | None,
    *,
    links_skills: bool,
) -> tuple[dict[str, Any] | None, list[str], list[str]]:
    """Switch the claude.ai skill sync off in a profile whose skills/ is a link.

    The sync writes into the skills directory of the profile it runs in; when
    that directory is a link, every file would land in the source profile.
    Injection is gated on key MEMBERSHIP (WARN-but-Respect): a value the
    configuration declares, a null included, is kept, and a value other than
    the disabled one produces a warning.

    Args:
        user_settings: The resolved user-settings section, or None.
        links_skills: Whether this run links the skills entry.

    Returns:
        Tuple of (user_settings, warnings, auto_injected_items); the first is
        unchanged when nothing is linked.
    """
    if not links_skills:
        return user_settings, [], []
    if user_settings is None:
        user_settings = {}
    if SKILLS_SYNC_KEY not in user_settings:
        user_settings[SKILLS_SYNC_KEY] = SKILLS_SYNC_DISABLED_VALUE
        return user_settings, [], [f'user-settings.{SKILLS_SYNC_KEY}: false']
    if user_settings[SKILLS_SYNC_KEY] == SKILLS_SYNC_DISABLED_VALUE:
        return user_settings, [], []
    return user_settings, [
        f'User set user-settings.{SKILLS_SYNC_KEY} to {user_settings[SKILLS_SYNC_KEY]!r} '
        f'(linked skills intent is {SKILLS_SYNC_DISABLED_VALUE!r}). Respecting user value.',
    ], []


def _cleanup_claude_json_ide_auto_install(claude_json_path: Path) -> None:
    """Remove stale autoInstallIdeExtension: false from a .claude.json file.

    Only removes a false value, whoever set it (the caller skips this
    sweep when the YAML sets the key to false in global-config).
    Preserves autoInstallIdeExtension: true (explicit user preference).
    """
    if not claude_json_path.exists():
        return
    try:
        content = json.loads(claude_json_path.read_text(encoding='utf-8'))
        if isinstance(content, dict) and content.get(IDE_AUTO_INSTALL_KEY) is False:
            # Use _write_merged_json with null-as-delete
            cleanup_dict: dict[str, Any] = {IDE_AUTO_INSTALL_KEY: None}
            ok, _ = _write_merged_json(claude_json_path, cleanup_dict)
            if ok:
                info(f'Cleaned stale {IDE_AUTO_INSTALL_KEY}: false from {claude_json_path}')
    except (OSError, json.JSONDecodeError, ValueError):
        pass  # Best-effort cleanup; non-fatal


def cleanup_stale_ide_extension_controls(
    home_dir: Path,
    machine_pinned: bool,
    *,
    user_declared_keys: frozenset[str],
    profile_dir: Path | None,
) -> None:
    """Remove stale IDE extension auto-install controls from the running profile's files.

    Implements write-remove symmetry inside one profile, exactly like
    cleanup_stale_auto_update_controls(): the sweep edits only the
    settings.json and .claude.json the running profile owns and never
    another profile's files. Two guards bound the sweep:

    - The sweep runs only when NO installed profile pins a version. The
      controls are machine-global, so while this run or any other profile
      recorded in the profile manifests pins a version, every location
      keeps its controls.
    - settings.json additionally keeps CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL
      when the current YAML sets it to a non-null value in user-settings.env,
      and .claude.json keeps autoInstallIdeExtension: false when the YAML
      sets it to false in global-config (the removal counterpart of
      WARN-but-Respect on the write side).

    Called AFTER all write steps in main() as a post-write cleanup pass.

    Args:
        home_dir: User home directory.
        machine_pinned: Whether any installed profile pins a Claude Code
            version -- this run's own pin or another profile's.
        user_declared_keys: Control keys the sweep keeps, as returned by
            _collect_user_declared_control_keys().
        profile_dir: The running profile's directory, or None for the base
            profile.
    """
    if machine_pinned:
        return

    settings_path, claude_json_path = _profile_control_files(home_dir, profile_dir)

    if IDE_SKIP_AUTO_INSTALL_KEY not in user_declared_keys:
        _cleanup_settings_json_env_controls(settings_path, (IDE_SKIP_AUTO_INSTALL_KEY,))

    if IDE_AUTO_INSTALL_KEY not in user_declared_keys:
        _cleanup_claude_json_ide_auto_install(claude_json_path)


def _vscode_target_platform() -> str | None:
    """Compute the VS Code Marketplace targetPlatform identifier for the host.

    The Claude Code extension is platform-specific: the marketplace hosts a
    separate VSIX per OS/architecture pair, and a download URL without the
    targetPlatform query parameter returns an arbitrary platform's build.

    Returns:
        Identifier in the form '{os}-{arch}' (e.g. 'win32-x64',
        'darwin-arm64', 'linux-arm64', 'alpine-x64'), or None when the host
        OS or architecture has no known marketplace identifier.
    """
    arch = VSCODE_TARGET_PLATFORM_ARCHES.get(platform.machine().lower())
    if arch is None:
        return None

    if sys.platform == 'win32':
        os_name = 'win32'
    elif sys.platform == 'darwin':
        os_name = 'darwin'
    elif sys.platform.startswith('linux'):
        os_name = 'alpine' if ALPINE_RELEASE_MARKER.exists() else 'linux'
    else:
        return None

    return f'{os_name}-{arch}'


def _vscode_well_known_locations(
    platform_name: str | None = None,
    home: Path | None = None,
    localappdata: str | None = None,
) -> list[tuple[str, Path]]:
    """Return (cli_name, path) candidates for VS Code family CLIs at well-known locations.

    Covers installs whose CLI shims are not on PATH: macOS app bundles
    (drag-and-drop installs do not register the 'code' CLI on PATH), Linux
    deb/rpm, snap, and Flatpak layouts, and the default Windows per-user
    install directory. Candidate paths are returned without checking
    existence; the caller filters.

    Args:
        platform_name: sys.platform-style identifier; defaults to sys.platform.
        home: User home directory; defaults to get_real_user_home().
        localappdata: Windows LOCALAPPDATA directory; defaults to the env var.

    Returns:
        List of (cli_name, candidate_path) tuples for the given platform.
    """
    if platform_name is None:
        platform_name = sys.platform
    if home is None:
        home = get_real_user_home()

    candidates: list[tuple[str, Path]] = []
    if platform_name == 'darwin':
        # The CLI shim inside each app bundle is named after the CLI itself
        mac_bundles = (
            ('code', 'Visual Studio Code.app'),
            ('code-insiders', 'Visual Studio Code - Insiders.app'),
            ('cursor', 'Cursor.app'),
            ('windsurf', 'Windsurf.app'),
            ('codium', 'VSCodium.app'),
        )
        for root in (Path('/Applications'), home / 'Applications'):
            for cli_name, bundle in mac_bundles:
                candidates.append((cli_name, root / bundle / 'Contents' / 'Resources' / 'app' / 'bin' / cli_name))
    elif platform_name.startswith('linux'):
        # Flatpak exports the launcher under the app ID, not as 'code'
        flatpak_export = Path('exports') / 'bin' / 'com.visualstudio.code'
        candidates.extend([
            ('code', Path('/usr/bin/code')),
            ('code', Path('/usr/share/code/bin/code')),
            ('code', Path('/snap/bin/code')),
            ('code', Path('/var/lib/flatpak') / flatpak_export),
            ('code', home / '.local' / 'share' / 'flatpak' / flatpak_export),
        ])
    elif platform_name == 'win32':
        if localappdata is None:
            localappdata = os.environ.get('LOCALAPPDATA', '')
        if localappdata:
            candidates.append(('code', Path(localappdata) / 'Programs' / 'Microsoft VS Code' / 'bin' / 'code.cmd'))
    return candidates


def _detect_vscode_family_ides() -> list[tuple[str, str]]:
    """Detect installed VS Code family IDEs.

    Checks PATH via shutil.which first, then probes platform-specific
    well-known install locations for installs whose CLI shim is not on PATH.
    Deduplicates by CLI name, keeping the first hit.

    Returns:
        List of (cli_name, cli_path) tuples for each detected IDE.
    """
    detected: dict[str, str] = {}
    for cli_name in VSCODE_FAMILY_CLI_NAMES:
        cli_path = shutil.which(cli_name)
        if cli_path:
            detected[cli_name] = cli_path
    for cli_name, candidate in _vscode_well_known_locations():
        if cli_name not in detected and candidate.is_file():
            detected[cli_name] = str(candidate)
    return list(detected.items())


def _vsix_manifest_target_platform(archive: zipfile.ZipFile) -> str | None:
    """Extract the TargetPlatform attribute from a VSIX manifest, if declared.

    Platform-specific VSIX builds declare TargetPlatform on the Identity
    element of extension.vsixmanifest; universal builds omit it.

    Args:
        archive: Open VSIX zip archive.

    Returns:
        The declared targetPlatform identifier, or None when absent.
    """
    try:
        with archive.open('extension.vsixmanifest') as manifest_file:
            manifest_text = manifest_file.read().decode('utf-8', errors='replace')
    except KeyError:
        return None
    match = re.search(r'TargetPlatform="([^"]*)"', manifest_text)
    return match.group(1) if match else None


def _bundled_vsix_matches(vsix_file: Path, version: str, target_platform: str | None) -> bool:
    """Check whether a bundled VSIX matches the pinned version and host platform.

    Reads extension/package.json inside the VSIX (a zip archive) and requires
    its version to equal the pinned version. When the VSIX manifest declares
    a TargetPlatform, it must equal the host targetPlatform. Unreadable or
    malformed archives are rejected.

    Args:
        vsix_file: Path to the candidate VSIX file.
        version: Pinned Claude Code version string.
        target_platform: Host targetPlatform identifier, or None when unknown.

    Returns:
        True when the VSIX is safe to install for this version and host.
    """
    try:
        with zipfile.ZipFile(vsix_file) as archive:
            with archive.open('extension/package.json') as package_file:
                package_data = json.loads(package_file.read().decode('utf-8'))
            if package_data.get('version') != version:
                return False
            manifest_platform = _vsix_manifest_target_platform(archive)
            return manifest_platform is None or manifest_platform == target_platform
    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
        return False


def _normalize_vsix_payload(data: bytes) -> bytes | None:
    """Normalize a downloaded VSIX payload to raw zip bytes.

    The marketplace /vspackage endpoint serves gzip-compressed bodies even
    when the request sends no Accept-Encoding header, and urllib does not
    transparently decompress. Decompresses gzip payloads and validates the
    zip magic prefix.

    Args:
        data: Raw response body from a VSIX download URL.

    Returns:
        Valid VSIX zip bytes, or None when the payload is not a VSIX archive.
    """
    if data.startswith(GZIP_MAGIC):
        # Corrupt deflate streams raise zlib.error, which is not an OSError
        try:
            data = gzip.decompress(data)
        except (OSError, EOFError, zlib.error):
            return None
    if not data.startswith(ZIP_MAGIC):
        return None
    return data


def install_ide_extensions(
    version: str,
) -> bool:
    """Install pinned-version IDE extensions into all detected VS Code family IDEs.

    Uses a three-tier fallback chain:
    1. Bundled VSIX from CLI package tree, used only when its embedded
       version matches the pinned version (and its declared targetPlatform,
       if any, matches the host)
    2. Platform-specific VSIX download from the marketplace CDN
       (auto-update disabled by VS Code v1.92+); skipped when the host
       targetPlatform is unknown
    3. Marketplace @version syntax as last resort (with warning about
       auto-update); the IDE resolves its own targetPlatform

    When every Tier 2 download URL returns HTTP 404, the pinned version has
    no matching extension in the marketplace: installation is skipped with a
    warning and the IDEs keep their current extension.

    Non-fatal: returns False on failure but does not raise.

    Args:
        version: Pinned Claude Code version string (e.g. "2.1.92").

    Returns:
        True if at least one IDE had the extension installed successfully,
        if no IDEs were detected (no-op success), or if the pinned version
        has no matching marketplace extension (skip with warning).
    """
    detected_ides = _detect_vscode_family_ides()
    if not detected_ides:
        info('No VS Code family IDEs detected, skipping extension installation')
        return True

    ide_names = ', '.join(name for name, _ in detected_ides)
    info(f'Detected VS Code family IDEs: {ide_names}')

    target_platform = _vscode_target_platform()

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
        if bundled_vsix.is_file():
            if _bundled_vsix_matches(bundled_vsix, version, target_platform):
                vsix_path = str(bundled_vsix)
                info(f'Using bundled VSIX: {vsix_path}')
            else:
                info(f'Bundled VSIX does not match version {version} for this platform, ignoring')

        if vsix_path is None and target_platform is not None:
            # Tier 2: Download the platform-specific VSIX from the
            # marketplace CDN. Both endpoints honor the targetPlatform
            # query parameter; without it they serve an arbitrary
            # platform's build of this platform-specific extension.
            download_urls = tuple(
                template.format(
                    publisher=IDE_EXTENSION_PUBLISHER,
                    extension=IDE_EXTENSION_NAME,
                    version=version,
                ) + f'?targetPlatform={target_platform}'
                for template in (VSIX_DOWNLOAD_URL_PRIMARY, VSIX_DOWNLOAD_URL_FALLBACK)
            )

            vsix_data: bytes | None = None
            not_found_count = 0
            for url in download_urls:
                try:
                    payload = fetch_url_bytes_with_auth(url)
                except urllib.error.HTTPError as exc:
                    # 404 means this URL has no VSIX for the pinned version;
                    # tracked to distinguish a missing version from
                    # transient download failures
                    if exc.code == 404:
                        not_found_count += 1
                    continue
                except Exception:
                    continue
                vsix_data = _normalize_vsix_payload(payload) if payload else None
                if vsix_data:
                    break

            if vsix_data is None and not_found_count == len(download_urls):
                warning(
                    f'IDE extension version {version} is not available in the '
                    f'VS Code Marketplace for {target_platform}. Skipping IDE '
                    'extension installation; the IDE keeps its current '
                    'extension version.',
                )
                return True

            if vsix_data:
                # Write to temp file
                tmp_fd: int | None = None
                tmp_name: str | None = None
                try:
                    tmp_fd, tmp_name = tempfile.mkstemp(suffix='.vsix')
                    os.write(tmp_fd, vsix_data)
                    os.close(tmp_fd)
                    vsix_path = tmp_name
                    temp_vsix_path = tmp_name
                    info(f'Downloaded VSIX ({len(vsix_data)} bytes) to {vsix_path}')
                except Exception:
                    if tmp_fd is not None:
                        with contextlib.suppress(OSError):
                            os.close(tmp_fd)
                    if tmp_name is not None:
                        with contextlib.suppress(OSError):
                            Path(tmp_name).unlink(missing_ok=True)

        if vsix_path is None:
            # Tier 3: Fall back to marketplace @version syntax; the IDE
            # resolves its own targetPlatform during the install
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
                    cmd = [cli_path, '--install-extension', str(vsix_path), '--force']
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
        """Validate a remote URL, escalating to authentication only on 401/403/404.

        Implements the "try unauthenticated first; escalate only on HTTP
        401/403/404" contract, mirroring the download path in _fetch_url_core.
        Non-authentication failures (SSL, DNS, 5xx, 416 Range Not Satisfiable,
        timeouts) do NOT trigger authentication prompts.

        Flow:
            Phase 1: GitLab URL conversion (web -> API) for raw URLs.
            Phase 2: Cache lookup -- reuse cached headers if the origin has
                     been probed before (None sentinel = known public origin,
                     dict = resolved authentication).
            Phase 3: Initial probe using unauthenticated headers (or cached
                     headers when available). HEAD first, Range as fallback.
                     On success, populate the cache with the headers that
                     worked (None on a fresh unauthenticated success).
            Phase 4: Auth escalation -- triggered ONLY when the last probe's
                     HTTP code is in (401, 403, 404). For 404 on GitHub URLs,
                     first probe api.github.com/repos/{owner}/{repo}: if the
                     repo is confirmed public, the 404 is a genuine missing
                     file and no auth prompt is needed. Otherwise (private,
                     nonexistent, or rate-limited), fall through to normal
                     escalation. Uses AuthHeaderCache.resolve_and_cache(url)
                     when a cache is available (double-checked locking
                     serializes prompts across parallel validation threads);
                     otherwise calls get_auth_headers(url, self.auth_param)
                     directly. resolve_and_cache returns {} (not None) when
                     no credentials are available -- treat this as terminal
                     and do not retry. Executes at most once per call.
            Phase 5: Non-auth failure -- return (False, 'None') without
                     invoking get_auth_headers on 5xx, SSL, DNS, 416, or
                     None codes.

        Args:
            url: Remote URL to validate.

        Returns:
            Tuple of (is_valid, method_used).
            method_used is 'HEAD' or 'Range' on success, 'None' on failure.
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
        # Phase 1: Convert GitLab web URLs to API format
        original_url = url
        if detect_repo_type(url) == 'gitlab' and '/-/raw/' in url:
            url = convert_gitlab_url_to_api(url)
            if url != original_url:
                info(f'Using API URL for validation: {url}')

        # Phase 2: Cache lookup. is_cached=True means the origin has already
        # been probed; cached_headers may be None (public sentinel) or a dict
        # (resolved authentication headers).
        initial_headers: dict[str, str] | None = None
        origin_cached = False
        if self.auth_cache is not None:
            is_cached, cached_headers = self.auth_cache.get_cached_headers(url)
            if is_cached:
                initial_headers = cached_headers
                origin_cached = True

        # Phase 3: Initial probe -- unauthenticated (or with cached headers).
        head_valid, head_code = self._check_with_head(url, initial_headers)
        if head_valid:
            if self.auth_cache is not None and not origin_cached:
                self.auth_cache.cache_headers(url, initial_headers)
            return (True, 'HEAD')

        range_valid, range_code = self._check_with_range(url, initial_headers)
        if range_valid:
            if self.auth_cache is not None and not origin_cached:
                self.auth_cache.cache_headers(url, initial_headers)
            return (True, 'Range')

        # Phase 4: Auth escalation -- ONLY on 401/403/404 from the last probe.
        # Prefer the Range code (last attempt); fall back to HEAD's code when
        # Range returned None (e.g., a non-HTTP error).
        last_http_code = range_code if range_code is not None else head_code

        if last_http_code in (401, 403, 404):
            # If we already used cached auth headers (non-empty dict) and still
            # got 401/403/404, the authentication failed -- re-prompting would
            # loop.
            if initial_headers:
                return (False, 'None')

            # 404 disambiguation for GitHub URLs: probe api.github.com/repos/
            # {owner}/{repo} unauthenticated. If the repo is confirmed public,
            # the original 404 is a genuine missing file (typo) and no auth
            # prompt is needed. Other outcomes (private, nonexistent,
            # rate-limited, network failure) fall through to normal escalation
            # (conservative: prompt for auth).
            if last_http_code == 404 and detect_repo_type(url) == 'github':
                owner_repo = _extract_github_owner_repo(url)
                if owner_repo is not None:
                    owner, repo = owner_repo
                    repo_public = _github_repo_is_public(owner, repo)
                    if repo_public is True:
                        info(
                            f'GitHub repo {owner}/{repo} is public; '
                            f'404 indicates missing file (not auth issue): {url}',
                        )
                        return (False, 'None')
                    if repo_public is None:
                        warning(
                            f'Could not verify public status of {owner}/{repo}; '
                            f'proceeding with auth prompt',
                        )

            # Resolve authentication. When a cache is available, route through
            # resolve_and_cache for thread-safe double-checked locking across
            # parallel validation threads. Note: resolve_and_cache returns {}
            # (empty dict), not None, when no credentials are available from
            # any source -- treat this as terminal.
            if self.auth_cache is not None:
                resolved_headers = self.auth_cache.resolve_and_cache(url)
                if not resolved_headers:
                    return (False, 'None')
                auth_headers: dict[str, str] | None = resolved_headers
            else:
                auth_headers = get_auth_headers(url, self.auth_param)
                if not auth_headers:
                    return (False, 'None')

            # Retry probe with resolved auth headers (at most once).
            head_valid, _head_code = self._check_with_head(url, auth_headers)
            if head_valid:
                if self.auth_cache is not None:
                    # resolve_and_cache already populated the cache; this
                    # defensive re-cache is a no-op in that case but keeps
                    # the non-cache path correct.
                    self.auth_cache.cache_headers(url, auth_headers)
                return (True, 'HEAD')

            range_valid, _range_code = self._check_with_range(url, auth_headers)
            if range_valid:
                if self.auth_cache is not None:
                    self.auth_cache.cache_headers(url, auth_headers)
                return (True, 'Range')

            # Authenticated retry also failed.
            return (False, 'None')

        # Phase 5: Non-auth failure (5xx, SSL, DNS, 416, None). Do NOT prompt.
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

    def _check_with_head(self, url: str, auth_headers: dict[str, str] | None) -> tuple[bool, int | None]:
        """Check URL availability using HEAD request.

        Args:
            url: URL to check
            auth_headers: Optional authentication headers

        Returns:
            Tuple of (is_valid, http_code).
            is_valid=True with http_code=200 on success (including after SSL fallback).
            is_valid=False with http_code=<code> on HTTP errors (401/403/404/416/5xx).
            is_valid=False with http_code=None on non-HTTP errors (SSL without fallback,
            DNS, URL errors, or other exceptions).

            The http_code is used by callers to decide whether to escalate to
            authentication (401/403/404) versus treating the failure as non-auth
            (5xx, None, etc.).
        """
        try:
            request = Request(url, method='HEAD')
            if auth_headers:
                for header, value in auth_headers.items():
                    request.add_header(header, value)

            try:
                response = urlopen(request)
                status = response.status
                return (bool(status == 200), status)
            except urllib.error.HTTPError as http_err:
                return (False, http_err.code)
            except urllib.error.URLError as e:
                if 'SSL' in str(e) or 'certificate' in str(e).lower():
                    # Try with unverified SSL context
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    try:
                        response = urlopen(request, context=ctx)
                        status = response.status
                        return (bool(status == 200), status)
                    except urllib.error.HTTPError as http_err:
                        return (False, http_err.code)
                    except Exception:
                        return (False, None)
                return (False, None)
        except Exception:
            return (False, None)

    def _check_with_range(self, url: str, auth_headers: dict[str, str] | None) -> tuple[bool, int | None]:
        """Check URL availability using Range request.

        Args:
            url: URL to check
            auth_headers: Optional authentication headers

        Returns:
            Tuple of (is_valid, http_code).
            is_valid=True with http_code=200 (full content) or 206 (partial content)
            on success (including after SSL fallback).
            is_valid=False with http_code=<code> on HTTP errors (including 416
            Range Not Satisfiable, which is a non-auth-related failure).
            is_valid=False with http_code=None on non-HTTP errors.

            The http_code is used by callers to decide whether to escalate to
            authentication (401/403/404) versus treating the failure as non-auth
            (5xx, 416, None, etc.).
        """
        try:
            request = Request(url)
            request.add_header('Range', 'bytes=0-0')
            if auth_headers:
                for header, value in auth_headers.items():
                    request.add_header(header, value)

            try:
                response = urlopen(request)
                status = response.status
                is_valid = status in (200, 206)
                return (is_valid, status)
            except urllib.error.HTTPError as http_err:
                return (False, http_err.code)
            except urllib.error.URLError as e:
                if 'SSL' in str(e) or 'certificate' in str(e).lower():
                    # Try with unverified SSL context
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    try:
                        response = urlopen(request, context=ctx)
                        status = response.status
                        is_valid = status in (200, 206)
                        return (is_valid, status)
                    except urllib.error.HTTPError as http_err:
                        return (False, http_err.code)
                    except Exception:
                        return (False, None)
                return (False, None)
        except Exception:
            return (False, None)

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

    # Hooks files and helper modules (both install into the hooks directory)
    hooks = config.get('hooks', {})
    if isinstance(hooks, dict):
        hooks_typed = cast(dict[str, Any], hooks)
        for hooks_key in ('files', 'helpers'):
            hook_files_raw = hooks_typed.get(hooks_key, [])
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
    """Detect the repository type from URL using hostname-based classification.

    Uses urllib.parse.urlparse to extract the hostname and classify the URL by
    exact host match, host suffix, or URL path marker. GitHub Pages URLs
    (hostname ending in .github.io) are explicitly excluded from the 'github'
    classification because Pages are static HTTP hosts with no repository
    auth model.

    Args:
        url: URL to classify.

    Returns:
        'gitlab' for gitlab.com, self-hosted *.gitlab.* hosts, or URLs using
            the /api/v4/projects/ path marker.
        'github' for github.com, *.github.com (including api.github.com), and
            raw.githubusercontent.com. Does NOT include *.github.io (Pages).
        'bitbucket' for hosts containing 'bitbucket'.
        None for all other URLs, including GitHub Pages URLs, gist.githubusercontent.com,
            and unparseable URLs.
    """
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
    except ValueError:
        return None

    host = (parsed.hostname or '').lower()

    # GitHub Pages: <owner>.github.io or bare github.io.
    # Excluded from 'github' because Pages sites use no repository auth model.
    if host == 'github.io' or host.endswith('.github.io'):
        return None

    # GitHub source hosts: github.com, api.github.com, raw.githubusercontent.com.
    if host == 'github.com' or host.endswith('.github.com') or host == 'raw.githubusercontent.com':
        return 'github'

    # GitLab: hostname substring match (covers gitlab.com and self-hosted) OR
    # API path marker (covers any host exposing the GitLab REST API).
    if 'gitlab' in host or '/api/v4/projects/' in url:
        return 'gitlab'

    # Bitbucket: hostname substring match (future expansion; preserves prior behavior).
    if 'bitbucket' in host:
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

        project_path = parts[0]  # e.g., "group/project"
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


def _extract_github_owner_repo(url: str) -> tuple[str, str] | None:
    """Extract (owner, repo) from any GitHub URL variant.

    Supports github.com web URLs, raw.githubusercontent.com URLs, and
    api.github.com Contents API URLs. Returns None for unparseable URLs,
    non-GitHub hosts, GitHub Pages URLs, or URLs lacking owner/repo path
    components.

    Args:
        url: Candidate GitHub URL.

    Returns:
        Tuple (owner, repo) for recognized GitHub URLs with at least
        owner/repo path segments; None otherwise.

    Examples:
        >>> _extract_github_owner_repo('https://github.com/owner/repo')
        ('owner', 'repo')
        >>> _extract_github_owner_repo('https://raw.githubusercontent.com/owner/repo/main/file.md')
        ('owner', 'repo')
        >>> _extract_github_owner_repo('https://api.github.com/repos/owner/repo/contents/x.md?ref=main')
        ('owner', 'repo')
        >>> _extract_github_owner_repo('https://github.io/x') is None
        True
    """
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return None

    host = (parsed.hostname or '').lower()
    parts = [p for p in parsed.path.split('/') if p]

    # api.github.com/repos/{owner}/{repo}/...
    if host == 'api.github.com':
        if len(parts) >= 3 and parts[0] == 'repos':
            return (parts[1], parts[2])
        return None

    # raw.githubusercontent.com/{owner}/{repo}/{ref}/...
    if host == 'raw.githubusercontent.com':
        if len(parts) >= 2:
            return (parts[0], parts[1])
        return None

    # github.com/{owner}/{repo}/... (web URL, supports tree/blob/etc subpaths)
    if host == 'github.com' or host.endswith('.github.com'):
        if len(parts) >= 2:
            return (parts[0], parts[1])
        return None

    # GitHub Pages and all other hosts: not a source repo URL.
    return None


def _github_repo_is_public(owner: str, repo: str, *, timeout: float = 5.0) -> bool | None:
    """Probe api.github.com/repos/{owner}/{repo} unauthenticated to check repo visibility.

    Used to disambiguate a 404 response on a GitHub file URL: when the bare-repo
    endpoint returns 200, the original 404 is a genuine missing file (typo) and
    no auth prompt is needed. When the bare-repo endpoint returns 404, the
    repo is either private (privacy-hidden by GitHub) or genuinely missing --
    in either case the caller should conservatively escalate to the auth
    prompt (legitimate for the private case, an unavoidable papercut otherwise).

    Endpoint choice (api.github.com/repos/{owner}/{repo}):
        GitHub intentionally returns 404 for both "private repo hidden" and
        "missing file" on the /contents/{path} endpoint, making them
        indistinguishable. The bare repo endpoint distinguishes:
            200 -> public repo exists -> a 404 on a file path is a genuine
                   typo/missing file
            404 -> ambiguous (private or nonexistent); the caller should
                   escalate to auth (legitimate for the private case)

    Args:
        owner: GitHub repository owner (user or org).
        repo: GitHub repository name.
        timeout: Maximum seconds to wait for the probe HTTP call.

    Returns:
        True  if the repo is confirmed public-existing (HTTP 200).
        False if the repo is private or does not exist (HTTP 404).
        None  on any other condition (rate-limit 403/429, network failure,
              timeout, malformed response). Caller should treat None as
              "unable to determine -- conservatively escalate".

    Note:
        This helper deliberately bypasses _fetch_url_core and AuthHeaderCache
        to avoid recursion (the validator may call this DURING auth resolution
        for a different URL on the same origin). It uses a raw urllib Request
        + urlopen with the documented GitHub REST API headers.
    """
    api_url = f'https://api.github.com/repos/{owner}/{repo}'
    request = Request(api_url)
    request.add_header('Accept', 'application/vnd.github+json')
    request.add_header('X-GitHub-Api-Version', '2022-11-28')
    try:
        with urlopen(request, timeout=timeout) as response:
            return getattr(response, 'status', None) == 200
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        return None
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def _env_tokens_checked_for_repo_type(repo_type: str | None) -> list[str]:
    """Return the ordered list of environment variable names to check for a repo type.

    Used by resolve_credentials (to determine env var lookup order) and by
    prompt_for_credentials (to inform the user which env vars were checked).

    Args:
        repo_type: Value returned by detect_repo_type (e.g., 'github', 'gitlab', 'bitbucket', None).

    Returns:
        Ordered list of env var names to check, repo-specific name first then REPO_TOKEN fallback.
        Unknown or None repo types return just ['REPO_TOKEN'].
    """
    if repo_type == 'gitlab':
        return ['GITLAB_TOKEN', 'REPO_TOKEN']
    if repo_type == 'github':
        return ['GITHUB_TOKEN', 'REPO_TOKEN']
    return ['REPO_TOKEN']


def resolve_credentials(url: str, auth_param: str | None = None) -> dict[str, str]:
    """Resolve authentication headers for a URL from non-interactive sources.

    Checks two sources in order:
        1. auth_param from CLAUDE_CODE_TOOLBOX_ENV_AUTH (format "header:value",
           "header=value", or bare token)
        2. Environment variables (GITLAB_TOKEN, GITHUB_TOKEN, REPO_TOKEN)

    This function is pure and non-interactive: it never prompts the user, never
    emits 'Authentication required' warnings, and never waits for terminal input.
    Callers that want interactive fallback should invoke prompt_for_credentials() afterward.

    Args:
        url: URL being authenticated (used only for repo type detection).
        auth_param: Optional auth value from CLAUDE_CODE_TOOLBOX_ENV_AUTH (format "header:value",
            "header=value", or a bare token).

    Returns:
        Dictionary of HTTP headers for authentication. Empty dict {} if no credentials
        are resolvable from the non-interactive sources.
    """
    repo_type = detect_repo_type(url)

    # Helper: build GitHub Authorization header with Bearer prefix.
    def build_github_headers(token: str) -> dict[str, str]:
        # Handle Bearer prefix - avoid duplication if already present
        auth_value = token if token.startswith('Bearer ') else f'Bearer {token}'
        return {'Authorization': auth_value}

    # Method 1: CLAUDE_CODE_TOOLBOX_ENV_AUTH explicit override (highest priority).
    if auth_param:
        # Support both : and = as separators
        if ':' in auth_param:
            header_name, token = auth_param.split(':', 1)
            info('Using authentication from CLAUDE_CODE_TOOLBOX_ENV_AUTH')
            return {header_name: token}
        if '=' in auth_param:
            header_name, token = auth_param.split('=', 1)
            info('Using authentication from CLAUDE_CODE_TOOLBOX_ENV_AUTH')
            return {header_name: token}
        # Bare token: use default header based on repo type.
        token = auth_param
        if repo_type == 'gitlab':
            info('Using authentication from CLAUDE_CODE_TOOLBOX_ENV_AUTH')
            return {'PRIVATE-TOKEN': token}
        if repo_type == 'github':
            info('Using authentication from CLAUDE_CODE_TOOLBOX_ENV_AUTH')
            return build_github_headers(token)
        error(
            'Cannot determine auth header type. '
            'Set CLAUDE_CODE_TOOLBOX_ENV_AUTH="Header-Name:value" '
            '(e.g. --env CLAUDE_CODE_TOOLBOX_ENV_AUTH=Header-Name:value)',
        )
        return {}

    # Method 2: Environment variables.
    if repo_type == 'gitlab':
        env_token = os.environ.get('GITLAB_TOKEN')
        if env_token:
            return {'PRIVATE-TOKEN': env_token}
    elif repo_type == 'github':
        env_token = os.environ.get('GITHUB_TOKEN')
        if env_token:
            return build_github_headers(env_token)

    # REPO_TOKEN fallback (only applied for known repo types).
    env_token = os.environ.get('REPO_TOKEN')
    if env_token:
        if repo_type == 'gitlab':
            return {'PRIVATE-TOKEN': env_token}
        if repo_type == 'github':
            return build_github_headers(env_token)

    return {}


def prompt_for_credentials(url: str, *, tokens_checked: list[str]) -> dict[str, str]:
    """Prompt the user interactively for authentication credentials.

    Guarded by sys.stdin.isatty(). In non-interactive terminals, emits an
    informational message (if a repo type is detected) and returns {} without
    prompting. In interactive terminals with a detected repo type, warns the
    user that authentication was not resolved, asks whether the user wants to
    enter a token, and collects the token via getpass.

    Args:
        url: URL being authenticated (used for repo type detection + header shape).
        tokens_checked: Ordered list of env var names already checked by
            resolve_credentials, used to inform the user of the fallback chain.

    Returns:
        Dictionary of HTTP headers for authentication. Empty dict {} if the
        terminal is non-interactive, the repo type is unknown, the user
        declines, or the user cancels with Ctrl+C / EOF.
    """
    repo_type = detect_repo_type(url)

    # Helper: build GitHub Authorization header with Bearer prefix.
    def build_github_headers(token: str) -> dict[str, str]:
        # Handle Bearer prefix - avoid duplication if already present
        auth_value = token if token.startswith('Bearer ') else f'Bearer {token}'
        return {'Authorization': auth_value}

    if repo_type and sys.stdin.isatty():
        warning(f'Authentication required for {url}')
        info(f"Checked environment variables: {', '.join(tokens_checked)}")
        info('You can provide authentication by:')
        info(f'  1. Setting environment variable: {tokens_checked[0]}')
        info(f'  2. Passing it on the command line: --env {tokens_checked[0]}=token_here')

        # Ask if they want to enter it now. The shared consent gate
        # flushes queued terminal reports, sanitizes escape sequences,
        # and re-prompts on an unrecognized answer, so a clean typed y is
        # never misread as a decline (the /dev/tty fallback inside is
        # unreachable here because this branch requires a tty stdin).
        try:
            if _ask_yes_no('Would you like to enter the token now? (y/N): '):
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
        info(f'Authentication required for {url}')
        info(f"If authentication is required, set one of: {', '.join(tokens_checked)}")

    return {}


def get_auth_headers(url: str, auth_param: str | None = None) -> dict[str, str]:
    """Resolve authentication headers for a URL, with interactive fallback.

    Orchestrates two-stage credential resolution:
        1. resolve_credentials() -- pure, non-interactive (env vars incl. CLAUDE_CODE_TOOLBOX_ENV_AUTH)
        2. prompt_for_credentials() -- interactive, guarded by sys.stdin.isatty()

    Preserves the public-API signature used by callers and test mocks. Callers
    that want non-interactive-only resolution can call resolve_credentials()
    directly without risking user prompts.

    Args:
        url: The URL to authenticate for.
        auth_param: Optional auth parameter in format "header:value" or
            "header=value" or a bare token.

    Returns:
        Dictionary of HTTP headers for authentication, or {} if no credentials
        could be resolved from any source (non-interactive and interactive).
    """
    headers = resolve_credentials(url, auth_param)
    if headers:
        return headers

    # No creds resolved via non-interactive sources; attempt interactive prompt.
    # The prompt is itself guarded by sys.stdin.isatty() and detects repo_type internally.
    repo_type = detect_repo_type(url)
    tokens_checked = _env_tokens_checked_for_repo_type(repo_type)
    return prompt_for_credentials(url, tokens_checked=tokens_checked)


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

    # Original-to-resolved mapping per selectable section, used below to
    # rewrite this config's own component selectors in lockstep with the
    # items they claim (selector identity for these sections is the item
    # string, which this function changes)
    selector_mappings: dict[str, dict[str, str]] = {}

    # --- Simple list keys: agents, slash-commands, rules ---
    for key in ('agents', 'slash-commands', 'rules'):
        items = result.get(key)
        if isinstance(items, list):
            resolved_items = []
            mapping: dict[str, str] = {}
            for item in items:
                if isinstance(item, str):
                    resolved_path, _ = resolve_resource_path(item, config_source, base_url)
                    resolved_items.append(resolved_path)
                    if resolved_path != item:
                        mapping[item.strip()] = resolved_path
                else:
                    resolved_items.append(item)
            result[key] = resolved_items
            if mapping:
                selector_mappings[key] = mapping

    # --- hooks.files and hooks.helpers ---
    hooks = result.get('hooks')
    if isinstance(hooks, dict):
        hooks = hooks.copy()
        hook_files = hooks.get('files')
        if isinstance(hook_files, list):
            resolved_files = []
            hooks_mapping: dict[str, str] = {}
            for item in hook_files:
                if isinstance(item, str):
                    resolved_path, _ = resolve_resource_path(item, config_source, base_url)
                    resolved_files.append(resolved_path)
                    if resolved_path != item:
                        hooks_mapping[item.strip()] = resolved_path
                else:
                    resolved_files.append(item)
            hooks['files'] = resolved_files
            if hooks_mapping:
                selector_mappings['hooks'] = hooks_mapping
        # Helpers resolve the same way but contribute no selector mapping:
        # they carry no component identity, so no selector can name one
        hook_helpers = hooks.get('helpers')
        if isinstance(hook_helpers, list):
            hooks['helpers'] = [
                resolve_resource_path(item, config_source, base_url)[0]
                if isinstance(item, str)
                else item
                for item in hook_helpers
            ]
        result['hooks'] = hooks

    # --- components[].includes selectors for path-identity sections ---
    # A selector that exactly matches an item string rewritten above is
    # rewritten to the same resolved string, so authors write one string in
    # the item list and the selector and both resolve identically. Every
    # other selector (hook event ids, name identities, already-absolute
    # paths, cross-file claims written in resolved form) passes through.
    components = result.get('components')
    if isinstance(components, list) and selector_mappings:
        resolved_components: list[Any] = []
        for comp in components:
            if not isinstance(comp, dict):
                resolved_components.append(comp)
                continue
            comp_copy = cast(dict[str, Any], comp).copy()
            includes = comp_copy.get('includes')
            if isinstance(includes, dict):
                includes_copy = cast(dict[str, Any], includes).copy()
                for section, section_mapping in selector_mappings.items():
                    selectors = includes_copy.get(section)
                    if isinstance(selectors, list):
                        includes_copy[section] = [
                            section_mapping.get(s.strip(), s) if isinstance(s, str) else s
                            for s in cast(list[object], selectors)
                        ]
                comp_copy['includes'] = includes_copy
            resolved_components.append(comp_copy)
        result['components'] = resolved_components

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


def _is_local_config_spec(config_spec: str) -> bool:
    """Report whether a configuration specification names a local file.

    Args:
        config_spec: The configuration as given: a URL, a path, or a name.

    Returns:
        True for a path (separators, a leading dot, an absolute path, or an
        existing file); False for a URL or a repository configuration name.
    """
    return (
        '/' in config_spec
        or '\\' in config_spec
        or config_spec.startswith(('./', '.\\', '../', '..\\'))
        or os.path.isabs(config_spec)
        or os.path.exists(config_spec)
    )


def config_identity_of_spec(config_spec: str) -> str | None:
    """Return the identity a configuration specification resolves to, without loading it.

    Mirrors load_config_from_source(): a URL is its own identity, a local
    path resolves to its absolute form, and a repository name resolves to
    the URL the loader fetches.

    Args:
        config_spec: The configuration as given.

    Returns:
        The identity config_identity_of() would return for the resolved
        source, or None when the name resolves to no URL.
    """
    if config_spec.startswith(('http://', 'https://')):
        return config_identity_of(config_spec)
    if _is_local_config_spec(config_spec):
        return config_identity_of(str(Path(config_spec).resolve()))
    url = resolve_config_source_url(config_spec, 'repo')
    return config_identity_of(url) if url else None


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
    if _is_local_config_spec(config_spec):
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


def _name_identity(item: dict[str, Any]) -> str | None:
    """Compute the merge identity of a named entry (mcp-servers, skills).

    Args:
        item: An entry dict with a 'name' key.

    Returns:
        The name as a string, or None when the entry has no name.
    """
    name = item.get('name')
    return None if name is None else str(name)


def _source_filename(source: str) -> str:
    """Derive the deployed filename a directory-form dest receives for a source.

    Strips query parameters and takes the last path segment. GitLab API
    raw-file URLs ({base}/api/v4/projects/{id}/repository/files/{encoded
    path}/raw?ref=...) carry the real filename inside the URL-encoded path
    segment while their last path segment is the literal 'raw', so for them
    the encoded segment is decoded and its basename used instead. Purely
    lexical (no filesystem or network access), so the result is identical
    whether the source is still relative or already resolved to a URL.

    Args:
        source: Source path or URL from a files-to-download entry.

    Returns:
        The filename to append to a directory-form dest.
    """
    clean_source = source.split('?')[0]
    if (
        clean_source.endswith('/raw')
        and '/api/v4/projects/' in clean_source
        and '/repository/files/' in clean_source
    ):
        encoded_path = clean_source.split('/repository/files/')[-1].removesuffix('/raw')
        return Path(urllib.parse.unquote(encoded_path)).name
    return Path(clean_source).name


def _files_download_identity(item: dict[str, Any]) -> str | None:
    """Compute the merge identity of a files-to-download entry.

    The identity is the final deployed file path in lexical form. A dest
    ending with a path separator ('/' or '\\') is a directory destination,
    so the filename from _source_filename() is appended, mirroring the
    destination resolution in process_file_downloads(), which uses the same
    helper. The check is purely lexical (no filesystem access) so that
    inheritance resolution behaves identically on machines whose filesystem
    does not match the target: a dest without a trailing separator is
    treated as a file path even if a directory exists at that path at
    download time.

    Args:
        item: An entry dict with 'source' and 'dest' keys.

    Returns:
        The identity string, or None when the entry has no dest.
    """
    dest = item.get('dest')
    if dest is None:
        return None
    dest_str = str(dest)
    if dest_str.endswith(('/', '\\')):
        return dest_str + _source_filename(str(item.get('source', '')))
    return dest_str


def _dedupe_by_identity(
    items: list[dict[str, Any]],
    identity_fn: Callable[[dict[str, Any]], str | None],
    section: str,
) -> list[dict[str, Any]]:
    """Drop entries sharing an identity, keeping only the last occurrence.

    Entries with the same identity resolve to the same final artifact, so
    only one can take effect; the last one is kept to match the
    later-overrides-earlier merge semantics, and every dropped entry is
    reported with a warning instead of disappearing silently.

    Args:
        items: List of entry dicts.
        identity_fn: Callable computing an entry's identity (None means the
            entry has no identity and always survives).
        section: Configuration section name used in warning messages.

    Returns:
        The list with earlier duplicate-identity entries removed.
    """
    last_index: dict[str, int] = {}
    for idx, item in enumerate(items):
        key = identity_fn(item)
        if key is not None:
            last_index[key] = idx

    result: list[dict[str, Any]] = []
    for idx, item in enumerate(items):
        key = identity_fn(item)
        if key is not None and last_index[key] != idx:
            warning(
                f"Duplicate identity '{key}' in {section}: "
                f'ignoring an earlier entry in favor of the last one',
            )
            continue
        result.append(item)
    return result


def _merge_named_list(
    parent_list: list[dict[str, Any]],
    child_list: list[dict[str, Any]],
    identity_fn: Callable[[dict[str, Any]], str | None],
    section: str,
) -> list[dict[str, Any]]:
    """Merge named lists with in-position replacement for matching identities.

    Identities are computed by identity_fn (the 'name' field for mcp-servers
    and skills, the normalized final file path for files-to-download). Child
    items sharing a parent item's identity replace it at the parent's
    original position. New child items (no matching parent) are appended.
    Duplicate identities within either input list are collapsed to the last
    occurrence with a warning before merging.

    Args:
        parent_list: Base list of dicts.
        child_list: Override list of dicts.
        identity_fn: Callable computing an entry's identity (None means the
            entry has no identity, never matches, and is always kept).
        section: Configuration section name used in duplicate warnings.

    Returns:
        Merged list preserving parent ordering with child overrides and appends.
    """
    parent_list = _dedupe_by_identity(parent_list, identity_fn, section)
    child_list = _dedupe_by_identity(child_list, identity_fn, section)

    child_by_id: dict[str, dict[str, Any]] = {}
    for item in child_list:
        key = identity_fn(item)
        if key is not None:
            child_by_id[key] = item

    consumed: set[str] = set()
    result: list[dict[str, Any]] = []

    for parent_item in parent_list:
        parent_key = identity_fn(parent_item)
        if parent_key is not None and parent_key in child_by_id:
            result.append(child_by_id[parent_key])
            consumed.add(parent_key)
        else:
            result.append(parent_item)

    for item in child_list:
        key = identity_fn(item)
        if key is None or key not in consumed:
            result.append(item)

    return result


def _merge_hooks(
    parent_hooks: dict[str, Any],
    child_hooks: dict[str, Any],
) -> dict[str, Any]:
    """Merge hooks: files and helpers with dedup, events concatenated.

    Args:
        parent_hooks: Parent hooks configuration.
        child_hooks: Child hooks configuration.

    Returns:
        Merged hooks with deduplicated files and helpers and concatenated
        events.
    """
    merged_files = _merge_string_list(
        parent_hooks.get('files', []), child_hooks.get('files', []),
    )
    merged_helpers = _merge_string_list(
        parent_hooks.get('helpers', []), child_hooks.get('helpers', []),
    )

    parent_events = parent_hooks.get('events', [])
    child_events = child_hooks.get('events', [])
    merged_events = list(parent_events) + list(child_events)

    return {'files': merged_files, 'helpers': merged_helpers, 'events': merged_events}


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
    if key in ('mcp-servers', 'skills', 'components'):
        p_named = cast(list[dict[str, object]], parent_value) if isinstance(parent_value, list) else []
        c_named = cast(list[dict[str, object]], child_value) if isinstance(child_value, list) else []
        return _merge_named_list(p_named, c_named, _name_identity, key)

    # Named list key with identity by the normalized final file path
    if key == 'files-to-download':
        p_files = cast(list[dict[str, object]], parent_value) if isinstance(parent_value, list) else []
        c_files = cast(list[dict[str, object]], child_value) if isinstance(child_value, list) else []
        return _merge_named_list(p_files, c_files, _files_download_identity, key)

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

    # The three dict-valued keys below compose PATCHES rather than applying
    # one: the resolved config is itself applied to disk later, so a child
    # null is carried forward as a deletion request instead of being
    # consumed here -- otherwise a parent-declared value would silently
    # cancel the child's deletion and the stale on-disk value would survive.

    # Global-config: objects deep-merge, and a child array replaces the
    # parent's at every depth. The Step 15 writer later unions the result
    # with the arrays the target .claude.json already holds.
    if key == 'global-config':
        p_gc = cast(dict[str, Any], parent_value) if isinstance(parent_value, dict) else {}
        c_gc = cast(dict[str, Any], child_value) if isinstance(child_value, dict) else {}
        return deep_merge_settings(p_gc, c_gc, array_union_keys=set(), preserve_nulls=True)

    # User-settings: objects deep-merge, permissions.allow/deny/ask arrays
    # are unioned (DEFAULT_ARRAY_UNION_KEYS), and every other child array
    # replaces the parent's.
    if key == 'user-settings':
        p_us = cast(dict[str, Any], parent_value) if isinstance(parent_value, dict) else {}
        c_us = cast(dict[str, Any], child_value) if isinstance(child_value, dict) else {}
        return deep_merge_settings(
            p_us, c_us, array_union_keys=DEFAULT_ARRAY_UNION_KEYS, preserve_nulls=True,
        )

    # OS-level environment variables: shallow dict composition
    if key == 'os-env-variables':
        p_env = cast(dict[str, str | None], parent_value) if isinstance(parent_value, dict) else {}
        c_env = cast(dict[str, str | None], child_value) if isinstance(child_value, dict) else {}
        return {**p_env, **c_env}

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
        >>> child = {'inherit': ['base.yaml', 'ext.yaml'], 'name': 'Leaf'}
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


def account_key_deletion_warnings(
    global_config: dict[str, Any] | None,
    target_file: Path,
    profile_label: str,
) -> list[str]:
    """Warn about global-config deletions that sign an account out.

    A null for one of GLOBAL_CONFIG_ACCOUNT_KEYS deletes the key from the
    .claude.json the run writes. When that file holds a value for the key,
    the profile it belongs to is signed out by the write, which is the
    configuration author's choice and never blocked, so the summary and
    --dry-run name the profile and the file before consent. The values
    themselves are never printed.

    Args:
        global_config: The resolved global-config section, or None.
        target_file: The .claude.json this run writes (see
            global_config_target_file()).
        profile_label: Display name of the profile the file belongs to
            ('base' or the primary command name).

    Returns:
        One warning per affected key; empty when nothing is deleted, the
        file lacks the key or holds null for it, or the file cannot be read.
    """
    if not global_config:
        return []
    deleted = [key for key in GLOBAL_CONFIG_ACCOUNT_KEYS if key in global_config and global_config[key] is None]
    if not deleted:
        return []
    content = _read_json_object(target_file)
    if not content:
        return []
    return [
        f"global-config deletes {key} from {target_file} (profile '{profile_label}'): "
        'the account signed in there is signed out'
        for key in deleted
        if content.get(key) is not None
    ]


def collect_machine_wide_writes(
    *,
    profile_dir: Path,
    command_names: list[str],
    skip_install: bool,
    install_version: str | None,
    keep_installed: bool,
    pinned_version: str | None,
    ide_clis: list[str],
    os_level_env: dict[str, str | None],
    mcp_servers: list[dict[str, Any]],
    files_to_download: list[dict[str, Any]],
    has_dependency_commands: bool,
    pin_effect: str | None = None,
) -> list[str]:
    """Name every write of an isolated run that reaches beyond its profile.

    An isolated run keeps its files inside its profile directory, so the
    writes that leave it are the ones every profile on the machine shares:
    the one Claude Code binary and the installMethod the installer records
    in the base ~/.claude.json, a version pin holding that binary, the IDE
    extension Step 2 installs at that pin into every detected VS Code
    family IDE, the machine-wide environment controls, the command wrappers
    in ~/.local/bin, project-scope MCP registrations in the working
    directory, files-to-download destinations outside the profile, and the
    side effects of dependency commands. The summary lists them before
    consent.

    Args:
        profile_dir: The isolated profile directory.
        command_names: Every command name the run registers.
        skip_install: Whether Step 1 (and with it Step 2) is skipped.
        install_version: The Claude Code version Step 1 installs or keeps.
        keep_installed: Whether Step 1 keeps the installed version.
        pinned_version: The version this run pins, or None.
        ide_clis: CLI names of the VS Code family IDEs Step 2 installs
            the extension into (see _detect_vscode_family_ides()); Step 2
            runs only for a pinned run without --skip-install, and writes
            nothing when no IDE is detected.
        os_level_env: The os-env-variables entries written to the OS
            environment (see partition_os_env_variables()).
        mcp_servers: The resolved mcp-servers list.
        files_to_download: The resolved files-to-download list.
        has_dependency_commands: Whether any dependency command runs on
            this platform.
        pin_effect: The pin_effect_line() of this run's pin, naming the
            other installed profiles, or None to describe the pin alone.

    Returns:
        One line per machine-wide write, in execution order.
    """
    writes: list[str] = []
    if not skip_install:
        version = install_version or 'latest'
        if keep_installed:
            writes.append(f'Claude Code binary: keep the installed version {version} (used by every profile)')
        else:
            writes.append(f'Claude Code binary: install or upgrade to {version} (used by every profile)')
        writes.append(
            f'{get_real_user_home() / ".claude.json"}: {INSTALL_METHOD_KEY}, recorded by the '
            'Claude Code installer when it installs, upgrades or migrates the binary',
        )
    if pinned_version is not None:
        writes.append(pin_effect or pin_effect_line(pinned_version, None, []))
        if not skip_install and ide_clis:
            writes.append(
                f'IDE extension {IDE_EXTENSION_ID} {pinned_version}: installed into '
                f'{", ".join(ide_clis)} (used by every profile)',
            )
    for key, value in os_level_env.items():
        if value is None:
            writes.append(f'OS environment: delete {key}')
        else:
            writes.append(f'OS environment: {key}="{value}"')
    if command_names:
        writes.append(f'{get_real_user_home() / ".local" / "bin"}: command wrapper(s) {", ".join(command_names)}')
    project_servers = [
        str(server.get('name', '<unnamed>'))
        for server in mcp_servers
        if 'project' in _mcp_scopes_or_empty(server.get('scope'))
    ]
    if project_servers:
        writes.append(
            f'.mcp.json in the working directory: project-scope MCP server(s) {", ".join(project_servers)}',
        )
    profile_key = _normalize_config_dir_key(str(profile_dir))
    for item in files_to_download:
        dest = item.get('dest')
        if not isinstance(dest, str) or not dest:
            continue
        dest_key = _normalize_config_dir_key(normalize_tilde_path(dest))
        if dest_key != profile_key and not dest_key.startswith(profile_key + '/'):
            writes.append(f'files-to-download outside the profile: {dest}')
    if has_dependency_commands:
        writes.append('Dependency commands: run machine-wide (listed above)')
    return writes


def _mcp_scopes_or_empty(scope_value: object) -> list[str]:
    """Normalize an MCP scope value for the summary, tolerating invalid ones.

    Args:
        scope_value: Raw scope value from the YAML entry.

    Returns:
        The normalized scopes, or an empty list when the value is not a
        string, a list of strings, or None (validation reports it later).
    """
    if scope_value is not None and not isinstance(scope_value, str | list):
        return []
    try:
        return normalize_scope(cast(str | list[str] | None, scope_value))
    except ValueError:
        return []


def collect_installation_plan(
    config: dict[str, Any],
    config_source: str,
    config_name: str,
    config_version: str | None,
    inheritance_chain: list[InheritanceChainEntry],
    args: argparse.Namespace,
    selection: ComponentSelection | None = None,
    deselected: dict[str, list[Any]] | None = None,
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
        selection: Resolved component selection, or None when the config
            defines no components.
        deselected: Removal plan from collect_deselected_items(), or None
            when the config defines no components.

    Returns:
        InstallationPlan containing all artifacts to be installed.
    """
    config_source_type = classify_config_source(config_source)

    # Extract resources
    hooks_dict: dict[str, Any] = config.get('hooks') or {}
    hooks_files: list[str] = hooks_dict.get('files') or []
    hooks_helpers: list[str] = hooks_dict.get('helpers') or []
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
        hooks_helpers=hooks_helpers,
        hooks_events=hooks_events,
        mcp_servers=mcp_servers,
        dependency_commands=dependency_commands,
        system_prompt=system_prompt,
        system_prompt_mode=system_prompt_mode,
        command_defaults=cmd_defaults,
        command_names=command_names,
        claude_code_version=config.get('claude-code-version'),
        install_nodejs=bool(config.get('install-nodejs')),
        skip_install=args.skip_install,
        os_env_variables=config.get('os-env-variables'),
        user_settings=config.get('user-settings'),
        global_config=config.get('global-config'),
        status_line=config.get('status-line'),
        unknown_keys=unknown_keys,
        sensitive_paths=sensitive_paths,
        component_selection=selection,
        deselected_items=deselected,
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
    _print(f'  * Hook helpers: {len(plan.hooks_helpers)}')
    _print(f'  * Hook events: {len(plan.hooks_events)}')
    if plan.hooks_events:
        type_counts: dict[str, int] = {}
        for evt in plan.hooks_events:
            t = evt.get('type', 'command')
            type_counts[t] = type_counts.get(t, 0) + 1
        type_parts = [f'{count} {name}' for name, count in sorted(type_counts.items())]
        _print(f'    ({", ".join(type_parts)})')
    _print(f'  * MCP servers: {len(plan.mcp_servers)}')

    # Component selection
    component_selection = plan.component_selection
    if component_selection is not None and component_selection.is_active:
        _print()
        selection_marker = origin_marker(component_selection.origin, remembered=component_selection.remembered)
        _print(f'{Colors.BOLD}Components:{Colors.NC}{selection_marker}')
        selected_set = set(component_selection.selected)
        for name in component_selection.available:
            mark = '[x]' if name in selected_set else '[ ]'
            label = component_selection.labels.get(name, name)
            suffix = f' ({name})' if label != name else ''
            cause = component_selection.auto_included.get(name)
            cause_str = f' {Colors.GREEN}[auto: {cause}]{Colors.NC}' if cause else ''
            _print(f'  {mark} {label}{suffix}{cause_str}')
        replay = component_selection.replay
        # Names from the flag or its variable are not in the configuration,
        # so a replay without them would install the configuration's profile
        if plan.command_names_origin in ('cli', 'env'):
            replay += f" --command-names {','.join(plan.command_names)}"
        _print(f'  Replay: {replay}')

    deselected = plan.deselected_items
    if deselected and has_deselected_items(deselected):
        _print()
        _print(f'{Colors.BOLD}Removals (deselected components):{Colors.NC}')
        removal_labels = {
            'agents': 'agent', 'slash-commands': 'slash command', 'rules': 'rule',
            'skills': 'skill', 'mcp-servers': 'MCP server',
            'files-to-download': 'file', 'hooks-files': 'hook file',
            'hooks-events': 'hook event',
        }
        for section, items in deselected.items():
            for item in items:
                if isinstance(item, dict):
                    item_dict = cast(dict[str, Any], item)
                    name = str(
                        item_dict.get('name')
                        or item_dict.get('dest')
                        or item_dict.get('id')
                        or item_dict.get('event')
                        or item,
                    )
                else:
                    name = str(item)
                _print(f'  {Colors.RED}[REMOVE]{Colors.NC} {removal_labels[section]}: {name}')

    # Claude Code installation
    _print()
    if plan.skip_install:
        _print('  * Claude Code: skip (--skip-install)')
    elif plan.keep_installed_claude:
        _print(f'  * Claude Code: keep the installed version {plan.claude_code_version} ({plan.claude_install_reason})')
    else:
        version_str = plan.claude_code_version or 'latest'
        reason_str = f' ({plan.claude_install_reason})' if plan.claude_install_reason else ''
        _print(f'  * Claude Code: install (version: {version_str}){reason_str}')
    if not plan.skip_install and plan.claude_install_warning:
        _print(f'    {Colors.YELLOW}Warning: {plan.claude_install_warning}{Colors.NC}')
    # An isolated run lists its pin among the machine-wide writes below
    if plan.pin_effect and not plan.command_names:
        _print(f'  * {plan.pin_effect}')
    if plan.install_nodejs:
        _print('  * Node.js: install if needed')

    # Settings
    settings_items: list[str] = []
    if plan.system_prompt:
        settings_items.append(f'System prompt: {plan.system_prompt_mode}')
    if plan.command_defaults_isolated_only:
        settings_items.append(f'{Colors.YELLOW}{COMMAND_DEFAULTS_ISOLATED_ONLY_NOTE}{Colors.NC}')
    if plan.os_env_variables:
        if plan.command_names:
            os_level, loader = partition_os_env_variables(plan.os_env_variables, isolated=True)
            settings_items.append(
                f'OS environment variables: {len(loader)} in the profile env loaders, '
                f'{len(os_level)} machine-wide (listed below)',
            )
        else:
            settings_items.append(f'OS environment variables: {len(plan.os_env_variables)} (machine-wide)')
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
    if plan.command_names:
        names_marker = origin_marker(plan.command_names_origin, remembered=plan.command_names_remembered)
        settings_items.append(f"Command names: {', '.join(plan.command_names)}{names_marker}")
    if plan.linked_from:
        settings_items.append(
            f'Configuration: applied from profile "{plan.linked_from}" ({RESOLVED_CONFIG_FILENAME}), '
            f'components as installed there',
        )
    settings_items.extend(unlinked_summary_lines(plan.link_spec, plan.configured_link_dirs))

    if settings_items:
        _print()
        _print(f'{Colors.BOLD}Settings:{Colors.NC}')
        for item in settings_items:
            _print(f'  * {item}')

    # Links of an isolated run: every entry Step 3 creates, keeps, repairs,
    # converts or removes, and every link on disk no value declares; a
    # conversion names each directory it moves aside before consent
    link_plan = plan.link_plan
    if link_plan is not None and link_plan.actions:
        _print()
        if plan.link_spec is not None and plan.link_spec.dirs:
            marker = origin_marker(plan.link_spec.dirs_origin, remembered=plan.link_spec.dirs_remembered)
            _print(f'{Colors.BOLD}Links (from profile "{plan.link_spec.source}"):{Colors.NC}{marker}')
        else:
            _print(f'{Colors.BOLD}Links:{Colors.NC}')
        for row in link_plan.rows():
            _print(f'  * {row}')
        for row in link_plan.move_aside_rows():
            _print(f'  {Colors.YELLOW}[MOVE ASIDE]{Colors.NC} {row}')

    # Profiles that link content from this one: each is re-run after this run
    # from this run's resolved-config.yaml; a dry run starts none
    if plan.dependents:
        _print()
        _print(f'{Colors.BOLD}Dependents (profiles linking content from this one, refreshed after this run):{Colors.NC}')
        for name in plan.dependents:
            _print(f'  * {name} (--profile {name} --yes --skip-install --no-admin)')

    # Dependency commands (highlighted in yellow -- most dangerous); a
    # command re-rooted into the profile is marked, and the block below
    # shows what it was rewritten from
    rerooted_commands = {
        (item.label, item.rewritten) for item in plan.rerooted_paths if item.section == 'dependencies'
    }
    if plan.dependency_commands:
        _print()
        _print(f'{Colors.YELLOW}{Colors.BOLD}Dependencies (shell commands):{Colors.NC}')
        for platform_key, cmds in plan.dependency_commands.items():
            _print(f'  {Colors.YELLOW}[{platform_key}]{Colors.NC}')
            for cmd in cmds:
                marker = f' {Colors.GREEN}[re-rooted]{Colors.NC}' if (platform_key, cmd) in rerooted_commands else ''
                _print(f'    $ {cmd}{marker}')

    # Base config-home paths an isolated run moved into its profile (green)
    if plan.rerooted_paths:
        _print()
        heading = 'Re-rooted into the profile (base config-home paths of an isolated run):'
        _print(f'{Colors.GREEN}{Colors.BOLD}{heading}{Colors.NC}')
        for item in plan.rerooted_paths:
            _print(f'  {Colors.GREEN}[re-rooted]{Colors.NC} {_rerooted_path_line(item)}')

    # Destinations inside a linked entry: the source's run wrote them into
    # the shared directory, so this run writes nothing there (a write would
    # go through the link into the source)
    if plan.linked_downloads:
        provided_by = plan.link_plan.source if plan.link_plan is not None else LINK_SOURCE_BASE
        _print()
        _print(
            f'{Colors.BOLD}Provided by links (files-to-download destinations inside linked entries, '
            f'written by the source):{Colors.NC}',
        )
        for dest, linked_entry in plan.linked_downloads:
            _print(f'  {Colors.CYAN}[linked]{Colors.NC} {_linked_download_line(dest, linked_entry, provided_by)}')

    # Auto-injected items section (green)
    if plan.auto_injected_items:
        _print()
        _print(f'{Colors.GREEN}{Colors.BOLD}Auto-update controls (version pinned):{Colors.NC}')
        for item in plan.auto_injected_items:
            _print(f'  {Colors.GREEN}[auto] {item}{Colors.NC}')

    # Machine-wide writes of an isolated run (yellow): everything that
    # leaves the profile directory is named before consent
    if plan.machine_wide_writes:
        _print()
        _print(f'{Colors.YELLOW}{Colors.BOLD}Machine-wide writes (shared by every profile on this machine):{Colors.NC}')
        for item in plan.machine_wide_writes:
            _print(f'  {Colors.YELLOW}[machine-wide]{Colors.NC} {item}')

    # Stale update controls other profiles hold: listed, never edited
    if plan.stale_controls_elsewhere:
        _print()
        _print(f'{Colors.YELLOW}{Colors.BOLD}Stale update controls in other profiles (not edited by this run):{Colors.NC}')
        for copy in plan.stale_controls_elsewhere:
            _print(f'  * {_stale_control_copy_line(copy)}')
        _print(f'  {STALE_CONTROLS_RERUN_NOTE}')

    # Attention section (red)
    has_attention = (
        plan.sensitive_paths or plan.unknown_keys or plan.account_key_warnings or plan.destination_warnings
    )
    if has_attention:
        _print()
        _print(f'{Colors.RED}{Colors.BOLD}[!] ATTENTION:{Colors.NC}')
        for account_warning in plan.account_key_warnings:
            _print(f'  {Colors.RED}[!] {account_warning}{Colors.NC}')
        for destination_warning in plan.destination_warnings:
            _print(f'  {Colors.RED}[!] {destination_warning}{Colors.NC}')
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


# Terminal escape sequences that can contaminate an interactive read: CSI
# sequences (including cursor-position reports like ESC[24;80R that a
# terminal queues in reply to queries from a full-screen prompt session),
# OSC sequences, DCS/SOS/PM/APC string sequences (terminal capability and
# graphics-protocol replies, body terminated by ST), SS3 function keys,
# and charset designators. Any remaining ESC byte is stripped ALONE: consuming the following character too would
# turn Alt+y (sent as ESC y by many terminals) into an empty answer and
# silently decline a clear consent, while a stray residue character merely
# triggers the re-prompt.
_TERMINAL_SEQUENCE_PATTERN = re.compile(
    r'\x1b\[[0-9;?<=>]*[A-Za-z~]'
    r'|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)'
    r'|\x1b[PX^_][^\x1b]*(?:\x1b\\)?'
    r'|\x1bO.'
    r'|\x1b[()*+][0-9A-Za-z]'
    r'|\x1b',
)


def _sanitize_interactive_input(raw: str) -> str:
    """Strip terminal escape sequences and control characters from input.

    An interactive line can arrive contaminated by terminal report
    sequences queued in the input buffer -- verified with a real pty: a
    cursor-position reply left by a full-screen prompt session prefixes the
    user's typed answer, so a visually clean ``y`` reads as
    ``ESC[24;80Ry``. Removes escape sequences and remaining C0 control
    characters, then strips surrounding whitespace. An Alt-modified key
    (sent as ESC plus the character) reduces to the bare character.

    Args:
        raw: The raw line as read from the interactive device.

    Returns:
        The cleaned user answer.
    """
    without_sequences = _TERMINAL_SEQUENCE_PATTERN.sub('', raw)
    without_controls = ''.join(
        ch for ch in without_sequences
        if (ch >= ' ' and ch != '\x7f') or ch == '\t'
    )
    return without_controls.strip()


def _flush_pending_terminal_input() -> None:
    """Discard queued unread bytes on the interactive input device.

    A consent prompt must never consume input queued before it rendered:
    late terminal query replies left by a full-screen prompt session, or
    stray type-ahead. POSIX flushes the terminal input queue via termios
    (the queue is a property of the terminal device, so flushing a fresh
    /dev/tty descriptor clears it for the subsequent read); Windows drains
    the console keyboard buffer. Best effort: any failure leaves the
    buffer untouched.
    """
    if sys.platform == 'win32':
        try:
            import msvcrt

            while msvcrt.kbhit():
                msvcrt.getwch()
        except (ImportError, OSError, AttributeError, TypeError):
            pass
        return
    try:
        import termios
    except ImportError:
        return
    # termios.error subclasses Exception directly, not OSError; a
    # non-standard stdin object (a test double, a wrapped stream) can
    # raise TypeError or AttributeError from fileno(), and best-effort
    # means none of these may escape
    try:
        if sys.stdin.isatty():
            termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
        else:
            with open('/dev/tty') as tty:
                termios.tcflush(tty.fileno(), termios.TCIFLUSH)
    except (OSError, ValueError, AttributeError, TypeError, termios.error):
        pass


# Returned by _read_user_input() for a line whose content was ENTIRELY
# terminal-report garbage: an empty string must keep meaning a deliberate
# Enter (the deny default in confirmations, confirm in the picker), so a
# fully-sanitized-away line surfaces as this answer and lands in each
# flow's unrecognized-input handling instead. Plain ASCII so the
# re-prompt warning renders on any console encoding; a user literally
# typing it gets the identical unrecognized-answer treatment.
_CONTAMINATED_INPUT_MARKER = '<terminal-noise>'


def _finalize_interactive_line(raw: str) -> str:
    """Sanitize a raw interactive line, marking all-garbage content.

    Args:
        raw: The raw line as read from the interactive device.

    Returns:
        The sanitized answer; _CONTAMINATED_INPUT_MARKER when the line had
        content but every character of it was terminal-report garbage.
    """
    cleaned = _sanitize_interactive_input(raw)
    if not cleaned and raw.strip():
        return _CONTAMINATED_INPUT_MARKER
    return cleaned


def _read_user_input(prompt: str) -> str:
    """Read one line of user input with /dev/tty fallback for piped stdin.

    On Unix systems, when stdin is not a TTY (e.g., curl | bash),
    attempts to read from /dev/tty as a best-effort fallback. This is
    a standard pattern used by sudo, ssh, and gpg. A Ctrl-C
    KeyboardInterrupt deliberately propagates to the caller so
    interactive flows can distinguish cancellation from an empty answer.
    The returned line is sanitized: terminal escape sequences and control
    characters never reach the caller, and a line consisting entirely of
    such garbage returns _CONTAMINATED_INPUT_MARKER rather than
    masquerading as a deliberate empty answer.

    Args:
        prompt: The prompt string to display.

    Returns:
        User's input string (sanitized and stripped), or empty string when
        no interactive input is available.
    """
    # Try stdin first if it's a TTY
    if sys.stdin.isatty():
        try:
            return _finalize_interactive_line(input(prompt))
        except EOFError:
            return ''

    # Best-effort /dev/tty fallback (Unix only)
    if sys.platform != 'win32':
        try:
            with open('/dev/tty') as tty:
                # Write prompt to stderr (stdout may be piped)
                sys.stderr.write(prompt)
                sys.stderr.flush()
                return _finalize_interactive_line(tty.readline())
        except (OSError, EOFError):
            pass

    # No interactive input available
    return ''


def _get_user_confirmation(prompt: str) -> str:
    """Get user input with /dev/tty fallback for piped stdin.

    Wraps _read_user_input(), converting Ctrl-C into an empty string so
    confirmation prompts treat cancellation as a denial. Pending unread
    terminal input is discarded first so a consent answer is never
    satisfied by bytes queued before the prompt rendered.

    Args:
        prompt: The prompt string to display.

    Returns:
        User's input string (sanitized), or empty string on
        EOF/error/Ctrl-C.
    """
    try:
        _flush_pending_terminal_input()
        return _read_user_input(prompt)
    except KeyboardInterrupt:
        return ''


def _ask_yes_no(prompt: str) -> bool:
    """Ask a y/N consent question with unrecognized-answer re-prompting.

    Up to three attempts: y/yes accepts, a deliberate Enter or n/no
    declines, and any other answer -- including the contaminated-input
    marker for an all-garbage line -- warns and re-prompts instead of
    silently counting as a denial. Every consent gate goes through this
    single loop so a mangled line is handled identically everywhere.

    Args:
        prompt: The prompt string to display.

    Returns:
        True only on explicit consent.
    """
    for _ in range(3):
        response = _get_user_confirmation(prompt)
        answer = response.lower()
        if answer in ('y', 'yes'):
            return True
        if answer in ('', 'n', 'no'):
            return False
        warning(f'Unrecognized answer {response!r}; type y to proceed or n to cancel.')
    return False


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
    if _ask_yes_no(f'{Colors.YELLOW}Proceed with installation? [y/N]: {Colors.NC}'):
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


def partition_os_env_variables(
    os_env_variables: dict[str, str | None],
    *,
    isolated: bool,
) -> tuple[dict[str, str | None], dict[str, str | None]]:
    """Split os-env-variables into the OS-level part and the profile-loader part.

    A base run writes every entry to the OS environment, so everything is
    OS-level and nothing goes to a loader. An isolated run writes only the
    MACHINE_WIDE_ENV_CONTROLS entries to the OS environment -- they hold the
    one Claude Code binary every profile uses -- and every other entry to its
    own env loader files, so a profile's variables reach that profile's
    sessions and nothing else on the machine. A machine-wide control never
    enters a loader file: an unset line there would strip the control from
    the profile's sessions after another profile pinned a version.

    Args:
        os_env_variables: The run's resolved os-env-variables (None values
            are deletion requests).
        isolated: Whether command-names creates an isolated environment.

    Returns:
        The (OS-level, loader) dicts, each keeping the input order.
    """
    if not isolated:
        return dict(os_env_variables), {}
    os_level = {k: v for k, v in os_env_variables.items() if k in MACHINE_WIDE_ENV_CONTROLS}
    loader = {k: v for k, v in os_env_variables.items() if k not in MACHINE_WIDE_ENV_CONTROLS}
    return os_level, loader


def generate_env_loader_files(
    os_env_vars: dict[str, str | None],
    command_names: list[str] | None,
    config_base_dir: Path | None,
) -> dict[str, Path]:
    """Generate shell-specific env loader files for OS environment variables.

    Creates Rustup-pattern env files holding ONLY os-env-variables (NOT
    user-settings.env, which is handled by Claude Code's settings-file env
    key). env.sh is sourced by launch.sh in the bash process that execs
    Claude Code, so every session receives the sets and unsets. env.fish,
    env.ps1 and env.cmd are generated for sourcing by hand, and no launcher
    or wrapper applies them: start.cmd, start.ps1 and the ~/.local/bin
    wrappers reference no loader, so the calling shell keeps its environment.

    Per-command files (when command_names provided):
        ~/.claude/{cmd}/env.sh      (Bash/Zsh)
        ~/.claude/{cmd}/env.fish    (Fish, if Fish installed)
        ~/.claude/{cmd}/env.ps1     (PowerShell, Windows only)
        ~/.claude/{cmd}/env.cmd     (CMD batch, Windows only)

    A None value is a deletion request and is rendered as an unset line in
    each shell's syntax, so a variable the profile's sessions inherit from
    the OS environment is removed when launch.sh sources env.sh at session
    start; a hand-sourced env.cmd, env.ps1 or env.fish applies the same
    unset to that shell. Loader files are toolbox-owned artifacts rebuilt on
    every run: when the dict is empty, the files are still rewritten
    header-only so that stale lines from a prior run stop reaching the
    sessions launch.sh starts.

    Args:
        os_env_vars: Dict of env var names to values. None values = deletions
                     (rendered as unset lines).
        command_names: List of command names, or None for non-command configs.
        config_base_dir: Base dir for per-command files (e.g., ~/.claude/{cmd}/).

    Returns:
        Dict mapping file type to generated Path (e.g., {"sh": Path(...)}).
    """
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
    for name, raw in os_env_vars.items():
        if raw is None:
            sh_lines.append(f'unset {name}')
            continue
        sh_lines.append(f'export {name}="{_escape_bash_double_quoted(str(raw))}"')
    sh_content = '\n'.join(sh_lines) + '\n'

    # Fish content
    fish_lines = [fish_header]
    for name, raw in os_env_vars.items():
        if raw is None:
            fish_lines.append(f'set -q {name}; and set -e {name}')
            continue
        # Escape special characters for double-quoted fish strings
        value = str(raw)
        escaped = value.replace('\\', '\\\\').replace('"', '\\"')
        fish_lines.append(f'set -gx {name} "{escaped}"')
    fish_content = '\n'.join(fish_lines) + '\n'

    # PowerShell content
    ps1_lines = [ps1_header]
    for name, raw in os_env_vars.items():
        if raw is None:
            ps1_lines.append(f'Remove-Item -Path Env:{name} -ErrorAction SilentlyContinue')
            continue
        # Single-quote for literal PowerShell strings; double internal single-quotes
        value = str(raw)
        escaped = value.replace("'", "''")
        ps1_lines.append(f"$env:{name} = '{escaped}'")
    ps1_content = '\n'.join(ps1_lines) + '\n'

    # CMD batch content (Windows only)
    cmd_header = '@echo off\n'
    cmd_header += 'REM Auto-generated by claude-code-toolbox -- do not edit manually\n'
    cmd_header += 'REM Re-run setup to update. Call this file to load OS env vars.\n'

    cmd_lines = [cmd_header]
    for name, raw in os_env_vars.items():
        if raw is None:
            cmd_lines.append(f'SET "{name}="')
            continue
        cmd_lines.append(f'SET "{name}={_escape_cmd_set_value(str(raw))}"')
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
            sudo_result = _run_with_sudo_fallback(
                ['installer', '-pkg', temp_path, '-target', '/'],
                timeout=600,
                tty_timeout=600,
            )
            if sudo_result is None:
                error('Cannot use sudo (non-interactive mode, no terminal available)')
                info(f'Run manually: sudo installer -pkg {temp_path} -target /')
                return False
            result = sudo_result
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
    _run_with_sudo_fallback(['apt-get', 'update'], timeout=600, tty_timeout=600)
    _run_with_sudo_fallback(
        ['apt-get', 'install', '-y', 'ca-certificates', 'curl', 'gnupg'],
        timeout=600,
        tty_timeout=600,
    )

    # Add NodeSource repository (the setup script must run as root)
    result = _run_with_sudo_fallback(
        ['-E', 'bash', '-c', 'curl -fsSL https://deb.nodesource.com/setup_lts.x | bash -'],
        timeout=600,
        tty_timeout=600,
    )

    if result is None:
        warning('Cannot use sudo (non-interactive mode, no terminal available)')
        return False
    if result.returncode != 0:
        return False

    # Install Node.js
    result = _run_with_sudo_fallback(['apt-get', 'install', '-y', 'nodejs'], timeout=600, tty_timeout=600)

    if result is not None and result.returncode == 0:
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


def needs_sudo_for_npm() -> bool:
    """Check if npm global directory requires sudo on Unix-like systems.

    Returns:
        True if sudo is needed for npm global installation, False otherwise.
    """
    if platform.system() == 'Windows':
        return False

    npm_path = shutil.which('npm')
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


def install_dependencies(dependencies: dict[str, list[str]] | None) -> list[str]:
    """Install dependencies from configuration.

    Returns:
        List of dependency commands that failed to install.
        An empty list means every dependency succeeded (or none were given).
    """
    if not dependencies:
        info('No dependencies to install')
        return []

    # Type annotation already ensures dependencies is a dict
    # Runtime type check removed as it's redundant with proper typing

    info('Installing dependencies...')

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
        return []

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
                # Sudo escalation is limited to plain global npm installs into a
                # non-writable prefix. Commands with shell control characters are
                # excluded so that user-authored compound shell strings are never
                # re-executed with elevated privileges, and a command that does
                # not parse as a simple argument vector is excluded so that a
                # malformed dependency stays a single recorded failure rather
                # than aborting the run.
                sudo_argv: list[str] | None = None
                if _is_global_npm_install(dep) and not _contains_shell_control_chars(expanded_dep):
                    try:
                        sudo_argv = shlex.split(expanded_dep)
                    except ValueError:
                        sudo_argv = None
                sudo_eligible = sudo_argv is not None and needs_sudo_for_npm()
                if sudo_eligible:
                    info('The npm global prefix is not writable by the current user; sudo may be requested')
                result = run_command(['bash', '-c', expanded_dep], capture_output=False)
                if result.returncode != 0 and sudo_eligible and sudo_argv is not None:
                    warning(f'Retrying with sudo: {expanded_dep}')
                    sudo_result = _run_with_sudo_fallback(
                        sudo_argv,
                        capture_output=False,
                        timeout=600,
                    )
                    if sudo_result is not None:
                        result = sudo_result
                    if sudo_result is None or sudo_result.returncode != 0:
                        if sudo_result is None:
                            warning('Cannot use sudo (non-interactive mode, no terminal available)')
                        info('Options:')
                        info(f'  1. Run manually: sudo {expanded_dep}')
                        info('  2. Configure npm for user installs:')
                        info('       npm config set prefix ~/.npm-global')
                        info('       export PATH=~/.npm-global/bin:$PATH')
                        info('  3. Reinstall Node.js with a version manager (see '
                             'https://docs.npmjs.com/resolving-eacces-permissions-errors-when-installing-packages-globally)')

        if result.returncode != 0:
            error(f'Failed to install dependency: {dep}')
            if system == 'Windows' and not is_admin() and 'winget' in dep and '--scope machine' in dep:
                warning('This may have failed due to lack of admin rights')
                info('Try: 1) Run as administrator, or 2) Use --scope user instead')
            warning('Continuing with other dependencies...')
            return False
        return True

    # Phase 1: Execute platform-specific dependencies
    failed_deps: list[str] = [dep for dep in platform_deps_list if not execute_dependency(dep)]

    # Phase 2: Refresh PATH from registry on Windows
    # This picks up any PATH changes from platform-specific installations (e.g., Node.js)
    if system == 'Windows' and platform_deps_list:
        refresh_path_from_registry()

    # Phase 3: Execute common dependencies
    failed_deps.extend(dep for dep in common_deps_list if not execute_dependency(dep))

    return failed_deps


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


def _write_file_atomic(destination: Path, write_to: Callable[[Path], object]) -> None:
    """Write a file atomically via a same-directory temp file and os.replace().

    The content is written to a uniquely-named temporary file in the
    destination's directory and then moved into place with os.replace(), so
    a reader (or a concurrent writer targeting the same path) can never
    observe a partially-written destination: it sees either the old file or
    the complete new one.

    Args:
        destination: Final file path; its parent directory must exist.
        write_to: Callable that writes the content to the given temp path.
    """
    fd, tmp_name = tempfile.mkstemp(dir=str(destination.parent), prefix=f'.{destination.name}.', suffix='.tmp')
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        # mkstemp creates the file with restrictive 0o600 permissions; align
        # with the destination's existing mode (or the conventional 0o644 for
        # new files) before writing. shutil.copy2 writers subsequently apply
        # the source file's mode on top, matching a direct copy's semantics.
        if os.name != 'nt':
            mode = destination.stat().st_mode & 0o777 if destination.exists() else 0o644
            os.chmod(tmp_path, mode)
        write_to(tmp_path)
        os.replace(tmp_path, destination)
    finally:
        tmp_path.unlink(missing_ok=True)


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

    # An existing destination is overwritten, except when the new content is
    # identical: a file two profiles install to the same machine-wide
    # destination is then left untouched
    exists = destination.exists()
    if exists:
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
            else:
                # Text file - fetch as text and write it UTF-8 encoded
                content = fetch_url_with_auth(
                    resolved_path, auth_param=auth_param, rate_limiter=rate_limiter, auth_cache=auth_cache,
                )
                content_bytes = content.encode('utf-8')
            if exists and _file_content_equals(destination, content_bytes):
                success(f'Unchanged: {filename}')
                return True
            _write_file_atomic(destination, lambda p: p.write_bytes(content_bytes))
            success(f'Downloaded: {filename}')
        else:
            # Copy from local path
            source_path = Path(resolved_path)
            if not source_path.exists():
                error(f'Local file not found: {resolved_path}')
                return False

            if exists and _file_content_equals(destination, source_path.read_bytes()):
                success(f'Unchanged: {filename}')
                return True
            # Copy the file
            _write_file_atomic(destination, lambda p: shutil.copy2(source_path, p))
            success(f'Copied: {filename} from {source_path}')

        return True
    except Exception as e:
        error(f'Failed to handle {filename}: {e}')
        return False


def _file_content_equals(path: Path, content: bytes) -> bool:
    """Report whether a file holds exactly the given bytes.

    Args:
        path: The file to compare.
        content: The bytes a write would store.

    Returns:
        True when the file exists and its content equals the bytes; False
        when it differs or cannot be read.
    """
    try:
        return path.read_bytes() == content
    except OSError:
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


def _download_destination(source: str, dest: str) -> Path:
    """Resolve the file a files-to-download entry writes to.

    Expands the destination with normalize_tilde_path() (WSL-safe tilde
    expansion) and appends the source filename when the destination names a
    directory: it ends with a separator, or it exists as a directory.

    Args:
        source: The entry's source path or URL.
        dest: The entry's destination as written.

    Returns:
        The final file path.
    """
    dest_path = Path(normalize_tilde_path(dest))
    if dest.endswith(('/', '\\')) or (dest_path.exists() and dest_path.is_dir()):
        dest_path = dest_path / _source_filename(source)
    return dest_path


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

        valid_downloads.append((str(source), _download_destination(str(source), str(dest))))

    # Entries resolving to the same final file would race in the parallel
    # download phase; keep only the last one (later-overrides-earlier
    # semantics) and warn about each skipped entry.
    last_by_dest: dict[Path, int] = {}
    for idx, (_, dest_path) in enumerate(valid_downloads):
        last_by_dest[dest_path] = idx
    if len(last_by_dest) < len(valid_downloads):
        deduped_downloads: list[tuple[str, Path]] = []
        for idx, (source_str, dest_path) in enumerate(valid_downloads):
            if last_by_dest[dest_path] != idx:
                warning(
                    f"Multiple entries resolve to the same destination '{dest_path}': "
                    f"skipping earlier source '{source_str}'",
                )
                continue
            deduped_downloads.append((source_str, dest_path))
        valid_downloads = deduped_downloads

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


# Every exception raised inside install_claude() is caught by its own
# catch-all handler and reported as a False return, so the docstring carries
# no Raises section; DOC501 cannot see the catch-all.
def install_claude(version: str | None = None, *, keep_installed: bool = False) -> bool:
    """Install Claude Code if needed.

    When install_claude.py sits beside this file (the PyPI wheel ships both
    scripts and every bootstrap wrapper stages them together), it runs under
    the interpreter already executing this setup, on every platform: the
    installer needs only the standard library. Without a sibling copy, the
    platform bootstrap script is downloaded and executed.

    Args:
        version: Specific Claude Code version to install (e.g., "1.0.128").
                If None, installs the latest version.
        keep_installed: Whether version is the version already installed,
                so the installer runs to keep it rather than to change it.

    Returns:
        True if installation succeeded, False otherwise.
    """  # noqa: DOC501
    if version:
        if keep_installed:
            info(f'Running the installer to keep Claude Code version {version}...')
        else:
            info(f'Installing Claude Code version {version}...')
        # Set environment variable for the installer scripts to use
        os.environ['CLAUDE_CODE_TOOLBOX_VERSION'] = version
    else:
        info('Installing Claude Code (latest version)...')

    system = platform.system()
    temp_installer: str | None = None

    try:
        # The sibling installer runs under this process's own interpreter.
        # It is never launched through `uv run`: under uvx the sibling lives
        # inside uv's cache, and uv refuses to run a script whose directory
        # is inside the cache.
        local_installer = Path(__file__).resolve().parent / 'install_claude.py'
        if local_installer.is_file():
            info('Using local installer script')
            result = run_command([sys.executable, str(local_installer)], capture_output=False)
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


# The three scopes `claude mcp add/remove` operate on. Scope 'profile' is
# file-based (create_mcp_config_file) and never reaches the Claude CLI.
MCP_CLI_SCOPES: tuple[str, str, str] = ('user', 'local', 'project')


class McpServerActionPlan(NamedTuple):
    """Decision for one (server, scope) pair at the MCP configuration step.

    `claude mcp remove` deletes the stored MCP OAuth tokens and OAuth client
    configuration of http/sse servers (keyed by name plus a hash of the
    server's type/url/headers), and `claude mcp add` restores only the
    connection config, never tokens. The plan therefore skips the CLI
    remove/add cycle entirely for servers whose live configuration already
    equals the declared one, so an unchanged authenticated server keeps its
    tokens across setup runs.
    """

    action: str  # 'skip' (live config matches; no add needed) or 'reconfigure'
    remove_scopes: list[str]  # scopes that actually hold the name and need removal
    clears_oauth: bool  # removal will clear stored OAuth tokens (live http/sse entry)


def _ambient_claude_config_dir() -> str | None:
    """Read the CLAUDE_CONFIG_DIR value the environment hands to the Claude CLI.

    The CLI accepts any non-empty value as a configuration-directory override,
    so an empty variable is the only state that means "unset" -- a value made
    of whitespace still redirects the CLI. Every toolbox decision that depends
    on the variable reads it here, so they all agree on what "set" means.

    Returns:
        The raw variable value, or None when the variable carries nothing.
    """
    return os.environ.get('CLAUDE_CONFIG_DIR') or None


def _claude_global_config_file(artifact_base_dir: Path | None) -> Path:
    """Resolve the .claude.json file `claude mcp` commands operate on.

    Mirrors the Claude CLI's own resolution: CLAUDE_CONFIG_DIR (which the
    toolbox sets to the isolated profile directory via artifact_base_dir)
    wins over the home directory.

    Args:
        artifact_base_dir: Isolated profile directory, or None for the
            base environment.

    Returns:
        Path to the .claude.json file holding user- and local-scope servers.
    """
    if artifact_base_dir is not None:
        return artifact_base_dir / '.claude.json'
    env_dir = _ambient_claude_config_dir()
    if env_dir:
        return Path(env_dir) / '.claude.json'
    return get_real_user_home() / '.claude.json'


def _read_json_object(path: Path) -> dict[str, Any] | None:
    """Read a JSON object file tolerantly.

    Args:
        path: File to read.

    Returns:
        The parsed object, {} when the file does not exist (a valid empty
        state), or None when the file exists but cannot be parsed as a JSON
        object (the caller must treat the state as unknown).
    """
    try:
        if not path.is_file():
            return {}
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if isinstance(data, dict):
        return cast(dict[str, Any], data)
    return None


def _normalize_project_dir_key(value: str) -> str:
    """Normalize a projects-section path key for comparison.

    The Claude CLI keys the projects section by the working directory using
    forward slashes (on Windows: uppercase drive letter, no trailing slash).
    Comparison is case-insensitive on Windows because drive-letter casing is
    not guaranteed across producers of the path.

    Args:
        value: Raw path key or filesystem path string.

    Returns:
        Normalized comparison key.
    """
    key = value.replace('\\', '/').rstrip('/')
    return key.casefold() if platform.system() == 'Windows' else key


def _find_project_entry(
    projects: dict[str, Any],
    project_dir: Path,
) -> dict[str, Any] | None:
    """Find the projects-section entry matching a directory.

    Falls back to symlink-resolved comparison so a key recorded through a
    symlinked path (for example /var vs /private/var on macOS) still matches
    the physical working directory.

    Args:
        projects: The .claude.json projects section.
        project_dir: Directory to look up (normally the current working
            directory, which is what `claude mcp --scope local` operates on).

    Returns:
        The matching project entry, or None when the directory has none.
    """
    targets = {_normalize_project_dir_key(str(project_dir))}
    with contextlib.suppress(OSError):
        targets.add(_normalize_project_dir_key(str(project_dir.resolve())))
    for key, value in projects.items():
        if isinstance(value, dict) and _normalize_project_dir_key(str(key)) in targets:
            return cast(dict[str, Any], value)
    for key, value in projects.items():
        if not isinstance(value, dict):
            continue
        try:
            resolved_key = _normalize_project_dir_key(str(Path(str(key)).resolve()))
        except OSError:
            continue
        if resolved_key in targets:
            return cast(dict[str, Any], value)
    return None


def _normalize_mcp_env_config(env_config: object) -> list[str] | None:
    """Normalize a server's env value to a list of KEY=value strings.

    Args:
        env_config: The YAML env value (string, list, or None).

    Returns:
        List of env var strings (empty when env_config is falsy), or None
        when the value has an invalid type.
    """
    if not env_config:
        return []
    if isinstance(env_config, str):
        return [env_config]
    if isinstance(env_config, list):
        return [str(item) for item in cast(list[object], env_config)]
    return None


def _mcp_env_list_to_dict(env_list: list[str]) -> dict[str, str]:
    """Convert KEY=value strings to the env dict the Claude CLI stores.

    Args:
        env_list: Environment variable assignments.

    Returns:
        Mapping of variable names to values; entries without '=' are dropped,
        matching the CLI's rejection of malformed assignments.
    """
    env_dict: dict[str, str] = {}
    for item in env_list:
        key, sep, value = item.partition('=')
        if sep:
            env_dict[key] = value
    return env_dict


def _build_expected_mcp_entry(server: dict[str, Any]) -> dict[str, Any] | None:
    """Predict the mcpServers entry `claude mcp add` writes for a server spec.

    Mirrors the add-command construction of configure_mcp_server() per
    platform so the result is byte-comparable with the live entry: stdio
    commands get YAML args appended (quoted), tildes expanded, and on Windows
    backslashes converted plus the `cmd /c` wrapper applied to npx commands,
    with the declared env attached; http/sse entries carry url and parsed
    headers.

    Args:
        server: MCP server spec from the resolved YAML config.

    Returns:
        The expected stored entry, or None when the spec cannot produce an
        add command (missing url/command or invalid env type).
    """
    transport = server.get('transport')
    url = server.get('url')
    command = server.get('command')

    if transport and url:
        entry: dict[str, Any] = {'type': str(transport), 'url': str(url)}
        header = server.get('header')
        if header:
            key, sep, value = str(header).partition(':')
            if sep:
                entry['headers'] = {key.strip(): value.strip()}
        return entry

    if command:
        env_list = _normalize_mcp_env_config(server.get('env'))
        if env_list is None:
            return None
        full_command = str(command)
        args_list = server.get('args')
        if args_list and isinstance(args_list, list):
            quoted = ' '.join(shlex.quote(str(a)) for a in cast(list[object], args_list))
            full_command = f'{full_command} {quoted}'
        expanded = expand_tildes_in_command(full_command)
        if platform.system() == 'Windows':
            expanded = expanded.replace('\\', '/')
            command_str = f'cmd /c {expanded}' if 'npx' in expanded else expanded
            try:
                parts = shlex.split(command_str)
            except ValueError:
                parts = command_str.split()
        else:
            parts = build_platform_aware_command(expanded)
        if not parts:
            return None
        return {
            'type': 'stdio',
            'command': parts[0],
            'args': parts[1:],
            'env': _mcp_env_list_to_dict(env_list),
        }

    return None


def _mcp_entries_equal(live: object, expected: dict[str, Any]) -> bool:
    """Compare a live mcpServers entry with the expected one.

    Only toolbox-controlled fields participate (type, command, url, args,
    env, headers); fields the CLI may add on its own never force a
    reconfiguration. An absent args/env/headers key is equivalent to an
    empty one, matching the CLI's varying serialization across transports.

    Args:
        live: The stored entry (any type; non-dicts never match).
        expected: Entry from _build_expected_mcp_entry().

    Returns:
        True when the live entry matches the declared configuration.
    """
    if not isinstance(live, dict):
        return False
    live_dict = cast(dict[str, Any], live)

    def _normalized(entry: dict[str, Any]) -> dict[str, Any]:
        return {
            'type': entry.get('type'),
            'command': entry.get('command'),
            'url': entry.get('url'),
            'args': entry.get('args') or [],
            'env': entry.get('env') or {},
            'headers': entry.get('headers') or {},
        }

    return _normalized(live_dict) == _normalized(expected)


def _read_live_mcp_entries(
    name: str,
    artifact_base_dir: Path | None,
) -> dict[str, Any] | None:
    """Read the live entry stored for a server name at each CLI scope.

    Reads the same files `claude mcp` mutates: .claude.json (user scope at
    the top level, local scope under the current working directory's
    projects entry) and .mcp.json in the current working directory (project
    scope).

    Args:
        name: MCP server name.
        artifact_base_dir: Isolated profile directory, or None.

    Returns:
        Mapping of scope to the raw stored entry (None when the scope does
        not hold the name), or None when any config file is unreadable and
        the live state is therefore unknown.
    """
    global_config = _read_json_object(_claude_global_config_file(artifact_base_dir))
    project_file = _read_json_object(Path.cwd() / '.mcp.json')
    if global_config is None or project_file is None:
        return None

    entries: dict[str, Any] = dict.fromkeys(MCP_CLI_SCOPES)

    user_servers = global_config.get('mcpServers')
    if isinstance(user_servers, dict):
        entries['user'] = cast(dict[str, Any], user_servers).get(name)

    projects = global_config.get('projects')
    if isinstance(projects, dict):
        project_entry = _find_project_entry(cast(dict[str, Any], projects), Path.cwd())
        if project_entry is not None:
            local_servers = project_entry.get('mcpServers')
            if isinstance(local_servers, dict):
                entries['local'] = cast(dict[str, Any], local_servers).get(name)

    project_servers = project_file.get('mcpServers')
    if isinstance(project_servers, dict):
        entries['project'] = cast(dict[str, Any], project_servers).get(name)

    return entries


def _plan_mcp_server_action(
    server: dict[str, Any],
    scope: str,
    artifact_base_dir: Path | None,
) -> McpServerActionPlan:
    """Plan the MCP configuration action for one (server, scope) pair.

    Skips the CLI remove/add cycle only on positive proof that the live
    entry at the target scope equals the declared configuration; any
    unreadable or ambiguous state falls back to a full reconfiguration with
    removal from every CLI scope. Removal is always restricted to scopes
    that actually hold the name, so a `claude mcp remove` never runs (and
    never clears http/sse OAuth tokens) against a scope it has nothing to
    remove from.

    Args:
        server: MCP server spec (with a single resolved scope).
        scope: The resolved target scope for this pass.
        artifact_base_dir: Isolated profile directory, or None.

    Returns:
        The action plan.
    """
    full_reconfigure = McpServerActionPlan(
        action='reconfigure',
        remove_scopes=list(MCP_CLI_SCOPES),
        clears_oauth=False,
    )
    name = server.get('name')
    if not name:
        return full_reconfigure

    live = _read_live_mcp_entries(str(name), artifact_base_dir)
    if live is None:
        return full_reconfigure

    present_scopes = [s for s in MCP_CLI_SCOPES if live.get(s) is not None]

    if scope == 'profile':
        # Profile servers never get a CLI add; only stale CLI-scope entries
        # (which would shadow or duplicate the profile config) need removal
        return McpServerActionPlan(
            action='skip',
            remove_scopes=present_scopes,
            clears_oauth=False,
        )

    expected = _build_expected_mcp_entry(server)
    if expected is None:
        return full_reconfigure

    target_live = live.get(scope)
    stale_scopes = [s for s in present_scopes if s != scope]
    if target_live is not None and _mcp_entries_equal(target_live, expected):
        return McpServerActionPlan(
            action='skip',
            remove_scopes=stale_scopes,
            clears_oauth=False,
        )

    live_type = target_live.get('type') if isinstance(target_live, dict) else None
    return McpServerActionPlan(
        action='reconfigure',
        remove_scopes=present_scopes,
        clears_oauth=live_type in ('http', 'sse'),
    )


def _remove_mcp_server_from_cli_scopes(
    claude_cmd: str | Path,
    name: str,
    scopes: list[str],
    nodejs_dir: str | None,
    artifact_base_dir: Path | None,
) -> None:
    """Remove an MCP server from the given CLI scopes best-effort.

    Uses the same execution environment as the add operation (Git Bash on
    Windows, direct subprocess on Unix) so removal and add behave
    symmetrically. Exit codes are ignored: the Claude CLI returns non-zero
    for a scope that lacks the server, which is expected, not an error.

    Args:
        claude_cmd: Resolved Claude CLI command.
        name: MCP server name.
        scopes: CLI scopes to remove from (subset of MCP_CLI_SCOPES).
        nodejs_dir: Verified Node.js directory path, or None if not verified.
        artifact_base_dir: Isolated profile directory, or None.
    """
    if not scopes:
        return

    info(f'Removing existing MCP server {name} (scopes: {", ".join(scopes)})...')

    if platform.system() == 'Windows':
        # Windows: Use bash execution for consistency with the add operation
        # (same PATH, shell, and MSYS settings), preventing "not found"
        # errors due to asymmetric execution
        env = _prepare_windows_bash_env(claude_cmd, nodejs_dir)

        remove_extra_env: dict[str, str] = {'PATH': env.unix_explicit_path}
        if artifact_base_dir is not None:
            remove_extra_env['CLAUDE_CONFIG_DIR'] = str(artifact_base_dir)

        for remove_scope in scopes:
            bash_cmd = (
                f'"{env.unix_claude_cmd}" mcp remove --scope {remove_scope} {name}'
            )
            run_bash_command(
                bash_cmd, capture_output=True, login_shell=True,
                extra_env=remove_extra_env,
            )
    else:
        # Unix: Direct subprocess execution
        remove_env: dict[str, str] | None = None
        if artifact_base_dir is not None:
            remove_env = {**os.environ, 'CLAUDE_CONFIG_DIR': str(artifact_base_dir)}

        for remove_scope in scopes:
            remove_cmd = [str(claude_cmd), 'mcp', 'remove', '--scope', remove_scope, name]
            run_command(remove_cmd, capture_output=True, env=remove_env)


def configure_mcp_server(
    server: dict[str, Any],
    nodejs_dir: str | None = None,
    artifact_base_dir: Path | None = None,
    remove_scopes: list[str] | None = None,
) -> bool:
    """Configure a single MCP server.

    Args:
        server: MCP server spec with a single resolved scope.
        nodejs_dir: Verified Node.js directory path, or None if not verified.
        artifact_base_dir: Isolated profile directory, or None.
        remove_scopes: CLI scopes to remove the name from before adding.
            None removes from every CLI scope; an empty list skips removal
            entirely (the caller has verified no scope holds the name).

    Returns:
        True when the server ends up configured (or removal-only for
        profile scope succeeded), False on failure.
    """
    name = server.get('name')
    scope = server.get('scope', 'user')
    transport = server.get('transport')
    url = server.get('url')
    command = server.get('command')
    header = server.get('header')

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
        # Remove existing MCP server entries to avoid conflicts: when servers
        # with the same name exist at multiple scopes, local-scoped servers
        # take precedence, followed by project, then user. The caller narrows
        # remove_scopes to the scopes that actually hold the name because
        # `claude mcp remove` clears stored OAuth tokens of http/sse servers;
        # None (direct calls) removes from every CLI scope
        scopes_to_remove = list(MCP_CLI_SCOPES) if remove_scopes is None else list(remove_scopes)
        _remove_mcp_server_from_cli_scopes(
            claude_cmd, str(name), scopes_to_remove, nodejs_dir, artifact_base_dir,
        )

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
            # Non-variadic --transport precedes positional arguments per Claude
            # CLI syntax; variadic --header MUST come AFTER positional arguments
            # (name, url) to prevent Commander.js from consuming positionals as
            # additional header values.
            # See: https://github.com/anthropics/claude-code/issues/2341

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

                # Single-quote --header (via shlex.quote) so a ${VAR} placeholder is
                # passed to `claude mcp add` literally and stored verbatim in the config;
                # Claude Code expands it from the environment at runtime. Double-quoting
                # would let Git Bash expand ${VAR} at setup time, baking the resolved value
                # (or an empty string when the variable is unset) into the config instead.
                # This matches the Unix branch and escapes any embedded special characters.
                header_part = f' --header {shlex.quote(header)}' if header else ''

                bash_cmd = (
                    f'"{env.unix_claude_cmd}" mcp add --scope {scope} '
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
                # Single-quote the header (via shlex.quote) so a ${VAR} placeholder is
                # passed to `claude mcp add` literally and stored verbatim; Claude Code
                # expands it at runtime. Double-quoting would let bash expand ${VAR} at
                # setup time, baking the resolved value (or an empty string) into the config.
                header_part = f' --header {shlex.quote(header)}' if header else ''
                bash_cmd = (
                    f'{shlex.quote(str(claude_cmd))} mcp add --scope {shlex.quote(scope)} '
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

            # Normalize env to list for consistent handling (supports both string and list syntax)
            normalized_env = _normalize_mcp_env_config(server.get('env'))
            if normalized_env is None:
                error(f'Invalid env format for {name}: expected string or list')
                return False
            env_list: list[str] = normalized_env

            # When args is provided separately, combine command + args into full command string
            args_list = server.get('args')
            if args_list and isinstance(args_list, list):
                command = command + ' ' + ' '.join(shlex.quote(str(a)) for a in args_list)

            # Expand tildes before any splitting so ~/ paths work on every
            # platform and quoted arguments survive (shlex-aware splitting
            # happens exactly once, inside build_platform_aware_command)
            command = expand_tildes_in_command(command)

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

                # Single-quote --env (via shlex.quote) so a ${VAR} placeholder in an env
                # value is passed literally and expanded by Claude Code at runtime, matching
                # the Unix stdio path which passes --env as argv. Double-quoting would let
                # Git Bash expand ${VAR} at setup time.
                env_flags = ' '.join(f'--env {shlex.quote(e)}' for e in env_list) if env_list else ''
                env_part = f' {env_flags}' if env_flags else ''

                # Build command string for STDIO
                # npx needs cmd /c wrapper on Windows even in bash
                # Tildes are already expanded (produces C:\Users\...); convert to
                # forward slashes so Git Bash does not see Windows separators
                expanded_command = command.replace('\\', '/')
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
                # Unix-like systems - execute directly (tildes already expanded
                # into base_cmd via build_platform_aware_command)
                info(f'Configuring stdio MCP server {name}...')

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


def _strict_hidden_registration_note(scopes: list[str]) -> str:
    """Say where a server strict mode hides from the isolated sessions still lives.

    A ``project``-scope registration is a .mcp.json file in the directory setup
    ran in, which strict mode hides from the isolated sessions but leaves for
    every other session opened there. A ``user``- or ``local``-scope
    registration goes through `claude mcp add` with CLAUDE_CONFIG_DIR pointing
    at the isolated profile, so it lands in the profile's own .claude.json --
    the file only the isolated sessions read, and exactly the file strict mode
    makes them ignore.

    Args:
        scopes: The server's non-profile scopes.

    Returns:
        One sentence naming where the registration ends up.
    """
    if 'project' in scopes:
        return (
            'Its registration stays in the .mcp.json of the directory setup ran in, '
            'so sessions opened there outside the isolated commands still load it.'
        )
    return (
        "Its registration goes into the isolated profile's own .claude.json, which no "
        'session outside those commands reads, so it currently loads nowhere.'
    )


def configure_all_mcp_servers(
    servers: list[dict[str, Any]],
    profile_mcp_config_path: Path | None = None,
    nodejs_dir: str | None = None,
    artifact_base_dir: Path | None = None,
    command_names: list[str] | None = None,
) -> tuple[bool, list[dict[str, Any]], dict[str, int]]:
    """Configure all MCP servers from configuration.

    Handles combined scope configurations where servers can be added to multiple
    locations simultaneously. For example, `scope: [user, profile]` adds the server
    to both ~/.claude.json (for global access) and the profile MCP config file
    (for isolated profile sessions).

    When an isolated environment ends up with a profile MCP config, its
    launcher starts Claude Code with --strict-mcp-config, so those sessions read
    that file and nothing else. Servers declared at a non-profile scope alone
    are then invisible to the isolated commands, and -- because an isolated run
    registers user- and local-scope servers in the profile's own .claude.json --
    only a project-scope registration is left for any other session to load.
    Each such server is reported by name.

    Args:
        servers: List of MCP server configurations from YAML
        profile_mcp_config_path: Path for profile-scoped servers JSON file
        nodejs_dir: Verified Node.js directory path, or None if not verified.
        artifact_base_dir: Isolated profile directory, or None for the base
            environment.
        command_names: Command names the isolated environment registers, or
            None for a non-isolated run. Drives the strict-mode warning.

    Returns:
        Tuple of (success: bool, profile_servers: list, stats: dict)
        stats contains:
            - global_count: Number of servers with any non-profile scope
            - profile_count: Number of servers with profile scope
            - combined_count: Number of servers with BOTH global AND profile scopes
            - unchanged_count: (server, scope) pairs skipped as already configured
            - strict_hidden_count: Non-profile-only servers the isolated
              commands will not load because of --strict-mcp-config
    """
    # No early return on an empty list: the stale profile-config cleanup at
    # the end must still run, because the generated launcher enables
    # --strict-mcp-config --mcp-config via a runtime file-existence test and
    # a leftover mcp.json from a prior run would keep deselected or removed
    # profile servers active in every profile session
    if not servers:
        info('No MCP servers to configure')
    else:
        info('Configuring MCP servers...')

    # Collect servers for profile config
    profile_servers: list[dict[str, Any]] = []

    # Track statistics for accurate summary display
    stats = {
        'global_count': 0,        # Servers with any non-profile scope
        'profile_count': 0,       # Servers with profile scope
        'combined_count': 0,      # Servers with BOTH global AND profile scopes
        'unchanged_count': 0,     # (server, scope) pairs skipped as already configured
        'strict_hidden_count': 0,  # Servers the isolated commands will not load
    }

    # Servers registered only at non-profile scopes, as (name, scopes) pairs.
    # Whether the isolated commands end up hiding them depends on the profile
    # MCP config the block after this loop writes or removes.
    strict_hidden: list[tuple[str, list[str]]] = []

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
        if has_global and not has_profile:
            strict_hidden.append((server_name, non_profile_scopes))

        # Add to profile config if profile scope present
        if has_profile:
            profile_servers.append(server)
            # Profile servers are configured via create_mcp_config_file(); the
            # CLI scopes only need cleanup when a stale same-name entry (which
            # would shadow the profile config) is actually present
            if not has_global:
                server_copy = server.copy()
                server_copy['scope'] = 'profile'
                plan = _plan_mcp_server_action(server_copy, 'profile', artifact_base_dir)
                if plan.remove_scopes:
                    claude_cmd = find_command('claude')
                    if claude_cmd:
                        _remove_mcp_server_from_cli_scopes(
                            claude_cmd, server_name, plan.remove_scopes,
                            nodejs_dir, artifact_base_dir,
                        )
                    else:
                        warning(f'Cannot remove stale MCP server {server_name}: claude command not found')
                info(f'MCP server {server_name} has scope: profile (will be configured via --strict-mcp-config)')

        # Configure for each non-profile scope via claude mcp add, skipping
        # servers whose live configuration already matches the declared one:
        # `claude mcp remove` clears stored OAuth tokens of http/sse servers,
        # so an unnecessary remove/add cycle would de-authenticate an
        # unchanged server on every setup run
        for scope in non_profile_scopes:
            server_copy = server.copy()
            server_copy['scope'] = scope
            plan = _plan_mcp_server_action(server_copy, scope, artifact_base_dir)
            if plan.action == 'skip':
                stats['unchanged_count'] += 1
                success(f'MCP server {server_name} already configured (scope: {scope}, unchanged) - skipping')
                if plan.remove_scopes:
                    # Stale same-name entries at other scopes would shadow or
                    # duplicate the target-scope entry; remove only those,
                    # leaving the matching entry and its stored OAuth tokens
                    # untouched
                    claude_cmd = find_command('claude')
                    if claude_cmd:
                        _remove_mcp_server_from_cli_scopes(
                            claude_cmd, server_name, plan.remove_scopes,
                            nodejs_dir, artifact_base_dir,
                        )
                    else:
                        warning(f'Cannot remove stale MCP server {server_name}: claude command not found')
                continue
            if plan.clears_oauth:
                warning(
                    f'MCP server {server_name} configuration changed; the Claude CLI clears '
                    f'stored OAuth tokens when removing an http/sse server, so re-authenticate '
                    f'it via /mcp after setup if it used OAuth',
                )
            configure_mcp_server(
                server_copy, nodejs_dir=nodejs_dir,
                artifact_base_dir=artifact_base_dir,
                remove_scopes=plan.remove_scopes,
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

    # The launcher turns --strict-mcp-config on by testing for the profile MCP
    # config file, so the report below asks the same question the launcher will
    # ask -- after the writes above, whose outcome decides the answer
    strict_mode_active = profile_mcp_config_path is not None and profile_mcp_config_path.exists()
    if strict_mode_active and command_names and strict_hidden:
        stats['strict_hidden_count'] = len(strict_hidden)
        session_list = ', '.join(command_names)
        session_noun = 'session' if len(command_names) == 1 else 'sessions'
        for hidden_name, hidden_scopes in strict_hidden:
            scope_text = ', '.join(hidden_scopes)
            example_scope = f'[{hidden_scopes[0]}, profile]'
            warning(
                f'MCP server {hidden_name} (scope: {scope_text}) will not load in the '
                f'{session_list} {session_noun}: the profile MCP config makes the launcher '
                f'run Claude Code with --strict-mcp-config, so those sessions read only that '
                f'file. {_strict_hidden_registration_note(hidden_scopes)} Add profile to its '
                f'scope to serve it to those sessions, for example scope: {example_scope}.',
            )

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

        # Environment variables for the stdio child process (override the
        # default empty env)
        env_config = server.get('env')
        if command and env_config:
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


# Where each origin of a run's command names is set, as error messages name it
COMMAND_NAMES_SOURCES: dict[str, str] = {
    'cli': '--command-names',
    'env': 'CLAUDE_CODE_TOOLBOX_COMMAND_NAMES',
    'yaml': 'command-names',
}

# Where a run's --profile value is set, as error messages name it
PROFILE_SOURCES: dict[str, str] = {
    'cli': '--profile',
    'env': 'CLAUDE_CODE_TOOLBOX_PROFILE',
}

# The --profile value that refreshes every installed profile
ALL_PROFILES = 'all'

# The hidden argument a parent run passes to every child it starts -- the
# children of --profile all, and the dependents a source's Step 23 refreshes:
# the parent's report covers every installed profile, so a child lists none
# as unrefreshed and leaves the dependent refresh to the parent
CHILD_RUN_FLAG = '--child-run'

# The second --command-names entry that drops every alias of a profile:
# NAME,none installs the profile NAME under that one command
DROP_ALIASES_TOKEN = 'none'


class CommandNames(NamedTuple):
    """The command names of a run and where they came from.

    Attributes:
        names: The primary name first, then the aliases; empty for a run that
            installs into the base ~/.claude.
        origin: 'cli' for --command-names, 'env' for
            CLAUDE_CODE_TOOLBOX_COMMAND_NAMES, 'yaml' for the configuration's
            command-names, 'default' for a profile selected by name alone
            when no source lists its aliases, or None when no source names a
            command. For a remembered value this is the origin the manifest
            recorded, which the manifest records again.
        remembered: Whether this run took the list from the profile's
            manifest instead of a source of its own.
    """

    names: list[str]
    origin: str | None
    remembered: bool = False


def command_name_errors(names: list[str], source: str) -> list[str]:
    """Validate command names for use as a profile directory and a global command.

    Args:
        names: Command names to validate, primary first.
        source: The flag, variable, or configuration key the names came from,
            named in every message.

    Returns:
        One error message per invalid name; empty when every name is valid.
    """
    errors: list[str] = []
    for name in names:
        if not name.strip():
            errors.append(f'Invalid command name in {source}: names cannot be empty')
        elif ' ' in name:
            errors.append(f'Invalid command name "{name}" in {source}: names cannot contain spaces')
        elif not validate_command_name_for_path(name):
            errors.append(
                f'Invalid command name "{name}" in {source}: use only letters, digits, hyphens, and '
                'underscores, starting with a letter or digit',
            )
        elif name.casefold() in RESERVED_COMMAND_NAMES:
            reserved = ', '.join(sorted(RESERVED_COMMAND_NAMES))
            errors.append(
                f'Command name "{name}" in {source} is reserved; choose a name other than: {reserved}',
            )
    return errors


def yaml_command_names(config: dict[str, Any]) -> tuple[list[str], str | None]:
    """Read the configuration's own command-names.

    Args:
        config: The resolved configuration.

    Returns:
        The names (empty without the key) and an error message for a value
        that is neither a string nor a list, else None.
    """
    raw = config.get('command-names')
    if raw is None:
        return [], None
    if isinstance(raw, str):
        return [raw], None
    if isinstance(raw, list):
        return [str(item) for item in cast(list[object], raw)], None
    return [], f'Invalid command-names value: expected string or list, got {type(raw).__name__}'


def remembered_command_names(manifest: dict[str, Any] | None) -> tuple[list[str] | None, str | None]:
    """Read the command names a profile manifest remembers.

    A manifest remembers its names only when they were typed for the run or
    came from the environment; names the configuration declared are read
    from the configuration again on every run.

    Args:
        manifest: The profile manifest, or None when the profile is new.

    Returns:
        The remembered names and their recorded origin, or (None, None).
    """
    if manifest is None:
        return None, None
    origins = manifest.get('origins')
    origin = origins.get('command_names') if isinstance(origins, dict) else None
    names = manifest.get('command_names')
    if origin in ('cli', 'env') and isinstance(names, list) and names:
        return [str(item) for item in cast(list[object], names)], str(origin)
    return None, None


def profile_target_name(args: argparse.Namespace, config: dict[str, Any]) -> str | None:
    """Name the profile a run installs into.

    Args:
        args: Arguments after resolve_args().
        config: The resolved configuration.

    Returns:
        The primary command name: the --profile value, the first typed or
        environment command name, or the configuration's first name; None
        for the base profile.
    """
    if args.profile:
        return None if args.profile == 'base' else str(args.profile)
    typed = _parse_csv(args.command_names)
    if typed:
        return typed[0]
    names, _ = yaml_command_names(config)
    return names[0] if names else None


def _split_alias_drop(tokens: list[str], source: str) -> tuple[list[str], bool, list[str]]:
    """Separate the alias-dropping token from a typed command-names list.

    Args:
        tokens: The parsed --command-names tokens.
        source: The flag or variable the tokens came from.

    Returns:
        The names without the token, whether the token dropped the aliases,
        and an error when the token stands anywhere but second and last.
    """
    positions = [index for index, token in enumerate(tokens) if token.casefold() == DROP_ALIASES_TOKEN]
    if not positions:
        return tokens, False, []
    if positions == [1] and len(tokens) == 2:
        return tokens[:1], True, []
    names = [token for index, token in enumerate(tokens) if index not in positions]
    return names, False, [
        f'"{DROP_ALIASES_TOKEN}" in {source} drops every alias of the profile and must follow '
        f'the primary name alone: NAME,{DROP_ALIASES_TOKEN}',
    ]


def resolve_command_names(
    args: argparse.Namespace,
    config: dict[str, Any],
    manifest: dict[str, Any] | None = None,
) -> tuple[CommandNames, list[str]]:
    """Determine the command names of a run and validate them.

    Per profile the sources rank: a value typed for this run, an environment
    value for this run, the value the profile's manifest remembers when it
    was typed or came from the environment, the configuration's own list,
    then the default. A typed or environment list replaces the
    configuration's list whole and never merges with it: NAME,ALIAS... sets
    the aliases, NAME,none drops them. A single NAME on a profile that has
    a manifest selects the profile and takes its aliases from the next
    source; on a new profile it is the whole list, recorded as typed, also
    when it equals the configuration's primary name. --profile NAME re-runs
    the profile with the same ranking and no typed value; --profile base
    re-runs the base profile, which has no names. Every source goes through
    command_name_errors().

    Args:
        args: Arguments after resolve_args(), which records in args.origins
            where args.command_names and args.profile came from.
        config: The resolved configuration.
        manifest: The manifest of the profile the run installs into (see
            profile_target_name()), or None when the profile is new.

    Returns:
        The effective command names with their origin, and the validation
        errors (empty when the names are usable).
    """
    yaml_names, yaml_error = yaml_command_names(config)
    if yaml_error:
        return CommandNames([], None), [yaml_error]
    yaml_source = COMMAND_NAMES_SOURCES['yaml']
    profile = str(args.profile) if args.profile else None
    profile_source = PROFILE_SOURCES[args.origins['profile']] if profile else ''
    remembered, remembered_origin = remembered_command_names(manifest)

    if args.command_names is not None:
        origin = args.origins['command_names']
        source = COMMAND_NAMES_SOURCES[origin]
        tokens = _parse_csv(args.command_names) or []
        if not tokens:
            return CommandNames([], origin), [f'{source} requires at least one command name']
        names, drops_aliases, errors = _split_alias_drop(tokens, source)
        errors = errors or command_name_errors(names, source)
        if errors:
            return CommandNames(names, origin), errors
        if profile == 'base':
            return CommandNames(names, origin), [
                f'{source} names the profile "{names[0]}", but {profile_source} selects the base '
                f'profile, which has no command names; clear {source} to re-run the base profile.',
            ]
        if profile and names[0].casefold() != profile.casefold():
            return CommandNames(names, origin), [
                f'{source} names the profile "{names[0]}", but {profile_source} selects "{profile}"; '
                f'clear {source}, or pass {source} {profile}[,ALIAS...] to change the aliases of '
                f'"{profile}".',
            ]
        if len(names) > 1 or drops_aliases or manifest is None:
            return CommandNames(names, origin), []
        # A single name on an installed profile selects it; the aliases come
        # from the next source that lists them
        if remembered is not None:
            return CommandNames(remembered, remembered_origin, remembered=True), []
        if yaml_names and yaml_names[0].casefold() == names[0].casefold():
            return CommandNames(yaml_names, 'yaml'), command_name_errors(yaml_names, yaml_source)
        return CommandNames(names, origin), []

    if profile == 'base':
        if yaml_names:
            return CommandNames([], None), [
                f'The configuration declares command-names {", ".join(yaml_names)}, but '
                f'{profile_source} base re-runs the base profile, which has none; pass '
                f'--command-names {yaml_names[0]} to re-run that profile, or remove command-names '
                'from the configuration.',
            ]
        return CommandNames([], None), []

    if profile:
        if remembered is not None:
            return CommandNames(remembered, remembered_origin, remembered=True), []
        if yaml_names:
            if yaml_names[0].casefold() != profile.casefold():
                return CommandNames([], None), [
                    f"The configuration's command-names start with \"{yaml_names[0]}\", but "
                    f'{profile_source} selects "{profile}"; pass --command-names {profile}[,ALIAS...] '
                    f'to keep the profile under its name, or install the configuration under its '
                    f'own names without {profile_source}.',
                ]
            return CommandNames(yaml_names, 'yaml'), command_name_errors(yaml_names, yaml_source)
        return CommandNames([profile], 'default'), []

    if remembered is not None and yaml_names and remembered[0].casefold() == yaml_names[0].casefold():
        return CommandNames(remembered, remembered_origin, remembered=True), []
    return CommandNames(yaml_names, 'yaml' if yaml_names else None), command_name_errors(yaml_names, yaml_source)


def _format_names(names: list[str]) -> str:
    """Render a list of names for a message, 'none' when empty."""
    return ', '.join(names) if names else 'none'


def remembered_value_warnings(
    names: CommandNames,
    selection: ComponentSelection | None,
    configured_names: list[str],
    manifest: dict[str, Any] | None,
) -> list[str]:
    """Warn when a remembered value overrides a configuration value that changed.

    Args:
        names: The run's effective command names.
        selection: The run's component selection, or None without components.
        configured_names: The configuration's own command-names for this run.
        manifest: The manifest the remembered values came from.

    Returns:
        One warning per remembered key whose configuration value differs
        from the value the manifest recorded at install time.
    """
    if manifest is None:
        return []
    recorded = manifest.get('yaml_values')
    if not isinstance(recorded, dict):
        return []
    recorded_values = cast(dict[str, Any], recorded)
    warnings: list[str] = []
    if names.remembered:
        then = recorded_values.get('command_names')
        now = configured_names
        if isinstance(then, list) and [str(item) for item in cast(list[object], then)] != now:
            then_names = _format_names([str(item) for item in cast(list[object], then)])
            warnings.append(
                f'command-names: using the remembered value {_format_names(names.names)} [remembered]; '
                f"the configuration's command-names changed from {then_names} to {_format_names(now)} "
                'since the profile was installed. Pass --command-names to replace the remembered value.',
            )
    if selection is not None and selection.is_active and selection.remembered:
        then = recorded_values.get('components')
        if isinstance(then, list) and [str(item) for item in cast(list[object], then)] != selection.defaults:
            then_defaults = _format_names([str(item) for item in cast(list[object], then)])
            warnings.append(
                f'components: using the remembered selection {_format_names(selection.selected)} [remembered]; '
                f"the configuration's default components changed from {then_defaults} to "
                f'{_format_names(selection.defaults)} since the profile was installed. Pass --select, --with '
                'or --without to replace the remembered selection.',
            )
    return warnings


# Where each origin of a run's link values is set, as messages name it
LINK_DIRS_SOURCES: dict[str, str] = {
    'cli': '--link-dirs',
    'env': 'CLAUDE_CODE_TOOLBOX_LINK_DIRS',
    'yaml': 'link-dirs',
}
LINK_FROM_SOURCES: dict[str, str] = {
    'cli': '--link-from',
    'env': 'CLAUDE_CODE_TOOLBOX_LINK_FROM',
    'yaml': 'link-from',
}


def clear_variables_text(variables: list[str]) -> str:
    """Name environment variables with the bash and PowerShell commands that clear them.

    Args:
        variables: The variable names, at least one.

    Returns:
        The names, followed in parentheses by the unset and Remove-Item
        commands, for a remedy such as ``Clear <text> to ...``.
    """
    names = variables[-1] if len(variables) == 1 else f'{", ".join(variables[:-1])} and {variables[-1]}'
    powershell = ', '.join(f'Env:{variable}' for variable in variables)
    return f'{names} (unset {" ".join(variables)}, or Remove-Item {powershell} in PowerShell)'


def parse_link_dirs(value: object, source: str) -> tuple[list[str], list[str]]:
    """Parse a link-dirs value into the entries it names.

    Accepts a comma-separated string (the flag and its variable) or a list
    (the configuration key). Entries are matched without regard to case and
    returned in LINKABLE_PROFILE_DIRS order; all stands for every entry and
    none for no entry, each only on its own.

    Args:
        value: The value to parse.
        source: The flag, variable, or configuration key it came from, named
            in every message.

    Returns:
        The entries and the validation errors (empty when the value is usable).
    """
    if isinstance(value, str):
        tokens = [token.strip() for token in value.split(',')]
    elif isinstance(value, list):
        tokens = [str(token).strip() for token in cast(list[object], value)]
    else:
        return [], [f'Invalid {source} value: expected a comma-separated list of entries, got {type(value).__name__}']
    lowered = [token.casefold() for token in tokens]
    if any(not token for token in lowered):
        return [], [f'{source} lists an empty entry; use all, none, or any of: {", ".join(LINKABLE_PROFILE_DIRS)}']
    sentinels = [token for token in lowered if token in (LINK_ALL_TOKEN, LINK_NONE_TOKEN)]
    if sentinels and len(lowered) > 1:
        return [], [f'{source} "{sentinels[0]}" stands alone: it cannot be combined with other entries']
    if lowered == [LINK_ALL_TOKEN]:
        return list(LINKABLE_PROFILE_DIRS), []
    if lowered == [LINK_NONE_TOKEN]:
        return [], []
    unknown = [token for token in tokens if token.casefold() not in LINKABLE_PROFILE_DIRS]
    if unknown:
        return [], [
            f'{source} names unknown entries: {", ".join(unknown)}; '
            f'use all, none, or any of: {", ".join(LINKABLE_PROFILE_DIRS)}',
        ]
    if len(set(lowered)) != len(lowered):
        return [], [f'{source} lists an entry twice']
    wanted = set(lowered)
    return [entry for entry in LINKABLE_PROFILE_DIRS if entry in wanted], []


def link_source_errors(name: str, source: str) -> list[str]:
    """Validate a link-from value: base, or a command name of an installed profile.

    Args:
        name: The value to validate.
        source: The flag, variable, or configuration key it came from.

    Returns:
        One error message per problem; empty when the value is usable.
    """
    if name.strip().casefold() == LINK_SOURCE_BASE:
        return []
    return command_name_errors([name], source)


class LinkSpec(NamedTuple):
    """The links of a run and where each value came from.

    Attributes:
        dirs: The linked entries in LINKABLE_PROFILE_DIRS order; empty when
            the profile links nothing.
        source: The display name of the profile the links come from: base,
            or the primary command name of an isolated profile.
        dirs_origin: 'cli', 'env', 'yaml', or 'default' (nothing linked); for
            a remembered value, the origin the manifest recorded.
        source_origin: The same for the source.
        dirs_remembered: Whether the entries came from the profile's manifest.
        source_remembered: Whether the source came from the profile's manifest.
    """

    dirs: list[str]
    source: str
    dirs_origin: str
    source_origin: str
    dirs_remembered: bool = False
    source_remembered: bool = False

    @property
    def content_dirs(self) -> list[str]:
        """The linked entries that hold installed content."""
        return [entry for entry in self.dirs if entry != SESSIONS_PROFILE_DIR]

    @property
    def links_content(self) -> bool:
        """Whether the profile takes its configuration from the source."""
        return bool(self.content_dirs)

    @property
    def typed(self) -> bool:
        """Whether the entries were typed for this run or came from its environment."""
        return not self.dirs_remembered and self.dirs_origin in ('cli', 'env')

    def record(self) -> dict[str, Any] | None:
        """Render the manifest's link field.

        A linked profile records its entries whatever their origin. A profile
        that links nothing records that only when the none was typed or came
        from the environment (this run or a remembered one), so a re-run
        remembers it ahead of the configuration's link-dirs.

        Returns:
            The record (entries, source and per-key origins), or None for a
            configuration or default none.
        """
        if not self.dirs and self.dirs_origin not in ('cli', 'env'):
            return None
        return {
            'dirs': list(self.dirs),
            'source': self.source,
            'origins': {'dirs': self.dirs_origin, 'source': self.source_origin},
        }


NO_LINKS = LinkSpec([], LINK_SOURCE_BASE, 'default', 'default')


def link_dirs_value_text(spec: LinkSpec) -> str:
    """Name a run's link-dirs value the way it was given, for a message.

    Args:
        spec: The run's links.

    Returns:
        The flag with its value, the variable with its value, the
        configuration key with its list, or the remembered value.
    """
    entries = ','.join(spec.dirs) or LINK_NONE_TOKEN
    if spec.dirs_remembered:
        return f'the remembered link-dirs value ({_format_names(spec.dirs)})'
    if spec.dirs_origin == 'env':
        return f'{LINK_DIRS_SOURCES["env"]}={entries}'
    if spec.dirs_origin == 'yaml':
        return f'{LINK_DIRS_SOURCES["yaml"]} [{_format_names(spec.dirs)}]'
    return f'{LINK_DIRS_SOURCES["cli"]} {entries}'


def link_source_value_text(spec: LinkSpec) -> str:
    """Name a run's link-from value the way it was given, for a message.

    Args:
        spec: The run's links.

    Returns:
        The flag with its value, the variable with its value, the
        configuration key with its value, or the remembered value.
    """
    if spec.source_remembered:
        return f'the remembered link-from value ({spec.source})'
    if spec.source_origin == 'env':
        return f'{LINK_FROM_SOURCES["env"]}={spec.source}'
    if spec.source_origin == 'yaml':
        return f'{LINK_FROM_SOURCES["yaml"]} {spec.source}'
    return f'{LINK_FROM_SOURCES["cli"]} {spec.source}'


def link_environment_variables(spec: LinkSpec) -> list[str]:
    """List the link variables a run's values came from, so a refusal can say how to clear them.

    Args:
        spec: The run's links.

    Returns:
        CLAUDE_CODE_TOOLBOX_LINK_DIRS and CLAUDE_CODE_TOOLBOX_LINK_FROM,
        each when its value was read from the environment for this run.
    """
    return [
        variable
        for variable, origin, remembered in (
            (LINK_DIRS_SOURCES['env'], spec.dirs_origin, spec.dirs_remembered),
            (LINK_FROM_SOURCES['env'], spec.source_origin, spec.source_remembered),
        )
        if origin == 'env' and not remembered
    ]


def unlinked_summary_lines(spec: LinkSpec | None, configured_dirs: list[str] | None) -> list[str]:
    """Name a none that sets the configuration's link-dirs aside, for the installation summary.

    Args:
        spec: The run's links, or None for a base run.
        configured_dirs: The entries the configuration's own link-dirs
            names, or None when it declares no link-dirs.

    Returns:
        One line when the run links nothing because a typed, environment or
        remembered none overrides a configuration that names entries, with
        the origin marker and, for a remembered value, the flag that
        replaces it; empty otherwise.
    """
    if spec is None or spec.dirs or spec.dirs_origin not in ('cli', 'env') or not configured_dirs:
        return []
    marker = origin_marker(spec.dirs_origin, remembered=spec.dirs_remembered)
    explanation = f"the configuration's link-dirs [{', '.join(configured_dirs)}] is not applied"
    if spec.dirs_remembered:
        explanation += '; pass --link-dirs to replace the remembered value'
    return [f'Links: {LINK_NONE_TOKEN}{marker} ({explanation})']


def manifest_link_record(manifest: dict[str, Any] | None) -> dict[str, Any] | None:
    """Read the link record of a manifest as LinkSpec.record() wrote it.

    Args:
        manifest: The profile manifest, or None when the profile is new.

    Returns:
        The record, whose ``dirs`` list is empty for a profile that recorded
        a typed or environment none, or None when the manifest records no
        link at all.
    """
    if manifest is None:
        return None
    record = manifest.get('link')
    if not isinstance(record, dict):
        return None
    record_dict = cast(dict[str, Any], record)
    if not isinstance(record_dict.get('dirs'), list):
        return None
    return record_dict


def manifest_link(manifest: dict[str, Any] | None) -> dict[str, Any] | None:
    """Read the link record of a manifest when the profile links at least one entry.

    A recorded none (an empty ``dirs`` list) is a remembered value, not a
    link: a profile that recorded one is neither a dependent of the source
    the record names nor a partially linked profile.

    Args:
        manifest: The profile manifest, or None when the profile is new.

    Returns:
        The record, or None when the manifest records no link or a none.
    """
    record = manifest_link_record(manifest)
    if record is None or not record['dirs']:
        return None
    return record


def remembered_link(manifest: dict[str, Any] | None) -> tuple[tuple[list[str], str] | None, tuple[str, str] | None]:
    """Read the link values a profile manifest remembers.

    A content link is remembered whatever its origin, because a profile that
    links content takes its configuration from the source and reads no
    link-dirs of its own; a projects-only link and a recorded none, like
    every other value, are remembered only when they were typed or came from
    the environment.

    Args:
        manifest: The profile manifest, or None when the profile is new.

    Returns:
        The remembered (entries, origin) and (source, origin), each None
        when not remembered.
    """
    record = manifest_link_record(manifest)
    if record is None:
        return None, None
    entries, errors = parse_link_dirs([str(item) for item in cast(list[object], record['dirs'])], 'manifest link')
    if errors:
        return None, None
    origins = record.get('origins')
    dirs_origin = str(cast(dict[str, Any], origins).get('dirs') or 'yaml') if isinstance(origins, dict) else 'yaml'
    source_origin = str(cast(dict[str, Any], origins).get('source') or 'default') if isinstance(origins, dict) else 'default'
    source = str(record.get('source') or LINK_SOURCE_BASE)
    links_content = any(entry != SESSIONS_PROFILE_DIR for entry in entries)
    dirs = (entries, dirs_origin) if links_content or dirs_origin in ('cli', 'env') else None
    source_value = (source, source_origin) if links_content or source_origin in ('cli', 'env') else None
    return dirs, source_value


def resolve_link_spec(
    args: argparse.Namespace,
    config: dict[str, Any],
    manifest: dict[str, Any] | None = None,
) -> tuple[LinkSpec, list[str]]:
    """Determine the links of a run and validate them.

    Per key the sources rank: a value typed for this run, an environment
    value for this run, the value the profile's manifest remembers (a typed
    or environment none included, so a profile converted back or installed
    as the source its configuration's link keys serve stays unlinked on
    every re-run), the configuration's own key, then the default (no links,
    from base).

    Args:
        args: Arguments after resolve_args(), which records in args.origins
            where args.link_dirs and args.link_from came from.
        config: The resolved configuration; an empty dict when the run has
            not loaded one yet.
        manifest: The manifest of the profile the run installs into, or
            None when the profile is new.

    Returns:
        The link spec and the validation errors (empty when it is usable).
    """
    errors: list[str] = []
    remembered_dirs, remembered_source = remembered_link(manifest)

    dirs: list[str] = []
    dirs_origin = 'default'
    dirs_remembered = False
    if args.link_dirs is not None:
        dirs_origin = args.origins['link_dirs']
        dirs, dirs_errors = parse_link_dirs(args.link_dirs, LINK_DIRS_SOURCES[dirs_origin])
        errors.extend(dirs_errors)
    elif remembered_dirs is not None:
        dirs, dirs_origin = remembered_dirs
        dirs_remembered = True
    elif config.get('link-dirs') is not None:
        dirs_origin = 'yaml'
        dirs, dirs_errors = parse_link_dirs(config.get('link-dirs'), LINK_DIRS_SOURCES['yaml'])
        errors.extend(dirs_errors)

    source = LINK_SOURCE_BASE
    source_origin = 'default'
    source_remembered = False
    if args.link_from is not None:
        source_origin = args.origins['link_from']
        source = str(args.link_from).strip()
        errors.extend(link_source_errors(source, LINK_FROM_SOURCES[source_origin]))
    elif remembered_source is not None:
        source, source_origin = remembered_source
        source_remembered = True
    elif config.get('link-from') is not None:
        source_origin = 'yaml'
        raw = config.get('link-from')
        if isinstance(raw, str):
            source = raw.strip()
            errors.extend(link_source_errors(source, LINK_FROM_SOURCES['yaml']))
        else:
            errors.append(f'Invalid link-from value: expected a profile name, got {type(raw).__name__}')
    if source.casefold() == LINK_SOURCE_BASE:
        source = LINK_SOURCE_BASE
    if not dirs and not errors and source_origin in ('cli', 'env') and not source_remembered:
        errors.append(
            f'{LINK_FROM_SOURCES[source_origin]} names the profile "{source}", but no entry is linked; pass '
            f'--link-dirs ENTRIES (or set CLAUDE_CODE_TOOLBOX_LINK_DIRS) to link from it, or clear '
            f'{LINK_FROM_SOURCES[source_origin]}.',
        )
    return LinkSpec(dirs, source, dirs_origin, source_origin, dirs_remembered, source_remembered), errors


def yaml_link_values(config: dict[str, Any]) -> dict[str, Any]:
    """Read the configuration's own link values, as the manifest records them.

    Args:
        config: The resolved configuration.

    Returns:
        The entries the configuration's link-dirs names (unparsed values
        kept as written) and its link-from, or None for each absent key.
    """
    raw_dirs = config.get('link-dirs')
    dirs: list[str] | None = None
    if raw_dirs is not None:
        dirs, _errors = parse_link_dirs(raw_dirs, 'link-dirs')
    raw_source = config.get('link-from')
    return {'link_dirs': dirs, 'link_from': str(raw_source) if raw_source is not None else None}


def remembered_link_warnings(spec: LinkSpec, config: dict[str, Any], manifest: dict[str, Any] | None) -> list[str]:
    """Warn when a remembered link value overrides a configuration value that changed.

    Args:
        spec: The run's link spec.
        config: The configuration this run read.
        manifest: The manifest the remembered values came from.

    Returns:
        One warning per remembered key whose configuration value differs
        from the value the manifest recorded at install time.
    """
    if manifest is None or not (spec.dirs_remembered or spec.source_remembered):
        return []
    recorded = manifest.get('yaml_values')
    if not isinstance(recorded, dict):
        return []
    recorded_values = cast(dict[str, Any], recorded)
    now = yaml_link_values(config)
    warnings: list[str] = []
    if spec.dirs_remembered and 'link_dirs' in recorded_values and recorded_values['link_dirs'] != now['link_dirs']:
        then = recorded_values['link_dirs']
        then_text = ', '.join(str(item) for item in cast(list[object], then)) if isinstance(then, list) else 'none'
        warnings.append(
            f"link-dirs: using the remembered value {_format_names(spec.dirs)} [remembered]; the configuration's "
            f"link-dirs changed from {then_text or 'none'} to {_format_names(now['link_dirs'] or [])} since the "
            'profile was installed. Pass --link-dirs to replace the remembered value.',
        )
    if spec.source_remembered and 'link_from' in recorded_values and recorded_values['link_from'] != now['link_from']:
        warnings.append(
            f"link-from: using the remembered value {spec.source} [remembered]; the configuration's link-from "
            f"changed from {recorded_values['link_from'] or 'none'} to {now['link_from'] or 'none'} since the "
            'profile was installed. Pass --link-from to replace the remembered value.',
        )
    return warnings


def guard_environment_link_change(
    args: argparse.Namespace,
    spec: LinkSpec,
    manifest: dict[str, Any] | None,
    profile_name: str,
) -> None:
    """Hold a run back when the environment would change a profile's links.

    A typed value proceeds; a value from CLAUDE_CODE_TOOLBOX_LINK_DIRS or
    CLAUDE_CODE_TOOLBOX_LINK_FROM that differs from the links the profile's
    manifest records needs consent, because a leftover variable must not
    re-link or unlink a profile silently.

    Args:
        args: Arguments after resolve_args().
        spec: The run's effective links.
        manifest: The manifest of the profile the run installs into.
        profile_name: The profile's display name.
    """
    if manifest is None:
        return
    record = manifest_link_record(manifest)
    recorded_dirs = [str(item) for item in cast(list[object], record['dirs'])] if record else []
    recorded_source = str(record.get('source') or LINK_SOURCE_BASE) if record else LINK_SOURCE_BASE
    changed: list[str] = []
    if spec.dirs_origin == 'env' and not spec.dirs_remembered and spec.dirs != recorded_dirs:
        changed.append(
            f'{LINK_DIRS_SOURCES["env"]} changes the linked entries of profile "{profile_name}" from '
            f'{_format_names(recorded_dirs)} to {_format_names(spec.dirs)}.',
        )
    if spec.source_origin == 'env' and not spec.source_remembered and spec.dirs and spec.source != recorded_source:
        changed.append(
            f'{LINK_FROM_SOURCES["env"]} changes the link source of profile "{profile_name}" from '
            f'{recorded_source} to {spec.source}.',
        )
    if not changed:
        return
    guard_decision(
        args,
        title=changed[0],
        lines=changed[1:],
        question=f'Change the links of profile "{profile_name}" to {_format_names(spec.dirs)} from {spec.source}?',
        remedy=[
            f'Pass --link-dirs {",".join(spec.dirs) or LINK_NONE_TOKEN} --link-from {spec.source} to change them.',
            f'Clear {clear_variables_text([LINK_DIRS_SOURCES["env"], LINK_FROM_SOURCES["env"]])} to keep '
            f'{_format_names(recorded_dirs)} from {recorded_source}.',
        ],
    )


# The first lines of the wrappers register_global_command() writes on
# Windows, by file suffix; each names the command the wrapper serves. A Unix
# wrapper is a symlink to the profile's launcher instead (see
# is_toolbox_wrapper()).
_TOOLBOX_WRAPPER_MARKERS: dict[str, str] = {
    '.cmd': r'^REM Global {name} command for CMD(?=\s|$)',
    '.ps1': r'^# Global {name} command for PowerShell(?=\s|$)',
    '': r'^# Bash wrapper for {name}(?=\s|$)',
}

# Suffixes Windows shells resolve a bare command name to, beyond the
# wrappers the toolbox writes: a name.exe answers to the name just like the
# name.cmd wrapper would
_WINDOWS_EXECUTABLE_SUFFIXES: tuple[str, ...] = ('.exe', '.bat', '.com')


def is_toolbox_wrapper(path: Path, name: str) -> bool:
    """Report whether a ~/.local/bin entry is a wrapper the toolbox wrote for a name.

    register_global_command() links name to the profile's launch.sh on Unix
    and writes name.cmd, name.ps1 and name on Windows, each opening with a
    comment that names the command. A dangling link still counts: its
    profile is gone, but the toolbox created it.

    Args:
        path: The ~/.local/bin entry to inspect.
        name: The command name the entry stands for.

    Returns:
        True when the entry is a toolbox wrapper for that name.
    """
    if path.is_symlink():
        try:
            return Path(os.readlink(path)).name == 'launch.sh'
        except OSError:
            return False
    marker = _TOOLBOX_WRAPPER_MARKERS.get(path.suffix.lower())
    if marker is None:
        return False
    try:
        with path.open('r', encoding='utf-8', errors='replace') as handle:
            head = handle.read(512)
    except OSError:
        return False
    pattern = marker.format(name=re.escape(name))
    return re.search(pattern, head, flags=re.MULTILINE | re.IGNORECASE) is not None


def _command_names_of_other_profiles(home_dir: Path, primary_command_name: str) -> dict[str, str]:
    """Map every command name another isolated profile holds to the reason it is taken.

    Each isolated profile records its command names in
    ~/.claude/{primary}/manifest.json. A manifest whose 'name' is this run's
    primary name belongs to this run's own profile. A manifest that cannot
    be read still holds its directory name, which is that profile's primary
    name. Names are compared without regard to case, because Windows and
    macOS file systems map both spellings onto the same wrapper files.

    Args:
        home_dir: User home directory.
        primary_command_name: This run's primary command name.

    Returns:
        Casefolded command name mapped to the error message refusing it,
        with '{name}' left for the name as typed.
    """
    claude_dir = home_dir / '.claude'
    own = primary_command_name.casefold()
    taken: dict[str, str] = {}
    try:
        profile_dirs = sorted(entry for entry in claude_dir.iterdir() if entry.is_dir())
    except OSError:
        return taken
    for profile_dir in profile_dirs:
        manifest_path = profile_dir / MANIFEST_FILENAME
        try:
            content = json.loads(manifest_path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            continue
        except (OSError, ValueError):
            content = None
        if not isinstance(content, dict):
            if profile_dir.name.casefold() != own:
                taken[profile_dir.name.casefold()] = (
                    f'Command name "{{name}}" names the profile directory {profile_dir}, whose '
                    f'{MANIFEST_FILENAME} could not be read. Choose another name, or repair or '
                    'remove that profile first.'
                )
            continue
        manifest = cast(dict[str, Any], content)
        owner = str(manifest.get('name') or profile_dir.name)
        if owner.casefold() == own:
            continue
        listed = manifest.get('command_names')
        names = [str(item) for item in cast(list[object], listed)] if isinstance(listed, list) else []
        for name in [owner, *names]:
            if name.casefold() == owner.casefold():
                reason = (
                    f'Command name "{{name}}" is the primary name of the profile "{owner}" '
                    f'({manifest_path}). Choose a name no other profile uses.'
                )
            else:
                reason = (
                    f'Command name "{{name}}" belongs to the profile "{owner}" (listed in '
                    f'{manifest_path}). Choose a name no other profile uses, or install that '
                    'profile again with a command-names list that leaves it out.'
                )
            taken.setdefault(name.casefold(), reason)
    return taken


def command_name_conflicts(command_names: list[str], home_dir: Path) -> list[str]:
    """Find the command names of a run that another owner already holds.

    Registering a name writes its wrappers into ~/.local/bin, which would
    silently take the command over from whoever holds it. A name is held
    when another profile's manifest lists it, or when ~/.local/bin has an
    entry for it that the toolbox did not create: on Windows that covers the
    wrapper files and every executable the shells resolve the name to. A
    toolbox wrapper that no other manifest lists, such as one a dropped
    alias left behind, is free to reuse.

    Args:
        command_names: This run's command names, primary first.
        home_dir: User home directory.

    Returns:
        One error message per held name, naming the owner and the remedy;
        empty when every name is free.
    """
    taken = _command_names_of_other_profiles(home_dir, command_names[0])
    local_bin = home_dir / '.local' / 'bin'
    suffixes: tuple[str, ...] = ('',)
    if platform.system() == 'Windows':
        suffixes = ('', '.cmd', '.ps1', *_WINDOWS_EXECUTABLE_SUFFIXES)
    errors: list[str] = []
    for name in command_names:
        reason = taken.get(name.casefold())
        if reason is not None:
            errors.append(reason.replace('{name}', name))
            continue
        for suffix in suffixes:
            entry = local_bin / f'{name}{suffix}'
            if (entry.exists() or entry.is_symlink()) and not is_toolbox_wrapper(entry, name):
                errors.append(
                    f'Command name "{name}" is taken by {entry}, which the toolbox did not create. '
                    f'Choose another name, or move that file out of {local_bin} if it is no longer needed.',
                )
                break
    return errors


def download_hook_files(
    hooks: dict[str, Any] | None,
    claude_user_dir: Path,
    config_source: str,
    base_url: str | None = None,
    auth_param: str | None = None,
    hooks_base_dir: Path | None = None,
    auth_cache: AuthHeaderCache | None = None,
) -> bool:
    """Download hook files and helper modules from configuration.

    Extracts the file and helper lists from hooks configuration and delegates
    download/parallel logic to process_resources(). Helpers land in the same
    directory as the hook scripts, so a script reaches its helper through its
    own directory no matter which directory the profile installs into.

    Args:
        hooks: Hooks configuration dictionary with 'files' and 'helpers' keys.
            None is accepted and means no hooks: 'hooks:' with no value is a
            model-valid null-as-delete request, and config.get('hooks', {})
            returns that None for a present-with-null key.
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
    hooks_dict = hooks or {}
    hook_sources = [*(hooks_dict.get('files') or []), *(hooks_dict.get('helpers') or [])]

    if not hook_sources:
        info('No hook files to download')
        return True

    hooks_dir = hooks_base_dir if hooks_base_dir is not None else claude_user_dir / 'hooks'
    return process_resources(hook_sources, hooks_dir, 'hook files', config_source, base_url, auth_param, auth_cache)


def _hook_launcher_args(file_name: str) -> list[str]:
    """Return the launcher argument list for a hooks-directory file.

    Picks the launcher by file type (case-insensitive): Python files run via
    uv, JavaScript files via node, and anything else executes directly (an
    empty launcher list).

    Args:
        file_name: Bare file name of the hook script.

    Returns:
        Launcher executable and its arguments; empty when the file executes
        directly.
    """
    lowered_name = file_name.lower()
    if lowered_name.endswith(('.py', '.pyw')):
        return ['uv', 'run', '--no-project', '--python', '3.12']
    if lowered_name.endswith(('.js', '.mjs', '.cjs')):
        return ['node']
    return []


def _build_file_command(
    file_reference: str,
    config_reference: str | None,
    hooks_dir: Path,
) -> str:
    """Build the shell command string for a hooks-directory file reference.

    Shared by _build_hooks_json() (command hooks) and
    _build_profile_settings() (statusLine): strips query parameters, resolves
    the basename under hooks_dir, picks the launcher by file type via
    _hook_launcher_args(), and appends the config file path when given. Built
    paths are double-quoted so a hooks directory containing spaces (for
    example a Windows home like C:/Users/John Smith) survives shell
    word-splitting in bash, PowerShell, and cmd alike.

    Args:
        file_reference: Script file reference from the YAML configuration
            (a hooks.files basename, optionally with query parameters).
        config_reference: Optional config file reference appended as the
            command's argument.
        hooks_dir: Absolute directory path where downloaded hook files reside.

    Returns:
        The complete command string for the generated settings JSON.
    """
    clean_reference = file_reference.split('?')[0] if '?' in file_reference else file_reference
    file_name = Path(clean_reference).name
    launcher_args = _hook_launcher_args(file_name)
    launcher_prefix = f'{" ".join(launcher_args)} ' if launcher_args else ''

    file_path_str = (hooks_dir / file_name).as_posix()
    command = f'{launcher_prefix}"{file_path_str}"'

    if config_reference:
        clean_config = (
            config_reference.split('?')[0] if '?' in config_reference else config_reference
        )
        config_path_str = (hooks_dir / Path(clean_config).name).as_posix()
        command = f'{command} "{config_path_str}"'

    return command


def _build_file_exec_command(
    file_reference: str,
    config_reference: str | None,
    hooks_dir: Path,
) -> tuple[str, list[str]]:
    """Build the exec-form executable and argument list for a file reference.

    Exec-form counterpart of _build_file_command(), used by
    _build_hooks_json() for command hooks that declare 'args': Claude Code
    spawns the executable directly with the argument list, without any
    shell, so no element is quoted (a spaced path survives as a single
    argument-list element). The launcher executable becomes the command,
    while the remaining launcher arguments, the resolved script path, and
    the config file path (when given) become the leading arguments.

    Args:
        file_reference: Script file reference from the YAML configuration
            (a hooks.files basename, optionally with query parameters).
        config_reference: Optional config file reference appended as an
            argument.
        hooks_dir: Absolute directory path where downloaded hook files reside.

    Returns:
        Tuple of the executable to spawn and its leading argument list.
    """
    clean_reference = file_reference.split('?')[0] if '?' in file_reference else file_reference
    file_name = Path(clean_reference).name
    file_path_str = (hooks_dir / file_name).as_posix()

    launcher_args = _hook_launcher_args(file_name)
    if launcher_args:
        executable = launcher_args[0]
        exec_args = [*launcher_args[1:], file_path_str]
    else:
        executable = file_path_str
        exec_args = []

    if config_reference:
        clean_config = (
            config_reference.split('?')[0] if '?' in config_reference else config_reference
        )
        exec_args.append((hooks_dir / Path(clean_config).name).as_posix())

    return executable, exec_args


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


# YAML keys accepted on a hooks.events[] entry, per hook type. Used by
# _build_hooks_json() to warn about (and ignore) keys that have no meaning
# for the entry's type; the generated JSON is built from an explicit
# whitelist, so an unlisted key never reaches the output.
_HOOK_COMMON_YAML_KEYS: frozenset[str] = frozenset({
    'event', 'matcher', 'type', 'if', 'status-message', 'once', 'timeout', 'id',
})
_HOOK_TYPE_ALLOWED_YAML_KEYS: dict[str, frozenset[str]] = {
    'command': _HOOK_COMMON_YAML_KEYS | {'command', 'config', 'args', 'async', 'async-rewake', 'shell'},
    'http': _HOOK_COMMON_YAML_KEYS | {'url', 'headers', 'allowed-env-vars'},
    'prompt': _HOOK_COMMON_YAML_KEYS | {'prompt', 'model', 'continue-on-block'},
    'agent': _HOOK_COMMON_YAML_KEYS | {'prompt', 'model'},
    'mcp_tool': _HOOK_COMMON_YAML_KEYS | {'server', 'tool', 'input'},
}


def _build_hooks_json(
    hooks: dict[str, Any],
    hooks_dir: Path,
) -> dict[str, Any]:
    """Build hooks JSON structure from YAML configuration.

    Converts YAML hook event definitions into Claude Code's JSON hooks format.
    Generates absolute POSIX paths for hook file references. Supports all five
    hook types: command, http, prompt, agent, mcp_tool.

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

    # Basenames listed in hooks.files: a listed name is always a file
    # reference, even when it contains spaces, so the space heuristic in the
    # command branch below only classifies commands that are not listed
    hook_files_raw = hooks.get('files')
    listed_basenames: set[str] = {
        _hook_file_basename(f).strip()
        for f in (hook_files_raw if isinstance(hook_files_raw, list) else [])
        if isinstance(f, str)
    }

    for hook in hook_events:
        event = hook.get('event')
        matcher = hook.get('matcher', '')
        hook_type = hook.get('type', 'command')
        command = hook.get('command')
        config = hook.get('config')  # Optional config file reference

        if not event:
            warning('Invalid hook configuration: missing event, skipping')
            continue

        if event not in HOOK_EVENT_NAMES:
            warning(
                f'Unknown hook event name: {event} (not recognized by Claude Code 2.1.238, '
                'which rejects unknown event names at configuration load time)',
            )

        allowed_keys = _HOOK_TYPE_ALLOWED_YAML_KEYS.get(hook_type)
        if allowed_keys is None:
            warning(f'Unknown hook type: {hook_type}, skipping')
            continue

        unknown_keys = sorted(set(hook) - allowed_keys)
        if unknown_keys:
            warning(
                f"Hook event {event}: ignoring key(s) not supported for hook type '{hook_type}': "
                f'{", ".join(unknown_keys)}',
            )

        # Validate required fields per hook type
        if hook_type == 'command' and not command:
            warning('Invalid command hook: missing command, skipping')
            continue
        if hook_type == 'http':
            url = hook.get('url')
            if not url:
                warning('Invalid http hook: missing url, skipping')
                continue
            if not isinstance(url, str) or not url.startswith(('http://', 'https://')):
                warning(f'Invalid http hook: url must be an http:// or https:// URL, got {url}, skipping')
                continue
        if hook_type in ('prompt', 'agent') and not hook.get('prompt'):
            warning(f'Invalid {hook_type} hook: missing prompt, skipping')
            continue
        if hook_type == 'mcp_tool':
            if not hook.get('server'):
                warning('Invalid mcp_tool hook: missing server, skipping')
                continue
            if not hook.get('tool'):
                warning('Invalid mcp_tool hook: missing tool, skipping')
                continue

        # Claude Code requires a positive timeout on every hook type
        timeout = hook.get('timeout')
        if timeout is not None and (
            isinstance(timeout, bool) or not isinstance(timeout, int | float) or timeout <= 0
        ):
            warning(f'Invalid {hook_type} hook: timeout must be a positive number, got {timeout}, skipping')
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

            # Check if this looks like a file reference or a direct command:
            # any basename listed in hooks.files is a file reference (even
            # with spaces); otherwise commands with spaces, like
            # 'echo "test"', are direct commands used as-is
            is_file_reference = clean_command in listed_basenames or ' ' not in clean_command

            args = hook.get('args')
            if args is not None:
                # Exec form: Claude Code spawns the executable directly with
                # the argument list and no shell, so the launcher and the
                # resolved script path move into the argument list unquoted.
                # Only a basename listed in hooks.files is folded this way;
                # any other command IS the executable (a bare name resolves
                # via PATH, an absolute path is spawned as-is), so the shell
                # form's no-space heuristic must not reroute it into hooks_dir
                extra_args = [str(a) for a in args] if isinstance(args, list) else [str(args)]
                if clean_command in listed_basenames:
                    executable, exec_args = _build_file_exec_command(command, config, hooks_dir)
                else:
                    executable, exec_args = command, []
                hook_config = {
                    'type': hook_type,
                    'command': executable,
                    'args': exec_args + extra_args,
                }
                if hook.get('shell') is not None:
                    warning(
                        f"Hook event {event}: 'shell' is ignored when 'args' is set "
                        '(exec form spawns the executable without a shell)',
                    )
            else:
                # An unlisted command with spaces is a direct command used as-is
                full_command = _build_file_command(command, config, hooks_dir) if is_file_reference else command
                hook_config = {
                    'type': hook_type,
                    'command': full_command,
                }
                if hook.get('shell') is not None:
                    hook_config['shell'] = hook['shell']

            # Background-execution fields apply to both forms
            if hook.get('async') is not None:
                hook_config['async'] = hook['async']
            if hook.get('async-rewake') is not None:
                hook_config['asyncRewake'] = hook['async-rewake']

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
            # Prompt hooks: pass-through for prompt, model, continue-on-block
            hook_config = {
                'type': hook_type,
                'prompt': hook.get('prompt', ''),
            }
            if hook.get('model') is not None:
                hook_config['model'] = hook['model']
            if hook.get('continue-on-block') is not None:
                hook_config['continueOnBlock'] = hook['continue-on-block']

        elif hook_type == 'agent':
            # Agent hooks: same structure as prompt but type is 'agent'
            hook_config = {
                'type': hook_type,
                'prompt': hook.get('prompt', ''),
            }
            if hook.get('model') is not None:
                hook_config['model'] = hook['model']

        elif hook_type == 'mcp_tool':
            # MCP tool hooks: call a tool on an already-configured MCP server
            hook_config = {
                'type': hook_type,
                'server': hook.get('server', ''),
                'tool': hook.get('tool', ''),
            }
            if hook.get('input') is not None:
                hook_config['input'] = hook['input']

        else:
            # Unreachable: hook_type membership is validated above
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

    # Delegate to the shared READ-MERGE-WRITE helper: every array at every
    # depth is unioned with structural dedupe, and ensure_parent=True
    # creates settings_dir if missing.
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

    The ``profile_config`` parameter is a dict whose keys are the camelCase
    on-disk names of the profile-owned keys (``statusLine``, ``hooks``).
    Dict MEMBERSHIP encodes the YAML declaration state (present-with-value,
    present-with-null, or absent) which is intentionally preserved
    end-to-end so that the downstream writer can apply RFC 7396
    null-as-delete to the shared ``settings.json`` for top-level YAML nulls.

    Three cases per key:

    - **Key absent** -- the builder OMITS the key from its output dict. The
      writer preserves the existing on-disk value (if any).
    - **Key present with value None** -- the builder emits
      ``settings[key] = None`` verbatim. The writer deletes the on-disk key
      via RFC 7396 null-as-delete semantics in ``_merge_recursive()``.
    - **Key present with a non-None value** -- the builder performs the
      usual processing (command-string construction for ``statusLine``,
      ``_build_hooks_json()`` delegation for ``hooks``) and emits the
      processed value.

    The ``hooks`` value in ``profile_config`` is either ``None`` (YAML null),
    absent (YAML omitted), or the full YAML hooks configuration dict with
    ``files`` / ``events`` keys (which is then processed via
    ``_build_hooks_json()``).

    Args:
        profile_config: Dict of profile-owned keys to build settings from.
            Keys use camelCase on-disk names. Values correspond directly to
            the YAML-declared values (with pre-processing for ``statusLine``
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
        >>> _build_profile_settings({}, Path('/tmp/hooks'))
        {}

        >>> _build_profile_settings({'statusLine': None}, Path('/tmp/hooks'))
        {'statusLine': None}
    """
    settings: dict[str, Any] = {}

    # statusLine (command-string construction)
    if 'statusLine' in profile_config:
        status_line = profile_config['statusLine']
        if status_line is None:
            settings['statusLine'] = None
            info('Deleting statusLine via explicit null')
        elif isinstance(status_line, dict):
            status_line_file = status_line.get('file')
            if status_line_file:
                clean_filename = status_line_file.split('?')[0] if '?' in status_line_file else status_line_file
                filename = Path(clean_filename).name

                status_line_command = _build_file_command(
                    status_line_file, status_line.get('config'), hooks_dir,
                )

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


def _strip_null_values(settings: dict[str, Any]) -> dict[str, Any]:
    """Recursively remove dict members whose value is None.

    Implements deletion-by-absence for atomically rebuilt JSON files: a
    YAML null is a deletion request (RFC 7396 convention), and under atomic
    rebuild semantics absence expresses deletion, so the literal JSON null
    is never written. A nested dict whose members are ALL deletion requests
    is itself dropped (an env section containing only null entries carries
    no content, so the emptied key is omitted rather than written as an
    empty object); a dict the user declared empty passes through unchanged.
    Only dict members are stripped; None elements inside lists are
    preserved (a null in an array is data, not a deletion request,
    matching RFC 7396 which processes object members only).

    Args:
        settings: Dict to strip (not modified).

    Returns:
        New dict without None-valued members at any nesting depth.
    """
    result: dict[str, Any] = {}
    for key, value in settings.items():
        if value is None:
            continue
        if isinstance(value, dict):
            value_dict = cast(dict[str, Any], value)
            stripped = _strip_null_values(value_dict)
            if stripped or not value_dict:
                result[key] = stripped
        else:
            result[key] = value
    return result


def _warn_wsl_windows_paths(settings: dict[str, Any]) -> None:
    """Warn when WSL is detected and a command key carries a Windows path.

    Tilde paths are preserved on non-Windows platforms, but a settings dict
    authored on Windows may contain absolute Windows-style paths (e.g.
    C:\\Users\\...) that do not resolve inside the Linux environment.

    Args:
        settings: Settings dict to inspect for Windows-style paths.
    """
    if not is_wsl():
        return
    for key in TILDE_EXPANSION_KEYS:
        if key in settings and isinstance(settings[key], str):
            value = settings[key]
            if re.search(r'[A-Za-z]:\\', value):
                warning(
                    f'WSL detected: {key} contains Windows-style path: {value}. '
                    'This may not work in the Linux environment. '
                    'Consider re-running setup from within WSL.',
                )
                break


def create_profile_config(
    profile_config: dict[str, Any],
    config_base_dir: Path,
    hooks_base_dir: Path | None = None,
    user_settings: dict[str, Any] | None = None,
) -> bool:
    """Create config.json (profile configuration) for the isolated environment.

    The isolated profile's config.json is delivered to Claude Code via the
    launcher's --settings flag (command-line settings layer), which outranks
    a repository's project settings. It carries the profile's complete
    settings.json content: the user-settings section (raw settings.json
    keys) plus the toolbox-built statusLine and hooks entries. The two
    sources are disjoint by construction because 'statusLine' and 'hooks'
    are rejected inside user-settings.

    Delegates to the pure builder _build_profile_settings() for the
    profile-owned keys and atomically writes the combined result to
    ~/.claude/{cmd}/config.json. This file is always overwritten on re-run,
    so YAML removals of keys cleanly propagate to the isolated profile
    (isolated-mode atomic rebuild semantics).

    In isolated mode, the on-disk config.json is fully toolbox-owned: each
    invocation rebuilds the file from scratch, so the distinction between
    "YAML key absent" and "YAML key set to null" collapses -- null-valued
    dict members at every depth are STRIPPED before the write, because
    under atomic rebuild semantics absence expresses deletion and Claude
    Code's treatment of literal nulls inside --settings files is
    undocumented.

    Args:
        profile_config: Dict of profile-owned keys (camelCase on-disk names:
            statusLine, hooks). Keys present with values are written; keys
            absent or null-valued are omitted. For the ``hooks`` key, the
            value is the full YAML hooks configuration dict with ``files`` /
            ``helpers`` / ``events`` keys.
        config_base_dir: Path to the isolated environment directory
            (e.g., ~/.claude/{cmd}/).
        hooks_base_dir: Optional base directory for hook files.
            When provided, hook file paths are resolved relative to this directory
            instead of config_base_dir / 'hooks'.
        user_settings: Optional user-settings section (raw settings.json
            content with camelCase keys). Tilde paths in command keys are
            expanded platform-conditionally before the write.

    Returns:
        bool: True if successful, False otherwise.
    """
    # Determine hooks directory: use hooks_base_dir if provided, else default
    hooks_dir = hooks_base_dir if hooks_base_dir is not None else config_base_dir / 'hooks'

    info('Creating config.json...')

    # user-settings content forms the base of the profile settings
    settings: dict[str, Any] = {}
    if user_settings:
        expanded_user_settings = _expand_tilde_keys_in_settings(user_settings)
        _warn_wsl_windows_paths(expanded_user_settings)
        settings.update(_strip_null_values(expanded_user_settings))
        info(f'Including {len(settings)} user-settings key(s) in config.json')

    # Build the profile-owned settings via the shared pure builder
    settings.update(_strip_null_values(_build_profile_settings(profile_config, hooks_dir)))

    # Save settings (always overwrite) - atomic rebuild semantics.
    # ensure_ascii=False keeps non-ASCII user-settings content readable,
    # matching the shared settings.json writer.
    settings_path = config_base_dir / 'config.json'
    try:
        config_base_dir.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(
            json.dumps(settings, indent=2, ensure_ascii=False), encoding='utf-8',
        )
        success('Created config.json')
        return True
    except Exception as e:
        error(f'Failed to save config.json: {e}')
        return False


RESOLVED_CONFIG_FILENAME = 'resolved-config.yaml'

# Top-level configuration keys that name the profile and its links instead of
# describing what it installs. A profile's resolved-config.yaml leaves them
# out, so the snapshot of a configuration is the same whichever profile
# installed it, and a profile that applies a source's snapshot takes no links
# from it.
PROFILE_IDENTITY_CONFIG_KEYS: tuple[str, ...] = ('command-names', 'link-dirs', 'link-from')

# Where each remembered value of a profile came from, as the manifest records
# it and the summaries mark it. 'yaml' is the configuration's own value (for
# components: the author defaults); 'default' is the value a run falls back to
# when no source names one.
VALUE_ORIGINS: tuple[str, ...] = ('cli', 'env', 'yaml', 'default')


def origin_marker(origin: str | None, *, remembered: bool = False) -> str:
    """Render where a run's value came from, for the summaries that list it.

    Args:
        origin: The value's origin: 'cli', 'env', 'yaml', 'default', or None
            when no source names a value.
        remembered: Whether this run took the value from the profile's
            manifest instead of a source of its own.

    Returns:
        ' [remembered]' for a remembered value, ' [<origin>]' otherwise, or
        an empty string without an origin.
    """
    if remembered:
        return ' [remembered]'
    return f' [{origin}]' if origin else ''


def config_identity_of(config_source: str) -> str:
    """Normalize a resolved configuration source for comparison across runs.

    Args:
        config_source: The resolved source load_config_from_source() returns:
            a URL, or an absolute local path.

    Returns:
        The URL as given, or the local path made absolute with normalized
        separators (and case, on Windows).
    """
    if config_source.startswith(('http://', 'https://')):
        return config_source.strip()
    return _normalize_config_dir_key(config_source)


def resolved_config_snapshot(config: dict[str, Any]) -> dict[str, Any]:
    """Copy a resolved configuration without the keys that name the profile.

    Args:
        config: The resolved, component-selected configuration a run installs.

    Returns:
        A deep copy without PROFILE_IDENTITY_CONFIG_KEYS.
    """
    return {
        key: deepcopy(value)
        for key, value in config.items()
        if key not in PROFILE_IDENTITY_CONFIG_KEYS
    }


def render_resolved_config(config: dict[str, Any]) -> str:
    """Serialize a configuration snapshot the way resolved-config.yaml stores it.

    Args:
        config: The resolved, component-selected configuration a run installs.

    Returns:
        YAML text of resolved_config_snapshot(config), keys in their original
        order so the same configuration always renders to the same bytes.
    """
    return yaml.safe_dump(
        resolved_config_snapshot(config), sort_keys=False, allow_unicode=True, default_flow_style=False,
    )


def config_digest_of(text: str) -> str:
    """Compute the digest a manifest records for a resolved-config.yaml text.

    Args:
        text: The YAML text render_resolved_config() produced.

    Returns:
        The hex sha256 of the UTF-8 encoded text.
    """
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def profile_directory(home_dir: Path, primary_command_name: str | None) -> Path:
    """Return the directory of a profile under the user's configuration home.

    Args:
        home_dir: User home directory.
        primary_command_name: The profile's primary command name, or None
            for the base profile.

    Returns:
        ~/.claude/{primary} for an isolated profile, ~/.claude for the base.
    """
    claude_dir = home_dir / '.claude'
    return claude_dir / primary_command_name if primary_command_name else claude_dir


def profile_display_name(primary_command_name: str | None) -> str:
    """Return the name the summaries and --profile use for a profile.

    Args:
        primary_command_name: The profile's primary command name, or None
            for the base profile.

    Returns:
        The primary command name, or 'base'.
    """
    return primary_command_name or 'base'


def read_profile_manifest(manifest_path: Path) -> dict[str, Any] | None:
    """Read one profile manifest.

    Args:
        manifest_path: Path to a profile's manifest.json.

    Returns:
        The manifest, or None when no file exists at the path.

    Raises:
        ValueError: When the file exists but cannot be read or is not a JSON
            object; the message names the file and the cause.
    """
    try:
        raw = manifest_path.read_text(encoding='utf-8')
    except FileNotFoundError:
        return None
    except OSError as e:
        raise ValueError(f'{manifest_path} could not be read: {e}') from None
    try:
        content = json.loads(raw)
    except ValueError as e:
        raise ValueError(f'{manifest_path} is not valid JSON: {e}') from None
    if not isinstance(content, dict):
        raise ValueError(f'{manifest_path} does not hold a JSON object')
    return cast(dict[str, Any], content)


class InstalledProfile(NamedTuple):
    """A profile recorded under the user's configuration home.

    Attributes:
        name: 'base' for the base profile, the directory name otherwise.
        directory: The profile directory.
        manifest_path: The profile's manifest.json.
        manifest: Its content, or None when the file cannot be read.
    """

    name: str
    directory: Path
    manifest_path: Path
    manifest: dict[str, Any] | None


def installed_profiles(home_dir: Path) -> list[InstalledProfile]:
    """List every profile under ~/.claude that has a manifest.

    Args:
        home_dir: User home directory.

    Returns:
        The base profile first when it has a manifest, then the isolated
        profiles in sorted directory order. A profile whose manifest cannot
        be read is listed with manifest None.
    """
    claude_dir = home_dir / '.claude'
    candidates: list[tuple[str, Path]] = [('base', claude_dir)]
    try:
        if claude_dir.is_dir():
            candidates.extend(
                (subdir.name, subdir)
                for subdir in sorted(claude_dir.iterdir())
                if subdir.is_dir()
            )
    except OSError:
        pass  # A directory that cannot be listed records no readable profile
    profiles: list[InstalledProfile] = []
    for name, directory in candidates:
        manifest_path = directory / MANIFEST_FILENAME
        try:
            manifest = read_profile_manifest(manifest_path)
        except ValueError:
            profiles.append(InstalledProfile(name, directory, manifest_path, None))
            continue
        if manifest is not None:
            profiles.append(InstalledProfile(name, directory, manifest_path, manifest))
    return profiles


def manifest_config_identity(manifest: dict[str, Any]) -> str | None:
    """Return the configuration identity a manifest records.

    A manifest written without config_identity is matched by its
    config_source_url when present, else by its resolved config_source: a
    URL as is, a repository name through the URL the loader fetches, an
    absolute local path as is, and a relative local path only when it
    resolves from the current directory.

    Args:
        manifest: The profile manifest.

    Returns:
        The identity, or None when the manifest records a relative local
        source that cannot be resolved from here.
    """
    identity = manifest.get('config_identity')
    if isinstance(identity, str) and identity:
        return identity
    url = manifest.get('config_source_url')
    if isinstance(url, str) and url:
        return config_identity_of(url)
    source = manifest.get('config_source')
    if not isinstance(source, str) or not source:
        return None
    if source.startswith(('http://', 'https://')):
        return config_identity_of(source)
    if manifest.get('config_source_type') == 'repo':
        return config_identity_of(resolve_config_source_url(source, 'repo') or source)
    if os.path.isabs(source) or Path(source).exists():
        return config_identity_of(source)
    return None


def content_dependents(home_dir: Path, source_name: str) -> list[InstalledProfile]:
    """List the installed profiles that link content from a profile.

    Args:
        home_dir: User home directory.
        source_name: The display name of the source: base, or a primary
            command name.

    Returns:
        The dependents in sorted directory order; the base profile never
        links, so it is never a dependent.
    """
    dependents: list[InstalledProfile] = []
    for profile in installed_profiles(home_dir):
        record = manifest_link(profile.manifest)
        if record is None or profile.name == 'base':
            continue
        if str(record.get('source') or LINK_SOURCE_BASE).casefold() != source_name.casefold():
            continue
        if any(str(entry) != SESSIONS_PROFILE_DIR for entry in cast(list[object], record['dirs'])):
            dependents.append(profile)
    return dependents


def dependents_remedy(dependents: list[InstalledProfile]) -> list[str]:
    """Name the commands that re-point or unlink each content dependent."""
    return [
        f'  --profile {profile.name} --link-from <other profile>   (re-point), or '
        f'--profile {profile.name} --link-dirs {LINK_NONE_TOKEN}   (unlink)'
        for profile in dependents
    ]


def wired_hook_file_names(config: dict[str, Any]) -> list[str]:
    """List the hooks-directory files the configuration's hook events and status line run.

    Args:
        config: The resolved configuration.

    Returns:
        The query-stripped basenames of every command hook's ``command``
        (when it names a hooks.files entry) and ``config``, and of the
        status line's ``file`` and ``config``, each once, in order.
    """
    hooks = config.get('hooks')
    hooks_dict = cast(dict[str, Any], hooks) if isinstance(hooks, dict) else {}
    listed = {_installed_resource_name(item) for item in cast(list[object], hooks_dict.get('files') or [])}
    names: list[str] = []

    def _add(reference: object) -> None:
        if isinstance(reference, str) and reference.strip():
            name = _installed_resource_name(reference)
            if name not in names:
                names.append(name)

    for event in cast(list[object], hooks_dict.get('events') or []):
        if not isinstance(event, dict):
            continue
        event_dict = cast(dict[str, Any], event)
        if event_dict.get('type', 'command') != 'command':
            continue
        command = event_dict.get('command')
        if isinstance(command, str) and _installed_resource_name(command) in listed:
            _add(command)
        _add(event_dict.get('config'))
    status_line = config.get('status-line')
    if isinstance(status_line, dict):
        status_dict = cast(dict[str, Any], status_line)
        _add(status_dict.get('file'))
        _add(status_dict.get('config'))
    return names


def missing_wired_hook_files(config: dict[str, Any], hooks_dir: Path) -> list[str]:
    """Name the wired hook files absent from a hooks directory.

    Args:
        config: The resolved configuration.
        hooks_dir: The profile's hooks directory, a link in a dependent.

    Returns:
        The absolute paths that do not exist as files.
    """
    return [str(hooks_dir / name) for name in wired_hook_file_names(config) if not (hooks_dir / name).is_file()]


def order_profiles_source_first(profiles: list[InstalledProfile]) -> list[InstalledProfile]:
    """Order installed profiles so every link source runs before its content dependents.

    Args:
        profiles: The profiles installed_profiles() lists.

    Returns:
        The base profile first, then the profiles that link no content in
        their listed order, then the content dependents in their listed order.
    """
    def _links_content(profile: InstalledProfile) -> bool:
        record = manifest_link(profile.manifest)
        return record is not None and any(
            str(entry) != SESSIONS_PROFILE_DIR for entry in cast(list[object], record['dirs'])
        )

    return [p for p in profiles if not _links_content(p)] + [p for p in profiles if _links_content(p)]


class DependentResult(NamedTuple):
    """The outcome of one dependent profile's refresh.

    Attributes:
        name: The dependent's display name.
        code: Its exit code.
        needs_elevation: Whether the run failed on a machine where its
            dependency commands need administrator rights the parent lacks.
    """

    name: str
    code: int
    needs_elevation: bool

    def line(self) -> str:
        """Render the result for the reports."""
        if self.code == 0:
            return f'{self.name}: ok'
        remedy = f'retry with --profile {self.name}'
        if self.needs_elevation:
            remedy += ' from an elevated terminal (a global npm install needs administrator rights the run could not request)'
        return f'{self.name}: failed (exit code {self.code}); {remedy}'


def refresh_dependents(dependents: list[InstalledProfile]) -> list[DependentResult]:
    """Re-run every profile that links content from this one, each in its own child run.

    A child runs ``--profile <dependent> --yes --child-run --skip-install
    --no-admin`` through the same program this run started from (the script,
    or the packaged entry point), with every argument twin except the
    repository credential and CLAUDE_CONFIG_DIR removed from its environment,
    so a variable set for the source cannot change what a dependent installs.
    ``--child-run`` because this run's summary reports on every installed
    profile, so the child lists none as unrefreshed; ``--skip-install``
    because the source just installed the one binary; ``--no-admin`` so no
    child relaunches through UAC and exits 0 unobserved. Every dependent runs
    whatever the others returned.

    Args:
        dependents: The profiles to refresh, from content_dependents().

    Returns:
        One result per dependent, in order.
    """
    launch = [sys.executable, *_elevation_launch_args(__name__, sys.argv[0])]
    env = child_run_environment()
    results: list[DependentResult] = []
    for profile in dependents:
        print()
        print(f'{Colors.CYAN}=== Dependent profile {profile.name} ==={Colors.NC}')
        try:
            code = subprocess.run(
                [*launch, '--profile', profile.name, '--yes', CHILD_RUN_FLAG, '--skip-install', '--no-admin'],
                env=env, check=False,
            ).returncode
        except OSError as e:
            error(f'Cannot start the run of profile "{profile.name}": {e}')
            code = 1
        needs_elevation = False
        if code != 0 and platform.system() == 'Windows' and not is_admin():
            snapshot = read_resolved_config_snapshot(profile.directory) or {}
            needs_elevation = bool(admin_elevation_reasons(snapshot, argparse.Namespace(skip_install=True)))
        results.append(DependentResult(profile.name, code, needs_elevation))
    return results


class LinkSource(NamedTuple):
    """The profile a run links from.

    Attributes:
        name: Its display name.
        directory: Its profile directory.
        manifest: Its manifest, or None when it has none (allowed for a
            projects-only link).
    """

    name: str
    directory: Path
    manifest: dict[str, Any] | None


def resolve_link_source(spec: LinkSpec, home_dir: Path) -> tuple[LinkSource | None, list[str]]:
    """Locate the profile a run links from.

    Args:
        spec: The run's links.
        home_dir: User home directory.

    Returns:
        The source and the errors: an uninstalled source, or a manifest that
        exists but cannot be read.
    """
    primary = None if spec.source == LINK_SOURCE_BASE else spec.source
    directory = profile_directory(home_dir, primary)
    if primary is not None and not directory.is_dir():
        variables = link_environment_variables(spec)
        remedy = (
            f'install it first, name an installed profile, or clear {clear_variables_text(variables)} to run '
            'without links' if variables
            else 'install it first, or name an installed profile'
        )
        return None, [
            f'{link_source_value_text(spec)} names the profile "{spec.source}", but no profile of that name is '
            f'installed ({directory} does not exist); {remedy}.',
        ]
    try:
        manifest = read_profile_manifest(directory / MANIFEST_FILENAME)
    except ValueError as e:
        return None, [f'The manifest of the link source "{spec.source}" cannot be read: {e}']
    return LinkSource(spec.source, directory, manifest), []


def link_request_errors(
    spec: LinkSpec,
    source: LinkSource | None,
    *,
    primary_command_name: str | None,
    this_identity: str | None,
    typed_selectors: bool,
) -> list[str]:
    """Check the link rules a run must satisfy before any write.

    Args:
        spec: The run's links.
        source: The resolved link source, or None when spec links nothing
            or the source could not be resolved.
        primary_command_name: This run's primary command name, None for
            the base profile.
        this_identity: The identity of the configuration this run was
            given, or None when it is unknown.
        typed_selectors: Whether --select, --with or --without was typed
            or came from the environment.

    Returns:
        One message per violated rule, each naming the value by where it
        came from (the flag, the variable with the commands that clear it,
        the configuration key, or the remembered value); empty when the
        links are allowed.
    """
    if not spec.dirs:
        return []
    variables = link_environment_variables(spec)
    clear_remedy = f'clear {clear_variables_text(variables)}' if variables else None
    if primary_command_name is None:
        remedies = [
            'pass --command-names NAME (or set CLAUDE_CODE_TOOLBOX_COMMAND_NAMES) so the links are created inside '
            '~/.claude/NAME',
        ]
        if clear_remedy:
            remedies.append(f'{clear_remedy} to run the base profile without links')
        elif spec.dirs_origin == 'yaml' and not spec.dirs_remembered:
            remedies.append(f'remove {LINK_DIRS_SOURCES["yaml"]} from the configuration')
        return [
            f'{link_dirs_value_text(spec)} needs an isolated profile: {", or ".join(remedies)}; the base profile '
            'cannot link.',
        ]
    if spec.source != LINK_SOURCE_BASE and spec.source.casefold() == primary_command_name.casefold():
        remedies = []
        if clear_remedy:
            remedies.append(f'{clear_remedy} to re-run "{primary_command_name}" as installed')
        elif spec.source_origin == 'yaml' and not spec.source_remembered:
            remedies.append(
                f'pass --link-dirs {LINK_NONE_TOKEN} to install "{primary_command_name}" without links, as the '
                "source the configuration's other profiles link from",
            )
        remedies.append('name another profile in --link-from')
        return [
            f'Profile "{primary_command_name}" cannot link from itself: {link_source_value_text(spec)} names the '
            f'profile this run installs; {", or ".join(remedies)}.',
        ]
    if source is None:
        return []
    errors = _content_link_errors(
        spec, source, primary_command_name=primary_command_name, this_identity=this_identity,
        typed_selectors=typed_selectors,
    )
    if clear_remedy:
        return [f'{err} Or {clear_remedy} to run without links.' for err in errors]
    return errors


def _content_link_errors(
    spec: LinkSpec,
    source: LinkSource,
    *,
    primary_command_name: str,
    this_identity: str | None,
    typed_selectors: bool,
) -> list[str]:
    """Check the rules of a content link against its resolved source.

    Args:
        spec: The run's links.
        source: The resolved link source.
        primary_command_name: This run's primary command name.
        this_identity: The identity of the configuration this run was
            given, or None when it is unknown.
        typed_selectors: Whether --select, --with or --without was typed
            or came from the environment.

    Returns:
        One message per violated rule; empty when the links are allowed.
    """
    errors: list[str] = []
    if spec.links_content:
        content = ', '.join(spec.content_dirs)
        if source.manifest is None:
            errors.append(
                f'Content entries ({content}) link only from a profile installed by this setup, and "{source.name}" '
                f'has no manifest ({source.directory / MANIFEST_FILENAME}); install it with this setup first, or link '
                f'only {SESSIONS_PROFILE_DIR}.',
            )
            return errors
        source_identity = manifest_config_identity(source.manifest)
        source_config = source.manifest.get('config_source')
        if this_identity is None or source_identity != this_identity:
            # A profile that already follows the source is re-pointed or
            # unlinked before it switches; a new link request is pointed at
            # the working topology: one full profile of this configuration,
            # the rest linked from it
            if spec.dirs_remembered:
                remedy = (
                    f'Pass --link-dirs {LINK_NONE_TOKEN}, or --link-from naming a profile installed from the '
                    f'configuration this run was given, so profile "{primary_command_name}" stops following '
                    f'"{source.name}"'
                )
            else:
                remedy = (
                    'Install one full profile of the configuration this run was given first (--command-names SOURCE '
                    'with no link keys), then link the others from it with --link-from SOURCE; or run the setup with '
                    f'the configuration profile "{source.name}" was installed from (the identity is its resolved '
                    'path or URL)'
                )
            errors.append(
                f'Content entries ({content}) link only between installs of one configuration: profile '
                f'"{source.name}" was installed from {source_config}, and this run was given a different '
                f'configuration. {remedy}; or link only {SESSIONS_PROFILE_DIR}.',
            )
        source_record = manifest_link(source.manifest)
        source_links_content = source_record is not None and any(
            str(entry) != SESSIONS_PROFILE_DIR for entry in cast(list[object], source_record['dirs'])
        )
        if source_links_content and source_record is not None:
            upstream = str(source_record.get('source') or LINK_SOURCE_BASE)
            errors.append(
                f'Profile "{source.name}" links content from profile "{upstream}" itself, and content links go only '
                f'to a profile that holds its entries for real; use --link-from {upstream}.',
            )
        if typed_selectors:
            errors.append(
                f'A profile that links content ({content}) takes the component selection of profile "{source.name}"; '
                'drop --select, --with and --without (and their variables).',
            )
    return errors


def _relative_inside(target: Path, directory: Path) -> Path | None:
    """Return a path relative to a directory when it lies inside it.

    Args:
        target: The path to test.
        directory: The directory that may contain it.

    Returns:
        The relative path in the target's own spelling, or None when the
        target lies outside the directory (separators and, on Windows, case
        do not matter).
    """
    target_abs = Path(os.path.abspath(target))
    directory_key = _normalize_config_dir_key(str(directory))
    if not _normalize_config_dir_key(str(target_abs)).startswith(directory_key + '/'):
        return None
    depth = len(Path(os.path.abspath(directory)).parts)
    return Path(*target_abs.parts[depth:])


def planned_profile_files(
    config: dict[str, Any],
    profile_dir: Path,
    *,
    reroot: ConfigHomeReroot | None = None,
    linked_entries: frozenset[str] = frozenset(),
) -> list[str]:
    """List the profile-relative paths of the files a configuration installs.

    Mirrors each installer's target-path resolution: agents, slash commands,
    rules and hook files (scripts and helpers) by query-stripped basename in
    their directories, skill files under skills/<name>/, the system prompt
    under prompts/, and files-to-download entries whose destination lies
    inside the profile directory. Launchers, settings, env loaders and the
    manifest are toolbox-owned and rebuilt on every run, so they are not
    listed. A linked entry installs nothing of its own, so nothing inside
    one is listed: the files a dependent sees through a link belong to its
    source, and a record of them would let a later configuration switch
    remove them from the source.

    Args:
        config: The resolved, component-selected configuration.
        profile_dir: The profile directory the run installs into.
        reroot: The isolated run's rerooter, applied to each destination
            when the configuration has not been rewritten yet (the switch
            guard reads it before the rewrite); None for a base run or a
            configuration already rewritten.
        linked_entries: The entries of the profile that are links.

    Returns:
        Sorted relative POSIX paths.
    """
    if linked_entries:
        config = config_without_linked_sections(config, linked_entries)
        downloads, _skipped = split_downloads_by_linked_entries(
            cast(list[Any], config.get('files-to-download') or []), profile_dir, linked_entries,
        )
        config = {**config, 'files-to-download': downloads}
    files: set[str] = set()
    for section, directory in (('agents', 'agents'), ('slash-commands', 'commands'), ('rules', 'rules')):
        files.update(
            f'{directory}/{_installed_resource_name(item)}'
            for item in cast(list[object], config.get(section) or [])
        )
    hooks = config.get('hooks')
    if isinstance(hooks, dict):
        hooks_dict = cast(dict[str, Any], hooks)
        files.update(
            f'hooks/{_installed_resource_name(item)}'
            for item in cast(list[object], [*(hooks_dict.get('files') or []), *(hooks_dict.get('helpers') or [])])
        )
    for skill in cast(list[object], config.get('skills') or []):
        if not isinstance(skill, dict):
            continue
        skill_dict = cast(dict[str, Any], skill)
        name = str(skill_dict.get('name') or '').strip()
        for file_path in cast(list[object], skill_dict.get('files') or []):
            if name and isinstance(file_path, str):
                files.add(f'skills/{name}/{file_path.replace(os.sep, "/")}')
    defaults = config.get('command-defaults')
    prompt = cast(dict[str, Any], defaults).get('system-prompt') if isinstance(defaults, dict) else None
    if prompt:
        files.add(f'prompts/{_installed_resource_name(prompt)}')
    for entry in cast(list[object], config.get('files-to-download') or []):
        if not isinstance(entry, dict):
            continue
        entry_dict = cast(dict[str, Any], entry)
        source, dest = entry_dict.get('source'), entry_dict.get('dest')
        if not source or not dest:
            continue
        dest_str = reroot.rewrite(str(dest)) if reroot is not None else str(dest)
        relative = _relative_inside(_download_destination(str(source), dest_str), profile_dir)
        if relative is not None:
            files.add(relative.as_posix())
    return sorted(files)


def _sha256_of_file(path: Path) -> str | None:
    """Hash a file's content.

    Args:
        path: The file to hash.

    Returns:
        The hex sha256, or None when the file cannot be read.
    """
    digest = hashlib.sha256()
    try:
        with path.open('rb') as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b''):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def machine_wide_download_records(
    files_to_download: list[dict[str, Any]],
    config_source: str,
    base_url: str | None,
    claude_dir: Path,
) -> list[dict[str, str | None]]:
    """Record the files-to-download destinations outside ~/.claude a run wrote.

    Args:
        files_to_download: The resolved files-to-download list.
        config_source: Where the configuration was loaded from.
        base_url: The configuration's base-url, or None.
        claude_dir: The base ~/.claude directory.

    Returns:
        One record per destination outside claude_dir: its absolute path,
        the resolved source, and the sha256 of the file on disk (None when
        the file is absent or unreadable).
    """
    claude_key = _normalize_config_dir_key(str(claude_dir))
    records: list[dict[str, str | None]] = []
    for entry in files_to_download:
        source, dest = entry.get('source'), entry.get('dest')
        if not source or not dest:
            continue
        target = Path(os.path.abspath(_download_destination(str(source), str(dest))))
        target_key = _normalize_config_dir_key(str(target))
        if target_key == claude_key or target_key.startswith(claude_key + '/'):
            continue
        resolved_source, _ = resolve_resource_path(str(source), config_source, base_url)
        records.append({'dest': str(target), 'source': resolved_source, 'sha256': _sha256_of_file(target)})
    return records


# The prefix of a settings record that names one env entry instead of a
# top-level key: 'env.FOO' is the FOO variable of the settings env object
SETTINGS_ENV_ENTRY_PREFIX = 'env.'


def written_settings_keys(
    user_settings: dict[str, Any] | None,
    status_line: object,
    hooks: object,
) -> list[str]:
    """List the settings keys a run writes.

    Args:
        user_settings: The resolved user-settings section, or None.
        status_line: The resolved status-line section, or None.
        hooks: The resolved hooks section, or None.

    Returns:
        Sorted keys: every non-null top-level user-settings key except env,
        one 'env.<VAR>' entry per non-null env variable, statusLine when a
        status line is configured, hooks when events are.
    """
    keys: set[str] = set()
    for key, value in (user_settings or {}).items():
        if value is None:
            continue
        if key == 'env' and isinstance(value, dict):
            keys.update(
                f'{SETTINGS_ENV_ENTRY_PREFIX}{variable}'
                for variable, entry in cast(dict[str, Any], value).items()
                if entry is not None
            )
            continue
        keys.add(key)
    if status_line:
        keys.add('statusLine')
    if isinstance(hooks, dict) and cast(dict[str, Any], hooks).get('events'):
        keys.add('hooks')
    return sorted(keys)


def _is_machine_wide_control_record(key: str) -> bool:
    """Report whether a settings or OS record names a machine-wide binary control.

    Args:
        key: An os_env_written entry or a settings_keys_written entry.

    Returns:
        True for a MACHINE_WIDE_ENV_CONTROLS variable, bare or as an env
        entry. Those controls belong to the pin gate and the Step 16
        sweep, never to the residue of a configuration switch.
    """
    return key.removeprefix(SETTINGS_ENV_ENTRY_PREFIX) in MACHINE_WIDE_ENV_CONTROLS


def mcp_server_records(mcp_servers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Record the MCP servers a run registers with their scopes.

    Args:
        mcp_servers: The resolved mcp-servers list.

    Returns:
        One record per named server: its name and normalized scopes.
    """
    records: list[dict[str, Any]] = []
    for server in mcp_servers:
        name = str(server.get('name') or '').strip()
        if name:
            records.append({'name': name, 'scopes': _mcp_scopes_or_empty(server.get('scope', 'user'))})
    return records


class ProfileResidue(NamedTuple):
    """What a profile's previous configuration left that a new one does not install.

    Attributes:
        files: Absolute paths of recorded profile files the new
            configuration does not install and that still exist.
        mcp_servers: (name, scopes) of recorded MCP servers the new
            configuration does not declare, non-profile scopes only.
        os_env: OS environment variables the previous run set and the new
            configuration does not, the machine-wide binary controls
            excluded.
        settings_keys: Settings keys of a base profile the previous run
            wrote and the new configuration does not: top-level keys, and
            'env.<VAR>' entries other than the machine-wide binary controls.
        destinations: Recorded destinations outside ~/.claude the new
            configuration does not install, whose file still holds the
            recorded content and which no other installed profile records.
        kept_destinations: (path, profile names) of recorded destinations
            outside ~/.claude the new configuration does not install but
            another installed profile still records; they are listed and
            never removed.
    """

    files: list[Path]
    mcp_servers: list[tuple[str, list[str]]]
    os_env: list[str]
    settings_keys: list[str]
    destinations: list[Path]
    kept_destinations: list[tuple[Path, list[str]]]

    def __bool__(self) -> bool:
        return any((self.files, self.mcp_servers, self.os_env, self.settings_keys, self.destinations))

    def lines(self) -> list[str]:
        """Render the residue one item per line, for a guard message."""
        rendered = [f'file: {path}' for path in self.files]
        rendered.extend(f'MCP server: {name} (scope: {", ".join(scopes)})' for name, scopes in self.mcp_servers)
        rendered.extend(f'OS environment variable: {key}' for key in self.os_env)
        for key in self.settings_keys:
            if key.startswith(SETTINGS_ENV_ENTRY_PREFIX):
                rendered.append(f'settings.json env variable: {key.removeprefix(SETTINGS_ENV_ENTRY_PREFIX)}')
            else:
                rendered.append(f'settings.json key: {key}')
        rendered.extend(f'file outside ~/.claude: {path}' for path in self.destinations)
        rendered.extend(
            f'file outside ~/.claude kept: {path} (recorded by profile {", ".join(names)})'
            for path, names in self.kept_destinations
        )
        return rendered


def _destinations_recorded_elsewhere(home_dir: Path, profile_dir: Path) -> dict[str, list[str]]:
    """Map each destination outside ~/.claude to the other installed profiles that record it.

    Args:
        home_dir: User home directory.
        profile_dir: The directory of the profile being switched, whose own
            manifest is left out.

    Returns:
        Normalized destination path to the display names of the profiles
        whose manifests record it.
    """
    own_key = _normalize_config_dir_key(str(profile_dir))
    recorded: dict[str, list[str]] = {}
    for profile in installed_profiles(home_dir):
        if profile.manifest is None or _normalize_config_dir_key(str(profile.directory)) == own_key:
            continue
        for record in cast(list[object], profile.manifest.get('machine_wide_destinations') or []):
            if not isinstance(record, dict):
                continue
            dest = cast(dict[str, Any], record).get('dest')
            if isinstance(dest, str) and dest:
                recorded.setdefault(_normalize_config_dir_key(dest), []).append(profile.name)
    return recorded


def _under_directory_link(profile_dir: Path, relative: str) -> bool:
    """Report whether a profile-relative path is reached through a directory link.

    Args:
        profile_dir: The profile directory.
        relative: A recorded relative POSIX path inside it.

    Returns:
        True when any directory between the profile directory and the path
        is a junction or symlink, so the path lies in another directory.
    """
    parts = [part for part in relative.split('/') if part]
    return any(_is_directory_link(profile_dir.joinpath(*parts[:depth])) for depth in range(1, len(parts)))


def profile_residue(
    manifest: dict[str, Any],
    profile_dir: Path,
    config: dict[str, Any],
    *,
    isolated: bool,
    config_source: str,
    base_url: str | None,
    claude_dir: Path,
    reroot: ConfigHomeReroot | None = None,
) -> ProfileResidue:
    """Compute what switching a profile to another configuration leaves behind.

    Args:
        manifest: The profile's current manifest.
        profile_dir: The profile directory.
        config: The new resolved, component-selected configuration.
        isolated: Whether the profile is isolated; the base profile's
            settings.json and OS environment carry residue, an isolated
            profile's config.json and env loaders are rebuilt each run.
        config_source: Where the new configuration was loaded from.
        base_url: The new configuration's base-url, or None.
        claude_dir: The base ~/.claude directory.
        reroot: The isolated run's rerooter, so the files the new
            configuration installs are compared at their re-rooted paths,
            which is how the previous run recorded them; None for a base
            run.

    Returns:
        The residue; empty when the new configuration covers everything the
        previous run recorded. A recorded file that lies under a directory
        link on disk is never residue: it belongs to the link's target, so
        removing it would edit another directory.
    """
    def _strings(key: str) -> list[str]:
        value = manifest.get(key)
        return [str(item) for item in cast(list[object], value)] if isinstance(value, list) else []

    planned = set(planned_profile_files(config, profile_dir, reroot=reroot))
    files = [
        profile_dir / relative
        for relative in _strings('files_written')
        if relative not in planned
        and (profile_dir / relative).is_file()
        and not _under_directory_link(profile_dir, relative)
    ]

    new_servers = {record['name'] for record in mcp_server_records(
        [cast(dict[str, Any], s) for s in cast(list[object], config.get('mcp-servers') or []) if isinstance(s, dict)],
    )}
    servers: list[tuple[str, list[str]]] = []
    for record in cast(list[object], manifest.get('mcp_servers') or []):
        if not isinstance(record, dict):
            continue
        record_dict = cast(dict[str, Any], record)
        name = str(record_dict.get('name') or '')
        scopes = [str(s) for s in cast(list[object], record_dict.get('scopes') or []) if str(s) != 'profile']
        if name and name not in new_servers and scopes:
            servers.append((name, scopes))

    # The machine-wide binary controls are never residue: the pin gate and
    # the Step 16 sweep decide their removal, and a run that drops a pin
    # while another installed profile still pins must leave them in place
    os_env: list[str] = []
    settings_keys: list[str] = []
    if not isolated:
        new_env = {key for key, value in (config.get('os-env-variables') or {}).items() if value is not None}
        os_env = [
            key for key in _strings('os_env_written')
            if key not in new_env and not _is_machine_wide_control_record(key)
        ]
        new_keys = set(written_settings_keys(config.get('user-settings'), config.get('status-line'), config.get('hooks')))
        settings_keys = [
            key for key in _strings('settings_keys_written')
            if key not in new_keys and not _is_machine_wide_control_record(key)
        ]

    new_downloads = [
        cast(dict[str, Any], entry)
        for entry in cast(list[object], config.get('files-to-download') or [])
        if isinstance(entry, dict)
    ]
    new_destinations = {
        _normalize_config_dir_key(str(record['dest']))
        for record in machine_wide_download_records(new_downloads, config_source, base_url, claude_dir)
        if record['dest']
    }
    # A destination another installed profile records is that profile's
    # file too, so a switch lists it as kept instead of removing it
    recorded_elsewhere = _destinations_recorded_elsewhere(claude_dir.parent, profile_dir)
    destinations: list[Path] = []
    kept_destinations: list[tuple[Path, list[str]]] = []
    for record in cast(list[object], manifest.get('machine_wide_destinations') or []):
        if not isinstance(record, dict):
            continue
        record_dict = cast(dict[str, Any], record)
        dest = record_dict.get('dest')
        if not isinstance(dest, str) or _normalize_config_dir_key(dest) in new_destinations:
            continue
        path = Path(dest)
        if not path.is_file():
            continue
        holders = recorded_elsewhere.get(_normalize_config_dir_key(dest))
        if holders:
            kept_destinations.append((path, holders))
        elif _sha256_of_file(path) == record_dict.get('sha256'):
            destinations.append(path)
    return ProfileResidue(files, servers, os_env, settings_keys, destinations, kept_destinations)


def remove_profile_residue(residue: ProfileResidue, *, profile_dir: Path, claude_dir: Path) -> None:
    """Remove what a profile's previous configuration left behind.

    Args:
        residue: The residue profile_residue() computed.
        profile_dir: The profile directory.
        claude_dir: The base ~/.claude directory, whose settings.json holds
            a base profile's settings residue.
    """
    for path in [*residue.files, *residue.destinations]:
        try:
            path.unlink()
            success(f'Removed {path}')
        except OSError as e:
            warning(f'Cannot remove {path}: {e}')
    skills_dir = profile_dir / 'skills'
    for path in residue.files:
        parent = path.parent
        while _relative_inside(parent, skills_dir) is not None:
            try:
                if any(parent.iterdir()):
                    break
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
    if residue.mcp_servers:
        claude_cmd = find_command('claude')
        if claude_cmd:
            for name, scopes in residue.mcp_servers:
                _remove_mcp_server_from_cli_scopes(
                    claude_cmd, name, scopes, None, profile_dir if profile_dir != claude_dir else None,
                )
        else:
            warning('Cannot remove the previous MCP servers: claude command not found')
    if residue.os_env:
        set_all_os_env_variables(dict.fromkeys(residue.os_env))
    if residue.settings_keys:
        # One null-as-delete write: top-level keys, and each recorded env
        # entry on its own, so the env object keeps every other variable
        settings_path = claude_dir / 'settings.json'
        deletions: dict[str, Any] = {}
        env_deletions: dict[str, None] = {}
        for key in residue.settings_keys:
            if key.startswith(SETTINGS_ENV_ENTRY_PREFIX):
                env_deletions[key.removeprefix(SETTINGS_ENV_ENTRY_PREFIX)] = None
            else:
                deletions[key] = None
        if env_deletions:
            deletions['env'] = env_deletions
        written, merged = _write_merged_json(settings_path, deletions)
        if written and merged.get('env') == {}:
            merged.pop('env')
            try:
                settings_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
            except OSError as e:
                warning(f'Cannot drop the emptied env object of {settings_path}: {e}')
        if written:
            success(f'Removed settings.json key(s): {", ".join(residue.settings_keys)}')
        else:
            warning(f'Cannot remove settings.json key(s): {", ".join(residue.settings_keys)}')


def write_manifest(
    config_base_dir: Path,
    command_name: str | None,
    config_version: str | None,
    config_source: str,
    config_source_type: str,
    config_source_url: str | None,
    command_names: list[str],
    claude_code_version: str | None,
    *,
    resolved_config: dict[str, Any] | None = None,
    origins: dict[str, str | None] | None = None,
    components: dict[str, str | None] | None = None,
    yaml_values: dict[str, Any] | None = None,
    machine_wide_destinations: list[dict[str, str | None]] | None = None,
    os_env_written: list[str] | None = None,
    settings_keys_written: list[str] | None = None,
    mcp_servers: list[dict[str, Any]] | None = None,
    files_written: list[str] | None = None,
    link: dict[str, Any] | None = None,
) -> bool:
    """Write the installation manifest of a profile.

    Creates manifest.json recording the profile's primary command name
    (None for the base profile), the configuration version, source and
    identity, the digest of the resolved configuration, all command names
    and the component delta with their origins, the configuration's own
    values at install time, the Claude Code version the profile pins, and
    what the run wrote: destinations outside ~/.claude with their source
    and content hash, OS environment variables, settings keys, MCP servers,
    and the profile files. A re-run reads the names, the delta and the
    identity; the switch guard reads the written records to list the
    residue another configuration would leave; _other_profile_pins() reads
    the pin to decide whether the machine-global update controls are still
    needed. When resolved_config is given, resolved-config.yaml is written
    beside the manifest and config_digest is its sha256.

    Args:
        config_base_dir: Path to the profile directory -- ~/.claude/{cmd}/
            for an isolated profile, ~/.claude/ for the base profile
        command_name: Primary command name, or None for the base profile
        config_version: Optional semantic version from config (e.g., "1.3.0")
        config_source: The resolved configuration source: a URL, or an
            absolute local path
        config_source_type: Classified source type ("url", "local", "repo")
        config_source_url: Resolved fetch URL, or None for local sources
        command_names: List of all command names (primary + aliases), empty
            for the base profile
        claude_code_version: Claude Code version this profile pins, or None
            when the profile tracks the latest release
        resolved_config: The resolved, component-selected configuration this
            run installed, or None to leave resolved-config.yaml untouched
        origins: Origin per remembered key ('command_names', 'components')
        components: The component delta as typed: the --select, --with and
            --without values, or None when the author defaults applied
        yaml_values: The configuration's own command-names and default
            component names at install time
        machine_wide_destinations: files-to-download destinations outside
            ~/.claude, each with its source and sha256
        os_env_written: OS environment variables this run set
        settings_keys_written: Top-level settings keys this run wrote
        mcp_servers: MCP servers this run registered, with their scopes
        files_written: Profile-relative paths of the files this run installs
        link: The profile's links as LinkSpec.record() renders them (the
            linked entries, the source profile, and the origin of each; an
            empty entry list for a typed or environment none, which a re-run
            remembers ahead of the configuration's link-dirs), or None when
            the profile links nothing without such a value

    Returns:
        True if manifest was written successfully, False otherwise.
    """
    manifest_path = config_base_dir / MANIFEST_FILENAME
    config_digest: str | None = None
    rendered_config: str | None = None
    if resolved_config is not None:
        rendered_config = render_resolved_config(resolved_config)
        config_digest = config_digest_of(rendered_config)

    manifest: dict[str, Any] = {
        'name': command_name,
        'version': config_version,
        MANIFEST_VERSION_PIN_KEY: claude_code_version,
        'config_source': config_source,
        'config_source_url': config_source_url,
        'config_source_type': config_source_type,
        'config_identity': config_identity_of(config_source),
        'config_digest': config_digest,
        'installed_at': datetime.now(UTC).isoformat(),
        'command_names': command_names,
        'components': components,
        'link': link,
        'origins': origins if origins is not None else {
            'command_names': 'yaml' if command_names else None,
            'components': 'yaml',
        },
        'yaml_values': yaml_values if yaml_values is not None else {},
        'machine_wide_destinations': machine_wide_destinations or [],
        'os_env_written': os_env_written or [],
        'settings_keys_written': settings_keys_written or [],
        'mcp_servers': mcp_servers or [],
        'files_written': files_written or [],
    }

    try:
        config_base_dir.mkdir(parents=True, exist_ok=True)
        if rendered_config is not None:
            (config_base_dir / RESOLVED_CONFIG_FILENAME).write_text(rendered_config, encoding='utf-8')
            success(f'Created {RESOLVED_CONFIG_FILENAME}')
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        success(f'Created {MANIFEST_FILENAME}')
        return True
    except Exception as e:
        warning(f'Failed to write manifest: {e}')
        return False


def _escape_bash_double_quoted(text: str) -> str:
    """Escape text for a literal inside a double-quoted bash string.

    Args:
        text: The literal text.

    Returns:
        The text with backslash, double quote, dollar sign and backtick escaped.
    """
    return text.replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$').replace('`', '\\`')


def _escape_cmd_set_value(text: str) -> str:
    """Escape text for a literal inside a batch-file ``set "NAME=value"`` assignment.

    Args:
        text: The literal text.

    Returns:
        The text with every percent sign doubled.
    """
    return text.replace('%', '%%')


def _escape_powershell_double_quoted(text: str) -> str:
    """Escape text for a literal inside a double-quoted PowerShell string.

    Args:
        text: The literal text.

    Returns:
        The text with backtick, dollar sign and double quote prefixed by a backtick.
    """
    return text.replace('`', '``').replace('$', '`$').replace('"', '`"')


class _ProfileDirSpelling(NamedTuple):
    """How generated launchers and wrappers spell one profile directory.

    A directory below the user's home is spelled relative to the home each
    shell resolves when the script runs; any other directory is spelled
    absolute.

    Attributes:
        posix: The directory inside a double-quoted bash string.
        cmd: The directory inside a batch-file ``set "NAME=value"`` assignment.
        powershell_parent: PowerShell expression for the directory holding it.
        powershell_leaf: Its name, escaped for a double-quoted PowerShell string.
    """

    posix: str
    cmd: str
    powershell_parent: str
    powershell_leaf: str


def _spell_profile_dir(profile_dir: Path) -> _ProfileDirSpelling:
    """Spell a profile directory for every shell a launcher or wrapper runs in.

    Args:
        profile_dir: The profile directory setup writes into; a relative path
            names the directory below the current working directory.

    Returns:
        The spelling of profile_dir for bash, CMD and PowerShell.
    """
    directory = Path(os.path.abspath(profile_dir))
    home_parts = Path(os.path.abspath(get_real_user_home())).parts
    parts = directory.parts
    leaf = _escape_powershell_double_quoted(directory.name)
    below_home = len(parts) > len(home_parts) and [os.path.normcase(part) for part in parts[:len(home_parts)]] == [
        os.path.normcase(part) for part in home_parts
    ]
    if not below_home:
        parent = _escape_powershell_double_quoted(str(directory.parent).replace('/', '\\'))
        return _ProfileDirSpelling(
            posix=_escape_bash_double_quoted(directory.as_posix()),
            cmd=_escape_cmd_set_value(str(directory).replace('/', '\\')),
            powershell_parent=f'"{parent}"',
            powershell_leaf=leaf,
        )
    relative = parts[len(home_parts):]
    parent_parts = relative[:-1]
    powershell_parent = '$env:USERPROFILE'
    if parent_parts:
        relative_parent = _escape_powershell_double_quoted('\\'.join(parent_parts))
        powershell_parent = f'Join-Path $env:USERPROFILE "{relative_parent}"'
    return _ProfileDirSpelling(
        posix='$HOME/' + '/'.join(_escape_bash_double_quoted(part) for part in relative),
        cmd='%USERPROFILE%\\' + '\\'.join(_escape_cmd_set_value(part) for part in relative),
        powershell_parent=powershell_parent,
        powershell_leaf=leaf,
    )


# Block of the Windows launch.sh that runs before claude starts. Git Bash
# rewrites every argument that looks like a POSIX path when it starts the
# native claude.exe, so a slash command such as "/review src" would reach
# Claude Code as "C:/Program Files/Git/review src". MSYS2_ARG_CONV_EXCL holds
# ';'-separated prefixes of arguments Git Bash passes unchanged; listing each
# argument that starts with a single '/' and names no existing path keeps it
# byte for byte, while an existing path such as /c/work still converts. The
# list is set only for a launch that has such an argument and keeps the
# entries the caller set. The session inherits it, and its entries exclude
# only arguments that start with those texts, so a Git Bash started from the
# session keeps converting other paths such as /tmp/... An argument holding
# ';' cannot be listed and needs no entry, because Git Bash never converts one.
WINDOWS_SLASH_ARGUMENTS_GUARD = r'''# Keep slash arguments such as slash commands unchanged: Git Bash converts an
# argument that looks like a POSIX path when it starts claude.exe, unless
# MSYS2_ARG_CONV_EXCL lists it. Existing paths keep converting.
UNCONVERTED_ARGS=""
for arg in "$@"; do
  case "$arg" in
    //* | *\;*) ;;
    /*) [ -e "$arg" ] || UNCONVERTED_ARGS="${UNCONVERTED_ARGS:+$UNCONVERTED_ARGS;}$arg" ;;
  esac
done
if [ -n "$UNCONVERTED_ARGS" ]; then
  export MSYS2_ARG_CONV_EXCL="${MSYS2_ARG_CONV_EXCL:+$MSYS2_ARG_CONV_EXCL;}$UNCONVERTED_ARGS"
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

    Every path a launcher reads -- the exported CLAUDE_CONFIG_DIR, config.json,
    mcp.json, the system prompt and the env.sh loader -- is spelled from
    config_base_dir: relative to the home directory the shell resolves at run
    time when config_base_dir lies below the user's home, absolute otherwise.

    Only launch.sh applies the profile's env loader: it sources env.sh in the
    bash process that execs Claude Code, so every session receives the
    loader's sets and unsets. start.ps1 and start.cmd run in the shell that
    calls them ($env: is process-wide in PowerShell; a batch file executes in
    the calling cmd.exe), so they reference no loader and leave that shell's
    environment as it was; start.cmd keeps its own variables behind setlocal.

    The Windows launch.sh runs WINDOWS_SLASH_ARGUMENTS_GUARD before it starts
    claude, so Git Bash hands slash commands to claude.exe unchanged.

    Args:
        config_base_dir: The profile directory (e.g., ~/.claude/{cmd}/, or the
            directory a user-settings.env CLAUDE_CONFIG_DIR names)
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
    spelling = _spell_profile_dir(config_base_dir)
    profile_sh = spelling.posix

    # Will hold the shared POSIX launch script path (Windows only; on Unix, same as launcher_path)
    shared_sh: Path | None = None

    try:
        config_base_dir.mkdir(parents=True, exist_ok=True)
        if system == 'Windows':
            # Create PowerShell wrapper for Windows
            launcher_path = config_base_dir / 'start.ps1'
            launcher_content = f'''# Claude Code Environment Launcher
# This script starts Claude Code with the configured environment

$claudeUserDir = {spelling.powershell_parent}

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
$scriptPath = Join-Path (Join-Path $claudeUserDir "{spelling.powershell_leaf}") "launch.sh"

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
setlocal
REM Claude Code Environment Launcher for CMD
REM This script starts Claude Code with the configured environment

echo Starting Claude Code with {command_name} configuration...

REM Call shared script
set "BASH_EXE=C:\\Program Files\\Git\\bin\\bash.exe"
if not exist "%BASH_EXE%" set "BASH_EXE=C:\\Program Files (x86)\\Git\\bin\\bash.exe"

set "SCRIPT_WIN={spelling.cmd}\\launch.sh"

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
export CLAUDE_CONFIG_DIR="{profile_sh}"

# Source OS-level environment variables (if configured)
ENV_FILE="{profile_sh}/env.sh"
[ -f "$ENV_FILE" ] && . "$ENV_FILE"

# Get Windows path for settings
SETTINGS_WIN="$(cygpath -m "{profile_sh}/config.json" 2>/dev/null ||
  echo "{profile_sh}/config.json")"

# MCP configuration for profile-scoped servers
MCP_CONFIG_PATH="{profile_sh}/mcp.json"
MCP_FLAGS=()
if [ -f "$MCP_CONFIG_PATH" ]; then
  MCP_WIN="$(cygpath -m "$MCP_CONFIG_PATH" 2>/dev/null || echo "$MCP_CONFIG_PATH")"
  MCP_FLAGS=(--strict-mcp-config --mcp-config "$MCP_WIN")
fi

PROMPT_PATH="{profile_sh}/prompts/{system_prompt_file}"
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

''' + WINDOWS_SLASH_ARGUMENTS_GUARD
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
  exec claude "${MCP_FLAGS[@]}" --system-prompt-file "$PROMPT_PATH" "$@" --settings "$SETTINGS_WIN"
elif [ "$HAS_CONTINUE" = true ]; then
  # Legacy workaround for v < 2.0.64: use --append-system-prompt for continuation
  # Continuation: use --append-system-prompt-file if available (v2.0.34+)
  if version_ge "$CLAUDE_VERSION" "2.0.34"; then
    exec claude "${MCP_FLAGS[@]}" --append-system-prompt-file "$PROMPT_PATH" "$@" --settings "$SETTINGS_WIN"
  else
    # For Claude < 2.0.34: check prompt size to avoid "Argument list too long"
    PROMPT_SIZE=$(get_file_size "$PROMPT_PATH")
    if [ "$PROMPT_SIZE" -lt "$SAFE_PROMPT_SIZE" ]; then
      # Small prompt: safe to use content-based flag
      PROMPT_CONTENT=$(cat "$PROMPT_PATH")
      exec claude "${MCP_FLAGS[@]}" --append-system-prompt "$PROMPT_CONTENT" "$@" --settings "$SETTINGS_WIN"
    else
      # Large prompt: skip to prevent error
      echo "Warning: System prompt too large ($PROMPT_SIZE bytes) for Claude < 2.0.34" >&2
      echo "Skipping prompt to prevent 'Argument list too long' error" >&2
      echo "Solutions: 1) Upgrade to Claude v2.0.34+, 2) Reduce prompt to <4KB" >&2
      exec claude "${MCP_FLAGS[@]}" "$@" --settings "$SETTINGS_WIN"
    fi
  fi
else
  # New session: use --system-prompt-file (available in v2.0.14+)
  if version_ge "$CLAUDE_VERSION" "2.0.14"; then
    exec claude "${MCP_FLAGS[@]}" --system-prompt-file "$PROMPT_PATH" "$@" --settings "$SETTINGS_WIN"
  else
    # Fallback to content-based flag for very old versions
    PROMPT_CONTENT=$(cat "$PROMPT_PATH")
    exec claude "${MCP_FLAGS[@]}" --system-prompt "$PROMPT_CONTENT" "$@" --settings "$SETTINGS_WIN"
  fi
fi
'''
                else:  # mode == 'append'
                    # Append mode: use --append-system-prompt-file if available
                    shared_sh_content += '''# Append mode: use --append-system-prompt-file if available (v2.0.34+)
if version_ge "$CLAUDE_VERSION" "2.0.34"; then
  exec claude "${MCP_FLAGS[@]}" --append-system-prompt-file "$PROMPT_PATH" "$@" --settings "$SETTINGS_WIN"
else
  # For Claude < 2.0.34: check prompt size to avoid "Argument list too long"
  PROMPT_SIZE=$(get_file_size "$PROMPT_PATH")
  if [ "$PROMPT_SIZE" -lt "$SAFE_PROMPT_SIZE" ]; then
    # Small prompt: safe to use content-based flag
    PROMPT_CONTENT=$(cat "$PROMPT_PATH")
    exec claude "${MCP_FLAGS[@]}" --append-system-prompt "$PROMPT_CONTENT" "$@" --settings "$SETTINGS_WIN"
  else
    # Large prompt: skip to prevent error
    echo "Warning: System prompt too large ($PROMPT_SIZE bytes) for Claude < 2.0.34" >&2
    echo "Skipping prompt to prevent 'Argument list too long' error" >&2
    echo "Solutions: 1) Upgrade to Claude v2.0.34+, 2) Reduce prompt to <4KB" >&2
    exec claude "${MCP_FLAGS[@]}" "$@" --settings "$SETTINGS_WIN"
  fi
fi
'''
            else:
                # No system prompt, only settings
                shared_sh_content = f'''#!/usr/bin/env bash
set -euo pipefail

# Set isolated environment directory
export CLAUDE_CONFIG_DIR="{profile_sh}"

# Source OS-level environment variables (if configured)
ENV_FILE="{profile_sh}/env.sh"
[ -f "$ENV_FILE" ] && . "$ENV_FILE"

# Get Windows path for settings
SETTINGS_WIN="$(cygpath -m "{profile_sh}/config.json" 2>/dev/null ||
  echo "{profile_sh}/config.json")"

# MCP configuration for profile-scoped servers
MCP_CONFIG_PATH="{profile_sh}/mcp.json"
MCP_FLAGS=()
if [ -f "$MCP_CONFIG_PATH" ]; then
  MCP_WIN="$(cygpath -m "$MCP_CONFIG_PATH" 2>/dev/null || echo "$MCP_CONFIG_PATH")"
  MCP_FLAGS=(--strict-mcp-config --mcp-config "$MCP_WIN")
fi

''' + WINDOWS_SLASH_ARGUMENTS_GUARD + '''exec claude "${MCP_FLAGS[@]}" "$@" --settings "$SETTINGS_WIN"
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
export CLAUDE_CONFIG_DIR="{profile_sh}"

# Source OS-level environment variables (if configured)
ENV_FILE="{profile_sh}/env.sh"
[ -f "$ENV_FILE" ] && . "$ENV_FILE"

SETTINGS_PATH="{profile_sh}/config.json"
PROMPT_PATH="{profile_sh}/prompts/{system_prompt_file}"

# MCP configuration for profile-scoped servers
MCP_CONFIG_PATH="{profile_sh}/mcp.json"
MCP_FLAGS=()
if [ -f "$MCP_CONFIG_PATH" ]; then
  MCP_FLAGS=(--strict-mcp-config --mcp-config "$MCP_CONFIG_PATH")
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
  claude "${{MCP_FLAGS[@]}}" --system-prompt-file "$PROMPT_PATH" "$@" --settings "$SETTINGS_PATH"
elif [ "$HAS_CONTINUE" = true ]; then
  echo -e "\\033[0;32mResuming Claude Code session with {command_name} configuration...\\033[0m"
  # Legacy workaround for v < 2.0.64: use --append-system-prompt for continuation
  # Continuation: use --append-system-prompt-file if available (v2.0.34+)
  if version_ge "$CLAUDE_VERSION" "2.0.34"; then
    claude "${{MCP_FLAGS[@]}}" --append-system-prompt-file "$PROMPT_PATH" "$@" --settings "$SETTINGS_PATH"
  else
    # For Claude < 2.0.34: check prompt size to avoid "Argument list too long"
    PROMPT_SIZE=$(get_file_size "$PROMPT_PATH")
    if [ "$PROMPT_SIZE" -lt "$SAFE_PROMPT_SIZE" ]; then
      # Small prompt: safe to use content-based flag
      PROMPT_CONTENT=$(cat "$PROMPT_PATH")
      claude "${{MCP_FLAGS[@]}}" --append-system-prompt "$PROMPT_CONTENT" "$@" --settings "$SETTINGS_PATH"
    else
      # Large prompt: skip to prevent error
      echo "Warning: System prompt too large ($PROMPT_SIZE bytes) for Claude < 2.0.34" >&2
      echo "Skipping prompt to prevent 'Argument list too long' error" >&2
      echo "Solutions: 1) Upgrade to Claude v2.0.34+, 2) Reduce prompt to <4KB" >&2
      claude "${{MCP_FLAGS[@]}}" "$@" --settings "$SETTINGS_PATH"
    fi
  fi
else
  echo -e "\\033[0;32mStarting Claude Code with {command_name} configuration...\\033[0m"
  # New session: use --system-prompt-file (available in v2.0.14+)
  if version_ge "$CLAUDE_VERSION" "2.0.14"; then
    claude "${{MCP_FLAGS[@]}}" --system-prompt-file "$PROMPT_PATH" "$@" --settings "$SETTINGS_PATH"
  else
    # Fallback to content-based flag for very old versions
    PROMPT_CONTENT=$(cat "$PROMPT_PATH")
    claude "${{MCP_FLAGS[@]}}" --system-prompt "$PROMPT_CONTENT" "$@" --settings "$SETTINGS_PATH"
  fi
fi
'''
                else:  # mode == 'append'
                    # Append mode: use --append-system-prompt-file if available
                    launcher_content += f'''# Append mode: use --append-system-prompt-file if available (v2.0.34+)
echo -e "\\033[0;32mStarting Claude Code with {command_name} configuration...\\033[0m"
if version_ge "$CLAUDE_VERSION" "2.0.34"; then
  claude "${{MCP_FLAGS[@]}}" --append-system-prompt-file "$PROMPT_PATH" "$@" --settings "$SETTINGS_PATH"
else
  # For Claude < 2.0.34: check prompt size to avoid "Argument list too long"
  PROMPT_SIZE=$(get_file_size "$PROMPT_PATH")
  if [ "$PROMPT_SIZE" -lt "$SAFE_PROMPT_SIZE" ]; then
    # Small prompt: safe to use content-based flag
    PROMPT_CONTENT=$(cat "$PROMPT_PATH")
    claude "${{MCP_FLAGS[@]}}" --append-system-prompt "$PROMPT_CONTENT" "$@" --settings "$SETTINGS_PATH"
  else
    # Large prompt: skip to prevent error
    echo "Warning: System prompt too large ($PROMPT_SIZE bytes) for Claude < 2.0.34" >&2
    echo "Skipping prompt to prevent 'Argument list too long' error" >&2
    echo "Solutions: 1) Upgrade to Claude v2.0.34+, 2) Reduce prompt to <4KB" >&2
    claude "${{MCP_FLAGS[@]}}" "$@" --settings "$SETTINGS_PATH"
  fi
fi
'''
            else:
                launcher_content = f'''#!/usr/bin/env bash
# Claude Code Environment Launcher
# This script starts Claude Code with the configured environment

# Set isolated environment directory
export CLAUDE_CONFIG_DIR="{profile_sh}"

# Source OS-level environment variables (if configured)
ENV_FILE="{profile_sh}/env.sh"
[ -f "$ENV_FILE" ] && . "$ENV_FILE"

SETTINGS_PATH="{profile_sh}/config.json"

# MCP configuration for profile-scoped servers
MCP_CONFIG_PATH="{profile_sh}/mcp.json"
MCP_FLAGS=()
if [ -f "$MCP_CONFIG_PATH" ]; then
  MCP_FLAGS=(--strict-mcp-config --mcp-config "$MCP_CONFIG_PATH")
fi

echo -e "\\033[0;32mStarting Claude Code with {command_name} configuration...\\033[0m"

# Pass any additional arguments to Claude
claude "${{MCP_FLAGS[@]}}" "$@" --settings "$SETTINGS_PATH"
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
    in ~/.local/bin/. PowerShell wrappers name launcher_path (start.ps1) by its
    absolute path. CMD and Git Bash wrappers reference launch_script_path
    (launch.sh); they spell its directory relative to the home directory when
    it lies below the user's home, absolute otherwise. No wrapper applies the
    profile's env loader: a wrapper runs in the shell that calls it, and
    launch.sh sources env.sh for the session itself. The CMD wrappers keep
    their own variables behind setlocal, so the calling cmd.exe is left as it
    was.

    On Unix, creates symlinks in ~/.local/bin/ pointing to launcher_path.

    Args:
        launcher_path: Path to the main launcher script (start.ps1 on Windows,
            launch.sh on Unix).
        command_name: Primary command name (used for file naming).
        additional_names: Optional list of additional command names (aliases).
        launch_script_path: Path to the shared POSIX launch script, by default
            launch.sh beside launcher_path. On Unix this parameter is not used
            (symlinks point to launcher_path directly).

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

            # Spell the profile's launch.sh for each shell
            launch_script = launch_script_path if launch_script_path is not None else launcher_path.parent / 'launch.sh'
            spelling = _spell_profile_dir(launch_script.parent)
            cmd_script_path = f'{spelling.cmd}\\{launch_script.name}'
            bash_script_path = f'{spelling.posix}/{launch_script.name}'
            ps1_launcher_path = _escape_powershell_double_quoted(str(launcher_path))

            # Create wrappers for all Windows shells
            # CMD wrapper
            batch_path = local_bin / f'{command_name}.cmd'
            batch_content = f'''@echo off
setlocal
REM Global {command_name} command for CMD
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
& "{ps1_launcher_path}" @args
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
setlocal
REM Global {alias_name} command for CMD (alias for {command_name})
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
& "{ps1_launcher_path}" @args
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

            def _link_to_launcher(link_path: Path) -> None:
                # exists() follows the link and reports False for one whose
                # profile is gone, yet that dangling link still holds the name
                if link_path.is_symlink() or link_path.exists():
                    link_path.unlink()
                link_path.symlink_to(launcher_path)

            _link_to_launcher(local_bin / command_name)

            # Create additional symlinks for aliases (Linux/macOS)
            if additional_names:
                for alias_name in additional_names:
                    _link_to_launcher(local_bin / alias_name)

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


def _is_windows_reparse_point(link_path: Path) -> bool:
    """Return True if link_path is a Windows reparse point (junction or symlink).

    Windows directory junctions report ``Path.is_symlink() == False`` while
    ``Path.is_dir() == True``, so junctions cannot be detected with
    ``Path.is_symlink()``. The reparse-point bit in the file attributes is the
    reliable signal for both junctions and symlinks.

    Args:
        link_path: The path to inspect.

    Returns:
        True if the path exists and carries the reparse-point attribute.
    """
    import stat as stat_module

    try:
        # Access the Windows-only st_file_attributes via getattr so type
        # checkers do not fail on non-Windows platforms, where the attribute is
        # absent (defaulting to 0, i.e. no reparse-point bit).
        attrs = getattr(os.lstat(link_path), 'st_file_attributes', 0)
    except OSError:
        return False
    return bool(attrs & stat_module.FILE_ATTRIBUTE_REPARSE_POINT)


def _strip_extended_path_prefix(path: str) -> str:
    """Remove the Windows extended-length prefix a junction target is stored with.

    Args:
        path: A path as os.readlink() returns it.

    Returns:
        The path without a leading ``\\\\?\\`` (or ``\\\\?\\UNC\\``) prefix.
    """
    if path.startswith('\\\\?\\UNC\\'):
        return '\\\\' + path[8:]
    if path.startswith('\\\\?\\'):
        return path[4:]
    return path


def _same_real_directory(first: str | Path, second: str | Path) -> bool:
    """Report whether two paths name the same directory once links, short names and case are resolved."""
    try:
        return os.path.normcase(os.path.realpath(first)) == os.path.normcase(os.path.realpath(second))
    except OSError:
        return False


def _link_points_to(link_path: Path, target: Path) -> bool:
    """Return True if the existing link at link_path resolves to target.

    A junction records its target with the extended-length prefix and may
    spell it with 8.3 short names, so both sides are compared through
    os.path.realpath() and os.path.normcase(). A junction os.readlink()
    cannot read is resolved through the link path itself.

    Args:
        link_path: The link (symlink or junction) to inspect.
        target: The expected target directory.

    Returns:
        True if the link resolves to target, False otherwise.
    """
    try:
        recorded = _strip_extended_path_prefix(os.readlink(link_path))
    except OSError:
        recorded = None
    if recorded is not None and _same_real_directory(recorded, target):
        return True
    return _same_real_directory(link_path, target)


def _is_directory_link(path: Path) -> bool:
    """Report whether a path is a directory link: a reparse point on Windows, a symlink elsewhere.

    Args:
        path: The path to inspect.

    Returns:
        True for a junction or symlink at the path, False for anything else.
    """
    if platform.system() == 'Windows':
        return _is_windows_reparse_point(path)
    return path.is_symlink()


def _remove_directory_link(link_path: Path) -> None:
    """Remove a directory link and nothing of its target.

    Args:
        link_path: The junction or symlink to remove.
    """
    if platform.system() == 'Windows':
        os.rmdir(link_path)
    else:
        link_path.unlink()


def _final_real_directory(path: Path) -> Path:
    """Return the real directory a path stands for, following every link on the way.

    Args:
        path: A directory, a link to one, or a link to a link.

    Returns:
        The resolved directory, so a new link never points at another link.
    """
    try:
        return path.resolve()
    except OSError:
        return path


def link_profile_directory(link_path: Path, target: Path) -> None:
    """Create a directory link at link_path pointing at target.

    Creates the target first if absent, then the link: a symlink on Unix, a
    directory junction on Windows (elevation-free). _winapi.CreateJunction is
    the primary mechanism, with mklink /J as a last-resort fallback; _winapi
    is a private CPython module retained for this purpose. link_path must not
    pre-exist, which apply_link_plan() guarantees. An OSError from the target
    or the link, or a CalledProcessError from the mklink /J fallback,
    propagates to the caller.

    Args:
        link_path: Where the link is created, e.g. ~/.claude/{cmd}/skills.
        target: The real directory the link points at.
    """
    target.mkdir(parents=True, exist_ok=True)
    if platform.system() != 'Windows':
        link_path.symlink_to(target, target_is_directory=True)
        return
    import _winapi

    # Access the Windows-only CreateJunction via getattr so type checkers do
    # not fail on non-Windows platforms. When it is present, attempt it first;
    # if it is unavailable or raises, fall back to mklink /J.
    create_junction = getattr(_winapi, 'CreateJunction', None)
    junction_error: OSError | None = None
    if create_junction is not None:
        try:
            create_junction(str(target), str(link_path))
        except OSError as error:
            junction_error = error
    if create_junction is None or junction_error is not None:
        reason = junction_error if junction_error is not None else 'CreateJunction is unavailable'
        warning(f'CreateJunction failed ({reason}); falling back to mklink /J')
        subprocess.run(
            ['cmd', '/c', 'mklink', '/J', str(link_path), str(target)],
            check=True,
            capture_output=True,
            text=True,
        )


class LinkAction(NamedTuple):
    """What Step 3 does to one linkable entry of a profile.

    Attributes:
        entry: The entry name, one of LINKABLE_PROFILE_DIRS.
        kind: 'create' (no entry on disk, or an empty real directory), 'keep'
            (a link already pointing at the target), 'repair' (a link pointing
            elsewhere), 'convert' (a real directory moved aside, then linked),
            'unlink' (a link removed because a typed or environment value no
            longer asks for it), or 'undeclared' (a link on disk no value asks
            for, left alone).
        link_path: The entry path inside the profile.
        target: The real directory the link points at; None for 'unlink' and
            'undeclared'.
        moved_to: Where 'convert' moves the real directory; None otherwise.
        item_count: The direct entries of the real directory 'convert' moves.
    """

    entry: str
    kind: str
    link_path: Path
    target: Path | None
    moved_to: Path | None = None
    item_count: int = 0


# The action kinds after which an entry is a link to its target
LINKED_ACTION_KINDS: frozenset[str] = frozenset({'create', 'keep', 'repair', 'convert'})


class LinkPlan(NamedTuple):
    """Everything Step 3 does to a profile's links, decided before consent.

    Attributes:
        source: The display name of the profile the links come from.
        actions: One action per entry Step 3 touches or reports, in
            LINKABLE_PROFILE_DIRS order.
        errors: Why the plan cannot be carried out; the run exits with code 1
            before any write when this is non-empty.
    """

    source: str
    actions: list[LinkAction]
    errors: list[str]

    @property
    def linked_entries(self) -> list[str]:
        """The entries that are links once the plan has been applied."""
        return [action.entry for action in self.actions if action.kind in LINKED_ACTION_KINDS]

    @property
    def moved_aside(self) -> list[LinkAction]:
        """The real directories the plan moves aside."""
        return [action for action in self.actions if action.kind == 'convert']

    def rows(self) -> list[str]:
        """Render the plan for the installation summary, one line per action."""
        rendered: list[str] = []
        for action in self.actions:
            if action.kind == 'create':
                rendered.append(f'{action.entry} -> {action.target} [create]')
            elif action.kind == 'keep':
                rendered.append(f'{action.entry} -> {action.target} [kept]')
            elif action.kind == 'repair':
                rendered.append(f'{action.entry} -> {action.target} [repair: the link points elsewhere]')
            elif action.kind == 'convert':
                rendered.append(f'{action.entry} -> {action.target} [create after moving the real directory aside]')
            elif action.kind == 'unlink':
                rendered.append(f'{action.entry}: [unlink] the link is removed; this run installs the real directory')
            else:
                rendered.append(f'{action.entry}: [on disk, not declared] the link is left alone')
        return rendered

    def move_aside_rows(self) -> list[str]:
        """Render every directory the plan moves aside, with its path, item count and consequence."""
        rendered: list[str] = []
        for action in self.moved_aside:
            items = 'item' if action.item_count == 1 else 'items'
            line = f'{action.entry}: {action.link_path} ({action.item_count} {items}) -> {action.moved_to}'
            if action.entry == SESSIONS_PROFILE_DIR:
                line += '; those sessions and auto-memory stop appearing in this profile'
            rendered.append(line)
        return rendered


def _count_direct_entries(directory: Path) -> int:
    """Count the direct entries of a directory, 0 when it cannot be listed."""
    try:
        return sum(1 for _ in directory.iterdir())
    except OSError:
        return 0


def move_aside_name(entry: str, timestamp: str) -> str:
    """Name the directory a conversion moves a real entry aside to."""
    return f'{entry}.unlinked-{timestamp}'


def plan_profile_links(
    profile_dir: Path,
    wanted: list[str],
    source_dir: Path,
    *,
    source_name: str,
    typed: bool,
    timestamp: str,
) -> LinkPlan:
    """Decide what Step 3 does to each linkable entry of a profile.

    A wanted entry is created when absent (an empty real directory is
    replaced), kept when it is a link to the target, repaired when it is a
    link elsewhere, and converted -- the real directory moved aside to
    <entry>.unlinked-<timestamp>, never deleted -- only when the value asking
    for it was typed or came from the environment; under a remembered or
    configuration value a real non-empty directory is an error naming the
    typed value that converts it. A link no value asks for is removed only
    under a typed or environment value and is otherwise reported as on disk
    and left alone. projects links to the final real directory behind the
    source's projects, so a link never points at a link; every other entry
    links to the source's own directory, created there when absent.

    Args:
        profile_dir: The profile directory whose entries are linked.
        wanted: The entries to link, a subset of LINKABLE_PROFILE_DIRS.
        source_dir: The directory of the profile the links come from.
        source_name: Its display name, for the plan.
        typed: Whether the link-dirs value was typed or came from the
            environment, which allows converting and unlinking.
        timestamp: The timestamp every moved-aside directory is named with.

    Returns:
        The plan, with errors when it cannot be carried out.
    """
    actions: list[LinkAction] = []
    errors: list[str] = []
    wanted_set = set(wanted)
    for entry in LINKABLE_PROFILE_DIRS:
        link_path = profile_dir / entry
        is_link = _is_directory_link(link_path)
        if entry in wanted_set:
            candidate = source_dir / entry
            target = _final_real_directory(candidate) if entry == SESSIONS_PROFILE_DIR else candidate
            if is_link:
                kind = 'keep' if _link_points_to(link_path, target) else 'repair'
                actions.append(LinkAction(entry, kind, link_path, target))
            elif not link_path.exists():
                actions.append(LinkAction(entry, 'create', link_path, target))
            elif link_path.is_dir():
                count = _count_direct_entries(link_path)
                if count == 0:
                    actions.append(LinkAction(entry, 'create', link_path, target))
                elif typed:
                    moved_to = profile_dir / move_aside_name(entry, timestamp)
                    actions.append(LinkAction(entry, 'convert', link_path, target, moved_to, count))
                else:
                    errors.append(
                        f'{link_path} is a real directory with {count} item(s), and only a typed value converts it: '
                        f'pass --link-dirs {",".join(wanted)} (or set CLAUDE_CODE_TOOLBOX_LINK_DIRS) to move it aside '
                        f'to {move_aside_name(entry, timestamp)} and link {entry} from profile "{source_name}".',
                    )
            else:
                errors.append(f'{link_path} is a file, so {entry} cannot be linked; move the file away first.')
        elif is_link:
            actions.append(LinkAction(entry, 'unlink' if typed else 'undeclared', link_path, None))
    return LinkPlan(source_name, actions, errors)


def apply_link_plan(plan: LinkPlan) -> None:
    """Carry out a link plan on disk.

    An OSError from a move, a link or an unlink, or a CalledProcessError
    from the mklink /J fallback, propagates to the caller.

    Args:
        plan: The plan from plan_profile_links(), with no errors.
    """
    for action in plan.actions:
        if action.kind == 'keep':
            info(f'{action.entry}/ already linked to {action.target}')
            continue
        if action.kind == 'undeclared':
            info(f'{action.entry}/ is a link on disk that no value declares; left alone')
            continue
        if action.kind == 'unlink':
            _remove_directory_link(action.link_path)
            success(f'Removed the {action.entry}/ link; this run installs the real directory')
            continue
        if action.kind == 'repair':
            _remove_directory_link(action.link_path)
        elif action.kind == 'convert' and action.moved_to is not None:
            action.link_path.rename(action.moved_to)
            success(f'Moved {action.link_path} aside to {action.moved_to}')
        elif action.link_path.is_dir():
            action.link_path.rmdir()
        assert action.target is not None
        link_profile_directory(action.link_path, action.target)
        success(f'Linked {action.entry}/ -> {action.target}')


def verify_profile_links(profile_dir: Path, plan: LinkPlan) -> list[str]:
    """Check that every entry a plan linked is still a link to its target.

    Args:
        profile_dir: The profile directory.
        plan: The plan Step 3 applied.

    Returns:
        One message per entry that is no longer a link to its target.
    """
    broken: list[str] = []
    for action in plan.actions:
        if action.kind not in LINKED_ACTION_KINDS or action.target is None:
            continue
        link_path = profile_dir / action.entry
        if not _is_directory_link(link_path):
            broken.append(f'{link_path} is no longer a link (it was linked to {action.target})')
        elif not _link_points_to(link_path, action.target):
            broken.append(f'{link_path} no longer points at {action.target}')
    return broken


def export_setup_time_config_dir(
    primary_command_name: str | None,
    artifact_base_dir: Path,
) -> str | None:
    """Export CLAUDE_CONFIG_DIR into the process env for setup-time child processes.

    Child processes spawned during setup (dependency installers, npx-based
    tooling, ``claude mcp ...``, IDE-extension install) inherit ``os.environ``,
    so exporting CLAUDE_CONFIG_DIR makes them resolve against the isolated
    profile directory rather than the default ~/.claude. The export is applied
    only for an isolated profile (``primary_command_name`` truthy); a
    non-isolated run leaves the process env untouched.

    The exported value is transient and process-scoped only. The runtime
    launcher export remains the sole authoritative runtime source, and this
    value is deliberately never written to config.json.

    Args:
        primary_command_name: The primary command name when an isolated profile
            is configured, otherwise None.
        artifact_base_dir: The directory CLAUDE_CONFIG_DIR should point to for an
            isolated profile (the isolated profile's base directory).

    Returns:
        The exported value (``str(artifact_base_dir)``) when an isolated profile
        triggers the export, otherwise None.
    """
    if not primary_command_name:
        return None
    config_dir_value = str(artifact_base_dir)
    os.environ['CLAUDE_CONFIG_DIR'] = config_dir_value
    info(f'Exported CLAUDE_CONFIG_DIR={artifact_base_dir} for setup-time child processes')
    return config_dir_value


def resolve_artifact_base_dir(
    primary_command_name: str | None,
    user_settings: dict[str, Any] | None,
) -> tuple[Path, bool]:
    """Resolve the directory this run writes its artifacts into.

    An isolated run (``command-names`` present) targets
    ``~/.claude/{primary_command_name}``, unless ``user-settings.env`` pins
    CLAUDE_CONFIG_DIR, in which case that value wins. A non-isolated run
    targets the base ``~/.claude`` directory.

    The function is free of side effects so the ambient-CLAUDE_CONFIG_DIR
    guard can learn the target directory before the installation summary,
    and ``main()`` can resolve the same directory again when it starts
    writing.

    Args:
        primary_command_name: The primary command name when an isolated
            profile is configured, otherwise None.
        user_settings: The resolved ``user-settings`` section, or None.

    Returns:
        Tuple of (target directory, whether ``user-settings.env`` supplied
        CLAUDE_CONFIG_DIR).
    """
    claude_user_dir = get_real_user_home() / '.claude'
    if not primary_command_name:
        return claude_user_dir, False

    user_env_section = user_settings.get('env') if user_settings else None
    user_config_dir = (
        user_env_section.get('CLAUDE_CONFIG_DIR')
        if isinstance(user_env_section, dict)
        else None
    )
    if isinstance(user_config_dir, str) and user_config_dir:
        if user_config_dir.startswith('~'):
            return Path(user_config_dir).expanduser(), True
        return Path(user_config_dir), True

    return claude_user_dir / primary_command_name, False


def _normalize_config_dir_key(value: str) -> str:
    """Normalize a CLAUDE_CONFIG_DIR value for directory comparison.

    Args:
        value: Raw directory path, possibly relative or tilde-prefixed.

    Returns:
        Absolute, separator- and case-normalized comparison key.
    """
    path = Path(value.strip())
    with contextlib.suppress(RuntimeError):
        path = path.expanduser()
    return _normalize_project_dir_key(os.path.abspath(path))


def check_ambient_claude_config_dir(
    primary_command_name: str | None,
    artifact_base_dir: Path,
) -> bool:
    """Check the inherited CLAUDE_CONFIG_DIR against this run's target directory.

    The Claude CLI resolves CLAUDE_CONFIG_DIR ahead of the home directory, so
    ``claude mcp add`` and the global-config writes follow that variable while
    the rest of the run writes to its own target directory. The value reaches
    the run from an isolated profile session's launcher export, from an
    OS-level variable, or from a settings ``env`` entry. A non-isolated run
    therefore aborts, because it has no way to reconcile the two destinations;
    an isolated run replaces the variable for its child processes and reports
    that it did.

    Args:
        primary_command_name: The primary command name when an isolated
            profile is configured, otherwise None.
        artifact_base_dir: The directory this run writes its artifacts into.

    Returns:
        True when the run may proceed, False when it must abort.
    """
    ambient = _ambient_claude_config_dir()
    if ambient is None:
        return True

    if not primary_command_name:
        error(f'CLAUDE_CONFIG_DIR is set to "{ambient}" in this environment.')
        error(
            'This configuration has no command-names, so the toolbox writes its artifacts to '
            f'{artifact_base_dir} and its global config to the home-directory .claude.json, '
            'while the Claude CLI resolves CLAUDE_CONFIG_DIR ahead of the home directory and '
            'would put MCP servers and global config under the directory that variable names. '
            'The run would be split across two directories.',
        )
        error('')
        error('Fix one of:')
        error('  1. Clear the variable and run setup again:')
        error('       bash:       unset CLAUDE_CONFIG_DIR')
        error('       PowerShell: Remove-Item Env:CLAUDE_CONFIG_DIR')
        error('  2. Run the setup from a terminal that is not inside an isolated profile session')
        error('  3. If a configuration persists the variable through os-env-variables or')
        error('     user-settings.env, remove it there and open a new terminal')
        return False

    if _normalize_config_dir_key(ambient) != _normalize_config_dir_key(str(artifact_base_dir)):
        warning(
            f'CLAUDE_CONFIG_DIR is set to "{ambient}" in this environment; setup replaces it '
            f'with {artifact_base_dir} for its child processes, so this run configures the '
            f'{primary_command_name} profile and not the one the variable points at.',
        )

    return True


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


def _apply_env_overrides(env_pairs: list[str] | None) -> None:
    """Apply --env KEY=VALUE pairs to the process environment.

    Explicit --env values override inherited environment variables,
    matching shell semantics (VAR=x command). Exits with an error on a
    malformed pair, mirroring argparse's fail-fast handling of bad input.

    Args:
        env_pairs: Raw KEY=VALUE strings from the repeatable --env flag,
            or None when the flag was not used.
    """
    for pair in env_pairs or []:
        key, separator, value = pair.partition('=')
        if not separator or not ENV_VAR_NAME_PATTERN.match(key):
            error(f"Invalid --env value '{pair}': expected KEY=VALUE with a valid variable name")
            sys.exit(1)
        os.environ[key] = value


def resolve_args(args: argparse.Namespace) -> argparse.Namespace:
    """Merge CLI flags with environment variable equivalents.

    Applies --env KEY=VALUE overrides to the process environment FIRST,
    so every env-var read below (and every later consumer, including
    child processes) sees them. Every fallback comes from ENV_TWINS, and
    CLI arguments take precedence over their environment variables:

    - A switch twin turns its store_true flag on only with the exact
      value '1'; argparse leaves the flag False when it is absent, so the
      variable is the channel for piped invocations that cannot pass flags.
    - A value twin fills its argument only when the argument is absent.
      An empty export (a common CI-template default) counts as absent
      instead of aborting the run over a flag the user never passed; an
      explicit CLI value, empty or not, is kept.

    args.origins maps every value argument that ended up set to 'cli' or
    'env'. args.auth carries CLAUDE_CODE_TOOLBOX_ENV_AUTH, which has no
    flag, or None. args.config carries the positional configuration or
    CLAUDE_CODE_TOOLBOX_ENV_CONFIG.

    Called immediately after parse_args() and before any flag-dependent
    logic (admin checks, confirmation gates, installation flow).

    Args:
        args: Parsed command-line arguments from argparse.

    Returns:
        Modified args namespace with environment variables merged.
    """
    _apply_env_overrides(getattr(args, 'env_vars', None))
    origins: dict[str, str] = {}
    for twin in ENV_TWINS:
        env_value = os.environ.get(twin.variable)
        if twin.kind == 'switch':
            setattr(args, twin.dest, bool(getattr(args, twin.dest, False)) or env_value == '1')
            continue
        if getattr(args, twin.dest, None) is not None:
            origins[twin.dest] = 'cli'
        elif env_value:
            setattr(args, twin.dest, env_value)
            origins[twin.dest] = 'env'
        else:
            setattr(args, twin.dest, None)
    args.origins = origins
    return args


class ProfileRerun(NamedTuple):
    """The installed profile a --profile value names.

    Attributes:
        primary: The profile's primary command name, None for the base profile.
        manifest_path: Its manifest.json.
        manifest: The manifest content.
        identity: The configuration identity the manifest records or derives,
            or None when it records a relative local source that cannot be
            resolved from the current directory.
    """

    primary: str | None
    manifest_path: Path
    manifest: dict[str, Any]
    identity: str | None

    @property
    def name(self) -> str:
        """The profile's display name."""
        return profile_display_name(self.primary)


def resolve_profile_rerun(args: argparse.Namespace, home_dir: Path) -> ProfileRerun:
    """Locate the installed profile --profile names.

    Args:
        args: Arguments after resolve_args(), with a --profile value other
            than ALL_PROFILES.
        home_dir: User home directory.

    Returns:
        The profile and its manifest. The run exits with code 1 when the
        name is invalid, no profile of that name is installed, or its
        manifest cannot be read.
    """
    source = PROFILE_SOURCES[args.origins['profile']]
    value = str(args.profile)
    primary = None if value == 'base' else value
    if primary is not None:
        name_errors = command_name_errors([primary], source)
        if name_errors:
            for err in name_errors:
                error(err)
            sys.exit(1)
    display = profile_display_name(primary)
    manifest_path = profile_directory(home_dir, primary) / MANIFEST_FILENAME
    try:
        manifest = read_profile_manifest(manifest_path)
    except ValueError as e:
        error(f'Profile "{display}" cannot be re-run: {e}')
        info('Repair or remove the manifest, then run the setup again.')
        sys.exit(1)
    if manifest is None:
        error(f'No installed profile named "{display}": {manifest_path} does not exist.')
        if primary is not None:
            info(f'Install it first: run the setup with a configuration and --command-names {primary}')
        else:
            info('Install the base profile first: run the setup with a configuration and no command names')
        sys.exit(1)
    return ProfileRerun(primary, manifest_path, manifest, manifest_config_identity(manifest))


def rerun_config_source(rerun: ProfileRerun) -> str:
    """Return the configuration a --profile re-run loads when none is given.

    Args:
        rerun: The profile being re-run.

    Returns:
        The configuration source the manifest records, in a form
        load_config_from_source() accepts. The run exits with code 1 when
        the manifest records a relative local source that cannot be
        resolved from the current directory.
    """
    source = rerun.manifest.get('config_source')
    if rerun.identity is None or not isinstance(source, str) or not source:
        error(
            f'The manifest of profile "{rerun.name}" records the configuration {source!r}, which cannot '
            f'be resolved from this directory; pass the configuration: --profile {rerun.name} <configuration>',
        )
        sys.exit(1)
    return source


def _read_target_manifest(primary_command_name: str | None, config: dict[str, Any]) -> dict[str, Any] | None:
    """Read the manifest of the profile a run installs into.

    Args:
        primary_command_name: The profile's primary command name, None for
            the base profile.
        config: The resolved configuration, whose user-settings may relocate
            the profile directory.

    Returns:
        The manifest, or None when the profile is new or its name is not a
        valid command name (validation reports that later). The run exits
        with code 1 when the manifest exists but cannot be read.
    """
    if primary_command_name is not None and command_name_errors([primary_command_name], 'command-names'):
        return None
    target_dir, _ = resolve_artifact_base_dir(primary_command_name, config.get('user-settings'))
    try:
        return read_profile_manifest(target_dir / MANIFEST_FILENAME)
    except ValueError as e:
        error(f'The manifest of profile "{profile_display_name(primary_command_name)}" cannot be read: {e}')
        info('Repair or remove it, then run the setup again.')
        sys.exit(1)


def _consent_is_interactive(args: argparse.Namespace) -> bool:
    """Report whether this run asks the user before it acts.

    Args:
        args: Arguments after resolve_args().

    Returns:
        True when neither --yes nor --dry-run is set and a terminal (or
        /dev/tty) can answer a prompt.
    """
    return not args.yes and not args.dry_run and (sys.stdin.isatty() or _dev_tty_available())


def guard_decision(
    args: argparse.Namespace,
    *,
    title: str,
    lines: list[str],
    question: str,
    remedy: list[str],
    accepted_by: str | None = None,
) -> None:
    """Hold a run back until a change it would make is accepted.

    A flag that accepts the change lets the run continue. An interactive
    run asks; a declined question cancels the setup with exit code 0.
    Under --yes, --dry-run, or without a terminal the run stops with exit
    code 1 and the remedy, so nothing changes without consent.

    Args:
        args: Arguments after resolve_args().
        title: What the run would change.
        lines: Details printed under the title.
        question: The y/N question an interactive run asks.
        remedy: How to accept the change or avoid it, one line each.
        accepted_by: The flag or variable that accepted the change, or None.
    """
    print()
    warning(title)
    for line in lines:
        warning(f'  {line}')
    if accepted_by:
        info(f'Accepted via {accepted_by}.')
        return
    if _consent_is_interactive(args):
        print()
        if _ask_yes_no(f'{Colors.YELLOW}{question} [y/N]: {Colors.NC}'):
            return
        info('Setup cancelled by user.')
        sys.exit(0)
    print()
    if args.dry_run:
        error('Dry run: a real run stops here.')
    else:
        error('Refusing to continue without consent.')
    for line in remedy:
        info(f'  {line}')
    sys.exit(1)


def guard_environment_name_change(
    args: argparse.Namespace,
    names: CommandNames,
    manifest: dict[str, Any] | None,
    profile_name: str,
) -> None:
    """Hold a run back when the environment would change a profile's command names.

    A typed --command-names value proceeds; a value from
    CLAUDE_CODE_TOOLBOX_COMMAND_NAMES that differs from the names the
    profile's manifest records needs consent, because a leftover variable
    must not rename a profile silently.

    Args:
        args: Arguments after resolve_args().
        names: The run's effective command names.
        manifest: The manifest of the profile the run installs into.
        profile_name: The profile's display name.
    """
    if names.origin != 'env' or names.remembered or manifest is None:
        return
    recorded = [str(item) for item in cast(list[object], manifest.get('command_names') or [])]
    if not recorded or recorded == names.names:
        return
    variable = COMMAND_NAMES_SOURCES['env']
    guard_decision(
        args,
        title=(
            f'{variable} changes the command names of profile "{profile_name}" from '
            f'{_format_names(recorded)} to {_format_names(names.names)}.'
        ),
        lines=[],
        question=f'Change the command names of profile "{profile_name}" to {_format_names(names.names)}?',
        remedy=[
            f'Pass --command-names {",".join(names.names)} to change them.',
            f'Clear {clear_variables_text([variable])} to keep {_format_names(recorded)}.',
        ],
    )


def guard_configuration_switch(
    args: argparse.Namespace,
    *,
    manifest: dict[str, Any],
    profile_name: str,
    old_identity: str,
    new_identity: str,
    new_source: str,
    residue: ProfileResidue,
) -> bool:
    """Hold a run back when a different configuration would re-provision a profile.

    Args:
        args: Arguments after resolve_args().
        manifest: The profile's current manifest.
        profile_name: The profile's display name.
        old_identity: The configuration identity the manifest records.
        new_identity: The identity of the configuration this run was given.
        new_source: The resolved source of that configuration.
        residue: What the previous configuration leaves behind.

    Returns:
        True when the run switches the profile (and removes the residue
        after consent); False when both identities match.
    """
    if old_identity == new_identity:
        return False
    from_environment = args.origins.get('config') == 'env'
    given = 'CLAUDE_CODE_TOOLBOX_ENV_CONFIG' if from_environment else 'the configuration argument'
    old_source = manifest.get('config_source')
    rendered = [f'  {line}' for line in residue.lines()]
    lines = (
        ['The previous configuration leaves behind:', *rendered] if residue
        else ['The previous configuration leaves nothing behind.', *rendered]
    )
    accepted = '--switch-config or CLAUDE_CODE_TOOLBOX_SWITCH_CONFIG=1' if args.switch_config else None
    # The remedy undoes the source the configuration came from
    if from_environment:
        keep_remedy = (
            f'Clear {clear_variables_text(["CLAUDE_CODE_TOOLBOX_ENV_CONFIG"])} and re-run the profile '
            f'with its own configuration: --profile {profile_name}.'
        )
    else:
        keep_remedy = (
            'Drop the configuration argument and re-run the profile with its own configuration: '
            f'--profile {profile_name}.'
        )
    guard_decision(
        args,
        title=(
            f'Profile "{profile_name}" was installed from {old_source}; {given} names a different '
            f'configuration, {new_source}.'
        ),
        lines=lines,
        question=f'Switch profile "{profile_name}" to {new_source} and remove what the previous configuration left?',
        remedy=[
            (
                'Pass --switch-config (or set CLAUDE_CODE_TOOLBOX_SWITCH_CONFIG=1) to accept the switch '
                'and remove what the previous configuration left.'
            ),
            keep_remedy,
        ],
        accepted_by=accepted,
    )
    return True


def remove_dropped_command_wrappers(previous_names: list[str], current_names: list[str], home_dir: Path) -> list[str]:
    """Remove the ~/.local/bin wrappers of names a profile no longer registers.

    Only wrappers the toolbox wrote are removed (see is_toolbox_wrapper()).

    Args:
        previous_names: The names the profile's previous manifest lists.
        current_names: The names this run registers.
        home_dir: User home directory.

    Returns:
        The dropped names.
    """
    current = {name.casefold() for name in current_names}
    dropped = [name for name in previous_names if name.casefold() not in current]
    if not dropped:
        return []
    local_bin = home_dir / '.local' / 'bin'
    suffixes: tuple[str, ...] = ('', '.cmd', '.ps1') if platform.system() == 'Windows' else ('',)
    for name in dropped:
        for suffix in suffixes:
            entry = local_bin / f'{name}{suffix}'
            if (entry.exists() or entry.is_symlink()) and is_toolbox_wrapper(entry, name):
                try:
                    entry.unlink()
                except OSError as e:
                    warning(f'Cannot remove the wrapper {entry}: {e}')
    success(f'Removed the wrapper(s) of dropped alias(es): {", ".join(dropped)}')
    return dropped


def pin_effect_line(pinned_version: str, installed_version: str | None, other_profiles: list[str]) -> str:
    """Describe what a run's version pin does to the binary other profiles use.

    Args:
        pinned_version: The version this run pins.
        installed_version: The version installed now, or None when unknown.
        other_profiles: Display names of the other installed profiles.

    Returns:
        One summary line.
    """
    if not other_profiles:
        return f'Claude Code version pin {pinned_version}: holds the binary every profile uses'
    profiles = ', '.join(other_profiles)
    if installed_version and installed_version != pinned_version:
        return (
            f'Claude Code version pin {pinned_version}: moves the binary from {installed_version} to '
            f'{pinned_version} for the other installed profile(s) {profiles}'
        )
    return (
        f'Claude Code version pin {pinned_version}: holds the binary at {pinned_version} for the other '
        f'installed profile(s) {profiles}'
    )


def shared_destination_warnings(
    files_to_download: list[dict[str, Any]],
    config_source: str,
    base_url: str | None,
    *,
    home_dir: Path,
    this_identity: str,
    this_profile: str,
) -> list[str]:
    """Warn about destinations outside ~/.claude another configuration's profile also installs.

    Args:
        files_to_download: This run's resolved files-to-download list.
        config_source: Where this configuration was loaded from.
        base_url: This configuration's base-url, or None.
        home_dir: User home directory.
        this_identity: This configuration's identity.
        this_profile: This run's profile display name.

    Returns:
        One warning per destination that a profile of a different
        configuration recorded from a different source.
    """
    records = machine_wide_download_records(files_to_download, config_source, base_url, home_dir / '.claude')
    if not records:
        return []
    warnings: list[str] = []
    for profile in installed_profiles(home_dir):
        if profile.name == this_profile or profile.manifest is None:
            continue
        if manifest_config_identity(profile.manifest) == this_identity:
            continue
        theirs: dict[str, dict[str, Any]] = {}
        for recorded in cast(list[object], profile.manifest.get('machine_wide_destinations') or []):
            if isinstance(recorded, dict) and isinstance(cast(dict[str, Any], recorded).get('dest'), str):
                recorded_dict = cast(dict[str, Any], recorded)
                theirs[_normalize_config_dir_key(str(recorded_dict['dest']))] = recorded_dict
        for record in records:
            other = theirs.get(_normalize_config_dir_key(str(record['dest'])))
            if other is not None and other.get('source') != record['source']:
                warnings.append(
                    f'{record["dest"]} is also installed by profile "{profile.name}" '
                    f'({profile.manifest.get("config_source")}) from {other.get("source")}; this run writes '
                    f'it from {record["source"]} and leaves it untouched only when the content is identical',
                )
    return warnings


def unrefreshed_profile_lines(home_dir: Path, this_profile: str, refreshed: frozenset[str] = frozenset()) -> list[str]:
    """List the installed profiles a run did not refresh, each with its --profile command.

    Args:
        home_dir: User home directory.
        this_profile: This run's profile display name.
        refreshed: The dependents this run refreshed in Step 23.

    Returns:
        One line per other installed profile this run did not refresh.
    """
    return [
        f'{profile.name} (--profile {profile.name})'
        for profile in installed_profiles(home_dir)
        if profile.name != this_profile and profile.name not in refreshed
    ]


def _exit_on_broken_links(broken: list[str], profile_name: str) -> None:
    """Stop the run when a linked entry is no longer a link to its target.

    Args:
        broken: The messages verify_profile_links() returned.
        profile_name: This run's profile display name.
    """
    if not broken:
        return
    error(f'Profile "{profile_name}" no longer holds every link it was installed with:')
    for line in broken:
        error(f'  - {line}')
    info(f'Re-run the profile to repair its links: --profile {profile_name}')
    sys.exit(1)


def run_dependent_refresh_step(
    dependents: list[InstalledProfile], *, source_name: str, child_run: bool,
) -> list[DependentResult]:
    """Run Step 23: refresh every profile that links content from this one.

    Args:
        dependents: The dependents content_dependents() found before the run.
        source_name: This run's profile display name.
        child_run: Whether another run started this one -- --profile all,
            which runs every installed profile itself, or a source's Step 23,
            which refreshes every dependent itself.

    Returns:
        One result per dependent refreshed; empty when none ran.
    """
    print()
    if child_run:
        print(f'{Colors.CYAN}Step 23: Dependent profiles are refreshed by the run that started this one{Colors.NC}')
        return []
    if not dependents:
        print(f'{Colors.CYAN}Step 23: No installed profile links content from "{source_name}"{Colors.NC}')
        return []
    names = ', '.join(profile.name for profile in dependents)
    print(f'{Colors.CYAN}Step 23: Refreshing {len(dependents)} dependent profile(s): {names}...{Colors.NC}')
    return refresh_dependents(dependents)


def child_run_environment() -> dict[str, str]:
    """Build the environment of a child run (of --profile all, or of a source's Step 23).

    Every argument twin except the repository credential is dropped, so a
    variable set for the parent cannot change what a child installs, and
    CLAUDE_CONFIG_DIR is dropped so each child resolves its own profile.

    Returns:
        The child's environment.
    """
    env = dict(os.environ)
    for twin in ENV_TWINS:
        if twin.variable not in CHILD_RUN_INHERITED_TWINS:
            env.pop(twin.variable, None)
    env.pop('CLAUDE_CONFIG_DIR', None)
    return env


def read_resolved_config_snapshot(profile_dir: Path) -> dict[str, Any] | None:
    """Read the configuration a profile's last run installed.

    Args:
        profile_dir: The profile directory holding resolved-config.yaml.

    Returns:
        The snapshot, or None when the file is missing, unreadable, or not
        a YAML mapping.
    """
    try:
        content = yaml.safe_load((profile_dir / RESOLVED_CONFIG_FILENAME).read_text(encoding='utf-8'))
    except (OSError, yaml.YAMLError):
        return None
    return cast(dict[str, Any], content) if isinstance(content, dict) else None


def _typed_selectors(args: argparse.Namespace) -> bool:
    """Report whether a component selector was typed for this run or came from its environment."""
    return any(args.origins.get(dest) in ('cli', 'env') for dest in ('select', 'with_', 'without'))


def load_dependent_config(source: LinkSource, profile_name: str) -> tuple[dict[str, Any], str, str | None]:
    """Load the configuration of a run that links content: its source's snapshot.

    The source's resolved-config.yaml is the component-selected configuration
    the source installed, so the dependent applies the same files and the
    same choices without fetching anything; its components registry is left
    out, because the source resolved it. The run exits with code 1 when the
    source has no readable snapshot.

    Args:
        source: The profile the run links content from.
        profile_name: This run's profile name, for the message.

    Returns:
        The configuration, the source's recorded configuration source, and
        the source's recorded configuration version.
    """
    snapshot = read_resolved_config_snapshot(source.directory)
    if snapshot is None or source.manifest is None:
        error(
            f'Profile "{profile_name}" links content from profile "{source.name}", whose '
            f'{RESOLVED_CONFIG_FILENAME} is missing or unreadable; re-run the source first: --profile {source.name}',
        )
        sys.exit(1)
    config = deepcopy(snapshot)
    config.pop('components', None)
    source_config = str(source.manifest.get('config_source') or '')
    version = source.manifest.get('version')
    info(f'Applying the configuration profile "{source.name}" installed ({source.directory / RESOLVED_CONFIG_FILENAME})')
    return config, source_config, str(version) if version is not None else None


# The configuration sections each linkable entry is installed from, so a
# linked entry installs nothing and validates nothing of its own
_LINKED_ENTRY_SECTIONS: dict[str, tuple[str, ...]] = {
    'skills': ('skills',),
    'agents': ('agents',),
    'commands': ('slash-commands',),
    'rules': ('rules',),
    'hooks': ('hooks',),
    'prompts': ('command-defaults',),
}


def config_without_linked_sections(config: dict[str, Any], linked_entries: frozenset[str]) -> dict[str, Any]:
    """Copy a configuration without the sections its linked entries are installed from.

    Hook events stay, because the profile's own config.json wires them; only
    the files and helpers that would be downloaded into the linked hooks
    directory are dropped, together with the system prompt of a linked
    prompts directory.

    Args:
        config: The resolved configuration.
        linked_entries: The entries that are links.

    Returns:
        A shallow copy with the linked sections emptied.
    """
    copy = dict(config)
    for entry in linked_entries:
        for section in _LINKED_ENTRY_SECTIONS.get(entry, ()):
            if section == 'hooks' and isinstance(copy.get('hooks'), dict):
                hooks = dict(cast(dict[str, Any], copy['hooks']))
                hooks['files'] = []
                hooks['helpers'] = []
                copy['hooks'] = hooks
            elif section == 'command-defaults' and isinstance(copy.get('command-defaults'), dict):
                defaults = dict(cast(dict[str, Any], copy['command-defaults']))
                defaults.pop('system-prompt', None)
                copy['command-defaults'] = defaults
            elif section in copy:
                copy[section] = []
    return copy


def split_downloads_by_linked_entries(
    files_to_download: list[Any],
    profile_dir: Path,
    linked_entries: frozenset[str],
) -> tuple[list[Any], list[tuple[str, str]]]:
    """Separate the files-to-download entries whose destination lies inside a linked entry.

    Args:
        files_to_download: The resolved files-to-download list.
        profile_dir: The profile directory.
        linked_entries: The entries that are links.

    Returns:
        The entries this run downloads, and (destination, entry) for each
        entry it skips because the source holds that directory.
    """
    kept: list[Any] = []
    skipped: list[tuple[str, str]] = []
    for item in files_to_download:
        if not isinstance(item, dict):
            kept.append(item)
            continue
        entry_dict = cast(dict[str, Any], item)
        source, dest = entry_dict.get('source'), entry_dict.get('dest')
        inside: str | None = None
        if source and dest:
            relative = _relative_inside(_download_destination(str(source), str(dest)), profile_dir)
            if relative is not None and relative.parts and relative.parts[0] in linked_entries:
                inside = relative.parts[0]
        if inside is None:
            kept.append(item)
        else:
            skipped.append((str(dest), inside))
    return kept, skipped


def refresh_all_elevation_reasons(profiles: list[InstalledProfile], args: argparse.Namespace) -> list[str]:
    """List why a --profile all run needs administrator rights before any child starts.

    Elevation is decided once, in the parent: a child relaunched through
    UAC opens its own window and exits 0, so the parent would report it as
    refreshed while it still runs. Without --skip-install every profile
    installs Claude Code, which needs elevation; with it, each profile's
    resolved-config.yaml decides, and a profile whose snapshot cannot be
    read counts as needing it.

    Args:
        profiles: The installed profiles the run refreshes.
        args: Arguments after resolve_args().

    Returns:
        The union of reasons, in profile order; empty off Windows, when the
        process already holds administrator rights, under --no-admin, and
        under --dry-run (a preview never elevates).
    """
    if args.no_admin or args.dry_run or platform.system() != 'Windows' or is_admin():
        return []
    if not args.skip_install:
        return admin_elevation_reasons({}, args)
    reasons: list[str] = []
    for profile in profiles:
        snapshot = read_resolved_config_snapshot(profile.directory)
        if snapshot is None:
            reasons.append(
                f'Profile "{profile.name}": {RESOLVED_CONFIG_FILENAME} is missing or unreadable, '
                'so its run may need elevation',
            )
            continue
        reasons.extend(reason for reason in admin_elevation_reasons(snapshot, args) if reason not in reasons)
    return reasons


def refresh_all_profiles(args: argparse.Namespace, *, elevated_via_uac: bool = False) -> int:
    """Re-run every installed profile, the base first, each in its own child run.

    The parent decides elevation once: when any profile's run needs
    administrator rights the parent lacks, it relaunches itself through UAC
    before asking for consent, so every child inherits the rights and none
    opens a window of its own. The parent then asks for consent once (or
    takes --yes); every child runs with --yes, --child-run, the parent's
    --dry-run and --skip-install, and --no-admin (a dry run
    forwards the parent's --no-admin instead, so each child still prints
    what a real run would elevate for). The report at the end names each
    profile with its result and the --profile command that retries a
    failed one; a parent relaunched through UAC then holds its window
    under the success or errors banner until Enter, because that window
    closes when the process exits.

    Args:
        args: Arguments after resolve_args().
        elevated_via_uac: Whether this process is the window a UAC
            relaunch opened.

    Returns:
        The exit code: 1 when any child failed, the request was invalid, or
        elevation was denied; 0 otherwise.
    """
    # Each conflicting value is named the way it was given: the flag, or
    # the variable it came from, with the commands that clear the variables
    def _given_as(dest: str, flag: str) -> str:
        if args.origins.get(dest) != 'env':
            return flag
        return next(twin.variable for twin in ENV_TWINS if twin.dest == dest)

    conflicts = [
        name for name, present in (
            (_given_as('config', 'a configuration'), bool(args.config)),
            (_given_as('command_names', '--command-names'), args.command_names is not None),
            (_given_as('select', '--select'), args.select is not None),
            (_given_as('with_', '--with'), args.with_ is not None),
            (_given_as('without', '--without'), args.without is not None),
            ('--switch-config', bool(args.switch_config)),
            ('--list-components', bool(args.list_components)),
            (_given_as('link_dirs', '--link-dirs'), args.link_dirs is not None),
            (_given_as('link_from', '--link-from'), args.link_from is not None),
        ) if present
    ]
    if conflicts:
        variables = [name for name in conflicts if name.startswith('CLAUDE_CODE_TOOLBOX_')]
        remedies: list[str] = []
        if len(variables) < len(conflicts):
            remedies.append('drop them from the command line')
        if variables:
            remedies.append(f'clear {clear_variables_text(variables)}')
        error(
            f'--profile {ALL_PROFILES} refreshes every installed profile from its own manifest and cannot '
            f'be combined with {", ".join(conflicts)}; {" and ".join(remedies)}.',
        )
        return 1
    home_dir = get_real_user_home()
    profiles = order_profiles_source_first(installed_profiles(home_dir))
    if not profiles:
        error('No installed profile has a manifest under ~/.claude; install a configuration first.')
        return 1
    print()
    info(f'Refreshing {len(profiles)} installed profile(s): {", ".join(profile.name for profile in profiles)}')
    elevation_reasons = refresh_all_elevation_reasons(profiles, args)
    if elevation_reasons:
        print()
        print(f'{Colors.YELLOW}========================================================================{Colors.NC}')
        print(f'{Colors.YELLOW}     Administrator Privileges Required{Colors.NC}')
        print(f'{Colors.YELLOW}========================================================================{Colors.NC}')
        print()
        info('Refreshing the installed profiles requires administrator privileges for:')
        for reason in elevation_reasons:
            info(f'  - {reason}')
        print()
        info('Requesting administrator elevation...')
        info('A new window will open with administrator privileges.')
        info('Please look for the UAC dialog and click "Yes" to continue.')
        print()
        request_admin_elevation()
        # If we reach here, elevation was denied
        error('Administrator elevation was denied')
        error('Please run this script as administrator manually, or pass --no-admin to skip elevation')
        return 1
    if not args.yes and not args.dry_run:
        if not (sys.stdin.isatty() or _dev_tty_available()):
            print()
            error('Cannot proceed: no interactive terminal available')
            info('Pass --yes (or set CLAUDE_CODE_TOOLBOX_CONFIRM_INSTALL=1) to refresh every profile, '
                 'or --dry-run to preview each one.')
            return 1
        print()
        if not _ask_yes_no(f'{Colors.YELLOW}Refresh these {len(profiles)} profile(s)? [y/N]: {Colors.NC}'):
            info('Setup cancelled by user.')
            return 0
    # A child never decides elevation for itself: the parent did, so a
    # child that relaunched through UAC could only exit 0 unobserved
    child_flags = ['--yes', CHILD_RUN_FLAG]
    for flag, present in (
        ('--dry-run', args.dry_run),
        ('--skip-install', args.skip_install),
        ('--no-admin', args.no_admin or not args.dry_run),
    ):
        if present:
            child_flags.append(flag)
    launch = [sys.executable, *_elevation_launch_args(__name__, sys.argv[0])]
    env = child_run_environment()
    results: list[tuple[str, int]] = []
    for profile in profiles:
        print()
        print(f'{Colors.CYAN}=== Profile {profile.name} ==={Colors.NC}')
        try:
            code = subprocess.run([*launch, '--profile', profile.name, *child_flags], env=env, check=False).returncode
        except OSError as e:
            error(f'Cannot start the run of profile "{profile.name}": {e}')
            code = 1
        results.append((profile.name, code))
    print()
    print(f'{Colors.YELLOW}Profiles refreshed:{Colors.NC}')
    failed = 0
    for name, code in results:
        if code == 0:
            print(f'   * {name}: ok')
        else:
            failed += 1
            print(f'   * {name}: failed (exit code {code}); retry with --profile {name}')
    print()
    if elevated_via_uac:
        if failed:
            _hold_elevated_window('Setup Completed with Errors', Colors.RED)
        else:
            _hold_elevated_window(
                'Setup Completed Successfully!',
                Colors.GREEN,
                (
                    'Every installed profile has been refreshed.',
                    'You can now close this window and use the configured environments.',
                ),
            )
    return 1 if failed else 0


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

    parser = argparse.ArgumentParser(description='Setup development environment for Claude Code')
    parser.add_argument('config', nargs='?', help='Configuration file name (e.g., python.yaml)')
    parser.add_argument('--skip-install', action='store_true', help='Skip Claude Code installation')
    parser.add_argument('--no-admin', action='store_true', help='Do not request admin elevation even if needed')
    parser.add_argument(
        '--env',
        dest='env_vars',
        action='append',
        metavar='KEY=VALUE',
        help='Set an environment variable for this run (repeatable; identical in every '
        'shell and forwarded through Windows UAC elevation). Covers every documented '
        'variable, e.g. --env GITHUB_TOKEN=... --env GITLAB_TOKEN=...',
    )
    parser.add_argument(
        '--yes', '-y',
        action='store_true',
        help='Auto-confirm installation (skip interactive confirmation)',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show installation plan and exit without installing or requesting admin elevation',
    )
    parser.add_argument(
        '--select',
        type=str,
        help='Install these components plus their bundled and required components '
        '(comma-separated; sentinels: all, none)',
    )
    parser.add_argument(
        '--with',
        dest='with_',
        type=str,
        help='Add components to the default selection (comma-separated)',
    )
    parser.add_argument(
        '--without',
        type=str,
        help='Remove components from the selection (comma-separated; hard requires still win)',
    )
    parser.add_argument(
        '--list-components',
        action='store_true',
        help='List the components defined by the configuration and exit',
    )
    parser.add_argument(
        '--command-names',
        type=str,
        metavar='NAME[,ALIAS...]',
        help='Install as the isolated profile ~/.claude/NAME with these command names '
        "(comma-separated, primary first); replaces the configuration's command-names; "
        'NAME,none drops every alias',
    )
    parser.add_argument(
        '--profile',
        type=str,
        metavar='NAME',
        help='Re-run the installed profile NAME from its manifest, with no configuration '
        'argument needed; base re-runs the base profile, all refreshes every installed profile',
    )
    parser.add_argument(
        '--switch-config',
        action='store_true',
        help='Accept a different configuration for an existing profile and remove what the '
        'previous configuration left behind',
    )
    parser.add_argument(
        '--link-dirs',
        type=str,
        metavar='ENTRIES',
        help='Take these entries of the isolated profile through a directory link from the profile '
        f'--link-from names (comma-separated; any of {", ".join(LINKABLE_PROFILE_DIRS)}; all for every '
        'entry, none for no entry); every entry but projects links only between installs of one '
        'configuration, and a profile that links one takes its configuration and components from the source',
    )
    parser.add_argument(
        '--link-from',
        type=str,
        metavar='SOURCE',
        help='The profile the linked entries come from: base for ~/.claude (the default), or the '
        'primary command name of an installed isolated profile',
    )
    parser.add_argument(CHILD_RUN_FLAG, dest='child_run', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    resolve_args(args)

    # Refuse to run as root on Unix unless explicitly allowed. Runs after
    # resolve_args so --env CLAUDE_CODE_TOOLBOX_ALLOW_ROOT=1 takes effect
    # (argument parsing performs no work), and before anything else does.
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

    # --profile all refreshes every installed profile, each in its own child run
    if args.profile == ALL_PROFILES:
        sys.exit(refresh_all_profiles(args, elevated_via_uac=was_elevated_via_uac))

    # --profile NAME re-runs an installed profile from its manifest; the
    # configuration defaults to the one the manifest records
    rerun: ProfileRerun | None = None
    if args.profile:
        rerun = resolve_profile_rerun(args, get_real_user_home())

    # The positional configuration, CLAUDE_CODE_TOOLBOX_ENV_CONFIG, or the
    # re-run profile's recorded configuration
    config_name = args.config
    if not config_name and rerun is not None:
        config_name = rerun_config_source(rerun)

    if not config_name:
        error('No configuration specified!')
        info('Usage: setup_environment.py <config_name>')
        info('   or: CLAUDE_CODE_TOOLBOX_ENV_CONFIG=<config_name> setup_environment.py')
        info('   or: setup_environment.py --profile <name>  (re-run an installed profile)')
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

    # Set once a step below has already held the UAC window for its outcome
    elevated_window_held = False

    try:
        # A run that links content applies its source's resolved-config.yaml
        # instead of fetching a configuration: a typed, environment or
        # remembered link value decides that before anything is loaded, and
        # the configuration the run was given is checked for identity only
        home_dir = get_real_user_home()
        early_target = profile_target_name(args, {})
        early_manifest: dict[str, Any] | None = None
        if rerun is not None:
            early_manifest = rerun.manifest
        elif early_target is not None:
            early_manifest = _read_target_manifest(early_target, {})
        link_spec, link_errors = resolve_link_spec(args, {}, early_manifest)
        if link_errors:
            for err in link_errors:
                error(err)
            sys.exit(1)
        link_source: LinkSource | None = None
        dependent_of: LinkSource | None = None
        config_version: str | None = None
        inheritance_chain: list[InheritanceChainEntry] = []
        if early_target is not None and link_spec.links_content:
            link_source, link_errors = resolve_link_source(link_spec, home_dir)
            link_errors.extend(link_request_errors(
                link_spec, link_source,
                primary_command_name=early_target,
                this_identity=config_identity_of_spec(config_name),
                typed_selectors=_typed_selectors(args),
            ))
            if link_errors:
                for err in link_errors:
                    error(err)
                sys.exit(1)
            assert link_source is not None
            config, config_source, config_version = load_dependent_config(link_source, early_target)
            dependent_of = link_source
        else:
            # Load configuration from source (URL, local file, or repository)
            config, config_source = load_config_from_source(config_name, args.auth)

            # Extract version from root config BEFORE inheritance resolution.
            # The version field identifies THIS specific config file's version,
            # not a behavioral setting inherited from parent configs.
            raw_version = config.get('version')
            if raw_version is not None:
                version_str = str(raw_version).strip()
                if version_str:
                    config_version = version_str
                    info(f'Configuration version: {config_version}')

            # Resolve configuration inheritance if present
            if INHERIT_KEY in config:
                info('Configuration uses inheritance, resolving parent configs...')
                config, inheritance_chain = resolve_config_inheritance(
                    config, config_source, auth_param=args.auth,
                )
                success('Configuration inheritance resolved successfully')
        # The current configuration is the last entry of the chain
        inheritance_chain.append(InheritanceChainEntry(
            source=config_source,
            source_type=classify_config_source(config_source),
            name=config.get('name', config_name),
        ))

        # The profile this run installs into and what its manifest remembers:
        # the component delta and the command names an earlier run typed or
        # took from the environment. Read before the selectors are validated,
        # so a remembered delta counts as supplied selectors.
        this_identity = config_identity_of(config_source)
        target_profile = profile_target_name(args, config)
        target_manifest: dict[str, Any] | None = (
            rerun.manifest if rerun is not None else _read_target_manifest(target_profile, config)
        )

        # The links, now with the configuration's own keys: a configuration
        # that declares content links is replaced by its source's snapshot
        # the same way a typed value is, after the same checks
        configured_link_values = yaml_link_values(config)
        if dependent_of is None:
            link_spec, link_errors = resolve_link_spec(args, config, target_manifest)
            if not link_errors and link_spec.dirs:
                link_source, link_errors = resolve_link_source(link_spec, home_dir)
                link_errors.extend(link_request_errors(
                    link_spec, link_source,
                    primary_command_name=target_profile,
                    this_identity=this_identity,
                    typed_selectors=_typed_selectors(args),
                ))
            if link_errors:
                for err in link_errors:
                    error(err)
                sys.exit(1)
            for warn_msg in remembered_link_warnings(link_spec, config, target_manifest):
                warning(warn_msg)
            if link_spec.links_content:
                assert link_source is not None
                assert target_profile is not None
                config, config_source, config_version = load_dependent_config(link_source, target_profile)
                inheritance_chain = [InheritanceChainEntry(
                    source=config_source,
                    source_type=classify_config_source(config_source),
                    name=config.get('name', config_name),
                )]
                dependent_of = link_source

        components_list: list[dict[str, Any]] = [
            cast(dict[str, Any], c)
            for c in config.get('components') or []
            if isinstance(c, dict)
        ]
        # A profile that links content takes its source's component
        # selection, so its own remembered delta is not applied
        remembered_delta_errors = [] if dependent_of is not None else apply_remembered_component_delta(
            args,
            target_manifest,
            [str(c.get('name', '')).strip() for c in components_list],
            profile_name=profile_display_name(target_profile),
            manifest_path=(
                rerun.manifest_path if rerun is not None
                else resolve_artifact_base_dir(target_profile, config.get('user-settings'))[0] / MANIFEST_FILENAME
            ),
        )
        if remembered_delta_errors:
            for err in remembered_delta_errors:
                error(err)
            sys.exit(1)

        # Resolve author-defined component selection at the single choke
        # point: after inheritance resolution and before the admin check and
        # remote file validation, so deselected items never trigger UAC
        # elevation, network fetches, or auth prompts. Downstream consumers
        # re-read config keys fresh, so one in-place filter pass suffices.
        component_errors = validate_components(config)
        hooks_consistency_errors = validate_hooks_files_consistency(config)
        if component_errors or hooks_consistency_errors:
            for err in [*component_errors, *hooks_consistency_errors]:
                error(err)
            sys.exit(1)
        selector_errors = _validate_component_selector_args(
            [str(c.get('name', '')).strip() for c in components_list],
            args,
        )
        if selector_errors:
            for err in selector_errors:
                error(err)
            sys.exit(1)
        if args.list_components:
            display_component_registry(components_list)
            sys.exit(0)

        # The run's command names: --command-names, then its environment twin,
        # then the names the profile's manifest remembers, then the
        # configuration. A typed or environment list replaces the
        # configuration's list, which every later step reads. A name another
        # profile or a foreign ~/.local/bin file holds is refused here, before
        # the summary, consent, or any write.
        effective_command_names, command_names_errors = resolve_command_names(args, config, target_manifest)
        if not command_names_errors and effective_command_names.names:
            command_names_errors = command_name_conflicts(
                effective_command_names.names, get_real_user_home(),
            )
        if command_names_errors:
            for err in command_names_errors:
                error(err)
            sys.exit(1)
        command_names: list[str] | None = effective_command_names.names or None
        # The configuration's own names, recorded so a later run can tell
        # whether they changed since this install
        configured_command_names, _ = yaml_command_names(config)
        if command_names:
            config['command-names'] = command_names

        # Get primary command name (first in list) for file naming
        primary_command_name = command_names[0] if command_names else None
        additional_command_names = command_names[1:] if command_names and len(command_names) > 1 else None
        profile_name = profile_display_name(primary_command_name)
        target_config_dir, _ = resolve_artifact_base_dir(
            primary_command_name, config.get('user-settings'),
        )

        # An isolated run keeps every path that names the base config home
        # inside its own profile. The rerooter is built as soon as the
        # target directory is known, because the switch guard below
        # compares the previous run's records with the files this
        # configuration installs at their re-rooted paths; the
        # configuration itself is rewritten after the snapshot records it
        # as authored
        installed = installed_profiles(get_real_user_home())
        reroot: ConfigHomeReroot | None = None
        if primary_command_name:
            reroot = ConfigHomeReroot(
                target_config_dir,
                get_real_user_home(),
                [primary_command_name, *(profile.name for profile in installed if profile.name != 'base')],
            )

        # Hold the run back, before any write, when the environment would
        # change the names an installed profile remembers, or when a
        # different configuration would re-provision it; the switch guard
        # lists what the previous configuration leaves behind, and the run
        # removes it after consent
        guard_environment_name_change(args, effective_command_names, target_manifest, profile_name)
        guard_environment_link_change(args, link_spec, target_manifest, profile_name)
        dependents = content_dependents(home_dir, profile_name)
        if dependents and target_manifest is not None:
            recorded_link = manifest_link(target_manifest)
            recorded_dirs = [str(item) for item in cast(list[object], recorded_link['dirs'])] if recorded_link else []
            recorded_source = str(recorded_link.get('source') or LINK_SOURCE_BASE) if recorded_link else LINK_SOURCE_BASE
            recorded_identity = manifest_config_identity(target_manifest)
            links_changed = link_spec.dirs != recorded_dirs or (bool(link_spec.dirs) and link_spec.source != recorded_source)
            if links_changed or (recorded_identity is not None and recorded_identity != this_identity):
                names = ', '.join(profile.name for profile in dependents)
                error(
                    f'Profile "{profile_name}" is the link source of {names}; its links and its configuration stay '
                    'as installed until each dependent is re-pointed or unlinked:',
                )
                for line in dependents_remedy(dependents):
                    info(line)
                sys.exit(1)
        residue_to_remove: ProfileResidue | None = None
        if target_manifest is not None:
            recorded_identity = manifest_config_identity(target_manifest)
            if recorded_identity is None:
                info(
                    f'Recording {config_source} as the configuration of profile "{profile_name}": its manifest '
                    'records a configuration that cannot be resolved from this directory.',
                )
            else:
                residue = profile_residue(
                    target_manifest, target_config_dir, config,
                    isolated=bool(primary_command_name),
                    config_source=config_source,
                    base_url=config.get('base-url'),
                    claude_dir=get_real_user_home() / '.claude',
                    reroot=reroot,
                )
                if guard_configuration_switch(
                    args,
                    manifest=target_manifest,
                    profile_name=profile_name,
                    old_identity=recorded_identity,
                    new_identity=this_identity,
                    new_source=config_source,
                    residue=residue,
                ):
                    residue_to_remove = residue

        # Guard the run against a CLAUDE_CONFIG_DIR inherited from the
        # environment. Runs as soon as the target directory is known, so no
        # component picker and no elevation prompt precedes the refusal, and
        # --dry-run reports it instead of a plan it cannot execute.
        if not check_ambient_claude_config_dir(primary_command_name, target_config_dir):
            sys.exit(1)

        # What Step 3 does to the profile's links, decided before consent so
        # the summary lists every directory a conversion moves aside; a base
        # run never links
        run_timestamp = datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')
        link_plan: LinkPlan | None = None
        if primary_command_name:
            link_plan = plan_profile_links(
                target_config_dir,
                link_spec.dirs,
                link_source.directory if link_source is not None else home_dir / '.claude',
                source_name=link_spec.source,
                typed=link_spec.typed,
                timestamp=run_timestamp,
            )
            if link_plan.errors:
                for err in link_plan.errors:
                    error(err)
                sys.exit(1)
        linked_entries: frozenset[str] = frozenset(link_plan.linked_entries) if link_plan is not None else frozenset()

        picker: Callable[[list[str]], list[str] | None] | None = None
        if components_list and (sys.stdin.isatty() or _dev_tty_available()):
            picker_environment_name = str(config.get('name', config_name))

            def _run_picker(seed: list[str]) -> list[str] | None:
                return prompt_component_selection(
                    components_list, seed, picker_environment_name, config_source,
                )

            picker = _run_picker
        selection = resolve_component_selection(components_list, args, picker=picker)
        deselected = collect_deselected_items(config, selection)
        if selection.is_active:
            apply_component_selection(config, selection)
            # Post-selection recheck: deselection can strand an event or
            # status-line reference whose file a deselected component
            # claimed. Reference resolution must hold on the filtered
            # config; unused files are legitimate deselection residue
            # covered by the hook-claim asymmetry warning.
            post_selection_errors = validate_hooks_files_consistency(
                config, require_all_files_used=False,
            )
            if post_selection_errors:
                for err in post_selection_errors:
                    error(err)
                error(
                    'The selected components leave hook references dangling. '
                    'Select the component that provides the referenced file, or '
                    'update the components registry to claim the event and its '
                    'file together.',
                )
                sys.exit(1)

        # The configuration this run installs, recorded beside the manifest
        # as resolved-config.yaml; a remembered value that overrides a
        # configuration value which changed since the install is reported
        installed_config_snapshot = resolved_config_snapshot(config)
        for warn_msg in remembered_value_warnings(
            effective_command_names, selection, configured_command_names, target_manifest,
        ):
            warning(warn_msg)

        # The destinations, the dependency commands and the settings values
        # of an isolated run are rewritten here, after the snapshot recorded
        # the configuration as authored and before anything reads them (the
        # elevation reasons, the summary, the installers, the manifest
        # records and the removal plan)
        rerooted_paths = reroot.apply(config, deselected) if reroot is not None else []

        # A destination inside a linked entry belongs to the source's run,
        # which wrote it into the shared directory; this run leaves it to the
        # link. The split reads the rewritten destinations, so a base
        # config-home path re-rooted into a linked hooks/ is among the ones
        # left out, and the summary names each of them before consent
        downloads_to_process, linked_downloads = split_downloads_by_linked_entries(
            cast(list[Any], config.get('files-to-download') or []), target_config_dir, linked_entries,
        )

        # Relaunch elevated on Windows when this configuration needs admin rights
        request_admin_elevation_if_needed(config, args)

        environment_name = config.get('name', 'Development')

        base_url = config.get('base-url')  # Optional base URL override from config

        # Extract command defaults
        command_defaults = config.get('command-defaults', {})
        system_prompt = command_defaults.get('system-prompt')
        mode = command_defaults.get('mode', 'replace')  # Default to 'replace'

        # Validate mode value
        if mode not in ['append', 'replace']:
            error(f"Invalid mode value: {mode}. Must be 'append' or 'replace'")
            sys.exit(1)

        # Extract OS-level environment variables configuration
        os_env_variables = config.get('os-env-variables')

        # Extract status_line configuration (still consumed by the summary
        # printout and by download_hook_files() path selection below).
        status_line = config.get('status-line')

        # Extract user-settings configuration (raw settings.json content)
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

        # Record which managed control keys the resolved YAML itself declares
        # with a value the Step 16 unpinned sweep must keep. Computed BEFORE
        # injection so auto-injected values are excluded.
        user_declared_control_keys = _collect_user_declared_control_keys(
            user_settings, global_config=global_config,
        )

        # The machine has one Claude Code binary, so the auto-update and
        # IDE extension controls that hold it at a pinned version are
        # machine-global. Read the profile manifests once to learn whether
        # any OTHER installed profile still pins a version; while one does,
        # this run keeps the controls in place instead of removing them.
        profile_pin_scan = _other_profile_pins(
            get_real_user_home(), primary_command_name,
        )
        other_profile_pinned = profile_pin_scan.other_profile_pinned
        machine_pinned = claude_code_version_normalized is not None or other_profile_pinned
        if claude_code_version_normalized is None and other_profile_pinned:
            info(_pinned_elsewhere_message(profile_pin_scan))
        # Only an unpinned run that installs next to a pinned profile needs to
        # know what is installed, so the probe does not run a binary on any
        # other run.
        claude_install_decision = _decide_claude_install(
            claude_code_version_normalized,
            profile_pin_scan,
            installed_version=(
                _installed_claude_version()
                if claude_code_version_normalized is None and other_profile_pinned and not args.skip_install
                else None
            ),
        )

        # Apply automatic auto-update settings based on version pinning
        (
            global_config,
            user_settings,
            os_env_variables,
            auto_update_warnings,
            auto_injected_items,
        ) = apply_auto_update_settings(
            claude_code_version_normalized,
            global_config,
            user_settings,
            os_env_variables,
            other_profile_pinned=other_profile_pinned,
        )
        for warn_msg in auto_update_warnings:
            warning(warn_msg)

        # Apply automatic IDE extension auto-install settings based on version pinning
        (
            global_config,
            user_settings,
            os_env_variables,
            ide_ext_warnings,
            ide_ext_auto_injected,
        ) = apply_ide_extension_settings(
            claude_code_version_normalized,
            global_config,
            user_settings,
            os_env_variables,
            other_profile_pinned=other_profile_pinned,
        )
        for warn_msg in ide_ext_warnings:
            warning(warn_msg)
        # Merge auto-injected items from both auto-update and IDE extension management
        auto_injected_items.extend(ide_ext_auto_injected)

        # A linked skills/ directory belongs to the source profile, so the
        # claude.ai skill sync of this profile is switched off
        user_settings, skills_sync_warnings, skills_sync_auto_injected = apply_skills_sync_settings(
            user_settings, links_skills=SKILLS_PROFILE_DIR in linked_entries,
        )
        for warn_msg in skills_sync_warnings:
            warning(warn_msg)
        auto_injected_items.extend(skills_sync_auto_injected)

        # Validate user-settings section (excluded keys and known key values)
        if user_settings:
            user_settings_errors = validate_user_settings(user_settings)
            if user_settings_errors:
                for err in user_settings_errors:
                    error(err)
                sys.exit(1)
            if user_settings.get('effortLevel') == 'max':
                warning(
                    "user-settings.effortLevel 'max' may be silently ignored by "
                    'Claude Code when loading settings files. To pin the max '
                    "effort level reliably, set user-settings.env.CLAUDE_CODE_EFFORT_LEVEL to 'max'.",
                )

        # Validate global-config section (excluded keys and key placement)
        if global_config:
            global_config_errors = validate_global_config(global_config)
            if global_config_errors:
                for err in global_config_errors:
                    error(err)
                sys.exit(1)

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
        all_valid, validation_results = validate_all_config_files(
            config_without_linked_sections(config, linked_entries), config_source, args.auth, auth_cache,
        )

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
            deselected=deselected,
            config_version=config_version,
            inheritance_chain=inheritance_chain,
            args=args,
            selection=selection,
        )
        plan.auto_injected_items = auto_injected_items
        plan.command_names_origin = effective_command_names.origin
        plan.command_names_remembered = effective_command_names.remembered
        plan.link_spec = link_spec if primary_command_name else None
        plan.link_plan = link_plan
        plan.configured_link_dirs = configured_link_values['link_dirs'] if primary_command_name else None
        plan.linked_from = dependent_of.name if dependent_of is not None else None
        plan.dependents = [profile.name for profile in dependents]
        plan.linked_downloads = linked_downloads
        plan.files_to_download = [
            cast(dict[str, Any], entry) for entry in downloads_to_process if isinstance(entry, dict)
        ]
        plan.claude_code_version = claude_install_decision.version
        plan.keep_installed_claude = claude_install_decision.kept
        plan.claude_install_reason = claude_install_decision.reason
        if claude_install_decision.note_is_warning:
            plan.claude_install_warning = claude_install_decision.note
        plan.rerooted_paths = rerooted_paths

        # A pin holds or moves the one binary the other installed profiles
        # use, so the summary names them; the installed version is probed
        # only when the pin has other profiles to affect
        other_profile_names = [profile.name for profile in installed if profile.name != profile_name]
        if claude_code_version_normalized is not None:
            plan.pin_effect = pin_effect_line(
                claude_code_version_normalized,
                _installed_claude_version() if other_profile_names and not args.skip_install else None,
                other_profile_names,
            )

        # Everything a run writes outside its own profile is named before
        # consent: the machine-wide writes of an isolated run, the account
        # keys a global-config null signs out of the .claude.json this run
        # writes, the destinations outside ~/.claude a profile of another
        # configuration also installs, and the stale update controls other
        # profiles still hold (which Step 16 lists again and never edits).
        pre_consent_profile_dir = target_config_dir if primary_command_name else None
        os_level_env, _ = partition_os_env_variables(os_env_variables or {}, isolated=bool(primary_command_name))
        if primary_command_name:
            # Step 2 installs the extension only for a pinned run without
            # --skip-install; detection is read-only, so the summary can name
            # the IDEs Step 2 will write into
            step_2_runs = claude_code_version_normalized is not None and not args.skip_install
            plan.machine_wide_writes = collect_machine_wide_writes(
                profile_dir=target_config_dir,
                command_names=command_names or [],
                skip_install=args.skip_install,
                install_version=claude_install_decision.version,
                keep_installed=claude_install_decision.kept,
                pinned_version=claude_code_version_normalized,
                ide_clis=[name for name, _ in _detect_vscode_family_ides()] if step_2_runs else [],
                os_level_env=os_level_env,
                mcp_servers=plan.mcp_servers,
                files_to_download=plan.files_to_download,
                has_dependency_commands=bool(plan.dependency_commands),
                pin_effect=plan.pin_effect,
            )
        plan.destination_warnings = shared_destination_warnings(
            plan.files_to_download, config_source, base_url,
            home_dir=get_real_user_home(), this_identity=this_identity, this_profile=profile_name,
        )
        plan.account_key_warnings = account_key_deletion_warnings(
            global_config,
            global_config_target_file(pre_consent_profile_dir),
            primary_command_name or 'base',
        )
        plan.stale_controls_elsewhere = find_stale_controls_in_other_profiles(
            get_real_user_home(),
            profile_dir=pre_consent_profile_dir,
            machine_pinned=machine_pinned,
            user_declared_keys=user_declared_control_keys,
        )

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
        artifact_base_dir, uses_user_config_dir = resolve_artifact_base_dir(
            primary_command_name, user_settings,
        )
        isolated_config_dir: Path | None = artifact_base_dir if primary_command_name else None

        if uses_user_config_dir:
            info('Using user-specified CLAUDE_CONFIG_DIR for artifact isolation')
            # Remove CLAUDE_CONFIG_DIR from user-settings.env -- the launcher
            # export is the sole authoritative source. Keeping it in the
            # profile's config.json env section would create a redundant,
            # potentially stale second source.
            user_env_section = user_settings.get('env') if user_settings else None
            if isinstance(user_env_section, dict):
                user_env_section.pop('CLAUDE_CONFIG_DIR', None)

        # Export CLAUDE_CONFIG_DIR (isolated profiles only) so setup-time child
        # processes resolve against the isolated profile directory rather than
        # the default ~/.claude. Transient and process-scoped; never written to
        # config.json (the runtime launcher export is the authoritative runtime
        # source).
        export_setup_time_config_dir(primary_command_name, artifact_base_dir)

        # A profile switched to another configuration sheds what the previous
        # one left behind before the new one installs
        if residue_to_remove:
            print()
            print(f'{Colors.CYAN}Removing what the previous configuration of "{profile_name}" left behind...{Colors.NC}')
            remove_profile_residue(residue_to_remove, profile_dir=artifact_base_dir, claude_dir=claude_user_dir)

        # Derive all artifact directories from artifact_base_dir
        agents_dir = artifact_base_dir / 'agents'
        commands_dir = artifact_base_dir / 'commands'
        rules_dir = artifact_base_dir / 'rules'
        prompts_dir = artifact_base_dir / 'prompts'
        hooks_dir = artifact_base_dir / 'hooks'
        skills_dir = artifact_base_dir / 'skills'

        # Step 1: Install Claude Code if needed (MUST be first - provides uv, git bash, node)
        if not args.skip_install:
            if claude_install_decision.kept:
                print(f'{Colors.CYAN}Step 1: Keeping the installed Claude Code...{Colors.NC}')
            else:
                print(f'{Colors.CYAN}Step 1: Installing Claude Code...{Colors.NC}')
            if claude_install_decision.note:
                if claude_install_decision.note_is_warning:
                    warning(claude_install_decision.note)
                else:
                    info(claude_install_decision.note)
            if not install_claude(claude_install_decision.version, keep_installed=claude_install_decision.kept):
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

        # Step 3: Create the base configuration directory and the profile's
        # links. Every link exists before any content step, so a linked entry
        # receives nothing of its own and a failed link stops the run.
        print()
        print(f'{Colors.CYAN}Step 3: Creating base configuration directory and profile links...{Colors.NC}')
        claude_user_dir.mkdir(parents=True, exist_ok=True)
        success(f'Created: {claude_user_dir}')
        if artifact_base_dir != claude_user_dir:
            artifact_base_dir.mkdir(parents=True, exist_ok=True)
            success(f'Created: {artifact_base_dir}')
        if link_plan is not None and link_plan.actions:
            try:
                apply_link_plan(link_plan)
            except (OSError, subprocess.CalledProcessError) as e:
                raise Exception(f'Linking the profile directories failed: {e}') from e
        # Subdirectories (agents, commands, rules, prompts, hooks, skills)
        # that are not links are created on-demand by their respective
        # processing functions only when files are actually placed into them.

        # Ensure .local/bin is in PATH early to prevent uv tool warnings
        ensure_local_bin_in_path()

        # Track download, dependency and dependent failures across all steps for final error reporting
        download_failures: list[str] = []
        dependency_failures: list[str] = []
        dependent_results: list[DependentResult] = []

        # Step 4: Download/copy custom files
        print()
        print(f'{Colors.CYAN}Step 4: Processing file downloads...{Colors.NC}')
        files_to_download = downloads_to_process
        for skipped_dest, entry in linked_downloads:
            info(f'Skipping {_linked_download_line(skipped_dest, entry, link_spec.source)}')
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
        dependency_failures = install_dependencies(dependencies)

        # A dependency command may have replaced a linked entry with a real
        # directory; the profile would then diverge from its source silently
        if link_plan is not None:
            _exit_on_broken_links(verify_profile_links(artifact_base_dir, link_plan), profile_name)

        # Step 7: OS environment variables. A base run writes every entry to
        # the OS environment. An isolated run writes only the machine-wide
        # binary controls there and routes everything else to its own env
        # loader files, so the profile's variables reach its sessions and
        # nothing else on the machine. An empty dict is a no-op inside
        # set_all_os_env_variables(), which prints its own message.
        print()
        print(f'{Colors.CYAN}Step 7: Setting OS environment variables...{Colors.NC}')
        os_level_env_variables, loader_env_variables = partition_os_env_variables(
            os_env_variables or {}, isolated=bool(primary_command_name),
        )
        set_all_os_env_variables(os_level_env_variables)

        # Rebuild env loader files for the profile's OS environment variables.
        # Loader files are toolbox-owned and rebuilt even when every entry is
        # a deletion, so stale exports from a prior run are cleared instead
        # of reaching the sessions launch.sh starts.
        generated_env_files: dict[str, Path] = generate_env_loader_files(
            loader_env_variables, command_names, artifact_base_dir if command_names else None,
        )
        if generated_env_files:
            success(f'Generated {len(generated_env_files)} env loader file(s)')

        # Step 8: Process agents
        print()
        print(f'{Colors.CYAN}Step 8: Processing agents...{Colors.NC}')
        agents = config.get('agents', [])
        if 'agents' in linked_entries:
            info(f'Agents are linked from profile "{link_spec.source}"; nothing to install')
        elif agents:
            if not process_resources(agents, agents_dir, 'agents', config_source, base_url, args.auth, auth_cache):
                download_failures.append('agents')
        else:
            info('No agents to process')

        # Step 9: Process slash commands
        print()
        print(f'{Colors.CYAN}Step 9: Processing slash commands...{Colors.NC}')
        commands = config.get('slash-commands', [])
        if 'commands' in linked_entries:
            info(f'Slash commands are linked from profile "{link_spec.source}"; nothing to install')
        elif commands:
            if not process_resources(commands, commands_dir, 'slash commands', config_source, base_url, args.auth, auth_cache):
                download_failures.append('slash commands')
        else:
            info('No slash commands to process')

        # Step 10: Process rules
        print()
        print(f'{Colors.CYAN}Step 10: Processing rules...{Colors.NC}')
        rules = config.get('rules', [])
        if 'rules' in linked_entries:
            info(f'Rules are linked from profile "{link_spec.source}"; nothing to install')
        elif rules:
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
        if 'skills' in linked_entries:
            info(f'Skills are linked from profile "{link_spec.source}"; nothing to install')
        elif skills:
            if not process_skills(skills, skills_dir, config_source, args.auth, auth_cache):
                download_failures.append('skills')
        else:
            info('No skills configured')

        # Step 12: Process system prompt (if specified)
        print()
        print(f'{Colors.CYAN}Step 12: Processing system prompt...{Colors.NC}')
        prompt_path = None
        if system_prompt and 'prompts' in linked_entries:
            info(f'The system prompt is linked from profile "{link_spec.source}"; nothing to install')
        elif system_prompt:
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
            command_names=command_names if primary_command_name else None,
        )
        has_profile_mcp_servers = len(profile_servers) > 0

        # Step 14: Write user settings (non-isolated mode only). In isolated
        # mode, the user-settings section is built into the profile's
        # config.json at Step 18: the launcher passes config.json via
        # --settings (command-line settings layer), so the profile's settings
        # outrank a repository's project settings, matching the enforcement
        # an isolated environment exists to provide.
        print()
        print(f'{Colors.CYAN}Step 14: Writing user settings...{Colors.NC}')
        if not user_settings:
            info('No user settings to configure')
        elif primary_command_name:
            info('Isolated mode: user settings are built into config.json in Step 18')
        elif write_user_settings(user_settings, claude_user_dir):
            success('User settings configured successfully')
        else:
            warning('Failed to write user settings (non-fatal)')

        # Step 15: Write global config
        print()
        print(f'{Colors.CYAN}Step 15: Writing global config...{Colors.NC}')
        global_config = _propagate_install_method(
            global_config, primary_command_name, auto_injected_items,
        )
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

        # Step 16: Cleanup stale auto-update and IDE extension controls in
        # this profile's own files; stale copies in other profiles are
        # listed and left alone.
        stale_controls_elsewhere = _run_stale_controls_cleanup(
            machine_pinned=machine_pinned,
            user_declared_keys=user_declared_control_keys,
            profile_dir=isolated_config_dir,
        )

        # What this run wrote and chose, as Step 19 records it: a later
        # re-run reads the names and the component delta, and the switch
        # guard reads the written records to list the residue
        manifest_records: dict[str, Any] = {
            'resolved_config': installed_config_snapshot,
            'origins': {
                'command_names': effective_command_names.origin,
                'components': selection.origin if selection.is_active else 'yaml',
            },
            'components': selection.delta if selection.is_active else None,
            'yaml_values': {
                'command_names': configured_command_names,
                'components': selection.defaults if selection.is_active else [],
                **configured_link_values,
            },
            'link': link_spec.record() if primary_command_name else None,
            'machine_wide_destinations': machine_wide_download_records(
                [cast(dict[str, Any], f) for f in cast(list[object], files_to_download or []) if isinstance(f, dict)],
                config_source, base_url, claude_user_dir,
            ),
            'os_env_written': [key for key, value in os_level_env_variables.items() if value is not None],
            'settings_keys_written': written_settings_keys(user_settings, status_line, config.get('hooks')),
            'mcp_servers': mcp_server_records(mcp_servers),
            'files_written': planned_profile_files(config, artifact_base_dir, linked_entries=linked_entries),
        }
        config_source_type = classify_config_source(config_source)
        config_source_url = resolve_config_source_url(config_source, config_source_type)

        # Check if command creation is needed
        if primary_command_name:
            # Step 17: Download hooks
            print()
            print(f'{Colors.CYAN}Step 17: Downloading hooks...{Colors.NC}')
            hooks = config.get('hooks', {})
            hooks_base_dir_arg = hooks_dir if isolated_config_dir else None
            if 'hooks' in linked_entries:
                info(f'Hook files are linked from profile "{link_spec.source}"; nothing to install')
            elif not download_hook_files(hooks, claude_user_dir, config_source, base_url, args.auth,
                                         hooks_base_dir=hooks_base_dir_arg, auth_cache=auth_cache):
                download_failures.append('hook files')

            # Step 18: Create profile configuration. config.json wires hook
            # files by path, so a linked hooks/ must already hold every file
            # the events and the status line name.
            print()
            print(f'{Colors.CYAN}Step 18: Creating profile configuration...{Colors.NC}')
            if 'hooks' in linked_entries:
                missing_hook_files = missing_wired_hook_files(config, hooks_dir)
                if missing_hook_files:
                    error(f'Profile "{profile_name}" wires hook files that profile "{link_spec.source}" does not hold:')
                    for missing in missing_hook_files:
                        error(f'  - {missing}')
                    info(f'Re-run the source first: --profile {link_spec.source}')
                    sys.exit(1)

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
                user_settings=user_settings,
            )

            # Step 19: Write installation manifest
            print()
            print(f'{Colors.CYAN}Step 19: Writing installation manifest...{Colors.NC}')
            write_manifest(
                config_base_dir=artifact_base_dir,
                command_name=primary_command_name,
                config_version=config_version,
                config_source=config_source,
                config_source_type=config_source_type,
                config_source_url=config_source_url,
                command_names=command_names or [primary_command_name],
                claude_code_version=claude_code_version_normalized,
                **manifest_records,
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

            # Step 21: Register global command(s); the wrappers of aliases the
            # profile's previous manifest listed and this run drops go first
            if launcher_result:
                main_launcher, launch_script = launcher_result
                print()
                if additional_command_names:
                    all_names = ', '.join(command_names) if command_names else primary_command_name
                    print(f'{Colors.CYAN}Step 21: Registering global commands: {all_names}...{Colors.NC}')
                else:
                    print(f'{Colors.CYAN}Step 21: Registering global {primary_command_name} command...{Colors.NC}')
                previous_names = [
                    str(item)
                    for item in cast(list[object], (target_manifest or {}).get('command_names') or [])
                ]
                remove_dropped_command_wrappers(
                    previous_names, command_names or [primary_command_name], get_real_user_home(),
                )
                register_global_command(
                    main_launcher, primary_command_name, additional_command_names,
                    launch_script_path=launch_script,
                )
            else:
                warning('Launcher script was not created')

            # Step 22: Remove previously installed artifacts of deselected
            # components (the removal plan derives from the unfiltered
            # config, so no on-disk state is needed); a linked entry belongs
            # to another profile and is left alone
            if has_deselected_items(deselected):
                print()
                print(f'{Colors.CYAN}Step 22: Removing deselected components...{Colors.NC}')
                execute_deselection_cleanup(
                    deselected,
                    config,
                    agents_dir=agents_dir,
                    commands_dir=commands_dir,
                    rules_dir=rules_dir,
                    skills_dir=skills_dir,
                    hooks_dir=hooks_dir,
                    is_isolated=True,
                    linked_entries=linked_entries,
                )

            # Every linked entry must still be a link when the run ends
            if link_plan is not None:
                _exit_on_broken_links(verify_profile_links(artifact_base_dir, link_plan), profile_name)

            # Step 23: Refresh the profiles that link content from this one
            dependent_results = run_dependent_refresh_step(
                dependents, source_name=profile_name, child_run=args.child_run,
            )
        else:
            # No command-names: route the profile-owned YAML keys
            # (status-line, hooks) to the shared ~/.claude/settings.json via
            # deep-merge with RFC 7396 null-as-delete. The user-settings
            # section reaches the same file through Step 14
            # write_user_settings(), so both modes deliver the full
            # settings.json content.
            hooks = config.get('hooks', {})

            # Step 17: Download hook scripts, helper modules, and the
            # status-line file + config to ~/.claude/hooks/. The status-line
            # file and its config must be listed in hooks.files per the
            # EnvironmentConfig schema Rule 3, so download_hook_files()
            # handles every source automatically.
            has_hook_events = bool(hooks and hooks.get('events'))
            has_status_line_file = bool(
                status_line
                and isinstance(status_line, dict)
                and status_line.get('file'),
            )
            has_hook_downloads = bool(
                isinstance(hooks, dict) and (hooks.get('files') or hooks.get('helpers')),
            )

            if has_hook_events or has_status_line_file or has_hook_downloads:
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

            # Step 19: Write the base profile's installation manifest. Every
            # toolbox-managed profile records its own Claude Code version
            # pin, so a later run of any profile can tell whether the
            # machine-global auto-update controls are still needed.
            print()
            print(f'{Colors.CYAN}Step 19: Writing installation manifest...{Colors.NC}')
            write_manifest(
                config_base_dir=claude_user_dir,
                command_name=None,
                config_version=config_version,
                config_source=config_source,
                config_source_type=config_source_type,
                config_source_url=config_source_url,
                command_names=[],
                claude_code_version=claude_code_version_normalized,
                **manifest_records,
            )

            # Steps 20-21: Skip command creation
            print()
            print(f'{Colors.CYAN}Steps 20-21: Skipping command creation (no command-names specified)...{Colors.NC}')

            # Step 22: Remove previously installed artifacts of deselected
            # components (the removal plan derives from the unfiltered
            # config, so no on-disk state is needed). Runs after the Step 18
            # settings merge so the union-written file is reconciled last.
            if has_deselected_items(deselected):
                print()
                print(f'{Colors.CYAN}Step 22: Removing deselected components...{Colors.NC}')
                execute_deselection_cleanup(
                    deselected,
                    config,
                    agents_dir=agents_dir,
                    commands_dir=commands_dir,
                    rules_dir=rules_dir,
                    skills_dir=skills_dir,
                    hooks_dir=hooks_dir,
                    is_isolated=False,
                )

            # Step 23: Refresh the profiles that link content from the base profile
            dependent_results = run_dependent_refresh_step(
                dependents, source_name=profile_name, child_run=args.child_run,
            )
            info('Environment configuration completed successfully')
            info('To create custom commands, add "command-names: [name1, name2]" to your config')

        # Check for download, dependency and dependent failures and report accordingly
        dependent_failures = [result for result in dependent_results if result.code != 0]
        if download_failures or dependency_failures or dependent_failures:
            print()
            print(f'{Colors.RED}========================================================================{Colors.NC}')
            print(f'{Colors.RED}              Setup Completed with Errors{Colors.NC}')
            print(f'{Colors.RED}========================================================================{Colors.NC}')
            print()
            if download_failures:
                error('The following resources failed to download:')
                for failure in download_failures:
                    error(f'  - {failure}')
                print()
                error('Some files are missing.')
                error('Please check your network connection and authentication, then re-run the setup.')
                print()
            if dependency_failures:
                error('The following dependencies failed to install:')
                for failure in dependency_failures:
                    error(f'  - {failure}')
                print()
                error('Review the dependency error messages above, then re-run the setup.')
                print()
            if dependent_failures:
                error('The following dependent profiles failed to refresh:')
                for result in dependent_failures:
                    error(f'  - {result.line()}')
                print()
                error('Review the output of each failed dependent above, then retry it with its --profile command.')
                print()
            error('Configuration steps were completed, but some components are missing.')
            print()

            # A UAC relaunch runs in a window that closes on exit: hold it so the user can see the error
            if was_elevated_via_uac:
                _hold_elevated_window('Setup Completed with Errors', Colors.RED)
                elevated_window_held = True

            sys.exit(1)

        # Final message - success (no download or dependency failures)
        print()
        print(f'{Colors.GREEN}========================================================================{Colors.NC}')
        print(f'{Colors.GREEN}                    Setup Complete!{Colors.NC}')
        print(f'{Colors.GREEN}========================================================================{Colors.NC}')
        print()

        print(f'{Colors.YELLOW}Summary:{Colors.NC}')
        print(f'   * Environment: {environment_name}')
        if args.skip_install:
            claude_install_status = 'Skipped'
        elif claude_install_decision.kept:
            claude_install_status = (
                f'Kept at {claude_install_decision.version} ({claude_install_decision.reason})'
            )
        else:
            claude_install_status = 'Completed'
        print(f'   * Claude Code installation: {claude_install_status}')
        print(f'   * Agents: {len(agents)} installed')
        print(f'   * Slash commands: {len(commands)} installed')
        print(f'   * Rules: {len(rules)} installed')
        print(f'   * Skills: {len(skills)} installed')
        if files_to_download:
            print(f'   * Files downloaded: {len(files_to_download)} processed')
        if system_prompt:
            print(f'   * {system_prompt_completion_line(mode, isolated=bool(command_names))}')
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
        if mcp_stats['unchanged_count'] > 0:
            print(f"   * MCP servers unchanged (skipped, tokens preserved): {mcp_stats['unchanged_count']}")
        if mcp_stats['strict_hidden_count'] > 0:
            print('   * MCP servers not loaded in isolated sessions '
                  f"(--strict-mcp-config): {mcp_stats['strict_hidden_count']}")
        if status_line and isinstance(status_line, dict):
            status_line_dict = cast(dict[str, Any], status_line)
            status_line_file_val = status_line_dict.get('file', '')
            if status_line_file_val and isinstance(status_line_file_val, str):
                if '?' in status_line_file_val:
                    clean_name = Path(status_line_file_val.split('?')[0]).name
                else:
                    clean_name = Path(status_line_file_val).name
                print(f'   * Status line: {clean_name}')
        if os_level_env_variables:
            set_vars = sum(1 for v in os_level_env_variables.values() if v is not None)
            del_vars = sum(1 for v in os_level_env_variables.values() if v is None)
            scope_label = ' (machine-wide)' if primary_command_name else ''
            if set_vars > 0:
                print(f'   * OS environment variables: {set_vars} configured{scope_label}')
            if del_vars > 0:
                print(f'   * OS environment variables: {del_vars} deleted{scope_label}')
        if loader_env_variables:
            set_vars = sum(1 for v in loader_env_variables.values() if v is not None)
            del_vars = sum(1 for v in loader_env_variables.values() if v is None)
            if set_vars > 0:
                print(f'   * Profile environment variables: {set_vars} exported by the env loaders')
            if del_vars > 0:
                print(f'   * Profile environment variables: {del_vars} unset by the env loaders')
        if user_settings:
            if isolated_config_dir is not None:
                print(f'   * User settings: built into {isolated_config_dir / "config.json"}')
            else:
                print('   * User settings: configured in ~/.claude/settings.json')
        if global_config:
            print(f'   * Global config: configured in {global_config_target_file(isolated_config_dir)}')
        if link_plan is not None and link_plan.linked_entries:
            links_marker = origin_marker(link_spec.dirs_origin, remembered=link_spec.dirs_remembered)
            print(
                f'   * Links: {", ".join(link_plan.linked_entries)} from profile "{link_spec.source}"{links_marker}',
            )
        if stale_controls_elsewhere:
            print('   * Stale update controls left in other profiles (re-run each with --profile to remove them):')
            for copy in stale_controls_elsewhere:
                print(f'       - {_stale_control_copy_line(copy)}')
        if dependent_results:
            print('   * Dependent profiles refreshed from this run:')
            for result in dependent_results:
                print(f'       - {result.line()}')
        # A child run lists nothing here: the report of the run that started
        # it (--profile all, or the source whose Step 23 refreshes this
        # dependent) covers every installed profile
        unrefreshed = [] if args.child_run else unrefreshed_profile_lines(
            get_real_user_home(), profile_name, frozenset(result.name for result in dependent_results),
        )
        if unrefreshed:
            print('   * Installed profiles this run did not refresh:')
            for line in unrefreshed:
                print(f'       - {line}')
        if claude_code_version_normalized is not None:
            print(f'   * IDE extensions: {IDE_EXTENSION_ID} v{claude_code_version_normalized} (auto-install disabled)')
        # Show hooks count with routing information
        hooks = config.get('hooks', {})
        hook_event_count = len(hooks.get('events', [])) if hooks else 0
        # Under --yes nobody reads the installation summary before the run,
        # so the closing lines name where the command names came from too
        names_marker = origin_marker(
            effective_command_names.origin, remembered=effective_command_names.remembered,
        )
        if command_names:
            print(f'   * Hooks: {hook_event_count} configured (in config.json)')
            if len(command_names) > 1:
                print(f'   * Global commands: {", ".join(command_names)} registered{names_marker}')
            else:
                print(f'   * Global command: {primary_command_name} registered{names_marker}')
        else:
            if hook_event_count > 0:
                print(f'   * Hooks: {hook_event_count} configured (in settings.json)')
            print('   * Custom command: Not created (no command-names specified)')

        print()
        print(f'{Colors.YELLOW}Quick Start:{Colors.NC}')
        if command_names:
            if len(command_names) > 1:
                print(f'   * Global commands: {", ".join(command_names)}{names_marker}')
            else:
                print(f'   * Global command: {primary_command_name}{names_marker}')
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

        # A UAC relaunch runs in a window that closes on exit: hold it so the user can see the results
        if was_elevated_via_uac:
            _hold_elevated_window(
                'Setup Completed Successfully!',
                Colors.GREEN,
                (
                    'The environment has been configured successfully.',
                    'You can now close this window and use the configured environment.',
                ),
            )

    except SystemExit as exit_request:
        # A UAC relaunch runs in a window that closes on exit: a failed exit that no step held yet
        # (a validation error, a refused guard) is held here so the user can read its error
        if was_elevated_via_uac and not elevated_window_held and exit_request.code not in (None, 0):
            _hold_elevated_window('Setup Failed', Colors.RED)
        raise

    except Exception as e:
        print()
        error(str(e))
        print()
        print(f'{Colors.RED}Setup failed. Please check the error above.{Colors.NC}')
        print(f'{Colors.YELLOW}For help, visit: https://github.com/alex-feel/claude-code-toolbox{Colors.NC}')
        print()

        # A UAC relaunch runs in a window that closes on exit: hold it so the user can see the error
        if was_elevated_via_uac:
            _hold_elevated_window('Setup Failed', Colors.RED)

        sys.exit(1)


if __name__ == '__main__':
    main()
