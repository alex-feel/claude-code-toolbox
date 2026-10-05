"""E2E tests for the work a profile that links content leaves to its source's run.

A profile that links content from a source (``--link-dirs all`` or any
content entry, with ``--link-from``) shares the one machine with it: the
Claude Code binary, the IDE extension, Node.js and the tools the dependency
commands install exist once, and the source's run installs them. Every run of
such a dependent -- a standalone install, ``--profile NAME``, a ``--profile
all`` child and a source's Step 23 refresh -- therefore skips the install and
upgrade of Step 1 (the presence check stays), the IDE extension of Step 2 and
the Node.js installation of Step 5. A dependent that links every content
entry (``all``, or each content entry listed) also skips every dependency
command whose text, after the run's re-rooting, equals a command the
source's run executes; a command rewritten into the profile still runs. A
dependent that links only some content entries runs every command, because
a command may write into a content directory it holds for real (the skills
CLI writes into ``CLAUDE_CONFIG_DIR``). A full copy, a profile that links
only ``projects``, the base profile and a source run everything, and
``--run-all-commands`` (or ``CLAUDE_CODE_TOOLBOX_RUN_ALL_COMMANDS=1``) makes
a dependent run everything too, also in the children ``--profile all`` and
Step 23 start. The installation summary and ``--dry-run`` name each skipped
item with its source, and the completion summary repeats them with the flag
that forces the full run. On Windows the elevation gate reads the same
decision: a dependent's dry run and real run list only the elevating work
the dependent does itself.

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
windows_only = pytest.mark.skipif(not IS_WINDOWS, reason='UAC elevation exists only on Windows')
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
# A command that writes into the skills/ of the profile running it, the way
# the skills CLI does: it reads the CLAUDE_CONFIG_DIR the setup exports, so
# its text names no config home and is the same in every isolated run
POSIX_SKILL_WRITE = 'mkdir -p "$CLAUDE_CONFIG_DIR/skills/e2e-skill"'
WINDOWS_SKILL_WRITE = 'New-Item -ItemType Directory -Force -Path "$env:CLAUDE_CONFIG_DIR\\skills\\e2e-skill" | Out-Null'
SKILL_WRITE = WINDOWS_SKILL_WRITE if IS_WINDOWS else POSIX_SKILL_WRITE
EVERY_CONTENT_ENTRY = ','.join(setup_environment.CONTENT_PROFILE_DIRS)
# Commands whose text the Windows elevation gate lists (a global npm install
# and a machine-scope winget install), spelled as PowerShell output so a run
# installs nothing; the winget one names the config home, so each isolated
# run re-roots it into its own profile
NPM_LIKE = 'Write-Output "npm install -g e2e-fake-cli"'
WINGET_LIKE = 'Write-Output "winget install --scope machine --log $env:USERPROFILE\\.claude\\winget.log"'
INSTALL_REASON = 'Installing Claude Code (includes Node.js and Git)'
DRY_RUN_HEADLINE = 'Dry run: administrator elevation is not requested.'
BANNER_TITLE = 'Administrator Privileges Required'
REASON_PREFIXES = ('Installing Claude Code', 'System-wide installation: ', 'Global npm package: ')
IDE_WRITE_ROW = f'IDE extension {setup_environment.IDE_EXTENSION_ID} 1.2.3: installed into code (used by every profile)'

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


def _rerooted_winget(profile: str) -> str:
    """Spell the winget-like command the way an isolated run of the given profile rewrites it."""
    return WINGET_LIKE.replace('\\.claude\\winget.log', f'\\.claude\\{profile}\\winget.log')


def _config_with_skill_write() -> dict[str, Any]:
    """The configuration plus the command that writes into the running profile's skills/."""
    config = _config()
    config['dependencies']['common'] = [SHARED, SKILL_WRITE]
    return config


def _elevating_config(*, winget: bool = True) -> dict[str, Any]:
    """The configuration plus the commands the Windows elevation gate lists.

    Args:
        winget: Whether the Windows list carries the machine-scope winget
            command, the one elevating command a dependent runs itself
            because its text is re-rooted into the profile.

    Returns:
        The configuration dictionary.
    """
    config = _config()
    config['dependencies']['common'] = [SHARED, NPM_LIKE]
    if winget:
        config['dependencies']['windows'] = [WINDOWS_PLATFORM, WINDOWS_MARKER, WINGET_LIKE]
    return config


def _elevation_reasons(output: str) -> list[str]:
    """The reasons the elevation gate listed, in order, from a dry run's report or a real run's banner."""
    reasons: list[str] = []
    for line in output.splitlines():
        marker = line.find('  - ')
        if marker == -1:
            continue
        reason = line[marker + 4:]
        if reason.startswith(REASON_PREFIXES):
            reasons.append(reason)
    return reasons


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

    def test_partial_content_link_leaves_the_installs_to_the_source_and_runs_every_command(
        self, e2e_isolated_home: dict[str, Path], configs: Path, install_log: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Linking one content entry leaves the binary to the source; every command runs, one into this profile's skills/."""
        home, claude_dir = e2e_isolated_home['home'], e2e_isolated_home['claude_dir']
        cfg = _install_source(configs, install_log, _config_with_skill_write())
        assert (claude_dir / SOURCE / 'skills' / 'e2e-skill').is_dir(), 'the source run wrote into its own skills/'
        capsys.readouterr()

        code = _run([str(cfg), '--command-names', DEPENDENT, '--link-dirs', 'agents', '--link-from', SOURCE], install_log)

        output = _output(capsys)
        assert code == 0, output
        assert _installs(install_log) == ['install_claude'], 'the binary install is left to the source'
        assert _runs(home) == ONE_RUN + ONE_RUN, 'the shared and platform commands ran again in the dependent'
        assert _marker(claude_dir, DEPENDENT).is_dir()
        assert setup_environment._is_directory_link(claude_dir / DEPENDENT / 'agents')
        dependent_skills = claude_dir / DEPENDENT / 'skills'
        assert dependent_skills.is_dir()
        assert not setup_environment._is_directory_link(dependent_skills), "skills/ is this profile's own directory"
        assert (dependent_skills / 'e2e-skill').is_dir(), 'the same-text command ran here and wrote into this profile'
        assert _from_source_rows(output, SOURCE) == ['Claude Code install or upgrade']
        assert f'Step 1: Skipping Claude Code installation (left to source profile "{SOURCE}")' in output
        assert _dependency_rows(output) == [
            SHARED, SKILL_WRITE, PLATFORM_COMMAND, f'{_rerooted_marker(DEPENDENT)} [re-rooted]',
        ]
        assert f'Running: {SHARED}' in output
        assert f'Running: {SKILL_WRITE}' in output
        assert f'Left to source profile "{SOURCE}": ' not in output, 'Step 6 leaves no command to the source'

    def test_every_content_entry_listed_leaves_the_same_work_to_the_source(
        self, e2e_isolated_home: dict[str, Path], configs: Path, install_log: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Listing each content entry links every content directory, so the shared commands are left to the source."""
        home, claude_dir = e2e_isolated_home['home'], e2e_isolated_home['claude_dir']
        cfg = _install_source(configs, install_log, _config_with_skill_write())
        capsys.readouterr()

        code = _run(
            [str(cfg), '--command-names', DEPENDENT, '--link-dirs', EVERY_CONTENT_ENTRY, '--link-from', SOURCE], install_log,
        )

        output = _output(capsys)
        assert code == 0, output
        assert _installs(install_log) == ['install_claude']
        assert _runs(home) == ONE_RUN
        assert _marker(claude_dir, DEPENDENT).is_dir()
        assert setup_environment._is_directory_link(claude_dir / DEPENDENT / 'skills')
        assert (claude_dir / DEPENDENT / 'skills' / 'e2e-skill').is_dir(), 'the skill the source wrote shows through the link'
        assert f'Running: {SKILL_WRITE}' not in output
        assert _from_source_rows(output, SOURCE) == ['Claude Code install or upgrade', PLATFORM_COMMAND, SHARED, SKILL_WRITE]
        assert _dependency_rows(output) == [f'{_rerooted_marker(DEPENDENT)} [re-rooted]']

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
        """A pinned configuration installs the IDE extension from the source's run only.

        IDE detection is stubbed to find one IDE, so the machine-wide row
        that names it is present where Step 2 installs and absent where the
        dependent leaves the install to the source; the stub also records
        that a run which leaves Step 2 to the source never probes the IDEs.
        """
        with patch.object(setup_environment, '_detect_vscode_family_ides', return_value=[('code', '/usr/bin/code')]) as detect:
            cfg = _install_source(configs, install_log, _config(**{'claude-code-version': '1.2.3'}))
            dependent = [str(cfg), '--command-names', DEPENDENT, '--link-dirs', 'all', '--link-from', SOURCE]
            source_output = _output(capsys)
            assert _installs(install_log) == ['install_claude', 'install_ide_extensions']
            assert IDE_WRITE_ROW in source_output, 'the source names the IDE write among its machine-wide ones'
            assert detect.call_count == 1, 'the source probes the IDEs once, for the summary row'
            detect.reset_mock()

            code = _run(dependent, install_log)

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
            assert IDE_WRITE_ROW not in output, 'the dependent names no IDE write among the machine-wide ones'
            assert detect.call_count == 0, 'a run that leaves Step 2 to the source never probes the IDEs'

            code = _run([*dependent, '--run-all-commands'], install_log)

            output = _output(capsys)
            assert code == 0, output
            assert _installs(install_log) == ['install_claude', 'install_ide_extensions'] * 2
            assert IDE_WRITE_ROW in output, 'with the flag the dependent installs the extension and names the write'
            assert 'Step 2: Installing IDE extensions...' in output
            assert detect.call_count == 1, 'with the flag the dependent probes the IDEs for its own summary row'

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


@windows_only
@pytest.mark.usefixtures('e2e_isolated_home')
class TestDependentElevationDecision:
    """The Windows elevation gate counts only the work a dependent does itself.

    The gate reads the install decision and the dependency lists after the
    shared commands came out of them, so a dependent that leaves the binary
    install and a global npm install to its source is never elevated for
    them, while the machine-scope winget command re-rooted into the profile
    is the profile's own and still counts. Every run here goes without
    ``--no-admin``, with the privilege probe reporting a non-elevated
    terminal.
    """

    DEPENDENT_ARGS = ('--command-names', DEPENDENT, '--link-dirs', 'all', '--link-from', SOURCE)

    def _dry_run(self, argv: list[str], install_log: Path) -> int:
        """Run main() with --dry-run and without --no-admin in a non-elevated terminal."""
        with _recorded_installers(install_log), patch.object(setup_environment, 'is_admin', return_value=False):
            return run_main([*argv, '--dry-run'])

    def test_dry_run_of_a_dependent_lists_only_the_rerooted_winget_command(
        self, configs: Path, install_log: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The binary install and the shared npm install are the source's; the re-rooted winget command is this profile's."""
        cfg = _install_source(configs, install_log, _elevating_config())
        capsys.readouterr()

        code = self._dry_run([str(cfg), *self.DEPENDENT_ARGS], install_log)

        output = _output(capsys)
        assert code == 0, output
        assert DRY_RUN_HEADLINE in output
        assert _elevation_reasons(output) == [f'System-wide installation: {_rerooted_winget(DEPENDENT)}']
        assert INSTALL_REASON not in output
        assert f'Global npm package: {NPM_LIKE}' not in output
        assert _from_source_rows(output, SOURCE) == ['Claude Code install or upgrade', WINDOWS_PLATFORM, SHARED, NPM_LIKE]

    def test_dry_run_of_a_dependent_whose_elevating_work_is_all_shared_reports_nothing(
        self, configs: Path, install_log: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """With the binary and the global npm install left to the source, nothing needs elevation here."""
        cfg = _install_source(configs, install_log, _elevating_config(winget=False))
        capsys.readouterr()

        code = self._dry_run([str(cfg), *self.DEPENDENT_ARGS], install_log)

        output = _output(capsys)
        assert code == 0, output
        assert DRY_RUN_HEADLINE not in output
        assert _elevation_reasons(output) == []
        assert 'Dry run complete. No changes were made.' in output

    def test_dry_run_with_the_flag_lists_every_reason_in_installation_order(
        self, configs: Path, install_log: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--run-all-commands makes the dependent's run elevate for the binary, the winget command and the npm install."""
        cfg = _install_source(configs, install_log, _elevating_config())
        capsys.readouterr()

        code = self._dry_run([str(cfg), *self.DEPENDENT_ARGS, '--run-all-commands'], install_log)

        output = _output(capsys)
        assert code == 0, output
        assert DRY_RUN_HEADLINE in output
        assert _elevation_reasons(output) == [
            INSTALL_REASON,
            f'System-wide installation: {_rerooted_winget(DEPENDENT)}',
            f'Global npm package: {NPM_LIKE}',
        ]

    def test_dry_run_of_a_full_copy_lists_every_reason(
        self, configs: Path, install_log: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A second full profile follows no source, so its run elevates for everything."""
        cfg = _install_source(configs, install_log, _elevating_config())
        capsys.readouterr()

        code = self._dry_run([str(cfg), '--command-names', DEPENDENT], install_log)

        output = _output(capsys)
        assert code == 0, output
        assert DRY_RUN_HEADLINE in output
        assert _elevation_reasons(output) == [
            INSTALL_REASON,
            f'System-wide installation: {_rerooted_winget(DEPENDENT)}',
            f'Global npm package: {NPM_LIKE}',
        ]
        assert 'from source' not in output

    def test_real_run_requests_elevation_only_for_the_work_the_dependent_does_itself(
        self, e2e_isolated_home: dict[str, Path], configs: Path, install_log: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """No banner opens for work left to the source; with the flag the banner lists it and the relaunch is requested."""
        claude_dir = e2e_isolated_home['claude_dir']
        cfg = _install_source(configs, install_log, _elevating_config(winget=False))
        capsys.readouterr()

        with (
            _recorded_installers(install_log),
            patch.object(setup_environment, 'is_admin', return_value=False),
            patch.object(setup_environment, 'request_admin_elevation') as relaunch,
        ):
            code = run_main([str(cfg), *self.DEPENDENT_ARGS, '--yes'])

        output = _output(capsys)
        assert code == 0, output
        relaunch.assert_not_called()
        assert BANNER_TITLE not in output
        assert _installs(install_log) == ['install_claude'], 'the dependent installed no binary'
        assert _marker(claude_dir, DEPENDENT).is_dir(), 'the run completed in the non-elevated process'
        capsys.readouterr()

        with (
            _recorded_installers(install_log),
            patch.object(setup_environment, 'is_admin', return_value=False),
            patch.object(setup_environment, 'request_admin_elevation') as relaunch,
        ):
            code = run_main([str(cfg), *self.DEPENDENT_ARGS, '--yes', '--run-all-commands'])

        output = _output(capsys)
        # The recorder returns instead of relaunching, which the gate reads as a denied elevation
        assert code == 1, output
        relaunch.assert_called_once_with()
        assert BANNER_TITLE in output
        assert _elevation_reasons(output) == [INSTALL_REASON, f'Global npm package: {NPM_LIKE}']
        assert 'Administrator elevation was denied' in output
        assert _installs(install_log) == ['install_claude'], 'the gate stopped the run before Step 1'


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

    def _install_base_and_a_dependent(
        self, configs: Path, install_log: Path, config: dict[str, Any] | None = None,
    ) -> Path:
        """Install the configuration as the base profile and team-2 as a dependent linking all from it."""
        cfg = write_config(configs, 'team.yaml', config or _config())
        assert _run([str(cfg)], install_log) == 0
        assert _run([str(cfg), '--command-names', DEPENDENT, '--link-dirs', 'all', '--link-from', 'base'], install_log) == 0
        return cfg

    def test_base_source_step_23_leaves_the_shared_commands_to_the_base_run(
        self, e2e_isolated_home: dict[str, Path], configs: Path, install_log: Path, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str],
    ) -> None:
        """--profile base refreshes its dependent, which skips the commands the base runs as authored and runs its own."""
        home, claude_dir = e2e_isolated_home['home'], e2e_isolated_home['claude_dir']
        self._install_base_and_a_dependent(configs, install_log)
        _reset(home, install_log)
        runner = _write_recording_runner(tmp_path, monkeypatch)
        argvs: list[list[str]] = []
        capfd.readouterr()

        with (
            patch.object(setup_environment.subprocess, 'run', side_effect=self._recording_run(argvs)),
            _recorded_installers(install_log),
        ):
            code = run_main(['--profile', 'base', *NO_ADMIN, '--yes'], argv0=str(runner))

        output = _fd_output(capfd)
        assert code == 0, output
        assert f'Step 23: Refreshing 1 dependent profile(s): {DEPENDENT}...' in output
        assert [argv[argv.index('--profile') + 1] for argv in argvs] == [DEPENDENT]
        assert argvs[0][-1] == '--no-admin', argvs
        assert '--run-all-commands' not in argvs[0], 'the child carries no flag the base run was not given'
        assert f'* {DEPENDENT} (--profile {DEPENDENT} --yes --skip-install --no-admin)' in output
        assert _installs(install_log) == ['install_claude'], 'the base installed the binary; its child skips it'
        assert _runs(home) == ONE_RUN, 'the shared and platform commands ran once, in the base'
        assert (claude_dir / 'dep-marker').is_dir(), 'the base ran its marker command as authored'
        assert _marker(claude_dir, DEPENDENT).is_dir(), 'the child ran its re-rooted marker command'
        assert f'Left to source profile "base": {SHARED}' in output
        assert f'Left to source profile "base": {PLATFORM_COMMAND}' in output
        assert output.count('Left to source profile "base": ') == 2, 'only the two same-text commands are left to the base'
        assert f'Running: {_rerooted_marker(DEPENDENT)}' in output
        assert f'- {DEPENDENT}: ok' in output

    def test_base_source_step_23_hands_the_flag_to_its_dependent(
        self, e2e_isolated_home: dict[str, Path], configs: Path, install_log: Path, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str],
    ) -> None:
        """--run-all-commands on a --profile base run reaches the child in argv, and the child runs every command itself."""
        home, claude_dir = e2e_isolated_home['home'], e2e_isolated_home['claude_dir']
        self._install_base_and_a_dependent(configs, install_log)
        _reset(home, install_log)
        runner = _write_recording_runner(tmp_path, monkeypatch)
        argvs: list[list[str]] = []
        capfd.readouterr()

        with (
            patch.object(setup_environment.subprocess, 'run', side_effect=self._recording_run(argvs)),
            _recorded_installers(install_log),
        ):
            code = run_main(['--profile', 'base', *NO_ADMIN, '--yes', '--run-all-commands'], argv0=str(runner))

        output = _fd_output(capfd)
        assert code == 0, output
        assert [argv[argv.index('--profile') + 1] for argv in argvs] == [DEPENDENT]
        assert argvs[0][-2:] == ['--no-admin', '--run-all-commands'], argvs
        assert f'* {DEPENDENT} (--profile {DEPENDENT} --yes --skip-install --no-admin --run-all-commands)' in output
        assert _installs(install_log) == ['install_claude'], '--skip-install keeps the child from installing the binary'
        assert sorted(_runs(home)) == sorted(ONE_RUN * 2), 'the child ran the shared and platform commands too'
        assert (claude_dir / 'dep-marker').is_dir()
        assert _marker(claude_dir, DEPENDENT).is_dir()
        assert 'from source' not in output
        assert 'Left to source profile' not in output

    @windows_only
    @pytest.mark.parametrize(
        ('source_flags', 'remedy_expected'),
        [
            pytest.param([], False, id='npm-install-left-to-the-base'),
            pytest.param(['--run-all-commands'], True, id='run-all-commands'),
        ],
    )
    def test_base_source_judges_a_failed_dependents_remedy_on_the_commands_it_runs_itself(
        self, source_flags: list[str], remedy_expected: bool, e2e_isolated_home: dict[str, Path], configs: Path,
        install_log: Path, tmp_path: Path, capfd: pytest.CaptureFixture[str],
    ) -> None:
        """The elevated-terminal remedy names a global npm install only when the dependent's own run executes it.

        The base runs the same command, so the dependent leaves it to the base
        and needs no elevation for it; with --run-all-commands the dependent
        runs it itself, and the remedy says so.
        """
        home = e2e_isolated_home['home']
        self._install_base_and_a_dependent(configs, install_log, _elevating_config(winget=False))
        _reset(home, install_log)
        runner = tmp_path / 'failing_runner.py'
        runner.write_text('import sys\nprint("child failed")\nsys.exit(1)\n', encoding='utf-8')
        capfd.readouterr()

        with patch.object(setup_environment, 'is_admin', return_value=False), _recorded_installers(install_log):
            code = run_main(['--profile', 'base', *NO_ADMIN, '--yes', *source_flags], argv0=str(runner))

        output = _fd_output(capfd)
        assert code == 1, output
        assert 'child failed' in output
        remedy = (
            f'- {DEPENDENT}: failed (exit code 1); retry with --profile {DEPENDENT} from an elevated terminal '
            '(a global npm install needs administrator rights the run could not request)'
        )
        if remedy_expected:
            assert remedy in output
        else:
            assert remedy not in output
            assert f'- {DEPENDENT}: failed (exit code 1); retry with --profile {DEPENDENT}' in output

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
