"""E2E tests for --remove-leftovers in the runs a run starts, and in the scheduled run.

The tests install real local YAML files into an isolated home through main(),
edit the configurations in place (their identities stay the same, as an
update of a remote configuration does), and re-run the profiles the ways a
run starts others: --profile all, a source's Step 24 and a dependent's
refresh of its stale source each hand the flag to their children in argv,
and the --profile all report reads each child's manifest to say what it
removed and what it kept. A scheduled run lists the leftovers in its log and
removes none, even with the variable set.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts import setup_environment
from scripts.setup_environment import SchedulerPlatform
from tests.e2e.fake_scheduler import FakeScheduler
from tests.e2e.profile_support import home_state
from tests.e2e.profile_support import read_manifest
from tests.e2e.profile_support import run_main
from tests.e2e.profile_support import write_child_runner
from tests.e2e.profile_support import write_config

SKIP = ['--skip-install', '--no-admin']
FLAG = '--remove-leftovers'
HEADING = 'Leftovers of earlier runs (this configuration no longer installs them):'
_ANSI = re.compile(r'\x1b\[[0-9;]*m')


@pytest.fixture
def configs(tmp_path: Path) -> Path:
    """A directory of configurations with the resources they install beside them."""
    directory = tmp_path / 'configs'
    for relative, content in (
        ('agents/core.md', '# core agent\n'),
        ('rules/rule.md', '# rule\n'),
        ('rules/other.md', '# other rule\n'),
        ('hooks/a.py', 'import h\n'),
        ('hooks/b.py', 'print("b")\n'),
        ('hooks/h.py', 'VALUE = 1\n'),
    ):
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    return directory


def _clean(text: str) -> str:
    """Text with Windows line endings normalized and colors left out."""
    return _ANSI.sub('', text.replace('\r\n', '\n'))


def _team(rules: list[str], script: str, helpers: list[str]) -> dict[str, Any]:
    """A team configuration: an agent, the rules given and one Stop hook running a hooks.files script."""
    return {
        'name': 'Team Env',
        'agents': ['agents/core.md'],
        'rules': rules,
        'hooks': {
            'files': [f'hooks/{script}'],
            'helpers': [f'hooks/{name}' for name in helpers],
            'events': [{'event': 'Stop', 'type': 'command', 'command': script}],
        },
    }


def _first() -> dict[str, Any]:
    """The first version of the team configuration: two rules and hooks/a.py with its helper."""
    return _team(['rules/rule.md', 'rules/other.md'], 'a.py', ['h.py'])


def _next() -> dict[str, Any]:
    """The next version of the same configuration: one rule, and hooks/b.py in place of hooks/a.py."""
    return _team(['rules/rule.md'], 'b.py', [])


def _install_team(configs: Path) -> Path:
    """Install team-1 from the first version and team-lab linking hooks/ from it; return the configuration."""
    cfg = write_config(configs, 'team.yaml', _first())
    assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0
    link = ['--command-names', 'team-lab', '--link-dirs', 'hooks', '--link-from', 'team-1']
    assert run_main([str(cfg), *SKIP, '--yes', *link]) == 0
    return cfg


def _recording_run(argvs: list[list[str]]) -> Callable[..., subprocess.CompletedProcess[Any]]:
    """A subprocess.run stand-in that records the argv of every child run, then runs it."""
    real_run = setup_environment.subprocess.run

    def _run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        if argv[0] == sys.executable:
            argvs.append(list(argv))
        return real_run(argv, **kwargs)

    return _run


def _report(stdout: str) -> list[str]:
    """The lines of the --profile all report, which the parent prints to stdout after every child has run."""
    text = _clean(stdout)
    assert 'Profiles refreshed:' in text, text
    return [line for line in text.split('Profiles refreshed:')[1].split('\n') if line.strip()]


def _wired_in_lab(lab: Path) -> str:
    """The detail of a source's hook file that team-lab's config.json still wires."""
    return (
        f'still wired in profile team-lab ({lab / "config.json"} hooks.Stop) until that profile is refreshed; '
        'a later run with --remove-leftovers removes it'
    )


@pytest.mark.usefixtures('e2e_isolated_home')
class TestProfileAll:
    """--profile all hands the flag to every child and reports what each profile removed and kept."""

    def test_flag_reaches_every_child_and_the_report_reads_each_manifest(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capfd: pytest.CaptureFixture[str],
    ) -> None:
        """A hook file the dependent still wires stays through the first flagged run and leaves with the next."""
        claude_dir = e2e_isolated_home['claude_dir']
        source, lab = claude_dir / 'team-1', claude_dir / 'team-lab'
        base_cfg = write_config(configs, 'base.yaml', {'name': 'Base', 'rules': ['rules/rule.md', 'rules/other.md']})
        assert run_main([str(base_cfg), *SKIP, '--yes']) == 0
        _install_team(configs)
        write_config(configs, 'base.yaml', {'name': 'Base', 'rules': ['rules/rule.md']})
        write_config(configs, 'team.yaml', _next())
        runner = write_child_runner(tmp_path, monkeypatch)
        argvs: list[list[str]] = []
        capfd.readouterr()

        with patch.object(setup_environment.subprocess, 'run', side_effect=_recording_run(argvs)):
            code = run_main(['--profile', 'all', *SKIP, '--yes', FLAG], argv0=str(runner))

        captured = capfd.readouterr()
        assert code == 0, _clean(captured.out + captured.err)
        assert [argv[argv.index('--profile') + 1] for argv in argvs] == ['base', 'team-1', 'team-lab']
        for argv in argvs:
            assert argv[-1] == FLAG, argv
        assert _report(captured.out) == [
            '   * base: ok',
            '       - leftovers removed (1):',
            '           file: rules/other.md',
            '   * team-1: ok',
            '       - leftovers removed (1):',
            '           file: rules/other.md',
            '       - leftovers left (2):',
            f'           file: hooks/a.py (kept: {_wired_in_lab(lab)})',
            '           file: hooks/h.py (kept: stays with hooks/a.py, which is still wired)',
            '   * team-lab: ok',
            '       - leftovers removed (1):',
            '           file: rules/other.md',
        ]
        for path in (claude_dir / 'rules' / 'other.md', source / 'rules' / 'other.md', lab / 'rules' / 'other.md'):
            assert not path.exists(), f'{path} was not removed'
        assert (source / 'hooks' / 'a.py').is_file(), 'team-lab wired it while team-1 ran'
        assert (lab / 'hooks' / 'b.py').as_posix() in (lab / 'config.json').read_text(encoding='utf-8')

        with patch.object(setup_environment.subprocess, 'run', side_effect=_recording_run(argvs)):
            code = run_main(['--profile', 'all', *SKIP, '--yes', FLAG], argv0=str(runner))

        captured = capfd.readouterr()
        assert code == 0, _clean(captured.out + captured.err)
        assert _report(captured.out) == [
            '   * base: ok',
            '   * team-1: ok',
            '       - leftovers removed (1):',
            '           file: hooks/a.py',
            '       - leftovers left (1):',
            '           file: hooks/h.py (kept: stays with hooks/b.py, which is still wired)',
            '   * team-lab: ok',
        ]
        assert not (source / 'hooks' / 'a.py').exists()
        assert (source / 'hooks' / 'h.py').is_file(), 'the new script both profiles run may import it'
        assert (source / 'hooks' / 'b.py').is_file()

    def test_without_the_flag_each_profile_with_leftovers_names_its_command(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capfd: pytest.CaptureFixture[str],
    ) -> None:
        """Every profile with leftovers gets one line naming the command; nothing is removed."""
        claude_dir = e2e_isolated_home['claude_dir']
        base_cfg = write_config(configs, 'base.yaml', {'name': 'Base', 'rules': ['rules/rule.md', 'rules/other.md']})
        assert run_main([str(base_cfg), *SKIP, '--yes']) == 0
        team_cfg = write_config(configs, 'team.yaml', _first())
        assert run_main([str(team_cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0
        write_config(configs, 'base.yaml', {'name': 'Base', 'rules': ['rules/rule.md']})
        write_config(configs, 'team.yaml', _next())
        runner = write_child_runner(tmp_path, monkeypatch)
        argvs: list[list[str]] = []
        capfd.readouterr()

        with patch.object(setup_environment.subprocess, 'run', side_effect=_recording_run(argvs)):
            code = run_main(['--profile', 'all', *SKIP, '--yes'], argv0=str(runner))

        captured = capfd.readouterr()
        assert code == 0, _clean(captured.out + captured.err)
        assert all(FLAG not in argv for argv in argvs)
        assert _report(captured.out) == [
            '   * base: ok',
            '       - 1 leftover(s); remove them with --profile base --remove-leftovers',
            '   * team-1: ok',
            '       - 3 leftover(s); remove them with --profile team-1 --remove-leftovers',
        ]
        assert (claude_dir / 'rules' / 'other.md').is_file()
        assert (claude_dir / 'team-1' / 'rules' / 'other.md').is_file()
        assert (claude_dir / 'team-1' / 'hooks' / 'a.py').is_file()

    def test_dry_run_previews_each_removal_and_reads_no_manifest(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capfd: pytest.CaptureFixture[str],
    ) -> None:
        claude_dir = e2e_isolated_home['claude_dir']
        cfg = write_config(configs, 'team.yaml', _first())
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0
        write_config(configs, 'team.yaml', _next())
        runner = write_child_runner(tmp_path, monkeypatch)
        before = home_state(e2e_isolated_home['home'])
        argvs: list[list[str]] = []
        capfd.readouterr()

        with patch.object(setup_environment.subprocess, 'run', side_effect=_recording_run(argvs)):
            code = run_main(['--profile', 'all', *SKIP, '--dry-run', FLAG], argv0=str(runner))

        captured = capfd.readouterr()
        output = _clean(captured.out + captured.err)
        assert code == 0, output
        assert argvs[0][-4:] == ['--dry-run', '--skip-install', '--no-admin', FLAG]
        assert f'[would be removed in Step 23] file: {claude_dir / "team-1" / "rules" / "other.md"}' in output
        assert _report(captured.out) == ['   * team-1: ok']
        assert home_state(e2e_isolated_home['home']) == before, 'a dry run removes nothing'


@pytest.mark.usefixtures('e2e_isolated_home')
class TestSourceRunRefreshesDependents:
    """A source's Step 24 hands the flag to each dependent, which removes its own leftovers."""

    def test_dependents_own_leftovers_leave_with_the_sources(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capfd: pytest.CaptureFixture[str],
    ) -> None:
        claude_dir = e2e_isolated_home['claude_dir']
        source, lab = claude_dir / 'team-1', claude_dir / 'team-lab'
        _install_team(configs)
        write_config(configs, 'team.yaml', _team(['rules/rule.md'], 'a.py', ['h.py']))
        runner = write_child_runner(tmp_path, monkeypatch)
        argvs: list[list[str]] = []
        capfd.readouterr()

        with patch.object(setup_environment.subprocess, 'run', side_effect=_recording_run(argvs)):
            code = run_main(['--profile', 'team-1', *SKIP, '--yes', FLAG], argv0=str(runner))

        output = _clean(''.join(capfd.readouterr()))
        assert code == 0, output
        assert f'  * team-lab (--profile team-lab --yes --skip-install --no-admin {FLAG})' in output
        assert [argv[argv.index('--profile'):] for argv in argvs] == [
            ['--profile', 'team-lab', '--yes', '--child-run', '--skip-install', '--no-admin', FLAG],
        ]
        assert not (source / 'rules' / 'other.md').exists()
        assert not (lab / 'rules' / 'other.md').exists(), "the dependent's Step 23 removed its own copy"
        assert (lab / 'rules' / 'rule.md').is_file()
        assert read_manifest(lab)['leftovers']['removed'] == ['file: rules/other.md']

    def test_base_source_hands_the_flag_to_its_dependents(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capfd: pytest.CaptureFixture[str],
    ) -> None:
        """The base profile's Step 24 runs in the other branch of the setup and passes the flag the same way."""
        claude_dir = e2e_isolated_home['claude_dir']
        lab = claude_dir / 'team-lab'
        cfg = write_config(configs, 'team.yaml', _first())
        assert run_main([str(cfg), *SKIP, '--yes']) == 0
        link = ['--command-names', 'team-lab', '--link-dirs', 'hooks', '--link-from', 'base']
        assert run_main([str(cfg), *SKIP, '--yes', *link]) == 0
        write_config(configs, 'team.yaml', _team(['rules/rule.md'], 'a.py', ['h.py']))
        runner = write_child_runner(tmp_path, monkeypatch)
        argvs: list[list[str]] = []
        capfd.readouterr()

        with patch.object(setup_environment.subprocess, 'run', side_effect=_recording_run(argvs)):
            code = run_main(['--profile', 'base', *SKIP, '--yes', FLAG], argv0=str(runner))

        output = _clean(''.join(capfd.readouterr()))
        assert code == 0, output
        assert f'  * team-lab (--profile team-lab --yes --skip-install --no-admin {FLAG})' in output
        assert [argv[argv.index('--profile'):] for argv in argvs] == [
            ['--profile', 'team-lab', '--yes', '--child-run', '--skip-install', '--no-admin', FLAG],
        ]
        assert not (claude_dir / 'rules' / 'other.md').exists()
        assert not (lab / 'rules' / 'other.md').exists(), "the dependent's Step 23 removed its own copy"
        assert read_manifest(lab)['leftovers']['removed'] == ['file: rules/other.md']


@pytest.mark.usefixtures('e2e_isolated_home')
class TestStaleSourceRefresh:
    """A dependent run that refreshes its stale source first hands the flag to the source's run."""

    def test_source_refresh_removes_the_sources_leftovers_and_the_dependent_its_own(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capfd: pytest.CaptureFixture[str],
    ) -> None:
        claude_dir = e2e_isolated_home['claude_dir']
        source, lab = claude_dir / 'team-1', claude_dir / 'team-lab'
        cfg = _install_team(configs)
        write_config(configs, 'team.yaml', _team(['rules/rule.md'], 'a.py', ['h.py']))
        runner = write_child_runner(tmp_path, monkeypatch)
        argvs: list[list[str]] = []
        capfd.readouterr()

        with patch.object(setup_environment.subprocess, 'run', side_effect=_recording_run(argvs)):
            code = run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-lab', FLAG], argv0=str(runner))

        output = _clean(''.join(capfd.readouterr()))
        assert code == 0, output
        assert 'Source refresh (profile "team-1" is re-run before this profile installs):' in output
        assert f'* command: --profile team-1 --yes --skip-install --no-admin {FLAG}' in output
        assert [argv[1:] for argv in argvs] == [[
            str(runner), '--profile', 'team-1', '--yes', '--child-run', '--for-dependent', 'team-lab',
            '--skip-install', '--no-admin', FLAG,
        ]]
        assert not (source / 'rules' / 'other.md').exists(), "the source's refresh removed its leftover"
        assert not (lab / 'rules' / 'other.md').exists(), 'the dependent removed its own'
        assert read_manifest(source)['leftovers']['removed'] == ['file: rules/other.md']


def _scheduled(rules: list[str], *, auto_update: bool) -> dict[str, Any]:
    """A configuration with the rules given and, when asked, a daily update job."""
    config: dict[str, Any] = {'name': 'Scheduled Env', 'agents': ['agents/core.md'], 'rules': rules}
    if auto_update:
        config['auto-update'] = {'time': '03:30'}
    return config


def _platform(home: Path, fake: FakeScheduler) -> SchedulerPlatform:
    """The scheduler platform a run in the isolated home builds, with the fake runner."""
    name = fake.platform_name or sys.platform
    return SchedulerPlatform(
        name=name,
        home=home,
        state=setup_environment.toolbox_state_dir(name, home, dict(os.environ)),
        runner=fake,
        environ=dict(os.environ),
    )


@pytest.mark.usefixtures('e2e_isolated_home')
class TestScheduledRun:
    """The scheduled run lists the leftovers in its log and removes none, whatever its environment sets."""

    def test_scheduled_run_with_the_variable_lists_and_keeps(
        self, e2e_isolated_home: dict[str, Path], configs: Path, fake_scheduler: FakeScheduler, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The configuration drops a rule and its own job in one edit: the rule is listed, the job never is."""
        home = e2e_isolated_home['home']
        profile_dir = e2e_isolated_home['claude_dir'] / 'team-1'
        cfg = write_config(configs, 'env.yaml', _scheduled(['rules/rule.md', 'rules/other.md'], auto_update=True))
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0
        write_config(configs, 'env.yaml', _scheduled(['rules/rule.md'], auto_update=False))
        monkeypatch.setenv('CLAUDE_CODE_TOOLBOX_REMOVE_LEFTOVERS', '1')
        runner = write_child_runner(tmp_path, monkeypatch)
        argv = [sys.executable, str(runner), '--profile', 'team-1', '--yes', *SKIP, '--scheduled-run']

        child = subprocess.run(argv, capture_output=True, text=True, check=False, env=dict(os.environ))

        assert child.returncode == 0, child.stdout + child.stderr
        record = setup_environment.read_scheduled_run_record(
            _platform(home, fake_scheduler), 'cc-toolbox-update-team-1',
        )
        assert record is not None, 'the scheduled run leaves a record'
        log = _clean(Path(record['log']).read_text(encoding='utf-8', errors='replace'))
        assert (
            'Leftovers are only listed in a scheduled run; remove them with --profile team-1 --remove-leftovers.'
        ) in log
        block = log.split(HEADING)[1].split('\n', 1)[1].split('\n\n')[0].strip('\n').split('\n')
        assert block == [
            f'  [leftover] file: {profile_dir / "rules" / "other.md"}',
            '  They stay in place.',
            '  A scheduled run only lists leftovers; remove them with --profile team-1 --remove-leftovers.',
        ]
        assert 'Removing leftovers' not in log
        assert (profile_dir / 'rules' / 'other.md').is_file()
        assert [item['path'] for item in read_manifest(profile_dir)['leftovers']['items']] == ['rules/other.md']
