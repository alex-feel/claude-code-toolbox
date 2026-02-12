"""E2E tests for source-aware upgrade logic in ensure_claude().

These tests verify that:
1. Native-source installations use native installer for upgrades (auto mode)
2. NPM-source installations use npm for upgrades (auto mode)
3. Native upgrade failure triggers npm fallback in auto mode
4. Native mode prevents npm fallback on upgrade failure
5. NPM mode bypasses source detection and always uses npm
6. Up-to-date versions skip upgrade entirely
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from scripts import install_claude


class TestSourceAwareUpgrade:
    """E2E tests for the source-aware upgrade path in ensure_claude().

    When Claude is already installed but outdated, the upgrade method should
    match the installation source rather than unconditionally using npm.
    """

    def test_native_source_triggers_native_upgrade(self) -> None:
        """When source is native in auto mode, native installer is used for upgrade."""
        with (
            patch('platform.system', return_value='Linux'),
            patch.object(
                install_claude, 'get_claude_version',
                side_effect=['2.0.76', '2.1.39'],
            ),
            patch.object(
                install_claude, 'get_latest_claude_version', return_value='2.1.39',
            ),
            patch.object(install_claude, 'compare_versions', return_value=False),
            patch.object(
                install_claude, 'verify_claude_installation',
                return_value=(True, '/home/user/.local/bin/claude', 'native'),
            ),
            patch.object(
                install_claude, 'install_claude_native_cross_platform', return_value=True,
            ) as mock_native,
            patch.object(install_claude, 'install_claude_npm') as mock_npm,
            patch.dict('os.environ', {'CLAUDE_INSTALL_METHOD': 'auto'}, clear=False),
        ):
            result = install_claude.ensure_claude()

        assert result is True
        mock_native.assert_called()
        mock_npm.assert_not_called()

    def test_npm_mode_triggers_npm_upgrade(self) -> None:
        """When CLAUDE_INSTALL_METHOD=npm, npm is used directly for upgrade.

        Note: In auto mode with npm source, the migration block fires first
        and returns before reaching the upgrade path. This test uses explicit
        npm mode to verify the upgrade path uses npm correctly.
        """
        with (
            patch('platform.system', return_value='Linux'),
            patch.object(
                install_claude, 'get_claude_version',
                side_effect=['2.0.76', '2.1.39'],
            ),
            patch.object(
                install_claude, 'get_latest_claude_version', return_value='2.1.39',
            ),
            patch.object(install_claude, 'compare_versions', return_value=False),
            patch.object(
                install_claude, 'verify_claude_installation',
                return_value=(True, '/usr/lib/node_modules/.bin/claude', 'npm'),
            ),
            patch.object(
                install_claude, 'install_claude_native_cross_platform',
            ) as mock_native,
            patch.object(
                install_claude, 'install_claude_npm', return_value=True,
            ) as mock_npm,
            patch.dict('os.environ', {'CLAUDE_INSTALL_METHOD': 'npm'}, clear=False),
        ):
            result = install_claude.ensure_claude()

        assert result is True
        mock_npm.assert_called()
        mock_native.assert_not_called()

    def test_auto_mode_native_fallback_to_npm(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When native upgrade fails in auto mode, npm fallback is attempted."""
        with (
            patch('platform.system', return_value='Linux'),
            patch.object(
                install_claude, 'get_claude_version',
                side_effect=['2.0.76', '2.1.39'],
            ),
            patch.object(
                install_claude, 'get_latest_claude_version', return_value='2.1.39',
            ),
            patch.object(install_claude, 'compare_versions', return_value=False),
            patch.object(
                install_claude, 'verify_claude_installation',
                return_value=(True, '/home/user/.local/bin/claude', 'native'),
            ),
            patch.object(
                install_claude, 'install_claude_native_cross_platform', return_value=False,
            ) as mock_native,
            patch.object(
                install_claude, 'install_claude_npm', return_value=True,
            ) as mock_npm,
            patch.dict('os.environ', {'CLAUDE_INSTALL_METHOD': 'auto'}, clear=False),
        ):
            result = install_claude.ensure_claude()

        assert result is True
        # Both should be called: native first (fails), then npm fallback
        mock_native.assert_called()
        mock_npm.assert_called()
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert 'falling back to npm' in combined.lower(), (
            'Should show npm fallback message when native upgrade fails'
        )

    def test_native_mode_no_npm_on_upgrade_failure(self) -> None:
        """When CLAUDE_INSTALL_METHOD=native, npm is not used even if native upgrade fails."""
        with (
            patch('platform.system', return_value='Linux'),
            patch.object(
                install_claude, 'get_claude_version', return_value='2.0.76',
            ),
            patch.object(
                install_claude, 'get_latest_claude_version', return_value='2.1.39',
            ),
            patch.object(install_claude, 'compare_versions', return_value=False),
            patch.object(
                install_claude, 'verify_claude_installation',
                return_value=(True, '/home/user/.local/bin/claude', 'native'),
            ),
            patch.object(
                install_claude, 'install_claude_native_cross_platform', return_value=False,
            ) as mock_native,
            patch.object(install_claude, 'install_claude_npm') as mock_npm,
            patch.dict('os.environ', {'CLAUDE_INSTALL_METHOD': 'native'}, clear=False),
        ):
            result = install_claude.ensure_claude()

        assert result is True
        mock_native.assert_called()
        mock_npm.assert_not_called()

    def test_npm_mode_ignores_source(self) -> None:
        """When CLAUDE_INSTALL_METHOD=npm, npm is used regardless of installation source."""
        with (
            patch('platform.system', return_value='Linux'),
            patch.object(
                install_claude, 'get_claude_version',
                side_effect=['2.0.76', '2.1.39'],
            ),
            patch.object(
                install_claude, 'get_latest_claude_version', return_value='2.1.39',
            ),
            patch.object(install_claude, 'compare_versions', return_value=False),
            patch.object(
                install_claude, 'verify_claude_installation',
                return_value=(True, '/home/user/.local/bin/claude', 'native'),
            ),
            patch.object(
                install_claude, 'install_claude_native_cross_platform',
            ) as mock_native,
            patch.object(
                install_claude, 'install_claude_npm', return_value=True,
            ) as mock_npm,
            patch.dict('os.environ', {'CLAUDE_INSTALL_METHOD': 'npm'}, clear=False),
        ):
            result = install_claude.ensure_claude()

        assert result is True
        mock_npm.assert_called()
        mock_native.assert_not_called()

    def test_up_to_date_version_no_upgrade(self) -> None:
        """When current version matches latest, no upgrade function is called."""
        with (
            patch('platform.system', return_value='Linux'),
            patch.object(
                install_claude, 'get_claude_version', return_value='2.1.39',
            ),
            patch.object(
                install_claude, 'get_latest_claude_version', return_value='2.1.39',
            ),
            patch.object(install_claude, 'compare_versions', return_value=True),
            patch.object(
                install_claude, 'verify_claude_installation',
                return_value=(True, '/home/user/.local/bin/claude', 'native'),
            ),
            patch.object(
                install_claude, 'install_claude_native_cross_platform',
            ) as mock_native,
            patch.object(install_claude, 'install_claude_npm') as mock_npm,
            patch.dict('os.environ', {'CLAUDE_INSTALL_METHOD': 'auto'}, clear=False),
        ):
            result = install_claude.ensure_claude()

        assert result is True
        mock_native.assert_not_called()
        mock_npm.assert_not_called()


class TestPathClassification:
    """E2E tests for verify_claude_installation() path classification.

    These tests verify that different installation paths are correctly
    classified as 'native', 'npm', or 'unknown' source types.
    """

    def test_usr_local_bin_classified_as_native(self) -> None:
        """Verify /usr/local/bin/claude is classified as native."""
        with (
            patch('sys.platform', 'linux'),
            patch.object(
                install_claude, 'find_command_robust',
                return_value='/usr/local/bin/claude',
            ),
        ):
            installed, path, source = install_claude.verify_claude_installation()

        assert installed is True
        assert path == '/usr/local/bin/claude'
        assert source == 'native', (
            f'/usr/local/bin/claude should be classified as native, got {source!r}'
        )

    def test_claude_bin_classified_as_native(self) -> None:
        """Verify ~/.claude/bin/claude is classified as native."""
        with (
            patch('sys.platform', 'linux'),
            patch.object(
                install_claude, 'find_command_robust',
                return_value='/home/user/.claude/bin/claude',
            ),
        ):
            installed, path, source = install_claude.verify_claude_installation()

        assert installed is True
        assert path == '/home/user/.claude/bin/claude'
        assert source == 'native', (
            f'.claude/bin path should be classified as native, got {source!r}'
        )

    def test_npm_global_path_classified_as_npm(self) -> None:
        """Verify .npm-global path is classified as npm."""
        with (
            patch('sys.platform', 'linux'),
            patch.object(
                install_claude, 'find_command_robust',
                return_value='/home/user/.npm-global/bin/claude',
            ),
        ):
            installed, path, source = install_claude.verify_claude_installation()

        assert installed is True
        assert path == '/home/user/.npm-global/bin/claude'
        assert source == 'npm', (
            f'.npm-global path should be classified as npm, got {source!r}'
        )

    def test_unknown_source_tries_native_first(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When source is unknown in auto mode, native is tried first, then npm fallback."""
        with (
            patch('platform.system', return_value='Linux'),
            patch.object(
                install_claude, 'get_claude_version',
                side_effect=['2.0.76', '2.1.39'],
            ),
            patch.object(
                install_claude, 'get_latest_claude_version', return_value='2.1.39',
            ),
            patch.object(install_claude, 'compare_versions', return_value=False),
            patch.object(
                install_claude, 'verify_claude_installation',
                return_value=(True, '/opt/custom/bin/claude', 'unknown'),
            ),
            patch.object(
                install_claude, 'install_claude_native_cross_platform', return_value=True,
            ) as mock_native,
            patch.object(install_claude, 'install_claude_npm') as mock_npm,
            patch.dict('os.environ', {'CLAUDE_INSTALL_METHOD': 'auto'}, clear=False),
        ):
            result = install_claude.ensure_claude()

        assert result is True
        mock_native.assert_called()
        mock_npm.assert_not_called()
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert 'unknown installation' in combined.lower(), (
            'Should log detection of unknown source'
        )
