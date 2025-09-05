"""Tests for entity counting script."""

from unittest.mock import MagicMock
from unittest.mock import mock_open
from unittest.mock import patch

import pytest
from scripts.count_entities import count_files
from scripts.count_entities import count_valid_configs
from scripts.count_entities import main
from scripts.count_entities import validate_yaml


class TestCountFiles:
    """Test count_files function."""

    def test_count_files_existing_directory(self, temp_dir):
        """Test counting files in an existing directory."""
        # Create test files
        test_dir = temp_dir / 'test_dir'
        test_dir.mkdir()
        (test_dir / 'file1.md').write_text('content')
        (test_dir / 'file2.md').write_text('content')
        (test_dir / 'file3.txt').write_text('content')

        # Count .md files
        count = count_files(test_dir, '*.md')
        assert count == 2

        # Count .txt files
        count = count_files(test_dir, '*.txt')
        assert count == 1

        # Count all files
        count = count_files(test_dir, '*')
        assert count == 3

    def test_count_files_nonexistent_directory(self, temp_dir):
        """Test counting files in a non-existent directory."""
        non_existent = temp_dir / 'non_existent'
        count = count_files(non_existent, '*.md')
        assert count == 0

    def test_count_files_empty_directory(self, temp_dir):
        """Test counting files in an empty directory."""
        empty_dir = temp_dir / 'empty'
        empty_dir.mkdir()
        count = count_files(empty_dir, '*.md')
        assert count == 0

    def test_count_files_nested_pattern(self, temp_dir):
        """Test counting files with nested pattern."""
        test_dir = temp_dir / 'test_dir'
        nested_dir = test_dir / 'nested'
        nested_dir.mkdir(parents=True)
        (test_dir / 'file1.md').write_text('content')
        (nested_dir / 'file2.md').write_text('content')

        # Only counts files in direct directory
        count = count_files(test_dir, '*.md')
        assert count == 1

        # Use recursive pattern
        count = count_files(test_dir, '**/*.md')
        assert count == 2


class TestValidateYaml:
    """Test validate_yaml function."""

    def test_valid_yaml_file(self, temp_dir):
        """Test validation of a valid YAML file."""
        yaml_file = temp_dir / 'valid.yaml'
        yaml_file.write_text('''
name: Test
key: value
list:
  - item1
  - item2
''')
        assert validate_yaml(yaml_file) is True

    def test_invalid_yaml_file(self, temp_dir):
        """Test validation of an invalid YAML file."""
        yaml_file = temp_dir / 'invalid.yaml'
        yaml_file.write_text('''
name: Test
  invalid: indentation
''')
        assert validate_yaml(yaml_file) is False

    def test_empty_yaml_file(self, temp_dir):
        """Test validation of an empty YAML file."""
        yaml_file = temp_dir / 'empty.yaml'
        yaml_file.write_text('')
        assert validate_yaml(yaml_file) is True  # Empty YAML is technically valid

    def test_nonexistent_file(self, temp_dir):
        """Test validation of a non-existent file."""
        yaml_file = temp_dir / 'missing.yaml'
        assert validate_yaml(yaml_file) is False

    def test_non_yaml_file(self, temp_dir):
        """Test validation of a non-YAML file."""
        text_file = temp_dir / 'test.txt'
        text_file.write_text('This is not YAML: {{{')
        assert validate_yaml(text_file) is False  # Should fail YAML parsing


class TestCountValidConfigs:
    """Test count_valid_configs function."""

    def test_count_valid_configs_with_valid_files(self, temp_dir):
        """Test counting valid YAML configs."""
        env_dir = temp_dir / 'environments'
        env_dir.mkdir()

        # Create valid YAML files
        (env_dir / 'config1.yaml').write_text('name: Config1')
        (env_dir / 'config2.yml').write_text('name: Config2')
        (env_dir / 'config3.yaml').write_text('key: value')

        count = count_valid_configs(env_dir)
        assert count == 3

    def test_count_valid_configs_with_invalid_files(self, temp_dir):
        """Test counting excludes invalid YAML files."""
        env_dir = temp_dir / 'environments'
        env_dir.mkdir()

        # Mix of valid and invalid files
        (env_dir / 'valid.yaml').write_text('name: Valid')
        (env_dir / 'invalid.yaml').write_text('name: Test\n  bad: indentation')
        (env_dir / 'empty.yaml').write_text('')  # Empty is valid

        count = count_valid_configs(env_dir)
        assert count == 2  # valid.yaml and empty.yaml

    def test_count_valid_configs_nonexistent_directory(self, temp_dir):
        """Test counting in non-existent directory."""
        non_existent = temp_dir / 'non_existent'
        count = count_valid_configs(non_existent)
        assert count == 0

    def test_count_valid_configs_empty_directory(self, temp_dir):
        """Test counting in empty directory."""
        empty_dir = temp_dir / 'empty'
        empty_dir.mkdir()
        count = count_valid_configs(empty_dir)
        assert count == 0

    def test_count_valid_configs_ignores_non_yaml(self, temp_dir):
        """Test that non-YAML files are ignored."""
        env_dir = temp_dir / 'environments'
        env_dir.mkdir()

        (env_dir / 'config.yaml').write_text('name: Config')
        (env_dir / 'readme.md').write_text('# README')
        (env_dir / 'script.py').write_text('print("hello")')

        count = count_valid_configs(env_dir)
        assert count == 1  # Only config.yaml


class TestMainFunction:
    """Test main function."""

    @patch('scripts.count_entities.Path')
    @patch('scripts.count_entities.count_files')
    @patch('scripts.count_entities.count_valid_configs')
    @patch('builtins.print')
    def test_main_creates_output_structure(self, mock_print, mock_count_valid, mock_count_files, mock_path_class):
        """Test that main creates correct output structure."""
        # Setup mocks
        mock_root = MagicMock()
        mock_path_class.return_value.parent.parent = mock_root

        # Mock directory structure
        mock_badges_dir = MagicMock()
        mock_root.__truediv__.return_value = mock_badges_dir
        mock_badges_dir.__truediv__.return_value = mock_badges_dir

        # Mock count functions
        mock_count_valid.return_value = 5
        mock_count_files.return_value = 3

        # Mock file operations
        written_files = {}

        def mock_open_func(file_path, mode='r', **kwargs):  # noqa: ARG001
            if mode == 'w':
                mock_file = MagicMock()
                mock_file.__enter__ = MagicMock(return_value=mock_file)
                mock_file.__exit__ = MagicMock(return_value=None)
                written_files[str(file_path)] = mock_file
                return mock_file
            return MagicMock()

        with patch('builtins.open', side_effect=mock_open_func), \
             patch('json.dump') as mock_json_dump:
            main()

        # Verify directories were created
        mock_badges_dir.mkdir.assert_called_with(parents=True, exist_ok=True)

        # Verify JSON files were written
        assert mock_json_dump.call_count > 0

        # Verify summary was printed
        print_calls = [str(call[0][0]) for call in mock_print.call_args_list]
        assert any('Entity counts:' in call for call in print_calls)

    @patch('scripts.count_entities.Path')
    @patch('scripts.count_entities.count_files')
    @patch('scripts.count_entities.count_valid_configs')
    def test_main_calculates_totals_correctly(self, mock_count_valid, mock_count_files, mock_path_class):
        """Test that main calculates totals correctly."""
        # Setup mocks
        mock_root = MagicMock()
        mock_path_class.return_value.parent.parent = mock_root

        # Mock specific counts
        mock_count_valid.return_value = 2  # environments
        mock_count_files.side_effect = [
            1,  # env_templates (*.yaml)
            0,  # env_templates (*.yml)
            3,  # agents
            1,  # agent_templates
            2,  # commands
            0,  # command_templates
            4,  # prompts
            0,  # prompt_templates
            1,  # styles
            0,  # style_templates
            2,  # hooks (.py)
            1,  # hooks (.sh)
            0,  # hooks (.ps1)
        ]

        captured_data = {}

        def capture_json_dump(data, file_obj, **kwargs):  # noqa: ARG001
            if 'counts' in data:
                captured_data['main'] = data

        with patch('builtins.open', mock_open()), \
             patch('json.dump', side_effect=capture_json_dump):
            main()

        # Verify total calculation
        if 'main' in captured_data:
            counts = captured_data['main']['counts']
            expected_total = (
                counts['environments'] +
                counts['agents'] +
                counts['commands'] +
                counts['prompts'] +
                counts['styles'] +
                counts['hooks']
            )
            assert counts['total_components'] == expected_total

    @patch('scripts.count_entities.Path')
    @patch('scripts.count_entities.count_files')
    @patch('scripts.count_entities.count_valid_configs')
    def test_main_badge_data_structure(self, mock_count_valid, mock_count_files, mock_path_class):
        """Test that badge data has correct structure."""
        # Setup mocks
        mock_root = MagicMock()
        mock_path_class.return_value.parent.parent = mock_root

        mock_count_valid.return_value = 1
        mock_count_files.return_value = 1

        captured_badges = []

        def capture_json_dump(data, file_obj, **kwargs):  # noqa: ARG001
            if 'schemaVersion' in data:
                captured_badges.append(data)

        with patch('builtins.open', mock_open()), \
             patch('json.dump', side_effect=capture_json_dump):
            main()

        # Verify badge structure
        for badge in captured_badges:
            assert 'schemaVersion' in badge
            assert badge['schemaVersion'] == 1
            assert 'label' in badge
            assert 'message' in badge
            assert 'color' in badge

    @patch('scripts.count_entities.Path')
    @patch('scripts.count_entities.count_files')
    @patch('scripts.count_entities.count_valid_configs')
    def test_main_handles_zero_counts(self, mock_count_valid, mock_count_files, mock_path_class):
        """Test that main handles zero counts correctly."""
        # Setup mocks
        mock_root = MagicMock()
        mock_path_class.return_value.parent.parent = mock_root

        # All counts return 0
        mock_count_valid.return_value = 0
        mock_count_files.return_value = 0

        with patch('builtins.open', mock_open()), \
             patch('json.dump') as mock_json_dump:
            main()

        # Should still write files even with zero counts
        assert mock_json_dump.call_count > 0


class TestIntegration:
    """Integration tests."""

    def test_full_workflow(self, temp_dir):
        """Test the complete workflow with real file system."""
        # Create directory structure
        repo_root = temp_dir
        env_dir = repo_root / 'environments' / 'library'
        agents_dir = repo_root / 'agents' / 'library'
        env_dir.mkdir(parents=True)
        agents_dir.mkdir(parents=True)

        # Create test files
        (env_dir / 'python.yaml').write_text('''
name: Python Development
command-name: claude-python
''')
        (env_dir / 'javascript.yaml').write_text('''
name: JavaScript Development
command-name: claude-js
''')
        (agents_dir / 'agent1.md').write_text('# Agent 1')

        # Test individual functions
        env_count = count_valid_configs(env_dir)
        assert env_count == 2

        agent_count = count_files(agents_dir, '*.md')
        assert agent_count == 1

        # Test validate_yaml
        assert validate_yaml(env_dir / 'python.yaml') is True

    def test_handles_special_characters_in_paths(self, temp_dir):
        """Test handling of special characters in file paths."""
        env_dir = temp_dir / 'environments'
        env_dir.mkdir()

        # Create files with special characters (where filesystem allows)
        special_file = env_dir / 'test-env_2024.yaml'
        special_file.write_text('name: Test')

        count = count_valid_configs(env_dir)
        assert count == 1

    def test_mixed_file_extensions(self, temp_dir):
        """Test handling of both .yaml and .yml extensions."""
        env_dir = temp_dir / 'environments'
        env_dir.mkdir()

        (env_dir / 'config1.yaml').write_text('name: Config1')
        (env_dir / 'config2.yml').write_text('name: Config2')
        (env_dir / 'config3.YAML').write_text('name: Config3')  # Wrong case

        count = count_valid_configs(env_dir)
        # On Windows, glob is case-insensitive, so .YAML matches *.yaml
        import platform
        if platform.system() == 'Windows':
            assert count == 3  # All three files match on Windows
        else:
            assert count == 2  # Only .yaml and .yml on Unix

    @pytest.mark.parametrize(('pattern', 'expected'), [
        ('*.py', 2),
        ('*.sh', 1),
        ('*.ps1', 0),
        ('*.md', 0),
    ])
    def test_count_files_with_patterns(self, temp_dir, pattern, expected):
        """Test count_files with various patterns."""
        test_dir = temp_dir / 'hooks'
        test_dir.mkdir()

        (test_dir / 'hook1.py').write_text('print("1")')
        (test_dir / 'hook2.py').write_text('print("2")')
        (test_dir / 'hook.sh').write_text('echo "hook"')

        count = count_files(test_dir, pattern)
        assert count == expected
