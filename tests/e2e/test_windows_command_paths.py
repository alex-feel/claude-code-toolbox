"""E2E tests for the apiKeyHelper and awsCredentialExport commands setup writes on Windows.

Claude Code runs both settings values through the shell, which on Windows is
cmd.exe started as ``cmd.exe /d /s /c "<value>"``. cmd.exe resolves no
``~``, so setup expands every tilde path to the absolute path under the home
folder and writes it in double quotes; unquoted, a home folder whose name
contains a space splits the path into two arguments and the helper never
starts (uv answers ``Failed to spawn``). An isolated run quotes each argument
that holds a re-rooted path, so a profile directory relocated below the home
into a folder whose name holds a space, and one outside the home that an
isolated run spells as an absolute path, reach cmd.exe as one argument too,
and a path the author already quoted keeps its quotes and gains none.

Every test installs a configuration through main() under an isolated home
named ``Test User``: as the base profile, as an isolated profile below the
home, as an isolated profile relocated below the home into a folder whose
name holds a space, and as an isolated profile relocated to a directory
outside the home whose name holds a space and parentheses. It then runs the
written values through cmd.exe exactly as Claude Code starts them, with the
real uv, and reads the helper's output. The same command with its quotes
removed fails under the same home, which shows the home folder really
splits it.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.profile_support import run_main
from tests.e2e.profile_support import write_config

pytestmark = [
    pytest.mark.skipif(sys.platform != 'win32', reason='cmd.exe runs the settings commands only on Windows'),
    pytest.mark.skipif(shutil.which('uv') is None, reason='uv is not on PATH'),
]

SKIP = ['--skip-install', '--no-admin']
PROFILE = 'p1'
HELPER_COMMAND = 'uv run --no-project --python 3.12'
API_KEY = 'sk-ant-api03-e2e-command-path-helper-key'
AWS_OUTPUT = 'e2e-aws-credential-export-ran'
_ANSI_SEQUENCE = re.compile(r'\x1b\[[0-9;]*m')


@pytest.fixture
def configs(tmp_path: Path) -> Path:
    """A directory holding the two helper scripts the configuration downloads."""
    directory = tmp_path / 'configs'
    (directory / 'files').mkdir(parents=True)
    (directory / 'files' / 'key_helper.py').write_text(f'print({API_KEY!r})\n', encoding='utf-8')
    (directory / 'files' / 'aws_export.py').write_text(f'print({AWS_OUTPUT!r})\n', encoding='utf-8')
    return directory


def _config(**user_settings: Any) -> dict[str, Any]:
    """A configuration whose helpers live in ~/.claude/scripts; awsCredentialExport is quoted by its author."""
    return {
        'name': 'Command Paths',
        'files-to-download': [
            {'source': 'files/key_helper.py', 'dest': '~/.claude/scripts/key_helper.py'},
            {'source': 'files/aws_export.py', 'dest': '~/.claude/scripts/aws_export.py'},
        ],
        'user-settings': {
            'apiKeyHelper': f'{HELPER_COMMAND} ~/.claude/scripts/key_helper.py',
            'awsCredentialExport': f'{HELPER_COMMAND} "~/.claude/scripts/aws_export.py"',
            **user_settings,
        },
    }


def _helper_environment(tmp_path: Path) -> dict[str, str]:
    """Return the environment the helpers run in: the isolated home, uv offline with a cache of its own.

    The interpreter running the tests leads PATH, so uv finds a Python 3.12
    without the managed installations the isolated home hides from it.

    Args:
        tmp_path: The test's temporary directory.

    Returns:
        The environment mapping for subprocess.run().
    """
    env = {key: value for key, value in os.environ.items() if key not in ('UV_LOCKED', 'UV_FROZEN')}
    env.update({
        'UV_CACHE_DIR': str(tmp_path / 'uv-cache'),
        'UV_PYTHON_DOWNLOADS': 'never',
        'PATH': os.pathsep.join([str(Path(sys.executable).parent), env.get('PATH', '')]),
    })
    return env


def _run_like_claude_code(command: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """Run a settings command the way Claude Code runs it on Windows.

    Claude Code starts the command with the ``shell: true`` option of
    child_process, which runs ``%COMSPEC% /d /s /c "<command>"`` with the
    command line passed verbatim; a string argument makes subprocess hand
    the same line to CreateProcess.

    Args:
        command: The apiKeyHelper or awsCredentialExport value.
        tmp_path: The test's temporary directory.

    Returns:
        The completed process.
    """
    work = tmp_path / 'work'
    work.mkdir(exist_ok=True)
    comspec = os.environ.get('COMSPEC', 'cmd.exe')
    return subprocess.run(
        f'{comspec} /d /s /c "{command}"',
        cwd=work, env=_helper_environment(tmp_path), capture_output=True, text=True, check=False, timeout=180,
    )


def _assert_helpers_print_their_output(settings: dict[str, Any], tmp_path: Path) -> None:
    """Run both written commands through cmd.exe and check each prints its helper's output."""
    for key, expected in (('apiKeyHelper', API_KEY), ('awsCredentialExport', AWS_OUTPUT)):
        completed = _run_like_claude_code(settings[key], tmp_path)
        assert completed.returncode == 0, f'{key}: {settings[key]}\n{completed.stdout}\n{completed.stderr}'
        assert completed.stdout.strip() == expected, f'{key}: {completed.stdout!r}'


def _assert_unquoted_command_splits(settings: dict[str, Any], tmp_path: Path) -> None:
    """The written apiKeyHelper with its quotes removed fails: the home folder's space splits the path."""
    unquoted = settings['apiKeyHelper'].replace('"', '')
    completed = _run_like_claude_code(unquoted, tmp_path)
    assert completed.returncode != 0, completed.stdout
    assert 'Failed to spawn' in completed.stderr, completed.stderr


def _quoted(path: Path) -> str:
    """Spell a path the way the Windows settings write spells it: absolute and double-quoted."""
    return f'"{os.path.normpath(str(path))}"'


def _output(capsys: pytest.CaptureFixture[str]) -> str:
    """Return everything the run printed, color codes stripped."""
    captured = capsys.readouterr()
    return _ANSI_SEQUENCE.sub('', captured.out + captured.err)


@pytest.mark.usefixtures('e2e_spaced_home')
class TestHelpersUnderASpacedHome:
    """The written helper commands run through cmd.exe under a home folder whose name contains a space."""

    def test_base_profile_settings_json_runs_through_cmd(
        self, e2e_spaced_home: dict[str, Path], configs: Path, tmp_path: Path,
    ) -> None:
        """settings.json carries each helper path once, double-quoted, and both helpers print their output."""
        home = e2e_spaced_home['home']
        assert ' ' in home.name
        cfg = write_config(configs, 'env.yaml', _config())

        assert run_main([str(cfg), *SKIP, '--yes']) == 0

        settings = json.loads((e2e_spaced_home['claude_dir'] / 'settings.json').read_text(encoding='utf-8'))
        scripts = home / '.claude' / 'scripts'
        assert settings['apiKeyHelper'] == f'{HELPER_COMMAND} {_quoted(scripts / "key_helper.py")}'
        assert settings['awsCredentialExport'] == f'{HELPER_COMMAND} {_quoted(scripts / "aws_export.py")}'
        _assert_helpers_print_their_output(settings, tmp_path)
        _assert_unquoted_command_splits(settings, tmp_path)

    def test_isolated_profile_config_json_runs_through_cmd(
        self, e2e_spaced_home: dict[str, Path], configs: Path, tmp_path: Path,
    ) -> None:
        """config.json carries the re-rooted helper paths inside the profile, double-quoted, and both run."""
        home = e2e_spaced_home['home']
        profile_dir = e2e_spaced_home['claude_dir'] / PROFILE
        cfg = write_config(configs, 'env.yaml', _config())

        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', PROFILE]) == 0

        settings = json.loads((profile_dir / 'config.json').read_text(encoding='utf-8'))
        scripts = home / '.claude' / PROFILE / 'scripts'
        assert settings['apiKeyHelper'] == f'{HELPER_COMMAND} {_quoted(scripts / "key_helper.py")}'
        assert settings['awsCredentialExport'] == f'{HELPER_COMMAND} {_quoted(scripts / "aws_export.py")}'
        assert (scripts / 'key_helper.py').is_file()
        _assert_helpers_print_their_output(settings, tmp_path)
        _assert_unquoted_command_splits(settings, tmp_path)

    @pytest.mark.parametrize(
        'parts',
        [
            pytest.param(('My Profiles', PROFILE), id='spaced-parent'),
            pytest.param(('profiles', 'tilde work'), id='spaced-profile'),
        ],
    )
    def test_profile_relocated_below_the_home_into_a_spaced_folder_runs_through_cmd(
        self, e2e_spaced_home: dict[str, Path], configs: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
        parts: tuple[str, str],
    ) -> None:
        """The summary quotes the home-relative path; config.json carries the whole absolute path once quoted."""
        profile_dir = e2e_spaced_home['home'].joinpath(*parts)
        relative = '/'.join(parts)
        cfg = write_config(configs, 'env.yaml', _config(env={'CLAUDE_CONFIG_DIR': f'~/{relative}'}))

        assert run_main([str(cfg), *SKIP, '--dry-run', '--command-names', PROFILE]) == 0
        dry_run = _output(capsys)
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', PROFILE]) == 0

        settings = json.loads((profile_dir / 'config.json').read_text(encoding='utf-8'))
        scripts = profile_dir / 'scripts'
        assert settings['apiKeyHelper'] == f'{HELPER_COMMAND} {_quoted(scripts / "key_helper.py")}'
        assert settings['awsCredentialExport'] == f'{HELPER_COMMAND} {_quoted(scripts / "aws_export.py")}'
        assert (scripts / 'key_helper.py').is_file()
        assert (
            f'[re-rooted] user-settings apiKeyHelper: {HELPER_COMMAND} ~/.claude/scripts/key_helper.py -> '
            f'{HELPER_COMMAND} "~/{relative}/scripts/key_helper.py"'
        ) in dry_run
        _assert_helpers_print_their_output(settings, tmp_path)
        _assert_unquoted_command_splits(settings, tmp_path)

    def test_profile_outside_the_home_runs_through_cmd(
        self, e2e_spaced_home: dict[str, Path], configs: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The absolute profile path is quoted once in config.json and in the summary, and both helpers run."""
        outside = e2e_spaced_home['home'].parent / 'Profile Store (work)' / PROFILE
        posix = outside.as_posix()
        cfg = write_config(configs, 'env.yaml', _config(env={'CLAUDE_CONFIG_DIR': str(outside)}))

        assert run_main([str(cfg), *SKIP, '--dry-run', '--command-names', PROFILE]) == 0
        dry_run = _output(capsys)
        assert run_main([str(cfg), *SKIP, '--yes', '--command-names', PROFILE]) == 0

        settings = json.loads((outside / 'config.json').read_text(encoding='utf-8'))
        helper = f'{HELPER_COMMAND} "{posix}/scripts/key_helper.py"'
        assert settings['apiKeyHelper'] == helper
        assert settings['awsCredentialExport'] == f'{HELPER_COMMAND} "{posix}/scripts/aws_export.py"'
        assert (
            f'[re-rooted] user-settings apiKeyHelper: {HELPER_COMMAND} ~/.claude/scripts/key_helper.py -> {helper}'
        ) in dry_run
        _assert_helpers_print_their_output(settings, tmp_path)
        _assert_unquoted_command_splits(settings, tmp_path)
