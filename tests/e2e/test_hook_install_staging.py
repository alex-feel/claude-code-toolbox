"""E2E tests for installing the hook files and helper modules as one set.

A Claude Code session that is open while the setup runs starts hooks from the
hooks directory at any moment, so the directory must never hold a new hook
script beside an old or missing helper. download_hook_files() downloads every
hooks.files and hooks.helpers entry into a staging directory inside the hooks
directory and moves the files into place only after every download succeeded,
helpers first; a failed download leaves the installed files as they were. The
tests run the real download against the mock repository: one watches the
hooks directory from another thread during a parallel download, the other runs
main() with a hook source that does not exist.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import sys
import threading
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts import setup_environment
from scripts.setup_environment import download_hook_files
from tests.e2e.hook_sync_recorder import HookSyncRecorder
from tests.e2e.profile_support import run_main
from tests.e2e.profile_support import write_config

E2E_DIR = Path(__file__).parent
MOCK_REPO = E2E_DIR / 'fixtures' / 'mock_repo'
GOLDEN_COMMAND = 'e2e-test-cmd'
SAMPLE_INTERVAL_SECONDS = 0.02
# Appended to a source to make the copy an earlier run installed. The copy is
# longer than the source, so a file's size tells the old copy from the new one.
OLD_COPY_MARKER = b'\n# installed by an earlier run\n'
MISSING_SOURCE = 'hooks/e2e_missing_hook.py'
MISSING_HOOK = 'e2e_missing_hook.py'


@dataclass(frozen=True)
class _Sample:
    """One look at the hooks directory: two listings, one after the other.

    The scripts are judged from the first listing and the helpers from the
    second, so a script seen in its new version was moved into place before
    the helpers were looked at.
    """

    started: float
    finished: float
    first: dict[str, int]
    second: dict[str, int]


@dataclass(frozen=True)
class _HookSet:
    """The hook files of a configuration with the sizes of their old and new versions."""

    scripts: tuple[str, ...]
    helpers: tuple[str, ...]
    old_sizes: dict[str, int]
    new_sizes: dict[str, int]

    def states(self, sample: _Sample) -> dict[str, str]:
        """Classify every installed entry a sample saw.

        Args:
            sample: The look at the hooks directory.

        Returns:
            For each script and helper 'old', 'new', 'missing' or the size
            that matches neither version, and 'unexpected' for any other
            entry.
        """
        states = {name: self._state(name, sample.first) for name in self.scripts}
        states |= {name: self._state(name, sample.second) for name in self.helpers}
        for name in sorted((sample.first.keys() | sample.second.keys()) - {*self.scripts, *self.helpers}):
            states[name] = 'unexpected'
        return states

    def _state(self, name: str, sizes: dict[str, int]) -> str:
        size = sizes.get(name)
        if size is None:
            return 'missing'
        if size == self.old_sizes[name]:
            return 'old'
        if size == self.new_sizes[name]:
            return 'new'
        return f'size {size}'


def _install_old_set(hooks_dir: Path, repo: Path, sources: Sequence[str]) -> dict[str, bytes]:
    """Write the copy of every source an earlier run installed.

    Args:
        hooks_dir: The profile's hooks directory.
        repo: The repository the sources resolve in.
        sources: The hooks.files and hooks.helpers entries.

    Returns:
        The content written, by file name.
    """
    hooks_dir.mkdir(parents=True, exist_ok=True)
    installed: dict[str, bytes] = {}
    for source in sources:
        content = (repo / source).read_bytes() + OLD_COPY_MARKER
        (hooks_dir / Path(source).name).write_bytes(content)
        installed[Path(source).name] = content
    return installed


def _entry_sizes(hooks_dir: Path) -> dict[str, int]:
    """Read the size of every installed entry from one listing of the hooks directory.

    No file is opened: on Windows a handle on a file, even the one os.stat()
    takes, can make an os.replace() onto that file fail, which would turn the
    observation into a failed installation. Entries whose name starts with a
    dot, the staging directory among them, are not installed hook files.

    Args:
        hooks_dir: The profile's hooks directory.

    Returns:
        The size of each entry, by name.
    """
    with os.scandir(hooks_dir) as entries:
        return {entry.name: entry.stat().st_size for entry in entries if not entry.name.startswith('.')}


def _watch(hooks_dir: Path, stop: threading.Event) -> list[_Sample]:
    """Look at the hooks directory every SAMPLE_INTERVAL_SECONDS until stopped.

    The last look starts after the stop was requested, so the installation
    has returned before it.

    Args:
        hooks_dir: The profile's hooks directory.
        stop: Set when the installation has returned.

    Returns:
        Every look, in the order taken.
    """
    samples: list[_Sample] = []
    while True:
        stopping = stop.is_set()
        started = time.perf_counter()
        first = _entry_sizes(hooks_dir)
        second = _entry_sizes(hooks_dir)
        samples.append(_Sample(started, time.perf_counter(), first, second))
        if stopping:
            return samples
        stop.wait(SAMPLE_INTERVAL_SECONDS)


def _wrong_looks(samples: list[_Sample], hook_set: _HookSet, expected: str, origin: float) -> list[str]:
    """Describe every look whose files are not all in the expected version."""
    wrong: list[str] = []
    for sample in samples:
        states = hook_set.states(sample)
        if set(states.values()) != {expected}:
            wrong.append(f'{sample.started - origin:.3f} s: expected every file {expected}, saw {states}')
    return wrong


def _section(output: str, start: str, end: str) -> str:
    """Return the output from the line that opens a step up to the line that opens the next one."""
    begin = output.index(start)
    return output[begin:output.index(end, begin)]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A copy of the mock repository, so the configuration can be written beside its resources."""
    destination = tmp_path / 'repo'
    shutil.copytree(MOCK_REPO, destination)
    return destination


class TestHookSetMovesIntoPlaceAfterTheDownloads:
    """The hooks directory holds the old set during the downloads and the new set after them."""

    def test_running_session_never_sees_a_mixed_hook_set(
        self,
        e2e_isolated_home: dict[str, Path],
        golden_config: dict[str, Any],
        mock_repo_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A watcher of the hooks directory during a parallel download sees the old set, then the new one.

        The downloads take seconds: two workers with half a second between
        submissions. The promotion pass that follows moves each file with its
        own os.replace(), helpers first, so a look that overlaps the pass may
        see some files new and others old, but never a new script beside an
        old helper; every look before the pass sees only old files and every
        look after it only new ones.
        """
        monkeypatch.delenv('CLAUDE_CODE_TOOLBOX_SEQUENTIAL_MODE', raising=False)
        hooks = golden_config['hooks']
        sources = [*hooks['files'], *hooks['helpers']]
        claude_dir = e2e_isolated_home['claude_dir']
        hooks_dir = claude_dir / GOLDEN_COMMAND / 'hooks'
        old = _install_old_set(hooks_dir, mock_repo_path, sources)
        new = {Path(source).name: (mock_repo_path / source).read_bytes() for source in sources}
        hook_set = _HookSet(
            scripts=tuple(Path(source).name for source in hooks['files']),
            helpers=tuple(Path(source).name for source in hooks['helpers']),
            old_sizes={name: len(content) for name, content in old.items()},
            new_sizes={name: len(content) for name, content in new.items()},
        )

        promotion_passes: list[tuple[float, float]] = []
        promote = setup_environment._promote_staged_hook_files

        def timed_promote(staging_dir: Path, target_dir: Path, ordered_names: Sequence[str]) -> str | None:
            started = time.perf_counter()
            try:
                return promote(staging_dir, target_dir, ordered_names)
            finally:
                promotion_passes.append((started, time.perf_counter()))

        monkeypatch.setattr(setup_environment, '_promote_staged_hook_files', timed_promote)

        stop = threading.Event()
        with ThreadPoolExecutor(max_workers=1) as pool:
            watcher = pool.submit(_watch, hooks_dir, stop)
            try:
                installed = download_hook_files(
                    hooks, claude_dir, str(mock_repo_path / 'config.yaml'), hooks_base_dir=hooks_dir,
                )
            finally:
                stop.set()
            samples = watcher.result()

        assert installed
        assert len(promotion_passes) == 1, promotion_passes
        promotion_started, promotion_finished = promotion_passes[0]
        before = [sample for sample in samples if sample.finished < promotion_started]
        after = [sample for sample in samples if sample.started > promotion_finished]
        assert before, 'no look at the hooks directory during the downloads'
        assert after, 'no look at the hooks directory after the promotion pass'

        origin = samples[0].started
        wrong = _wrong_looks(before, hook_set, 'old', origin) + _wrong_looks(after, hook_set, 'new', origin)
        for sample in samples:
            states = hook_set.states(sample)
            new_script = any(states[name] == 'new' for name in hook_set.scripts)
            if new_script and any(states[name] != 'new' for name in hook_set.helpers):
                wrong.append(f'{sample.started - origin:.3f} s: a new script beside an old or missing helper: {states}')
        assert not wrong, f'{len(wrong)} of {len(samples)} looks went wrong:\n' + '\n'.join(wrong[:5])

        assert sorted(os.listdir(hooks_dir)) == sorted(new)
        for name, content in new.items():
            assert (hooks_dir / name).read_bytes() == content, name


class TestFailedHookDownload:
    """A hook source that cannot be downloaded fails the run and leaves the installed set alone."""

    def test_failed_hook_download_leaves_the_installed_set_and_reports_the_file(
        self,
        e2e_isolated_home: dict[str, Path],
        repo: Path,
        hook_sync_recorder: HookSyncRecorder,
        capfd: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Step 17 names the missing file, every installed hook file stays byte for byte, and Step 19 is skipped.

        The run uses sequential mode, which installs the hook set through the
        same staging directory as parallel mode.
        """
        monkeypatch.setenv('CLAUDE_CODE_TOOLBOX_SEQUENTIAL_MODE', '1')
        with (E2E_DIR / 'golden_config.yaml').open(encoding='utf-8') as handle:
            config: dict[str, Any] = yaml.safe_load(handle)
        config.pop('base-url', None)
        installed_sources = [*config['hooks']['files'], *config['hooks']['helpers']]
        config['hooks']['files'].append(MISSING_SOURCE)
        config['hooks']['events'].append(
            {'event': 'PostToolUse', 'matcher': 'Bash', 'type': 'command', 'command': MISSING_HOOK},
        )
        hooks_dir = e2e_isolated_home['claude_dir'] / GOLDEN_COMMAND / 'hooks'
        old = _install_old_set(hooks_dir, repo, installed_sources)
        cfg = write_config(repo, 'golden.yaml', config)
        capfd.readouterr()

        # Error lines go to stderr; printing them to stdout keeps every line
        # in the order the run printed it, so each one is found in its step
        with contextlib.redirect_stderr(sys.stdout):
            code = run_main([str(cfg), '--skip-install', '--no-admin', '--yes'])

        captured = capfd.readouterr()
        output = (captured.out + captured.err).replace('\r\n', '\n')
        assert code == 1, output
        step_17 = _section(output, 'Step 17: Downloading hooks...', 'Step 18: ')
        assert (
            f'Hook files failed to download: {MISSING_HOOK}; the installed hook files were left unchanged'
        ) in step_17, step_17
        assert 'moved into place' not in step_17, step_17
        step_19 = _section(output, 'Step 19: Preparing hook environments...', 'Step 20: ')
        assert 'Skipped: the hook files failed to download' in step_19, step_19
        assert hook_sync_recorder.records() == []
        errors_block = output[output.index('Setup Completed with Errors'):]
        assert 'The following resources failed to download:' in errors_block, errors_block
        assert '  - hook files' in errors_block, errors_block

        assert sorted(os.listdir(hooks_dir)) == sorted(old)
        for name, content in old.items():
            assert (hooks_dir / name).read_bytes() == content, name
