"""E2E tests for auto-update controls on a machine with several toolbox profiles.

The Claude Code binary is machine-global, so the controls that hold it at a
pinned version (DISABLE_AUTOUPDATER, autoUpdates, CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL,
autoInstallIdeExtension) are machine-global too. These tests cover the
interaction between an installed base profile and an installed isolated
profile: a run removes the controls only when no installed profile pins a
version, and each run records its own pin in its profile manifest.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from unittest.mock import patch

if TYPE_CHECKING:
    from unittest.mock import MagicMock

import pytest

from scripts import setup_environment

PINNED_VERSION = '2.1.85'

CONTROLLED_SETTINGS_ENV = {
    'DISABLE_AUTOUPDATER': '1',
    'CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL': '1',
}
CONTROLLED_CLAUDE_JSON = {
    'autoUpdates': False,
    'autoInstallIdeExtension': False,
}


def _write_profile_manifest(directory: Path, name: str | None, pin: str | None) -> None:
    """Write the minimal profile manifest the pin registry reads."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'manifest.json').write_text(
        json.dumps({
            'name': name,
            'version': None,
            'claude_code_version': pin,
            'config_source': 'e2e-test',
            'config_source_url': None,
            'config_source_type': 'repo',
            'installed_at': '2026-01-01T00:00:00+00:00',
            'last_checked_at': None,
            'command_names': [name] if name else [],
        }),
        encoding='utf-8',
    )


def _seed_base_profile_controls(claude_dir: Path, home: Path) -> None:
    """Seed the machine-global control artifacts a pinned base run leaves behind."""
    (claude_dir / 'settings.json').write_text(
        json.dumps({'env': dict(CONTROLLED_SETTINGS_ENV)}), encoding='utf-8',
    )
    (home / '.claude.json').write_text(
        json.dumps(dict(CONTROLLED_CLAUDE_JSON)), encoding='utf-8',
    )


class TestPinnedBaseWithPinnedIsolatedProfile:
    """Scenario (a): a pinned isolated run must not strip the pinned base controls."""

    @patch('scripts.setup_environment.load_config_from_source')
    @patch('scripts.setup_environment.validate_all_config_files')
    @patch('scripts.setup_environment.install_claude', return_value=True)
    @patch('scripts.setup_environment.install_dependencies', return_value=[])
    @patch('scripts.setup_environment.process_resources')
    @patch('scripts.setup_environment.process_skills')
    @patch('scripts.setup_environment.configure_all_mcp_servers')
    @patch('scripts.setup_environment.set_all_os_env_variables', return_value=True)
    @patch('scripts.setup_environment.generate_env_loader_files', return_value={})
    @patch('scripts.setup_environment.create_launcher_script')
    @patch('scripts.setup_environment.register_global_command', return_value=True)
    @patch('scripts.setup_environment.find_command', return_value='/usr/bin/claude')
    @patch('scripts.setup_environment.is_admin', return_value=True)
    def test_pinned_isolated_run_keeps_base_settings_controls(
        self,
        mock_is_admin: MagicMock,
        mock_find_cmd: MagicMock,
        mock_register: MagicMock,
        mock_launcher: MagicMock,
        mock_env_loader: MagicMock,
        mock_os_env: MagicMock,
        mock_mcp: MagicMock,
        mock_skills: MagicMock,
        mock_resources: MagicMock,
        mock_deps: MagicMock,
        mock_install: MagicMock,
        mock_validate: MagicMock,
        mock_load: MagicMock,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """A pinned isolated run leaves every base-profile control untouched."""
        del mock_is_admin, mock_find_cmd, mock_register, mock_env_loader
        del mock_skills, mock_resources, mock_deps, mock_install
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']

        _write_profile_manifest(claude_dir, None, PINNED_VERSION)
        _seed_base_profile_controls(claude_dir, home)

        profile_dir = claude_dir / 'claude-personal'
        mock_launcher.return_value = (profile_dir / 'launch.sh', profile_dir / 'launch.sh')
        config: dict[str, Any] = {
            'name': 'Personal Profile',
            'command-names': ['claude-personal'],
            'command-defaults': {},
            'claude-code-version': PINNED_VERSION,
            'user-settings': {'theme': 'dark'},
        }
        mock_load.return_value = (config, 'personal.yaml')
        mock_validate.return_value = (True, [])
        mock_mcp.return_value = (
            True, [],
            {'global_count': 0, 'profile_count': 0, 'combined_count': 0, 'unchanged_count': 0},
        )

        with patch('sys.argv', ['setup_environment.py', 'personal', '--yes', '--skip-install']), \
             patch('sys.exit') as mock_exit:
            setup_environment.main()
            mock_exit.assert_not_called()

        settings = json.loads((claude_dir / 'settings.json').read_text())
        assert settings['env'] == CONTROLLED_SETTINGS_ENV, \
            'A pinned isolated run must not strip the base profile auto-update controls'
        assert json.loads((home / '.claude.json').read_text()) == CONTROLLED_CLAUDE_JSON

        # The isolated run still writes the machine-global controls itself.
        assert mock_os_env.call_args is not None
        os_env_written = mock_os_env.call_args[0][0]
        assert os_env_written['DISABLE_AUTOUPDATER'] == '1'
        assert os_env_written['CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL'] == '1'

        manifest = json.loads((profile_dir / 'manifest.json').read_text(encoding='utf-8'))
        assert manifest['name'] == 'claude-personal'
        assert manifest['claude_code_version'] == PINNED_VERSION


class TestPinnedBaseWithUnpinnedIsolatedProfile:
    """Scenario (b): an unpinned isolated run defers to the pinned base profile."""

    def test_unpinned_isolated_run_keeps_base_claude_json_and_schedules_no_deletion(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']

        _write_profile_manifest(claude_dir, None, PINNED_VERSION)
        _seed_base_profile_controls(claude_dir, home)

        scan = setup_environment._other_profile_pins(home, 'claude-personal')
        assert scan.pinned_profiles == ['base']
        other_profile_pinned = scan.other_profile_pinned
        machine_pinned = other_profile_pinned  # this run does not pin

        _, _, os_env, _, _ = setup_environment.apply_auto_update_settings(
            None, None, None, None, other_profile_pinned=other_profile_pinned,
        )
        assert os_env is None, 'No OS-level DISABLE_AUTOUPDATER deletion may be scheduled'
        _, _, os_env, _, _ = setup_environment.apply_ide_extension_settings(
            None, None, None, None, other_profile_pinned=other_profile_pinned,
        )
        assert os_env is None, \
            'No OS-level CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL deletion may be scheduled'

        setup_environment._run_stale_controls_cleanup(
            machine_pinned=machine_pinned, user_declared_keys=frozenset(),
        )

        claude_json = json.loads((home / '.claude.json').read_text())
        assert claude_json == CONTROLLED_CLAUDE_JSON, \
            'An unpinned run must keep the controls a pinned sibling profile needs'
        settings = json.loads((claude_dir / 'settings.json').read_text())
        assert settings['env'] == CONTROLLED_SETTINGS_ENV


class TestSingleUnpinnedProfile:
    """Scenario (c): with no pinned profile anywhere, the full sweep still runs."""

    def test_unpinned_lone_profile_sweeps_every_location(
        self, e2e_isolated_home: dict[str, Path],
    ) -> None:
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']

        _write_profile_manifest(claude_dir, None, None)
        _seed_base_profile_controls(claude_dir, home)
        isolated_dir = claude_dir / 'claude-personal'
        _write_profile_manifest(isolated_dir, 'claude-personal', None)
        (isolated_dir / 'settings.json').write_text(
            json.dumps({'env': dict(CONTROLLED_SETTINGS_ENV)}), encoding='utf-8',
        )
        (isolated_dir / '.claude.json').write_text(
            json.dumps(dict(CONTROLLED_CLAUDE_JSON)), encoding='utf-8',
        )

        scan = setup_environment._other_profile_pins(home, None)
        assert scan.other_profile_pinned is False

        _, _, os_env, _, _ = setup_environment.apply_auto_update_settings(
            None, None, None, None, other_profile_pinned=False,
        )
        assert os_env == {'DISABLE_AUTOUPDATER': None}
        _, _, os_env, _, _ = setup_environment.apply_ide_extension_settings(
            None, None, None, None, other_profile_pinned=False,
        )
        assert os_env == {'CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL': None}

        setup_environment._run_stale_controls_cleanup(
            machine_pinned=False, user_declared_keys=frozenset(),
        )

        for settings_path in (claude_dir / 'settings.json', isolated_dir / 'settings.json'):
            env_section = json.loads(settings_path.read_text()).get('env', {})
            assert 'DISABLE_AUTOUPDATER' not in env_section, settings_path
            assert 'CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL' not in env_section, settings_path
        for claude_json_path in (home / '.claude.json', isolated_dir / '.claude.json'):
            data = json.loads(claude_json_path.read_text())
            assert 'autoUpdates' not in data, claude_json_path
            assert 'autoInstallIdeExtension' not in data, claude_json_path


class TestBaseProfileManifest:
    """Scenario (d): a run without command-names records the base profile manifest."""

    @patch('scripts.setup_environment.load_config_from_source')
    @patch('scripts.setup_environment.validate_all_config_files')
    @patch('scripts.setup_environment.install_claude', return_value=True)
    @patch('scripts.setup_environment.install_dependencies', return_value=[])
    @patch('scripts.setup_environment.process_resources')
    @patch('scripts.setup_environment.process_skills')
    @patch('scripts.setup_environment.configure_all_mcp_servers')
    @patch('scripts.setup_environment.set_all_os_env_variables', return_value=True)
    @patch('scripts.setup_environment.generate_env_loader_files', return_value={})
    @patch('scripts.setup_environment.find_command', return_value='/usr/bin/claude')
    @patch('scripts.setup_environment.is_admin', return_value=True)
    def test_base_run_writes_manifest_with_pin(
        self,
        mock_is_admin: MagicMock,
        mock_find_cmd: MagicMock,
        mock_env_loader: MagicMock,
        mock_os_env: MagicMock,
        mock_mcp: MagicMock,
        mock_skills: MagicMock,
        mock_resources: MagicMock,
        mock_deps: MagicMock,
        mock_install: MagicMock,
        mock_validate: MagicMock,
        mock_load: MagicMock,
        e2e_isolated_home: dict[str, Path],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A non-isolated run writes ~/.claude/manifest.json recording its pin."""
        del mock_is_admin, mock_find_cmd, mock_env_loader, mock_os_env, mock_skills
        del mock_resources, mock_deps, mock_install
        claude_dir = e2e_isolated_home['claude_dir']

        config: dict[str, Any] = {
            'name': 'Base Profile',
            'version': '1.0.0',
            'claude-code-version': PINNED_VERSION,
            'user-settings': {'theme': 'dark'},
        }
        mock_load.return_value = (config, 'base.yaml')
        mock_validate.return_value = (True, [])
        mock_mcp.return_value = (
            True, [],
            {'global_count': 0, 'profile_count': 0, 'combined_count': 0, 'unchanged_count': 0},
        )

        with patch('sys.argv', ['setup_environment.py', 'base', '--yes', '--skip-install']), \
             patch('sys.exit') as mock_exit:
            setup_environment.main()
            mock_exit.assert_not_called()

        captured = capsys.readouterr()
        assert 'Step 19: Writing installation manifest' in captured.out

        manifest_path = claude_dir / 'manifest.json'
        assert manifest_path.exists(), 'A base-profile run must write ~/.claude/manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        assert manifest['name'] is None
        assert manifest['command_names'] == []
        assert manifest['claude_code_version'] == PINNED_VERSION
        assert manifest['version'] == '1.0.0'

        from tests.e2e.validators import validate_manifest

        errors = validate_manifest(manifest_path, config)
        assert not errors, 'Base manifest validation failed:\n' + '\n'.join(errors)

    @patch('scripts.setup_environment.load_config_from_source')
    @patch('scripts.setup_environment.validate_all_config_files')
    @patch('scripts.setup_environment.install_claude', return_value=True)
    @patch('scripts.setup_environment.install_dependencies', return_value=[])
    @patch('scripts.setup_environment.process_resources')
    @patch('scripts.setup_environment.process_skills')
    @patch('scripts.setup_environment.configure_all_mcp_servers')
    @patch('scripts.setup_environment.set_all_os_env_variables', return_value=True)
    @patch('scripts.setup_environment.generate_env_loader_files', return_value={})
    @patch('scripts.setup_environment.find_command', return_value='/usr/bin/claude')
    @patch('scripts.setup_environment.is_admin', return_value=True)
    def test_unpinned_base_run_defers_to_pinned_isolated_profile(
        self,
        mock_is_admin: MagicMock,
        mock_find_cmd: MagicMock,
        mock_env_loader: MagicMock,
        mock_os_env: MagicMock,
        mock_mcp: MagicMock,
        mock_skills: MagicMock,
        mock_resources: MagicMock,
        mock_deps: MagicMock,
        mock_install: MagicMock,
        mock_validate: MagicMock,
        mock_load: MagicMock,
        e2e_isolated_home: dict[str, Path],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """An unpinned base run leaves a pinned isolated profile's controls alone."""
        del mock_is_admin, mock_find_cmd, mock_env_loader, mock_skills, mock_resources
        del mock_deps, mock_install
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']

        isolated_dir = claude_dir / 'claude-personal'
        _write_profile_manifest(isolated_dir, 'claude-personal', PINNED_VERSION)
        (isolated_dir / 'settings.json').write_text(
            json.dumps({'env': dict(CONTROLLED_SETTINGS_ENV)}), encoding='utf-8',
        )
        (home / '.claude.json').write_text(
            json.dumps(dict(CONTROLLED_CLAUDE_JSON)), encoding='utf-8',
        )

        config: dict[str, Any] = {'name': 'Base Profile', 'user-settings': {'theme': 'dark'}}
        mock_load.return_value = (config, 'base.yaml')
        mock_validate.return_value = (True, [])
        mock_mcp.return_value = (
            True, [],
            {'global_count': 0, 'profile_count': 0, 'combined_count': 0, 'unchanged_count': 0},
        )

        with patch('sys.argv', ['setup_environment.py', 'base', '--yes', '--skip-install']), \
             patch('sys.exit') as mock_exit:
            setup_environment.main()
            mock_exit.assert_not_called()

        captured = capsys.readouterr()
        assert "Another installed profile pins a Claude Code version ('claude-personal')" in captured.out

        env_section = json.loads((isolated_dir / 'settings.json').read_text()).get('env', {})
        assert env_section == CONTROLLED_SETTINGS_ENV, \
            'An unpinned base run must keep the pinned isolated profile controls'
        assert json.loads((home / '.claude.json').read_text()) == CONTROLLED_CLAUDE_JSON

        # The unpinned run schedules no OS-level deletion while a sibling pins.
        assert mock_os_env.call_args is not None
        assert mock_os_env.call_args[0][0] == {}

        manifest = json.loads((claude_dir / 'manifest.json').read_text(encoding='utf-8'))
        assert manifest['claude_code_version'] is None
