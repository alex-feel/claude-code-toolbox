"""Shared helpers of the leftovers tests: reading the leftovers block of a run's output, linking a file, and a
dependency command that installs a skill directory."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

# The dependencies key of this platform, whose commands run in bash on Linux and macOS and in PowerShell on Windows
DEPENDENCY_PLATFORM = {'win32': 'windows', 'darwin': 'macos'}.get(sys.platform, 'linux')
SKIP = ['--skip-install', '--no-admin']
HEADING = 'Leftovers of earlier runs (this configuration no longer installs them):'
REMOVES = 'Step 23 removes each item marked [remove] only while it still holds what the setup wrote.'
REMOVES_OTHERS_STAY = (
    'Step 23 removes each item marked [remove] only while it still holds what the setup wrote; the others stay in place.'
)
_ANSI = re.compile(r'\x1b\[[0-9;]*m')
# Windows refuses a symlink without administrator rights or Developer Mode
_WINERROR_PRIVILEGE_NOT_HELD = 1314


def symlink_file(link: Path, target: Path) -> None:
    """Make link a symlink to the file target, as a dotfiles manager links a settings file.

    Args:
        link: The link to create.
        target: What it points to, absolute or relative to the link's directory.

    Raises:
        OSError: When the link cannot be created for a reason other than a
            missing Windows symlink privilege, which skips the test instead.
    """
    try:
        os.symlink(target, link)
    except OSError as error:
        if sys.platform == 'win32' and getattr(error, 'winerror', None) == _WINERROR_PRIVILEGE_NOT_HELD:
            pytest.skip(
                'file symlinks need administrator rights or Developer Mode on this Windows machine '
                f'(WinError {_WINERROR_PRIVILEGE_NOT_HELD})',
            )
        raise


def create_skill_command(name: str) -> str:
    """A dependency command that creates one skill directory of the base config home in place.

    In an isolated run the setup re-roots the path into the profile.

    Args:
        name: The skill name.

    Returns:
        The command for this platform's shell.
    """
    if DEPENDENCY_PLATFORM == 'windows':
        return (
            f'New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\\.claude\\skills\\{name}" | Out-Null; '
            f'Set-Content -Path "$env:USERPROFILE\\.claude\\skills\\{name}\\SKILL.md" -Value {name}'
        )
    return f'mkdir -p "$HOME/.claude/skills/{name}" && echo {name} > "$HOME/.claude/skills/{name}/SKILL.md"'


def printed(capture: pytest.CaptureFixture[str]) -> str:
    """Return everything the run printed, with Windows line endings normalized and colors left out.

    Args:
        capture: The capsys or capfd fixture of the test.

    Returns:
        The standard output and standard error of the run, in that order.
    """
    captured = capture.readouterr()
    return _ANSI.sub('', (captured.out + captured.err).replace('\r\n', '\n'))


def leftover_rows(output: str) -> list[str]:
    """Return the rows of the installation summary's leftovers block, below its heading line.

    Args:
        output: What the run printed.

    Returns:
        The block's lines, each with its indentation.
    """
    assert HEADING in output, output
    return output.split(HEADING)[1].split('\n', 1)[1].split('\n\n')[0].strip('\n').split('\n')
