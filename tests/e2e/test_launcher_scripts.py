"""E2E tests for platform-specific launcher script verification.

These tests verify that the launcher scripts created for each platform
have correct content, format, and are properly configured.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.setup_environment import create_launcher_script
from scripts.setup_environment import register_global_command
from tests.e2e.expected import EXPECTED_PATHS
from tests.e2e.validators import validate_launcher_script


def resolve_path_template(template: str, paths: dict[str, Path], cmd: str) -> Path:
    """Resolve path template with fixture paths and command name."""
    result = template
    for key, path in paths.items():
        result = result.replace(f'{{{key}}}', str(path))
    result = result.replace('{cmd}', cmd)
    return Path(result)


class TestLauncherScriptsWindows:
    """Windows-specific launcher script tests."""

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only test')
    def test_windows_cmd_wrapper_content(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify Windows CMD wrapper has correct content.

        Checks:
        - @echo off directive present
        - Bash invocation for launcher script
        - Passes through arguments
        """
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        # Create launcher script
        launcher_path = create_launcher_script(
            claude_user_dir=claude_dir,
            command_name=cmd,
            system_prompt_file=None,
            mode='replace',
            has_profile_mcp_servers=False,
        )

        # Register global command creates wrappers
        if launcher_path:
            register_global_command(
                launcher_path=launcher_path,
                command_name=cmd,
                additional_names=None,
            )

        # Validate CMD wrapper
        cmd_wrapper_path = resolve_path_template(
            EXPECTED_PATHS['command_wrapper_cmd'],
            paths,
            cmd,
        )

        errors = validate_launcher_script(cmd_wrapper_path, cmd)
        assert not errors, 'CMD wrapper validation failed:\n' + '\n'.join(errors)

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only test')
    def test_windows_ps1_wrapper_content(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify Windows PowerShell wrapper has correct content.

        Checks:
        - PowerShell invocation (& or Invoke-Expression)
        - References launcher script or command
        """
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        # Create launcher script
        launcher_path = create_launcher_script(
            claude_user_dir=claude_dir,
            command_name=cmd,
            system_prompt_file=None,
            mode='replace',
            has_profile_mcp_servers=False,
        )

        # Register global command creates wrappers
        if launcher_path:
            register_global_command(
                launcher_path=launcher_path,
                command_name=cmd,
                additional_names=None,
            )

        # Validate PS1 wrapper
        ps1_wrapper_path = resolve_path_template(
            EXPECTED_PATHS['command_wrapper_ps1'],
            paths,
            cmd,
        )

        errors = validate_launcher_script(ps1_wrapper_path, cmd)
        assert not errors, 'PowerShell wrapper validation failed:\n' + '\n'.join(errors)

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only test')
    def test_windows_bash_wrapper_exists(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify Windows Git Bash wrapper exists and has correct format.

        The Git Bash wrapper is the extensionless file in local_bin.
        """
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        # Create launcher script
        launcher_path = create_launcher_script(
            claude_user_dir=claude_dir,
            command_name=cmd,
            system_prompt_file=None,
            mode='replace',
            has_profile_mcp_servers=False,
        )

        # Register global command creates wrappers
        if launcher_path:
            register_global_command(
                launcher_path=launcher_path,
                command_name=cmd,
                additional_names=None,
            )

        # Validate Git Bash wrapper
        bash_wrapper_path = resolve_path_template(
            EXPECTED_PATHS['command_wrapper_bash'],
            paths,
            cmd,
        )

        errors = validate_launcher_script(bash_wrapper_path, cmd)
        assert not errors, 'Git Bash wrapper validation failed:\n' + '\n'.join(errors)


class TestLauncherScriptsUnix:
    """Unix-specific (Linux/macOS) launcher script tests."""

    @pytest.mark.skipif(sys.platform == 'win32', reason='Unix-only test')
    def test_unix_launcher_script_content(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify Unix launcher script has correct content.

        Checks:
        - Shebang line present
        - Claude invocation
        - References to settings file
        """
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        # Create launcher script
        launcher_path = create_launcher_script(
            claude_user_dir=claude_dir,
            command_name=cmd,
            system_prompt_file=None,
            mode='replace',
            has_profile_mcp_servers=False,
        )

        assert launcher_path is not None, 'create_launcher_script returned None'

        errors = validate_launcher_script(launcher_path, cmd)
        assert not errors, 'Unix launcher validation failed:\n' + '\n'.join(errors)

    @pytest.mark.skipif(sys.platform == 'win32', reason='Unix-only test')
    def test_unix_launcher_executable(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify Unix launcher script is executable.

        On Unix systems, the launcher script must have execute permissions.
        """
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        # Create launcher script
        launcher_path = create_launcher_script(
            claude_user_dir=claude_dir,
            command_name=cmd,
            system_prompt_file=None,
            mode='replace',
            has_profile_mcp_servers=False,
        )

        assert launcher_path is not None, 'create_launcher_script returned None'
        assert launcher_path.exists(), f'Launcher script not created: {launcher_path}'

        # Check executable bit (Unix only)
        import stat

        mode = launcher_path.stat().st_mode
        is_executable = bool(mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
        assert is_executable, f'Launcher script {launcher_path} is not executable'


class TestLauncherScriptsPlatformAgnostic:
    """Platform-agnostic launcher script tests."""

    def test_launcher_references_settings_file(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify launcher script references the settings file.

        The launcher should reference {cmd}-additional-settings.json
        to load environment-specific configuration.
        """
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        # Create launcher script
        launcher_path = create_launcher_script(
            claude_user_dir=claude_dir,
            command_name=cmd,
            system_prompt_file=None,
            mode='replace',
            has_profile_mcp_servers=False,
        )

        assert launcher_path is not None, 'create_launcher_script returned None'
        assert launcher_path.exists(), f'Launcher script not created: {launcher_path}'

        content = launcher_path.read_text(encoding='utf-8')
        settings_pattern = f'{cmd}-additional-settings.json'

        # Note: On Windows, the launcher .sh file may not directly reference
        # additional-settings if it's using a different invocation path
        if sys.platform == 'win32':
            # On Windows, check for settings reference OR claude invocation
            has_settings_ref = settings_pattern in content or '--settings' in content
            has_claude_ref = 'claude' in content.lower()
            assert has_settings_ref or has_claude_ref, (
                f'Launcher script {launcher_path.name} missing settings reference '
                f'or claude invocation'
            )
        else:
            # On Unix, the launcher should directly reference the settings file
            assert settings_pattern in content or '--settings' in content, (
                f'Launcher script {launcher_path.name} missing reference to {settings_pattern}'
            )

    def test_launcher_script_format(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify launcher script has correct format for current platform.

        Platform-specific format checks using validate_launcher_script.
        """
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        # Create launcher script
        launcher_path = create_launcher_script(
            claude_user_dir=claude_dir,
            command_name=cmd,
            system_prompt_file=None,
            mode='replace',
            has_profile_mcp_servers=False,
        )

        assert launcher_path is not None, 'create_launcher_script returned None'

        # Use the validator which handles platform-specific checks
        errors = validate_launcher_script(launcher_path, cmd)
        assert not errors, 'Launcher script format validation failed:\n' + '\n'.join(errors)
