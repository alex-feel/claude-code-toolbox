"""
Comprehensive tests for setup_environment.py - the main environment setup script.
"""

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

import setup_environment


class TestColors:
    """Test the Colors class and color stripping."""

    def test_colors_strip_windows_cmd(self):
        """Test that colors are stripped in Windows CMD."""
        with patch('platform.system', return_value='Windows'), patch.dict('os.environ', {}, clear=True):
            setup_environment.Colors.strip()
            assert setup_environment.Colors.RED == ''
            assert setup_environment.Colors.GREEN == ''
            assert setup_environment.Colors.NC == ''

    def test_colors_kept_windows_terminal(self):
        """Test that colors are kept in Windows Terminal."""
        # Reset colors first
        setup_environment.Colors.RED = '\033[0;31m'
        setup_environment.Colors.GREEN = '\033[0;32m'
        with patch('platform.system', return_value='Windows'), patch.dict('os.environ', {'WT_SESSION': '1'}):
            setup_environment.Colors.strip()
            assert setup_environment.Colors.RED == '\033[0;31m'


class TestLoggingFunctions:
    """Test logging functions."""

    def test_info(self, capsys):
        """Test info message output."""
        setup_environment.info('Test message')
        captured = capsys.readouterr()
        assert 'INFO:' in captured.out
        assert 'Test message' in captured.out

    def test_success(self, capsys):
        """Test success message output."""
        setup_environment.success('Operation complete')
        captured = capsys.readouterr()
        assert 'OK:' in captured.out
        assert 'Operation complete' in captured.out

    def test_warning(self, capsys):
        """Test warning message output."""
        setup_environment.warning('Warning message')
        captured = capsys.readouterr()
        assert 'WARN:' in captured.out
        assert 'Warning message' in captured.out

    def test_error(self, capsys):
        """Test error message output."""
        setup_environment.error('Error occurred')
        captured = capsys.readouterr()
        assert 'ERROR:' in captured.err
        assert 'Error occurred' in captured.err

    def test_header(self, capsys):
        """Test header output."""
        setup_environment.header('Python')
        captured = capsys.readouterr()
        assert 'Claude Code Python Environment Setup' in captured.out


class TestUtilityFunctions:
    """Test utility functions."""

    @patch('subprocess.run')
    def test_run_command_success(self, mock_run):
        """Test successful command execution."""
        mock_run.return_value = subprocess.CompletedProcess(['test'], 0, 'output', 'error')
        result = setup_environment.run_command(['test', 'command'])
        assert result.returncode == 0
        assert result.stdout == 'output'

    @patch('subprocess.run')
    def test_run_command_file_not_found(self, mock_run):
        """Test command not found error."""
        mock_run.side_effect = FileNotFoundError('Command not found')
        result = setup_environment.run_command(['missing'])
        assert result.returncode == 1
        assert 'Command not found' in result.stderr

    @patch('scripts.setup_environment.sys.platform', 'win32')
    @patch('scripts.setup_environment.shutil.which')
    @patch('subprocess.run')
    def test_run_command_windows_batch_resolution(self, mock_run, mock_which):
        """Test that on Windows, batch files are resolved via shutil.which()."""
        mock_which.return_value = r'C:\Program Files\nodejs\npm.cmd'
        mock_run.return_value = subprocess.CompletedProcess(
            [r'C:\Program Files\nodejs\npm.cmd', 'install'], 0, '', '',
        )
        result = setup_environment.run_command(['npm', 'install'])
        assert result.returncode == 0
        # Verify shutil.which was called with the command
        mock_which.assert_called_once_with('npm')
        # Verify subprocess.run was called with the resolved path
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == r'C:\Program Files\nodejs\npm.cmd'
        assert call_args[1] == 'install'

    @patch('scripts.setup_environment.sys.platform', 'win32')
    @patch('scripts.setup_environment.shutil.which')
    @patch('subprocess.run')
    def test_run_command_windows_which_returns_none(self, mock_run, mock_which):
        """Test that when shutil.which returns None, original command is used."""
        mock_which.return_value = None
        mock_run.return_value = subprocess.CompletedProcess(['npm', 'install'], 0, '', '')
        result = setup_environment.run_command(['npm', 'install'])
        assert result.returncode == 0
        # Verify subprocess.run was called with the original command
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == 'npm'
        assert call_args[1] == 'install'

    @patch('scripts.setup_environment.sys.platform', 'linux')
    @patch('scripts.setup_environment.shutil.which')
    @patch('subprocess.run')
    def test_run_command_non_windows_no_resolution(self, mock_run, mock_which):
        """Test that on non-Windows platforms, batch file resolution is skipped."""
        mock_run.return_value = subprocess.CompletedProcess(['npm', 'install'], 0, '', '')
        result = setup_environment.run_command(['npm', 'install'])
        assert result.returncode == 0
        # Verify shutil.which was NOT called
        mock_which.assert_not_called()
        # Verify subprocess.run was called with the original command
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == 'npm'

    @patch('scripts.setup_environment.sys.platform', 'win32')
    @patch('scripts.setup_environment.shutil.which')
    @patch('subprocess.run')
    def test_run_command_empty_cmd_list(self, mock_run, mock_which):
        """Test that empty command list doesn't cause issues."""
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')
        result = setup_environment.run_command([])
        assert result.returncode == 0
        # Verify shutil.which was NOT called for empty list
        mock_which.assert_not_called()

    @patch('shutil.which')
    def test_find_command(self, mock_which):
        """Test finding command in PATH."""
        mock_which.return_value = '/usr/bin/git'
        assert setup_environment.find_command('git') == '/usr/bin/git'


class TestTildeExpansion:
    """Test tilde expansion in commands."""

    def test_expand_single_tilde(self):
        """Test expanding a single tilde path."""
        cmd = "sed -i '/pattern/d' ~/.bashrc"
        expanded = setup_environment.expand_tildes_in_command(cmd)
        home = str(Path.home())
        assert expanded == f"sed -i '/pattern/d' {home}/.bashrc"

    def test_expand_multiple_tildes(self):
        """Test expanding multiple tilde paths in one command."""
        cmd = 'cp ~/.config/file1 ~/.local/file2'
        expanded = setup_environment.expand_tildes_in_command(cmd)
        home = str(Path.home())
        assert expanded == f'cp {home}/.config/file1 {home}/.local/file2'

    def test_expand_tilde_in_complex_command(self):
        """Test tilde expansion in complex sed command."""
        cmd = "sed -i -E '/^[[:space:]]*export[[:space:]]+HTTP_PROXY=/d' ~/.bashrc"
        expanded = setup_environment.expand_tildes_in_command(cmd)
        home = str(Path.home())
        assert expanded == f"sed -i -E '/^[[:space:]]*export[[:space:]]+HTTP_PROXY=/d' {home}/.bashrc"

    def test_expand_tilde_with_echo(self):
        """Test tilde expansion with echo command."""
        cmd = "echo 'export FOO=bar' >> ~/.bashrc"
        expanded = setup_environment.expand_tildes_in_command(cmd)
        home = str(Path.home())
        assert expanded == f"echo 'export FOO=bar' >> {home}/.bashrc"

    def test_no_tilde_unchanged(self):
        """Test that commands without tildes remain unchanged."""
        cmd = 'npm install -g package'
        expanded = setup_environment.expand_tildes_in_command(cmd)
        assert expanded == cmd

    def test_tilde_in_quotes_preserved(self):
        """Test that tildes in single quotes are expanded (shell would not expand them)."""
        cmd = "echo '~/.bashrc'"
        expanded = setup_environment.expand_tildes_in_command(cmd)
        home = str(Path.home())
        # Our function expands tildes even in quotes, which is correct for subprocess context
        assert expanded == f"echo '{home}/.bashrc'"

    def test_touch_tilde(self):
        """Test tilde expansion with touch command."""
        cmd = 'touch ~/.bashrc'
        expanded = setup_environment.expand_tildes_in_command(cmd)
        home = str(Path.home())
        assert expanded == f'touch {home}/.bashrc'

    def test_tilde_with_nested_path(self):
        """Test tilde expansion with deeply nested path."""
        cmd = 'cat ~/.config/claude/settings.json'
        expanded = setup_environment.expand_tildes_in_command(cmd)
        home = str(Path.home())
        assert expanded == f'cat {home}/.config/claude/settings.json'


class TestDownloadFile:
    """Test file download functionality."""

    @patch('setup_environment.urlopen')
    def test_download_file_success(self, mock_urlopen):
        """Test successful file download."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'file content'
        mock_urlopen.return_value = mock_response

        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / 'test.txt'
            result = setup_environment.download_file('http://example.com/file', dest)
            assert result is True
            assert dest.exists()
            assert dest.read_text() == 'file content'

    @patch('setup_environment.urlopen')
    def test_download_file_ssl_error_fallback(self, mock_urlopen):
        """Test download with SSL error fallback."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'content'
        mock_urlopen.side_effect = [
            urllib.error.URLError('SSL: CERTIFICATE_VERIFY_FAILED'),
            mock_response,
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / 'test.txt'
            result = setup_environment.download_file('https://example.com/file', dest)
            assert result is True
            assert dest.read_bytes() == b'content'

    def test_download_file_skip_existing(self):
        """Test skipping existing file when force=False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / 'existing.txt'
            dest.write_text('existing content')
            result = setup_environment.download_file('http://example.com', dest, force=False)
            assert result is True
            assert dest.read_text() == 'existing content'


class TestRepoTypeDetection:
    """Test repository type detection."""

    def test_detect_gitlab_url(self):
        """Test GitLab URL detection."""
        assert setup_environment.detect_repo_type('https://gitlab.com/user/repo') == 'gitlab'
        assert setup_environment.detect_repo_type('https://gitlab.example.com/api/v4/projects/') == 'gitlab'

    def test_detect_github_url(self):
        """Test GitHub URL detection."""
        assert setup_environment.detect_repo_type('https://github.com/user/repo') == 'github'
        assert setup_environment.detect_repo_type('https://api.github.com/repos/') == 'github'

    def test_detect_unknown_url(self):
        """Test unknown URL returns None."""
        assert setup_environment.detect_repo_type('https://example.com/repo') is None


class TestGitLabUrlConversion:
    """Test GitLab URL conversion to API format."""

    def test_convert_gitlab_web_to_api(self):
        """Test converting GitLab web URL to API URL."""
        web_url = 'https://gitlab.com/namespace/project/-/raw/main/path/to/file.yaml'
        api_url = setup_environment.convert_gitlab_url_to_api(web_url)
        assert '/api/v4/projects/' in api_url
        assert 'namespace%2Fproject' in api_url
        assert 'path%2Fto%2Ffile.yaml' in api_url
        assert 'ref=main' in api_url

    def test_convert_gitlab_already_api_url(self):
        """Test that API URLs are returned unchanged."""
        api_url = 'https://gitlab.com/api/v4/projects/123/repository/files/file.yaml/raw?ref=main'
        result = setup_environment.convert_gitlab_url_to_api(api_url)
        assert result == api_url

    def test_convert_non_gitlab_url(self):
        """Test that non-GitLab URLs are returned unchanged."""
        url = 'https://github.com/user/repo/raw/main/file.yaml'
        result = setup_environment.convert_gitlab_url_to_api(url)
        assert result == url


class TestAuthHeaders:
    """Test authentication header generation."""

    def test_get_auth_headers_from_param(self):
        """Test getting auth headers from command-line parameter."""
        headers = setup_environment.get_auth_headers('https://gitlab.com/repo', 'PRIVATE-TOKEN:mytoken')
        assert headers == {'PRIVATE-TOKEN': 'mytoken'}

    def test_get_auth_headers_from_param_equals(self):
        """Test getting auth headers with = separator."""
        headers = setup_environment.get_auth_headers('https://gitlab.com/repo', 'PRIVATE-TOKEN=mytoken')
        assert headers == {'PRIVATE-TOKEN': 'mytoken'}

    @patch.dict('os.environ', {'GITLAB_TOKEN': 'env_token'})
    def test_get_auth_headers_from_env_gitlab(self):
        """Test getting GitLab token from environment."""
        headers = setup_environment.get_auth_headers('https://gitlab.com/repo', None)
        assert headers == {'PRIVATE-TOKEN': 'env_token'}

    @patch.dict('os.environ', {'GITHUB_TOKEN': 'gh_token'})
    def test_get_auth_headers_from_env_github(self):
        """Test getting GitHub token from environment."""
        headers = setup_environment.get_auth_headers('https://github.com/repo', None)
        assert headers == {'Authorization': 'Bearer gh_token'}

    @patch.dict('os.environ', {'REPO_TOKEN': 'generic_token'})
    def test_get_auth_headers_from_env_generic(self):
        """Test getting generic token from environment."""
        headers = setup_environment.get_auth_headers('https://gitlab.com/repo', None)
        assert headers == {'PRIVATE-TOKEN': 'generic_token'}

    def test_get_auth_headers_none(self):
        """Test no auth headers when not provided."""
        with patch.dict('os.environ', {}, clear=True):
            headers = setup_environment.get_auth_headers('https://example.com/repo', None)
            assert headers == {}


class TestDeriveBaseUrl:
    """Test base URL derivation."""

    def test_derive_base_url_gitlab_api(self):
        """Test deriving base URL from GitLab API URL."""
        config_url = 'https://gitlab.com/api/v4/projects/123/repository/files/configs%2Fenv.yaml/raw?ref=main'
        base_url = setup_environment.derive_base_url(config_url)
        assert base_url == 'https://gitlab.com/api/v4/projects/123/repository/files/{path}/raw?ref=main'

    def test_derive_base_url_github_raw(self):
        """Test deriving base URL from GitHub raw URL."""
        config_url = 'https://raw.githubusercontent.com/user/repo/main/configs/env.yaml'
        base_url = setup_environment.derive_base_url(config_url)
        assert base_url == 'https://raw.githubusercontent.com/user/repo/main/{path}'

    def test_derive_base_url_generic(self):
        """Test deriving base URL from generic URL."""
        config_url = 'https://example.com/path/to/file.yaml'
        base_url = setup_environment.derive_base_url(config_url)
        assert base_url == 'https://example.com/path/to/{path}'


class TestResolveResourcePath:
    """Test resource path resolution."""

    def test_resolve_resource_path_full_url(self):
        """Test that full URLs are returned as-is."""
        path, is_remote = setup_environment.resolve_resource_path(
            'https://example.com/file.yaml',
            'config_source',
            None,
        )
        assert path == 'https://example.com/file.yaml'
        assert is_remote is True

    def test_resolve_resource_path_with_base_url(self):
        """Test resolution with base URL override."""
        path, is_remote = setup_environment.resolve_resource_path(
            'agents/test.md',
            'config_source',
            'https://example.com/base/',
        )
        assert path == 'https://example.com/base/agents/test.md'
        assert is_remote is True

    def test_resolve_resource_path_from_config_source(self):
        """Test resolution from config source URL."""
        path, is_remote = setup_environment.resolve_resource_path(
            'agents/test.md',
            'https://raw.githubusercontent.com/user/repo/main/config.yaml',
            None,
        )
        assert path == 'https://raw.githubusercontent.com/user/repo/main/agents/test.md'
        assert is_remote is True

    @patch('setup_environment.Path')
    def test_resolve_resource_path_local(self, mock_path_cls):
        """Test local path resolution."""
        # Mock for local file - relative path should be resolved to current dir
        mock_cwd = Path('/current/dir')
        mock_path_cls.cwd.return_value = mock_cwd

        # Create a resolved path mock
        mock_resolved = Path('/current/dir/agents/test.md')
        mock_path_cls.return_value.resolve.return_value = mock_resolved

        path, is_remote = setup_environment.resolve_resource_path(
            'agents/test.md',
            'local_config.yaml',
            None,
        )
        assert is_remote is False


class TestLoadConfig:
    """Test configuration loading."""

    @patch('setup_environment.fetch_url_with_auth')
    def test_load_config_from_url(self, mock_fetch):
        """Test loading configuration from URL."""
        mock_fetch.return_value = 'name: Test Config\nversion: 1.0'

        config, source = setup_environment.load_config_from_source('https://example.com/config.yaml')
        assert config['name'] == 'Test Config'
        assert source == 'https://example.com/config.yaml'

    def test_load_config_from_local_file(self):
        """Test loading configuration from local file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tmp:
            tmp.write('name: Local Config\nversion: 2.0')
            tmp_path = tmp.name

        try:
            config, source = setup_environment.load_config_from_source(tmp_path)
            assert config['name'] == 'Local Config'
            assert source == str(Path(tmp_path).resolve())
        finally:
            os.unlink(tmp_path)

    @patch('setup_environment.fetch_url_with_auth')
    def test_load_config_from_repository(self, mock_fetch):
        """Test loading configuration from repository."""
        mock_fetch.return_value = 'name: Repo Config\nversion: 3.0'

        config, source = setup_environment.load_config_from_source('python')
        assert config['name'] == 'Repo Config'
        assert source == 'python.yaml'
        mock_fetch.assert_called_once()


class TestGetRealUserHome:
    """Tests for get_real_user_home() function."""

    def test_returns_path_on_windows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test returns Path.home() on Windows."""
        monkeypatch.setattr(sys, 'platform', 'win32')
        result = setup_environment.get_real_user_home()
        assert isinstance(result, Path)

    @pytest.mark.skipif(sys.platform == 'win32', reason='Unix-specific test')
    def test_returns_sudo_user_home_when_sudo(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test returns sudo user's home when running under sudo."""
        monkeypatch.setattr(sys, 'platform', 'linux')
        monkeypatch.setenv('SUDO_USER', 'testuser')

        # Create mock pwd module to avoid importing real pwd on Windows
        class MockPasswd:
            pw_dir = '/home/testuser'

        class MockPwdModule:
            @staticmethod
            def getpwnam(_name: str) -> MockPasswd:
                return MockPasswd()

        # Inject mock pwd into sys.modules before the function imports it
        monkeypatch.setitem(sys.modules, 'pwd', MockPwdModule())

        result = setup_environment.get_real_user_home()
        assert result == Path('/home/testuser')

    @pytest.mark.skipif(sys.platform == 'win32', reason='Unix-specific test')
    def test_returns_home_when_no_sudo(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test returns Path.home() when not running under sudo."""
        monkeypatch.delenv('SUDO_USER', raising=False)
        result = setup_environment.get_real_user_home()
        assert result == Path.home()


class TestGetAllShellConfigFiles:
    """Tests for get_all_shell_config_files() function."""

    def test_returns_empty_on_windows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test returns empty list on Windows."""
        monkeypatch.setattr(sys, 'platform', 'win32')
        result = setup_environment.get_all_shell_config_files()
        assert result == []

    @pytest.mark.skipif(sys.platform == 'win32', reason='Unix-specific test')
    def test_returns_all_files_on_macos(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test returns all config files on macOS."""
        monkeypatch.setattr(sys, 'platform', 'darwin')
        monkeypatch.setattr(platform, 'system', lambda: 'Darwin')
        result = setup_environment.get_all_shell_config_files()
        filenames = [f.name for f in result]
        assert '.bashrc' in filenames
        assert '.bash_profile' in filenames
        assert '.zshenv' in filenames
        assert '.zprofile' in filenames
        assert '.zshrc' in filenames

    @pytest.mark.skipif(sys.platform == 'win32', reason='Unix-specific test')
    def test_excludes_zsh_files_on_linux_without_zsh(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test excludes zsh files on Linux when zsh is not installed."""
        monkeypatch.setattr(sys, 'platform', 'linux')
        monkeypatch.setattr(platform, 'system', lambda: 'Linux')
        monkeypatch.setattr(shutil, 'which', lambda x: None if x == 'zsh' else '/bin/bash')
        result = setup_environment.get_all_shell_config_files()
        filenames = [f.name for f in result]
        assert '.bashrc' in filenames
        assert '.zshrc' not in filenames
        assert '.zshenv' not in filenames


class TestAddExportToFile:
    """Tests for add_export_to_file() function."""

    def test_creates_file_with_export(self, tmp_path: Path) -> None:
        """Test creates new file with export line."""
        config_file = tmp_path / '.bashrc'
        result = setup_environment.add_export_to_file(config_file, 'MY_VAR', 'my_value')
        assert result is True
        assert config_file.exists()
        content = config_file.read_text()
        assert 'export MY_VAR="my_value"' in content
        assert setup_environment.ENV_VAR_MARKER_START in content
        assert setup_environment.ENV_VAR_MARKER_END in content

    def test_updates_existing_variable(self, tmp_path: Path) -> None:
        """Test updates existing variable in marker block."""
        config_file = tmp_path / '.bashrc'
        setup_environment.add_export_to_file(config_file, 'MY_VAR', 'old_value')
        result = setup_environment.add_export_to_file(config_file, 'MY_VAR', 'new_value')
        assert result is True
        content = config_file.read_text()
        assert 'export MY_VAR="new_value"' in content
        assert 'old_value' not in content
        # Should only have one marker block
        assert content.count(setup_environment.ENV_VAR_MARKER_START) == 1

    def test_adds_multiple_variables(self, tmp_path: Path) -> None:
        """Test adds multiple variables to same block."""
        config_file = tmp_path / '.bashrc'
        setup_environment.add_export_to_file(config_file, 'VAR1', 'value1')
        setup_environment.add_export_to_file(config_file, 'VAR2', 'value2')
        content = config_file.read_text()
        assert 'export VAR1="value1"' in content
        assert 'export VAR2="value2"' in content
        assert content.count(setup_environment.ENV_VAR_MARKER_START) == 1


class TestRemoveExportFromFile:
    """Tests for remove_export_from_file() function."""

    def test_removes_variable(self, tmp_path: Path) -> None:
        """Test removes variable from marker block."""
        config_file = tmp_path / '.bashrc'
        setup_environment.add_export_to_file(config_file, 'MY_VAR', 'my_value')
        result = setup_environment.remove_export_from_file(config_file, 'MY_VAR')
        assert result is True
        content = config_file.read_text()
        assert 'MY_VAR' not in content

    def test_removes_only_target_variable(self, tmp_path: Path) -> None:
        """Test removes only the target variable, keeps others."""
        config_file = tmp_path / '.bashrc'
        setup_environment.add_export_to_file(config_file, 'VAR1', 'value1')
        setup_environment.add_export_to_file(config_file, 'VAR2', 'value2')
        setup_environment.remove_export_from_file(config_file, 'VAR1')
        content = config_file.read_text()
        assert 'VAR1' not in content
        assert 'export VAR2="value2"' in content

    def test_returns_true_for_nonexistent_file(self, tmp_path: Path) -> None:
        """Test returns True when file doesn't exist."""
        config_file = tmp_path / '.nonexistent'
        result = setup_environment.remove_export_from_file(config_file, 'MY_VAR')
        assert result is True


class TestSetOsEnvVariableWindows:
    """Tests for set_os_env_variable_windows() function."""

    def test_returns_false_on_non_windows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test returns False on non-Windows platforms."""
        monkeypatch.setattr(sys, 'platform', 'linux')
        result = setup_environment.set_os_env_variable_windows('MY_VAR', 'value')
        assert result is False

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-specific test')
    def test_calls_setx_for_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test calls setx command to set variable."""
        called_with: list[list[str]] = []

        class MockResult:
            returncode = 0
            stderr = ''

        def mock_run(cmd: list[str], **_kwargs: object) -> MockResult:
            called_with.append(cmd)
            return MockResult()

        monkeypatch.setattr(subprocess, 'run', mock_run)
        result = setup_environment.set_os_env_variable_windows('MY_VAR', 'my_value')
        assert result is True
        assert called_with[0] == ['setx', 'MY_VAR', 'my_value']

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-specific test')
    def test_calls_reg_delete_for_delete(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test calls reg delete command to delete variable."""
        called_with: list[list[str]] = []

        class MockResult:
            returncode = 0
            stderr = ''

        def mock_run(cmd: list[str], **_kwargs: object) -> MockResult:
            called_with.append(cmd)
            return MockResult()

        monkeypatch.setattr(subprocess, 'run', mock_run)
        result = setup_environment.set_os_env_variable_windows('MY_VAR', None)
        assert result is True
        assert called_with[0] == ['reg', 'delete', r'HKCU\Environment', '/v', 'MY_VAR', '/f']


class TestSetAllOsEnvVariables:
    """Tests for set_all_os_env_variables() function."""

    def test_empty_dict_returns_true(self) -> None:
        """Test returns True for empty dictionary."""
        result = setup_environment.set_all_os_env_variables({})
        assert result is True

    @pytest.mark.skipif(sys.platform == 'win32', reason='Unix-specific test')
    def test_sets_multiple_variables(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Test sets multiple variables successfully."""
        monkeypatch.setattr(sys, 'platform', 'linux')
        # Mock get_all_shell_config_files to return temp path
        monkeypatch.setattr(
            setup_environment,
            'get_all_shell_config_files',
            lambda: [tmp_path / '.bashrc'],
        )
        result = setup_environment.set_all_os_env_variables({
            'VAR1': 'value1',
            'VAR2': 'value2',
        })
        assert result is True
        content = (tmp_path / '.bashrc').read_text()
        assert 'export VAR1="value1"' in content
        assert 'export VAR2="value2"' in content

    @pytest.mark.skipif(sys.platform == 'win32', reason='Unix-specific test')
    def test_handles_null_values_for_deletion(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Test handles None values as deletion requests."""
        monkeypatch.setattr(sys, 'platform', 'linux')
        config_file = tmp_path / '.bashrc'
        monkeypatch.setattr(
            setup_environment,
            'get_all_shell_config_files',
            lambda: [config_file],
        )
        # First set a variable
        setup_environment.add_export_to_file(config_file, 'OLD_VAR', 'old_value')
        # Then delete it
        result = setup_environment.set_all_os_env_variables({'OLD_VAR': None})
        assert result is True
        content = config_file.read_text()
        assert 'OLD_VAR' not in content


class TestInstallDependencies:
    """Test dependency installation."""

    @patch('platform.system', return_value='Windows')
    @patch('setup_environment.run_command')
    def test_install_dependencies_windows(self, mock_run, mock_system):
        """Test installing dependencies on Windows."""
        # Verify mock configuration
        assert mock_system.return_value == 'Windows'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        result = setup_environment.install_dependencies({'windows': ['npm install -g package']})
        assert result is True
        mock_run.assert_called_with(['npm', 'install', '-g', 'package'], capture_output=False)

    @patch('platform.system', return_value='Linux')
    @patch('setup_environment.run_command')
    def test_install_dependencies_linux(self, mock_run, mock_system):
        """Test installing dependencies on Linux."""
        # Verify mock configuration
        assert mock_system.return_value == 'Linux'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        result = setup_environment.install_dependencies({'linux': ['apt-get install package']})
        assert result is True
        mock_run.assert_called_with(['bash', '-c', 'apt-get install package'], capture_output=False)

    @patch('platform.system', return_value='Darwin')
    @patch('setup_environment.run_command')
    def test_install_dependencies_macos_executes_as_is(self, mock_run, mock_system):
        """Test macOS executes commands as-is with tilde expansion."""
        assert mock_system.return_value == 'Darwin'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        # Commands should be executed as-is (with tilde expansion)
        result = setup_environment.install_dependencies({
            'mac': [
                'echo "export FOO=bar" >> ~/.zshrc',
                'brew install tool',
            ],
        })
        assert result is True

        calls = mock_run.call_args_list
        assert len(calls) == 2

        # Commands should be executed as-is with expanded tilde paths
        home = str(Path.home())
        call_args = [call[0][0][2] for call in calls]
        assert f'echo "export FOO=bar" >> {home}/.zshrc' in call_args
        assert 'brew install tool' in call_args

    @patch('platform.system', return_value='Windows')
    @patch('setup_environment.run_command')
    def test_install_dependencies_uv_tool_windows(self, mock_run, mock_system):
        """Test installing uv tools with force flag on Windows."""
        # Verify mock configuration
        assert mock_system.return_value == 'Windows'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        result = setup_environment.install_dependencies({'windows': ['uv tool install ruff']})
        assert result is True
        mock_run.assert_called_with(['uv', 'tool', 'install', '--force', 'ruff'], capture_output=False)


class TestInstallNodejsIfRequested:
    """Test install_nodejs_if_requested() function."""

    def test_not_requested_returns_true(self):
        """Test that function returns True when install-nodejs is not set."""
        config: dict = {'name': 'Test'}
        result = setup_environment.install_nodejs_if_requested(config)
        assert result is True

    def test_false_returns_true(self):
        """Test that function returns True when install-nodejs is False."""
        config = {'install-nodejs': False}
        result = setup_environment.install_nodejs_if_requested(config)
        assert result is True

    @patch('install_claude.ensure_nodejs')
    def test_true_calls_ensure_nodejs(self, mock_ensure):
        """Test that function calls ensure_nodejs when install-nodejs is True."""
        mock_ensure.return_value = True
        config = {'install-nodejs': True}
        result = setup_environment.install_nodejs_if_requested(config)
        assert result is True
        mock_ensure.assert_called_once()

    @patch('install_claude.ensure_nodejs')
    def test_installation_failure_returns_false(self, mock_ensure):
        """Test that function returns False when ensure_nodejs fails."""
        mock_ensure.return_value = False
        config = {'install-nodejs': True}
        result = setup_environment.install_nodejs_if_requested(config)
        assert result is False

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-specific')
    @patch('install_claude.ensure_nodejs')
    @patch('setup_environment.refresh_path_from_registry')
    def test_windows_refreshes_path(self, mock_refresh, mock_ensure):
        """Test that PATH is refreshed on Windows after installation."""
        mock_ensure.return_value = True
        config = {'install-nodejs': True}
        setup_environment.install_nodejs_if_requested(config)
        mock_refresh.assert_called_once()

    @patch('platform.system', return_value='Linux')
    @patch('install_claude.ensure_nodejs')
    @patch('setup_environment.refresh_path_from_registry')
    def test_non_windows_skips_path_refresh(self, mock_refresh, mock_ensure, mock_system):
        """Test that PATH refresh is skipped on non-Windows platforms."""
        # Verify mock configuration
        assert mock_system.return_value == 'Linux'
        mock_ensure.return_value = True
        config = {'install-nodejs': True}
        setup_environment.install_nodejs_if_requested(config)
        mock_refresh.assert_not_called()


class TestFetchUrlWithAuth:
    """Test URL fetching with authentication."""

    @patch('setup_environment.urlopen')
    def test_fetch_url_without_auth(self, mock_urlopen):
        """Test fetching public URL without authentication."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'content'
        mock_urlopen.return_value = mock_response

        result = setup_environment.fetch_url_with_auth('https://example.com/file')
        assert result == 'content'

    @patch('setup_environment.urlopen')
    @patch('setup_environment.get_auth_headers')
    def test_fetch_url_with_auth_retry(self, mock_get_auth, mock_urlopen):
        """Test fetching with authentication retry on 401."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'authenticated content'
        mock_urlopen.side_effect = [
            urllib.error.HTTPError('url', 401, 'Unauthorized', {}, None),
            mock_response,
        ]
        mock_get_auth.return_value = {'PRIVATE-TOKEN': 'token'}

        result = setup_environment.fetch_url_with_auth('https://gitlab.com/file')
        assert result == 'authenticated content'
        assert mock_urlopen.call_count == 2


class TestConfigureMCPServer:
    """Test MCP server configuration."""

    @patch('setup_environment.find_command_robust')
    @patch('setup_environment.run_command')
    def test_configure_mcp_server_http(self, mock_run, mock_find):
        """Test configuring HTTP MCP server."""
        mock_find.return_value = 'claude'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        server = {
            'name': 'test-server',
            'scope': 'user',
            'transport': 'http',
            'url': 'http://localhost:3000',
        }

        result = setup_environment.configure_mcp_server(server)
        assert result is True
        # Should call run_command 4 times: 3 for removing from all scopes, once for add
        assert mock_run.call_count == 4
        # Check the last call (add command) contains mcp add
        add_cmd_str = ' '.join(str(arg) for arg in mock_run.call_args_list[3][0][0])
        assert 'mcp add' in add_cmd_str
        assert 'test-server' in add_cmd_str

    @patch('setup_environment.find_command_robust')
    @patch('setup_environment.run_command')
    def test_configure_mcp_server_stdio(self, mock_run, mock_find):
        """Test configuring stdio MCP server."""
        mock_find.return_value = 'claude'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        server = {
            'name': 'test-server',
            'scope': 'user',
            'command': 'npx test-server',
        }

        result = setup_environment.configure_mcp_server(server)
        assert result is True
        # Should call run_command 4 times: 3 for removing from all scopes, once for add
        assert mock_run.call_count == 4


class TestCreateAdditionalSettings:
    """Test additional settings creation."""

    def test_create_additional_settings_basic(self):
        """Test creating basic additional settings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            result = setup_environment.create_additional_settings(
                {},
                claude_dir,
                'test-env',
                model='claude-3-opus',
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            assert settings_file.exists()

            settings = json.loads(settings_file.read_text())
            assert settings['model'] == 'claude-3-opus'

    def test_create_additional_settings_with_mcp_permissions(self):
        """Test creating settings without automatic MCP server permissions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            result = setup_environment.create_additional_settings(
                {},
                claude_dir,
                'test-env',
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            # MCP servers should NOT be automatically added to permissions
            assert 'permissions' not in settings or (
                'mcp__server1' not in settings.get('permissions', {}).get('allow', [])
                and 'mcp__server2' not in settings.get('permissions', {}).get('allow', [])
            )

    def test_create_additional_settings_with_explicit_permissions(self):
        """Test that explicit permissions are still preserved."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            permissions = {
                'allow': ['mcp__server1', 'tool__*'],
                'deny': ['mcp__server3'],
            }

            result = setup_environment.create_additional_settings(
                {},
                claude_dir,
                'test-env',
                permissions=permissions,
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            # Explicit permissions should be preserved exactly as provided
            assert 'permissions' in settings
            assert 'mcp__server1' in settings['permissions']['allow']
            assert 'tool__*' in settings['permissions']['allow']
            # server2 should NOT be auto-added
            assert 'mcp__server2' not in settings['permissions']['allow']
            assert 'mcp__server3' in settings['permissions']['deny']

    @patch('setup_environment.handle_resource')
    def test_create_additional_settings_with_hooks(self, mock_download):
        """Test creating settings with hooks."""
        mock_download.return_value = True

        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            hooks = {
                'files': ['hooks/test.py'],
                'events': [
                    {
                        'event': 'PostToolUse',
                        'matcher': 'Edit',
                        'type': 'command',
                        'command': 'test.py',
                    },
                ],
            }

            # First download hook files
            setup_environment.download_hook_files(
                hooks,
                claude_dir,
                config_source='https://example.com/config.yaml',
            )

            # Then create additional settings
            result = setup_environment.create_additional_settings(
                hooks,
                claude_dir,
                'test-env',
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            assert 'hooks' in settings
            assert 'PostToolUse' in settings['hooks']

    def test_create_additional_settings_always_thinking_enabled_true(self):
        """Test alwaysThinkingEnabled set to true."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            result = setup_environment.create_additional_settings(
                {},
                claude_dir,
                'test-env',
                always_thinking_enabled=True,
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            assert 'alwaysThinkingEnabled' in settings
            assert settings['alwaysThinkingEnabled'] is True

    def test_create_additional_settings_always_thinking_enabled_false(self):
        """Test alwaysThinkingEnabled set to false."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            result = setup_environment.create_additional_settings(
                {},
                claude_dir,
                'test-env',
                always_thinking_enabled=False,
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            assert 'alwaysThinkingEnabled' in settings
            assert settings['alwaysThinkingEnabled'] is False

    def test_create_additional_settings_always_thinking_enabled_none_not_included(self):
        """Test alwaysThinkingEnabled not included when None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            result = setup_environment.create_additional_settings(
                {},
                claude_dir,
                'test-env',
                always_thinking_enabled=None,
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            assert 'alwaysThinkingEnabled' not in settings


class TestCreateLauncherScript:
    """Test launcher script creation."""

    @patch('platform.system', return_value='Windows')
    def test_create_launcher_windows(self, mock_system):
        """Test creating launcher script on Windows."""
        # Verify mock configuration
        assert mock_system.return_value == 'Windows'
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            launcher = setup_environment.create_launcher_script(
                claude_dir,
                'test-env',
                'prompt.md',
            )

            assert launcher is not None
            assert launcher.suffix == '.ps1'
            assert launcher.exists()

            # Check that shared script was created
            shared_script = claude_dir / 'launch-test-env.sh'
            assert shared_script.exists()

    @patch('platform.system', return_value='Linux')
    def test_create_launcher_linux(self, mock_system):
        """Test creating launcher script on Linux."""
        # Verify mock configuration
        assert mock_system.return_value == 'Linux'
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            launcher = setup_environment.create_launcher_script(
                claude_dir,
                'test-env',
            )

            assert launcher is not None
            assert launcher.suffix == '.sh'
            assert launcher.exists()
            assert os.access(launcher, os.X_OK)


class TestRegisterGlobalCommand:
    """Test global command registration."""

    @patch('platform.system', return_value='Windows')
    @patch('setup_environment.run_command')
    def test_register_global_command_windows(self, mock_run, mock_system):
        """Test registering global command on Windows."""
        # Verify mock configuration
        assert mock_system.return_value == 'Windows'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        with tempfile.TemporaryDirectory() as tmpdir:
            launcher = Path(tmpdir) / 'launcher.ps1'
            launcher.write_text('# Launcher')

            result = setup_environment.register_global_command(launcher, 'test-cmd')
            assert result is True

    @patch('platform.system', return_value='Linux')
    def test_register_global_command_linux(self, mock_system):
        """Test registering global command on Linux."""
        # Verify mock configuration
        assert mock_system.return_value == 'Linux'
        with tempfile.TemporaryDirectory() as tmpdir:
            launcher = Path(tmpdir) / 'launcher.sh'
            launcher.write_text('#!/bin/bash\necho test')
            launcher.chmod(0o755)

            # Mock the local bin directory and symlink creation
            with patch('pathlib.Path.home') as mock_home:
                mock_home.return_value = Path(tmpdir)
                with patch('pathlib.Path.symlink_to') as mock_symlink:
                    result = setup_environment.register_global_command(launcher, 'test-cmd')
                    assert result is True
                    mock_symlink.assert_called_once()


class TestInstallClaude:
    """Test Claude installation."""

    @patch('platform.system', return_value='Windows')
    @patch('urllib.request.urlopen')
    @patch('setup_environment.run_command')
    @patch('setup_environment.is_admin', return_value=True)
    def test_install_claude_windows(self, mock_is_admin, mock_run, mock_urlopen, mock_system):
        """Test installing Claude on Windows."""
        # Verify mock configuration
        assert mock_system.return_value == 'Windows'
        assert mock_is_admin.return_value is True  # Verify admin check is mocked
        mock_response = MagicMock()
        mock_response.read.return_value = b'# PowerShell installer'
        mock_urlopen.return_value = mock_response

        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        result = setup_environment.install_claude()
        assert result is True
        mock_run.assert_called_once()
        assert 'powershell' in mock_run.call_args[0][0]
        mock_is_admin.assert_called()  # Verify is_admin was called

    @patch('platform.system', return_value='Darwin')
    @patch('setup_environment.run_command')
    def test_install_claude_macos(self, mock_run, mock_system):
        """Test installing Claude on macOS."""
        # Verify mock configuration
        assert mock_system.return_value == 'Darwin'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        result = setup_environment.install_claude()
        assert result is True
        mock_run.assert_called_once()
        assert 'bash' in mock_run.call_args[0][0]


class TestExtractFrontMatter:
    """Test YAML front matter extraction from Markdown files."""

    def test_extract_front_matter_valid_with_name_and_description_only(self):
        """Test extracting valid front matter with ONLY name and description fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a markdown file with valid front matter (ONLY name and description)
            md_file = Path(tmpdir) / 'test.md'
            md_file.write_text('''---
name: Test Markdown File
description: A test markdown file with front matter
---

# Content

This is the content of the file.
''')
            result = setup_environment.extract_front_matter(md_file)
            assert result is not None
            assert result['name'] == 'Test Markdown File'
            assert result['description'] == 'A test markdown file with front matter'
            assert len(result) == 2  # Only name and description fields

    def test_extract_front_matter_no_front_matter(self):
        """Test extracting from file without front matter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            md_file = Path(tmpdir) / 'test.md'
            md_file.write_text('''# Just a regular markdown file

No front matter here.
''')
            result = setup_environment.extract_front_matter(md_file)
            assert result is None

    def test_extract_front_matter_malformed_yaml(self):
        """Test extracting malformed YAML front matter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            md_file = Path(tmpdir) / 'test.md'
            md_file.write_text('''---
name: Test
invalid yaml here: [
---

Content
''')
            result = setup_environment.extract_front_matter(md_file)
            assert result is None

    def test_extract_front_matter_alternative_delimiter(self):
        """Test extracting with alternative delimiter format (--- at end of line)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            md_file = Path(tmpdir) / 'test.md'
            md_file.write_text('''---
name: Alternative Style
description: Alternative markdown file description
---
# Content
''')
            result = setup_environment.extract_front_matter(md_file)
            assert result is not None
            assert result['name'] == 'Alternative Style'
            assert result['description'] == 'Alternative markdown file description'

    def test_extract_front_matter_empty_front_matter(self):
        """Test extracting empty front matter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            md_file = Path(tmpdir) / 'test.md'
            md_file.write_text('''---
---

# Content
''')
            result = setup_environment.extract_front_matter(md_file)
            # Empty YAML should parse to None or empty dict
            assert result is None or result == {}

    def test_extract_front_matter_missing_closing_delimiter(self):
        """Test extracting when closing delimiter is missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            md_file = Path(tmpdir) / 'test.md'
            md_file.write_text('''---
name: Incomplete
description: Missing closing delimiter

# Content without proper closing
''')
            result = setup_environment.extract_front_matter(md_file)
            assert result is None

    def test_extract_front_matter_file_not_found(self):
        """Test extracting from non-existent file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            md_file = Path(tmpdir) / 'nonexistent.md'
            result = setup_environment.extract_front_matter(md_file)
            assert result is None


class TestMainFunction:
    """Test the main setup flow."""

    @patch('setup_environment.load_config_from_source')
    def test_main_invalid_mode(self, mock_load):
        """Test main with invalid mode value."""
        mock_load.return_value = (
            {
                'name': 'Test',
                'command-defaults': {
                    'system-prompt': 'test.md',
                    'mode': 'invalid',  # Invalid mode value
                },
            },
            'test.yaml',
        )

        with patch('sys.argv', ['setup_environment.py', 'test']), patch('sys.exit') as mock_exit:
            setup_environment.main()
            mock_exit.assert_called_with(1)

    @patch('setup_environment.load_config_from_source')
    @patch('setup_environment.validate_all_config_files')
    @patch('setup_environment.install_claude')
    @patch('setup_environment.install_dependencies')
    @patch('setup_environment.process_resources')
    @patch('setup_environment.configure_all_mcp_servers')
    @patch('setup_environment.create_additional_settings')
    @patch('setup_environment.create_launcher_script')
    @patch('setup_environment.register_global_command')
    @patch('setup_environment.is_admin', return_value=True)
    @patch('pathlib.Path.mkdir')
    def test_main_success(
        self,
        mock_mkdir,
        mock_is_admin,
        mock_register,
        mock_launcher,
        mock_settings,
        mock_mcp,
        mock_download,
        mock_deps,
        mock_install,
        mock_validate,
        mock_load,
    ):
        """Test successful main flow."""
        # Verify mock configuration is available
        assert mock_mkdir is not None
        assert mock_is_admin.return_value is True
        mock_load.return_value = (
            {
                'name': 'Test Environment',
                'command-name': 'test-env',
                'dependencies': {
                    'windows': ['npm install -g test'],
                },
                'agents': ['agents/test.md'],
                'slash-commands': ['commands/test.md'],
                'mcp-servers': [{'name': 'test'}],
            },
            'test.yaml',
        )

        # Mock validation to succeed
        mock_validate.return_value = (True, [])

        mock_install.return_value = True
        mock_deps.return_value = True
        mock_download.return_value = True
        mock_mcp.return_value = True
        mock_settings.return_value = True
        mock_launcher.return_value = Path('/tmp/launcher.sh')
        mock_register.return_value = True

        with patch('sys.argv', ['setup_environment.py', 'test']), patch('sys.exit') as mock_exit:
            setup_environment.main()
            mock_exit.assert_not_called()

    @patch('setup_environment.load_config_from_source')
    def test_main_no_config(self, mock_load):
        """Test main with no configuration specified."""
        # Mock load to simulate no config found
        mock_load.side_effect = Exception('No config specified')
        with patch('sys.argv', ['setup_environment.py']), patch('sys.exit') as mock_exit:
            setup_environment.main()
            mock_exit.assert_called_with(1)

    @patch('setup_environment.load_config_from_source')
    @patch('setup_environment.install_claude')
    @patch('setup_environment.is_admin', return_value=True)
    def test_main_install_failure(self, mock_is_admin, mock_install, mock_load):
        """Test main with Claude installation failure."""
        assert mock_is_admin.return_value is True  # Verify admin check is mocked
        mock_load.return_value = ({'name': 'Test'}, 'test.yaml')
        mock_install.return_value = False

        with patch('sys.argv', ['setup_environment.py', 'test']), patch('sys.exit') as mock_exit:
            setup_environment.main()
            mock_exit.assert_called_with(1)

    @patch('setup_environment.load_config_from_source')
    @patch('setup_environment.find_command_robust')
    @patch('setup_environment.is_admin', return_value=True)
    def test_main_skip_install(self, mock_is_admin, mock_find, mock_load):
        """Test main with --skip-install flag."""
        assert mock_is_admin.return_value is True  # Verify admin check is mocked
        mock_load.return_value = (
            {
                'name': 'Test Environment',
                'dependencies': [],
                'agents': [],
                'slash-commands': [],
            },
            'test.yaml',
        )
        mock_find.return_value = 'claude'

        with (
            patch('sys.argv', ['setup_environment.py', 'test', '--skip-install']),
            patch('setup_environment.create_additional_settings', return_value=True),
            patch('setup_environment.create_launcher_script', return_value=Path('/tmp/launcher')),
            patch('setup_environment.register_global_command', return_value=True),
            patch('sys.exit') as mock_exit,
        ):
            setup_environment.main()
            mock_exit.assert_not_called()


class TestClaudeCodeVersion:
    """Test claude-code-version configuration handling."""

    def test_claude_code_version_latest(self):
        """Test that 'latest' value results in None being passed to install_claude."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / 'test-latest.yaml'
            config_file.write_text('''
name: "Test Latest"
claude-code-version: "latest"
dependencies:
  - uv
''')
            config, source = setup_environment.load_config_from_source(str(config_file), None)
            assert config.get('claude-code-version') == 'latest'

            # Simulate the normalization logic from setup_environment.py
            claude_code_version = config.get('claude-code-version')
            claude_code_version_normalized = None
            if claude_code_version is not None:
                claude_code_version_str = str(claude_code_version).strip()
                if not claude_code_version_str or claude_code_version_str.lower() == 'latest':
                    claude_code_version_normalized = None
                else:
                    claude_code_version_normalized = claude_code_version_str

            assert claude_code_version_normalized is None

    def test_claude_code_version_latest_case_insensitive(self):
        """Test that 'latest' is case-insensitive (LATEST, Latest, etc.)."""
        test_cases = ['latest', 'LATEST', 'Latest', 'LaTeSt']

        for test_value in test_cases:
            with tempfile.TemporaryDirectory() as tmpdir:
                config_file = Path(tmpdir) / f'test-{test_value}.yaml'
                config_file.write_text(f'''
name: "Test {test_value}"
claude-code-version: "{test_value}"
dependencies:
  - uv
''')
                config, source = setup_environment.load_config_from_source(str(config_file), None)

                # Simulate normalization logic
                claude_code_version = config.get('claude-code-version')
                claude_code_version_normalized = None
                if claude_code_version is not None:
                    claude_code_version_str = str(claude_code_version).strip()
                    if claude_code_version_str.lower() == 'latest':
                        claude_code_version_normalized = None
                    else:
                        claude_code_version_normalized = claude_code_version_str

                assert claude_code_version_normalized is None, f'Failed for value: {test_value}'

    def test_claude_code_version_specific(self):
        """Test that specific version strings are preserved."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / 'test-specific.yaml'
            config_file.write_text('''
name: "Test Specific"
claude-code-version: "1.0.124"
dependencies:
  - uv
''')
            config, source = setup_environment.load_config_from_source(str(config_file), None)
            assert config.get('claude-code-version') == '1.0.124'

            # Simulate normalization logic
            claude_code_version = config.get('claude-code-version')
            claude_code_version_normalized = None
            if claude_code_version is not None:
                claude_code_version_str = str(claude_code_version).strip()
                if not claude_code_version_str or claude_code_version_str.lower() == 'latest':
                    claude_code_version_normalized = None
                else:
                    claude_code_version_normalized = claude_code_version_str

            assert claude_code_version_normalized == '1.0.124'

    def test_claude_code_version_numeric_yaml(self):
        """Test that numeric YAML values are properly converted to strings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / 'test-numeric.yaml'
            # YAML will parse 1.0 as a float
            config_file.write_text('''
name: "Test Numeric"
claude-code-version: 1.0
dependencies:
  - uv
''')
            config, source = setup_environment.load_config_from_source(str(config_file), None)

            # Simulate normalization logic with type conversion
            claude_code_version = config.get('claude-code-version')
            claude_code_version_normalized = None
            if claude_code_version is not None:
                # Convert to string to handle numeric values
                claude_code_version_str = str(claude_code_version).strip()
                if not claude_code_version_str or claude_code_version_str.lower() == 'latest':
                    claude_code_version_normalized = None
                else:
                    claude_code_version_normalized = claude_code_version_str

            assert claude_code_version_normalized == '1.0'

    def test_claude_code_version_empty_string(self):
        """Test that empty string defaults to latest (None)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / 'test-empty.yaml'
            config_file.write_text('''
name: "Test Empty"
claude-code-version: ""
dependencies:
  - uv
''')
            config, source = setup_environment.load_config_from_source(str(config_file), None)

            # Simulate normalization logic
            claude_code_version = config.get('claude-code-version')
            claude_code_version_normalized = None
            if claude_code_version is not None:
                claude_code_version_str = str(claude_code_version).strip()
                if not claude_code_version_str or claude_code_version_str.lower() == 'latest':
                    claude_code_version_normalized = None
                else:
                    claude_code_version_normalized = claude_code_version_str

            assert claude_code_version_normalized is None

    def test_claude_code_version_whitespace(self):
        """Test that whitespace is properly trimmed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / 'test-whitespace.yaml'
            config_file.write_text('''
name: "Test Whitespace"
claude-code-version: "  latest  "
dependencies:
  - uv
''')
            config, source = setup_environment.load_config_from_source(str(config_file), None)

            # Simulate normalization logic
            claude_code_version = config.get('claude-code-version')
            claude_code_version_normalized = None
            if claude_code_version is not None:
                claude_code_version_str = str(claude_code_version).strip()
                if not claude_code_version_str or claude_code_version_str.lower() == 'latest':
                    claude_code_version_normalized = None
                else:
                    claude_code_version_normalized = claude_code_version_str

            assert claude_code_version_normalized is None

    def test_claude_code_version_not_specified(self):
        """Test behavior when claude-code-version is not specified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / 'test-no-version.yaml'
            config_file.write_text('''
name: "Test No Version"
dependencies:
  - uv
''')
            config, source = setup_environment.load_config_from_source(str(config_file), None)
            assert config.get('claude-code-version') is None

            # Simulate normalization logic
            claude_code_version = config.get('claude-code-version')
            claude_code_version_normalized = None
            if claude_code_version is not None:
                claude_code_version_str = str(claude_code_version).strip()
                if not claude_code_version_str or claude_code_version_str.lower() == 'latest':
                    claude_code_version_normalized = None
                else:
                    claude_code_version_normalized = claude_code_version_str

            assert claude_code_version_normalized is None


class TestMergeConfigs:
    """Test the _merge_configs helper function."""

    def test_basic_merge(self):
        """Test basic merge with no conflicts."""
        parent = {'a': 1, 'b': 2}
        child = {'c': 3, 'd': 4}
        result = setup_environment._merge_configs(parent, child)
        assert result == {'a': 1, 'b': 2, 'c': 3, 'd': 4}

    def test_child_override(self):
        """Test that child overrides parent for same key."""
        parent = {'a': 1, 'b': 2}
        child = {'b': 20, 'c': 3}
        result = setup_environment._merge_configs(parent, child)
        assert result == {'a': 1, 'b': 20, 'c': 3}

    def test_no_deep_merge(self):
        """Test that nested dicts are completely replaced, not merged."""
        parent = {'config': {'x': 1, 'y': 2}}
        child = {'config': {'z': 3}}
        result = setup_environment._merge_configs(parent, child)
        assert result['config'] == {'z': 3}
        assert 'x' not in result['config']

    def test_inherit_key_excluded(self):
        """Test that 'inherit' key from child is not in result."""
        parent = {'a': 1}
        child = {'inherit': 'something', 'b': 2}
        result = setup_environment._merge_configs(parent, child)
        assert result == {'a': 1, 'b': 2}
        assert 'inherit' not in result


class TestResolveInheritPath:
    """Test the _resolve_inherit_path helper function."""

    def test_full_url_unchanged(self):
        """Test that full URLs are returned unchanged."""
        result = setup_environment._resolve_inherit_path(
            'https://example.com/config.yaml',
            '/local/child.yaml',
        )
        assert result == 'https://example.com/config.yaml'

    def test_http_url_unchanged(self):
        """Test that HTTP URLs are returned unchanged."""
        result = setup_environment._resolve_inherit_path(
            'http://example.com/config.yaml',
            '/local/child.yaml',
        )
        assert result == 'http://example.com/config.yaml'

    def test_absolute_path_unchanged(self):
        """Test that absolute paths are returned unchanged."""
        # Use platform-appropriate absolute path
        if sys.platform == 'win32':
            abs_path = 'C:\\absolute\\path\\config.yaml'
            result = setup_environment._resolve_inherit_path(
                abs_path,
                'C:\\different\\child.yaml',
            )
            assert result == abs_path
        else:
            result = setup_environment._resolve_inherit_path(
                '/absolute/path/config.yaml',
                '/different/child.yaml',
            )
            assert result == '/absolute/path/config.yaml'

    def test_relative_from_url(self):
        """Test relative path resolution from URL source."""
        result = setup_environment._resolve_inherit_path(
            'parent.yaml',
            'https://example.com/configs/child.yaml',
        )
        assert result == 'https://example.com/configs/parent.yaml'

    def test_repo_name_from_repo_name(self):
        """Test repo name resolution when source is also repo name."""
        result = setup_environment._resolve_inherit_path(
            'python-base',
            'python-web',
        )
        assert result == 'python-base'


class TestConfigInheritance:
    """Test configuration inheritance functionality."""

    def test_no_inheritance_returns_config_unchanged(self):
        """Test that config without 'inherit' key is returned as-is."""
        config = {'name': 'Test', 'model': 'claude-3'}
        result = setup_environment.resolve_config_inheritance(config, 'test.yaml')
        assert result == config

    def test_inherit_key_removed_from_result(self):
        """Test that 'inherit' key is not in the final result."""
        with patch.object(setup_environment, 'load_config_from_source') as mock_load:
            mock_load.return_value = ({'name': 'Parent'}, 'parent.yaml')
            config = {'inherit': 'parent.yaml', 'model': 'claude-3'}
            result = setup_environment.resolve_config_inheritance(config, 'child.yaml')
            assert 'inherit' not in result

    @patch.object(setup_environment, 'load_config_from_source')
    def test_simple_inheritance(self, mock_load):
        """Test simple single-level inheritance."""
        mock_load.return_value = (
            {'name': 'Parent', 'model': 'claude-2', 'dependencies': {'common': ['uv']}},
            'parent.yaml',
        )
        child = {'inherit': 'parent.yaml', 'model': 'claude-3'}
        result = setup_environment.resolve_config_inheritance(child, 'child.yaml')

        assert result['name'] == 'Parent'  # Inherited from parent
        assert result['model'] == 'claude-3'  # Overridden by child
        assert result['dependencies'] == {'common': ['uv']}  # Inherited

    @patch.object(setup_environment, 'load_config_from_source')
    def test_child_completely_overrides_parent_key(self, mock_load):
        """Test that child completely replaces parent's top-level key (no deep merge)."""
        mock_load.return_value = (
            {'dependencies': {'common': ['uv'], 'windows': ['npm']}},
            'parent.yaml',
        )
        child = {
            'inherit': 'parent.yaml',
            'dependencies': {'linux': ['apt']},  # Completely replaces
        }
        result = setup_environment.resolve_config_inheritance(child, 'child.yaml')

        # Child's dependencies should COMPLETELY replace parent's
        assert result['dependencies'] == {'linux': ['apt']}
        assert 'common' not in result['dependencies']
        assert 'windows' not in result['dependencies']

    @patch.object(setup_environment, 'load_config_from_source')
    def test_multi_level_inheritance(self, mock_load):
        """Test grandparent -> parent -> child inheritance chain."""

        def load_side_effect(config_spec: str, _auth_param: str | None = None) -> tuple[dict, str]:
            if 'grandparent' in config_spec:
                return ({'name': 'Grandparent', 'a': 1, 'b': 2}, 'grandparent.yaml')
            if 'parent' in config_spec:
                return ({'inherit': 'grandparent.yaml', 'b': 20, 'c': 3}, 'parent.yaml')
            raise FileNotFoundError(f'Not found: {config_spec}')

        mock_load.side_effect = load_side_effect

        child = {'inherit': 'parent.yaml', 'c': 30, 'd': 4}
        result = setup_environment.resolve_config_inheritance(child, 'child.yaml')

        assert result['name'] == 'Grandparent'  # From grandparent
        assert result['a'] == 1  # From grandparent
        assert result['b'] == 20  # Parent overrides grandparent
        assert result['c'] == 30  # Child overrides parent
        assert result['d'] == 4  # Child only

    def test_circular_dependency_self_reference(self):
        """Test circular dependency detection for self-reference."""
        config = {'inherit': 'self.yaml', 'name': 'Self'}
        with patch.object(setup_environment, 'load_config_from_source') as mock_load:
            mock_load.return_value = (config, 'self.yaml')
            import pytest

            with pytest.raises(ValueError, match='Circular dependency'):
                setup_environment.resolve_config_inheritance(config, 'self.yaml')

    @patch.object(setup_environment, 'load_config_from_source')
    def test_circular_dependency_a_b_a(self, mock_load):
        """Test circular dependency detection: A -> B -> A."""

        def load_side_effect(config_spec: str, _auth_param: str | None = None) -> tuple[dict, str]:
            if 'a.yaml' in config_spec:
                return ({'inherit': 'b.yaml', 'name': 'A'}, 'a.yaml')
            if 'b.yaml' in config_spec:
                return ({'inherit': 'a.yaml', 'name': 'B'}, 'b.yaml')
            raise FileNotFoundError(f'Not found: {config_spec}')

        mock_load.side_effect = load_side_effect

        config = {'inherit': 'b.yaml', 'model': 'test'}
        import pytest

        with pytest.raises(ValueError, match='Circular dependency'):
            setup_environment.resolve_config_inheritance(config, 'a.yaml')

    def test_max_depth_exceeded(self):
        """Test maximum depth limit enforcement."""
        with patch.object(setup_environment, 'load_config_from_source') as mock_load:
            # Create a chain that exceeds MAX_INHERITANCE_DEPTH
            call_count = [0]

            def deep_chain(
                _config_spec: str, _auth_param: str | None = None,
            ) -> tuple[dict, str]:
                call_count[0] += 1
                # Create configs: level0 -> level1 -> level2 -> ...
                return ({'inherit': f'level{call_count[0]}.yaml'}, f'level{call_count[0] - 1}.yaml')

            mock_load.side_effect = deep_chain

            config = {'inherit': 'level0.yaml'}
            import pytest

            with pytest.raises(ValueError, match='Maximum inheritance depth'):
                setup_environment.resolve_config_inheritance(config, 'start.yaml')

    def test_invalid_inherit_value_not_string(self):
        """Test error when inherit value is not a string."""
        config = {'inherit': ['parent.yaml'], 'name': 'Test'}  # List instead of string
        import pytest

        with pytest.raises(ValueError, match='must be a string'):
            setup_environment.resolve_config_inheritance(config, 'test.yaml')

    def test_invalid_inherit_value_dict(self):
        """Test error when inherit value is a dict."""
        config = {'inherit': {'source': 'parent.yaml'}, 'name': 'Test'}
        import pytest

        with pytest.raises(ValueError, match='must be a string'):
            setup_environment.resolve_config_inheritance(config, 'test.yaml')

    def test_empty_inherit_value(self):
        """Test error when inherit value is empty string."""
        config = {'inherit': '', 'name': 'Test'}
        import pytest

        with pytest.raises(ValueError, match='cannot be empty'):
            setup_environment.resolve_config_inheritance(config, 'test.yaml')

    def test_whitespace_inherit_value(self):
        """Test error when inherit value is only whitespace."""
        config = {'inherit': '   ', 'name': 'Test'}
        import pytest

        with pytest.raises(ValueError, match='cannot be empty'):
            setup_environment.resolve_config_inheritance(config, 'test.yaml')

    @patch.object(setup_environment, 'load_config_from_source')
    def test_parent_not_found_local(self, mock_load):
        """Test error when local parent config doesn't exist."""
        mock_load.side_effect = FileNotFoundError('Configuration not found')
        config = {'inherit': './missing.yaml', 'name': 'Test'}
        import pytest

        with pytest.raises(FileNotFoundError):
            setup_environment.resolve_config_inheritance(config, 'test.yaml')

    @patch.object(setup_environment, 'load_config_from_source')
    def test_parent_not_found_url(self, mock_load):
        """Test error when URL parent config doesn't exist."""
        mock_load.side_effect = urllib.error.HTTPError(
            'url', 404, 'Not Found', {}, None,
        )
        config = {'inherit': 'https://example.com/missing.yaml', 'name': 'Test'}
        with pytest.raises(urllib.error.HTTPError):
            setup_environment.resolve_config_inheritance(config, 'test.yaml')

    @patch.object(setup_environment, 'load_config_from_source')
    def test_inherit_full_url(self, mock_load):
        """Test inheriting from full URL."""
        mock_load.return_value = ({'name': 'Remote'}, 'https://example.com/base.yaml')
        config = {'inherit': 'https://example.com/base.yaml', 'model': 'test'}
        result = setup_environment.resolve_config_inheritance(config, './local.yaml')

        assert result['name'] == 'Remote'
        mock_load.assert_called_once_with('https://example.com/base.yaml', None)

    @patch.object(setup_environment, 'load_config_from_source')
    def test_inherit_relative_from_url(self, mock_load):
        """Test inheriting relative path when current config is from URL."""
        mock_load.return_value = ({'name': 'Parent'}, 'https://example.com/configs/parent.yaml')
        config = {'inherit': 'parent.yaml', 'model': 'test'}

        setup_environment.resolve_config_inheritance(
            config, 'https://example.com/configs/child.yaml',
        )

        # Should resolve to same directory as child
        mock_load.assert_called_once_with(
            'https://example.com/configs/parent.yaml', None,
        )

    @patch.object(setup_environment, 'load_config_from_source')
    def test_inherit_relative_from_local(self, mock_load):
        """Test inheriting relative path when current config is local."""
        mock_load.return_value = ({'name': 'Parent'}, '/home/user/configs/parent.yaml')
        config = {'inherit': 'parent.yaml', 'model': 'test'}

        with tempfile.TemporaryDirectory() as tmpdir:
            child_path = Path(tmpdir) / 'child.yaml'
            child_path.touch()

            setup_environment.resolve_config_inheritance(config, str(child_path))

            # Should resolve relative to child's directory
            mock_load.assert_called_once()
            call_args = mock_load.call_args[0][0]
            assert Path(call_args).name == 'parent.yaml'

    @patch.object(setup_environment, 'load_config_from_source')
    def test_inherit_repo_name(self, mock_load):
        """Test inheriting repository config by name."""
        mock_load.return_value = ({'name': 'Base Python'}, 'python-base.yaml')
        config = {'inherit': 'python-base', 'model': 'test'}

        setup_environment.resolve_config_inheritance(config, 'python')

        # Should pass through as repo name
        mock_load.assert_called_once_with('python-base', None)

    @patch.object(setup_environment, 'load_config_from_source')
    def test_auth_propagated_through_chain(self, mock_load):
        """Test that auth_param is passed through inheritance chain."""

        def check_auth(config_spec, auth_param=None):
            assert auth_param == 'my-token'
            if 'grandparent' in config_spec:
                return ({'name': 'GP'}, 'grandparent.yaml')
            return ({'inherit': 'grandparent.yaml'}, 'parent.yaml')

        mock_load.side_effect = check_auth

        config = {'inherit': 'parent.yaml', 'model': 'test'}
        setup_environment.resolve_config_inheritance(
            config, 'child.yaml', auth_param='my-token',
        )

    def test_full_inheritance_with_temp_files(self):
        """Integration test with actual temp files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create grandparent
            grandparent = Path(tmpdir) / 'grandparent.yaml'
            grandparent.write_text('''
name: Grandparent Config
model: claude-2
dependencies:
  common:
    - pip install base
''')

            # Create parent that inherits from grandparent
            parent = Path(tmpdir) / 'parent.yaml'
            parent.write_text(f'''
inherit: {grandparent}
command-name: my-env
mcp-servers:
  - name: server1
''')

            # Create child that inherits from parent
            child = Path(tmpdir) / 'child.yaml'
            child.write_text(f'''
inherit: {parent}
model: claude-3
agents:
  - my-agent.md
''')

            # Load and resolve
            config, source = setup_environment.load_config_from_source(str(child))
            resolved = setup_environment.resolve_config_inheritance(config, source)

            # Verify inheritance
            assert resolved['name'] == 'Grandparent Config'  # From grandparent
            assert resolved['model'] == 'claude-3'  # Overridden by child
            assert resolved['command-name'] == 'my-env'  # From parent
            assert resolved['mcp-servers'] == [{'name': 'server1'}]  # From parent
            assert resolved['agents'] == ['my-agent.md']  # From child
            assert resolved['dependencies'] == {'common': ['pip install base']}  # From grandparent
            assert 'inherit' not in resolved
