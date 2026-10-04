"""E2E tests for the working directory a generated launcher starts Claude Code in.

Claude Code tells the home folder's ``.claude``, the base profile, apart from
a project's ``.claude`` by spelling, and Windows spells a home whose account
name is longer than eight characters short in %TEMP% and %TMP%
(``C:\\Users\\CHRIST~1``), so a session started under such a path would load
the base profile's skills, agents and commands as a project's. Every Windows
``launch.sh`` therefore starts Claude Code in the long spelling of the
working directory it was started in, whichever entry point started it and
however the shell spelled the directory; the Linux and macOS launchers leave
the working directory alone, because their directories have one spelling.

The stub claude records the working directory it starts in. The tests start
the launchers from a project below the isolated home, spelled long, with the
home short, with every component short and in lowercase; the home lies below
pytest's temporary directory, whose components are longer than eight
characters, so Windows gives it a differing short spelling wherever the volume
creates 8.3 names, and the short-spelling tests skip with the reason where it
does not.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from scripts import setup_environment
from scripts.setup_environment import create_launcher_script
from scripts.setup_environment import register_global_command
from tests.e2e.base_home_support import short_spelling
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
from tests.e2e.launcher_support import same_path
from tests.e2e.launcher_support import seed_profile
from tests.e2e.validators import validate_launcher_starts_in_the_long_working_directory

COMMAND = 'spell-cmd'
ALIAS = 'spell-alias'
IS_WINDOWS = sys.platform == 'win32'
# How the project below the home is spelled when a launch starts there: as
# given, with the home short and the rest long (the %TEMP% shape), with every
# component short, and in lowercase
SPELLINGS = ['long', 'short-home', 'short', 'lowercase']


def _project(home: Path) -> Path:
    """Return the project below ``home`` the launches start in, creating it."""
    project = home / 'work' / 'project'
    project.mkdir(parents=True, exist_ok=True)
    return project


def _spelled(home: Path, project: Path, spelling: str) -> Path:
    """Return ``project`` spelled as ``spelling`` asks, or skip when the volume creates no 8.3 names."""
    if spelling == 'long':
        return project
    if spelling == 'lowercase':
        return Path(str(project).lower())
    short_home = short_spelling(home)
    if short_home is None:
        pytest.skip('the volume creates no 8.3 names for the home folder')
    if spelling == 'short-home':
        return short_home / project.relative_to(home)
    short_project = short_spelling(project)
    assert short_project is not None
    return short_project


def _assert_long_spelling(record: LaunchRecord, project: Path, label: str) -> None:
    """Assert that the stub started in ``project`` spelled without any 8.3 short name."""
    assert '~' not in record.cwd, f'{label} started claude in {record.cwd}'
    assert os.path.normcase(record.cwd) == os.path.normcase(str(project)), f'{label} started claude in {record.cwd}'


@pytest.mark.skipif(not IS_WINDOWS, reason='8.3 short names are a Windows path form')
class TestWindowsLaunchShStartsInTheLongSpelling:
    """launch.sh of every variant, run under bash, starts claude in the long spelling of the working directory."""

    @pytest.mark.parametrize('spelling', SPELLINGS)
    @pytest.mark.parametrize(('variant', 'prompt', 'mode'), LAUNCHER_VARIANTS)
    def test_launch_sh_starts_claude_in_the_long_spelling(
        self,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        spelling: str,
        variant: str,
        prompt: str | None,
        mode: str,
    ) -> None:
        del variant
        bash = find_bash()
        if bash is None:
            pytest.skip('bash unavailable')
        require_empty_array_expansion(bash)
        home = e2e_isolated_home['home']
        profile_dir = e2e_isolated_home['claude_dir'] / COMMAND
        seed_profile(profile_dir, prompt)
        monkeypatch.setattr(setup_environment.platform, 'system', lambda: 'Windows')
        result = create_launcher_script(profile_dir, COMMAND, prompt, mode, has_profile_mcp_servers=True)
        assert result is not None
        assert validate_launcher_starts_in_the_long_working_directory(result[1], windows=True) == []
        project = _project(home)

        record = launch(
            [bash, str(result[1]), '--probe-arg'], home=home, stub_dir=home.parent / 'stub-bin',
            cwd=_spelled(home, project, spelling),
        )

        assert_reaches_profile(record, profile_dir, prompt)
        _assert_long_spelling(record, project, f'launch.sh from the project spelled {spelling}')

    def test_every_entry_point_starts_claude_in_the_long_spelling(self, e2e_isolated_home: dict[str, Path]) -> None:
        """start.cmd, start.ps1 and every global wrapper, started under the short home, reach the long spelling."""
        powershell = find_powershell()
        bash = find_bash()
        if not WINDOWS_GIT_BASH.exists() or powershell is None or bash is None:
            pytest.skip('Git Bash at its standard location and PowerShell are required')
        home = e2e_isolated_home['home']
        local_bin = e2e_isolated_home['local_bin']
        profile_dir = e2e_isolated_home['claude_dir'] / COMMAND
        seed_profile(profile_dir, None)
        result = create_launcher_script(profile_dir, COMMAND, None, 'replace', has_profile_mcp_servers=True)
        assert result is not None
        start_ps1, launch_sh = result
        assert register_global_command(start_ps1, COMMAND, [ALIAS], launch_script_path=launch_sh)
        project = _project(home)
        cwd = _spelled(home, project, 'short-home')

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
            assert_reaches_profile(record, profile_dir, None)
            _assert_long_spelling(record, project, f'{label} from {cwd}')


class TestUnixLaunchShLeavesTheWorkingDirectory:
    """The Linux and macOS launch.sh change no spelling and start claude where they were started."""

    @pytest.mark.parametrize('system', ['Linux', 'Darwin'])
    @pytest.mark.parametrize(('variant', 'prompt', 'mode'), LAUNCHER_VARIANTS)
    def test_launch_sh_starts_claude_where_it_was_started(
        self,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        system: str,
        variant: str,
        prompt: str | None,
        mode: str,
    ) -> None:
        del variant
        bash = find_bash()
        if bash is None:
            pytest.skip('bash unavailable')
        home = e2e_isolated_home['home']
        profile_dir = e2e_isolated_home['claude_dir'] / COMMAND
        seed_profile(profile_dir, prompt)
        monkeypatch.setattr(setup_environment.platform, 'system', lambda: system)
        result = create_launcher_script(profile_dir, COMMAND, prompt, mode, has_profile_mcp_servers=True)
        assert result is not None
        assert validate_launcher_starts_in_the_long_working_directory(result[1], windows=False) == []
        project = _project(home)

        record = launch([bash, str(result[1]), '--probe-arg'], home=home, stub_dir=home.parent / 'stub-bin', cwd=project)

        assert_reaches_profile(record, profile_dir, prompt)
        assert same_path(record.cwd, project), record.cwd
