"""Executable stubs standing in for the host CLIs (gh, glab) a credential lookup asks.

A stub prints fixed lines and exits with a fixed code, so a test decides what
``gh auth token`` or ``glab auth status --show-token`` answers without a real
login on the machine running the suite. On Windows a stub is a ``.cmd`` file
(found through PATHEXT), elsewhere an executable shell script.
"""

from __future__ import annotations

import stat
import sys
from pathlib import Path


def write_cli_stub(directory: Path, name: str, lines: list[str], *, stderr: bool = False, exit_code: int = 0) -> Path:
    """Write a stub executable into a directory that is on PATH.

    Args:
        directory: The directory the stub goes into.
        name: The command name the stub answers for.
        lines: The lines the stub prints.
        stderr: Whether the lines go to stderr instead of stdout.
        exit_code: The stub's exit code.

    Returns:
        The stub's path.
    """
    if sys.platform == 'win32':
        body = ['@echo off']
        body.extend(f'echo {line} 1>&2' if stderr else f'echo {line}' for line in lines)
        body.append(f'exit /b {exit_code}')
        path = directory / f'{name}.cmd'
        path.write_text('\r\n'.join(body) + '\r\n', encoding='utf-8')
        return path
    body = ['#!/bin/sh']
    body.extend(f"echo '{line}' >&2" if stderr else f"echo '{line}'" for line in lines)
    body.append(f'exit {exit_code}')
    path = directory / name
    path.write_text('\n'.join(body) + '\n', encoding='utf-8')
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path
