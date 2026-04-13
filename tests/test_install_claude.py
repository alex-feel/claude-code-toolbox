"""
Comprehensive tests for install_claude.py - the main Claude Code installer.
"""

import contextlib
import json
import os
import subprocess
import sys
import time
import urllib.error
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

import install_claude


class TestColors:
    """Test the Colors class and color stripping."""

    def test_colors_strip_windows_cmd(self):
        """Test that colors are stripped in Windows CMD."""
        with patch('platform.system', return_value='Windows'), patch.dict('os.environ', {}, clear=True):
            install_claude.Colors.strip()
            assert install_claude.Colors.RED == ''
            assert install_claude.Colors.GREEN == ''
            assert install_claude.Colors.NC == ''

    def test_colors_kept_windows_terminal(self):
        """Test that colors are kept in Windows Terminal."""
        # Reset colors first
        install_claude.Colors.RED = '\033[0;31m'
        install_claude.Colors.GREEN = '\033[0;32m'
        with patch('platform.system', return_value='Windows'), patch.dict('os.environ', {'WT_SESSION': '1'}):
            install_claude.Colors.strip()
            assert install_claude.Colors.RED == '\033[0;31m'
            assert install_claude.Colors.GREEN == '\033[0;32m'

    def test_colors_kept_unix(self):
        """Test that colors are kept on Unix systems."""
        install_claude.Colors.RED = '\033[0;31m'
        with patch('platform.system', return_value='Linux'):
            install_claude.Colors.strip()
            assert install_claude.Colors.RED == '\033[0;31m'


class TestLoggingFunctions:
    """Test logging functions."""

    def test_info(self, capsys):
        """Test info message output."""
        install_claude.info('Test message')
        captured = capsys.readouterr()
        assert '[INFO]' in captured.out
        assert 'Test message' in captured.out

    def test_success(self, capsys):
        """Test success message output."""
        install_claude.success('Operation complete')
        captured = capsys.readouterr()
        assert '[OK]' in captured.out
        assert 'Operation complete' in captured.out

    def test_warning(self, capsys):
        """Test warning message output."""
        install_claude.warning('Warning message')
        captured = capsys.readouterr()
        assert '[WARN]' in captured.out
        assert 'Warning message' in captured.out

    def test_error(self, capsys):
        """Test error message output."""
        install_claude.error('Error occurred')
        captured = capsys.readouterr()
        assert '[FAIL]' in captured.err
        assert 'Error occurred' in captured.err

    def test_banner(self, capsys):
        """Test banner output."""
        with patch('platform.system', return_value='Windows'):
            install_claude.banner()
            captured = capsys.readouterr()
            assert 'Claude Code Windows Installer' in captured.out


class TestUtilityFunctions:
    """Test utility functions."""

    def test_parse_version_valid(self):
        """Test parsing valid version strings."""
        assert install_claude.parse_version('v18.17.0') == (18, 17, 0)
        assert install_claude.parse_version('20.5.1') == (20, 5, 1)
        assert install_claude.parse_version('1.2.3') == (1, 2, 3)

    def test_parse_version_invalid(self):
        """Test parsing invalid version strings."""
        assert install_claude.parse_version('invalid') is None
        assert install_claude.parse_version('') is None
        assert install_claude.parse_version('1.2') is None

    def test_compare_versions_valid(self):
        """Test version comparison with valid versions."""
        assert install_claude.compare_versions('18.0.0', '17.0.0') is True
        assert install_claude.compare_versions('18.0.0', '18.0.0') is True
        assert install_claude.compare_versions('17.0.0', '18.0.0') is False
        assert install_claude.compare_versions('18.1.0', '18.0.5') is True

    def test_compare_versions_invalid(self):
        """Test version comparison with invalid versions."""
        assert install_claude.compare_versions('invalid', '18.0.0') is False
        assert install_claude.compare_versions('18.0.0', 'invalid') is False

    @patch('subprocess.run')
    def test_run_command_success(self, mock_run):
        """Test successful command execution."""
        mock_run.return_value = subprocess.CompletedProcess(['test'], 0, 'output', 'error')
        result = install_claude.run_command(['test', 'command'])
        assert result.returncode == 0
        assert result.stdout == 'output'
        mock_run.assert_called_once()

    @patch('subprocess.run')
    def test_run_command_file_not_found(self, mock_run):
        """Test command not found error."""
        mock_run.side_effect = FileNotFoundError('Command not found')
        result = install_claude.run_command(['missing'])
        assert result.returncode == 1
        assert 'Command not found' in result.stderr

    @patch('subprocess.run')
    def test_run_command_exception(self, mock_run):
        """Test general exception during command execution."""
        mock_run.side_effect = Exception('Test error')
        result = install_claude.run_command(['test'])
        assert result.returncode == 1
        assert 'Test error' in result.stderr


class TestAdminCheck:
    """Test admin/sudo privilege checking."""

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-specific test')
    @patch('platform.system', return_value='Windows')
    @patch('ctypes.windll.shell32.IsUserAnAdmin', return_value=1)
    def test_is_admin_windows_true(self, mock_admin, mock_system):
        """Test admin check on Windows when admin."""
        # Verify mock configurations
        assert mock_system.return_value == 'Windows'
        assert mock_admin.return_value == 1
        assert install_claude.is_admin() is True

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-specific test')
    @patch('platform.system', return_value='Windows')
    @patch('ctypes.windll.shell32.IsUserAnAdmin', return_value=0)
    def test_is_admin_windows_false(self, mock_admin, mock_system):
        """Test admin check on Windows when not admin."""
        # Verify mock configurations
        assert mock_system.return_value == 'Windows'
        assert mock_admin.return_value == 0
        assert install_claude.is_admin() is False

    @patch('platform.system', return_value='Linux')
    def test_is_admin_unix_root(self, mock_system):
        """Test admin check on Unix when root."""
        # Verify mock configuration
        assert mock_system.return_value == 'Linux'
        # Create a mock geteuid function if it doesn't exist (Windows)
        if not hasattr(os, 'geteuid'):
            with patch.object(os, 'geteuid', create=True, return_value=0):
                assert install_claude.is_admin() is True
        else:
            with patch('os.geteuid', return_value=0):
                assert install_claude.is_admin() is True

    @patch('platform.system', return_value='Linux')
    def test_is_admin_unix_user(self, mock_system):
        """Test admin check on Unix when regular user."""
        # Verify mock configuration
        assert mock_system.return_value == 'Linux'
        # Create a mock geteuid function if it doesn't exist (Windows)
        if not hasattr(os, 'geteuid'):
            with patch.object(os, 'geteuid', create=True, return_value=1000):
                assert install_claude.is_admin() is False
        else:
            with patch('os.geteuid', return_value=1000):
                assert install_claude.is_admin() is False


class TestWindowsGitBash:
    """Test Windows Git Bash detection and installation."""

    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_GIT_BASH_PATH': 'C:\\Git\\bash.exe'})
    @patch('pathlib.Path.exists', return_value=True)
    def test_find_bash_windows_env_var(self, mock_exists):
        """Test finding bash via environment variable."""
        # Verify mock configuration
        assert mock_exists.return_value is True
        result = install_claude.find_bash_windows()
        assert result == str(Path('C:\\Git\\bash.exe').resolve())

    @patch('shutil.which', return_value='C:\\Program Files\\Git\\bin\\bash.exe')
    @patch('pathlib.Path.exists', return_value=False)
    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_GIT_BASH_PATH': ''})
    def test_find_bash_windows_in_path(self, mock_exists, mock_which):
        """Test finding bash.exe in PATH via shutil.which fallback."""
        # Verify mock configuration
        assert mock_exists.return_value is False
        assert mock_which.return_value == 'C:\\Program Files\\Git\\bin\\bash.exe'
        result = install_claude.find_bash_windows()
        assert result == 'C:\\Program Files\\Git\\bin\\bash.exe'

    @patch('install_claude.find_command', return_value=None)
    @patch('os.path.expandvars')
    @patch('pathlib.Path.exists')
    def test_find_bash_windows_common_locations(self, mock_exists, mock_expandvars, mock_find):
        """Test finding bash in common locations."""
        # Verify mock configuration
        assert mock_find.return_value is None
        # Mock expandvars to return the path as-is (or expanded)
        mock_expandvars.side_effect = lambda x: x

        # Mock exists to return True for the first common path
        def exists_side_effect():
            # This will be called for each path check
            # Return True for the first Git path
            return mock_exists.call_count == 1

        mock_exists.side_effect = [True, False, False, False, False, False]

        result = install_claude.find_bash_windows()
        assert result is not None
        assert 'Git' in result

    @patch('shutil.which', return_value='winget')
    def test_check_winget_available(self, mock_which):
        """Test winget availability check."""
        # Verify mock configuration
        assert mock_which.return_value == 'winget'
        assert install_claude.check_winget() is True

    @patch('shutil.which', return_value=None)
    def test_check_winget_not_available(self, mock_find):
        """Test winget not available."""
        # Verify mock configuration
        assert mock_find.return_value is None
        assert install_claude.check_winget() is False

    @patch('install_claude.check_winget', return_value=True)
    @patch('install_claude.run_command')
    def test_install_git_windows_winget_success(self, mock_run, mock_winget):
        """Test successful Git installation via winget."""
        # Verify mock configuration
        assert mock_winget.return_value is True
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')
        result = install_claude.install_git_windows_winget('user')
        assert result is True
        mock_run.assert_called_once()
        assert '--scope' in mock_run.call_args[0][0]
        assert 'user' in mock_run.call_args[0][0]

    @patch('install_claude.check_winget', return_value=True)
    @patch('install_claude.run_command')
    def test_install_git_windows_winget_failure(self, mock_run, mock_winget):
        """Test failed Git installation via winget."""
        # Verify mock configuration
        assert mock_winget.return_value is True
        mock_run.return_value = subprocess.CompletedProcess([], 1, '', 'error')
        result = install_claude.install_git_windows_winget()
        assert result is False

    @patch('install_claude.urlopen')
    @patch('install_claude.urlretrieve')  # Changed to patch directly from install_claude
    @patch('install_claude.run_command')
    @patch('tempfile.NamedTemporaryFile')
    @patch('os.unlink')
    def test_install_git_windows_download_success(self, mock_unlink, mock_temp, mock_run, mock_retrieve, mock_urlopen):
        """Test successful Git installation via direct download."""
        # Mock the download page response
        mock_response = MagicMock()
        mock_response.read.return_value = b'<a href="https://github.com/git-for-windows/git/releases/download/v2.51.0.windows.1/Git-2.51.0-64-bit.exe">Download</a>'
        mock_response.__enter__ = lambda _: mock_response
        mock_response.__exit__ = lambda *_: None
        mock_urlopen.return_value = mock_response

        # Mock temp file
        temp_file = MagicMock()
        temp_file.name = 'C:\\temp\\git.exe'
        temp_file.write = MagicMock()
        mock_temp.return_value.__enter__.return_value = temp_file

        # Mock urlretrieve to write to temp file
        def retrieve_side_effect(url, filename):
            # Just pretend we downloaded the file
            pass

        mock_retrieve.side_effect = retrieve_side_effect

        # Mock installer execution
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        result = install_claude.install_git_windows_download()
        assert result is True
        # Verify mock was configured and called
        mock_unlink.assert_called_once()
        mock_retrieve.assert_called_once()
        mock_run.assert_called_once()

    @patch('install_claude.get_git_installer_with_retry', return_value=None)
    @patch('install_claude.urlopen')
    def test_install_git_windows_download_ssl_error(self, mock_urlopen, mock_github):
        """Test Git download with SSL error fallback."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'<a href="/git/Git-2.43.0-64-bit.exe">Download</a>'
        mock_response.__enter__ = lambda _: mock_response
        mock_response.__exit__ = lambda *_: None

        mock_urlopen.side_effect = [
            urllib.error.URLError('SSL: CERTIFICATE_VERIFY_FAILED'),
            mock_response,
        ]

        with patch('install_claude.urlretrieve'), patch('install_claude.run_command') as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 1, '', '')
            result = install_claude.install_git_windows_download()
            assert result is False
            mock_github.assert_called_once()


class TestGitHubAPIDownload:
    """Test GitHub API-based Git installation."""

    @patch('install_claude.urlopen')
    def test_get_git_installer_url_success(self, mock_urlopen):
        """Test successful GitHub API response parsing."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            'tag_name': 'v2.51.1.windows.1',
            'assets': [
                {
                    'name': 'PortableGit-2.51.1-64-bit.7z.exe',
                    'browser_download_url': 'https://github.com/.../PortableGit-2.51.1-64-bit.7z.exe',
                },
                {
                    'name': 'Git-2.51.1-64-bit.exe',
                    'browser_download_url': 'https://github.com/.../Git-2.51.1-64-bit.exe',
                    'content_type': 'application/executable',
                },
            ],
        }).encode()
        mock_response.__enter__ = lambda _: mock_response
        mock_response.__exit__ = lambda *_: None
        mock_urlopen.return_value = mock_response

        result = install_claude.get_git_installer_url_from_github()
        assert result is not None
        assert 'Git-2.51.1-64-bit.exe' in result
        assert result.startswith('https://github.com/')

    @patch('install_claude.urlopen')
    def test_get_git_installer_url_no_assets(self, mock_urlopen):
        """Test handling of release with no suitable assets."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            'tag_name': 'v2.51.1.windows.1',
            'assets': [],
        }).encode()
        mock_response.__enter__ = lambda _: mock_response
        mock_response.__exit__ = lambda *_: None
        mock_urlopen.return_value = mock_response

        result = install_claude.get_git_installer_url_from_github()
        assert result is None

    @patch('install_claude.urlopen')
    def test_get_git_installer_url_network_error(self, mock_urlopen):
        """Test network failure returns None for graceful fallback."""
        mock_urlopen.side_effect = urllib.error.URLError('Network unreachable')

        result = install_claude.get_git_installer_url_from_github()
        assert result is None

    @patch('install_claude.urlopen')
    def test_get_git_installer_url_ssl_fallback(self, mock_urlopen):
        """Test SSL error fallback to unverified context."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            'tag_name': 'v2.51.1.windows.1',
            'assets': [
                {
                    'name': 'Git-2.51.1-64-bit.exe',
                    'browser_download_url': 'https://github.com/.../Git-2.51.1-64-bit.exe',
                },
            ],
        }).encode()
        mock_response.__enter__ = lambda _: mock_response
        mock_response.__exit__ = lambda *_: None

        # First call raises SSL error, second succeeds with unverified context
        mock_urlopen.side_effect = [
            urllib.error.URLError('SSL: CERTIFICATE_VERIFY_FAILED'),
            mock_response,
        ]

        result = install_claude.get_git_installer_url_from_github()
        assert result is not None
        assert 'Git-2.51.1-64-bit.exe' in result

    @patch('install_claude.get_git_installer_with_retry')
    @patch('install_claude.urlretrieve')
    @patch('install_claude.run_command')
    @patch('tempfile.NamedTemporaryFile')
    @patch('os.unlink')
    def test_install_git_via_github_api(self, mock_unlink, mock_temp, mock_run, mock_retrieve, mock_retry):
        """Test successful Git installation via GitHub API with retry logic."""
        # Mock GitHub API returning URL via retry function
        mock_retry.return_value = 'https://github.com/git-for-windows/git/releases/download/v2.51.1.windows.1/Git-2.51.1-64-bit.exe'

        # Mock temp file
        temp_file = MagicMock()
        temp_file.name = 'C:\\temp\\git.exe'
        mock_temp.return_value.__enter__.return_value = temp_file

        # Mock successful installation
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        result = install_claude.install_git_windows_download()
        assert result is True
        mock_retry.assert_called_once()
        mock_retrieve.assert_called_once()
        mock_run.assert_called_once()
        mock_unlink.assert_called_once()

    @patch('install_claude.get_git_installer_with_retry', return_value=None)
    @patch('install_claude.urlopen')
    @patch('install_claude.urlretrieve')
    @patch('install_claude.run_command')
    @patch('tempfile.NamedTemporaryFile')
    def test_install_git_fallback_to_scraping(self, mock_temp, mock_run, mock_retrieve, mock_urlopen, mock_retry):
        """Test fallback to git-scm.com scraping when GitHub API fails."""
        # Mock the download page response for fallback
        mock_response = MagicMock()
        mock_response.read.return_value = b'<a href="https://github.com/git-for-windows/git/releases/download/v2.51.0.windows.1/Git-2.51.0-64-bit.exe">Download</a>'
        mock_response.__enter__ = lambda _: mock_response
        mock_response.__exit__ = lambda *_: None
        mock_urlopen.return_value = mock_response

        # Mock temp file
        temp_file = MagicMock()
        temp_file.name = 'C:\\temp\\git.exe'
        mock_temp.return_value.__enter__.return_value = temp_file

        # Mock successful installation
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        result = install_claude.install_git_windows_download()
        assert result is True
        # Verify GitHub API with retry was tried first
        mock_retry.assert_called_once()
        # Verify fallback to scraping occurred
        mock_urlopen.assert_called()
        mock_retrieve.assert_called_once()
        mock_run.assert_called_once()


class TestWindowsEnvVar:
    """Test Windows environment variable setting."""

    @patch('platform.system', return_value='Windows')
    @patch('install_claude.run_command')
    def test_set_windows_env_var(self, mock_run, mock_system):
        """Test setting Windows environment variable."""
        # Verify mock configuration
        assert mock_system.return_value == 'Windows'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')
        install_claude.set_windows_env_var('TEST_VAR', 'test_value')
        assert os.environ['TEST_VAR'] == 'test_value'
        mock_run.assert_called_with(['setx', 'TEST_VAR', 'test_value'], capture_output=False)

    @patch('platform.system', return_value='Linux')
    def test_set_windows_env_var_on_linux(self, mock_system):
        """Test that env var setting only affects current process on Linux."""
        # Verify mock configuration
        assert mock_system.return_value == 'Linux'
        install_claude.set_windows_env_var('TEST_VAR', 'test_value')
        assert os.environ['TEST_VAR'] == 'test_value'


class TestPowerShellPolicy:
    """Test PowerShell execution policy configuration."""

    @patch('platform.system', return_value='Windows')
    @patch('install_claude.run_command')
    def test_configure_powershell_policy_already_configured(self, mock_run, mock_system):
        """Test PowerShell policy when already configured (no action needed)."""
        # Verify mock configuration
        assert mock_system.return_value == 'Windows'
        # Mock Get-ExecutionPolicy returning RemoteSigned
        mock_run.return_value = subprocess.CompletedProcess([], 0, 'RemoteSigned\n', '')
        install_claude.configure_powershell_policy()
        # Should only call Get-ExecutionPolicy, not Set-ExecutionPolicy
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert 'Get-ExecutionPolicy' in str(cmd)

    @patch('platform.system', return_value='Windows')
    @patch('install_claude.run_command')
    def test_configure_powershell_policy_needs_configuration(self, mock_run, mock_system):
        """Test PowerShell policy when it needs to be set."""
        # Verify mock configuration
        assert mock_system.return_value == 'Windows'
        # First call returns Restricted (needs configuration)
        # Second call sets the policy successfully
        mock_run.side_effect = [
            subprocess.CompletedProcess([], 0, 'Restricted\n', ''),
            subprocess.CompletedProcess([], 0, '', ''),
        ]
        install_claude.configure_powershell_policy()
        # Should call Get-ExecutionPolicy first, then Set-ExecutionPolicy
        assert mock_run.call_count == 2
        # First call should be Get-ExecutionPolicy
        first_cmd = mock_run.call_args_list[0][0][0]
        assert 'Get-ExecutionPolicy' in str(first_cmd)
        # Second call should be Set-ExecutionPolicy
        second_cmd = mock_run.call_args_list[1][0][0]
        assert 'Set-ExecutionPolicy' in str(second_cmd)

    @patch('platform.system', return_value='Windows')
    @patch('install_claude.run_command')
    def test_configure_powershell_policy_group_policy_restriction(self, mock_run, mock_system):
        """Test PowerShell policy when restricted by Group Policy."""
        # Verify mock configuration
        assert mock_system.return_value == 'Windows'
        # First call returns Restricted, second call fails (Group Policy restriction)
        mock_run.side_effect = [
            subprocess.CompletedProcess([], 0, 'Restricted\n', ''),
            subprocess.CompletedProcess([], 1, '', 'Access denied'),
        ]
        install_claude.configure_powershell_policy()
        # Should attempt both Get and Set
        assert mock_run.call_count == 2

    @patch('platform.system', return_value='Linux')
    @patch('install_claude.run_command')
    def test_configure_powershell_policy_skip_linux(self, mock_run, mock_system):
        """Test that PowerShell policy is skipped on Linux."""
        # Verify mock configuration
        assert mock_system.return_value == 'Linux'
        install_claude.configure_powershell_policy()
        mock_run.assert_not_called()


class TestNodeJsInstallation:
    """Test Node.js installation functions."""

    @patch('install_claude.find_command')
    @patch('install_claude.run_command')
    def test_get_node_version_found(self, mock_run, mock_find):
        """Test getting Node.js version when installed."""
        mock_find.return_value = '/usr/bin/node'
        mock_run.return_value = subprocess.CompletedProcess([], 0, 'v18.17.0\n', '')
        version = install_claude.get_node_version()
        assert version == 'v18.17.0'

    @patch('shutil.which', return_value=None)
    def test_get_node_version_not_found(self, mock_find):
        """Test getting Node.js version when not installed."""
        # Verify mock configuration
        assert mock_find.return_value is None
        version = install_claude.get_node_version()
        assert version is None

    @patch('install_claude.check_winget', return_value=True)
    @patch('install_claude.run_command')
    def test_install_nodejs_winget_success(self, mock_run, mock_winget):
        """Test successful Node.js installation via winget."""
        # Verify mock configuration
        assert mock_winget.return_value is True
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')
        result = install_claude.install_nodejs_winget('user')
        assert result is True
        assert 'OpenJS.NodeJS.LTS' in mock_run.call_args[0][0]

    @patch('install_claude.urlopen')
    @patch('install_claude.urlretrieve')  # Changed to patch directly from install_claude
    @patch('platform.system', return_value='Windows')
    @patch('platform.machine', return_value='x86_64')
    @patch('install_claude.run_command')
    @patch('tempfile.NamedTemporaryFile')
    def test_install_nodejs_direct_windows(self, mock_temp, mock_run, mock_machine, mock_system, mock_retrieve, mock_urlopen):
        """Test direct Node.js installation on Windows."""
        # Verify mock configurations
        assert mock_system.return_value == 'Windows'
        assert mock_machine.return_value == 'x86_64'
        # Mock API response
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps([
            {'version': 'v20.10.0', 'lts': 'Iron'},
            {'version': 'v19.0.0', 'lts': False},
        ]).encode()
        mock_response.__enter__ = lambda _: mock_response
        mock_response.__exit__ = lambda *_: None
        mock_urlopen.return_value = mock_response

        # Mock temp file
        temp_file = MagicMock()
        temp_file.name = 'C:\\temp\\node.msi'
        temp_file.write = MagicMock()
        mock_temp.return_value.__enter__.return_value = temp_file

        # Mock urlretrieve to write to temp file
        def retrieve_side_effect(url, filename):
            # Just pretend we downloaded the file
            pass

        mock_retrieve.side_effect = retrieve_side_effect

        # Mock installer execution
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        result = install_claude.install_nodejs_direct()
        assert result is True
        mock_retrieve.assert_called_once()
        assert 'node-v20.10.0-x64.msi' in mock_retrieve.call_args[0][0]

    @patch('install_claude.find_command')
    @patch('install_claude.run_command')
    def test_install_nodejs_homebrew(self, mock_run, mock_find):
        """Test Node.js LTS installation via Homebrew."""
        mock_find.return_value = '/usr/local/bin/brew'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')
        result = install_claude.install_nodejs_homebrew()
        assert result is True
        # Verify brew install uses node@22 (LTS), not node (current)
        install_calls = [str(call) for call in mock_run.call_args_list]
        assert any('node@22' in call for call in install_calls), \
            'Homebrew should install node@22 (LTS), not node (current)'
        # Verify brew link is called for keg-only formula
        assert any('link' in call for call in install_calls), \
            'brew link should be called for keg-only node@22 formula'

    @patch('shutil.which', return_value='/usr/local/bin/brew')
    @patch('install_claude.run_command')
    def test_install_nodejs_homebrew_install_fails(self, mock_run, mock_which):
        """Homebrew returns False when brew install node@22 fails."""
        # Verify mock configuration
        assert mock_which.return_value == '/usr/local/bin/brew'
        # brew update succeeds, brew install node@22 fails
        mock_run.side_effect = [
            subprocess.CompletedProcess([], 0, '', ''),  # brew update
            subprocess.CompletedProcess([], 1, '', 'Error installing'),  # brew install node@22
        ]
        result = install_claude.install_nodejs_homebrew()
        assert result is False

    @patch('shutil.which', return_value='/usr/local/bin/brew')
    @patch('install_claude.run_command')
    def test_install_nodejs_homebrew_link_fails_still_succeeds(self, mock_run, mock_which):
        """Homebrew returns True even when brew link fails."""
        del mock_which  # Mark as intentionally unused (mock active via decorator)
        # Verify shutil.which is properly mocked
        # brew update succeeds, brew install succeeds, brew link fails
        mock_run.side_effect = [
            subprocess.CompletedProcess([], 0, '', ''),  # brew update
            subprocess.CompletedProcess([], 0, '', ''),  # brew install node@22
            subprocess.CompletedProcess([], 1, '', 'Warning: Already linked'),  # brew link
        ]
        result = install_claude.install_nodejs_homebrew()
        assert result is True

    @patch('install_claude.run_command')
    def test_install_nodejs_apt(self, mock_run):
        """Test Node.js installation via apt."""
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')
        result = install_claude.install_nodejs_apt()
        assert result is True


class TestEnsureNodejsCheckClaudeCompat:
    """Test ensure_nodejs check_claude_compat parameter behavior."""

    @patch('platform.system', return_value='Linux')
    @patch('install_claude.get_node_version', return_value='v25.5.0')
    @patch('install_claude.compare_versions', return_value=True)
    def test_check_claude_compat_false_accepts_v25(self, mock_compare, mock_version, mock_system):
        """Node.js v25 accepted when check_claude_compat=False."""
        # Verify mock configurations
        assert mock_system.return_value == 'Linux'
        assert mock_version.return_value == 'v25.5.0'
        assert mock_compare.return_value is True
        result = install_claude.ensure_nodejs(check_claude_compat=False)
        assert result is True

    @patch('platform.system', return_value='Linux')
    @patch('install_claude.get_node_version', return_value='v25.5.0')
    @patch('install_claude.check_nodejs_compatibility', return_value=False)
    def test_check_claude_compat_true_rejects_v25(self, mock_compat, mock_version, mock_system):
        """Node.js v25 rejected when check_claude_compat=True (default)."""
        # Verify mock configurations
        assert mock_system.return_value == 'Linux'
        assert mock_version.return_value == 'v25.5.0'
        result = install_claude.ensure_nodejs(check_claude_compat=True)
        assert result is False
        mock_compat.assert_called_once()

    @patch('platform.system', return_value='Linux')
    @patch('install_claude.get_node_version', return_value='v25.5.0')
    @patch('install_claude.check_nodejs_compatibility', return_value=False)
    def test_default_check_claude_compat_rejects_v25(self, mock_compat, mock_version, mock_system):
        """Default behavior (check_claude_compat=True) preserved -- v25 rejected."""
        # Verify mock configurations
        assert mock_system.return_value == 'Linux'
        assert mock_version.return_value == 'v25.5.0'
        result = install_claude.ensure_nodejs()
        assert result is False
        mock_compat.assert_called_once()

    @patch('platform.system', return_value='Linux')
    @patch('install_claude.get_node_version', return_value='v25.5.0')
    @patch('install_claude.check_nodejs_compatibility')
    @patch('install_claude.compare_versions', return_value=True)
    def test_check_claude_compat_false_skips_compat_check(self, mock_compare, mock_compat, mock_version, mock_system):
        """check_nodejs_compatibility() not called when check_claude_compat=False."""
        # Verify mock configurations
        assert mock_system.return_value == 'Linux'
        assert mock_version.return_value == 'v25.5.0'
        assert mock_compare.return_value is True
        result = install_claude.ensure_nodejs(check_claude_compat=False)
        assert result is True
        mock_compat.assert_not_called()

    @patch('platform.system', return_value='Linux')
    @patch('install_claude.get_node_version', return_value='v22.0.0')
    @patch('install_claude.check_nodejs_compatibility', return_value=True)
    @patch('install_claude.compare_versions', return_value=True)
    def test_check_claude_compat_true_with_compatible_version(self, mock_compare, mock_compat, mock_version, mock_system):
        """Compatible version passes with check_claude_compat=True."""
        # Verify mock configurations
        assert mock_system.return_value == 'Linux'
        assert mock_version.return_value == 'v22.0.0'
        assert mock_compat.return_value is True
        assert mock_compare.return_value is True
        result = install_claude.ensure_nodejs(check_claude_compat=True)
        assert result is True


class TestVerifyNodejsVersion:
    """Test _verify_nodejs_version helper function."""

    @patch('install_claude.get_node_version', return_value='v22.0.0')
    @patch('install_claude.check_nodejs_compatibility', return_value=True)
    @patch('install_claude.compare_versions', return_value=True)
    def test_compatible_version_passes(self, mock_compare, mock_compat, mock_version):
        """Compatible Node.js version passes all checks."""
        # Verify mock configurations
        assert mock_version.return_value == 'v22.0.0'
        assert mock_compat.return_value is True
        assert mock_compare.return_value is True
        result = install_claude._verify_nodejs_version(check_claude_compat=True)
        assert result is True
        mock_compat.assert_called_once()

    @patch('install_claude.get_node_version', return_value='v25.5.0')
    @patch('install_claude.check_nodejs_compatibility', return_value=False)
    def test_v25_rejected_with_compat_check(self, mock_compat, mock_version):
        """Node.js v25 rejected when check_claude_compat=True."""
        # Verify mock configurations
        assert mock_version.return_value == 'v25.5.0'
        assert mock_compat.return_value is False
        result = install_claude._verify_nodejs_version(check_claude_compat=True)
        assert result is False

    @patch('install_claude.get_node_version', return_value='v25.5.0')
    @patch('install_claude.compare_versions', return_value=True)
    def test_v25_accepted_without_compat_check(self, mock_compare, mock_version):
        """Node.js v25 accepted when check_claude_compat=False."""
        # Verify mock configurations
        assert mock_version.return_value == 'v25.5.0'
        assert mock_compare.return_value is True
        result = install_claude._verify_nodejs_version(check_claude_compat=False)
        assert result is True

    @patch('install_claude.get_node_version', return_value=None)
    def test_no_node_returns_false(self, mock_version):
        """Returns False when Node.js not found."""
        # Verify mock configuration
        assert mock_version.return_value is None
        result = install_claude._verify_nodejs_version(check_claude_compat=True)
        assert result is False

    @patch('install_claude.get_node_version', return_value='v16.0.0')
    @patch('install_claude.check_nodejs_compatibility', return_value=True)
    @patch('install_claude.compare_versions', return_value=False)
    def test_below_minimum_version_rejected(self, mock_compare, mock_compat, mock_version):
        """Node.js below minimum version rejected even with compatible v25 check."""
        # Verify mock configurations
        assert mock_version.return_value == 'v16.0.0'
        assert mock_compat.return_value is True
        assert mock_compare.return_value is False
        result = install_claude._verify_nodejs_version(check_claude_compat=True)
        assert result is False


class TestCheckNodejsCompatibilityVersionAware:
    """Test version-aware Node.js compatibility checking."""

    @patch('install_claude.get_node_version', return_value='v25.5.0')
    def test_v25_rejected_when_no_fixed_version(self, mock_version):
        """v25 rejected when CLAUDE_NPM_SLOWBUFFER_FIXED_VERSION is None."""
        assert mock_version.return_value == 'v25.5.0'
        result = install_claude.check_nodejs_compatibility(claude_code_version='2.1.39')
        assert result is False

    @patch('install_claude.get_node_version', return_value='v25.5.0')
    @patch.object(install_claude, 'CLAUDE_NPM_SLOWBUFFER_FIXED_VERSION', '2.2.0')
    @patch('install_claude.compare_versions', return_value=True)
    def test_v25_accepted_when_claude_version_fixed(self, mock_compare, mock_version):
        """v25 accepted when Claude Code version has SlowBuffer fix."""
        assert mock_version.return_value == 'v25.5.0'
        assert mock_compare.return_value is True
        result = install_claude.check_nodejs_compatibility(claude_code_version='2.3.0')
        assert result is True

    @patch('install_claude.get_node_version', return_value='v25.5.0')
    @patch.object(install_claude, 'CLAUDE_NPM_SLOWBUFFER_FIXED_VERSION', '2.2.0')
    @patch('install_claude.compare_versions', return_value=False)
    def test_v25_rejected_when_claude_version_too_old(self, mock_compare, mock_version):
        """v25 rejected when Claude Code version is before the fix."""
        assert mock_version.return_value == 'v25.5.0'
        assert mock_compare.return_value is False
        result = install_claude.check_nodejs_compatibility(claude_code_version='2.1.39')
        assert result is False

    @patch('install_claude.get_node_version', return_value='v25.5.0')
    @patch.object(install_claude, 'CLAUDE_NPM_SLOWBUFFER_FIXED_VERSION', '2.2.0')
    def test_v25_rejected_when_no_claude_version_provided(self, mock_version):
        """v25 rejected when claude_code_version is None (unknown version)."""
        assert mock_version.return_value == 'v25.5.0'
        result = install_claude.check_nodejs_compatibility(claude_code_version=None)
        assert result is False

    @patch('install_claude.get_node_version', return_value='v22.0.0')
    def test_v22_always_compatible(self, mock_version):
        """v22 is always compatible regardless of Claude Code version."""
        assert mock_version.return_value == 'v22.0.0'
        result = install_claude.check_nodejs_compatibility(claude_code_version=None)
        assert result is True

    @patch('install_claude.get_node_version', return_value='v16.0.0')
    def test_v16_always_rejected(self, mock_version):
        """v16 is always rejected (below minimum v18)."""
        assert mock_version.return_value == 'v16.0.0'
        result = install_claude.check_nodejs_compatibility(claude_code_version=None)
        assert result is False


class TestClaudeInstallation:
    """Test Claude Code installation functions."""

    @patch('install_claude.find_command')
    @patch('platform.system', return_value='Windows')
    @patch('pathlib.Path.exists', return_value=True)
    def test_get_claude_version_windows(self, mock_exists, mock_system, mock_find):
        """Test getting Claude version on Windows."""
        # Verify mock configurations
        assert mock_system.return_value == 'Windows'
        assert mock_exists.return_value is True
        mock_find.return_value = 'C:\\Program Files\\nodejs\\claude.cmd'
        with patch('install_claude.run_command') as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0, 'claude, version 0.7.7', '')
            version = install_claude.get_claude_version()
            assert version == '0.7.7'

    @patch('install_claude.find_command')
    @patch('install_claude.run_command')
    def test_get_claude_version_found(self, mock_run, mock_find):
        """Test getting Claude version when found in PATH."""
        mock_find.return_value = '/usr/local/bin/claude'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '@anthropic-ai/claude-code/0.7.7', '')
        version = install_claude.get_claude_version()
        assert version == '0.7.7'

    @patch('platform.system', return_value='Windows')
    @patch('pathlib.Path.exists', return_value=True)
    @patch('install_claude.find_command')
    @patch('install_claude.run_command')
    def test_install_claude_npm_windows(self, mock_run, mock_find, mock_exists, mock_system):
        """Test Claude installation via npm on Windows."""
        # Verify mock configurations
        assert mock_system.return_value == 'Windows'
        assert mock_exists.return_value is True
        mock_find.return_value = 'C:\\Program Files\\nodejs\\npm.cmd'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')
        result = install_claude.install_claude_npm()
        assert result is True
        assert '@anthropic-ai/claude-code@latest' in mock_run.call_args[0][0]

    @patch('platform.system', return_value='Linux')
    @patch('install_claude.find_command', return_value='/usr/bin/npm')
    @patch('install_claude.needs_sudo_for_npm', return_value=True)
    @patch('install_claude.run_command')
    @patch('install_claude._run_with_sudo_fallback')
    def test_install_claude_npm_sudo_fallback(
        self, mock_sudo, mock_run, mock_needs_sudo, mock_find, mock_system,
    ):
        """Test Claude installation with sudo fallback via _run_with_sudo_fallback."""
        with patch('pathlib.Path.exists', return_value=True):
            assert mock_system.return_value == 'Linux'
            assert mock_find.return_value == '/usr/bin/npm'
            assert mock_needs_sudo.return_value is True
            # Non-sudo attempt fails via run_command
            mock_run.return_value = subprocess.CompletedProcess([], 1, '', 'permission denied')
            # Sudo attempt succeeds via _run_with_sudo_fallback
            mock_sudo.return_value = subprocess.CompletedProcess([], 0, '', '')

            result = install_claude.install_claude_npm()

            assert result is True
            assert mock_run.call_count == 1  # Only non-sudo via run_command
            mock_sudo.assert_called_once()
            sudo_cmd = mock_sudo.call_args[0][0]
            assert sudo_cmd[0] == '/usr/bin/npm'

    @patch('platform.system', return_value='Windows')
    @patch('install_claude.get_claude_version', return_value='2.1.39')
    @patch('install_claude.urlopen')
    @patch('tempfile.NamedTemporaryFile')
    @patch('install_claude.run_command')
    @patch('install_claude.verify_claude_installation')
    @patch('install_claude.ensure_local_bin_in_path_windows')
    @patch('install_claude.update_install_method_config')
    def test_install_claude_native_windows(
        self,
        mock_update_config,
        mock_ensure_path,
        mock_verify,
        mock_run,
        mock_temp,
        mock_urlopen,
        mock_get_version,
        mock_system,
    ):
        """Test native Claude installer on Windows."""
        # Verify mock configuration
        assert mock_system.return_value == 'Windows'
        assert mock_update_config is not None
        assert mock_get_version.return_value == '2.1.39'
        # Mock installer script download
        mock_response = MagicMock()
        mock_response.read.return_value = b'# PowerShell installer script'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        # Mock temp file
        temp_file = MagicMock()
        temp_file.name = 'C:\\temp\\install.ps1'
        temp_file.write = MagicMock()
        mock_temp.return_value.__enter__.return_value = temp_file

        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        # Mock the new verification and PATH functions
        mock_verify.return_value = (True, 'C:\\Users\\Test\\.local\\bin\\claude.exe', 'native')
        mock_ensure_path.return_value = True

        result = install_claude.install_claude_native_windows()
        assert result is True


class TestEnsureFunctions:
    """Test the ensure_* functions that orchestrate installations."""

    @patch('install_claude.find_bash_windows')
    def test_ensure_git_bash_windows_already_installed(self, mock_find):
        """Test ensure_git_bash_windows when already installed."""
        mock_find.return_value = 'C:\\Program Files\\Git\\bin\\bash.exe'
        result = install_claude.ensure_git_bash_windows()
        assert result == 'C:\\Program Files\\Git\\bin\\bash.exe'

    @patch('install_claude.find_bash_windows')
    @patch('install_claude.check_winget', return_value=True)
    @patch('install_claude.install_git_windows_winget', return_value=True)
    @patch('time.sleep')
    def test_ensure_git_bash_windows_winget_install(self, mock_sleep, mock_install, mock_winget, mock_find):
        """Test Git Bash installation via winget."""
        # Verify mock configurations
        assert mock_winget.return_value is True
        assert mock_install.return_value is True
        mock_find.side_effect = [None, 'C:\\Program Files\\Git\\bin\\bash.exe']
        result = install_claude.ensure_git_bash_windows()
        assert result == 'C:\\Program Files\\Git\\bin\\bash.exe'
        mock_install.assert_called_once()
        mock_sleep.assert_called_once()

    @patch('platform.system', return_value='Windows')
    @patch('install_claude.get_node_version')
    @patch('install_claude.compare_versions')
    def test_ensure_nodejs_already_sufficient(self, mock_compare, mock_get_version, mock_system):
        """Test ensure_nodejs when version is already sufficient."""
        # Verify mock configuration
        assert mock_system.return_value == 'Windows'
        mock_get_version.return_value = 'v20.10.0'
        mock_compare.return_value = True
        result = install_claude.ensure_nodejs()
        assert result is True

    @patch('platform.system', return_value='Windows')
    @patch('install_claude.get_node_version', return_value=None)
    @patch('install_claude.check_winget', return_value=False)
    @patch('install_claude.install_nodejs_direct', return_value=True)
    @patch('time.sleep')
    def test_ensure_nodejs_direct_install(self, mock_sleep, mock_install, mock_winget, mock_get_version, mock_system):
        """Test Node.js installation via direct download."""
        # Verify mock configurations
        assert mock_system.return_value == 'Windows'
        assert mock_get_version.return_value is None
        assert mock_winget.return_value is False
        assert mock_install.return_value is True
        with (
            patch('install_claude.get_node_version') as mock_get_after,
            patch('install_claude.compare_versions', return_value=True),
            patch('install_claude.check_nodejs_compatibility', return_value=True),
        ):
            # _verify_nodejs_version calls get_node_version once;
            # check_nodejs_compatibility is mocked and does not consume side_effect
            mock_get_after.side_effect = [None, 'v20.10.0']
            result = install_claude.ensure_nodejs()
            assert result is True
            mock_install.assert_called_once()
            mock_sleep.assert_called()

    @patch('install_claude.verify_claude_installation')
    @patch('install_claude.get_latest_claude_version')
    @patch('install_claude.get_claude_version')
    def test_ensure_claude_already_installed(self, mock_get_version, mock_get_latest, mock_verify):
        """Test Claude when already installed and up-to-date (no upgrade attempted)."""
        mock_get_version.return_value = '0.7.0'
        mock_get_latest.return_value = '0.7.0'  # Same version - already up-to-date
        # Mock verify to return native source to prevent migration logic
        mock_verify.return_value = (True, '/usr/local/bin/claude', 'native')
        result = install_claude.ensure_claude()
        assert result is True
        # Should check version once and check latest once, but not upgrade
        assert mock_get_version.call_count >= 1  # At least once (may be more with migration check)
        mock_get_latest.assert_called_once()

    @patch('install_claude.get_claude_version', return_value=None)
    @patch('install_claude.install_claude_npm', return_value=False)
    @patch('platform.system', return_value='Windows')
    @patch('install_claude.install_claude_native_cross_platform', return_value=True)
    def test_ensure_claude_native_fallback(self, mock_native, mock_system, mock_npm, mock_get_version):
        """Test Claude installation fallback to native installer."""
        # Verify mock configurations
        assert mock_system.return_value == 'Windows'
        assert mock_get_version.return_value is None
        assert mock_npm.return_value is False
        assert mock_native.return_value is True
        result = install_claude.ensure_claude()
        assert result is True
        mock_native.assert_called_once()


class TestEnsureClaudeSourceAwareUpgrade:
    """Test source-aware upgrade logic in ensure_claude().

    When Claude is already installed but outdated, the upgrade method should
    match the installation source (native or npm) rather than unconditionally
    using npm.
    """

    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'auto'}, clear=False)
    @patch('install_claude._verify_upgrade_version', return_value=(True, '2.1.39'))
    @patch('install_claude.install_claude_npm')
    @patch('install_claude.install_claude_native_cross_platform', return_value=True)
    @patch('install_claude.compare_versions', return_value=False)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.39')
    @patch('install_claude.get_claude_version')
    @patch('install_claude.verify_claude_installation')
    def test_upgrade_native_source_uses_native_installer(
        self,
        mock_verify,
        mock_get_version,
        mock_get_latest,
        mock_compare,
        mock_native,
        mock_npm,
        mock_verify_upgrade,
    ):
        """When source is native in auto mode, upgrade should use native installer."""
        mock_get_version.side_effect = ['2.0.76', '2.1.39']
        mock_verify.return_value = (True, '/home/user/.local/bin/claude', 'native')

        result = install_claude.ensure_claude()
        assert result is True
        # Verify mock configurations
        assert mock_get_latest.return_value == '2.1.39'
        assert mock_compare.return_value is False
        # Native should be used, npm should NOT
        mock_native.assert_called()
        mock_npm.assert_not_called()
        mock_verify_upgrade.assert_called()

    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'npm'}, clear=False)
    @patch('install_claude.install_claude_npm', return_value=True)
    @patch('install_claude.install_claude_native_cross_platform')
    @patch('install_claude.compare_versions', return_value=False)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.39')
    @patch('install_claude.get_claude_version')
    @patch('install_claude.verify_claude_installation')
    def test_upgrade_npm_source_uses_npm(
        self,
        mock_verify,
        mock_get_version,
        mock_get_latest,
        mock_compare,
        mock_native,
        mock_npm,
    ):
        """When CLAUDE_CODE_TOOLBOX_INSTALL_METHOD=npm, upgrade should use npm directly."""
        mock_get_version.side_effect = ['2.0.76', '2.1.39']
        mock_verify.return_value = (True, '/usr/lib/node_modules/.bin/claude', 'npm')

        result = install_claude.ensure_claude()
        assert result is True
        # Verify mock configurations
        assert mock_get_latest.return_value == '2.1.39'
        assert mock_compare.return_value is False
        # npm should be used, native should NOT
        mock_npm.assert_called()
        mock_native.assert_not_called()

    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'auto'}, clear=False)
    @patch('install_claude.install_claude_npm', return_value=True)
    @patch('install_claude.install_claude_native_cross_platform', return_value=False)
    @patch('install_claude.compare_versions', return_value=False)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.39')
    @patch('install_claude.get_claude_version')
    @patch('install_claude.verify_claude_installation')
    @patch('install_claude.update_install_method_config')
    def test_upgrade_native_source_fallback_to_npm_on_failure(
        self,
        mock_update_config,
        mock_verify,
        mock_get_version,
        mock_get_latest,
        mock_compare,
        mock_native,
        mock_npm,
    ):
        """When native upgrade fails in auto mode, should fall back to npm."""
        assert mock_update_config is not None
        mock_get_version.side_effect = ['2.0.76', '2.1.39']
        mock_verify.return_value = (True, '/home/user/.local/bin/claude', 'native')

        result = install_claude.ensure_claude()
        assert result is True
        # Verify mock configurations
        assert mock_get_latest.return_value == '2.1.39'
        assert mock_compare.return_value is False
        # Both should be called: native first (fails), then npm fallback
        mock_native.assert_called()
        mock_npm.assert_called()

    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'native'}, clear=False)
    @patch('install_claude.install_claude_npm')
    @patch('install_claude.install_claude_native_cross_platform', return_value=False)
    @patch('install_claude.compare_versions', return_value=False)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.39')
    @patch('install_claude.get_claude_version', return_value='2.0.76')
    @patch('install_claude.verify_claude_installation')
    def test_upgrade_native_mode_no_npm_fallback(
        self,
        mock_verify,
        mock_get_version,
        mock_get_latest,
        mock_compare,
        mock_native,
        mock_npm,
    ):
        """When CLAUDE_CODE_TOOLBOX_INSTALL_METHOD=native, no npm fallback on upgrade failure."""
        mock_verify.return_value = (True, '/home/user/.local/bin/claude', 'native')

        result = install_claude.ensure_claude()
        assert result is True
        # Verify mock configurations
        assert mock_get_version.return_value == '2.0.76'
        assert mock_get_latest.return_value == '2.1.39'
        assert mock_compare.return_value is False
        # Native should be called, npm should NOT (no fallback in native mode)
        mock_native.assert_called()
        mock_npm.assert_not_called()

    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'npm'}, clear=False)
    @patch('install_claude.install_claude_npm', return_value=True)
    @patch('install_claude.install_claude_native_cross_platform')
    @patch('install_claude.compare_versions', return_value=False)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.39')
    @patch('install_claude.get_claude_version')
    @patch('install_claude.verify_claude_installation')
    def test_upgrade_npm_mode_always_uses_npm(
        self,
        mock_verify,
        mock_get_version,
        mock_get_latest,
        mock_compare,
        mock_native,
        mock_npm,
    ):
        """When CLAUDE_CODE_TOOLBOX_INSTALL_METHOD=npm, always use npm regardless of source."""
        mock_get_version.side_effect = ['2.0.76', '2.1.39']
        # Source is native, but install_method is npm
        mock_verify.return_value = (True, '/home/user/.local/bin/claude', 'native')

        result = install_claude.ensure_claude()
        assert result is True
        # Verify mock configurations
        assert mock_get_latest.return_value == '2.1.39'
        assert mock_compare.return_value is False
        # npm should be used regardless of native source
        mock_npm.assert_called()
        mock_native.assert_not_called()

    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'auto'}, clear=False)
    @patch('install_claude._verify_upgrade_version', return_value=(True, '2.1.39'))
    @patch('install_claude.install_claude_npm')
    @patch('install_claude.install_claude_native_cross_platform', return_value=True)
    @patch('install_claude.compare_versions', return_value=False)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.39')
    @patch('install_claude.get_claude_version')
    @patch('install_claude.verify_claude_installation')
    def test_upgrade_unknown_source_tries_native_first(
        self,
        mock_verify,
        mock_get_version,
        mock_get_latest,
        mock_compare,
        mock_native,
        mock_npm,
        mock_verify_upgrade,
    ):
        """When source is unknown in auto mode, try native first, then npm fallback."""
        mock_get_version.side_effect = ['2.0.76', '2.1.39']
        mock_verify.return_value = (True, '/usr/bin/claude', 'unknown')

        result = install_claude.ensure_claude()
        assert result is True
        # Verify mock configurations
        assert mock_get_latest.return_value == '2.1.39'
        assert mock_compare.return_value is False
        # Native should be tried first for unknown source
        mock_native.assert_called()
        # npm should NOT be called since native succeeded and version verified
        mock_npm.assert_not_called()
        mock_verify_upgrade.assert_called()

    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'auto'}, clear=False)
    @patch('install_claude.install_claude_npm', return_value=True)
    @patch('install_claude.install_claude_native_cross_platform', return_value=False)
    @patch('install_claude.compare_versions', return_value=False)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.39')
    @patch('install_claude.get_claude_version')
    @patch('install_claude.verify_claude_installation')
    @patch('install_claude.update_install_method_config')
    def test_upgrade_unknown_source_npm_fallback(
        self,
        mock_update_config,
        mock_verify,
        mock_get_version,
        mock_get_latest,
        mock_compare,
        mock_native,
        mock_npm,
    ):
        """When source is unknown and native fails, fall back to npm."""
        assert mock_update_config is not None
        mock_get_version.side_effect = ['2.0.76', '2.1.39']
        mock_verify.return_value = (True, '/usr/bin/claude', 'unknown')

        result = install_claude.ensure_claude()
        assert result is True
        # Verify mock configurations
        assert mock_get_latest.return_value == '2.1.39'
        assert mock_compare.return_value is False
        # Native should be tried first
        mock_native.assert_called()
        # npm should be called as fallback since native failed
        mock_npm.assert_called()

    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'auto'}, clear=False)
    @patch('install_claude._verify_upgrade_version', return_value=(True, '2.1.39'))
    @patch('install_claude.install_claude_native_cross_platform', return_value=True)
    @patch('install_claude.compare_versions', return_value=False)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.39')
    @patch('install_claude.get_claude_version')
    @patch('install_claude.verify_claude_installation')
    def test_upgrade_version_reported_correctly_after_native(
        self,
        mock_verify,
        mock_get_version,
        mock_get_latest,
        mock_compare,
        mock_native,
        mock_verify_upgrade,
    ):
        """After native upgrade, _verify_upgrade_version() should be called to verify."""
        mock_get_version.side_effect = ['2.0.76', '2.1.39']
        mock_verify.return_value = (True, '/home/user/.local/bin/claude', 'native')

        result = install_claude.ensure_claude()
        assert result is True
        # Verify mock configurations
        assert mock_get_latest.return_value == '2.1.39'
        assert mock_compare.return_value is False
        mock_native.assert_called()
        # _verify_upgrade_version should be called after successful upgrade
        mock_verify_upgrade.assert_called_once()


class TestMainFunction:
    """Test the main installation flow."""

    @patch('platform.system', return_value='Windows')
    @patch('install_claude.ensure_git_bash_windows', return_value='C:\\Git\\bash.exe')
    @patch('install_claude.ensure_nodejs', return_value=True)
    @patch('install_claude.ensure_claude', return_value=True)
    @patch('install_claude.configure_powershell_policy')
    @patch('install_claude.update_path')
    @patch('install_claude.shutil.which', return_value=None)
    @patch('install_claude.set_windows_env_var')
    def test_main_windows_success(
        self,
        mock_set_env,
        mock_which,
        mock_update,
        mock_ps,
        mock_claude,
        mock_node,
        mock_git,
        mock_system,
    ):
        """Test successful main flow on Windows."""
        # Verify mock configurations
        assert mock_system.return_value == 'Windows'
        assert mock_git.return_value == 'C:\\Git\\bash.exe'
        assert mock_node.return_value is True
        assert mock_claude.return_value is True
        assert mock_which.return_value is None
        # Force npm installation method to ensure Node.js is installed
        with patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'npm'}), patch('sys.exit') as mock_exit:
            install_claude.main()
            mock_exit.assert_not_called()
            mock_git.assert_called_once()
            mock_node.assert_called_once()
            mock_claude.assert_called_once()
            mock_ps.assert_called_once()
            mock_update.assert_called_once()
            mock_set_env.assert_called_once()

    @patch('platform.system', return_value='Linux')
    @patch('install_claude.ensure_nodejs', return_value=True)
    @patch('install_claude.ensure_claude', return_value=True)
    def test_main_linux_success(self, mock_claude, mock_node, mock_system):
        """Test successful main flow on Linux."""
        # Verify mock configurations
        assert mock_system.return_value == 'Linux'
        assert mock_node.return_value is True
        assert mock_claude.return_value is True
        # Force npm installation method to ensure Node.js is installed
        with patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'npm'}), patch('sys.exit') as mock_exit:
            install_claude.main()
            mock_exit.assert_not_called()
            mock_node.assert_called_once()
            mock_claude.assert_called_once()

    @patch('platform.system', return_value='Windows')
    @patch('install_claude.ensure_git_bash_windows', return_value=None)
    def test_main_git_bash_failure(self, mock_git, mock_system):
        """Test main flow failure when Git Bash installation fails."""
        # Verify mock configurations
        assert mock_system.return_value == 'Windows'
        assert mock_git.return_value is None
        with pytest.raises(SystemExit) as exc_info:
            install_claude.main()
        assert exc_info.value.code == 1

    @patch('platform.system', return_value='Darwin')
    @patch('install_claude.ensure_nodejs', return_value=False)
    def test_main_nodejs_failure(self, mock_node, mock_system):
        """Test main flow failure when Node.js installation fails."""
        # Verify mock configurations
        assert mock_system.return_value == 'Darwin'
        assert mock_node.return_value is False
        # Force npm installation method to ensure Node.js is required
        with patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'npm'}), pytest.raises(SystemExit) as exc_info:
            install_claude.main()
        assert exc_info.value.code == 1


class TestUpdatePath:
    """Test PATH update function."""

    @patch('platform.system', return_value='Windows')
    @patch('pathlib.Path.exists', return_value=True)
    @patch.dict('os.environ', {'PATH': 'C:\\Windows\\System32', 'APPDATA': 'C:\\Users\\Test\\AppData\\Roaming'})
    def test_update_path_windows(self, mock_exists, mock_system):
        """Test PATH update on Windows."""
        # Verify mock configurations
        assert mock_system.return_value == 'Windows'
        assert mock_exists.return_value is True
        install_claude.update_path()
        npm_path = os.path.expandvars(r'%APPDATA%\npm')
        assert npm_path in os.environ['PATH']

    @patch('platform.system', return_value='Linux')
    def test_update_path_skip_linux(self, mock_system):
        """Test that PATH update is skipped on Linux."""
        # Verify mock configuration
        assert mock_system.return_value == 'Linux'
        original_path = os.environ.get('PATH', '')
        install_claude.update_path()
        assert os.environ.get('PATH', '') == original_path


class TestGitHubApiAuthentication:
    """Test GitHub API authentication and rate limiting in Git installer."""

    @patch.dict(os.environ, {'GITHUB_TOKEN': 'test-token-12345'})
    @patch('install_claude.urlopen')
    def test_uses_github_token_when_available(self, mock_urlopen):
        """Test that GITHUB_TOKEN is used for authentication in API request."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            'assets': [
                {
                    'name': 'Git-2.43.0-64-bit.exe',
                    'browser_download_url': 'https://github.com/.../Git-2.43.0-64-bit.exe',
                },
            ],
        }).encode()
        mock_response.__enter__ = lambda _: mock_response
        mock_response.__exit__ = lambda *_: None
        mock_urlopen.return_value = mock_response

        result = install_claude.get_git_installer_url_from_github()

        # Verify URL was called with a Request object
        assert mock_urlopen.called
        call_args = mock_urlopen.call_args
        request = call_args[0][0]

        # Check that Authorization header was set
        assert hasattr(request, 'get_header')
        assert request.get_header('Authorization') == 'Bearer test-token-12345'
        assert result is not None
        assert 'Git-2.43.0-64-bit.exe' in result

    @patch.dict(os.environ, {}, clear=True)
    @patch('install_claude.urlopen')
    def test_works_without_github_token(self, mock_urlopen):
        """Test that function works without GITHUB_TOKEN (unauthenticated)."""
        # Clear GITHUB_TOKEN from environment
        if 'GITHUB_TOKEN' in os.environ:
            del os.environ['GITHUB_TOKEN']

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            'assets': [
                {
                    'name': 'Git-2.43.0-64-bit.exe',
                    'browser_download_url': 'https://github.com/.../Git-2.43.0-64-bit.exe',
                },
            ],
        }).encode()
        mock_response.__enter__ = lambda _: mock_response
        mock_response.__exit__ = lambda *_: None
        mock_urlopen.return_value = mock_response

        result = install_claude.get_git_installer_url_from_github()

        assert result is not None
        assert 'Git-2.43.0-64-bit.exe' in result

        # Verify request was made (but without auth header)
        assert mock_urlopen.called
        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        # Authorization header should be None when token is not set
        assert request.get_header('Authorization') is None

    @patch.dict(os.environ, {'GITHUB_TOKEN': 'test-token'})
    @patch('install_claude.urlopen')
    def test_check_github_rate_limit_authenticated(self, mock_urlopen):
        """Test rate limit check with authentication."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            'resources': {
                'core': {
                    'limit': 5000,
                    'remaining': 4999,
                    'reset': 1700000000,
                },
            },
        }).encode()
        mock_response.__enter__ = lambda _: mock_response
        mock_response.__exit__ = lambda *_: None
        mock_urlopen.return_value = mock_response

        result = install_claude.check_github_rate_limit()

        assert result is not None
        assert result['limit'] == 5000
        assert result['remaining'] == 4999
        assert result['reset'] == 1700000000

        # Verify auth header was used
        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        assert request.get_header('Authorization') == 'Bearer test-token'

    @patch.dict(os.environ, {}, clear=True)
    @patch('install_claude.urlopen')
    def test_check_github_rate_limit_unauthenticated(self, mock_urlopen):
        """Test rate limit check without authentication (60/hour limit)."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            'resources': {
                'core': {
                    'limit': 60,
                    'remaining': 0,
                    'reset': 1700000000,
                },
            },
        }).encode()
        mock_response.__enter__ = lambda _: mock_response
        mock_response.__exit__ = lambda *_: None
        mock_urlopen.return_value = mock_response

        result = install_claude.check_github_rate_limit()

        assert result is not None
        assert result['limit'] == 60
        assert result['remaining'] == 0

    @patch('install_claude.urlopen')
    def test_check_github_rate_limit_network_error(self, mock_urlopen):
        """Test rate limit check returns None on network error."""
        mock_urlopen.side_effect = urllib.error.URLError('Network unreachable')

        result = install_claude.check_github_rate_limit()

        assert result is None


def _create_mock_http_error(
    code: int,
    msg: str = 'Error',
    headers_get_return: str | None = None,
    headers_get_side_effect: Callable[[str], str | None] | None = None,
) -> urllib.error.HTTPError:
    """Create an HTTPError with mocked headers for testing.

    This helper properly creates an HTTPError with a Message object for headers
    to satisfy type checkers, then replaces headers with a MagicMock.

    Args:
        code: HTTP error code (e.g., 403, 404).
        msg: Error message.
        headers_get_return: Value for headers.get() to return for any key.
        headers_get_side_effect: Callable for headers.get() side_effect.

    Returns:
        HTTPError with mocked headers attribute.
    """
    from email.message import Message
    headers = Message()
    error = urllib.error.HTTPError(
        'https://api.github.com/repos/git-for-windows/git/releases/latest',
        code,
        msg,
        headers,
        None,
    )
    # Replace headers with MagicMock for easier testing
    mock_headers = MagicMock()
    if headers_get_side_effect is not None:
        mock_headers.get = MagicMock(side_effect=headers_get_side_effect)
    else:
        mock_headers.get = MagicMock(return_value=headers_get_return)
    object.__setattr__(error, 'headers', mock_headers)
    return error


class TestGitInstallerRetryLogic:
    """Test retry logic for Git installer download."""

    @patch('time.sleep')
    @patch('install_claude.urlopen')
    def test_retry_on_rate_limit_403(self, mock_urlopen, mock_sleep):
        """Test that function retries on 403 rate limit error."""
        # Create HTTPError with mock headers using side_effect for x-ratelimit-reset
        reset_time = str(int(time.time()) + 60)
        rate_limit_error = _create_mock_http_error(
            403,
            'rate limit exceeded',
            headers_get_side_effect=lambda k: reset_time if k == 'x-ratelimit-reset' else None,
        )

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            'assets': [
                {
                    'name': 'Git-2.43.0-64-bit.exe',
                    'browser_download_url': 'https://github.com/.../Git-2.43.0-64-bit.exe',
                },
            ],
        }).encode()
        mock_response.__enter__ = lambda _: mock_response
        mock_response.__exit__ = lambda *_: None

        mock_urlopen.side_effect = [rate_limit_error, mock_response]

        result = install_claude.get_git_installer_with_retry(max_retries=2)

        assert result is not None
        assert 'Git-2.43.0-64-bit.exe' in result
        # Verify sleep was called for backoff
        mock_sleep.assert_called()

    @patch('time.sleep')
    @patch('install_claude.urlopen')
    def test_retry_respects_retry_after_header(self, mock_urlopen, mock_sleep):
        """Test that function respects Retry-After header."""
        rate_limit_error = _create_mock_http_error(
            403,
            'rate limit exceeded',
            headers_get_side_effect=lambda k: '30' if k == 'retry-after' else None,
        )

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            'assets': [
                {
                    'name': 'Git-2.43.0-64-bit.exe',
                    'browser_download_url': 'https://github.com/.../Git-2.43.0-64-bit.exe',
                },
            ],
        }).encode()
        mock_response.__enter__ = lambda _: mock_response
        mock_response.__exit__ = lambda *_: None

        mock_urlopen.side_effect = [rate_limit_error, mock_response]

        result = install_claude.get_git_installer_with_retry(max_retries=2)

        assert result is not None
        # Verify sleep was called with capped value (max 60 seconds)
        mock_sleep.assert_called_with(30)

    @patch('time.sleep')
    @patch('install_claude.urlopen')
    def test_returns_none_after_max_retries(self, mock_urlopen, mock_sleep):
        """Test that function returns None after exhausting retries."""
        rate_limit_error = _create_mock_http_error(403, 'rate limit exceeded')

        mock_urlopen.side_effect = rate_limit_error

        result = install_claude.get_git_installer_with_retry(max_retries=3)

        assert result is None
        # Should have slept twice (before retry 2 and retry 3)
        assert mock_sleep.call_count == 2

    @patch('time.sleep')
    @patch('install_claude.urlopen')
    def test_retry_on_network_error(self, mock_urlopen, mock_sleep):
        """Test that function retries on network errors."""
        network_error = urllib.error.URLError('Connection refused')

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            'assets': [
                {
                    'name': 'Git-2.43.0-64-bit.exe',
                    'browser_download_url': 'https://github.com/.../Git-2.43.0-64-bit.exe',
                },
            ],
        }).encode()
        mock_response.__enter__ = lambda _: mock_response
        mock_response.__exit__ = lambda *_: None

        mock_urlopen.side_effect = [network_error, mock_response]

        result = install_claude.get_git_installer_with_retry(max_retries=2)

        assert result is not None
        mock_sleep.assert_called()

    @patch('install_claude.urlopen')
    def test_non_403_http_error_no_retry(self, mock_urlopen):
        """Test that non-403 HTTP errors don't trigger retry."""
        http_error = _create_mock_http_error(404, 'Not Found')

        mock_urlopen.side_effect = http_error

        result = install_claude.get_git_installer_with_retry(max_retries=3)

        assert result is None
        # Should only be called once (no retries for 404)
        assert mock_urlopen.call_count == 1

    @patch('install_claude.get_git_installer_url_from_github')
    @patch('install_claude.urlopen')
    def test_ssl_error_fallback(self, mock_urlopen, mock_fallback):
        """Test that SSL errors fall back to non-retry method."""
        ssl_error = urllib.error.URLError('SSL: CERTIFICATE_VERIFY_FAILED')
        mock_urlopen.side_effect = ssl_error
        mock_fallback.return_value = 'https://github.com/.../Git-2.43.0-64-bit.exe'

        result = install_claude.get_git_installer_with_retry(max_retries=2)

        assert result is not None
        mock_fallback.assert_called_once()


class TestNativeInstallerHttpRetry:
    """Tests for HTTP retry logic in _install_claude_native_windows_installer()."""

    @staticmethod
    def _make_http_error(code, reason='Error'):
        from email.message import Message
        return urllib.error.HTTPError(
            'https://claude.ai/install.ps1', code, reason, Message(), None,
        )

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only test')
    @patch('install_claude.time.sleep')
    @patch('install_claude.urlopen')
    def test_retries_on_http_403(self, mock_urlopen, mock_sleep):
        """Retries on HTTP 403 (Cloudflare challenge) and succeeds on third attempt."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'echo "installer"'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.side_effect = [
            self._make_http_error(403, 'Forbidden'),
            self._make_http_error(403, 'Forbidden'),
            mock_response,
        ]
        with patch('install_claude.run_command') as mock_run, \
             patch('install_claude.ensure_local_bin_in_path_windows'), \
             patch('install_claude.verify_claude_installation', return_value=(False, None, 'none')), \
             patch('install_claude.get_latest_claude_version', return_value=None):
            mock_run.return_value = MagicMock(returncode=1, stdout='', stderr='')
            install_claude._install_claude_native_windows_installer()
        assert mock_urlopen.call_count == 3
        assert mock_sleep.call_args_list == [((1,),), ((2,),)]

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only test')
    @patch('install_claude.time.sleep')
    @patch('install_claude.urlopen')
    def test_retries_on_http_429(self, mock_urlopen, mock_sleep):
        """Retries on HTTP 429 and succeeds on second attempt."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'echo "installer"'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.side_effect = [
            self._make_http_error(429, 'Too Many Requests'),
            mock_response,
        ]
        with patch('install_claude.run_command') as mock_run, \
             patch('install_claude.ensure_local_bin_in_path_windows'), \
             patch('install_claude.verify_claude_installation', return_value=(False, None, 'none')), \
             patch('install_claude.get_latest_claude_version', return_value=None):
            mock_run.return_value = MagicMock(returncode=1, stdout='', stderr='')
            install_claude._install_claude_native_windows_installer()
        assert mock_urlopen.call_count == 2
        mock_sleep.assert_called_once_with(1)

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only test')
    @patch('install_claude.time.sleep')
    @patch('install_claude.urlopen')
    def test_retries_on_http_5xx(self, mock_urlopen, mock_sleep):
        """Retries on HTTP 503 and succeeds on second attempt."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'echo "installer"'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.side_effect = [
            self._make_http_error(503, 'Service Unavailable'),
            mock_response,
        ]
        with patch('install_claude.run_command') as mock_run, \
             patch('install_claude.ensure_local_bin_in_path_windows'), \
             patch('install_claude.verify_claude_installation', return_value=(False, None, 'none')), \
             patch('install_claude.get_latest_claude_version', return_value=None):
            mock_run.return_value = MagicMock(returncode=1, stdout='', stderr='')
            install_claude._install_claude_native_windows_installer()
        assert mock_urlopen.call_count == 2
        mock_sleep.assert_called_once_with(1)

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only test')
    @patch('install_claude.time.sleep')
    @patch('install_claude.urlopen')
    def test_no_retry_on_http_404(self, mock_urlopen, mock_sleep):
        """Non-transient HTTP 404 returns False immediately without retry."""
        mock_urlopen.side_effect = self._make_http_error(404, 'Not Found')
        result = install_claude._install_claude_native_windows_installer()
        assert result is False
        assert mock_urlopen.call_count == 1
        mock_sleep.assert_not_called()

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only test')
    @patch('install_claude.time.sleep')
    @patch('install_claude.urlopen')
    def test_returns_false_after_max_retries(self, mock_urlopen, mock_sleep):
        """Returns False after exhausting all retry attempts."""
        mock_urlopen.side_effect = self._make_http_error(403, 'Forbidden')
        result = install_claude._install_claude_native_windows_installer()
        assert result is False
        assert mock_urlopen.call_count == 3
        assert mock_sleep.call_count == 2

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only test')
    @patch('install_claude.time.sleep')
    @patch('install_claude.urlopen')
    def test_ssl_error_still_triggers_fallback(self, mock_urlopen, mock_sleep):
        """SSL URLError triggers the SSL fallback path, not a retry or hard failure."""
        mock_urlopen.side_effect = urllib.error.URLError('SSL: CERTIFICATE_VERIFY_FAILED')
        with patch('install_claude.ssl') as mock_ssl:
            mock_ctx = MagicMock()
            mock_ssl.create_default_context.return_value = mock_ctx
            # SSL fallback also fails to keep test simple
            second_urlopen_error = Exception('SSL fallback failed')
            mock_urlopen.side_effect = [
                urllib.error.URLError('SSL: CERTIFICATE_VERIFY_FAILED'),
                second_urlopen_error,
            ]
            result = install_claude._install_claude_native_windows_installer()
        assert result is False
        # urlopen called twice: once in retry loop (SSL error), once in SSL fallback
        assert mock_urlopen.call_count == 2
        # SSL errors do not trigger HTTP retry backoff
        mock_sleep.assert_not_called()

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only test')
    @patch('install_claude.time.sleep')
    @patch('install_claude.urlopen')
    def test_success_on_first_attempt_no_retry(self, mock_urlopen, mock_sleep):
        """Successful first attempt does not trigger any retry or sleep."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'echo "installer"'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        with patch('install_claude.run_command') as mock_run, \
             patch('install_claude.ensure_local_bin_in_path_windows'), \
             patch('install_claude.verify_claude_installation', return_value=(False, None, 'none')), \
             patch('install_claude.get_latest_claude_version', return_value=None):
            mock_run.return_value = MagicMock(returncode=1, stdout='', stderr='')
            install_claude._install_claude_native_windows_installer()
        assert mock_urlopen.call_count == 1
        mock_sleep.assert_not_called()


class TestVerifyClaudeInstallation:
    """Test verify_claude_installation() function for robust installation verification."""

    @patch('sys.platform', 'win32')
    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.stat')
    def test_verify_claude_installation_native_exists(self, mock_stat, mock_exists):
        """Test verification when native installation exists with valid file."""
        # Mock native path exists and has valid size
        mock_stat.return_value.st_size = 5000000  # 5MB file
        mock_exists.return_value = True

        is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is True
        assert source == 'native'
        assert '.local' in path.lower()
        assert 'bin' in path.lower()

    @patch('sys.platform', 'win32')
    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.stat')
    def test_verify_claude_installation_native_file_too_small(self, mock_stat, mock_exists):
        """Test verification rejects native file that's too small (corrupted/empty)."""
        # Mock native path exists but file is too small (< 1KB)
        mock_stat.return_value.st_size = 500  # 500 bytes - too small

        def exists_side_effect():
            return '.local' in str(mock_exists.call_args)

        mock_exists.side_effect = exists_side_effect

        with patch('install_claude.find_command', return_value=None):
            is_installed, path, source = install_claude.verify_claude_installation()

            # Should reject the small file and continue searching
            assert is_installed is False or source != 'native'

    @patch('sys.platform', 'win32')
    @patch('pathlib.Path.exists')
    @patch('os.path.expandvars')
    def test_verify_claude_installation_npm_cmd(self, mock_expandvars, mock_exists):
        """Test verification when only npm .cmd installation exists."""
        # Mock: native doesn't exist, npm .cmd exists
        # Order of exists() calls: native, npm_cmd, npm_executable, winget
        mock_exists.side_effect = [
            False,  # native_path.exists() -> False
            True,  # npm_cmd_path.exists() -> True
        ]
        mock_expandvars.side_effect = lambda x: x.replace('%APPDATA%', 'C:\\Users\\Test\\AppData\\Roaming')

        is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is True
        assert source == 'npm'
        assert 'npm' in path.lower()

    @patch('sys.platform', 'win32')
    @patch('pathlib.Path.exists')
    @patch('os.path.expandvars')
    def test_verify_claude_installation_npm_executable(self, mock_expandvars, mock_exists):
        """Test verification when npm executable (without .cmd) exists."""
        # Mock: native doesn't exist, npm .cmd doesn't exist, npm executable exists
        # Order of exists() calls: native, npm_cmd, npm_executable, winget
        mock_exists.side_effect = [
            False,  # native_path.exists() -> False
            False,  # npm_cmd_path.exists() -> False
            True,  # npm_path.exists() -> True
        ]
        mock_expandvars.side_effect = lambda x: x.replace('%APPDATA%', 'C:\\Users\\Test\\AppData\\Roaming')

        is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is True
        assert source == 'npm'
        assert 'npm' in path.lower()

    @patch('sys.platform', 'win32')
    @patch('install_claude._classify_localappdata_claude', return_value='winget')
    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.stat')
    @patch('os.path.expandvars')
    def test_verify_claude_installation_winget(self, mock_expandvars, mock_stat, mock_exists, mock_classify):
        """Test verification when winget installation exists."""
        # Mock: native and npm don't exist, programs path exists with valid size
        # Order of exists() calls: native, npm_cmd, npm_executable, programs_path
        assert mock_classify.return_value == 'winget'
        mock_exists.side_effect = [
            False,  # native_path.exists() -> False
            False,  # npm_cmd_path.exists() -> False
            False,  # npm_path.exists() -> False
            True,  # programs_path.exists() -> True
        ]
        mock_stat.return_value.st_size = 5000000  # 5MB file
        mock_expandvars.side_effect = lambda x: x.replace('%LOCALAPPDATA%', 'C:\\Users\\Test\\AppData\\Local')

        is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is True
        assert source == 'winget'
        assert 'programs\\claude' in path.lower() or 'programs/claude' in path.lower()

    @patch('sys.platform', 'win32')
    @patch('pathlib.Path.exists', return_value=False)
    @patch('install_claude.find_command')
    def test_verify_claude_installation_path_fallback_npm_detection(self, mock_find, mock_exists):
        """Test PATH fallback with npm source detection from path string."""
        # Mock: no direct paths exist, but find_command finds npm installation
        assert mock_exists.return_value is False
        mock_find.return_value = 'C:\\Users\\Test\\AppData\\Roaming\\npm\\claude.cmd'

        is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is True
        assert source == 'npm'
        assert 'npm' in path.lower()

    @patch('sys.platform', 'win32')
    @patch('pathlib.Path.exists', return_value=False)
    @patch('install_claude.find_command')
    def test_verify_claude_installation_path_fallback_native_detection(self, mock_find, mock_exists):
        """Test PATH fallback with native source detection from path string."""
        # Mock: no direct paths exist, but find_command finds native location
        assert mock_exists.return_value is False
        mock_find.return_value = 'C:\\Users\\Test\\.local\\bin\\claude.exe'

        is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is True
        assert source == 'native'
        assert '.local\\bin' in path.lower()

    @patch('sys.platform', 'win32')
    @patch('install_claude._classify_localappdata_claude', return_value='winget')
    @patch('pathlib.Path.exists', return_value=False)
    @patch('install_claude.find_command')
    def test_verify_claude_installation_path_fallback_winget_detection(self, mock_find, mock_exists, mock_classify):
        """Test PATH fallback with winget source detection from path string."""
        # Mock: no direct paths exist, but find_command finds winget installation
        assert mock_exists.return_value is False
        assert mock_classify.return_value == 'winget'
        mock_find.return_value = 'C:\\Users\\Test\\AppData\\Local\\Programs\\claude\\claude.exe'

        is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is True
        assert source == 'winget'
        assert 'programs\\claude' in path.lower()

    @patch('sys.platform', 'win32')
    @patch('pathlib.Path.exists', return_value=False)
    @patch('install_claude.find_command')
    def test_verify_claude_installation_path_fallback_unknown(self, mock_find, mock_exists):
        """Test PATH fallback with unknown source (doesn't match patterns)."""
        # Mock: find_command finds claude but in unexpected location
        assert mock_exists.return_value is False
        mock_find.return_value = 'C:\\CustomPath\\claude.exe'

        is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is True
        assert source == 'unknown'
        assert path == 'C:\\CustomPath\\claude.exe'

    @patch('sys.platform', 'win32')
    @patch('pathlib.Path.exists', return_value=False)
    @patch('install_claude.find_command', return_value=None)
    def test_verify_claude_installation_not_found(self, mock_find, mock_exists):
        """Test verification when Claude is not installed anywhere."""
        # Mock: no paths exist, find_command returns None
        assert mock_exists.return_value is False
        assert mock_find.return_value is None

        is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is False
        assert path is None
        assert source == 'none'

    @patch('sys.platform', 'linux')
    @patch('install_claude.find_command')
    def test_verify_claude_installation_linux_npm(self, mock_find):
        """Test verification on Linux with npm installation."""
        mock_find.return_value = '/home/user/.npm-global/bin/claude'

        is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is True
        assert source == 'npm'
        assert '.npm-global' in path or 'npm' in path

    @patch('sys.platform', 'linux')
    @patch('install_claude.find_command')
    def test_verify_claude_installation_linux_unknown(self, mock_find):
        """Verify unrecognized path is classified as unknown on Linux."""
        mock_find.return_value = '/opt/custom/bin/claude'

        is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is True
        assert source == 'unknown'
        assert path == '/opt/custom/bin/claude'

    @patch('sys.platform', 'linux')
    @patch('install_claude.find_command', return_value=None)
    def test_verify_claude_installation_linux_not_found(self, mock_find):
        """Test verification on Linux when not installed."""
        assert mock_find.return_value is None

        is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is False
        assert path is None
        assert source == 'none'

    @patch('sys.platform', 'darwin')
    @patch('install_claude.find_command')
    def test_verify_claude_installation_macos_unknown(self, mock_find):
        """Verify unrecognized path is classified as unknown on macOS."""
        mock_find.return_value = '/opt/homebrew/custom/claude'

        is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is True
        assert source == 'unknown'
        assert path == '/opt/homebrew/custom/claude'

    @patch('sys.platform', 'linux')
    @patch('install_claude.find_command')
    def test_verify_claude_installation_linux_native(self, mock_find):
        """Test verification on Linux with native installation at ~/.local/bin."""
        mock_find.return_value = '/home/user/.local/bin/claude'

        is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is True
        assert source == 'native'
        assert '.local/bin' in path

    @patch('sys.platform', 'darwin')
    @patch('install_claude.find_command')
    def test_verify_claude_installation_macos_native(self, mock_find):
        """Test verification on macOS with native installation at ~/.local/bin."""
        mock_find.return_value = '/Users/testuser/.local/bin/claude'

        is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is True
        assert source == 'native'
        assert '.local/bin' in path

    @patch('sys.platform', 'win32')
    @patch('pathlib.Path.exists', return_value=False)
    @patch('install_claude.find_command')
    def test_verify_claude_installation_false_positive_scenario(self, mock_find, mock_exists):
        """Test the exact false positive scenario from user report.

        Native installer claims installation at ~/.local/bin/claude.exe
        but file doesn't exist. npm installation exists elsewhere.
        Should return npm source, NOT native.
        """
        # This is the critical test case that validates the fix
        assert mock_exists.return_value is False  # Native file doesn't exist
        mock_find.return_value = 'C:\\Users\\Test\\AppData\\Roaming\\npm\\claude'  # npm exists

        is_installed, path, source = install_claude.verify_claude_installation()

        # CRITICAL ASSERTIONS - this is what fixes the bug
        assert is_installed is True
        assert source == 'npm', 'Should detect npm source, not native'
        assert path is not None
        assert '.local\\bin' not in path.lower(), 'Should NOT report native path'
        assert 'npm' in path.lower(), 'Should report actual npm location'

    @patch('sys.platform', 'linux')
    @patch('install_claude.find_command')
    def test_verify_claude_installation_linux_usr_local_bin_unknown(self, mock_find):
        """/usr/local/bin/claude is classified as 'unknown' on Linux (could be npm or native)."""
        mock_find.return_value = '/usr/local/bin/claude'

        with patch('pathlib.Path.exists', return_value=False):
            is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is True
        assert source == 'unknown'
        assert path == '/usr/local/bin/claude'

    @patch('sys.platform', 'darwin')
    @patch('install_claude.find_command')
    def test_verify_claude_installation_macos_usr_local_bin_unknown(self, mock_find):
        """/usr/local/bin/claude is classified as 'unknown' on macOS (could be npm or native)."""
        mock_find.return_value = '/usr/local/bin/claude'

        with patch('pathlib.Path.exists', return_value=False):
            is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is True
        assert source == 'unknown'
        assert path == '/usr/local/bin/claude'

    @patch('sys.platform', 'linux')
    @patch('install_claude.find_command')
    def test_verify_claude_installation_linux_claude_bin_native(self, mock_find):
        """Verify ~/.claude/bin/claude is classified as native on Linux."""
        mock_find.return_value = '/home/user/.claude/bin/claude'

        is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is True
        assert source == 'native'
        assert path == '/home/user/.claude/bin/claude'

    @patch('sys.platform', 'darwin')
    @patch('install_claude.find_command')
    def test_verify_claude_installation_macos_claude_bin_native(self, mock_find):
        """Verify ~/.claude/bin/claude is classified as native on macOS."""
        mock_find.return_value = '/Users/testuser/.claude/bin/claude'

        is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is True
        assert source == 'native'
        assert path == '/Users/testuser/.claude/bin/claude'

    @patch('sys.platform', 'linux')
    @patch('install_claude.find_command')
    def test_verify_claude_installation_linux_usr_bin_unknown(self, mock_find):
        """Verify /usr/bin/claude is classified as unknown (system package territory)."""
        mock_find.return_value = '/usr/bin/claude'

        is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is True
        assert source == 'unknown'
        assert path == '/usr/bin/claude'

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only test')
    @patch('sys.platform', 'win32')
    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.stat')
    @patch('os.path.expandvars')
    def test_verify_claude_installation_winget_links_detected(self, mock_expandvars, mock_stat, mock_exists):
        """Test winget portable installation detected via WinGet Links path."""
        mock_expandvars.side_effect = lambda x: x.replace(
            '%LOCALAPPDATA%', r'C:\Users\Test\AppData\Local',
        ).replace('%APPDATA%', r'C:\Users\Test\AppData\Roaming')
        # Order of exists() calls: native_path, npm_cmd, npm_exe, programs_path, winget_links
        mock_exists.side_effect = [
            False,  # native_path.exists()
            False,  # npm_cmd.exists()
            False,  # npm_exe.exists()
            False,  # programs_path.exists()
            True,   # winget_links.exists()
        ]
        mock_stat.return_value.st_size = 100  # Small file (for native_path check)

        is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is True
        assert source == 'winget'
        assert 'winget' in path.lower()

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only test')
    @patch('sys.platform', 'win32')
    @patch('pathlib.Path.exists', return_value=False)
    @patch('install_claude.find_command')
    def test_verify_claude_installation_path_fallback_winget_links(self, mock_find, mock_exists):
        """Test PATH fallback detects winget Links path."""
        assert mock_exists.return_value is False
        mock_find.return_value = r'C:\Users\Test\AppData\Local\Microsoft\WinGet\Links\claude.exe'

        is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is True
        assert source == 'winget'

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only test')
    @patch('sys.platform', 'win32')
    @patch('pathlib.Path.exists', return_value=False)
    @patch('install_claude.find_command')
    def test_verify_claude_installation_path_fallback_winget_packages(self, mock_find, mock_exists):
        """Test PATH fallback detects winget Packages path."""
        assert mock_exists.return_value is False
        mock_find.return_value = r'C:\Users\Test\AppData\Local\Microsoft\WinGet\Packages\Anthropic.ClaudeCode_1.2.3\claude.exe'

        is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is True
        assert source == 'winget'


class TestWindowsFileLockHandling:
    """Tests for Windows file locking workaround (WinError 5 Access Denied).

    These tests verify the rename-before-replace strategy used when
    claude.exe is running during installation.
    """

    def test_cleanup_old_file_before_rename_file_does_not_exist(self, tmp_path: Path) -> None:
        """Test cleanup when .old file does not exist returns True."""
        old_file = tmp_path / 'claude.exe.old'
        assert not old_file.exists()

        with patch('sys.platform', 'win32'):
            result = install_claude._cleanup_old_file_before_rename(old_file)

        assert result is True

    def test_cleanup_old_file_before_rename_file_deleted(self, tmp_path: Path) -> None:
        """Test cleanup successfully deletes existing .old file."""
        old_file = tmp_path / 'claude.exe.old'
        old_file.write_text('old content')
        assert old_file.exists()

        with patch('sys.platform', 'win32'):
            result = install_claude._cleanup_old_file_before_rename(old_file)

        assert result is True
        assert not old_file.exists()

    def test_cleanup_old_file_before_rename_file_locked(self, tmp_path: Path) -> None:
        """Test cleanup returns False when .old file is locked."""
        old_file = tmp_path / 'claude.exe.old'
        old_file.write_text('locked content')

        with patch('sys.platform', 'win32'), patch.object(Path, 'unlink', side_effect=PermissionError('Access is denied')):
            result = install_claude._cleanup_old_file_before_rename(old_file)

        assert result is False

    def test_cleanup_old_file_before_rename_non_windows(self, tmp_path: Path) -> None:
        """Test cleanup returns True immediately on non-Windows platforms."""
        old_file = tmp_path / 'claude.old'
        old_file.write_text('some content')

        with patch('sys.platform', 'linux'):
            result = install_claude._cleanup_old_file_before_rename(old_file)

        # Returns True without attempting deletion on non-Windows
        assert result is True
        # File should still exist (no deletion on non-Windows)
        assert old_file.exists()

    def test_get_unique_old_path_first_available(self, tmp_path: Path) -> None:
        """Test unique path returns .old.1 when no numbered files exist."""
        target = tmp_path / 'claude.exe'

        result = install_claude._get_unique_old_path(target)

        assert result.name == 'claude.exe.old.1'

    def test_get_unique_old_path_skips_existing_unlocked(self, tmp_path: Path) -> None:
        """Test unique path deletes existing unlocked file and returns it."""
        target = tmp_path / 'claude.exe'
        old_1 = tmp_path / 'claude.exe.old.1'
        old_1.write_text('orphaned file')

        result = install_claude._get_unique_old_path(target)

        # Should return .old.1 after deleting the orphaned file
        assert result.name == 'claude.exe.old.1'
        assert not old_1.exists()

    def test_get_unique_old_path_skips_locked_files(self, tmp_path: Path) -> None:
        """Test unique path skips locked files and finds next available."""
        target = tmp_path / 'claude.exe'
        old_1 = tmp_path / 'claude.exe.old.1'
        old_1.write_text('locked')

        # Mock unlink to fail for .old.1 but succeed for .old.2
        original_unlink = Path.unlink
        call_count = [0]

        def mock_unlink(self: Path, missing_ok: bool = False) -> None:
            call_count[0] += 1
            if '.old.1' in str(self):
                raise PermissionError('Access is denied')
            original_unlink(self, missing_ok=missing_ok)

        with patch.object(Path, 'unlink', mock_unlink):
            result = install_claude._get_unique_old_path(target)

        # Should skip .old.1 and return .old.2
        assert result.name == 'claude.exe.old.2'

    def test_handle_windows_file_lock_success(self, tmp_path: Path) -> None:
        """Test successful rename strategy when claude.exe is running."""
        target = tmp_path / 'claude.exe'
        temp = tmp_path / 'claude.tmp'
        target.write_bytes(b'old version')
        temp.write_bytes(b'new version')

        result = install_claude._handle_windows_file_lock(temp, target, '2.0.76', 1000)

        assert result is True
        # target should have new content
        assert target.read_bytes() == b'new version'
        # .old file should exist with old content
        old_path = tmp_path / 'claude.exe.old'
        assert old_path.exists()
        assert old_path.read_bytes() == b'old version'
        # temp file should not exist
        assert not temp.exists()

    def test_handle_windows_file_lock_with_existing_old_file(self, tmp_path: Path) -> None:
        """Test rename strategy when .old file already exists (not locked)."""
        target = tmp_path / 'claude.exe'
        temp = tmp_path / 'claude.tmp'
        old_existing = tmp_path / 'claude.exe.old'

        target.write_bytes(b'old version')
        temp.write_bytes(b'new version')
        old_existing.write_bytes(b'very old version')

        result = install_claude._handle_windows_file_lock(temp, target, '2.0.76', 1000)

        assert result is True
        # .old should now contain the old version (overwritten)
        assert old_existing.read_bytes() == b'old version'
        # target should have new content
        assert target.read_bytes() == b'new version'

    def test_handle_windows_file_lock_old_file_locked_uses_unique(self, tmp_path: Path) -> None:
        """Test rename strategy uses unique suffix when .old is locked."""
        target = tmp_path / 'claude.exe'
        temp = tmp_path / 'claude.tmp'
        old_existing = tmp_path / 'claude.exe.old'

        target.write_bytes(b'old version')
        temp.write_bytes(b'new version')
        old_existing.write_bytes(b'locked old version')

        # Make _cleanup_old_file_before_rename return False (simulating locked .old)
        with patch.object(install_claude, '_cleanup_old_file_before_rename', return_value=False):
            result = install_claude._handle_windows_file_lock(temp, target, '2.0.76', 1000)

        assert result is True
        # Original .old should still exist (was locked)
        assert old_existing.exists()
        # .old.1 should have the old version
        old_1 = tmp_path / 'claude.exe.old.1'
        assert old_1.exists()
        assert old_1.read_bytes() == b'old version'
        # target should have new content
        assert target.read_bytes() == b'new version'

    def test_handle_windows_file_lock_rename_fails(self, tmp_path: Path) -> None:
        """Test rename strategy returns False when rename fails."""
        target = tmp_path / 'claude.exe'
        temp = tmp_path / 'claude.tmp'
        target.write_bytes(b'old version')
        temp.write_bytes(b'new version')

        # Mock rename to fail
        with patch.object(Path, 'rename', side_effect=PermissionError('Access is denied')):
            result = install_claude._handle_windows_file_lock(temp, target, '2.0.76', 1000)

        assert result is False
        # temp file should be cleaned up
        assert not temp.exists()

    def test_cleanup_old_claude_files_removes_old_file(self, tmp_path: Path) -> None:
        """Test cleanup removes standard .old file."""
        local_bin = tmp_path / '.local' / 'bin'
        local_bin.mkdir(parents=True)
        old_file = local_bin / 'claude.exe.old'
        old_file.write_text('old content')

        with patch('sys.platform', 'win32'), patch('pathlib.Path.home', return_value=tmp_path):
            install_claude._cleanup_old_claude_files()

        assert not old_file.exists()

    def test_cleanup_old_claude_files_removes_numbered_old_files(self, tmp_path: Path) -> None:
        """Test cleanup removes numbered .old files."""
        local_bin = tmp_path / '.local' / 'bin'
        local_bin.mkdir(parents=True)
        old_1 = local_bin / 'claude.exe.old.1'
        old_2 = local_bin / 'claude.exe.old.2'
        old_1.write_text('old 1')
        old_2.write_text('old 2')

        with patch('sys.platform', 'win32'), patch('pathlib.Path.home', return_value=tmp_path):
            install_claude._cleanup_old_claude_files()

        assert not old_1.exists()
        assert not old_2.exists()

    def test_cleanup_old_claude_files_ignores_locked_files(self, tmp_path: Path) -> None:
        """Test cleanup ignores locked files without error."""
        local_bin = tmp_path / '.local' / 'bin'
        local_bin.mkdir(parents=True)
        old_file = local_bin / 'claude.exe.old'
        old_file.write_text('locked')

        # Mock unlink to raise PermissionError
        original_unlink = Path.unlink

        def mock_unlink(self: Path, missing_ok: bool = False) -> None:
            if 'claude.exe.old' in str(self):
                raise PermissionError('Access is denied')
            original_unlink(self, missing_ok=missing_ok)

        with (
            patch('sys.platform', 'win32'),
            patch('pathlib.Path.home', return_value=tmp_path),
            patch.object(Path, 'unlink', mock_unlink),
        ):
            # Should not raise
            install_claude._cleanup_old_claude_files()

        # File should still exist
        assert old_file.exists()

    def test_cleanup_old_claude_files_non_windows_noop(self, tmp_path: Path) -> None:
        """Test cleanup is a no-op on non-Windows platforms."""
        local_bin = tmp_path / '.local' / 'bin'
        local_bin.mkdir(parents=True)
        old_file = local_bin / 'claude.exe.old'
        old_file.write_text('content')

        with patch('sys.platform', 'linux'), patch('pathlib.Path.home', return_value=tmp_path):
            install_claude._cleanup_old_claude_files()

        # File should still exist (no cleanup on non-Windows)
        assert old_file.exists()

    def test_cleanup_old_claude_files_directory_not_exists(self, tmp_path: Path) -> None:
        """Test cleanup handles missing .local/bin directory gracefully."""
        # No .local/bin directory created

        with patch('sys.platform', 'win32'), patch('pathlib.Path.home', return_value=tmp_path):
            # Should not raise
            install_claude._cleanup_old_claude_files()

    @patch('sys.platform', 'win32')
    @patch('install_claude._handle_windows_file_lock')
    def test_download_gcs_calls_file_lock_handler_on_permission_error(
        self, mock_handler: MagicMock, tmp_path: Path,
    ) -> None:
        """Test that _download_claude_direct_from_gcs calls the handler on Windows PermissionError."""
        target = tmp_path / 'claude.exe'
        mock_handler.return_value = True

        # Mock urlretrieve to create a temp file
        def mock_urlretrieve(_url: str, filename: str) -> None:
            Path(filename).write_bytes(b'x' * 2000)  # Above min_size

        # Mock replace to raise PermissionError with "Access is denied"
        original_replace = Path.replace

        def mock_replace(self: Path, target: Path) -> Path:
            if str(self).endswith('.tmp'):
                raise PermissionError('[WinError 5] Access is denied')
            return original_replace(self, target)

        with (
            patch('install_claude.urlretrieve', mock_urlretrieve),
            patch.object(Path, 'replace', mock_replace),
        ):
            result = install_claude._download_claude_direct_from_gcs('2.0.76', target)

        assert result is True
        mock_handler.assert_called_once()
        # Verify arguments passed to handler
        call_args = mock_handler.call_args[0]
        assert str(call_args[0]).endswith('.tmp')  # temp_path
        assert call_args[1] == target  # target_path
        assert call_args[2] == '2.0.76'  # version
        assert call_args[3] > 1000  # file_size

    @patch('sys.platform', 'linux')
    def test_download_gcs_reraises_permission_error_on_non_windows(self, tmp_path: Path) -> None:
        """Test that PermissionError is re-raised on non-Windows platforms."""
        target = tmp_path / 'claude'

        # Mock urlretrieve to create a temp file
        def mock_urlretrieve(_url: str, filename: str) -> None:
            Path(filename).write_bytes(b'x' * 2000)

        # Mock replace to raise PermissionError
        original_replace = Path.replace

        def mock_replace(self: Path, target_arg: Path) -> Path:
            if str(self).endswith('.tmp'):
                raise PermissionError('Permission denied')
            return original_replace(self, target_arg)

        with (
            patch('install_claude.urlretrieve', mock_urlretrieve),
            patch.object(Path, 'replace', mock_replace),
            pytest.raises(PermissionError, match='Permission denied'),
        ):
            install_claude._download_claude_direct_from_gcs('2.0.76', target)

    def test_install_native_windows_calls_cleanup_at_start(self) -> None:
        """Test that install_claude_native_windows calls cleanup at start."""
        with (
            patch('platform.system', return_value='Windows'),
            patch('install_claude._cleanup_old_claude_files') as mock_cleanup,
            patch(
                'install_claude._install_claude_native_windows_installer',
            ) as mock_installer,
        ):
            mock_installer.return_value = True

            install_claude.install_claude_native_windows(version='latest')

            # Verify cleanup was called
            mock_cleanup.assert_called_once()
            # Verify installer was called after cleanup
            mock_installer.assert_called_once_with(version='latest')


class TestRemoveNpmClaude:
    """Test remove_npm_claude() function for automatic npm removal."""

    @patch('install_claude.find_command', return_value=None)
    def test_remove_npm_claude_no_npm_installed(self, mock_find: MagicMock) -> None:
        """Test remove_npm_claude returns True when npm is not installed."""
        result = install_claude.remove_npm_claude()

        assert result is True
        mock_find.assert_called_once_with('npm')

    @patch('install_claude.run_command')
    @patch('install_claude.find_command')
    def test_remove_npm_claude_npm_package_not_installed(
        self, mock_find: MagicMock, mock_run: MagicMock,
    ) -> None:
        """Test remove_npm_claude returns True when npm exists but package not installed."""
        mock_find.return_value = '/usr/local/bin/npm'
        # npm list -g returns non-zero when package not found
        mock_run.return_value = MagicMock(returncode=1)

        result = install_claude.remove_npm_claude()

        assert result is True
        mock_find.assert_called_once_with('npm')
        # Verify npm list was called to check package
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ['/usr/local/bin/npm', 'list', '-g', '@anthropic-ai/claude-code']

    @patch('install_claude.run_command')
    @patch('install_claude.find_command')
    def test_remove_npm_claude_uninstall_success(
        self, mock_find: MagicMock, mock_run: MagicMock,
    ) -> None:
        """Test remove_npm_claude returns True when npm uninstall succeeds."""
        mock_find.return_value = '/usr/local/bin/npm'
        # First call: npm list -g returns 0 (package found)
        # Second call: npm uninstall -g returns 0 (success)
        mock_run.side_effect = [
            MagicMock(returncode=0),  # npm list -g
            MagicMock(returncode=0),  # npm uninstall -g
        ]

        result = install_claude.remove_npm_claude()

        assert result is True
        assert mock_run.call_count == 2
        # Verify uninstall command was called correctly
        uninstall_call = mock_run.call_args_list[1]
        assert uninstall_call[0][0] == [
            '/usr/local/bin/npm', 'uninstall', '-g', '@anthropic-ai/claude-code',
        ]

    @patch('install_claude._warn_npm_removal_failed')
    @patch('sys.platform', 'win32')
    @patch('install_claude.run_command')
    @patch('install_claude.find_command')
    def test_remove_npm_claude_uninstall_failure(
        self, mock_find: MagicMock, mock_run: MagicMock,
        mock_warn: MagicMock,
    ) -> None:
        """Test remove_npm_claude returns False when npm uninstall fails on Windows."""
        mock_find.return_value = '/usr/local/bin/npm'
        # First call: npm list -g returns 0 (package found)
        # Second call: npm uninstall -g returns non-zero (failure)
        mock_run.side_effect = [
            MagicMock(returncode=0),  # npm list -g
            MagicMock(returncode=1),  # npm uninstall -g fails
        ]

        result = install_claude.remove_npm_claude()

        assert result is False
        assert mock_run.call_count == 2
        mock_warn.assert_called_once()

    @patch('install_claude.run_command')
    @patch('install_claude.find_command')
    def test_remove_npm_claude_windows_npm_path(
        self, mock_find: MagicMock, mock_run: MagicMock,
    ) -> None:
        """Test remove_npm_claude works with Windows npm path."""
        mock_find.return_value = r'C:\Program Files\nodejs\npm.cmd'
        mock_run.side_effect = [
            MagicMock(returncode=0),  # npm list -g
            MagicMock(returncode=0),  # npm uninstall -g
        ]

        result = install_claude.remove_npm_claude()

        assert result is True
        # Verify Windows path was used correctly
        args = mock_run.call_args_list[0][0][0]
        assert args[0] == r'C:\Program Files\nodejs\npm.cmd'

    @patch('sys.platform', 'linux')
    @patch('install_claude._run_with_sudo_fallback')
    @patch('install_claude.run_command')
    @patch('install_claude.find_command')
    def test_remove_npm_claude_sudo_with_tty(
        self, mock_find: MagicMock, mock_run: MagicMock,
        mock_sudo: MagicMock,
    ) -> None:
        """Test sudo retry via _run_with_sudo_fallback when initial uninstall fails."""
        mock_find.return_value = '/usr/bin/npm'
        mock_run.side_effect = [
            MagicMock(returncode=0),  # npm list -g (package found)
            MagicMock(returncode=1),  # npm uninstall -g (permission denied)
        ]
        # _run_with_sudo_fallback returns success
        mock_sudo.return_value = subprocess.CompletedProcess([], 0, '', '')

        result = install_claude.remove_npm_claude()

        assert result is True
        mock_sudo.assert_called_once()
        sudo_args = mock_sudo.call_args[0][0]
        assert sudo_args[0] == '/usr/bin/npm'
        assert 'uninstall' in sudo_args

    @patch('sys.platform', 'linux')
    @patch('install_claude._run_with_sudo_fallback')
    @patch('install_claude.run_command')
    @patch('install_claude.find_command')
    def test_remove_npm_claude_no_tty_no_cached_creds(
        self, mock_find: MagicMock, mock_run: MagicMock,
        mock_sudo: MagicMock,
    ) -> None:
        """Test direct file removal fallback when sudo is unavailable."""
        mock_find.return_value = '/usr/bin/npm'
        mock_run.side_effect = [
            MagicMock(returncode=0),  # npm list -g (package found)
            MagicMock(returncode=1),  # npm uninstall -g (permission denied)
        ]
        # _run_with_sudo_fallback returns None (no sudo available)
        mock_sudo.return_value = None

        with patch('pathlib.Path.exists', return_value=False):
            result = install_claude.remove_npm_claude()

        assert result is False
        mock_sudo.assert_called_once()

    @patch('sys.platform', 'linux')
    @patch('install_claude._run_with_sudo_fallback')
    @patch('install_claude.run_command')
    @patch('install_claude.find_command')
    def test_remove_npm_claude_no_tty_cached_creds(
        self, mock_find: MagicMock, mock_run: MagicMock,
        mock_sudo: MagicMock,
    ) -> None:
        """Test sudo retry via _run_with_sudo_fallback with cached credentials."""
        mock_find.return_value = '/usr/bin/npm'
        mock_run.side_effect = [
            MagicMock(returncode=0),  # npm list -g (package found)
            MagicMock(returncode=1),  # npm uninstall -g (permission denied)
        ]
        # _run_with_sudo_fallback returns success
        mock_sudo.return_value = subprocess.CompletedProcess([], 0, '', '')

        result = install_claude.remove_npm_claude()

        assert result is True
        mock_sudo.assert_called_once()
        sudo_args = mock_sudo.call_args[0][0]
        assert sudo_args[0] == '/usr/bin/npm'

    @patch('sys.platform', 'linux')
    @patch('install_claude._run_with_sudo_fallback')
    @patch('install_claude.run_command')
    @patch('install_claude.find_command')
    def test_remove_npm_claude_sudo_file_not_found(
        self, mock_find: MagicMock, mock_run: MagicMock,
        mock_sudo: MagicMock,
    ) -> None:
        """Test graceful handling when sudo is unavailable (returns None)."""
        mock_find.return_value = '/usr/bin/npm'
        mock_run.side_effect = [
            MagicMock(returncode=0),  # npm list -g (package found)
            MagicMock(returncode=1),  # npm uninstall -g (permission denied)
        ]
        # _run_with_sudo_fallback returns None (no sudo)
        mock_sudo.return_value = None

        with patch('pathlib.Path.exists', return_value=False):
            result = install_claude.remove_npm_claude()

        assert result is False
        mock_sudo.assert_called_once()

    @patch('sys.platform', 'linux')
    @patch('subprocess.run')
    @patch('install_claude.run_command')
    @patch('install_claude.find_command')
    def test_remove_npm_claude_first_attempt_succeeds_no_sudo(
        self, mock_find: MagicMock, mock_run: MagicMock,
        mock_subprocess: MagicMock,
    ) -> None:
        """Test no sudo attempt when initial uninstall succeeds (regression test)."""
        mock_find.return_value = '/usr/bin/npm'
        mock_run.side_effect = [
            MagicMock(returncode=0),  # npm list -g (package found)
            MagicMock(returncode=0),  # npm uninstall -g (success)
        ]

        result = install_claude.remove_npm_claude()

        assert result is True
        # subprocess.run should NOT be called at all (no sudo needed)
        mock_subprocess.assert_not_called()

    @patch('install_claude._warn_npm_removal_failed')
    @patch('sys.platform', 'win32')
    @patch('subprocess.run')
    @patch('install_claude.run_command')
    @patch('install_claude.find_command')
    def test_remove_npm_claude_windows_no_sudo(
        self, mock_find: MagicMock, mock_run: MagicMock,
        mock_subprocess: MagicMock,
        mock_warn: MagicMock,
    ) -> None:
        """Test no sudo attempt on Windows even when uninstall fails."""
        mock_find.return_value = r'C:\Program Files\nodejs\npm.cmd'
        mock_run.side_effect = [
            MagicMock(returncode=0),  # npm list -g (package found)
            MagicMock(returncode=1),  # npm uninstall -g (fails)
        ]

        result = install_claude.remove_npm_claude()

        assert result is False
        # subprocess.run should NOT be called (Windows, no sudo)
        mock_subprocess.assert_not_called()
        mock_warn.assert_called_once()


class TestGetNpmGlobalPrefix:
    """Tests for _get_npm_global_prefix() helper."""

    @patch('subprocess.run')
    def test_returns_prefix_on_success(self, mock_run: MagicMock) -> None:
        """Successful prefix retrieval."""
        mock_run.return_value = MagicMock(returncode=0, stdout='/usr\n')
        result = install_claude._get_npm_global_prefix('/usr/bin/npm')
        assert result == '/usr'
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ['/usr/bin/npm', 'config', 'get', 'prefix']

    @patch('subprocess.run')
    def test_returns_none_on_failure(self, mock_run: MagicMock) -> None:
        """Returns None when npm config command fails."""
        mock_run.return_value = MagicMock(returncode=1, stdout='')
        result = install_claude._get_npm_global_prefix('/usr/bin/npm')
        assert result is None

    @patch('subprocess.run')
    def test_returns_none_on_empty_output(self, mock_run: MagicMock) -> None:
        """Returns None when npm returns empty prefix."""
        mock_run.return_value = MagicMock(returncode=0, stdout='  \n')
        result = install_claude._get_npm_global_prefix('/usr/bin/npm')
        assert result is None

    @patch('subprocess.run', side_effect=subprocess.TimeoutExpired(cmd=[], timeout=10))
    def test_returns_none_on_timeout(self, mock_run: MagicMock) -> None:
        """Returns None when npm config times out."""
        result = install_claude._get_npm_global_prefix('/usr/bin/npm')
        assert result is None
        mock_run.assert_called_once()

    @patch('subprocess.run', side_effect=FileNotFoundError)
    def test_returns_none_on_file_not_found(self, mock_run: MagicMock) -> None:
        """Returns None when npm executable not found."""
        result = install_claude._get_npm_global_prefix('/nonexistent/npm')
        assert result is None
        mock_run.assert_called_once()

    @patch('subprocess.run')
    def test_strips_whitespace(self, mock_run: MagicMock) -> None:
        """Output whitespace is stripped."""
        mock_run.return_value = MagicMock(returncode=0, stdout='  /usr/local  \n')
        result = install_claude._get_npm_global_prefix('/usr/bin/npm')
        assert result == '/usr/local'


class TestRemoveNpmClaudeRmrfFallback:
    """Tests for rm-rf fallback in remove_npm_claude()."""

    @patch('sys.platform', 'linux')
    @patch('platform.system', return_value='Linux')
    @patch('install_claude._run_with_sudo_fallback')
    @patch('install_claude.run_command')
    @patch('install_claude.find_command')
    def test_rmrf_fallback_success(
        self, mock_find: MagicMock, mock_run: MagicMock, mock_sudo: MagicMock, mock_system: MagicMock, tmp_path: Path,
    ) -> None:
        """rm-rf fallback succeeds after npm uninstall and sudo both fail."""
        assert mock_system.return_value == 'Linux'
        mock_find.return_value = '/usr/bin/npm'
        mock_run.side_effect = [
            MagicMock(returncode=0),  # npm list -g (found)
            MagicMock(returncode=1),  # npm uninstall -g (ENOTEMPTY)
        ]

        # Create mock directory structure for glob expansion
        parent_dir = tmp_path / 'lib' / 'node_modules' / '@anthropic-ai'
        parent_dir.mkdir(parents=True)
        (parent_dir / '.claude-code-ABC123').mkdir()
        (parent_dir / 'claude-code').mkdir()
        bin_dir = tmp_path / 'bin'
        bin_dir.mkdir()
        (bin_dir / 'claude').touch()

        # First sudo: npm uninstall via sudo fails
        # Second sudo: rm -rf via sudo succeeds
        mock_sudo.side_effect = [
            subprocess.CompletedProcess([], 1, '', ''),
            subprocess.CompletedProcess([], 0, '', ''),
        ]

        with patch('install_claude._get_npm_global_prefix', return_value=str(tmp_path)):
            install_claude.remove_npm_claude()

        # rm -rf was attempted (second sudo call)
        assert mock_sudo.call_count == 2

    @patch('sys.platform', 'linux')
    @patch('platform.system', return_value='Linux')
    @patch('install_claude._run_with_sudo_fallback')
    @patch('install_claude.run_command')
    @patch('install_claude.find_command')
    def test_rmrf_no_prefix_falls_through(
        self, mock_find: MagicMock, mock_run: MagicMock, mock_sudo: MagicMock, mock_system: MagicMock,
    ) -> None:
        """rm-rf fallback is skipped when prefix is unavailable."""
        assert mock_system.return_value == 'Linux'
        mock_find.return_value = '/usr/bin/npm'
        mock_run.side_effect = [
            MagicMock(returncode=0),  # npm list -g (found)
            MagicMock(returncode=1),  # npm uninstall -g fails
        ]
        # sudo npm uninstall fails
        mock_sudo.return_value = subprocess.CompletedProcess([], 1, '', '')

        with patch('install_claude._get_npm_global_prefix', return_value=None), \
             patch('install_claude._warn_npm_removal_failed'):
            result = install_claude.remove_npm_claude()

        # Should fall through to static binary removal (which also fails)
        assert result is False

    @patch('sys.platform', 'linux')
    @patch('platform.system', return_value='Linux')
    @patch('install_claude._run_with_sudo_fallback')
    @patch('install_claude.run_command')
    @patch('install_claude.find_command')
    def test_rmrf_expands_glob_in_python(
        self, mock_find: MagicMock, mock_run: MagicMock, mock_sudo: MagicMock, mock_system: MagicMock, tmp_path: Path,
    ) -> None:
        """Glob .claude-code-* is expanded via Path.glob(), not passed raw to subprocess."""
        assert mock_system.return_value == 'Linux'
        mock_find.return_value = '/usr/bin/npm'
        mock_run.side_effect = [
            MagicMock(returncode=0),  # npm list -g (found)
            MagicMock(returncode=1),  # npm uninstall -g fails
        ]
        # First sudo: npm uninstall fails; second: rm -rf succeeds
        mock_sudo.side_effect = [
            subprocess.CompletedProcess([], 1, '', ''),
            subprocess.CompletedProcess([], 0, '', ''),
        ]

        # Create mock directory structure with stale temp dirs
        parent_dir = tmp_path / 'lib' / 'node_modules' / '@anthropic-ai'
        parent_dir.mkdir(parents=True)
        (parent_dir / '.claude-code-ABC123').mkdir()
        (parent_dir / '.claude-code-XYZ789').mkdir()
        (parent_dir / 'claude-code').mkdir()
        bin_dir = tmp_path / 'bin'
        bin_dir.mkdir()
        (bin_dir / 'claude').touch()

        with patch('install_claude._get_npm_global_prefix', return_value=str(tmp_path)):
            install_claude.remove_npm_claude()

        # Verify the rm -rf command received expanded paths, not raw glob
        if mock_sudo.call_count >= 2:
            rm_call_args = mock_sudo.call_args_list[1][0][0]  # Second sudo call args
            # Should NOT contain any glob pattern like '.claude-code-*'
            for arg in rm_call_args:
                assert '*' not in arg, f'Raw glob pattern found in subprocess args: {arg}'


class TestDevTtySudoAvailable:
    """Tests for _dev_tty_sudo_available() helper."""

    @patch('sys.platform', 'win32')
    def test_returns_false_on_windows(self) -> None:
        """Returns False on Windows (no /dev/tty)."""
        assert install_claude._dev_tty_sudo_available() is False

    @patch('sys.platform', 'linux')
    @patch('builtins.open', side_effect=OSError('No /dev/tty'))
    def test_returns_false_when_no_tty(self, mock_open: MagicMock) -> None:
        """Returns False when /dev/tty is not available."""
        del mock_open
        assert install_claude._dev_tty_sudo_available() is False

    @patch('sys.platform', 'linux')
    def test_returns_true_when_tty_available(self) -> None:
        """Returns True when /dev/tty can be opened."""
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        with patch('builtins.open', return_value=mock_file):
            assert install_claude._dev_tty_sudo_available() is True


class TestRunWithSudoFallback:
    """Tests for _run_with_sudo_fallback() DRY helper."""

    @patch('sys.platform', 'win32')
    def test_returns_none_on_windows(self) -> None:
        """Returns None immediately on Windows."""
        result = install_claude._run_with_sudo_fallback(['npm', 'uninstall', '-g', 'pkg'])
        assert result is None

    @patch('sys.platform', 'linux')
    @patch('sys.stdin')
    @patch('subprocess.run')
    def test_tier1_interactive_success(
        self, mock_run: MagicMock, mock_stdin: MagicMock,
    ) -> None:
        """Tier 1: uses sudo directly when stdin is a TTY."""
        mock_stdin.isatty.return_value = True
        expected = subprocess.CompletedProcess(['sudo', 'cmd'], 0, '', '')
        mock_run.return_value = expected

        result = install_claude._run_with_sudo_fallback(['cmd'])

        assert result is expected
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0] == ['sudo', 'cmd']

    @patch('sys.platform', 'linux')
    @patch('sys.stdin')
    @patch('subprocess.run')
    def test_tier1_timeout_returns_none(
        self, mock_run: MagicMock, mock_stdin: MagicMock,
    ) -> None:
        """Tier 1: returns None on timeout."""
        mock_stdin.isatty.return_value = True
        mock_run.side_effect = subprocess.TimeoutExpired(cmd='sudo', timeout=30)

        result = install_claude._run_with_sudo_fallback(['cmd'])

        assert result is None

    @patch('sys.platform', 'linux')
    @patch('install_claude._dev_tty_sudo_available', return_value=False)
    @patch('sys.stdin')
    @patch('subprocess.run')
    def test_tier2_cached_credentials(
        self, mock_run: MagicMock, mock_stdin: MagicMock,
        mock_tty: MagicMock,
    ) -> None:
        """Tier 2: uses cached credentials when available."""
        del mock_tty
        mock_stdin.isatty.return_value = False
        expected = subprocess.CompletedProcess(['sudo', 'cmd'], 0, '', '')
        mock_run.side_effect = [
            subprocess.CompletedProcess(['sudo', '-n', 'true'], 0, '', ''),  # cred check
            expected,  # actual command
        ]

        result = install_claude._run_with_sudo_fallback(['cmd'])

        assert result is expected
        assert mock_run.call_count == 2

    @patch('sys.platform', 'linux')
    @patch('install_claude._dev_tty_sudo_available', return_value=False)
    @patch('sys.stdin')
    @patch('subprocess.run')
    def test_all_tiers_fail_returns_none(
        self, mock_run: MagicMock, mock_stdin: MagicMock,
        mock_tty: MagicMock,
    ) -> None:
        """Returns None when all three tiers are exhausted."""
        del mock_tty
        mock_stdin.isatty.return_value = False
        # sudo -n true fails (no cached creds)
        mock_run.return_value = subprocess.CompletedProcess([], 1, '', '')

        result = install_claude._run_with_sudo_fallback(['cmd'])

        assert result is None

    @patch('sys.platform', 'linux')
    @patch('install_claude._dev_tty_sudo_available', return_value=True)
    @patch('sys.stdin')
    @patch('subprocess.run')
    def test_tier3_dev_tty_fallback(
        self, mock_run: MagicMock, mock_stdin: MagicMock,
        mock_tty: MagicMock,
    ) -> None:
        """Tier 3: uses /dev/tty when available and other tiers fail."""
        del mock_tty
        mock_stdin.isatty.return_value = False
        # Tier 2: cached creds fail
        cred_fail = subprocess.CompletedProcess([], 1, '', '')
        # Tier 3: sudo via /dev/tty succeeds
        tty_success = subprocess.CompletedProcess(['sudo', 'cmd'], 0, '', '')
        mock_run.side_effect = [cred_fail, tty_success]

        mock_tty_file = MagicMock()
        mock_tty_file.__enter__ = MagicMock(return_value=mock_tty_file)
        mock_tty_file.__exit__ = MagicMock(return_value=False)
        with patch('builtins.open', return_value=mock_tty_file):
            result = install_claude._run_with_sudo_fallback(['cmd'])

        assert result is tty_success


class TestWarnNpmRemovalFailed:
    """Tests for _warn_npm_removal_failed() warning display."""

    def test_produces_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Produces visible warning output."""
        with patch('install_claude._get_npm_global_prefix', return_value=None):
            install_claude._warn_npm_removal_failed()
        captured = capsys.readouterr()
        combined = captured.err + captured.out
        assert 'WARNING' in combined
        assert 'npm Claude Code installation was NOT removed' in combined

    @patch('install_claude._get_npm_global_prefix', return_value='/usr')
    @patch('sys.platform', 'linux')
    def test_unix_shows_rmrf_instructions(self, mock_prefix: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
        """Unix instructions show rm -rf, not npm uninstall."""
        assert mock_prefix.return_value == '/usr'
        install_claude._warn_npm_removal_failed(npm_path='/usr/bin/npm')
        captured = capsys.readouterr()
        combined = captured.err + captured.out
        assert 'sudo rm -rf' in combined
        assert 'sudo rm -f' in combined
        assert '/usr/lib/node_modules/@anthropic-ai' in combined
        assert '/usr/bin/claude' in combined

    @patch('install_claude._get_npm_global_prefix', return_value=None)
    @patch('sys.platform', 'linux')
    def test_unix_no_prefix_uses_defaults(self, mock_prefix: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
        """Fallback paths when prefix is unavailable."""
        assert mock_prefix.return_value is None
        install_claude._warn_npm_removal_failed(npm_path='/usr/bin/npm')
        captured = capsys.readouterr()
        combined = captured.err + captured.out
        assert '/usr/lib/node_modules/@anthropic-ai' in combined
        assert '/usr/bin/claude' in combined

    @patch('sys.platform', 'win32')
    def test_windows_shows_npm_uninstall(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Windows instructions still show npm uninstall."""
        install_claude._warn_npm_removal_failed(npm_path=r'C:\npm.cmd')
        captured = capsys.readouterr()
        combined = captured.err + captured.out
        assert 'npm' in combined
        assert 'uninstall' in combined

    @patch('install_claude._get_npm_global_prefix', return_value='/usr/local')
    @patch('sys.platform', 'linux')
    def test_uses_dynamic_prefix(self, mock_prefix: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
        """Uses dynamic prefix path when available."""
        assert mock_prefix.return_value == '/usr/local'
        install_claude._warn_npm_removal_failed(npm_path='/usr/bin/npm')
        captured = capsys.readouterr()
        combined = captured.err + captured.out
        assert '/usr/local/lib/node_modules/@anthropic-ai' in combined
        assert '/usr/local/bin/claude' in combined


class TestCheckNpmClaudeInstalled:
    """Tests for _check_npm_claude_installed() helper."""

    @patch('install_claude.run_command')
    @patch('install_claude.find_command', return_value=None)
    def test_returns_false_when_npm_not_found(
        self, mock_find: MagicMock, mock_run: MagicMock,
    ) -> None:
        """Returns False when npm is not installed."""
        del mock_find
        assert install_claude._check_npm_claude_installed() is False
        mock_run.assert_not_called()

    @patch('install_claude.run_command')
    @patch('install_claude.find_command', return_value='/usr/bin/npm')
    def test_returns_true_when_installed(
        self, mock_find: MagicMock, mock_run: MagicMock,
    ) -> None:
        """Returns True when npm list -g succeeds."""
        del mock_find
        mock_run.return_value = MagicMock(returncode=0)
        assert install_claude._check_npm_claude_installed() is True

    @patch('install_claude.run_command')
    @patch('install_claude.find_command', return_value='/usr/bin/npm')
    def test_returns_false_when_not_installed(
        self, mock_find: MagicMock, mock_run: MagicMock,
    ) -> None:
        """Returns False when npm list -g reports package not found."""
        del mock_find
        mock_run.return_value = MagicMock(returncode=1)
        assert install_claude._check_npm_claude_installed() is False


class TestFinalizeNativeInstall:
    """Tests for _finalize_native_install() cleanup sequence."""

    @patch('install_claude.update_install_method_config')
    @patch('install_claude._check_npm_claude_installed')
    @patch('install_claude.remove_npm_claude', return_value=True)
    def test_skips_npm_check_on_successful_removal(
        self, mock_remove: MagicMock, mock_check: MagicMock, mock_config: MagicMock,
    ) -> None:
        """_check_npm_claude_installed is NOT called when removal succeeds."""
        install_claude._finalize_native_install()

        mock_remove.assert_called_once()
        mock_check.assert_not_called()
        mock_config.assert_called_once_with('native')

    @patch('install_claude.update_install_method_config')
    @patch('install_claude._check_npm_claude_installed', return_value=True)
    @patch('install_claude.remove_npm_claude', return_value=False)
    def test_checks_npm_on_failed_removal(
        self, mock_remove: MagicMock, mock_check: MagicMock, mock_config: MagicMock,
    ) -> None:
        """_check_npm_claude_installed IS called when removal fails."""
        install_claude._finalize_native_install()

        mock_remove.assert_called_once()
        mock_check.assert_called_once()
        mock_config.assert_called_once_with('native')

    @patch('install_claude.update_install_method_config')
    @patch('install_claude._check_npm_claude_installed', return_value=False)
    @patch('install_claude.remove_npm_claude', return_value=False)
    def test_no_extra_warning_when_npm_check_returns_false(
        self, mock_remove: MagicMock, mock_check: MagicMock, mock_config: MagicMock,
    ) -> None:
        """No additional warning when npm is already gone despite failure return."""
        install_claude._finalize_native_install()

        mock_remove.assert_called_once()
        mock_check.assert_called_once()
        mock_config.assert_called_once_with('native')

    @patch('install_claude.update_install_method_config')
    def test_always_updates_config_to_native(
        self, mock_config: MagicMock,
    ) -> None:
        """Config is always updated to 'native' regardless of removal outcome."""
        with patch('install_claude.remove_npm_claude', return_value=True):
            install_claude._finalize_native_install()
        mock_config.assert_called_once_with('native')

    @patch('install_claude.update_install_method_config')
    @patch('install_claude._warn_npm_removal_failed')
    @patch('install_claude._check_npm_claude_installed', return_value=True)
    @patch('install_claude.remove_npm_claude', return_value=False)
    def test_does_not_call_warn_directly(
        self, mock_remove: MagicMock, mock_check: MagicMock, mock_warn: MagicMock, mock_config: MagicMock,
    ) -> None:
        """_finalize_native_install does not call _warn_npm_removal_failed directly.

        Warning display is handled by remove_npm_claude() itself when all
        removal strategies are exhausted. _finalize_native_install() must NOT
        call _warn_npm_removal_failed() separately to avoid double-warning.
        """
        install_claude._finalize_native_install()

        mock_remove.assert_called_once()
        mock_check.assert_called_once()
        mock_config.assert_called_once_with('native')
        # _warn_npm_removal_failed should NOT be called directly by _finalize_native_install
        mock_warn.assert_not_called()


class TestVerifyClaudeInstallationUsrLocalBin:
    """Tests for /usr/local/bin classification and native-path-first."""

    @patch('sys.platform', 'linux')
    @patch('install_claude.find_command', return_value='/usr/local/bin/claude')
    def test_usr_local_bin_classified_as_unknown(self, mock_find: MagicMock) -> None:
        """/usr/local/bin/claude is classified as 'unknown', not 'native'."""
        del mock_find
        with patch('pathlib.Path.exists', return_value=False):
            is_installed, path, source = install_claude.verify_claude_installation()
        assert is_installed is True
        assert source == 'unknown'

    @patch('sys.platform', 'linux')
    def test_unix_native_path_first(self) -> None:
        """When ~/.local/bin/claude exists with valid size, returns 'native' immediately."""
        mock_stat = MagicMock()
        mock_stat.st_size = 5000
        with patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.stat', return_value=mock_stat):
            is_installed, path, source = install_claude.verify_claude_installation()
        assert is_installed is True
        assert source == 'native'
        assert '.local' in (path or '')


class TestFindCommandRobustNativeFirst:
    """Tests for native-path-first check in find_command()."""

    @patch('sys.platform', 'linux')
    def test_native_path_returned_first(self) -> None:
        """When ~/.local/bin/claude exists, returns it before PATH search."""
        mock_stat = MagicMock()
        mock_stat.st_size = 5000
        with patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.stat', return_value=mock_stat), \
             patch('shutil.which', return_value='/usr/local/bin/claude'):
            result = install_claude.find_command('claude')
        assert result is not None
        assert '.local' in result

    @patch('sys.platform', 'linux')
    def test_falls_through_when_native_absent(self) -> None:
        """Falls through to shutil.which when native path does not exist."""
        with patch('pathlib.Path.exists', return_value=False), \
             patch('shutil.which', return_value='/usr/local/bin/claude'):
            result = install_claude.find_command('claude')
        assert result == '/usr/local/bin/claude'


class TestGetClaudeVersionExplicitPath:
    """Tests for get_claude_version() with explicit path parameter."""

    @patch('install_claude.run_command')
    def test_uses_explicit_path(self, mock_run: MagicMock) -> None:
        """When called with explicit path, uses that path directly."""
        mock_run.return_value = MagicMock(returncode=0, stdout='claude, version 2.0.14')
        result = install_claude.get_claude_version('/explicit/claude')
        assert result == '2.0.14'
        mock_run.assert_called_once_with(['/explicit/claude', '--version'])

    @patch('install_claude.find_command', return_value='/found/claude')
    @patch('install_claude.run_command')
    def test_falls_back_to_find_command(
        self, mock_run: MagicMock, mock_find: MagicMock,
    ) -> None:
        """When called without path, uses find_command()."""
        mock_run.return_value = MagicMock(returncode=0, stdout='claude, version 1.0.0')
        result = install_claude.get_claude_version()
        assert result == '1.0.0'
        mock_find.assert_called_once_with('claude')


class TestEnsureLocalBinInPathUnixProfileCreation:
    """Tests for _ensure_local_bin_in_path_unix() profile creation fix."""

    @patch('sys.platform', 'linux')
    def test_creates_bashrc_for_bash_shell(self, tmp_path: Path) -> None:
        """Creates .bashrc when current shell is bash and file does not exist."""
        with patch('install_claude.get_real_user_home', return_value=tmp_path), \
             patch.dict(os.environ, {'SHELL': '/bin/bash', 'PATH': ''}), \
             patch('install_claude.shutil.which', return_value=None):
            install_claude._ensure_local_bin_in_path_unix()

        bashrc = tmp_path / '.bashrc'
        assert bashrc.exists()
        content = bashrc.read_text()
        assert '.local/bin' in content
        assert install_claude.SHELL_CONFIG_MARKER_START in content

    @patch('sys.platform', 'linux')
    def test_creates_zshrc_for_zsh_shell(self, tmp_path: Path) -> None:
        """Creates .zshrc when current shell is zsh and file does not exist."""
        with patch('install_claude.get_real_user_home', return_value=tmp_path), \
             patch.dict(os.environ, {'SHELL': '/bin/zsh', 'PATH': ''}), \
             patch('install_claude.shutil.which', return_value='/usr/bin/zsh'):
            install_claude._ensure_local_bin_in_path_unix()

        zshrc = tmp_path / '.zshrc'
        assert zshrc.exists()
        content = zshrc.read_text()
        assert '.local/bin' in content
        assert install_claude.SHELL_CONFIG_MARKER_START in content

    @patch('sys.platform', 'linux')
    def test_creates_fish_config_for_fish_shell(self, tmp_path: Path) -> None:
        """Creates config.fish when current shell is fish and file does not exist."""
        with patch('install_claude.get_real_user_home', return_value=tmp_path), \
             patch.dict(os.environ, {'SHELL': '/usr/bin/fish', 'PATH': ''}), \
             patch('install_claude.shutil.which', return_value='/usr/bin/fish'):
            install_claude._ensure_local_bin_in_path_unix()

        fish_config = tmp_path / '.config' / 'fish' / 'config.fish'
        assert fish_config.exists()
        content = fish_config.read_text()
        assert 'fish_add_path' in content
        assert install_claude.SHELL_CONFIG_MARKER_START in content

    @patch('sys.platform', 'linux')
    def test_does_not_create_for_unknown_shell(self, tmp_path: Path) -> None:
        """Does not create profile files when shell is unknown (e.g. tcsh)."""
        with patch('install_claude.get_real_user_home', return_value=tmp_path), \
             patch.dict(os.environ, {'SHELL': '/bin/tcsh', 'PATH': ''}), \
             patch('install_claude.shutil.which', return_value=None):
            install_claude._ensure_local_bin_in_path_unix()

        assert not (tmp_path / '.bashrc').exists()
        assert not (tmp_path / '.zshrc').exists()

    @patch('sys.platform', 'linux')
    def test_updates_existing_profiles(self, tmp_path: Path) -> None:
        """Updates existing profile files without creating new ones."""
        bashrc = tmp_path / '.bashrc'
        bashrc.write_text('# existing content\n')

        with patch('install_claude.get_real_user_home', return_value=tmp_path), \
             patch.dict(os.environ, {'SHELL': '/bin/bash', 'PATH': ''}), \
             patch('install_claude.shutil.which', return_value=None):
            install_claude._ensure_local_bin_in_path_unix()

        content = bashrc.read_text()
        assert '# existing content' in content
        assert '.local/bin' in content
        assert install_claude.SHELL_CONFIG_MARKER_START in content


class TestUpdateInstallMethodConfig:
    """Test update_install_method_config() function for config updates."""

    def test_update_config_file_modification(
        self, tmp_path: Path,
    ) -> None:
        """Test update_install_method_config updates config file."""
        config_file = tmp_path / '.claude.json'
        config_file.write_text('{"existingKey": "value"}')

        with patch('install_claude.Path.home', return_value=tmp_path):
            result = install_claude.update_install_method_config('native')

        assert result is True
        config = json.loads(config_file.read_text())
        assert config['installMethod'] == 'native'
        assert config['existingKey'] == 'value'

    def test_update_config_creates_new_file(
        self, tmp_path: Path,
    ) -> None:
        """Test update_install_method_config creates config file if missing."""
        config_file = tmp_path / '.claude.json'
        assert not config_file.exists()

        with patch('install_claude.Path.home', return_value=tmp_path):
            result = install_claude.update_install_method_config('native')

        assert result is True
        assert config_file.exists()
        config = json.loads(config_file.read_text())
        assert config == {'installMethod': 'native'}

    def test_update_config_corrupted_file(
        self, tmp_path: Path,
    ) -> None:
        """Test update_install_method_config handles corrupted config file gracefully."""
        config_file = tmp_path / '.claude.json'
        config_file.write_text('not valid json {{{')

        with patch('install_claude.Path.home', return_value=tmp_path):
            result = install_claude.update_install_method_config('native')

        # Resilient handling: starts fresh and still writes successfully
        assert result is True
        config = json.loads(config_file.read_text())
        assert config == {'installMethod': 'native'}

    def test_update_config_permission_denied(
        self, tmp_path: Path,
    ) -> None:
        """Test update_install_method_config handles permission errors."""
        config_file = tmp_path / '.claude.json'
        config_file.write_text('{}')

        with (
            patch('install_claude.Path.home', return_value=tmp_path),
            patch.object(Path, 'write_text', side_effect=PermissionError('Permission denied')),
        ):
            result = install_claude.update_install_method_config('native')

        assert result is False

    def test_update_config_preserves_existing_keys(
        self, tmp_path: Path,
    ) -> None:
        """Test update_install_method_config preserves other config keys."""
        config_file = tmp_path / '.claude.json'
        existing_config = {
            'theme': 'dark',
            'telemetry': False,
            'installMethod': 'global',
        }
        config_file.write_text(json.dumps(existing_config))

        with patch('install_claude.Path.home', return_value=tmp_path):
            result = install_claude.update_install_method_config('native')

        assert result is True
        config = json.loads(config_file.read_text())
        assert config['installMethod'] == 'native'
        assert config['theme'] == 'dark'
        assert config['telemetry'] is False

    def test_update_config_npm_global_method_file(
        self, tmp_path: Path,
    ) -> None:
        """Test update_install_method_config works with npm-global method."""
        config_file = tmp_path / '.claude.json'
        config_file.write_text('{}')

        with patch('install_claude.Path.home', return_value=tmp_path):
            result = install_claude.update_install_method_config('npm-global')

        assert result is True
        config = json.loads(config_file.read_text())
        assert config['installMethod'] == 'npm-global'


class TestUpdateInstallMethodConfigDeepMerge:
    """Test update_install_method_config deep-merge-compatible behavior."""

    def test_handles_non_dict_json(self, tmp_path: Path) -> None:
        """Non-dict JSON starts fresh with warning."""
        config_file = tmp_path / '.claude.json'
        config_file.write_text('["array", "not", "dict"]')

        with patch('install_claude.Path.home', return_value=tmp_path):
            result = install_claude.update_install_method_config('native')

        assert result is True
        config = json.loads(config_file.read_text())
        assert config == {'installMethod': 'native'}

    def test_handles_empty_file(self, tmp_path: Path) -> None:
        """Empty file is treated as empty dict."""
        config_file = tmp_path / '.claude.json'
        config_file.write_text('')

        with patch('install_claude.Path.home', return_value=tmp_path):
            result = install_claude.update_install_method_config('native')

        assert result is True
        config = json.loads(config_file.read_text())
        assert config == {'installMethod': 'native'}

    def test_preserves_all_existing_keys(self, tmp_path: Path) -> None:
        """Preserves all existing keys including complex structures."""
        config_file = tmp_path / '.claude.json'
        existing = {
            'autoConnectIde': True,
            'editorMode': 'vim',
            'mcpServers': {'server1': {'url': 'http://localhost:3000'}},
            'showTurnDuration': True,
        }
        config_file.write_text(json.dumps(existing))

        with patch('install_claude.Path.home', return_value=tmp_path):
            result = install_claude.update_install_method_config('native')

        assert result is True
        config = json.loads(config_file.read_text())
        assert config['installMethod'] == 'native'
        assert config['autoConnectIde'] is True
        assert config['editorMode'] == 'vim'
        assert config['mcpServers'] == existing['mcpServers']
        assert config['showTurnDuration'] is True

    def test_file_ends_with_newline(self, tmp_path: Path) -> None:
        """Written file ends with newline for consistency."""
        config_file = tmp_path / '.claude.json'

        with patch('install_claude.Path.home', return_value=tmp_path):
            install_claude.update_install_method_config('native')

        content = config_file.read_text()
        assert content.endswith('\n')

    def test_coexistence_install_then_global_config(self, tmp_path: Path) -> None:
        """install_method then global_config preserves both."""
        config_file = tmp_path / '.claude.json'

        # First: install_claude writes installMethod
        with patch('install_claude.Path.home', return_value=tmp_path):
            install_claude.update_install_method_config('native')

        # Second: setup_environment writes global config
        with patch.object(Path, 'home', return_value=tmp_path):
            import scripts.setup_environment as setup_env
            setup_env.write_global_config({'autoConnectIde': True})

        config = json.loads(config_file.read_text())
        assert config['installMethod'] == 'native'
        assert config['autoConnectIde'] is True

    def test_coexistence_global_config_then_install(self, tmp_path: Path) -> None:
        """global_config then install_method preserves both."""
        config_file = tmp_path / '.claude.json'

        # First: setup_environment writes global config
        with patch.object(Path, 'home', return_value=tmp_path):
            import scripts.setup_environment as setup_env
            setup_env.write_global_config({'editorMode': 'vim'})

        # Second: install_claude writes installMethod
        with patch('install_claude.Path.home', return_value=tmp_path):
            install_claude.update_install_method_config('native')

        config = json.loads(config_file.read_text())
        assert config['editorMode'] == 'vim'
        assert config['installMethod'] == 'native'


class TestNativeInstallCallsConfigUpdate:
    """Test that native installation functions call update_install_method_config."""

    def test_windows_native_install_calls_config_update(
        self,
    ) -> None:
        """Test install_claude_native_windows calls update_install_method_config."""
        with (
            patch('install_claude.ensure_local_bin_in_path_windows'),
            patch('platform.system', return_value='Windows'),
            patch('install_claude._download_claude_direct_from_gcs', return_value=True),
            patch('pathlib.Path.chmod'),  # Mock chmod to prevent file operations
            patch(
                'install_claude.verify_claude_installation',
                return_value=(True, '/path/to/claude', 'native'),
            ),
            patch('install_claude.remove_npm_claude') as mock_remove_npm,
            patch('install_claude.update_install_method_config') as mock_update_config,
        ):
            install_claude.install_claude_native_windows(version='2.0.76')

            mock_remove_npm.assert_called_once()
            mock_update_config.assert_called_once_with('native')

    def test_macos_native_install_calls_config_update(
        self,
    ) -> None:
        """Test install_claude_native_macos calls update_install_method_config."""
        with (
            patch('install_claude._ensure_local_bin_in_path_unix'),
            patch('sys.platform', 'darwin'),
            patch('install_claude._download_claude_direct_from_gcs', return_value=True),
            patch('pathlib.Path.chmod'),  # Mock chmod to prevent file operations
            patch(
                'install_claude.verify_claude_installation',
                return_value=(True, '/path/to/claude', 'native'),
            ),
            patch('install_claude.remove_npm_claude') as mock_remove_npm,
            patch('install_claude.update_install_method_config') as mock_update_config,
        ):
            install_claude.install_claude_native_macos(version='2.0.76')

            mock_remove_npm.assert_called_once()
            mock_update_config.assert_called_once_with('native')


class TestRootGuard:
    """Test root detection guard in install_claude.py main()."""

    def test_root_guard_exits_when_root_without_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Running as root without CLAUDE_CODE_TOOLBOX_ALLOW_ROOT=1 exits with code 1."""
        monkeypatch.delenv('CLAUDE_CODE_TOOLBOX_ALLOW_ROOT', raising=False)
        with (
            patch('platform.system', return_value='Linux'),
            patch('os.geteuid', create=True, return_value=0),
            pytest.raises(SystemExit) as exc_info,
        ):
            install_claude.main()
        assert exc_info.value.code == 1

    def test_root_guard_allows_when_override_set(self) -> None:
        """CLAUDE_CODE_TOOLBOX_ALLOW_ROOT=1 allows root execution to proceed past the guard."""
        with (
            patch('platform.system', return_value='Linux'),
            patch('os.geteuid', create=True, return_value=0),
            patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_ALLOW_ROOT': '1', 'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'npm'}),
            patch.object(install_claude, 'ensure_nodejs', return_value=True),
            patch.object(install_claude, 'ensure_claude', return_value=True),
            contextlib.suppress(SystemExit),
        ):
            install_claude.main()

    def test_root_guard_skipped_on_windows(self) -> None:
        """Root guard does not activate on Windows."""
        with (
            patch('platform.system', return_value='Windows'),
            patch.object(install_claude, 'ensure_git_bash_windows', return_value='C:\\Git\\bash.exe'),
            patch.object(install_claude, 'ensure_claude', return_value=True),
            patch.object(install_claude, 'configure_powershell_policy'),
            patch.object(install_claude, 'update_path'),
            patch('shutil.which', return_value=None),
            patch.object(install_claude, 'set_windows_env_var'),
            patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'native'}),
            contextlib.suppress(SystemExit),
        ):
            install_claude.main()

    def test_root_guard_skipped_for_non_root(self) -> None:
        """Non-root users (euid != 0) pass through root guard."""
        with (
            patch('platform.system', return_value='Linux'),
            patch('os.geteuid', create=True, return_value=1000),
            patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'npm'}),
            patch.object(install_claude, 'ensure_nodejs', return_value=True),
            patch.object(install_claude, 'ensure_claude', return_value=True),
            contextlib.suppress(SystemExit),
        ):
            install_claude.main()

    def test_root_guard_error_message_content(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Root guard error message contains key information."""
        monkeypatch.delenv('CLAUDE_CODE_TOOLBOX_ALLOW_ROOT', raising=False)
        with (
            patch('platform.system', return_value='Linux'),
            patch('os.geteuid', create=True, return_value=0),
            pytest.raises(SystemExit),
        ):
            install_claude.main()
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert 'root' in combined.lower() or 'sudo' in combined.lower()
        assert 'CLAUDE_CODE_TOOLBOX_ALLOW_ROOT' in combined

    def test_root_guard_works_on_macos(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Root guard activates on macOS (Darwin) the same as Linux."""
        monkeypatch.delenv('CLAUDE_CODE_TOOLBOX_ALLOW_ROOT', raising=False)
        with (
            patch('platform.system', return_value='Darwin'),
            patch('os.geteuid', create=True, return_value=0),
            pytest.raises(SystemExit) as exc_info,
        ):
            install_claude.main()
        assert exc_info.value.code == 1


class TestInstallClaudeNpmSudo:
    """Test sudo fallback behavior in install_claude_npm (via _run_with_sudo_fallback)."""

    @patch('platform.system', return_value='Linux')
    @patch('install_claude.find_command', return_value='/usr/bin/npm')
    @patch('install_claude.needs_sudo_for_npm', return_value=True)
    @patch('install_claude.run_command')
    @patch('install_claude._run_with_sudo_fallback')
    def test_sudo_uses_resolved_npm_path(
        self, mock_sudo, mock_run_command,
        mock_needs_sudo, mock_find, mock_system,
    ):
        """Sudo fallback uses resolved npm_path, not bare 'npm'."""
        assert mock_needs_sudo.return_value is True
        assert mock_find.return_value == '/usr/bin/npm'
        assert mock_system.return_value == 'Linux'
        with patch('pathlib.Path.exists', return_value=True):
            mock_run_command.return_value = subprocess.CompletedProcess(
                [], 1, '', 'permission denied',
            )
            mock_sudo.return_value = subprocess.CompletedProcess([], 0, '', '')

            result = install_claude.install_claude_npm()

            assert result is True
            mock_sudo.assert_called_once()
            sudo_cmd = mock_sudo.call_args[0][0]
            assert sudo_cmd[0] == '/usr/bin/npm'

    @patch('platform.system', return_value='Linux')
    @patch('install_claude.find_command', return_value='/usr/bin/npm')
    @patch('install_claude.needs_sudo_for_npm', return_value=True)
    @patch('install_claude.run_command')
    @patch('install_claude._run_with_sudo_fallback')
    def test_tty_aware_guidance_when_no_tty(
        self, mock_sudo, mock_run_command,
        mock_needs_sudo, mock_find, mock_system, capsys,
    ):
        """Provides guidance when _run_with_sudo_fallback returns None."""
        assert mock_needs_sudo.return_value is True
        assert mock_find.return_value == '/usr/bin/npm'
        assert mock_system.return_value == 'Linux'
        with patch('pathlib.Path.exists', return_value=True):
            mock_run_command.return_value = subprocess.CompletedProcess(
                [], 1, '', 'permission denied',
            )
            mock_sudo.return_value = None

            result = install_claude.install_claude_npm()

            assert result is False
            captured = capsys.readouterr()
            combined = captured.out + captured.err
            assert 'cannot use sudo' in combined.lower()

    @patch('platform.system', return_value='Linux')
    @patch('install_claude.find_command', return_value='/usr/bin/npm')
    @patch('install_claude.needs_sudo_for_npm', return_value=False)
    @patch('install_claude.run_command')
    @patch('install_claude._run_with_sudo_fallback')
    def test_tty_aware_guidance_when_tty_available(
        self, mock_sudo, mock_run_command,
        mock_needs_sudo, mock_find, mock_system,
    ):
        """Sudo succeeds when _run_with_sudo_fallback returns success."""
        assert mock_needs_sudo.return_value is False
        assert mock_find.return_value == '/usr/bin/npm'
        assert mock_system.return_value == 'Linux'
        with patch('pathlib.Path.exists', return_value=True):
            mock_run_command.return_value = subprocess.CompletedProcess(
                [], 1, '', 'permission denied',
            )
            mock_sudo.return_value = subprocess.CompletedProcess([], 0, '', '')

            result = install_claude.install_claude_npm()

            assert result is True
            mock_sudo.assert_called_once()

    @patch('platform.system', return_value='Linux')
    @patch('install_claude.find_command', return_value='/usr/bin/npm')
    @patch('install_claude.needs_sudo_for_npm', return_value=True)
    @patch('install_claude.run_command')
    @patch('install_claude._run_with_sudo_fallback')
    def test_sudo_timeout_handled_gracefully(
        self, mock_sudo, mock_run_command,
        mock_needs_sudo, mock_find, mock_system,
    ):
        """Timeout is handled gracefully (returns None from helper)."""
        assert mock_needs_sudo.return_value is True
        assert mock_find.return_value == '/usr/bin/npm'
        assert mock_system.return_value == 'Linux'
        with patch('pathlib.Path.exists', return_value=True):
            mock_run_command.return_value = subprocess.CompletedProcess(
                [], 1, '', 'permission denied',
            )
            mock_sudo.return_value = None

            result = install_claude.install_claude_npm()

            assert result is False

    @patch('platform.system', return_value='Linux')
    @patch('install_claude.find_command', return_value='/usr/bin/npm')
    @patch('install_claude.needs_sudo_for_npm', return_value=True)
    @patch('install_claude.run_command')
    @patch('install_claude._run_with_sudo_fallback')
    def test_sudo_capture_output_enabled(
        self, mock_sudo, mock_run_command,
        mock_needs_sudo, mock_find, mock_system,
    ):
        """_run_with_sudo_fallback is called with capture_output=True."""
        assert mock_needs_sudo.return_value is True
        assert mock_find.return_value == '/usr/bin/npm'
        assert mock_system.return_value == 'Linux'
        with patch('pathlib.Path.exists', return_value=True):
            mock_run_command.return_value = subprocess.CompletedProcess(
                [], 1, '', 'permission denied',
            )
            mock_sudo.return_value = subprocess.CompletedProcess([], 0, '', '')

            install_claude.install_claude_npm()

            mock_sudo.assert_called_once()
            assert mock_sudo.call_args[1]['capture_output'] is True

    @patch('platform.system', return_value='Linux')
    @patch('install_claude.find_command', return_value='/usr/bin/npm')
    @patch('install_claude.needs_sudo_for_npm', return_value=True)
    @patch('install_claude.run_command')
    @patch('install_claude._run_with_sudo_fallback')
    def test_pre_warning_when_sudo_predicted(
        self, mock_sudo, mock_run_command,
        mock_needs_sudo, mock_find, mock_system, capsys,
    ):
        """Pre-warning shown when needs_sudo_for_npm is True."""
        assert mock_needs_sudo.return_value is True
        assert mock_find.return_value == '/usr/bin/npm'
        assert mock_system.return_value == 'Linux'
        with patch('pathlib.Path.exists', return_value=True):
            mock_run_command.return_value = subprocess.CompletedProcess(
                [], 1, '', 'permission denied',
            )
            mock_sudo.return_value = subprocess.CompletedProcess([], 0, '', '')

            install_claude.install_claude_npm()

            captured = capsys.readouterr()
            combined = captured.out + captured.err
            assert 'elevated permissions' in combined.lower()

    @patch('platform.system', return_value='Linux')
    @patch('install_claude.find_command', return_value='/usr/bin/npm')
    @patch('install_claude.needs_sudo_for_npm', return_value=True)
    @patch('install_claude.run_command')
    @patch('install_claude._run_with_sudo_fallback')
    def test_enhanced_error_on_total_failure(
        self, mock_sudo, mock_run_command,
        mock_needs_sudo, mock_find, mock_system, capsys,
    ):
        """Enhanced error messages on total failure."""
        del capsys
        assert mock_needs_sudo.return_value is True
        assert mock_find.return_value == '/usr/bin/npm'
        assert mock_system.return_value == 'Linux'
        with patch('pathlib.Path.exists', return_value=True):
            mock_run_command.return_value = subprocess.CompletedProcess(
                [], 1, '', 'permission denied',
            )
            mock_sudo.return_value = subprocess.CompletedProcess([], 1, '', 'failed')

            result = install_claude.install_claude_npm()

            assert result is False

    @patch('platform.system', return_value='Linux')
    @patch('install_claude.find_command', return_value='/usr/bin/npm')
    @patch('install_claude.needs_sudo_for_npm', return_value=True)
    @patch('install_claude.run_command')
    @patch('install_claude._run_with_sudo_fallback')
    def test_sudo_success_with_specific_version(
        self, mock_sudo, mock_run_command,
        mock_needs_sudo, mock_find, mock_system,
    ):
        """Sudo fallback succeeds when installing a specific version."""
        assert mock_needs_sudo.return_value is True
        assert mock_find.return_value == '/usr/bin/npm'
        assert mock_system.return_value == 'Linux'
        with patch('pathlib.Path.exists', return_value=True):
            # First call from run_command: npm view (version check succeeds)
            # Second call from run_command: npm install (fails, triggers sudo)
            mock_run_command.side_effect = [
                subprocess.CompletedProcess([], 0, '1.2.3', ''),
                subprocess.CompletedProcess([], 1, '', 'permission denied'),
            ]
            mock_sudo.return_value = subprocess.CompletedProcess([], 0, '', '')

            result = install_claude.install_claude_npm(version='1.2.3')

            assert result is True

    @patch('platform.system', return_value='Windows')
    @patch('install_claude.find_command', return_value=r'C:\Program Files\nodejs\npm.cmd')
    @patch('install_claude.run_command')
    @patch('install_claude._run_with_sudo_fallback')
    def test_no_sudo_attempt_on_windows(
        self, mock_sudo, mock_run_command, mock_find, mock_system,
    ):
        """No sudo attempt on Windows."""
        del mock_find
        assert mock_system.return_value == 'Windows'
        with patch('pathlib.Path.exists', return_value=True):
            mock_run_command.return_value = subprocess.CompletedProcess(
                [], 1, '', 'permission denied',
            )

            result = install_claude.install_claude_npm()

            assert result is False
            mock_sudo.assert_not_called()


class TestInstallClaudeNpmSudoGating:
    """Test pre-sudo TTY/credentials gating in install_claude_npm (via _run_with_sudo_fallback)."""

    @patch('platform.system', return_value='Linux')
    @patch('install_claude.find_command', return_value='/usr/bin/npm')
    @patch('install_claude.needs_sudo_for_npm', return_value=True)
    @patch('install_claude.run_command')
    @patch('install_claude._run_with_sudo_fallback')
    def test_npm_sudo_skipped_without_tty_and_no_cached_creds(
        self, mock_sudo, mock_run_command,
        mock_needs_sudo, mock_find, mock_system, capsys,
    ):
        """Sudo is skipped when _run_with_sudo_fallback returns None."""
        assert mock_needs_sudo.return_value is True
        assert mock_find.return_value == '/usr/bin/npm'
        assert mock_system.return_value == 'Linux'
        with patch('pathlib.Path.exists', return_value=True):
            mock_run_command.return_value = subprocess.CompletedProcess(
                [], 1, '', 'permission denied',
            )
            mock_sudo.return_value = None

            result = install_claude.install_claude_npm()

            assert result is False
            mock_sudo.assert_called_once()
            captured = capsys.readouterr()
            combined = captured.out + captured.err
            assert 'cannot use sudo' in combined.lower()

    @patch('platform.system', return_value='Linux')
    @patch('install_claude.find_command', return_value='/usr/bin/npm')
    @patch('install_claude.needs_sudo_for_npm', return_value=True)
    @patch('install_claude.run_command')
    @patch('install_claude._run_with_sudo_fallback')
    def test_npm_sudo_attempted_with_cached_creds_no_tty(
        self, mock_sudo, mock_run_command,
        mock_needs_sudo, mock_find, mock_system,
    ):
        """Sudo succeeds when _run_with_sudo_fallback returns success."""
        assert mock_needs_sudo.return_value is True
        assert mock_find.return_value == '/usr/bin/npm'
        assert mock_system.return_value == 'Linux'
        with patch('pathlib.Path.exists', return_value=True):
            mock_run_command.return_value = subprocess.CompletedProcess(
                [], 1, '', 'permission denied',
            )
            mock_sudo.return_value = subprocess.CompletedProcess([], 0, '', '')

            result = install_claude.install_claude_npm()

            assert result is True
            mock_sudo.assert_called_once()
            sudo_cmd = mock_sudo.call_args[0][0]
            assert sudo_cmd[0] == '/usr/bin/npm'

    @patch('platform.system', return_value='Linux')
    @patch('install_claude.find_command', return_value='/usr/bin/npm')
    @patch('install_claude.needs_sudo_for_npm', return_value=False)
    @patch('install_claude.run_command')
    @patch('install_claude._run_with_sudo_fallback')
    def test_npm_sudo_attempted_with_tty(
        self, mock_sudo, mock_run_command,
        mock_needs_sudo, mock_find, mock_system,
    ):
        """Sudo is attempted directly via _run_with_sudo_fallback."""
        assert mock_needs_sudo.return_value is False
        assert mock_find.return_value == '/usr/bin/npm'
        assert mock_system.return_value == 'Linux'
        with patch('pathlib.Path.exists', return_value=True):
            mock_run_command.return_value = subprocess.CompletedProcess(
                [], 1, '', 'permission denied',
            )
            mock_sudo.return_value = subprocess.CompletedProcess([], 0, '', '')

            result = install_claude.install_claude_npm()

            assert result is True
            mock_sudo.assert_called_once()
            sudo_cmd = mock_sudo.call_args[0][0]
            assert sudo_cmd[0] == '/usr/bin/npm'

    @patch('platform.system', return_value='Linux')
    @patch('install_claude.find_command', return_value='/usr/bin/npm')
    @patch('install_claude.needs_sudo_for_npm', return_value=True)
    @patch('install_claude.run_command')
    @patch('install_claude._run_with_sudo_fallback')
    def test_npm_sudo_filenotfounderror_handled(
        self, mock_sudo, mock_run_command,
        mock_needs_sudo, mock_find, mock_system,
    ):
        """_run_with_sudo_fallback returning None is handled gracefully."""
        assert mock_needs_sudo.return_value is True
        assert mock_find.return_value == '/usr/bin/npm'
        assert mock_system.return_value == 'Linux'
        with patch('pathlib.Path.exists', return_value=True):
            mock_run_command.return_value = subprocess.CompletedProcess(
                [], 1, '', 'permission denied',
            )
            mock_sudo.return_value = None

            result = install_claude.install_claude_npm()

            assert result is False


class TestNeedsSudoForNpm:
    """Test needs_sudo_for_npm() function for sudo requirement detection."""

    def test_returns_false_on_windows(self) -> None:
        """Windows should always return False (no sudo concept)."""
        with patch('platform.system', return_value='Windows'):
            assert install_claude.needs_sudo_for_npm() is False

    def test_returns_false_when_npm_not_found(self) -> None:
        """When npm is not installed, returns False."""
        with (
            patch('platform.system', return_value='Linux'),
            patch('shutil.which', return_value=None),
        ):
            assert install_claude.needs_sudo_for_npm() is False

    def test_returns_true_when_no_write_access(self) -> None:
        """Returns True when user cannot write to npm global directory."""
        with (
            patch('platform.system', return_value='Linux'),
            patch('shutil.which', return_value='/usr/bin/npm'),
            patch.object(
                install_claude, 'run_command',
                return_value=subprocess.CompletedProcess([], 0, '/usr/local\n', ''),
            ),
            patch('os.access', return_value=False),
        ):
            assert install_claude.needs_sudo_for_npm() is True

    def test_returns_false_when_write_access(self) -> None:
        """Returns False when user can write to npm global directory."""
        with (
            patch('platform.system', return_value='Linux'),
            patch('shutil.which', return_value='/usr/bin/npm'),
            patch.object(
                install_claude, 'run_command',
                return_value=subprocess.CompletedProcess([], 0, '/home/user/.npm-global\n', ''),
            ),
            patch('os.access', return_value=True),
        ):
            assert install_claude.needs_sudo_for_npm() is False

    def test_returns_false_when_npm_config_fails(self) -> None:
        """Returns False when npm config get prefix fails."""
        with (
            patch('platform.system', return_value='Linux'),
            patch('shutil.which', return_value='/usr/bin/npm'),
            patch.object(
                install_claude, 'run_command',
                return_value=subprocess.CompletedProcess([], 1, '', 'error'),
            ),
        ):
            assert install_claude.needs_sudo_for_npm() is False

    def test_returns_false_when_access_check_raises(self) -> None:
        """Returns False when os.access raises an exception."""
        with (
            patch('platform.system', return_value='Linux'),
            patch('shutil.which', return_value='/usr/bin/npm'),
            patch.object(
                install_claude, 'run_command',
                return_value=subprocess.CompletedProcess([], 0, '/usr/local\n', ''),
            ),
            patch('os.access', side_effect=OSError('Permission denied')),
        ):
            assert install_claude.needs_sudo_for_npm() is False


class TestEnsureClaudeErrorMessaging:
    """Test enhanced error messaging when all installation methods fail."""

    @patch('platform.system', return_value='Linux')
    @patch('install_claude.get_claude_version', return_value=None)
    @patch('install_claude.install_claude_native_cross_platform', return_value=False)
    @patch('install_claude.install_claude_npm', return_value=False)
    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'auto'}, clear=False)
    def test_all_methods_failed_shows_troubleshooting_unix(
        self, mock_npm, mock_native, mock_version, mock_system, capsys,
    ):
        """When all methods fail on Unix, show numbered troubleshooting steps."""
        assert mock_system.return_value == 'Linux'
        assert mock_version.return_value is None
        assert mock_native.return_value is False
        assert mock_npm.return_value is False

        result = install_claude.ensure_claude()

        assert result is False
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert 'troubleshooting' in combined.lower()
        assert 'sudo' in combined
        assert 'npm config set prefix' in combined
        assert 'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD' in combined

    @patch('platform.system', return_value='Windows')
    @patch('install_claude.get_claude_version', return_value=None)
    @patch('install_claude.install_claude_native_cross_platform', return_value=False)
    @patch('install_claude.install_claude_npm', return_value=False)
    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'auto'}, clear=False)
    def test_all_methods_failed_shows_troubleshooting_windows(
        self, mock_npm, mock_native, mock_version, mock_system, capsys,
    ):
        """When all methods fail on Windows, show platform-appropriate steps."""
        assert mock_system.return_value == 'Windows'
        assert mock_version.return_value is None
        assert mock_native.return_value is False
        assert mock_npm.return_value is False

        result = install_claude.ensure_claude()

        assert result is False
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert 'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD' in combined
        assert 'irm' in combined

    @patch('platform.system', return_value='Linux')
    @patch('install_claude.get_claude_version', return_value=None)
    @patch('install_claude.install_claude_native_cross_platform', return_value=False)
    @patch('install_claude.install_claude_npm', return_value=False)
    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'auto'}, clear=False)
    def test_native_fallback_suggests_method_override(
        self, mock_npm, mock_native, mock_version, mock_system, capsys,
    ):
        """When native fails and falls back to npm, suggest CLAUDE_CODE_TOOLBOX_INSTALL_METHOD."""
        assert mock_system.return_value == 'Linux'
        assert mock_version.return_value is None
        assert mock_native.return_value is False
        assert mock_npm.return_value is False

        install_claude.ensure_claude()

        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert 'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD=native' in combined or 'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD' in combined


class TestGetLatestClaudeVersionGitHub:
    """Tests for _get_latest_claude_version_github() GitHub API fallback."""

    @patch('install_claude.urllib.request.urlopen')
    def test_github_version_success(self, mock_urlopen):
        """Test successful version retrieval from GitHub API."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({'tag_name': 'v2.1.83'}).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        result = install_claude._get_latest_claude_version_github()
        assert result == '2.1.83'

    @patch('install_claude.urllib.request.urlopen')
    def test_github_version_strips_v_prefix(self, mock_urlopen):
        """Test that 'v' prefix is stripped from tag_name."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({'tag_name': 'v3.0.0'}).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        result = install_claude._get_latest_claude_version_github()
        assert result == '3.0.0'

    @patch('install_claude.urllib.request.urlopen')
    def test_github_version_no_v_prefix(self, mock_urlopen):
        """Test tag_name without 'v' prefix is returned as-is."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({'tag_name': '2.1.83'}).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        result = install_claude._get_latest_claude_version_github()
        assert result == '2.1.83'

    @patch('install_claude.urllib.request.urlopen')
    def test_github_version_network_error(self, mock_urlopen):
        """Test that network errors return None."""
        mock_urlopen.side_effect = urllib.error.URLError('Connection refused')
        result = install_claude._get_latest_claude_version_github()
        assert result is None

    @patch('install_claude.urllib.request.urlopen')
    def test_github_version_empty_tag(self, mock_urlopen):
        """Test that empty tag_name returns None."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({'tag_name': ''}).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        result = install_claude._get_latest_claude_version_github()
        assert result is None

    @patch('install_claude.urllib.request.urlopen')
    def test_github_version_missing_tag_name(self, mock_urlopen):
        """Test that missing tag_name key returns None."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({'name': 'some release'}).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        result = install_claude._get_latest_claude_version_github()
        assert result is None


class TestGetLatestClaudeVersionFallback:
    """Tests for get_latest_claude_version() npm-first with GitHub fallback."""

    @patch('install_claude._get_latest_claude_version_github', return_value='2.1.83')
    @patch('install_claude.find_command', return_value=None)
    def test_npm_unavailable_uses_github(self, mock_find, mock_github):
        """Test that GitHub API is used when npm is not available."""
        assert mock_find.return_value is None
        result = install_claude.get_latest_claude_version()
        assert result == '2.1.83'
        mock_github.assert_called_once()

    @patch('install_claude._get_latest_claude_version_github')
    @patch('install_claude.run_command')
    @patch('install_claude.find_command', return_value='/usr/bin/npm')
    def test_npm_available_prefers_npm(self, mock_find, mock_run, mock_github):
        """Test that npm result is used when npm is available."""
        assert mock_find.return_value == '/usr/bin/npm'
        mock_run.return_value = MagicMock(returncode=0, stdout='2.1.83')
        result = install_claude.get_latest_claude_version()
        assert result == '2.1.83'
        mock_github.assert_not_called()

    @patch('install_claude._get_latest_claude_version_github', return_value='2.1.83')
    @patch('install_claude.run_command')
    @patch('install_claude.find_command', return_value='/usr/bin/npm')
    def test_npm_fails_falls_back_to_github(self, mock_find, mock_run, mock_github):
        """Test that GitHub API is used when npm command fails."""
        assert mock_find.return_value == '/usr/bin/npm'
        mock_run.return_value = MagicMock(returncode=1, stdout='')
        result = install_claude.get_latest_claude_version()
        assert result == '2.1.83'
        mock_github.assert_called_once()

    @patch('install_claude._get_latest_claude_version_github', return_value=None)
    @patch('install_claude.find_command', return_value=None)
    def test_both_unavailable_returns_none(self, mock_find, mock_github):
        """Test that None is returned when both npm and GitHub fail."""
        assert mock_find.return_value is None
        assert mock_github.return_value is None
        result = install_claude.get_latest_claude_version()
        assert result is None


class TestVersionCheckFailureUX:
    """Tests for version-check failure UX."""

    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'auto'}, clear=False)
    @patch('install_claude.get_latest_claude_version', return_value=None)
    @patch('install_claude.verify_claude_installation', return_value=(True, '/usr/local/bin/claude', 'native'))
    @patch('install_claude.get_claude_version', return_value='2.0.76')
    def test_version_check_failure_shows_info(self, mock_ver, mock_verify, mock_latest, capsys):
        """Test that version check failure shows single info message."""
        assert mock_ver.return_value == '2.0.76'
        assert mock_verify.return_value[0] is True
        assert mock_latest.return_value is None
        result = install_claude.ensure_claude()
        assert result is True
        captured = capsys.readouterr()
        assert 'Claude Code version 2.0.76 is installed (could not check for updates)' in captured.out

    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'auto'}, clear=False)
    @patch('install_claude.get_latest_claude_version', return_value=None)
    @patch('install_claude.verify_claude_installation', return_value=(True, '/usr/local/bin/claude', 'native'))
    @patch('install_claude.get_claude_version', return_value='2.0.76')
    def test_version_check_failure_no_warning_no_success(self, mock_ver, mock_verify, mock_latest, capsys):
        """Test that no warning() or success() messages appear for version check failure."""
        assert mock_ver.return_value == '2.0.76'
        assert mock_verify.return_value[0] is True
        assert mock_latest.return_value is None
        install_claude.ensure_claude()
        captured = capsys.readouterr()
        assert 'Cannot determine latest version' not in captured.out
        assert 'is already installed' not in captured.out


class TestNodejsSkipMessageWording:
    """Tests for rephrased Node.js skip message in main()."""

    @patch('platform.system', return_value='Linux')
    @patch('install_claude.ensure_claude', return_value=True)
    def test_auto_mode_shows_native_first_message(self, mock_claude, mock_system, capsys):
        """Test auto mode shows 'native installer will be tried first' message."""
        assert mock_claude.return_value is True
        assert mock_system.return_value == 'Linux'
        with patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'auto'}, clear=False), \
                patch('sys.exit'):
            install_claude.main()
        captured = capsys.readouterr()
        assert 'Skipping Node.js pre-installation (native installer will be tried first)' in captured.out

    @patch('platform.system', return_value='Linux')
    @patch('install_claude.ensure_claude', return_value=True)
    def test_native_mode_shows_native_only_message(self, mock_claude, mock_system, capsys):
        """Test native mode shows 'native-only mode' message."""
        assert mock_claude.return_value is True
        assert mock_system.return_value == 'Linux'
        with patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'native'}, clear=False), \
                patch('sys.exit'):
            install_claude.main()
        captured = capsys.readouterr()
        assert 'Skipping Node.js installation (native-only mode)' in captured.out


class TestNpmFallbackConfigUpdate:
    """Tests for update_install_method_config('npm') after native->npm fallback."""

    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'auto'}, clear=False)
    @patch('install_claude.update_install_method_config')
    @patch('install_claude.install_claude_npm', return_value=True)
    @patch('install_claude.install_claude_native_cross_platform', return_value=False)
    @patch('install_claude.compare_versions', return_value=False)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.39')
    @patch('install_claude.get_claude_version')
    @patch('install_claude.verify_claude_installation')
    def test_native_upgrade_fallback_updates_config(
        self, mock_verify, mock_get_version, mock_latest, mock_compare,
        mock_native, mock_npm, mock_config,
    ):
        """Test that native upgrade fallback to npm calls update_install_method_config('npm')."""
        assert mock_latest.return_value == '2.1.39'
        assert mock_compare.return_value is False
        assert mock_native.return_value is False
        assert mock_npm.return_value is True
        mock_get_version.side_effect = ['2.0.76', '2.1.39']
        mock_verify.return_value = (True, '/home/user/.local/bin/claude', 'native')
        result = install_claude.ensure_claude()
        assert result is True
        mock_config.assert_called_with('npm')

    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'auto'}, clear=False)
    @patch('install_claude.update_install_method_config')
    @patch('install_claude.install_claude_npm', return_value=True)
    @patch('install_claude.install_claude_native_cross_platform', return_value=False)
    @patch('install_claude.compare_versions', return_value=False)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.39')
    @patch('install_claude.get_claude_version')
    @patch('install_claude.verify_claude_installation')
    def test_unknown_upgrade_fallback_updates_config(
        self, mock_verify, mock_get_version, mock_latest, mock_compare,
        mock_native, mock_npm, mock_config,
    ):
        """Test that unknown source upgrade fallback to npm calls update_install_method_config('npm')."""
        assert mock_latest.return_value == '2.1.39'
        assert mock_compare.return_value is False
        assert mock_native.return_value is False
        assert mock_npm.return_value is True
        mock_get_version.side_effect = ['2.0.76', '2.1.39']
        mock_verify.return_value = (True, '/opt/claude', 'unknown')
        result = install_claude.ensure_claude()
        assert result is True
        mock_config.assert_called_with('npm')


class TestClassifyLocalappdataClaude:
    """Tests for _classify_localappdata_claude() heuristic."""

    @patch('os.path.expandvars')
    @patch('pathlib.Path.exists', return_value=True)
    @patch('pathlib.Path.iterdir')
    def test_classify_returns_winget_when_winget_metadata_exists(
        self, mock_iterdir, mock_exists, mock_expandvars,
    ):
        """Returns 'winget' when WinGet Packages dir contains claude directory."""
        assert mock_exists.return_value is True
        mock_expandvars.side_effect = lambda x: x.replace(
            '%LOCALAPPDATA%', r'C:\Users\Test\AppData\Local',
        )
        claude_dir = MagicMock()
        claude_dir.name = 'Anthropic.Claude_1.2.3'
        claude_dir.is_dir.return_value = True
        mock_iterdir.return_value = [claude_dir]
        assert install_claude._classify_localappdata_claude() == 'winget'

    @patch('os.path.expandvars')
    @patch('pathlib.Path.exists', return_value=False)
    def test_classify_returns_native_when_no_winget_metadata(
        self, mock_exists, mock_expandvars,
    ):
        """Returns 'native' when WinGet Packages directory does not exist."""
        assert mock_exists.return_value is False
        mock_expandvars.side_effect = lambda x: x.replace(
            '%LOCALAPPDATA%', r'C:\Users\Test\AppData\Local',
        )
        assert install_claude._classify_localappdata_claude() == 'native'

    @patch('os.path.expandvars')
    @patch('pathlib.Path.exists', return_value=True)
    @patch('pathlib.Path.iterdir')
    def test_classify_returns_native_when_winget_dir_empty(
        self, mock_iterdir, mock_exists, mock_expandvars,
    ):
        """Returns 'native' when WinGet Packages dir exists but has no claude entries."""
        assert mock_exists.return_value is True
        mock_expandvars.side_effect = lambda x: x.replace(
            '%LOCALAPPDATA%', r'C:\Users\Test\AppData\Local',
        )
        other_pkg = MagicMock()
        other_pkg.name = 'SomeOtherPackage'
        other_pkg.is_dir.return_value = True
        mock_iterdir.return_value = [other_pkg]
        assert install_claude._classify_localappdata_claude() == 'native'

    @patch('os.path.expandvars')
    @patch('pathlib.Path.exists', return_value=True)
    @patch('pathlib.Path.iterdir', side_effect=OSError('Access denied'))
    def test_classify_returns_native_on_oserror(
        self, mock_iterdir, mock_exists, mock_expandvars,
    ):
        """Returns 'native' when iterdir raises OSError."""
        assert mock_iterdir.side_effect is not None
        assert mock_exists.return_value is True
        mock_expandvars.side_effect = lambda x: x.replace(
            '%LOCALAPPDATA%', r'C:\Users\Test\AppData\Local',
        )
        assert install_claude._classify_localappdata_claude() == 'native'

    @patch('sys.platform', 'win32')
    @patch('install_claude._classify_localappdata_claude', return_value='winget')
    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.stat')
    @patch('os.path.expandvars')
    def test_verify_claude_installation_programs_path_uses_classifier_winget(
        self, mock_expandvars, mock_stat, mock_exists, mock_classify,
    ):
        """verify_claude_installation() delegates to _classify_localappdata_claude for programs path."""
        mock_exists.side_effect = [
            False,  # native_path.exists() -> False
            False,  # npm_cmd_path.exists() -> False
            False,  # npm_path.exists() -> False
            True,   # programs_path.exists() -> True
        ]
        mock_stat.return_value.st_size = 5000000
        mock_expandvars.side_effect = lambda x: x.replace(
            '%LOCALAPPDATA%', r'C:\Users\Test\AppData\Local',
        ).replace('%APPDATA%', r'C:\Users\Test\AppData\Roaming')
        is_installed, path, source = install_claude.verify_claude_installation()
        assert is_installed is True
        assert source == 'winget'
        mock_classify.assert_called_once()

    @patch('sys.platform', 'win32')
    @patch('install_claude._classify_localappdata_claude', return_value='native')
    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.stat')
    @patch('os.path.expandvars')
    def test_verify_claude_installation_programs_path_uses_classifier_native(
        self, mock_expandvars, mock_stat, mock_exists, mock_classify,
    ):
        """verify_claude_installation() classifies programs path as native when no winget metadata."""
        mock_exists.side_effect = [
            False,  # native_path.exists() -> False
            False,  # npm_cmd_path.exists() -> False
            False,  # npm_path.exists() -> False
            True,   # programs_path.exists() -> True
        ]
        mock_stat.return_value.st_size = 5000000
        mock_expandvars.side_effect = lambda x: x.replace(
            '%LOCALAPPDATA%', r'C:\Users\Test\AppData\Local',
        ).replace('%APPDATA%', r'C:\Users\Test\AppData\Roaming')
        is_installed, path, source = install_claude.verify_claude_installation()
        assert is_installed is True
        assert source == 'native'
        mock_classify.assert_called_once()

    @patch('sys.platform', 'win32')
    @patch('install_claude._classify_localappdata_claude', return_value='winget')
    @patch('pathlib.Path.exists', return_value=False)
    @patch('install_claude.find_command')
    def test_verify_claude_installation_path_fallback_uses_classifier(
        self, mock_find, mock_exists, mock_classify,
    ):
        """PATH fallback also delegates to _classify_localappdata_claude."""
        assert mock_exists.return_value is False
        mock_find.return_value = r'C:\Users\Test\AppData\Local\Programs\claude\claude.exe'
        is_installed, path, source = install_claude.verify_claude_installation()
        assert is_installed is True
        assert source == 'winget'
        mock_classify.assert_called_once()


class TestWarnMigrationFailed:
    """Tests for _warn_migration_failed() boxed warning."""

    def test_warn_migration_failed_produces_output(self, capsys):
        """Verify boxed warning with expected content."""
        install_claude._warn_migration_failed('/usr/lib/node_modules/.bin/claude')
        captured = capsys.readouterr()
        assert '=' * 70 in captured.out
        assert 'WARNING' in captured.out
        assert 'Migration' in captured.out
        assert 'FAILED' in captured.out
        assert '/usr/lib/node_modules/.bin/claude' in captured.out
        assert 'still functional via npm' in captured.out

    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'auto'}, clear=False)
    @patch('install_claude._warn_migration_failed')
    @patch('install_claude.update_install_method_config')
    @patch('install_claude.install_claude_native_cross_platform', return_value=False)
    @patch('install_claude.get_claude_version', return_value='2.1.0')
    @patch('install_claude.verify_claude_installation')
    @patch('install_claude.get_latest_claude_version', return_value='2.1.0')
    @patch('install_claude.compare_versions', return_value=True)
    def test_warn_migration_failed_called_on_failure(
        self, mock_compare, mock_latest, mock_verify,
        mock_get_version, mock_native, mock_config, mock_warn,
    ):
        """_warn_migration_failed is called when migration fails."""
        assert mock_compare.return_value is True
        assert mock_latest.return_value == '2.1.0'
        assert mock_get_version.return_value == '2.1.0'
        assert mock_native.return_value is False
        assert mock_config is not None
        npm_path = '/usr/lib/node_modules/.bin/claude'
        mock_verify.return_value = (True, npm_path, 'npm')
        result = install_claude.ensure_claude()
        assert result is True
        mock_warn.assert_called_once_with(npm_path or '')


class TestMigrationFailureInstallMethodReset:
    """Tests for update_install_method_config('npm') on migration failure."""

    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'auto'}, clear=False)
    @patch('install_claude.update_install_method_config')
    @patch('install_claude._warn_migration_failed')
    @patch('install_claude.install_claude_native_cross_platform', return_value=False)
    @patch('install_claude.get_claude_version', return_value='2.1.0')
    @patch('install_claude.verify_claude_installation')
    @patch('install_claude.get_latest_claude_version', return_value='2.1.0')
    @patch('install_claude.compare_versions', return_value=True)
    def test_migration_failure_resets_install_method_no_version_pin(
        self, mock_compare, mock_latest, mock_verify,
        mock_get_version, mock_native, mock_warn, mock_config,
    ):
        """Migration failure without version pin resets installMethod to npm."""
        assert mock_compare.return_value is True
        assert mock_latest.return_value == '2.1.0'
        assert mock_get_version.return_value == '2.1.0'
        assert mock_native.return_value is False
        assert mock_warn is not None
        mock_verify.return_value = (True, '/usr/lib/node_modules/.bin/claude', 'npm')
        result = install_claude.ensure_claude()
        assert result is True
        mock_config.assert_called_with('npm')

    @patch.dict('os.environ', {
        'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'auto',
        'CLAUDE_CODE_TOOLBOX_VERSION': '2.1.0',
    }, clear=False)
    @patch('install_claude.update_install_method_config')
    @patch('install_claude._warn_migration_failed')
    @patch('install_claude.install_claude_native_cross_platform', return_value=False)
    @patch('install_claude.get_claude_version', return_value='2.1.0')
    @patch('install_claude.verify_claude_installation')
    def test_migration_failure_resets_install_method_version_pinned(
        self, mock_verify, mock_get_version,
        mock_native, mock_warn, mock_config,
    ):
        """Migration failure with version pin resets installMethod to npm."""
        assert mock_get_version.return_value == '2.1.0'
        assert mock_native.return_value is False
        assert mock_warn is not None
        mock_verify.return_value = (True, '/usr/lib/node_modules/.bin/claude', 'npm')
        result = install_claude.ensure_claude()
        assert result is True
        mock_config.assert_called_with('npm')

    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'auto'}, clear=False)
    @patch('install_claude.update_install_method_config')
    @patch('install_claude._warn_migration_failed')
    @patch('install_claude.install_claude_native_cross_platform', return_value=True)
    @patch('install_claude.get_claude_version', return_value='2.1.0')
    @patch('install_claude.verify_claude_installation')
    @patch('install_claude.get_latest_claude_version', return_value='2.1.0')
    @patch('install_claude.compare_versions', return_value=True)
    def test_migration_not_detected_resets_install_method(
        self, mock_compare, mock_latest, mock_verify,
        mock_get_version, mock_native, mock_warn, mock_config,
    ):
        """Migration succeeds but verify returns non-native resets installMethod to npm."""
        assert mock_compare.return_value is True
        assert mock_latest.return_value == '2.1.0'
        assert mock_get_version.return_value == '2.1.0'
        assert mock_native.return_value is True
        assert mock_warn is not None
        # First call: detect npm installation; second call: after native install, still npm
        mock_verify.side_effect = [
            (True, '/usr/lib/node_modules/.bin/claude', 'npm'),
            (True, '/usr/lib/node_modules/.bin/claude', 'npm'),
        ]
        result = install_claude.ensure_claude()
        assert result is True
        mock_config.assert_called_with('npm')

    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'auto'}, clear=False)
    @patch('install_claude.update_install_method_config')
    @patch('install_claude.remove_npm_claude', return_value=True)
    @patch('install_claude._check_npm_claude_installed', return_value=False)
    @patch('install_claude.install_claude_native_cross_platform', return_value=True)
    @patch('install_claude.get_claude_version')
    @patch('install_claude.verify_claude_installation')
    @patch('install_claude.get_latest_claude_version', return_value='2.1.0')
    @patch('install_claude.compare_versions', return_value=True)
    def test_successful_migration_sets_native_not_npm(
        self, mock_compare, mock_latest, mock_verify,
        mock_get_version, mock_native, mock_npm_check, mock_remove, mock_config,
    ):
        """Successful migration sets installMethod to native, not npm."""
        assert mock_compare.return_value is True
        assert mock_latest.return_value == '2.1.0'
        assert mock_native.return_value is True
        assert mock_npm_check.return_value is False
        assert mock_remove.return_value is True
        mock_get_version.return_value = '2.1.0'
        mock_verify.side_effect = [
            (True, '/usr/lib/node_modules/.bin/claude', 'npm'),
            (True, '/home/user/.local/bin/claude', 'native'),
        ]
        result = install_claude.ensure_claude()
        assert result is True
        mock_config.assert_called_with('native')


class TestNativeInstallerRecoveryChain:
    """Tests for the recovery chain in _install_claude_native_windows_installer()."""

    @pytest.fixture
    def base_mocks(self):
        """Common mocks for recovery chain tests."""
        with patch('install_claude.run_command') as mock_run, \
                patch('install_claude.urlopen') as mock_urlopen, \
                patch('install_claude.ensure_local_bin_in_path_windows'), \
                patch('install_claude.remove_npm_claude', return_value=True), \
                patch('install_claude._check_npm_claude_installed', return_value=False), \
                patch('install_claude.update_install_method_config') as mock_config, \
                patch('install_claude._warn_npm_removal_failed'), \
                patch('tempfile.NamedTemporaryFile') as mock_tmp, \
                patch('os.unlink'):
            # Set up basic installer success
            mock_response = MagicMock()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_response.read.return_value = b'# installer script'
            mock_urlopen.return_value = mock_response
            mock_tmp_file = MagicMock()
            mock_tmp_file.__enter__ = MagicMock(return_value=mock_tmp_file)
            mock_tmp_file.__exit__ = MagicMock(return_value=False)
            mock_tmp_file.name = 'C:\\temp\\installer.ps1'
            mock_tmp.return_value = mock_tmp_file
            mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')
            yield {
                'config': mock_config,
            }

    @patch('time.sleep')
    @patch('install_claude.verify_claude_installation')
    def test_recovery_retry_succeeds_on_second_attempt(
        self, mock_verify, mock_sleep, base_mocks,
    ):
        """Recovery retries succeed on second attempt after filesystem sync delay."""
        assert mock_sleep is not None
        native_path = r'C:\Users\Test\.local\bin\claude.exe'
        # Initial verify: found but npm, retry 1: still npm, retry 2: native
        mock_verify.side_effect = [
            (True, r'C:\Users\Test\AppData\Roaming\npm\claude.cmd', 'npm'),
            (True, r'C:\Users\Test\AppData\Roaming\npm\claude.cmd', 'npm'),
            (True, native_path, 'native'),
        ]
        result = install_claude._install_claude_native_windows_installer()
        assert result is True
        base_mocks['config'].assert_called_with('native')

    @patch('time.sleep')
    @patch('shutil.copy2')
    @patch('pathlib.Path.mkdir')
    @patch('pathlib.Path.stat')
    @patch('pathlib.Path.exists')
    @patch('install_claude.verify_claude_installation')
    @patch('os.path.expandvars')
    def test_recovery_alternative_path_succeeds(
        self, mock_expandvars, mock_verify, mock_exists_path,
        mock_stat, mock_mkdir, mock_copy, mock_sleep, base_mocks,
    ):
        """Recovery finds binary at alternative path and copies to expected location."""
        assert mock_mkdir is not None
        assert mock_sleep is not None
        native_path = r'C:\Users\Test\.local\bin\claude.exe'
        mock_expandvars.side_effect = lambda x: x.replace(
            '%LOCALAPPDATA%', r'C:\Users\Test\AppData\Local',
        )
        # Initial verify: not found; 3 retries: not found; alt path exists
        mock_verify.side_effect = [
            (False, None, 'none'),
            (False, None, 'none'),
            (False, None, 'none'),
            (False, None, 'none'),
            (True, native_path, 'native'),  # after copy
        ]
        # alt_paths[0].exists() -> True, alt_paths[0].stat().st_size > 1000
        mock_exists_path.side_effect = [True]
        mock_stat.return_value.st_size = 5000000
        result = install_claude._install_claude_native_windows_installer()
        assert result is True
        mock_copy.assert_called_once()
        base_mocks['config'].assert_called_with('native')

    @patch('time.sleep')
    @patch('pathlib.Path.exists', return_value=False)
    @patch('install_claude._download_claude_direct_from_gcs', return_value=True)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.0')
    @patch('install_claude.verify_claude_installation')
    def test_recovery_gcs_fallback_succeeds(
        self, mock_verify, mock_latest, mock_gcs, mock_exists, mock_sleep, base_mocks,
    ):
        """Recovery GCS download fallback succeeds when all other methods fail."""
        assert mock_latest.return_value == '2.1.0'
        assert mock_exists.return_value is False
        assert mock_sleep is not None
        native_path = r'C:\Users\Test\.local\bin\claude.exe'
        # Initial: not found; 3 retries: not found; no alt paths; GCS succeeds
        mock_verify.side_effect = [
            (False, None, 'none'),
            (False, None, 'none'),
            (False, None, 'none'),
            (False, None, 'none'),
            (True, native_path, 'native'),  # after GCS download
        ]
        result = install_claude._install_claude_native_windows_installer()
        assert result is True
        mock_gcs.assert_called_once()
        base_mocks['config'].assert_called_with('native')

    @patch('time.sleep')
    @patch('pathlib.Path.exists', return_value=False)
    @patch('install_claude._download_claude_direct_from_gcs', return_value=False)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.0')
    @patch('install_claude.verify_claude_installation')
    def test_recovery_all_steps_fail(
        self, mock_verify, mock_latest, mock_gcs, mock_exists, mock_sleep, base_mocks,
    ):
        """Returns False when all recovery steps fail."""
        assert mock_latest.return_value == '2.1.0'
        assert mock_gcs.return_value is False
        assert mock_exists.return_value is False
        assert mock_sleep is not None
        assert base_mocks is not None
        mock_verify.return_value = (False, None, 'none')
        result = install_claude._install_claude_native_windows_installer()
        assert result is False

    @patch('time.sleep')
    @patch('install_claude.verify_claude_installation')
    def test_recovery_not_triggered_when_native_verified(
        self, mock_verify, mock_sleep, base_mocks,
    ):
        """No recovery when initial verification succeeds as native."""
        assert base_mocks is not None
        native_path = r'C:\Users\Test\.local\bin\claude.exe'
        mock_verify.return_value = (True, native_path, 'native')
        result = install_claude._install_claude_native_windows_installer()
        assert result is True
        # Only the initial 1-second sleep for PATH update, no 2-second recovery sleeps
        sleep_calls = [c.args[0] for c in mock_sleep.call_args_list]
        assert 2 not in sleep_calls


class TestInstallClaudeWinget:
    """Tests for _install_claude_winget() function."""

    WINGET_PATH = r'C:\Users\Test\AppData\Local\Programs\claude\claude.exe'

    @patch('install_claude.update_install_method_config')
    @patch('install_claude.verify_claude_installation')
    @patch('install_claude.run_command')
    @patch('install_claude.check_winget', return_value=True)
    def test_success_latest(self, mock_winget, mock_run, mock_verify, mock_config):
        """Winget installs latest version successfully."""
        assert mock_winget.return_value is True
        mock_verify.return_value = (True, self.WINGET_PATH, 'winget')
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')
        result = install_claude._install_claude_winget()
        assert result is True
        mock_config.assert_called_once_with('winget')
        # Verify correct winget command args
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == 'winget'
        assert call_args[1] == 'install'
        assert '--id' in call_args
        assert 'Anthropic.ClaudeCode' in call_args
        assert '--version' not in call_args

    @patch('install_claude.check_winget', return_value=False)
    def test_no_winget(self, mock_winget):
        """Returns False when winget is not available."""
        assert mock_winget.return_value is False
        result = install_claude._install_claude_winget()
        assert result is False

    @patch('install_claude.update_install_method_config')
    @patch('install_claude.verify_claude_installation')
    @patch('install_claude.run_command')
    @patch('install_claude.check_winget', return_value=True)
    def test_with_version(self, mock_winget, mock_run, mock_verify, mock_config):
        """Winget installs specific version with --version flag."""
        assert mock_winget.return_value is True
        assert mock_verify is not None
        assert mock_config is not None
        mock_verify.return_value = (True, self.WINGET_PATH, 'winget')
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')
        result = install_claude._install_claude_winget(version='2.0.76')
        assert result is True
        call_args = mock_run.call_args[0][0]
        assert '--version' in call_args
        version_idx = call_args.index('--version')
        assert call_args[version_idx + 1] == '2.0.76'

    @patch('install_claude.update_install_method_config')
    @patch('install_claude.verify_claude_installation')
    @patch('install_claude.run_command')
    @patch('install_claude.check_winget', return_value=True)
    def test_already_installed_exit_code(self, mock_winget, mock_run, mock_verify, mock_config):
        """Exit code -1978335189 treated as success (already installed)."""
        assert mock_winget.return_value is True
        mock_verify.return_value = (True, self.WINGET_PATH, 'winget')
        mock_run.return_value = MagicMock(returncode=-1978335189, stdout='', stderr='')
        result = install_claude._install_claude_winget()
        assert result is True
        mock_config.assert_called_once_with('winget')

    @patch('install_claude.run_command')
    @patch('install_claude.check_winget', return_value=True)
    def test_failure(self, mock_winget, mock_run):
        """Non-zero exit code returns False."""
        assert mock_winget.return_value is True
        mock_run.return_value = MagicMock(returncode=1, stdout='', stderr='some error')
        result = install_claude._install_claude_winget()
        assert result is False

    @patch('install_claude.update_install_method_config')
    @patch('install_claude.verify_claude_installation')
    @patch('install_claude.run_command')
    @patch('install_claude.check_winget', return_value=True)
    def test_no_remove_npm(self, mock_winget, mock_run, mock_verify, mock_config):
        """Verify remove_npm_claude() is NOT called by _install_claude_winget."""
        assert mock_winget.return_value is True
        assert mock_verify is not None
        assert mock_config is not None
        mock_verify.return_value = (True, self.WINGET_PATH, 'winget')
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')
        with patch('install_claude.remove_npm_claude') as mock_remove:
            install_claude._install_claude_winget()
            mock_remove.assert_not_called()

    @patch('install_claude.run_command')
    @patch('install_claude.check_winget', return_value=True)
    def test_manifest_lag_warning(self, mock_winget, mock_run):
        """Version-not-available produces lag-specific warning."""
        assert mock_winget.return_value is True
        mock_run.return_value = MagicMock(
            returncode=1, stdout='', stderr='No package found matching version 99.0.0',
        )
        result = install_claude._install_claude_winget(version='99.0.0')
        assert result is False

    @patch('install_claude.verify_claude_installation', return_value=(False, None, 'none'))
    @patch('install_claude.run_command')
    @patch('install_claude.check_winget', return_value=True)
    def test_success_but_verify_fails(self, mock_winget, mock_run, mock_verify):
        """Winget reports success but verification fails."""
        assert mock_winget.return_value is True
        assert mock_verify.return_value == (False, None, 'none')
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')
        result = install_claude._install_claude_winget()
        assert result is False

    @patch('install_claude.update_install_method_config')
    @patch('install_claude.verify_claude_installation')
    @patch('install_claude.run_command')
    @patch('install_claude.check_winget', return_value=True)
    def test_success_but_native_source_no_config_update(
        self, mock_winget, mock_run, mock_verify, mock_config,
    ):
        """Winget succeeds but native binary shadows -- no installMethod update."""
        assert mock_winget.return_value is True
        mock_verify.return_value = (True, r'C:\Users\test\.local\bin\claude.exe', 'native')
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')
        result = install_claude._install_claude_winget()
        assert result is True
        mock_config.assert_not_called()

    @patch('install_claude.update_install_method_config')
    @patch('install_claude.verify_claude_installation')
    @patch('install_claude.run_command')
    @patch('install_claude.check_winget', return_value=True)
    def test_success_unknown_source_no_config_update(
        self, mock_winget, mock_run, mock_verify, mock_config,
    ):
        """Winget succeeds but unknown source found -- no installMethod update."""
        assert mock_winget.return_value is True
        mock_verify.return_value = (True, r'C:\some\other\path\claude.exe', 'unknown')
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')
        result = install_claude._install_claude_winget()
        assert result is True
        mock_config.assert_not_called()


class TestInstallClaudeNativeWindowsGcsFallback:
    """Tests for GCS fallback in install_claude_native_windows()."""

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only test')
    @patch('install_claude._finalize_native_install')
    @patch(
        'install_claude.verify_claude_installation',
        return_value=(True, r'C:\Users\test\.local\bin\claude.exe', 'native'),
    )
    @patch('install_claude.ensure_local_bin_in_path_windows')
    @patch('install_claude.time.sleep')
    @patch('install_claude._download_claude_direct_from_gcs', return_value=True)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.98')
    @patch('install_claude._install_claude_native_windows_installer', return_value=False)
    @patch('install_claude._cleanup_old_claude_files')
    def test_latest_gcs_fallback_success(
        self, mock_cleanup, mock_native, mock_get_latest,
        mock_gcs, mock_sleep, mock_path, mock_verify, mock_finalize,
    ):
        """Native installer fails for latest, GCS direct download succeeds."""
        assert mock_cleanup is not None
        assert mock_sleep is not None
        result = install_claude.install_claude_native_windows()
        assert result is True
        mock_native.assert_called_once_with(version='latest')
        mock_get_latest.assert_called_once()
        mock_gcs.assert_called_once()
        mock_path.assert_called_once()
        mock_verify.assert_called()
        mock_finalize.assert_called_once()

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only test')
    @patch('install_claude._download_claude_direct_from_gcs', return_value=False)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.98')
    @patch('install_claude._install_claude_native_windows_installer', return_value=False)
    @patch('install_claude._cleanup_old_claude_files')
    def test_latest_gcs_fallback_fail(self, mock_cleanup, mock_native, mock_get_latest, mock_gcs):
        """Native installer and GCS both fail, returns False."""
        assert mock_cleanup is not None
        result = install_claude.install_claude_native_windows()
        assert result is False
        mock_native.assert_called_once_with(version='latest')
        mock_get_latest.assert_called_once()
        mock_gcs.assert_called_once()

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only test')
    @patch('install_claude.get_latest_claude_version', return_value=None)
    @patch('install_claude._install_claude_native_windows_installer', return_value=False)
    @patch('install_claude._cleanup_old_claude_files')
    def test_latest_gcs_version_unavailable(self, mock_cleanup, mock_native, mock_get_latest):
        """Native installer fails and latest version cannot be resolved."""
        assert mock_cleanup is not None
        result = install_claude.install_claude_native_windows()
        assert result is False
        mock_native.assert_called_once_with(version='latest')
        mock_get_latest.assert_called_once()

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only test')
    @patch('install_claude._install_claude_native_windows_installer', return_value=False)
    @patch('install_claude._install_claude_winget', return_value=True)
    @patch('install_claude._download_claude_direct_from_gcs', return_value=False)
    @patch('install_claude._cleanup_old_claude_files')
    def test_specific_gcs_fail_winget_success(self, mock_cleanup, mock_gcs, mock_winget, mock_native):
        """GCS fails for specific version, winget succeeds."""
        assert mock_cleanup is not None
        result = install_claude.install_claude_native_windows(version='2.0.76')
        assert result is True
        mock_gcs.assert_called_once()
        mock_winget.assert_called_once_with(version='2.0.76')
        # Native installer "latest" fallback should NOT be called (winget succeeded)
        mock_native.assert_not_called()


class TestInstallClaudeNativeMacosGcsFallback:
    """Tests for GCS fallback in install_claude_native_macos() for latest."""

    @pytest.mark.skipif(sys.platform != 'darwin', reason='macOS-only test')
    @patch('install_claude._finalize_native_install')
    @patch('install_claude.verify_claude_installation')
    @patch('time.sleep')
    @patch('install_claude._ensure_local_bin_in_path_unix')
    @patch('pathlib.Path.chmod')
    @patch('install_claude._download_claude_direct_from_gcs', return_value=True)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.0')
    @patch('install_claude._install_claude_native_macos_installer', return_value=False)
    def test_latest_gcs_fallback_success(
        self, mock_native, mock_latest, mock_gcs, mock_chmod, mock_path, mock_sleep,
        mock_verify, mock_finalize,
    ):
        """Native installer fails for latest, GCS fallback succeeds."""
        assert mock_latest.return_value == '2.1.0'
        assert mock_chmod is not None
        assert mock_path is not None
        assert mock_sleep is not None
        mock_verify.return_value = (True, '/Users/test/.local/bin/claude', 'native')
        result = install_claude.install_claude_native_macos()
        assert result is True
        mock_native.assert_called_once_with(version='latest')
        mock_gcs.assert_called_once()
        mock_finalize.assert_called_once()


class TestInstallClaudeNativeLinuxGcsFallback:
    """Tests for GCS fallback in install_claude_native_linux() for latest."""

    @pytest.mark.skipif(sys.platform == 'win32', reason='Not applicable on Windows')
    @patch('platform.system', return_value='Linux')
    @patch('install_claude._finalize_native_install')
    @patch('install_claude.verify_claude_installation')
    @patch('time.sleep')
    @patch('install_claude._ensure_local_bin_in_path_unix')
    @patch('pathlib.Path.chmod')
    @patch('install_claude._download_claude_direct_from_gcs', return_value=True)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.0')
    @patch('install_claude._install_claude_native_linux_installer', return_value=False)
    def test_latest_gcs_fallback_success(
        self, mock_native, mock_latest, mock_gcs, mock_chmod, mock_path, mock_sleep,
        mock_verify, mock_finalize, mock_platform,
    ):
        """Native installer fails for latest, GCS fallback succeeds."""
        assert mock_latest.return_value == '2.1.0'
        assert mock_chmod is not None
        assert mock_path is not None
        assert mock_sleep is not None
        assert mock_platform.return_value == 'Linux'
        mock_verify.return_value = (True, '/home/test/.local/bin/claude', 'native')
        result = install_claude.install_claude_native_linux()
        assert result is True
        mock_native.assert_called_once_with(version='latest')
        mock_gcs.assert_called_once()
        mock_finalize.assert_called_once()

    @pytest.mark.skipif(sys.platform == 'win32', reason='Not applicable on Windows')
    @patch('platform.system', return_value='Linux')
    @patch('install_claude._download_claude_direct_from_gcs', return_value=False)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.0')
    @patch('install_claude._install_claude_native_linux_installer', return_value=False)
    def test_latest_all_fallbacks_fail(self, mock_native, mock_latest, mock_gcs, mock_platform):
        """Both native installer and GCS fail for latest."""
        assert mock_native.return_value is False
        assert mock_platform.return_value == 'Linux'
        assert mock_latest.return_value == '2.1.0'
        assert mock_gcs.return_value is False
        result = install_claude.install_claude_native_linux()
        assert result is False


class TestEnsureClaudeWingetUpgrade:
    """Tests for winget-source upgrade routing in ensure_claude()."""

    @patch('install_claude._verify_upgrade_version', return_value=(True, '2.1.39'))
    @patch('install_claude.run_command')
    @patch('install_claude.update_install_method_config')
    @patch('install_claude.install_claude_npm')
    @patch('install_claude.compare_versions', return_value=False)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.39')
    @patch('install_claude.get_claude_version')
    @patch('install_claude.verify_claude_installation')
    def test_winget_source_tries_winget_upgrade(
        self, mock_verify, mock_get_version, mock_get_latest,
        mock_compare, mock_npm, mock_config, mock_run, mock_verify_upgrade,
    ):
        """Winget source tries winget upgrade before npm."""
        assert mock_get_latest.return_value == '2.1.39'
        assert mock_compare.return_value is False
        assert mock_config is not None
        mock_get_version.side_effect = ['2.0.76', '2.1.39']
        mock_verify.return_value = (
            True,
            r'C:\Users\Test\AppData\Local\Programs\claude\claude.exe',
            'winget',
        )
        # winget upgrade succeeds
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')

        result = install_claude.ensure_claude()
        assert result is True
        # npm should NOT be called
        mock_npm.assert_not_called()
        # winget upgrade command should have been called
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == 'winget'
        assert call_args[1] == 'upgrade'
        mock_verify_upgrade.assert_called()

    @patch('install_claude.run_command')
    @patch('install_claude.update_install_method_config')
    @patch('install_claude.install_claude_npm', return_value=True)
    @patch('install_claude.compare_versions', return_value=False)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.39')
    @patch('install_claude.get_claude_version')
    @patch('install_claude.verify_claude_installation')
    def test_winget_upgrade_fails_npm_fallback(
        self, mock_verify, mock_get_version, mock_get_latest,
        mock_compare, mock_npm, mock_config, mock_run,
    ):
        """Winget upgrade fails, falls back to npm."""
        assert mock_get_latest.return_value == '2.1.39'
        assert mock_compare.return_value is False
        mock_get_version.side_effect = ['2.0.76', '2.1.39']
        mock_verify.return_value = (
            True,
            r'C:\Users\Test\AppData\Local\Programs\claude\claude.exe',
            'winget',
        )
        # winget upgrade fails
        mock_run.return_value = MagicMock(returncode=1, stdout='', stderr='')

        result = install_claude.ensure_claude()
        assert result is True
        # npm should be called as fallback
        mock_npm.assert_called_once()
        mock_config.assert_called_with('npm')


class TestFinalizeNativeInstallMethodParam:
    """Tests for _finalize_native_install() method parameter (Step 12 refactoring)."""

    @patch('install_claude.update_install_method_config')
    @patch('install_claude.remove_npm_claude', return_value=True)
    def test_default_method(self, mock_remove, mock_config):
        """Default method parameter is 'native'."""
        assert mock_remove.return_value is True
        install_claude._finalize_native_install()
        mock_config.assert_called_once_with('native')

    @patch('install_claude.update_install_method_config')
    @patch('install_claude.remove_npm_claude', return_value=True)
    def test_custom_method(self, mock_remove, mock_config):
        """Custom method parameter is passed to update_install_method_config."""
        assert mock_remove.return_value is True
        install_claude._finalize_native_install(method='winget')
        mock_config.assert_called_once_with('winget')

    @patch('install_claude.update_install_method_config')
    @patch('install_claude._check_npm_claude_installed', return_value=True)
    @patch('install_claude.remove_npm_claude', return_value=False)
    def test_custom_method_with_npm_check(self, mock_remove, mock_check, mock_config):
        """Custom method works even when npm removal fails."""
        assert mock_remove.return_value is False
        install_claude._finalize_native_install(method='custom')
        mock_check.assert_called_once()
        mock_config.assert_called_once_with('custom')


class TestVerifyUpgradeVersion:
    """Tests for _verify_upgrade_version() post-upgrade version check."""

    @patch('install_claude.get_claude_version', return_value='2.1.92')
    @patch('install_claude.compare_versions', return_value=True)
    def test_version_matches(self, mock_compare, mock_get_version):
        """Returns (True, actual_version) when version >= expected."""
        assert mock_get_version.return_value  # Ensure mock is active
        result = install_claude._verify_upgrade_version('2.1.92', 'native installer')
        assert result == (True, '2.1.92')
        mock_compare.assert_called_once_with('2.1.92', '2.1.92')

    @patch('install_claude.get_claude_version', return_value='2.1.89')
    @patch('install_claude.compare_versions', return_value=False)
    def test_version_mismatch(self, mock_compare, mock_get_version):
        """Returns (False, actual_version) when version < expected."""
        assert mock_get_version.return_value  # Ensure mock is active
        result = install_claude._verify_upgrade_version('2.1.92', 'native installer')
        assert result == (False, '2.1.89')
        mock_compare.assert_called_once_with('2.1.89', '2.1.92')

    @patch('install_claude.get_claude_version', return_value=None)
    def test_version_undetectable(self, mock_get_version):
        """Returns (False, None) when version cannot be detected."""
        mock_get_version.assert_not_called()  # Not called yet
        result = install_claude._verify_upgrade_version('2.1.92', 'native installer')
        assert result == (False, None)
        mock_get_version.assert_called_once()

    @patch('install_claude.get_claude_version', return_value='2.1.93')
    @patch('install_claude.compare_versions', return_value=True)
    def test_newer_version_accepted(self, mock_compare, mock_get_version):
        """Accepts a version newer than expected (race condition handling)."""
        assert mock_get_version.return_value  # Ensure mock is active
        result = install_claude._verify_upgrade_version('2.1.92', 'native installer')
        assert result == (True, '2.1.93')
        mock_compare.assert_called_once_with('2.1.93', '2.1.92')

    @patch('install_claude.get_claude_version', return_value='2.1.89')
    @patch('install_claude.compare_versions', return_value=False)
    def test_method_label_in_warning(self, mock_compare, mock_get_version, capsys):
        """Method label appears in the warning message."""
        assert mock_get_version.return_value  # Ensure mock is active
        install_claude._verify_upgrade_version('2.1.92', 'winget')
        captured = capsys.readouterr()
        assert 'winget' in captured.out
        mock_compare.assert_called_once()


class TestRecoverFromVersionsDirectory:
    """Tests for _recover_from_versions_directory() cache promotion."""

    def test_binary_not_found(self, tmp_path, monkeypatch):
        """Returns None when versions directory does not exist."""
        monkeypatch.setattr('install_claude.get_real_user_home', lambda: tmp_path)
        result = install_claude._recover_from_versions_directory('2.1.92')
        assert result is None

    def test_binary_too_small(self, tmp_path, monkeypatch):
        """Returns None when cached binary is too small (corrupt)."""
        monkeypatch.setattr('install_claude.get_real_user_home', lambda: tmp_path)
        versions_dir = tmp_path / '.local' / 'share' / 'claude' / 'versions' / '2.1.92'
        versions_dir.mkdir(parents=True)
        binary_name = 'claude.exe' if sys.platform == 'win32' else 'claude'
        (versions_dir / binary_name).write_bytes(b'x' * 500)
        result = install_claude._recover_from_versions_directory('2.1.92')
        assert result is None

    @patch('install_claude.get_claude_version', return_value='2.1.92')
    @patch('install_claude.compare_versions', return_value=True)
    def test_successful_promotion(self, mock_compare, mock_get_version, tmp_path, monkeypatch):
        """Promotes cached binary and returns version string."""
        monkeypatch.setattr('install_claude.get_real_user_home', lambda: tmp_path)
        versions_dir = tmp_path / '.local' / 'share' / 'claude' / 'versions' / '2.1.92'
        versions_dir.mkdir(parents=True)
        binary_name = 'claude.exe' if sys.platform == 'win32' else 'claude'
        (versions_dir / binary_name).write_bytes(b'x' * 2000)
        (tmp_path / '.local' / 'bin').mkdir(parents=True, exist_ok=True)
        result = install_claude._recover_from_versions_directory('2.1.92')
        assert result == '2.1.92'
        assert (tmp_path / '.local' / 'bin' / binary_name).exists()
        mock_get_version.assert_called_once()
        mock_compare.assert_called_once()

    def test_different_version_not_promoted(self, tmp_path, monkeypatch):
        """Only promotes exact target_version, not other versions in cache."""
        monkeypatch.setattr('install_claude.get_real_user_home', lambda: tmp_path)
        # Create version 2.1.91 but request 2.1.92
        versions_dir = tmp_path / '.local' / 'share' / 'claude' / 'versions' / '2.1.91'
        versions_dir.mkdir(parents=True)
        binary_name = 'claude.exe' if sys.platform == 'win32' else 'claude'
        (versions_dir / binary_name).write_bytes(b'x' * 2000)
        result = install_claude._recover_from_versions_directory('2.1.92')
        assert result is None

    @patch('install_claude.get_claude_version', return_value='2.1.90')
    @patch('install_claude.compare_versions', return_value=False)
    def test_promoted_binary_version_mismatch(
        self, mock_compare, mock_get_version, tmp_path, monkeypatch,
    ):
        """Returns None when promoted binary reports wrong version."""
        monkeypatch.setattr('install_claude.get_real_user_home', lambda: tmp_path)
        versions_dir = tmp_path / '.local' / 'share' / 'claude' / 'versions' / '2.1.92'
        versions_dir.mkdir(parents=True)
        binary_name = 'claude.exe' if sys.platform == 'win32' else 'claude'
        (versions_dir / binary_name).write_bytes(b'x' * 2000)
        (tmp_path / '.local' / 'bin').mkdir(parents=True, exist_ok=True)
        result = install_claude._recover_from_versions_directory('2.1.92')
        assert result is None
        mock_get_version.assert_called_once()
        mock_compare.assert_called_once()

    def test_creates_target_directory(self, tmp_path, monkeypatch):
        """Creates ~/.local/bin/ if it does not exist."""
        monkeypatch.setattr('install_claude.get_real_user_home', lambda: tmp_path)
        monkeypatch.setattr(
            'install_claude.get_claude_version', lambda *_args: '2.1.92',
        )
        monkeypatch.setattr(
            'install_claude.compare_versions', lambda *_args: True,
        )
        versions_dir = tmp_path / '.local' / 'share' / 'claude' / 'versions' / '2.1.92'
        versions_dir.mkdir(parents=True)
        binary_name = 'claude.exe' if sys.platform == 'win32' else 'claude'
        (versions_dir / binary_name).write_bytes(b'x' * 2000)
        # Do NOT create .local/bin -- function should create it
        assert not (tmp_path / '.local' / 'bin').exists()
        result = install_claude._recover_from_versions_directory('2.1.92')
        assert result == '2.1.92'
        assert (tmp_path / '.local' / 'bin').exists()

    def test_oserror_on_copy(self, tmp_path, monkeypatch):
        """Returns None on general OSError during copy."""
        monkeypatch.setattr('install_claude.get_real_user_home', lambda: tmp_path)
        versions_dir = tmp_path / '.local' / 'share' / 'claude' / 'versions' / '2.1.92'
        versions_dir.mkdir(parents=True)
        binary_name = 'claude.exe' if sys.platform == 'win32' else 'claude'
        (versions_dir / binary_name).write_bytes(b'x' * 2000)
        (tmp_path / '.local' / 'bin').mkdir(parents=True, exist_ok=True)
        with patch('shutil.copy2', side_effect=OSError('disk full')):
            result = install_claude._recover_from_versions_directory('2.1.92')
        assert result is None

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only test')
    def test_windows_permission_error_delegates_to_file_lock(self, tmp_path, monkeypatch):
        """On Windows PermissionError, copies to temp then delegates to file lock handler."""
        monkeypatch.setattr('install_claude.get_real_user_home', lambda: tmp_path)
        versions_dir = tmp_path / '.local' / 'share' / 'claude' / 'versions' / '2.1.92'
        versions_dir.mkdir(parents=True)
        (versions_dir / 'claude.exe').write_bytes(b'x' * 2000)
        (tmp_path / '.local' / 'bin').mkdir(parents=True, exist_ok=True)
        # First copy2 call raises PermissionError (to target); second succeeds (to temp)
        copy_calls = []

        def mock_copy2(src, dst):  # noqa: ARG001
            copy_calls.append(dst)
            if len(copy_calls) == 1:
                raise PermissionError('Access is denied')
            # Second call (to .tmp) succeeds -- create the file
            Path(dst).write_bytes(b'x' * 2000)

        with (
            patch('shutil.copy2', side_effect=mock_copy2),
            patch(
                'install_claude._handle_windows_file_lock', return_value=True,
            ) as mock_file_lock,
        ):
            result = install_claude._recover_from_versions_directory('2.1.92')
        assert result == '2.1.92'
        mock_file_lock.assert_called_once()

    @pytest.mark.skipif(sys.platform == 'win32', reason='Unix-only test')
    def test_unix_permission_error_returns_none(self, tmp_path, monkeypatch):
        """On Unix PermissionError, returns None without file lock handling."""
        monkeypatch.setattr('install_claude.get_real_user_home', lambda: tmp_path)
        versions_dir = tmp_path / '.local' / 'share' / 'claude' / 'versions' / '2.1.92'
        versions_dir.mkdir(parents=True)
        binary_name = 'claude'
        (versions_dir / binary_name).write_bytes(b'x' * 2000)
        (tmp_path / '.local' / 'bin').mkdir(parents=True, exist_ok=True)
        with patch('shutil.copy2', side_effect=PermissionError('Permission denied')):
            result = install_claude._recover_from_versions_directory('2.1.92')
        assert result is None


class TestUpgradeVersionVerification:
    """Tests for post-upgrade version verification in ensure_claude() upgrade branches."""

    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'auto'}, clear=False)
    @patch('install_claude.update_install_method_config')
    @patch('install_claude._recover_from_versions_directory', return_value='2.1.92')
    @patch('install_claude._verify_upgrade_version', return_value=(False, '2.1.89'))
    @patch('install_claude.install_claude_native_cross_platform', return_value=True)
    @patch('install_claude.compare_versions', return_value=False)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.92')
    @patch('install_claude.get_claude_version', return_value='2.1.89')
    @patch('install_claude.verify_claude_installation')
    def test_native_source_mismatch_recovers_from_versions_dir(
        self, mock_verify, mock_get_version, mock_get_latest, mock_compare,
        mock_native, mock_verify_upgrade, mock_recover, mock_config,
    ):
        """When native upgrade has version mismatch, Tier 1 recovery from versions dir."""
        mock_verify.return_value = (True, '/home/user/.local/bin/claude', 'native')
        result = install_claude.ensure_claude()
        assert result is True
        mock_recover.assert_called_once_with('2.1.92')
        mock_config.assert_called_with('native')
        assert mock_get_version.return_value == '2.1.89'
        assert mock_get_latest.return_value == '2.1.92'
        assert mock_compare.return_value is False
        mock_native.assert_called()
        mock_verify_upgrade.assert_called()

    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'auto'}, clear=False)
    @patch('install_claude.update_install_method_config')
    @patch('install_claude._download_claude_direct_from_gcs', return_value=True)
    @patch('install_claude._recover_from_versions_directory', return_value=None)
    @patch('install_claude._verify_upgrade_version', return_value=(False, '2.1.89'))
    @patch('install_claude.install_claude_native_cross_platform', return_value=True)
    @patch('install_claude.compare_versions', return_value=False)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.92')
    @patch('install_claude.get_claude_version')
    @patch('install_claude.verify_claude_installation')
    def test_native_source_mismatch_gcs_fallback(
        self, mock_verify, mock_get_version, mock_get_latest, mock_compare,
        mock_native, mock_verify_upgrade, mock_recover, mock_gcs, mock_config,
    ):
        """When versions dir recovery fails, Tier 2 GCS download."""
        mock_get_version.return_value = '2.1.89'
        mock_verify.return_value = (True, '/home/user/.local/bin/claude', 'native')
        result = install_claude.ensure_claude()
        assert result is True
        mock_recover.assert_called_once()
        mock_gcs.assert_called_once()
        mock_config.assert_called_with('native')
        assert mock_get_latest.return_value == '2.1.92'
        assert mock_compare.return_value is False
        mock_native.assert_called()
        mock_verify_upgrade.assert_called()

    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'auto'}, clear=False)
    @patch('install_claude.update_install_method_config')
    @patch('install_claude.install_claude_npm', return_value=True)
    @patch('install_claude._download_claude_direct_from_gcs', return_value=False)
    @patch('install_claude._recover_from_versions_directory', return_value=None)
    @patch('install_claude._verify_upgrade_version', return_value=(False, '2.1.89'))
    @patch('install_claude.install_claude_native_cross_platform', return_value=True)
    @patch('install_claude.compare_versions', return_value=False)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.92')
    @patch('install_claude.get_claude_version')
    @patch('install_claude.verify_claude_installation')
    def test_native_source_mismatch_npm_last_resort(
        self, mock_verify, mock_get_version, mock_get_latest, mock_compare,
        mock_native, mock_verify_upgrade, mock_recover, mock_gcs, mock_npm,
        mock_update_config,
    ):
        """When GCS also fails, Tier 3 npm fallback in auto mode."""
        mock_get_version.return_value = '2.1.89'
        mock_verify.return_value = (True, '/home/user/.local/bin/claude', 'native')
        result = install_claude.ensure_claude()
        assert result is True
        mock_npm.assert_called_once()
        mock_update_config.assert_called_with('npm')
        assert mock_get_latest.return_value == '2.1.92'
        assert mock_compare.return_value is False
        mock_native.assert_called()
        mock_verify_upgrade.assert_called()
        mock_recover.assert_called_once()
        mock_gcs.assert_called_once()

    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'native'}, clear=False)
    @patch('install_claude.install_claude_npm')
    @patch('install_claude._download_claude_direct_from_gcs', return_value=False)
    @patch('install_claude._recover_from_versions_directory', return_value=None)
    @patch('install_claude._verify_upgrade_version', return_value=(False, '2.1.89'))
    @patch('install_claude.install_claude_native_cross_platform', return_value=True)
    @patch('install_claude.compare_versions', return_value=False)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.92')
    @patch('install_claude.get_claude_version', return_value='2.1.89')
    @patch('install_claude.verify_claude_installation')
    def test_native_mode_no_npm_in_recovery(
        self, mock_verify, mock_get_version, mock_get_latest, mock_compare,
        mock_native, mock_verify_upgrade, mock_recover, mock_gcs, mock_npm,
    ):
        """Native-only mode skips npm in recovery cascade (Tier 3 omitted)."""
        mock_verify.return_value = (True, '/home/user/.local/bin/claude', 'native')
        result = install_claude.ensure_claude()
        assert result is True
        mock_npm.assert_not_called()
        assert mock_get_version.return_value == '2.1.89'
        assert mock_get_latest.return_value == '2.1.92'
        assert mock_compare.return_value is False
        mock_native.assert_called()
        mock_verify_upgrade.assert_called()
        mock_recover.assert_called_once()
        mock_gcs.assert_called_once()

    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'auto'}, clear=False)
    @patch('install_claude._verify_upgrade_version', return_value=(True, '2.1.92'))
    @patch('install_claude.install_claude_native_cross_platform', return_value=True)
    @patch('install_claude.compare_versions', return_value=False)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.92')
    @patch('install_claude.get_claude_version', return_value='2.1.89')
    @patch('install_claude.verify_claude_installation')
    def test_native_source_version_matches_no_recovery(
        self, mock_verify, mock_get_version, mock_get_latest, mock_compare,
        mock_native, mock_verify_upgrade,
    ):
        """When version matches after upgrade, no recovery cascade triggered."""
        mock_verify.return_value = (True, '/home/user/.local/bin/claude', 'native')
        result = install_claude.ensure_claude()
        assert result is True
        assert mock_get_version.return_value == '2.1.89'
        assert mock_get_latest.return_value == '2.1.92'
        assert mock_compare.return_value is False
        mock_native.assert_called()
        mock_verify_upgrade.assert_called()

    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'auto'}, clear=False)
    @patch('install_claude.update_install_method_config')
    @patch('install_claude._recover_from_versions_directory', return_value='2.1.92')
    @patch('install_claude._verify_upgrade_version', return_value=(False, '2.1.89'))
    @patch('install_claude.install_claude_native_cross_platform', return_value=True)
    @patch('install_claude.compare_versions', return_value=False)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.92')
    @patch('install_claude.get_claude_version', return_value='2.1.89')
    @patch('install_claude.verify_claude_installation')
    def test_unknown_source_mismatch_recovers_from_versions_dir(
        self, mock_verify, mock_get_version, mock_get_latest, mock_compare,
        mock_native, mock_verify_upgrade, mock_recover, mock_config,
    ):
        """Unknown source upgrade with mismatch triggers versions dir recovery."""
        mock_verify.return_value = (True, '/usr/local/bin/claude', 'unknown')
        result = install_claude.ensure_claude()
        assert result is True
        mock_recover.assert_called_once_with('2.1.92')
        mock_config.assert_called_with('native')
        assert mock_get_version.return_value == '2.1.89'
        assert mock_get_latest.return_value == '2.1.92'
        assert mock_compare.return_value is False
        mock_native.assert_called()
        mock_verify_upgrade.assert_called()

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only test')
    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'auto'}, clear=False)
    @patch('install_claude.update_install_method_config')
    @patch('install_claude._recover_from_versions_directory', return_value='2.1.92')
    @patch('install_claude._verify_upgrade_version', return_value=(False, '2.1.89'))
    @patch('install_claude.run_command')
    @patch('install_claude.compare_versions', return_value=False)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.92')
    @patch('install_claude.get_claude_version', return_value='2.1.89')
    @patch('install_claude.verify_claude_installation')
    def test_winget_source_mismatch_recovers_from_versions_dir(
        self, mock_verify, mock_get_version, mock_get_latest, mock_compare,
        mock_run, mock_verify_upgrade, mock_recover, mock_config,
    ):
        """Winget upgrade with mismatch triggers versions dir recovery."""
        mock_verify.return_value = (
            True,
            r'C:\Users\test\AppData\Local\Programs\claude\claude.exe',
            'winget',
        )
        mock_run.return_value = MagicMock(returncode=0)
        result = install_claude.ensure_claude()
        assert result is True
        mock_recover.assert_called_once_with('2.1.92')
        mock_config.assert_called_with('native')
        assert mock_get_version.return_value == '2.1.89'
        assert mock_get_latest.return_value == '2.1.92'
        assert mock_compare.return_value is False
        mock_verify_upgrade.assert_called()

    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'auto'}, clear=False)
    @patch('install_claude._verify_upgrade_version', return_value=(False, '2.1.89'))
    @patch('install_claude.install_claude_npm', return_value=True)
    @patch('install_claude.compare_versions', return_value=False)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.92')
    @patch('install_claude.get_claude_version', return_value='2.1.89')
    @patch('install_claude.verify_claude_installation')
    def test_npm_source_mismatch_graceful_degradation(
        self, mock_verify, mock_get_version, mock_get_latest, mock_compare,
        mock_npm, mock_verify_upgrade,
    ):
        """npm upgrade with mismatch degrades gracefully (no recovery cascade)."""
        # First call: migration check (return non-npm to skip migration)
        # Second call: upgrade source detection (return npm)
        mock_verify.side_effect = [
            (True, '/home/user/.local/bin/claude', 'native'),
            (True, '/home/user/.npm-global/bin/claude', 'npm'),
        ]
        result = install_claude.ensure_claude()
        assert result is True
        assert mock_get_version.return_value == '2.1.89'
        assert mock_get_latest.return_value == '2.1.92'
        assert mock_compare.return_value is False
        mock_npm.assert_called()
        mock_verify_upgrade.assert_called()

    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'auto'}, clear=False)
    @patch('install_claude._verify_upgrade_version', return_value=(True, '2.1.92'))
    @patch('install_claude.install_claude_npm', return_value=True)
    @patch('install_claude.compare_versions', return_value=False)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.92')
    @patch('install_claude.get_claude_version', return_value='2.1.89')
    @patch('install_claude.verify_claude_installation')
    def test_npm_source_version_matches(
        self, mock_verify, mock_get_version, mock_get_latest, mock_compare,
        mock_npm, mock_verify_upgrade,
    ):
        """npm upgrade with version match succeeds normally."""
        # First call: migration check (return non-npm to skip migration)
        # Second call: upgrade source detection (return npm)
        mock_verify.side_effect = [
            (True, '/home/user/.local/bin/claude', 'native'),
            (True, '/home/user/.npm-global/bin/claude', 'npm'),
        ]
        result = install_claude.ensure_claude()
        assert result is True
        assert mock_get_version.return_value == '2.1.89'
        assert mock_get_latest.return_value == '2.1.92'
        assert mock_compare.return_value is False
        mock_npm.assert_called()
        mock_verify_upgrade.assert_called()

    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'auto'}, clear=False)
    @patch('install_claude.install_claude_npm')
    @patch('install_claude._download_claude_direct_from_gcs', return_value=False)
    @patch('install_claude._recover_from_versions_directory', return_value=None)
    @patch('install_claude._verify_upgrade_version', return_value=(False, '2.1.89'))
    @patch('install_claude.install_claude_native_cross_platform', return_value=True)
    @patch('install_claude.compare_versions', return_value=False)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.92')
    @patch('install_claude.get_claude_version', return_value='2.1.89')
    @patch('install_claude.verify_claude_installation')
    def test_all_recovery_tiers_fail_graceful_degradation(
        self, mock_verify, mock_get_version, mock_get_latest, mock_compare,
        mock_native, mock_verify_upgrade, mock_recover, mock_gcs, mock_npm,
    ):
        """When all recovery tiers fail, graceful degradation with warning."""
        mock_verify.return_value = (True, '/home/user/.local/bin/claude', 'native')
        mock_npm.return_value = False
        result = install_claude.ensure_claude()
        assert result is True  # Graceful degradation -- never blocks installation
        assert mock_get_version.return_value == '2.1.89'
        assert mock_get_latest.return_value == '2.1.92'
        assert mock_compare.return_value is False
        mock_native.assert_called()
        mock_verify_upgrade.assert_called()
        mock_recover.assert_called_once()
        mock_gcs.assert_called_once()


class TestGcsRecoveryInstallMethodReset:
    """Tests that update_install_method_config('native') is called on GCS recovery success."""

    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'native'}, clear=False)
    @patch('install_claude.update_install_method_config')
    @patch('install_claude._download_claude_direct_from_gcs', return_value=True)
    @patch('install_claude._recover_from_versions_directory', return_value=None)
    @patch('install_claude._verify_upgrade_version', return_value=(False, '2.1.89'))
    @patch('install_claude.install_claude_native_cross_platform', return_value=True)
    @patch('install_claude.compare_versions', return_value=False)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.92')
    @patch('install_claude.get_claude_version', return_value='2.1.89')
    @patch('install_claude.verify_claude_installation')
    def test_native_mode_gcs_recovery_sets_native(
        self, mock_verify, mock_get_version, mock_get_latest, mock_compare,
        mock_native, mock_verify_upgrade, mock_recover, mock_gcs, mock_config,
    ):
        """install_method=='native' branch: GCS recovery sets installMethod to native."""
        mock_verify.return_value = (True, '/home/user/.local/bin/claude', 'native')
        result = install_claude.ensure_claude()
        assert result is True
        mock_gcs.assert_called_once()
        mock_config.assert_called_with('native')
        # Confirm mocks participated
        assert mock_get_version.return_value == '2.1.89'
        assert mock_get_latest.return_value == '2.1.92'
        assert mock_compare.return_value is False
        mock_native.assert_called()
        mock_verify_upgrade.assert_called()
        mock_recover.assert_called_once()

    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'auto'}, clear=False)
    @patch('install_claude.update_install_method_config')
    @patch('install_claude._download_claude_direct_from_gcs', return_value=True)
    @patch('install_claude._recover_from_versions_directory', return_value=None)
    @patch('install_claude._verify_upgrade_version', return_value=(False, '2.1.89'))
    @patch('install_claude.install_claude_native_cross_platform', return_value=True)
    @patch('install_claude.compare_versions', return_value=False)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.92')
    @patch('install_claude.get_claude_version', return_value='2.1.89')
    @patch('install_claude.verify_claude_installation')
    def test_native_source_gcs_recovery_sets_native(
        self, mock_verify, mock_get_version, mock_get_latest, mock_compare,
        mock_native, mock_verify_upgrade, mock_recover, mock_gcs, mock_config,
    ):
        """upgrade_source=='native' branch: GCS recovery sets installMethod to native."""
        mock_verify.return_value = (True, '/home/user/.local/bin/claude', 'native')
        result = install_claude.ensure_claude()
        assert result is True
        mock_gcs.assert_called_once()
        mock_config.assert_called_with('native')
        assert mock_get_version.return_value == '2.1.89'
        assert mock_get_latest.return_value == '2.1.92'
        assert mock_compare.return_value is False
        mock_native.assert_called()
        mock_verify_upgrade.assert_called()
        mock_recover.assert_called_once()

    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'auto'}, clear=False)
    @patch('install_claude.update_install_method_config')
    @patch('install_claude._download_claude_direct_from_gcs', return_value=True)
    @patch('install_claude._recover_from_versions_directory', return_value=None)
    @patch('install_claude._verify_upgrade_version', return_value=(False, '2.1.89'))
    @patch('install_claude.install_claude_native_cross_platform', return_value=True)
    @patch('install_claude.compare_versions', return_value=False)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.92')
    @patch('install_claude.get_claude_version', return_value='2.1.89')
    @patch('install_claude.verify_claude_installation')
    def test_unknown_source_gcs_recovery_sets_native(
        self, mock_verify, mock_get_version, mock_get_latest, mock_compare,
        mock_native, mock_verify_upgrade, mock_recover, mock_gcs, mock_config,
    ):
        """upgrade_source=='unknown' branch: GCS recovery sets installMethod to native."""
        mock_verify.return_value = (True, '/usr/local/bin/claude', 'unknown')
        result = install_claude.ensure_claude()
        assert result is True
        mock_gcs.assert_called_once()
        mock_config.assert_called_with('native')
        assert mock_get_version.return_value == '2.1.89'
        assert mock_get_latest.return_value == '2.1.92'
        assert mock_compare.return_value is False
        mock_native.assert_called()
        mock_verify_upgrade.assert_called()
        mock_recover.assert_called_once()

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only test')
    @patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'auto'}, clear=False)
    @patch('install_claude.update_install_method_config')
    @patch('install_claude._download_claude_direct_from_gcs', return_value=True)
    @patch('install_claude._recover_from_versions_directory', return_value=None)
    @patch('install_claude._verify_upgrade_version', return_value=(False, '2.1.89'))
    @patch('install_claude.run_command')
    @patch('install_claude.compare_versions', return_value=False)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.92')
    @patch('install_claude.get_claude_version', return_value='2.1.89')
    @patch('install_claude.verify_claude_installation')
    def test_winget_source_gcs_recovery_sets_native(
        self, mock_verify, mock_get_version, mock_get_latest, mock_compare,
        mock_run, mock_verify_upgrade, mock_recover, mock_gcs, mock_config,
    ):
        """upgrade_source=='winget' branch: GCS recovery sets installMethod to native."""
        mock_verify.return_value = (
            True, r'C:\Users\test\AppData\Local\Programs\claude\claude.exe', 'winget',
        )
        # Winget upgrade returns 0 (success) but version mismatch triggers recovery
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')
        result = install_claude.ensure_claude()
        assert result is True
        mock_gcs.assert_called_once()
        mock_config.assert_called_with('native')
        assert mock_get_version.return_value == '2.1.89'
        assert mock_get_latest.return_value == '2.1.92'
        assert mock_compare.return_value is False
        mock_verify_upgrade.assert_called()
        mock_recover.assert_called_once()


class TestRecoveryCascade:
    """Tests for _recovery_cascade() helper that consolidates versions cache + GCS recovery."""

    @patch('install_claude.update_install_method_config')
    @patch('install_claude._download_claude_direct_from_gcs')
    @patch('install_claude._recover_from_versions_directory', return_value='2.1.92')
    def test_versions_cache_success_returns_true(self, mock_recover, mock_gcs, mock_config):
        """Versions cache hit returns True and skips GCS download."""
        result = install_claude._recovery_cascade('2.1.92')

        assert result is True
        mock_recover.assert_called_once_with('2.1.92')
        mock_gcs.assert_not_called()
        assert mock_config.called

    @patch('install_claude.update_install_method_config')
    @patch('install_claude._download_claude_direct_from_gcs')
    @patch('install_claude._recover_from_versions_directory', return_value='2.1.92')
    def test_versions_cache_success_sets_native_install_method(self, mock_recover, mock_gcs, mock_config):
        """Versions cache recovery records installMethod as 'native'."""
        install_claude._recovery_cascade('2.1.92')

        mock_config.assert_called_once_with('native')
        assert mock_recover.return_value == '2.1.92'
        mock_gcs.assert_not_called()

    @patch('install_claude.update_install_method_config')
    @patch('install_claude.get_claude_version', return_value='2.1.92')
    @patch('install_claude.get_real_user_home', return_value=Path('/home/test'))
    @patch('install_claude._download_claude_direct_from_gcs', return_value=True)
    @patch('install_claude._recover_from_versions_directory', return_value=None)
    def test_gcs_success_returns_true_and_sets_native(
        self, mock_recover, mock_gcs, mock_home, mock_version, mock_config,
    ):
        """GCS download success returns True and records installMethod as 'native'."""
        result = install_claude._recovery_cascade('2.1.92')

        assert result is True
        mock_recover.assert_called_once_with('2.1.92')
        mock_gcs.assert_called_once()
        mock_config.assert_called_once_with('native')
        assert mock_home.return_value == Path('/home/test')
        assert mock_version.return_value == '2.1.92'

    @patch('install_claude.update_install_method_config')
    @patch('install_claude.get_real_user_home', return_value=Path('/home/test'))
    @patch('install_claude._download_claude_direct_from_gcs', return_value=False)
    @patch('install_claude._recover_from_versions_directory', return_value=None)
    def test_all_tiers_fail_returns_false(self, mock_recover, mock_gcs, mock_home, mock_config):
        """Both tiers failing returns False without setting installMethod."""
        result = install_claude._recovery_cascade('2.1.92')

        assert result is False
        mock_config.assert_not_called()
        mock_recover.assert_called_once_with('2.1.92')
        mock_gcs.assert_called_once()
        assert mock_home.return_value == Path('/home/test')

    @patch('install_claude.update_install_method_config')
    @patch('install_claude.get_claude_version', return_value='2.1.92')
    @patch('install_claude.get_real_user_home', return_value=Path('/home/test'))
    @patch('install_claude._download_claude_direct_from_gcs', return_value=True)
    @patch('install_claude._recover_from_versions_directory', return_value=None)
    def test_gcs_success_logs_version(self, mock_recover, mock_gcs, mock_home, mock_version, mock_config):
        """GCS recovery logs the version on success."""
        install_claude._recovery_cascade('2.1.92')

        mock_version.assert_called_once()
        mock_recover.assert_called_once_with('2.1.92')
        mock_gcs.assert_called_once()
        assert mock_home.return_value == Path('/home/test')
        assert mock_config.called

    @patch('install_claude.update_install_method_config')
    @patch('install_claude.get_claude_version', return_value=None)
    @patch('install_claude.get_real_user_home', return_value=Path('/home/test'))
    @patch('install_claude._download_claude_direct_from_gcs', return_value=True)
    @patch('install_claude._recover_from_versions_directory', return_value=None)
    def test_gcs_success_no_version_still_returns_true(
        self, mock_recover, mock_gcs, mock_home, mock_version, mock_config,
    ):
        """GCS recovery returns True even when version query returns None."""
        result = install_claude._recovery_cascade('2.1.92')

        assert result is True
        mock_config.assert_called_once_with('native')
        mock_recover.assert_called_once_with('2.1.92')
        mock_gcs.assert_called_once()
        assert mock_home.return_value == Path('/home/test')
        assert mock_version.return_value is None


class TestEnsureClaudeVersionPassThrough:
    """Tests verifying ensure_claude() passes latest_version to install chain at upgrade sites."""

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only test')
    @patch.dict(os.environ, {'CLAUDE_CODE_TOOLBOX_INSTALL_METHOD': 'native'})
    @patch('install_claude._recovery_cascade', return_value=False)
    @patch('install_claude._verify_upgrade_version', return_value=(True, '2.1.98'))
    @patch('install_claude.install_claude_native_cross_platform', return_value=True)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.98')
    @patch('install_claude.compare_versions', return_value=False)
    @patch('install_claude.get_claude_version', return_value='2.1.89')
    @patch(
        'install_claude.verify_claude_installation',
        return_value=(True, r'C:\Users\test\.local\bin\claude.exe', 'native'),
    )
    @patch('install_claude.ensure_nodejs')
    def test_native_mode_upgrade_passes_version(
        self, mock_node, mock_verify, mock_get_version, mock_compare,
        mock_get_latest, mock_cross_platform, mock_verify_upgrade, mock_cascade,
    ):
        """Native-only mode upgrade passes latest_version to install_claude_native_cross_platform."""
        install_claude.ensure_claude()

        mock_cross_platform.assert_called_once_with(version='2.1.98')
        assert mock_verify.return_value == (True, r'C:\Users\test\.local\bin\claude.exe', 'native')
        assert mock_get_version.return_value == '2.1.89'
        assert mock_compare.return_value is False
        assert mock_get_latest.return_value == '2.1.98'
        mock_verify_upgrade.assert_called()
        assert mock_cascade.return_value is False
        assert mock_node is not None

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only test')
    @patch('install_claude._recovery_cascade', return_value=False)
    @patch('install_claude._verify_upgrade_version', return_value=(True, '2.1.98'))
    @patch('install_claude.install_claude_native_cross_platform', return_value=True)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.98')
    @patch('install_claude.compare_versions', return_value=False)
    @patch('install_claude.get_claude_version', return_value='2.1.89')
    @patch(
        'install_claude.verify_claude_installation',
        return_value=(True, r'C:\Users\test\.local\bin\claude.exe', 'native'),
    )
    @patch('install_claude.ensure_nodejs')
    def test_native_source_upgrade_passes_version(
        self, mock_node, mock_verify, mock_get_version, mock_compare,
        mock_get_latest, mock_cross_platform, mock_verify_upgrade, mock_cascade,
    ):
        """Auto mode with native source passes latest_version to install_claude_native_cross_platform."""
        install_claude.ensure_claude()

        mock_cross_platform.assert_called_once_with(version='2.1.98')
        assert mock_verify.return_value == (True, r'C:\Users\test\.local\bin\claude.exe', 'native')
        assert mock_get_version.return_value == '2.1.89'
        assert mock_compare.return_value is False
        assert mock_get_latest.return_value == '2.1.98'
        mock_verify_upgrade.assert_called()
        assert mock_cascade.return_value is False
        assert mock_node is not None

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only test')
    @patch('install_claude._recovery_cascade', return_value=False)
    @patch('install_claude._verify_upgrade_version', return_value=(True, '2.1.98'))
    @patch('install_claude.install_claude_native_cross_platform', return_value=True)
    @patch('install_claude.get_latest_claude_version', return_value='2.1.98')
    @patch('install_claude.compare_versions', return_value=False)
    @patch('install_claude.get_claude_version', return_value='2.1.89')
    @patch(
        'install_claude.verify_claude_installation',
        return_value=(True, r'C:\some\random\path\claude.exe', 'unknown'),
    )
    @patch('install_claude.ensure_nodejs')
    def test_unknown_source_upgrade_passes_version(
        self, mock_node, mock_verify, mock_get_version, mock_compare,
        mock_get_latest, mock_cross_platform, mock_verify_upgrade, mock_cascade,
    ):
        """Auto mode with unknown source passes latest_version to install_claude_native_cross_platform."""
        install_claude.ensure_claude()

        mock_cross_platform.assert_called_once_with(version='2.1.98')
        assert mock_verify.return_value == (True, r'C:\some\random\path\claude.exe', 'unknown')
        assert mock_get_version.return_value == '2.1.89'
        assert mock_compare.return_value is False
        assert mock_get_latest.return_value == '2.1.98'
        mock_verify_upgrade.assert_called()
        assert mock_cascade.return_value is False
        assert mock_node is not None


class TestDiagnosticLogging:
    """Tests for diagnostic version logging in _install_claude_native_windows_installer."""

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only test')
    @patch('install_claude._finalize_native_install')
    @patch('install_claude.get_claude_version', return_value='2.1.92')
    @patch(
        'install_claude.verify_claude_installation',
        return_value=(True, r'C:\Users\test\.local\bin\claude.exe', 'native'),
    )
    @patch('install_claude.ensure_local_bin_in_path_windows')
    @patch('install_claude.run_command')
    @patch('install_claude.urlopen')
    def test_logs_post_install_version(
        self, mock_urlopen, mock_run, mock_path, mock_verify,
        mock_get_version, mock_finalize, capsys,
    ):
        """Diagnostic info line is printed after successful native install."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'echo "test"'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        mock_run.return_value = MagicMock(
            returncode=0, stdout='Installed 2.1.92', stderr='',
        )

        install_claude._install_claude_native_windows_installer()

        # Verify all mocks participated correctly
        mock_get_version.assert_called()
        mock_verify.assert_called()
        mock_path.assert_called()
        mock_finalize.assert_called()
        captured = capsys.readouterr()
        assert 'Post-install binary version: 2.1.92' in captured.out
