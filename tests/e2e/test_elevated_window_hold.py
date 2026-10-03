"""The window a UAC relaunch opens stays on screen for every failed or finished outcome.

Each test runs main() against a configuration file in an isolated home, with the platform
reported as Windows and the process as elevated, the way the relaunched window runs.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import setup_environment


def _run_main(argv: list[str], prompts: list[str]) -> int:
    """Run main() as the elevated window a UAC relaunch opens, recording every Enter prompt."""

    def _input(prompt: str) -> str:
        prompts.append(prompt)
        return ''

    with (
        patch.object(setup_environment.platform, 'system', return_value='Windows'),
        patch.object(setup_environment, 'is_admin', return_value=True),
        patch.object(setup_environment, 'is_running_in_pytest', return_value=False),
        patch('builtins.input', side_effect=_input),
        patch('sys.argv', ['setup_environment.py', *argv]),
        pytest.raises(SystemExit) as exc,
    ):
        setup_environment.main()
    code = exc.value.code
    assert isinstance(code, int)
    return code


@pytest.fixture
def invalid_settings_config(tmp_path: Path) -> Path:
    """A configuration whose user-settings fail validation after the elevation point."""
    config = tmp_path / 'invalid-settings.yaml'
    config.write_text(
        'name: Invalid settings\nuser-settings:\n  effortLevel: not-a-level\n',
        encoding='utf-8',
    )
    return config


def test_failed_validation_in_the_elevated_window_waits_for_enter(
    e2e_isolated_home: dict[str, Path], invalid_settings_config: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """A validation error exits 1 without a banner of its own, so the window holds it under 'Setup Failed'."""
    prompts: list[str] = []

    code = _run_main(['--elevated-via-uac', '--yes', '--skip-install', str(invalid_settings_config)], prompts)

    assert code == 1
    assert prompts == ['Press Enter to exit...']
    out = capsys.readouterr()
    assert 'effortLevel' in out.out + out.err
    assert 'Setup Failed' in out.out


def test_failed_validation_in_the_user_terminal_never_pauses(
    e2e_isolated_home: dict[str, Path], invalid_settings_config: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """Without the UAC relaunch the terminal stays open by itself, so nothing waits for Enter."""
    prompts: list[str] = []

    code = _run_main(['--yes', '--skip-install', str(invalid_settings_config)], prompts)

    assert code == 1
    assert prompts == []
    assert 'Setup Failed' not in capsys.readouterr().out


def test_an_exit_zero_in_the_elevated_window_closes_at_once(e2e_isolated_home: dict[str, Path], tmp_path: Path) -> None:
    """A successful early exit, such as listing the components, needs no pause."""
    config = tmp_path / 'components.yaml'
    config.write_text('name: Components\n', encoding='utf-8')
    prompts: list[str] = []

    code = _run_main(['--elevated-via-uac', '--list-components', str(config)], prompts)

    assert code == 0
    assert prompts == []
