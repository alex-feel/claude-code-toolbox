"""E2E tests for automatic auto-update management.

Validates that version pinning correctly injects auto-update disable controls
across all three targets, and that latest/absent versions do not inject controls.
"""

from __future__ import annotations

import json
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

import pytest
import yaml

from scripts import setup_environment
from tests.e2e.validators import validate_auto_update_controls

# The two environment controls a version pin writes: DISABLE_AUTOUPDATER
# stops the background updater, DISABLE_UPDATES also blocks manual
# `claude update` and `claude install`.
ENV_CONTROL_KEYS = ('DISABLE_AUTOUPDATER', 'DISABLE_UPDATES')


def _load_fixture_config(name: str) -> dict[str, Any]:
    """Load a fixture YAML config by name."""
    fixture_path = Path(__file__).parent / 'fixtures' / name
    with fixture_path.open('r', encoding='utf-8') as f:
        result: dict[str, Any] = yaml.safe_load(f)
    return result


class TestPinnedVersionInjectsControls:
    """Verify that pinned version injects auto-update controls into all targets."""

    def test_pinned_version_injects_all_targets(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        home = e2e_isolated_home['home']
        config = _load_fixture_config('pinned_version_config.yaml')

        # Extract config sections
        global_config = config.get('global-config')
        user_settings = config.get('user-settings')
        os_env_variables = config.get('os-env-variables')

        # Normalize version
        version_str = str(config.get('claude-code-version', '')).strip()
        claude_code_version_normalized = None if version_str.lower() == 'latest' else version_str

        # Apply auto-update settings
        gc, us, osev, warns, auto = setup_environment.apply_auto_update_settings(
            claude_code_version_normalized,
            global_config, user_settings, os_env_variables,
            other_profile_pinned=False,
        )

        # Verify all 3 targets injected, including the manual-update block
        assert gc is not None
        assert gc.get('autoUpdates') is False
        assert us is not None
        assert us.get('env', {}).get('DISABLE_AUTOUPDATER') == '1'
        assert us.get('env', {}).get('DISABLE_UPDATES') == '1'
        assert osev is not None
        assert osev.get('DISABLE_AUTOUPDATER') == '1'
        assert osev.get('DISABLE_UPDATES') == '1'

        # Write global config to the profile's own .claude.json (command-names present)
        primary_command = config.get('command-names', [None])[0]
        artifact_dir = home / '.claude' / primary_command if primary_command else None
        if artifact_dir:
            artifact_dir.mkdir(parents=True, exist_ok=True)

        if gc is not None:
            setup_environment.write_global_config(
                gc, artifact_base_dir=artifact_dir,
            )

        errors = validate_auto_update_controls(
            home, pinned=True, command_name=primary_command,
        )
        assert not errors, '\n'.join(errors)
        assert not (home / '.claude.json').exists(), 'The pinned isolated run must leave the base file alone'

    def test_pinned_version_shows_auto_injected_items(self) -> None:
        config = _load_fixture_config('pinned_version_config.yaml')
        version_str = str(config.get('claude-code-version', '')).strip()
        claude_code_version_normalized = None if version_str.lower() == 'latest' else version_str

        _, _, _, _, auto = setup_environment.apply_auto_update_settings(
            claude_code_version_normalized,
            config.get('global-config'), config.get('user-settings'),
            config.get('os-env-variables'),
            other_profile_pinned=False,
        )
        # global-config.autoUpdates, plus DISABLE_AUTOUPDATER and DISABLE_UPDATES
        # in each of user-settings.env and os-env-variables.
        assert len(auto) == 5
        assert any('global-config' in item for item in auto)
        assert sum('user-settings' in item for item in auto) == 2
        assert sum('os-env-variables' in item for item in auto) == 2
        assert any('DISABLE_AUTOUPDATER' in item for item in auto)
        assert any('DISABLE_UPDATES' in item for item in auto)


class TestLatestVersionNoControls:
    """Verify that latest/absent version does not inject controls."""

    def test_latest_version_does_not_inject(
        self, golden_config: dict[str, Any],
    ) -> None:
        version = golden_config.get('claude-code-version')
        version_str = str(version).strip() if version else ''
        normalized = None if not version_str or version_str.lower() == 'latest' else version_str

        gc, us, osev, _, auto = setup_environment.apply_auto_update_settings(
            normalized,
            golden_config.get('global-config'),
            golden_config.get('user-settings'),
            golden_config.get('os-env-variables'),
            other_profile_pinned=False,
        )

        assert not auto
        # Global config should not have autoUpdates injected
        if gc is not None:
            assert gc.get('autoUpdates') is not False

    def test_absent_version_does_not_inject(self) -> None:
        gc, us, osev, _, auto = setup_environment.apply_auto_update_settings(
            None, None, None, None,
            other_profile_pinned=False,
        )
        assert not auto


class TestAutoMarkerInDryRun:
    """Verify [auto] markers appear in dry-run output for pinned versions."""

    def test_auto_marker_shown_in_plan_display(self) -> None:
        import io

        plan = setup_environment.InstallationPlan(
            config_name='Test',
            config_source='test',
            config_source_type='repo',
            config_version='1.0',
            auto_injected_items=[
                'global-config.autoUpdates: false',
                'user-settings.env.DISABLE_AUTOUPDATER: "1"',
                'user-settings.env.DISABLE_UPDATES: "1"',
                'os-env-variables.DISABLE_AUTOUPDATER: "1"',
                'os-env-variables.DISABLE_UPDATES: "1"',
            ],
        )
        buf = io.StringIO()
        setup_environment.display_installation_summary(plan, output=buf)
        output = buf.getvalue()
        assert '[auto]' in output
        assert 'autoUpdates' in output
        assert 'DISABLE_AUTOUPDATER' in output
        assert 'DISABLE_UPDATES' in output

    def test_no_auto_marker_when_no_items(self) -> None:
        import io

        plan = setup_environment.InstallationPlan(
            config_name='Test',
            config_source='test',
            config_source_type='repo',
            config_version='1.0',
        )
        buf = io.StringIO()
        setup_environment.display_installation_summary(plan, output=buf)
        output = buf.getvalue()
        assert '[auto]' not in output


class TestUserConflictRespected:
    """Verify user conflicts are respected with warnings."""

    def test_user_autoupdates_true_respected(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        home = e2e_isolated_home['home']
        global_config: dict[str, Any] = {'autoUpdates': True, 'editorMode': 'vim'}

        gc, _, _, warns, _ = setup_environment.apply_auto_update_settings(
            '2.1.85', global_config, {}, {},
            other_profile_pinned=False,
        )
        assert gc is not None
        assert gc['autoUpdates'] is True
        assert len(warns) >= 1
        assert any('Respecting user value' in w for w in warns)

        # Write and verify file preserves user value
        setup_environment.write_global_config(gc)
        claude_json = home / '.claude.json'
        data = json.loads(claude_json.read_text())
        assert data['autoUpdates'] is True


class TestPinnedVersionProfileConfig:
    """Verify that injected user-settings.env flows to create_profile_config."""

    def test_user_settings_env_flows_to_profile_config(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        home = e2e_isolated_home['home']
        config_dir = home / '.claude' / 'auto-update-test'
        config_dir.mkdir(parents=True, exist_ok=True)

        user_settings: dict[str, Any] = {'env': {'TEST_VAR': 'value'}}

        # Apply auto-update injection into user-settings.env
        _, us, _, _, _ = setup_environment.apply_auto_update_settings(
            '2.1.85', {}, user_settings, {},
            other_profile_pinned=False,
        )

        # In isolated mode, the user-settings section is built into config.json
        assert us is not None
        setup_environment.create_profile_config({}, config_dir, user_settings=us)

        config_json = config_dir / 'config.json'
        assert config_json.exists()
        data = json.loads(config_json.read_text())
        assert data['env']['DISABLE_AUTOUPDATER'] == '1'
        assert data['env']['TEST_VAR'] == 'value'


class TestUnpinnedRemovalSemantics:
    """Verify unpinned runs preserve user declarations and sweep stale disk keys."""

    def test_unpinned_preserves_user_declared_env_and_sweep_cleans_disk(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """User-declared controls survive in memory; the disk sweep removes stale keys."""
        home = e2e_isolated_home['home']
        claude_dir = home / '.claude'

        # Pre-populate settings.json with both stale environment controls
        settings_path = claude_dir / 'settings.json'
        settings_path.write_text(json.dumps({
            'env': {'DISABLE_AUTOUPDATER': '1', 'DISABLE_UPDATES': '1', 'OTHER_VAR': 'keep'},
        }))

        # Apply with no version pin: user-declared controls are preserved
        gc, us, osev, warns, _ = setup_environment.apply_auto_update_settings(
            None, {},
            {'env': {'DISABLE_AUTOUPDATER': '1', 'DISABLE_UPDATES': '1', 'OTHER_VAR': 'keep'}},
            {},
            other_profile_pinned=False,
        )
        assert us is not None
        assert us['env']['DISABLE_AUTOUPDATER'] == '1', \
            'User-declared DISABLE_AUTOUPDATER must be preserved in memory'
        assert us['env']['DISABLE_UPDATES'] == '1', \
            'User-declared DISABLE_UPDATES must be preserved in memory'
        assert us['env']['OTHER_VAR'] == 'keep'
        assert not warns

        # Stale on-disk artifacts are removed by the Step 16 sweep helper
        setup_environment._cleanup_settings_json_env_controls(
            settings_path, ENV_CONTROL_KEYS,
        )
        data = json.loads(settings_path.read_text())
        assert 'DISABLE_AUTOUPDATER' not in data.get('env', {}), \
            'Stale DISABLE_AUTOUPDATER should be removed from disk by the sweep'
        assert 'DISABLE_UPDATES' not in data.get('env', {}), \
            'Stale DISABLE_UPDATES should be removed from disk by the sweep'
        assert data['env']['OTHER_VAR'] == 'keep'

    def test_unpinned_schedules_os_level_deletion_when_not_declared(self) -> None:
        """Both OS-level variables get deletion entries because neither has a disk sweep."""
        _, _, osev, _, _ = setup_environment.apply_auto_update_settings(
            None, {}, {}, {},
            other_profile_pinned=False,
        )
        assert osev is not None
        assert osev == {'DISABLE_AUTOUPDATER': None, 'DISABLE_UPDATES': None}, \
            'Unpinned run must schedule OS-level deletion for both auto-update controls'

    @pytest.mark.parametrize(
        ('declared_key', 'other_key'),
        [
            ('DISABLE_AUTOUPDATER', 'DISABLE_UPDATES'),
            ('DISABLE_UPDATES', 'DISABLE_AUTOUPDATER'),
        ],
    )
    def test_unpinned_sweep_preserves_declared_key_independently(
        self, e2e_isolated_home: dict[str, Path], declared_key: str, other_key: str,
    ) -> None:
        """The orchestrated sweep keeps exactly the declared key, per key, independently.

        Declaring one control key must never shield the other: only the
        declared key survives, and the undeclared sibling is still removed.
        """
        home = e2e_isolated_home['home']
        claude_dir = home / '.claude'

        settings_path = claude_dir / 'settings.json'
        settings_path.write_text(json.dumps({
            'env': {declared_key: '1', other_key: '1'},
        }))

        setup_environment.cleanup_stale_auto_update_controls(
            home, machine_pinned=False, user_declared_keys=frozenset({declared_key}), profile_dir=None,
        )

        data = json.loads(settings_path.read_text())
        assert data['env'][declared_key] == '1', \
            f'Declared key {declared_key} must survive the unpinned sweep'
        assert other_key not in data.get('env', {}), \
            f'Undeclared key {other_key} must be removed independently of {declared_key}'

    def test_unpinned_sweep_removes_both_undeclared_settings_keys(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """The orchestrated sweep removes every stale key the current YAML does not declare."""
        home = e2e_isolated_home['home']
        claude_dir = home / '.claude'

        settings_path = claude_dir / 'settings.json'
        settings_path.write_text(json.dumps({
            'env': {'DISABLE_AUTOUPDATER': '1', 'DISABLE_UPDATES': '1'},
        }))

        setup_environment.cleanup_stale_auto_update_controls(
            home, machine_pinned=False, user_declared_keys=frozenset(), profile_dir=None,
        )

        data = json.loads(settings_path.read_text())
        assert 'DISABLE_AUTOUPDATER' not in data.get('env', {}), \
            'Undeclared stale DISABLE_AUTOUPDATER must be removed by the unpinned sweep'
        assert 'DISABLE_UPDATES' not in data.get('env', {}), \
            'Undeclared stale DISABLE_UPDATES must be removed by the unpinned sweep'


class TestUnpinnedNullEnvControlFlow:
    """A null user-settings.env control is a deletion request the Step 16 sweep carries out in its own profile."""

    def test_null_env_control_does_not_shield_the_running_profile_copy(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """The base run removes its own stale copy and reports, without editing, the sibling's."""
        home = e2e_isolated_home['home']
        base_settings = home / '.claude' / 'settings.json'
        sibling_settings = home / '.claude' / 'sibling' / 'settings.json'
        sibling_settings.parent.mkdir(parents=True)
        for path in (base_settings, sibling_settings):
            path.write_text(json.dumps({'env': {'DISABLE_UPDATES': '1', 'KEEP': 'x'}}))

        declared = setup_environment._collect_user_declared_control_keys(
            {'env': {'DISABLE_UPDATES': None}}, global_config=None,
        )
        report = setup_environment._run_stale_controls_cleanup(
            machine_pinned=False, user_declared_keys=declared, profile_dir=None,
        )

        assert json.loads(base_settings.read_text()) == {'env': {'KEEP': 'x'}}, \
            'A null DISABLE_UPDATES must not keep the stale value in the running profile'
        assert json.loads(sibling_settings.read_text()) == {'env': {'DISABLE_UPDATES': '1', 'KEEP': 'x'}}, \
            "Another profile's file is never edited"
        assert report == [setup_environment.StaleControlCopy('sibling', sibling_settings, ('DISABLE_UPDATES',))]


class TestUnpinnedDeclaredGlobalConfigFlow:
    """Step 15 writes the YAML global-config, then the Step 16 sweep runs on the same machine."""

    @staticmethod
    def _run_steps_15_16(
        home: Path, global_config: dict[str, Any],
    ) -> tuple[Path, Path, list[setup_environment.StaleControlCopy]]:
        """Seed a sibling profile's stale control, write global-config, sweep; return both files and the report."""
        sibling = home / '.claude' / 'sibling' / '.claude.json'
        sibling.parent.mkdir(parents=True)
        sibling.write_text(json.dumps({'autoUpdates': False}))

        declared = setup_environment._collect_user_declared_control_keys(None, global_config=global_config)
        gc, _, _, _, _ = setup_environment.apply_auto_update_settings(
            None, global_config, {}, {},
            other_profile_pinned=False,
        )
        assert gc is not None
        setup_environment.write_global_config(gc)
        report = setup_environment._run_stale_controls_cleanup(
            machine_pinned=False, user_declared_keys=declared, profile_dir=None,
        )
        return home / '.claude.json', sibling, report

    def test_declared_false_survives_the_sweep(self, e2e_isolated_home: dict[str, Path]) -> None:
        """A global-config autoUpdates: false written by Step 15 is not removed by Step 16 and shields the sibling's report."""
        claude_json, sibling, report = self._run_steps_15_16(e2e_isolated_home['home'], {'autoUpdates': False})

        assert json.loads(claude_json.read_text())['autoUpdates'] is False, \
            'The declared autoUpdates: false must survive the unpinned sweep'
        assert json.loads(sibling.read_text()) == {'autoUpdates': False}
        assert report == []

    def test_declared_true_leaves_the_sibling_copy_reported_but_untouched(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """A global-config autoUpdates: true does not shield another profile's stale false from the report."""
        claude_json, sibling, report = self._run_steps_15_16(e2e_isolated_home['home'], {'autoUpdates': True})

        assert json.loads(claude_json.read_text())['autoUpdates'] is True
        assert json.loads(sibling.read_text()) == {'autoUpdates': False}, \
            "A stale autoUpdates: false in another profile's .claude.json is reported, never edited"
        assert report == [setup_environment.StaleControlCopy('sibling', sibling, ('autoUpdates',))]


class TestPinnedBaseFlowSequence:
    """Verify the pinned non-isolated write sequence keeps env controls on disk."""

    def test_pinned_non_isolated_sequence_keeps_env_controls(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Step 14 write -> Step 16 cleanup (non-isolated) -> Step 18 keeps all three keys.

        In non-isolated mode the injected controls live in user-settings.env
        and reach ~/.claude/settings.json via the Step 14 write. Step 18 writes
        only the statusLine/hooks delta, so it never touches the env block.
        """
        home = e2e_isolated_home['home']
        claude_dir = home / '.claude'

        # YAML with a pinned version and NO user-settings section
        config: dict[str, Any] = {'claude-code-version': '2.1.85'}

        gc, us, osev, _, _ = setup_environment.apply_auto_update_settings(
            '2.1.85', config.get('global-config'), config.get('user-settings'),
            config.get('os-env-variables'),
            other_profile_pinned=False,
        )
        gc, us, osev, _, _ = setup_environment.apply_ide_extension_settings(
            '2.1.85', gc, us, osev,
            other_profile_pinned=False,
        )

        # main() writes the injected user-settings dict back into config
        if us is not None:
            config['user-settings'] = us

        # Step 14: write user settings to the base ~/.claude/settings.json
        assert us is not None
        assert setup_environment.write_user_settings(us, claude_dir)
        data = json.loads((claude_dir / 'settings.json').read_text())
        assert data['env']['DISABLE_AUTOUPDATER'] == '1'
        assert data['env']['DISABLE_UPDATES'] == '1'
        assert data['env']['CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL'] == '1'

        # Step 16: pinned non-isolated cleanup must NOT sweep the base file
        setup_environment._run_stale_controls_cleanup(
            machine_pinned=True, user_declared_keys=frozenset(), profile_dir=None,
        )
        data = json.loads((claude_dir / 'settings.json').read_text())
        assert data['env']['DISABLE_AUTOUPDATER'] == '1', \
            'Pinned non-isolated Step 16 must not delete the run-written control'
        assert data['env']['DISABLE_UPDATES'] == '1', \
            'Pinned non-isolated Step 16 must not delete the run-written control'
        assert data['env']['CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL'] == '1', \
            'Pinned non-isolated Step 16 must not delete the run-written control'

        # Step 18: profile settings delta built from config the way main() does
        # (statusLine/hooks only; no env in the profile-owned key map)
        profile_config: dict[str, Any] = {
            camel_key: config[yaml_key]
            for yaml_key, camel_key in setup_environment._YAML_TO_CAMEL_PROFILE_KEYS.items()
            if yaml_key in config
        }
        delta = setup_environment._build_profile_settings(profile_config, claude_dir / 'hooks')
        setup_environment.write_profile_settings_to_settings(delta, claude_dir)

        # Final state: all three injected env keys present in ~/.claude/settings.json
        data = json.loads((claude_dir / 'settings.json').read_text())
        assert data['env']['DISABLE_AUTOUPDATER'] == '1'
        assert data['env']['DISABLE_UPDATES'] == '1'
        assert data['env']['CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL'] == '1'


class TestIsolatedInjectedEnvReachesConfigJson:
    """Verify injected user-settings.env reaches the isolated config.json."""

    def test_isolated_pinned_profile_config_includes_injected_env(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Isolated config.json env carries injected keys when YAML lacks user-settings."""
        home = e2e_isolated_home['home']
        config_dir = home / '.claude' / 'test-cmd'
        config_dir.mkdir(parents=True, exist_ok=True)

        # YAML with command-names, a pinned version, and NO user-settings
        config: dict[str, Any] = {
            'command-names': ['test-cmd'],
            'claude-code-version': '2.1.85',
        }

        _, us, _, _, _ = setup_environment.apply_auto_update_settings(
            '2.1.85', None, config.get('user-settings'), None,
            other_profile_pinned=False,
        )
        _, us, _, _, _ = setup_environment.apply_ide_extension_settings(
            '2.1.85', None, us, None,
            other_profile_pinned=False,
        )

        # main() writes the injected user-settings dict back into config
        if us is not None:
            config['user-settings'] = us

        # Step 18 isolated: user-settings is built into config.json; the
        # profile-owned keys (statusLine/hooks) are empty here.
        profile_config: dict[str, Any] = {
            camel_key: config[yaml_key]
            for yaml_key, camel_key in setup_environment._YAML_TO_CAMEL_PROFILE_KEYS.items()
            if yaml_key in config
        }
        setup_environment.create_profile_config(
            profile_config, config_dir, user_settings=config.get('user-settings'),
        )

        data = json.loads((config_dir / 'config.json').read_text())
        assert data['env']['DISABLE_AUTOUPDATER'] == '1'
        assert data['env']['DISABLE_UPDATES'] == '1'
        assert data['env']['CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL'] == '1'


class TestCrossLocationStaleCleanup:
    """Verify the per-file cleanup helper removes the controls from exactly the file it is given."""

    def test_helper_cleans_each_settings_json_it_is_given(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Called once per file, the helper removes both env controls from every one of them."""
        home = e2e_isolated_home['home']
        claude_dir = home / '.claude'

        # Create both stale controls in multiple locations
        for subdir_name in ['', 'aegis', 'myenv']:
            target_dir = claude_dir / subdir_name if subdir_name else claude_dir
            target_dir.mkdir(parents=True, exist_ok=True)
            settings_path = target_dir / 'settings.json'
            settings_path.write_text(json.dumps({
                'env': dict.fromkeys(ENV_CONTROL_KEYS, '1'),
            }))

        # Call helpers directly (not mocked by conftest)
        setup_environment._cleanup_settings_json_env_controls(
            claude_dir / 'settings.json', ENV_CONTROL_KEYS,
        )
        for subdir in claude_dir.iterdir():
            if subdir.is_dir():
                s = subdir / 'settings.json'
                if s.exists():
                    setup_environment._cleanup_settings_json_env_controls(s, ENV_CONTROL_KEYS)

        # Verify all locations cleaned of both controls
        for subdir_name in ['', 'aegis', 'myenv']:
            target_dir = claude_dir / subdir_name if subdir_name else claude_dir
            settings_path = target_dir / 'settings.json'
            if settings_path.exists():
                data = json.loads(settings_path.read_text())
                env_section = data.get('env', {})
                for key in ENV_CONTROL_KEYS:
                    assert key not in env_section, f'Stale {key} in {settings_path}'

    def test_cleanup_removes_empty_env_object(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Empty env: {} is cleaned up after both env controls are removed."""
        home = e2e_isolated_home['home']
        claude_dir = home / '.claude'

        settings_path = claude_dir / 'settings.json'
        settings_path.write_text(json.dumps({
            'env': dict.fromkeys(ENV_CONTROL_KEYS, '1'),
        }))

        setup_environment._cleanup_settings_json_env_controls(settings_path, ENV_CONTROL_KEYS)

        data = json.loads(settings_path.read_text())
        assert 'env' not in data, 'Empty env: {} should be cleaned up after removal'

    def test_helper_leaves_every_other_file_alone(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """The helper touches only the file it is given; a sibling profile's copy stays."""
        home = e2e_isolated_home['home']
        claude_dir = home / '.claude'

        # Create stale in both global and isolated locations
        claude_dir.mkdir(parents=True, exist_ok=True)
        (claude_dir / 'settings.json').write_text(json.dumps({
            'env': dict.fromkeys(ENV_CONTROL_KEYS, '1'),
        }))

        isolated_dir = claude_dir / 'myenv'
        isolated_dir.mkdir(parents=True, exist_ok=True)
        (isolated_dir / 'settings.json').write_text(json.dumps({
            'env': dict.fromkeys(ENV_CONTROL_KEYS, '1'),
        }))

        setup_environment._cleanup_settings_json_env_controls(
            claude_dir / 'settings.json', ENV_CONTROL_KEYS,
        )

        # Verify global settings cleaned of both controls
        data = json.loads((claude_dir / 'settings.json').read_text())
        env_section = data.get('env', {})
        for key in ENV_CONTROL_KEYS:
            assert key not in env_section

        # Isolated is NOT cleaned by this call (only when called for that path)
        data = json.loads((isolated_dir / 'settings.json').read_text())
        isolated_env = data.get('env', {})
        for key in ENV_CONTROL_KEYS:
            assert isolated_env.get(key) == '1'


class TestGlobalConfigSingleWrite:
    """Verify write_global_config() writes exactly one .claude.json: the running profile's."""

    def test_isolated_write_creates_only_the_profile_file(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """An isolated run writes ~/.claude/{cmd}/.claude.json and never creates ~/.claude.json."""
        home = e2e_isolated_home['home']
        artifact_dir = home / '.claude' / 'test-cmd'
        artifact_dir.mkdir(parents=True, exist_ok=True)

        global_config: dict[str, Any] = {'autoConnectIde': True, 'editorMode': 'vim'}

        result = setup_environment.write_global_config(
            global_config, artifact_base_dir=artifact_dir,
        )

        assert result is True
        isolated_json = json.loads((artifact_dir / '.claude.json').read_text())
        assert isolated_json['autoConnectIde'] is True
        assert isolated_json['editorMode'] == 'vim'
        assert not (home / '.claude.json').exists(), 'An isolated run must not create the base ~/.claude.json'

    def test_isolated_write_leaves_an_existing_base_file_unchanged(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """A base ~/.claude.json with an account keeps every byte when an isolated run deletes account keys."""
        home = e2e_isolated_home['home']
        artifact_dir = home / '.claude' / 'test-cmd'
        artifact_dir.mkdir(parents=True, exist_ok=True)
        base_json = home / '.claude.json'
        base_json.write_text(json.dumps({
            'oauthAccount': {'emailAddress': 'base@example.com'}, 'userID': 'base-user', 'editorMode': 'emacs',
        }))
        base_bytes = base_json.read_bytes()

        assert setup_environment.write_global_config(
            {'oauthAccount': None, 'userID': None, 'editorMode': 'vim'}, artifact_base_dir=artifact_dir,
        )

        assert base_json.read_bytes() == base_bytes
        assert json.loads((artifact_dir / '.claude.json').read_text()) == {'editorMode': 'vim'}

    def test_base_write_targets_only_the_base_file(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """A base run writes ~/.claude.json and no isolated .claude.json."""
        home = e2e_isolated_home['home']
        global_config: dict[str, Any] = {'showTurnDuration': True}

        result = setup_environment.write_global_config(global_config)

        assert result is True
        assert json.loads((home / '.claude.json').read_text()) == {'showTurnDuration': True}
        claude_dir = home / '.claude'
        for subdir in claude_dir.iterdir():
            if subdir.is_dir():
                assert not (subdir / '.claude.json').exists()

    def test_auto_updates_false_reaches_only_the_profile_file_when_pinned(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """A pinned isolated run writes autoUpdates: false into its own .claude.json only."""
        home = e2e_isolated_home['home']
        artifact_dir = home / '.claude' / 'test-cmd'
        artifact_dir.mkdir(parents=True, exist_ok=True)

        gc, _, _, _, _ = setup_environment.apply_auto_update_settings(
            '2.1.85', {'editorMode': 'vim'}, {}, {},
            other_profile_pinned=False,
        )
        assert gc is not None
        setup_environment.write_global_config(gc, artifact_base_dir=artifact_dir)

        isolated_json = json.loads((artifact_dir / '.claude.json').read_text())
        assert isolated_json['autoUpdates'] is False
        assert not (home / '.claude.json').exists()
        assert not validate_auto_update_controls(home, pinned=True, command_name='test-cmd')

    def test_profile_dir_equal_to_home_is_the_base_file(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Degenerate case: artifact_base_dir == home_dir writes the base ~/.claude.json once."""
        home = e2e_isolated_home['home']

        global_config: dict[str, Any] = {'autoConnectIde': True, 'editorMode': 'vim'}

        result = setup_environment.write_global_config(
            global_config, artifact_base_dir=home,
        )

        assert result is True
        home_json = json.loads((home / '.claude.json').read_text())
        assert home_json['autoConnectIde'] is True
        assert home_json['editorMode'] == 'vim'
        claude_dir = home / '.claude'
        for subdir in claude_dir.iterdir():
            if subdir.is_dir():
                assert not (subdir / '.claude.json').exists(), f'Unexpected .claude.json in {subdir}'


class TestStaleAutoUpdatesFalseCleanup:
    """Verify cleanup of stale autoUpdates: false from .claude.json files."""

    def test_no_global_config_cleans_stale(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Stale autoUpdates: false on disk is cleaned by helper."""
        home = e2e_isolated_home['home']
        claude_json = home / '.claude.json'
        claude_json.write_text(json.dumps({
            'autoUpdates': False, 'userID': 'test-user',
        }))

        # Call helper directly (not mocked)
        setup_environment._cleanup_claude_json_auto_updates(claude_json)

        data = json.loads(claude_json.read_text())
        assert 'autoUpdates' not in data, 'Stale autoUpdates: false should be removed'
        assert data['userID'] == 'test-user', 'Other keys should be preserved'

    def test_global_config_without_autoupdates_cleans_stale(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Stale autoUpdates: false cleaned when no autoUpdates key in YAML."""
        home = e2e_isolated_home['home']
        claude_json = home / '.claude.json'
        claude_json.write_text(json.dumps({
            'autoUpdates': False, 'editorMode': 'vim',
        }))

        setup_environment._cleanup_claude_json_auto_updates(claude_json)

        data = json.loads(claude_json.read_text())
        assert 'autoUpdates' not in data
        assert data['editorMode'] == 'vim'

    def test_preserves_autoupdates_true(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """User-set autoUpdates: true must NOT be removed."""
        home = e2e_isolated_home['home']
        claude_json = home / '.claude.json'
        claude_json.write_text(json.dumps({'autoUpdates': True}))

        setup_environment._cleanup_claude_json_auto_updates(claude_json)

        data = json.loads(claude_json.read_text())
        assert data['autoUpdates'] is True

    def test_helper_cleans_each_isolated_claude_json_it_is_given(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Called for a profile's own .claude.json, the helper removes the stale false there."""
        home = e2e_isolated_home['home']
        for name in ['aegis', 'myenv']:
            isolated_dir = home / '.claude' / name
            isolated_dir.mkdir(parents=True, exist_ok=True)
            (isolated_dir / '.claude.json').write_text(json.dumps({
                'autoUpdates': False, 'userID': f'{name}-user',
            }))

        for name in ['aegis', 'myenv']:
            path = home / '.claude' / name / '.claude.json'
            setup_environment._cleanup_claude_json_auto_updates(path)

        for name in ['aegis', 'myenv']:
            data = json.loads(
                (home / '.claude' / name / '.claude.json').read_text(),
            )
            assert 'autoUpdates' not in data
            assert data['userID'] == f'{name}-user'


class TestMcpClaudeConfigDirPropagation:
    """Verify CLAUDE_CONFIG_DIR is passed to MCP subprocess when isolated."""

    def test_http_propagates_config_dir(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """run_bash_command receives CLAUDE_CONFIG_DIR in extra_env."""
        from unittest.mock import patch

        home = e2e_isolated_home['home']
        artifact_dir = home / '.claude' / 'test-cmd'
        artifact_dir.mkdir(parents=True, exist_ok=True)

        captured_extra_envs: list[dict[str, str] | None] = []

        def mock_run_bash(
            command: str,
            capture_output: bool = True,
            login_shell: bool = False,
            extra_env: dict[str, str] | None = None,
        ) -> CompletedProcess[str]:
            _ = capture_output, login_shell
            captured_extra_envs.append(extra_env)
            return CompletedProcess(args=command, returncode=0, stdout='', stderr='')

        claude_path = str(home / '.local' / 'bin' / 'claude')
        with (
            patch.object(setup_environment, 'run_bash_command', side_effect=mock_run_bash),
            patch.object(
                setup_environment, 'find_command',
                side_effect=lambda cmd: claude_path if cmd == 'claude' else None,
            ),
            patch('platform.system', return_value='Windows'),
        ):
            server: dict[str, Any] = {
                'name': 'test-server',
                'transport': 'http',
                'url': 'http://localhost:3000',
                'scope': 'user',
            }

            setup_environment.configure_mcp_server(
                server, artifact_base_dir=artifact_dir,
            )

        # Verify at least one captured extra_env contains CLAUDE_CONFIG_DIR
        envs_with_config_dir = [
            env for env in captured_extra_envs
            if env is not None and 'CLAUDE_CONFIG_DIR' in env
        ]
        assert envs_with_config_dir, \
            'CLAUDE_CONFIG_DIR should be propagated to subprocess via extra_env'
        assert envs_with_config_dir[0]['CLAUDE_CONFIG_DIR'] == str(artifact_dir)

    def test_no_config_dir_without_artifact_base_dir(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        """No CLAUDE_CONFIG_DIR when artifact_base_dir is None."""
        from unittest.mock import patch

        home = e2e_isolated_home['home']

        captured_extra_envs: list[dict[str, str] | None] = []

        def mock_run_bash(
            command: str,
            capture_output: bool = True,
            login_shell: bool = False,
            extra_env: dict[str, str] | None = None,
        ) -> CompletedProcess[str]:
            _ = capture_output, login_shell
            captured_extra_envs.append(extra_env)
            return CompletedProcess(args=command, returncode=0, stdout='', stderr='')

        claude_path = str(home / '.local' / 'bin' / 'claude')
        with (
            patch.object(setup_environment, 'run_bash_command', side_effect=mock_run_bash),
            patch.object(
                setup_environment, 'find_command',
                side_effect=lambda cmd: claude_path if cmd == 'claude' else None,
            ),
            patch('platform.system', return_value='Windows'),
        ):
            server: dict[str, Any] = {
                'name': 'test-server',
                'transport': 'http',
                'url': 'http://localhost:3000',
                'scope': 'user',
            }

            setup_environment.configure_mcp_server(server)

        # No extra_env should contain CLAUDE_CONFIG_DIR
        for env in captured_extra_envs:
            if env is not None:
                assert 'CLAUDE_CONFIG_DIR' not in env, \
                    'CLAUDE_CONFIG_DIR should NOT be set without artifact_base_dir'
