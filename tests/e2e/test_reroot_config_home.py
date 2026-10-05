"""E2E tests for re-rooting base config-home paths into an isolated profile.

A configuration written for the base profile names ``~/.claude`` in its
``files-to-download`` destinations, its dependency commands and its
``apiKeyHelper``. Installed with ``--command-names``, every such path is
rewritten to the same path inside the profile directory, in every spelling
(``~``, ``$HOME``, ``${HOME}``, ``"$HOME"``, ``$env:USERPROFILE``,
``%USERPROFILE%``, forward or back slashes), together with the
``~/.claude.json`` siblings, so the base ``~/.claude`` tree and
``~/.claude.json`` stay exactly as they were. A path naming another installed
profile's directory or something outside the config home stays as written, a
base run changes nothing, each rewritten item is marked ``[re-rooted]`` in the
installation summary and in ``--dry-run``, the manifest records follow the
rewritten paths, and deselection removes the file the install wrote.

A profile that links content from a source (``--link-dirs``, ``--link-from``)
re-roots the same paths, but a destination that lands inside a linked entry
(``~/.claude/hooks/...`` re-rooted into a linked ``hooks/``) is left to the
link: the source's run wrote it there, so the dependent's run skips it, keeps
it out of ``files_written``, and lists it under ``Provided by links`` in the
summary and in ``--dry-run``; a destination outside every linked entry is
written into the dependent's own profile, a profile that links only
``projects`` writes everything it re-roots, and the Step 23 refresh a source
run starts behaves the same way. The source is an isolated profile or the
base ``~/.claude`` itself, whose run wrote the same destinations without any
rewrite.

Every test runs main() against YAML files on disk with the real download,
dependency, settings, manifest and deselection code: the dependency commands
run for real in bash (Linux, macOS) or PowerShell (Windows) against the
isolated home, which is how the rewritten ``$HOME`` and
``$env:USERPROFILE`` lines are proven to reach the profile and not the base.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.setup_environment import LINKABLE_PROFILE_DIRS
from tests.e2e.profile_support import home_state
from tests.e2e.profile_support import read_manifest
from tests.e2e.profile_support import run_main
from tests.e2e.profile_support import write_child_runner
from tests.e2e.profile_support import write_config
from tests.e2e.validators import validate_manifest

SKIP = ['--skip-install', '--no-admin']
PROFILE = 'p1'
DEPENDENT = 'p2'
OTHER = 'other'
BASE = 'base'
HELPER_COMMAND = 'uv run --no-project --python 3.12'
_ANSI_SEQUENCE = re.compile(r'\x1b\[[0-9;]*m')

# The dependency commands of the configuration, one list per platform; the
# marker directories they create and the files they remove prove where each
# spelling of the config home pointed when the command ran
POSIX_DEPENDENCIES = [
    'mkdir -p ~/.claude/dep-tilde',
    'mkdir -p "$HOME/.claude/dep-home"',
    'mkdir -p "${HOME}/.claude/dep-braces"',
    'mkdir -p "$HOME"/.claude/dep-quoted',
    'rm -rf "$HOME/.claude/statsig"',
    'rm -f "$HOME/.claude.json.backup"',
    'rm -f "$HOME"/.claude.json.corrupted.* 2>/dev/null || true',
]
WINDOWS_DEPENDENCIES = [
    'New-Item -ItemType Directory -Force -Path "~/.claude/dep-tilde" | Out-Null',
    'New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\\.claude\\dep-userprofile" | Out-Null',
    'cmd /c "if not exist %USERPROFILE%\\.claude\\dep-cmd mkdir %USERPROFILE%\\.claude\\dep-cmd"',
    'if (Test-Path "$env:USERPROFILE\\.claude\\statsig") { Remove-Item -Recurse -Force "$env:USERPROFILE\\.claude\\statsig" }',
    'if (Test-Path "$env:USERPROFILE\\.claude.json.backup") { Remove-Item -Force "$env:USERPROFILE\\.claude.json.backup" }',
    'Remove-Item "$env:USERPROFILE\\.claude.json.corrupted.*" -Force -ErrorAction SilentlyContinue',
]
DEPENDENCY_MARKERS = (
    ('dep-tilde', 'dep-userprofile', 'dep-cmd') if sys.platform == 'win32'
    else ('dep-tilde', 'dep-home', 'dep-braces', 'dep-quoted')
)
# The ~/.claude.json siblings the cleanup lines remove: the backup by name,
# the corrupted copy through the shell glob .claude.json.corrupted.*
CLAUDE_JSON_SIBLINGS = ('.claude.json.backup', '.claude.json.corrupted.123')
# The cleanup lines of this platform's list, in list order: statsig, the
# backup, the corrupted glob
PLATFORM_DEPENDENCIES = WINDOWS_DEPENDENCIES if sys.platform == 'win32' else POSIX_DEPENDENCIES


@pytest.fixture
def configs(tmp_path: Path) -> Path:
    """A directory of configurations with the files they install beside them."""
    directory = tmp_path / 'configs'
    for relative, content in (
        ('files/claude.md', '# profile CLAUDE.md\n'),
        ('files/override.yaml', 'override: true\n'),
        ('files/username.py', 'print("user")\n'),
        ('files/outside.txt', 'outside the config home\n'),
        ('files/shared.txt', 'shared with another profile\n'),
        ('files/keep.txt', 'kept\n'),
        ('files/extra.txt', 'extra\n'),
        ('files/a.txt', 'a\n'),
        ('files/b.txt', 'b\n'),
        ('files/c.txt', 'c\n'),
        ('hooks/hook.py', 'print("hook")\n'),
    ):
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    return directory


def _base_config() -> dict[str, Any]:
    """A configuration written for the base profile: every path names ~/.claude."""
    return {
        'name': 'Base Home Env',
        'files-to-download': [
            {'source': 'files/claude.md', 'dest': '~/.claude/CLAUDE.md'},
            {'source': 'files/override.yaml', 'dest': '~/.claude/project-overrides/'},
            {'source': 'files/username.py', 'dest': '~/.claude/scripts/username.py'},
            {'source': 'files/outside.txt', 'dest': '~/.serena/outside.txt'},
        ],
        'dependencies': {
            'linux': list(POSIX_DEPENDENCIES),
            'macos': list(POSIX_DEPENDENCIES),
            'windows': list(WINDOWS_DEPENDENCIES),
        },
        'user-settings': {
            'theme': 'dark',
            'apiKeyHelper': f'{HELPER_COMMAND} ~/.claude/scripts/username.py',
            'awsCredentialExport': '~/.claude/scripts/aws-credentials.sh',
        },
    }


def _linked_config() -> dict[str, Any]:
    """Build a configuration for the base profile whose downloads reach into hooks/ and the config home itself.

    The hooks file and its event make hooks/ a linkable content entry the
    source holds for real; the override lands inside hooks/, the text file
    beside it, and one dependency command names the config home.

    Returns:
        The configuration mapping.
    """
    return {
        'name': 'Linked Home Env',
        'hooks': {
            'files': ['hooks/hook.py'],
            'events': [{'event': 'PostToolUse', 'matcher': 'Edit', 'type': 'command', 'command': 'hook.py'}],
        },
        'files-to-download': [
            {'source': 'files/override.yaml', 'dest': '~/.claude/hooks/project-overrides/override.yaml'},
            {'source': 'files/a.txt', 'dest': '~/.claude/x.txt'},
        ],
        'dependencies': {
            'linux': [POSIX_DEPENDENCIES[0]],
            'macos': [POSIX_DEPENDENCIES[0]],
            'windows': [WINDOWS_DEPENDENCIES[0]],
        },
    }


LINKED_OVERRIDE = f'~/.claude/{DEPENDENT}/hooks/project-overrides/override.yaml'
PROVIDED_HEADING = 'Provided by links (files-to-download destinations inside linked entries, written by the source):'


def _linked_row(source: str) -> str:
    """Spell the [linked] row and the Step 4 skip text for the override a dependent of the source leaves to the link."""
    return f'{LINKED_OVERRIDE}: hooks/ is linked from profile "{source}"'


LINKED_ROW = _linked_row(PROFILE)
BASE_LINKED_ROW = _linked_row(BASE)


def _source_dir(claude_dir: Path, source: str) -> Path:
    """Return the directory a link source holds its content in: the base ~/.claude itself, or the profile below it."""
    return claude_dir if source == BASE else claude_dir / source


def _sibling_dir(directory: Path) -> Path:
    """Return where a config directory keeps its .claude.json siblings: beside the base ~/.claude, inside a profile."""
    return directory.parent if directory.name == '.claude' else directory


def _seed_cleanup_targets(directory: Path) -> None:
    """Create the statsig directory and the .claude.json siblings the cleanup lines remove."""
    (directory / 'statsig').mkdir(parents=True, exist_ok=True)
    (directory / 'statsig' / 'cache.bin').write_bytes(b'cache')
    for name in CLAUDE_JSON_SIBLINGS:
        (_sibling_dir(directory) / name).write_text('{}\n', encoding='utf-8')


def _cleanup_targets_present(directory: Path) -> dict[str, bool]:
    """Report which of the seeded cleanup targets of a config directory still exist."""
    present = {'statsig': (directory / 'statsig').exists()}
    present.update({name: (_sibling_dir(directory) / name).exists() for name in CLAUDE_JSON_SIBLINGS})
    return present


def _cleanup_lines(dependencies: list[str]) -> list[str]:
    """Return the statsig, backup and corrupted cleanup lines of a platform list, in that order."""
    return [
        next(line for line in dependencies if marker in line)
        for marker in ('statsig', '.claude.json.backup', '.claude.json.corrupted.*')
    ]


def _rerooted_line(line: str, profile: str = PROFILE) -> str:
    """Spell a cleanup line the way an isolated run of the default profile layout rewrites it."""
    return (
        line.replace('\\.claude\\statsig', f'\\.claude\\{profile}\\statsig')
        .replace('/.claude/statsig', f'/.claude/{profile}/statsig')
        .replace('\\.claude.json', f'\\.claude\\{profile}\\.claude.json')
        .replace('/.claude.json', f'/.claude/{profile}/.claude.json')
    )


def _helper_path(home: Path, *parts: str) -> str:
    """Spell the apiKeyHelper script path the way the written settings carry it on this platform."""
    if sys.platform == 'win32':
        return os.path.normpath(str(home.joinpath(*parts)))
    return '~/' + '/'.join(parts)


def _output(capsys: pytest.CaptureFixture[str]) -> str:
    """Return everything the run printed, color codes stripped."""
    captured = capsys.readouterr()
    return _ANSI_SEQUENCE.sub('', captured.out + captured.err)


def _rerooted_rows(output: str) -> list[str]:
    """Return the text of every [re-rooted] row of the installation summary."""
    return [line.split('[re-rooted] ', 1)[1] for line in output.splitlines() if '[re-rooted] ' in line]


def _machine_wide_rows(output: str) -> list[str]:
    """Return the text of every [machine-wide] row of the installation summary."""
    return [line.split('[machine-wide] ', 1)[1] for line in output.splitlines() if '[machine-wide] ' in line]


def _linked_rows(output: str) -> list[str]:
    """Return the text of every [linked] row of the installation summary."""
    return [line.split('[linked] ', 1)[1] for line in output.splitlines() if '[linked] ' in line]


def _base_snapshot(home: Path, profiles: tuple[str, ...] = (PROFILE,)) -> dict[str, str]:
    """Snapshot the base config home and its .claude.json siblings, leaving the named profile directories out."""
    profile_dirs = [home / '.claude' / name for name in profiles]
    claude_dir = home / '.claude'
    return home_state(
        home,
        skip=lambda entry: (
            any(entry == profile_dir or profile_dir in entry.parents for profile_dir in profile_dirs)
            or not (entry == claude_dir or claude_dir in entry.parents or entry.name.startswith('.claude.json'))
        ),
    )


def _resolves_to(path: Path, target: Path) -> bool:
    """Report whether a path resolves to the same directory as the target (through a junction or symlink)."""
    return os.path.normcase(os.path.realpath(path)) == os.path.normcase(os.path.realpath(target))


def _assert_base_unchanged(home: Path, before: dict[str, str], link_targets: frozenset[str] = frozenset()) -> None:
    """Check the base config home against its snapshot after a dependent's run.

    Every entry the snapshot holds must be as it was. Step 3 creates a
    missing link target inside the source, so a dependent of the base may
    add an empty ``~/.claude/<entry>`` directory for each linked entry the
    base run never created, and nothing else.

    Args:
        home: The isolated home.
        before: The snapshot taken before the dependent's run.
        link_targets: The entries the dependent links from the base.
    """
    after = _base_snapshot(home, (PROFILE, DEPENDENT))
    changed = {key: (value, after.get(key)) for key, value in before.items() if after.get(key) != value}
    assert not changed, f'the dependent run changed the base config home: {changed}'
    allowed = {f'.claude/{entry}': 'dir' for entry in link_targets}
    added = {key: value for key, value in after.items() if key not in before and allowed.get(key) != value}
    assert not added, f'the dependent run added to the base config home: {added}'


@pytest.mark.usefixtures('e2e_isolated_home')
class TestIsolatedRunStaysInsideItsProfile:
    """The base configuration installs as an isolated profile without touching the base profile."""

    def test_base_tree_and_claude_json_are_unchanged_and_everything_lands_in_the_profile(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Downloads, cleanup lines and the helper all point into the profile; the base is byte-identical."""
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']
        profile_dir = claude_dir / PROFILE
        (home / '.claude.json').write_text(
            json.dumps({'oauthAccount': {'emailAddress': 'base@example.com'}, 'userID': 'base-user'}),
            encoding='utf-8',
        )
        (claude_dir / 'CLAUDE.md').write_text('# base CLAUDE.md\n', encoding='utf-8')
        _seed_cleanup_targets(claude_dir)
        profile_dir.mkdir()
        _seed_cleanup_targets(profile_dir)
        cfg = write_config(configs, 'env.yaml', _base_config())
        before = _base_snapshot(home)

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', PROFILE]) == 0

        assert _base_snapshot(home) == before, 'an isolated run changed the base config home'
        assert (claude_dir / 'CLAUDE.md').read_text(encoding='utf-8') == '# base CLAUDE.md\n'
        assert (claude_dir / 'statsig' / 'cache.bin').exists(), 'the cleanup line removed the base statsig'
        assert (home / '.claude.json.backup').exists(), 'the cleanup line removed the base .claude.json backup'
        assert (home / '.claude.json.corrupted.123').exists(), 'the glob cleanup line removed the base corrupted copy'
        assert (profile_dir / 'CLAUDE.md').read_text(encoding='utf-8') == '# profile CLAUDE.md\n'
        assert (profile_dir / 'project-overrides' / 'override.yaml').read_text(encoding='utf-8') == 'override: true\n'
        assert (profile_dir / 'scripts' / 'username.py').read_text(encoding='utf-8') == 'print("user")\n'
        assert (home / '.serena' / 'outside.txt').exists(), 'a destination outside the config home stays as written'
        for marker in DEPENDENCY_MARKERS:
            assert (profile_dir / marker).is_dir(), f'the dependency did not create {marker} in the profile'
            assert not (claude_dir / marker).exists(), f'the dependency created {marker} in the base'
        assert _cleanup_targets_present(profile_dir) == {
            'statsig': False, '.claude.json.backup': False, '.claude.json.corrupted.123': False,
        }, 'a cleanup line left its target in the profile'
        settings = json.loads((profile_dir / 'config.json').read_text(encoding='utf-8'))
        helper = _helper_path(home, '.claude', PROFILE, 'scripts', 'username.py')
        assert settings['apiKeyHelper'] == f'{HELPER_COMMAND} {helper}'
        assert settings['awsCredentialExport'] == _helper_path(home, '.claude', PROFILE, 'scripts', 'aws-credentials.sh')
        assert f'[re-rooted] files-to-download: ~/.claude/CLAUDE.md -> ~/.claude/{PROFILE}/CLAUDE.md' in _output(capsys)

    def test_manifest_records_follow_the_rerooted_paths(
        self, e2e_isolated_home: dict[str, Path], configs: Path,
    ) -> None:
        """files_written lists the profile files; only the outside destination is machine-wide."""
        home = e2e_isolated_home['home']
        profile_dir = e2e_isolated_home['claude_dir'] / PROFILE
        config = _base_config()
        cfg = write_config(configs, 'env.yaml', config)

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', PROFILE]) == 0

        manifest = read_manifest(profile_dir)
        assert not validate_manifest(profile_dir / 'manifest.json', {**config, 'command-names': [PROFILE]})
        assert manifest['files_written'] == ['CLAUDE.md', 'project-overrides/override.yaml', 'scripts/username.py']
        assert [record['dest'] for record in manifest['machine_wide_destinations']] == [
            str(home / '.serena' / 'outside.txt'),
        ]
        assert manifest['settings_keys_written'] == ['apiKeyHelper', 'awsCredentialExport', 'claudeMdExcludes', 'theme']
        resolved = (profile_dir / 'resolved-config.yaml').read_text(encoding='utf-8')
        assert f'~/.claude/{PROFILE}' not in resolved, 'the recorded configuration keeps the paths as authored'
        assert '~/.claude/CLAUDE.md' in resolved

    def test_base_run_of_the_same_configuration_writes_the_base(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Without command names every path stays as written and lands in the base config home."""
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']
        _seed_cleanup_targets(claude_dir)
        cfg = write_config(configs, 'env.yaml', _base_config())

        assert run_main([str(cfg), *SKIP, '--yes']) == 0

        assert (claude_dir / 'CLAUDE.md').read_text(encoding='utf-8') == '# profile CLAUDE.md\n'
        assert (claude_dir / 'project-overrides' / 'override.yaml').exists()
        assert (claude_dir / 'scripts' / 'username.py').exists()
        assert (home / '.serena' / 'outside.txt').exists()
        for marker in DEPENDENCY_MARKERS:
            assert (claude_dir / marker).is_dir(), f'the dependency did not create {marker} in the base'
        assert _cleanup_targets_present(claude_dir) == {
            'statsig': False, '.claude.json.backup': False, '.claude.json.corrupted.123': False,
        }, 'a cleanup line left its target in the base'
        assert not (claude_dir / PROFILE).exists()
        settings = json.loads((claude_dir / 'settings.json').read_text(encoding='utf-8'))
        assert settings['apiKeyHelper'] == f'{HELPER_COMMAND} {_helper_path(home, ".claude", "scripts", "username.py")}'
        assert settings['awsCredentialExport'] == _helper_path(home, '.claude', 'scripts', 'aws-credentials.sh')
        assert 're-rooted' not in _output(capsys).lower()


@pytest.mark.usefixtures('e2e_isolated_home')
class TestSpellingsAndExemptions:
    """Each spelling of the config home moves; other profiles and outside paths stay."""

    @pytest.mark.skipif(sys.platform == 'win32', reason='POSIX destination spellings')
    def test_each_posix_destination_spelling_lands_in_the_profile(
        self, e2e_isolated_home: dict[str, Path], configs: Path,
    ) -> None:
        """Destinations spelled with ~, $HOME and ${HOME} all land inside the profile."""
        profile_dir = e2e_isolated_home['claude_dir'] / PROFILE
        config: dict[str, Any] = {'name': 'Spellings', 'files-to-download': [
            {'source': 'files/a.txt', 'dest': '~/.claude/spelled/a.txt'},
            {'source': 'files/b.txt', 'dest': '$HOME/.claude/spelled/b.txt'},
            {'source': 'files/c.txt', 'dest': '${HOME}/.claude/spelled/c.txt'},
        ]}
        cfg = write_config(configs, 'env.yaml', config)

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', PROFILE]) == 0

        for name in ('a', 'b', 'c'):
            assert (profile_dir / 'spelled' / f'{name}.txt').read_text(encoding='utf-8') == f'{name}\n'
        assert not (e2e_isolated_home['claude_dir'] / 'spelled').exists()

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows destination spellings')
    def test_each_windows_destination_spelling_lands_in_the_profile(
        self, e2e_isolated_home: dict[str, Path], configs: Path,
    ) -> None:
        """Destinations spelled with ~/, ~\\ and %USERPROFILE%\\ all land inside the profile."""
        profile_dir = e2e_isolated_home['claude_dir'] / PROFILE
        config: dict[str, Any] = {'name': 'Spellings', 'files-to-download': [
            {'source': 'files/a.txt', 'dest': '~/.claude/spelled/a.txt'},
            {'source': 'files/b.txt', 'dest': '~\\.claude\\spelled\\b.txt'},
            {'source': 'files/c.txt', 'dest': '%USERPROFILE%\\.claude\\spelled\\c.txt'},
        ]}
        cfg = write_config(configs, 'env.yaml', config)

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', PROFILE]) == 0

        for name in ('a', 'b', 'c'):
            assert (profile_dir / 'spelled' / f'{name}.txt').read_text(encoding='utf-8') == f'{name}\n'
        assert not (e2e_isolated_home['claude_dir'] / 'spelled').exists()

    def test_other_profile_own_profile_and_outside_paths_stay_as_written(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A path into an installed profile, into this profile, or outside the config home is not moved."""
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']
        other_cfg = write_config(configs, 'other.yaml', {'name': 'Other', 'user-settings': {'theme': 'dark'}})
        assert run_main([str(other_cfg), *SKIP, '--yes', '--command-names', OTHER]) == 0
        config: dict[str, Any] = {'name': 'Exempt', 'files-to-download': [
            {'source': 'files/shared.txt', 'dest': f'~/.claude/{OTHER}/shared.txt'},
            {'source': 'files/keep.txt', 'dest': f'~/.claude/{PROFILE}/own.txt'},
            {'source': 'files/outside.txt', 'dest': '~/.serena/outside.txt'},
            {'source': 'files/a.txt', 'dest': '~/.claude/moved.txt'},
        ]}
        cfg = write_config(configs, 'env.yaml', config)

        assert run_main([str(cfg), *SKIP, '--dry-run', '--command-names', PROFILE]) == 0
        output = _output(capsys)
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', PROFILE]) == 0

        assert (claude_dir / OTHER / 'shared.txt').exists()
        assert (claude_dir / PROFILE / 'own.txt').exists()
        assert (home / '.serena' / 'outside.txt').exists()
        assert (claude_dir / PROFILE / 'moved.txt').exists()
        assert not (claude_dir / 'moved.txt').exists()
        assert not (claude_dir / PROFILE / OTHER).exists()
        assert _rerooted_rows(output) == [f'files-to-download: ~/.claude/moved.txt -> ~/.claude/{PROFILE}/moved.txt']
        rows = _machine_wide_rows(output)
        assert f'files-to-download outside the profile: ~/.claude/{OTHER}/shared.txt' in rows
        assert 'files-to-download outside the profile: ~/.serena/outside.txt' in rows
        assert not any('moved.txt' in row or 'own.txt' in row for row in rows)

    def test_relocated_profile_receives_the_rerooted_files(
        self, e2e_isolated_home: dict[str, Path], configs: Path,
    ) -> None:
        """A profile moved by user-settings.env CLAUDE_CONFIG_DIR is where the paths are re-rooted to."""
        home = e2e_isolated_home['home']
        relocated = home / 'profiles' / PROFILE
        config: dict[str, Any] = {
            'name': 'Relocated',
            'files-to-download': [{'source': 'files/claude.md', 'dest': '~/.claude/CLAUDE.md'}],
            'user-settings': {'env': {'CLAUDE_CONFIG_DIR': str(relocated)}},
        }
        cfg = write_config(configs, 'env.yaml', config)

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', PROFILE]) == 0

        assert (relocated / 'CLAUDE.md').read_text(encoding='utf-8') == '# profile CLAUDE.md\n'
        assert not (e2e_isolated_home['claude_dir'] / 'CLAUDE.md').exists()
        assert not (e2e_isolated_home['claude_dir'] / PROFILE / 'CLAUDE.md').exists()
        assert read_manifest(relocated)['files_written'] == ['CLAUDE.md']


@pytest.mark.usefixtures('e2e_isolated_home')
class TestSummaryRows:
    """The installation summary and --dry-run mark every rewritten item."""

    def test_dry_run_lists_every_rewritten_item_and_marks_the_dependency_row(
        self, configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Files, dependency commands and settings values appear with their original and rewritten paths."""
        cfg = write_config(configs, 'env.yaml', _base_config())

        assert run_main([str(cfg), *SKIP, '--dry-run', '--command-names', PROFILE]) == 0

        output = _output(capsys)
        rows = _rerooted_rows(output)
        assert rows[:3] == [
            f'files-to-download: ~/.claude/CLAUDE.md -> ~/.claude/{PROFILE}/CLAUDE.md',
            f'files-to-download: ~/.claude/project-overrides/ -> ~/.claude/{PROFILE}/project-overrides/',
            f'files-to-download: ~/.claude/scripts/username.py -> ~/.claude/{PROFILE}/scripts/username.py',
        ]
        assert not any('outside.txt' in row for row in rows)
        assert (
            f'dependencies [linux]: rm -rf "$HOME/.claude/statsig" -> rm -rf "$HOME/.claude/{PROFILE}/statsig"'
        ) in rows
        assert (
            f'dependencies [linux]: rm -f "$HOME"/.claude.json.corrupted.* 2>/dev/null || true -> '
            f'rm -f "$HOME"/.claude/{PROFILE}/.claude.json.corrupted.* 2>/dev/null || true'
        ) in rows
        for line in _cleanup_lines(WINDOWS_DEPENDENCIES):
            assert f'dependencies [windows]: {line} -> {_rerooted_line(line)}' in rows
        assert (
            f'dependencies [windows]: Remove-Item "$env:USERPROFILE\\.claude.json.corrupted.*" -Force '
            f'-ErrorAction SilentlyContinue -> Remove-Item "$env:USERPROFILE\\.claude\\{PROFILE}\\.claude.json.corrupted.*" '
            '-Force -ErrorAction SilentlyContinue'
        ) in rows
        assert (
            f'user-settings apiKeyHelper: {HELPER_COMMAND} ~/.claude/scripts/username.py -> '
            f'{HELPER_COMMAND} ~/.claude/{PROFILE}/scripts/username.py'
        ) in rows
        assert (
            'user-settings awsCredentialExport: ~/.claude/scripts/aws-credentials.sh -> '
            f'~/.claude/{PROFILE}/scripts/aws-credentials.sh'
        ) in rows
        for line in _cleanup_lines(PLATFORM_DEPENDENCIES):
            assert f'    $ {_rerooted_line(line)} [re-rooted]' in output
        machine_wide = _machine_wide_rows(output)
        assert not any('files-to-download outside the profile: ~/.claude/' in row for row in machine_wide)
        assert 'files-to-download outside the profile: ~/.serena/outside.txt' in machine_wide
        # A re-rooted dependency command still runs on the machine and can
        # write anywhere, so the dependency row stays machine-wide
        assert 'Dependency commands: run machine-wide (listed above)' in machine_wide

    def test_confirmed_run_prints_the_same_rows(
        self, configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A --yes run shows the re-rooted block in the summary it prints before installing."""
        cfg = write_config(configs, 'env.yaml', _base_config())

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', PROFILE]) == 0

        output = _output(capsys)
        assert 'Re-rooted into the profile (base config-home paths of an isolated run):' in output
        assert f'files-to-download: ~/.claude/CLAUDE.md -> ~/.claude/{PROFILE}/CLAUDE.md' in _rerooted_rows(output)


@pytest.mark.usefixtures('e2e_isolated_home')
class TestDeselectionRemovesTheRerootedFile:
    """Deselecting a component removes the file the install wrote into the profile."""

    def test_deselected_download_is_removed_from_the_profile_and_kept_in_the_base(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The removal plan resolves the re-rooted path, so the base copy of the same file survives."""
        claude_dir = e2e_isolated_home['claude_dir']
        profile_dir = claude_dir / PROFILE
        config: dict[str, Any] = {
            'name': 'Components',
            'files-to-download': [
                {'source': 'files/keep.txt', 'dest': '~/.claude/keep.txt'},
                {'source': 'files/extra.txt', 'dest': '~/.claude/opt/extra.txt'},
            ],
            'components': [
                {'name': 'core', 'includes': {'files-to-download': ['~/.claude/keep.txt']}},
                {'name': 'extra', 'includes': {'files-to-download': ['~/.claude/opt/extra.txt']}},
            ],
        }
        cfg = write_config(configs, 'env.yaml', config)
        base_copy = claude_dir / 'opt' / 'extra.txt'
        base_copy.parent.mkdir()
        base_copy.write_text('base copy\n', encoding='utf-8')

        assert run_main([str(cfg), *SKIP, '--yes', '--select', 'all', '--command-names', PROFILE]) == 0
        assert (profile_dir / 'opt' / 'extra.txt').exists()
        capsys.readouterr()
        assert run_main([str(cfg), *SKIP, '--yes', '--select', 'core', '--command-names', PROFILE]) == 0

        assert not (profile_dir / 'opt' / 'extra.txt').exists(), 'the deselected profile file survived'
        assert (profile_dir / 'keep.txt').exists()
        assert base_copy.read_text(encoding='utf-8') == 'base copy\n'
        assert f'[REMOVE] file: ~/.claude/{PROFILE}/opt/extra.txt' in _output(capsys)


@pytest.mark.usefixtures('e2e_isolated_home')
class TestConfigurationSwitchSeesTheRerootedFiles:
    """The switch guard compares the previous records with the new configuration's re-rooted files."""

    def test_switch_lists_only_the_file_the_new_configuration_drops(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A re-rooted file both configurations install is neither listed as residue nor removed."""
        profile_dir = e2e_isolated_home['claude_dir'] / PROFILE
        cfg_a = write_config(configs, 'a.yaml', {'name': 'A', 'files-to-download': [
            {'source': 'files/claude.md', 'dest': '~/.claude/CLAUDE.md'},
            {'source': 'files/a.txt', 'dest': '~/.claude/only-a.txt'},
        ]})
        cfg_b = write_config(configs, 'b.yaml', {'name': 'B', 'files-to-download': [
            {'source': 'files/override.yaml', 'dest': '~/.claude/CLAUDE.md'},
            {'source': 'files/b.txt', 'dest': '~/.claude/only-b.txt'},
        ]})
        assert run_main([str(cfg_a), *SKIP, '--yes', '--command-names', PROFILE]) == 0
        capsys.readouterr()

        assert run_main([str(cfg_b), *SKIP, '--yes', '--switch-config', '--command-names', PROFILE]) == 0

        output = _output(capsys)
        assert f'file: {profile_dir / "only-a.txt"}' in output
        assert f'Removed {profile_dir / "only-a.txt"}' in output
        assert f'file: {profile_dir / "CLAUDE.md"}' not in output, 'a file the new configuration installs is not residue'
        assert f'Removed {profile_dir / "CLAUDE.md"}' not in output
        assert not (profile_dir / 'only-a.txt').exists()
        assert (profile_dir / 'only-b.txt').read_text(encoding='utf-8') == 'b\n'
        assert (profile_dir / 'CLAUDE.md').read_text(encoding='utf-8') == 'override: true\n'
        assert read_manifest(profile_dir)['files_written'] == ['CLAUDE.md', 'only-b.txt']


def _fd_output(capfd: pytest.CaptureFixture[str]) -> str:
    """Return everything the run and its child processes printed, color codes stripped."""
    captured = capfd.readouterr()
    return _ANSI_SEQUENCE.sub('', (captured.out + captured.err).replace('\r\n', '\n'))


@pytest.mark.usefixtures('e2e_isolated_home')
class TestProfileRerunRerootsAgain:
    """A --profile re-run rewrites the recorded configuration's paths for the profile again.

    The manifest records the configuration as authored, so a re-run with no
    configuration argument must re-root the same paths, restore the profile
    files, run the cleanup lines against the profile and leave the base
    config home exactly as it was.
    """

    def _install(
        self, home: Path, claude_dir: Path, configs: Path,
    ) -> tuple[dict[str, str], dict[str, Any]]:
        """Install the base configuration as the profile; return the base snapshot and the manifest."""
        (home / '.claude.json').write_text(
            json.dumps({'oauthAccount': {'emailAddress': 'base@example.com'}, 'userID': 'base-user'}),
            encoding='utf-8',
        )
        (claude_dir / 'CLAUDE.md').write_text('# base CLAUDE.md\n', encoding='utf-8')
        _seed_cleanup_targets(claude_dir)
        cfg = write_config(configs, 'env.yaml', _base_config())
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', PROFILE]) == 0
        profile_dir = claude_dir / PROFILE
        # What a re-run has to undo: an edited profile file and the cleanup
        # targets back in place
        (profile_dir / 'CLAUDE.md').write_text('# edited by hand\n', encoding='utf-8')
        _seed_cleanup_targets(profile_dir)
        return _base_snapshot(home), read_manifest(profile_dir)

    def _assert_rerun_rerooted(
        self, home: Path, claude_dir: Path, before: dict[str, str], manifest_before: dict[str, Any], output: str,
    ) -> None:
        """Check a re-run against the install: the same files, the same records, the base untouched."""
        profile_dir = claude_dir / PROFILE
        assert 'names a different configuration' not in output, 'the re-run hit the configuration-switch guard'
        assert 'changes the command names of profile' not in output, 'the re-run hit the environment-name guard'
        assert _base_snapshot(home) == before, 'the re-run changed the base config home'
        assert (profile_dir / 'CLAUDE.md').read_text(encoding='utf-8') == '# profile CLAUDE.md\n'
        assert _cleanup_targets_present(profile_dir) == {
            'statsig': False, '.claude.json.backup': False, '.claude.json.corrupted.123': False,
        }, 'a cleanup line of the re-run left its target in the profile'
        manifest = read_manifest(profile_dir)
        assert manifest['files_written'] == manifest_before['files_written']
        assert manifest['config_digest'] == manifest_before['config_digest']
        settings = json.loads((profile_dir / 'config.json').read_text(encoding='utf-8'))
        helper = _helper_path(home, '.claude', PROFILE, 'scripts', 'username.py')
        assert settings['apiKeyHelper'] == f'{HELPER_COMMAND} {helper}'
        rows = _rerooted_rows(output)
        assert f'files-to-download: ~/.claude/CLAUDE.md -> ~/.claude/{PROFILE}/CLAUDE.md' in rows
        assert (
            f'user-settings apiKeyHelper: {HELPER_COMMAND} ~/.claude/scripts/username.py -> '
            f'{HELPER_COMMAND} ~/.claude/{PROFILE}/scripts/username.py'
        ) in rows
        for line in _cleanup_lines(PLATFORM_DEPENDENCIES):
            assert f'    $ {_rerooted_line(line)} [re-rooted]' in output

    def test_profile_flag_rerun_reroots_the_recorded_configuration(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--profile NAME with no configuration argument re-roots the paths again."""
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']
        before, manifest = self._install(home, claude_dir, configs)
        capsys.readouterr()

        assert run_main(['--profile', PROFILE, *SKIP, '--yes']) == 0

        self._assert_rerun_rerooted(home, claude_dir, before, manifest, _output(capsys))

    def test_profile_variable_rerun_reroots_the_recorded_configuration(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """CLAUDE_CODE_TOOLBOX_PROFILE selects the profile the same way the flag does."""
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']
        before, manifest = self._install(home, claude_dir, configs)
        capsys.readouterr()
        monkeypatch.setenv('CLAUDE_CODE_TOOLBOX_PROFILE', PROFILE)

        assert run_main([*SKIP, '--yes']) == 0

        self._assert_rerun_rerooted(home, claude_dir, before, manifest, _output(capsys))

    def test_profile_all_rerun_reroots_in_the_child_run(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str],
    ) -> None:
        """--profile all re-runs the profile as a child process that re-roots the paths again."""
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']
        before, manifest = self._install(home, claude_dir, configs)
        runner = write_child_runner(tmp_path, monkeypatch)
        capfd.readouterr()

        code = run_main(['--profile', 'all', *SKIP, '--yes'], argv0=str(runner))

        output = _fd_output(capfd)
        assert code == 0, output
        assert f'* {PROFILE}: ok' in output
        self._assert_rerun_rerooted(home, claude_dir, before, manifest, output)


@pytest.mark.usefixtures('e2e_isolated_home')
class TestProfileOutsideTheHome:
    """A profile relocated outside the home receives the re-rooted paths spelled absolute."""

    @pytest.mark.parametrize(
        'layout',
        [('elsewhere', PROFILE), ('My Profiles (work)', PROFILE)],
        ids=['outside-home', 'outside-home-spaced'],
    )
    def test_relocated_profile_outside_the_home_receives_absolute_paths(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
        layout: tuple[str, str],
    ) -> None:
        """Files, the cleanup lines and the helper all name the absolute profile directory."""
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']
        outside = home.parent.joinpath(*layout)
        posix_dir = outside.as_posix()
        windows_dir = str(outside).replace('/', '\\')
        (home / '.claude.json').write_text(json.dumps({'userID': 'base-user'}), encoding='utf-8')
        _seed_cleanup_targets(claude_dir)
        outside.mkdir(parents=True)
        _seed_cleanup_targets(outside)
        posix_statsig = next(line for line in POSIX_DEPENDENCIES if 'statsig' in line)
        windows_statsig = next(line for line in WINDOWS_DEPENDENCIES if 'statsig' in line)
        config: dict[str, Any] = {
            'name': 'Outside The Home',
            'files-to-download': [
                {'source': 'files/claude.md', 'dest': '~/.claude/CLAUDE.md'},
                {'source': 'files/username.py', 'dest': '~/.claude/scripts/username.py'},
            ],
            'dependencies': {'linux': [posix_statsig], 'macos': [posix_statsig], 'windows': [windows_statsig]},
            'user-settings': {
                'env': {'CLAUDE_CONFIG_DIR': str(outside)},
                'apiKeyHelper': f'{HELPER_COMMAND} ~/.claude/scripts/username.py',
            },
        }
        cfg = write_config(configs, 'env.yaml', config)
        before = _base_snapshot(home)

        assert run_main([str(cfg), *SKIP, '--dry-run', '--command-names', PROFILE]) == 0
        dry_run = _output(capsys)
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', PROFILE]) == 0

        assert (outside / 'CLAUDE.md').read_text(encoding='utf-8') == '# profile CLAUDE.md\n'
        assert (outside / 'scripts' / 'username.py').read_text(encoding='utf-8') == 'print("user")\n'
        assert read_manifest(outside)['files_written'] == ['CLAUDE.md', 'scripts/username.py']
        assert not (outside / 'statsig').exists(), 'the cleanup line left the profile statsig'
        assert (claude_dir / 'statsig' / 'cache.bin').exists(), 'the cleanup line removed the base statsig'
        assert _base_snapshot(home) == before, 'an isolated run changed the base config home'
        assert not (claude_dir / PROFILE).exists(), 'setup wrote into the default profile directory'
        settings = json.loads((outside / 'config.json').read_text(encoding='utf-8'))
        assert settings['apiKeyHelper'] == f'{HELPER_COMMAND} {posix_dir}/scripts/username.py'
        rows = _rerooted_rows(dry_run)
        assert f'files-to-download: ~/.claude/CLAUDE.md -> {posix_dir}/CLAUDE.md' in rows
        assert f'files-to-download: ~/.claude/scripts/username.py -> {posix_dir}/scripts/username.py' in rows
        assert f'dependencies [linux]: {posix_statsig} -> rm -rf "{posix_dir}/statsig"' in rows
        rewritten_windows = windows_statsig.replace('$env:USERPROFILE\\.claude\\statsig', f'{windows_dir}\\statsig')
        assert f'dependencies [windows]: {windows_statsig} -> {rewritten_windows}' in rows
        assert (
            f'user-settings apiKeyHelper: {HELPER_COMMAND} ~/.claude/scripts/username.py -> '
            f'{HELPER_COMMAND} {posix_dir}/scripts/username.py'
        ) in rows
        assert not any('files-to-download outside the profile' in row for row in _machine_wide_rows(dry_run))


@pytest.mark.usefixtures('e2e_isolated_home')
class TestDependentLeavesLinkedDestinationsToTheLink:
    """A profile linking content re-roots its paths and leaves a destination inside a linked entry to the source.

    The source's run wrote that file into the shared directory; a dependent
    that wrote it again would write through the link into the source. The
    source copy carries an edit the source's configuration does not hold,
    so a write through the link is seen as the edit disappearing. The source
    is the isolated profile ``p1`` or the base ``~/.claude``, whose own run
    wrote the same destinations as written.
    """

    EDITED = 'override: true\nedited: in the source\n'

    def _install_source(self, configs: Path, claude_dir: Path, source: str = PROFILE) -> tuple[Path, Path]:
        """Install the configuration as the source and edit its override file.

        Args:
            configs: The configuration directory.
            claude_dir: The base ``~/.claude`` of the isolated home.
            source: The profile to install as: an isolated profile name, or
                ``base`` for a run without command names.

        Returns:
            The configuration path and the source's override file.
        """
        cfg = write_config(configs, 'linked.yaml', _linked_config())
        names = [] if source == BASE else ['--command-names', source]
        assert run_main([str(cfg), *SKIP, '--yes', *names]) == 0
        source_dir = _source_dir(claude_dir, source)
        source_file = source_dir / 'hooks' / 'project-overrides' / 'override.yaml'
        assert source_file.read_text(encoding='utf-8') == 'override: true\n'
        assert (source_dir / 'x.txt').read_text(encoding='utf-8') == 'a\n'
        assert read_manifest(source_dir)['files_written'] == [
            'hooks/hook.py', 'hooks/project-overrides/override.yaml', 'x.txt',
        ], 'the source holds every file itself'
        source_file.write_text(self.EDITED, encoding='utf-8')
        return cfg, source_file

    def _assert_dependent_left_the_override_to_the_link(
        self, home: Path, claude_dir: Path, source_file: Path, before: dict[str, str], output: str,
        source: str = PROFILE, linked: frozenset[str] = frozenset(),
    ) -> None:
        """Check a dependent run that links hooks/: nothing written through the link, x.txt in its own profile.

        Args:
            home: The isolated home.
            claude_dir: The base ``~/.claude`` of the isolated home.
            source_file: The source's override file, carrying the edit.
            before: The base snapshot taken before the dependent's run.
            output: Everything the dependent's run printed.
            source: The profile the dependent links from.
            linked: The entries the dependent links, which Step 3 creates
                inside a base source when the base run never made them.
        """
        dependent_dir = claude_dir / DEPENDENT
        source_dir = _source_dir(claude_dir, source)
        assert source_file.read_text(encoding='utf-8') == self.EDITED, 'the dependent wrote through the link'
        assert _resolves_to(dependent_dir / 'hooks', source_dir / 'hooks')
        assert (dependent_dir / 'hooks' / 'hook.py').is_file(), 'the wired hook file is reached through the link'
        assert (dependent_dir / 'x.txt').read_text(encoding='utf-8') == 'a\n'
        assert (source_dir / 'x.txt').read_text(encoding='utf-8') == 'a\n', "the source's own copy is untouched"
        if source != BASE:
            assert not (claude_dir / 'x.txt').exists()
            assert not (claude_dir / 'hooks').exists()
        _assert_base_unchanged(home, before, linked if source == BASE else frozenset())
        manifest = read_manifest(dependent_dir)
        assert manifest['files_written'] == ['x.txt']
        assert manifest['machine_wide_destinations'] == []
        for marker in DEPENDENCY_MARKERS[:1]:
            assert (dependent_dir / marker).is_dir(), 're-rooted dependency commands run for the dependent as before'
            if source != BASE:
                assert not (claude_dir / marker).exists()
        rows = _rerooted_rows(output)
        assert f'files-to-download: ~/.claude/hooks/project-overrides/override.yaml -> {LINKED_OVERRIDE}' in rows
        assert f'files-to-download: ~/.claude/x.txt -> ~/.claude/{DEPENDENT}/x.txt' in rows
        assert PROVIDED_HEADING in output
        assert _linked_rows(output) == [_linked_row(source)]
        assert f'Skipping {_linked_row(source)}' in output
        assert '* Files to download: 1' in output, 'the summary counts only the file this run writes'
        assert not any('project-overrides' in row for row in _machine_wide_rows(output))

    def test_dependent_linking_all_skips_the_destination_inside_the_linked_hooks(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--link-dirs all: the override is provided by the link, x.txt lands in the dependent's own profile."""
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']
        cfg, source_file = self._install_source(configs, claude_dir)
        before = _base_snapshot(home, (PROFILE, DEPENDENT))
        capsys.readouterr()

        assert run_main([
            str(cfg), *SKIP, '--yes', '--command-names', DEPENDENT, '--link-dirs', 'all', '--link-from', PROFILE,
        ]) == 0

        self._assert_dependent_left_the_override_to_the_link(home, claude_dir, source_file, before, _output(capsys))

    def test_dependent_linking_hooks_only_skips_the_same_destination(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--link-dirs hooks: the one linked entry decides; every other re-rooted path is written as before."""
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']
        cfg, source_file = self._install_source(configs, claude_dir)
        before = _base_snapshot(home, (PROFILE, DEPENDENT))
        capsys.readouterr()

        assert run_main([
            str(cfg), *SKIP, '--yes', '--command-names', DEPENDENT, '--link-dirs', 'hooks', '--link-from', PROFILE,
        ]) == 0

        output = _output(capsys)
        self._assert_dependent_left_the_override_to_the_link(home, claude_dir, source_file, before, output)
        assert not (claude_dir / DEPENDENT / 'projects').exists(), 'only hooks/ is linked'
        assert f'Links (from profile "{PROFILE}"):' in output

    def test_dependent_linking_all_from_base_skips_the_destination_inside_the_linked_hooks(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--link-dirs all --link-from base: the base wrote the override as written, the dependent leaves it there."""
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']
        cfg, source_file = self._install_source(configs, claude_dir, BASE)
        before = _base_snapshot(home, (PROFILE, DEPENDENT))
        capsys.readouterr()

        assert run_main([
            str(cfg), *SKIP, '--yes', '--command-names', DEPENDENT, '--link-dirs', 'all', '--link-from', BASE,
        ]) == 0

        self._assert_dependent_left_the_override_to_the_link(
            home, claude_dir, source_file, before, _output(capsys), source=BASE, linked=frozenset(LINKABLE_PROFILE_DIRS),
        )

    def test_dependent_linking_hooks_only_from_base_skips_the_same_destination(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--link-dirs hooks --link-from base: the base's hooks/ decides; every other re-rooted path is written as before."""
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']
        cfg, source_file = self._install_source(configs, claude_dir, BASE)
        before = _base_snapshot(home, (PROFILE, DEPENDENT))
        capsys.readouterr()

        assert run_main([
            str(cfg), *SKIP, '--yes', '--command-names', DEPENDENT, '--link-dirs', 'hooks', '--link-from', BASE,
        ]) == 0

        output = _output(capsys)
        self._assert_dependent_left_the_override_to_the_link(
            home, claude_dir, source_file, before, output, source=BASE, linked=frozenset({'hooks'}),
        )
        assert not (claude_dir / DEPENDENT / 'projects').exists(), 'only hooks/ is linked'
        assert f'Links (from profile "{BASE}"):' in output

    def test_projects_only_profile_writes_everything_it_reroots(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A profile that links only projects/ holds its own hooks/, so both destinations land in its profile."""
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']
        cfg, source_file = self._install_source(configs, claude_dir)
        before = _base_snapshot(home, (PROFILE, DEPENDENT))
        capsys.readouterr()

        assert run_main([
            str(cfg), *SKIP, '--yes', '--command-names', DEPENDENT, '--link-dirs', 'projects', '--link-from', PROFILE,
        ]) == 0

        output = _output(capsys)
        dependent_dir = claude_dir / DEPENDENT
        assert _resolves_to(dependent_dir / 'projects', claude_dir / PROFILE / 'projects')
        assert not _resolves_to(dependent_dir / 'hooks', claude_dir / PROFILE / 'hooks'), 'hooks/ is a real directory'
        assert (dependent_dir / 'hooks' / 'project-overrides' / 'override.yaml').read_text(encoding='utf-8') == (
            'override: true\n'
        )
        assert (dependent_dir / 'hooks' / 'hook.py').read_text(encoding='utf-8') == 'print("hook")\n'
        assert (dependent_dir / 'x.txt').read_text(encoding='utf-8') == 'a\n'
        assert source_file.read_text(encoding='utf-8') == self.EDITED, 'the source copy is its own'
        assert _base_snapshot(home, (PROFILE, DEPENDENT)) == before
        assert read_manifest(dependent_dir)['files_written'] == [
            'hooks/hook.py', 'hooks/project-overrides/override.yaml', 'x.txt',
        ]
        assert f'files-to-download: ~/.claude/hooks/project-overrides/override.yaml -> {LINKED_OVERRIDE}' in (
            _rerooted_rows(output)
        )
        assert _linked_rows(output) == []
        assert PROVIDED_HEADING not in output
        assert f'Skipping {LINKED_OVERRIDE}' not in output
        assert '* Files to download: 2' in output

    def test_projects_only_profile_of_the_base_writes_everything_it_reroots(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A profile that links only the base's projects/ holds its own hooks/ and never writes into the base."""
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']
        cfg, source_file = self._install_source(configs, claude_dir, BASE)
        before = _base_snapshot(home, (PROFILE, DEPENDENT))
        capsys.readouterr()

        assert run_main([
            str(cfg), *SKIP, '--yes', '--command-names', DEPENDENT, '--link-dirs', 'projects', '--link-from', BASE,
        ]) == 0

        output = _output(capsys)
        dependent_dir = claude_dir / DEPENDENT
        assert _resolves_to(dependent_dir / 'projects', claude_dir / 'projects')
        assert not _resolves_to(dependent_dir / 'hooks', claude_dir / 'hooks'), 'hooks/ is a real directory'
        assert (dependent_dir / 'hooks' / 'project-overrides' / 'override.yaml').read_text(encoding='utf-8') == (
            'override: true\n'
        )
        assert (dependent_dir / 'hooks' / 'hook.py').read_text(encoding='utf-8') == 'print("hook")\n'
        assert (dependent_dir / 'x.txt').read_text(encoding='utf-8') == 'a\n'
        assert source_file.read_text(encoding='utf-8') == self.EDITED, "the base's copy is its own"
        _assert_base_unchanged(home, before, frozenset({'projects'}))
        assert read_manifest(dependent_dir)['files_written'] == [
            'hooks/hook.py', 'hooks/project-overrides/override.yaml', 'x.txt',
        ]
        rows = _rerooted_rows(output)
        assert f'files-to-download: ~/.claude/hooks/project-overrides/override.yaml -> {LINKED_OVERRIDE}' in rows
        assert f'files-to-download: ~/.claude/x.txt -> ~/.claude/{DEPENDENT}/x.txt' in rows
        assert _linked_rows(output) == []
        assert PROVIDED_HEADING not in output
        assert f'Skipping {LINKED_OVERRIDE}' not in output
        assert '* Files to download: 2' in output

    def test_dry_run_of_a_dependent_lists_the_provided_destination_and_writes_nothing(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--dry-run shows the re-rooted rows, the provided row and the count before any link or file exists."""
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']
        cfg, source_file = self._install_source(configs, claude_dir)
        before = _base_snapshot(home, (PROFILE,))
        capsys.readouterr()

        assert run_main([
            str(cfg), *SKIP, '--dry-run', '--command-names', DEPENDENT, '--link-dirs', 'all', '--link-from', PROFILE,
        ]) == 0

        output = _output(capsys)
        assert not (claude_dir / DEPENDENT).exists(), 'a dry run wrote the profile'
        assert source_file.read_text(encoding='utf-8') == self.EDITED
        assert _base_snapshot(home, (PROFILE,)) == before
        rows = _rerooted_rows(output)
        assert f'files-to-download: ~/.claude/hooks/project-overrides/override.yaml -> {LINKED_OVERRIDE}' in rows
        assert f'files-to-download: ~/.claude/x.txt -> ~/.claude/{DEPENDENT}/x.txt' in rows
        assert PROVIDED_HEADING in output
        assert _linked_rows(output) == [LINKED_ROW]
        assert '* Files to download: 1' in output
        assert f'hooks -> {claude_dir / PROFILE / "hooks"} [create]' in output

    def test_source_rerun_refreshes_the_dependent_the_same_way(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str],
    ) -> None:
        """Step 23 of the source re-runs the dependent as a child that leaves the override to the link again."""
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']
        cfg, source_file = self._install_source(configs, claude_dir)
        assert run_main([
            str(cfg), *SKIP, '--yes', '--command-names', DEPENDENT, '--link-dirs', 'all', '--link-from', PROFILE,
        ]) == 0
        dependent_dir = claude_dir / DEPENDENT
        installed_at = read_manifest(dependent_dir)['installed_at']
        (dependent_dir / 'x.txt').write_text('edited in the dependent\n', encoding='utf-8')
        runner = write_child_runner(tmp_path, monkeypatch)
        before = _base_snapshot(home, (PROFILE, DEPENDENT))
        capfd.readouterr()

        code = run_main(['--profile', PROFILE, *SKIP, '--yes'], argv0=str(runner))

        output = _fd_output(capfd)
        assert code == 0, output
        assert f'Step 23: Refreshing 1 dependent profile(s): {DEPENDENT}...' in output
        assert f'=== Dependent profile {DEPENDENT} ===' in output
        assert f'- {DEPENDENT}: ok' in output
        child_output = output[output.index(f'=== Dependent profile {DEPENDENT} ==='):]
        assert PROVIDED_HEADING in child_output
        assert _linked_rows(child_output) == [LINKED_ROW]
        assert f'Skipping {LINKED_OVERRIDE}: hooks/ is linked from profile "{PROFILE}"' in child_output
        assert f'files-to-download: ~/.claude/x.txt -> ~/.claude/{DEPENDENT}/x.txt' in _rerooted_rows(child_output)
        assert source_file.read_text(encoding='utf-8') == 'override: true\n', 'the source run restored its own file'
        assert (dependent_dir / 'x.txt').read_text(encoding='utf-8') == 'a\n', 'the child restored its own file'
        manifest = read_manifest(dependent_dir)
        assert manifest['installed_at'] != installed_at, 'the dependent was refreshed'
        assert manifest['files_written'] == ['x.txt']
        assert _resolves_to(dependent_dir / 'hooks', claude_dir / PROFILE / 'hooks')
        assert _base_snapshot(home, (PROFILE, DEPENDENT)) == before, 'the refresh changed the base config home'

    def test_base_source_rerun_refreshes_the_dependent_the_same_way(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str],
    ) -> None:
        """Step 23 of --profile base re-runs the dependent as a child that leaves the override to the base's hooks/ again."""
        claude_dir = e2e_isolated_home['claude_dir']
        cfg, source_file = self._install_source(configs, claude_dir, BASE)
        assert run_main([
            str(cfg), *SKIP, '--yes', '--command-names', DEPENDENT, '--link-dirs', 'all', '--link-from', BASE,
        ]) == 0
        dependent_dir = claude_dir / DEPENDENT
        installed_at = read_manifest(dependent_dir)['installed_at']
        (dependent_dir / 'x.txt').write_text('edited in the dependent\n', encoding='utf-8')
        runner = write_child_runner(tmp_path, monkeypatch)
        capfd.readouterr()

        code = run_main(['--profile', BASE, *SKIP, '--yes'], argv0=str(runner))

        output = _fd_output(capfd)
        assert code == 0, output
        assert f'Step 23: Refreshing 1 dependent profile(s): {DEPENDENT}...' in output
        assert f'=== Dependent profile {DEPENDENT} ===' in output
        assert f'- {DEPENDENT}: ok' in output
        child_output = output[output.index(f'=== Dependent profile {DEPENDENT} ==='):]
        assert PROVIDED_HEADING in child_output
        assert _linked_rows(child_output) == [BASE_LINKED_ROW]
        assert f'Skipping {BASE_LINKED_ROW}' in child_output
        assert f'files-to-download: ~/.claude/x.txt -> ~/.claude/{DEPENDENT}/x.txt' in _rerooted_rows(child_output)
        assert source_file.read_text(encoding='utf-8') == 'override: true\n', 'the base run restored its own file'
        assert (claude_dir / 'x.txt').read_text(encoding='utf-8') == 'a\n'
        assert (dependent_dir / 'x.txt').read_text(encoding='utf-8') == 'a\n', 'the child restored its own file'
        manifest = read_manifest(dependent_dir)
        assert manifest['installed_at'] != installed_at, 'the dependent was refreshed'
        assert manifest['files_written'] == ['x.txt']
        assert _resolves_to(dependent_dir / 'hooks', claude_dir / 'hooks')
