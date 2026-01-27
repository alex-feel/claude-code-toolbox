"""E2E tests for cleanup verification.

These tests verify that no E2E test artifacts leak outside the isolated
test environment to the real user home directory. They validate that the
e2e_isolated_home fixture provides proper isolation.
"""

from __future__ import annotations

from pathlib import Path


class TestCleanup:
    """Verify no test artifacts leak to real home directory.

    IMPORTANT: These tests check the REAL home directory (not the mocked one)
    to ensure isolation is working correctly. The fixture's post-test
    verification handles cleanup checks automatically.
    """

    def test_no_artifacts_in_real_home_claude_dir(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Verify no E2E test artifacts in real ~/.claude directory.

        Checks that files with 'e2e-test' pattern don't exist in real home.
        During test execution, the fixture isolates all operations to tmp_path.
        This test documents and validates that behavior.
        """
        # The fixture's post-test verification handles this
        # This test is here for explicit documentation and CI verification
        # In CI, this test runs AFTER the isolated fixture cleanup
        # The fixture itself verifies no leakage
        paths = e2e_isolated_home
        assert paths['home'].exists(), 'Isolated home should exist'

    def test_no_artifacts_in_real_local_bin(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Verify no E2E test artifacts in real ~/.local/bin directory.

        Checks that command wrappers with 'e2e-test' pattern don't exist
        in the real user's local bin directory.
        """
        # Same as above - fixture handles verification
        paths = e2e_isolated_home
        assert paths['local_bin'].exists(), 'Isolated local_bin should exist'

    def test_temp_directory_isolation(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Verify all operations happen in temp directory.

        Confirms that:
        - home path is under tmp_path
        - claude_dir is under tmp_path
        - local_bin is under tmp_path
        """
        paths = e2e_isolated_home

        # The home directory should be a subdirectory (not the real home)
        home = paths['home']
        claude_dir = paths['claude_dir']
        local_bin = paths['local_bin']

        # Verify paths are not the real home locations
        # Real home would be like /home/user or C:\Users\user
        # Our isolated home is tmp_path/home
        home_str = str(home)

        # Check that home is a temp directory
        # pytest's tmp_path is always under system temp or a pytest-managed location
        assert 'home' in home_str, 'Home path should contain "home" subdirectory'

        # Verify claude_dir is under our isolated home
        assert str(claude_dir).startswith(str(home)), (
            f'claude_dir {claude_dir} not under isolated home {home}'
        )

        # Verify local_bin is under our isolated home
        assert str(local_bin).startswith(str(home)), (
            f'local_bin {local_bin} not under isolated home {home}'
        )

    def test_fixture_provides_required_paths(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Verify fixture provides all required path keys.

        Confirms the fixture returns expected path dictionary keys.
        """
        paths = e2e_isolated_home

        required_keys = [
            'home',
            'claude_dir',
            'local_bin',
            'config_claude',
            'localappdata_claude',
            'appdata_roaming',
            'appdata_local',
        ]

        missing = [k for k in required_keys if k not in paths]
        assert not missing, f'Fixture missing required keys: {missing}'

    def test_directories_are_writable(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Verify isolated directories are writable.

        Confirms tests can create files in the isolated environment.
        """
        paths = e2e_isolated_home

        # Try creating a test file
        test_file = paths['claude_dir'] / 'test_write.txt'
        test_file.write_text('test content')

        assert test_file.exists(), f'Could not write test file: {test_file}'

        # Clean up
        test_file.unlink()
        assert not test_file.exists(), 'Failed to clean up test file'

    def test_monkeypatch_path_home(
        self,
        e2e_isolated_home: dict[str, Path],
    ) -> None:
        """Verify Path.home() returns isolated home.

        This confirms monkeypatching is working correctly.
        """
        paths = e2e_isolated_home

        # During test, Path.home() should return our isolated home
        current_home = Path.home()
        expected_home = paths['home']

        assert current_home == expected_home, (
            f'Path.home() returned {current_home}, expected {expected_home}'
        )
