"""Unit tests for keeping an installed Node.js on the newest release of its LTS line.

plan_node_upgrade() decides, before the installation summary, what Step 5
does with the node the step checks; install_nodejs_if_requested() then
performs that decision. The tests drive the planner with stub installations
and release documents, and the executor with recorded commands, so nothing
reaches the network, a package manager or the machine's Node.js.
"""

from __future__ import annotations

import argparse
import io
import subprocess
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from scripts import setup_environment
from scripts.setup_environment import NodeInstallation
from scripts.setup_environment import NodeStepResult
from scripts.setup_environment import NodeUpgradePlan

# tests/conftest.py replaces the planner for every unit test; these tests
# exercise the implementation captured at import time
plan_node_upgrade = setup_environment.plan_node_upgrade

TODAY = date(2026, 10, 28)
SCHEDULE: dict[str, Any] = {
    'v20': {'start': '2023-04-18', 'lts': '2023-10-24', 'maintenance': '2024-10-22', 'end': '2026-04-30'},
    'v22': {'start': '2024-04-24', 'lts': '2024-10-29', 'maintenance': '2025-10-21', 'end': '2027-04-30'},
    'v24': {'start': '2025-05-06', 'lts': '2025-10-28', 'maintenance': '2026-10-20', 'end': '2028-04-30'},
    'v25': {'start': '2025-10-15', 'maintenance': '2026-04-01', 'end': '2026-06-01'},
    'v26': {'start': '2026-05-05', 'lts': '2026-10-28', 'maintenance': '2027-10-20', 'end': '2029-04-30'},
    'v27': {'start': '2027-04-22', 'lts': '2027-10-20', 'end': '2030-04-30'},
}
INDEX: list[dict[str, Any]] = [
    {'version': 'v26.12.1', 'lts': False},
    {'version': 'v25.9.0', 'lts': False},
    {'version': 'v24.22.1', 'lts': 'Krypton'},
    {'version': 'v24.22.0', 'lts': 'Krypton'},
    {'version': 'v24.19.0', 'lts': 'Krypton'},
    {'version': 'v22.23.4', 'lts': 'Jod'},
    {'version': 'v20.20.2', 'lts': 'Iron'},
]
WINGET_UPGRADE = [
    'winget', 'upgrade', '--id', 'OpenJS.NodeJS.LTS', '-e', '--version', '24.22.1', '--source', 'winget',
    '--accept-package-agreements', '--accept-source-agreements', '--silent', '--disable-interactivity',
]


def _documents(url: str) -> object:
    """Answer the release index and the schedule the way nodejs.org and GitHub do."""
    return {setup_environment.NODE_RELEASE_INDEX_URL: INDEX, setup_environment.NODE_RELEASE_SCHEDULE_URL: SCHEDULE}[url]


def _plan(
    real_path: Path | str,
    version: str | None,
    *,
    system: str = 'Linux',
    path: Path | str | None = None,
    documents: object = _documents,
    today: date = TODAY,
    **patches: Any,
) -> NodeUpgradePlan:
    """Plan the Node.js step for one stub installation on one platform."""
    installation = NodeInstallation(str(path if path is not None else real_path), str(real_path))
    with (
        patch.object(setup_environment, '_locate_node', return_value=installation),
        patch.object(setup_environment, '_get_node_version', return_value=version),
        patch.object(setup_environment, '_fetch_node_release_json', side_effect=documents),
        patch.object(setup_environment.platform, 'system', return_value=system),
        patch.object(setup_environment, '_check_winget_available', return_value=patches.pop('winget', True)),
        patch.object(setup_environment, '_is_debian_family', return_value=patches.pop('debian', False)),
        patch.object(setup_environment, '_debian_nodejs_package_version', return_value=patches.pop('package', None)),
    ):
        assert not patches, patches
        return plan_node_upgrade(today=today)


class TestPlanReleaseData:
    """The release index and schedule decide; a document that cannot be read changes nothing."""

    @pytest.mark.parametrize(('missing', 'name'), [
        (setup_environment.NODE_RELEASE_INDEX_URL, 'index'),
        (setup_environment.NODE_RELEASE_SCHEDULE_URL, 'schedule'),
    ])
    def test_unreadable_document_leaves_node_unchanged(self, tmp_path: Path, missing: str, name: str) -> None:
        def documents(url: str) -> object:
            if url == missing:
                raise setup_environment.urllib.error.URLError('no route to host')
            return _documents(url)

        plan = _plan(tmp_path / 'node', 'v24.19.0', documents=documents)

        assert plan.action == 'unchanged'
        assert plan.installed == '24.19.0'
        assert plan.reason == f'the Node.js release {name} at {missing} could not be read: <urlopen error no route to host>'
        assert plan.summary_lines() == [f'Node.js: 24.19.0 unchanged ({plan.reason})']

    def test_malformed_document_leaves_node_unchanged(self, tmp_path: Path) -> None:
        plan = _plan(tmp_path / 'node', 'v24.19.0', documents=ValueError('Expecting value'))
        assert plan.action == 'unchanged'
        assert plan.reason is not None
        assert plan.reason.endswith('could not be read: Expecting value')

    def test_index_without_the_installed_line_leaves_node_unchanged(self, tmp_path: Path) -> None:
        def documents(url: str) -> object:
            if url == setup_environment.NODE_RELEASE_INDEX_URL:
                return [{'version': 'v26.12.1'}]
            return SCHEDULE

        plan = _plan(tmp_path / 'node', 'v24.19.0', documents=documents)
        assert plan.action == 'unchanged'
        assert plan.reason == 'the Node.js release index lists no release of line 24'


class TestPlanReleaseLines:
    """Only a supported LTS line is kept current; the others are named with the active LTS line."""

    def test_odd_line_is_left_unchanged(self, tmp_path: Path) -> None:
        plan = _plan(tmp_path / 'node', 'v25.2.0')
        assert plan.action == 'unchanged'
        assert plan.reason == '25 is an odd-numbered release line, which never becomes LTS; the active LTS line is 26'

    def test_end_of_life_line_is_left_unchanged(self, tmp_path: Path) -> None:
        plan = _plan(tmp_path / 'node', 'v20.19.0')
        assert plan.action == 'unchanged'
        assert plan.reason == 'release line 20 reached end of life on 2026-04-30; the active LTS line is 26'

    def test_line_not_yet_lts_is_left_unchanged(self, tmp_path: Path) -> None:
        plan = _plan(tmp_path / 'node', 'v26.11.0', today=date(2026, 10, 27))
        assert plan.action == 'unchanged'
        assert plan.reason == 'release line 26 becomes LTS on 2026-10-28; the active LTS line is 24'

    def test_line_missing_from_the_schedule_is_left_unchanged(self, tmp_path: Path) -> None:
        plan = _plan(tmp_path / 'node', 'v28.0.0')
        assert plan.action == 'unchanged'
        assert plan.reason == 'the Node.js release schedule lists no release line 28; the active LTS line is 26'

    def test_newest_release_of_a_supported_line_is_current_with_the_newer_line_named(self, tmp_path: Path) -> None:
        plan = _plan(tmp_path / 'node', 'v24.22.1')
        assert plan == NodeUpgradePlan(
            'current', installed='24.22.1', newest='24.22.1', executable=str(tmp_path / 'node'),
            notice='Node.js 26 is the active LTS line; 24 is supported until 2028-04-30',
        )
        assert plan.summary_lines() == [
            'Node.js: 24.22.1 (the newest release of its LTS line)',
            '  Node.js 26 is the active LTS line; 24 is supported until 2028-04-30',
        ]

    def test_active_line_has_no_notice(self, tmp_path: Path) -> None:
        plan = _plan(tmp_path / 'node', 'v26.12.1')
        assert plan.action == 'current'
        assert plan.notice is None

    def test_older_release_of_an_unrecognized_installation_is_left_unchanged(self, tmp_path: Path) -> None:
        plan = _plan(tmp_path / 'tools' / 'node', 'v24.19.0')
        assert plan.action == 'unchanged'
        assert plan.newest == '24.22.1'
        assert plan.remedy is None
        assert plan.reason == (
            f'setup does not recognize the installation at {tmp_path / "tools" / "node"}; '
            'the newest release of line 24 is 24.22.1'
        )
        assert plan.notice == 'Node.js 26 is the active LTS line; 24 is supported until 2028-04-30'


class TestPlanWindowsInstaller:
    """The official Windows installer in %ProgramFiles%\\nodejs is upgraded through winget or its MSI."""

    def _installer_dir(self, tmp_path: Path) -> Path:
        directory = tmp_path / 'Program Files' / 'nodejs'
        directory.mkdir(parents=True)
        return directory

    def test_outdated_release_is_upgraded_through_winget(self, tmp_path: Path) -> None:
        directory = self._installer_dir(tmp_path)
        with patch.object(setup_environment, '_windows_nodejs_dir', return_value=directory):
            plan = _plan(directory / 'node.exe', 'v24.19.0', system='Windows')

        assert plan.action == 'upgrade'
        assert plan.channel == 'windows-msi'
        assert plan.needs_elevation is True
        assert (plan.installed, plan.newest) == ('24.19.0', '24.22.1')
        assert plan.location == str(directory)
        assert plan.remedy == ' '.join(WINGET_UPGRADE)
        assert plan.elevation_reason() == (
            f'Upgrading Node.js 24.19.0 -> 24.22.1 (machine-wide installation in {directory})'
        )
        assert plan.summary_lines() == [
            'Node.js: 24.19.0 -> 24.22.1 through winget OpenJS.NodeJS.LTS or the official installer',
            f'  machine-wide installation in {directory}, which needs an elevated run',
            '  Node.js 26 is the active LTS line; 24 is supported until 2028-04-30',
        ]

    def test_without_winget_the_remedy_is_the_msi(self, tmp_path: Path) -> None:
        directory = self._installer_dir(tmp_path)
        with (
            patch.object(setup_environment, '_windows_nodejs_dir', return_value=directory),
            patch.object(setup_environment.platform, 'machine', return_value='AMD64'),
        ):
            plan = _plan(directory / 'node.exe', 'v24.19.0', system='Windows', winget=False)

        assert plan.channel == 'windows-msi'
        assert plan.remedy == (
            'download https://nodejs.org/dist/v24.22.1/node-v24.22.1-x64.msi and run: '
            'msiexec /i node-v24.22.1-x64.msi /qn /norestart'
        )

    def test_elsewhere_on_windows_is_not_recognized(self, tmp_path: Path) -> None:
        directory = self._installer_dir(tmp_path)
        with patch.object(setup_environment, '_windows_nodejs_dir', return_value=directory):
            plan = _plan(tmp_path / 'tools' / 'node.exe', 'v24.19.0', system='Windows')
        assert plan.action == 'unchanged'
        assert plan.reason is not None
        assert plan.reason.startswith('setup does not recognize the installation at')

    def test_an_unavailable_elevation_is_named_in_the_summary(self, tmp_path: Path) -> None:
        directory = self._installer_dir(tmp_path)
        with patch.object(setup_environment, '_windows_nodejs_dir', return_value=directory):
            plan = _plan(directory / 'node.exe', 'v24.19.0', system='Windows')
        lines = setup_environment.replace(plan, elevation_unavailable=True).summary_lines()
        assert lines[2] == (
            '  skipped: --no-admin keeps this run without administrator rights; run from an elevated terminal: '
            f'{" ".join(WINGET_UPGRADE)}'
        )


class TestPlanMacOSAndLinuxChannels:
    """Homebrew's node@<major>, the macOS installer package and NodeSource are upgraded; the rest is left alone."""

    def test_homebrew_formula_of_the_line_is_upgraded(self) -> None:
        cellar = '/opt/homebrew/Cellar/node@24/24.19.0/bin/node'
        plan = _plan(cellar, 'v24.19.0', system='Darwin', path='/opt/homebrew/opt/node@24/bin/node')
        assert plan.action == 'upgrade'
        assert plan.channel == 'homebrew'
        assert plan.needs_elevation is False
        assert plan.elevation_reason() is None
        assert plan.remedy == 'brew upgrade node@24'
        assert plan.executable == '/opt/homebrew/opt/node@24/bin/node'
        assert plan.summary_lines()[0] == 'Node.js: 24.19.0 -> 24.22.1 through brew upgrade node@24'

    def test_homebrew_unversioned_formula_is_left_unchanged(self) -> None:
        plan = _plan('/opt/homebrew/Cellar/node/24.19.0/bin/node', 'v24.19.0', system='Darwin')
        assert plan.action == 'unchanged'
        assert plan.reason is not None
        assert "Homebrew's node formula provides it" in plan.reason
        assert 'follows the newest Node.js release rather than an LTS line' in plan.reason

    def test_homebrew_formula_of_another_line_is_left_unchanged(self) -> None:
        plan = _plan('/usr/local/Cellar/node@22/24.19.0/bin/node', 'v24.19.0', system='Darwin')
        assert plan.action == 'unchanged'
        assert plan.reason is not None
        assert "Homebrew's node@22 formula provides it" in plan.reason

    def test_macos_installer_package_is_upgraded(self) -> None:
        plan = _plan('/usr/local/bin/node', 'v24.19.0', system='Darwin')
        assert plan.action == 'upgrade'
        assert plan.channel == 'macos-pkg'
        assert plan.remedy == (
            'curl -fLo node-v24.22.1.pkg https://nodejs.org/dist/v24.22.1/node-v24.22.1.pkg '
            '&& sudo installer -pkg node-v24.22.1.pkg -target /'
        )

    def test_usr_local_bin_off_macos_is_not_recognized(self) -> None:
        plan = _plan('/usr/local/bin/node', 'v24.19.0', system='Linux')
        assert plan.action == 'unchanged'

    def test_nodesource_package_is_upgraded(self) -> None:
        plan = _plan('/usr/bin/node', 'v24.19.0', debian=True, package='24.19.0-1nodesource1')
        assert plan.action == 'upgrade'
        assert plan.channel == 'nodesource'
        assert plan.remedy == 'sudo apt-get update && sudo apt-get install --only-upgrade -y nodejs'

    def test_distribution_package_is_left_unchanged(self) -> None:
        plan = _plan('/usr/bin/node', 'v24.19.0', debian=True, package='24.19.0+dfsg-1')
        assert plan.action == 'unchanged'
        assert plan.reason == (
            "the distribution's nodejs package 24.19.0+dfsg-1 provides it; the newest release of line 24 is 24.22.1"
        )

    def test_usr_bin_without_a_debian_package_is_not_recognized(self) -> None:
        plan = _plan('/usr/bin/node', 'v24.19.0', debian=False)
        assert plan.action == 'unchanged'
        assert plan.reason is not None
        assert plan.reason.startswith('setup does not recognize the installation at')


class TestPlanVersionManagers:
    """A version manager's installation is left to it, with its own command."""

    @pytest.mark.parametrize(('system', 'components', 'name', 'remedy'), [
        ('Linux', ('.nvm', 'versions', 'node', 'v24.19.0', 'bin', 'node'), 'nvm', 'nvm install 24.22.1'),
        (
            'Windows', ('AppData', 'Roaming', 'nvm', 'v24.19.0', 'node.exe'), 'nvm-windows',
            'nvm install 24.22.1, then nvm use 24.22.1',
        ),
        (
            'Darwin', ('.local', 'share', 'fnm', 'node-versions', 'v24.19.0', 'installation', 'bin', 'node'), 'fnm',
            'fnm install 24.22.1, then fnm default 24.22.1',
        ),
        ('Windows', ('AppData', 'Local', 'Volta', 'tools', 'image', 'node', '24.19.0', 'node.exe'), 'volta',
         'volta install node@24.22.1'),
        ('Linux', ('.asdf', 'installs', 'nodejs', '24.19.0', 'bin', 'node'), 'asdf', 'asdf install nodejs 24.22.1'),
        ('Linux', ('.local', 'share', 'mise', 'installs', 'node', '24.19.0', 'bin', 'node'), 'mise',
         'mise use -g node@24.22.1'),
    ])
    def test_manager_is_named_with_its_command(
        self, tmp_path: Path, system: str, components: tuple[str, ...], name: str, remedy: str,
    ) -> None:
        real_path = tmp_path.joinpath(*components)

        plan = _plan(real_path, 'v24.19.0', system=system)

        assert plan.action == 'unchanged'
        assert plan.remedy == remedy
        assert plan.reason == f'{name} manages it ({real_path}); the newest release of line 24 is 24.22.1'
        assert plan.summary_lines()[1] == f'  upgrade it with: {remedy}'

    def test_nvm_windows_symlink_in_program_files_is_the_manager(self, tmp_path: Path) -> None:
        """nvm-windows links %ProgramFiles%\\nodejs to its own directory, which the real path reveals."""
        directory = tmp_path / 'Program Files' / 'nodejs'
        directory.mkdir(parents=True)
        real_path = tmp_path / 'AppData' / 'Roaming' / 'nvm' / 'v24.19.0' / 'node.exe'
        with patch.object(setup_environment, '_windows_nodejs_dir', return_value=directory):
            plan = _plan(real_path, 'v24.19.0', system='Windows', path=directory / 'node.exe')
        assert plan.action == 'unchanged'
        assert plan.remedy == 'nvm install 24.22.1, then nvm use 24.22.1'

    def test_root_variable_names_a_relocated_manager(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = tmp_path / 'node-versions-root'
        monkeypatch.setenv('VOLTA_HOME', str(root))
        plan = _plan(root / 'tools' / 'image' / 'node' / '24.19.0' / 'bin' / 'node', 'v24.19.0')
        assert plan.remedy == 'volta install node@24.22.1'

    def test_posix_manager_is_not_matched_on_windows(self, tmp_path: Path) -> None:
        """The nvm marker of the POSIX tool is the dot directory; nvm-windows uses its own."""
        plan = _plan(tmp_path / '.nvm' / 'node.exe', 'v24.19.0', system='Windows')
        assert plan.reason is not None
        assert plan.reason.startswith('setup does not recognize')


def _upgrade_plan(channel: str, **fields: Any) -> NodeUpgradePlan:
    """A planned upgrade 24.19.0 -> 24.22.1 through one channel."""
    remedies = {
        'windows-msi': ' '.join(WINGET_UPGRADE),
        'homebrew': 'brew upgrade node@24',
        'macos-pkg': setup_environment._macos_pkg_command_text('24.22.1'),
        'nodesource': 'sudo apt-get update && sudo apt-get install --only-upgrade -y nodejs',
    }
    values: dict[str, Any] = {
        'installed': '24.19.0', 'newest': '24.22.1', 'executable': '/stub/node', 'location': '/stub',
        'channel': channel, 'remedy': remedies[channel],
    }
    values.update(fields)
    return NodeUpgradePlan('upgrade', **values)


class _Commands:
    """Records the Node.js commands Step 5 runs and answers each with a scripted result."""

    def __init__(self, results: dict[str, int | None] | None = None) -> None:
        self.calls: list[tuple[list[str], bool]] = []
        self.results = results or {}

    def __call__(self, command: list[str], *, sudo: bool = False) -> subprocess.CompletedProcess[str] | None:
        self.calls.append((list(command), sudo))
        code = self.results.get(command[0], 0)
        if code is None:
            return None
        return subprocess.CompletedProcess(command, code, '', '')


def _run_upgrade(
    plan: NodeUpgradePlan,
    versions: list[tuple[int, int, int] | None],
    commands: _Commands,
    *,
    admin: bool = True,
    winget: bool = True,
    download: MagicMock | None = None,
) -> NodeStepResult:
    """Run Step 5 for a planned upgrade with scripted node versions, before and after."""
    with (
        patch.object(setup_environment, '_node_version_parts', side_effect=versions),
        patch.object(setup_environment, '_run_nodejs_command', commands),
        patch.object(setup_environment, 'is_admin', return_value=admin),
        patch.object(setup_environment, '_check_winget_available', return_value=winget),
        patch.object(setup_environment, '_download_nodejs_installer', download or MagicMock(return_value='/tmp/node.msi')),
        patch.object(setup_environment, '_prepend_windows_nodejs_dir'),
        patch.object(setup_environment.os, 'unlink'),
        patch.object(
            setup_environment.platform, 'system', return_value='Windows' if plan.channel == 'windows-msi' else 'Darwin',
        ),
        patch.object(setup_environment.platform, 'machine', return_value='AMD64'),
    ):
        return setup_environment.install_nodejs_if_requested({'install-nodejs': True}, plan)


OLD = (24, 19, 0)
NEW = (24, 22, 1)


class TestStepFiveWithoutUpgrade:
    """A current or unchanged plan runs nothing and says why."""

    def test_current_plan_reports_the_release(self, capsys: pytest.CaptureFixture[str]) -> None:
        commands = _Commands()
        plan = NodeUpgradePlan(
            'current', installed='24.22.1', newest='24.22.1', notice='Node.js 26 is the active LTS line; 24 is supported',
        )
        with patch.object(setup_environment, '_run_nodejs_command', commands):
            result = setup_environment.install_nodejs_if_requested({'install-nodejs': True}, plan)
        assert result == NodeStepResult(True, 'Node.js: 24.22.1 (the newest release of its LTS line)')
        assert commands.calls == []
        out = capsys.readouterr().out
        assert 'Node.js 26 is the active LTS line; 24 is supported' in out

    def test_unchanged_plan_warns_with_the_remedy(self, capsys: pytest.CaptureFixture[str]) -> None:
        commands = _Commands()
        plan = NodeUpgradePlan(
            'unchanged', installed='24.19.0', newest='24.22.1', reason='nvm manages it (/x/node)',
            remedy='nvm install 24.22.1',
        )
        with patch.object(setup_environment, '_run_nodejs_command', commands):
            result = setup_environment.install_nodejs_if_requested({'install-nodejs': True}, plan)
        assert result == NodeStepResult(True, 'Node.js: 24.19.0 unchanged (nvm manages it (/x/node))')
        assert commands.calls == []
        out = capsys.readouterr().out
        assert 'Node.js 24.19.0 left unchanged: nvm manages it (/x/node)' in out
        assert 'Upgrade it with: nvm install 24.22.1' in out


class TestStepFiveWindowsUpgrade:
    """The Windows upgrade runs winget pinned to the release, else the release's MSI, in an elevated run only."""

    def test_winget_upgrades_to_the_release(self) -> None:
        commands = _Commands()
        result = _run_upgrade(_upgrade_plan('windows-msi'), [OLD, NEW, NEW], commands)
        assert result == NodeStepResult(True, 'Node.js: 24.19.0 -> 24.22.1')
        assert commands.calls == [(WINGET_UPGRADE, False)]

    def test_failing_winget_falls_back_to_the_msi(self) -> None:
        commands = _Commands({'winget': 1})
        download = MagicMock(return_value='/tmp/node-v24.22.1-x64.msi')
        result = _run_upgrade(_upgrade_plan('windows-msi'), [OLD, NEW], commands, download=download)
        assert result.line == 'Node.js: 24.19.0 -> 24.22.1'
        download.assert_called_once_with('https://nodejs.org/dist/v24.22.1/node-v24.22.1-x64.msi')
        assert [call[0][:3] for call in commands.calls] == [
            WINGET_UPGRADE[:3], ['msiexec', '/i', '/tmp/node-v24.22.1-x64.msi'],
        ]

    def test_winget_that_does_not_reach_the_release_falls_back_to_the_msi(self) -> None:
        commands = _Commands()
        result = _run_upgrade(_upgrade_plan('windows-msi'), [OLD, OLD, NEW], commands)
        assert result.line == 'Node.js: 24.19.0 -> 24.22.1'
        assert [call[0][0] for call in commands.calls] == ['winget', 'msiexec']

    def test_without_winget_the_msi_runs(self) -> None:
        commands = _Commands()
        result = _run_upgrade(_upgrade_plan('windows-msi'), [OLD, NEW], commands, winget=False)
        assert result.line == 'Node.js: 24.19.0 -> 24.22.1'
        assert [call[0][0] for call in commands.calls] == ['msiexec']

    def test_a_run_without_administrator_rights_skips_with_the_command(self, capsys: pytest.CaptureFixture[str]) -> None:
        commands = _Commands()
        result = _run_upgrade(_upgrade_plan('windows-msi'), [OLD], commands, admin=False)
        assert result.available is True
        assert result.failure is None
        assert result.line == (
            f'Node.js: 24.19.0 unchanged (the upgrade to 24.22.1 needs an elevated run: {" ".join(WINGET_UPGRADE)})'
        )
        assert commands.calls == []
        out = capsys.readouterr().out
        assert 'Node.js upgrade 24.19.0 -> 24.22.1 skipped' in out
        assert f'Run it from an elevated terminal: {" ".join(WINGET_UPGRADE)}' in out

    def test_failed_winget_and_msi_is_a_failure_with_the_retry(self) -> None:
        commands = _Commands({'winget': 1, 'msiexec': 1603})
        with patch.object(setup_environment, '_run_windows_msi', return_value=False):
            result = _run_upgrade(_upgrade_plan('windows-msi'), [OLD, OLD, OLD], commands)
        assert result.available is True
        assert result.line is None
        assert result.failure == (
            'Node.js 24.19.0 -> 24.22.1 through winget OpenJS.NodeJS.LTS or the official installer: '
            'the official installer failed (its log is shown above); Node.js 24.19.0 still runs'
        )
        assert result.retry == f'from an elevated terminal: {" ".join(WINGET_UPGRADE)}'

    def test_download_failure_is_a_failure(self) -> None:
        commands = _Commands({'winget': 1})
        download = MagicMock(side_effect=setup_environment.urllib.error.URLError('timed out'))
        result = _run_upgrade(_upgrade_plan('windows-msi'), [OLD, OLD], commands, download=download)
        assert result.failure is not None
        assert 'the official installer could not be downloaded from https://nodejs.org/dist/v24.22.1/' in result.failure

    def test_exact_channel_reporting_another_release_is_a_failure(self) -> None:
        commands = _Commands()
        result = _run_upgrade(_upgrade_plan('windows-msi'), [OLD, OLD, (24, 21, 0)], commands, winget=True)
        assert result.failure is not None
        assert 'the upgrade finished, but Node.js reports 24.21.0' in result.failure

    def test_node_that_no_longer_runs_is_unavailable(self, capsys: pytest.CaptureFixture[str]) -> None:
        commands = _Commands()
        result = _run_upgrade(_upgrade_plan('windows-msi'), [OLD, None], commands, winget=False)
        assert result == NodeStepResult(False)
        assert 'Node.js does not run after the upgrade attempt' in capsys.readouterr().err

    def test_release_already_reached_runs_nothing(self) -> None:
        commands = _Commands()
        result = _run_upgrade(_upgrade_plan('windows-msi'), [NEW], commands)
        assert result == NodeStepResult(True, 'Node.js: 24.22.1 (the newest release of its LTS line)')
        assert commands.calls == []


class TestStepFiveManagedChannels:
    """Homebrew and NodeSource install what they hold; the macOS package and apt-get need sudo."""

    def test_homebrew_upgrade(self) -> None:
        commands = _Commands()
        result = _run_upgrade(_upgrade_plan('homebrew'), [OLD, NEW], commands)
        assert result.line == 'Node.js: 24.19.0 -> 24.22.1'
        assert commands.calls == [(['brew', 'upgrade', 'node@24'], False)]

    def test_homebrew_without_the_newest_release_yet_is_no_failure(self, capsys: pytest.CaptureFixture[str]) -> None:
        result = _run_upgrade(_upgrade_plan('homebrew'), [OLD, OLD], _Commands())
        assert result == NodeStepResult(True, "Node.js: 24.19.0 unchanged (Homebrew's node@24 has no 24.22.1 yet)")
        assert "Node.js 24.19.0 left unchanged: Homebrew's node@24 has no 24.22.1 yet" in capsys.readouterr().out

    def test_homebrew_with_a_newer_but_not_the_newest_release(self) -> None:
        result = _run_upgrade(_upgrade_plan('homebrew'), [OLD, (24, 21, 0)], _Commands())
        assert result == NodeStepResult(
            True, "Node.js: 24.19.0 -> 24.21.0 (Homebrew's node@24 has no 24.22.1 yet)",
        )

    def test_homebrew_failure_names_the_retry(self) -> None:
        result = _run_upgrade(_upgrade_plan('homebrew'), [OLD, OLD], _Commands({'brew': 1}))
        assert result.failure == (
            'Node.js 24.19.0 -> 24.22.1 through brew upgrade node@24: brew exited with code 1; Node.js 24.19.0 still runs'
        )
        assert result.retry == 'brew upgrade node@24'

    def test_macos_package_runs_the_installer_with_sudo(self) -> None:
        commands = _Commands()
        download = MagicMock(return_value='/tmp/node-v24.22.1.pkg')
        result = _run_upgrade(_upgrade_plan('macos-pkg'), [OLD, NEW], commands, download=download)
        assert result.line == 'Node.js: 24.19.0 -> 24.22.1'
        download.assert_called_once_with('https://nodejs.org/dist/v24.22.1/node-v24.22.1.pkg')
        assert commands.calls == [(['installer', '-pkg', '/tmp/node-v24.22.1.pkg', '-target', '/'], True)]

    def test_macos_package_without_sudo_skips_with_the_command(self, capsys: pytest.CaptureFixture[str]) -> None:
        plan = _upgrade_plan('macos-pkg')
        result = _run_upgrade(plan, [OLD], _Commands({'installer': None}))
        assert result.failure is None
        assert result.line == f'Node.js: 24.19.0 unchanged (the upgrade to 24.22.1 needs sudo: {plan.remedy})'
        out = capsys.readouterr().out
        assert 'skipped: sudo cannot prompt for a password in this run' in out
        assert f'Run it yourself: {plan.remedy}' in out

    def test_nodesource_upgrade_runs_apt_get_with_sudo(self) -> None:
        commands = _Commands()
        result = _run_upgrade(_upgrade_plan('nodesource'), [OLD, NEW], commands)
        assert result.line == 'Node.js: 24.19.0 -> 24.22.1'
        assert commands.calls == [
            (['apt-get', 'update'], True), (['apt-get', 'install', '--only-upgrade', '-y', 'nodejs'], True),
        ]

    def test_nodesource_without_sudo_skips(self) -> None:
        result = _run_upgrade(_upgrade_plan('nodesource'), [OLD], _Commands({'apt-get': None}))
        assert result.failure is None
        assert result.line is not None
        assert 'needs sudo' in result.line

    def test_nodesource_failure_names_the_command(self) -> None:
        result = _run_upgrade(_upgrade_plan('nodesource'), [OLD, OLD], _Commands({'apt-get': 100}))
        assert result.failure is not None
        assert 'apt-get update exited with code 100' in result.failure
        assert result.retry == 'sudo apt-get update && sudo apt-get install --only-upgrade -y nodejs'


class TestElevationReasons:
    """An upgrade of the machine-wide Windows installation joins the single UAC gate."""

    WINDOWS_PLAN = _upgrade_plan('windows-msi', location=r'C:\Program Files\nodejs')
    REASON = r'Upgrading Node.js 24.19.0 -> 24.22.1 (machine-wide installation in C:\Program Files\nodejs)'

    def test_reason_follows_the_claude_code_install_and_precedes_the_dependencies(self) -> None:
        config = {'dependencies': {'common': ['npm install -g typescript']}}
        with patch.object(setup_environment.platform, 'system', return_value='Windows'):
            reasons = setup_environment.admin_elevation_reasons(
                config, argparse.Namespace(skip_install=False), node_upgrade=self.WINDOWS_PLAN,
            )
        assert reasons == [
            'Installing Claude Code (includes Node.js and Git)',
            self.REASON,
            'Global npm package: npm install -g typescript',
        ]

    @pytest.mark.parametrize('plan', [
        None,
        _upgrade_plan('homebrew'),
        NodeUpgradePlan('current', installed='24.22.1', newest='24.22.1'),
        NodeUpgradePlan('install', reason='not found'),
    ])
    def test_other_plans_need_no_elevation(self, plan: NodeUpgradePlan | None) -> None:
        with patch.object(setup_environment.platform, 'system', return_value='Windows'):
            assert setup_environment.admin_elevation_reasons(
                {}, argparse.Namespace(skip_install=True), node_upgrade=plan,
            ) == []

    def test_dry_run_lists_the_reason(self, capsys: pytest.CaptureFixture[str]) -> None:
        args = argparse.Namespace(skip_install=True, no_admin=False, dry_run=True)
        with (
            patch.object(setup_environment.platform, 'system', return_value='Windows'),
            patch.object(setup_environment, 'is_admin', return_value=False),
            patch.object(setup_environment, 'request_admin_elevation') as relaunch,
        ):
            setup_environment.request_admin_elevation_if_needed({}, args, node_upgrade=self.WINDOWS_PLAN)
        relaunch.assert_not_called()
        out = capsys.readouterr().out
        assert 'Dry run: administrator elevation is not requested.' in out
        assert f'  - {self.REASON}' in out

    def test_source_refresh_lists_the_reason_of_the_source_run(self, tmp_path: Path) -> None:
        refresh = setup_environment.SourceRefresh(
            'team-1', tmp_path / 'team-1', 'differs', 'digest', [], True, False, {'install-nodejs': True},
        )
        with patch.object(setup_environment.platform, 'system', return_value='Windows'):
            assert refresh.elevation_reasons(tmp_path, ['team-1'], node_upgrade=self.WINDOWS_PLAN) == [self.REASON]
            assert refresh.elevation_reasons(tmp_path, ['team-1']) == []

    def _profile(self, tmp_path: Path, name: str, link_source: str | None = None) -> setup_environment.InstalledProfile:
        manifest: dict[str, Any] = {'name': name}
        if link_source is not None:
            manifest['link'] = {'dirs': ['skills'], 'source': link_source}
        return setup_environment.InstalledProfile(name, tmp_path / name, tmp_path / name / 'manifest.json', manifest)

    @pytest.mark.parametrize(('run_all_commands', 'expected_checks'), [(False, 1), (True, 1)])
    def test_profile_all_checks_node_once_and_lists_the_reason_once(
        self, tmp_path: Path, run_all_commands: bool, expected_checks: int,
    ) -> None:
        profiles = [
            self._profile(tmp_path, 'team-1'),
            self._profile(tmp_path, 'team-2', link_source='team-1'),
            self._profile(tmp_path, 'solo'),
        ]
        args = argparse.Namespace(no_admin=False, dry_run=False, skip_install=True, run_all_commands=run_all_commands)
        planner = MagicMock(return_value=self.WINDOWS_PLAN)
        with (
            patch.object(setup_environment.platform, 'system', return_value='Windows'),
            patch.object(setup_environment, 'is_admin', return_value=False),
            patch.object(setup_environment, 'read_resolved_config_snapshot', return_value={'install-nodejs': True}),
            patch.object(setup_environment, 'default_scheduler_platform', return_value=MagicMock()),
            patch.object(setup_environment, 'plan_scheduled_update', return_value=MagicMock(changes_registration=False)),
            patch.object(setup_environment, 'plan_node_upgrade', planner),
        ):
            reasons = setup_environment.refresh_all_elevation_reasons(profiles, args)
        assert reasons == [self.REASON]
        assert planner.call_count == expected_checks

    def test_profile_all_without_install_nodejs_never_checks_node(self, tmp_path: Path) -> None:
        args = argparse.Namespace(no_admin=False, dry_run=False, skip_install=True, run_all_commands=False)
        planner = MagicMock(return_value=self.WINDOWS_PLAN)
        with (
            patch.object(setup_environment.platform, 'system', return_value='Windows'),
            patch.object(setup_environment, 'is_admin', return_value=False),
            patch.object(setup_environment, 'read_resolved_config_snapshot', return_value={}),
            patch.object(setup_environment, 'default_scheduler_platform', return_value=MagicMock()),
            patch.object(setup_environment, 'plan_scheduled_update', return_value=MagicMock(changes_registration=False)),
            patch.object(setup_environment, 'plan_node_upgrade', planner),
        ):
            reasons = setup_environment.refresh_all_elevation_reasons([self._profile(tmp_path, 'team-1')], args)
        assert reasons == []
        planner.assert_not_called()

    def test_profile_all_dependent_leaves_node_to_its_source(self, tmp_path: Path) -> None:
        args = argparse.Namespace(no_admin=False, dry_run=False, skip_install=True, run_all_commands=False)
        planner = MagicMock(return_value=self.WINDOWS_PLAN)
        with (
            patch.object(setup_environment.platform, 'system', return_value='Windows'),
            patch.object(setup_environment, 'is_admin', return_value=False),
            patch.object(setup_environment, 'read_resolved_config_snapshot', return_value={'install-nodejs': True}),
            patch.object(setup_environment, 'default_scheduler_platform', return_value=MagicMock()),
            patch.object(setup_environment, 'plan_scheduled_update', return_value=MagicMock(changes_registration=False)),
            patch.object(setup_environment, 'plan_node_upgrade', planner),
        ):
            reasons = setup_environment.refresh_all_elevation_reasons(
                [self._profile(tmp_path, 'team-2', link_source='team-1')], args,
            )
        assert reasons == []
        planner.assert_not_called()


class TestSummaries:
    """The installation summary and the machine-wide writes name the decision."""

    def _render(self, plan: setup_environment.InstallationPlan) -> str:
        output = io.StringIO()
        with patch.object(setup_environment.Colors, 'BOLD', ''), patch.object(setup_environment.Colors, 'NC', ''):
            setup_environment.display_installation_summary(plan, output=output)
        return output.getvalue()

    def _plan(self, node_upgrade: NodeUpgradePlan) -> setup_environment.InstallationPlan:
        return setup_environment.InstallationPlan(
            config_name='Node', config_source='node.yaml', config_source_type='local', config_version=None,
            install_nodejs=True, node_upgrade=node_upgrade,
        )

    def test_upgrade_rows(self) -> None:
        text = self._render(self._plan(_upgrade_plan(
            'windows-msi', location=r'C:\Program Files\nodejs',
            notice='Node.js 26 is the active LTS line; 24 is still supported',
        )))
        assert '  * Node.js: 24.19.0 -> 24.22.1 through winget OpenJS.NodeJS.LTS or the official installer\n' in text
        assert '    machine-wide installation in C:\\Program Files\\nodejs, which needs an elevated run\n' in text
        assert '    Node.js 26 is the active LTS line; 24 is still supported\n' in text

    def test_unchanged_rows(self) -> None:
        text = self._render(self._plan(NodeUpgradePlan(
            'unchanged', installed='24.19.0', reason='fnm manages it (/x)', remedy='fnm install 24.22.1',
        )))
        assert '  * Node.js: 24.19.0 unchanged (fnm manages it (/x))\n' in text
        assert '    upgrade it with: fnm install 24.22.1\n' in text

    def test_machine_wide_rows(self, tmp_path: Path) -> None:
        def writes(node_upgrade: NodeUpgradePlan | None) -> list[str]:
            return setup_environment.collect_machine_wide_writes(
                profile_dir=tmp_path / 'p', command_names=[], skip_install=True, install_version=None,
                keep_installed=False, pinned_version=None, ide_clis=[], os_level_env={}, mcp_servers=[],
                files_to_download=[], has_dependency_commands=False, node_upgrade=node_upgrade,
            )

        assert writes(_upgrade_plan('homebrew')) == [
            'Node.js: upgrade 24.19.0 -> 24.22.1 through brew upgrade node@24 (used by every profile)',
        ]
        machine_wide = _upgrade_plan('windows-msi', location=r'C:\Program Files\nodejs')
        assert writes(machine_wide) == [(
            'Node.js: upgrade 24.19.0 -> 24.22.1 through winget OpenJS.NodeJS.LTS or the official installer '
            '(used by every profile)'
        )]
        assert writes(setup_environment.replace(machine_wide, elevation_unavailable=True)) == [], (
            'an upgrade --no-admin skips writes nothing'
        )
        assert writes(NodeUpgradePlan('current', installed='24.22.1', newest='24.22.1')) == []
        assert writes(None) == []

    @pytest.mark.parametrize(('plan', 'performs'), [
        (_upgrade_plan('homebrew'), True),
        (_upgrade_plan('windows-msi'), True),
        (_upgrade_plan('windows-msi', elevation_unavailable=True), False),
        (NodeUpgradePlan('current', installed='24.22.1', newest='24.22.1'), False),
        (NodeUpgradePlan('unchanged', installed='24.19.0', reason='fnm manages it (/x)'), False),
        (NodeUpgradePlan('install', reason='not found', installs=('the NodeSource LTS repository',)), False),
    ])
    def test_performs_upgrade_agrees_with_the_summary_and_the_machine_wide_row(
        self, plan: NodeUpgradePlan, performs: bool,
    ) -> None:
        assert plan.performs_upgrade is performs
        upgrade_row = plan.machine_wide_row() or ''
        assert upgrade_row.startswith('Node.js: upgrade ') is performs
        skipped = any(line.strip().startswith('skipped:') for line in plan.summary_lines())
        assert skipped is (plan.action == 'upgrade' and not performs)


class TestInstallerPieces:
    """The shared installer pieces build the official URLs and commands."""

    @pytest.mark.parametrize(('system', 'machine', 'url'), [
        ('Windows', 'AMD64', 'https://nodejs.org/dist/v24.22.1/node-v24.22.1-x64.msi'),
        ('Darwin', 'arm64', 'https://nodejs.org/dist/v24.22.1/node-v24.22.1.pkg'),
        ('Darwin', 'x86_64', 'https://nodejs.org/dist/v24.22.1/node-v24.22.1.pkg'),
    ])
    def test_installer_url(self, system: str, machine: str, url: str) -> None:
        with (
            patch.object(setup_environment.platform, 'system', return_value=system),
            patch.object(setup_environment.platform, 'machine', return_value=machine),
        ):
            assert setup_environment._nodejs_installer_url('24.22.1') == url

    def test_installer_url_off_windows_and_macos_raises(self) -> None:
        with (
            patch.object(setup_environment.platform, 'system', return_value='Linux'),
            pytest.raises(ValueError, match='cover Windows and macOS'),
        ):
            setup_environment._nodejs_installer_url('24.22.1')

    def test_winget_install_command_keeps_its_scope_last(self) -> None:
        commands = _Commands()
        with (
            patch.object(setup_environment, '_check_winget_available', return_value=True),
            patch.object(setup_environment, '_run_nodejs_command', commands),
        ):
            assert setup_environment._install_nodejs_winget('machine') is True
        assert commands.calls == [([
            'winget', 'install', '--id', 'OpenJS.NodeJS.LTS', '-e', '--source', 'winget',
            '--accept-package-agreements', '--accept-source-agreements', '--silent', '--disable-interactivity',
            '--scope', 'machine',
        ], False)]

    def test_sudo_commands_go_through_the_fallback(self) -> None:
        with patch.object(setup_environment, '_run_with_sudo_fallback', return_value=None) as fallback:
            assert setup_environment._run_nodejs_command(['apt-get', 'update'], sudo=True) is None
        fallback.assert_called_once_with(['apt-get', 'update'], timeout=600, tty_timeout=600)

    def test_failed_download_deletes_the_temporary_file(self) -> None:
        created: list[str] = []

        def fail(_url: str, path: str) -> None:
            created.append(path)
            raise setup_environment.urllib.error.URLError('refused')

        with (
            patch.object(setup_environment, 'urlretrieve', side_effect=fail),
            pytest.raises(setup_environment.urllib.error.URLError),
        ):
            setup_environment._download_nodejs_installer('https://nodejs.org/dist/v24.22.1/node-v24.22.1.pkg')
        assert created
        assert created[0].endswith('.pkg')
        assert not Path(created[0]).exists()

    def test_newest_lts_release(self) -> None:
        assert setup_environment._newest_lts_release(INDEX) == '24.22.1'
        assert setup_environment._newest_lts_release([{'version': 'v26.0.0', 'lts': False}]) is None
        assert setup_environment._newest_lts_release({'not': 'a list'}) is None

    def test_locate_node_prefers_the_windows_installer_directory_off_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        directory = tmp_path / 'nodejs'
        directory.mkdir()
        other = tmp_path / 'other'

        def which(cmd: str, path: str | None = None) -> str | None:
            assert cmd == 'node'
            return str(directory / 'node.exe') if path == str(directory) else str(other / 'node.exe')

        monkeypatch.setenv('PATH', str(other))
        with (
            patch.object(setup_environment.platform, 'system', return_value='Windows'),
            patch.object(setup_environment, '_windows_nodejs_dir', return_value=directory),
            patch.object(setup_environment.shutil, 'which', side_effect=which),
        ):
            installation = setup_environment._locate_node()
        assert installation is not None
        assert installation.path == str(directory / 'node.exe')
        assert setup_environment.os.environ['PATH'] == str(other), 'locating node changes no PATH'
