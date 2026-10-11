"""E2E tests for Step 19, which prepares the uv environment of every PEP 723 hook.

After a profile's hook files and settings file are in place, the setup runs
``uv sync --script "<hooks dir>/<file>" --python 3.12`` for every wired
Python command hook and status-line file that declares PEP 723 metadata, on
the path spelling the written hook command uses, in the hooks directory, and
in the environment a session hands its hooks. Every case runs through
main() in the isolated home with the autouse recorder of tests/e2e/conftest.py
standing in for uv, in the parent run and in every child run, so the tests
assert on exactly what each sync would have run.

The golden configurations wire two Python files: e2e_test_hook.py, whose
PEP 723 block declares no dependencies, and the plain e2e_statusline.py, so
a golden run prepares exactly one file and skips one.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts import setup_environment
from tests.e2e.hook_sync_recorder import FAILED_SYNC_STDERR
from tests.e2e.hook_sync_recorder import FAILING_VARIABLE
from tests.e2e.hook_sync_recorder import HookSyncRecorder
from tests.e2e.profile_support import run_main
from tests.e2e.profile_support import write_child_runner
from tests.e2e.profile_support import write_config

E2E_DIR = Path(__file__).parent
MOCK_REPO = E2E_DIR / 'fixtures' / 'mock_repo'
SKIP = ['--skip-install', '--no-admin']

PEP723_HOOK = 'e2e_test_hook.py'
PLAIN_HOOK = 'e2e_statusline.py'
SECOND_PEP723_HOOK = 'second_hook.py'
GOLDEN_COMMAND = 'e2e-test-cmd'

STEP_LINE = 'Step 19: Preparing hook environments...'
PREPARING_LINE = f'Preparing the environment of {PEP723_HOOK}'
SKIPPED_LINE = f'{PLAIN_HOOK}: no PEP 723 metadata'
SUMMARY_ROW = (
    f'* Hook environments: {PEP723_HOOK}, {PLAIN_HOOK} '
    '(uv builds an environment after download for each file with PEP 723 metadata)'
)
COMPLETION_ROW = '* Hook environments: 1 prepared, 1 without PEP 723 metadata'
ERRORS_HEADING = 'The following hook environments could not be prepared:'
DOWNLOAD_SKIP_LINE = 'Skipped: the hook files failed to download'


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A copy of the mock repository, so a test can add or remove a resource beside its configuration."""
    destination = tmp_path / 'repo'
    shutil.copytree(MOCK_REPO, destination)
    return destination


@pytest.fixture(autouse=True)
def _no_inherited_uv_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every run without the uv settings these tests assert on, whatever the developer's shell holds."""
    for name in ('UV_CACHE_DIR', 'UV_LOCKED', 'UV_FROZEN'):
        monkeypatch.delenv(name, raising=False)


def _golden(filename: str) -> dict[str, Any]:
    """Load a golden configuration with its resources resolved beside the configuration file.

    Args:
        filename: The golden configuration's file name.

    Returns:
        The configuration without base-url, so every resource resolves
        relative to the file it is written to in the repository copy.
    """
    with (E2E_DIR / filename).open(encoding='utf-8') as handle:
        config: dict[str, Any] = yaml.safe_load(handle)
    config.pop('base-url', None)
    return config


def _hooks_config(name: str = 'Hook Environments') -> dict[str, Any]:
    """A configuration wiring the PEP 723 hook, its helper, and the plain status line."""
    return {
        'name': name,
        'hooks': {
            'files': [f'hooks/{PEP723_HOOK}', f'hooks/{PLAIN_HOOK}'],
            'helpers': ['hooks/e2e_hook_helper.py'],
            'events': [{'event': 'PostToolUse', 'matcher': 'Edit', 'type': 'command', 'command': PEP723_HOOK}],
        },
        'status-line': {'file': PLAIN_HOOK},
    }


def _hook_path(hooks_dir: Path, name: str = PEP723_HOOK) -> str:
    """Spell a hook path the way the written hook command spells it."""
    return (hooks_dir / name).as_posix()


def _sync_arguments(hook_path: str) -> list[str]:
    """The arguments after the uv executable in the sync the step runs for one hook path."""
    return ['sync', '--script', hook_path, '--python', '3.12']


def _is_uv(executable: str) -> bool:
    """Whether a recorded sync starts with the uv the run resolved on PATH when it started: an absolute path."""
    return Path(executable).is_absolute() and Path(executable).name.lower() in {'uv', 'uv.exe'}


def _output(capfd: pytest.CaptureFixture[str]) -> str:
    """Everything the run and its children printed, with Windows line endings normalized."""
    captured = capfd.readouterr()
    return (captured.out + captured.err).replace('\r\n', '\n')


def _sync_errors(records: list[dict[str, Any]], expected: list[Path]) -> list[str]:
    """Compare the recorded syncs with the hooks directories expected to sync the PEP 723 hook, in order.

    Args:
        records: The recorder's records.
        expected: One hooks directory per expected sync.

    Returns:
        Every mismatch, with the record it concerns.
    """
    errors: list[str] = []
    if len(records) != len(expected):
        errors.append(f'expected {len(expected)} sync(s), recorded {len(records)}: {records}')
    for index, (record, hooks_dir) in enumerate(zip(records, expected, strict=False)):
        arguments = _sync_arguments(_hook_path(hooks_dir))
        if not _is_uv(record['command'][0]) or record['command'][1:] != arguments:
            errors.append(f'sync {index}: command {record["command"]}, expected uv {arguments}')
        if record['cwd'] != str(hooks_dir):
            errors.append(f'sync {index}: working directory {record["cwd"]}, expected {hooks_dir}')
    return errors


def _output_errors(output: str, *expected: str) -> list[str]:
    """Name every expected text the output lacks."""
    return [f'output lacks {text!r}' for text in expected if text not in output]


@pytest.mark.usefixtures('e2e_isolated_home')
class TestGoldenRuns:
    """A golden run prepares the PEP 723 hook on the written path and skips the plain status line."""

    def test_isolated_run_prepares_the_pep723_hook_in_the_profile(
        self, e2e_isolated_home: dict[str, Path], repo: Path, hook_sync_recorder: HookSyncRecorder,
        capfd: pytest.CaptureFixture[str],
    ) -> None:
        """The sync names <profile>/hooks/e2e_test_hook.py, runs there, and every step text appears."""
        cfg = write_config(repo, 'golden.yaml', _golden('golden_config.yaml'))
        capfd.readouterr()

        code = run_main([str(cfg), *SKIP, '--yes'])

        captured = capfd.readouterr()
        output = (captured.out + captured.err).replace('\r\n', '\n')
        assert code == 0, output
        hooks_dir = e2e_isolated_home['claude_dir'] / GOLDEN_COMMAND / 'hooks'
        errors = _sync_errors(hook_sync_recorder.records(), [hooks_dir])
        errors += _output_errors(output, STEP_LINE, PREPARING_LINE, SKIPPED_LINE, SUMMARY_ROW, COMPLETION_ROW)
        assert not errors, '\n'.join(errors)
        # The summary goes to stderr when stdout is not a terminal; the step and
        # the completion row share stdout, where their order is observable
        assert captured.out.index(STEP_LINE) < captured.out.index(PREPARING_LINE) < captured.out.index(COMPLETION_ROW)

    def test_base_run_prepares_the_pep723_hook_in_the_base_hooks_directory(
        self, e2e_isolated_home: dict[str, Path], repo: Path, hook_sync_recorder: HookSyncRecorder,
        capfd: pytest.CaptureFixture[str],
    ) -> None:
        """A run without command names syncs ~/.claude/hooks/e2e_test_hook.py."""
        cfg = write_config(repo, 'golden-base.yaml', _golden('golden_config_no_command_names.yaml'))
        capfd.readouterr()

        code = run_main([str(cfg), *SKIP, '--yes'])

        output = _output(capfd)
        assert code == 0, output
        errors = _sync_errors(hook_sync_recorder.records(), [e2e_isolated_home['claude_dir'] / 'hooks'])
        errors += _output_errors(output, STEP_LINE, PREPARING_LINE, SKIPPED_LINE, SUMMARY_ROW, COMPLETION_ROW)
        assert not errors, '\n'.join(errors)

    @pytest.mark.skipif(sys.platform != 'win32', reason='Step 13 rebuilds PATH from the registry on Windows only')
    def test_uv_resolved_before_the_registry_path_rebuild(
        self, repo: Path, hook_sync_recorder: HookSyncRecorder, monkeypatch: pytest.MonkeyPatch,
        capfd: pytest.CaptureFixture[str],
    ) -> None:
        """The syncs run the uv found before Step 13 drops its directory from PATH.

        A CI runner puts uv on the job's PATH alone, which the registry
        rebuild of Step 13 does not hold, so the run has to resolve uv
        before that step and use the resolved path afterwards.
        """
        uv_before = shutil.which('uv')
        assert uv_before is not None, 'the suite runs under uv, so uv is on PATH when the run starts'
        uv_dir = Path(uv_before).parent

        def rebuild_without_uv() -> bool:
            entries = os.environ['PATH'].split(os.pathsep)
            os.environ['PATH'] = os.pathsep.join(entry for entry in entries if Path(entry) != uv_dir)
            return True

        monkeypatch.setattr(setup_environment, 'refresh_path_from_registry', rebuild_without_uv)
        cfg = write_config(repo, 'golden.yaml', _golden('golden_config.yaml'))
        capfd.readouterr()

        code = run_main([str(cfg), *SKIP, '--yes'])

        output = _output(capfd)
        assert code == 0, output
        assert 'uv is not on PATH' not in output
        records = hook_sync_recorder.records()
        assert len(records) == 1, records
        assert Path(records[0]['command'][0]) == Path(uv_before)

    def test_dry_run_names_the_files_and_syncs_nothing(
        self, repo: Path, hook_sync_recorder: HookSyncRecorder, capfd: pytest.CaptureFixture[str],
    ) -> None:
        """The summary row shows the candidates before consent; a dry run never reaches the step."""
        cfg = write_config(repo, 'golden.yaml', _golden('golden_config.yaml'))
        capfd.readouterr()

        code = run_main([str(cfg), *SKIP, '--dry-run'])

        output = _output(capfd)
        assert code == 0, output
        assert SUMMARY_ROW in output
        assert 'Step 19:' not in output
        assert hook_sync_recorder.records() == []


@pytest.mark.usefixtures('e2e_isolated_home')
class TestProfileRuns:
    """Re-runs, linked dependents and --profile all each prepare the paths their profiles write."""

    def test_profile_rerun_prepares_again(
        self, e2e_isolated_home: dict[str, Path], repo: Path, hook_sync_recorder: HookSyncRecorder,
    ) -> None:
        """--profile NAME re-runs the step from the manifest's configuration."""
        cfg = write_config(repo, 'hooks.yaml', _hooks_config())
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0
        hook_sync_recorder.clear()

        assert run_main(['--profile', 'team-1', *SKIP, '--yes']) == 0

        errors = _sync_errors(hook_sync_recorder.records(), [e2e_isolated_home['claude_dir'] / 'team-1' / 'hooks'])
        assert not errors, '\n'.join(errors)

    def test_linked_dependent_prepares_its_own_path(
        self, e2e_isolated_home: dict[str, Path], repo: Path, hook_sync_recorder: HookSyncRecorder,
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A dependent linking hooks/ syncs its own spelling through the link, also when the source's run refreshes it."""
        claude_dir = e2e_isolated_home['claude_dir']
        cfg = write_config(repo, 'hooks.yaml', _hooks_config())
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0
        hook_sync_recorder.clear()

        assert run_main([
            str(cfg), *SKIP, '--yes', '--command-names', 'team-2', '--link-dirs', 'hooks', '--link-from', 'team-1',
        ]) == 0

        errors = _sync_errors(hook_sync_recorder.records(), [claude_dir / 'team-2' / 'hooks'])
        assert not errors, '\n'.join(errors)

        # The source's re-run refreshes the dependent in a child run (Step 24),
        # which records into the same file
        hook_sync_recorder.clear()
        runner = write_child_runner(tmp_path, monkeypatch)
        assert run_main(['--profile', 'team-1', *SKIP, '--yes'], argv0=str(runner)) == 0

        errors = _sync_errors(
            hook_sync_recorder.records(), [claude_dir / 'team-1' / 'hooks', claude_dir / 'team-2' / 'hooks'],
        )
        assert not errors, '\n'.join(errors)

    @pytest.mark.skipif(sys.platform != 'win32', reason='Step 13 rebuilds PATH from the registry on Windows only')
    def test_child_run_finds_uv_through_the_launcher_variable(
        self, e2e_isolated_home: dict[str, Path], repo: Path, hook_sync_recorder: HookSyncRecorder,
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A dependent refreshed as a child starts with the parent's rebuilt PATH and still finds uv.

        The parent resolves uv before Step 13 drops its directory from PATH;
        the child starts with that PATH and resolves uv from the UV
        variable the launching uv set, which the parent hands down.
        """
        uv_before = shutil.which('uv')
        assert uv_before is not None, 'the suite runs under uv, so uv is on PATH when the run starts'
        uv_dir = Path(uv_before).parent
        claude_dir = e2e_isolated_home['claude_dir']
        cfg = write_config(repo, 'hooks.yaml', _hooks_config())
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0
        assert run_main([
            str(cfg), *SKIP, '--yes', '--command-names', 'team-2', '--link-dirs', 'hooks', '--link-from', 'team-1',
        ]) == 0
        hook_sync_recorder.clear()

        def rebuild_without_uv() -> bool:
            entries = os.environ['PATH'].split(os.pathsep)
            os.environ['PATH'] = os.pathsep.join(entry for entry in entries if Path(entry) != uv_dir)
            return True

        monkeypatch.setattr(setup_environment, 'refresh_path_from_registry', rebuild_without_uv)
        monkeypatch.setenv('UV', uv_before)
        runner = write_child_runner(tmp_path, monkeypatch)

        assert run_main(['--profile', 'team-1', *SKIP, '--yes'], argv0=str(runner)) == 0

        records = hook_sync_recorder.records()
        errors = _sync_errors(records, [claude_dir / 'team-1' / 'hooks', claude_dir / 'team-2' / 'hooks'])
        assert not errors, '\n'.join(errors)
        assert [Path(record['command'][0]) for record in records] == [Path(uv_before), Path(uv_before)]

    def test_profile_all_children_prepare_every_profile(
        self, e2e_isolated_home: dict[str, Path], repo: Path, hook_sync_recorder: HookSyncRecorder,
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Every --profile all child records its own profile's sync; the parent syncs nothing itself."""
        claude_dir = e2e_isolated_home['claude_dir']
        base = write_config(repo, 'base.yaml', _hooks_config('Base Hooks'))
        team = write_config(repo, 'team.yaml', _hooks_config('Team Hooks'))
        assert run_main([str(base), *SKIP, '--yes']) == 0
        assert run_main([str(team), *SKIP, '--yes', '--command-names', 'team-1']) == 0
        hook_sync_recorder.clear()
        runner = write_child_runner(tmp_path, monkeypatch)

        assert run_main(['--profile', 'all', *SKIP, '--yes'], argv0=str(runner)) == 0

        errors = _sync_errors(hook_sync_recorder.records(), [claude_dir / 'hooks', claude_dir / 'team-1' / 'hooks'])
        assert not errors, '\n'.join(errors)


@pytest.mark.usefixtures('e2e_isolated_home')
class TestFailures:
    """A failed sync fails the run after every other file is prepared; a failed download skips the step."""

    def test_failed_sync_is_reported_and_the_other_hook_is_still_prepared(
        self, e2e_isolated_home: dict[str, Path], repo: Path, hook_sync_recorder: HookSyncRecorder,
        monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str],
    ) -> None:
        """The errors block names the failed path with its retry command, and the run exits 1."""
        (repo / 'hooks' / SECOND_PEP723_HOOK).write_text(
            '# /// script\n# dependencies = []\n# ///\nprint("second")\n', encoding='utf-8',
        )
        config = _hooks_config()
        config['hooks']['files'].append(f'hooks/{SECOND_PEP723_HOOK}')
        config['hooks']['events'].append(
            {'event': 'PreToolUse', 'matcher': 'Bash', 'type': 'command', 'command': SECOND_PEP723_HOOK},
        )
        cfg = write_config(repo, 'hooks.yaml', config)
        monkeypatch.setenv(FAILING_VARIABLE, PEP723_HOOK)
        capfd.readouterr()

        code = run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1'])

        captured = capfd.readouterr()
        output = (captured.out + captured.err).replace('\r\n', '\n')
        stderr = captured.err.replace('\r\n', '\n')
        assert code == 1, output
        hooks_dir = e2e_isolated_home['claude_dir'] / 'team-1' / 'hooks'
        failed = _hook_path(hooks_dir)
        recorded = [record['command'] for record in hook_sync_recorder.records()]
        assert all(_is_uv(command[0]) for command in recorded), recorded
        assert [command[1:] for command in recorded] == [
            _sync_arguments(failed), _sync_arguments(_hook_path(hooks_dir, SECOND_PEP723_HOOK)),
        ]
        errors = _output_errors(
            stderr, ERRORS_HEADING, f'  - {failed}', f'retry by hand: uv sync --script "{failed}" --python 3.12',
            FAILED_SYNC_STDERR,
        )
        errors += _output_errors(output, f'Preparing the environment of {SECOND_PEP723_HOOK}')
        assert not errors, '\n'.join(errors)

    def test_failed_hook_download_skips_the_step(
        self, repo: Path, hook_sync_recorder: HookSyncRecorder, capfd: pytest.CaptureFixture[str],
    ) -> None:
        """A hook file that cannot be downloaded leaves nothing complete to prepare."""
        (repo / 'hooks' / PLAIN_HOOK).unlink()
        cfg = write_config(repo, 'hooks.yaml', _hooks_config())
        capfd.readouterr()

        code = run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1'])

        output = _output(capfd)
        assert code == 1, output
        assert STEP_LINE in output
        assert DOWNLOAD_SKIP_LINE in output
        assert hook_sync_recorder.records() == []


@pytest.mark.usefixtures('e2e_isolated_home')
class TestSyncEnvironment:
    """The sync runs in the environment a session hands its hooks, on the profile's real location."""

    @pytest.mark.parametrize('command_names', [['team-1'], None], ids=['isolated', 'base'])
    def test_uv_cache_dir_from_user_settings_reaches_the_sync(
        self, command_names: list[str] | None, repo: Path, hook_sync_recorder: HookSyncRecorder, tmp_path: Path,
    ) -> None:
        """A UV_CACHE_DIR in user-settings.env moves the environment the hook uses, so the sync uses it too."""
        cache = str(tmp_path / 'uv-cache')
        config = _hooks_config()
        config['user-settings'] = {'env': {'UV_CACHE_DIR': cache}}
        if command_names is not None:
            config['command-names'] = command_names
        cfg = write_config(repo, 'hooks.yaml', config)

        assert run_main([str(cfg), *SKIP, '--yes']) == 0

        records = hook_sync_recorder.records()
        assert len(records) == 1, records
        assert records[0]['uv_env'].get('UV_CACHE_DIR') == cache

    @pytest.mark.parametrize('with_lockfile', [False, True], ids=['no-lockfile', 'lockfile'])
    def test_uv_locked_follows_the_sidecar_lockfile(
        self, with_lockfile: bool, repo: Path, hook_sync_recorder: HookSyncRecorder, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """UV_LOCKED reaches the sync only when <hook>.lock lies beside the hook, where uv run honors it too."""
        config = _hooks_config()
        if with_lockfile:
            (repo / 'hooks' / f'{PEP723_HOOK}.lock').write_text('version = 1\n', encoding='utf-8')
            config['hooks']['helpers'].append(f'hooks/{PEP723_HOOK}.lock')
        cfg = write_config(repo, 'hooks.yaml', config)
        monkeypatch.setenv('UV_LOCKED', '1')

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0

        records = hook_sync_recorder.records()
        assert len(records) == 1, records
        if with_lockfile:
            assert records[0]['uv_env'].get('UV_LOCKED') == '1'
        else:
            assert 'UV_LOCKED' not in records[0]['uv_env']
            assert 'UV_LOCKED' not in records[0]['other_env_names']

    def test_relocated_profile_prepares_the_relocated_hooks_path(
        self, e2e_isolated_home: dict[str, Path], repo: Path, hook_sync_recorder: HookSyncRecorder, tmp_path: Path,
    ) -> None:
        """A profile moved by user-settings.env CLAUDE_CONFIG_DIR syncs the hook where its config.json names it."""
        relocated = tmp_path / 'relocated' / 'work'
        config = _hooks_config()
        config['command-names'] = ['relo']
        config['user-settings'] = {'env': {'CLAUDE_CONFIG_DIR': str(relocated)}}
        cfg = write_config(repo, 'hooks.yaml', config)

        assert run_main([str(cfg), *SKIP, '--yes']) == 0

        errors = _sync_errors(hook_sync_recorder.records(), [relocated / 'hooks'])
        assert not errors, '\n'.join(errors)
        assert not (e2e_isolated_home['claude_dir'] / 'relo' / 'hooks').exists()
