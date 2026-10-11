"""A recorder standing in for the uv sync that prepares hook environments.

Step 19 of the setup runs ``uv sync --script`` for every wired PEP 723 hook
through one runner, ``_run_hook_environment_sync()``. The recorder takes the
runner's place: it appends what each call would have run to a JSON-lines
file and answers like a successful sync, so the E2E tests see the exact
command, working directory and uv settings of every sync without reaching
the network or the machine's uv cache. With the file named in
RECORDER_VARIABLE, a child run (a ``--profile all`` child, a dependent
refresh, a source refresh) records into the same file as the parent test.

A test makes the sync of chosen hooks fail by naming their basenames in
FAILING_VARIABLE, comma-separated; the recorder then answers exit code 2 and
one error line on stderr, the way uv reports an unsatisfiable dependency.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

# The environment variable through which a test hands the record file to every
# child run; it belongs to the test harness, not to the toolbox interface, so it
# sits outside the CLAUDE_CODE_TOOLBOX_ namespace
RECORDER_VARIABLE = 'CCT_E2E_HOOK_SYNC_RECORD'

# Comma-separated hook basenames whose sync the recorder answers as failed
FAILING_VARIABLE = 'CCT_E2E_HOOK_SYNC_FAIL'

FAILED_SYNC_EXIT_CODE = 2
FAILED_SYNC_STDERR = 'error: No solution found when resolving script dependencies'

# The variables whose values the record keeps: uv's own settings decide which
# environment a sync builds. Every other variable is recorded by name only,
# because the machine's environment holds credentials
_RECORDED_VALUE_PREFIX = 'UV_'


class HookSyncRecorder:
    """Records every hook environment sync instead of running uv."""

    def __init__(self, path: Path) -> None:
        """Bind the recorder to its JSON-lines file.

        Args:
            path: The record file; created on the first call.
        """
        self.path = path

    def __call__(self, command: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        """Record one sync and answer as uv would.

        Args:
            command: The ``uv sync --script`` argument vector.
            cwd: The working directory the sync runs in.
            env: The environment the sync runs in.

        Returns:
            A completed process: exit code 0, or FAILED_SYNC_EXIT_CODE with
            FAILED_SYNC_STDERR for a hook FAILING_VARIABLE names.
        """
        record = {
            'command': list(command),
            'cwd': str(cwd),
            'uv_env': {name: value for name, value in env.items() if name.startswith(_RECORDED_VALUE_PREFIX)},
            'other_env_names': sorted(name for name in env if not name.startswith(_RECORDED_VALUE_PREFIX)),
        }
        with self.path.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(record) + '\n')
        failing = {name.strip() for name in os.environ.get(FAILING_VARIABLE, '').split(',') if name.strip()}
        script = Path(command[3]).name if len(command) > 3 else ''
        if script in failing:
            return subprocess.CompletedProcess(command, FAILED_SYNC_EXIT_CODE, stdout='', stderr=FAILED_SYNC_STDERR)
        return subprocess.CompletedProcess(command, 0, stdout='', stderr='')

    def records(self) -> list[dict[str, Any]]:
        """Read every recorded sync, in call order, children's included.

        Returns:
            One dict per sync with ``command``, ``cwd``, ``uv_env`` and
            ``other_env_names``; empty when nothing was recorded.
        """
        if not self.path.is_file():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding='utf-8').splitlines() if line.strip()]

    def clear(self) -> None:
        """Forget every recorded sync, so a test can assert on the next run alone."""
        self.path.unlink(missing_ok=True)
