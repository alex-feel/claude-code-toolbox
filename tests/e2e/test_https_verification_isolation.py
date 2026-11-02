"""E2E tests that every test starts with the HTTPS verification the test session started with.

main() calls use_os_trust_store(), which points ssl.SSLContext at
truststore's class for the rest of the process, and urlopen() keeps the
opener it builds on its first call together with the TLS context of that
moment. A main()-flow test would otherwise decide how every later test
verifies certificates. tests/conftest.py restores ssl.SSLContext and starts
every test without urllib's cached opener.

Each test runs its own pytest session through pytester over one inner
module: a writer injects the trust store and builds urllib's opener, and a
reader then checks that neither reached it. With the tests/conftest.py
fixture in the inner conftest the reader passes; without it the reader
fails, which shows the inner session observes the leak.
"""

from __future__ import annotations

import pytest

_INNER_TESTS = '''
import ssl
import urllib.request

import truststore

from scripts import setup_environment

ORIGINAL = ssl.SSLContext


def test_writer() -> None:
    setup_environment.use_os_trust_store()
    with urllib.request.urlopen('data:text/plain,built') as response:
        assert response.read() == b'built'
    assert ssl.SSLContext is truststore.SSLContext
    assert urllib.request._opener is not None


def test_reader() -> None:
    assert ssl.SSLContext is ORIGINAL
    assert urllib.request._opener is None
'''

_INNER_ARGS = ('-p', 'no:cacheprovider', '-p', 'no:asyncio', '-W', 'error')


def test_restore_fixture_gives_the_next_test_the_session_verification(pytester: pytest.Pytester) -> None:
    """With the tests/conftest.py fixture, the reader starts with the standard library context and no opener."""
    pytester.makeconftest('from tests.conftest import _restore_https_verification\n')
    pytester.makepyfile(test_inner=_INNER_TESTS)

    result = pytester.runpytest(*_INNER_ARGS)

    result.assert_outcomes(passed=2)


def test_without_the_restore_fixture_the_reader_sees_the_trust_store(pytester: pytest.Pytester) -> None:
    """Without the fixture, the writer's injection and opener reach the reader, so the inner session detects a leak."""
    pytester.makepyfile(test_inner=_INNER_TESTS)

    result = pytester.runpytest(*_INNER_ARGS)

    result.assert_outcomes(passed=1, failed=1)
    result.stdout.fnmatch_lines(['*FAILED*test_reader*'])
