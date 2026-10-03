"""E2E tests that every test starts with the PATH the test session started with.

The setup code updates the session PATH in place: refresh_path_from_registry()
rebuilds it from the Windows registry after installs (main() Step 13 among
other places), and the installers prepend the directories they create. A
registry rebuild drops every directory that exists only in the process PATH,
such as the directory a CI runner installs uv into, so a main()-flow test that
kept its PATH change would leave every later test unable to find uv.
tests/conftest.py restores PATH after every test.

The tests run in file order: each writer records the PATH it started with and
then changes PATH the way the setup code does; the last test checks that it
starts with that same PATH.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from scripts import setup_environment

_STARTING_PATHS: list[str] = []


@pytest.mark.skipif(sys.platform != 'win32', reason='refresh_path_from_registry() reads the Windows registry')
def test_registry_refresh_drops_a_process_only_directory(tmp_path: Path) -> None:
    """The registry rebuild main() runs on Windows removes a directory only the process PATH holds."""
    _STARTING_PATHS.append(os.environ['PATH'])
    process_only = tmp_path / 'process-only-bin'
    process_only.mkdir()
    os.environ['PATH'] = os.pathsep.join([str(process_only), os.environ['PATH']])

    assert setup_environment.refresh_path_from_registry()

    assert str(process_only) not in os.environ['PATH'].split(os.pathsep)


def test_direct_write_replaces_the_session_path(tmp_path: Path) -> None:
    """A writer that assigns os.environ['PATH'] directly, as the installers do, changes it for the process."""
    _STARTING_PATHS.append(os.environ['PATH'])

    os.environ['PATH'] = str(tmp_path)

    assert os.environ['PATH'] == str(tmp_path)


def test_next_test_starts_with_the_session_path() -> None:
    """The PATH changes the earlier tests made are gone: every test started with the same PATH."""
    assert _STARTING_PATHS, 'the writer tests above must run first'
    assert all(path == _STARTING_PATHS[0] for path in _STARTING_PATHS), _STARTING_PATHS
    assert os.environ['PATH'] == _STARTING_PATHS[0]
