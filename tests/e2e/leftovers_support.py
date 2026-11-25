"""Shared helpers of the E2E tests that read the leftovers block of a run's output."""

from __future__ import annotations

import re

import pytest

SKIP = ['--skip-install', '--no-admin']
HEADING = 'Leftovers of earlier runs (this configuration no longer installs them):'
REMOVES = 'Step 23 removes each item marked [remove] only while it still holds what the setup wrote.'
_ANSI = re.compile(r'\x1b\[[0-9;]*m')


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
