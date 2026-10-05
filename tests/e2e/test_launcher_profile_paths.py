"""E2E tests for the profile directory every launcher and wrapper names.

Setup writes a profile's launchers into the profile directory and its global
wrappers into ``~/.local/bin``. Every path those scripts read is spelled from
the profile directory: home-relative when it lies below the home directory,
absolute otherwise. These tests pin the exact bytes generated for the default
directory ``~/.claude/<cmd>``, and run the scripts generated for relocated
profile directories under their real interpreters with a stub ``claude``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts import setup_environment
from scripts.setup_environment import create_launcher_script
from scripts.setup_environment import register_global_command
from tests.e2e.expected.launchers import GOLDEN_ALIAS
from tests.e2e.expected.launchers import GOLDEN_COMMAND
from tests.e2e.expected.launchers import GOLDEN_PROMPT
from tests.e2e.launcher_support import LAUNCHER_VARIANTS
from tests.e2e.launcher_support import WINDOWS_GIT_BASH
from tests.e2e.launcher_support import assert_default_rendering
from tests.e2e.launcher_support import assert_reaches_profile
from tests.e2e.launcher_support import cmd_command
from tests.e2e.launcher_support import expected_spelling
from tests.e2e.launcher_support import find_bash
from tests.e2e.launcher_support import find_powershell
from tests.e2e.launcher_support import launch
from tests.e2e.launcher_support import powershell_command
from tests.e2e.launcher_support import require_empty_array_expansion
from tests.e2e.launcher_support import seed_profile
from tests.e2e.launcher_support import write_marking_loaders
from tests.e2e.validators import validate_launcher_profile_spelling

# Relocated profile directories: (id, location relative to 'home' or 'tmp').
RELOCATED_LAYOUTS = [
    pytest.param('home', ('.claude-work',), id='direct-child-of-home'),
    pytest.param('home', ('profiles', 'work'), id='below-home'),
    pytest.param('home', ('my profiles (x)', 'work'), id='below-home-spaced'),
    pytest.param('tmp', ('elsewhere', 'work'), id='outside-home'),
    pytest.param('tmp', ('My Profiles (work)', 'work'), id='outside-home-spaced'),
]


def _profile_dir(paths: dict[str, Path], anchor: str, parts: tuple[str, ...]) -> Path:
    """Return a relocated profile directory below home or beside it.

    Args:
        paths: The e2e_isolated_home paths.
        anchor: 'home' for a directory below home, 'tmp' for one outside it.
        parts: Path components below the anchor.

    Returns:
        The profile directory.
    """
    base = paths['home'] if anchor == 'home' else paths['home'].parent
    return base.joinpath(*parts)


def _mock_windows_registration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep register_global_command() away from the real user PATH."""
    monkeypatch.setattr(
        setup_environment, 'add_directory_to_windows_path', lambda directory: (True, f'[mock] {directory}'),
    )


class TestDefaultLayoutRendering:
    """A profile in ~/.claude/<cmd> gets exactly the established launcher text.

    platform.system() is the only platform detection create_launcher_script()
    and register_global_command() use, so mocking it renders the Windows and
    the Unix file sets on every CI runner.
    """

    @pytest.mark.parametrize(('variant', 'prompt', 'mode'), LAUNCHER_VARIANTS)
    def test_windows_launchers_match_default_rendering(
        self,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        variant: str,
        prompt: str | None,
        mode: str,
    ) -> None:
        """start.ps1, start.cmd and launch.sh match the default rendering byte for byte."""
        profile_dir = e2e_isolated_home['claude_dir'] / GOLDEN_COMMAND
        monkeypatch.setattr(setup_environment.platform, 'system', lambda: 'Windows')

        result = create_launcher_script(profile_dir, GOLDEN_COMMAND, prompt, mode, has_profile_mcp_servers=True)

        assert result == (profile_dir / 'start.ps1', profile_dir / 'launch.sh')
        assert_default_rendering(profile_dir / 'start.ps1', 'windows/start.ps1', lf_pinned=False)
        assert_default_rendering(profile_dir / 'start.cmd', 'windows/start.cmd', lf_pinned=False)
        assert_default_rendering(profile_dir / 'launch.sh', f'windows/launch.sh/{variant}', lf_pinned=True)

    @pytest.mark.parametrize('system', ['Linux', 'Darwin'])
    @pytest.mark.parametrize(('variant', 'prompt', 'mode'), LAUNCHER_VARIANTS)
    def test_unix_launcher_matches_default_rendering(
        self,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        system: str,
        variant: str,
        prompt: str | None,
        mode: str,
    ) -> None:
        """launch.sh matches the default rendering byte for byte on Linux and macOS."""
        profile_dir = e2e_isolated_home['claude_dir'] / GOLDEN_COMMAND
        monkeypatch.setattr(setup_environment.platform, 'system', lambda: system)

        result = create_launcher_script(profile_dir, GOLDEN_COMMAND, prompt, mode, has_profile_mcp_servers=True)

        assert result == (profile_dir / 'launch.sh', profile_dir / 'launch.sh')
        assert_default_rendering(profile_dir / 'launch.sh', f'unix/launch.sh/{variant}', lf_pinned=False)

    def test_windows_wrappers_match_default_rendering(
        self,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The CMD, PowerShell and Git Bash wrappers of a command and its alias match byte for byte."""
        profile_dir = e2e_isolated_home['claude_dir'] / GOLDEN_COMMAND
        local_bin = e2e_isolated_home['local_bin']
        monkeypatch.setattr(setup_environment.platform, 'system', lambda: 'Windows')
        _mock_windows_registration(monkeypatch)
        result = create_launcher_script(profile_dir, GOLDEN_COMMAND, None, 'replace', has_profile_mcp_servers=False)
        assert result is not None
        start_ps1, launch_sh = result

        assert register_global_command(start_ps1, GOLDEN_COMMAND, [GOLDEN_ALIAS], launch_script_path=launch_sh)

        for name in (GOLDEN_COMMAND, GOLDEN_ALIAS):
            assert_default_rendering(local_bin / f'{name}.cmd', f'windows-wrappers/{name}.cmd', lf_pinned=False)
            assert_default_rendering(
                local_bin / f'{name}.ps1', f'windows-wrappers/{name}.ps1', lf_pinned=False, launcher_path=start_ps1,
            )
            assert_default_rendering(local_bin / name, f'windows-wrappers/{name}', lf_pinned=True)


class TestMcpConfigPathWithSpaces:
    """A profile MCP config path containing spaces reaches claude as one argument.

    A home directory such as ``C:/Users/First Last`` puts spaces into every
    profile path; --mcp-config must still receive the whole mcp.json path.
    """

    @pytest.mark.parametrize('system', ['Windows', 'Linux'])
    @pytest.mark.parametrize(('variant', 'prompt', 'mode'), LAUNCHER_VARIANTS)
    def test_spaced_mcp_config_path_is_one_argument(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        system: str,
        variant: str,
        prompt: str | None,
        mode: str,
    ) -> None:
        """launch.sh passes --strict-mcp-config and the full spaced mcp.json path."""
        del variant
        bash = find_bash()
        if bash is None:
            pytest.skip('bash unavailable')
        if system == 'Windows':
            require_empty_array_expansion(bash)
        home = tmp_path / 'user home (x)'
        profile_dir = home / '.claude' / GOLDEN_COMMAND
        seed_profile(profile_dir, prompt)
        write_marking_loaders(profile_dir)
        monkeypatch.setattr(Path, 'home', lambda: home)
        monkeypatch.setattr(setup_environment.platform, 'system', lambda: system)
        result = create_launcher_script(profile_dir, GOLDEN_COMMAND, prompt, mode, has_profile_mcp_servers=True)
        assert result is not None

        record = launch([bash, str(result[1]), '--probe-arg'], home=home, stub_dir=tmp_path / 'stub-bin')

        assert_reaches_profile(record, profile_dir, prompt)
        assert record.loader_marks == 'sh;'


class TestRelocatedProfileLaunchers:
    """Launchers of a relocated profile directory read every file from it.

    resolve_artifact_base_dir() lets user-settings.env move an isolated
    profile out of ~/.claude/<cmd>; setup writes the profile's files there,
    so the launchers must export and read that directory.
    """

    @pytest.mark.parametrize(('anchor', 'parts'), RELOCATED_LAYOUTS)
    @pytest.mark.parametrize('system', ['Windows', 'Linux', 'Darwin'])
    @pytest.mark.parametrize(('variant', 'prompt', 'mode'), LAUNCHER_VARIANTS)
    def test_launch_sh_reaches_relocated_profile(
        self,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        anchor: str,
        parts: tuple[str, ...],
        system: str,
        variant: str,
        prompt: str | None,
        mode: str,
    ) -> None:
        """launch.sh exports the relocated directory and reads every file from it."""
        del variant
        bash = find_bash()
        if bash is None:
            pytest.skip('bash unavailable')
        if system == 'Windows':
            require_empty_array_expansion(bash)
        home = e2e_isolated_home['home']
        profile_dir = _profile_dir(e2e_isolated_home, anchor, parts)
        seed_profile(profile_dir, prompt)
        write_marking_loaders(profile_dir)
        monkeypatch.setattr(setup_environment.platform, 'system', lambda: system)

        result = create_launcher_script(profile_dir, 'relo-cmd', prompt, mode, has_profile_mcp_servers=True)
        assert result is not None

        spelling = expected_spelling(profile_dir, home)
        errors = validate_launcher_profile_spelling(
            profile_dir,
            posix_dir=spelling.posix_dir,
            cmd_dir=spelling.cmd_dir,
            powershell_parent=spelling.powershell_parent,
            windows_launchers=system == 'Windows',
        )
        assert not errors, '\n'.join(errors)

        record = launch([bash, str(result[1]), '--probe-arg'], home=home, stub_dir=home.parent / 'stub-bin')

        assert_reaches_profile(record, profile_dir, prompt)
        assert record.loader_marks == 'sh;'

    @pytest.mark.parametrize(('anchor', 'parts'), RELOCATED_LAYOUTS)
    def test_windows_wrappers_name_relocated_profile(
        self,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        anchor: str,
        parts: tuple[str, ...],
    ) -> None:
        """Every Windows wrapper of a command and its alias names the relocated directory."""
        profile_dir = _profile_dir(e2e_isolated_home, anchor, parts)
        local_bin = e2e_isolated_home['local_bin']
        monkeypatch.setattr(setup_environment.platform, 'system', lambda: 'Windows')
        _mock_windows_registration(monkeypatch)
        result = create_launcher_script(profile_dir, 'relo-cmd', None, 'replace', has_profile_mcp_servers=False)
        assert result is not None

        assert register_global_command(result[0], 'relo-cmd', ['relo-alias'], launch_script_path=result[1])

        spelling = expected_spelling(profile_dir, e2e_isolated_home['home'])
        errors = validate_launcher_profile_spelling(
            profile_dir,
            posix_dir=spelling.posix_dir,
            cmd_dir=spelling.cmd_dir,
            powershell_parent=spelling.powershell_parent,
            windows_launchers=True,
            local_bin=local_bin,
            wrapper_names=('relo-cmd', 'relo-alias'),
        )
        assert not errors, '\n'.join(errors)


@pytest.mark.skipif(sys.platform != 'win32', reason='runs the generated scripts under cmd.exe and Windows PowerShell')
class TestRelocatedProfileWindowsEntryPoints:
    """Every Windows entry point of a relocated profile starts claude with that profile.

    Each entry point is run the way a user runs it: the CMD and PowerShell
    launchers and wrappers hand over to launch.sh through Git Bash, and
    launch.sh alone sources env.sh. The marking env.cmd and env.ps1 beside it
    stay unsourced, so the session carries the ``sh;`` mark and no other.
    """

    @pytest.mark.parametrize(('anchor', 'parts'), RELOCATED_LAYOUTS)
    def test_every_entry_point_reaches_relocated_profile(
        self,
        e2e_isolated_home: dict[str, Path],
        anchor: str,
        parts: tuple[str, ...],
    ) -> None:
        """start.cmd, start.ps1 and every wrapper export the relocated directory and use its files."""
        powershell = find_powershell()
        bash = find_bash()
        if not WINDOWS_GIT_BASH.exists() or powershell is None or bash is None:
            pytest.skip('Git Bash at its standard location and PowerShell are required')
        home = e2e_isolated_home['home']
        local_bin = e2e_isolated_home['local_bin']
        profile_dir = _profile_dir(e2e_isolated_home, anchor, parts)
        seed_profile(profile_dir, GOLDEN_PROMPT)
        write_marking_loaders(profile_dir)
        result = create_launcher_script(profile_dir, 'relo-cmd', GOLDEN_PROMPT, 'replace', has_profile_mcp_servers=True)
        assert result is not None
        start_ps1, _ = result
        assert register_global_command(start_ps1, 'relo-cmd', ['relo-alias'], launch_script_path=result[1])
        stub_dir = home.parent / 'stub-bin'

        entry_points: list[tuple[str, list[str] | str]] = [
            ('start.cmd', cmd_command(profile_dir / 'start.cmd', '--probe-arg')),
            ('start.ps1', powershell_command(powershell, start_ps1, '--probe-arg')),
        ]
        for name in ('relo-cmd', 'relo-alias'):
            entry_points.extend([
                (f'{name}.cmd', f'cmd.exe /d /c {name} --probe-arg'),
                (f'{name}.ps1', powershell_command(powershell, local_bin / f'{name}.ps1', '--probe-arg')),
                (name, [bash, str(local_bin / name), '--probe-arg']),
            ])

        for label, command in entry_points:
            record = launch(command, home=home, stub_dir=stub_dir, extra_path=local_bin)
            assert_reaches_profile(record, profile_dir, GOLDEN_PROMPT)
            assert record.loader_marks == 'sh;', f'{label}: loader marks {record.loader_marks!r}'


@pytest.mark.skipif(sys.platform == 'win32', reason='Unix registers wrappers as symlinks to launch.sh')
class TestRelocatedProfileUnixEntryPoints:
    """The ~/.local/bin symlinks of a relocated profile start claude with that profile."""

    @pytest.mark.parametrize(('anchor', 'parts'), RELOCATED_LAYOUTS)
    def test_command_and_alias_reach_relocated_profile(
        self,
        e2e_isolated_home: dict[str, Path],
        anchor: str,
        parts: tuple[str, ...],
    ) -> None:
        """Running the command or its alias exports the relocated directory and uses its files."""
        if find_bash() is None:
            pytest.skip('bash unavailable')
        home = e2e_isolated_home['home']
        local_bin = e2e_isolated_home['local_bin']
        profile_dir = _profile_dir(e2e_isolated_home, anchor, parts)
        seed_profile(profile_dir, GOLDEN_PROMPT)
        write_marking_loaders(profile_dir)
        result = create_launcher_script(profile_dir, 'relo-cmd', GOLDEN_PROMPT, 'replace', has_profile_mcp_servers=True)
        assert result is not None
        assert register_global_command(result[0], 'relo-cmd', ['relo-alias'], launch_script_path=result[1])

        for name in ('relo-cmd', 'relo-alias'):
            assert (local_bin / name).resolve() == (profile_dir / 'launch.sh').resolve()
            record = launch([str(local_bin / name), '--probe-arg'], home=home, stub_dir=home.parent / 'stub-bin')
            assert_reaches_profile(record, profile_dir, GOLDEN_PROMPT)
            assert record.loader_marks == 'sh;'


class TestRelocatedProfileScriptSyntax:
    """Generated scripts for every layout parse under their real interpreters.

    Execution covers the branch the stub's version selects; the parsers cover
    every other branch of every variant.
    """

    @pytest.mark.parametrize(('anchor', 'parts'), RELOCATED_LAYOUTS)
    @pytest.mark.parametrize('system', ['Windows', 'Linux'])
    @pytest.mark.parametrize(('variant', 'prompt', 'mode'), LAUNCHER_VARIANTS)
    def test_launch_sh_passes_bash_syntax_check(
        self,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        anchor: str,
        parts: tuple[str, ...],
        system: str,
        variant: str,
        prompt: str | None,
        mode: str,
    ) -> None:
        """bash -n accepts launch.sh in every layout and variant."""
        del variant
        bash = find_bash()
        if bash is None:
            pytest.skip('bash unavailable')
        profile_dir = _profile_dir(e2e_isolated_home, anchor, parts)
        monkeypatch.setattr(setup_environment.platform, 'system', lambda: system)
        result = create_launcher_script(profile_dir, 'relo-cmd', prompt, mode, has_profile_mcp_servers=True)
        assert result is not None

        completed = subprocess.run(
            [bash, '-n', str(result[1])], capture_output=True, text=True, check=False, timeout=60,
        )

        assert completed.returncode == 0, f'bash -n rejected launch.sh:\n{completed.stderr}'

    @pytest.mark.parametrize(('anchor', 'parts'), RELOCATED_LAYOUTS)
    def test_powershell_scripts_parse_without_errors(
        self,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        anchor: str,
        parts: tuple[str, ...],
    ) -> None:
        """The PowerShell parser accepts start.ps1 and both PowerShell wrappers."""
        powershell = find_powershell()
        if powershell is None:
            pytest.skip('PowerShell unavailable')
        profile_dir = _profile_dir(e2e_isolated_home, anchor, parts)
        local_bin = e2e_isolated_home['local_bin']
        monkeypatch.setattr(setup_environment.platform, 'system', lambda: 'Windows')
        _mock_windows_registration(monkeypatch)
        result = create_launcher_script(profile_dir, 'relo-cmd', None, 'replace', has_profile_mcp_servers=False)
        assert result is not None
        assert register_global_command(result[0], 'relo-cmd', ['relo-alias'], launch_script_path=result[1])

        for script in (result[0], local_bin / 'relo-cmd.ps1', local_bin / 'relo-alias.ps1'):
            literal = str(script).replace("'", "''")
            parse_command = (
                '$t=$null;$e=$null;'
                f"[System.Management.Automation.Language.Parser]::ParseFile('{literal}',[ref]$t,[ref]$e)|Out-Null;"
                'if($e.Count -gt 0){$e|ForEach-Object{Write-Error $_.Message};exit 1}'
            )
            completed = subprocess.run(
                [powershell, '-NoProfile', '-Command', parse_command],
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
            )
            assert completed.returncode == 0, f'PowerShell parser rejected {script.name}:\n{completed.stderr}'
