"""Unit tests for how the Windows launch.sh keeps arguments that start with a slash."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from scripts import setup_environment
from scripts.setup_environment import WINDOWS_SLASH_ARGUMENTS_GUARD
from scripts.setup_environment import create_launcher_script
from tests.e2e.shells import find_bash

LAUNCHER_VARIANTS = [
    pytest.param(None, 'replace', id='no-prompt'),
    pytest.param('probe-prompt.md', 'replace', id='prompt-replace'),
    pytest.param('probe-prompt.md', 'append', id='prompt-append'),
]


def _launch_sh(profile_dir: Path, system: str, prompt: str | None, mode: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """Render launch.sh for a platform and return its text.

    Args:
        profile_dir: The profile directory.
        system: The platform.system() value to render for.
        prompt: The system prompt file name, or None.
        mode: The system prompt mode.
        monkeypatch: Fixture that fakes the platform.

    Returns:
        The generated launch.sh.
    """
    monkeypatch.setattr(setup_environment.platform, 'system', lambda: system)
    result = create_launcher_script(profile_dir, 'slash-cmd', prompt, mode, has_profile_mcp_servers=True)
    assert result is not None
    return result[1].read_text(encoding='utf-8')


class TestLaunchShTemplate:
    """The Windows launch.sh lists slash arguments before it starts claude; Unix launchers do not."""

    @pytest.mark.parametrize(('prompt', 'mode'), LAUNCHER_VARIANTS)
    def test_windows_guard_precedes_every_claude_start(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prompt: str | None, mode: str,
    ) -> None:
        """The guard appears once, and every exec claude line comes after it."""
        content = _launch_sh(tmp_path / 'slash-cmd', 'Windows', prompt, mode, monkeypatch)

        assert content.count(WINDOWS_SLASH_ARGUMENTS_GUARD) == 1
        guard_end = content.index(WINDOWS_SLASH_ARGUMENTS_GUARD) + len(WINDOWS_SLASH_ARGUMENTS_GUARD)
        starts = [line for line in content[:guard_end].splitlines() if line.strip().startswith('exec claude')]
        assert starts == []
        assert 'exec claude' in content[guard_end:]

    @pytest.mark.parametrize('system', ['Linux', 'Darwin'])
    @pytest.mark.parametrize(('prompt', 'mode'), LAUNCHER_VARIANTS)
    def test_unix_launch_sh_carries_no_guard(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, system: str, prompt: str | None, mode: str,
    ) -> None:
        """Linux and macOS convert no arguments, so their launch.sh sets no exclusion list."""
        content = _launch_sh(tmp_path / 'slash-cmd', system, prompt, mode, monkeypatch)

        assert 'MSYS2_ARG_CONV_EXCL' not in content


class TestGuardExclusionList:
    """The guard builds MSYS2_ARG_CONV_EXCL from the slash arguments that name no existing path."""

    @staticmethod
    def _exclusions(args: list[str], inherited: str | None = None) -> str | None:
        """Run the guard under bash with args and return the exclusion list it leaves.

        Args:
            args: The launcher's arguments.
            inherited: The MSYS2_ARG_CONV_EXCL value the launcher inherits, or None.

        Returns:
            The MSYS2_ARG_CONV_EXCL value after the guard, or None when unset.
        """
        bash = find_bash()
        if bash is None:
            pytest.skip('bash unavailable')
        env = {key: value for key, value in os.environ.items() if key not in {'MSYS2_ARG_CONV_EXCL', 'MSYS_NO_PATHCONV'}}
        if inherited is not None:
            env['MSYS2_ARG_CONV_EXCL'] = inherited
        script = (
            'set -euo pipefail\n'
            + WINDOWS_SLASH_ARGUMENTS_GUARD
            + 'printf "%s" "${MSYS2_ARG_CONV_EXCL-<unset>}"\n'
        )
        completed = subprocess.run(
            [bash, '-c', script, 'launch.sh', *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
            env=env,
        )
        assert completed.returncode == 0, completed.stderr
        return None if completed.stdout == '<unset>' else completed.stdout

    def test_lists_slash_arguments_that_name_no_path(self) -> None:
        """Slash commands are listed in order; existing paths and other arguments are not."""
        exclusions = self._exclusions(['-p', '/help me', '/review src\\a.py', '/', '/tmp', 'plain', '--flag'])

        assert exclusions == '/help me;/review src\\a.py'

    def test_skips_double_slash_and_semicolon_arguments(self) -> None:
        """An argument with a leading double slash or holding ';' is never listed."""
        assert self._exclusions(['//literal', '/run a;b', '--value=/help']) is None

    def test_extends_an_inherited_list(self) -> None:
        """Entries the caller set stay first and the slash arguments follow them."""
        assert self._exclusions(['/help'], inherited='/keep-me') == '/keep-me;/help'

    def test_leaves_an_inherited_list_alone_without_slash_arguments(self) -> None:
        """A launch with no slash argument keeps the inherited value as it was."""
        assert self._exclusions(['plain', '/'], inherited='/keep-me') == '/keep-me'

    def test_leaves_the_list_unset_without_slash_arguments(self) -> None:
        """A launch with no slash argument adds no variable to the session's environment."""
        assert self._exclusions([]) is None
