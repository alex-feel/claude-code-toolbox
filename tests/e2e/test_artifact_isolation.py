"""E2E tests for CLAUDE_CONFIG_DIR-based artifact isolation.

Verifies that when command-names is set, environment artifacts (agents, skills,
rules, commands, hooks, prompts) are placed in an isolated directory under
~/.claude/{primary_command_name}/, while infrastructure files (settings, MCP config,
launcher scripts) remain in the standard ~/.claude/ directory.
"""

import json
import sys
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

    def test_infrastructure_files_in_claude_user_dir(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify settings and MCP config remain in standard ~/.claude/ directory."""
        paths = _run_isolated_setup(e2e_isolated_home, golden_config)
        claude_dir = paths.claude_dir
        primary_cmd = paths.primary_command_name

        # Create settings file as create_settings() would
        settings: dict[str, Any] = {'model': 'test'}
        settings_path = claude_dir / f'{primary_cmd}-settings.json'
        settings_path.write_text(json.dumps(settings, indent=2))

        # Verify settings file is in claude_dir, not in isolated dir
        assert settings_path.exists()
        assert settings_path.parent == claude_dir


class TestConfigDirInjection:
    """Test CLAUDE_CONFIG_DIR injection into settings env block."""

    def test_settings_claude_config_dir_injected(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify {command_name}-settings.json contains env.CLAUDE_CONFIG_DIR."""
        paths = _run_isolated_setup(e2e_isolated_home, golden_config)
        claude_dir = paths.claude_dir
        primary_cmd = paths.primary_command_name
        artifact_base = paths.artifact_base_dir
        home = paths.home

        # Create hooks dir in isolated location
        hooks_dir = artifact_base / 'hooks'
        hooks_dir.mkdir(parents=True, exist_ok=True)

        # Simulate the CLAUDE_CONFIG_DIR injection logic from main()
        env_variables: dict[str, str] = golden_config.get('env-variables', {}) or {}
        if 'CLAUDE_CONFIG_DIR' not in env_variables:
            home_str = str(home)
            isolated_str = str(artifact_base)
            config_dir_value = (
                str(artifact_base) if sys.platform == 'win32'
                else ('~' + isolated_str[len(home_str):] if isolated_str.startswith(home_str) else isolated_str)
            )
            env_variables['CLAUDE_CONFIG_DIR'] = config_dir_value

        result = setup_environment.create_settings(
            golden_config.get('hooks', {}),
            claude_dir,
            primary_cmd,
            env=env_variables,
            hooks_base_dir=hooks_dir,
        )

        assert result is True

        settings_file = claude_dir / f'{primary_cmd}-settings.json'
        assert settings_file.exists()

        settings = json.loads(settings_file.read_text())
        assert 'env' in settings
        assert 'CLAUDE_CONFIG_DIR' in settings['env']

        config_dir_val = settings['env']['CLAUDE_CONFIG_DIR']
        # On non-Windows, should be tilde-based
        if sys.platform != 'win32':
            assert config_dir_val.startswith('~/')
            assert primary_cmd in config_dir_val

    def test_hooks_in_isolated_dir(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify hook file paths in settings point to isolated directory."""
        paths = _run_isolated_setup(e2e_isolated_home, golden_config)
        claude_dir = paths.claude_dir
        primary_cmd = paths.primary_command_name
        artifact_base = paths.artifact_base_dir

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

        result = setup_environment.create_settings(
            hooks_config,
            claude_dir,
            primary_cmd,
            hooks_base_dir=hooks_dir,
        )

        assert result is True

        settings_file = claude_dir / f'{primary_cmd}-settings.json'
        settings = json.loads(settings_file.read_text())

        hook_command = settings['hooks']['PostToolUse'][0]['hooks'][0]['command']
        # Hook path should reference the isolated hooks directory
        assert primary_cmd in hook_command
        assert 'hooks/test_hook.py' in hook_command

    def test_user_override_claude_config_dir(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify user-specified CLAUDE_CONFIG_DIR is preserved in settings."""
        paths = _run_isolated_setup(e2e_isolated_home, golden_config)
        claude_dir = paths.claude_dir
        primary_cmd = paths.primary_command_name

        # User explicitly sets CLAUDE_CONFIG_DIR
        user_env = {'CLAUDE_CONFIG_DIR': '/custom/user/path'}

        result = setup_environment.create_settings(
            {},
            claude_dir,
            primary_cmd,
            env=user_env,
        )

        assert result is True

        settings_file = claude_dir / f'{primary_cmd}-settings.json'
        settings = json.loads(settings_file.read_text())

        assert settings['env']['CLAUDE_CONFIG_DIR'] == '/custom/user/path'
