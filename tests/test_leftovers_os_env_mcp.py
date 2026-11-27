"""Tests for the leftovers among the base profile's OS environment variables and every profile's MCP servers.

A base run records a digest of the value of each OS environment variable
Step 7 sets, and every run records a digest of the entry each MCP server it
declares holds at each CLI scope once Step 13 registered it, but only an
entry that equals what the configuration declares. A re-run lists the
recorded variables and servers its configuration no longer declares; a run
given --remove-leftovers removes in Step 23 each one that still holds what
the setup wrote and records per item whether it is gone. The machine-wide
update controls are never recorded.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
from collections.abc import Callable
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts import setup_environment
from scripts.setup_environment import LeftoverEntry
from scripts.setup_environment import LeftoverItem
from scripts.setup_environment import LeftoverReadError
from scripts.setup_environment import LeftoverRemoval
from scripts.setup_environment import LeftoverReport
from scripts.setup_environment import LiveLeftoverState
from scripts.setup_environment import PlannedRecords

digest = setup_environment.leftover_digest
_REAL_READ_OS_ENV_VARIABLE = setup_environment.read_os_env_variable
_REAL_READ_USER_ENVIRONMENT_VALUE = setup_environment._read_user_environment_value
_REAL_RECORD_MANIFEST_LEFTOVERS = setup_environment._record_manifest_leftovers

_HTTP_SERVER: dict[str, Any] = {'name': 'old-srv', 'transport': 'http', 'url': 'https://mcp.example/mcp'}
_LIVE_ENTRY: dict[str, Any] = {'type': 'http', 'url': 'https://mcp.example/mcp'}


class Machine:
    """The OS environment and the MCP registrations a run reads, held in memory.

    Attributes:
        env: Variable name to the values the places the setup writes hold.
        mcp: Server name to the entry each CLI scope holds.
        unreadable: Names whose state cannot be read.
    """

    def __init__(self) -> None:
        self.env: dict[str, tuple[str, ...]] = {}
        self.mcp: dict[str, dict[str, Any]] = {}
        self.unreadable: set[str] = set()

    def read_env(self, name: str) -> tuple[str, ...]:
        if name in self.unreadable:
            raise LeftoverReadError('the user environment cannot be read')
        return self.env.get(name, ())

    def read_mcp(self, name: str) -> dict[str, Any]:
        if name in self.unreadable:
            raise LeftoverReadError('.claude.json cannot be read')
        return dict(self.mcp.get(name, {}))

    def live(self) -> LiveLeftoverState:
        return LiveLeftoverState(
            file_digest=lambda _path: None,
            under_link=lambda _relative: False,
            destination_holders=lambda _dest: [],
            os_env=self.read_env,
            mcp=self.read_mcp,
        )

    def writer(self, *, deletes: bool = True) -> Callable[[Sequence[str]], bool]:
        """Stand in for delete_toolbox_os_env_variables(): delete each variable named."""
        def _write(names: Sequence[str]) -> bool:
            for name in names:
                if deletes:
                    self.env.pop(name, None)
            return deletes
        return _write

    def mcp_remover(self, *, removes: bool = True) -> Callable[..., None]:
        """Stand in for _remove_mcp_server_from_cli_scopes(): drop the named scopes."""
        def _remove(_claude: str, name: str, scopes: list[str], _nodejs_dir: str | None, _config_dir: Path | None) -> None:
            if removes:
                for scope in scopes:
                    self.mcp.get(name, {}).pop(scope, None)
        return _remove


def _os_env_item(name: str, value: str) -> LeftoverItem:
    return LeftoverItem.os_env(name, digest(value))


def _mcp_item(name: str, scope: str, entry: dict[str, Any]) -> LeftoverItem:
    return LeftoverItem.mcp_server(name, scope, digest(entry))


def _report(profile_dir: Path, *entries: LeftoverEntry) -> LeftoverReport:
    return LeftoverReport(profile_name='base', profile_dir=profile_dir, entries=tuple(entries), untracked_note=False)


def _step(
    report: LeftoverReport,
    machine: Machine,
    *,
    claude_dir: Path,
    profile_dir: Path,
    remove: bool = True,
    written: PlannedRecords | None = None,
) -> LeftoverRemoval:
    removal = setup_environment.run_leftovers_step(
        report,
        remove=remove,
        download_failed=False,
        written=written or PlannedRecords(),
        live=machine.live(),
        profile_dir=profile_dir,
        claude_dir=claude_dir,
        manifest_path=profile_dir / 'manifest.json',
        run_at='t',
    )
    assert removal is not None
    return removal


@pytest.fixture
def claude_dir(tmp_path: Path) -> Path:
    """The base ~/.claude directory."""
    directory = tmp_path / '.claude'
    directory.mkdir()
    return directory


class TestShellExportReader:
    """On Linux and macOS a variable lives in the toolbox block of every shell file the setup writes."""

    @pytest.fixture
    def shell_files(self, tmp_path: Path) -> list[Path]:
        home = tmp_path / 'home'
        home.mkdir()
        return [home / '.bashrc', home / '.zshenv']

    def test_reads_what_the_writer_wrote(self, shell_files: list[Path]) -> None:
        for path in shell_files:
            assert setup_environment.add_export_to_file(path, 'TOOL_HOME', 'some value')

        assert setup_environment._read_shell_export_values(shell_files, 'TOOL_HOME') == ('some value',)

    def test_a_value_holding_double_quotes_reads_back(self, shell_files: list[Path]) -> None:
        assert setup_environment.add_export_to_file(shell_files[0], 'TOOL_HOME', 'a "quoted" word')

        assert setup_environment._read_shell_export_values(shell_files, 'TOOL_HOME') == ('a "quoted" word',)

    def test_the_set_syntax_file_reads_back(self, tmp_path: Path) -> None:
        set_file = tmp_path / 'cfg' / 'fish' / 'config.fish'
        assert setup_environment.add_export_to_file(set_file, 'TOOL_HOME', 'v')
        assert 'set -gx TOOL_HOME "v"' in set_file.read_text(encoding='utf-8')

        assert setup_environment._read_shell_export_values([set_file], 'TOOL_HOME') == ('v',)

    def test_a_removed_variable_reads_as_absent(self, shell_files: list[Path]) -> None:
        for path in shell_files:
            assert setup_environment.add_export_to_file(path, 'TOOL_HOME', 'v')
            assert setup_environment.add_export_to_file(path, 'OTHER', 'x')
            assert setup_environment.remove_export_from_file(path, 'TOOL_HOME')

        assert setup_environment._read_shell_export_values(shell_files, 'TOOL_HOME') == ()
        assert setup_environment._read_shell_export_values(shell_files, 'OTHER') == ('x',)

    def test_files_that_disagree_give_every_value(self, shell_files: list[Path]) -> None:
        assert setup_environment.add_export_to_file(shell_files[0], 'TOOL_HOME', 'one')
        assert setup_environment.add_export_to_file(shell_files[1], 'TOOL_HOME', 'two')

        assert setup_environment._read_shell_export_values(shell_files, 'TOOL_HOME') == ('one', 'two')

    def test_a_file_without_the_line_does_not_count(self, shell_files: list[Path], tmp_path: Path) -> None:
        assert setup_environment.add_export_to_file(shell_files[0], 'TOOL_HOME', 'v')
        assert setup_environment.add_export_to_file(shell_files[1], 'OTHER', 'x')

        files = [*shell_files, tmp_path / 'home' / '.profile']
        assert setup_environment._read_shell_export_values(files, 'TOOL_HOME') == ('v',)

    def test_a_line_outside_the_toolbox_block_is_not_the_setups(self, shell_files: list[Path]) -> None:
        shell_files[0].write_text('export TOOL_HOME="mine"\n', encoding='utf-8')
        assert setup_environment.add_export_to_file(shell_files[1], 'OTHER', 'x')
        shell_files[1].write_text(
            shell_files[1].read_text(encoding='utf-8') + 'export TOOL_HOME="mine too"\n', encoding='utf-8',
        )

        assert setup_environment._read_shell_export_values(shell_files, 'TOOL_HOME') == ()

    def test_a_file_that_cannot_be_read_cannot_be_checked(self, shell_files: list[Path]) -> None:
        shell_files[0].write_bytes(b'\xff\xfe export TOOL_HOME="v"')

        with pytest.raises(LeftoverReadError, match=r'\.bashrc'):
            setup_environment._read_shell_export_values(shell_files, 'TOOL_HOME')

    def test_a_directory_in_place_of_a_file_cannot_be_checked(self, shell_files: list[Path]) -> None:
        shell_files[1].mkdir()

        with pytest.raises(LeftoverReadError, match=r'\.zshenv'):
            setup_environment._read_shell_export_values(shell_files, 'TOOL_HOME')


class TestToolboxBlockRemoval:
    """A leftover variable leaves the toolbox block of a shell file; the lines a user wrote outside it stay."""

    def test_only_the_line_inside_the_block_leaves(self, tmp_path: Path) -> None:
        bashrc = tmp_path / '.bashrc'
        bashrc.write_text('# mine\nexport TOOL_HOME="mine"\n', encoding='utf-8')
        assert setup_environment.add_export_to_file(bashrc, 'TOOL_HOME', 'v')
        assert setup_environment.add_export_to_file(bashrc, 'OTHER', 'x')

        assert setup_environment.remove_export_from_toolbox_block(bashrc, 'TOOL_HOME')

        content = bashrc.read_text(encoding='utf-8')
        assert content.startswith('# mine\nexport TOOL_HOME="mine"\n')
        assert 'export TOOL_HOME="v"' not in content
        assert setup_environment._read_shell_export_values([bashrc], 'TOOL_HOME') == ()
        assert setup_environment._read_shell_export_values([bashrc], 'OTHER') == ('x',)

    def test_a_block_the_removal_empties_goes_with_it(self, tmp_path: Path) -> None:
        bashrc, zshenv = tmp_path / '.bashrc', tmp_path / '.zshenv'
        bashrc.write_text('export TOOL_HOME="mine"\n', encoding='utf-8')
        for path in (bashrc, zshenv):
            assert setup_environment.add_export_to_file(path, 'TOOL_HOME', 'v')
            assert setup_environment.remove_export_from_toolbox_block(path, 'TOOL_HOME')

        assert bashrc.read_text(encoding='utf-8') == 'export TOOL_HOME="mine"\n'
        assert zshenv.read_text(encoding='utf-8') == ''

    def test_the_set_syntax_file_keeps_its_own_line(self, tmp_path: Path) -> None:
        set_file = tmp_path / 'cfg' / 'fish' / 'config.fish'
        set_file.parent.mkdir(parents=True)
        set_file.write_text('set -gx TOOL_HOME "mine"\n', encoding='utf-8')
        assert setup_environment.add_export_to_file(set_file, 'TOOL_HOME', 'v')

        assert setup_environment.remove_export_from_toolbox_block(set_file, 'TOOL_HOME')

        assert set_file.read_text(encoding='utf-8') == 'set -gx TOOL_HOME "mine"\n'

    def test_a_file_without_a_block_or_without_the_file_is_left_alone(self, tmp_path: Path) -> None:
        bashrc = tmp_path / '.bashrc'
        bashrc.write_text('export TOOL_HOME="mine"\n', encoding='utf-8')

        assert setup_environment.remove_export_from_toolbox_block(bashrc, 'TOOL_HOME')
        assert setup_environment.remove_export_from_toolbox_block(tmp_path / '.zshenv', 'TOOL_HOME')

        assert bashrc.read_text(encoding='utf-8') == 'export TOOL_HOME="mine"\n'
        assert not (tmp_path / '.zshenv').exists()

    def test_a_null_entry_still_deletes_every_line(self, tmp_path: Path) -> None:
        bashrc = tmp_path / '.bashrc'
        bashrc.write_text('export TOOL_HOME="mine"\n', encoding='utf-8')
        assert setup_environment.add_export_to_file(bashrc, 'TOOL_HOME', 'v')

        assert setup_environment.remove_export_from_file(bashrc, 'TOOL_HOME')

        assert 'TOOL_HOME' not in bashrc.read_text(encoding='utf-8')


class TestDeleteToolboxOsEnvVariables:
    """Step 23 deletes a leftover variable where Step 7 wrote it and nowhere else."""

    def test_shell_files_lose_only_the_block_lines(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        bashrc, zshenv = tmp_path / '.bashrc', tmp_path / '.zshenv'
        bashrc.write_text('export TOOL_HOME="mine"\n', encoding='utf-8')
        for path in (bashrc, zshenv):
            assert setup_environment.add_export_to_file(path, 'TOOL_HOME', 'v')
        monkeypatch.setattr(sys, 'platform', 'linux')
        monkeypatch.setattr(setup_environment, 'get_all_shell_config_files', lambda: [bashrc, zshenv])
        monkeypatch.setattr(setup_environment.shutil, 'which', lambda _cmd: None)
        monkeypatch.setenv('TOOL_HOME', 'v')

        assert setup_environment.delete_toolbox_os_env_variables(['TOOL_HOME'])

        assert bashrc.read_text(encoding='utf-8') == 'export TOOL_HOME="mine"\n'
        assert zshenv.read_text(encoding='utf-8') == ''
        assert _REAL_READ_OS_ENV_VARIABLE('TOOL_HOME') == ()
        assert 'TOOL_HOME' not in os.environ

    def test_the_fish_universal_variable_the_setup_set_is_erased(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        calls: list[list[str]] = []

        def _run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
            calls.append(command)
            return subprocess.CompletedProcess(command, 0)

        monkeypatch.setattr(sys, 'platform', 'linux')
        monkeypatch.setattr(setup_environment, 'get_all_shell_config_files', lambda: [tmp_path / '.bashrc'])
        monkeypatch.setattr(setup_environment.shutil, 'which', lambda cmd: '/usr/bin/fish' if cmd == 'fish' else None)
        monkeypatch.setattr(setup_environment.subprocess, 'run', _run)

        assert setup_environment.delete_toolbox_os_env_variables(['TOOL_HOME'])

        assert calls == [['fish', '-c', 'set -Ue TOOL_HOME']]

    def test_windows_deletes_the_user_environment_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        written: list[tuple[str, str | None]] = []

        def _write(name: str, value: str | None) -> bool:
            written.append((name, value))
            return name != 'REFUSED'

        monkeypatch.setattr(sys, 'platform', 'win32')
        monkeypatch.setattr(setup_environment, 'set_os_env_variable_windows', _write)
        monkeypatch.setenv('TOOL_HOME', 'v')
        monkeypatch.setenv('REFUSED', 'r')

        assert not setup_environment.delete_toolbox_os_env_variables(['TOOL_HOME', 'REFUSED'])

        assert written == [('TOOL_HOME', None), ('REFUSED', None)]
        assert 'TOOL_HOME' not in os.environ
        assert os.environ['REFUSED'] == 'r', 'a variable the deletion left keeps its value in the process'


class TestReadOsEnvVariable:
    """The live value of a variable is read where Step 7 writes it on each platform."""

    def test_windows_reads_the_user_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        values = {'TOOL_HOME': 'v'}
        monkeypatch.setattr(sys, 'platform', 'win32')
        monkeypatch.setattr(setup_environment, '_read_user_environment_value', values.get)

        assert _REAL_READ_OS_ENV_VARIABLE('TOOL_HOME') == ('v',)
        assert _REAL_READ_OS_ENV_VARIABLE('ABSENT') == ()

    def test_an_unreadable_user_environment_cannot_be_checked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _refuse(_name: str) -> str | None:
            raise PermissionError(13, 'Access is denied')

        monkeypatch.setattr(sys, 'platform', 'win32')
        monkeypatch.setattr(setup_environment, '_read_user_environment_value', _refuse)

        with pytest.raises(LeftoverReadError, match='Access is denied'):
            _REAL_READ_OS_ENV_VARIABLE('TOOL_HOME')

    def test_other_platforms_read_the_shell_files(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        bashrc = tmp_path / '.bashrc'
        assert setup_environment.add_export_to_file(bashrc, 'TOOL_HOME', 'v')
        monkeypatch.setattr(sys, 'platform', 'linux')
        monkeypatch.setattr(setup_environment, 'get_all_shell_config_files', lambda: [bashrc])

        assert _REAL_READ_OS_ENV_VARIABLE('TOOL_HOME') == ('v',)

    def test_the_user_environment_value_comes_from_the_registry(self) -> None:
        if sys.platform != 'win32':
            pytest.skip('the user environment is a Windows registry key')
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as key:
            name, value, _kind = winreg.EnumValue(key, 0)

        assert _REAL_READ_USER_ENVIRONMENT_VALUE(name) == str(value)
        assert _REAL_READ_USER_ENVIRONMENT_VALUE(f'CCT_ABSENT_{secrets.token_hex(8)}') is None


class TestRecords:
    """What a run records about the variables and servers it wrote, as digests only."""

    def test_a_base_run_records_each_variable_it_set(self) -> None:
        records = setup_environment.os_env_records(
            {'TOOL_HOME': 'v', 'GONE': None, 'DISABLE_UPDATES': '1', 'DISABLE_AUTOUPDATER': '1'}, isolated=False,
        )

        assert records == [{'name': 'TOOL_HOME', 'sha256': digest('v')}]

    def test_an_isolated_run_records_no_variable(self) -> None:
        assert setup_environment.os_env_records({'TOOL_HOME': 'v'}, isolated=True) == []

    def test_a_server_entry_equal_to_the_declaration_is_recorded(self) -> None:
        server = {**_HTTP_SERVER, 'scope': ['user', 'profile']}
        records = setup_environment.mcp_server_records(
            [server, {'scope': 'user'}], live_entries=lambda _name: {'user': _LIVE_ENTRY, 'local': None},
        )

        assert records == [{'name': 'old-srv', 'scopes': ['user', 'profile'], 'sha256': {'user': digest(_LIVE_ENTRY)}}]

    def test_an_entry_the_setup_did_not_write_is_not_the_setups(self) -> None:
        """A same-name entry that differs from the declaration (its registration failed) never gets a digest."""
        foreign = {'type': 'http', 'url': 'https://elsewhere.example/mcp'}

        records = setup_environment.mcp_server_records([_HTTP_SERVER], live_entries=lambda _name: {'user': foreign})

        assert records == [{'name': 'old-srv', 'scopes': ['user'], 'sha256': {'user': None}}]

    def test_an_absent_or_unreadable_entry_is_recorded_without_a_digest(self) -> None:
        server = {**_HTTP_SERVER, 'scope': 'project'}

        absent = setup_environment.mcp_server_records([server], live_entries=lambda _name: {'project': None})
        unreadable = setup_environment.mcp_server_records([server], live_entries=lambda _name: None)

        assert absent == unreadable == [{'name': 'old-srv', 'scopes': ['project'], 'sha256': {'project': None}}]

    def test_a_profile_only_server_records_no_digest(self) -> None:
        records = setup_environment.mcp_server_records(
            [{**_HTTP_SERVER, 'scope': 'profile'}], live_entries=lambda _name: {'user': _LIVE_ENTRY},
        )

        assert records == [{'name': 'old-srv', 'scopes': ['profile'], 'sha256': {}}]


class TestItems:
    """A variable and a server are named by identity; their records carry no value."""

    def test_records_round_trip(self) -> None:
        for item in (_os_env_item('TOOL_HOME', 'v'), _mcp_item('old-srv', 'user', _LIVE_ENTRY)):
            assert LeftoverItem.from_record(item.to_record(), claude_dir=Path('/home/u/.claude')) == item

    def test_record_shapes(self) -> None:
        assert _os_env_item('TOOL_HOME', 'v').to_record() == {'kind': 'os-env', 'name': 'TOOL_HOME', 'sha256': digest('v')}
        assert _mcp_item('old-srv', 'local', _LIVE_ENTRY).to_record() == {
            'kind': 'mcp-server', 'name': 'old-srv', 'scope': 'local', 'sha256': digest(_LIVE_ENTRY),
        }

    def test_labels(self, tmp_path: Path) -> None:
        assert _os_env_item('TOOL_HOME', 'v').label() == 'OS environment variable: TOOL_HOME'
        assert _mcp_item('old-srv', 'user', _LIVE_ENTRY).label() == 'MCP server: old-srv (scope: user)'
        assert _os_env_item('TOOL_HOME', 'v').display(tmp_path) == 'OS environment variable: TOOL_HOME'

    def test_a_variable_differing_only_in_letter_case_is_the_same_item(self) -> None:
        assert _os_env_item('Tool_Home', 'v').key() == _os_env_item('TOOL_HOME', 'w').key()
        assert _mcp_item('Srv', 'user', {}).key() != _mcp_item('srv', 'user', {}).key()
        assert _mcp_item('srv', 'user', {}).key() != _mcp_item('srv', 'local', {}).key()

    @pytest.mark.parametrize('record', [
        {'kind': 'os-env', 'name': '1BAD', 'sha256': 'h'},
        {'kind': 'os-env', 'name': 'TWO WORDS', 'sha256': 'h'},
        {'kind': 'os-env', 'name': 'TOOL_HOME'},
        {'kind': 'os-env', 'name': 7, 'sha256': 'h'},
        {'kind': 'mcp-server', 'name': 'srv', 'scope': 'profile', 'sha256': 'h'},
        {'kind': 'mcp-server', 'name': 'srv', 'scope': 'everywhere', 'sha256': 'h'},
        {'kind': 'mcp-server', 'name': '', 'scope': 'user', 'sha256': 'h'},
        {'kind': 'mcp-server', 'name': 'srv', 'sha256': 'h'},
    ])
    def test_a_record_of_another_shape_is_no_item(self, record: dict[str, Any]) -> None:
        assert LeftoverItem.from_record(record, claude_dir=Path('/home/u/.claude')) is None


class TestCompute:
    """A re-run lists the recorded variables and servers its configuration no longer declares."""

    def _compute(
        self,
        manifest: dict[str, Any],
        config: dict[str, Any],
        machine: Machine,
        claude_dir: Path,
    ) -> LeftoverReport:
        return setup_environment.compute_profile_leftovers(
            {'leftovers': {}, **manifest}, claude_dir,
            profile_name='base',
            planned=setup_environment.planned_records(config, claude_dir, claude_dir=claude_dir, base=True),
            live=machine.live(),
            claude_dir=claude_dir,
        )

    def _states(self, report: LeftoverReport) -> list[tuple[str, str]]:
        return [(entry.item.label(), entry.state) for entry in report.entries]

    def test_a_variable_the_configuration_no_longer_sets_is_a_leftover(self, claude_dir: Path) -> None:
        machine = Machine()
        machine.env = {'TOOL_HOME': ('v',), 'KEPT': ('k',)}
        manifest = {'os_env_written': [
            {'name': 'TOOL_HOME', 'sha256': digest('v')}, {'name': 'KEPT', 'sha256': digest('k')},
        ]}

        report = self._compute(manifest, {'os-env-variables': {'KEPT': 'k2'}}, machine, claude_dir)

        assert self._states(report) == [('OS environment variable: TOOL_HOME', 'removable')]
        assert report.lines()[0] == '[leftover] OS environment variable: TOOL_HOME'
        assert report.lines(remove=True)[0] == '[remove] OS environment variable: TOOL_HOME'

    @pytest.mark.parametrize(('values', 'state'), [
        (('edited',), 'changed'),
        (('v', 'other'), 'changed'),
        ((), 'gone'),
    ])
    def test_the_live_value_decides(self, claude_dir: Path, values: tuple[str, ...], state: str) -> None:
        machine = Machine()
        machine.env = {'TOOL_HOME': values}

        report = self._compute(
            {'os_env_written': [{'name': 'TOOL_HOME', 'sha256': digest('v')}]}, {}, machine, claude_dir,
        )

        assert self._states(report) == [('OS environment variable: TOOL_HOME', state)]

    def test_an_unreadable_variable_is_carried(self, claude_dir: Path) -> None:
        machine = Machine()
        machine.unreadable = {'TOOL_HOME'}

        report = self._compute(
            {'os_env_written': [{'name': 'TOOL_HOME', 'sha256': digest('v')}]}, {}, machine, claude_dir,
        )

        assert self._states(report) == [('OS environment variable: TOOL_HOME', 'unreadable')]
        assert report.carried() == [_os_env_item('TOOL_HOME', 'v')]
        assert report.lines()[0] == (
            '[cannot check: the user environment cannot be read] OS environment variable: TOOL_HOME'
        )

    def test_a_variable_the_configuration_deletes_is_no_leftover(self, claude_dir: Path) -> None:
        """Step 7 deletes a variable the configuration declares null; it is the configuration's, not a leftover."""
        machine = Machine()
        machine.env = {'TOOL_HOME': ('v',)}

        report = self._compute(
            {'os_env_written': [{'name': 'TOOL_HOME', 'sha256': digest('v')}]},
            {'os-env-variables': {'TOOL_HOME': None}}, machine, claude_dir,
        )

        assert report.entries == ()

    def test_a_machine_wide_control_is_never_a_leftover(self, claude_dir: Path) -> None:
        machine = Machine()
        machine.env = {'DISABLE_UPDATES': ('1',)}
        record = {'kind': 'os-env', 'name': 'DISABLE_UPDATES', 'sha256': digest('1')}

        report = self._compute(
            {'os_env_written': [{'name': 'DISABLE_UPDATES', 'sha256': digest('1')}], 'leftovers': {'items': [record]}},
            {}, machine, claude_dir,
        )

        assert report.entries == ()

    def test_a_record_of_names_only_lists_nothing(self, claude_dir: Path) -> None:
        machine = Machine()
        machine.env = {'TOOL_HOME': ('v',)}

        report = self._compute({'os_env_written': ['TOOL_HOME']}, {}, machine, claude_dir)

        assert report.entries == ()

    def test_a_server_the_configuration_no_longer_declares_is_a_leftover(self, claude_dir: Path) -> None:
        machine = Machine()
        machine.mcp = {'old-srv': {'user': _LIVE_ENTRY, 'local': {'type': 'stdio', 'command': 'x'}}}
        manifest = {'mcp_servers': [{
            'name': 'old-srv', 'scopes': ['user', 'local'],
            'sha256': {'user': digest(_LIVE_ENTRY), 'local': None},
        }]}

        report = self._compute(manifest, {}, machine, claude_dir)

        assert self._states(report) == [('MCP server: old-srv (scope: user)', 'removable')]

    @pytest.mark.parametrize(('scopes', 'state'), [
        ({'user': {'type': 'http', 'url': 'https://moved.example/mcp'}}, 'changed'),
        ({}, 'gone'),
    ])
    def test_the_live_entry_decides(self, claude_dir: Path, scopes: dict[str, Any], state: str) -> None:
        machine = Machine()
        machine.mcp = {'old-srv': scopes}

        report = self._compute(
            {'mcp_servers': [{'name': 'old-srv', 'scopes': ['user'], 'sha256': {'user': digest(_LIVE_ENTRY)}}]},
            {}, machine, claude_dir,
        )

        assert self._states(report) == [('MCP server: old-srv (scope: user)', state)]

    def test_a_server_whose_registrations_cannot_be_read_is_carried(self, claude_dir: Path) -> None:
        machine = Machine()
        machine.unreadable = {'old-srv'}

        report = self._compute(
            {'mcp_servers': [{'name': 'old-srv', 'scopes': ['user'], 'sha256': {'user': digest(_LIVE_ENTRY)}}]},
            {}, machine, claude_dir,
        )

        assert self._states(report) == [('MCP server: old-srv (scope: user)', 'unreadable')]

    def test_a_server_the_configuration_declares_at_any_scope_is_no_leftover(self, claude_dir: Path) -> None:
        """Step 13 owns every scope of a declared name: it removes the stale registrations itself."""
        machine = Machine()
        machine.mcp = {'old-srv': {'user': _LIVE_ENTRY}}

        report = self._compute(
            {'mcp_servers': [{'name': 'old-srv', 'scopes': ['user'], 'sha256': {'user': digest(_LIVE_ENTRY)}}]},
            {'mcp-servers': [{**_HTTP_SERVER, 'scope': 'profile'}]}, machine, claude_dir,
        )

        assert report.entries == ()

    def test_carried_items_are_looked_at_again(self, claude_dir: Path) -> None:
        machine = Machine()
        machine.env = {'TOOL_HOME': ('v',)}
        machine.mcp = {'old-srv': {'project': _LIVE_ENTRY}}
        carried = [_os_env_item('TOOL_HOME', 'v').to_record(), _mcp_item('old-srv', 'project', _LIVE_ENTRY).to_record()]

        report = self._compute({'leftovers': {'items': carried}}, {}, machine, claude_dir)

        assert self._states(report) == [
            ('OS environment variable: TOOL_HOME', 'removable'), ('MCP server: old-srv (scope: project)', 'removable'),
        ]

    def test_the_report_orders_files_settings_variables_and_servers(self, claude_dir: Path) -> None:
        machine = Machine()
        machine.env = {'TOOL_HOME': ('v',)}
        machine.mcp = {'old-srv': {'user': _LIVE_ENTRY}}
        rule = claude_dir / 'rules' / 'old.md'
        rule.parent.mkdir()
        rule.write_bytes(b'rule')
        manifest = {
            'mcp_servers': [{'name': 'old-srv', 'scopes': ['user'], 'sha256': {'user': digest(_LIVE_ENTRY)}}],
            'os_env_written': [{'name': 'TOOL_HOME', 'sha256': digest('v')}],
            'files_written': [{'path': 'rules/old.md', 'sha256': setup_environment._sha256_of_file(rule)}],
        }
        live = LiveLeftoverState.for_profile(claude_dir, claude_dir.parent)
        report = setup_environment.compute_profile_leftovers(
            {'leftovers': {}, **manifest}, claude_dir,
            profile_name='base', planned=PlannedRecords(),
            live=LiveLeftoverState(
                file_digest=live.file_digest, under_link=live.under_link, destination_holders=lambda _dest: [],
                os_env=machine.read_env, mcp=machine.read_mcp,
            ),
            claude_dir=claude_dir,
        )

        assert [entry.item.kind for entry in report.entries] == ['file', 'os-env', 'mcp-server']


class TestStep23:
    """Step 23 removes each variable and server that still holds what the setup wrote, and checks it went."""

    def test_variables_leave_through_one_writer_call(self, claude_dir: Path) -> None:
        machine = Machine()
        machine.env = {'TOOL_HOME': ('v',), 'TOOL_PATH': ('p',)}
        calls: list[list[str]] = []
        writer = machine.writer()

        def _record(names: Sequence[str]) -> bool:
            calls.append(list(names))
            return writer(names)

        report = _report(
            claude_dir,
            LeftoverEntry(_os_env_item('TOOL_HOME', 'v'), 'removable'),
            LeftoverEntry(_os_env_item('TOOL_PATH', 'p'), 'removable'),
        )
        with patch.object(setup_environment, 'delete_toolbox_os_env_variables', side_effect=_record):
            removal = _step(report, machine, claude_dir=claude_dir, profile_dir=claude_dir)

        assert calls == [['TOOL_HOME', 'TOOL_PATH']]
        assert [(o.entry.item.label(), o.result) for o in removal.outcomes] == [
            ('OS environment variable: TOOL_HOME', 'removed'), ('OS environment variable: TOOL_PATH', 'removed'),
        ]
        assert machine.env == {}

    def test_a_variable_still_set_after_the_removal_failed(self, claude_dir: Path) -> None:
        machine = Machine()
        machine.env = {'TOOL_HOME': ('v',)}
        report = _report(claude_dir, LeftoverEntry(_os_env_item('TOOL_HOME', 'v'), 'removable'))

        with patch.object(setup_environment, 'delete_toolbox_os_env_variables', side_effect=machine.writer(deletes=False)):
            removal = _step(report, machine, claude_dir=claude_dir, profile_dir=claude_dir)

        [outcome] = removal.outcomes
        assert (outcome.result, outcome.detail) == ('failed', 'the variable is still set')
        assert removal.failed() == [outcome]

    def test_a_variable_changed_since_the_summary_is_left_alone(self, claude_dir: Path) -> None:
        machine = Machine()
        machine.env = {'TOOL_HOME': ('edited',)}
        report = _report(claude_dir, LeftoverEntry(_os_env_item('TOOL_HOME', 'v'), 'removable'))

        with patch.object(setup_environment, 'delete_toolbox_os_env_variables') as writer:
            removal = _step(report, machine, claude_dir=claude_dir, profile_dir=claude_dir)

        writer.assert_not_called()
        [outcome] = removal.outcomes
        assert (outcome.result, outcome.detail) == ('dropped', 'changed')
        assert machine.env == {'TOOL_HOME': ('edited',)}

    def test_a_variable_this_run_wrote_again_is_dropped(self, claude_dir: Path) -> None:
        machine = Machine()
        machine.env = {'TOOL_HOME': ('v',)}
        report = _report(claude_dir, LeftoverEntry(_os_env_item('TOOL_HOME', 'v'), 'removable'))
        written = setup_environment.written_leftover_records({
            'files_written': [], 'machine_wide_destinations': [], 'settings_written': [],
            'os_env_written': [{'name': 'TOOL_HOME', 'sha256': digest('v2')}], 'mcp_servers': [],
        })

        with patch.object(setup_environment, 'delete_toolbox_os_env_variables') as writer:
            removal = _step(report, machine, claude_dir=claude_dir, profile_dir=claude_dir, written=written)

        writer.assert_not_called()
        assert [(o.result, o.detail) for o in removal.outcomes] == [('dropped', 'written again')]

    def test_a_base_server_is_removed_from_the_base_registrations(self, claude_dir: Path) -> None:
        machine = Machine()
        machine.mcp = {'old-srv': {'user': _LIVE_ENTRY, 'local': {'type': 'stdio'}}}
        report = _report(claude_dir, LeftoverEntry(_mcp_item('old-srv', 'user', _LIVE_ENTRY), 'removable'))

        with (
            patch.object(setup_environment, 'find_command', return_value='/usr/bin/claude'),
            patch.object(setup_environment, '_remove_mcp_server_from_cli_scopes',
                         side_effect=machine.mcp_remover()) as remover,
        ):
            removal = _step(report, machine, claude_dir=claude_dir, profile_dir=claude_dir)

        remover.assert_called_once_with('/usr/bin/claude', 'old-srv', ['user'], None, None)
        assert [o.result for o in removal.outcomes] == ['removed']
        assert machine.mcp == {'old-srv': {'local': {'type': 'stdio'}}}, 'another scope stays'

    def test_an_isolated_server_is_removed_from_the_profile_registrations(self, claude_dir: Path) -> None:
        profile_dir = claude_dir / 'p'
        profile_dir.mkdir()
        machine = Machine()
        machine.mcp = {'old-srv': {'user': _LIVE_ENTRY}}
        report = _report(profile_dir, LeftoverEntry(_mcp_item('old-srv', 'user', _LIVE_ENTRY), 'removable'))

        with (
            patch.object(setup_environment, 'find_command', return_value='/usr/bin/claude'),
            patch.object(setup_environment, '_remove_mcp_server_from_cli_scopes',
                         side_effect=machine.mcp_remover()) as remover,
        ):
            removal = _step(report, machine, claude_dir=claude_dir, profile_dir=profile_dir)

        remover.assert_called_once_with('/usr/bin/claude', 'old-srv', ['user'], None, profile_dir)
        assert [o.result for o in removal.outcomes] == ['removed']

    def test_a_server_still_registered_after_the_removal_failed(self, claude_dir: Path) -> None:
        machine = Machine()
        machine.mcp = {'old-srv': {'user': _LIVE_ENTRY}}
        report = _report(claude_dir, LeftoverEntry(_mcp_item('old-srv', 'user', _LIVE_ENTRY), 'removable'))

        with (
            patch.object(setup_environment, 'find_command', return_value='/usr/bin/claude'),
            patch.object(setup_environment, '_remove_mcp_server_from_cli_scopes',
                         side_effect=machine.mcp_remover(removes=False)),
        ):
            removal = _step(report, machine, claude_dir=claude_dir, profile_dir=claude_dir)

        assert [(o.result, o.detail) for o in removal.outcomes] == [('failed', 'the server is still registered')]

    def test_a_server_whose_registrations_cannot_be_read_after_the_removal_failed(self, claude_dir: Path) -> None:
        machine = Machine()
        machine.mcp = {'old-srv': {'user': _LIVE_ENTRY}}
        report = _report(claude_dir, LeftoverEntry(_mcp_item('old-srv', 'user', _LIVE_ENTRY), 'removable'))

        def _remove_and_break(*_args: Any) -> None:
            machine.unreadable.add('old-srv')

        with (
            patch.object(setup_environment, 'find_command', return_value='/usr/bin/claude'),
            patch.object(setup_environment, '_remove_mcp_server_from_cli_scopes', side_effect=_remove_and_break),
        ):
            removal = _step(report, machine, claude_dir=claude_dir, profile_dir=claude_dir)

        assert [(o.result, o.detail) for o in removal.outcomes] == [('failed', '.claude.json cannot be read')]

    def test_without_the_claude_command_no_server_can_be_removed(self, claude_dir: Path) -> None:
        machine = Machine()
        machine.mcp = {'old-srv': {'user': _LIVE_ENTRY}}
        report = _report(claude_dir, LeftoverEntry(_mcp_item('old-srv', 'user', _LIVE_ENTRY), 'removable'))

        with (
            patch.object(setup_environment, 'find_command', return_value=None),
            patch.object(setup_environment, '_remove_mcp_server_from_cli_scopes') as remover,
        ):
            removal = _step(report, machine, claude_dir=claude_dir, profile_dir=claude_dir)

        remover.assert_not_called()
        assert [(o.result, o.detail) for o in removal.outcomes] == [('failed', 'claude command not found')]

    def test_without_the_flag_nothing_is_removed(self, claude_dir: Path) -> None:
        machine = Machine()
        machine.env = {'TOOL_HOME': ('v',)}
        report = _report(claude_dir, LeftoverEntry(_os_env_item('TOOL_HOME', 'v'), 'removable'))

        with patch.object(setup_environment, 'delete_toolbox_os_env_variables') as writer:
            removal = setup_environment.run_leftovers_step(
                report, remove=False, download_failed=False, written=PlannedRecords(),
                live=machine.live(), profile_dir=claude_dir, claude_dir=claude_dir,
                manifest_path=claude_dir / 'manifest.json', run_at='t',
            )

        assert removal is None
        writer.assert_not_called()

    def test_variables_and_servers_leave_after_the_files(self, claude_dir: Path) -> None:
        machine = Machine()
        machine.env = {'TOOL_HOME': ('v',)}
        machine.mcp = {'old-srv': {'user': _LIVE_ENTRY}}
        rule = claude_dir / 'rules' / 'old.md'
        rule.parent.mkdir()
        rule.write_bytes(b'rule')
        order: list[str] = []
        file_entry = LeftoverEntry(
            LeftoverItem('file', 'rules/old.md', setup_environment._sha256_of_file(rule)), 'removable',
        )
        report = _report(
            claude_dir,
            LeftoverEntry(_mcp_item('old-srv', 'user', _LIVE_ENTRY), 'removable'),
            LeftoverEntry(_os_env_item('TOOL_HOME', 'v'), 'removable'),
            file_entry,
        )
        live = LiveLeftoverState(
            file_digest=setup_environment._live_file_digest, under_link=lambda _relative: False,
            destination_holders=lambda _dest: [], os_env=machine.read_env, mcp=machine.read_mcp,
        )

        def _write(names: Sequence[str]) -> bool:
            order.append(f'env: rule present={rule.exists()}')
            return machine.writer()(names)

        def _remove(*args: Any) -> None:
            order.append(f'mcp: variable present={bool(machine.env)}')
            machine.mcp_remover()(*args)

        with (
            patch.object(setup_environment, 'find_command', return_value='/usr/bin/claude'),
            patch.object(setup_environment, 'delete_toolbox_os_env_variables', side_effect=_write),
            patch.object(setup_environment, '_remove_mcp_server_from_cli_scopes', side_effect=_remove),
        ):
            removal = setup_environment.run_leftovers_step(
                report, remove=True, download_failed=False, written=PlannedRecords(),
                live=live, profile_dir=claude_dir, claude_dir=claude_dir,
                manifest_path=claude_dir / 'manifest.json', run_at='t',
            )

        assert order == ['env: rule present=False', 'mcp: variable present=False']
        assert removal is not None
        assert [o.entry.item.kind for o in removal.outcomes] == ['file', 'os-env', 'mcp-server']
        assert all(o.result == 'removed' for o in removal.outcomes)


class TestFailedDownload:
    """A run whose content download failed removes no variable and no server; both stay recorded."""

    def test_a_failed_download_keeps_them_recorded(self, claude_dir: Path) -> None:
        machine = Machine()
        machine.env = {'OLD_VAR': ('v',)}
        machine.mcp = {'old-srv': {'user': _LIVE_ENTRY}}
        variable = LeftoverEntry(_os_env_item('OLD_VAR', 'v'), 'removable')
        server = LeftoverEntry(_mcp_item('old-srv', 'user', _LIVE_ENTRY), 'removable')
        report = _report(claude_dir, variable, server)
        manifest_path = claude_dir / 'manifest.json'
        manifest_path.write_text('{}', encoding='utf-8')

        with (
            patch.object(setup_environment, '_record_manifest_leftovers', _REAL_RECORD_MANIFEST_LEFTOVERS),
            patch.object(setup_environment, 'find_command', return_value='/usr/bin/claude'),
            patch.object(setup_environment, 'delete_toolbox_os_env_variables') as writer,
            patch.object(setup_environment, '_remove_mcp_server_from_cli_scopes') as remover,
        ):
            removal = setup_environment.run_leftovers_step(
                report, remove=True, download_failed=True, written=PlannedRecords(),
                live=machine.live(), profile_dir=claude_dir, claude_dir=claude_dir,
                manifest_path=manifest_path, run_at='t',
            )

        assert removal == LeftoverRemoval(skipped='content downloads failed')
        writer.assert_not_called()
        remover.assert_not_called()
        assert machine.env == {'OLD_VAR': ('v',)}
        assert json.loads(manifest_path.read_text(encoding='utf-8'))['leftovers']['items'] == [
            variable.item.to_record(), server.item.to_record(),
        ]


class TestMachineWideRow:
    """An isolated run names before consent each project-scope server it removes from the working directory."""

    def test_the_report_names_removable_project_servers(self, claude_dir: Path) -> None:
        report = _report(
            claude_dir / 'p',
            LeftoverEntry(_mcp_item('proj-srv', 'project', _LIVE_ENTRY), 'removable'),
            LeftoverEntry(_mcp_item('user-srv', 'user', _LIVE_ENTRY), 'removable'),
            LeftoverEntry(_mcp_item('edited-srv', 'project', _LIVE_ENTRY), 'changed'),
        )

        assert report.removable_project_mcp_servers() == ['proj-srv']

    def test_the_row_names_them(self, tmp_path: Path) -> None:
        writes = setup_environment.collect_machine_wide_writes(
            profile_dir=tmp_path / 'p', command_names=[], skip_install=True, install_version=None,
            keep_installed=False, pinned_version=None, ide_clis=[], os_level_env={}, mcp_servers=[],
            files_to_download=[], has_dependency_commands=False, leftover_mcp_servers=['proj-srv'],
        )

        assert writes == ['.mcp.json in the working directory: remove leftover project-scope MCP server(s) proj-srv']


class TestWrittenRecords:
    """Step 23 drops as written again a variable or a server this run's own steps wrote."""

    def test_written_names_cover_every_scope(self) -> None:
        written = setup_environment.written_leftover_records({
            'files_written': [], 'machine_wide_destinations': [], 'settings_written': [],
            'os_env_written': [{'name': 'TOOL_HOME', 'sha256': digest('v')}],
            'mcp_servers': [{'name': 'srv', 'scopes': ['profile'], 'sha256': {}}],
        })

        assert written.writes(_os_env_item('tool_home', 'other'))
        assert all(written.writes(_mcp_item('srv', scope, {})) for scope in ('user', 'local', 'project'))
        assert not written.writes(_mcp_item('other', 'user', {}))
