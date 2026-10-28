"""E2E tests for keeping an installed Node.js on the newest release of its LTS line.

With ``install-nodejs: true`` and no Node.js, the installation summary names
what Step 5 installs on the platform. With a Node.js already installed, the
setup reads the release index and schedule of the Node.js project before the
installation summary, names the decision there (and in --dry-run), carries
it out in Step 5 through the channel that owns the installation and repeats
the outcome in the completion summary. Every test runs main() in the
isolated home against a stub installation the test builds: the official
Windows installer's directory under a %PROGRAMFILES% in the temporary
directory, with a winget entry on PATH, on Windows; Homebrew's node@24 keg
linked into a prefix's bin directory on Linux and macOS. The release
documents come from tests/e2e/fixtures/nodejs, and every command and
installer download is recorded instead of run (see
tests/e2e/node_upgrade_support.py); a recorded command that succeeds makes
the stub report the upgraded release, as the real channel would.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any
from typing import NamedTuple

import pytest

from scripts import setup_environment
from tests.e2e.node_upgrade_support import FAILING_VARIABLE
from tests.e2e.node_upgrade_support import UNREACHABLE_VARIABLE
from tests.e2e.node_upgrade_support import UPGRADED_VERSION_VARIABLE
from tests.e2e.node_upgrade_support import VERSION_FILE_VARIABLE
from tests.e2e.node_upgrade_support import NodeCommandRecorder
from tests.e2e.node_upgrade_support import write_homebrew_node
from tests.e2e.node_upgrade_support import write_node
from tests.e2e.node_upgrade_support import write_winget
from tests.e2e.profile_support import run_main
from tests.e2e.profile_support import write_config

RUN_FLAGS = ['--yes', '--skip-install', '--no-admin']
WINGET_UPGRADE = [
    'winget', 'upgrade', '--id', 'OpenJS.NodeJS.LTS', '-e', '--version', '24.22.1', '--source', 'winget',
    '--accept-package-agreements', '--accept-source-agreements', '--silent', '--disable-interactivity',
]
NOTICE = 'Node.js 26 is the active LTS line; 24 is supported until 2028-04-30'
_ANSI = re.compile(r'\x1b\[[0-9;]*m')


class NodeLayout(NamedTuple):
    """A stub Node.js installation in the platform's recognized shape.

    Attributes:
        version_file: The file the stub node reports its release from.
        upgrade: The command the setup runs to upgrade it.
        channel: How the summary names that command.
        location: The installation directory a machine-wide upgrade writes,
            or None for one that needs no elevation.
    """

    version_file: Path
    upgrade: list[str]
    channel: str
    location: Path | None


def _prepend_path(monkeypatch: pytest.MonkeyPatch, directory: Path) -> None:
    monkeypatch.setenv('PATH', f'{directory}{os.pathsep}{os.environ["PATH"]}')


def _installed_node(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, version: str) -> NodeLayout:
    """Build the recognized installation of this platform at a release, and the upgrade it receives."""
    if sys.platform == 'win32':
        program_files = tmp_path / 'Program Files'
        _, version_file = write_node(program_files / 'nodejs', version)
        monkeypatch.setenv('PROGRAMFILES', str(program_files))
        _prepend_path(monkeypatch, write_winget(tmp_path / 'winget'))
        layout = NodeLayout(
            version_file, WINGET_UPGRADE, 'winget OpenJS.NodeJS.LTS or the official installer', program_files / 'nodejs',
        )
    else:
        bin_dir, version_file = write_homebrew_node(tmp_path / 'homebrew', 24, version)
        _prepend_path(monkeypatch, bin_dir)
        layout = NodeLayout(version_file, ['brew', 'upgrade', 'node@24'], 'brew upgrade node@24', None)
    monkeypatch.setenv(VERSION_FILE_VARIABLE, str(layout.version_file))
    monkeypatch.setenv(UPGRADED_VERSION_VARIABLE, '24.22.1')
    return layout


def _run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], flags: list[str] | None = None, **config: Any,
) -> tuple[int, str]:
    """Run the setup of a configuration with install-nodejs and return its exit code and output."""
    path = write_config(tmp_path, 'node.yaml', {'name': 'Node check', 'install-nodejs': True, **config})
    code = run_main([str(path), *(RUN_FLAGS if flags is None else flags)])
    captured = capsys.readouterr()
    return code, _ANSI.sub('', captured.out + captured.err)


def _reported_version(layout: NodeLayout) -> str:
    return layout.version_file.read_text(encoding='utf-8').strip()


@pytest.mark.usefixtures('e2e_isolated_home')
class TestOutdatedRelease:
    """An older release of a supported LTS line is upgraded to the newest one of that line."""

    def test_upgrade_runs_through_the_owning_channel_and_is_reported_everywhere(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
        node_command_recorder: NodeCommandRecorder,
    ) -> None:
        layout = _installed_node(tmp_path, monkeypatch, '24.19.0')

        code, output = _run(tmp_path, capsys)

        assert code == 0, output
        assert node_command_recorder.commands() == [layout.upgrade]
        assert _reported_version(layout) == 'v24.22.1'
        assert f'  * Node.js: 24.19.0 -> 24.22.1 through {layout.channel}' in output, 'the installation summary'
        assert f'    {NOTICE}' in output
        assert 'Node.js upgraded: 24.19.0 -> 24.22.1' in output, 'Step 5'
        assert '   * Node.js: 24.19.0 -> 24.22.1\n' in output, 'the completion summary'

    def test_dry_run_names_the_upgrade_and_changes_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
        node_command_recorder: NodeCommandRecorder,
    ) -> None:
        layout = _installed_node(tmp_path, monkeypatch, '24.19.0')

        code, output = _run(tmp_path, capsys, ['--dry-run', '--skip-install'])

        assert code == 0, output
        assert f'  * Node.js: 24.19.0 -> 24.22.1 through {layout.channel}' in output
        assert node_command_recorder.records() == []
        assert _reported_version(layout) == 'v24.19.0'
        assert 'Step 5' not in output

    def test_failed_upgrade_keeps_the_run_going_and_ends_with_exit_code_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
        node_command_recorder: NodeCommandRecorder,
    ) -> None:
        layout = _installed_node(tmp_path, monkeypatch, '24.19.0')
        monkeypatch.setenv(FAILING_VARIABLE, 'winget,msiexec,brew')

        code, output = _run(tmp_path, capsys)

        assert code == 1, output
        assert _reported_version(layout) == 'v24.19.0'
        assert 'Step 6: Installing dependencies...' in output, 'the run continues after the failed upgrade'
        assert 'Setup Completed with Errors' in output
        assert 'The Node.js upgrade failed:' in output
        assert f'  - Node.js 24.19.0 -> 24.22.1 through {layout.channel}: ' in output
        assert 'Node.js 24.19.0 still runs' in output
        retry = ' '.join(layout.upgrade)
        assert (f'retry: from an elevated terminal: {retry}' if layout.location else f'retry: {retry}') in output
        if sys.platform == 'win32':
            assert [record.get('download') or record['command'][0] for record in node_command_recorder.records()] == [
                'winget', 'https://nodejs.org/dist/v24.22.1/node-v24.22.1-x64.msi', 'msiexec',
            ]
        else:
            assert node_command_recorder.commands() == [layout.upgrade]

    def test_isolated_run_lists_the_upgrade_among_the_machine_wide_writes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
        node_command_recorder: NodeCommandRecorder,
    ) -> None:
        layout = _installed_node(tmp_path, monkeypatch, '24.19.0')

        code, output = _run(tmp_path, capsys, ['--dry-run', '--skip-install'], **{'command-names': ['node-check']})

        assert code == 0, output
        assert (
            f'[machine-wide] Node.js: upgrade 24.19.0 -> 24.22.1 through {layout.channel} (used by every profile)'
        ) in output
        assert node_command_recorder.records() == []


@pytest.mark.usefixtures('e2e_isolated_home')
class TestNothingToUpgrade:
    """A current release, an unrecognized installation and unreadable release data change nothing."""

    def test_current_release_runs_no_command(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
        node_command_recorder: NodeCommandRecorder,
    ) -> None:
        _installed_node(tmp_path, monkeypatch, '24.22.1')

        code, output = _run(tmp_path, capsys)

        assert code == 0, output
        assert node_command_recorder.records() == []
        assert '  * Node.js: 24.22.1 (the newest release of its LTS line)' in output
        assert '   * Node.js: 24.22.1 (the newest release of its LTS line)\n' in output
        assert NOTICE in output, 'the newer LTS line is named, and only named'

    def test_unrecognized_installation_is_left_unchanged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
        node_command_recorder: NodeCommandRecorder,
    ) -> None:
        executable, version_file = write_node(tmp_path / 'tools' / 'node', '24.19.0')
        _prepend_path(monkeypatch, executable.parent)
        # The official Windows installer's directory of this test holds no node
        monkeypatch.setenv('PROGRAMFILES', str(tmp_path / 'Program Files'))

        code, output = _run(tmp_path, capsys)

        assert code == 0, output
        assert node_command_recorder.records() == []
        assert version_file.read_text(encoding='utf-8').strip() == 'v24.19.0'
        assert 'Node.js 24.19.0 left unchanged: setup does not recognize the installation at' in output
        assert 'the newest release of line 24 is 24.22.1' in output
        assert '   * Node.js: 24.19.0 unchanged (setup does not recognize the installation at' in output

    @pytest.mark.parametrize('document', ['index', 'schedule'])
    def test_unreadable_release_data_warns_and_continues(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
        node_command_recorder: NodeCommandRecorder, document: str,
    ) -> None:
        layout = _installed_node(tmp_path, monkeypatch, '24.19.0')
        monkeypatch.setenv(UNREACHABLE_VARIABLE, document)

        code, output = _run(tmp_path, capsys)

        assert code == 0, output
        assert node_command_recorder.records() == []
        assert _reported_version(layout) == 'v24.19.0'
        assert f'Node.js 24.19.0 left unchanged: the Node.js release {document} at https://' in output
        assert 'could not be read: <urlopen error Temporary failure in name resolution>' in output

    def test_end_of_life_line_names_the_active_lts_line(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
        node_command_recorder: NodeCommandRecorder,
    ) -> None:
        _installed_node(tmp_path, monkeypatch, '20.19.0')

        code, output = _run(tmp_path, capsys)

        assert code == 0, output
        assert node_command_recorder.records() == []
        assert (
            'Node.js 20.19.0 left unchanged: release line 20 reached end of life on 2026-04-30; '
            'the active LTS line is 26'
        ) in output


def _platform_installs() -> str | None:
    """Name what Step 5 installs on this machine without Node.js, as the fixtures and the platform decide."""
    if sys.platform == 'win32':
        return "winget's OpenJS.NodeJS.LTS package, else the official installer of the newest LTS release"
    if sys.platform == 'darwin':
        # The Homebrew fixtures hold no node@26 yet, so the newest supported line Homebrew carries is 24
        homebrew = "Homebrew's node@24 (24.22.1)" if shutil.which('brew') else 'Homebrew, then its node@24 (24.22.1)'
        return f'{homebrew}, else the official installer package of the newest LTS release'
    if Path('/etc/debian_version').exists():
        return 'the nodejs package of the NodeSource LTS repository'
    return None


@pytest.mark.usefixtures('e2e_isolated_home')
class TestNoNodeInstalled:
    """Without Node.js, the summaries name what Step 5 installs on the platform."""

    def test_dry_run_names_what_step_5_installs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
        node_command_recorder: NodeCommandRecorder,
    ) -> None:
        # The official Windows installer's directory of this test holds no node
        monkeypatch.setenv('PROGRAMFILES', str(tmp_path / 'Program Files'))

        code, output = _run(tmp_path, capsys, ['--dry-run', '--skip-install'], **{'command-names': ['node-check']})

        assert code == 0, output
        installs = _platform_installs()
        if installs is None:
            assert (
                '  * Node.js: not found; Step 5 installs Node.js only on Debian and Ubuntu among Linux distributions, '
                'so install Node.js 18.0.0 or newer by hand'
            ) in output
            assert '[machine-wide] Node.js' not in output
        else:
            assert f'  * Node.js: not found; Step 5 installs {installs}\n' in output
            assert f'[machine-wide] Node.js: install {installs} (used by every profile)' in output
        assert node_command_recorder.records() == []


@pytest.mark.skipif(sys.platform != 'win32', reason='the machine-wide installation and its UAC gate exist on Windows')
@pytest.mark.usefixtures('e2e_isolated_home')
class TestWindowsElevation:
    """The upgrade of the machine-wide Windows installation needs an elevated run."""

    def test_no_admin_without_administrator_rights_skips_with_the_command(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
        node_command_recorder: NodeCommandRecorder,
    ) -> None:
        layout = _installed_node(tmp_path, monkeypatch, '24.19.0')
        monkeypatch.setattr(setup_environment, 'is_admin', lambda: False)

        code, output = _run(tmp_path, capsys)

        assert code == 0, output
        assert node_command_recorder.records() == []
        assert _reported_version(layout) == 'v24.19.0'
        command = ' '.join(WINGET_UPGRADE)
        assert (
            '    skipped: --no-admin keeps this run without administrator rights; run from an elevated terminal: '
            f'{command}'
        ) in output, 'the installation summary'
        assert f'Run it from an elevated terminal: {command}' in output, 'Step 5'
        assert f'   * Node.js: 24.19.0 unchanged (the upgrade to 24.22.1 needs an elevated run: {command})' in output

    def test_dry_run_lists_the_upgrade_among_the_elevation_reasons(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
        node_command_recorder: NodeCommandRecorder,
    ) -> None:
        layout = _installed_node(tmp_path, monkeypatch, '24.19.0')
        monkeypatch.setattr(setup_environment, 'is_admin', lambda: False)

        code, output = _run(tmp_path, capsys, ['--dry-run', '--skip-install'])

        assert code == 0, output
        assert 'Dry run: administrator elevation is not requested.' in output
        assert (
            f'  - Upgrading Node.js 24.19.0 -> 24.22.1 (machine-wide installation in {layout.location})'
        ) in output
        assert node_command_recorder.records() == []

    def test_failing_winget_falls_back_to_the_release_msi(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
        node_command_recorder: NodeCommandRecorder,
    ) -> None:
        layout = _installed_node(tmp_path, monkeypatch, '24.19.0')
        monkeypatch.setenv(FAILING_VARIABLE, 'winget')

        code, output = _run(tmp_path, capsys)

        assert code == 0, output
        records = node_command_recorder.records()
        assert [record.get('download') or record['command'][0] for record in records] == [
            'winget', 'https://nodejs.org/dist/v24.22.1/node-v24.22.1-x64.msi', 'msiexec',
        ]
        msiexec = records[2]['command']
        assert msiexec[:2] == ['msiexec', '/i']
        assert msiexec[2].endswith('node-v24.22.1-x64.msi')
        assert msiexec[3:5] == ['/qn', '/norestart']
        assert _reported_version(layout) == 'v24.22.1'
        assert '   * Node.js: 24.19.0 -> 24.22.1\n' in output
