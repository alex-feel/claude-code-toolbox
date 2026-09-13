"""Tests for the ambient CLAUDE_CONFIG_DIR guard and the target-directory helper.

The Claude CLI resolves CLAUDE_CONFIG_DIR ahead of the home directory, so a
setup run started inside an isolated profile session inherits that variable and
would let ``claude mcp add`` and the global-config writes land somewhere other
than the directory the rest of the run targets.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

import setup_environment


class TestResolveArtifactBaseDir:
    """resolve_artifact_base_dir() reports the directory a run writes into."""

    def test_non_isolated_run_targets_base_claude_dir(self, mock_home_dir: Path) -> None:
        """Without command-names the target is ~/.claude."""
        base_dir, uses_override = setup_environment.resolve_artifact_base_dir(None, None)

        assert base_dir == mock_home_dir / '.claude'
        assert uses_override is False

    def test_isolated_run_targets_named_profile_dir(self, mock_home_dir: Path) -> None:
        """With command-names the target is ~/.claude/{primary}."""
        base_dir, uses_override = setup_environment.resolve_artifact_base_dir('claude-test', None)

        assert base_dir == mock_home_dir / '.claude' / 'claude-test'
        assert uses_override is False

    def test_user_settings_env_override_wins(self, mock_home_dir: Path, temp_dir: Path) -> None:
        """A CLAUDE_CONFIG_DIR in user-settings.env replaces the computed path."""
        del mock_home_dir
        override = temp_dir / 'custom-profile'
        base_dir, uses_override = setup_environment.resolve_artifact_base_dir(
            'claude-test', {'env': {'CLAUDE_CONFIG_DIR': str(override)}},
        )

        assert base_dir == override
        assert uses_override is True

    def test_user_settings_env_override_expands_tilde(
        self, mock_home_dir: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A tilde-prefixed override expands against the user's home."""
        # Path.expanduser() resolves through the home environment variables,
        # which mock_home_dir (Path.home only) does not cover
        monkeypatch.setenv('HOME', str(mock_home_dir))
        monkeypatch.setenv('USERPROFILE', str(mock_home_dir))

        base_dir, uses_override = setup_environment.resolve_artifact_base_dir(
            'claude-test', {'env': {'CLAUDE_CONFIG_DIR': '~/custom-profile'}},
        )

        assert base_dir == mock_home_dir / 'custom-profile'
        assert uses_override is True

    def test_null_override_falls_back_to_computed_path(self, mock_home_dir: Path) -> None:
        """A null (deletion) entry is not a path and does not override the target."""
        base_dir, uses_override = setup_environment.resolve_artifact_base_dir(
            'claude-test', {'env': {'CLAUDE_CONFIG_DIR': None}},
        )

        assert base_dir == mock_home_dir / '.claude' / 'claude-test'
        assert uses_override is False

    def test_override_ignored_without_command_names(self, mock_home_dir: Path, temp_dir: Path) -> None:
        """A non-isolated run keeps ~/.claude even when user-settings.env pins a directory."""
        base_dir, uses_override = setup_environment.resolve_artifact_base_dir(
            None, {'env': {'CLAUDE_CONFIG_DIR': str(temp_dir / 'ignored')}},
        )

        assert base_dir == mock_home_dir / '.claude'
        assert uses_override is False


class TestCheckAmbientClaudeConfigDir:
    """check_ambient_claude_config_dir() gates the run on the inherited variable."""

    def test_unset_variable_passes_silently(
        self, temp_dir: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """No ambient value means nothing to reconcile."""
        assert setup_environment.check_ambient_claude_config_dir(None, temp_dir / '.claude') is True

        captured = capsys.readouterr()
        assert captured.out == ''
        assert captured.err == ''

    def test_whitespace_only_value_counts_as_set(
        self, temp_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A blank value still redirects the CLI, so the guard must not wave it through."""
        monkeypatch.setenv('CLAUDE_CONFIG_DIR', '   ')

        assert setup_environment.check_ambient_claude_config_dir(None, temp_dir / '.claude') is False
        assert 'CLAUDE_CONFIG_DIR is set to' in capsys.readouterr().err

    def test_set_definition_matches_the_cli_target_resolution(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The guard and the CLI-target resolution agree on which values count as set."""
        monkeypatch.setenv('CLAUDE_CONFIG_DIR', '   ')
        # The resolution the toolbox uses for `claude mcp` targets honors the value...
        assert setup_environment._claude_global_config_file(None) == Path('   ') / '.claude.json'
        # ...so the guard must treat the same value as a split run, not as unset
        assert setup_environment.check_ambient_claude_config_dir(None, Path.home() / '.claude') is False

        monkeypatch.setenv('CLAUDE_CONFIG_DIR', '')
        assert setup_environment._claude_global_config_file(None) == (
            setup_environment.get_real_user_home() / '.claude.json'
        )
        assert setup_environment.check_ambient_claude_config_dir(None, Path.home() / '.claude') is True

    def test_refusal_names_the_persisted_variable_case(
        self, temp_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A variable persisted by a configuration reproduces in every terminal, so say so."""
        monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(temp_dir / 'profile'))

        assert setup_environment.check_ambient_claude_config_dir(None, temp_dir / '.claude') is False

        err = capsys.readouterr().err
        assert 'os-env-variables' in err
        assert 'user-settings.env' in err

    def test_non_isolated_run_is_blocked(
        self, temp_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Without command-names any ambient value splits the run and aborts it."""
        monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(temp_dir / 'profile'))

        assert setup_environment.check_ambient_claude_config_dir(None, temp_dir / '.claude') is False

        err = capsys.readouterr().err
        assert 'CLAUDE_CONFIG_DIR is set to' in err
        assert str(temp_dir / 'profile') in err
        assert str(temp_dir / '.claude') in err
        assert 'unset CLAUDE_CONFIG_DIR' in err
        assert 'Remove-Item Env:CLAUDE_CONFIG_DIR' in err
        assert 'not inside an isolated profile session' in err

    def test_non_isolated_run_blocked_even_when_value_equals_target(
        self, temp_dir: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """~/.claude is still wrong for the CLI, whose base global config is ~/.claude.json."""
        claude_dir = temp_dir / '.claude'
        monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(claude_dir))

        assert setup_environment.check_ambient_claude_config_dir(None, claude_dir) is False

    def test_isolated_run_with_matching_value_passes_silently(
        self, temp_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """An isolated run already inside its own profile session has nothing to report."""
        profile_dir = temp_dir / '.claude' / 'claude-test'
        monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(profile_dir))

        assert setup_environment.check_ambient_claude_config_dir('claude-test', profile_dir) is True

        captured = capsys.readouterr()
        assert 'CLAUDE_CONFIG_DIR' not in captured.out
        assert captured.err == ''

    def test_isolated_run_tolerates_trailing_separator(
        self, temp_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The same directory written with a trailing separator is still the same directory."""
        profile_dir = temp_dir / '.claude' / 'claude-test'
        monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(profile_dir) + '/')

        assert setup_environment.check_ambient_claude_config_dir('claude-test', profile_dir) is True
        assert 'CLAUDE_CONFIG_DIR' not in capsys.readouterr().out

    def test_isolated_run_with_different_value_warns_and_proceeds(
        self, temp_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Setup replaces the inherited value, and says which profile it configures."""
        other_dir = temp_dir / '.claude' / 'claude-other'
        profile_dir = temp_dir / '.claude' / 'claude-test'
        monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(other_dir))

        assert setup_environment.check_ambient_claude_config_dir('claude-test', profile_dir) is True

        out = capsys.readouterr().out
        assert 'WARN' in out
        assert str(other_dir) in out
        assert str(profile_dir) in out
        assert 'claude-test' in out


class TestMainAmbientConfigDirGuard:
    """main() runs the guard before the installation summary."""

    @staticmethod
    def _run_main(config: dict[str, object], extra_argv: list[str]) -> None:
        argv = ['setup_environment.py', 'test', '--skip-install', *extra_argv]
        with (
            patch('setup_environment.load_config_from_source', return_value=(config, 'test.yaml')),
            patch('setup_environment.validate_all_config_files', return_value=(True, [])),
            patch('sys.argv', argv),
        ):
            setup_environment.main()

    def test_non_isolated_run_exits_before_the_summary(
        self,
        mock_home_dir: Path,
        temp_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The guard aborts the run before the plan is collected or confirmed."""
        del mock_home_dir
        monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(temp_dir / 'profile'))

        with pytest.raises(SystemExit) as exc_info:
            self._run_main({'name': 'Guarded'}, ['--yes'])

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert 'CLAUDE_CONFIG_DIR is set to' in captured.err
        # The summary renders to stderr when stdout is piped, so check both streams
        assert 'Installation Summary' not in captured.out + captured.err

    def test_dry_run_reports_the_block_too(
        self,
        mock_home_dir: Path,
        temp_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--dry-run must surface the block rather than print a plan it cannot execute."""
        del mock_home_dir
        monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(temp_dir / 'profile'))

        with pytest.raises(SystemExit) as exc_info:
            self._run_main({'name': 'Guarded'}, ['--dry-run'])

        assert exc_info.value.code == 1
        assert 'CLAUDE_CONFIG_DIR is set to' in capsys.readouterr().err

    def test_guard_precedes_the_component_picker_and_the_admin_check(
        self,
        mock_home_dir: Path,
        temp_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A refused run asks the user nothing first."""
        del mock_home_dir
        monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(temp_dir / 'profile'))
        config: dict[str, object] = {
            'name': 'Guarded',
            'agents': ['agents/optional.md'],
            'components': [
                {'name': 'optional', 'includes': {'agents': ['agents/optional.md']}},
            ],
        }

        with (
            patch('setup_environment.prompt_component_selection') as mock_picker,
            patch('setup_environment.check_admin_needed', return_value=True) as mock_admin,
            patch('sys.stdin.isatty', return_value=True),
            pytest.raises(SystemExit) as exc_info,
        ):
            self._run_main(config, [])

        assert exc_info.value.code == 1
        # The refusal, not a configuration error, is what ended the run
        assert 'CLAUDE_CONFIG_DIR is set to' in capsys.readouterr().err
        mock_picker.assert_not_called()
        mock_admin.assert_not_called()

    def test_isolated_run_warns_and_continues_to_the_summary(
        self,
        mock_home_dir: Path,
        temp_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """An isolated run reports the replacement and still reaches the dry-run plan."""
        del mock_home_dir
        monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(temp_dir / 'other-profile'))

        with pytest.raises(SystemExit) as exc_info:
            self._run_main(
                {'name': 'Guarded', 'command-names': ['claude-test']}, ['--dry-run'],
            )

        assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert str(temp_dir / 'other-profile') in out
        assert 'claude-test' in out
