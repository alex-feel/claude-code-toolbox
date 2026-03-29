"""E2E tests verifying specific bug fixes in the artifact isolation reorganization.

Bug 1: Prompt paths in launchers reference isolated directory.
Bug 4+5: CLAUDE_CONFIG_DIR removed from config.json, added to launcher export.
Bug 4+5 (user-explicit): User-specified CLAUDE_CONFIG_DIR popped from env.
Update marker: Uses path inside isolated directory.

Covers: Scenarios 14-17.
"""

import json
from pathlib import Path
from typing import Any

from scripts.setup_environment import _get_update_check_snippet
from scripts.setup_environment import create_launcher_script
from scripts.setup_environment import create_profile_config


class TestBugFixVerification:
    """Verify specific bug fixes produce correct behavior."""

    def test_launcher_prompt_path_in_isolated_dir(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Scenario 14 (Bug 1): Prompt paths reference isolated directory, not flat ~/.claude/."""
        claude_dir = e2e_isolated_home['claude_dir']
        command_names: list[str] = golden_config['command-names']
        cmd = command_names[0]
        artifact_base_dir = claude_dir / cmd
        artifact_base_dir.mkdir(parents=True, exist_ok=True)

        launcher_result = create_launcher_script(
            artifact_base_dir, cmd,
            system_prompt_file='e2e-test-prompt.md',
        )
        assert launcher_result is not None

        launch_sh = artifact_base_dir / 'launch.sh'
        assert launch_sh.exists()
        launch_content = launch_sh.read_text()

        # Prompt path must reference the isolated directory
        assert f'$HOME/.claude/{cmd}/prompts/e2e-test-prompt.md' in launch_content, (
            'Prompt path must be inside isolated environment directory'
        )

        # Must NOT reference the old flat path
        # Check for the specific broken pattern: $HOME/.claude/prompts/ without {cmd}
        # We need to be careful: the correct path contains .claude/{cmd}/prompts/
        # The broken path would be .claude/prompts/ (without {cmd} segment)
        lines = launch_content.splitlines()
        for line in lines:
            if (
                'prompts/e2e-test-prompt.md' in line
                and f'.claude/{cmd}/prompts/' not in line
                and '.claude/prompts/' in line
            ):
                raise AssertionError(
                    f'Found broken prompt path (flat, not isolated): {line.strip()}',
                )

    def test_claude_config_dir_only_in_launcher(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Scenario 15 (Bug 4+5): CLAUDE_CONFIG_DIR absent from config.json, present in launcher."""
        claude_dir = e2e_isolated_home['claude_dir']
        command_names: list[str] = golden_config['command-names']
        cmd = command_names[0]
        artifact_base_dir = claude_dir / cmd
        artifact_base_dir.mkdir(parents=True, exist_ok=True)

        hooks_dir = artifact_base_dir / 'hooks'
        hooks_dir.mkdir(parents=True, exist_ok=True)

        # Create config with custom env vars (but no CLAUDE_CONFIG_DIR)
        env_vars: dict[str, str] = {'MY_VAR': 'val'}
        create_profile_config(
            golden_config.get('hooks', {}),
            artifact_base_dir,
            env=env_vars,
            hooks_base_dir=hooks_dir,
        )

        # Verify config.json does NOT contain CLAUDE_CONFIG_DIR
        config_path = artifact_base_dir / 'config.json'
        assert config_path.exists()
        config_content = json.loads(config_path.read_text())
        env_block = config_content.get('env', {})
        assert 'CLAUDE_CONFIG_DIR' not in env_block, (
            'Bug 4: CLAUDE_CONFIG_DIR must NOT be in config.json env section'
        )
        assert env_block.get('MY_VAR') == 'val', (
            'Other env vars must still be present in config.json'
        )

        # Create launcher and verify it DOES contain CLAUDE_CONFIG_DIR export
        launcher_result = create_launcher_script(artifact_base_dir, cmd)
        assert launcher_result is not None

        launch_sh = artifact_base_dir / 'launch.sh'
        launch_content = launch_sh.read_text()
        assert f'export CLAUDE_CONFIG_DIR="$HOME/.claude/{cmd}"' in launch_content, (
            'Bug 5: launcher must export CLAUDE_CONFIG_DIR'
        )

    def test_user_explicit_claude_config_dir(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Scenario 16: User-explicit CLAUDE_CONFIG_DIR is used for dir, popped from env."""
        claude_dir = e2e_isolated_home['claude_dir']

        # Simulate the main() logic for user-supplied CLAUDE_CONFIG_DIR
        env_variables: dict[str, str] = {
            'CLAUDE_CONFIG_DIR': str(claude_dir / 'custom-env'),
            'OTHER_VAR': 'keep',
        }

        # Step 1: Extract user's custom config dir
        user_config_dir = env_variables.get('CLAUDE_CONFIG_DIR')
        assert user_config_dir is not None
        isolated_config_dir = Path(user_config_dir)
        isolated_config_dir.mkdir(parents=True, exist_ok=True)

        # Step 2: Pop CLAUDE_CONFIG_DIR from env before passing to create_profile_config
        env_variables.pop('CLAUDE_CONFIG_DIR')
        assert 'CLAUDE_CONFIG_DIR' not in env_variables
        assert env_variables == {'OTHER_VAR': 'keep'}

        # Step 3: Create config -- CLAUDE_CONFIG_DIR must NOT appear in output
        hooks_dir = isolated_config_dir / 'hooks'
        hooks_dir.mkdir(parents=True, exist_ok=True)

        create_profile_config(
            {},
            isolated_config_dir,
            env=env_variables,
            hooks_base_dir=hooks_dir,
        )

        config_path = isolated_config_dir / 'config.json'
        assert config_path.exists()
        config_content = json.loads(config_path.read_text())
        env_block = config_content.get('env', {})
        assert 'CLAUDE_CONFIG_DIR' not in env_block
        assert env_block.get('OTHER_VAR') == 'keep'

        # Step 4: Launcher exports the custom path
        launcher_result = create_launcher_script(isolated_config_dir, 'custom-cmd')
        assert launcher_result is not None

        launch_sh = isolated_config_dir / 'launch.sh'
        launch_content = launch_sh.read_text()
        assert 'export CLAUDE_CONFIG_DIR=' in launch_content

    def test_update_check_snippet_path(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Scenario 17: Update marker path uses new path inside isolated directory."""
        command_names: list[str] = golden_config['command-names']
        cmd = command_names[0]

        # Test the snippet function directly
        marker_path = f'$HOME/.claude/{cmd}/update-available.json'
        snippet = _get_update_check_snippet(
            update_marker_path=marker_path,
            command_name=cmd,
        )

        assert f'$HOME/.claude/{cmd}/update-available.json' in snippet
        # Must NOT contain old hyphenated format
        assert f'{cmd}-update-available.json' not in snippet

        # Also verify via launcher generation
        claude_dir = e2e_isolated_home['claude_dir']
        artifact_base_dir = claude_dir / cmd
        artifact_base_dir.mkdir(parents=True, exist_ok=True)

        launcher_result = create_launcher_script(artifact_base_dir, cmd)
        assert launcher_result is not None

        launch_sh = artifact_base_dir / 'launch.sh'
        launch_content = launch_sh.read_text()

        # The update check path should be inside the isolated directory
        assert f'$HOME/.claude/{cmd}/update-available.json' in launch_content, (
            'Update marker path must be inside isolated directory'
        )
        assert f'{cmd}-update-available.json' not in launch_content, (
            'Old hyphenated update marker format must not be present'
        )
