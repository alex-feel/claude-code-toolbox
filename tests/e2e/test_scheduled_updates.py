"""E2E tests for the daily update job the auto-update key registers.

A configuration with ``auto-update: {time: "HH:MM"}`` gives every profile
installed from it one job in the operating system's scheduler that re-runs
the profile's setup through ``uvx cc-toolbox@latest setup --profile NAME
--yes --no-admin --scheduled-run`` (or runs the command the key names). The
tests install real local YAML files into an isolated home through main(),
with the scheduler replaced by the fake every E2E test shares, so a
registration, an update, a removal and a scheduled run itself are seen end to
end without a real job ever reaching the machine. The one test that reaches
the real scheduler runs only where CI says so.
"""

from __future__ import annotations

import email.message
import json
import os
import subprocess
import sys
import urllib.error
from datetime import UTC
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.request import Request

import pytest
import yaml

from scripts import setup_environment
from scripts.setup_environment import AutoUpdateSpec
from scripts.setup_environment import SchedulerPlatform
from tests.e2e.cli_stubs import write_cli_stub
from tests.e2e.fake_scheduler import FakeScheduler
from tests.e2e.profile_support import read_manifest
from tests.e2e.profile_support import run_main
from tests.e2e.profile_support import write_child_runner
from tests.e2e.profile_support import write_config

SKIP = ['--skip-install', '--no-admin']
JOB = 'cc-toolbox-update-team-1'
REAL_SCHEDULER_VARIABLE = 'CLAUDE_CODE_TOOLBOX_E2E_REAL_SCHEDULER'


@pytest.fixture
def configs(tmp_path: Path) -> Path:
    """A directory of configurations with the resources they install beside them."""
    directory = tmp_path / 'configs'
    for relative, content in (
        ('agents/core.md', '# core agent\n'),
        ('rules/rule.md', '# rule\n'),
    ):
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    return directory


def _scheduled(time: str = '03:30', command: str | None = None) -> dict[str, Any]:
    """A configuration whose profiles get a daily update job."""
    auto_update: dict[str, Any] = {'time': time}
    if command is not None:
        auto_update['command'] = command
    return {
        'name': 'Scheduled Env',
        'agents': ['agents/core.md'],
        'rules': ['rules/rule.md'],
        'user-settings': {'theme': 'dark'},
        'auto-update': auto_update,
    }


def _unscheduled() -> dict[str, Any]:
    """The same configuration without the key."""
    config = _scheduled()
    del config['auto-update']
    return config


def _output(capsys: pytest.CaptureFixture[str]) -> str:
    """Everything the run printed, with Windows line endings normalized."""
    captured = capsys.readouterr()
    return (captured.out + captured.err).replace('\r\n', '\n')


def _platform(home: Path, fake: FakeScheduler) -> SchedulerPlatform:
    """The scheduler platform a run in the isolated home builds, with the fake runner."""
    return SchedulerPlatform(
        name=sys.platform,
        home=home,
        state=setup_environment.toolbox_state_dir(sys.platform, home, dict(os.environ)),
        runner=fake,
        environ=dict(os.environ),
    )


def _expected_command(home: Path, fake: FakeScheduler, profile: str) -> list[str]:
    """The command line the OS job of a profile runs on this machine."""
    return setup_environment.scheduled_update_command(_platform(home, fake), profile)


def _job_record(home: Path, fake: FakeScheduler, name: str) -> dict[str, Any] | None:
    return setup_environment.read_job_record(_platform(home, fake), name)


def _run_record(home: Path, fake: FakeScheduler, name: str) -> dict[str, Any] | None:
    return setup_environment.read_scheduled_run_record(_platform(home, fake), name)


def _registered_document(fake: FakeScheduler, name: str) -> str:
    fake.reload()
    assert name in fake.jobs, f'{name} is not registered; jobs: {sorted(fake.jobs)}'
    return fake.jobs[name]


@pytest.mark.usefixtures('e2e_isolated_home')
class TestRegistration:
    """A profile installed from a configuration with auto-update gets one daily job."""

    def test_install_registers_the_daily_job(
        self, e2e_isolated_home: dict[str, Path], configs: Path, fake_scheduler: FakeScheduler,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Step 24 registers the job with the resolved command; the manifest and the state directory record it."""
        home = e2e_isolated_home['home']
        cfg = write_config(configs, 'env.yaml', _scheduled())

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0

        document = _registered_document(fake_scheduler, JOB)
        command = _expected_command(home, fake_scheduler, 'team-1')
        assert command[-6:] == ['setup', '--profile', 'team-1', '--yes', '--no-admin', '--scheduled-run']
        if sys.platform == 'win32':
            assert 'HighestAvailable' in document
            assert 'InteractiveToken' in document
            assert '<DaysInterval>1</DaysInterval>' in document
        elif sys.platform == 'darwin':
            assert 'StartCalendarInterval' in document
        else:
            assert document == f'{JOB}.timer'
        assert _job_record(home, fake_scheduler, JOB) == {'time': '03:30', 'command': None, 'os_command': command}
        manifest = read_manifest(e2e_isolated_home['claude_dir'] / 'team-1')
        assert manifest['auto_update'] == {'time': '03:30', 'command': None, 'job': JOB}
        output = _output(capsys)
        assert 'Scheduled update (auto-update):' in output
        assert f'Job {JOB}: register (no job is registered yet); runs every day at 03:30 local time' in output
        assert f'Runs: {subprocess.list2cmdline(command)}' in output
        assert f'Step 24: Scheduling the daily update job {JOB} (every day at 03:30 local time)...' in output
        assert f'Scheduled update: job {JOB} registered, every day at 03:30 local time' in output

    def test_base_profile_gets_a_job_named_base(
        self, e2e_isolated_home: dict[str, Path], configs: Path, fake_scheduler: FakeScheduler,
    ) -> None:
        """The base profile's job re-runs --profile base."""
        home = e2e_isolated_home['home']
        cfg = write_config(configs, 'env.yaml', _scheduled())

        assert run_main([str(cfg), *SKIP, '--yes']) == 0

        _registered_document(fake_scheduler, 'cc-toolbox-update-base')
        record = _job_record(home, fake_scheduler, 'cc-toolbox-update-base')
        assert record is not None
        assert record['os_command'][-5:] == ['--profile', 'base', '--yes', '--no-admin', '--scheduled-run']
        assert read_manifest(e2e_isolated_home['claude_dir'])['auto_update']['job'] == 'cc-toolbox-update-base'

    def test_rerun_leaves_an_unchanged_job_alone(
        self, configs: Path, fake_scheduler: FakeScheduler,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A re-run with the same time and command registers nothing again."""
        cfg = write_config(configs, 'env.yaml', _scheduled())
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0
        fake_scheduler.reload()
        creations = len(fake_scheduler.creations())
        capsys.readouterr()

        assert run_main(['--profile', 'team-1', *SKIP, '--yes']) == 0

        fake_scheduler.reload()
        assert len(fake_scheduler.creations()) == creations
        output = _output(capsys)
        assert f'Job {JOB}: unchanged (registered as the configuration asks)' in output
        assert f'Scheduled update: job {JOB} unchanged, every day at 03:30 local time' in output

    def test_changed_time_updates_the_job(
        self, e2e_isolated_home: dict[str, Path], configs: Path, fake_scheduler: FakeScheduler,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A new time in the configuration re-registers the job and the record follows."""
        home = e2e_isolated_home['home']
        cfg = write_config(configs, 'env.yaml', _scheduled())
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0
        write_config(configs, 'env.yaml', _scheduled(time='04:00'))
        capsys.readouterr()

        assert run_main(['--profile', 'team-1', *SKIP, '--yes']) == 0

        fake_scheduler.reload()
        assert len(fake_scheduler.creations()) == 2
        record = _job_record(home, fake_scheduler, JOB)
        assert record is not None
        assert record['time'] == '04:00'
        document = _registered_document(fake_scheduler, JOB)
        if sys.platform == 'win32':
            assert 'T04:00:00' in document
        output = _output(capsys)
        assert f'Job {JOB}: update (time 03:30 -> 04:00); runs every day at 04:00 local time' in output
        assert f'Scheduled update: job {JOB} updated, every day at 04:00 local time' in output
        assert read_manifest(e2e_isolated_home['claude_dir'] / 'team-1')['auto_update']['time'] == '04:00'

    def test_custom_command_is_recorded_and_the_job_still_runs_the_toolbox(
        self, e2e_isolated_home: dict[str, Path], configs: Path, fake_scheduler: FakeScheduler,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The configured command is what the scheduled run executes; the OS job runs the toolbox wrapper."""
        home = e2e_isolated_home['home']
        cfg = write_config(configs, 'env.yaml', _scheduled(command='my-update --quiet'))

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0

        record = _job_record(home, fake_scheduler, JOB)
        expected_command = _expected_command(home, fake_scheduler, 'team-1')
        assert record == {'time': '03:30', 'command': 'my-update --quiet', 'os_command': expected_command}
        assert read_manifest(e2e_isolated_home['claude_dir'] / 'team-1')['auto_update']['command'] == 'my-update --quiet'
        output = _output(capsys)
        assert 'Command: my-update --quiet (run under the job lock, logged in the state directory)' in output

    def test_dry_run_shows_the_job_and_registers_nothing(
        self, e2e_isolated_home: dict[str, Path], configs: Path, fake_scheduler: FakeScheduler,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--dry-run names the job, its schedule and its command, and leaves the scheduler alone."""
        home = e2e_isolated_home['home']
        cfg = write_config(configs, 'env.yaml', _scheduled())

        assert run_main([str(cfg), *SKIP, '--dry-run', '--command-names', 'team-1']) == 0

        fake_scheduler.reload()
        assert fake_scheduler.creations() == []
        assert _job_record(home, fake_scheduler, JOB) is None
        output = _output(capsys)
        assert 'Scheduled update (auto-update):' in output
        assert f'Job {JOB}: register (no job is registered yet); runs every day at 03:30 local time' in output
        assert 'Command: the setup of this profile (uvx cc-toolbox@latest' in output
        assert 'Step 24' not in output

    def test_isolated_run_names_the_job_among_the_machine_wide_writes(
        self, configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The job lives in the OS scheduler, so the summary lists it with the other machine-wide writes."""
        cfg = write_config(configs, 'env.yaml', _scheduled())

        assert run_main([str(cfg), *SKIP, '--dry-run', '--command-names', 'team-1']) == 0

        output = _output(capsys)
        assert f'OS scheduler: daily update job {JOB} (every day at 03:30 local time)' in output
        assert '[machine-wide]' in output


@pytest.mark.usefixtures('e2e_isolated_home')
class TestRemoval:
    """Dropping the key, switching configuration or linking content removes the job."""

    def test_removing_the_key_removes_the_job(
        self, e2e_isolated_home: dict[str, Path], configs: Path, fake_scheduler: FakeScheduler,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A re-run of the configuration without auto-update removes the job and its record."""
        home = e2e_isolated_home['home']
        cfg = write_config(configs, 'env.yaml', _scheduled())
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0
        _registered_document(fake_scheduler, JOB)
        write_config(configs, 'env.yaml', _unscheduled())
        capsys.readouterr()

        assert run_main(['--profile', 'team-1', *SKIP, '--yes']) == 0

        fake_scheduler.reload()
        assert JOB not in fake_scheduler.jobs
        assert _job_record(home, fake_scheduler, JOB) is None
        assert read_manifest(e2e_isolated_home['claude_dir'] / 'team-1')['auto_update'] is None
        output = _output(capsys)
        assert f'Step 24: Removing the scheduled update job {JOB}...' in output
        assert f'Scheduled update: job {JOB} removed (the configuration declares no auto-update)' in output

    def test_switching_to_a_configuration_without_the_key_removes_the_job(
        self, e2e_isolated_home: dict[str, Path], configs: Path, fake_scheduler: FakeScheduler,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The switch guard lists the job as residue and --switch-config removes it."""
        home = e2e_isolated_home['home']
        cfg = write_config(configs, 'env.yaml', _scheduled())
        other = write_config(configs, 'other.yaml', {'name': 'Other Env', 'user-settings': {'theme': 'light'}})
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0
        _registered_document(fake_scheduler, JOB)
        capsys.readouterr()

        assert run_main([str(other), *SKIP, '--yes', '--command-names', 'team-1', '--switch-config']) == 0

        fake_scheduler.reload()
        assert JOB not in fake_scheduler.jobs
        assert _job_record(home, fake_scheduler, JOB) is None
        assert read_manifest(e2e_isolated_home['claude_dir'] / 'team-1')['auto_update'] is None
        output = _output(capsys)
        assert f'scheduled update job: {JOB}' in output, 'the guard lists the job among the residue'
        assert f'Removed the scheduled update job {JOB}' in output

    def test_switch_guard_refuses_without_consent_and_keeps_the_job(
        self, configs: Path, fake_scheduler: FakeScheduler,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Without --switch-config the run stops before any write and the job stays."""
        cfg = write_config(configs, 'env.yaml', _scheduled())
        other = write_config(configs, 'other.yaml', {'name': 'Other Env', 'user-settings': {'theme': 'light'}})
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0
        capsys.readouterr()

        assert run_main([str(other), *SKIP, '--yes', '--command-names', 'team-1']) == 1

        _registered_document(fake_scheduler, JOB)
        assert f'scheduled update job: {JOB}' in _output(capsys)

    def test_linked_profile_gets_no_job(
        self, e2e_isolated_home: dict[str, Path], configs: Path, fake_scheduler: FakeScheduler,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A profile that links content from a source is refreshed by the source's job and registers none."""
        cfg = write_config(configs, 'env.yaml', _scheduled())
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0
        capsys.readouterr()

        linked = [str(cfg), *SKIP, '--yes', '--command-names', 'team-2', '--link-dirs', 'all', '--link-from', 'team-1']
        assert run_main(linked) == 0

        fake_scheduler.reload()
        assert sorted(fake_scheduler.jobs) == [JOB]
        assert read_manifest(e2e_isolated_home['claude_dir'] / 'team-2')['auto_update'] is None
        output = _output(capsys)
        reason = 'the profile links content from profile "team-1", whose job refreshes it'
        assert f'Job: none ({reason})' in output
        assert f'Scheduled update: none ({reason})' in output

    def test_converting_a_full_copy_into_a_linked_profile_removes_its_job(
        self, configs: Path, fake_scheduler: FakeScheduler,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A profile that starts linking content loses the job it had as a full copy."""
        cfg = write_config(configs, 'env.yaml', _scheduled())
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-2']) == 0
        _registered_document(fake_scheduler, 'cc-toolbox-update-team-2')
        capsys.readouterr()

        assert run_main(['--profile', 'team-2', *SKIP, '--yes', '--link-dirs', 'all', '--link-from', 'team-1']) == 0

        fake_scheduler.reload()
        assert sorted(fake_scheduler.jobs) == [JOB]
        assert 'Job cc-toolbox-update-team-2: remove (the profile links content from profile "team-1"' in _output(capsys)

    def test_source_rerun_refreshes_the_dependent_without_a_job(
        self, e2e_isolated_home: dict[str, Path], configs: Path, fake_scheduler: FakeScheduler, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Step 23 of the source re-runs the dependent as a child, which registers no job of its own."""
        cfg = write_config(configs, 'env.yaml', _scheduled())
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0
        linked = [str(cfg), *SKIP, '--yes', '--command-names', 'team-2', '--link-dirs', 'all', '--link-from', 'team-1']
        assert run_main(linked) == 0
        runner = write_child_runner(tmp_path, monkeypatch)
        capsys.readouterr()

        assert run_main(['--profile', 'team-1', *SKIP, '--yes'], argv0=str(runner)) == 0

        fake_scheduler.reload()
        assert sorted(fake_scheduler.jobs) == [JOB]
        assert 'Step 23: Refreshing 1 dependent profile(s): team-2...' in _output(capsys)
        assert read_manifest(e2e_isolated_home['claude_dir'] / 'team-2')['auto_update'] is None


@pytest.mark.usefixtures('e2e_isolated_home')
class TestScheduledRun:
    """What the job does when it fires: the lock, the log, the command, the record."""

    @staticmethod
    def _install(configs: Path, config: dict[str, Any]) -> Path:
        cfg = write_config(configs, 'env.yaml', config)
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0
        return cfg

    @staticmethod
    def _scheduled_child(runner: Path) -> subprocess.CompletedProcess[str]:
        argv = [
            sys.executable, str(runner), '--profile', 'team-1', '--yes', '--no-admin', '--skip-install', '--scheduled-run',
        ]
        return subprocess.run(argv, capture_output=True, text=True, check=False, env=dict(os.environ))

    def test_scheduled_run_runs_the_setup_logs_it_and_records_the_outcome(
        self, e2e_isolated_home: dict[str, Path], configs: Path, fake_scheduler: FakeScheduler, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The scheduled run re-runs the profile's setup with its output in a log, and the next manual run reports it."""
        home = e2e_isolated_home['home']
        self._install(configs, _scheduled())
        runner = write_child_runner(tmp_path, monkeypatch)

        child = self._scheduled_child(runner)

        assert child.returncode == 0, child.stdout + child.stderr
        record = _run_record(home, fake_scheduler, JOB)
        assert record is not None, 'the scheduled run leaves a record'
        assert record['outcome'] == 'completed'
        assert record['exit_code'] == 0
        assert record['profile'] == 'team-1'
        log = Path(record['log'])
        assert log.parent == _platform(home, fake_scheduler).state / 'logs'
        text = log.read_text(encoding='utf-8', errors='replace')
        assert f'cc-toolbox scheduled update: profile team-1, job {JOB}' in text
        assert 'Step 24:' in text, 'the setup output lands in the log'
        assert 'Finished: exit code 0' in text
        assert not (_platform(home, fake_scheduler).state / 'update.lock').exists(), 'the lock is released'
        fake_scheduler.reload()
        assert len(fake_scheduler.creations()) == 1, 'the scheduled run leaves its own job as registered'
        capsys.readouterr()

        assert run_main(['--profile', 'team-1', *SKIP, '--yes']) == 0

        output = _output(capsys)
        assert 'Last scheduled run: ' in output
        assert f'exit code 0, log {log}' in output

    def test_scheduled_run_with_a_custom_command_runs_it_instead_of_the_setup(
        self, e2e_isolated_home: dict[str, Path], configs: Path, fake_scheduler: FakeScheduler, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The configured command runs under the lock with its output in the log; the setup does not run."""
        home = e2e_isolated_home['home']
        marker = tmp_path / 'custom-ran.txt'
        script = f"import pathlib; pathlib.Path(r'{marker}').write_text('ran'); print('custom command ran')"
        command = f'"{sys.executable}" -c "{script}"'
        self._install(configs, _scheduled(command=command))
        runner = write_child_runner(tmp_path, monkeypatch)

        child = self._scheduled_child(runner)

        assert child.returncode == 0, child.stdout + child.stderr
        assert marker.read_text() == 'ran'
        record = _run_record(home, fake_scheduler, JOB)
        assert record is not None
        assert record['command'] == command
        assert record['exit_code'] == 0
        text = Path(record['log']).read_text(encoding='utf-8', errors='replace')
        assert 'custom command ran' in text
        assert 'Step 1' not in text, 'the setup itself does not run for a custom command'

    def test_scheduled_run_waits_for_the_lock_then_skips_with_a_logged_reason(
        self, e2e_isolated_home: dict[str, Path], configs: Path, fake_scheduler: FakeScheduler,
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Another scheduled run holds the lock past the wait: this one logs why, records the skip and exits 1."""
        home = e2e_isolated_home['home']
        self._install(configs, _scheduled())
        platform = _platform(home, fake_scheduler)
        lock = platform.state / 'update.lock'
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text('4242\n', encoding='utf-8')
        monkeypatch.setattr(setup_environment, 'SCHEDULED_UPDATE_LOCK_WAIT_SECONDS', 0)
        monkeypatch.setattr(setup_environment, '_redirect_output_to', lambda _path: None)
        capsys.readouterr()

        code = run_main(['--profile', 'team-1', *SKIP, '--yes', '--scheduled-run'])

        assert code == 1
        record = _run_record(home, fake_scheduler, JOB)
        assert record is not None
        assert record['outcome'] == 'skipped'
        assert 'held the lock' in str(record['reason'])
        assert 'Skipped: another scheduled run held the lock' in Path(record['log']).read_text(encoding='utf-8')
        assert lock.read_text(encoding='utf-8').strip() == '4242', 'the holder keeps its lock'
        assert 'Step 1' not in _output(capsys), 'the setup did not run'

    def test_scheduled_run_keeps_the_last_30_logs(
        self, e2e_isolated_home: dict[str, Path], configs: Path, fake_scheduler: FakeScheduler,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Older logs of the job are pruned to the newest 30 after each run."""
        home = e2e_isolated_home['home']
        self._install(configs, _scheduled())
        logs = _platform(home, fake_scheduler).state / 'logs'
        logs.mkdir(parents=True, exist_ok=True)
        for index in range(32):
            (logs / f'{JOB}-202609{index:02d}-000000.log').write_text('old\n', encoding='utf-8')
        monkeypatch.setattr(setup_environment, '_redirect_output_to', lambda _path: None)

        assert run_main(['--profile', 'team-1', *SKIP, '--yes', '--scheduled-run']) == 0

        remaining = sorted(logs.glob(f'{JOB}-*.log'))
        assert len(remaining) == 30
        assert remaining[-1].read_text(encoding='utf-8').startswith('cc-toolbox scheduled update'), 'the newest is this run'

    def test_scheduled_run_leaves_its_own_changed_job_to_the_next_manual_run(
        self, e2e_isolated_home: dict[str, Path], configs: Path, fake_scheduler: FakeScheduler,
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A configuration whose time moved is applied by the next manual run, never by the job itself."""
        home = e2e_isolated_home['home']
        self._install(configs, _scheduled())
        write_config(configs, 'env.yaml', _scheduled(time='04:00'))
        monkeypatch.setattr(setup_environment, '_redirect_output_to', lambda _path: None)
        capsys.readouterr()

        assert run_main(['--profile', 'team-1', *SKIP, '--yes', '--scheduled-run']) == 0

        fake_scheduler.reload()
        assert len(fake_scheduler.creations()) == 1
        record = _job_record(home, fake_scheduler, JOB)
        assert record is not None
        assert record['time'] == '03:30'
        output = _output(capsys)
        assert 'a scheduled run leaves its own job as registered, the next manual run applies the change' in output
        assert f'Scheduled update: job {JOB} left as registered, every day at 04:00 local time' in output

        assert run_main(['--profile', 'team-1', *SKIP, '--yes']) == 0

        record = _job_record(home, fake_scheduler, JOB)
        assert record is not None
        assert record['time'] == '04:00'

    def test_scheduled_run_needs_a_single_profile(
        self, configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--scheduled-run without --profile NAME (or with all) is refused."""
        cfg = write_config(configs, 'env.yaml', _scheduled())

        assert run_main([str(cfg), *SKIP, '--yes', '--scheduled-run']) == 1
        assert run_main(['--profile', 'all', *SKIP, '--yes', '--scheduled-run']) == 1

        refusal = '--scheduled-run runs the daily update of one installed profile and needs --profile NAME'
        assert _output(capsys).count(refusal) == 2


@pytest.mark.usefixtures('e2e_isolated_home')
class TestWindowsElevation:
    """On Windows the job runs with the highest privileges, so registering it needs an elevated run."""

    def test_no_admin_in_a_non_elevated_process_reports_the_failed_registration(
        self, e2e_isolated_home: dict[str, Path], configs: Path, fake_scheduler: FakeScheduler,
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The registration is reported as failed with the remedy, nothing is registered, and the run exits 1."""
        monkeypatch.setattr(setup_environment, '_scheduler_registration_needs_elevation', lambda: True)
        cfg = write_config(configs, 'env.yaml', _scheduled())

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 1

        fake_scheduler.reload()
        assert fake_scheduler.creations() == []
        output = _output(capsys)
        assert f'The scheduled update job {JOB} was not registered' in output
        assert 'Run the setup from an elevated terminal, or without --no-admin' in output
        assert 'The scheduled update job (auto-update) was not applied:' in output
        assert (e2e_isolated_home['claude_dir'] / 'team-1' / 'agents' / 'core.md').is_file(), 'the rest of the setup ran'

    def test_elevated_process_registers_under_no_admin(
        self, configs: Path, fake_scheduler: FakeScheduler,
    ) -> None:
        """--no-admin in a process that already holds administrator rights registers the job."""
        cfg = write_config(configs, 'env.yaml', _scheduled())

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0

        _registered_document(fake_scheduler, JOB)


GITHUB_CONFIG_URL = 'https://raw.githubusercontent.com/acme/private-configs/main/env.yaml'


class _Response:
    """The part of an HTTP response the fetch reads."""

    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self) -> bytes:
        """Return the body.

        Returns:
            The response bytes.
        """
        return self.body


class _PrivateGitHub:
    """A urlopen stand-in for a private repository that answers only to one bearer token."""

    def __init__(self, token: str, body: bytes) -> None:
        self.token = token
        self.body = body
        self.requests: list[Request] = []

    def __call__(self, request: Request, *_args: Any, **_kwargs: Any) -> _Response:
        """Answer one request.

        Returns:
            The response when the bearer token matches.

        Raises:
            urllib.error.HTTPError: 401 for every other request.
        """
        self.requests.append(request)
        if request.get_header('Authorization') != f'Bearer {self.token}':
            raise urllib.error.HTTPError(request.full_url, 401, 'Unauthorized', email.message.Message(), None)
        return _Response(self.body)


@pytest.mark.usefixtures('e2e_isolated_home')
class TestUnattendedCredentials:
    """A private configuration is fetched with the logged-in host CLI's token when no variable applies."""

    @pytest.fixture
    def stubs(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        """A directory first on PATH for stub gh and glab, shadowing the machine's own."""
        directory = tmp_path / 'bin'
        directory.mkdir()
        monkeypatch.setenv('PATH', f'{directory}{os.pathsep}{os.environ.get("PATH", "")}')
        for variable in ('GITHUB_TOKEN', 'GITLAB_TOKEN', 'REPO_TOKEN'):
            monkeypatch.delenv(variable, raising=False)
        return directory

    @staticmethod
    def _private_config() -> bytes:
        config = {'name': 'Private Env', 'user-settings': {'theme': 'dark'}, 'auto-update': {'time': '03:30'}}
        return yaml.safe_dump(config, sort_keys=False).encode('utf-8')

    def test_private_configuration_is_fetched_with_the_gh_token(
        self, stubs: Path, fake_scheduler: FakeScheduler, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """GITHUB_TOKEN is absent, gh is logged in: the fetch authenticates with gh's token and never prints it."""
        write_cli_stub(stubs, 'gh', ['ghp_stub_token_value'])
        private = _PrivateGitHub('ghp_stub_token_value', self._private_config())

        with patch('scripts.setup_environment.urlopen', private):
            code = run_main([GITHUB_CONFIG_URL, *SKIP, '--yes', '--command-names', 'team-1'])

        assert code == 0
        assert any(request.get_header('Authorization') == 'Bearer ghp_stub_token_value' for request in private.requests)
        output = _output(capsys)
        assert 'Using the stored GitHub CLI (gh) login for github.com' in output
        assert 'ghp_stub_token_value' not in output
        assert 'cannot authenticate' not in output, 'the gh login covers the scheduled job too'
        _registered_document(fake_scheduler, JOB)

    def test_job_for_a_private_configuration_warns_without_an_unattended_credential(
        self, stubs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A token passed with --env lives in this run only, and gh is not logged in: the summary and Step 24 warn."""
        write_cli_stub(stubs, 'gh', ['no oauth token found for github.com'], stderr=True, exit_code=1)
        private = _PrivateGitHub('ghp_for_this_run', self._private_config())

        with patch('scripts.setup_environment.urlopen', private):
            code = run_main([
                GITHUB_CONFIG_URL, *SKIP, '--yes', '--command-names', 'team-1', '--env', 'GITHUB_TOKEN=ghp_for_this_run',
            ])

        assert code == 0
        output = _output(capsys)
        assert 'The scheduled update job cannot authenticate to github.com' in output
        assert 'GITHUB_TOKEN' in output
        assert 'gh auth login --hostname github.com' in output
        assert 'ghp_for_this_run' not in output

    def test_public_configuration_warns_nothing(
        self, stubs: Path, configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A configuration that needed no credentials gets no credential warning."""
        write_cli_stub(stubs, 'gh', ['no oauth token found for github.com'], stderr=True, exit_code=1)
        cfg = write_config(configs, 'env.yaml', _scheduled())

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0

        assert 'cannot authenticate' not in _output(capsys)


@pytest.mark.real_scheduler
@pytest.mark.skipif(
    os.environ.get(REAL_SCHEDULER_VARIABLE) != '1',
    reason=f'registers a job with the real OS scheduler; runs only where {REAL_SCHEDULER_VARIABLE}=1 (CI sets it)',
)
def test_real_scheduler_registers_queries_and_removes_a_job(tmp_path: Path) -> None:
    """The real backend of this OS registers a daily job, reports it, and removes it without a trace."""
    platform = SchedulerPlatform(
        name=sys.platform,
        home=Path.home(),
        state=tmp_path / 'state',
        runner=setup_environment._run_scheduler_command,
        environ=dict(os.environ),
    )
    problems = setup_environment.scheduler_problems(platform)
    assert problems == [], problems
    name = f'cc-toolbox-update-e2e-real-{os.getpid()}'
    command = [sys.executable, '-c', 'pass']
    spec = AutoUpdateSpec(3, 30, None)
    registration = setup_environment.plan_job_registration(platform, name, command, spec, datetime.now(UTC).astimezone())
    try:
        setup_environment.apply_job_registration(platform, registration)
        registered = setup_environment.query_job_registration(platform, name)
        assert registered is not None, 'the scheduler reports the registered job'
        if sys.platform == 'win32':
            assert name in registered
    finally:
        setup_environment.remove_job_registration(platform, name)
    assert setup_environment.query_job_registration(platform, name) is None
    for path in registration.files:
        if path.suffix == '.plist' or path.parent.name == 'user':
            assert not path.exists(), f'{path} was left behind'
    (tmp_path / 'state' / 'done').write_text(json.dumps({'job': name}), encoding='utf-8')
