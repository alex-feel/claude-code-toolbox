"""Unit tests for the work a content dependent leaves to its source's run.

A profile that links content from a source shares the one machine with it:
the Claude Code binary, the IDE extension, Node.js and the tools the
dependency commands install exist once, and the source's run installs them.
The dependent's run therefore leaves that work out -- the Step 1 install
(the presence check stays), the Step 2 IDE extension, the Step 5 Node.js
installation and, when the profile links every content entry, every
dependency command whose text, after this run's re-rooting, equals a command
the source's run executes -- unless ``--run-all-commands`` asks for the full
run. A profile that links only some content entries runs every command,
because a command may write into a content directory it holds for real.
These tests cover the helpers that compute and render that work.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from scripts import setup_environment
from scripts.setup_environment import LinkSource
from scripts.setup_environment import SourceWork


def _write_snapshot(directory: Path, dependencies: dict[str, Any]) -> None:
    """Write a resolved-config.yaml with the given dependencies into a profile directory."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'resolved-config.yaml').write_text(
        yaml.safe_dump({'name': 'Team', 'dependencies': dependencies}, sort_keys=False), encoding='utf-8',
    )


class TestPlatformCommands:
    """dependency_commands_for_this_platform() lists what install_dependencies() runs, in its order."""

    def test_platform_list_runs_before_common_and_other_platforms_are_left_out(self) -> None:
        dependencies = {
            'linux': ['apt install node'],
            'windows': ['winget install node'],
            'macos': ['brew install node'],
            'common': ['npm install -g x', 'uv tool install ruff'],
        }
        with patch.object(setup_environment.platform, 'system', return_value='Linux'):
            assert setup_environment.dependency_commands_for_this_platform(dependencies) == [
                'apt install node', 'npm install -g x', 'uv tool install ruff',
            ]
        with patch.object(setup_environment.platform, 'system', return_value='Windows'):
            assert setup_environment.dependency_commands_for_this_platform(dependencies) == [
                'winget install node', 'npm install -g x', 'uv tool install ruff',
            ]

    def test_malformed_sections_yield_nothing(self) -> None:
        with patch.object(setup_environment.platform, 'system', return_value='Linux'):
            assert setup_environment.dependency_commands_for_this_platform(None) == []
            assert setup_environment.dependency_commands_for_this_platform('npm install -g x') == []
            assert setup_environment.dependency_commands_for_this_platform({'common': 'npm install -g x'}) == []
            assert setup_environment.dependency_commands_for_this_platform({'linux': None, 'common': []}) == []


class TestSourceRunCommands:
    """source_run_commands() spells the source's commands the way the source's run executes them."""

    def test_isolated_source_commands_are_rerooted_into_the_source(self, tmp_path: Path) -> None:
        home = tmp_path / 'home'
        source_dir = home / '.claude' / 'team-1'
        _write_snapshot(source_dir, {
            'common': ['npm install -g x', 'rm -rf ~/.claude/statsig'],
            'linux': ['mkdir -p "$HOME/.claude/dep"'],
            'windows': ['New-Item "$env:USERPROFILE\\.claude\\dep"'],
        })
        source = LinkSource('team-1', source_dir, {'name': 'team-1'})

        with patch.object(setup_environment.platform, 'system', return_value='Linux'):
            commands = setup_environment.source_run_commands(source, home, ['team-2', 'team-1'])

        assert commands == frozenset({
            'npm install -g x', 'rm -rf ~/.claude/team-1/statsig', 'mkdir -p "$HOME/.claude/team-1/dep"',
        })

    def test_base_source_commands_stay_as_authored(self, tmp_path: Path) -> None:
        home = tmp_path / 'home'
        _write_snapshot(home / '.claude', {'common': ['npm install -g x', 'rm -rf ~/.claude/statsig']})
        source = LinkSource('base', home / '.claude', {'name': None})

        with patch.object(setup_environment.platform, 'system', return_value='Linux'):
            commands = setup_environment.source_run_commands(source, home, ['team-2'])

        assert commands == frozenset({'npm install -g x', 'rm -rf ~/.claude/statsig'})

    def test_missing_snapshot_means_no_commands(self, tmp_path: Path) -> None:
        source = LinkSource('team-1', tmp_path / 'home' / '.claude' / 'team-1', {'name': 'team-1'})
        assert setup_environment.source_run_commands(source, tmp_path / 'home', ['team-1']) == frozenset()

    def test_snapshot_of_a_pending_refresh_replaces_the_stale_file(self, tmp_path: Path) -> None:
        """A run that refreshes the source first reads the commands of the snapshot that refresh records."""
        home = tmp_path / 'home'
        source_dir = home / '.claude' / 'team-1'
        _write_snapshot(source_dir, {'common': ['npm install -g old']})
        source = LinkSource('team-1', source_dir, {'name': 'team-1'})
        refreshed: dict[str, Any] = {
            'name': 'Team', 'dependencies': {'common': ['npm install -g new', 'rm -rf ~/.claude/statsig']},
        }

        with patch.object(setup_environment.platform, 'system', return_value='Linux'):
            commands = setup_environment.source_run_commands(source, home, ['team-1'], snapshot=refreshed)

        assert commands == frozenset({'npm install -g new', 'rm -rf ~/.claude/team-1/statsig'})
        assert refreshed['dependencies']['common'][1] == 'rm -rf ~/.claude/statsig', 'the snapshot stays as authored'


class TestCoversEveryContentEntry:
    """covers_every_content_entry() tells a profile holding no content directory from one holding some."""

    def test_all_and_the_full_content_list_cover_every_entry(self) -> None:
        assert setup_environment.covers_every_content_entry(setup_environment.LINKABLE_PROFILE_DIRS)
        assert setup_environment.covers_every_content_entry(setup_environment.CONTENT_PROFILE_DIRS)
        assert setup_environment.covers_every_content_entry(
            [entry.upper() for entry in setup_environment.CONTENT_PROFILE_DIRS],
        ), 'entries are matched without regard to case, as the manifest and the flag spell them'

    def test_a_partial_list_and_a_projects_only_link_do_not(self) -> None:
        assert not setup_environment.covers_every_content_entry(['agents'])
        assert not setup_environment.covers_every_content_entry(['projects'])
        assert not setup_environment.covers_every_content_entry(
            [entry for entry in setup_environment.CONTENT_PROFILE_DIRS if entry != 'skills'],
        ), 'a profile holding skills/ for real needs the commands that write into it'
        assert not setup_environment.covers_every_content_entry([])

    def test_link_spec_property_follows_the_helper(self) -> None:
        full = setup_environment.LinkSpec(list(setup_environment.LINKABLE_PROFILE_DIRS), 'team-1', 'cli', 'cli')
        content_only = setup_environment.LinkSpec(list(setup_environment.CONTENT_PROFILE_DIRS), 'team-1', 'cli', 'cli')
        partial = setup_environment.LinkSpec(['agents', 'projects'], 'team-1', 'cli', 'cli')
        assert full.links_every_content_entry
        assert content_only.links_every_content_entry
        assert partial.links_content
        assert not partial.links_every_content_entry
        assert not setup_environment.NO_LINKS.links_every_content_entry


class TestLeaveCommandsToSource:
    """leave_commands_to_source() drops the commands the source runs and reports them in run order."""

    def test_identical_commands_are_dropped_and_rewritten_ones_kept(self) -> None:
        dependencies: dict[str, Any] = {
            'linux': ['apt install node', 'mkdir -p "$HOME/.claude/team-2/dep"'],
            'common': ['npm install -g x', 'rm -rf ~/.claude/team-2/statsig', 'uv tool install ruff'],
            'windows': ['npm install -g x'],
        }
        source_commands = frozenset({
            'apt install node', 'mkdir -p "$HOME/.claude/team-1/dep"', 'npm install -g x',
            'rm -rf ~/.claude/team-1/statsig', 'uv tool install ruff',
        })

        with patch.object(setup_environment.platform, 'system', return_value='Linux'):
            skipped = setup_environment.leave_commands_to_source(dependencies, source_commands)

        assert skipped == ['apt install node', 'npm install -g x', 'uv tool install ruff']
        assert dependencies == {
            'linux': ['mkdir -p "$HOME/.claude/team-2/dep"'],
            'common': ['rm -rf ~/.claude/team-2/statsig'],
            'windows': ['npm install -g x'],
        }, 'the lists of this platform lose the shared commands in place; another platform list is left alone'

    def test_nothing_shared_leaves_the_lists_alone(self) -> None:
        dependencies: dict[str, Any] = {'common': ['npm install -g x']}
        with patch.object(setup_environment.platform, 'system', return_value='Linux'):
            assert setup_environment.leave_commands_to_source(dependencies, frozenset()) == []
            assert setup_environment.leave_commands_to_source(dependencies, frozenset({'other'})) == []
            assert setup_environment.leave_commands_to_source(None, frozenset({'npm install -g x'})) == []
        assert dependencies == {'common': ['npm install -g x']}


class TestSourceWorkRows:
    """source_work_rows() names every item the dependent leaves to its source."""

    def test_rows_follow_the_step_order(self) -> None:
        work = SourceWork('team-1', ('npm install -g x', 'uv tool install ruff'), pinned_version='1.2.3', install_nodejs=True)
        assert setup_environment.source_work_rows(work) == [
            'Claude Code install or upgrade',
            f'IDE extension {setup_environment.IDE_EXTENSION_ID} v1.2.3',
            'Node.js installation',
            'npm install -g x',
            'uv tool install ruff',
        ]

    def test_unpinned_run_without_nodejs_lists_the_binary_and_the_commands(self) -> None:
        work = SourceWork('base', ('npm install -g x',), pinned_version=None, install_nodejs=False)
        assert setup_environment.source_work_rows(work) == ['Claude Code install or upgrade', 'npm install -g x']


class TestSummaryRendering:
    """The installation summary names the source and every item left to it."""

    def _render(self, plan: setup_environment.InstallationPlan) -> str:
        output = io.StringIO()
        with (
            patch.object(setup_environment.Colors, 'CYAN', ''), patch.object(setup_environment.Colors, 'NC', ''),
            patch.object(setup_environment.Colors, 'BOLD', ''), patch.object(setup_environment.Colors, 'YELLOW', ''),
            patch.object(setup_environment.Colors, 'GREEN', ''),
        ):
            setup_environment.display_installation_summary(plan, output=output)
        return output.getvalue()

    def test_dependent_rows_name_the_source_and_the_flag_that_forces_the_full_run(self) -> None:
        plan = setup_environment.InstallationPlan(
            config_name='Team', config_source='team.yaml', config_source_type='local', config_version=None,
            command_names=['team-2'], install_nodejs=True,
            dependency_commands={'common': ['mkdir -p ~/.claude/team-2/dep']},
            source_work=SourceWork('team-1', ('npm install -g x',), pinned_version='1.2.3', install_nodejs=True),
        )

        text = self._render(plan)

        assert '  * Claude Code: skip (left to source profile "team-1")' in text
        assert '  * Node.js: left to source profile "team-1"' in text
        assert (
            'Left to source profile "team-1" (its run does this work for the machine; '
            '--run-all-commands repeats it in this profile):'
        ) in text
        assert '  [from source team-1] Claude Code install or upgrade' in text
        assert f'  [from source team-1] IDE extension {setup_environment.IDE_EXTENSION_ID} v1.2.3' in text
        assert '  [from source team-1] Node.js installation' in text
        assert '  [from source team-1] npm install -g x' in text
        assert '    $ mkdir -p ~/.claude/team-2/dep' in text, 'the rewritten command still runs and is listed as such'
        assert '    $ npm install -g x' not in text

    def test_skip_install_wins_over_the_source_in_the_claude_code_line(self) -> None:
        plan = setup_environment.InstallationPlan(
            config_name='Team', config_source='team.yaml', config_source_type='local', config_version=None,
            command_names=['team-2'], skip_install=True,
            source_work=SourceWork('team-1', (), pinned_version=None, install_nodejs=False),
        )

        text = self._render(plan)

        assert '  * Claude Code: skip (--skip-install)' in text
        assert '  [from source team-1] Claude Code install or upgrade' in text

    def test_full_run_has_no_source_block(self) -> None:
        plan = setup_environment.InstallationPlan(
            config_name='Team', config_source='team.yaml', config_source_type='local', config_version=None,
            command_names=['team-2'], install_nodejs=True, dependency_commands={'common': ['npm install -g x']},
        )

        text = self._render(plan)

        assert 'from source' not in text
        assert 'Left to source profile' not in text
        assert '  * Node.js: install if needed' in text
        assert '  * Claude Code: install (version: latest)' in text

    def test_dependents_rows_carry_the_flag_the_children_receive(self) -> None:
        plan = setup_environment.InstallationPlan(
            config_name='Team', config_source='team.yaml', config_source_type='local', config_version=None,
            command_names=['team-1'], dependents=['team-2'],
        )
        assert '  * team-2 (--profile team-2 --yes --skip-install --no-admin)\n' in self._render(plan)
        plan.run_all_commands = True
        assert '  * team-2 (--profile team-2 --yes --skip-install --no-admin --run-all-commands)\n' in self._render(plan)


class TestDependentRunSnapshot:
    """dependent_run_snapshot() spells what a dependent's run executes, for the elevation hint."""

    @staticmethod
    def _profile(home: Path, link_dirs: list[str] | None) -> setup_environment.InstalledProfile:
        dependent_dir = home / '.claude' / 'team-2'
        _write_snapshot(dependent_dir, {'common': ['npm install -g x', 'rm -rf ~/.claude/statsig']})
        manifest: dict[str, Any] | None = None
        if link_dirs is not None:
            manifest = {'name': 'team-2', 'link': {'dirs': link_dirs, 'source': 'team-1'}}
        return setup_environment.InstalledProfile('team-2', dependent_dir, dependent_dir / 'manifest.json', manifest)

    def test_snapshot_is_rerooted_and_loses_the_commands_the_source_runs(self, tmp_path: Path) -> None:
        home = tmp_path / 'home'
        profile = self._profile(home, list(setup_environment.LINKABLE_PROFILE_DIRS))

        with (
            patch.object(setup_environment, 'get_real_user_home', return_value=home),
            patch.object(setup_environment.platform, 'system', return_value='Linux'),
        ):
            trimmed = setup_environment.dependent_run_snapshot(profile, source_commands=frozenset({'npm install -g x'}))
            full = setup_environment.dependent_run_snapshot(profile, source_commands=None)

        assert trimmed['dependencies'] == {'common': ['rm -rf ~/.claude/team-2/statsig']}
        assert full['dependencies'] == {'common': ['npm install -g x', 'rm -rf ~/.claude/team-2/statsig']}

    def test_partial_content_link_keeps_every_command(self, tmp_path: Path) -> None:
        """A dependent holding some content directory for real runs every command, so its remedy counts them."""
        home = tmp_path / 'home'
        profile = self._profile(home, ['agents'])

        with (
            patch.object(setup_environment, 'get_real_user_home', return_value=home),
            patch.object(setup_environment.platform, 'system', return_value='Linux'),
        ):
            snapshot = setup_environment.dependent_run_snapshot(profile, source_commands=frozenset({'npm install -g x'}))

        assert snapshot['dependencies'] == {'common': ['npm install -g x', 'rm -rf ~/.claude/team-2/statsig']}

    def test_unreadable_manifest_keeps_every_command(self, tmp_path: Path) -> None:
        """Without the link record the run cannot know what the dependent leaves out, so nothing is dropped."""
        home = tmp_path / 'home'
        profile = self._profile(home, None)

        with (
            patch.object(setup_environment, 'get_real_user_home', return_value=home),
            patch.object(setup_environment.platform, 'system', return_value='Linux'),
        ):
            snapshot = setup_environment.dependent_run_snapshot(profile, source_commands=frozenset({'npm install -g x'}))

        assert snapshot['dependencies'] == {'common': ['npm install -g x', 'rm -rf ~/.claude/team-2/statsig']}

    def test_missing_snapshot_is_empty(self, tmp_path: Path) -> None:
        profile = setup_environment.InstalledProfile('team-2', tmp_path / 'team-2', tmp_path / 'team-2' / 'm.json', None)
        with patch.object(setup_environment, 'get_real_user_home', return_value=tmp_path):
            assert setup_environment.dependent_run_snapshot(profile, source_commands=frozenset()) == {}


class TestElevationReasonsOverride:
    """admin_elevation_reasons() takes the install decision of a run that leaves the binary to its source."""

    def test_skip_install_keyword_overrides_the_argument(self) -> None:
        args = setup_environment.argparse.Namespace(skip_install=False)
        with patch.object(setup_environment.platform, 'system', return_value='Windows'):
            assert setup_environment.admin_elevation_reasons({}, args) == [
                'Installing Claude Code (includes Node.js and Git)',
            ]
            assert setup_environment.admin_elevation_reasons({}, args, skip_install=True) == []
            assert setup_environment.admin_elevation_reasons(
                {}, setup_environment.argparse.Namespace(skip_install=True), skip_install=False,
            ) == ['Installing Claude Code (includes Node.js and Git)']

    def test_request_passes_the_override_on(self) -> None:
        args = setup_environment.argparse.Namespace(skip_install=False, no_admin=False, dry_run=False)
        with patch.object(setup_environment, 'admin_elevation_reasons', return_value=[]) as reasons:
            setup_environment.request_admin_elevation_if_needed({'x': 1}, args, skip_install=True)
        reasons.assert_called_once_with({'x': 1}, args, skip_install=True, scheduled_update=None)

    def test_source_refresh_reasons_come_first_and_count_for_a_run_with_none_of_its_own(
        self, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A dependent that leaves its work to the source still elevates for the refresh of that source."""
        args = setup_environment.argparse.Namespace(skip_install=False, no_admin=False, dry_run=True)
        refresh_reasons = ['Installing Claude Code (includes Node.js and Git)', 'Global npm package: npm install -g x']
        own = {'dependencies': {'windows': ['npm install -g x', 'npm install -g own']}}
        with (
            patch.object(setup_environment.platform, 'system', return_value='Windows'),
            patch.object(setup_environment, 'is_admin', return_value=False),
        ):
            setup_environment.request_admin_elevation_if_needed(
                own, args, skip_install=True, source_refresh_reasons=refresh_reasons,
            )
            listed = capsys.readouterr().out
            setup_environment.request_admin_elevation_if_needed({}, args, skip_install=True)
            nothing = capsys.readouterr().out
        assert [line.split('  - ', 1)[1] for line in listed.splitlines() if '  - ' in line] == [
            'Installing Claude Code (includes Node.js and Git)',
            'Global npm package: npm install -g x',
            'Global npm package: npm install -g own',
        ], 'the refresh reasons first, then the reasons of this run without repeating one'
        assert nothing == '', 'without a refresh, a run with no work of its own requests nothing'


def test_run_all_commands_flag_and_twin() -> None:
    """The flag is spelled once and its variable is a switch twin, so only the exact value 1 turns it on."""
    assert setup_environment.RUN_ALL_COMMANDS_FLAG == '--run-all-commands'
    twin = next(twin for twin in setup_environment.ENV_TWINS if twin.dest == 'run_all_commands')
    assert twin.variable == 'CLAUDE_CODE_TOOLBOX_RUN_ALL_COMMANDS'
    assert twin.kind == 'switch'
