"""E2E tests for the profile directory every launcher and wrapper names.

Setup writes a profile's launchers into the profile directory and its global
wrappers into ``~/.local/bin``. These tests pin the exact bytes generated for
the default profile directory ``~/.claude/<cmd>``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from scripts import setup_environment
from scripts.setup_environment import create_launcher_script
from scripts.setup_environment import register_global_command
from tests.e2e.expected.launchers import DEFAULT_RENDERINGS
from tests.e2e.expected.launchers import GOLDEN_ALIAS
from tests.e2e.expected.launchers import GOLDEN_COMMAND
from tests.e2e.expected.launchers import GOLDEN_PROMPT
from tests.e2e.expected.launchers import LAUNCHER_PATH_TOKEN

# Launcher variants create_launcher_script() generates: (id, prompt file, mode).
LAUNCHER_VARIANTS = [
    pytest.param('no-prompt', None, 'replace', id='no-prompt'),
    pytest.param('prompt-replace', GOLDEN_PROMPT, 'replace', id='prompt-replace'),
    pytest.param('prompt-append', GOLDEN_PROMPT, 'append', id='prompt-append'),
]


def _expected_bytes(text: str, *, lf_pinned: bool) -> bytes:
    """Encode an expected rendering the way setup writes it on this host.

    Files setup writes with ``newline='\\n'`` keep LF line endings on every
    host; the rest use the host's line separator.

    Args:
        text: Expected file content with LF line endings.
        lf_pinned: Whether setup pins the file to LF line endings.

    Returns:
        The exact bytes the file must contain.
    """
    newline = '\n' if lf_pinned else os.linesep
    return text.replace('\n', newline).encode('utf-8')


def _assert_bytes(path: Path, key: str, *, lf_pinned: bool, launcher_path: Path | None = None) -> None:
    """Assert that a generated file matches its default-layout rendering byte for byte.

    Args:
        path: The generated file.
        key: The DEFAULT_RENDERINGS key of its expected content.
        lf_pinned: Whether setup pins the file to LF line endings.
        launcher_path: The start.ps1 path substituted for LAUNCHER_PATH_TOKEN.
    """
    expected = DEFAULT_RENDERINGS[key]
    if launcher_path is not None:
        expected = expected.replace(LAUNCHER_PATH_TOKEN, str(launcher_path))
    actual = path.read_bytes()
    assert actual == _expected_bytes(expected, lf_pinned=lf_pinned), (
        f'{path.name} differs from the default rendering {key!r}:\n'
        f'--- expected ---\n{expected}\n--- actual ---\n{actual.decode("utf-8", "replace")}'
    )


class TestDefaultLayoutRendering:
    """A profile in ~/.claude/<cmd> gets exactly the established launcher text.

    platform.system() is the only platform detection create_launcher_script()
    and register_global_command() use, so mocking it renders the Windows and
    the Unix file sets on every CI runner.
    """

    @pytest.mark.parametrize(('variant', 'prompt', 'mode'), LAUNCHER_VARIANTS)
    def test_windows_launchers_match_default_rendering(
        self,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        variant: str,
        prompt: str | None,
        mode: str,
    ) -> None:
        """start.ps1, start.cmd and launch.sh match the default rendering byte for byte."""
        profile_dir = e2e_isolated_home['claude_dir'] / GOLDEN_COMMAND
        monkeypatch.setattr(setup_environment.platform, 'system', lambda: 'Windows')

        result = create_launcher_script(profile_dir, GOLDEN_COMMAND, prompt, mode, has_profile_mcp_servers=True)

        assert result == (profile_dir / 'start.ps1', profile_dir / 'launch.sh')
        _assert_bytes(profile_dir / 'start.ps1', 'windows/start.ps1', lf_pinned=False)
        _assert_bytes(profile_dir / 'start.cmd', 'windows/start.cmd', lf_pinned=False)
        _assert_bytes(profile_dir / 'launch.sh', f'windows/launch.sh/{variant}', lf_pinned=True)

    @pytest.mark.parametrize('system', ['Linux', 'Darwin'])
    @pytest.mark.parametrize(('variant', 'prompt', 'mode'), LAUNCHER_VARIANTS)
    def test_unix_launcher_matches_default_rendering(
        self,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        system: str,
        variant: str,
        prompt: str | None,
        mode: str,
    ) -> None:
        """launch.sh matches the default rendering byte for byte on Linux and macOS."""
        profile_dir = e2e_isolated_home['claude_dir'] / GOLDEN_COMMAND
        monkeypatch.setattr(setup_environment.platform, 'system', lambda: system)

        result = create_launcher_script(profile_dir, GOLDEN_COMMAND, prompt, mode, has_profile_mcp_servers=True)

        assert result == (profile_dir / 'launch.sh', profile_dir / 'launch.sh')
        _assert_bytes(profile_dir / 'launch.sh', f'unix/launch.sh/{variant}', lf_pinned=False)

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows wrappers render from Windows path semantics')
    def test_windows_wrappers_match_default_rendering(
        self,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The CMD, PowerShell and Git Bash wrappers of a command and its alias match byte for byte."""
        profile_dir = e2e_isolated_home['claude_dir'] / GOLDEN_COMMAND
        local_bin = e2e_isolated_home['local_bin']
        monkeypatch.setattr(setup_environment.platform, 'system', lambda: 'Windows')
        monkeypatch.setattr(
            setup_environment, 'add_directory_to_windows_path', lambda directory: (True, f'[mock] {directory}'),
        )
        result = create_launcher_script(profile_dir, GOLDEN_COMMAND, None, 'replace', has_profile_mcp_servers=False)
        assert result is not None
        start_ps1, launch_sh = result

        assert register_global_command(start_ps1, GOLDEN_COMMAND, [GOLDEN_ALIAS], launch_script_path=launch_sh)

        for name in (GOLDEN_COMMAND, GOLDEN_ALIAS):
            _assert_bytes(local_bin / f'{name}.cmd', f'windows-wrappers/{name}.cmd', lf_pinned=False)
            _assert_bytes(
                local_bin / f'{name}.ps1', f'windows-wrappers/{name}.ps1', lf_pinned=False, launcher_path=start_ps1,
            )
            _assert_bytes(local_bin / name, f'windows-wrappers/{name}', lf_pinned=True)
