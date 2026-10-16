"""E2E tests running real Claude Code subcommands through a profile's launch.sh.

launch.sh hands Claude Code the profile's options first and the caller's
arguments last, so a subcommand receives every profile option as a root
option of Claude Code; the commands Claude Code dispatches only from the
start of its command line receive the caller's arguments alone. The real
binary runs every case through the launch.sh create_launcher_script()
writes, in an isolated home, against an offline fake API:

- ``mcp add -s user -t http ...``, ``mcp get``, ``mcp list`` and
  ``mcp remove`` succeed and change the profile's own .claude.json;
- a positional prompt in a profile with profile-scoped MCP servers and no
  system prompt starts a session that carries the profile's settings;
- each first-argument command that can run without starting a background
  service, a runner or Remote Control dispatches as that command rather
  than as a prompt, and ``--update`` under DISABLE_UPDATES prints the
  refusal and changes nothing;
- every command ``claude --help`` lists either shows its own usage behind
  the launcher's options or is in CLAUDE_FIRST_ARGUMENT_COMMANDS and does
  not, so a later release that adds a command Claude Code dispatches only
  from the start of its command line fails here until the definition names
  it.

Skipped when the binary is absent; CLAUDE_CODE_TOOLBOX_REQUIRE_REAL_BINARY=1
(set in CI) turns absence into a failure instead of a silent skip.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts import install_claude
from scripts import setup_environment
from scripts.setup_environment import CLAUDE_FIRST_ARGUMENT_COMMANDS
from tests.e2e import linked_entries_support as support
from tests.e2e.fake_anthropic_api import FakeAnthropicServer
from tests.e2e.launcher_support import launch

_REQUIRE_REAL_BINARY = os.environ.get('CLAUDE_CODE_TOOLBOX_REQUIRE_REAL_BINARY') == '1'
_PROFILE_NAME = 'e2e-sub'
_PROMPT_FILE = 'e2e-sub-prompt.md'
_HEADER_NAME = 'x-e2e-profile'
_HEADER_SENTINEL = 'ZQX-SUBCOMMAND-PROFILE-8d41c7'
_PROMPT_SENTINEL = 'ZQX-POSITIONAL-PROMPT-2b6e90'
_UNKNOWN_SESSION = 'zzz-none'
_PROBE_URL = 'https://example.invalid/mcp'
# A closed local port: any network attempt fails immediately
_DEAD_PROXY = 'http://127.0.0.1:9'
_ROOT_USAGE_PREFIX = 'Usage: claude [options]'
# Background-session commands that answer an unknown id without starting the
# background service; respawn starts it first.
_UNKNOWN_SESSION_COMMANDS = ('logs', 'attach', 'stop', 'kill', 'rm')

pytestmark = [
    pytest.mark.real_binary,
    pytest.mark.skipif(
        support.CLAUDE_CMD is None and not _REQUIRE_REAL_BINARY,
        reason='claude binary not available',
    ),
]


@dataclass
class Run:
    """One launch.sh or claude run and what it produced."""

    argv: list[str]
    returncode: int
    stdout: str
    stderr: str
    requests: int

    @property
    def output(self) -> str:
        """Standard output and standard error together."""
        return self.stdout + self.stderr

    def describe(self) -> str:
        """Summarize the run for an assertion message."""
        return (
            f'argv={self.argv!r}\nreturncode={self.returncode}\nrequests={self.requests}\n'
            f'stdout={self.stdout[-3000:]!r}\nstderr={self.stderr[-3000:]!r}'
        )


@dataclass
class LauncherProfile:
    """An installed profile in an isolated home, with the fake API it talks to."""

    home: Path
    config_dir: Path
    project_dir: Path
    env: dict[str, str]
    server: FakeAnthropicServer

    def install_launcher(self, prompt: str | None, mode: str = 'replace') -> Path:
        """Write launch.sh exactly as an install writes it, spelled against the isolated home.

        Args:
            prompt: The system prompt file name, or None.
            mode: The command-defaults mode.

        Returns:
            The launch.sh path.
        """
        with patch.object(setup_environment, 'get_real_user_home', return_value=self.home):
            created = setup_environment.create_launcher_script(
                self.config_dir, _PROFILE_NAME, prompt, mode, has_profile_mcp_servers=True,
            )
        assert created is not None
        return created[1]

    def run(self, argv: list[str], *, env: dict[str, str] | None = None, cwd: Path | None = None) -> Run:
        """Run a command in the profile's environment and count the API requests it made.

        Args:
            argv: The full command line.
            env: The environment; the profile's own when omitted.
            cwd: The working directory; the project when omitted.

        Returns:
            The run.
        """
        first = len(self.server.bodies)
        completed = subprocess.run(
            argv, cwd=cwd or self.project_dir, env=env or self.env, capture_output=True, encoding='utf-8',
            errors='replace', stdin=subprocess.DEVNULL, check=False, timeout=120,
        )
        return Run(
            argv=argv, returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr,
            requests=len(self.server.bodies) - first,
        )

    def run_launcher(self, launch_sh: Path, *args: str, env: dict[str, str] | None = None) -> Run:
        """Run launch.sh under bash (Git Bash on Windows) with args."""
        bash = setup_environment.find_bash_windows() if sys.platform == 'win32' else shutil.which('bash')
        assert bash is not None, 'bash is required to run the toolbox launcher'
        return self.run([bash, launch_sh.as_posix(), *args], env=env)

    def run_claude(self, *args: str) -> Run:
        """Run the real binary directly with args."""
        assert support.CLAUDE_CMD is not None
        return self.run([str(support.CLAUDE_CMD), *args])

    def global_config(self) -> dict[str, Any]:
        """Return the profile's .claude.json."""
        return json.loads((self.config_dir / '.claude.json').read_text(encoding='utf-8'))


@pytest.fixture
def profile(tmp_path: Path) -> Iterator[LauncherProfile]:
    """Provide an installed profile with a config.json, an mcp.json and a system prompt, and a running fake API."""
    root, cleanup = support.workspace_root(tmp_path)
    home = root / 'home'
    config_dir = home / '.claude' / _PROFILE_NAME
    (config_dir / 'prompts').mkdir(parents=True)
    (config_dir / 'prompts' / _PROMPT_FILE).write_text('You are the e2e subcommand profile.\n', encoding='utf-8')
    (config_dir / 'mcp.json').write_text(json.dumps({'mcpServers': {}}), encoding='utf-8')
    project_dir = root / 'project'
    project_dir.mkdir()
    user_settings = {'env': {'ANTHROPIC_CUSTOM_HEADERS': f'{_HEADER_NAME}: {_HEADER_SENTINEL}'}}
    assert setup_environment.create_profile_config({}, config_dir, user_settings=user_settings)
    support.seed_global_config(config_dir, project_dir)
    server = FakeAnthropicServer().start()
    try:
        env = support.claude_child_env(
            config_dir=config_dir, home=home, api_url=server.url, claude_cmd=support.CLAUDE_CMD,
        )
        yield LauncherProfile(home=home, config_dir=config_dir, project_dir=project_dir, env=env, server=server)
    finally:
        server.stop()
        cleanup()


def _offline_env(profile: LauncherProfile) -> dict[str, str]:
    """Return the profile's environment with every network path closed and updates disabled.

    Every proxy variable points at a closed local port, the per-user data and
    state directories lie inside the isolated home, and DISABLE_UPDATES is
    set, so an update attempt can neither download nor install anything.

    Args:
        profile: The installed profile.

    Returns:
        The environment mapping for subprocess.run().
    """
    env = {key: value for key, value in profile.env.items() if key.upper() != 'NO_PROXY'}
    for name in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY'):
        env[name] = _DEAD_PROXY
        env[name.lower()] = _DEAD_PROXY
    for name, relative in (('XDG_DATA_HOME', ('.local', 'share')), ('XDG_STATE_HOME', ('.local', 'state'))):
        directory = profile.home.joinpath(*relative)
        directory.mkdir(parents=True, exist_ok=True)
        env[name] = str(directory)
    env['DISABLE_UPDATES'] = '1'
    return env


def _first_line(text: str) -> str:
    """Return the first non-empty line of text."""
    return next((line.strip() for line in text.splitlines() if line.strip()), '')


def _listed_commands(help_text: str) -> list[str]:
    """Return every command name and alias the Commands section of ``claude --help`` lists.

    Args:
        help_text: The output of ``claude --help``.

    Returns:
        The names, aliases split out (``stop|kill`` gives ``stop`` and ``kill``).
    """
    _, _, section = help_text.partition('\nCommands:\n')
    names: list[str] = []
    for line in section.splitlines():
        match = re.match(r'^  (\S+)', line)
        if match:
            names.extend(match.group(1).split('|'))
    return names


def _launcher_options(profile: LauncherProfile, launch_sh: Path, stub_dir: Path) -> list[str]:
    """Return the options launch.sh hands claude ahead of the caller's arguments.

    The launcher runs once with a stub claude from the home folder, where it
    passes every option it has, and the stub records them.

    Args:
        profile: The installed profile.
        launch_sh: The profile's launch.sh.
        stub_dir: Directory for the stub claude.

    Returns:
        The options, in the order the launcher passes them.
    """
    bash = setup_environment.find_bash_windows() if sys.platform == 'win32' else shutil.which('bash')
    assert bash is not None
    record = launch([bash, str(launch_sh), '--probe-arg'], home=profile.home, stub_dir=stub_dir, cwd=profile.home)
    assert record.args[-1] == '--probe-arg', record.args
    options = record.args[:-1]
    assert '--settings' in options, options
    assert '--setting-sources' in options, options
    return options


@pytest.mark.parametrize('prompt', [None, _PROMPT_FILE], ids=['no-prompt', 'prompt-replace'])
def test_mcp_subcommands_run_through_the_launcher(profile: LauncherProfile, prompt: str | None) -> None:
    """mcp add, get, list and remove succeed through launch.sh and change the profile's .claude.json."""
    launch_sh = profile.install_launcher(prompt)

    added = profile.run_launcher(launch_sh, 'mcp', 'add', '-s', 'user', '-t', 'http', 'probe', _PROBE_URL)
    assert added.returncode == 0, added.describe()
    assert "unknown option '--settings'" not in added.output, added.describe()
    assert profile.global_config()['mcpServers']['probe']['url'] == _PROBE_URL

    shown = profile.run_launcher(launch_sh, 'mcp', 'get', 'probe')
    assert shown.returncode == 0, shown.describe()
    assert _PROBE_URL in shown.output, shown.describe()

    listed = profile.run_launcher(launch_sh, 'mcp', 'list')
    assert listed.returncode == 0, listed.describe()
    assert 'probe' in listed.output, listed.describe()

    removed = profile.run_launcher(launch_sh, 'mcp', 'remove', 'probe', '-s', 'user')
    assert removed.returncode == 0, removed.describe()
    assert 'probe' not in profile.global_config().get('mcpServers', {})

    assert added.requests == shown.requests == listed.requests == removed.requests == 0


def test_positional_prompt_starts_a_session_with_the_profile_settings(profile: LauncherProfile) -> None:
    """A positional prompt in a no-prompt profile with profile-scoped MCP servers reaches the model as the prompt."""
    launch_sh = profile.install_launcher(None)

    run = profile.run_launcher(
        launch_sh, _PROMPT_SENTINEL, '-p', '--output-format', 'stream-json', '--verbose', '--max-turns', '1',
    )

    assert run.returncode == 0, run.describe()
    assert run.requests == 1, run.describe()
    assert _PROMPT_SENTINEL in json.dumps(profile.server.bodies[-1]), run.describe()
    assert profile.server.headers[-1].get(_HEADER_NAME) == _HEADER_SENTINEL, run.describe()


@pytest.mark.parametrize('prompt', [None, _PROMPT_FILE], ids=['no-prompt', 'prompt-replace'])
@pytest.mark.parametrize('command', _UNKNOWN_SESSION_COMMANDS)
def test_background_session_commands_dispatch_as_commands(
    profile: LauncherProfile, command: str, prompt: str | None,
) -> None:
    """An unknown session id gets the command's own answer, and no prompt reaches the model."""
    launch_sh = profile.install_launcher(prompt)

    run = profile.run_launcher(launch_sh, command, _UNKNOWN_SESSION)

    assert run.returncode == 1, run.describe()
    assert f"No job matching '{_UNKNOWN_SESSION}'" in run.output, run.describe()
    assert run.requests == 0, run.describe()


def test_plugin_test_dispatches_as_its_own_command(profile: LauncherProfile) -> None:
    """``plugin test`` reaches Claude Code's plugin test runner instead of the plugin command group."""
    launch_sh = profile.install_launcher(_PROMPT_FILE)

    run = profile.run_launcher(launch_sh, 'plugin', 'test', '--help')

    assert 'claude plugin test' in run.output, run.describe()
    assert 'Usage: claude plugin|plugins' not in run.output, run.describe()
    assert run.requests == 0, run.describe()


@pytest.mark.parametrize('flag', CLAUDE_FIRST_ARGUMENT_COMMANDS.sole)
def test_sole_update_flag_dispatches_as_the_update_command(profile: LauncherProfile, flag: str) -> None:
    """``--update`` alone runs the update command, which DISABLE_UPDATES refuses without changing anything."""
    launch_sh = profile.install_launcher(_PROMPT_FILE)
    assert support.CLAUDE_CMD is not None
    binary_before = support.CLAUDE_CMD.stat().st_mtime_ns

    run = profile.run_launcher(launch_sh, flag, env=_offline_env(profile))

    assert run.returncode == 0, run.describe()
    assert install_claude.CLAUDE_UPDATES_DISABLED_MESSAGE in run.output, run.describe()
    assert run.requests == 0, run.describe()
    assert support.CLAUDE_CMD.stat().st_mtime_ns == binary_before


def test_every_listed_command_works_behind_the_launcher_options_or_starts_first(
    profile: LauncherProfile, tmp_path: Path,
) -> None:
    """Each command of ``claude --help`` shows its own usage behind the launcher's options, unless it must start first.

    A command in CLAUDE_FIRST_ARGUMENT_COMMANDS must fall back to the root
    usage behind the options, which is why the launcher hands it the caller's
    arguments alone; every other listed command must show the same usage
    there as it shows alone.
    """
    launch_sh = profile.install_launcher(_PROMPT_FILE)
    options = _launcher_options(profile, launch_sh, tmp_path / 'stub-bin')
    root = profile.run_claude('--help')
    assert root.returncode == 0, root.describe()
    root_usage = _first_line(root.stdout)
    assert root_usage.startswith(_ROOT_USAGE_PREFIX), root.describe()
    listed = _listed_commands(root.stdout)
    assert 'mcp' in listed, root.describe()
    assert 'logs' in listed, root.describe()

    misclassified: list[str] = []
    for name in listed:
        behind = profile.run_claude(*options, name, '--help')
        behind_usage = _first_line(behind.stdout)
        if name in CLAUDE_FIRST_ARGUMENT_COMMANDS.names:
            if behind_usage != root_usage:
                misclassified.append(f'{name}: shows {behind_usage!r} behind the options, so it needs no passthrough')
            continue
        alone = profile.run_claude(name, '--help')
        alone_usage = _first_line(alone.stdout)
        if behind_usage != alone_usage or behind_usage == root_usage:
            misclassified.append(
                f'{name}: shows {behind_usage!r} behind the options and {alone_usage!r} alone; '
                'name it in CLAUDE_FIRST_ARGUMENT_COMMANDS if Claude Code dispatches it only first',
            )
    assert not misclassified, '\n'.join(misclassified)
