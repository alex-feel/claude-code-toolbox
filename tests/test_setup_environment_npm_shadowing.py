"""Tests for the check that finds an older npm in the npm global prefix shadowing the bundled one.

``npm install -g npm@<version>`` puts a separate npm copy into the npm global
prefix. On Windows the npm.cmd shim of Node.js runs that copy whenever it
exists, and on Linux and macOS it runs when the prefix bin directory comes
first on PATH, so the npm bundled with each newer Node.js never runs. The
check compares the version npm reports with the npm bundled beside the
Node.js on PATH, names both copies and the commands that resolve it, and
changes nothing; anything it cannot determine yields no warning.

tests/conftest.py replaces find_shadowing_global_npm for every unit test,
because the real check runs the npm of the machine running the suite; these
tests call the implementation captured at import time.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts import setup_environment
from scripts.setup_environment import NPM_PROBE_ENVIRONMENT
from scripts.setup_environment import NPM_PROBE_TIMEOUT_SECONDS
from scripts.setup_environment import ShadowingNpm

find_shadowing_global_npm = setup_environment.find_shadowing_global_npm

BUNDLED = '11.17.0'
STALE = '11.8.0'


def _write_package(package_dir: Path, version: object) -> Path:
    """Write an npm package directory whose package.json declares the version."""
    (package_dir / 'bin').mkdir(parents=True, exist_ok=True)
    (package_dir / 'bin' / 'npm-cli.js').write_text('// npm\n', encoding='utf-8')
    (package_dir / 'package.json').write_text(json.dumps({'name': 'npm', 'version': version}), encoding='utf-8')
    return package_dir


class Machine:
    """A Node.js installation and an npm global prefix laid out for one platform."""

    def __init__(self, root: Path, *, windows: bool) -> None:
        self.windows = windows
        self.node_root = root / 'nodejs'
        self.prefix = root / 'npm-prefix'
        if windows:
            self.node = self.node_root / 'node.exe'
            self.bundled_dir = self.node_root / 'node_modules' / 'npm'
            self.prefix_dir = self.prefix / 'node_modules' / 'npm'
        else:
            self.node = self.node_root / 'bin' / 'node'
            self.bundled_dir = self.node_root / 'lib' / 'node_modules' / 'npm'
            self.prefix_dir = self.prefix / 'lib' / 'node_modules' / 'npm'
        self.node.parent.mkdir(parents=True)
        self.node.write_text('', encoding='utf-8')
        self.prefix.mkdir()
        self.answers: dict[tuple[str, ...], subprocess.CompletedProcess[str] | type[BaseException]] = {
            ('config', 'get', 'prefix'): subprocess.CompletedProcess([], 0, f'{self.prefix}\n', ''),
        }
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def reports(self, version: str) -> None:
        """Make npm --version print the version."""
        self.answers[('--version',)] = subprocess.CompletedProcess([], 0, f'{version}\n', '')

    def run_command(self, cmd: list[str], capture_output: bool = True, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        """Answer the npm probes the way this machine's npm would."""
        del capture_output
        self.calls.append((cmd, kwargs))
        answer = self.answers.get(tuple(cmd[1:]), subprocess.CompletedProcess(cmd, 1, '', 'unknown command'))
        if isinstance(answer, type):
            raise answer(cmd, kwargs.get('timeout', 0))
        return answer

    def which(self, name: str) -> str | None:
        """Resolve node to this machine's Node.js and nothing else."""
        return str(self.node) if name == 'node' else None

    def check(self) -> ShadowingNpm | None:
        """Run the check against this machine."""
        platform = 'win32' if self.windows else 'linux'
        with (
            patch('sys.platform', platform),
            patch.object(setup_environment.shutil, 'which', side_effect=self.which),
            patch.object(setup_environment, 'run_command', side_effect=self.run_command),
        ):
            return find_shadowing_global_npm()

    def probes(self) -> list[list[str]]:
        """The npm argument lists the check ran, in order."""
        return [cmd[1:] for cmd, _kwargs in self.calls]


@pytest.fixture(params=[True, False], ids=['windows-layout', 'posix-layout'])
def machine(request: pytest.FixtureRequest, tmp_path: Path) -> Machine:
    """A machine with Node.js bundling npm 11.17.0 and an empty npm global prefix, in each layout."""
    machine = Machine(tmp_path, windows=request.param)
    _write_package(machine.bundled_dir, BUNDLED)
    return machine


class TestShadowingCopyIsFound:
    """An older global-prefix copy that npm runs is reported with both copies."""

    def test_stale_prefix_copy_shadows_the_bundled_one(self, machine: Machine) -> None:
        _write_package(machine.prefix_dir, STALE)
        machine.reports(STALE)

        shadow = machine.check()

        assert shadow == ShadowingNpm(STALE, machine.prefix_dir, BUNDLED, machine.bundled_dir)
        assert machine.probes() == [['--version'], ['config', 'get', 'prefix']]

    def test_windows_copy_lives_in_the_prefix_node_modules(self, tmp_path: Path) -> None:
        machine = Machine(tmp_path, windows=True)
        _write_package(machine.bundled_dir, BUNDLED)
        _write_package(machine.prefix / 'node_modules' / 'npm', STALE)
        machine.reports(STALE)

        shadow = machine.check()

        assert shadow is not None
        assert shadow.prefix_dir == machine.prefix / 'node_modules' / 'npm'
        assert shadow.bundled_dir == machine.node.parent / 'node_modules' / 'npm'

    def test_posix_copy_lives_in_the_prefix_lib_node_modules(self, tmp_path: Path) -> None:
        machine = Machine(tmp_path, windows=False)
        _write_package(machine.bundled_dir, BUNDLED)
        _write_package(machine.prefix / 'lib' / 'node_modules' / 'npm', STALE)
        machine.reports(STALE)

        shadow = machine.check()

        assert shadow is not None
        assert shadow.prefix_dir == machine.prefix / 'lib' / 'node_modules' / 'npm'
        assert shadow.bundled_dir == machine.node.parent.parent / 'lib' / 'node_modules' / 'npm'

    def test_probes_run_read_only_with_a_timeout(self, machine: Machine) -> None:
        _write_package(machine.prefix_dir, STALE)
        machine.reports(STALE)

        machine.check()

        assert machine.calls
        for cmd, kwargs in machine.calls:
            assert cmd[0] == 'npm'
            assert kwargs['timeout'] == NPM_PROBE_TIMEOUT_SECONDS
            environment = kwargs['env']
            for key, value in NPM_PROBE_ENVIRONMENT.items():
                assert environment[key] == value
            assert environment['PATH'] == setup_environment.os.environ['PATH']

    def test_probe_environment_turns_off_the_update_check_and_log_files(self) -> None:
        assert NPM_PROBE_ENVIRONMENT == {'NPM_CONFIG_UPDATE_NOTIFIER': 'false', 'NPM_CONFIG_LOGS_MAX': '0'}


class TestNoWarning:
    """npm running a copy at least as new as the bundled one is not reported."""

    def test_npm_follows_the_bundled_copy(self, machine: Machine) -> None:
        machine.reports(BUNDLED)

        assert machine.check() is None
        assert machine.probes() == [['--version']]

    @pytest.mark.parametrize('version', [BUNDLED, '11.18.0', '12.0.0'])
    def test_prefix_copy_newer_or_equal(self, machine: Machine, version: str) -> None:
        _write_package(machine.prefix_dir, version)
        machine.reports(version)

        assert machine.check() is None
        assert machine.probes() == [['--version']]

    def test_older_npm_that_is_not_the_prefix_copy(self, machine: Machine) -> None:
        """An older npm from somewhere else on PATH is not a global-prefix copy."""
        machine.reports(STALE)

        assert machine.check() is None

    def test_prefix_copy_of_another_version_than_npm_reports(self, machine: Machine) -> None:
        _write_package(machine.prefix_dir, '11.9.0')
        machine.reports(STALE)

        assert machine.check() is None


class TestUndeterminedChecks:
    """A check that cannot determine a version reports nothing and raises nothing."""

    def test_node_not_on_path(self, machine: Machine) -> None:
        with (
            patch('sys.platform', 'win32' if machine.windows else 'linux'),
            patch.object(setup_environment.shutil, 'which', return_value=None),
            patch.object(setup_environment, 'run_command', side_effect=machine.run_command),
        ):
            assert find_shadowing_global_npm() is None
        assert machine.calls == []

    def test_node_without_a_bundled_npm(self, tmp_path: Path) -> None:
        machine = Machine(tmp_path, windows=False)
        machine.reports(STALE)

        assert machine.check() is None
        assert machine.calls == []

    @pytest.mark.parametrize(
        'content',
        ['{not json', '[]', '{"name": "npm"}', '{"version": 11}', '{"version": "next"}'],
        ids=['invalid-json', 'not-an-object', 'no-version', 'version-not-a-string', 'version-not-numeric'],
    )
    def test_bundled_package_json_without_a_version(self, machine: Machine, content: str) -> None:
        (machine.bundled_dir / 'package.json').write_text(content, encoding='utf-8')
        machine.reports(STALE)

        assert machine.check() is None
        assert machine.calls == []

    def test_bundled_package_json_not_utf8(self, machine: Machine) -> None:
        (machine.bundled_dir / 'package.json').write_bytes(b'\xff\xfe\x00{')
        machine.reports(STALE)

        assert machine.check() is None

    def test_npm_not_found(self, machine: Machine) -> None:
        _write_package(machine.prefix_dir, STALE)
        machine.answers[('--version',)] = subprocess.CompletedProcess([], 1, '', 'Command not found: npm')

        assert machine.check() is None

    @pytest.mark.parametrize('output', ['', 'npm warn something\n', 'v-next\n'])
    def test_npm_version_output_without_a_version(self, machine: Machine, output: str) -> None:
        _write_package(machine.prefix_dir, STALE)
        machine.answers[('--version',)] = subprocess.CompletedProcess([], 0, output, '')

        assert machine.check() is None

    def test_npm_version_times_out(self, machine: Machine) -> None:
        _write_package(machine.prefix_dir, STALE)
        machine.answers[('--version',)] = subprocess.TimeoutExpired

        assert machine.check() is None

    def test_npm_prefix_fails(self, machine: Machine) -> None:
        _write_package(machine.prefix_dir, STALE)
        machine.reports(STALE)
        machine.answers[('config', 'get', 'prefix')] = subprocess.CompletedProcess([], 1, '', 'error')

        assert machine.check() is None

    def test_npm_prefix_times_out(self, machine: Machine) -> None:
        _write_package(machine.prefix_dir, STALE)
        machine.reports(STALE)
        machine.answers[('config', 'get', 'prefix')] = subprocess.TimeoutExpired

        assert machine.check() is None

    def test_prefix_package_json_unreadable(self, machine: Machine) -> None:
        _write_package(machine.prefix_dir, STALE)
        (machine.prefix_dir / 'package.json').write_text('{broken', encoding='utf-8')
        machine.reports(STALE)

        assert machine.check() is None


class TestReport:
    """The warning names both versions, both copies and the commands that resolve it."""

    SHADOW = ShadowingNpm(STALE, Path('prefix') / 'npm', BUNDLED, Path('nodejs') / 'npm')

    def test_lines(self) -> None:
        assert self.SHADOW.lines() == [
            f'npm {STALE} in the npm global prefix runs instead of the npm {BUNDLED} bundled with Node.js',
            f'Global prefix copy: {Path("prefix") / "npm"}',
            f'Bundled copy: {Path("nodejs") / "npm"}',
            'To run the bundled copy, remove the global prefix copy: npm uninstall -g npm',
            f'Or update the global prefix copy to the bundled version: npm install -g npm@{BUNDLED}',
        ]

    def test_report_prints_the_warning_and_returns_the_shadow(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch.object(setup_environment, 'find_shadowing_global_npm', return_value=self.SHADOW):
            assert setup_environment.report_shadowing_global_npm() == self.SHADOW

        output = capsys.readouterr().out
        for line in self.SHADOW.lines():
            assert line in output
        assert 'Setup leaves both copies unchanged' in output

    def test_report_prints_nothing_without_a_shadow(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch.object(setup_environment, 'find_shadowing_global_npm', return_value=None):
            assert setup_environment.report_shadowing_global_npm() is None

        assert capsys.readouterr().out == ''

    def test_print_lists_every_line_as_a_warning(self, capsys: pytest.CaptureFixture[str]) -> None:
        setup_environment.print_shadowing_npm_warning(self.SHADOW)

        lines = capsys.readouterr().out.splitlines()
        assert len(lines) == len(self.SHADOW.lines())
        for printed, line in zip(lines, self.SHADOW.lines(), strict=True):
            assert 'WARN:' in printed
            assert printed.endswith(line)
