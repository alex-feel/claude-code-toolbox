"""E2E tests for manifest creation and update marker lifecycle.

Tests verify:
- Manifest is created during setup
- Stale update marker is cleaned during re-installation
- Marker file absence does not cause issues
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class TestMarkerLifecycle:
    """Test update marker file lifecycle."""

    def test_stale_marker_cleaned_on_reinstall(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Verify stale update-available marker is removed during setup."""
        from scripts.setup_environment import cleanup_stale_marker

        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']

        # Create a stale marker (simulating a previous version check)
        marker_path = claude_dir / 'update-available.json'
        marker_data = {
            'installed_version': '1.0.0',
            'available_version': '1.1.0',
            'checked_at': '2026-01-01T00:00:00+00:00',
            'config_source_url': 'https://example.com/config.yaml',
        }
        marker_path.write_text(json.dumps(marker_data), encoding='utf-8')
        assert marker_path.exists(), 'Marker should exist before cleanup'

        # Run cleanup (simulating what setup_environment.py does)
        cleanup_stale_marker(claude_dir)

        assert not marker_path.exists(), 'Stale marker should be removed after cleanup'

    def test_cleanup_no_marker_no_error(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Verify cleanup does not fail when no marker exists."""
        from scripts.setup_environment import cleanup_stale_marker

        paths = e2e_isolated_home
        claude_dir = paths['claude_dir']

        marker_path = claude_dir / 'update-available.json'
        assert not marker_path.exists()

        # Should not raise
        cleanup_stale_marker(claude_dir)

    def test_marker_not_recreated_by_manifest_write(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
    ) -> None:
        """Verify write_manifest does not create the marker file."""
        from scripts.setup_environment import write_manifest

        paths = e2e_isolated_home
        cmd = golden_config['command-names'][0]
        claude_dir = paths['claude_dir']

        write_manifest(
            config_base_dir=claude_dir,
            command_name=cmd,
            config_version='1.0.0',
            config_source='test',
            config_source_type='repo',
            config_source_url=None,
            command_names=[cmd],
        )

        marker_path = claude_dir / 'update-available.json'
        assert not marker_path.exists(), 'write_manifest should not create marker file'


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
        )

        manifest_path = claude_dir / 'manifest.json'
        data = json.loads(manifest_path.read_text(encoding='utf-8'))
        assert data['config_source_type'] == 'local'
        assert data['config_source_url'] is None
