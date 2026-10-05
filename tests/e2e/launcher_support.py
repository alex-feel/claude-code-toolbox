"""Helpers for E2E tests that render profile launchers and run them.

The generated launchers and wrappers are run under their real interpreters
(bash, cmd.exe, PowerShell) with a stub ``claude`` first on PATH. The stub
records the CLAUDE_CONFIG_DIR it inherits, the marks the env loaders left,
the MSYS2_ARG_CONV_EXCL list it inherits, and every argument it receives, so
a test can check which profile directory a script actually reached and what
Claude Code is handed. On request it also starts Git Bash from its own
environment, the way a session's Bash tool does, and records what a native
program started from there receives.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.e2e.expected.launchers import DEFAULT_RENDERINGS
from tests.e2e.expected.launchers import GOLDEN_PROMPT
from tests.e2e.expected.launchers import LAUNCHER_PATH_TOKEN
from tests.e2e.shells import LOGIN_SHELL_INHERITED_PATH

# Launcher variants create_launcher_script() generates: (id, prompt file, mode).
LAUNCHER_VARIANTS = [
    pytest.param('no-prompt', None, 'replace', id='no-prompt'),
    pytest.param('prompt-replace', GOLDEN_PROMPT, 'replace', id='prompt-replace'),
    pytest.param('prompt-append', GOLDEN_PROMPT, 'append', id='prompt-append'),
]

# Git Bash location the generated CMD and PowerShell launchers look up first.
WINDOWS_GIT_BASH = Path(r'C:\Program Files\Git\bin\bash.exe')

# Variable the marking loaders append to: each loader adds its own mark.
LOADER_MARKS_VARIABLE = 'PROFILE_LOADER_MARKS'

# Variables that switch Git Bash argument conversion off; a launch starts
# without them unless a test hands them in.
PATH_CONVERSION_VARIABLES = ('MSYS2_ARG_CONV_EXCL', 'MSYS_NO_PATHCONV')

# Variable naming the bash the stub starts from its own environment; set, it
# makes the stub run the session probe below.
SESSION_BASH_VARIABLE = 'LAUNCHER_SESSION_BASH'

# POSIX path the session probe hands a native program from Git Bash, as the
# Bash tool of a session hands a script under /tmp to a native interpreter.
SESSION_PROBE_PATH = '/tmp/session-probe.py'


@dataclass(frozen=True)
class SessionProbe:
    """What a Git Bash started from the session's environment hands a native program.

    Attributes:
        received: SESSION_PROBE_PATH as the native program received it.
        converted: The Windows spelling ``cygpath -m`` gives SESSION_PROBE_PATH
            in the same environment.
    """

    received: str
    converted: str


@dataclass(frozen=True)
class LaunchRecord:
    """What the stub claude received when a generated script started it.

    Attributes:
        config_dir: The CLAUDE_CONFIG_DIR value in the stub's environment.
        loader_marks: The marks the env loaders appended, in sourcing order.
        conversion_exclusions: The MSYS2_ARG_CONV_EXCL value in the stub's
            environment, or None when the variable is unset.
        args: The command-line arguments, one per element.
        session_probe: What the stub's Git Bash child handed a native program,
            or None when the launch did not set SESSION_BASH_VARIABLE.
        cwd: The working directory the stub was started in, as the native
            program spells it.
    """

    config_dir: str
    loader_marks: str
    conversion_exclusions: str | None
    args: list[str]
    session_probe: SessionProbe | None
    cwd: str

    def value_after(self, flag: str) -> str:
        """Return the argument that follows flag.

        Args:
            flag: A flag the stub received.

        Returns:
            The argument right after the flag.
        """
        assert flag in self.args, f'{flag} missing from {self.args}'
        return self.args[self.args.index(flag) + 1]


@dataclass(frozen=True)
class ExpectedSpelling:
    """How generated scripts must spell a profile directory.

    Attributes:
        posix_dir: Spelling inside a double-quoted bash string.
        cmd_dir: Spelling inside a CMD ``set`` assignment.
        powershell_parent: PowerShell expression of the directory's parent.
    """

    posix_dir: str
    cmd_dir: str
    powershell_parent: str


def expected_spelling(profile_dir: Path, home: Path) -> ExpectedSpelling:
    """Spell a profile directory home-relative below home, absolute elsewhere.

    Args:
        profile_dir: The profile directory; its path holds no shell metacharacters.
        home: The home directory setup resolves.

    Returns:
        The spellings the generated scripts must use.
    """
    try:
        relative = profile_dir.relative_to(home)
    except ValueError:
        return ExpectedSpelling(
            posix_dir=profile_dir.as_posix(),
            cmd_dir=str(profile_dir).replace('/', '\\'),
            powershell_parent='"' + str(profile_dir.parent).replace('/', '\\') + '"',
        )
    parent_parts = relative.parts[:-1]
    return ExpectedSpelling(
        posix_dir='$HOME/' + '/'.join(relative.parts),
        cmd_dir='%USERPROFILE%\\' + '\\'.join(relative.parts),
        powershell_parent=(
            'Join-Path $env:USERPROFILE "' + '\\'.join(parent_parts) + '"' if parent_parts else '$env:USERPROFILE'
        ),
    )


def find_bash() -> str | None:
    """Locate a bash able to run the generated POSIX launcher.

    On Windows, plain which('bash') can resolve to the WSL shim, which cannot
    execute Windows paths; the Git Bash discovery of the module under test is
    authoritative there.

    Returns:
        Path to a usable bash executable, or None when unavailable.
    """
    if sys.platform == 'win32':
        from scripts.setup_environment import find_bash_windows

        return find_bash_windows()
    return shutil.which('bash')


def find_powershell() -> str | None:
    """Locate a PowerShell able to run and parse generated .ps1 files.

    Returns:
        Path to a PowerShell executable, or None when unavailable.
    """
    return shutil.which('pwsh') or shutil.which('powershell')


def require_empty_array_expansion(bash: str) -> None:
    """Skip the test when bash cannot start claude with an empty flag array.

    The Windows launch.sh runs under ``set -u`` and passes ``"${MCP_FLAGS[@]}"``
    and ``"${SOURCES[@]}"``, arrays that are empty when the profile has no
    mcp.json or the session starts outside the home folder. bash before 4.4
    reports an empty array as unbound there and stops, while Git Bash, the
    only shell the Windows launch.sh runs under, expands it to nothing. A
    bash a non-Windows runner provides, such as the macOS /bin/bash 3.2, can
    be older.

    Args:
        bash: The bash that runs the launchers.
    """
    completed = subprocess.run(
        [bash, '-c', 'set -u; flags=(); : "${flags[@]}"'],
        capture_output=True,
        check=False,
        timeout=60,
    )
    if completed.returncode != 0:
        pytest.skip(f'{bash} stops at an empty array under set -u, which Git Bash expands to nothing')


def _sh_single_quoted(value: str) -> str:
    """Quote a value for a POSIX shell so it stays one literal word.

    Args:
        value: The text to quote.

    Returns:
        The value in single quotes.
    """
    return "'" + value.replace("'", "'\\''") + "'"


def write_stub_claude(stub_dir: Path, record_file: Path) -> None:
    """Write a stub claude that records its environment and arguments.

    The stub is a shell script that hands its arguments to a recorder run by
    the test interpreter. On Windows that interpreter is a native program, so
    Git Bash converts the arguments and the environment on the way in exactly
    as it does when a launcher starts claude.exe, and the record holds what
    Claude Code itself would receive.

    When SESSION_BASH_VARIABLE names a bash, the recorder also starts that
    bash with the environment it inherited, has it hand SESSION_PROBE_PATH to
    the test interpreter, and records what arrived beside the ``cygpath -m``
    spelling of the path in the same environment.

    Args:
        stub_dir: Directory that receives the stub; prepended to PATH.
        record_file: File the stub writes its record to.
    """
    stub_dir.mkdir(parents=True, exist_ok=True)
    recorder = stub_dir / 'claude_recorder.py'
    recorder.write_text(
        'import json\n'
        'import os\n'
        'import subprocess\n'
        'import sys\n'
        '\n'
        "if sys.argv[1:2] == ['--version']:\n"
        "    print('2.1.0 (Claude Code)')\n"
        '    sys.exit(0)\n'
        'session_probe = None\n'
        f'bash = os.environ.get({SESSION_BASH_VARIABLE!r})\n'
        'if bash:\n'
        "    python = sys.executable.replace(os.sep, '/')\n"
        "    show_first_argument = 'import json, sys; print(json.dumps(sys.argv[1]))'\n"
        '    received = subprocess.run(\n'
        f"        [bash, '-c', 'exec \"$0\" -c \"$1\" {SESSION_PROBE_PATH}', python, show_first_argument],\n"
        '        capture_output=True, text=True, check=True,\n'
        '    ).stdout\n'
        '    converted = subprocess.run(\n'
        f"        [bash, '-c', 'cygpath -m {SESSION_PROBE_PATH}'], capture_output=True, text=True, check=True,\n"
        '    ).stdout\n'
        "    session_probe = {'received': json.loads(received), 'converted': converted.strip()}\n"
        'record = {\n'
        "    'config_dir': os.environ.get('CLAUDE_CONFIG_DIR', ''),\n"
        f"    'loader_marks': os.environ.get({LOADER_MARKS_VARIABLE!r}, ''),\n"
        "    'conversion_exclusions': os.environ.get('MSYS2_ARG_CONV_EXCL'),\n"
        "    'args': sys.argv[1:],\n"
        "    'session_probe': session_probe,\n"
        "    'cwd': os.getcwd(),\n"
        '}\n'
        f"with open({str(record_file)!r}, 'w', encoding='utf-8') as handle:\n"
        '    json.dump(record, handle)\n',
        encoding='utf-8',
    )
    stub = stub_dir / 'claude'
    stub.write_text(
        '#!/bin/sh\n'
        f'exec {_sh_single_quoted(Path(sys.executable).as_posix())} {_sh_single_quoted(recorder.as_posix())} "$@"\n',
        encoding='utf-8',
        newline='\n',
    )
    stub.chmod(0o755)


def write_marking_loaders(profile_dir: Path) -> None:
    """Write env loaders that each append their own mark when sourced.

    The marks show which loader a script found at the path it names:
    ``sh;`` from env.sh, ``cmd;`` from env.cmd and ``ps1;`` from env.ps1.

    Args:
        profile_dir: The profile directory the loaders belong to.
    """
    profile_dir.mkdir(parents=True, exist_ok=True)
    name = LOADER_MARKS_VARIABLE
    (profile_dir / 'env.sh').write_text(f'export {name}="${{{name}:-}}sh;"\n', encoding='utf-8', newline='\n')
    (profile_dir / 'env.cmd').write_text(f'@echo off\nset "{name}=%{name}%cmd;"\n', encoding='utf-8')
    (profile_dir / 'env.ps1').write_text(f'$env:{name} = "$env:{name}" + \'ps1;\'\n', encoding='utf-8')


def seed_profile(profile_dir: Path, prompt: str | None, *, mcp: bool = True) -> None:
    """Create the files a launcher reads from its profile directory.

    Args:
        profile_dir: The profile directory.
        prompt: The system prompt file name, or None.
        mcp: Whether the profile holds an mcp.json; without one the launcher
            passes no MCP flags.
    """
    (profile_dir / 'prompts').mkdir(parents=True, exist_ok=True)
    (profile_dir / 'config.json').write_text('{}', encoding='utf-8')
    if mcp:
        (profile_dir / 'mcp.json').write_text('{"mcpServers": {}}', encoding='utf-8')
    if prompt is not None:
        (profile_dir / 'prompts' / prompt).write_text('Probe prompt.\n', encoding='utf-8')


def launch(
    command: list[str] | str,
    *,
    home: Path,
    stub_dir: Path,
    extra_path: Path | None = None,
    extra_env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> LaunchRecord:
    """Run a generated script with the stub claude first on PATH.

    The script starts without the variables that switch Git Bash argument
    conversion off, so the conversion a test observes does not depend on the
    environment the test suite runs in, and without the PATH an outer Git
    Bash login shell recorded, so the login shell a Windows entry point
    starts keeps the stub first on PATH.

    Args:
        command: The command line that runs the script; a string is handed to
            the OS verbatim, which cmd.exe quoting needs.
        home: The home directory the script sees at run time.
        stub_dir: Directory holding the stub claude.
        extra_path: Directory appended to PATH, such as ~/.local/bin.
        extra_env: Variables the script inherits on top of the test environment.
        cwd: The working directory of the launch; the test's own when omitted.

    Returns:
        What the stub claude received.
    """
    record_file = stub_dir / 'record.json'
    record_file.unlink(missing_ok=True)
    write_stub_claude(stub_dir, record_file)
    dropped = {
        'CLAUDE_CONFIG_DIR', LOADER_MARKS_VARIABLE, SESSION_BASH_VARIABLE, LOGIN_SHELL_INHERITED_PATH,
        *PATH_CONVERSION_VARIABLES,
    }
    env = {key: value for key, value in os.environ.items() if key not in dropped}
    env['HOME'] = str(home)
    env['USERPROFILE'] = str(home)
    env['PATH'] = f'{stub_dir}{os.pathsep}' + env.get('PATH', '')
    if extra_path is not None:
        env['PATH'] += f'{os.pathsep}{extra_path}'
    env.update(extra_env or {})

    completed = subprocess.run(
        command, capture_output=True, text=True, encoding='utf-8', errors='replace', check=False, timeout=120, env=env,
        cwd=cwd,
    )

    assert completed.returncode == 0, (
        f'{command} failed with {completed.returncode}:\nstdout: {completed.stdout}\nstderr: {completed.stderr}'
    )
    assert record_file.exists(), f'stub claude was never invoked:\nstdout: {completed.stdout}\nstderr: {completed.stderr}'
    record = json.loads(record_file.read_text(encoding='utf-8'))
    probe = record['session_probe']
    return LaunchRecord(
        config_dir=record['config_dir'],
        loader_marks=record['loader_marks'],
        conversion_exclusions=record['conversion_exclusions'],
        args=record['args'],
        session_probe=None if probe is None else SessionProbe(received=probe['received'], converted=probe['converted']),
        cwd=record['cwd'],
    )


def cmd_command(script: Path, *args: str) -> str:
    """Build a cmd.exe command line that runs a batch file with arguments.

    ``/s`` makes cmd.exe strip only the outer quote pair, so a script path
    holding spaces and parentheses survives.

    Args:
        script: The batch file.
        *args: Arguments for the batch file.

    Returns:
        The command line for subprocess.
    """
    return f'cmd.exe /d /s /c ""{script}" {" ".join(args)}"'


def powershell_command(powershell: str, script: Path, *args: str) -> list[str]:
    """Build a PowerShell command line that runs a script file with arguments.

    Args:
        powershell: The PowerShell executable.
        script: The .ps1 file.
        *args: Arguments for the script.

    Returns:
        The command line for subprocess.
    """
    return [powershell, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(script), *args]


def same_path(value: str, expected: Path) -> bool:
    """Return True when a recorded path names the expected file or directory.

    Args:
        value: A path the stub recorded.
        expected: The path it must name.

    Returns:
        Whether both resolve to the same location.
    """
    return Path(value).resolve() == expected.resolve()


def assert_reaches_profile(record: LaunchRecord, profile_dir: Path, prompt: str | None, *, mcp: bool = True) -> None:
    """Assert that a launch used every file of profile_dir and nothing else.

    Args:
        record: What the stub claude received.
        profile_dir: The profile directory the launch must use.
        prompt: The system prompt file name, or None.
        mcp: Whether the profile holds an mcp.json; without one the launch
            must pass no MCP flags.
    """
    assert same_path(record.config_dir, profile_dir), f'CLAUDE_CONFIG_DIR={record.config_dir}'
    assert same_path(record.value_after('--settings'), profile_dir / 'config.json'), record.args
    if mcp:
        assert '--strict-mcp-config' in record.args, record.args
        assert same_path(record.value_after('--mcp-config'), profile_dir / 'mcp.json'), record.args
    else:
        assert '--strict-mcp-config' not in record.args, record.args
        assert '--mcp-config' not in record.args, record.args
    if prompt is not None:
        prompt_flags = [arg for arg in record.args if arg in {'--system-prompt-file', '--append-system-prompt-file'}]
        assert len(prompt_flags) == 1, record.args
        assert same_path(record.value_after(prompt_flags[0]), profile_dir / 'prompts' / prompt), record.args
    assert '--probe-arg' in record.args, record.args


def expected_bytes(text: str, *, lf_pinned: bool) -> bytes:
    """Encode an expected rendering the way setup writes it on this host.

    Files setup writes with ``newline='\\n'`` keep LF line endings on every
    host; the rest use the host's line separator.

    Args:
        text: Expected file content with LF line endings.
        lf_pinned: Whether setup pins the file to LF line endings.

    Returns:
        The exact bytes the file must contain.
    """
    newline = '\n' if lf_pinned else os.linesep
    return text.replace('\n', newline).encode('utf-8')


def assert_default_rendering(path: Path, key: str, *, lf_pinned: bool, launcher_path: Path | None = None) -> None:
    """Assert that a generated file matches its default-layout rendering byte for byte.

    Args:
        path: The generated file.
        key: The DEFAULT_RENDERINGS key of its expected content.
        lf_pinned: Whether setup pins the file to LF line endings.
        launcher_path: The start.ps1 path substituted for LAUNCHER_PATH_TOKEN.
    """
    expected = DEFAULT_RENDERINGS[key]
    if launcher_path is not None:
        expected = expected.replace(LAUNCHER_PATH_TOKEN, str(launcher_path))
    actual = path.read_bytes()
    assert actual == expected_bytes(expected, lf_pinned=lf_pinned), (
        f'{path.name} differs from the default rendering {key!r}:\n'
        f'--- expected ---\n{expected}\n--- actual ---\n{actual.decode("utf-8", "replace")}'
    )
