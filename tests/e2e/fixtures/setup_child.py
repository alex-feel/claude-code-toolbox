"""Run setup_environment.main() as a child process confined to its home directory.

The real-binary E2E tests start this runner the way a source profile's
refresh starts a dependent profile: a separate interpreter with
``--yes --skip-install --no-admin`` and an isolated home directory::

    PYTHONPATH=<repo root> python tests/e2e/fixtures/setup_child.py <config> --yes --skip-install --no-admin

Everything main() does stays real -- the elevation gate, dependency
installation, settings and manifest writes -- except the writers that reach
outside the isolated home: the Windows registry (OS environment variables,
the WM_SETTINGCHANGE broadcast, the user PATH cleanup and extension) and
Fish universal variables. Those are replaced with no-ops so a test run never
changes the machine it runs on.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

from scripts import setup_environment

_real_which = shutil.which


def _which_without_fish(cmd: str, *args: Any, **kwargs: Any) -> str | None:
    if cmd == 'fish':
        return None
    return _real_which(cmd, *args, **kwargs)


def main() -> None:
    """Run the setup with the runner's arguments and no machine-wide writes."""
    sys.argv = [str(Path(setup_environment.__file__)), *sys.argv[1:]]
    with (
        patch.object(setup_environment, 'set_os_env_variable_windows', lambda *_args, **_kwargs: True),
        patch.object(setup_environment, '_broadcast_wm_settingchange', lambda *_args, **_kwargs: None),
        patch.object(
            setup_environment, 'add_directory_to_windows_path',
            lambda directory: (True, f'[neutralized] {directory}'),
        ),
        patch.object(setup_environment, 'cleanup_temp_paths_from_registry', lambda: (0, [])),
        patch.object(shutil, 'which', _which_without_fish),
    ):
        setup_environment.main()


if __name__ == '__main__':
    main()
