"""E2E tests for the ambient CLAUDE_CONFIG_DIR guard against the golden configs.

A setup run started from inside an isolated profile session inherits the
CLAUDE_CONFIG_DIR the launcher exported. The Claude CLI resolves that variable
ahead of the home directory, so a non-isolated run would write its MCP servers
and global config into the profile directory while everything else lands in
~/.claude. Such a run is refused; an isolated run replaces the value and says so.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from scripts import setup_environment


def _load_golden(name: str) -> dict[str, Any]:
    """Load one of the golden configuration files."""
    config_path = Path(__file__).parent / name
    with config_path.open('r', encoding='utf-8') as handle:
        config: dict[str, Any] = yaml.safe_load(handle)
    return config


def _run_main(config: dict[str, Any], extra_argv: list[str]) -> None:
    """Drive main() against an in-memory config with network validation stubbed."""
    with (
        patch('scripts.setup_environment.load_config_from_source',
              return_value=(config, 'golden.yaml')),
        patch('scripts.setup_environment.validate_all_config_files',
              return_value=(True, [])),
        patch('sys.argv', ['setup_environment.py', 'golden', '--skip-install', *extra_argv]),
    ):
        setup_environment.main()


class TestNonIsolatedRunUnderAmbientConfigDir:
    """A golden run without command-names refuses to start."""

    def test_run_exits_one_without_writing_anything(
        self,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The guard fires before any artifact directory or settings file is created."""
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']
        monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(claude_dir / 'some-profile'))

        with pytest.raises(SystemExit) as exc_info:
            _run_main(_load_golden('golden_config_no_command_names.yaml'), ['--yes'])

        assert exc_info.value.code == 1

        err = capsys.readouterr().err
        assert 'CLAUDE_CONFIG_DIR is set to' in err
        assert 'unset CLAUDE_CONFIG_DIR' in err
        assert 'Remove-Item Env:CLAUDE_CONFIG_DIR' in err

        assert not (claude_dir / 'settings.json').exists()
        assert not (home / '.claude.json').exists()
        for subdir in ('agents', 'commands', 'rules', 'skills', 'hooks', 'prompts'):
            assert not (claude_dir / subdir).exists(), f'{subdir} should not have been created'

    def test_dry_run_reports_the_block(
        self,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A preview of a run that cannot execute reports the block, not a plan."""
        claude_dir = e2e_isolated_home['claude_dir']
        monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(claude_dir / 'some-profile'))

        with pytest.raises(SystemExit) as exc_info:
            _run_main(_load_golden('golden_config_no_command_names.yaml'), ['--dry-run'])

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert 'CLAUDE_CONFIG_DIR is set to' in captured.err
        # The summary renders to stderr when stdout is piped, so check both streams
        assert 'Installation Summary' not in captured.out + captured.err


class TestIsolatedRunUnderAmbientConfigDir:
    """A golden run with command-names proceeds and reports the replacement."""

    def test_differing_value_warns_and_the_run_continues(
        self,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The run says which profile it configures and still renders the plan."""
        claude_dir = e2e_isolated_home['claude_dir']
        other_profile = claude_dir / 'other-profile'
        monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(other_profile))

        config = _load_golden('golden_config.yaml')
        with pytest.raises(SystemExit) as exc_info:
            _run_main(config, ['--dry-run'])

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert str(other_profile) in captured.out
        assert str(claude_dir / config['command-names'][0]) in captured.out
        assert 'Installation Summary' in captured.out + captured.err

    def test_matching_value_adds_no_warning(
        self,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Running from inside the profile's own session is the expected case."""
        claude_dir = e2e_isolated_home['claude_dir']
        config = _load_golden('golden_config.yaml')
        profile_dir = claude_dir / config['command-names'][0]
        monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(profile_dir))

        with pytest.raises(SystemExit) as exc_info:
            _run_main(config, ['--dry-run'])

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert 'setup replaces it with' not in captured.out
        assert 'Installation Summary' in captured.out + captured.err
