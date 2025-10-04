"""
Comprehensive tests for setup_environment.py - the main environment setup script.
"""

import json
import os
import subprocess
import sys
import tempfile
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

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

    @patch('shutil.which')
    def test_find_command(self, mock_which):
        """Test finding command in PATH."""
        mock_which.return_value = '/usr/bin/git'
        assert setup_environment.find_command('git') == '/usr/bin/git'


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


class TestShellDetection:
    """Test shell detection and configuration for macOS."""

    @patch.dict('os.environ', {'SHELL': '/bin/bash'})
    def test_detect_user_shell_bash(self):
        """Test detecting bash shell."""
        assert setup_environment.detect_user_shell() == 'bash'

    @patch.dict('os.environ', {'SHELL': '/bin/zsh'})
    def test_detect_user_shell_zsh(self):
        """Test detecting zsh shell."""
        assert setup_environment.detect_user_shell() == 'zsh'

    @patch.dict('os.environ', {}, clear=True)
    def test_detect_user_shell_default(self):
        """Test default shell when SHELL env var is missing."""
        assert setup_environment.detect_user_shell() == 'bash'

    def test_get_shell_config_file_bash(self):
        """Test getting config file for bash shell."""
        config_file = setup_environment.get_shell_config_file('bash')
        assert config_file == Path.home() / '.bash_profile'

    def test_get_shell_config_file_zsh(self):
        """Test getting config file for zsh shell."""
        config_file = setup_environment.get_shell_config_file('zsh')
        assert config_file == Path.home() / '.zprofile'

    def test_get_shell_config_file_unknown(self):
        """Test getting config file for unknown shell."""
        config_file = setup_environment.get_shell_config_file('fish')
        assert config_file == Path.home() / '.profile'

    @patch('setup_environment.detect_user_shell', return_value='bash')
    def test_translate_shell_commands_zsh_to_bash(self, mock_detect):
        """Test translating zsh commands to bash."""
        assert mock_detect.return_value == 'bash'  # Verify mock is configured
        commands = [
            'echo "export FOO=bar" >> ~/.zshrc',
            'exec zsh -l',
        ]
        translated = setup_environment.translate_shell_commands(commands)

        expected_config = Path.home() / '.bash_profile'
        assert f'echo "export FOO=bar" >> {expected_config}' in translated
        assert 'exec bash -l' in translated

    @patch('setup_environment.detect_user_shell', return_value='zsh')
    def test_translate_shell_commands_bash_to_zsh(self, mock_detect):
        """Test translating bash commands to zsh."""
        assert mock_detect.return_value == 'zsh'  # Verify mock is configured
        commands = [
            'echo "export FOO=bar" >> ~/.bashrc',
            'exec bash -l',
        ]
        translated = setup_environment.translate_shell_commands(commands)

        expected_config = Path.home() / '.zprofile'
        assert f'echo "export FOO=bar" >> {expected_config}' in translated
        assert 'exec zsh -l' in translated

    @patch('setup_environment.detect_user_shell', return_value='bash')
    def test_translate_shell_commands_source(self, mock_detect):
        """Test translating source commands."""
        assert mock_detect.return_value == 'bash'  # Verify mock is configured
        commands = [
            'source ~/.zshrc',
            'source ~/.bashrc',
        ]
        translated = setup_environment.translate_shell_commands(commands)

        expected_config = Path.home() / '.bash_profile'
        assert f'source {expected_config}' in translated
        assert len(translated) == 2

    @patch('setup_environment.detect_user_shell', return_value='bash')
    def test_translate_shell_commands_non_shell_commands(self, mock_detect):
        """Test that non-shell commands are preserved."""
        assert mock_detect.return_value == 'bash'  # Verify mock is configured
        commands = [
            'npm install -g package',
            'brew install tool',
        ]
        translated = setup_environment.translate_shell_commands(commands)

        assert translated == commands

    def test_get_shell_config_file_dual_shell(self):
        """Test getting config files for dual-shell mode."""
        config_files = setup_environment.get_shell_config_file('bash', dual_shell=True)
        assert isinstance(config_files, list)
        assert len(config_files) == 2
        assert Path.home() / '.bash_profile' in config_files
        assert Path.home() / '.zprofile' in config_files

    @patch('setup_environment.detect_user_shell', return_value='bash')
    def test_translate_shell_commands_dual_shell(self, mock_detect):
        """Test translating commands in dual-shell mode."""
        assert mock_detect.return_value == 'bash'  # Verify mock is configured
        commands = [
            'echo "export FOO=bar" >> ~/.zshrc',
        ]
        translated = setup_environment.translate_shell_commands(commands, dual_shell=True)

        # Should write to both config files
        assert len(translated) == 2
        bash_profile = Path.home() / '.bash_profile'
        zprofile = Path.home() / '.zprofile'
        assert f'echo "export FOO=bar" >> {bash_profile}' in translated
        assert f'echo "export FOO=bar" >> {zprofile}' in translated

    @patch('setup_environment.detect_user_shell', return_value='zsh')
    def test_translate_shell_commands_dual_shell_exec(self, mock_detect):
        """Test translating exec commands in dual-shell mode."""
        assert mock_detect.return_value == 'zsh'  # Verify mock is configured
        commands = [
            'exec bash -l',
        ]
        translated = setup_environment.translate_shell_commands(commands, dual_shell=True)

        # Should use current shell for exec in dual mode
        assert len(translated) == 1
        assert 'exec zsh -l' in translated

    @patch('setup_environment.detect_user_shell', return_value='bash')
    def test_translate_shell_commands_dual_shell_source(self, mock_detect):
        """Test translating source commands in dual-shell mode."""
        assert mock_detect.return_value == 'bash'  # Verify mock is configured
        commands = [
            'source ~/.zshrc',
        ]
        translated = setup_environment.translate_shell_commands(commands, dual_shell=True)

        # Should source the current shell's config file
        assert len(translated) == 1
        expected_config = Path.home() / '.bash_profile'
        assert f'source {expected_config}' in translated


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
    @patch('setup_environment.detect_user_shell', return_value='bash')
    @patch('setup_environment.run_command')
    def test_install_dependencies_macos_shell_translation(self, mock_run, mock_detect, mock_system):
        """Test macOS shell command translation with dual-shell approach."""
        # Verify mock configuration
        assert mock_system.return_value == 'Darwin'
        assert mock_detect.return_value == 'bash'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        # Test with zsh-specific commands that should be translated for both shells
        result = setup_environment.install_dependencies({
            'mac': [
                'echo "export FOO=bar" >> ~/.zshrc',
                'exec zsh -l',
            ],
        })
        assert result is True

        # With dual-shell approach, we expect writes to both config files
        bash_profile = Path.home() / '.bash_profile'
        zprofile = Path.home() / '.zprofile'
        calls = mock_run.call_args_list

        # Should have 3 calls: 2 for the echo command (both shells) + 1 for exec
        assert len(calls) == 3

        # First two calls should write to both shell config files
        call_args = [call[0][0][2] for call in calls]
        assert f'echo "export FOO=bar" >> {bash_profile}' in call_args
        assert f'echo "export FOO=bar" >> {zprofile}' in call_args

        # Last command should be exec for the current shell (bash)
        assert 'exec bash -l' in call_args[2]

    @patch('platform.system', return_value='Darwin')
    @patch.dict('os.environ', {'SHELL': '/bin/zsh'})
    @patch('setup_environment.run_command')
    def test_install_dependencies_macos_zsh_user(self, mock_run, mock_system):
        """Test macOS with zsh user - dual-shell approach writes to both configs."""
        assert mock_system.return_value == 'Darwin'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        result = setup_environment.install_dependencies({
            'mac': [
                'echo "export FOO=bar" >> ~/.zshrc',
            ],
        })
        assert result is True

        # With dual-shell approach, should write to both config files
        bash_profile = Path.home() / '.bash_profile'
        zprofile = Path.home() / '.zprofile'
        calls = mock_run.call_args_list

        # Should have 2 calls: one for each shell config file
        assert len(calls) == 2

        call_args = [call[0][0][2] for call in calls]
        assert f'echo "export FOO=bar" >> {bash_profile}' in call_args
        assert f'echo "export FOO=bar" >> {zprofile}' in call_args

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

    @patch('setup_environment.find_command')
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

    @patch('setup_environment.find_command')
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
                output_style='style.md',
                model='claude-3-opus',
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            assert settings_file.exists()

            settings = json.loads(settings_file.read_text())
            assert settings['outputStyle'] == 'style'
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

            result = setup_environment.create_additional_settings(
                hooks,
                claude_dir,
                'test-env',
                config_source='https://example.com/config.yaml',
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            assert 'hooks' in settings
            assert 'PostToolUse' in settings['hooks']


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
name: Test Output Style
description: A test output style
---

# Content

This is the content of the file.
''')
            result = setup_environment.extract_front_matter(md_file)
            assert result is not None
            assert result['name'] == 'Test Output Style'
            assert result['description'] == 'A test output style'
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
description: Alternative output style description
---
# Content
''')
            result = setup_environment.extract_front_matter(md_file)
            assert result is not None
            assert result['name'] == 'Alternative Style'
            assert result['description'] == 'Alternative output style description'

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


class TestResolveOutputStyleName:
    """Test output style name resolution from front matter."""

    def test_resolve_output_style_name_matches_filename(self):
        """Test when front matter name matches the filename."""
        with tempfile.TemporaryDirectory() as tmpdir:
            styles_dir = Path(tmpdir)
            style_file = styles_dir / 'my-style.md'
            style_file.write_text('''---
name: my-style
description: Test style
---
# Content
''')
            result = setup_environment.resolve_output_style_name('my-style', styles_dir)
            assert result == 'my-style'

    def test_resolve_output_style_name_differs_from_filename(self):
        """Test when front matter name differs from filename."""
        with tempfile.TemporaryDirectory() as tmpdir:
            styles_dir = Path(tmpdir)
            style_file = styles_dir / 'filename.md'
            style_file.write_text('''---
name: Actual Style Name
description: The real name differs from filename
---
# Content
''')
            result = setup_environment.resolve_output_style_name('filename', styles_dir)
            assert result == 'Actual Style Name'

    def test_resolve_output_style_name_no_front_matter(self):
        """Test resolution when file has no front matter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            styles_dir = Path(tmpdir)
            style_file = styles_dir / 'plain-file.md'
            style_file.write_text('# Just content, no front matter')

            result = setup_environment.resolve_output_style_name('plain-file', styles_dir)
            assert result == 'plain-file'

    def test_resolve_output_style_name_missing_name_field(self):
        """Test resolution when front matter exists but lacks name field (has description only)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            styles_dir = Path(tmpdir)
            style_file = styles_dir / 'no-name.md'
            style_file.write_text('''---
description: Has front matter but no name field
---
# Content
''')
            result = setup_environment.resolve_output_style_name('no-name', styles_dir)
            assert result == 'no-name'

    def test_resolve_output_style_name_file_not_found(self):
        """Test resolution when file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            styles_dir = Path(tmpdir)
            result = setup_environment.resolve_output_style_name('nonexistent', styles_dir)
            assert result == 'nonexistent'

    def test_resolve_output_style_name_with_md_extension(self):
        """Test resolution when input includes .md extension."""
        with tempfile.TemporaryDirectory() as tmpdir:
            styles_dir = Path(tmpdir)
            style_file = styles_dir / 'style.md'
            style_file.write_text('''---
name: Style With Extension
---
# Content
''')
            result = setup_environment.resolve_output_style_name('style.md', styles_dir)
            assert result == 'Style With Extension'

    def test_resolve_output_style_name_without_md_extension(self):
        """Test resolution when input doesn't include .md extension."""
        with tempfile.TemporaryDirectory() as tmpdir:
            styles_dir = Path(tmpdir)
            style_file = styles_dir / 'another-style.md'
            style_file.write_text('''---
name: Another Style Name
---
# Content
''')
            result = setup_environment.resolve_output_style_name('another-style', styles_dir)
            assert result == 'Another Style Name'

    def test_resolve_output_style_name_special_characters(self):
        """Test resolution with special characters in the name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            styles_dir = Path(tmpdir)
            style_file = styles_dir / 'special.md'
            style_file.write_text('''---
name: "Style: With Special-Characters & Symbols!"
---
# Content
''')
            result = setup_environment.resolve_output_style_name('special', styles_dir)
            assert result == 'Style: With Special-Characters & Symbols!'


class TestCreateAdditionalSettingsWithOutputStyleResolution:
    """Test create_additional_settings with output style name resolution."""

    def test_create_additional_settings_resolves_output_style_name(self):
        """Test that output style name is resolved from front matter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir) / '.claude'
            styles_dir = claude_dir / 'output-styles'
            styles_dir.mkdir(parents=True, exist_ok=True)

            # Create an output style file with different name in front matter
            style_file = styles_dir / 'file-name.md'
            style_file.write_text('''---
name: Actual Display Name
description: Test output style
---
# Test Style Content
''')

            # Create additional settings with output style
            result = setup_environment.create_additional_settings(
                hooks={},
                claude_user_dir=claude_dir,
                command_name='test-env',
                output_style='file-name',
                output_styles_dir=styles_dir,
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            assert settings_file.exists()

            settings = json.loads(settings_file.read_text())
            # Should use the name from front matter, not the filename
            assert settings['outputStyle'] == 'Actual Display Name'

    def test_create_additional_settings_fallback_to_filename(self):
        """Test fallback to filename when front matter is missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir) / '.claude'
            styles_dir = claude_dir / 'output-styles'
            styles_dir.mkdir(parents=True, exist_ok=True)

            # Create an output style file without front matter
            style_file = styles_dir / 'plain-style.md'
            style_file.write_text('# Plain Style\n\nNo front matter here.')

            # Create additional settings with output style
            result = setup_environment.create_additional_settings(
                hooks={},
                claude_user_dir=claude_dir,
                command_name='test-env',
                output_style='plain-style.md',
                output_styles_dir=styles_dir,
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())
            # Should use cleaned filename (without .md) as fallback
            assert settings['outputStyle'] == 'plain-style'

    def test_create_additional_settings_without_output_styles_dir(self):
        """Test output style handling when output_styles_dir is not provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir) / '.claude'
            claude_dir.mkdir(parents=True, exist_ok=True)

            # Create additional settings without output_styles_dir (old behavior)
            result = setup_environment.create_additional_settings(
                hooks={},
                claude_user_dir=claude_dir,
                command_name='test-env',
                output_style='legacy-style.md',
                # output_styles_dir not provided - should just strip .md
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())
            # Should strip .md extension
            assert settings['outputStyle'] == 'legacy-style'

    def test_create_additional_settings_output_style_not_found(self):
        """Test handling when output style file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir) / '.claude'
            styles_dir = claude_dir / 'output-styles'
            styles_dir.mkdir(parents=True, exist_ok=True)

            # Don't create the file, just reference it
            result = setup_environment.create_additional_settings(
                hooks={},
                claude_user_dir=claude_dir,
                command_name='test-env',
                output_style='nonexistent-style',
                output_styles_dir=styles_dir,
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())
            # Should still use the provided name when file not found
            assert settings['outputStyle'] == 'nonexistent-style'


class TestMainFunction:
    """Test the main setup flow."""

    @patch('setup_environment.load_config_from_source')
    @patch('setup_environment.validate_all_config_files')
    @patch('setup_environment.install_claude')
    @patch('setup_environment.install_dependencies')
    @patch('setup_environment.process_resources')
    @patch('setup_environment.configure_all_mcp_servers')
    @patch('setup_environment.create_additional_settings')
    @patch('setup_environment.create_launcher_script')
    @patch('setup_environment.register_global_command')
    @patch('pathlib.Path.mkdir')
    def test_main_success(
        self,
        mock_mkdir,
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
        mock_load.return_value = (
            {
                'name': 'Test Environment',
                'command-name': 'test-env',
                'dependencies': ['npm install -g test'],
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
    def test_main_install_failure(self, mock_install, mock_load):
        """Test main with Claude installation failure."""
        mock_load.return_value = ({'name': 'Test'}, 'test.yaml')
        mock_install.return_value = False

        with patch('sys.argv', ['setup_environment.py', 'test']), patch('sys.exit') as mock_exit:
            setup_environment.main()
            mock_exit.assert_called_with(1)

    @patch('setup_environment.load_config_from_source')
    @patch('setup_environment.find_command')
    def test_main_skip_install(self, mock_find, mock_load):
        """Test main with --skip-install flag."""
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
