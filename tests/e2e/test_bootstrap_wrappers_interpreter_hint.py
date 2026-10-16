"""E2E tests for the interpreter hint the platform bootstrap wrappers print when uv run fails.

When ``uv run`` exits non-zero, each wrapper asks ``uv python find`` whether
uv can provide the Python version the setup runs on, with the check's output
discarded. Only when the check fails too does the wrapper name the repair,
``uv python install --reinstall``; in every case it exits with the code
``uv run`` returned. A recording stand-in for uv answers each call the way a
test asks and writes every argument vector it receives to a file. On Linux
and macOS the bash wrappers run for real with that stand-in and a curl
stand-in. On Windows the stand-in is a native command (a ``uv.cmd`` first on
PATH), so Windows PowerShell treats the check's stderr as it treats real
uv's, and the wrapper runs as a script and through ``iex``, the documented
one-liner.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.e2e.bootstrap_wrapper_support import UNIX_WRAPPERS
from tests.e2e.bootstrap_wrapper_support import WINDOWS_WRAPPER
from tests.e2e.bootstrap_wrapper_support import run_unix_wrapper
from tests.e2e.bootstrap_wrapper_support import unix_wrapper

_ANSI_SEQUENCE = re.compile(r'\x1b\[[0-9;]*m')

# The Python version the wrappers run the setup on
SETUP_PYTHON = '3.12'
CONFIG = 'profile.yaml'
RUN_CALL = ['run', '--no-project', '--python', SETUP_PYTHON, 'setup_environment.py', CONFIG]
PROBE_CALL = ['python', 'find', SETUP_PYTHON]
INSTALL_CALL = ['python', 'install', SETUP_PYTHON]
HINT_LINES = (
    f'[FAIL] uv cannot provide Python {SETUP_PYTHON}, which the setup runs on.',
    f'[FAIL] Install it with: uv python install --reinstall {SETUP_PYTHON}',
    (
        f'[FAIL] This installs Python {SETUP_PYTHON}, or replaces a uv-managed copy whose files are missing; '
        'then run this setup command again.'
    ),
)
MISSING_INTERPRETER = r'error: Python interpreter not found at C:\uv\python\cpython-3.12.15\python.exe'
PROBE_STDOUT = 'probe output on stdout'
PROBE_STDERR = 'probe output on stderr'

UV_RECORDER = f'''\
"""Stand-in for uv: record each call, then answer it the way the test asks."""
import json
import os
import sys

arguments = sys.argv[1:]
with open(os.environ['E2E_UV_CALLS'], 'a', encoding='utf-8') as calls:
    calls.write(json.dumps(arguments) + '\\n')
if arguments[:2] == ['python', 'find']:
    print({PROBE_STDOUT!r})
    print({PROBE_STDERR!r}, file=sys.stderr)
    sys.exit(int(os.environ['E2E_UV_FIND_EXIT']))
if arguments[:1] == ['run']:
    if os.environ.get('E2E_UV_RUN_STDERR'):
        print(os.environ['E2E_UV_RUN_STDERR'], file=sys.stderr)
    sys.exit(int(os.environ['E2E_UV_RUN_EXIT']))
sys.exit(0)
'''

UNIX_UV_SHIM = '''\
#!/usr/bin/env bash
exec "$E2E_PYTHON" "$E2E_UV_RECORDER" "$@"
'''

WINDOWS_UV_SHIM = '@"%E2E_PYTHON%" "%E2E_UV_RECORDER%" %*\r\n'

WINDOWS_DOWNLOAD_STAND_IN = '''\
function Invoke-WebRequest {
    param($Uri, $OutFile, [switch]$UseBasicParsing)
    Set-Content -LiteralPath $OutFile -Value ''
}
'''

# (exit code of uv run, its stderr, exit code of uv python find)
SETUP_FAILS = (1, 'setup failed', 0)
INTERPRETER_MISSING = (2, MISSING_INTERPRETER, 2)
SETUP_SUCCEEDS = (0, '', 0)


def _recorder_environment(tmp_path: Path, answers: tuple[int, str, int]) -> dict[str, str]:
    """Write the uv recorder and return the variables that point the stand-in at it and set its answers."""
    recorder = tmp_path / 'uv_recorder.py'
    recorder.write_text(UV_RECORDER, encoding='utf-8')
    run_exit, run_stderr, find_exit = answers
    return {
        'E2E_PYTHON': sys.executable,
        'E2E_UV_RECORDER': str(recorder),
        'E2E_UV_CALLS': str(tmp_path / 'uv-calls.jsonl'),
        'E2E_UV_RUN_EXIT': str(run_exit),
        'E2E_UV_RUN_STDERR': run_stderr,
        'E2E_UV_FIND_EXIT': str(find_exit),
    }


def _recorded_calls(tmp_path: Path) -> list[list[str]]:
    """Return every argument vector the uv stand-in received, in order."""
    calls = tmp_path / 'uv-calls.jsonl'
    return [json.loads(line) for line in calls.read_text(encoding='utf-8').splitlines()]


def _plain(output: str) -> str:
    """Strip color codes and Windows line endings from a wrapper's output."""
    return _ANSI_SEQUENCE.sub('', output).replace('\r\n', '\n')


def _assert_probe_output_discarded(output: str) -> None:
    """The check's own output never reaches the wrapper's output."""
    assert PROBE_STDOUT not in output, output
    assert PROBE_STDERR not in output, output


def _run_unix(tmp_path: Path, platform_dir: str, answers: tuple[int, str, int]) -> tuple[int, str]:
    """Run a bash wrapper with the uv recorder and return its exit code and plain output."""
    result = run_unix_wrapper(
        tmp_path, unix_wrapper(platform_dir), [CONFIG], _recorder_environment(tmp_path, answers),
        uv_stand_in=UNIX_UV_SHIM,
    )
    return result.returncode, _plain(result.stdout + result.stderr)


@pytest.mark.parametrize('platform_dir', UNIX_WRAPPERS)
class TestUnixWrapperInterpreterHint:
    """The bash wrappers name the interpreter repair only when uv cannot provide the interpreter."""

    def test_setup_failure_with_the_interpreter_available_prints_no_hint(
        self, platform_dir: str, tmp_path: Path,
    ) -> None:
        """A failed setup is checked, the check passes, and the setup's exit code comes back unchanged."""
        code, output = _run_unix(tmp_path, platform_dir, SETUP_FAILS)

        assert code == 1, output
        assert _recorded_calls(tmp_path) == [INSTALL_CALL, RUN_CALL, PROBE_CALL]
        assert 'setup failed' in output
        for line in HINT_LINES:
            assert line not in output, output
        _assert_probe_output_discarded(output)

    def test_missing_interpreter_names_the_repair(self, platform_dir: str, tmp_path: Path) -> None:
        """uv's own error stays visible, the three hint lines print, and the exit code is uv run's."""
        code, output = _run_unix(tmp_path, platform_dir, INTERPRETER_MISSING)

        assert code == 2, output
        assert _recorded_calls(tmp_path) == [INSTALL_CALL, RUN_CALL, PROBE_CALL]
        assert MISSING_INTERPRETER in output
        assert '\n'.join(HINT_LINES) in output, output
        _assert_probe_output_discarded(output)

    def test_successful_setup_runs_no_check(self, platform_dir: str, tmp_path: Path) -> None:
        """A setup that succeeds never runs uv python find."""
        code, output = _run_unix(tmp_path, platform_dir, SETUP_SUCCEEDS)

        assert code == 0, output
        assert _recorded_calls(tmp_path) == [INSTALL_CALL, RUN_CALL]
        assert HINT_LINES[0] not in output


WINDOWS_SHELLS = [
    pytest.param('powershell', id='windows-powershell'),
    pytest.param(
        'pwsh',
        id='powershell-7',
        marks=pytest.mark.skipif(shutil.which('pwsh') is None, reason='PowerShell 7 (pwsh) is not installed'),
    ),
]


def _run_windows(
    tmp_path: Path, shell: str, answers: tuple[int, str, int], *, one_liner: bool = False,
) -> tuple[int, str]:
    """Run the PowerShell wrapper with a native uv recorder first on PATH.

    Args:
        tmp_path: The test's temporary directory, holding the stand-ins and the home.
        shell: The PowerShell executable to run the wrapper under.
        answers: How the recorder answers uv run and uv python find.
        one_liner: Run the wrapper's text through ``iex`` with the
            configuration in CLAUDE_CODE_TOOLBOX_ENV_CONFIG, as the
            documented one-liner does, instead of as a script with the
            configuration argument.

    Returns:
        The wrapper's exit code and its plain output.
    """
    fake_bin = tmp_path / 'fake-bin'
    fake_bin.mkdir()
    (fake_bin / 'uv.cmd').write_bytes(WINDOWS_UV_SHIM.encode('ascii'))
    home = tmp_path / 'home'
    home.mkdir()
    env = {**os.environ, **_recorder_environment(tmp_path, answers)}
    env['PATH'] = f'{fake_bin}{os.pathsep}{os.environ["PATH"]}'
    env['USERPROFILE'] = str(home)
    for variable in [name for name in env if name.startswith('CLAUDE_CODE_TOOLBOX_')]:
        del env[variable]
    if one_liner:
        env['CLAUDE_CODE_TOOLBOX_ENV_CONFIG'] = CONFIG
        invocation = f"iex (Get-Content -LiteralPath '{WINDOWS_WRAPPER}' -Raw)"
    else:
        invocation = f"& '{WINDOWS_WRAPPER}' '{CONFIG}'"
    command = f'{WINDOWS_DOWNLOAD_STAND_IN}\n{invocation}\nexit $LASTEXITCODE'
    # PowerShell writes its module analysis cache relative to the working
    # directory when the profile directories it expects are absent, so the
    # process runs inside the test's temporary directory
    result = subprocess.run(
        [shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', command],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    return result.returncode, _plain(result.stdout + result.stderr)


@pytest.mark.skipif(sys.platform != 'win32', reason='the PowerShell wrapper runs only on Windows')
@pytest.mark.parametrize('shell', WINDOWS_SHELLS)
class TestWindowsWrapperInterpreterHint:
    """The PowerShell wrapper names the interpreter repair only when uv cannot provide the interpreter."""

    def test_setup_failure_with_the_interpreter_available_prints_no_hint(self, shell: str, tmp_path: Path) -> None:
        """A failed setup is checked, the check passes, and the setup's exit code comes back unchanged."""
        code, output = _run_windows(tmp_path, shell, SETUP_FAILS)

        assert code == 1, output
        assert _recorded_calls(tmp_path) == [RUN_CALL, PROBE_CALL]
        assert 'setup failed' in output
        assert 'Failed to run setup' not in output, output
        for line in HINT_LINES:
            assert line not in output, output
        _assert_probe_output_discarded(output)

    @pytest.mark.parametrize('one_liner', [False, True], ids=['script', 'iex'])
    def test_missing_interpreter_names_the_repair(self, shell: str, one_liner: bool, tmp_path: Path) -> None:
        """uv's own error stays visible, the three hint lines print, and the exit code is uv run's."""
        code, output = _run_windows(tmp_path, shell, INTERPRETER_MISSING, one_liner=one_liner)

        assert code == 2, output
        expected_run = RUN_CALL[:-1] if one_liner else RUN_CALL
        assert _recorded_calls(tmp_path) == [expected_run, PROBE_CALL]
        assert MISSING_INTERPRETER in output
        assert '\n'.join(HINT_LINES) in output, output
        assert 'Failed to run setup' not in output, output
        _assert_probe_output_discarded(output)

    def test_successful_setup_runs_no_check(self, shell: str, tmp_path: Path) -> None:
        """A setup that succeeds never runs uv python find."""
        code, output = _run_windows(tmp_path, shell, SETUP_SUCCEEDS)

        assert code == 0, output
        assert _recorded_calls(tmp_path) == [RUN_CALL]
        assert HINT_LINES[0] not in output
