"""
Tests for scripts/cli.py - the packaged subcommand dispatcher.
"""

import sys
from unittest.mock import patch

import pytest

from scripts.cli import USAGE
from scripts.cli import main


class TestCliDispatcher:
    """Test the claude-code-toolbox subcommand dispatcher."""

    def test_no_arguments_exits_2_with_usage_on_stderr(
        self,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Invoking without a subcommand fails with exit code 2 and prints usage to stderr."""
        monkeypatch.setattr(sys, 'argv', ['claude-code-toolbox'])
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 2
        captured = capsys.readouterr()
        assert USAGE in captured.err
        assert captured.out == ''

    @pytest.mark.parametrize('flag', ['-h', '--help'])
    def test_help_exits_0_with_usage_on_stdout(
        self,
        flag: str,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Top-level -h/--help succeeds with exit code 0 and prints usage to stdout."""
        monkeypatch.setattr(sys, 'argv', ['claude-code-toolbox', flag])
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        assert USAGE in capsys.readouterr().out

    def test_unknown_command_exits_2_with_usage_on_stderr(
        self,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An unknown subcommand fails with exit code 2 and names the command on stderr."""
        monkeypatch.setattr(sys, 'argv', ['claude-code-toolbox', 'bogus'])
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 2
        captured = capsys.readouterr()
        assert "'bogus'" in captured.err
        assert USAGE in captured.err

    def test_setup_delegates_with_subcommand_token_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The setup subcommand delegates once with the token stripped from sys.argv."""
        monkeypatch.setattr(sys, 'argv', ['claude-code-toolbox', 'setup', 'foo.yaml', '--dry-run'])
        observed_argv: list[str] = []
        with patch('scripts.setup_environment.main', side_effect=lambda: observed_argv.extend(sys.argv)) as setup_main:
            main()
        setup_main.assert_called_once()
        assert observed_argv[1:] == ['foo.yaml', '--dry-run']
        assert observed_argv[0].endswith('setup')

    def test_install_delegates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The install subcommand delegates to install_claude.main."""
        monkeypatch.setattr(sys, 'argv', ['claude-code-toolbox', 'install'])
        with patch('scripts.install_claude.main') as install_main:
            main()
        install_main.assert_called_once()

    def test_install_help_exits_0_without_delegating(
        self,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """install --help prints usage and never starts an installation."""
        monkeypatch.setattr(sys, 'argv', ['claude-code-toolbox', 'install', '--help'])
        with patch('scripts.install_claude.main') as install_main, pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        install_main.assert_not_called()
        assert USAGE in capsys.readouterr().out
