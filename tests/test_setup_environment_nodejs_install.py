"""Unit tests for installing Node.js on a machine without a usable one.

Without Node.js 18 or newer, plan_node_upgrade() plans an installation and
names what Step 5 installs on the platform: winget's LTS package or the
official MSI on Windows, Homebrew's formula of the newest supported LTS line
it carries or the official installer package on macOS, the NodeSource LTS
repository on Debian and Ubuntu. _ensure_nodejs() then installs through
those channels. The tests drive the planner with stub release documents and
the installer with recorded commands, so nothing reaches the network or a
package manager.
"""

from __future__ import annotations

import email.message
import io
import subprocess
import urllib.error
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from scripts import setup_environment
from scripts.setup_environment import NodeUpgradePlan
from tests.test_setup_environment_nodejs_upgrade import INDEX
from tests.test_setup_environment_nodejs_upgrade import SCHEDULE
from tests.test_setup_environment_nodejs_upgrade import TODAY

# tests/conftest.py replaces the planner for every unit test; these tests
# exercise the implementation captured at import time
plan_node_upgrade = setup_environment.plan_node_upgrade

# Homebrew's formulae of the Node.js lines on TODAY: node@26 does not exist
# yet, and the unversioned node formula follows the newest release
HOMEBREW: dict[str, dict[str, Any]] = {
    'node@24': {'name': 'node@24', 'versions': {'stable': '24.22.1'}, 'keg_only': True},
    'node@22': {'name': 'node@22', 'versions': {'stable': '22.23.4'}, 'keg_only': True},
    'node': {'name': 'node', 'versions': {'stable': '26.12.1'}, 'keg_only': False},
}
PACKAGE = 'the official installer package of the newest LTS release'


def _formula_url(formula: str) -> str:
    return setup_environment.NODE_HOMEBREW_FORMULA_URL.format(formula=formula)


def _http_error(url: str, code: int, message: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, message, email.message.Message(), None)


def _documents(formulae: dict[str, dict[str, Any]] = HOMEBREW) -> MagicMock:
    """Answer the release index and schedule and Homebrew's formulae, a missing formula with HTTP 404."""
    def answer(url: str) -> object:
        if url == setup_environment.NODE_RELEASE_INDEX_URL:
            return INDEX
        if url == setup_environment.NODE_RELEASE_SCHEDULE_URL:
            return SCHEDULE
        for name, document in formulae.items():
            if url == _formula_url(name):
                return document
        raise _http_error(url, 404, 'Not Found')

    return MagicMock(side_effect=answer)


def _install_plan(
    system: str,
    *,
    documents: MagicMock | None = None,
    brew: bool = True,
    debian: bool = False,
    today: date = TODAY,
) -> NodeUpgradePlan:
    """Plan the Node.js step of a machine without Node.js on one platform."""
    with (
        patch.object(setup_environment, '_locate_node', return_value=None),
        patch.object(setup_environment, '_fetch_node_release_json', documents or _documents()),
        patch.object(setup_environment.platform, 'system', return_value=system),
        patch.object(setup_environment, '_check_homebrew_available', return_value=brew),
        patch.object(setup_environment, '_is_debian_family', return_value=debian),
    ):
        return plan_node_upgrade(today=today)


class TestInstallPlanPerPlatform:
    """The installation plan names what Step 5 installs on the platform."""

    def test_windows_names_winget_then_the_official_installer(self) -> None:
        documents = _documents()
        plan = _install_plan('Windows', documents=documents)

        assert plan.action == 'install'
        assert plan.homebrew_formula is None
        assert plan.summary_lines() == [
            (
                "Node.js: not found; Step 5 installs winget's OpenJS.NodeJS.LTS package, "
                'else the official installer of the newest LTS release'
            ),
        ]
        documents.assert_not_called()

    def test_debian_names_the_nodesource_lts_repository(self) -> None:
        documents = _documents()
        plan = _install_plan('Linux', documents=documents, debian=True)

        assert plan.summary_lines() == [
            'Node.js: not found; Step 5 installs the nodejs package of the NodeSource LTS repository',
        ]
        documents.assert_not_called()

    def test_other_linux_distributions_have_no_installer(self) -> None:
        plan = _install_plan('Linux', debian=False)

        assert plan.installs == ()
        assert plan.summary_lines() == [
            (
                'Node.js: not found; Step 5 installs Node.js only on Debian and Ubuntu among Linux distributions, '
                'so install Node.js 18.0.0 or newer by hand'
            ),
        ]

    def test_macos_takes_the_newest_supported_line_homebrew_carries(self) -> None:
        documents = _documents()
        plan = _install_plan('Darwin', documents=documents)

        assert plan.homebrew_formula == 'node@24'
        assert plan.summary_lines() == [
            f"Node.js: not found; Step 5 installs Homebrew's node@24 (24.22.1), else {PACKAGE}",
        ]
        # Line 27 is not LTS on TODAY, so its formula is never asked for
        assert [call.args[0] for call in documents.call_args_list] == [
            setup_environment.NODE_RELEASE_SCHEDULE_URL, _formula_url('node@26'), _formula_url('node@24'),
        ]

    def test_macos_takes_the_newest_line_once_homebrew_carries_it(self) -> None:
        formulae = {**HOMEBREW, 'node@26': {'name': 'node@26', 'versions': {'stable': '26.12.1'}}}
        plan = _install_plan('Darwin', documents=_documents(formulae))

        assert plan.homebrew_formula == 'node@26'
        assert plan.installs[0] == "Homebrew's node@26 (26.12.1)"

    def test_macos_leaves_out_a_line_past_its_end_of_life(self) -> None:
        # Line 22 reaches end of life on 2027-04-30 while Homebrew still carries node@22
        documents = _documents({'node@22': HOMEBREW['node@22']})
        plan = _install_plan('Darwin', documents=documents, today=date(2027, 5, 1))

        assert plan.homebrew_formula is None
        assert _formula_url('node@22') not in [call.args[0] for call in documents.call_args_list]
        assert plan.installs == (f'{PACKAGE} (Homebrew is skipped: Homebrew carries none of node@26, node@24)',)

    def test_macos_without_brew_installs_homebrew_first(self) -> None:
        plan = _install_plan('Darwin', brew=False)

        assert plan.homebrew_formula == 'node@24'
        assert plan.installs == ('Homebrew, then its node@24 (24.22.1)', PACKAGE)

    def test_macos_without_a_carried_formula_skips_homebrew(self) -> None:
        plan = _install_plan('Darwin', documents=_documents({}))

        assert plan.homebrew_formula is None
        assert plan.summary_lines() == [
            (
                f'Node.js: not found; Step 5 installs {PACKAGE} '
                '(Homebrew is skipped: Homebrew carries none of node@26, node@24, node@22)'
            ),
        ]

    def test_macos_with_an_unreadable_schedule_skips_homebrew(self) -> None:
        documents = MagicMock(side_effect=urllib.error.URLError('no route to host'))
        plan = _install_plan('Darwin', documents=documents)

        assert plan.homebrew_formula is None
        assert plan.installs == (
            (
                f'{PACKAGE} (Homebrew is skipped: the Node.js release schedule at '
                f'{setup_environment.NODE_RELEASE_SCHEDULE_URL} could not be read: <urlopen error no route to host>)'
            ),
        )

    @pytest.mark.parametrize(('failure', 'text'), [
        (_http_error(_formula_url('node@26'), 503, 'Service Unavailable'), 'HTTP Error 503: Service Unavailable'),
        (urllib.error.URLError('no route to host'), '<urlopen error no route to host>'),
        (ValueError('Expecting value'), 'Expecting value'),
    ])
    def test_macos_with_an_unreadable_formula_skips_homebrew(self, failure: Exception, text: str) -> None:
        def answer(url: str) -> object:
            if url == setup_environment.NODE_RELEASE_SCHEDULE_URL:
                return SCHEDULE
            raise failure

        plan = _install_plan('Darwin', documents=MagicMock(side_effect=answer))

        assert plan.homebrew_formula is None
        assert plan.installs == (
            (
                f"{PACKAGE} (Homebrew is skipped: Homebrew's formula node@26 at {_formula_url('node@26')} "
                f'could not be read: {text})'
            ),
        )

    def test_macos_formula_without_a_stable_version_skips_homebrew(self) -> None:
        plan = _install_plan('Darwin', documents=_documents({'node@26': {'name': 'node@26', 'versions': {}}}))

        assert plan.homebrew_formula is None
        skipped = f"Homebrew's formula node@26 at {_formula_url('node@26')} names no stable version"
        assert plan.installs == (f'{PACKAGE} (Homebrew is skipped: {skipped})',)

    @pytest.mark.parametrize(('version', 'reason'), [
        (None, '{node} reports no version'),
        ('v16.20.2', '16.20.2 is older than 18.0.0'),
    ])
    def test_an_unusable_node_is_replaced_through_the_same_channels(
        self, tmp_path: Path, version: str | None, reason: str,
    ) -> None:
        node = str(tmp_path / 'node')
        with (
            patch.object(setup_environment, '_locate_node', return_value=setup_environment.NodeInstallation(node, node)),
            patch.object(setup_environment, '_get_node_version', return_value=version),
            patch.object(setup_environment, '_fetch_node_release_json', _documents()),
            patch.object(setup_environment.platform, 'system', return_value='Darwin'),
            patch.object(setup_environment, '_check_homebrew_available', return_value=True),
        ):
            plan = plan_node_upgrade(today=TODAY)

        assert plan.action == 'install'
        assert plan.executable == node
        assert plan.reason == reason.format(node=node)
        assert plan.homebrew_formula == 'node@24'


class TestInstallSummaries:
    """The installation summary and the machine-wide writes of an isolated run name what Step 5 installs."""

    MACOS = NodeUpgradePlan(
        'install', reason='not found', homebrew_formula='node@24', installs=("Homebrew's node@24 (24.22.1)", PACKAGE),
    )

    def _writes(self, tmp_path: Path, node_upgrade: NodeUpgradePlan) -> list[str]:
        return setup_environment.collect_machine_wide_writes(
            profile_dir=tmp_path / 'p', command_names=[], skip_install=True, install_version=None,
            keep_installed=False, pinned_version=None, ide_clis=[], os_level_env={}, mcp_servers=[],
            files_to_download=[], has_dependency_commands=False, node_upgrade=node_upgrade,
        )

    def test_installation_summary_row(self) -> None:
        plan = setup_environment.InstallationPlan(
            config_name='Node', config_source='node.yaml', config_source_type='local', config_version=None,
            install_nodejs=True, node_upgrade=self.MACOS,
        )
        output = io.StringIO()
        with patch.object(setup_environment.Colors, 'BOLD', ''), patch.object(setup_environment.Colors, 'NC', ''):
            setup_environment.display_installation_summary(plan, output=output)

        assert f"  * Node.js: not found; Step 5 installs Homebrew's node@24 (24.22.1), else {PACKAGE}\n" in output.getvalue()

    def test_machine_wide_row(self, tmp_path: Path) -> None:
        assert self._writes(tmp_path, self.MACOS) == [
            f"Node.js: install Homebrew's node@24 (24.22.1), else {PACKAGE} (used by every profile)",
        ]

    def test_no_machine_wide_row_without_an_installer(self, tmp_path: Path) -> None:
        assert self._writes(tmp_path, NodeUpgradePlan('install', reason='not found')) == []


class _Commands:
    """Record the Node.js commands Step 5 runs and answer each with exit code 0, or 1 for the named programs."""

    def __init__(self, failing: tuple[str, ...] = ()) -> None:
        self.calls: list[list[str]] = []
        self.failing = failing

    def __call__(self, command: list[str], *, sudo: bool = False) -> subprocess.CompletedProcess[str]:
        assert not sudo
        self.calls.append(command)
        failed = any(' '.join(command).startswith(prefix) for prefix in self.failing)
        return subprocess.CompletedProcess(command, 1 if failed else 0, '', '')


def _ensure_on_macos(
    commands: _Commands, homebrew_formula: str | None, *, versions: list[str | None], brew: bool = True,
) -> tuple[bool, MagicMock]:
    """Run _ensure_nodejs() on macOS with recorded commands; the node versions answer each check in turn."""
    direct = MagicMock(return_value=True)
    with (
        patch.object(setup_environment.platform, 'system', return_value='Darwin'),
        patch.object(setup_environment, '_get_node_version', side_effect=versions),
        patch.object(setup_environment, '_run_nodejs_command', commands),
        patch.object(setup_environment, '_check_homebrew_available', return_value=brew),
        patch.object(setup_environment, '_install_nodejs_direct', direct),
        patch.object(setup_environment.time, 'sleep'),
    ):
        return setup_environment._ensure_nodejs(homebrew_formula=homebrew_formula), direct


class TestInstallOnMacOS:
    """Step 5 installs and links the planned Homebrew formula, else the official installer package."""

    def test_the_planned_formula_is_installed_and_linked(self) -> None:
        commands = _Commands()
        ok, direct = _ensure_on_macos(commands, 'node@24', versions=[None, 'v24.22.1'])

        assert ok
        assert commands.calls == [
            ['brew', 'update'],
            ['brew', 'install', 'node@24'],
            ['brew', 'link', '--force', '--overwrite', 'node@24'],
        ]
        direct.assert_not_called()

    def test_homebrew_is_installed_first_when_brew_is_missing(self) -> None:
        commands = _Commands()
        ok, _ = _ensure_on_macos(commands, 'node@24', versions=[None, 'v24.22.1'], brew=False)

        assert ok
        assert commands.calls[0][:2] == ['/bin/bash', '-c']
        assert commands.calls[1:] == [
            ['brew', 'update'],
            ['brew', 'install', 'node@24'],
            ['brew', 'link', '--force', '--overwrite', 'node@24'],
        ]

    def test_without_a_planned_formula_the_official_package_is_installed(self, capsys: pytest.CaptureFixture[str]) -> None:
        commands = _Commands()
        ok, direct = _ensure_on_macos(commands, None, versions=[None, 'v26.12.1'])

        assert ok
        assert commands.calls == []
        direct.assert_called_once_with()
        assert 'Skipping Homebrew: no Homebrew formula of a supported Node.js LTS line is known' in capsys.readouterr().out

    def test_a_failed_homebrew_install_falls_back_to_the_official_package(self) -> None:
        commands = _Commands(failing=('brew install',))
        ok, direct = _ensure_on_macos(commands, 'node@24', versions=[None, 'v26.12.1'])

        assert ok
        assert ['brew', 'link', '--force', '--overwrite', 'node@24'] not in commands.calls
        direct.assert_called_once_with()


class TestStepFiveInstall:
    """install_nodejs_if_requested() hands the planned formula to the installer."""

    def test_the_plan_formula_reaches_ensure_nodejs(self) -> None:
        plan = NodeUpgradePlan('install', reason='not found', homebrew_formula='node@24')
        with (
            patch.object(setup_environment, '_ensure_nodejs', return_value=True) as ensure,
            patch.object(setup_environment, '_get_node_version', return_value='v24.22.1'),
            patch.object(setup_environment.platform, 'system', return_value='Darwin'),
        ):
            result = setup_environment.install_nodejs_if_requested({'install-nodejs': True}, plan)

        ensure.assert_called_once_with(homebrew_formula='node@24')
        assert result == setup_environment.NodeStepResult(True, 'Node.js: 24.22.1')
