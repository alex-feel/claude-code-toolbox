"""E2E tests for the leftovers among the base profile's OS environment variables and MCP servers.

The tests install the base profile of an isolated home through main() with
the real OS environment writer: on Linux and macOS it writes the toolbox
block of the isolated home's shell files, on Windows the fake user
environment the E2E conftest installs in place of HKCU\\Environment. The
configuration is then changed in place (its identity stays the same, as an
update of a remote configuration does) and the profile is re-run: the
summary lists each variable the configuration no longer sets, a run given
--remove-leftovers deletes in Step 23 each one still holding the value the
setup wrote, and a variable changed by hand is left alone. On Linux and
macOS the deletion takes only the line inside the toolbox block, so a line
the user wrote outside it stays. A base MCP server
is recorded and listed from the home's .claude.json, where the CLI keeps
user-scope servers; its removal through the real CLI is the subject of
tests/e2e/test_real_binary_leftovers.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts import setup_environment
from tests.e2e.leftovers_support import SKIP
from tests.e2e.leftovers_support import leftover_rows
from tests.e2e.leftovers_support import printed
from tests.e2e.profile_support import read_manifest
from tests.e2e.profile_support import run_main
from tests.e2e.profile_support import write_child_runner
from tests.e2e.profile_support import write_config
from tests.e2e.user_environment_fake import FakeUserEnvironment
from tests.e2e.validators import validate_manifest

FLAG = '--remove-leftovers'
DROPPED = 'CCT_E2E_LEFTOVER_TOOL'
KEPT = 'CCT_E2E_KEPT_TOOL'


def _config(variables: dict[str, str]) -> dict[str, Any]:
    return {'name': 'Base Env Vars', 'os-env-variables': variables}


def _read(name: str) -> tuple[str, ...]:
    return setup_environment.read_os_env_variable(name)


def _set_by_hand(name: str, value: str, fake: FakeUserEnvironment | None) -> None:
    """Change a variable where the setup keeps it, the way a user editing it by hand does."""
    if fake is not None:
        fake.write(name, value)
        return
    for config_file in setup_environment.get_all_shell_config_files():
        if config_file.is_file():
            assert setup_environment.add_export_to_file(config_file, name, value)


def _in_the_machines_user_environment(name: str) -> bool:
    """Report whether the real Windows user environment holds a variable."""
    if sys.platform != 'win32':
        return False
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as key:
        try:
            winreg.QueryValueEx(key, name)
        except FileNotFoundError:
            return False
    return True


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    """Where the base profile's configuration lives; each test rewrites it in place."""
    return tmp_path / 'configs' / 'base.yaml'


def _install(config_path: Path, variables: dict[str, str]) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    write_config(config_path.parent, config_path.name, _config(variables))
    assert run_main([str(config_path), *SKIP, '--yes'], real_os_env=True) == 0


@pytest.mark.usefixtures('e2e_isolated_home')
class TestOsEnvLeftovers:
    """A variable the configuration no longer sets is listed, and leaves only with the flag while still as set."""

    def test_a_dropped_variable_is_listed_then_removed_with_the_flag(
        self, e2e_isolated_home: dict[str, Path], config_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        claude_dir = e2e_isolated_home['claude_dir']
        _install(config_path, {DROPPED: 'one', KEPT: 'two'})
        assert _read(DROPPED) == ('one',)
        assert not _in_the_machines_user_environment(DROPPED), 'the machine keeps its own user environment'
        manifest = read_manifest(claude_dir)
        assert manifest['os_env_written'] == [
            {'name': DROPPED, 'sha256': setup_environment.leftover_digest('one')},
            {'name': KEPT, 'sha256': setup_environment.leftover_digest('two')},
        ]
        write_config(config_path.parent, config_path.name, _config({KEPT: 'two'}))
        capsys.readouterr()

        assert run_main([str(config_path), *SKIP, '--yes'], real_os_env=True) == 0

        output = printed(capsys)
        assert f'[leftover] OS environment variable: {DROPPED}' in leftover_rows(output)[0]
        assert _read(DROPPED) == ('one',), 'nothing is removed without the flag'
        manifest = read_manifest(claude_dir)
        assert not validate_manifest(claude_dir / 'manifest.json', _config({KEPT: 'two'}))
        assert manifest['leftovers']['items'] == [
            {'kind': 'os-env', 'name': DROPPED, 'sha256': setup_environment.leftover_digest('one')},
        ]

        assert run_main([str(config_path), *SKIP, '--yes', '--dry-run', FLAG], real_os_env=True) == 0

        output = printed(capsys)
        assert f'[would be removed in Step 23] OS environment variable: {DROPPED}' in leftover_rows(output)[0]
        assert _read(DROPPED) == ('one',), 'a dry run removes nothing'

        assert run_main([str(config_path), *SKIP, '--yes', FLAG], real_os_env=True) == 0

        output = printed(capsys)
        assert f'[remove] OS environment variable: {DROPPED}' in leftover_rows(output)[0]
        assert f'Removed leftover OS environment variable: {DROPPED}' in output
        assert output.index('Step 23:') < output.index(f'Removed leftover OS environment variable: {DROPPED}')
        assert _read(DROPPED) == ()
        assert _read(KEPT) == ('two',)
        leftovers = read_manifest(claude_dir)['leftovers']
        assert leftovers['removed'] == [f'OS environment variable: {DROPPED}']
        assert leftovers['items'] == []

    def test_a_variable_changed_by_hand_is_left_in_place(
        self,
        e2e_isolated_home: dict[str, Path],
        config_path: Path,
        fake_user_environment: FakeUserEnvironment | None,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        claude_dir = e2e_isolated_home['claude_dir']
        _install(config_path, {DROPPED: 'one', KEPT: 'two'})
        _set_by_hand(DROPPED, 'edited by hand', fake_user_environment)
        assert _read(DROPPED) == ('edited by hand',)
        write_config(config_path.parent, config_path.name, _config({KEPT: 'two'}))
        capsys.readouterr()

        assert run_main([str(config_path), *SKIP, '--yes', FLAG], real_os_env=True) == 0

        output = printed(capsys)
        assert leftover_rows(output)[0].strip() == (
            f'[changed since written: left in place, no longer tracked] OS environment variable: {DROPPED}'
        )
        assert f'Removed leftover OS environment variable: {DROPPED}' not in output
        assert _read(DROPPED) == ('edited by hand',)
        leftovers = read_manifest(claude_dir)['leftovers']
        assert leftovers['dropped'] == [{'label': f'OS environment variable: {DROPPED}', 'reason': 'changed'}]
        assert leftovers['items'] == []

    @pytest.mark.skipif(
        sys.platform == 'win32', reason='Windows keeps the variable in the user environment, which has no toolbox block',
    )
    def test_a_line_the_user_wrote_outside_the_toolbox_block_stays(
        self, e2e_isolated_home: dict[str, Path], config_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        claude_dir, bashrc = e2e_isolated_home['claude_dir'], e2e_isolated_home['home'] / '.bashrc'
        bashrc.write_text(f'# mine\nexport {DROPPED}="mine"\n', encoding='utf-8')
        _install(config_path, {DROPPED: 'one', KEPT: 'two'})
        assert bashrc.read_text(encoding='utf-8').startswith(f'# mine\nexport {DROPPED}="mine"\n')
        assert _read(DROPPED) == ('one',)
        write_config(config_path.parent, config_path.name, _config({KEPT: 'two'}))
        capsys.readouterr()

        assert run_main([str(config_path), *SKIP, '--yes', FLAG], real_os_env=True) == 0

        output = printed(capsys)
        assert f'Removed leftover OS environment variable: {DROPPED}' in output
        assert _read(DROPPED) == ()
        assert _read(KEPT) == ('two',)
        content = bashrc.read_text(encoding='utf-8')
        assert content.startswith(f'# mine\nexport {DROPPED}="mine"\n'), 'the line outside the block stays'
        assert f'export {DROPPED}="one"' not in content
        assert f'export {KEPT}="two"' in content
        leftovers = read_manifest(claude_dir)['leftovers']
        assert leftovers['removed'] == [f'OS environment variable: {DROPPED}']
        assert leftovers['items'] == []

    def test_child_runs_read_and_remove_what_the_parent_set(
        self,
        config_path: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capfd: pytest.CaptureFixture[str],
    ) -> None:
        """A --profile all child reads the variables the parent's run set, and removes them under the flag."""
        _install(config_path, {DROPPED: 'one', KEPT: 'two'})
        write_config(config_path.parent, config_path.name, _config({KEPT: 'two'}))
        runner = write_child_runner(tmp_path, monkeypatch)
        capfd.readouterr()

        assert run_main(['--profile', 'all', *SKIP, '--yes'], argv0=str(runner), real_os_env=True) == 0

        output = printed(capfd)
        assert f'[leftover] OS environment variable: {DROPPED}' in leftover_rows(output)[0]
        assert '       - 1 leftover(s); remove them with --profile base --remove-leftovers' in output
        assert _read(DROPPED) == ('one',)

        assert run_main(['--profile', 'all', *SKIP, '--yes', FLAG], argv0=str(runner), real_os_env=True) == 0

        output = printed(capfd)
        assert f'Removed leftover OS environment variable: {DROPPED}' in output
        assert '       - leftovers removed (1):\n           OS environment variable: ' + DROPPED in output
        assert _read(DROPPED) == ()
        assert _read(KEPT) == ('two',)


@pytest.mark.usefixtures('e2e_isolated_home')
class TestBaseMcpLeftovers:
    """A base profile records and lists its user-scope MCP servers from the home's .claude.json."""

    def test_a_dropped_server_is_listed_from_the_home_registrations(
        self,
        e2e_isolated_home: dict[str, Path],
        config_path: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        claude_dir = e2e_isolated_home['claude_dir']
        project = tmp_path / 'project'
        project.mkdir()
        monkeypatch.chdir(project)
        server = {'name': 'cct-e2e-lefty', 'scope': 'user', 'transport': 'http', 'url': 'http://127.0.0.1:9/lefty'}
        # Step 13 is replaced in these runs; this entry stands in for what
        # its `claude mcp add --scope user` stores in the home's .claude.json
        entry = {'type': 'http', 'url': server['url']}
        (e2e_isolated_home['home'] / '.claude.json').write_text(
            json.dumps({'mcpServers': {server['name']: entry}}), encoding='utf-8',
        )
        config_path.parent.mkdir(parents=True, exist_ok=True)
        write_config(config_path.parent, config_path.name, {'name': 'Base MCP', 'mcp-servers': [server]})

        assert run_main([str(config_path), *SKIP, '--yes']) == 0

        manifest = read_manifest(claude_dir)
        assert not validate_manifest(claude_dir / 'manifest.json', {'name': 'Base MCP', 'mcp-servers': [server]})
        assert manifest['mcp_servers'] == [{
            'name': server['name'], 'scopes': ['user'], 'sha256': {'user': setup_environment.leftover_digest(entry)},
        }]
        write_config(config_path.parent, config_path.name, {'name': 'Base MCP'})
        capsys.readouterr()

        assert run_main([str(config_path), *SKIP, '--yes']) == 0

        assert leftover_rows(printed(capsys))[0].strip() == f'[leftover] MCP server: {server["name"]} (scope: user)'
        assert read_manifest(claude_dir)['leftovers']['items'] == [{
            'kind': 'mcp-server', 'name': server['name'], 'scope': 'user',
            'sha256': setup_environment.leftover_digest(entry),
        }]

        assert run_main([str(config_path), *SKIP, '--yes', '--dry-run', FLAG]) == 0

        rows = leftover_rows(printed(capsys))
        assert rows[0].strip() == f'[would be removed in Step 23] MCP server: {server["name"]} (scope: user)'
