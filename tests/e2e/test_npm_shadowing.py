"""E2E tests for the warning about an older npm in the npm global prefix shadowing the bundled npm.

``npm install -g npm@<version>`` puts a separate npm copy into the npm global
prefix: ``%APPDATA%\\npm\\node_modules\\npm`` with an npm.cmd shim beside it on
Windows, ``<prefix>/lib/node_modules/npm`` with ``<prefix>/bin/npm`` on Linux
and macOS. The npm.cmd shim of Node.js runs that copy whenever it exists, and
a POSIX shell runs it when the prefix bin directory comes first on PATH, so
the newer npm each Node.js upgrade bundles never runs. Setup checks for that
in Step 5, after its Node.js step and before the Step 6 dependency commands:
it warns with both versions, both package directories and the commands that
remove or update the prefix copy, repeats the warning in the block that
closes the run, and changes nothing. A copy that is newer or equal, npm that
follows the bundled copy, an older npm that is not the global-prefix copy,
and every check that cannot determine a version print nothing and leave the
run's outcome alone.

Every test runs main() against a configuration on disk in the isolated home,
with a Node.js installation and an npm global prefix the test builds in the
platform's layout (tests/e2e/npm_layout_support.py) first on PATH, or, for a
machine without Node.js, a PATH that holds no node; the npm and node entries
there are stand-ins that answer the probes, so the machine's own npm is
never run or changed.
"""

from __future__ import annotations

import json
import shutil
import stat
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts import setup_environment
from tests.e2e.expected import EXPECTED_NPM_LAYOUT
from tests.e2e.npm_layout_support import NpmLayout
from tests.e2e.npm_layout_support import build_npm_layout
from tests.e2e.npm_layout_support import path_with
from tests.e2e.npm_layout_support import write_npm_entry
from tests.e2e.npm_layout_support import write_package
from tests.e2e.profile_support import run_main
from tests.e2e.profile_support import write_config
from tests.e2e.validators import validate_no_npm_shadowing_report
from tests.e2e.validators import validate_npm_shadowing_report

BUNDLED = '11.17.0'
STALE = '11.8.0'
RUN_FLAGS = ['--yes', '--skip-install', '--no-admin']
# The directory the Windows Node.js step adds to PATH when it exists and PATH
# lacks it; naming it on PATH keeps the test's own Node.js first
WINDOWS_NODEJS_DIR = r'C:\Program Files\nodejs'


def _real_node_installation() -> tuple[Path, str] | None:
    """The bundled npm of the Node.js on this machine's PATH and its version, when there is one."""
    node = shutil.which('node')
    if node is None:
        return None
    node_bin_dir = Path(node).parent
    node_root = node_bin_dir if EXPECTED_NPM_LAYOUT['node_bin_dir'] == '{node_root}' else node_bin_dir.parent
    bundled_dir = Path(EXPECTED_NPM_LAYOUT['bundled_npm'].format(node_root=node_root, npm_prefix=''))
    try:
        version = json.loads((bundled_dir / 'package.json').read_text(encoding='utf-8'))['version']
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return (bundled_dir, version) if isinstance(version, str) else None


REAL_NODE = _real_node_installation()


def _npm_prefix(home: dict[str, Path]) -> Path:
    """The npm global prefix of the isolated home.

    On Windows the builtin npmrc of the Node.js installer sets it to
    %APPDATA%\\npm; elsewhere the test configures ~/.npm-global, the prefix
    setup itself suggests for user-level global installs.

    Returns:
        The prefix directory.
    """
    if sys.platform == 'win32':
        return home['appdata_roaming'] / 'npm'
    return home['home'] / '.npm-global'


def _shadowing_order(layout: NpmLayout) -> tuple[Path, ...]:
    """PATH order under which the prefix copy runs.

    On Windows the machine PATH holding the Node.js directory precedes the
    user PATH holding %APPDATA%\\npm, and the npm.cmd shim of Node.js runs the
    prefix copy itself; on Linux and macOS the prefix bin directory is put
    first, as npm's own instructions for a user-level prefix do.

    Returns:
        The directories to put first on PATH, in order.
    """
    if sys.platform == 'win32':
        return (layout.node_bin_dir, layout.prefix_bin_dir)
    return (layout.prefix_bin_dir, layout.node_bin_dir)


def _use(
    monkeypatch: pytest.MonkeyPatch,
    layout: NpmLayout,
    directories: tuple[Path, ...] | None = None,
    *,
    keep_npm: bool = True,
    keep_node: bool = True,
) -> None:
    """Put the layout first on PATH and point npm at its global prefix."""
    monkeypatch.setenv('FAKE_NPM_LOG', str(layout.log))
    if sys.platform == 'win32':
        monkeypatch.delenv('NPM_CONFIG_PREFIX', raising=False)
    else:
        monkeypatch.setenv('NPM_CONFIG_PREFIX', str(layout.npm_prefix))
    order = directories if directories is not None else _shadowing_order(layout)
    monkeypatch.setenv('PATH', path_with(*order, keep_npm=keep_npm, keep_node=keep_node))


def _run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    config: dict[str, Any] | None = None,
) -> tuple[int, str]:
    """Run setup with a base configuration and return its exit code and output."""
    path = write_config(tmp_path, 'npm-check.yaml', {'name': 'npm check', **(config or {})})
    code = run_main([str(path), *RUN_FLAGS])
    captured = capsys.readouterr()
    return code, captured.out + captured.err


class TestShadowingCopyIsReported:
    """An older global-prefix copy that npm runs is reported, and nothing changes."""

    @pytest.mark.parametrize('install_nodejs', [False, True], ids=['without-install-nodejs', 'after-install-nodejs'])
    def test_stale_prefix_copy_is_reported_in_step_5_and_the_summary(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        install_nodejs: bool,
    ) -> None:
        layout = build_npm_layout(
            tmp_path, _npm_prefix(e2e_isolated_home), bundled_version=BUNDLED, prefix_version=STALE,
        )
        _use(monkeypatch, layout)
        if install_nodejs and sys.platform == 'win32':
            # The Windows Node.js step adds its standard directory to PATH when
            # PATH lacks it and then rebuilds PATH from the registry of the
            # machine running the suite; both would put that machine's npm first
            monkeypatch.setenv('PATH', f'{setup_environment.os.environ["PATH"]};{WINDOWS_NODEJS_DIR}')
            monkeypatch.setattr(setup_environment, 'refresh_path_from_registry', lambda: True)
        before = layout.package_bytes()

        code, output = _run(tmp_path, capsys, {'install-nodejs': install_nodejs})

        assert code == 0, output
        errors = validate_npm_shadowing_report(
            output,
            prefix_version=STALE,
            prefix_dir=layout.prefix_dir,
            bundled_version=BUNDLED,
            bundled_dir=layout.bundled_dir,
        )
        assert not errors, '\n'.join(errors)
        assert layout.package_bytes() == before
        assert (layout.prefix_dir / 'bin' / 'npm-cli.js').is_file()
        assert layout.npm_calls() == [['--version'], ['config', 'get', 'prefix']]

    def test_stale_prefix_copy_is_reported_when_setup_completes_with_errors(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        layout = build_npm_layout(
            tmp_path, _npm_prefix(e2e_isolated_home), bundled_version=BUNDLED, prefix_version=STALE,
        )
        _use(monkeypatch, layout)

        code, output = _run(tmp_path, capsys, {'dependencies': {'common': ['exit 1']}})

        assert code == 1, output
        assert 'Setup Completed with Errors' in output
        errors = validate_npm_shadowing_report(
            output,
            prefix_version=STALE,
            prefix_dir=layout.prefix_dir,
            bundled_version=BUNDLED,
            bundled_dir=layout.bundled_dir,
        )
        assert not errors, '\n'.join(errors)


class TestNoWarning:
    """npm that runs a copy at least as new as the bundled one is not reported."""

    def test_npm_follows_the_bundled_copy(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        layout = build_npm_layout(tmp_path, _npm_prefix(e2e_isolated_home), bundled_version=BUNDLED)
        _use(monkeypatch, layout)

        code, output = _run(tmp_path, capsys)

        assert code == 0, output
        errors = validate_no_npm_shadowing_report(output)
        assert not errors, '\n'.join(errors)
        assert layout.npm_calls() == [['--version']]

    @pytest.mark.parametrize('version', [BUNDLED, '11.18.0', '12.0.0'], ids=['equal', 'newer-minor', 'newer-major'])
    def test_prefix_copy_equal_or_newer(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        version: str,
    ) -> None:
        layout = build_npm_layout(
            tmp_path, _npm_prefix(e2e_isolated_home), bundled_version=BUNDLED, prefix_version=version,
        )
        _use(monkeypatch, layout)

        code, output = _run(tmp_path, capsys)

        assert code == 0, output
        errors = validate_no_npm_shadowing_report(output)
        assert not errors, '\n'.join(errors)
        assert layout.npm_calls() == [['--version']]

    @pytest.mark.skipif(
        sys.platform == 'win32',
        reason='the npm.cmd shim of Node.js runs a global-prefix copy whatever the PATH order',
    )
    def test_prefix_copy_behind_the_bundled_npm_on_path(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        layout = build_npm_layout(
            tmp_path, _npm_prefix(e2e_isolated_home), bundled_version=BUNDLED, prefix_version=STALE,
        )
        _use(monkeypatch, layout, (layout.node_bin_dir, layout.prefix_bin_dir))

        code, output = _run(tmp_path, capsys)

        assert code == 0, output
        errors = validate_no_npm_shadowing_report(output)
        assert not errors, '\n'.join(errors)
        assert layout.npm_calls() == [['--version']]

    @pytest.mark.parametrize('prefix_version', [None, '11.10.0'], ids=['no-prefix-copy', 'prefix-copy-of-another-version'])
    def test_older_npm_that_is_not_the_prefix_copy(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        prefix_version: str | None,
    ) -> None:
        """An older npm first on PATH that the global prefix does not hold is not reported.

        npm reports the older version, so the check asks npm for its global
        prefix; the prefix holds no copy, or a copy of another version, so
        the older npm is not the prefix copy and nothing is named.
        """
        layout = build_npm_layout(
            tmp_path, _npm_prefix(e2e_isolated_home), bundled_version=BUNDLED, prefix_version=prefix_version,
        )
        other_package = tmp_path / 'other-npm'
        other_bin_dir = tmp_path / 'other-bin'
        write_package(other_package, STALE)
        write_npm_entry(other_bin_dir, other_package, layout.stub)
        _use(monkeypatch, layout, (other_bin_dir, *_shadowing_order(layout)))
        before = layout.package_bytes()

        code, output = _run(tmp_path, capsys)

        assert code == 0, output
        errors = validate_no_npm_shadowing_report(output)
        assert not errors, '\n'.join(errors)
        assert layout.npm_calls() == [['--version'], ['config', 'get', 'prefix']]
        assert layout.package_bytes() == before


def _assert_silent_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Run setup and require exit 0 with no shadowing warning."""
    code, output = _run(tmp_path, capsys)
    assert code == 0, output
    errors = validate_no_npm_shadowing_report(output)
    assert not errors, '\n'.join(errors)


def _assert_reported_run(tmp_path: Path, capsys: pytest.CaptureFixture[str], layout: NpmLayout) -> None:
    """Run setup and require exit 0 with the warning about the stale prefix copy of the layout."""
    code, output = _run(tmp_path, capsys)
    assert code == 0, output
    errors = validate_npm_shadowing_report(
        output,
        prefix_version=STALE,
        prefix_dir=layout.prefix_dir,
        bundled_version=BUNDLED,
        bundled_dir=layout.bundled_dir,
    )
    assert not errors, '\n'.join(errors)


class TestUndeterminedChecksLeaveTheRunAlone:
    """A check that cannot determine a version prints no warning and the run completes.

    Each machine holds a stale prefix copy; the first run meets one thing the
    check cannot read and stays silent, and a second run after that one thing
    is repaired warns, so the silence comes from the undetermined value alone.
    """

    def test_npm_missing(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        layout = build_npm_layout(
            tmp_path,
            _npm_prefix(e2e_isolated_home),
            bundled_version=BUNDLED,
            prefix_version=STALE,
            bundled_npm_entry=False,
        )
        _use(monkeypatch, layout, (layout.node_bin_dir,), keep_npm=False)

        _assert_silent_run(tmp_path, capsys)
        assert layout.npm_calls() == []

        _use(monkeypatch, layout, (layout.node_bin_dir, layout.prefix_bin_dir), keep_npm=False)
        _assert_reported_run(tmp_path, capsys, layout)

    def test_no_node_on_path(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A machine without Node.js on PATH has no bundled npm to compare with."""
        layout = build_npm_layout(
            tmp_path, _npm_prefix(e2e_isolated_home), bundled_version=BUNDLED, prefix_version=STALE,
        )
        _use(monkeypatch, layout, (), keep_npm=False, keep_node=False)
        assert shutil.which('node') is None, 'a PATH entry still resolves node'

        _assert_silent_run(tmp_path, capsys)
        assert layout.npm_calls() == []

        _use(monkeypatch, layout)
        _assert_reported_run(tmp_path, capsys, layout)

    def test_node_without_a_bundled_npm(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        layout = build_npm_layout(
            tmp_path, _npm_prefix(e2e_isolated_home), bundled_version=None, prefix_version=STALE,
        )
        _use(monkeypatch, layout)

        _assert_silent_run(tmp_path, capsys)
        assert layout.npm_calls() == []

        write_package(layout.bundled_dir, BUNDLED)
        _assert_reported_run(tmp_path, capsys, layout)

    def test_unreadable_bundled_package_json(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        layout = build_npm_layout(
            tmp_path, _npm_prefix(e2e_isolated_home), bundled_version=BUNDLED, prefix_version=STALE,
        )
        (layout.bundled_dir / 'package.json').write_text('{"version": ', encoding='utf-8')
        _use(monkeypatch, layout)

        _assert_silent_run(tmp_path, capsys)
        assert layout.npm_calls() == []

        write_package(layout.bundled_dir, BUNDLED)
        _assert_reported_run(tmp_path, capsys, layout)

    def test_unreadable_prefix_copy(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """npm cannot report a version when the copy it runs has a broken package.json."""
        layout = build_npm_layout(
            tmp_path, _npm_prefix(e2e_isolated_home), bundled_version=BUNDLED, prefix_version=STALE,
        )
        (layout.prefix_dir / 'package.json').write_text('{"version": ', encoding='utf-8')
        _use(monkeypatch, layout)

        _assert_silent_run(tmp_path, capsys)
        assert layout.npm_calls() == [['--version']]

        write_package(layout.prefix_dir, STALE)
        _assert_reported_run(tmp_path, capsys, layout)

    def test_npm_fails(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        layout = build_npm_layout(
            tmp_path, _npm_prefix(e2e_isolated_home), bundled_version=BUNDLED, prefix_version=STALE,
        )
        _use(monkeypatch, layout)
        monkeypatch.setenv('FAKE_NPM_FAIL', '1')

        _assert_silent_run(tmp_path, capsys)
        assert layout.npm_calls() == [['--version']]

        monkeypatch.delenv('FAKE_NPM_FAIL')
        _assert_reported_run(tmp_path, capsys, layout)

    def test_npm_times_out(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        layout = build_npm_layout(
            tmp_path, _npm_prefix(e2e_isolated_home), bundled_version=BUNDLED, prefix_version=STALE,
        )
        _use(monkeypatch, layout)
        monkeypatch.setenv('FAKE_NPM_DELAY', '3')
        monkeypatch.setattr(setup_environment, 'NPM_PROBE_TIMEOUT_SECONDS', 1)

        _assert_silent_run(tmp_path, capsys)
        assert layout.npm_calls() == [['--version']]

        monkeypatch.delenv('FAKE_NPM_DELAY')
        _assert_reported_run(tmp_path, capsys, layout)

    def test_npm_prefix_probe_fails(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """npm reports an older version, then fails to report its global prefix."""
        layout = build_npm_layout(
            tmp_path, _npm_prefix(e2e_isolated_home), bundled_version=BUNDLED, prefix_version=STALE,
        )
        _use(monkeypatch, layout)
        monkeypatch.setenv('FAKE_NPM_FAIL', '1')
        monkeypatch.setenv('FAKE_NPM_ONLY_ARGS', 'config get prefix')

        _assert_silent_run(tmp_path, capsys)
        assert layout.npm_calls() == [['--version'], ['config', 'get', 'prefix']]

        monkeypatch.delenv('FAKE_NPM_FAIL')
        monkeypatch.delenv('FAKE_NPM_ONLY_ARGS')
        _assert_reported_run(tmp_path, capsys, layout)

    def test_npm_prefix_probe_times_out(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """npm reports an older version, then runs past the timeout asked for its global prefix."""
        layout = build_npm_layout(
            tmp_path, _npm_prefix(e2e_isolated_home), bundled_version=BUNDLED, prefix_version=STALE,
        )
        _use(monkeypatch, layout)
        monkeypatch.setenv('FAKE_NPM_DELAY', '3')
        monkeypatch.setenv('FAKE_NPM_ONLY_ARGS', 'config get prefix')
        monkeypatch.setattr(setup_environment, 'NPM_PROBE_TIMEOUT_SECONDS', 1)

        _assert_silent_run(tmp_path, capsys)
        assert layout.npm_calls() == [['--version'], ['config', 'get', 'prefix']]

        monkeypatch.delenv('FAKE_NPM_DELAY')
        monkeypatch.delenv('FAKE_NPM_ONLY_ARGS')
        _assert_reported_run(tmp_path, capsys, layout)


@pytest.mark.skipif(REAL_NODE is None, reason='no Node.js with a bundled npm on PATH')
class TestRealNpm:
    """The machine's own Node.js and npm run a copy of npm placed in a test-owned global prefix.

    The bundled npm of the Node.js on PATH is copied into a global prefix the
    test owns, with an older version in its package.json, the way
    ``npm install -g npm@<older>`` leaves it: on Windows the npm.cmd shim of
    Node.js finds the copy through the configured prefix and runs it; on
    Linux and macOS ``<prefix>/bin/npm`` links to it and comes first on PATH.
    The real npm answers setup's probes, so the warning names what the real
    npm runs, and the probes leave no debug log in the npm cache.
    """

    STALE_COPY = '1.0.0'

    def test_real_npm_running_a_stale_prefix_copy_is_reported(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert REAL_NODE is not None
        bundled_dir, bundled_version = REAL_NODE
        prefix = tmp_path / 'npm-prefix'
        prefix_dir = Path(EXPECTED_NPM_LAYOUT['prefix_npm'].format(node_root='', npm_prefix=prefix))
        # Copy file contents, never links: an installation whose files are relative
        # links into another tree (a package manager's linked install) would leave
        # links that resolve to nothing in the prefix copy. The copy keeps each
        # file's mode, and such an installation can hold read-only files, so the
        # copy's package.json is made writable before its version is changed
        shutil.copytree(bundled_dir, prefix_dir)
        package_json = prefix_dir / 'package.json'
        package_json.chmod(package_json.stat().st_mode | stat.S_IWUSR)
        manifest = json.loads(package_json.read_text(encoding='utf-8'))
        manifest['version'] = self.STALE_COPY
        (prefix_dir / 'package.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        monkeypatch.setenv('NPM_CONFIG_PREFIX', str(prefix))
        if sys.platform != 'win32':
            prefix_bin_dir = Path(EXPECTED_NPM_LAYOUT['prefix_bin_dir'].format(node_root='', npm_prefix=prefix))
            prefix_bin_dir.mkdir(parents=True)
            (prefix_bin_dir / 'npm').symlink_to(Path('..') / 'lib' / 'node_modules' / 'npm' / 'bin' / 'npm-cli.js')
            monkeypatch.setenv('PATH', path_with(prefix_bin_dir))
        copy_before = (prefix_dir / 'package.json').read_bytes()
        bundled_before = (bundled_dir / 'package.json').read_bytes()

        code, output = _run(tmp_path, capsys)

        assert code == 0, output
        errors = validate_npm_shadowing_report(
            output,
            prefix_version=self.STALE_COPY,
            prefix_dir=prefix_dir,
            bundled_version=bundled_version,
            bundled_dir=bundled_dir,
        )
        assert not errors, '\n'.join(errors)
        assert (prefix_dir / 'package.json').read_bytes() == copy_before
        assert (bundled_dir / 'package.json').read_bytes() == bundled_before
        cache = (
            e2e_isolated_home['appdata_local'] / 'npm-cache' if sys.platform == 'win32'
            else e2e_isolated_home['home'] / '.npm'
        )
        assert not (cache / '_logs').exists()
