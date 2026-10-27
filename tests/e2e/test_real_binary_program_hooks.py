"""E2E tests proving that the real Claude Code binary runs a program hook found on PATH.

A configuration wires the hook commands an installed tool ships by naming
the program, not a hooks.files script, in exec form: the setup writes the
command verbatim as the executable and args as its whole argument list.
These tests install such a program the way a tool reaches a machine -- a
console script uv installs from a wheel, a native launcher executable on
Windows and an executable script elsewhere, under a name unique to the
test -- write config.json with the toolbox's own create_profile_config(),
and run one non-interactive turn of the real binary against an offline fake
API with that config.json passed through --settings, as the launcher of an
installed profile passes it.

The program appends one line per run to a marker file: the arguments it
received and the hook_event_name of the JSON Claude Code wrote to its
standard input. With the program's directory on PATH, the UserPromptSubmit
and Stop hooks both run with their declared arguments; with the same
config.json and the directory left off PATH, the name resolves nowhere,
nothing runs, and the turn still completes, because a hook that cannot
start is a non-blocking error.

Skipped when the binary is absent; CLAUDE_CODE_TOOLBOX_REQUIRE_REAL_BINARY=1
(set in CI) turns absence into a failure instead of a silent skip.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from scripts import setup_environment
from tests.e2e import linked_entries_support as support
from tests.e2e.fake_anthropic_api import FakeAnthropicServer

_REQUIRE_REAL_BINARY = os.environ.get('CLAUDE_CODE_TOOLBOX_REQUIRE_REAL_BINARY') == '1'
_PROFILE_NAME = 'e2e-program-hooks'
_PROMPT = 'Reply with the single word READY.'
_PROMPT_SUBMIT_ARGS = ['hook', 'prompt-submit']
_STOP_ARGS = ['hook', 'stop']

pytestmark = [
    pytest.mark.real_binary,
    pytest.mark.skipif(
        support.CLAUDE_CMD is None and not _REQUIRE_REAL_BINARY,
        reason='claude binary not available',
    ),
]

# The program's module: it records its arguments and the event named in the
# hook input Claude Code writes to its standard input
_PROGRAM_SOURCE = '''\
import json
import sys

MARKER = {marker!r}


def main() -> None:
    payload = json.loads(sys.stdin.read())
    record = {{'args': sys.argv[1:], 'event': payload.get('hook_event_name')}}
    with open(MARKER, 'a', encoding='utf-8') as handle:
        handle.write(json.dumps(record) + '\\n')
'''


def _record_row(name: str, data: bytes) -> str:
    """Return the RECORD row of one wheel member."""
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode('ascii')
    return f'{name},sha256={digest},{len(data)}'


def _build_wheel(directory: Path, program: str, module: str, marker: Path) -> Path:
    """Build a wheel whose only console script is ``program``, running ``module``.main().

    Args:
        directory: Where the wheel is written.
        program: The console script's name.
        module: The importable module name, also the distribution name.
        marker: The file the program appends its records to.

    Returns:
        The wheel's path.
    """
    dist_info = f'{module}-0.0.0.dist-info'
    members = {
        f'{module}.py': _PROGRAM_SOURCE.format(marker=str(marker)),
        f'{dist_info}/METADATA': f'Metadata-Version: 2.1\nName: {module}\nVersion: 0.0.0\n',
        f'{dist_info}/WHEEL': 'Wheel-Version: 1.0\nGenerator: e2e\nRoot-Is-Purelib: true\nTag: py3-none-any\n',
        f'{dist_info}/entry_points.txt': f'[console_scripts]\n{program} = {module}:main\n',
    }
    rows = [_record_row(name, text.encode('utf-8')) for name, text in members.items()]
    rows.append(f'{dist_info}/RECORD,,')
    wheel = directory / f'{module}-0.0.0-py3-none-any.whl'
    with zipfile.ZipFile(wheel, 'w') as archive:
        for name, text in members.items():
            archive.writestr(name, text)
        archive.writestr(f'{dist_info}/RECORD', '\n'.join(rows) + '\n')
    return wheel


def install_program(directory: Path, program: str, marker: Path) -> Path:
    """Install ``program`` as a console script into a fresh virtual environment, offline.

    uv writes the console script the way it writes any installed tool's
    entry point: a native launcher executable on Windows, an executable
    script with a shebang elsewhere.

    Args:
        directory: An empty directory for the wheel, the environment and uv's cache.
        program: The program's name.
        marker: The file the program appends its records to.

    Returns:
        The environment's scripts directory, which holds the program.
    """
    uv = shutil.which('uv')
    assert uv is not None, 'the suite runs under uv, so uv is on PATH'
    directory.mkdir(parents=True)
    env = {key: value for key, value in os.environ.items() if key != 'VIRTUAL_ENV'}
    env.update({'UV_CACHE_DIR': str(directory / 'uv-cache'), 'UV_PYTHON_DOWNLOADS': 'never'})
    wheel = _build_wheel(directory, program, program.replace('-', '_'), marker)
    venv = directory / 'venv'
    scripts = venv / ('Scripts' if sys.platform == 'win32' else 'bin')
    python = scripts / ('python.exe' if sys.platform == 'win32' else 'python')
    for command in (
        [uv, 'venv', str(venv), '--python', sys.executable, '--no-config'],
        [uv, 'pip', 'install', '--python', str(python), '--offline', '--no-config', str(wheel)],
    ):
        completed = subprocess.run(
            command, cwd=directory, env=env, capture_output=True, text=True, check=False, timeout=120,
        )
        assert completed.returncode == 0, f'{command}\n{completed.stdout}\n{completed.stderr}'
    executable = scripts / (f'{program}.exe' if sys.platform == 'win32' else program)
    assert executable.is_file(), sorted(path.name for path in scripts.iterdir())
    return scripts


@dataclass
class ProgramWorkspace:
    """An isolated home, a profile whose config.json wires the program, and the fake API."""

    home: Path
    config_dir: Path
    project_dir: Path
    marker: Path
    program: str
    scripts: Path
    server: FakeAnthropicServer

    def hooks(self) -> dict[str, Any]:
        """The YAML hooks section: the program on UserPromptSubmit and on Stop, in exec form."""
        return {
            'events': [
                {'event': 'UserPromptSubmit', 'type': 'command', 'command': self.program, 'args': _PROMPT_SUBMIT_ARGS},
                {
                    'event': 'Stop', 'type': 'command', 'command': self.program, 'args': _STOP_ARGS,
                    'async-rewake': True, 'timeout': 86400,
                },
            ],
        }

    def run(self, *, program_on_path: bool) -> support.ClaudeRun:
        """Run one turn with config.json passed through --settings.

        Args:
            program_on_path: Whether the program's directory leads PATH.

        Returns:
            The parsed run.
        """
        assert support.CLAUDE_CMD is not None
        env = support.claude_child_env(
            config_dir=self.config_dir, home=self.home, api_url=self.server.url, claude_cmd=support.CLAUDE_CMD,
        )
        if program_on_path:
            env['PATH'] = os.pathsep.join([str(self.scripts), env['PATH']])
        found = shutil.which(self.program, path=env['PATH'])
        assert (found is not None) is program_on_path, found
        settings = ['--settings', str(self.config_dir / 'config.json')]
        argv = [str(support.CLAUDE_CMD), *support.print_args(_PROMPT, *settings)]
        return support.run_stream_json(argv, env=env, cwd=self.project_dir, server=self.server)

    def records(self) -> list[dict[str, Any]]:
        """Return the lines the program appended, oldest first."""
        if not self.marker.is_file():
            return []
        return [json.loads(line) for line in self.marker.read_text(encoding='utf-8').splitlines() if line]


@pytest.fixture
def workspace(tmp_path: Path) -> Iterator[ProgramWorkspace]:
    """Provide the program, a profile whose config.json the toolbox wrote, and a running fake API."""
    root, cleanup = support.workspace_root(tmp_path)
    try:
        home = root / 'home'
        config_dir = home / '.claude' / _PROFILE_NAME
        config_dir.mkdir(parents=True)
        project_dir = root / 'project'
        project_dir.mkdir()
        marker = root / 'program_marker.jsonl'
        program = f'cct-e2e-hook-program-{uuid.uuid4().hex[:8]}'
        scripts = install_program(root / 'program', program, marker)
        server = FakeAnthropicServer().start()
        try:
            workspace = ProgramWorkspace(
                home=home, config_dir=config_dir, project_dir=project_dir, marker=marker,
                program=program, scripts=scripts, server=server,
            )
            hooks = workspace.hooks()
            assert setup_environment.validate_hooks_files_consistency({'hooks': hooks}) == []
            assert setup_environment.create_profile_config({'hooks': hooks}, config_dir)
            support.seed_global_config(config_dir, project_dir)
            yield workspace
        finally:
            server.stop()
    finally:
        cleanup()


def test_config_json_names_the_program_verbatim(workspace: ProgramWorkspace) -> None:
    """config.json runs the bare program name with exactly the declared args and keys."""
    hooks = json.loads((workspace.config_dir / 'config.json').read_text(encoding='utf-8'))['hooks']

    assert hooks == {
        'UserPromptSubmit': [{
            'matcher': '',
            'hooks': [{'type': 'command', 'command': workspace.program, 'args': _PROMPT_SUBMIT_ARGS}],
        }],
        'Stop': [{
            'matcher': '',
            'hooks': [{
                'type': 'command', 'command': workspace.program, 'args': _STOP_ARGS,
                'asyncRewake': True, 'timeout': 86400,
            }],
        }],
    }


def test_program_on_path_runs_with_its_args(workspace: ProgramWorkspace) -> None:
    """Claude Code finds the program on PATH and runs it for each event with its args and the hook input."""
    run = workspace.run(program_on_path=True)

    assert run.returncode == 0, run.describe()
    assert len(run.bodies) == 1, run.describe()
    assert workspace.records() == [
        {'args': _PROMPT_SUBMIT_ARGS, 'event': 'UserPromptSubmit'},
        {'args': _STOP_ARGS, 'event': 'Stop'},
    ], run.describe()


def test_program_off_path_runs_nowhere_and_the_turn_completes(workspace: ProgramWorkspace) -> None:
    """With the program's directory off PATH, no hook runs, and the failure to start it blocks nothing."""
    run = workspace.run(program_on_path=False)

    assert run.returncode == 0, run.describe()
    assert len(run.bodies) == 1, run.describe()
    assert workspace.records() == [], run.describe()
