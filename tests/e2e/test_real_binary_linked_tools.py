"""E2E tests of the external tools a linked profile depends on, against the real binaries.

Two questions are answered here with the tools themselves, not with mocks:

- The skills CLI (`npx skills add ... -g -a claude-code --copy`, the form
  an environment configuration uses) installing into a profile whose skills/ is a
  symlink or a junction raises four questions a linked skills/ directory
  must answer: whether the link survives, where the files land, which
  config home the CLI honors (CLAUDE_CONFIG_DIR, or ~/.claude when it is
  unset), and whether installing a skill the link target already holds
  updates that one copy in place instead of adding a second one. The skill
  source is a local directory, so no repository is fetched; the CLI package
  itself comes from the npm registry.
- `npm install -g` inside a separate interpreter running
  setup_environment.main() with --yes --skip-install --no-admin against an
  isolated home: the Windows elevation gate is skipped and the global
  install lands in a prefix the test owns. On Windows the child also runs as
  a simulated non-elevated process, which shows the gate firing without
  --no-admin and being skipped with it. The package is a dependency-free
  local directory, so no registry access is needed for the install.

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
from tests.e2e.fixtures.setup_child import ELEVATION_MARKER
from tests.e2e.fixtures.setup_child import SIMULATE_NON_ADMIN_VARIABLE
from tests.e2e.linked_entries_workspace import Workspace
from tests.e2e.linked_entries_workspace import open_workspace

_REQUIRE_REAL_BINARY = os.environ.get('CLAUDE_CODE_TOOLBOX_REQUIRE_REAL_BINARY') == '1'
_NPX = setup_environment.find_command('npx')
_NPM = setup_environment.find_command('npm')
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SETUP_CHILD = _REPO_ROOT / 'tests' / 'e2e' / 'fixtures' / 'setup_child.py'

_CLI_SKILL_NAME = 'sentinel-cli-skill'
_CLI_SKILL_SENTINEL = 'ZQX-CLISKILL-8d2e4f'
_CLI_SKILL_SENTINEL_UPDATED = 'ZQX-CLISKILL-UPD-1a7c3e'
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


def _write_local_skill(root: Path, sentinel: str = _CLI_SKILL_SENTINEL) -> Path:
    """Write (or rewrite) a one-file skill the skills CLI can install from a local path."""
    skill_dir = root / _CLI_SKILL_NAME
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / 'SKILL.md').write_text(
        f'---\nname: {_CLI_SKILL_NAME}\ndescription: Skill installed by the skills CLI {sentinel}\n---\n'
        '# Sentinel CLI skill\n',
        encoding='utf-8',
    )
    return skill_dir


def _skills_add(skill_dir: Path, env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run the skills CLI the way an environment configuration does, non-interactively."""
    assert _NPX is not None
    argv = [str(_NPX), '-y', 'skills@latest', 'add', str(skill_dir), '-g', '-a', 'claude-code', '--copy', '-y']
    return subprocess.run(
        argv, cwd=cwd, env=env, capture_output=True, encoding='utf-8', errors='replace', check=False,
        timeout=_TOOL_TIMEOUT,
    )


def _skill_directories(skills_dir: Path) -> list[str]:
    """Return the names of the skill directories under ``skills_dir``, sorted."""
    return sorted(entry.name for entry in skills_dir.iterdir() if entry.is_dir())


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


@pytest.mark.parametrize('kind', support.link_only_kinds())
def test_skills_cli_reinstalls_over_existing_skill_through_linked_skills_dir(
    workspace: Workspace, kind: str, tmp_path: Path,
) -> None:
    """Installing a skill the link target already holds, from a linked profile, updates the one copy in place.

    The skill is first installed into the source's real skills/ by the CLI
    itself (CLAUDE_CONFIG_DIR at the source), so the CLI's global lock
    records it the way a source install does. Its SKILL.md is then rewritten
    with a second sentinel and installed twice from a profile whose skills/
    links the source's: each run must succeed, keep the link, leave exactly
    one directory for the skill in the source holding only the new
    sentinel, and never touch ~/.claude/skills; the binary then loads the
    new content through the link.
    """
    skill_dir = _write_local_skill(tmp_path / 'local-skills')
    source_env = support.isolated_home_env(workspace.home)
    source_env['CLAUDE_CONFIG_DIR'] = str(workspace.source)
    first = _skills_add(skill_dir, source_env, workspace.project_dir)
    first_output = first.stdout + first.stderr
    assert first.returncode == 0, first_output[-4000:]
    installed = workspace.source / 'skills' / _CLI_SKILL_NAME / 'SKILL.md'
    assert _CLI_SKILL_SENTINEL in installed.read_text(encoding='utf-8'), first_output[-4000:]
    _write_local_skill(tmp_path / 'local-skills', _CLI_SKILL_SENTINEL_UPDATED)
    profile = workspace.make_profile('e2e-linked', kind, hooks_enabled=False)

    for attempt in (1, 2):
        completed = _skills_add(skill_dir, profile.env, profile.project_dir)

        output = completed.stdout + completed.stderr
        assert completed.returncode == 0, (attempt, output[-4000:])
        assert support.entry_is_link_to(profile.config_dir / 'skills', workspace.source / 'skills'), (
            f'the skills/ link must survive install {attempt}: {output[-4000:]}'
        )
        content = installed.read_text(encoding='utf-8')
        assert _CLI_SKILL_SENTINEL_UPDATED in content, (attempt, output[-4000:])
        assert _CLI_SKILL_SENTINEL not in content, (attempt, output[-4000:])
        assert _skill_directories(workspace.source / 'skills') == sorted([support.SKILL_NAME, _CLI_SKILL_NAME]), (
            attempt, output[-4000:],
        )
        assert not (workspace.home / '.claude' / 'skills').exists(), (attempt, output[-4000:])

    run = profile.run('Reply with the single word READY.')

    assert run.returncode == 0, run.describe()
    assert run.init is not None, run.describe()
    assert _CLI_SKILL_NAME in run.init['skills'], run.describe()
    assert _CLI_SKILL_SENTINEL_UPDATED in run.body_text, run.describe()
    assert _CLI_SKILL_SENTINEL not in run.body_text, run.describe()


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


def _run_npm_setup_child(
    workspace: Workspace, tmp_path: Path, *, no_admin: bool, simulate_non_admin: bool,
) -> tuple[subprocess.CompletedProcess[str], Path, str]:
    """Run the setup child with a configuration whose one dependency is a global npm install.

    The npm prefix and cache are directories under ``tmp_path`` that the
    test owns, so the install never reaches the user's npm prefix.

    Args:
        workspace: The isolated home the child runs against.
        tmp_path: The test's temporary directory.
        no_admin: Whether ``--no-admin`` is passed.
        simulate_non_admin: Whether the child reports no administrator token.

    Returns:
        The completed child, the npm prefix, and the dependency command line.
    """
    package_dir = _write_local_npm_package(tmp_path / 'npm-package')
    if ' ' in str(package_dir):
        pytest.skip('a dependency command is split on whitespace, so the package path must not contain spaces')
    prefix = tmp_path / 'npm-prefix'
    config_path = tmp_path / 'npm-child.yaml'
    dependency = f'npm install -g {package_dir.as_posix()}'
    config_path.write_text(yaml.safe_dump({
        'name': 'E2E npm global install in a setup child',
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
    if simulate_non_admin:
        env[SIMULATE_NON_ADMIN_VARIABLE] = '1'
    argv = [sys.executable, str(_SETUP_CHILD), str(config_path), '--yes', '--skip-install']
    if no_admin:
        argv.append('--no-admin')
    completed = subprocess.run(
        argv, cwd=workspace.project_dir, env=env, capture_output=True, encoding='utf-8', errors='replace',
        check=False, timeout=_TOOL_TIMEOUT,
    )
    return completed, prefix, dependency


def test_npm_global_install_succeeds_in_no_admin_setup_child(workspace: Workspace, tmp_path: Path) -> None:
    """A setup child started with --yes --skip-install --no-admin installs a global npm package.

    The child is a separate interpreter running setup_environment.main()
    against an isolated home; the only neutralized writers are the Windows
    registry and Fish universal variables (see fixtures/setup_child.py).
    --no-admin skips the Windows elevation gate that a global npm dependency
    would otherwise trigger, so no elevated window is requested and no
    elevation is denied, and the install goes to a prefix the test owns
    (npm_config_prefix), never to the user's npm prefix.
    """
    completed, prefix, dependency = _run_npm_setup_child(workspace, tmp_path, no_admin=True, simulate_non_admin=False)

    output = completed.stdout + completed.stderr
    assert completed.returncode == 0, output[-6000:]
    assert f'Running: {dependency}' in output, output[-6000:]
    assert 'Administrator privileges granted' not in output, output[-6000:]
    assert 'elevation was denied' not in output, output[-6000:]
    assert ELEVATION_MARKER not in output, output[-6000:]
    assert 'failed to install' not in output.lower(), output[-6000:]
    assert (_global_package_dir(prefix) / 'package.json').is_file(), output[-6000:]


@pytest.mark.skipif(sys.platform != 'win32', reason='the elevation gate of main() exists on Windows only')
@pytest.mark.parametrize('no_admin', [True, False], ids=['no-admin', 'gate'])
def test_npm_global_install_in_simulated_non_admin_setup_child(
    workspace: Workspace, tmp_path: Path, no_admin: bool,
) -> None:
    """Without an administrator token the gate fires on a global npm dependency unless --no-admin is given.

    CCT_E2E_SIMULATE_NON_ADMIN=1 makes the child report no administrator
    token and turns the elevation request into a printed marker plus exit 1,
    whatever token the test process holds, so the gate is observed on an
    elevated developer session and on CI alike. With --no-admin the gate is
    skipped and the package installs; without it the gate names the
    dependency, the marker is printed, the child exits 1 and nothing is
    installed.
    """
    completed, prefix, dependency = _run_npm_setup_child(
        workspace, tmp_path, no_admin=no_admin, simulate_non_admin=True,
    )

    output = completed.stdout + completed.stderr
    if no_admin:
        assert completed.returncode == 0, output[-6000:]
        assert ELEVATION_MARKER not in output, output[-6000:]
        assert 'Administrator Privileges Required' not in output, output[-6000:]
        assert f'Running: {dependency}' in output, output[-6000:]
        assert (_global_package_dir(prefix) / 'package.json').is_file(), output[-6000:]
    else:
        assert completed.returncode == 1, output[-6000:]
        assert ELEVATION_MARKER in output, output[-6000:]
        assert 'Administrator Privileges Required' in output, output[-6000:]
        assert f'Global npm package: {dependency}' in output, output[-6000:]
        assert f'Running: {dependency}' not in output, output[-6000:]
        assert not _global_package_dir(prefix).exists(), output[-6000:]
