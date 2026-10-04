"""E2E tests for linked profiles: --link-dirs, --link-from and their twins.

An isolated profile takes entries of its directory through a directory link
(a junction on Windows, a symlink elsewhere) from the profile --link-from
names. Content entries link only between installs of one configuration and
make the profile apply its source's resolved-config.yaml; projects links to
any source. Step 3 creates every link before any content step, repairs a
stale one, converts a real directory only under a typed value (moving it
aside, never deleting it), and leaves a link no value declares alone. The
tests install real local YAML files into an isolated home with the real
link, launcher, wrapper, profile-config and manifest writers; only network
access, the Claude Code binary, MCP registration, OS-level variables and the
Windows PATH registry are replaced.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts import setup_environment
from scripts.setup_environment import LINKABLE_PROFILE_DIRS
from tests.e2e.profile_support import home_state
from tests.e2e.profile_support import read_manifest
from tests.e2e.profile_support import run_main
from tests.e2e.profile_support import wrappers_exist
from tests.e2e.profile_support import write_child_runner
from tests.e2e.profile_support import write_config
from tests.e2e.profile_support import write_legacy_manifest

SKIP = ['--skip-install', '--no-admin']
CONTENT_ENTRIES = [entry for entry in LINKABLE_PROFILE_DIRS if entry != 'projects']
TOPOLOGY_REMEDY = (
    'Install one full profile of the configuration this run was given first (--command-names SOURCE with no link '
    'keys), then link the others from it with --link-from SOURCE'
)


@pytest.fixture
def configs(tmp_path: Path) -> Path:
    """A directory of configurations with the resources they install beside them."""
    directory = tmp_path / 'configs'
    for relative, content in (
        ('agents/core.md', '# core agent\n'),
        ('agents/extra.md', '# extra agent\n'),
        ('commands/cmd.md', '# command\n'),
        ('rules/rule.md', '# rule\n'),
        ('skills/SKILL.md', '---\nname: tool-skill\n---\n# skill\n'),
        ('hooks/hook.py', 'print("hook")\n'),
        ('prompts/prompt.md', '# prompt\n'),
    ):
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    return directory


def _team() -> dict[str, Any]:
    """A configuration with every kind of content entry."""
    return {
        'name': 'Team Like',
        'agents': ['agents/core.md'],
        'slash-commands': ['commands/cmd.md'],
        'rules': ['rules/rule.md'],
        'skills': [{'name': 'tool-skill', 'base': 'skills/', 'files': ['SKILL.md']}],
        'hooks': {
            'files': ['hooks/hook.py'],
            'events': [{'event': 'PostToolUse', 'matcher': 'Edit', 'type': 'command', 'command': 'hook.py'}],
        },
        'command-defaults': {'system-prompt': 'prompts/prompt.md'},
        'user-settings': {'theme': 'dark'},
    }


def _plain(name: str = 'Plain Env') -> dict[str, Any]:
    """A configuration without content, like a shared base configuration."""
    return {'name': name, 'user-settings': {'theme': 'dark'}}


def _components() -> dict[str, Any]:
    """A configuration whose author lets the user pick an optional component."""
    return {
        'name': 'Components Env',
        'agents': ['agents/core.md', 'agents/extra.md'],
        'components': [
            {'name': 'core', 'includes': {'agents': ['agents/core.md']}},
            {'name': 'extra', 'default': False, 'includes': {'agents': ['agents/extra.md']}},
        ],
    }


def _output(capsys: pytest.CaptureFixture[str]) -> str:
    """Everything the run printed, with Windows line endings normalized."""
    captured = capsys.readouterr()
    return (captured.out + captured.err).replace('\r\n', '\n')


def _is_link(path: Path) -> bool:
    """Report whether a path is a junction (Windows) or a symlink (elsewhere)."""
    if sys.platform == 'win32':
        return bool(os.lstat(path).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    return path.is_symlink()


def _links_to(link: Path, target: Path) -> bool:
    """Report whether a link resolves to a directory."""
    return _is_link(link) and os.path.normcase(os.path.realpath(link)) == os.path.normcase(os.path.realpath(target))


def _install_source(configs: Path, name: str = 'team-1') -> Path:
    """Install the configuration as a full isolated profile and return the configuration path."""
    cfg = write_config(configs, 'team.yaml', _team())
    assert run_main([str(cfg), *SKIP, '--yes', '--command-names', name]) == 0
    return cfg


def _install_dependent(cfg: Path, name: str, source: str = 'team-1', dirs: str = 'all') -> None:
    """Install the configuration as a profile linking entries from a source."""
    assert run_main([str(cfg), *SKIP, '--yes', '--command-names', name, '--link-dirs', dirs, '--link-from', source]) == 0


@pytest.mark.usefixtures('e2e_isolated_home')
class TestLinkCreation:
    """Step 3 links every requested entry before any content step."""

    def test_all_links_every_entry_from_an_isolated_source(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--link-dirs all --link-from team-1 makes eight links and applies team-1's snapshot."""
        cfg = _install_source(configs)
        claude_dir = e2e_isolated_home['claude_dir']
        source_dir = claude_dir / 'team-1'
        source_command = source_dir / 'commands' / 'cmd.md'
        command_stat_before = (source_command.stat().st_mtime_ns, source_command.read_bytes())
        capsys.readouterr()

        _install_dependent(cfg, 'team-2')

        output = _output(capsys)
        profile_dir = claude_dir / 'team-2'
        for entry in LINKABLE_PROFILE_DIRS:
            assert _links_to(profile_dir / entry, source_dir / entry), entry
            assert (source_dir / entry).is_dir(), entry
            assert not _is_link(source_dir / entry), entry
            if sys.platform == 'win32':
                assert (profile_dir / entry).is_symlink() is False, 'Windows uses a junction, not a symlink'
        assert (profile_dir / 'agents' / 'core.md').is_file(), 'the content is reachable through the link'
        assert (source_dir / 'agents' / 'core.md').is_file()
        assert _links_to(profile_dir / 'commands', source_dir / 'commands')
        linked_command = profile_dir / 'commands' / 'cmd.md'
        assert (linked_command.stat().st_mtime_ns, linked_command.read_bytes()) == command_stat_before, (
            'the slash command is the source file itself, not a fresh download'
        )
        assert (source_command.stat().st_mtime_ns, source_command.read_bytes()) == command_stat_before
        for own in ('config.json', 'manifest.json', 'resolved-config.yaml', 'launch.sh'):
            assert (profile_dir / own).is_file(), own
            assert not _is_link(profile_dir / own), own
        assert wrappers_exist(e2e_isolated_home['local_bin'], 'team-2')
        manifest = read_manifest(profile_dir)
        assert manifest['link'] == {
            'dirs': list(LINKABLE_PROFILE_DIRS), 'source': 'team-1', 'origins': {'dirs': 'cli', 'source': 'cli'},
        }
        assert manifest['config_identity'] == read_manifest(source_dir)['config_identity']
        assert manifest['config_digest'] == read_manifest(source_dir)['config_digest']
        assert 'Links (from profile "team-1"):' in output
        assert '[cli]' in output.split('Links (from profile "team-1"):')[1].split('\n')[0]
        assert f'* skills -> {source_dir / "skills"} [create]' in output
        assert 'Configuration: applied from profile "team-1" (resolved-config.yaml), components as installed there' in output
        for message in (
            'Agents are linked from profile "team-1"; nothing to install',
            'Slash commands are linked from profile "team-1"; nothing to install',
            'Rules are linked from profile "team-1"; nothing to install',
            'Skills are linked from profile "team-1"; nothing to install',
            'The system prompt is linked from profile "team-1"; nothing to install',
            'Hook files are linked from profile "team-1"; nothing to install',
        ):
            assert message in output
        assert f'* Links: {", ".join(LINKABLE_PROFILE_DIRS)} from profile "team-1" [cli]' in output

    def test_projects_links_from_the_base_by_default(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A configuration's link-dirs: [projects] links the sessions directory to the base ~/.claude/projects."""
        cfg = write_config(configs, 'personal.yaml', {**_plain(), 'link-dirs': ['projects']})
        claude_dir = e2e_isolated_home['claude_dir']
        capsys.readouterr()

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'claude-alt']) == 0

        output = _output(capsys)
        profile_dir = claude_dir / 'claude-alt'
        assert _links_to(profile_dir / 'projects', claude_dir / 'projects')
        assert (claude_dir / 'projects').is_dir()
        assert not any((profile_dir / entry).exists() for entry in CONTENT_ENTRIES), 'only projects is linked'
        assert read_manifest(profile_dir)['link'] == {
            'dirs': ['projects'], 'source': 'base', 'origins': {'dirs': 'yaml', 'source': 'default'},
        }
        assert 'Links (from profile "base"):' in output
        assert '[yaml]' in output.split('Links (from profile "base"):')[1].split('\n')[0]
        assert 'Configuration: applied from profile' not in output, 'a projects-only link keeps its own configuration'

    def test_configuration_link_keys_install_a_dependent_marked_yaml(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """link-dirs: [all] with link-from: team-1 in the YAML links every entry, each value marked [yaml]."""
        cfg = _install_source(configs)
        write_config(configs, 'team.yaml', {**_team(), 'link-dirs': ['all'], 'link-from': 'team-1'})
        claude_dir = e2e_isolated_home['claude_dir']
        capsys.readouterr()

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-2']) == 0

        output = _output(capsys)
        for entry in LINKABLE_PROFILE_DIRS:
            assert _links_to(claude_dir / 'team-2' / entry, claude_dir / 'team-1' / entry), entry
        assert '[yaml]' in output.split('Links (from profile "team-1"):')[1].split('\n')[0]
        assert f'* Links: {", ".join(LINKABLE_PROFILE_DIRS)} from profile "team-1" [yaml]' in output
        manifest = read_manifest(claude_dir / 'team-2')
        assert manifest['link'] == {
            'dirs': list(LINKABLE_PROFILE_DIRS), 'source': 'team-1', 'origins': {'dirs': 'yaml', 'source': 'yaml'},
        }
        assert manifest['yaml_values']['link_dirs'] == list(LINKABLE_PROFILE_DIRS)
        assert manifest['yaml_values']['link_from'] == 'team-1'
        assert manifest['config_digest'] == read_manifest(claude_dir / 'team-1')['config_digest']

    def test_non_string_configuration_link_from_is_refused(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A link-from that is not a profile name stops the run before any write."""
        cfg = write_config(configs, 'personal.yaml', {**_plain(), 'link-dirs': ['projects'], 'link-from': 5})
        capsys.readouterr()

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'p1']) == 1

        assert 'Invalid link-from value: expected a profile name, got int' in _output(capsys)
        assert not (e2e_isolated_home['claude_dir'] / 'p1').exists()

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows junction behavior')
    def test_windows_falls_back_to_mklink_when_createjunction_fails(
        self, e2e_isolated_home: dict[str, Path], configs: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When _winapi.CreateJunction raises, the link is still made with mklink /J."""
        import _winapi

        cfg = _install_source(configs)
        claude_dir = e2e_isolated_home['claude_dir']

        def _raise_create_junction(_src: str, _dst: str) -> None:
            raise OSError('simulated CreateJunction failure')

        monkeypatch.setattr(_winapi, 'CreateJunction', _raise_create_junction)
        _install_dependent(cfg, 'team-2', dirs='projects')

        assert _links_to(claude_dir / 'team-2' / 'projects', claude_dir / 'team-1' / 'projects')

    def test_fatal_link_failure_exits_1_before_the_profile_is_written(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A link that cannot be made stops the run with exit code 1 and no manifest or wrappers."""
        cfg = _install_source(configs)
        claude_dir = e2e_isolated_home['claude_dir']

        def _refuse(_link_path: Path, _target: Path) -> None:
            raise OSError('simulated link failure')

        with patch.object(setup_environment, 'link_profile_directory', side_effect=_refuse):
            code = run_main([
                str(cfg), *SKIP, '--yes', '--command-names', 'team-2', '--link-dirs', 'all', '--link-from', 'team-1',
            ])

        assert code == 1
        output = _output(capsys)
        assert 'Linking the profile directories failed: simulated link failure' in output
        assert not (claude_dir / 'team-2' / 'manifest.json').exists()
        assert not wrappers_exist(e2e_isolated_home['local_bin'], 'team-2')


@pytest.mark.usefixtures('e2e_isolated_home')
class TestRerunsAndRepairs:
    """A re-run keeps, repairs or converts links as the value asking for them allows."""

    def test_rerun_keeps_every_link_and_remembers_the_typed_value(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--profile NAME keeps the links a typed value made, marked [remembered]."""
        cfg = _install_source(configs)
        _install_dependent(cfg, 'team-2')
        claude_dir = e2e_isolated_home['claude_dir']
        capsys.readouterr()

        assert run_main(['--profile', 'team-2', *SKIP, '--yes']) == 0

        output = _output(capsys)
        assert 'Links (from profile "team-1"):' in output
        assert '[remembered]' in output.split('Links (from profile "team-1"):')[1].split('\n')[0]
        assert f'* agents -> {claude_dir / "team-1" / "agents"} [kept]' in output
        for entry in LINKABLE_PROFILE_DIRS:
            assert _links_to(claude_dir / 'team-2' / entry, claude_dir / 'team-1' / entry), entry
        manifest = read_manifest(claude_dir / 'team-2')
        assert manifest['link']['origins'] == {'dirs': 'cli', 'source': 'cli'}

    def test_stale_link_is_repaired(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A link pointing elsewhere is re-pointed at the source under a remembered value."""
        cfg = _install_source(configs)
        _install_dependent(cfg, 'team-2')
        claude_dir = e2e_isolated_home['claude_dir']
        skills = claude_dir / 'team-2' / 'skills'
        elsewhere = tmp_path / 'elsewhere'
        elsewhere.mkdir()
        setup_environment._remove_directory_link(skills)
        setup_environment.link_profile_directory(skills, elsewhere)
        capsys.readouterr()

        assert run_main(['--profile', 'team-2', *SKIP, '--yes']) == 0

        output = _output(capsys)
        assert f'* skills -> {claude_dir / "team-1" / "skills"} [repair: the link points elsewhere]' in output
        assert _links_to(skills, claude_dir / 'team-1' / 'skills')
        assert elsewhere.is_dir(), 'repairing a link never touches its old target'

    def test_remembered_value_never_converts_a_real_directory(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A real non-empty directory under a remembered value stops the run, naming the typed value that converts it."""
        cfg = _install_source(configs)
        _install_dependent(cfg, 'team-2')
        claude_dir = e2e_isolated_home['claude_dir']
        agents = claude_dir / 'team-2' / 'agents'
        setup_environment._remove_directory_link(agents)
        agents.mkdir()
        (agents / 'local.md').write_text('# local\n', encoding='utf-8')
        capsys.readouterr()

        assert run_main(['--profile', 'team-2', *SKIP, '--yes']) == 1

        output = _output(capsys)
        assert f'{agents} is a real directory with 1 item(s), and only a typed value converts it' in output
        assert f'pass --link-dirs {",".join(LINKABLE_PROFILE_DIRS)}' in output
        assert (agents / 'local.md').is_file(), 'nothing was moved or removed'

    def test_remembered_typed_value_overrides_a_changed_configuration_value_with_a_warning(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A projects link typed at install time is kept when the YAML later asks for all, and the run says so."""
        cfg = write_config(configs, 'personal.yaml', {**_team(), 'link-dirs': ['projects']})
        claude_dir = e2e_isolated_home['claude_dir']
        assert run_main([
            str(cfg), *SKIP, '--yes', '--command-names', 'p2', '--link-dirs', 'projects', '--link-from', 'base',
        ]) == 0
        assert read_manifest(claude_dir / 'p2')['link']['origins'] == {'dirs': 'cli', 'source': 'cli'}
        write_config(configs, 'personal.yaml', {**_team(), 'link-dirs': ['all']})
        capsys.readouterr()

        assert run_main(['--profile', 'p2', *SKIP, '--yes']) == 0

        output = _output(capsys)
        assert (
            "link-dirs: using the remembered value projects [remembered]; the configuration's link-dirs changed from "
            f'projects to {", ".join(LINKABLE_PROFILE_DIRS)} since the profile was installed. Pass --link-dirs to '
            'replace the remembered value.'
        ) in output
        assert _links_to(claude_dir / 'p2' / 'projects', claude_dir / 'projects')
        for entry in CONTENT_ENTRIES:
            assert not ((claude_dir / 'p2' / entry).exists() and _is_link(claude_dir / 'p2' / entry)), entry
        assert (claude_dir / 'p2' / 'agents' / 'core.md').is_file(), 'the profile keeps installing its own content'
        assert read_manifest(claude_dir / 'p2')['link'] == {
            'dirs': ['projects'], 'source': 'base', 'origins': {'dirs': 'cli', 'source': 'cli'},
        }

    def test_configuration_value_never_converts_a_real_projects_directory(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A YAML that gains link-dirs: [projects] stops the re-run of a profile whose projects/ holds sessions."""
        cfg = write_config(configs, 'personal.yaml', _plain())
        claude_dir = e2e_isolated_home['claude_dir']
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'claude-alt']) == 0
        projects = claude_dir / 'claude-alt' / 'projects'
        projects.mkdir()
        (projects / 'session.jsonl').write_text('{}\n', encoding='utf-8')
        write_config(configs, 'personal.yaml', {**_plain(), 'link-dirs': ['projects']})
        before = home_state(e2e_isolated_home['home'])
        capsys.readouterr()

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'claude-alt']) == 1

        output = _output(capsys)
        assert f'{projects} is a real directory with 1 item(s), and only a typed value converts it' in output
        assert 'pass --link-dirs projects' in output
        assert (projects / 'session.jsonl').is_file()
        assert not _is_link(projects)
        assert not list((claude_dir / 'claude-alt').glob('projects.unlinked-*'))
        assert home_state(e2e_isolated_home['home']) == before, 'the refused run changed nothing'

    def test_empty_real_directory_is_replaced_under_any_value(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """An empty real directory holds nothing to lose, so a remembered value links it again."""
        cfg = _install_source(configs)
        _install_dependent(cfg, 'team-2')
        claude_dir = e2e_isolated_home['claude_dir']
        agents = claude_dir / 'team-2' / 'agents'
        setup_environment._remove_directory_link(agents)
        agents.mkdir()
        capsys.readouterr()

        assert run_main(['--profile', 'team-2', *SKIP, '--yes']) == 0

        assert f'* agents -> {claude_dir / "team-1" / "agents"} [create]' in _output(capsys)
        assert _links_to(agents, claude_dir / 'team-1' / 'agents')


@pytest.mark.usefixtures('e2e_isolated_home')
class TestConversions:
    """A typed value converts a profile in both directions, naming every directory it moves aside."""

    def test_typed_all_moves_real_directories_aside_after_listing_them(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The summary and --dry-run list each moved directory with its path and item count; the run moves them."""
        _install_source(configs)
        _install_source(configs, 'team-lab')
        claude_dir = e2e_isolated_home['claude_dir']
        lab = claude_dir / 'team-lab'
        (lab / 'projects').mkdir()
        (lab / 'projects' / 'session.jsonl').write_text('{}\n', encoding='utf-8')
        (lab / 'projects' / 'memory').mkdir()
        before = home_state(e2e_isolated_home['home'])
        capsys.readouterr()

        assert run_main(['--profile', 'team-lab', '--link-dirs', 'all', '--link-from', 'team-1', *SKIP, '--dry-run']) == 0

        output = _output(capsys)
        stamp = output.split('agents.unlinked-')[1].split('\n')[0].strip()
        assert output.count('[MOVE ASIDE]') == 7, 'agents, commands, rules, skills, hooks, prompts and projects are listed'
        assert f'agents: {lab / "agents"} (1 item) -> {lab / f"agents.unlinked-{stamp}"}' in output
        assert (
            f'projects: {lab / "projects"} (2 items) -> {lab / f"projects.unlinked-{stamp}"}; '
            'those sessions and auto-memory stop appearing in this profile'
        ) in output
        assert f'* agents -> {claude_dir / "team-1" / "agents"} [create after moving the real directory aside]' in output
        assert home_state(e2e_isolated_home['home']) == before, 'a dry run changes nothing'
        capsys.readouterr()

        assert run_main(['--profile', 'team-lab', '--link-dirs', 'all', '--link-from', 'team-1', *SKIP, '--yes']) == 0

        output = _output(capsys)
        moved = sorted(entry.name.split('.unlinked-')[0] for entry in lab.iterdir() if '.unlinked-' in entry.name)
        assert moved == ['agents', 'commands', 'hooks', 'projects', 'prompts', 'rules', 'skills']
        agents_aside = next(entry for entry in lab.iterdir() if entry.name.startswith('agents.unlinked-'))
        assert (agents_aside / 'core.md').is_file(), 'the moved directory keeps its content'
        projects_aside = next(entry for entry in lab.iterdir() if entry.name.startswith('projects.unlinked-'))
        assert (projects_aside / 'session.jsonl').is_file()
        for entry in LINKABLE_PROFILE_DIRS:
            assert _links_to(lab / entry, claude_dir / 'team-1' / entry), entry
        assert f'Moved {lab / "agents"} aside to' in output
        assert read_manifest(lab)['link']['source'] == 'team-1'

    def test_typed_none_removes_the_links_and_refills_the_directories(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--link-dirs none removes every link, and the run installs the real directories again."""
        cfg = _install_source(configs)
        _install_dependent(cfg, 'team-2')
        claude_dir = e2e_isolated_home['claude_dir']
        profile_dir = claude_dir / 'team-2'
        capsys.readouterr()

        assert run_main(['--profile', 'team-2', '--link-dirs', 'none', *SKIP, '--yes']) == 0

        output = _output(capsys)
        assert '* agents: [unlink] the link is removed; this run installs the real directory' in output
        for entry in ('agents', 'commands', 'rules', 'skills', 'hooks', 'prompts'):
            assert (profile_dir / entry).is_dir(), entry
            assert not _is_link(profile_dir / entry), entry
        assert (profile_dir / 'agents' / 'core.md').is_file()
        assert (profile_dir / 'commands' / 'cmd.md').is_file()
        assert (profile_dir / 'skills' / 'tool-skill' / 'SKILL.md').is_file()
        assert (claude_dir / 'team-1' / 'agents' / 'core.md').is_file(), 'unlinking never touches the source'
        assert read_manifest(profile_dir)['link'] == {
            'dirs': [], 'source': 'team-1', 'origins': {'dirs': 'cli', 'source': 'cli'},
        }, 'the typed none is recorded like any typed value'
        capsys.readouterr()

        assert run_main(['--profile', 'team-2', *SKIP, '--yes']) == 0, 'the unlinked profile re-runs as a full install'

        assert 'Links' not in _output(capsys).split('Installation Summary')[1].split('Machine-wide')[0]
        assert not _is_link(profile_dir / 'agents')

    def test_typed_projects_only_converts_a_full_dependent_into_a_partial_one(
        self, e2e_isolated_home: dict[str, Path], configs: Path,
    ) -> None:
        """A shorter typed list removes the links it leaves out and keeps the rest."""
        cfg = _install_source(configs)
        _install_dependent(cfg, 'team-2')
        claude_dir = e2e_isolated_home['claude_dir']
        profile_dir = claude_dir / 'team-2'

        assert run_main([
            str(cfg), *SKIP, '--yes', '--command-names', 'team-2', '--link-dirs', 'projects', '--link-from', 'team-1',
        ]) == 0

        assert _links_to(profile_dir / 'projects', claude_dir / 'team-1' / 'projects')
        assert (profile_dir / 'agents').is_dir()
        assert not _is_link(profile_dir / 'agents')
        assert (profile_dir / 'agents' / 'core.md').is_file()
        assert read_manifest(profile_dir)['link'] == {
            'dirs': ['projects'], 'source': 'team-1', 'origins': {'dirs': 'cli', 'source': 'cli'},
        }


@pytest.mark.usefixtures('e2e_isolated_home')
class TestRememberedNone:
    """A typed or environment none is remembered like any typed value, ahead of the configuration's link-dirs."""

    def test_convert_back_holds_across_plain_reruns_and_profile_all(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capfd: pytest.CaptureFixture[str],
    ) -> None:
        """After --link-dirs none, a profile whose YAML declares link-dirs: [projects] stays unlinked with its sessions."""
        cfg = write_config(configs, 'personal.yaml', {**_plain(), 'link-dirs': ['projects']})
        claude_dir = e2e_isolated_home['claude_dir']
        profile_dir = claude_dir / 'claude-alt'
        projects = profile_dir / 'projects'
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'claude-alt']) == 0
        assert _links_to(projects, claude_dir / 'projects')
        capfd.readouterr()

        assert run_main(['--profile', 'claude-alt', '--link-dirs', 'none', *SKIP, '--yes']) == 0

        output = _run_output(capfd)
        assert '* projects: [unlink] the link is removed' in output
        assert "Links: none [cli] (the configuration's link-dirs [projects] is not applied)" in output
        assert not projects.exists() or not _is_link(projects)
        assert read_manifest(profile_dir)['link'] == {
            'dirs': [], 'source': 'base', 'origins': {'dirs': 'cli', 'source': 'default'},
        }
        projects.mkdir(exist_ok=True)
        (projects / 'session.jsonl').write_text('{}\n', encoding='utf-8')
        capfd.readouterr()

        assert run_main(['--profile', 'claude-alt', *SKIP, '--yes']) == 0, 'the remembered none beats the YAML'

        output = _run_output(capfd)
        assert (
            "Links: none [remembered] (the configuration's link-dirs [projects] is not applied; pass --link-dirs to "
            'replace the remembered value)'
        ) in output
        assert 'is a real directory with' not in output
        assert (projects / 'session.jsonl').is_file()
        assert not _is_link(projects)
        assert read_manifest(profile_dir)['link'] == {
            'dirs': [], 'source': 'base', 'origins': {'dirs': 'cli', 'source': 'default'},
        }, 'the re-run records the remembered none again'
        runner = write_child_runner(tmp_path, monkeypatch)
        capfd.readouterr()

        code = run_main(['--profile', 'all', *SKIP, '--yes'], argv0=str(runner))

        output = _run_output(capfd)
        assert code == 0, output
        assert '=== Profile claude-alt ===' in output
        assert '* claude-alt: ok' in output
        assert (projects / 'session.jsonl').is_file()
        assert not _is_link(projects)

    def test_source_installed_with_none_under_its_own_link_keys_reruns_and_refreshes_its_dependents(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capfd: pytest.CaptureFixture[str],
    ) -> None:
        """A source installed with --link-dirs none under its own YAML link keys re-runs without the flag."""
        cfg = write_config(configs, 'team.yaml', {**_team(), 'link-dirs': ['all'], 'link-from': 'team-1'})
        claude_dir = e2e_isolated_home['claude_dir']
        source_dir = claude_dir / 'team-1'
        capfd.readouterr()

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1', '--link-dirs', 'none']) == 0

        output = _run_output(capfd)
        assert (
            f"Links: none [cli] (the configuration's link-dirs [{', '.join(LINKABLE_PROFILE_DIRS)}] is not applied)"
        ) in output
        assert read_manifest(source_dir)['link'] == {
            'dirs': [], 'source': 'team-1', 'origins': {'dirs': 'cli', 'source': 'yaml'},
        }
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-2']) == 0, 'the YAML keys install a dependent'
        assert _links_to(claude_dir / 'team-2' / 'agents', source_dir / 'agents')
        dependent_before = _installed_at(claude_dir / 'team-2')
        runner = write_child_runner(tmp_path, monkeypatch)
        capfd.readouterr()

        code = run_main(['--profile', 'team-1', *SKIP, '--yes'], argv0=str(runner))

        output = _run_output(capfd)
        assert code == 0, output
        assert 'cannot link from itself' not in output
        assert (
            f"Links: none [remembered] (the configuration's link-dirs [{', '.join(LINKABLE_PROFILE_DIRS)}] is not "
            'applied; pass --link-dirs to replace the remembered value)'
        ) in output
        assert 'Step 23: Refreshing 1 dependent profile(s): team-2...' in output
        assert '- team-2: ok' in output
        assert _installed_at(claude_dir / 'team-2') != dependent_before
        for entry in CONTENT_ENTRIES:
            assert (source_dir / entry).is_dir(), entry
            assert not _is_link(source_dir / entry), entry
        assert _links_to(claude_dir / 'team-2' / 'agents', source_dir / 'agents')
        capfd.readouterr()

        code = run_main(['--profile', 'all', *SKIP, '--yes'], argv0=str(runner))

        output = _run_output(capfd)
        assert code == 0, output
        assert output.index('=== Profile team-1 ===') < output.index('=== Profile team-2 ===')
        assert '* team-1: ok' in output
        assert '* team-2: ok' in output
        assert not _is_link(source_dir / 'agents')

    def test_environment_none_is_remembered_and_warns_when_the_configuration_changes(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """CLAUDE_CODE_TOOLBOX_LINK_DIRS=none is recorded with its origin, remembered, and named when the YAML changes."""
        cfg = write_config(configs, 'personal.yaml', {**_plain(), 'link-dirs': ['projects']})
        claude_dir = e2e_isolated_home['claude_dir']
        profile_dir = claude_dir / 'p1'
        capsys.readouterr()

        with patch.dict(os.environ, {'CLAUDE_CODE_TOOLBOX_LINK_DIRS': 'none'}):
            assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'p1']) == 0

        output = _output(capsys)
        assert "Links: none [env] (the configuration's link-dirs [projects] is not applied)" in output
        assert not (profile_dir / 'projects').exists()
        assert read_manifest(profile_dir)['link'] == {
            'dirs': [], 'source': 'base', 'origins': {'dirs': 'env', 'source': 'default'},
        }
        write_config(configs, 'personal.yaml', {**_plain(), 'link-dirs': ['all']})
        capsys.readouterr()

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'p1']) == 0

        output = _output(capsys)
        assert (
            "link-dirs: using the remembered value none [remembered]; the configuration's link-dirs changed from "
            f'projects to {", ".join(LINKABLE_PROFILE_DIRS)} since the profile was installed. Pass --link-dirs to '
            'replace the remembered value.'
        ) in output
        assert "Links: none [remembered] (the configuration's link-dirs" in output
        assert not any(_is_link(profile_dir / entry) for entry in LINKABLE_PROFILE_DIRS if (profile_dir / entry).exists())
        assert read_manifest(profile_dir)['link']['origins'] == {'dirs': 'env', 'source': 'default'}

    def test_configuration_none_is_not_remembered(
        self, e2e_isolated_home: dict[str, Path], configs: Path,
    ) -> None:
        """A YAML link-dirs: [none] is re-read on every run, so the manifest records no link."""
        cfg = write_config(configs, 'personal.yaml', {**_plain(), 'link-dirs': ['none']})
        claude_dir = e2e_isolated_home['claude_dir']
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'p1']) == 0
        assert read_manifest(claude_dir / 'p1')['link'] is None
        write_config(configs, 'personal.yaml', {**_plain(), 'link-dirs': ['projects']})

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'p1']) == 0

        assert _links_to(claude_dir / 'p1' / 'projects', claude_dir / 'projects'), 'the configuration value applies'
        assert read_manifest(claude_dir / 'p1')['link']['origins'] == {'dirs': 'yaml', 'source': 'default'}


@pytest.mark.usefixtures('e2e_isolated_home')
class TestUndeclaredLinks:
    """A link on disk that no value asks for is reported and left alone."""

    def test_link_no_value_declares_is_shown_and_kept(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """[on disk, not declared] names the link, and the run neither removes nor records it."""
        cfg = write_config(configs, 'plain.yaml', _plain())
        claude_dir = e2e_isolated_home['claude_dir']
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'p1']) == 0
        projects = claude_dir / 'p1' / 'projects'
        setup_environment.link_profile_directory(projects, claude_dir / 'projects')
        capsys.readouterr()

        assert run_main(['--profile', 'p1', *SKIP, '--yes']) == 0

        output = _output(capsys)
        assert '* projects: [on disk, not declared] the link is left alone' in output
        assert _links_to(projects, claude_dir / 'projects')
        assert read_manifest(claude_dir / 'p1')['link'] is None

    def test_legacy_projects_junction_counts_as_the_projects_link(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A projects link an earlier install created is kept under --link-dirs projects."""
        cfg = write_config(configs, 'plain.yaml', _plain())
        claude_dir = e2e_isolated_home['claude_dir']
        profile_dir = claude_dir / 'legacy-1'
        profile_dir.mkdir()
        setup_environment.link_profile_directory(profile_dir / 'projects', claude_dir / 'projects')
        write_legacy_manifest(
            profile_dir, 'legacy-1', ['legacy-1'],
            config_source=str(cfg.resolve()), config_source_type='local', config_source_url=None,
        )
        capsys.readouterr()

        assert run_main(['--profile', 'legacy-1', '--link-dirs', 'projects', *SKIP, '--yes']) == 0

        assert f'* projects -> {claude_dir / "projects"} [kept]' in _output(capsys)
        assert read_manifest(profile_dir)['link'] == {
            'dirs': ['projects'], 'source': 'base', 'origins': {'dirs': 'cli', 'source': 'default'},
        }


@pytest.mark.usefixtures('e2e_isolated_home')
class TestLinkRules:
    """Every rule is checked before any write, each refusal naming its remedy."""

    def test_links_need_an_isolated_profile(self, configs: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """The base profile cannot link; the remedy is --command-names."""
        cfg = write_config(configs, 'plain.yaml', _plain())

        assert run_main([str(cfg), *SKIP, '--yes', '--link-dirs', 'projects']) == 1

        output = _output(capsys)
        assert 'link-dirs projects needs an isolated profile: pass --command-names NAME' in output

    def test_content_links_need_the_same_configuration(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A content link from a profile of another configuration is refused before any write."""
        _install_source(configs)
        other = write_config(configs, 'other.yaml', _plain('Other'))
        claude_dir = e2e_isolated_home['claude_dir']

        assert run_main([
            str(other), *SKIP, '--yes', '--command-names', 'x1', '--link-dirs', 'all', '--link-from', 'team-1',
        ]) == 1

        output = _output(capsys)
        assert (
            'Content entries (skills, agents, commands, rules, hooks, output-styles, prompts) link only between '
            'installs of one configuration'
        ) in output
        assert 'profile "team-1" was installed from' in output
        assert TOPOLOGY_REMEDY in output
        assert 'or link only projects' in output
        assert not (claude_dir / 'x1').exists()

    def test_content_links_to_a_base_of_another_configuration_name_the_working_topology(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Beside a corporate base, team.yaml with --link-dirs all is refused with the full-profile-first remedy."""
        corp = write_config(configs, 'team-corp.yaml', {**_team(), 'name': 'Corp'})
        assert run_main([str(corp), *SKIP, '--yes']) == 0
        cfg = write_config(configs, 'team.yaml', _team())
        claude_dir = e2e_isolated_home['claude_dir']
        capsys.readouterr()

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-2', '--link-dirs', 'all']) == 1

        output = _output(capsys)
        assert f'profile "base" was installed from {corp.resolve()}' in output
        assert TOPOLOGY_REMEDY in output
        assert not (claude_dir / 'team-2').exists()
        capsys.readouterr()

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0, 'the remedy: a full profile first'
        _install_dependent(cfg, 'team-2')

        assert _links_to(claude_dir / 'team-2' / 'agents', claude_dir / 'team-1' / 'agents')

    def test_chain_is_refused_with_the_source_as_the_remedy(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A content link from a profile that links content itself names that profile's source."""
        cfg = _install_source(configs)
        _install_dependent(cfg, 'team-2')
        claude_dir = e2e_isolated_home['claude_dir']
        capsys.readouterr()

        assert run_main([
            str(cfg), *SKIP, '--yes', '--command-names', 'team-3', '--link-dirs', 'all', '--link-from', 'team-2',
        ]) == 1

        output = _output(capsys)
        assert 'Profile "team-2" links content from profile "team-1" itself' in output
        assert 'use --link-from team-1' in output
        assert not (claude_dir / 'team-3').exists()

    def test_partially_linked_source_is_refused(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A profile that links one content entry is no source for any content entry."""
        cfg = _install_source(configs)
        _install_dependent(cfg, 'team-lab', dirs='skills,projects')
        capsys.readouterr()

        assert run_main([
            str(cfg), *SKIP, '--yes', '--command-names', 'team-lab2', '--link-dirs', 'hooks', '--link-from', 'team-lab',
        ]) == 1

        output = _output(capsys)
        assert 'Profile "team-lab" links content from profile "team-1" itself' in output
        assert 'use --link-from team-1' in output
        assert not (e2e_isolated_home['claude_dir'] / 'team-lab2').exists()

    def test_projects_links_to_any_source_without_a_manifest(
        self, e2e_isolated_home: dict[str, Path], configs: Path,
    ) -> None:
        """projects links to a bare directory under ~/.claude and to a profile of another configuration."""
        cfg = write_config(configs, 'plain.yaml', _plain())
        other = write_config(configs, 'other.yaml', _plain('Other'))
        claude_dir = e2e_isolated_home['claude_dir']
        (claude_dir / 'bare' / 'projects').mkdir(parents=True)
        assert run_main([str(other), *SKIP, '--yes', '--command-names', 'corp']) == 0

        assert run_main([
            str(cfg), *SKIP, '--yes', '--command-names', 'p1', '--link-dirs', 'projects', '--link-from', 'bare',
        ]) == 0
        assert run_main([
            str(cfg), *SKIP, '--yes', '--command-names', 'p2', '--link-dirs', 'projects', '--link-from', 'corp',
        ]) == 0

        assert _links_to(claude_dir / 'p1' / 'projects', claude_dir / 'bare' / 'projects')
        assert _links_to(claude_dir / 'p2' / 'projects', claude_dir / 'corp' / 'projects')

    def test_projects_link_targets_the_final_real_directory(
        self, e2e_isolated_home: dict[str, Path], configs: Path,
    ) -> None:
        """A profile linking all from a projects-only source gets its content there and its sessions at the base."""
        cfg = write_config(configs, 'personal.yaml', {**_team(), 'link-dirs': ['projects']})
        claude_dir = e2e_isolated_home['claude_dir']
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'claude-alt']) == 0
        assert _links_to(claude_dir / 'claude-alt' / 'projects', claude_dir / 'projects')

        _install_dependent(cfg, 'claude-p2', source='claude-alt')

        p2 = claude_dir / 'claude-p2'
        assert _links_to(p2 / 'projects', claude_dir / 'projects')
        recorded_target = setup_environment._strip_extended_path_prefix(os.readlink(p2 / 'projects'))
        base_projects = os.path.normcase(os.path.realpath(claude_dir / 'projects'))
        assert os.path.normcase(os.path.realpath(recorded_target)) == base_projects, (
            'the link points at the real directory, not at the source link'
        )
        for entry in CONTENT_ENTRIES:
            assert _links_to(p2 / entry, claude_dir / 'claude-alt' / entry), entry
        assert (p2 / 'agents' / 'core.md').is_file()

    def test_content_links_refuse_selector_flags_and_take_the_source_selection(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--select, --with and --without are refused, and the dependent gets the source's components."""
        cfg = write_config(configs, 'components.yaml', _components())
        claude_dir = e2e_isolated_home['claude_dir']
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1', '--with', 'extra']) == 0
        capsys.readouterr()

        link_argv = [str(cfg), *SKIP, '--yes', '--command-names', 'team-2', '--link-dirs', 'all', '--link-from', 'team-1']
        assert run_main([*link_argv, '--with', 'extra']) == 1
        output = _output(capsys)
        assert 'takes the component selection of profile "team-1"; drop --select, --with and --without' in output
        with patch.dict(os.environ, {'CLAUDE_CODE_TOOLBOX_SELECT': 'all'}):
            assert run_main(link_argv) == 1
        assert not (claude_dir / 'team-2').exists()
        capsys.readouterr()

        _install_dependent(cfg, 'team-2')

        output = _output(capsys)
        assert (claude_dir / 'team-2' / 'agents' / 'extra.md').is_file(), 'the source selected the extra component'
        assert 'components as installed there' in output
        assert 'Components:' not in output.split('Installation Summary')[1]
        manifest = read_manifest(claude_dir / 'team-2')
        assert manifest['components'] is None
        assert manifest['origins']['components'] == 'yaml'

    def test_projects_only_link_keeps_its_own_selection(
        self, e2e_isolated_home: dict[str, Path], configs: Path,
    ) -> None:
        """A profile that links only projects picks its own components."""
        cfg = write_config(configs, 'components.yaml', _components())
        claude_dir = e2e_isolated_home['claude_dir']

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'p1', '--link-dirs', 'projects', '--with', 'extra']) == 0

        assert (claude_dir / 'p1' / 'agents' / 'extra.md').is_file()
        assert read_manifest(claude_dir / 'p1')['components'] == {'select': None, 'with': 'extra', 'without': None}

    def test_source_with_dependents_refuses_link_and_configuration_changes(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A profile others link content from keeps its links and configuration until they are re-pointed or unlinked."""
        cfg = _install_source(configs)
        _install_dependent(cfg, 'team-2')
        _install_dependent(cfg, 'team-3')
        other = write_config(configs, 'other.yaml', _plain('Other'))
        runner = write_child_runner(tmp_path, monkeypatch)
        capsys.readouterr()

        assert run_main(['--profile', 'team-1', '--link-dirs', 'projects', *SKIP, '--yes']) == 1
        output = _output(capsys)
        assert 'Profile "team-1" is the link source of team-2, team-3' in output
        assert (
            '--profile team-2 --link-from <other profile>   (re-point), or --profile team-2 --link-dirs none   (unlink)'
        ) in output
        assert '--profile team-3 --link-from <other profile>' in output

        assert run_main([str(other), *SKIP, '--yes', '--command-names', 'team-1', '--switch-config']) == 1
        assert 'Profile "team-1" is the link source of team-2, team-3' in _output(capsys)

        assert run_main(['--profile', 'team-1', *SKIP, '--yes'], argv0=str(runner)) == 0, (
            'an unchanged re-run of the source proceeds and refreshes the dependents'
        )
        assert run_main(['--profile', 'team-2', '--link-dirs', 'none', *SKIP, '--yes']) == 0
        assert run_main(['--profile', 'team-3', '--link-dirs', 'none', *SKIP, '--yes']) == 0
        capsys.readouterr()

        assert run_main(['--profile', 'team-1', '--link-dirs', 'projects', *SKIP, '--yes']) == 0

        claude_dir = e2e_isolated_home['claude_dir']
        assert _links_to(claude_dir / 'team-1' / 'projects', claude_dir / 'projects')

    @pytest.mark.parametrize(
        ('argv', 'message'),
        [
            (['--link-from', 'team-1'], 'names the profile "team-1", but no entry is linked'),
            (['--link-dirs', 'settings'], 'names unknown entries: settings'),
            (['--link-dirs', 'all,skills'], '"all" stands alone'),
            (['--link-dirs', 'all', '--link-from', 'team-2'], 'Profile "team-2" cannot link from itself'),
            (['--link-dirs', 'all', '--link-from', 'nobody'], 'no profile of that name is installed'),
            (['--link-dirs', 'projects', '--link-from', 'nobody'], 'no profile of that name is installed'),
        ],
    )
    def test_malformed_requests_are_refused(
        self, argv: list[str], message: str, e2e_isolated_home: dict[str, Path], configs: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """An empty link, an unknown entry, a sentinel beside an entry, a self link and an unknown source are refused."""
        cfg = _install_source(configs)
        capsys.readouterr()

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-2', *argv]) == 1

        assert message in _output(capsys)
        assert not (e2e_isolated_home['claude_dir'] / 'team-2').exists()

    def test_typed_configuration_for_a_dependent_is_an_identity_check_only(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A dependent re-run with a configuration never loads it: a matching one proceeds, another one is refused."""
        cfg = _install_source(configs)
        _install_dependent(cfg, 'team-2')
        other = write_config(configs, 'other.yaml', _plain('Other'))
        capsys.readouterr()

        with patch.object(setup_environment, 'load_config_from_source') as load:
            assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-2']) == 0
            assert run_main(['--profile', 'team-2', *SKIP, '--yes']) == 0
            assert run_main([str(other), *SKIP, '--yes', '--command-names', 'team-2']) == 1
        load.assert_not_called()
        output = _output(capsys)
        assert 'link only between installs of one configuration' in output
        assert (
            'Pass --link-dirs none, or --link-from naming a profile installed from the configuration this run was '
            'given, so profile "team-2" stops following "team-1"'
        ) in output
        assert TOPOLOGY_REMEDY not in output, 'a profile that already follows a source is re-pointed or unlinked instead'
        assert 'Profile "team-2" was installed from' not in output, 'the identity check runs before the switch guard'
        assert (e2e_isolated_home['claude_dir'] / 'team-2' / 'manifest.json').is_file()


@pytest.mark.usefixtures('e2e_isolated_home')
class TestConfigurationSwitch:
    """A --switch-config run removes only what the profile holds itself, never what it sees through a link."""

    def test_switching_dependents_leaves_the_source_and_its_other_dependents_intact(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Three dependents of team-1 switch configuration (projects only, none, re-pointed); team-1 loses nothing."""
        cfg = _install_source(configs)
        for name in ('team-2', 'team-3', 'team-4', 'team-5'):
            _install_dependent(cfg, name)
        other = write_config(configs, 'other.yaml', _plain('Other'))
        assert run_main([str(other), *SKIP, '--yes', '--command-names', 'corp-1']) == 0
        claude_dir = e2e_isolated_home['claude_dir']
        source_dir = claude_dir / 'team-1'
        source_before = home_state(source_dir)
        for name in ('team-2', 'team-3', 'team-4', 'team-5'):
            recorded = read_manifest(claude_dir / name)['files_written']
            linked_paths = [path for path in recorded if path.split('/')[0] in LINKABLE_PROFILE_DIRS]
            assert linked_paths == [], f'{name} records files it sees through its links: {linked_paths}'
        capsys.readouterr()

        switches = {
            'team-2': ['--link-dirs', 'projects', '--link-from', 'team-1'],
            'team-3': ['--link-dirs', 'none'],
            'team-4': ['--link-dirs', 'all', '--link-from', 'corp-1'],
        }
        for name, link_argv in switches.items():
            assert run_main([str(other), *SKIP, '--yes', '--command-names', name, *link_argv, '--switch-config']) == 0, name

        output = _output(capsys)
        assert output.count('Accepted via --switch-config') == 3
        for name in switches:
            for entry in CONTENT_ENTRIES:
                assert f'file: {claude_dir / name / entry}' not in output, (name, entry)
                assert f'Removed {claude_dir / name / entry}' not in output, (name, entry)
        assert home_state(source_dir) == source_before, 'the source lost nothing'
        assert (source_dir / 'agents' / 'core.md').is_file()
        assert (source_dir / 'skills' / 'tool-skill' / 'SKILL.md').is_file()
        for entry in LINKABLE_PROFILE_DIRS:
            assert _links_to(claude_dir / 'team-5' / entry, source_dir / entry), entry
        assert _links_to(claude_dir / 'team-2' / 'projects', source_dir / 'projects')
        assert not any((claude_dir / 'team-2' / entry).exists() for entry in CONTENT_ENTRIES), (
            'the content links were dissolved and the new configuration installs no content'
        )
        assert read_manifest(claude_dir / 'team-3')['link'] == {
            'dirs': [], 'source': 'team-1', 'origins': {'dirs': 'cli', 'source': 'cli'},
        }, 'the typed none is remembered'
        assert not any((claude_dir / 'team-3' / entry).exists() for entry in LINKABLE_PROFILE_DIRS)
        for entry in LINKABLE_PROFILE_DIRS:
            assert _links_to(claude_dir / 'team-4' / entry, claude_dir / 'corp-1' / entry), entry
        re_pointed = read_manifest(claude_dir / 'team-4')
        assert re_pointed['link']['source'] == 'corp-1'
        assert re_pointed['config_identity'] == read_manifest(claude_dir / 'corp-1')['config_identity']

    def test_a_link_made_outside_the_setup_shields_its_target_from_residue_removal(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A full profile whose agents/ was replaced by a link by hand switches without deleting through it."""
        _install_source(configs)
        _install_source(configs, 'team-copy')
        claude_dir = e2e_isolated_home['claude_dir']
        copy = claude_dir / 'team-copy'
        recorded = read_manifest(copy)['files_written']
        assert 'agents/core.md' in recorded
        assert 'rules/rule.md' in recorded
        shutil.rmtree(copy / 'agents')
        setup_environment.link_profile_directory(copy / 'agents', claude_dir / 'team-1' / 'agents')
        other = write_config(configs, 'other.yaml', _plain('Other'))
        capsys.readouterr()

        assert run_main([str(other), *SKIP, '--yes', '--command-names', 'team-copy', '--switch-config']) == 0

        output = _output(capsys)
        assert f'file: {copy / "rules" / "rule.md"}' in output, 'a file in a real directory is residue'
        assert f'file: {copy / "agents" / "core.md"}' not in output, 'a file behind the link is not'
        assert not (copy / 'rules' / 'rule.md').exists()
        assert (claude_dir / 'team-1' / 'agents' / 'core.md').is_file(), 'the link target kept its file'
        assert '* agents: [on disk, not declared] the link is left alone' in output
        assert _links_to(copy / 'agents', claude_dir / 'team-1' / 'agents')


@pytest.mark.usefixtures('e2e_isolated_home')
class TestSharedTarget:
    """Several profiles link the same source."""

    def test_two_profiles_share_one_target(self, e2e_isolated_home: dict[str, Path], configs: Path) -> None:
        """team-2 and team-3 both see what team-1 holds, and both are its dependents."""
        cfg = _install_source(configs)
        _install_dependent(cfg, 'team-2')
        _install_dependent(cfg, 'team-3')
        claude_dir = e2e_isolated_home['claude_dir']
        (claude_dir / 'team-1' / 'agents' / 'added.md').write_text('# added\n', encoding='utf-8')

        for name in ('team-2', 'team-3'):
            assert (claude_dir / name / 'agents' / 'added.md').is_file(), name
            assert _links_to(claude_dir / name / 'skills', claude_dir / 'team-1' / 'skills')
        dependents = setup_environment.content_dependents(e2e_isolated_home['home'], 'team-1')
        assert [profile.name for profile in dependents] == ['team-2', 'team-3']
        assert setup_environment.content_dependents(e2e_isolated_home['home'], 'team-2') == []


@pytest.mark.usefixtures('e2e_isolated_home')
class TestEnvironmentValues:
    """The twins CLAUDE_CODE_TOOLBOX_LINK_DIRS and CLAUDE_CODE_TOOLBOX_LINK_FROM stand in for the flags."""

    def test_one_liner_shape_installs_a_dependent_from_the_variables(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The four variables alone install the dependent, marked [env]."""
        cfg = _install_source(configs)
        claude_dir = e2e_isolated_home['claude_dir']
        capsys.readouterr()

        with patch.dict(os.environ, {
            'CLAUDE_CODE_TOOLBOX_ENV_CONFIG': str(cfg),
            'CLAUDE_CODE_TOOLBOX_COMMAND_NAMES': 'team-2',
            'CLAUDE_CODE_TOOLBOX_LINK_DIRS': 'all',
            'CLAUDE_CODE_TOOLBOX_LINK_FROM': 'team-1',
        }):
            assert run_main([*SKIP, '--yes']) == 0

        output = _output(capsys)
        for entry in LINKABLE_PROFILE_DIRS:
            assert _links_to(claude_dir / 'team-2' / entry, claude_dir / 'team-1' / entry), entry
        assert '[env]' in output.split('Links (from profile "team-1"):')[1].split('\n')[0]
        assert read_manifest(claude_dir / 'team-2')['link']['origins'] == {'dirs': 'env', 'source': 'env'}

    def test_leftover_variables_are_named_by_the_source_and_base_refusals(
        self, e2e_isolated_home: dict[str, Path], configs: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """With the one-liner's variables still set, re-running the source or the base names them and how to clear them."""
        cfg = write_config(configs, 'team.yaml', _team())
        assert run_main([str(cfg), *SKIP, '--yes']) == 0
        _install_source(configs)
        claude_dir = e2e_isolated_home['claude_dir']
        source_installed_at = read_manifest(claude_dir / 'team-1')['installed_at']
        monkeypatch.setenv('CLAUDE_CODE_TOOLBOX_LINK_DIRS', 'all')
        monkeypatch.setenv('CLAUDE_CODE_TOOLBOX_LINK_FROM', 'team-1')
        clear = (
            'clear CLAUDE_CODE_TOOLBOX_LINK_DIRS and CLAUDE_CODE_TOOLBOX_LINK_FROM (unset CLAUDE_CODE_TOOLBOX_LINK_DIRS '
            'CLAUDE_CODE_TOOLBOX_LINK_FROM, or Remove-Item Env:CLAUDE_CODE_TOOLBOX_LINK_DIRS, '
            'Env:CLAUDE_CODE_TOOLBOX_LINK_FROM in PowerShell)'
        )
        capsys.readouterr()

        assert run_main(['--profile', 'team-1', *SKIP, '--yes']) == 1

        output = _output(capsys)
        assert (
            'Profile "team-1" cannot link from itself: CLAUDE_CODE_TOOLBOX_LINK_FROM=team-1 names the profile this '
            f'run installs; {clear} to re-run "team-1" as installed, or name another profile in --link-from.'
        ) in output
        assert read_manifest(claude_dir / 'team-1')['installed_at'] == source_installed_at, 'nothing ran'
        capsys.readouterr()

        assert run_main(['--profile', 'base', *SKIP, '--yes']) == 1

        output = _output(capsys)
        assert (
            f'CLAUDE_CODE_TOOLBOX_LINK_DIRS={",".join(LINKABLE_PROFILE_DIRS)} needs an isolated profile: pass '
            '--command-names NAME (or set CLAUDE_CODE_TOOLBOX_COMMAND_NAMES) so the links are created inside '
            f'~/.claude/NAME, or {clear} to run the base profile without links; the base profile cannot link.'
        ) in output
        assert not any(_is_link(claude_dir / entry) for entry in LINKABLE_PROFILE_DIRS if (claude_dir / entry).exists())

    def test_profile_all_refuses_a_link_variable_or_flag_before_any_child(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--profile all names a leftover CLAUDE_CODE_TOOLBOX_LINK_DIRS, or a typed --link-from, and starts nothing."""
        cfg = _install_source(configs)
        _install_dependent(cfg, 'team-2')
        claude_dir = e2e_isolated_home['claude_dir']
        before = {name: read_manifest(claude_dir / name)['installed_at'] for name in ('team-1', 'team-2')}
        capsys.readouterr()

        with (
            patch.object(setup_environment.subprocess, 'run') as run,
            patch.dict(os.environ, {'CLAUDE_CODE_TOOLBOX_LINK_DIRS': 'all'}),
        ):
            assert run_main(['--profile', 'all', *SKIP, '--yes']) == 1
        output = _output(capsys)
        assert (
            'cannot be combined with CLAUDE_CODE_TOOLBOX_LINK_DIRS; clear CLAUDE_CODE_TOOLBOX_LINK_DIRS (unset '
            'CLAUDE_CODE_TOOLBOX_LINK_DIRS, or Remove-Item Env:CLAUDE_CODE_TOOLBOX_LINK_DIRS in PowerShell).'
        ) in output
        run.assert_not_called()
        capsys.readouterr()

        with patch.object(setup_environment.subprocess, 'run') as run:
            assert run_main(['--profile', 'all', '--link-from', 'team-1', *SKIP, '--yes']) == 1
        assert 'cannot be combined with --link-from; drop them from the command line.' in _output(capsys)
        run.assert_not_called()
        assert {name: read_manifest(claude_dir / name)['installed_at'] for name in before} == before, 'no child ran'

    def test_environment_value_that_changes_the_links_is_guarded(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A leftover variable that would re-link a profile is refused under --yes; a typed value proceeds."""
        cfg = _install_source(configs)
        _install_dependent(cfg, 'team-2')
        claude_dir = e2e_isolated_home['claude_dir']
        capsys.readouterr()

        with patch.dict(os.environ, {'CLAUDE_CODE_TOOLBOX_LINK_DIRS': 'projects'}):
            assert run_main(['--profile', 'team-2', *SKIP, '--yes']) == 1
        output = _output(capsys)
        assert 'CLAUDE_CODE_TOOLBOX_LINK_DIRS changes the linked entries of profile "team-2"' in output
        assert 'Pass --link-dirs projects --link-from team-1 to change them.' in output
        assert _links_to(claude_dir / 'team-2' / 'agents', claude_dir / 'team-1' / 'agents'), 'nothing changed'

        assert run_main(['--profile', 'team-2', '--link-dirs', 'projects', '--link-from', 'team-1', *SKIP, '--yes']) == 0

        assert not _is_link(claude_dir / 'team-2' / 'agents')
        assert _links_to(claude_dir / 'team-2' / 'projects', claude_dir / 'team-1' / 'projects')


@pytest.mark.usefixtures('e2e_isolated_home')
class TestDeselectionGuard:
    """Deselection never deletes through a link."""

    def test_deselection_skips_linked_sections(self, e2e_isolated_home: dict[str, Path]) -> None:
        """A deselected agent inside a linked agents/ directory survives the cleanup."""
        claude_dir = e2e_isolated_home['claude_dir']
        source = claude_dir / 'src'
        (source / 'agents').mkdir(parents=True)
        (source / 'agents' / 'dropped.md').write_text('# dropped\n', encoding='utf-8')
        (source / 'skills' / 'gone').mkdir(parents=True)
        profile = claude_dir / 'dep'
        profile.mkdir()
        setup_environment.link_profile_directory(profile / 'agents', source / 'agents')
        setup_environment.link_profile_directory(profile / 'skills', source / 'skills')
        deselected: dict[str, list[Any]] = {
            'agents': ['agents/dropped.md'], 'slash-commands': [], 'rules': [], 'skills': [{'name': 'gone'}],
            'mcp-servers': [], 'files-to-download': [], 'hooks-files': [], 'hooks-events': [],
        }

        setup_environment.execute_deselection_cleanup(
            deselected, {'agents': [], 'skills': []},
            agents_dir=profile / 'agents', commands_dir=profile / 'commands', rules_dir=profile / 'rules',
            skills_dir=profile / 'skills', hooks_dir=profile / 'hooks', is_isolated=True,
            linked_entries=frozenset({'agents', 'skills'}),
        )

        assert (source / 'agents' / 'dropped.md').is_file()
        assert (source / 'skills' / 'gone').is_dir()


def _installed_at(profile_dir: Path) -> str:
    """The installed_at stamp of a profile's manifest."""
    return str(read_manifest(profile_dir)['installed_at'])


def _theme(profile_dir: Path) -> str:
    """The theme a profile's config.json carries."""
    return str(json.loads((profile_dir / 'config.json').read_text(encoding='utf-8'))['theme'])


def _run_output(capfd: pytest.CaptureFixture[str]) -> str:
    """Everything the run and its child processes printed, with Windows line endings normalized."""
    captured = capfd.readouterr()
    return (captured.out + captured.err).replace('\r\n', '\n')


@pytest.mark.usefixtures('e2e_isolated_home')
class TestSourceRunRefreshesDependents:
    """Step 23 of a source run re-runs every profile that links content from it."""

    def test_base_source_refreshes_every_dependent(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capfd: pytest.CaptureFixture[str],
    ) -> None:
        """The base re-run refreshes team-1 and team-2 (all from base) and leaves the projects-only profile alone."""
        cfg = write_config(configs, 'team.yaml', _team())
        claude_dir = e2e_isolated_home['claude_dir']
        assert run_main([str(cfg), *SKIP, '--yes']) == 0
        _install_dependent(cfg, 'team-1', source='base')
        _install_dependent(cfg, 'team-2', source='base')
        _install_dependent(cfg, 'sessions-only', source='base', dirs='projects')
        before = {name: _installed_at(claude_dir / name) for name in ('team-1', 'team-2', 'sessions-only')}
        write_config(configs, 'team.yaml', {**_team(), 'user-settings': {'theme': 'light'}})
        runner = write_child_runner(tmp_path, monkeypatch)
        capfd.readouterr()

        code = run_main([str(cfg), *SKIP, '--yes'], argv0=str(runner))

        output = _run_output(capfd)
        assert code == 0, output
        assert 'Dependents (profiles linking content from this one, refreshed after this run):' in output
        assert '* team-1 (--profile team-1 --yes --skip-install --no-admin)' in output
        assert 'Step 23: Refreshing 2 dependent profile(s): team-1, team-2...' in output
        assert '=== Dependent profile team-1 ===' in output
        assert '* Dependent profiles refreshed from this run:' in output
        assert '- team-1: ok' in output
        assert '- team-2: ok' in output
        assert 'sessions-only (--profile sessions-only)' in output, 'a projects-only profile is not a dependent'
        for name in ('team-1', 'team-2'):
            assert _installed_at(claude_dir / name) != before[name], name
            assert _theme(claude_dir / name) == 'light', 'the dependent applied the refreshed snapshot'
            assert _links_to(claude_dir / name / 'agents', claude_dir / 'agents')
        assert _installed_at(claude_dir / 'sessions-only') == before['sessions-only']
        assert output.count('* Installed profiles this run did not refresh:') == 1, (
            'only the base run lists the profiles it did not refresh; its children list none'
        )
        assert output.count('Step 23: Dependent profiles are refreshed by the run that started this one') == 2, (
            'each dependent child leaves Step 23 to the base run that started it'
        )
        assert 'the --profile all run' not in output, 'a child of a base run is not a child of --profile all'
        assert 'base (--profile base)' not in output, 'no child names the base: the base run is refreshing it right now'
        for name in ('team-1', 'team-2'):
            assert f'{name} (--profile {name})' not in output, (
                f'no child lists {name}: the base run refreshes it in the same run'
            )
        source_summary = output[output.rindex('=== Dependent profile team-2 ==='):]
        source_summary = source_summary[source_summary.index('* Dependent profiles refreshed from this run:'):]
        assert '* Installed profiles this run did not refresh:' in source_summary
        assert '- sessions-only (--profile sessions-only)' in source_summary, (
            'the projects-only profile is the one profile the base run did not refresh'
        )

    def test_isolated_source_refreshes_its_dependents_and_a_dependent_rerun_applies_the_snapshot(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capfd: pytest.CaptureFixture[str],
    ) -> None:
        """Beside a corporate base, team-2 and team-3 follow team-1; the base is never touched and refreshes nobody."""
        corp = write_config(configs, 'team-corp.yaml', {**_team(), 'name': 'Corp', 'user-settings': {'theme': 'corp'}})
        assert run_main([str(corp), *SKIP, '--yes']) == 0, 'the corporate base installs first'
        cfg = _install_source(configs)
        _install_dependent(cfg, 'team-2')
        _install_dependent(cfg, 'team-3')
        claude_dir = e2e_isolated_home['claude_dir']
        base_manifest = read_manifest(claude_dir)
        base_before = (
            base_manifest['installed_at'], base_manifest['config_digest'],
            (claude_dir / 'settings.json').read_bytes(), home_state(claude_dir / 'agents'),
        )
        write_config(configs, 'team.yaml', {**_team(), 'user-settings': {'theme': 'light'}})
        runner = write_child_runner(tmp_path, monkeypatch)

        assert run_main(['--profile', 'team-2', *SKIP, '--yes']) == 0, 'a dependent re-run applies the recorded snapshot'
        assert _theme(claude_dir / 'team-2') == 'dark', 'the source has not been refreshed yet'
        capfd.readouterr()

        code = run_main(['--profile', 'team-1', *SKIP, '--yes'], argv0=str(runner))

        output = _run_output(capfd)
        assert code == 0, output
        assert 'Step 23: Refreshing 2 dependent profile(s): team-2, team-3...' in output
        source_digest = read_manifest(claude_dir / 'team-1')['config_digest']
        for name in ('team-2', 'team-3'):
            assert _theme(claude_dir / name) == 'light', name
            assert read_manifest(claude_dir / name)['config_digest'] == source_digest
            assert _links_to(claude_dir / name / 'agents', claude_dir / 'team-1' / 'agents'), name
            assert not _links_to(claude_dir / name / 'agents', claude_dir / 'agents'), name
        base_manifest = read_manifest(claude_dir)
        assert (
            base_manifest['installed_at'], base_manifest['config_digest'],
            (claude_dir / 'settings.json').read_bytes(), home_state(claude_dir / 'agents'),
        ) == base_before, 'the base profile is untouched'
        assert json.loads((claude_dir / 'settings.json').read_text(encoding='utf-8'))['theme'] == 'corp'
        parent_summary = output[output.index('* Dependent profiles refreshed from this run:'):]
        assert '- base (--profile base)' in parent_summary, 'the base is the one profile this run did not refresh'
        assert '- team-2 (--profile team-2)' not in parent_summary
        assert '- team-3 (--profile team-3)' not in parent_summary
        installed_at = {name: _installed_at(claude_dir / name) for name in ('team-1', 'team-2', 'team-3')}
        capfd.readouterr()

        code = run_main([str(corp), *SKIP, '--yes'], argv0=str(runner))

        output = _run_output(capfd)
        assert code == 0, output
        assert 'Step 23: No installed profile links content from "base"' in output
        assert '=== Dependent profile' not in output
        assert '* Installed profiles this run did not refresh:' in output
        for name in ('team-1', 'team-2', 'team-3'):
            assert f'- {name} (--profile {name})' in output, name
            assert _installed_at(claude_dir / name) == installed_at[name], name
        assert read_manifest(claude_dir)['installed_at'] != base_before[0], 'the base itself was re-installed'

    def test_dependent_run_fetches_nothing_and_reads_the_snapshot(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The configuration a dependent applies comes from the source's resolved-config.yaml, never from the file."""
        cfg = _install_source(configs)
        _install_dependent(cfg, 'team-2')
        claude_dir = e2e_isolated_home['claude_dir']
        cfg.unlink()
        capsys.readouterr()

        with patch.object(setup_environment, 'load_config_from_source') as load:
            assert run_main(['--profile', 'team-2', *SKIP, '--yes']) == 0
        load.assert_not_called()
        snapshot = claude_dir / 'team-1' / 'resolved-config.yaml'
        assert f'Applying the configuration profile "team-1" installed ({snapshot})' in _output(capsys)

    def test_failed_dependent_is_listed_and_the_others_still_run(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capfd: pytest.CaptureFixture[str],
    ) -> None:
        """A dependent that exits non-zero is named with its --profile command; the source exits 1 after running the rest."""
        cfg = _install_source(configs)
        _install_dependent(cfg, 'team-2')
        _install_dependent(cfg, 'team-3')
        claude_dir = e2e_isolated_home['claude_dir']
        # A real agents directory with content in team-2 makes its remembered-value re-run
        # refuse, because only a typed value converts it
        agents = claude_dir / 'team-2' / 'agents'
        setup_environment._remove_directory_link(agents)
        agents.mkdir()
        (agents / 'local.md').write_text('local', encoding='utf-8')
        before = _installed_at(claude_dir / 'team-3')
        runner = write_child_runner(tmp_path, monkeypatch)
        capfd.readouterr()

        code = run_main(['--profile', 'team-1', *SKIP, '--yes'], argv0=str(runner))

        output = _run_output(capfd)
        assert code == 1, output
        assert 'Setup Completed with Errors' in output
        assert 'The following dependent profiles failed to refresh:' in output
        assert '- team-2: failed (exit code 1); retry with --profile team-2' in output
        assert _installed_at(claude_dir / 'team-3') != before, 'the other dependent still ran'

    @pytest.mark.skipif(sys.platform != 'win32', reason='administrator rights are a Windows concern')
    def test_failed_dependent_with_a_global_npm_install_gets_the_elevated_terminal_remedy(
        self, configs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str],
    ) -> None:
        """A dependent whose snapshot installs a global npm package fails on a non-elevated source run with the remedy."""
        cfg = write_config(configs, 'team.yaml', {**_team(), 'dependencies': {'common': ['echo npm install -g fake']}})
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0
        _install_dependent(cfg, 'team-2')
        runner = tmp_path / 'failing_runner.py'
        runner.write_text('import sys\nprint("child failed")\nsys.exit(1)\n', encoding='utf-8')
        monkeypatch.setenv('PYTHONPATH', str(Path(__file__).resolve().parents[2]))
        capfd.readouterr()

        with patch.object(setup_environment, 'is_admin', return_value=False):
            code = run_main(['--profile', 'team-1', *SKIP, '--yes'], argv0=str(runner))

        output = _run_output(capfd)
        assert code == 1, output
        assert 'child failed' in output
        assert (
            '- team-2: failed (exit code 1); retry with --profile team-2 from an elevated terminal (a global npm '
            'install needs administrator rights the run could not request)'
        ) in output

    def test_dry_run_lists_the_dependents_and_starts_none(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--dry-run shows the Dependents block computed from the manifests and runs no child."""
        cfg = _install_source(configs)
        _install_dependent(cfg, 'team-2')
        before = home_state(e2e_isolated_home['home'])
        capsys.readouterr()

        with patch.object(setup_environment.subprocess, 'run') as run:
            assert run_main(['--profile', 'team-1', *SKIP, '--dry-run']) == 0

        run.assert_not_called()
        output = _output(capsys)
        assert 'Dependents (profiles linking content from this one, refreshed after this run):' in output
        assert '* team-2 (--profile team-2 --yes --skip-install --no-admin)' in output
        assert 'Step 23' not in output
        assert home_state(e2e_isolated_home['home']) == before

    def test_children_run_with_the_twins_and_config_dir_stripped(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capfd: pytest.CaptureFixture[str],
    ) -> None:
        """Selector, configuration and link variables set for the source never reach a dependent's run."""
        cfg = _install_source(configs)
        _install_dependent(cfg, 'team-2')
        claude_dir = e2e_isolated_home['claude_dir']
        runner = write_child_runner(tmp_path, monkeypatch)
        monkeypatch.setenv('CLAUDE_CODE_TOOLBOX_SELECT', 'none')
        monkeypatch.setenv('CLAUDE_CODE_TOOLBOX_ENV_CONFIG', str(cfg))
        monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(tmp_path / 'leaked'))
        argvs: list[list[str]] = []
        envs: list[dict[str, str]] = []
        real_run = setup_environment.subprocess.run

        def _recording_run(argv: list[str], *, env: dict[str, str], check: bool) -> subprocess.CompletedProcess[Any]:
            argvs.append(list(argv))
            envs.append(dict(env))
            return real_run(argv, env=env, check=check)

        capfd.readouterr()

        with patch.object(setup_environment.subprocess, 'run', side_effect=_recording_run):
            code = run_main(['--profile', 'team-1', *SKIP, '--yes'], argv0=str(runner))

        output = _run_output(capfd)
        assert code == 0, output
        assert len(argvs) == 1
        assert argvs[0][0] == sys.executable
        assert argvs[0][1:] == [str(runner), '--profile', 'team-2', '--yes', '--child-run', '--skip-install', '--no-admin']
        for variable in ('CLAUDE_CODE_TOOLBOX_SELECT', 'CLAUDE_CODE_TOOLBOX_ENV_CONFIG', 'CLAUDE_CONFIG_DIR'):
            assert variable not in envs[0], variable
        assert '- team-2: ok' in output
        assert _links_to(claude_dir / 'team-2' / 'agents', claude_dir / 'team-1' / 'agents')
        assert (claude_dir / 'team-1' / 'agents' / 'core.md').is_file(), 'the selector variable did not deselect anything'

    def test_profile_all_runs_sources_before_dependents_and_children_skip_step_23(
        self, configs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str],
    ) -> None:
        """--profile all orders a dependent after its source, whatever the names sort to, and refreshes each once."""
        cfg = _install_source(configs, 'zeta-source')
        _install_dependent(cfg, 'alpha-dep', source='zeta-source')
        runner = write_child_runner(tmp_path, monkeypatch)
        capfd.readouterr()

        code = run_main(['--profile', 'all', *SKIP, '--yes'], argv0=str(runner))

        output = _run_output(capfd)
        assert code == 0, output
        assert output.index('=== Profile zeta-source ===') < output.index('=== Profile alpha-dep ===')
        assert output.count('=== Profile alpha-dep ===') == 1
        assert 'Step 23: Dependent profiles are refreshed by the run that started this one' in output
        assert '=== Dependent profile alpha-dep ===' not in output

    def test_children_of_a_source_run_leave_the_unrefreshed_list_to_the_source(
        self, configs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str],
    ) -> None:
        """A dependent child names no profile as unrefreshed; the source's own summary names the base once."""
        corp = write_config(configs, 'team-corp.yaml', {**_team(), 'name': 'Corp', 'user-settings': {'theme': 'corp'}})
        assert run_main([str(corp), *SKIP, '--yes']) == 0, 'the corporate base installs first'
        cfg = _install_source(configs)
        _install_dependent(cfg, 'team-2')
        _install_dependent(cfg, 'team-3')
        runner = write_child_runner(tmp_path, monkeypatch)
        capfd.readouterr()

        code = run_main(['--profile', 'team-1', *SKIP, '--yes'], argv0=str(runner))

        output = _run_output(capfd)
        assert code == 0, output
        assert output.count('=== Dependent profile ') == 2
        assert output.count('Step 23: Dependent profiles are refreshed by the run that started this one') == 2, (
            'each dependent child leaves Step 23 to the source run that started it'
        )
        assert 'the --profile all run' not in output, 'a child of a source run is not a child of --profile all'
        assert output.count('* Installed profiles this run did not refresh:') == 1, (
            'only the source run lists the profiles it did not refresh; its children list none'
        )
        source_summary = output[output.rindex('=== Dependent profile team-3 ==='):]
        source_summary = source_summary[source_summary.index('* Dependent profiles refreshed from this run:'):]
        assert '- team-2: ok' in source_summary
        assert '- team-3: ok' in source_summary
        assert '* Installed profiles this run did not refresh:' in source_summary
        assert '- base (--profile base)' in source_summary, 'the base is the one profile the source run did not refresh'
        for name in ('team-1', 'team-2', 'team-3'):
            assert f'{name} (--profile {name})' not in output, (
                f'no child lists {name}: the source is refreshing it right now, or refreshes it in the same run'
            )

    def test_dependent_rerun_by_name_lists_the_profiles_it_did_not_refresh(
        self, configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A dependent re-run on its own, not as a child, reports like any other single run."""
        cfg = _install_source(configs)
        _install_dependent(cfg, 'team-2')
        _install_dependent(cfg, 'team-3')
        capsys.readouterr()

        assert run_main(['--profile', 'team-2', *SKIP, '--yes']) == 0

        output = _output(capsys)
        assert 'Step 23: No installed profile links content from "team-2"' in output
        assert 'refreshed by the run that started this one' not in output
        assert '* Installed profiles this run did not refresh:' in output
        assert '- team-1 (--profile team-1)' in output
        assert '- team-3 (--profile team-3)' in output
        assert '- team-2 (--profile team-2)' not in output


@pytest.mark.usefixtures('e2e_isolated_home')
class TestDependentIntegrity:
    """A dependent's links are verified after the dependency commands and at the end of the run."""

    def test_dependency_command_that_replaces_a_link_stops_the_run(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A link turned into a real directory during Step 6 exits 1 with the repair command."""
        cfg = _install_source(configs)
        _install_dependent(cfg, 'team-2')
        claude_dir = e2e_isolated_home['claude_dir']
        agents = claude_dir / 'team-2' / 'agents'

        def _replace_link(_dependencies: object) -> list[str]:
            setup_environment._remove_directory_link(agents)
            agents.mkdir()
            return []

        capsys.readouterr()
        with patch.object(setup_environment, 'install_dependencies', side_effect=_replace_link):
            assert run_main(['--profile', 'team-2', *SKIP, '--yes']) == 1

        output = _output(capsys)
        assert 'Profile "team-2" no longer holds every link it was installed with:' in output
        assert f'{agents} is no longer a link' in output
        assert 'Re-run the profile to repair its links: --profile team-2' in output

    def test_missing_wired_hook_file_in_the_source_stops_the_run(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A hook file the events wire must exist through the linked hooks/ before config.json is written."""
        cfg = _install_source(configs)
        _install_dependent(cfg, 'team-2')
        claude_dir = e2e_isolated_home['claude_dir']
        (claude_dir / 'team-1' / 'hooks' / 'hook.py').unlink()
        capsys.readouterr()

        assert run_main(['--profile', 'team-2', *SKIP, '--yes']) == 1

        output = _output(capsys)
        assert 'Profile "team-2" wires hook files that profile "team-1" does not hold:' in output
        assert str(claude_dir / 'team-2' / 'hooks' / 'hook.py') in output
        assert 'Re-run the source first: --profile team-1' in output


def _profile_settings(profile_dir: Path) -> dict[str, Any]:
    """The settings a profile's config.json carries."""
    content: dict[str, Any] = json.loads((profile_dir / 'config.json').read_text(encoding='utf-8'))
    return content


@pytest.mark.usefixtures('e2e_isolated_home')
class TestSkillsSync:
    """A profile whose skills/ is a link gets syncClaudeAiSkills switched off, so the sync never writes into the source."""

    def test_profile_linking_skills_disables_the_sync_and_marks_it_auto(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The dependent's config.json carries syncClaudeAiSkills false; the source's config.json does not."""
        cfg = _install_source(configs)
        claude_dir = e2e_isolated_home['claude_dir']
        capsys.readouterr()

        _install_dependent(cfg, 'team-2')

        output = _output(capsys)
        assert '[auto] user-settings.syncClaudeAiSkills: false' in output
        assert _profile_settings(claude_dir / 'team-2')['syncClaudeAiSkills'] is False
        assert 'syncClaudeAiSkills' not in _profile_settings(claude_dir / 'team-1')
        assert _links_to(claude_dir / 'team-2' / 'skills', claude_dir / 'team-1' / 'skills')

    def test_projects_only_link_leaves_the_sync_alone(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A sessions-only link installs its own skills/, so the sync stays as the configuration leaves it."""
        cfg = _install_source(configs)
        claude_dir = e2e_isolated_home['claude_dir']
        capsys.readouterr()

        _install_dependent(cfg, 'sessions-only', dirs='projects')

        assert '[auto] user-settings.syncClaudeAiSkills' not in _output(capsys)
        assert 'syncClaudeAiSkills' not in _profile_settings(claude_dir / 'sessions-only')

    def test_declared_value_is_kept_with_a_warning(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A configuration that sets syncClaudeAiSkills true keeps it in the linked profile; the run warns."""
        cfg = write_config(configs, 'team.yaml', {**_team(), 'user-settings': {'syncClaudeAiSkills': True}})
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'team-1']) == 0
        claude_dir = e2e_isolated_home['claude_dir']
        capsys.readouterr()

        _install_dependent(cfg, 'team-2')

        output = _output(capsys)
        assert (
            'User set user-settings.syncClaudeAiSkills to True (linked skills intent is False). Respecting user value.'
        ) in output
        assert '[auto] user-settings.syncClaudeAiSkills' not in output
        assert _profile_settings(claude_dir / 'team-2')['syncClaudeAiSkills'] is True

    def test_dry_run_shows_the_auto_row_and_writes_nothing(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--dry-run of a profile that would link skills lists the injected value before anything exists."""
        cfg = _install_source(configs)
        before = home_state(e2e_isolated_home['home'])
        capsys.readouterr()

        code = run_main([
            str(cfg), *SKIP, '--dry-run', '--command-names', 'team-2', '--link-dirs', 'all', '--link-from', 'team-1',
        ])

        assert code == 0
        assert '[auto] user-settings.syncClaudeAiSkills: false' in _output(capsys)
        assert home_state(e2e_isolated_home['home']) == before
