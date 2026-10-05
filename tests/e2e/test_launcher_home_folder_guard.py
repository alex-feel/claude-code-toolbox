"""E2E tests for the setting sources a profile launcher hands Claude Code, by working directory.

Claude Code reads the working directory's ``.claude`` as the project settings
of the session, so a session started in the home folder would read the home
folder's ``.claude`` -- the base profile -- as its project settings and
hooks. Every ``launch.sh`` therefore passes ``--setting-sources user`` exactly
when it starts in the home folder, and nothing anywhere else, so the working
project's own ``.claude`` keeps applying. The tests run every launcher
variant and every entry point under its real interpreter with a stub
``claude`` from the home folder (on Windows also spelled in another letter
case and as a short name), from a project below it and from a directory
outside it, and read the arguments the stub received.
"""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path

import pytest

from scripts import setup_environment
from scripts.setup_environment import create_launcher_script
from scripts.setup_environment import register_global_command
from tests.e2e.expected.launchers import GOLDEN_PROMPT
from tests.e2e.launcher_support import LAUNCHER_VARIANTS
from tests.e2e.launcher_support import WINDOWS_GIT_BASH
from tests.e2e.launcher_support import LaunchRecord
from tests.e2e.launcher_support import assert_reaches_profile
from tests.e2e.launcher_support import cmd_command
from tests.e2e.launcher_support import find_bash
from tests.e2e.launcher_support import find_powershell
from tests.e2e.launcher_support import launch
from tests.e2e.launcher_support import powershell_command
from tests.e2e.launcher_support import require_empty_array_expansion
from tests.e2e.launcher_support import seed_profile

COMMAND = 'guard-cmd'
ALIAS = 'guard-alias'
IS_WINDOWS = sys.platform == 'win32'

# Where a launch starts: the home folder, a project below it, a directory
# beside it.
START_DIRECTORIES = ['home', 'project', 'outside']


def _setting_sources(record: LaunchRecord) -> list[str]:
    """Return every value claude received after ``--setting-sources``, in order."""
    return [record.args[index + 1] for index, arg in enumerate(record.args) if arg == '--setting-sources']


def _assert_sources(record: LaunchRecord, where: str, label: str) -> None:
    """Assert that the flags match the start directory: user-only in the home folder, none elsewhere."""
    sources = _setting_sources(record)
    if where == 'home':
        assert sources == ['user'], f'{label} started in the home folder without limiting settings: {record.args}'
        assert record.args.index('--setting-sources') < record.args.index('--probe-arg'), record.args
    else:
        assert sources == [], f'{label} started in {where} limited the settings sources: {record.args}'


def _start_directory(home: Path, where: str) -> Path:
    """Return the directory a launch starts in, creating it when needed."""
    if where == 'home':
        return home
    directory = home / 'work' / 'project' if where == 'project' else home.parent / 'outside'
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _windows_spellings(home: Path) -> list[Path]:
    """Return the home folder spelled in another letter case and as a short name."""
    buffer = ctypes.create_unicode_buffer(260)
    assert ctypes.windll.kernel32.GetShortPathNameW(str(home), buffer, 260)
    return [Path(str(home).swapcase()), Path(buffer.value)]


class TestLaunchShLimitsSettingsInTheHomeFolder:
    """launch.sh of every variant, run under bash, passes --setting-sources user in the home folder only."""

    @pytest.mark.parametrize('where', START_DIRECTORIES)
    @pytest.mark.parametrize('system', ['Windows', 'Linux', 'Darwin'])
    @pytest.mark.parametrize(('variant', 'prompt', 'mode'), LAUNCHER_VARIANTS)
    def test_flags_follow_the_start_directory(
        self,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        where: str,
        system: str,
        variant: str,
        prompt: str | None,
        mode: str,
    ) -> None:
        del variant
        bash = find_bash()
        if bash is None:
            pytest.skip('bash unavailable')
        if system == 'Windows':
            require_empty_array_expansion(bash)
        home = e2e_isolated_home['home']
        profile_dir = e2e_isolated_home['claude_dir'] / COMMAND
        seed_profile(profile_dir, prompt)
        monkeypatch.setattr(setup_environment.platform, 'system', lambda: system)
        result = create_launcher_script(profile_dir, COMMAND, prompt, mode, has_profile_mcp_servers=True)
        assert result is not None

        record = launch(
            [bash, str(result[1]), '--probe-arg'], home=home, stub_dir=home.parent / 'stub-bin',
            cwd=_start_directory(home, where),
        )

        assert_reaches_profile(record, profile_dir, prompt)
        _assert_sources(record, where, f'launch.sh ({system}, {where})')

    def test_a_caller_s_own_setting_sources_come_last(
        self, e2e_isolated_home: dict[str, Path], monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A --setting-sources the user passes follows the launcher's, so Claude Code takes the user's."""
        bash = find_bash()
        if bash is None:
            pytest.skip('bash unavailable')
        home = e2e_isolated_home['home']
        profile_dir = e2e_isolated_home['claude_dir'] / COMMAND
        seed_profile(profile_dir, None)
        monkeypatch.setattr(setup_environment.platform, 'system', lambda: 'Linux')
        result = create_launcher_script(profile_dir, COMMAND, None, 'replace', has_profile_mcp_servers=True)
        assert result is not None

        record = launch(
            [bash, str(result[1]), '--setting-sources', 'user,project', '--probe-arg'],
            home=home, stub_dir=home.parent / 'stub-bin', cwd=home,
        )

        assert _setting_sources(record) == ['user', 'user,project']

    @pytest.mark.skipif(not IS_WINDOWS, reason='letter case and short names are Windows path forms')
    def test_home_folder_in_every_windows_spelling(
        self, e2e_isolated_home: dict[str, Path], monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The home folder spelled in another letter case or as a short name still limits the settings."""
        bash = find_bash()
        if bash is None:
            pytest.skip('bash unavailable')
        home = e2e_isolated_home['home']
        profile_dir = e2e_isolated_home['claude_dir'] / COMMAND
        seed_profile(profile_dir, None)
        monkeypatch.setattr(setup_environment.platform, 'system', lambda: 'Windows')
        result = create_launcher_script(profile_dir, COMMAND, None, 'replace', has_profile_mcp_servers=True)
        assert result is not None

        for spelling in _windows_spellings(home):
            record = launch(
                [bash, str(result[1]), '--probe-arg'], home=home, stub_dir=home.parent / 'stub-bin', cwd=spelling,
            )
            _assert_sources(record, 'home', f'launch.sh started in {spelling}')


@pytest.mark.skipif(not IS_WINDOWS, reason='runs the generated entry points under cmd.exe and PowerShell')
class TestWindowsEntryPointsLimitSettingsInTheHomeFolder:
    """start.cmd, start.ps1 and every global wrapper limit the settings in the home folder only."""

    @pytest.mark.parametrize('where', START_DIRECTORIES)
    @pytest.mark.parametrize(('variant', 'prompt', 'mode'), LAUNCHER_VARIANTS)
    def test_every_entry_point_follows_the_start_directory(
        self,
        e2e_isolated_home: dict[str, Path],
        where: str,
        variant: str,
        prompt: str | None,
        mode: str,
    ) -> None:
        del variant
        powershell = find_powershell()
        bash = find_bash()
        if not WINDOWS_GIT_BASH.exists() or powershell is None or bash is None:
            pytest.skip('Git Bash at its standard location and PowerShell are required')
        home = e2e_isolated_home['home']
        local_bin = e2e_isolated_home['local_bin']
        profile_dir = e2e_isolated_home['claude_dir'] / COMMAND
        seed_profile(profile_dir, prompt)
        result = create_launcher_script(profile_dir, COMMAND, prompt, mode, has_profile_mcp_servers=True)
        assert result is not None
        start_ps1, launch_sh = result
        assert register_global_command(start_ps1, COMMAND, [ALIAS], launch_script_path=launch_sh)
        cwd = _start_directory(home, where)

        entry_points: list[tuple[str, list[str] | str]] = [
            ('start.cmd', cmd_command(profile_dir / 'start.cmd', '--probe-arg')),
            ('start.ps1', powershell_command(powershell, start_ps1, '--probe-arg')),
        ]
        for name in (COMMAND, ALIAS):
            entry_points.extend([
                (f'{name}.cmd', f'cmd.exe /d /c {name} --probe-arg'),
                (f'{name}.ps1', powershell_command(powershell, local_bin / f'{name}.ps1', '--probe-arg')),
                (name, [bash, str(local_bin / name), '--probe-arg']),
            ])

        for label, command in entry_points:
            record = launch(command, home=home, stub_dir=home.parent / 'stub-bin', extra_path=local_bin, cwd=cwd)
            assert_reaches_profile(record, profile_dir, prompt)
            _assert_sources(record, where, label)

    def test_cmd_and_powershell_entry_points_recognize_every_home_spelling(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """A cmd.exe or PowerShell started in the home folder under another spelling still limits the settings."""
        powershell = find_powershell()
        if not WINDOWS_GIT_BASH.exists() or powershell is None:
            pytest.skip('Git Bash at its standard location and PowerShell are required')
        home = e2e_isolated_home['home']
        profile_dir = e2e_isolated_home['claude_dir'] / COMMAND
        seed_profile(profile_dir, None)
        result = create_launcher_script(profile_dir, COMMAND, None, 'replace', has_profile_mcp_servers=True)
        assert result is not None

        for spelling in _windows_spellings(home):
            for label, command in (
                ('start.cmd', cmd_command(profile_dir / 'start.cmd', '--probe-arg')),
                ('start.ps1', powershell_command(powershell, result[0], '--probe-arg')),
            ):
                record = launch(command, home=home, stub_dir=home.parent / 'stub-bin', cwd=spelling)
                _assert_sources(record, 'home', f'{label} started in {spelling}')


@pytest.mark.skipif(IS_WINDOWS, reason='Unix registers wrappers as symlinks to launch.sh')
class TestUnixEntryPointsLimitSettingsInTheHomeFolder:
    """The ~/.local/bin symlinks of a profile limit the settings in the home folder only."""

    @pytest.mark.parametrize('where', START_DIRECTORIES)
    @pytest.mark.parametrize(('variant', 'prompt', 'mode'), LAUNCHER_VARIANTS)
    def test_command_and_alias_follow_the_start_directory(
        self,
        e2e_isolated_home: dict[str, Path],
        where: str,
        variant: str,
        prompt: str | None,
        mode: str,
    ) -> None:
        del variant
        if find_bash() is None:
            pytest.skip('bash unavailable')
        home = e2e_isolated_home['home']
        local_bin = e2e_isolated_home['local_bin']
        profile_dir = e2e_isolated_home['claude_dir'] / COMMAND
        seed_profile(profile_dir, prompt)
        result = create_launcher_script(profile_dir, COMMAND, prompt, mode, has_profile_mcp_servers=True)
        assert result is not None
        assert register_global_command(result[0], COMMAND, [ALIAS], launch_script_path=result[1])
        cwd = _start_directory(home, where)

        for name in (COMMAND, ALIAS):
            record = launch(
                [str(local_bin / name), '--probe-arg'], home=home, stub_dir=home.parent / 'stub-bin', cwd=cwd,
            )
            assert_reaches_profile(record, profile_dir, prompt)
            _assert_sources(record, where, name)


def test_golden_prompt_is_the_pinned_prompt_file() -> None:
    """The prompt file the variants use is the one the default renderings pin."""
    assert LAUNCHER_VARIANTS[1].values[1] == GOLDEN_PROMPT
