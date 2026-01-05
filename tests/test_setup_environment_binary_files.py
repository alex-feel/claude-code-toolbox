"""Tests for binary file handling in setup_environment.py."""

import tempfile
import urllib.error
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from scripts import setup_environment
from scripts.setup_environment import BINARY_EXTENSIONS
from scripts.setup_environment import fetch_url_bytes_with_auth
from scripts.setup_environment import handle_resource
from scripts.setup_environment import is_binary_file
from scripts.setup_environment import process_skill


class TestBinaryExtensions:
    """Test BINARY_EXTENSIONS constant."""

    def test_binary_extensions_is_frozenset(self) -> None:
        """Test that BINARY_EXTENSIONS is immutable."""
        assert isinstance(BINARY_EXTENSIONS, frozenset)

    def test_binary_extensions_contains_archives(self) -> None:
        """Test that common archive extensions are included."""
        archive_extensions = ['.tar.gz', '.tgz', '.gz', '.zip', '.7z', '.tar', '.bz2', '.xz']
        for ext in archive_extensions:
            assert ext in BINARY_EXTENSIONS, f'{ext} should be in BINARY_EXTENSIONS'

    def test_binary_extensions_contains_images(self) -> None:
        """Test that common image extensions are included."""
        image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.webp']
        for ext in image_extensions:
            assert ext in BINARY_EXTENSIONS, f'{ext} should be in BINARY_EXTENSIONS'


class TestIsBinaryFile:
    """Test binary file detection."""

    @pytest.mark.parametrize(
        'filename',
        [
            'archive.tar.gz',
            'file.tgz',
            'data.gz',
            'package.zip',
            'archive.7z',
            'backup.tar',
            'compressed.bz2',
            'image.png',
            'photo.jpg',
            'icon.ico',
            'document.pdf',
            'program.exe',
            'wheel.whl',
        ],
    )
    def test_binary_extensions_detected(self, filename: str) -> None:
        """Test that known binary extensions are detected."""
        assert is_binary_file(filename) is True

    @pytest.mark.parametrize(
        'filename',
        [
            'script.py',
            'config.yaml',
            'readme.md',
            'style.css',
            'app.js',
            'data.json',
            'template.html',
            'SKILL.md',
            'hook.sh',
        ],
    )
    def test_text_extensions_not_detected(self, filename: str) -> None:
        """Test that text file extensions are not detected as binary."""
        assert is_binary_file(filename) is False

    def test_case_insensitive(self) -> None:
        """Test that detection is case-insensitive."""
        assert is_binary_file('FILE.TAR.GZ') is True
        assert is_binary_file('Image.PNG') is True
        assert is_binary_file('ARCHIVE.ZIP') is True

    def test_url_with_binary_extension(self) -> None:
        """Test detection works with full URLs."""
        url = 'https://example.com/path/to/archive.tar.gz'
        assert is_binary_file(url) is True

    def test_path_with_binary_extension(self) -> None:
        """Test detection works with Path objects."""
        path = Path('/home/user/files/data.zip')
        assert is_binary_file(path) is True

    def test_path_with_text_extension(self) -> None:
        """Test detection works with Path objects for text files."""
        path = Path('/home/user/files/script.py')
        assert is_binary_file(path) is False


class TestFetchUrlBytesWithAuth:
    """Test binary URL fetching."""

    @patch('scripts.setup_environment.urlopen')
    @patch('scripts.setup_environment.detect_repo_type')
    def test_fetch_binary_content(self, mock_detect: MagicMock, mock_urlopen: MagicMock) -> None:
        """Test fetching binary content returns bytes."""
        mock_detect.return_value = None
        # Simulate gzip magic number at start
        binary_content = b'\x1f\x8b\x08\x00...'
        mock_response = MagicMock()
        mock_response.read.return_value = binary_content
        mock_urlopen.return_value = mock_response

        result = fetch_url_bytes_with_auth('https://example.com/file.tar.gz')

        assert isinstance(result, bytes)
        assert result == binary_content

    @patch('scripts.setup_environment.urlopen')
    @patch('scripts.setup_environment.get_auth_headers')
    @patch('scripts.setup_environment.detect_repo_type')
    @patch('scripts.setup_environment.info')
    def test_fetch_with_auth_retry(
        self,
        mock_info: MagicMock,
        mock_detect: MagicMock,
        mock_auth: MagicMock,
        mock_urlopen: MagicMock,
    ) -> None:
        """Test auth retry mechanism for binary files."""
        del mock_info
        mock_detect.return_value = None
        mock_auth.return_value = {'Authorization': 'Bearer token'}

        # First call fails with 401, second succeeds
        mock_response = MagicMock()
        mock_response.read.return_value = b'binary data'
        mock_urlopen.side_effect = [
            urllib.error.HTTPError('url', 401, 'Unauthorized', MagicMock(), None),
            mock_response,
        ]

        result = fetch_url_bytes_with_auth(
            'https://example.com/file.tar.gz',
            auth_param='token123',
        )

        assert result == b'binary data'

    @patch('scripts.setup_environment.urlopen')
    @patch('scripts.setup_environment.detect_repo_type')
    @patch('scripts.setup_environment.convert_gitlab_url_to_api')
    @patch('scripts.setup_environment.info')
    def test_gitlab_url_conversion(
        self,
        mock_info: MagicMock,
        mock_convert: MagicMock,
        mock_detect: MagicMock,
        mock_urlopen: MagicMock,
    ) -> None:
        """Test GitLab URL conversion for binary files."""
        del mock_info
        mock_detect.return_value = 'gitlab'
        mock_convert.return_value = 'https://gitlab.com/api/v4/converted'

        mock_response = MagicMock()
        mock_response.read.return_value = b'gitlab binary data'
        mock_urlopen.return_value = mock_response

        result = fetch_url_bytes_with_auth('https://gitlab.com/project/-/raw/main/file.tar.gz')

        assert result == b'gitlab binary data'
        mock_convert.assert_called_once()


class TestHandleResourceBinary:
    """Test handle_resource with binary files."""

    @patch('scripts.setup_environment.fetch_url_bytes_with_auth')
    @patch('scripts.setup_environment.resolve_resource_path')
    @patch('scripts.setup_environment.success')
    @patch('scripts.setup_environment.info')
    def test_handle_remote_binary_file(
        self,
        mock_info: MagicMock,
        mock_success: MagicMock,
        mock_resolve: MagicMock,
        mock_fetch_bytes: MagicMock,
    ) -> None:
        """Test downloading remote binary file."""
        del mock_info, mock_success
        binary_content = b'\x1f\x8b\x08\x00binary content'
        mock_fetch_bytes.return_value = binary_content
        mock_resolve.return_value = ('https://example.com/file.tar.gz', True)

        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / 'file.tar.gz'

            result = handle_resource(
                'https://example.com/file.tar.gz',
                dest,
                'https://example.com/config.yaml',
            )

            assert result is True
            assert dest.exists()
            assert dest.read_bytes() == binary_content
            mock_fetch_bytes.assert_called_once()

    @patch('scripts.setup_environment.fetch_url_with_auth')
    @patch('scripts.setup_environment.resolve_resource_path')
    @patch('scripts.setup_environment.success')
    @patch('scripts.setup_environment.info')
    def test_handle_remote_text_file(
        self,
        mock_info: MagicMock,
        mock_success: MagicMock,
        mock_resolve: MagicMock,
        mock_fetch_text: MagicMock,
    ) -> None:
        """Test downloading remote text file still works."""
        del mock_info, mock_success
        mock_fetch_text.return_value = '# Test content'
        mock_resolve.return_value = ('https://example.com/file.md', True)

        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / 'file.md'

            result = handle_resource(
                'https://example.com/file.md',
                dest,
                'https://example.com/config.yaml',
            )

            assert result is True
            assert dest.exists()
            assert dest.read_text() == '# Test content'
            mock_fetch_text.assert_called_once()


class TestProcessSkillBinary:
    """Test process_skill with binary files."""

    @patch('scripts.setup_environment.fetch_url_bytes_with_auth')
    @patch('scripts.setup_environment.fetch_url_with_auth')
    @patch('scripts.setup_environment.convert_to_raw_url')
    @patch('scripts.setup_environment.info')
    @patch('scripts.setup_environment.success')
    def test_skill_with_binary_file(
        self,
        mock_success: MagicMock,
        mock_info: MagicMock,
        mock_convert: MagicMock,
        mock_fetch_text: MagicMock,
        mock_fetch_bytes: MagicMock,
    ) -> None:
        """Test skill installation with mixed text and binary files."""
        del mock_success, mock_info
        mock_convert.return_value = 'https://example.com/skills/test-skill'
        mock_fetch_text.return_value = '# Skill content'
        mock_fetch_bytes.return_value = b'\x1f\x8b\x08\x00binary'

        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / 'skills'
            skills_dir.mkdir()

            skill_config: dict[str, Any] = {
                'name': 'test-skill',
                'base': 'https://example.com/skills/test-skill',
                'files': ['SKILL.md', 'data.tar.gz'],
            }

            result = process_skill(
                skill_config,
                skills_dir,
                'https://example.com/config.yaml',
            )

            assert result is True
            skill_dir = skills_dir / 'test-skill'
            assert (skill_dir / 'SKILL.md').exists()
            assert (skill_dir / 'data.tar.gz').exists()

            # Verify binary file was written correctly
            assert (skill_dir / 'data.tar.gz').read_bytes() == b'\x1f\x8b\x08\x00binary'

            # Verify text function called for .md, bytes function for .tar.gz
            mock_fetch_text.assert_called_once()
            mock_fetch_bytes.assert_called_once()

    @patch('scripts.setup_environment.fetch_url_bytes_with_auth')
    @patch('scripts.setup_environment.fetch_url_with_auth')
    @patch('scripts.setup_environment.convert_to_raw_url')
    @patch('scripts.setup_environment.info')
    @patch('scripts.setup_environment.success')
    def test_skill_with_nested_binary_file(
        self,
        mock_success: MagicMock,
        mock_info: MagicMock,
        mock_convert: MagicMock,
        mock_fetch_text: MagicMock,
        mock_fetch_bytes: MagicMock,
    ) -> None:
        """Test skill installation with nested binary file path (e.g., scripts/file.tar.gz)."""
        del mock_success, mock_info
        mock_convert.return_value = 'https://example.com/skills/web-artifacts-builder'
        mock_fetch_text.return_value = '# Web Artifacts Builder'
        mock_fetch_bytes.return_value = b'\x1f\x8b\x08\x00shadcn components'

        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / 'skills'
            skills_dir.mkdir()

            skill_config: dict[str, Any] = {
                'name': 'web-artifacts-builder',
                'base': 'https://example.com/skills/web-artifacts-builder',
                'files': ['SKILL.md', 'scripts/shadcn-components.tar.gz'],
            }

            result = setup_environment.process_skill(
                skill_config,
                skills_dir,
                'https://example.com/config.yaml',
            )

            assert result is True
            skill_dir = skills_dir / 'web-artifacts-builder'
            assert (skill_dir / 'SKILL.md').exists()
            assert (skill_dir / 'scripts' / 'shadcn-components.tar.gz').exists()

            # Verify binary file was written correctly
            assert (skill_dir / 'scripts' / 'shadcn-components.tar.gz').read_bytes() == b'\x1f\x8b\x08\x00shadcn components'

            # Verify bytes function was called for the .tar.gz file
            assert mock_fetch_bytes.call_count == 1
            assert 'shadcn-components.tar.gz' in mock_fetch_bytes.call_args[0][0]


class TestBinaryFileIntegration:
    """Integration tests for binary file handling."""

    @patch('scripts.setup_environment.urlopen')
    @patch('scripts.setup_environment.detect_repo_type')
    def test_gzip_magic_number_preserved(
        self,
        mock_detect: MagicMock,
        mock_urlopen: MagicMock,
    ) -> None:
        """Test that gzip magic number (0x1f 0x8b) is preserved in downloaded content."""
        mock_detect.return_value = None
        # Real gzip magic number
        gzip_content = b'\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\x03content'
        mock_response = MagicMock()
        mock_response.read.return_value = gzip_content
        mock_urlopen.return_value = mock_response

        result = fetch_url_bytes_with_auth('https://example.com/archive.tar.gz')

        # Verify magic number is preserved
        assert result[:2] == b'\x1f\x8b'
        assert result == gzip_content
