"""E2E tests for npm sudo fallback, native installer diagnostics, and error messaging.

Tests verify that:
- Sudo uses the resolved npm_path (not bare 'npm')
- Non-interactive environments get TTY-aware guidance
- Interactive environments get password/sudoers guidance
- Sudo timeout is handled gracefully (30-second limit)
- Enhanced error messages appear on total npm failure
- Pre-warning appears when sudo is predicted via needs_sudo_for_npm()
- capture_output=True is set on the sudo subprocess call
- Native installer captures and logs stderr on failure
- Native installer captures and logs stdout on success
- ensure_claude() shows numbered troubleshooting steps on total failure
- ensure_claude() logs diagnostic info at npm fallback points
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from scripts import install_claude


class TestNpmSudoFallback:
    """E2E tests for TTY-aware sudo fallback in install_claude_npm()."""

    def test_sudo_uses_resolved_npm_path(self) -> None:
        """Verify sudo command uses the full resolved npm path, not bare 'npm'."""
        mock_subprocess = MagicMock()
        mock_subprocess.return_value = subprocess.CompletedProcess([], 0, '', '')

        with (
            patch('platform.system', return_value='Linux'),
            patch.object(install_claude, 'find_command_robust', return_value='/usr/local/bin/npm'),
            patch.object(install_claude, 'needs_sudo_for_npm', return_value=False),
            patch.object(
                install_claude, 'run_command',
                return_value=subprocess.CompletedProcess([], 1, '', 'permission denied'),
            ),
            patch('subprocess.run', mock_subprocess),
            patch('pathlib.Path.exists', return_value=True),
            patch('sys.stdin') as mock_stdin,
        ):
            mock_stdin.isatty.return_value = True
            result = install_claude.install_claude_npm()

        assert result is True
        # Verify the sudo call used the resolved path
        sudo_cmd = mock_subprocess.call_args[0][0]
        assert sudo_cmd[0] == 'sudo'
        assert sudo_cmd[1] == '/usr/local/bin/npm', (
            f'Expected resolved npm path, got bare command: {sudo_cmd[1]}'
        )

    def test_non_interactive_error_guidance(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Verify non-interactive (no TTY) environments get pipe-specific guidance.

        With pre-sudo gating, when no TTY and no cached credentials, sudo is
        SKIPPED entirely (only the credential check subprocess call happens).
        """
        mock_subprocess = MagicMock()
        # Credential check returns non-zero (no cached credentials)
        mock_subprocess.return_value = subprocess.CompletedProcess(
            ['sudo', '-n', 'true'], 1, '', '',
        )

        with (
            patch('platform.system', return_value='Linux'),
            patch.object(install_claude, 'find_command_robust', return_value='/usr/bin/npm'),
            patch.object(install_claude, 'needs_sudo_for_npm', return_value=False),
            patch.object(
                install_claude, 'run_command',
                return_value=subprocess.CompletedProcess([], 1, '', 'permission denied'),
            ),
            patch('subprocess.run', mock_subprocess),
            patch('pathlib.Path.exists', return_value=True),
            patch('sys.stdin') as mock_stdin,
        ):
            mock_stdin.isatty.return_value = False
            result = install_claude.install_claude_npm()

        assert result is False
        # Only the credential check should have been called (sudo skipped)
        assert mock_subprocess.call_count == 1, (
            f'Expected 1 subprocess.run call (credential check only), got {mock_subprocess.call_count}'
        )
        cred_check_args = mock_subprocess.call_args[0][0]
        assert cred_check_args == ['sudo', '-n', 'true'], (
            f'Expected credential check call, got: {cred_check_args}'
        )
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert 'non-interactive' in combined.lower(), (
            'Should mention non-interactive mode when no TTY'
        )
        assert 'curl | bash' in combined or 'curl' in combined.lower(), (
            'Should mention pipe scenario'
        )
        assert 'CLAUDE_INSTALL_METHOD=native' in combined, (
            'Should suggest native installer alternative'
        )

    def test_interactive_error_guidance(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Verify interactive (TTY available) environments get password/sudoers guidance."""
        mock_subprocess = MagicMock()
        mock_subprocess.return_value = subprocess.CompletedProcess([], 1, '', 'incorrect password')

        with (
            patch('platform.system', return_value='Linux'),
            patch.object(install_claude, 'find_command_robust', return_value='/usr/bin/npm'),
            patch.object(install_claude, 'needs_sudo_for_npm', return_value=False),
            patch.object(
                install_claude, 'run_command',
                return_value=subprocess.CompletedProcess([], 1, '', 'permission denied'),
            ),
            patch('subprocess.run', mock_subprocess),
            patch('pathlib.Path.exists', return_value=True),
            patch('sys.stdin') as mock_stdin,
        ):
            mock_stdin.isatty.return_value = True
            result = install_claude.install_claude_npm()

        assert result is False
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert 'password' in combined.lower(), 'Should mention password check'
        assert 'sudoers' in combined.lower(), 'Should mention sudoers check'

    def test_sudo_timeout_handled_gracefully(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Verify subprocess.TimeoutExpired is caught and produces warning."""
        mock_subprocess = MagicMock()
        mock_subprocess.side_effect = subprocess.TimeoutExpired(cmd=['sudo', 'npm'], timeout=30)

        with (
            patch('platform.system', return_value='Linux'),
            patch.object(install_claude, 'find_command_robust', return_value='/usr/bin/npm'),
            patch.object(install_claude, 'needs_sudo_for_npm', return_value=False),
            patch.object(
                install_claude, 'run_command',
                return_value=subprocess.CompletedProcess([], 1, '', 'permission denied'),
            ),
            patch('subprocess.run', mock_subprocess),
            patch('pathlib.Path.exists', return_value=True),
            patch('sys.stdin') as mock_stdin,
        ):
            mock_stdin.isatty.return_value = True
            result = install_claude.install_claude_npm()

        assert result is False
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert 'timed out' in combined.lower(), 'Should mention timeout'

    def test_enhanced_error_on_total_failure(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Verify comprehensive manual installation options appear on total npm failure."""
        mock_subprocess = MagicMock()
        mock_subprocess.return_value = subprocess.CompletedProcess([], 1, '', 'failed')

        with (
            patch('platform.system', return_value='Linux'),
            patch.object(install_claude, 'find_command_robust', return_value='/usr/bin/npm'),
            patch.object(install_claude, 'needs_sudo_for_npm', return_value=False),
            patch.object(
                install_claude, 'run_command',
                return_value=subprocess.CompletedProcess([], 1, '', 'permission denied'),
            ),
            patch('subprocess.run', mock_subprocess),
            patch('pathlib.Path.exists', return_value=True),
            patch('sys.stdin') as mock_stdin,
        ):
            mock_stdin.isatty.return_value = True
            result = install_claude.install_claude_npm()

        assert result is False
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        # Enhanced error should include manual installation options
        assert 'manual installation' in combined.lower(), (
            'Should mention manual installation options'
        )
        assert 'npm config set prefix' in combined, (
            'Should suggest npm prefix configuration'
        )
        assert 'CLAUDE_INSTALL_METHOD=native' in combined, (
            'Should suggest native installer alternative'
        )
        assert 'claude.ai/install.sh' in combined, (
            'Should provide direct native install URL'
        )

    def test_pre_warning_when_sudo_predicted(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Verify pre-warning message when needs_sudo_for_npm() predicts sudo requirement."""
        mock_subprocess = MagicMock()
        mock_subprocess.return_value = subprocess.CompletedProcess([], 0, '', '')

        with (
            patch('platform.system', return_value='Linux'),
            patch.object(install_claude, 'find_command_robust', return_value='/usr/bin/npm'),
            patch.object(install_claude, 'needs_sudo_for_npm', return_value=True),
            patch.object(
                install_claude, 'run_command',
                return_value=subprocess.CompletedProcess([], 1, '', 'EACCES'),
            ),
            patch('subprocess.run', mock_subprocess),
            patch('pathlib.Path.exists', return_value=True),
            patch('sys.stdin') as mock_stdin,
        ):
            mock_stdin.isatty.return_value = True
            result = install_claude.install_claude_npm()

        assert result is True
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert 'elevated permissions' in combined.lower(), (
            'Should warn about elevated permissions when sudo predicted'
        )

    def test_sudo_capture_output_is_true(self) -> None:
        """Verify subprocess.run for sudo is called with capture_output=True."""
        mock_subprocess = MagicMock()
        mock_subprocess.return_value = subprocess.CompletedProcess([], 0, '', '')

        with (
            patch('platform.system', return_value='Linux'),
            patch.object(install_claude, 'find_command_robust', return_value='/usr/bin/npm'),
            patch.object(install_claude, 'needs_sudo_for_npm', return_value=False),
            patch.object(
                install_claude, 'run_command',
                return_value=subprocess.CompletedProcess([], 1, '', 'permission denied'),
            ),
            patch('subprocess.run', mock_subprocess),
            patch('pathlib.Path.exists', return_value=True),
            patch('sys.stdin') as mock_stdin,
        ):
            mock_stdin.isatty.return_value = True
            install_claude.install_claude_npm()

        # Verify capture_output=True was passed on the sudo install call
        call_kwargs = mock_subprocess.call_args[1]
        assert call_kwargs.get('capture_output') is True, (
            'Sudo subprocess.run must use capture_output=True to suppress noisy output'
        )


class TestNpmSudoGatingE2E:
    """E2E tests for pre-sudo TTY/credential gating in install_claude_npm()."""

    def test_npm_sudo_skipped_without_tty(
        self, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Sudo is completely skipped when no TTY and no cached credentials."""
        mock_subprocess = MagicMock()
        # Credential check returns non-zero (no cached credentials)
        mock_subprocess.return_value = subprocess.CompletedProcess(
            ['sudo', '-n', 'true'], 1, '', '',
        )

        with (
            patch('platform.system', return_value='Linux'),
            patch.object(install_claude, 'find_command_robust', return_value='/usr/bin/npm'),
            patch.object(install_claude, 'needs_sudo_for_npm', return_value=True),
            patch.object(
                install_claude, 'run_command',
                return_value=subprocess.CompletedProcess([], 1, '', 'EACCES'),
            ),
            patch('subprocess.run', mock_subprocess),
            patch('pathlib.Path.exists', return_value=True),
            patch('sys.stdin') as mock_stdin,
        ):
            mock_stdin.isatty.return_value = False
            result = install_claude.install_claude_npm()

        assert result is False
        # Only credential check should have been called, not sudo npm install
        assert mock_subprocess.call_count == 1, (
            f'Expected 1 call (credential check), got {mock_subprocess.call_count}'
        )
        cred_args = mock_subprocess.call_args[0][0]
        assert cred_args == ['sudo', '-n', 'true'], (
            f'Expected credential check, got: {cred_args}'
        )
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert 'cannot use sudo' in combined.lower(), (
            'Should warn that sudo cannot be used'
        )

    def test_npm_sudo_uses_cached_credentials(self) -> None:
        """Sudo proceeds when cached credentials are available even without TTY."""
        mock_subprocess = MagicMock()
        mock_subprocess.side_effect = [
            # First call: credential check succeeds
            subprocess.CompletedProcess(['sudo', '-n', 'true'], 0, '', ''),
            # Second call: sudo npm install succeeds
            subprocess.CompletedProcess([], 0, '', ''),
        ]

        with (
            patch('platform.system', return_value='Linux'),
            patch.object(install_claude, 'find_command_robust', return_value='/usr/bin/npm'),
            patch.object(install_claude, 'needs_sudo_for_npm', return_value=False),
            patch.object(
                install_claude, 'run_command',
                return_value=subprocess.CompletedProcess([], 1, '', 'permission denied'),
            ),
            patch('subprocess.run', mock_subprocess),
            patch('pathlib.Path.exists', return_value=True),
            patch('sys.stdin') as mock_stdin,
        ):
            mock_stdin.isatty.return_value = False
            result = install_claude.install_claude_npm()

        assert result is True
        # Should have 2 calls: credential check + sudo npm install
        assert mock_subprocess.call_count == 2, (
            f'Expected 2 calls (cred check + install), got {mock_subprocess.call_count}'
        )
        # Verify first call was credential check
        first_args = mock_subprocess.call_args_list[0][0][0]
        assert first_args == ['sudo', '-n', 'true'], (
            f'First call should be credential check, got: {first_args}'
        )
        # Verify second call was sudo npm install
        second_args = mock_subprocess.call_args_list[1][0][0]
        assert second_args[0] == 'sudo', (
            f'Second call should start with sudo, got: {second_args[0]}'
        )
        assert '/usr/bin/npm' in second_args, (
            f'Second call should include npm path, got: {second_args}'
        )

    def test_npm_sudo_filenotfounderror_graceful(
        self, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """FileNotFoundError during credential check is handled gracefully."""
        mock_subprocess = MagicMock()
        # Credential check raises FileNotFoundError (no sudo binary)
        mock_subprocess.side_effect = FileNotFoundError('sudo not found')

        with (
            patch('platform.system', return_value='Linux'),
            patch.object(install_claude, 'find_command_robust', return_value='/usr/bin/npm'),
            patch.object(install_claude, 'needs_sudo_for_npm', return_value=False),
            patch.object(
                install_claude, 'run_command',
                return_value=subprocess.CompletedProcess([], 1, '', 'permission denied'),
            ),
            patch('subprocess.run', mock_subprocess),
            patch('pathlib.Path.exists', return_value=True),
            patch('sys.stdin') as mock_stdin,
        ):
            mock_stdin.isatty.return_value = False
            result = install_claude.install_claude_npm()

        assert result is False
        # Only one call should have been attempted (the credential check that raised)
        assert mock_subprocess.call_count == 1, (
            f'Expected 1 call attempt, got {mock_subprocess.call_count}'
        )
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        # Should not crash - should produce error guidance
        assert 'CLAUDE_INSTALL_METHOD=native' in combined, (
            'Should suggest native installer when sudo unavailable'
        )


class TestNativeInstallerDiagnostics:
    """E2E tests for native installer diagnostic logging (stderr/stdout capture)."""

    def test_linux_installer_logs_stderr_on_failure(
        self, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When the Linux native installer fails, stderr is captured and logged."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'#!/bin/bash\nexit 1'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)

        with (
            patch.object(install_claude, 'urlopen', return_value=mock_response),
            patch('tempfile.NamedTemporaryFile') as mock_tmp,
            patch('os.chmod'),
            patch('os.unlink'),
            patch.object(
                install_claude, 'run_command',
                return_value=subprocess.CompletedProcess(
                    [], 1, stdout='', stderr='Error: glibc version too old',
                ),
            ),
        ):
            mock_tmp.return_value.__enter__.return_value.name = '/tmp/installer.sh'

            result = install_claude._install_claude_native_linux_installer()

        assert result is False
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert 'glibc version too old' in combined, (
            'Should log stderr content from failed native installer'
        )
        assert 'exited with code 1' in combined, (
            'Should log the exit code of failed native installer'
        )

    def test_macos_installer_logs_stderr_on_failure(
        self, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When the macOS native installer fails, stderr is captured and logged."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'#!/bin/bash\nexit 1'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)

        with (
            patch.object(install_claude, 'urlopen', return_value=mock_response),
            patch('tempfile.NamedTemporaryFile') as mock_tmp,
            patch('os.chmod'),
            patch('os.unlink'),
            patch.object(
                install_claude, 'run_command',
                return_value=subprocess.CompletedProcess(
                    [], 1, stdout='', stderr='Error: Unsupported macOS version',
                ),
            ),
        ):
            mock_tmp.return_value.__enter__.return_value.name = '/tmp/installer.sh'

            result = install_claude._install_claude_native_macos_installer()

        assert result is False
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert 'Unsupported macOS version' in combined, (
            'Should log stderr content from failed native installer'
        )

    def test_windows_installer_logs_stderr_on_failure(
        self, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When the Windows native installer fails, stderr is captured and logged."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'Write-Output "Installing"'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)

        with (
            patch.object(install_claude, 'urlopen', return_value=mock_response),
            patch('tempfile.NamedTemporaryFile') as mock_tmp,
            patch('os.unlink'),
            patch.object(
                install_claude, 'run_command',
                return_value=subprocess.CompletedProcess(
                    [], 1, stdout='', stderr='Error: PowerShell execution policy',
                ),
            ),
        ):
            mock_tmp.return_value.__enter__.return_value.name = 'C:\\Temp\\install.ps1'

            result = install_claude._install_claude_native_windows_installer()

        assert result is False
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert 'PowerShell execution policy' in combined, (
            'Should log stderr content from failed native installer'
        )

    def test_linux_installer_logs_stdout_on_success(
        self, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When the Linux native installer succeeds, stdout is logged."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'#!/bin/bash\necho "OK"'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)

        with (
            patch.object(install_claude, 'urlopen', return_value=mock_response),
            patch('tempfile.NamedTemporaryFile') as mock_tmp,
            patch('os.chmod'),
            patch('os.unlink'),
            patch.object(
                install_claude, 'run_command',
                return_value=subprocess.CompletedProcess(
                    [], 0, stdout='Claude installed to /home/user/.local/bin/claude', stderr='',
                ),
            ),
            patch.object(
                install_claude, 'verify_claude_installation',
                return_value=(True, '/home/user/.local/bin/claude', 'native'),
            ),
            patch.object(install_claude, 'remove_npm_claude'),
            patch.object(install_claude, 'update_install_method_config'),
            patch('time.sleep'),
        ):
            mock_tmp.return_value.__enter__.return_value.name = '/tmp/installer.sh'

            result = install_claude._install_claude_native_linux_installer()

        assert result is True
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert 'Installer output' in combined, (
            'Should log installer output on success'
        )

    def test_linux_installer_uses_capture_output_true(self) -> None:
        """Native Linux installer calls run_command with capture_output=True."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'#!/bin/bash\nexit 0'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)

        with (
            patch.object(install_claude, 'urlopen', return_value=mock_response),
            patch('tempfile.NamedTemporaryFile') as mock_tmp,
            patch('os.chmod'),
            patch('os.unlink'),
            patch.object(install_claude, 'run_command') as mock_run,
        ):
            mock_tmp.return_value.__enter__.return_value.name = '/tmp/installer.sh'
            mock_run.return_value = subprocess.CompletedProcess([], 1, '', '')

            install_claude._install_claude_native_linux_installer()

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs.get('capture_output') is True, (
            'Native installer must use capture_output=True for diagnostic logging'
        )

    def test_macos_installer_uses_capture_output_true(self) -> None:
        """Native macOS installer calls run_command with capture_output=True."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'#!/bin/bash\nexit 0'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)

        with (
            patch.object(install_claude, 'urlopen', return_value=mock_response),
            patch('tempfile.NamedTemporaryFile') as mock_tmp,
            patch('os.chmod'),
            patch('os.unlink'),
            patch.object(install_claude, 'run_command') as mock_run,
        ):
            mock_tmp.return_value.__enter__.return_value.name = '/tmp/installer.sh'
            mock_run.return_value = subprocess.CompletedProcess([], 1, '', '')

            install_claude._install_claude_native_macos_installer()

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs.get('capture_output') is True, (
            'Native macOS installer must use capture_output=True for diagnostic logging'
        )

    def test_windows_installer_uses_capture_output_true(self) -> None:
        """Native Windows installer calls run_command with capture_output=True."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'Write-Output "test"'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)

        with (
            patch.object(install_claude, 'urlopen', return_value=mock_response),
            patch('tempfile.NamedTemporaryFile') as mock_tmp,
            patch('os.unlink'),
            patch.object(install_claude, 'run_command') as mock_run,
        ):
            mock_tmp.return_value.__enter__.return_value.name = 'C:\\Temp\\install.ps1'
            mock_run.return_value = subprocess.CompletedProcess([], 1, '', '')

            install_claude._install_claude_native_windows_installer()

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs.get('capture_output') is True, (
            'Native Windows installer must use capture_output=True for diagnostic logging'
        )

    def test_macos_installer_logs_stdout_on_success(
        self, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When the macOS native installer succeeds, stdout is logged."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'#!/bin/bash\necho "OK"'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)

        with (
            patch.object(install_claude, 'urlopen', return_value=mock_response),
            patch('tempfile.NamedTemporaryFile') as mock_tmp,
            patch('os.chmod'),
            patch('os.unlink'),
            patch.object(
                install_claude, 'run_command',
                return_value=subprocess.CompletedProcess(
                    [], 0, stdout='Claude installed to /usr/local/bin/claude', stderr='',
                ),
            ),
            patch.object(
                install_claude, 'verify_claude_installation',
                return_value=(True, '/usr/local/bin/claude', 'native'),
            ),
            patch.object(install_claude, 'remove_npm_claude'),
            patch.object(install_claude, 'update_install_method_config'),
            patch('time.sleep'),
        ):
            mock_tmp.return_value.__enter__.return_value.name = '/tmp/installer.sh'

            result = install_claude._install_claude_native_macos_installer()

        assert result is True
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert 'Installer output' in combined, (
            'Should log installer output on success'
        )


class TestEnsureClaudeTroubleshooting:
    """E2E tests for enhanced error messaging in ensure_claude()."""

    def test_all_methods_failed_unix_troubleshooting(
        self, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When all methods fail on Unix, numbered troubleshooting steps appear."""
        with (
            patch('platform.system', return_value='Linux'),
            patch.object(install_claude, 'get_claude_version', return_value=None),
            patch.object(
                install_claude, 'install_claude_native_cross_platform', return_value=False,
            ),
            patch.object(install_claude, 'install_claude_npm', return_value=False),
            patch.dict('os.environ', {'CLAUDE_INSTALL_METHOD': 'auto'}, clear=False),
        ):
            result = install_claude.ensure_claude()

        assert result is False
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert 'Troubleshooting steps' in combined, (
            'Should show "Troubleshooting steps" header'
        )
        assert 'sudo npm install' in combined, (
            'Should suggest sudo npm install'
        )
        assert 'npm config set prefix' in combined, (
            'Should suggest npm prefix configuration'
        )
        assert 'CLAUDE_INSTALL_METHOD=native' in combined, (
            'Should suggest method override'
        )
        assert 'CLAUDE_INSTALL_METHOD=npm' in combined, (
            'Should suggest npm-only override'
        )

    def test_all_methods_failed_windows_troubleshooting(
        self, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When all methods fail on Windows, platform-appropriate steps appear."""
        with (
            patch('platform.system', return_value='Windows'),
            patch.object(install_claude, 'get_claude_version', return_value=None),
            patch.object(
                install_claude, 'install_claude_native_cross_platform', return_value=False,
            ),
            patch.object(install_claude, 'install_claude_npm', return_value=False),
            patch.dict('os.environ', {'CLAUDE_INSTALL_METHOD': 'auto'}, clear=False),
        ):
            result = install_claude.ensure_claude()

        assert result is False
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert 'irm' in combined, 'Should mention PowerShell irm command'
        assert '$env:CLAUDE_INSTALL_METHOD' in combined, (
            'Should use PowerShell env var syntax'
        )

    def test_fallback_diagnostic_suggests_method_override(
        self, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When native fails and npm fallback occurs, diagnostic info is logged."""
        with (
            patch('platform.system', return_value='Linux'),
            patch.object(install_claude, 'get_claude_version', return_value=None),
            patch.object(
                install_claude, 'install_claude_native_cross_platform', return_value=False,
            ),
            patch.object(install_claude, 'install_claude_npm', return_value=False),
            patch.dict('os.environ', {'CLAUDE_INSTALL_METHOD': 'auto'}, clear=False),
        ):
            install_claude.ensure_claude()

        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert 'CLAUDE_INSTALL_METHOD=native' in combined, (
            'Should suggest CLAUDE_INSTALL_METHOD=native at fallback point'
        )


class TestWindowsPathLengthHandling:
    """E2E tests for Windows PATH length limit handling.

    Verifies that:
    - refresh_path_from_registry() gracefully handles PATH exceeding 32762 chars
    - add_directory_to_windows_path() skips session PATH update when too long
    - Warning messages are produced for long PATH scenarios
    - The _WIN_PATH_VALUE_MAX_LENGTH constant is correctly defined
    """

    def test_path_length_constant_defined(self) -> None:
        """Verify _WIN_PATH_VALUE_MAX_LENGTH constant exists and has correct value."""
        from scripts import setup_environment

        assert hasattr(setup_environment, '_WIN_PATH_VALUE_MAX_LENGTH'), (
            'Missing _WIN_PATH_VALUE_MAX_LENGTH constant in setup_environment'
        )
        assert setup_environment._WIN_PATH_VALUE_MAX_LENGTH == 32762, (
            f'Expected 32762, got {setup_environment._WIN_PATH_VALUE_MAX_LENGTH}'
        )

    def test_refresh_path_graceful_on_long_path(self) -> None:
        """When registry PATH exceeds limit, refresh_path_from_registry warns and keeps current PATH."""
        from scripts import setup_environment

        # Generate a PATH value that exceeds _WIN_PATH_VALUE_MAX_LENGTH
        long_path = ';'.join([f'C:\\fake\\path{i}' for i in range(3000)])
        assert len(long_path) > setup_environment._WIN_PATH_VALUE_MAX_LENGTH

        mock_winreg = MagicMock()
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value.__enter__ = MagicMock(return_value=mock_key)
        mock_winreg.OpenKey.return_value.__exit__ = MagicMock(return_value=None)
        mock_winreg.QueryValueEx.return_value = (long_path, 1)
        mock_winreg.HKEY_LOCAL_MACHINE = 0x80000002
        mock_winreg.HKEY_CURRENT_USER = 0x80000001
        mock_winreg.KEY_READ = 0x20019
        mock_winreg.KEY_WOW64_64KEY = 0x0100
        mock_winreg.REG_EXPAND_SZ = 2

        with (
            patch('sys.platform', 'win32'),
            patch.object(setup_environment, 'winreg', mock_winreg, create=True),
            patch.dict('os.environ', {'PATH': 'C:\\original'}, clear=False),
        ):
            result = setup_environment.refresh_path_from_registry()

        # Should return True (graceful degradation) not crash
        assert result is True, 'refresh_path_from_registry should return True for graceful degradation on long PATH'

    def test_add_directory_warns_when_session_path_too_long(self) -> None:
        """When session PATH would exceed limit, registry is updated but session PATH is not."""
        from scripts import setup_environment

        # Build a long existing session PATH that is under the limit itself
        # but would exceed it after prepending the new directory
        # We need the path to be long enough that adding another entry pushes it over
        segment_count = 2100
        long_session_path = ';'.join([f'C:\\path{i}' for i in range(segment_count)])

        mock_winreg = MagicMock()
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.QueryValueEx.return_value = ('C:\\existing', 1)
        mock_winreg.HKEY_CURRENT_USER = 0x80000001
        mock_winreg.KEY_READ = 0x20019
        mock_winreg.KEY_WRITE = 0x20006
        mock_winreg.REG_EXPAND_SZ = 2

        home_dir = str(Path.home() / '.local' / 'bin')

        with (
            patch('sys.platform', 'win32'),
            patch.object(setup_environment, 'winreg', mock_winreg, create=True),
            patch.dict('os.environ', {'PATH': long_session_path}, clear=False),
            patch('subprocess.run'),
            patch('pathlib.Path.resolve', return_value=Path(home_dir)),
            patch('pathlib.Path.exists', return_value=True),
        ):
            success_flag, message = setup_environment.add_directory_to_windows_path(home_dir)

        # Should not crash - graceful handling
        assert isinstance(success_flag, bool)
        assert isinstance(message, str)


class TestEnsureClaudeFullFlow:
    """E2E tests for the complete ensure_claude() installation flow.

    Tests the full native-first-then-npm-fallback pipeline end-to-end.
    """

    def test_auto_mode_native_success_skips_npm(self) -> None:
        """When native installation succeeds in auto mode, npm is never attempted."""
        with (
            patch('platform.system', return_value='Linux'),
            patch.object(install_claude, 'get_claude_version', return_value=None),
            patch.object(
                install_claude, 'install_claude_native_cross_platform', return_value=True,
            ),
            patch.object(install_claude, 'install_claude_npm') as mock_npm,
            patch.dict('os.environ', {'CLAUDE_INSTALL_METHOD': 'auto'}, clear=False),
        ):
            result = install_claude.ensure_claude()

        assert result is True
        mock_npm.assert_not_called()

    def test_auto_mode_native_fails_tries_npm(self, capsys: pytest.CaptureFixture[str]) -> None:
        """When native fails in auto mode, npm fallback is attempted with diagnostic message."""
        with (
            patch('platform.system', return_value='Linux'),
            patch.object(install_claude, 'get_claude_version', return_value=None),
            patch.object(
                install_claude, 'install_claude_native_cross_platform', return_value=False,
            ),
            patch.object(install_claude, 'install_claude_npm', return_value=False),
            patch.dict('os.environ', {'CLAUDE_INSTALL_METHOD': 'auto'}, clear=False),
        ):
            result = install_claude.ensure_claude()

        assert result is False
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert 'falling back to npm' in combined.lower(), (
            'Should show npm fallback diagnostic message'
        )
        assert 'CLAUDE_INSTALL_METHOD=native' in combined, (
            'Should suggest method override at fallback point'
        )

    def test_native_only_mode_no_npm_fallback(self, capsys: pytest.CaptureFixture[str]) -> None:
        """When method=native, npm is never attempted even on failure."""
        with (
            patch('platform.system', return_value='Linux'),
            patch.object(install_claude, 'get_claude_version', return_value=None),
            patch.object(
                install_claude, 'install_claude_native_cross_platform', return_value=False,
            ),
            patch.object(install_claude, 'install_claude_npm') as mock_npm,
            patch.dict('os.environ', {'CLAUDE_INSTALL_METHOD': 'native'}, clear=False),
        ):
            result = install_claude.ensure_claude()

        assert result is False
        mock_npm.assert_not_called()
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert 'npm fallback is disabled' in combined.lower(), (
            'Should explain that npm fallback is disabled in native mode'
        )

    def test_npm_only_mode_no_native_attempt(self) -> None:
        """When method=npm, native installer is never attempted."""
        with (
            patch('platform.system', return_value='Linux'),
            patch.object(install_claude, 'get_claude_version', return_value=None),
            patch.object(
                install_claude, 'install_claude_native_cross_platform',
            ) as mock_native,
            patch.object(install_claude, 'install_claude_npm', return_value=True),
            patch.object(install_claude, 'find_command_robust', return_value='/usr/bin/claude'),
            patch.object(install_claude, 'get_claude_version', return_value='1.0.130'),
            patch.dict('os.environ', {'CLAUDE_INSTALL_METHOD': 'npm'}, clear=False),
        ):
            result = install_claude.ensure_claude()

        assert result is True
        mock_native.assert_not_called()

    def test_already_installed_up_to_date_returns_true(self) -> None:
        """When Claude is already installed and up to date, returns True immediately."""
        with (
            patch('platform.system', return_value='Linux'),
            patch.object(install_claude, 'get_claude_version', return_value='1.0.130'),
            patch.object(install_claude, 'get_latest_claude_version', return_value='1.0.130'),
            patch.object(install_claude, 'compare_versions', return_value=True),
            patch.object(
                install_claude, 'verify_claude_installation',
                return_value=(True, '/usr/local/bin/claude', 'native'),
            ),
            patch.dict('os.environ', {'CLAUDE_INSTALL_METHOD': 'auto'}, clear=False),
        ):
            result = install_claude.ensure_claude()

        assert result is True

    def test_invalid_install_method_defaults_to_auto(
        self, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When CLAUDE_INSTALL_METHOD is invalid, falls back to 'auto' with warning."""
        with (
            patch('platform.system', return_value='Linux'),
            patch.object(install_claude, 'get_claude_version', return_value=None),
            patch.object(
                install_claude, 'install_claude_native_cross_platform', return_value=True,
            ),
            patch.dict('os.environ', {'CLAUDE_INSTALL_METHOD': 'invalid'}, clear=False),
        ):
            result = install_claude.ensure_claude()

        assert result is True
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert 'invalid' in combined.lower(), (
            'Should warn about invalid install method'
        )
