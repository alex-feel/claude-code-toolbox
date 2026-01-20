"""
Additional tests for install_claude.py to increase coverage.
"""

import json
import os
import subprocess
import sys
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

import install_claude


class TestErrorHandling:
    """Test error handling scenarios."""

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-specific test')
    @patch('ctypes.windll.shell32.IsUserAnAdmin', side_effect=Exception('ctypes error'))
    @patch('platform.system', return_value='Windows')
    def test_is_admin_windows_exception(self, mock_system, mock_admin):
        """Test admin check on Windows when ctypes fails."""
        # Verify mocks are configured correctly
        assert mock_system.return_value == 'Windows'
        assert mock_admin.side_effect
        assert install_claude.is_admin() is False

    @patch('install_claude.urlopen')
    def test_install_git_windows_download_no_link_found(self, mock_urlopen):
        """Test Git download when no installer link is found."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'<html>No git links here</html>'
        mock_response.__enter__ = lambda _: mock_response
        mock_response.__exit__ = lambda *_: None
        mock_urlopen.return_value = mock_response

        result = install_claude.install_git_windows_download()
        assert result is False

    @patch('install_claude.get_git_installer_url_from_github', return_value=None)
    @patch('install_claude.urlopen')
    def test_install_git_windows_download_ssl_error(self, mock_urlopen, mock_github):
        """Test Git download with SSL error and fallback."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'<a href="/git/Git-2.43.0-64-bit.exe">Download</a>'
        mock_response.__enter__ = lambda _: mock_response
        mock_response.__exit__ = lambda *_: None

        mock_urlopen.side_effect = [
            urllib.error.URLError('SSL: CERTIFICATE_VERIFY_FAILED'),
            mock_response,
        ]

        with patch('install_claude.urlretrieve'), patch('install_claude.run_command') as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')
            result = install_claude.install_git_windows_download()
            assert result is True
            # Verify GitHub API was tried first
            mock_github.assert_called_once()

    @patch('install_claude.urlopen')
    def test_install_git_windows_download_url_error_non_ssl(self, mock_urlopen):
        """Test Git download with non-SSL URL error."""
        mock_urlopen.side_effect = urllib.error.URLError('Connection refused')

        result = install_claude.install_git_windows_download()
        assert result is False

    @patch('install_claude.urlopen')
    @patch('install_claude.urlretrieve')
    def test_install_git_windows_download_retrieve_ssl_error(self, mock_retrieve, mock_urlopen):
        """Test Git download when urlretrieve has SSL error."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'<a href="https://github.com/git/Git-2.43.0-64-bit.exe">Download</a>'
        mock_response.__enter__ = lambda _: mock_response
        mock_response.__exit__ = lambda *_: None
        mock_urlopen.return_value = mock_response

        # First urlretrieve fails with SSL, second succeeds
        mock_retrieve.side_effect = [
            urllib.error.URLError('SSL: CERTIFICATE_VERIFY_FAILED'),
            None,
        ]

        with patch('install_claude.run_command') as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')
            result = install_claude.install_git_windows_download()
            assert result is True

    @patch('install_claude.urlopen')
    @patch('install_claude.urlretrieve')
    def test_install_git_windows_download_installer_fails(self, mock_retrieve, mock_urlopen):
        """Test Git download when installer fails."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'<a href="https://github.com/git/Git-2.43.0-64-bit.exe">Download</a>'
        mock_response.__enter__ = lambda _: mock_response
        mock_response.__exit__ = lambda *_: None
        mock_urlopen.return_value = mock_response

        mock_retrieve.return_value = None

        with patch('install_claude.run_command') as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 1, '', 'Installation failed')
            result = install_claude.install_git_windows_download()
            assert result is False


class TestNodeJsInstallationAdditional:
    """Additional tests for Node.js installation."""

    @patch('install_claude.urlopen')
    def test_install_nodejs_direct_no_lts_version(self, mock_urlopen):
        """Test Node.js installation when no LTS version is found."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps([
            {'version': 'v19.0.0', 'lts': False},
            {'version': 'v18.0.0', 'lts': False},
        ]).encode()
        mock_response.__enter__ = lambda _: mock_response
        mock_response.__exit__ = lambda *_: None
        mock_urlopen.return_value = mock_response

        result = install_claude.install_nodejs_direct()
        assert result is False

    @patch('install_claude.urlopen')
    def test_install_nodejs_direct_api_error(self, mock_urlopen):
        """Test Node.js installation when API call fails."""
        mock_urlopen.side_effect = urllib.error.URLError('Connection error')

        result = install_claude.install_nodejs_direct()
        assert result is False

    @patch('platform.system', return_value='Linux')
    @patch('platform.machine', return_value='x86_64')
    @patch('install_claude.urlopen')
    @patch('install_claude.run_command')
    def test_install_nodejs_direct_linux(self, mock_run, mock_urlopen, mock_machine, mock_system):
        """Test direct Node.js installation on Linux."""
        # Verify platform mocks
        assert mock_system.return_value == 'Linux'
        assert mock_machine.return_value == 'x86_64'

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps([
            {'version': 'v20.10.0', 'lts': 'Iron'},
        ]).encode()
        mock_response.__enter__ = lambda _: mock_response
        mock_response.__exit__ = lambda *_: None
        mock_urlopen.return_value = mock_response

        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        # Linux direct installation is not implemented
        result = install_claude.install_nodejs_direct()
        assert result is False

    @patch('platform.system', return_value='Darwin')
    @patch('platform.machine', return_value='arm64')
    @patch('install_claude.urlopen')
    @patch('install_claude.urlretrieve')
    @patch('install_claude.run_command')
    def test_install_nodejs_direct_macos_arm(self, mock_run, mock_urlretrieve, mock_urlopen, mock_machine, mock_system):
        """Test direct Node.js installation on macOS ARM."""
        # Verify platform mocks
        assert mock_system.return_value == 'Darwin'
        assert mock_machine.return_value == 'arm64'

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps([
            {'version': 'v20.10.0', 'lts': 'Iron'},
        ]).encode()
        mock_response.__enter__ = lambda _: mock_response
        mock_response.__exit__ = lambda *_: None
        mock_urlopen.return_value = mock_response

        # Mock urlretrieve to succeed
        mock_urlretrieve.return_value = None

        # Mock run_command to succeed for the installer
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        result = install_claude.install_nodejs_direct()
        assert result is True


class TestClaudeInstallationAdditional:
    """Additional tests for Claude installation."""

    @patch('install_claude.platform.system', return_value='Linux')
    @patch('install_claude.urlopen')
    @patch('install_claude.run_command')
    @patch('install_claude.verify_claude_installation')
    def test_install_claude_native_linux(self, mock_verify, mock_run, mock_urlopen, mock_platform):
        """Test native Claude installation on Linux with mocked dependencies."""
        # Mock urlopen to return installer script
        mock_response = MagicMock()
        mock_response.read.return_value = b'#!/bin/bash\necho "Installing Claude"'
        mock_response.__enter__ = lambda _: mock_response
        mock_response.__exit__ = lambda *_: None
        mock_urlopen.return_value = mock_response

        # Mock run_command to succeed
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        # Mock verification to succeed
        mock_verify.return_value = (True, '/usr/local/bin/claude', 'native')

        result = install_claude.install_claude_native_linux()
        assert result is True

        # Verify external calls were made
        mock_urlopen.assert_called()
        mock_run.assert_called()
        mock_verify.assert_called()
        mock_platform.assert_called()

    @patch('sys.platform', 'darwin')
    @patch('install_claude.urlopen')
    @patch('install_claude.run_command')
    @patch('install_claude.verify_claude_installation')
    def test_install_claude_native_macos(self, mock_verify, mock_run, mock_urlopen):
        """Test native Claude installation on macOS with mocked dependencies."""
        # Mock urlopen to return installer script
        mock_response = MagicMock()
        mock_response.read.return_value = b'#!/bin/bash\necho "Installing Claude"'
        mock_response.__enter__ = lambda _: mock_response
        mock_response.__exit__ = lambda *_: None
        mock_urlopen.return_value = mock_response

        # Mock run_command to succeed
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        # Mock verification to succeed
        mock_verify.return_value = (True, '/usr/local/bin/claude', 'native')

        result = install_claude.install_claude_native_macos()
        assert result is True

        # Verify external calls were made
        mock_urlopen.assert_called()
        mock_run.assert_called()
        mock_verify.assert_called()

    @patch('install_claude.urlopen')
    def test_install_claude_native_download_error(self, mock_urlopen):
        """Test native Claude installation with download error."""
        mock_urlopen.side_effect = urllib.error.URLError('Connection error')
        result = install_claude.install_claude_native_windows()
        assert result is False


class TestEnsureFunctionsAdditional:
    """Additional tests for ensure functions."""

    @patch('install_claude.find_bash_windows')
    @patch('install_claude.install_git_windows_winget', return_value=False)
    @patch('install_claude.install_git_windows_download', return_value=True)
    @patch('time.sleep')
    def test_ensure_git_bash_windows_fallback_to_download(self, mock_sleep, mock_download, mock_winget, mock_find):
        """Test Git Bash installation fallback to direct download."""
        # Verify mock configurations
        assert mock_winget.return_value is False
        assert mock_download.return_value is True

        mock_find.side_effect = [None, 'C:\\Program Files\\Git\\bin\\bash.exe']
        result = install_claude.ensure_git_bash_windows()
        assert result == 'C:\\Program Files\\Git\\bin\\bash.exe'
        mock_download.assert_called_once()
        mock_sleep.assert_called()

    @patch('install_claude.find_bash_windows', return_value=None)
    @patch('install_claude.install_git_windows_winget', return_value=False)
    @patch('install_claude.install_git_windows_download', return_value=False)
    def test_ensure_git_bash_windows_all_fail(self, mock_download, mock_winget, mock_find):
        """Test Git Bash installation when all methods fail."""
        # Verify all methods are configured to fail
        assert mock_find.return_value is None
        assert mock_winget.return_value is False
        assert mock_download.return_value is False

        result = install_claude.ensure_git_bash_windows()
        assert result is None

    @patch('platform.system', return_value='Linux')
    @patch('install_claude.get_node_version')
    @patch('install_claude.install_nodejs_apt', return_value=True)
    def test_ensure_nodejs_linux_apt(self, mock_apt, mock_get_version, mock_system):
        """Test Node.js installation on Linux via apt."""
        # Verify mock configurations
        assert mock_system.return_value == 'Linux'
        assert mock_apt.return_value is True

        # ensure_nodejs calls get_node_version multiple times:
        # 1. Initial check (line 551) - returns None
        # 2. After apt installation check 1 (line 609) - returns v20.10.0
        # 3. After apt installation check 2 (line 610) - returns v20.10.0
        mock_get_version.side_effect = [None, 'v20.10.0', 'v20.10.0']

        with (
            patch('install_claude.compare_versions', return_value=True),
            patch('pathlib.Path.exists', return_value=True),
        ):  # For /etc/debian_version check
            result = install_claude.ensure_nodejs()
            assert result is True
            mock_apt.assert_called_once()
            # Note: Linux apt path doesn't call time.sleep()

    @patch('platform.system', return_value='Darwin')
    @patch('install_claude.get_node_version')
    @patch('install_claude.install_nodejs_homebrew', return_value=False)
    @patch('install_claude.install_nodejs_direct', return_value=True)
    @patch('time.sleep')
    def test_ensure_nodejs_macos_direct(self, mock_sleep, mock_direct, mock_brew, mock_get_version, mock_system):
        """Test Node.js installation on macOS fallback to direct."""
        # Verify mock configurations
        assert mock_system.return_value == 'Darwin'
        assert mock_brew.return_value is False
        assert mock_direct.return_value is True

        # ensure_nodejs calls get_node_version multiple times:
        # 1. Initial check (line 551) - returns None
        # 2. After direct installation check 1 (line 601) - returns v20.10.0
        # 3. After direct installation check 2 (line 601) - returns v20.10.0 (compare_versions calls it again)
        mock_get_version.side_effect = [None, 'v20.10.0', 'v20.10.0']

        with patch('install_claude.compare_versions', return_value=True):
            result = install_claude.ensure_nodejs()
            assert result is True
            mock_direct.assert_called_once()
            mock_sleep.assert_called()

    @patch('platform.system', return_value='Windows')
    @patch('install_claude.get_node_version')
    @patch('install_claude.compare_versions')
    @patch('install_claude.check_winget', return_value=True)
    @patch('install_claude.install_nodejs_winget', return_value=True)
    @patch('time.sleep')
    @patch('pathlib.Path.exists', return_value=False)  # For Windows nodejs path check
    def test_ensure_nodejs_upgrade_old_version(
        self,
        mock_path_exists,
        mock_sleep,
        mock_winget,
        mock_check,
        mock_compare,
        mock_get_version,
        mock_system,
    ):
        """Test Node.js upgrade when version is too old."""
        # Verify mock configurations
        assert mock_system.return_value == 'Windows'
        assert mock_check.return_value is True
        assert mock_winget.return_value is True
        assert mock_path_exists.return_value is False  # Verify the path check mock

        # ensure_nodejs calls get_node_version multiple times:
        # 1. Initial check (line 551) - returns v16.0.0
        # 2. After winget install check 1 (line 569) - returns v20.10.0
        # 3. After winget install check 2 (line 569) for compare_versions - returns v20.10.0
        mock_get_version.side_effect = ['v16.0.0', 'v20.10.0', 'v20.10.0']

        # compare_versions is called:
        # 1. Initial check (line 554) - returns False (v16 < v18)
        # 2. After winget install (line 569) - returns True (v20 >= v18)
        mock_compare.side_effect = [False, True]

        result = install_claude.ensure_nodejs()
        assert result is True
        mock_winget.assert_called_once()
        mock_sleep.assert_called()

    @patch('platform.system', return_value='Windows')
    @patch('install_claude.get_node_version', return_value=None)
    @patch('install_claude.check_winget', return_value=False)
    @patch('install_claude.install_nodejs_direct', return_value=False)
    def test_ensure_nodejs_all_methods_fail(self, mock_direct, mock_check, mock_version, mock_system):
        """Test Node.js installation when all methods fail."""
        # Verify all methods are configured to fail
        assert mock_system.return_value == 'Windows'
        assert mock_version.return_value is None
        assert mock_check.return_value is False
        assert mock_direct.return_value is False

        result = install_claude.ensure_nodejs()
        assert result is False


class TestMainFlowAdditional:
    """Additional tests for main flow."""

    @patch('platform.system', return_value='Windows')
    @patch('install_claude.ensure_git_bash_windows', return_value='C:\\Git\\bash.exe')
    @patch('install_claude.ensure_nodejs', return_value=False)
    def test_main_nodejs_failure_exits(self, mock_node, mock_git, mock_system):
        """Test main flow exits when Node.js installation fails."""
        # Verify mock configurations
        assert mock_system.return_value == 'Windows'
        assert mock_git.return_value == 'C:\\Git\\bash.exe'
        assert mock_node.return_value is False

        # Force npm installation method to ensure Node.js is required
        with patch.dict('os.environ', {'CLAUDE_INSTALL_METHOD': 'npm'}), patch('sys.exit') as mock_exit:
            install_claude.main()
            mock_exit.assert_called_with(1)

    @patch('platform.system', return_value='Linux')
    @patch('install_claude.ensure_nodejs', return_value=True)
    @patch('install_claude.ensure_claude', return_value=False)
    def test_main_claude_failure_exits(self, mock_claude, mock_node, mock_system):
        """Test main flow exits when Claude installation fails."""
        # Verify mock configurations
        assert mock_system.return_value == 'Linux'
        assert mock_node.return_value is True
        assert mock_claude.return_value is False

        with patch('sys.exit') as mock_exit:
            install_claude.main()
            mock_exit.assert_called_with(1)


class TestHelperFunctions:
    """Test helper functions."""

    @patch('platform.system', return_value='Darwin')
    def test_update_path_skip_macos(self, mock_system):
        """Test that PATH update is skipped on macOS."""
        # Verify platform mock
        assert mock_system.return_value == 'Darwin'

        original_path = os.environ.get('PATH', '')
        install_claude.update_path()
        assert os.environ.get('PATH', '') == original_path

    @patch('platform.system', return_value='Windows')
    @patch('pathlib.Path.exists', return_value=False)
    def test_update_path_windows_npm_not_exists(self, mock_exists, mock_system):
        """Test PATH update on Windows when npm path doesn't exist."""
        # Verify mock configurations
        assert mock_system.return_value == 'Windows'
        assert mock_exists.return_value is False

        original_path = os.environ.get('PATH', '')
        install_claude.update_path()
        # PATH should not change if npm path doesn't exist
        assert original_path == os.environ.get('PATH', '')


class TestGitBashDetection:
    """Test Git Bash detection on Windows."""

    @patch('install_claude.find_command', return_value=None)
    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-specific test')
    @patch('os.path.expandvars')
    @patch('pathlib.Path.exists')
    def test_find_bash_windows_check_localappdata(self, mock_exists, mock_expand, mock_find):
        """Test finding bash in LOCALAPPDATA location."""
        # Verify find_command returns None (bash not in PATH)
        assert mock_find.return_value is None

        mock_expand.side_effect = lambda x: x.replace('%LOCALAPPDATA%', 'C:\\Users\\Test\\AppData\\Local')
        mock_exists.side_effect = [False, False, False, False, True, False]  # 5th path exists

        result = install_claude.find_bash_windows()
        assert result is not None
        assert 'AppData\\Local' in result


class TestWingetCheck:
    """Test winget availability check."""

    @patch('install_claude.find_command', return_value='C:\\Windows\\System32\\winget.exe')
    def test_check_winget_found(self, mock_find):
        """Test winget check when found."""
        # Verify mock configuration
        assert mock_find.return_value == 'C:\\Windows\\System32\\winget.exe'
        assert install_claude.check_winget() is True

    @patch('install_claude.find_command', return_value=None)
    def test_check_winget_not_found(self, mock_find):
        """Test winget check when not found."""
        # Verify mock configuration
        assert mock_find.return_value is None
        assert install_claude.check_winget() is False


class TestNodeVersionComparison:
    """Test Node.js version comparison."""

    @patch('install_claude.find_command', return_value='node')
    @patch('install_claude.run_command')
    def test_get_node_version_error(self, mock_run, mock_find):
        """Test getting Node.js version when command fails."""
        # Verify mock configurations
        assert mock_find.return_value == 'node'

        mock_run.return_value = subprocess.CompletedProcess([], 1, '', 'error')
        version = install_claude.get_node_version()
        assert version is None


class TestInstallNodeJsWinget:
    """Test Node.js installation via winget."""

    @patch('install_claude.check_winget', return_value=False)
    def test_install_nodejs_winget_no_winget(self, mock_check):
        """Test Node.js winget install when winget not available."""
        # Verify mock configuration
        assert mock_check.return_value is False

        result = install_claude.install_nodejs_winget()
        assert result is False

    @patch('install_claude.check_winget', return_value=True)
    @patch('install_claude.run_command')
    def test_install_nodejs_winget_failure(self, mock_run, mock_check):
        """Test Node.js winget install failure."""
        # Verify mock configurations
        assert mock_check.return_value is True

        mock_run.return_value = subprocess.CompletedProcess([], 1, '', 'error')
        result = install_claude.install_nodejs_winget()
        assert result is False


class TestInstallGitWinget:
    """Test Git installation via winget."""

    @patch('install_claude.check_winget', return_value=False)
    def test_install_git_windows_winget_no_winget(self, mock_check):
        """Test Git winget install when winget not available."""
        # Verify mock configuration
        assert mock_check.return_value is False

        result = install_claude.install_git_windows_winget()
        assert result is False

    @patch('install_claude.check_winget', return_value=True)
    @patch('install_claude.run_command')
    def test_install_git_windows_winget_failure(self, mock_run, mock_check):
        """Test Git winget install failure."""
        # Verify mock configurations
        assert mock_check.return_value is True

        mock_run.return_value = subprocess.CompletedProcess([], 1, '', 'error')
        result = install_claude.install_git_windows_winget()
        assert result is False


class TestGCSDirectDownload:
    """Test direct download from GCS bucket for specific versions."""

    @patch('install_claude._get_gcs_platform_path', return_value=('win32-x64', 'claude.exe'))
    @patch('install_claude.urlretrieve')
    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.stat')
    @patch('pathlib.Path.replace')
    @patch('pathlib.Path.mkdir')
    def test_download_claude_direct_from_gcs_success(
        self,
        mock_mkdir,
        mock_replace,
        mock_stat,
        mock_exists,
        mock_urlretrieve,
        mock_platform_path,
    ):
        """Test successful direct download from GCS."""
        # Mock file exists after download
        mock_exists.return_value = True
        mock_stat.return_value.st_size = 5_000_000  # 5MB file

        target_path = Path.home() / '.local' / 'bin' / 'claude.exe'
        result = install_claude._download_claude_direct_from_gcs('2.0.76', target_path)

        assert result is True
        mock_platform_path.assert_called_once()  # Platform path was determined
        mock_urlretrieve.assert_called_once()
        mock_mkdir.assert_called()  # Directory creation
        mock_replace.assert_called()  # Atomic file move
        # Verify GCS URL was used
        call_url = mock_urlretrieve.call_args[0][0]
        assert 'storage.googleapis.com' in call_url
        assert '2.0.76' in call_url
        assert 'win32-x64' in call_url

    @patch('install_claude.urlretrieve')
    @patch('pathlib.Path.mkdir')
    def test_download_claude_direct_from_gcs_http_404(self, mock_mkdir, mock_urlretrieve):
        """Test direct download when version not found (HTTP 404)."""
        from email.message import Message

        headers = Message()
        mock_urlretrieve.side_effect = urllib.error.HTTPError(
            'https://storage.googleapis.com/...',
            404,
            'Not Found',
            headers,
            None,
        )

        target_path = Path.home() / '.local' / 'bin' / 'claude.exe'
        result = install_claude._download_claude_direct_from_gcs('99.99.99', target_path)

        assert result is False
        mock_mkdir.assert_called()  # Directory creation attempted

    @patch('install_claude.urlretrieve')
    @patch('pathlib.Path.mkdir')
    def test_download_claude_direct_from_gcs_network_error(self, mock_mkdir, mock_urlretrieve):
        """Test direct download with network error."""
        mock_urlretrieve.side_effect = urllib.error.URLError('Connection refused')

        target_path = Path.home() / '.local' / 'bin' / 'claude.exe'
        result = install_claude._download_claude_direct_from_gcs('2.0.76', target_path)

        assert result is False
        mock_mkdir.assert_called()  # Directory creation attempted

    @patch('install_claude.urlretrieve')
    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.stat')
    @patch('pathlib.Path.unlink')
    @patch('pathlib.Path.mkdir')
    def test_download_claude_direct_from_gcs_file_too_small(
        self,
        mock_mkdir,
        mock_unlink,
        mock_stat,
        mock_exists,
        mock_urlretrieve,
    ):
        """Test direct download when downloaded file is too small (corrupted)."""
        mock_exists.return_value = True
        mock_stat.return_value.st_size = 500  # Only 500 bytes - too small
        mock_urlretrieve.return_value = None  # Download "succeeds"

        target_path = Path.home() / '.local' / 'bin' / 'claude.exe'
        result = install_claude._download_claude_direct_from_gcs('2.0.76', target_path)

        assert result is False
        mock_mkdir.assert_called()  # Directory creation
        mock_urlretrieve.assert_called()  # Download attempted
        mock_unlink.assert_called()  # Corrupted file cleaned up

    @patch('install_claude.urllib.request.build_opener')
    @patch('install_claude.urllib.request.install_opener')
    @patch('install_claude.urlretrieve')
    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.stat')
    @patch('pathlib.Path.replace')
    @patch('pathlib.Path.mkdir')
    def test_download_claude_direct_from_gcs_ssl_fallback(
        self,
        mock_mkdir,
        mock_replace,
        mock_stat,
        mock_exists,
        mock_urlretrieve,
        mock_install_opener,
        mock_build_opener,
    ):
        """Test direct download with SSL error fallback."""
        # First call fails with SSL error, second succeeds
        mock_urlretrieve.side_effect = [
            urllib.error.URLError('SSL: CERTIFICATE_VERIFY_FAILED'),
            None,  # Second call succeeds
        ]
        mock_exists.return_value = True
        mock_stat.return_value.st_size = 5_000_000

        target_path = Path.home() / '.local' / 'bin' / 'claude.exe'
        result = install_claude._download_claude_direct_from_gcs('2.0.76', target_path)

        assert result is True
        assert mock_urlretrieve.call_count == 2
        mock_build_opener.assert_called_once()
        mock_install_opener.assert_called_once()
        mock_mkdir.assert_called()  # Directory creation
        mock_replace.assert_called()  # Atomic file move


class TestHybridInstallApproach:
    """Test the hybrid installation approach for Windows."""

    @patch('platform.system', return_value='Windows')
    @patch('install_claude._install_claude_native_windows_installer')
    def test_install_claude_native_windows_no_version_uses_installer(
        self,
        mock_installer,
        mock_system,
    ):
        """Test that no version uses native installer with 'latest'."""
        # Verify mock configuration
        assert mock_system.return_value == 'Windows'
        mock_installer.return_value = True

        result = install_claude.install_claude_native_windows(version=None)

        assert result is True
        mock_installer.assert_called_once_with(version='latest')

    @patch('platform.system', return_value='Windows')
    @patch('install_claude._install_claude_native_windows_installer')
    def test_install_claude_native_windows_latest_uses_installer(
        self,
        mock_installer,
        mock_system,
    ):
        """Test that 'latest' version uses native installer."""
        # Verify mock configuration
        assert mock_system.return_value == 'Windows'
        mock_installer.return_value = True

        result = install_claude.install_claude_native_windows(version='latest')

        assert result is True
        mock_installer.assert_called_once_with(version='latest')

    @patch('platform.system', return_value='Windows')
    @patch('install_claude._download_claude_direct_from_gcs')
    @patch('install_claude.ensure_local_bin_in_path_windows')
    @patch('install_claude.verify_claude_installation')
    @patch('time.sleep')
    def test_install_claude_native_windows_specific_version_uses_gcs(
        self,
        mock_sleep,
        mock_verify,
        mock_ensure_path,
        mock_gcs_download,
        mock_system,
    ):
        """Test that specific version uses GCS direct download.

        The implementation configures PATH directly via ensure_local_bin_in_path_windows()
        without calling 'claude install', which would trigger auto-update behavior.
        """
        # Verify mock configuration
        assert mock_system.return_value == 'Windows'
        mock_gcs_download.return_value = True
        mock_verify.return_value = (True, 'C:\\Users\\Test\\.local\\bin\\claude.exe', 'native')

        result = install_claude.install_claude_native_windows(version='2.0.76')

        assert result is True
        mock_gcs_download.assert_called_once()
        mock_sleep.assert_called()
        mock_ensure_path.assert_called()
        # Verify version was passed to GCS download
        call_args = mock_gcs_download.call_args[0]
        assert call_args[0] == '2.0.76'

    @patch('platform.system', return_value='Windows')
    @patch('install_claude._download_claude_direct_from_gcs')
    @patch('install_claude._install_claude_native_windows_installer')
    def test_install_claude_native_windows_gcs_fails_fallback_to_installer(
        self,
        mock_installer,
        mock_gcs_download,
        mock_system,
    ):
        """Test fallback to native installer when GCS download fails."""
        # Verify mock configuration
        assert mock_system.return_value == 'Windows'
        mock_gcs_download.return_value = False
        mock_installer.return_value = True

        result = install_claude.install_claude_native_windows(version='2.0.76')

        assert result is True
        mock_gcs_download.assert_called_once()
        mock_installer.assert_called_once_with(version='latest')

    @patch('platform.system', return_value='Linux')
    def test_install_claude_native_windows_returns_false_on_linux(self, mock_system):
        """Test that Windows installer returns False on Linux."""
        # Verify mock configuration
        assert mock_system.return_value == 'Linux'
        result = install_claude.install_claude_native_windows(version='2.0.76')

        assert result is False


class TestNativeWindowsInstallerFunction:
    """Test the internal native Windows installer function."""

    @patch('platform.system', return_value='Windows')
    @patch('install_claude.urlopen')
    @patch('install_claude.run_command')
    @patch('install_claude.verify_claude_installation')
    @patch('install_claude.ensure_local_bin_in_path_windows')
    @patch('install_claude.remove_npm_claude')
    @patch('tempfile.NamedTemporaryFile')
    @patch('os.unlink')
    @patch('time.sleep')
    def test_install_claude_native_windows_installer_success(
        self,
        mock_sleep,
        mock_unlink,
        mock_temp,
        mock_remove_npm,
        mock_ensure_path,
        mock_verify,
        mock_run,
        mock_urlopen,
        mock_system,
    ):
        """Test successful native installer execution."""
        # Verify mock configuration
        assert mock_system.return_value == 'Windows'

        # Mock installer script download
        mock_response = MagicMock()
        mock_response.read.return_value = b'# PowerShell installer script'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        # Mock temp file
        temp_file = MagicMock()
        temp_file.name = 'C:\\temp\\install.ps1'
        mock_temp.return_value.__enter__.return_value = temp_file

        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')
        mock_verify.return_value = (True, 'C:\\Users\\Test\\.local\\bin\\claude.exe', 'native')
        mock_remove_npm.return_value = True

        result = install_claude._install_claude_native_windows_installer(version='latest')

        assert result is True
        mock_run.assert_called_once()
        mock_sleep.assert_called()
        mock_unlink.assert_called()
        mock_ensure_path.assert_called()
        mock_remove_npm.assert_called_once()
        # Verify 'latest' was passed to the installer
        call_args = mock_run.call_args[0][0]
        assert 'latest' in call_args

    @patch('install_claude.urlopen')
    def test_install_claude_native_windows_installer_network_error(self, mock_urlopen):
        """Test native installer with network error."""
        mock_urlopen.side_effect = urllib.error.URLError('Connection refused')

        result = install_claude._install_claude_native_windows_installer(version='latest')

        assert result is False

    @patch('install_claude.urlopen')
    @patch('install_claude.run_command')
    @patch('install_claude.verify_claude_installation')
    @patch('install_claude.ensure_local_bin_in_path_windows')
    @patch('tempfile.NamedTemporaryFile')
    @patch('os.unlink')
    @patch('time.sleep')
    def test_install_claude_native_windows_installer_ssl_fallback(
        self,
        mock_sleep,
        mock_unlink,
        mock_temp,
        mock_ensure_path,
        mock_verify,
        mock_run,
        mock_urlopen,
    ):
        """Test native installer with SSL error fallback."""
        # First call fails with SSL, second succeeds
        mock_response = MagicMock()
        mock_response.read.return_value = b'# PowerShell installer script'

        mock_urlopen.side_effect = [
            urllib.error.URLError('SSL: CERTIFICATE_VERIFY_FAILED'),
            MagicMock(__enter__=lambda _: mock_response, __exit__=lambda *_: None),
        ]

        # Mock temp file
        temp_file = MagicMock()
        temp_file.name = 'C:\\temp\\install.ps1'
        mock_temp.return_value.__enter__.return_value = temp_file

        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')
        mock_verify.return_value = (True, 'C:\\Users\\Test\\.local\\bin\\claude.exe', 'native')

        result = install_claude._install_claude_native_windows_installer(version='latest')

        # Verify mocks were used
        mock_sleep.assert_called()
        mock_unlink.assert_called()
        mock_ensure_path.assert_called()

        assert result is True
        assert mock_urlopen.call_count == 2


class TestGetGcsPlatformPath:
    """Test the _get_gcs_platform_path function for cross-platform support."""

    @patch('platform.system', return_value='Windows')
    @patch('platform.machine', return_value='AMD64')
    def test_get_gcs_platform_path_windows(self, mock_machine, mock_system):
        """Test GCS path for Windows."""
        # Verify mock configuration
        assert mock_system.return_value == 'Windows'
        assert mock_machine.return_value == 'AMD64'

        platform_path, binary_name = install_claude._get_gcs_platform_path()

        assert platform_path == 'win32-x64'
        assert binary_name == 'claude.exe'

    @patch('platform.system', return_value='Darwin')
    @patch('platform.machine', return_value='arm64')
    def test_get_gcs_platform_path_macos_arm(self, mock_machine, mock_system):
        """Test GCS path for macOS ARM (Apple Silicon)."""
        # Verify mock configuration
        assert mock_system.return_value == 'Darwin'
        assert mock_machine.return_value == 'arm64'

        platform_path, binary_name = install_claude._get_gcs_platform_path()

        assert platform_path == 'darwin-arm64'
        assert binary_name == 'claude'

    @patch('platform.system', return_value='Darwin')
    @patch('platform.machine', return_value='x86_64')
    def test_get_gcs_platform_path_macos_intel(self, mock_machine, mock_system):
        """Test GCS path for macOS Intel."""
        # Verify mock configuration
        assert mock_system.return_value == 'Darwin'
        assert mock_machine.return_value == 'x86_64'

        platform_path, binary_name = install_claude._get_gcs_platform_path()

        assert platform_path == 'darwin-x64'
        assert binary_name == 'claude'

    @patch('platform.system', return_value='Linux')
    @patch('platform.machine', return_value='x86_64')
    def test_get_gcs_platform_path_linux_x64(self, mock_machine, mock_system):
        """Test GCS path for Linux x64."""
        # Verify mock configuration
        assert mock_system.return_value == 'Linux'
        assert mock_machine.return_value == 'x86_64'

        platform_path, binary_name = install_claude._get_gcs_platform_path()

        assert platform_path == 'linux-x64'
        assert binary_name == 'claude'

    @patch('platform.system', return_value='Linux')
    @patch('platform.machine', return_value='aarch64')
    def test_get_gcs_platform_path_linux_arm64(self, mock_machine, mock_system):
        """Test GCS path for Linux ARM64."""
        # Verify mock configuration
        assert mock_system.return_value == 'Linux'
        assert mock_machine.return_value == 'aarch64'

        platform_path, binary_name = install_claude._get_gcs_platform_path()

        assert platform_path == 'linux-arm64'
        assert binary_name == 'claude'


class TestHybridInstallMacOS:
    """Test the hybrid installation approach for macOS."""

    @patch('sys.platform', 'darwin')
    @patch('install_claude._install_claude_native_macos_installer')
    def test_install_claude_native_macos_no_version_uses_installer(
        self,
        mock_installer,
    ):
        """Test that no version uses native installer with 'latest'."""
        mock_installer.return_value = True

        result = install_claude.install_claude_native_macos(version=None)

        assert result is True
        mock_installer.assert_called_once_with(version='latest')

    @patch('sys.platform', 'darwin')
    @patch('install_claude._install_claude_native_macos_installer')
    def test_install_claude_native_macos_latest_uses_installer(
        self,
        mock_installer,
    ):
        """Test that 'latest' version uses native installer."""
        mock_installer.return_value = True

        result = install_claude.install_claude_native_macos(version='latest')

        assert result is True
        mock_installer.assert_called_once_with(version='latest')

    @patch('sys.platform', 'darwin')
    @patch('install_claude._download_claude_direct_from_gcs')
    @patch('install_claude._ensure_local_bin_in_path_unix')
    @patch('install_claude.verify_claude_installation')
    @patch('pathlib.Path.chmod')
    @patch('time.sleep')
    def test_install_claude_native_macos_specific_version_uses_gcs(
        self,
        mock_sleep,
        mock_chmod,
        mock_verify,
        mock_ensure_path,
        mock_gcs_download,
    ):
        """Test that specific version uses GCS direct download on macOS.

        The implementation configures PATH directly via _ensure_local_bin_in_path_unix()
        without calling 'claude install', which would trigger auto-update behavior.
        """
        mock_gcs_download.return_value = True
        mock_verify.return_value = (True, '/Users/Test/.local/bin/claude', 'native')

        result = install_claude.install_claude_native_macos(version='2.0.76')

        assert result is True
        mock_gcs_download.assert_called_once()
        mock_sleep.assert_called()
        mock_chmod.assert_called()
        # Verify version was passed to GCS download
        call_args = mock_gcs_download.call_args[0]
        assert call_args[0] == '2.0.76'
        mock_ensure_path.assert_called()

    @patch('sys.platform', 'darwin')
    @patch('install_claude._download_claude_direct_from_gcs')
    @patch('install_claude._install_claude_native_macos_installer')
    def test_install_claude_native_macos_gcs_fails_fallback_to_installer(
        self,
        mock_installer,
        mock_gcs_download,
    ):
        """Test fallback to native installer when GCS download fails on macOS."""
        mock_gcs_download.return_value = False
        mock_installer.return_value = True

        result = install_claude.install_claude_native_macos(version='2.0.76')

        assert result is True
        mock_gcs_download.assert_called_once()
        mock_installer.assert_called_once_with(version='latest')

    @patch('sys.platform', 'win32')
    def test_install_claude_native_macos_returns_false_on_windows(self):
        """Test that macOS installer returns False on Windows."""
        result = install_claude.install_claude_native_macos(version='2.0.76')

        assert result is False


class TestHybridInstallLinux:
    """Test the hybrid installation approach for Linux."""

    @patch('platform.system', return_value='Linux')
    @patch('install_claude._install_claude_native_linux_installer')
    def test_install_claude_native_linux_no_version_uses_installer(
        self,
        mock_installer,
        mock_platform,
    ):
        """Test that no version uses native installer with 'latest'."""
        mock_installer.return_value = True

        result = install_claude.install_claude_native_linux(version=None)

        assert result is True
        mock_installer.assert_called_once_with(version='latest')
        mock_platform.assert_called()

    @patch('platform.system', return_value='Linux')
    @patch('install_claude._install_claude_native_linux_installer')
    def test_install_claude_native_linux_latest_uses_installer(
        self,
        mock_installer,
        mock_platform,
    ):
        """Test that 'latest' version uses native installer."""
        mock_installer.return_value = True

        result = install_claude.install_claude_native_linux(version='latest')

        assert result is True
        mock_installer.assert_called_once_with(version='latest')
        mock_platform.assert_called()

    @patch('platform.system', return_value='Linux')
    @patch('install_claude._download_claude_direct_from_gcs')
    @patch('install_claude._ensure_local_bin_in_path_unix')
    @patch('install_claude.verify_claude_installation')
    @patch('pathlib.Path.chmod')
    @patch('time.sleep')
    def test_install_claude_native_linux_specific_version_uses_gcs(
        self,
        mock_sleep,
        mock_chmod,
        mock_verify,
        mock_ensure_path,
        mock_gcs_download,
        mock_platform,
    ):
        """Test that specific version uses GCS direct download on Linux.

        The implementation configures PATH directly via _ensure_local_bin_in_path_unix()
        without calling 'claude install', which would trigger auto-update behavior.
        """
        mock_gcs_download.return_value = True
        mock_verify.return_value = (True, '/home/test/.local/bin/claude', 'native')

        result = install_claude.install_claude_native_linux(version='2.0.76')

        assert result is True
        mock_gcs_download.assert_called_once()
        mock_sleep.assert_called()
        mock_chmod.assert_called()
        # Verify version was passed to GCS download
        call_args = mock_gcs_download.call_args[0]
        assert call_args[0] == '2.0.76'
        mock_ensure_path.assert_called()
        mock_platform.assert_called()

    @patch('platform.system', return_value='Linux')
    @patch('install_claude._download_claude_direct_from_gcs')
    @patch('install_claude._install_claude_native_linux_installer')
    def test_install_claude_native_linux_gcs_fails_fallback_to_installer(
        self,
        mock_installer,
        mock_gcs_download,
        mock_platform,
    ):
        """Test fallback to native installer when GCS download fails on Linux."""
        mock_gcs_download.return_value = False
        mock_installer.return_value = True

        result = install_claude.install_claude_native_linux(version='2.0.76')

        assert result is True
        mock_gcs_download.assert_called_once()
        mock_installer.assert_called_once_with(version='latest')
        mock_platform.assert_called()

    @patch('platform.system', return_value='Windows')
    def test_install_claude_native_linux_returns_false_on_windows(self, mock_system):
        """Test that Linux installer returns False on Windows."""
        # Verify mock configuration
        assert mock_system.return_value == 'Windows'
        result = install_claude.install_claude_native_linux(version='2.0.76')

        assert result is False


class TestNativeMacOSInstallerFunction:
    """Test the internal native macOS installer function."""

    @patch('install_claude.urlopen')
    @patch('install_claude.run_command')
    @patch('install_claude.verify_claude_installation')
    @patch('install_claude.remove_npm_claude')
    @patch('tempfile.NamedTemporaryFile')
    @patch('os.chmod')
    @patch('os.unlink')
    @patch('time.sleep')
    def test_install_claude_native_macos_installer_success(
        self,
        mock_sleep,
        mock_unlink,
        mock_chmod,
        mock_temp,
        mock_remove_npm,
        mock_verify,
        mock_run,
        mock_urlopen,
    ):
        """Test successful native macOS installer execution."""
        # Mock installer script download
        mock_response = MagicMock()
        mock_response.read.return_value = b'#!/bin/bash\necho "Installing"'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        # Mock temp file
        temp_file = MagicMock()
        temp_file.name = '/tmp/install.sh'
        mock_temp.return_value.__enter__.return_value = temp_file

        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')
        mock_verify.return_value = (True, '/Users/Test/.local/bin/claude', 'native')
        mock_remove_npm.return_value = True

        result = install_claude._install_claude_native_macos_installer(version='latest')

        assert result is True
        mock_run.assert_called_once()
        mock_sleep.assert_called()
        mock_unlink.assert_called()
        mock_chmod.assert_called()
        mock_remove_npm.assert_called_once()

    @patch('install_claude.urlopen')
    def test_install_claude_native_macos_installer_network_error(self, mock_urlopen):
        """Test native macOS installer with network error."""
        mock_urlopen.side_effect = urllib.error.URLError('Connection refused')

        result = install_claude._install_claude_native_macos_installer(version='latest')

        assert result is False


class TestNativeLinuxInstallerFunction:
    """Test the internal native Linux installer function."""

    @patch('install_claude.urlopen')
    @patch('install_claude.run_command')
    @patch('install_claude.verify_claude_installation')
    @patch('install_claude.remove_npm_claude')
    @patch('tempfile.NamedTemporaryFile')
    @patch('os.chmod')
    @patch('os.unlink')
    @patch('time.sleep')
    def test_install_claude_native_linux_installer_success(
        self,
        mock_sleep,
        mock_unlink,
        mock_chmod,
        mock_temp,
        mock_remove_npm,
        mock_verify,
        mock_run,
        mock_urlopen,
    ):
        """Test successful native Linux installer execution."""
        # Mock installer script download
        mock_response = MagicMock()
        mock_response.read.return_value = b'#!/bin/bash\necho "Installing"'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        # Mock temp file
        temp_file = MagicMock()
        temp_file.name = '/tmp/install.sh'
        mock_temp.return_value.__enter__.return_value = temp_file

        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')
        mock_verify.return_value = (True, '/home/test/.local/bin/claude', 'native')
        mock_remove_npm.return_value = True

        result = install_claude._install_claude_native_linux_installer(version='latest')

        assert result is True
        mock_run.assert_called_once()
        mock_sleep.assert_called()
        mock_unlink.assert_called()
        mock_chmod.assert_called()
        mock_remove_npm.assert_called_once()

    @patch('install_claude.urlopen')
    def test_install_claude_native_linux_installer_network_error(self, mock_urlopen):
        """Test native Linux installer with network error."""
        mock_urlopen.side_effect = urllib.error.URLError('Connection refused')

        result = install_claude._install_claude_native_linux_installer(version='latest')

        assert result is False


class TestEnsureLocalBinInPathUnix:
    """Test the _ensure_local_bin_in_path_unix function."""

    @patch('sys.platform', 'win32')
    def test_ensure_local_bin_in_path_unix_noop_on_windows(self) -> None:
        """Test that function is a no-op on Windows."""
        result = install_claude._ensure_local_bin_in_path_unix()

        assert result is True

    @patch('install_claude.sys.platform', 'linux')
    @patch('pathlib.Path.home')
    @patch('pathlib.Path.mkdir')
    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.read_text')
    @patch('pathlib.Path.write_text')
    def test_ensure_local_bin_in_path_unix_updates_path(
        self,
        mock_write: MagicMock,
        mock_read: MagicMock,
        mock_exists: MagicMock,
        mock_mkdir: MagicMock,
        mock_home: MagicMock,
    ) -> None:
        """Test that function updates PATH on Unix."""
        # Mock home directory
        mock_home.return_value = Path('/home/testuser')
        # Profile files don't exist
        mock_exists.return_value = False

        # Save original PATH
        original_path = os.environ.get('PATH', '')
        os.environ['PATH'] = '/usr/bin:/bin'

        try:
            result = install_claude._ensure_local_bin_in_path_unix()

            assert result is True
            # PATH should be updated in current process (check for .local and bin in path)
            assert '.local' in os.environ['PATH']
            assert 'bin' in os.environ['PATH']
            # Verify mocks were configured (profile files don't exist, so no writes)
            assert mock_exists.return_value is False
            # mock_write and mock_read are not called when files don't exist
            assert not mock_write.called
            assert not mock_read.called
            # mkdir is called to create .local/bin
            mock_mkdir.assert_called()
        finally:
            # Restore PATH
            os.environ['PATH'] = original_path

    @patch('install_claude.sys.platform', 'linux')
    @patch('pathlib.Path.home')
    @patch('pathlib.Path.mkdir')
    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.read_text')
    @patch('pathlib.Path.write_text')
    def test_ensure_local_bin_in_path_unix_updates_profile(
        self,
        mock_write: MagicMock,
        mock_read: MagicMock,
        mock_exists: MagicMock,
        mock_mkdir: MagicMock,
        mock_home: MagicMock,
    ) -> None:
        """Test that function updates shell profile files."""
        # Mock home directory
        mock_home.return_value = Path('/home/testuser')
        # .bashrc exists, doesn't have .local/bin
        mock_exists.return_value = True
        mock_read.return_value = '# .bashrc content'

        # Save original PATH
        original_path = os.environ.get('PATH', '')
        os.environ['PATH'] = '/usr/bin:/bin'

        try:
            result = install_claude._ensure_local_bin_in_path_unix()

            assert result is True
            # Should write to profile files
            assert mock_write.called
            # mkdir is called to create .local/bin
            mock_mkdir.assert_called()
        finally:
            # Restore PATH
            os.environ['PATH'] = original_path
