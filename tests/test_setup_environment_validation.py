"""Tests for pre-download validation functionality in setup_environment.py."""

import contextlib
import os
import sys
import tempfile
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

import setup_environment
from setup_environment import FileValidator


class TestFileValidator:
    """Test the unified FileValidator class."""

    def test_init_with_auth_param(self) -> None:
        """Test FileValidator initialization with auth parameter."""
        validator = FileValidator(auth_param='Bearer token123')
        assert validator.auth_param == 'Bearer token123'

    def test_init_without_auth_param(self) -> None:
        """Test FileValidator initialization without auth parameter."""
        validator = FileValidator()
        assert validator.auth_param is None

    @patch('setup_environment.urlopen')
    def test_check_with_head_success(self, mock_urlopen: MagicMock) -> None:
        """Test HEAD request success."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value = mock_response

        validator = FileValidator()
        result = validator._check_with_head('https://example.com/file.md', None)

        assert result is True
        mock_urlopen.assert_called_once()
        request = mock_urlopen.call_args[0][0]
        assert request.get_method() == 'HEAD'
        assert request.full_url == 'https://example.com/file.md'

    @patch('setup_environment.urlopen')
    def test_check_with_head_with_auth(self, mock_urlopen: MagicMock) -> None:
        """Test HEAD request with authentication headers."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value = mock_response

        validator = FileValidator()
        auth_headers = {'Authorization': 'Bearer token'}
        result = validator._check_with_head('https://example.com/file.md', auth_headers)

        assert result is True
        request = mock_urlopen.call_args[0][0]
        assert request.headers.get('Authorization') == 'Bearer token'

    @patch('setup_environment.urlopen')
    def test_check_with_head_not_found(self, mock_urlopen: MagicMock) -> None:
        """Test HEAD request with 404."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            'https://example.com/file.md',
            404,
            'Not Found',
            {},
            None,
        )

        validator = FileValidator()
        result = validator._check_with_head('https://example.com/file.md', None)

        assert result is False

    @patch('setup_environment.urlopen')
    def test_check_with_head_ssl_error_retry(self, mock_urlopen: MagicMock) -> None:
        """Test HEAD request with SSL error and successful retry."""
        mock_urlopen.side_effect = [
            urllib.error.URLError('SSL: CERTIFICATE_VERIFY_FAILED'),
            MagicMock(status=200),
        ]

        validator = FileValidator()
        result = validator._check_with_head('https://example.com/file.md', None)

        assert result is True
        assert mock_urlopen.call_count == 2
        second_call_context = mock_urlopen.call_args_list[1][1].get('context')
        assert second_call_context is not None

    @patch('setup_environment.urlopen')
    def test_check_with_head_non_ssl_error(self, mock_urlopen: MagicMock) -> None:
        """Test HEAD request with non-SSL URLError."""
        mock_urlopen.side_effect = urllib.error.URLError('Connection refused')

        validator = FileValidator()
        result = validator._check_with_head('https://example.com/file.md', None)

        assert result is False
        assert mock_urlopen.call_count == 1

    @patch('setup_environment.urlopen')
    def test_check_with_range_success_200(self, mock_urlopen: MagicMock) -> None:
        """Test successful Range request with 200 response."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value = mock_response

        validator = FileValidator()
        result = validator._check_with_range('https://example.com/file.md', None)

        assert result is True
        request = mock_urlopen.call_args[0][0]
        assert request.headers.get('Range') == 'bytes=0-0'

    @patch('setup_environment.urlopen')
    def test_check_with_range_success_206(self, mock_urlopen: MagicMock) -> None:
        """Test successful Range request with 206 partial content response."""
        mock_response = MagicMock()
        mock_response.status = 206
        mock_urlopen.return_value = mock_response

        validator = FileValidator()
        result = validator._check_with_range('https://example.com/file.md', None)

        assert result is True

    @patch('setup_environment.urlopen')
    def test_check_with_range_with_auth(self, mock_urlopen: MagicMock) -> None:
        """Test Range request with authentication headers."""
        mock_response = MagicMock()
        mock_response.status = 206
        mock_urlopen.return_value = mock_response

        validator = FileValidator()
        auth_headers = {'Authorization': 'Token abc123', 'X-Custom': 'value'}
        result = validator._check_with_range('https://example.com/file.md', auth_headers)

        assert result is True
        request = mock_urlopen.call_args[0][0]
        assert request.headers.get('Authorization') == 'Token abc123'
        assert request.headers.get('X-custom') == 'value'
        assert request.headers.get('Range') == 'bytes=0-0'

    @patch('setup_environment.urlopen')
    def test_check_with_range_ssl_error_retry(self, mock_urlopen: MagicMock) -> None:
        """Test Range request with SSL error and successful retry."""
        mock_urlopen.side_effect = [
            urllib.error.URLError('certificate verify failed'),
            MagicMock(status=206),
        ]

        validator = FileValidator()
        result = validator._check_with_range('https://example.com/file.md', None)

        assert result is True
        assert mock_urlopen.call_count == 2

    @patch('setup_environment.urlopen')
    def test_check_with_range_http_error(self, mock_urlopen: MagicMock) -> None:
        """Test Range request with HTTP error."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            'https://example.com/file.md',
            416,
            'Range Not Satisfiable',
            {},
            None,
        )

        validator = FileValidator()
        result = validator._check_with_range('https://example.com/file.md', None)

        assert result is False

    @patch('setup_environment.urlopen')
    def test_check_with_range_generic_exception(self, mock_urlopen: MagicMock) -> None:
        """Test Range request with generic exception."""
        mock_urlopen.side_effect = Exception('Network error')

        validator = FileValidator()
        result = validator._check_with_range('https://example.com/file.md', None)

        assert result is False

    @patch('setup_environment.get_auth_headers')
    @patch.object(FileValidator, '_check_with_head')
    def test_validate_remote_url_generates_auth_per_url(
        self,
        mock_head: MagicMock,
        mock_auth: MagicMock,
    ) -> None:
        """Test that validate_remote_url generates auth for the specific URL.

        CRITICAL: This is the core bug fix test - verify auth is generated for the
        FILE URL, not the config source.
        """
        mock_auth.return_value = {'Authorization': 'Bearer token'}
        mock_head.return_value = True

        validator = FileValidator(auth_param='my_token')
        result = validator.validate_remote_url('https://github.com/user/repo/file.md')

        assert result == (True, 'HEAD')
        # CRITICAL: verify auth was generated for the FILE URL, not config source
        mock_auth.assert_called_once_with(
            'https://github.com/user/repo/file.md',
            'my_token',
        )

    @patch.object(FileValidator, '_check_with_head')
    @patch.object(FileValidator, '_check_with_range')
    def test_validate_remote_url_head_success(
        self,
        mock_range: MagicMock,
        mock_head: MagicMock,
    ) -> None:
        """Test validation succeeds with HEAD request."""
        mock_head.return_value = True
        mock_range.return_value = False

        validator = FileValidator()
        with patch('setup_environment.get_auth_headers', return_value=None):
            is_valid, method = validator.validate_remote_url('https://example.com/file.md')

        assert is_valid is True
        assert method == 'HEAD'
        mock_head.assert_called_once()
        mock_range.assert_not_called()

    @patch.object(FileValidator, '_check_with_head')
    @patch.object(FileValidator, '_check_with_range')
    def test_validate_remote_url_fallback_to_range(
        self,
        mock_range: MagicMock,
        mock_head: MagicMock,
    ) -> None:
        """Test validation falls back to Range when HEAD fails."""
        mock_head.return_value = False
        mock_range.return_value = True

        validator = FileValidator()
        with patch('setup_environment.get_auth_headers', return_value=None):
            is_valid, method = validator.validate_remote_url('https://example.com/file.md')

        assert is_valid is True
        assert method == 'Range'
        mock_head.assert_called_once()
        mock_range.assert_called_once()

    @patch.object(FileValidator, '_check_with_head')
    @patch.object(FileValidator, '_check_with_range')
    def test_validate_remote_url_both_fail(
        self,
        mock_range: MagicMock,
        mock_head: MagicMock,
    ) -> None:
        """Test validation fails when both methods fail."""
        mock_head.return_value = False
        mock_range.return_value = False

        validator = FileValidator()
        with patch('setup_environment.get_auth_headers', return_value=None):
            is_valid, method = validator.validate_remote_url('https://example.com/file.md')

        assert is_valid is False
        assert method == 'None'
        mock_head.assert_called_once()
        mock_range.assert_called_once()

    @patch('setup_environment.info')
    @patch('setup_environment.convert_gitlab_url_to_api')
    @patch('setup_environment.detect_repo_type')
    @patch.object(FileValidator, '_check_with_head')
    def test_validate_remote_url_gitlab_url_conversion(
        self,
        mock_head: MagicMock,
        mock_detect: MagicMock,
        mock_convert: MagicMock,
        mock_info: MagicMock,
    ) -> None:
        """Test that GitLab URLs are converted to API format for validation."""
        gitlab_web_url = 'https://gitlab.com/namespace/project/-/raw/main/file.md'
        gitlab_api_url = 'https://gitlab.com/api/v4/projects/namespace%2Fproject/repository/files/file.md/raw?ref=main'

        mock_detect.return_value = 'gitlab'
        mock_convert.return_value = gitlab_api_url
        mock_head.return_value = True

        validator = FileValidator()
        with patch('setup_environment.get_auth_headers', return_value=None):
            is_valid, method = validator.validate_remote_url(gitlab_web_url)

        assert is_valid is True
        assert method == 'HEAD'
        mock_detect.assert_called_once_with(gitlab_web_url)
        mock_convert.assert_called_once_with(gitlab_web_url)
        mock_info.assert_called_once_with(f'Using API URL for validation: {gitlab_api_url}')

    def test_validate_local_path_exists(self) -> None:
        """Test local file validation when file exists."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b'content')
            temp_path = f.name

        try:
            validator = FileValidator()
            result = validator.validate_local_path(temp_path)
            assert result == (True, 'Local')
        finally:
            Path(temp_path).unlink()

    def test_validate_local_path_not_exists(self) -> None:
        """Test local file validation when file doesn't exist."""
        validator = FileValidator()
        result = validator.validate_local_path('/nonexistent/path/file.md')
        assert result == (False, 'Local')

    def test_validate_local_path_is_directory(self) -> None:
        """Test local file validation when path is a directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            validator = FileValidator()
            result = validator.validate_local_path(tmpdir)
            assert result == (False, 'Local')

    def test_validate_chooses_remote_for_is_remote_true(self) -> None:
        """Test validate() uses validate_remote_url when is_remote=True."""
        with patch.object(FileValidator, 'validate_remote_url', return_value=(True, 'HEAD')) as mock:
            validator = FileValidator()
            result = validator.validate('https://example.com/file.md', is_remote=True)

            mock.assert_called_once_with('https://example.com/file.md')
            assert result == (True, 'HEAD')

    def test_validate_chooses_local_for_is_remote_false(self) -> None:
        """Test validate() uses validate_local_path when is_remote=False."""
        with patch.object(FileValidator, 'validate_local_path', return_value=(True, 'Local')) as mock:
            validator = FileValidator()
            result = validator.validate('/local/file.md', is_remote=False)

            mock.assert_called_once_with('/local/file.md')
            assert result == (True, 'Local')

    def test_results_accumulation(self) -> None:
        """Test that results are properly accumulated."""
        validator = FileValidator()
        validator.add_result('agent', 'agent.md', True, 'HEAD')
        validator.add_result('hook', 'hook.py', False, 'None')

        assert len(validator.results) == 2
        assert validator.results[0] == ('agent', 'agent.md', True, 'HEAD')
        assert validator.results[1] == ('hook', 'hook.py', False, 'None')

    def test_clear_results(self) -> None:
        """Test clearing accumulated results."""
        validator = FileValidator()
        validator.add_result('agent', 'agent.md', True, 'HEAD')
        validator.clear_results()

        assert len(validator.results) == 0


class TestLocalConfigWithRemoteFiles:
    """Tests for the specific bug: local config with remote files requiring auth.

    This is the core bug being fixed. These tests MUST pass after refactoring.
    """

    @patch('setup_environment.get_auth_headers')
    @patch('setup_environment.resolve_resource_path')
    @patch.object(FileValidator, '_check_with_head')
    def test_local_config_with_github_files_uses_file_url_for_auth(
        self,
        mock_head: MagicMock,
        mock_resolve: MagicMock,
        mock_auth: MagicMock,
    ) -> None:
        """Test that auth is generated for the FILE URL, not config source.

        BUG SCENARIO:
        - Config loaded from: C:/local/config.yaml
        - File to validate: https://raw.githubusercontent.com/user/repo/main/agent.md
        - Expected: get_auth_headers called with GitHub URL
        - Bug behavior: get_auth_headers not called (config_source is local)
        """
        mock_auth.return_value = {'Authorization': 'Bearer github_token'}
        mock_resolve.return_value = (
            'https://raw.githubusercontent.com/user/repo/main/agent.md',
            True,  # is_remote
        )
        mock_head.return_value = True

        config = {'agents': ['agent.md']}

        all_valid, results = setup_environment.validate_all_config_files(
            config,
            'C:/local/config.yaml',  # LOCAL config source
            auth_param='github_token',
        )

        assert all_valid is True
        # CRITICAL: Auth must be generated for the FILE URL
        mock_auth.assert_called()
        call_url = mock_auth.call_args[0][0]
        assert 'githubusercontent.com' in call_url
        assert 'C:' not in call_url  # Not the config source!

    @patch('setup_environment.get_auth_headers')
    @patch('setup_environment.resolve_resource_path')
    @patch.object(FileValidator, '_check_with_head')
    def test_local_config_with_gitlab_files_uses_file_url_for_auth(
        self,
        mock_head: MagicMock,
        mock_resolve: MagicMock,
        mock_auth: MagicMock,
    ) -> None:
        """Test GitLab files with local config source."""
        mock_auth.return_value = {'PRIVATE-TOKEN': 'gitlab_token'}
        mock_resolve.return_value = (
            'https://gitlab.com/user/repo/-/raw/main/agent.md',
            True,
        )
        mock_head.return_value = True

        config = {'agents': ['agent.md']}

        with patch('setup_environment.detect_repo_type', return_value=None):
            all_valid, results = setup_environment.validate_all_config_files(
                config,
                '/local/config.yaml',  # LOCAL config source
                auth_param='gitlab_token',
            )

        assert all_valid is True
        mock_auth.assert_called()
        call_url = mock_auth.call_args[0][0]
        assert 'gitlab.com' in call_url


class TestMixedAuthScenarios:
    """Tests for files requiring different authentication (GitHub + GitLab)."""

    @patch('setup_environment.detect_repo_type')
    @patch('setup_environment.get_auth_headers')
    @patch('setup_environment.resolve_resource_path')
    @patch.object(FileValidator, '_check_with_head')
    def test_mixed_github_and_gitlab_files(
        self,
        mock_head: MagicMock,
        mock_resolve: MagicMock,
        mock_auth: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """Test that different files get appropriate auth headers."""

        # Simulate different repo types
        def detect_side_effect(url: str) -> str | None:
            if 'github' in url:
                return 'github'
            if 'gitlab' in url:
                return 'gitlab'
            return None

        mock_detect.side_effect = detect_side_effect

        # Different auth headers per repo type
        def auth_side_effect(url: str, _param: str | None) -> dict[str, str]:
            if 'github' in url:
                return {'Authorization': 'Bearer github_token'}
            if 'gitlab' in url:
                return {'PRIVATE-TOKEN': 'gitlab_token'}
            return {}

        mock_auth.side_effect = auth_side_effect
        mock_head.return_value = True

        mock_resolve.side_effect = [
            ('https://raw.githubusercontent.com/user/repo/main/agent1.md', True),
            ('https://gitlab.com/user/repo/-/raw/main/agent2.md', True),
        ]

        config = {'agents': ['agent1.md', 'agent2.md']}

        all_valid, results = setup_environment.validate_all_config_files(
            config,
            '/local/config.yaml',
            auth_param='token',
        )

        assert all_valid is True
        assert len(results) == 2
        # Verify get_auth_headers was called twice with different URLs
        assert mock_auth.call_count == 2


class TestAuthEdgeCases:
    """Edge case tests for authentication scenarios."""

    @patch('setup_environment.get_auth_headers')
    @patch('setup_environment.resolve_resource_path')
    @patch.object(FileValidator, '_check_with_head')
    def test_public_file_with_auth_token_provided(
        self,
        mock_head: MagicMock,
        mock_resolve: MagicMock,
        mock_auth: MagicMock,
    ) -> None:
        """Test that public files work even when auth token is provided."""
        mock_auth.return_value = {'Authorization': 'Bearer token'}
        mock_resolve.return_value = ('https://example.com/public.md', True)
        mock_head.return_value = True

        config = {'agents': ['public.md']}

        all_valid, results = setup_environment.validate_all_config_files(
            config,
            '/local/config.yaml',
            auth_param='token',
        )

        assert all_valid is True

    @patch('setup_environment.get_auth_headers')
    @patch('setup_environment.resolve_resource_path')
    @patch.object(FileValidator, '_check_with_head')
    @patch.object(FileValidator, '_check_with_range')
    def test_private_file_without_auth_token(
        self,
        mock_range: MagicMock,
        mock_head: MagicMock,
        mock_resolve: MagicMock,
        mock_auth: MagicMock,
    ) -> None:
        """Test that private files fail gracefully without auth."""
        mock_auth.return_value = {}  # No auth headers
        mock_resolve.return_value = ('https://example.com/private.md', True)
        mock_head.return_value = False
        mock_range.return_value = False

        config = {'agents': ['private.md']}

        all_valid, results = setup_environment.validate_all_config_files(
            config,
            '/local/config.yaml',
            auth_param=None,
        )

        assert all_valid is False
        assert results[0][2] is False  # is_valid

    @patch('setup_environment.get_auth_headers')
    @patch('setup_environment.resolve_resource_path')
    @patch('setup_environment.urlopen')
    def test_network_failure_during_validation(
        self,
        mock_urlopen: MagicMock,
        mock_resolve: MagicMock,
        mock_auth: MagicMock,
    ) -> None:
        """Test handling of network failures."""
        mock_auth.return_value = {}
        mock_resolve.return_value = ('https://example.com/file.md', True)
        # urlopen raises exception, which is caught internally by _check_with_head
        mock_urlopen.side_effect = Exception('Connection refused')

        config = {'agents': ['file.md']}

        # Should not raise exception - network failures are handled gracefully
        all_valid, results = setup_environment.validate_all_config_files(
            config,
            '/local/config.yaml',
            auth_param=None,
        )

        assert all_valid is False


class TestValidateAllConfigFiles:
    """Test full configuration validation."""

    @patch('setup_environment.resolve_resource_path')
    @patch.object(FileValidator, 'validate')
    def test_validate_all_config_files_empty_config(
        self,
        mock_validate: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """Test validation with empty configuration."""
        del mock_resolve  # Unused but required by decorator
        config: dict[str, list[str]] = {}

        all_valid, results = setup_environment.validate_all_config_files(config, 'local')

        assert all_valid is True
        assert results == []
        mock_validate.assert_not_called()

    @patch('setup_environment.resolve_resource_path')
    @patch.object(FileValidator, 'validate')
    def test_validate_all_config_files_with_agents(
        self,
        mock_validate: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """Test validation with agents."""
        config = {
            'agents': ['agent1.md', 'agent2.md'],
        }
        mock_resolve.side_effect = [
            ('https://example.com/agent1.md', True),  # Remote
            ('https://example.com/agent2.md', True),  # Remote
        ]
        mock_validate.side_effect = [
            (True, 'HEAD'),
            (True, 'Range'),
        ]

        all_valid, results = setup_environment.validate_all_config_files(config, 'https://example.com')

        assert all_valid is True
        assert len(results) == 2
        assert results[0] == ('agent', 'agent1.md', True, 'HEAD')
        assert results[1] == ('agent', 'agent2.md', True, 'Range')

    @patch('setup_environment.resolve_resource_path')
    @patch.object(FileValidator, 'validate')
    def test_validate_all_config_files_with_mixed_resources(
        self,
        mock_validate: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """Test validation with multiple resource types (remote and local)."""
        config = {
            'agents': ['agent.md'],
            'slash-commands': ['cmd1.py', 'cmd2.py'],
            'command-defaults': {
                'system-prompt': 'prompt.md',
            },
            'hooks': {
                'files': ['hook1.py', 'hook2.py'],
            },
        }

        # Mock some as remote, some as local
        mock_resolve.side_effect = [
            ('https://example.com/agent.md', True),  # Remote
            ('/local/path/cmd1.py', False),  # Local
            ('https://example.com/cmd2.py', True),  # Remote
            ('https://example.com/prompt.md', True),  # Remote
            ('/local/path/hook1.py', False),  # Local
            ('https://example.com/hook2.py', True),  # Remote
        ]

        # Mock validation responses
        mock_validate.side_effect = [
            (True, 'HEAD'),  # agent.md (remote)
            (True, 'Local'),  # cmd1.py (local)
            (True, 'Range'),  # cmd2.py (remote)
            (True, 'HEAD'),  # prompt.md (remote)
            (True, 'Local'),  # hook1.py (local)
            (True, 'HEAD'),  # hook2.py (remote)
        ]

        all_valid, results = setup_environment.validate_all_config_files(
            config,
            'https://example.com',
            'token',
        )

        assert all_valid is True
        assert len(results) == 6
        assert results[0] == ('agent', 'agent.md', True, 'HEAD')
        assert results[1] == ('slash_command', 'cmd1.py', True, 'Local')
        assert results[2] == ('slash_command', 'cmd2.py', True, 'Range')
        assert results[3] == ('system_prompt', 'prompt.md', True, 'HEAD')
        assert results[4] == ('hook', 'hook1.py', True, 'Local')
        assert results[5] == ('hook', 'hook2.py', True, 'HEAD')

    @patch('setup_environment.resolve_resource_path')
    @patch.object(FileValidator, 'validate')
    def test_validate_all_config_files_with_failures(
        self,
        mock_validate: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """Test validation with some failures."""
        config = {
            'agents': ['good.md', 'bad.md'],
            'slash-commands': ['cmd.py'],
        }
        mock_resolve.side_effect = [
            ('https://example.com/good.md', True),  # Remote
            ('/local/bad.md', False),  # Local
            ('https://example.com/cmd.py', True),  # Remote
        ]

        mock_validate.side_effect = [
            (True, 'HEAD'),  # good.md
            (False, 'Local'),  # bad.md
            (True, 'Range'),  # cmd.py
        ]

        all_valid, results = setup_environment.validate_all_config_files(config, 'https://example.com')

        assert all_valid is False
        assert len(results) == 3
        assert results[0] == ('agent', 'good.md', True, 'HEAD')
        assert results[1] == ('agent', 'bad.md', False, 'Local')  # Local file not found
        assert results[2] == ('slash_command', 'cmd.py', True, 'Range')

    @patch('setup_environment.resolve_resource_path')
    @patch.object(FileValidator, 'validate')
    def test_validate_all_config_files_with_base_url(
        self,
        mock_validate: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """Test validation with base URL configured."""
        config = {
            'base-url': 'https://cdn.example.com/files',
            'agents': ['agent.md'],
        }
        mock_resolve.return_value = ('https://cdn.example.com/files/agent.md', True)  # Remote
        mock_validate.return_value = (True, 'HEAD')

        all_valid, results = setup_environment.validate_all_config_files(config, 'local')

        assert all_valid is True
        assert len(results) == 1
        # Verify base_url was passed to resolve_resource_path
        mock_resolve.assert_called_once_with('agent.md', 'local', 'https://cdn.example.com/files')

    @patch('setup_environment.info')
    @patch('setup_environment.error')
    @patch('setup_environment.resolve_resource_path')
    @patch.object(FileValidator, 'validate')
    def test_validate_all_config_files_output_messages(
        self,
        mock_validate: MagicMock,
        mock_resolve: MagicMock,
        mock_error: MagicMock,
        mock_info: MagicMock,
    ) -> None:
        """Test validation output messages."""
        config = {
            'agents': ['good.md', 'bad.md'],
        }
        mock_resolve.side_effect = [
            ('https://example.com/good.md', True),  # Remote
            ('https://example.com/bad.md', True),  # Remote
        ]
        mock_validate.side_effect = [
            (True, 'HEAD'),
            (False, 'None'),
        ]

        all_valid, results = setup_environment.validate_all_config_files(config, 'https://example.com')

        assert all_valid is False
        # Check info messages
        mock_info.assert_any_call('Validating 2 files...')
        mock_info.assert_any_call('  [OK] agent: good.md (remote, validated via HEAD)')
        # Check error message
        mock_error.assert_called_once_with('  [FAIL] agent: bad.md (remote, not accessible)')

    @patch('setup_environment.resolve_resource_path')
    @patch.object(FileValidator, 'validate')
    def test_validate_all_config_files_empty_lists(
        self,
        mock_validate: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """Test validation with empty lists in config."""
        del mock_resolve  # Unused but required by decorator
        config: dict[str, object] = {
            'agents': [],
            'slash-commands': None,
            'hooks': {
                'files': None,
            },
        }

        all_valid, results = setup_environment.validate_all_config_files(config, 'local')

        assert all_valid is True
        assert results == []
        mock_validate.assert_not_called()


class TestMainFlowWithValidation:
    """Test the main flow with validation integrated."""

    @patch('setup_environment.sys.exit')
    @patch('setup_environment.validate_all_config_files')
    @patch('setup_environment.load_config_from_source')
    @patch('argparse.ArgumentParser.parse_args')
    def test_main_validation_failure_exits(
        self,
        mock_args: MagicMock,
        mock_load: MagicMock,
        mock_validate: MagicMock,
        mock_exit: MagicMock,
    ) -> None:
        """Test that main exits on validation failure."""
        # Setup mocks
        mock_args.return_value = MagicMock(
            config='test',
            skip_install=True,
            auth=None,
        )
        mock_load.return_value = (
            {
                'name': 'Test',
                'command-name': 'test-cmd',
                'agents': ['bad.md'],
            },
            'https://example.com',
        )
        mock_validate.return_value = (
            False,
            [('agent', 'bad.md', False, 'None')],
        )

        # Run main
        with (
            patch('setup_environment.find_command_robust', return_value='claude'),
            patch('setup_environment.error') as mock_error,
        ):
            setup_environment.main()

        # Verify exit was called with code 1 (may be called multiple times
        # since mocked sys.exit doesn't actually halt execution)
        mock_exit.assert_any_call(1)
        # Verify error messages
        mock_error.assert_any_call('Configuration validation failed!')
        mock_error.assert_any_call('The following files are not accessible:')
        mock_error.assert_any_call('  - agent: bad.md')

    @patch('setup_environment.process_resources')
    @patch('setup_environment.install_dependencies')
    @patch('setup_environment.success')
    @patch('setup_environment.validate_all_config_files')
    @patch('setup_environment.load_config_from_source')
    @patch('argparse.ArgumentParser.parse_args')
    def test_main_validation_success_continues(
        self,
        mock_args: MagicMock,
        mock_load: MagicMock,
        mock_validate: MagicMock,
        mock_success: MagicMock,
        mock_install: MagicMock,
        mock_download: MagicMock,
    ) -> None:
        """Test that main continues when validation succeeds."""
        del mock_download  # Unused but required by decorator
        # Setup mocks
        mock_args.return_value = MagicMock(
            config='test',
            skip_install=True,
            auth=None,
        )
        mock_load.return_value = (
            {
                'name': 'Test',
                'command-name': 'test-cmd',
                'agents': ['good.md'],
                'dependencies': [],
            },
            'https://example.com',
        )
        mock_validate.return_value = (
            True,
            [('agent', 'good.md', True, 'HEAD')],
        )

        # Run main (will fail later but that's ok for this test)
        with (
            patch('setup_environment.find_command_robust', return_value='claude'),
            patch('setup_environment.Path.mkdir'),
            contextlib.suppress(Exception),  # Expected to fail at later steps
        ):
            setup_environment.main()

        # Verify validation success message
        mock_success.assert_any_call('All configuration files validated successfully!')
        # Verify we didn't exit early
        mock_install.assert_called()


class TestLocalPathValidation:
    """Test local path validation with real files."""

    @patch('setup_environment.info')
    @patch('setup_environment.error')
    def test_validate_local_files_with_real_paths(
        self,
        mock_error: MagicMock,
        mock_info: MagicMock,
    ) -> None:
        """Test validation with actual temporary files."""
        del mock_error, mock_info  # Unused but needed to suppress output
        with tempfile.TemporaryDirectory() as tmpdir_str:
            tmpdir_path = Path(tmpdir_str)

            # Create some test files
            (tmpdir_path / 'exists.md').write_text('content')
            (tmpdir_path / 'subdir').mkdir()
            (tmpdir_path / 'subdir' / 'nested.md').write_text('nested')

            # Create config with various local paths
            config = {
                'agents': [
                    str(tmpdir_path / 'exists.md'),  # Absolute path that exists
                    str(tmpdir_path / 'missing.md'),  # Absolute path that doesn't exist
                ],
                'slash-commands': [
                    './subdir/nested.md',  # Relative path (will be resolved)
                ],
            }

            # Create a config file in tmpdir for relative path resolution
            config_file = tmpdir_path / 'config.yaml'
            config_file.write_text('dummy')

            # Run validation
            all_valid, results = setup_environment.validate_all_config_files(
                config,
                str(config_file),
            )

            # Verify results
            assert all_valid is False  # One file missing
            assert len(results) == 3

            # Check first agent (exists)
            assert results[0][0] == 'agent'
            assert results[0][1] == str(tmpdir_path / 'exists.md')
            assert results[0][2] is True
            assert results[0][3] == 'Local'

            # Check second agent (missing)
            assert results[1][0] == 'agent'
            assert results[1][1] == str(tmpdir_path / 'missing.md')
            assert results[1][2] is False
            assert results[1][3] == 'Local'

            # Check slash command (nested, exists)
            assert results[2][0] == 'slash_command'
            assert results[2][1] == './subdir/nested.md'
            assert results[2][2] is True
            assert results[2][3] == 'Local'

    def test_resolve_resource_path_local_variations(self) -> None:
        """Test resolve_resource_path with various local path types."""
        with tempfile.TemporaryDirectory() as tmpdir_str:
            tmpdir_path = Path(tmpdir_str)
            config_file = tmpdir_path / 'config.yaml'
            config_file.write_text('dummy')

            # Test absolute path
            abs_path = str(tmpdir_path / 'file.md')
            resolved, is_remote = setup_environment.resolve_resource_path(
                abs_path,
                str(config_file),
            )
            assert resolved == str(Path(abs_path).resolve())
            assert is_remote is False

            # Test relative path with ./
            resolved, is_remote = setup_environment.resolve_resource_path(
                './file.md',
                str(config_file),
            )
            assert resolved == str((tmpdir_path / 'file.md').resolve())
            assert is_remote is False

            # Test parent relative path
            resolved, is_remote = setup_environment.resolve_resource_path(
                '../file.md',
                str(config_file),
            )
            assert resolved == str((tmpdir_path.parent / 'file.md').resolve())
            assert is_remote is False

            # Test simple relative path
            resolved, is_remote = setup_environment.resolve_resource_path(
                'file.md',
                str(config_file),
            )
            assert resolved == str((tmpdir_path / 'file.md').resolve())
            assert is_remote is False

            # Test home directory expansion
            with patch.dict(os.environ, {'HOME': str(tmpdir_path), 'USERPROFILE': str(tmpdir_path)}):
                resolved, is_remote = setup_environment.resolve_resource_path(
                    '~/file.md',
                    str(config_file),
                )
                assert resolved == str((tmpdir_path / 'file.md').resolve())
                assert is_remote is False

            # Test environment variable expansion (platform-specific)
            import platform

            if platform.system() == 'Windows':
                # Test Windows environment variable expansion
                with patch.dict(os.environ, {'USERPROFILE': str(tmpdir_path)}):
                    resolved, is_remote = setup_environment.resolve_resource_path(
                        '%USERPROFILE%\\file.md',
                        str(config_file),
                    )
                    assert resolved == str((tmpdir_path / 'file.md').resolve())
                    assert is_remote is False
            else:
                # Test Unix environment variable expansion
                with patch.dict(os.environ, {'HOME': str(tmpdir_path)}):
                    resolved, is_remote = setup_environment.resolve_resource_path(
                        '$HOME/file.md',
                        str(config_file),
                    )
                    assert resolved == str((tmpdir_path / 'file.md').resolve())
                    assert is_remote is False
