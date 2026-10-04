"""Support for the real-binary E2E tests of linked profile entries.

A linked profile entry is a directory under CLAUDE_CONFIG_DIR (skills,
agents, commands, rules, hooks, output-styles, prompts, projects) that is a
directory link -- a symlink on Unix, a junction or a symlink on Windows --
to the same directory of another profile. The tests drive the real Claude
Code binary against such a layout without network access and without any
real user state; this module holds what they share:

- write_source_entries(): one sentinel per linkable entry in a source
  profile, so every assertion is discriminating (absent entry, absent
  sentinel); the hooks entry carries what an installed hooks/ holds
  beside the script: a helper module the script imports, a
  project-overrides/ file it reads, and a uv script lockfile that
  lock_hook_script() creates and make_hook_lock_stale() invalidates;
- place_entry(): copies or links an entry into a profile with the same
  primitives the toolbox uses (os.symlink with target_is_directory, and
  _winapi.CreateJunction on Windows);
- claude_child_env() and run_stream_json(): the isolated child environment
  and the stream-json parser for `claude -p` and for the toolbox launcher.

The fake Messages API lives in fake_anthropic_api and the profile layouts
in linked_entries_workspace.
"""

from __future__ import annotations

import functools
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any

import pytest

from scripts import setup_environment
from tests.e2e.fake_anthropic_api import FakeAnthropicServer
from tests.e2e.shells import LOGIN_SHELL_INHERITED_PATH

LINKABLE_ENTRIES: tuple[str, ...] = (
    'skills', 'agents', 'commands', 'rules', 'hooks', 'output-styles', 'prompts', 'projects',
)

# One sentinel per content entry; projects carries no file content of its own
# (its proof is the session file the binary writes) and hooks prove themselves
# through the marker file the hook script writes.
SENTINELS: dict[str, str] = {
    'skills': 'ZQX-SKILL-7f3a9c',
    'agents': 'ZQX-AGENT-4b8d2e',
    'commands': 'ZQX-CMD-9e1c5a',
    'rules': 'ZQX-RULE-2d7f8b',
    'output-styles': 'ZQX-STYLE-6a4e3c',
    'prompts': 'ZQX-PROMPT-1b2c3d',
}

SKILL_NAME = 'sentinel-skill'
AGENT_NAME = 'sentinel-agent'
COMMAND_NAME = 'sentinel-cmd'
STYLE_NAME = 'sentinel-style'
PROMPT_FILE = 'sentinel-prompt.md'
HOOK_SCRIPT = 'sentinel_hook.py'
HOOK_CONFIG = 'sentinel_hook.json'
# The files an installed hooks/ holds beside a script: the helper module the
# script imports from its own directory, the uv script lockfile uv reads
# beside the script, and the project-overrides/ file the script reads
# relative to its own directory
HOOK_HELPER = 'sentinel_hook_helper.py'
HOOK_LOCKFILE = f'{HOOK_SCRIPT}.lock'
HOOK_OVERRIDES_DIR = 'project-overrides'
HOOK_OVERRIDE_FILE = 'sentinel.json'
HELPER_SENTINEL = 'ZQX-HELPER-3e9a1b'
OVERRIDE_SENTINEL = 'ZQX-OVERRIDE-5c2d8e'
HOOK_REQUIRES_PYTHON = '>=3.12'
# A requires-python the lockfile does not record: a locked run refuses it
HOOK_STALE_REQUIRES_PYTHON = '>=3.11'

FAKE_API_KEY = 'sk-ant-api03-fake-key-for-e2e-0000000000000000000000'

_found_claude = setup_environment.find_command('claude')
CLAUDE_CMD: Path | None = Path(_found_claude) if _found_claude else None

# Windows: creating a directory symlink needs SeCreateSymbolicLinkPrivilege
# (administrator) or Developer Mode; without either the OS refuses with 1314
_WINERROR_PRIVILEGE_NOT_HELD = 1314
_SYMLINK_SKIP_REASON = (
    'directory symlinks need administrator rights or Developer Mode on this Windows machine '
    f'(WinError {_WINERROR_PRIVILEGE_NOT_HELD})'
)

# Variables the child must never inherit from the developer's session: the
# toolbox's own switches, API routing and credentials, and update controls
_STRIPPED_ENV_PREFIXES = ('CLAUDE_', 'ANTHROPIC_', 'DISABLE_')
# The one CLAUDE_ variable kept: Claude Code uses it to find Git Bash on Windows
_KEPT_ENV_VARIABLES = ('CLAUDE_CODE_GIT_BASH_PATH',)
# Variables dropped by name: the PATH an outer Git Bash login shell recorded,
# which the login shell a Windows entry point starts would restore
_STRIPPED_ENV_VARIABLES = (LOGIN_SHELL_INHERITED_PATH,)

# What Claude Code reads from a directory above the working directory: its
# .claude directory (project settings in the working directory itself, memory
# and rules from every ancestor), its memory files, and its .mcp.json
CONFIG_HOME_MARKERS: tuple[str, ...] = ('.claude', 'CLAUDE.md', 'CLAUDE.local.md', '.mcp.json')


def config_home_above(path: Path) -> Path | None:
    """Return the nearest directory at or above ``path`` that holds a config home or memory file.

    Args:
        path: The directory to start from.

    Returns:
        The directory holding one of CONFIG_HOME_MARKERS, or None when none
        of ``path`` and its ancestors does.
    """
    for directory in (path, *path.parents):
        if any((directory / marker).exists() for marker in CONFIG_HOME_MARKERS):
            return directory
    return None


def workspace_root(tmp_path: Path) -> tuple[Path, Callable[[], None]]:
    """Return a directory with no config home above it, and the cleanup that removes it.

    The real binary discovers settings and memory exactly as a user's session
    does: from the working directory's .claude and from the .claude, memory
    files and .mcp.json of every directory above it. pytest's tmp_path lies
    below the system temp directory, which on Windows lies below the user's
    home, so a developer's real ~/.claude would contribute to every run made
    there. The workspace therefore stays in tmp_path when nothing above it
    holds such a file, and otherwise moves to a fresh directory under the
    first clean, writable candidate: the system temp directory, then the
    root of the drive tmp_path is on.

    Args:
        tmp_path: The test's temporary directory.

    Returns:
        The root directory, and a callable that removes it when it was
        created here (a no-op for tmp_path itself).
    """
    polluted = config_home_above(tmp_path)
    if polluted is None:
        return tmp_path, lambda: None
    for candidate in (Path(tempfile.gettempdir()), Path(tmp_path.anchor)):
        if config_home_above(candidate) is not None:
            continue
        root = candidate / f'cct-e2e-{uuid.uuid4().hex[:12]}'
        try:
            root.mkdir()
        except OSError:
            continue
        return root, functools.partial(shutil.rmtree, root, ignore_errors=True)
    pytest.skip(f'no writable directory without a Claude Code config home above it ({polluted} holds one)')


def link_kinds() -> list[str]:
    """Return the link kinds the current platform can be proven on.

    'real' is the positive control (a copied directory); 'symlink' exists on
    every platform; 'junction' is Windows-only and is the primitive the
    toolbox creates without elevation.

    Returns:
        The kinds in the order the tests report them.
    """
    if sys.platform == 'win32':
        return ['real', 'symlink', 'junction']
    return ['real', 'symlink']


def link_only_kinds() -> list[str]:
    """Return link_kinds() without the 'real' positive control."""
    return [kind for kind in link_kinds() if kind != 'real']


def write_source_entries(source: Path, hook_marker: Path) -> None:
    """Populate every linkable entry of a source profile with one sentinel.

    The hook script carries a PEP 723 header (so uv reads the lockfile
    lock_hook_script() writes beside it), imports HOOK_HELPER from its own
    directory and reads HOOK_OVERRIDE_FILE under HOOK_OVERRIDES_DIR next to
    itself. It appends one JSON line per invocation to ``hook_marker`` (a
    path outside every linked directory) carrying the event name, its own
    ``__file__``, the real path of that file, the helper and override
    sentinels and ``sys.path[0]``, so a run through a link shows the profile
    path in ``file``, the source path in ``realpath``, and in ``sys_path0``
    the directory CPython put first on the module search path: the profile
    path on Windows, the source path on POSIX, where CPython canonicalizes
    the script path before taking its directory.

    Args:
        source: The profile directory that holds the entries for real.
        hook_marker: File the hook script appends to.
    """
    skill_dir = source / 'skills' / SKILL_NAME
    skill_dir.mkdir(parents=True)
    (skill_dir / 'SKILL.md').write_text(
        f'---\nname: {SKILL_NAME}\ndescription: Sentinel skill {SENTINELS["skills"]}\n---\n'
        '# Sentinel skill\n\nThe body is never sent unless the skill is invoked.\n',
        encoding='utf-8',
    )
    (source / 'agents').mkdir()
    (source / 'agents' / f'{AGENT_NAME}.md').write_text(
        f'---\nname: {AGENT_NAME}\ndescription: Sentinel agent {SENTINELS["agents"]}\n---\n'
        'You are the sentinel agent.\n',
        encoding='utf-8',
    )
    (source / 'commands').mkdir()
    # The description is deliberately sentinel-free: the body sentinel reaches
    # a request only when the command is invoked, never from the command list
    (source / 'commands' / f'{COMMAND_NAME}.md').write_text(
        '---\ndescription: Sentinel slash command of the linked-entries E2E\n---\n'
        f'Sentinel command body {SENTINELS["commands"]}\n',
        encoding='utf-8',
    )
    (source / 'rules').mkdir()
    (source / 'rules' / 'sentinel-rule.md').write_text(
        f'# Sentinel rule\n\nAlways obey {SENTINELS["rules"]}.\n', encoding='utf-8',
    )
    (source / 'output-styles').mkdir()
    (source / 'output-styles' / f'{STYLE_NAME}.md').write_text(
        f'---\nname: {STYLE_NAME}\ndescription: Sentinel output style\n---\n'
        f'Sentinel style body {SENTINELS["output-styles"]}\n',
        encoding='utf-8',
    )
    (source / 'prompts').mkdir()
    (source / 'prompts' / PROMPT_FILE).write_text(
        f'Sentinel system prompt {SENTINELS["prompts"]}\n', encoding='utf-8',
    )
    (source / 'projects').mkdir()
    hooks_dir = source / 'hooks'
    hooks_dir.mkdir()
    (hooks_dir / HOOK_SCRIPT).write_text(
        '# /// script\n'
        f'# requires-python = "{HOOK_REQUIRES_PYTHON}"\n'
        '# dependencies = []\n'
        '# ///\n'
        'import json\n'
        'import os\n'
        'import sys\n'
        'from pathlib import Path\n'
        '\n'
        'import sentinel_hook_helper\n'
        '\n'
        'with open(sys.argv[1], encoding="utf-8") as config_file:\n'
        '    config = json.load(config_file)\n'
        f'override_path = Path(__file__).parent / "{HOOK_OVERRIDES_DIR}" / "{HOOK_OVERRIDE_FILE}"\n'
        'override = json.loads(override_path.read_text(encoding="utf-8"))\n'
        'payload = json.load(sys.stdin)\n'
        'record = {\n'
        '    "event": payload.get("hook_event_name"),\n'
        '    "file": __file__,\n'
        '    "realpath": os.path.realpath(__file__),\n'
        '    "helper": sentinel_hook_helper.HELPER_SENTINEL,\n'
        '    "override": override["override"],\n'
        '    "sys_path0": sys.path[0],\n'
        '}\n'
        'with open(config["marker"], "a", encoding="utf-8") as marker:\n'
        '    marker.write(json.dumps(record) + "\\n")\n',
        encoding='utf-8',
    )
    (hooks_dir / HOOK_HELPER).write_text(f'HELPER_SENTINEL = "{HELPER_SENTINEL}"\n', encoding='utf-8')
    (hooks_dir / HOOK_OVERRIDES_DIR).mkdir()
    (hooks_dir / HOOK_OVERRIDES_DIR / HOOK_OVERRIDE_FILE).write_text(
        json.dumps({'override': OVERRIDE_SENTINEL}), encoding='utf-8',
    )
    (hooks_dir / HOOK_CONFIG).write_text(
        json.dumps({'marker': str(hook_marker)}), encoding='utf-8',
    )


def lock_hook_script(source: Path, env: dict[str, str]) -> Path:
    """Write the uv script lockfile beside the sentinel hook script.

    Runs ``uv lock --script`` the way a configuration author locks a hook
    before shipping it; the script declares no dependencies, so the lock
    resolves offline. Claude Code then runs the hook under UV_LOCKED=1
    (see claude_child_env()), which makes uv refuse a lockfile that no
    longer matches the script instead of re-resolving.

    Args:
        source: The profile directory that holds hooks/ for real.
        env: The environment of the uv process (an isolated home).

    Returns:
        The lockfile path.

    Raises:
        RuntimeError: When uv is not installed or the lock fails.
    """
    uv = shutil.which('uv')
    if uv is None:
        raise RuntimeError('uv is required to lock the sentinel hook script')
    script = source / 'hooks' / HOOK_SCRIPT
    completed = subprocess.run(
        [uv, 'lock', '--script', str(script)], cwd=source, env=env, capture_output=True, encoding='utf-8',
        errors='replace', check=False, timeout=120,
    )
    if completed.returncode != 0:
        raise RuntimeError(f'uv lock --script failed ({completed.returncode}): {completed.stdout}{completed.stderr}')
    return source / 'hooks' / HOOK_LOCKFILE


def make_hook_lock_stale(source: Path) -> None:
    """Change the script's requires-python so the lockfile beside it no longer matches.

    A locked run (UV_LOCKED=1) then fails with uv's "needs to be updated"
    error instead of running the hook (exit code 2 before uv 0.12.14, 1 from
    0.12.14 on); a lockfile uv cannot find at all only produces a warning
    and the script runs, so that error proves the lockfile was read beside
    the script.

    Args:
        source: The profile directory that holds hooks/ for real.
    """
    script = source / 'hooks' / HOOK_SCRIPT
    content = script.read_text(encoding='utf-8')
    stale = content.replace(
        f'# requires-python = "{HOOK_REQUIRES_PYTHON}"', f'# requires-python = "{HOOK_STALE_REQUIRES_PYTHON}"',
    )
    assert stale != content, 'the sentinel hook script must declare HOOK_REQUIRES_PYTHON'
    script.write_text(stale, encoding='utf-8')


def place_entry(source: Path, profile: Path, entry: str, kind: str) -> None:
    """Put one entry into a profile as a copy, a link, or nothing.

    'symlink' uses os.symlink(target_is_directory=True) and 'junction' uses
    _winapi.CreateJunction, the two primitives link_profile_directory()
    creates links with. A Windows symlink the OS refuses (no privilege, no
    Developer Mode) skips the calling test with the reason.

    Args:
        source: Profile that holds the entry for real.
        profile: Profile receiving the entry.
        entry: One of LINKABLE_ENTRIES.
        kind: 'real', 'symlink', 'junction' or 'absent'.

    Raises:
        ValueError: When ``kind`` is none of the four.
        OSError: When the link cannot be created for a reason other than a
            missing Windows symlink privilege.
    """
    target = source / entry
    link = profile / entry
    if kind == 'absent':
        return
    if kind == 'real':
        shutil.copytree(target, link)
        return
    if kind == 'symlink':
        try:
            os.symlink(target, link, target_is_directory=True)
        except OSError as error:
            if sys.platform == 'win32' and getattr(error, 'winerror', None) == _WINERROR_PRIVILEGE_NOT_HELD:
                pytest.skip(_SYMLINK_SKIP_REASON)
            raise
        return
    if kind == 'junction':
        if sys.platform != 'win32':
            pytest.skip('junctions exist on Windows only')
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
        return
    raise ValueError(f'unknown link kind: {kind!r}')


def available_link_kinds(probe_dir: Path) -> list[str]:
    """Return link_kinds() minus the kinds this process cannot create.

    Probes a symlink inside ``probe_dir`` once, because a Windows process
    without the symlink privilege or Developer Mode cannot create one; the
    per-kind tests skip that variant with the reason, and a test covering
    every kind at once drops it instead of skipping entirely.

    Args:
        probe_dir: A writable directory for the probe link.

    Returns:
        The kinds that can be created here, in link_kinds() order.

    Raises:
        OSError: When the probe fails for a reason other than a missing
            symlink privilege.
    """
    kinds = link_kinds()
    if sys.platform != 'win32':
        return kinds
    target = probe_dir / 'symlink-probe-target'
    target.mkdir(exist_ok=True)
    probe = probe_dir / 'symlink-probe'
    try:
        os.symlink(target, probe, target_is_directory=True)
    except OSError as error:
        if getattr(error, 'winerror', None) == _WINERROR_PRIVILEGE_NOT_HELD:
            return [kind for kind in kinds if kind != 'symlink']
        raise
    os.rmdir(probe)
    return kinds


def entry_is_link_to(link: Path, target: Path) -> bool:
    """Return True when ``link`` is a directory link resolving to ``target``.

    Reparse-aware on Windows (a junction reports is_symlink() == False), a
    plain symlink check elsewhere; a real directory is never a link even when
    its content equals the target's.

    Args:
        link: The path expected to be a link.
        target: The directory the link should resolve to.

    Returns:
        True for a symlink or junction resolving to ``target``.
    """
    is_link = (
        setup_environment._is_windows_reparse_point(link) if sys.platform == 'win32' else link.is_symlink()
    )
    if not is_link:
        return False
    try:
        return link.resolve() == target.resolve()
    except OSError:
        return False


@functools.cache
def _uv_directories() -> dict[str, str]:
    """Return the real uv Python and cache directories, keyed by variable name.

    The hook command the toolbox builds runs scripts through
    ``uv run --no-project --python 3.12``; with HOME redirected to an empty
    temporary directory uv would otherwise lose sight of its managed
    interpreters and download one.

    Returns:
        UV_PYTHON_INSTALL_DIR and UV_CACHE_DIR values, or an empty mapping
        when uv is not installed.
    """
    uv = shutil.which('uv')
    if uv is None:
        return {}
    directories: dict[str, str] = {}
    for variable, args in (('UV_PYTHON_INSTALL_DIR', ['python', 'dir']), ('UV_CACHE_DIR', ['cache', 'dir'])):
        result = subprocess.run([uv, *args], capture_output=True, text=True, check=False, timeout=60)
        if result.returncode == 0 and result.stdout.strip():
            directories[variable] = result.stdout.strip()
    return directories


def isolated_home_env(home: Path) -> dict[str, str]:
    """Build an environment whose home and per-user directories live under ``home``.

    The session's PATH and system variables are inherited; its Claude Code,
    Anthropic and update-control variables are not (CLAUDE_CODE_GIT_BASH_PATH
    stays, Claude Code needs it to find Git Bash on Windows), and neither is
    the PATH an outer Git Bash login shell recorded. HOME is passed in POSIX
    form so the toolbox launcher resolves ``$HOME/.claude/...`` under Git
    Bash as well.

    Args:
        home: Directory to use as the home directory.

    Returns:
        The environment mapping for subprocess.run().
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if (not key.upper().startswith(_STRIPPED_ENV_PREFIXES) or key.upper() in _KEPT_ENV_VARIABLES)
        and key.upper() not in _STRIPPED_ENV_VARIABLES
    }
    appdata_local = home / 'AppData' / 'Local'
    appdata_roaming = home / 'AppData' / 'Roaming'
    tmp_dir = home / 'tmp'
    for directory in (appdata_local, appdata_roaming, tmp_dir, home / '.config', home / '.cache'):
        directory.mkdir(parents=True, exist_ok=True)
    home_posix = home.as_posix()
    env.update({
        'HOME': home_posix,
        'USERPROFILE': home_posix,
        'APPDATA': str(appdata_roaming),
        'LOCALAPPDATA': str(appdata_local),
        'XDG_CONFIG_HOME': str(home / '.config'),
        'XDG_CACHE_HOME': str(home / '.cache'),
        'TEMP': str(tmp_dir),
        'TMP': str(tmp_dir),
        'TMPDIR': str(tmp_dir),
    })
    env.update(_uv_directories())
    return env


def claude_child_env(
    *,
    config_dir: Path,
    home: Path,
    api_url: str,
    claude_cmd: Path | None = None,
) -> dict[str, str]:
    """Build the environment of a child Claude Code process.

    On top of isolated_home_env(): the config dir is ``config_dir``, API
    traffic goes to ``api_url`` with a dummy key, nonessential traffic and
    updates are off, uv runs hook scripts against their lockfiles
    (UV_LOCKED=1, so a stale lockfile fails the hook instead of being
    re-resolved), and ``claude_cmd``'s directory is prepended to PATH so the
    toolbox launcher resolves ``claude`` the way a shell would.

    Args:
        config_dir: Value of CLAUDE_CONFIG_DIR.
        home: Directory to use as the home directory.
        api_url: Base URL of the fake API server.
        claude_cmd: Path of the claude binary, when the launcher needs it on PATH.

    Returns:
        The environment mapping for subprocess.run().
    """
    env = isolated_home_env(home)
    env.update({
        'CLAUDE_CONFIG_DIR': str(config_dir),
        'ANTHROPIC_BASE_URL': api_url,
        'ANTHROPIC_API_KEY': FAKE_API_KEY,
        'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC': '1',
        'DISABLE_AUTOUPDATER': '1',
        'DISABLE_TELEMETRY': '1',
        'DISABLE_ERROR_REPORTING': '1',
        'UV_LOCKED': '1',
    })
    if claude_cmd is not None:
        env['PATH'] = os.pathsep.join([str(Path(claude_cmd).parent), env.get('PATH', '')])
    return env


def seed_global_config(config_dir: Path, project_dir: Path) -> None:
    """Write the .claude.json that lets `claude -p` start without prompts.

    Onboarding is marked complete, the dummy API key is pre-approved (the
    CLI stores the last 20 characters of an approved key), and the working
    directory is trusted.

    Args:
        config_dir: The profile directory (CLAUDE_CONFIG_DIR).
        project_dir: The working directory the runs start in.
    """
    (config_dir / '.claude.json').write_text(json.dumps({
        'hasCompletedOnboarding': True,
        'customApiKeyResponses': {'approved': [FAKE_API_KEY[-20:]], 'rejected': []},
        'projects': {str(project_dir): {'hasTrustDialogAccepted': True}},
    }), encoding='utf-8')


def profile_config_sections(hooks_enabled: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the (profile_config, user_settings) pair create_profile_config() writes.

    The hooks section is the YAML shape of a toolbox configuration: the
    sentinel hook runs on SessionStart and on UserPromptSubmit with its
    config file as the argument, so config.json carries exactly the command
    string an installed profile would; the helper module is declared under
    ``hooks.helpers``, which installs it beside the script and never
    registers it as a command.

    Args:
        hooks_enabled: Whether the hook events are declared.

    Returns:
        The profile-owned keys and the user-settings section.
    """
    profile_config: dict[str, Any] = {}
    if hooks_enabled:
        profile_config['hooks'] = {
            'files': [f'hooks/{HOOK_SCRIPT}', f'hooks/{HOOK_CONFIG}'],
            'helpers': [f'hooks/{HOOK_HELPER}'],
            'events': [
                {'event': 'SessionStart', 'type': 'command', 'command': HOOK_SCRIPT, 'config': HOOK_CONFIG},
                {'event': 'UserPromptSubmit', 'type': 'command', 'command': HOOK_SCRIPT, 'config': HOOK_CONFIG},
            ],
        }
    return profile_config, {'outputStyle': STYLE_NAME}


@dataclass
class ClaudeRun:
    """One `claude -p --output-format stream-json` run and what it produced."""

    argv: list[str]
    returncode: int
    stdout: str
    stderr: str
    bodies: list[dict[str, Any]] = field(default_factory=list)
    init: dict[str, Any] | None = None
    hook_responses: list[dict[str, Any]] = field(default_factory=list)
    result: dict[str, Any] | None = None

    @property
    def body_text(self) -> str:
        """Every recorded request body, serialized, for sentinel searches."""
        return json.dumps(self.bodies, ensure_ascii=False)

    @property
    def system_text(self) -> str:
        """The system prompt of every recorded request, serialized."""
        return json.dumps([body.get('system') for body in self.bodies], ensure_ascii=False)

    def describe(self) -> str:
        """Summarize the run for an assertion message."""
        return (
            f'argv={self.argv!r}\nreturncode={self.returncode}\n'
            f'requests={len(self.bodies)}\nstdout={self.stdout[-3000:]!r}\nstderr={self.stderr[-3000:]!r}'
        )


def parse_stream_json(stdout: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]], dict[str, Any] | None]:
    """Extract the init message, the hook responses and the result from stream-json output.

    Lines that are not JSON objects are ignored (the launcher prints its own
    text before exec'ing claude).

    Args:
        stdout: The child's standard output.

    Returns:
        The system/init message, the hook_response messages, and the result message.
    """
    init: dict[str, Any] | None = None
    hook_responses: list[dict[str, Any]] = []
    result: dict[str, Any] | None = None
    for line in stdout.splitlines():
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if not isinstance(message, dict):
            continue
        if message.get('type') == 'system' and message.get('subtype') == 'init':
            init = message
        elif message.get('type') == 'system' and message.get('subtype') == 'hook_response':
            hook_responses.append(message)
        elif message.get('type') == 'result':
            result = message
    return init, hook_responses, result


def run_stream_json(
    argv: list[str],
    *,
    env: dict[str, str],
    cwd: Path,
    server: FakeAnthropicServer,
    timeout: int = 90,
) -> ClaudeRun:
    """Run a command that ends in a `claude -p ... --output-format stream-json` turn.

    The request bodies the fake server records during the run are attached
    to the result; bodies recorded by earlier runs on the same server are not.

    Args:
        argv: The full command line (claude itself, or the launcher).
        env: The child environment.
        cwd: The working directory of the run.
        server: The fake API server the child talks to.
        timeout: Seconds before the run is abandoned.

    Returns:
        The parsed run.
    """
    first_body = len(server.bodies)
    completed = subprocess.run(
        argv, cwd=cwd, env=env, capture_output=True, encoding='utf-8', errors='replace',
        check=False, timeout=timeout,
    )
    init, hook_responses, result = parse_stream_json(completed.stdout)
    return ClaudeRun(
        argv=argv, returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr,
        bodies=list(server.bodies[first_body:]), init=init, hook_responses=hook_responses, result=result,
    )


def print_args(prompt: str, *extra: str) -> list[str]:
    """Return the `claude` arguments of one non-interactive turn.

    Nothing here limits where Claude Code reads settings or memory from: the
    run discovers files exactly as a user's session does, and the workspace
    layout (see workspace_root()) keeps every real config home out of the
    working directory's ancestors instead.

    Args:
        prompt: The user prompt.
        extra: Further claude arguments placed after the prompt.

    Returns:
        The argument list, without the binary itself.
    """
    return ['-p', prompt, *extra, '--output-format', 'stream-json', '--verbose', '--max-turns', '1']


def session_file(projects_dir: Path, session_id: str) -> Path | None:
    """Find the transcript of ``session_id`` under ``projects_dir``, if any."""
    matches = list(projects_dir.glob(f'*/{session_id}.jsonl'))
    return matches[0] if matches else None
