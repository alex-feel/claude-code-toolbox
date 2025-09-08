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


class TestResolveResourceUrl:
    """Test resource URL resolution."""

    def test_resolve_resource_url_full_url(self):
        """Test that full URLs are returned as-is."""
        result = setup_environment.resolve_resource_url(
            'https://example.com/file.yaml',
            'config_source',
            None,
        )
        assert result == 'https://example.com/file.yaml'

    def test_resolve_resource_url_with_base_url(self):
        """Test resolution with base URL override."""
        result = setup_environment.resolve_resource_url(
            'agents/test.md',
            'config_source',
            'https://example.com/base/',
        )
        assert result == 'https://example.com/base/agents/test.md'

    def test_resolve_resource_url_from_config_source(self):
        """Test resolution from config source URL."""
        result = setup_environment.resolve_resource_url(
            'agents/test.md',
            'https://raw.githubusercontent.com/user/repo/main/config.yaml',
            None,
        )
        assert result == 'https://raw.githubusercontent.com/user/repo/main/agents/test.md'

    def test_resolve_resource_url_default(self):
        """Test fallback to default repo URL."""
        result = setup_environment.resolve_resource_url(
            'agents/test.md',
            'local_config.yaml',
            None,
        )
        assert result.endswith('/agents/test.md')


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


class TestInstallDependencies:
    """Test dependency installation."""

    @patch('platform.system', return_value='Windows')
    @patch('setup_environment.run_command')
    def test_install_dependencies_windows(self, mock_run, mock_system):
        """Test installing dependencies on Windows."""
        # Verify mock configuration
        assert mock_system.return_value == 'Windows'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        result = setup_environment.install_dependencies(['npm install -g package'])
        assert result is True
        mock_run.assert_called_with(['npm', 'install', '-g', 'package'], capture_output=False)

    @patch('platform.system', return_value='Linux')
    @patch('setup_environment.run_command')
    def test_install_dependencies_linux(self, mock_run, mock_system):
        """Test installing dependencies on Linux."""
        # Verify mock configuration
        assert mock_system.return_value == 'Linux'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        result = setup_environment.install_dependencies(['apt-get install package'])
        assert result is True
        mock_run.assert_called_with(['bash', '-c', 'apt-get install package'], capture_output=False)

    @patch('platform.system', return_value='Windows')
    @patch('setup_environment.run_command')
    def test_install_dependencies_uv_tool_windows(self, mock_run, mock_system):
        """Test installing uv tools with force flag on Windows."""
        # Verify mock configuration
        assert mock_system.return_value == 'Windows'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        result = setup_environment.install_dependencies(['uv tool install ruff'])
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
        mock_run.assert_called_once()
        # Check the command string contains mcp add
        cmd_str = ' '.join(str(arg) for arg in mock_run.call_args[0][0])
        assert 'mcp add' in cmd_str
        assert 'test-server' in cmd_str

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
        """Test creating settings with MCP server permissions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            mcp_servers = [
                {'name': 'server1'},
                {'name': 'server2'},
            ]

            result = setup_environment.create_additional_settings(
                {},
                claude_dir,
                'test-env',
                mcp_servers=mcp_servers,
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            assert 'permissions' in settings
            assert 'mcp__server1' in settings['permissions']['allow']
            assert 'mcp__server2' in settings['permissions']['allow']

    @patch('setup_environment.download_resource_with_url')
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
    def test_install_claude_windows(self, mock_run, mock_urlopen, mock_system):
        """Test installing Claude on Windows."""
        # Verify mock configuration
        assert mock_system.return_value == 'Windows'
        mock_response = MagicMock()
        mock_response.read.return_value = b'# PowerShell installer'
        mock_urlopen.return_value = mock_response

        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        result = setup_environment.install_claude()
        assert result is True
        mock_run.assert_called_once()
        assert 'powershell' in mock_run.call_args[0][0]

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


class TestMainFunction:
    """Test the main setup flow."""

    @patch('setup_environment.load_config_from_source')
    @patch('setup_environment.validate_all_config_files')
    @patch('setup_environment.install_claude')
    @patch('setup_environment.install_dependencies')
    @patch('setup_environment.download_resources')
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
