"""Tests for pre-download validation functionality in setup_environment.py."""

import contextlib
import sys
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

import setup_environment


class TestCheckFileWithHead:
    """Test HEAD request validation."""

    @patch('setup_environment.urlopen')
    def test_check_file_with_head_success(self, mock_urlopen):
        """Test successful HEAD request."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value = mock_response

        result = setup_environment.check_file_with_head('https://example.com/file.md')

        assert result is True
        mock_urlopen.assert_called_once()
        request = mock_urlopen.call_args[0][0]
        assert request.get_method() == 'HEAD'
        assert request.full_url == 'https://example.com/file.md'

    @patch('setup_environment.urlopen')
    def test_check_file_with_head_not_found(self, mock_urlopen):
        """Test HEAD request with 404."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            'https://example.com/file.md', 404, 'Not Found', {}, None,
        )

        result = setup_environment.check_file_with_head('https://example.com/file.md')

        assert result is False

    @patch('setup_environment.urlopen')
    def test_check_file_with_head_with_auth(self, mock_urlopen):
        """Test HEAD request with authentication headers."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value = mock_response

        auth_headers = {'Authorization': 'Bearer token123'}
        result = setup_environment.check_file_with_head('https://example.com/file.md', auth_headers)

        assert result is True
        request = mock_urlopen.call_args[0][0]
        assert request.headers.get('Authorization') == 'Bearer token123'

    @patch('setup_environment.urlopen')
    def test_check_file_with_head_ssl_error_retry(self, mock_urlopen):
        """Test HEAD request with SSL error and successful retry."""
        # First call fails with SSL error
        mock_urlopen.side_effect = [
            urllib.error.URLError('SSL: CERTIFICATE_VERIFY_FAILED'),
            MagicMock(status=200),  # Second call succeeds
        ]

        result = setup_environment.check_file_with_head('https://example.com/file.md')

        assert result is True
        assert mock_urlopen.call_count == 2
        # Second call should use unverified context
        second_call_context = mock_urlopen.call_args_list[1][1].get('context')
        assert second_call_context is not None

    @patch('setup_environment.urlopen')
    def test_check_file_with_head_non_ssl_error(self, mock_urlopen):
        """Test HEAD request with non-SSL URLError."""
        mock_urlopen.side_effect = urllib.error.URLError('Connection refused')

        result = setup_environment.check_file_with_head('https://example.com/file.md')

        assert result is False
        assert mock_urlopen.call_count == 1


class TestCheckFileWithRange:
    """Test Range request validation."""

    @patch('setup_environment.urlopen')
    def test_check_file_with_range_success_200(self, mock_urlopen):
        """Test successful Range request with 200 response."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value = mock_response

        result = setup_environment.check_file_with_range('https://example.com/file.md')

        assert result is True
        request = mock_urlopen.call_args[0][0]
        assert request.headers.get('Range') == 'bytes=0-0'

    @patch('setup_environment.urlopen')
    def test_check_file_with_range_success_206(self, mock_urlopen):
        """Test successful Range request with 206 partial content response."""
        mock_response = MagicMock()
        mock_response.status = 206
        mock_urlopen.return_value = mock_response

        result = setup_environment.check_file_with_range('https://example.com/file.md')

        assert result is True

    @patch('setup_environment.urlopen')
    def test_check_file_with_range_with_auth(self, mock_urlopen):
        """Test Range request with authentication headers."""
        mock_response = MagicMock()
        mock_response.status = 206
        mock_urlopen.return_value = mock_response

        auth_headers = {'Authorization': 'Token abc123', 'X-Custom': 'value'}
        result = setup_environment.check_file_with_range('https://example.com/file.md', auth_headers)

        assert result is True
        request = mock_urlopen.call_args[0][0]
        assert request.headers.get('Authorization') == 'Token abc123'
        assert request.headers.get('X-custom') == 'value'  # Note: headers are case-insensitive
        assert request.headers.get('Range') == 'bytes=0-0'

    @patch('setup_environment.urlopen')
    def test_check_file_with_range_ssl_error_retry(self, mock_urlopen):
        """Test Range request with SSL error and successful retry."""
        mock_urlopen.side_effect = [
            urllib.error.URLError('certificate verify failed'),
            MagicMock(status=206),
        ]

        result = setup_environment.check_file_with_range('https://example.com/file.md')

        assert result is True
        assert mock_urlopen.call_count == 2

    @patch('setup_environment.urlopen')
    def test_check_file_with_range_http_error(self, mock_urlopen):
        """Test Range request with HTTP error."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            'https://example.com/file.md', 416, 'Range Not Satisfiable', {}, None,
        )

        result = setup_environment.check_file_with_range('https://example.com/file.md')

        assert result is False

    @patch('setup_environment.urlopen')
    def test_check_file_with_range_generic_exception(self, mock_urlopen):
        """Test Range request with generic exception."""
        mock_urlopen.side_effect = Exception('Network error')

        result = setup_environment.check_file_with_range('https://example.com/file.md')

        assert result is False


class TestValidateFileAvailability:
    """Test the hybrid validation approach."""

    @patch('setup_environment.check_file_with_head')
    @patch('setup_environment.check_file_with_range')
    def test_validate_file_availability_head_success(self, mock_range, mock_head):
        """Test validation succeeds with HEAD request."""
        mock_head.return_value = True
        mock_range.return_value = False  # Should not be called

        is_valid, method = setup_environment.validate_file_availability('https://example.com/file.md')

        assert is_valid is True
        assert method == 'HEAD'
        mock_head.assert_called_once_with('https://example.com/file.md', None)
        mock_range.assert_not_called()

    @patch('setup_environment.check_file_with_head')
    @patch('setup_environment.check_file_with_range')
    def test_validate_file_availability_fallback_to_range(self, mock_range, mock_head):
        """Test validation falls back to Range when HEAD fails."""
        mock_head.return_value = False
        mock_range.return_value = True

        is_valid, method = setup_environment.validate_file_availability('https://example.com/file.md')

        assert is_valid is True
        assert method == 'Range'
        mock_head.assert_called_once()
        mock_range.assert_called_once_with('https://example.com/file.md', None)

    @patch('setup_environment.check_file_with_head')
    @patch('setup_environment.check_file_with_range')
    def test_validate_file_availability_both_fail(self, mock_range, mock_head):
        """Test validation fails when both methods fail."""
        mock_head.return_value = False
        mock_range.return_value = False

        is_valid, method = setup_environment.validate_file_availability('https://example.com/file.md')

        assert is_valid is False
        assert method == 'None'
        mock_head.assert_called_once()
        mock_range.assert_called_once()

    @patch('setup_environment.check_file_with_head')
    @patch('setup_environment.check_file_with_range')
    def test_validate_file_availability_with_auth(self, mock_range, mock_head):
        """Test validation passes authentication headers."""
        mock_head.return_value = False
        mock_range.return_value = True
        auth_headers = {'Authorization': 'Bearer token'}

        is_valid, method = setup_environment.validate_file_availability(
            'https://example.com/file.md', auth_headers,
        )

        assert is_valid is True
        assert method == 'Range'
        mock_head.assert_called_once_with('https://example.com/file.md', auth_headers)
        mock_range.assert_called_once_with('https://example.com/file.md', auth_headers)


class TestValidateAllConfigFiles:
    """Test full configuration validation."""

    @patch('setup_environment.get_auth_headers')
    @patch('setup_environment.resolve_resource_url')
    @patch('setup_environment.validate_file_availability')
    def test_validate_all_config_files_empty_config(self, mock_validate, mock_resolve, mock_auth):
        """Test validation with empty configuration."""
        del mock_resolve  # Unused but required by decorator
        config = {}
        mock_auth.return_value = None

        all_valid, results = setup_environment.validate_all_config_files(config, 'local')

        assert all_valid is True
        assert results == []
        mock_validate.assert_not_called()

    @patch('setup_environment.get_auth_headers')
    @patch('setup_environment.resolve_resource_url')
    @patch('setup_environment.validate_file_availability')
    def test_validate_all_config_files_with_agents(self, mock_validate, mock_resolve, mock_auth):
        """Test validation with agents."""
        config = {
            'agents': ['agent1.md', 'agent2.md'],
        }
        mock_auth.return_value = None
        mock_resolve.side_effect = [
            'https://example.com/agent1.md',
            'https://example.com/agent2.md',
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

    @patch('setup_environment.get_auth_headers')
    @patch('setup_environment.resolve_resource_url')
    @patch('setup_environment.validate_file_availability')
    def test_validate_all_config_files_with_mixed_resources(self, mock_validate, mock_resolve, mock_auth):
        """Test validation with multiple resource types."""
        config = {
            'agents': ['agent.md'],
            'slash-commands': ['cmd1.py', 'cmd2.py'],
            'output-styles': ['style.md'],
            'hooks': {
                'files': ['hook1.py', 'hook2.py'],
            },
        }
        mock_auth.return_value = {'Authorization': 'Bearer token'}
        mock_resolve.side_effect = [
            'https://example.com/agent.md',
            'https://example.com/cmd1.py',
            'https://example.com/cmd2.py',
            'https://example.com/style.md',
            'https://example.com/hook1.py',
            'https://example.com/hook2.py',
        ]
        mock_validate.return_value = (True, 'HEAD')

        all_valid, results = setup_environment.validate_all_config_files(
            config, 'https://example.com', 'token',
        )

        assert all_valid is True
        assert len(results) == 6
        assert results[0][0] == 'agent'
        assert results[1][0] == 'slash_command'
        assert results[2][0] == 'slash_command'
        assert results[3][0] == 'output_style'
        assert results[4][0] == 'hook'
        assert results[5][0] == 'hook'
        # Verify auth headers were passed
        for call in mock_validate.call_args_list:
            assert call[0][1] == {'Authorization': 'Bearer token'}

    @patch('setup_environment.get_auth_headers')
    @patch('setup_environment.resolve_resource_url')
    @patch('setup_environment.validate_file_availability')
    def test_validate_all_config_files_with_failures(self, mock_validate, mock_resolve, mock_auth):
        """Test validation with some failures."""
        config = {
            'agents': ['good.md', 'bad.md'],
            'slash-commands': ['cmd.py'],
        }
        mock_auth.return_value = None
        mock_resolve.side_effect = [
            'https://example.com/good.md',
            'https://example.com/bad.md',
            'https://example.com/cmd.py',
        ]
        mock_validate.side_effect = [
            (True, 'HEAD'),
            (False, 'None'),  # bad.md fails
            (True, 'Range'),
        ]

        all_valid, results = setup_environment.validate_all_config_files(config, 'https://example.com')

        assert all_valid is False
        assert len(results) == 3
        assert results[0] == ('agent', 'good.md', True, 'HEAD')
        assert results[1] == ('agent', 'bad.md', False, 'None')
        assert results[2] == ('slash_command', 'cmd.py', True, 'Range')

    @patch('setup_environment.get_auth_headers')
    @patch('setup_environment.resolve_resource_url')
    @patch('setup_environment.validate_file_availability')
    def test_validate_all_config_files_with_base_url(self, mock_validate, mock_resolve, mock_auth):
        """Test validation with base URL configured."""
        config = {
            'base-url': 'https://cdn.example.com/files',
            'agents': ['agent.md'],
        }
        mock_auth.return_value = None
        mock_resolve.return_value = 'https://cdn.example.com/files/agent.md'
        mock_validate.return_value = (True, 'HEAD')

        all_valid, results = setup_environment.validate_all_config_files(config, 'local')

        assert all_valid is True
        assert len(results) == 1
        # Verify base_url was passed to resolve_resource_url
        mock_resolve.assert_called_once_with('agent.md', 'local', 'https://cdn.example.com/files')

    @patch('setup_environment.info')
    @patch('setup_environment.error')
    @patch('setup_environment.get_auth_headers')
    @patch('setup_environment.resolve_resource_url')
    @patch('setup_environment.validate_file_availability')
    def test_validate_all_config_files_output_messages(
        self, mock_validate, mock_resolve, mock_auth, mock_error, mock_info,
    ):
        """Test validation output messages."""
        config = {
            'agents': ['good.md', 'bad.md'],
        }
        mock_auth.return_value = None
        mock_resolve.side_effect = [
            'https://example.com/good.md',
            'https://example.com/bad.md',
        ]
        mock_validate.side_effect = [
            (True, 'HEAD'),
            (False, 'None'),
        ]

        all_valid, results = setup_environment.validate_all_config_files(config, 'https://example.com')

        assert all_valid is False
        # Check info messages
        mock_info.assert_any_call('Validating 2 files before download...')
        mock_info.assert_any_call('  ✓ agent: good.md (validated via HEAD)')
        # Check error message
        mock_error.assert_called_once_with('  ✗ agent: bad.md (not accessible)')

    @patch('setup_environment.get_auth_headers')
    @patch('setup_environment.resolve_resource_url')
    @patch('setup_environment.validate_file_availability')
    def test_validate_all_config_files_empty_lists(self, mock_validate, mock_resolve, mock_auth):
        """Test validation with empty lists in config."""
        del mock_resolve  # Unused but required by decorator
        config = {
            'agents': [],
            'slash-commands': None,
            'output-styles': [],
            'hooks': {
                'files': None,
            },
        }
        mock_auth.return_value = None

        all_valid, results = setup_environment.validate_all_config_files(config, 'local')

        assert all_valid is True
        assert results == []
        mock_validate.assert_not_called()

    @patch('setup_environment.get_auth_headers')
    @patch('setup_environment.resolve_resource_url')
    @patch('setup_environment.validate_file_availability')
    def test_validate_all_config_files_system_prompts(self, mock_validate, mock_resolve, mock_auth):
        """Test validation with system prompts (file-based)."""
        config = {
            'system-prompts': ['prompt1.md', 'prompt2.md'],
        }
        mock_auth.return_value = None
        mock_resolve.side_effect = [
            'https://example.com/prompt1.md',
            'https://example.com/prompt2.md',
        ]
        mock_validate.return_value = (True, 'HEAD')

        all_valid, results = setup_environment.validate_all_config_files(config, 'https://example.com')

        assert all_valid is True
        assert len(results) == 2
        assert results[0] == ('system_prompt', 'prompt1.md', True, 'HEAD')
        assert results[1] == ('system_prompt', 'prompt2.md', True, 'HEAD')


class TestMainFlowWithValidation:
    """Test the main flow with validation integrated."""

    @patch('setup_environment.sys.exit')
    @patch('setup_environment.validate_all_config_files')
    @patch('setup_environment.load_config_from_source')
    @patch('argparse.ArgumentParser.parse_args')
    def test_main_validation_failure_exits(self, mock_args, mock_load, mock_validate, mock_exit):
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
            patch('setup_environment.find_command', return_value='claude'),
            patch('setup_environment.error') as mock_error,
        ):
            setup_environment.main()

        # Verify exit was called
        mock_exit.assert_called_once_with(1)
        # Verify error messages
        mock_error.assert_any_call('Configuration validation failed!')
        mock_error.assert_any_call('The following files are not accessible:')
        mock_error.assert_any_call('  - agent: bad.md')

    @patch('setup_environment.download_resources')
    @patch('setup_environment.install_dependencies')
    @patch('setup_environment.success')
    @patch('setup_environment.validate_all_config_files')
    @patch('setup_environment.load_config_from_source')
    @patch('argparse.ArgumentParser.parse_args')
    def test_main_validation_success_continues(
        self, mock_args, mock_load, mock_validate, mock_success, mock_install, mock_download,
    ):
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
            patch('setup_environment.find_command', return_value='claude'),
            patch('setup_environment.Path.mkdir'),
            contextlib.suppress(Exception),  # Expected to fail at later steps
        ):
            setup_environment.main()

        # Verify validation success message
        mock_success.assert_any_call('All configuration files validated successfully!')
        # Verify we didn't exit early
        mock_install.assert_called()
