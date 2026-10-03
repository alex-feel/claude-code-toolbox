"""Tests for how setup_environment.py decides the command names of a run.

--command-names wins over CLAUDE_CODE_TOOLBOX_COMMAND_NAMES, which wins over
the configuration's command-names. A typed or environment value replaces the
configuration's list whole, and every source goes through the same
validation, reserved names included. The installation summary names the
source of the effective list and carries a typed list on its replay line.
"""

from __future__ import annotations

import argparse
import io
import os
from typing import Any
from unittest.mock import patch

import pytest

from scripts import setup_environment
from scripts.setup_environment import CommandNames
from scripts.setup_environment import ComponentSelection
from scripts.setup_environment import InstallationPlan
from scripts.setup_environment import resolve_command_names


def _args(command_names: str | None = None, *, env: dict[str, str] | None = None) -> argparse.Namespace:
    """Build resolved arguments the way main() does, from a typed value and an environment."""
    namespace = argparse.Namespace(
        config=None,
        yes=False,
        dry_run=False,
        skip_install=False,
        no_admin=False,
        env_vars=None,
        select=None,
        with_=None,
        without=None,
        list_components=False,
        command_names=command_names,
    )
    with patch.dict(os.environ, env or {}, clear=False):
        if not env:
            os.environ.pop('CLAUDE_CODE_TOOLBOX_COMMAND_NAMES', None)
        return setup_environment.resolve_args(namespace)


class TestCommandNamesTwin:
    """CLAUDE_CODE_TOOLBOX_COMMAND_NAMES is the registered twin of --command-names."""

    def test_twin_is_registered_as_a_value(self) -> None:
        """The registry maps the variable to the command_names argument."""
        twins = {twin.variable: twin for twin in setup_environment.ENV_TWINS}
        twin = twins['CLAUDE_CODE_TOOLBOX_COMMAND_NAMES']
        assert twin.dest == 'command_names'
        assert twin.kind == 'value'

    def test_environment_fills_an_absent_flag(self) -> None:
        """The variable supplies the names when the flag is not typed."""
        args = _args(env={'CLAUDE_CODE_TOOLBOX_COMMAND_NAMES': 'from-env'})
        assert args.command_names == 'from-env'
        assert args.origins['command_names'] == 'env'

    def test_typed_flag_wins_over_environment(self) -> None:
        """A typed value beats the variable."""
        args = _args('typed', env={'CLAUDE_CODE_TOOLBOX_COMMAND_NAMES': 'from-env'})
        assert args.command_names == 'typed'
        assert args.origins['command_names'] == 'cli'


class TestPrecedence:
    """Flag beats environment beats the configuration."""

    def test_flag_wins_over_environment_and_configuration(self) -> None:
        """Every source is set; the typed list is the effective one."""
        args = _args('cli-name', env={'CLAUDE_CODE_TOOLBOX_COMMAND_NAMES': 'env-name'})
        resolved, errors = resolve_command_names(args, {'command-names': ['yaml-name']})
        assert errors == []
        assert resolved == CommandNames(['cli-name'], 'cli')

    def test_environment_wins_over_configuration(self) -> None:
        """Without a flag, the variable replaces the configuration's list."""
        args = _args(env={'CLAUDE_CODE_TOOLBOX_COMMAND_NAMES': 'env-name,env-alias'})
        resolved, errors = resolve_command_names(args, {'command-names': ['yaml-name']})
        assert errors == []
        assert resolved == CommandNames(['env-name', 'env-alias'], 'env')

    def test_configuration_applies_without_flag_or_environment(self) -> None:
        """The configuration's list is used as written."""
        resolved, errors = resolve_command_names(_args(), {'command-names': ['yaml-name', 'yaml-alias']})
        assert errors == []
        assert resolved == CommandNames(['yaml-name', 'yaml-alias'], 'yaml')

    def test_configuration_string_form_is_one_name(self) -> None:
        """A scalar command-names value is a one-name list."""
        resolved, errors = resolve_command_names(_args(), {'command-names': 'solo'})
        assert errors == []
        assert resolved == CommandNames(['solo'], 'yaml')

    def test_no_source_means_a_base_install(self) -> None:
        """Without any source the run has no command names and no origin."""
        resolved, errors = resolve_command_names(_args(), {})
        assert errors == []
        assert resolved == CommandNames([], None)

    def test_empty_configuration_list_means_a_base_install(self) -> None:
        """An empty configuration list names nothing."""
        resolved, errors = resolve_command_names(_args(), {'command-names': []})
        assert errors == []
        assert resolved == CommandNames([], None)


class TestReplacementNeverMerges:
    """A typed or environment list replaces the configuration's list whole."""

    def test_single_typed_name_drops_the_configured_aliases(self) -> None:
        """One typed name is the whole list: no alias of the configuration survives."""
        config = {'command-names': ['claude-personal', 'claude-p', 'claude-sub']}
        resolved, errors = resolve_command_names(_args('claude-p2'), config)
        assert errors == []
        assert resolved.names == ['claude-p2']

    def test_typed_list_keeps_its_order(self) -> None:
        """The first typed name is the primary, the rest are aliases in typed order."""
        resolved, errors = resolve_command_names(_args('main,second,third'), {'command-names': ['x']})
        assert errors == []
        assert resolved.names == ['main', 'second', 'third']

    def test_typed_value_tolerates_spaces_around_commas_and_empty_items(self) -> None:
        """Whitespace around commas and empty items are dropped, as in --select."""
        resolved, errors = resolve_command_names(_args(' main , alias ,'), {})
        assert errors == []
        assert resolved.names == ['main', 'alias']

    def test_configuration_is_not_consulted_for_a_typed_list(self) -> None:
        """An invalid configuration list does not matter when a list is typed."""
        resolved, errors = resolve_command_names(_args('good'), {'command-names': ['bad name']})
        assert errors == []
        assert resolved.names == ['good']


class TestValidation:
    """Every source goes through the same name validation."""

    @pytest.mark.parametrize('value', ['', ' ', ',', ' , '])
    def test_typed_value_without_any_name_is_refused(self, value: str) -> None:
        """A typed list must name at least one command."""
        _resolved, errors = resolve_command_names(_args(value), {})
        assert len(errors) == 1
        assert '--command-names requires at least one command name' in errors[0]

    def test_environment_value_without_any_name_is_refused_naming_the_variable(self) -> None:
        """The message names the variable the value came from."""
        args = _args(env={'CLAUDE_CODE_TOOLBOX_COMMAND_NAMES': ' , '})
        _resolved, errors = resolve_command_names(args, {})
        assert errors == ['CLAUDE_CODE_TOOLBOX_COMMAND_NAMES requires at least one command name']

    @pytest.mark.parametrize(
        ('value', 'fragment'),
        [
            ('../escape', 'Invalid command name "../escape" in --command-names'),
            ('-dash', 'Invalid command name "-dash" in --command-names'),
            ('.hidden', 'Invalid command name ".hidden" in --command-names'),
            ('a/b', 'Invalid command name "a/b" in --command-names'),
            ('bad$name', 'Invalid command name "bad$name" in --command-names'),
        ],
    )
    def test_typed_names_follow_the_configuration_rules(self, value: str, fragment: str) -> None:
        """Characters a profile directory cannot carry are refused."""
        _resolved, errors = resolve_command_names(_args(value), {})
        assert any(fragment in err for err in errors)

    def test_configuration_name_with_a_space_is_refused(self) -> None:
        """The configuration's list follows the same rules and names its source."""
        _resolved, errors = resolve_command_names(_args(), {'command-names': ['has space']})
        assert errors == ['Invalid command name "has space" in command-names: names cannot contain spaces']

    def test_configuration_empty_name_is_refused(self) -> None:
        """An empty entry in the configuration's list is refused."""
        _resolved, errors = resolve_command_names(_args(), {'command-names': ['ok', '  ']})
        assert errors == ['Invalid command name in command-names: names cannot be empty']

    def test_configuration_value_of_the_wrong_type_is_refused(self) -> None:
        """A mapping is neither a name nor a list of names."""
        _resolved, errors = resolve_command_names(_args(), {'command-names': {'a': 1}})
        assert errors == ['Invalid command-names value: expected string or list, got dict']


class TestReservedNames:
    """Reserved words and profile directory entries never name a profile."""

    @pytest.mark.parametrize(
        'name',
        ['none', 'base', 'all', 'skills', 'agents', 'commands', 'rules', 'hooks', 'output-styles', 'prompts', 'projects'],
    )
    def test_every_reserved_name_is_refused_when_typed(self, name: str) -> None:
        """Each reserved name is refused from the flag."""
        _resolved, errors = resolve_command_names(_args(name), {})
        assert len(errors) == 1
        assert f'Command name "{name}" in --command-names is reserved' in errors[0]

    def test_reserved_names_are_matched_without_regard_to_case(self) -> None:
        """Case-insensitive file systems map Projects onto the base projects directory."""
        _resolved, errors = resolve_command_names(_args('Projects'), {})
        assert len(errors) == 1
        assert 'is reserved' in errors[0]

    def test_reserved_alias_is_refused_from_the_environment(self) -> None:
        """An alias is checked like the primary name, and the message names the variable."""
        args = _args(env={'CLAUDE_CODE_TOOLBOX_COMMAND_NAMES': 'mine,all'})
        _resolved, errors = resolve_command_names(args, {})
        assert len(errors) == 1
        assert 'Command name "all" in CLAUDE_CODE_TOOLBOX_COMMAND_NAMES is reserved' in errors[0]

    def test_reserved_name_is_refused_from_the_configuration(self) -> None:
        """The configuration's list is held to the same reserved set."""
        _resolved, errors = resolve_command_names(_args(), {'command-names': ['skills']})
        assert len(errors) == 1
        assert 'Command name "skills" in command-names is reserved' in errors[0]

    def test_names_that_merely_contain_a_reserved_word_are_accepted(self) -> None:
        """Only an exact match is reserved."""
        resolved, errors = resolve_command_names(_args('all-in-one,my-projects,baseline'), {})
        assert errors == []
        assert resolved.names == ['all-in-one', 'my-projects', 'baseline']


def _plan(names: list[str], origin: str | None, *, components: bool) -> InstallationPlan:
    """Build a minimal installation plan carrying command names."""
    selection = None
    if components:
        selection = ComponentSelection(
            is_active=True,
            available=['core', 'extra'],
            selected=['core'],
            replay='--select core --without extra',
        )
    return InstallationPlan(
        config_name='Profile',
        config_source='profile.yaml',
        config_source_type='local',
        config_version=None,
        command_names=names,
        command_names_origin=origin,
        component_selection=selection,
    )


def _summary(plan: InstallationPlan) -> str:
    """Render the installation summary into a string."""
    buffer = io.StringIO()
    setup_environment.display_installation_summary(plan, output=buffer)
    return buffer.getvalue()


class TestSummaryShowsTheOrigin:
    """The summary row names where the command names came from."""

    @pytest.mark.parametrize('origin', ['cli', 'env', 'yaml'])
    def test_command_names_row_carries_the_origin_marker(self, origin: str) -> None:
        """Each origin renders as its bracketed marker after the names."""
        out = _summary(_plan(['main', 'alias'], origin, components=False))
        assert f'Command names: main, alias [{origin}]' in out

    def test_base_install_has_no_command_names_row(self) -> None:
        """A run without command names prints no row."""
        out = _summary(_plan([], None, components=False))
        assert 'Command names:' not in out


class TestReplayLineCarriesTypedNames:
    """The replay line reproduces the profile a typed list selected."""

    @pytest.mark.parametrize('origin', ['cli', 'env'])
    def test_typed_or_environment_names_join_the_replay_line(self, origin: str) -> None:
        """Without --command-names a replay would install the configuration's profile instead."""
        out = _summary(_plan(['p2', 'p2-alias'], origin, components=True))
        assert 'Replay: --select core --without extra --command-names p2,p2-alias' in out

    def test_configuration_names_stay_off_the_replay_line(self) -> None:
        """Names the configuration declares come back from the configuration on replay."""
        out = _summary(_plan(['yaml-name'], 'yaml', components=True))
        assert 'Replay: --select core --without extra\n' in out.replace('\r\n', '\n')
        assert '--command-names' not in out


def _model_errors(config: dict[str, Any]) -> str:
    """Return the validation error text the model raises for a configuration."""
    from pydantic import ValidationError

    from scripts.models.environment_config import EnvironmentConfig

    with pytest.raises(ValidationError) as exc_info:
        EnvironmentConfig.model_validate(config)
    return str(exc_info.value)


class TestModelRefusesReservedNames:
    """The configuration model refuses the reserved names the runtime refuses."""

    @pytest.mark.parametrize('name', ['all', 'Projects', 'output-styles'])
    def test_reserved_name_fails_model_validation(self, name: str) -> None:
        """A reserved name fails at YAML parsing time, before any run."""
        text = _model_errors({'name': 'x', 'command-names': [name], 'command-defaults': {}})
        assert 'is reserved' in text
