"""E2E tests for the writes an isolated install makes outside its own profile.

An isolated run (command-names present) writes inside ~/.claude/{cmd} and
leaves every other profile alone:

- global-config goes to the profile's own .claude.json; the base
  ~/.claude.json changes only when Step 1 installs or upgrades Claude Code,
  and then only in installMethod, which the installer records there.
- os-env-variables go to the profile's env loader files, null entries as
  unset lines; only the three machine-wide binary controls reach the OS
  environment.
- The Step 16 sweeps edit the running profile's settings.json and
  .claude.json; stale controls found in other profiles are listed and never
  edited.
- A global-config null for oauthAccount or userID that signs an account out
  of the .claude.json this run writes is named in the summary and in
  --dry-run; nothing blocks it.
- Every machine-wide write of an isolated run is named in the summary
  before consent: the binary and its installMethod record, a version pin
  and the IDE extension installed at that pin, each OS-level control, the
  command wrappers, project-scope MCP servers, files-to-download
  destinations outside the profile, and the dependency commands.
- The final summary names the files the run wrote: the profile's
  config.json and .claude.json for an isolated run, ~/.claude/settings.json
  and ~/.claude.json for a base run.
- The loaders work when sourced: a null entry removes a variable the
  session inherited, in bash on every platform and in CMD and PowerShell
  on Windows; env.fish is generated when fish is installed.
- Only launch.sh applies a loader, inside the bash process that runs Claude
  Code: the cmd.exe and PowerShell entry points (the ~/.local/bin wrappers,
  start.cmd and start.ps1) leave the calling shell's environment exactly as
  it was while the session they start still receives every set and unset.

A base run keeps writing ~/.claude.json and the OS environment as before.

Every test runs main() against YAML files on disk, so loading, validation,
the writers and the summary run for real; only the steps that never touch
these files (Claude Code installation, dependencies, downloads, MCP
registration, OS environment writes, and, except where a test runs the
generated scripts, launcher and command registration) are stubbed. The
Claude Code installation stub records installMethod in the base
~/.claude.json the way the installer does, so the base file's one allowed
change is exercised rather than assumed. IDE detection is pinned to one
VS Code family CLI so the extension row does not depend on the host.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from collections.abc import Mapping
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from scripts import setup_environment
from tests.conftest import empty_mcp_stats
from tests.e2e.launcher_support import WINDOWS_GIT_BASH
from tests.e2e.shells import find_bash
from tests.e2e.shells import find_powershell
from tests.e2e.validators import validate_env_loader_files

PROFILE_NAME = 'e2e-corp'
PROFILE_ALIAS = 'e2e-corp-alias'
PINNED_VERSION = '2.1.85'
DETECTED_IDE_CLI = 'code'
_ANSI_SEQUENCE = re.compile(r'\x1b\[[0-9;]*m')
MACHINE_WIDE_CONTROLS = ('DISABLE_AUTOUPDATER', 'DISABLE_UPDATES', 'CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL')
BASE_ACCOUNT = {'emailAddress': 'base@example.com', 'accountUuid': 'base-account-uuid'}
LOADER_VARS: dict[str, str | None] = {'E2E_KEPT': 'kept-value', 'E2E_GONE': None}
# Marker a probe prints for a variable its shell does not define.
UNSET_MARKER = '<unset>'


def _write_yaml(path: Path, data: dict[str, Any]) -> Path:
    """Write a configuration dict as a YAML file and return its path."""
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding='utf-8')
    return path


def _write_json(path: Path, data: dict[str, Any]) -> None:
    """Seed a JSON file the way Claude Code leaves it before setup runs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding='utf-8')


def _read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object from disk."""
    data: dict[str, Any] = json.loads(path.read_text(encoding='utf-8'))
    return data


def _install_recording_install_method(home: Path) -> Callable[..., bool]:
    """Build an install_claude stand-in that records installMethod like the installer does.

    update_install_method_config() in install_claude.py reads ~/.claude.json,
    sets installMethod and writes the file back; this stand-in performs the
    same read-merge-write so the test observes the one base-file change an
    isolated run is allowed to cause.

    Returns:
        A callable with install_claude()'s signature that always succeeds.
    """
    def fake_install(_version: str | None = None, *, keep_installed: bool = False) -> bool:
        del keep_installed
        path = home / '.claude.json'
        data = _read_json(path) if path.exists() else {}
        data['installMethod'] = 'native'
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        return True
    return fake_install


def _corp_like_config(
    *,
    isolated: bool,
    pinned: bool = True,
    os_env_variables: Mapping[str, str | None] | None = None,
) -> dict[str, Any]:
    """Build a configuration shaped like a corporate base profile.

    Such a configuration pins a Claude Code version and deletes the account
    keys from the global config so that every install signs in afresh.

    Returns:
        The configuration dict, ready to be written as YAML.
    """
    config: dict[str, Any] = {
        'name': 'Corporate Profile',
        'global-config': {'oauthAccount': None, 'userID': None, 'editorMode': 'vim'},
        'user-settings': {'theme': 'dark'},
    }
    if pinned:
        config['claude-code-version'] = PINNED_VERSION
    if isolated:
        config['command-names'] = [PROFILE_NAME]
    if os_env_variables is not None:
        config['os-env-variables'] = dict(os_env_variables)
    return config


def _run_setup(
    config_path: Path,
    home: Path,
    *args: str,
    install_claude: Callable[..., bool] | None = None,
    real_launchers: bool = False,
) -> tuple[dict[str, str | None] | None, int | None]:
    """Run main() for one YAML file with the unrelated steps stubbed.

    Args:
        config_path: The YAML file main() loads.
        home: The isolated home directory.
        *args: Command-line arguments after the configuration.
        install_claude: Stand-in for the Claude Code installer; always
            succeeds when omitted.
        real_launchers: Whether create_launcher_script() and
            register_global_command() run for real, so the profile's launchers
            and the ~/.local/bin wrappers exist on disk afterwards.

    Returns:
        The dict handed to the OS environment writer (None when Step 7 never
        ran) and the exit code main() asked for (None when it returned).
    """
    profile_dir = home / '.claude' / 'unused-launcher'
    passthrough_find = setup_environment.find_command
    recorded: dict[str, Any] = {}

    def find_with_claude(cmd: str) -> str | None:
        return '/usr/bin/claude' if cmd == 'claude' else passthrough_find(cmd)

    def record_os_env(env_vars: dict[str, str | None]) -> bool:
        recorded['os_env'] = dict(env_vars)
        return True

    exit_code: int | None = None
    with ExitStack() as stack:
        stack.enter_context(patch('scripts.setup_environment.find_command', side_effect=find_with_claude))
        stack.enter_context(patch(
            'scripts.setup_environment.install_claude', side_effect=install_claude or (lambda *_a, **_k: True),
        ))
        stack.enter_context(patch(
            'scripts.setup_environment._detect_vscode_family_ides',
            return_value=[(DETECTED_IDE_CLI, f'/usr/bin/{DETECTED_IDE_CLI}')],
        ))
        stack.enter_context(patch('scripts.setup_environment.install_ide_extensions', return_value=True))
        stack.enter_context(patch('scripts.setup_environment.install_dependencies', return_value=[]))
        stack.enter_context(patch('scripts.setup_environment.process_resources', return_value=True))
        stack.enter_context(patch('scripts.setup_environment.process_skills', return_value=True))
        stack.enter_context(patch(
            'scripts.setup_environment.configure_all_mcp_servers', return_value=(True, [], empty_mcp_stats()),
        ))
        stack.enter_context(patch('scripts.setup_environment.set_all_os_env_variables', side_effect=record_os_env))
        if not real_launchers:
            stack.enter_context(patch(
                'scripts.setup_environment.create_launcher_script',
                return_value=(profile_dir / 'launch.sh', profile_dir / 'launch.sh'),
            ))
            stack.enter_context(patch('scripts.setup_environment.register_global_command', return_value=True))
        stack.enter_context(patch('scripts.setup_environment.is_admin', return_value=True))
        stack.enter_context(patch('sys.argv', ['setup_environment.py', str(config_path), *args]))
        try:
            setup_environment.main()
        except SystemExit as exc:
            exit_code = int(exc.code) if isinstance(exc.code, int) else 1
    return recorded.get('os_env'), exit_code


def _output(capsys: pytest.CaptureFixture[str]) -> str:
    """Return everything the run printed, color codes stripped; the summary goes to stderr under capture."""
    captured = capsys.readouterr()
    return _ANSI_SEQUENCE.sub('', captured.out + captured.err)


def _machine_wide_rows(output: str) -> list[str]:
    """Return the text of every [machine-wide] row of the installation summary."""
    return [line.split('[machine-wide] ', 1)[1] for line in output.splitlines() if '[machine-wide] ' in line]


def _run_isolated_with_loader_vars(config_path: Path, home: Path) -> Path:
    """Install an unpinned isolated profile declaring LOADER_VARS and return its profile directory."""
    _, exit_code = _run_setup(config_path, home, '--yes', '--skip-install')
    assert exit_code is None
    return home / '.claude' / PROFILE_NAME


class TestIsolatedInstallLeavesTheBaseAlone:
    """An isolated install of a base configuration writes only its own profile's .claude.json."""

    def test_base_file_changes_only_in_install_method_when_step_1_installs(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
    ) -> None:
        """oauthAccount and userID survive in the base file; the profile file gets the resolved global-config."""
        home = e2e_isolated_home['home']
        base_json = home / '.claude.json'
        base_before = {
            'oauthAccount': dict(BASE_ACCOUNT),
            'userID': 'base-user',
            'editorMode': 'emacs',
            'installMethod': 'global',
            'projects': {'/work': {'allowedTools': []}},
        }
        _write_json(base_json, base_before)
        config_path = _write_yaml(tmp_path / 'corp.yaml', _corp_like_config(isolated=True))

        _, exit_code = _run_setup(config_path, home, '--yes', install_claude=_install_recording_install_method(home))

        assert exit_code is None
        expected_base = dict(base_before, installMethod='native')
        assert _read_json(base_json) == expected_base, \
            'An isolated run may change the base ~/.claude.json only through the installer, in installMethod'
        profile_json = _read_json(home / '.claude' / PROFILE_NAME / '.claude.json')
        assert 'oauthAccount' not in profile_json
        assert 'userID' not in profile_json
        assert profile_json['editorMode'] == 'vim'
        assert profile_json['autoUpdates'] is False
        assert profile_json['autoInstallIdeExtension'] is False
        assert profile_json['installMethod'] == 'native', 'installMethod is propagated into the profile file'

    def test_base_file_is_byte_identical_under_skip_install(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
    ) -> None:
        """Without Step 1 nothing at all touches ~/.claude.json."""
        home = e2e_isolated_home['home']
        base_json = home / '.claude.json'
        _write_json(base_json, {'oauthAccount': dict(BASE_ACCOUNT), 'userID': 'base-user', 'installMethod': 'native'})
        base_bytes = base_json.read_bytes()
        config_path = _write_yaml(tmp_path / 'corp.yaml', _corp_like_config(isolated=True))

        _, exit_code = _run_setup(config_path, home, '--yes', '--skip-install')

        assert exit_code is None
        assert base_json.read_bytes() == base_bytes
        profile_json = _read_json(home / '.claude' / PROFILE_NAME / '.claude.json')
        assert 'oauthAccount' not in profile_json
        assert profile_json['installMethod'] == 'native'

    def test_base_run_still_writes_the_base_file(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
    ) -> None:
        """A base run of the same configuration deletes the account keys from ~/.claude.json."""
        home = e2e_isolated_home['home']
        base_json = home / '.claude.json'
        _write_json(base_json, {'oauthAccount': dict(BASE_ACCOUNT), 'userID': 'base-user', 'editorMode': 'emacs'})
        config_path = _write_yaml(tmp_path / 'corp.yaml', _corp_like_config(isolated=False))

        _, exit_code = _run_setup(config_path, home, '--yes', '--skip-install')

        assert exit_code is None
        base_after = _read_json(base_json)
        assert 'oauthAccount' not in base_after
        assert 'userID' not in base_after
        assert base_after['editorMode'] == 'vim'
        assert base_after['autoUpdates'] is False
        assert not any(
            (subdir / '.claude.json').exists() for subdir in (home / '.claude').iterdir() if subdir.is_dir()
        ), 'A base run writes no isolated .claude.json'


class TestIsolatedOsEnvVariablesStayInTheProfile:
    """os-env-variables of an isolated run reach the env loaders; only the binary controls reach the OS."""

    def test_pinned_isolated_run_writes_only_the_controls_to_the_os(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
    ) -> None:
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']
        yaml_vars: dict[str, str | None] = {'CORP_GATEWAY': 'https://gateway.example', 'OLD_TOKEN': None}
        config_path = _write_yaml(
            tmp_path / 'corp.yaml', _corp_like_config(isolated=True, os_env_variables=yaml_vars),
        )

        os_env, exit_code = _run_setup(config_path, home, '--yes', '--skip-install')

        assert exit_code is None
        assert os_env == dict.fromkeys(MACHINE_WIDE_CONTROLS, '1'), \
            'Only the three machine-wide controls may reach the OS environment from an isolated run'
        errors = validate_env_loader_files(claude_dir, yaml_vars, command_name=PROFILE_NAME)
        assert not errors, '\n'.join(errors)
        loader = (claude_dir / PROFILE_NAME / 'env.sh').read_text(encoding='utf-8')
        assert 'export CORP_GATEWAY="https://gateway.example"' in loader
        assert 'unset OLD_TOKEN\n' in loader
        for control in MACHINE_WIDE_CONTROLS:
            assert control not in loader, f'{control} is machine-wide and never enters a profile loader'

    def test_unpinned_isolated_run_deletes_only_the_controls_from_the_os(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
    ) -> None:
        """With no pin anywhere, the OS writer gets the three deletions and the YAML variables stay in the loaders."""
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']
        config_path = _write_yaml(
            tmp_path / 'personal.yaml',
            _corp_like_config(isolated=True, pinned=False, os_env_variables={'MY_VAR': 'x', 'GONE': None}),
        )

        os_env, exit_code = _run_setup(config_path, home, '--yes', '--skip-install')

        assert exit_code is None
        assert os_env == dict.fromkeys(MACHINE_WIDE_CONTROLS)
        loader = (claude_dir / PROFILE_NAME / 'env.sh').read_text(encoding='utf-8')
        assert 'export MY_VAR="x"' in loader
        assert 'unset GONE\n' in loader
        for control in MACHINE_WIDE_CONTROLS:
            assert control not in loader

    def test_base_run_writes_every_variable_to_the_os_and_no_loader(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
    ) -> None:
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']
        config_path = _write_yaml(
            tmp_path / 'corp.yaml',
            _corp_like_config(isolated=False, os_env_variables={'CORP_GATEWAY': 'g', 'OLD_TOKEN': None}),
        )

        os_env, exit_code = _run_setup(config_path, home, '--yes', '--skip-install')

        assert exit_code is None
        assert os_env == {
            'CORP_GATEWAY': 'g',
            'OLD_TOKEN': None,
            **dict.fromkeys(MACHINE_WIDE_CONTROLS, '1'),
        }
        assert not list(claude_dir.rglob('env.sh')), 'A base run generates no env loader files'


class TestStep16StaysInsideTheProfile:
    """The unpinned sweep edits the running profile's files and reports the copies other profiles hold."""

    @staticmethod
    def _seed_stale_controls(settings_path: Path, claude_json_path: Path) -> None:
        _write_json(settings_path, {'env': {'DISABLE_AUTOUPDATER': '1', 'DISABLE_UPDATES': '1', 'KEEP': 'x'}})
        _write_json(claude_json_path, {'autoUpdates': False, 'autoInstallIdeExtension': False, 'userID': 'u'})

    def test_unpinned_isolated_run_edits_its_own_files_and_reports_the_base_copy(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']
        profile_dir = claude_dir / PROFILE_NAME
        base_settings = claude_dir / 'settings.json'
        base_json = home / '.claude.json'
        self._seed_stale_controls(base_settings, base_json)
        self._seed_stale_controls(profile_dir / 'settings.json', profile_dir / '.claude.json')
        base_settings_bytes = base_settings.read_bytes()
        base_json_bytes = base_json.read_bytes()
        config_path = _write_yaml(
            tmp_path / 'personal.yaml',
            {'name': 'Personal', 'command-names': [PROFILE_NAME], 'user-settings': {'theme': 'dark'}},
        )

        _, exit_code = _run_setup(config_path, home, '--yes', '--skip-install')

        assert exit_code is None
        assert _read_json(profile_dir / 'settings.json') == {'env': {'KEEP': 'x'}}
        profile_json = _read_json(profile_dir / '.claude.json')
        assert 'autoUpdates' not in profile_json
        assert 'autoInstallIdeExtension' not in profile_json
        assert profile_json['userID'] == 'u'
        assert base_settings.read_bytes() == base_settings_bytes, 'The base settings.json is never edited'
        assert base_json.read_bytes() == base_json_bytes, 'The base .claude.json is never edited'
        output = _output(capsys)
        assert 'Stale update controls in other profiles (not edited by this run):' in output
        assert 'Stale update controls remain in other profiles' in output
        assert f'base: {base_settings} (DISABLE_AUTOUPDATER, DISABLE_UPDATES)' in output
        assert f'base: {base_json} (autoUpdates, autoInstallIdeExtension)' in output
        assert setup_environment.STALE_CONTROLS_RERUN_NOTE in output
        assert 'Stale update controls left in other profiles' in output

    def test_stale_copy_lines_name_the_profile_command_that_removes_them(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Each stale copy is reported with the --profile command of the profile that owns the file."""
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']
        base_settings = claude_dir / 'settings.json'
        other_settings = claude_dir / 'team-1' / 'settings.json'
        _write_json(base_settings, {'env': {'DISABLE_UPDATES': '1'}})
        _write_json(other_settings, {'env': {'DISABLE_UPDATES': '1'}})
        config_path = _write_yaml(
            tmp_path / 'team-2.yaml',
            {'name': 'Team 2', 'command-names': ['team-2'], 'user-settings': {'theme': 'dark'}},
        )

        _, exit_code = _run_setup(config_path, home, '--yes', '--skip-install')

        assert exit_code is None
        output = _output(capsys)
        assert f'team-1: {other_settings} (DISABLE_UPDATES) -- re-run with --profile team-1' in output
        assert f'base: {base_settings} (DISABLE_UPDATES) -- re-run with --profile base' in output
        assert 're-run each listed profile with --profile <name> to remove them' in output
        assert _read_json(base_settings) == {'env': {'DISABLE_UPDATES': '1'}}
        assert _read_json(other_settings) == {'env': {'DISABLE_UPDATES': '1'}}

    def test_unpinned_base_run_edits_its_own_files_and_reports_the_isolated_copy(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']
        other_dir = claude_dir / 'team-1'
        self._seed_stale_controls(claude_dir / 'settings.json', home / '.claude.json')
        self._seed_stale_controls(other_dir / 'settings.json', other_dir / '.claude.json')
        other_settings_bytes = (other_dir / 'settings.json').read_bytes()
        other_json_bytes = (other_dir / '.claude.json').read_bytes()
        config_path = _write_yaml(tmp_path / 'base.yaml', {'name': 'Base', 'user-settings': {'theme': 'dark'}})

        _, exit_code = _run_setup(config_path, home, '--yes', '--skip-install')

        assert exit_code is None
        base_settings = _read_json(claude_dir / 'settings.json')
        assert 'DISABLE_UPDATES' not in base_settings['env']
        assert 'DISABLE_AUTOUPDATER' not in base_settings['env']
        assert 'autoUpdates' not in _read_json(home / '.claude.json')
        assert (other_dir / 'settings.json').read_bytes() == other_settings_bytes
        assert (other_dir / '.claude.json').read_bytes() == other_json_bytes
        output = _output(capsys)
        assert f'team-1: {other_dir / "settings.json"} (DISABLE_AUTOUPDATER, DISABLE_UPDATES)' in output
        assert f'team-1: {other_dir / ".claude.json"} (autoUpdates, autoInstallIdeExtension)' in output

    def test_pinned_base_keeps_its_controls_through_an_unpinned_isolated_run(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """While the base pins a version nothing is swept and nothing is reported as stale."""
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']
        _write_json(claude_dir / 'manifest.json', {'name': None, 'claude_code_version': PINNED_VERSION})
        self._seed_stale_controls(claude_dir / 'settings.json', home / '.claude.json')
        profile_dir = claude_dir / PROFILE_NAME
        self._seed_stale_controls(profile_dir / 'settings.json', profile_dir / '.claude.json')
        snapshots = {
            path: path.read_bytes()
            for path in (claude_dir / 'settings.json', home / '.claude.json', profile_dir / 'settings.json')
        }
        config_path = _write_yaml(
            tmp_path / 'personal.yaml',
            {'name': 'Personal', 'command-names': [PROFILE_NAME], 'user-settings': {'theme': 'dark'}},
        )

        os_env, exit_code = _run_setup(config_path, home, '--yes', '--skip-install')

        assert exit_code is None
        for path, before in snapshots.items():
            assert path.read_bytes() == before, f'{path} must keep the controls the pinned base needs'
        assert _read_json(profile_dir / '.claude.json')['autoUpdates'] is False
        assert os_env == {}, 'No OS-level deletion while another profile pins'
        output = _output(capsys)
        assert 'Stale update controls' not in output
        assert "Another installed profile pins a Claude Code version ('base')" in output

    def test_pinned_isolated_run_keeps_its_own_controls(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
    ) -> None:
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']
        config_path = _write_yaml(tmp_path / 'corp.yaml', _corp_like_config(isolated=True))

        _, exit_code = _run_setup(config_path, home, '--yes', '--skip-install')

        assert exit_code is None
        profile_dir = claude_dir / PROFILE_NAME
        assert _read_json(profile_dir / '.claude.json')['autoUpdates'] is False
        config_env = _read_json(profile_dir / 'config.json')['env']
        for control in MACHINE_WIDE_CONTROLS:
            assert config_env[control] == '1'


class TestAccountKeyWarning:
    """A global-config null for an account key names the profile it signs out, before consent."""

    def test_dry_run_names_the_profile_and_file_without_printing_values(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        home = e2e_isolated_home['home']
        profile_json = home / '.claude' / PROFILE_NAME / '.claude.json'
        _write_json(profile_json, {'oauthAccount': {'emailAddress': 'profile@example.com'}, 'userID': 'profile-user'})
        _write_json(home / '.claude.json', {'oauthAccount': dict(BASE_ACCOUNT), 'userID': 'base-user'})
        config_path = _write_yaml(tmp_path / 'corp.yaml', _corp_like_config(isolated=True))

        _, exit_code = _run_setup(config_path, home, '--dry-run')

        assert exit_code == 0
        output = _output(capsys)
        assert (
            f"[!] global-config deletes oauthAccount from {profile_json} (profile '{PROFILE_NAME}'): "
            'the account signed in there is signed out'
        ) in output
        assert f"[!] global-config deletes userID from {profile_json} (profile '{PROFILE_NAME}')" in output
        assert f'global-config deletes oauthAccount from {home / ".claude.json"}' not in output, \
            'The base file is not the target of an isolated run, so it is not named as signed out'
        for secret in ('profile@example.com', 'profile-user', 'base@example.com', 'base-user'):
            assert secret not in output, 'Account values are never printed'
        assert not (home / '.claude' / PROFILE_NAME / 'config.json').exists(), 'A dry run writes nothing'

    def test_dry_run_is_silent_when_the_target_holds_no_account(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        home = e2e_isolated_home['home']
        _write_json(home / '.claude' / PROFILE_NAME / '.claude.json', {'editorMode': 'emacs', 'oauthAccount': None})
        _write_json(home / '.claude.json', {'oauthAccount': dict(BASE_ACCOUNT), 'userID': 'base-user'})
        config_path = _write_yaml(tmp_path / 'corp.yaml', _corp_like_config(isolated=True))

        _, exit_code = _run_setup(config_path, home, '--dry-run')

        assert exit_code == 0
        output = _output(capsys)
        assert 'global-config deletes' not in output

    def test_base_run_summary_warns_and_the_run_proceeds(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The warning never blocks: with --yes the key is deleted from the base file as asked."""
        home = e2e_isolated_home['home']
        base_json = home / '.claude.json'
        _write_json(base_json, {'userID': 'base-user', 'editorMode': 'emacs'})
        config_path = _write_yaml(tmp_path / 'corp.yaml', _corp_like_config(isolated=False))

        _, exit_code = _run_setup(config_path, home, '--yes', '--skip-install')

        assert exit_code is None
        output = _output(capsys)
        assert f"[!] global-config deletes userID from {base_json} (profile 'base')" in output
        assert 'global-config deletes oauthAccount' not in output, 'The base file holds no oauthAccount'
        assert 'base-user' not in output
        assert 'userID' not in _read_json(base_json)

    def test_base_run_is_silent_when_the_base_file_lacks_the_keys(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        home = e2e_isolated_home['home']
        _write_json(home / '.claude.json', {'editorMode': 'emacs'})
        config_path = _write_yaml(tmp_path / 'corp.yaml', _corp_like_config(isolated=False))

        _, exit_code = _run_setup(config_path, home, '--dry-run')

        assert exit_code == 0
        assert 'global-config deletes' not in _output(capsys)


class TestMachineWideWritesNamedBeforeConsent:
    """The summary of an isolated run lists every write that leaves the profile directory."""

    def test_pinned_isolated_dry_run_lists_the_binary_install_method_and_controls(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        home = e2e_isolated_home['home']
        config_path = _write_yaml(
            tmp_path / 'corp.yaml',
            _corp_like_config(isolated=True, os_env_variables={'CORP_GATEWAY': 'g'}),
        )

        _, exit_code = _run_setup(config_path, home, '--dry-run')

        assert exit_code == 0
        output = _output(capsys)
        assert 'Machine-wide writes (shared by every profile on this machine):' in output
        assert f'[machine-wide] Claude Code binary: install or upgrade to {PINNED_VERSION} (used by every profile)' in output
        assert (
            f'[machine-wide] {home / ".claude.json"}: installMethod, recorded by the Claude Code installer '
            'when it installs, upgrades or migrates the binary'
        ) in output
        assert f'[machine-wide] Claude Code version pin {PINNED_VERSION}: holds the binary every profile uses' in output
        rows = _machine_wide_rows(output)
        pin_index = rows.index(f'Claude Code version pin {PINNED_VERSION}: holds the binary every profile uses')
        assert rows[pin_index + 1] == (
            f'IDE extension {setup_environment.IDE_EXTENSION_ID} {PINNED_VERSION}: '
            f'installed into {DETECTED_IDE_CLI} (used by every profile)'
        ), 'Step 2 installs the pinned extension into every detected IDE, right after the pin row'
        for control in MACHINE_WIDE_CONTROLS:
            assert f'[machine-wide] OS environment: {control}="1"' in output
        assert f'[machine-wide] {home / ".local" / "bin"}: command wrapper(s) {PROFILE_NAME}' in output
        assert 'OS environment variables: 1 in the profile env loaders, 3 machine-wide (listed below)' in output
        assert '[machine-wide] OS environment: CORP_GATEWAY' not in output, \
            'A profile variable never appears as a machine-wide write'

    def test_unpinned_isolated_dry_run_under_skip_install_lists_the_deletions_only(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        home = e2e_isolated_home['home']
        config_path = _write_yaml(tmp_path / 'personal.yaml', _corp_like_config(isolated=True, pinned=False))

        _, exit_code = _run_setup(config_path, home, '--dry-run', '--skip-install')

        assert exit_code == 0
        output = _output(capsys)
        assert 'Machine-wide writes (shared by every profile on this machine):' in output
        assert 'recorded by the Claude Code installer' not in output, \
            'Under --skip-install no installer runs, so no installMethod write is named'
        assert 'Claude Code binary:' not in output
        assert '[machine-wide] IDE extension' not in output, 'An unpinned run installs no extension'
        for control in MACHINE_WIDE_CONTROLS:
            assert f'[machine-wide] OS environment: delete {control}' in output

    def test_pinned_isolated_dry_run_under_skip_install_names_no_ide_extension(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--skip-install skips Step 2 with Step 1, so the pin row stands alone."""
        home = e2e_isolated_home['home']
        config_path = _write_yaml(tmp_path / 'corp.yaml', _corp_like_config(isolated=True))

        _, exit_code = _run_setup(config_path, home, '--dry-run', '--skip-install')

        assert exit_code == 0
        output = _output(capsys)
        assert f'[machine-wide] Claude Code version pin {PINNED_VERSION}: holds the binary every profile uses' in output
        assert '[machine-wide] IDE extension' not in output

    def test_isolated_dry_run_names_destinations_project_servers_and_dependencies(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Content that lands outside the profile is named per destination, server and command group.

        A destination spelled against the base config home is re-rooted into
        the profile, so it is marked [re-rooted] instead of machine-wide.
        """
        home = e2e_isolated_home['home']
        (tmp_path / 'payload.txt').write_text('payload\n', encoding='utf-8')
        config = _corp_like_config(isolated=True)
        config['files-to-download'] = [
            {'source': 'payload.txt', 'dest': '~/.serena/x.yml'},
            {'source': 'payload.txt', 'dest': '~/.claude/x.txt'},
            {'source': 'payload.txt', 'dest': f'~/.claude/{PROFILE_NAME}/x.txt'},
        ]
        config['mcp-servers'] = [
            {'name': 'shared-server', 'scope': 'project', 'transport': 'http', 'url': 'http://localhost:3001/shared'},
            {'name': 'mine-server', 'scope': 'user', 'transport': 'http', 'url': 'http://localhost:3002/mine'},
        ]
        config['dependencies'] = {'common': ["echo 'dependency-installed'"]}
        config_path = _write_yaml(tmp_path / 'corp.yaml', config)

        _, exit_code = _run_setup(config_path, home, '--dry-run')

        assert exit_code == 0
        output = _output(capsys)
        rows = _machine_wide_rows(output)
        assert 'files-to-download outside the profile: ~/.serena/x.yml' in rows
        assert f'[re-rooted] files-to-download: ~/.claude/x.txt -> ~/.claude/{PROFILE_NAME}/x.txt' in output
        assert not any(
            PROFILE_NAME in row or row.endswith('~/.claude/x.txt') for row in rows if row.startswith('files-to-download')
        ), 'A destination inside the profile is not a machine-wide write'
        assert '.mcp.json in the working directory: project-scope MCP server(s) shared-server' in rows
        assert not any('mine-server' in row for row in rows), 'A user-scope server lands in the profile'
        assert 'Dependency commands: run machine-wide (listed above)' in rows

    def test_unpinned_isolated_dry_run_beside_a_pinned_base_keeps_the_installed_binary(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The base pins a version, so Step 1 keeps the installed binary and the row says so."""
        home = e2e_isolated_home['home']
        _write_json(e2e_isolated_home['claude_dir'] / 'manifest.json', {'name': None, 'claude_code_version': PINNED_VERSION})
        config_path = _write_yaml(tmp_path / 'personal.yaml', _corp_like_config(isolated=True, pinned=False))

        with patch('scripts.setup_environment._installed_claude_version', return_value='2.1.80'):
            _, exit_code = _run_setup(config_path, home, '--dry-run')

        assert exit_code == 0
        output = _output(capsys)
        assert '[machine-wide] Claude Code binary: keep the installed version 2.1.80 (used by every profile)' in output
        assert 'install or upgrade' not in output
        assert f'[machine-wide] {home / ".claude.json"}: installMethod, recorded by the Claude Code installer' in output, \
            'A kept binary can still be migrated, so the installMethod record is named'

    def test_base_dry_run_has_no_machine_wide_block(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A base run's writes are the base profile's own; its OS variables are labeled machine-wide inline."""
        home = e2e_isolated_home['home']
        config_path = _write_yaml(
            tmp_path / 'corp.yaml',
            _corp_like_config(isolated=False, os_env_variables={'CORP_GATEWAY': 'g'}),
        )

        _, exit_code = _run_setup(config_path, home, '--dry-run')

        assert exit_code == 0
        output = _output(capsys)
        assert 'Machine-wide writes' not in output
        assert 'OS environment variables: 4 (machine-wide)' in output


class TestFinalSummaryNamesTheFilesWritten:
    """The completion summary names the files this run wrote, per profile."""

    def test_isolated_run_names_the_profile_files_and_loader_counts(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """An unpinned isolated run: one declared control stays OS-level, the rest go to the loaders."""
        home = e2e_isolated_home['home']
        profile_dir = home / '.claude' / PROFILE_NAME
        config_path = _write_yaml(
            tmp_path / 'personal.yaml',
            _corp_like_config(
                isolated=True, pinned=False,
                os_env_variables={'DISABLE_UPDATES': '1', 'FOO': 'x', 'BAR': None},
            ),
        )

        _, exit_code = _run_setup(config_path, home, '--yes', '--skip-install')

        assert exit_code is None
        output = _output(capsys)
        assert 'OS environment variables: 1 configured (machine-wide)' in output
        assert 'OS environment variables: 2 deleted (machine-wide)' in output, \
            'The two controls the YAML does not declare are deleted from the OS environment'
        assert 'Profile environment variables: 1 exported by the env loaders' in output
        assert 'Profile environment variables: 1 unset by the env loaders' in output
        assert f'User settings: built into {profile_dir / "config.json"}' in output
        assert 'User settings: configured in ~/.claude/settings.json' not in output
        assert f'Global config: configured in {profile_dir / ".claude.json"}' in output
        assert f'Global config: configured in {home / ".claude.json"}' not in output

    def test_base_run_names_the_base_files_without_the_machine_wide_label(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        home = e2e_isolated_home['home']
        config_path = _write_yaml(
            tmp_path / 'base.yaml',
            _corp_like_config(
                isolated=False, pinned=False,
                os_env_variables={'DISABLE_UPDATES': '1', 'FOO': 'x', 'BAR': None},
            ),
        )

        _, exit_code = _run_setup(config_path, home, '--yes', '--skip-install')

        assert exit_code is None
        output = _output(capsys)
        assert re.search(r'^\s*\* OS environment variables: 2 configured$', output, re.MULTILINE), output
        assert re.search(r'^\s*\* OS environment variables: 3 deleted$', output, re.MULTILINE), output
        assert 'configured (machine-wide)' not in output
        assert 'Profile environment variables' not in output, 'A base run has no env loaders'
        assert 'User settings: configured in ~/.claude/settings.json' in output
        assert 'User settings: built into' not in output
        assert f'Global config: configured in {home / ".claude.json"}' in output


class TestLoaderFilesWorkWhenSourced:
    """Loader files generated by an isolated run take effect in the shells that source them."""

    @staticmethod
    def _loader_config(tmp_path: Path) -> Path:
        return _write_yaml(
            tmp_path / 'personal.yaml',
            _corp_like_config(isolated=True, pinned=False, os_env_variables=LOADER_VARS),
        )

    def test_env_fish_is_generated_with_set_and_erase_lines_when_fish_is_installed(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
    ) -> None:
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']
        real_which = shutil.which

        def which_with_fish(cmd: str, *args: Any, **kwargs: Any) -> str | None:
            return '/usr/bin/fish' if cmd == 'fish' else real_which(cmd, *args, **kwargs)

        with patch('scripts.setup_environment.shutil.which', side_effect=which_with_fish):
            profile_dir = _run_isolated_with_loader_vars(self._loader_config(tmp_path), home)

        assert (profile_dir / 'env.fish').is_file(), 'fish is installed, so the fish loader is generated'
        errors = validate_env_loader_files(claude_dir, LOADER_VARS, command_name=PROFILE_NAME, expect_fish=True)
        assert not errors, '\n'.join(errors)
        content = (profile_dir / 'env.fish').read_text(encoding='utf-8')
        assert 'set -gx E2E_KEPT "kept-value"\n' in content
        assert 'set -q E2E_GONE; and set -e E2E_GONE\n' in content
        assert 'E2E_GONE "' not in content, 'A null entry is never exported'

    def test_env_fish_is_absent_without_fish(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
    ) -> None:
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']
        real_which = shutil.which

        def which_without_fish(cmd: str, *args: Any, **kwargs: Any) -> str | None:
            return None if cmd == 'fish' else real_which(cmd, *args, **kwargs)

        with patch('scripts.setup_environment.shutil.which', side_effect=which_without_fish):
            profile_dir = _run_isolated_with_loader_vars(self._loader_config(tmp_path), home)

        assert not (profile_dir / 'env.fish').exists()
        errors = validate_env_loader_files(claude_dir, LOADER_VARS, command_name=PROFILE_NAME, expect_fish=True)
        assert errors == [
            f'Per-command Fish env loader not found although fish is installed: {profile_dir / "env.fish"}',
        ]

    def test_bash_loader_unsets_the_inherited_variable_and_exports_the_declared_one(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
    ) -> None:
        """Sourcing env.sh in a shell that inherited the deleted variable removes it."""
        bash = find_bash()
        if bash is None:
            pytest.skip('bash unavailable')
        profile_dir = _run_isolated_with_loader_vars(self._loader_config(tmp_path), e2e_isolated_home['home'])
        env_sh = (profile_dir / 'env.sh').as_posix()

        probe = (
            f'export E2E_GONE=1; export E2E_KEPT=stale; . "{env_sh}"; '
            '[ -z "${E2E_GONE+x}" ] && [ "$E2E_KEPT" = "kept-value" ]'
        )
        completed = subprocess.run([bash, '-c', probe], capture_output=True, text=True, check=False, timeout=60)

        assert completed.returncode == 0, f'env.sh did not unset E2E_GONE or export E2E_KEPT:\n{completed.stderr}'

    @pytest.mark.skipif(sys.platform != 'win32', reason='env.cmd is generated only on Windows')
    def test_cmd_loader_unsets_the_inherited_variable_and_sets_the_declared_one(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
    ) -> None:
        """Calling env.cmd in a CMD session that inherited the deleted variable removes it."""
        profile_dir = _run_isolated_with_loader_vars(self._loader_config(tmp_path), e2e_isolated_home['home'])
        probe = tmp_path / 'probe.cmd'
        probe.write_text(
            '@echo off\r\n'
            'set E2E_GONE=1\r\n'
            'set E2E_KEPT=stale\r\n'
            f'call "{profile_dir / "env.cmd"}"\r\n'
            'if defined E2E_GONE exit /b 1\r\n'
            'if not "%E2E_KEPT%"=="kept-value" exit /b 2\r\n'
            'exit /b 0\r\n',
            encoding='utf-8',
        )

        completed = subprocess.run(
            ['cmd', '/d', '/c', str(probe)], capture_output=True, text=True, check=False, timeout=60,
        )

        assert completed.returncode == 0, \
            f'env.cmd left E2E_GONE defined or E2E_KEPT stale (exit {completed.returncode})'

    @pytest.mark.skipif(sys.platform != 'win32', reason='env.ps1 is generated only on Windows')
    def test_powershell_loader_removes_the_inherited_variable_and_sets_the_declared_one(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
    ) -> None:
        """Dot-sourcing env.ps1 in a PowerShell session that inherited the deleted variable removes it."""
        powershell = find_powershell()
        if powershell is None:
            pytest.skip('PowerShell unavailable')
        profile_dir = _run_isolated_with_loader_vars(self._loader_config(tmp_path), e2e_isolated_home['home'])

        probe = (
            "$env:E2E_GONE='1'; $env:E2E_KEPT='stale'; "
            f". '{profile_dir / 'env.ps1'}'; "
            "exit [int]((Test-Path Env:E2E_GONE) -or ($env:E2E_KEPT -ne 'kept-value'))"
        )
        completed = subprocess.run(
            [powershell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', probe],
            capture_output=True, text=True, check=False, timeout=120,
        )

        assert completed.returncode == 0, f'env.ps1 left E2E_GONE set or E2E_KEPT stale:\n{completed.stderr}'


def _run_isolated_with_real_launchers(config_path: Path, home: Path) -> Path:
    """Install an isolated profile with its launchers and wrappers written for real.

    Returns:
        The profile directory.
    """
    _, exit_code = _run_setup(config_path, home, '--yes', '--skip-install', real_launchers=True)
    assert exit_code is None
    return home / '.claude' / PROFILE_NAME


def _write_recording_claude(stub_dir: Path, record: Path) -> None:
    """Write a stub claude that records the loader variables it inherits.

    The record names CLAUDE_CONFIG_DIR as a host path and each loader
    variable as its value or UNSET_MARKER, so a test can tell an unset
    variable from an empty one.

    Args:
        stub_dir: Directory that receives the stub; put first on PATH.
        record: File the stub writes.
    """
    stub_dir.mkdir(parents=True, exist_ok=True)
    stub = stub_dir / 'claude'
    stub.write_text(
        '#!/bin/sh\n'
        'if [ "$1" = "--version" ]; then echo "2.1.0 (Claude Code)"; exit 0; fi\n'
        '{\n'
        '  printf \'CLAUDE_CONFIG_DIR=%s\\n\' "$(cygpath -m "${CLAUDE_CONFIG_DIR:-}")"\n'
        f'  printf \'E2E_KEPT=%s\\n\' "${{E2E_KEPT-{UNSET_MARKER}}}"\n'
        f'  printf \'E2E_GONE=%s\\n\' "${{E2E_GONE-{UNSET_MARKER}}}"\n'
        '} > "' + record.as_posix() + '"\n',
        encoding='utf-8',
        newline='\n',
    )
    stub.chmod(0o755)


def _probe_environment(home: Path, stub_dir: Path) -> dict[str, str]:
    """Build the environment a probe shell starts with.

    The stub claude leads PATH, the home directories name the isolated
    home, and no loader variable or CLAUDE_CONFIG_DIR is inherited.

    Returns:
        The environment for subprocess.run.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {'CLAUDE_CONFIG_DIR', 'E2E_KEPT', 'E2E_GONE'}
    }
    env['HOME'] = str(home)
    env['USERPROFILE'] = str(home)
    env['PATH'] = f'{stub_dir}{os.pathsep}' + env.get('PATH', '')
    return env


def _parse_record(path: Path) -> dict[str, str]:
    """Read a KEY=VALUE record file into a dict."""
    assert path.exists(), f'{path.name} was never written: the stub claude did not run'
    return dict(line.split('=', 1) for line in path.read_text(encoding='utf-8').splitlines() if '=' in line)


def _caller_values(output: str) -> dict[str, str]:
    """Return the CALLER_* lines a probe printed, keyed by variable."""
    return dict(
        line.removeprefix('CALLER_').split('=', 1)
        for line in output.splitlines()
        if line.startswith('CALLER_') and '=' in line
    )


def _assert_caller_unchanged(label: str, caller: dict[str, str], before: Path, after: Path) -> None:
    """Assert that the shell that ran an entry point kept its environment.

    Args:
        label: The entry point, for the failure message.
        caller: The CALLER_* values the probe printed after the call.
        before: The shell's environment listing taken before the call.
        after: The same listing taken after the call.
    """
    assert caller.get('GONE') == 'preset', (
        f'{label} removed E2E_GONE from the calling shell: the loader was applied to the caller'
    )
    assert caller.get('KEPT') == UNSET_MARKER, (
        f'{label} left E2E_KEPT={caller.get("KEPT")!r} in the calling shell: the loader was applied to the caller'
    )
    assert after.read_text(encoding='utf-8') == before.read_text(encoding='utf-8'), (
        f'{label} changed the calling shell environment:\n--- before ---\n'
        f'{before.read_text(encoding="utf-8")}\n--- after ---\n{after.read_text(encoding="utf-8")}'
    )


def _assert_session_received_loader(label: str, record: dict[str, str], profile_dir: Path) -> None:
    """Assert that the session an entry point started received the loader through launch.sh.

    Args:
        label: The entry point, for the failure message.
        record: What the stub claude recorded.
        profile_dir: The profile directory the session must use.
    """
    assert Path(record['CLAUDE_CONFIG_DIR']).resolve() == profile_dir.resolve(), f'{label}: {record}'
    assert record['E2E_KEPT'] == 'kept-value', f'{label}: the session did not receive the exported variable'
    assert record['E2E_GONE'] == UNSET_MARKER, f'{label}: the session kept the variable the loader unsets'


@pytest.mark.skipif(sys.platform != 'win32', reason='runs the generated entry points under cmd.exe and PowerShell')
class TestWindowsEntryPointsLeaveTheCallingShellAlone:
    """The cmd.exe and PowerShell entry points change nothing in the shell that runs them.

    A batch file run from a cmd.exe prompt executes in that shell, and $env:
    is process-wide in PowerShell, so a loader applied by a wrapper would stay
    in the window after the session ends and reach a plain ``claude`` started
    next. The session itself still receives every loader variable: launch.sh
    sources env.sh in the bash process that execs Claude Code. Each probe
    presets the variable the loader unsets, leaves the one it exports
    undefined, lists its environment, runs the entry point, and lists it
    again.
    """

    @staticmethod
    def _config(tmp_path: Path) -> Path:
        config = _corp_like_config(isolated=True, pinned=False, os_env_variables=LOADER_VARS)
        config['command-names'] = [PROFILE_NAME, PROFILE_ALIAS]
        return _write_yaml(tmp_path / 'personal.yaml', config)

    def _install(self, e2e_isolated_home: dict[str, Path], tmp_path: Path) -> tuple[Path, Path, Path]:
        """Install the profile and the stub claude.

        Returns:
            The profile directory, the stub directory and the stub's record file.
        """
        if not WINDOWS_GIT_BASH.exists():
            pytest.skip('the generated entry points run Git Bash from its standard location')
        profile_dir = _run_isolated_with_real_launchers(self._config(tmp_path), e2e_isolated_home['home'])
        for loader in ('env.sh', 'env.cmd', 'env.ps1'):
            assert (profile_dir / loader).is_file(), f'{loader} was not generated'
        stub_dir = tmp_path / 'stub-bin'
        record = stub_dir / 'record.txt'
        _write_recording_claude(stub_dir, record)
        return profile_dir, stub_dir, record

    @pytest.mark.parametrize('entry_point', [f'{PROFILE_NAME}.cmd', f'{PROFILE_ALIAS}.cmd', 'start.cmd'])
    def test_cmd_entry_point_keeps_the_caller_and_loads_the_session(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        entry_point: str,
    ) -> None:
        """A .cmd wrapper or start.cmd leaves cmd.exe as it was; the session gets the set and the unset."""
        profile_dir, stub_dir, record = self._install(e2e_isolated_home, tmp_path)
        script = (profile_dir if entry_point == 'start.cmd' else e2e_isolated_home['local_bin']) / entry_point
        assert script.is_file(), f'{script} was not written'
        before, after = tmp_path / 'before.txt', tmp_path / 'after.txt'
        # cmd.exe reads < and > as redirections unless escaped with ^.
        unset = UNSET_MARKER.replace('<', '^<').replace('>', '^>')
        probe = tmp_path / 'probe.cmd'
        probe.write_text(
            '@echo off\r\n'
            'set "E2E_GONE=preset"\r\n'
            'set "E2E_KEPT="\r\n'
            f'set > "{before}"\r\n'
            f'call "{script}" --probe-arg\r\n'
            f'set > "{after}"\r\n'
            f'if defined E2E_GONE (echo CALLER_GONE=%E2E_GONE%) else (echo CALLER_GONE={unset})\r\n'
            f'if defined E2E_KEPT (echo CALLER_KEPT=%E2E_KEPT%) else (echo CALLER_KEPT={unset})\r\n',
            encoding='utf-8',
        )

        completed = subprocess.run(
            ['cmd.exe', '/d', '/c', str(probe)],
            capture_output=True, text=True, check=False, timeout=120,
            env=_probe_environment(e2e_isolated_home['home'], stub_dir),
        )

        assert completed.returncode == 0, f'{entry_point} failed:\n{completed.stdout}\n{completed.stderr}'
        _assert_session_received_loader(entry_point, _parse_record(record), profile_dir)
        _assert_caller_unchanged(entry_point, _caller_values(completed.stdout), before, after)

    @pytest.mark.parametrize('entry_point', [f'{PROFILE_NAME}.ps1', f'{PROFILE_ALIAS}.ps1', 'start.ps1'])
    def test_powershell_entry_point_keeps_the_caller_and_loads_the_session(
        self,
        e2e_isolated_home: dict[str, Path],
        tmp_path: Path,
        entry_point: str,
    ) -> None:
        """A .ps1 wrapper or start.ps1 leaves PowerShell as it was; the session gets the set and the unset."""
        powershell = find_powershell()
        if powershell is None:
            pytest.skip('PowerShell unavailable')
        profile_dir, stub_dir, record = self._install(e2e_isolated_home, tmp_path)
        script = (profile_dir if entry_point == 'start.ps1' else e2e_isolated_home['local_bin']) / entry_point
        assert script.is_file(), f'{script} was not written'
        before, after = tmp_path / 'before.txt', tmp_path / 'after.txt'
        listing = 'Get-ChildItem Env: | Sort-Object Name | ForEach-Object { "$($_.Name)=$($_.Value)" }'
        probe = tmp_path / 'probe.ps1'
        probe.write_text(
            "$env:E2E_GONE = 'preset'\n"
            'Remove-Item -Path Env:E2E_KEPT -ErrorAction SilentlyContinue\n'
            f"{listing} | Set-Content -LiteralPath '{before}'\n"
            f"& '{script}' --probe-arg | Out-Null\n"
            f"{listing} | Set-Content -LiteralPath '{after}'\n"
            f"\"CALLER_GONE=$(if (Test-Path Env:E2E_GONE) {{ $env:E2E_GONE }} else {{ '{UNSET_MARKER}' }})\"\n"
            f"\"CALLER_KEPT=$(if (Test-Path Env:E2E_KEPT) {{ $env:E2E_KEPT }} else {{ '{UNSET_MARKER}' }})\"\n",
            encoding='utf-8',
        )

        completed = subprocess.run(
            [powershell, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(probe)],
            capture_output=True, text=True, check=False, timeout=120,
            env=_probe_environment(e2e_isolated_home['home'], stub_dir),
        )

        assert completed.returncode == 0, f'{entry_point} failed:\n{completed.stdout}\n{completed.stderr}'
        _assert_session_received_loader(entry_point, _parse_record(record), profile_dir)
        _assert_caller_unchanged(entry_point, _caller_values(completed.stdout), before, after)
