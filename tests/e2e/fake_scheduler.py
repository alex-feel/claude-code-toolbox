"""A fake operating-system scheduler for the scheduled profile update tests.

The toolbox drives Task Scheduler, launchd, the systemd user manager and
crontab through one command runner. The fake answers every command that
runner is handed the way the real scheduler of the test machine's platform
would, keeps the registered jobs, and never reaches the real scheduler. With
a registry file the jobs and calls persist across processes, so a child run
(a dependent refresh, a scheduled run started by a test) sees the jobs the
parent registered the way it would see a real scheduler's.
"""

from __future__ import annotations

import json
import plistlib
import subprocess
from pathlib import Path

# The environment variable through which a test hands the registry file to
# every child run; it belongs to the test harness, not to the toolbox
# interface, so it sits outside the CLAUDE_CODE_TOOLBOX_ namespace
REGISTRY_VARIABLE = 'CCT_E2E_FAKE_SCHEDULER_REGISTRY'


class FakeScheduler:
    """Answers the scheduler commands of every backend and keeps the registered jobs."""

    def __init__(self, registry: Path | None = None, *, systemd: bool = True, fail_create: bool = False) -> None:
        """Load the jobs and calls earlier runs left in the registry, if any.

        Args:
            registry: The JSON file holding the fake scheduler's state, or
                None to keep it in memory.
            systemd: Whether the systemd user manager answers (Linux only).
            fail_create: Whether every registration is refused.
        """
        self.registry = registry
        self.systemd = systemd
        self.fail_create = fail_create
        loaded: dict[str, object] = {}
        if registry is not None and registry.exists():
            loaded = json.loads(registry.read_text(encoding='utf-8'))
        jobs = loaded.get('jobs', {})
        calls = loaded.get('calls', [])
        self.jobs: dict[str, str] = dict(jobs) if isinstance(jobs, dict) else {}
        self.calls: list[list[str]] = [list(call) for call in calls] if isinstance(calls, list) else []

    def __call__(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        """Answer one command and record it.

        Returns:
            The fake's answer.
        """
        self.calls.append(list(command))
        code, out = self._answer(command)
        if self.registry is not None:
            self.registry.parent.mkdir(parents=True, exist_ok=True)
            self.registry.write_text(json.dumps({'jobs': self.jobs, 'calls': self.calls}, indent=1), encoding='utf-8')
        return subprocess.CompletedProcess(command, code, out, '' if code == 0 else out)

    def reload(self) -> None:
        """Re-read the registry, so a parent sees what a child run registered."""
        if self.registry is None or not self.registry.exists():
            return
        loaded = json.loads(self.registry.read_text(encoding='utf-8'))
        self.jobs = dict(loaded.get('jobs', {}))
        self.calls = [list(call) for call in loaded.get('calls', [])]

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
        return (0, 'SUCCESS') if self.jobs.pop(name, None) is not None else missing

    def _launchd(self, command: list[str]) -> tuple[int, str]:
        if command[1] == 'bootstrap':
            if self.fail_create:
                return 5, 'Bootstrap failed: 5: Input/output error'
            document = Path(command[3]).read_bytes()
            self.jobs[plistlib.loads(document)['Label']] = document.decode('utf-8')
            return 0, ''
        name = command[2].rsplit('/', 1)[-1]
        if command[1] == 'print':
            return (0, self.jobs[name]) if name in self.jobs else (113, 'Could not find service')
        return (0, '') if self.jobs.pop(name, None) is not None else (3, 'No such process')

    def _systemd(self, command: list[str]) -> tuple[int, str]:
        if not self.systemd:
            return 1, 'Failed to connect to bus: No such file or directory'
        verb = command[2]
        if verb in {'show-environment', 'daemon-reload'}:
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
        self.jobs.pop(name, None)
        return 0, ''

    def _crontab(self, command: list[str]) -> tuple[int, str]:
        if command[1] == '-l':
            lines = [content.removeprefix('cron:') for content in self.jobs.values() if content.startswith('cron:')]
            return (0, ''.join(f'{line}\n' for line in lines)) if lines else (1, 'no crontab for user')
        content = Path(command[1]).read_text(encoding='utf-8')
        self.jobs = {key: value for key, value in self.jobs.items() if not value.startswith('cron:')}
        for line in content.splitlines():
            if line.strip():
                self.jobs[line.rsplit('# ', 1)[-1]] = f'cron:{line}'
        return 0, ''
