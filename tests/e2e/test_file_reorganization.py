"""E2E tests for file reorganization into isolated subdirectories.

Verifies that when command-names is set, all infrastructure files (config.json,
manifest.json, mcp.json, launch.sh, start.ps1, start.cmd) are created inside
~/.claude/{cmd}/ with generic names (no command-name prefix).

Covers: Scenarios 9-13.
"""

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.setup_environment import create_launcher_script
from scripts.setup_environment import create_mcp_config_file
from scripts.setup_environment import create_profile_config
from scripts.setup_environment import register_global_command
from scripts.setup_environment import write_manifest
from tests.e2e.validators import _is_profile_scoped


def _resolve_path_template(template: str, paths: dict[str, Path], cmd: str) -> Path:
    """Resolve a path template with fixture values.

    Replaces {claude_dir}, {local_bin}, {cmd}, etc. with actual paths.

    Returns:
        Resolved Path object.
    """
    result = template
    for key, value in paths.items():
        result = result.replace(f'{{{key}}}', str(value))
    result = result.replace('{cmd}', cmd)
    return Path(result)


class TestFileReorganization:
    """Verify all files are placed in the correct isolated subdirectory."""

    def test_all_files_in_isolated_subdirectory(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Scenario 9: All infrastructure files created inside {cmd}/ subdirectory."""
        claude_dir = e2e_isolated_home['claude_dir']
        command_names: list[str] = golden_config['command-names']
        cmd = command_names[0]
        artifact_base_dir = claude_dir / cmd
        artifact_base_dir.mkdir(parents=True, exist_ok=True)

        # Create hooks dir for create_profile_config
        hooks_dir = artifact_base_dir / 'hooks'
        hooks_dir.mkdir(parents=True, exist_ok=True)

        # Create profile config (config.json)
        create_profile_config(
            {'hooks': golden_config.get('hooks', {}), 'model': golden_config.get('model')},
            artifact_base_dir,
            hooks_base_dir=hooks_dir,
        )

        # Create MCP config (mcp.json)
        mcp_path = artifact_base_dir / 'mcp.json'
        profile_servers = [
            s for s in golden_config.get('mcp-servers', [])
            if _is_profile_scoped(s)
        ]
        if profile_servers:
            create_mcp_config_file(profile_servers, mcp_path)

        # Create launcher scripts
        launcher_result = create_launcher_script(
            artifact_base_dir, cmd,
            system_prompt_file=golden_config.get('command-defaults', {}).get('system-prompt'),
            has_profile_mcp_servers=bool(profile_servers),
        )
        assert launcher_result is not None

        # Create manifest
        write_manifest(
            config_base_dir=artifact_base_dir,
            command_name=cmd,
            config_version=golden_config.get('version'),
            config_source='golden_config.yaml',
            config_source_type='local',
            config_source_url=None,
            command_names=command_names,
        )

        # Verify all expected files exist inside artifact_base_dir
        assert (artifact_base_dir / 'config.json').exists()
        assert (artifact_base_dir / 'mcp.json').exists()
        assert (artifact_base_dir / 'manifest.json').exists()
        assert (artifact_base_dir / 'launch.sh').exists()

        if sys.platform == 'win32':
            assert (artifact_base_dir / 'start.ps1').exists()
            assert (artifact_base_dir / 'start.cmd').exists()

        # Verify NO prefixed files in parent claude_dir
        parent_files = list(claude_dir.glob(f'{cmd}-*'))
        assert len(parent_files) == 0, (
            f'No prefixed files should exist in claude_dir, found: {parent_files}'
        )

        # Verify NO old-style launcher in parent
        assert not (claude_dir / f'launch-{cmd}.sh').exists()

    def test_generic_filenames_no_prefix(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Scenario 10: All filenames are generic (no command-name prefix)."""
        claude_dir = e2e_isolated_home['claude_dir']
        command_names: list[str] = golden_config['command-names']
        cmd = command_names[0]
        artifact_base_dir = claude_dir / cmd
        artifact_base_dir.mkdir(parents=True, exist_ok=True)

        hooks_dir = artifact_base_dir / 'hooks'
        hooks_dir.mkdir(parents=True, exist_ok=True)

        create_profile_config({}, artifact_base_dir, hooks_base_dir=hooks_dir)

        mcp_path = artifact_base_dir / 'mcp.json'
        # Provide a minimal server so create_mcp_config_file creates the file
        dummy_server = [{'name': 'test-server', 'command': 'echo', 'args': []}]
        create_mcp_config_file(dummy_server, mcp_path)

        write_manifest(
            config_base_dir=artifact_base_dir,
            command_name=cmd,
            config_version=None,
            config_source='test',
            config_source_type='local',
            config_source_url=None,
            command_names=command_names,
        )

        create_launcher_script(artifact_base_dir, cmd)

        # Verify generic names exist
        for expected_name in ['config.json', 'manifest.json', 'mcp.json', 'launch.sh']:
            assert (artifact_base_dir / expected_name).exists(), (
                f'Expected generic file {expected_name} in artifact_base_dir'
            )

        if sys.platform == 'win32':
            for expected_name in ['start.ps1', 'start.cmd']:
                assert (artifact_base_dir / expected_name).exists(), (
                    f'Expected generic file {expected_name} in artifact_base_dir'
                )

        # Verify NO old-format prefixed files anywhere
        old_patterns = [
            f'{cmd}-settings.json',
            f'{cmd}-mcp.json',
            f'{cmd}-manifest.json',
            f'{cmd}-update-available.json',
            f'launch-{cmd}.sh',
            f'start-{cmd}.ps1',
            f'start-{cmd}.cmd',
        ]
        all_files_claude = {p.name for p in claude_dir.rglob('*') if p.is_file()}
        for old_name in old_patterns:
            assert old_name not in all_files_claude, (
                f'Legacy prefixed file {old_name} should not exist'
            )

    def test_config_json_content_correctness(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Scenario 11: config.json contains correct keys and excludes user-settings content."""
        claude_dir = e2e_isolated_home['claude_dir']
        command_names: list[str] = golden_config['command-names']
        cmd = command_names[0]
        artifact_base_dir = claude_dir / cmd
        artifact_base_dir.mkdir(parents=True, exist_ok=True)

        hooks_dir = artifact_base_dir / 'hooks'
        hooks_dir.mkdir(parents=True, exist_ok=True)

        env_vars: dict[str, str] = {}
        raw_env = golden_config.get('env-variables', {})
        for k, v in raw_env.items():
            env_vars[k] = str(v)

        create_profile_config(
            {
                'hooks': golden_config.get('hooks', {}),
                'model': golden_config.get('model'),
                'permissions': golden_config.get('permissions'),
                'env': env_vars,
                'alwaysThinkingEnabled': golden_config.get('always-thinking-enabled'),
                'companyAnnouncements': golden_config.get('company-announcements'),
                'attribution': golden_config.get('attribution'),
                'statusLine': golden_config.get('status-line'),
                'effortLevel': golden_config.get('effort-level'),
            },
            artifact_base_dir,
            hooks_base_dir=hooks_dir,
        )

        config_path = artifact_base_dir / 'config.json'
        assert config_path.exists()
        content = json.loads(config_path.read_text())

        # Verify expected keys present
        assert 'hooks' in content
        assert 'env' in content
        assert 'permissions' in content
        assert 'model' in content
        assert content.get('alwaysThinkingEnabled') is True
        assert isinstance(content.get('companyAnnouncements'), list)
        assert isinstance(content.get('attribution'), dict)
        assert isinstance(content.get('statusLine'), dict)
        assert content.get('effortLevel') == 'low'

        # Verify env vars present but CLAUDE_CONFIG_DIR absent
        env_block = content.get('env', {})
        assert 'CLAUDE_CONFIG_DIR' not in env_block
        assert env_block.get('E2E_TEST_VAR') == 'test_value'
        assert env_block.get('E2E_ANOTHER_VAR') == 'another_value'
        assert env_block.get('E2E_INT_VAR') == '42'  # YAML int -> string conversion

        # Verify user-settings content NOT in config.json
        assert 'theme' not in content
        assert 'language' not in content
        assert 'apiKeyHelper' not in content

    def test_launcher_script_paths_correct(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Scenario 12: Launcher and wrapper scripts reference correct paths."""
        claude_dir = e2e_isolated_home['claude_dir']
        command_names: list[str] = golden_config['command-names']
        cmd = command_names[0]
        artifact_base_dir = claude_dir / cmd
        artifact_base_dir.mkdir(parents=True, exist_ok=True)

        profile_servers = [
            s for s in golden_config.get('mcp-servers', [])
            if _is_profile_scoped(s)
        ]

        launcher_result = create_launcher_script(
            artifact_base_dir, cmd,
            system_prompt_file='e2e-test-prompt.md',
            has_profile_mcp_servers=bool(profile_servers),
        )
        assert launcher_result is not None
        launcher_path, launch_script_path = launcher_result

        # Read launch.sh content
        launch_sh = artifact_base_dir / 'launch.sh'
        assert launch_sh.exists()
        launch_content = launch_sh.read_text()

        # Verify CLAUDE_CONFIG_DIR export
        assert f'export CLAUDE_CONFIG_DIR="$HOME/.claude/{cmd}"' in launch_content

        # Verify config.json reference (not old {cmd}-settings.json)
        assert f'$HOME/.claude/{cmd}/config.json' in launch_content
        assert f'{cmd}-settings.json' not in launch_content

        # Verify mcp.json reference (not old {cmd}-mcp.json)
        assert f'$HOME/.claude/{cmd}/mcp.json' in launch_content
        assert f'{cmd}-mcp.json' not in launch_content

        if sys.platform == 'win32':
            # Verify start.ps1 references launch.sh in correct directory
            ps1_path = artifact_base_dir / 'start.ps1'
            assert ps1_path.exists()
            ps1_content = ps1_path.read_text()
            assert f'.claude/{cmd}/launch.sh' in ps1_content or 'launch.sh' in ps1_content

            # Verify start.cmd references launch.sh
            cmd_path = artifact_base_dir / 'start.cmd'
            assert cmd_path.exists()
            cmd_content = cmd_path.read_text()
            assert 'launch.sh' in cmd_content

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only global wrappers')
    def test_global_wrappers_reference_correct_paths_windows(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Scenario 13 (Windows): Global wrappers in ~/.local/bin/ reference correct paths."""
        claude_dir = e2e_isolated_home['claude_dir']
        local_bin = e2e_isolated_home['local_bin']
        command_names: list[str] = golden_config['command-names']
        cmd = command_names[0]
        artifact_base_dir = claude_dir / cmd
        artifact_base_dir.mkdir(parents=True, exist_ok=True)

        launcher_result = create_launcher_script(artifact_base_dir, cmd)
        assert launcher_result is not None
        launcher_path, launch_script_path = launcher_result

        register_global_command(
            launcher_path, cmd,
            additional_names=command_names[1:] if len(command_names) > 1 else None,
            launch_script_path=launch_script_path,
        )

        # Git Bash wrapper should reference launch.sh in isolated dir
        bash_wrapper = local_bin / cmd
        if bash_wrapper.exists():
            bash_content = bash_wrapper.read_text()
            assert f'.claude/{cmd}/launch.sh' in bash_content

        # CMD wrapper should reference launch.sh
        cmd_wrapper = local_bin / f'{cmd}.cmd'
        if cmd_wrapper.exists():
            cmd_content = cmd_wrapper.read_text()
            assert 'launch.sh' in cmd_content

        # PowerShell wrapper should reference start.ps1 in the isolated dir
        ps1_wrapper = local_bin / f'{cmd}.ps1'
        if ps1_wrapper.exists():
            ps1_content = ps1_wrapper.read_text()
            # The wrapper uses absolute paths, so check for the {cmd}/start.ps1 segment
            assert f'{cmd}\\start.ps1' in ps1_content or f'{cmd}/start.ps1' in ps1_content

    @pytest.mark.skipif(sys.platform == 'win32', reason='Unix-only symlink test')
    def test_global_wrappers_reference_correct_paths_unix(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Scenario 13 (Unix): Global symlinks in ~/.local/bin/ point to correct paths."""
        claude_dir = e2e_isolated_home['claude_dir']
        local_bin = e2e_isolated_home['local_bin']
        command_names: list[str] = golden_config['command-names']
        cmd = command_names[0]
        artifact_base_dir = claude_dir / cmd
        artifact_base_dir.mkdir(parents=True, exist_ok=True)

        launcher_result = create_launcher_script(artifact_base_dir, cmd)
        assert launcher_result is not None
        launcher_path, launch_script_path = launcher_result

        register_global_command(
            launcher_path, cmd,
            additional_names=command_names[1:] if len(command_names) > 1 else None,
            launch_script_path=launch_script_path,
        )

        symlink_path = local_bin / cmd
        assert symlink_path.exists(), f'Symlink not created at {symlink_path}'
        assert symlink_path.is_symlink(), f'{symlink_path} should be a symlink'

        # Resolve and verify the symlink target is inside the isolated dir
        target = symlink_path.resolve()
        expected_target = (artifact_base_dir / 'launch.sh').resolve()
        assert target == expected_target, (
            f'Symlink target {target} does not match expected {expected_target}'
        )
