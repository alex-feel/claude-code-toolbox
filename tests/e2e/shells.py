"""Interpreter discovery for E2E tests that run generated scripts for real.

The toolbox generates POSIX, PowerShell and CMD files; the tests that hand
those files to their real interpreters share these lookups so every module
resolves the same executables.
"""

from __future__ import annotations

import shutil
import sys

from scripts.setup_environment import find_bash_windows


def find_bash() -> str | None:
    """Locate a bash able to run generated POSIX scripts.

    On Windows, plain which('bash') can resolve to the WSL shim, which
    cannot execute Windows paths; the Git Bash discovery from the module
    under test is authoritative there.

    Returns:
        Path to a usable bash executable, or None when unavailable.
    """
    if sys.platform == 'win32':
        return find_bash_windows()
    return shutil.which('bash')


def find_powershell() -> str | None:
    """Locate a PowerShell able to run generated .ps1 files.

    Returns:
        Path to a PowerShell executable, or None when unavailable.
    """
    return shutil.which('pwsh') or shutil.which('powershell')
