"""E2E tests for the work a profile that links content leaves to its source's run.

A profile that links content from a source (``--link-dirs all`` or any
content entry, with ``--link-from``) shares the one machine with it: the
Claude Code binary, the IDE extension, Node.js and the tools the dependency
commands install exist once, and the source's run installs them. Every run of
such a dependent -- a standalone install, ``--profile NAME``, a ``--profile
all`` child and a source's Step 23 refresh -- therefore skips the install and
upgrade of Step 1 (the presence check stays), the IDE extension of Step 2,
the Node.js installation of Step 5 and every dependency command whose text,
after the run's re-rooting, equals a command the source's run executes; a
command rewritten into the profile still runs. A full copy, a profile that
links only ``projects``, the base profile and a source run everything, and
``--run-all-commands`` (or ``CLAUDE_CODE_TOOLBOX_RUN_ALL_COMMANDS=1``) makes
a dependent run everything too, also in the children ``--profile all`` and
Step 23 start. The installation summary and ``--dry-run`` name each skipped
item with its source, and the completion summary repeats them with the flag
that forces the full run.

Every test runs main() against YAML files on disk; the dependency commands
run for real in bash (Linux, macOS) or PowerShell (Windows), in that
platform's spelling, against the isolated home: a command that appends to a
log outside the config home has the same text in every profile's run and is
skipped, while the one naming the config home is re-rooted into each
profile and runs there. The installers of Steps 1, 2 and 5 are replaced by
recorders, because no test installs a real binary.
"""

from __future__ import annotations

import contextlib
import re
import subprocess
import sys
from collections.abc import Callable
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts import setup_environment
from tests.e2e.profile_support import REPO_ROOT
from tests.e2e.profile_support import run_main
from tests.e2e.profile_support import write_config

IS_WINDOWS = sys.platform == 'win32'
NO_ADMIN = ['--no-admin']
SOURCE = 'team-1'
DEPENDENT = 'team-2'
RUNS_LOG = '.tool-runs.log'
INSTALL_LOG_VARIABLE = 'E2E_INSTALL_LOG'
_ANSI_SEQUENCE = re.compile(r'\x1b\[[0-9;]*m')

# The dependency commands, one spelling per shell. The log lines land outside
# the config home, so their text is the same in every profile's run; the
# marker directory lies inside it, so each isolated run re-roots that command
# into its own profile
POSIX_SHARED = f'echo shared >> "$HOME/{RUNS_LOG}"'
POSIX_PLATFORM = f'echo platform >> "$HOME/{RUNS_LOG}"'
POSIX_MARKER = 'mkdir -p ~/.claude/dep-marker'
WINDOWS_SHARED = f'Add-Content -Path "$env:USERPROFILE\\{RUNS_LOG}" -Value shared -Encoding ascii'
WINDOWS_PLATFORM = f'Add-Content -Path "$env:USERPROFILE\\{RUNS_LOG}" -Value platform -Encoding ascii'
WINDOWS_MARKER = 'New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\\.claude\\dep-marker" | Out-Null'
SHARED = WINDOWS_SHARED if IS_WINDOWS else POSIX_SHARED
PLATFORM_COMMAND = WINDOWS_PLATFORM if IS_WINDOWS else POSIX_PLATFORM
MARKER_COMMAND = WINDOWS_MARKER if IS_WINDOWS else POSIX_MARKER
# One full run appends the platform list first, then the common list
ONE_RUN = ['platform', 'shared']

RECORDING_RUNNER = '''\
"""Child runner: setup_environment.main() with the machine-wide installers recorded instead of run."""
import os
from pathlib import Path
from unittest.mock import patch

from scripts import setup_environment
from tests.e2e.fixtures import setup_child

_real_find = setup_environment.find_command
_log = Path(os.environ['E2E_INSTALL_LOG'])


def _find(name):
    return '/usr/bin/claude' if name == 'claude' else _real_find(name)


def _record(label):
    def _recorder(*_args, **_kwargs):
        with _log.open('a', encoding='utf-8') as handle:
            handle.write(label + '\\n')
        return True
    return _recorder


with (
    patch.object(setup_environment, 'find_command', _find),
    patch.object(setup_environment, 'ensure_local_bin_in_path', lambda: None),
    patch.object(setup_environment, 'refresh_path_from_registry', lambda: None),
    patch.object(setup_environment, 'install_claude', _record('install_claude')),
    patch.object(setup_environment, 'install_ide_extensions', _record('install_ide_extensions')),
    patch.object(setup_environment, '_ensure_nodejs', _record('ensure_nodejs')),
    patch.object(setup_environment, '_installed_claude_version', lambda: None),
):
    setup_child.main()
'''


@pytest.fixture
def configs(tmp_path: Path) -> Path:
    """A directory of configurations with the agent they install beside them."""
    directory = tmp_path / 'configs'
    (directory / 'agents').mkdir(parents=True)
    (directory / 'agents' / 'core.md').write_text('# core agent\n', encoding='utf-8')
    return directory


@pytest.fixture
def install_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The file the installer recorders append to, in this process and in child runs."""
    log = tmp_path / 'installs.log'
    monkeypatch.setenv(INSTALL_LOG_VARIABLE, str(log))
    return log


def _config(**extra: Any) -> dict[str, Any]:
    """A configuration whose dependency commands prove where and how often they ran."""
    return {
        'name': 'Linked Work Env',
        'agents': ['agents/core.md'],
        'dependencies': {
            'common': [SHARED],
            'linux': [POSIX_PLATFORM, POSIX_MARKER],
            'macos': [POSIX_PLATFORM, POSIX_MARKER],
            'windows': [WINDOWS_PLATFORM, WINDOWS_MARKER],
        },
        'user-settings': {'theme': 'dark'},
        **extra,
    }


def _rerooted_marker(profile: str) -> str:
    """Spell the marker command the way an isolated run of the given profile rewrites it."""
    return MARKER_COMMAND.replace('\\.claude\\dep-marker', f'\\.claude\\{profile}\\dep-marker').replace(
        '/.claude/dep-marker', f'/.claude/{profile}/dep-marker',
    )


def _record_label(log: Path, label: str) -> Callable[..., bool]:
    def _recorder(*_args: Any, **_kwargs: Any) -> bool:
        with log.open('a', encoding='utf-8') as handle:
            handle.write(f'{label}\n')
        return True
    return _recorder


@contextlib.contextmanager
def _recorded_installers(log: Path) -> Generator[None]:
    """Replace the installers of Steps 1, 2 and 5 with recorders that append their name to the log and succeed."""
    with (
        patch.object(setup_environment, 'install_claude', _record_label(log, 'install_claude')),
        patch.object(setup_environment, 'install_ide_extensions', _record_label(log, 'install_ide_extensions')),
        patch.object(setup_environment, '_ensure_nodejs', _record_label(log, 'ensure_nodejs')),
        patch.object(setup_environment, '_installed_claude_version', return_value=None),
        patch.object(setup_environment, 'refresh_path_from_registry', lambda: None),
    ):
        yield


def _run(argv: list[str], install_log: Path, **kwargs: Any) -> int:
    """Run main() with --yes and --no-admin and the installers recorded."""
    with _recorded_installers(install_log):
        return run_main([*argv, *NO_ADMIN, '--yes'], **kwargs)


def _installs(log: Path) -> list[str]:
    """The installer calls recorded so far."""
    return log.read_text(encoding='utf-8').split() if log.exists() else []


def _runs(home: Path) -> list[str]:
    """The lines the shared and platform commands appended so far."""
    log = home / RUNS_LOG
    return log.read_text(encoding='utf-8').split() if log.exists() else []


def _reset(home: Path, install_log: Path) -> None:
    """Forget every recorded run and installer call and remove every marker directory."""
    (home / RUNS_LOG).unlink(missing_ok=True)
    install_log.unlink(missing_ok=True)
    for marker in (home / '.claude').glob('**/dep-marker'):
        marker.rmdir()


def _marker(claude_dir: Path, profile: str) -> Path:
    return claude_dir / profile / 'dep-marker'


def _output(capsys: pytest.CaptureFixture[str]) -> str:
    """Everything the run printed, color codes stripped and line endings normalized."""
    captured = capsys.readouterr()
    return _ANSI_SEQUENCE.sub('', captured.out + captured.err).replace('\r\n', '\n')


def _fd_output(capfd: pytest.CaptureFixture[str]) -> str:
    """Everything the run and its child processes printed, color codes stripped and line endings normalized."""
    captured = capfd.readouterr()
    return _ANSI_SEQUENCE.sub('', captured.out + captured.err).replace('\r\n', '\n')


def _from_source_rows(output: str, source: str) -> list[str]:
    """The text of every [from source NAME] row of the installation summary."""
    prefix = f'[from source {source}] '
    return [line.split(prefix, 1)[1] for line in output.splitlines() if prefix in line]


def _dependency_rows(output: str) -> list[str]:
    """The commands listed under Dependencies (shell commands)."""
    return [line.strip()[2:] for line in output.splitlines() if line.strip().startswith('$ ')]


def _install_source(configs: Path, install_log: Path, config: dict[str, Any] | None = None) -> Path:
    """Install the configuration as the full isolated profile team-1 and return the configuration path."""
    cfg = write_config(configs, 'team.yaml', config or _config())
    assert _run([str(cfg), '--command-names', SOURCE], install_log) == 0
    return cfg


def _write_recording_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Write the runner child runs go through, with the installers recorded into the install log."""
    runner = tmp_path / 'recording_runner.py'
    runner.write_text(RECORDING_RUNNER, encoding='utf-8')
    monkeypatch.setenv('PYTHONPATH', str(REPO_ROOT))
    return runner


def _assert_source_ran_everything(home: Path, install_log: Path, claude_dir: Path) -> None:
    """The full install of the source ran the binary install and every command, the marker inside its profile."""
    assert _installs(install_log) == ['install_claude']
    assert _runs(home) == ONE_RUN
    assert _marker(claude_dir, SOURCE).is_dir()


@pytest.mark.usefixtures('e2e_isolated_home')
class TestDependentLeavesWorkToSource:
    """A profile that links content skips the work its source's run does for the machine."""

    def test_all_link_leaves_the_binary_and_the_shared_commands_to_the_source(
        self, e2e_isolated_home: dict[str, Path], configs: Path, install_log: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The dependent installs no binary, runs no shared command, runs its re-rooted command, and says so."""
        home, claude_dir = e2e_isolated_home['home'], e2e_isolated_home['claude_dir']
        cfg = _install_source(configs, install_log)
        _assert_source_ran_everything(home, install_log, claude_dir)
        capsys.readouterr()

        code = _run([str(cfg), '--command-names', DEPENDENT, '--link-dirs', 'all', '--link-from', SOURCE], install_log)

        output = _output(capsys)
        assert code == 0, output
        assert _installs(install_log) == ['install_claude'], 'the dependent installed no binary'
        assert _runs(home) == ONE_RUN, 'the dependent ran neither the shared nor the platform command'
        assert _marker(claude_dir, DEPENDENT).is_dir(), 'the command re-rooted into the dependent ran there'
        # The installation summary, before consent
        assert f'* Claude Code: skip (left to source profile "{SOURCE}")' in output
        assert (
            f'Left to source profile "{SOURCE}" (its run does this work for the machine; '
            '--run-all-commands repeats it in this profile):'
        ) in output
        assert _from_source_rows(output, SOURCE) == ['Claude Code install or upgrade', PLATFORM_COMMAND, SHARED]
        assert _dependency_rows(output) == [f'{_rerooted_marker(DEPENDENT)} [re-rooted]'], (
            'only the command this profile runs itself is listed as a dependency'
        )
        assert 'Claude Code binary:' not in output, 'the dependent names no binary write among the machine-wide ones'
        assert 'Dependency commands: run machine-wide (listed above)' in output
        # The steps
        assert f'Step 1: Skipping Claude Code installation (left to source profile "{SOURCE}")' in output
        assert f'Left to source profile "{SOURCE}": {PLATFORM_COMMAND}' in output
        assert f'Left to source profile "{SOURCE}": {SHARED}' in output
        assert f'Running: {_rerooted_marker(DEPENDENT)}' in output
        assert f'Running: {SHARED}' not in output
        # The completion summary
        assert f'* Claude Code installation: Skipped (left to source profile "{SOURCE}")' in output
        assert f'* Left to source profile "{SOURCE}" (pass --run-all-commands to run them in this profile):' in output
        assert '- Claude Code install or upgrade' in output
        assert f'- {SHARED}' in output
        assert f'- {PLATFORM_COMMAND}' in output

    def test_dependent_rerun_by_name_leaves_the_same_work_to_the_source(
        self, e2e_isolated_home: dict[str, Path], configs: Path, install_log: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--profile NAME of a dependent skips the same items as its install did."""
        home, claude_dir = e2e_isolated_home['home'], e2e_isolated_home['claude_dir']
        cfg = _install_source(configs, install_log)
        assert _run([str(cfg), '--command-names', DEPENDENT, '--link-dirs', 'all', '--link-from', SOURCE], install_log) == 0
        _reset(home, install_log)
        capsys.readouterr()

        code = _run(['--profile', DEPENDENT], install_log)

        output = _output(capsys)
        assert code == 0, output
        assert _installs(install_log) == []
        assert _runs(home) == []
        assert _marker(claude_dir, DEPENDENT).is_dir()
        assert not _marker(claude_dir, SOURCE).exists(), 'a dependent run writes nothing into the source'
        assert _from_source_rows(output, SOURCE) == ['Claude Code install or upgrade', PLATFORM_COMMAND, SHARED]

    def test_partial_content_link_leaves_the_same_work_to_the_source(
        self, e2e_isolated_home: dict[str, Path], configs: Path, install_log: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Linking one content entry makes the profile a dependent, so the source's work is left to it."""
        home, claude_dir = e2e_isolated_home['home'], e2e_isolated_home['claude_dir']
        cfg = _install_source(configs, install_log)
        capsys.readouterr()

        code = _run([str(cfg), '--command-names', DEPENDENT, '--link-dirs', 'agents', '--link-from', SOURCE], install_log)

        output = _output(capsys)
        assert code == 0, output
        assert _installs(install_log) == ['install_claude']
        assert _runs(home) == ONE_RUN
        assert _marker(claude_dir, DEPENDENT).is_dir()
        assert _from_source_rows(output, SOURCE) == ['Claude Code install or upgrade', PLATFORM_COMMAND, SHARED]

    def test_projects_only_link_runs_everything(
        self, e2e_isolated_home: dict[str, Path], configs: Path, install_log: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A profile that links only sessions follows no source, so it installs and runs everything itself."""
        home, claude_dir = e2e_isolated_home['home'], e2e_isolated_home['claude_dir']
        cfg = _install_source(configs, install_log)
        capsys.readouterr()

        code = _run([str(cfg), '--command-names', DEPENDENT, '--link-dirs', 'projects', '--link-from', SOURCE], install_log)

        output = _output(capsys)
        assert code == 0, output
        assert _installs(install_log) == ['install_claude', 'install_claude']
        assert _runs(home) == ONE_RUN + ONE_RUN
        assert _marker(claude_dir, DEPENDENT).is_dir()
        assert 'from source' not in output
        assert 'Left to source profile' not in output
        assert '* Claude Code: install (version: latest)' in output
        assert '* Claude Code installation: Completed' in output

    def test_full_copy_runs_everything(
        self, e2e_isolated_home: dict[str, Path], configs: Path, install_log: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A second full profile of the same configuration shares nothing and runs everything itself."""
        home, claude_dir = e2e_isolated_home['home'], e2e_isolated_home['claude_dir']
        cfg = _install_source(configs, install_log)
        capsys.readouterr()

        code = _run([str(cfg), '--command-names', DEPENDENT], install_log)

        output = _output(capsys)
        assert code == 0, output
        assert _installs(install_log) == ['install_claude', 'install_claude']
        assert _runs(home) == ONE_RUN + ONE_RUN
        assert _marker(claude_dir, DEPENDENT).is_dir()
        assert 'from source' not in output
        assert _dependency_rows(output) == [SHARED, PLATFORM_COMMAND, f'{_rerooted_marker(DEPENDENT)} [re-rooted]']

    def test_source_rerun_runs_everything(
        self, e2e_isolated_home: dict[str, Path], configs: Path, install_log: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The source is a full profile: its re-run installs the binary and runs every command again."""
        home = e2e_isolated_home['home']
        _install_source(configs, install_log)
        capsys.readouterr()

        assert _run(['--profile', SOURCE], install_log) == 0

        assert _installs(install_log) == ['install_claude', 'install_claude']
        assert _runs(home) == ONE_RUN + ONE_RUN
        assert 'from source' not in _output(capsys)

    def test_dependent_of_the_base_skips_the_commands_the_base_runs_as_authored(
        self, e2e_isolated_home: dict[str, Path], configs: Path, install_log: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The base's run executes its commands as written; the dependent skips those and runs its re-rooted one."""
        home, claude_dir = e2e_isolated_home['home'], e2e_isolated_home['claude_dir']
        cfg = write_config(configs, 'team.yaml', _config())
        assert _run([str(cfg)], install_log) == 0
        assert _installs(install_log) == ['install_claude']
        assert _runs(home) == ONE_RUN
        assert (claude_dir / 'dep-marker').is_dir(), 'the base run created the marker where the configuration names it'
        capsys.readouterr()

        code = _run([str(cfg), '--command-names', DEPENDENT, '--link-dirs', 'all'], install_log)

        output = _output(capsys)
        assert code == 0, output
        assert _installs(install_log) == ['install_claude']
        assert _runs(home) == ONE_RUN
        assert _marker(claude_dir, DEPENDENT).is_dir()
        assert _from_source_rows(output, 'base') == ['Claude Code install or upgrade', PLATFORM_COMMAND, SHARED]
        assert 'Step 1: Skipping Claude Code installation (left to source profile "base")' in output
        assert _dependency_rows(output) == [f'{_rerooted_marker(DEPENDENT)} [re-rooted]']

    def test_pinned_dependent_leaves_the_ide_extension_to_the_source(
        self, configs: Path, install_log: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A pinned configuration installs the IDE extension from the source's run only."""
        cfg = _install_source(configs, install_log, _config(**{'claude-code-version': '1.2.3'}))
        assert _installs(install_log) == ['install_claude', 'install_ide_extensions']
        capsys.readouterr()

        code = _run([str(cfg), '--command-names', DEPENDENT, '--link-dirs', 'all', '--link-from', SOURCE], install_log)

        output = _output(capsys)
        assert code == 0, output
        assert _installs(install_log) == ['install_claude', 'install_ide_extensions']
        assert _from_source_rows(output, SOURCE) == [
            'Claude Code install or upgrade',
            f'IDE extension {setup_environment.IDE_EXTENSION_ID} v1.2.3',
            PLATFORM_COMMAND,
            SHARED,
        ]
        assert f'Step 2: Skipping IDE extensions (left to source profile "{SOURCE}")' in output
        assert 'IDE extension anthropic.claude-code 1.2.3: installed into' not in output, (
            'the dependent names no IDE write among the machine-wide ones'
        )

    def test_dependent_leaves_the_nodejs_installation_to_the_source(
        self, configs: Path, install_log: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """install-nodejs: true is honored by the source's run; the dependent's Step 5 installs nothing."""
        cfg = _install_source(configs, install_log, _config(**{'install-nodejs': True}))
        assert _installs(install_log) == ['install_claude', 'ensure_nodejs']
        capsys.readouterr()

        code = _run([str(cfg), '--command-names', DEPENDENT, '--link-dirs', 'all', '--link-from', SOURCE], install_log)

        output = _output(capsys)
        assert code == 0, output
        assert _installs(install_log) == ['install_claude', 'ensure_nodejs']
        assert _from_source_rows(output, SOURCE) == [
            'Claude Code install or upgrade', 'Node.js installation', PLATFORM_COMMAND, SHARED,
        ]
        assert f'* Node.js: left to source profile "{SOURCE}"' in output
        assert f'Node.js installation requested (install-nodejs: true); left to source profile "{SOURCE}"' in output
        assert '- Node.js installation' in output

    def test_missing_binary_stops_a_dependent_run_and_names_the_source(
        self, configs: Path, install_log: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Step 1 still checks that the binary is present; a dependent is told to re-run its source or pass the flag."""
        cfg = _install_source(configs, install_log)
        capsys.readouterr()

        code = _run(
            [str(cfg), '--command-names', DEPENDENT, '--link-dirs', 'all', '--link-from', SOURCE], install_log,
            claude_path=None,
        )

        output = _output(capsys)
        assert code == 1, output
        assert 'Claude Code is not available in PATH' in output
        assert (
            f'Re-run the source profile first (--profile {SOURCE}), or pass --run-all-commands to install Claude Code '
            'from this profile'
        ) in output
        assert _installs(install_log) == ['install_claude'], 'the dependent attempted no install of its own'

    def test_dry_run_lists_the_rows_and_runs_nothing(
        self, e2e_isolated_home: dict[str, Path], configs: Path, install_log: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--dry-run of a dependent shows what is left to the source and what runs here, and changes nothing."""
        home, claude_dir = e2e_isolated_home['home'], e2e_isolated_home['claude_dir']
        cfg = _install_source(configs, install_log)
        _reset(home, install_log)
        capsys.readouterr()

        with _recorded_installers(install_log):
            code = run_main([
                str(cfg), *NO_ADMIN, '--dry-run', '--command-names', DEPENDENT, '--link-dirs', 'all', '--link-from', SOURCE,
            ])

        output = _output(capsys)
        assert code == 0, output
        assert 'Dry run complete. No changes were made.' in output
        assert _from_source_rows(output, SOURCE) == ['Claude Code install or upgrade', PLATFORM_COMMAND, SHARED]
        assert _dependency_rows(output) == [f'{_rerooted_marker(DEPENDENT)} [re-rooted]']
        assert _installs(install_log) == []
        assert _runs(home) == []
        assert not _marker(claude_dir, DEPENDENT).exists()
        assert not (claude_dir / DEPENDENT).exists()


@pytest.mark.usefixtures('e2e_isolated_home')
class TestRunAllCommands:
    """--run-all-commands and its twin make a dependent do the source's work itself."""

    def test_flag_makes_the_dependent_run_everything(
        self, e2e_isolated_home: dict[str, Path], configs: Path, install_log: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        home, claude_dir = e2e_isolated_home['home'], e2e_isolated_home['claude_dir']
        cfg = _install_source(configs, install_log)
        capsys.readouterr()

        code = _run(
            [str(cfg), '--command-names', DEPENDENT, '--link-dirs', 'all', '--link-from', SOURCE, '--run-all-commands'],
            install_log,
        )

        output = _output(capsys)
        assert code == 0, output
        assert _installs(install_log) == ['install_claude', 'install_claude']
        assert _runs(home) == ONE_RUN + ONE_RUN
        assert _marker(claude_dir, DEPENDENT).is_dir()
        assert 'from source' not in output
        assert 'Left to source profile' not in output
        assert '* Claude Code: install (version: latest)' in output
        assert _dependency_rows(output) == [SHARED, PLATFORM_COMMAND, f'{_rerooted_marker(DEPENDENT)} [re-rooted]']
        assert f'Configuration: applied from profile "{SOURCE}"' in output, 'the profile is still a dependent'

    def test_variable_makes_a_dependent_rerun_run_everything(
        self, e2e_isolated_home: dict[str, Path], configs: Path, install_log: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        home, claude_dir = e2e_isolated_home['home'], e2e_isolated_home['claude_dir']
        cfg = _install_source(configs, install_log)
        assert _run([str(cfg), '--command-names', DEPENDENT, '--link-dirs', 'all', '--link-from', SOURCE], install_log) == 0
        _reset(home, install_log)
        monkeypatch.setenv('CLAUDE_CODE_TOOLBOX_RUN_ALL_COMMANDS', '1')

        assert _run(['--profile', DEPENDENT], install_log) == 0

        assert _installs(install_log) == ['install_claude']
        assert _runs(home) == ONE_RUN
        assert _marker(claude_dir, DEPENDENT).is_dir()

    def test_variable_turns_the_flag_on_only_with_the_exact_value_1(
        self, e2e_isolated_home: dict[str, Path], configs: Path, install_log: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        home = e2e_isolated_home['home']
        cfg = _install_source(configs, install_log)
        assert _run([str(cfg), '--command-names', DEPENDENT, '--link-dirs', 'all', '--link-from', SOURCE], install_log) == 0
        _reset(home, install_log)
        monkeypatch.setenv('CLAUDE_CODE_TOOLBOX_RUN_ALL_COMMANDS', 'true')

        assert _run(['--profile', DEPENDENT], install_log) == 0

        assert _installs(install_log) == []
        assert _runs(home) == []

    def test_flag_changes_nothing_for_a_full_profile(
        self, e2e_isolated_home: dict[str, Path], configs: Path, install_log: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        home = e2e_isolated_home['home']
        cfg = write_config(configs, 'team.yaml', _config())
        capsys.readouterr()

        assert _run([str(cfg), '--command-names', SOURCE, '--run-all-commands'], install_log) == 0

        assert _installs(install_log) == ['install_claude']
        assert _runs(home) == ONE_RUN
        assert 'from source' not in _output(capsys)


@pytest.mark.usefixtures('e2e_isolated_home')
class TestChildRuns:
    """The children --profile all and a source's Step 23 start are dependents too, and receive the flag."""

    def _install_source_and_two_dependents(self, configs: Path, install_log: Path) -> Path:
        cfg = _install_source(configs, install_log)
        for name in ('team-2', 'team-3'):
            assert _run([str(cfg), '--command-names', name, '--link-dirs', 'all', '--link-from', SOURCE], install_log) == 0
        return cfg

    def _recording_run(
        self, argvs: list[list[str]], envs: list[dict[str, str]] | None = None,
    ) -> Callable[..., subprocess.CompletedProcess[Any]]:
        """Record the argv (and environment) of every child run started, and run it; other subprocesses pass through."""
        real_run = setup_environment.subprocess.run

        def _record(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
            if '--profile' in argv:
                argvs.append(list(argv))
                if envs is not None:
                    envs.append(dict(kwargs['env']))
            return real_run(argv, **kwargs)

        return _record

    def test_profile_all_runs_the_source_commands_once_and_the_rewritten_ones_per_profile(
        self, e2e_isolated_home: dict[str, Path], configs: Path, install_log: Path, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str],
    ) -> None:
        """Of the source and its two dependents, only the source installs the binary and runs the shared commands."""
        home, claude_dir = e2e_isolated_home['home'], e2e_isolated_home['claude_dir']
        self._install_source_and_two_dependents(configs, install_log)
        _reset(home, install_log)
        runner = _write_recording_runner(tmp_path, monkeypatch)
        argvs: list[list[str]] = []
        capfd.readouterr()

        with patch.object(setup_environment.subprocess, 'run', side_effect=self._recording_run(argvs)):
            code = run_main(['--profile', 'all', *NO_ADMIN, '--yes'], argv0=str(runner))

        output = _fd_output(capfd)
        assert code == 0, output
        assert [argv[argv.index('--profile') + 1] for argv in argvs] == [SOURCE, 'team-2', 'team-3']
        assert all('--run-all-commands' not in argv for argv in argvs)
        assert _installs(install_log) == ['install_claude'], 'the source child installed the binary once'
        assert _runs(home) == ONE_RUN, 'the shared commands ran once, in the source child'
        for name in (SOURCE, 'team-2', 'team-3'):
            assert _marker(claude_dir, name).is_dir(), f'the re-rooted command ran in {name}'
        assert output.count(f'Step 1: Skipping Claude Code installation (left to source profile "{SOURCE}")') == 2
        assert output.count(f'Left to source profile "{SOURCE}": {SHARED}') == 2
        assert '* team-2: ok' in output
        assert '* team-3: ok' in output

    def test_profile_all_hands_the_flag_to_every_child(
        self, e2e_isolated_home: dict[str, Path], configs: Path, install_log: Path, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str],
    ) -> None:
        """With --run-all-commands every child installs the binary and runs every command itself."""
        home, claude_dir = e2e_isolated_home['home'], e2e_isolated_home['claude_dir']
        self._install_source_and_two_dependents(configs, install_log)
        _reset(home, install_log)
        runner = _write_recording_runner(tmp_path, monkeypatch)
        argvs: list[list[str]] = []
        capfd.readouterr()

        with patch.object(setup_environment.subprocess, 'run', side_effect=self._recording_run(argvs)):
            code = run_main(['--profile', 'all', *NO_ADMIN, '--yes', '--run-all-commands'], argv0=str(runner))

        output = _fd_output(capfd)
        assert code == 0, output
        assert len(argvs) == 3
        assert all(argv[-1] == '--run-all-commands' for argv in argvs), argvs
        assert _installs(install_log) == ['install_claude'] * 3
        assert sorted(_runs(home)) == sorted(ONE_RUN * 3)
        for name in (SOURCE, 'team-2', 'team-3'):
            assert _marker(claude_dir, name).is_dir()
        assert 'from source' not in output

    def test_profile_all_variable_reaches_the_children_as_the_flag(
        self, e2e_isolated_home: dict[str, Path], configs: Path, install_log: Path, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str],
    ) -> None:
        """The parent's twin is stripped from the children's environment, so it travels as the flag in argv."""
        home = e2e_isolated_home['home']
        self._install_source_and_two_dependents(configs, install_log)
        _reset(home, install_log)
        runner = _write_recording_runner(tmp_path, monkeypatch)
        monkeypatch.setenv('CLAUDE_CODE_TOOLBOX_RUN_ALL_COMMANDS', '1')
        argvs: list[list[str]] = []
        envs: list[dict[str, str]] = []
        capfd.readouterr()

        with patch.object(setup_environment.subprocess, 'run', side_effect=self._recording_run(argvs, envs)):
            code = run_main(['--profile', 'all', *NO_ADMIN, '--yes'], argv0=str(runner))

        output = _fd_output(capfd)
        assert code == 0, output
        assert all(argv[-1] == '--run-all-commands' for argv in argvs), argvs
        assert all('CLAUDE_CODE_TOOLBOX_RUN_ALL_COMMANDS' not in env for env in envs)
        assert sorted(_runs(home)) == sorted(ONE_RUN * 3)

    def test_step_23_children_leave_the_work_to_the_source_run_that_starts_them(
        self, e2e_isolated_home: dict[str, Path], configs: Path, install_log: Path, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str],
    ) -> None:
        """A source re-run runs everything once; the dependents it refreshes run only their re-rooted command."""
        home, claude_dir = e2e_isolated_home['home'], e2e_isolated_home['claude_dir']
        self._install_source_and_two_dependents(configs, install_log)
        _reset(home, install_log)
        runner = _write_recording_runner(tmp_path, monkeypatch)
        argvs: list[list[str]] = []
        capfd.readouterr()

        with (
            patch.object(setup_environment.subprocess, 'run', side_effect=self._recording_run(argvs)),
            _recorded_installers(install_log),
        ):
            code = run_main(['--profile', SOURCE, *NO_ADMIN, '--yes'], argv0=str(runner))

        output = _fd_output(capfd)
        assert code == 0, output
        assert 'Step 23: Refreshing 2 dependent profile(s): team-2, team-3...' in output
        assert [argv[argv.index('--profile') + 1] for argv in argvs] == ['team-2', 'team-3']
        assert all(argv[-1] == '--no-admin' for argv in argvs), 'no child carries the flag the source was not given'
        assert '* team-2 (--profile team-2 --yes --skip-install --no-admin)' in output
        assert _installs(install_log) == ['install_claude'], 'the source installed the binary; its children skip it'
        assert _runs(home) == ONE_RUN
        for name in (SOURCE, 'team-2', 'team-3'):
            assert _marker(claude_dir, name).is_dir()
        assert output.count(f'Left to source profile "{SOURCE}": {SHARED}') == 2
        assert '- team-2: ok' in output
        assert '- team-3: ok' in output

    def test_step_23_hands_the_flag_to_every_dependent(
        self, e2e_isolated_home: dict[str, Path], configs: Path, install_log: Path, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str],
    ) -> None:
        """--run-all-commands on the source run reaches each dependent child, which then runs every command."""
        home = e2e_isolated_home['home']
        self._install_source_and_two_dependents(configs, install_log)
        _reset(home, install_log)
        runner = _write_recording_runner(tmp_path, monkeypatch)
        argvs: list[list[str]] = []
        capfd.readouterr()

        with (
            patch.object(setup_environment.subprocess, 'run', side_effect=self._recording_run(argvs)),
            _recorded_installers(install_log),
        ):
            code = run_main(['--profile', SOURCE, *NO_ADMIN, '--yes', '--run-all-commands'], argv0=str(runner))

        output = _fd_output(capfd)
        assert code == 0, output
        assert all(argv[-2:] == ['--no-admin', '--run-all-commands'] for argv in argvs), argvs
        assert '* team-2 (--profile team-2 --yes --skip-install --no-admin --run-all-commands)' in output
        assert sorted(_runs(home)) == sorted(ONE_RUN * 3)
        assert 'from source' not in output

    def test_dry_run_of_a_source_shows_the_flag_in_the_dependents_rows_and_starts_none(
        self, e2e_isolated_home: dict[str, Path], configs: Path, install_log: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        home = e2e_isolated_home['home']
        self._install_source_and_two_dependents(configs, install_log)
        _reset(home, install_log)
        capsys.readouterr()

        with patch.object(setup_environment.subprocess, 'run') as run, _recorded_installers(install_log):
            code = run_main(['--profile', SOURCE, *NO_ADMIN, '--dry-run', '--run-all-commands'])

        run.assert_not_called()
        output = _output(capsys)
        assert code == 0, output
        assert '* team-2 (--profile team-2 --yes --skip-install --no-admin --run-all-commands)' in output
        assert '* team-3 (--profile team-3 --yes --skip-install --no-admin --run-all-commands)' in output
        assert _runs(home) == []
