"""A fake operating-system scheduler for the scheduled profile update tests.

The toolbox drives Task Scheduler, launchd, the systemd user manager and
crontab through one command runner. The fake answers every command that
runner is handed the way the real scheduler of a platform would, keeps the
registered jobs, and never reaches the real scheduler. With a registry file
the jobs, the calls and the fake's shape persist across processes, so a child
run (a dependent refresh, a scheduled run started by a test) sees the jobs
the parent registered the way it would see a real scheduler's.

A fake can stand in for another platform's scheduler than the test
machine's: a Linux machine without a systemd user manager (the job is a
crontab entry), a Windows machine (Task Scheduler), a Linux machine with a
user manager. ``fake_platform()`` builds the scheduler platform of such a
fake, which a test installs in place of the toolbox's own, so every
backend's path through ``main()`` runs on every CI operating system.
"""

from __future__ import annotations

import json
import os
import plistlib
import shutil
import subprocess
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING
from typing import Any

if TYPE_CHECKING:
    from scripts.setup_environment import SchedulerPlatform

# The environment variable through which a test hands the registry file to
# every child run; it belongs to the test harness, not to the toolbox
# interface, so it sits outside the CLAUDE_CODE_TOOLBOX_ namespace
REGISTRY_VARIABLE = 'CCT_E2E_FAKE_SCHEDULER_REGISTRY'

# The path the shaped platform's lookup answers for crontab, so a Linux shape
# has the command on every CI operating system
CRONTAB_PATH = '/usr/bin/crontab'


class FakeScheduler:
    """Answers the scheduler commands of every backend and keeps the registered jobs."""

    def __init__(
        self,
        registry: Path | None = None,
        *,
        systemd: bool | None = None,
        fail_create: bool = False,
        fail_remove: bool = False,
        platform_name: str | None = None,
        crontab: bool | None = None,
        environment: dict[str, str] | None = None,
    ) -> None:
        """Load the jobs, calls and shape earlier runs left in the registry, if any.

        A registry written by an earlier process carries the shape (platform,
        systemd, crontab, environment) into this one, so a child run answers
        the way the parent test's fake does; a shape argument given here wins
        over the registry's, so a test reshapes a registry its fixture wrote.

        Args:
            registry: The JSON file holding the fake scheduler's state, or
                None to keep it in memory.
            systemd: Whether the systemd user manager answers (Linux only);
                None keeps the registry's answer, else True.
            fail_create: Whether every registration is refused.
            fail_remove: Whether every removal is refused.
            platform_name: The ``sys.platform`` value the fake stands in
                for; None keeps the registry's, else the test machine's own.
            crontab: Whether the shaped platform has the crontab command;
                None keeps the registry's answer, else True.
            environment: The variables the scheduler hands its jobs (the
                registry user environment, launchd's, the user manager's);
                None keeps the registry's, else none.
        """
        self.registry = registry
        self.fail_create = fail_create
        self.fail_remove = fail_remove
        self.systemd = True
        self.crontab = True
        self.platform_name: str | None = None
        self.environment: dict[str, str] = {}
        self.jobs: dict[str, str] = {}
        self.calls: list[list[str]] = []
        if registry is not None and registry.exists():
            self._load(json.loads(registry.read_text(encoding='utf-8')))
        if systemd is not None:
            self.systemd = systemd
        if crontab is not None:
            self.crontab = crontab
        if platform_name is not None:
            self.platform_name = platform_name
        if environment is not None:
            self.environment = dict(environment)

    def _load(self, loaded: dict[str, Any]) -> None:
        jobs = loaded.get('jobs', {})
        calls = loaded.get('calls', [])
        self.jobs = dict(jobs) if isinstance(jobs, dict) else {}
        self.calls = [list(call) for call in calls] if isinstance(calls, list) else []
        if 'systemd' in loaded:
            self.systemd = bool(loaded['systemd'])
        if 'crontab' in loaded:
            self.crontab = bool(loaded['crontab'])
        if loaded.get('platform'):
            self.platform_name = str(loaded['platform'])
        environment = loaded.get('environment')
        if isinstance(environment, dict):
            self.environment = {str(key): str(value) for key, value in environment.items()}

    def save(self) -> None:
        """Write the jobs, the calls and the shape to the registry, if there is one."""
        if self.registry is None:
            return
        self.registry.parent.mkdir(parents=True, exist_ok=True)
        state = {
            'jobs': self.jobs,
            'calls': self.calls,
            'systemd': self.systemd,
            'crontab': self.crontab,
            'platform': self.platform_name,
            'environment': self.environment,
        }
        self.registry.write_text(json.dumps(state, indent=1), encoding='utf-8')

    def __call__(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        """Answer one command and record it.

        Returns:
            The fake's answer.
        """
        self.calls.append(list(command))
        code, out = self._answer(command)
        self.save()
        return subprocess.CompletedProcess(command, code, out, '' if code == 0 else out)

    def reload(self) -> None:
        """Re-read the registry, so a parent sees what a child run registered."""
        if self.registry is None or not self.registry.exists():
            return
        self._load(json.loads(self.registry.read_text(encoding='utf-8')))

    def creations(self) -> list[list[str]]:
        """Return the calls that registered a job.

        Returns:
            The schtasks /Create, launchctl bootstrap, systemctl enable and crontab installs recorded so far.
        """
        return [
            call for call in self.calls
            if call[:2] in (['schtasks', '/Create'], ['launchctl', 'bootstrap'])
            or (call[0] == 'systemctl' and 'enable' in call)
            or (call[0] == 'crontab' and call[1] != '-l')
        ]

    def crontab_lines(self) -> list[str]:
        """Return the lines of the fake's crontab, in order.

        Returns:
            The installed crontab lines.
        """
        return [content.removeprefix('cron:') for content in self.jobs.values() if content.startswith('cron:')]

    def _answer(self, command: list[str]) -> tuple[int, str]:
        if command == ['id', '-u']:
            return 0, '501\n'
        if command[0] == 'schtasks':
            return self._task_scheduler(command)
        if command[0] == 'launchctl':
            return self._launchd(command)
        if command[0] == 'systemctl':
            return self._systemd(command)
        if command[0] == 'crontab':
            return self._crontab(command)
        if command[0] == 'reg':
            return self._registry_query(command)
        return 127, f'{command[0]}: the fake answers no such command'

    def _task_scheduler(self, command: list[str]) -> tuple[int, str]:
        verb, name = command[1], command[3]
        if verb == '/Create':
            if self.fail_create:
                return 1, 'ERROR: Access is denied.'
            self.jobs[name] = Path(command[5]).read_text(encoding='utf-16')
            return 0, f'SUCCESS: The scheduled task "{name}" has successfully been created.'
        missing = (1, 'ERROR: The system cannot find the file specified.')
        if verb == '/Query':
            return (0, f'TaskName: \\{name}\n') if name in self.jobs else missing
        if self.fail_remove:
            return 1, 'ERROR: Access is denied.'
        return (0, 'SUCCESS') if self.jobs.pop(name, None) is not None else missing

    def _launchd(self, command: list[str]) -> tuple[int, str]:
        if command[1] == 'bootstrap':
            if self.fail_create:
                return 5, 'Bootstrap failed: 5: Input/output error'
            document = Path(command[3]).read_bytes()
            self.jobs[plistlib.loads(document)['Label']] = document.decode('utf-8')
            return 0, ''
        if command[1] == 'getenv':
            return 0, f'{self.environment.get(command[2], "")}\n'
        name = command[2].rsplit('/', 1)[-1]
        if command[1] == 'print':
            return (0, self.jobs[name]) if name in self.jobs else (113, 'Could not find service')
        if self.fail_remove:
            return 1, 'Boot-out failed: 1: Operation not permitted'
        return (0, '') if self.jobs.pop(name, None) is not None else (3, 'No such process')

    def _systemd(self, command: list[str]) -> tuple[int, str]:
        if not self.systemd:
            return 1, 'Failed to connect to bus: No such file or directory'
        verb = command[2]
        if verb == 'show-environment':
            return 0, ''.join(f'{key}={value}\n' for key, value in self.environment.items())
        if verb == 'daemon-reload':
            return 0, ''
        name = next(part for part in command if part.endswith('.timer')).removesuffix('.timer')
        if verb == 'enable':
            if self.fail_create:
                return 1, 'Failed to enable unit'
            self.jobs[name] = f'{name}.timer'
            return 0, ''
        if verb == 'list-timers':
            listed = f'NEXT LEFT LAST PASSED UNIT ACTIVATES\n- - - - {name}.timer {name}.service\n'
            return 0, listed if name in self.jobs else '0 timers listed.\n'
        if self.fail_remove:
            return 1, f'Failed to disable unit: Unit file {name}.timer does not exist.'
        self.jobs.pop(name, None)
        return 0, ''

    def _crontab(self, command: list[str]) -> tuple[int, str]:
        if command[1] == '-l':
            lines = self.crontab_lines()
            return (0, ''.join(f'{line}\n' for line in lines)) if lines else (1, 'no crontab for user')
        content = Path(command[1]).read_text(encoding='utf-8')
        new_lines = [line for line in content.splitlines() if line.strip()]
        if self.fail_remove and len(new_lines) < len(self.crontab_lines()):
            return 1, 'crontab: installing new crontab: Permission denied'
        if self.fail_create and len(new_lines) > len(self.crontab_lines()):
            return 1, 'crontab: installing new crontab: Permission denied'
        self.jobs = {key: value for key, value in self.jobs.items() if not value.startswith('cron:')}
        for line in new_lines:
            self.jobs[line.rsplit('# ', 1)[-1]] = f'cron:{line}'
        return 0, ''

    def _registry_query(self, command: list[str]) -> tuple[int, str]:
        # reg query <key> /v <name>: the value line the real tool prints, or
        # the error it prints when the value does not exist
        name = command[4]
        value = self.environment.get(name)
        if value is None:
            return 1, 'ERROR: The system was unable to find the specified registry key or value.'
        return 0, f'\n{command[2]}\n    {name}    REG_SZ    {value}\n\n'


def fake_platform(fake: FakeScheduler, module: ModuleType) -> SchedulerPlatform:
    """Build the scheduler platform of a fake that stands in for another platform.

    Args:
        fake: The fake, whose ``platform_name`` names the platform.
        module: The setup_environment module to build the platform with
            (its SchedulerPlatform class, home lookup and state directory).

    Returns:
        A SchedulerPlatform named after the fake's platform, with the state
        directory that platform uses under the current home, the fake as its
        runner, and a lookup that finds crontab when the shape has it.
    """
    assert fake.platform_name is not None
    home = module.get_real_user_home()

    def which(command: str) -> str | None:
        if command == 'crontab':
            return CRONTAB_PATH if fake.crontab else None
        return shutil.which(command)

    platform: SchedulerPlatform = module.SchedulerPlatform(
        name=fake.platform_name,
        home=home,
        state=module.toolbox_state_dir(fake.platform_name, home, os.environ),
        runner=fake,
        environ=dict(os.environ),
        which=which,
    )
    return platform
