"""Stand-ins for the Node.js the setup checks, the release documents it reads and the commands it runs.

Step 5 keeps an installed Node.js on the newest release of its LTS line:
plan_node_upgrade() runs the node the step checks and reads the Node.js
release index and schedule, and Step 5 runs winget, msiexec, brew, the macOS
installer or apt-get through ``_run_nodejs_command()`` and downloads an
official installer through ``_download_nodejs_installer()``. For the E2E
tests:

- the release documents come from ``tests/e2e/fixtures/nodejs`` and are read
  against RELEASE_DAY, so the decisions never change with the calendar;
  UNREACHABLE_VARIABLE (``index`` or ``schedule``) makes one unreachable;
- the machine's own Node.js stays out of every test: a node outside the
  directory CONFINEMENT_VARIABLE names (the pytest base temporary
  directory) counts as absent, so only a stub a test builds is checked;
- every command and download is recorded into the JSON-lines file
  RECORD_VARIABLE names instead of running; a recorded command succeeds
  and, when VERSION_FILE_VARIABLE names a stub node's version file, writes
  UPGRADED_VERSION_VARIABLE into it, so the stub then reports the upgraded
  release, while a command whose program FAILING_VARIABLE names exits 1.

The variables live in the environment, so a child run started by a test
(tests/e2e/fixtures/setup_child.py) behaves the same way. They belong to the
test harness, not to the toolbox interface, so they sit outside the
CLAUDE_CODE_TOOLBOX_ namespace.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import urllib.error
from collections.abc import Callable
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Any

from scripts.setup_environment import NodeInstallation

FIXTURE_DIR = Path(__file__).parent / 'fixtures' / 'nodejs'
# The day the fixture schedule is read against: Node.js 26 becomes LTS that
# day, 24 is in maintenance, 25 and 20 are past their end of life
RELEASE_DAY = date(2026, 10, 28)

RECORD_VARIABLE = 'CCT_E2E_NODE_COMMAND_RECORD'
CONFINEMENT_VARIABLE = 'CCT_E2E_NODE_ROOT'
FAILING_VARIABLE = 'CCT_E2E_NODE_COMMAND_FAIL'
VERSION_FILE_VARIABLE = 'CCT_E2E_NODE_VERSION_FILE'
UPGRADED_VERSION_VARIABLE = 'CCT_E2E_NODE_UPGRADED_VERSION'
UNREACHABLE_VARIABLE = 'CCT_E2E_NODE_RELEASES_UNREACHABLE'

ALL_VARIABLES = (
    RECORD_VARIABLE, CONFINEMENT_VARIABLE, FAILING_VARIABLE, VERSION_FILE_VARIABLE, UPGRADED_VERSION_VARIABLE,
    UNREACHABLE_VARIABLE,
)


def release_document(url: str) -> object:
    """Answer one release document from the fixtures, as nodejs.org and GitHub answer it.

    Args:
        url: The index or schedule URL the setup reads.

    Returns:
        The parsed fixture.

    Raises:
        urllib.error.URLError: The document is the one UNREACHABLE_VARIABLE
            names, or no fixture stands for the URL.
    """
    name = 'index' if url.endswith('/index.json') else 'schedule' if url.endswith('/schedule.json') else None
    if name is None or os.environ.get(UNREACHABLE_VARIABLE) == name:
        raise urllib.error.URLError('Temporary failure in name resolution')
    return json.loads((FIXTURE_DIR / f'{name}.json').read_text(encoding='utf-8'))


def _within(path: str, directory: str) -> bool:
    resolved_dir = os.path.normcase(os.path.realpath(directory))
    resolved = os.path.normcase(os.path.realpath(path))
    try:
        return os.path.commonpath([resolved, resolved_dir]) == resolved_dir
    except ValueError:
        return False


class NodeCommandRecorder:
    """Records every Node.js command and installer download of the setup instead of running it."""

    def __init__(self, path: Path) -> None:
        """Bind the recorder to its JSON-lines file.

        Args:
            path: The record file; created on the first call.
        """
        self.path = path

    def _append(self, record: dict[str, Any]) -> None:
        with self.path.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(record) + '\n')

    def run(self, command: list[str], *, sudo: bool = False) -> subprocess.CompletedProcess[str]:
        """Record one command and answer as a successful run of it, or as a failed one.

        Args:
            command: The command, without ``sudo``.
            sudo: Whether the setup runs it with sudo.

        Returns:
            Exit code 1 when FAILING_VARIABLE names the program, else exit
            code 0 after the stub node's version file receives the upgraded
            release.
        """
        self._append({'command': list(command), 'sudo': sudo})
        failing = {name.strip() for name in os.environ.get(FAILING_VARIABLE, '').split(',') if name.strip()}
        if Path(command[0]).name in failing:
            return subprocess.CompletedProcess(command, 1, '', f'{command[0]} failed')
        version_file = os.environ.get(VERSION_FILE_VARIABLE)
        upgraded = os.environ.get(UPGRADED_VERSION_VARIABLE)
        if version_file and upgraded:
            Path(version_file).write_text(f'v{upgraded}\n', encoding='utf-8')
        return subprocess.CompletedProcess(command, 0, '', '')

    def download(self, url: str) -> str:
        """Record one installer download and hand back an empty file in its place.

        Args:
            url: The installer URL.

        Returns:
            The path of the stand-in file, beside the record file.
        """
        self._append({'download': url})
        target = self.path.parent / f'downloaded-{url.rsplit("/", 1)[-1]}'
        target.write_bytes(b'')
        return str(target)

    def records(self) -> list[dict[str, Any]]:
        """Read every recorded command and download, in call order, children's included."""
        if not self.path.is_file():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding='utf-8').splitlines() if line.strip()]

    def commands(self) -> list[list[str]]:
        """The recorded commands, without the downloads."""
        return [record['command'] for record in self.records() if 'command' in record]


def replacements(module: ModuleType, recorder: NodeCommandRecorder) -> dict[str, object]:
    """The stand-ins of one setup module's Node.js seams.

    Args:
        module: A setup_environment module object.
        recorder: The recorder of the test or child run.

    Returns:
        The attribute names with their stand-ins.
    """
    locate: Callable[[], NodeInstallation | None] = module._locate_node

    def confined_locate() -> NodeInstallation | None:
        installation = locate()
        root = os.environ.get(CONFINEMENT_VARIABLE)
        if installation is None or not root or not _within(installation.real_path, root):
            return None
        return installation

    return {
        '_fetch_node_release_json': release_document,
        '_node_release_today': lambda: RELEASE_DAY,
        '_run_nodejs_command': recorder.run,
        '_download_nodejs_installer': recorder.download,
        '_locate_node': confined_locate,
    }


def write_node(directory: Path, version: str) -> tuple[Path, Path]:
    """Write a node executable that reports the release its version file holds.

    Args:
        directory: The directory of the executable.
        version: The release it reports at first (``X.Y.Z``).

    Returns:
        The executable and its version file.
    """
    directory.mkdir(parents=True, exist_ok=True)
    version_file = directory / 'node-version.txt'
    version_file.write_text(f'v{version}\n', encoding='utf-8')
    if sys.platform == 'win32':
        executable = directory / 'node.cmd'
        executable.write_text(f'@type "{version_file}"\r\n', encoding='utf-8')
        return executable, version_file
    executable = directory / 'node'
    executable.write_text(f"#!/bin/sh\ncat '{version_file}'\n", encoding='utf-8')
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return executable, version_file


def write_homebrew_node(prefix: Path, major: int, version: str) -> tuple[Path, Path]:
    """Lay out Homebrew's node@<major> keg with its release linked into the prefix's bin directory.

    Args:
        prefix: The Homebrew prefix.
        major: The formula's release line.
        version: The release the keg holds.

    Returns:
        The bin directory to put on PATH and the version file of the keg's node.
    """
    executable, version_file = write_node(prefix / 'Cellar' / f'node@{major}' / version / 'bin', version)
    bin_dir = prefix / 'bin'
    bin_dir.mkdir(parents=True, exist_ok=True)
    (bin_dir / 'node').symlink_to(executable)
    return bin_dir, version_file


def write_winget(directory: Path) -> Path:
    """Write a winget entry, so the setup finds winget; the recorder stands in for every run of it.

    Args:
        directory: The directory to put first on PATH.

    Returns:
        The directory.
    """
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'winget.cmd').write_text('@exit /b 0\r\n', encoding='utf-8')
    return directory
