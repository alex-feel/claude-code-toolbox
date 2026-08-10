"""Unit tests for interactive input sanitization and consent robustness.

A consent line read from a terminal can be contaminated by queued terminal
report sequences (verified with a real pty: a cursor-position reply left in
the input buffer prefixes the typed answer, so a visually clean ``y`` reads
as ``ESC[24;80Ry`` and cancelled the installation). These tests cover the
sanitizer, the pending-input flush, the sanitized read path, and the
confirmation re-prompt loop. The real /dev/tty behavior is exercised
end-to-end by tests/e2e/test_confirmation_tty.py on POSIX.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from scripts import setup_environment
from scripts.setup_environment import _flush_pending_terminal_input
from scripts.setup_environment import _read_user_input
from scripts.setup_environment import _sanitize_interactive_input


class TestSanitizeInteractiveInput:
    """Escape sequences and control characters never reach the caller."""

    @pytest.mark.parametrize(
        ('raw', 'expected'),
        [
            ('y\n', 'y'),
            ('  yes  ', 'yes'),
            ('\x1b[24;80Ry\n', 'y'),
            ('\x1b[24;80R\x1b[1;1Hy\n', 'y'),
            ('y\x1b[24;80R\n', 'y'),
            ('\x1b]0;title\x07y\n', 'y'),
            ('\x1b(By\n', 'y'),
            ('\x01\x02y\x7f\n', 'y'),
            ('\x1b[?2004hy\x1b[?2004l\n', 'y'),
            # Alt+y arrives as a bare ESC plus the character; the ESC is
            # stripped alone so the consent survives
            ('\x1by\n', 'y'),
            # SS3 function keys (xterm F1) are stripped whole
            ('\x1bOPy\n', 'y'),
            ('\x1bOP\n', ''),
            ('\x1b\n', ''),
            ('', ''),
            ('\x1b[24;80R\n', ''),
        ],
    )
    def test_sanitizes(self, raw: str, expected: str) -> None:
        """Every contaminated form reduces to the typed answer."""
        assert _sanitize_interactive_input(raw) == expected

    def test_interior_whitespace_preserved(self) -> None:
        """Sanitization strips edges only; interior content is untouched."""
        assert _sanitize_interactive_input('a b\tc\n') == 'a b\tc'


class TestFlushPendingTerminalInput:
    """The flush is best-effort and never raises."""

    def test_never_raises_in_test_environment(self) -> None:
        """Captured pytest streams (no real terminal) are handled silently."""
        _flush_pending_terminal_input()

    def test_posix_tty_stdin_flushes_terminal_queue(self) -> None:
        """A tty stdin is flushed via termios.tcflush on POSIX."""
        fake_termios = SimpleNamespace(
            tcflush=MagicMock(),
            TCIFLUSH=0,
            error=type('error', (Exception,), {}),
        )
        fake_stdin = MagicMock()
        fake_stdin.isatty.return_value = True
        fake_stdin.fileno.return_value = 5
        with patch.object(sys, 'platform', 'linux'), \
             patch.dict(sys.modules, {'termios': fake_termios}), \
             patch.object(sys, 'stdin', fake_stdin):
            _flush_pending_terminal_input()
        fake_termios.tcflush.assert_called_once_with(5, 0)

    def test_posix_piped_stdin_flushes_dev_tty(self) -> None:
        """With piped stdin, the /dev/tty queue is flushed instead."""
        fake_termios = SimpleNamespace(
            tcflush=MagicMock(),
            TCIFLUSH=0,
            error=type('error', (Exception,), {}),
        )
        fake_stdin = MagicMock()
        fake_stdin.isatty.return_value = False
        tty_handle = MagicMock()
        tty_handle.fileno.return_value = 7
        opener = MagicMock()
        opener.return_value.__enter__ = MagicMock(return_value=tty_handle)
        opener.return_value.__exit__ = MagicMock(return_value=False)
        with patch.object(sys, 'platform', 'linux'), \
             patch.dict(sys.modules, {'termios': fake_termios}), \
             patch.object(sys, 'stdin', fake_stdin), \
             patch('builtins.open', opener):
            _flush_pending_terminal_input()
        opener.assert_called_once_with('/dev/tty')
        fake_termios.tcflush.assert_called_once_with(7, 0)

    def test_missing_termios_is_silent(self) -> None:
        """An unavailable termios module ends the flush without raising."""
        fake_stdin = MagicMock()
        fake_stdin.isatty.return_value = True
        with patch.object(sys, 'platform', 'linux'), \
             patch.dict(sys.modules, {'termios': None}), \
             patch.object(sys, 'stdin', fake_stdin):
            _flush_pending_terminal_input()

    def test_windows_branch_drains_console_buffer(self) -> None:
        """The win32 branch drains msvcrt keystrokes until the buffer is empty."""
        fake_msvcrt = SimpleNamespace(
            kbhit=MagicMock(side_effect=[True, True, False]),
            getwch=MagicMock(return_value='x'),
        )
        with patch.object(sys, 'platform', 'win32'), \
             patch.dict(sys.modules, {'msvcrt': fake_msvcrt}):
            _flush_pending_terminal_input()
        assert fake_msvcrt.getwch.call_count == 2

    def test_windows_missing_msvcrt_is_silent(self) -> None:
        """An unavailable msvcrt module ends the flush without raising."""
        with patch.object(sys, 'platform', 'win32'), \
             patch.dict(sys.modules, {'msvcrt': None}):
            _flush_pending_terminal_input()


class TestReadUserInputSanitized:
    """Both read paths return sanitized answers."""

    def test_tty_stdin_path_sanitizes(self) -> None:
        """A contaminated input() line reduces to the typed answer."""
        fake_stdin = MagicMock()
        fake_stdin.isatty.return_value = True
        with patch.object(sys, 'stdin', fake_stdin), \
             patch('builtins.input', return_value='\x1b[24;80Ry'):
            assert _read_user_input('prompt: ') == 'y'


class TestConfirmationReprompt:
    """Unrecognized answers re-prompt instead of silently cancelling."""

    @staticmethod
    def _confirm(responses: list[str]) -> tuple[bool, MagicMock]:
        confirmation = MagicMock(side_effect=responses)
        fake_stdin = MagicMock()
        fake_stdin.isatty.return_value = True
        with patch.object(setup_environment, 'display_installation_summary'), \
             patch.object(sys, 'stdin', fake_stdin), \
             patch.object(setup_environment, '_get_user_confirmation', confirmation):
            plan = MagicMock()
            result = setup_environment.confirm_installation(plan)
        return result, confirmation

    def test_garbage_then_yes_proceeds(self) -> None:
        """A mangled first answer re-prompts; the second y proceeds."""
        result, confirmation = self._confirm(['[24;80Rq', 'y'])
        assert result is True
        assert confirmation.call_count == 2

    def test_three_garbage_answers_cancel(self) -> None:
        """Persistent unrecognized answers cancel after three attempts."""
        result, confirmation = self._confirm(['a', 'b', 'c'])
        assert result is False
        assert confirmation.call_count == 3

    def test_explicit_no_cancels_without_reprompt(self) -> None:
        """An explicit n cancels on the first read."""
        result, confirmation = self._confirm(['n'])
        assert result is False
        assert confirmation.call_count == 1

    def test_enter_cancels_without_reprompt(self) -> None:
        """The default deny (empty answer) cancels on the first read."""
        result, confirmation = self._confirm([''])
        assert result is False
        assert confirmation.call_count == 1
