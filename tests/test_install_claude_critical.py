"""Critical missing test coverage for install_claude.py focusing on SSL errors and edge cases."""

import subprocess
import sys
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

# Add parent directory to path so we can import scripts
sys.path.insert(0, str(Path(__file__).parent.parent))

import scripts.install_claude as install_claude


class TestSSLErrorHandling:
    """Test SSL certificate error handling in various functions."""

    @patch('scripts.install_claude.get_git_installer_url_from_github', return_value=None)
    @patch('scripts.install_claude.ssl.create_default_context')
    @patch('scripts.install_claude.urlopen')
    def test_install_git_windows_download_ssl_error(self, mock_urlopen, mock_ssl_context, mock_github):
        """Test Git for Windows download with SSL certificate error."""
        # First urlopen raises SSL error, second succeeds
        ssl_error = urllib.error.URLError('SSL: CERTIFICATE_VERIFY_FAILED')

        # Create mock response with HTML containing Git installer link
        mock_response = MagicMock()
        mock_response.read.return_value = b'<a href="https://github.com/git-for-windows/Git-2.43.0-64-bit.exe">'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)

        mock_urlopen.side_effect = [
            ssl_error,  # First attempt fails with SSL
            mock_response,  # Retry succeeds
        ]

        # Mock SSL context
        mock_ctx = MagicMock()
        mock_ssl_context.return_value = mock_ctx

        # Mock the installer download and execution
        with (
            patch('scripts.install_claude.urlretrieve'),
            patch('scripts.install_claude.run_command') as mock_run,
            patch('scripts.install_claude.os.unlink'),
            patch('scripts.install_claude.tempfile.NamedTemporaryFile') as mock_temp,
        ):
            mock_temp.return_value.__enter__.return_value.name = 'temp.exe'
            mock_run.return_value = subprocess.CompletedProcess([], 0)

            result = install_claude.install_git_windows_download()

            assert result is True
            # Verify GitHub API was tried first
            mock_github.assert_called_once()
            assert mock_ssl_context.called
            assert mock_ctx.check_hostname is False
            assert mock_ctx.verify_mode == 0  # ssl.CERT_NONE
            # Verify urlopen was called with unverified context
            assert mock_urlopen.call_count == 2

    @patch('scripts.install_claude.urllib.request.install_opener')
    @patch('scripts.install_claude.urllib.request.build_opener')
    @patch('scripts.install_claude.ssl.create_default_context')
    @patch('scripts.install_claude.urlretrieve')
    @patch('scripts.install_claude.urlopen')
    def test_install_git_windows_download_urlretrieve_ssl_error(
        self,
        mock_urlopen,
        mock_urlretrieve,
        mock_ssl_context,
        mock_build_opener,
        mock_install_opener,
    ):
        """Test Git installer download with SSL error during urlretrieve."""
        # Create proper mock response for urlopen
        mock_response = MagicMock()
        mock_response.read.return_value = b'<a href="https://github.com/git-for-windows/Git-2.43.0-64-bit.exe">'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)
        mock_urlopen.return_value = mock_response

        # urlretrieve raises SSL error on first attempt
        ssl_error = urllib.error.URLError('certificate verify failed')
        mock_urlretrieve.side_effect = [
            ssl_error,  # First attempt fails
            None,  # Second attempt succeeds
        ]

        # Mock SSL context
        mock_ctx = MagicMock()
        mock_ssl_context.return_value = mock_ctx

        with (
            patch('scripts.install_claude.run_command') as mock_run,
            patch('scripts.install_claude.os.unlink'),
            patch('scripts.install_claude.tempfile.NamedTemporaryFile') as mock_temp,
        ):
            mock_temp.return_value.__enter__.return_value.name = 'temp.exe'
            mock_run.return_value = subprocess.CompletedProcess([], 0)

            result = install_claude.install_git_windows_download()

            assert result is True
            assert mock_ssl_context.called
            assert mock_build_opener.called
            assert mock_install_opener.called
            # urlretrieve called twice (once failed, once succeeded)
            assert mock_urlretrieve.call_count == 2

    @patch('scripts.install_claude.json.loads')
    @patch('scripts.install_claude.ssl.create_default_context')
    @patch('scripts.install_claude.urlopen')
    def test_install_nodejs_direct_ssl_error(self, mock_urlopen, mock_ssl_context, mock_json_loads):
        """Test Node.js direct installation with SSL certificate error."""
        # First urlopen raises SSL error
        ssl_error = urllib.error.URLError('SSL handshake failed')
        mock_urlopen.side_effect = [
            ssl_error,  # First attempt fails
            MagicMock(read=lambda: b'[{"version": "v20.10.0", "lts": "Iron"}]'),  # Retry succeeds
        ]

        # Mock SSL context
        mock_ctx = MagicMock()
        mock_ssl_context.return_value = mock_ctx

        mock_json_loads.return_value = [{'version': 'v20.10.0', 'lts': 'Iron'}]

        with (
            patch('scripts.install_claude.platform.system', return_value='Darwin'),
            patch('scripts.install_claude.platform.machine', return_value='arm64'),
            patch('scripts.install_claude.urlretrieve'),
            patch('scripts.install_claude.run_command') as mock_run,
            patch('scripts.install_claude.os.unlink'),
            patch('scripts.install_claude.tempfile.NamedTemporaryFile') as mock_temp,
        ):
            mock_temp.return_value.__enter__.return_value.name = 'temp.pkg'
            mock_run.return_value = subprocess.CompletedProcess([], 0)

            result = install_claude.install_nodejs_direct()

            assert result is True
            assert mock_ssl_context.called
            assert mock_ctx.check_hostname is False
            assert mock_urlopen.call_count == 2

    @patch('scripts.install_claude.ssl.create_default_context')
    @patch('scripts.install_claude.urlopen')
    @patch('scripts.install_claude.verify_claude_installation')
    @patch('scripts.install_claude.ensure_local_bin_in_path_windows')
    def test_install_claude_native_ssl_error(
        self, mock_ensure_path, mock_verify, mock_urlopen, mock_ssl_context,
    ):
        """Test Claude native installer with SSL certificate error."""
        with patch('scripts.install_claude.platform.system', return_value='Windows'):
            # First urlopen raises SSL error
            ssl_error = urllib.error.URLError('CERTIFICATE_VERIFY_FAILED')
            mock_urlopen.side_effect = [
                ssl_error,  # First attempt fails
                MagicMock(read=lambda: b'# PowerShell installer script'),  # Retry succeeds
            ]

            # Mock SSL context
            mock_ctx = MagicMock()
            mock_ssl_context.return_value = mock_ctx

            # Mock the new verification and PATH functions
            mock_verify.return_value = (True, 'C:\\Users\\Test\\.local\\bin\\claude.exe', 'native')
            mock_ensure_path.return_value = True

            with (
                patch('scripts.install_claude.run_command') as mock_run,
                patch('scripts.install_claude.os.unlink'),
                patch('scripts.install_claude.tempfile.NamedTemporaryFile') as mock_temp,
            ):
                mock_temp.return_value.__enter__.return_value.name = 'temp.ps1'
                mock_temp.return_value.__enter__.return_value.write = MagicMock()
                mock_run.return_value = subprocess.CompletedProcess([], 0)

                result = install_claude.install_claude_native_windows()

                assert result is True
                assert mock_ssl_context.called
                assert mock_ctx.verify_mode == 0
                assert mock_urlopen.call_count == 2


class TestWindowsEnvVar:
    """Test Windows environment variable setting."""

    @patch('scripts.install_claude.platform.system', return_value='Windows')
    @patch('scripts.install_claude.run_command')
    def test_set_windows_env_var_success(self, mock_run, mock_system):
        """Test successful setting of Windows environment variable."""
        del mock_system  # Mark as intentionally unused
        mock_run.return_value = subprocess.CompletedProcess([], 0)

        install_claude.set_windows_env_var('TEST_VAR', 'test_value')

        # Check that setx was called
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert call_args == ['setx', 'TEST_VAR', 'test_value']
        assert mock_run.call_args[1]['capture_output'] is False

    @patch('scripts.install_claude.platform.system', return_value='Windows')
    @patch('scripts.install_claude.run_command')
    def test_set_windows_env_var_exception(self, mock_run, mock_system):
        """Test exception handling when setting Windows environment variable."""
        del mock_system  # Mark as intentionally unused
        mock_run.side_effect = Exception('Access denied')

        # Should not raise, just warn
        install_claude.set_windows_env_var('TEST_VAR', 'test_value')

        assert mock_run.called


class TestNodeInstallationEdgeCases:
    """Test edge cases in Node.js installation."""

    @patch('scripts.install_claude.Path')
    @patch('scripts.install_claude.platform.system', return_value='Windows')
    def test_ensure_nodejs_windows_path_update(self, mock_system, mock_path):
        """Test Node.js path update on Windows when found in Program Files."""
        del mock_system  # Mark as intentionally unused

        # Mock Path existence check
        mock_nodejs_path = MagicMock()
        mock_nodejs_path.exists.return_value = True
        mock_path.return_value = mock_nodejs_path

        # Save original PATH and set up test environment
        with (
            patch.dict('scripts.install_claude.os.environ', {'PATH': 'C:\\Windows\\System32'}),
            patch('scripts.install_claude.get_node_version', return_value='v20.10.0'),
            patch('scripts.install_claude.compare_versions', return_value=True),
        ):
            result = install_claude.ensure_nodejs()

            assert result is True
            # Check that PATH was updated
            assert 'C:\\Program Files\\nodejs' in install_claude.os.environ.get('PATH', '')

    @patch('scripts.install_claude.install_nodejs_apt')
    @patch('scripts.install_claude.Path')
    @patch('scripts.install_claude.platform.system', return_value='Linux')
    @patch('scripts.install_claude.get_node_version')
    @patch('scripts.install_claude.compare_versions')
    def test_ensure_nodejs_linux_debian(self, mock_compare, mock_get_version, mock_system, mock_path, mock_apt):
        """Test Node.js installation on Debian-based Linux."""
        del mock_system  # Mark as intentionally unused
        # get_node_version is called 3 times: initial check, after apt install, and final check
        mock_get_version.side_effect = [None, 'v20.10.0', 'v20.10.0']  # Not found initially, then found
        mock_compare.return_value = True
        mock_apt.return_value = True

        # Mock /etc/debian_version exists
        mock_debian_path = MagicMock()
        mock_debian_path.exists.return_value = True
        mock_path.return_value = mock_debian_path

        result = install_claude.ensure_nodejs()

        assert result is True
        assert mock_apt.called

    @patch('scripts.install_claude.platform.system', return_value='Linux')
    @patch('scripts.install_claude.get_node_version', return_value=None)
    @patch('scripts.install_claude.Path')
    def test_ensure_nodejs_unsupported_linux(self, mock_path, mock_get_version, mock_system):
        """Test Node.js installation on unsupported Linux distribution."""
        del mock_system, mock_get_version  # Mark as intentionally unused
        # Mock /etc/debian_version doesn't exist
        mock_path.return_value.exists.return_value = False

        result = install_claude.ensure_nodejs()

        assert result is False


class TestClaudeInstallationEdgeCases:
    """Test edge cases in Claude installation."""

    @patch('scripts.install_claude.platform.system', return_value='Windows')
    @patch('scripts.install_claude.Path')
    @patch('scripts.install_claude.find_command', return_value=None)
    def test_get_claude_version_windows_paths(self, mock_find, mock_path, mock_system):
        """Test Claude version detection checking Windows-specific paths."""
        del mock_system, mock_find  # Mark as intentionally unused

        # Mock first path doesn't exist, second path exists
        mock_path_instance = MagicMock()
        mock_path_instance.exists.side_effect = [False, True, False, False]
        mock_path.return_value = mock_path_instance

        with patch('scripts.install_claude.run_command') as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0, 'claude, version 0.7.8', '')

            version = install_claude.get_claude_version()

            assert version == '0.7.8'
            # Check that run_command was called with the found path
            mock_run.assert_called()

    @patch('scripts.install_claude.platform.system', return_value='Windows')
    @patch('scripts.install_claude.Path')
    @patch('scripts.install_claude.find_command')
    def test_install_claude_npm_windows_npm_path(self, mock_find, mock_path, mock_system):
        """Test Claude npm installation finding npm.cmd on Windows."""
        del mock_system  # Mark as intentionally unused
        mock_find.return_value = None  # npm not in PATH

        # Mock npm.cmd exists
        mock_npm_cmd = MagicMock()
        mock_npm_cmd.exists.return_value = True
        mock_path.return_value = mock_npm_cmd

        with patch('scripts.install_claude.run_command') as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0)

            result = install_claude.install_claude_npm(upgrade=True)

            assert result is True
            # Check npm command was called with @latest
            call_args = mock_run.call_args[0][0]
            assert '@anthropic-ai/claude-code@latest' in call_args

    @patch('scripts.install_claude.get_latest_claude_version')
    @patch('scripts.install_claude.get_claude_version')
    def test_ensure_claude_already_installed_no_upgrade(self, mock_get_version, mock_get_latest):
        """Test Claude when already installed and up-to-date (no upgrade attempted)."""
        mock_get_version.return_value = '0.7.8'
        mock_get_latest.return_value = '0.7.8'  # Same version - already up-to-date

        result = install_claude.ensure_claude()

        assert result is True
        # Should check version once and check latest once, but not upgrade
        mock_get_version.assert_called_once()
        mock_get_latest.assert_called_once()

    @patch('scripts.install_claude.platform.system', return_value='Darwin')
    @patch('scripts.install_claude.get_claude_version', return_value=None)
    @patch('scripts.install_claude.install_claude_npm', return_value=False)
    @patch('scripts.install_claude.install_claude_native_cross_platform', return_value=False)
    def test_ensure_claude_all_methods_fail(self, mock_native, mock_npm, mock_get_version, mock_system):
        """Test Claude installation when all methods fail."""
        del mock_native, mock_npm, mock_get_version, mock_system  # Mark as intentionally unused

        result = install_claude.ensure_claude()

        assert result is False


class TestRunCommandEdgeCases:
    """Test edge cases in run_command function."""

    def test_run_command_not_capturing_output(self):
        """Test run_command when not capturing output (shows command)."""
        with patch('scripts.install_claude.subprocess.run') as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(['echo', 'test'], 0, 'test', '')

            result = install_claude.run_command(['echo', 'test'], capture_output=False)

            assert result.returncode == 0
            # Check subprocess.run was called with capture_output=False
            assert mock_run.call_args[1]['capture_output'] is False

    def test_run_command_exception_handling(self):
        """Test run_command handling general exceptions."""
        with patch('scripts.install_claude.subprocess.run') as mock_run:
            mock_run.side_effect = Exception('Unexpected error')

            result = install_claude.run_command(['test_cmd'])

            assert result.returncode == 1
            assert 'Unexpected error' in result.stderr


class TestPowerShellConfiguration:
    """Test PowerShell configuration."""

    @patch('scripts.install_claude.platform.system', return_value='Linux')
    def test_configure_powershell_policy_non_windows(self, mock_system):
        """Test PowerShell configuration skipped on non-Windows."""
        del mock_system  # Mark as intentionally unused
        with patch('scripts.install_claude.run_command') as mock_run:
            install_claude.configure_powershell_policy()

            # Should not be called on Linux
            assert not mock_run.called

    @patch('scripts.install_claude.platform.system', return_value='Windows')
    @patch('scripts.install_claude.run_command')
    def test_configure_powershell_policy_failure(self, mock_run, mock_system):
        """Test PowerShell configuration when command fails."""
        del mock_system  # Mark as intentionally unused
        mock_run.return_value = subprocess.CompletedProcess([], 1, '', 'Access denied')

        # Should not raise, just warn
        install_claude.configure_powershell_policy()

        assert mock_run.called


class TestUpdatePath:
    """Test PATH update functionality."""

    @patch('scripts.install_claude.platform.system', return_value='Linux')
    def test_update_path_non_windows(self, mock_system):
        """Test PATH update skipped on non-Windows."""
        del mock_system  # Mark as intentionally unused
        with patch('scripts.install_claude.os.environ.get') as mock_get:
            install_claude.update_path()

            # Should not modify PATH on Linux
            assert not mock_get.called

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-specific test')
    @patch('scripts.install_claude.platform.system', return_value='Windows')
    @patch('scripts.install_claude.Path')
    def test_update_path_windows_npm_exists(self, mock_path, mock_system):
        """Test PATH update when npm path exists on Windows."""
        del mock_system  # Mark as intentionally unused
        mock_path.return_value.exists.return_value = True

        # Mock os.environ with a test PATH
        test_env = {'PATH': 'C:\\Windows', 'APPDATA': 'C:\\Users\\Test\\AppData\\Roaming'}
        with patch.dict('scripts.install_claude.os.environ', test_env):
            install_claude.update_path()

            # Check PATH was updated
            # The function should have added the npm path to PATH
            assert 'C:\\Users\\Test\\AppData\\Roaming\\npm' in install_claude.os.environ.get('PATH', '')
