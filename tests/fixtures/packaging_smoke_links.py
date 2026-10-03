"""Package-smoke probe: a source run refreshes a dependent profile through the packaged entry point.

Run inside the uvx environment built from the wheel::

    uvx --from dist/<wheel> python tests/fixtures/packaging_smoke_links.py

Inside a temporary home the probe installs the profile smoke-1 from a
minimal configuration, installs smoke-2 linking every entry from smoke-1,
and re-runs smoke-1 the way the console script does: through
cc_toolbox.cli with a sys.argv[0] that carries no .py suffix. Step 23 of
that run starts the refresh of smoke-2 as ``python -m cc_toolbox.cli setup
--profile smoke-2 --yes --skip-install --no-admin``; the probe records the
argv the run hands to subprocess.run, lets the real child run, and fails
unless the argv has that shape, the child exits 0, smoke-2's links still
point into smoke-1, and smoke-2's manifest was rewritten.

The writers that reach outside the home -- the Windows registry (OS
environment variables, the WM_SETTINGCHANGE broadcast, the user PATH
cleanup and extension) and Fish universal variables -- are replaced with
no-ops in this process and, through a sitecustomize module on PYTHONPATH,
in the child, so the probe never changes the machine it runs on.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

from cc_toolbox import cli
from cc_toolbox import setup_environment

NEUTRALIZE = '''\
"""Replace the machine-wide writers of cc_toolbox.setup_environment with no-ops."""
import shutil

from cc_toolbox import setup_environment

_real_which = shutil.which


def _which_without_fish(cmd, *args, **kwargs):
    return None if cmd == 'fish' else _real_which(cmd, *args, **kwargs)


setup_environment.set_os_env_variable_windows = lambda *_args, **_kwargs: True
setup_environment._broadcast_wm_settingchange = lambda *_args, **_kwargs: None
setup_environment.add_directory_to_windows_path = lambda directory: (True, f'[neutralized] {directory}')
setup_environment.cleanup_temp_paths_from_registry = lambda: (0, [])
setup_environment.refresh_path_from_registry = lambda: None
shutil.which = _which_without_fish
'''

CONFIG = 'name: Packaging Smoke Links\n'
RUN_FLAGS = ['--yes', '--skip-install', '--no-admin']


def _run_setup(argv: list[str]) -> int:
    """Run ``cc-toolbox setup`` in this process as the console script does and return its exit code."""
    os.environ.pop('CLAUDE_CONFIG_DIR', None)
    with patch.object(sys, 'argv', ['cc-toolbox', 'setup', *argv]):
        try:
            cli.main()
        except SystemExit as exc:
            return exc.code if isinstance(exc.code, int) else 1
    return 0


def _neutralize_in_process(module_path: Path) -> None:
    """Apply the child's sitecustomize module to this interpreter."""
    spec = importlib.util.spec_from_file_location('cct_smoke_neutralize', module_path)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(importlib.util.module_from_spec(spec))


def _fail(message: str) -> int:
    print(f'FAIL: {message}')
    return 1


def main() -> int:
    """Install a source and a dependent, refresh the source, and check the dependent's refresh."""
    home = Path(tempfile.mkdtemp(prefix='cct-smoke-links-'))
    site_dir = home / 'site'
    site_dir.mkdir()
    (site_dir / 'sitecustomize.py').write_text(NEUTRALIZE, encoding='utf-8')
    config = home / 'smoke.yaml'
    config.write_text(CONFIG, encoding='utf-8')
    os.environ.update({'HOME': str(home), 'USERPROFILE': str(home), 'PYTHONPATH': str(site_dir)})
    _neutralize_in_process(site_dir / 'sitecustomize.py')

    if _run_setup([str(config), '--command-names', 'smoke-1', *RUN_FLAGS]) != 0:
        return _fail('installing smoke-1 did not succeed')
    if _run_setup([str(config), '--command-names', 'smoke-2', '--link-dirs', 'all', '--link-from', 'smoke-1', *RUN_FLAGS]):
        return _fail('installing smoke-2 linked from smoke-1 did not succeed')
    source_dir = home / '.claude' / 'smoke-1'
    dependent_dir = home / '.claude' / 'smoke-2'
    manifest_path = dependent_dir / 'manifest.json'
    installed_before = json.loads(manifest_path.read_text(encoding='utf-8'))['installed_at']

    recorded: list[list[str]] = []
    real_run = subprocess.run

    def run_recorded(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        recorded.append(list(argv))
        return real_run(argv, **kwargs)

    with patch.object(subprocess, 'run', run_recorded):
        code = _run_setup(['--profile', 'smoke-1', *RUN_FLAGS])

    launches = [argv for argv in recorded if '--profile' in argv]
    print(f'Step 23 launches: {launches!r}')
    expected = [sys.executable, '-m', 'cc_toolbox.cli', 'setup', '--profile', 'smoke-2', *RUN_FLAGS]
    if launches != [expected]:
        return _fail(f'expected exactly one launch {expected!r}')
    if code != 0:
        return _fail(f'the source run exited {code}')
    for entry in setup_environment.LINKABLE_PROFILE_DIRS:
        link = dependent_dir / entry
        if not setup_environment._is_directory_link(link) or not setup_environment._link_points_to(link, source_dir / entry):
            return _fail(f'{link} no longer links into smoke-1')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest['installed_at'] == installed_before:
        return _fail('the dependent manifest was not rewritten by the refresh')
    if manifest['link'] != {
        'dirs': list(setup_environment.LINKABLE_PROFILE_DIRS), 'source': 'smoke-1',
        'origins': {'dirs': 'cli', 'source': 'cli'},
    }:
        return _fail(f'unexpected link record {manifest["link"]!r}')
    shutil.rmtree(home, ignore_errors=True)
    print('OK: the source run refreshed its dependent through the packaged entry point')
    return 0


if __name__ == '__main__':
    sys.exit(main())
