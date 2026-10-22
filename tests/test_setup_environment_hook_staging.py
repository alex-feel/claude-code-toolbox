"""Tests for the staged, all-or-nothing installation of hook files and helpers.

download_hook_files() downloads every hooks.files and hooks.helpers entry into
a staging directory inside the hooks directory and moves the staged files into
place only after every download succeeded, helpers first, so a hook running
during the installation never loads a new script beside an old or missing
helper. Every test drives the real download path, sequentially and in
parallel.
"""

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from scripts import setup_environment
from scripts.setup_environment import HOOK_STAGING_PREFIX
from scripts.setup_environment import _write_file_atomic
from scripts.setup_environment import download_hook_files
from tests.e2e.shells import find_powershell

SCRIPT_A = 'hook_a.py'
SCRIPT_B = 'hook_b.py'
HELPER = 'hook_shared.py'
OLD_TIMESTAMP = 1_000_000_000
USERS_SID = 'S-1-5-32-545'
USERS_SDDL_ALIAS = 'BU'

type StrPath = str | os.PathLike[str]


@pytest.fixture(params=['sequential', 'parallel'], autouse=True)
def download_mode(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    """Run every test with sequential and with parallel downloads."""
    if request.param == 'sequential':
        monkeypatch.setenv('CLAUDE_CODE_TOOLBOX_SEQUENTIAL_MODE', '1')
    else:
        monkeypatch.delenv('CLAUDE_CODE_TOOLBOX_SEQUENTIAL_MODE', raising=False)
    return str(request.param)


def _hooks(prefix: str = 'hooks/') -> dict[str, Any]:
    """Return a hooks section with two scripts and one helper."""
    return {
        'files': [f'{prefix}{SCRIPT_A}', f'{prefix}{SCRIPT_B}'],
        'helpers': [f'{prefix}{HELPER}'],
    }


def _local_source(tmp_path: Path, contents: dict[str, bytes]) -> str:
    """Write a local configuration with the given hook sources and return its path."""
    source_dir = tmp_path / 'src'
    (source_dir / 'hooks').mkdir(parents=True)
    config_file = source_dir / 'config.yaml'
    config_file.write_text('name: hooks\n', encoding='utf-8')
    for name, content in contents.items():
        (source_dir / 'hooks' / name).write_bytes(content)
    return str(config_file)


def _installed_hooks_dir(tmp_path: Path, contents: dict[str, bytes]) -> Path:
    """Create a hooks directory holding the given installed files."""
    hooks_dir = tmp_path / 'profile' / 'hooks'
    hooks_dir.mkdir(parents=True)
    for name, content in contents.items():
        (hooks_dir / name).write_bytes(content)
    return hooks_dir


def _install(hooks: dict[str, Any], config_source: str, hooks_dir: Path) -> bool:
    """Run download_hook_files() into the given hooks directory."""
    return download_hook_files(hooks, hooks_dir.parent, config_source, hooks_base_dir=hooks_dir)


def _record_moves_into(
    monkeypatch: pytest.MonkeyPatch,
    hooks_dir: Path,
    fail_on: int | None = None,
) -> list[str]:
    """Record the names os.replace() moves into hooks_dir, optionally failing one move.

    Args:
        monkeypatch: The test's monkeypatch fixture.
        hooks_dir: The directory whose incoming moves are recorded.
        fail_on: 1-based number of the move into hooks_dir that raises
            PermissionError instead of moving.

    Returns:
        The list the recorder appends each moved name to, in move order.
    """
    moved: list[str] = []
    real_replace: Callable[[StrPath, StrPath], None] = os.replace

    def recording_replace(src: StrPath, dst: StrPath) -> None:
        target = Path(dst)
        if target.parent == hooks_dir:
            if fail_on is not None and len(moved) + 1 == fail_on:
                raise PermissionError(f'simulated lock on {target.name}')
            moved.append(target.name)
        real_replace(src, dst)

    monkeypatch.setattr(os, 'replace', recording_replace)
    return moved


def _dacl(path: Path) -> str:
    """Return the DACL part of a file's security descriptor in SDDL form.

    Args:
        path: The file to read.

    Returns:
        The SDDL text from its 'D:' component on, without owner and group.
    """
    powershell = find_powershell()
    assert powershell is not None, 'PowerShell is required to read a Windows security descriptor'
    literal = str(path).replace("'", "''")
    result = subprocess.run(
        [powershell, '-NoProfile', '-Command', f"(Get-Acl -LiteralPath '{literal}').Sddl"],
        capture_output=True, text=True, check=True,
    )
    sddl = result.stdout.strip()
    return sddl[sddl.index('D:'):]


def _assert_no_staging_residue(hooks_dir: Path) -> None:
    """Assert that the hooks directory holds no staging directory and no temp file."""
    names = [entry.name for entry in hooks_dir.iterdir()]
    assert not [name for name in names if name.startswith(HOOK_STAGING_PREFIX)], names
    assert not [name for name in names if name.endswith('.tmp')], names


class TestHookFileStaging:
    """download_hook_files() installs hooks.files and hooks.helpers as one set."""

    def test_helpers_are_moved_into_place_before_scripts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Every helper reaches the hooks directory before any script does."""
        config_source = _local_source(
            tmp_path, {SCRIPT_A: b'new a\n', SCRIPT_B: b'new b\n', HELPER: b'new helper\n'},
        )
        hooks_dir = _installed_hooks_dir(tmp_path, {})
        moved = _record_moves_into(monkeypatch, hooks_dir)

        assert _install(_hooks(), config_source, hooks_dir) is True

        assert sorted(moved) == sorted([SCRIPT_A, SCRIPT_B, HELPER])
        assert moved.index(HELPER) < min(moved.index(SCRIPT_A), moved.index(SCRIPT_B)), moved

    def test_failed_download_leaves_installed_files_unchanged(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """One missing source leaves every installed file as it was and no residue."""
        installed = {SCRIPT_A: b'old a\n', SCRIPT_B: b'old b\n', HELPER: b'old helper\n'}
        config_source = _local_source(tmp_path, {SCRIPT_A: b'new a\n', HELPER: b'new helper\n'})
        hooks_dir = _installed_hooks_dir(tmp_path, installed)

        assert _install(_hooks(), config_source, hooks_dir) is False

        assert {name: (hooks_dir / name).read_bytes() for name in installed} == installed
        _assert_no_staging_residue(hooks_dir)
        assert sorted(entry.name for entry in hooks_dir.iterdir()) == sorted(installed)
        output = capsys.readouterr()
        assert SCRIPT_B in output.err
        assert 'installed hook files were left unchanged' in output.err

    def test_unchanged_file_keeps_its_timestamp(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A file equal to the installed copy is not replaced and keeps its mtime."""
        config_source = _local_source(
            tmp_path, {SCRIPT_A: b'same a\n', SCRIPT_B: b'new b\n', HELPER: b'new helper\n'},
        )
        hooks_dir = _installed_hooks_dir(tmp_path, {SCRIPT_A: b'same a\n', SCRIPT_B: b'old b\n'})
        os.utime(hooks_dir / SCRIPT_A, (OLD_TIMESTAMP, OLD_TIMESTAMP))

        assert _install(_hooks(), config_source, hooks_dir) is True

        assert (hooks_dir / SCRIPT_A).stat().st_mtime == OLD_TIMESTAMP
        assert (hooks_dir / SCRIPT_B).read_bytes() == b'new b\n'
        assert (hooks_dir / HELPER).read_bytes() == b'new helper\n'
        assert f'Unchanged: {SCRIPT_A}' in capsys.readouterr().out

    def test_successful_install_leaves_only_the_hook_files(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A successful run removes its staging directory and reports the moved files."""
        contents = {SCRIPT_A: b'new a\n', SCRIPT_B: b'new b\n', HELPER: b'new helper\n'}
        config_source = _local_source(tmp_path, contents)
        hooks_dir = _installed_hooks_dir(tmp_path, {})

        assert _install(_hooks(), config_source, hooks_dir) is True

        assert {entry.name: entry.read_bytes() for entry in hooks_dir.iterdir()} == contents
        assert '3 hook files moved into place' in capsys.readouterr().out

    def test_remote_sources_compare_against_the_installed_copy(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Remote hook files install through staging and skip an unchanged installed copy."""
        base = 'https://example.com/repo/hooks/'
        remote = {
            f'{base}{SCRIPT_A}': 'same a\n',
            f'{base}{SCRIPT_B}': 'new b\n',
            f'{base}{HELPER}': 'new helper\n',
        }

        def fake_fetch(url: str, **_kwargs: object) -> str:
            return remote[url]

        monkeypatch.setattr(setup_environment, 'fetch_url_with_auth', fake_fetch)
        hooks_dir = _installed_hooks_dir(tmp_path, {SCRIPT_A: b'same a\n'})
        os.utime(hooks_dir / SCRIPT_A, (OLD_TIMESTAMP, OLD_TIMESTAMP))

        assert _install(_hooks(base), 'https://example.com/repo/config.yaml', hooks_dir) is True

        assert (hooks_dir / SCRIPT_A).stat().st_mtime == OLD_TIMESTAMP
        assert (hooks_dir / SCRIPT_B).read_bytes() == b'new b\n'
        assert (hooks_dir / HELPER).read_bytes() == b'new helper\n'
        _assert_no_staging_residue(hooks_dir)
        output = capsys.readouterr().out
        assert f'Unchanged: {SCRIPT_A}' in output
        assert '2 hook files moved into place' in output

    def test_unchanged_set_moves_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A set equal to the installed files moves nothing and says so."""
        contents = {SCRIPT_A: b'a\n', SCRIPT_B: b'b\n', HELPER: b'helper\n'}
        config_source = _local_source(tmp_path, contents)
        hooks_dir = _installed_hooks_dir(tmp_path, contents)
        moved = _record_moves_into(monkeypatch, hooks_dir)

        assert _install(_hooks(), config_source, hooks_dir) is True

        assert moved == []
        _assert_no_staging_residue(hooks_dir)
        assert 'Hook files unchanged; nothing moved into place' in capsys.readouterr().out

    def test_promotion_failure_names_the_file_and_the_moved_count(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A move that fails stops the promotion and reports the file and the moved count."""
        config_source = _local_source(
            tmp_path, {SCRIPT_A: b'new a\n', SCRIPT_B: b'new b\n', HELPER: b'new helper\n'},
        )
        hooks_dir = _installed_hooks_dir(tmp_path, {})
        moved = _record_moves_into(monkeypatch, hooks_dir, fail_on=2)

        assert _install(_hooks(), config_source, hooks_dir) is False

        assert moved == [HELPER]
        _assert_no_staging_residue(hooks_dir)
        output = capsys.readouterr().err
        assert f'Could not move hook file {SCRIPT_A} into place' in output
        assert 'simulated lock' in output
        assert '1 of 3 staged hook files' in output

    @pytest.mark.skipif(sys.platform == 'win32', reason='POSIX file mode semantics')
    def test_replaced_remote_file_keeps_the_installed_mode(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A downloaded file replacing an installed one takes the installed file's permission bits."""
        base = 'https://example.com/repo/hooks/'

        def fake_fetch(url: str, **_kwargs: object) -> str:
            return f'new {url}\n'

        monkeypatch.setattr(setup_environment, 'fetch_url_with_auth', fake_fetch)
        hooks_dir = _installed_hooks_dir(tmp_path, {SCRIPT_A: b'old a\n'})
        (hooks_dir / SCRIPT_A).chmod(0o755)

        assert _install(_hooks(base), 'https://example.com/repo/config.yaml', hooks_dir) is True

        assert (hooks_dir / SCRIPT_A).read_text(encoding='utf-8') == f'new {base}{SCRIPT_A}\n'
        assert (hooks_dir / SCRIPT_A).stat().st_mode & 0o777 == 0o755
        assert (hooks_dir / HELPER).stat().st_mode & 0o777 == 0o644

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows access control lists')
    def test_promoted_file_inherits_the_hooks_directory_permissions(self, tmp_path: Path) -> None:
        """A moved-in hook file carries the same inherited DACL as a file written in place.

        The hooks directory grants the built-in Users group an inheritable
        ACE, as a user profile grants its own account, so a staging directory
        that does not inherit the hooks directory's DACL hands the moved-in
        file an ACL without it.
        """
        config_source = _local_source(
            tmp_path, {SCRIPT_A: b'new a\n', SCRIPT_B: b'new b\n', HELPER: b'new helper\n'},
        )
        hooks_dir = _installed_hooks_dir(tmp_path, {})
        subprocess.run(
            ['icacls', str(hooks_dir), '/grant', f'*{USERS_SID}:(OI)(CI)(RX)'],
            capture_output=True, text=True, check=True,
        )
        control = hooks_dir / 'control.py'
        _write_file_atomic(control, lambda target: target.write_bytes(b'control\n'))

        assert _install(_hooks(), config_source, hooks_dir) is True

        promoted_dacl = _dacl(hooks_dir / SCRIPT_A)
        assert 'D:P' not in promoted_dacl
        assert f';;;{USERS_SDDL_ALIAS})' in promoted_dacl
        assert promoted_dacl == _dacl(control)
