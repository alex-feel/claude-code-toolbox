"""E2E tests for OS environment variable handling.

These tests verify that:
1. set_os_env_variable() updates both persistent storage AND os.environ
2. set_all_os_env_variables() processes mixed SET/DELETE operations correctly
3. Deletion of variables properly removes them from os.environ
4. Unix systems get explicit unset instructions for deleted variables
5. Golden config os-env-variables entries (including null deletions) are processed
"""

from __future__ import annotations

import contextlib
import os
import sys
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from scripts import setup_environment


@contextlib.contextmanager
def _mock_platform_func(*, mock_return: bool) -> Iterator[MagicMock]:
    """Mock the current platform's env var function.

    Args:
        mock_return: The return value for the mocked function.

    Yields:
        The MagicMock object for the patched function.
    """
    target = (
        'set_os_env_variable_windows'
        if sys.platform == 'win32'
        else 'set_os_env_variable_unix'
    )
    with patch.object(
        setup_environment,
        target,
        return_value=mock_return,
    ) as mock:
        yield mock


class TestOsEnvVariableProcessSync:
    """Test that os.environ is synchronized after persistent storage operations."""

    def test_set_os_env_variable_syncs_to_process(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify os.environ is updated when setting a variable succeeds.

        Mocks the platform-specific persistent storage function to succeed,
        then verifies that os.environ reflects the new value immediately.
        """
        test_var = 'E2E_TEST_SET_SYNC_PROCESS_12345'

        # Ensure variable does not exist before test
        monkeypatch.delenv(test_var, raising=False)

        with _mock_platform_func(mock_return=True):
            result = setup_environment.set_os_env_variable(test_var, 'sync_value')

        assert result is True
        assert os.environ.get(test_var) == 'sync_value'

        # Clean up
        os.environ.pop(test_var, None)

    def test_delete_os_env_variable_removes_from_process(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify os.environ entry is removed when deleting a variable succeeds.

        Pre-sets a variable in os.environ, then mocks the persistent storage
        function to succeed, and verifies the variable is gone from os.environ.
        """
        test_var = 'E2E_TEST_DELETE_SYNC_PROCESS_12345'

        # Pre-set the variable
        monkeypatch.setenv(test_var, 'old_value')
        assert os.environ.get(test_var) == 'old_value'

        with _mock_platform_func(mock_return=True):
            result = setup_environment.set_os_env_variable(test_var, None)

        assert result is True
        assert test_var not in os.environ

    def test_set_all_os_env_variables_mixed_operations(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify mixed SET and DELETE operations update os.environ correctly.

        Creates a scenario where one variable is set and another is deleted,
        then verifies both operations are reflected in os.environ.
        """
        set_var = 'E2E_TEST_MIXED_SET_12345'
        delete_var = 'E2E_TEST_MIXED_DELETE_12345'

        # Pre-set the variable to be deleted
        monkeypatch.setenv(delete_var, 'should_be_deleted')
        # Ensure the SET variable does not exist
        monkeypatch.delenv(set_var, raising=False)

        env_vars: dict[str, str | None] = {
            set_var: 'new_value',
            delete_var: None,
        }

        with _mock_platform_func(mock_return=True):
            result = setup_environment.set_all_os_env_variables(env_vars)

        assert result is True
        assert os.environ.get(set_var) == 'new_value'
        assert delete_var not in os.environ

        # Clean up
        os.environ.pop(set_var, None)

    def test_delete_nonexistent_var_no_crash(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify deleting a variable not in os.environ does not crash.

        os.environ.pop(name, None) should handle missing keys gracefully.
        """
        test_var = 'E2E_TEST_NONEXISTENT_DELETE_12345'

        # Ensure variable does not exist
        monkeypatch.delenv(test_var, raising=False)
        assert test_var not in os.environ

        with _mock_platform_func(mock_return=True):
            result = setup_environment.set_os_env_variable(test_var, None)

        assert result is True
        assert test_var not in os.environ

    def test_no_process_env_change_on_failure(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify os.environ is NOT modified when persistent storage fails.

        When the platform-specific function returns False, os.environ should
        remain unchanged to maintain consistency with persistent state.
        """
        test_var = 'E2E_TEST_FAIL_NO_CHANGE_12345'

        # Pre-set a value
        monkeypatch.setenv(test_var, 'original_value')

        with _mock_platform_func(mock_return=False):
            result = setup_environment.set_os_env_variable(test_var, None)

        assert result is False
        # os.environ should still have the original value
        assert os.environ.get(test_var) == 'original_value'


class TestOsEnvVariableUnsetGuidance:
    """Test that Unix systems provide explicit unset instructions."""

    @pytest.mark.skipif(sys.platform == 'win32', reason='Unix-only unset guidance')
    def test_delete_guidance_includes_unset_command(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Verify unset instructions are shown for deleted variables on Unix.

        When variables are deleted on Unix, the output should include explicit
        'unset VARNAME' commands so users can remove them from their current shell.
        """
        test_var = 'E2E_TEST_UNSET_GUIDANCE_12345'

        with _mock_platform_func(mock_return=True):
            setup_environment.set_all_os_env_variables({test_var: None})

        captured = capsys.readouterr()
        assert f'unset {test_var}' in captured.out

    @pytest.mark.skipif(sys.platform == 'win32', reason='Unix-only unset guidance')
    def test_no_unset_when_only_setting(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Verify no unset instructions when only setting variables (no deletions).

        The unset guidance should only appear when variables are actually deleted.
        """
        test_var = 'E2E_TEST_NO_UNSET_12345'

        with _mock_platform_func(mock_return=True):
            setup_environment.set_all_os_env_variables({test_var: 'some_value'})

        captured = capsys.readouterr()
        assert 'unset' not in captured.out

        # Clean up
        os.environ.pop(test_var, None)


class TestOsEnvVariableGoldenConfig:
    """Test that golden config os-env-variables are processed correctly."""

    def test_golden_config_has_deletion_entries(
        self,
        golden_config: dict[str, Any],
    ) -> None:
        """Verify the golden config contains null-valued entries for deletion testing.

        The golden config should have both SET and DELETE (null) entries in
        os-env-variables to exercise both code paths.
        """
        os_env = golden_config.get('os-env-variables', {})

        # Must have SET entries
        set_entries = {k: v for k, v in os_env.items() if v is not None}
        assert len(set_entries) > 0, 'Golden config should have SET os-env-variables entries'

        # Must have DELETE (null) entries
        delete_entries = {k: v for k, v in os_env.items() if v is None}
        assert len(delete_entries) > 0, (
            'Golden config should have DELETE (null) os-env-variables entries'
        )

    def test_golden_config_set_operations(
        self,
        golden_config: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify golden config SET entries update os.environ correctly.

        Processes only the SET entries from os-env-variables and verifies
        each value appears in os.environ after the operation.
        """
        os_env = golden_config.get('os-env-variables', {})
        set_entries = {k: v for k, v in os_env.items() if v is not None}

        if not set_entries:
            return

        # Clean up any pre-existing vars
        for name in set_entries:
            monkeypatch.delenv(name, raising=False)

        with _mock_platform_func(mock_return=True):
            setup_environment.set_all_os_env_variables(set_entries)

        errors: list[str] = []
        for name, expected_value in set_entries.items():
            actual = os.environ.get(name)
            if actual != str(expected_value):
                errors.append(
                    f'os.environ[{name!r}]: expected {expected_value!r}, got {actual!r}',
                )

        # Clean up
        for name in set_entries:
            os.environ.pop(name, None)

        assert not errors, 'Golden config SET operations failed:\n' + '\n'.join(errors)

    def test_golden_config_delete_operations(
        self,
        golden_config: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify golden config DELETE (null) entries remove from os.environ.

        Pre-sets the variables in os.environ, processes the DELETE entries,
        and verifies each variable is removed from os.environ.
        """
        os_env = golden_config.get('os-env-variables', {})
        delete_entries: dict[str, str | None] = {
            k: v for k, v in os_env.items() if v is None
        }

        if not delete_entries:
            return

        # Pre-set the variables to be deleted
        for name in delete_entries:
            monkeypatch.setenv(name, 'pre_existing_value')

        with _mock_platform_func(mock_return=True):
            setup_environment.set_all_os_env_variables(delete_entries)

        errors: list[str] = [
            f'os.environ[{name!r}] still present after deletion '
            f'(value: {os.environ[name]!r})'
            for name in delete_entries
            if name in os.environ
        ]

        assert not errors, 'Golden config DELETE operations failed:\n' + '\n'.join(errors)

    def test_golden_config_mixed_operations(
        self,
        golden_config: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify golden config processes mixed SET and DELETE entries together.

        Processes all os-env-variables (both SET and DELETE) in a single call
        and verifies the result matches expectations for each entry.
        """
        os_env = golden_config.get('os-env-variables', {})

        if not os_env:
            return

        # Pre-set variables that will be deleted (so we can verify removal)
        for name, value in os_env.items():
            if value is None:
                monkeypatch.setenv(name, 'should_be_deleted')
            else:
                monkeypatch.delenv(name, raising=False)

        with _mock_platform_func(mock_return=True):
            result = setup_environment.set_all_os_env_variables(os_env)

        assert result is True

        errors: list[str] = []
        for name, expected_value in os_env.items():
            if expected_value is None:
                # Should be removed
                if name in os.environ:
                    errors.append(
                        f'os.environ[{name!r}] still present after deletion',
                    )
            else:
                # Should be set
                actual = os.environ.get(name)
                if actual != str(expected_value):
                    errors.append(
                        f'os.environ[{name!r}]: expected {expected_value!r}, got {actual!r}',
                    )

        # Clean up SET variables
        for name, value in os_env.items():
            if value is not None:
                os.environ.pop(name, None)

        assert not errors, 'Mixed SET/DELETE operations failed:\n' + '\n'.join(errors)
