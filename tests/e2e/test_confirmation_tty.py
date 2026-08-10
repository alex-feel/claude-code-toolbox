"""E2E tests for the real /dev/tty confirmation path under a pty.

The confirmation regression that motivated these tests was invisible to
mocked tests: every existing confirmation test patched
_get_user_confirmation to return a clean string, while the real read path
returned the terminal's queued cursor-position report glued to the typed
answer (``ESC[24;80Ry``), cancelling the installation on a visually clean
``y``. These tests exercise the REAL code path: a forked child whose
controlling terminal is a pty and whose stdin is /dev/null (the curl | bash
shape), reading through _get_user_confirmation and confirm_installation
exactly as production does.

The POSIX-only modules (pty) and constants (WNOHANG, SIGKILL) are accessed
dynamically because the type checkers analyze this file for the Windows
platform too, where the tests are skipped.
"""

from __future__ import annotations

import importlib
import os
import select
import signal
import sys
import time
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform == 'win32',
    reason='pty and /dev/tty are POSIX-only',
)

REPO_ROOT = Path(__file__).resolve().parents[2]
_WNOHANG: int = getattr(os, 'WNOHANG', 1)
_SIGKILL: int = getattr(signal, 'SIGKILL', 9)

CONFIRMATION_PROBE = '''
import sys, time
sys.path.insert(0, {repo!r})
from scripts.setup_environment import _get_user_confirmation
time.sleep({delay})
result = _get_user_confirmation('PROMPT_READY: ')
print('RESULT=' + repr(result))
'''

CONFIRM_INSTALLATION_PROBE = '''
import sys, time
sys.path.insert(0, {repo!r})
from scripts import setup_environment
setup_environment.display_installation_summary = lambda plan: None
time.sleep({delay})
result = setup_environment.confirm_installation(None)
print('RESULT=' + repr(result))
'''


def _reap_child(pid: int) -> None:
    """Wait for the probe child, force-killing it if it lingers."""
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            done, _ = os.waitpid(pid, _WNOHANG)
        except ChildProcessError:
            return
        if done:
            return
        time.sleep(0.05)
    os.kill(pid, _SIGKILL)
    os.waitpid(pid, 0)


def _run_pty_probe(
    code_template: str,
    payload: bytes,
    *,
    pre_queued: bytes = b'',
    prompt_marker: bytes = b'PROMPT_READY',
    delay: float = 0.0,
) -> str:
    """Run a probe in a child whose controlling terminal is a fresh pty.

    The child's stdin is redirected to /dev/null before exec, so the
    production /dev/tty fallback is the only interactive channel -- the
    same shape as a curl | bash install.

    Args:
        code_template: Python source with {repo} and {delay} placeholders.
        payload: Bytes written to the pty after the prompt renders.
        pre_queued: Bytes queued into the pty before the prompt renders.
        prompt_marker: Output substring that signals the prompt rendered.
        delay: Seconds the child sleeps before prompting, giving pre_queued
            bytes time to land in the terminal input queue.

    Returns:
        The RESULT=... line printed by the child.

    Raises:
        AssertionError: When the probe times out or produces no RESULT line.
    """
    pty_module: Any = importlib.import_module('pty')

    pid, master = pty_module.fork()
    if pid == 0:  # pragma: no cover - child process
        devnull = os.open(os.devnull, os.O_RDONLY)
        os.dup2(devnull, 0)
        code = code_template.format(repo=str(REPO_ROOT), delay=delay)
        os.execv(sys.executable, [sys.executable, '-c', code])

    buffer = b''
    sent = False
    timed_out = True
    deadline = time.time() + 60
    try:
        if pre_queued:
            os.write(master, pre_queued)
        while time.time() < deadline:
            ready, _, _ = select.select([master], [], [], 0.5)
            if ready:
                try:
                    chunk = os.read(master, 4096)
                except OSError:
                    timed_out = False
                    break
                if not chunk:
                    timed_out = False
                    break
                buffer += chunk
            if not sent and prompt_marker in buffer:
                os.write(master, payload)
                sent = True
            if b'RESULT=' in buffer and b'\n' in buffer.split(b'RESULT=')[-1]:
                timed_out = False
                break
        if timed_out:
            os.kill(pid, _SIGKILL)
    finally:
        _reap_child(pid)
        os.close(master)

    if timed_out:
        raise AssertionError(f'pty probe timed out; output so far: {buffer!r}')

    for line in buffer.decode('utf-8', 'replace').splitlines():
        if 'RESULT=' in line:
            return line[line.index('RESULT='):]
    raise AssertionError(f'no RESULT line in pty output: {buffer!r}')


class TestDevTtyConfirmationRead:
    """_get_user_confirmation through a real pty with piped stdin."""

    def test_clean_yes(self) -> None:
        """A plain typed y reads back as y."""
        assert _run_pty_probe(CONFIRMATION_PROBE, b'y\n') == "RESULT='y'"

    def test_clean_no(self) -> None:
        """A plain typed n reads back as n."""
        assert _run_pty_probe(CONFIRMATION_PROBE, b'n\n') == "RESULT='n'"

    def test_contaminated_line_sanitized(self) -> None:
        """A cursor-position report glued to the answer is stripped.

        This is the exact regression: the report renders invisibly, the
        user sees a clean y, and the unsanitized read returned
        ESC[24;80Ry.
        """
        assert _run_pty_probe(CONFIRMATION_PROBE, b'\x1b[24;80Ry\n') == "RESULT='y'"

    def test_pre_queued_garbage_flushed(self) -> None:
        """Bytes queued before the prompt renders never satisfy the read."""
        result = _run_pty_probe(
            CONFIRMATION_PROBE,
            b'y\n',
            pre_queued=b'\x1b[24;80R',
            delay=1.0,
        )
        assert result == "RESULT='y'"


class TestConfirmInstallationThroughPty:
    """confirm_installation end-to-end through a real pty."""

    def test_contaminated_yes_proceeds(self) -> None:
        """The full consent flow accepts a contaminated y."""
        result = _run_pty_probe(
            CONFIRM_INSTALLATION_PROBE,
            b'\x1b[24;80Ry\n',
            prompt_marker=b'Proceed with installation?',
        )
        assert result == 'RESULT=True'

    def test_enter_cancels(self) -> None:
        """The default deny still cancels through the real path."""
        result = _run_pty_probe(
            CONFIRM_INSTALLATION_PROBE,
            b'\n',
            prompt_marker=b'Proceed with installation?',
        )
        assert result == 'RESULT=False'
