"""E2E tests for re-running installed profiles.

An update is the install command run again: by configuration plus the
primary name, or by --profile NAME (environment twin
CLAUDE_CODE_TOOLBOX_PROFILE) with no configuration at all. A profile's
manifest remembers the command names and component delta a run typed or
took from the environment, so a re-run keeps its aliases and components;
configuration values are re-read every time. Guards hold a run back before
any write when the environment would rename a profile or a different
configuration would re-provision it. The tests install real local YAML
files into an isolated home with the real launcher, wrapper, profile-config
and manifest writers; only network access, the Claude Code binary, MCP
registration, OS-level variables and the Windows PATH registry are replaced.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from scripts import setup_environment
from tests.e2e.profile_support import home_state
from tests.e2e.profile_support import read_manifest
from tests.e2e.profile_support import run_main
from tests.e2e.profile_support import wrapper_targets_profile
from tests.e2e.profile_support import wrappers_absent
from tests.e2e.profile_support import wrappers_exist
from tests.e2e.profile_support import write_config
from tests.e2e.profile_support import write_legacy_manifest
from tests.e2e.validators import validate_manifest

REPO_ROOT = Path(__file__).resolve().parents[2]

SKIP = ['--skip-install', '--no-admin']


@pytest.fixture
def configs(tmp_path: Path) -> Path:
    """A directory of configurations with the resources they install beside them."""
    directory = tmp_path / 'configs'
    for relative, content in (
        ('agents/core.md', '# core agent\n'),
        ('agents/extra.md', '# extra agent\n'),
        ('agents/other.md', '# other agent\n'),
        ('rules/rule.md', '# rule\n'),
        ('files/same-a.txt', 'identical content\n'),
        ('files/same-b.txt', 'identical content\n'),
        ('files/different.txt', 'different content\n'),
    ):
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    return directory


def _plain(name: str = 'Plain Env') -> dict[str, Any]:
    """A configuration without command-names, like a shared base configuration."""
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


@pytest.mark.usefixtures('e2e_isolated_home')
class TestRerunKeepsTypedChoices:
    """A re-run keeps the aliases and the components the install typed."""

    def test_profile_rerun_keeps_aliases_and_components(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--profile NAME alone restores every alias and the added component."""
        cfg = write_config(configs, 'env.yaml', _components())
        claude_dir, local_bin = e2e_isolated_home['claude_dir'], e2e_isolated_home['local_bin']
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'aegis-1,a1,a2', '--with', 'extra']) == 0
        profile_dir = claude_dir / 'aegis-1'
        assert (profile_dir / 'agents' / 'extra.md').is_file()
        capsys.readouterr()

        assert run_main(['--profile', 'aegis-1', *SKIP, '--yes']) == 0

        manifest = read_manifest(profile_dir)
        assert manifest['command_names'] == ['aegis-1', 'a1', 'a2']
        assert manifest['origins'] == {'command_names': 'cli', 'components': 'cli'}
        assert manifest['components'] == {'select': None, 'with': 'extra', 'without': None}
        assert (profile_dir / 'agents' / 'extra.md').is_file(), 'the added component was deselected'
        for name in ('aegis-1', 'a1', 'a2'):
            assert wrappers_exist(local_bin, name)
            assert wrapper_targets_profile(local_bin, name, profile_dir)
        output = _output(capsys)
        assert 'Command names: aegis-1, a1, a2 [remembered]' in output
        assert '[remembered]' in output.split('Components:')[1].split('\n')[0]
        assert '* Global commands: aegis-1, a1, a2 registered [remembered]' in output

    def test_configuration_with_primary_name_keeps_aliases_and_components(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The configuration plus the primary name selects the profile and keeps its choices."""
        cfg = write_config(configs, 'env.yaml', _components())
        claude_dir, local_bin = e2e_isolated_home['claude_dir'], e2e_isolated_home['local_bin']
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'aegis-1,a1', '--with', 'extra']) == 0
        capsys.readouterr()

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'aegis-1']) == 0

        manifest = read_manifest(claude_dir / 'aegis-1')
        assert manifest['command_names'] == ['aegis-1', 'a1']
        assert manifest['components'] == {'select': None, 'with': 'extra', 'without': None}
        assert (claude_dir / 'aegis-1' / 'agents' / 'extra.md').is_file()
        assert wrappers_exist(local_bin, 'a1')
        assert 'Command names: aegis-1, a1 [remembered]' in _output(capsys)

    def test_name_none_drops_every_alias_and_its_wrappers(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """NAME,none installs the profile under one command and removes the alias wrappers."""
        cfg = write_config(configs, 'env.yaml', _plain())
        claude_dir, local_bin = e2e_isolated_home['claude_dir'], e2e_isolated_home['local_bin']
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'aegis-1,a1,a2']) == 0
        capsys.readouterr()

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'aegis-1,none']) == 0

        assert read_manifest(claude_dir / 'aegis-1')['command_names'] == ['aegis-1']
        assert wrappers_exist(local_bin, 'aegis-1')
        assert wrappers_absent(local_bin, 'a1')
        assert wrappers_absent(local_bin, 'a2')
        assert 'Removed the wrapper(s) of dropped alias(es): a1, a2' in _output(capsys)

    def test_shorter_typed_list_removes_the_dropped_wrapper(
        self, e2e_isolated_home: dict[str, Path], configs: Path,
    ) -> None:
        """A typed list that leaves an alias out removes that alias's wrappers and keeps the rest."""
        cfg = write_config(configs, 'env.yaml', _plain())
        local_bin = e2e_isolated_home['local_bin']
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'aegis-1,a1,a2']) == 0

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'aegis-1,a1']) == 0

        assert wrappers_exist(local_bin, 'a1')
        assert wrappers_absent(local_bin, 'a2')
        assert read_manifest(e2e_isolated_home['claude_dir'] / 'aegis-1')['command_names'] == ['aegis-1', 'a1']


@pytest.mark.usefixtures('e2e_isolated_home')
class TestPrecedenceAndMarkers:
    """Each value is ranked typed, environment, remembered, configuration, default, and marked so."""

    def test_remembered_marker_and_yaml_changed_warning(
        self, configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A remembered list overrides a configuration list that changed, with a warning that says so."""
        config = {**_plain(), 'command-names': ['p1', 'y1']}
        cfg = write_config(configs, 'env.yaml', config)
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'p1,t1']) == 0
        write_config(configs, 'env.yaml', {**config, 'command-names': ['p1', 'y2']})
        capsys.readouterr()

        assert run_main(['--profile', 'p1', *SKIP, '--dry-run']) == 0

        output = _output(capsys)
        assert 'Command names: p1, t1 [remembered]' in output
        assert (
            "command-names: using the remembered value p1, t1 [remembered]; the configuration's command-names "
            'changed from p1, y1 to p1, y2 since the profile was installed.'
        ) in output

    def test_yaml_names_are_re_read_and_dropped_aliases_removed(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A profile installed from its configuration's names follows the configuration on a re-run."""
        config = {**_plain(), 'command-names': ['p1', 'y1']}
        cfg = write_config(configs, 'env.yaml', config)
        local_bin = e2e_isolated_home['local_bin']
        assert run_main([str(cfg), *SKIP, '--yes']) == 0
        write_config(configs, 'env.yaml', {**config, 'command-names': ['p1', 'y2']})
        capsys.readouterr()

        assert run_main(['--profile', 'p1', *SKIP, '--yes']) == 0

        assert read_manifest(e2e_isolated_home['claude_dir'] / 'p1')['command_names'] == ['p1', 'y2']
        assert wrappers_exist(local_bin, 'y2')
        assert wrappers_absent(local_bin, 'y1')
        assert 'Command names: p1, y2 [yaml]' in _output(capsys)

    def test_default_marker_when_no_source_lists_aliases(
        self, configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A profile selected by name whose configuration lost its names runs under that name alone."""
        config = {**_plain(), 'command-names': ['p1', 'y1']}
        cfg = write_config(configs, 'env.yaml', config)
        assert run_main([str(cfg), *SKIP, '--yes']) == 0
        write_config(configs, 'env.yaml', _plain())
        capsys.readouterr()

        assert run_main(['--profile', 'p1', *SKIP, '--dry-run']) == 0

        assert 'Command names: p1 [default]' in _output(capsys)

    def test_typed_list_beats_the_remembered_one(
        self, configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A list typed for this run wins over the remembered one and is marked as typed."""
        cfg = write_config(configs, 'env.yaml', _plain())
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'p1,t1']) == 0
        capsys.readouterr()

        assert run_main([str(cfg), *SKIP, '--dry-run', '--command-names', 'p1,c1']) == 0

        assert 'Command names: p1, c1 [cli]' in _output(capsys)

    def test_components_remembered_and_warned_when_defaults_change(
        self, configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A remembered component delta is marked and warns when the author defaults changed."""
        config = _components()
        cfg = write_config(configs, 'env.yaml', config)
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'aegis-1', '--without', 'core', '--with', 'extra']) == 0
        config['components'][1]['default'] = True
        write_config(configs, 'env.yaml', config)
        capsys.readouterr()

        assert run_main(['--profile', 'aegis-1', *SKIP, '--dry-run']) == 0

        output = _output(capsys)
        assert '[remembered]' in output.split('Components:')[1].split('\n')[0]
        assert 'components: using the remembered selection extra [remembered]' in output
        assert 'changed from core to core, extra' in output


@pytest.mark.usefixtures('e2e_isolated_home')
class TestEnvironmentChangeGuard:
    """A leftover variable may not rename an installed profile without consent."""

    def _install(self, configs: Path) -> Path:
        cfg = write_config(configs, 'env.yaml', _plain())
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'aegis-1,a1']) == 0
        return cfg

    def test_variable_change_is_refused_under_yes(
        self, e2e_isolated_home: dict[str, Path], configs: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Without a terminal the run stops before any write."""
        cfg = self._install(configs)
        home = e2e_isolated_home['home']
        before = home_state(home)
        monkeypatch.setenv('CLAUDE_CODE_TOOLBOX_COMMAND_NAMES', 'aegis-1,b1')
        capsys.readouterr()

        assert run_main([str(cfg), *SKIP, '--yes']) == 1

        output = _output(capsys)
        assert (
            'CLAUDE_CODE_TOOLBOX_COMMAND_NAMES changes the command names of profile "aegis-1" '
            'from aegis-1, a1 to aegis-1, b1.'
        ) in output
        assert 'Pass --command-names aegis-1,b1 to change them.' in output
        assert home_state(home) == before

    def test_variable_change_is_refused_under_dry_run(
        self, configs: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A preview reports the refusal instead of a plan the real run would not execute."""
        cfg = self._install(configs)
        monkeypatch.setenv('CLAUDE_CODE_TOOLBOX_COMMAND_NAMES', 'aegis-1,b1')
        capsys.readouterr()

        assert run_main([str(cfg), *SKIP, '--dry-run']) == 1

        output = _output(capsys)
        assert 'Dry run: a real run stops here.' in output
        assert 'Installation Summary' not in output

    @pytest.mark.parametrize(('answer', 'renamed'), [('n', False), ('y', True)])
    def test_variable_change_prompts_interactively(
        self,
        answer: str,
        renamed: bool,
        e2e_isolated_home: dict[str, Path],
        configs: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """An interactive run asks; no cancels, yes renames the profile with the environment's list."""
        cfg = self._install(configs)
        local_bin = e2e_isolated_home['local_bin']
        monkeypatch.setenv('CLAUDE_CODE_TOOLBOX_COMMAND_NAMES', 'aegis-1,b1')
        capsys.readouterr()

        assert run_main([str(cfg), *SKIP], interactive=True, answers=[answer, 'y']) == 0

        manifest = read_manifest(e2e_isolated_home['claude_dir'] / 'aegis-1')
        if renamed:
            assert manifest['command_names'] == ['aegis-1', 'b1']
            assert manifest['origins']['command_names'] == 'env'
            assert wrappers_exist(local_bin, 'b1')
            assert wrappers_absent(local_bin, 'a1')
            assert 'Command names: aegis-1, b1 [env]' in _output(capsys)
        else:
            assert manifest['command_names'] == ['aegis-1', 'a1']
            assert wrappers_absent(local_bin, 'b1')

    def test_typed_change_proceeds(self, e2e_isolated_home: dict[str, Path], configs: Path) -> None:
        """A typed list is a deliberate choice and needs no further consent."""
        cfg = self._install(configs)

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'aegis-1,b1']) == 0

        assert read_manifest(e2e_isolated_home['claude_dir'] / 'aegis-1')['command_names'] == ['aegis-1', 'b1']

    def test_variable_naming_the_profile_alone_selects_it(
        self, e2e_isolated_home: dict[str, Path], configs: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A variable holding only the primary name selects the profile and keeps its aliases."""
        cfg = self._install(configs)
        monkeypatch.setenv('CLAUDE_CODE_TOOLBOX_COMMAND_NAMES', 'aegis-1')

        assert run_main([str(cfg), *SKIP, '--yes']) == 0

        assert read_manifest(e2e_isolated_home['claude_dir'] / 'aegis-1')['command_names'] == ['aegis-1', 'a1']


@pytest.mark.usefixtures('e2e_isolated_home')
class TestConfigurationSwitchGuard:
    """A different configuration for an installed profile needs consent and sheds the residue."""

    def _install_a(self, configs: Path, *, names: list[str] | None = None) -> tuple[Path, Path]:
        cfg_a = write_config(configs, 'a.yaml', {'name': 'A', 'agents': ['agents/core.md']})
        cfg_b = write_config(configs, 'b.yaml', {'name': 'B', 'agents': ['agents/other.md']})
        argv = [str(cfg_a), *SKIP, '--yes']
        if names:
            argv += ['--command-names', ','.join(names)]
        assert run_main(argv) == 0
        return cfg_a, cfg_b

    def test_refused_under_yes_listing_the_residue(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The refusal names both configurations and what the previous one leaves behind."""
        cfg_a, cfg_b = self._install_a(configs, names=['aegis-1'])
        profile_dir = e2e_isolated_home['claude_dir'] / 'aegis-1'
        before = home_state(e2e_isolated_home['home'])
        capsys.readouterr()

        assert run_main([str(cfg_b), *SKIP, '--yes', '--command-names', 'aegis-1']) == 1

        output = _output(capsys)
        assert (
            f'Profile "aegis-1" was installed from {cfg_a.resolve()}; the configuration argument names a '
            f'different configuration, {cfg_b.resolve()}.'
        ) in output
        assert f'file: {profile_dir / "agents" / "core.md"}' in output
        assert 'Pass --switch-config (or set CLAUDE_CODE_TOOLBOX_SWITCH_CONFIG=1)' in output
        assert home_state(e2e_isolated_home['home']) == before

    def test_variable_configuration_is_named_in_the_refusal(
        self, configs: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A configuration from CLAUDE_CODE_TOOLBOX_ENV_CONFIG is named as such."""
        _cfg_a, cfg_b = self._install_a(configs, names=['aegis-1'])
        monkeypatch.setenv('CLAUDE_CODE_TOOLBOX_ENV_CONFIG', str(cfg_b))
        capsys.readouterr()

        assert run_main([*SKIP, '--yes', '--command-names', 'aegis-1']) == 1

        assert 'CLAUDE_CODE_TOOLBOX_ENV_CONFIG names a different configuration' in _output(capsys)

    def test_dry_run_stops_with_exit_1(
        self, configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A preview of a switch the real run refuses exits 1."""
        _cfg_a, cfg_b = self._install_a(configs, names=['aegis-1'])
        capsys.readouterr()

        assert run_main([str(cfg_b), *SKIP, '--dry-run', '--command-names', 'aegis-1']) == 1

        assert 'Dry run: a real run stops here.' in _output(capsys)

    @pytest.mark.parametrize(('answer', 'switched'), [('n', False), ('y', True)])
    def test_interactive_prompt_lists_the_residue(
        self, answer: str, switched: bool, e2e_isolated_home: dict[str, Path], configs: Path,
    ) -> None:
        """No keeps the profile as it is; yes switches it and removes the residue."""
        cfg_a, cfg_b = self._install_a(configs, names=['aegis-1'])
        profile_dir = e2e_isolated_home['claude_dir'] / 'aegis-1'

        assert run_main([str(cfg_b), *SKIP, '--command-names', 'aegis-1'], interactive=True, answers=[answer, 'y']) == 0

        manifest = read_manifest(profile_dir)
        if switched:
            assert manifest['config_identity'] == setup_environment.config_identity_of(str(cfg_b.resolve()))
            assert not (profile_dir / 'agents' / 'core.md').exists()
            assert (profile_dir / 'agents' / 'other.md').is_file()
        else:
            assert manifest['config_identity'] == setup_environment.config_identity_of(str(cfg_a.resolve()))
            assert (profile_dir / 'agents' / 'core.md').is_file()

    @pytest.mark.parametrize('how', ['flag', 'variable'])
    def test_switch_config_accepts_and_removes_the_residue(
        self, how: str, e2e_isolated_home: dict[str, Path], configs: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--switch-config (or its variable) switches the profile without a prompt."""
        _cfg_a, cfg_b = self._install_a(configs, names=['aegis-1'])
        profile_dir = e2e_isolated_home['claude_dir'] / 'aegis-1'
        argv = [str(cfg_b), *SKIP, '--yes', '--command-names', 'aegis-1']
        if how == 'flag':
            argv.append('--switch-config')
        else:
            monkeypatch.setenv('CLAUDE_CODE_TOOLBOX_SWITCH_CONFIG', '1')
        capsys.readouterr()

        assert run_main(argv) == 0

        output = _output(capsys)
        assert 'Accepted via --switch-config or CLAUDE_CODE_TOOLBOX_SWITCH_CONFIG=1.' in output
        assert f'Removed {profile_dir / "agents" / "core.md"}' in output
        assert not (profile_dir / 'agents' / 'core.md').exists()
        assert (profile_dir / 'agents' / 'other.md').is_file()
        assert read_manifest(profile_dir)['config_identity'] == setup_environment.config_identity_of(str(cfg_b.resolve()))

    def test_base_profile_switch_is_guarded(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A different configuration for the base profile is refused the same way."""
        _cfg_a, cfg_b = self._install_a(configs)
        claude_dir = e2e_isolated_home['claude_dir']
        assert (claude_dir / 'agents' / 'core.md').is_file()
        capsys.readouterr()

        assert run_main([str(cfg_b), *SKIP, '--yes']) == 1

        assert 'Profile "base" was installed from' in _output(capsys)
        assert (claude_dir / 'agents' / 'core.md').is_file()
        assert run_main([str(cfg_b), *SKIP, '--yes', '--switch-config']) == 0
        assert not (claude_dir / 'agents' / 'core.md').exists()
        assert (claude_dir / 'agents' / 'other.md').is_file()

    def test_same_configuration_spelled_differently_is_no_switch(
        self, configs: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The identity is the resolved path, so a relative spelling of the same file proceeds."""
        self._install_a(configs, names=['aegis-1'])
        monkeypatch.chdir(configs)
        capsys.readouterr()

        assert run_main(['./a.yaml', *SKIP, '--yes', '--command-names', 'aegis-1']) == 0

        assert 'names a different configuration' not in _output(capsys)


@pytest.mark.usefixtures('e2e_isolated_home')
class TestProfileWithConfiguration:
    """A configuration given beside --profile is checked against the manifest's identity."""

    def _install(self, configs: Path) -> tuple[Path, Path]:
        cfg_a = write_config(configs, 'a.yaml', {'name': 'A', 'agents': ['agents/core.md']})
        cfg_b = write_config(configs, 'b.yaml', {'name': 'B', 'agents': ['agents/other.md']})
        assert run_main([str(cfg_a), *SKIP, '--yes', '--command-names', 'aegis-1,a1']) == 0
        return cfg_a, cfg_b

    @pytest.mark.parametrize('how', ['positional', 'variable'])
    def test_equal_identity_proceeds(
        self, how: str, configs: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The profile's own configuration beside --profile is accepted without a guard."""
        cfg_a, _cfg_b = self._install(configs)
        argv = ['--profile', 'aegis-1', *SKIP, '--yes']
        if how == 'positional':
            argv.insert(0, str(cfg_a))
        else:
            monkeypatch.setenv('CLAUDE_CODE_TOOLBOX_ENV_CONFIG', str(cfg_a))
        capsys.readouterr()

        assert run_main(argv) == 0

        output = _output(capsys)
        assert 'names a different configuration' not in output
        assert 'Command names: aegis-1, a1 [remembered]' in output

    @pytest.mark.parametrize(
        ('how', 'expected', 'remedy'),
        [
            (
                'positional', 'the configuration argument',
                'Drop the configuration argument and re-run the profile with its own configuration: --profile aegis-1.',
            ),
            (
                'variable', 'CLAUDE_CODE_TOOLBOX_ENV_CONFIG',
                'Clear CLAUDE_CODE_TOOLBOX_ENV_CONFIG (unset CLAUDE_CODE_TOOLBOX_ENV_CONFIG, or '
                'Remove-Item Env:CLAUDE_CODE_TOOLBOX_ENV_CONFIG in PowerShell) and re-run the profile with its own '
                'configuration: --profile aegis-1.',
            ),
        ],
    )
    def test_different_identity_goes_through_the_switch_guard(
        self, how: str, expected: str, remedy: str, e2e_isolated_home: dict[str, Path], configs: Path,
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Another configuration beside --profile is the switch guard, whose remedy undoes the argument or variable."""
        _cfg_a, cfg_b = self._install(configs)
        argv = ['--profile', 'aegis-1', *SKIP, '--yes']
        if how == 'positional':
            argv.insert(0, str(cfg_b))
        else:
            monkeypatch.setenv('CLAUDE_CODE_TOOLBOX_ENV_CONFIG', str(cfg_b))
        capsys.readouterr()

        assert run_main(argv) == 1

        output = _output(capsys)
        assert f'{expected} names a different configuration, {cfg_b.resolve()}.' in output
        assert remedy in output
        assert run_main([*argv, '--switch-config']) == 0
        assert (e2e_isolated_home['claude_dir'] / 'aegis-1' / 'agents' / 'other.md').is_file()

    @pytest.mark.parametrize(
        ('argv', 'env', 'expected'),
        [
            (
                ['--command-names', 'other'], {},
                '--command-names names the profile "other", but --profile selects "aegis-1"; clear --command-names',
            ),
            (
                [], {'CLAUDE_CODE_TOOLBOX_COMMAND_NAMES': 'other,x'},
                (
                    'CLAUDE_CODE_TOOLBOX_COMMAND_NAMES names the profile "other", but --profile selects "aegis-1"; '
                    'clear CLAUDE_CODE_TOOLBOX_COMMAND_NAMES'
                ),
            ),
        ],
    )
    def test_other_primary_beside_profile_is_an_error(
        self,
        argv: list[str],
        env: dict[str, str],
        expected: str,
        e2e_isolated_home: dict[str, Path],
        configs: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A command-names primary other than the profile names the flag or variable to clear."""
        self._install(configs)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        before = home_state(e2e_isolated_home['home'])
        capsys.readouterr()

        assert run_main(['--profile', 'aegis-1', *SKIP, '--yes', *argv]) == 1

        assert expected in _output(capsys)
        assert home_state(e2e_isolated_home['home']) == before

    def test_typed_aliases_beside_profile_change_them(self, e2e_isolated_home: dict[str, Path], configs: Path) -> None:
        """--profile NAME --command-names NAME,ALIAS changes the profile's aliases."""
        self._install(configs)

        assert run_main(['--profile', 'aegis-1', *SKIP, '--yes', '--command-names', 'aegis-1,z1']) == 0

        assert read_manifest(e2e_isolated_home['claude_dir'] / 'aegis-1')['command_names'] == ['aegis-1', 'z1']
        assert wrappers_absent(e2e_isolated_home['local_bin'], 'a1')


@pytest.mark.usefixtures('e2e_isolated_home')
class TestProfileBase:
    """--profile base re-runs the base install from its manifest."""

    def test_base_rerun_needs_no_configuration(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The base profile is re-run from the configuration its manifest records."""
        cfg = write_config(
            configs, 'base.yaml', {'name': 'Base', 'agents': ['agents/core.md'], 'user-settings': {'theme': 'dark'}},
        )
        claude_dir = e2e_isolated_home['claude_dir']
        assert run_main([str(cfg), *SKIP, '--yes']) == 0
        first = read_manifest(claude_dir)
        (claude_dir / 'agents' / 'core.md').unlink()
        capsys.readouterr()

        assert run_main(['--profile', 'base', *SKIP, '--yes']) == 0

        second = read_manifest(claude_dir)
        assert first['config_identity'] == setup_environment.config_identity_of(str(cfg.resolve()))
        assert second['config_identity'] == first['config_identity']
        assert second['installed_at'] != first['installed_at']
        assert (claude_dir / 'agents' / 'core.md').is_file()
        assert 'Custom command: Not created (no command-names specified)' in _output(capsys)
        assert not any(path.is_dir() and (path / 'manifest.json').exists() for path in claude_dir.iterdir())

    def test_base_rerun_refuses_a_configuration_that_now_declares_command_names(
        self, configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A base re-run of a configuration that turned into an isolated profile is an error."""
        cfg = write_config(configs, 'base.yaml', _plain())
        assert run_main([str(cfg), *SKIP, '--yes']) == 0
        write_config(configs, 'base.yaml', {**_plain(), 'command-names': ['iso']})
        capsys.readouterr()

        assert run_main(['--profile', 'base', *SKIP, '--yes']) == 1

        assert 'declares command-names iso, but --profile base re-runs the base profile' in _output(capsys)

    def test_base_with_command_names_is_an_error(
        self, configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--profile base cannot carry command names."""
        cfg = write_config(configs, 'base.yaml', _plain())
        assert run_main([str(cfg), *SKIP, '--yes']) == 0
        capsys.readouterr()

        assert run_main(['--profile', 'base', *SKIP, '--yes', '--command-names', 'x']) == 1

        assert 'selects the base profile, which has no command names; clear --command-names' in _output(capsys)

    def test_missing_profile_is_an_error(
        self, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A profile that was never installed cannot be re-run."""
        assert run_main(['--profile', 'ghost', *SKIP, '--yes']) == 1
        output = _output(capsys)
        assert 'No installed profile named "ghost"' in output
        assert run_main(['--profile', 'base', *SKIP, '--yes']) == 1
        assert 'No installed profile named "base"' in _output(capsys)


RUNNER = '''\
"""Child runner: setup_environment.main() with the machine-wide writers replaced."""
from unittest.mock import patch

from scripts import setup_environment
from tests.e2e.fixtures import setup_child

_real_find = setup_environment.find_command


def _find(name: str) -> str | None:
    return '/usr/bin/claude' if name == 'claude' else _real_find(name)


with (
    patch.object(setup_environment, 'find_command', _find),
    patch.object(setup_environment, 'ensure_local_bin_in_path', lambda: None),
    patch.object(setup_environment, 'refresh_path_from_registry', lambda: None),
):
    setup_child.main()
'''


@pytest.mark.usefixtures('e2e_isolated_home')
class TestProfileAll:
    """--profile all refreshes every installed profile, each in its own child run."""

    def _install_three(self, configs: Path) -> tuple[Path, Path, Path]:
        base = write_config(configs, 'base.yaml', {'name': 'Base', 'agents': ['agents/core.md']})
        one = write_config(configs, 'one.yaml', {'name': 'One', 'agents': ['agents/extra.md']})
        two = write_config(configs, 'two.yaml', {'name': 'Two', 'agents': ['agents/other.md']})
        assert run_main([str(base), *SKIP, '--yes']) == 0
        assert run_main([str(one), *SKIP, '--yes', '--command-names', 'aegis-1,a1']) == 0
        assert run_main([str(two), *SKIP, '--yes', '--command-names', 'aegis-2']) == 0
        return base, one, two

    def _runner(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        runner = tmp_path / 'runner.py'
        runner.write_text(RUNNER, encoding='utf-8')
        monkeypatch.setenv('PYTHONPATH', str(REPO_ROOT))
        return runner

    def test_refreshes_every_profile_and_reports_a_failed_child(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capfd: pytest.CaptureFixture[str],
    ) -> None:
        """The base first, then the isolated profiles in order; a failed child is named with its retry command."""
        _base, _one, two = self._install_three(configs)
        claude_dir = e2e_isolated_home['claude_dir']
        before = {name: read_manifest(claude_dir / name if name != 'base' else claude_dir)['installed_at']
                  for name in ('base', 'aegis-1', 'aegis-2')}
        (claude_dir / 'aegis-1' / 'agents' / 'extra.md').unlink()
        two.unlink()
        # A directory no child may resolve its profile through: the base child
        # would refuse it as an ambient CLAUDE_CONFIG_DIR, so a green run proves
        # the children start with it stripped
        monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(tmp_path / 'leaked'))
        runner = self._runner(tmp_path, monkeypatch)
        capfd.readouterr()

        code = run_main(['--profile', 'all', *SKIP, '--yes'], argv0=str(runner))

        captured = capfd.readouterr()
        output = (captured.out + captured.err).replace('\r\n', '\n')
        assert code == 1, output
        positions = [output.index(f'=== Profile {name} ===') for name in ('base', 'aegis-1', 'aegis-2')]
        assert positions == sorted(positions), 'the base runs first, then the isolated profiles in order'
        assert '* base: ok' in output
        assert '* aegis-1: ok' in output
        assert '* aegis-2: failed (exit code 1); retry with --profile aegis-2' in output
        assert read_manifest(claude_dir)['installed_at'] != before['base']
        assert read_manifest(claude_dir / 'aegis-1')['installed_at'] != before['aegis-1']
        assert read_manifest(claude_dir / 'aegis-2')['installed_at'] == before['aegis-2']
        assert (claude_dir / 'aegis-1' / 'agents' / 'extra.md').is_file(), 'the child did not re-install the profile'
        assert wrappers_exist(e2e_isolated_home['local_bin'], 'a1')
        assert 'Installed profiles this run did not refresh' not in output, (
            'a child lists no unrefreshed profiles; the parent report covers them all'
        )

    def test_children_carry_no_admin_and_the_report_shows_their_exit_codes(
        self, configs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str],
    ) -> None:
        """An elevated parent starts every child with --no-admin, so no child can relaunch and exit 0 unobserved."""
        _base, _one, two = self._install_three(configs)
        two.unlink()
        runner = self._runner(tmp_path, monkeypatch)
        real_run = setup_environment.subprocess.run
        argvs: list[list[str]] = []

        def _recording_run(argv: list[str], *, env: dict[str, str], check: bool) -> subprocess.CompletedProcess[bytes]:
            argvs.append(list(argv))
            return real_run(argv, env=env, check=check)

        capfd.readouterr()

        with (
            patch.object(setup_environment, 'is_admin', return_value=True),
            patch.object(setup_environment.subprocess, 'run', side_effect=_recording_run),
        ):
            code = run_main(['--profile', 'all', '--skip-install', '--yes'], argv0=str(runner))

        captured = capfd.readouterr()
        output = (captured.out + captured.err).replace('\r\n', '\n')
        assert code == 1, output
        assert [argv[argv.index('--profile') + 1] for argv in argvs] == ['base', 'aegis-1', 'aegis-2']
        for argv in argvs:
            assert '--no-admin' in argv, argv
            assert '--refresh-all-child' in argv, argv
        assert '* base: ok' in output
        assert '* aegis-1: ok' in output
        assert '* aegis-2: failed (exit code 1); retry with --profile aegis-2' in output

    @pytest.mark.parametrize(
        ('failing_child', 'title', 'expected_code'),
        [
            (False, 'Setup Completed Successfully!', 0),
            (True, 'Setup Completed with Errors', 1),
        ],
    )
    def test_an_elevated_parent_holds_its_window_until_the_report_is_read(
        self, failing_child: bool, title: str, expected_code: int, configs: Path, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str],
    ) -> None:
        """The window a UAC relaunch opened closes on exit, so the parent waits for Enter after its report."""
        _base, _one, two = self._install_three(configs)
        if failing_child:
            two.unlink()
        runner = self._runner(tmp_path, monkeypatch)
        prompts: list[str] = []

        def _input(prompt: str) -> str:
            prompts.append(prompt)
            return ''

        capfd.readouterr()

        with (
            patch.object(setup_environment.platform, 'system', return_value='Windows'),
            patch.object(setup_environment, 'is_admin', return_value=True),
            patch.object(setup_environment, 'is_running_in_pytest', return_value=False),
            patch('builtins.input', side_effect=_input),
        ):
            code = run_main(['--elevated-via-uac', '--profile', 'all', '--skip-install', '--yes'], argv0=str(runner))

        captured = capfd.readouterr()
        output = (captured.out + captured.err).replace('\r\n', '\n')
        assert code == expected_code, output
        assert prompts == ['Press Enter to exit...'], 'the parent waits once, after every child has run'
        assert output.index('Profiles refreshed:') < output.index(title), 'the report is on screen before the pause'
        assert '* base: ok' in output
        assert '* aegis-1: ok' in output
        if failing_child:
            assert '* aegis-2: failed (exit code 1); retry with --profile aegis-2' in output
        else:
            assert '* aegis-2: ok' in output
            assert 'Every installed profile has been refreshed.' in output

    @pytest.mark.parametrize(
        ('argv', 'expected_reason'),
        [
            (['--profile', 'all', '--yes'], 'Installing Claude Code (includes Node.js and Git)'),
            (['--profile', 'all', '--yes', '--skip-install'], 'Global npm package: echo npm install -g fake'),
        ],
    )
    def test_non_admin_windows_parent_elevates_once_before_any_child(
        self, argv: list[str], expected_reason: str, configs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Elevation is decided in the parent from every profile, before consent and before any child starts."""
        base = write_config(configs, 'base.yaml', {'name': 'Base', 'agents': ['agents/core.md']})
        one = write_config(configs, 'one.yaml', {
            'name': 'One', 'agents': ['agents/extra.md'], 'dependencies': {'common': ['echo npm install -g fake']},
        })
        assert run_main([str(base), *SKIP, '--yes']) == 0
        with patch.object(setup_environment, 'install_dependencies', return_value=[]):
            assert run_main([str(one), *SKIP, '--yes', '--command-names', 'aegis-1']) == 0
        runner = self._runner(tmp_path, monkeypatch)
        real_decide = setup_environment.refresh_all_elevation_reasons

        def _decide_as_windows(
            profiles: list[setup_environment.InstalledProfile], args: argparse.Namespace,
        ) -> list[str]:
            with patch.object(setup_environment.platform, 'system', return_value='Windows'):
                return real_decide(profiles, args)

        elevations: list[list[str] | None] = []

        def _elevate(script_args: list[str] | None = None) -> None:
            elevations.append(script_args)
            raise SystemExit(0)

        capsys.readouterr()

        with (
            patch.object(setup_environment, 'is_admin', return_value=False),
            patch.object(setup_environment, 'refresh_all_elevation_reasons', side_effect=_decide_as_windows),
            patch.object(setup_environment, 'request_admin_elevation', side_effect=_elevate),
            patch.object(setup_environment.subprocess, 'run') as run,
        ):
            code = run_main(argv, argv0=str(runner))

        output = _output(capsys)
        assert code == 0, output
        assert elevations == [None], 'the parent requests elevation exactly once, forwarding its own arguments'
        run.assert_not_called()
        assert 'Administrator Privileges Required' in output
        assert f'  - {expected_reason}' in output

    def test_dry_run_previews_every_child(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capfd: pytest.CaptureFixture[str],
    ) -> None:
        """Every child runs with --dry-run and changes nothing."""
        self._install_three(configs)
        home = e2e_isolated_home['home']
        before = home_state(home)
        runner = self._runner(tmp_path, monkeypatch)
        capfd.readouterr()

        code = run_main(['--profile', 'all', *SKIP, '--dry-run'], argv0=str(runner))

        captured = capfd.readouterr()
        output = captured.out + captured.err
        assert code == 0, output
        assert output.count('Dry run complete. No changes were made.') == 3
        assert home_state(home) == before

    def test_conflicting_arguments_and_missing_profiles_are_refused(
        self, configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--profile all takes no configuration, and needs at least one installed profile."""
        cfg = write_config(configs, 'base.yaml', _plain())
        assert run_main(['--profile', 'all', *SKIP, '--yes']) == 1
        assert 'No installed profile has a manifest' in _output(capsys)

        assert run_main([str(cfg), '--profile', 'all', *SKIP, '--yes']) == 1

        assert 'cannot be combined with a configuration' in _output(capsys)

    def test_interactive_decline_starts_no_child(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The parent asks once; a declined question starts nothing."""
        self._install_three(configs)
        home = e2e_isolated_home['home']
        before = home_state(home)
        runner = self._runner(tmp_path, monkeypatch)

        assert run_main(['--profile', 'all', *SKIP], argv0=str(runner), interactive=True, answers=['n']) == 0

        assert home_state(home) == before


@pytest.mark.usefixtures('e2e_isolated_home')
class TestLegacyManifests:
    """Manifests written before identities were recorded are matched and upgraded."""

    def test_absolute_local_source_reruns_and_upgrades_the_manifest(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A manifest naming its configuration by absolute path is enough for --profile."""
        cfg = write_config(configs, 'env.yaml', _plain())
        profile_dir = e2e_isolated_home['claude_dir'] / 'legacy-1'
        write_legacy_manifest(
            profile_dir, 'legacy-1', ['legacy-1', 'old-alias'],
            config_source=str(cfg.resolve()), config_source_type='local', config_source_url=None,
        )
        capsys.readouterr()

        assert run_main(['--profile', 'legacy-1', *SKIP, '--yes']) == 0

        manifest = read_manifest(profile_dir)
        assert manifest['config_identity'] == setup_environment.config_identity_of(str(cfg.resolve()))
        assert manifest['command_names'] == ['legacy-1']
        assert manifest['origins']['command_names'] == 'default'
        assert manifest['link'] is None
        assert (profile_dir / 'resolved-config.yaml').is_file()
        assert not validate_manifest(profile_dir / 'manifest.json', {**_plain(), 'command-names': ['legacy-1']})
        assert 'Command names: legacy-1 [default]' in _output(capsys)

    def test_url_source_is_matched_by_the_recorded_url(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A manifest with a config_source_url is identified by that URL, so a local file is a switch."""
        cfg = write_config(configs, 'env.yaml', _plain())
        write_legacy_manifest(
            e2e_isolated_home['claude_dir'] / 'legacy-1', 'legacy-1', ['legacy-1'],
            config_source='shared-env', config_source_type='repo',
            config_source_url='https://example.com/shared-env.yaml',
        )
        capsys.readouterr()

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'legacy-1']) == 1

        assert (
            'Profile "legacy-1" was installed from shared-env; the configuration argument names a different'
        ) in _output(capsys)

    def test_relative_source_needs_the_configuration_once(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A relative source that no longer resolves is replaced by the configuration the re-run is given."""
        cfg = write_config(configs, 'env.yaml', _plain())
        profile_dir = e2e_isolated_home['claude_dir'] / 'legacy-1'
        write_legacy_manifest(
            profile_dir, 'legacy-1', ['legacy-1'],
            config_source='./env.yaml', config_source_type='local', config_source_url=None,
        )
        capsys.readouterr()
        assert run_main(['--profile', 'legacy-1', *SKIP, '--yes']) == 1
        output = _output(capsys)
        assert "records the configuration './env.yaml', which cannot be resolved from this directory" in output
        assert '--profile legacy-1 <configuration>' in output

        assert run_main(['--profile', 'legacy-1', str(cfg), *SKIP, '--yes']) == 0

        output = _output(capsys)
        assert f'Recording {cfg.resolve()} as the configuration of profile "legacy-1"' in output
        assert read_manifest(profile_dir)['config_identity'] == setup_environment.config_identity_of(str(cfg.resolve()))
        assert run_main(['--profile', 'legacy-1', *SKIP, '--yes']) == 0, 'the second re-run needs no configuration'

    def test_rerun_from_todays_manifest_and_projects_link_layout(
        self, e2e_isolated_home: dict[str, Path], configs: Path,
    ) -> None:
        """A profile installed with link-projects-dir and the previous manifest shape re-runs intact."""
        config = {**_plain(), 'command-names': ['linked-1', 'l1'], 'link-projects-dir': True}
        cfg = write_config(configs, 'env.yaml', config)
        claude_dir = e2e_isolated_home['claude_dir']
        assert run_main([str(cfg), *SKIP, '--yes']) == 0
        profile_dir = claude_dir / 'linked-1'
        projects = profile_dir / 'projects'
        assert setup_environment._is_windows_reparse_point(projects) or projects.is_symlink()
        write_legacy_manifest(
            profile_dir, 'linked-1', ['linked-1', 'l1'],
            config_source=str(cfg.resolve()), config_source_type='local', config_source_url=None,
        )

        assert run_main(['--profile', 'linked-1', *SKIP, '--yes']) == 0

        assert setup_environment._is_windows_reparse_point(projects) or projects.is_symlink()
        (claude_dir / 'projects' / 'marker.txt').write_text('shared session\n', encoding='utf-8')
        assert (projects / 'marker.txt').is_file(), 'the link no longer reaches the base projects directory'
        manifest = read_manifest(profile_dir)
        assert manifest['command_names'] == ['linked-1', 'l1']
        assert manifest['origins']['command_names'] == 'yaml'
        assert wrappers_exist(e2e_isolated_home['local_bin'], 'l1')


@pytest.mark.usefixtures('e2e_isolated_home')
class TestClaudePersonalLikeProfile:
    """A profile that carries its names in the configuration re-runs from the configuration."""

    def test_rerun_follows_the_configuration_aliases(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--profile claude-personal re-reads the aliases and drops the ones the configuration dropped."""
        config = {
            'name': 'Personal Profile',
            'command-names': ['claude-personal', 'claude-p', 'claude-sub'],
            'user-settings': {'theme': 'dark'},
            'global-config': None,
        }
        cfg = write_config(configs, 'claude-personal.yaml', config)
        claude_dir, local_bin = e2e_isolated_home['claude_dir'], e2e_isolated_home['local_bin']
        assert run_main([str(cfg), *SKIP, '--yes']) == 0
        capsys.readouterr()

        assert run_main(['--profile', 'claude-personal', *SKIP, '--yes']) == 0

        manifest = read_manifest(claude_dir / 'claude-personal')
        assert manifest['command_names'] == ['claude-personal', 'claude-p', 'claude-sub']
        assert manifest['origins']['command_names'] == 'yaml'
        for name in manifest['command_names']:
            assert wrappers_exist(local_bin, name)
        assert 'Command names: claude-personal, claude-p, claude-sub [yaml]' in _output(capsys)
        assert json.loads((claude_dir / 'claude-personal' / 'config.json').read_text(encoding='utf-8'))['theme'] == 'dark'

        write_config(configs, 'claude-personal.yaml', {**config, 'command-names': ['claude-personal', 'claude-p']})
        assert run_main(['--profile', 'claude-personal', *SKIP, '--yes']) == 0
        assert read_manifest(claude_dir / 'claude-personal')['command_names'] == ['claude-personal', 'claude-p']
        assert wrappers_absent(local_bin, 'claude-sub')


@pytest.mark.usefixtures('e2e_isolated_home')
class TestSharedDestinations:
    """Destinations outside ~/.claude shared by profiles of different configurations are named."""

    def _configs(self, configs: Path, tmp_path: Path, *, b_source: str) -> tuple[Path, Path, Path]:
        shared = tmp_path / 'shared' / 'tool.txt'
        cfg_a = write_config(configs, 'a.yaml', {
            'name': 'A', 'files-to-download': [{'source': 'files/same-a.txt', 'dest': str(shared)}],
        })
        cfg_b = write_config(configs, 'b.yaml', {
            'name': 'B', 'files-to-download': [{'source': b_source, 'dest': str(shared)}],
        })
        return cfg_a, cfg_b, shared

    def test_different_source_warns_before_consent(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The second profile's summary names the first profile, its configuration and its source."""
        cfg_a, cfg_b, shared = self._configs(configs, tmp_path, b_source='files/different.txt')
        assert run_main([str(cfg_a), *SKIP, '--yes', '--command-names', 'prof-a']) == 0
        record = read_manifest(e2e_isolated_home['claude_dir'] / 'prof-a')['machine_wide_destinations']
        assert record == [{
            'dest': str(shared), 'source': str((configs / 'files' / 'same-a.txt').resolve()),
            'sha256': setup_environment._sha256_of_file(shared),
        }]
        capsys.readouterr()

        assert run_main([str(cfg_b), *SKIP, '--dry-run', '--command-names', 'prof-b']) == 0

        output = _output(capsys)
        assert '[!] ATTENTION:' in output
        assert (
            f'[!] {shared} is also installed by profile "prof-a" ({cfg_a.resolve()}) from '
            f'{(configs / "files" / "same-a.txt").resolve()}; this run writes it from '
            f'{(configs / "files" / "different.txt").resolve()} and leaves it untouched only when the content is identical'
        ) in output

    def test_identical_file_is_left_untouched(
        self, configs: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Identical content from another configuration leaves the file on disk as it is."""
        cfg_a, cfg_b, shared = self._configs(configs, tmp_path, b_source='files/same-b.txt')
        assert run_main([str(cfg_a), *SKIP, '--yes', '--command-names', 'prof-a']) == 0
        old_time = 1_000_000_000
        os.utime(shared, (old_time, old_time))
        if sys.platform != 'win32':
            shared.chmod(stat.S_IRUSR | stat.S_IWUSR)
        capsys.readouterr()

        assert run_main([str(cfg_b), *SKIP, '--yes', '--command-names', 'prof-b']) == 0

        assert 'Unchanged: tool.txt' in _output(capsys)
        assert int(shared.stat().st_mtime) == old_time
        assert shared.read_text(encoding='utf-8') == 'identical content\n'


@pytest.mark.usefixtures('e2e_isolated_home')
class TestPinEffectAndUnrefreshedProfiles:
    """A pin names the profiles it affects, and a run lists the profiles it did not refresh."""

    @pytest.mark.parametrize(
        ('installed', 'expected'),
        [
            (
                '2.1.100',
                (
                    'Claude Code version pin 2.1.280: moves the binary from 2.1.100 to 2.1.280 '
                    'for the other installed profile(s) prof-a'
                ),
            ),
            (
                '2.1.280',
                'Claude Code version pin 2.1.280: holds the binary at 2.1.280 for the other installed profile(s) prof-a',
            ),
        ],
    )
    def test_pin_effect_line_in_the_summary(
        self, installed: str, expected: str, configs: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A base run that pins a version names the other installed profile the pin affects."""
        cfg_a = write_config(configs, 'a.yaml', _plain())
        assert run_main([str(cfg_a), *SKIP, '--yes', '--command-names', 'prof-a']) == 0
        cfg_base = write_config(configs, 'base.yaml', {**_plain('Base'), 'claude-code-version': '2.1.280'})
        capsys.readouterr()

        with patch.object(setup_environment, '_installed_claude_version', return_value=installed):
            assert run_main([str(cfg_base), '--no-admin', '--dry-run']) == 0

        assert f'* {expected}' in _output(capsys)

    def test_isolated_pin_effect_among_machine_wide_writes(
        self, configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """An isolated run lists the pin effect among its machine-wide writes."""
        cfg_base = write_config(configs, 'base.yaml', _plain('Base'))
        assert run_main([str(cfg_base), *SKIP, '--yes']) == 0
        cfg_b = write_config(configs, 'b.yaml', {**_plain('B'), 'claude-code-version': '2.1.280'})
        capsys.readouterr()

        with patch.object(setup_environment, '_installed_claude_version', return_value='2.1.280'):
            assert run_main([str(cfg_b), '--no-admin', '--dry-run', '--command-names', 'prof-b']) == 0

        expected = 'Claude Code version pin 2.1.280: holds the binary at 2.1.280 for the other installed profile(s) base'
        lines = [line for line in _output(capsys).splitlines() if expected in line]
        assert len(lines) == 1, lines
        assert '[machine-wide]' in lines[0]

    def test_unrefreshed_profiles_are_listed_after_the_run(
        self, configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The closing summary names every other installed profile with its --profile command."""
        cfg = write_config(configs, 'env.yaml', _plain())
        assert run_main([str(cfg), *SKIP, '--yes']) == 0
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'prof-a']) == 0
        capsys.readouterr()

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'prof-b']) == 0

        output = _output(capsys)
        assert '* Installed profiles this run did not refresh:' in output
        assert '- base (--profile base)' in output
        assert '- prof-a (--profile prof-a)' in output
        assert '- prof-b' not in output


@pytest.mark.usefixtures('e2e_isolated_home')
class TestManifestRecords:
    """The manifest records the configuration, the choices and what the run wrote."""

    def test_isolated_install_records_everything(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path,
    ) -> None:
        """Every record of an isolated install is present and validates."""
        outside = tmp_path / 'shared' / 'tool.txt'
        config = {
            'name': 'Recorded',
            'agents': ['agents/core.md'],
            'rules': ['rules/rule.md'],
            'files-to-download': [
                {'source': 'files/same-a.txt', 'dest': str(outside)},
                {'source': 'files/different.txt', 'dest': '~/.claude/prof-a/extra/inside.txt'},
            ],
            'mcp-servers': [{'name': 'srv', 'scope': 'profile', 'command': 'echo'}],
            'os-env-variables': {'PROFILE_VAR': 'x'},
            'user-settings': {'theme': 'dark', 'model': 'sonnet'},
            'command-defaults': {'system-prompt': 'rules/rule.md'},
        }
        cfg = write_config(configs, 'env.yaml', config)
        claude_dir = e2e_isolated_home['claude_dir']

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'prof-a,alias']) == 0

        profile_dir = claude_dir / 'prof-a'
        manifest = read_manifest(profile_dir)
        assert not validate_manifest(profile_dir / 'manifest.json', {**config, 'command-names': ['prof-a', 'alias']})
        assert manifest['config_source'] == str(cfg.resolve())
        assert manifest['config_identity'] == setup_environment.config_identity_of(str(cfg.resolve()))
        resolved = yaml.safe_load((profile_dir / 'resolved-config.yaml').read_text(encoding='utf-8'))
        assert 'command-names' not in resolved
        assert resolved['agents'] == ['agents/core.md']
        assert manifest['config_digest'] == setup_environment.config_digest_of(
            (profile_dir / 'resolved-config.yaml').read_text(encoding='utf-8'),
        )
        assert manifest['command_names'] == ['prof-a', 'alias']
        assert manifest['origins'] == {'command_names': 'cli', 'components': 'yaml'}
        assert manifest['components'] is None
        assert manifest['yaml_values'] == {'command_names': [], 'components': []}
        assert manifest['files_written'] == ['agents/core.md', 'extra/inside.txt', 'prompts/rule.md', 'rules/rule.md']
        assert manifest['machine_wide_destinations'] == [{
            'dest': str(outside), 'source': str((configs / 'files' / 'same-a.txt').resolve()),
            'sha256': setup_environment._sha256_of_file(outside),
        }]
        assert manifest['os_env_written'] == [], 'an isolated run routes its variables to the env loaders'
        assert manifest['settings_keys_written'] == ['model', 'theme']
        assert manifest['mcp_servers'] == [{'name': 'srv', 'scopes': ['profile']}]
        for relative in manifest['files_written']:
            assert (profile_dir / relative).is_file(), relative

    def test_base_install_records_os_variables_and_settings(
        self, e2e_isolated_home: dict[str, Path], configs: Path,
    ) -> None:
        """A base install records the OS variables it set and the settings keys it wrote."""
        config = {
            'name': 'Base',
            'os-env-variables': {'MY_VAR': 'x', 'GONE_VAR': None},
            'user-settings': {'theme': 'dark'},
            'hooks': {'files': ['rules/rule.md'], 'events': [
                {'event': 'PostToolUse', 'matcher': 'Edit', 'type': 'command', 'command': 'rule.md'},
            ]},
        }
        cfg = write_config(configs, 'base.yaml', config)
        claude_dir = e2e_isolated_home['claude_dir']

        assert run_main([str(cfg), *SKIP, '--yes']) == 0

        manifest = read_manifest(claude_dir)
        assert not validate_manifest(claude_dir / 'manifest.json', config)
        assert manifest['name'] is None
        assert manifest['command_names'] == []
        assert manifest['origins'] == {'command_names': None, 'components': 'yaml'}
        assert manifest['os_env_written'] == ['MY_VAR']
        assert manifest['settings_keys_written'] == ['hooks', 'theme']
        assert manifest['files_written'] == ['hooks/rule.md']

    def test_base_install_records_settings_env_entries_one_by_one(
        self, e2e_isolated_home: dict[str, Path], configs: Path,
    ) -> None:
        """Each env variable the settings write is its own record, so a switch can remove one and keep the rest."""
        config = {'name': 'Base', 'user-settings': {'theme': 'dark', 'env': {'FOO': 'x', 'GONE': None}}}
        cfg = write_config(configs, 'base.yaml', config)

        assert run_main([str(cfg), *SKIP, '--yes']) == 0

        assert read_manifest(e2e_isolated_home['claude_dir'])['settings_keys_written'] == ['env.FOO', 'theme']


def _three_components() -> dict[str, Any]:
    """A configuration with one default component and two optional ones, each shipping one agent."""
    return {
        'name': 'Three Components',
        'agents': ['agents/core.md', 'agents/extra.md', 'agents/other.md'],
        'components': [
            {'name': 'core', 'includes': {'agents': ['agents/core.md']}},
            {'name': 'extra', 'default': False, 'includes': {'agents': ['agents/extra.md']}},
            {'name': 'other', 'default': False, 'includes': {'agents': ['agents/other.md']}},
        ],
    }


def _components_line(output: str) -> str:
    """The first Components header line of a run's output, which carries the origin marker."""
    return output.split('Components:')[1].split('\n')[0]


@pytest.mark.usefixtures('e2e_isolated_home')
class TestComponentDeltaPrecedence:
    """The component delta ranks typed, environment, remembered, then the author defaults, and is marked so."""

    def test_typed_with_is_marked_cli_and_recorded(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        cfg = write_config(configs, 'env.yaml', _three_components())
        profile_dir = e2e_isolated_home['claude_dir'] / 'aegis-1'

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'aegis-1', '--with', 'extra']) == 0

        assert '[cli]' in _components_line(_output(capsys))
        manifest = read_manifest(profile_dir)
        assert manifest['origins']['components'] == 'cli'
        assert manifest['components'] == {'select': None, 'with': 'extra', 'without': None}
        assert (profile_dir / 'agents' / 'extra.md').is_file()
        assert not (profile_dir / 'agents' / 'other.md').exists()

    def test_environment_with_is_marked_env_and_kept_by_a_yes_rerun(
        self, e2e_isolated_home: dict[str, Path], configs: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A delta from the environment is remembered like a typed one, so a bare --yes re-run keeps the component."""
        cfg = write_config(configs, 'env.yaml', _three_components())
        profile_dir = e2e_isolated_home['claude_dir'] / 'aegis-1'
        monkeypatch.setenv('CLAUDE_CODE_TOOLBOX_WITH', 'extra')
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'aegis-1']) == 0
        assert '[env]' in _components_line(_output(capsys))
        assert read_manifest(profile_dir)['origins']['components'] == 'env'
        monkeypatch.delenv('CLAUDE_CODE_TOOLBOX_WITH')

        assert run_main(['--profile', 'aegis-1', *SKIP, '--yes']) == 0

        assert '[remembered]' in _components_line(_output(capsys))
        manifest = read_manifest(profile_dir)
        assert manifest['components'] == {'select': None, 'with': 'extra', 'without': None}
        assert manifest['origins']['components'] == 'env'
        assert (profile_dir / 'agents' / 'extra.md').is_file(), 'the added component was deselected'

    def test_typed_with_replaces_the_whole_remembered_delta(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A selector typed for the re-run replaces the remembered delta key by key, so the old addition is removed."""
        cfg = write_config(configs, 'env.yaml', _three_components())
        profile_dir = e2e_isolated_home['claude_dir'] / 'aegis-1'
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'aegis-1', '--with', 'extra']) == 0
        assert (profile_dir / 'agents' / 'extra.md').is_file()
        capsys.readouterr()

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'aegis-1', '--with', 'other']) == 0

        assert '[cli]' in _components_line(_output(capsys))
        manifest = read_manifest(profile_dir)
        assert manifest['components'] == {'select': None, 'with': 'other', 'without': None}
        assert manifest['origins']['components'] == 'cli'
        assert (profile_dir / 'agents' / 'other.md').is_file()
        assert not (profile_dir / 'agents' / 'extra.md').exists(), 'the previously added component stayed installed'

    def test_environment_select_beats_the_remembered_delta(
        self, e2e_isolated_home: dict[str, Path], configs: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        cfg = write_config(configs, 'env.yaml', _three_components())
        profile_dir = e2e_isolated_home['claude_dir'] / 'aegis-1'
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'aegis-1', '--with', 'extra']) == 0
        monkeypatch.setenv('CLAUDE_CODE_TOOLBOX_SELECT', 'core,other')
        capsys.readouterr()

        assert run_main(['--profile', 'aegis-1', *SKIP, '--yes']) == 0

        assert '[env]' in _components_line(_output(capsys))
        manifest = read_manifest(profile_dir)
        assert manifest['components'] == {'select': 'core,other', 'with': None, 'without': None}
        assert manifest['origins']['components'] == 'env'
        assert (profile_dir / 'agents' / 'other.md').is_file()
        assert not (profile_dir / 'agents' / 'extra.md').exists()

    def test_picker_choice_is_recorded_as_typed_and_kept_by_a_yes_rerun(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Toggling a component in the numbered picker is remembered exactly, and --profile keeps that set."""
        cfg = write_config(configs, 'env.yaml', _three_components())
        profile_dir = e2e_isolated_home['claude_dir'] / 'aegis-1'

        # The picker lists core, extra, other with core checked: '2' adds extra, Enter confirms, 'y' installs
        assert run_main([str(cfg), *SKIP, '--command-names', 'aegis-1'], interactive=True, answers=['2', '', 'y']) == 0

        manifest = read_manifest(profile_dir)
        assert manifest['components'] == {'select': 'core,extra', 'with': None, 'without': 'other'}
        assert manifest['origins']['components'] == 'cli'
        assert (profile_dir / 'agents' / 'extra.md').is_file()
        assert not (profile_dir / 'agents' / 'other.md').exists()
        capsys.readouterr()

        assert run_main(['--profile', 'aegis-1', *SKIP, '--yes']) == 0

        output = _output(capsys)
        assert '[remembered]' in _components_line(output)
        assert not [line for line in output.splitlines() if 'Removed' in line and 'agents' in line], (
            'the remembered picker choice must delete nothing on a re-run'
        )
        assert read_manifest(profile_dir)['components'] == {'select': 'core,extra', 'with': None, 'without': 'other'}
        assert (profile_dir / 'agents' / 'core.md').is_file()
        assert (profile_dir / 'agents' / 'extra.md').is_file()
        assert not (profile_dir / 'agents' / 'other.md').exists()


@pytest.mark.usefixtures('e2e_isolated_home')
class TestRememberedSelectorsAgainstTheRegistry:
    """A remembered selector is checked against the components the configuration declares today."""

    def test_remembered_without_naming_a_removed_component_is_dropped_with_a_warning(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        config = _three_components()
        config['components'][2]['default'] = True  # 'other' is on by default, so --without other has an effect
        cfg = write_config(configs, 'env.yaml', config)
        profile_dir = e2e_isolated_home['claude_dir'] / 'aegis-1'
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'aegis-1', '--without', 'other', '--with', 'extra']) == 0
        assert (profile_dir / 'agents' / 'extra.md').is_file()
        assert not (profile_dir / 'agents' / 'other.md').exists()
        config['agents'].remove('agents/other.md')
        config['components'].pop(2)
        write_config(configs, 'env.yaml', config)
        capsys.readouterr()

        assert run_main(['--profile', 'aegis-1', *SKIP, '--yes']) == 0

        output = _output(capsys)
        assert (
            "components: the remembered selection of profile aegis-1 names 'other', which the configuration "
            'no longer declares; dropped [remembered]'
        ) in output
        assert '[remembered]' in _components_line(output)
        assert (profile_dir / 'agents' / 'extra.md').is_file(), 'the remembered addition was lost with the dropped name'
        assert read_manifest(profile_dir)['components'] == {'select': None, 'with': 'extra', 'without': None}

    def test_remembered_with_naming_a_removed_component_refuses_and_names_the_manifest(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        config = _three_components()
        cfg = write_config(configs, 'env.yaml', config)
        profile_dir = e2e_isolated_home['claude_dir'] / 'aegis-1'
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'aegis-1', '--with', 'other']) == 0
        config['agents'].remove('agents/other.md')
        config['components'].pop(2)
        write_config(configs, 'env.yaml', config)
        before = home_state(e2e_isolated_home['home'])
        capsys.readouterr()

        assert run_main(['--profile', 'aegis-1', *SKIP, '--yes']) == 1

        output = _output(capsys)
        assert (
            f'components: the remembered selection of profile aegis-1 (recorded in {profile_dir / "manifest.json"}) '
            "names 'other' in --with, which the configuration no longer declares; pass --with explicitly to replace "
            'the remembered selection, or --select all.'
        ) in output
        assert '--with: unknown component' not in output, 'the error names the manifest, not a flag nobody typed'
        assert home_state(e2e_isolated_home['home']) == before


@pytest.mark.usefixtures('e2e_isolated_home')
class TestCommandNamesPrecedence:
    """Each command-names rule, through real installs: typed single name, typed aliases, configuration re-read."""

    PERSONAL_NAMES = ['claude-personal', 'claude-p', 'claude-sub']

    def _personal(self, configs: Path, names: list[str] | None = None) -> Path:
        return write_config(configs, 'claude-personal.yaml', {
            'name': 'Personal Profile',
            'command-names': names if names is not None else list(self.PERSONAL_NAMES),
            'user-settings': {'theme': 'dark'},
        })

    def test_single_typed_name_on_a_fresh_profile_is_the_whole_list(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--command-names claude-personal installs one wrapper although the configuration lists aliases."""
        cfg = self._personal(configs)
        claude_dir, local_bin = e2e_isolated_home['claude_dir'], e2e_isolated_home['local_bin']

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'claude-personal']) == 0

        manifest = read_manifest(claude_dir / 'claude-personal')
        assert manifest['command_names'] == ['claude-personal']
        assert manifest['origins']['command_names'] == 'cli'
        assert wrappers_exist(local_bin, 'claude-personal')
        assert wrappers_absent(local_bin, 'claude-p')
        assert wrappers_absent(local_bin, 'claude-sub')
        assert 'Command names: claude-personal [cli]' in _output(capsys)
        capsys.readouterr()

        assert run_main(['--profile', 'claude-personal', *SKIP, '--yes']) == 0

        assert read_manifest(claude_dir / 'claude-personal')['command_names'] == ['claude-personal']
        assert wrappers_absent(local_bin, 'claude-p')
        assert wrappers_absent(local_bin, 'claude-sub')
        assert 'Command names: claude-personal [remembered]' in _output(capsys)

    def test_configuration_only_rerun_keeps_the_typed_aliases(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Without --command-names or --profile, a configuration whose primary matches keeps the typed aliases."""
        cfg = write_config(configs, 'env.yaml', {**_plain(), 'command-names': ['p1', 'y1']})
        claude_dir, local_bin = e2e_isolated_home['claude_dir'], e2e_isolated_home['local_bin']
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'p1,t1']) == 0
        capsys.readouterr()

        assert run_main([str(cfg), *SKIP, '--yes']) == 0

        assert read_manifest(claude_dir / 'p1')['command_names'] == ['p1', 't1']
        assert wrappers_exist(local_bin, 't1')
        assert wrappers_absent(local_bin, 'y1')
        assert 'Command names: p1, t1 [remembered]' in _output(capsys)

    def test_single_typed_name_on_a_yaml_profile_re_reads_the_aliases_until_the_primary_changes(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """CONFIG --command-names claude-personal re-reads the aliases; once the YAML primary differs, the name is alone."""
        cfg = self._personal(configs)
        claude_dir, local_bin = e2e_isolated_home['claude_dir'], e2e_isolated_home['local_bin']
        assert run_main([str(cfg), *SKIP, '--yes']) == 0
        assert read_manifest(claude_dir / 'claude-personal')['origins']['command_names'] == 'yaml'
        capsys.readouterr()

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'claude-personal']) == 0

        manifest = read_manifest(claude_dir / 'claude-personal')
        assert manifest['command_names'] == self.PERSONAL_NAMES
        assert manifest['origins']['command_names'] == 'yaml'
        for name in self.PERSONAL_NAMES:
            assert wrappers_exist(local_bin, name)
        assert 'Command names: claude-personal, claude-p, claude-sub [yaml]' in _output(capsys)

        self._personal(configs, ['other-name', 'claude-p'])
        capsys.readouterr()

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', 'claude-personal']) == 0

        manifest = read_manifest(claude_dir / 'claude-personal')
        assert manifest['command_names'] == ['claude-personal']
        assert manifest['origins']['command_names'] == 'cli'
        assert wrappers_exist(local_bin, 'claude-personal')
        assert wrappers_absent(local_bin, 'claude-p')
        assert wrappers_absent(local_bin, 'claude-sub')
        assert 'Command names: claude-personal [cli]' in _output(capsys)


@pytest.mark.usefixtures('e2e_isolated_home')
class TestSwitchKeepsSharedDestinations:
    """A configuration switch never removes a destination outside ~/.claude another profile still records."""

    def _shared_configs(self, configs: Path, tmp_path: Path) -> tuple[Path, Path, Path, Path]:
        shared = tmp_path / 'shared' / 'tool.txt'
        cfg_a = write_config(configs, 'a.yaml', {
            'name': 'A', 'agents': ['agents/core.md'],
            'files-to-download': [{'source': 'files/same-a.txt', 'dest': str(shared)}],
        })
        cfg_a2 = write_config(configs, 'a2.yaml', {
            'name': 'A2', 'agents': ['agents/extra.md'],
            'files-to-download': [{'source': 'files/same-a.txt', 'dest': str(shared)}],
        })
        cfg_b = write_config(configs, 'b.yaml', {'name': 'B', 'agents': ['agents/other.md']})
        return cfg_a, cfg_a2, cfg_b, shared

    def test_destination_another_profile_records_is_kept(
        self, e2e_isolated_home: dict[str, Path], configs: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        cfg_a, cfg_a2, cfg_b, shared = self._shared_configs(configs, tmp_path)
        claude_dir = e2e_isolated_home['claude_dir']
        assert run_main([str(cfg_a), *SKIP, '--yes']) == 0
        assert run_main([str(cfg_a2), *SKIP, '--yes', '--command-names', 'aegis-1']) == 0
        assert shared.read_text(encoding='utf-8') == 'identical content\n'
        capsys.readouterr()

        assert run_main([str(cfg_b), *SKIP, '--yes', '--switch-config']) == 0

        output = _output(capsys)
        assert f'file outside ~/.claude kept: {shared} (recorded by profile aegis-1)' in output
        assert f'Removed {shared}' not in output
        assert shared.read_text(encoding='utf-8') == 'identical content\n'
        assert not (claude_dir / 'agents' / 'core.md').exists(), 'the profile residue is still removed'
        assert (claude_dir / 'agents' / 'other.md').is_file()

    def test_destination_only_this_profile_records_is_removed(
        self, configs: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        cfg_a, _cfg_a2, cfg_b, shared = self._shared_configs(configs, tmp_path)
        assert run_main([str(cfg_a), *SKIP, '--yes']) == 0
        assert shared.is_file()
        capsys.readouterr()

        assert run_main([str(cfg_b), *SKIP, '--yes', '--switch-config']) == 0

        output = _output(capsys)
        assert f'file outside ~/.claude: {shared}' in output
        assert f'Removed {shared}' in output
        assert not shared.exists()


@pytest.mark.usefixtures('e2e_isolated_home')
class TestSwitchKeepsMachineWideControls:
    """Switching a pinned base to an unpinned configuration leaves the binary controls to the pin gate."""

    def test_controls_survive_the_switch_while_another_profile_pins(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        claude_dir = e2e_isolated_home['claude_dir']
        cfg_iso = write_config(configs, 'iso.yaml', {**_plain('Iso'), 'claude-code-version': '2.1.280'})
        cfg_base = write_config(configs, 'base.yaml', {
            'name': 'Pinned Base', 'claude-code-version': '2.1.280',
            'os-env-variables': {'FOO': 'x'},
            'user-settings': {'theme': 'dark', 'env': {'FOO': 'x'}},
        })
        cfg_new = write_config(configs, 'new.yaml', {'name': 'Unpinned Base', 'user-settings': {'theme': 'light'}})
        assert run_main([str(cfg_iso), *SKIP, '--yes', '--command-names', 'pinned-1']) == 0
        assert run_main([str(cfg_base), *SKIP, '--yes']) == 0
        manifest = read_manifest(claude_dir)
        assert 'DISABLE_UPDATES' in manifest['os_env_written']
        assert 'env.DISABLE_UPDATES' in manifest['settings_keys_written']
        settings_env = json.loads((claude_dir / 'settings.json').read_text(encoding='utf-8'))['env']
        assert settings_env['DISABLE_UPDATES'] == '1'
        assert settings_env['FOO'] == 'x'
        os_env_writes: list[dict[str, str | None]] = []
        capsys.readouterr()

        assert run_main([str(cfg_new), *SKIP, '--yes', '--switch-config'], os_env_writes=os_env_writes) == 0

        output = _output(capsys)
        assert 'OS environment variable: FOO' in output
        assert 'settings.json env variable: FOO' in output
        assert 'DISABLE_UPDATES' not in output.split('The previous configuration leaves behind:')[1].split('Accepted via')[0]
        assert {'FOO': None} in os_env_writes, 'the variable the previous configuration set is deleted'
        for write in os_env_writes:
            for key in setup_environment.MACHINE_WIDE_ENV_CONTROLS:
                assert key not in write, f'{key} deletion scheduled by {write}'
        settings = json.loads((claude_dir / 'settings.json').read_text(encoding='utf-8'))
        assert settings['theme'] == 'light'
        assert settings['env']['DISABLE_UPDATES'] == '1', 'the control another profile still needs was removed'
        assert settings['env']['DISABLE_AUTOUPDATER'] == '1'
        assert 'FOO' not in settings['env']
