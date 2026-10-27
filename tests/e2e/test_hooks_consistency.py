"""E2E tests for setup-time hooks-files consistency validation.

The runtime twin validate_hooks_files_consistency() runs at the main() choke
point on the RESOLVED configuration, closing the model's inherit blind spot:
a composition whose hook events or status-line reference a missing hook file
fails at setup time instead of at hook execution. These tests exercise the
real golden configs, real fixture-file compositions resolved through
resolve_config_inheritance(), and the fail-fast exit path of main(),
including the program-command rule: a command naming no hooks.files script
is accepted only in exec form (args) and without a config.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from scripts import setup_environment
from scripts.models.environment_config import EnvironmentConfig
from tests.e2e.hook_sync_recorder import HookSyncRecorder
from tests.e2e.profile_support import run_main
from tests.e2e.profile_support import write_config

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

    def test_main_exits_when_deselection_strands_an_exec_form_reference(
        self,
        e2e_isolated_home: dict[str, Path],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """An exec-form event naming a dropped script stops setup like a shell-form one.

        The dropped script's basename is no longer in the filtered
        hooks.files, but the recheck knows the configuration declared it, so
        the surviving event is a dangling reference rather than a program on
        PATH, and no settings file is written.
        """
        config = self._asymmetric_config()
        config['hooks']['events'][0]['args'] = ['--fix']
        with patch('scripts.setup_environment.load_config_from_source',
                   return_value=(config, 'test.yaml')), \
             patch('sys.argv', ['setup_environment.py', 'test', '--yes', '--skip-install']), \
             pytest.raises(SystemExit) as exc_info:
            setup_environment.main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert 'hooks.events command "my_hook.py" not found in hooks.files. Available files: none' in captured.err
        assert 'leave hook references dangling' in captured.err
        assert 'Step 1' not in captured.out
        assert not (e2e_isolated_home['claude_dir'] / 'settings.json').exists()

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


PROGRAM_HOOKS_COMMAND = 'program-hooks'

# Hook events naming programs on PATH: a tool whose hook subcommands run in
# the background, and a program that takes no arguments
PROGRAM_EVENTS: list[dict[str, Any]] = [
    {
        'event': 'Stop', 'type': 'command', 'command': 'my-tool', 'args': ['hook', 'stop'],
        'async-rewake': True, 'timeout': 86400,
    },
    {
        'event': 'UserPromptSubmit', 'type': 'command', 'command': 'my-tool', 'args': ['hook', 'prompt-submit'],
        'async': True,
    },
    {'event': 'SessionStart', 'matcher': 'startup', 'type': 'command', 'command': 'my-tool-ready', 'args': []},
]

# The hooks block those events produce, exactly
PROGRAM_HOOKS_JSON: dict[str, Any] = {
    'Stop': [{
        'matcher': '',
        'hooks': [{
            'type': 'command', 'command': 'my-tool', 'args': ['hook', 'stop'], 'asyncRewake': True, 'timeout': 86400,
        }],
    }],
    'UserPromptSubmit': [{
        'matcher': '',
        'hooks': [{'type': 'command', 'command': 'my-tool', 'args': ['hook', 'prompt-submit'], 'async': True}],
    }],
    'SessionStart': [{
        'matcher': 'startup',
        'hooks': [{'type': 'command', 'command': 'my-tool-ready', 'args': []}],
    }],
}


class TestMainProgramCommands:
    """main() refuses a program command in shell form or beside a config, and installs one in exec form."""

    @staticmethod
    def _refused_before_install(
        tmp_path: Path, claude_dir: Path, config: dict[str, Any], capfd: pytest.CaptureFixture[str],
    ) -> str:
        """Run main() on a configuration that must be refused, and return what it printed.

        Asserts exit code 1, no Claude Code installation attempt (the run is
        not given --skip-install), and nothing written into ~/.claude.

        Args:
            tmp_path: Directory the configuration file is written to.
            claude_dir: The isolated ~/.claude, empty before the run.
            config: The configuration to run.
            capfd: Captures what the run printed.

        Returns:
            Everything the run printed.
        """
        cfg = write_config(tmp_path, 'program.yaml', config)
        with patch.object(setup_environment, 'install_claude') as install_claude:
            code = run_main([str(cfg), '--no-admin', '--yes'])
        captured = capfd.readouterr()
        output = captured.out + captured.err
        assert code == 1, output
        install_claude.assert_not_called()
        assert sorted(path.name for path in claude_dir.iterdir()) == [], output
        return output

    def test_shell_form_program_is_refused_naming_args(
        self, e2e_isolated_home: dict[str, Path], tmp_path: Path, capfd: pytest.CaptureFixture[str],
    ) -> None:
        """A command naming no hooks.files script without args stops the run, naming args as the remedy."""
        config = {
            'name': 'Shell-Form Program',
            'hooks': {'events': [{'event': 'Stop', 'type': 'command', 'command': 'my-tool'}]},
        }

        output = self._refused_before_install(tmp_path, e2e_isolated_home['claude_dir'], config, capfd)

        assert 'hooks.events command "my-tool" not found in hooks.files. Available files: none.' in output
        assert (
            'A command that is not a hooks.files script runs as a program in exec form: name the program '
            '(on PATH or by absolute path) in command and give its arguments in args, '
            'using args: [] when it takes none.'
        ) in output

    def test_program_with_config_is_refused(
        self, e2e_isolated_home: dict[str, Path], tmp_path: Path, capfd: pytest.CaptureFixture[str],
    ) -> None:
        """A config beside an exec-form program stops the run: only a hooks.files script receives it."""
        config = {
            'name': 'Program With Config',
            'hooks': {
                'events': [{
                    'event': 'Stop', 'type': 'command', 'command': 'my-tool', 'args': ['hook', 'stop'],
                    'config': 'tool.yaml',
                }],
            },
        }

        output = self._refused_before_install(tmp_path, e2e_isolated_home['claude_dir'], config, capfd)

        assert (
            'hooks.events config "tool.yaml" is set beside command "my-tool", which is a program, '
            'not a hooks.files script. config is passed only to a hooks.files script; '
            'a program takes its arguments in args.'
        ) in output

    @pytest.mark.parametrize('isolated', [True, False], ids=['isolated', 'base'])
    def test_exec_form_programs_install(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        hook_sync_recorder: HookSyncRecorder,
        capfd: pytest.CaptureFixture[str],
        isolated: bool,
    ) -> None:
        """Exec-form programs install, written verbatim with their args and keys, with no environment to prepare."""
        config: dict[str, Any] = {'name': 'Program Hooks', 'hooks': {'events': PROGRAM_EVENTS}}
        if isolated:
            config['command-names'] = [PROGRAM_HOOKS_COMMAND]
        cfg = write_config(tmp_path, 'program.yaml', config)

        code = run_main([str(cfg), '--skip-install', '--no-admin', '--yes'])

        captured = capfd.readouterr()
        output = captured.out + captured.err
        assert code == 0, output
        claude_dir = e2e_isolated_home['claude_dir']
        written = claude_dir / PROGRAM_HOOKS_COMMAND / 'config.json' if isolated else claude_dir / 'settings.json'
        assert json.loads(written.read_text(encoding='utf-8'))['hooks'] == PROGRAM_HOOKS_JSON
        assert 'No Python hooks to prepare environments for' in output
        assert hook_sync_recorder.records() == []
