"""Tests for the commands launch.sh hands Claude Code with the caller's arguments alone.

Claude Code dispatches some commands only from the start of its command line,
so every launch.sh runs FIRST_ARGUMENT_COMMANDS_GUARD before the lines that
start claude with the profile's options: when the caller's arguments form one
of those commands, the guard execs claude with nothing but them.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from scripts import setup_environment
from scripts.setup_environment import CLAUDE_FIRST_ARGUMENT_COMMANDS
from scripts.setup_environment import FIRST_ARGUMENT_COMMANDS_GUARD
from scripts.setup_environment import HOME_FOLDER_SETTINGS_GUARD
from scripts.setup_environment import WINDOWS_SLASH_ARGUMENTS_GUARD
from scripts.setup_environment import WINDOWS_WORKING_DIRECTORY_SPELLING_GUARD
from scripts.setup_environment import create_launcher_script
from tests.e2e.shells import find_bash

LAUNCHER_VARIANTS = [
    pytest.param(None, 'replace', id='no-prompt'),
    pytest.param('probe-prompt.md', 'replace', id='prompt-replace'),
    pytest.param('probe-prompt.md', 'append', id='prompt-append'),
]

# What the stub claude prints first, before one argument per line.
PASSTHROUGH_MARK = 'PASSTHROUGH'
# What the test script prints when the guard lets the launch continue.
PROFILE_MARK = 'PROFILE-OPTIONS'

# Argument lists Claude Code dispatches only from the start of its command line.
FIRST_ARGUMENT_FORMS: list[list[str]] = [
    *([name, 'zzz-none'] for name in CLAUDE_FIRST_ARGUMENT_COMMANDS.names),
    ['logs'],
    ['plugin', 'test'],
    ['plugin', 'test', '--file', 'hooks.test.ts', 'plugin-dir'],
    ['daemon'],
    ['daemon', 'status'],
    ['--dangerously-skip-permissions', 'daemon', 'start'],
    ['--allow-dangerously-skip-permissions', '--dangerously-skip-permissions', 'daemon'],
    ['--update'],
    ['--upgrade'],
]

# Argument lists that only resemble those commands: Claude Code reads them
# with its option parser, so they keep the profile's options.
PROFILE_OPTION_FORMS: list[list[str]] = [
    [],
    ['mcp', 'add', '-s', 'user', '-t', 'http', 'probe', 'https://example.invalid/mcp'],
    ['plugin'],
    ['plugin', 'list'],
    ['plugins', 'test'],
    ['update'],
    ['upgrade'],
    ['--update', 'now'],
    ['--upgrade', '--verbose'],
    ['-p', 'logs'],
    ['--model', 'opus', 'logs', 'zzz-none'],
    ['--dangerously-skip-permissions'],
    ['--dangerously-skip-permissions', '-p', 'daemon'],
    ['--bg', 'fix the build'],
    ['agents'],
    ['Logs', 'zzz-none'],
    ['--', 'logs'],
    ['logs-extra'],
]


def _run_guard(bash: str, stub_dir: Path, args: list[str]) -> list[str]:
    """Run the guard under bash with a stub claude and return what the launch did.

    Args:
        bash: The bash that runs launch.sh.
        stub_dir: Directory holding the stub claude; prepended to PATH.
        args: The caller's arguments.

    Returns:
        The stub's output lines (PASSTHROUGH_MARK, then one argument per
        line) when the guard started claude, or [PROFILE_MARK] when it let
        the launch continue.
    """
    env = dict(os.environ)
    env['PATH'] = f'{stub_dir}{os.pathsep}{env.get("PATH", "")}'
    script = 'set -euo pipefail\n' + FIRST_ARGUMENT_COMMANDS_GUARD + f'printf "%s" {PROFILE_MARK}\n'
    completed = subprocess.run(
        [bash, '-c', script, 'launch.sh', *args],
        capture_output=True, text=True, encoding='utf-8', check=False, timeout=60, env=env,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.split('\n')


@pytest.fixture
def stub_dir(tmp_path: Path) -> Path:
    """Provide a directory with a stub claude that prints its arguments, one per line."""
    directory = tmp_path / 'stub-bin'
    directory.mkdir()
    stub = directory / 'claude'
    stub.write_text(
        f'#!/bin/sh\nprintf "%s" {PASSTHROUGH_MARK}\nfor arg in "$@"; do printf "\\n%s" "$arg"; done\n',
        encoding='utf-8',
        newline='\n',
    )
    stub.chmod(0o755)
    return directory


@pytest.fixture
def bash() -> str:
    """Return the bash generated launchers run under, or skip."""
    found = find_bash()
    if found is None:
        pytest.skip('bash unavailable')
    return found


class TestFirstArgumentCommandsGuardUnderBash:
    """The guard hands claude the caller's arguments alone exactly for the first-argument commands."""

    @pytest.mark.parametrize('args', FIRST_ARGUMENT_FORMS, ids=' '.join)
    def test_first_argument_commands_start_with_the_caller_arguments_alone(
        self, bash: str, stub_dir: Path, args: list[str],
    ) -> None:
        assert _run_guard(bash, stub_dir, args) == [PASSTHROUGH_MARK, *args]

    @pytest.mark.parametrize('args', PROFILE_OPTION_FORMS, ids=lambda args: ' '.join(args) or 'no-arguments')
    def test_other_arguments_keep_the_profile_options(self, bash: str, stub_dir: Path, args: list[str]) -> None:
        assert _run_guard(bash, stub_dir, args) == [PROFILE_MARK]


class TestRenderedGuard:
    """The guard is rendered from CLAUDE_FIRST_ARGUMENT_COMMANDS and runs in every launch.sh."""

    def test_guard_names_every_command_of_the_definition(self) -> None:
        definition = CLAUDE_FIRST_ARGUMENT_COMMANDS
        case_branch = f'  {" | ".join(definition.names)})\n'
        assert case_branch in FIRST_ARGUMENT_COMMANDS_GUARD
        for first, second in definition.two_word:
            assert f'  {first})\n    if [ "${{2-}}" = {second} ]; then\n' in FIRST_ARGUMENT_COMMANDS_GUARD
        assert f'    {definition.after_flags})\n' in FIRST_ARGUMENT_COMMANDS_GUARD
        assert f'    {" | ".join(definition.leading_flags)}) ;;\n' in FIRST_ARGUMENT_COMMANDS_GUARD
        assert f'  {" | ".join(definition.sole)})\n    if [ "$#" -eq 1 ]; then\n' in FIRST_ARGUMENT_COMMANDS_GUARD
        assert FIRST_ARGUMENT_COMMANDS_GUARD.count('exec claude') == 1
        assert '  exec claude "$@"\n' in FIRST_ARGUMENT_COMMANDS_GUARD

    def test_two_word_commands_sharing_a_first_word_share_one_branch(self) -> None:
        definition = setup_environment.FirstArgumentCommands(
            names=('logs',),
            two_word=(('plugin', 'test'), ('plugin', 'eval')),
            after_flags='daemon',
            leading_flags=('--dangerously-skip-permissions',),
            sole=('--update',),
        )

        guard = definition.render_guard()

        assert guard.count('  plugin)\n') == 1
        assert '    if [ "${2-}" = test ] || [ "${2-}" = eval ]; then\n' in guard

    @pytest.mark.parametrize('system', ['Windows', 'Linux', 'Darwin'])
    @pytest.mark.parametrize(('prompt', 'mode'), LAUNCHER_VARIANTS)
    def test_guard_runs_once_after_the_home_folder_guard_and_before_every_profile_start(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, system: str, prompt: str | None, mode: str,
    ) -> None:
        monkeypatch.setattr(setup_environment.platform, 'system', lambda: system)
        result = create_launcher_script(tmp_path / 'first-cmd', 'first-cmd', prompt, mode, has_profile_mcp_servers=True)
        assert result is not None
        content = result[1].read_text(encoding='utf-8')

        assert content.count(FIRST_ARGUMENT_COMMANDS_GUARD) == 1
        guard_start = content.index(FIRST_ARGUMENT_COMMANDS_GUARD)
        assert content.index(HOME_FOLDER_SETTINGS_GUARD) < guard_start
        before = content[:guard_start]
        assert 'exec claude' not in before
        assert 'claude "' not in before
        after = content[guard_start + len(FIRST_ARGUMENT_COMMANDS_GUARD):]
        assert 'claude "${MCP_FLAGS[@]}"' in after
        assert 'get_claude_version' not in before
        assert 'System prompt not found' not in before
        assert content.index('export CLAUDE_CONFIG_DIR=') < guard_start
        assert content.index('[ -f "$ENV_FILE" ] && . "$ENV_FILE"') < guard_start
        if system == 'Windows':
            assert content.index(WINDOWS_SLASH_ARGUMENTS_GUARD) < guard_start
            assert content.index(WINDOWS_WORKING_DIRECTORY_SPELLING_GUARD) < guard_start
