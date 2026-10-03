"""Tests for how the installation summaries report command-defaults.

command-defaults reaches Claude Code only through the launcher of an isolated
profile, so the summaries of a run without command names state that it
applies only to isolated installs, and the summaries of an isolated run
describe how the launcher applies the system prompt.
"""

from __future__ import annotations

import io
from typing import Any
from unittest.mock import MagicMock

import pytest

from scripts import setup_environment

NOTE = setup_environment.COMMAND_DEFAULTS_ISOLATED_ONLY_NOTE


def _plan_from(config: dict[str, Any]) -> setup_environment.InstallationPlan:
    """Collect the installation plan of a configuration.

    Args:
        config: The resolved configuration.

    Returns:
        The plan collect_installation_plan() builds for it.
    """
    args = MagicMock()
    args.skip_install = True
    return setup_environment.collect_installation_plan(
        config=config,
        config_source='probe.yaml',
        config_name='probe',
        config_version=None,
        inheritance_chain=[setup_environment.InheritanceChainEntry('probe.yaml', 'local', 'probe')],
        args=args,
    )


def _summary(plan: setup_environment.InstallationPlan) -> str:
    """Render the installation summary of a plan.

    Args:
        plan: The plan to render.

    Returns:
        The rendered summary.
    """
    buffer = io.StringIO()
    setup_environment.display_installation_summary(plan, output=buffer)
    return buffer.getvalue()


class TestCollectedCommandDefaults:
    """collect_installation_plan() records command-defaults and whether a launcher applies it."""

    def test_base_run_with_command_defaults_is_isolated_only(self) -> None:
        """A configuration without command names declaring command-defaults is flagged."""
        plan = _plan_from({
            'name': 'probe',
            'command-defaults': {'system-prompt': 'prompts/p.md', 'mode': 'append'},
        })
        assert plan.command_defaults == {'system-prompt': 'prompts/p.md', 'mode': 'append'}
        assert plan.command_defaults_isolated_only is True

    def test_isolated_run_with_command_defaults_is_not_flagged(self) -> None:
        """Command names give the run a launcher that applies command-defaults."""
        plan = _plan_from({
            'name': 'probe',
            'command-names': ['probe-cmd'],
            'command-defaults': {'system-prompt': 'prompts/p.md'},
        })
        assert plan.command_defaults_isolated_only is False

    @pytest.mark.parametrize(
        'config',
        [
            pytest.param({'name': 'probe'}, id='absent'),
            pytest.param({'name': 'probe', 'command-defaults': {}}, id='empty'),
        ],
    )
    def test_base_run_without_command_defaults_is_not_flagged(self, config: dict[str, Any]) -> None:
        """No declared command-defaults means nothing to note."""
        plan = _plan_from(config)
        assert plan.command_defaults == {}
        assert plan.command_defaults_isolated_only is False


class TestSummaryNote:
    """display_installation_summary() states where command-defaults applies."""

    def test_note_for_base_run_with_system_prompt(self) -> None:
        """The note follows the system prompt row of a base run."""
        output = _summary(_plan_from({
            'name': 'probe',
            'command-defaults': {'system-prompt': 'prompts/p.md', 'mode': 'append'},
        }))
        settings = output.split('Settings:', 1)[1]
        assert 'System prompt: append' in settings
        assert NOTE in settings
        assert settings.index('System prompt: append') < settings.index(NOTE)

    def test_note_for_base_run_with_mode_only(self) -> None:
        """A non-empty command-defaults without a system prompt is noted too."""
        output = _summary(_plan_from({'name': 'probe', 'command-defaults': {'mode': 'append'}}))
        assert NOTE in output.split('Settings:', 1)[1]
        assert 'System prompt:' not in output

    def test_no_note_for_isolated_run(self) -> None:
        """An isolated run shows the system prompt row and no note."""
        output = _summary(_plan_from({
            'name': 'probe',
            'command-names': ['probe-cmd'],
            'command-defaults': {'system-prompt': 'prompts/p.md'},
        }))
        assert 'System prompt: replace' in output
        assert NOTE not in output

    @pytest.mark.parametrize(
        'config',
        [
            pytest.param({'name': 'probe'}, id='absent'),
            pytest.param({'name': 'probe', 'command-defaults': {}}, id='empty'),
        ],
    )
    def test_no_note_without_command_defaults(self, config: dict[str, Any]) -> None:
        """A base run that declares no command-defaults prints no note."""
        assert NOTE not in _summary(_plan_from(config))


class TestCompletionSummaryLine:
    """system_prompt_completion_line() renders the closing summary's system prompt row."""

    @pytest.mark.parametrize(
        ('mode', 'expected'),
        [
            pytest.param('append', 'System prompt: appending to default', id='append'),
            pytest.param('replace', 'System prompt: replacing default', id='replace'),
        ],
    )
    def test_isolated_run_names_the_mode(self, mode: str, expected: str) -> None:
        """An isolated run's launcher applies the prompt in the configured mode."""
        assert setup_environment.system_prompt_completion_line(mode, isolated=True) == expected

    @pytest.mark.parametrize('mode', ['append', 'replace'])
    def test_base_run_states_the_prompt_is_not_applied(self, mode: str) -> None:
        """A base run has no launcher, so the row says the prompt is not applied."""
        assert setup_environment.system_prompt_completion_line(mode, isolated=False) == (
            f'System prompt: not applied ({NOTE})'
        )
