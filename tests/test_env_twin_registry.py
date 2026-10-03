"""Tests for the environment-twin registry of setup_environment.py.

Every CLAUDE_CODE_TOOLBOX_* variable that stands in for a command-line
argument is listed once in ENV_TWINS. resolve_args() takes its fallbacks from
that table, and request_admin_elevation() forwards the same table into the
elevated process, which does not inherit the environment of the process that
asked for elevation.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Iterator
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from scripts import setup_environment

TOOLBOX_PREFIX = 'CLAUDE_CODE_TOOLBOX_'


class _RecordingEnviron:
    """A stand-in process environment that records every variable name read."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.read: set[str] = set()

    def get(self, key: str, default: str | None = None) -> str | None:
        self.read.add(key)
        return self.values.get(key, default)

    def __getitem__(self, key: str) -> str:
        self.read.add(key)
        return self.values[key]

    def __setitem__(self, key: str, value: str) -> None:
        self.values[key] = value

    def __contains__(self, key: object) -> bool:
        if isinstance(key, str):
            self.read.add(key)
        return key in self.values


def _empty_namespace() -> argparse.Namespace:
    """Build the namespace argparse produces when no argument is given."""
    return argparse.Namespace(
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
    )


def _toolbox_variables_resolve_args_reads() -> set[str]:
    """Run resolve_args() on an empty environment and return the toolbox variables it read."""
    recorder = _RecordingEnviron()
    with patch.object(os, 'environ', recorder):
        setup_environment.resolve_args(_empty_namespace())
    return {name for name in recorder.read if name.startswith(TOOLBOX_PREFIX)}


@pytest.fixture
def mock_shell_execute() -> Iterator[MagicMock]:
    """Replace the UAC relaunch primitive so no prompt opens and the call is recorded."""
    with (
        patch('platform.system', return_value='Windows'),
        patch('ctypes.windll', create=True) as mock_windll,
        patch('time.sleep'),
    ):
        mock_windll.shell32.ShellExecuteW.return_value = 33
        yield mock_windll.shell32.ShellExecuteW


def _relaunch_arguments(shell_execute: MagicMock, script_args: list[str]) -> list[str]:
    """Run request_admin_elevation() and return the argument list it relaunches with."""
    captured: list[list[str]] = []
    original = setup_environment.subprocess.list2cmdline

    def _capture(args: list[str]) -> str:
        captured.append(list(args))
        return original(args)

    with (
        patch.object(setup_environment.subprocess, 'list2cmdline', side_effect=_capture),
        pytest.raises(SystemExit) as exc_info,
    ):
        setup_environment.request_admin_elevation(script_args)
    assert exc_info.value.code == 0
    shell_execute.assert_called_once()
    assert len(captured) == 1
    return captured[0]


class TestRegistryShape:
    """The registry names each variable and each argument once."""

    def test_variables_are_unique_toolbox_names(self) -> None:
        """No variable appears twice and every one carries the toolbox prefix."""
        variables = [twin.variable for twin in setup_environment.ENV_TWINS]
        assert len(variables) == len(set(variables))
        assert all(name.startswith(TOOLBOX_PREFIX) for name in variables)

    def test_destinations_are_unique(self) -> None:
        """No argument is filled by two variables."""
        destinations = [twin.dest for twin in setup_environment.ENV_TWINS]
        assert len(destinations) == len(set(destinations))

    def test_kinds_are_switch_or_value(self) -> None:
        """Every entry declares one of the two resolution kinds."""
        assert {twin.kind for twin in setup_environment.ENV_TWINS} <= {'switch', 'value'}

    def test_every_twin_is_registered(self) -> None:
        """Each variable that stands in for an argument maps to that argument."""
        registered = {twin.variable: twin.dest for twin in setup_environment.ENV_TWINS}
        assert registered == {
            'CLAUDE_CODE_TOOLBOX_ENV_CONFIG': 'config',
            'CLAUDE_CODE_TOOLBOX_CONFIRM_INSTALL': 'yes',
            'CLAUDE_CODE_TOOLBOX_DRY_RUN': 'dry_run',
            'CLAUDE_CODE_TOOLBOX_SKIP_INSTALL': 'skip_install',
            'CLAUDE_CODE_TOOLBOX_NO_ADMIN': 'no_admin',
            'CLAUDE_CODE_TOOLBOX_ENV_AUTH': 'auth',
            'CLAUDE_CODE_TOOLBOX_SELECT': 'select',
            'CLAUDE_CODE_TOOLBOX_WITH': 'with_',
            'CLAUDE_CODE_TOOLBOX_WITHOUT': 'without',
        }


class TestResolveArgsReadsOnlyRegisteredTwins:
    """resolve_args() reads exactly the toolbox variables the registry lists."""

    def test_every_toolbox_variable_read_is_registered(self) -> None:
        """A variable read outside the registry would miss the UAC relaunch."""
        registered = {twin.variable for twin in setup_environment.ENV_TWINS}
        assert _toolbox_variables_resolve_args_reads() == registered

    def test_each_value_twin_fills_its_argument(self) -> None:
        """A non-empty value fills an absent argument and is marked as coming from the environment."""
        values = {
            twin.variable: f'value-of-{twin.dest}'
            for twin in setup_environment.ENV_TWINS
            if twin.kind == 'value'
        }
        with patch.dict(os.environ, values):
            args = setup_environment.resolve_args(_empty_namespace())
        for twin in setup_environment.ENV_TWINS:
            if twin.kind == 'value':
                assert getattr(args, twin.dest) == f'value-of-{twin.dest}'
                assert args.origins[twin.dest] == 'env'

    def test_each_switch_twin_turns_on_only_with_exact_one(self) -> None:
        """A switch twin accepts the exact value 1 and nothing else."""
        switches = [twin for twin in setup_environment.ENV_TWINS if twin.kind == 'switch']
        with patch.dict(os.environ, {twin.variable: '1' for twin in switches}):
            args = setup_environment.resolve_args(_empty_namespace())
        assert all(getattr(args, twin.dest) is True for twin in switches)

        with patch.dict(os.environ, {twin.variable: 'true' for twin in switches}):
            args = setup_environment.resolve_args(_empty_namespace())
        assert all(getattr(args, twin.dest) is False for twin in switches)

    def test_typed_value_wins_and_is_marked_cli(self) -> None:
        """A typed argument beats its variable and is marked as typed."""
        with patch.dict(os.environ, {'CLAUDE_CODE_TOOLBOX_SELECT': 'from-env'}):
            namespace = _empty_namespace()
            namespace.select = 'typed'
            args = setup_environment.resolve_args(namespace)
        assert args.select == 'typed'
        assert args.origins['select'] == 'cli'

    def test_empty_value_export_counts_as_absent(self) -> None:
        """An empty export, a common CI template default, leaves the argument unset."""
        with patch.dict(os.environ, {'CLAUDE_CODE_TOOLBOX_ENV_CONFIG': ''}):
            args = setup_environment.resolve_args(_empty_namespace())
        assert args.config is None
        assert 'config' not in args.origins

    def test_config_twin_supplies_the_positional_configuration(self) -> None:
        """CLAUDE_CODE_TOOLBOX_ENV_CONFIG stands in for the positional configuration."""
        with patch.dict(os.environ, {'CLAUDE_CODE_TOOLBOX_ENV_CONFIG': 'python.yaml'}):
            args = setup_environment.resolve_args(_empty_namespace())
        assert args.config == 'python.yaml'

    def test_positional_configuration_wins_over_the_config_twin(self) -> None:
        """A configuration given on the command line beats the variable."""
        with patch.dict(os.environ, {'CLAUDE_CODE_TOOLBOX_ENV_CONFIG': 'from-env.yaml'}):
            namespace = _empty_namespace()
            namespace.config = 'typed.yaml'
            args = setup_environment.resolve_args(namespace)
        assert args.config == 'typed.yaml'


class TestUacRelaunchForwardsEveryTwin:
    """The elevated process receives every registered twin that is set."""

    def test_every_registered_twin_is_forwarded(self, mock_shell_execute: MagicMock) -> None:
        """Each set twin travels as an --env-VAR=value argument."""
        values = {twin.variable: f'v-{index}' for index, twin in enumerate(setup_environment.ENV_TWINS)}
        with patch.dict(os.environ, values):
            relaunch = _relaunch_arguments(mock_shell_execute, ['--yes'])
        for variable, value in values.items():
            assert f'--env-{variable}={value}' in relaunch

    def test_every_variable_resolve_args_reads_is_forwarded(self, mock_shell_execute: MagicMock) -> None:
        """No toolbox variable the run reads for its arguments is lost on elevation."""
        toolbox_reads = _toolbox_variables_resolve_args_reads()
        with patch.dict(os.environ, dict.fromkeys(toolbox_reads, 'set')):
            relaunch = _relaunch_arguments(mock_shell_execute, [])
        forwarded = {
            arg.split('=', 1)[0].removeprefix('--env-')
            for arg in relaunch
            if arg.startswith('--env-')
        }
        assert toolbox_reads <= forwarded

    def test_credentials_and_installer_pin_are_forwarded(self, mock_shell_execute: MagicMock) -> None:
        """Repository tokens and the installer's version pin reach the elevated process."""
        values = dict.fromkeys(setup_environment.UAC_FORWARDED_ENV_VARS, 'secret')
        with patch.dict(os.environ, values):
            relaunch = _relaunch_arguments(mock_shell_execute, [])
        for variable in ('GITHUB_TOKEN', 'GITLAB_TOKEN', 'REPO_TOKEN', 'CLAUDE_CODE_TOOLBOX_VERSION'):
            assert f'--env-{variable}=secret' in relaunch

    def test_unset_twins_are_not_forwarded(self, mock_shell_execute: MagicMock) -> None:
        """A twin that is not set adds nothing to the relaunch."""
        with patch.dict(os.environ, {}, clear=False):
            for twin in setup_environment.ENV_TWINS:
                os.environ.pop(twin.variable, None)
            relaunch = _relaunch_arguments(mock_shell_execute, [])
        assert not any(arg.startswith(f'--env-{TOOLBOX_PREFIX}') for arg in relaunch)

    def test_env_flag_values_are_forwarded_verbatim(self, mock_shell_execute: MagicMock) -> None:
        """--env pairs stay in the forwarded arguments, so the elevated run applies them again."""
        script_args = ['golden.yaml', '--env', 'GITHUB_TOKEN=ghp_x', '--env', 'CUSTOM=a=b', '--yes']
        relaunch = _relaunch_arguments(mock_shell_execute, script_args)
        assert relaunch[-len(script_args):] == script_args
        assert '--elevated-via-uac' in relaunch

    def test_elevated_process_restores_the_forwarded_twins(self, mock_shell_execute: MagicMock) -> None:
        """The elevated process puts every forwarded twin back into its environment."""
        values = {twin.variable: f'v-{index}' for index, twin in enumerate(setup_environment.ENV_TWINS)}
        with patch.dict(os.environ, values):
            relaunch = _relaunch_arguments(mock_shell_execute, ['golden.yaml', '--yes'])
        # Everything before the first forwarded variable launches the program
        first_forwarded = next(index for index, arg in enumerate(relaunch) if arg.startswith('--env-'))

        with patch.dict(os.environ, {}, clear=False):
            for variable in values:
                os.environ.pop(variable, None)
            with patch('sys.argv', ['setup_environment.py', *relaunch[first_forwarded:]]):
                remaining, elevated = setup_environment.restore_env_vars_from_args()
            restored = {variable: os.environ.get(variable) for variable in values}
        assert elevated is True
        assert remaining == ['setup_environment.py', 'golden.yaml', '--yes']
        assert restored == values
