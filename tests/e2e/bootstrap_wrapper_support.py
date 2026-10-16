"""Helpers for E2E tests that run the platform bootstrap wrappers.

Each platform has two wrappers: ``setup-environment``, which runs the
environment setup, and ``install-claude``, which runs the Claude Code
installer. The bash wrappers run for real on their own platform with
stand-ins for curl, which copies the repository's scripts instead of
downloading them, and for uv, whose behavior each test module supplies. The
Linux wrappers refuse to run anywhere but Linux and the macOS wrappers
anywhere but macOS, so each platform is parametrized with a skip for the
other platforms.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / 'scripts'
WINDOWS_SETUP_WRAPPER = SCRIPTS_DIR / 'windows' / 'setup-environment.ps1'
WINDOWS_INSTALL_WRAPPER = SCRIPTS_DIR / 'windows' / 'install-claude-windows.ps1'

FAKE_CURL = '''\
#!/usr/bin/env bash
# Stand-in for curl: copy the requested repository script to the -o path
out=""
url=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        -o) out="$2"; shift 2 ;;
        -*) shift ;;
        *) url="$1"; shift ;;
    esac
done
cp "$E2E_SCRIPTS_DIR/$(basename "$url")" "$out"
'''

UNIX_WRAPPERS = [
    pytest.param(
        'linux',
        marks=pytest.mark.skipif(not sys.platform.startswith('linux'), reason='the Linux wrappers run only on Linux'),
    ),
    pytest.param(
        'macos',
        marks=pytest.mark.skipif(sys.platform != 'darwin', reason='the macOS wrappers run only on macOS'),
    ),
]


def unix_setup_wrapper(platform_dir: str) -> Path:
    """Return the setup bootstrap wrapper of one Unix platform."""
    return SCRIPTS_DIR / platform_dir / 'setup-environment.sh'


def unix_install_wrapper(platform_dir: str) -> Path:
    """Return the installer bootstrap wrapper of one Unix platform."""
    return SCRIPTS_DIR / platform_dir / f'install-claude-{platform_dir}.sh'


def run_unix_wrapper(
    tmp_path: Path,
    wrapper: Path,
    args: list[str],
    extra_env: dict[str, str],
    *,
    uv_stand_in: str,
) -> subprocess.CompletedProcess[str]:
    """Run a bash bootstrap wrapper with stand-ins for curl and uv in an isolated home.

    Args:
        tmp_path: The test's temporary directory, holding the stand-ins and the home.
        wrapper: The bash wrapper to run.
        args: The arguments the wrapper receives.
        extra_env: Environment variables set for the wrapper.
        uv_stand_in: The bash script that stands in for uv.

    Returns:
        The finished wrapper process with its captured output.
    """
    fake_bin = tmp_path / 'fake-bin'
    fake_bin.mkdir()
    for name, body in (('curl', FAKE_CURL), ('uv', uv_stand_in)):
        stand_in = fake_bin / name
        stand_in.write_text(body, encoding='utf-8', newline='\n')
        stand_in.chmod(0o755)
    home = tmp_path / 'home'
    home.mkdir(exist_ok=True)
    env = {
        'PATH': f'{fake_bin}{os.pathsep}{os.environ["PATH"]}',
        'HOME': str(home),
        'E2E_SCRIPTS_DIR': str(SCRIPTS_DIR),
        'E2E_PYTHON': sys.executable,
        'CLAUDE_CODE_TOOLBOX_ALLOW_ROOT': '1',
        **extra_env,
    }
    bash = shutil.which('bash')
    assert bash is not None
    return subprocess.run(
        [bash, str(wrapper), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
