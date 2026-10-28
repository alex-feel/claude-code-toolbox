"""E2E tests for the order of a run's output when its stdout and stderr go to one file.

A run redirected to a file or a pipe (``> setup.log 2>&1``, a CI log, an
agent's shell) shares that descriptor with every child process it starts:
the dependent runs of Step 24, the installer of Step 1, dependency commands
and uv. Each test starts the entry point as its own process with stdout and
stderr in one file and reads the file back, so the order on disk is the
order a reader of the log sees: every line follows the lines printed before
it, a failing dependent's errors sit under its own header, and an error line
follows the lines printed before it.
"""

from __future__ import annotations

import re
import subprocess
import sys
from operator import itemgetter
from pathlib import Path
from typing import Any

import pytest

from scripts import setup_environment
from tests.e2e.profile_support import REPO_ROOT
from tests.e2e.profile_support import run_main
from tests.e2e.profile_support import write_child_runner
from tests.e2e.profile_support import write_config

SKIP = ['--skip-install', '--no-admin']
DEPENDENCY_OUTPUT = 'cct-dependency-output'
ANSI_SEQUENCE = re.compile(r'\x1b\[[0-9;]*m')

# The parent run executes the child runner itself, with every child run it
# starts going through the child runner too, so the parent and its children
# all run setup_environment.main() with the machine-wide writers replaced
PARENT_RUNNER = '''\
import runpy
import sys
from unittest.mock import patch

from scripts import setup_environment

child_runner = sys.argv.pop(1)
with patch.object(setup_environment, '_elevation_launch_args', lambda _module, _argv0: [child_runner]):
    runpy.run_path(child_runner, run_name='__main__')
'''

# install_claude.main() with an installation that fails: the steps print to
# stdout, the failure to stderr; nothing on the machine is changed
INSTALLER_RUNNER = '''\
from unittest.mock import patch

from scripts import install_claude

with (
    patch.object(install_claude, 'ensure_git_bash_windows', lambda: 'C:/Program Files/Git/bin/bash.exe'),
    patch.object(install_claude, 'configure_powershell_policy', lambda: None),
    patch.object(install_claude, 'set_windows_env_var', lambda *_args, **_kwargs: None),
    patch.object(install_claude, 'ensure_claude', lambda: False),
):
    install_claude.main()
'''


def _run_redirected(argv: list[str], output: Path) -> tuple[int, list[str]]:
    """Run a process with stdout and stderr in one file and return its exit code and the file's lines."""
    with output.open('wb') as stream:
        code = subprocess.run(
            argv, stdout=stream, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, check=False, timeout=600,
        ).returncode
    text = ANSI_SEQUENCE.sub('', output.read_text(encoding='utf-8', errors='replace'))
    return code, text.replace('\r\n', '\n').splitlines()


def _index(lines: list[str], *parts: str) -> int:
    """The index of the first line that contains every part, -1 when none does."""
    return next((i for i, line in enumerate(lines) if all(part in line for part in parts)), -1)


def _enclosing_lines(lines: list[str], index: int) -> tuple[str, str]:
    """The nearest step or command line before a line, and the nearest step line after it."""
    before = next(
        (lines[i].strip() for i in range(index - 1, -1, -1) if lines[i].startswith('Step ') or 'Running:' in lines[i]),
        '',
    )
    after = next((lines[i] for i in range(index + 1, len(lines)) if lines[i].startswith('Step ')), '')
    return before, after


def _assert_in_order(lines: list[str], expected: list[tuple[str, int]]) -> None:
    """Assert that every labeled line was found and that the lines appear in the listed order."""
    missing = [label for label, index in expected if index < 0]
    assert not missing, f'lines not found: {missing}\n' + '\n'.join(lines)
    actual = [label for label, _ in sorted(expected, key=itemgetter(1))]
    assert actual == [label for label, _ in expected], (
        f'order in the file: {actual}\n' + '\n'.join(lines)
    )


def _team() -> dict[str, Any]:
    """A configuration with content entries and a dependency command that writes to the shared output.

    The command prints the profile directory the run exports for its child
    processes, so each run's output line names the profile that ran it.

    Returns:
        The configuration.
    """
    return {
        'name': 'Team Like',
        'agents': ['agents/core.md'],
        'rules': ['rules/rule.md'],
        'dependencies': {
            'windows': [f'echo "{DEPENDENCY_OUTPUT} $env:CLAUDE_CONFIG_DIR"'],
            'linux': [f'echo "{DEPENDENCY_OUTPUT} $CLAUDE_CONFIG_DIR"'],
            'macos': [f'echo "{DEPENDENCY_OUTPUT} $CLAUDE_CONFIG_DIR"'],
        },
        'user-settings': {'theme': 'dark'},
    }


@pytest.fixture
def configs(tmp_path: Path) -> Path:
    """A directory holding the configuration's resources."""
    directory = tmp_path / 'configs'
    for relative, content in (('agents/core.md', '# core agent\n'), ('rules/rule.md', '# rule\n')):
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    return directory


class TestDependentRefreshOutputOrder:
    """Step 24 of a source run whose output goes to a file."""

    def test_failing_dependent_output_stays_under_its_own_header(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Each dependent's lines, its errors included, sit under its header, and the parent's lines keep their place.

        team-2 fails: a real agents directory with content makes its
        remembered link refuse. team-3 succeeds and runs the dependency
        command. The file must read top to bottom in the order the lines
        were printed: the source's own steps and its dependency output, the
        Step 24 line, team-2's header and refusal, team-3's header and run,
        then the source's completion banner and the failure it names.
        """
        cfg = write_config(configs, 'team.yaml', _team())
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0
        for name in ('team-2', 'team-3'):
            assert run_main([
                str(cfg), *SKIP, '--yes', '--command-names', name, '--link-dirs', 'all', '--link-from', 'team-1',
            ]) == 0
        agents = e2e_isolated_home['claude_dir'] / 'team-2' / 'agents'
        setup_environment._remove_directory_link(agents)
        agents.mkdir()
        (agents / 'local.md').write_text('local', encoding='utf-8')
        child_runner = write_child_runner(tmp_path, monkeypatch)
        parent_runner = tmp_path / 'parent_runner.py'
        parent_runner.write_text(PARENT_RUNNER, encoding='utf-8')

        argv = [str(parent_runner), str(child_runner), '--profile', 'team-1', *SKIP, '--yes', '--run-all-commands']
        code, lines = _run_redirected([sys.executable, *argv], tmp_path / 'setup.log')

        assert code == 1, '\n'.join(lines)
        source_output = _index(lines, f'{DEPENDENCY_OUTPUT} ', 'team-1')
        team_3_output = _index(lines, f'{DEPENDENCY_OUTPUT} ', 'team-3')
        _assert_in_order(lines, [
            ('source dependency output', source_output),
            ('source registers its command', _index(lines, 'Step 22: Registering global team-1 command')),
            ('source Step 24', _index(lines, 'Step 24: Refreshing 2 dependent profile(s): team-2, team-3')),
            ('team-2 header', _index(lines, '=== Dependent profile team-2 ===')),
            ('team-2 refusal', _index(lines, 'ERROR:', 'team-2', 'is a real directory with 1 item(s)')),
            ('team-3 header', _index(lines, '=== Dependent profile team-3 ===')),
            ('team-3 dependency output', team_3_output),
            ('team-3 registers its command', _index(lines, 'Step 22: Registering global team-3 command')),
            ('team-3 completes', _index(lines, 'Setup Complete!')),
            ('source completes with errors', _index(lines, 'Setup Completed with Errors')),
            ('source names the failed dependent', _index(lines, 'The following dependent profiles failed to refresh:')),
        ])
        # The output of a command a run starts lies inside that run's Step 6,
        # right after the line that names the command
        for output in (source_output, team_3_output):
            before, after = _enclosing_lines(lines, output)
            assert before.startswith('INFO: Running: echo'), (before, '\n'.join(lines))
            assert after.startswith('Step 7:'), (after, '\n'.join(lines))


class TestInstallerOutputOrder:
    """install_claude.py run with its output in a file."""

    def test_failure_line_follows_the_steps_printed_before_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The [FAIL] line of a failed installation comes after the banner and the steps, not before them."""
        runner = tmp_path / 'installer_runner.py'
        runner.write_text(INSTALLER_RUNNER, encoding='utf-8')
        monkeypatch.setenv('PYTHONPATH', str(REPO_ROOT))

        code, lines = _run_redirected([sys.executable, str(runner)], tmp_path / 'installer.log')

        assert code == 1, '\n'.join(lines)
        _assert_in_order(lines, [
            ('banner', _index(lines, 'Installer')),
            ('installation step', _index(lines, 'Installing Claude Code CLI...')),
            ('failure', _index(lines, '[FAIL] Claude Code installation failed with all methods')),
            ('closing advice', _index(lines, 'Installation failed. Please check the error above.')),
        ])
