"""E2E tests for cross-platform version detection in launcher scripts.

These tests verify that the version detection regex (grep -oE) works correctly
on all platforms (Linux, macOS, Windows) to prevent regression of the
grep -P incompatibility issue.

The grep -oP flag uses Perl-Compatible Regular Expressions (PCRE) which is
not supported on macOS BSD grep. The solution uses grep -oE with POSIX
Extended Regular Expressions (ERE) instead.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.setup_environment import create_launcher_script
from tests.e2e.validators import validate_version_detection_pattern


class TestVersionDetectionPattern:
    """Tests for cross-platform version detection regex pattern.

    These tests run the actual grep command to ensure compatibility
    with the platform's grep implementation:
    - GNU grep on Linux and Windows (Git Bash)
    - BSD grep on macOS
    """

    @pytest.mark.parametrize(
        ('version_output', 'expected_version'),
        [
            ('claude, version 2.0.76', '2.0.76'),
            ('Claude Code version 2.1.0', '2.1.0'),
            ('version 10.20.30', '10.20.30'),
            ('v1.0.0 (build 123)', '1.0.0'),
            ('2.0.76\n', '2.0.76'),
        ],
        ids=[
            'standard-format',
            'claude-code-format',
            'double-digit-components',
            'version-with-build-info',
            'trailing-newline',
        ],
    )
    def test_version_regex_extraction(
        self,
        version_output: str,
        expected_version: str,
    ) -> None:
        """Verify version extraction regex works on current platform.

        This test runs the actual grep command to ensure it works with
        the platform's grep implementation (GNU grep on Linux/Windows,
        BSD grep on macOS).
        """
        # Use platform-appropriate shell
        if sys.platform == 'win32':
            # Windows: use Git Bash via bash.exe
            cmd = [
                'bash',
                '-c',
                f"echo '{version_output}' | grep -oE '[0-9]+\\.[0-9]+\\.[0-9]+' | head -1",
            ]
        else:
            # Unix: use sh directly
            cmd = [
                'sh',
                '-c',
                f"echo '{version_output}' | grep -oE '[0-9]+\\.[0-9]+\\.[0-9]+' | head -1",
            ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        # Verify extraction succeeded
        assert result.returncode == 0, f'grep command failed: {result.stderr}'
        extracted = result.stdout.strip()
        assert extracted == expected_version, (
            f'Version extraction mismatch: expected {expected_version!r}, got {extracted!r}'
        )

    def test_version_regex_no_match(self) -> None:
        """Verify regex returns empty when no version pattern found."""
        version_output = 'claude: command not found'

        if sys.platform == 'win32':
            cmd = [
                'bash',
                '-c',
                f"echo '{version_output}' | grep -oE '[0-9]+\\.[0-9]+\\.[0-9]+' | head -1",
            ]
        else:
            cmd = [
                'sh',
                '-c',
                f"echo '{version_output}' | grep -oE '[0-9]+\\.[0-9]+\\.[0-9]+' | head -1",
            ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        # grep returns 1 when no match - this is expected
        extracted = result.stdout.strip()
        assert extracted == '', f'Expected empty string, got {extracted!r}'

    def test_posix_ere_flag_supported(self) -> None:
        """Verify that grep -E flag is available on current platform.

        This is a sanity check that the POSIX ERE flag works.
        """
        if sys.platform == 'win32':
            cmd = ['bash', '-c', "echo '123' | grep -E '[0-9]+'"]
        else:
            cmd = ['sh', '-c', "echo '123' | grep -E '[0-9]+'"]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        assert result.returncode == 0, (
            f'grep -E not supported on this platform: {result.stderr}'
        )


def _create_test_prompt(claude_dir: Path) -> str:
    """Create a test system prompt file and return its filename.

    The version detection function is only included in launcher scripts when
    a system prompt file is configured. This helper creates the required
    prompt file for testing.

    Args:
        claude_dir: The Claude user directory

    Returns:
        The filename of the created prompt (relative to prompts/)
    """
    prompts_dir = claude_dir / 'prompts'
    prompts_dir.mkdir(exist_ok=True)
    prompt_file = prompts_dir / 'test-prompt.md'
    prompt_file.write_text('# Test System Prompt\n\nThis is a test prompt.')
    return 'test-prompt.md'


class TestLauncherVersionDetection:
    """Tests for version detection in generated launcher scripts.

    These tests verify that launcher scripts with system prompts use
    POSIX ERE (grep -oE) for version detection, ensuring compatibility
    with macOS BSD grep.

    Note: Version detection is only included in launchers when a system
    prompt file is configured, as it's needed to determine which prompt
    flag to use (--system-prompt vs --append-system-prompt).
    """

    def test_launcher_contains_posix_ere_pattern(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify launcher script uses POSIX ERE pattern (grep -oE), not PCRE (grep -oP).

        This test ensures the fix for macOS compatibility is in place.
        The launcher script MUST use:
        - grep -oE (POSIX Extended Regular Expressions)
        - [0-9]+ (POSIX digit class)

        It MUST NOT use:
        - grep -oP (Perl-Compatible Regular Expressions - not supported on macOS)
        - \\d+ (PCRE digit shorthand)
        """
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        # Create system prompt file (required for version detection to be included)
        prompt_file = _create_test_prompt(claude_dir)

        # Create launcher script with system prompt
        launcher_path = create_launcher_script(
            claude_user_dir=claude_dir,
            command_name=cmd,
            system_prompt_file=prompt_file,
            mode='replace',
            has_profile_mcp_servers=False,
        )

        assert launcher_path is not None, 'create_launcher_script returned None'
        assert launcher_path.exists(), f'Launcher script not created: {launcher_path}'

        # On Windows, check the shared POSIX script which contains version detection
        if sys.platform == 'win32':
            posix_script = claude_dir / f'launch-{cmd}.sh'
            assert posix_script.exists(), f'Shared POSIX script not found: {posix_script}'
            content = posix_script.read_text(encoding='utf-8')
            script_name = posix_script.name
        else:
            content = launcher_path.read_text(encoding='utf-8')
            script_name = launcher_path.name

        # Use validator for comprehensive checks
        errors = validate_version_detection_pattern(content, script_name)
        assert not errors, (
            'Launcher script version detection pattern validation failed:\n'
            + '\n'.join(errors)
        )

    def test_launcher_version_function_exists(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify launcher contains get_claude_version function.

        On Windows, the version function is in the shared POSIX script (launch-{cmd}.sh),
        not in the PowerShell/CMD wrappers. On Unix, it's in the main launcher script.
        """
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        # Create system prompt file (required for version detection to be included)
        prompt_file = _create_test_prompt(claude_dir)

        launcher_path = create_launcher_script(
            claude_user_dir=claude_dir,
            command_name=cmd,
            system_prompt_file=prompt_file,
            mode='replace',
            has_profile_mcp_servers=False,
        )

        assert launcher_path is not None

        # On Windows, the version function is in the shared POSIX script
        if sys.platform == 'win32':
            # The shared script is at ~/.claude/launch-{cmd}.sh
            posix_script = claude_dir / f'launch-{cmd}.sh'
            assert posix_script.exists(), f'Shared POSIX script not found: {posix_script}'
            content = posix_script.read_text(encoding='utf-8')
            script_name = posix_script.name
        else:
            content = launcher_path.read_text(encoding='utf-8')
            script_name = launcher_path.name

        # Verify version detection function exists
        has_version_func = (
            'get_claude_version()' in content or 'get_claude_version ()' in content
        )
        assert has_version_func, (
            f'Launcher script {script_name} missing get_claude_version function'
        )

    def test_launcher_no_pcre_patterns(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify launcher does not contain any PCRE-specific patterns.

        PCRE patterns like grep -P and \\d are not supported on macOS BSD grep.
        This test ensures no such patterns exist in the generated launcher.
        """
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        # Create system prompt file (required for version detection to be included)
        prompt_file = _create_test_prompt(claude_dir)

        launcher_path = create_launcher_script(
            claude_user_dir=claude_dir,
            command_name=cmd,
            system_prompt_file=prompt_file,
            mode='replace',
            has_profile_mcp_servers=False,
        )

        assert launcher_path is not None

        # On Windows, check the shared POSIX script which contains version detection
        if sys.platform == 'win32':
            posix_script = claude_dir / f'launch-{cmd}.sh'
            assert posix_script.exists(), f'Shared POSIX script not found: {posix_script}'
            content = posix_script.read_text(encoding='utf-8')
            script_name = posix_script.name
        else:
            content = launcher_path.read_text(encoding='utf-8')
            script_name = launcher_path.name

        # Check for PCRE-specific patterns
        assert 'grep -oP' not in content, (
            f'Launcher script {script_name} contains grep -oP which is NOT supported '
            'on macOS. Use grep -oE instead.'
        )
        assert 'grep -P' not in content, (
            f'Launcher script {script_name} contains grep -P which is NOT supported '
            'on macOS. Use grep -E instead.'
        )

        # Check for PCRE digit shorthand (escaped for shell context)
        pcre_digit_patterns = ['\\\\d+', "'\\d+"]
        for pattern in pcre_digit_patterns:
            if pattern in content:
                pytest.fail(
                    f'Launcher script {script_name} contains PCRE digit shorthand '
                    f'({pattern}) which is NOT supported on macOS. Use [0-9]+ instead.',
                )
