"""E2E tests for author-controlled component selection.

Runs the real golden configs through validation, resolution, and in-place
filtering (direct function calls, no network access), verifying
artifact-level outcomes with the composable validators.
"""

from __future__ import annotations

import argparse
import copy
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import yaml

from scripts import setup_environment
from tests.e2e.validators import validate_selected_artifacts

GOLDEN_CONFIGS = ['golden_config.yaml', 'golden_config_no_command_names.yaml']


def _load_golden(filename: str) -> dict[str, Any]:
    """Load a golden config YAML by filename.

    Args:
        filename: Golden config filename inside tests/e2e/.

    Returns:
        The parsed config dict.
    """
    path = Path(__file__).parent / filename
    with path.open(encoding='utf-8') as f:
        return yaml.safe_load(f)


def _args(
    select: str | None = None,
    with_: str | None = None,
    without: str | None = None,
) -> argparse.Namespace:
    """Build a Namespace carrying the component selector flags."""
    return argparse.Namespace(
        yes=False,
        dry_run=False,
        skip_install=True,
        no_admin=True,
        env_vars=None,
        select=select,
        with_=with_,
        without=without,
        list_components=False,
    )


def _select_and_apply(
    config: dict[str, Any],
    args: argparse.Namespace,
) -> setup_environment.ComponentSelection:
    """Validate, resolve, and apply component selection on a config.

    Args:
        config: Config dict (mutated in place by the filter).
        args: Selector arguments.

    Returns:
        The resolved ComponentSelection.
    """
    errors = setup_environment.validate_components(config)
    assert not errors, '\n'.join(errors)
    components = [c for c in config.get('components') or [] if isinstance(c, dict)]
    selection = setup_environment.resolve_component_selection(components, args)
    setup_environment.apply_component_selection(config, selection)
    return selection


class TestGoldenConfigComponents:
    """Validate the golden components registries and their selection behavior."""

    @pytest.mark.parametrize('filename', GOLDEN_CONFIGS)
    def test_golden_components_validate(self, filename: str) -> None:
        """Every golden config passes runtime components validation cleanly."""
        with patch.object(setup_environment, 'warning') as mock_warning:
            errors = setup_environment.validate_components(_load_golden(filename))
        assert errors == [], '\n'.join(errors)
        assert not mock_warning.called, 'golden configs must not trip the asymmetry warning'

    @pytest.mark.parametrize('filename', GOLDEN_CONFIGS)
    def test_default_selection_is_noop(self, filename: str) -> None:
        """All golden components default to true, so filtering changes nothing."""
        config = _load_golden(filename)
        expected = copy.deepcopy(config)
        selection = _select_and_apply(config, _args())
        assert selection.selected == ['core', 'mcp-http', 'extras']
        assert config == expected

    @pytest.mark.parametrize('filename', GOLDEN_CONFIGS)
    def test_default_filtered_config_matches_selection(self, filename: str) -> None:
        """The filtered config satisfies the artifact-level selection contract."""
        config = _load_golden(filename)
        components = copy.deepcopy(config['components'])
        selection = _select_and_apply(config, _args())
        errors = validate_selected_artifacts(config, components, selection.selected)
        assert not errors, '\n'.join(errors)


class TestSelectionFiltering:
    """Selector-driven filtering against the full golden config."""

    def test_select_core_drops_optional_claims_keeps_mandatory(self) -> None:
        """--select core drops items claimed only by mcp-http/extras."""
        config = _load_golden('golden_config.yaml')
        components = copy.deepcopy(config['components'])
        selection = _select_and_apply(config, _args(select='core'))
        assert selection.selected == ['core']

        server_names = [s['name'] for s in config['mcp-servers']]
        assert 'e2e-http-server' not in server_names
        assert 'e2e-http-profile-server' not in server_names
        assert 'e2e-sse-server' not in server_names
        # Unclaimed servers are mandatory and survive
        assert 'e2e-stdio-server' in server_names
        assert 'e2e-npx-server' in server_names
        assert 'e2e-combined-scope-server' in server_names

        assert config['files-to-download'] == []
        assert config['skills'] == []
        assert "echo 'common-dependency-installed'" not in config['dependencies']['common']
        # OS-specific dependencies are unclaimed and survive
        assert config['dependencies']['windows'] == ["echo 'windows-dependency-installed'"]

        # core's own claims survive
        assert config['agents'] == ['agents/e2e-test-agent.md']
        assert 'hooks/e2e_test_hook.py' in config['hooks']['files']
        # Unclaimed JS hooks survive
        assert 'hooks/e2e_test_hook.js' in config['hooks']['files']

        # Infrastructure keys are untouched
        assert config['command-names'] == ['e2e-test-cmd', 'e2e-test-alias']
        assert 'user-settings' in config

        errors = validate_selected_artifacts(config, components, selection.selected)
        assert not errors, '\n'.join(errors)

    def test_select_none_drops_every_claimed_item(self) -> None:
        """--select none keeps only unclaimed (mandatory) items."""
        config = _load_golden('golden_config.yaml')
        components = copy.deepcopy(config['components'])
        selection = _select_and_apply(config, _args(select='none'))
        assert selection.selected == []
        assert selection.replay == '--select none'

        assert config['agents'] == []
        assert config['rules'] == []
        assert config['slash-commands'] == []
        assert 'hooks/e2e_test_hook.py' not in config['hooks']['files']
        assert 'hooks/e2e_test_hook.js' in config['hooks']['files']
        claimed_ids = {'e2e-post-edit', 'e2e-notify'}
        surviving_ids = {e.get('id') for e in config['hooks']['events'] if e.get('id')}
        assert not (claimed_ids & surviving_ids)

        errors = validate_selected_artifacts(config, components, selection.selected)
        assert not errors, '\n'.join(errors)

    def test_requires_auto_includes_core_with_cause(self) -> None:
        """--select mcp-http pulls core in through the hard requires edge."""
        config = _load_golden('golden_config.yaml')
        selection = _select_and_apply(config, _args(select='mcp-http'))
        assert selection.selected == ['core', 'mcp-http']
        assert selection.auto_included == {'core': "required by 'mcp-http'"}

    def test_without_vs_hard_requires_warns_and_keeps(self) -> None:
        """--without core loses to the hard requires edge, with a warning."""
        config = _load_golden('golden_config.yaml')
        with patch.object(setup_environment, 'warning') as mock_warning:
            selection = _select_and_apply(config, _args(select='mcp-http', without='core'))
        assert 'core' in selection.selected
        warning_texts = [call.args[0] for call in mock_warning.call_args_list]
        assert any("--without 'core' overridden" in text for text in warning_texts)

    def test_bundles_seed_extras_pull_mcp_http(self) -> None:
        """--select extras softly bundles mcp-http, which hard-requires core."""
        config = _load_golden('golden_config.yaml')
        selection = _select_and_apply(config, _args(select='extras'))
        assert selection.selected == ['core', 'mcp-http', 'extras']

    def test_non_interactive_run_uses_defaults_without_prompting(self) -> None:
        """Without a picker the defaults apply and no prompt is attempted."""
        config = _load_golden('golden_config.yaml')
        with patch.object(setup_environment, 'prompt_component_selection') as mock_prompt:
            selection = _select_and_apply(config, _args())
        assert not mock_prompt.called
        assert selection.selected == ['core', 'mcp-http', 'extras']


class TestListComponentsRegistry:
    """--list-components output shape against the golden registry."""

    def test_registry_output_shape(self, capsys: pytest.CaptureFixture[str]) -> None:
        """The registry shows names, labels, markers, edges, and counts."""
        config = _load_golden('golden_config.yaml')
        setup_environment.display_component_registry(config['components'])
        output = capsys.readouterr().out
        assert 'core -- Core tooling [default]' in output
        assert 'mcp-http -- HTTP MCP servers [default]' in output
        assert 'extras -- Optional extras [default]' in output
        assert 'requires: core' in output
        assert 'bundles: mcp-http' in output
        assert 'includes: 3 mcp-servers' in output


class TestPickerIntegration:
    """Picker wiring against the golden registry."""

    def test_picker_unchecking_extras_drops_its_items(self) -> None:
        """A picker deselecting extras drops the extras-only items."""
        config = _load_golden('golden_config.yaml')
        components = copy.deepcopy(config['components'])
        errors = setup_environment.validate_components(config)
        assert not errors
        picker = MagicMock(return_value=['core', 'mcp-http'])
        selection = setup_environment.resolve_component_selection(
            list(config['components']), _args(), picker=picker,
        )
        setup_environment.apply_component_selection(config, selection)
        picker.assert_called_once_with(['core', 'mcp-http', 'extras'])
        assert selection.selected == ['core', 'mcp-http']
        assert config['files-to-download'] == []
        assert config['skills'] == []
        validation_errors = validate_selected_artifacts(config, components, selection.selected)
        assert not validation_errors, '\n'.join(validation_errors)
