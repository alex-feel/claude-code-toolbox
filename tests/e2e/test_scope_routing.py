"""E2E tests for scope-based routing of settings and config files.

Verifies that the presence or absence of command-names in the resolved
configuration determines where the user-settings content is written.

- Isolated mode (command-names present): the user-settings section is built
  into the isolated profile's config.json via create_profile_config(). The
  toolbox never writes ~/.claude/{cmd}/settings.json; that file is owned by
  Claude Code (user layer), not the toolbox.
- Non-isolated mode (command-names absent): the user-settings section is
  deep-merged into the shared ~/.claude/settings.json via write_user_settings().

Covers: Scenarios 1-8 (scope-based routing) and Scenario 18 (preservation).
"""

import json
from pathlib import Path
from typing import Any

import yaml

from scripts import setup_environment
from scripts.setup_environment import _merge_configs
from scripts.setup_environment import create_profile_config
from scripts.setup_environment import write_user_settings


def _load_fixture(name: str) -> dict[str, Any]:
    """Load a YAML fixture from the fixtures directory."""
    fixture_path = Path(__file__).parent / 'fixtures' / name
    with fixture_path.open('r', encoding='utf-8') as f:
        result: dict[str, Any] = yaml.safe_load(f)
    return result


def _resolve_fixture(
    name: str,
) -> tuple[dict[str, Any], list[setup_environment.InheritanceChainEntry]]:
    """Load and resolve inheritance for a YAML fixture."""
    fixture_path = Path(__file__).parent / 'fixtures' / name
    config = _load_fixture(name)
    return setup_environment.resolve_config_inheritance(config, str(fixture_path))


class TestScopeBasedRouting:
    """Verify user-settings content is routed to the correct file based on command-names."""

    def test_isolated_config_settings_in_config_json(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Scenario 1: Config WITH command-names builds user-settings into config.json."""
        config = _load_fixture('scope_isolated.yaml')
        claude_dir = e2e_isolated_home['claude_dir']

        command_names = config['command-names']
        primary_cmd = command_names[0]
        artifact_base_dir = claude_dir / primary_cmd
        artifact_base_dir.mkdir(parents=True, exist_ok=True)

        create_profile_config({}, artifact_base_dir, user_settings=config['user-settings'])

        isolated_config = artifact_base_dir / 'config.json'
        assert isolated_config.exists(), (
            f'config.json not created in isolated dir: {isolated_config}'
        )

        content = json.loads(isolated_config.read_text())
        assert content.get('theme') == 'dark'
        assert content.get('language') == 'english'

        # The toolbox does NOT write an isolated settings.json in isolated mode.
        assert not (artifact_base_dir / 'settings.json').exists(), (
            'toolbox must not write an isolated settings.json in isolated mode'
        )

        standard_settings = claude_dir / 'settings.json'
        assert not standard_settings.exists(), (
            'settings.json should NOT exist in standard claude_dir for isolated config'
        )

    def test_standard_config_settings_in_claude_dir(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Scenario 2: Config WITHOUT command-names writes settings.json to standard dir."""
        config = _load_fixture('scope_standard.yaml')
        claude_dir = e2e_isolated_home['claude_dir']

        assert 'command-names' not in config

        write_user_settings(config['user-settings'], claude_dir)

        standard_settings = claude_dir / 'settings.json'
        assert standard_settings.exists(), (
            f'settings.json not created in standard dir: {standard_settings}'
        )

        content = json.loads(standard_settings.read_text())
        assert content.get('theme') == 'light'

        # No subdirectories should be created
        subdirs = [p for p in claude_dir.iterdir() if p.is_dir()]
        assert len(subdirs) == 0, (
            f'No subdirectories expected in claude_dir, found: {subdirs}'
        )

    def test_child_inherits_command_names_from_parent(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Scenario 3: Child inherits parent's command-names via _merge_configs parent.copy()."""
        resolved, _ = _resolve_fixture('scope_child_inherits.yaml')

        assert 'command-names' in resolved, (
            'command-names must propagate from parent to child'
        )
        assert resolved['command-names'] == ['parent-cmd']

        # Without merge-keys, child's user-settings REPLACES parent's
        assert resolved['user-settings'] == {'language': 'french'}

        # Verify routing goes to config.json in the isolated dir
        claude_dir = e2e_isolated_home['claude_dir']
        primary_cmd = resolved['command-names'][0]
        artifact_base_dir = claude_dir / primary_cmd
        artifact_base_dir.mkdir(parents=True, exist_ok=True)

        create_profile_config({}, artifact_base_dir, user_settings=resolved['user-settings'])

        isolated_config = artifact_base_dir / 'config.json'
        assert isolated_config.exists()
        assert json.loads(isolated_config.read_text()).get('language') == 'french'

        assert not (artifact_base_dir / 'settings.json').exists()
        assert not (claude_dir / 'settings.json').exists()

    def test_merge_keys_preserves_command_names_merges_selected(
        self,
    ) -> None:
        """Scenario 4: merge-keys selectively merges listed keys; command-names propagated."""
        resolved, _ = _resolve_fixture('scope_child_mergekeys.yaml')

        # command-names always propagated from parent
        assert resolved['command-names'] == ['parent-cmd']

        # user-settings MERGED (in merge-keys list)
        user_settings = resolved['user-settings']
        assert user_settings.get('theme') == 'dark', (
            'Parent theme should be merged into child'
        )
        assert user_settings.get('language') == 'spanish', (
            'Child language should be present'
        )

        # hooks NOT in merge-keys, so child's hooks REPLACE parent's (parent has none)
        assert 'hooks' in resolved
        events = resolved['hooks']['events']
        assert len(events) == 1
        assert events[0]['event'] == 'PostToolUse'

    def test_child_cannot_escape_isolation(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Scenario 5: Child without command-names key still inherits parent's isolation."""
        resolved, _ = _resolve_fixture('scope_child_inherits.yaml')

        # Child config has NO command-names key, but parent has it
        child_config = _load_fixture('scope_child_inherits.yaml')
        assert 'command-names' not in child_config, (
            'Child fixture must NOT define command-names directly'
        )

        # After inheritance resolution, command-names is present from parent
        assert 'command-names' in resolved
        assert resolved['command-names'] == ['parent-cmd']

        # Routing must build config.json in the isolated dir
        claude_dir = e2e_isolated_home['claude_dir']
        primary_cmd = resolved['command-names'][0]
        artifact_base_dir = claude_dir / primary_cmd
        artifact_base_dir.mkdir(parents=True, exist_ok=True)

        create_profile_config({}, artifact_base_dir, user_settings=resolved['user-settings'])

        assert (artifact_base_dir / 'config.json').exists()
        assert not (artifact_base_dir / 'settings.json').exists()
        assert not (claude_dir / 'settings.json').exists()

    def test_explicit_null_deisolates(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Scenario 6: Explicit null command-names in child de-isolates to standard scope.

        _merge_configs uses result[key] = value for non-merge keys, so
        command-names: null in the child sets the key to None (not deleted).
        The routing logic checks truthiness: None is falsy, so no isolation.
        """
        resolved, _ = _resolve_fixture('scope_child_nullcmd.yaml')

        # command-names should be None (null from YAML)
        cmd_names = resolved.get('command-names')
        assert cmd_names is None, (
            f'Expected command-names to be None after null override, got: {cmd_names}'
        )

        # Routing: command-names is falsy -> standard scope
        claude_dir = e2e_isolated_home['claude_dir']
        settings_target = claude_dir  # No isolation

        write_user_settings(resolved['user-settings'], settings_target)

        standard_settings = claude_dir / 'settings.json'
        assert standard_settings.exists()

        content = json.loads(standard_settings.read_text())
        assert content.get('theme') == 'light'

    def test_non_interference_between_configs(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Scenario 7: Independent configs produce isolated outputs without cross-contamination."""
        claude_dir = e2e_isolated_home['claude_dir']

        configs: list[tuple[str, dict[str, Any]]] = [
            ('cmd-a', {'theme': 'dark'}),
            ('cmd-b', {'theme': 'light'}),
        ]

        for cmd, user_settings in configs:
            target = claude_dir / cmd
            target.mkdir(parents=True, exist_ok=True)
            create_profile_config({}, target, user_settings=user_settings)

        config_a = json.loads((claude_dir / 'cmd-a' / 'config.json').read_text())
        config_b = json.loads((claude_dir / 'cmd-b' / 'config.json').read_text())

        assert config_a == {'theme': 'dark'}
        assert config_b == {'theme': 'light'}

    def test_no_user_settings_no_settings_json(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Scenario 8: Isolated config never yields a toolbox-written settings.json.

        The user-settings section is built into config.json, so the isolated
        directory receives config.json but never a toolbox-written
        settings.json (that file is Claude Code's user layer, not the
        toolbox's).
        """
        config = _load_fixture('scope_nouser.yaml')
        claude_dir = e2e_isolated_home['claude_dir']

        assert config['command-names'] == ['nousercmd']

        primary_cmd = config['command-names'][0]
        artifact_base_dir = claude_dir / primary_cmd
        artifact_base_dir.mkdir(parents=True, exist_ok=True)

        create_profile_config({}, artifact_base_dir, user_settings=config.get('user-settings'))

        # The user-settings model lands in config.json ...
        isolated_config = artifact_base_dir / 'config.json'
        assert isolated_config.exists()
        assert json.loads(isolated_config.read_text()).get('model') == 'sonnet'

        # ... and no toolbox-written settings.json exists anywhere.
        assert not (artifact_base_dir / 'settings.json').exists(), (
            'toolbox must not write an isolated settings.json in isolated mode'
        )
        assert not (claude_dir / 'settings.json').exists()


class TestScopePreservation:
    """Verify non-isolated configurations are unaffected by the reorganization."""

    def test_non_isolated_config_no_subdirectory(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Scenario 18: Non-isolated config writes to standard location with no subdirs."""
        config = _load_fixture('scope_standard.yaml')
        claude_dir = e2e_isolated_home['claude_dir']

        assert 'command-names' not in config

        write_user_settings(config['user-settings'], claude_dir)

        # Standard settings exist
        standard_settings = claude_dir / 'settings.json'
        assert standard_settings.exists()

        content = json.loads(standard_settings.read_text())
        assert content.get('theme') == 'light'

        # No subdirectories created
        subdirs = [p for p in claude_dir.iterdir() if p.is_dir()]
        assert len(subdirs) == 0, (
            f'Non-isolated config must not create subdirectories, found: {subdirs}'
        )

        # No infrastructure files created
        for f in ['config.json', 'manifest.json', 'mcp.json']:
            assert not (claude_dir / f).exists(), (
                f'{f} should not exist for non-isolated config'
            )


class TestMergeConfigsNullHandling:
    """Verify _merge_configs behavior with null values for top-level keys."""

    def test_null_value_sets_key_to_none(self) -> None:
        """Confirm that _merge_configs sets key to None (not deleted) for null child values."""
        parent: dict[str, Any] = {'command-names': ['parent-cmd'], 'name': 'Parent'}
        child: dict[str, Any] = {'command-names': None, 'name': 'Child'}

        result = _merge_configs(parent, child)

        # _merge_configs uses result[key] = value, so None is set explicitly
        assert 'command-names' in result
        assert result['command-names'] is None

    def test_absent_key_inherits_from_parent(self) -> None:
        """Confirm that missing keys in child are inherited from parent via parent.copy()."""
        parent: dict[str, Any] = {'command-names': ['parent-cmd'], 'name': 'Parent'}
        child: dict[str, Any] = {'name': 'Child'}

        result = _merge_configs(parent, child)

        assert result['command-names'] == ['parent-cmd']
        assert result['name'] == 'Child'
