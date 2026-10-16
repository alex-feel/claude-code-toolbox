"""E2E tests for claude subcommands started through a profile's entry points.

Claude Code's option parser reads an option placed before a subcommand as a
root option and one placed after it as the subcommand's own, so every
launch.sh hands claude the profile's options first and the caller's
arguments last: ``<profile> mcp add -s user ...`` reaches Claude Code as
``claude <profile options> mcp add -s user ...``. Claude Code dispatches some
commands only from the start of its command line; for those the launcher
hands claude the caller's arguments alone, after it applied the profile's
environment.

The stub claude these tests put on PATH records what each entry point
started it with; every generated entry point runs under its real
interpreter.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scripts import setup_environment
from scripts.setup_environment import create_launcher_script
from scripts.setup_environment import register_global_command
from tests.e2e.launcher_support import LAUNCHER_VARIANTS
from tests.e2e.launcher_support import WINDOWS_GIT_BASH
from tests.e2e.launcher_support import LaunchRecord
from tests.e2e.launcher_support import find_bash
from tests.e2e.launcher_support import find_powershell
from tests.e2e.launcher_support import launch
from tests.e2e.launcher_support import mcp_config_values
from tests.e2e.launcher_support import powershell_command
from tests.e2e.launcher_support import require_empty_array_expansion
from tests.e2e.launcher_support import same_path
from tests.e2e.launcher_support import seed_profile
from tests.e2e.launcher_support import write_marking_loaders

COMMAND = 'sub-cmd'
ALIAS = 'sub-alias'
IS_WINDOWS = sys.platform == 'win32'

# The command a user ran when every subcommand failed with
# "unknown option '--settings'".
MCP_ADD = ['mcp', 'add', '-s', 'user', '-t', 'http', 'probe', 'https://example.invalid/mcp']

# One argument list per kind of command Claude Code dispatches only from the
# start of its command line.
FIRST_ARGUMENT_FORMS = [
    pytest.param(['logs', 'zzz-none'], id='command'),
    pytest.param(['plugin', 'test'], id='two-word-command'),
    pytest.param(['--allow-dangerously-skip-permissions', 'daemon', 'status'], id='command-after-flags'),
    pytest.param(['--upgrade'], id='sole-flag'),
]

# Argument lists Claude Code reads with its option parser.
PROFILE_OPTION_FORMS = [
    pytest.param(['mcp', 'list'], id='subcommand'),
    pytest.param(['--update', 'now'], id='flag-not-alone'),
    pytest.param(['hi'], id='positional-prompt'),
    pytest.param(['-p', '--', '-dash prompt'], id='end-of-options'),
    pytest.param(['--settings', 'other.json', '--probe-arg'], id='own-settings'),
]


def _assert_profile_options_then(
    record: LaunchRecord, profile_dir: Path, prompt: str | None, user_args: list[str], *, mcp: bool,
) -> None:
    """Assert that claude received exactly the profile's options and then the caller's arguments.

    Args:
        record: What the stub claude received.
        profile_dir: The profile directory the launch must use.
        prompt: The system prompt file name, or None.
        user_args: The arguments the caller passed.
        mcp: Whether the profile holds an mcp.json.
    """
    options = record.args[:len(record.args) - len(user_args)]
    assert record.args[len(options):] == user_args, record.args
    assert same_path(record.config_dir, profile_dir), f'CLAUDE_CONFIG_DIR={record.config_dir}'
    assert record.loader_marks == 'sh;', record.loader_marks
    assert options[-2] == '--settings', record.args
    assert same_path(options[-1], profile_dir / 'config.json'), record.args
    remaining = options[:-2]
    if mcp:
        assert remaining[0] == '--strict-mcp-config', record.args
        assert remaining[1].startswith('--mcp-config='), record.args
        assert same_path(remaining[1].removeprefix('--mcp-config='), profile_dir / 'mcp.json'), record.args
        remaining = remaining[2:]
    if prompt is not None:
        assert remaining[-2] in {'--system-prompt-file', '--append-system-prompt-file'}, record.args
        assert same_path(remaining[-1], profile_dir / 'prompts' / prompt), record.args
        remaining = remaining[:-2]
    assert remaining == [], record.args


def _assert_caller_arguments_alone(record: LaunchRecord, profile_dir: Path, user_args: list[str]) -> None:
    """Assert that claude received the caller's arguments and nothing else, in the profile's environment.

    Args:
        record: What the stub claude received.
        profile_dir: The profile directory the launch must use.
        user_args: The arguments the caller passed.
    """
    assert record.args == user_args, record.args
    assert same_path(record.config_dir, profile_dir), f'CLAUDE_CONFIG_DIR={record.config_dir}'
    assert record.loader_marks == 'sh;', record.loader_marks


def _cmd_line(target: str, *args: str) -> str:
    """Build a cmd.exe command line that runs a batch file or command with arguments.

    Args:
        target: The batch file path or the command name.
        *args: The arguments, none holding a space.

    Returns:
        The command line for subprocess.
    """
    return f'cmd.exe /d /s /c ""{target}" {" ".join(args)}"'


def _install_profile(
    paths: dict[str, Path], prompt: str | None, mode: str,
) -> tuple[Path, Path, Path]:
    """Install a profile's launchers and global commands under the isolated home.

    Args:
        paths: The e2e_isolated_home paths.
        prompt: The system prompt file name, or None.
        mode: The command-defaults mode.

    Returns:
        The profile directory, the main launcher and launch.sh.
    """
    profile_dir = paths['claude_dir'] / COMMAND
    seed_profile(profile_dir, prompt)
    write_marking_loaders(profile_dir)
    result = create_launcher_script(profile_dir, COMMAND, prompt, mode, has_profile_mcp_servers=True)
    assert result is not None
    main_launcher, launch_sh = result
    assert register_global_command(main_launcher, COMMAND, [ALIAS], launch_script_path=launch_sh)
    return profile_dir, main_launcher, launch_sh


def _windows_entry_points(
    profile_dir: Path, start_ps1: Path, local_bin: Path, args: list[str],
) -> list[tuple[str, list[str] | str]]:
    """Return every Windows entry point of the profile, each started with args.

    Args:
        profile_dir: The profile directory.
        start_ps1: The profile's start.ps1.
        local_bin: The directory holding the global commands.
        args: The caller's arguments.

    Returns:
        Labels and command lines.
    """
    bash = find_bash()
    powershell = find_powershell()
    assert bash is not None
    assert powershell is not None
    entry_points: list[tuple[str, list[str] | str]] = [
        ('launch.sh', [bash, str(profile_dir / 'launch.sh'), *args]),
        ('start.cmd', _cmd_line(str(profile_dir / 'start.cmd'), *args)),
        ('start.ps1', powershell_command(powershell, start_ps1, *args)),
    ]
    for name in (COMMAND, ALIAS):
        entry_points.extend([
            (f'{name}.cmd', _cmd_line(name, *args)),
            (f'{name}.ps1', powershell_command(powershell, local_bin / f'{name}.ps1', *args)),
            (name, [bash, str(local_bin / name), *args]),
        ])
    return entry_points


def _unix_entry_points(profile_dir: Path, local_bin: Path, args: list[str]) -> list[tuple[str, list[str] | str]]:
    """Return every Linux and macOS entry point of the profile, each started with args.

    Args:
        profile_dir: The profile directory.
        local_bin: The directory holding the global commands.
        args: The caller's arguments.

    Returns:
        Labels and command lines.
    """
    bash = find_bash()
    assert bash is not None
    return [
        ('launch.sh', [bash, str(profile_dir / 'launch.sh'), *args]),
        (COMMAND, [str(local_bin / COMMAND), *args]),
        (ALIAS, [str(local_bin / ALIAS), *args]),
    ]


def _entry_points(
    paths: dict[str, Path], profile_dir: Path, main_launcher: Path, args: list[str],
) -> list[tuple[str, list[str] | str]]:
    """Return every entry point this platform registers for the profile, each started with args."""
    if IS_WINDOWS:
        if not WINDOWS_GIT_BASH.exists() or find_powershell() is None or find_bash() is None:
            pytest.skip('Git Bash at its standard location and PowerShell are required')
        return _windows_entry_points(profile_dir, main_launcher, paths['local_bin'], args)
    if find_bash() is None:
        pytest.skip('bash unavailable')
    return _unix_entry_points(profile_dir, paths['local_bin'], args)


class TestEveryEntryPoint:
    """Each entry point of a profile starts subcommands and first-argument commands correctly."""

    @pytest.mark.parametrize(('variant', 'prompt', 'mode'), LAUNCHER_VARIANTS)
    def test_subcommand_receives_every_profile_option_before_it(
        self, e2e_isolated_home: dict[str, Path], variant: str, prompt: str | None, mode: str,
    ) -> None:
        """``mcp add ...`` reaches claude after every profile option, its own arguments last."""
        del variant
        profile_dir, main_launcher, _ = _install_profile(e2e_isolated_home, prompt, mode)

        for label, command in _entry_points(e2e_isolated_home, profile_dir, main_launcher, MCP_ADD):
            record = launch(
                command, home=e2e_isolated_home['home'], stub_dir=e2e_isolated_home['home'].parent / 'stub-bin',
                extra_path=e2e_isolated_home['local_bin'],
            )
            try:
                _assert_profile_options_then(record, profile_dir, prompt, MCP_ADD, mcp=True)
            except AssertionError as error:
                raise AssertionError(f'{label}: {error}') from error

    @pytest.mark.parametrize(
        'args', [['logs', 'zzz-none'], ['--dangerously-skip-permissions', 'daemon', 'status']], ids=' '.join,
    )
    def test_first_argument_command_receives_the_caller_arguments_alone(
        self, e2e_isolated_home: dict[str, Path], args: list[str],
    ) -> None:
        """A command Claude Code dispatches only from the start reaches claude with no profile option."""
        profile_dir, main_launcher, _ = _install_profile(e2e_isolated_home, 'sub-prompt.md', 'replace')

        for label, command in _entry_points(e2e_isolated_home, profile_dir, main_launcher, args):
            record = launch(
                command, home=e2e_isolated_home['home'], stub_dir=e2e_isolated_home['home'].parent / 'stub-bin',
                extra_path=e2e_isolated_home['local_bin'],
            )
            try:
                _assert_caller_arguments_alone(record, profile_dir, args)
            except AssertionError as error:
                raise AssertionError(f'{label}: {error}') from error


class TestLaunchShRenderings:
    """The Windows and the Unix launch.sh, run under bash, order the arguments the same way."""

    @staticmethod
    def _launch(
        paths: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        system: str,
        prompt: str | None,
        mode: str,
        args: list[str],
        *,
        mcp: bool,
    ) -> tuple[Path, LaunchRecord]:
        """Render launch.sh for a platform and run it under this host's bash with args.

        Returns:
            The profile directory and what the stub claude received.
        """
        bash = find_bash()
        if bash is None:
            pytest.skip('bash unavailable')
        if system == 'Windows':
            require_empty_array_expansion(bash)
        profile_dir = paths['claude_dir'] / COMMAND
        seed_profile(profile_dir, prompt, mcp=mcp)
        write_marking_loaders(profile_dir)
        monkeypatch.setattr(setup_environment.platform, 'system', lambda: system)
        result = create_launcher_script(profile_dir, COMMAND, prompt, mode, has_profile_mcp_servers=mcp)
        assert result is not None
        record = launch([bash, str(result[1]), *args], home=paths['home'], stub_dir=paths['home'].parent / 'stub-bin')
        return profile_dir, record

    @pytest.mark.parametrize('system', ['Windows', 'Linux'])
    @pytest.mark.parametrize(('variant', 'prompt', 'mode'), LAUNCHER_VARIANTS)
    @pytest.mark.parametrize('args', FIRST_ARGUMENT_FORMS)
    def test_first_argument_commands_start_with_the_caller_arguments_alone(
        self,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        system: str,
        variant: str,
        prompt: str | None,
        mode: str,
        args: list[str],
    ) -> None:
        del variant
        profile_dir, record = self._launch(e2e_isolated_home, monkeypatch, system, prompt, mode, args, mcp=True)

        _assert_caller_arguments_alone(record, profile_dir, args)

    @pytest.mark.parametrize('mcp', [True, False], ids=['mcp', 'no-mcp'])
    @pytest.mark.parametrize('system', ['Windows', 'Linux'])
    @pytest.mark.parametrize(('variant', 'prompt', 'mode'), LAUNCHER_VARIANTS)
    @pytest.mark.parametrize('args', PROFILE_OPTION_FORMS)
    def test_other_arguments_follow_every_profile_option(
        self,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        system: str,
        variant: str,
        prompt: str | None,
        mode: str,
        args: list[str],
        mcp: bool,
    ) -> None:
        del variant
        profile_dir, record = self._launch(e2e_isolated_home, monkeypatch, system, prompt, mode, args, mcp=mcp)

        _assert_profile_options_then(record, profile_dir, prompt, args, mcp=mcp)
        assert len(mcp_config_values(record)) == (1 if mcp else 0), record.args
