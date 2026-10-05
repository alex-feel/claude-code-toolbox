"""E2E tests for the daily update job the auto-update key registers.

A configuration with ``auto-update: {time: "HH:MM"}`` gives every profile
installed from it one job in the operating system's scheduler that re-runs
the profile's setup through ``uvx cc-toolbox@latest setup --profile NAME
--yes --no-admin --scheduled-run`` (or runs the command the key names). The
tests install real local YAML files into an isolated home through main(),
with the scheduler replaced by the fake every E2E test shares, so a
registration, an update, a removal and a scheduled run itself are seen end to
end without a real job ever reaching the machine. The fake can take the shape
of another platform's scheduler (Windows, Linux with and without a systemd
user manager), so every backend's path through main() runs on every CI
operating system. The one test that reaches the real scheduler runs only
where CI says so.
"""

from __future__ import annotations

import email.message
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
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
WINDOWS_ONLY = pytest.mark.skipif(
    sys.platform != 'win32',
    reason='a Task Scheduler task runs in a console of its own, which only Windows can give a child process',
)


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
    """The scheduler platform a run in the isolated home builds, with the fake runner.

    A fake shaped for another platform names that platform, so the state
    directory is the one the run used.

    Returns:
        The platform.
    """
    name = fake.platform_name or sys.platform
    return SchedulerPlatform(
        name=name,
        home=home,
        state=setup_environment.toolbox_state_dir(name, home, dict(os.environ)),
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


def _custom_command(tmp_path: Path, marker_name: str, text: str) -> tuple[str, Path]:
    """A command line that writes a marker file and prints a line, for the scheduled run to execute."""
    marker = tmp_path / marker_name
    script = f"import pathlib; pathlib.Path(r'{marker}').write_text('ran'); print('{text}')"
    return f'"{sys.executable}" -c "{script}"', marker


def _scheduled_child(runner: Path, **run_kwargs: Any) -> subprocess.CompletedProcess[str]:
    argv = [
        sys.executable, str(runner), '--profile', 'team-1', '--yes', '--no-admin', '--skip-install', '--scheduled-run',
    ]
    return subprocess.run(argv, text=True, check=False, env=dict(os.environ), **run_kwargs)


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

    def test_changed_command_updates_the_job(
        self, e2e_isolated_home: dict[str, Path], configs: Path, fake_scheduler: FakeScheduler, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A new command re-registers the job, the records follow, and the next scheduled run executes the new one."""
        home = e2e_isolated_home['home']
        first, first_marker = _custom_command(tmp_path, 'first.txt', 'first command ran')
        second, second_marker = _custom_command(tmp_path, 'second.txt', 'second command ran')
        cfg = write_config(configs, 'env.yaml', _scheduled(command=first))
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0
        write_config(configs, 'env.yaml', _scheduled(command=second))
        capsys.readouterr()

        assert run_main(['--profile', 'team-1', *SKIP, '--yes']) == 0

        fake_scheduler.reload()
        assert len(fake_scheduler.creations()) == 2
        record = _job_record(home, fake_scheduler, JOB)
        assert record is not None
        assert record['command'] == second
        assert read_manifest(e2e_isolated_home['claude_dir'] / 'team-1')['auto_update']['command'] == second
        output = _output(capsys)
        assert f'Job {JOB}: update (command {first} -> {second}); runs every day at 03:30 local time' in output
        runner = write_child_runner(tmp_path, monkeypatch)

        child = _scheduled_child(runner, capture_output=True)

        assert child.returncode == 0, child.stdout + child.stderr
        assert second_marker.read_text() == 'ran'
        assert not first_marker.exists(), 'the scheduled run executes the command the manifest records now'
        run = _run_record(home, fake_scheduler, JOB)
        assert run is not None
        assert run['command'] == second

    def test_removed_command_falls_back_to_the_profile_setup(
        self, e2e_isolated_home: dict[str, Path], configs: Path, fake_scheduler: FakeScheduler, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Dropping the command re-registers the job for the profile setup, which the next scheduled run performs."""
        home = e2e_isolated_home['home']
        command, marker = _custom_command(tmp_path, 'custom.txt', 'custom command ran')
        cfg = write_config(configs, 'env.yaml', _scheduled(command=command))
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0
        write_config(configs, 'env.yaml', _scheduled())
        capsys.readouterr()

        assert run_main(['--profile', 'team-1', *SKIP, '--yes']) == 0

        fake_scheduler.reload()
        assert len(fake_scheduler.creations()) == 2
        record = _job_record(home, fake_scheduler, JOB)
        assert record is not None
        assert record['command'] is None
        assert read_manifest(e2e_isolated_home['claude_dir'] / 'team-1')['auto_update']['command'] is None
        assert f'Job {JOB}: update (command {command} -> the profile setup)' in _output(capsys)
        runner = write_child_runner(tmp_path, monkeypatch)

        child = _scheduled_child(runner, capture_output=True)

        assert child.returncode == 0, child.stdout + child.stderr
        assert not marker.exists(), 'the dropped command no longer runs'
        run = _run_record(home, fake_scheduler, JOB)
        assert run is not None
        assert 'Step 24:' in Path(run['log']).read_text(encoding='utf-8', errors='replace'), 'the setup ran instead'

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
        """The switch guard lists the job as residue and --switch-config lets Step 24 remove it."""
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
        assert f'The scheduled update job {JOB} is removed in Step 24' in output
        assert f'Step 24: Removing the scheduled update job {JOB}...' in output
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

    def test_switch_under_no_admin_on_windows_keeps_the_job_recorded_until_an_elevated_run_removes_it(
        self, e2e_isolated_home: dict[str, Path], configs: Path, windows_scheduler: FakeScheduler,
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A non-elevated switch cannot remove the task: the run fails with the remedy; an elevated re-run removes it."""
        home = e2e_isolated_home['home']
        cfg = write_config(configs, 'env.yaml', _scheduled())
        other = write_config(configs, 'other.yaml', {'name': 'Other Env', 'user-settings': {'theme': 'light'}})
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0
        _registered_document(windows_scheduler, JOB)
        monkeypatch.setattr(setup_environment, 'is_admin', lambda: False)
        capsys.readouterr()

        assert run_main([str(other), *SKIP, '--yes', '--command-names', 'team-1', '--switch-config']) == 1

        _registered_document(windows_scheduler, JOB)
        assert _job_record(home, windows_scheduler, JOB) is not None, 'the job record survives the refused removal'
        manifest = read_manifest(e2e_isolated_home['claude_dir'] / 'team-1')
        assert manifest['auto_update'] == {'time': '03:30', 'command': None, 'job': JOB}
        output = _output(capsys)
        assert f'The scheduled update job {JOB} was not removed' in output
        assert 'Run the setup from an elevated terminal, or without --no-admin' in output
        assert 'The scheduled update job (auto-update) was not applied:' in output
        assert f'The manifest keeps recording the job {JOB} until a run removes it' in output
        monkeypatch.setattr(setup_environment, 'is_admin', lambda: True)
        capsys.readouterr()

        assert run_main(['--profile', 'team-1', *SKIP, '--yes']) == 0

        windows_scheduler.reload()
        assert JOB not in windows_scheduler.jobs
        assert _job_record(home, windows_scheduler, JOB) is None
        assert read_manifest(e2e_isolated_home['claude_dir'] / 'team-1')['auto_update'] is None
        assert f'Removed the scheduled update job {JOB}' in _output(capsys)

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

    @pytest.fixture
    def in_process(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A scheduled run inside the test process keeps its terminal, so pytest captures its output."""
        monkeypatch.setattr(setup_environment, '_detach_from_terminal', lambda _path: None)

    def test_scheduled_run_runs_the_setup_logs_it_and_records_the_outcome(
        self, e2e_isolated_home: dict[str, Path], configs: Path, fake_scheduler: FakeScheduler, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The scheduled run re-runs the profile's setup with its output in a log, and the next manual run reports it."""
        home = e2e_isolated_home['home']
        self._install(configs, _scheduled())
        runner = write_child_runner(tmp_path, monkeypatch)

        child = _scheduled_child(runner, capture_output=True)

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

    @WINDOWS_ONLY
    def test_scheduled_run_in_its_own_console_logs_the_setup_output(
        self, e2e_isolated_home: dict[str, Path], configs: Path, fake_scheduler: FakeScheduler, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A run started the way Task Scheduler starts it, with a console of its own and no pipes, logs every line."""
        home = e2e_isolated_home['home']
        self._install(configs, _scheduled())
        runner = write_child_runner(tmp_path, monkeypatch)

        child = _scheduled_child(runner, creationflags=getattr(subprocess, 'CREATE_NEW_CONSOLE', 0), timeout=600)

        assert child.returncode == 0
        record = _run_record(home, fake_scheduler, JOB)
        assert record is not None, 'the scheduled run leaves a record'
        assert record['outcome'] == 'completed'
        assert record['exit_code'] == 0
        assert record['reason'] is None
        text = Path(record['log']).read_text(encoding='utf-8', errors='replace')
        assert 'Step 24:' in text, 'the setup output lands in the log when stdout was the console'
        assert 'Scheduled update: job' in text
        assert 'Finished: exit code 0' in text
        assert 'The handle is invalid' not in text

    @pytest.mark.usefixtures('in_process')
    def test_scheduled_run_records_a_crash_of_the_setup(
        self, e2e_isolated_home: dict[str, Path], configs: Path, fake_scheduler: FakeScheduler,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A setup that raises is a completed run with exit code 1: the traceback is in the log, the record names it."""
        home = e2e_isolated_home['home']
        self._install(configs, _scheduled())
        capsys.readouterr()

        def _crash(*_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError('the setup fell over')

        with patch.object(setup_environment, '_run_setup', _crash):
            code = run_main(['--profile', 'team-1', *SKIP, '--yes', '--scheduled-run'])

        assert code == 1
        record = _run_record(home, fake_scheduler, JOB)
        assert record is not None
        assert record['outcome'] == 'completed'
        assert record['exit_code'] == 1
        assert record['reason'] == 'the run raised RuntimeError: the setup fell over'
        text = Path(record['log']).read_text(encoding='utf-8', errors='replace')
        assert 'Traceback (most recent call last)' in text
        assert 'the setup fell over' in text
        assert 'Finished: exit code 1' in text
        assert not (_platform(home, fake_scheduler).state / 'update.lock').exists(), 'the lock is released'
        capsys.readouterr()

        assert run_main(['--profile', 'team-1', *SKIP, '--yes']) == 0

        assert f'exit code 1, log {record["log"]}' in _output(capsys)

    def test_scheduled_run_with_a_custom_command_runs_it_instead_of_the_setup(
        self, e2e_isolated_home: dict[str, Path], configs: Path, fake_scheduler: FakeScheduler, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The configured command runs under the lock with its output in the log; the setup does not run."""
        home = e2e_isolated_home['home']
        command, marker = _custom_command(tmp_path, 'custom-ran.txt', 'custom command ran')
        self._install(configs, _scheduled(command=command))
        runner = write_child_runner(tmp_path, monkeypatch)

        child = _scheduled_child(runner, capture_output=True)

        assert child.returncode == 0, child.stdout + child.stderr
        assert marker.read_text() == 'ran'
        record = _run_record(home, fake_scheduler, JOB)
        assert record is not None
        assert record['command'] == command
        assert record['exit_code'] == 0
        text = Path(record['log']).read_text(encoding='utf-8', errors='replace')
        assert 'custom command ran' in text
        assert 'Step 1' not in text, 'the setup itself does not run for a custom command'

    @pytest.mark.usefixtures('in_process')
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

    @pytest.mark.usefixtures('in_process')
    def test_scheduled_run_takes_over_a_stale_lock(
        self, e2e_isolated_home: dict[str, Path], configs: Path, fake_scheduler: FakeScheduler,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A lock left by a run killed mid-night does not block the next one: it is taken over, noted, and released."""
        home = e2e_isolated_home['home']
        self._install(configs, _scheduled())
        lock = _platform(home, fake_scheduler).state / 'update.lock'
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text('4242\n', encoding='utf-8')
        old = lock.stat().st_mtime - setup_environment.SCHEDULED_UPDATE_LOCK_STALE_SECONDS - 60
        os.utime(lock, (old, old))
        capsys.readouterr()

        assert run_main(['--profile', 'team-1', *SKIP, '--yes', '--scheduled-run']) == 0

        record = _run_record(home, fake_scheduler, JOB)
        assert record is not None
        assert record['outcome'] == 'completed'
        assert record['exit_code'] == 0
        text = Path(record['log']).read_text(encoding='utf-8', errors='replace')
        assert f'Took over the stale lock {lock}' in text
        assert 'Step 24:' in _output(capsys), 'the setup ran'
        assert not lock.exists(), 'the lock is released afterwards'

    @pytest.mark.usefixtures('in_process')
    def test_scheduled_run_keeps_the_last_30_logs(
        self, e2e_isolated_home: dict[str, Path], configs: Path, fake_scheduler: FakeScheduler,
    ) -> None:
        """Older logs of the job are pruned to the newest 30 after each run."""
        home = e2e_isolated_home['home']
        self._install(configs, _scheduled())
        logs = _platform(home, fake_scheduler).state / 'logs'
        logs.mkdir(parents=True, exist_ok=True)
        for index in range(32):
            (logs / f'{JOB}-202609{index:02d}-000000.log').write_text('old\n', encoding='utf-8')

        assert run_main(['--profile', 'team-1', *SKIP, '--yes', '--scheduled-run']) == 0

        remaining = sorted(logs.glob(f'{JOB}-*.log'))
        assert len(remaining) == 30
        assert remaining[-1].read_text(encoding='utf-8').startswith('cc-toolbox scheduled update'), 'the newest is this run'

    @pytest.mark.usefixtures('in_process')
    def test_scheduled_run_leaves_its_own_changed_job_to_the_next_manual_run(
        self, e2e_isolated_home: dict[str, Path], configs: Path, fake_scheduler: FakeScheduler,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A configuration whose time moved is applied by the next manual run, never by the job itself."""
        home = e2e_isolated_home['home']
        self._install(configs, _scheduled())
        write_config(configs, 'env.yaml', _scheduled(time='04:00'))
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

    @pytest.mark.usefixtures('in_process')
    def test_scheduled_run_leaves_the_removal_of_its_own_job_to_the_next_manual_run(
        self, e2e_isolated_home: dict[str, Path], configs: Path, fake_scheduler: FakeScheduler,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A configuration that dropped the key is first seen by the job itself: the job stays for a manual run to remove."""
        home = e2e_isolated_home['home']
        self._install(configs, _scheduled())
        write_config(configs, 'env.yaml', _unscheduled())
        capsys.readouterr()

        assert run_main(['--profile', 'team-1', *SKIP, '--yes', '--scheduled-run']) == 0

        _registered_document(fake_scheduler, JOB)
        assert _job_record(home, fake_scheduler, JOB) is not None
        run = _run_record(home, fake_scheduler, JOB)
        assert run is not None
        assert run['outcome'] == 'completed'
        assert run['exit_code'] == 0
        manifest = read_manifest(e2e_isolated_home['claude_dir'] / 'team-1')
        assert manifest['auto_update'] == {'time': '03:30', 'command': None, 'job': JOB}, 'the manifest keeps the job'
        output = _output(capsys)
        assert (
            f'Job {JOB}: deferred (the configuration declares no auto-update; a scheduled run leaves its own job as '
            'registered, the next manual run removes it)'
        ) in output
        assert f'Scheduled update: job {JOB} left as registered, every day at 03:30 local time' in output
        capsys.readouterr()

        assert run_main(['--profile', 'team-1', *SKIP, '--yes']) == 0

        fake_scheduler.reload()
        assert JOB not in fake_scheduler.jobs
        assert _job_record(home, fake_scheduler, JOB) is None
        assert read_manifest(e2e_isolated_home['claude_dir'] / 'team-1')['auto_update'] is None
        assert f'Scheduled update: job {JOB} removed (the configuration declares no auto-update)' in _output(capsys)

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
    """On Windows the job runs with the highest privileges, so registering it needs an elevated run.

    The fake takes the shape of the Windows scheduler, so the real elevation
    check runs on every CI operating system; the process's rights are what
    each test says they are.
    """

    def test_no_admin_in_a_non_elevated_process_reports_the_failed_registration(
        self, e2e_isolated_home: dict[str, Path], configs: Path, windows_scheduler: FakeScheduler,
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The registration is reported as failed with the remedy, nothing is registered, and the run exits 1."""
        monkeypatch.setattr(setup_environment, 'is_admin', lambda: False)
        cfg = write_config(configs, 'env.yaml', _scheduled())

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 1

        windows_scheduler.reload()
        assert windows_scheduler.creations() == []
        output = _output(capsys)
        assert f'The scheduled update job {JOB} was not registered' in output
        assert 'Run the setup from an elevated terminal, or without --no-admin' in output
        assert 'The scheduled update job (auto-update) was not applied:' in output
        assert (e2e_isolated_home['claude_dir'] / 'team-1' / 'agents' / 'core.md').is_file(), 'the rest of the setup ran'

    def test_elevated_process_registers_under_no_admin(
        self, configs: Path, windows_scheduler: FakeScheduler, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--no-admin in a process that already holds administrator rights registers the task."""
        monkeypatch.setattr(setup_environment, 'is_admin', lambda: True)
        cfg = write_config(configs, 'env.yaml', _scheduled())

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0

        document = _registered_document(windows_scheduler, JOB)
        assert 'HighestAvailable' in document

    def test_other_platforms_register_without_administrator_rights(
        self, configs: Path, linux_scheduler: FakeScheduler, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A systemd user timer needs no rights the process lacks, whatever is_admin says."""
        monkeypatch.setattr(setup_environment, 'is_admin', lambda: False)
        cfg = write_config(configs, 'env.yaml', _scheduled())

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0

        assert _registered_document(linux_scheduler, JOB) == f'{JOB}.timer'


@pytest.mark.usefixtures('e2e_isolated_home')
class TestCronFallback:
    """On a Linux machine without a systemd user manager the job is a tagged crontab entry.

    The fake takes that shape, so the crontab backend runs through main() on
    every CI operating system.
    """

    OTHER_LINE = '0 1 * * * echo other # other'

    def _seed_user_crontab(self, cron_scheduler: FakeScheduler) -> None:
        cron_scheduler.jobs['other'] = f'cron:{self.OTHER_LINE}'
        cron_scheduler.save()

    def test_install_registers_a_tagged_crontab_line_and_the_logs_directory(
        self, e2e_isolated_home: dict[str, Path], configs: Path, cron_scheduler: FakeScheduler,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The line carries the daily time, the resolved command and the job tag; the user's own lines survive."""
        home = e2e_isolated_home['home']
        self._seed_user_crontab(cron_scheduler)
        cfg = write_config(configs, 'env.yaml', _scheduled())

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0

        cron_scheduler.reload()
        line = cron_scheduler.jobs[JOB].removeprefix('cron:')
        assert line.startswith('30 3 * * * PATH=')
        assert line.endswith(f'# {JOB}')
        assert 'cc-toolbox@latest setup --profile team-1 --yes --no-admin --scheduled-run' in line
        assert cron_scheduler.crontab_lines() == [self.OTHER_LINE, line]
        state = _platform(home, cron_scheduler).state
        assert (state / 'logs').is_dir(), 'the directory the line redirects into exists before the job first fires'
        assert f'{state / "logs"}' in line
        assert _job_record(home, cron_scheduler, JOB) is not None
        output = _output(capsys)
        cron_note = 'The job is a crontab entry: it fires only while a cron daemon runs and does not catch up a missed day'
        assert cron_note in output
        assert f'Scheduled update: job {JOB} registered, every day at 03:30 local time' in output

    def test_rerun_leaves_the_line_alone(
        self, configs: Path, cron_scheduler: FakeScheduler, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """An unchanged configuration installs no second crontab."""
        cfg = write_config(configs, 'env.yaml', _scheduled())
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0
        cron_scheduler.reload()
        installs = len(cron_scheduler.creations())
        capsys.readouterr()

        assert run_main(['--profile', 'team-1', *SKIP, '--yes']) == 0

        cron_scheduler.reload()
        assert len(cron_scheduler.creations()) == installs
        assert f'Job {JOB}: unchanged (registered as the configuration asks)' in _output(capsys)

    def test_changed_time_rewrites_the_line(
        self, configs: Path, cron_scheduler: FakeScheduler, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A new time replaces the tagged line and only that line."""
        self._seed_user_crontab(cron_scheduler)
        cfg = write_config(configs, 'env.yaml', _scheduled())
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0
        write_config(configs, 'env.yaml', _scheduled(time='04:00'))
        capsys.readouterr()

        assert run_main(['--profile', 'team-1', *SKIP, '--yes']) == 0

        cron_scheduler.reload()
        lines = cron_scheduler.crontab_lines()
        assert len(lines) == 2
        assert lines[0] == self.OTHER_LINE
        assert lines[1].startswith('0 4 * * * ')
        assert lines[1].endswith(f'# {JOB}')
        assert f'Job {JOB}: update (time 03:30 -> 04:00)' in _output(capsys)

    def test_removing_the_key_removes_only_the_tagged_line(
        self, e2e_isolated_home: dict[str, Path], configs: Path, cron_scheduler: FakeScheduler,
    ) -> None:
        """The user's other lines survive the removal."""
        home = e2e_isolated_home['home']
        self._seed_user_crontab(cron_scheduler)
        cfg = write_config(configs, 'env.yaml', _scheduled())
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0
        write_config(configs, 'env.yaml', _unscheduled())

        assert run_main(['--profile', 'team-1', *SKIP, '--yes']) == 0

        cron_scheduler.reload()
        assert cron_scheduler.crontab_lines() == [self.OTHER_LINE]
        assert _job_record(home, cron_scheduler, JOB) is None
        assert read_manifest(e2e_isolated_home['claude_dir'] / 'team-1')['auto_update'] is None

    def test_switching_configuration_removes_only_the_tagged_line(
        self, configs: Path, cron_scheduler: FakeScheduler, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--switch-config to a configuration without the key removes the job's line and keeps the rest."""
        self._seed_user_crontab(cron_scheduler)
        cfg = write_config(configs, 'env.yaml', _scheduled())
        other = write_config(configs, 'other.yaml', {'name': 'Other Env', 'user-settings': {'theme': 'light'}})
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0
        capsys.readouterr()

        assert run_main([str(other), *SKIP, '--yes', '--command-names', 'team-1', '--switch-config']) == 0

        cron_scheduler.reload()
        assert cron_scheduler.crontab_lines() == [self.OTHER_LINE]
        assert f'Removed the scheduled update job {JOB}' in _output(capsys)

    def test_scheduled_child_run_completes_and_records(
        self, e2e_isolated_home: dict[str, Path], configs: Path, cron_scheduler: FakeScheduler, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The run a cron line starts completes against the same crontab shape and leaves its record."""
        home = e2e_isolated_home['home']
        cfg = write_config(configs, 'env.yaml', _scheduled())
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0
        runner = write_child_runner(tmp_path, monkeypatch)

        child = _scheduled_child(runner, capture_output=True)

        assert child.returncode == 0, child.stdout + child.stderr
        record = _run_record(home, cron_scheduler, JOB)
        assert record is not None
        assert record['outcome'] == 'completed'
        assert record['exit_code'] == 0
        assert 'Step 24:' in Path(record['log']).read_text(encoding='utf-8', errors='replace')
        cron_scheduler.reload()
        assert len(cron_scheduler.creations()) == 1, 'the scheduled run leaves its own line alone'
        assert JOB in cron_scheduler.jobs

    def test_without_systemd_or_crontab_the_problem_reaches_the_summary_and_the_error_block(
        self, e2e_isolated_home: dict[str, Path], configs: Path, fake_scheduler: FakeScheduler,
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A Linux machine with neither scheduler installs everything else, names the problem and exits 1."""
        from tests.e2e.conftest import _shaped_scheduler

        fake = _shaped_scheduler(fake_scheduler, monkeypatch, platform_name='linux', systemd=False, crontab=False)
        cfg = write_config(configs, 'env.yaml', _scheduled())

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 1

        fake.reload()
        assert fake.creations() == []
        output = _output(capsys)
        problem = 'neither a systemd user manager nor the crontab command is available to schedule the job'
        assert '[!]' in output
        assert output.count(problem) >= 2, 'the summary before consent and Step 24 both name it'
        assert 'The scheduled update job (auto-update) was not applied:' in output
        assert f'The scheduled update job {JOB} cannot be registered: {problem}' in output
        assert (e2e_isolated_home['claude_dir'] / 'team-1' / 'agents' / 'core.md').is_file(), 'the rest of the setup ran'


GITHUB_CONFIG_URL = 'https://raw.githubusercontent.com/acme/private-configs/main/env.yaml'
GITLAB_CONFIG_URL = 'https://gitlab.example.com/acme/private-configs/-/raw/main/env.yaml'
GITLAB_BASE_URL = 'https://gitlab.example.com/acme/private-configs/-/raw/main/base.yaml'
GITLAB_HOST = 'gitlab.example.com'


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


GITHUB_HOSTS = ('raw.githubusercontent.com', 'api.github.com')


class _PrivateHosts:
    """A urlopen stand-in for private repositories, each answering only to its own credential header.

    A private GitHub file is fetched through the API host once the raw host
    answered 401, so both GitHub hosts serve the GitHub entry.
    """

    def __init__(self, hosts: dict[str, tuple[str, str, bytes]]) -> None:
        """Describe the hosts.

        Args:
            hosts: Per hostname, the header name the host checks, the value
                it accepts, and the body it serves.
        """
        self.hosts = dict(hosts)
        github = next((entry for host, entry in hosts.items() if host in GITHUB_HOSTS), None)
        if github is not None:
            for host in GITHUB_HOSTS:
                self.hosts.setdefault(host, github)
        self.requests: list[Request] = []

    def __call__(self, request: Request, *_args: Any, **_kwargs: Any) -> _Response:
        """Answer one request.

        Returns:
            The response when the credential header matches.

        Raises:
            urllib.error.HTTPError: 401 for every other request.
        """
        self.requests.append(request)
        header, accepted, body = self.hosts[str(urllib.parse.urlparse(request.full_url).hostname)]
        sent = {name.lower(): value for name, value in {**request.unredirected_hdrs, **request.headers}.items()}
        if sent.get(header.lower()) != accepted:
            raise urllib.error.HTTPError(request.full_url, 401, 'Unauthorized', email.message.Message(), None)
        return _Response(body)

    def header_values(self, header: str) -> list[str]:
        """Return every value sent for a header, across the requests.

        Returns:
            The values, in request order.
        """
        values: list[str] = []
        for request in self.requests:
            sent = {name.lower(): value for name, value in {**request.unredirected_hdrs, **request.headers}.items()}
            if header.lower() in sent:
                values.append(sent[header.lower()])
        return values


def _private_github(token: str, body: bytes) -> _PrivateHosts:
    """A private GitHub repository answering only to one bearer token."""
    return _PrivateHosts({'raw.githubusercontent.com': ('Authorization', f'Bearer {token}', body)})


def _private_gitlab(token: str, body: bytes) -> _PrivateHosts:
    """A private GitLab repository answering only to one private token."""
    return _PrivateHosts({GITLAB_HOST: ('PRIVATE-TOKEN', token, body)})


def _glab_logged_in(stubs: Path, token: str) -> None:
    """A glab stub whose status report names the stored token for the host."""
    write_cli_stub(
        stubs, 'glab',
        [
            GITLAB_HOST,
            f'  Logged in to {GITLAB_HOST} as me',
            f'  Token found in configuration file (plaintext): {token}',
        ],
        stderr=True,
    )


def _glab_not_logged_in(stubs: Path) -> None:
    """A glab stub that knows no login for the host."""
    write_cli_stub(stubs, 'glab', [f'  {GITLAB_HOST}: no token found'], stderr=True, exit_code=1)


@pytest.mark.usefixtures('e2e_isolated_home')
class TestUnattendedCredentials:
    """A private configuration is fetched with the logged-in host CLI's token when no variable applies.

    A job registered or kept for a private host warns unless the host is
    covered by a login the CLI stores or by a variable in the environment
    the scheduler hands the job; the shaped fakes answer the environment
    probes (the registry on Windows, the user manager on Linux).
    """

    @pytest.fixture
    def stubs(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        """A directory first on PATH for stub gh and glab, shadowing the machine's own."""
        directory = tmp_path / 'bin'
        directory.mkdir()
        monkeypatch.setenv('PATH', f'{directory}{os.pathsep}{os.environ.get("PATH", "")}')
        for variable in ('GITHUB_TOKEN', 'GITLAB_TOKEN', 'REPO_TOKEN', 'CLAUDE_CODE_TOOLBOX_ENV_AUTH'):
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
        private = _private_github('ghp_stub_token_value', self._private_config())

        with patch('scripts.setup_environment.urlopen', private):
            code = run_main([GITHUB_CONFIG_URL, *SKIP, '--yes', '--command-names', 'team-1'])

        assert code == 0
        assert 'Bearer ghp_stub_token_value' in private.header_values('Authorization')
        output = _output(capsys)
        assert 'Using the stored GitHub CLI (gh) login for github.com' in output
        assert 'ghp_stub_token_value' not in output
        assert 'cannot authenticate' not in output, 'the gh login covers the scheduled job too'
        _registered_document(fake_scheduler, JOB)

    def test_private_gitlab_configuration_is_fetched_with_the_glab_token(
        self, stubs: Path, e2e_isolated_home: dict[str, Path], fake_scheduler: FakeScheduler,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """GITLAB_TOKEN is absent, glab is logged in: the fetch sends glab's token as PRIVATE-TOKEN and never prints it."""
        _glab_logged_in(stubs, 'glpat-stub-token-value')
        private = _private_gitlab('glpat-stub-token-value', self._private_config())

        with patch('scripts.setup_environment.urlopen', private):
            code = run_main([GITLAB_CONFIG_URL, *SKIP, '--yes', '--command-names', 'team-1'])

        assert code == 0
        assert 'glpat-stub-token-value' in private.header_values('PRIVATE-TOKEN')
        output = _output(capsys)
        assert f'Using the stored GitLab CLI (glab) login for {GITLAB_HOST}' in output
        assert 'glpat-stub-token-value' not in output
        assert 'cannot authenticate' not in output, 'the glab login covers the scheduled job too'
        _registered_document(fake_scheduler, JOB)
        home = e2e_isolated_home['home']
        run_record = _run_record(home, fake_scheduler, JOB)
        assert run_record is None
        state_text = ''.join(
            path.read_text(encoding='utf-8', errors='replace')
            for path in _platform(home, fake_scheduler).state.rglob('*') if path.is_file()
        )
        manifest_text = (e2e_isolated_home['claude_dir'] / 'team-1' / 'manifest.json').read_text(encoding='utf-8')
        assert 'glpat-stub-token-value' not in state_text + manifest_text

    def test_job_for_a_private_configuration_warns_without_an_unattended_credential(
        self, stubs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A token passed with --env lives in this run only, and gh is not logged in: the summary and Step 24 warn."""
        write_cli_stub(stubs, 'gh', ['no oauth token found for github.com'], stderr=True, exit_code=1)
        private = _private_github('ghp_for_this_run', self._private_config())

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

    def test_job_for_a_private_gitlab_configuration_warns_when_glab_is_not_logged_in(
        self, stubs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """GITLAB_TOKEN from --env reaches this run only, glab knows no login: the warning names the glab login."""
        _glab_not_logged_in(stubs)
        private = _private_gitlab('glpat-for-this-run', self._private_config())

        with patch('scripts.setup_environment.urlopen', private):
            code = run_main([
                GITLAB_CONFIG_URL, *SKIP, '--yes', '--command-names', 'team-1', '--env', 'GITLAB_TOKEN=glpat-for-this-run',
            ])

        assert code == 0
        output = _output(capsys)
        assert f'The scheduled update job cannot authenticate to {GITLAB_HOST}' in output
        assert f'glab auth login --hostname {GITLAB_HOST}' in output
        assert 'GITLAB_TOKEN' in output
        assert 'glpat-for-this-run' not in output

    def test_masked_glab_token_is_not_used(
        self, stubs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A glab report that masks the token offers nothing: the fetch has no credential and fails without a prompt."""
        _glab_logged_in(stubs, '**************')
        private = _private_gitlab('glpat-real', self._private_config())

        with patch('scripts.setup_environment.urlopen', private):
            code = run_main([GITLAB_CONFIG_URL, *SKIP, '--yes', '--command-names', 'team-1'])

        assert code == 1
        assert private.header_values('PRIVATE-TOKEN') == [], 'the masked line is never sent as a token'
        output = _output(capsys)
        assert f'Authentication required for https://{GITLAB_HOST}/' in output
        assert f'Checked the stored CLI login too: glab auth status --hostname {GITLAB_HOST} --show-token' in output
        assert 'Using the stored GitLab CLI' not in output

    def test_public_configuration_warns_nothing(
        self, stubs: Path, configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A configuration that needed no credentials gets no credential warning."""
        write_cli_stub(stubs, 'gh', ['no oauth token found for github.com'], stderr=True, exit_code=1)
        cfg = write_config(configs, 'env.yaml', _scheduled())

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0

        assert 'cannot authenticate' not in _output(capsys)

    def test_session_token_does_not_count_as_a_job_credential(
        self, stubs: Path, windows_scheduler: FakeScheduler, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A GITHUB_TOKEN this shell exports is not in the task's environment: the warning fires and names setx."""
        write_cli_stub(stubs, 'gh', ['no oauth token found for github.com'], stderr=True, exit_code=1)
        monkeypatch.setenv('GITHUB_TOKEN', 'ghp_session_only')
        private = _private_github('ghp_session_only', self._private_config())

        with patch('scripts.setup_environment.urlopen', private):
            code = run_main([GITHUB_CONFIG_URL, *SKIP, '--yes', '--command-names', 'team-1'])

        assert code == 0
        output = _output(capsys)
        assert 'The scheduled update job cannot authenticate to github.com' in output
        assert 'setx GITHUB_TOKEN' in output
        assert 'ghp_session_only' not in output
        windows_scheduler.reload()
        assert any(call[:3] == ['reg', 'query', r'HKCU\Environment'] for call in windows_scheduler.calls)

    @pytest.mark.parametrize(
        ('fixture', 'variable'),
        [
            ('windows_scheduler', 'GITHUB_TOKEN'),
            ('windows_scheduler', 'CLAUDE_CODE_TOOLBOX_ENV_AUTH'),
            ('linux_scheduler', 'GITHUB_TOKEN'),
            ('linux_scheduler', 'CLAUDE_CODE_TOOLBOX_ENV_AUTH'),
        ],
    )
    def test_job_visible_variable_covers_the_job(
        self, stubs: Path, request: pytest.FixtureRequest, fixture: str, variable: str, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A token, or the auth override, in the environment the scheduler hands the job silences the warning."""
        fake: FakeScheduler = request.getfixturevalue(fixture)
        value = 'Authorization:Bearer ghp_persistent' if variable.endswith('ENV_AUTH') else 'ghp_persistent'
        fake.environment[variable] = value
        fake.save()
        write_cli_stub(stubs, 'gh', ['no oauth token found for github.com'], stderr=True, exit_code=1)
        monkeypatch.setenv(variable, fake.environment[variable])
        private = _private_github('ghp_persistent', self._private_config())

        with patch('scripts.setup_environment.urlopen', private):
            code = run_main([GITHUB_CONFIG_URL, *SKIP, '--yes', '--command-names', 'team-1'])

        assert code == 0
        output = _output(capsys)
        assert 'cannot authenticate' not in output
        assert 'ghp_persistent' not in output

    def test_every_private_host_of_the_configuration_is_checked(
        self, stubs: Path, windows_scheduler: FakeScheduler, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A GitHub leaf inheriting a GitLab base, only the GitHub token job-visible: the warning names GitLab alone."""
        windows_scheduler.environment['GITHUB_TOKEN'] = 'ghp_persistent'
        windows_scheduler.save()
        monkeypatch.setenv('GITHUB_TOKEN', 'ghp_persistent')
        _glab_not_logged_in(stubs)
        leaf = yaml.safe_dump(
            {'name': 'Leaf', 'inherit': GITLAB_BASE_URL, 'auto-update': {'time': '03:30'}}, sort_keys=False,
        ).encode('utf-8')
        base = yaml.safe_dump({'name': 'Base', 'user-settings': {'theme': 'dark'}}, sort_keys=False).encode('utf-8')
        private = _PrivateHosts({
            'raw.githubusercontent.com': ('Authorization', 'Bearer ghp_persistent', leaf),
            GITLAB_HOST: ('PRIVATE-TOKEN', 'glpat-for-this-run', base),
        })

        with patch('scripts.setup_environment.urlopen', private):
            code = run_main([
                GITHUB_CONFIG_URL, *SKIP, '--yes', '--command-names', 'team-1', '--env', 'GITLAB_TOKEN=glpat-for-this-run',
            ])

        assert code == 0, _output(capsys)
        assert 'glpat-for-this-run' in private.header_values('PRIVATE-TOKEN'), 'the base was fetched from GitLab'
        output = _output(capsys)
        assert f'The scheduled update job cannot authenticate to {GITLAB_HOST}' in output
        assert f'glab auth login --hostname {GITLAB_HOST}' in output
        assert 'cannot authenticate to github.com' not in output
        assert 'glpat-for-this-run' not in output
        assert 'ghp_persistent' not in output


PRIVATE_CHILD_RUNNER = '''\
"""Child runner for a scheduled run whose configuration host refuses every request."""
import email.message
import urllib.error
from unittest.mock import patch

from scripts import setup_environment
from tests.e2e.fixtures import setup_child

_real_find = setup_environment.find_command


def _find(name: str) -> str | None:
    return '/usr/bin/claude' if name == 'claude' else _real_find(name)


def _refuse(request, *_args, **_kwargs):
    raise urllib.error.HTTPError(request.full_url, 401, 'Unauthorized', email.message.Message(), None)


with (
    patch.object(setup_environment, 'find_command', _find),
    patch.object(setup_environment, 'ensure_local_bin_in_path', lambda: None),
    patch.object(setup_environment, 'refresh_path_from_registry', lambda: None),
    patch.object(setup_environment, 'urlopen', _refuse),
):
    setup_child.main()
'''


@pytest.mark.usefixtures('e2e_isolated_home')
class TestScheduledRunNeverPrompts:
    """A scheduled run owns a console on Windows, where a credential prompt would wait for a keypress nobody gives."""

    @WINDOWS_ONLY
    def test_private_configuration_without_a_credential_fails_fast_in_its_own_console(
        self, e2e_isolated_home: dict[str, Path], fake_scheduler: FakeScheduler, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """No variable, no gh login, a console of its own: the run exits 1 with the failure logged instead of waiting."""
        home = e2e_isolated_home['home']
        stubs = tmp_path / 'bin'
        stubs.mkdir()
        monkeypatch.setenv('PATH', f'{stubs}{os.pathsep}{os.environ.get("PATH", "")}')
        write_cli_stub(stubs, 'gh', ['no oauth token found for github.com'], stderr=True, exit_code=1)
        for variable in ('GITHUB_TOKEN', 'GITLAB_TOKEN', 'REPO_TOKEN', 'CLAUDE_CODE_TOOLBOX_ENV_AUTH'):
            monkeypatch.delenv(variable, raising=False)
        config = {'name': 'Private Env', 'user-settings': {'theme': 'dark'}, 'auto-update': {'time': '03:30'}}
        private = _private_github('ghp_install_only', yaml.safe_dump(config, sort_keys=False).encode('utf-8'))
        with patch('scripts.setup_environment.urlopen', private):
            assert run_main([
                GITHUB_CONFIG_URL, *SKIP, '--yes', '--command-names', 'team-1', '--env', 'GITHUB_TOKEN=ghp_install_only',
            ]) == 0
        write_child_runner(tmp_path, monkeypatch)
        runner = tmp_path / 'private_runner.py'
        runner.write_text(PRIVATE_CHILD_RUNNER, encoding='utf-8')

        child = _scheduled_child(runner, creationflags=getattr(subprocess, 'CREATE_NEW_CONSOLE', 0), timeout=300)

        assert child.returncode == 1
        record = _run_record(home, fake_scheduler, JOB)
        assert record is not None
        assert record['outcome'] == 'completed'
        assert record['exit_code'] == 1
        text = Path(record['log']).read_text(encoding='utf-8', errors='replace')
        assert 'Authentication required for https://' in text
        assert 'Checked the stored CLI login too: gh auth token --hostname github.com' in text
        assert 'Would you like to enter the token now?' not in text
        assert 'Finished: exit code 1' in text
        assert not (_platform(home, fake_scheduler).state / 'update.lock').exists(), 'the lock is released'


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
        for directory in registration.directories:
            assert directory.is_dir(), f'{directory} was not created for the job'
    finally:
        setup_environment.remove_job_registration(platform, name)
    assert setup_environment.query_job_registration(platform, name) is None
    for path in registration.files:
        if path.suffix == '.plist' or path.parent.name == 'user':
            assert not path.exists(), f'{path} was left behind'
    (tmp_path / 'state' / 'done').write_text(json.dumps({'job': name}), encoding='utf-8')
