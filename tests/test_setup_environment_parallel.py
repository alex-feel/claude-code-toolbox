"""Tests for parallel execution functionality in setup_environment.py."""

import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

import setup_environment
from setup_environment import DEFAULT_PARALLEL_WORKERS
from setup_environment import execute_parallel
from setup_environment import execute_parallel_safe
from setup_environment import is_parallel_mode_enabled


class TestIsParallelModeEnabled:
    """Test the is_parallel_mode_enabled function."""

    def test_parallel_mode_enabled_by_default(self) -> None:
        """Test that parallel mode is enabled by default."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove CLAUDE_SEQUENTIAL_MODE if it exists
            os.environ.pop('CLAUDE_SEQUENTIAL_MODE', None)
            assert is_parallel_mode_enabled() is True

    def test_parallel_mode_disabled_with_1(self) -> None:
        """Test that CLAUDE_SEQUENTIAL_MODE=1 disables parallel mode."""
        with patch.dict(os.environ, {'CLAUDE_SEQUENTIAL_MODE': '1'}):
            assert is_parallel_mode_enabled() is False

    def test_parallel_mode_disabled_with_true(self) -> None:
        """Test that CLAUDE_SEQUENTIAL_MODE=true disables parallel mode."""
        with patch.dict(os.environ, {'CLAUDE_SEQUENTIAL_MODE': 'true'}):
            assert is_parallel_mode_enabled() is False

    def test_parallel_mode_disabled_with_yes(self) -> None:
        """Test that CLAUDE_SEQUENTIAL_MODE=yes disables parallel mode."""
        with patch.dict(os.environ, {'CLAUDE_SEQUENTIAL_MODE': 'yes'}):
            assert is_parallel_mode_enabled() is False

    def test_parallel_mode_disabled_case_insensitive(self) -> None:
        """Test that CLAUDE_SEQUENTIAL_MODE is case insensitive."""
        with patch.dict(os.environ, {'CLAUDE_SEQUENTIAL_MODE': 'TRUE'}):
            assert is_parallel_mode_enabled() is False
        with patch.dict(os.environ, {'CLAUDE_SEQUENTIAL_MODE': 'Yes'}):
            assert is_parallel_mode_enabled() is False

    def test_parallel_mode_enabled_with_other_values(self) -> None:
        """Test that other values keep parallel mode enabled."""
        with patch.dict(os.environ, {'CLAUDE_SEQUENTIAL_MODE': '0'}):
            assert is_parallel_mode_enabled() is True
        with patch.dict(os.environ, {'CLAUDE_SEQUENTIAL_MODE': 'false'}):
            assert is_parallel_mode_enabled() is True
        with patch.dict(os.environ, {'CLAUDE_SEQUENTIAL_MODE': 'no'}):
            assert is_parallel_mode_enabled() is True


class TestExecuteParallel:
    """Test the execute_parallel function."""

    def test_empty_list_returns_empty(self) -> None:
        """Test that empty input returns empty output."""
        result = execute_parallel([], lambda x: x)
        assert result == []

    def test_single_item_processing(self) -> None:
        """Test processing a single item."""
        result = execute_parallel([1], lambda x: x * 2)
        assert result == [2]

    def test_multiple_items_processing(self) -> None:
        """Test processing multiple items."""
        result = execute_parallel([1, 2, 3, 4, 5], lambda x: x * 2)
        assert result == [2, 4, 6, 8, 10]

    def test_order_preserved(self) -> None:
        """Test that result order matches input order."""
        # Use a function with varying execution times to test ordering
        def slow_func(x: int) -> int:
            time.sleep(0.01 * (5 - x))  # Reverse time - higher numbers finish faster
            return x * 10

        result = execute_parallel([1, 2, 3, 4, 5], slow_func)
        assert result == [10, 20, 30, 40, 50]

    def test_exception_raised_on_failure(self) -> None:
        """Test that exceptions are re-raised."""

        def failing_func(x: int) -> int:
            if x == 3:
                raise ValueError(f'Failed on {x}')
            return x * 2

        with pytest.raises(ValueError, match='Failed on 3'):
            execute_parallel([1, 2, 3, 4, 5], failing_func)

    def test_sequential_mode_fallback(self) -> None:
        """Test that sequential mode processes items in order."""
        call_order: list[int] = []

        def tracking_func(x: int) -> int:
            call_order.append(x)
            return x * 2

        with patch.dict(os.environ, {'CLAUDE_SEQUENTIAL_MODE': '1'}):
            result = execute_parallel([1, 2, 3, 4, 5], tracking_func)

        assert result == [2, 4, 6, 8, 10]
        assert call_order == [1, 2, 3, 4, 5]  # Sequential order preserved

    def test_default_max_workers(self) -> None:
        """Test that default max_workers is 3 (reduced from 5 to minimize rate limiting)."""
        assert DEFAULT_PARALLEL_WORKERS == 3

    def test_custom_max_workers(self) -> None:
        """Test that custom max_workers is respected."""
        # This test verifies the function accepts max_workers parameter
        result = execute_parallel([1, 2, 3], lambda x: x * 2, max_workers=2)
        assert result == [2, 4, 6]


class TestExecuteParallelSafe:
    """Test the execute_parallel_safe function."""

    def test_empty_list_returns_empty(self) -> None:
        """Test that empty input returns empty output."""
        result = execute_parallel_safe([], lambda x: x, default_on_error=0)
        assert result == []

    def test_successful_processing(self) -> None:
        """Test successful processing of all items."""
        result = execute_parallel_safe([1, 2, 3], lambda x: x * 2, default_on_error=0)
        assert result == [2, 4, 6]

    def test_failed_items_return_default(self) -> None:
        """Test that failed items return the default value."""

        def failing_func(x: int) -> int:
            if x == 2:
                raise ValueError(f'Failed on {x}')
            return x * 10

        result = execute_parallel_safe([1, 2, 3], failing_func, default_on_error=-1)
        assert result == [10, -1, 30]

    def test_all_failures_return_defaults(self) -> None:
        """Test that all failures return default values."""

        def always_fail(_x: int) -> int:
            raise RuntimeError('Always fails')

        result = execute_parallel_safe([1, 2, 3], always_fail, default_on_error=0)
        assert result == [0, 0, 0]

    def test_order_preserved_with_failures(self) -> None:
        """Test that order is preserved even with failures."""

        def sometimes_fail(x: int) -> int:
            if x % 2 == 0:
                raise ValueError('Even number')
            return x

        result = execute_parallel_safe([1, 2, 3, 4, 5], sometimes_fail, default_on_error=-1)
        assert result == [1, -1, 3, -1, 5]

    def test_sequential_mode_with_safe_execution(self) -> None:
        """Test sequential mode with safe execution."""

        def sometimes_fail(x: int) -> int:
            if x == 3:
                raise ValueError('Failed')
            return x * 2

        with patch.dict(os.environ, {'CLAUDE_SEQUENTIAL_MODE': '1'}):
            result = execute_parallel_safe([1, 2, 3, 4, 5], sometimes_fail, default_on_error=-1)

        assert result == [2, 4, -1, 8, 10]


class TestValidationWithParallelExecution:
    """Test validate_all_config_files with parallel execution."""

    @patch('setup_environment.resolve_resource_path')
    @patch('setup_environment.FileValidator')
    def test_parallel_validation_order_preserved(
        self,
        mock_validator_class: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """Test that validation results maintain correct order."""
        mock_validator = MagicMock()
        mock_validator_class.return_value = mock_validator

        # Simulate varying validation times
        mock_resolve.side_effect = [
            ('https://example.com/file1.md', True),
            ('https://example.com/file2.md', True),
            ('https://example.com/file3.md', True),
        ]

        mock_validator.validate.side_effect = [
            (True, 'HEAD'),
            (True, 'Range'),
            (True, 'HEAD'),
        ]

        config = {'agents': ['file1.md', 'file2.md', 'file3.md']}

        all_valid, results = setup_environment.validate_all_config_files(
            config,
            'https://example.com',
            auth_param=None,
        )

        assert all_valid is True
        assert len(results) == 3
        assert results[0] == ('agent', 'file1.md', True, 'HEAD')
        assert results[1] == ('agent', 'file2.md', True, 'Range')
        assert results[2] == ('agent', 'file3.md', True, 'HEAD')

    @patch('setup_environment.resolve_resource_path')
    @patch('setup_environment.FileValidator')
    def test_validation_sequential_mode(
        self,
        mock_validator_class: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """Test validation in sequential mode."""
        mock_validator = MagicMock()
        mock_validator_class.return_value = mock_validator

        mock_resolve.side_effect = [
            ('https://example.com/file1.md', True),
            ('https://example.com/file2.md', True),
        ]

        mock_validator.validate.side_effect = [
            (True, 'HEAD'),
            (False, 'None'),
        ]

        config = {'agents': ['file1.md', 'file2.md']}

        with patch.dict(os.environ, {'CLAUDE_SEQUENTIAL_MODE': '1'}):
            all_valid, results = setup_environment.validate_all_config_files(
                config,
                'https://example.com',
                auth_param=None,
            )

        assert all_valid is False
        assert len(results) == 2
        assert results[0][2] is True
        assert results[1][2] is False


class TestDownloadsWithParallelExecution:
    """Test download functions with parallel execution."""

    @patch('setup_environment.handle_resource')
    def test_process_resources_parallel(self, mock_handle: MagicMock) -> None:
        """Test that process_resources uses parallel execution."""
        mock_handle.return_value = True

        with tempfile.TemporaryDirectory() as tmpdir:
            dest_dir = Path(tmpdir)
            resources = ['file1.md', 'file2.md', 'file3.md']

            result = setup_environment.process_resources(
                resources,
                dest_dir,
                'test_resources',
                'https://example.com',
            )

        assert result is True
        assert mock_handle.call_count == 3

    @patch('setup_environment.handle_resource')
    def test_process_resources_sequential_mode(self, mock_handle: MagicMock) -> None:
        """Test process_resources in sequential mode."""
        mock_handle.return_value = True

        with tempfile.TemporaryDirectory() as tmpdir:
            dest_dir = Path(tmpdir)
            resources = ['file1.md', 'file2.md']

            with patch.dict(os.environ, {'CLAUDE_SEQUENTIAL_MODE': '1'}):
                result = setup_environment.process_resources(
                    resources,
                    dest_dir,
                    'test_resources',
                    'https://example.com',
                )

        assert result is True
        assert mock_handle.call_count == 2

    @patch('setup_environment.handle_resource')
    def test_process_resources_partial_failure(self, mock_handle: MagicMock) -> None:
        """Test process_resources with some failures."""
        mock_handle.side_effect = [True, False, True]

        with tempfile.TemporaryDirectory() as tmpdir:
            dest_dir = Path(tmpdir)
            resources = ['file1.md', 'file2.md', 'file3.md']

            result = setup_environment.process_resources(
                resources,
                dest_dir,
                'test_resources',
                'https://example.com',
            )

        assert result is False  # At least one failure

    @patch('setup_environment.handle_resource')
    def test_download_hook_files_parallel(self, mock_handle: MagicMock) -> None:
        """Test that download_hook_files uses parallel execution."""
        mock_handle.return_value = True

        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)
            hooks = {'files': ['hook1.py', 'hook2.py', 'hook3.py']}

            result = setup_environment.download_hook_files(
                hooks,
                claude_dir,
                config_source='https://example.com',
            )

        assert result is True
        assert mock_handle.call_count == 3

    @patch('setup_environment.handle_resource')
    def test_download_hook_files_no_config_source(self, mock_handle: MagicMock) -> None:
        """Test download_hook_files returns False when no config_source."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)
            hooks = {'files': ['hook1.py']}

            result = setup_environment.download_hook_files(
                hooks,
                claude_dir,
                config_source=None,
            )

        assert result is False
        mock_handle.assert_not_called()

    @patch('setup_environment.handle_resource')
    def test_process_file_downloads_parallel(self, mock_handle: MagicMock) -> None:
        """Test that process_file_downloads uses parallel execution."""
        mock_handle.return_value = True

        file_specs = [
            {'source': 'file1.txt', 'dest': '/tmp/file1.txt'},
            {'source': 'file2.txt', 'dest': '/tmp/file2.txt'},
            {'source': 'file3.txt', 'dest': '/tmp/file3.txt'},
        ]

        result = setup_environment.process_file_downloads(
            file_specs,
            'https://example.com',
        )

        assert result is True
        assert mock_handle.call_count == 3

    @patch('setup_environment.handle_resource')
    def test_process_file_downloads_with_invalid_specs(self, mock_handle: MagicMock) -> None:
        """Test process_file_downloads handles invalid specs."""
        mock_handle.return_value = True

        file_specs = [
            {'source': 'file1.txt', 'dest': '/tmp/file1.txt'},  # Valid
            {'source': 'file2.txt'},  # Missing dest
            {'dest': '/tmp/file3.txt'},  # Missing source
            {'source': 'file4.txt', 'dest': '/tmp/file4.txt'},  # Valid
        ]

        result = setup_environment.process_file_downloads(
            file_specs,
            'https://example.com',
        )

        assert result is False  # 2 invalid specs
        assert mock_handle.call_count == 2  # Only valid specs processed


class TestParallelExecutionPerformance:
    """Test that parallel execution actually improves performance."""

    def test_parallel_faster_than_sequential(self) -> None:
        """Test that parallel execution is faster for I/O-bound tasks."""

        def slow_task(x: int) -> int:
            time.sleep(0.05)  # 50ms delay
            return x * 2

        items = [1, 2, 3, 4, 5]

        # Measure sequential time
        with patch.dict(os.environ, {'CLAUDE_SEQUENTIAL_MODE': '1'}):
            start = time.time()
            execute_parallel(items, slow_task)
            sequential_time = time.time() - start

        # Measure parallel time
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop('CLAUDE_SEQUENTIAL_MODE', None)
            start = time.time()
            execute_parallel(items, slow_task)
            parallel_time = time.time() - start

        # Parallel should be significantly faster (at least 2x for 5 items)
        # Being conservative with 1.5x to account for thread overhead
        assert parallel_time < sequential_time * 0.7, (
            f'Parallel ({parallel_time:.3f}s) should be significantly faster '
            f'than sequential ({sequential_time:.3f}s)'
        )


class TestSkillsWithParallelExecution:
    """Test skills processing with parallel execution."""

    @patch('setup_environment.process_skill')
    def test_process_skills_parallel_all_success(
        self,
        mock_process_skill: MagicMock,
    ) -> None:
        """Test parallel skills processing with all successful."""
        mock_process_skill.return_value = True

        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / 'skills'
            skills_dir.mkdir()

            skills_config = [
                {'name': 'skill-1', 'base': 'https://example.com/skill-1', 'files': ['SKILL.md']},
                {'name': 'skill-2', 'base': 'https://example.com/skill-2', 'files': ['SKILL.md']},
                {'name': 'skill-3', 'base': 'https://example.com/skill-3', 'files': ['SKILL.md']},
            ]

            result = setup_environment.process_skills(
                skills_config,
                skills_dir,
                'https://example.com/config.yaml',
                None,
            )

            assert result is True
            assert mock_process_skill.call_count == 3

    @patch('setup_environment.process_skill')
    def test_process_skills_parallel_partial_failure(
        self,
        mock_process_skill: MagicMock,
    ) -> None:
        """Test parallel skills processing with partial failure."""
        # First and third succeed, second fails
        mock_process_skill.side_effect = [True, False, True]

        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / 'skills'
            skills_dir.mkdir()

            skills_config = [
                {'name': 'skill-1', 'base': 'https://example.com/skill-1', 'files': ['SKILL.md']},
                {'name': 'skill-2', 'base': 'https://example.com/skill-2', 'files': ['SKILL.md']},
                {'name': 'skill-3', 'base': 'https://example.com/skill-3', 'files': ['SKILL.md']},
            ]

            result = setup_environment.process_skills(
                skills_config,
                skills_dir,
                'https://example.com/config.yaml',
                None,
            )

            assert result is False  # At least one failed
            assert mock_process_skill.call_count == 3

    @patch('setup_environment.process_skill')
    def test_process_skills_sequential_mode(
        self,
        mock_process_skill: MagicMock,
    ) -> None:
        """Test skills processing respects sequential mode."""
        mock_process_skill.return_value = True

        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / 'skills'
            skills_dir.mkdir()

            skills_config = [
                {'name': 'skill-1', 'base': 'https://example.com/skill-1', 'files': ['SKILL.md']},
            ]

            with patch.dict(os.environ, {'CLAUDE_SEQUENTIAL_MODE': '1'}):
                result = setup_environment.process_skills(
                    skills_config,
                    skills_dir,
                    'https://example.com/config.yaml',
                    None,
                )

            assert result is True
