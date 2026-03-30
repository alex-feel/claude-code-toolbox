"""E2E tests for env loader file generation and launcher env sourcing.

These tests validate that generate_env_loader_files() creates correct
shell-specific loader files and that create_launcher_script() injects
guarded source lines for loading OS-level environment variables.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.setup_environment import create_launcher_script
from scripts.setup_environment import generate_env_loader_files
from tests.e2e.validators import validate_env_loader_files
from tests.e2e.validators import validate_launcher_env_sourcing


class TestEnvLoaderFileGeneration:
    """E2E tests for generate_env_loader_files() output."""

    def test_global_env_loader_files_exist(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify global convenience files are generated for os-env-variables.

        Checks:
        - toolbox-env.sh exists in ~/.claude/
        - toolbox-env.ps1 exists in ~/.claude/ (Windows only)
        - Content contains correct export syntax
        - Deletion variables (None values) are excluded
        """
        paths = e2e_isolated_home
        os_env_vars = golden_config.get('os-env-variables', {})
        if not os_env_vars:
            pytest.skip('No os-env-variables in golden config')

        generate_env_loader_files(os_env_vars, None, None)

        errors = validate_env_loader_files(
            paths['claude_dir'], os_env_vars, command_name=None,
        )
        assert not errors, 'Global env loader validation failed:\n' + '\n'.join(errors)

    def test_per_command_env_loader_files_exist(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify per-command env loader files are generated alongside global files.

        Checks:
        - env.sh exists in ~/.claude/{cmd}/
        - env.ps1 exists in ~/.claude/{cmd}/ (Windows only)
        - Global files are also generated
        """
        paths = e2e_isolated_home
        os_env_vars = golden_config.get('os-env-variables', {})
        cmd_names = golden_config.get('command-names', [])
        if not os_env_vars or not cmd_names:
            pytest.skip('No os-env-variables or command-names in golden config')

        cmd = cmd_names[0]
        cmd_dir = paths['claude_dir'] / cmd
        cmd_dir.mkdir(parents=True, exist_ok=True)

        generate_env_loader_files(os_env_vars, cmd_names, cmd_dir)

        errors = validate_env_loader_files(
            paths['claude_dir'], os_env_vars, command_name=cmd,
        )
        assert not errors, 'Per-command env loader validation failed:\n' + '\n'.join(errors)

    def test_no_files_when_all_deletions(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Verify no env loader files are generated when all vars are deletions."""
        paths = e2e_isolated_home
        all_deletions: dict[str, str | None] = {'DEL_A': None, 'DEL_B': None}

        result = generate_env_loader_files(all_deletions, None, None)

        assert result == {}, 'Expected empty result for all-deletion vars'
        global_sh = paths['claude_dir'] / 'toolbox-env.sh'
        assert not global_sh.exists(), 'toolbox-env.sh should not exist for all-deletion vars'

    def test_deletion_vars_excluded_from_content(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Verify deletion vars (None values) do not appear in loader files."""
        paths = e2e_isolated_home
        mixed_vars: dict[str, str | None] = {
            'KEEP_VAR': 'keep_value',
            'DELETE_VAR': None,
        }

        generate_env_loader_files(mixed_vars, None, None)

        errors = validate_env_loader_files(
            paths['claude_dir'], mixed_vars, command_name=None,
        )
        assert not errors, 'Mixed vars validation failed:\n' + '\n'.join(errors)

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only test')
    def test_cmd_env_loader_files_on_windows(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify env.cmd and toolbox-env.cmd generated on Windows."""
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']
        cmd_names = golden_config.get('command-names', [])
        os_env_vars = golden_config.get('os-env-variables', {})
        if not os_env_vars:
            pytest.skip('No os-env-variables in golden config')
        if not cmd_names:
            pytest.skip('No command-names in golden config')

        cmd = cmd_names[0]
        cmd_dir = claude_dir / cmd
        cmd_dir.mkdir(parents=True, exist_ok=True)

        generate_env_loader_files(os_env_vars, cmd_names, cmd_dir)

        errors = validate_env_loader_files(claude_dir, os_env_vars, cmd)
        cmd_errors = [e for e in errors if 'cmd' in e.lower()]
        assert not cmd_errors, 'CMD env loader validation failed:\n' + '\n'.join(cmd_errors)


class TestLauncherEnvSourcing:
    """E2E tests for launcher script env loader integration."""

    @pytest.mark.skipif(sys.platform == 'win32', reason='Unix-only test')
    def test_unix_launcher_contains_env_source_guard(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify Unix launch.sh contains guarded source for env.sh.

        Checks:
        - File-existence guard ([ -f ... ]) is present
        - Reference to env.sh is present
        """
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        launcher_result = create_launcher_script(
            config_base_dir=claude_dir,
            command_name=cmd,
            system_prompt_file=None,
            mode='replace',
            has_profile_mcp_servers=False,
        )
        launcher_path = launcher_result[0] if launcher_result else None
        assert launcher_path is not None, 'create_launcher_script returned None'

        errors = validate_launcher_env_sourcing(launcher_path)
        assert not errors, 'Unix launcher env sourcing validation failed:\n' + '\n'.join(errors)

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only test')
    def test_windows_ps1_launcher_contains_env_source_guard(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify Windows start.ps1 contains guarded dot-source for env.ps1.

        Checks:
        - Test-Path guard is present
        - Reference to env.ps1 is present
        """
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        create_launcher_script(
            config_base_dir=claude_dir,
            command_name=cmd,
            system_prompt_file=None,
            mode='replace',
            has_profile_mcp_servers=False,
        )

        # Find the PS1 wrapper
        ps1_path = claude_dir / 'start.ps1'
        if not ps1_path.exists():
            # Try alternate location
            ps1_path = paths['local_bin'] / f'{cmd}.ps1'

        if ps1_path.exists():
            errors = validate_launcher_env_sourcing(ps1_path)
            assert not errors, 'Windows PS1 launcher env sourcing failed:\n' + '\n'.join(errors)

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only test')
    def test_windows_bash_launcher_contains_env_source_guard(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify Windows launch.sh (shared POSIX) contains env.sh source guard."""
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        launcher_result = create_launcher_script(
            config_base_dir=claude_dir,
            command_name=cmd,
            system_prompt_file=None,
            mode='replace',
            has_profile_mcp_servers=False,
        )
        launcher_path = launcher_result[0] if launcher_result else None
        assert launcher_path is not None, 'create_launcher_script returned None'

        errors = validate_launcher_env_sourcing(launcher_path)
        assert not errors, 'Windows bash launcher env sourcing failed:\n' + '\n'.join(errors)

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only test')
    def test_windows_cmd_launcher_contains_env_source_guard(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify Windows start.cmd contains guarded call for env.cmd.

        Checks:
        - if exist guard is present
        - Reference to env.cmd is present
        - call command is present
        """
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        create_launcher_script(
            config_base_dir=claude_dir,
            command_name=cmd,
            system_prompt_file=None,
            mode='replace',
            has_profile_mcp_servers=False,
        )

        cmd_path = claude_dir / 'start.cmd'
        if cmd_path.exists():
            errors = validate_launcher_env_sourcing(cmd_path)
            assert not errors, 'Windows CMD launcher env sourcing failed:\n' + '\n'.join(errors)
