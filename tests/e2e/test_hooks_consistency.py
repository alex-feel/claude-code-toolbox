"""E2E tests for setup-time hooks-files consistency validation.

The runtime twin validate_hooks_files_consistency() runs at the main() choke
point on the RESOLVED configuration, closing the model's inherit blind spot:
a composition whose hook events or status-line reference a missing hook file
fails at setup time instead of at hook execution. These tests exercise the
real golden configs, real fixture-file compositions resolved through
resolve_config_inheritance(), and the fail-fast exit path of main().
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from scripts import setup_environment
from scripts.models.environment_config import EnvironmentConfig

GOLDEN_CONFIGS = ['golden_config.yaml', 'golden_config_no_command_names.yaml']


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file and return its content."""
    with path.open(encoding='utf-8') as f:
        return yaml.safe_load(f)


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the E2E fixtures directory."""
    return Path(__file__).parent / 'fixtures'


class TestGoldenConfigHooksConsistency:
    """The golden configs pass the runtime hooks-consistency validation."""

    @pytest.mark.parametrize('filename', GOLDEN_CONFIGS)
    def test_golden_hooks_consistent(self, filename: str) -> None:
        """Every golden config's hooks references resolve within hooks.files."""
        config = _load_yaml(Path(__file__).parent / filename)
        errors = setup_environment.validate_hooks_files_consistency(config)
        assert errors == [], '\n'.join(errors)


class TestResolvedCompositionConsistency:
    """Consistency verdicts over real inherit compositions resolved from disk."""

    def test_valid_composition_passes(self, fixtures_dir: Path) -> None:
        """A leaf event referencing a parent-contributed file resolves cleanly."""
        path = fixtures_dir / 'hooks_consistency_valid_leaf.yaml'
        config = _load_yaml(path)

        # The model accepts the leaf standalone: inherit is declared, so the
        # consistency checks are skipped as undecidable
        EnvironmentConfig.model_validate(config)

        resolved, _ = setup_environment.resolve_config_inheritance(config, str(path))
        errors = setup_environment.validate_hooks_files_consistency(resolved)
        assert errors == [], '\n'.join(errors)

    def test_broken_composition_fails_at_setup(self, fixtures_dir: Path) -> None:
        """A dangling hook reference in a composition is caught on the resolved config."""
        path = fixtures_dir / 'hooks_consistency_broken_leaf.yaml'
        config = _load_yaml(path)

        # The model cannot catch this standalone: inherit is declared, so the
        # consistency checks are skipped -- only the runtime twin sees the
        # resolved composition
        EnvironmentConfig.model_validate(config)

        resolved, _ = setup_environment.resolve_config_inheritance(config, str(path))
        errors = setup_environment.validate_hooks_files_consistency(resolved)
        assert any(
            'command "e2e_missing_hook.py" not found in hooks.files' in e for e in errors
        ), '\n'.join(errors)

    def test_composition_merges_parent_hooks_files(self, fixtures_dir: Path) -> None:
        """The resolved composition carries the parent's files for the leaf's events."""
        path = fixtures_dir / 'hooks_consistency_valid_leaf.yaml'
        config = _load_yaml(path)
        resolved, _ = setup_environment.resolve_config_inheritance(config, str(path))

        basenames = {
            setup_environment._hook_file_basename(f)
            for f in resolved['hooks']['files']
        }
        assert basenames == {'e2e_test_hook.py', 'e2e-hook-config.yaml'}
        assert len(resolved['hooks']['events']) == 2


class TestPostSelectionRecheck:
    """Deselection-induced dangling hook references fail at setup."""

    @staticmethod
    def _asymmetric_config() -> dict[str, Any]:
        """Config where a component claims a hook file but not its id-less event."""
        return {
            'name': 'Asymmetric Claims',
            'agents': ['agents/keep.md'],
            'hooks': {
                'files': ['hooks/my_hook.py'],
                'events': [
                    {'event': 'PostToolUse', 'matcher': 'Edit',
                     'type': 'command', 'command': 'my_hook.py'},
                ],
            },
            'components': [
                {'name': 'core', 'includes': {'agents': ['agents/keep.md']}},
                {'name': 'extra', 'default': False,
                 'includes': {'hooks': ['hooks/my_hook.py']}},
            ],
        }

    def test_main_exits_when_deselection_strands_a_reference(
        self,
        e2e_isolated_home: dict[str, Path],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Deselecting the file-claiming component stops setup at the recheck.

        The pre-filter validation passes (the config is self-consistent),
        but the default selection drops the claimed hooks.files entry while
        the id-less event survives as mandatory, so the post-selection
        recheck reports the dangling command reference.
        """
        del e2e_isolated_home
        with patch('scripts.setup_environment.load_config_from_source',
                   return_value=(self._asymmetric_config(), 'test.yaml')), \
             patch('sys.argv', ['setup_environment.py', 'test', '--yes', '--skip-install']), \
             pytest.raises(SystemExit) as exc_info:
            setup_environment.main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert 'command "my_hook.py" not found in hooks.files' in captured.err
        assert 'leave hook references dangling' in captured.err

    def test_stranded_file_without_dangling_reference_is_tolerated(self) -> None:
        """Deselecting an event-claiming component leaves an unused file, not an error."""
        config: dict[str, Any] = {
            'name': 'Event Claimed Only',
            'hooks': {
                'files': ['hooks/my_hook.py'],
                'events': [
                    {'event': 'PostToolUse', 'matcher': 'Edit', 'type': 'command',
                     'command': 'my_hook.py', 'id': 'claimed-event'},
                ],
            },
            'components': [
                {'name': 'extra', 'default': False,
                 'includes': {'hooks': ['claimed-event']}},
            ],
        }
        assert setup_environment.validate_components(config) == []
        components = [c for c in config['components'] if isinstance(c, dict)]
        selection = setup_environment.resolve_component_selection(
            components,
            argparse.Namespace(
                yes=True, dry_run=False, select=None, with_=None, without=None,
            ),
        )
        setup_environment.apply_component_selection(config, selection)
        assert config['hooks']['events'] == []
        assert config['hooks']['files'] == ['hooks/my_hook.py']
        errors = setup_environment.validate_hooks_files_consistency(
            config, require_all_files_used=False,
        )
        assert errors == []


class TestMainFailsFastOnBrokenHooks:
    """main() exits 1 at the choke point before any installation work."""

    def test_main_exits_with_all_errors_listed(
        self,
        e2e_isolated_home: dict[str, Path],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A broken resolved config stops setup with every violation reported."""
        del e2e_isolated_home
        broken_config = {
            'name': 'Broken Hooks',
            'hooks': {
                'files': ['hooks/a.py', 'hooks/unused.py'],
                'events': [
                    {'event': 'PostToolUse', 'matcher': 'Edit',
                     'type': 'command', 'command': 'missing.py'},
                ],
            },
            'status-line': {'file': 'missing_sl.py'},
        }

        with patch('scripts.setup_environment.load_config_from_source',
                   return_value=(broken_config, 'test.yaml')), \
             patch('sys.argv', ['setup_environment.py', 'test', '--yes', '--skip-install']), \
             pytest.raises(SystemExit) as exc_info:
            setup_environment.main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert 'command "missing.py" not found in hooks.files' in captured.err
        assert 'status-line.file "missing_sl.py" not found in hooks.files' in captured.err
        assert "unused files: ['a.py', 'unused.py']" in captured.err

    def test_main_exits_when_status_line_lacks_hooks(
        self,
        e2e_isolated_home: dict[str, Path],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A status-line without hooks.files stops setup at the choke point."""
        del e2e_isolated_home
        broken_config = {
            'name': 'Status Line Without Hooks',
            'status-line': {'file': 'sl.py'},
        }

        with patch('scripts.setup_environment.load_config_from_source',
                   return_value=(broken_config, 'test.yaml')), \
             patch('sys.argv', ['setup_environment.py', 'test', '--yes', '--skip-install']), \
             pytest.raises(SystemExit) as exc_info:
            setup_environment.main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert 'requires hooks.files to be configured' in captured.err
