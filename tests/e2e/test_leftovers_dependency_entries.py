"""E2E tests for dependency entries: what the Step 6 dependency commands install into a profile's content directories.

The tests install real local YAML files into an isolated home through main(),
whose dependency commands run for real (bash on Linux and macOS, PowerShell
on Windows) and create skill directories the way a skills installer in copy
mode does: each skill is built in a staging directory beside the home, the
old one is removed and the new one moved into place. The configuration is
then edited in place (its identity stays the same) to drop one command and
narrow another: the next run lists, after Step 6, the entries no command
installs any more and removes none of them even with --remove-leftovers,
and the run after it removes them in Step 23. A command that creates its
entry only when it is absent keeps it, and a profile whose skills/ is a link
observes nothing there. A skill the configuration installed itself and a
dependency command now installs stays in place through a flagged run.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.leftovers_support import SKIP
from tests.e2e.leftovers_support import leftover_rows as _block
from tests.e2e.leftovers_support import printed as _output
from tests.e2e.profile_support import home_state
from tests.e2e.profile_support import read_manifest
from tests.e2e.profile_support import run_main
from tests.e2e.profile_support import write_config
from tests.e2e.validators import validate_manifest

PLATFORM = {'win32': 'windows', 'darwin': 'macos'}.get(sys.platform, 'linux')
LISTED_NOW = 'Dependency entries listed now (2; --remove-leftovers removes them on a later run):'


def _recreate(*names: str) -> str:
    """A command that installs skill directories the way a copy-mode installer does: built aside, then moved in.

    Every path is spelled out per name, with no shell variable of the
    command's own, so no expansion can leave a path pointing at skills/
    itself.

    Args:
        *names: The skill names.

    Returns:
        The command for this platform's shell.
    """
    if PLATFORM == 'windows':
        skills, stage = '$env:USERPROFILE\\.claude\\skills', '$env:USERPROFILE\\stage'
        steps = [f'New-Item -ItemType Directory -Force -Path "{skills}", "{stage}" | Out-Null']
        for name in names:
            steps.extend([
                f'Remove-Item -Recurse -Force -ErrorAction SilentlyContinue "{stage}\\{name}"',
                f'New-Item -ItemType Directory -Path "{stage}\\{name}" | Out-Null',
                f'Set-Content -Path "{stage}\\{name}\\SKILL.md" -Value {name}',
                f'Remove-Item -Recurse -Force -ErrorAction SilentlyContinue "{skills}\\{name}"',
                f'Move-Item -Path "{stage}\\{name}" -Destination "{skills}\\{name}"',
            ])
        return '; '.join(steps)
    steps = ['mkdir -p "$HOME/.claude/skills" "$HOME/stage"']
    for name in names:
        steps.extend([
            f'rm -rf "$HOME/stage/{name}"',
            f'mkdir "$HOME/stage/{name}"',
            f'echo {name} > "$HOME/stage/{name}/SKILL.md"',
            f'rm -rf "$HOME/.claude/skills/{name}"',
            f'mv "$HOME/stage/{name}" "$HOME/.claude/skills/{name}"',
        ])
    return ' && '.join(steps)


def _create(name: str) -> str:
    """A command that creates one skill directory in place."""
    if PLATFORM == 'windows':
        return (
            f'New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\\.claude\\skills\\{name}" | Out-Null; '
            f'Set-Content -Path "$env:USERPROFILE\\.claude\\skills\\{name}\\SKILL.md" -Value {name}'
        )
    return f'mkdir -p "$HOME/.claude/skills/{name}" && echo {name} > "$HOME/.claude/skills/{name}/SKILL.md"'


def _create_if_absent(name: str) -> str:
    """A command that creates one skill directory only when it is absent."""
    if PLATFORM == 'windows':
        return (
            f'if (-not (Test-Path "$env:USERPROFILE\\.claude\\skills\\{name}")) {{ {_create(name)} }}'
        )
    return f'[ -e "$HOME/.claude/skills/{name}" ] || {{ {_create(name)}; }}'


def _config(rules: list[str], commands: list[str]) -> dict[str, Any]:
    """A configuration with rules and this platform's dependency commands."""
    return {'name': 'Dependency Env', 'rules': rules, 'dependencies': {PLATFORM: commands}}


@pytest.fixture
def configs(tmp_path: Path) -> Path:
    """A directory of configurations with the rules they install beside them."""
    directory = tmp_path / 'configs'
    for relative, content in (('rules/rule.md', '# rule\n'), ('rules/other.md', '# other rule\n')):
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    return directory


def _named(config: dict[str, Any], profile: str | None) -> dict[str, Any]:
    """The configuration as an isolated run installs it, with its command name, for validate_manifest()."""
    return {**config, 'command-names': [profile]} if profile else config


def _commands(manifest: dict[str, Any]) -> dict[str, list[str]]:
    """Map each recorded command to the paths of the entries it is credited with."""
    return {
        str(record['command']): [str(entry['path']) for entry in record['entries']]
        for record in manifest['dependency_entries']
    }


def _dependency_items(manifest: dict[str, Any]) -> list[str]:
    """Return the paths of the dependency entries the manifest's leftovers field carries."""
    return sorted(
        str(item['path']) for item in manifest['leftovers']['items'] if item['kind'] == 'dependency-entry'
    )


@pytest.mark.usefixtures('e2e_isolated_home')
class TestDependencyEntries:
    """Step 6 records what each command installed, lists what none installs any more, and a later run removes it."""

    @pytest.mark.parametrize('profile', ['prof-d', None], ids=['isolated', 'base'])
    def test_listed_after_step_6_and_removed_by_the_next_flagged_run(
        self,
        e2e_isolated_home: dict[str, Path],
        configs: Path,
        capsys: pytest.CaptureFixture[str],
        profile: str | None,
    ) -> None:
        claude_dir = e2e_isolated_home['claude_dir']
        profile_dir = claude_dir / profile if profile else claude_dir
        skills = profile_dir / 'skills'
        names = ['--command-names', profile] if profile else []
        rerun = ['--profile', profile or 'base', *SKIP, '--yes', '--remove-leftovers']
        first = _config(
            ['rules/rule.md', 'rules/other.md'],
            [_recreate('s1', 's2'), _create('s3'), _create_if_absent('s4')],
        )
        cfg = write_config(configs, 'env.yaml', first)
        assert run_main([str(cfg), *SKIP, '--yes', *names]) == 0
        manifest = read_manifest(profile_dir)
        assert not validate_manifest(profile_dir / 'manifest.json', _named(first, profile))
        assert sorted(path for paths in _commands(manifest).values() for path in paths) == [
            'skills/s1', 'skills/s2', 'skills/s3', 'skills/s4',
        ]

        # The next version drops the s3 command and narrows the recreating
        # command to s1; it also drops a rule, so Step 23 runs and patches
        # the manifest
        second = _config(['rules/rule.md'], [_recreate('s1'), _create_if_absent('s4')])
        write_config(configs, 'env.yaml', second)
        capsys.readouterr()
        assert run_main(rerun) == 0
        output = _output(capsys)
        assert 'Step 23: Removing leftovers...' in output
        assert not (profile_dir / 'rules' / 'other.md').exists(), 'the dropped rule is removed in Step 23'
        assert (skills / 's2').is_dir(), 'the run that lists an entry never removes it'
        assert (skills / 's3').is_dir(), 'the run that lists an entry never removes it'
        assert LISTED_NOW in output
        for name in ('s2', 's3'):
            assert f'dependency entry: {skills / name} (from: ' in output
        manifest = read_manifest(profile_dir)
        assert _dependency_items(manifest) == ['skills/s2', 'skills/s3']
        assert manifest['leftovers']['removed'] == ['file: rules/other.md']
        assert {entry['reason'] for entry in manifest['leftovers']['kept']} == {
            'listed after Step 6 of this run; a later run with --remove-leftovers removes it',
        }
        assert sorted(_commands(manifest).values()) == [['skills/s1'], ['skills/s4']], (
            'the recreating command keeps what it installed again, the create-if-absent command keeps its entry'
        )
        assert not validate_manifest(profile_dir / 'manifest.json', _named(second, profile))

        # A dry run of the next flagged run names both and removes nothing
        before = home_state(e2e_isolated_home['home'])
        assert run_main([*rerun, '--dry-run']) == 0
        dry = _output(capsys)
        assert home_state(e2e_isolated_home['home']) == before
        rows = _block(dry)
        for name in ('s2', 's3'):
            assert any(
                row.startswith(f'  [would be removed in Step 23] dependency entry: {skills / name} (from: ')
                for row in rows
            ), rows

        # The next flagged run removes them in Step 23
        assert run_main(rerun) == 0
        output = _output(capsys)
        assert not (skills / 's2').exists()
        assert not (skills / 's3').exists()
        assert (skills / 's1' / 'SKILL.md').is_file()
        assert (skills / 's4' / 'SKILL.md').is_file()
        manifest = read_manifest(profile_dir)
        assert manifest['leftovers']['removed'] == ['dependency entry: skills/s2', 'dependency entry: skills/s3']
        assert manifest['leftovers']['items'] == []
        assert 'Leftovers removed (2):' in output


@pytest.mark.usefixtures('e2e_isolated_home')
class TestLinkedSkillsAreNotObserved:
    """A profile that links skills/ from another profile records nothing a command writes through the link."""

    def test_a_dependent_linking_skills_records_no_entry_there(
        self, e2e_isolated_home: dict[str, Path], configs: Path,
    ) -> None:
        claude_dir = e2e_isolated_home['claude_dir']
        cfg = write_config(configs, 'env.yaml', _config(['rules/rule.md'], [_recreate('s1')]))
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'src']) == 0
        assert run_main([
            str(cfg), *SKIP, '--yes', '--command-names', 'dep', '--link-dirs', 'skills', '--link-from', 'src',
        ]) == 0

        assert list(_commands(read_manifest(claude_dir / 'src')).values()) == [['skills/s1']]
        assert read_manifest(claude_dir / 'dep')['dependency_entries'] == []
        assert (claude_dir / 'src' / 'skills' / 's1' / 'SKILL.md').is_file(), 'the command wrote through the link'


def _copy_in(source: Path, name: str) -> str:
    """A command that installs a skill directory by copying it whole from a source directory, replacing any earlier one."""
    if PLATFORM == 'windows':
        skills = '$env:USERPROFILE\\.claude\\skills'
        return '; '.join([
            f'New-Item -ItemType Directory -Force -Path "{skills}" | Out-Null',
            f'Remove-Item -Recurse -Force -ErrorAction SilentlyContinue "{skills}\\{name}"',
            f'Copy-Item -Recurse -Path "{source}" -Destination "{skills}\\{name}"',
        ])
    return (
        f'mkdir -p "$HOME/.claude/skills" && rm -rf "$HOME/.claude/skills/{name}" '
        f'&& cp -R "{source}" "$HOME/.claude/skills/{name}"'
    )


@pytest.mark.usefixtures('e2e_isolated_home')
class TestSkillMovedToADependencyCommand:
    """A skill the configuration installed itself and a dependency command now installs stays in place."""

    @pytest.mark.parametrize('profile', ['prof-m', None], ids=['isolated', 'base'])
    def test_the_command_owns_the_skill_and_the_flagged_run_leaves_it(
        self,
        e2e_isolated_home: dict[str, Path],
        configs: Path,
        capsys: pytest.CaptureFixture[str],
        profile: str | None,
    ) -> None:
        claude_dir = e2e_isolated_home['claude_dir']
        profile_dir = claude_dir / profile if profile else claude_dir
        skill_file = profile_dir / 'skills' / 'moved' / 'SKILL.md'
        source = configs / 'skills' / 'moved'
        source.mkdir(parents=True)
        (source / 'SKILL.md').write_bytes(b'# moved skill\n')
        names = ['--command-names', profile] if profile else []
        first = {
            **_config(['rules/rule.md', 'rules/other.md'], []),
            'skills': [{'name': 'moved', 'base': 'skills/moved/', 'files': ['SKILL.md']}],
        }
        cfg = write_config(configs, 'env.yaml', first)
        assert run_main([str(cfg), *SKIP, '--yes', *names]) == 0
        assert skill_file.read_bytes() == b'# moved skill\n'
        assert 'skills/moved/SKILL.md' in [record['path'] for record in read_manifest(profile_dir)['files_written']]

        # The next version installs the skill through a dependency command
        # with the same bytes, and drops a rule, so Step 23 removes something
        second = _config(['rules/rule.md'], [_copy_in(source, 'moved')])
        write_config(configs, 'env.yaml', second)
        capsys.readouterr()
        assert run_main(['--profile', profile or 'base', *SKIP, '--yes', '--remove-leftovers']) == 0
        output = _output(capsys)
        assert not (profile_dir / 'rules' / 'other.md').exists(), 'the dropped rule is removed in Step 23'
        assert skill_file.read_bytes() == b'# moved skill\n', 'the skill the command installed stays'
        manifest = read_manifest(profile_dir)
        assert manifest['leftovers']['removed'] == ['file: rules/other.md']
        assert {'label': 'file: skills/moved/SKILL.md', 'reason': 'recreated'} in manifest['leftovers']['dropped']
        assert manifest['leftovers']['items'] == []
        assert list(_commands(manifest).values()) == [['skills/moved']]
        assert f'file: {skill_file} (installed again by a dependency command)' in output
        assert not validate_manifest(profile_dir / 'manifest.json', _named(second, profile))


def _guarded(command: str) -> str:
    """Prefix a command with a check that fails it, with the same text, while the home holds a fail marker."""
    if PLATFORM == 'windows':
        return f'if (Test-Path "$env:USERPROFILE\\fail-marker") {{ exit 1 }}; {command}'
    return f'test ! -e "$HOME/fail-marker" && {command}'


@pytest.mark.usefixtures('e2e_isolated_home')
class TestCommandOutcomes:
    """A listed entry stays while its command fails, and is no longer tracked once a command installs it again."""

    @pytest.mark.parametrize('profile', ['prof-f', None], ids=['isolated', 'base'])
    def test_kept_while_its_command_fails_and_dropped_once_installed_again(
        self,
        e2e_isolated_home: dict[str, Path],
        configs: Path,
        capsys: pytest.CaptureFixture[str],
        profile: str | None,
    ) -> None:
        home, claude_dir = e2e_isolated_home['home'], e2e_isolated_home['claude_dir']
        skills = (claude_dir / profile if profile else claude_dir) / 'skills'
        both, first_only = _guarded(_recreate('s1', 's2')), _guarded(_recreate('s1'))
        rerun = ['--profile', profile or 'base', *SKIP, '--yes', '--remove-leftovers']
        cfg = write_config(configs, 'env.yaml', _config(['rules/rule.md'], [both]))
        names = ['--command-names', profile] if profile else []
        assert run_main([str(cfg), *SKIP, '--yes', *names]) == 0
        write_config(configs, 'env.yaml', _config(['rules/rule.md'], [first_only]))
        assert run_main(rerun) == 0
        assert _dependency_items(read_manifest(skills.parent)) == ['skills/s2']

        # The command that installed s2 runs again and fails: s2 stays
        write_config(configs, 'env.yaml', _config(['rules/rule.md'], [both]))
        (home / 'fail-marker').write_text('', encoding='utf-8')
        capsys.readouterr()
        assert run_main(rerun) == 1
        assert (skills / 's2' / 'SKILL.md').is_file()
        leftovers = read_manifest(skills.parent)['leftovers']
        assert 'skills/s2' in [item['path'] for item in leftovers['items']]
        assert {'label': 'dependency entry: skills/s2', 'reason': 'kept: its dependency command failed in this run'} in (
            leftovers['kept']
        )
        assert 'dependency entry: skills/s2' not in leftovers['removed']

        # The command runs fine and installs s2 again: no longer a leftover
        (home / 'fail-marker').unlink()
        assert run_main(rerun) == 0
        output = _output(capsys)
        assert (skills / 's2' / 'SKILL.md').is_file()
        manifest = read_manifest(skills.parent)
        assert {'label': 'dependency entry: skills/s2', 'reason': 'recreated'} in manifest['leftovers']['dropped']
        assert 'skills/s2' not in _dependency_items(manifest)
        # The command is recorded as the run spells it, re-rooted into the profile
        (command, entries), = _commands(manifest).items()
        assert entries == ['skills/s1', 'skills/s2']
        assert f'dependency entry: {skills / "s2"} (from: {command}) (installed again by a dependency command)' in output
