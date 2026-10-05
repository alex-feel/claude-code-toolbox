"""Unit tests for the link layer of setup_environment.py.

Covers the link-dirs parser, the per-key precedence of the link values, the
manifest record, the on-disk plan of Step 3, the link rules, the dependent
registry, and the helpers a dependent run uses.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from typing import cast
from unittest.mock import patch

import pytest

from scripts import setup_environment
from scripts.setup_environment import LINKABLE_PROFILE_DIRS
from scripts.setup_environment import LinkSource
from scripts.setup_environment import LinkSpec
from scripts.setup_environment import content_dependents
from scripts.setup_environment import link_request_errors
from scripts.setup_environment import parse_link_dirs
from scripts.setup_environment import plan_profile_links
from scripts.setup_environment import resolve_link_spec

_REAL_INSTALLED_PROFILES = setup_environment.installed_profiles


def _args(
    *,
    link_dirs: str | None = None,
    link_from: str | None = None,
    env: dict[str, str] | None = None,
    select: str | None = None,
) -> argparse.Namespace:
    """Build resolved arguments the way main() does."""
    namespace = argparse.Namespace(
        config=None, yes=True, dry_run=False, skip_install=True, no_admin=True, env_vars=None,
        select=select, with_=None, without=None, list_components=False, command_names=None, profile=None,
        switch_config=False, child_run=False, link_dirs=link_dirs, link_from=link_from, run_all_commands=False,
    )
    cleared = {twin.variable: '' for twin in setup_environment.ENV_TWINS}
    with patch.dict(os.environ, {**cleared, **(env or {})}, clear=False):
        return setup_environment.resolve_args(namespace)


def _manifest(
    directory: Path,
    name: str | None,
    *,
    link: dict[str, Any] | None = None,
    config_source: str = 'https://example.com/team.yaml',
    yaml_values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write a manifest with a link record and return it."""
    directory.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        'name': name,
        'version': None,
        'claude_code_version': None,
        'config_source': config_source,
        'config_source_url': config_source,
        'config_source_type': 'url',
        'config_identity': setup_environment.config_identity_of(config_source),
        'config_digest': None,
        'installed_at': '2026-01-01T00:00:00+00:00',
        'command_names': [name] if name else [],
        'components': None,
        'link': link,
        'origins': {'command_names': 'cli' if name else None, 'components': 'yaml'},
        'yaml_values': yaml_values if yaml_values is not None else {'command_names': [], 'components': []},
        'machine_wide_destinations': [],
        'os_env_written': [],
        'settings_keys_written': [],
        'mcp_servers': [],
        'files_written': [],
    }
    (directory / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    return manifest


def _record(dirs: list[str], source: str = 'base', dirs_origin: str = 'cli', source_origin: str = 'cli') -> dict[str, Any]:
    return {'dirs': dirs, 'source': source, 'origins': {'dirs': dirs_origin, 'source': source_origin}}


class TestParseLinkDirs:
    """parse_link_dirs() accepts entries, all and none, in either value shape."""

    def test_all_expands_to_every_entry_in_display_order(self) -> None:
        assert parse_link_dirs('ALL', '--link-dirs') == (list(LINKABLE_PROFILE_DIRS), [])

    def test_none_is_no_entry(self) -> None:
        assert parse_link_dirs(['none'], 'link-dirs') == ([], [])

    def test_entries_are_ordered_and_case_insensitive(self) -> None:
        assert parse_link_dirs('projects, Skills ,hooks', '--link-dirs') == (['skills', 'hooks', 'projects'], [])

    @pytest.mark.parametrize(
        ('value', 'message'),
        [
            ('settings', 'names unknown entries: settings'),
            ('all,skills', '"all" stands alone'),
            ('skills,skills', 'lists an entry twice'),
            ('skills,', 'lists an empty entry'),
            (3, 'expected a comma-separated list'),
        ],
    )
    def test_invalid_values_name_the_source(self, value: object, message: str) -> None:
        entries, errors = parse_link_dirs(value, 'CLAUDE_CODE_TOOLBOX_LINK_DIRS')
        assert entries == []
        assert len(errors) == 1
        assert message in errors[0]
        assert 'CLAUDE_CODE_TOOLBOX_LINK_DIRS' in errors[0]


class TestResolveLinkSpec:
    """Per key: typed, environment, remembered, configuration, default."""

    def test_default_links_nothing_from_base(self) -> None:
        spec, errors = resolve_link_spec(_args(), {}, None)
        assert errors == []
        assert spec == LinkSpec([], 'base', 'default', 'default')
        assert spec.record() is None

    def test_typed_values_win_and_are_recorded(self) -> None:
        spec, errors = resolve_link_spec(
            _args(link_dirs='all', link_from='team-1', env={'CLAUDE_CODE_TOOLBOX_LINK_DIRS': 'projects'}),
            {'link-dirs': ['projects'], 'link-from': 'other'},
            None,
        )
        assert errors == []
        assert spec.dirs == list(LINKABLE_PROFILE_DIRS)
        assert spec.source == 'team-1'
        assert (spec.dirs_origin, spec.source_origin) == ('cli', 'cli')
        assert spec.typed
        assert spec.record() == _record(list(LINKABLE_PROFILE_DIRS), 'team-1')

    def test_environment_values_rank_second(self) -> None:
        spec, errors = resolve_link_spec(
            _args(env={'CLAUDE_CODE_TOOLBOX_LINK_DIRS': 'projects', 'CLAUDE_CODE_TOOLBOX_LINK_FROM': 'team-1'}),
            {'link-dirs': ['all']},
            None,
        )
        assert errors == []
        assert spec.dirs == ['projects']
        assert spec.source == 'team-1'
        assert (spec.dirs_origin, spec.source_origin) == ('env', 'env')
        assert spec.typed

    def test_remembered_content_link_beats_the_configuration_whatever_its_origin(self, tmp_path: Path) -> None:
        manifest = _manifest(tmp_path, 'dep', link=_record(['skills', 'projects'], 'team-1', 'yaml', 'yaml'))
        spec, errors = resolve_link_spec(_args(), {'link-dirs': ['projects']}, manifest)
        assert errors == []
        assert spec.dirs == ['skills', 'projects']
        assert spec.source == 'team-1'
        assert spec.dirs_remembered
        assert spec.source_remembered
        assert (spec.dirs_origin, spec.source_origin) == ('yaml', 'yaml')
        assert not spec.typed

    def test_remembered_projects_link_is_kept_only_when_typed_or_from_the_environment(self, tmp_path: Path) -> None:
        typed = _manifest(tmp_path / 'a', 'dep', link=_record(['projects'], 'base', 'env', 'default'))
        spec, _ = resolve_link_spec(_args(), {}, typed)
        assert spec.dirs == ['projects']
        assert spec.dirs_remembered
        assert spec.dirs_origin == 'env'
        assert spec.source == 'base'
        assert not spec.source_remembered
        declared = _manifest(tmp_path / 'b', 'dep', link=_record(['projects'], 'base', 'yaml', 'default'))
        spec, _ = resolve_link_spec(_args(), {}, declared)
        assert spec.dirs == [], 'a configuration value is re-read on every run'
        assert not spec.dirs_remembered
        spec, _ = resolve_link_spec(_args(), {'link-dirs': ['projects']}, declared)
        assert spec.dirs == ['projects']
        assert spec.dirs_origin == 'yaml'

    def test_configuration_values_rank_fourth(self) -> None:
        spec, errors = resolve_link_spec(_args(), {'link-dirs': ['hooks', 'skills'], 'link-from': 'team-1'}, None)
        assert errors == []
        assert spec.dirs == ['skills', 'hooks']
        assert spec.source == 'team-1'
        assert (spec.dirs_origin, spec.source_origin) == ('yaml', 'yaml')
        assert not spec.typed

    def test_typed_none_links_nothing_and_is_recorded_as_typed(self, tmp_path: Path) -> None:
        manifest = _manifest(tmp_path, 'dep', link=_record(list(LINKABLE_PROFILE_DIRS), 'team-1'))
        spec, errors = resolve_link_spec(_args(link_dirs='none'), {'link-dirs': ['projects']}, manifest)
        assert errors == []
        assert spec.dirs == []
        assert spec.typed
        assert spec.record() == _record([], 'team-1', 'cli', 'cli'), 'the remembered source keeps its origin'
        from_environment, _ = resolve_link_spec(_args(env={'CLAUDE_CODE_TOOLBOX_LINK_DIRS': 'none'}), {}, None)
        assert from_environment.record() == _record([], 'base', 'env', 'default')

    def test_configuration_none_is_not_recorded(self) -> None:
        spec, errors = resolve_link_spec(_args(), {'link-dirs': ['none'], 'link-from': 'team-1'}, None)
        assert errors == []
        assert spec.dirs == []
        assert not spec.typed
        assert spec.record() is None, 'a configuration value is re-read on every run, never remembered'

    def test_remembered_none_beats_the_configuration(self, tmp_path: Path) -> None:
        """A typed or environment none is remembered ahead of the YAML link-dirs, whatever the YAML declares."""
        for origin in ('cli', 'env'):
            manifest = _manifest(tmp_path / origin, 'dep', link=_record([], 'base', origin, 'default'))
            spec, errors = resolve_link_spec(_args(), {'link-dirs': ['all'], 'link-from': 'team-1'}, manifest)
            assert errors == [], origin
            assert spec.dirs == [], origin
            assert spec.dirs_remembered, origin
            assert spec.dirs_origin == origin
            assert not spec.typed, 'a remembered none never converts or unlinks anything'
            assert spec.source == 'team-1', 'the source falls through to the configuration'
            assert spec.source_origin == 'yaml'
            assert spec.record() == _record([], 'team-1', origin, 'yaml'), 'the re-run records the none again'
        remembered = _manifest(tmp_path / 'again', 'dep', link=_record([], 'base'))
        typed_again, errors = resolve_link_spec(_args(link_dirs='projects'), {'link-dirs': ['all']}, remembered)
        assert errors == []
        assert typed_again.dirs == ['projects']
        assert typed_again.typed

    def test_remembered_none_with_a_typed_source_still_needs_entries(self, tmp_path: Path) -> None:
        manifest = _manifest(tmp_path, 'dep', link=_record([], 'base'))
        _spec, errors = resolve_link_spec(_args(link_from='team-1'), {}, manifest)
        assert errors == [
            (
                '--link-from names the profile "team-1", but no entry is linked; pass --link-dirs ENTRIES '
                '(or set CLAUDE_CODE_TOOLBOX_LINK_DIRS) to link from it, or clear --link-from.'
            ),
        ]

    def test_recorded_none_with_a_configuration_origin_is_not_remembered(self, tmp_path: Path) -> None:
        manifest = _manifest(tmp_path, 'dep', link=_record([], 'base', 'yaml', 'default'))
        spec, _ = resolve_link_spec(_args(), {'link-dirs': ['projects']}, manifest)
        assert spec.dirs == ['projects']
        assert spec.dirs_origin == 'yaml'
        assert not spec.dirs_remembered

    def test_source_without_entries_is_an_error_only_when_typed_or_from_the_environment(self) -> None:
        _spec, errors = resolve_link_spec(_args(link_from='team-1'), {}, None)
        assert errors == [
            (
                '--link-from names the profile "team-1", but no entry is linked; pass --link-dirs ENTRIES '
                '(or set CLAUDE_CODE_TOOLBOX_LINK_DIRS) to link from it, or clear --link-from.'
            ),
        ]
        _spec, errors = resolve_link_spec(_args(), {'link-from': 'team-1'}, None)
        assert errors == []

    @pytest.mark.parametrize('value', ['two words', 'all', 'bad/name', ''])
    def test_invalid_source_is_an_error(self, value: str) -> None:
        _spec, errors = resolve_link_spec(_args(link_dirs='projects', link_from=value), {}, None)
        assert errors
        assert '--link-from' in errors[0]

    def test_base_is_matched_without_regard_to_case(self) -> None:
        spec, errors = resolve_link_spec(_args(link_dirs='projects', link_from='Base'), {}, None)
        assert errors == []
        assert spec.source == 'base'

    def test_invalid_configuration_values_are_errors(self) -> None:
        _spec, errors = resolve_link_spec(_args(), {'link-dirs': 'projects,bogus', 'link-from': 3}, None)
        assert any('link-dirs names unknown entries: bogus' in err for err in errors)
        assert any('Invalid link-from value' in err for err in errors)


class TestPlanProfileLinks:
    """plan_profile_links() decides create, keep, repair, convert, unlink or report per entry."""

    @pytest.fixture
    def layout(self, tmp_path: Path) -> tuple[Path, Path]:
        source = tmp_path / '.claude' / 'team-1'
        for entry in LINKABLE_PROFILE_DIRS:
            (source / entry).mkdir(parents=True)
        profile = tmp_path / '.claude' / 'team-2'
        profile.mkdir()
        return profile, source

    def test_absent_entries_are_created_and_the_rest_reported(self, layout: tuple[Path, Path]) -> None:
        profile, source = layout
        plan = plan_profile_links(
            profile, ['skills', 'projects'], source, source_name='team-1', typed=False, timestamp='T',
        )
        assert plan.errors == []
        assert [(a.entry, a.kind) for a in plan.actions] == [('skills', 'create'), ('projects', 'create')]
        assert plan.actions[0].target == source / 'skills'
        assert plan.linked_entries == ['skills', 'projects']
        assert plan.rows() == [
            f'skills -> {source / "skills"} [create]', f'projects -> {source / "projects"} [create]',
        ]
        assert plan.move_aside_rows() == []

    def test_existing_links_are_kept_or_repaired(self, layout: tuple[Path, Path], tmp_path: Path) -> None:
        profile, source = layout
        setup_environment.link_profile_directory(profile / 'skills', source / 'skills')
        elsewhere = tmp_path / 'elsewhere'
        elsewhere.mkdir()
        setup_environment.link_profile_directory(profile / 'agents', elsewhere)
        plan = plan_profile_links(
            profile, ['skills', 'agents'], source, source_name='team-1', typed=False, timestamp='T',
        )
        assert [(a.entry, a.kind) for a in plan.actions] == [('skills', 'keep'), ('agents', 'repair')]
        assert plan.rows()[1] == f'agents -> {source / "agents"} [repair: the link points elsewhere]'

    def test_projects_targets_the_final_real_directory(self, layout: tuple[Path, Path], tmp_path: Path) -> None:
        profile, source = layout
        real = tmp_path / '.claude' / 'projects'
        real.mkdir()
        (source / 'projects').rmdir()
        setup_environment.link_profile_directory(source / 'projects', real)
        plan = plan_profile_links(
            profile, ['projects', 'skills'], source, source_name='team-1', typed=True, timestamp='T',
        )
        by_entry = {a.entry: a for a in plan.actions}
        projects_target = by_entry['projects'].target
        assert projects_target is not None
        assert os.path.normcase(os.path.realpath(projects_target)) == os.path.normcase(os.path.realpath(real))
        assert by_entry['skills'].target == source / 'skills', 'content links point at the source itself'

    def test_real_directory_converts_only_under_a_typed_value(self, layout: tuple[Path, Path]) -> None:
        profile, source = layout
        (profile / 'projects').mkdir()
        (profile / 'projects' / 'a.jsonl').write_text('', encoding='utf-8')
        (profile / 'projects' / 'b.jsonl').write_text('', encoding='utf-8')
        (profile / 'agents').mkdir()
        remembered = plan_profile_links(
            profile, ['projects', 'agents'], source, source_name='team-1', typed=False, timestamp='T',
        )
        assert len(remembered.errors) == 1
        assert (
            f'{profile / "projects"} is a real directory with 2 item(s), and only a typed value converts it'
        ) in remembered.errors[0]
        assert 'pass --link-dirs projects,agents' in remembered.errors[0]
        assert [(a.entry, a.kind) for a in remembered.actions] == [('agents', 'create')], 'an empty directory is replaced'
        typed = plan_profile_links(
            profile, ['projects', 'agents'], source, source_name='team-1', typed=True, timestamp='T',
        )
        assert typed.errors == []
        convert = next(a for a in typed.actions if a.entry == 'projects')
        assert convert.kind == 'convert'
        assert convert.moved_to == profile / 'projects.unlinked-T'
        assert convert.item_count == 2
        assert typed.move_aside_rows() == [
            (
                f'projects: {profile / "projects"} (2 items) -> {profile / "projects.unlinked-T"}; '
                'those sessions and auto-memory stop appearing in this profile'
            ),
        ]
        assert typed.rows()[-1] == f'projects -> {source / "projects"} [create after moving the real directory aside]'

    def test_a_file_at_an_entry_path_is_an_error(self, layout: tuple[Path, Path]) -> None:
        profile, source = layout
        (profile / 'rules').write_text('', encoding='utf-8')
        plan = plan_profile_links(profile, ['rules'], source, source_name='team-1', typed=True, timestamp='T')
        assert plan.errors == [f'{profile / "rules"} is a file, so rules cannot be linked; move the file away first.']

    def test_undeclared_links_are_reported_and_unlinked_only_when_typed(self, layout: tuple[Path, Path]) -> None:
        profile, source = layout
        setup_environment.link_profile_directory(profile / 'hooks', source / 'hooks')
        reported = plan_profile_links(profile, [], source, source_name='base', typed=False, timestamp='T')
        assert [(a.entry, a.kind) for a in reported.actions] == [('hooks', 'undeclared')]
        assert reported.rows() == ['hooks: [on disk, not declared] the link is left alone']
        assert reported.linked_entries == []
        removed = plan_profile_links(profile, [], source, source_name='base', typed=True, timestamp='T')
        assert [(a.entry, a.kind) for a in removed.actions] == [('hooks', 'unlink')]
        assert removed.rows() == ['hooks: [unlink] the link is removed; this run installs the real directory']

    def test_apply_and_verify(self, layout: tuple[Path, Path], tmp_path: Path) -> None:
        profile, source = layout
        (profile / 'agents').mkdir()
        (profile / 'agents' / 'x.md').write_text('', encoding='utf-8')
        setup_environment.link_profile_directory(profile / 'hooks', source / 'hooks')
        elsewhere = tmp_path / 'elsewhere'
        elsewhere.mkdir()
        setup_environment.link_profile_directory(profile / 'rules', elsewhere)
        plan = plan_profile_links(
            profile, ['agents', 'rules', 'skills'], source, source_name='team-1', typed=True, timestamp='T',
        )

        setup_environment.apply_link_plan(plan)

        assert (profile / 'agents.unlinked-T' / 'x.md').is_file()
        for entry in ('agents', 'rules', 'skills'):
            assert setup_environment._is_directory_link(profile / entry)
            assert setup_environment._link_points_to(profile / entry, source / entry), entry
        assert not setup_environment._is_directory_link(profile / 'hooks'), 'the typed value unlinked hooks'
        assert (source / 'hooks').is_dir(), 'unlinking leaves the target alone'
        assert setup_environment.verify_profile_links(profile, plan) == []
        setup_environment._remove_directory_link(profile / 'skills')
        (profile / 'skills').mkdir()
        setup_environment._remove_directory_link(profile / 'rules')
        setup_environment.link_profile_directory(profile / 'rules', elsewhere)
        broken = setup_environment.verify_profile_links(profile, plan)
        assert broken == [
            f'{profile / "skills"} is no longer a link (it was linked to {source / "skills"})',
            f'{profile / "rules"} no longer points at {source / "rules"}',
        ]

    def test_missing_source_entry_is_created_when_linked(self, tmp_path: Path) -> None:
        source = tmp_path / 'src'
        source.mkdir()
        profile = tmp_path / 'dep'
        profile.mkdir()
        plan = plan_profile_links(profile, ['output-styles'], source, source_name='src', typed=True, timestamp='T')
        setup_environment.apply_link_plan(plan)
        assert (source / 'output-styles').is_dir()
        assert setup_environment._link_points_to(profile / 'output-styles', source / 'output-styles')


class TestLinkRules:
    """link_request_errors() checks every rule before any write."""

    def _source(self, tmp_path: Path, *, link: dict[str, Any] | None = None, manifest: bool = True) -> LinkSource:
        directory = tmp_path / '.claude' / 'team-1'
        record = _manifest(directory, 'team-1', link=link) if manifest else None
        if not manifest:
            directory.mkdir(parents=True, exist_ok=True)
        return LinkSource('team-1', directory, record)

    def test_no_links_no_errors(self) -> None:
        assert link_request_errors(
            LinkSpec([], 'base', 'default', 'default'), None, primary_command_name=None, this_identity='x',
            typed_selectors=True,
        ) == []

    def test_base_profile_cannot_link(self) -> None:
        errors = link_request_errors(
            LinkSpec(['projects'], 'base', 'cli', 'default'), None, primary_command_name=None, this_identity='x',
            typed_selectors=False,
        )
        assert errors == [
            (
                '--link-dirs projects needs an isolated profile: pass --command-names NAME (or set '
                'CLAUDE_CODE_TOOLBOX_COMMAND_NAMES) so the links are created inside ~/.claude/NAME; the base '
                'profile cannot link.'
            ),
        ]

    def test_base_profile_refusal_names_the_configuration_key_and_the_variable(self) -> None:
        """The message names the value the way it was given, with the remedy that undoes that source."""
        from_yaml = link_request_errors(
            LinkSpec(['projects'], 'base', 'yaml', 'default'), None, primary_command_name=None, this_identity='x',
            typed_selectors=False,
        )
        assert from_yaml == [
            (
                'link-dirs [projects] needs an isolated profile: pass --command-names NAME (or set '
                'CLAUDE_CODE_TOOLBOX_COMMAND_NAMES) so the links are created inside ~/.claude/NAME, or remove '
                'link-dirs from the configuration; the base profile cannot link.'
            ),
        ]
        from_environment = link_request_errors(
            LinkSpec(['skills', 'projects'], 'team-1', 'env', 'env'), None, primary_command_name=None,
            this_identity='x', typed_selectors=False,
        )
        assert from_environment == [
            (
                'CLAUDE_CODE_TOOLBOX_LINK_DIRS=skills,projects needs an isolated profile: pass --command-names NAME '
                '(or set CLAUDE_CODE_TOOLBOX_COMMAND_NAMES) so the links are created inside ~/.claude/NAME, or clear '
                'CLAUDE_CODE_TOOLBOX_LINK_DIRS and CLAUDE_CODE_TOOLBOX_LINK_FROM (unset CLAUDE_CODE_TOOLBOX_LINK_DIRS '
                'CLAUDE_CODE_TOOLBOX_LINK_FROM, or Remove-Item Env:CLAUDE_CODE_TOOLBOX_LINK_DIRS, '
                'Env:CLAUDE_CODE_TOOLBOX_LINK_FROM in PowerShell) to run the base profile without links; the base '
                'profile cannot link.'
            ),
        ]

    def test_profile_cannot_link_from_itself(self, tmp_path: Path) -> None:
        errors = link_request_errors(
            LinkSpec(['projects'], 'team-1', 'cli', 'cli'), self._source(tmp_path), primary_command_name='Team-1',
            this_identity='x', typed_selectors=False,
        )
        assert errors == [
            (
                'Profile "Team-1" cannot link from itself: --link-from team-1 names the profile this run installs; '
                'name another profile in --link-from.'
            ),
        ]

    def test_self_link_refusal_names_the_variable_or_the_configuration_key(self, tmp_path: Path) -> None:
        """A leftover variable gets the clear remedy; a configuration meant for the dependents gets --link-dirs none."""
        from_environment = link_request_errors(
            LinkSpec(list(LINKABLE_PROFILE_DIRS), 'team-1', 'env', 'env'), self._source(tmp_path),
            primary_command_name='team-1', this_identity='x', typed_selectors=False,
        )
        assert from_environment == [
            (
                'Profile "team-1" cannot link from itself: CLAUDE_CODE_TOOLBOX_LINK_FROM=team-1 names the profile '
                'this run installs; clear CLAUDE_CODE_TOOLBOX_LINK_DIRS and CLAUDE_CODE_TOOLBOX_LINK_FROM (unset '
                'CLAUDE_CODE_TOOLBOX_LINK_DIRS CLAUDE_CODE_TOOLBOX_LINK_FROM, or Remove-Item '
                'Env:CLAUDE_CODE_TOOLBOX_LINK_DIRS, Env:CLAUDE_CODE_TOOLBOX_LINK_FROM in PowerShell) to re-run '
                '"team-1" as installed, or name another profile in --link-from.'
            ),
        ]
        from_yaml = link_request_errors(
            LinkSpec(list(LINKABLE_PROFILE_DIRS), 'team-1', 'yaml', 'yaml'), self._source(tmp_path),
            primary_command_name='team-1', this_identity='x', typed_selectors=False,
        )
        assert from_yaml == [
            (
                'Profile "team-1" cannot link from itself: link-from team-1 names the profile this run installs; '
                'pass --link-dirs none to install "team-1" without links, as the source the configuration\'s other '
                'profiles link from, or name another profile in --link-from.'
            ),
        ]

    def test_content_rule_refusals_add_the_clear_remedy_for_environment_values(self, tmp_path: Path) -> None:
        """Every content-rule message ends with how to clear a variable the value came from."""
        errors = link_request_errors(
            LinkSpec(['skills'], 'team-1', 'cli', 'env'), self._source(tmp_path), primary_command_name='p1',
            this_identity='other', typed_selectors=True,
        )
        assert len(errors) == 2
        suffix = (
            ' Or clear CLAUDE_CODE_TOOLBOX_LINK_FROM (unset CLAUDE_CODE_TOOLBOX_LINK_FROM, or Remove-Item '
            'Env:CLAUDE_CODE_TOOLBOX_LINK_FROM in PowerShell) to run without links.'
        )
        assert all(err.endswith(suffix) for err in errors), errors
        assert 'link only between installs of one configuration' in errors[0]
        assert 'drop --select, --with and --without' in errors[1]

    def test_unknown_source_names_the_value_and_its_variable(self, tmp_path: Path) -> None:
        (tmp_path / '.claude').mkdir()
        typed, typed_errors = setup_environment.resolve_link_source(LinkSpec(['projects'], 'nobody', 'cli', 'cli'), tmp_path)
        assert typed is None
        assert typed_errors == [
            (
                f'--link-from nobody names the profile "nobody", but no profile of that name is installed '
                f'({tmp_path / ".claude" / "nobody"} does not exist); install it first, or name an installed profile.'
            ),
        ]
        _, env_errors = setup_environment.resolve_link_source(LinkSpec(['projects'], 'nobody', 'cli', 'env'), tmp_path)
        assert env_errors == [
            (
                f'CLAUDE_CODE_TOOLBOX_LINK_FROM=nobody names the profile "nobody", but no profile of that name is '
                f'installed ({tmp_path / ".claude" / "nobody"} does not exist); install it first, name an installed '
                'profile, or clear CLAUDE_CODE_TOOLBOX_LINK_FROM (unset CLAUDE_CODE_TOOLBOX_LINK_FROM, or Remove-Item '
                'Env:CLAUDE_CODE_TOOLBOX_LINK_FROM in PowerShell) to run without links.'
            ),
        ]

    def test_clear_variables_text(self) -> None:
        assert setup_environment.clear_variables_text(['A']) == 'A (unset A, or Remove-Item Env:A in PowerShell)'
        assert setup_environment.clear_variables_text(['A', 'B', 'C']) == (
            'A, B and C (unset A B C, or Remove-Item Env:A, Env:B, Env:C in PowerShell)'
        )

    def test_projects_needs_no_manifest_and_no_identity(self, tmp_path: Path) -> None:
        source = self._source(tmp_path, manifest=False)
        assert link_request_errors(
            LinkSpec(['projects'], 'team-1', 'cli', 'cli'), source, primary_command_name='p1', this_identity=None,
            typed_selectors=True,
        ) == []

    def test_content_needs_a_manifest_the_same_identity_and_a_real_holder(self, tmp_path: Path) -> None:
        identity = setup_environment.config_identity_of('https://example.com/team.yaml')
        no_manifest = link_request_errors(
            LinkSpec(['skills'], 'team-1', 'cli', 'cli'), self._source(tmp_path / 'a', manifest=False),
            primary_command_name='p1', this_identity=identity, typed_selectors=False,
        )
        assert len(no_manifest) == 1
        assert 'has no manifest' in no_manifest[0]
        other_identity = link_request_errors(
            LinkSpec(['skills'], 'team-1', 'cli', 'cli'), self._source(tmp_path / 'b'),
            primary_command_name='p1', this_identity='other', typed_selectors=False,
        )
        assert other_identity == [
            (
                'Content entries (skills) link only between installs of one configuration: profile "team-1" was '
                'installed from https://example.com/team.yaml, and this run was given a different configuration. '
                'Install one full profile of the configuration this run was given first (--command-names SOURCE '
                'with no link keys), then link the others from it with --link-from SOURCE; or run the setup with '
                'the configuration profile "team-1" was installed from (the identity is its resolved path or URL); '
                'or link only projects.'
            ),
        ]
        remembered = link_request_errors(
            LinkSpec(['skills'], 'team-1', 'cli', 'cli', dirs_remembered=True, source_remembered=True),
            self._source(tmp_path / 'b'), primary_command_name='p1', this_identity='other', typed_selectors=False,
        )
        assert remembered == [
            (
                'Content entries (skills) link only between installs of one configuration: profile "team-1" was '
                'installed from https://example.com/team.yaml, and this run was given a different configuration. '
                'Pass --link-dirs none, or --link-from naming a profile installed from the configuration this run '
                'was given, so profile "p1" stops following "team-1"; or link only projects.'
            ),
        ]
        chained = link_request_errors(
            LinkSpec(['skills'], 'team-1', 'cli', 'cli'), self._source(tmp_path / 'c', link=_record(['hooks'], 'base')),
            primary_command_name='p1', this_identity=identity, typed_selectors=False,
        )
        assert chained == [
            (
                'Profile "team-1" links content from profile "base" itself, and content links go only to a '
                'profile that holds its entries for real; use --link-from base.'
            ),
        ]
        projects_only_source = link_request_errors(
            LinkSpec(['skills'], 'team-1', 'cli', 'cli'),
            self._source(tmp_path / 'd', link=_record(['projects'], 'base')),
            primary_command_name='p1', this_identity=identity, typed_selectors=False,
        )
        assert projects_only_source == [], 'a projects-only link does not make a profile a dependent'
        unlinked_source = link_request_errors(
            LinkSpec(['skills'], 'team-1', 'cli', 'cli'),
            self._source(tmp_path / 'e', link=_record([], 'team-1', 'cli', 'yaml')),
            primary_command_name='p1', this_identity=identity, typed_selectors=False,
        )
        assert unlinked_source == [], 'a source installed with --link-dirs none holds every entry for real'

    def test_remembered_none_links_nothing_and_breaks_no_rule(self, tmp_path: Path) -> None:
        """A source re-run under a remembered none never trips the self-link rule its YAML link-from would."""
        assert link_request_errors(
            LinkSpec([], 'team-1', 'cli', 'yaml', dirs_remembered=True), self._source(tmp_path),
            primary_command_name='team-1', this_identity='x', typed_selectors=False,
        ) == []

    def test_content_links_refuse_typed_selectors(self, tmp_path: Path) -> None:
        identity = setup_environment.config_identity_of('https://example.com/team.yaml')
        errors = link_request_errors(
            LinkSpec(['skills', 'projects'], 'team-1', 'cli', 'cli'), self._source(tmp_path),
            primary_command_name='p1', this_identity=identity, typed_selectors=True,
        )
        assert errors == [
            (
                'A profile that links content (skills) takes the component selection of profile "team-1"; '
                'drop --select, --with and --without (and their variables).'
            ),
        ]


class TestContentDependents:
    """content_dependents() lists the profiles that link content from a source."""

    def test_sorted_dependents_with_content_links_only(self, tmp_path: Path) -> None:
        claude = tmp_path / '.claude'
        _manifest(claude, None)
        _manifest(claude / 'zeta', 'zeta', link=_record(['skills'], 'team-1'))
        _manifest(claude / 'alpha', 'alpha', link=_record(list(LINKABLE_PROFILE_DIRS), 'team-1'))
        _manifest(claude / 'sessions', 'sessions', link=_record(['projects'], 'team-1'))
        _manifest(claude / 'other', 'other', link=_record(['hooks'], 'base'))
        _manifest(claude / 'unlinked', 'unlinked', link=_record([], 'team-1', 'cli', 'yaml'))
        _manifest(claude / 'team-1', 'team-1', link=_record([], 'team-1', 'cli', 'yaml'))
        with patch.object(setup_environment, 'installed_profiles', _REAL_INSTALLED_PROFILES):
            assert [p.name for p in content_dependents(tmp_path, 'team-1')] == ['alpha', 'zeta'], (
                'a recorded none is not a dependency, whichever source it names'
            )
            assert [p.name for p in content_dependents(tmp_path, 'base')] == ['other']
            assert content_dependents(tmp_path, 'sessions') == []
            assert setup_environment.manifest_link(setup_environment.read_profile_manifest(
                claude / 'unlinked' / 'manifest.json',
            )) is None
            assert setup_environment.manifest_link_record(setup_environment.read_profile_manifest(
                claude / 'unlinked' / 'manifest.json',
            )) == _record([], 'team-1', 'cli', 'yaml')
        alpha = setup_environment.InstalledProfile('alpha', claude / 'alpha', claude / 'alpha' / 'manifest.json', None)
        assert setup_environment.dependents_remedy([alpha]) == [
            '  --profile alpha --link-from <other profile>   (re-point), or --profile alpha --link-dirs none   (unlink)',
        ]


class TestDependentHelpers:
    """The helpers of a run that links content."""

    def test_identity_of_a_spec_without_loading(self, tmp_path: Path) -> None:
        local = tmp_path / 'a.yaml'
        assert setup_environment.config_identity_of_spec('https://x/y.yaml') == 'https://x/y.yaml'
        expected_local = setup_environment.config_identity_of(str(local.resolve()))
        assert setup_environment.config_identity_of_spec(str(local)) == expected_local
        assert setup_environment.config_identity_of_spec('python') == setup_environment.config_identity_of(
            'https://raw.githubusercontent.com/alex-feel/claude-code-artifacts-public/main/python.yaml',
        )

    def test_dependent_config_is_the_snapshot_without_components(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        source_dir = tmp_path / '.claude' / 'team-1'
        manifest = _manifest(source_dir, 'team-1', config_source='https://example.com/team.yaml')
        manifest['version'] = '2.0.0'
        (source_dir / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        (source_dir / 'resolved-config.yaml').write_text(
            'name: Team\nagents:\n- agents/core.md\ncomponents:\n- name: core\n', encoding='utf-8',
        )
        config, source, version = setup_environment.load_dependent_config(
            LinkSource('team-1', source_dir, manifest), 'team-2',
        )
        assert config == {'name': 'Team', 'agents': ['agents/core.md']}
        assert source == 'https://example.com/team.yaml'
        assert version == '2.0.0'
        assert 'Applying the configuration profile "team-1" installed' in capsys.readouterr().out

    def test_dependent_without_a_readable_snapshot_exits(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        source_dir = tmp_path / '.claude' / 'team-1'
        manifest = _manifest(source_dir, 'team-1')
        with pytest.raises(SystemExit) as exc_info:
            setup_environment.load_dependent_config(LinkSource('team-1', source_dir, manifest), 'team-2')
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert 'resolved-config.yaml is missing or unreadable; re-run the source first: --profile team-1' in captured.err

    def test_config_without_linked_sections(self) -> None:
        config = {
            'agents': ['a.md'], 'slash-commands': ['c.md'], 'rules': ['r.md'], 'skills': [{'name': 's'}],
            'hooks': {'files': ['h.py'], 'helpers': ['x.py'], 'events': [{'event': 'Stop'}]},
            'command-defaults': {'system-prompt': 'p.md', 'mode': 'append'},
            'files-to-download': [{'source': 'f', 'dest': '~/x'}],
        }
        filtered = setup_environment.config_without_linked_sections(
            config, frozenset({'agents', 'hooks', 'prompts', 'commands'}),
        )
        assert filtered['agents'] == []
        assert filtered['slash-commands'] == []
        assert filtered['rules'] == ['r.md']
        assert filtered['skills'] == [{'name': 's'}]
        assert filtered['hooks'] == {'files': [], 'helpers': [], 'events': [{'event': 'Stop'}]}
        assert filtered['command-defaults'] == {'mode': 'append'}
        assert filtered['files-to-download'] == config['files-to-download']
        assert config['agents'] == ['a.md'], 'the original is untouched'

    def test_split_downloads_by_linked_entries(self, tmp_path: Path) -> None:
        profile = tmp_path / 'dep'
        files = [
            {'source': 'a.txt', 'dest': str(profile / 'skills' / 'a.txt')},
            {'source': 'b.txt', 'dest': str(profile / 'notes' / 'b.txt')},
            {'source': 'c.txt', 'dest': str(tmp_path / 'elsewhere' / 'c.txt')},
            'not-a-dict',
        ]
        kept, skipped = setup_environment.split_downloads_by_linked_entries(files, profile, frozenset({'skills'}))
        assert kept == files[1:]
        assert skipped == [(str(profile / 'skills' / 'a.txt'), 'skills')]


class TestEnvironmentLinkGuard:
    """guard_environment_link_change() holds back a variable that would change a profile's links."""

    def test_typed_and_unchanged_values_pass(self, tmp_path: Path) -> None:
        manifest = _manifest(tmp_path, 'dep', link=_record(['projects'], 'base'))
        typed = LinkSpec(list(LINKABLE_PROFILE_DIRS), 'base', 'cli', 'default')
        setup_environment.guard_environment_link_change(_args(link_dirs='all'), typed, manifest, 'dep')
        unchanged = LinkSpec(['projects'], 'base', 'env', 'default')
        setup_environment.guard_environment_link_change(_args(), unchanged, manifest, 'dep')

    def test_environment_change_refuses_under_yes(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        manifest = _manifest(tmp_path, 'dep', link=_record(['projects'], 'base'))
        args = _args(env={'CLAUDE_CODE_TOOLBOX_LINK_DIRS': 'all', 'CLAUDE_CODE_TOOLBOX_LINK_FROM': 'team-1'})
        spec, _ = resolve_link_spec(args, {}, manifest)
        with pytest.raises(SystemExit) as exc_info:
            setup_environment.guard_environment_link_change(args, spec, manifest, 'dep')
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        output = captured.out + captured.err
        assert 'CLAUDE_CODE_TOOLBOX_LINK_DIRS changes the linked entries of profile "dep" from projects to' in output
        assert 'CLAUDE_CODE_TOOLBOX_LINK_FROM changes the link source of profile "dep" from base to team-1' in output
        assert 'Refusing to continue without consent.' in output
        assert (
            'Pass --link-dirs skills,agents,commands,rules,hooks,output-styles,prompts,projects --link-from team-1'
        ) in output


class TestRememberedLinkWarnings:
    """A remembered link value that overrides a changed configuration value is reported."""

    def test_changed_configuration_values_are_named(self, tmp_path: Path) -> None:
        manifest = _manifest(
            tmp_path, 'dep', link=_record(['projects'], 'base', 'env', 'env'),
            yaml_values={'command_names': [], 'components': [], 'link_dirs': ['projects'], 'link_from': 'base'},
        )
        changed = {'link-dirs': ['skills'], 'link-from': 'team-1'}
        spec, _ = resolve_link_spec(_args(), changed, manifest)
        warnings = setup_environment.remembered_link_warnings(spec, changed, manifest)
        assert warnings == [
            (
                "link-dirs: using the remembered value projects [remembered]; the configuration's link-dirs changed "
                'from projects to skills since the profile was installed. Pass --link-dirs to replace the remembered '
                'value.'
            ),
            (
                "link-from: using the remembered value base [remembered]; the configuration's link-from changed from "
                'base to team-1 since the profile was installed. Pass --link-from to replace the remembered value.'
            ),
        ]
        unchanged = {'link-dirs': ['projects'], 'link-from': 'base'}
        assert setup_environment.remembered_link_warnings(spec, unchanged, manifest) == []

    def test_remembered_none_is_named_as_none(self, tmp_path: Path) -> None:
        manifest = _manifest(
            tmp_path, 'dep', link=_record([], 'base', 'cli', 'default'),
            yaml_values={'command_names': [], 'components': [], 'link_dirs': ['projects'], 'link_from': None},
        )
        changed = {'link-dirs': ['all']}
        spec, _ = resolve_link_spec(_args(), changed, manifest)
        assert setup_environment.remembered_link_warnings(spec, changed, manifest) == [
            (
                "link-dirs: using the remembered value none [remembered]; the configuration's link-dirs changed "
                f'from projects to {", ".join(LINKABLE_PROFILE_DIRS)} since the profile was installed. Pass '
                '--link-dirs to replace the remembered value.'
            ),
        ]
        assert setup_environment.remembered_link_warnings(spec, {'link-dirs': ['projects']}, manifest) == []
        assert setup_environment.link_dirs_value_text(spec) == 'the remembered link-dirs value (none)'


class TestRefreshAllConflicts:
    """--profile all refuses the link flags like every other per-run flag."""

    def test_link_flags_are_named(self, capsys: pytest.CaptureFixture[str]) -> None:
        args = _args(link_dirs='all', link_from='team-1')
        args.profile = 'all'
        assert setup_environment.refresh_all_profiles(args) == 1
        assert 'cannot be combined with --link-dirs, --link-from; drop them from the command line.' in capsys.readouterr().err

    def test_link_variables_are_named_with_the_clear_remedy(self, capsys: pytest.CaptureFixture[str]) -> None:
        args = _args(link_from='team-1', env={'CLAUDE_CODE_TOOLBOX_LINK_DIRS': 'all'})
        args.profile = 'all'
        assert setup_environment.refresh_all_profiles(args) == 1
        assert (
            'cannot be combined with CLAUDE_CODE_TOOLBOX_LINK_DIRS, --link-from; drop them from the command line and clear '
            'CLAUDE_CODE_TOOLBOX_LINK_DIRS (unset CLAUDE_CODE_TOOLBOX_LINK_DIRS, or Remove-Item '
            'Env:CLAUDE_CODE_TOOLBOX_LINK_DIRS in PowerShell).'
        ) in capsys.readouterr().err


class TestWiredHookFiles:
    """wired_hook_file_names() lists what a profile's config.json wires into hooks/."""

    def test_commands_configs_and_status_line_once_each(self) -> None:
        config = {
            'hooks': {
                'files': ['hooks/lint.py', 'configs/lint.yaml', 'hooks/status.py'],
                'events': [
                    {'event': 'PostToolUse', 'type': 'command', 'command': 'lint.py', 'config': 'lint.yaml?x=1'},
                    {'event': 'Stop', 'type': 'command', 'command': 'lint.py'},
                    {'event': 'Stop', 'type': 'command', 'command': '/usr/bin/notify'},
                    {'event': 'PreToolUse', 'type': 'prompt', 'prompt': 'check'},
                ],
            },
            'status-line': {'file': 'status.py', 'config': 'status.yaml'},
        }
        assert setup_environment.wired_hook_file_names(config) == ['lint.py', 'lint.yaml', 'status.py', 'status.yaml']

    def test_missing_files_are_named_by_path(self, tmp_path: Path) -> None:
        config = {'hooks': {'files': ['hooks/lint.py'], 'events': [{'event': 'Stop', 'command': 'lint.py'}]}}
        (tmp_path / 'lint.py').write_text('', encoding='utf-8')
        assert setup_environment.missing_wired_hook_files(config, tmp_path) == []
        (tmp_path / 'lint.py').unlink()
        assert setup_environment.missing_wired_hook_files(config, tmp_path) == [str(tmp_path / 'lint.py')]


class TestSourceFirstOrder:
    """order_profiles_source_first() runs every source before its content dependents."""

    def test_dependents_move_after_every_other_profile(self, tmp_path: Path) -> None:
        claude = tmp_path / '.claude'
        _manifest(claude, None)
        _manifest(claude / 'alpha-dep', 'alpha-dep', link=_record(['skills'], 'zeta'))
        _manifest(claude / 'mid', 'mid', link=_record(['projects'], 'base'))
        _manifest(claude / 'zeta', 'zeta')
        with patch.object(setup_environment, 'installed_profiles', _REAL_INSTALLED_PROFILES):
            ordered = setup_environment.order_profiles_source_first(setup_environment.installed_profiles(tmp_path))
        assert [p.name for p in ordered] == ['base', 'mid', 'zeta', 'alpha-dep']


class TestRefreshDependents:
    """refresh_dependents() runs each dependent through the program this run started from."""

    def _dependents(self, tmp_path: Path) -> list[setup_environment.InstalledProfile]:
        claude = tmp_path / '.claude'
        profiles = []
        for name in ('team-2', 'team-3'):
            _manifest(claude / name, name, link=_record(list(LINKABLE_PROFILE_DIRS), 'team-1'))
            profiles.append(setup_environment.InstalledProfile(name, claude / name, claude / name / 'manifest.json', None))
        return profiles

    def test_script_argv_shape_environment_and_results(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        calls: list[tuple[list[str], dict[str, str]]] = []

        def _run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append((argv, cast(dict[str, str], kwargs['env'])))
            return subprocess.CompletedProcess(argv, 1 if 'team-3' in argv else 0)

        with (
            patch.object(setup_environment.subprocess, 'run', side_effect=_run),
            patch.dict(os.environ, {
                'CLAUDE_CODE_TOOLBOX_LINK_DIRS': 'leak', 'CLAUDE_CODE_TOOLBOX_ENV_CONFIG': 'leak',
                'CLAUDE_CONFIG_DIR': '/x', 'GITHUB_TOKEN': 't', 'CLAUDE_CODE_TOOLBOX_ENV_AUTH': 'h:v',
            }),
            patch('sys.argv', ['/repo/scripts/setup_environment.py', 'team.yaml', '--yes']),
            patch.object(setup_environment.platform, 'system', return_value='Linux'),
        ):
            results = setup_environment.refresh_dependents(self._dependents(tmp_path))

        script = '/repo/scripts/setup_environment.py'
        assert [argv for argv, _ in calls] == [
            [sys.executable, script, '--profile', 'team-2', '--yes', '--child-run', '--skip-install', '--no-admin'],
            [sys.executable, script, '--profile', 'team-3', '--yes', '--child-run', '--skip-install', '--no-admin'],
        ]
        for _, env in calls:
            assert 'CLAUDE_CODE_TOOLBOX_LINK_DIRS' not in env
            assert 'CLAUDE_CODE_TOOLBOX_ENV_CONFIG' not in env
            assert 'CLAUDE_CONFIG_DIR' not in env
            assert env['GITHUB_TOKEN'] == 't'
            assert env['CLAUDE_CODE_TOOLBOX_ENV_AUTH'] == 'h:v'
        assert results == [
            setup_environment.DependentResult('team-2', 0, False),
            setup_environment.DependentResult('team-3', 1, False),
        ]
        assert [result.line() for result in results] == [
            'team-2: ok',
            'team-3: failed (exit code 1); retry with --profile team-3',
        ]
        output = capsys.readouterr().out
        assert '=== Dependent profile team-2 ===' in output

    def test_packaged_entry_point_starts_dependents_through_the_cli_module(self, tmp_path: Path) -> None:
        calls: list[list[str]] = []

        def _run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0)

        with (
            patch.object(setup_environment.subprocess, 'run', side_effect=_run),
            patch.object(setup_environment, '__name__', 'cc_toolbox.setup_environment'),
            patch('sys.argv', ['/venv/bin/cc-toolbox', 'setup', '--profile', 'team-1']),
        ):
            setup_environment.refresh_dependents(self._dependents(tmp_path)[:1])
        assert calls == [[
            sys.executable, '-m', 'cc_toolbox.cli', 'setup', '--profile', 'team-2', '--yes', '--child-run',
            '--skip-install', '--no-admin',
        ]]

    def test_run_all_commands_is_forwarded_to_every_child(self, tmp_path: Path) -> None:
        """A source run given --run-all-commands hands it to each dependent, whose environment lost the twin."""
        calls: list[list[str]] = []

        def _run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0)

        with (
            patch.object(setup_environment.subprocess, 'run', side_effect=_run),
            patch('sys.argv', ['/repo/scripts/setup_environment.py', '--profile', 'team-1', '--run-all-commands']),
        ):
            setup_environment.refresh_dependents(self._dependents(tmp_path), run_all_commands=True)
        script = '/repo/scripts/setup_environment.py'
        assert calls == [
            [sys.executable, script, '--profile', name, '--yes', '--child-run', '--skip-install', '--no-admin',
             '--run-all-commands']
            for name in ('team-2', 'team-3')
        ]

    def test_unstartable_child_and_elevation_remedy(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """The remedy names the elevated terminal only for a global npm install the dependent's run itself executes."""
        dependents = self._dependents(tmp_path)[:1]
        (dependents[0].directory / 'resolved-config.yaml').write_text(
            'name: Team\ndependencies:\n  common:\n  - npm install -g some-cli\n', encoding='utf-8',
        )
        remedy = (
            'team-2: failed (exit code 1); retry with --profile team-2 from an elevated terminal '
            '(a global npm install needs administrator rights the run could not request)'
        )
        with (
            patch.object(setup_environment.subprocess, 'run', side_effect=OSError('no interpreter')),
            patch.object(setup_environment.platform, 'system', return_value='Windows'),
            patch.object(setup_environment, 'is_admin', return_value=False),
            patch.object(setup_environment, 'get_real_user_home', return_value=tmp_path),
            patch('sys.argv', ['/repo/scripts/setup_environment.py']),
        ):
            # The source runs the same command, so the dependent leaves it out and needs no elevation for it
            left_to_source = setup_environment.refresh_dependents(
                dependents, source_commands=frozenset({'npm install -g some-cli'}),
            )
            # The source runs something else: the dependent runs the install itself
            own_install = setup_environment.refresh_dependents(dependents, source_commands=frozenset({'uv tool install x'}))
            # --run-all-commands makes the dependent run every command, the shared one included
            forced = setup_environment.refresh_dependents(
                dependents, source_commands=frozenset({'npm install -g some-cli'}), run_all_commands=True,
            )
        assert left_to_source == [setup_environment.DependentResult('team-2', 1, False)]
        assert left_to_source[0].line() == 'team-2: failed (exit code 1); retry with --profile team-2'
        assert own_install == [setup_environment.DependentResult('team-2', 1, True)]
        assert own_install[0].line() == remedy
        assert forced == [setup_environment.DependentResult('team-2', 1, True)]
        assert 'Cannot start the run of profile "team-2": no interpreter' in capsys.readouterr().err


class TestDependentRefreshStep:
    """run_dependent_refresh_step() prints Step 23 and runs only when there is something to run."""

    def test_no_dependents_and_child_run(self, capsys: pytest.CaptureFixture[str]) -> None:
        """A child run -- of --profile all, or a dependent a source refreshes -- leaves the step to its parent."""
        with patch.object(setup_environment, 'refresh_dependents') as refresh:
            assert setup_environment.run_dependent_refresh_step([], source_name='team-1', child_run=False) == []
            dep = setup_environment.InstalledProfile('d', Path('/d'), Path('/d/manifest.json'), None)
            assert setup_environment.run_dependent_refresh_step([dep], source_name='team-1', child_run=True) == []
            assert setup_environment.run_dependent_refresh_step([], source_name='team-2', child_run=True) == []
        refresh.assert_not_called()
        output = capsys.readouterr().out
        assert output.count('Step 23: No installed profile links content from "team-1"') == 1
        assert output.count('Step 23: Dependent profiles are refreshed by the run that started this one') == 2
        assert '--profile all' not in output
        assert 'team-2' not in output

    def test_dependents_are_refreshed(self, capsys: pytest.CaptureFixture[str]) -> None:
        dep = setup_environment.InstalledProfile('d', Path('/d'), Path('/d/manifest.json'), None)
        expected = [setup_environment.DependentResult('d', 0, False)]
        with patch.object(setup_environment, 'refresh_dependents', return_value=expected) as refresh:
            assert setup_environment.run_dependent_refresh_step([dep], source_name='s', child_run=False) == expected
        refresh.assert_called_once_with([dep], source_commands=frozenset(), run_all_commands=False)
        assert 'Step 23: Refreshing 1 dependent profile(s): d...' in capsys.readouterr().out

    def test_source_commands_and_the_flag_reach_the_children(self) -> None:
        """The source's own commands and --run-all-commands travel to refresh_dependents()."""
        dep = setup_environment.InstalledProfile('d', Path('/d'), Path('/d/manifest.json'), None)
        with patch.object(setup_environment, 'refresh_dependents', return_value=[]) as refresh:
            setup_environment.run_dependent_refresh_step(
                [dep], source_name='s', child_run=False,
                source_commands=frozenset({'npm install -g x'}), run_all_commands=True,
            )
        refresh.assert_called_once_with([dep], source_commands=frozenset({'npm install -g x'}), run_all_commands=True)


class TestUnrefreshedLines:
    """unrefreshed_profile_lines() leaves the refreshed dependents out."""

    def test_refreshed_dependents_are_omitted(self, tmp_path: Path) -> None:
        claude = tmp_path / '.claude'
        _manifest(claude, None)
        _manifest(claude / 'a', 'a')
        _manifest(claude / 'b', 'b')
        with patch.object(setup_environment, 'installed_profiles', _REAL_INSTALLED_PROFILES):
            assert setup_environment.unrefreshed_profile_lines(tmp_path, 'a') == ['base (--profile base)', 'b (--profile b)']
            assert setup_environment.unrefreshed_profile_lines(tmp_path, 'a', frozenset({'b'})) == ['base (--profile base)']


class TestSkillsSyncSettings:
    """apply_skills_sync_settings() keeps the claude.ai skill sync out of a linked skills/ directory."""

    def test_linked_skills_inject_the_disable(self) -> None:
        settings, warnings, auto = setup_environment.apply_skills_sync_settings({'theme': 'dark'}, links_skills=True)
        assert settings == {'theme': 'dark', 'syncClaudeAiSkills': False}
        assert warnings == []
        assert auto == ['user-settings.syncClaudeAiSkills: false']

    def test_absent_user_settings_become_the_disable_alone(self) -> None:
        settings, warnings, auto = setup_environment.apply_skills_sync_settings(None, links_skills=True)
        assert settings == {'syncClaudeAiSkills': False}
        assert warnings == []
        assert auto == ['user-settings.syncClaudeAiSkills: false']

    def test_user_value_is_kept_with_a_warning(self) -> None:
        settings, warnings, auto = setup_environment.apply_skills_sync_settings(
            {'syncClaudeAiSkills': True}, links_skills=True,
        )
        assert settings == {'syncClaudeAiSkills': True}
        assert warnings == [
            'User set user-settings.syncClaudeAiSkills to True (linked skills intent is False). Respecting user value.',
        ]
        assert auto == []

    def test_user_null_is_kept_with_a_warning(self) -> None:
        settings, warnings, auto = setup_environment.apply_skills_sync_settings(
            {'syncClaudeAiSkills': None}, links_skills=True,
        )
        assert settings == {'syncClaudeAiSkills': None}
        assert len(warnings) == 1
        assert auto == []

    def test_matching_user_value_is_silent(self) -> None:
        settings, warnings, auto = setup_environment.apply_skills_sync_settings(
            {'syncClaudeAiSkills': False}, links_skills=True,
        )
        assert settings == {'syncClaudeAiSkills': False}
        assert warnings == []
        assert auto == []

    def test_without_linked_skills_nothing_changes(self) -> None:
        assert setup_environment.apply_skills_sync_settings(None, links_skills=False) == (None, [], [])
        assert setup_environment.apply_skills_sync_settings({'theme': 'dark'}, links_skills=False) == (
            {'theme': 'dark'}, [], [],
        )
