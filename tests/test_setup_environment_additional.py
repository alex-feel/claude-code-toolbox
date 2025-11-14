"""
Additional comprehensive tests for setup_environment.py to achieve >90% coverage.
Focuses on error paths, edge cases, and complex scenarios.
"""
# ruff: noqa: PT019  # Mock patch parameters are not fixtures

import json
import os
import subprocess
import sys
import tempfile
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import yaml

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

import setup_environment


class TestSSLErrorHandling:
    """Test SSL error handling and fallback scenarios."""

    @patch('setup_environment.urlopen')
    def test_download_file_ssl_error_then_success(self, mock_urlopen):
        """Test SSL error fallback succeeds on retry."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'ssl fallback content'

        # First call raises SSL error, second succeeds with unverified context
        mock_urlopen.side_effect = [
            urllib.error.URLError('SSL: CERTIFICATE_VERIFY_FAILED'),
            mock_response,
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / 'test.txt'
            result = setup_environment.download_file('https://secure.example.com/file', dest)

            assert result is True
            assert dest.exists()
            assert dest.read_bytes() == b'ssl fallback content'

            # Verify SSL context was created for second call
            assert mock_urlopen.call_count == 2
            second_call = mock_urlopen.call_args_list[1]
            assert 'context' in second_call[1]

    @patch('setup_environment.urlopen')
    def test_download_file_non_ssl_error_propagates(self, mock_urlopen):
        """Test non-SSL errors are propagated."""
        mock_urlopen.side_effect = urllib.error.URLError('Network unreachable')

        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / 'test.txt'
            result = setup_environment.download_file('https://example.com/file', dest)

            assert result is False
            assert not dest.exists()

    @patch('setup_environment.urlopen')
    def test_download_file_generic_exception(self, mock_urlopen):
        """Test generic exception handling in download_file."""
        mock_urlopen.side_effect = Exception('Unexpected error')

        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / 'test.txt'
            result = setup_environment.download_file('https://example.com/file', dest)

            assert result is False
            assert not dest.exists()


class TestGitLabURLConversionEdgeCases:
    """Test GitLab URL conversion edge cases."""

    def test_convert_gitlab_url_http_protocol(self):
        """Test GitLab URL conversion with HTTP protocol."""
        url = 'http://gitlab.com/namespace/project/-/raw/main/file.yaml'
        result = setup_environment.convert_gitlab_url_to_api(url)
        assert result.startswith('http://gitlab.com/api/v4/projects/')
        assert 'namespace%2Fproject' in result

    def test_convert_gitlab_url_no_file_path(self):
        """Test GitLab URL with no file path after branch."""
        url = 'https://gitlab.com/namespace/project/-/raw/main'
        result = setup_environment.convert_gitlab_url_to_api(url)
        assert '/api/v4/projects/' in result
        assert 'ref=main' in result

    def test_convert_gitlab_url_with_query_params(self):
        """Test GitLab URL with query parameters."""
        url = 'https://gitlab.com/namespace/project/-/raw/main/file.yaml?ref=develop&ref_type=heads'
        result = setup_environment.convert_gitlab_url_to_api(url)
        assert 'ref=develop' in result  # ref parameter should override branch

    def test_convert_gitlab_url_malformed(self):
        """Test malformed GitLab URL returns original."""
        url = 'https://gitlab.com/malformed'
        result = setup_environment.convert_gitlab_url_to_api(url)
        assert result == url

    def test_convert_gitlab_url_invalid_protocol(self):
        """Test URL with invalid protocol returns original."""
        url = 'ftp://gitlab.com/namespace/project/-/raw/main/file.yaml'
        result = setup_environment.convert_gitlab_url_to_api(url)
        assert result == url

    def test_convert_gitlab_url_exception_handling(self):
        """Test exception handling in URL conversion."""
        # URL that would normally cause issues but is handled
        url = 'https://gitlab.com/project'  # No /-/raw/ part
        result = setup_environment.convert_gitlab_url_to_api(url)
        assert result == url  # Should return original when not a raw URL


class TestAuthenticationWithPrompts:
    """Test authentication headers with interactive prompts."""

    @patch('sys.stdin.isatty', return_value=True)
    @patch('builtins.input', return_value='y')
    @patch('getpass.getpass', return_value='secret_token')
    def test_get_auth_headers_interactive_gitlab(self, mock_getpass, mock_input, mock_isatty):
        """Test interactive authentication prompt for GitLab."""
        with patch.dict('os.environ', {}, clear=True):
            headers = setup_environment.get_auth_headers('https://gitlab.com/repo', None)

            assert headers == {'PRIVATE-TOKEN': 'secret_token'}
            # Verify mocks were called correctly
            mock_isatty.assert_called_once()
            assert mock_isatty.return_value is True
            mock_input.assert_called_once()
            assert mock_input.return_value == 'y'
            mock_getpass.assert_called_once()
            assert mock_getpass.return_value == 'secret_token'

    @patch('sys.stdin.isatty', return_value=True)
    @patch('builtins.input', return_value='y')
    @patch('getpass.getpass', return_value='gh_token123')
    def test_get_auth_headers_interactive_github(self, mock_getpass, mock_input, mock_isatty):
        """Test interactive authentication prompt for GitHub."""
        with patch.dict('os.environ', {}, clear=True):
            headers = setup_environment.get_auth_headers('https://github.com/repo', None)

            assert headers == {'Authorization': 'Bearer gh_token123'}
            # Verify mocks were called and configured correctly
            mock_isatty.assert_called_once()
            assert mock_isatty.return_value is True
            mock_input.assert_called_once()
            assert mock_input.return_value == 'y'
            mock_getpass.assert_called_once()
            assert mock_getpass.return_value == 'gh_token123'

    @patch('sys.stdin.isatty', return_value=True)
    @patch('builtins.input', return_value='n')
    def test_get_auth_headers_interactive_declined(self, mock_input, mock_isatty):
        """Test declining interactive authentication."""
        with patch.dict('os.environ', {}, clear=True):
            headers = setup_environment.get_auth_headers('https://gitlab.com/repo', None)

            assert headers == {}
            mock_input.assert_called_once()
            # Verify mock configurations
            assert mock_isatty.return_value is True
            assert mock_input.return_value == 'n'

    @patch('sys.stdin.isatty', return_value=True)
    @patch('builtins.input', side_effect=KeyboardInterrupt)
    def test_get_auth_headers_interactive_cancelled(self, mock_input, mock_isatty):
        """Test cancelling interactive authentication with Ctrl+C."""
        with patch.dict('os.environ', {}, clear=True):
            headers = setup_environment.get_auth_headers('https://gitlab.com/repo', None)

            assert headers == {}
            # Verify mock configurations
            assert mock_isatty.return_value is True
            mock_input.assert_called_once()

    @patch('sys.stdin.isatty', return_value=False)
    def test_get_auth_headers_non_interactive_terminal(self, mock_isatty):
        """Test non-interactive terminal with private repo."""
        with patch.dict('os.environ', {}, clear=True):
            headers = setup_environment.get_auth_headers('https://gitlab.com/repo', None)

            assert headers == {}
            mock_isatty.assert_called_once()

    def test_get_auth_headers_token_only_gitlab(self):
        """Test auth parameter with token only for GitLab."""
        headers = setup_environment.get_auth_headers('https://gitlab.com/repo', 'mytoken123')
        assert headers == {'PRIVATE-TOKEN': 'mytoken123'}

    def test_get_auth_headers_token_only_github(self):
        """Test auth parameter with token only for GitHub."""
        headers = setup_environment.get_auth_headers('https://github.com/repo', 'ghp_token')
        assert headers == {'Authorization': 'Bearer ghp_token'}

    def test_get_auth_headers_token_only_unknown_repo(self):
        """Test auth parameter with token only for unknown repo type."""
        headers = setup_environment.get_auth_headers('https://example.com/repo', 'token123')
        assert headers == {}

    def test_get_auth_headers_bearer_prefix_github(self):
        """Test GitHub token with Bearer prefix already included."""
        headers = setup_environment.get_auth_headers('https://github.com/repo', 'Bearer ghp_token')
        assert headers == {'Authorization': 'Bearer ghp_token'}


class TestBitbucketDetection:
    """Test Bitbucket repository detection."""

    def test_detect_bitbucket_repo(self):
        """Test Bitbucket URL detection."""
        assert setup_environment.detect_repo_type('https://bitbucket.org/user/repo') == 'bitbucket'
        assert setup_environment.detect_repo_type('https://api.bitbucket.org/2.0/repositories/') == 'bitbucket'


class TestConfigLoadingErrorPaths:
    """Test configuration loading error paths."""

    @patch('setup_environment.fetch_url_with_auth')
    def test_load_config_from_url_failure(self, mock_fetch):
        """Test URL config loading failure."""
        mock_fetch.side_effect = Exception('Network error')

        with pytest.raises(Exception, match='Network error'):
            setup_environment.load_config_from_source('https://example.com/config.yaml')

    def test_load_config_from_missing_local_file(self):
        """Test loading from non-existent local file."""
        with pytest.raises(FileNotFoundError):
            setup_environment.load_config_from_source('./missing_config.yaml')

    def test_load_config_from_invalid_yaml(self):
        """Test loading invalid YAML from local file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tmp:
            tmp.write('invalid: yaml: content: [')
            tmp_path = tmp.name

        try:
            with pytest.raises(yaml.YAMLError):
                setup_environment.load_config_from_source(tmp_path)
        finally:
            os.unlink(tmp_path)

    @patch('setup_environment.fetch_url_with_auth')
    def test_load_config_from_repo_404(self, mock_fetch):
        """Test repository config not found (404)."""
        mock_fetch.side_effect = urllib.error.HTTPError(
            'url',
            404,
            'Not Found',
            {},
            None,
        )

        with pytest.raises(Exception, match='Configuration not found'):
            setup_environment.load_config_from_source('nonexistent')

    @patch('setup_environment.fetch_url_with_auth')
    def test_load_config_from_repo_other_http_error(self, mock_fetch):
        """Test repository config with non-404 HTTP error."""
        mock_fetch.side_effect = urllib.error.HTTPError(
            'url',
            500,
            'Server Error',
            {},
            None,
        )

        with pytest.raises(urllib.error.HTTPError):
            setup_environment.load_config_from_source('python')

    @patch('setup_environment.fetch_url_with_auth')
    def test_load_config_from_repo_generic_error(self, mock_fetch):
        """Test repository config with generic error."""
        mock_fetch.side_effect = Exception('Generic error')

        with pytest.raises(Exception, match='Generic error'):
            setup_environment.load_config_from_source('python')


class TestResolveResourcePathEdgeCases:
    """Test resource URL resolution edge cases."""

    def test_resolve_resource_path_gitlab_encoding(self):
        """Test GitLab API URL encoding in resource resolution."""
        path, is_remote = setup_environment.resolve_resource_path(
            'path/to/file.yaml',
            'config',
            'https://gitlab.com/api/v4/projects/123/repository/files/{path}/raw?ref=main',
        )
        assert 'path%2Fto%2Ffile.yaml' in path
        assert is_remote is True

    def test_resolve_resource_path_from_gitlab_config_source(self):
        """Test resource resolution from GitLab config source."""
        path, is_remote = setup_environment.resolve_resource_path(
            'hooks/script.py',
            'https://gitlab.com/api/v4/projects/123/repository/files/config.yaml/raw?ref=main',
            None,
        )
        assert '/api/v4/projects/123/repository/files/' in path
        assert 'hooks%2Fscript.py' in path
        assert is_remote is True

    def test_resolve_resource_path_base_url_without_path_placeholder(self):
        """Test base URL without {path} placeholder."""
        path, is_remote = setup_environment.resolve_resource_path(
            'test.md',
            'config',
            'https://example.com/base/',
        )
        assert path == 'https://example.com/base/test.md'
        assert is_remote is True

    def test_resolve_resource_path_base_url_no_trailing_slash(self):
        """Test base URL without trailing slash."""
        path, is_remote = setup_environment.resolve_resource_path(
            'test.md',
            'config',
            'https://example.com/base',
        )
        assert path == 'https://example.com/base/test.md'
        assert is_remote is True


class TestFetchURLWithAuthEdgeCases:
    """Test URL fetching with authentication edge cases."""

    @patch('setup_environment.urlopen')
    @patch('setup_environment.convert_gitlab_url_to_api')
    def test_fetch_url_gitlab_conversion(self, mock_convert, mock_urlopen):
        """Test GitLab URL conversion before fetching."""
        mock_convert.return_value = 'https://gitlab.com/api/v4/projects/123/file'
        mock_response = MagicMock()
        mock_response.read.return_value = b'content'
        mock_urlopen.return_value = mock_response

        result = setup_environment.fetch_url_with_auth(
            'https://gitlab.com/project/-/raw/main/file',
        )

        assert result == 'content'
        mock_convert.assert_called_once()

    @patch('setup_environment.urlopen')
    @patch('setup_environment.get_auth_headers')
    def test_fetch_url_401_with_auth_failure(self, mock_get_auth, mock_urlopen):
        """Test 401 error even after authentication."""
        mock_urlopen.side_effect = [
            urllib.error.HTTPError('url', 401, 'Unauthorized', {}, None),
            urllib.error.HTTPError('url', 401, 'Unauthorized', {}, None),
        ]
        mock_get_auth.return_value = {'PRIVATE-TOKEN': 'bad_token'}

        with pytest.raises(urllib.error.HTTPError):
            setup_environment.fetch_url_with_auth('https://gitlab.com/file')

    @patch('setup_environment.urlopen')
    @patch('setup_environment.get_auth_headers')
    def test_fetch_url_403_with_auth(self, mock_get_auth, mock_urlopen):
        """Test 403 error after authentication."""
        mock_urlopen.side_effect = [
            urllib.error.HTTPError('url', 403, 'Forbidden', {}, None),
            urllib.error.HTTPError('url', 403, 'Forbidden', {}, None),
        ]
        mock_get_auth.return_value = {'PRIVATE-TOKEN': 'token'}

        with pytest.raises(urllib.error.HTTPError):
            setup_environment.fetch_url_with_auth('https://gitlab.com/file')

    @patch('setup_environment.urlopen')
    def test_fetch_url_404_no_auth_available(self, mock_urlopen):
        """Test 404 error with no authentication available."""
        mock_urlopen.side_effect = urllib.error.HTTPError('url', 404, 'Not Found', {}, None)

        with pytest.raises(urllib.error.HTTPError):
            setup_environment.fetch_url_with_auth('https://example.com/file')

    @patch('setup_environment.urlopen')
    @patch('setup_environment.get_auth_headers')
    def test_fetch_url_404_with_auth(self, mock_get_auth, mock_urlopen):
        """Test 404 error even with authentication."""
        mock_urlopen.side_effect = [
            urllib.error.HTTPError('url', 404, 'Not Found', {}, None),
            urllib.error.HTTPError('url', 404, 'Not Found', {}, None),
        ]
        mock_get_auth.return_value = {'PRIVATE-TOKEN': 'token'}

        with pytest.raises(urllib.error.HTTPError):
            setup_environment.fetch_url_with_auth('https://gitlab.com/file')

    @patch('setup_environment.urlopen')
    def test_fetch_url_ssl_error_with_auth_headers(self, mock_urlopen):
        """Test SSL error handling with pre-provided auth headers."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'ssl content'
        mock_urlopen.side_effect = [
            urllib.error.URLError('SSL: CERTIFICATE_VERIFY_FAILED'),
            mock_response,
        ]

        auth_headers = {'PRIVATE-TOKEN': 'token'}
        result = setup_environment.fetch_url_with_auth(
            'https://secure.example.com/file',
            auth_headers=auth_headers,
        )

        assert result == 'ssl content'
        # Check that auth headers were added to the request
        second_call = mock_urlopen.call_args_list[1]
        assert 'context' in second_call[1]


class TestHandleResource:
    """Test handle_resource function."""

    @patch('setup_environment.resolve_resource_path')
    @patch('setup_environment.fetch_url_with_auth')
    def test_handle_resource_remote_success(self, mock_fetch, mock_resolve):
        """Test successful remote resource download."""
        mock_resolve.return_value = ('https://example.com/base/agents/test.md', True)
        mock_fetch.return_value = 'file content'

        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / 'resource.md'
            result = setup_environment.handle_resource(
                'agents/test.md',
                dest,
                'https://example.com/config.yaml',
                base_url='https://example.com/base/{path}',
                auth_param='token123',
            )

            assert result is True
            assert dest.exists()
            assert dest.read_text() == 'file content'

    @patch('setup_environment.resolve_resource_path')
    @patch('setup_environment.fetch_url_with_auth')
    def test_handle_resource_overwrite_existing(self, mock_fetch, mock_resolve):
        """Test overwriting existing file."""
        mock_resolve.return_value = ('https://example.com/resource.md', True)
        mock_fetch.return_value = 'new content'

        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / 'existing.md'
            dest.write_text('old content')

            result = setup_environment.handle_resource(
                'resource.md',
                dest,
                'config.yaml',
                None,
                None,
            )

            assert result is True
            assert dest.read_text() == 'new content'

    @patch('setup_environment.resolve_resource_path')
    @patch('setup_environment.fetch_url_with_auth')
    def test_handle_resource_failure(self, mock_fetch, mock_resolve):
        """Test resource download failure."""
        mock_resolve.return_value = ('https://example.com/resource.md', True)
        mock_fetch.side_effect = Exception('Download failed')

        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / 'resource.md'
            result = setup_environment.handle_resource(
                'resource.md',
                dest,
                'config.yaml',
                None,
                None,
            )

            assert result is False
            assert not dest.exists()


class TestInstallClaudeEdgeCases:
    """Test Claude installation edge cases."""

    @patch('platform.system', return_value='Windows')
    @patch('setup_environment.urlopen')
    @patch('setup_environment.run_command')
    @patch('setup_environment.is_admin', return_value=True)
    def test_install_claude_windows_ssl_error(self, mock_is_admin, mock_run, mock_urlopen, _mock_system):
        """Test Claude installation on Windows with SSL error."""
        assert mock_is_admin.return_value is True  # Verify admin check is mocked
        mock_urlopen.side_effect = [
            urllib.error.URLError('SSL: CERTIFICATE_VERIFY_FAILED'),
            MagicMock(read=lambda: b'# PowerShell script'),
        ]
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        result = setup_environment.install_claude()
        assert result is True
        assert mock_urlopen.call_count == 2
        mock_is_admin.assert_called()  # Verify is_admin was called

    @patch('setup_environment.is_admin', return_value=True)
    @patch('platform.system', return_value='Windows')
    @patch('setup_environment.urlopen')
    @patch('setup_environment.run_command')
    def test_install_claude_windows_failure(self, mock_run, mock_urlopen, mock_system, mock_is_admin):
        """Test Claude installation failure on Windows."""
        assert mock_system.return_value == 'Windows'
        assert mock_is_admin.return_value is True
        mock_urlopen.return_value = MagicMock(read=lambda: b'# Script')
        mock_run.return_value = subprocess.CompletedProcess([], 1, '', 'Error')

        result = setup_environment.install_claude()
        assert result is False

    @patch('platform.system', return_value='Darwin')
    @patch('setup_environment.run_command')
    def test_install_claude_macos_failure(self, mock_run, _mock_system):
        """Test Claude installation failure on macOS."""
        mock_run.return_value = subprocess.CompletedProcess([], 1, '', 'Error')

        result = setup_environment.install_claude()
        assert result is False

    @patch('platform.system', return_value='Linux')
    @patch('setup_environment.run_command')
    def test_install_claude_linux_success(self, mock_run, _mock_system):
        """Test Claude installation on Linux."""
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        result = setup_environment.install_claude()
        assert result is True

    @patch('setup_environment.is_admin', return_value=True)
    @patch('platform.system', return_value='Windows')
    @patch('setup_environment.urlopen')
    def test_install_claude_windows_network_error(self, mock_urlopen, _mock_system, mock_is_admin):
        """Test Claude installation with network error."""
        assert mock_is_admin.return_value is True
        mock_urlopen.side_effect = urllib.error.URLError('Network error')

        result = setup_environment.install_claude()
        assert result is False


class TestMCPServerConfigurationEdgeCases:
    """Test MCP server configuration edge cases."""

    @patch('platform.system', return_value='Windows')
    @patch('setup_environment.find_command_robust', return_value=None)
    @patch('pathlib.Path.exists')
    def test_configure_mcp_server_claude_not_found(self, mock_exists, mock_find, _mock_system):
        """Test MCP configuration when claude command not found."""
        del mock_find  # Unused but required for patch
        del _mock_system  # Unused but required for patch
        mock_exists.return_value = False

        server = {'name': 'test', 'transport': 'http', 'url': 'http://localhost'}
        result = setup_environment.configure_mcp_server(server)

        assert result is False

    @patch('platform.system', return_value='Windows')
    @patch('setup_environment.find_command', return_value=None)
    def test_configure_mcp_server_find_in_npm_path(self, mock_find, mock_system):
        """Test finding claude in npm path on Windows."""
        del mock_find  # Unused but required for patch
        assert mock_system.return_value == 'Windows'
        with (
            patch.dict('os.environ', {'APPDATA': 'C:\\Users\\Test\\AppData\\Roaming'}),
            patch('pathlib.Path.exists', return_value=True),
            patch('setup_environment.run_command') as mock_run,
        ):
            mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

            server = {'name': 'test', 'transport': 'http', 'url': 'http://localhost'}
            result = setup_environment.configure_mcp_server(server)

            assert result is True
            # Should call run_command 4 times: 3 for removing from all scopes, once for add
            assert mock_run.call_count == 4

    @patch('platform.system', return_value='Linux')
    @patch('setup_environment.find_command', return_value=None)
    def test_configure_mcp_server_find_in_unix_paths(self, mock_find, _mock_system):
        """Test finding claude in Unix paths."""
        del mock_find  # Unused but required for patch
        del _mock_system  # Unused but required for patch
        # Mock exists to return True for the first Unix path checked
        with patch('pathlib.Path.exists', return_value=True), patch('setup_environment.run_command') as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

            server = {'name': 'test', 'command': 'npx server'}
            result = setup_environment.configure_mcp_server(server)

            assert result is True
            # Should call run_command 4 times: 3 for removing from all scopes, once for add
            assert mock_run.call_count == 4

    def test_configure_mcp_server_missing_name(self):
        """Test MCP configuration with missing name."""
        server = {'transport': 'http', 'url': 'http://localhost'}
        result = setup_environment.configure_mcp_server(server)
        assert result is False

    @patch('setup_environment.find_command_robust', return_value='claude')
    def test_configure_mcp_server_missing_transport_details(self, mock_find):
        """Test MCP configuration with missing transport details."""
        del mock_find  # Unused but required for patch
        server = {'name': 'test'}
        result = setup_environment.configure_mcp_server(server)
        assert result is False

    @patch('platform.system', return_value='Windows')
    @patch('setup_environment.find_command_robust', return_value='claude')
    @patch('setup_environment.run_command')
    def test_configure_mcp_server_windows_retry(self, mock_run, mock_find, _mock_system):
        """Test MCP configuration retry on Windows."""
        del mock_find  # Unused but required for patch
        del _mock_system  # Unused but required for patch
        # 3 removes (one per scope), first add attempt fails, retry add succeeds
        mock_run.side_effect = [
            subprocess.CompletedProcess([], 1, '', 'Server not found'),  # remove user fails
            subprocess.CompletedProcess([], 1, '', 'Server not found'),  # remove local fails
            subprocess.CompletedProcess([], 1, '', 'Server not found'),  # remove project fails
            subprocess.CompletedProcess([], 1, '', 'Error'),  # first add fails
            subprocess.CompletedProcess([], 0, '', ''),  # retry add succeeds
        ]

        server = {
            'name': 'test',
            'transport': 'http',
            'url': 'http://localhost',
            'header': 'Auth: token',
        }

        with patch('time.sleep'):  # Skip actual sleep
            result = setup_environment.configure_mcp_server(server)

        assert result is True
        assert mock_run.call_count == 5

    @patch('setup_environment.find_command_robust', return_value='claude')
    @patch('setup_environment.run_command')
    def test_configure_mcp_server_already_exists(self, mock_run, mock_find):
        """Test MCP configuration removes existing server before adding."""
        del mock_find  # Unused but required for patch
        # 3 removes (one per scope) can fail - server might not exist
        # Then add should succeed
        mock_run.side_effect = [
            subprocess.CompletedProcess([], 1, '', 'Server not found'),  # remove user fails
            subprocess.CompletedProcess([], 1, '', 'Server not found'),  # remove local fails
            subprocess.CompletedProcess([], 1, '', 'Server not found'),  # remove project fails
            subprocess.CompletedProcess([], 0, '', ''),  # add succeeds
        ]

        server = {'name': 'test', 'command': 'test-server'}
        result = setup_environment.configure_mcp_server(server)

        assert result is True
        # Verify 3 remove commands and 1 add command were called
        assert mock_run.call_count == 4

    @patch('platform.system', return_value='Windows')
    @patch('setup_environment.find_command_robust', return_value='claude')
    @patch('setup_environment.run_command')
    def test_configure_mcp_server_final_failure(self, mock_run, mock_find, mock_system):
        """Test MCP configuration final failure after retry."""
        del mock_find  # Unused but required for patch
        del mock_system  # Unused but required for patch
        # 3 removes (one per scope), first add fails, retry add fails
        mock_run.side_effect = [
            subprocess.CompletedProcess([], 1, '', 'Server not found'),  # remove user fails
            subprocess.CompletedProcess([], 1, '', 'Server not found'),  # remove local fails
            subprocess.CompletedProcess([], 1, '', 'Server not found'),  # remove project fails
            subprocess.CompletedProcess([], 1, '', 'Error'),  # first add fails
            subprocess.CompletedProcess([], 1, '', 'Error'),  # retry add fails
        ]

        server = {'name': 'test', 'command': 'test-server'}

        with patch('time.sleep'):
            result = setup_environment.configure_mcp_server(server)

        assert result is False
        # Expects 5 calls: 3 removes + first add + retry add
        assert mock_run.call_count == 5

    @patch('platform.system', return_value='Windows')
    @patch('setup_environment.find_command_robust', return_value='claude')
    @patch('setup_environment.run_command')
    def test_configure_mcp_server_windows_npx_command(self, mock_run, mock_find, _mock_system):
        """Test MCP configuration with npx command on Windows."""
        del mock_find  # Unused but required for patch
        del _mock_system  # Unused but required for patch
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        server = {
            'name': 'test',
            'command': 'npx @modelcontextprotocol/server-memory',
            'env': 'TEST_VAR=value',
        }

        result = setup_environment.configure_mcp_server(server)
        assert result is True

        # Should call run_command 4 times: 3 for removing from all scopes, once for add
        assert mock_run.call_count == 4
        # Check that cmd /c was used for npx in the last call (add)
        call_args = mock_run.call_args_list[3][0][0]
        assert 'cmd' in call_args
        assert '/c' in call_args
        assert 'npx @modelcontextprotocol/server-memory' in call_args

    @patch('setup_environment.find_command_robust', return_value='claude')
    def test_configure_mcp_server_exception(self, mock_find):
        """Test MCP configuration with exception."""
        del mock_find  # Unused but required for patch
        server = {'name': 'test', 'command': 'test'}

        # Exception happens on the add command (second call)
        with patch(
            'setup_environment.run_command',
            side_effect=[
                subprocess.CompletedProcess([], 0, '', ''),  # remove succeeds
                Exception('Unexpected'),  # add throws exception
            ],
        ):
            result = setup_environment.configure_mcp_server(server)

        assert result is False


class TestCreateAdditionalSettingsComplex:
    """Test complex additional settings creation scenarios."""

    def test_create_additional_settings_with_permissions_merge(self):
        """Test that only explicit permissions are included, no auto-adding."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            permissions = {
                'allow': ['tool__*', 'mcp__server1'],
                'deny': ['mcp__server3'],
                'ask': ['mcp__server4'],
            }

            result = setup_environment.create_additional_settings(
                {},
                claude_dir,
                'test',
                permissions=permissions,
            )

            assert result is True
            settings_file = claude_dir / 'test-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            # Only explicitly listed permissions should be present
            assert 'mcp__server1' in settings['permissions']['allow']
            assert 'tool__*' in settings['permissions']['allow']
            # server2 should NOT be auto-added
            assert 'mcp__server2' not in settings['permissions']['allow']
            assert settings['permissions']['allow'].count('mcp__server1') == 1

    def test_create_additional_settings_mcp_in_deny_list(self):
        """Test MCP server in deny list is not auto-allowed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            permissions = {'deny': ['mcp__blocked_server']}

            setup_environment.create_additional_settings(
                {},
                claude_dir,
                'test',
                permissions=permissions,
            )

            settings_file = claude_dir / 'test-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            # Should not be in allow list
            assert 'allow' not in settings['permissions'] or 'mcp__blocked_server' not in settings['permissions'].get(
                'allow',
                [],
            )

    def test_create_additional_settings_mcp_in_ask_list(self):
        """Test MCP server in ask list is not auto-allowed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            permissions = {'ask': ['mcp__ask_server']}

            setup_environment.create_additional_settings(
                {},
                claude_dir,
                'test',
                permissions=permissions,
            )

            settings_file = claude_dir / 'test-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            # Should not be in allow list
            assert 'allow' not in settings['permissions'] or 'mcp__ask_server' not in settings['permissions'].get('allow', [])

    def test_create_additional_settings_with_env_variables(self):
        """Test creating settings with environment variables."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            env_vars = {
                'API_KEY': 'secret123',
                'DEBUG': 'true',
            }

            setup_environment.create_additional_settings(
                {},
                claude_dir,
                'test',
                env=env_vars,
            )

            settings_file = claude_dir / 'test-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            assert settings['env'] == env_vars

    @patch('setup_environment.download_file')
    @patch('platform.system', return_value='Windows')
    @patch('shutil.which', return_value='py')
    def test_create_additional_settings_hooks_windows_python(self, mock_which, _mock_system, mock_download):
        """Test hook configuration with Python scripts on Windows."""
        del mock_which  # Unused but required for patch
        del _mock_system  # Unused but required for patch
        mock_download.return_value = True

        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)
            hooks_dir = claude_dir / 'hooks'
            hooks_dir.mkdir(parents=True, exist_ok=True)

            # Create a dummy hook file
            hook_file = hooks_dir / 'test.py'
            hook_file.write_text('print("test")')

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

            setup_environment.create_additional_settings(
                hooks,
                claude_dir,
                'test',
            )

            settings_file = claude_dir / 'test-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            # Should use py command on Windows
            hook_cmd = settings['hooks']['PostToolUse'][0]['hooks'][0]['command']
            assert 'py' in hook_cmd
            assert hook_file.as_posix() in hook_cmd

    @patch('setup_environment.handle_resource')
    @patch('platform.system', return_value='Linux')
    def test_create_additional_settings_hooks_linux(self, _mock_system, mock_download):
        """Test hook configuration on Linux."""
        mock_download.return_value = True

        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)
            hooks_dir = claude_dir / 'hooks'
            hooks_dir.mkdir(parents=True, exist_ok=True)

            hook_file = hooks_dir / 'test.py'
            hook_file.write_text('#!/usr/bin/env python3\nprint("test")')

            hooks = {
                'files': ['hooks/test.py'],
                'events': [
                    {
                        'event': 'PostToolUse',
                        'matcher': '',
                        'type': 'shell',
                        'command': 'test.py',
                    },
                ],
            }

            result = setup_environment.create_additional_settings(
                hooks,
                claude_dir,
                'test',
                config_source='https://example.com/config.yaml',
            )

            assert result is True
            # Note: With uv run, executable permissions are no longer needed
            # The script is executed via: uv run --python 3.12 script.py

    def test_create_additional_settings_hooks_invalid(self):
        """Test handling invalid hook configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            hooks = {
                'events': [
                    {
                        'event': 'PostToolUse',
                        # Missing 'command' field
                    },
                ],
            }

            result = setup_environment.create_additional_settings(
                hooks,
                claude_dir,
                'test',
            )

            # Should still succeed but skip invalid hook
            assert result is True

    def test_create_additional_settings_non_python_hook(self):
        """Test hook configuration with non-Python script."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            hooks = {
                'events': [
                    {
                        'event': 'PreToolUse',
                        'matcher': 'Bash',
                        'type': 'command',
                        'command': 'echo "test"',
                    },
                ],
            }

            setup_environment.create_additional_settings(
                hooks,
                claude_dir,
                'test',
            )

            settings_file = claude_dir / 'test-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            # Command should be used as-is
            hook_cmd = settings['hooks']['PreToolUse'][0]['hooks'][0]['command']
            assert hook_cmd == 'echo "test"'

    def test_create_additional_settings_save_failure(self):
        """Test handling save failure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            # Make directory read-only to cause save failure
            settings_file = claude_dir / 'test-additional-settings.json'
            settings_file.write_text('dummy')

            with patch('builtins.open', side_effect=PermissionError('Cannot write')):
                result = setup_environment.create_additional_settings(
                    {},
                    claude_dir,
                    'test',
                )

            assert result is False


class TestCreateLauncherScriptEdgeCases:
    """Test launcher script creation edge cases."""

    @patch('platform.system', return_value='Windows')
    def test_create_launcher_windows_without_prompt(self, _mock_system):
        """Test creating Windows launcher without system prompt."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            launcher = setup_environment.create_launcher_script(
                claude_dir,
                'test-env',
                None,  # No system prompt
            )

            assert launcher is not None
            # Check shared script doesn't reference prompt
            shared_script = claude_dir / 'launch-test-env.sh'
            content = shared_script.read_text()
            assert '--append-system-prompt' not in content

    @patch('platform.system', return_value='Linux')
    def test_create_launcher_linux_with_prompt(self, _mock_system):
        """Test creating Linux launcher with system prompt (default mode='replace')."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            launcher = setup_environment.create_launcher_script(
                claude_dir,
                'test-env',
                'custom-prompt.md',
            )

            assert launcher is not None
            content = launcher.read_text()
            assert 'custom-prompt.md' in content
            assert '--system-prompt' in content  # Default mode is 'replace'

    @patch('platform.system', return_value='Linux')
    def test_create_launcher_with_mode_append(self, _mock_system):
        """Test creating launcher with mode='append'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            launcher = setup_environment.create_launcher_script(
                claude_dir,
                'test-env',
                'prompt.md',
                mode='append',
            )

            assert launcher is not None
            content = launcher.read_text()
            assert 'prompt.md' in content
            assert '--append-system-prompt' in content
            assert '--system-prompt' not in content or '--append-system-prompt' in content

    @patch('platform.system', return_value='Linux')
    def test_create_launcher_with_mode_replace(self, _mock_system):
        """Test creating launcher with explicit mode='replace'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            launcher = setup_environment.create_launcher_script(
                claude_dir,
                'test-env',
                'prompt.md',
                mode='replace',
            )

            assert launcher is not None
            content = launcher.read_text()
            assert 'prompt.md' in content
            assert '--system-prompt' in content
            assert '--append-system-prompt' not in content

    @patch('platform.system', return_value='Windows')
    def test_create_launcher_windows_mode_append(self, _mock_system):
        """Test creating Windows launcher with mode='append'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            launcher = setup_environment.create_launcher_script(
                claude_dir,
                'test-env',
                'prompt.md',
                mode='append',
            )

            assert launcher is not None
            # Check shared script for correct flag
            shared_script = claude_dir / 'launch-test-env.sh'
            content = shared_script.read_text()
            assert '--append-system-prompt' in content
            assert 'exec claude --append-system-prompt' in content

    @patch('platform.system', return_value='Windows')
    def test_create_launcher_windows_mode_replace(self, _mock_system):
        """Test creating Windows launcher with mode='replace'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            launcher = setup_environment.create_launcher_script(
                claude_dir,
                'test-env',
                'prompt.md',
                mode='replace',
            )

            assert launcher is not None
            # Check shared script for correct flag
            shared_script = claude_dir / 'launch-test-env.sh'
            content = shared_script.read_text()
            assert '--system-prompt' in content
            assert 'exec claude --system-prompt' in content

    def test_create_launcher_script_exception(self):
        """Test launcher creation with exception."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            with patch('pathlib.Path.write_text', side_effect=Exception('Write failed')):
                launcher = setup_environment.create_launcher_script(
                    claude_dir,
                    'test-env',
                )

            assert launcher is None


class TestRegisterGlobalCommandEdgeCases:
    """Test global command registration edge cases."""

    @patch('platform.system', return_value='Windows')
    @patch('setup_environment.run_command')
    @patch.dict('os.environ', {'PATH': 'C:\\existing\\path'})
    def test_register_global_command_windows_update_path(self, mock_run, _mock_system):
        """Test updating PATH on Windows."""
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        with tempfile.TemporaryDirectory() as tmpdir, patch('pathlib.Path.home', return_value=Path(tmpdir)):
            launcher = Path(tmpdir) / 'launcher.ps1'
            launcher.write_text('# Launcher')

            result = setup_environment.register_global_command(launcher, 'test-cmd')

            assert result is True
            # Check setx was called to update PATH
            setx_called = any('setx' in str(call) for call in mock_run.call_args_list)
            assert setx_called

    @patch('platform.system', return_value='Windows')
    def test_register_global_command_windows_existing_wrappers(self, _mock_system):
        """Test registering command when wrapper files already exist on Windows."""
        with tempfile.TemporaryDirectory() as tmpdir:
            launcher = Path(tmpdir) / 'launcher.ps1'
            launcher.write_text('# Launcher')

            local_bin = Path(tmpdir) / '.local' / 'bin'
            local_bin.mkdir(parents=True, exist_ok=True)

            # Create existing wrapper files
            existing_cmd = local_bin / 'test-cmd.cmd'
            existing_ps1 = local_bin / 'test-cmd.ps1'
            existing_bash = local_bin / 'test-cmd'

            existing_cmd.write_text('@echo off\necho old')
            existing_ps1.write_text('# Old PowerShell')
            existing_bash.write_text('#!/bin/bash\necho old')

            with patch('pathlib.Path.home', return_value=Path(tmpdir)):
                result = setup_environment.register_global_command(launcher, 'test-cmd')

            assert result is True
            # Verify files were overwritten with new content
            assert 'Global test-cmd command for CMD' in existing_cmd.read_text()
            assert 'Global test-cmd command for PowerShell' in existing_ps1.read_text()
            assert 'launch-test-cmd.sh' in existing_bash.read_text()

    def test_register_global_command_exception(self):
        """Test command registration with exception."""
        with tempfile.TemporaryDirectory() as tmpdir:
            launcher = Path(tmpdir) / 'launcher.sh'
            launcher.write_text('#!/bin/bash')

            # Mock mkdir to fail
            with patch('pathlib.Path.mkdir', side_effect=Exception('Cannot create directory')):
                result = setup_environment.register_global_command(launcher, 'test-cmd')

            # register_global_command returns False on exceptions
            assert result is False


class TestMainFunctionErrorPaths:
    """Test main function error paths and edge cases."""

    @patch('setup_environment.load_config_from_source')
    def test_main_config_load_exception(self, mock_load):
        """Test main with config loading exception."""
        mock_load.side_effect = Exception('Config load failed')

        with patch('sys.argv', ['setup_environment.py', 'test']), patch('sys.exit') as mock_exit:
            setup_environment.main()
            mock_exit.assert_called_with(1)

    @patch('setup_environment.load_config_from_source')
    @patch('setup_environment.find_command_robust', return_value=None)
    def test_main_skip_install_claude_not_found(self, mock_find, mock_load):
        """Test main with --skip-install but Claude not found."""
        del mock_find  # Unused but required for patch
        mock_load.return_value = ({'name': 'Test'}, 'test.yaml')

        with patch('sys.argv', ['setup_environment.py', 'test', '--skip-install']), patch('sys.exit') as mock_exit:
            setup_environment.main()
            mock_exit.assert_called_with(1)

    @patch('setup_environment.load_config_from_source')
    @patch('setup_environment.validate_all_config_files', return_value=(True, []))
    @patch('setup_environment.install_claude', return_value=True)
    @patch('setup_environment.install_dependencies', return_value=True)
    @patch('setup_environment.process_resources', return_value=True)
    @patch('setup_environment.handle_resource', return_value=True)
    @patch('setup_environment.is_admin', return_value=True)
    @patch('setup_environment.configure_all_mcp_servers', return_value=True)
    @patch('setup_environment.create_additional_settings', return_value=True)
    @patch('setup_environment.create_launcher_script', return_value=None)
    @patch('pathlib.Path.mkdir')
    def test_main_no_launcher_created(
        self,
        _mock_mkdir,
        mock_launcher,
        mock_settings,
        mock_mcp,
        mock_is_admin,
        mock_handle_resource,
        mock_process_resources,
        mock_deps,
        mock_install,
        mock_validate,
        mock_load,
    ):
        """Test main when launcher creation fails."""
        assert mock_is_admin.return_value is True
        del _mock_mkdir  # Unused but required for patch
        del mock_launcher  # Unused but required for patch
        del mock_settings  # Unused but required for patch
        del mock_mcp  # Unused but required for patch
        del mock_handle_resource  # Unused but required for patch
        del mock_process_resources  # Unused but required for patch
        del mock_deps  # Unused but required for patch
        del mock_install  # Unused but required for patch
        del mock_validate  # Unused but required for patch
        mock_load.return_value = (
            {
                'name': 'Test',
                'command-defaults': {
                    'system-prompt': 'prompts/test.md',
                },
            },
            'test.yaml',
        )

        with patch('sys.argv', ['setup_environment.py', 'test']), patch('sys.exit') as mock_exit:
            setup_environment.main()
            mock_exit.assert_not_called()  # Should continue despite launcher failure

    @patch('setup_environment.is_admin', return_value=True)
    @patch.dict('os.environ', {'CLAUDE_ENV_CONFIG': 'env-config'})
    @patch('setup_environment.load_config_from_source')
    @patch('setup_environment.install_claude', return_value=True)
    @patch('setup_environment.install_dependencies', return_value=True)
    @patch('setup_environment.process_resources', return_value=True)
    @patch('setup_environment.configure_all_mcp_servers', return_value=True)
    @patch('setup_environment.create_additional_settings', return_value=True)
    @patch('setup_environment.create_launcher_script')
    @patch('setup_environment.register_global_command', return_value=True)
    @patch('pathlib.Path.mkdir')
    def test_main_from_env_variable(
        self,
        _mock_mkdir,
        mock_register,
        mock_launcher,
        mock_settings,
        mock_mcp,
        mock_download,
        mock_deps,
        mock_install,
        mock_load,
        mock_is_admin,
    ):
        """Test main using CLAUDE_ENV_CONFIG environment variable."""
        assert mock_is_admin.return_value is True
        del _mock_mkdir  # Unused but required for patch
        del mock_register  # Unused but required for patch
        del mock_settings  # Unused but required for patch
        del mock_mcp  # Unused but required for patch
        del mock_download  # Unused but required for patch
        del mock_deps  # Unused but required for patch
        del mock_install  # Unused but required for patch
        mock_load.return_value = ({'name': 'Env Test'}, 'env-config.yaml')
        mock_launcher.return_value = Path('/tmp/launcher')

        with (
            patch('sys.argv', ['setup_environment.py']),  # No config argument
            patch('sys.exit') as mock_exit,
        ):
            setup_environment.main()
            mock_exit.assert_not_called()
            mock_load.assert_called_with('env-config', None)

    @patch('setup_environment.is_admin', return_value=True)
    @patch('setup_environment.load_config_from_source')
    @patch('setup_environment.validate_all_config_files')
    @patch('setup_environment.install_claude', return_value=True)
    @patch('setup_environment.install_dependencies', return_value=True)
    @patch('setup_environment.process_resources', return_value=True)
    @patch('setup_environment.handle_resource', return_value=True)
    @patch('setup_environment.configure_all_mcp_servers', return_value=True)
    @patch('setup_environment.create_additional_settings', return_value=True)
    @patch('setup_environment.create_launcher_script')
    @patch('setup_environment.register_global_command', return_value=True)
    @patch('pathlib.Path.mkdir')
    def test_main_with_all_features(
        self,
        _mock_mkdir,
        mock_register,
        mock_launcher,
        mock_settings,
        mock_mcp,
        mock_download_resource,
        mock_download,
        mock_deps,
        mock_install,
        mock_validate,
        mock_load,
        mock_is_admin,
    ):
        """Test main with all configuration features enabled."""
        assert mock_is_admin.return_value is True
        del _mock_mkdir  # Unused but required for patch
        del mock_download_resource  # Unused but required for patch

        # Mock validation to succeed
        mock_validate.return_value = (True, [])

        mock_load.return_value = (
            {
                'name': 'Full Test',
                'command-name': 'full-test',
                'base-url': 'https://example.com/base/{path}',
                'model': 'claude-3-opus',
                'permissions': {
                    'defaultMode': 'ask',
                    'allow': ['tool__*'],
                    'deny': ['mcp__dangerous'],
                    'ask': ['mcp__sensitive'],
                },
                'env-variables': {
                    'API_KEY': 'test123',
                    'DEBUG': 'true',
                },
                'dependencies': {
                    'windows': ['npm install test'],
                },
                'agents': ['agents/test.md'],
                'slash-commands': ['commands/test.md'],
                'command-defaults': {
                    'system-prompt': 'prompts/test.md',
                },
                'mcp-servers': [
                    {'name': 'test-server'},
                    {'name': 'another-server'},
                ],
                'hooks': {
                    'files': ['hooks/test.py'],
                    'events': [
                        {
                            'event': 'PostToolUse',
                            'matcher': 'Edit',
                            'command': 'test.py',
                        },
                    ],
                },
            },
            'full-test.yaml',
        )

        mock_launcher.return_value = Path('/tmp/launcher')

        with (
            patch('sys.argv', ['setup_environment.py', 'full-test', '--auth', 'token123']),
            patch('sys.exit') as mock_exit,
        ):
            setup_environment.main()
            mock_exit.assert_not_called()

            # Verify all components were called
            mock_install.assert_called_once()
            mock_deps.assert_called_once()
            mock_download.assert_called()
            mock_mcp.assert_called_once()
            mock_settings.assert_called_once()
            mock_register.assert_called_once()


class TestInstallDependenciesEdgeCases:
    """Test dependency installation edge cases."""

    @patch('platform.system', return_value='Windows')
    @patch('setup_environment.run_command')
    def test_install_dependencies_windows_powershell_fallback(self, mock_run, _mock_system):
        """Test PowerShell fallback for unknown commands on Windows."""
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        result = setup_environment.install_dependencies({'windows': ['custom-command install package']})
        assert result is True

        # Should use PowerShell for unknown command
        call_args = mock_run.call_args[0][0]
        assert 'powershell' in call_args

    @patch('platform.system', return_value='Linux')
    @patch('setup_environment.run_command')
    def test_install_dependencies_uv_tool_force_linux(self, mock_run, _mock_system):
        """Test uv tool install with force flag on Linux."""
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        result = setup_environment.install_dependencies({'linux': ['uv tool install pytest']})
        assert result is True

        # Should add --force flag
        call_args = mock_run.call_args[0][0]
        assert 'uv tool install --force pytest' in ' '.join(call_args)

    @patch('platform.system', return_value='Windows')
    @patch('setup_environment.run_command')
    def test_install_dependencies_failure_continues(self, mock_run, _mock_system):
        """Test that dependency installation continues after failure."""
        mock_run.side_effect = [
            subprocess.CompletedProcess([], 1, '', 'Error'),  # First fails
            subprocess.CompletedProcess([], 0, '', ''),  # Second succeeds
        ]

        result = setup_environment.install_dependencies({'windows': ['failing-dep', 'working-dep']})
        assert result is True
        assert mock_run.call_count == 2


class TestDeriveBaseURLEdgeCases:
    """Test base URL derivation edge cases."""

    def test_derive_base_url_github_api(self):
        """Test deriving base URL from GitHub API URL."""
        url = 'https://api.github.com/repos/user/repo/contents/config.yaml'
        result = setup_environment.derive_base_url(url)
        assert result == 'https://api.github.com/repos/user/repo/contents/{path}'

    def test_derive_base_url_gitlab_api_no_ref(self):
        """Test deriving base URL from GitLab API without ref parameter."""
        url = 'https://gitlab.com/api/v4/projects/123/repository/files/config.yaml/raw'
        result = setup_environment.derive_base_url(url)
        assert result == 'https://gitlab.com/api/v4/projects/123/repository/files/{path}/raw'

    def test_derive_base_url_github_raw_short_path(self):
        """Test GitHub raw URL with insufficient path components."""
        url = 'https://raw.githubusercontent.com/user/repo'
        result = setup_environment.derive_base_url(url)
        assert result == 'https://raw.githubusercontent.com/user/{path}'

    def test_derive_base_url_single_component(self):
        """Test URL with single path component."""
        url = 'https://example.com'
        result = setup_environment.derive_base_url(url)
        # When URL has no path to split, it returns generic pattern
        assert result == 'https://{path}'


class TestSystemPromptWithUserFlags:
    """Test system prompt application with user-provided flags.

    This test class covers the critical bug fix where system prompts were not
    applied when commands were invoked with additional flags (e.g., --continue).
    The bug was caused by incorrect argument ordering where user flags ($@)
    were placed after --settings, disrupting Claude CLI parsing.
    """

    @patch('platform.system', return_value='Windows')
    def test_windows_launcher_arguments_order_with_prompt_replace_mode(self, _mock_system):
        """Test Windows shared script places user args before --settings (replace mode)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            launcher = setup_environment.create_launcher_script(
                claude_dir,
                'test-cmd',
                'prompt.md',
                mode='replace',
            )

            assert launcher is not None
            shared_script = claude_dir / 'launch-test-cmd.sh'
            assert shared_script.exists()

            content = shared_script.read_text()

            # Verify correct argument ordering: prompt flag + content + user args + settings
            assert '--system-prompt' in content
            assert 'exec claude --system-prompt "$PROMPT_CONTENT" "$@" --settings "$SETTINGS_WIN"' in content

    @patch('platform.system', return_value='Windows')
    def test_windows_launcher_arguments_order_with_prompt_append_mode(self, _mock_system):
        """Test Windows shared script places user args before --settings (append mode)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            launcher = setup_environment.create_launcher_script(
                claude_dir,
                'test-cmd',
                'prompt.md',
                mode='append',
            )

            assert launcher is not None
            shared_script = claude_dir / 'launch-test-cmd.sh'
            content = shared_script.read_text()

            # Verify correct argument ordering with append mode
            assert '--append-system-prompt' in content
            assert 'exec claude --append-system-prompt "$PROMPT_CONTENT" "$@" --settings "$SETTINGS_WIN"' in content

    @patch('platform.system', return_value='Windows')
    def test_windows_launcher_arguments_order_without_prompt(self, _mock_system):
        """Test Windows shared script places user args before --settings (no prompt)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            launcher = setup_environment.create_launcher_script(
                claude_dir,
                'test-cmd',
                None,  # No system prompt
            )

            assert launcher is not None
            shared_script = claude_dir / 'launch-test-cmd.sh'
            content = shared_script.read_text()

            # Verify correct argument ordering without prompt
            assert 'exec claude "$@" --settings "$SETTINGS_WIN"' in content

    @patch('platform.system', return_value='Linux')
    def test_linux_launcher_arguments_order_with_prompt_replace_mode(self, _mock_system):
        """Test Linux launcher uses single command with user args before --settings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            launcher = setup_environment.create_launcher_script(
                claude_dir,
                'test-cmd',
                'prompt.md',
                mode='replace',
            )

            assert launcher is not None
            content = launcher.read_text()

            # Should use single exec command, not if-else branches
            assert '--system-prompt' in content
            # Verify user args come before --settings
            assert 'claude --system-prompt "$PROMPT_CONTENT" "$@" --settings "$SETTINGS_PATH"' in content

    @patch('platform.system', return_value='Linux')
    def test_linux_launcher_arguments_order_with_prompt_append_mode(self, _mock_system):
        """Test Linux launcher with append mode uses correct argument order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            launcher = setup_environment.create_launcher_script(
                claude_dir,
                'test-cmd',
                'prompt.md',
                mode='append',
            )

            assert launcher is not None
            content = launcher.read_text()

            assert '--append-system-prompt' in content
            assert 'claude --append-system-prompt "$PROMPT_CONTENT" "$@" --settings "$SETTINGS_PATH"' in content

    @patch('platform.system', return_value='Linux')
    def test_linux_launcher_arguments_order_without_prompt(self, _mock_system):
        """Test Linux launcher without prompt uses correct argument order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            launcher = setup_environment.create_launcher_script(
                claude_dir,
                'test-cmd',
                None,  # No system prompt
            )

            assert launcher is not None
            content = launcher.read_text()

            # Should use single command, not if-else branches
            assert 'claude "$@" --settings "$SETTINGS_PATH"' in content

    @patch('platform.system', return_value='Darwin')
    def test_macos_launcher_arguments_order(self, _mock_system):
        """Test macOS launcher (same as Linux) uses correct argument order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            launcher = setup_environment.create_launcher_script(
                claude_dir,
                'test-cmd',
                'prompt.md',
                mode='replace',
            )

            assert launcher is not None
            content = launcher.read_text()

            # macOS should behave like Linux
            assert 'claude --system-prompt "$PROMPT_CONTENT" "$@" --settings "$SETTINGS_PATH"' in content

    @patch('platform.system', return_value='Windows')
    def test_windows_no_conditional_branches_for_args(self, _mock_system):
        """Test Windows shared script doesn't use conditionals for argument handling."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            _ = setup_environment.create_launcher_script(
                claude_dir,
                'test-cmd',
                'prompt.md',
            )

            shared_script = claude_dir / 'launch-test-cmd.sh'
            content = shared_script.read_text()

            # Should NOT contain conditional logic for $@
            # The exec command should always include "$@"
            assert 'if [ $# -gt 0 ]' not in content
            assert 'exec claude' in content
            assert '"$@"' in content

    @patch('platform.system', return_value='Linux')
    def test_linux_no_conditional_branches_for_args(self, _mock_system):
        """Test Linux launcher doesn't use conditionals for argument handling."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            launcher = setup_environment.create_launcher_script(
                claude_dir,
                'test-cmd',
                'prompt.md',
            )

            content = launcher.read_text()

            # Should use single command, not if-else for args
            assert 'claude --system-prompt "$PROMPT_CONTENT" "$@" --settings "$SETTINGS_PATH"' in content
            # But the actual claude command should not be in a conditional
            claude_lines = [line for line in content.split('\n') if line.strip().startswith('claude ')]
            # All claude command lines should not be inside conditionals
            for claude_line in claude_lines:
                # The line should contain both "$@" and --settings
                if '--settings' in claude_line:
                    assert '"$@"' in claude_line
                    # Verify order: user args before --settings
                    args_pos = claude_line.index('"$@"')
                    settings_pos = claude_line.index('--settings')
                    assert args_pos < settings_pos, f'User args must come before --settings: {claude_line}'


class TestConditionalSystemPromptLoading:
    """Test conditional system prompt loading based on resume flags.

    This test class covers the implementation of Strategy 1 from the investigation
    report: conditional system prompt loading that detects resume flags and only
    applies custom prompts for new sessions, preserving original prompts for
    continued sessions.
    """

    @patch('platform.system', return_value='Windows')
    def test_windows_launcher_detects_continue_flags(self, _mock_system):
        """Test Windows shared script has logic to detect --continue and --resume flags."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            launcher = setup_environment.create_launcher_script(
                claude_dir,
                'test-cmd',
                'prompt.md',
                mode='replace',
            )

            assert launcher is not None
            shared_script = claude_dir / 'launch-test-cmd.sh'
            content = shared_script.read_text()

            # Verify flag detection logic exists
            assert 'HAS_CONTINUE=false' in content
            assert 'for arg in "$@"' in content
            assert '--continue' in content
            assert '-c' in content
            assert '--resume' in content
            assert '-r' in content

    @patch('platform.system', return_value='Windows')
    def test_windows_launcher_conditional_branches(self, _mock_system):
        """Test Windows shared script has conditional execution based on resume flags."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            _launcher = setup_environment.create_launcher_script(
                claude_dir,
                'test-cmd',
                'prompt.md',
                mode='replace',
            )

            shared_script = claude_dir / 'launch-test-cmd.sh'
            content = shared_script.read_text()

            # Verify conditional branches exist
            assert 'if [ "$HAS_CONTINUE" = true ]' in content
            assert 'else' in content
            assert 'fi' in content

            # Verify continue mode doesn't apply prompt
            lines = content.split('\n')
            in_continue_branch = False
            in_new_session_branch = False

            for line in lines:
                if 'if [ "$HAS_CONTINUE" = true ]' in line:
                    in_continue_branch = True
                    in_new_session_branch = False
                elif 'else' in line and in_continue_branch:
                    in_continue_branch = False
                    in_new_session_branch = True
                elif 'fi' in line and (in_continue_branch or in_new_session_branch):
                    break

                # In continue branch: should NOT have prompt loading
                if in_continue_branch and 'exec claude' in line:
                    assert '--system-prompt' not in line
                    assert 'PROMPT_CONTENT' not in line

                # In new session branch: should have prompt loading
                if in_new_session_branch and 'exec claude' in line:
                    assert '--system-prompt' in line
                    assert 'PROMPT_CONTENT' in line

    @patch('platform.system', return_value='Windows')
    def test_windows_launcher_append_mode_conditional(self, _mock_system):
        """Test Windows shared script with append mode has conditional logic."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            _launcher = setup_environment.create_launcher_script(
                claude_dir,
                'test-cmd',
                'prompt.md',
                mode='append',
            )

            shared_script = claude_dir / 'launch-test-cmd.sh'
            content = shared_script.read_text()

            # Should use append flag in new session branch
            lines = content.split('\n')
            in_new_session_branch = False

            for line in lines:
                if 'else' in line:
                    in_new_session_branch = True
                elif 'fi' in line:
                    in_new_session_branch = False

                if in_new_session_branch and 'exec claude' in line:
                    assert '--append-system-prompt' in line

    @patch('platform.system', return_value='Linux')
    def test_linux_launcher_detects_continue_flags(self, _mock_system):
        """Test Linux launcher has logic to detect --continue and --resume flags."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            launcher = setup_environment.create_launcher_script(
                claude_dir,
                'test-cmd',
                'prompt.md',
                mode='replace',
            )

            content = launcher.read_text()

            # Verify flag detection logic exists
            assert 'HAS_CONTINUE=false' in content
            assert 'for arg in "$@"' in content
            assert '--continue' in content
            assert '-c' in content
            assert '--resume' in content
            assert '-r' in content

    @patch('platform.system', return_value='Linux')
    def test_linux_launcher_conditional_branches(self, _mock_system):
        """Test Linux launcher has conditional execution based on resume flags."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            launcher = setup_environment.create_launcher_script(
                claude_dir,
                'test-cmd',
                'prompt.md',
                mode='replace',
            )

            content = launcher.read_text()

            # Verify conditional branches exist
            assert 'if [ "$HAS_CONTINUE" = true ]' in content
            assert 'else' in content
            assert 'fi' in content

            # Verify continue mode doesn't apply prompt
            lines = content.split('\n')
            in_continue_branch = False
            in_new_session_branch = False

            for line in lines:
                if 'if [ "$HAS_CONTINUE" = true ]' in line:
                    in_continue_branch = True
                    in_new_session_branch = False
                elif 'else' in line and in_continue_branch:
                    in_continue_branch = False
                    in_new_session_branch = True
                elif 'fi' in line and (in_continue_branch or in_new_session_branch):
                    break

                # In continue branch: should NOT have prompt loading
                if in_continue_branch and 'claude ' in line and '--settings' in line:
                    assert '--system-prompt' not in line
                    assert 'PROMPT_CONTENT' not in line

                # In new session branch: should have prompt loading
                if in_new_session_branch and 'claude ' in line and '--settings' in line:
                    assert '--system-prompt' in line
                    assert 'PROMPT_CONTENT' in line

    @patch('platform.system', return_value='Linux')
    def test_linux_launcher_append_mode_conditional(self, _mock_system):
        """Test Linux launcher with append mode has conditional logic."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            launcher = setup_environment.create_launcher_script(
                claude_dir,
                'test-cmd',
                'prompt.md',
                mode='append',
            )

            content = launcher.read_text()

            # Should use append flag in new session branch
            lines = content.split('\n')
            in_new_session_branch = False

            for line in lines:
                if 'else' in line:
                    in_new_session_branch = True
                elif 'fi' in line:
                    in_new_session_branch = False

                if in_new_session_branch and 'claude ' in line and '--settings' in line:
                    assert '--append-system-prompt' in line

    @patch('platform.system', return_value='Darwin')
    def test_macos_launcher_conditional_logic(self, _mock_system):
        """Test macOS launcher (same as Linux) has conditional logic."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            launcher = setup_environment.create_launcher_script(
                claude_dir,
                'test-cmd',
                'prompt.md',
                mode='replace',
            )

            content = launcher.read_text()

            # macOS should behave like Linux
            assert 'HAS_CONTINUE=false' in content
            assert 'if [ "$HAS_CONTINUE" = true ]' in content

    @patch('platform.system', return_value='Windows')
    def test_windows_launcher_all_resume_flags(self, _mock_system):
        """Test Windows launcher detects all resume flag variations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            _launcher = setup_environment.create_launcher_script(
                claude_dir,
                'test-cmd',
                'prompt.md',
            )

            shared_script = claude_dir / 'launch-test-cmd.sh'
            content = shared_script.read_text()

            # All four flag variations should be checked
            assert '"$arg" == "--continue"' in content
            assert '"$arg" == "-c"' in content
            assert '"$arg" == "--resume"' in content
            assert '"$arg" == "-r"' in content

    @patch('platform.system', return_value='Linux')
    def test_linux_launcher_all_resume_flags(self, _mock_system):
        """Test Linux launcher detects all resume flag variations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            launcher = setup_environment.create_launcher_script(
                claude_dir,
                'test-cmd',
                'prompt.md',
            )

            content = launcher.read_text()

            # All four flag variations should be checked
            assert '"$arg" == "--continue"' in content
            assert '"$arg" == "-c"' in content
            assert '"$arg" == "--resume"' in content
            assert '"$arg" == "-r"' in content

    @patch('platform.system', return_value='Windows')
    def test_windows_launcher_without_prompt_no_conditional(self, _mock_system):
        """Test Windows launcher without prompt doesn't have conditional logic."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            _launcher = setup_environment.create_launcher_script(
                claude_dir,
                'test-cmd',
                None,  # No system prompt
            )

            shared_script = claude_dir / 'launch-test-cmd.sh'
            content = shared_script.read_text()

            # Should not have conditional logic when no prompt is configured
            assert 'HAS_CONTINUE' not in content
            assert 'if [ "$HAS_CONTINUE" = true ]' not in content

    @patch('platform.system', return_value='Linux')
    def test_linux_launcher_without_prompt_no_conditional(self, _mock_system):
        """Test Linux launcher without prompt doesn't have conditional logic."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            launcher = setup_environment.create_launcher_script(
                claude_dir,
                'test-cmd',
                None,  # No system prompt
            )

            content = launcher.read_text()

            # Should not have conditional logic when no prompt is configured
            assert 'HAS_CONTINUE' not in content
            assert 'if [ "$HAS_CONTINUE" = true ]' not in content

    @patch('platform.system', return_value='Windows')
    def test_windows_continue_branch_preserves_settings(self, _mock_system):
        """Test Windows continue branch still applies settings file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            _launcher = setup_environment.create_launcher_script(
                claude_dir,
                'test-cmd',
                'prompt.md',
            )

            shared_script = claude_dir / 'launch-test-cmd.sh'
            content = shared_script.read_text()

            # Find the continue branch
            lines = content.split('\n')
            in_continue_branch = False

            for line in lines:
                if 'if [ "$HAS_CONTINUE" = true ]' in line:
                    in_continue_branch = True
                elif 'else' in line:
                    break

                # Continue branch should still use settings
                if in_continue_branch and 'exec claude' in line:
                    assert '--settings "$SETTINGS_WIN"' in line

    @patch('platform.system', return_value='Linux')
    def test_linux_continue_branch_preserves_settings(self, _mock_system):
        """Test Linux continue branch still applies settings file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            launcher = setup_environment.create_launcher_script(
                claude_dir,
                'test-cmd',
                'prompt.md',
            )

            content = launcher.read_text()

            # Find the continue branch
            lines = content.split('\n')
            in_continue_branch = False

            for line in lines:
                if 'if [ "$HAS_CONTINUE" = true ]' in line:
                    in_continue_branch = True
                elif 'else' in line:
                    break

                # Continue branch should still use settings
                if in_continue_branch and 'claude ' in line:
                    assert '--settings "$SETTINGS_PATH"' in line

    @patch('platform.system', return_value='Linux')
    def test_linux_continue_mode_message(self, _mock_system):
        """Test Linux launcher shows appropriate message for continue mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            launcher = setup_environment.create_launcher_script(
                claude_dir,
                'test-cmd',
                'prompt.md',
            )

            content = launcher.read_text()

            # Should have different echo message for continue mode
            assert 'Resuming Claude Code session' in content or 'Continue mode' in content
