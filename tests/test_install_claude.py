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

    @patch('platform.system', return_value='Windows')
    @patch('ctypes.windll.shell32.IsUserAnAdmin', return_value=1)
    def test_is_admin_windows_true(self, mock_admin, mock_system):
        """Test admin check on Windows when admin."""
        # Verify mock configurations
        assert mock_system.return_value == 'Windows'
        assert mock_admin.return_value == 1
        assert install_claude.is_admin() is True

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
    def test_configure_powershell_policy_success(self, mock_run, mock_system):
        """Test successful PowerShell policy configuration."""
        # Verify mock configuration
        assert mock_system.return_value == 'Windows'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')
        install_claude.configure_powershell_policy()
        mock_run.assert_called_once()
        # Check that the command list contains powershell and Set-ExecutionPolicy
        cmd = mock_run.call_args[0][0]
        assert 'powershell' in cmd or 'powershell.exe' in cmd
        assert any('Set-ExecutionPolicy' in str(arg) for arg in cmd)

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

    @patch('install_claude.find_command')
    @patch('platform.system', return_value='Windows')
    @patch('pathlib.Path.exists', return_value=True)
    def test_get_claude_version_windows(self, mock_exists, mock_system, mock_find):
        """Test getting Claude version on Windows."""
        # Verify mock configurations
        assert mock_system.return_value == 'Windows'
        assert mock_exists.return_value is True
        mock_find.return_value = None
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
    @patch('install_claude.find_command', return_value='npm')
    @patch('install_claude.run_command')
    def test_install_claude_npm_sudo_fallback(self, mock_run, mock_find, mock_system):
        """Test Claude installation with sudo fallback."""
        # Verify mock configurations
        assert mock_system.return_value == 'Linux'
        assert mock_find.return_value == 'npm'
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
    def test_install_claude_native_windows(self, mock_run, mock_temp, mock_urlopen, mock_system):
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
        result = install_claude.install_claude_native()
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

    @patch('install_claude.get_claude_version')
    @patch('install_claude.install_claude_npm')
    def test_ensure_claude_upgrade(self, mock_install, mock_get_version):
        """Test Claude upgrade when already installed."""
        mock_get_version.side_effect = ['0.7.0', '0.7.7']
        mock_install.return_value = True
        result = install_claude.ensure_claude()
        assert result is True
        mock_install.assert_called_with(upgrade=True)

    @patch('install_claude.get_claude_version', return_value=None)
    @patch('install_claude.install_claude_npm', return_value=False)
    @patch('platform.system', return_value='Windows')
    @patch('install_claude.install_claude_native', return_value=True)
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
    def test_main_windows_success(self, mock_set_env, mock_find, mock_update, mock_ps, mock_claude, mock_node, mock_git,
                                   mock_system):
        """Test successful main flow on Windows."""
        # Verify mock configurations
        assert mock_system.return_value == 'Windows'
        assert mock_git.return_value == 'C:\\Git\\bash.exe'
        assert mock_node.return_value is True
        assert mock_claude.return_value is True
        assert mock_find.return_value is None
        with patch('sys.exit') as mock_exit:
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
        with patch('sys.exit') as mock_exit:
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
        with patch('sys.exit') as mock_exit:
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
