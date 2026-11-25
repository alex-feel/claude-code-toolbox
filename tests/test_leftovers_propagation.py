"""Tests for how --remove-leftovers reaches the runs a run starts, and for the scheduled run that only lists.

A run that starts other runs -- --profile all, a source's Step 24 and a
dependent's refresh of its stale source -- hands --remove-leftovers to each
child in argv, because a child's environment loses every argument twin, and
the installation summary's previews name it. The --profile all parent asks
once, and its closing report reads what each child's manifest records about
the profile's leftovers. A scheduled run lists leftovers and removes none,
even when the variable is set in the environment the scheduler hands it.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
from collections.abc import Callable
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts import setup_environment
from scripts.setup_environment import InstalledProfile
from scripts.setup_environment import LeftoverEntry
from scripts.setup_environment import LeftoverItem
from scripts.setup_environment import LeftoverOutcome
from scripts.setup_environment import LeftoverRemoval
from scripts.setup_environment import LeftoverReport

_REAL_INSTALLED_PROFILES = setup_environment.installed_profiles
FLAG = '--remove-leftovers'


def _args(**values: Any) -> argparse.Namespace:
    """Build resolved arguments the way main() does, every argument twin cleared from the environment."""
    namespace = argparse.Namespace(
        config=None, yes=False, dry_run=False, skip_install=False, no_admin=False, env_vars=None, select=None,
        with_=None, without=None, list_components=False, command_names=None, profile=None, switch_config=False,
        child_run=False, link_dirs=None, link_from=None, run_all_commands=False, remove_leftovers=False,
        scheduled_run=False,
    )
    env = values.pop('env', {})
    for key, value in values.items():
        setattr(namespace, key, value)
    cleared = {twin.variable: '' for twin in setup_environment.ENV_TWINS}
    with patch.dict(os.environ, {**cleared, **env}, clear=False):
        return setup_environment.resolve_args(namespace)


def _write_manifest(directory: Path, name: str | None, leftovers: dict[str, Any] | None = None) -> Path:
    """Write a manifest the registry lists, with a leftovers field when given, and return its path."""
    directory.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {'name': name, 'command_names': [name] if name else [], 'files_written': []}
    if leftovers is not None:
        manifest['leftovers'] = leftovers
    path = directory / 'manifest.json'
    path.write_text(json.dumps(manifest), encoding='utf-8')
    return path


def _record(run_at: str, **fields: Any) -> dict[str, Any]:
    """A leftovers field as leftovers_manifest_record() writes it."""
    return {
        'run_at': run_at, 'items': [], 'removed': [], 'dropped': [], 'skipped': None, 'failed': [], 'kept': [],
        **fields,
    }


def _file(path: str) -> dict[str, str]:
    return {'kind': 'file', 'path': path, 'sha256': 'a' * 64}


def _profile(home: Path, name: str) -> InstalledProfile:
    directory = home / '.claude' if name == 'base' else home / '.claude' / name
    return InstalledProfile(name, directory, directory / 'manifest.json', None)


def _recorder(calls: list[list[str]]) -> Callable[..., subprocess.CompletedProcess[bytes]]:
    """A subprocess.run stand-in that records each child's argv and reports success."""
    def _run(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    return _run


class TestRefreshDependents:
    """A source's Step 24 starts each dependent with the flag when the source's run was given it."""

    @pytest.mark.parametrize(
        ('remove_leftovers', 'run_all_commands', 'expected_flags'),
        [
            (False, False, ['--yes', '--child-run', '--skip-install', '--no-admin']),
            (True, False, ['--yes', '--child-run', '--skip-install', '--no-admin', FLAG]),
            (True, True, ['--yes', '--child-run', '--skip-install', '--no-admin', '--run-all-commands', FLAG]),
        ],
    )
    def test_children_carry_the_flag_in_argv(
        self, remove_leftovers: bool, run_all_commands: bool, expected_flags: list[str], tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        calls: list[list[str]] = []
        with patch.object(setup_environment.subprocess, 'run', side_effect=_recorder(calls)):
            results = setup_environment.refresh_dependents(
                [_profile(tmp_path, 'team-2')], run_all_commands=run_all_commands, remove_leftovers=remove_leftovers,
            )
        capsys.readouterr()
        assert [result.code for result in results] == [0]
        assert calls[0][calls[0].index('--profile'):] == ['--profile', 'team-2', *expected_flags]

    @pytest.mark.parametrize('for_dependent', [None, 'team-3'], ids=['source-run', 'source-refresh'])
    def test_step_24_hands_the_flag_to_every_dependent_it_refreshes(
        self, for_dependent: str | None, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The source's own run and the refresh a dependent starts both forward it, the --for-dependent branch too."""
        dependents = [_profile(tmp_path, 'team-2'), _profile(tmp_path, 'team-3')]
        calls: list[list[str]] = []
        with patch.object(setup_environment.subprocess, 'run', side_effect=_recorder(calls)):
            setup_environment.run_dependent_refresh_step(
                dependents, source_name='team-1', child_run=False, for_dependent=for_dependent, remove_leftovers=True,
            )
        capsys.readouterr()
        expected = ['team-2'] if for_dependent else ['team-2', 'team-3']
        assert [argv[argv.index('--profile') + 1] for argv in calls] == expected
        for argv in calls:
            assert argv[-1] == FLAG, argv


class TestSourceRefresh:
    """The refresh of a stale source hands the dependent run's flag to the source's run."""

    @staticmethod
    def _refresh(tmp_path: Path, *, remove_leftovers: bool) -> setup_environment.SourceRefresh:
        return setup_environment.SourceRefresh(
            'team-1', tmp_path / '.claude' / 'team-1', 'differs', 'abc', ['team-3'], True, False, remove_leftovers, {},
        )

    def test_child_arguments_and_the_command_row_carry_the_flag(self, tmp_path: Path) -> None:
        refresh = self._refresh(tmp_path, remove_leftovers=True)
        assert refresh.child_arguments('team-2') == [
            '--profile', 'team-1', '--yes', '--child-run', '--for-dependent', 'team-2', '--skip-install', '--no-admin',
            FLAG,
        ]
        assert refresh.rows()[1] == f'command: --profile team-1 --yes --skip-install --no-admin {FLAG}'

    def test_without_the_flag_neither_names_it(self, tmp_path: Path) -> None:
        refresh = self._refresh(tmp_path, remove_leftovers=False)
        assert FLAG not in refresh.child_arguments('team-2')
        assert FLAG not in refresh.rows()[1]


class TestSummaryPreviews:
    """The Dependents block names the flag its children receive."""

    @staticmethod
    def _render(plan: setup_environment.InstallationPlan) -> str:
        output = io.StringIO()
        with (
            patch.object(setup_environment.Colors, 'CYAN', ''), patch.object(setup_environment.Colors, 'NC', ''),
            patch.object(setup_environment.Colors, 'BOLD', ''), patch.object(setup_environment.Colors, 'YELLOW', ''),
            patch.object(setup_environment.Colors, 'GREEN', ''),
        ):
            setup_environment.display_installation_summary(plan, output=output)
        return output.getvalue()

    def test_dependents_rows_carry_the_flag(self) -> None:
        plan = setup_environment.InstallationPlan(
            config_name='Team', config_source='team.yaml', config_source_type='local', config_version=None,
            command_names=['team-1'], dependents=['team-2'], remove_leftovers=True,
        )
        assert f'  * team-2 (--profile team-2 --yes --skip-install --no-admin {FLAG})\n' in self._render(plan)
        plan.run_all_commands = True
        assert (
            f'  * team-2 (--profile team-2 --yes --skip-install --no-admin --run-all-commands {FLAG})\n'
        ) in self._render(plan)
        plan.remove_leftovers = False
        plan.run_all_commands = False
        assert '  * team-2 (--profile team-2 --yes --skip-install --no-admin)\n' in self._render(plan)


class TestScheduledRun:
    """A scheduled run lists the leftovers and removes none, whatever the environment it runs in sets."""

    def test_switch_off_names_the_manual_command(self, capsys: pytest.CaptureFixture[str]) -> None:
        args = _args(profile='team-1', scheduled_run=True, remove_leftovers=True)
        setup_environment.switch_off_scheduled_removal(args)
        assert args.remove_leftovers is False
        assert (
            'Leftovers are only listed in a scheduled run; remove them with --profile team-1 --remove-leftovers.'
        ) in capsys.readouterr().out

    def test_switch_off_is_silent_without_the_flag_and_outside_a_scheduled_run(
        self, capsys: pytest.CaptureFixture[str],
    ) -> None:
        unflagged = _args(profile='team-1', scheduled_run=True)
        setup_environment.switch_off_scheduled_removal(unflagged)
        manual = _args(profile='team-1', remove_leftovers=True)
        setup_environment.switch_off_scheduled_removal(manual)
        assert manual.remove_leftovers is True, 'a manual run keeps the flag'
        assert 'scheduled run' not in capsys.readouterr().out

    def test_main_switches_the_variable_off_inside_the_scheduled_setup(
        self, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The switch happens once the run writes to its log: inside the setup the scheduled update runs."""
        seen: list[bool] = []

        def _scheduled(args: argparse.Namespace, run_setup: Callable[[], None], *, custom_command: str | None) -> int:
            assert custom_command is None
            assert args.remove_leftovers is True, 'not switched off before the log takes the output'
            run_setup()
            return 0

        def _setup(args: argparse.Namespace, _elevated: bool) -> None:
            seen.append(bool(args.remove_leftovers))

        argv = ['setup_environment.py', '--profile', 'team-1', '--yes', '--scheduled-run']
        with (
            patch.dict(os.environ, {'CLAUDE_CODE_TOOLBOX_REMOVE_LEFTOVERS': '1'}),
            patch.object(setup_environment, 'scheduled_custom_command', return_value=None),
            patch.object(setup_environment, 'run_scheduled_update', side_effect=_scheduled),
            patch.object(setup_environment, '_run_setup', side_effect=_setup),
            patch('sys.argv', argv),
            pytest.raises(SystemExit) as exc,
        ):
            setup_environment.main()
        assert exc.value.code == 0
        assert seen == [False]
        assert 'Leftovers are only listed in a scheduled run' in capsys.readouterr().out

    @staticmethod
    def _report(tmp_path: Path) -> LeftoverReport:
        return LeftoverReport(
            profile_name='team-1',
            profile_dir=tmp_path,
            entries=(LeftoverEntry(LeftoverItem('file', 'rules/old.md', 'a' * 64), 'removable', ''),),
            untracked_note=False,
        )

    def test_summary_footer_names_the_manual_command(self, tmp_path: Path) -> None:
        assert self._report(tmp_path).lines(scheduled=True) == [
            f'[leftover] file: {tmp_path / "rules" / "old.md"}',
            'They stay in place.',
            'A scheduled run only lists leftovers; remove them with --profile team-1 --remove-leftovers.',
        ]
        assert setup_environment.LEFTOVERS_FLAG_FOOTER in self._report(tmp_path).lines()

    def test_plan_marks_the_scheduled_run(self, tmp_path: Path) -> None:
        plan = setup_environment.InstallationPlan(
            config_name='Team', config_source='team.yaml', config_source_type='local', config_version=None,
            leftovers=self._report(tmp_path), scheduled_run=True,
        )
        output = io.StringIO()
        setup_environment.display_installation_summary(plan, output=output)
        assert 'A scheduled run only lists leftovers' in output.getvalue()
        assert setup_environment.LEFTOVERS_FLAG_FOOTER not in output.getvalue()


class TestKeptRecord:
    """The manifest's leftovers field says why each kept leftover stays, for the reports that read it."""

    def test_kept_entries_carry_their_reason(self, tmp_path: Path) -> None:
        destination = str(tmp_path / 'x.txt')
        held = LeftoverEntry(LeftoverItem('destination', destination, 'b' * 64), 'held', 'recorded by profile p2')
        unreadable = LeftoverEntry(LeftoverItem('file', 'rules/r.md', 'c' * 64), 'unreadable', 'Permission denied')
        plain = LeftoverEntry(LeftoverItem('file', 'rules/old.md', 'a' * 64), 'removable', '')
        report = LeftoverReport(
            profile_name='p', profile_dir=tmp_path, entries=(plain, unreadable, held), untracked_note=False,
        )
        record = setup_environment.leftovers_manifest_record(report, run_at='t')
        assert record['kept'] == [
            {'label': 'file: rules/r.md', 'reason': 'cannot check: Permission denied'},
            {'label': f'file outside ~/.claude: {destination}', 'reason': 'kept: recorded by profile p2'},
        ]

    def test_step_23_outcomes_decide_the_reasons(self, tmp_path: Path) -> None:
        wired = LeftoverEntry(LeftoverItem('file', 'hooks/a.py', 'a' * 64), 'referenced', 'still wired in s hooks.Stop')
        failed = LeftoverEntry(LeftoverItem('file', 'rules/old.md', 'b' * 64), 'removable', '')
        report = LeftoverReport(profile_name='p', profile_dir=tmp_path, entries=(wired, failed), untracked_note=False)
        removal = LeftoverRemoval(outcomes=(
            LeftoverOutcome(wired, 'kept', wired.detail),
            LeftoverOutcome(failed, 'failed', 'Access is denied'),
        ))
        record = setup_environment.leftovers_manifest_record(report, run_at='t', removal=removal)
        assert record['kept'] == [{'label': 'file: hooks/a.py', 'reason': 'kept: still wired in s hooks.Stop'}]
        assert record['failed'] == ['file: rules/old.md']

    def test_first_install_records_none(self) -> None:
        assert setup_environment.leftovers_manifest_record(None, run_at='t')['kept'] == []


class TestProfileLeftoversLines:
    """The --profile all report reads each child's manifest: what it removed, what is left and why."""

    @staticmethod
    def _lines(tmp_path: Path, record: dict[str, Any] | None, *, remove: bool, since: datetime) -> list[str]:
        profile = _profile(tmp_path, 'team-1')
        _write_manifest(profile.directory, 'team-1', record)
        return setup_environment.profile_leftovers_lines(
            profile, since=since, remove=remove, claude_dir=tmp_path / '.claude',
        )

    def test_flagged_run_lists_what_it_removed_and_what_is_left(self, tmp_path: Path) -> None:
        started = datetime.now(UTC)
        record = _record(
            (started + timedelta(seconds=5)).isoformat(),
            items=[_file('hooks/a.py'), _file('rules/locked.md')],
            removed=['file: rules/old.md', 'file: agents/extra.md'],
            failed=['file: rules/locked.md'],
            kept=[{'label': 'file: hooks/a.py', 'reason': 'kept: still wired in s hooks.Stop'}],
        )
        assert self._lines(tmp_path, record, remove=True, since=started) == [
            '- leftovers removed (2):',
            '    file: rules/old.md',
            '    file: agents/extra.md',
            '- leftovers left (2):',
            '    file: hooks/a.py (kept: still wired in s hooks.Stop)',
            '    file: rules/locked.md (could not be removed)',
        ]

    def test_skipped_removal_names_why_nothing_was_removed(self, tmp_path: Path) -> None:
        started = datetime.now(UTC)
        record = _record(
            (started + timedelta(seconds=5)).isoformat(), items=[_file('rules/old.md')],
            skipped='content downloads failed',
        )
        assert self._lines(tmp_path, record, remove=True, since=started) == [
            '- leftovers left (1; not removed: content downloads failed):',
            '    file: rules/old.md',
        ]

    def test_record_older_than_the_parent_counts_only_as_the_carried_list(self, tmp_path: Path) -> None:
        """A child that stopped before Step 20 left an earlier run's record: its removals are not this run's."""
        started = datetime.now(UTC)
        record = _record(
            '2026-01-01T00:00:00+00:00', items=[_file('rules/old.md')], removed=['file: agents/extra.md'],
            kept=[{'label': 'file: rules/old.md', 'reason': 'kept: recorded by profile p2'}],
        )
        assert self._lines(tmp_path, record, remove=True, since=started) == [
            '- leftovers left (1; recorded by an earlier run):',
            '    file: rules/old.md',
        ]

    def test_unflagged_run_names_the_command_that_removes_them(self, tmp_path: Path) -> None:
        started = datetime.now(UTC)
        record = _record(
            (started + timedelta(seconds=5)).isoformat(), items=[_file('rules/a.md'), _file('hooks/a.py')],
            kept=[{'label': 'file: hooks/a.py', 'reason': 'kept: still wired in s hooks.Stop'}],
        )
        assert self._lines(tmp_path, record, remove=False, since=started) == [
            '- 2 leftover(s); remove them with --profile team-1 --remove-leftovers',
        ]

    @pytest.mark.parametrize('run_at', ['not a time', '2030-01-01T00:00:00', None], ids=['unparsable', 'naive', 'null'])
    def test_record_time_that_cannot_be_compared_counts_as_an_earlier_run(
        self, tmp_path: Path, run_at: str | None,
    ) -> None:
        """A run_at the parent cannot place after its own start never vouches for removals."""
        started = datetime.now(UTC)
        record = _record('', items=[_file('rules/old.md')], removed=['file: agents/extra.md'])
        record['run_at'] = run_at
        assert self._lines(tmp_path, record, remove=True, since=started) == [
            '- leftovers left (1; recorded by an earlier run):',
            '    file: rules/old.md',
        ]

    def test_unflagged_run_names_the_command_for_a_stale_record_too(self, tmp_path: Path) -> None:
        """Without the flag the carried list is what counts, whichever run recorded it."""
        started = datetime.now(UTC)
        record = _record('2026-01-01T00:00:00+00:00', items=[_file('rules/a.md')])
        assert self._lines(tmp_path, record, remove=False, since=started) == [
            '- 1 leftover(s); remove them with --profile team-1 --remove-leftovers',
        ]

    @pytest.mark.parametrize(
        'record',
        [None, {'run_at': 'x'}, _record('2030-01-01T00:00:00+00:00')],
        ids=['no-field', 'other-shape', 'nothing-left'],
    )
    def test_nothing_to_report(self, tmp_path: Path, record: dict[str, Any] | None) -> None:
        started = datetime.now(UTC)
        assert self._lines(tmp_path, record, remove=True, since=started) == []
        assert self._lines(tmp_path, record, remove=False, since=started) == []

    def test_unreadable_or_missing_manifest_reports_nothing(self, tmp_path: Path) -> None:
        profile = _profile(tmp_path, 'team-1')
        started = datetime.now(UTC)
        assert setup_environment.profile_leftovers_lines(
            profile, since=started, remove=True, claude_dir=tmp_path / '.claude',
        ) == []
        profile.directory.mkdir(parents=True)
        profile.manifest_path.write_text('{not json', encoding='utf-8')
        assert setup_environment.profile_leftovers_lines(
            profile, since=started, remove=True, claude_dir=tmp_path / '.claude',
        ) == []


class TestProfileAll:
    """--profile all hands the flag to every child, asks once in its own words, and reports per profile."""

    @staticmethod
    def _install(home: Path) -> None:
        _write_manifest(home / '.claude', None)
        _write_manifest(home / '.claude' / 'team-1', 'team-1')

    def test_children_receive_the_flag_and_the_report_reads_their_manifests(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._install(tmp_path)
        fresh = (datetime.now(UTC) + timedelta(seconds=5)).isoformat()
        calls: list[list[str]] = []

        def _run(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
            calls.append(argv)
            if argv[argv.index('--profile') + 1] == 'team-1':
                _write_manifest(tmp_path / '.claude' / 'team-1', 'team-1', _record(
                    fresh, items=[_file('hooks/a.py')], removed=['file: rules/old.md'],
                    kept=[{'label': 'file: hooks/a.py', 'reason': 'kept: still wired in s hooks.Stop'}],
                ))
            return subprocess.CompletedProcess(argv, 0)

        with (
            patch.object(setup_environment, 'get_real_user_home', return_value=tmp_path),
            patch.object(setup_environment, 'installed_profiles', _REAL_INSTALLED_PROFILES),
            patch.object(setup_environment.subprocess, 'run', side_effect=_run),
            patch('sys.argv', ['/repo/scripts/setup_environment.py']),
        ):
            assert setup_environment.refresh_all_profiles(_args(profile='all', yes=True, remove_leftovers=True)) == 0

        assert [argv[argv.index('--profile') + 1] for argv in calls] == ['base', 'team-1']
        for argv in calls:
            assert argv[argv.index('--profile') + 2:] == ['--yes', '--child-run', '--no-admin', FLAG]
        out = capsys.readouterr().out
        report = out[out.index('Profiles refreshed:'):]
        assert report.split('\n')[1:7] == [
            '   * base: ok',
            '   * team-1: ok',
            '       - leftovers removed (1):',
            '           file: rules/old.md',
            '       - leftovers left (1):',
            '           file: hooks/a.py (kept: still wired in s hooks.Stop)',
        ]

    def test_without_the_flag_each_profile_with_leftovers_names_its_command(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._install(tmp_path)
        fresh = (datetime.now(UTC) + timedelta(seconds=5)).isoformat()

        def _run(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
            if argv[argv.index('--profile') + 1] == 'base':
                _write_manifest(tmp_path / '.claude', None, _record(fresh, items=[_file('rules/old.md')]))
            return subprocess.CompletedProcess(argv, 0)

        with (
            patch.object(setup_environment, 'get_real_user_home', return_value=tmp_path),
            patch.object(setup_environment, 'installed_profiles', _REAL_INSTALLED_PROFILES),
            patch.object(setup_environment.subprocess, 'run', side_effect=_run),
        ):
            assert setup_environment.refresh_all_profiles(_args(profile='all', yes=True)) == 0

        out = capsys.readouterr().out
        report = out[out.index('Profiles refreshed:'):]
        assert report.split('\n')[1:4] == [
            '   * base: ok',
            '       - 1 leftover(s); remove them with --profile base --remove-leftovers',
            '   * team-1: ok',
        ]

    def test_a_failed_flagged_child_is_retried_with_the_flag(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A removal that failed is retried only by a run given the flag, so the retry names it."""
        self._install(tmp_path)

        def _run(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
            return subprocess.CompletedProcess(argv, 1 if argv[argv.index('--profile') + 1] == 'team-1' else 0)

        with (
            patch.object(setup_environment, 'get_real_user_home', return_value=tmp_path),
            patch.object(setup_environment, 'installed_profiles', _REAL_INSTALLED_PROFILES),
            patch.object(setup_environment.subprocess, 'run', side_effect=_run),
        ):
            assert setup_environment.refresh_all_profiles(_args(profile='all', yes=True, remove_leftovers=True)) == 1
        assert '   * team-1: failed (exit code 1); retry with --profile team-1 --remove-leftovers' in capsys.readouterr().out

    def test_dry_run_reads_no_manifest(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """A dry run's children write nothing, so the parent reports their results only."""
        _write_manifest(tmp_path / '.claude', None, _record('2030-01-01T00:00:00+00:00', items=[_file('rules/x.md')]))
        calls: list[list[str]] = []
        with (
            patch.object(setup_environment, 'get_real_user_home', return_value=tmp_path),
            patch.object(setup_environment, 'installed_profiles', _REAL_INSTALLED_PROFILES),
            patch.object(setup_environment.subprocess, 'run', side_effect=_recorder(calls)),
            patch.object(setup_environment, 'profile_leftovers_lines') as lines,
        ):
            code = setup_environment.refresh_all_profiles(_args(profile='all', dry_run=True, remove_leftovers=True))

        assert code == 0
        lines.assert_not_called()
        assert calls[0][-3:] == ['--child-run', '--dry-run', FLAG]
        assert 'leftover' not in capsys.readouterr().out.split('Profiles refreshed:')[1]

    @staticmethod
    def _ask(tmp_path: Path, args: argparse.Namespace) -> list[str]:
        """Answer the parent's consent question with no and return the prompts it showed."""
        prompts: list[str] = []

        def _input(prompt: str) -> str:
            prompts.append(prompt)
            return 'n'

        with (
            patch.object(setup_environment, 'get_real_user_home', return_value=tmp_path),
            patch.object(setup_environment, 'installed_profiles', _REAL_INSTALLED_PROFILES),
            patch.object(setup_environment.subprocess, 'run') as run,
            patch.object(setup_environment, '_read_user_input', side_effect=_input),
            patch.object(setup_environment, '_flush_pending_terminal_input'),
            patch('sys.stdin.isatty', return_value=True),
        ):
            assert setup_environment.refresh_all_profiles(args) == 0
        run.assert_not_called()
        return prompts

    def test_consent_names_the_removal_and_the_preview(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """The children run with --yes, so the one question the parent asks says they remove leftovers."""
        self._install(tmp_path)
        prompts = self._ask(tmp_path, _args(profile='all', remove_leftovers=True))
        assert len(prompts) == 1
        assert 'Refresh these 2 profile(s) and remove their leftovers? [y/N]' in prompts[0]
        out = capsys.readouterr().out
        assert '--profile all --remove-leftovers --dry-run' in out
        assert out.index('--profile all --remove-leftovers --dry-run') < out.index('Setup cancelled by user.')

    def test_consent_without_the_flag_keeps_its_question(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        self._install(tmp_path)
        prompts = self._ask(tmp_path, _args(profile='all'))
        assert 'Refresh these 2 profile(s)? [y/N]' in prompts[0]
        assert 'leftovers' not in capsys.readouterr().out

    def test_variable_reaches_the_children_in_argv(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """The child's environment loses the twin, so a parent given the variable passes the flag."""
        self._install(tmp_path)
        calls: list[list[str]] = []
        envs: list[dict[str, str]] = []

        def _run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
            calls.append(argv)
            envs.append(kwargs['env'])
            return subprocess.CompletedProcess(argv, 0)

        args = _args(profile='all', yes=True, env={'CLAUDE_CODE_TOOLBOX_REMOVE_LEFTOVERS': '1'})
        with (
            patch.object(setup_environment, 'get_real_user_home', return_value=tmp_path),
            patch.object(setup_environment, 'installed_profiles', _REAL_INSTALLED_PROFILES),
            patch.object(setup_environment.subprocess, 'run', side_effect=_run),
            patch.dict(os.environ, {'CLAUDE_CODE_TOOLBOX_REMOVE_LEFTOVERS': '1'}),
        ):
            assert setup_environment.refresh_all_profiles(args) == 0
        capsys.readouterr()
        assert len(calls) == 2
        assert all(argv[-1] == FLAG for argv in calls)
        assert all('CLAUDE_CODE_TOOLBOX_REMOVE_LEFTOVERS' not in env for env in envs)
