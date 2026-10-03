"""E2E tests for --command-names through the platform bootstrap wrappers.

The wrappers download setup_environment.py and run it with uv, forwarding
every user argument verbatim, and leave CLAUDE_CODE_TOOLBOX_COMMAND_NAMES in
the environment the script reads. On Linux and macOS the wrapper runs with
stand-ins for curl (which copies the repository's scripts) and uv (which runs
them with the test interpreter), so the real setup script previews the
profile the arguments select. On Windows the stand-ins for Invoke-WebRequest
and uv record what the wrapper hands over instead: a real run there would
rewrite the user's PATH registry entries.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / 'scripts'

PROFILE_YAML = '''\
name: Wrapper Profile
command-names: [yaml-name]
command-defaults: {}
user-settings:
  theme: dark
'''

FAKE_CURL = '''\
#!/usr/bin/env bash
# Stand-in for curl: copy the requested repository script to the -o path
out=""
url=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        -o) out="$2"; shift 2 ;;
        -*) shift ;;
        *) url="$1"; shift ;;
    esac
done
cp "$E2E_SCRIPTS_DIR/$(basename "$url")" "$out"
'''

FAKE_UV = '''\
#!/usr/bin/env bash
# Stand-in for uv: accept the Python install, run the script with the test interpreter
if [ "$1" = "python" ]; then
    exit 0
fi
if [ "$1" = "run" ]; then
    shift 4
    exec "$E2E_PYTHON" "$@"
fi
exit 2
'''


def _unix_wrapper(platform_dir: str) -> Path:
    """Return the bootstrap wrapper of one Unix platform."""
    return SCRIPTS_DIR / platform_dir / 'setup-environment.sh'


def _run_unix_wrapper(
    tmp_path: Path,
    wrapper: Path,
    args: list[str],
    extra_env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    """Run a bash bootstrap wrapper with stand-ins for curl and uv in an isolated home."""
    fake_bin = tmp_path / 'fake-bin'
    fake_bin.mkdir()
    for name, body in (('curl', FAKE_CURL), ('uv', FAKE_UV)):
        stand_in = fake_bin / name
        stand_in.write_text(body, encoding='utf-8', newline='\n')
        stand_in.chmod(0o755)
    home = tmp_path / 'home'
    home.mkdir()
    env = {
        'PATH': f'{fake_bin}{os.pathsep}{os.environ["PATH"]}',
        'HOME': str(home),
        'E2E_SCRIPTS_DIR': str(SCRIPTS_DIR),
        'E2E_PYTHON': sys.executable,
        'CLAUDE_CODE_TOOLBOX_ALLOW_ROOT': '1',
        **extra_env,
    }
    bash = shutil.which('bash')
    assert bash is not None
    return subprocess.run(
        [bash, str(wrapper), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


UNIX_WRAPPERS = [
    pytest.param(
        'linux',
        marks=pytest.mark.skipif(not sys.platform.startswith('linux'), reason='the Linux wrapper runs only on Linux'),
    ),
    pytest.param(
        'macos',
        marks=pytest.mark.skipif(sys.platform != 'darwin', reason='the macOS wrapper runs only on macOS'),
    ),
]


@pytest.mark.parametrize('platform_dir', UNIX_WRAPPERS)
class TestUnixWrapper:
    """The bash wrappers hand --command-names and its variable to the setup script."""

    def test_flag_reaches_the_setup_script(self, platform_dir: str, tmp_path: Path) -> None:
        """A typed list is forwarded verbatim and wins over the configuration."""
        config = tmp_path / 'profile.yaml'
        config.write_text(PROFILE_YAML, encoding='utf-8')

        result = _run_unix_wrapper(
            tmp_path,
            _unix_wrapper(platform_dir),
            [str(config), '--skip-install', '--dry-run', '--command-names', 'wrapped,wrapped-alias'],
            {},
        )

        output = result.stdout + result.stderr
        assert result.returncode == 0, output
        assert 'Command names: wrapped, wrapped-alias [cli]' in output
        assert not (tmp_path / 'home' / '.claude' / 'wrapped').exists()

    def test_variable_reaches_the_setup_script(self, platform_dir: str, tmp_path: Path) -> None:
        """The variable passes through the wrapper's environment unchanged."""
        config = tmp_path / 'profile.yaml'
        config.write_text(PROFILE_YAML, encoding='utf-8')

        result = _run_unix_wrapper(
            tmp_path,
            _unix_wrapper(platform_dir),
            [str(config), '--skip-install', '--dry-run'],
            {'CLAUDE_CODE_TOOLBOX_COMMAND_NAMES': 'from-env'},
        )

        output = result.stdout + result.stderr
        assert result.returncode == 0, output
        assert 'Command names: from-env [env]' in output

    def test_configuration_from_variable_with_flag(self, platform_dir: str, tmp_path: Path) -> None:
        """The flag works when the configuration comes from CLAUDE_CODE_TOOLBOX_ENV_CONFIG."""
        config = tmp_path / 'profile.yaml'
        config.write_text(PROFILE_YAML, encoding='utf-8')

        result = _run_unix_wrapper(
            tmp_path,
            _unix_wrapper(platform_dir),
            ['--skip-install', '--dry-run', '--command-names', 'second'],
            {'CLAUDE_CODE_TOOLBOX_ENV_CONFIG': str(config)},
        )

        output = result.stdout + result.stderr
        assert result.returncode == 0, output
        assert 'Command names: second [cli]' in output


WINDOWS_STAND_INS = '''\
function Invoke-WebRequest {
    param($Uri, $OutFile, [switch]$UseBasicParsing)
    Set-Content -LiteralPath $OutFile -Value ''
}
function uv {
    # Arguments arrive as PowerShell values (3.12 is a number); record the text uv receives
    $record = @{ args = @($args | ForEach-Object { [string]$_ }); command_names = $env:CLAUDE_CODE_TOOLBOX_COMMAND_NAMES }
    $record | ConvertTo-Json | Set-Content -LiteralPath $env:E2E_RECORD -Encoding utf8
    $global:LASTEXITCODE = 0
}
'''


def _run_windows_wrapper(tmp_path: Path, args: list[str], extra_env: dict[str, str]) -> dict[str, object]:
    """Run the PowerShell wrapper with recording stand-ins and return what uv received."""
    home = tmp_path / 'home'
    home.mkdir()
    record = tmp_path / 'record.json'
    wrapper = SCRIPTS_DIR / 'windows' / 'setup-environment.ps1'
    quoted_args = ' '.join("'" + arg.replace("'", "''") + "'" for arg in args)
    command = f"{WINDOWS_STAND_INS}\n& '{wrapper}' {quoted_args}\nexit $LASTEXITCODE"
    env = {**os.environ, 'USERPROFILE': str(home), 'E2E_RECORD': str(record), **extra_env}
    result = subprocess.run(
        ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', command],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    recorded: dict[str, object] = json.loads(record.read_text(encoding='utf-8-sig'))
    return recorded


@pytest.mark.skipif(sys.platform != 'win32', reason='the PowerShell wrapper runs only on Windows')
class TestWindowsWrapper:
    """The PowerShell wrapper hands --command-names and its variable to the setup script."""

    def test_flag_is_forwarded_verbatim(self, tmp_path: Path) -> None:
        """Every argument after the configuration reaches setup_environment.py unchanged."""
        recorded = _run_windows_wrapper(
            tmp_path, ['profile.yaml', '--command-names', 'wrapped,wrapped-alias', '--dry-run'], {},
        )

        assert recorded['args'] == [
            'run', '--no-project', '--python', '3.12', 'setup_environment.py',
            'profile.yaml', '--command-names', 'wrapped,wrapped-alias', '--dry-run',
        ]
        assert recorded['command_names'] is None

    def test_variable_reaches_the_setup_script(self, tmp_path: Path) -> None:
        """The variable passes through the wrapper's environment unchanged."""
        recorded = _run_windows_wrapper(
            tmp_path, ['profile.yaml', '--dry-run'], {'CLAUDE_CODE_TOOLBOX_COMMAND_NAMES': 'from-env'},
        )

        assert recorded['command_names'] == 'from-env'
        assert recorded['args'] == [
            'run', '--no-project', '--python', '3.12', 'setup_environment.py', 'profile.yaml', '--dry-run',
        ]

    def test_configuration_from_variable_with_flag(self, tmp_path: Path) -> None:
        """With the configuration in CLAUDE_CODE_TOOLBOX_ENV_CONFIG the flag still follows it."""
        recorded = _run_windows_wrapper(
            tmp_path,
            ['--command-names', 'second', '--dry-run'],
            {'CLAUDE_CODE_TOOLBOX_ENV_CONFIG': 'profile.yaml'},
        )

        assert recorded['args'] == [
            'run', '--no-project', '--python', '3.12', 'setup_environment.py',
            'profile.yaml', '--command-names', 'second', '--dry-run',
        ]
