"""Package-smoke probe: the setup's Step 1 launches the wheel's own installer.

Run inside the uvx environment built from the wheel::

    uvx --from dist/<wheel> python tests/fixtures/packaging_smoke_step1.py

It calls install_claude() with run_command() replaced by a recorder that
appends ``--help`` before executing the recorded argv, so the launch
mechanism runs against the cache-resident sibling installer without
installing anything. The probe fails unless the argv is exactly
``[sys.executable, <sibling install_claude.py>]`` and that launch succeeds.
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from cc_toolbox import setup_environment


def main() -> int:
    """Exercise install_claude() and return the process exit code."""
    recorded: list[list[str]] = []

    def run_recorded(cmd: list[str], capture_output: bool = True, **kwargs: object) -> subprocess.CompletedProcess[str]:
        del capture_output, kwargs
        recorded.append(list(cmd))
        return subprocess.run([*cmd, '--help'], capture_output=True, text=True, check=False)

    with (
        patch.object(setup_environment, 'run_command', run_recorded),
        patch.object(setup_environment, 'is_admin', return_value=True),
    ):
        installed = setup_environment.install_claude()

    expected = [sys.executable, str(Path(setup_environment.__file__).resolve().parent / 'install_claude.py')]
    if len(recorded) != 1:
        print(f'FAIL: expected exactly one launch, recorded {recorded!r}')
        return 1
    argv = recorded[0]
    print(f'Step 1 launch: {argv!r}')
    if argv != expected:
        print(f'FAIL: expected {expected!r}')
        return 1
    if not installed:
        print('FAIL: the launch did not succeed')
        return 1
    print('OK: the setup runs the bundled installer under the current interpreter')
    return 0


if __name__ == '__main__':
    sys.exit(main())
