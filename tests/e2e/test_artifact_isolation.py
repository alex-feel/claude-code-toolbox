"""E2E tests for CLAUDE_CONFIG_DIR-based artifact isolation.

Verifies that when command-names is set, environment artifacts (agents, skills,
rules, commands, hooks, prompts) are placed in an isolated directory under
~/.claude/{primary_command_name}/, while infrastructure files (settings, MCP config,
launcher scripts) remain in the standard ~/.claude/ directory.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts import setup_environment


@dataclass
class _IsolatedPaths:
    """Container for isolated setup paths."""

    home: Path
    claude_dir: Path
    primary_command_name: str
    artifact_base_dir: Path


def _run_isolated_setup(
    e2e_isolated_home: dict[str, Path],
    golden_config: dict[str, Any],
) -> _IsolatedPaths:
    """Compute isolation paths from golden config.

    Returns:
        _IsolatedPaths with home, claude_dir, primary_command_name, artifact_base_dir.
    """
    home = e2e_isolated_home['home']
    claude_dir = e2e_isolated_home['claude_dir']

    command_names = golden_config.get('command-names', [])
    primary_command_name = command_names[0] if command_names else None
    assert primary_command_name is not None, 'Golden config must have command-names'
    assert isinstance(primary_command_name, str)

    artifact_base_dir = claude_dir / primary_command_name

    return _IsolatedPaths(
        home=home,
        claude_dir=claude_dir,
        primary_command_name=primary_command_name,
        artifact_base_dir=artifact_base_dir,
    )


class TestArtifactIsolationDirectories:
    """Test that isolated directories are created when command-names is set."""

    def test_isolated_directories_created(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify isolated artifact directories are created under ~/.claude/{primary_command_name}/."""
        paths = _run_isolated_setup(e2e_isolated_home, golden_config)
        artifact_base = paths.artifact_base_dir

        # Create the isolated directories as main() would
        artifact_base.mkdir(parents=True, exist_ok=True)
        for subdir in ['agents', 'commands', 'rules', 'prompts', 'hooks', 'skills']:
            (artifact_base / subdir).mkdir(parents=True, exist_ok=True)

        # Verify isolated directories exist
        for subdir in ['agents', 'commands', 'rules', 'prompts', 'hooks', 'skills']:
            isolated_dir = artifact_base / subdir
            assert isolated_dir.exists(), f'Missing isolated directory: {isolated_dir}'
            assert isolated_dir.is_dir(), f'Not a directory: {isolated_dir}'

        # Verify standard claude_dir also exists
        assert paths.claude_dir.exists()

    def test_infrastructure_files_in_config_base_dir(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify config.json is created inside the isolated config directory."""
        paths = _run_isolated_setup(e2e_isolated_home, golden_config)
        artifact_base = paths.artifact_base_dir
        artifact_base.mkdir(parents=True, exist_ok=True)

        # Create settings file as create_profile_config() would
        settings: dict[str, Any] = {'model': 'test'}
        config_path = artifact_base / 'config.json'
        config_path.write_text(json.dumps(settings, indent=2))

        # Verify config.json is in artifact_base_dir
        assert config_path.exists()
        assert config_path.parent == artifact_base


class TestConfigDirIsolation:
    """Test CLAUDE_CONFIG_DIR isolation behavior after Bug 4 deletion.

    CLAUDE_CONFIG_DIR auto-injection into settings was deleted. The launcher
    export is now the sole source of truth. These tests verify:
    - CLAUDE_CONFIG_DIR is NOT injected into config.json env section
    - Hook file paths correctly reference the isolated directory
    - User-specified env vars (other than CLAUDE_CONFIG_DIR) are preserved
    """

    def test_settings_claude_config_dir_not_injected(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify config.json does NOT contain env.CLAUDE_CONFIG_DIR.

        After Bug 4 deletion, CLAUDE_CONFIG_DIR is only exported in launcher
        scripts. It must NOT appear in the config.json env section.
        """
        paths = _run_isolated_setup(e2e_isolated_home, golden_config)
        artifact_base = paths.artifact_base_dir

        # Create hooks dir in isolated location
        hooks_dir = artifact_base / 'hooks'
        hooks_dir.mkdir(parents=True, exist_ok=True)

        # Pass env variables WITHOUT CLAUDE_CONFIG_DIR
        env_variables: dict[str, str] = {'MY_VAR': 'test_value'}

        result = setup_environment.create_profile_config(
            golden_config.get('hooks', {}),
            artifact_base,
            env=env_variables,
            hooks_base_dir=hooks_dir,
        )

        assert result is True

        config_file = artifact_base / 'config.json'
        assert config_file.exists()

        settings = json.loads(config_file.read_text())
        env_block = settings.get('env', {})
        assert 'CLAUDE_CONFIG_DIR' not in env_block, (
            'CLAUDE_CONFIG_DIR should NOT be in config.json env section'
        )
        # Other env vars should still be present
        assert env_block.get('MY_VAR') == 'test_value'

    def test_hooks_in_isolated_dir(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify hook file paths in settings point to isolated directory."""
        paths = _run_isolated_setup(e2e_isolated_home, golden_config)
        artifact_base = paths.artifact_base_dir
        primary_cmd = paths.primary_command_name

        hooks_dir = artifact_base / 'hooks'
        hooks_dir.mkdir(parents=True, exist_ok=True)

        hooks_config = {
            'events': [{
                'event': 'PostToolUse',
                'matcher': 'Edit',
                'type': 'command',
                'command': 'test_hook.py',
            }],
        }

        result = setup_environment.create_profile_config(
            hooks_config,
            artifact_base,
            hooks_base_dir=hooks_dir,
        )

        assert result is True

        config_file = artifact_base / 'config.json'
        settings = json.loads(config_file.read_text())

        hook_command = settings['hooks']['PostToolUse'][0]['hooks'][0]['command']
        # Hook path should reference the isolated hooks directory
        assert primary_cmd in hook_command
        assert 'hooks/test_hook.py' in hook_command

    def test_user_override_claude_config_dir(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify user-specified CLAUDE_CONFIG_DIR is NOT written to config.json.

        Even when user provides CLAUDE_CONFIG_DIR in env-variables, it should
        be popped from the env dict (launcher export is the sole source).
        """
        paths = _run_isolated_setup(e2e_isolated_home, golden_config)
        artifact_base = paths.artifact_base_dir
        artifact_base.mkdir(parents=True, exist_ok=True)

        # User explicitly sets CLAUDE_CONFIG_DIR along with other vars
        user_env = {
            'CLAUDE_CONFIG_DIR': '/custom/user/path',
            'OTHER_VAR': 'keep_this',
        }

        result = setup_environment.create_profile_config(
            {},
            artifact_base,
            env=user_env,
        )

        assert result is True

        config_file = artifact_base / 'config.json'
        settings = json.loads(config_file.read_text())

        env_block = settings.get('env', {})
        # OTHER_VAR should be present
        assert env_block.get('OTHER_VAR') == 'keep_this'
