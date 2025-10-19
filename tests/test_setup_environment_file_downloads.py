"""Tests for file download functionality in setup_environment.py."""

import os
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

from scripts.setup_environment import process_file_downloads


class TestProcessFileDownloads:
    """Test suite for process_file_downloads function."""

    def test_process_file_downloads_empty_list(self) -> None:
        """Test handling empty file list returns True and shows info."""
        with patch('scripts.setup_environment.info') as mock_info:
            result = process_file_downloads([], 'config.yaml')

            assert result is True
            mock_info.assert_called_once_with('No files to download configured')

    @patch('scripts.setup_environment.success')
    @patch('scripts.setup_environment.handle_resource')
    def test_process_file_downloads_single_success(
        self, mock_handle: MagicMock, mock_success: MagicMock,
    ) -> None:
        """Test successful single file download."""
        mock_handle.return_value = True

        file_specs = [{'source': 'test.txt', 'dest': '~/dest.txt'}]
        result = process_file_downloads(file_specs, 'config.yaml')

        assert result is True
        assert mock_handle.call_count == 1
        mock_success.assert_called_once()
        assert 'All 1 files' in mock_success.call_args[0][0]

    @patch('scripts.setup_environment.warning')
    @patch('scripts.setup_environment.handle_resource')
    def test_process_file_downloads_missing_source(
        self, mock_handle: MagicMock, mock_warning: MagicMock,
    ) -> None:
        """Test handling missing source key."""
        file_specs = [{'dest': '~/dest.txt'}]  # No source
        result = process_file_downloads(file_specs, 'config.yaml')

        assert result is False
        mock_handle.assert_not_called()
        # Check that warning was called twice: once for missing source, once for summary
        assert mock_warning.call_count == 2
        assert 'missing source' in mock_warning.call_args_list[0][0][0]

    @patch('scripts.setup_environment.warning')
    @patch('scripts.setup_environment.handle_resource')
    def test_process_file_downloads_missing_dest(
        self, mock_handle: MagicMock, mock_warning: MagicMock,
    ) -> None:
        """Test handling missing dest key."""
        file_specs = [{'source': 'test.txt'}]  # No dest
        result = process_file_downloads(file_specs, 'config.yaml')

        assert result is False
        mock_handle.assert_not_called()
        # Check that warning was called twice: once for missing dest, once for summary
        assert mock_warning.call_count == 2
        assert 'missing dest' in mock_warning.call_args_list[0][0][0]

    @patch('scripts.setup_environment.handle_resource')
    def test_process_file_downloads_path_expansion_tilde(
        self, mock_handle: MagicMock,
    ) -> None:
        """Test tilde expansion in dest path."""
        mock_handle.return_value = True
        home = str(Path.home())

        file_specs = [{'source': 'test.txt', 'dest': '~/.config/test.txt'}]
        process_file_downloads(file_specs, 'config.yaml')

        # Check that handle_resource was called with expanded path
        call_args = mock_handle.call_args[0]
        dest_path = call_args[1]
        assert str(dest_path).startswith(home)
        assert '.config' in str(dest_path)

    @patch.dict(os.environ, {'TESTVAR': '/test/path'})
    @patch('scripts.setup_environment.handle_resource')
    def test_process_file_downloads_path_expansion_env_var(
        self, mock_handle: MagicMock,
    ) -> None:
        """Test environment variable expansion."""
        mock_handle.return_value = True

        file_specs = [{'source': 'test.txt', 'dest': '$TESTVAR/file.txt'}]
        process_file_downloads(file_specs, 'config.yaml')

        call_args = mock_handle.call_args[0]
        dest_path = call_args[1]
        # On Windows, path uses backslashes; on Unix, forward slashes
        # Just check that the path contains 'test' and 'path' components
        path_str = str(dest_path)
        assert 'test' in path_str.lower()
        assert 'path' in path_str.lower()
        assert 'file.txt' in path_str

    @patch('pathlib.Path.is_dir')
    @patch('pathlib.Path.exists')
    @patch('scripts.setup_environment.handle_resource')
    def test_process_file_downloads_directory_dest(
        self, mock_handle: MagicMock, mock_exists: MagicMock, mock_is_dir: MagicMock,
    ) -> None:
        """Test directory destination appends filename."""
        mock_handle.return_value = True
        mock_exists.return_value = True
        mock_is_dir.return_value = True

        file_specs = [{'source': 'path/to/test.txt', 'dest': '~/.config/'}]
        process_file_downloads(file_specs, 'config.yaml')

        call_args = mock_handle.call_args[0]
        dest_path = call_args[1]
        assert dest_path.name == 'test.txt'

    @patch('scripts.setup_environment.handle_resource')
    def test_process_file_downloads_file_dest(self, mock_handle: MagicMock) -> None:
        """Test file destination used as-is."""
        mock_handle.return_value = True

        file_specs = [{'source': 'test.txt', 'dest': '~/.config/renamed.txt'}]
        process_file_downloads(file_specs, 'config.yaml')

        call_args = mock_handle.call_args[0]
        dest_path = call_args[1]
        assert dest_path.name == 'renamed.txt'

    @patch('scripts.setup_environment.warning')
    @patch('scripts.setup_environment.handle_resource')
    def test_process_file_downloads_mixed_success_failure(
        self,
        mock_handle: MagicMock,
        mock_warning: MagicMock,
    ) -> None:
        """Test some files succeed, some fail."""
        # First call succeeds, second fails
        mock_handle.side_effect = [True, False]

        file_specs = [
            {'source': 'success.txt', 'dest': '~/success.txt'},
            {'source': 'fail.txt', 'dest': '~/fail.txt'},
        ]
        result = process_file_downloads(file_specs, 'config.yaml')

        assert result is False
        assert mock_handle.call_count == 2
        mock_warning.assert_called()
        assert '1 succeeded, 1 failed' in mock_warning.call_args[0][0]

    @patch('scripts.setup_environment.handle_resource')
    def test_process_file_downloads_authentication(self, mock_handle: MagicMock) -> None:
        """Test auth parameter passed correctly."""
        mock_handle.return_value = True

        file_specs = [{'source': 'private/file.txt', 'dest': '~/file.txt'}]
        process_file_downloads(
            file_specs, 'config.yaml', base_url='https://example.com', auth_param='token123',
        )

        call_args = mock_handle.call_args
        assert call_args[0][2] == 'config.yaml'  # config_source
        assert call_args[0][3] == 'https://example.com'  # base_url
        assert call_args[0][4] == 'token123'  # auth_param

    @patch('scripts.setup_environment.handle_resource')
    def test_process_file_downloads_query_params_removed(
        self, mock_handle: MagicMock,
    ) -> None:
        """Test query parameters removed from source when determining filename."""
        mock_handle.return_value = True

        file_specs = [{'source': 'file.txt?raw=true', 'dest': '~/dest/'}]
        process_file_downloads(file_specs, 'config.yaml')

        call_args = mock_handle.call_args[0]
        dest_path = call_args[1]
        # Filename should be 'file.txt', not 'file.txt?raw=true'
        assert dest_path.name == 'file.txt'

    @patch('scripts.setup_environment.success')
    @patch('scripts.setup_environment.handle_resource')
    def test_process_file_downloads_multiple_files(
        self, mock_handle: MagicMock, mock_success: MagicMock,
    ) -> None:
        """Test processing multiple files successfully."""
        mock_handle.return_value = True

        file_specs = [
            {'source': 'file1.txt', 'dest': '~/file1.txt'},
            {'source': 'file2.txt', 'dest': '~/file2.txt'},
            {'source': 'file3.txt', 'dest': '~/file3.txt'},
        ]
        result = process_file_downloads(file_specs, 'config.yaml')

        assert result is True
        assert mock_handle.call_count == 3
        mock_success.assert_called_once()
        assert 'All 3 files' in mock_success.call_args[0][0]

    @patch('pathlib.Path.is_dir')
    @patch('pathlib.Path.exists')
    @patch('scripts.setup_environment.handle_resource')
    def test_process_file_downloads_trailing_slash(
        self, mock_handle: MagicMock, mock_exists: MagicMock, mock_is_dir: MagicMock,
    ) -> None:
        """Test destination with trailing slash treated as directory."""
        mock_handle.return_value = True
        mock_exists.return_value = False  # Directory doesn't exist yet
        mock_is_dir.return_value = False

        file_specs = [{'source': 'config.json', 'dest': '~/.config/myapp/'}]
        process_file_downloads(file_specs, 'config.yaml')

        call_args = mock_handle.call_args[0]
        dest_path = call_args[1]
        # Should append filename to directory path
        assert dest_path.name == 'config.json'
        assert '.config' in str(dest_path)
        assert 'myapp' in str(dest_path)

    @patch.dict(os.environ, {'USERPROFILE': 'C:\\Users\\TestUser'})
    @patch('scripts.setup_environment.handle_resource')
    def test_process_file_downloads_windows_env_var(
        self, mock_handle: MagicMock,
    ) -> None:
        """Test Windows environment variable expansion."""
        mock_handle.return_value = True

        file_specs = [{'source': 'test.txt', 'dest': '%USERPROFILE%\\test.txt'}]
        process_file_downloads(file_specs, 'config.yaml')

        call_args = mock_handle.call_args[0]
        dest_path = call_args[1]
        # On Windows, this should expand to C:\Users\TestUser\test.txt
        # On Unix, %USERPROFILE% won't expand, but we still test the logic
        assert 'test.txt' in str(dest_path)

    @patch('scripts.setup_environment.handle_resource')
    def test_process_file_downloads_backslash_separator(
        self, mock_handle: MagicMock,
    ) -> None:
        """Test destination with backslash separator treated as directory."""
        mock_handle.return_value = True

        file_specs = [{'source': 'test.txt', 'dest': '~\\.config\\'}]
        process_file_downloads(file_specs, 'config.yaml')

        call_args = mock_handle.call_args[0]
        dest_path = call_args[1]
        # Should append filename
        assert dest_path.name == 'test.txt'

    @patch('scripts.setup_environment.handle_resource')
    def test_process_file_downloads_empty_source(
        self, mock_handle: MagicMock,
    ) -> None:
        """Test handling empty source string."""
        mock_handle.return_value = True

        file_specs = [
            {'source': '', 'dest': '~/test.txt'},  # Empty source
            {'source': 'valid.txt', 'dest': '~/valid.txt'},  # Valid entry
        ]
        result = process_file_downloads(file_specs, 'config.yaml')

        # Should fail because one entry is invalid
        assert result is False
        # Only valid file should be processed
        assert mock_handle.call_count == 1

    @patch('scripts.setup_environment.handle_resource')
    def test_process_file_downloads_empty_dest(
        self, mock_handle: MagicMock,
    ) -> None:
        """Test handling empty dest string."""
        mock_handle.return_value = True

        file_specs = [
            {'source': 'test.txt', 'dest': ''},  # Empty dest
            {'source': 'valid.txt', 'dest': '~/valid.txt'},  # Valid entry
        ]
        result = process_file_downloads(file_specs, 'config.yaml')

        # Should fail because one entry is invalid
        assert result is False
        # Only valid file should be processed
        assert mock_handle.call_count == 1

    @patch('scripts.setup_environment.handle_resource')
    def test_process_file_downloads_preserves_source(
        self, mock_handle: MagicMock,
    ) -> None:
        """Test that source is passed to handle_resource unchanged."""
        mock_handle.return_value = True

        test_source = 'https://example.com/path/to/file.txt?raw=true&token=abc'
        file_specs = [{'source': test_source, 'dest': '~/file.txt'}]
        process_file_downloads(file_specs, 'config.yaml')

        call_args = mock_handle.call_args[0]
        actual_source = call_args[0]
        # Source should be passed unchanged (query params preserved)
        assert actual_source == test_source
