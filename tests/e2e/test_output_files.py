"""E2E tests for output file content verification.

These tests validate that JSON files are created with correct structure
and content according to the golden configuration.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.setup_environment import configure_all_mcp_servers
from scripts.setup_environment import create_mcp_config_file
from scripts.setup_environment import create_profile_config
from scripts.setup_environment import write_user_settings
from tests.e2e.expected.common import EXPECTED_JSON_KEYS
from tests.e2e.validators import validate_mcp_json
from tests.e2e.validators import validate_settings
from tests.e2e.validators import validate_settings_json


class TestOutputFiles:
    """Test output file content and structure."""

    def test_settings_json_structure(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify settings.json has correct structure and content.

        Uses validate_settings from validators.py.
        Checks: model, permissions, env, hooks, alwaysThinkingEnabled,
        companyAnnouncements, attribution, statusLine.
        """
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']

        # Create settings
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

        # File is written to config_base_dir as config.json
        settings_path = claude_dir / 'config.json'

        # Validate using validators.py
        errors = validate_settings(settings_path, golden_config)
        assert not errors, 'settings.json validation failed:\n' + '\n'.join(errors)

    def test_settings_has_expected_keys(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify settings.json contains all expected top-level keys.

        Uses EXPECTED_JSON_KEYS['settings'] for reference.
        """
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']

        # Create settings
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

        # File is written to config_base_dir as config.json
        settings_path = claude_dir / 'config.json'

        # Load and check keys
        data = json.loads(settings_path.read_text())
        expected_keys = EXPECTED_JSON_KEYS['settings']

        missing_keys = [k for k in expected_keys if k not in data]
        assert not missing_keys, f'Missing expected keys in settings.json: {missing_keys}'

    def test_mcp_json_structure(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify {cmd}-mcp.json has correct structure.

        Uses validate_mcp_json from validators.py.
        Checks: mcpServers key, server configurations, transport-specific fields.
        """
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        # Create MCP config
        mcp_path = claude_dir / f'{cmd}-mcp.json'

        # Configure MCP servers (extracts profile-scoped servers)
        _, profile_servers, _ = configure_all_mcp_servers(
            servers=golden_config.get('mcp-servers', []),
            profile_mcp_config_path=mcp_path,
        )

        # Create the MCP config file
        create_mcp_config_file(
            servers=profile_servers,
            config_path=mcp_path,
        )

        # Validate using validators.py
        errors = validate_mcp_json(mcp_path, golden_config)
        assert not errors, 'mcp.json validation failed:\n' + '\n'.join(errors)

    def test_mcp_json_has_mcp_servers_key(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify {cmd}-mcp.json has required mcpServers key."""
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']
        mcp_path = claude_dir / f'{cmd}-mcp.json'

        # Configure servers
        _, profile_servers, _ = configure_all_mcp_servers(
            servers=golden_config.get('mcp-servers', []),
            profile_mcp_config_path=mcp_path,
        )

        # Create the file
        create_mcp_config_file(
            servers=profile_servers,
            config_path=mcp_path,
        )

        data = json.loads(mcp_path.read_text())
        assert 'mcpServers' in data, "Missing 'mcpServers' key in mcp.json"
        assert isinstance(data['mcpServers'], dict), "'mcpServers' must be a dict"

    def test_user_settings_json_merge(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify user-settings are correctly merged into settings.json.

        Uses validate_settings_json from validators.py.
        Checks: Values from golden_config['user-settings'] are present.
        """
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']
        user_settings = golden_config.get('user-settings', {})

        if not user_settings:
            pytest.skip('No user-settings in golden_config')

        # Write user settings
        write_user_settings(user_settings, claude_dir)

        settings_path = claude_dir / 'settings.json'

        # Validate using validators.py
        errors = validate_settings_json(settings_path, golden_config)
        assert not errors, 'settings.json validation failed:\n' + '\n'.join(errors)

    def test_permissions_structure_complete(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify permissions in settings has all required arrays.

        Checks: defaultMode, allow, deny, ask arrays present with expected values.
        """
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']

        create_profile_config(
            hooks={},
            config_base_dir=claude_dir,
            model=None,
            permissions=golden_config.get('permissions'),
            env=None,

            always_thinking_enabled=None,
            company_announcements=None,
            attribution=None,
            status_line=None,
            effort_level=None,
        )

        # File is written to config_base_dir as config.json
        settings_path = claude_dir / 'config.json'

        data = json.loads(settings_path.read_text())

        if 'permissions' in golden_config:
            assert 'permissions' in data, 'Missing permissions block'

            expected_perm_keys = EXPECTED_JSON_KEYS['permissions']
            for key in expected_perm_keys:
                if key in golden_config['permissions']:
                    assert key in data['permissions'], f'Missing permissions.{key}'


class TestManifestFile:
    """Test manifest file creation and content."""

    def test_manifest_json_created(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify {cmd}-manifest.json is created with correct structure."""
        from scripts.setup_environment import classify_config_source
        from scripts.setup_environment import resolve_config_source_url
        from scripts.setup_environment import write_manifest

        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        config_source = 'e2e-test'
        config_source_type = classify_config_source(config_source)
        config_source_url = resolve_config_source_url(config_source, config_source_type)

        write_manifest(
            config_base_dir=claude_dir,
            command_name=cmd,
            config_version=str(golden_config.get('version', '')).strip() or None,
            config_source=config_source,
            config_source_type=config_source_type,
            config_source_url=config_source_url,
            command_names=golden_config['command-names'],
        )

        manifest_path = claude_dir / 'manifest.json'

        from tests.e2e.validators import validate_manifest

        errors = validate_manifest(manifest_path, golden_config)
        assert not errors, 'Manifest validation failed:\n' + '\n'.join(errors)

    def test_manifest_has_all_required_fields(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify manifest contains all required fields."""
        from scripts.setup_environment import write_manifest

        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        write_manifest(
            config_base_dir=claude_dir,
            command_name=cmd,
            config_version='1.0.0',
            config_source='test-config',
            config_source_type='repo',
            config_source_url='https://example.com/config.yaml',
            command_names=[cmd],
        )

        manifest_path = claude_dir / 'manifest.json'
        data = json.loads(manifest_path.read_text(encoding='utf-8'))

        required_fields = [
            'name', 'version', 'config_source', 'config_source_url',
            'config_source_type', 'installed_at', 'last_checked_at', 'command_names',
        ]
        missing = [f for f in required_fields if f not in data]
        assert not missing, f'Missing fields in manifest: {missing}'

    def test_manifest_source_classification(
        self,
    ) -> None:
        """Verify config source classification logic."""
        from scripts.setup_environment import classify_config_source

        # URL sources
        assert classify_config_source('https://example.com/config.yaml') == 'url'
        assert classify_config_source('http://example.com/config.yaml') == 'url'

        # Repo sources (bare names)
        assert classify_config_source('python.yaml') == 'repo'
        assert classify_config_source('python') == 'repo'
        assert classify_config_source('my-env') == 'repo'

        # Local sources (paths)
        assert classify_config_source('/home/user/config.yaml') == 'local'
        assert classify_config_source('./config.yaml') == 'local'
        assert classify_config_source('../configs/env.yaml') == 'local'

    def test_manifest_overwrites_on_reinstall(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify manifest is overwritten when setup runs again."""
        from scripts.setup_environment import write_manifest

        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        # Write manifest with version 1.0.0
        write_manifest(
            config_base_dir=claude_dir,
            command_name=cmd,
            config_version='1.0.0',
            config_source='test',
            config_source_type='repo',
            config_source_url=None,
            command_names=[cmd],
        )

        # Write manifest again with version 2.0.0
        write_manifest(
            config_base_dir=claude_dir,
            command_name=cmd,
            config_version='2.0.0',
            config_source='test',
            config_source_type='repo',
            config_source_url=None,
            command_names=[cmd],
        )

        manifest_path = claude_dir / 'manifest.json'
        data = json.loads(manifest_path.read_text(encoding='utf-8'))
        assert data['version'] == '2.0.0', 'Manifest was not overwritten on reinstall'


class TestGlobalConfigOutput:
    """Test global-config output to ~/.claude.json."""

    def test_global_config_written_to_claude_json(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify global-config values are written to ~/.claude.json."""
        from scripts.setup_environment import write_global_config
        from tests.e2e.validators import validate_global_config_output

        paths = e2e_isolated_home
        home = paths['home']

        global_config = golden_config.get('global-config')
        if not global_config:
            pytest.skip('No global-config in golden_config')

        # Path.home() is already patched by e2e_isolated_home fixture
        write_global_config(global_config)

        errors = validate_global_config_output(home, golden_config)
        assert not errors, 'global-config output validation failed:\n' + '\n'.join(errors)

    def test_global_config_preserves_existing_keys(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify global-config preserves existing keys in ~/.claude.json."""
        from scripts.setup_environment import write_global_config

        paths = e2e_isolated_home
        home = paths['home']

        # Pre-populate with installMethod
        claude_json = home / '.claude.json'
        claude_json.write_text(json.dumps({'installMethod': 'native'}), encoding='utf-8')

        global_config = golden_config.get('global-config', {})
        if not global_config:
            pytest.skip('No global-config in golden_config')

        # Path.home() is already patched by e2e_isolated_home fixture
        write_global_config(global_config)

        data = json.loads(claude_json.read_text(encoding='utf-8'))
        assert data['installMethod'] == 'native', 'installMethod was lost during merge'
        for key, expected in global_config.items():
            assert data.get(key) == expected, f'Key {key!r}: expected {expected!r}, got {data.get(key)!r}'


class TestRulesOutput:
    """Test rules files are processed into ~/.claude/rules/."""

    def test_rules_directory_and_file(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify rules files are processed into ~/.claude/rules/."""
        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']
        rules_dir = claude_dir / 'rules'
        rules_dir.mkdir(parents=True, exist_ok=True)

        rules = golden_config.get('rules', [])
        if not rules:
            pytest.skip('No rules in golden_config')

        mock_repo = Path(__file__).parent / 'fixtures' / 'mock_repo'
        config_source = str(mock_repo / 'config.yaml')

        from scripts.setup_environment import process_resources
        result = process_resources(
            rules, rules_dir, 'rules', config_source, None, None,
        )
        assert result, 'process_resources() failed for rules'

        errors: list[str] = []
        for rule_path in rules:
            filename = Path(rule_path).name
            dest = rules_dir / filename
            if not dest.exists():
                errors.append(f'Rule file not found: {dest}')
            elif dest.stat().st_size == 0:
                errors.append(f'Rule file is empty: {dest}')

        assert not errors, 'Rules E2E validation failed:\n' + '\n'.join(errors)
