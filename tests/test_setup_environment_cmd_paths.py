"""Tests for the Windows spelling of the paths setup writes into apiKeyHelper and awsCredentialExport.

Claude Code runs both settings values through the shell, which is cmd.exe
on Windows (``cmd.exe /d /s /c "<value>"``). cmd.exe resolves no tilde, so
setup expands every ``~`` path and writes it in double quotes; a profile
directory outside the home, which the re-rooting of an isolated run spells
as an absolute path, is double-quoted the same way. Unquoted, a path under a
home folder whose name contains a space reaches the program as two
arguments. A path the author already quoted keeps its quotes and gains
none, and Linux and macOS keep the value exactly as authored. The other
callers of expand_tildes_in_command() keep its unquoted output.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

import setup_environment
from setup_environment import ConfigHomeReroot
from setup_environment import RerootedPath

PROFILE = 'p1'
HELPER = 'uv run --no-project --python 3.12'


@pytest.fixture
def spaced_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point every home lookup at a home folder whose name contains a space."""
    home = tmp_path / 'Test User'
    (home / '.claude').mkdir(parents=True)
    monkeypatch.setattr(Path, 'home', lambda: home)
    monkeypatch.setattr(setup_environment, 'get_real_user_home', lambda: home)
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('USERPROFILE', str(home))
    return home


@pytest.fixture
def on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the code under test as it runs on Windows."""
    monkeypatch.setattr(setup_environment.sys, 'platform', 'win32')


def _expanded(path: str) -> str:
    """Spell a tilde path the way the expansion spells it on this machine."""
    return setup_environment.normalize_tilde_path(path)


def _quoted(path: str) -> str:
    """Spell a tilde path the way the Windows settings write spells it: expanded and double-quoted."""
    return f'"{_expanded(path)}"'


@pytest.mark.parametrize(
    ('command', 'index', 'inside'),
    [
        ('"a b" c', 0, False),
        ('"a b" c', 1, True),
        ('"a b" c', 4, True),
        ('"a b" c', 5, False),
        ('x "~/a" y', 3, True),
        ('x ~/a', 2, False),
    ],
)
def test_the_quote_state_counts_the_quotes_before_the_position(command: str, index: int, inside: bool) -> None:
    """A position is inside double quotes when an odd number of quotes precedes it; a quote at it does not count."""
    assert setup_environment._inside_double_quotes(command, index) is inside


@pytest.mark.usefixtures('spaced_home')
class TestExpandTildesForCmd:
    """Each expanded tilde path becomes one double-quoted cmd.exe argument."""

    def test_a_path_under_a_spaced_home_is_quoted(self, spaced_home: Path) -> None:
        """The helper shape that cmd.exe would split at the space reaches it as one argument."""
        result = setup_environment.expand_tildes_for_cmd(f'{HELPER} ~/.claude/scripts/helper.py')

        assert result == f'{HELPER} {_quoted("~/.claude/scripts/helper.py")}'
        assert ' ' in str(spaced_home)
        assert str(spaced_home) in result

    def test_a_path_under_a_home_without_a_space_is_quoted_as_well(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Every expanded path takes the same double-quoted shape, whatever the home folder is called."""
        home = tmp_path / 'plainuser'
        monkeypatch.setattr(setup_environment, 'get_real_user_home', lambda: home)

        result = setup_environment.expand_tildes_for_cmd('python ~/.claude/key.py')

        assert result == f'python "{setup_environment.normalize_tilde_path("~/.claude/key.py")}"'

    @pytest.mark.parametrize(
        'value',
        [
            f'{HELPER} "~/.claude/scripts/helper.py"',
            '"~/.claude/scripts/helper.cmd"',
            'bash -c "cat ~/.claude/key.txt"',
        ],
    )
    def test_a_path_inside_the_authors_quotes_gains_no_quotes(self, value: str) -> None:
        """A path already standing inside double quotes is expanded and keeps the author's quotes only."""
        result = setup_environment.expand_tildes_for_cmd(value)

        assert result == setup_environment.expand_tildes_in_command(value)
        assert result.count('"') == value.count('"')
        assert '~' not in result

    def test_several_paths_in_one_value_are_each_quoted(self) -> None:
        """Every unquoted tilde path of the value is quoted on its own; an author-quoted one keeps its quotes."""
        value = 'python ~/.claude/a.py --config ~/.claude/b.json --log "~/.claude/c.log"'

        result = setup_environment.expand_tildes_for_cmd(value)

        assert result == (
            f'python {_quoted("~/.claude/a.py")} --config {_quoted("~/.claude/b.json")} '
            f'--log "{_expanded("~/.claude/c.log")}"'
        )

    def test_a_path_inside_an_option_is_quoted_from_the_tilde(self) -> None:
        """An option glued to its path value keeps the option outside the quotes, as cmd.exe accepts it."""
        result = setup_environment.expand_tildes_for_cmd('tool --config=~/.claude/c.json --verbose')

        assert result == f'tool --config={_quoted("~/.claude/c.json")} --verbose'

    def test_a_backslash_tilde_path_is_quoted(self) -> None:
        """A tilde path written with backslashes takes the same shape."""
        result = setup_environment.expand_tildes_for_cmd('python ~\\.claude\\key.py')

        assert result == f'python {_quoted("~\\.claude\\key.py")}'

    @pytest.mark.parametrize('value', ['get-key --profile work', 'python C:\\tools\\key.py', 'echo hello'])
    def test_a_value_without_a_tilde_path_is_unchanged(self, value: str) -> None:
        """Nothing the author wrote outside a tilde path is touched."""
        assert setup_environment.expand_tildes_for_cmd(value) == value

    def test_expand_tildes_in_command_keeps_its_unquoted_output(self) -> None:
        """The dependency and MCP callers keep the expansion without quotes."""
        result = setup_environment.expand_tildes_in_command(f'{HELPER} ~/.claude/scripts/helper.py')

        assert result == f'{HELPER} {_expanded("~/.claude/scripts/helper.py")}'


@pytest.mark.usefixtures('spaced_home')
class TestSettingsWritersOnWindows:
    """The base settings.json and the isolated config.json carry the quoted command."""

    @staticmethod
    def _settings() -> dict[str, Any]:
        return {
            'apiKeyHelper': f'{HELPER} ~/.claude/scripts/helper.py',
            'awsCredentialExport': '~/.claude/scripts/aws-export.cmd',
            'theme': 'dark',
        }

    @pytest.mark.usefixtures('on_windows')
    def test_expanding_the_settings_quotes_both_command_keys(self) -> None:
        """Both TILDE_EXPANSION_KEYS values are expanded and quoted; other keys and the input stay as they were."""
        settings = self._settings()

        result = setup_environment._expand_tilde_keys_in_settings(settings)

        assert result == {
            'apiKeyHelper': f'{HELPER} {_quoted("~/.claude/scripts/helper.py")}',
            'awsCredentialExport': _quoted('~/.claude/scripts/aws-export.cmd'),
            'theme': 'dark',
        }
        assert settings == self._settings()

    @pytest.mark.usefixtures('on_windows')
    def test_the_base_settings_json_carries_the_quoted_command(self, spaced_home: Path) -> None:
        """write_user_settings() writes the quoted command into ~/.claude/settings.json."""
        claude_dir = spaced_home / '.claude'

        assert setup_environment.write_user_settings(self._settings(), claude_dir)

        written = json.loads((claude_dir / 'settings.json').read_text(encoding='utf-8'))
        assert written['apiKeyHelper'] == f'{HELPER} {_quoted("~/.claude/scripts/helper.py")}'
        assert written['awsCredentialExport'] == _quoted('~/.claude/scripts/aws-export.cmd')

    @pytest.mark.usefixtures('on_windows')
    def test_the_isolated_config_json_carries_the_quoted_command(self, spaced_home: Path) -> None:
        """create_profile_config() writes the quoted command into the profile's config.json."""
        profile_dir = spaced_home / '.claude' / PROFILE

        assert setup_environment.create_profile_config({}, profile_dir, user_settings=self._settings())

        written = json.loads((profile_dir / 'config.json').read_text(encoding='utf-8'))
        assert written['apiKeyHelper'] == f'{HELPER} {_quoted("~/.claude/scripts/helper.py")}'
        assert written['awsCredentialExport'] == _quoted('~/.claude/scripts/aws-export.cmd')

    @pytest.mark.parametrize('platform_name', ['linux', 'darwin'])
    def test_linux_and_macos_keep_the_value_as_authored(
        self, monkeypatch: pytest.MonkeyPatch, platform_name: str,
    ) -> None:
        """Off Windows the tilde stays for Claude Code's shell to resolve, with no quotes added."""
        monkeypatch.setattr(setup_environment.sys, 'platform', platform_name)

        assert setup_environment._expand_tilde_keys_in_settings(self._settings()) == self._settings()


class TestRerootedPathsOnWindows:
    """A re-rooted settings value reaches cmd.exe as one argument wherever the profile lies."""

    @pytest.mark.usefixtures('on_windows')
    def test_a_profile_below_the_home_keeps_the_tilde_until_the_quoted_expansion(self, spaced_home: Path) -> None:
        """The re-rooted value keeps its tilde; the settings write expands it into the profile and quotes it."""
        settings = {'apiKeyHelper': f'{HELPER} ~/.claude/scripts/username.py'}
        reroot = ConfigHomeReroot(spaced_home / '.claude' / PROFILE, spaced_home, [PROFILE])

        records = reroot.apply({'user-settings': settings})
        expanded = setup_environment._expand_tilde_keys_in_settings(settings)

        assert settings['apiKeyHelper'] == f'{HELPER} ~/.claude/{PROFILE}/scripts/username.py'
        assert records[0].rewritten == settings['apiKeyHelper']
        profile_script = str(spaced_home / '.claude' / PROFILE / 'scripts' / 'username.py')
        assert expanded['apiKeyHelper'] == f'{HELPER} "{os.path.normpath(profile_script)}"'

    @pytest.mark.usefixtures('on_windows')
    def test_a_profile_outside_the_home_is_spelled_absolute_and_quoted(
        self, spaced_home: Path, tmp_path: Path,
    ) -> None:
        """Each unquoted path is quoted through the end of its argument; the summary record shows the quoted value."""
        outside = tmp_path / 'Profile Store (work)' / PROFILE
        posix = outside.as_posix()
        config: dict[str, Any] = {
            'user-settings': {
                'apiKeyHelper': f'{HELPER} ~/.claude/scripts/username.py --config ~/.claude/key.json',
                'awsCredentialExport': '~/.claude/scripts/aws-export.cmd',
            },
        }

        records = ConfigHomeReroot(outside, spaced_home, [PROFILE]).apply(config)

        helper = f'{HELPER} "{posix}/scripts/username.py" --config "{posix}/key.json"'
        assert config['user-settings'] == {
            'apiKeyHelper': helper,
            'awsCredentialExport': f'"{posix}/scripts/aws-export.cmd"',
        }
        assert records == [
            RerootedPath(
                'user-settings', 'apiKeyHelper',
                f'{HELPER} ~/.claude/scripts/username.py --config ~/.claude/key.json', helper,
            ),
            RerootedPath(
                'user-settings', 'awsCredentialExport', '~/.claude/scripts/aws-export.cmd',
                f'"{posix}/scripts/aws-export.cmd"',
            ),
        ]
        assert setup_environment._expand_tilde_keys_in_settings(config['user-settings']) == config['user-settings']

    @pytest.mark.usefixtures('on_windows')
    def test_a_path_inside_the_authors_quotes_is_not_quoted_twice(self, spaced_home: Path, tmp_path: Path) -> None:
        """The author's quotes already hold the absolute path as one argument."""
        outside = tmp_path / 'Profile Store' / PROFILE
        settings = {'apiKeyHelper': f'{HELPER} "~/.claude/scripts/username.py"'}

        ConfigHomeReroot(outside, spaced_home, [PROFILE]).apply({'user-settings': settings})

        assert settings['apiKeyHelper'] == f'{HELPER} "{outside.as_posix()}/scripts/username.py"'

    @pytest.mark.usefixtures('on_windows')
    def test_a_backslash_path_is_quoted_in_windows_spelling(self, spaced_home: Path, tmp_path: Path) -> None:
        """A path written with backslashes is spelled with backslashes and quoted."""
        outside = tmp_path / 'Profile Store' / PROFILE
        windows = str(outside).replace('/', '\\')
        settings = {'apiKeyHelper': 'python ~\\.claude\\scripts\\username.py'}

        ConfigHomeReroot(outside, spaced_home, [PROFILE]).apply({'user-settings': settings})

        assert settings['apiKeyHelper'] == f'python "{windows}\\scripts\\username.py"'

    @pytest.mark.usefixtures('on_windows')
    def test_another_profiles_path_stays_as_written(self, spaced_home: Path, tmp_path: Path) -> None:
        """A path naming another installed profile is neither rewritten nor quoted."""
        outside = tmp_path / 'Profile Store' / PROFILE
        value = f'{HELPER} ~/.claude/other/scripts/username.py'
        settings = {'apiKeyHelper': value}

        records = ConfigHomeReroot(outside, spaced_home, [PROFILE, 'other']).apply({'user-settings': settings})

        assert settings['apiKeyHelper'] == value
        assert records == []

    @pytest.mark.usefixtures('on_windows')
    def test_dependency_commands_are_never_quoted(self, spaced_home: Path, tmp_path: Path) -> None:
        """PowerShell and bash commands keep the plain rewrite: a quoted path in command position is no call."""
        outside = tmp_path / 'Profile Store' / PROFILE
        config: dict[str, Any] = {
            'dependencies': {
                'windows': ['~/.claude/bin/tool.exe install', 'Remove-Item "$env:USERPROFILE\\.claude\\statsig"'],
                'linux': ['uv run --script ~/.claude/skills/x/run.py'],
            },
        }

        ConfigHomeReroot(outside, spaced_home, [PROFILE]).apply(config)

        windows = str(outside).replace('/', '\\')
        assert config['dependencies'] == {
            'windows': [f'{outside.as_posix()}/bin/tool.exe install', f'Remove-Item "{windows}\\statsig"'],
            'linux': [f'uv run --script {outside.as_posix()}/skills/x/run.py'],
        }

    @pytest.mark.parametrize('platform_name', ['linux', 'darwin'])
    def test_linux_and_macos_keep_the_absolute_path_unquoted(
        self, spaced_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform_name: str,
    ) -> None:
        """Off Windows the re-rooted settings value is the plain rewrite."""
        monkeypatch.setattr(setup_environment.sys, 'platform', platform_name)
        outside = tmp_path / 'Profile Store' / PROFILE
        settings = {'apiKeyHelper': f'{HELPER} ~/.claude/scripts/username.py'}

        ConfigHomeReroot(outside, spaced_home, [PROFILE]).apply({'user-settings': settings})

        assert settings['apiKeyHelper'] == f'{HELPER} {outside.as_posix()}/scripts/username.py'

    @pytest.mark.usefixtures('on_windows')
    def test_rewriting_the_quoted_value_again_changes_nothing(self, spaced_home: Path, tmp_path: Path) -> None:
        """The quoted absolute value names no config-home path, so a second rewrite leaves it alone."""
        outside = tmp_path / 'Profile Store' / PROFILE
        reroot = ConfigHomeReroot(outside, spaced_home, [PROFILE])
        settings = {'apiKeyHelper': f'{HELPER} ~/.claude/scripts/username.py'}
        reroot.apply({'user-settings': settings})
        once = settings['apiKeyHelper']

        assert reroot.apply({'user-settings': settings}) == []
        assert settings['apiKeyHelper'] == once
