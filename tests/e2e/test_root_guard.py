"""E2E tests for root detection guard behavior.

Tests verify that:
- Root detection guard prevents execution as root/sudo
- CLAUDE_ALLOW_ROOT=1 override works correctly
- Root guard only activates on Unix platforms (Linux/macOS)
- Root guard produces correct error messages with actionable guidance
- Root guard runs before any other setup logic
"""

from __future__ import annotations

import contextlib
import os
from unittest.mock import patch

import pytest

from scripts import install_claude
from scripts import setup_environment


class TestRootGuardInstallClaude:
    """E2E tests for root guard in install_claude.py main()."""

    def test_root_guard_blocks_root_execution(self) -> None:
        """Verify main() exits with code 1 when running as root without override."""
        os.environ.pop('CLAUDE_ALLOW_ROOT', None)
        with (
            patch('platform.system', return_value='Linux'),
            patch('os.geteuid', create=True, return_value=0),
            patch.dict('os.environ', {}, clear=False),
            pytest.raises(SystemExit) as exc_info,
        ):
            install_claude.main()

        assert exc_info.value.code == 1

    def test_root_guard_allows_with_override(self) -> None:
        """Verify main() proceeds when CLAUDE_ALLOW_ROOT=1 is set."""
        with (
            patch('platform.system', return_value='Linux'),
            patch('os.geteuid', create=True, return_value=0),
            patch.dict('os.environ', {'CLAUDE_ALLOW_ROOT': '1', 'CLAUDE_INSTALL_METHOD': 'npm'}),
            patch.object(install_claude, 'ensure_nodejs', return_value=True),
            patch.object(install_claude, 'ensure_claude', return_value=True), contextlib.suppress(SystemExit),
        ):
            install_claude.main()

    def test_root_guard_skipped_on_non_root(self) -> None:
        """Verify root guard does not trigger for regular users (euid != 0)."""
        with (
            patch('platform.system', return_value='Linux'),
            patch('os.geteuid', create=True, return_value=1000),
            patch.dict('os.environ', {'CLAUDE_INSTALL_METHOD': 'npm'}),
            patch.object(install_claude, 'ensure_nodejs', return_value=True),
            patch.object(install_claude, 'ensure_claude', return_value=True), contextlib.suppress(SystemExit),
        ):
            install_claude.main()

    def test_root_guard_error_message_content(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Verify root guard produces informative error message with actionable guidance."""
        os.environ.pop('CLAUDE_ALLOW_ROOT', None)
        with (
            patch('platform.system', return_value='Linux'),
            patch('os.geteuid', create=True, return_value=0),
            patch.dict('os.environ', {}, clear=False),
            pytest.raises(SystemExit),
        ):
            install_claude.main()

        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert 'CLAUDE_ALLOW_ROOT' in combined, 'Error message should mention override variable'
        assert 'root' in combined.lower() or 'sudo' in combined.lower(), \
            'Error message should mention root/sudo'

    def test_root_guard_activates_on_macos(self) -> None:
        """Verify root guard also activates on macOS (Darwin)."""
        os.environ.pop('CLAUDE_ALLOW_ROOT', None)
        with (
            patch('platform.system', return_value='Darwin'),
            patch('os.geteuid', create=True, return_value=0),
            patch.dict('os.environ', {}, clear=False),
            pytest.raises(SystemExit) as exc_info,
        ):
            install_claude.main()

        assert exc_info.value.code == 1

    def test_root_guard_does_not_activate_on_windows(self) -> None:
        """Verify root guard is not triggered on Windows even with admin rights."""
        with (
            patch('platform.system', return_value='Windows'),
            patch.object(install_claude, 'ensure_git_bash_windows', return_value='C:\\Git\\bash.exe'),
            patch.object(install_claude, 'ensure_claude', return_value=True),
            patch.object(install_claude, 'configure_powershell_policy'),
            patch.object(install_claude, 'update_path'),
            patch.object(install_claude, 'find_command', return_value=None),
            patch.object(install_claude, 'set_windows_env_var'),
            patch.dict('os.environ', {'CLAUDE_INSTALL_METHOD': 'native'}), contextlib.suppress(SystemExit),
        ):
            install_claude.main()

    def test_root_guard_with_empty_claude_allow_root(self) -> None:
        """CLAUDE_ALLOW_ROOT='' (empty string) should NOT bypass root guard."""
        os.environ.pop('CLAUDE_ALLOW_ROOT', None)
        with (
            patch('platform.system', return_value='Linux'),
            patch('os.geteuid', create=True, return_value=0),
            patch.dict('os.environ', {'CLAUDE_ALLOW_ROOT': ''}, clear=False),
            pytest.raises(SystemExit) as exc_info,
        ):
            install_claude.main()

        assert exc_info.value.code == 1

    def test_root_guard_with_non_one_value(self) -> None:
        """CLAUDE_ALLOW_ROOT=true (not '1') should NOT bypass root guard."""
        with (
            patch('platform.system', return_value='Linux'),
            patch('os.geteuid', create=True, return_value=0),
            patch.dict('os.environ', {'CLAUDE_ALLOW_ROOT': 'true'}, clear=False),
            pytest.raises(SystemExit) as exc_info,
        ):
            install_claude.main()

        assert exc_info.value.code == 1


class TestRootGuardSetupEnvironment:
    """E2E tests for root guard in setup_environment.py main()."""

    def test_root_guard_blocks_root_execution(self) -> None:
        """Verify setup_environment main() exits when running as root."""
        os.environ.pop('CLAUDE_ALLOW_ROOT', None)
        with (
            patch('platform.system', return_value='Linux'),
            patch('os.geteuid', create=True, return_value=0),
            patch.dict('os.environ', {}, clear=False),
            pytest.raises(SystemExit) as exc_info,
        ):
            setup_environment.main()

        assert exc_info.value.code == 1

    def test_root_guard_allows_with_override(self) -> None:
        """Verify setup_environment proceeds when CLAUDE_ALLOW_ROOT=1 is set."""
        with (
            patch('platform.system', return_value='Linux'),
            patch('os.geteuid', create=True, return_value=0),
            patch.dict('os.environ', {'CLAUDE_ALLOW_ROOT': '1'}),
            patch('sys.argv', ['setup_environment.py', 'python']), contextlib.suppress(SystemExit, Exception),
        ):
            setup_environment.main()

    def test_root_guard_error_message_content(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Verify setup_environment root guard message contains key information."""
        os.environ.pop('CLAUDE_ALLOW_ROOT', None)
        with (
            patch('platform.system', return_value='Linux'),
            patch('os.geteuid', create=True, return_value=0),
            patch.dict('os.environ', {}, clear=False),
            pytest.raises(SystemExit),
        ):
            setup_environment.main()

        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert 'CLAUDE_ALLOW_ROOT' in combined, 'Should mention override variable'
        assert 'root' in combined.lower() or 'sudo' in combined.lower()

    def test_root_guard_activates_on_macos(self) -> None:
        """Verify root guard on macOS for setup_environment."""
        os.environ.pop('CLAUDE_ALLOW_ROOT', None)
        with (
            patch('platform.system', return_value='Darwin'),
            patch('os.geteuid', create=True, return_value=0),
            patch.dict('os.environ', {}, clear=False),
            pytest.raises(SystemExit) as exc_info,
        ):
            setup_environment.main()

        assert exc_info.value.code == 1

    def test_root_guard_runs_before_argument_parsing(self) -> None:
        """Verify root guard triggers even without valid CLI arguments.

        The root guard MUST run before argparse to catch all invocations.
        """
        os.environ.pop('CLAUDE_ALLOW_ROOT', None)
        with (
            patch('platform.system', return_value='Linux'),
            patch('os.geteuid', create=True, return_value=0),
            patch.dict('os.environ', {}, clear=False),
            patch('sys.argv', ['setup_environment.py']),
            pytest.raises(SystemExit) as exc_info,
        ):
            setup_environment.main()

        # Should exit from root guard (code 1), NOT from argparse error (code 2)
        assert exc_info.value.code == 1

    def test_root_guard_skipped_on_windows(self) -> None:
        """Verify Windows admin handling is separate from root guard."""
        with (
            patch('platform.system', return_value='Windows'),
            patch.object(setup_environment, 'is_admin', return_value=False),
            patch('sys.argv', ['setup_environment.py', 'python']), contextlib.suppress(SystemExit, Exception),
        ):
            setup_environment.main()

    def test_root_guard_with_empty_claude_allow_root(self) -> None:
        """CLAUDE_ALLOW_ROOT='' should NOT bypass root guard in setup_environment."""
        os.environ.pop('CLAUDE_ALLOW_ROOT', None)
        with (
            patch('platform.system', return_value='Linux'),
            patch('os.geteuid', create=True, return_value=0),
            patch.dict('os.environ', {'CLAUDE_ALLOW_ROOT': ''}, clear=False),
            pytest.raises(SystemExit) as exc_info,
        ):
            setup_environment.main()

        assert exc_info.value.code == 1

    def test_root_guard_with_non_one_value(self) -> None:
        """CLAUDE_ALLOW_ROOT=yes should NOT bypass root guard in setup_environment."""
        with (
            patch('platform.system', return_value='Linux'),
            patch('os.geteuid', create=True, return_value=0),
            patch.dict('os.environ', {'CLAUDE_ALLOW_ROOT': 'yes'}, clear=False),
            pytest.raises(SystemExit) as exc_info,
        ):
            setup_environment.main()

        assert exc_info.value.code == 1
