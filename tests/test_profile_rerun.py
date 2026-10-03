"""Tests for re-running installed profiles from their manifests.

A profile's manifest records the configuration it was installed from, the
command names and component delta a run typed or took from the environment,
and what the run wrote. A later run ranks its sources per key -- typed,
environment, remembered, configuration, default -- and the guards hold a
run back before any write when the environment would rename a profile or a
different configuration would re-provision it.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from scripts import setup_environment
from scripts.setup_environment import CommandNames
from scripts.setup_environment import ComponentSelection
from scripts.setup_environment import ProfileResidue
from scripts.setup_environment import resolve_command_names

_REAL_READ_TARGET_MANIFEST = setup_environment._read_target_manifest
_REAL_INSTALLED_PROFILES = setup_environment.installed_profiles


def _args(
    command_names: str | None = None,
    *,
    profile: str | None = None,
    env: dict[str, str] | None = None,
    select: str | None = None,
    with_: str | None = None,
    without: str | None = None,
    yes: bool = False,
    dry_run: bool = False,
    switch_config: bool = False,
    config: str | None = None,
) -> argparse.Namespace:
    """Build resolved arguments the way main() does."""
    namespace = argparse.Namespace(
        config=config,
        yes=yes,
        dry_run=dry_run,
        skip_install=False,
        no_admin=False,
        env_vars=None,
        select=select,
        with_=with_,
        without=without,
        list_components=False,
        command_names=command_names,
        profile=profile,
        switch_config=switch_config,
    )
    cleared = {
        twin.variable: '' for twin in setup_environment.ENV_TWINS
    }
    with patch.dict(os.environ, {**cleared, **(env or {})}, clear=False):
        return setup_environment.resolve_args(namespace)


def _manifest(
    directory: Path,
    name: str | None,
    command_names: list[str],
    *,
    origin: str | None = 'cli',
    components: dict[str, str | None] | None = None,
    components_origin: str = 'yaml',
    config_source: str = 'https://example.com/profile.yaml',
    yaml_values: dict[str, Any] | None = None,
    **records: Any,
) -> dict[str, Any]:
    """Write a manifest in the current shape and return it."""
    directory.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        'name': name,
        'version': None,
        'claude_code_version': None,
        'config_source': config_source,
        'config_source_url': config_source if config_source.startswith('http') else None,
        'config_source_type': 'url' if config_source.startswith('http') else 'local',
        'config_identity': setup_environment.config_identity_of(config_source),
        'config_digest': None,
        'installed_at': '2026-01-01T00:00:00+00:00',
        'command_names': command_names,
        'components': components,
        'link': None,
        'origins': {'command_names': origin, 'components': components_origin},
        'yaml_values': yaml_values if yaml_values is not None else {'command_names': [], 'components': []},
        'machine_wide_destinations': [],
        'os_env_written': [],
        'settings_keys_written': [],
        'mcp_servers': [],
        'files_written': [],
    }
    manifest.update(records)
    (directory / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    return manifest


class TestConfigIdentity:
    """A configuration's identity is its URL or its normalized absolute path."""

    def test_url_is_its_own_identity(self) -> None:
        assert setup_environment.config_identity_of('https://x/y.yaml') == 'https://x/y.yaml'

    def test_local_path_is_made_absolute(self, tmp_path: Path) -> None:
        identity = setup_environment.config_identity_of(str(tmp_path / 'sub' / '..' / 'env.yaml'))
        assert identity == setup_environment._normalize_config_dir_key(str(tmp_path / 'env.yaml'))

    @pytest.mark.skipif(sys.platform != 'win32', reason='case-insensitive comparison applies on Windows')
    def test_windows_case_and_separators_do_not_matter(self, tmp_path: Path) -> None:
        upper = str(tmp_path / 'Env.yaml').upper()
        lower = str(tmp_path / 'Env.yaml').lower().replace('\\', '/')
        assert setup_environment.config_identity_of(upper) == setup_environment.config_identity_of(lower)


class TestResolvedConfigSnapshot:
    """resolved-config.yaml holds the installed configuration without the profile's names."""

    def test_snapshot_strips_command_names_and_copies_deeply(self) -> None:
        config: dict[str, Any] = {
            'name': 'E', 'command-names': ['a', 'b'], 'agents': ['x.md'], 'user-settings': {'env': {'K': 'v'}},
        }
        snapshot = setup_environment.resolved_config_snapshot(config)
        assert snapshot == {'name': 'E', 'agents': ['x.md'], 'user-settings': {'env': {'K': 'v'}}}
        snapshot['user-settings']['env']['K'] = 'changed'
        assert config['user-settings']['env']['K'] == 'v'

    def test_rendering_is_deterministic_and_hashed(self) -> None:
        config = {'name': 'E', 'command-names': ['a'], 'agents': ['x.md']}
        first = setup_environment.render_resolved_config(config)
        second = setup_environment.render_resolved_config(dict(config))
        assert first == second
        assert 'command-names' not in first
        assert setup_environment.config_digest_of(first) == setup_environment.config_digest_of(second)
        assert len(setup_environment.config_digest_of(first)) == 64


class TestManifestIdentity:
    """A manifest's identity is recorded, or derived for manifests written without one."""

    def test_recorded_identity_wins(self) -> None:
        manifest = {'config_identity': 'https://recorded', 'config_source_url': 'https://other'}
        assert setup_environment.manifest_config_identity(manifest) == 'https://recorded'

    def test_legacy_url_source(self) -> None:
        manifest = {'config_source': 'https://example.com/env.yaml', 'config_source_url': None, 'config_source_type': 'url'}
        assert setup_environment.manifest_config_identity(manifest) == 'https://example.com/env.yaml'

    def test_legacy_repository_name_resolves_to_the_fetched_url(self) -> None:
        manifest = {'config_source': 'python', 'config_source_url': None, 'config_source_type': 'repo'}
        assert setup_environment.manifest_config_identity(manifest) == (
            'https://raw.githubusercontent.com/alex-feel/claude-code-artifacts-public/main/python.yaml'
        )

    def test_legacy_source_url_is_preferred_over_the_typed_name(self) -> None:
        manifest = {'config_source': 'python', 'config_source_url': 'https://mirror/python.yaml', 'config_source_type': 'repo'}
        assert setup_environment.manifest_config_identity(manifest) == 'https://mirror/python.yaml'

    def test_legacy_absolute_local_path(self, tmp_path: Path) -> None:
        source = str(tmp_path / 'env.yaml')
        manifest = {'config_source': source, 'config_source_url': None, 'config_source_type': 'local'}
        assert setup_environment.manifest_config_identity(manifest) == setup_environment.config_identity_of(source)

    def test_legacy_relative_local_path_resolves_only_from_its_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        manifest = {'config_source': './env.yaml', 'config_source_url': None, 'config_source_type': 'local'}
        assert setup_environment.manifest_config_identity(manifest) is None
        (tmp_path / 'env.yaml').write_text('name: x\n', encoding='utf-8')
        monkeypatch.chdir(tmp_path)
        assert setup_environment.manifest_config_identity(manifest) == setup_environment.config_identity_of('./env.yaml')


class TestInstalledProfiles:
    """The registry lists the base first, then the isolated profiles in sorted order."""

    def test_order_and_unreadable_manifest(self, tmp_path: Path) -> None:
        claude_dir = tmp_path / '.claude'
        _manifest(claude_dir / 'zeta', 'zeta', ['zeta'])
        _manifest(claude_dir / 'alpha', 'alpha', ['alpha'])
        _manifest(claude_dir, None, [], origin=None)
        (claude_dir / 'broken').mkdir()
        (claude_dir / 'broken' / 'manifest.json').write_text('{not json', encoding='utf-8')
        (claude_dir / 'no-manifest').mkdir()

        profiles = _REAL_INSTALLED_PROFILES(tmp_path)

        assert [profile.name for profile in profiles] == ['base', 'alpha', 'broken', 'zeta']
        assert profiles[0].directory == claude_dir
        assert profiles[2].manifest is None
        assert profiles[1].manifest is not None
        assert profiles[1].manifest['name'] == 'alpha'

    def test_no_claude_dir(self, tmp_path: Path) -> None:
        assert _REAL_INSTALLED_PROFILES(tmp_path) == []

    def test_read_profile_manifest_reports_invalid_content(self, tmp_path: Path) -> None:
        path = tmp_path / 'manifest.json'
        assert setup_environment.read_profile_manifest(path) is None
        path.write_text('[]', encoding='utf-8')
        with pytest.raises(ValueError, match='does not hold a JSON object'):
            setup_environment.read_profile_manifest(path)
        path.write_text('{oops', encoding='utf-8')
        with pytest.raises(ValueError, match='not valid JSON'):
            setup_environment.read_profile_manifest(path)


class TestRememberedCommandNames:
    """Only typed and environment names are remembered; configuration names are re-read."""

    @pytest.mark.parametrize('origin', ['cli', 'env'])
    def test_typed_or_environment_names_are_remembered(self, origin: str) -> None:
        manifest = {'command_names': ['p', 'a'], 'origins': {'command_names': origin}}
        assert setup_environment.remembered_command_names(manifest) == (['p', 'a'], origin)

    @pytest.mark.parametrize('origin', ['yaml', 'default', None])
    def test_configuration_names_are_not_remembered(self, origin: str | None) -> None:
        manifest = {'command_names': ['p', 'a'], 'origins': {'command_names': origin}}
        assert setup_environment.remembered_command_names(manifest) == (None, None)

    def test_manifest_without_origins_is_not_remembered(self) -> None:
        assert setup_environment.remembered_command_names({'command_names': ['p']}) == (None, None)
        assert setup_environment.remembered_command_names(None) == (None, None)


class TestProfileTargetName:
    """The profile a run installs into comes from --profile, the typed primary, or the configuration."""

    def test_profile_flag_wins(self) -> None:
        assert setup_environment.profile_target_name(_args('typed', profile='chosen'), {'command-names': ['y']}) == 'chosen'

    def test_profile_base_is_the_base(self) -> None:
        assert setup_environment.profile_target_name(_args(profile='base'), {'command-names': ['y']}) is None

    def test_typed_primary_then_configuration_then_base(self) -> None:
        assert setup_environment.profile_target_name(_args('t,a'), {'command-names': ['y']}) == 't'
        assert setup_environment.profile_target_name(_args(), {'command-names': ['y', 'z']}) == 'y'
        assert setup_environment.profile_target_name(_args(), {}) is None


class TestTypedListRules:
    """A typed list sets the aliases; NAME,none drops them; a single NAME selects an installed profile."""

    def test_list_sets_the_aliases_whatever_the_manifest_remembers(self) -> None:
        manifest = {'command_names': ['p', 'old'], 'origins': {'command_names': 'cli'}}
        resolved, errors = resolve_command_names(_args('p,new'), {'command-names': ['p', 'yaml-alias']}, manifest)
        assert errors == []
        assert resolved == CommandNames(['p', 'new'], 'cli')

    def test_name_none_drops_every_alias(self) -> None:
        manifest = {'command_names': ['p', 'old'], 'origins': {'command_names': 'cli'}}
        resolved, errors = resolve_command_names(_args('p,none'), {'command-names': ['p', 'yaml-alias']}, manifest)
        assert errors == []
        assert resolved == CommandNames(['p'], 'cli')

    def test_single_name_on_a_new_profile_is_the_whole_list(self) -> None:
        resolved, errors = resolve_command_names(_args('p'), {'command-names': ['p', 'yaml-alias']}, None)
        assert errors == []
        assert resolved == CommandNames(['p'], 'cli')

    def test_single_name_on_an_installed_profile_keeps_the_remembered_aliases(self) -> None:
        manifest = {'command_names': ['p', 'old'], 'origins': {'command_names': 'env'}}
        resolved, errors = resolve_command_names(_args('p'), {'command-names': ['p', 'yaml-alias']}, manifest)
        assert errors == []
        assert resolved == CommandNames(['p', 'old'], 'env', remembered=True)

    def test_single_name_on_an_installed_profile_re_reads_the_configuration(self) -> None:
        manifest = {'command_names': ['p', 'old'], 'origins': {'command_names': 'yaml'}}
        resolved, errors = resolve_command_names(_args('p'), {'command-names': ['p', 'yaml-alias']}, manifest)
        assert errors == []
        assert resolved == CommandNames(['p', 'yaml-alias'], 'yaml')

    def test_single_name_on_an_installed_profile_falls_back_to_itself(self) -> None:
        manifest = {'command_names': ['p', 'old'], 'origins': {'command_names': 'yaml'}}
        resolved, errors = resolve_command_names(_args('p'), {'command-names': ['other']}, manifest)
        assert errors == []
        assert resolved == CommandNames(['p'], 'cli')

    def test_environment_single_name_selects_too(self) -> None:
        manifest = {'command_names': ['p', 'old'], 'origins': {'command_names': 'cli'}}
        args = _args(env={'CLAUDE_CODE_TOOLBOX_COMMAND_NAMES': 'p'})
        resolved, errors = resolve_command_names(args, {}, manifest)
        assert errors == []
        assert resolved == CommandNames(['p', 'old'], 'cli', remembered=True)


class TestProfileFlagRules:
    """--profile NAME re-runs a profile with the same ranking and no typed value."""

    def test_remembered_names_win(self) -> None:
        manifest = {'command_names': ['p', 'a'], 'origins': {'command_names': 'cli'}}
        resolved, errors = resolve_command_names(_args(profile='p'), {'command-names': ['p', 'y']}, manifest)
        assert errors == []
        assert resolved == CommandNames(['p', 'a'], 'cli', remembered=True)

    def test_configuration_names_are_re_read(self) -> None:
        manifest = {'command_names': ['p', 'a'], 'origins': {'command_names': 'yaml'}}
        resolved, errors = resolve_command_names(_args(profile='p'), {'command-names': ['p', 'y']}, manifest)
        assert errors == []
        assert resolved == CommandNames(['p', 'y'], 'yaml')

    def test_configuration_whose_primary_differs_is_refused(self) -> None:
        manifest = {'command_names': ['p'], 'origins': {'command_names': 'yaml'}}
        _resolved, errors = resolve_command_names(_args(profile='p'), {'command-names': ['other', 'y']}, manifest)
        assert len(errors) == 1
        assert 'start with "other", but --profile selects "p"' in errors[0]
        assert '--command-names p[,ALIAS...]' in errors[0]

    def test_default_is_the_name_alone(self) -> None:
        manifest = {'command_names': ['p'], 'origins': {'command_names': 'yaml'}}
        resolved, errors = resolve_command_names(_args(profile='p'), {}, manifest)
        assert errors == []
        assert resolved == CommandNames(['p'], 'default')

    def test_typed_primary_other_than_the_profile_is_refused(self) -> None:
        _resolved, errors = resolve_command_names(_args('q,a', profile='p'), {}, {'command_names': ['p']})
        assert errors == [
            (
                '--command-names names the profile "q", but --profile selects "p"; clear --command-names, '
                'or pass --command-names p[,ALIAS...] to change the aliases of "p".'
            ),
        ]

    def test_environment_primary_other_than_the_profile_names_both_variables(self) -> None:
        args = _args(env={'CLAUDE_CODE_TOOLBOX_COMMAND_NAMES': 'q', 'CLAUDE_CODE_TOOLBOX_PROFILE': 'p'})
        _resolved, errors = resolve_command_names(args, {}, {'command_names': ['p']})
        assert len(errors) == 1
        assert (
            'CLAUDE_CODE_TOOLBOX_COMMAND_NAMES names the profile "q", but CLAUDE_CODE_TOOLBOX_PROFILE selects "p"'
        ) in errors[0]

    def test_typed_aliases_for_the_profile_proceed(self) -> None:
        resolved, errors = resolve_command_names(_args('p,new', profile='p'), {}, {'command_names': ['p', 'old']})
        assert errors == []
        assert resolved == CommandNames(['p', 'new'], 'cli')


class TestProfileBaseRules:
    """--profile base re-runs the base profile, which has no command names."""

    def test_base_without_configuration_names(self) -> None:
        resolved, errors = resolve_command_names(_args(profile='base'), {}, {'command_names': []})
        assert errors == []
        assert resolved == CommandNames([], None)

    def test_configuration_names_are_refused(self) -> None:
        _resolved, errors = resolve_command_names(_args(profile='base'), {'command-names': ['p', 'a']}, {'command_names': []})
        assert len(errors) == 1
        assert 'declares command-names p, a, but --profile base re-runs the base profile' in errors[0]
        assert '--command-names p' in errors[0]

    def test_typed_names_are_refused(self) -> None:
        _resolved, errors = resolve_command_names(_args('p', profile='base'), {}, {'command_names': []})
        assert len(errors) == 1
        assert 'selects the base profile, which has no command names; clear --command-names' in errors[0]


class TestConfigurationRunRemembers:
    """A run by configuration takes the remembered names of the configuration's own profile."""

    def test_remembered_names_of_the_yaml_primary_win(self) -> None:
        manifest = {'command_names': ['p', 'typed-alias'], 'origins': {'command_names': 'cli'}}
        resolved, errors = resolve_command_names(_args(), {'command-names': ['p', 'yaml-alias']}, manifest)
        assert errors == []
        assert resolved == CommandNames(['p', 'typed-alias'], 'cli', remembered=True)

    def test_yaml_names_apply_when_the_manifest_recorded_yaml(self) -> None:
        manifest = {'command_names': ['p', 'old'], 'origins': {'command_names': 'yaml'}}
        resolved, errors = resolve_command_names(_args(), {'command-names': ['p', 'new']}, manifest)
        assert errors == []
        assert resolved == CommandNames(['p', 'new'], 'yaml')


class TestRememberedValueWarnings:
    """A remembered value that overrides a configuration value which changed is reported."""

    def test_command_names_warning(self) -> None:
        names = CommandNames(['p', 'a'], 'cli', remembered=True)
        manifest = {'yaml_values': {'command_names': ['p', 'x']}}
        warnings = setup_environment.remembered_value_warnings(names, None, ['p', 'y'], manifest)
        assert warnings == [
            (
                "command-names: using the remembered value p, a [remembered]; the configuration's command-names "
                'changed from p, x to p, y since the profile was installed. Pass --command-names to replace the '
                'remembered value.'
            ),
        ]

    def test_no_warning_when_the_configuration_did_not_change(self) -> None:
        names = CommandNames(['p', 'a'], 'cli', remembered=True)
        manifest = {'yaml_values': {'command_names': ['p', 'x']}}
        assert setup_environment.remembered_value_warnings(names, None, ['p', 'x'], manifest) == []

    def test_no_warning_for_a_value_that_is_not_remembered(self) -> None:
        names = CommandNames(['p', 'y'], 'yaml')
        manifest = {'yaml_values': {'command_names': ['p', 'x']}}
        assert setup_environment.remembered_value_warnings(names, None, ['p', 'y'], manifest) == []

    def test_components_warning(self) -> None:
        selection = ComponentSelection(is_active=True, selected=['core'], remembered=True, defaults=['core', 'new'])
        manifest = {'yaml_values': {'components': ['core']}}
        warnings = setup_environment.remembered_value_warnings(CommandNames([], None), selection, [], manifest)
        assert len(warnings) == 1
        assert 'components: using the remembered selection core [remembered]' in warnings[0]
        assert 'changed from core to core, new' in warnings[0]


class TestRememberedComponentDelta:
    """The component delta a run typed is applied to a later run that types none."""

    def test_delta_fills_absent_selectors_and_marks_them_remembered(self) -> None:
        manifest = {'components': {'select': 'core', 'with': None, 'without': 'lab'}, 'origins': {'components': 'env'}}
        args = _args()
        setup_environment.apply_remembered_component_delta(args, manifest)
        assert (args.select, args.with_, args.without) == ('core', None, 'lab')
        assert args.origins['select'] == 'remembered'
        assert args.origins['without'] == 'remembered'
        assert args.origins['components'] == 'env'

    def test_typed_selectors_are_left_alone(self) -> None:
        manifest = {'components': {'select': 'core', 'with': None, 'without': None}, 'origins': {'components': 'cli'}}
        args = _args(with_='extra')
        setup_environment.apply_remembered_component_delta(args, manifest)
        assert (args.select, args.with_, args.without) == (None, 'extra', None)

    @pytest.mark.parametrize('origin', ['yaml', None])
    def test_author_defaults_are_not_remembered(self, origin: str | None) -> None:
        manifest = {'components': {'select': 'core', 'with': None, 'without': None}, 'origins': {'components': origin}}
        assert setup_environment.remembered_component_delta(manifest) == (None, None)

    def test_empty_delta_is_not_remembered(self) -> None:
        manifest = {'components': {'select': None, 'with': None, 'without': None}, 'origins': {'components': 'cli'}}
        assert setup_environment.remembered_component_delta(manifest) == (None, None)


COMPONENTS: list[dict[str, Any]] = [
    {'name': 'core', 'includes': {'agents': ['a.md']}},
    {'name': 'extra', 'default': False, 'includes': {'agents': ['b.md']}},
]


class TestSelectionRecordsItsDelta:
    """resolve_component_selection() records how the selection came about."""

    def test_author_defaults_leave_no_delta(self) -> None:
        selection = setup_environment.resolve_component_selection(COMPONENTS, _args())
        assert selection.delta is None
        assert selection.origin == 'yaml'
        assert selection.remembered is False
        assert selection.defaults == ['core']

    def test_typed_selectors_are_the_delta(self) -> None:
        selection = setup_environment.resolve_component_selection(COMPONENTS, _args(with_='extra'))
        assert selection.delta == {'select': None, 'with': 'extra', 'without': None}
        assert selection.origin == 'cli'
        assert selection.selected == ['core', 'extra']

    def test_environment_selectors_are_marked_env(self) -> None:
        selection = setup_environment.resolve_component_selection(COMPONENTS, _args(env={'CLAUDE_CODE_TOOLBOX_WITH': 'extra'}))
        assert selection.origin == 'env'

    def test_remembered_delta_keeps_its_recorded_origin(self) -> None:
        args = _args()
        manifest = {'components': {'select': None, 'with': 'extra', 'without': None}, 'origins': {'components': 'env'}}
        setup_environment.apply_remembered_component_delta(args, manifest)
        selection = setup_environment.resolve_component_selection(COMPONENTS, args)
        assert selection.remembered is True
        assert selection.origin == 'env'
        assert selection.selected == ['core', 'extra']

    def test_picker_change_is_recorded_as_typed(self) -> None:
        selection = setup_environment.resolve_component_selection(COMPONENTS, _args(), picker=lambda _seed: ['core', 'extra'])
        assert selection.delta == {'select': 'core,extra', 'with': None, 'without': None}
        assert selection.origin == 'cli'

    def test_picker_confirming_the_seed_leaves_no_delta(self) -> None:
        selection = setup_environment.resolve_component_selection(COMPONENTS, _args(), picker=lambda seed: seed)
        assert selection.delta is None
        assert selection.origin == 'yaml'


class TestInstallRecords:
    """The manifest records what a run writes, with installer-mirroring paths."""

    def test_planned_profile_files(self, tmp_path: Path) -> None:
        profile_dir = tmp_path / '.claude' / 'p'
        config = {
            'agents': ['agents/a.md?ref=x'],
            'slash-commands': ['commands/c.md'],
            'rules': ['rules/r.md'],
            'hooks': {'files': ['hooks/h.py'], 'helpers': ['hooks/helper.py']},
            'skills': [{'name': 'sk', 'files': ['SKILL.md', 'scripts/run.py']}],
            'command-defaults': {'system-prompt': 'prompts/sys.md'},
            'files-to-download': [
                {'source': 'x/in.txt', 'dest': f'{profile_dir}/extra/in.txt'},
                {'source': 'x/out.txt', 'dest': str(tmp_path / 'elsewhere' / 'out.txt')},
            ],
        }
        assert setup_environment.planned_profile_files(config, profile_dir) == [
            'agents/a.md', 'commands/c.md', 'extra/in.txt', 'hooks/h.py', 'hooks/helper.py',
            'prompts/sys.md', 'rules/r.md', 'skills/sk/SKILL.md', 'skills/sk/scripts/run.py',
        ]

    def test_machine_wide_download_records(self, tmp_path: Path) -> None:
        claude_dir = tmp_path / '.claude'
        outside = tmp_path / 'shared' / 'file.txt'
        outside.parent.mkdir()
        outside.write_bytes(b'content')
        records = setup_environment.machine_wide_download_records(
            [
                {'source': 'https://host/file.txt', 'dest': str(outside)},
                {'source': 'https://host/inside.txt', 'dest': str(claude_dir / 'inside.txt')},
                {'source': 'https://host/missing.txt', 'dest': str(tmp_path / 'missing.txt')},
            ],
            'https://host/config.yaml', None, claude_dir,
        )
        assert records == [
            {'dest': str(outside), 'source': 'https://host/file.txt',
             'sha256': setup_environment._sha256_of_file(outside)},
            {'dest': str(tmp_path / 'missing.txt'), 'source': 'https://host/missing.txt', 'sha256': None},
        ]

    def test_settings_keys_and_mcp_records(self) -> None:
        keys = setup_environment.written_settings_keys({'theme': 'dark', 'gone': None}, {'file': 's.py'}, {'events': [{}]})
        assert keys == ['hooks', 'statusLine', 'theme']
        assert setup_environment.written_settings_keys(None, None, None) == []
        servers = setup_environment.mcp_server_records([
            {'name': 'a', 'scope': ['user', 'profile']}, {'name': 'b'}, {'scope': 'user'},
        ])
        assert servers == [{'name': 'a', 'scopes': ['user', 'profile']}, {'name': 'b', 'scopes': ['user']}]


class TestProfileResidue:
    """Residue is what the previous configuration wrote that the new one does not install."""

    def test_residue_lists_only_what_exists_and_is_not_reinstalled(self, tmp_path: Path) -> None:
        claude_dir = tmp_path / '.claude'
        profile_dir = claude_dir / 'p'
        (profile_dir / 'agents').mkdir(parents=True)
        (profile_dir / 'agents' / 'old.md').write_text('x', encoding='utf-8')
        (profile_dir / 'agents' / 'kept.md').write_text('x', encoding='utf-8')
        outside = tmp_path / 'shared.txt'
        outside.write_bytes(b'shared')
        manifest = {
            'files_written': ['agents/old.md', 'agents/kept.md', 'agents/gone-already.md'],
            'mcp_servers': [{'name': 'old-srv', 'scopes': ['user', 'profile']}, {'name': 'kept-srv', 'scopes': ['user']},
                            {'name': 'profile-only', 'scopes': ['profile']}],
            'os_env_written': ['OLD_VAR', 'KEPT_VAR'],
            'settings_keys_written': ['theme', 'model'],
            'machine_wide_destinations': [
                {'dest': str(outside), 'source': 's', 'sha256': setup_environment._sha256_of_file(outside)},
            ],
        }
        config = {
            'agents': ['agents/kept.md'],
            'mcp-servers': [{'name': 'kept-srv'}],
            'os-env-variables': {'KEPT_VAR': '1'},
            'user-settings': {'theme': 'light'},
        }

        residue = setup_environment.profile_residue(
            manifest, profile_dir, config, isolated=False, config_source='c.yaml', base_url=None, claude_dir=claude_dir,
        )

        assert residue == ProfileResidue(
            files=[profile_dir / 'agents' / 'old.md'],
            mcp_servers=[('old-srv', ['user'])],
            os_env=['OLD_VAR'],
            settings_keys=['model'],
            destinations=[outside],
        )
        assert bool(residue)
        assert residue.lines() == [
            f'file: {profile_dir / "agents" / "old.md"}',
            'MCP server: old-srv (scope: user)',
            'OS environment variable: OLD_VAR',
            'settings.json key: model',
            f'file outside ~/.claude: {outside}',
        ]

    def test_isolated_profile_carries_no_settings_or_os_residue(self, tmp_path: Path) -> None:
        manifest = {'os_env_written': ['OLD_VAR'], 'settings_keys_written': ['theme']}
        residue = setup_environment.profile_residue(
            manifest, tmp_path / 'p', {}, isolated=True, config_source='c.yaml', base_url=None, claude_dir=tmp_path,
        )
        assert not residue

    def test_changed_destination_is_not_residue(self, tmp_path: Path) -> None:
        outside = tmp_path / 'shared.txt'
        outside.write_bytes(b'edited by the user')
        manifest = {'machine_wide_destinations': [{'dest': str(outside), 'source': 's', 'sha256': 'recorded'}]}
        residue = setup_environment.profile_residue(
            manifest, tmp_path / 'p', {}, isolated=True, config_source='c.yaml', base_url=None, claude_dir=tmp_path,
        )
        assert residue.destinations == []

    def test_remove_residue(self, tmp_path: Path) -> None:
        claude_dir = tmp_path / '.claude'
        profile_dir = claude_dir / 'p'
        skill_file = profile_dir / 'skills' / 'old' / 'SKILL.md'
        skill_file.parent.mkdir(parents=True)
        skill_file.write_text('x', encoding='utf-8')
        outside = tmp_path / 'shared.txt'
        outside.write_bytes(b'x')
        (claude_dir / 'settings.json').write_text(json.dumps({'theme': 'dark', 'model': 'm'}), encoding='utf-8')
        residue = ProfileResidue([skill_file], [('old-srv', ['user'])], ['OLD_VAR'], ['model'], [outside])

        with (
            patch.object(setup_environment, 'find_command', return_value='/usr/bin/claude'),
            patch.object(setup_environment, '_remove_mcp_server_from_cli_scopes') as remove_mcp,
            patch.object(setup_environment, 'set_all_os_env_variables', return_value=True) as set_env,
        ):
            setup_environment.remove_profile_residue(residue, profile_dir=profile_dir, claude_dir=claude_dir)

        assert not skill_file.exists()
        assert not skill_file.parent.exists(), 'the emptied skill directory is pruned'
        assert (profile_dir / 'skills').exists()
        assert not outside.exists()
        remove_mcp.assert_called_once_with('/usr/bin/claude', 'old-srv', ['user'], None, profile_dir)
        set_env.assert_called_once_with({'OLD_VAR': None})
        assert json.loads((claude_dir / 'settings.json').read_text(encoding='utf-8')) == {'theme': 'dark'}


class TestGuardDecision:
    """A guard proceeds only with consent, and never under --yes, --dry-run or without a terminal."""

    def _decide(
        self, args: argparse.Namespace, *, accepted_by: str | None = None, answers: list[str] | None = None,
    ) -> int | None:
        remaining = list(answers or [])
        with (
            patch.object(setup_environment, '_read_user_input', side_effect=lambda _p: remaining.pop(0)),
            patch.object(setup_environment, '_flush_pending_terminal_input'),
            patch.object(setup_environment, '_dev_tty_available', return_value=False),
        ):
            try:
                setup_environment.guard_decision(
                    args, title='T', lines=['L'], question='Q', remedy=['R'], accepted_by=accepted_by,
                )
            except SystemExit as exc:
                return int(exc.code or 0)
        return None

    def test_accepted_by_flag_proceeds(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert self._decide(_args(yes=True), accepted_by='--switch-config') is None
        assert 'Accepted via --switch-config' in capsys.readouterr().out

    def test_yes_refuses_with_the_remedy(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch('sys.stdin.isatty', return_value=True):
            assert self._decide(_args(yes=True)) == 1
        captured = capsys.readouterr()
        assert 'Refusing to continue without consent.' in captured.err
        assert 'R' in captured.out

    def test_dry_run_reports_and_exits_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch('sys.stdin.isatty', return_value=True):
            assert self._decide(_args(dry_run=True)) == 1
        assert 'Dry run: a real run stops here.' in capsys.readouterr().err

    def test_no_terminal_refuses(self) -> None:
        with patch('sys.stdin.isatty', return_value=False):
            assert self._decide(_args()) == 1

    def test_interactive_yes_proceeds_and_no_cancels(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch('sys.stdin.isatty', return_value=True):
            assert self._decide(_args(), answers=['y']) is None
            assert self._decide(_args(), answers=['n']) == 0
        assert 'Setup cancelled by user.' in capsys.readouterr().out


class TestEnvironmentNameChangeGuard:
    """A leftover variable must not rename an installed profile silently."""

    def test_environment_value_that_changes_the_names_is_guarded(self) -> None:
        names = CommandNames(['p', 'new'], 'env')
        with patch.object(setup_environment, 'guard_decision') as decide:
            setup_environment.guard_environment_name_change(_args(yes=True), names, {'command_names': ['p', 'old']}, 'p')
        decide.assert_called_once()
        assert 'from p, old to p, new' in decide.call_args.kwargs['title']
        assert decide.call_args.kwargs['remedy'] == [
            'Pass --command-names p,new to change them.',
            'Clear CLAUDE_CODE_TOOLBOX_COMMAND_NAMES to keep p, old.',
        ]

    @pytest.mark.parametrize(
        ('names', 'manifest'),
        [
            (CommandNames(['p', 'new'], 'cli'), {'command_names': ['p', 'old']}),
            (CommandNames(['p', 'old'], 'env'), {'command_names': ['p', 'old']}),
            (CommandNames(['p', 'old'], 'env', remembered=True), {'command_names': ['p', 'old']}),
            (CommandNames(['p', 'new'], 'env'), None),
        ],
    )
    def test_other_cases_pass(self, names: CommandNames, manifest: dict[str, Any] | None) -> None:
        with patch.object(setup_environment, 'guard_decision') as decide:
            setup_environment.guard_environment_name_change(_args(yes=True), names, manifest, 'p')
        decide.assert_not_called()


class TestConfigurationSwitchGuard:
    """A different configuration for an installed profile needs consent and lists the residue."""

    def test_same_identity_is_no_switch(self) -> None:
        with patch.object(setup_environment, 'guard_decision') as decide:
            switched = setup_environment.guard_configuration_switch(
                _args(), manifest={}, profile_name='p', old_identity='a', new_identity='a', new_source='a',
                residue=ProfileResidue([], [], [], [], []),
            )
        assert switched is False
        decide.assert_not_called()

    @pytest.mark.parametrize(
        ('args', 'expected_given', 'expected_accepted'),
        [
            (_args(config='b.yaml', yes=True), 'the configuration argument', None),
            (_args(env={'CLAUDE_CODE_TOOLBOX_ENV_CONFIG': 'b.yaml'}, yes=True), 'CLAUDE_CODE_TOOLBOX_ENV_CONFIG', None),
            (_args(config='b.yaml', switch_config=True), 'the configuration argument',
             '--switch-config or CLAUDE_CODE_TOOLBOX_SWITCH_CONFIG=1'),
        ],
    )
    def test_switch_names_the_source_and_the_residue(
        self, args: argparse.Namespace, expected_given: str, expected_accepted: str | None,
    ) -> None:
        residue = ProfileResidue([Path('/p/agents/old.md')], [], [], [], [])
        with patch.object(setup_environment, 'guard_decision') as decide:
            switched = setup_environment.guard_configuration_switch(
                args, manifest={'config_source': 'a.yaml'}, profile_name='p', old_identity='a', new_identity='b',
                new_source='b.yaml', residue=residue,
            )
        assert switched is True
        kwargs = decide.call_args.kwargs
        assert kwargs['title'] == (
            f'Profile "p" was installed from a.yaml; {expected_given} names a different configuration, b.yaml.'
        )
        assert kwargs['lines'] == ['The previous configuration leaves behind:', f'  file: {Path("/p/agents/old.md")}']
        assert kwargs['accepted_by'] == expected_accepted
        assert '--profile p' in kwargs['remedy'][1]


class TestDroppedWrappers:
    """Wrappers of aliases a profile no longer registers are removed."""

    def test_only_toolbox_wrappers_of_dropped_names_are_removed(self, tmp_path: Path) -> None:
        local_bin = tmp_path / '.local' / 'bin'
        local_bin.mkdir(parents=True)
        launcher = tmp_path / '.claude' / 'p' / 'launch.sh'
        launcher.parent.mkdir(parents=True)
        launcher.write_text('#!/bin/bash\n', encoding='utf-8')
        if sys.platform == 'win32':
            (local_bin / 'old.cmd').write_text('@echo off\nREM Global old command for CMD\n', encoding='utf-8')
            (local_bin / 'old.ps1').write_text('# Global old command for PowerShell\n', encoding='utf-8')
            (local_bin / 'old').write_text('#!/bin/bash\n# Bash wrapper for old to work in Git Bash\n', encoding='utf-8')
            (local_bin / 'kept.cmd').write_text('@echo off\nREM Global kept command for CMD\n', encoding='utf-8')
        else:
            (local_bin / 'old').symlink_to(launcher)
            (local_bin / 'kept').symlink_to(launcher)
        foreign = local_bin / 'foreign'
        foreign.write_text('#!/bin/bash\necho mine\n', encoding='utf-8')

        dropped = setup_environment.remove_dropped_command_wrappers(['p', 'old', 'kept', 'foreign'], ['p', 'kept'], tmp_path)

        assert dropped == ['old', 'foreign']
        assert not any(local_bin.glob('old*'))
        assert any(local_bin.glob('kept*'))
        assert foreign.exists(), 'a file the toolbox did not write is never removed'

    def test_nothing_dropped(self, tmp_path: Path) -> None:
        assert setup_environment.remove_dropped_command_wrappers(['p', 'a'], ['p', 'a', 'b'], tmp_path) == []


class TestSummaryLines:
    """The pin effect, shared destinations and unrefreshed profiles are named."""

    def test_pin_effect_line(self) -> None:
        assert setup_environment.pin_effect_line('2.1.280', None, []) == (
            'Claude Code version pin 2.1.280: holds the binary every profile uses'
        )
        assert setup_environment.pin_effect_line('2.1.280', '2.1.280', ['a', 'base']) == (
            'Claude Code version pin 2.1.280: holds the binary at 2.1.280 for the other installed profile(s) a, base'
        )
        assert setup_environment.pin_effect_line('2.1.280', '2.1.100', ['a']) == (
            'Claude Code version pin 2.1.280: moves the binary from 2.1.100 to 2.1.280 for the other installed profile(s) a'
        )

    def test_shared_destination_warnings(self, tmp_path: Path) -> None:
        claude_dir = tmp_path / '.claude'
        dest = tmp_path / 'shared' / 'tool.toml'
        _manifest(claude_dir / 'other', 'other', ['other'], config_source='https://example.com/other.yaml',
                  machine_wide_destinations=[{'dest': str(dest), 'source': 'https://example.com/their.toml', 'sha256': 'x'}])
        _manifest(claude_dir / 'same', 'same', ['same'], config_source='https://example.com/mine.yaml',
                  machine_wide_destinations=[{'dest': str(dest), 'source': 'https://example.com/their.toml', 'sha256': 'x'}])
        files = [{'source': 'https://example.com/mine.toml', 'dest': str(dest)}]

        with patch.object(setup_environment, 'installed_profiles', _REAL_INSTALLED_PROFILES):
            warnings = setup_environment.shared_destination_warnings(
                files, 'https://example.com/mine.yaml', None,
                home_dir=tmp_path, this_identity='https://example.com/mine.yaml', this_profile='me',
            )

        assert warnings == [
            (
                f'{dest} is also installed by profile "other" (https://example.com/other.yaml) from '
                'https://example.com/their.toml; this run writes it from https://example.com/mine.toml and leaves it '
                'untouched only when the content is identical'
            ),
        ]

    def test_unrefreshed_profile_lines(self, tmp_path: Path) -> None:
        claude_dir = tmp_path / '.claude'
        _manifest(claude_dir, None, [], origin=None)
        _manifest(claude_dir / 'b', 'b', ['b'])
        _manifest(claude_dir / 'a', 'a', ['a'])
        with patch.object(setup_environment, 'installed_profiles', _REAL_INSTALLED_PROFILES):
            lines = setup_environment.unrefreshed_profile_lines(tmp_path, 'a')
        assert lines == ['base (--profile base)', 'b (--profile b)']


class TestChildRunEnvironment:
    """A child run inherits the credentials and nothing that would change what it installs."""

    def test_twins_and_config_dir_are_stripped(self) -> None:
        values = {twin.variable: 'set' for twin in setup_environment.ENV_TWINS}
        values['CLAUDE_CONFIG_DIR'] = '/somewhere'
        values['GITHUB_TOKEN'] = 'token'
        with patch.dict(os.environ, values):
            env = setup_environment.child_run_environment()
        assert env['CLAUDE_CODE_TOOLBOX_ENV_AUTH'] == 'set'
        assert env['GITHUB_TOKEN'] == 'token'
        assert 'CLAUDE_CONFIG_DIR' not in env
        stripped = {twin.variable for twin in setup_environment.ENV_TWINS} - setup_environment.CHILD_RUN_INHERITED_TWINS
        assert not stripped & set(env)

    def test_every_twin_resolve_args_reads_is_stripped_or_listed_as_inherited(self) -> None:
        """A new twin must be a stripping decision, never an accidental leak."""
        registered = {twin.variable for twin in setup_environment.ENV_TWINS}
        assert registered >= setup_environment.CHILD_RUN_INHERITED_TWINS


class TestRefreshAllProfiles:
    """--profile all runs every installed profile as its own child and reports each result."""

    def _profiles(self, home: Path) -> None:
        _manifest(home / '.claude', None, [], origin=None)
        _manifest(home / '.claude' / 'b', 'b', ['b'])
        _manifest(home / '.claude' / 'a', 'a', ['a'])

    def test_conflicting_arguments_are_refused(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert setup_environment.refresh_all_profiles(_args('x', config='c.yaml', profile='all', yes=True)) == 1
        assert 'cannot be combined with a configuration, --command-names' in capsys.readouterr().err

    def test_no_profiles(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        with patch.object(setup_environment, 'get_real_user_home', return_value=tmp_path), \
                patch.object(setup_environment, 'installed_profiles', _REAL_INSTALLED_PROFILES):
            assert setup_environment.refresh_all_profiles(_args(profile='all', yes=True)) == 1
        assert 'No installed profile has a manifest' in capsys.readouterr().err

    def test_children_run_in_order_with_stripped_environment_and_report(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._profiles(tmp_path)
        calls: list[tuple[list[str], dict[str, str]]] = []

        def _run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
            calls.append((argv, kwargs['env']))
            profile = argv[argv.index('--profile') + 1]
            return subprocess.CompletedProcess(argv, 1 if profile == 'a' else 0)

        with (
            patch.object(setup_environment, 'get_real_user_home', return_value=tmp_path),
            patch.object(setup_environment, 'installed_profiles', _REAL_INSTALLED_PROFILES),
            patch.object(setup_environment.subprocess, 'run', side_effect=_run),
            patch.dict(os.environ, {
                'CLAUDE_CODE_TOOLBOX_COMMAND_NAMES': 'leak', 'CLAUDE_CONFIG_DIR': '/x', 'GITHUB_TOKEN': 't',
            }),
            patch('sys.argv', ['/repo/scripts/setup_environment.py']),
        ):
            code = setup_environment.refresh_all_profiles(_args(profile='all', yes=True, dry_run=True))

        assert code == 1
        assert [argv[argv.index('--profile') + 1] for argv, _ in calls] == ['base', 'a', 'b']
        for argv, env in calls:
            assert argv[:2] == [sys.executable, '/repo/scripts/setup_environment.py']
            assert argv[-2:] == ['--yes', '--dry-run']
            assert 'CLAUDE_CODE_TOOLBOX_COMMAND_NAMES' not in env
            assert 'CLAUDE_CONFIG_DIR' not in env
            assert env['GITHUB_TOKEN'] == 't'
        out = capsys.readouterr().out
        assert '* base: ok' in out
        assert '* a: failed (exit code 1); retry with --profile a' in out
        assert '* b: ok' in out

    def test_packaged_entry_point_starts_children_through_the_cli_module(self, tmp_path: Path) -> None:
        self._profiles(tmp_path)
        calls: list[list[str]] = []

        def _run(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0)

        with (
            patch.object(setup_environment, 'get_real_user_home', return_value=tmp_path),
            patch.object(setup_environment, 'installed_profiles', _REAL_INSTALLED_PROFILES),
            patch.object(setup_environment.subprocess, 'run', side_effect=_run),
            patch.object(setup_environment, '__name__', 'cc_toolbox.setup_environment'),
            patch('sys.argv', ['/venv/bin/cc-toolbox']),
        ):
            assert setup_environment.refresh_all_profiles(_args(profile='all', yes=True)) == 0
        assert calls[0][:4] == [sys.executable, '-m', 'cc_toolbox.cli', 'setup']
        assert calls[0][4:] == ['--profile', 'base', '--yes']

    def test_interactive_consent_once(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        self._profiles(tmp_path)
        answers = ['n']
        with (
            patch.object(setup_environment, 'get_real_user_home', return_value=tmp_path),
            patch.object(setup_environment, 'installed_profiles', _REAL_INSTALLED_PROFILES),
            patch.object(setup_environment.subprocess, 'run') as run,
            patch.object(setup_environment, '_read_user_input', side_effect=lambda _p: answers.pop(0)),
            patch.object(setup_environment, '_flush_pending_terminal_input'),
            patch('sys.stdin.isatty', return_value=True),
        ):
            assert setup_environment.refresh_all_profiles(_args(profile='all')) == 0
        run.assert_not_called()
        assert 'Setup cancelled by user.' in capsys.readouterr().out

    def test_non_interactive_without_yes_refuses(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        self._profiles(tmp_path)
        with (
            patch.object(setup_environment, 'get_real_user_home', return_value=tmp_path),
            patch.object(setup_environment, 'installed_profiles', _REAL_INSTALLED_PROFILES),
            patch.object(setup_environment, '_dev_tty_available', return_value=False),
            patch('sys.stdin.isatty', return_value=False),
        ):
            assert setup_environment.refresh_all_profiles(_args(profile='all')) == 1
        assert 'no interactive terminal available' in capsys.readouterr().err


class TestProfileRerunResolution:
    """--profile NAME locates the installed profile and its configuration."""

    def test_missing_profile_is_an_error(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc:
            setup_environment.resolve_profile_rerun(_args(profile='ghost'), tmp_path)
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert 'No installed profile named "ghost"' in captured.err
        assert '--command-names ghost' in captured.out

    def test_reserved_or_invalid_name_is_refused(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit):
            setup_environment.resolve_profile_rerun(_args(profile='skills'), tmp_path)
        assert 'Command name "skills" in --profile is reserved' in capsys.readouterr().err

    def test_unreadable_manifest_is_an_error(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        profile_dir = tmp_path / '.claude' / 'p'
        profile_dir.mkdir(parents=True)
        (profile_dir / 'manifest.json').write_text('{oops', encoding='utf-8')
        with pytest.raises(SystemExit):
            setup_environment.resolve_profile_rerun(_args(profile='p'), tmp_path)
        assert 'Profile "p" cannot be re-run' in capsys.readouterr().err

    def test_base_and_named_profiles_resolve(self, tmp_path: Path) -> None:
        _manifest(tmp_path / '.claude', None, [], origin=None, config_source='https://example.com/base.yaml')
        _manifest(tmp_path / '.claude' / 'p', 'p', ['p'])
        base = setup_environment.resolve_profile_rerun(_args(profile='base'), tmp_path)
        named = setup_environment.resolve_profile_rerun(_args(env={'CLAUDE_CODE_TOOLBOX_PROFILE': 'p'}), tmp_path)
        assert (base.primary, base.name, base.identity) == (None, 'base', 'https://example.com/base.yaml')
        assert (named.primary, named.name, named.identity) == ('p', 'p', 'https://example.com/profile.yaml')
        assert setup_environment.rerun_config_source(named) == 'https://example.com/profile.yaml'

    def test_unresolvable_legacy_source_needs_a_configuration(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        profile_dir = tmp_path / '.claude' / 'p'
        profile_dir.mkdir(parents=True)
        (profile_dir / 'manifest.json').write_text(json.dumps({
            'name': 'p', 'command_names': ['p'], 'config_source': './env.yaml',
            'config_source_url': None, 'config_source_type': 'local',
        }), encoding='utf-8')
        rerun = setup_environment.resolve_profile_rerun(_args(profile='p'), tmp_path)
        assert rerun.identity is None
        with pytest.raises(SystemExit):
            setup_environment.rerun_config_source(rerun)
        assert "records the configuration './env.yaml', which cannot be resolved" in capsys.readouterr().err


class TestReadTargetManifest:
    """The manifest of the profile a run installs into is read from the resolved profile directory."""

    def test_reads_the_profile_directory(self, tmp_path: Path) -> None:
        _manifest(tmp_path / '.claude' / 'p', 'p', ['p'])
        with patch.object(setup_environment, 'get_real_user_home', return_value=tmp_path):
            manifest = _REAL_READ_TARGET_MANIFEST('p', {})
        assert manifest is not None
        assert manifest['name'] == 'p'

    def test_invalid_name_reads_nothing(self, tmp_path: Path) -> None:
        with patch.object(setup_environment, 'get_real_user_home', return_value=tmp_path):
            assert _REAL_READ_TARGET_MANIFEST('../escape', {}) is None

    def test_unreadable_manifest_exits(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        (tmp_path / '.claude').mkdir()
        (tmp_path / '.claude' / 'manifest.json').write_text('{oops', encoding='utf-8')
        with patch.object(setup_environment, 'get_real_user_home', return_value=tmp_path), pytest.raises(SystemExit):
            _REAL_READ_TARGET_MANIFEST(None, {})
        assert 'The manifest of profile "base" cannot be read' in capsys.readouterr().err


class TestOriginMarker:
    """The summaries mark every value with its origin."""

    def test_markers(self) -> None:
        assert setup_environment.origin_marker('cli') == ' [cli]'
        assert setup_environment.origin_marker('yaml', remembered=True) == ' [remembered]'
        assert setup_environment.origin_marker(None) == ''

    def test_components_header_and_names_row_carry_remembered(self) -> None:
        import io

        plan = setup_environment.InstallationPlan(
            config_name='P', config_source='p.yaml', config_source_type='local', config_version=None,
            command_names=['p', 'a'], command_names_origin='cli', command_names_remembered=True,
            component_selection=ComponentSelection(
                is_active=True, available=['core'], selected=['core'], origin='env', remembered=True,
            ),
        )
        buffer = io.StringIO()
        setup_environment.display_installation_summary(plan, output=buffer)
        text = buffer.getvalue()
        assert 'Command names: p, a [remembered]' in text
        assert 'Components:' in text
        assert '[remembered]' in text.split('Components:')[1].split('\n')[0]


class TestMachineWideWritesPinEffect:
    """An isolated run's machine-wide list carries the pin effect line."""

    def test_pin_effect_replaces_the_plain_pin_line(self, tmp_path: Path) -> None:
        with patch.object(setup_environment, 'get_real_user_home', return_value=tmp_path):
            writes = setup_environment.collect_machine_wide_writes(
                profile_dir=tmp_path / '.claude' / 'p', command_names=['p'], skip_install=True, install_version=None,
                keep_installed=False, pinned_version='2.1.280', ide_clis=[], os_level_env={}, mcp_servers=[],
                files_to_download=[], has_dependency_commands=False,
                pin_effect='Claude Code version pin 2.1.280: holds the binary at 2.1.280 for base',
            )
        assert 'Claude Code version pin 2.1.280: holds the binary at 2.1.280 for base' in writes
        assert 'Claude Code version pin 2.1.280: holds the binary every profile uses' not in writes


def _mock_shell_execute() -> MagicMock:
    """Build a ShellExecuteW stand-in that reports success."""
    mock = MagicMock()
    mock.return_value = 33
    return mock


class TestNewTwinsForwardThroughUac:
    """The profile and switch-config twins travel into the elevated process like every other twin."""

    def test_profile_and_switch_config_are_forwarded(self) -> None:
        captured: list[list[str]] = []
        original = setup_environment.subprocess.list2cmdline

        def _capture(args: list[str]) -> str:
            captured.append(list(args))
            return original(args)

        with (
            patch('platform.system', return_value='Windows'),
            patch('ctypes.windll', create=True) as windll,
            patch('time.sleep'),
            patch.object(setup_environment.subprocess, 'list2cmdline', side_effect=_capture),
            patch.dict(os.environ, {'CLAUDE_CODE_TOOLBOX_PROFILE': 'p', 'CLAUDE_CODE_TOOLBOX_SWITCH_CONFIG': '1'}),
        ):
            windll.shell32.ShellExecuteW = _mock_shell_execute()
            with pytest.raises(SystemExit):
                setup_environment.request_admin_elevation(['--profile', 'p'])
        assert '--env-CLAUDE_CODE_TOOLBOX_PROFILE=p' in captured[0]
        assert '--env-CLAUDE_CODE_TOOLBOX_SWITCH_CONFIG=1' in captured[0]
