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
            'https://example.com/file.md',
            404,
            'Not Found',
            {},
            None,
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
            'https://example.com/file.md',
            416,
            'Range Not Satisfiable',
            {},
            None,
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
            'https://example.com/file.md',
            auth_headers,
        )

        assert is_valid is True
        assert method == 'Range'
        mock_head.assert_called_once_with('https://example.com/file.md', auth_headers)
        mock_range.assert_called_once_with('https://example.com/file.md', auth_headers)

    @patch('setup_environment.info')
    @patch('setup_environment.convert_gitlab_url_to_api')
    @patch('setup_environment.detect_repo_type')
    @patch('setup_environment.check_file_with_head')
    def test_validate_file_availability_gitlab_url_conversion(self, mock_head, mock_detect, mock_convert, mock_info):
        """Test that GitLab URLs are converted to API format for validation."""
        # Setup
        gitlab_web_url = 'https://gitlab.com/namespace/project/-/raw/main/file.md'
        gitlab_api_url = 'https://gitlab.com/api/v4/projects/namespace%2Fproject/repository/files/file.md/raw?ref=main'

        mock_detect.return_value = 'gitlab'
        mock_convert.return_value = gitlab_api_url
        mock_head.return_value = True

        # Execute
        is_valid, method = setup_environment.validate_file_availability(gitlab_web_url)

        # Verify
        assert is_valid is True
        assert method == 'HEAD'
        mock_detect.assert_called_once_with(gitlab_web_url)
        mock_convert.assert_called_once_with(gitlab_web_url)
        # The HEAD check should be called with the converted API URL
        mock_head.assert_called_once_with(gitlab_api_url, None)
        mock_info.assert_called_once_with(f'Using API URL for validation: {gitlab_api_url}')


class TestValidateAllConfigFiles:
    """Test full configuration validation."""

    @patch('setup_environment.get_auth_headers')
    @patch('setup_environment.resolve_resource_path')
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
    @patch('setup_environment.resolve_resource_path')
    @patch('setup_environment.validate_file_availability')
    def test_validate_all_config_files_with_agents(self, mock_validate, mock_resolve, mock_auth):
        """Test validation with agents."""
        config = {
            'agents': ['agent1.md', 'agent2.md'],
        }
        mock_auth.return_value = None
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

    @patch('setup_environment.get_auth_headers')
    @patch('setup_environment.resolve_resource_path')
    @patch('setup_environment.validate_file_availability')
    @patch('setup_environment.Path')
    def test_validate_all_config_files_with_mixed_resources(self, mock_path_cls, mock_validate, mock_resolve, mock_auth):
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
        mock_auth.return_value = {'Authorization': 'Bearer token'}

        # Mock some as remote, some as local
        mock_resolve.side_effect = [
            ('https://example.com/agent.md', True),  # Remote
            ('/local/path/cmd1.py', False),  # Local
            ('https://example.com/cmd2.py', True),  # Remote
            ('https://example.com/prompt.md', True),  # Remote
            ('/local/path/hook1.py', False),  # Local
            ('https://example.com/hook2.py', True),  # Remote
        ]

        # Mock local file checks
        mock_path = MagicMock()
        mock_path.exists.side_effect = [True, True]  # All local files exist
        mock_path.is_file.return_value = True
        mock_path_cls.return_value = mock_path

        # Mock remote validation
        mock_validate.side_effect = [
            (True, 'HEAD'),  # agent.md
            (True, 'Range'),  # cmd2.py
            (True, 'HEAD'),  # prompt.md
            (True, 'HEAD'),  # hook2.py
        ]

        all_valid, results = setup_environment.validate_all_config_files(
            config,
            'https://example.com',
            'token',
        )

        assert all_valid is True
        assert len(results) == 6
        # Check result types and validation methods
        assert results[0] == ('agent', 'agent.md', True, 'HEAD')  # Remote
        assert results[1] == ('slash_command', 'cmd1.py', True, 'Local')  # Local
        assert results[2] == ('slash_command', 'cmd2.py', True, 'Range')  # Remote
        assert results[3] == ('system_prompt', 'prompt.md', True, 'HEAD')  # Remote
        assert results[4] == ('hook', 'hook1.py', True, 'Local')  # Local
        assert results[5] == ('hook', 'hook2.py', True, 'HEAD')  # Remote

    @patch('setup_environment.get_auth_headers')
    @patch('setup_environment.resolve_resource_path')
    @patch('setup_environment.validate_file_availability')
    @patch('setup_environment.Path')
    def test_validate_all_config_files_with_failures(self, mock_path_cls, mock_validate, mock_resolve, mock_auth):
        """Test validation with some failures."""
        config = {
            'agents': ['good.md', 'bad.md'],
            'slash-commands': ['cmd.py'],
        }
        mock_auth.return_value = None
        mock_resolve.side_effect = [
            ('https://example.com/good.md', True),  # Remote
            ('/local/bad.md', False),  # Local
            ('https://example.com/cmd.py', True),  # Remote
        ]

        # Mock local file check for bad.md (doesn't exist)
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_path.is_file.return_value = False
        mock_path_cls.return_value = mock_path

        mock_validate.side_effect = [
            (True, 'HEAD'),  # good.md
            (True, 'Range'),  # cmd.py
        ]

        all_valid, results = setup_environment.validate_all_config_files(config, 'https://example.com')

        assert all_valid is False
        assert len(results) == 3
        assert results[0] == ('agent', 'good.md', True, 'HEAD')
        assert results[1] == ('agent', 'bad.md', False, 'Local')  # Local file not found
        assert results[2] == ('slash_command', 'cmd.py', True, 'Range')

    @patch('setup_environment.get_auth_headers')
    @patch('setup_environment.resolve_resource_path')
    @patch('setup_environment.Path')
    def test_validate_all_config_files_local_paths_comprehensive(self, mock_path_cls, mock_resolve, mock_auth):
        """Test validation with all types of local paths."""
        config = {
            'agents': [
                'C:\\absolute\\windows\\path.md',  # Windows absolute
                '/absolute/unix/path.md',  # Unix absolute
                './relative/path.md',  # Relative with ./
                '../parent/path.md',  # Parent relative
                'simple.md',  # Simple relative
                '~/home/path.md',  # Home directory
                '%USERPROFILE%\\env\\path.md',  # Windows env var
                '$HOME/env/path.md',  # Unix env var
            ],
        }
        mock_auth.return_value = None

        # All resolve to local paths
        mock_resolve.side_effect = [
            ('C:\\absolute\\windows\\path.md', False),
            ('/absolute/unix/path.md', False),
            ('C:\\current\\relative\\path.md', False),
            ('C:\\parent\\path.md', False),
            ('C:\\current\\simple.md', False),
            ('C:\\Users\\test\\home\\path.md', False),
            ('C:\\Users\\test\\env\\path.md', False),
            ('C:\\Users\\test\\env\\path.md', False),
        ]

        # Mock Path objects for each resolved path
        mock_paths = []
        for i in range(8):
            mock_path = MagicMock()
            # Make first 5 exist, last 3 not exist
            mock_path.exists.return_value = i < 5
            mock_path.is_file.return_value = i < 5
            mock_paths.append(mock_path)

        mock_path_cls.side_effect = mock_paths

        all_valid, results = setup_environment.validate_all_config_files(config, 'local.yaml')

        assert all_valid is False  # Some files don't exist
        assert len(results) == 8

        # Check that first 5 are valid
        for i in range(5):
            assert results[i][2] is True  # is_valid
            assert results[i][3] == 'Local'  # method

        # Check that last 3 are invalid
        for i in range(5, 8):
            assert results[i][2] is False  # is_valid
            assert results[i][3] == 'Local'  # method

    @patch('setup_environment.get_auth_headers')
    @patch('setup_environment.resolve_resource_path')
    @patch('setup_environment.validate_file_availability')
    def test_validate_all_config_files_with_base_url(self, mock_validate, mock_resolve, mock_auth):
        """Test validation with base URL configured."""
        config = {
            'base-url': 'https://cdn.example.com/files',
            'agents': ['agent.md'],
        }
        mock_auth.return_value = None
        mock_resolve.return_value = ('https://cdn.example.com/files/agent.md', True)  # Remote
        mock_validate.return_value = (True, 'HEAD')

        all_valid, results = setup_environment.validate_all_config_files(config, 'local')

        assert all_valid is True
        assert len(results) == 1
        # Verify base_url was passed to resolve_resource_path
        mock_resolve.assert_called_once_with('agent.md', 'local', 'https://cdn.example.com/files')

    @patch('setup_environment.info')
    @patch('setup_environment.error')
    @patch('setup_environment.get_auth_headers')
    @patch('setup_environment.resolve_resource_path')
    @patch('setup_environment.validate_file_availability')
    def test_validate_all_config_files_output_messages(
        self,
        mock_validate,
        mock_resolve,
        mock_auth,
        mock_error,
        mock_info,
    ):
        """Test validation output messages."""
        config = {
            'agents': ['good.md', 'bad.md'],
        }
        mock_auth.return_value = None
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
        mock_info.assert_any_call('  ✓ agent: good.md (remote, validated via HEAD)')
        # Check error message
        mock_error.assert_called_once_with('  ✗ agent: bad.md (remote, not accessible)')

    @patch('setup_environment.get_auth_headers')
    @patch('setup_environment.resolve_resource_path')
    @patch('setup_environment.validate_file_availability')
    def test_validate_all_config_files_empty_lists(self, mock_validate, mock_resolve, mock_auth):
        """Test validation with empty lists in config."""
        del mock_resolve  # Unused but required by decorator
        config = {
            'agents': [],
            'slash-commands': None,
            'hooks': {
                'files': None,
            },
        }
        mock_auth.return_value = None

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
            patch('setup_environment.find_command_robust', return_value='claude'),
            patch('setup_environment.error') as mock_error,
        ):
            setup_environment.main()

        # Verify exit was called
        mock_exit.assert_called_once_with(1)
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
        mock_args,
        mock_load,
        mock_validate,
        mock_success,
        mock_install,
        mock_download,
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
    def test_validate_local_files_with_real_paths(self, mock_error, mock_info):
        """Test validation with actual temporary files."""
        del mock_error, mock_info  # Unused but needed to suppress output
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create some test files
            (tmpdir / 'exists.md').write_text('content')
            (tmpdir / 'subdir').mkdir()
            (tmpdir / 'subdir' / 'nested.md').write_text('nested')

            # Create config with various local paths
            config = {
                'agents': [
                    str(tmpdir / 'exists.md'),  # Absolute path that exists
                    str(tmpdir / 'missing.md'),  # Absolute path that doesn't exist
                ],
                'slash-commands': [
                    './subdir/nested.md',  # Relative path (will be resolved)
                ],
            }

            # Create a config file in tmpdir for relative path resolution
            config_file = tmpdir / 'config.yaml'
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
            assert results[0][1] == str(tmpdir / 'exists.md')
            assert results[0][2] is True
            assert results[0][3] == 'Local'

            # Check second agent (missing)
            assert results[1][0] == 'agent'
            assert results[1][1] == str(tmpdir / 'missing.md')
            assert results[1][2] is False
            assert results[1][3] == 'Local'

            # Check slash command (nested, exists)
            assert results[2][0] == 'slash_command'
            assert results[2][1] == './subdir/nested.md'
            assert results[2][2] is True
            assert results[2][3] == 'Local'

    def test_resolve_resource_path_local_variations(self):
        """Test resolve_resource_path with various local path types."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            config_file = tmpdir / 'config.yaml'
            config_file.write_text('dummy')

            # Test absolute path
            abs_path = str(tmpdir / 'file.md')
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
            assert resolved == str((tmpdir / 'file.md').resolve())
            assert is_remote is False

            # Test parent relative path
            resolved, is_remote = setup_environment.resolve_resource_path(
                '../file.md',
                str(config_file),
            )
            assert resolved == str((tmpdir.parent / 'file.md').resolve())
            assert is_remote is False

            # Test simple relative path
            resolved, is_remote = setup_environment.resolve_resource_path(
                'file.md',
                str(config_file),
            )
            assert resolved == str((tmpdir / 'file.md').resolve())
            assert is_remote is False

            # Test home directory expansion
            with patch.dict(os.environ, {'HOME': str(tmpdir), 'USERPROFILE': str(tmpdir)}):
                resolved, is_remote = setup_environment.resolve_resource_path(
                    '~/file.md',
                    str(config_file),
                )
                assert resolved == str((tmpdir / 'file.md').resolve())
                assert is_remote is False

            # Test environment variable expansion (platform-specific)
            import platform

            if platform.system() == 'Windows':
                # Test Windows environment variable expansion
                with patch.dict(os.environ, {'USERPROFILE': str(tmpdir)}):
                    resolved, is_remote = setup_environment.resolve_resource_path(
                        '%USERPROFILE%\\file.md',
                        str(config_file),
                    )
                    assert resolved == str((tmpdir / 'file.md').resolve())
                    assert is_remote is False
            else:
                # Test Unix environment variable expansion
                with patch.dict(os.environ, {'HOME': str(tmpdir)}):
                    resolved, is_remote = setup_environment.resolve_resource_path(
                        '$HOME/file.md',
                        str(config_file),
                    )
                    assert resolved == str((tmpdir / 'file.md').resolve())
                    assert is_remote is False
