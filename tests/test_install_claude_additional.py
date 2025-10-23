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

    @patch('platform.system', return_value='Linux')
    def test_install_claude_native_linux(self, mock_system):
        """Test native Claude installation on Linux."""
        # Verify platform mock
        assert mock_system.return_value == 'Linux'

        # install_claude_native returns False for non-Windows platforms
        result = install_claude.install_claude_native()
        assert result is False

    @patch('platform.system', return_value='Darwin')
    def test_install_claude_native_macos(self, mock_system):
        """Test native Claude installation on macOS."""
        # Verify platform mock
        assert mock_system.return_value == 'Darwin'

        # install_claude_native returns False for non-Windows platforms
        result = install_claude.install_claude_native()
        assert result is False

    @patch('install_claude.urlopen')
    def test_install_claude_native_download_error(self, mock_urlopen):
        """Test native Claude installation with download error."""
        mock_urlopen.side_effect = urllib.error.URLError('Connection error')
        result = install_claude.install_claude_native()
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

        with patch('sys.exit') as mock_exit:
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
