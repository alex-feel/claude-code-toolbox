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
        launcher_path_result = create_launcher_script(
            config_base_dir=claude_dir,
            command_name=cmd,
            system_prompt_file=None,
            mode='replace',
            has_profile_mcp_servers=False,
        )
        launcher_path = launcher_path_result[0] if launcher_path_result else None
        launch_script = launcher_path_result[1] if launcher_path_result else None

        # Register global command creates wrappers
        if launcher_path:
            register_global_command(
                launcher_path=launcher_path,
                command_name=cmd,
                additional_names=None,
                launch_script_path=launch_script,
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
        launcher_path_result = create_launcher_script(
            config_base_dir=claude_dir,
            command_name=cmd,
            system_prompt_file=None,
            mode='replace',
            has_profile_mcp_servers=False,
        )
        launcher_path = launcher_path_result[0] if launcher_path_result else None
        launch_script = launcher_path_result[1] if launcher_path_result else None

        # Register global command creates wrappers
        if launcher_path:
            register_global_command(
                launcher_path=launcher_path,
                command_name=cmd,
                additional_names=None,
                launch_script_path=launch_script,
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
        launcher_path_result = create_launcher_script(
            config_base_dir=claude_dir,
            command_name=cmd,
            system_prompt_file=None,
            mode='replace',
            has_profile_mcp_servers=False,
        )
        launcher_path = launcher_path_result[0] if launcher_path_result else None
        launch_script = launcher_path_result[1] if launcher_path_result else None

        # Register global command creates wrappers
        if launcher_path:
            register_global_command(
                launcher_path=launcher_path,
                command_name=cmd,
                additional_names=None,
                launch_script_path=launch_script,
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
        launcher_path_result = create_launcher_script(
            config_base_dir=claude_dir,
            command_name=cmd,
            system_prompt_file=None,
            mode='replace',
            has_profile_mcp_servers=False,
        )
        launcher_path = launcher_path_result[0] if launcher_path_result else None

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
        launcher_path_result = create_launcher_script(
            config_base_dir=claude_dir,
            command_name=cmd,
            system_prompt_file=None,
            mode='replace',
            has_profile_mcp_servers=False,
        )
        launcher_path = launcher_path_result[0] if launcher_path_result else None

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
        """Verify launcher script references the settings file via --settings flag."""
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        # Create launcher script
        launcher_path_result = create_launcher_script(
            config_base_dir=claude_dir,
            command_name=cmd,
            system_prompt_file=None,
            mode='replace',
            has_profile_mcp_servers=False,
        )
        launcher_path = launcher_path_result[0] if launcher_path_result else None

        assert launcher_path is not None, 'create_launcher_script returned None'
        assert launcher_path.exists(), f'Launcher script not created: {launcher_path}'

        content = launcher_path.read_text(encoding='utf-8')

        if sys.platform == 'win32':
            # On Windows, check for settings reference OR claude invocation
            has_settings_ref = '--settings' in content
            has_claude_ref = 'claude' in content.lower()
            assert has_settings_ref or has_claude_ref, (
                f'Launcher script {launcher_path.name} missing --settings reference '
                f'or claude invocation'
            )
        else:
            # On Unix, the launcher should reference --settings flag
            assert '--settings' in content, (
                f'Launcher script {launcher_path.name} missing --settings flag reference'
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
        launcher_path_result = create_launcher_script(
            config_base_dir=claude_dir,
            command_name=cmd,
            system_prompt_file=None,
            mode='replace',
            has_profile_mcp_servers=False,
        )
        launcher_path = launcher_path_result[0] if launcher_path_result else None

        assert launcher_path is not None, 'create_launcher_script returned None'

        # Use the validator which handles platform-specific checks
        errors = validate_launcher_script(launcher_path, cmd)
        assert not errors, 'Launcher script format validation failed:\n' + '\n'.join(errors)


def _find_bash() -> str | None:
    """Locate a bash able to run the generated POSIX launcher.

    On Windows, plain which('bash') can resolve to the WSL shim, which
    cannot execute Windows paths; the Git Bash discovery from the module
    under test is authoritative there.

    Returns:
        Path to a usable bash executable, or None when unavailable.
    """
    import shutil

    if sys.platform == 'win32':
        from scripts.setup_environment import find_bash_windows

        return find_bash_windows()
    return shutil.which('bash')


def _find_powershell() -> str | None:
    """Locate a PowerShell able to parse generated .ps1 wrappers.

    Returns:
        Path to a PowerShell executable, or None when unavailable.
    """
    import shutil

    return shutil.which('pwsh') or shutil.which('powershell')


class TestGeneratedScriptSyntax:
    """Generated scripts must parse with their real interpreters.

    Content substring checks cannot catch quoting or syntax regressions in
    the generated code; these tests hand the actual generated files to the
    actual interpreters.
    """

    @staticmethod
    def _generate(claude_dir: Path, cmd: str) -> tuple[Path, Path]:
        result = create_launcher_script(
            config_base_dir=claude_dir / cmd,
            command_name=cmd,
            system_prompt_file=None,
            mode='replace',
            has_profile_mcp_servers=False,
        )
        assert result is not None
        ps1_path, launch_sh = result
        return Path(ps1_path), Path(launch_sh)

    def test_launch_sh_passes_bash_syntax_check(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """bash -n accepts the generated launch.sh."""
        import subprocess

        bash = _find_bash()
        if bash is None:
            pytest.skip('bash unavailable')
        cmd = golden_config['command-names'][0]
        _, launch_sh = self._generate(e2e_isolated_home['claude_dir'], cmd)

        completed = subprocess.run(
            [bash, '-n', str(launch_sh)],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        assert completed.returncode == 0, f'bash -n rejected launch.sh:\n{completed.stderr}'

    @pytest.mark.skipif(
        sys.platform != 'win32',
        reason='start.ps1 is generated only on Windows; on POSIX the returned '
               'tuple carries shell launchers',
    )
    def test_start_ps1_parses_without_errors(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """The PowerShell AST parser accepts the generated start.ps1."""
        import subprocess

        powershell = _find_powershell()
        if powershell is None:
            pytest.skip('PowerShell unavailable')
        cmd = golden_config['command-names'][0]
        ps1_path, _ = self._generate(e2e_isolated_home['claude_dir'], cmd)

        parse_command = (
            '$t=$null;$e=$null;'
            f"[System.Management.Automation.Language.Parser]::ParseFile('{ps1_path}',[ref]$t,[ref]$e)|Out-Null;"
            'if($e.Count -gt 0){$e|ForEach-Object{Write-Error $_.Message};exit 1}'
        )
        completed = subprocess.run(
            [powershell, '-NoProfile', '-Command', parse_command],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        assert completed.returncode == 0, f'PowerShell parser rejected start.ps1:\n{completed.stderr}'


class TestLauncherExecutionSmoke:
    """The generated launcher actually reaches the claude invocation.

    Runs the real launch.sh under bash with a stub claude on PATH,
    asserting the stub receives --settings with the isolated config.json
    plus pass-through arguments -- the layer where a quoting bug survives
    every content assertion.
    """

    def test_launch_sh_invokes_claude_with_settings(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """launch.sh execs claude with --settings and forwards arguments."""
        import os
        import subprocess

        bash = _find_bash()
        if bash is None:
            pytest.skip('bash unavailable')
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']
        cmd = golden_config['command-names'][0]
        profile_dir = claude_dir / cmd
        profile_dir.mkdir(parents=True, exist_ok=True)
        (profile_dir / 'config.json').write_text('{}', encoding='utf-8')

        result = create_launcher_script(
            config_base_dir=profile_dir,
            command_name=cmd,
            system_prompt_file=None,
            mode='replace',
            has_profile_mcp_servers=False,
        )
        assert result is not None
        launch_sh = Path(result[1])

        stub_dir = claude_dir / 'stub-bin'
        stub_dir.mkdir(parents=True, exist_ok=True)
        args_file = stub_dir / 'invoked.txt'
        stub = stub_dir / 'claude'
        stub_body = '#!/bin/sh\nprintf \'%s\\n\' "$@" > "' + args_file.as_posix() + '"\n'
        stub.write_text(stub_body, encoding='utf-8')
        stub.chmod(0o755)

        home_dir = claude_dir.parent
        env = dict(os.environ)
        env['HOME'] = str(home_dir)
        env['PATH'] = f'{stub_dir}{os.pathsep}' + env.get('PATH', '')

        completed = subprocess.run(
            [bash, str(launch_sh), '--probe-arg'],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
            env=env,
        )
        assert completed.returncode == 0, (
            f'launch.sh failed:\nstdout: {completed.stdout}\nstderr: {completed.stderr}'
        )
        assert args_file.exists(), 'stub claude was never invoked'
        invoked_args = args_file.read_text(encoding='utf-8').splitlines()
        assert '--settings' in invoked_args
        assert '--probe-arg' in invoked_args
        settings_value = invoked_args[invoked_args.index('--settings') + 1]
        assert settings_value.replace('\\', '/').endswith(f'.claude/{cmd}/config.json')
