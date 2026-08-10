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

import contextlib
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

NUMBERED_PICKER_PROBE = '''
import sys, time
sys.path.insert(0, {repo!r})
from scripts.setup_environment import _prompt_component_selection_numbered
time.sleep({delay})
result = _prompt_component_selection_numbered(
    ['alpha', 'beta'], {{'alpha': 'Alpha', 'beta': 'Beta'}}, ['alpha', 'beta'],
)
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
    try:
        os.kill(pid, _SIGKILL)
        os.waitpid(pid, 0)
    except (ProcessLookupError, ChildProcessError, OSError):
        pass


def _run_pty_probe(
    code_template: str,
    payload: bytes,
    *,
    pre_queued: bytes = b'',
    prompt_marker: bytes = b'PROMPT_READY',
    followup: tuple[bytes, bytes] | None = None,
    delay: float = 0.0,
) -> tuple[str, str]:
    """Run a probe in a child whose controlling terminal is a fresh pty.

    The child's stdin is redirected to /dev/null before exec, so the
    production /dev/tty fallback is the only interactive channel -- the
    same shape as a curl | bash install.

    Args:
        code_template: Python source with {repo} and {delay} placeholders.
        payload: Bytes written to the pty after the prompt renders.
        pre_queued: Bytes queued into the pty before the prompt renders.
        prompt_marker: Output substring that signals the prompt rendered.
        followup: Optional second exchange (marker, payload): the payload
            is written only after the marker appears in output produced
            AFTER the first payload was sent, because consent re-prompts
            flush type-ahead.
        delay: Seconds the child sleeps before prompting, giving pre_queued
            bytes time to land in the terminal input queue.

    Returns:
        Tuple of the RESULT=... line printed by the child and the child's
        full decoded output (for asserting which prompts and warnings
        rendered).

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
    followup_sent = False
    search_from = 0
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
                search_from = len(buffer)
            if (
                sent and not followup_sent and followup is not None
                and followup[0] in buffer[search_from:]
            ):
                os.write(master, followup[1])
                followup_sent = True
            if b'RESULT=' in buffer and b'\n' in buffer.split(b'RESULT=')[-1]:
                timed_out = False
                break
        if timed_out:
            with contextlib.suppress(ProcessLookupError, OSError):
                os.kill(pid, _SIGKILL)
    finally:
        _reap_child(pid)
        os.close(master)

    if timed_out:
        raise AssertionError(f'pty probe timed out; output so far: {buffer!r}')

    output = buffer.decode('utf-8', 'replace')
    for line in output.splitlines():
        if 'RESULT=' in line:
            return line[line.index('RESULT='):], output
    raise AssertionError(f'no RESULT line in pty output: {buffer!r}')


class TestDevTtyConfirmationRead:
    """_get_user_confirmation through a real pty with piped stdin."""

    def test_clean_yes(self) -> None:
        """A plain typed y reads back as y."""
        result, _ = _run_pty_probe(CONFIRMATION_PROBE, b'y\n')
        assert result == "RESULT='y'"

    def test_clean_no(self) -> None:
        """A plain typed n reads back as n."""
        result, _ = _run_pty_probe(CONFIRMATION_PROBE, b'n\n')
        assert result == "RESULT='n'"

    def test_contaminated_line_sanitized(self) -> None:
        """A cursor-position report glued to the answer is stripped.

        This is the exact regression: the report renders invisibly, the
        user sees a clean y, and the unsanitized read returned
        ESC[24;80Ry.
        """
        result, _ = _run_pty_probe(CONFIRMATION_PROBE, b'\x1b[24;80Ry\n')
        assert result == "RESULT='y'"

    def test_pre_queued_garbage_flushed(self) -> None:
        """A garbage line queued before the prompt renders is discarded.

        The queued report forms its own complete line so an unflushed read
        would consume it as a standalone answer; the flush makes the read
        start at the user's y with no detour through the marker handling.
        """
        result, _ = _run_pty_probe(
            CONFIRMATION_PROBE,
            b'y\n',
            pre_queued=b'\x1b[24;80R\n',
            delay=1.0,
        )
        assert result == "RESULT='y'"


class TestNumberedPickerThroughPty:
    """The Tier 2 numbered picker through a real pty with piped stdin."""

    def test_pre_queued_garbage_never_confirms_the_seed(self) -> None:
        """Garbage queued before the picker renders cannot press Enter for the user.

        The questionary tier can fail mid-render with its terminal query
        replies still queued; the numbered picker flushes them at entry, so
        the user's real toggle of item 2 plus Enter decides the outcome.
        The queued report forms its own complete line, and the absence of
        the invalid-input warning proves the flush discarded it rather than
        the marker handling absorbing it.
        """
        result, output = _run_pty_probe(
            NUMBERED_PICKER_PROBE,
            b'2\n\n',
            pre_queued=b'\x1b[24;80R\n',
            prompt_marker=b'Enter = confirm:',
            delay=1.0,
        )
        assert result == "RESULT=['alpha']"
        assert 'Invalid input' not in output

    def test_contaminated_line_reprompts_not_confirms(self) -> None:
        """An all-garbage line mid-loop is invalid input, not Enter-confirm."""
        result, output = _run_pty_probe(
            NUMBERED_PICKER_PROBE,
            b'\x1b[24;80R\n2\n\n',
            prompt_marker=b'Enter = confirm:',
        )
        assert result == "RESULT=['alpha']"
        assert 'Invalid input' in output


class TestConfirmInstallationThroughPty:
    """confirm_installation end-to-end through a real pty."""

    def test_contaminated_yes_proceeds(self) -> None:
        """The full consent flow accepts a contaminated y."""
        result, _ = _run_pty_probe(
            CONFIRM_INSTALLATION_PROBE,
            b'\x1b[24;80Ry\n',
            prompt_marker=b'Proceed with installation?',
        )
        assert result == 'RESULT=True'

    def test_all_garbage_line_reprompts_then_accepts(self) -> None:
        """A pure-garbage line re-prompts; a y at the re-prompt proceeds.

        The y is sent only after the warning renders, because the
        re-prompt flushes type-ahead by design.
        """
        result, output = _run_pty_probe(
            CONFIRM_INSTALLATION_PROBE,
            b'\x1b[24;80R\n',
            prompt_marker=b'Proceed with installation?',
            followup=(b'Unrecognized answer', b'y\n'),
        )
        assert result == 'RESULT=True'
        assert 'Unrecognized answer' in output

    def test_enter_cancels(self) -> None:
        """The default deny still cancels through the real path."""
        result, _ = _run_pty_probe(
            CONFIRM_INSTALLATION_PROBE,
            b'\n',
            prompt_marker=b'Proceed with installation?',
        )
        assert result == 'RESULT=False'
