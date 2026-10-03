"""E2E tests for the installation manifest lifecycle.

Tests verify:
- The isolated and the base profile manifests carry exactly the expected fields
- The manifest records the configuration version, or None without one
- The manifest records every command name and the configuration source
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.e2e.expected import EXPECTED_JSON_KEYS


class TestManifestFields:
    """Test the field set of a written manifest."""

    @pytest.mark.parametrize(
        ('command_name', 'command_names'),
        [
            pytest.param('fields-cmd', ['fields-cmd', 'fields-alias'], id='isolated'),
            pytest.param(None, [], id='base'),
        ],
    )
    def test_manifest_carries_exactly_the_profile_fields(
        self,
        e2e_isolated_home: dict[str, Path],
        command_name: str | None,
        command_names: list[str],
    ) -> None:
        """Verify a written manifest holds the expected fields and nothing else."""
        from scripts.setup_environment import write_manifest

        claude_dir = e2e_isolated_home['claude_dir']
        profile_dir = claude_dir / command_name if command_name else claude_dir

        assert write_manifest(
            config_base_dir=profile_dir,
            command_name=command_name,
            config_version='1.4.0',
            config_source='fields.yaml',
            config_source_type='repo',
            config_source_url=None,
            command_names=command_names,
            claude_code_version='2.1.85',
        )

        data = json.loads((profile_dir / 'manifest.json').read_text(encoding='utf-8'))
        assert sorted(data) == sorted(EXPECTED_JSON_KEYS['manifest'])
        assert data['version'] == '1.4.0'
        assert data['claude_code_version'] == '2.1.85'


class TestManifestLifecycle:
    """Test manifest file lifecycle scenarios."""

    def test_manifest_without_version_field(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Verify manifest works when config has no version field."""
        from scripts.setup_environment import write_manifest

        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']
        cmd = 'test-cmd'

        write_manifest(
            config_base_dir=claude_dir,
            command_name=cmd,
            config_version=None,
            config_source='test',
            config_source_type='repo',
            config_source_url=None,
            command_names=[cmd],
            claude_code_version=None,
        )

        manifest_path = claude_dir / 'manifest.json'
        data = json.loads(manifest_path.read_text(encoding='utf-8'))
        assert data['version'] is None, 'Version should be None when not specified'

    def test_manifest_preserves_all_command_names(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Verify manifest includes primary and alias command names."""
        from scripts.setup_environment import write_manifest

        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']
        cmd = 'primary-cmd'
        all_names = ['primary-cmd', 'alias-1', 'alias-2']

        write_manifest(
            config_base_dir=claude_dir,
            command_name=cmd,
            config_version='1.0.0',
            config_source='test',
            config_source_type='repo',
            config_source_url=None,
            command_names=all_names,
            claude_code_version=None,
        )

        manifest_path = claude_dir / 'manifest.json'
        data = json.loads(manifest_path.read_text(encoding='utf-8'))
        assert data['command_names'] == all_names, (
            f'Expected {all_names}, got {data["command_names"]}'
        )

    def test_manifest_with_url_source(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Verify manifest records URL source correctly."""
        from scripts.setup_environment import write_manifest

        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']
        cmd = 'url-cmd'
        url = 'https://gitlab.example.com/env.yaml'

        write_manifest(
            config_base_dir=claude_dir,
            command_name=cmd,
            config_version='2.0.0',
            config_source=url,
            config_source_type='url',
            config_source_url=url,
            command_names=[cmd],
            claude_code_version=None,
        )

        manifest_path = claude_dir / 'manifest.json'
        data = json.loads(manifest_path.read_text(encoding='utf-8'))
        assert data['config_source_type'] == 'url'
        assert data['config_source_url'] == url
        assert data['config_source'] == url

    def test_manifest_with_local_source(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Verify manifest records local source correctly."""
        from scripts.setup_environment import write_manifest

        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']
        cmd = 'local-cmd'

        write_manifest(
            config_base_dir=claude_dir,
            command_name=cmd,
            config_version='1.0.0',
            config_source='/home/user/my-config.yaml',
            config_source_type='local',
            config_source_url=None,
            command_names=[cmd],
            claude_code_version=None,
        )

        manifest_path = claude_dir / 'manifest.json'
        data = json.loads(manifest_path.read_text(encoding='utf-8'))
        assert data['config_source_type'] == 'local'
        assert data['config_source_url'] is None
