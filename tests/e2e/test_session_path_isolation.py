"""E2E tests that every test starts with the PATH the test session started with.

The setup code updates the session PATH in place: refresh_path_from_registry()
rebuilds it from the Windows registry after installs (main() Step 13 among
other places), and the installers prepend the directories they create. A
registry rebuild drops every directory that exists only in the process PATH,
such as the directory a CI runner installs uv into, so a main()-flow test that
kept its PATH change would leave every later test unable to find uv.
tests/conftest.py restores PATH after every test.

Each test runs its own pytest session through pytester over one inner module:
a writer changes PATH the way the setup code does, and a reader then checks
that PATH is the value the inner session started with. The inner session runs
both, writer first, whichever of these tests is selected. With the
tests/conftest.py fixture in the inner conftest the reader passes; without it
the reader fails, which shows the inner session observes a leaked PATH.
"""

from __future__ import annotations

import pytest

_INNER_TESTS = '''
import os
import sys
from pathlib import Path

from scripts import setup_environment

ORIGINAL = os.environ['PATH']


def test_writer(tmp_path: Path) -> None:
    if sys.platform == 'win32':
        process_only = tmp_path / 'process-only-bin'
        process_only.mkdir()
        os.environ['PATH'] = os.pathsep.join([str(process_only), os.environ['PATH']])
        assert setup_environment.refresh_path_from_registry()
        assert str(process_only) not in os.environ['PATH'].split(os.pathsep)
    os.environ['PATH'] = os.pathsep.join([str(tmp_path), os.environ['PATH']])
    assert os.environ['PATH'] != ORIGINAL


def test_reader() -> None:
    assert os.environ['PATH'] == ORIGINAL
'''

_INNER_ARGS = ('-p', 'no:cacheprovider', '-p', 'no:asyncio', '-W', 'error')


def test_restore_fixture_gives_the_next_test_the_session_path(pytester: pytest.Pytester) -> None:
    """With the tests/conftest.py fixture, the reader starts with the PATH the writer started with."""
    pytester.makeconftest('from tests.conftest import _restore_session_path\n')
    pytester.makepyfile(test_inner=_INNER_TESTS)

    result = pytester.runpytest(*_INNER_ARGS)

    result.assert_outcomes(passed=2)


def test_without_the_restore_fixture_the_reader_sees_the_leaked_path(pytester: pytest.Pytester) -> None:
    """Without the fixture, the writer's PATH reaches the reader, so the inner session detects a leak."""
    pytester.makepyfile(test_inner=_INNER_TESTS)

    result = pytester.runpytest(*_INNER_ARGS)

    result.assert_outcomes(passed=1, failed=1)
    result.stdout.fnmatch_lines(['*FAILED*test_reader*'])
