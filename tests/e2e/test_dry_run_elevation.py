"""E2E tests for Windows administrator elevation under --dry-run.

A real run on Windows that needs administrator rights relaunches itself
through a UAC prompt before anything is installed. A dry run only previews
the plan, so it never requests elevation: it reports what the real run would
elevate for and continues to the installation summary. The tests drive main()
against the golden configuration with the privilege probe and the UAC relaunch
replaced, so no prompt opens and the outcome does not depend on whether the
test process itself runs elevated.

UAC elevation exists only on Windows, where main() takes this path from the
real platform, so the module runs on Windows only.
"""

from __future__ import annotations

import copy
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import yaml

from scripts import setup_environment

pytestmark = pytest.mark.skipif(
    sys.platform != 'win32', reason='UAC elevation exists only on Windows',
)

INSTALL_REASON = 'Installing Claude Code (includes Node.js and Git)'
WINGET_DEPENDENCY = 'winget install E2E.MachineTool --scope machine'
NPM_DEPENDENCY = 'npm install -g e2e-global-cli'
DRY_RUN_HEADLINE = 'Dry run: administrator elevation is not requested.'
BANNER_TITLE = 'Administrator Privileges Required'


def _load_golden() -> dict[str, Any]:
    """Load the golden configuration."""
    config_path = Path(__file__).parent / 'golden_config.yaml'
    with config_path.open('r', encoding='utf-8') as handle:
        config: dict[str, Any] = yaml.safe_load(handle)
    return config


def _golden_with_elevated_dependencies() -> dict[str, Any]:
    """Return the golden configuration plus one dependency of each kind that needs admin."""
    config = copy.deepcopy(_load_golden())
    dependencies = config['dependencies']
    dependencies['windows'] = [*dependencies['windows'], WINGET_DEPENDENCY]
    dependencies['common'] = [*dependencies['common'], NPM_DEPENDENCY]
    return config


@pytest.fixture
def mock_request_elevation() -> Iterator[MagicMock]:
    """Replace the UAC relaunch so no prompt opens and every call is recorded."""
    with patch('scripts.setup_environment.request_admin_elevation') as mock_request:
        yield mock_request


def _run_main(
    config: dict[str, Any], extra_argv: list[str], *, admin: bool = False,
) -> int:
    """Drive main() with network validation stubbed and a non-interactive terminal.

    Returns:
        The exit code main() ended with.
    """
    with (
        patch('scripts.setup_environment.load_config_from_source',
              return_value=(config, 'golden.yaml')),
        patch('scripts.setup_environment.validate_all_config_files',
              return_value=(True, [])),
        patch('scripts.setup_environment.is_admin', return_value=admin),
        patch('scripts.setup_environment._dev_tty_available', return_value=False),
        patch('sys.stdin.isatty', return_value=False),
        patch('sys.argv', ['setup_environment.py', 'golden', *extra_argv]),
        pytest.raises(SystemExit) as exc_info,
    ):
        setup_environment.main()
    code = exc_info.value.code
    assert isinstance(code, int)
    return code


def _assert_nothing_installed(paths: dict[str, Path]) -> None:
    """Assert that the run wrote no configuration into the isolated home."""
    claude_dir = paths['claude_dir']
    assert not (paths['home'] / '.claude.json').exists()
    assert not (claude_dir / 'settings.json').exists()
    assert list(claude_dir.iterdir()) == [], 'the run created files under ~/.claude'


class TestDryRunNeverElevates:
    """A dry run that a real run would elevate for previews the plan instead."""

    @pytest.mark.parametrize('via', ['flag', 'environment variable'])
    def test_dry_run_reports_the_claude_code_install_and_exits_zero(
        self,
        via: str,
        e2e_isolated_home: dict[str, Path],
        mock_request_elevation: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Installing Claude Code needs admin, so the dry run names it and reaches the summary."""
        if via == 'flag':
            extra_argv = ['--dry-run']
        else:
            monkeypatch.setenv('CLAUDE_CODE_TOOLBOX_DRY_RUN', '1')
            extra_argv = []

        exit_code = _run_main(_load_golden(), extra_argv)

        assert exit_code == 0
        mock_request_elevation.assert_not_called()
        captured = capsys.readouterr()
        assert DRY_RUN_HEADLINE in captured.out
        assert 'A real run requests administrator privileges for:' in captured.out
        assert f'  - {INSTALL_REASON}' in captured.out
        assert BANNER_TITLE not in captured.out
        # The summary renders to stderr when stdout is piped, so check both streams
        assert 'Installation Summary' in captured.out + captured.err
        assert 'Dry run complete. No changes were made.' in captured.out
        _assert_nothing_installed(e2e_isolated_home)

    def test_dry_run_lists_every_dependency_the_banner_would_list(
        self,
        e2e_isolated_home: dict[str, Path],
        mock_request_elevation: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """With --skip-install the reasons are the machine-scope winget and global npm commands."""
        exit_code = _run_main(
            _golden_with_elevated_dependencies(), ['--dry-run', '--skip-install'],
        )

        assert exit_code == 0
        mock_request_elevation.assert_not_called()
        out = capsys.readouterr().out
        assert DRY_RUN_HEADLINE in out
        assert f'  - System-wide installation: {WINGET_DEPENDENCY}' in out
        assert f'  - Global npm package: {NPM_DEPENDENCY}' in out
        assert INSTALL_REASON not in out
        assert out.index(WINGET_DEPENDENCY) < out.index(NPM_DEPENDENCY)
        _assert_nothing_installed(e2e_isolated_home)

    def test_dry_run_in_an_elevated_terminal_reports_nothing(
        self,
        e2e_isolated_home: dict[str, Path],
        mock_request_elevation: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """An elevated process would not relaunch, so there is nothing to report."""
        exit_code = _run_main(_load_golden(), ['--dry-run'], admin=True)

        assert exit_code == 0
        mock_request_elevation.assert_not_called()
        captured = capsys.readouterr()
        assert DRY_RUN_HEADLINE not in captured.out
        assert 'Installation Summary' in captured.out + captured.err
        _assert_nothing_installed(e2e_isolated_home)

    def test_dry_run_with_no_admin_reports_nothing(
        self,
        e2e_isolated_home: dict[str, Path],
        mock_request_elevation: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--no-admin turns the check off, so a dry run with it prints no elevation block."""
        exit_code = _run_main(_load_golden(), ['--dry-run', '--no-admin'])

        assert exit_code == 0
        mock_request_elevation.assert_not_called()
        captured = capsys.readouterr()
        assert DRY_RUN_HEADLINE not in captured.out
        assert 'Installation Summary' in captured.out + captured.err
        _assert_nothing_installed(e2e_isolated_home)


class TestRealRunElevation:
    """A real run keeps requesting elevation unless --no-admin is given."""

    def test_real_run_requests_elevation_before_any_install(
        self,
        e2e_isolated_home: dict[str, Path],
        mock_request_elevation: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The banner lists every reason and the granted relaunch ends this process."""
        mock_request_elevation.side_effect = SystemExit(0)

        exit_code = _run_main(_golden_with_elevated_dependencies(), ['--yes'])

        assert exit_code == 0
        mock_request_elevation.assert_called_once_with()
        captured = capsys.readouterr()
        assert BANNER_TITLE in captured.out
        assert f'  - {INSTALL_REASON}' in captured.out
        assert f'  - System-wide installation: {WINGET_DEPENDENCY}' in captured.out
        assert f'  - Global npm package: {NPM_DEPENDENCY}' in captured.out
        assert DRY_RUN_HEADLINE not in captured.out
        assert 'Installation Summary' not in captured.out + captured.err
        _assert_nothing_installed(e2e_isolated_home)

    def test_denied_elevation_exits_one(
        self,
        e2e_isolated_home: dict[str, Path],
        mock_request_elevation: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A relaunch that returns means elevation was denied, and the run stops."""
        exit_code = _run_main(_load_golden(), ['--yes'])

        assert exit_code == 1
        mock_request_elevation.assert_called_once_with()
        captured = capsys.readouterr()
        assert BANNER_TITLE in captured.out
        assert 'Administrator elevation was denied' in captured.err
        assert 'Alternatively, use --no-admin flag to skip elevation' in captured.err
        _assert_nothing_installed(e2e_isolated_home)

    @pytest.mark.parametrize('via', ['flag', 'environment variable'])
    def test_no_admin_skips_elevation_on_a_real_run(
        self,
        via: str,
        e2e_isolated_home: dict[str, Path],
        mock_request_elevation: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The run goes straight to its summary; the missing terminal then refuses consent."""
        if via == 'flag':
            extra_argv = ['--no-admin']
        else:
            monkeypatch.setenv('CLAUDE_CODE_TOOLBOX_NO_ADMIN', '1')
            extra_argv = []

        exit_code = _run_main(_golden_with_elevated_dependencies(), extra_argv)

        assert exit_code == 1
        mock_request_elevation.assert_not_called()
        captured = capsys.readouterr()
        assert BANNER_TITLE not in captured.out
        assert DRY_RUN_HEADLINE not in captured.out
        assert 'Installation Summary' in captured.out + captured.err
        assert 'Cannot proceed: no interactive terminal available' in captured.err
        _assert_nothing_installed(e2e_isolated_home)
