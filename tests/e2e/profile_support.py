"""Helpers for the E2E tests that re-run installed profiles through main().

The tests install real local YAML files into an isolated home with the real
launcher, wrapper, profile-config and manifest writers; only network access,
the Claude Code binary, MCP registration, OS-level variables and the Windows
PATH registry are replaced. A configuration is written to disk so its
resolved path is a real identity the manifest records and a re-run compares.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from scripts import setup_environment
from tests.conftest import empty_mcp_stats
from tests.e2e.expected import EXPECTED_FILES

REPO_ROOT = Path(__file__).resolve().parents[2]


CHILD_RUNNER = '''\
"""Child runner: setup_environment.main() with the machine-wide writers replaced."""
from unittest.mock import patch

from scripts import setup_environment
from tests.e2e.fixtures import setup_child

_real_find = setup_environment.find_command


def _find(name: str) -> str | None:
    return '/usr/bin/claude' if name == 'claude' else _real_find(name)


with (
    patch.object(setup_environment, 'find_command', _find),
    patch.object(setup_environment, 'ensure_local_bin_in_path', lambda: None),
    patch.object(setup_environment, 'refresh_path_from_registry', lambda: None),
):
    setup_child.main()
'''


def write_child_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Write the runner a parent run starts its child runs through.

    The runner stands in for sys.argv[0]: a child run executes it with the
    test interpreter, so every child goes through setup_child.main() with the
    machine-wide writers replaced and the Claude Code binary stubbed.

    Args:
        tmp_path: The test's temporary directory.
        monkeypatch: Sets PYTHONPATH so the child imports the repository.

    Returns:
        The runner path, to pass as argv0 to run_main().
    """
    runner = tmp_path / 'runner.py'
    runner.write_text(CHILD_RUNNER, encoding='utf-8')
    monkeypatch.setenv('PYTHONPATH', str(REPO_ROOT))
    return runner


def write_config(directory: Path, name: str, config: dict[str, Any]) -> Path:
    """Write a configuration to a YAML file and return its path."""
    path = directory / name
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding='utf-8')
    return path


def run_main(
    argv: list[str],
    *,
    interactive: bool = False,
    answers: list[str] | None = None,
    argv0: str = 'setup_environment.py',
    os_env_writes: list[dict[str, str | None]] | None = None,
) -> int:
    """Run main() with the given arguments and return its exit code.

    An interactive run answers every prompt from ``answers`` in order,
    the numbered component picker included: the questionary tier is
    unavailable to the run (its checkbox needs a real console), so a
    configuration with components and no selector shows the numbered
    picker, whose toggles and confirming Enter come from ``answers`` before
    the installation confirmation does.

    Args:
        argv: Arguments after the program name.
        interactive: Whether stdin counts as a terminal; prompts then read
            from ``answers`` in order.
        answers: The answers an interactive run gives, one per prompt.
        argv0: The program name main() sees.
        os_env_writes: When given, every dict the run hands to the OS
            environment writer is appended to it.

    Returns:
        The exit code; 0 when main() returns normally.
    """
    original_find = setup_environment.find_command
    remaining = list(answers or [])

    def _find_command(name: str) -> str | None:
        return '/usr/bin/claude' if name == 'claude' else original_find(name)

    def _read_answer(_prompt: str) -> str:
        return remaining.pop(0) if remaining else ''

    def _record_os_env(env_vars: dict[str, str | None]) -> bool:
        if os_env_writes is not None:
            os_env_writes.append(dict(env_vars))
        return True

    # Every run starts from the environment the test prepared: main() exports
    # the profile's CLAUDE_CONFIG_DIR and the IDE auto-install control into
    # its own process, which a real shell never carries into the next run
    with (
        patch.dict(os.environ, {}, clear=False),
        patch.dict(sys.modules, {'questionary': None}),
        patch('scripts.setup_environment.validate_all_config_files', return_value=(True, [])),
        patch('scripts.setup_environment.cleanup_temp_paths_from_registry', return_value=(0, [])),
        patch('scripts.setup_environment.set_all_os_env_variables', side_effect=_record_os_env),
        patch('scripts.setup_environment.configure_all_mcp_servers',
              return_value=(True, [], empty_mcp_stats())),
        patch('scripts.setup_environment.find_command', side_effect=_find_command),
        patch('scripts.setup_environment._dev_tty_available', return_value=False),
        patch('scripts.setup_environment._read_user_input', side_effect=_read_answer),
        patch('sys.stdin.isatty', return_value=interactive),
        patch('sys.argv', [argv0, *argv]),
    ):
        os.environ.pop('CLAUDE_CONFIG_DIR', None)
        try:
            setup_environment.main()
        except SystemExit as exc:
            code = exc.code
            assert isinstance(code, int)
            return code
    return 0


def wrapper_paths(local_bin: Path, name: str) -> list[Path]:
    """Return the ~/.local/bin entries the setup registers for one command name."""
    templates = [template for template in EXPECTED_FILES if template.startswith('{local_bin}/')]
    return [Path(template.replace('{local_bin}', str(local_bin)).replace('{cmd}', name)) for template in templates]


def wrappers_exist(local_bin: Path, name: str) -> bool:
    """Report whether every wrapper of a command name exists."""
    return all(path.exists() or path.is_symlink() for path in wrapper_paths(local_bin, name))


def wrappers_absent(local_bin: Path, name: str) -> bool:
    """Report whether no wrapper of a command name exists."""
    return not any(path.exists() or path.is_symlink() for path in wrapper_paths(local_bin, name))


def wrapper_targets_profile(local_bin: Path, name: str, profile_dir: Path) -> bool:
    """Report whether the command name launches the given profile."""
    if sys.platform == 'win32':
        ps1 = (local_bin / f'{name}.ps1').read_text(encoding='utf-8')
        return str(profile_dir / 'start.ps1') in ps1
    link = local_bin / name
    return link.is_symlink() and Path(os.readlink(link)) == profile_dir / 'launch.sh'


def read_manifest(profile_dir: Path) -> dict[str, Any]:
    """Read a profile's manifest."""
    content: dict[str, Any] = json.loads((profile_dir / 'manifest.json').read_text(encoding='utf-8'))
    return content


def write_legacy_manifest(
    profile_dir: Path,
    name: str | None,
    command_names: list[str],
    *,
    config_source: str,
    config_source_type: str,
    config_source_url: str | None,
) -> Path:
    """Write a manifest in the shape installs wrote before identities were recorded."""
    profile_dir.mkdir(parents=True, exist_ok=True)
    path = profile_dir / 'manifest.json'
    path.write_text(json.dumps({
        'name': name,
        'version': None,
        'claude_code_version': None,
        'config_source': config_source,
        'config_source_url': config_source_url,
        'config_source_type': config_source_type,
        'installed_at': '2026-01-01T00:00:00+00:00',
        'command_names': command_names,
    }, indent=2), encoding='utf-8')
    return path


def home_state(home: Path, skip: Callable[[Path], bool] | None = None) -> dict[str, str]:
    """Snapshot every entry under the home: links by target, files by content, directories by name."""
    state: dict[str, str] = {}
    for entry in sorted(home.rglob('*')):
        if skip is not None and skip(entry):
            continue
        key = entry.relative_to(home).as_posix()
        if entry.is_symlink():
            state[key] = f'link:{os.readlink(entry)}'
        elif entry.is_dir():
            state[key] = 'dir'
        else:
            state[key] = f'file:{entry.read_bytes()!r}'
    return state
