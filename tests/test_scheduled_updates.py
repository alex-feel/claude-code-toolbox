"""Unit tests for the scheduled profile update: the auto-update key and the OS job it registers.

A configuration with ``auto-update`` gives every profile installed from it one
daily OS job that re-runs the profile's setup through ``uvx cc-toolbox@latest``
(or a command the configuration names), serialized machine-wide by a lock in
the toolbox state directory, logged there, and recorded for the next manual
run's summary. The scheduler itself is faked here: every command the backends
hand to the runner is answered by an in-memory scheduler.
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import subprocess
import sys
from datetime import UTC
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch
from xml.etree import ElementTree as ET

import pytest

from scripts import setup_environment
from scripts.setup_environment import AutoUpdateSpec
from scripts.setup_environment import ScheduledUpdatePlan
from scripts.setup_environment import SchedulerError
from scripts.setup_environment import SchedulerPlatform
from tests.e2e.cli_stubs import write_cli_stub
from tests.e2e.fake_scheduler import FakeScheduler

TASK_NS = '{http://schemas.microsoft.com/windows/2004/02/mit/task}'
NOW = datetime(2026, 10, 5, 12, 0, 0, tzinfo=UTC)


def _platform(
    tmp_path: Path,
    name: str,
    scheduler: FakeScheduler,
    *,
    which: dict[str, str | None] | None = None,
    environ: dict[str, str] | None = None,
) -> SchedulerPlatform:
    """Build a scheduler platform for one OS with a fake runner and a fake PATH lookup."""
    found = {'uvx': '/opt/uv/uvx', 'uv': '/opt/uv/uv', 'crontab': '/usr/bin/crontab', **(which or {})}
    home = tmp_path / 'home'
    home.mkdir(exist_ok=True)
    return SchedulerPlatform(
        name=name,
        home=home,
        state=tmp_path / 'state',
        runner=scheduler,
        environ={'PATH': '/opt/uv:/usr/bin', **(environ or {})},
        which=lambda command: found.get(command),
    )


SPEC = AutoUpdateSpec(hour=3, minute=30, command=None)
COMMAND = ['/opt/uv/uvx', 'cc-toolbox@latest', 'setup', '--profile', 'team-1', '--yes', '--no-admin', '--scheduled-run']


class TestAutoUpdateKey:
    """The auto-update key: a daily local time and an optional command."""

    def test_known_config_key(self) -> None:
        """The key is a known top-level key."""
        assert 'auto-update' in setup_environment.KNOWN_CONFIG_KEYS

    def test_validate_accepts_time_and_optional_command(self) -> None:
        """A time and an optional command pass; the spec carries both."""
        assert setup_environment.validate_auto_update({'auto-update': {'time': '03:30'}}) == []
        assert setup_environment.validate_auto_update({'auto-update': {'time': '23:59', 'command': 'my-update'}}) == []
        spec = setup_environment.parse_auto_update({'auto-update': {'time': '03:30', 'command': 'my-update'}})
        assert spec is not None
        assert spec == AutoUpdateSpec(3, 30, 'my-update')
        assert spec.time_text == '03:30'
        assert spec.describe() == 'every day at 03:30 local time'

    def test_parse_returns_none_without_the_key(self) -> None:
        """A configuration without the key schedules nothing."""
        assert setup_environment.parse_auto_update({}) is None
        assert setup_environment.validate_auto_update({}) == []

    @pytest.mark.parametrize(
        ('value', 'fragment'),
        [
            ('03:30', 'must be a mapping'),
            ({}, 'time is required'),
            ({'time': 330}, 'HH:MM'),
            ({'time': '3:30'}, 'HH:MM'),
            ({'time': '24:00'}, 'HH:MM'),
            ({'time': '03:60'}, 'HH:MM'),
            ({'time': '03:30', 'command': ''}, 'command must be a non-empty string'),
            ({'time': '03:30', 'command': 3}, 'command must be a non-empty string'),
            ({'time': '03:30', 'weekday': 'mon'}, 'unknown key'),
        ],
    )
    def test_validate_rejects_bad_shapes(self, value: object, fragment: str) -> None:
        """Every malformed value is an error naming what is wrong."""
        errors = setup_environment.validate_auto_update({'auto-update': value})
        assert errors, value
        assert any(fragment in err for err in errors), errors


class TestStateDirAndNames:
    """Where the toolbox keeps its scheduler state, and how jobs are named."""

    def test_state_dir_per_platform(self, tmp_path: Path) -> None:
        """Windows uses LOCALAPPDATA, macOS Application Support, Linux XDG_STATE_HOME or ~/.local/state."""
        home = tmp_path / 'home'
        assert setup_environment.toolbox_state_dir('win32', home, {'LOCALAPPDATA': str(tmp_path / 'Local')}) == (
            tmp_path / 'Local' / 'cc-toolbox'
        )
        assert setup_environment.toolbox_state_dir('win32', home, {}) == home / 'AppData' / 'Local' / 'cc-toolbox'
        assert setup_environment.toolbox_state_dir('darwin', home, {}) == (
            home / 'Library' / 'Application Support' / 'cc-toolbox'
        )
        assert setup_environment.toolbox_state_dir('linux', home, {'XDG_STATE_HOME': str(tmp_path / 'xdg')}) == (
            tmp_path / 'xdg' / 'cc-toolbox'
        )
        assert setup_environment.toolbox_state_dir('linux', home, {}) == home / '.local' / 'state' / 'cc-toolbox'

    def test_job_name_per_profile(self) -> None:
        """One job per profile, the base profile included."""
        assert setup_environment.scheduled_update_job_name('team-1') == 'cc-toolbox-update-team-1'
        assert setup_environment.scheduled_update_job_name('base') == 'cc-toolbox-update-base'

    def test_default_platform_reads_the_module_runner(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """The default platform picks up a replaced runner and the state dir of the real home."""
        monkeypatch.setattr(setup_environment, 'get_real_user_home', lambda: tmp_path)
        monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'Local'))
        monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'xdg'))
        fake = FakeScheduler()
        monkeypatch.setattr(setup_environment, '_run_scheduler_command', fake)
        platform = setup_environment.default_scheduler_platform()
        assert platform.runner is fake
        assert platform.home == tmp_path
        assert platform.state == setup_environment.toolbox_state_dir(sys.platform, tmp_path, dict(os.environ))


class TestScheduledUpdateCommand:
    """The command line the OS job runs."""

    def test_uses_uvx_resolved_to_an_absolute_path(self, tmp_path: Path) -> None:
        """uvx resolved at registration, cc-toolbox@latest, the profile re-run flags and the hidden flag."""
        platform = _platform(tmp_path, 'linux', FakeScheduler())
        assert setup_environment.scheduled_update_command(platform, 'team-1') == COMMAND

    def test_base_profile_is_named_base(self, tmp_path: Path) -> None:
        """The base profile's job re-runs --profile base."""
        command = setup_environment.scheduled_update_command(_platform(tmp_path, 'linux', FakeScheduler()), 'base')
        assert command[3:5] == ['--profile', 'base']

    def test_falls_back_to_uv_tool_run(self, tmp_path: Path) -> None:
        """Without uvx the job runs uv tool run."""
        platform = _platform(tmp_path, 'linux', FakeScheduler(), which={'uvx': None})
        command = setup_environment.scheduled_update_command(platform, 'team-1')
        assert command[:4] == ['/opt/uv/uv', 'tool', 'run', 'cc-toolbox@latest']

    def test_without_uv_is_an_error(self, tmp_path: Path) -> None:
        """Neither uvx nor uv on PATH: the job cannot be registered."""
        platform = _platform(tmp_path, 'linux', FakeScheduler(), which={'uvx': None, 'uv': None})
        with pytest.raises(SchedulerError, match='uvx'):
            setup_environment.scheduled_update_command(platform, 'team-1')

    def test_windows_prefers_the_exe_beside_a_shell_shim(self, tmp_path: Path) -> None:
        """A bare-name lookup that returns a shell script is replaced by the .exe beside it."""
        shim = tmp_path / 'uvx'
        shim.write_text('#!/bin/sh\n', encoding='utf-8')
        (tmp_path / 'uvx.exe').write_bytes(b'MZ')
        platform = _platform(
            tmp_path, 'win32', FakeScheduler(), which={'uvx': str(shim)}, environ={'PATHEXT': '.COM;.EXE;.BAT;.CMD'},
        )
        assert setup_environment.resolve_scheduler_executable(platform, 'uvx') == str(tmp_path / 'uvx.exe')


class TestRenderedRegistrations:
    """What each backend writes to the scheduler."""

    def test_windows_task_xml(self) -> None:
        """Daily trigger, interactive logon with the highest privileges, catch-up, no overlap."""
        xml = setup_environment.windows_update_task_xml(COMMAND, SPEC, NOW, 'team-1')
        assert xml.startswith('<?xml version="1.0" encoding="UTF-16"?>')
        root = ET.fromstring(xml.split('\n', 1)[1])
        trigger = root.find(f'{TASK_NS}Triggers/{TASK_NS}CalendarTrigger')
        assert trigger is not None
        assert trigger.findtext(f'{TASK_NS}StartBoundary') == '2026-10-06T03:30:00', 'the slot passed today, so tomorrow'
        assert trigger.findtext(f'{TASK_NS}ScheduleByDay/{TASK_NS}DaysInterval') == '1'
        principal = root.find(f'{TASK_NS}Principals/{TASK_NS}Principal')
        assert principal is not None
        assert principal.findtext(f'{TASK_NS}LogonType') == 'InteractiveToken'
        assert principal.findtext(f'{TASK_NS}RunLevel') == 'HighestAvailable'
        settings = root.find(f'{TASK_NS}Settings')
        assert settings is not None
        assert settings.findtext(f'{TASK_NS}StartWhenAvailable') == 'true'
        assert settings.findtext(f'{TASK_NS}MultipleInstancesPolicy') == 'IgnoreNew'
        assert settings.findtext(f'{TASK_NS}RunOnlyIfNetworkAvailable') == 'true'
        action = root.find(f'{TASK_NS}Actions/{TASK_NS}Exec')
        assert action is not None
        assert action.findtext(f'{TASK_NS}Command') == '/opt/uv/uvx'
        assert action.findtext(f'{TASK_NS}Arguments') == subprocess.list2cmdline(COMMAND[1:])
        assert 'team-1' in (root.findtext(f'{TASK_NS}RegistrationInfo/{TASK_NS}Description') or '')

    def test_windows_task_xml_keeps_today_when_the_slot_is_ahead(self) -> None:
        """A registration before the slot keeps today's run."""
        xml = setup_environment.windows_update_task_xml(COMMAND, SPEC, datetime(2026, 10, 5, 1, 0, tzinfo=UTC), 'team-1')
        assert '2026-10-05T03:30:00' in xml

    def test_launchd_plist(self, tmp_path: Path) -> None:
        """Daily calendar interval, the PATH of the registering shell, logs in the state dir."""
        text = setup_environment.launchd_update_plist(
            'cc-toolbox-update-team-1', COMMAND, SPEC, '/opt/uv:/usr/bin', tmp_path / 'l.log',
        )
        plist = plistlib.loads(text.encode('utf-8'))
        assert plist['Label'] == 'cc-toolbox-update-team-1'
        assert plist['ProgramArguments'] == COMMAND
        assert plist['StartCalendarInterval'] == {'Hour': 3, 'Minute': 30}
        assert plist['EnvironmentVariables'] == {'PATH': '/opt/uv:/usr/bin'}
        assert plist['StandardOutPath'] == str(tmp_path / 'l.log')
        assert plist['RunAtLoad'] is False

    def test_systemd_units(self) -> None:
        """A oneshot service and a persistent daily timer."""
        service, timer = setup_environment.systemd_update_units(COMMAND, SPEC, '/opt/uv:/usr/bin')
        assert 'Type=oneshot' in service
        assert 'ExecStart="/opt/uv/uvx" "cc-toolbox@latest" "setup" "--profile" "team-1"' in service
        assert 'Environment="PATH=/opt/uv:/usr/bin"' in service
        assert 'OnCalendar=*-*-* 03:30:00' in timer
        assert 'Persistent=true' in timer

    def test_cron_line(self, tmp_path: Path) -> None:
        """A daily crontab entry tagged with the job name, output appended to the scheduler log."""
        line = setup_environment.cron_update_line(
            'cc-toolbox-update-team-1', COMMAND, SPEC, '/opt/uv:/usr/bin', tmp_path / 'l.log',
        )
        assert line.startswith('30 3 * * * PATH=/opt/uv:/usr/bin /opt/uv/uvx cc-toolbox@latest setup --profile team-1')
        assert line.endswith('# cc-toolbox-update-team-1')
        assert '2>&1' in line


class TestBackends:
    """Registering, querying and removing a job on every platform through the fake scheduler."""

    @pytest.mark.parametrize('name', ['win32', 'darwin', 'linux'])
    def test_register_query_remove(self, tmp_path: Path, name: str) -> None:
        """Each platform registers the job, reports it, and removes it."""
        scheduler = FakeScheduler()
        platform = _platform(tmp_path, name, scheduler)
        job = 'cc-toolbox-update-team-1'
        plan = setup_environment.plan_job_registration(platform, job, COMMAND, SPEC, NOW)
        assert setup_environment.query_job_registration(platform, job) is None
        setup_environment.apply_job_registration(platform, plan)
        assert job in scheduler.jobs
        assert setup_environment.query_job_registration(platform, job) is not None
        for path in plan.files:
            assert path.is_file(), f'{path} was written'
        setup_environment.remove_job_registration(platform, job)
        assert job not in scheduler.jobs
        assert setup_environment.query_job_registration(platform, job) is None

    def test_linux_without_systemd_uses_cron(self, tmp_path: Path) -> None:
        """Without a user manager the job is a tagged crontab line and the existing crontab survives."""
        scheduler = FakeScheduler(systemd=False)
        scheduler.jobs['other'] = 'cron:0 1 * * * echo other # other'
        platform = _platform(tmp_path, 'linux', scheduler)
        assert setup_environment.scheduler_uses_cron(platform)
        job = 'cc-toolbox-update-team-1'
        setup_environment.apply_job_registration(
            platform, setup_environment.plan_job_registration(platform, job, COMMAND, SPEC, NOW),
        )
        assert job in scheduler.jobs
        assert 'other' in scheduler.jobs
        assert setup_environment.query_job_registration(platform, job) is not None
        setup_environment.remove_job_registration(platform, job)
        assert job not in scheduler.jobs
        assert 'other' in scheduler.jobs

    def test_linux_without_systemd_or_crontab_is_a_problem(self, tmp_path: Path) -> None:
        """Neither scheduler available: the problem is named, nothing is registered."""
        platform = _platform(tmp_path, 'linux', FakeScheduler(systemd=False), which={'crontab': None})
        assert setup_environment.scheduler_problems(platform) == [
            'neither a systemd user manager nor the crontab command is available to schedule the job',
        ]
        assert setup_environment.scheduler_problems(_platform(tmp_path, 'win32', FakeScheduler())) == []

    def test_failed_scheduler_command_raises(self, tmp_path: Path) -> None:
        """A scheduler command that exits non-zero raises with its output."""
        platform = _platform(tmp_path, 'win32', FakeScheduler(fail_create=True))
        plan = setup_environment.plan_job_registration(platform, 'cc-toolbox-update-team-1', COMMAND, SPEC, NOW)
        with pytest.raises(SchedulerError, match='Access is denied'):
            setup_environment.apply_job_registration(platform, plan)

    @pytest.mark.real_scheduler
    def test_default_runner_reports_a_missing_command(self) -> None:
        """The real runner turns a missing executable into exit 127 instead of raising."""
        result = setup_environment._run_scheduler_command(['cc-toolbox-no-such-command-e2e', '--x'])
        assert result.returncode == 127


def _plan(
    tmp_path: Path,
    scheduler: FakeScheduler,
    *,
    spec: AutoUpdateSpec | None = SPEC,
    manifest: dict[str, Any] | None = None,
    linked_from: str | None = None,
    scheduled_run: bool = False,
    name: str = 'linux',
) -> tuple[ScheduledUpdatePlan, SchedulerPlatform]:
    platform = _platform(tmp_path, name, scheduler)
    plan = setup_environment.plan_scheduled_update(
        platform,
        profile_name='team-1',
        spec=spec,
        linked_from=linked_from,
        manifest=manifest,
        scheduled_run=scheduled_run,
    )
    return plan, platform


def _registered(
    tmp_path: Path, scheduler: FakeScheduler, name: str = 'linux',
) -> tuple[ScheduledUpdatePlan, SchedulerPlatform]:
    """Register the default job with the fake scheduler and return its plan and platform."""
    plan, platform = _plan(tmp_path, scheduler, name=name)
    assert setup_environment.apply_scheduled_update(platform, plan, now=NOW) is None
    return plan, platform


class TestPlanScheduledUpdate:
    """What a run decides to do with the profile's job, before consent."""

    def test_new_job_is_registered(self, tmp_path: Path) -> None:
        """No job yet: register with the resolved command."""
        plan, _ = _plan(tmp_path, FakeScheduler())
        assert plan.action == 'register'
        assert plan.name == 'cc-toolbox-update-team-1'
        assert plan.command == COMMAND
        assert plan.changes_registration

    def test_registered_identical_job_is_unchanged(self, tmp_path: Path) -> None:
        """A registered job with the same time and command is left alone."""
        scheduler = FakeScheduler()
        _registered(tmp_path, scheduler)
        again, _ = _plan(tmp_path, scheduler)
        assert again.action == 'unchanged'
        assert not again.changes_registration

    def test_changed_time_updates(self, tmp_path: Path) -> None:
        """A different time re-registers the job and names the change."""
        scheduler = FakeScheduler()
        _registered(tmp_path, scheduler)
        later, _ = _plan(tmp_path, scheduler, spec=AutoUpdateSpec(4, 0, None))
        assert later.action == 'update'
        assert '03:30' in later.reason
        assert '04:00' in later.reason

    def test_changed_custom_command_updates(self, tmp_path: Path) -> None:
        """A different command re-registers the job even though the OS command line is the same wrapper."""
        scheduler = FakeScheduler()
        _registered(tmp_path, scheduler)
        later, _ = _plan(tmp_path, scheduler, spec=AutoUpdateSpec(3, 30, 'my-update'))
        assert later.action == 'update'
        assert 'command' in later.reason

    def test_registered_job_without_record_is_re_registered(self, tmp_path: Path) -> None:
        """A job the scheduler holds but the state dir does not remember is re-registered."""
        scheduler = FakeScheduler()
        plan, platform = _registered(tmp_path, scheduler)
        setup_environment.job_record_path(platform, plan.name).unlink()
        again, _ = _plan(tmp_path, scheduler)
        assert again.action == 'update'

    def test_key_removed_removes_a_recorded_job(self, tmp_path: Path) -> None:
        """The manifest records a job and the configuration no longer declares the key."""
        manifest = {'auto_update': {'time': '03:30', 'command': None, 'job': 'cc-toolbox-update-team-1'}}
        plan, _ = _plan(tmp_path, FakeScheduler(), spec=None, manifest=manifest)
        assert plan.action == 'remove'
        assert 'no auto-update' in plan.reason

    def test_key_removed_removes_a_registered_job_without_a_manifest_record(self, tmp_path: Path) -> None:
        """A job the scheduler still holds is removed when the state dir remembers it."""
        scheduler = FakeScheduler()
        _registered(tmp_path, scheduler)
        later, _ = _plan(tmp_path, scheduler, spec=None, manifest=None)
        assert later.action == 'remove'

    def test_nothing_to_do_without_key_or_job(self, tmp_path: Path) -> None:
        """No key, no record, no job: the step has nothing to do and never queries the scheduler."""
        scheduler = FakeScheduler()
        plan, _ = _plan(tmp_path, scheduler, spec=None)
        assert plan.action == 'none'
        assert scheduler.calls == []

    def test_linked_profile_gets_no_job(self, tmp_path: Path) -> None:
        """A profile that links content from a source is refreshed by the source's job."""
        plan, _ = _plan(tmp_path, FakeScheduler(), linked_from='team-0')
        assert plan.action == 'none'
        assert 'links content' in plan.reason

    def test_linked_profile_drops_a_leftover_job(self, tmp_path: Path) -> None:
        """A profile converted to a linked one loses the job it had as a full copy."""
        scheduler = FakeScheduler()
        _registered(tmp_path, scheduler)
        later, _ = _plan(tmp_path, scheduler, linked_from='team-0')
        assert later.action == 'remove'
        assert 'links content' in later.reason

    def test_scheduled_run_leaves_its_own_changed_job_alone(self, tmp_path: Path) -> None:
        """The job that is running now is never replaced from inside it; the change is deferred."""
        scheduler = FakeScheduler()
        _registered(tmp_path, scheduler)
        later, _ = _plan(tmp_path, scheduler, spec=AutoUpdateSpec(4, 0, None), scheduled_run=True)
        assert later.action == 'deferred'
        assert not later.changes_registration

    def test_scheduler_problem_is_carried(self, tmp_path: Path) -> None:
        """A Linux box with neither systemd nor crontab carries the problem into the plan."""
        platform = _platform(tmp_path, 'linux', FakeScheduler(systemd=False), which={'crontab': None})
        plan = setup_environment.plan_scheduled_update(
            platform, profile_name='team-1', spec=SPEC, linked_from=None, manifest=None, scheduled_run=False,
        )
        assert plan.action == 'register'
        assert plan.problems


class TestApplyScheduledUpdate:
    """Step 24: applying the plan."""

    def test_register_writes_the_job_record(self, tmp_path: Path) -> None:
        """Registration records time, command and the OS command line in the state dir."""
        plan, platform = _registered(tmp_path, FakeScheduler())
        record = setup_environment.read_job_record(platform, plan.name)
        assert record == {'time': '03:30', 'command': None, 'os_command': COMMAND}

    def test_remove_deletes_the_record(self, tmp_path: Path) -> None:
        """Removal deletes the job and its record."""
        scheduler = FakeScheduler()
        plan, platform = _registered(tmp_path, scheduler)
        removal, _ = _plan(tmp_path, scheduler, spec=None)
        assert setup_environment.apply_scheduled_update(platform, removal, now=NOW) is None
        assert setup_environment.read_job_record(platform, plan.name) is None
        assert plan.name not in scheduler.jobs

    def test_failed_registration_returns_the_failure(self, tmp_path: Path) -> None:
        """A scheduler refusal is returned as the step's failure and nothing is recorded."""
        plan, platform = _plan(tmp_path, FakeScheduler(fail_create=True), name='win32')
        failure = setup_environment.apply_scheduled_update(platform, plan, now=NOW)
        assert failure is not None
        assert 'Access is denied' in failure
        assert setup_environment.read_job_record(platform, plan.name) is None

    def test_windows_non_elevated_registration_fails_with_the_remedy(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Under --no-admin in a non-elevated process the registration is reported failed, with the remedy."""
        scheduler = FakeScheduler()
        plan, platform = _plan(tmp_path, scheduler, name='win32')
        monkeypatch.setattr(setup_environment, '_scheduler_registration_needs_elevation', lambda: True)
        failure = setup_environment.apply_scheduled_update(platform, plan, now=NOW)
        assert failure is not None
        assert 'elevated' in failure
        assert '--no-admin' in failure
        assert all(call[:2] != ['schtasks', '/Create'] for call in scheduler.calls), 'nothing was registered'

    def test_unchanged_touches_nothing(self, tmp_path: Path) -> None:
        """An unchanged job runs no scheduler command."""
        scheduler = FakeScheduler()
        _, platform = _registered(tmp_path, scheduler)
        again, _ = _plan(tmp_path, scheduler)
        before = len(scheduler.calls)
        assert setup_environment.apply_scheduled_update(platform, again, now=NOW) is None
        assert len(scheduler.calls) == before


class TestElevationReason:
    """Windows registration of a highest-privilege task needs an elevated setup run."""

    def _args(self, **overrides: Any) -> argparse.Namespace:
        values: dict[str, Any] = {'skip_install': True, 'no_admin': False, 'dry_run': False}
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_key_adds_the_reason_on_windows(self) -> None:
        """A configuration with auto-update lists the job registration among the reasons."""
        with patch.object(setup_environment.platform, 'system', return_value='Windows'):
            reasons = setup_environment.admin_elevation_reasons({'auto-update': {'time': '03:30'}}, self._args())
        assert reasons == [setup_environment.SCHEDULED_UPDATE_ELEVATION_REASON]

    def test_plan_without_a_registration_change_adds_no_reason(self, tmp_path: Path) -> None:
        """An unchanged job needs no elevation, so a run with the plan lists none."""
        scheduler = FakeScheduler()
        plan, _ = _registered(tmp_path, scheduler, name='win32')
        unchanged, _ = _plan(tmp_path, scheduler, name='win32')
        with patch.object(setup_environment.platform, 'system', return_value='Windows'):
            reasons = setup_environment.admin_elevation_reasons(
                {'auto-update': {'time': '03:30'}}, self._args(), scheduled_update=unchanged,
            )
            with_change = setup_environment.admin_elevation_reasons(
                {'auto-update': {'time': '03:30'}}, self._args(), scheduled_update=plan,
            )
        assert reasons == []
        assert with_change == [setup_environment.SCHEDULED_UPDATE_ELEVATION_REASON]

    def test_no_reason_off_windows(self) -> None:
        """Only Windows registers with privileges."""
        with patch.object(setup_environment.platform, 'system', return_value='Linux'):
            assert setup_environment.admin_elevation_reasons({'auto-update': {'time': '03:30'}}, self._args()) == []


class TestUpdateLock:
    """Jobs never overlap on one machine."""

    def test_acquire_and_release(self, tmp_path: Path) -> None:
        """A free lock is taken and holds the pid; releasing removes it."""
        lock = tmp_path / 'state' / 'update.lock'
        assert setup_environment.acquire_update_lock(lock, wait_seconds=0, poll_seconds=1, stale_seconds=3600)
        assert lock.read_text(encoding='utf-8').strip() == str(os.getpid())
        setup_environment.release_update_lock(lock)
        assert not lock.exists()

    def test_held_lock_is_waited_for_then_given_up(self, tmp_path: Path) -> None:
        """A held lock is polled for the bounded time, then the run gives up."""
        lock = tmp_path / 'update.lock'
        lock.write_text('1\n', encoding='utf-8')
        slept: list[float] = []
        clock = [1000.0]

        def _sleep(seconds: float) -> None:
            slept.append(seconds)
            clock[0] += seconds

        taken = setup_environment.acquire_update_lock(
            lock, wait_seconds=60, poll_seconds=15, stale_seconds=3600, sleep=_sleep, clock=lambda: clock[0],
        )
        assert not taken
        assert slept == [15.0, 15.0, 15.0, 15.0]
        assert lock.exists()

    def test_lock_released_while_waiting_is_taken(self, tmp_path: Path) -> None:
        """A run waiting for the lock takes it once the holder releases it."""
        lock = tmp_path / 'update.lock'
        lock.write_text('1\n', encoding='utf-8')
        polls = 0

        def _sleep(_seconds: float) -> None:
            nonlocal polls
            polls += 1
            if polls == 2:
                lock.unlink()

        assert setup_environment.acquire_update_lock(
            lock, wait_seconds=600, poll_seconds=15, stale_seconds=3600, sleep=_sleep,
        )
        assert polls == 2

    def test_stale_lock_is_replaced(self, tmp_path: Path) -> None:
        """A lock older than the stale threshold belongs to a dead run and is taken over."""
        lock = tmp_path / 'update.lock'
        lock.write_text('1\n', encoding='utf-8')
        old = lock.stat().st_mtime - 7200
        os.utime(lock, (old, old))
        assert setup_environment.acquire_update_lock(lock, wait_seconds=0, poll_seconds=1, stale_seconds=3600)
        assert lock.read_text(encoding='utf-8').strip() == str(os.getpid())


class TestLogsAndRecords:
    """Logs are kept to the last 30; the run record feeds the next summary."""

    def test_prune_keeps_the_newest_logs(self, tmp_path: Path) -> None:
        """Only the newest 30 logs of the job survive; other jobs' logs are untouched."""
        logs = tmp_path / 'logs'
        logs.mkdir()
        for index in range(35):
            (logs / f'cc-toolbox-update-team-1-202610{index:02d}-000000.log').write_text('x', encoding='utf-8')
        (logs / 'cc-toolbox-update-base-20261001-000000.log').write_text('x', encoding='utf-8')
        setup_environment.prune_scheduled_update_logs(logs, 'cc-toolbox-update-team-1', keep=30)
        remaining = sorted(path.name for path in logs.glob('cc-toolbox-update-team-1-*.log'))
        assert len(remaining) == 30
        assert remaining[0] == 'cc-toolbox-update-team-1-20261005-000000.log'
        assert (logs / 'cc-toolbox-update-base-20261001-000000.log').exists()

    def test_run_record_round_trip_and_summary_line(self, tmp_path: Path) -> None:
        """The record is written as JSON and rendered for the summary."""
        platform = _platform(tmp_path, 'linux', FakeScheduler())
        log_path = tmp_path / 'state' / 'logs' / 'x.log'
        record = {
            'profile': 'team-1', 'job': 'cc-toolbox-update-team-1', 'started_at': '2026-10-05T03:30:00+03:00',
            'finished_at': '2026-10-05T03:32:10+03:00', 'exit_code': 0, 'outcome': 'completed', 'reason': None,
            'log': str(log_path), 'command': 'setup --profile team-1',
        }
        setup_environment.write_scheduled_run_record(platform, 'cc-toolbox-update-team-1', record)
        assert setup_environment.read_scheduled_run_record(platform, 'cc-toolbox-update-team-1') == record
        line = setup_environment.last_scheduled_run_line(platform, 'cc-toolbox-update-team-1')
        assert line == f'Last scheduled run: 2026-10-05 03:30 (local), exit code 0, log {log_path}'
        skipped = {**record, 'outcome': 'skipped', 'exit_code': 1, 'reason': 'another scheduled run held the lock'}
        setup_environment.write_scheduled_run_record(platform, 'cc-toolbox-update-team-1', skipped)
        assert setup_environment.last_scheduled_run_line(platform, 'cc-toolbox-update-team-1') == (
            f'Last scheduled run: 2026-10-05 03:30 (local), skipped: another scheduled run held the lock, log {log_path}'
        )
        assert setup_environment.last_scheduled_run_line(platform, 'cc-toolbox-update-other') is None


def _scheduled_args(**overrides: Any) -> argparse.Namespace:
    values: dict[str, Any] = {'profile': 'team-1', 'scheduled_run': True, 'yes': True, 'no_admin': True}
    values.update(overrides)
    return argparse.Namespace(**values)


class TestRunScheduledUpdate:
    """The harness a scheduled run goes through: lock, log, the command, the record."""

    @pytest.fixture(autouse=True)
    def _no_output_redirect(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Keep the test process's own output where pytest captures it."""
        monkeypatch.setattr(setup_environment, '_redirect_output_to', lambda _path: None)

    def test_default_runs_the_setup_and_records_its_exit_code(self, tmp_path: Path) -> None:
        """The setup callable runs under the lock; its SystemExit code becomes the run's exit code."""
        platform = _platform(tmp_path, 'linux', FakeScheduler())
        calls: list[str] = []

        def _setup() -> None:
            calls.append('ran')
            assert (platform.state / 'update.lock').exists(), 'the lock is held while the setup runs'
            raise SystemExit(0)

        code = setup_environment.run_scheduled_update(_scheduled_args(), _setup, platform_=platform, custom_command=None)
        assert code == 0
        assert calls == ['ran']
        record = setup_environment.read_scheduled_run_record(platform, 'cc-toolbox-update-team-1')
        assert record is not None
        assert record['exit_code'] == 0
        assert record['outcome'] == 'completed'
        assert record['profile'] == 'team-1'
        log = Path(record['log'])
        assert log.is_file()
        assert log.parent == platform.state / 'logs'
        assert 'profile team-1' in log.read_text(encoding='utf-8')
        assert not (platform.state / 'update.lock').exists(), 'the lock is released'

    def test_failed_setup_exit_code_is_recorded(self, tmp_path: Path) -> None:
        """A setup that exits 1 is recorded as exit 1 and the harness returns it."""
        platform = _platform(tmp_path, 'linux', FakeScheduler())

        def _setup() -> None:
            raise SystemExit(1)

        assert setup_environment.run_scheduled_update(_scheduled_args(), _setup, platform_=platform, custom_command=None) == 1
        record = setup_environment.read_scheduled_run_record(platform, 'cc-toolbox-update-team-1')
        assert record is not None
        assert record['exit_code'] == 1

    def test_custom_command_runs_instead_of_the_setup(self, tmp_path: Path) -> None:
        """A configured command runs in the shell, its output lands in the log, the setup never runs."""
        platform = _platform(tmp_path, 'linux', FakeScheduler())
        marker = tmp_path / 'marker.txt'
        script = f"import pathlib; pathlib.Path(r'{marker}').write_text('ran'); print('custom ran')"
        command = f'"{sys.executable}" -c "{script}"'

        def _setup() -> None:
            raise AssertionError('the setup must not run for a custom command')

        code = setup_environment.run_scheduled_update(_scheduled_args(), _setup, platform_=platform, custom_command=command)
        assert code == 0
        assert marker.read_text() == 'ran'
        record = setup_environment.read_scheduled_run_record(platform, 'cc-toolbox-update-team-1')
        assert record is not None
        assert record['command'] == command
        assert 'custom ran' in Path(record['log']).read_text(encoding='utf-8')

    def test_held_lock_skips_with_a_logged_reason(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Another scheduled run holds the lock past the wait: the run logs why and exits 1."""
        platform = _platform(tmp_path, 'linux', FakeScheduler())
        lock = platform.state / 'update.lock'
        lock.parent.mkdir(parents=True)
        lock.write_text('4242\n', encoding='utf-8')
        monkeypatch.setattr(setup_environment, 'SCHEDULED_UPDATE_LOCK_WAIT_SECONDS', 0)

        def _setup() -> None:
            raise AssertionError('the setup must not run while the lock is held')

        code = setup_environment.run_scheduled_update(_scheduled_args(), _setup, platform_=platform, custom_command=None)
        assert code == 1
        record = setup_environment.read_scheduled_run_record(platform, 'cc-toolbox-update-team-1')
        assert record is not None
        assert record['outcome'] == 'skipped'
        assert 'lock' in str(record['reason'])
        assert 'Skipped' in Path(record['log']).read_text(encoding='utf-8')
        assert lock.read_text(encoding='utf-8').strip() == '4242', 'the holder keeps its lock'

    def test_logs_are_pruned_after_the_run(self, tmp_path: Path) -> None:
        """The run leaves at most 30 logs for its job."""
        platform = _platform(tmp_path, 'linux', FakeScheduler())
        logs = platform.state / 'logs'
        logs.mkdir(parents=True)
        for index in range(32):
            (logs / f'cc-toolbox-update-team-1-202609{index:02d}-000000.log').write_text('x', encoding='utf-8')

        def _setup() -> None:
            raise SystemExit(0)

        setup_environment.run_scheduled_update(_scheduled_args(), _setup, platform_=platform, custom_command=None)
        assert len(list(logs.glob('cc-toolbox-update-team-1-*.log'))) == 30


@pytest.fixture
def stubs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A directory first on PATH for stub gh and glab executables, with the token cache cleared."""
    directory = tmp_path / 'bin'
    directory.mkdir()
    # Only the stub directory is on PATH, so the machine's own gh and glab are never asked
    monkeypatch.setenv('PATH', str(directory))
    monkeypatch.setattr(setup_environment, '_CLI_TOKEN_CACHE', {})
    for variable in ('GITHUB_TOKEN', 'GITLAB_TOKEN', 'REPO_TOKEN'):
        monkeypatch.delenv(variable, raising=False)
    return directory


GITHUB_URL = 'https://raw.githubusercontent.com/acme/private/main/config.yaml'
GITLAB_URL = 'https://gitlab.example.com/acme/private/-/raw/main/config.yaml'


class TestCliStoredCredentials:
    """Unattended runs take the token of the logged-in gh or glab when no variable applies."""

    def test_github_token_from_gh(self, stubs: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """gh auth token --hostname github.com supplies the bearer token; it is never printed."""
        write_cli_stub(stubs, 'gh', ['ghp_stub_token_value'])
        headers = setup_environment.resolve_credentials(GITHUB_URL)
        assert headers == {'Authorization': 'Bearer ghp_stub_token_value'}
        assert 'ghp_stub_token_value' not in capsys.readouterr().out

    def test_gitlab_token_from_glab_status(self, stubs: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """glab auth status --show-token prints the token on its status line, which the lookup parses."""
        write_cli_stub(
            stubs, 'glab',
            [
                'gitlab.example.com',
                '  Logged in to gitlab.example.com as me',
                '  Token found in configuration file (plaintext): glpat-stub-value',
            ],
            stderr=True,
        )
        headers = setup_environment.resolve_credentials(GITLAB_URL)
        assert headers == {'PRIVATE-TOKEN': 'glpat-stub-value'}
        assert 'glpat-stub-value' not in capsys.readouterr().out

    def test_masked_glab_token_is_not_a_token(self, stubs: Path) -> None:
        """A masked status line (no --show-token effect) yields nothing."""
        write_cli_stub(stubs, 'glab', ['  Token found in configuration file (plaintext): **************'], stderr=True)
        assert setup_environment.resolve_credentials(GITLAB_URL) == {}

    def test_environment_variable_wins_over_the_cli(self, stubs: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """GITHUB_TOKEN is used before gh is asked."""
        write_cli_stub(stubs, 'gh', ['ghp_from_cli'])
        monkeypatch.setenv('GITHUB_TOKEN', 'ghp_from_env')
        assert setup_environment.resolve_credentials(GITHUB_URL) == {'Authorization': 'Bearer ghp_from_env'}

    def test_failing_cli_yields_nothing(self, stubs: Path) -> None:
        """gh without a login for the host exits 1: no credentials, no exception."""
        write_cli_stub(stubs, 'gh', ['no oauth token found for github.com'], stderr=True, exit_code=1)
        assert setup_environment.resolve_credentials(GITHUB_URL) == {}
        assert setup_environment.cli_stored_token('github', 'github.com') is None

    @pytest.mark.usefixtures('stubs')
    def test_missing_cli_yields_nothing(self) -> None:
        """Neither gh on PATH nor a variable: empty, and the lookup is cached."""
        assert setup_environment.resolve_credentials(GITHUB_URL) == {}
        assert setup_environment._CLI_TOKEN_CACHE == {('github', 'github.com'): None}

    def test_cli_result_is_cached_per_host(self, stubs: Path) -> None:
        """The CLI is asked once per host."""
        write_cli_stub(stubs, 'gh', ['ghp_stub'])
        setup_environment.resolve_credentials(GITHUB_URL)
        (stubs / ('gh.cmd' if sys.platform == 'win32' else 'gh')).unlink()
        assert setup_environment.resolve_credentials(GITHUB_URL) == {'Authorization': 'Bearer ghp_stub'}

    def test_credential_host_normalizes_the_github_family(self) -> None:
        """Every GitHub host asks gh for github.com; a GitLab host is asked by name."""
        assert setup_environment._credential_host(GITHUB_URL) == 'github.com'
        assert setup_environment._credential_host('https://api.github.com/repos/a/b/contents/x') == 'github.com'
        assert setup_environment._credential_host(GITLAB_URL) == 'gitlab.example.com'
        assert setup_environment._credential_host('https://example.org/x.yaml') is None

    @pytest.mark.usefixtures('stubs')
    def test_prompt_names_the_cli_as_checked(self, capsys: pytest.CaptureFixture[str]) -> None:
        """The interactive prompt stays last and tells what was checked before it."""
        with patch('sys.stdin.isatty', return_value=False):
            assert setup_environment.get_auth_headers(GITHUB_URL) == {}
        out = capsys.readouterr().out
        assert 'GITHUB_TOKEN' in out
        assert 'gh auth token' in out


class TestUnattendedCredentialWarning:
    """Registering a job for a private configuration warns when no unattended source covers its host."""

    @pytest.fixture(autouse=True)
    def _private_host(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(setup_environment, '_AUTHENTICATED_HOSTS', {'github.com'})

    @pytest.mark.usefixtures('stubs')
    def test_warns_when_neither_source_covers_the_host(self) -> None:
        """No variable, no gh login: the warning names the host and both remedies."""
        warning_text = setup_environment.unattended_credential_warning(GITHUB_URL, env_vars_from_cli=[])
        assert warning_text is not None
        assert 'github.com' in warning_text
        assert 'GITHUB_TOKEN' in warning_text
        assert 'gh auth login' in warning_text

    @pytest.mark.usefixtures('stubs')
    def test_token_passed_with_env_flag_does_not_count(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """--env GITHUB_TOKEN=... lives in this run only, so the job still lacks credentials."""
        monkeypatch.setenv('GITHUB_TOKEN', 'ghp_x')
        assert setup_environment.unattended_credential_warning(GITHUB_URL, env_vars_from_cli=['GITHUB_TOKEN']) is not None
        assert setup_environment.unattended_credential_warning(GITHUB_URL, env_vars_from_cli=[]) is None

    def test_gh_login_covers_the_host(self, stubs: Path) -> None:
        """A logged-in gh means the job can authenticate."""
        write_cli_stub(stubs, 'gh', ['ghp_stub'])
        assert setup_environment.unattended_credential_warning(GITHUB_URL, env_vars_from_cli=[]) is None

    @pytest.mark.usefixtures('stubs')
    def test_public_or_local_configuration_warns_nothing(self) -> None:
        """A host that needed no authentication this run, or a local file, is not private."""
        public = 'https://raw.githubusercontent.com/acme/pub/main/c.yaml'
        setup_environment._AUTHENTICATED_HOSTS.clear()
        assert setup_environment.unattended_credential_warning(public, env_vars_from_cli=[]) is None
        assert setup_environment.unattended_credential_warning(GITHUB_URL, env_vars_from_cli=[]) is None
        assert setup_environment.unattended_credential_warning('/home/me/config.yaml', env_vars_from_cli=[]) is None

    @pytest.mark.usefixtures('stubs')
    def test_get_auth_headers_records_the_authenticated_host(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Resolving credentials for a URL marks its host as private for the rest of the run."""
        setup_environment._AUTHENTICATED_HOSTS.clear()
        monkeypatch.setenv('GITLAB_TOKEN', 'glpat-x')
        assert setup_environment.get_auth_headers(GITLAB_URL) == {'PRIVATE-TOKEN': 'glpat-x'}
        assert 'gitlab.example.com' in setup_environment._AUTHENTICATED_HOSTS
        assert len(setup_environment._AUTHENTICATED_HOSTS) == 1


class TestManifestRecord:
    """What the manifest records about the job."""

    def test_record_shape(self) -> None:
        """Time, command and job name; None without a job."""
        record = setup_environment.auto_update_manifest_record(SPEC, 'cc-toolbox-update-team-1')
        assert record == {'time': '03:30', 'command': None, 'job': 'cc-toolbox-update-team-1'}
        assert setup_environment.auto_update_manifest_record(None, 'cc-toolbox-update-team-1') is None

    def test_write_manifest_records_the_job(self, tmp_path: Path) -> None:
        """write_manifest stores the auto_update field."""
        real_write = setup_environment.write_manifest
        assert real_write(
            config_base_dir=tmp_path, command_name='team-1', config_version=None, config_source='x.yaml',
            config_source_type='repo', config_source_url=None, command_names=['team-1'], claude_code_version=None,
            auto_update={'time': '03:30', 'command': None, 'job': 'cc-toolbox-update-team-1'},
        )
        data = json.loads((tmp_path / 'manifest.json').read_text(encoding='utf-8'))
        assert data['auto_update'] == {'time': '03:30', 'command': None, 'job': 'cc-toolbox-update-team-1'}


class TestResidue:
    """Switching to a configuration without the key removes the job."""

    def test_residue_lists_and_removes_the_job(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """The recorded job is residue when the new configuration declares no auto-update."""
        scheduler = FakeScheduler()
        plan, platform = _registered(tmp_path, scheduler)
        monkeypatch.setattr(setup_environment, 'default_scheduler_platform', lambda: platform)
        manifest = {
            'auto_update': {'time': '03:30', 'command': None, 'job': plan.name},
            'files_written': [], 'mcp_servers': [], 'os_env_written': [], 'settings_keys_written': [],
            'machine_wide_destinations': [],
        }
        monkeypatch.setattr(setup_environment, 'installed_profiles', lambda *_a, **_kw: [])
        profile_dir = tmp_path / 'home' / '.claude' / 'team-1'
        claude_dir = tmp_path / 'home' / '.claude'
        residue = setup_environment.profile_residue(
            manifest, profile_dir, {'name': 'x'},
            isolated=True, config_source='x.yaml', base_url=None, claude_dir=claude_dir,
        )
        assert residue.scheduled_job == plan.name
        assert bool(residue)
        assert f'scheduled update job: {plan.name}' in residue.lines()
        kept = setup_environment.profile_residue(
            manifest, profile_dir, {'name': 'x', 'auto-update': {'time': '04:00'}},
            isolated=True, config_source='x.yaml', base_url=None, claude_dir=claude_dir,
        )
        assert kept.scheduled_job is None
        setup_environment.remove_profile_residue(residue, profile_dir=profile_dir, claude_dir=claude_dir)
        assert plan.name not in scheduler.jobs
        assert setup_environment.read_job_record(platform, plan.name) is None
