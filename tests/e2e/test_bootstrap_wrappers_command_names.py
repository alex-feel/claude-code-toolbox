"""E2E tests for --command-names, --profile and the link flags through the platform bootstrap wrappers.

The wrappers download setup_environment.py and run it with uv, forwarding
every user argument verbatim, and leave CLAUDE_CODE_TOOLBOX_ENV_CONFIG,
CLAUDE_CODE_TOOLBOX_COMMAND_NAMES, CLAUDE_CODE_TOOLBOX_PROFILE,
CLAUDE_CODE_TOOLBOX_LINK_DIRS and CLAUDE_CODE_TOOLBOX_LINK_FROM in the
environment the script reads: a configuration from the variable never
reaches the command line, which is how the script tells a typed
configuration from one set in the environment. A --profile re-run needs no
configuration, so the wrappers run without one when the flag or its
variable is present. On Linux and macOS the wrapper runs with stand-ins for
curl (which copies the repository's scripts) and uv (which runs them with
the test interpreter), so the real setup script previews the profile the
arguments select. On Windows the stand-ins for Invoke-WebRequest and uv
record what the wrapper hands over instead: a real run there would rewrite
the user's PATH registry entries.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import setup_environment

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
    home.mkdir(exist_ok=True)
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
        """The flag works when the configuration comes from CLAUDE_CODE_TOOLBOX_ENV_CONFIG, which the script reads."""
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


@pytest.mark.parametrize('platform_dir', UNIX_WRAPPERS)
class TestUnixWrapperLinks:
    """The bash wrappers hand --link-dirs, --link-from and their variables to the setup script."""

    def test_link_flags_reach_the_setup_script(self, platform_dir: str, tmp_path: Path) -> None:
        """Typed link flags are forwarded verbatim and the preview lists the link they request."""
        config = tmp_path / 'profile.yaml'
        config.write_text(PROFILE_YAML, encoding='utf-8')

        result = _run_unix_wrapper(
            tmp_path,
            _unix_wrapper(platform_dir),
            [
                str(config), '--skip-install', '--dry-run', '--command-names', 'linked',
                '--link-dirs', 'projects', '--link-from', 'base',
            ],
            {},
        )

        output = result.stdout + result.stderr
        assert result.returncode == 0, output
        assert 'Links (from profile "base"):' in output
        assert '[cli]' in output.split('Links (from profile "base"):')[1].splitlines()[0]
        assert f'projects -> {tmp_path / "home" / ".claude" / "projects"} [create]' in output
        assert not (tmp_path / 'home' / '.claude' / 'linked').exists()

    def test_link_variables_reach_the_setup_script(self, platform_dir: str, tmp_path: Path) -> None:
        """The one-liner form sets the names and the links through the variables the wrapper leaves in place."""
        config = tmp_path / 'profile.yaml'
        config.write_text(PROFILE_YAML, encoding='utf-8')

        result = _run_unix_wrapper(
            tmp_path,
            _unix_wrapper(platform_dir),
            ['--skip-install', '--dry-run'],
            {
                'CLAUDE_CODE_TOOLBOX_ENV_CONFIG': str(config),
                'CLAUDE_CODE_TOOLBOX_COMMAND_NAMES': 'linked',
                'CLAUDE_CODE_TOOLBOX_LINK_DIRS': 'projects',
                'CLAUDE_CODE_TOOLBOX_LINK_FROM': 'base',
            },
        )

        output = result.stdout + result.stderr
        assert result.returncode == 0, output
        assert 'Command names: linked [env]' in output
        assert 'Links (from profile "base"):' in output
        assert '[env]' in output.split('Links (from profile "base"):')[1].splitlines()[0]
        assert f'projects -> {tmp_path / "home" / ".claude" / "projects"} [create]' in output


def _install_profile_manifest(tmp_path: Path, name: str) -> Path:
    """Record an installed profile in the wrapper's home, with a configuration beside it.

    Returns:
        The configuration the profile was installed from.
    """
    config = tmp_path / 'profile.yaml'
    config.write_text(PROFILE_YAML, encoding='utf-8')
    profile_dir = tmp_path / 'home' / '.claude' / name
    assert setup_environment.write_manifest(
        config_base_dir=profile_dir,
        command_name=name,
        config_version=None,
        config_source=str(config.resolve()),
        config_source_type='local',
        config_source_url=None,
        command_names=[name, f'{name}-alias'],
        claude_code_version=None,
        origins={'command_names': 'cli', 'components': 'yaml'},
    )
    return config


def _write_other_configuration(tmp_path: Path) -> Path:
    """Write a second configuration of a different identity beside the profile's own."""
    other = tmp_path / 'other.yaml'
    other.write_text(PROFILE_YAML.replace('Wrapper Profile', 'Other Profile'), encoding='utf-8')
    return other


@pytest.mark.parametrize('platform_dir', UNIX_WRAPPERS)
class TestUnixWrapperProfileRerun:
    """The bash wrappers run a --profile re-run without a configuration."""

    def test_profile_flag_needs_no_configuration(self, platform_dir: str, tmp_path: Path) -> None:
        """--profile NAME as the first argument reaches the setup script, which re-runs the profile."""
        _install_profile_manifest(tmp_path, 'wrapped')

        result = _run_unix_wrapper(
            tmp_path, _unix_wrapper(platform_dir), ['--profile', 'wrapped', '--skip-install', '--dry-run'], {},
        )

        output = result.stdout + result.stderr
        assert result.returncode == 0, output
        assert 'Command names: wrapped, wrapped-alias [remembered]' in output

    def test_profile_variable_needs_no_configuration(self, platform_dir: str, tmp_path: Path) -> None:
        """CLAUDE_CODE_TOOLBOX_PROFILE alone selects the profile the script re-runs."""
        _install_profile_manifest(tmp_path, 'wrapped')

        result = _run_unix_wrapper(
            tmp_path, _unix_wrapper(platform_dir), ['--skip-install', '--dry-run'],
            {'CLAUDE_CODE_TOOLBOX_PROFILE': 'wrapped'},
        )

        output = result.stdout + result.stderr
        assert result.returncode == 0, output
        assert 'Command names: wrapped, wrapped-alias [remembered]' in output

    def test_no_configuration_and_no_profile_is_refused_by_the_wrapper(self, platform_dir: str, tmp_path: Path) -> None:
        """Without a configuration or a profile the wrapper stops before downloading anything."""
        result = _run_unix_wrapper(tmp_path, _unix_wrapper(platform_dir), ['--skip-install', '--dry-run'], {})

        output = result.stdout + result.stderr
        assert result.returncode == 1, output
        assert 'No configuration specified!' in output
        assert '--profile <name>' in output

    def test_profile_with_the_same_configuration_in_the_variable_proceeds(
        self, platform_dir: str, tmp_path: Path,
    ) -> None:
        """CLAUDE_CODE_TOOLBOX_ENV_CONFIG naming the profile's own configuration is accepted beside --profile."""
        config = _install_profile_manifest(tmp_path, 'wrapped')

        result = _run_unix_wrapper(
            tmp_path, _unix_wrapper(platform_dir), ['--profile', 'wrapped', '--skip-install', '--dry-run'],
            {'CLAUDE_CODE_TOOLBOX_ENV_CONFIG': str(config)},
        )

        output = result.stdout + result.stderr
        assert result.returncode == 0, output
        assert 'Command names: wrapped, wrapped-alias [remembered]' in output
        assert 'names a different configuration' not in output

    def test_profile_with_another_configuration_in_the_variable_names_the_variable(
        self, platform_dir: str, tmp_path: Path,
    ) -> None:
        """A different configuration left in the variable is the switch guard, whose remedy clears the variable."""
        _install_profile_manifest(tmp_path, 'wrapped')
        other = _write_other_configuration(tmp_path)

        result = _run_unix_wrapper(
            tmp_path, _unix_wrapper(platform_dir), ['--profile', 'wrapped', '--skip-install', '--dry-run'],
            {'CLAUDE_CODE_TOOLBOX_ENV_CONFIG': str(other)},
        )

        output = result.stdout + result.stderr
        assert result.returncode == 1, output
        assert f'CLAUDE_CODE_TOOLBOX_ENV_CONFIG names a different configuration, {other.resolve()}.' in output
        assert (
            'Clear CLAUDE_CODE_TOOLBOX_ENV_CONFIG (unset CLAUDE_CODE_TOOLBOX_ENV_CONFIG, or '
            'Remove-Item Env:CLAUDE_CODE_TOOLBOX_ENV_CONFIG in PowerShell) and re-run the profile with its own '
            'configuration: --profile wrapped.'
        ) in output

    def test_profile_with_another_positional_configuration_names_the_argument(
        self, platform_dir: str, tmp_path: Path,
    ) -> None:
        """A different configuration typed beside --profile is named as the configuration argument."""
        _install_profile_manifest(tmp_path, 'wrapped')
        other = _write_other_configuration(tmp_path)

        result = _run_unix_wrapper(
            tmp_path, _unix_wrapper(platform_dir), [str(other), '--profile', 'wrapped', '--skip-install', '--dry-run'],
            {},
        )

        output = result.stdout + result.stderr
        assert result.returncode == 1, output
        assert f'the configuration argument names a different configuration, {other.resolve()}.' in output
        assert (
            'Drop the configuration argument and re-run the profile with its own configuration: --profile wrapped.'
        ) in output


WINDOWS_STAND_INS = '''\
function Invoke-WebRequest {
    param($Uri, $OutFile, [switch]$UseBasicParsing)
    Set-Content -LiteralPath $OutFile -Value ''
}
function uv {
    # Arguments arrive as PowerShell values (3.12 is a number); record the text uv receives
    $record = @{
        args = @($args | ForEach-Object { [string]$_ })
        config = $env:CLAUDE_CODE_TOOLBOX_ENV_CONFIG
        command_names = $env:CLAUDE_CODE_TOOLBOX_COMMAND_NAMES
        profile = $env:CLAUDE_CODE_TOOLBOX_PROFILE
        link_dirs = $env:CLAUDE_CODE_TOOLBOX_LINK_DIRS
        link_from = $env:CLAUDE_CODE_TOOLBOX_LINK_FROM
    }
    $record | ConvertTo-Json | Set-Content -LiteralPath $env:E2E_RECORD -Encoding utf8
    $global:LASTEXITCODE = 0
}
'''


def _run_windows_wrapper(
    tmp_path: Path, args: list[str], extra_env: dict[str, str], *, expect_exit: int = 0,
) -> dict[str, object]:
    """Run the PowerShell wrapper with recording stand-ins.

    Args:
        tmp_path: The test's temporary directory, holding the wrapper's home.
        args: The arguments the wrapper receives.
        extra_env: Environment variables set for the wrapper.
        expect_exit: The exit code the wrapper is expected to return.

    Returns:
        What uv received (``args``, ``config``, ``command_names``,
        ``profile``, ``link_dirs``, ``link_from``), or the wrapper's output
        under ``output`` when it stopped before running uv.
    """
    home = tmp_path / 'home'
    home.mkdir(exist_ok=True)
    record = tmp_path / 'record.json'
    wrapper = SCRIPTS_DIR / 'windows' / 'setup-environment.ps1'
    quoted_args = ' '.join("'" + arg.replace("'", "''") + "'" for arg in args)
    command = f"{WINDOWS_STAND_INS}\n& '{wrapper}' {quoted_args}\nexit $LASTEXITCODE"
    env = {**os.environ, 'USERPROFILE': str(home), 'E2E_RECORD': str(record), **extra_env}
    for variable in (
        'CLAUDE_CODE_TOOLBOX_PROFILE', 'CLAUDE_CODE_TOOLBOX_ENV_CONFIG', 'CLAUDE_CODE_TOOLBOX_COMMAND_NAMES',
        'CLAUDE_CODE_TOOLBOX_LINK_DIRS', 'CLAUDE_CODE_TOOLBOX_LINK_FROM',
    ):
        env.pop(variable, None)
    env.update(extra_env)
    # PowerShell writes its module analysis cache relative to the working
    # directory when the profile directories it expects are absent, so the
    # process runs inside the test's temporary directory
    result = subprocess.run(
        ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', command],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == expect_exit, result.stdout + result.stderr
    if not record.exists():
        return {'output': result.stdout + result.stderr}
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
        """A configuration in CLAUDE_CODE_TOOLBOX_ENV_CONFIG stays a variable; the arguments go through as typed."""
        recorded = _run_windows_wrapper(
            tmp_path,
            ['--command-names', 'second', '--dry-run'],
            {'CLAUDE_CODE_TOOLBOX_ENV_CONFIG': 'profile.yaml'},
        )

        assert recorded['args'] == [
            'run', '--no-project', '--python', '3.12', 'setup_environment.py', '--command-names', 'second', '--dry-run',
        ]
        assert recorded['config'] == 'profile.yaml'


@pytest.mark.skipif(sys.platform != 'win32', reason='the PowerShell wrapper runs only on Windows')
class TestWindowsWrapperLinks:
    """The PowerShell wrapper hands the link flags and their variables to the setup script."""

    def test_link_flags_are_forwarded_verbatim(self, tmp_path: Path) -> None:
        """--link-dirs and --link-from typed after the configuration reach setup_environment.py unchanged."""
        recorded = _run_windows_wrapper(
            tmp_path,
            ['team', '--command-names', 'team-2', '--link-dirs', 'all', '--link-from', 'team-1', '--dry-run'],
            {},
        )

        assert recorded['args'] == [
            'run', '--no-project', '--python', '3.12', 'setup_environment.py',
            'team', '--command-names', 'team-2', '--link-dirs', 'all', '--link-from', 'team-1', '--dry-run',
        ]
        assert recorded['link_dirs'] is None
        assert recorded['link_from'] is None

    def test_one_liner_links_a_profile_from_the_variables(self, tmp_path: Path) -> None:
        """The iex (irm ...) form with the configuration, the names and the two link variables runs with no arguments."""
        recorded = _run_windows_wrapper(
            tmp_path,
            [],
            {
                'CLAUDE_CODE_TOOLBOX_ENV_CONFIG': 'team',
                'CLAUDE_CODE_TOOLBOX_COMMAND_NAMES': 'team-2',
                'CLAUDE_CODE_TOOLBOX_LINK_DIRS': 'all',
                'CLAUDE_CODE_TOOLBOX_LINK_FROM': 'team-1',
            },
        )

        assert recorded['args'] == ['run', '--no-project', '--python', '3.12', 'setup_environment.py']
        assert recorded['config'] == 'team'
        assert recorded['command_names'] == 'team-2'
        assert recorded['link_dirs'] == 'all'
        assert recorded['link_from'] == 'team-1'


@pytest.mark.skipif(sys.platform != 'win32', reason='the PowerShell wrapper runs only on Windows')
class TestWindowsWrapperProfileRerun:
    """The PowerShell wrapper runs a --profile re-run without a configuration."""

    def test_profile_flag_without_configuration_is_forwarded(self, tmp_path: Path) -> None:
        """--profile NAME as the first argument is forwarded with no configuration in front of it."""
        recorded = _run_windows_wrapper(tmp_path, ['--profile', 'team-1', '--dry-run'], {})

        assert recorded['args'] == [
            'run', '--no-project', '--python', '3.12', 'setup_environment.py', '--profile', 'team-1', '--dry-run',
        ]
        assert recorded['profile'] is None

    def test_one_liner_with_the_profile_variable_runs_without_arguments(self, tmp_path: Path) -> None:
        """The iex (irm ...) form with CLAUDE_CODE_TOOLBOX_PROFILE set runs the script with no arguments."""
        recorded = _run_windows_wrapper(tmp_path, [], {'CLAUDE_CODE_TOOLBOX_PROFILE': 'team-1'})

        assert recorded['args'] == ['run', '--no-project', '--python', '3.12', 'setup_environment.py']
        assert recorded['profile'] == 'team-1'

    def test_no_configuration_and_no_profile_is_refused_by_the_wrapper(self, tmp_path: Path) -> None:
        """Without a configuration or a profile the wrapper stops before running uv."""
        recorded = _run_windows_wrapper(tmp_path, ['--dry-run'], {}, expect_exit=1)

        assert 'args' not in recorded
        assert 'No configuration specified!' in str(recorded['output'])
        assert '--profile <name>' in str(recorded['output'])

    @pytest.mark.parametrize('config', ['profile.yaml', 'other.yaml'])
    def test_profile_with_a_configuration_in_the_variable_keeps_it_out_of_the_arguments(
        self, config: str, tmp_path: Path,
    ) -> None:
        """Whether the variable names the profile's own configuration or another, the script decides from the variable."""
        recorded = _run_windows_wrapper(
            tmp_path, ['--profile', 'team-1', '--dry-run'], {'CLAUDE_CODE_TOOLBOX_ENV_CONFIG': config},
        )

        assert recorded['args'] == [
            'run', '--no-project', '--python', '3.12', 'setup_environment.py', '--profile', 'team-1', '--dry-run',
        ]
        assert recorded['config'] == config

    def test_profile_with_a_positional_configuration_forwards_it_as_typed(self, tmp_path: Path) -> None:
        """A configuration typed beside --profile reaches the script as the configuration argument."""
        recorded = _run_windows_wrapper(tmp_path, ['other.yaml', '--profile', 'team-1', '--dry-run'], {})

        assert recorded['args'] == [
            'run', '--no-project', '--python', '3.12', 'setup_environment.py',
            'other.yaml', '--profile', 'team-1', '--dry-run',
        ]
        assert recorded['config'] is None
