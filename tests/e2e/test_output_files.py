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
from scripts.setup_environment import create_additional_settings
from scripts.setup_environment import create_mcp_config_file
from scripts.setup_environment import write_user_settings
from tests.e2e.expected.common import EXPECTED_JSON_KEYS
from tests.e2e.validators import validate_additional_settings
from tests.e2e.validators import validate_mcp_json
from tests.e2e.validators import validate_settings_json


class TestOutputFiles:
    """Test output file content and structure."""

    def test_additional_settings_json_structure(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify additional-settings.json has correct structure and content.

        Uses validate_additional_settings from validators.py.
        Checks: model, permissions, env, hooks, alwaysThinkingEnabled,
        companyAnnouncements, attribution, statusLine.
        """
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        # Create additional settings
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

        # File is written to claude_user_dir (= claude_dir)
        settings_path = claude_dir / f'{cmd}-additional-settings.json'

        # Validate using validators.py
        errors = validate_additional_settings(settings_path, golden_config)
        assert not errors, 'additional-settings.json validation failed:\n' + '\n'.join(errors)

    def test_additional_settings_has_expected_keys(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify additional-settings.json contains all expected top-level keys.

        Uses EXPECTED_JSON_KEYS['additional-settings'] for reference.
        """
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        # Create additional settings
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

        # File is written to claude_user_dir (= claude_dir)
        settings_path = claude_dir / f'{cmd}-additional-settings.json'

        # Load and check keys
        data = json.loads(settings_path.read_text())
        expected_keys = EXPECTED_JSON_KEYS['additional-settings']

        missing_keys = [k for k in expected_keys if k not in data]
        assert not missing_keys, f'Missing expected keys in additional-settings.json: {missing_keys}'

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
        """Verify permissions in additional-settings has all required arrays.

        Checks: defaultMode, allow, deny, ask arrays present with expected values.
        """
        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        create_additional_settings(
            hooks={},
            claude_user_dir=claude_dir,
            command_name=cmd,
            model=None,
            permissions=golden_config.get('permissions'),
            env=None,
            include_co_authored_by=None,
            always_thinking_enabled=None,
            company_announcements=None,
            attribution=None,
            status_line=None,
        )

        # File is written to claude_user_dir (= claude_dir)
        settings_path = claude_dir / f'{cmd}-additional-settings.json'

        data = json.loads(settings_path.read_text())

        if 'permissions' in golden_config:
            assert 'permissions' in data, 'Missing permissions block'

            expected_perm_keys = EXPECTED_JSON_KEYS['permissions']
            for key in expected_perm_keys:
                if key in golden_config['permissions']:
                    assert key in data['permissions'], f'Missing permissions.{key}'
