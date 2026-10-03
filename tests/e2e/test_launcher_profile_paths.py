"""E2E tests for the profile directory every launcher and wrapper names.

Setup writes a profile's launchers into the profile directory and its global
wrappers into ``~/.local/bin``. These tests pin the exact bytes generated for
the default profile directory ``~/.claude/<cmd>``, and run the generated
scripts under their real interpreters with a stub ``claude`` that records the
environment and arguments it receives.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from scripts import setup_environment
from scripts.setup_environment import create_launcher_script
from scripts.setup_environment import register_global_command
from tests.e2e.expected.launchers import DEFAULT_RENDERINGS
from tests.e2e.expected.launchers import GOLDEN_ALIAS
from tests.e2e.expected.launchers import GOLDEN_COMMAND
from tests.e2e.expected.launchers import GOLDEN_PROMPT
from tests.e2e.expected.launchers import LAUNCHER_PATH_TOKEN
from tests.e2e.test_launcher_scripts import _find_bash

# Launcher variants create_launcher_script() generates: (id, prompt file, mode).
LAUNCHER_VARIANTS = [
    pytest.param('no-prompt', None, 'replace', id='no-prompt'),
    pytest.param('prompt-replace', GOLDEN_PROMPT, 'replace', id='prompt-replace'),
    pytest.param('prompt-append', GOLDEN_PROMPT, 'append', id='prompt-append'),
]


def _expected_bytes(text: str, *, lf_pinned: bool) -> bytes:
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


def _assert_bytes(path: Path, key: str, *, lf_pinned: bool, launcher_path: Path | None = None) -> None:
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
    assert actual == _expected_bytes(expected, lf_pinned=lf_pinned), (
        f'{path.name} differs from the default rendering {key!r}:\n'
        f'--- expected ---\n{expected}\n--- actual ---\n{actual.decode("utf-8", "replace")}'
    )


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


def _write_stub_claude(stub_dir: Path, record_file: Path) -> None:
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
        '  printf \'LOADER_MARKS=%s\\n\' "${PROFILE_LOADER_MARKS:-}"\n'
        '  for arg in "$@"; do printf \'ARG=%s\\n\' "$(to_host "$arg")"; done\n'
        '} > "' + record_file.as_posix() + '"\n',
        encoding='utf-8',
        newline='\n',
    )
    stub.chmod(0o755)


def _launch(command: list[str], *, home: Path, stub_dir: Path) -> LaunchRecord:
    """Run a generated script with the stub claude first on PATH.

    Args:
        command: The command line that runs the script.
        home: The home directory the script sees at run time.
        stub_dir: Directory holding the stub claude.

    Returns:
        What the stub claude received.
    """
    record_file = stub_dir / 'record.txt'
    _write_stub_claude(stub_dir, record_file)
    env = {key: value for key, value in os.environ.items() if key not in {'CLAUDE_CONFIG_DIR', 'PROFILE_LOADER_MARKS'}}
    env['HOME'] = str(home)
    env['USERPROFILE'] = str(home)
    env['PATH'] = f'{stub_dir}{os.pathsep}' + env.get('PATH', '')

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


def _same_path(value: str, expected: Path) -> bool:
    """Return True when a recorded path names the expected file or directory.

    Args:
        value: A path the stub recorded.
        expected: The path it must name.

    Returns:
        Whether both resolve to the same location.
    """
    return Path(value).resolve() == expected.resolve()


def _seed_profile(profile_dir: Path, prompt: str | None) -> None:
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


class TestDefaultLayoutRendering:
    """A profile in ~/.claude/<cmd> gets exactly the established launcher text.

    platform.system() is the only platform detection create_launcher_script()
    and register_global_command() use, so mocking it renders the Windows and
    the Unix file sets on every CI runner.
    """

    @pytest.mark.parametrize(('variant', 'prompt', 'mode'), LAUNCHER_VARIANTS)
    def test_windows_launchers_match_default_rendering(
        self,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        variant: str,
        prompt: str | None,
        mode: str,
    ) -> None:
        """start.ps1, start.cmd and launch.sh match the default rendering byte for byte."""
        profile_dir = e2e_isolated_home['claude_dir'] / GOLDEN_COMMAND
        monkeypatch.setattr(setup_environment.platform, 'system', lambda: 'Windows')

        result = create_launcher_script(profile_dir, GOLDEN_COMMAND, prompt, mode, has_profile_mcp_servers=True)

        assert result == (profile_dir / 'start.ps1', profile_dir / 'launch.sh')
        _assert_bytes(profile_dir / 'start.ps1', 'windows/start.ps1', lf_pinned=False)
        _assert_bytes(profile_dir / 'start.cmd', 'windows/start.cmd', lf_pinned=False)
        _assert_bytes(profile_dir / 'launch.sh', f'windows/launch.sh/{variant}', lf_pinned=True)

    @pytest.mark.parametrize('system', ['Linux', 'Darwin'])
    @pytest.mark.parametrize(('variant', 'prompt', 'mode'), LAUNCHER_VARIANTS)
    def test_unix_launcher_matches_default_rendering(
        self,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        system: str,
        variant: str,
        prompt: str | None,
        mode: str,
    ) -> None:
        """launch.sh matches the default rendering byte for byte on Linux and macOS."""
        profile_dir = e2e_isolated_home['claude_dir'] / GOLDEN_COMMAND
        monkeypatch.setattr(setup_environment.platform, 'system', lambda: system)

        result = create_launcher_script(profile_dir, GOLDEN_COMMAND, prompt, mode, has_profile_mcp_servers=True)

        assert result == (profile_dir / 'launch.sh', profile_dir / 'launch.sh')
        _assert_bytes(profile_dir / 'launch.sh', f'unix/launch.sh/{variant}', lf_pinned=False)

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows wrappers render from Windows path semantics')
    def test_windows_wrappers_match_default_rendering(
        self,
        e2e_isolated_home: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The CMD, PowerShell and Git Bash wrappers of a command and its alias match byte for byte."""
        profile_dir = e2e_isolated_home['claude_dir'] / GOLDEN_COMMAND
        local_bin = e2e_isolated_home['local_bin']
        monkeypatch.setattr(setup_environment.platform, 'system', lambda: 'Windows')
        monkeypatch.setattr(
            setup_environment, 'add_directory_to_windows_path', lambda directory: (True, f'[mock] {directory}'),
        )
        result = create_launcher_script(profile_dir, GOLDEN_COMMAND, None, 'replace', has_profile_mcp_servers=False)
        assert result is not None
        start_ps1, launch_sh = result

        assert register_global_command(start_ps1, GOLDEN_COMMAND, [GOLDEN_ALIAS], launch_script_path=launch_sh)

        for name in (GOLDEN_COMMAND, GOLDEN_ALIAS):
            _assert_bytes(local_bin / f'{name}.cmd', f'windows-wrappers/{name}.cmd', lf_pinned=False)
            _assert_bytes(
                local_bin / f'{name}.ps1', f'windows-wrappers/{name}.ps1', lf_pinned=False, launcher_path=start_ps1,
            )
            _assert_bytes(local_bin / name, f'windows-wrappers/{name}', lf_pinned=True)


class TestMcpConfigPathWithSpaces:
    """A profile MCP config path containing spaces reaches claude as one argument.

    A home directory such as ``C:/Users/First Last`` puts spaces into every
    profile path; --mcp-config must still receive the whole mcp.json path.
    """

    @pytest.mark.parametrize('system', ['Windows', 'Linux'])
    @pytest.mark.parametrize(('variant', 'prompt', 'mode'), LAUNCHER_VARIANTS)
    def test_spaced_mcp_config_path_is_one_argument(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        system: str,
        variant: str,
        prompt: str | None,
        mode: str,
    ) -> None:
        """launch.sh passes --strict-mcp-config and the full spaced mcp.json path."""
        del variant
        bash = _find_bash()
        if bash is None:
            pytest.skip('bash unavailable')
        home = tmp_path / 'user home (x)'
        profile_dir = home / '.claude' / GOLDEN_COMMAND
        _seed_profile(profile_dir, prompt)
        monkeypatch.setattr(Path, 'home', lambda: home)
        monkeypatch.setattr(setup_environment.platform, 'system', lambda: system)
        result = create_launcher_script(profile_dir, GOLDEN_COMMAND, prompt, mode, has_profile_mcp_servers=True)
        assert result is not None

        record = _launch([bash, str(result[1]), '--probe-arg'], home=home, stub_dir=tmp_path / 'stub-bin')

        assert '--strict-mcp-config' in record.args
        assert _same_path(record.value_after('--mcp-config'), profile_dir / 'mcp.json'), record.args
        assert _same_path(record.value_after('--settings'), profile_dir / 'config.json'), record.args
        assert '--probe-arg' in record.args
