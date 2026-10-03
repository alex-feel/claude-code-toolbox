"""E2E tests of the external tools a linked profile depends on, against the real binaries.

Two questions a shared skills/ directory and a refreshed dependent profile
raise are answered here with the tools themselves, not with mocks:

- The skills CLI (`npx skills add ... -g -a claude-code --copy`, the form
  the AEGIS configuration uses) installing into a profile whose skills/ is a
  symlink or a junction: whether the link survives, where the files land,
  and which config home the CLI honors (CLAUDE_CONFIG_DIR, or ~/.claude when
  it is unset). The skill source is a local directory, so no repository is
  fetched; the CLI package itself comes from the npm registry.
- `npm install -g` inside a setup child started with --yes --skip-install
  --no-admin, the way a source profile's refresh starts a dependent profile:
  the elevation gate is skipped and the global install succeeds with the
  user's npm prefix. The package is a dependency-free local directory, so no
  registry access is needed for the install.

Skipped when the claude binary (or npx/npm) is absent;
CLAUDE_CODE_TOOLBOX_REQUIRE_REAL_BINARY=1 (set in CI) turns absence into a
failure instead of a silent skip.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

from scripts import setup_environment
from tests.e2e import linked_entries_support as support
from tests.e2e.linked_entries_workspace import Workspace
from tests.e2e.linked_entries_workspace import open_workspace

_REQUIRE_REAL_BINARY = os.environ.get('CLAUDE_CODE_TOOLBOX_REQUIRE_REAL_BINARY') == '1'
_NPX = setup_environment.find_command('npx')
_NPM = setup_environment.find_command('npm')
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SETUP_CHILD = _REPO_ROOT / 'tests' / 'e2e' / 'fixtures' / 'setup_child.py'

_CLI_SKILL_NAME = 'sentinel-cli-skill'
_CLI_SKILL_SENTINEL = 'ZQX-CLISKILL-8d2e4f'
_NPM_PACKAGE_NAME = 'cc-toolbox-e2e-npm-package'
_TOOL_TIMEOUT = 240

pytestmark = [
    pytest.mark.real_binary,
    pytest.mark.timeout(300),
    pytest.mark.skipif(
        (support.CLAUDE_CMD is None or _NPX is None or _NPM is None) and not _REQUIRE_REAL_BINARY,
        reason='claude, npx and npm binaries are all required',
    ),
]


@pytest.fixture
def workspace(tmp_path: Path) -> Iterator[Workspace]:
    """Provide an isolated home, a populated source profile and a running fake API."""
    yield from open_workspace(tmp_path)


def _write_local_skill(root: Path) -> Path:
    """Write a one-file skill the skills CLI can install from a local path."""
    skill_dir = root / _CLI_SKILL_NAME
    skill_dir.mkdir(parents=True)
    (skill_dir / 'SKILL.md').write_text(
        f'---\nname: {_CLI_SKILL_NAME}\ndescription: Skill installed by the skills CLI {_CLI_SKILL_SENTINEL}\n---\n'
        '# Sentinel CLI skill\n',
        encoding='utf-8',
    )
    return skill_dir


def _skills_add(skill_dir: Path, env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run the skills CLI the way the AEGIS configuration does, non-interactively."""
    assert _NPX is not None
    argv = [str(_NPX), '-y', 'skills@latest', 'add', str(skill_dir), '-g', '-a', 'claude-code', '--copy', '-y']
    return subprocess.run(
        argv, cwd=cwd, env=env, capture_output=True, encoding='utf-8', errors='replace', check=False,
        timeout=_TOOL_TIMEOUT,
    )


@pytest.mark.parametrize('kind', support.link_only_kinds())
def test_skills_cli_copies_through_linked_skills_dir(workspace: Workspace, kind: str, tmp_path: Path) -> None:
    """The skills CLI writes the skill into the link target, keeps the link, and the binary loads it."""
    profile = workspace.make_profile('e2e-linked', kind, hooks_enabled=False)
    skill_dir = _write_local_skill(tmp_path / 'local-skills')

    completed = _skills_add(skill_dir, profile.env, profile.project_dir)

    output = completed.stdout + completed.stderr
    assert completed.returncode == 0, output[-4000:]
    assert support.entry_is_link_to(profile.config_dir / 'skills', workspace.source / 'skills'), (
        f'the skills/ link must survive the install: {output[-4000:]}'
    )
    installed = workspace.source / 'skills' / _CLI_SKILL_NAME / 'SKILL.md'
    assert installed.is_file(), output[-4000:]
    assert _CLI_SKILL_SENTINEL in installed.read_text(encoding='utf-8')
    through_link = profile.config_dir / 'skills' / _CLI_SKILL_NAME / 'SKILL.md'
    assert through_link.resolve() == installed.resolve()
    assert not (workspace.home / '.claude' / 'skills').exists(), (
        'with CLAUDE_CONFIG_DIR set the CLI must not write into ~/.claude/skills'
    )

    run = profile.run('Reply with the single word READY.')

    assert run.returncode == 0, run.describe()
    assert run.init is not None, run.describe()
    assert _CLI_SKILL_NAME in run.init['skills'], run.describe()
    assert _CLI_SKILL_SENTINEL in run.body_text, run.describe()


def test_skills_cli_uses_home_claude_without_config_dir(workspace: Workspace, tmp_path: Path) -> None:
    """Without CLAUDE_CONFIG_DIR the skills CLI installs into ~/.claude/skills."""
    skill_dir = _write_local_skill(tmp_path / 'local-skills')
    env = support.isolated_home_env(workspace.home)
    assert 'CLAUDE_CONFIG_DIR' not in env

    completed = _skills_add(skill_dir, env, workspace.project_dir)

    output = completed.stdout + completed.stderr
    assert completed.returncode == 0, output[-4000:]
    installed = workspace.home / '.claude' / 'skills' / _CLI_SKILL_NAME / 'SKILL.md'
    assert installed.is_file(), output[-4000:]
    assert _CLI_SKILL_SENTINEL in installed.read_text(encoding='utf-8')


def _write_local_npm_package(root: Path) -> Path:
    """Write a dependency-free npm package with one bin script."""
    root.mkdir(parents=True)
    (root / 'package.json').write_text(json.dumps({
        'name': _NPM_PACKAGE_NAME,
        'version': '1.0.0',
        'description': 'Dependency-free package the E2E suite installs globally from this directory',
        'license': 'MIT',
        'private': True,
        'bin': {_NPM_PACKAGE_NAME: 'bin.js'},
    }, indent=2), encoding='utf-8')
    (root / 'bin.js').write_text(f"#!/usr/bin/env node\nprocess.stdout.write('{_NPM_PACKAGE_NAME}\\n');\n", encoding='utf-8')
    return root


def _global_package_dir(prefix: Path) -> Path:
    """Return where `npm install -g` puts a package under ``prefix``."""
    if sys.platform == 'win32':
        return prefix / 'node_modules' / _NPM_PACKAGE_NAME
    return prefix / 'lib' / 'node_modules' / _NPM_PACKAGE_NAME


def test_npm_global_install_succeeds_in_no_admin_setup_child(workspace: Workspace, tmp_path: Path) -> None:
    """A setup child started with --yes --skip-install --no-admin installs a global npm package.

    The child is a separate interpreter running setup_environment.main()
    against an isolated home; the only neutralized writers are the Windows
    registry and Fish universal variables (see fixtures/setup_child.py).
    The elevation gate that `npm install -g` would otherwise trigger on
    Windows is skipped by --no-admin and the install goes to the user's npm
    prefix, so no elevated window is requested and no elevation is denied.
    """
    package_dir = _write_local_npm_package(tmp_path / 'npm-package')
    if ' ' in str(package_dir):
        pytest.skip('a dependency command is split on whitespace, so the package path must not contain spaces')
    prefix = tmp_path / 'npm-prefix'
    config_path = tmp_path / 'npm-child.yaml'
    dependency = f'npm install -g {package_dir.as_posix()}'
    config_path.write_text(yaml.safe_dump({
        'name': 'E2E npm global install in a no-admin child',
        'dependencies': {'common': [dependency]},
    }), encoding='utf-8')
    env = support.isolated_home_env(workspace.home)
    env.update({
        'PYTHONPATH': str(_REPO_ROOT),
        'npm_config_prefix': str(prefix),
        'npm_config_cache': str(tmp_path / 'npm-cache'),
        'npm_config_update_notifier': 'false',
        'npm_config_fund': 'false',
        'npm_config_audit': 'false',
    })
    argv = [sys.executable, str(_SETUP_CHILD), str(config_path), '--yes', '--skip-install', '--no-admin']

    completed = subprocess.run(
        argv, cwd=workspace.project_dir, env=env, capture_output=True, encoding='utf-8', errors='replace',
        check=False, timeout=_TOOL_TIMEOUT,
    )

    output = completed.stdout + completed.stderr
    assert completed.returncode == 0, output[-6000:]
    assert f'Running: {dependency}' in output, output[-6000:]
    assert 'Administrator privileges granted' not in output, output[-6000:]
    assert 'elevation was denied' not in output, output[-6000:]
    assert 'failed to install' not in output.lower(), output[-6000:]
    assert (_global_package_dir(prefix) / 'package.json').is_file(), output[-6000:]
