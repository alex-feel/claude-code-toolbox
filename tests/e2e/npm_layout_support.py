"""Test-owned Node.js installations and npm global prefixes for the npm shadowing E2E tests.

A layout puts a Node.js installation with its bundled npm and an npm global
prefix into the test's temporary directory, in the platform's own shape
(EXPECTED_NPM_LAYOUT), and places their executables first on PATH. The
``node`` and ``npm`` entries are stand-ins run by the test interpreter that
answer what setup asks: ``node --version``, ``npm --version`` and ``npm config
get prefix``. Each npm stand-in answers for the copy the real entry would
run: the npm.cmd shim of Node.js on Windows runs the global-prefix copy
whenever its bin/npm-cli.js exists and the bundled copy otherwise, the
npm.cmd shim in the prefix runs the prefix copy, and a POSIX bin/npm runs the
package it belongs to. Every npm invocation is appended to a log, so a test
can prove which npm commands setup ran. FAKE_NPM_FAIL makes an invocation
exit 1 and FAKE_NPM_DELAY stalls it for the given seconds: every invocation,
or only the one whose space-joined arguments equal FAKE_NPM_ONLY_ARGS when
that is set. Nothing outside the temporary directory is read or changed.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path

from tests.e2e.expected import EXPECTED_NPM_LAYOUT

NODE_VERSION = 'v24.19.0'

FAKE_NPM = '''\
"""Stand-in for npm: answers npm --version and npm config get prefix for one copy."""
import json
import os
import sys
import time
from pathlib import Path

role, location, *args = sys.argv[1:]
with open(os.environ['FAKE_NPM_LOG'], 'a', encoding='utf-8') as log:
    log.write(json.dumps(args) + '\\n')
only_args = os.environ.get('FAKE_NPM_ONLY_ARGS')
if only_args is None or only_args == ' '.join(args):
    time.sleep(float(os.environ.get('FAKE_NPM_DELAY', '0')))
    if os.environ.get('FAKE_NPM_FAIL'):
        sys.exit(1)

configured = os.environ.get('NPM_CONFIG_PREFIX')
# Without a configured prefix, the builtin npmrc of the Windows Node.js
# installer points the global prefix at %APPDATA%\\npm
prefix = Path(configured) if configured else Path(os.environ.get('APPDATA', '')) / 'npm'
if role == 'windows-node-shim':
    prefix_copy = prefix / 'node_modules' / 'npm'
    bundled = Path(location) / 'node_modules' / 'npm'
    package = prefix_copy if (prefix_copy / 'bin' / 'npm-cli.js').is_file() else bundled
elif role == 'windows-prefix-shim':
    package = Path(location) / 'node_modules' / 'npm'
else:
    package = Path(location)

if args == ['--version']:
    print(json.loads((package / 'package.json').read_text(encoding='utf-8'))['version'])
elif args == ['config', 'get', 'prefix']:
    print(prefix)
else:
    sys.exit(1)
'''


@dataclass(frozen=True)
class NpmLayout:
    """A test-owned Node.js installation and npm global prefix.

    Attributes:
        node_root: The Node.js installation directory.
        npm_prefix: The npm global prefix.
        node_bin_dir: The directory holding node and the bundled npm's entry.
        bundled_dir: The bundled npm package directory.
        prefix_bin_dir: The directory holding the prefix copy's npm entry.
        prefix_dir: The package directory a prefix copy occupies.
        log: The file every npm invocation is appended to.
        stub: The npm stand-in script every npm entry runs.
    """

    node_root: Path
    npm_prefix: Path
    node_bin_dir: Path
    bundled_dir: Path
    prefix_bin_dir: Path
    prefix_dir: Path
    log: Path
    stub: Path

    def npm_calls(self) -> list[list[str]]:
        """The argument lists of every npm invocation so far, in order."""
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding='utf-8').splitlines()]

    def package_bytes(self) -> dict[str, bytes]:
        """The package.json bytes of each copy present, to prove a run changed neither."""
        return {
            str(package): (package / 'package.json').read_bytes()
            for package in (self.bundled_dir, self.prefix_dir)
            if (package / 'package.json').is_file()
        }


def _template(key: str, node_root: Path, npm_prefix: Path) -> Path:
    """Resolve one EXPECTED_NPM_LAYOUT template."""
    return Path(EXPECTED_NPM_LAYOUT[key].format(node_root=node_root, npm_prefix=npm_prefix))


def write_package(package_dir: Path, version: str) -> None:
    """Write an npm package directory: package.json with the version and bin/npm-cli.js."""
    (package_dir / 'bin').mkdir(parents=True, exist_ok=True)
    (package_dir / 'bin' / 'npm-cli.js').write_text("require('../lib/cli.js')(process)\n", encoding='utf-8')
    (package_dir / 'package.json').write_text(json.dumps({'name': 'npm', 'version': version}), encoding='utf-8')


def _write_entry(directory: Path, name: str, argv: list[str]) -> None:
    """Write an executable entry that runs argv followed by its own arguments."""
    directory.mkdir(parents=True, exist_ok=True)
    if sys.platform == 'win32':
        quoted = ' '.join(f'"{part}"' for part in argv)
        (directory / f'{name}.cmd').write_text(f'@echo off\r\n{quoted} %*\r\n', encoding='utf-8')
        return
    quoted = ' '.join(f"'{part}'" for part in argv)
    entry = directory / name
    entry.write_text(f'#!/bin/sh\nexec {quoted} "$@"\n', encoding='utf-8')
    entry.chmod(entry.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def write_npm_entry(directory: Path, package_dir: Path, stub: Path) -> None:
    """Write an npm entry that runs the npm package in package_dir.

    The entry stands for an npm outside both the Node.js installation and the
    npm global prefix, such as one a Node.js version manager puts first on
    PATH: it reports the version package_dir declares, and the global prefix
    npm would use.

    Args:
        directory: The directory to write the entry into.
        package_dir: The npm package directory the entry runs.
        stub: The npm stand-in script of a layout (NpmLayout.stub).
    """
    _write_entry(directory, 'npm', [sys.executable, str(stub), 'posix-bin', str(package_dir)])


def _write_node(directory: Path) -> None:
    """Write a node entry that reports NODE_VERSION."""
    directory.mkdir(parents=True, exist_ok=True)
    if sys.platform == 'win32':
        (directory / 'node.cmd').write_text(f'@echo {NODE_VERSION}\r\n', encoding='utf-8')
        return
    entry = directory / 'node'
    entry.write_text(f'#!/bin/sh\necho {NODE_VERSION}\n', encoding='utf-8')
    entry.chmod(entry.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def build_npm_layout(
    root: Path,
    npm_prefix: Path,
    *,
    bundled_version: str | None,
    prefix_version: str | None = None,
    bundled_npm_entry: bool = True,
) -> NpmLayout:
    """Build a Node.js installation and an npm global prefix in the platform's layout.

    Args:
        root: The directory to build the Node.js installation in.
        npm_prefix: The npm global prefix (on Windows, %APPDATA%\\npm of the
            isolated home unless the test configures another).
        bundled_version: The version the bundled npm declares, or None for a
            Node.js installation without npm.
        prefix_version: The version of an npm copy in the global prefix, or
            None for a prefix without one.
        bundled_npm_entry: Whether the Node.js installation has an npm entry
            (False leaves only node, so no npm resolves from it).

    Returns:
        The layout.
    """
    node_root = root / 'nodejs'
    layout = NpmLayout(
        node_root=node_root,
        npm_prefix=npm_prefix,
        node_bin_dir=_template('node_bin_dir', node_root, npm_prefix),
        bundled_dir=_template('bundled_npm', node_root, npm_prefix),
        prefix_bin_dir=_template('prefix_bin_dir', node_root, npm_prefix),
        prefix_dir=_template('prefix_npm', node_root, npm_prefix),
        log=root / 'npm-calls.log',
        stub=root / 'fake_npm.py',
    )
    stub = layout.stub
    stub.write_text(FAKE_NPM, encoding='utf-8')
    _write_node(layout.node_bin_dir)
    if bundled_version is not None:
        write_package(layout.bundled_dir, bundled_version)
    npm_prefix.mkdir(parents=True, exist_ok=True)
    windows = sys.platform == 'win32'
    if bundled_npm_entry:
        bundled_argv = (
            [sys.executable, str(stub), 'windows-node-shim', str(node_root)] if windows
            else [sys.executable, str(stub), 'posix-bin', str(layout.bundled_dir)]
        )
        _write_entry(layout.node_bin_dir, 'npm', bundled_argv)
    if prefix_version is not None:
        write_package(layout.prefix_dir, prefix_version)
        prefix_argv = (
            [sys.executable, str(stub), 'windows-prefix-shim', str(npm_prefix)] if windows
            else [sys.executable, str(stub), 'posix-bin', str(layout.prefix_dir)]
        )
        _write_entry(layout.prefix_bin_dir, 'npm', prefix_argv)
    return layout


def path_with(*directories: Path, keep_npm: bool = True, keep_node: bool = True) -> str:
    """Build a PATH that puts the directories first, then the current PATH.

    Args:
        *directories: The directories to put first, in order.
        keep_npm: Whether entries of the current PATH that hold an npm stay;
            False drops them so that npm resolves only from the directories.
        keep_node: Whether entries of the current PATH that hold a node stay;
            False drops them so that node resolves only from the directories.

    Returns:
        The PATH value.
    """
    dropped = [name for name, keep in (('npm', keep_npm), ('node', keep_node)) if not keep]
    current = [
        entry
        for entry in os.environ.get('PATH', '').split(os.pathsep)
        if entry and not any(_holds(Path(entry), name) for name in dropped)
    ]
    return os.pathsep.join([*(str(directory) for directory in directories), *current])


def _holds(directory: Path, name: str) -> bool:
    """Report whether a PATH entry holds an executable of the given name."""
    if sys.platform == 'win32':
        candidates = (f'{name}.cmd', f'{name}.exe', f'{name}.bat', f'{name}.ps1', name)
    else:
        candidates = (name,)
    return any((directory / candidate).exists() for candidate in candidates)
