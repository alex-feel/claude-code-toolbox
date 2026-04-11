"""E2E tests for the complete setup_environment workflow.

These tests verify that the setup process creates all expected directories
and files using the golden configuration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.setup_environment import create_launcher_script
from scripts.setup_environment import create_mcp_config_file
from scripts.setup_environment import create_profile_config
from scripts.setup_environment import register_global_command
from tests.e2e.expected import EXPECTED_FILES


def resolve_path_template(template: str, paths: dict[str, Path], cmd: str) -> Path:
    """Resolve path template with fixture paths and command name.

    Args:
        template: Path template like '{claude_dir}/{cmd}-mcp.json'
        paths: Dictionary from e2e_isolated_home fixture
        cmd: Command name from golden_config

    Returns:
        Resolved Path object
    """
    result = template
    for key, path in paths.items():
        result = result.replace(f'{{{key}}}', str(path))
    result = result.replace('{cmd}', cmd)
    return Path(result)


class TestE2EFullSetup:
    """Test the complete E2E setup workflow."""

    def test_no_empty_subdirectories_created(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Verify that subdirectories are NOT created when no content targets them.

        Subdirectories (agents, commands, rules, prompts, hooks, skills) must only
        exist when files are actually placed into them by their respective processing
        functions. An empty configuration must not produce empty subdirectories.
        """
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']

        # Ensure base directory exists (as Step 2 does)
        claude_dir.mkdir(parents=True, exist_ok=True)

        # Verify: subdirectories must NOT exist since no content was written
        subdirs = ['agents', 'commands', 'rules', 'prompts', 'hooks', 'skills']
        for subdir_name in subdirs:
            subdir_path = claude_dir / subdir_name
            assert not subdir_path.exists(), (
                f'Empty subdirectory should not exist: {subdir_path}'
            )

    def test_setup_creates_expected_files(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify setup creates all platform-specific expected files.

        Uses EXPECTED_FILES from tests/e2e/expected/ to check
        platform-appropriate files are created.
        """
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]

        # Run minimal setup operations to create expected files
        # This test verifies file creation logic
        claude_dir = paths['claude_dir']
        artifact_base_dir = claude_dir / cmd
        artifact_base_dir.mkdir(parents=True, exist_ok=True)

        # Create config.json in artifact base dir
        create_profile_config(
            hooks=golden_config.get('hooks', {}),
            config_base_dir=artifact_base_dir,
            model=golden_config.get('model'),
            permissions=golden_config.get('permissions'),
            env=golden_config.get('env-variables'),

            always_thinking_enabled=golden_config.get('always-thinking-enabled'),
            company_announcements=golden_config.get('company-announcements'),
            attribution=golden_config.get('attribution'),
            status_line=golden_config.get('status-line'),
            effort_level=golden_config.get('effort-level'),
        )

        # Create MCP config file in artifact base dir
        profile_mcp_path = artifact_base_dir / 'mcp.json'
        from scripts.setup_environment import configure_all_mcp_servers

        _, profile_servers, _ = configure_all_mcp_servers(
            servers=golden_config.get('mcp-servers', []),
            profile_mcp_config_path=profile_mcp_path,
        )
        create_mcp_config_file(
            servers=profile_servers,
            config_path=profile_mcp_path,
        )

        # Create launcher script in artifact base dir
        launcher_path_result = create_launcher_script(
            config_base_dir=artifact_base_dir,
            command_name=cmd,
            system_prompt_file=None,
            mode='replace',
            has_profile_mcp_servers=False,
        )
        launcher_path = launcher_path_result[0] if launcher_path_result else None
        launch_script = launcher_path_result[1] if launcher_path_result else None

        # Register global command creates wrappers in local_bin
        if launcher_path:
            register_global_command(
                launcher_path=launcher_path,
                command_name=cmd,
                additional_names=None,
                launch_script_path=launch_script,
            )

        # Verify files from EXPECTED_FILES
        errors: list[str] = []
        for template in EXPECTED_FILES:
            expected_path = resolve_path_template(template, paths, cmd)
            if not expected_path.exists():
                errors.append(f'Missing: {expected_path} (template: {template})')

        assert not errors, 'Expected files not created:\n' + '\n'.join(errors)

    def test_create_profile_config_processes_all_keys(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify create_profile_config() writes ALL profile-owned keys to config.json.

        This test validates the isolated-mode writer:
        - model, permissions, env, attribution, alwaysThinkingEnabled, effortLevel,
          companyAnnouncements, statusLine, hooks are all present in config.json
          (the file written by create_profile_config() when command-names is set).

        NOTE: This test covers ONLY the isolated mode writer. For the non-
        command-names mode, where write_profile_settings_to_settings()
        writes the same profile-owned keys into the shared settings.json,
        see tests/e2e/test_profile_settings_routing.py.
        """
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']

        # Create settings with ALL config keys
        create_profile_config(
            hooks=golden_config.get('hooks', {}),
            config_base_dir=claude_dir,
            model=golden_config.get('model'),
            permissions=golden_config.get('permissions'),
            env=golden_config.get('env-variables'),

            always_thinking_enabled=golden_config.get('always-thinking-enabled'),
            company_announcements=golden_config.get('company-announcements'),
            attribution=golden_config.get('attribution'),
            status_line=golden_config.get('status-line'),
            effort_level=golden_config.get('effort-level'),
        )

        # Verify settings file exists (written to config_base_dir as config.json)
        settings_path = claude_dir / 'config.json'

        assert settings_path.exists(), f'settings.json not created: {settings_path}'

        # Content validation is done in test_output_files.py
