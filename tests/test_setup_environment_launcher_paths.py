"""Unit tests for how generated launchers and wrappers spell the profile directory."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from scripts import setup_environment
from scripts.setup_environment import _escape_bash_double_quoted
from scripts.setup_environment import _escape_cmd_set_value
from scripts.setup_environment import _escape_powershell_double_quoted
from scripts.setup_environment import _spell_profile_dir
from scripts.setup_environment import create_launcher_script
from scripts.setup_environment import register_global_command


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point get_real_user_home() at an isolated home directory."""
    home_dir = tmp_path / 'home'
    home_dir.mkdir()
    monkeypatch.setattr(Path, 'home', lambda: home_dir)
    monkeypatch.delenv('SUDO_USER', raising=False)
    return home_dir


class TestSpellProfileDir:
    """_spell_profile_dir() spells a profile home-relative below home, absolute elsewhere."""

    def test_default_profile_directory(self, home: Path) -> None:
        """~/.claude/<cmd> keeps the established $HOME, %USERPROFILE% and Join-Path forms."""
        spelling = _spell_profile_dir(home / '.claude' / 'my-cmd')

        assert spelling.posix == '$HOME/.claude/my-cmd'
        assert spelling.cmd == '%USERPROFILE%\\.claude\\my-cmd'
        assert spelling.powershell_parent == 'Join-Path $env:USERPROFILE ".claude"'
        assert spelling.powershell_leaf == 'my-cmd'

    def test_directory_below_home_outside_claude(self, home: Path) -> None:
        """A directory below home stays home-relative, with every component kept."""
        spelling = _spell_profile_dir(home / 'profiles' / 'team a' / 'work')

        assert spelling.posix == '$HOME/profiles/team a/work'
        assert spelling.cmd == '%USERPROFILE%\\profiles\\team a\\work'
        assert spelling.powershell_parent == 'Join-Path $env:USERPROFILE "profiles\\team a"'
        assert spelling.powershell_leaf == 'work'

    def test_direct_child_of_home(self, home: Path) -> None:
        """A profile directly in home has the home itself as its PowerShell parent."""
        spelling = _spell_profile_dir(home / 'work')

        assert spelling.posix == '$HOME/work'
        assert spelling.cmd == '%USERPROFILE%\\work'
        assert spelling.powershell_parent == '$env:USERPROFILE'
        assert spelling.powershell_leaf == 'work'

    def test_directory_outside_home_is_absolute(self, home: Path) -> None:
        """A directory outside home is spelled absolute in every shell."""
        profile_dir = home.parent / 'My Profiles (work)' / 'work'

        spelling = _spell_profile_dir(profile_dir)

        assert spelling.posix == profile_dir.as_posix()
        assert spelling.cmd == str(profile_dir).replace('/', '\\')
        assert spelling.powershell_parent == '"' + str(profile_dir.parent).replace('/', '\\') + '"'
        assert spelling.powershell_leaf == 'work'

    def test_sibling_with_home_name_as_prefix_is_outside_home(self, home: Path) -> None:
        """A directory whose name only starts with the home's name is not below home."""
        profile_dir = home.parent / f'{home.name}-other' / 'work'

        spelling = _spell_profile_dir(profile_dir)

        assert spelling.posix == profile_dir.as_posix()
        assert '%USERPROFILE%' not in spelling.cmd

    def test_relative_directory_is_spelled_from_the_working_directory(
        self, home: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A relative profile directory names the absolute directory setup writes into."""
        monkeypatch.chdir(home.parent)

        spelling = _spell_profile_dir(Path('relative-profile'))

        assert spelling.posix == Path(os.path.abspath('relative-profile')).as_posix()

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows paths compare case-insensitively')
    def test_windows_home_comparison_ignores_case(self, home: Path) -> None:
        """A profile path typed in another case still counts as below home on Windows."""
        profile_dir = Path(str(home).upper()) / 'profiles' / 'work'

        spelling = _spell_profile_dir(profile_dir)

        assert spelling.posix == '$HOME/profiles/work'
        assert spelling.cmd == '%USERPROFILE%\\profiles\\work'


class TestEscapes:
    """Each shell's escape keeps a literal path literal inside its quotes."""

    def test_bash_double_quoted(self) -> None:
        """Backslash, double quote, dollar and backtick are escaped; spaces stay."""
        assert _escape_bash_double_quoted('a b\\c"d$e`f') == 'a b\\\\c\\"d\\$e\\`f'

    def test_cmd_set_value(self) -> None:
        """Percent signs are doubled; spaces and parentheses stay."""
        assert _escape_cmd_set_value('My Profiles (work)\\100%') == 'My Profiles (work)\\100%%'

    def test_powershell_double_quoted(self) -> None:
        """Backtick, dollar and double quote get a backtick; backslashes stay."""
        assert _escape_powershell_double_quoted('C:\\a $b`c"d') == 'C:\\a `$b``c`"d'


class TestLauncherRendering:
    """create_launcher_script() and register_global_command() render from the profile directory."""

    def test_windows_launchers_name_relocated_directory(self, home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """start.ps1, start.cmd and launch.sh name the relocated directory and nothing under ~/.claude."""
        monkeypatch.setattr(setup_environment.platform, 'system', lambda: 'Windows')
        profile_dir = home / 'profiles' / 'work'

        create_launcher_script(profile_dir, 'my-cmd', 'prompt.md', 'replace', has_profile_mcp_servers=True)

        launch_sh = (profile_dir / 'launch.sh').read_text(encoding='utf-8')
        assert 'export CLAUDE_CONFIG_DIR="$HOME/profiles/work"' in launch_sh
        assert 'PROMPT_PATH="$HOME/profiles/work/prompts/prompt.md"' in launch_sh
        assert '$HOME/.claude' not in launch_sh
        assert 'ENV_FILE="$HOME/profiles/work/env.sh"' in launch_sh
        start_cmd = (profile_dir / 'start.cmd').read_text(encoding='utf-8')
        assert 'set "SCRIPT_WIN=%USERPROFILE%\\profiles\\work\\launch.sh"' in start_cmd
        start_ps1 = (profile_dir / 'start.ps1').read_text(encoding='utf-8')
        assert '$claudeUserDir = Join-Path $env:USERPROFILE "profiles"\n' in start_ps1
        assert '(Join-Path $claudeUserDir "work") "launch.sh"' in start_ps1

    def test_windows_entry_points_apply_no_loader_and_scope_their_variables(
        self, home: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """start.cmd, start.ps1 and the .cmd wrappers reference no loader; launch.sh alone sources env.sh.

        A batch file run from a cmd.exe prompt executes in that shell and
        $env: is process-wide in PowerShell, so a loader applied there would
        outlive the session in the calling shell; the .cmd files also keep
        their own variables behind setlocal.
        """
        monkeypatch.setattr(setup_environment.platform, 'system', lambda: 'Windows')
        monkeypatch.setattr(setup_environment, 'add_directory_to_windows_path', lambda directory: (True, str(directory)))
        profile_dir = home / 'profiles' / 'work'
        result = create_launcher_script(profile_dir, 'my-cmd', None, 'replace', has_profile_mcp_servers=False)
        assert result is not None
        assert register_global_command(result[0], 'my-cmd', ['my-alias'], launch_script_path=result[1])
        local_bin = home / '.local' / 'bin'

        launch_sh = (profile_dir / 'launch.sh').read_text(encoding='utf-8')
        assert 'ENV_FILE="$HOME/profiles/work/env.sh"\n[ -f "$ENV_FILE" ] && . "$ENV_FILE"' in launch_sh
        for batch in (profile_dir / 'start.cmd', local_bin / 'my-cmd.cmd', local_bin / 'my-alias.cmd'):
            content = batch.read_text(encoding='utf-8')
            assert content.startswith('@echo off\nsetlocal\n'), f'{batch.name} does not scope its variables'
            assert 'env.cmd' not in content, f'{batch.name} applies the loader to the calling shell'
            assert 'ENV_FILE' not in content, batch.name
        start_ps1 = (profile_dir / 'start.ps1').read_text(encoding='utf-8')
        assert 'env.ps1' not in start_ps1, 'start.ps1 applies the loader to the calling shell'
        assert '$envFile' not in start_ps1

    def test_unix_launcher_names_directory_outside_home(self, home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """The Unix launch.sh exports an absolute directory outside home."""
        monkeypatch.setattr(setup_environment.platform, 'system', lambda: 'Linux')
        profile_dir = home.parent / 'elsewhere' / 'work'

        create_launcher_script(profile_dir, 'my-cmd', None, 'replace', has_profile_mcp_servers=False)

        launch_sh = (profile_dir / 'launch.sh').read_text(encoding='utf-8')
        assert f'export CLAUDE_CONFIG_DIR="{profile_dir.as_posix()}"' in launch_sh
        assert f'SETTINGS_PATH="{profile_dir.as_posix()}/config.json"' in launch_sh
        assert '$HOME/' not in launch_sh

    def test_windows_wrappers_default_to_launch_sh_beside_launcher(
        self, home: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Without launch_script_path, the wrappers run the launch.sh beside start.ps1."""
        monkeypatch.setattr(setup_environment.platform, 'system', lambda: 'Windows')
        monkeypatch.setattr(setup_environment, 'add_directory_to_windows_path', lambda directory: (True, str(directory)))
        profile_dir = home / 'profiles' / 'work'
        result = create_launcher_script(profile_dir, 'my-cmd', None, 'replace', has_profile_mcp_servers=False)
        assert result is not None

        assert register_global_command(result[0], 'my-cmd')

        local_bin = home / '.local' / 'bin'
        cmd_wrapper = (local_bin / 'my-cmd.cmd').read_text(encoding='utf-8')
        assert 'set "SCRIPT_WIN=%USERPROFILE%\\profiles\\work\\launch.sh"' in cmd_wrapper
        bash_wrapper = (local_bin / 'my-cmd').read_text(encoding='utf-8')
        assert 'exec "$HOME/profiles/work/launch.sh" "$@"' in bash_wrapper
        ps1_wrapper = (local_bin / 'my-cmd.ps1').read_text(encoding='utf-8')
        assert f'& "{profile_dir / "start.ps1"}" @args' in ps1_wrapper
