"""Tests for _line_buffer_output_streams(), which both standalone scripts call first in main().

A standard stream connected to a file or a pipe buffers its text in blocks;
after the call every printed line reaches the stream's buffer as it is
printed. A stream a caller replaced with an object that cannot be
reconfigured, such as an in-memory text buffer, is left as it is.
"""

from __future__ import annotations

import io
import sys
from types import ModuleType
from unittest.mock import patch

import pytest

from scripts import install_claude
from scripts import setup_environment

MODULES = [
    pytest.param(install_claude, id='install_claude'),
    pytest.param(setup_environment, id='setup_environment'),
]


def _file_like_stream(raw: io.BytesIO) -> io.TextIOWrapper:
    """A text stream over a byte buffer, block-buffered like a standard stream connected to a file."""
    return io.TextIOWrapper(raw, encoding='utf-8', newline='\n')


@pytest.mark.parametrize('module', MODULES)
def test_printed_line_reaches_the_buffer_at_once(module: ModuleType) -> None:
    """A line printed after the call is in the underlying buffer before anything flushes the stream."""
    out_raw, err_raw = io.BytesIO(), io.BytesIO()
    stdout, stderr = _file_like_stream(out_raw), _file_like_stream(err_raw)

    with patch.object(sys, 'stdout', stdout), patch.object(sys, 'stderr', stderr):
        module._line_buffer_output_streams()
        print('step line')
        print('error line', file=sys.stderr)

        assert out_raw.getvalue() == b'step line\n'
        assert err_raw.getvalue() == b'error line\n'
    assert stdout.line_buffering
    assert stderr.line_buffering


def test_file_like_stream_holds_a_printed_line_until_flushed() -> None:
    """The stream the tests above use buffers like a redirected standard stream: a printed line waits for a flush."""
    raw = io.BytesIO()
    stdout = _file_like_stream(raw)

    with patch.object(sys, 'stdout', stdout):
        print('step line')

        assert raw.getvalue() == b''
        stdout.flush()
        assert raw.getvalue() == b'step line\n'


@pytest.mark.parametrize('module', MODULES)
def test_stream_without_reconfigure_is_left_as_it_is(module: ModuleType) -> None:
    """An in-memory text buffer in place of a standard stream keeps working and keeps its content."""
    stdout, stderr = io.StringIO(), io.StringIO()

    with patch.object(sys, 'stdout', stdout), patch.object(sys, 'stderr', stderr):
        module._line_buffer_output_streams()
        print('step line')

    assert stdout.getvalue() == 'step line\n'
    assert stderr.getvalue() == ''
