"""
Comprehensive tests for install_claude.py - the main Claude Code installer.
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

    @patch('shutil.which')
    def test_find_command(self, mock_which):
        """Test finding command in PATH."""
        mock_which.return_value = '/usr/bin/git'
        assert install_claude.find_command('git') == '/usr/bin/git'
        mock_which.assert_called_with('git')


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

    @patch.dict('os.environ', {'CLAUDE_CODE_GIT_BASH_PATH': 'C:\\Git\\bash.exe'})
    @patch('pathlib.Path.exists', return_value=True)
    def test_find_bash_windows_env_var(self, mock_exists):
        """Test finding bash via environment variable."""
        # Verify mock configuration
        assert mock_exists.return_value is True
        result = install_claude.find_bash_windows()
        assert result == str(Path('C:\\Git\\bash.exe').resolve())

    @patch('install_claude.find_command')
    def test_find_bash_windows_in_path(self, mock_find):
        """Test finding bash.exe in PATH."""
        mock_find.return_value = 'C:\\Program Files\\Git\\bin\\bash.exe'
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

    @patch('install_claude.find_command', return_value='winget')
    def test_check_winget_available(self, mock_find):
        """Test winget availability check."""
        # Verify mock configuration
        assert mock_find.return_value == 'winget'
        assert install_claude.check_winget() is True

    @patch('install_claude.find_command', return_value=None)
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

    @patch('urllib.request.urlopen')
    def test_install_git_windows_download_ssl_error(self, mock_urlopen):
        """Test Git download with SSL error fallback."""
        mock_urlopen.side_effect = [
            urllib.error.URLError('SSL: CERTIFICATE_VERIFY_FAILED'),
            MagicMock(read=lambda: b'<a href="/git/Git-2.43.0-64-bit.exe">Download</a>'),
        ]

        with patch('urllib.request.urlretrieve'), patch('install_claude.run_command') as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 1, '', '')
            result = install_claude.install_git_windows_download()
            assert result is False


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

    @patch('install_claude.get_git_installer_url_from_github')
    @patch('install_claude.urlretrieve')
    @patch('install_claude.run_command')
    @patch('tempfile.NamedTemporaryFile')
    @patch('os.unlink')
    def test_install_git_via_github_api(self, mock_unlink, mock_temp, mock_run, mock_retrieve, mock_github):
        """Test successful Git installation via GitHub API."""
        # Mock GitHub API returning URL
        mock_github.return_value = 'https://github.com/git-for-windows/git/releases/download/v2.51.1.windows.1/Git-2.51.1-64-bit.exe'

        # Mock temp file
        temp_file = MagicMock()
        temp_file.name = 'C:\\temp\\git.exe'
        mock_temp.return_value.__enter__.return_value = temp_file

        # Mock successful installation
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        result = install_claude.install_git_windows_download()
        assert result is True
        mock_github.assert_called_once()
        mock_retrieve.assert_called_once()
        mock_run.assert_called_once()
        mock_unlink.assert_called_once()

    @patch('install_claude.get_git_installer_url_from_github', return_value=None)
    @patch('install_claude.urlopen')
    @patch('install_claude.urlretrieve')
    @patch('install_claude.run_command')
    @patch('tempfile.NamedTemporaryFile')
    def test_install_git_fallback_to_scraping(self, mock_temp, mock_run, mock_retrieve, mock_urlopen, mock_github):
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
        # Verify GitHub API was tried first
        mock_github.assert_called_once()
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

    @patch('install_claude.find_command', return_value=None)
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
        """Test Node.js installation via Homebrew."""
        mock_find.return_value = '/usr/local/bin/brew'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')
        result = install_claude.install_nodejs_homebrew()
        assert result is True

    @patch('install_claude.run_command')
    def test_install_nodejs_apt(self, mock_run):
        """Test Node.js installation via apt."""
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')
        result = install_claude.install_nodejs_apt()
        assert result is True


class TestClaudeInstallation:
    """Test Claude Code installation functions."""

    @patch('install_claude.find_command_robust')
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

    @patch('install_claude.find_command_robust')
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
    @patch('install_claude.find_command', return_value='npm')
    @patch('install_claude.needs_sudo_for_npm', return_value=True)
    @patch('install_claude.run_command')
    def test_install_claude_npm_sudo_fallback(self, mock_run, mock_needs_sudo, mock_find, mock_system):
        """Test Claude installation with sudo fallback."""
        # Verify mock configurations
        assert mock_system.return_value == 'Linux'
        assert mock_find.return_value == 'npm'
        assert mock_needs_sudo.return_value is True
        mock_run.side_effect = [
            subprocess.CompletedProcess([], 1, '', 'permission denied'),
            subprocess.CompletedProcess([], 0, '', ''),
        ]
        result = install_claude.install_claude_npm()
        assert result is True
        assert mock_run.call_count == 2
        assert 'sudo' in mock_run.call_args_list[1][0][0]

    @patch('platform.system', return_value='Windows')
    @patch('urllib.request.urlopen')
    @patch('tempfile.NamedTemporaryFile')
    @patch('install_claude.run_command')
    @patch('install_claude.verify_claude_installation')
    @patch('install_claude.ensure_local_bin_in_path_windows')
    def test_install_claude_native_windows(
        self,
        mock_ensure_path,
        mock_verify,
        mock_run,
        mock_temp,
        mock_urlopen,
        mock_system,
    ):
        """Test native Claude installer on Windows."""
        # Verify mock configuration
        assert mock_system.return_value == 'Windows'
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
        with patch('install_claude.get_node_version') as mock_get_after:
            mock_get_after.side_effect = [None, 'v20.10.0']
            with patch('install_claude.compare_versions', return_value=True):
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


class TestMainFunction:
    """Test the main installation flow."""

    @patch('platform.system', return_value='Windows')
    @patch('install_claude.ensure_git_bash_windows', return_value='C:\\Git\\bash.exe')
    @patch('install_claude.ensure_nodejs', return_value=True)
    @patch('install_claude.ensure_claude', return_value=True)
    @patch('install_claude.configure_powershell_policy')
    @patch('install_claude.update_path')
    @patch('install_claude.find_command', return_value=None)
    @patch('install_claude.set_windows_env_var')
    def test_main_windows_success(
        self,
        mock_set_env,
        mock_find,
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
        assert mock_find.return_value is None
        # Force npm installation method to ensure Node.js is installed
        with patch.dict('os.environ', {'CLAUDE_INSTALL_METHOD': 'npm'}), patch('sys.exit') as mock_exit:
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
        with patch.dict('os.environ', {'CLAUDE_INSTALL_METHOD': 'npm'}), patch('sys.exit') as mock_exit:
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
        with patch('sys.exit') as mock_exit:
            install_claude.main()
            mock_exit.assert_called_with(1)

    @patch('platform.system', return_value='Darwin')
    @patch('install_claude.ensure_nodejs', return_value=False)
    def test_main_nodejs_failure(self, mock_node, mock_system):
        """Test main flow failure when Node.js installation fails."""
        # Verify mock configurations
        assert mock_system.return_value == 'Darwin'
        assert mock_node.return_value is False
        # Force npm installation method to ensure Node.js is required
        with patch.dict('os.environ', {'CLAUDE_INSTALL_METHOD': 'npm'}), patch('sys.exit') as mock_exit:
            install_claude.main()
            mock_exit.assert_called_with(1)


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

        with patch('install_claude.find_command_robust', return_value=None):
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
    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.stat')
    @patch('os.path.expandvars')
    def test_verify_claude_installation_winget(self, mock_expandvars, mock_stat, mock_exists):
        """Test verification when winget installation exists."""
        # Mock: native and npm don't exist, winget exists with valid size
        # Order of exists() calls: native, npm_cmd, npm_executable, winget
        mock_exists.side_effect = [
            False,  # native_path.exists() -> False
            False,  # npm_cmd_path.exists() -> False
            False,  # npm_path.exists() -> False
            True,  # winget_path.exists() -> True
        ]
        mock_stat.return_value.st_size = 5000000  # 5MB file
        mock_expandvars.side_effect = lambda x: x.replace('%LOCALAPPDATA%', 'C:\\Users\\Test\\AppData\\Local')

        is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is True
        assert source == 'winget'
        assert 'programs\\claude' in path.lower() or 'programs/claude' in path.lower()

    @patch('sys.platform', 'win32')
    @patch('pathlib.Path.exists', return_value=False)
    @patch('install_claude.find_command_robust')
    def test_verify_claude_installation_path_fallback_npm_detection(self, mock_find, mock_exists):
        """Test PATH fallback with npm source detection from path string."""
        # Mock: no direct paths exist, but find_command_robust finds npm installation
        assert mock_exists.return_value is False
        mock_find.return_value = 'C:\\Users\\Test\\AppData\\Roaming\\npm\\claude.cmd'

        is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is True
        assert source == 'npm'
        assert 'npm' in path.lower()

    @patch('sys.platform', 'win32')
    @patch('pathlib.Path.exists', return_value=False)
    @patch('install_claude.find_command_robust')
    def test_verify_claude_installation_path_fallback_native_detection(self, mock_find, mock_exists):
        """Test PATH fallback with native source detection from path string."""
        # Mock: no direct paths exist, but find_command_robust finds native location
        assert mock_exists.return_value is False
        mock_find.return_value = 'C:\\Users\\Test\\.local\\bin\\claude.exe'

        is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is True
        assert source == 'native'
        assert '.local\\bin' in path.lower()

    @patch('sys.platform', 'win32')
    @patch('pathlib.Path.exists', return_value=False)
    @patch('install_claude.find_command_robust')
    def test_verify_claude_installation_path_fallback_winget_detection(self, mock_find, mock_exists):
        """Test PATH fallback with winget source detection from path string."""
        # Mock: no direct paths exist, but find_command_robust finds winget installation
        assert mock_exists.return_value is False
        mock_find.return_value = 'C:\\Users\\Test\\AppData\\Local\\Programs\\claude\\claude.exe'

        is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is True
        assert source == 'winget'
        assert 'programs\\claude' in path.lower()

    @patch('sys.platform', 'win32')
    @patch('pathlib.Path.exists', return_value=False)
    @patch('install_claude.find_command_robust')
    def test_verify_claude_installation_path_fallback_unknown(self, mock_find, mock_exists):
        """Test PATH fallback with unknown source (doesn't match patterns)."""
        # Mock: find_command_robust finds claude but in unexpected location
        assert mock_exists.return_value is False
        mock_find.return_value = 'C:\\CustomPath\\claude.exe'

        is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is True
        assert source == 'unknown'
        assert path == 'C:\\CustomPath\\claude.exe'

    @patch('sys.platform', 'win32')
    @patch('pathlib.Path.exists', return_value=False)
    @patch('install_claude.find_command_robust', return_value=None)
    def test_verify_claude_installation_not_found(self, mock_find, mock_exists):
        """Test verification when Claude is not installed anywhere."""
        # Mock: no paths exist, find_command_robust returns None
        assert mock_exists.return_value is False
        assert mock_find.return_value is None

        is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is False
        assert path is None
        assert source == 'none'

    @patch('sys.platform', 'linux')
    @patch('install_claude.find_command_robust')
    def test_verify_claude_installation_linux_npm(self, mock_find):
        """Test verification on Linux with npm installation."""
        mock_find.return_value = '/home/user/.npm-global/bin/claude'

        is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is True
        assert source == 'npm'
        assert '.npm-global' in path or 'npm' in path

    @patch('sys.platform', 'linux')
    @patch('install_claude.find_command_robust')
    def test_verify_claude_installation_linux_unknown(self, mock_find):
        """Test verification on Linux with unknown source."""
        mock_find.return_value = '/usr/local/bin/claude'

        is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is True
        assert source == 'unknown'
        assert path == '/usr/local/bin/claude'

    @patch('sys.platform', 'linux')
    @patch('install_claude.find_command_robust', return_value=None)
    def test_verify_claude_installation_linux_not_found(self, mock_find):
        """Test verification on Linux when not installed."""
        assert mock_find.return_value is None

        is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is False
        assert path is None
        assert source == 'none'

    @patch('sys.platform', 'darwin')
    @patch('install_claude.find_command_robust')
    def test_verify_claude_installation_macos(self, mock_find):
        """Test verification on macOS."""
        mock_find.return_value = '/usr/local/bin/claude'

        is_installed, path, source = install_claude.verify_claude_installation()

        assert is_installed is True
        assert source == 'unknown'
        assert path == '/usr/local/bin/claude'

    @patch('sys.platform', 'win32')
    @patch('pathlib.Path.exists', return_value=False)
    @patch('install_claude.find_command_robust')
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
