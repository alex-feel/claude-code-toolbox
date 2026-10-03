"""Helpers for E2E tests that render profile launchers and run them.

The generated launchers and wrappers are run under their real interpreters
(bash, cmd.exe, PowerShell) with a stub ``claude`` first on PATH. The stub
records the CLAUDE_CONFIG_DIR it inherits, the marks the env loaders left,
and every argument it receives, so a test can check which profile directory
a script actually reached.
"""

from __future__ import annotations

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


@dataclass(frozen=True)
class LaunchRecord:
    """What the stub claude received when a generated script started it.

    Attributes:
        config_dir: The CLAUDE_CONFIG_DIR value in the stub's environment.
        loader_marks: The marks the env loaders appended, in sourcing order.
        args: The command-line arguments, one per element.
    """

    config_dir: str
    loader_marks: str
    args: list[str]

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


def write_stub_claude(stub_dir: Path, record_file: Path) -> None:
    """Write a stub claude that records its environment and arguments.

    On Windows, POSIX-form paths are converted with cygpath so the record
    holds host paths whichever form the launcher passed.

    Args:
        stub_dir: Directory that receives the stub; prepended to PATH.
        record_file: File the stub writes its record to.
    """
    stub_dir.mkdir(parents=True, exist_ok=True)
    stub = stub_dir / 'claude'
    stub.write_text(
        '#!/bin/sh\n'
        'if [ "$1" = "--version" ]; then echo "2.1.0 (Claude Code)"; exit 0; fi\n'
        'to_host() {\n'
        '  case "$1" in\n'
        '    /*) if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; return; fi ;;\n'
        '  esac\n'
        "  printf '%s\\n' \"$1\"\n"
        '}\n'
        '{\n'
        '  printf \'CLAUDE_CONFIG_DIR=%s\\n\' "$(to_host "${CLAUDE_CONFIG_DIR:-}")"\n'
        f'  printf \'LOADER_MARKS=%s\\n\' "${{{LOADER_MARKS_VARIABLE}:-}}"\n'
        '  for arg in "$@"; do printf \'ARG=%s\\n\' "$(to_host "$arg")"; done\n'
        '} > "' + record_file.as_posix() + '"\n',
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


def seed_profile(profile_dir: Path, prompt: str | None) -> None:
    """Create the files a launcher reads from its profile directory.

    Args:
        profile_dir: The profile directory.
        prompt: The system prompt file name, or None.
    """
    (profile_dir / 'prompts').mkdir(parents=True, exist_ok=True)
    (profile_dir / 'config.json').write_text('{}', encoding='utf-8')
    (profile_dir / 'mcp.json').write_text('{"mcpServers": {}}', encoding='utf-8')
    if prompt is not None:
        (profile_dir / 'prompts' / prompt).write_text('Probe prompt.\n', encoding='utf-8')


def launch(command: list[str] | str, *, home: Path, stub_dir: Path, extra_path: Path | None = None) -> LaunchRecord:
    """Run a generated script with the stub claude first on PATH.

    Args:
        command: The command line that runs the script; a string is handed to
            the OS verbatim, which cmd.exe quoting needs.
        home: The home directory the script sees at run time.
        stub_dir: Directory holding the stub claude.
        extra_path: Directory appended to PATH, such as ~/.local/bin.

    Returns:
        What the stub claude received.
    """
    record_file = stub_dir / 'record.txt'
    record_file.unlink(missing_ok=True)
    write_stub_claude(stub_dir, record_file)
    env = {key: value for key, value in os.environ.items() if key not in {'CLAUDE_CONFIG_DIR', LOADER_MARKS_VARIABLE}}
    env['HOME'] = str(home)
    env['USERPROFILE'] = str(home)
    env['PATH'] = f'{stub_dir}{os.pathsep}' + env.get('PATH', '')
    if extra_path is not None:
        env['PATH'] += f'{os.pathsep}{extra_path}'

    completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=120, env=env)

    assert completed.returncode == 0, (
        f'{command} failed with {completed.returncode}:\nstdout: {completed.stdout}\nstderr: {completed.stderr}'
    )
    assert record_file.exists(), f'stub claude was never invoked:\nstdout: {completed.stdout}\nstderr: {completed.stderr}'
    lines = record_file.read_text(encoding='utf-8').splitlines()
    fields = dict(line.split('=', 1) for line in lines if not line.startswith('ARG='))
    return LaunchRecord(
        config_dir=fields['CLAUDE_CONFIG_DIR'],
        loader_marks=fields['LOADER_MARKS'],
        args=[line.removeprefix('ARG=') for line in lines if line.startswith('ARG=')],
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


def assert_reaches_profile(record: LaunchRecord, profile_dir: Path, prompt: str | None) -> None:
    """Assert that a launch used every file of profile_dir and nothing else.

    Args:
        record: What the stub claude received.
        profile_dir: The profile directory the launch must use.
        prompt: The system prompt file name, or None.
    """
    assert same_path(record.config_dir, profile_dir), f'CLAUDE_CONFIG_DIR={record.config_dir}'
    assert same_path(record.value_after('--settings'), profile_dir / 'config.json'), record.args
    assert '--strict-mcp-config' in record.args, record.args
    assert same_path(record.value_after('--mcp-config'), profile_dir / 'mcp.json'), record.args
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
