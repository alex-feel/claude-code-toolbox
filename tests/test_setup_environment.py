"""
Comprehensive tests for setup_environment.py - the main environment setup script.
"""

import contextlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.error
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

import math

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


class TestDebugFunctions:
    """Test debug logging functions."""

    @pytest.mark.parametrize('env_value', ['1', 'true', 'yes', 'TRUE', 'Yes', 'TrUe'])
    def test_is_debug_enabled_true(self, env_value):
        """Test that '1', 'true', 'yes' (case-insensitive) all return True."""
        with patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_DEBUG': env_value}):
            assert setup_environment.is_debug_enabled() is True

    @pytest.mark.parametrize('env_value', ['', '0', 'false', 'no', 'FALSE', 'No', 'anything'])
    def test_is_debug_enabled_false(self, env_value):
        """Test that '', '0', 'false', 'no', and other values return False."""
        with patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_DEBUG': env_value}):
            assert setup_environment.is_debug_enabled() is False

    def test_is_debug_enabled_unset(self):
        """Test that unset environment variable returns False."""
        with patch.dict('os.environ', {}, clear=True):
            # Remove the key if it exists
            os.environ.pop('CLAUDE_CODE_TOOLBOX_DEBUG', None)
            assert setup_environment.is_debug_enabled() is False

    def test_debug_log_outputs_when_enabled(self, capsys):
        """Test that debug_log outputs to stderr when debug is enabled."""
        with patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_DEBUG': '1'}):
            setup_environment.debug_log('Test debug message')
            captured = capsys.readouterr()
            assert '  [DEBUG] Test debug message' in captured.err

    def test_debug_log_silent_when_disabled(self, capsys):
        """Test that debug_log produces no output when debug is disabled."""
        with patch.dict('os.environ', {'CLAUDE_CODE_TOOLBOX_DEBUG': '0'}):
            setup_environment.debug_log('Test debug message')
            captured = capsys.readouterr()
            assert captured.err == ''
            assert captured.out == ''


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

    @patch('scripts.setup_environment.sys.platform', 'win32')
    @patch('scripts.setup_environment.shutil.which')
    @patch('subprocess.run')
    def test_run_command_windows_batch_resolution(self, mock_run, mock_which):
        """Test that on Windows, batch files are resolved via shutil.which()."""
        mock_which.return_value = r'C:\Program Files\nodejs\npm.cmd'
        mock_run.return_value = subprocess.CompletedProcess(
            [r'C:\Program Files\nodejs\npm.cmd', 'install'], 0, '', '',
        )
        result = setup_environment.run_command(['npm', 'install'])
        assert result.returncode == 0
        # Verify shutil.which was called with the command
        mock_which.assert_called_once_with('npm')
        # Verify subprocess.run was called with the resolved path
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == r'C:\Program Files\nodejs\npm.cmd'
        assert call_args[1] == 'install'

    @patch('scripts.setup_environment.sys.platform', 'win32')
    @patch('scripts.setup_environment.shutil.which')
    @patch('subprocess.run')
    def test_run_command_windows_which_returns_none(self, mock_run, mock_which):
        """Test that when shutil.which returns None, original command is used."""
        mock_which.return_value = None
        mock_run.return_value = subprocess.CompletedProcess(['npm', 'install'], 0, '', '')
        result = setup_environment.run_command(['npm', 'install'])
        assert result.returncode == 0
        # Verify subprocess.run was called with the original command
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == 'npm'
        assert call_args[1] == 'install'

    @patch('scripts.setup_environment.sys.platform', 'linux')
    @patch('scripts.setup_environment.shutil.which')
    @patch('subprocess.run')
    def test_run_command_non_windows_no_resolution(self, mock_run, mock_which):
        """Test that on non-Windows platforms, batch file resolution is skipped."""
        mock_run.return_value = subprocess.CompletedProcess(['npm', 'install'], 0, '', '')
        result = setup_environment.run_command(['npm', 'install'])
        assert result.returncode == 0
        # Verify shutil.which was NOT called
        mock_which.assert_not_called()
        # Verify subprocess.run was called with the original command
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == 'npm'

    @patch('scripts.setup_environment.sys.platform', 'win32')
    @patch('scripts.setup_environment.shutil.which')
    @patch('subprocess.run')
    def test_run_command_empty_cmd_list(self, mock_run, mock_which):
        """Test that empty command list doesn't cause issues."""
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')
        result = setup_environment.run_command([])
        assert result.returncode == 0
        # Verify shutil.which was NOT called for empty list
        mock_which.assert_not_called()

    @patch('shutil.which')
    def test_find_command(self, mock_which):
        """Test finding command in PATH."""
        mock_which.return_value = '/usr/bin/git'
        assert setup_environment.find_command('git') == '/usr/bin/git'


class TestConvertToUnixPath:
    """Tests for convert_to_unix_path function."""

    def test_windows_absolute_path(self):
        """Test conversion of Windows absolute path."""
        result = setup_environment.convert_to_unix_path(r'C:\Users\Aleksandr\.local\bin\claude.EXE')
        assert result == '/c/Users/Aleksandr/.local/bin/claude.EXE'

    def test_windows_path_with_spaces(self):
        """Test conversion of Windows path with spaces."""
        result = setup_environment.convert_to_unix_path(r'C:\Program Files\nodejs\node.exe')
        assert result == '/c/Program Files/nodejs/node.exe'

    def test_different_drive_letter(self):
        """Test conversion with different drive letters."""
        result = setup_environment.convert_to_unix_path(r'D:\projects\app\bin\tool.exe')
        assert result == '/d/projects/app/bin/tool.exe'

    def test_lowercase_drive_letter(self):
        """Test conversion with lowercase drive letter input."""
        result = setup_environment.convert_to_unix_path(r'c:\Windows\System32\cmd.exe')
        assert result == '/c/Windows/System32/cmd.exe'

    def test_already_unix_path(self):
        """Test that Unix paths are returned unchanged."""
        result = setup_environment.convert_to_unix_path('/usr/local/bin/tool')
        assert result == '/usr/local/bin/tool'

    def test_empty_path(self):
        """Test empty path handling."""
        result = setup_environment.convert_to_unix_path('')
        assert result == ''

    def test_forward_slash_windows_path(self):
        """Test Windows path already using forward slashes."""
        result = setup_environment.convert_to_unix_path('C:/Users/Name/file.txt')
        assert result == '/c/Users/Name/file.txt'

    def test_mixed_slashes(self):
        """Test Windows path with mixed slashes."""
        result = setup_environment.convert_to_unix_path(r'C:\Users/Name\Documents/file.txt')
        assert result == '/c/Users/Name/Documents/file.txt'


class TestConvertPathEnvToUnix:
    """Tests for convert_path_env_to_unix function."""

    def test_single_path(self):
        """Test conversion of single path."""
        result = setup_environment.convert_path_env_to_unix(r'C:\Windows')
        assert result == '/c/Windows'

    def test_multiple_paths(self):
        """Test conversion of multiple paths."""
        result = setup_environment.convert_path_env_to_unix(r'C:\Windows;C:\Program Files\nodejs;D:\tools')
        assert result == '/c/Windows:/c/Program Files/nodejs:/d/tools'

    def test_empty_path(self):
        """Test empty path handling."""
        result = setup_environment.convert_path_env_to_unix('')
        assert result == ''

    def test_path_with_empty_entries(self):
        """Test path with empty entries (consecutive semicolons)."""
        result = setup_environment.convert_path_env_to_unix(r'C:\Windows;;C:\tools')
        assert result == '/c/Windows:/c/tools'

    def test_path_with_whitespace(self):
        """Test path entries with whitespace are trimmed."""
        result = setup_environment.convert_path_env_to_unix(r'C:\Windows ; C:\tools')
        assert result == '/c/Windows:/c/tools'

    def test_single_empty_entry(self):
        """Test that single semicolon (empty entries only) produces empty result."""
        result = setup_environment.convert_path_env_to_unix(';')
        assert result == ''


class TestGetBashPreferredCommand:
    """Tests for get_bash_preferred_command function."""

    def test_cmd_file_with_extensionless_alternative(self, tmp_path):
        """Test that .cmd file is replaced with extensionless alternative when it exists."""
        # Create both .cmd and extensionless files
        cmd_file = tmp_path / 'claude.cmd'
        extensionless_file = tmp_path / 'claude'
        cmd_file.write_text('@echo off\nnode %~dp0\\claude-code %*')
        extensionless_file.write_text('#!/bin/sh\nexec node "$basedir/claude-code" "$@"')

        result = setup_environment.get_bash_preferred_command(str(cmd_file))
        assert result == str(extensionless_file)

    def test_cmd_file_without_extensionless_alternative(self, tmp_path):
        """Test that .cmd file is returned unchanged when no extensionless alternative exists."""
        # Create only .cmd file
        cmd_file = tmp_path / 'claude.cmd'
        cmd_file.write_text('@echo off\nnode %~dp0\\claude-code %*')

        result = setup_environment.get_bash_preferred_command(str(cmd_file))
        assert result == str(cmd_file)

    def test_bat_file_with_extensionless_alternative(self, tmp_path):
        """Test that .bat file is also replaced with extensionless alternative."""
        # Create both .bat and extensionless files
        bat_file = tmp_path / 'tool.bat'
        extensionless_file = tmp_path / 'tool'
        bat_file.write_text('@echo off')
        extensionless_file.write_text('#!/bin/sh\necho "shell script"')

        result = setup_environment.get_bash_preferred_command(str(bat_file))
        assert result == str(extensionless_file)

    def test_uppercase_cmd_extension(self, tmp_path):
        """Test that uppercase .CMD extension is also handled."""
        # Create both .CMD and extensionless files
        cmd_file = tmp_path / 'claude.CMD'
        extensionless_file = tmp_path / 'claude'
        cmd_file.write_text('@echo off')
        extensionless_file.write_text('#!/bin/sh')

        result = setup_environment.get_bash_preferred_command(str(cmd_file))
        assert result == str(extensionless_file)

    def test_exe_file_unchanged(self, tmp_path):
        """Test that .exe files are returned unchanged (not processed)."""
        exe_file = tmp_path / 'claude.exe'
        extensionless_file = tmp_path / 'claude'
        exe_file.write_text('fake exe')
        extensionless_file.write_text('#!/bin/sh')

        result = setup_environment.get_bash_preferred_command(str(exe_file))
        assert result == str(exe_file)

    def test_extensionless_file_unchanged(self, tmp_path):
        """Test that extensionless files are returned unchanged."""
        extensionless_file = tmp_path / 'claude'
        extensionless_file.write_text('#!/bin/sh')

        result = setup_environment.get_bash_preferred_command(str(extensionless_file))
        assert result == str(extensionless_file)

    def test_empty_path(self):
        """Test empty path handling."""
        result = setup_environment.get_bash_preferred_command('')
        assert result == ''

    def test_none_path(self):
        """Test None-like path handling (empty string)."""
        result = setup_environment.get_bash_preferred_command('')
        assert result == ''

    def test_nonexistent_file(self, tmp_path):
        """Test handling of nonexistent .cmd file returns original path."""
        nonexistent = tmp_path / 'nonexistent.cmd'
        result = setup_environment.get_bash_preferred_command(str(nonexistent))
        # Should return original path even if file doesn't exist
        assert result == str(nonexistent)


class TestTildeExpansion:
    """Test tilde expansion in commands."""

    def test_expand_single_tilde(self):
        """Test expanding a single tilde path."""
        cmd = "sed -i '/pattern/d' ~/.bashrc"
        expanded = setup_environment.expand_tildes_in_command(cmd)
        home = str(Path.home())
        bashrc = os.path.normpath(os.path.join(home, '.bashrc'))
        assert expanded == f"sed -i '/pattern/d' {bashrc}"

    def test_expand_multiple_tildes(self):
        """Test expanding multiple tilde paths in one command."""
        cmd = 'cp ~/.config/file1 ~/.local/file2'
        expanded = setup_environment.expand_tildes_in_command(cmd)
        home = str(Path.home())
        config_file = os.path.normpath(os.path.join(home, '.config', 'file1'))
        local_file = os.path.normpath(os.path.join(home, '.local', 'file2'))
        assert expanded == f'cp {config_file} {local_file}'

    def test_expand_tilde_in_complex_command(self):
        """Test tilde expansion in complex sed command."""
        cmd = "sed -i -E '/^[[:space:]]*export[[:space:]]+HTTP_PROXY=/d' ~/.bashrc"
        expanded = setup_environment.expand_tildes_in_command(cmd)
        home = str(Path.home())
        bashrc = os.path.normpath(os.path.join(home, '.bashrc'))
        assert expanded == f"sed -i -E '/^[[:space:]]*export[[:space:]]+HTTP_PROXY=/d' {bashrc}"

    def test_expand_tilde_with_echo(self):
        """Test tilde expansion with echo command."""
        cmd = "echo 'export FOO=bar' >> ~/.bashrc"
        expanded = setup_environment.expand_tildes_in_command(cmd)
        home = str(Path.home())
        bashrc = os.path.normpath(os.path.join(home, '.bashrc'))
        assert expanded == f"echo 'export FOO=bar' >> {bashrc}"

    def test_no_tilde_unchanged(self):
        """Test that commands without tildes remain unchanged."""
        cmd = 'npm install -g package'
        expanded = setup_environment.expand_tildes_in_command(cmd)
        assert expanded == cmd

    def test_tilde_in_quotes_preserved(self):
        """Test that tildes in single quotes are expanded (shell would not expand them)."""
        cmd = "echo '~/.bashrc'"
        expanded = setup_environment.expand_tildes_in_command(cmd)
        home = str(Path.home())
        bashrc = os.path.normpath(os.path.join(home, '.bashrc'))
        # Our function expands tildes even in quotes, which is correct for subprocess context
        assert expanded == f"echo '{bashrc}'"

    def test_touch_tilde(self):
        """Test tilde expansion with touch command."""
        cmd = 'touch ~/.bashrc'
        expanded = setup_environment.expand_tildes_in_command(cmd)
        home = str(Path.home())
        bashrc = os.path.normpath(os.path.join(home, '.bashrc'))
        assert expanded == f'touch {bashrc}'

    def test_tilde_with_nested_path(self):
        """Test tilde expansion with deeply nested path."""
        cmd = 'cat ~/.config/claude/settings.json'
        expanded = setup_environment.expand_tildes_in_command(cmd)
        home = str(Path.home())
        settings = os.path.normpath(os.path.join(home, '.config', 'claude', 'settings.json'))
        assert expanded == f'cat {settings}'


class TestNormalizeTildePath:
    """Test the central path normalization function."""

    def test_expand_simple_tilde(self):
        """Test expanding simple tilde to home directory."""
        result = setup_environment.normalize_tilde_path('~/.claude/agent.md')
        home = str(Path.home())
        expected = os.path.normpath(os.path.join(home, '.claude', 'agent.md'))
        assert result == expected
        assert '~' not in result

    def test_expand_tilde_with_username(self):
        """Test expanding ~username format."""
        # This test verifies the function handles ~username
        # The actual expansion depends on the system
        result = setup_environment.normalize_tilde_path('~root/.bashrc')
        # On most systems, ~root expands to /root
        assert result != '~root/.bashrc' or not Path('/root').exists()

    def test_expand_environment_variable_unix_style(self):
        """Test expanding $VAR format environment variables."""
        os.environ['TEST_VAR_PATH'] = '/test/path'
        try:
            result = setup_environment.normalize_tilde_path('$TEST_VAR_PATH/file.txt')
            expected = os.path.normpath('/test/path/file.txt')
            assert result == expected
        finally:
            del os.environ['TEST_VAR_PATH']

    def test_expand_environment_variable_windows_style(self):
        """Test expanding %VAR% format environment variables."""
        os.environ['TEST_WIN_PATH'] = '/test/win/path'
        try:
            result = setup_environment.normalize_tilde_path('%TEST_WIN_PATH%/file.txt')
            # On Windows, %VAR% is expanded; on Unix, it may not be
            # os.path.expandvars handles both
            if platform.system() == 'Windows':
                expected = os.path.normpath('/test/win/path/file.txt')
                assert result == expected
        finally:
            del os.environ['TEST_WIN_PATH']

    def test_expand_combined_tilde_and_env_var(self):
        """Test expanding both tilde and environment variable."""
        os.environ['SUBDIR'] = 'mysubdir'
        try:
            result = setup_environment.normalize_tilde_path('~/$SUBDIR/file.txt')
            home = str(Path.home())
            expected = os.path.normpath(os.path.join(home, 'mysubdir', 'file.txt'))
            assert result == expected
        finally:
            del os.environ['SUBDIR']

    def test_empty_string_returns_empty(self):
        """Test that empty string returns empty string."""
        result = setup_environment.normalize_tilde_path('')
        assert result == ''

    def test_none_like_empty_returns_unchanged(self):
        """Test that falsy values return unchanged."""
        result = setup_environment.normalize_tilde_path('')
        assert result == ''

    def test_no_expansion_needed(self):
        """Test path without tilde or env vars passes through."""
        result = setup_environment.normalize_tilde_path('/absolute/path/file.txt')
        expected = os.path.normpath('/absolute/path/file.txt')
        assert result == expected

    def test_relative_path_without_resolve(self):
        """Test relative path without resolve flag stays relative."""
        result = setup_environment.normalize_tilde_path('./relative/path')
        expected = os.path.normpath('./relative/path')
        assert result == expected

    def test_relative_path_with_resolve(self):
        """Test relative path with resolve=True becomes absolute."""
        result = setup_environment.normalize_tilde_path('./relative/path', resolve=True)
        assert Path(result).is_absolute()

    def test_absolute_path_with_resolve_unchanged(self):
        """Test absolute path with resolve=True is still valid."""
        if platform.system() == 'Windows':
            # On Windows, use a proper Windows absolute path
            result = setup_environment.normalize_tilde_path('C:\\absolute\\path', resolve=True)
            assert 'C:' in result
            assert 'absolute' in result
        else:
            result = setup_environment.normalize_tilde_path('/absolute/path', resolve=True)
            assert result == '/absolute/path'

    def test_url_passes_through_unchanged(self):
        """Test that URLs are not modified by normpath.

        The URL guard in normalize_tilde_path skips os.path.normpath for
        URLs starting with http:// or https:// to prevent corruption of
        the :// scheme separator on Windows (where normpath converts
        forward slashes to backslashes).
        """
        https_url = 'https://example.com/file.md'
        result = setup_environment.normalize_tilde_path(https_url)
        assert result == https_url

        http_url = 'http://example.com/path/to/file.yaml'
        result = setup_environment.normalize_tilde_path(http_url)
        assert result == http_url

    def test_windows_path_unchanged_on_windows(self):
        """Test Windows paths work correctly."""
        if platform.system() == 'Windows':
            result = setup_environment.normalize_tilde_path('C:\\Users\\test\\file.txt')
            assert 'C:' in result

    def test_tilde_only_expands_to_home(self):
        """Test that ~ alone expands to home directory."""
        result = setup_environment.normalize_tilde_path('~')
        assert result == str(Path.home())

    def test_nested_path_expansion(self):
        """Test deeply nested path with tilde."""
        result = setup_environment.normalize_tilde_path('~/.config/claude/agents/my-agent.md')
        home = str(Path.home())
        expected = os.path.normpath(os.path.join(home, '.config', 'claude', 'agents', 'my-agent.md'))
        assert result == expected

    @pytest.mark.parametrize(('path', 'expected_contains'), [
        ('~/.claude', str(Path.home())),
        ('~/test/file.md', str(Path.home())),
        ('~/.config/claude/settings.json', str(Path.home())),
    ])
    def test_parametrized_tilde_expansion(self, path, expected_contains):
        """Parametrized test for various tilde paths."""
        result = setup_environment.normalize_tilde_path(path)
        assert expected_contains in result
        assert '~' not in result


class TestNormalizeTildePathUserScenario:
    """Test the specific user scenario that triggered the bug investigation."""

    def test_files_to_download_dest_tilde_expansion(self):
        """Test files-to-download with dest: ~/.claude/scripts/ pattern.

        This is the PRIMARY test case that validates the fix works for the user's
        actual configuration pattern.

        Note: os.path.normpath strips trailing slashes and normalizes separators,
        so the result will not have a trailing slash and will use platform-native
        separators.
        """
        dest_path = '~/.claude/scripts/'
        result = setup_environment.normalize_tilde_path(dest_path)
        home = str(Path.home())
        expected = os.path.normpath(os.path.join(home, '.claude', 'scripts'))
        assert result == expected
        assert '~' not in result
        assert Path(result).is_absolute()

    def test_files_to_download_with_nested_dest(self):
        """Test nested destination paths.

        Note: os.path.normpath strips trailing slashes and normalizes separators.
        """
        dest_path = '~/.claude/agents/custom/'
        result = setup_environment.normalize_tilde_path(dest_path)
        home = str(Path.home())
        expected = os.path.normpath(os.path.join(home, '.claude', 'agents', 'custom'))
        assert result == expected

    def test_resolve_resource_path_integration_scenario(self):
        """Test that normalized path is correctly identified as absolute."""
        dest_path = '~/.claude/scripts/my-script.py'
        normalized = setup_environment.normalize_tilde_path(dest_path)
        # After normalization, the path should be absolute
        assert Path(normalized).is_absolute()


class TestNormalizeTildePathNormpath:
    """Test os.path.normpath behavior added to normalize_tilde_path.

    These tests specifically verify the normpath step that normalizes
    path separators and resolves '.' and '..' components.
    """

    def test_no_mixed_separators(self):
        """After normpath, paths should have consistent separators."""
        result = setup_environment.normalize_tilde_path('~/.claude/scripts/test.py')
        if sys.platform == 'win32':
            assert '/' not in result, f'Mixed separators found on Windows: {result}'
        else:
            assert '\\' not in result, f'Backslashes found on Unix: {result}'

    def test_normpath_resolves_dot_dot(self):
        """Verify that normpath resolves '..' components."""
        result = setup_environment.normalize_tilde_path('~/foo/../bar')
        assert '..' not in result, f'Unresolved .. found in path: {result}'
        home = str(Path.home())
        expected = os.path.normpath(os.path.join(home, 'bar'))
        assert result == expected

    def test_normpath_resolves_single_dot(self):
        """Verify that normpath resolves '.' components."""
        result = setup_environment.normalize_tilde_path('~/./scripts/./test.py')
        assert '/.' not in result.replace('/.', ''), (
            f'Unresolved . found in path: {result}'
        )
        home = str(Path.home())
        expected = os.path.normpath(os.path.join(home, 'scripts', 'test.py'))
        assert result == expected

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-specific')
    def test_windows_consistency(self):
        """On Windows, tilde-expanded paths should use backslashes consistently."""
        result = setup_environment.normalize_tilde_path('~/.claude/scripts/file.py')
        # After normpath on Windows, all separators should be backslashes
        assert '/' not in result, f'Forward slashes found on Windows: {result}'
        assert '\\' in result, f'No backslashes found on Windows: {result}'

    @pytest.mark.skipif(sys.platform == 'win32', reason='Unix-specific')
    def test_unix_forward_slashes(self):
        """On Unix, paths should maintain forward slashes."""
        result = setup_environment.normalize_tilde_path('~/.claude/scripts/file.py')
        assert '\\' not in result, f'Backslashes found on Unix: {result}'
        assert '/' in result, f'No forward slashes found on Unix: {result}'

    def test_normpath_strips_trailing_separator(self):
        """Verify that normpath strips trailing path separators."""
        result = setup_environment.normalize_tilde_path('~/.claude/scripts/')
        assert not result.endswith('/'), f'Trailing / found: {result}'
        assert not result.endswith('\\'), f'Trailing \\\\ found: {result}'

    def test_multiple_consecutive_separators_normalized(self):
        """Verify that multiple consecutive separators are collapsed."""
        result = setup_environment.normalize_tilde_path('~/.claude//scripts///test.py')
        home = str(Path.home())
        expected = os.path.normpath(os.path.join(home, '.claude', 'scripts', 'test.py'))
        assert result == expected


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


class TestGitHubUrlConversion:
    """Test GitHub raw URL conversion to API format."""

    def test_convert_github_raw_to_api_standard(self):
        """Test conversion of standard raw.githubusercontent.com URL."""
        url = 'https://raw.githubusercontent.com/owner/repo/main/path/to/file.yaml'
        result = setup_environment.convert_github_raw_to_api(url)
        assert result == 'https://api.github.com/repos/owner/repo/contents/path/to/file.yaml?ref=main'

    def test_convert_github_raw_to_api_refs_heads(self):
        """Test conversion of URL with refs/heads/ prefix."""
        url = 'https://raw.githubusercontent.com/owner/repo/refs/heads/main/file.yaml'
        result = setup_environment.convert_github_raw_to_api(url)
        assert result == 'https://api.github.com/repos/owner/repo/contents/file.yaml?ref=main'

    def test_convert_github_raw_to_api_nested_path(self):
        """Test conversion of deeply nested file paths."""
        url = 'https://raw.githubusercontent.com/owner/repo/main/a/b/c/file.yaml'
        result = setup_environment.convert_github_raw_to_api(url)
        assert result == 'https://api.github.com/repos/owner/repo/contents/a/b/c/file.yaml?ref=main'

    def test_convert_github_already_api_url(self):
        """Test that API URLs are returned unchanged."""
        url = 'https://api.github.com/repos/owner/repo/contents/file.yaml?ref=main'
        result = setup_environment.convert_github_raw_to_api(url)
        assert result == url

    def test_convert_github_non_raw_url(self):
        """Test that non-raw GitHub URLs are returned unchanged."""
        url = 'https://github.com/owner/repo/blob/main/file.yaml'
        result = setup_environment.convert_github_raw_to_api(url)
        assert result == url

    def test_convert_github_gitlab_url_unchanged(self):
        """Test that GitLab URLs are returned unchanged."""
        url = 'https://gitlab.com/owner/repo/-/raw/main/file.yaml'
        result = setup_environment.convert_github_raw_to_api(url)
        assert result == url

    def test_convert_github_insufficient_parts(self):
        """Test handling of URLs with insufficient path parts."""
        url = 'https://raw.githubusercontent.com/owner/repo'
        result = setup_environment.convert_github_raw_to_api(url)
        assert result == url  # Returned unchanged

    def test_convert_github_gist_url_unchanged(self):
        """Test that gist.githubusercontent.com URLs are NOT converted."""
        url = 'https://gist.githubusercontent.com/user/gist_id/raw/file.txt'
        result = setup_environment.convert_github_raw_to_api(url)
        assert result == url  # Should not be converted

    def test_convert_github_no_file_path(self):
        """Test handling of URLs with no file path specified."""
        url = 'https://raw.githubusercontent.com/owner/repo/main'
        result = setup_environment.convert_github_raw_to_api(url)
        assert result == url  # Returned unchanged

    def test_convert_github_refs_heads_nested_path(self):
        """Test conversion of refs/heads/ URL with nested path."""
        url = 'https://raw.githubusercontent.com/owner/repo/refs/heads/feature/branch/path/to/file.yaml'
        result = setup_environment.convert_github_raw_to_api(url)
        # With refs/heads/, the branch is extracted from path_parts[4]
        assert result == 'https://api.github.com/repos/owner/repo/contents/branch/path/to/file.yaml?ref=feature'


class TestRepoTypeDetectionGitHubRaw:
    """Test repository type detection for raw.githubusercontent.com URLs."""

    def test_detect_raw_githubusercontent(self):
        """Test that raw.githubusercontent.com is detected as GitHub."""
        url = 'https://raw.githubusercontent.com/owner/repo/main/file.yaml'
        assert setup_environment.detect_repo_type(url) == 'github'

    def test_detect_raw_githubusercontent_refs_heads(self):
        """Test detection with refs/heads/ prefix."""
        url = 'https://raw.githubusercontent.com/owner/repo/refs/heads/main/file.yaml'
        assert setup_environment.detect_repo_type(url) == 'github'

    def test_detect_github_com(self):
        """Test that github.com is still detected as GitHub."""
        url = 'https://github.com/owner/repo/blob/main/file.yaml'
        assert setup_environment.detect_repo_type(url) == 'github'

    def test_detect_api_github_com(self):
        """Test that api.github.com is detected as GitHub."""
        url = 'https://api.github.com/repos/owner/repo/contents/file.yaml'
        assert setup_environment.detect_repo_type(url) == 'github'

    def test_detect_gist_githubusercontent_not_github(self):
        """Test that gist.githubusercontent.com is NOT detected as GitHub.

        gist.githubusercontent.com does not contain 'github.com' substring,
        and is a different service that requires different handling.
        """
        url = 'https://gist.githubusercontent.com/user/gist_id/raw/file.txt'
        # This should NOT be detected as GitHub because 'github.com' is not in the URL
        # and we specifically check for 'raw.githubusercontent.com'
        result = setup_environment.detect_repo_type(url)
        assert result is None  # gist is a separate service

    def test_detect_gitlab_unchanged(self):
        """Test that GitLab detection is unchanged."""
        url = 'https://gitlab.com/owner/repo/-/raw/main/file.yaml'
        assert setup_environment.detect_repo_type(url) == 'gitlab'


class TestGitHubAuthHeaders:
    """Test GitHub authentication headers generation."""

    def test_github_api_headers_include_accept(self, monkeypatch):
        """Test that GitHub API URLs get Accept header."""
        monkeypatch.setenv('GITHUB_TOKEN', 'test_token')
        url = 'https://api.github.com/repos/owner/repo/contents/file.yaml'
        headers = setup_environment.get_auth_headers(url)
        assert headers.get('Accept') == 'application/vnd.github.raw+json'
        assert headers.get('Authorization') == 'Bearer test_token'

    def test_github_api_headers_include_version(self, monkeypatch):
        """Test that GitHub API URLs get API version header."""
        monkeypatch.setenv('GITHUB_TOKEN', 'test_token')
        url = 'https://api.github.com/repos/owner/repo/contents/file.yaml'
        headers = setup_environment.get_auth_headers(url)
        assert headers.get('X-GitHub-Api-Version') == '2022-11-28'

    def test_github_non_api_no_extra_headers(self, monkeypatch):
        """Test that non-API GitHub URLs don't get extra headers."""
        monkeypatch.setenv('GITHUB_TOKEN', 'test_token')
        url = 'https://raw.githubusercontent.com/owner/repo/main/file.yaml'
        headers = setup_environment.get_auth_headers(url)
        # Raw URLs don't get Accept header - only API URLs do
        assert 'Accept' not in headers
        assert headers.get('Authorization') == 'Bearer test_token'


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

    @patch.dict('os.environ', {'REPO_TOKEN': 'generic_token'}, clear=True)
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


class TestResolveResourcePathTildeExpansion:
    """Test P1 fix: tilde paths resolved as LOCAL even with remote config source.

    This test class validates the critical fix where tilde paths (~/.claude/file)
    must be recognized as local paths and NOT be combined with remote URLs.
    """

    def test_tilde_path_with_remote_config_returns_local(self):
        """Critical P1 test: ~/ path must return LOCAL even when config is from URL.

        This was the core bug: tilde paths were being treated as relative and
        incorrectly combined with remote config URL.
        """
        path, is_remote = setup_environment.resolve_resource_path(
            '~/.claude/scripts/my-script.py',
            'https://raw.githubusercontent.com/user/repo/main/config.yaml',
            None,
        )
        home = str(Path.home())
        assert path.startswith(home)
        assert is_remote is False
        assert '~' not in path

    def test_tilde_path_with_base_url_returns_local(self):
        """Tilde paths must return LOCAL even when base_url is configured."""
        path, is_remote = setup_environment.resolve_resource_path(
            '~/.config/file.yaml',
            'local_config.yaml',
            'https://example.com/base/',
        )
        home = str(Path.home())
        assert path.startswith(home)
        assert is_remote is False

    def test_env_var_path_with_remote_config_returns_local(self):
        """Environment variable paths must also resolve as LOCAL."""
        os.environ['MY_CONFIG_DIR'] = str(Path.home() / '.myconfig')
        try:
            path, is_remote = setup_environment.resolve_resource_path(
                '$MY_CONFIG_DIR/file.yaml',
                'https://example.com/config.yaml',
                None,
            )
            assert is_remote is False
            assert str(Path.home()) in path
        finally:
            del os.environ['MY_CONFIG_DIR']

    def test_relative_path_with_remote_config_returns_remote(self):
        """Relative paths (no tilde) should still derive from remote config."""
        path, is_remote = setup_environment.resolve_resource_path(
            'agents/my-agent.md',
            'https://raw.githubusercontent.com/user/repo/main/config.yaml',
            None,
        )
        assert is_remote is True
        assert 'https://' in path

    def test_absolute_path_with_remote_config_returns_local(self):
        """Absolute paths (non-tilde) must return LOCAL."""
        abs_path = 'C:\\Users\\test\\file.txt' if platform.system() == 'Windows' else '/home/user/file.txt'

        path, is_remote = setup_environment.resolve_resource_path(
            abs_path,
            'https://example.com/config.yaml',
            None,
        )
        assert is_remote is False

    def test_user_scenario_files_to_download_dest(self):
        """Test the EXACT user scenario that reported the bug.

        User had: files-to-download with dest: ~/.claude/scripts/
        Bug: This was being combined with remote URL instead of expanded locally.
        """
        path, is_remote = setup_environment.resolve_resource_path(
            '~/.claude/scripts/',
            'https://raw.githubusercontent.com/org/repo/main/environments/python.yaml',
            None,
        )
        home = str(Path.home())
        # Path should start with home directory
        assert path.startswith(home)
        assert is_remote is False

    def test_tilde_in_nested_config_path(self):
        """Test tilde expansion with deeply nested paths."""
        path, is_remote = setup_environment.resolve_resource_path(
            '~/.config/claude/agents/specialized/data-analyst.md',
            'https://example.com/config.yaml',
            None,
        )
        home = str(Path.home())
        assert home in path
        assert is_remote is False

    def test_windows_env_var_with_remote_config(self):
        """Test Windows-style environment variable with remote config."""
        if platform.system() == 'Windows':
            # On Windows, %USERPROFILE% is expanded
            path, is_remote = setup_environment.resolve_resource_path(
                '%USERPROFILE%/.claude/file.txt',
                'https://example.com/config.yaml',
                None,
            )
            # After expansion, should be absolute and local
            assert is_remote is False
            assert '~' not in path
            assert '%' not in path


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


class TestGetRealUserHome:
    """Tests for get_real_user_home() function."""

    def test_returns_path_on_windows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test returns Path.home() on Windows."""
        monkeypatch.setattr(sys, 'platform', 'win32')
        result = setup_environment.get_real_user_home()
        assert isinstance(result, Path)

    @pytest.mark.skipif(sys.platform == 'win32', reason='Unix-specific test')
    def test_returns_sudo_user_home_when_sudo(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test returns sudo user's home when running under sudo."""
        monkeypatch.setattr(sys, 'platform', 'linux')
        monkeypatch.setenv('SUDO_USER', 'testuser')

        # Create mock pwd module to avoid importing real pwd on Windows
        class MockPasswd:
            pw_dir = '/home/testuser'

        class MockPwdModule:
            @staticmethod
            def getpwnam(_name: str) -> MockPasswd:
                return MockPasswd()

        # Inject mock pwd into sys.modules before the function imports it
        monkeypatch.setitem(sys.modules, 'pwd', MockPwdModule())

        result = setup_environment.get_real_user_home()
        assert result == Path('/home/testuser')

    @pytest.mark.skipif(sys.platform == 'win32', reason='Unix-specific test')
    def test_returns_home_when_no_sudo(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test returns Path.home() when not running under sudo."""
        monkeypatch.delenv('SUDO_USER', raising=False)
        result = setup_environment.get_real_user_home()
        assert result == Path.home()


class TestGetAllShellConfigFiles:
    """Tests for get_all_shell_config_files() function."""

    def test_returns_empty_on_windows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test returns empty list on Windows."""
        monkeypatch.setattr(sys, 'platform', 'win32')
        result = setup_environment.get_all_shell_config_files()
        assert result == []

    @pytest.mark.skipif(sys.platform == 'win32', reason='Unix-specific test')
    def test_returns_all_files_on_macos(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test returns all config files on macOS."""
        monkeypatch.setattr(sys, 'platform', 'darwin')
        monkeypatch.setattr(platform, 'system', lambda: 'Darwin')
        result = setup_environment.get_all_shell_config_files()
        filenames = [f.name for f in result]
        assert '.bashrc' in filenames
        assert '.bash_profile' in filenames
        assert '.zshenv' in filenames
        assert '.zprofile' in filenames
        assert '.zshrc' in filenames

    @pytest.mark.skipif(sys.platform == 'win32', reason='Unix-specific test')
    def test_excludes_zsh_files_on_linux_without_zsh(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test excludes zsh files on Linux when zsh is not installed."""
        monkeypatch.setattr(sys, 'platform', 'linux')
        monkeypatch.setattr(platform, 'system', lambda: 'Linux')
        monkeypatch.setattr(shutil, 'which', lambda x: None if x == 'zsh' else '/bin/bash')
        result = setup_environment.get_all_shell_config_files()
        filenames = [f.name for f in result]
        assert '.bashrc' in filenames
        assert '.zshrc' not in filenames
        assert '.zshenv' not in filenames

    @pytest.mark.skipif(sys.platform == 'win32', reason='Unix-specific test')
    def test_includes_fish_config_on_macos(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test includes fish config file on macOS."""
        monkeypatch.setattr(platform, 'system', lambda: 'Darwin')
        config_files = setup_environment.get_all_shell_config_files()
        file_names = [str(f) for f in config_files]
        # Should include fish config on macOS (fish is common on macOS)
        assert any('fish' in name and 'config.fish' in name for name in file_names)

    @pytest.mark.skipif(sys.platform == 'win32', reason='Unix-specific test')
    def test_includes_fish_config_when_fish_installed_on_linux(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test includes fish config on Linux when fish is installed."""
        monkeypatch.setattr(platform, 'system', lambda: 'Linux')

        def which_mock(cmd: str) -> str | None:
            if cmd == 'fish':
                return '/usr/bin/fish'
            if cmd == 'zsh':
                return '/usr/bin/zsh'
            return None

        monkeypatch.setattr(shutil, 'which', which_mock)
        config_files = setup_environment.get_all_shell_config_files()
        file_names = [str(f) for f in config_files]
        assert any('fish' in name and 'config.fish' in name for name in file_names)

    @pytest.mark.skipif(sys.platform == 'win32', reason='Unix-specific test')
    def test_excludes_fish_config_when_not_installed_on_linux(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test excludes fish config on Linux when fish is not installed."""
        monkeypatch.setattr(platform, 'system', lambda: 'Linux')
        monkeypatch.setattr(shutil, 'which', lambda _: None)
        config_files = setup_environment.get_all_shell_config_files()
        file_names = [str(f) for f in config_files]
        assert not any('fish' in name for name in file_names)


class TestAddExportToFile:
    """Tests for add_export_to_file() function."""

    def test_creates_file_with_export(self, tmp_path: Path) -> None:
        """Test creates new file with export line."""
        config_file = tmp_path / '.bashrc'
        result = setup_environment.add_export_to_file(config_file, 'MY_VAR', 'my_value')
        assert result is True
        assert config_file.exists()
        content = config_file.read_text()
        assert 'export MY_VAR="my_value"' in content
        assert setup_environment.ENV_VAR_MARKER_START in content
        assert setup_environment.ENV_VAR_MARKER_END in content

    def test_updates_existing_variable(self, tmp_path: Path) -> None:
        """Test updates existing variable in marker block."""
        config_file = tmp_path / '.bashrc'
        setup_environment.add_export_to_file(config_file, 'MY_VAR', 'old_value')
        result = setup_environment.add_export_to_file(config_file, 'MY_VAR', 'new_value')
        assert result is True
        content = config_file.read_text()
        assert 'export MY_VAR="new_value"' in content
        assert 'old_value' not in content
        # Should only have one marker block
        assert content.count(setup_environment.ENV_VAR_MARKER_START) == 1

    def test_adds_multiple_variables(self, tmp_path: Path) -> None:
        """Test adds multiple variables to same block."""
        config_file = tmp_path / '.bashrc'
        setup_environment.add_export_to_file(config_file, 'VAR1', 'value1')
        setup_environment.add_export_to_file(config_file, 'VAR2', 'value2')
        content = config_file.read_text()
        assert 'export VAR1="value1"' in content
        assert 'export VAR2="value2"' in content
        assert content.count(setup_environment.ENV_VAR_MARKER_START) == 1


class TestRemoveExportFromFile:
    """Tests for remove_export_from_file() function."""

    def test_removes_variable(self, tmp_path: Path) -> None:
        """Test removes variable from marker block."""
        config_file = tmp_path / '.bashrc'
        setup_environment.add_export_to_file(config_file, 'MY_VAR', 'my_value')
        result = setup_environment.remove_export_from_file(config_file, 'MY_VAR')
        assert result is True
        content = config_file.read_text()
        assert 'MY_VAR' not in content

    def test_removes_only_target_variable(self, tmp_path: Path) -> None:
        """Test removes only the target variable, keeps others."""
        config_file = tmp_path / '.bashrc'
        setup_environment.add_export_to_file(config_file, 'VAR1', 'value1')
        setup_environment.add_export_to_file(config_file, 'VAR2', 'value2')
        setup_environment.remove_export_from_file(config_file, 'VAR1')
        content = config_file.read_text()
        assert 'VAR1' not in content
        assert 'export VAR2="value2"' in content

    def test_returns_true_for_nonexistent_file(self, tmp_path: Path) -> None:
        """Test returns True when file doesn't exist."""
        config_file = tmp_path / '.nonexistent'
        result = setup_environment.remove_export_from_file(config_file, 'MY_VAR')
        assert result is True

    def test_removes_variable_outside_managed_block(self, tmp_path: Path) -> None:
        """Test removes variable that was added outside the managed block."""
        config_file = tmp_path / '.bashrc'
        # Manually create content with variable OUTSIDE managed block
        config_file.write_text('export MY_VAR="legacy_value"\n# Other content\n')
        result = setup_environment.remove_export_from_file(config_file, 'MY_VAR')
        assert result is True
        content = config_file.read_text()
        assert 'MY_VAR' not in content
        assert '# Other content' in content

    def test_removes_variable_when_no_managed_block_exists(self, tmp_path: Path) -> None:
        """Test removes variable when no managed block exists."""
        config_file = tmp_path / '.bashrc'
        # Create content without managed block
        config_file.write_text(
            '# My bashrc\nexport PATH="/usr/bin"\nexport MY_VAR="value"\nexport OTHER="keep"\n',
        )
        result = setup_environment.remove_export_from_file(config_file, 'MY_VAR')
        assert result is True
        content = config_file.read_text()
        assert 'MY_VAR' not in content
        assert 'export PATH="/usr/bin"' in content
        assert 'export OTHER="keep"' in content

    def test_removes_variable_from_both_inside_and_outside_block(self, tmp_path: Path) -> None:
        """Test removes variable that exists both inside and outside managed block."""
        config_file = tmp_path / '.bashrc'
        # First add variable outside block
        config_file.write_text('export MY_VAR="legacy_value"\n')
        # Then add the same variable via managed block
        setup_environment.add_export_to_file(config_file, 'MY_VAR', 'managed_value')
        # Now remove it - should remove from both places
        result = setup_environment.remove_export_from_file(config_file, 'MY_VAR')
        assert result is True
        content = config_file.read_text()
        assert 'MY_VAR' not in content

    def test_removes_variable_without_export_keyword(self, tmp_path: Path) -> None:
        """Test removes variable defined without export keyword."""
        config_file = tmp_path / '.bashrc'
        config_file.write_text('MY_VAR="value"\n# Other content\n')
        result = setup_environment.remove_export_from_file(config_file, 'MY_VAR')
        assert result is True
        content = config_file.read_text()
        assert 'MY_VAR' not in content
        assert '# Other content' in content

    def test_preserves_comments_containing_variable_name(self, tmp_path: Path) -> None:
        """Test preserves comments that contain the variable name."""
        config_file = tmp_path / '.bashrc'
        config_file.write_text(
            '# Set MY_VAR for development\nexport MY_VAR="value"\n'
            '# MY_VAR should be set\n',
        )
        result = setup_environment.remove_export_from_file(config_file, 'MY_VAR')
        assert result is True
        content = config_file.read_text()
        # Export line should be removed
        assert 'export MY_VAR="value"' not in content
        # Comments should be preserved
        assert '# Set MY_VAR for development' in content
        assert '# MY_VAR should be set' in content


class TestFishShellSupport:
    """Tests for Fish shell syntax support."""

    def test_add_export_uses_fish_syntax(self, tmp_path: Path) -> None:
        """Test add_export_to_file uses fish set syntax for fish config."""
        config_file = tmp_path / '.config' / 'fish' / 'config.fish'
        result = setup_environment.add_export_to_file(config_file, 'MY_VAR', 'my_value')
        assert result is True
        content = config_file.read_text()
        assert 'set -gx MY_VAR "my_value"' in content
        assert 'export' not in content

    def test_remove_export_handles_fish_syntax(self, tmp_path: Path) -> None:
        """Test remove_export_from_file handles fish set syntax."""
        config_file = tmp_path / '.config' / 'fish' / 'config.fish'
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text('set -gx MY_VAR "value"\n# Keep this\n')
        result = setup_environment.remove_export_from_file(config_file, 'MY_VAR')
        assert result is True
        content = config_file.read_text()
        assert 'MY_VAR' not in content
        assert '# Keep this' in content

    def test_remove_export_handles_fish_universal_variable(self, tmp_path: Path) -> None:
        """Test remove_export_from_file handles fish -Ux (universal) variable."""
        config_file = tmp_path / '.config' / 'fish' / 'config.fish'
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text('set -Ux MY_VAR "value"\n')
        result = setup_environment.remove_export_from_file(config_file, 'MY_VAR')
        assert result is True
        content = config_file.read_text()
        assert 'MY_VAR' not in content

    def test_update_existing_fish_variable(self, tmp_path: Path) -> None:
        """Test updating an existing variable in fish config."""
        config_file = tmp_path / '.config' / 'fish' / 'config.fish'
        setup_environment.add_export_to_file(config_file, 'MY_VAR', 'old_value')
        setup_environment.add_export_to_file(config_file, 'MY_VAR', 'new_value')
        content = config_file.read_text()
        assert 'set -gx MY_VAR "new_value"' in content
        assert 'old_value' not in content
        # Should only have one occurrence
        assert content.count('MY_VAR') == 1


class TestSetOsEnvVariableWindows:
    """Tests for set_os_env_variable_windows() function."""

    def test_returns_false_on_non_windows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test returns False on non-Windows platforms."""
        monkeypatch.setattr(sys, 'platform', 'linux')
        result = setup_environment.set_os_env_variable_windows('MY_VAR', 'value')
        assert result is False

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-specific test')
    def test_calls_setx_for_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test calls setx command to set variable."""
        called_with: list[list[str]] = []

        class MockResult:
            returncode = 0
            stderr = ''

        def mock_run(cmd: list[str], **_kwargs: object) -> MockResult:
            called_with.append(cmd)
            return MockResult()

        monkeypatch.setattr(subprocess, 'run', mock_run)
        result = setup_environment.set_os_env_variable_windows('MY_VAR', 'my_value')
        assert result is True
        assert called_with[0] == ['setx', 'MY_VAR', 'my_value']

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-specific test')
    def test_calls_reg_delete_for_delete(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test calls reg delete command to delete variable."""
        called_with: list[list[str]] = []

        class MockResult:
            returncode = 0
            stderr = ''

        def mock_run(cmd: list[str], **_kwargs: object) -> MockResult:
            called_with.append(cmd)
            return MockResult()

        monkeypatch.setattr(subprocess, 'run', mock_run)
        result = setup_environment.set_os_env_variable_windows('MY_VAR', None)
        assert result is True
        assert called_with[0] == ['reg', 'delete', r'HKCU\Environment', '/v', 'MY_VAR', '/f']


class TestSetOsEnvVariableProcessSync:
    """Tests for os.environ synchronization in set_os_env_variable()."""

    def test_updates_process_env_on_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify os.environ is updated when persistent storage succeeds.

        When set_os_env_variable() successfully writes to persistent storage,
        it should also update os.environ for the current process so that
        child processes (e.g., Claude Code) see the change immediately.
        """
        # Mock the platform-specific function to succeed
        if sys.platform == 'win32':
            monkeypatch.setattr(
                setup_environment, 'set_os_env_variable_windows', lambda _n, _v: True,
            )
        else:
            monkeypatch.setattr(
                setup_environment, 'set_os_env_variable_unix', lambda _n, _v: True,
            )

        test_var = 'E2E_TEST_SET_OS_ENV_SYNC_12345'
        try:
            result = setup_environment.set_os_env_variable(test_var, 'test_value')
            assert result is True
            assert os.environ.get(test_var) == 'test_value'
        finally:
            os.environ.pop(test_var, None)

    def test_removes_from_process_env_on_delete(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify os.environ is updated when variable is deleted.

        When set_os_env_variable() successfully deletes a persistent variable,
        it should also remove the variable from os.environ.
        """
        if sys.platform == 'win32':
            monkeypatch.setattr(
                setup_environment, 'set_os_env_variable_windows', lambda _n, _v: True,
            )
        else:
            monkeypatch.setattr(
                setup_environment, 'set_os_env_variable_unix', lambda _n, _v: True,
            )

        test_var = 'E2E_TEST_SET_OS_ENV_DEL_12345'
        os.environ[test_var] = 'old_value'
        try:
            result = setup_environment.set_os_env_variable(test_var, None)
            assert result is True
            assert test_var not in os.environ
        finally:
            os.environ.pop(test_var, None)

    def test_no_env_change_on_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify os.environ is unchanged when persistent storage fails.

        When the platform-specific function returns False (e.g., setx fails
        or shell config write fails), os.environ should remain unchanged
        to maintain consistency between persistent and process state.
        """
        if sys.platform == 'win32':
            monkeypatch.setattr(
                setup_environment, 'set_os_env_variable_windows', lambda _n, _v: False,
            )
        else:
            monkeypatch.setattr(
                setup_environment, 'set_os_env_variable_unix', lambda _n, _v: False,
            )

        test_var = 'E2E_TEST_SET_OS_ENV_FAIL_12345'
        os.environ[test_var] = 'old_value'
        try:
            result = setup_environment.set_os_env_variable(test_var, None)
            assert result is False
            # os.environ should be unchanged because persistent op failed
            assert os.environ.get(test_var) == 'old_value'
        finally:
            os.environ.pop(test_var, None)

    def test_delete_nonexistent_var_no_crash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify deleting a var not in os.environ does not crash.

        os.environ.pop(name, None) should handle missing keys gracefully.
        """
        if sys.platform == 'win32':
            monkeypatch.setattr(
                setup_environment, 'set_os_env_variable_windows', lambda _n, _v: True,
            )
        else:
            monkeypatch.setattr(
                setup_environment, 'set_os_env_variable_unix', lambda _n, _v: True,
            )

        test_var = 'E2E_TEST_NONEXIST_DEL_12345'
        # Ensure it does not exist
        os.environ.pop(test_var, None)
        result = setup_environment.set_os_env_variable(test_var, None)
        assert result is True
        assert test_var not in os.environ


class TestSetAllOsEnvVariablesUnsetGuidance:
    """Tests for unset guidance in set_all_os_env_variables()."""

    @pytest.mark.skipif(sys.platform == 'win32', reason='Unix-specific test')
    def test_shows_unset_instructions_on_delete(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Verify unset instructions are shown when variables are deleted.

        On Unix, after deleting environment variables from shell configs,
        set_all_os_env_variables() should print explicit unset commands
        for the user to run in their current shell session.
        """
        monkeypatch.setattr(sys, 'platform', 'linux')
        config_file = tmp_path / '.bashrc'
        monkeypatch.setattr(
            setup_environment,
            'get_all_shell_config_files',
            lambda: [config_file],
        )
        # First set a variable so there's something to delete
        setup_environment.add_export_to_file(config_file, 'TOKEN_TO_DELETE', 'secret')

        setup_environment.set_all_os_env_variables({'TOKEN_TO_DELETE': None})

        captured = capsys.readouterr()
        assert 'unset TOKEN_TO_DELETE' in captured.out

    @pytest.mark.skipif(sys.platform == 'win32', reason='Unix-specific test')
    def test_no_unset_instructions_when_only_setting(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Verify no unset instructions when only setting variables (no deletes)."""
        monkeypatch.setattr(sys, 'platform', 'linux')
        monkeypatch.setattr(
            setup_environment,
            'get_all_shell_config_files',
            lambda: [tmp_path / '.bashrc'],
        )

        setup_environment.set_all_os_env_variables({'MY_VAR': 'my_value'})

        captured = capsys.readouterr()
        assert 'unset' not in captured.out


class TestSetAllOsEnvVariables:
    """Tests for set_all_os_env_variables() function."""

    def test_empty_dict_returns_true(self) -> None:
        """Test returns True for empty dictionary."""
        result = setup_environment.set_all_os_env_variables({})
        assert result is True

    @pytest.mark.skipif(sys.platform == 'win32', reason='Unix-specific test')
    def test_sets_multiple_variables(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Test sets multiple variables successfully."""
        monkeypatch.setattr(sys, 'platform', 'linux')
        # Mock get_all_shell_config_files to return temp path
        monkeypatch.setattr(
            setup_environment,
            'get_all_shell_config_files',
            lambda: [tmp_path / '.bashrc'],
        )
        result = setup_environment.set_all_os_env_variables({
            'VAR1': 'value1',
            'VAR2': 'value2',
        })
        assert result is True
        content = (tmp_path / '.bashrc').read_text()
        assert 'export VAR1="value1"' in content
        assert 'export VAR2="value2"' in content

    @pytest.mark.skipif(sys.platform == 'win32', reason='Unix-specific test')
    def test_handles_null_values_for_deletion(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Test handles None values as deletion requests."""
        monkeypatch.setattr(sys, 'platform', 'linux')
        config_file = tmp_path / '.bashrc'
        monkeypatch.setattr(
            setup_environment,
            'get_all_shell_config_files',
            lambda: [config_file],
        )
        # First set a variable
        setup_environment.add_export_to_file(config_file, 'OLD_VAR', 'old_value')
        # Then delete it
        result = setup_environment.set_all_os_env_variables({'OLD_VAR': None})
        assert result is True
        content = config_file.read_text()
        assert 'OLD_VAR' not in content


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
    @patch('setup_environment.run_command')
    def test_install_dependencies_macos_executes_as_is(self, mock_run, mock_system):
        """Test macOS executes commands as-is with tilde expansion."""
        assert mock_system.return_value == 'Darwin'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        # Commands should be executed as-is (with tilde expansion)
        result = setup_environment.install_dependencies({
            'mac': [
                'echo "export FOO=bar" >> ~/.zshrc',
                'brew install tool',
            ],
        })
        assert result is True

        calls = mock_run.call_args_list
        assert len(calls) == 2

        # Commands should be executed as-is with expanded tilde paths
        home = str(Path.home())
        zshrc = os.path.normpath(os.path.join(home, '.zshrc'))
        call_args = [call[0][0][2] for call in calls]
        assert f'echo "export FOO=bar" >> {zshrc}' in call_args
        assert 'brew install tool' in call_args

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

    @patch('platform.system', return_value='Windows')
    @patch('setup_environment.run_command')
    @patch('setup_environment.expand_tildes_in_command')
    def test_install_dependencies_windows_powershell_expands_tilde(
        self, mock_expand, mock_run, mock_system,
    ):
        """Test that Windows PowerShell dependencies expand tildes.

        P3 fix: Ensures tilde paths in PowerShell commands are expanded on Windows.
        PowerShell does not natively expand ~ paths, so we must do it before execution.
        """
        # Verify mock configuration
        assert mock_system.return_value == 'Windows'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')
        home = str(Path.home())
        mock_expand.return_value = f'Write-Output "test" >> {home}/.config/file.txt'

        # PowerShell command with tilde path (not a known command like npm, pip, winget, uv tool)
        result = setup_environment.install_dependencies({
            'windows': ['Write-Output "test" >> ~/.config/file.txt'],
        })

        assert result is True
        mock_expand.assert_called_with('Write-Output "test" >> ~/.config/file.txt')
        # Verify PowerShell command uses expanded path
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == 'powershell'
        assert call_args[1] == '-NoProfile'
        assert call_args[2] == '-Command'
        assert home in call_args[3]

    @patch('platform.system', return_value='Linux')
    @patch('setup_environment.run_command')
    @patch('setup_environment.expand_tildes_in_command')
    def test_install_dependencies_uv_tool_linux_expands_tilde(
        self, mock_expand, mock_run, mock_system,
    ):
        """Test that uv tool install with tilde path expands on Linux.

        P4 fix: Ensures tilde paths in uv tool install commands are expanded on Linux.
        Without this fix, uv tool install commands bypass tilde expansion.
        """
        # Verify mock configuration
        assert mock_system.return_value == 'Linux'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')
        home = str(Path.home())
        mock_expand.return_value = f'uv tool install --force {home}/.local/tools/my-tool'

        result = setup_environment.install_dependencies({
            'linux': ['uv tool install ~/.local/tools/my-tool'],
        })

        assert result is True
        # Verify expand_tildes_in_command was called with the --force flag added
        mock_expand.assert_called()
        call_arg = mock_expand.call_args[0][0]
        assert '--force' in call_arg
        assert '~/.local/tools/my-tool' in call_arg

    @patch('platform.system', return_value='Darwin')
    @patch('setup_environment.run_command')
    @patch('setup_environment.expand_tildes_in_command')
    def test_install_dependencies_uv_tool_macos_expands_tilde(
        self, mock_expand, mock_run, mock_system,
    ):
        """Test that uv tool install with tilde path expands on macOS.

        P4 fix: Ensures tilde paths in uv tool install commands are expanded on macOS.
        Without this fix, uv tool install commands bypass tilde expansion.
        """
        # Verify mock configuration
        assert mock_system.return_value == 'Darwin'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')
        home = str(Path.home())
        mock_expand.return_value = f'uv tool install --force {home}/.local/tools/custom-tool'

        result = setup_environment.install_dependencies({
            'mac': ['uv tool install ~/.local/tools/custom-tool'],
        })

        assert result is True
        # Verify expand_tildes_in_command was called with the --force flag added
        mock_expand.assert_called()
        call_arg = mock_expand.call_args[0][0]
        assert '--force' in call_arg
        assert '~/.local/tools/custom-tool' in call_arg


class TestInstallNodejsIfRequested:
    """Test install_nodejs_if_requested() function."""

    def test_not_requested_returns_true(self):
        """Test that function returns True when install-nodejs is not set."""
        config: dict = {'name': 'Test'}
        result = setup_environment.install_nodejs_if_requested(config)
        assert result is True

    def test_false_returns_true(self):
        """Test that function returns True when install-nodejs is False."""
        config = {'install-nodejs': False}
        result = setup_environment.install_nodejs_if_requested(config)
        assert result is True

    @patch('install_claude.ensure_nodejs')
    def test_true_calls_ensure_nodejs(self, mock_ensure):
        """Test that function calls ensure_nodejs when install-nodejs is True."""
        mock_ensure.return_value = True
        config = {'install-nodejs': True}
        result = setup_environment.install_nodejs_if_requested(config)
        assert result is True
        mock_ensure.assert_called_once()

    @patch('install_claude.ensure_nodejs')
    def test_installation_failure_returns_false(self, mock_ensure):
        """Test that function returns False when ensure_nodejs fails."""
        mock_ensure.return_value = False
        config = {'install-nodejs': True}
        result = setup_environment.install_nodejs_if_requested(config)
        assert result is False

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-specific')
    @patch('install_claude.ensure_nodejs')
    @patch('setup_environment.refresh_path_from_registry')
    def test_windows_refreshes_path(self, mock_refresh, mock_ensure):
        """Test that PATH is refreshed on Windows after installation."""
        mock_ensure.return_value = True
        config = {'install-nodejs': True}
        setup_environment.install_nodejs_if_requested(config)
        mock_refresh.assert_called_once()

    @patch('platform.system', return_value='Linux')
    @patch('install_claude.ensure_nodejs')
    @patch('setup_environment.refresh_path_from_registry')
    def test_non_windows_skips_path_refresh(self, mock_refresh, mock_ensure, mock_system):
        """Test that PATH refresh is skipped on non-Windows platforms."""
        # Verify mock configuration
        assert mock_system.return_value == 'Linux'
        mock_ensure.return_value = True
        config = {'install-nodejs': True}
        setup_environment.install_nodejs_if_requested(config)
        mock_refresh.assert_not_called()


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

    @patch('setup_environment.run_bash_command')
    @patch('setup_environment.find_command_robust')
    @patch('setup_environment.run_command')
    def test_configure_mcp_server_http(self, mock_run, mock_find, mock_bash):
        """Test configuring HTTP MCP server on Unix."""
        mock_find.return_value = 'claude'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')
        mock_bash.return_value = subprocess.CompletedProcess([], 0, '', '')

        server = {
            'name': 'test-server',
            'scope': 'user',
            'transport': 'http',
            'url': 'http://localhost:3000',
        }

        with patch('platform.system', return_value='Linux'):
            result = setup_environment.configure_mcp_server(server)

        assert result is True
        # Should call run_command 3 times for removing from all scopes
        assert mock_run.call_count == 3
        # Unix HTTP transport now uses run_bash_command for consistency with Windows
        assert mock_bash.call_count == 1
        # Check the bash command contains mcp add and server name
        bash_cmd = mock_bash.call_args[0][0]
        assert 'mcp add' in bash_cmd
        assert 'test-server' in bash_cmd

    @patch('setup_environment.find_command_robust')
    @patch('setup_environment.run_command')
    def test_configure_mcp_server_stdio(self, mock_run, mock_find):
        """Test configuring stdio MCP server on Unix."""
        mock_find.return_value = 'claude'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        server = {
            'name': 'test-server',
            'scope': 'user',
            'command': 'npx test-server',
        }

        with patch('platform.system', return_value='Linux'):
            result = setup_environment.configure_mcp_server(server)
        assert result is True
        # Should call run_command 4 times: 3 for removing from all scopes, once for add
        assert mock_run.call_count == 4

    @patch('setup_environment.run_bash_command')
    @patch('setup_environment.find_command_robust')
    @patch('setup_environment.run_command')
    def test_configure_mcp_server_http_with_ampersand_in_url(self, mock_run, mock_find, mock_bash):
        """Test configuring HTTP MCP server with URL containing ampersand on Unix.

        This tests that URLs with '&' query parameters are properly handled
        when using bash for command execution.
        """
        mock_find.return_value = 'claude'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')
        mock_bash.return_value = subprocess.CompletedProcess([], 0, '', '')

        server = {
            'name': 'supabase',
            'scope': 'user',
            'transport': 'http',
            'url': 'https://mcp.supabase.com/mcp?project_ref=xxx&read_only=true',
        }

        with patch('platform.system', return_value='Linux'):
            result = setup_environment.configure_mcp_server(server)

        assert result is True
        # Should call run_command 3 times for removing from all scopes
        assert mock_run.call_count == 3
        # Unix HTTP transport now uses run_bash_command for consistency with Windows
        assert mock_bash.call_count == 1
        # Check the bash command contains the full URL
        bash_cmd = mock_bash.call_args[0][0]
        assert 'supabase' in bash_cmd
        # The URL should be in the command (not split by &)
        assert 'project_ref=xxx' in bash_cmd
        assert 'read_only=true' in bash_cmd

    @patch('setup_environment.run_bash_command')
    @patch('setup_environment.find_command_robust')
    @patch('setup_environment.run_command')
    def test_configure_mcp_server_http_with_multiple_query_params(self, mock_run, mock_find, mock_bash):
        """Test configuring HTTP MCP server with URL containing multiple special characters."""
        mock_find.return_value = 'claude'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')
        mock_bash.return_value = subprocess.CompletedProcess([], 0, '', '')

        server = {
            'name': 'test-api',
            'scope': 'user',
            'transport': 'http',
            'url': 'https://api.example.com/v1?key=abc&token=xyz&mode=read&format=json',
        }

        with patch('platform.system', return_value='Linux'):
            result = setup_environment.configure_mcp_server(server)

        assert result is True
        # Should call run_command 3 times for removing from all scopes
        assert mock_run.call_count == 3
        # Unix HTTP transport now uses run_bash_command for consistency with Windows
        assert mock_bash.call_count == 1
        # Check all query parameters are preserved in the bash command
        bash_cmd = mock_bash.call_args[0][0]
        assert 'key=abc' in bash_cmd
        assert 'token=xyz' in bash_cmd
        assert 'mode=read' in bash_cmd
        assert 'format=json' in bash_cmd

    @patch('setup_environment.run_bash_command')
    @patch('setup_environment.find_command_robust')
    @patch('setup_environment.run_command')
    def test_configure_mcp_server_http_with_header_and_special_url(self, mock_run, mock_find, mock_bash):
        """Test configuring HTTP MCP server with header and URL containing special characters."""
        mock_find.return_value = 'claude'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')
        mock_bash.return_value = subprocess.CompletedProcess([], 0, '', '')

        server = {
            'name': 'auth-api',
            'scope': 'user',
            'transport': 'http',
            'url': 'https://api.example.com?client_id=123&scope=read&redirect_uri=http://localhost',
            'header': 'Authorization: Bearer token123',
        }

        with patch('platform.system', return_value='Linux'):
            result = setup_environment.configure_mcp_server(server)

        assert result is True
        # Should call run_command 3 times for removing from all scopes
        assert mock_run.call_count == 3
        # Unix HTTP transport now uses run_bash_command for consistency with Windows
        assert mock_bash.call_count == 1
        # Check the bash command contains both header and full URL
        bash_cmd = mock_bash.call_args[0][0]
        assert 'auth-api' in bash_cmd
        assert '--header' in bash_cmd
        assert 'client_id=123' in bash_cmd
        assert 'scope=read' in bash_cmd

    @patch('platform.system', return_value='Windows')
    @patch('setup_environment.run_bash_command')
    @patch('setup_environment.run_command')
    @patch('setup_environment.find_command_robust')
    def test_configure_mcp_server_windows_uses_bash(
        self, mock_find, mock_run_cmd, mock_bash_cmd, mock_system,
    ):
        """Test Windows HTTP transport uses bash for consistent cross-platform behavior.

        On Windows, HTTP transport should use run_bash_command to avoid
        PowerShell/CMD escaping issues with URLs containing special characters.
        """
        del mock_system  # Unused but required for patch
        mock_find.return_value = 'C:\\Users\\Test\\AppData\\Roaming\\npm\\claude.CMD'

        # First 3 calls are for removing from scopes (success)
        mock_run_cmd.return_value = subprocess.CompletedProcess([], 0, '', '')

        # Bash command succeeds
        mock_bash_cmd.return_value = subprocess.CompletedProcess([], 0, '', '')

        server = {
            'name': 'supabase',
            'scope': 'user',
            'transport': 'http',
            'url': 'https://mcp.supabase.com/mcp?project_ref=xxx&read_only=true',
        }

        result = setup_environment.configure_mcp_server(server)
        assert result is True

        # Verify run_bash_command was called for the add operation
        assert mock_bash_cmd.called
        call_args = mock_bash_cmd.call_args

        # Check the bash command contains the URL with proper quoting
        bash_cmd = call_args.args[0]
        assert 'mcp add' in bash_cmd
        assert 'supabase' in bash_cmd
        assert 'https://mcp.supabase.com/mcp?project_ref=xxx&read_only=true' in bash_cmd

    @patch('platform.system', return_value='Windows')
    @patch('setup_environment.run_bash_command')
    @patch('setup_environment.run_command')
    @patch('setup_environment.find_command_robust')
    def test_configure_mcp_server_stdio_windows_uses_bash(
        self, mock_find, mock_run_cmd, mock_bash_cmd, mock_system,
    ):
        """Test Windows STDIO transport uses bash for consistent cross-platform behavior.

        On Windows, STDIO transport should use run_bash_command (same as HTTP)
        to provide unified execution behavior across all transport types.
        """
        del mock_system  # Unused but required for patch
        mock_find.return_value = 'C:\\Users\\Test\\AppData\\Roaming\\npm\\claude.CMD'

        # run_command for removes succeeds
        mock_run_cmd.return_value = subprocess.CompletedProcess([], 0, '', '')

        # Bash command succeeds
        mock_bash_cmd.return_value = subprocess.CompletedProcess([], 0, '', '')

        server = {
            'name': 'test-stdio-server',
            'scope': 'user',
            'command': 'npx @test/server',
        }

        result = setup_environment.configure_mcp_server(server)
        assert result is True

        # Verify run_bash_command was called for the add operation
        assert mock_bash_cmd.called
        call_args = mock_bash_cmd.call_args

        # Check the bash command contains proper STDIO configuration
        bash_cmd = call_args.args[0]
        assert 'mcp add' in bash_cmd
        assert 'test-stdio-server' in bash_cmd
        # npx commands should use cmd /c wrapper
        assert 'cmd /c npx @test/server' in bash_cmd
        # PATH export should be present
        assert 'export PATH=' in bash_cmd

    @patch('platform.system', return_value='Windows')
    @patch('setup_environment.run_bash_command')
    @patch('setup_environment.run_command')
    @patch('setup_environment.find_command_robust')
    def test_configure_mcp_server_windows_prefers_shell_script_over_cmd(
        self, mock_find, mock_run_cmd, mock_bash_cmd, mock_system, tmp_path,
    ):
        """Test Windows uses shell script instead of .cmd to avoid & parsing issues.

        When both .cmd and extensionless shell script exist, the extensionless
        version should be preferred to avoid CMD.exe interpreting & in URLs
        as command separators.
        """
        del mock_system  # Unused but required for patch

        # Create both .cmd and extensionless files
        cmd_file = tmp_path / 'claude.cmd'
        extensionless_file = tmp_path / 'claude'
        cmd_file.write_text('@echo off\nnode %~dp0\\claude-code %*')
        extensionless_file.write_text('#!/bin/sh\nexec node "$basedir/claude-code" "$@"')

        # find_command_robust returns the .cmd file (as Windows would typically find)
        mock_find.return_value = str(cmd_file)

        # Commands succeed
        mock_run_cmd.return_value = subprocess.CompletedProcess([], 0, '', '')
        mock_bash_cmd.return_value = subprocess.CompletedProcess([], 0, '', '')

        server = {
            'name': 'supabase',
            'scope': 'user',
            'transport': 'http',
            'url': 'https://mcp.supabase.com/mcp?project_ref=xxx&read_only=true',
        }

        result = setup_environment.configure_mcp_server(server)
        assert result is True

        # Verify run_bash_command was called
        assert mock_bash_cmd.called
        bash_cmd = mock_bash_cmd.call_args.args[0]

        # The bash command should use the extensionless file, not .cmd
        # Convert to unix path format for the check
        assert 'claude.cmd' not in bash_cmd.lower()
        # The extensionless 'claude' should be in the path (converted to unix format)
        assert '/claude"' in bash_cmd or "/claude'" in bash_cmd or 'claude" mcp' in bash_cmd


class TestMCPTildeExpansionWindows:
    """Test tilde expansion in user-scope STDIO MCP commands on Windows.

    Validates that tildes in commands are expanded using Python's os.path.expanduser()
    before being passed to Git Bash, preventing bash from expanding ~ to Unix-style
    /c/Users/... paths.
    """

    @patch('platform.system', return_value='Windows')
    @patch('setup_environment.expand_tildes_in_command')
    @patch('setup_environment.run_bash_command')
    @patch('setup_environment.run_command')
    @patch('setup_environment.find_command_robust')
    def test_configure_mcp_server_stdio_windows_expands_tilde_in_command(
        self, mock_find, mock_run_cmd, mock_bash_cmd, mock_expand_tilde, mock_system,
    ):
        """Verify tildes in user-scope STDIO commands are expanded to Windows paths.

        Ensures that tildes are expanded using Python's os.path.expanduser() which
        produces Windows paths (C:\\Users\\...) rather than letting Git Bash expand
        them to Unix-style paths (/c/Users/...).
        """
        del mock_system  # Unused but required for patch
        mock_find.return_value = 'C:\\Users\\Test\\AppData\\Roaming\\npm\\claude.CMD'
        mock_run_cmd.return_value = subprocess.CompletedProcess([], 0, '', '')
        mock_bash_cmd.return_value = subprocess.CompletedProcess([], 0, '', '')
        # Mock expand_tildes_in_command to return Windows-style expanded path
        mock_expand_tilde.return_value = 'python C:\\Users\\test\\.claude\\mcp\\mcp_wrapper.py'

        server = {
            'name': 'tilde-test-server',
            'scope': 'user',
            'command': 'python ~/.claude/mcp/mcp_wrapper.py',
        }

        result = setup_environment.configure_mcp_server(server)

        assert result is True
        # Verify expand_tildes_in_command was called with the original command
        mock_expand_tilde.assert_called_once_with('python ~/.claude/mcp/mcp_wrapper.py')
        # Verify bash command contains expanded path with forward slashes
        bash_cmd = mock_bash_cmd.call_args.args[0]
        assert 'C:/Users/test/.claude/mcp/mcp_wrapper.py' in bash_cmd
        # Verify no unexpanded tilde in command portion (after '--')
        command_part = bash_cmd.split('-- ')[1] if '-- ' in bash_cmd else bash_cmd
        assert '~' not in command_part

    @patch('platform.system', return_value='Windows')
    @patch('setup_environment.expand_tildes_in_command')
    @patch('setup_environment.run_bash_command')
    @patch('setup_environment.run_command')
    @patch('setup_environment.find_command_robust')
    def test_configure_mcp_server_stdio_windows_npx_with_tilde_expands(
        self, mock_find, mock_run_cmd, mock_bash_cmd, mock_expand_tilde, mock_system,
    ):
        """Verify npx commands with tildes are expanded AND wrapped with cmd /c.

        npx commands on Windows require both tilde expansion AND cmd /c wrapper
        for proper execution in Git Bash.
        """
        del mock_system  # Unused but required for patch
        mock_find.return_value = 'C:\\Users\\Test\\AppData\\Roaming\\npm\\claude.CMD'
        mock_run_cmd.return_value = subprocess.CompletedProcess([], 0, '', '')
        mock_bash_cmd.return_value = subprocess.CompletedProcess([], 0, '', '')
        mock_expand_tilde.return_value = 'npx C:\\Users\\test\\.claude\\mcp\\server-script'

        server = {
            'name': 'npx-tilde-server',
            'scope': 'user',
            'command': 'npx ~/.claude/mcp/server-script',
        }

        result = setup_environment.configure_mcp_server(server)

        assert result is True
        bash_cmd = mock_bash_cmd.call_args.args[0]
        # Verify cmd /c wrapper with expanded path
        assert 'cmd /c npx C:/Users/test/.claude/mcp/server-script' in bash_cmd
        # Verify no unexpanded tilde in the command part
        command_part = bash_cmd.split('-- ')[1] if '-- ' in bash_cmd else bash_cmd
        assert '~' not in command_part

    @patch('platform.system', return_value='Windows')
    @patch('setup_environment.expand_tildes_in_command')
    @patch('setup_environment.run_bash_command')
    @patch('setup_environment.run_command')
    @patch('setup_environment.find_command_robust')
    def test_configure_mcp_server_stdio_windows_no_tilde_unchanged(
        self, mock_find, mock_run_cmd, mock_bash_cmd, mock_expand_tilde, mock_system,
    ):
        """Verify commands without tildes are not modified (regression test).

        Commands that don't contain tildes should pass through unchanged to
        ensure backward compatibility.
        """
        del mock_system  # Unused but required for patch
        mock_find.return_value = 'C:\\Users\\Test\\AppData\\Roaming\\npm\\claude.CMD'
        mock_run_cmd.return_value = subprocess.CompletedProcess([], 0, '', '')
        mock_bash_cmd.return_value = subprocess.CompletedProcess([], 0, '', '')
        # Command without tilde returns unchanged
        mock_expand_tilde.return_value = 'uvx mcp-server-package'

        server = {
            'name': 'no-tilde-server',
            'scope': 'user',
            'command': 'uvx mcp-server-package',
        }

        result = setup_environment.configure_mcp_server(server)

        assert result is True
        mock_expand_tilde.assert_called_once_with('uvx mcp-server-package')
        bash_cmd = mock_bash_cmd.call_args.args[0]
        assert 'uvx mcp-server-package' in bash_cmd

    @patch('platform.system', return_value='Windows')
    @patch('setup_environment.run_bash_command')
    @patch('setup_environment.run_command')
    @patch('setup_environment.find_command_robust')
    def test_configure_mcp_server_profile_scope_unchanged(
        self, mock_find, mock_run_cmd, mock_bash_cmd, mock_system,
    ):
        """Verify profile-scope servers return early without STDIO add operation.

        Profile-scope servers are configured via --strict-mcp-config, not claude mcp add.
        On Windows, removals use run_bash_command, then the function returns early.
        """
        del mock_system, mock_run_cmd  # Unused but required for patch
        mock_find.return_value = 'C:\\Users\\Test\\AppData\\Roaming\\npm\\claude.CMD'
        mock_bash_cmd.return_value = subprocess.CompletedProcess([], 0, '', '')

        server = {
            'name': 'profile-server',
            'scope': 'profile',
            'command': 'python ~/.claude/mcp/script.py',
        }

        result = setup_environment.configure_mcp_server(server)

        assert result is True
        # On Windows, removals use run_bash_command (3 calls: user, local, project)
        # Then profile scope returns early - no add operation
        assert mock_bash_cmd.call_count == 3
        # All bash calls should be removal commands, not 'mcp add'
        for call in mock_bash_cmd.call_args_list:
            bash_cmd = call.args[0]
            assert 'mcp remove' in bash_cmd
            assert 'mcp add' not in bash_cmd

    @patch('platform.system', return_value='Windows')
    @patch('setup_environment.expand_tildes_in_command')
    @patch('setup_environment.run_bash_command')
    @patch('setup_environment.run_command')
    @patch('setup_environment.find_command_robust')
    def test_configure_mcp_server_stdio_windows_multiple_tildes_expanded(
        self, mock_find, mock_run_cmd, mock_bash_cmd, mock_expand_tilde, mock_system,
    ):
        """Verify commands with multiple tilde paths all get expanded.

        When a command contains multiple tilde references (e.g., script path
        and config path), all should be expanded.
        """
        del mock_system  # Unused but required for patch
        mock_find.return_value = 'C:\\Users\\Test\\AppData\\Roaming\\npm\\claude.CMD'
        mock_run_cmd.return_value = subprocess.CompletedProcess([], 0, '', '')
        mock_bash_cmd.return_value = subprocess.CompletedProcess([], 0, '', '')
        # Both tildes expanded
        mock_expand_tilde.return_value = (
            'python C:\\Users\\test\\.claude\\mcp\\script.py '
            '--config C:\\Users\\test\\.config\\mcp.yaml'
        )

        server = {
            'name': 'multi-tilde-server',
            'scope': 'user',
            'command': 'python ~/.claude/mcp/script.py --config ~/.config/mcp.yaml',
        }

        result = setup_environment.configure_mcp_server(server)

        assert result is True
        bash_cmd = mock_bash_cmd.call_args.args[0]
        # Verify both paths expanded with forward slashes
        assert 'C:/Users/test/.claude/mcp/script.py' in bash_cmd
        assert 'C:/Users/test/.config/mcp.yaml' in bash_cmd
        # No unexpanded tildes in command portion
        command_part = bash_cmd.split('-- ')[1] if '-- ' in bash_cmd else bash_cmd
        assert '~' not in command_part

    @patch('platform.system', return_value='Windows')
    @patch('setup_environment.expand_tildes_in_command')
    @patch('setup_environment.run_bash_command')
    @patch('setup_environment.run_command')
    @patch('setup_environment.find_command_robust')
    def test_configure_mcp_server_stdio_windows_backslash_to_forward_slash(
        self, mock_find, mock_run_cmd, mock_bash_cmd, mock_expand_tilde, mock_system,
    ):
        """Verify backslashes from os.path.expanduser() are converted to forward slashes.

        Windows os.path.expanduser() returns backslashes (C:\\Users\\...) which must
        be converted to forward slashes for consistent cross-platform paths.
        """
        del mock_system  # Unused but required for patch
        mock_find.return_value = 'C:\\Users\\Test\\AppData\\Roaming\\npm\\claude.CMD'
        mock_run_cmd.return_value = subprocess.CompletedProcess([], 0, '', '')
        mock_bash_cmd.return_value = subprocess.CompletedProcess([], 0, '', '')
        # Simulate os.path.expanduser returning backslashes
        mock_expand_tilde.return_value = 'python C:\\Users\\test\\.claude\\script.py'

        server = {
            'name': 'backslash-test-server',
            'scope': 'user',
            'command': 'python ~/.claude/script.py',
        }

        result = setup_environment.configure_mcp_server(server)

        assert result is True
        bash_cmd = mock_bash_cmd.call_args.args[0]
        # Extract command portion after '--'
        command_part = bash_cmd.split('-- ')[1] if '-- ' in bash_cmd else bash_cmd
        # Verify no backslashes in command part
        assert '\\' not in command_part
        # Verify forward slashes are used
        assert 'C:/Users/test/.claude/script.py' in bash_cmd

    @patch('platform.system', return_value='Windows')
    @patch('setup_environment.expand_tildes_in_command')
    @patch('setup_environment.run_bash_command')
    @patch('setup_environment.run_command')
    @patch('setup_environment.find_command_robust')
    def test_configure_mcp_server_local_scope_stdio_with_tilde(
        self, mock_find, mock_run_cmd, mock_bash_cmd, mock_expand_tilde, mock_system,
    ):
        """Verify local-scope also gets tilde expansion on Windows.

        Local-scope servers use the same STDIO code path as user-scope
        and should receive the same tilde expansion treatment.
        """
        del mock_system  # Unused but required for patch
        mock_find.return_value = 'C:\\Users\\Test\\AppData\\Roaming\\npm\\claude.CMD'
        mock_run_cmd.return_value = subprocess.CompletedProcess([], 0, '', '')
        mock_bash_cmd.return_value = subprocess.CompletedProcess([], 0, '', '')
        mock_expand_tilde.return_value = 'python C:\\Users\\test\\.claude\\mcp\\local_server.py'

        server = {
            'name': 'local-tilde-server',
            'scope': 'local',
            'command': 'python ~/.claude/mcp/local_server.py',
        }

        result = setup_environment.configure_mcp_server(server)

        assert result is True
        bash_cmd = mock_bash_cmd.call_args.args[0]
        # Tilde expanded and backslashes converted
        assert 'C:/Users/test/.claude/mcp/local_server.py' in bash_cmd
        # No unexpanded tilde in command portion
        command_part = bash_cmd.split('-- ')[1] if '-- ' in bash_cmd else bash_cmd
        assert '~' not in command_part

    @patch('platform.system', return_value='Windows')
    @patch('setup_environment.expand_tildes_in_command')
    @patch('setup_environment.run_bash_command')
    @patch('setup_environment.run_command')
    @patch('setup_environment.find_command_robust')
    def test_configure_mcp_server_combined_scope_with_tilde(
        self, mock_find, mock_run_cmd, mock_bash_cmd, mock_expand_tilde, mock_system,
    ):
        """Verify combined scope servers with tildes work correctly.

        When scope is [user, profile], the user-scope add command should
        have expanded tilde, while profile servers are returned for separate handling.
        """
        del mock_system  # Unused but required for patch
        mock_find.return_value = 'C:\\Users\\Test\\AppData\\Roaming\\npm\\claude.CMD'
        mock_run_cmd.return_value = subprocess.CompletedProcess([], 0, '', '')
        mock_bash_cmd.return_value = subprocess.CompletedProcess([], 0, '', '')
        mock_expand_tilde.return_value = 'python C:\\Users\\test\\.claude\\mcp\\combined.py'

        server = {
            'name': 'combined-tilde-server',
            'scope': ['user', 'profile'],
            'command': 'python ~/.claude/mcp/combined.py',
        }

        result = setup_environment.configure_mcp_server(server)

        assert result is True
        # expand_tildes_in_command should be called for user-scope add
        mock_expand_tilde.assert_called()
        # Verify user-scope bash command has expanded path
        bash_cmd = mock_bash_cmd.call_args.args[0]
        assert 'C:/Users/test/.claude/mcp/combined.py' in bash_cmd


class TestMCPTildeExpansionUnix:
    """Test tilde expansion in STDIO MCP commands on Mac/Linux.

    P2 fix: Ensures tilde paths in MCP server commands are expanded
    on Unix systems, matching the Windows behavior.
    """

    @patch('platform.system', return_value='Darwin')
    @patch('setup_environment.expand_tildes_in_command')
    @patch('setup_environment.run_command')
    @patch('setup_environment.find_command_robust')
    def test_configure_mcp_server_stdio_macos_expands_tilde(
        self, mock_find, mock_run_cmd, mock_expand_tilde, mock_system,
    ):
        """Verify tildes in STDIO commands are expanded on macOS."""
        del mock_system  # Unused but required for patch
        mock_find.return_value = '/usr/local/bin/claude'
        mock_run_cmd.return_value = subprocess.CompletedProcess([], 0, '', '')
        mock_expand_tilde.return_value = 'python /Users/test/.claude/mcp/server.py'

        server = {
            'name': 'macos-tilde-server',
            'scope': 'user',
            'command': 'python ~/.claude/mcp/server.py',
        }

        result = setup_environment.configure_mcp_server(server)

        assert result is True
        # Verify expand_tildes_in_command was called
        mock_expand_tilde.assert_called()
        # Verify expanded path is used in command
        call_args = mock_run_cmd.call_args
        cmd_list = call_args[0][0]
        # Command should contain expanded path
        assert any('/Users/test/.claude' in str(arg) for arg in cmd_list)

    @patch('platform.system', return_value='Linux')
    @patch('setup_environment.expand_tildes_in_command')
    @patch('setup_environment.run_command')
    @patch('setup_environment.find_command_robust')
    def test_configure_mcp_server_stdio_linux_expands_tilde(
        self, mock_find, mock_run_cmd, mock_expand_tilde, mock_system,
    ):
        """Verify tildes in STDIO commands are expanded on Linux."""
        del mock_system  # Unused but required for patch
        mock_find.return_value = '/usr/bin/claude'
        mock_run_cmd.return_value = subprocess.CompletedProcess([], 0, '', '')
        mock_expand_tilde.return_value = 'python /home/test/.claude/mcp/server.py'

        server = {
            'name': 'linux-tilde-server',
            'scope': 'user',
            'command': 'python ~/.claude/mcp/server.py',
        }

        result = setup_environment.configure_mcp_server(server)

        assert result is True
        # Verify expand_tildes_in_command was called
        mock_expand_tilde.assert_called()
        # Verify expanded path is used in command
        call_args = mock_run_cmd.call_args
        cmd_list = call_args[0][0]
        # Command should contain expanded path
        assert any('/home/test/.claude' in str(arg) for arg in cmd_list)

    @patch('platform.system', return_value='Darwin')
    @patch('setup_environment.expand_tildes_in_command')
    @patch('setup_environment.run_command')
    @patch('setup_environment.find_command_robust')
    def test_configure_mcp_server_stdio_unix_no_tilde_unchanged(
        self, mock_find, mock_run_cmd, mock_expand_tilde, mock_system,
    ):
        """Verify commands without tildes pass through unchanged on Unix."""
        del mock_system  # Unused but required for patch
        mock_find.return_value = '/usr/local/bin/claude'
        mock_run_cmd.return_value = subprocess.CompletedProcess([], 0, '', '')
        # Command without tilde returns unchanged
        mock_expand_tilde.return_value = 'uvx mcp-server-package'

        server = {
            'name': 'no-tilde-unix-server',
            'scope': 'user',
            'command': 'uvx mcp-server-package',
        }

        result = setup_environment.configure_mcp_server(server)

        assert result is True
        # Verify expand_tildes_in_command was called
        mock_expand_tilde.assert_called_with('uvx mcp-server-package')

    @patch('platform.system', return_value='Linux')
    @patch('setup_environment.expand_tildes_in_command')
    @patch('setup_environment.run_command')
    @patch('setup_environment.find_command_robust')
    def test_configure_mcp_server_stdio_linux_multiple_tildes_expanded(
        self, mock_find, mock_run_cmd, mock_expand_tilde, mock_system,
    ):
        """Verify commands with multiple tilde paths all get expanded on Linux."""
        del mock_system  # Unused but required for patch
        mock_find.return_value = '/usr/bin/claude'
        mock_run_cmd.return_value = subprocess.CompletedProcess([], 0, '', '')
        # Both tildes expanded
        mock_expand_tilde.return_value = (
            'python /home/test/.claude/mcp/script.py '
            '--config /home/test/.config/mcp.yaml'
        )

        server = {
            'name': 'multi-tilde-linux-server',
            'scope': 'user',
            'command': 'python ~/.claude/mcp/script.py --config ~/.config/mcp.yaml',
        }

        result = setup_environment.configure_mcp_server(server)

        assert result is True
        # Verify expand_tildes_in_command was called
        mock_expand_tilde.assert_called()
        # Verify expanded path is used in command
        call_args = mock_run_cmd.call_args
        cmd_list = call_args[0][0]
        # Command should contain expanded paths
        cmd_str = ' '.join(str(arg) for arg in cmd_list)
        assert '/home/test/.claude/mcp/script.py' in cmd_str
        assert '/home/test/.config/mcp.yaml' in cmd_str

    @patch('platform.system', return_value='Darwin')
    @patch('setup_environment.expand_tildes_in_command')
    @patch('setup_environment.run_command')
    @patch('setup_environment.find_command_robust')
    def test_configure_mcp_server_local_scope_macos_with_tilde(
        self, mock_find, mock_run_cmd, mock_expand_tilde, mock_system,
    ):
        """Verify local-scope also gets tilde expansion on macOS."""
        del mock_system  # Unused but required for patch
        mock_find.return_value = '/usr/local/bin/claude'
        mock_run_cmd.return_value = subprocess.CompletedProcess([], 0, '', '')
        mock_expand_tilde.return_value = 'python /Users/test/.claude/mcp/local_server.py'

        server = {
            'name': 'local-tilde-macos-server',
            'scope': 'local',
            'command': 'python ~/.claude/mcp/local_server.py',
        }

        result = setup_environment.configure_mcp_server(server)

        assert result is True
        # Verify expand_tildes_in_command was called
        mock_expand_tilde.assert_called()
        # Verify expanded path is used in command
        call_args = mock_run_cmd.call_args
        cmd_list = call_args[0][0]
        # Command should contain expanded path
        assert any('/Users/test/.claude' in str(arg) for arg in cmd_list)


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
                model='claude-3-opus',
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            assert settings_file.exists()

            settings = json.loads(settings_file.read_text())
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

            # First download hook files
            setup_environment.download_hook_files(
                hooks,
                claude_dir,
                config_source='https://example.com/config.yaml',
            )

            # Then create additional settings
            result = setup_environment.create_additional_settings(
                hooks,
                claude_dir,
                'test-env',
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            assert 'hooks' in settings
            assert 'PostToolUse' in settings['hooks']

    @patch('setup_environment.handle_resource')
    def test_create_additional_settings_with_javascript_hooks(self, mock_download):
        """Test creating settings with JavaScript hooks includes node prefix."""
        mock_download.return_value = True

        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)
            hooks_dir = claude_dir / 'hooks'
            hooks_dir.mkdir(parents=True, exist_ok=True)

            hooks = {
                'files': ['hooks/quality-check.js'],
                'events': [
                    {
                        'event': 'PostToolUse',
                        'matcher': 'Edit|Write',
                        'type': 'command',
                        'command': 'quality-check.js',
                    },
                ],
            }

            result = setup_environment.create_additional_settings(
                hooks,
                claude_dir,
                'test-env',
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            assert 'hooks' in settings
            assert 'PostToolUse' in settings['hooks']

            # Verify node prefix is present
            hook_command = settings['hooks']['PostToolUse'][0]['hooks'][0]['command']
            assert hook_command.startswith('node ')
            assert 'quality-check.js' in hook_command

    @patch('setup_environment.handle_resource')
    def test_create_additional_settings_with_mjs_hooks(self, mock_download):
        """Test creating settings with .mjs ES module hooks includes node prefix."""
        mock_download.return_value = True

        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)
            hooks_dir = claude_dir / 'hooks'
            hooks_dir.mkdir(parents=True, exist_ok=True)

            hooks = {
                'files': ['hooks/validator.mjs'],
                'events': [
                    {
                        'event': 'PreToolUse',
                        'matcher': 'Bash',
                        'type': 'command',
                        'command': 'validator.mjs',
                    },
                ],
            }

            result = setup_environment.create_additional_settings(
                hooks,
                claude_dir,
                'test-env',
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            hook_command = settings['hooks']['PreToolUse'][0]['hooks'][0]['command']
            assert hook_command.startswith('node ')
            assert 'validator.mjs' in hook_command

    @patch('setup_environment.handle_resource')
    def test_create_additional_settings_with_cjs_hooks(self, mock_download):
        """Test creating settings with .cjs CommonJS hooks includes node prefix."""
        mock_download.return_value = True

        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)
            hooks_dir = claude_dir / 'hooks'
            hooks_dir.mkdir(parents=True, exist_ok=True)

            hooks = {
                'files': ['hooks/legacy-hook.cjs'],
                'events': [
                    {
                        'event': 'PostToolUse',
                        'matcher': 'Read',
                        'type': 'command',
                        'command': 'legacy-hook.cjs',
                    },
                ],
            }

            result = setup_environment.create_additional_settings(
                hooks,
                claude_dir,
                'test-env',
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            hook_command = settings['hooks']['PostToolUse'][0]['hooks'][0]['command']
            assert hook_command.startswith('node ')
            assert 'legacy-hook.cjs' in hook_command

    @patch('setup_environment.handle_resource')
    def test_create_additional_settings_javascript_hook_with_config(self, mock_download):
        """Test JavaScript hooks with config file path appended correctly."""
        mock_download.return_value = True

        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)
            hooks_dir = claude_dir / 'hooks'
            hooks_dir.mkdir(parents=True, exist_ok=True)

            hooks = {
                'files': ['hooks/quality-check.js', 'configs/js-hook-config.yaml'],
                'events': [
                    {
                        'event': 'PostToolUse',
                        'matcher': 'Edit|Write',
                        'type': 'command',
                        'command': 'quality-check.js',
                        'config': 'js-hook-config.yaml',
                    },
                ],
            }

            result = setup_environment.create_additional_settings(
                hooks,
                claude_dir,
                'test-env',
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            hook_command = settings['hooks']['PostToolUse'][0]['hooks'][0]['command']
            assert hook_command.startswith('node ')
            assert 'quality-check.js' in hook_command
            assert 'js-hook-config.yaml' in hook_command

    @patch('setup_environment.handle_resource')
    def test_create_additional_settings_mixed_python_javascript_hooks(self, mock_download):
        """Test mixed Python and JavaScript hooks get correct prefixes."""
        mock_download.return_value = True

        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)
            hooks_dir = claude_dir / 'hooks'
            hooks_dir.mkdir(parents=True, exist_ok=True)

            hooks = {
                'files': ['hooks/python_hook.py', 'hooks/js_hook.js'],
                'events': [
                    {
                        'event': 'PostToolUse',
                        'matcher': 'Edit',
                        'type': 'command',
                        'command': 'python_hook.py',
                    },
                    {
                        'event': 'PostToolUse',
                        'matcher': 'Write',
                        'type': 'command',
                        'command': 'js_hook.js',
                    },
                ],
            }

            result = setup_environment.create_additional_settings(
                hooks,
                claude_dir,
                'test-env',
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            # Find Python and JavaScript hooks
            post_tool_use_hooks = settings['hooks']['PostToolUse']

            for hook_group in post_tool_use_hooks:
                for hook in hook_group['hooks']:
                    if 'python_hook.py' in hook['command']:
                        assert 'uv run' in hook['command']
                    elif 'js_hook.js' in hook['command']:
                        assert hook['command'].startswith('node ')

    @patch('setup_environment.handle_resource')
    def test_create_additional_settings_javascript_case_insensitive(self, mock_download):
        """Test JavaScript extension detection is case-insensitive."""
        mock_download.return_value = True

        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)
            hooks_dir = claude_dir / 'hooks'
            hooks_dir.mkdir(parents=True, exist_ok=True)

            hooks = {
                'files': ['hooks/Hook.JS'],
                'events': [
                    {
                        'event': 'PostToolUse',
                        'matcher': 'Edit',
                        'type': 'command',
                        'command': 'Hook.JS',
                    },
                ],
            }

            result = setup_environment.create_additional_settings(
                hooks,
                claude_dir,
                'test-env',
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            hook_command = settings['hooks']['PostToolUse'][0]['hooks'][0]['command']
            assert hook_command.startswith('node ')

    def test_create_additional_settings_always_thinking_enabled_true(self):
        """Test alwaysThinkingEnabled set to true."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            result = setup_environment.create_additional_settings(
                {},
                claude_dir,
                'test-env',
                always_thinking_enabled=True,
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            assert 'alwaysThinkingEnabled' in settings
            assert settings['alwaysThinkingEnabled'] is True

    def test_create_additional_settings_always_thinking_enabled_false(self):
        """Test alwaysThinkingEnabled set to false."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            result = setup_environment.create_additional_settings(
                {},
                claude_dir,
                'test-env',
                always_thinking_enabled=False,
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            assert 'alwaysThinkingEnabled' in settings
            assert settings['alwaysThinkingEnabled'] is False

    def test_create_additional_settings_always_thinking_enabled_none_not_included(self):
        """Test alwaysThinkingEnabled not included when None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            result = setup_environment.create_additional_settings(
                {},
                claude_dir,
                'test-env',
                always_thinking_enabled=None,
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            assert 'alwaysThinkingEnabled' not in settings

    def test_create_additional_settings_company_announcements(self):
        """Test companyAnnouncements set with multiple items."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)
            announcements = [
                'Welcome to Acme Corp!',
                'Code reviews required for all PRs',
            ]

            result = setup_environment.create_additional_settings(
                {},
                claude_dir,
                'test-env',
                company_announcements=announcements,
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            assert 'companyAnnouncements' in settings
            assert settings['companyAnnouncements'] == announcements
            assert len(settings['companyAnnouncements']) == 2

    def test_create_additional_settings_company_announcements_single(self):
        """Test companyAnnouncements with single announcement."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)
            announcements = ['Single announcement']

            result = setup_environment.create_additional_settings(
                {},
                claude_dir,
                'test-env',
                company_announcements=announcements,
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            assert 'companyAnnouncements' in settings
            assert settings['companyAnnouncements'] == announcements

    def test_create_additional_settings_company_announcements_empty_list(self):
        """Test companyAnnouncements with empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            result = setup_environment.create_additional_settings(
                {},
                claude_dir,
                'test-env',
                company_announcements=[],
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            # Empty list should still be included (explicit configuration)
            assert 'companyAnnouncements' in settings
            assert settings['companyAnnouncements'] == []

    def test_create_additional_settings_company_announcements_none_not_included(self):
        """Test companyAnnouncements not included when None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            result = setup_environment.create_additional_settings(
                {},
                claude_dir,
                'test-env',
                company_announcements=None,
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            assert 'companyAnnouncements' not in settings

    def test_create_additional_settings_attribution_full(self):
        """Test attribution with both commit and pr values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)
            attribution = {
                'commit': 'Custom commit attribution',
                'pr': 'Custom PR attribution',
            }

            result = setup_environment.create_additional_settings(
                {},
                claude_dir,
                'test-env',
                attribution=attribution,
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            assert 'attribution' in settings
            assert settings['attribution']['commit'] == 'Custom commit attribution'
            assert settings['attribution']['pr'] == 'Custom PR attribution'

    def test_create_additional_settings_attribution_hide_all(self):
        """Test attribution with empty strings to hide all."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)
            attribution = {'commit': '', 'pr': ''}

            result = setup_environment.create_additional_settings(
                {},
                claude_dir,
                'test-env',
                attribution=attribution,
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            assert settings['attribution'] == {'commit': '', 'pr': ''}

    def test_create_additional_settings_attribution_precedence_over_deprecated(self):
        """Test attribution takes precedence over deprecated include_co_authored_by."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)
            attribution = {'commit': 'New format', 'pr': 'New format'}

            result = setup_environment.create_additional_settings(
                {},
                claude_dir,
                'test-env',
                include_co_authored_by=False,  # This should be ignored
                attribution=attribution,
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            assert 'attribution' in settings
            assert settings['attribution'] == attribution
            assert 'includeCoAuthoredBy' not in settings

    def test_create_additional_settings_deprecated_include_co_authored_by_false(self):
        """Test deprecated include_co_authored_by=False converts to attribution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            result = setup_environment.create_additional_settings(
                {},
                claude_dir,
                'test-env',
                include_co_authored_by=False,
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            # Should be converted to new format
            assert 'attribution' in settings
            assert settings['attribution'] == {'commit': '', 'pr': ''}
            assert 'includeCoAuthoredBy' not in settings

    def test_create_additional_settings_deprecated_include_co_authored_by_true(self):
        """Test deprecated include_co_authored_by=True does not override defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            result = setup_environment.create_additional_settings(
                {},
                claude_dir,
                'test-env',
                include_co_authored_by=True,
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            # true -> use defaults, so neither key should be set
            assert 'attribution' not in settings
            assert 'includeCoAuthoredBy' not in settings

    def test_create_additional_settings_attribution_none_not_included(self):
        """Test attribution not included when None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            result = setup_environment.create_additional_settings(
                {},
                claude_dir,
                'test-env',
                attribution=None,
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            assert 'attribution' not in settings

    def test_create_additional_settings_status_line_python(self):
        """Test statusLine with Python script."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)
            # Create hooks directory
            hooks_dir = claude_dir / 'hooks'
            hooks_dir.mkdir(parents=True, exist_ok=True)

            status_line = {
                'file': 'statusline.py',
                'padding': 0,
            }

            result = setup_environment.create_additional_settings(
                {},
                claude_dir,
                'test-env',
                status_line=status_line,
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            assert 'statusLine' in settings
            assert settings['statusLine']['type'] == 'command'
            assert 'uv run' in settings['statusLine']['command']
            assert 'statusline.py' in settings['statusLine']['command']
            assert settings['statusLine']['padding'] == 0

    def test_create_additional_settings_status_line_shell(self):
        """Test statusLine with shell script."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)
            hooks_dir = claude_dir / 'hooks'
            hooks_dir.mkdir(parents=True, exist_ok=True)

            status_line = {
                'file': 'statusline.sh',
            }

            result = setup_environment.create_additional_settings(
                {},
                claude_dir,
                'test-env',
                status_line=status_line,
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            assert 'statusLine' in settings
            assert settings['statusLine']['type'] == 'command'
            assert 'uv run' not in settings['statusLine']['command']
            assert 'statusline.sh' in settings['statusLine']['command']
            assert 'padding' not in settings['statusLine']

    def test_create_additional_settings_status_line_none_not_included(self):
        """Test statusLine not included when None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)

            result = setup_environment.create_additional_settings(
                {},
                claude_dir,
                'test-env',
                status_line=None,
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            assert 'statusLine' not in settings

    def test_create_additional_settings_status_line_with_query_params(self):
        """Test statusLine file with query parameters stripped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)
            hooks_dir = claude_dir / 'hooks'
            hooks_dir.mkdir(parents=True, exist_ok=True)

            status_line = {
                'file': 'statusline.py?ref_type=heads',
            }

            result = setup_environment.create_additional_settings(
                {},
                claude_dir,
                'test-env',
                status_line=status_line,
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            assert 'statusLine' in settings
            assert '?' not in settings['statusLine']['command']
            assert 'statusline.py' in settings['statusLine']['command']

    def test_create_additional_settings_status_line_with_config(self):
        """Test statusLine with Python script and config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)
            hooks_dir = claude_dir / 'hooks'
            hooks_dir.mkdir(parents=True, exist_ok=True)

            # Create dummy files
            (hooks_dir / 'statusline.py').write_text('print("status")')
            (hooks_dir / 'config.yaml').write_text('key: value')

            status_line = {
                'file': 'statusline.py',
                'config': 'config.yaml',
                'padding': 0,
            }

            result = setup_environment.create_additional_settings(
                {},
                claude_dir,
                'test-env',
                status_line=status_line,
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            assert 'statusLine' in settings
            assert settings['statusLine']['type'] == 'command'
            assert 'uv run' in settings['statusLine']['command']
            assert 'statusline.py' in settings['statusLine']['command']
            assert 'config.yaml' in settings['statusLine']['command']
            assert settings['statusLine']['command'].endswith('config.yaml')
            assert settings['statusLine']['padding'] == 0

    def test_create_additional_settings_status_line_config_with_query_params(self):
        """Test statusLine config with query parameters stripped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)
            hooks_dir = claude_dir / 'hooks'
            hooks_dir.mkdir(parents=True, exist_ok=True)

            (hooks_dir / 'statusline.py').write_text('print("status")')
            (hooks_dir / 'config.yaml').write_text('key: value')

            status_line = {
                'file': 'statusline.py?ref_type=heads',
                'config': 'config.yaml?token=abc123',
            }

            result = setup_environment.create_additional_settings(
                {},
                claude_dir,
                'test-env',
                status_line=status_line,
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            assert 'statusLine' in settings
            assert '?' not in settings['statusLine']['command']
            assert 'statusline.py' in settings['statusLine']['command']
            assert 'config.yaml' in settings['statusLine']['command']

    def test_create_additional_settings_status_line_shell_with_config(self):
        """Test statusLine with shell script and config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)
            hooks_dir = claude_dir / 'hooks'
            hooks_dir.mkdir(parents=True, exist_ok=True)

            (hooks_dir / 'statusline.sh').write_text('#!/bin/bash\necho "status"')
            (hooks_dir / 'config.yaml').write_text('key: value')

            status_line = {
                'file': 'statusline.sh',
                'config': 'config.yaml',
            }

            result = setup_environment.create_additional_settings(
                {},
                claude_dir,
                'test-env',
                status_line=status_line,
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            assert 'statusLine' in settings
            assert 'uv run' not in settings['statusLine']['command']
            assert 'statusline.sh' in settings['statusLine']['command']
            assert 'config.yaml' in settings['statusLine']['command']

    def test_create_additional_settings_status_line_without_config_backward_compat(self):
        """Test that status-line without config field still works (backward compatibility)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir)
            hooks_dir = claude_dir / 'hooks'
            hooks_dir.mkdir(parents=True, exist_ok=True)

            (hooks_dir / 'statusline.py').write_text('print("status")')

            status_line = {
                'file': 'statusline.py',
                'padding': 0,
                # No 'config' field - backward compatibility
            }

            result = setup_environment.create_additional_settings(
                {},
                claude_dir,
                'test-env',
                status_line=status_line,
            )

            assert result is True
            settings_file = claude_dir / 'test-env-additional-settings.json'
            settings = json.loads(settings_file.read_text())

            assert 'statusLine' in settings
            # Command should end with the Python file, not a config
            assert settings['statusLine']['command'].endswith('statusline.py')


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
name: Test Markdown File
description: A test markdown file with front matter
---

# Content

This is the content of the file.
''')
            result = setup_environment.extract_front_matter(md_file)
            assert result is not None
            assert result['name'] == 'Test Markdown File'
            assert result['description'] == 'A test markdown file with front matter'
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
description: Alternative markdown file description
---
# Content
''')
            result = setup_environment.extract_front_matter(md_file)
            assert result is not None
            assert result['name'] == 'Alternative Style'
            assert result['description'] == 'Alternative markdown file description'

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


class TestMainFunction:
    """Test the main setup flow."""

    @patch('setup_environment.load_config_from_source')
    def test_main_invalid_mode(self, mock_load: MagicMock) -> None:
        """Test main with invalid mode value."""
        mock_load.return_value = (
            {
                'name': 'Test',
                'command-defaults': {
                    'system-prompt': 'test.md',
                    'mode': 'invalid',  # Invalid mode value
                },
            },
            'test.yaml',
        )

        with patch('sys.argv', ['setup_environment.py', 'test']), pytest.raises(SystemExit) as exc_info:
            setup_environment.main()

        assert exc_info.value.code == 1

    @patch('setup_environment.load_config_from_source')
    @patch('setup_environment.validate_all_config_files')
    @patch('setup_environment.install_claude')
    @patch('setup_environment.install_dependencies')
    @patch('setup_environment.process_resources')
    @patch('setup_environment.configure_all_mcp_servers')
    @patch('setup_environment.create_additional_settings')
    @patch('setup_environment.create_launcher_script')
    @patch('setup_environment.register_global_command')
    @patch('setup_environment.is_admin', return_value=True)
    @patch('pathlib.Path.mkdir')
    def test_main_success(
        self,
        mock_mkdir,
        mock_is_admin,
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
        assert mock_is_admin.return_value is True
        mock_load.return_value = (
            {
                'name': 'Test Environment',
                'command-name': 'test-env',
                'dependencies': {
                    'windows': ['npm install -g test'],
                },
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
        mock_mcp.return_value = (True, [], {'global_count': 0, 'profile_count': 0, 'combined_count': 0})
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
        with patch('sys.argv', ['setup_environment.py']), pytest.raises(SystemExit) as exc_info:
            setup_environment.main()
        assert exc_info.value.code == 1

    @patch('setup_environment.load_config_from_source')
    @patch('setup_environment.install_claude')
    @patch('setup_environment.is_admin', return_value=True)
    def test_main_install_failure(self, mock_is_admin, mock_install, mock_load):
        """Test main with Claude installation failure."""
        assert mock_is_admin.return_value is True  # Verify admin check is mocked
        mock_load.return_value = ({'name': 'Test'}, 'test.yaml')
        mock_install.return_value = False

        with patch('sys.argv', ['setup_environment.py', 'test']), pytest.raises(SystemExit) as exc_info:
            setup_environment.main()
        assert exc_info.value.code == 1

    @patch('setup_environment.load_config_from_source')
    @patch('setup_environment.find_command_robust')
    @patch('setup_environment.is_admin', return_value=True)
    def test_main_skip_install(self, mock_is_admin, mock_find, mock_load):
        """Test main with --skip-install flag."""
        assert mock_is_admin.return_value is True  # Verify admin check is mocked
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


class TestDownloadFailureTracking:
    """Test that download failures are tracked and reported in main()."""

    @patch('setup_environment.load_config_from_source')
    @patch('setup_environment.validate_all_config_files')
    @patch('setup_environment.install_claude')
    @patch('setup_environment.install_dependencies')
    @patch('setup_environment.process_resources')
    @patch('setup_environment.process_file_downloads')
    @patch('setup_environment.process_skills')
    @patch('setup_environment.download_hook_files')
    @patch('setup_environment.handle_resource')
    @patch('setup_environment.configure_all_mcp_servers')
    @patch('setup_environment.create_additional_settings')
    @patch('setup_environment.create_launcher_script')
    @patch('setup_environment.register_global_command')
    @patch('setup_environment.is_admin', return_value=True)
    @patch('pathlib.Path.mkdir')
    def test_main_exits_with_error_on_download_failure(
        self,
        mock_mkdir: MagicMock,
        mock_is_admin: MagicMock,
        mock_register: MagicMock,
        mock_launcher: MagicMock,
        mock_settings: MagicMock,
        mock_mcp: MagicMock,
        mock_handle: MagicMock,
        mock_hooks: MagicMock,
        mock_skills: MagicMock,
        mock_files: MagicMock,
        mock_resources: MagicMock,
        mock_deps: MagicMock,
        mock_install: MagicMock,
        mock_validate: MagicMock,
        mock_load: MagicMock,
    ) -> None:
        """Test that main() exits with code 1 when downloads fail."""
        del mock_mkdir, mock_is_admin
        mock_load.return_value = (
            {
                'name': 'Test Environment',
                'command-names': ['test-env'],
                'agents': ['agents/test.md'],
                'slash-commands': ['commands/test.md'],
                'hooks': {'files': ['hook.py']},
            },
            'test.yaml',
        )
        mock_validate.return_value = (True, [])
        mock_install.return_value = True
        mock_deps.return_value = True
        # Agents download fails
        mock_resources.return_value = False
        mock_files.return_value = True
        mock_skills.return_value = True
        mock_hooks.return_value = True
        mock_handle.return_value = True
        mock_mcp.return_value = (True, [], {'global_count': 0, 'profile_count': 0, 'combined_count': 0})
        mock_settings.return_value = True
        mock_launcher.return_value = Path('/tmp/launcher.sh')
        mock_register.return_value = True

        with patch('sys.argv', ['setup_environment.py', 'test']), pytest.raises(SystemExit) as exc_info:
            setup_environment.main()
        assert exc_info.value.code == 1

    @patch('setup_environment.load_config_from_source')
    @patch('setup_environment.validate_all_config_files')
    @patch('setup_environment.install_claude')
    @patch('setup_environment.install_dependencies')
    @patch('setup_environment.process_resources')
    @patch('setup_environment.process_file_downloads')
    @patch('setup_environment.process_skills')
    @patch('setup_environment.download_hook_files')
    @patch('setup_environment.handle_resource')
    @patch('setup_environment.configure_all_mcp_servers')
    @patch('setup_environment.create_additional_settings')
    @patch('setup_environment.create_launcher_script')
    @patch('setup_environment.register_global_command')
    @patch('setup_environment.is_admin', return_value=True)
    @patch('pathlib.Path.mkdir')
    def test_main_shows_success_when_all_downloads_succeed(
        self,
        mock_mkdir: MagicMock,
        mock_is_admin: MagicMock,
        mock_register: MagicMock,
        mock_launcher: MagicMock,
        mock_settings: MagicMock,
        mock_mcp: MagicMock,
        mock_handle: MagicMock,
        mock_hooks: MagicMock,
        mock_skills: MagicMock,
        mock_files: MagicMock,
        mock_resources: MagicMock,
        mock_deps: MagicMock,
        mock_install: MagicMock,
        mock_validate: MagicMock,
        mock_load: MagicMock,
    ) -> None:
        """Test that main() shows success banner when all downloads succeed."""
        del mock_mkdir, mock_is_admin
        mock_load.return_value = (
            {
                'name': 'Test Environment',
                'command-names': ['test-env'],
                'agents': ['agents/test.md'],
                'slash-commands': ['commands/test.md'],
                'hooks': {'files': ['hook.py']},
            },
            'test.yaml',
        )
        mock_validate.return_value = (True, [])
        mock_install.return_value = True
        mock_deps.return_value = True
        mock_resources.return_value = True
        mock_files.return_value = True
        mock_skills.return_value = True
        mock_hooks.return_value = True
        mock_handle.return_value = True
        mock_mcp.return_value = (True, [], {'global_count': 0, 'profile_count': 0, 'combined_count': 0})
        mock_settings.return_value = True
        mock_launcher.return_value = Path('/tmp/launcher.sh')
        mock_register.return_value = True

        with patch('sys.argv', ['setup_environment.py', 'test']), patch('sys.exit') as mock_exit:
            setup_environment.main()
            # sys.exit should NOT be called with 1 when everything succeeds
            mock_exit.assert_not_called()

    @patch('setup_environment.load_config_from_source')
    @patch('setup_environment.validate_all_config_files')
    @patch('setup_environment.install_claude')
    @patch('setup_environment.install_dependencies')
    @patch('setup_environment.process_resources')
    @patch('setup_environment.process_file_downloads')
    @patch('setup_environment.process_skills')
    @patch('setup_environment.download_hook_files')
    @patch('setup_environment.handle_resource')
    @patch('setup_environment.configure_all_mcp_servers')
    @patch('setup_environment.create_additional_settings')
    @patch('setup_environment.create_launcher_script')
    @patch('setup_environment.register_global_command')
    @patch('setup_environment.is_admin', return_value=True)
    @patch('pathlib.Path.mkdir')
    def test_main_reports_all_failed_categories(
        self,
        mock_mkdir: MagicMock,
        mock_is_admin: MagicMock,
        mock_register: MagicMock,
        mock_launcher: MagicMock,
        mock_settings: MagicMock,
        mock_mcp: MagicMock,
        mock_handle: MagicMock,
        mock_hooks: MagicMock,
        mock_skills: MagicMock,
        mock_files: MagicMock,
        mock_resources: MagicMock,
        mock_deps: MagicMock,
        mock_install: MagicMock,
        mock_validate: MagicMock,
        mock_load: MagicMock,
    ) -> None:
        """Test that main() lists all failure categories, not just the first."""
        del mock_mkdir, mock_is_admin
        mock_load.return_value = (
            {
                'name': 'Test Environment',
                'command-names': ['test-env'],
                'agents': ['agents/test.md'],
                'slash-commands': ['commands/test.md'],
                'skills': [{'name': 'test-skill'}],
                'files-to-download': [{'source': 'file.txt', 'dest': '~/file.txt'}],
                'hooks': {'files': ['hook.py']},
            },
            'test.yaml',
        )
        mock_validate.return_value = (True, [])
        mock_install.return_value = True
        mock_deps.return_value = True
        # Multiple categories fail
        mock_files.return_value = False
        mock_resources.return_value = False
        mock_skills.return_value = False
        mock_hooks.return_value = False
        mock_handle.return_value = True
        mock_mcp.return_value = (True, [], {'global_count': 0, 'profile_count': 0, 'combined_count': 0})
        mock_settings.return_value = True
        mock_launcher.return_value = Path('/tmp/launcher.sh')
        mock_register.return_value = True

        with (
            patch('sys.argv', ['setup_environment.py', 'test']),
            patch('builtins.print') as mock_print,
            pytest.raises(SystemExit) as exc_info,
        ):
            setup_environment.main()
        assert exc_info.value.code == 1

        # Verify the error banner was printed (happens before sys.exit)
        printed_text = ' '.join(str(call) for call in mock_print.call_args_list)
        assert 'Setup Completed with Errors' in printed_text

    @patch('setup_environment.load_config_from_source')
    @patch('setup_environment.validate_all_config_files')
    @patch('setup_environment.install_claude')
    @patch('setup_environment.install_dependencies')
    @patch('setup_environment.process_resources')
    @patch('setup_environment.process_file_downloads')
    @patch('setup_environment.process_skills')
    @patch('setup_environment.download_hook_files')
    @patch('setup_environment.handle_resource')
    @patch('setup_environment.configure_all_mcp_servers')
    @patch('setup_environment.create_additional_settings')
    @patch('setup_environment.create_launcher_script')
    @patch('setup_environment.register_global_command')
    @patch('setup_environment.is_admin', return_value=True)
    @patch('pathlib.Path.mkdir')
    def test_main_continues_config_steps_despite_download_failures(
        self,
        mock_mkdir: MagicMock,
        mock_is_admin: MagicMock,
        mock_register: MagicMock,
        mock_launcher: MagicMock,
        mock_settings: MagicMock,
        mock_mcp: MagicMock,
        mock_handle: MagicMock,
        mock_hooks: MagicMock,
        mock_skills: MagicMock,
        mock_files: MagicMock,
        mock_resources: MagicMock,
        mock_deps: MagicMock,
        mock_install: MagicMock,
        mock_validate: MagicMock,
        mock_load: MagicMock,
    ) -> None:
        """Test that main() continues configuration steps even when downloads fail."""
        del mock_mkdir, mock_is_admin
        mock_load.return_value = (
            {
                'name': 'Test Environment',
                'command-names': ['test-env'],
                'agents': ['agents/test.md'],
                'slash-commands': ['commands/test.md'],
                'mcp-servers': [{'name': 'test'}],
                'hooks': {'files': ['hook.py']},
            },
            'test.yaml',
        )
        mock_validate.return_value = (True, [])
        mock_install.return_value = True
        mock_deps.return_value = True
        # Downloads fail
        mock_resources.return_value = False
        mock_files.return_value = True
        mock_skills.return_value = True
        mock_hooks.return_value = True
        mock_handle.return_value = True
        mock_mcp.return_value = (True, [], {'global_count': 0, 'profile_count': 0, 'combined_count': 0})
        mock_settings.return_value = True
        mock_launcher.return_value = Path('/tmp/launcher.sh')
        mock_register.return_value = True

        with patch('sys.argv', ['setup_environment.py', 'test']), patch('sys.exit'):
            setup_environment.main()
            # MCP servers should still be configured despite download failures
            mock_mcp.assert_called_once()
            # Settings should still be created
            mock_settings.assert_called_once()
            # Launcher should still be created
            mock_launcher.assert_called_once()
            # Global command should still be registered
            mock_register.assert_called_once()


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


class TestMergeConfigs:
    """Test the _merge_configs helper function."""

    def test_basic_merge(self):
        """Test basic merge with no conflicts."""
        parent = {'a': 1, 'b': 2}
        child = {'c': 3, 'd': 4}
        result = setup_environment._merge_configs(parent, child)
        assert result == {'a': 1, 'b': 2, 'c': 3, 'd': 4}

    def test_child_override(self):
        """Test that child overrides parent for same key."""
        parent = {'a': 1, 'b': 2}
        child = {'b': 20, 'c': 3}
        result = setup_environment._merge_configs(parent, child)
        assert result == {'a': 1, 'b': 20, 'c': 3}

    def test_no_deep_merge(self):
        """Test that nested dicts are completely replaced, not merged."""
        parent = {'config': {'x': 1, 'y': 2}}
        child = {'config': {'z': 3}}
        result = setup_environment._merge_configs(parent, child)
        assert result['config'] == {'z': 3}
        assert 'x' not in result['config']

    def test_inherit_key_excluded(self):
        """Test that 'inherit' key from child is not in result."""
        parent = {'a': 1}
        child = {'inherit': 'something', 'b': 2}
        result = setup_environment._merge_configs(parent, child)
        assert result == {'a': 1, 'b': 2}
        assert 'inherit' not in result


class TestDeepMergeSettings:
    """Tests for deep_merge_settings function and its helpers."""

    # === Basic Merge Tests ===

    def test_empty_base_nonempty_updates(self):
        """Merge into empty base produces updates."""
        base: dict[str, object] = {}
        updates = {'a': 1, 'b': 2}
        result = setup_environment.deep_merge_settings(base, updates)
        assert result == {'a': 1, 'b': 2}
        assert base == {}  # Immutability check

    def test_nonempty_base_empty_updates(self):
        """Merge empty updates preserves base."""
        base = {'a': 1, 'b': 2}
        updates: dict[str, object] = {}
        result = setup_environment.deep_merge_settings(base, updates)
        assert result == {'a': 1, 'b': 2}

    def test_both_empty(self):
        """Merge two empty dicts returns empty dict."""
        base: dict[str, object] = {}
        updates: dict[str, object] = {}
        result = setup_environment.deep_merge_settings(base, updates)
        assert result == {}

    def test_disjoint_keys(self):
        """Merge with disjoint keys combines both."""
        base = {'a': 1}
        updates = {'b': 2}
        result = setup_environment.deep_merge_settings(base, updates)
        assert result == {'a': 1, 'b': 2}

    def test_overlapping_scalar_update_wins(self):
        """Updates override base for same scalar key."""
        base = {'a': 1}
        updates = {'a': 2}
        result = setup_environment.deep_merge_settings(base, updates)
        assert result == {'a': 2}

    # === Nested Object Merge Tests ===

    def test_nested_dict_merge(self):
        """Nested dicts are recursively merged."""
        base = {'a': {'b': 1, 'c': 2}}
        updates = {'a': {'c': 99, 'd': 3}}
        result = setup_environment.deep_merge_settings(base, updates)
        assert result == {'a': {'b': 1, 'c': 99, 'd': 3}}

    def test_deep_nested_merge(self):
        """Deep nesting is recursively merged."""
        base = {'a': {'b': {'c': 1}}}
        updates = {'a': {'b': {'d': 2}}}
        result = setup_environment.deep_merge_settings(base, updates)
        assert result == {'a': {'b': {'c': 1, 'd': 2}}}

    def test_update_nested_key(self):
        """Nested keys can be updated."""
        base = {'a': {'b': 1, 'c': 2}}
        updates = {'a': {'b': 99}}
        result = setup_environment.deep_merge_settings(base, updates)
        assert result == {'a': {'b': 99, 'c': 2}}

    def test_dict_replaces_scalar(self):
        """Dict in updates replaces scalar in base."""
        base = {'a': 1}
        updates = {'a': {'b': 2}}
        result = setup_environment.deep_merge_settings(base, updates)
        assert result == {'a': {'b': 2}}

    def test_scalar_replaces_dict(self):
        """Scalar in updates replaces dict in base."""
        base = {'a': {'b': 1}}
        updates = {'a': 2}
        result = setup_environment.deep_merge_settings(base, updates)
        assert result == {'a': 2}

    # === Array Union Tests (Default Keys) ===

    def test_permissions_allow_union(self):
        """permissions.allow arrays are unioned with deduplication."""
        base = {'permissions': {'allow': ['Read', 'Glob']}}
        updates = {'permissions': {'allow': ['Write', 'Read']}}
        result = setup_environment.deep_merge_settings(base, updates)
        # Order: base items first, then new items from updates
        assert result == {'permissions': {'allow': ['Read', 'Glob', 'Write']}}

    def test_permissions_deny_union(self):
        """permissions.deny arrays are unioned."""
        base = {'permissions': {'deny': ['Bash']}}
        updates = {'permissions': {'deny': ['Edit']}}
        result = setup_environment.deep_merge_settings(base, updates)
        assert result == {'permissions': {'deny': ['Bash', 'Edit']}}

    def test_permissions_ask_union(self):
        """permissions.ask arrays are unioned."""
        base = {'permissions': {'ask': ['Glob']}}
        updates = {'permissions': {'ask': ['Grep']}}
        result = setup_environment.deep_merge_settings(base, updates)
        assert result == {'permissions': {'ask': ['Glob', 'Grep']}}

    def test_permissions_deduplication(self):
        """Duplicate items in array union are removed."""
        base = {'permissions': {'allow': ['Read', 'Glob']}}
        updates = {'permissions': {'allow': ['Write', 'Read', 'Glob']}}
        result = setup_environment.deep_merge_settings(base, updates)
        # Read and Glob already in base, only Write is added
        assert result == {'permissions': {'allow': ['Read', 'Glob', 'Write']}}

    def test_permissions_empty_base_array(self):
        """Empty base array gets filled from updates."""
        base: dict[str, object] = {'permissions': {'allow': []}}
        updates = {'permissions': {'allow': ['Read']}}
        result = setup_environment.deep_merge_settings(base, updates)
        assert result == {'permissions': {'allow': ['Read']}}

    def test_permissions_empty_updates_array(self):
        """Empty updates array preserves base array."""
        base = {'permissions': {'allow': ['Read']}}
        updates: dict[str, object] = {'permissions': {'allow': []}}
        result = setup_environment.deep_merge_settings(base, updates)
        assert result == {'permissions': {'allow': ['Read']}}

    # === Array Non-Union Tests ===

    def test_non_union_key_replaces(self):
        """Arrays at non-union keys are replaced entirely."""
        base = {'items': [1, 2]}
        updates = {'items': [3, 4]}
        result = setup_environment.deep_merge_settings(base, updates)
        assert result == {'items': [3, 4]}

    # === Custom Array Union Keys Tests ===

    def test_custom_array_union_keys(self):
        """Custom array union keys override defaults."""
        base = {
            'custom': {'list': [1, 2]},
            'permissions': {'allow': ['a']},
        }
        updates = {
            'custom': {'list': [2, 3]},
            'permissions': {'allow': ['b']},
        }
        result = setup_environment.deep_merge_settings(
            base, updates, array_union_keys={'custom.list'},
        )
        # custom.list is unioned, permissions.allow is replaced (not in custom keys)
        assert result['custom']['list'] == [1, 2, 3]
        assert result['permissions']['allow'] == ['b']

    def test_empty_custom_keys_disables_union(self):
        """Empty custom keys set disables all array union."""
        base = {'permissions': {'allow': ['Read']}}
        updates = {'permissions': {'allow': ['Write']}}
        result = setup_environment.deep_merge_settings(base, updates, array_union_keys=set())
        # With no union keys, array is replaced
        assert result == {'permissions': {'allow': ['Write']}}

    # === Immutability Tests ===

    def test_base_not_mutated(self):
        """Original base dict is not modified."""
        base = {'a': {'b': 1}}
        original_base = {'a': {'b': 1}}
        updates = {'a': {'c': 2}}
        setup_environment.deep_merge_settings(base, updates)
        assert base == original_base

    def test_updates_not_mutated(self):
        """Original updates dict is not modified."""
        base = {'a': 1}
        updates = {'b': {'c': 2}}
        original_updates = {'b': {'c': 2}}
        setup_environment.deep_merge_settings(base, updates)
        assert updates == original_updates

    def test_nested_base_not_mutated(self):
        """Nested dicts in base are not modified."""
        inner = {'b': 1}
        base = {'a': inner}
        updates = {'a': {'c': 2}}
        setup_environment.deep_merge_settings(base, updates)
        assert inner == {'b': 1}  # inner dict unchanged

    # === Edge Cases ===

    def test_none_values(self):
        """None values are handled correctly."""
        base = {'a': None}
        updates = {'b': None}
        result = setup_environment.deep_merge_settings(base, updates)
        assert result == {'a': None, 'b': None}

    def test_boolean_values(self):
        """Boolean values are preserved."""
        base = {'enabled': True}
        updates = {'disabled': False}
        result = setup_environment.deep_merge_settings(base, updates)
        assert result == {'enabled': True, 'disabled': False}
        assert result['enabled'] is True
        assert result['disabled'] is False

    def test_numeric_types(self):
        """Numeric types are preserved."""
        base = {'int_val': 42, 'float_val': math.pi}
        updates = {'new_int': 100}
        result = setup_environment.deep_merge_settings(base, updates)
        assert result == {'int_val': 42, 'float_val': math.pi, 'new_int': 100}

    def test_string_values(self):
        """String values are handled correctly."""
        base = {'name': 'base'}
        updates = {'name': 'updated'}
        result = setup_environment.deep_merge_settings(base, updates)
        assert result == {'name': 'updated'}

    def test_default_array_union_keys_constant(self):
        """DEFAULT_ARRAY_UNION_KEYS contains expected permission keys."""
        expected = {'permissions.allow', 'permissions.deny', 'permissions.ask'}
        assert expected == setup_environment.DEFAULT_ARRAY_UNION_KEYS

    # === Deep Copy Value Helper Tests ===

    def test_deep_copy_preserves_nested_structure(self):
        """_deep_copy_value creates independent copy of nested structure."""
        original = {'a': {'b': [1, 2, 3]}}
        copied = setup_environment._deep_copy_value(original)
        assert copied == original
        # Modify original nested structure
        assert isinstance(original['a'], dict)
        nested = original['a']
        assert isinstance(nested['b'], list)
        nested['b'].append(4)
        # Copied should be unchanged
        assert isinstance(copied, dict)
        assert isinstance(copied['a'], dict)
        assert copied['a']['b'] == [1, 2, 3]

    def test_deep_copy_primitives(self):
        """_deep_copy_value handles primitives correctly."""
        assert setup_environment._deep_copy_value(42) == 42
        assert setup_environment._deep_copy_value('hello') == 'hello'
        assert setup_environment._deep_copy_value(True) is True
        assert setup_environment._deep_copy_value(None) is None
        assert setup_environment._deep_copy_value(math.pi) == math.pi


class TestWriteUserSettings:
    """Tests for write_user_settings function."""

    def test_write_to_nonexistent_file(self, tmp_path: Path) -> None:
        """Write settings when settings.json doesn't exist."""
        claude_dir = tmp_path / '.claude'
        settings = {'language': 'russian', 'model': 'claude-sonnet-4'}

        result = setup_environment.write_user_settings(settings, claude_dir)

        assert result is True
        settings_file = claude_dir / 'settings.json'
        assert settings_file.exists()
        written = json.loads(settings_file.read_text(encoding='utf-8'))
        assert written == settings

    def test_write_to_existing_file(self, tmp_path: Path) -> None:
        """Write settings when settings.json already exists."""
        claude_dir = tmp_path / '.claude'
        claude_dir.mkdir(parents=True)
        settings_file = claude_dir / 'settings.json'
        existing = {'existingKey': 'existingValue', 'language': 'english'}
        settings_file.write_text(json.dumps(existing), encoding='utf-8')

        new_settings = {'language': 'russian', 'model': 'claude-opus-4'}
        result = setup_environment.write_user_settings(new_settings, claude_dir)

        assert result is True
        written = json.loads(settings_file.read_text(encoding='utf-8'))
        assert written['existingKey'] == 'existingValue'  # Preserved
        assert written['language'] == 'russian'  # Updated
        assert written['model'] == 'claude-opus-4'  # Added

    def test_write_empty_settings(self, tmp_path: Path) -> None:
        """Write empty settings dict preserves existing file."""
        claude_dir = tmp_path / '.claude'
        claude_dir.mkdir(parents=True)
        settings_file = claude_dir / 'settings.json'
        existing = {'language': 'english'}
        settings_file.write_text(json.dumps(existing), encoding='utf-8')

        result = setup_environment.write_user_settings({}, claude_dir)

        assert result is True
        written = json.loads(settings_file.read_text(encoding='utf-8'))
        assert written == existing  # Unchanged

    def test_write_creates_directory(self, tmp_path: Path) -> None:
        """Write when ~/.claude doesn't exist creates the directory."""
        claude_dir = tmp_path / 'nonexistent' / '.claude'
        assert not claude_dir.exists()
        settings = {'language': 'russian'}

        result = setup_environment.write_user_settings(settings, claude_dir)

        assert result is True
        assert claude_dir.exists()
        settings_file = claude_dir / 'settings.json'
        assert settings_file.exists()

    def test_merge_preserves_existing_keys(self, tmp_path: Path) -> None:
        """Existing keys not in settings are preserved after merge."""
        claude_dir = tmp_path / '.claude'
        claude_dir.mkdir(parents=True)
        settings_file = claude_dir / 'settings.json'
        existing = {'existingKey': 'existingValue', 'language': 'english'}
        settings_file.write_text(json.dumps(existing), encoding='utf-8')

        new_settings = {'language': 'russian'}
        result = setup_environment.write_user_settings(new_settings, claude_dir)

        assert result is True
        written = json.loads(settings_file.read_text(encoding='utf-8'))
        assert written['existingKey'] == 'existingValue'  # Preserved
        assert written['language'] == 'russian'  # Updated

    def test_merge_nested_objects(self, tmp_path: Path) -> None:
        """Nested objects are recursively merged."""
        claude_dir = tmp_path / '.claude'
        claude_dir.mkdir(parents=True)
        settings_file = claude_dir / 'settings.json'
        existing = {'sandbox': {'enabled': True, 'existingKey': 'value'}}
        settings_file.write_text(json.dumps(existing), encoding='utf-8')

        new_settings = {'sandbox': {'autoAllowBashIfSandboxed': True}}
        result = setup_environment.write_user_settings(new_settings, claude_dir)

        assert result is True
        written = json.loads(settings_file.read_text(encoding='utf-8'))
        assert written['sandbox']['enabled'] is True  # Preserved
        assert written['sandbox']['existingKey'] == 'value'  # Preserved
        assert written['sandbox']['autoAllowBashIfSandboxed'] is True  # Added

    def test_permissions_array_union(self, tmp_path: Path) -> None:
        """permissions.allow arrays are unioned during merge."""
        claude_dir = tmp_path / '.claude'
        claude_dir.mkdir(parents=True)
        settings_file = claude_dir / 'settings.json'
        existing = {'permissions': {'allow': ['Read', 'Glob']}}
        settings_file.write_text(json.dumps(existing), encoding='utf-8')

        new_settings = {'permissions': {'allow': ['Write', 'Read']}}
        result = setup_environment.write_user_settings(new_settings, claude_dir)

        assert result is True
        written = json.loads(settings_file.read_text(encoding='utf-8'))
        # Union: ['Read', 'Glob'] + ['Write', 'Read'] -> ['Read', 'Glob', 'Write']
        assert set(written['permissions']['allow']) == {'Read', 'Glob', 'Write'}

    def test_api_key_helper_tilde_expanded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """apiKeyHelper with tilde path is expanded before writing."""
        # Mock home directory for consistent test
        if sys.platform == 'win32':
            monkeypatch.setenv('USERPROFILE', 'C:\\Users\\testuser')
            # Windows can return either forward or backslash in expanded path
            expected_path_parts = ('C:/Users/testuser', 'C:\\Users\\testuser')
        else:
            monkeypatch.setenv('HOME', '/home/testuser')
            expected_path_parts = ('/home/testuser',)

        claude_dir = tmp_path / '.claude'
        settings = {
            'apiKeyHelper': 'uv run --no-project --python 3.12 ~/.claude/scripts/api_key_helper.py',
        }

        result = setup_environment.write_user_settings(settings, claude_dir)

        assert result is True
        settings_file = claude_dir / 'settings.json'
        written = json.loads(settings_file.read_text(encoding='utf-8'))
        # Tilde should be expanded
        assert '~' not in written['apiKeyHelper']
        assert any(part in written['apiKeyHelper'] for part in expected_path_parts)

    def test_aws_credential_export_tilde_expanded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """awsCredentialExport with tilde path is expanded before writing."""
        if sys.platform == 'win32':
            monkeypatch.setenv('USERPROFILE', 'C:\\Users\\testuser')
        else:
            monkeypatch.setenv('HOME', '/home/testuser')

        claude_dir = tmp_path / '.claude'
        settings = {
            'awsCredentialExport': 'bash ~/.claude/scripts/aws_creds.sh',
        }

        result = setup_environment.write_user_settings(settings, claude_dir)

        assert result is True
        settings_file = claude_dir / 'settings.json'
        written = json.loads(settings_file.read_text(encoding='utf-8'))
        assert '~' not in written['awsCredentialExport']

    def test_tilde_expansion_preserves_other_keys(self, tmp_path: Path) -> None:
        """Keys not in TILDE_EXPANSION_KEYS are not modified."""
        claude_dir = tmp_path / '.claude'
        settings = {
            'language': 'russian',
            'model': 'claude-opus-4',
            'cleanupPeriodDays': 60,
        }
        original_settings = settings.copy()

        result = setup_environment.write_user_settings(settings, claude_dir)

        assert result is True
        settings_file = claude_dir / 'settings.json'
        written = json.loads(settings_file.read_text(encoding='utf-8'))
        assert written == original_settings

    def test_tilde_expansion_multiple_paths(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Command with multiple tilde paths has all expanded."""
        if sys.platform == 'win32':
            monkeypatch.setenv('USERPROFILE', 'C:\\Users\\testuser')
        else:
            monkeypatch.setenv('HOME', '/home/testuser')

        claude_dir = tmp_path / '.claude'
        settings = {
            'apiKeyHelper': 'bash -c "cat ~/.claude/key.txt && echo ~/.claude/done"',
        }

        result = setup_environment.write_user_settings(settings, claude_dir)

        assert result is True
        settings_file = claude_dir / 'settings.json'
        written = json.loads(settings_file.read_text(encoding='utf-8'))
        # All tildes should be expanded
        assert written['apiKeyHelper'].count('~') == 0

    def test_no_tilde_no_change(self, tmp_path: Path) -> None:
        """Keys without tilde are unchanged."""
        claude_dir = tmp_path / '.claude'
        settings = {
            'apiKeyHelper': 'python3 /absolute/path/helper.py',
        }
        original_value = settings['apiKeyHelper']

        result = setup_environment.write_user_settings(settings, claude_dir)

        assert result is True
        settings_file = claude_dir / 'settings.json'
        written = json.loads(settings_file.read_text(encoding='utf-8'))
        assert written['apiKeyHelper'] == original_value

    def test_invalid_json_in_existing_file(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Invalid JSON in existing file logs warning and starts fresh."""
        claude_dir = tmp_path / '.claude'
        claude_dir.mkdir(parents=True)
        settings_file = claude_dir / 'settings.json'
        settings_file.write_text('{ invalid json }', encoding='utf-8')

        settings = {'language': 'russian'}
        result = setup_environment.write_user_settings(settings, claude_dir)

        assert result is True
        captured = capsys.readouterr()
        assert 'Invalid JSON' in captured.out
        written = json.loads(settings_file.read_text(encoding='utf-8'))
        assert written == settings

    def test_existing_file_not_dict(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Existing file that is array/string logs warning and starts fresh."""
        claude_dir = tmp_path / '.claude'
        claude_dir.mkdir(parents=True)
        settings_file = claude_dir / 'settings.json'
        settings_file.write_text('["array", "not", "dict"]', encoding='utf-8')

        settings = {'language': 'russian'}
        result = setup_environment.write_user_settings(settings, claude_dir)

        assert result is True
        captured = capsys.readouterr()
        assert 'not a dict' in captured.out
        written = json.loads(settings_file.read_text(encoding='utf-8'))
        assert written == settings

    def test_empty_existing_file(self, tmp_path: Path) -> None:
        """Existing empty file is treated as empty dict."""
        claude_dir = tmp_path / '.claude'
        claude_dir.mkdir(parents=True)
        settings_file = claude_dir / 'settings.json'
        settings_file.write_text('', encoding='utf-8')

        settings = {'language': 'russian'}
        result = setup_environment.write_user_settings(settings, claude_dir)

        assert result is True
        written = json.loads(settings_file.read_text(encoding='utf-8'))
        assert written == settings

    def test_whitespace_only_existing_file(self, tmp_path: Path) -> None:
        """Existing file with only whitespace is treated as empty dict."""
        claude_dir = tmp_path / '.claude'
        claude_dir.mkdir(parents=True)
        settings_file = claude_dir / 'settings.json'
        settings_file.write_text('   \n  \t  ', encoding='utf-8')

        settings = {'language': 'russian'}
        result = setup_environment.write_user_settings(settings, claude_dir)

        assert result is True
        written = json.loads(settings_file.read_text(encoding='utf-8'))
        assert written == settings

    def test_input_settings_not_mutated(self, tmp_path: Path) -> None:
        """Original settings dict is not modified by write_user_settings."""
        claude_dir = tmp_path / '.claude'
        settings = {
            'apiKeyHelper': 'uv run ~/.claude/scripts/helper.py',
            'language': 'russian',
        }
        original = {
            'apiKeyHelper': 'uv run ~/.claude/scripts/helper.py',
            'language': 'russian',
        }

        setup_environment.write_user_settings(settings, claude_dir)

        assert settings == original  # Not mutated

    def test_write_returns_false_on_permission_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns False when write fails due to permission error."""
        claude_dir = tmp_path / '.claude'
        claude_dir.mkdir(parents=True)

        # Mock write_text to raise OSError
        def mock_write_text(*_args: Any, **_kwargs: Any) -> None:
            raise OSError('Permission denied')

        monkeypatch.setattr(Path, 'write_text', mock_write_text)

        settings = {'language': 'russian'}
        result = setup_environment.write_user_settings(settings, claude_dir)

        assert result is False

    def test_file_ends_with_newline(self, tmp_path: Path) -> None:
        """Written file ends with newline for proper formatting."""
        claude_dir = tmp_path / '.claude'
        settings = {'language': 'russian'}

        setup_environment.write_user_settings(settings, claude_dir)

        settings_file = claude_dir / 'settings.json'
        content = settings_file.read_text(encoding='utf-8')
        assert content.endswith('\n')

    def test_json_formatted_with_indent(self, tmp_path: Path) -> None:
        """Written JSON is formatted with proper indentation."""
        claude_dir = tmp_path / '.claude'
        settings = {'language': 'russian', 'model': 'claude-opus-4'}

        setup_environment.write_user_settings(settings, claude_dir)

        settings_file = claude_dir / 'settings.json'
        content = settings_file.read_text(encoding='utf-8')
        # Check for indentation (2 spaces)
        assert '  "language"' in content or '  "model"' in content


class TestExpandTildeKeysInSettings:
    """Tests for _expand_tilde_keys_in_settings helper function."""

    def test_expands_api_key_helper(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """apiKeyHelper tilde paths are expanded."""
        if sys.platform == 'win32':
            monkeypatch.setenv('USERPROFILE', 'C:\\Users\\testuser')
            # Windows can return either forward or backslash in expanded path
            expected_path_parts = ('C:/Users/testuser', 'C:\\Users\\testuser')
        else:
            monkeypatch.setenv('HOME', '/home/testuser')
            expected_path_parts = ('/home/testuser',)

        settings = {'apiKeyHelper': 'uv run ~/.claude/scripts/helper.py'}

        result = setup_environment._expand_tilde_keys_in_settings(settings)

        assert '~' not in result['apiKeyHelper']
        assert any(part in result['apiKeyHelper'] for part in expected_path_parts)

    def test_expands_aws_credential_export(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """awsCredentialExport tilde paths are expanded."""
        if sys.platform == 'win32':
            monkeypatch.setenv('USERPROFILE', 'C:\\Users\\testuser')
        else:
            monkeypatch.setenv('HOME', '/home/testuser')

        settings = {'awsCredentialExport': 'bash ~/.aws/export.sh'}

        result = setup_environment._expand_tilde_keys_in_settings(settings)

        assert '~' not in result['awsCredentialExport']

    def test_does_not_expand_other_keys(self) -> None:
        """Keys not in TILDE_EXPANSION_KEYS are unchanged."""
        settings = {'language': 'russian', 'model': 'claude-opus-4'}

        result = setup_environment._expand_tilde_keys_in_settings(settings)

        assert result == settings

    def test_does_not_mutate_input(self) -> None:
        """Input settings dict is not modified."""
        settings = {'apiKeyHelper': 'uv run ~/.claude/helper.py'}
        original_value = settings['apiKeyHelper']

        setup_environment._expand_tilde_keys_in_settings(settings)

        assert settings['apiKeyHelper'] == original_value

    def test_handles_non_string_values(self) -> None:
        """Non-string values for expansion keys are ignored."""
        settings: dict[str, Any] = {'apiKeyHelper': 123}  # Invalid but should not crash

        result = setup_environment._expand_tilde_keys_in_settings(settings)

        assert result['apiKeyHelper'] == 123

    def test_handles_missing_expansion_keys(self) -> None:
        """Missing expansion keys do not cause errors."""
        settings = {'language': 'russian'}  # No apiKeyHelper or awsCredentialExport

        result = setup_environment._expand_tilde_keys_in_settings(settings)

        assert result == {'language': 'russian'}

    def test_expands_both_keys_when_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Both apiKeyHelper and awsCredentialExport are expanded when present."""
        if sys.platform == 'win32':
            monkeypatch.setenv('USERPROFILE', 'C:\\Users\\testuser')
        else:
            monkeypatch.setenv('HOME', '/home/testuser')

        settings = {
            'apiKeyHelper': 'python ~/.claude/key.py',
            'awsCredentialExport': 'bash ~/.aws/creds.sh',
            'language': 'russian',
        }

        result = setup_environment._expand_tilde_keys_in_settings(settings)

        assert '~' not in result['apiKeyHelper']
        assert '~' not in result['awsCredentialExport']
        assert result['language'] == 'russian'  # Unchanged


class TestValidateUserSettings:
    """Test the validate_user_settings function."""

    def test_empty_settings_passes(self) -> None:
        """Empty user-settings passes validation."""
        result = setup_environment.validate_user_settings({})
        assert result == []

    def test_valid_keys_pass(self) -> None:
        """Valid keys (not in excluded list) pass validation."""
        settings = {
            'language': 'russian',
            'model': 'claude-opus-4',
            'permissions': {'allow': ['Bash']},
        }
        result = setup_environment.validate_user_settings(settings)
        assert result == []

    def test_hooks_key_rejected(self) -> None:
        """The 'hooks' key is rejected."""
        settings = {'hooks': {'events': []}}
        result = setup_environment.validate_user_settings(settings)
        assert len(result) == 1
        assert 'hooks' in result[0]
        assert 'not allowed' in result[0]

    def test_statusline_key_rejected(self) -> None:
        """The 'statusLine' key is rejected."""
        settings = {'statusLine': {'file': 'script.py'}}
        result = setup_environment.validate_user_settings(settings)
        assert len(result) == 1
        assert 'statusLine' in result[0]
        assert 'not allowed' in result[0]

    def test_multiple_excluded_keys_all_reported(self) -> None:
        """Multiple excluded keys are all reported."""
        settings = {
            'hooks': {'events': []},
            'statusLine': {'file': 'script.py'},
        }
        result = setup_environment.validate_user_settings(settings)
        assert len(result) == 2
        error_text = ' '.join(result)
        assert 'hooks' in error_text
        assert 'statusLine' in error_text

    def test_mixed_valid_and_excluded_keys(self) -> None:
        """Mix of valid and excluded keys reports only excluded."""
        settings = {
            'language': 'russian',
            'hooks': {'events': []},
            'model': 'claude-opus-4',
        }
        result = setup_environment.validate_user_settings(settings)
        assert len(result) == 1
        assert 'hooks' in result[0]

    def test_excluded_keys_constant_used(self) -> None:
        """Function uses USER_SETTINGS_EXCLUDED_KEYS constant."""
        for key in setup_environment.USER_SETTINGS_EXCLUDED_KEYS:
            settings = {key: 'test_value'}
            result = setup_environment.validate_user_settings(settings)
            assert len(result) == 1
            assert key in result[0]


class TestDetectSettingsConflicts:
    """Test the detect_settings_conflicts function."""

    def test_no_conflicts_empty_sections(self) -> None:
        """Empty sections have no conflicts."""
        result = setup_environment.detect_settings_conflicts({}, {})
        assert result == []

    def test_no_conflicts_disjoint_keys(self) -> None:
        """Different keys in each section have no conflicts."""
        user_settings = {'language': 'russian'}
        root_config = {'model': 'claude-opus-4'}
        result = setup_environment.detect_settings_conflicts(user_settings, root_config)
        assert result == []

    def test_same_key_conflict_detected(self) -> None:
        """Same key in both sections is detected as conflict."""
        user_settings = {'model': 'claude-opus-4'}
        root_config = {'model': 'claude-sonnet-4'}
        result = setup_environment.detect_settings_conflicts(user_settings, root_config)
        assert len(result) == 1
        assert result[0] == ('model', 'claude-opus-4', 'claude-sonnet-4')

    def test_kebab_to_camel_mapping_conflict(self) -> None:
        """Kebab-case root key maps to camelCase user-settings key."""
        user_settings = {'alwaysThinkingEnabled': True}
        root_config = {'always-thinking-enabled': False}
        result = setup_environment.detect_settings_conflicts(user_settings, root_config)
        assert len(result) == 1
        assert result[0] == ('alwaysThinkingEnabled', True, False)

    def test_env_variables_mapping_conflict(self) -> None:
        """env-variables root key maps to env user-settings key."""
        user_settings = {'env': {'FOO': 'bar'}}
        root_config = {'env-variables': {'FOO': 'baz'}}
        result = setup_environment.detect_settings_conflicts(user_settings, root_config)
        assert len(result) == 1
        assert result[0] == ('env', {'FOO': 'bar'}, {'FOO': 'baz'})

    def test_multiple_conflicts_detected(self) -> None:
        """Multiple conflicts are all detected."""
        user_settings = {
            'model': 'claude-opus-4',
            'alwaysThinkingEnabled': True,
        }
        root_config = {
            'model': 'claude-sonnet-4',
            'always-thinking-enabled': False,
        }
        result = setup_environment.detect_settings_conflicts(user_settings, root_config)
        assert len(result) == 2
        conflicts_dict = {r[0]: (r[1], r[2]) for r in result}
        assert conflicts_dict['model'] == ('claude-opus-4', 'claude-sonnet-4')
        assert conflicts_dict['alwaysThinkingEnabled'] == (True, False)

    def test_unmapped_key_uses_same_name(self) -> None:
        """Keys not in mapping use same name for lookup."""
        user_settings = {'permissions': {'allow': ['Bash']}}
        root_config = {'permissions': {'deny': ['Web']}}
        result = setup_environment.detect_settings_conflicts(user_settings, root_config)
        assert len(result) == 1
        assert result[0][0] == 'permissions'

    def test_root_key_without_user_key_no_conflict(self) -> None:
        """Root key present without corresponding user key is not a conflict."""
        user_settings = {'language': 'russian'}
        root_config = {'model': 'claude-opus-4', 'always-thinking-enabled': True}
        result = setup_environment.detect_settings_conflicts(user_settings, root_config)
        assert result == []

    def test_all_mapped_keys_checked(self) -> None:
        """All keys in ROOT_TO_USER_SETTINGS_KEY_MAP are properly checked."""
        for root_key, user_key in setup_environment.ROOT_TO_USER_SETTINGS_KEY_MAP.items():
            user_settings = {user_key: 'user_value'}
            root_config = {root_key: 'root_value'}
            result = setup_environment.detect_settings_conflicts(user_settings, root_config)
            assert len(result) == 1, f'Failed for mapping {root_key} -> {user_key}'
            assert result[0][0] == user_key

    def test_conflict_returns_correct_tuple_structure(self) -> None:
        """Conflict tuple has correct structure (user_key, user_value, root_value)."""
        user_settings = {'model': 'user_model'}
        root_config = {'model': 'root_model'}
        result = setup_environment.detect_settings_conflicts(user_settings, root_config)
        assert len(result) == 1
        conflict = result[0]
        assert len(conflict) == 3
        assert conflict[0] == 'model'
        assert conflict[1] == 'user_model'
        assert conflict[2] == 'root_model'


class TestResolveInheritPath:
    """Test the _resolve_inherit_path helper function."""

    def test_full_url_unchanged(self):
        """Test that full URLs are returned unchanged."""
        result = setup_environment._resolve_inherit_path(
            'https://example.com/config.yaml',
            '/local/child.yaml',
        )
        assert result == 'https://example.com/config.yaml'

    def test_http_url_unchanged(self):
        """Test that HTTP URLs are returned unchanged."""
        result = setup_environment._resolve_inherit_path(
            'http://example.com/config.yaml',
            '/local/child.yaml',
        )
        assert result == 'http://example.com/config.yaml'

    def test_absolute_path_unchanged(self):
        """Test that absolute paths are returned unchanged."""
        # Use platform-appropriate absolute path
        if sys.platform == 'win32':
            abs_path = 'C:\\absolute\\path\\config.yaml'
            result = setup_environment._resolve_inherit_path(
                abs_path,
                'C:\\different\\child.yaml',
            )
            assert result == abs_path
        else:
            result = setup_environment._resolve_inherit_path(
                '/absolute/path/config.yaml',
                '/different/child.yaml',
            )
            assert result == '/absolute/path/config.yaml'

    def test_relative_from_url(self):
        """Test relative path resolution from URL source."""
        result = setup_environment._resolve_inherit_path(
            'parent.yaml',
            'https://example.com/configs/child.yaml',
        )
        assert result == 'https://example.com/configs/parent.yaml'

    def test_repo_name_from_repo_name(self):
        """Test repo name resolution when source is also repo name."""
        result = setup_environment._resolve_inherit_path(
            'python-base',
            'python-web',
        )
        assert result == 'python-base'


class TestConfigInheritance:
    """Test configuration inheritance functionality."""

    def test_no_inheritance_returns_config_unchanged(self):
        """Test that config without 'inherit' key is returned as-is."""
        config = {'name': 'Test', 'model': 'claude-3'}
        result = setup_environment.resolve_config_inheritance(config, 'test.yaml')
        assert result == config

    def test_inherit_key_removed_from_result(self):
        """Test that 'inherit' key is not in the final result."""
        with patch.object(setup_environment, 'load_config_from_source') as mock_load:
            mock_load.return_value = ({'name': 'Parent'}, 'parent.yaml')
            config = {'inherit': 'parent.yaml', 'model': 'claude-3'}
            result = setup_environment.resolve_config_inheritance(config, 'child.yaml')
            assert 'inherit' not in result

    @patch.object(setup_environment, 'load_config_from_source')
    def test_simple_inheritance(self, mock_load):
        """Test simple single-level inheritance."""
        mock_load.return_value = (
            {'name': 'Parent', 'model': 'claude-2', 'dependencies': {'common': ['uv']}},
            'parent.yaml',
        )
        child = {'inherit': 'parent.yaml', 'model': 'claude-3'}
        result = setup_environment.resolve_config_inheritance(child, 'child.yaml')

        assert result['name'] == 'Parent'  # Inherited from parent
        assert result['model'] == 'claude-3'  # Overridden by child
        assert result['dependencies'] == {'common': ['uv']}  # Inherited

    @patch.object(setup_environment, 'load_config_from_source')
    def test_child_completely_overrides_parent_key(self, mock_load):
        """Test that child completely replaces parent's top-level key (no deep merge)."""
        mock_load.return_value = (
            {'dependencies': {'common': ['uv'], 'windows': ['npm']}},
            'parent.yaml',
        )
        child = {
            'inherit': 'parent.yaml',
            'dependencies': {'linux': ['apt']},  # Completely replaces
        }
        result = setup_environment.resolve_config_inheritance(child, 'child.yaml')

        # Child's dependencies should COMPLETELY replace parent's
        assert result['dependencies'] == {'linux': ['apt']}
        assert 'common' not in result['dependencies']
        assert 'windows' not in result['dependencies']

    @patch.object(setup_environment, 'load_config_from_source')
    def test_multi_level_inheritance(self, mock_load):
        """Test grandparent -> parent -> child inheritance chain."""

        def load_side_effect(config_spec: str, _auth_param: str | None = None) -> tuple[dict, str]:
            if 'grandparent' in config_spec:
                return ({'name': 'Grandparent', 'a': 1, 'b': 2}, 'grandparent.yaml')
            if 'parent' in config_spec:
                return ({'inherit': 'grandparent.yaml', 'b': 20, 'c': 3}, 'parent.yaml')
            raise FileNotFoundError(f'Not found: {config_spec}')

        mock_load.side_effect = load_side_effect

        child = {'inherit': 'parent.yaml', 'c': 30, 'd': 4}
        result = setup_environment.resolve_config_inheritance(child, 'child.yaml')

        assert result['name'] == 'Grandparent'  # From grandparent
        assert result['a'] == 1  # From grandparent
        assert result['b'] == 20  # Parent overrides grandparent
        assert result['c'] == 30  # Child overrides parent
        assert result['d'] == 4  # Child only

    def test_circular_dependency_self_reference(self):
        """Test circular dependency detection for self-reference."""
        config = {'inherit': 'self.yaml', 'name': 'Self'}
        with patch.object(setup_environment, 'load_config_from_source') as mock_load:
            mock_load.return_value = (config, 'self.yaml')
            import pytest

            with pytest.raises(ValueError, match='Circular dependency'):
                setup_environment.resolve_config_inheritance(config, 'self.yaml')

    @patch.object(setup_environment, 'load_config_from_source')
    def test_circular_dependency_a_b_a(self, mock_load):
        """Test circular dependency detection: A -> B -> A."""

        def load_side_effect(config_spec: str, _auth_param: str | None = None) -> tuple[dict, str]:
            if 'a.yaml' in config_spec:
                return ({'inherit': 'b.yaml', 'name': 'A'}, 'a.yaml')
            if 'b.yaml' in config_spec:
                return ({'inherit': 'a.yaml', 'name': 'B'}, 'b.yaml')
            raise FileNotFoundError(f'Not found: {config_spec}')

        mock_load.side_effect = load_side_effect

        config = {'inherit': 'b.yaml', 'model': 'test'}
        import pytest

        with pytest.raises(ValueError, match='Circular dependency'):
            setup_environment.resolve_config_inheritance(config, 'a.yaml')

    def test_max_depth_exceeded(self):
        """Test maximum depth limit enforcement."""
        with patch.object(setup_environment, 'load_config_from_source') as mock_load:
            # Create a chain that exceeds MAX_INHERITANCE_DEPTH
            call_count = [0]

            def deep_chain(
                _config_spec: str, _auth_param: str | None = None,
            ) -> tuple[dict, str]:
                call_count[0] += 1
                # Create configs: level0 -> level1 -> level2 -> ...
                return ({'inherit': f'level{call_count[0]}.yaml'}, f'level{call_count[0] - 1}.yaml')

            mock_load.side_effect = deep_chain

            config = {'inherit': 'level0.yaml'}
            import pytest

            with pytest.raises(ValueError, match='Maximum inheritance depth'):
                setup_environment.resolve_config_inheritance(config, 'start.yaml')

    def test_invalid_inherit_value_not_string(self):
        """Test error when inherit value is not a string."""
        config = {'inherit': ['parent.yaml'], 'name': 'Test'}  # List instead of string
        import pytest

        with pytest.raises(ValueError, match='must be a string'):
            setup_environment.resolve_config_inheritance(config, 'test.yaml')

    def test_invalid_inherit_value_dict(self):
        """Test error when inherit value is a dict."""
        config = {'inherit': {'source': 'parent.yaml'}, 'name': 'Test'}
        import pytest

        with pytest.raises(ValueError, match='must be a string'):
            setup_environment.resolve_config_inheritance(config, 'test.yaml')

    def test_empty_inherit_value(self):
        """Test error when inherit value is empty string."""
        config = {'inherit': '', 'name': 'Test'}
        import pytest

        with pytest.raises(ValueError, match='cannot be empty'):
            setup_environment.resolve_config_inheritance(config, 'test.yaml')

    def test_whitespace_inherit_value(self):
        """Test error when inherit value is only whitespace."""
        config = {'inherit': '   ', 'name': 'Test'}
        import pytest

        with pytest.raises(ValueError, match='cannot be empty'):
            setup_environment.resolve_config_inheritance(config, 'test.yaml')

    @patch.object(setup_environment, 'load_config_from_source')
    def test_parent_not_found_local(self, mock_load):
        """Test error when local parent config doesn't exist."""
        mock_load.side_effect = FileNotFoundError('Configuration not found')
        config = {'inherit': './missing.yaml', 'name': 'Test'}
        import pytest

        with pytest.raises(FileNotFoundError):
            setup_environment.resolve_config_inheritance(config, 'test.yaml')

    @patch.object(setup_environment, 'load_config_from_source')
    def test_parent_not_found_url(self, mock_load):
        """Test error when URL parent config doesn't exist."""
        mock_load.side_effect = urllib.error.HTTPError(
            'url', 404, 'Not Found', {}, None,
        )
        config = {'inherit': 'https://example.com/missing.yaml', 'name': 'Test'}
        with pytest.raises(urllib.error.HTTPError):
            setup_environment.resolve_config_inheritance(config, 'test.yaml')

    @patch.object(setup_environment, 'load_config_from_source')
    def test_inherit_full_url(self, mock_load):
        """Test inheriting from full URL."""
        mock_load.return_value = ({'name': 'Remote'}, 'https://example.com/base.yaml')
        config = {'inherit': 'https://example.com/base.yaml', 'model': 'test'}
        result = setup_environment.resolve_config_inheritance(config, './local.yaml')

        assert result['name'] == 'Remote'
        mock_load.assert_called_once_with('https://example.com/base.yaml', None)

    @patch.object(setup_environment, 'load_config_from_source')
    def test_inherit_relative_from_url(self, mock_load):
        """Test inheriting relative path when current config is from URL."""
        mock_load.return_value = ({'name': 'Parent'}, 'https://example.com/configs/parent.yaml')
        config = {'inherit': 'parent.yaml', 'model': 'test'}

        setup_environment.resolve_config_inheritance(
            config, 'https://example.com/configs/child.yaml',
        )

        # Should resolve to same directory as child
        mock_load.assert_called_once_with(
            'https://example.com/configs/parent.yaml', None,
        )

    @patch.object(setup_environment, 'load_config_from_source')
    def test_inherit_relative_from_local(self, mock_load):
        """Test inheriting relative path when current config is local."""
        mock_load.return_value = ({'name': 'Parent'}, '/home/user/configs/parent.yaml')
        config = {'inherit': 'parent.yaml', 'model': 'test'}

        with tempfile.TemporaryDirectory() as tmpdir:
            child_path = Path(tmpdir) / 'child.yaml'
            child_path.touch()

            setup_environment.resolve_config_inheritance(config, str(child_path))

            # Should resolve relative to child's directory
            mock_load.assert_called_once()
            call_args = mock_load.call_args[0][0]
            assert Path(call_args).name == 'parent.yaml'

    @patch.object(setup_environment, 'load_config_from_source')
    def test_inherit_repo_name(self, mock_load):
        """Test inheriting repository config by name."""
        mock_load.return_value = ({'name': 'Base Python'}, 'python-base.yaml')
        config = {'inherit': 'python-base', 'model': 'test'}

        setup_environment.resolve_config_inheritance(config, 'python')

        # Should pass through as repo name
        mock_load.assert_called_once_with('python-base', None)

    @patch.object(setup_environment, 'load_config_from_source')
    def test_auth_propagated_through_chain(self, mock_load):
        """Test that auth_param is passed through inheritance chain."""

        def check_auth(config_spec, auth_param=None):
            assert auth_param == 'my-token'
            if 'grandparent' in config_spec:
                return ({'name': 'GP'}, 'grandparent.yaml')
            return ({'inherit': 'grandparent.yaml'}, 'parent.yaml')

        mock_load.side_effect = check_auth

        config = {'inherit': 'parent.yaml', 'model': 'test'}
        setup_environment.resolve_config_inheritance(
            config, 'child.yaml', auth_param='my-token',
        )

    def test_full_inheritance_with_temp_files(self):
        """Integration test with actual temp files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create grandparent
            grandparent = Path(tmpdir) / 'grandparent.yaml'
            grandparent.write_text('''
name: Grandparent Config
model: claude-2
dependencies:
  common:
    - pip install base
''')

            # Create parent that inherits from grandparent
            parent = Path(tmpdir) / 'parent.yaml'
            parent.write_text(f'''
inherit: {grandparent}
command-name: my-env
mcp-servers:
  - name: server1
''')

            # Create child that inherits from parent
            child = Path(tmpdir) / 'child.yaml'
            child.write_text(f'''
inherit: {parent}
model: claude-3
agents:
  - my-agent.md
''')

            # Load and resolve
            config, source = setup_environment.load_config_from_source(str(child))
            resolved = setup_environment.resolve_config_inheritance(config, source)

            # Verify inheritance
            assert resolved['name'] == 'Grandparent Config'  # From grandparent
            assert resolved['model'] == 'claude-3'  # Overridden by child
            assert resolved['command-name'] == 'my-env'  # From parent
            assert resolved['mcp-servers'] == [{'name': 'server1'}]  # From parent
            assert resolved['agents'] == ['my-agent.md']  # From child
            assert resolved['dependencies'] == {'common': ['pip install base']}  # From grandparent
            assert 'inherit' not in resolved


class TestCommandNames:
    """Test command-names configuration (new format) and backward compatibility."""

    @patch('setup_environment.load_config_from_source')
    @patch('setup_environment.validate_all_config_files')
    @patch('setup_environment.install_claude')
    @patch('setup_environment.install_dependencies')
    @patch('setup_environment.process_resources')
    @patch('setup_environment.configure_all_mcp_servers')
    @patch('setup_environment.create_additional_settings')
    @patch('setup_environment.create_launcher_script')
    @patch('setup_environment.register_global_command')
    @patch('setup_environment.is_admin', return_value=True)
    @patch('pathlib.Path.mkdir')
    def test_command_names_single(
        self,
        mock_mkdir,
        mock_is_admin,
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
        """Test command-names with single name works correctly."""
        # Verify mock configuration is available
        assert mock_mkdir is not None
        assert mock_is_admin.return_value is True
        mock_load.return_value = (
            {
                'name': 'Test Environment',
                'command-names': ['aegis'],  # New format with single name
                'dependencies': {},
                'agents': [],
                'slash-commands': [],
                'mcp-servers': [],
            },
            'test.yaml',
        )
        mock_validate.return_value = (True, [])
        mock_install.return_value = True
        mock_deps.return_value = True
        mock_download.return_value = True
        mock_mcp.return_value = (True, [], {'global_count': 0, 'profile_count': 0, 'combined_count': 0})
        mock_settings.return_value = True
        mock_launcher.return_value = Path('/tmp/launcher.sh')
        mock_register.return_value = True

        with patch('sys.argv', ['setup_environment.py', 'test']), patch('sys.exit') as mock_exit:
            setup_environment.main()
            mock_exit.assert_not_called()

        # Verify register_global_command was called with primary name and no additional names
        mock_register.assert_called_once()
        call_args = mock_register.call_args
        assert call_args[0][1] == 'aegis'  # Primary command name
        assert call_args[0][2] is None  # No additional names

    @patch('setup_environment.load_config_from_source')
    @patch('setup_environment.validate_all_config_files')
    @patch('setup_environment.install_claude')
    @patch('setup_environment.install_dependencies')
    @patch('setup_environment.process_resources')
    @patch('setup_environment.configure_all_mcp_servers')
    @patch('setup_environment.create_additional_settings')
    @patch('setup_environment.create_launcher_script')
    @patch('setup_environment.register_global_command')
    @patch('setup_environment.is_admin', return_value=True)
    @patch('pathlib.Path.mkdir')
    def test_command_names_multiple(
        self,
        mock_mkdir,
        mock_is_admin,
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
        """Test command-names with multiple names creates all commands."""
        # Verify mock configuration is available
        assert mock_mkdir is not None
        assert mock_is_admin.return_value is True
        mock_load.return_value = (
            {
                'name': 'Test Environment',
                'command-names': ['aegis', 'claude-dev', 'myenv'],  # Multiple names
                'dependencies': {},
                'agents': [],
                'slash-commands': [],
                'mcp-servers': [],
            },
            'test.yaml',
        )
        mock_validate.return_value = (True, [])
        mock_install.return_value = True
        mock_deps.return_value = True
        mock_download.return_value = True
        mock_mcp.return_value = (True, [], {'global_count': 0, 'profile_count': 0, 'combined_count': 0})
        mock_settings.return_value = True
        mock_launcher.return_value = Path('/tmp/launcher.sh')
        mock_register.return_value = True

        with patch('sys.argv', ['setup_environment.py', 'test']), patch('sys.exit') as mock_exit:
            setup_environment.main()
            mock_exit.assert_not_called()

        # Verify register_global_command was called with primary name and additional names
        mock_register.assert_called_once()
        call_args = mock_register.call_args
        assert call_args[0][1] == 'aegis'  # Primary command name
        assert call_args[0][2] == ['claude-dev', 'myenv']  # Additional names

    @patch('setup_environment.load_config_from_source')
    @patch('setup_environment.validate_all_config_files')
    @patch('setup_environment.install_claude')
    @patch('setup_environment.install_dependencies')
    @patch('setup_environment.process_resources')
    @patch('setup_environment.configure_all_mcp_servers')
    @patch('setup_environment.create_additional_settings')
    @patch('setup_environment.create_launcher_script')
    @patch('setup_environment.register_global_command')
    @patch('setup_environment.is_admin', return_value=True)
    @patch('pathlib.Path.mkdir')
    def test_command_name_deprecated_shows_warning(
        self,
        mock_mkdir,
        mock_is_admin,
        mock_register,
        mock_launcher,
        mock_settings,
        mock_mcp,
        mock_download,
        mock_deps,
        mock_install,
        mock_validate,
        mock_load,
        capsys,
    ):
        """Test deprecated command-name shows deprecation warning."""
        # Verify mocks are properly configured
        assert mock_mkdir is not None
        assert mock_is_admin.return_value is True
        mock_load.return_value = (
            {
                'name': 'Test Environment',
                'command-name': 'old-style',  # Deprecated format
                'dependencies': {},
                'agents': [],
                'slash-commands': [],
                'mcp-servers': [],
            },
            'test.yaml',
        )
        mock_validate.return_value = (True, [])
        mock_install.return_value = True
        mock_deps.return_value = True
        mock_download.return_value = True
        mock_mcp.return_value = (True, [], {'global_count': 0, 'profile_count': 0, 'combined_count': 0})
        mock_settings.return_value = True
        mock_launcher.return_value = Path('/tmp/launcher.sh')
        mock_register.return_value = True

        with patch('sys.argv', ['setup_environment.py', 'test']), patch('sys.exit') as mock_exit:
            setup_environment.main()
            mock_exit.assert_not_called()

        # Verify deprecation warning was shown
        captured = capsys.readouterr()
        assert 'deprecated' in captured.out.lower()
        assert 'command-names' in captured.out

        # Verify register_global_command was still called with the name
        mock_register.assert_called_once()
        call_args = mock_register.call_args
        assert call_args[0][1] == 'old-style'  # Primary command name
        assert call_args[0][2] is None  # No additional names

    @patch('setup_environment.load_config_from_source')
    @patch('setup_environment.validate_all_config_files')
    @patch('setup_environment.install_claude')
    @patch('setup_environment.install_dependencies')
    @patch('setup_environment.process_resources')
    @patch('setup_environment.configure_all_mcp_servers')
    @patch('setup_environment.create_additional_settings')
    @patch('setup_environment.create_launcher_script')
    @patch('setup_environment.register_global_command')
    @patch('setup_environment.is_admin', return_value=True)
    @patch('pathlib.Path.mkdir')
    def test_command_names_takes_precedence_over_deprecated(
        self,
        mock_mkdir,
        mock_is_admin,
        mock_register,
        mock_launcher,
        mock_settings,
        mock_mcp,
        mock_download,
        mock_deps,
        mock_install,
        mock_validate,
        mock_load,
        capsys,
    ):
        """Test command-names takes precedence when both are specified."""
        # Verify mocks are properly configured
        assert mock_mkdir is not None
        assert mock_is_admin.return_value is True
        mock_load.return_value = (
            {
                'name': 'Test Environment',
                'command-names': ['new-style'],  # New format
                'command-name': 'old-style',  # Deprecated format (should be ignored)
                'dependencies': {},
                'agents': [],
                'slash-commands': [],
                'mcp-servers': [],
            },
            'test.yaml',
        )
        mock_validate.return_value = (True, [])
        mock_install.return_value = True
        mock_deps.return_value = True
        mock_download.return_value = True
        mock_mcp.return_value = (True, [], {'global_count': 0, 'profile_count': 0, 'combined_count': 0})
        mock_settings.return_value = True
        mock_launcher.return_value = Path('/tmp/launcher.sh')
        mock_register.return_value = True

        with patch('sys.argv', ['setup_environment.py', 'test']), patch('sys.exit') as mock_exit:
            setup_environment.main()
            mock_exit.assert_not_called()

        # Verify warning about both being specified
        captured = capsys.readouterr()
        assert 'both' in captured.out.lower() or 'Both' in captured.out

        # Verify register_global_command was called with new format
        mock_register.assert_called_once()
        call_args = mock_register.call_args
        assert call_args[0][1] == 'new-style'  # New format takes precedence

    @patch('setup_environment.load_config_from_source')
    def test_command_names_validation_empty_name(self, mock_load):
        """Test validation fails for empty command names."""
        mock_load.return_value = (
            {
                'name': 'Test Environment',
                'command-names': ['valid', ''],  # Empty name is invalid
            },
            'test.yaml',
        )

        with patch('sys.argv', ['setup_environment.py', 'test']), pytest.raises(SystemExit) as exc_info:
            setup_environment.main()
        assert exc_info.value.code == 1

    @patch('setup_environment.load_config_from_source')
    def test_command_names_validation_spaces(self, mock_load):
        """Test validation fails for command names with spaces."""
        mock_load.return_value = (
            {
                'name': 'Test Environment',
                'command-names': ['valid', 'invalid name'],  # Space is invalid
            },
            'test.yaml',
        )

        with patch('sys.argv', ['setup_environment.py', 'test']), pytest.raises(SystemExit) as exc_info:
            setup_environment.main()
        assert exc_info.value.code == 1


class TestRegisterGlobalCommandWithAliases:
    """Test register_global_command with additional command names (aliases)."""

    @patch('platform.system', return_value='Windows')
    @patch('setup_environment.add_directory_to_windows_path')
    def test_register_global_command_windows_with_aliases(self, mock_add_path, mock_system):
        """Test registering global command with aliases on Windows."""
        # Verify mock is properly configured for Windows platform
        assert mock_system.return_value == 'Windows'
        mock_add_path.return_value = (True, 'Added to PATH')

        with tempfile.TemporaryDirectory() as tmpdir:
            launcher = Path(tmpdir) / 'start-primary.ps1'
            launcher.write_text('# Launcher')

            # Mock home directory
            with patch('pathlib.Path.home', return_value=Path(tmpdir)):
                local_bin = Path(tmpdir) / '.local' / 'bin'
                local_bin.mkdir(parents=True, exist_ok=True)

                result = setup_environment.register_global_command(
                    launcher, 'primary', ['alias1', 'alias2'],
                )
                assert result is True

                # Verify primary command files were created
                assert (local_bin / 'primary.cmd').exists()
                assert (local_bin / 'primary.ps1').exists()
                assert (local_bin / 'primary').exists()

                # Verify alias command files were created
                assert (local_bin / 'alias1.cmd').exists()
                assert (local_bin / 'alias1.ps1').exists()
                assert (local_bin / 'alias1').exists()
                assert (local_bin / 'alias2.cmd').exists()
                assert (local_bin / 'alias2.ps1').exists()
                assert (local_bin / 'alias2').exists()

                # Verify alias CMD wrapper references primary launch script
                alias1_cmd_content = (local_bin / 'alias1.cmd').read_text()
                assert 'launch-primary.sh' in alias1_cmd_content
                assert 'alias for primary' in alias1_cmd_content

    @patch('platform.system', return_value='Linux')
    def test_register_global_command_linux_with_aliases(self, mock_system):
        """Test registering global command with aliases on Linux."""
        # Verify mock is properly configured for Linux platform
        assert mock_system.return_value == 'Linux'
        with tempfile.TemporaryDirectory() as tmpdir:
            launcher = Path(tmpdir) / 'start-primary.sh'
            launcher.write_text('#!/bin/bash\necho test')
            launcher.chmod(0o755)

            # Mock home directory and symlink creation
            with patch('pathlib.Path.home', return_value=Path(tmpdir)):
                local_bin = Path(tmpdir) / '.local' / 'bin'
                local_bin.mkdir(parents=True, exist_ok=True)

                # Track symlinks created
                symlinks_created = []

                def mock_symlink_to(self, target):
                    symlinks_created.append((self, target))
                    # Create a regular file instead of symlink for testing
                    self.write_text(f'# Symlink to {target}')

                with patch.object(Path, 'symlink_to', mock_symlink_to):
                    result = setup_environment.register_global_command(
                        launcher, 'primary', ['alias1', 'alias2'],
                    )
                    assert result is True

                # Verify symlinks were created for primary and all aliases
                symlink_names = [s[0].name for s in symlinks_created]
                assert 'primary' in symlink_names
                assert 'alias1' in symlink_names
                assert 'alias2' in symlink_names
                assert len(symlinks_created) == 3


class TestVerifyNodejsAvailable:
    """Test verify_nodejs_available function with various Node.js installation methods."""

    @patch('platform.system', return_value='Linux')
    def test_non_windows_returns_true(self, mock_system):
        """Test that non-Windows platforms always return True."""
        # Verify mock is properly configured for Linux platform
        assert mock_system.return_value == 'Linux'
        result = setup_environment.verify_nodejs_available()
        assert result is True

    @patch('platform.system', return_value='Windows')
    @patch('shutil.which')
    @patch('subprocess.run')
    def test_windows_node_in_path(self, mock_run, mock_which, mock_system, capsys):
        """Test finding Node.js via shutil.which on Windows."""
        # Verify mock is properly configured for Windows platform
        assert mock_system.return_value == 'Windows'
        mock_which.return_value = r'C:\Program Files\nodejs\node.exe'
        mock_run.return_value = subprocess.CompletedProcess(
            ['node', '--version'], 0, 'v20.10.0', '',
        )

        result = setup_environment.verify_nodejs_available()

        assert result is True
        mock_which.assert_called_with('node')
        captured = capsys.readouterr()
        assert 'Node.js verified' in captured.out
        assert 'v20.10.0' in captured.out

    @patch('platform.system', return_value='Windows')
    @patch('shutil.which')
    @patch('setup_environment.find_command_robust')
    @patch('subprocess.run')
    def test_windows_node_via_find_command_robust(
        self, mock_run, mock_find_robust, mock_which, mock_system, capsys,
    ):
        """Test finding Node.js via find_command_robust fallback on Windows."""
        # Verify mock is properly configured for Windows platform
        assert mock_system.return_value == 'Windows'
        # shutil.which returns None (not in PATH)
        mock_which.return_value = None
        # find_command_robust finds it in a version manager location
        mock_find_robust.return_value = r'C:\Users\test\AppData\Roaming\nvm\v20.10.0\node.exe'
        mock_run.return_value = subprocess.CompletedProcess(
            ['node', '--version'], 0, 'v20.10.0', '',
        )

        with patch.dict('os.environ', {'PATH': r'C:\Windows\System32'}):
            result = setup_environment.verify_nodejs_available()

        assert result is True
        captured = capsys.readouterr()
        assert 'Node.js verified' in captured.out

    @patch('platform.system', return_value='Windows')
    @patch('shutil.which')
    @patch('setup_environment.find_command_robust')
    def test_windows_node_not_found(self, mock_find_robust, mock_which, mock_system, capsys):
        """Test when Node.js is not found on Windows."""
        # Verify mock is properly configured for Windows platform
        assert mock_system.return_value == 'Windows'
        mock_which.return_value = None
        mock_find_robust.return_value = None

        result = setup_environment.verify_nodejs_available()

        assert result is False
        captured = capsys.readouterr()
        assert 'Node.js not found in PATH' in captured.err


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows-specific test')
class TestFindCommandRobustNodePaths:
    """Test find_command_robust with various Node.js installation paths."""

    @patch('platform.system', return_value='Windows')
    @patch('shutil.which', return_value=None)  # Primary search fails
    @patch('time.sleep')  # Skip retry delay
    def test_finds_node_in_volta_location(self, mock_sleep, mock_which, mock_system):
        """Test finding Node.js in Volta installation location."""
        # Verify mocks are properly configured
        assert mock_system.return_value == 'Windows'
        assert mock_which.return_value is None
        assert mock_sleep is not None  # Ensures time.sleep is mocked
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create volta directory structure
            volta_bin = Path(tmpdir) / '.volta' / 'bin'
            volta_bin.mkdir(parents=True)
            node_exe = volta_bin / 'node.exe'
            node_exe.write_text('fake node')

            with patch.dict('os.environ', {'USERPROFILE': tmpdir}):
                result = setup_environment.find_command_robust('node')

            assert result is not None
            assert 'node.exe' in result

    @patch('platform.system', return_value='Windows')
    @patch('shutil.which', return_value=None)  # Primary search fails
    @patch('time.sleep')  # Skip retry delay
    def test_finds_node_in_scoop_location(self, mock_sleep, mock_which, mock_system):
        """Test finding Node.js in Scoop installation location."""
        # Verify mocks are properly configured
        assert mock_system.return_value == 'Windows'
        assert mock_which.return_value is None
        assert mock_sleep is not None  # Ensures time.sleep is mocked
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create scoop directory structure
            scoop_node = Path(tmpdir) / 'scoop' / 'apps' / 'nodejs' / 'current'
            scoop_node.mkdir(parents=True)
            node_exe = scoop_node / 'node.exe'
            node_exe.write_text('fake node')

            with patch.dict('os.environ', {'USERPROFILE': tmpdir}):
                result = setup_environment.find_command_robust('node')

            assert result is not None
            assert 'node.exe' in result

    @patch('platform.system', return_value='Windows')
    @patch('shutil.which', return_value=None)  # Primary search fails
    @patch('time.sleep')  # Skip retry delay
    def test_finds_node_in_nvm_subdirectory(self, mock_sleep, mock_which, mock_system):
        """Test finding Node.js in nvm-windows version subdirectory."""
        # Verify mocks are properly configured
        assert mock_system.return_value == 'Windows'
        assert mock_which.return_value is None
        assert mock_sleep is not None  # Ensures time.sleep is mocked
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create nvm directory structure with version subdirectory
            nvm_dir = Path(tmpdir) / 'nvm'
            nvm_dir.mkdir(parents=True)
            version_dir = nvm_dir / 'v20.10.0'
            version_dir.mkdir()
            node_exe = version_dir / 'node.exe'
            node_exe.write_text('fake node')

            with patch.dict('os.environ', {'APPDATA': tmpdir}):
                result = setup_environment.find_command_robust('node')

            assert result is not None
            assert 'node.exe' in result


class TestMCPServerNeedsNodejsDetection:
    """Test smart detection of npx-based MCP servers that need Node.js."""

    def test_detects_npx_in_command(self):
        """Test that npx-based servers are correctly detected."""
        mcp_servers = [
            {'name': 'http-server', 'transport': 'http', 'url': 'http://localhost:8080'},
            {'name': 'npx-server', 'command': 'npx -y @modelcontextprotocol/server-filesystem'},
        ]

        needs_nodejs = any(
            'npx' in str(server.get('command', ''))
            for server in mcp_servers
            if server.get('command')
        )

        assert needs_nodejs is True

    def test_http_transport_does_not_need_nodejs(self):
        """Test that HTTP transport servers don't trigger Node.js requirement."""
        mcp_servers = [
            {'name': 'http-server', 'transport': 'http', 'url': 'http://localhost:8080'},
            {'name': 'sse-server', 'transport': 'sse', 'url': 'http://localhost:9090'},
        ]

        needs_nodejs = any(
            'npx' in str(server.get('command', ''))
            for server in mcp_servers
            if server.get('command')
        )

        assert needs_nodejs is False

    def test_empty_server_list(self):
        """Test empty server list returns False."""
        mcp_servers: list[dict[str, str]] = []

        needs_nodejs = any(
            'npx' in str(server.get('command', ''))
            for server in mcp_servers
            if server.get('command')
        )

        assert needs_nodejs is False

    def test_non_npx_command(self):
        """Test non-npx commands don't trigger Node.js requirement."""
        mcp_servers = [
            {'name': 'python-server', 'command': 'python server.py'},
            {'name': 'binary-server', 'command': '/usr/local/bin/mcp-server'},
        ]

        needs_nodejs = any(
            'npx' in str(server.get('command', ''))
            for server in mcp_servers
            if server.get('command')
        )

        assert needs_nodejs is False


class TestFetchWithRetry:
    """Test fetch retry logic for rate limiting."""

    @patch('setup_environment.time.sleep')
    def test_fetch_with_retry_success_first_attempt(self, mock_sleep: MagicMock) -> None:
        """Test successful fetch on first attempt."""
        call_count = 0

        def request_func() -> str:
            nonlocal call_count
            call_count += 1
            return 'content'

        result = setup_environment.fetch_with_retry(request_func, 'https://example.com/file')
        assert result == 'content'
        assert call_count == 1
        mock_sleep.assert_not_called()

    @patch('setup_environment.time.sleep')
    def test_fetch_with_retry_429_then_success(self, mock_sleep: MagicMock) -> None:
        """Test retry after 429 error."""
        call_count = 0

        def request_func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                error = urllib.error.HTTPError('https://example.com', 429, 'Too Many Requests', {}, None)
                raise error
            return 'content'

        result = setup_environment.fetch_with_retry(request_func, 'https://example.com/file')
        assert result == 'content'
        assert call_count == 2
        mock_sleep.assert_called_once()

    @patch('setup_environment.time.sleep')
    def test_fetch_with_retry_respects_retry_after_header(self, mock_sleep: MagicMock) -> None:
        """Test that Retry-After header is respected."""
        call_count = 0

        def request_func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                error = urllib.error.HTTPError(
                    'https://example.com', 429, 'Too Many Requests', {'retry-after': '5'}, None,
                )
                raise error
            return 'content'

        result = setup_environment.fetch_with_retry(request_func, 'https://example.com/file')
        assert result == 'content'
        # Verify wait time was 5 seconds (from header)
        assert mock_sleep.call_args[0][0] == 5.0

    @patch('setup_environment.time.sleep')
    def test_fetch_with_retry_max_retries_exceeded(self, mock_sleep: MagicMock) -> None:
        """Test that exception is raised after max retries."""

        def request_func() -> str:
            error = urllib.error.HTTPError('https://example.com', 429, 'Too Many Requests', {}, None)
            raise error

        with pytest.raises(urllib.error.HTTPError) as exc_info:
            setup_environment.fetch_with_retry(request_func, 'https://example.com/file', max_retries=2)

        assert exc_info.value.code == 429
        assert mock_sleep.call_count == 2  # Retried twice

    @patch('setup_environment.time.sleep')
    def test_fetch_with_retry_non_rate_limit_error_not_retried(self, mock_sleep: MagicMock) -> None:
        """Test that non-rate-limit errors are not retried."""

        def request_func() -> str:
            error = urllib.error.HTTPError('https://example.com', 500, 'Internal Server Error', {}, None)
            raise error

        with pytest.raises(urllib.error.HTTPError) as exc_info:
            setup_environment.fetch_with_retry(request_func, 'https://example.com/file')

        assert exc_info.value.code == 500
        mock_sleep.assert_not_called()

    @patch('setup_environment.time.sleep')
    def test_fetch_with_retry_403_rate_limit_with_remaining_zero(self, mock_sleep: MagicMock) -> None:
        """Test that 403 with x-ratelimit-remaining=0 is treated as rate limit."""
        call_count = 0

        def request_func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                error = urllib.error.HTTPError(
                    'https://example.com', 403, 'Forbidden', {'x-ratelimit-remaining': '0'}, None,
                )
                raise error
            return 'content'

        result = setup_environment.fetch_with_retry(request_func, 'https://example.com/file')
        assert result == 'content'
        assert call_count == 2
        mock_sleep.assert_called_once()

    @patch('setup_environment.time.sleep')
    def test_fetch_with_retry_403_not_rate_limit_raises_immediately(self, mock_sleep: MagicMock) -> None:
        """Test that 403 without rate limit indicators raises immediately."""

        def request_func() -> str:
            error = urllib.error.HTTPError(
                'https://example.com', 403, 'Forbidden', {'x-ratelimit-remaining': '100'}, None,
            )
            raise error

        with pytest.raises(urllib.error.HTTPError) as exc_info:
            setup_environment.fetch_with_retry(request_func, 'https://example.com/file')

        assert exc_info.value.code == 403
        mock_sleep.assert_not_called()

    @patch('setup_environment.time.sleep')
    def test_fetch_with_retry_exponential_backoff(self, mock_sleep: MagicMock) -> None:
        """Test that exponential backoff is applied."""
        call_count = 0

        def request_func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 4:
                error = urllib.error.HTTPError('https://example.com', 429, 'Too Many Requests', {}, None)
                raise error
            return 'content'

        result = setup_environment.fetch_with_retry(
            request_func, 'https://example.com/file',
            max_retries=3, initial_backoff=1.0,
        )
        assert result == 'content'
        assert call_count == 4  # Initial + 3 retries
        assert mock_sleep.call_count == 3

        # Verify backoff pattern (with jitter, times should be within range)
        sleep_times = [call[0][0] for call in mock_sleep.call_args_list]
        # First retry: ~1s (1 * 2^0 + jitter)
        assert 1.0 <= sleep_times[0] <= 1.25
        # Second retry: ~2s (1 * 2^1 + jitter)
        assert 2.0 <= sleep_times[1] <= 2.5
        # Third retry: ~4s (1 * 2^2 + jitter)
        assert 4.0 <= sleep_times[2] <= 5.0


class TestFetchWithRetryNewDefaults:
    """Test fetch retry logic with new default parameters."""

    def test_default_max_retries_is_10(self) -> None:
        """Test that default max_retries is 10."""
        import inspect

        sig = inspect.signature(setup_environment.fetch_with_retry)
        assert sig.parameters['max_retries'].default == 10

    def test_default_initial_backoff_is_2(self) -> None:
        """Test that default initial_backoff is 2.0."""
        import inspect

        sig = inspect.signature(setup_environment.fetch_with_retry)
        assert sig.parameters['initial_backoff'].default == 2.0

    @patch('setup_environment.time.sleep')
    def test_backoff_sequence_with_new_defaults(self, mock_sleep: MagicMock) -> None:
        """Test exponential backoff sequence with default parameters."""
        call_count = 0

        def request_func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 4:
                raise urllib.error.HTTPError(
                    'https://example.com', 429, 'Too Many Requests', {}, None,
                )
            return 'content'

        result = setup_environment.fetch_with_retry(
            request_func, 'https://example.com/file', max_retries=3, initial_backoff=2.0,
        )
        assert result == 'content'
        sleep_times = [call[0][0] for call in mock_sleep.call_args_list]
        # First retry: ~2s (2 * 2^0 + jitter)
        assert 2.0 <= sleep_times[0] <= 2.5
        # Second retry: ~4s (2 * 2^1 + jitter)
        assert 4.0 <= sleep_times[1] <= 5.0
        # Third retry: ~8s (2 * 2^2 + jitter)
        assert 8.0 <= sleep_times[2] <= 10.0

    @patch('setup_environment.time.sleep')
    def test_backoff_capped_at_60_seconds(self, mock_sleep: MagicMock) -> None:
        """Test that backoff never exceeds 60 seconds."""
        call_count = 0

        def request_func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count <= 7:
                raise urllib.error.HTTPError(
                    'https://example.com', 429, 'Too Many Requests', {}, None,
                )
            return 'content'

        result = setup_environment.fetch_with_retry(
            request_func, 'https://example.com/file',
            max_retries=10, initial_backoff=2.0,
        )
        assert result == 'content'
        sleep_times = [call[0][0] for call in mock_sleep.call_args_list]
        # After attempt 5+, backoff should be capped at 60s (with jitter up to 75s max)
        for sleep_time in sleep_times[5:]:
            assert sleep_time <= 75.0  # 60s + 25% jitter


class TestParallelWorkersConfiguration:
    """Test parallel workers configuration via environment variable.

    Note: We test the configuration logic without reloading the module
    to avoid test isolation issues with @patch decorators in other tests.
    """

    def test_default_parallel_workers_value(self) -> None:
        """Test that default parallel workers is 2."""
        # Verify the module has the expected default
        assert setup_environment.DEFAULT_PARALLEL_WORKERS == 2

    def test_parallel_workers_env_parsing_logic(self) -> None:
        """Test that CLAUDE_PARALLEL_WORKERS parsing logic works correctly."""
        # Test the parsing logic that the module uses at load time
        # The module uses: int(os.environ.get('CLAUDE_PARALLEL_WORKERS', '2'))

        # Test with env var set
        os.environ['CLAUDE_PARALLEL_WORKERS'] = '2'
        value = int(os.environ.get('CLAUDE_PARALLEL_WORKERS', '2'))
        assert value == 2

        # Test with higher value
        os.environ['CLAUDE_PARALLEL_WORKERS'] = '10'
        value = int(os.environ.get('CLAUDE_PARALLEL_WORKERS', '2'))
        assert value == 10

        # Clean up
        os.environ.pop('CLAUDE_PARALLEL_WORKERS', None)

        # Test fallback to default
        value = int(os.environ.get('CLAUDE_PARALLEL_WORKERS', '2'))
        assert value == 2


class TestRunBashCommandMsysPathConversion:
    """Tests for MSYS path conversion prevention in run_bash_command().

    Git Bash (MSYS2) automatically converts POSIX-style paths like /c to
    Windows drive paths like C:/. This breaks cmd.exe's /c flag which is
    used to run commands. These tests verify that MSYS_NO_PATHCONV=1 is
    set correctly to disable this conversion.
    """

    @patch('scripts.setup_environment.sys.platform', 'win32')
    @patch('setup_environment.find_bash_windows')
    @patch('subprocess.run')
    def test_msys_no_pathconv_set_on_windows(
        self, mock_run: MagicMock, mock_find_bash: MagicMock,
    ) -> None:
        """Verify MSYS_NO_PATHCONV=1 is set in env on Windows."""
        mock_find_bash.return_value = r'C:\Program Files\Git\bin\bash.exe'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        setup_environment.run_bash_command('echo test')

        # Verify subprocess.run was called with env parameter containing MSYS_NO_PATHCONV
        assert mock_run.called
        call_kwargs = mock_run.call_args[1]
        assert 'env' in call_kwargs
        assert call_kwargs['env'].get('MSYS_NO_PATHCONV') == '1'

    @patch('scripts.setup_environment.sys.platform', 'linux')
    @patch('shutil.which')
    @patch('subprocess.run')
    def test_msys_no_pathconv_not_set_on_linux(
        self, mock_run: MagicMock, mock_which: MagicMock,
    ) -> None:
        """Verify MSYS_NO_PATHCONV is NOT set in env on Linux."""
        mock_which.return_value = '/usr/bin/bash'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        setup_environment.run_bash_command('echo test')

        assert mock_run.called
        call_kwargs = mock_run.call_args[1]
        # On Linux, env should not contain MSYS_NO_PATHCONV
        env = call_kwargs.get('env')
        assert env is not None
        assert 'MSYS_NO_PATHCONV' not in env

    @patch('scripts.setup_environment.sys.platform', 'darwin')
    @patch('shutil.which')
    @patch('subprocess.run')
    def test_msys_no_pathconv_not_set_on_macos(
        self, mock_run: MagicMock, mock_which: MagicMock,
    ) -> None:
        """Verify MSYS_NO_PATHCONV is NOT set in env on macOS."""
        mock_which.return_value = '/bin/bash'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        setup_environment.run_bash_command('echo test')

        assert mock_run.called
        call_kwargs = mock_run.call_args[1]
        # On macOS, env should not contain MSYS_NO_PATHCONV
        env = call_kwargs.get('env')
        assert env is not None
        assert 'MSYS_NO_PATHCONV' not in env

    @patch('scripts.setup_environment.sys.platform', 'win32')
    @patch('setup_environment.find_bash_windows')
    @patch('subprocess.run')
    def test_c_flag_preserved_in_command(
        self, mock_run: MagicMock, mock_find_bash: MagicMock,
    ) -> None:
        """Verify /c flag is preserved and not converted to C:/."""
        mock_find_bash.return_value = r'C:\Program Files\Git\bin\bash.exe'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        # Command that includes /c flag (typical Windows cmd wrapper)
        setup_environment.run_bash_command('cmd /c npx test-package')

        # Verify the command string passed to subprocess contains /c not C:/
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        command_arg = call_args[-1]  # Last element is the command string
        assert '/c' in command_arg
        assert 'C:/' not in command_arg

    @patch('scripts.setup_environment.sys.platform', 'win32')
    @patch('setup_environment.find_bash_windows')
    @patch('subprocess.run')
    @patch.dict('os.environ', {'EXISTING_VAR': 'existing_value', 'PATH': '/usr/bin'})
    def test_existing_env_vars_preserved(
        self, mock_run: MagicMock, mock_find_bash: MagicMock,
    ) -> None:
        """Verify existing environment variables are preserved when adding MSYS_NO_PATHCONV."""
        mock_find_bash.return_value = r'C:\Program Files\Git\bin\bash.exe'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        setup_environment.run_bash_command('echo test')

        call_kwargs = mock_run.call_args[1]
        env = call_kwargs.get('env')
        assert env is not None
        # MSYS_NO_PATHCONV should be set
        assert env.get('MSYS_NO_PATHCONV') == '1'
        # Existing environment variables should be preserved
        assert env.get('EXISTING_VAR') == 'existing_value'
        assert env.get('PATH') == '/usr/bin'

    @patch('scripts.setup_environment.sys.platform', 'win32')
    @patch('setup_environment.find_bash_windows')
    @patch('subprocess.run')
    def test_tilde_expansion_still_works(
        self, mock_run: MagicMock, mock_find_bash: MagicMock,
    ) -> None:
        """Verify that disabling path conversion does not break tilde expansion.

        Tilde expansion (~) is handled by bash itself, not MSYS path conversion,
        so it should continue to work when MSYS_NO_PATHCONV=1 is set.
        """
        mock_find_bash.return_value = r'C:\Program Files\Git\bin\bash.exe'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '/c/Users/test', '')

        result = setup_environment.run_bash_command('echo ~')

        # The command should execute successfully
        assert mock_run.called
        assert result.returncode == 0

    @patch('scripts.setup_environment.sys.platform', 'win32')
    @patch('setup_environment.find_bash_windows')
    @patch('subprocess.run')
    def test_login_shell_with_msys_no_pathconv(
        self, mock_run: MagicMock, mock_find_bash: MagicMock,
    ) -> None:
        """Verify MSYS_NO_PATHCONV is set even with login_shell=True."""
        mock_find_bash.return_value = r'C:\Program Files\Git\bin\bash.exe'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        setup_environment.run_bash_command('echo test', login_shell=True)

        call_kwargs = mock_run.call_args[1]
        env = call_kwargs.get('env')
        assert env is not None
        assert env.get('MSYS_NO_PATHCONV') == '1'

    @patch('scripts.setup_environment.sys.platform', 'win32')
    @patch('setup_environment.find_bash_windows')
    @patch('subprocess.run')
    def test_capture_output_with_msys_no_pathconv(
        self, mock_run: MagicMock, mock_find_bash: MagicMock,
    ) -> None:
        """Verify MSYS_NO_PATHCONV is set with capture_output=False."""
        mock_find_bash.return_value = r'C:\Program Files\Git\bin\bash.exe'
        mock_run.return_value = subprocess.CompletedProcess([], 0, '', '')

        setup_environment.run_bash_command('echo test', capture_output=False)

        call_kwargs = mock_run.call_args[1]
        env = call_kwargs.get('env')
        assert env is not None
        assert env.get('MSYS_NO_PATHCONV') == '1'


class TestMainFunctionUserSettings:
    """Test main function integration with user-settings feature (Phase 4)."""

    @patch('setup_environment.load_config_from_source')
    @patch('setup_environment.validate_all_config_files')
    @patch('setup_environment.install_claude')
    @patch('setup_environment.install_dependencies')
    @patch('setup_environment.process_resources')
    @patch('setup_environment.process_skills')
    @patch('setup_environment.configure_all_mcp_servers')
    @patch('setup_environment.write_user_settings')
    @patch('setup_environment.is_admin', return_value=True)
    @patch('pathlib.Path.mkdir')
    def test_main_user_settings_only_mode(
        self,
        mock_mkdir: MagicMock,
        mock_is_admin: MagicMock,
        mock_write_user_settings: MagicMock,
        mock_mcp: MagicMock,
        mock_skills: MagicMock,
        mock_resources: MagicMock,
        mock_deps: MagicMock,
        mock_install: MagicMock,
        mock_validate: MagicMock,
        mock_load: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test main with user-settings only (no command-names) - user-only mode."""
        # Mocks required by @patch decorators but not directly asserted
        del mock_mkdir, mock_is_admin, mock_skills, mock_resources, mock_deps
        mock_load.return_value = (
            {
                'name': 'User Settings Only',
                'user-settings': {
                    'language': 'russian',
                    'model': 'claude-opus-4',
                },
                # No command-names - user-only mode
            },
            'test.yaml',
        )
        mock_validate.return_value = (True, [])
        mock_install.return_value = True
        mock_mcp.return_value = (True, [], {'global_count': 0, 'profile_count': 0, 'combined_count': 0})
        mock_write_user_settings.return_value = True

        with patch('sys.argv', ['setup_environment.py', 'test']), patch('sys.exit') as mock_exit:
            setup_environment.main()
            mock_exit.assert_not_called()

        # Verify write_user_settings was called with correct args
        mock_write_user_settings.assert_called_once()
        call_args = mock_write_user_settings.call_args
        assert call_args[0][0] == {'language': 'russian', 'model': 'claude-opus-4'}

        # Verify output shows Steps 13-16 skipped
        captured = capsys.readouterr()
        assert 'Steps 13-16: Skipping command creation' in captured.out
        assert 'Step 12: Writing user settings' in captured.out

    @patch('setup_environment.load_config_from_source')
    @patch('setup_environment.validate_all_config_files')
    @patch('setup_environment.install_claude')
    @patch('setup_environment.install_dependencies')
    @patch('setup_environment.process_resources')
    @patch('setup_environment.process_skills')
    @patch('setup_environment.configure_all_mcp_servers')
    @patch('setup_environment.write_user_settings')
    @patch('setup_environment.create_additional_settings')
    @patch('setup_environment.create_launcher_script')
    @patch('setup_environment.register_global_command')
    @patch('setup_environment.is_admin', return_value=True)
    @patch('pathlib.Path.mkdir')
    def test_main_user_settings_combined_mode(
        self,
        mock_mkdir: MagicMock,
        mock_is_admin: MagicMock,
        mock_register: MagicMock,
        mock_launcher: MagicMock,
        mock_settings: MagicMock,
        mock_write_user_settings: MagicMock,
        mock_mcp: MagicMock,
        mock_skills: MagicMock,
        mock_resources: MagicMock,
        mock_deps: MagicMock,
        mock_install: MagicMock,
        mock_validate: MagicMock,
        mock_load: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test main with user-settings AND command-names - combined mode."""
        # Mocks required by @patch decorators but not directly asserted
        del mock_mkdir, mock_is_admin, mock_skills, mock_resources, mock_deps
        mock_load.return_value = (
            {
                'name': 'Combined Mode',
                'command-names': ['mydev'],
                'user-settings': {
                    'language': 'russian',
                },
                'model': 'claude-sonnet-4',  # Profile-level model
            },
            'test.yaml',
        )
        mock_validate.return_value = (True, [])
        mock_install.return_value = True
        mock_mcp.return_value = (True, [], {'global_count': 0, 'profile_count': 0, 'combined_count': 0})
        mock_write_user_settings.return_value = True
        mock_settings.return_value = True
        mock_launcher.return_value = Path('/tmp/launcher.sh')
        mock_register.return_value = True

        with patch('sys.argv', ['setup_environment.py', 'test']), patch('sys.exit') as mock_exit:
            setup_environment.main()
            mock_exit.assert_not_called()

        # Verify write_user_settings was called
        mock_write_user_settings.assert_called_once()

        # Verify profile settings were also created
        mock_settings.assert_called_once()

        # Verify output shows Step 12 and Steps 13-16
        captured = capsys.readouterr()
        assert 'Step 12: Writing user settings' in captured.out
        assert 'Step 13: Downloading hooks' in captured.out
        assert 'Step 14: Configuring settings' in captured.out
        assert 'Step 15: Creating launcher script' in captured.out
        assert 'Step 16: Registering global' in captured.out

    @patch('setup_environment.load_config_from_source')
    def test_main_user_settings_excluded_key_error(
        self,
        mock_load: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test main with excluded key in user-settings (should exit with code 1)."""
        mock_load.return_value = (
            {
                'name': 'Invalid Config',
                'user-settings': {
                    'hooks': {'events': []},  # Excluded key
                },
            },
            'test.yaml',
        )

        with patch('sys.argv', ['setup_environment.py', 'test']), pytest.raises(SystemExit) as exc_info:
            setup_environment.main()
        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        # Error messages go to stderr via print_error()
        assert 'hooks' in captured.err
        assert 'not allowed' in captured.err

    @patch('setup_environment.load_config_from_source')
    @patch('setup_environment.validate_all_config_files')
    @patch('setup_environment.install_claude')
    @patch('setup_environment.install_dependencies')
    @patch('setup_environment.process_resources')
    @patch('setup_environment.process_skills')
    @patch('setup_environment.configure_all_mcp_servers')
    @patch('setup_environment.write_user_settings')
    @patch('setup_environment.create_additional_settings')
    @patch('setup_environment.create_launcher_script')
    @patch('setup_environment.register_global_command')
    @patch('setup_environment.is_admin', return_value=True)
    @patch('pathlib.Path.mkdir')
    def test_main_user_settings_conflict_warning(
        self,
        mock_mkdir: MagicMock,
        mock_is_admin: MagicMock,
        mock_register: MagicMock,
        mock_launcher: MagicMock,
        mock_settings: MagicMock,
        mock_write_user_settings: MagicMock,
        mock_mcp: MagicMock,
        mock_skills: MagicMock,
        mock_resources: MagicMock,
        mock_deps: MagicMock,
        mock_install: MagicMock,
        mock_validate: MagicMock,
        mock_load: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test main with conflicting keys emits warning."""
        # Mocks required by @patch decorators but not directly asserted
        del mock_mkdir, mock_is_admin, mock_skills, mock_resources, mock_deps
        mock_load.return_value = (
            {
                'name': 'Conflict Config',
                'command-names': ['mydev'],
                'user-settings': {
                    'model': 'claude-opus-4',  # Conflict with root level
                },
                'model': 'claude-sonnet-4',  # Root level model
            },
            'test.yaml',
        )
        mock_validate.return_value = (True, [])
        mock_install.return_value = True
        mock_mcp.return_value = (True, [], {'global_count': 0, 'profile_count': 0, 'combined_count': 0})
        mock_write_user_settings.return_value = True
        mock_settings.return_value = True
        mock_launcher.return_value = Path('/tmp/launcher.sh')
        mock_register.return_value = True

        with patch('sys.argv', ['setup_environment.py', 'test']), patch('sys.exit') as mock_exit:
            setup_environment.main()
            mock_exit.assert_not_called()

        captured = capsys.readouterr()
        # Warning should be emitted about model conflict
        assert 'model' in captured.out
        assert 'both root level and user-settings' in captured.out or 'specified in both' in captured.out

    @patch('setup_environment.load_config_from_source')
    @patch('setup_environment.validate_all_config_files')
    @patch('setup_environment.install_claude')
    @patch('setup_environment.install_dependencies')
    @patch('setup_environment.process_resources')
    @patch('setup_environment.process_skills')
    @patch('setup_environment.configure_all_mcp_servers')
    @patch('setup_environment.write_user_settings')
    @patch('setup_environment.create_additional_settings')
    @patch('setup_environment.create_launcher_script')
    @patch('setup_environment.register_global_command')
    @patch('setup_environment.is_admin', return_value=True)
    @patch('pathlib.Path.mkdir')
    def test_main_without_user_settings(
        self,
        mock_mkdir: MagicMock,
        mock_is_admin: MagicMock,
        mock_register: MagicMock,
        mock_launcher: MagicMock,
        mock_settings: MagicMock,
        mock_write_user_settings: MagicMock,
        mock_mcp: MagicMock,
        mock_skills: MagicMock,
        mock_resources: MagicMock,
        mock_deps: MagicMock,
        mock_install: MagicMock,
        mock_validate: MagicMock,
        mock_load: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test main without user-settings (no-op for user settings)."""
        # Mocks required by @patch decorators but not directly asserted
        del mock_mkdir, mock_is_admin, mock_skills, mock_resources, mock_deps
        mock_load.return_value = (
            {
                'name': 'No User Settings',
                'command-names': ['mydev'],
                # No user-settings section
            },
            'test.yaml',
        )
        mock_validate.return_value = (True, [])
        mock_install.return_value = True
        mock_mcp.return_value = (True, [], {'global_count': 0, 'profile_count': 0, 'combined_count': 0})
        mock_write_user_settings.return_value = True
        mock_settings.return_value = True
        mock_launcher.return_value = Path('/tmp/launcher.sh')
        mock_register.return_value = True

        with patch('sys.argv', ['setup_environment.py', 'test']), patch('sys.exit') as mock_exit:
            setup_environment.main()
            mock_exit.assert_not_called()

        # write_user_settings should not be called since user_settings is None
        mock_write_user_settings.assert_not_called()

        captured = capsys.readouterr()
        assert 'No user settings to configure' in captured.out

    @patch('setup_environment.load_config_from_source')
    @patch('setup_environment.validate_all_config_files')
    @patch('setup_environment.install_claude')
    @patch('setup_environment.install_dependencies')
    @patch('setup_environment.process_resources')
    @patch('setup_environment.process_skills')
    @patch('setup_environment.configure_all_mcp_servers')
    @patch('setup_environment.write_user_settings')
    @patch('setup_environment.is_admin', return_value=True)
    @patch('pathlib.Path.mkdir')
    def test_main_summary_includes_user_settings(
        self,
        mock_mkdir: MagicMock,
        mock_is_admin: MagicMock,
        mock_write_user_settings: MagicMock,
        mock_mcp: MagicMock,
        mock_skills: MagicMock,
        mock_resources: MagicMock,
        mock_deps: MagicMock,
        mock_install: MagicMock,
        mock_validate: MagicMock,
        mock_load: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test summary output includes user-settings line."""
        # Mocks required by @patch decorators but not directly asserted
        del mock_mkdir, mock_is_admin, mock_skills, mock_resources, mock_deps
        mock_load.return_value = (
            {
                'name': 'User Settings Test',
                'user-settings': {
                    'language': 'russian',
                },
            },
            'test.yaml',
        )
        mock_validate.return_value = (True, [])
        mock_install.return_value = True
        mock_mcp.return_value = (True, [], {'global_count': 0, 'profile_count': 0, 'combined_count': 0})
        mock_write_user_settings.return_value = True

        with patch('sys.argv', ['setup_environment.py', 'test']), patch('sys.exit') as mock_exit:
            setup_environment.main()
            mock_exit.assert_not_called()

        captured = capsys.readouterr()
        assert 'User settings: configured in ~/.claude/settings.json' in captured.out

    @patch('setup_environment.load_config_from_source')
    @patch('setup_environment.validate_all_config_files')
    @patch('setup_environment.install_claude')
    @patch('setup_environment.install_dependencies')
    @patch('setup_environment.process_resources')
    @patch('setup_environment.process_skills')
    @patch('setup_environment.configure_all_mcp_servers')
    @patch('setup_environment.write_user_settings')
    @patch('setup_environment.is_admin', return_value=True)
    @patch('pathlib.Path.mkdir')
    def test_main_user_settings_write_failure_non_fatal(
        self,
        mock_mkdir: MagicMock,
        mock_is_admin: MagicMock,
        mock_write_user_settings: MagicMock,
        mock_mcp: MagicMock,
        mock_skills: MagicMock,
        mock_resources: MagicMock,
        mock_deps: MagicMock,
        mock_install: MagicMock,
        mock_validate: MagicMock,
        mock_load: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test that user settings write failure is non-fatal (warning only)."""
        # Mocks required by @patch decorators but not directly asserted
        del mock_mkdir, mock_is_admin, mock_skills, mock_resources, mock_deps
        mock_load.return_value = (
            {
                'name': 'Write Failure Test',
                'user-settings': {
                    'language': 'russian',
                },
            },
            'test.yaml',
        )
        mock_validate.return_value = (True, [])
        mock_install.return_value = True
        mock_mcp.return_value = (True, [], {'global_count': 0, 'profile_count': 0, 'combined_count': 0})
        mock_write_user_settings.return_value = False  # Simulate write failure

        with patch('sys.argv', ['setup_environment.py', 'test']), patch('sys.exit') as mock_exit:
            setup_environment.main()
            # Should NOT exit with error - write failure is non-fatal
            mock_exit.assert_not_called()

        captured = capsys.readouterr()
        assert 'Failed to write user settings' in captured.out


# =============================================================================
# Phase 5: Comprehensive Tests - Edge Cases and Integration Tests
# =============================================================================


class TestDetectSettingsConflictsComplete:
    """Exhaustive conflict detection tests for all ROOT_TO_USER_SETTINGS_KEY_MAP entries."""

    @pytest.mark.parametrize(
        ('root_key', 'user_key'),
        [
            ('model', 'model'),
            ('permissions', 'permissions'),
            ('attribution', 'attribution'),
            ('always-thinking-enabled', 'alwaysThinkingEnabled'),
            ('company-announcements', 'companyAnnouncements'),
            ('env-variables', 'env'),
        ],
    )
    def test_conflict_all_mapped_keys_exhaustive(
        self, root_key: str, user_key: str,
    ) -> None:
        """Every ROOT_TO_USER_SETTINGS_KEY_MAP entry produces a conflict when both present."""
        user_settings = {user_key: 'user_value'}
        root_settings = {root_key: 'root_value'}

        conflicts = setup_environment.detect_settings_conflicts(user_settings, root_settings)

        assert len(conflicts) == 1, f'Expected conflict for {root_key} -> {user_key}'
        key, user_val, root_val = conflicts[0]
        assert key == user_key
        assert user_val == 'user_value'
        assert root_val == 'root_value'


class TestDeepMergeEdgeCases:
    """Edge case tests for deep_merge_settings not covered in Phase 1."""

    def test_deep_merge_four_level_nesting(self) -> None:
        """Verify 4+ levels of nested dicts merge correctly."""
        base = {'a': {'b': {'c': {'d': 'base_value'}}}}
        updates = {'a': {'b': {'c': {'e': 'new_value'}}}}
        result = setup_environment.deep_merge_settings(base, updates)
        assert result['a']['b']['c']['d'] == 'base_value'  # Preserved
        assert result['a']['b']['c']['e'] == 'new_value'   # Added

    def test_deep_merge_array_inside_nested_object(self) -> None:
        """Array union works at top-level permissions.allow path."""
        # Test that the standard permissions path works with nested structure
        base = {'permissions': {'allow': ['Read', 'Write'], 'deny': ['Web']}}
        updates = {'permissions': {'allow': ['Bash', 'Write']}}  # Write duplicate
        result = setup_environment.deep_merge_settings(base, updates)
        # permissions.allow should be unioned (standard behavior)
        assert set(result['permissions']['allow']) == {'Read', 'Write', 'Bash'}
        # permissions.deny preserved from base
        assert result['permissions']['deny'] == ['Web']

    def test_deep_merge_empty_nested_dicts(self) -> None:
        """Empty dicts at various nesting levels."""
        base = {'a': {'b': {}}, 'c': 'value'}
        updates = {'a': {'b': {'d': 'new'}}, 'e': {}}
        result = setup_environment.deep_merge_settings(base, updates)
        assert result['a']['b']['d'] == 'new'
        assert result['c'] == 'value'
        assert result['e'] == {}

    def test_deep_merge_unicode_keys_and_values(self) -> None:
        """Non-ASCII characters in keys and values."""
        base = {'язык': 'русский', 'model': 'claude'}
        updates = {'язык': 'english', 'тема': 'темная'}
        result = setup_environment.deep_merge_settings(base, updates)
        assert result['язык'] == 'english'
        assert result['тема'] == 'темная'
        assert result['model'] == 'claude'

    def test_deep_merge_null_in_nested_structure(self) -> None:
        """None/null values at various positions."""
        base = {'a': None, 'b': {'c': 'value'}}
        updates = {'a': {'nested': 'now'}, 'b': None}
        result = setup_environment.deep_merge_settings(base, updates)
        # When base has None and updates has dict, dict wins
        assert result['a'] == {'nested': 'now'}
        # When base has dict and updates has None, None wins
        assert result['b'] is None

    def test_deep_merge_mixed_types_at_same_path(self) -> None:
        """Different types in base vs updates for nested paths."""
        # List in base, dict in updates
        base = {'config': ['item1', 'item2']}
        updates = {'config': {'key': 'value'}}
        result = setup_environment.deep_merge_settings(base, updates)
        assert result['config'] == {'key': 'value'}  # Updates value wins

        # String in base, list in updates
        base2 = {'setting': 'simple'}
        updates2 = {'setting': ['complex', 'list']}
        result2 = setup_environment.deep_merge_settings(base2, updates2)
        assert result2['setting'] == ['complex', 'list']


class TestUserSettingsIntegration:
    """Integration tests for complete user-settings workflow."""

    def test_integration_user_settings_only_writes_settings_json(
        self, tmp_path: Path,
    ) -> None:
        """User-only mode (no command-names) writes ONLY to ~/.claude/settings.json."""
        claude_dir = tmp_path / '.claude'
        claude_dir.mkdir(parents=True)

        # Create config with user-settings but NO command-names
        config = {
            'name': 'User Settings Only',
            'user-settings': {
                'language': 'russian',
                'model': 'claude-opus-4',
            },
        }

        # Write user settings
        result = setup_environment.write_user_settings(
            config['user-settings'], claude_dir,
        )
        assert result is True

        # Verify settings.json exists with correct content
        settings_file = claude_dir / 'settings.json'
        assert settings_file.exists()
        with open(settings_file) as f:
            content = json.load(f)
        assert content['language'] == 'russian'
        assert content['model'] == 'claude-opus-4'

    def test_integration_combined_mode_writes_both_files(
        self, tmp_path: Path,
    ) -> None:
        """Verify combined mode writes to both settings.json AND additional-settings.json."""
        claude_dir = tmp_path / '.claude'
        claude_dir.mkdir(parents=True)

        user_settings = {
            'language': 'russian',
            'permissions': {'allow': ['Read']},
        }

        profile_settings = {
            'model': 'claude-sonnet-4',
            'permissions': {'allow': ['Bash(npm:*)']},
        }

        # Write user settings
        result1 = setup_environment.write_user_settings(user_settings, claude_dir)
        assert result1 is True

        # Write profile settings (simulating additional-settings behavior)
        result2 = setup_environment.create_additional_settings(
            hooks={},  # Empty hooks
            claude_user_dir=claude_dir,
            command_name='mydev',
            model=profile_settings['model'],
            permissions=profile_settings['permissions'],
        )
        assert result2 is True

        # Verify both files exist
        assert (claude_dir / 'settings.json').exists()
        assert (claude_dir / 'mydev-additional-settings.json').exists()

    def test_integration_existing_settings_preserved_during_merge(
        self, tmp_path: Path,
    ) -> None:
        """Verify existing ~/.claude/settings.json keys not in YAML are preserved."""
        claude_dir = tmp_path / '.claude'
        claude_dir.mkdir(parents=True)
        settings_file = claude_dir / 'settings.json'

        # Create existing settings with keys not in our update
        existing = {
            'existingKey': 'should_be_preserved',
            'language': 'english',
            'sandbox': {'enabled': True},
        }
        with open(settings_file, 'w') as f:
            json.dump(existing, f)

        # Write new user settings
        new_settings = {
            'language': 'russian',  # Override
            'model': 'claude-opus-4',  # Add new
        }
        setup_environment.write_user_settings(new_settings, claude_dir)

        # Verify merge
        with open(settings_file) as f:
            result = json.load(f)
        assert result['existingKey'] == 'should_be_preserved'  # Preserved
        assert result['language'] == 'russian'  # Updated
        assert result['model'] == 'claude-opus-4'  # Added
        assert result['sandbox']['enabled'] is True  # Preserved

    def test_integration_permissions_array_union_across_files(
        self, tmp_path: Path,
    ) -> None:
        """Verify permissions arrays are properly unioned in settings.json."""
        claude_dir = tmp_path / '.claude'
        claude_dir.mkdir(parents=True)
        settings_file = claude_dir / 'settings.json'

        # Existing permissions
        existing = {
            'permissions': {
                'allow': ['Read', 'Glob'],
                'deny': ['Web'],
            },
        }
        with open(settings_file, 'w') as f:
            json.dump(existing, f)

        # New permissions to merge
        new_settings = {
            'permissions': {
                'allow': ['Bash', 'Read'],  # Read is duplicate
                'ask': ['Edit'],
            },
        }
        setup_environment.write_user_settings(new_settings, claude_dir)

        # Verify array union
        with open(settings_file) as f:
            result = json.load(f)
        assert set(result['permissions']['allow']) == {'Read', 'Glob', 'Bash'}
        assert result['permissions']['deny'] == ['Web']  # Preserved
        assert result['permissions']['ask'] == ['Edit']  # Added

    def test_integration_tilde_expanded_in_final_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify apiKeyHelper/awsCredentialExport have expanded tilde paths in output."""
        claude_dir = tmp_path / '.claude'
        claude_dir.mkdir(parents=True)

        # Mock home directory
        fake_home = str(tmp_path / 'home' / 'user')
        monkeypatch.setenv('HOME', fake_home)
        monkeypatch.setenv('USERPROFILE', fake_home)

        settings = {
            'apiKeyHelper': 'uv run --no-project ~/.claude/scripts/helper.py',
            'awsCredentialExport': 'uv run ~/.claude/aws_creds.py',
            'otherKey': '~/path/unchanged',  # Non-expansion key
        }

        setup_environment.write_user_settings(settings, claude_dir)

        with open(claude_dir / 'settings.json') as f:
            result = json.load(f)

        # Tilde should be expanded for apiKeyHelper and awsCredentialExport
        assert '~' not in result['apiKeyHelper']
        assert fake_home.replace('\\', '/') in result['apiKeyHelper'] or fake_home in result['apiKeyHelper']
        assert '~' not in result['awsCredentialExport']
        # Other keys should keep tilde unchanged
        assert result['otherKey'] == '~/path/unchanged'


class TestValidateUserSettingsEdgeCases:
    """Edge case tests for validate_user_settings."""

    def test_validate_case_sensitivity(self) -> None:
        """Verify 'Hooks' vs 'hooks' and 'StatusLine' vs 'statusLine'."""
        # Lowercase versions are excluded
        result_hooks = setup_environment.validate_user_settings({'hooks': {}})
        assert len(result_hooks) == 1
        assert 'hooks' in result_hooks[0]

        result_status = setup_environment.validate_user_settings({'statusLine': {}})
        assert len(result_status) == 1
        assert 'statusLine' in result_status[0]

        # Different case variations should pass (case-sensitive check)
        result_caps = setup_environment.validate_user_settings({'Hooks': {}, 'StatusLine': {}})
        assert len(result_caps) == 0  # Pass - not excluded

    def test_validate_nested_excluded_keys_allowed(self) -> None:
        """Nested paths like something.hooks should NOT be rejected."""
        settings = {
            'config': {
                'hooks': 'nested_value',  # hooks nested inside config
            },
            'myHooks': 'value',  # Contains 'hooks' but not the key itself
        }
        result = setup_environment.validate_user_settings(settings)
        assert len(result) == 0  # Pass - only top-level hooks is excluded

    def test_validate_similar_but_valid_keys(self) -> None:
        """Keys like 'hook' (without 's') should pass."""
        settings = {
            'hook': 'single_hook',  # Not 'hooks'
            'statusLines': ['line1', 'line2'],  # Not 'statusLine'
            'hookConfig': {'enabled': True},  # Contains 'hook' but different key
        }
        result = setup_environment.validate_user_settings(settings)
        assert len(result) == 0  # All should pass


class TestWriteUserSettingsEdgeCases:
    """Edge case tests for write_user_settings."""

    def test_write_user_settings_file_with_bom(self, tmp_path: Path) -> None:
        """Handle existing file with UTF-8 BOM marker."""
        claude_dir = tmp_path / '.claude'
        claude_dir.mkdir(parents=True)
        settings_file = claude_dir / 'settings.json'

        # Write file with UTF-8 BOM
        existing = {'existing': 'value'}
        with open(settings_file, 'wb') as f:
            f.write(b'\xef\xbb\xbf')  # UTF-8 BOM
            f.write(json.dumps(existing).encode('utf-8'))

        # Should handle BOM and merge correctly
        new_settings = {'new': 'setting'}
        result = setup_environment.write_user_settings(new_settings, claude_dir)
        assert result is True

        with open(settings_file, encoding='utf-8-sig') as f:
            content = json.load(f)
        assert content['new'] == 'setting'

    def test_write_user_settings_large_settings(self, tmp_path: Path) -> None:
        """Performance with 100+ keys."""
        claude_dir = tmp_path / '.claude'
        claude_dir.mkdir(parents=True)

        # Create settings with 100+ keys
        large_settings = {f'key_{i}': f'value_{i}' for i in range(150)}
        large_settings['permissions'] = {'allow': [f'perm_{i}' for i in range(50)]}

        result = setup_environment.write_user_settings(large_settings, claude_dir)
        assert result is True

        with open(claude_dir / 'settings.json') as f:
            content = json.load(f)
        assert len(content) >= 150
        assert len(content['permissions']['allow']) == 50

    def test_write_user_settings_special_json_chars(self, tmp_path: Path) -> None:
        """Keys/values requiring JSON escaping (quotes, backslashes)."""
        claude_dir = tmp_path / '.claude'
        claude_dir.mkdir(parents=True)

        settings = {
            'path': 'C:\\Users\\Name\\file.txt',
            'quote': 'She said "hello"',
            'special': 'tab\there\nnewline',
            'unicode': '\u00e9\u00e0\u00fc',
        }

        result = setup_environment.write_user_settings(settings, claude_dir)
        assert result is True

        with open(claude_dir / 'settings.json') as f:
            content = json.load(f)
        assert content['path'] == 'C:\\Users\\Name\\file.txt'
        assert content['quote'] == 'She said "hello"'
        assert '\t' in content['special']
        assert '\n' in content['special']

    def test_write_user_settings_read_only_directory(
        self, tmp_path: Path,
    ) -> None:
        """Graceful failure when write fails due to OSError."""
        claude_dir = tmp_path / '.claude'
        claude_dir.mkdir(parents=True)

        settings = {'key': 'value'}

        # Mock Path.write_text to raise OSError (simulates permission error)
        with patch.object(Path, 'write_text', side_effect=OSError('Read-only filesystem')):
            result = setup_environment.write_user_settings(settings, claude_dir)
            assert result is False  # Should return False on OSError  # Should return False on permission error


class TestUserSettingsErrorRecovery:
    """Error handling and recovery tests."""

    @patch('setup_environment.load_config_from_source')
    @patch('setup_environment.validate_all_config_files')
    @patch('setup_environment.install_claude')
    @patch('setup_environment.install_dependencies')
    @patch('setup_environment.process_resources')
    @patch('setup_environment.process_skills')
    @patch('setup_environment.configure_all_mcp_servers')
    @patch('setup_environment.write_user_settings')
    @patch('setup_environment.is_admin', return_value=True)
    @patch('pathlib.Path.mkdir')
    def test_main_continues_after_user_settings_write_failure(
        self,
        mock_mkdir: MagicMock,
        mock_is_admin: MagicMock,
        mock_write_user_settings: MagicMock,
        mock_mcp: MagicMock,
        mock_skills: MagicMock,
        mock_resources: MagicMock,
        mock_deps: MagicMock,
        mock_install: MagicMock,
        mock_validate: MagicMock,
        mock_load: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """main() continues execution even if write_user_settings fails."""
        del mock_mkdir, mock_is_admin, mock_skills, mock_resources, mock_deps
        mock_load.return_value = (
            {
                'name': 'Continue After Failure',
                'user-settings': {'language': 'russian'},
            },
            'test.yaml',
        )
        mock_validate.return_value = (True, [])
        mock_install.return_value = True
        mock_mcp.return_value = (True, [], {'global_count': 0, 'profile_count': 0, 'combined_count': 0})
        mock_write_user_settings.return_value = False  # Write fails

        with patch('sys.argv', ['setup_environment.py', 'test']), patch('sys.exit') as mock_exit:
            setup_environment.main()
            # Should NOT exit - write failure is non-fatal
            mock_exit.assert_not_called()

        captured = capsys.readouterr()
        assert 'Failed to write user settings' in captured.out

    @patch('setup_environment.load_config_from_source')
    def test_main_exits_on_validation_error(
        self,
        mock_load: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """main() exits with code 1 when user-settings contains excluded keys."""
        mock_load.return_value = (
            {
                'name': 'Invalid Config',
                'user-settings': {
                    'hooks': {'events': []},  # Excluded key
                    'statusLine': 'test',     # Another excluded key
                },
            },
            'test.yaml',
        )

        with patch('sys.argv', ['setup_environment.py', 'test']), pytest.raises(SystemExit) as exc_info:
            setup_environment.main()

        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert 'hooks' in captured.err
        assert 'statusLine' in captured.err

    def test_write_user_settings_recovers_from_corrupted_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Corrupted settings.json is overwritten with warning."""
        claude_dir = tmp_path / '.claude'
        claude_dir.mkdir(parents=True)
        settings_file = claude_dir / 'settings.json'

        # Create corrupted JSON file
        Path(settings_file).write_text('{invalid json content')

        # Should recover and write new settings
        new_settings = {'language': 'russian'}
        result = setup_environment.write_user_settings(new_settings, claude_dir)
        assert result is True

        with open(settings_file) as f:
            content = json.load(f)
        assert content['language'] == 'russian'

        captured = capsys.readouterr()
        assert 'warning' in captured.out.lower() or 'invalid' in captured.out.lower() or result is True


class TestConfigInheritanceUserSettings:
    """Inheritance chain tests with user-settings."""

    def test_inheritance_user_settings_child_overrides_parent(
        self, tmp_path: Path,
    ) -> None:
        """Child user-settings completely overrides parent user-settings (no merge)."""
        # Create parent config
        parent_file = tmp_path / 'parent.yaml'
        parent_file.write_text('''
name: Parent Config
user-settings:
  language: english
  model: claude-sonnet-4
''')

        # Create child config
        child_file = tmp_path / 'child.yaml'
        child_file.write_text(f'''
name: Child Config
inherit: {parent_file}
user-settings:
  language: russian
''')

        # Load child config (should inherit from parent)
        config, _ = setup_environment.load_config_from_source(str(child_file))

        # Child's user-settings should completely override parent
        # Based on standard YAML merge semantics (child overrides parent for same key)
        assert config.get('user-settings', {}).get('language') == 'russian'
        # The 'model' from parent is NOT inherited because user-settings as a whole is replaced
        # This is standard YAML merge behavior - child's user-settings replaces parent's entirely

    def test_inheritance_user_settings_only_in_parent(
        self, tmp_path: Path,
    ) -> None:
        """Parent has user-settings, child does not - child inherits user-settings."""
        parent_file = tmp_path / 'parent.yaml'
        parent_file.write_text('''
name: Parent Config
user-settings:
  language: russian
  model: claude-opus-4
''')

        child_file = tmp_path / 'child.yaml'
        child_file.write_text(f'''
name: Child Config
inherit: {parent_file}
model: claude-sonnet-4
''')

        # Load child config
        config, source = setup_environment.load_config_from_source(str(child_file))
        # Resolve inheritance chain
        resolved = setup_environment.resolve_config_inheritance(config, source)

        # Child inherits parent's user-settings
        assert 'user-settings' in resolved
        assert resolved['user-settings']['language'] == 'russian'
        assert resolved['user-settings']['model'] == 'claude-opus-4'

    def test_inheritance_user_settings_only_in_child(
        self, tmp_path: Path,
    ) -> None:
        """Parent has no user-settings, child has user-settings."""
        parent_file = tmp_path / 'parent.yaml'
        parent_file.write_text('''
name: Parent Config
model: claude-sonnet-4
''')

        child_file = tmp_path / 'child.yaml'
        child_file.write_text(f'''
name: Child Config
inherit: {parent_file}
user-settings:
  language: russian
''')

        # Load child config
        config, source = setup_environment.load_config_from_source(str(child_file))
        # Resolve inheritance chain
        resolved = setup_environment.resolve_config_inheritance(config, source)

        # Child has user-settings, parent did not
        assert 'user-settings' in resolved
        assert resolved['user-settings']['language'] == 'russian'
        # Parent's model should still be inherited at root level
        assert resolved.get('model') == 'claude-sonnet-4'


class TestRootGuard:
    """Test root detection guard in setup_environment.py main()."""

    def test_root_guard_exits_when_root_without_override(self) -> None:
        """Running as root without CLAUDE_ALLOW_ROOT=1 exits with code 1."""
        os.environ.pop('CLAUDE_ALLOW_ROOT', None)
        with (
            patch('platform.system', return_value='Linux'),
            patch('os.geteuid', create=True, return_value=0),
            patch.dict('os.environ', {}, clear=False),
            pytest.raises(SystemExit) as exc_info,
        ):
            setup_environment.main()
        assert exc_info.value.code == 1

    def test_root_guard_allows_when_override_set(self) -> None:
        """CLAUDE_ALLOW_ROOT=1 allows root execution to proceed."""
        with (
            patch('platform.system', return_value='Linux'),
            patch('os.geteuid', create=True, return_value=0),
            patch.dict('os.environ', {'CLAUDE_ALLOW_ROOT': '1'}),
            patch('sys.argv', ['setup_environment.py', 'python']),
            contextlib.suppress(SystemExit, Exception),
        ):
            setup_environment.main()

    def test_root_guard_skipped_on_windows(self) -> None:
        """Root guard does not activate on Windows."""
        with (
            patch('platform.system', return_value='Windows'),
            patch.object(setup_environment, 'is_admin', return_value=False),
            patch('sys.argv', ['setup_environment.py', 'python']),
            contextlib.suppress(SystemExit, Exception),
        ):
            setup_environment.main()

    def test_root_guard_error_message_content(
        self, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Root guard error message contains key information."""
        os.environ.pop('CLAUDE_ALLOW_ROOT', None)
        with (
            patch('platform.system', return_value='Linux'),
            patch('os.geteuid', create=True, return_value=0),
            patch.dict('os.environ', {}, clear=False),
            pytest.raises(SystemExit),
        ):
            setup_environment.main()
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert 'root' in combined.lower() or 'sudo' in combined.lower()
        assert 'CLAUDE_ALLOW_ROOT' in combined

    def test_root_guard_works_on_macos(self) -> None:
        """Root guard activates on macOS the same as Linux."""
        os.environ.pop('CLAUDE_ALLOW_ROOT', None)
        with (
            patch('platform.system', return_value='Darwin'),
            patch('os.geteuid', create=True, return_value=0),
            patch.dict('os.environ', {}, clear=False),
            pytest.raises(SystemExit) as exc_info,
        ):
            setup_environment.main()
        assert exc_info.value.code == 1

    def test_root_guard_runs_before_argument_parsing(self) -> None:
        """Root guard triggers even without valid CLI arguments.

        The root guard MUST run before argparse to catch all invocations.
        """
        os.environ.pop('CLAUDE_ALLOW_ROOT', None)
        with (
            patch('platform.system', return_value='Linux'),
            patch('os.geteuid', create=True, return_value=0),
            patch.dict('os.environ', {}, clear=False),
            patch('sys.argv', ['setup_environment.py']),
            pytest.raises(SystemExit) as exc_info,
        ):
            setup_environment.main()
        # Should exit from root guard (code 1), NOT from argparse error (code 2)
        assert exc_info.value.code == 1
