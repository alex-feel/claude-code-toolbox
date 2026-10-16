"""E2E tests for the interpreter hint the platform bootstrap wrappers print when uv run fails.

Both kinds of wrapper -- ``setup-environment``, which runs the environment
setup, and ``install-claude``, which runs the Claude Code installer -- start
their Python script with ``uv run``. When it exits non-zero, each wrapper asks
``uv python find`` whether uv can provide the Python version the script runs
on, with the check's output discarded. Only when the check fails too does the
wrapper name the repair, ``uv python install --reinstall``; in every case it
exits with the code ``uv run`` returned. A recording stand-in for uv answers
each call the way a test asks and writes every argument vector it receives to
a file. On Linux and macOS the bash wrappers run for real with that stand-in
and a curl stand-in. On Windows the stand-in is a native command (a ``uv.cmd``
first on PATH), so Windows PowerShell treats the check's stderr as it treats
real uv's, and the wrapper runs as a script and through ``iex``, the
documented one-liner.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

import pytest

from tests.e2e.bootstrap_wrapper_support import UNIX_WRAPPERS
from tests.e2e.bootstrap_wrapper_support import WINDOWS_INSTALL_WRAPPER
from tests.e2e.bootstrap_wrapper_support import WINDOWS_SETUP_WRAPPER
from tests.e2e.bootstrap_wrapper_support import run_unix_wrapper
from tests.e2e.bootstrap_wrapper_support import unix_install_wrapper
from tests.e2e.bootstrap_wrapper_support import unix_setup_wrapper

_ANSI_SEQUENCE = re.compile(r'\x1b\[[0-9;]*m')

# The Python version the wrappers run their scripts on
WRAPPER_PYTHON = '3.12'
CONFIG = 'profile.yaml'
PROBE_CALL = ['python', 'find', WRAPPER_PYTHON]
INSTALL_CALL = ['python', 'install', WRAPPER_PYTHON]
MISSING_INTERPRETER = r'error: Python interpreter not found at C:\uv\python\cpython-3.12.15\python.exe'
SCRIPT_FAILED = 'the script failed'
PROBE_STDOUT = 'probe output on stdout'
PROBE_STDERR = 'probe output on stderr'


@dataclass(frozen=True)
class WrapperKind:
    """One kind of bootstrap wrapper: the script it runs and how its hint names that script.

    Attributes:
        unix_wrapper: Returns the bash wrapper of a Unix platform directory.
        windows_wrapper: The PowerShell wrapper.
        script: The file name of the Python script ``uv run`` starts.
        runs_on: What the hint says runs on the interpreter.
        command: The command the hint says to run again.
        arguments: The arguments the wrapper receives in a test.
        windows_error_line: The start of the line the PowerShell wrapper
            prints when the wrapper itself throws, which a failed ``uv run``
            never reaches.
        one_liner_environment: The variables the documented ``iex``
            one-liner sets in place of those arguments.
        unix_installs_python: Whether the bash wrapper runs ``uv python
            install`` before ``uv run``.
        unix_failure_line: The line the bash wrapper prints when ``uv run``
            fails, if it prints one.
    """

    unix_wrapper: Callable[[str], Path]
    windows_wrapper: Path
    script: str
    runs_on: str
    command: str
    arguments: tuple[str, ...]
    windows_error_line: str
    one_liner_environment: dict[str, str] = field(default_factory=dict)
    unix_installs_python: bool = False
    unix_failure_line: str | None = None

    @property
    def hint_lines(self) -> tuple[str, str, str]:
        """The three lines that name the repair, in order."""
        return (
            f'[FAIL] uv cannot provide Python {WRAPPER_PYTHON}, which {self.runs_on} runs on.',
            f'[FAIL] Install it with: uv python install --reinstall {WRAPPER_PYTHON}',
            (
                f'[FAIL] This installs Python {WRAPPER_PYTHON}, or replaces a uv-managed copy whose files are missing; '
                f'then run this {self.command} command again.'
            ),
        )

    def run_call(self, *, one_liner: bool = False) -> list[str]:
        """The ``uv run`` call, its script argument reduced to the file name."""
        arguments = [] if one_liner else list(self.arguments)
        return ['run', '--no-project', '--python', WRAPPER_PYTHON, self.script, *arguments]

    def unix_calls(self, *, probed: bool) -> list[list[str]]:
        """Every call the bash wrapper makes, in order."""
        calls = [INSTALL_CALL] if self.unix_installs_python else []
        calls.append(self.run_call())
        if probed:
            calls.append(PROBE_CALL)
        return calls


SETUP = WrapperKind(
    unix_wrapper=unix_setup_wrapper,
    windows_wrapper=WINDOWS_SETUP_WRAPPER,
    script='setup_environment.py',
    runs_on='the setup',
    command='setup',
    arguments=(CONFIG,),
    windows_error_line='[FAIL] Failed to run setup',
    one_liner_environment={'CLAUDE_CODE_TOOLBOX_ENV_CONFIG': CONFIG},
    unix_installs_python=True,
)
INSTALL = WrapperKind(
    unix_wrapper=unix_install_wrapper,
    windows_wrapper=WINDOWS_INSTALL_WRAPPER,
    script='install_claude.py',
    runs_on='the installer',
    command='install',
    arguments=(),
    windows_error_line='[FAIL] Failed to run installer',
    unix_failure_line='[FAIL] Installation failed',
)
WRAPPER_KINDS = [pytest.param(SETUP, id='setup'), pytest.param(INSTALL, id='install')]

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
SCRIPT_FAILS = (1, SCRIPT_FAILED, 0)
INTERPRETER_MISSING = (2, MISSING_INTERPRETER, 2)
SCRIPT_SUCCEEDS = (0, '', 0)


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
    """Return every argument vector the uv stand-in received, in order.

    The bash installer wrapper runs its script from a fresh temporary
    directory and the PowerShell one from a directory in the home, so the
    path of a script argument is reduced to its file name.

    Returns:
        The recorded argument vectors, script paths reduced to file names.
    """
    calls = tmp_path / 'uv-calls.jsonl'
    return [
        [Path(argument).name if argument.endswith('.py') else argument for argument in json.loads(line)]
        for line in calls.read_text(encoding='utf-8').splitlines()
    ]


def _plain(output: str) -> str:
    """Strip color codes and Windows line endings from a wrapper's output."""
    return _ANSI_SEQUENCE.sub('', output).replace('\r\n', '\n')


def _assert_probe_output_discarded(output: str) -> None:
    """The check's own output never reaches the wrapper's output."""
    assert PROBE_STDOUT not in output, output
    assert PROBE_STDERR not in output, output


def _run_unix(
    tmp_path: Path, kind: WrapperKind, platform_dir: str, answers: tuple[int, str, int],
) -> tuple[int, str]:
    """Run a bash wrapper with the uv recorder and return its exit code and plain output."""
    result = run_unix_wrapper(
        tmp_path, kind.unix_wrapper(platform_dir), list(kind.arguments), _recorder_environment(tmp_path, answers),
        uv_stand_in=UNIX_UV_SHIM,
    )
    return result.returncode, _plain(result.stdout + result.stderr)


@pytest.mark.parametrize('kind', WRAPPER_KINDS)
@pytest.mark.parametrize('platform_dir', UNIX_WRAPPERS)
class TestUnixWrapperInterpreterHint:
    """The bash wrappers name the interpreter repair only when uv cannot provide the interpreter."""

    def test_run_failure_with_the_interpreter_available_prints_no_hint(
        self, platform_dir: str, kind: WrapperKind, tmp_path: Path,
    ) -> None:
        """A failed run is checked, the check passes, and the script's exit code comes back unchanged."""
        code, output = _run_unix(tmp_path, kind, platform_dir, SCRIPT_FAILS)

        assert code == 1, output
        assert _recorded_calls(tmp_path) == kind.unix_calls(probed=True)
        assert SCRIPT_FAILED in output
        if kind.unix_failure_line:
            assert kind.unix_failure_line in output, output
        for line in kind.hint_lines:
            assert line not in output, output
        _assert_probe_output_discarded(output)

    def test_missing_interpreter_names_the_repair(self, platform_dir: str, kind: WrapperKind, tmp_path: Path) -> None:
        """uv's own error stays visible, the three hint lines print, and the exit code is uv run's."""
        code, output = _run_unix(tmp_path, kind, platform_dir, INTERPRETER_MISSING)

        assert code == 2, output
        assert _recorded_calls(tmp_path) == kind.unix_calls(probed=True)
        assert MISSING_INTERPRETER in output
        assert '\n'.join(kind.hint_lines) in output, output
        if kind.unix_failure_line:
            assert kind.unix_failure_line in output, output
        _assert_probe_output_discarded(output)

    def test_successful_run_runs_no_check(self, platform_dir: str, kind: WrapperKind, tmp_path: Path) -> None:
        """A script that succeeds never runs uv python find."""
        code, output = _run_unix(tmp_path, kind, platform_dir, SCRIPT_SUCCEEDS)

        assert code == 0, output
        assert _recorded_calls(tmp_path) == kind.unix_calls(probed=False)
        assert kind.hint_lines[0] not in output
        if kind.unix_failure_line:
            assert kind.unix_failure_line not in output, output


WINDOWS_SHELLS = [
    pytest.param('powershell', id='windows-powershell'),
    pytest.param(
        'pwsh',
        id='powershell-7',
        marks=pytest.mark.skipif(shutil.which('pwsh') is None, reason='PowerShell 7 (pwsh) is not installed'),
    ),
]


def _run_windows(
    tmp_path: Path, kind: WrapperKind, shell: str, answers: tuple[int, str, int], *, one_liner: bool = False,
) -> tuple[int, str]:
    """Run a PowerShell wrapper with a native uv recorder first on PATH.

    Args:
        tmp_path: The test's temporary directory, holding the stand-ins and the home.
        kind: The wrapper to run.
        shell: The PowerShell executable to run the wrapper under.
        answers: How the recorder answers uv run and uv python find.
        one_liner: Run the wrapper's text through ``iex`` with the
            variables the documented one-liner sets, instead of as a script
            with the wrapper's arguments.

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
        env.update(kind.one_liner_environment)
        invocation = f"iex (Get-Content -LiteralPath '{kind.windows_wrapper}' -Raw)"
    else:
        quoted_arguments = ''.join(f" '{argument}'" for argument in kind.arguments)
        invocation = f"& '{kind.windows_wrapper}'{quoted_arguments}"
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


@pytest.mark.skipif(sys.platform != 'win32', reason='the PowerShell wrappers run only on Windows')
@pytest.mark.parametrize('kind', WRAPPER_KINDS)
@pytest.mark.parametrize('shell', WINDOWS_SHELLS)
class TestWindowsWrapperInterpreterHint:
    """The PowerShell wrappers name the interpreter repair only when uv cannot provide the interpreter."""

    def test_run_failure_with_the_interpreter_available_prints_no_hint(
        self, shell: str, kind: WrapperKind, tmp_path: Path,
    ) -> None:
        """A failed run is checked, the check passes, and the script's exit code comes back unchanged."""
        code, output = _run_windows(tmp_path, kind, shell, SCRIPT_FAILS)

        assert code == 1, output
        assert _recorded_calls(tmp_path) == [kind.run_call(), PROBE_CALL]
        assert SCRIPT_FAILED in output
        assert kind.windows_error_line not in output, output
        for line in kind.hint_lines:
            assert line not in output, output
        _assert_probe_output_discarded(output)

    @pytest.mark.parametrize('one_liner', [False, True], ids=['script', 'iex'])
    def test_missing_interpreter_names_the_repair(
        self, shell: str, kind: WrapperKind, one_liner: bool, tmp_path: Path,
    ) -> None:
        """uv's own error stays visible, the three hint lines print, and the exit code is uv run's."""
        code, output = _run_windows(tmp_path, kind, shell, INTERPRETER_MISSING, one_liner=one_liner)

        assert code == 2, output
        assert _recorded_calls(tmp_path) == [kind.run_call(one_liner=one_liner), PROBE_CALL]
        assert MISSING_INTERPRETER in output
        assert '\n'.join(kind.hint_lines) in output, output
        assert kind.windows_error_line not in output, output
        _assert_probe_output_discarded(output)

    def test_successful_run_runs_no_check(self, shell: str, kind: WrapperKind, tmp_path: Path) -> None:
        """A script that succeeds never runs uv python find."""
        code, output = _run_windows(tmp_path, kind, shell, SCRIPT_SUCCEEDS)

        assert code == 0, output
        assert _recorded_calls(tmp_path) == [kind.run_call()]
        assert kind.hint_lines[0] not in output
