"""Run setup_environment.main() as a child process confined to its home directory.

The real-binary E2E tests start this runner as a separate interpreter that
runs setup_environment.main() with ``--yes --skip-install --no-admin``
against an isolated home directory::

    PYTHONPATH=<repo root> python tests/e2e/fixtures/setup_child.py <config> --yes --skip-install --no-admin

Everything main() does stays real -- the elevation gate, dependency
installation, settings and manifest writes -- except the writers that reach
outside the isolated home: the Windows registry (OS environment variables,
the WM_SETTINGCHANGE broadcast, the user PATH cleanup and extension) and
Fish universal variables. Those are replaced with no-ops so a test run never
changes the machine it runs on.

Setting SIMULATE_NON_ADMIN_VARIABLE to ``1`` makes the child behave as a
process without an administrator token whatever token it actually holds:
is_admin() reports False, and the elevation request the main() gate makes
prints ELEVATION_MARKER and exits 1 instead of opening an elevated window.
A test can then observe the gate firing, or being skipped by --no-admin, on
an elevated developer session and on CI runners alike. The variable sits
outside the CLAUDE_CODE_TOOLBOX_ namespace because it belongs to this
runner, not to the toolbox interface.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

from scripts import setup_environment

SIMULATE_NON_ADMIN_VARIABLE = 'CCT_E2E_SIMULATE_NON_ADMIN'
ELEVATION_MARKER = '[setup_child] elevation requested by the administrator gate'

_real_which = shutil.which


def _which_without_fish(cmd: str, *args: Any, **kwargs: Any) -> str | None:
    if cmd == 'fish':
        return None
    return _real_which(cmd, *args, **kwargs)


def _refuse_elevation(*_args: Any, **_kwargs: Any) -> None:
    """Stand in for the elevation request: print the marker and exit 1."""
    print(ELEVATION_MARKER, flush=True)
    sys.exit(1)


def main() -> None:
    """Run the setup with the runner's arguments and no machine-wide writes."""
    sys.argv = [str(Path(setup_environment.__file__)), *sys.argv[1:]]
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(setup_environment, 'set_os_env_variable_windows', lambda *_args, **_kwargs: True))
        stack.enter_context(patch.object(setup_environment, '_broadcast_wm_settingchange', lambda *_args, **_kwargs: None))
        stack.enter_context(patch.object(
            setup_environment, 'add_directory_to_windows_path',
            lambda directory: (True, f'[neutralized] {directory}'),
        ))
        stack.enter_context(patch.object(setup_environment, 'cleanup_temp_paths_from_registry', lambda: (0, [])))
        stack.enter_context(patch.object(shutil, 'which', _which_without_fish))
        if os.environ.get(SIMULATE_NON_ADMIN_VARIABLE) == '1':
            stack.enter_context(patch.object(setup_environment, 'is_admin', lambda: False))
            stack.enter_context(patch.object(setup_environment, 'request_admin_elevation', _refuse_elevation))
        setup_environment.main()


if __name__ == '__main__':
    main()
