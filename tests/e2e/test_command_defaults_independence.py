"""E2E tests for command-defaults and version installed independently of command-names.

command-defaults reaches Claude Code only through a profile launcher. A
configuration that declares it without command names still installs, as the
base profile, and says before consent, in --dry-run and in the closing summary
that it applies only to isolated installs; installed as an isolated profile,
the same configuration's launcher hands its system prompt to Claude Code. A
configuration with command names and no command-defaults installs a launcher
that passes no system prompt, and a configuration with version and no command
names records the version in the base profile manifest. The configuration
model accepts every one of these files.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from scripts import setup_environment
from scripts.models.environment_config import EnvironmentConfig
from tests.e2e.launcher_support import LaunchRecord
from tests.e2e.launcher_support import find_bash
from tests.e2e.launcher_support import launch
from tests.e2e.launcher_support import same_path
from tests.e2e.validators import validate_manifest

FIXTURES = Path(__file__).parent / 'fixtures'
DEFAULTS_BASE = FIXTURES / 'command_defaults_base.yaml'
DEFAULTS_ISOLATED_LEAF = FIXTURES / 'command_defaults_isolated_leaf.yaml'
NAMES_WITHOUT_DEFAULTS = FIXTURES / 'command_names_without_defaults.yaml'
VERSION_BASE = FIXTURES / 'version_base.yaml'
PROMPT_FILE = 'e2e-test-prompt.md'
PROMPT_FLAGS = {'--system-prompt', '--system-prompt-file', '--append-system-prompt', '--append-system-prompt-file'}


def _load(path: Path) -> dict[str, Any]:
    """Load a fixture configuration.

    Args:
        path: The YAML file.

    Returns:
        The parsed configuration.
    """
    with path.open(encoding='utf-8') as f:
        loaded: dict[str, Any] = yaml.safe_load(f)
    return loaded


def _run_setup(config_path: Path, *flags: str) -> None:
    """Run setup_environment.main() on a configuration file.

    The configuration, its parents and its system prompt are read from disk
    the way a user's local file is; only the writers that would reach beyond
    the isolated home (the Windows registry and the OS environment) are
    stubbed, and claude resolves to a path so the --skip-install check passes
    without running any claude command.

    Args:
        config_path: The configuration file to install.
        *flags: Command-line flags after the configuration.
    """
    find_other_command = setup_environment.find_command

    def find_command(name: str) -> str | None:
        return '/usr/bin/claude' if name == 'claude' else find_other_command(name)

    with (
        patch.object(setup_environment, 'cleanup_temp_paths_from_registry', return_value=(0, [])),
        patch.object(setup_environment, 'find_command', side_effect=find_command),
        patch.object(setup_environment, 'set_all_os_env_variables', return_value=True),
        patch.object(setup_environment, 'is_admin', return_value=True),
        patch('sys.argv', ['setup_environment.py', str(config_path), '--skip-install', *flags]),
    ):
        setup_environment.main()


def _install(config_path: Path) -> None:
    """Validate a configuration with the model, install it with --yes, and assert the run completed.

    Args:
        config_path: The configuration file to install.
    """
    EnvironmentConfig.model_validate(_load(config_path))
    with patch('sys.exit') as mock_exit:
        _run_setup(config_path, '--yes')
    mock_exit.assert_not_called()


def _launch_profile(profile_dir: Path, home: Path) -> LaunchRecord:
    """Start the profile's launch.sh with a stub claude and return what claude received.

    Args:
        profile_dir: The isolated profile directory.
        home: The home directory the launcher sees.

    Returns:
        The stub claude's record.
    """
    bash = find_bash()
    if bash is None:
        pytest.skip('bash is needed to run the generated launcher')
    return launch(
        [bash, str(profile_dir / 'launch.sh'), '--probe-arg'],
        home=home,
        stub_dir=home.parent / 'stub-bin',
    )


class TestModelAcceptsIndependentKeys:
    """The configuration model validates each key without the others."""

    @pytest.mark.parametrize(
        'path',
        [
            pytest.param(DEFAULTS_BASE, id='command-defaults-without-command-names'),
            pytest.param(NAMES_WITHOUT_DEFAULTS, id='command-names-without-command-defaults'),
            pytest.param(VERSION_BASE, id='version-without-command-names'),
        ],
    )
    def test_fixture_validates(self, path: Path) -> None:
        """Each configuration file passes model validation."""
        config = _load(path)
        validated = EnvironmentConfig.model_validate(config)
        assert validated.name == config['name']

    def test_defaults_base_declares_no_command_names(self) -> None:
        """The command-defaults fixture is a base configuration."""
        config = _load(DEFAULTS_BASE)
        assert 'command-names' not in config
        assert config['command-defaults']['system-prompt'].endswith(PROMPT_FILE)

    def test_version_base_declares_no_command_names(self) -> None:
        """The version fixture is a base configuration."""
        config = _load(VERSION_BASE)
        assert 'command-names' not in config
        assert config['version'] == '3.1.4'

    def test_names_fixture_declares_no_command_defaults(self) -> None:
        """The command-names fixture leaves command-defaults out."""
        assert 'command-defaults' not in _load(NAMES_WITHOUT_DEFAULTS)


class TestCommandDefaultsWithoutCommandNames:
    """A configuration declaring command-defaults without command names installs in both modes."""

    def test_base_install_completes_and_notes_isolated_only(
        self,
        e2e_isolated_home: dict[str, Path],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The base install completes, keeps the prompt file and says the prompt is not applied."""
        claude_dir = e2e_isolated_home['claude_dir']

        _install(DEFAULTS_BASE)

        captured = capsys.readouterr()
        note = setup_environment.COMMAND_DEFAULTS_ISOLATED_ONLY_NOTE
        # The installation summary goes to stderr when stdout is not a terminal;
        # the closing summary goes to stdout.
        assert note in captured.err.split('Installation Summary', 1)[1]
        assert f'System prompt: not applied ({note})' in captured.out.split('Setup Complete', 1)[1]
        assert (claude_dir / 'prompts' / PROMPT_FILE).is_file()
        assert not (claude_dir / 'launch.sh').exists()
        manifest = json.loads((claude_dir / 'manifest.json').read_text(encoding='utf-8'))
        assert manifest['name'] is None
        assert manifest['command_names'] == []

    def test_dry_run_notes_isolated_only(
        self,
        e2e_isolated_home: dict[str, Path],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--dry-run prints the note and changes nothing."""
        claude_dir = e2e_isolated_home['claude_dir']
        EnvironmentConfig.model_validate(_load(DEFAULTS_BASE))

        with pytest.raises(SystemExit) as exc_info:
            _run_setup(DEFAULTS_BASE, '--dry-run')

        assert exc_info.value.code == 0
        assert setup_environment.COMMAND_DEFAULTS_ISOLATED_ONLY_NOTE in capsys.readouterr().err
        assert not (claude_dir / 'prompts').exists()
        assert not (claude_dir / 'manifest.json').exists()

    def test_isolated_install_launcher_appends_the_prompt(
        self,
        e2e_isolated_home: dict[str, Path],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Given command names, the same configuration's launcher hands its prompt to Claude Code."""
        home = e2e_isolated_home['home']
        profile_dir = e2e_isolated_home['claude_dir'] / 'defaults-probe'
        assert 'command-defaults' not in _load(DEFAULTS_ISOLATED_LEAF)
        EnvironmentConfig.model_validate(_load(DEFAULTS_BASE))

        _install(DEFAULTS_ISOLATED_LEAF)

        captured = capsys.readouterr()
        assert setup_environment.COMMAND_DEFAULTS_ISOLATED_ONLY_NOTE not in captured.out + captured.err
        assert (profile_dir / 'prompts' / PROMPT_FILE).is_file()
        record = _launch_profile(profile_dir, home)
        assert same_path(record.config_dir, profile_dir), record.config_dir
        assert same_path(record.value_after('--settings'), profile_dir / 'config.json'), record.args
        prompt_flags = [arg for arg in record.args if arg in PROMPT_FLAGS]
        assert prompt_flags == ['--append-system-prompt-file'], record.args
        assert same_path(record.value_after('--append-system-prompt-file'), profile_dir / 'prompts' / PROMPT_FILE)


class TestCommandNamesWithoutCommandDefaults:
    """A configuration declaring command names without command-defaults installs a plain launcher."""

    def test_isolated_install_launcher_passes_no_prompt(
        self,
        e2e_isolated_home: dict[str, Path],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The launcher starts Claude Code with its own profile and no system prompt flag."""
        home = e2e_isolated_home['home']
        profile_dir = e2e_isolated_home['claude_dir'] / 'names-probe'

        _install(NAMES_WITHOUT_DEFAULTS)

        captured = capsys.readouterr()
        assert setup_environment.COMMAND_DEFAULTS_ISOLATED_ONLY_NOTE not in captured.out + captured.err
        assert 'System prompt' not in captured.out.split('Setup Complete', 1)[1]
        errors = validate_manifest(profile_dir / 'manifest.json', _load(NAMES_WITHOUT_DEFAULTS))
        assert not errors, '\n'.join(errors)
        assert not (profile_dir / 'prompts').exists() or not any((profile_dir / 'prompts').iterdir())
        local_bin = e2e_isolated_home['local_bin']
        wrapper_suffix = '.cmd' if sys.platform == 'win32' else ''
        for name in ('names-probe', 'names-probe-alias'):
            assert (local_bin / f'{name}{wrapper_suffix}').exists(), f'{name} wrapper missing'
        record = _launch_profile(profile_dir, home)
        assert same_path(record.config_dir, profile_dir), record.config_dir
        assert same_path(record.value_after('--settings'), profile_dir / 'config.json'), record.args
        assert not [arg for arg in record.args if arg in PROMPT_FLAGS], record.args
        assert '--probe-arg' in record.args, record.args


class TestVersionWithoutCommandNames:
    """A configuration declaring version without command names records it in the base manifest."""

    def test_base_install_records_version(self, e2e_isolated_home: dict[str, Path]) -> None:
        """~/.claude/manifest.json carries the configuration version and the base profile shape."""
        claude_dir = e2e_isolated_home['claude_dir']
        config = _load(VERSION_BASE)

        _install(VERSION_BASE)

        manifest_path = claude_dir / 'manifest.json'
        errors = validate_manifest(manifest_path, config)
        assert not errors, '\n'.join(errors)
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        assert manifest['version'] == '3.1.4'
        assert manifest['name'] is None
        assert manifest['command_names'] == []
        assert manifest['config_source_type'] == 'local'
