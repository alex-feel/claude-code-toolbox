"""E2E tests for user arguments that start with a slash.

On Windows every profile command runs the profile's launch.sh under Git Bash,
and Git Bash rewrites an argument that looks like a POSIX path when it starts
the native claude.exe: ``/review src`` would reach Claude Code as
``C:/Program Files/Git/review src``. The Windows launch.sh therefore keeps an
argument that starts with a single slash and names no existing path, such as
a slash command, exactly as typed, while an argument naming an existing path
keeps its conversion to a Windows path.

The stub claude these tests put on PATH is a native program on Windows, so
Git Bash converts its arguments exactly as it converts those of claude.exe.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts import setup_environment
from scripts.setup_environment import create_launcher_script
from scripts.setup_environment import register_global_command
from tests.e2e.launcher_support import LAUNCHER_VARIANTS
from tests.e2e.launcher_support import SESSION_BASH_VARIABLE
from tests.e2e.launcher_support import SESSION_PROBE_PATH
from tests.e2e.launcher_support import WINDOWS_GIT_BASH
from tests.e2e.launcher_support import LaunchRecord
from tests.e2e.launcher_support import assert_reaches_profile
from tests.e2e.launcher_support import find_bash
from tests.e2e.launcher_support import find_powershell
from tests.e2e.launcher_support import launch
from tests.e2e.launcher_support import powershell_command
from tests.e2e.launcher_support import same_path
from tests.e2e.launcher_support import seed_profile
from tests.e2e.profile_support import run_main
from tests.e2e.validators import validate_launcher_keeps_slash_arguments

FIXTURES = Path(__file__).parent / 'fixtures'

# A slash command with spaces and a trailing OWNER/NAME, as a scheduled
# headless run passes it.
SLASH_COMMAND = '/weekly-review scheduled OWNER/NAME'
SLASH_WITH_BACKSLASH = '/review src\\launcher.py'
SLASH_WITH_QUOTES = '/explain "quoted" it\'s'
# Git Bash never converts an argument holding a semicolon.
SLASH_WITH_SEMICOLON = '/run first;second'
# Git Bash turns a leading double slash into a single one on its own.
DOUBLE_SLASH = '//literal'
PLAIN_ARGUMENT = 'plain words'

IS_WINDOWS = sys.platform == 'win32'


def _require_bash() -> str:
    """Return the bash the generated launch.sh runs under, or skip the test."""
    bash = find_bash()
    if bash is None:
        pytest.skip('bash unavailable')
    return bash


def _require_empty_array_expansion(bash: str) -> None:
    """Skip the test when bash cannot start claude with an empty MCP_FLAGS.

    The Windows launch.sh runs under ``set -u`` and passes ``"${MCP_FLAGS[@]}"``,
    an empty array when the profile has no mcp.json. bash before 4.4 reports
    an empty array as unbound there and stops, while Git Bash, the only shell
    the Windows launch.sh runs under, expands it to nothing. A bash a
    non-Windows runner provides, such as the macOS /bin/bash 3.2, can be older.

    Args:
        bash: The bash that runs the launchers.
    """
    completed = subprocess.run(
        [bash, '-c', 'set -u; flags=(); : "${flags[@]}"'],
        capture_output=True,
        check=False,
        timeout=60,
    )
    if completed.returncode != 0:
        pytest.skip(f'{bash} stops at an empty array under set -u, which Git Bash expands to nothing')


def _posix_spelling(bash: str, path: Path) -> str:
    """Spell an existing path the way a Git Bash user types it.

    Args:
        bash: The bash that runs the launchers.
        path: An existing path.

    Returns:
        ``/c/...`` on Windows, the path itself elsewhere.
    """
    if not IS_WINDOWS:
        return path.as_posix()
    completed = subprocess.run(
        [bash, '-c', 'cygpath -u "$1"', 'cygpath', str(path)],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return completed.stdout.strip()


def _windows_spelling(bash: str, text: str) -> str:
    """Spell a POSIX path the way Git Bash hands it to a native program.

    Args:
        bash: The bash that runs the launchers.
        text: A POSIX path.

    Returns:
        The ``cygpath -m`` spelling of text.
    """
    completed = subprocess.run(
        [bash, '-c', 'cygpath -m "$1"', 'cygpath', text],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return completed.stdout.strip()


def _user_arguments(record: LaunchRecord, count: int) -> list[str]:
    """Return the arguments claude received from the user, starting at -p.

    Args:
        record: What the stub claude received.
        count: How many user arguments the launch passed.

    Returns:
        The user arguments in the order claude received them.
    """
    assert '-p' in record.args, record.args
    start = record.args.index('-p')
    return record.args[start:start + count]


def _assert_converted_path(value: str, posix_path: str, expected: Path) -> None:
    """Assert that an existing path argument reached claude the way Git Bash hands it over.

    Args:
        value: The argument claude received.
        posix_path: The argument as the user typed it.
        expected: The path the argument names.
    """
    if IS_WINDOWS:
        assert not value.startswith('/'), f'{posix_path} reached claude unconverted: {value}'
        assert same_path(value, expected), value
    else:
        assert value == posix_path


def _cmd_line(target: str, *args: str) -> str:
    """Build a cmd.exe command line that runs a batch file or command with arguments.

    Args:
        target: The batch file path or the command name.
        *args: The arguments; one holding a space is double-quoted.

    Returns:
        The command line for subprocess.
    """
    quoted = [f'"{arg}"' if ' ' in arg else arg for arg in args]
    return f'cmd.exe /d /s /c ""{target}" {" ".join(quoted)}"'


class TestLaunchShKeepsSlashArguments:
    """launch.sh hands claude every slash argument exactly as it received it."""

    @pytest.mark.parametrize('with_mcp', [True, False], ids=['mcp', 'no-mcp'])
    @pytest.mark.parametrize(('variant', 'prompt', 'mode'), LAUNCHER_VARIANTS)
    def test_slash_arguments_reach_claude_unchanged(
        self,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        variant: str,
        prompt: str | None,
        mode: str,
        with_mcp: bool,
    ) -> None:
        """Slash commands arrive unchanged, an existing path still converts, other arguments stay as typed.

        Without an mcp.json the launcher starts claude with no MCP flags, and
        the slash commands still arrive unchanged.
        """
        del variant
        bash = _require_bash()
        if not with_mcp:
            _require_empty_array_expansion(bash)
        home = e2e_isolated_home['home']
        profile_dir = e2e_isolated_home['claude_dir'] / 'slash-cmd'
        seed_profile(profile_dir, prompt, mcp=with_mcp)
        monkeypatch.setattr(setup_environment.platform, 'system', lambda: 'Windows')
        result = create_launcher_script(profile_dir, 'slash-cmd', prompt, mode, has_profile_mcp_servers=with_mcp)
        assert result is not None
        existing = _posix_spelling(bash, profile_dir)
        arguments = [
            '-p', SLASH_COMMAND, SLASH_WITH_BACKSLASH, SLASH_WITH_QUOTES, SLASH_WITH_SEMICOLON,
            DOUBLE_SLASH, existing, PLAIN_ARGUMENT, '--probe-arg',
        ]

        record = launch([bash, str(result[1]), *arguments], home=home, stub_dir=home.parent / 'stub-bin')

        received = _user_arguments(record, len(arguments))
        assert received[:5] == ['-p', SLASH_COMMAND, SLASH_WITH_BACKSLASH, SLASH_WITH_QUOTES, SLASH_WITH_SEMICOLON]
        assert received[5] == ('/literal' if IS_WINDOWS else DOUBLE_SLASH)
        _assert_converted_path(received[6], existing, profile_dir)
        assert received[7:] == [PLAIN_ARGUMENT, '--probe-arg']
        assert_reaches_profile(record, profile_dir, prompt, mcp=with_mcp)

    @pytest.mark.parametrize(('variant', 'prompt', 'mode'), LAUNCHER_VARIANTS)
    def test_launch_without_slash_arguments_lists_nothing(
        self,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        variant: str,
        prompt: str | None,
        mode: str,
    ) -> None:
        """A launch with no slash argument leaves MSYS2_ARG_CONV_EXCL out of the session's environment."""
        del variant
        bash = _require_bash()
        home = e2e_isolated_home['home']
        profile_dir = e2e_isolated_home['claude_dir'] / 'slash-cmd'
        seed_profile(profile_dir, prompt)
        monkeypatch.setattr(setup_environment.platform, 'system', lambda: 'Windows')
        result = create_launcher_script(profile_dir, 'slash-cmd', prompt, mode, has_profile_mcp_servers=True)
        assert result is not None

        record = launch(
            [bash, str(result[1]), '-p', PLAIN_ARGUMENT, _posix_spelling(bash, profile_dir), '--probe-arg'],
            home=home,
            stub_dir=home.parent / 'stub-bin',
        )

        assert record.conversion_exclusions is None
        assert_reaches_profile(record, profile_dir, prompt)

    @pytest.mark.parametrize('system', ['Linux', 'Darwin'])
    @pytest.mark.parametrize(('variant', 'prompt', 'mode'), LAUNCHER_VARIANTS)
    def test_unix_launch_sh_lists_nothing(
        self,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        system: str,
        variant: str,
        prompt: str | None,
        mode: str,
    ) -> None:
        """The Linux and macOS launch.sh pass every argument straight through."""
        del variant
        profile_dir = e2e_isolated_home['claude_dir'] / 'slash-cmd'
        monkeypatch.setattr(setup_environment.platform, 'system', lambda: system)

        result = create_launcher_script(profile_dir, 'slash-cmd', prompt, mode, has_profile_mcp_servers=True)

        assert result is not None
        errors = validate_launcher_keeps_slash_arguments(result[1], windows=False)
        assert not errors, '\n'.join(errors)


@pytest.mark.skipif(sys.platform != 'win32', reason='Git Bash converts arguments only on Windows')
class TestWindowsEntryPointsKeepSlashArguments:
    """Every Windows entry point hands claude slash commands unchanged.

    Each entry point is run the way a user or a scheduled task runs it: the
    CMD and PowerShell launchers and wrappers hand over to launch.sh through
    Git Bash, and the Git Bash wrappers exec launch.sh directly.
    """

    @pytest.mark.parametrize('with_mcp', [True, False], ids=['mcp', 'no-mcp'])
    @pytest.mark.parametrize(('variant', 'prompt', 'mode'), LAUNCHER_VARIANTS)
    def test_every_entry_point_keeps_slash_arguments(
        self,
        e2e_isolated_home: dict[str, Path],
        variant: str,
        prompt: str | None,
        mode: str,
        with_mcp: bool,
    ) -> None:
        """start.cmd, start.ps1 and every global wrapper keep slash commands and convert existing paths.

        The profile runs with and without an mcp.json, so every launcher form
        starts claude through each entry point.
        """
        del variant
        powershell = find_powershell()
        bash = find_bash()
        if not WINDOWS_GIT_BASH.exists() or powershell is None or bash is None:
            pytest.skip('Git Bash at its standard location and PowerShell are required')
        home = e2e_isolated_home['home']
        local_bin = e2e_isolated_home['local_bin']
        profile_dir = e2e_isolated_home['claude_dir'] / 'slash-cmd'
        seed_profile(profile_dir, prompt, mcp=with_mcp)
        result = create_launcher_script(profile_dir, 'slash-cmd', prompt, mode, has_profile_mcp_servers=with_mcp)
        assert result is not None
        start_ps1, launch_sh = result
        assert register_global_command(start_ps1, 'slash-cmd', ['slash-alias'], launch_script_path=launch_sh)
        existing = _posix_spelling(bash, profile_dir)
        arguments = ['-p', SLASH_COMMAND, SLASH_WITH_BACKSLASH, existing, PLAIN_ARGUMENT, '--probe-arg']

        entry_points: list[tuple[str, list[str] | str]] = [
            ('start.cmd', _cmd_line(str(profile_dir / 'start.cmd'), *arguments)),
            ('start.ps1', powershell_command(powershell, start_ps1, *arguments)),
        ]
        for name in ('slash-cmd', 'slash-alias'):
            entry_points.extend([
                (f'{name}.cmd', _cmd_line(name, *arguments)),
                (f'{name}.ps1', powershell_command(powershell, local_bin / f'{name}.ps1', *arguments)),
                (name, [bash, str(local_bin / name), *arguments]),
            ])

        for label, command in entry_points:
            record = launch(command, home=home, stub_dir=home.parent / 'stub-bin', extra_path=local_bin)
            received = _user_arguments(record, len(arguments))
            assert received[:3] == ['-p', SLASH_COMMAND, SLASH_WITH_BACKSLASH], f'{label}: {record.args}'
            _assert_converted_path(received[3], existing, profile_dir)
            assert received[4:] == [PLAIN_ARGUMENT, '--probe-arg'], f'{label}: {record.args}'
            assert_reaches_profile(record, profile_dir, prompt, mcp=with_mcp)

    def test_inherited_exclusions_keep_applying(self, e2e_isolated_home: dict[str, Path]) -> None:
        """An MSYS2_ARG_CONV_EXCL the caller set still excludes its own entries beside the slash command."""
        bash = find_bash()
        if not WINDOWS_GIT_BASH.exists() or bash is None:
            pytest.skip('Git Bash at its standard location is required')
        home = e2e_isolated_home['home']
        local_bin = e2e_isolated_home['local_bin']
        profile_dir = e2e_isolated_home['claude_dir'] / 'slash-cmd'
        seed_profile(profile_dir, None)
        result = create_launcher_script(profile_dir, 'slash-cmd', None, 'replace', has_profile_mcp_servers=True)
        assert result is not None
        assert register_global_command(result[0], 'slash-cmd', [], launch_script_path=result[1])
        existing = _posix_spelling(bash, profile_dir)
        arguments = ['-p', SLASH_COMMAND, existing, '--probe-arg']

        record = launch(
            _cmd_line('slash-cmd', *arguments),
            home=home,
            stub_dir=home.parent / 'stub-bin',
            extra_path=local_bin,
            extra_env={'MSYS2_ARG_CONV_EXCL': existing},
        )

        assert _user_arguments(record, len(arguments)) == arguments


@pytest.mark.skipif(sys.platform != 'win32', reason='Git Bash converts arguments only on Windows')
class TestWindowsSessionKeepsConvertingPaths:
    """A session started with slash arguments inherits only their entries.

    The Bash tool of a session runs Git Bash with the session's environment,
    so the MSYS2_ARG_CONV_EXCL a launch exported reaches every native program
    started from there. The stub starts such a Git Bash and has it hand a path
    under /tmp to a native program, as the Bash tool does with a script.
    """

    def _launch_with_session_probe(
        self,
        e2e_isolated_home: dict[str, Path],
        prompt: str | None,
        mode: str,
        slash_arguments: list[str],
    ) -> tuple[str, LaunchRecord, list[str]]:
        """Run launch.sh with slash arguments and an existing path, probing the session.

        Args:
            e2e_isolated_home: The isolated home of the test.
            prompt: The system prompt file name, or None.
            mode: The system prompt mode.
            slash_arguments: The slash arguments the user passes.

        Returns:
            The bash that ran the launch, what the stub claude received, and
            the arguments the launch passed.
        """
        bash = find_bash()
        if not WINDOWS_GIT_BASH.exists() or bash is None:
            pytest.skip('Git Bash at its standard location is required')
        home = e2e_isolated_home['home']
        profile_dir = e2e_isolated_home['claude_dir'] / 'slash-cmd'
        seed_profile(profile_dir, prompt)
        result = create_launcher_script(profile_dir, 'slash-cmd', prompt, mode, has_profile_mcp_servers=True)
        assert result is not None
        arguments = ['-p', *slash_arguments, _posix_spelling(bash, profile_dir), '--probe-arg']

        record = launch(
            [bash, str(result[1]), *arguments],
            home=home,
            stub_dir=home.parent / 'stub-bin',
            extra_env={SESSION_BASH_VARIABLE: bash},
        )

        return bash, record, arguments

    @staticmethod
    def _assert_session_converts_paths(record: LaunchRecord) -> None:
        """Assert that Git Bash started from the session still converts a /tmp path.

        Args:
            record: What the stub claude received.
        """
        probe = record.session_probe
        assert probe is not None, 'the stub ran no session probe'
        assert not probe.received.startswith('/'), f'{SESSION_PROBE_PATH} reached the native program unconverted'
        assert probe.received == probe.converted, probe

    @pytest.mark.parametrize(('variant', 'prompt', 'mode'), LAUNCHER_VARIANTS)
    def test_one_listed_argument_reaches_session_in_windows_spelling(
        self,
        e2e_isolated_home: dict[str, Path],
        variant: str,
        prompt: str | None,
        mode: str,
    ) -> None:
        """One listed argument reaches the session as Git Bash spells that path, and paths keep converting."""
        del variant
        bash, record, arguments = self._launch_with_session_probe(e2e_isolated_home, prompt, mode, [SLASH_COMMAND])

        self._assert_session_converts_paths(record)
        assert _user_arguments(record, 2) == arguments[:2]
        assert record.conversion_exclusions == _windows_spelling(bash, SLASH_COMMAND)

    @pytest.mark.parametrize(('variant', 'prompt', 'mode'), LAUNCHER_VARIANTS)
    def test_several_listed_arguments_reach_session_as_listed(
        self,
        e2e_isolated_home: dict[str, Path],
        variant: str,
        prompt: str | None,
        mode: str,
    ) -> None:
        """Several listed arguments reach the session as the ';'-joined list, and paths keep converting."""
        del variant
        _, record, arguments = self._launch_with_session_probe(
            e2e_isolated_home, prompt, mode, [SLASH_COMMAND, SLASH_WITH_BACKSLASH],
        )

        self._assert_session_converts_paths(record)
        assert _user_arguments(record, 3) == arguments[:3]
        assert record.conversion_exclusions == f'{SLASH_COMMAND};{SLASH_WITH_BACKSLASH}'


class TestInstalledProfileKeepsSlashArguments:
    """A profile installed by setup starts claude with a slash command unchanged."""

    def test_global_command_passes_slash_command(self, e2e_isolated_home: dict[str, Path]) -> None:
        """The installed command hands a scheduled slash command to claude as typed."""
        _require_bash()
        home = e2e_isolated_home['home']
        local_bin = e2e_isolated_home['local_bin']
        profile_dir = e2e_isolated_home['claude_dir'] / 'slash-probe'

        exit_code = run_main([
            str(FIXTURES / 'command_defaults_base.yaml'), '--yes', '--skip-install', '--command-names', 'slash-probe',
        ])

        assert exit_code == 0
        errors = validate_launcher_keeps_slash_arguments(profile_dir / 'launch.sh', windows=IS_WINDOWS)
        assert not errors, '\n'.join(errors)
        arguments = ['-p', SLASH_COMMAND, '--probe-arg']
        command: list[str] | str
        if IS_WINDOWS:
            if not WINDOWS_GIT_BASH.exists():
                pytest.skip('Git Bash at its standard location is required')
            command = _cmd_line('slash-probe', *arguments)
        else:
            command = [str(local_bin / 'slash-probe'), *arguments]

        record = launch(command, home=home, stub_dir=home.parent / 'stub-bin', extra_path=local_bin)

        assert _user_arguments(record, len(arguments)) == arguments
        assert same_path(record.config_dir, profile_dir), record.config_dir
