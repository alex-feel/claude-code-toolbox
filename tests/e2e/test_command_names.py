"""E2E tests for choosing a run's command names with --command-names.

--command-names NAME[,ALIAS...] (environment twin
CLAUDE_CODE_TOOLBOX_COMMAND_NAMES) installs any configuration as the isolated
profile ~/.claude/NAME. The value replaces the configuration's command-names
whole, a flag beats its variable and the variable beats the configuration,
and reserved names are refused before anything is written, as are names
another profile's manifest lists or a foreign ~/.local/bin file holds. The tests drive
main() with the real launcher, wrapper, profile-config and manifest writers
in an isolated home; only network access, the Claude Code binary, MCP
registration, OS-level variables and the Windows PATH registry are replaced.
"""

from __future__ import annotations

import copy
import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from scripts import cli
from scripts import setup_environment
from tests.conftest import empty_mcp_stats
from tests.e2e.expected import EXPECTED_FILES

windows_only = pytest.mark.skipif(sys.platform != 'win32', reason='UAC elevation exists only on Windows')

# A configuration shaped like claude-personal.yaml: one profile under three names
PERSONAL_CONFIG: dict[str, Any] = {
    'name': 'Personal Profile',
    'command-names': ['claude-a', 'claude-b', 'claude-c'],
    'command-defaults': {},
    'user-settings': {'theme': 'dark'},
}

# A configuration shaped like aegis.yaml: no command-names at all
SHARED_CONFIG: dict[str, Any] = {
    'name': 'Shared Environment',
    'user-settings': {'theme': 'light'},
}

NPM_DEPENDENCY = 'npm install -g e2e-global-cli'


def _run_main(argv: list[str], config: dict[str, Any]) -> int:
    """Run main() with the given arguments after the program name and return its exit code.

    Args:
        argv: Arguments after the program name, configuration included.
        config: The configuration main() loads.

    Returns:
        The exit code; 0 when main() returns normally.
    """
    original_find = setup_environment.find_command

    def _find_command(name: str) -> str | None:
        return '/usr/bin/claude' if name == 'claude' else original_find(name)

    with (
        patch('scripts.setup_environment.load_config_from_source',
              return_value=(copy.deepcopy(config), 'profile.yaml')),
        patch('scripts.setup_environment.validate_all_config_files', return_value=(True, [])),
        patch('scripts.setup_environment.cleanup_temp_paths_from_registry', return_value=(0, [])),
        patch('scripts.setup_environment.set_all_os_env_variables', return_value=True),
        patch('scripts.setup_environment.configure_all_mcp_servers',
              return_value=(True, [], empty_mcp_stats())),
        patch('scripts.setup_environment.find_command', side_effect=_find_command),
        patch('scripts.setup_environment._dev_tty_available', return_value=False),
        patch('sys.stdin.isatty', return_value=False),
        patch('sys.argv', ['setup_environment.py', *argv]),
    ):
        try:
            setup_environment.main()
        except SystemExit as exc:
            code = exc.code
            assert isinstance(code, int)
            return code
    return 0


def _install(extra_argv: list[str], config: dict[str, Any] = PERSONAL_CONFIG) -> int:
    """Run a setup of the configuration with Claude Code installation skipped."""
    return _run_main(['profile.yaml', '--skip-install', *extra_argv], config)


def _wrapper_paths(local_bin: Path, name: str) -> list[Path]:
    """Return the ~/.local/bin entries the setup registers for one command name."""
    templates = [template for template in EXPECTED_FILES if template.startswith('{local_bin}/')]
    return [Path(template.replace('{local_bin}', str(local_bin)).replace('{cmd}', name)) for template in templates]


def _local_bin_state(local_bin: Path) -> dict[str, str]:
    """Snapshot every ~/.local/bin entry: a link by its target, a file by its content."""
    state: dict[str, str] = {}
    for entry in sorted(local_bin.iterdir()):
        if entry.is_symlink():
            state[entry.name] = f'link:{os.readlink(entry)}'
        else:
            state[entry.name] = f'file:{entry.read_text(encoding="utf-8", errors="replace")}'
    return state


def _manifest(profile_dir: Path) -> dict[str, Any]:
    """Read a profile's manifest."""
    content: dict[str, Any] = json.loads((profile_dir / 'manifest.json').read_text(encoding='utf-8'))
    return content


def _assert_wrapper_targets_profile(local_bin: Path, name: str, profile_dir: Path) -> None:
    """Assert that the command name launches the given profile."""
    if sys.platform == 'win32':
        ps1 = (local_bin / f'{name}.ps1').read_text(encoding='utf-8')
        assert str(profile_dir / 'start.ps1') in ps1
    else:
        link = local_bin / name
        assert link.is_symlink()
        assert Path(os.readlink(link)) == profile_dir / 'launch.sh'


def _assert_profile_installed(paths: dict[str, Path], name: str, names: list[str]) -> Path:
    """Assert that profile NAME exists with the given command names and wrappers."""
    profile_dir = paths['claude_dir'] / name
    assert (profile_dir / 'config.json').is_file()
    assert (profile_dir / 'launch.sh').is_file()
    manifest = _manifest(profile_dir)
    assert manifest['name'] == name
    assert manifest['command_names'] == names
    for command in names:
        for wrapper in _wrapper_paths(paths['local_bin'], command):
            assert wrapper.exists() or wrapper.is_symlink(), f'missing wrapper {wrapper}'
        _assert_wrapper_targets_profile(paths['local_bin'], command, profile_dir)
    return profile_dir


def _assert_nothing_written(paths: dict[str, Path]) -> None:
    """Assert that the run created nothing in the isolated home."""
    assert list(paths['claude_dir'].iterdir()) == []
    assert list(paths['local_bin'].iterdir()) == []
    assert not (paths['home'] / '.claude.json').exists()


class TestOneConfigurationManyProfiles:
    """Two installs of one configuration under different names are two profiles."""

    def test_two_installs_produce_two_separate_profiles(self, e2e_isolated_home: dict[str, Path]) -> None:
        """Each name gets its own directory, manifest, config.json and wrappers."""
        assert _install(['--yes', '--command-names', 'work-1']) == 0
        assert _install(['--yes', '--command-names', 'work-2']) == 0

        first = _assert_profile_installed(e2e_isolated_home, 'work-1', ['work-1'])
        second = _assert_profile_installed(e2e_isolated_home, 'work-2', ['work-2'])
        assert first != second
        for profile_dir in (first, second):
            config = json.loads((profile_dir / 'config.json').read_text(encoding='utf-8'))
            assert config['theme'] == 'dark'
        # The configuration's own names were replaced, so nothing exists under them
        for configured in PERSONAL_CONFIG['command-names']:
            assert not (e2e_isolated_home['claude_dir'] / configured).exists()
            assert not any(path.exists() for path in _wrapper_paths(e2e_isolated_home['local_bin'], configured))

    def test_configuration_without_command_names_installs_as_an_isolated_profile(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """A base configuration lands in ~/.claude/NAME and leaves the base profile alone."""
        claude_dir = e2e_isolated_home['claude_dir']

        assert _install(['--yes', '--command-names', 'shared-1'], SHARED_CONFIG) == 0

        profile_dir = _assert_profile_installed(e2e_isolated_home, 'shared-1', ['shared-1'])
        config = json.loads((profile_dir / 'config.json').read_text(encoding='utf-8'))
        assert config['theme'] == 'light'
        assert not (claude_dir / 'settings.json').exists(), 'user-settings went to the base profile'
        assert not (claude_dir / 'manifest.json').exists(), 'the run recorded a base install'

    def test_same_configuration_without_the_flag_still_installs_into_the_base(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Without --command-names a configuration without command-names stays a base install."""
        claude_dir = e2e_isolated_home['claude_dir']

        assert _install(['--yes'], SHARED_CONFIG) == 0

        settings = json.loads((claude_dir / 'settings.json').read_text(encoding='utf-8'))
        assert settings['theme'] == 'light'
        assert _manifest(claude_dir)['command_names'] == []
        assert list(e2e_isolated_home['local_bin'].iterdir()) == []


class TestEnvironmentTwin:
    """CLAUDE_CODE_TOOLBOX_COMMAND_NAMES works like the flag."""

    def test_variable_installs_the_profile_it_names_with_its_aliases(
        self, e2e_isolated_home: dict[str, Path], monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The variable's list replaces the configuration's list, aliases included."""
        monkeypatch.setenv('CLAUDE_CODE_TOOLBOX_COMMAND_NAMES', 'env-main,env-alias')

        assert _install(['--yes']) == 0

        _assert_profile_installed(e2e_isolated_home, 'env-main', ['env-main', 'env-alias'])
        assert not (e2e_isolated_home['claude_dir'] / 'claude-a').exists()

    def test_variable_set_through_env_flag_selects_the_profile(self, e2e_isolated_home: dict[str, Path]) -> None:
        """--env CLAUDE_CODE_TOOLBOX_COMMAND_NAMES=... is the same channel as an exported variable."""
        assert _install(['--yes', '--env', 'CLAUDE_CODE_TOOLBOX_COMMAND_NAMES=via-env-flag']) == 0

        _assert_profile_installed(e2e_isolated_home, 'via-env-flag', ['via-env-flag'])


class TestPrecedence:
    """Flag beats variable beats configuration, and the summary says which one won."""

    @pytest.mark.parametrize(
        ('flag', 'variable', 'expected_row'),
        [
            ('cli-name', 'env-name', 'Command names: cli-name [cli]'),
            (None, 'env-name', 'Command names: env-name [env]'),
            (None, None, 'Command names: claude-a, claude-b, claude-c [yaml]'),
        ],
    )
    def test_dry_run_summary_names_the_winning_source(
        self,
        flag: str | None,
        variable: str | None,
        expected_row: str,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The summary row carries the effective names and their origin."""
        if variable is not None:
            monkeypatch.setenv('CLAUDE_CODE_TOOLBOX_COMMAND_NAMES', variable)
        extra = ['--dry-run'] + (['--command-names', flag] if flag else [])

        assert _install(extra) == 0

        captured = capsys.readouterr()
        assert expected_row in captured.out + captured.err
        _assert_nothing_written(e2e_isolated_home)

    def test_flag_wins_over_variable_in_a_real_install(
        self, e2e_isolated_home: dict[str, Path], monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Only the typed profile is installed when both sources are set."""
        monkeypatch.setenv('CLAUDE_CODE_TOOLBOX_COMMAND_NAMES', 'env-name')

        assert _install(['--yes', '--command-names', 'cli-name']) == 0

        _assert_profile_installed(e2e_isolated_home, 'cli-name', ['cli-name'])
        assert not (e2e_isolated_home['claude_dir'] / 'env-name').exists()
        assert not (e2e_isolated_home['claude_dir'] / 'claude-a').exists()


class TestTypedNameNeverMergesWithTheConfiguration:
    """A typed single name is a new profile with exactly one command."""

    def test_second_profile_gets_one_wrapper_and_the_first_stays_untouched(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """claude-personal installed, then the same YAML with --command-names p2."""
        claude_dir = e2e_isolated_home['claude_dir']
        local_bin = e2e_isolated_home['local_bin']
        assert _install(['--yes']) == 0
        first = _assert_profile_installed(e2e_isolated_home, 'claude-a', ['claude-a', 'claude-b', 'claude-c'])
        bin_before = _local_bin_state(local_bin)
        first_before = {
            name: (first / name).read_bytes() for name in ('manifest.json', 'config.json', 'launch.sh')
        }

        assert _install(['--yes', '--command-names', 'p2']) == 0

        bin_after = _local_bin_state(local_bin)
        added = set(bin_after) - set(bin_before)
        assert added == {path.name for path in _wrapper_paths(local_bin, 'p2')}
        assert {name: bin_after[name] for name in bin_before} == bin_before
        assert {name: (first / name).read_bytes() for name in first_before} == first_before
        _assert_profile_installed(e2e_isolated_home, 'p2', ['p2'])
        assert sorted(entry.name for entry in claude_dir.iterdir()) == ['claude-a', 'p2']


class TestReservedNames:
    """A reserved name is refused before anything is written."""

    @pytest.mark.parametrize(
        ('source', 'value', 'message'),
        [
            ('flag', 'all', 'Command name "all" in --command-names is reserved'),
            ('flag', 'ok-name,Base', 'Command name "Base" in --command-names is reserved'),
            ('variable', 'projects', 'Command name "projects" in CLAUDE_CODE_TOOLBOX_COMMAND_NAMES is reserved'),
            ('configuration', 'skills', 'Command name "skills" in command-names is reserved'),
        ],
    )
    def test_reserved_name_is_refused_without_writes(
        self,
        source: str,
        value: str,
        message: str,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The run exits 1 with the reason and leaves the home untouched."""
        config = copy.deepcopy(PERSONAL_CONFIG)
        extra = ['--yes']
        if source == 'flag':
            extra += ['--command-names', value]
        elif source == 'variable':
            monkeypatch.setenv('CLAUDE_CODE_TOOLBOX_COMMAND_NAMES', value)
        else:
            config['command-names'] = [value]

        assert _install(extra, config) == 1

        assert message in capsys.readouterr().err
        _assert_nothing_written(e2e_isolated_home)

    def test_dry_run_reports_the_refusal(
        self, e2e_isolated_home: dict[str, Path], capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A preview of a run that cannot execute reports the refusal, not a plan."""
        assert _install(['--dry-run', '--command-names', 'hooks']) == 1

        captured = capsys.readouterr()
        assert 'Command name "hooks" in --command-names is reserved' in captured.err
        assert 'Installation Summary' not in captured.out + captured.err
        _assert_nothing_written(e2e_isolated_home)


def _home_state(home: Path) -> dict[str, str]:
    """Snapshot every entry under the home: links by target, files by content, directories by name."""
    state: dict[str, str] = {}
    for entry in sorted(home.rglob('*')):
        key = entry.relative_to(home).as_posix()
        if entry.is_symlink():
            state[key] = f'link:{os.readlink(entry)}'
        elif entry.is_file():
            state[key] = f'file:{entry.read_bytes().hex()}'
        else:
            state[key] = 'dir'
    return state


def _foreign_entry(local_bin: Path, name: str) -> Path:
    """Create a file the toolbox did not write under the name's wrapper path."""
    path = local_bin / (f'{name}.cmd' if sys.platform == 'win32' else name)
    path.write_text('@echo off\r\necho mine\r\n' if sys.platform == 'win32' else '#!/bin/sh\necho mine\n', encoding='utf-8')
    return path


class TestNamesAnotherProfileOwns:
    """A name another profile's manifest lists is refused before anything is written."""

    @pytest.mark.parametrize(
        ('typed', 'message'),
        [
            ('claude-b', 'Command name "claude-b" belongs to the profile "claude-a"'),
            ('fresh,claude-c', 'Command name "claude-c" belongs to the profile "claude-a"'),
            ('fresh,claude-a', 'Command name "claude-a" is the primary name of the profile "claude-a"'),
        ],
    )
    def test_owned_name_is_refused_and_nothing_changes(
        self,
        typed: str,
        message: str,
        e2e_isolated_home: dict[str, Path],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Neither the other profile's wrappers nor any new profile is written."""
        home = e2e_isolated_home['home']
        assert _install(['--yes']) == 0
        capsys.readouterr()
        before = _home_state(home)

        assert _install(['--yes', '--command-names', typed]) == 1

        err = capsys.readouterr().err
        assert message in err
        assert str(e2e_isolated_home['claude_dir'] / 'claude-a' / 'manifest.json') in err
        assert _home_state(home) == before

    def test_variable_naming_an_owned_name_is_refused(
        self,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The check applies to names from the environment twin too."""
        home = e2e_isolated_home['home']
        assert _install(['--yes']) == 0
        before = _home_state(home)
        monkeypatch.setenv('CLAUDE_CODE_TOOLBOX_COMMAND_NAMES', 'claude-b')

        assert _install(['--yes']) == 1

        assert 'Command name "claude-b" belongs to the profile "claude-a"' in capsys.readouterr().err
        assert _home_state(home) == before

    def test_dry_run_reports_the_owner(
        self, e2e_isolated_home: dict[str, Path], capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A preview reports the refusal instead of a plan for a run that cannot proceed."""
        assert _install(['--yes']) == 0
        capsys.readouterr()
        before = _home_state(e2e_isolated_home['home'])

        assert _install(['--dry-run', '--command-names', 'claude-c']) == 1

        captured = capsys.readouterr()
        assert 'Command name "claude-c" belongs to the profile "claude-a"' in captured.err
        assert 'Installation Summary' not in captured.out + captured.err
        assert _home_state(e2e_isolated_home['home']) == before

    def test_re_run_of_the_same_profile_keeps_its_names(self, e2e_isolated_home: dict[str, Path]) -> None:
        """The profile that owns the names installs again under them."""
        assert _install(['--yes']) == 0
        assert _install(['--yes']) == 0
        assert _install(['--yes', '--command-names', 'claude-a,claude-b']) == 0

        _assert_profile_installed(e2e_isolated_home, 'claude-a', ['claude-a', 'claude-b'])

    def test_wrapper_of_a_dropped_alias_is_free_to_reuse(self, e2e_isolated_home: dict[str, Path]) -> None:
        """Once its profile stops listing an alias, another profile may take the name."""
        assert _install(['--yes', '--command-names', 'old-main,old-alias']) == 0
        assert _install(['--yes', '--command-names', 'old-main']) == 0

        assert _install(['--yes', '--command-names', 'new-main,old-alias']) == 0

        new_profile = _assert_profile_installed(e2e_isolated_home, 'new-main', ['new-main', 'old-alias'])
        _assert_wrapper_targets_profile(e2e_isolated_home['local_bin'], 'old-alias', new_profile)

    def test_profile_with_an_unreadable_manifest_keeps_its_name(
        self, e2e_isolated_home: dict[str, Path], capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A manifest that cannot be read still marks its directory's name as taken."""
        broken = e2e_isolated_home['claude_dir'] / 'broken'
        broken.mkdir()
        (broken / 'manifest.json').write_text('{not json', encoding='utf-8')

        assert _install(['--yes', '--command-names', 'fresh,broken']) == 1

        assert 'Command name "broken" names the profile directory' in capsys.readouterr().err
        assert not (e2e_isolated_home['claude_dir'] / 'fresh').exists()


class TestNamesAForeignFileHolds:
    """A name ~/.local/bin holds as a file the toolbox did not create is refused."""

    def test_foreign_file_is_refused_and_left_alone(
        self, e2e_isolated_home: dict[str, Path], capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The file keeps its content and no profile is created."""
        home = e2e_isolated_home['home']
        foreign = _foreign_entry(e2e_isolated_home['local_bin'], 'mytool')
        before = _home_state(home)

        assert _install(['--yes', '--command-names', 'mytool']) == 1

        err = capsys.readouterr().err
        assert f'Command name "mytool" is taken by {foreign}, which the toolbox did not create' in err
        assert _home_state(home) == before

    def test_foreign_file_under_an_alias_is_refused(
        self, e2e_isolated_home: dict[str, Path], capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Every name of the run is checked, not only the primary."""
        _foreign_entry(e2e_isolated_home['local_bin'], 'mytool')

        assert _install(['--yes', '--command-names', 'fresh,mytool']) == 1

        assert 'Command name "mytool" is taken by' in capsys.readouterr().err
        assert not (e2e_isolated_home['claude_dir'] / 'fresh').exists()

    def test_configuration_names_are_checked_too(
        self, e2e_isolated_home: dict[str, Path], capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A name from the YAML gets the same protection as a typed one."""
        _foreign_entry(e2e_isolated_home['local_bin'], 'claude-b')

        assert _install(['--yes']) == 1

        assert 'Command name "claude-b" is taken by' in capsys.readouterr().err
        assert not (e2e_isolated_home['claude_dir'] / 'claude-a').exists()

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows shells resolve name.exe for the bare name')
    def test_windows_executable_with_the_name_is_refused(
        self, e2e_isolated_home: dict[str, Path], capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A wrapper named claude next to claude.exe would hijack the real binary."""
        binary = e2e_isolated_home['local_bin'] / 'claude.exe'
        binary.write_bytes(b'MZ')

        assert _install(['--yes', '--command-names', 'claude']) == 1

        assert f'Command name "claude" is taken by {binary}' in capsys.readouterr().err
        assert sorted(entry.name for entry in e2e_isolated_home['local_bin'].iterdir()) == ['claude.exe']

    @pytest.mark.skipif(sys.platform == 'win32', reason='the native Claude Code link is the Unix layout')
    def test_unix_link_to_a_binary_is_refused(
        self, e2e_isolated_home: dict[str, Path], capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Replacing the native Claude Code link would make the launcher call itself."""
        home = e2e_isolated_home['home']
        target = home / '.local' / 'share' / 'claude' / 'versions' / '2.1.0'
        target.parent.mkdir(parents=True)
        target.write_text('binary', encoding='utf-8')
        link = e2e_isolated_home['local_bin'] / 'claude'
        link.symlink_to(target)

        assert _install(['--yes', '--command-names', 'claude']) == 1

        assert f'Command name "claude" is taken by {link}' in capsys.readouterr().err
        assert Path(os.readlink(link)) == target


class TestPackagedCli:
    """cc-toolbox setup forwards --command-names to the setup unchanged."""

    def test_cli_setup_passes_the_flag_through(
        self, e2e_isolated_home: dict[str, Path], capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The dispatcher hands every argument to setup's own parser."""
        del e2e_isolated_home
        with (
            patch('scripts.setup_environment.load_config_from_source',
                  return_value=(copy.deepcopy(PERSONAL_CONFIG), 'profile.yaml')),
            patch('scripts.setup_environment.validate_all_config_files', return_value=(True, [])),
            patch('scripts.setup_environment.cleanup_temp_paths_from_registry', return_value=(0, [])),
            patch('sys.argv', ['cc-toolbox', 'setup', 'profile.yaml', '--skip-install', '--dry-run',
                               '--command-names', 'via-cli,via-cli-alias']),
            pytest.raises(SystemExit) as exc_info,
        ):
            cli.main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert 'Command names: via-cli, via-cli-alias [cli]' in captured.out + captured.err


@pytest.fixture
def mock_shell_execute() -> Iterator[MagicMock]:
    """Replace the UAC relaunch primitive so no prompt opens and the call is recorded."""
    with (
        patch('ctypes.windll', create=True) as mock_windll,
        patch('time.sleep'),
    ):
        mock_windll.shell32.ShellExecuteW.return_value = 33
        yield mock_windll.shell32.ShellExecuteW


@windows_only
class TestUacRelaunch:
    """The elevated window installs the profile the variable named in the original shell."""

    def test_variable_survives_the_relaunch(
        self,
        e2e_isolated_home: dict[str, Path],
        mock_shell_execute: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A run that needs elevation forwards the variable, and the elevated run honors it."""
        monkeypatch.setenv('CLAUDE_CODE_TOOLBOX_COMMAND_NAMES', 'uac-profile')
        config = copy.deepcopy(PERSONAL_CONFIG)
        config['dependencies'] = {'common': [NPM_DEPENDENCY]}
        relaunches: list[list[str]] = []
        original_list2cmdline = setup_environment.subprocess.list2cmdline

        def _capture(args: list[str]) -> str:
            relaunches.append(list(args))
            return original_list2cmdline(args)

        with (
            patch('scripts.setup_environment.is_admin', return_value=False),
            patch.object(setup_environment.subprocess, 'list2cmdline', side_effect=_capture),
        ):
            assert _install(['--yes'], config) == 0

        mock_shell_execute.assert_called_once()
        assert len(relaunches) == 1
        relaunch = relaunches[0]
        assert '--env-CLAUDE_CODE_TOOLBOX_COMMAND_NAMES=uac-profile' in relaunch
        assert not (e2e_isolated_home['claude_dir'] / 'uac-profile').exists()

        # The elevated window starts without the variable in its environment
        monkeypatch.delenv('CLAUDE_CODE_TOOLBOX_COMMAND_NAMES')
        first_forwarded = next(index for index, arg in enumerate(relaunch) if arg.startswith('--env-'))
        with (
            patch('scripts.setup_environment.is_admin', return_value=True),
            patch('scripts.setup_environment.install_dependencies', return_value=[]) as mock_dependencies,
        ):
            assert _run_main(relaunch[first_forwarded:], config) == 0

        mock_dependencies.assert_called_once()
        _assert_profile_installed(e2e_isolated_home, 'uac-profile', ['uac-profile'])
        assert not (e2e_isolated_home['claude_dir'] / 'claude-a').exists()
        captured = capsys.readouterr()
        assert 'Command names: uac-profile [env]' in captured.out + captured.err
