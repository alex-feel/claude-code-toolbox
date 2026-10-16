"""E2E tests for Step 19 against the real uv: the environment the setup builds is the one the hook uses.

The setup runs ``uv sync --script`` for every wired PEP 723 hook so the hook
command it writes, ``uv run --no-project --python 3.12 "<hooks dir>/<file>"``,
finds a ready environment on its first launch. These tests run main() with
the real uv against a cache of their own, from a working directory whose
uv.toml names an unreachable index, which the sync must not read because the
written command does not. They then run the written command offline and see
it install nothing, see an unsatisfiable dependency fail the setup with the
network, index and proxy note, and see a uv that cannot provide Python 3.12
fail it with the command that installs or repairs the interpreter.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.profile_support import run_main
from tests.e2e.profile_support import write_config

pytestmark = [
    pytest.mark.real_uv_sync,
    pytest.mark.skipif(shutil.which('uv') is None, reason='uv is not on PATH'),
]

SKIP = ['--skip-install', '--no-admin']
PEP723_HOOK = 'warm_hook.py'
PLAIN_HOOK = 'plain_hook.py'
UNREACHABLE_INDEX = 'http://127.0.0.1:9/simple/'
MISSING_DEPENDENCY = 'cct-e2e-nonexistent-package==0.0.0'
NETWORK_NOTE = 'Check the network, index and proxy settings the hook would use'
REPAIR_LINE = 'Install it with: uv python install --reinstall 3.12'
# The variables that would point uv at an interpreter outside the empty store
# the interpreter test gives it
INTERPRETER_SOURCES = (
    'VIRTUAL_ENV', 'CONDA_PREFIX', 'UV_PYTHON', 'UV_MANAGED_PYTHON', 'UV_NO_MANAGED_PYTHON', 'UV_SYSTEM_PYTHON',
)


def _write_hooks(repo: Path, dependencies: str) -> None:
    """Write the PEP 723 hook with the given dependency list and the plain hook."""
    hooks = repo / 'hooks'
    hooks.mkdir(parents=True, exist_ok=True)
    (hooks / PEP723_HOOK).write_text(
        f'# /// script\n# dependencies = {dependencies}\n# ///\nprint("warm hook ran")\n', encoding='utf-8',
    )
    (hooks / PLAIN_HOOK).write_text('print("plain hook ran")\n', encoding='utf-8')


def _config(command_name: str) -> dict[str, Any]:
    """A configuration wiring the PEP 723 hook and the plain hook as command hooks of an isolated profile."""
    return {
        'name': 'Real uv Hook Environments',
        'command-names': [command_name],
        'hooks': {
            'files': [f'hooks/{PEP723_HOOK}', f'hooks/{PLAIN_HOOK}'],
            'events': [
                {'event': 'PostToolUse', 'matcher': 'Edit', 'type': 'command', 'command': PEP723_HOOK},
                {'event': 'PreToolUse', 'matcher': 'Bash', 'type': 'command', 'command': PLAIN_HOOK},
            ],
        },
    }


def _written_command(profile_dir: Path, script: str) -> str:
    """Find the hook command config.json names for one script."""
    config = json.loads((profile_dir / 'config.json').read_text(encoding='utf-8'))
    for groups in config['hooks'].values():
        for group in groups:
            for hook in group['hooks']:
                if script in hook.get('command', ''):
                    command: str = hook['command']
                    return command
    raise AssertionError(f'config.json names no command for {script}: {config["hooks"]}')


@pytest.fixture
def uv_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A uv cache of the test's own, and a working directory whose uv.toml names an unreachable index."""
    cache = tmp_path / 'uv-cache'
    monkeypatch.setenv('UV_CACHE_DIR', str(cache))
    for name in ('UV_LOCKED', 'UV_FROZEN', 'UV_OFFLINE', 'UV_INDEX_URL', 'UV_DEFAULT_INDEX'):
        monkeypatch.delenv(name, raising=False)
    work = tmp_path / 'work'
    work.mkdir()
    (work / 'uv.toml').write_text(f'index-url = "{UNREACHABLE_INDEX}"\n', encoding='utf-8')
    monkeypatch.chdir(work)
    return cache


@pytest.mark.usefixtures('e2e_isolated_home')
class TestRealUvSync:
    """The real sync builds the hook's environment, and the written command reuses it."""

    def test_setup_builds_the_environment_the_written_command_uses(
        self, e2e_isolated_home: dict[str, Path], uv_cache: Path, tmp_path: Path, capfd: pytest.CaptureFixture[str],
    ) -> None:
        """One environment appears for the PEP 723 hook, and the written command then installs nothing offline."""
        repo = tmp_path / 'repo'
        _write_hooks(repo, '[]')
        cfg = write_config(repo, 'hooks.yaml', _config('warm'))
        capfd.readouterr()

        code = run_main([str(cfg), *SKIP, '--yes'])

        captured = capfd.readouterr()
        assert code == 0, captured.out + captured.err
        environments = sorted(path.name for path in (uv_cache / 'environments-v2').iterdir())
        assert len(environments) == 1, environments
        assert environments[0].startswith(Path(PEP723_HOOK).stem.replace('_', '-')), environments

        argv = shlex.split(_written_command(e2e_isolated_home['claude_dir'] / 'warm', PEP723_HOOK))
        elsewhere = tmp_path / 'elsewhere'
        elsewhere.mkdir()
        completed = subprocess.run(
            argv, cwd=elsewhere, env={**os.environ, 'UV_OFFLINE': '1'},
            capture_output=True, text=True, timeout=300, check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert 'warm hook ran' in completed.stdout
        assert 'Installed' not in completed.stdout + completed.stderr
        assert sorted(path.name for path in (uv_cache / 'environments-v2').iterdir()) == environments

    def test_unsatisfiable_dependency_fails_the_setup(
        self, e2e_isolated_home: dict[str, Path], uv_cache: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capfd: pytest.CaptureFixture[str],
    ) -> None:
        """A dependency uv cannot resolve offline makes the run exit 1 with the errors block naming the file."""
        del uv_cache
        repo = tmp_path / 'repo'
        _write_hooks(repo, f'["{MISSING_DEPENDENCY}"]')
        cfg = write_config(repo, 'hooks.yaml', _config('broken'))
        monkeypatch.setenv('UV_OFFLINE', '1')
        capfd.readouterr()

        code = run_main([str(cfg), *SKIP, '--yes'])

        captured = capfd.readouterr()
        output = (captured.out + captured.err).replace('\r\n', '\n')
        assert code == 1, output
        stderr = captured.err.replace('\r\n', '\n')
        assert 'The following hook environments could not be prepared:' in stderr
        failed = (e2e_isolated_home['claude_dir'] / 'broken' / 'hooks' / PEP723_HOOK).as_posix()
        assert f'  - {failed}\n' in stderr, stderr
        assert f'retry by hand: uv sync --script "{failed}" --python 3.12' in stderr, stderr
        assert f'  - {Path(failed).with_name(PLAIN_HOOK).as_posix()}' not in stderr, stderr
        assert 'Checking that uv can provide Python 3.12...' in output, output
        assert NETWORK_NOTE in stderr, stderr
        assert REPAIR_LINE not in stderr, stderr

    def test_missing_interpreter_names_the_repair(
        self, e2e_isolated_home: dict[str, Path], uv_cache: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capfd: pytest.CaptureFixture[str],
    ) -> None:
        """A uv limited to an empty store of its own, without downloads, fails the sync and the probe alike.

        The interpreter store and the directory for interpreter links lie in
        the test's own directory, so nothing reaches the machine's uv
        installations or ~/.local/bin.
        """
        del uv_cache
        python_dir = tmp_path / 'uv-python'
        python_dir.mkdir()
        bin_dir = tmp_path / 'uv-python-bin'
        monkeypatch.setenv('UV_PYTHON_INSTALL_DIR', str(python_dir))
        monkeypatch.setenv('UV_PYTHON_BIN_DIR', str(bin_dir))
        monkeypatch.setenv('UV_PYTHON_PREFERENCE', 'only-managed')
        monkeypatch.setenv('UV_PYTHON_DOWNLOADS', 'never')
        for name in INTERPRETER_SOURCES:
            monkeypatch.delenv(name, raising=False)
        repo = tmp_path / 'repo'
        _write_hooks(repo, '[]')
        cfg = write_config(repo, 'hooks.yaml', _config('no-python'))
        capfd.readouterr()

        code = run_main([str(cfg), *SKIP, '--yes'])

        captured = capfd.readouterr()
        output = (captured.out + captured.err).replace('\r\n', '\n')
        assert code == 1, output
        stderr = captured.err.replace('\r\n', '\n')
        failed = (e2e_isolated_home['claude_dir'] / 'no-python' / 'hooks' / PEP723_HOOK).as_posix()
        assert f'  - {failed}\n' in stderr, stderr
        assert 'uv cannot provide Python 3.12 for the hooks (exit code 2)' in stderr, stderr
        assert REPAIR_LINE in stderr, stderr
        assert NETWORK_NOTE not in stderr, stderr
        assert list(python_dir.iterdir()) == []
        assert not bin_dir.exists() or list(bin_dir.iterdir()) == []
