"""Tests for refusing command names that another profile or a foreign file holds.

A run registers its command names as wrappers in ~/.local/bin. Before
anything is written, setup refuses a name that another profile's manifest
lists, and a name that ~/.local/bin already holds as a file the toolbox did
not create. A name the same profile owns, and a toolbox wrapper no manifest
lists any more, stay usable.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import setup_environment

# conftest replaces the check with a no-op for main()-flow unit tests; these
# tests exercise the real function, captured before that fixture runs
command_name_conflicts = setup_environment.command_name_conflicts
is_toolbox_wrapper = setup_environment.is_toolbox_wrapper

unix_only = pytest.mark.skipif(sys.platform == 'win32', reason='symlink wrappers are the Unix layout')


def _write_manifest(home: Path, directory: str, name: str | None, command_names: list[str]) -> Path:
    """Write a profile manifest the way write_manifest() records names."""
    profile_dir = home / '.claude' / directory
    profile_dir.mkdir(parents=True, exist_ok=True)
    manifest = profile_dir / 'manifest.json'
    manifest.write_text(json.dumps({'name': name, 'command_names': command_names}), encoding='utf-8')
    return manifest


def _register(home: Path, system: str, primary: str, aliases: list[str] | None = None) -> Path:
    """Register wrappers with the real register_global_command() for one platform layout."""
    profile_dir = home / '.claude' / primary
    profile_dir.mkdir(parents=True, exist_ok=True)
    launch = profile_dir / 'launch.sh'
    launch.write_text('#!/bin/bash\n', encoding='utf-8')
    launcher = profile_dir / 'start.ps1' if system == 'Windows' else launch
    with (
        patch('platform.system', return_value=system),
        patch.object(setup_environment, 'get_real_user_home', return_value=home),
        patch.object(setup_environment, 'add_directory_to_windows_path', return_value=(True, 'ok')),
    ):
        assert setup_environment.register_global_command(launcher, primary, aliases, launch)
    return home / '.local' / 'bin'


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """An empty home directory with ~/.claude and ~/.local/bin."""
    (tmp_path / '.claude').mkdir()
    (tmp_path / '.local' / 'bin').mkdir(parents=True)
    return tmp_path


class TestToolboxWrapperRecognition:
    """The wrappers register_global_command() writes are recognized as toolbox files."""

    @pytest.mark.parametrize('system', ['Windows', pytest.param('Linux', marks=unix_only)])
    def test_wrappers_of_primary_and_alias_are_recognized(self, home: Path, system: str) -> None:
        """Every entry written for the primary name and an alias counts as a toolbox wrapper."""
        local_bin = _register(home, system, 'tool-main', ['tool-alias'])

        entries = sorted(local_bin.iterdir())
        assert entries
        for entry in entries:
            name = entry.name.split('.')[0]
            assert is_toolbox_wrapper(entry, name), entry

    def test_windows_wrapper_of_another_name_is_not_recognized_for_this_name(self, home: Path) -> None:
        """The marker must name exactly this command; a longer name does not match."""
        local_bin = _register(home, 'Windows', 'abc')
        (local_bin / 'abc.cmd').rename(local_bin / 'a.cmd')
        (local_bin / 'abc.ps1').rename(local_bin / 'a.ps1')
        (local_bin / 'abc').rename(local_bin / 'a')

        for entry in ('a.cmd', 'a.ps1', 'a'):
            assert not is_toolbox_wrapper(local_bin / entry, 'a')

    @pytest.mark.parametrize(
        ('file_name', 'content'),
        [
            ('tool', '#!/bin/sh\necho tool\n'),
            ('tool.cmd', '@echo off\nREM user script\n'),
            ('tool.ps1', 'Write-Host user\n'),
        ],
    )
    def test_foreign_scripts_are_not_recognized(self, home: Path, file_name: str, content: str) -> None:
        """A script without the toolbox marker is a foreign file."""
        path = home / '.local' / 'bin' / file_name
        path.write_text(content, encoding='utf-8')
        assert not is_toolbox_wrapper(path, 'tool')

    def test_binary_file_is_not_recognized(self, home: Path) -> None:
        """An executable such as claude.exe is never a toolbox wrapper."""
        path = home / '.local' / 'bin' / 'tool.exe'
        path.write_bytes(b'MZ\x90\x00' + bytes(range(256)) * 8)
        assert not is_toolbox_wrapper(path, 'tool')

    @unix_only
    def test_symlink_to_another_target_is_not_recognized(self, home: Path) -> None:
        """A link to a binary, like the native Claude Code link, is a foreign file."""
        target = home / '.local' / 'share' / 'tool' / 'versions' / '1.0.0'
        target.parent.mkdir(parents=True)
        target.write_text('binary', encoding='utf-8')
        link = home / '.local' / 'bin' / 'tool'
        link.symlink_to(target)
        assert not is_toolbox_wrapper(link, 'tool')

    @unix_only
    def test_dangling_symlink_to_a_profile_launcher_is_recognized(self, home: Path) -> None:
        """A wrapper whose profile was deleted is still a file the toolbox created."""
        link = home / '.local' / 'bin' / 'gone'
        link.symlink_to(home / '.claude' / 'gone' / 'launch.sh')
        assert is_toolbox_wrapper(link, 'gone')


class TestOwnershipByManifest:
    """A name another profile's manifest lists is refused."""

    def test_alias_of_another_profile_is_refused(self, home: Path) -> None:
        """The message names the owning profile, its manifest, and the remedy."""
        manifest = _write_manifest(home, 'claude-personal', 'claude-personal', ['claude-personal', 'claude-p'])

        errors = command_name_conflicts(['claude-p'], home)

        assert len(errors) == 1
        assert 'Command name "claude-p" belongs to the profile "claude-personal"' in errors[0]
        assert str(manifest) in errors[0]
        assert 'leaves it out' in errors[0]

    def test_primary_name_of_another_profile_is_refused_as_an_alias(self, home: Path) -> None:
        """Another profile's primary name cannot become an alias of this run."""
        _write_manifest(home, 'claude-personal', 'claude-personal', ['claude-personal'])

        errors = command_name_conflicts(['p2', 'claude-personal'], home)

        assert len(errors) == 1
        assert 'is the primary name of the profile "claude-personal"' in errors[0]

    def test_names_of_the_same_profile_are_accepted(self, home: Path) -> None:
        """A re-run of a profile may keep or drop its own names."""
        _write_manifest(home, 'claude-personal', 'claude-personal', ['claude-personal', 'claude-p', 'claude-sub'])

        assert command_name_conflicts(['claude-personal', 'claude-p'], home) == []
        assert command_name_conflicts(['claude-personal', 'claude-sub', 'claude-new'], home) == []

    def test_names_are_compared_without_regard_to_case(self, home: Path) -> None:
        """Case-insensitive file systems would map Claude-P onto claude-p's wrappers."""
        _write_manifest(home, 'claude-personal', 'claude-personal', ['claude-personal', 'claude-p'])

        errors = command_name_conflicts(['Claude-P'], home)

        assert len(errors) == 1
        assert 'belongs to the profile "claude-personal"' in errors[0]

    def test_unreadable_manifest_still_owns_its_directory_name(self, home: Path) -> None:
        """A manifest that cannot be parsed leaves its profile's primary name taken."""
        profile_dir = home / '.claude' / 'broken'
        profile_dir.mkdir()
        (profile_dir / 'manifest.json').write_text('{not json', encoding='utf-8')

        errors = command_name_conflicts(['p2', 'broken'], home)

        assert len(errors) == 1
        assert 'Command name "broken" names the profile directory' in errors[0]
        assert 'could not be read' in errors[0]

    def test_unreadable_manifest_of_the_same_profile_does_not_block_its_re_run(self, home: Path) -> None:
        """The run's own directory is never another profile."""
        profile_dir = home / '.claude' / 'mine'
        profile_dir.mkdir()
        (profile_dir / 'manifest.json').write_text('[]', encoding='utf-8')

        assert command_name_conflicts(['mine'], home) == []

    def test_base_manifest_owns_no_names(self, home: Path) -> None:
        """The base profile registers no commands."""
        (home / '.claude' / 'manifest.json').write_text(
            json.dumps({'name': None, 'command_names': []}), encoding='utf-8',
        )
        assert command_name_conflicts(['anything'], home) == []

    def test_directory_without_manifest_owns_nothing(self, home: Path) -> None:
        """Only manifests record names; other directories of ~/.claude are not profiles."""
        (home / '.claude' / 'plugins').mkdir()
        assert command_name_conflicts(['plugins'], home) == []


class TestOwnershipByForeignFile:
    """A name ~/.local/bin holds as a file the toolbox did not create is refused."""

    def test_foreign_script_is_refused_with_the_path_and_remedy(self, home: Path) -> None:
        """The message names the file and how to free the name."""
        local_bin = home / '.local' / 'bin'
        foreign = local_bin / ('tool.cmd' if sys.platform == 'win32' else 'tool')
        foreign.write_text('@echo off\n' if sys.platform == 'win32' else '#!/bin/sh\n', encoding='utf-8')

        errors = command_name_conflicts(['tool'], home)

        assert len(errors) == 1
        assert f'Command name "tool" is taken by {foreign}, which the toolbox did not create' in errors[0]
        assert str(local_bin) in errors[0]

    def test_windows_executable_with_the_name_is_refused(self, home: Path) -> None:
        """On Windows a name.exe answers to the name in every shell, as claude.exe does."""
        (home / '.local' / 'bin' / 'claude.exe').write_bytes(b'MZ')

        with patch('platform.system', return_value='Windows'):
            errors = command_name_conflicts(['claude'], home)

        assert len(errors) == 1
        assert 'claude.exe' in errors[0]

    def test_executable_extensions_are_not_checked_off_windows(self, home: Path) -> None:
        """Unix shells resolve the bare name only."""
        (home / '.local' / 'bin' / 'tool.exe').write_bytes(b'MZ')

        with patch('platform.system', return_value='Linux'):
            assert command_name_conflicts(['tool'], home) == []

    def test_toolbox_wrapper_no_manifest_lists_is_usable(self, home: Path) -> None:
        """A wrapper left behind by a dropped alias belongs to nobody."""
        system = 'Windows' if sys.platform == 'win32' else 'Linux'
        _register(home, system, 'old-main', ['old-alias'])
        _write_manifest(home, 'old-main', 'old-main', ['old-main'])

        assert command_name_conflicts(['new-main', 'old-alias'], home) == []

    def test_absent_local_bin_holds_nothing(self, tmp_path: Path) -> None:
        """A machine without ~/.local/bin has no file to collide with."""
        assert command_name_conflicts(['tool'], tmp_path) == []

    def test_every_conflict_is_reported(self, home: Path) -> None:
        """One message per conflicting name, in command-name order."""
        _write_manifest(home, 'owner', 'owner', ['owner', 'taken'])
        foreign = home / '.local' / 'bin' / ('mine.cmd' if sys.platform == 'win32' else 'mine')
        foreign.write_text('user file\n', encoding='utf-8')

        errors = command_name_conflicts(['fresh', 'taken', 'mine'], home)

        assert len(errors) == 2
        assert errors[0].startswith('Command name "taken"')
        assert errors[1].startswith('Command name "mine"')


@unix_only
class TestUnixLayout:
    """The bare-name entry is the only file a Unix name maps to."""

    def test_symlink_to_a_binary_is_refused(self, home: Path) -> None:
        """Registering over the native Claude Code link would make the launcher call itself."""
        target = home / '.local' / 'share' / 'claude' / 'versions' / '2.1.0'
        target.parent.mkdir(parents=True)
        target.write_text('binary', encoding='utf-8')
        (home / '.local' / 'bin' / 'claude').symlink_to(target)

        errors = command_name_conflicts(['claude'], home)

        assert len(errors) == 1
        assert os.fspath(home / '.local' / 'bin' / 'claude') in errors[0]
