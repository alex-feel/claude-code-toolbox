"""E2E tests for an isolated install whose profile directory user-settings.env relocates.

An isolated configuration installs into ``~/.claude/<cmd>`` unless its
``user-settings.env`` sets ``CLAUDE_CONFIG_DIR``, in which case setup writes
the profile there. A full setup run must then produce launchers and global
wrappers that export that directory and read every profile file from it, and
a configuration without the override must keep its established rendering.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts import setup_environment
from tests.e2e.expected.launchers import GOLDEN_ALIAS
from tests.e2e.expected.launchers import GOLDEN_COMMAND
from tests.e2e.expected.launchers import GOLDEN_PROMPT
from tests.e2e.launcher_support import LOADER_MARKS_VARIABLE
from tests.e2e.launcher_support import WINDOWS_GIT_BASH
from tests.e2e.launcher_support import assert_default_rendering
from tests.e2e.launcher_support import assert_reaches_profile
from tests.e2e.launcher_support import expected_spelling
from tests.e2e.launcher_support import find_bash
from tests.e2e.launcher_support import find_powershell
from tests.e2e.launcher_support import launch
from tests.e2e.launcher_support import powershell_command
from tests.e2e.validators import validate_launcher_profile_spelling
from tests.e2e.validators import validate_manifest

# Profile directory layouts: (id, CLAUDE_CONFIG_DIR value or None, location of
# the expected profile directory relative to 'home' or 'tmp'). In a value,
# {home} is the home directory, {home_case} the same directory with the case of
# every letter swapped, and {tmp} the directory holding the home directory.
LAYOUTS = [
    pytest.param(None, ('home', ('.claude', GOLDEN_COMMAND)), id='default'),
    pytest.param('~/.claude-work', ('home', ('.claude-work',)), id='direct-child-of-home'),
    pytest.param('~/profiles/tilde work', ('home', ('profiles', 'tilde work')), id='tilde-below-home'),
    pytest.param('{home}/profiles/work', ('home', ('profiles', 'work')), id='below-home'),
    pytest.param(
        '{home_case}/profiles/work',
        ('home', ('profiles', 'work')),
        id='below-home-other-case',
        marks=pytest.mark.skipif(sys.platform != 'win32', reason='Windows paths are case-insensitive'),
    ),
    pytest.param('{tmp}/elsewhere/work', ('tmp', ('elsewhere', 'work')), id='outside-home'),
    pytest.param('{tmp}/My Profiles (work)/work', ('tmp', ('My Profiles (work)', 'work')), id='outside-home-spaced'),
]

# Value every generated env loader assigns; a launch that sourced a loader of
# the profile directory hands it to claude.
LOADER_VALUE = 'os-loader;'


def _config(config_dir: str | None) -> dict[str, Any]:
    """Build an isolated configuration with a prompt, an env loader and a profile MCP server.

    Args:
        config_dir: The user-settings.env CLAUDE_CONFIG_DIR value, or None.

    Returns:
        The configuration.
    """
    user_settings: dict[str, Any] = {'theme': 'dark'}
    if config_dir is not None:
        user_settings['env'] = {'CLAUDE_CONFIG_DIR': config_dir}
    return {
        'name': 'Relocated Profile Probe',
        'version': '1.0.0',
        'command-names': [GOLDEN_COMMAND, GOLDEN_ALIAS],
        'command-defaults': {'system-prompt': f'prompts/{GOLDEN_PROMPT}', 'mode': 'replace'},
        'user-settings': user_settings,
        'os-env-variables': {LOADER_MARKS_VARIABLE: LOADER_VALUE},
        'mcp-servers': [
            {'name': 'relo-profile-server', 'scope': 'profile', 'transport': 'http', 'url': 'http://localhost:9/mcp'},
        ],
    }


def _run_setup(config: dict[str, Any]) -> None:
    """Run setup_environment.main() for config with every network and OS writer stubbed.

    Args:
        config: The configuration main() loads.
    """

    def write_prompt(_source: str, destination: Path, *_args: object, **_kwargs: object) -> bool:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text('Relocated profile prompt.\n', encoding='utf-8')
        return True

    find_other_command = setup_environment.find_command

    def find_command(name: str) -> str | None:
        return '/usr/bin/claude' if name == 'claude' else find_other_command(name)

    with patch.object(setup_environment, 'load_config_from_source', return_value=(config, 'relocated.yaml')), \
            patch.object(setup_environment, 'validate_all_config_files', return_value=(True, [])), \
            patch.object(setup_environment, 'install_dependencies', return_value=[]), \
            patch.object(setup_environment, 'process_resources', return_value=True), \
            patch.object(setup_environment, 'process_skills', return_value=True), \
            patch.object(setup_environment, 'handle_resource', side_effect=write_prompt), \
            patch.object(setup_environment, 'set_all_os_env_variables', return_value=True), \
            patch.object(setup_environment, 'is_admin', return_value=True), \
            patch.object(setup_environment, 'find_command', side_effect=find_command), \
            patch('sys.argv', ['setup_environment.py', 'relocated', '--yes', '--skip-install']), \
            patch('sys.exit') as mock_exit:
        setup_environment.main()
        mock_exit.assert_not_called()


def _entry_points(local_bin: Path, profile_dir: Path) -> list[tuple[str, list[str] | str]]:
    """List the commands a user runs to start the profile on this platform.

    Args:
        local_bin: Directory holding the global wrappers.
        profile_dir: The profile directory holding launch.sh.

    Returns:
        (label, command line) pairs; empty when an interpreter is missing.
    """
    if sys.platform != 'win32':
        return [(name, [str(local_bin / name), '--probe-arg']) for name in (GOLDEN_COMMAND, GOLDEN_ALIAS)]
    powershell = find_powershell()
    bash = find_bash()
    if not WINDOWS_GIT_BASH.exists() or powershell is None or bash is None:
        return []
    entry_points: list[tuple[str, list[str] | str]] = [('launch.sh', [bash, str(profile_dir / 'launch.sh'), '--probe-arg'])]
    for name in (GOLDEN_COMMAND, GOLDEN_ALIAS):
        entry_points.extend([
            (f'{name}.cmd', f'cmd.exe /d /c {name} --probe-arg'),
            (f'{name}.ps1', powershell_command(powershell, local_bin / f'{name}.ps1', '--probe-arg')),
            (name, [bash, str(local_bin / name), '--probe-arg']),
        ])
    return entry_points


class TestIsolatedInstallLaunchersFollowProfileDirectory:
    """A full isolated install renders every launcher and wrapper from its profile directory."""

    @pytest.mark.parametrize(('config_dir', 'location'), LAYOUTS)
    def test_setup_writes_launchers_that_start_the_profile(
        self,
        e2e_isolated_home: dict[str, Path],
        config_dir: str | None,
        location: tuple[str, tuple[str, ...]],
    ) -> None:
        """Setup writes the profile where configured and every entry point starts claude with it."""
        home = e2e_isolated_home['home']
        tmp = home.parent
        local_bin = e2e_isolated_home['local_bin']
        anchor, parts = location
        profile_dir = (home if anchor == 'home' else tmp).joinpath(*parts)
        # The profile directory as the configuration spells it; the PowerShell
        # wrappers name start.ps1 by this absolute spelling.
        configured_dir = profile_dir
        if config_dir is not None:
            config_dir = config_dir.format(
                home=home.as_posix(), home_case=home.as_posix().swapcase(), tmp=tmp.as_posix(),
            )
            configured_dir = Path(config_dir).expanduser()
            assert configured_dir == profile_dir, f'{config_dir} does not name {profile_dir}'
        config = _config(config_dir)

        _run_setup(config)

        for name in ('config.json', 'mcp.json', 'env.sh', 'manifest.json', 'launch.sh', f'prompts/{GOLDEN_PROMPT}'):
            assert (profile_dir / name).is_file(), f'{name} missing from {profile_dir}'
        if config_dir is not None:
            assert not (home / '.claude' / GOLDEN_COMMAND).exists(), 'setup wrote into the default profile directory'
        errors = validate_manifest(profile_dir / 'manifest.json', config)

        is_windows = sys.platform == 'win32'
        spelling = expected_spelling(configured_dir, home)
        errors.extend(validate_launcher_profile_spelling(
            configured_dir,
            posix_dir=spelling.posix_dir,
            cmd_dir=spelling.cmd_dir,
            powershell_parent=spelling.powershell_parent,
            windows_launchers=is_windows,
            local_bin=local_bin if is_windows else None,
            wrapper_names=(GOLDEN_COMMAND, GOLDEN_ALIAS),
        ))
        assert not errors, '\n'.join(errors)

        if config_dir is None:
            if is_windows:
                start_ps1 = profile_dir / 'start.ps1'
                assert_default_rendering(start_ps1, 'windows/start.ps1', lf_pinned=False)
                assert_default_rendering(profile_dir / 'start.cmd', 'windows/start.cmd', lf_pinned=False)
                assert_default_rendering(profile_dir / 'launch.sh', 'windows/launch.sh/prompt-replace', lf_pinned=True)
                for name in (GOLDEN_COMMAND, GOLDEN_ALIAS):
                    assert_default_rendering(local_bin / f'{name}.cmd', f'windows-wrappers/{name}.cmd', lf_pinned=False)
                    assert_default_rendering(
                        local_bin / f'{name}.ps1', f'windows-wrappers/{name}.ps1', lf_pinned=False,
                        launcher_path=start_ps1,
                    )
                    assert_default_rendering(local_bin / name, f'windows-wrappers/{name}', lf_pinned=True)
            else:
                assert_default_rendering(profile_dir / 'launch.sh', 'unix/launch.sh/prompt-replace', lf_pinned=False)

        entry_points = _entry_points(local_bin, profile_dir)
        if not entry_points:
            pytest.skip('the interpreters the generated scripts need are unavailable')
        for label, command in entry_points:
            record = launch(command, home=home, stub_dir=tmp / 'stub-bin', extra_path=local_bin)
            assert_reaches_profile(record, profile_dir, GOLDEN_PROMPT)
            assert record.loader_marks == LOADER_VALUE, f'{label}: loader marks {record.loader_marks!r}'
