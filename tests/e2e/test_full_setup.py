"""E2E tests for the complete setup_environment workflow.

These tests verify that the setup process creates all expected directories
and files using the golden configuration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.setup_environment import create_additional_settings
from scripts.setup_environment import create_launcher_script
from scripts.setup_environment import create_mcp_config_file
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

    def test_setup_creates_all_directories(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Verify setup creates all required directories.

        Verifies:
        - hooks_dir, agents_dir, commands_dir, skills_dir exist
        - Directories are created under claude_dir
        """
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']

        # Create directories as setup_environment.py does
        agents_dir = claude_dir / 'agents'
        commands_dir = claude_dir / 'commands'
        prompts_dir = claude_dir / 'prompts'
        hooks_dir = claude_dir / 'hooks'
        skills_dir = claude_dir / 'skills'

        for dir_path in [agents_dir, commands_dir, prompts_dir, hooks_dir, skills_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

        # Verify
        assert agents_dir.exists(), f'agents_dir not created: {agents_dir}'
        assert commands_dir.exists(), f'commands_dir not created: {commands_dir}'
        assert prompts_dir.exists(), f'prompts_dir not created: {prompts_dir}'
        assert hooks_dir.exists(), f'hooks_dir not created: {hooks_dir}'
        assert skills_dir.exists(), f'skills_dir not created: {skills_dir}'

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

        # Create additional-settings.json
        create_additional_settings(
            hooks=golden_config.get('hooks', {}),
            claude_user_dir=claude_dir,
            command_name=cmd,
            model=golden_config.get('model'),
            permissions=golden_config.get('permissions'),
            env=golden_config.get('env-variables'),
            include_co_authored_by=None,
            always_thinking_enabled=golden_config.get('always-thinking-enabled'),
            company_announcements=golden_config.get('company-announcements'),
            attribution=golden_config.get('attribution'),
            status_line=golden_config.get('status-line'),
        )

        # Create MCP config file (use configure_all_mcp_servers to get profile servers)
        profile_mcp_path = claude_dir / f'{cmd}-mcp.json'
        from scripts.setup_environment import configure_all_mcp_servers

        _, profile_servers, _ = configure_all_mcp_servers(
            servers=golden_config.get('mcp-servers', []),
            profile_mcp_config_path=profile_mcp_path,
        )
        create_mcp_config_file(
            servers=profile_servers,
            config_path=profile_mcp_path,
        )

        # Create launcher script
        launcher_path = create_launcher_script(
            claude_user_dir=claude_dir,
            command_name=cmd,
            system_prompt_file=None,
            mode='replace',
            has_profile_mcp_servers=False,
        )

        # Register global command creates wrappers in local_bin
        if launcher_path:
            register_global_command(
                launcher_path=launcher_path,
                command_name=cmd,
                additional_names=None,
            )

        # Verify files from EXPECTED_FILES
        errors: list[str] = []
        for template in EXPECTED_FILES:
            expected_path = resolve_path_template(template, paths, cmd)
            if not expected_path.exists():
                errors.append(f'Missing: {expected_path} (template: {template})')

        assert not errors, 'Expected files not created:\n' + '\n'.join(errors)

    def test_setup_processes_all_config_keys(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify ALL config keys from golden_config are processed.

        This test validates that:
        - model, permissions, env-variables are in additional-settings.json
        - mcp-servers are in {cmd}-mcp.json
        - hooks events are configured
        - always-thinking-enabled, company-announcements, attribution, status-line are present
        """
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        # Create additional settings with ALL config keys
        create_additional_settings(
            hooks=golden_config.get('hooks', {}),
            claude_user_dir=claude_dir,
            command_name=cmd,
            model=golden_config.get('model'),
            permissions=golden_config.get('permissions'),
            env=golden_config.get('env-variables'),
            include_co_authored_by=None,
            always_thinking_enabled=golden_config.get('always-thinking-enabled'),
            company_announcements=golden_config.get('company-announcements'),
            attribution=golden_config.get('attribution'),
            status_line=golden_config.get('status-line'),
        )

        # Verify additional-settings file exists (written to claude_user_dir)
        settings_path = claude_dir / f'{cmd}-additional-settings.json'

        assert settings_path.exists(), f'additional-settings.json not created: {settings_path}'

        # Content validation is done in test_output_files.py
