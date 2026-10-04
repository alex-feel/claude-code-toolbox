"""E2E tests proving, with the real Claude Code binary, that an isolated profile's sessions read nothing from the base profile.

Claude Code reads the working directory's ``.claude`` as the project settings
of a session and the ``.claude`` of every directory above it as project
memory. The home folder's ``.claude`` is the base profile, so a session of an
isolated profile started in the home folder would take the base profile's
``settings.json`` (its ``env``, ``model`` and hooks) and ``settings.local.json``
as project settings, a session started anywhere below the home would load
the base profile's ``CLAUDE.md`` and ``rules/`` as ancestor memory, and a
session started inside ``~/.claude`` itself or inside the profile directory
would load its ``CLAUDE.local.md`` as well. The toolbox closes every channel:
the profile's ``config.json`` excludes the base profile's memory files, with
every letter of each pattern spelled as a case class because Claude Code
matches the patterns case-sensitively against paths built from the working
directory as spelled, and ``launch.sh`` limits a session started in the home
folder to the profile's own settings sources.

The profile is installed by ``main()`` in a child interpreter and started
exactly as a user starts it -- through ``launch.sh`` and, on Windows,
``start.cmd``, ``start.ps1`` and the ``~/.local/bin`` wrappers, on Unix the
``~/.local/bin`` symlink -- with no argument added by the tests, from the home
folder, from a project below it, from ``~/.claude`` itself, from the profile
directory and, on Windows, from the project spelled with a lowercase drive
letter and all in lowercase. Every channel carries a sentinel that is
observable only when it loaded: the requested model, a request header the
``env`` block sets, a marker file each hook writes, memory text in the request
body, and the skills, agents, commands and MCP servers the init message lists.
Control runs without the toolbox's exclusions, and with exact-case patterns
from a working directory spelled in another case, show each base sentinel
leaking, so every negative assertion is discriminating. The working project's
own ``CLAUDE.md``, ``CLAUDE.local.md``, ``.claude`` settings, hooks, rules,
skills, agents and commands keep loading, the profile's own ``settings.json``
applies everywhere, and a ``claudeMdExcludes`` the configuration declares
still applies beside the toolbox's.

The home folder's own ``CLAUDE.md``, ``CLAUDE.local.md`` and ``.mcp.json`` lie
outside ``~/.claude``: they load below the home as the home folder's own
project files and stay out of a session started in the home folder itself,
where the launcher's ``--setting-sources user`` leaves no project source. A
second profile installed without profile-scoped MCP servers, whose launcher
therefore runs without ``--strict-mcp-config``, shows that for ``.mcp.json``.

The layout lives where no real config home is an ancestor (see
linked_entries_support.workspace_root()), so nothing real contributes to a
run; the sentinels are unique strings, so no real file could stand in for one
either. Skipped when the binary is absent; CLAUDE_CODE_TOOLBOX_REQUIRE_REAL_BINARY=1
(set in CI) turns absence into a failure instead of a silent skip.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts import setup_environment
from scripts.setup_environment import CLAUDE_MD_EXCLUDES_KEY
from tests.e2e import linked_entries_support as support
from tests.e2e.fake_anthropic_api import FakeAnthropicServer
from tests.e2e.shells import find_powershell

_REQUIRE_REAL_BINARY = os.environ.get('CLAUDE_CODE_TOOLBOX_REQUIRE_REAL_BINARY') == '1'
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SETUP_CHILD = _REPO_ROOT / 'tests' / 'e2e' / 'fixtures' / 'setup_child.py'
_SETUP_TIMEOUT = 240
PROFILE = 'work-1'
# A profile installed without profile-scoped MCP servers: its launcher runs
# without --strict-mcp-config, so a project .mcp.json reaches its sessions
SECOND_PROFILE = 'work-2'
PROMPT = 'Reply with the single word READY.'

BASE_MODEL = 'zqx-base-model-7f3a'
PROJECT_MODEL = 'zqx-project-model-4b8d'
PROFILE_SETTINGS_MODEL = 'zqx-profile-settings-model-2c9e'
# Request headers the base and project env blocks set through ANTHROPIC_CUSTOM_HEADERS
BASE_HEADER = 'x-zqx-base'
PROJECT_HEADER = 'x-zqx-project'
SENTINELS = {
    'base-claude-md': 'ZQX-BASE-CLAUDEMD-1a2b',
    'base-claude-local': 'ZQX-BASE-CLAUDE-LOCAL-3c4d',
    'base-rule': 'ZQX-BASE-RULE-5e6f',
    'home-claude-md': 'ZQX-HOME-CLAUDEMD-6b7c',
    'home-claude-local': 'ZQX-HOME-CLAUDE-LOCAL-8d9e',
    'project-claude-md': 'ZQX-PROJECT-CLAUDEMD-7a8b',
    'project-claude-local': 'ZQX-PROJECT-CLAUDE-LOCAL-9c0d',
    'project-dot-claude-md': 'ZQX-PROJECT-DOT-CLAUDEMD-1e2f',
    'project-rule': 'ZQX-PROJECT-RULE-3a4b',
    'profile-claude-md': 'ZQX-PROFILE-CLAUDEMD-5c6d',
    'profile-rule': 'ZQX-PROFILE-RULE-7e8f',
    'profile-prompt': 'ZQX-PROFILE-PROMPT-9a0b',
}
BASE_SKILL, BASE_AGENT, BASE_COMMAND = 'base-skill', 'base-agent', 'base-cmd'
PROJECT_SKILL, PROJECT_AGENT, PROJECT_COMMAND = 'project-skill', 'project-agent', 'project-cmd'
PROFILE_SKILL, PROFILE_AGENT, PROFILE_COMMAND, PROFILE_MCP = 'own-skill', 'own-agent', 'own-cmd', 'own-mcp'
HOME_MCP = 'home-mcp'
MARKER_NAMES = ('base-hook', 'base-local-hook', 'project-hook', 'profile-hook', 'profile-settings-hook')
BASE_MEMORY_NAMES = ('CLAUDE.md', 'CLAUDE.local.md', 'rules/**')
WINDOWS_SPELLINGS = ['lowercase-drive', 'lowercase']

pytestmark = [
    pytest.mark.real_binary,
    pytest.mark.timeout(300),
    pytest.mark.skipif(
        support.CLAUDE_CMD is None and not _REQUIRE_REAL_BINARY,
        reason='claude binary not available',
    ),
]


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _hook(marker: Path) -> dict[str, Any]:
    """A UserPromptSubmit hook that creates ``marker`` when it runs."""
    return {'UserPromptSubmit': [{'hooks': [{'type': 'command', 'command': f'echo ran > "{marker.as_posix()}"'}]}]}


def _skill(root: Path, name: str) -> None:
    _write(root / 'skills' / name / 'SKILL.md', f'---\nname: {name}\ndescription: Skill {name}\n---\nbody\n')


def _agent(root: Path, name: str) -> None:
    _write(root / 'agents' / f'{name}.md', f'---\nname: {name}\ndescription: Agent {name}\n---\nbody\n')


def _command(root: Path, name: str) -> None:
    _write(root / 'commands' / f'{name}.md', f'---\ndescription: Command {name}\n---\nbody\n')


def _failing_mcp_server() -> dict[str, Any]:
    """A stdio MCP server that exits at once; the init message still lists it by name."""
    return {'command': sys.executable, 'args': ['-c', 'import sys; sys.exit(1)']}


def _case_classes(text: str) -> str:
    """Spell every ASCII letter of ``text`` as a glob class matching either case."""
    return re.sub(r'[A-Za-z]', lambda match: f'[{match.group(0).lower()}{match.group(0).upper()}]', text)


def _base_exclusions(home: Path, *, with_rules: bool = True) -> list[str]:
    """The exclusions an isolated profile of ``home`` carries for the base config home."""
    base = (home / '.claude').as_posix()
    names = BASE_MEMORY_NAMES if with_rules else BASE_MEMORY_NAMES[:2]
    return [_case_classes(f'{base}/{name}') for name in names]


def _exact_case_exclusions(home: Path) -> list[str]:
    """The same exclusions spelled with the home's own letter case, matching that one spelling only."""
    base = (home / '.claude').as_posix()
    return [f'{base}/{name}' for name in BASE_MEMORY_NAMES]


def _spellings(directory: Path) -> list[str]:
    """Every spelling a session may start ``directory`` under: as given and, on Windows, in other letter cases."""
    spelled = str(directory)
    if sys.platform != 'win32':
        return [spelled]
    return [spelled, spelled[0].lower() + spelled[1:], spelled.lower()]


def _spell(directory: Path, spelling: str) -> str:
    """``directory`` spelled with a lowercase drive letter or entirely in lowercase."""
    spelled = str(directory)
    if spelling == 'lowercase-drive':
        return spelled[0].lower() + spelled[1:]
    return spelled.lower()


def _write_base_profile(home: Path, markers: dict[str, Path]) -> None:
    """Populate the home folder's .claude the way a base install leaves it, one sentinel per channel."""
    base = home / '.claude'
    _write(base / 'settings.json', json.dumps({
        'model': BASE_MODEL,
        'env': {'ANTHROPIC_CUSTOM_HEADERS': f'{BASE_HEADER}: 1'},
        'hooks': _hook(markers['base-hook']),
    }))
    _write(base / 'settings.local.json', json.dumps({'hooks': _hook(markers['base-local-hook'])}))
    _write(base / 'CLAUDE.md', f'Sentinel {SENTINELS["base-claude-md"]}\n')
    _write(base / 'CLAUDE.local.md', f'Sentinel {SENTINELS["base-claude-local"]}\n')
    _write(base / 'rules' / 'base.md', f'Sentinel {SENTINELS["base-rule"]}\n')
    _skill(base, BASE_SKILL)
    _agent(base, BASE_AGENT)
    _command(base, BASE_COMMAND)


def _write_home_folder_files(home: Path) -> None:
    """Give the home folder its own project files outside .claude: memory, local memory and a .mcp.json."""
    _write(home / 'CLAUDE.md', f'Sentinel {SENTINELS["home-claude-md"]}\n')
    _write(home / 'CLAUDE.local.md', f'Sentinel {SENTINELS["home-claude-local"]}\n')
    _write(home / '.mcp.json', json.dumps({'mcpServers': {HOME_MCP: _failing_mcp_server()}}))


def _write_project(project: Path, markers: dict[str, Path]) -> None:
    """Populate a project below the home with its own memory, settings, hook, rule, skill, agent and command."""
    _write(project / 'CLAUDE.md', f'Sentinel {SENTINELS["project-claude-md"]}\n')
    _write(project / 'CLAUDE.local.md', f'Sentinel {SENTINELS["project-claude-local"]}\n')
    dot = project / '.claude'
    _write(dot / 'CLAUDE.md', f'Sentinel {SENTINELS["project-dot-claude-md"]}\n')
    _write(dot / 'rules' / 'project.md', f'Sentinel {SENTINELS["project-rule"]}\n')
    _write(dot / 'settings.json', json.dumps({
        'model': PROJECT_MODEL,
        'env': {'ANTHROPIC_CUSTOM_HEADERS': f'{PROJECT_HEADER}: 1'},
        'hooks': _hook(markers['project-hook']),
    }))
    _skill(dot, PROJECT_SKILL)
    _agent(dot, PROJECT_AGENT)
    _command(dot, PROJECT_COMMAND)


def _write_profile_settings(profile_dir: Path, marker: Path) -> None:
    """Write the profile's own settings.json, as /model and /config leave it: a model and a hook."""
    _write(profile_dir / 'settings.json', json.dumps({'model': PROFILE_SETTINGS_MODEL, 'hooks': _hook(marker)}))


def _write_configuration(
    configs: Path,
    project: Path,
    marker: Path,
    *,
    command_name: str | None = PROFILE,
    profile_mcp: bool = True,
    filename: str = 'team.yaml',
) -> Path:
    """Write a configuration and the resources it installs beside it.

    The configuration declares one exclusion of its own (the project's
    CLAUDE.local.md) so the union with the toolbox's exclusions is observed,
    a UserPromptSubmit hook whose run shows config.json applies, a system
    prompt, a CLAUDE.md destination naming the base config home, which
    an isolated install re-roots into the profile, and, when it names a
    command and ``profile_mcp`` is set, a profile-scoped MCP server (which
    a base install has no launcher for).

    Returns:
        The configuration path.
    """
    _write(configs / 'rules' / 'own.md', f'Sentinel {SENTINELS["profile-rule"]}\n')
    _write(configs / 'agents' / f'{PROFILE_AGENT}.md', f'---\nname: {PROFILE_AGENT}\ndescription: own\n---\nbody\n')
    _write(configs / 'commands' / f'{PROFILE_COMMAND}.md', '---\ndescription: own\n---\nbody\n')
    _write(configs / 'skills' / 'SKILL.md', f'---\nname: {PROFILE_SKILL}\ndescription: own\n---\nbody\n')
    _write(configs / 'prompts' / 'own.md', f'Sentinel {SENTINELS["profile-prompt"]}\n')
    _write(configs / 'memory' / 'CLAUDE.md', f'Sentinel {SENTINELS["profile-claude-md"]}\n')
    _write(configs / 'hooks' / 'own_hook.py', 'import pathlib\nimport sys\n'
           'pathlib.Path(sys.argv[1]).write_text("ran", encoding="utf-8")\n')
    config: dict[str, Any] = {
        'name': 'Team',
        'rules': ['rules/own.md'],
        'agents': [f'agents/{PROFILE_AGENT}.md'],
        'slash-commands': [f'commands/{PROFILE_COMMAND}.md'],
        'skills': [{'name': PROFILE_SKILL, 'base': 'skills/', 'files': ['SKILL.md']}],
        'files-to-download': [{'source': 'memory/CLAUDE.md', 'dest': '~/.claude/CLAUDE.md'}],
        'hooks': {
            'files': ['hooks/own_hook.py'],
            'events': [{
                'event': 'UserPromptSubmit', 'type': 'command', 'command': 'own_hook.py',
                'args': [marker.as_posix()],
            }],
        },
        'command-defaults': {'system-prompt': 'prompts/own.md'},
        'user-settings': {CLAUDE_MD_EXCLUDES_KEY: [f'{project.as_posix()}/CLAUDE.local.md']},
    }
    if command_name:
        config['command-names'] = [command_name]
        if profile_mcp:
            config['mcp-servers'] = [{'name': PROFILE_MCP, 'scope': 'profile', **_failing_mcp_server()}]
    path = configs / filename
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding='utf-8')
    return path


def _run_setup(config: Path, home: Path, *args: str) -> None:
    """Run main() in a child interpreter confined to ``home``."""
    env = support.isolated_home_env(home)
    env['PYTHONPATH'] = str(_REPO_ROOT)
    completed = subprocess.run(
        [sys.executable, str(_SETUP_CHILD), str(config), '--yes', '--skip-install', '--no-admin', *args],
        cwd=home, env=env, capture_output=True, encoding='utf-8', errors='replace', check=False,
        timeout=_SETUP_TIMEOUT,
    )
    assert completed.returncode == 0, (completed.stdout + completed.stderr)[-6000:]


def _trust(profile_dir: Path, directories: list[Path]) -> None:
    """Mark onboarding complete, the fake key approved and every start directory trusted in the profile's .claude.json.

    Each directory is trusted in every spelling a session may start it
    under, and the home folder's .mcp.json server is approved for it, the
    way ``/mcp`` records the approval.
    """
    path = profile_dir / '.claude.json'
    content: dict[str, Any] = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
    content['hasCompletedOnboarding'] = True
    content['customApiKeyResponses'] = {'approved': [support.FAKE_API_KEY[-20:]], 'rejected': []}
    projects = content.setdefault('projects', {})
    for directory in directories:
        for spelled in _spellings(directory):
            entry = projects.setdefault(spelled, {})
            entry['hasTrustDialogAccepted'] = True
            entry['enabledMcpjsonServers'] = [HOME_MCP]
    path.write_text(json.dumps(content), encoding='utf-8')


@dataclass
class Layout:
    """An isolated home with a base profile, a project below it, and two installed isolated profiles."""

    root: Path
    home: Path
    project: Path
    profile_dir: Path
    second_profile_dir: Path
    markers: dict[str, Path]
    server: FakeAnthropicServer

    def session_env(self) -> dict[str, str]:
        """The environment of a session started from a shell: the real binary first on PATH, no CLAUDE_CONFIG_DIR."""
        env = support.claude_child_env(
            config_dir=self.profile_dir, home=self.home, api_url=self.server.url, claude_cmd=support.CLAUDE_CMD,
        )
        env.pop('CLAUDE_CONFIG_DIR')
        env['PATH'] = os.pathsep.join([str(self.home / '.local' / 'bin'), env['PATH']])
        return env

    def clear_markers(self) -> None:
        for marker in self.markers.values():
            marker.unlink(missing_ok=True)

    def hooks_ran(self) -> set[str]:
        return {name for name, marker in self.markers.items() if marker.exists()}

    def run(self, argv: list[str] | str, cwd: Path | str, *, env: dict[str, str] | None = None) -> support.ClaudeRun:
        """Run one turn through ``argv`` from ``cwd`` and attach what the fake API recorded.

        Args:
            argv: The command line; a string is handed to the OS verbatim.
            cwd: The working directory the session starts in, spelled as given.
            env: The child environment; session_env() when omitted.

        Returns:
            The parsed run, with the request bodies this run produced.
        """
        self.clear_markers()
        first = len(self.server.bodies)
        completed = subprocess.run(
            argv, cwd=cwd, env=self.session_env() if env is None else env, capture_output=True, encoding='utf-8',
            errors='replace', check=False, timeout=120,
        )
        init, hook_responses, result = support.parse_stream_json(completed.stdout)
        return support.ClaudeRun(
            argv=argv if isinstance(argv, list) else [argv], returncode=completed.returncode,
            stdout=completed.stdout, stderr=completed.stderr, bodies=list(self.server.bodies[first:]),
            init=init, hook_responses=hook_responses, result=result,
        )

    def headers(self) -> dict[str, str]:
        """The headers of the last recorded request."""
        return self.server.headers[-1]

    def start_directory(self, location: str) -> Path:
        """The directory a start location names: the home, the project, ``~/.claude`` or the profile directory."""
        return {
            'home': self.home, 'project': self.project, '.claude': self.home / '.claude', 'profile': self.profile_dir,
        }[location]


def _build_layout(tmp_path: Path) -> Iterator[Layout]:
    root, cleanup = support.workspace_root(tmp_path)
    home = root / 'home'
    project = home / 'work' / 'project'
    project.mkdir(parents=True)
    markers = {name: root / f'{name}.marker' for name in MARKER_NAMES}
    _write_base_profile(home, markers)
    _write_home_folder_files(home)
    _write_project(project, markers)
    configs = root / 'configs'
    _run_setup(_write_configuration(configs, project, markers['profile-hook']), home)
    _run_setup(_write_configuration(
        configs, project, markers['profile-hook'], command_name=SECOND_PROFILE, profile_mcp=False,
        filename='team-no-mcp.yaml',
    ), home)
    profile_dir = home / '.claude' / PROFILE
    second_profile_dir = home / '.claude' / SECOND_PROFILE
    assert (profile_dir / 'launch.sh').is_file()
    assert (second_profile_dir / 'launch.sh').is_file()
    assert not (second_profile_dir / 'mcp.json').exists()
    starts = [home, project, home / '.claude', profile_dir, second_profile_dir]
    for directory in (profile_dir, second_profile_dir):
        _write_profile_settings(directory, markers['profile-settings-hook'])
        _trust(directory, starts)
    server = FakeAnthropicServer().start()
    try:
        yield Layout(
            root=root, home=home, project=project, profile_dir=profile_dir, second_profile_dir=second_profile_dir,
            markers=markers, server=server,
        )
    finally:
        server.stop()
        cleanup()


@pytest.fixture(scope='module')
def layout(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Layout]:
    """Two installed isolated profiles beside a base profile and a project, shared by the module's tests."""
    yield from _build_layout(tmp_path_factory.mktemp('base-home-isolation'))


def _bash() -> str:
    bash = setup_environment.find_bash_windows() if sys.platform == 'win32' else shutil.which('bash')
    if bash is None:
        pytest.skip('bash is required to run the toolbox launcher')
    return bash


def _launch_sh(profile_dir: Path, *extra: str) -> list[str]:
    """launch.sh of ``profile_dir`` under bash, handing claude one non-interactive turn plus ``extra`` arguments."""
    return [_bash(), (profile_dir / 'launch.sh').as_posix(), *support.print_args(PROMPT, *extra)]


def _entry_points(layout: Layout) -> list[tuple[str, list[str] | str]]:
    """Every way a user starts the profile, each handing it one non-interactive turn."""
    args = support.print_args(PROMPT)
    local_bin = layout.home / '.local' / 'bin'
    bash = _bash()
    points: list[tuple[str, list[str] | str]] = [('launch.sh', _launch_sh(layout.profile_dir))]
    if sys.platform != 'win32':
        points.append((PROFILE, [str(local_bin / PROFILE), *args]))
        return points
    quoted = ' '.join(f'"{arg}"' for arg in args)
    points.extend([
        ('start.cmd', f'cmd.exe /d /s /c ""{layout.profile_dir / "start.cmd"}" {quoted}"'),
        (f'{PROFILE}.cmd', f'cmd.exe /d /s /c "{PROFILE} {quoted}"'),
        (PROFILE, [bash, str(local_bin / PROFILE), *args]),
    ])
    powershell = find_powershell()
    if powershell is not None:
        scripts = (('start.ps1', layout.profile_dir / 'start.ps1'), (f'{PROFILE}.ps1', local_bin / f'{PROFILE}.ps1'))
        points.extend(
            (name, [powershell, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(script), *args])
            for name, script in scripts
        )
    return points


def _entry_point_ids() -> list[str]:
    if sys.platform != 'win32':
        return ['launch.sh', PROFILE]
    return ['launch.sh', 'start.cmd', f'{PROFILE}.cmd', PROFILE, 'start.ps1', f'{PROFILE}.ps1']


def _assert_turn(run: support.ClaudeRun) -> dict[str, Any]:
    assert run.returncode == 0, run.describe()
    assert len(run.bodies) == 1, run.describe()
    assert run.init is not None, run.describe()
    return run.init


def _mcp_names(init: dict[str, Any]) -> list[str]:
    return [server.get('name') for server in init['mcp_servers']]


def _assert_nothing_from_the_base(layout: Layout, run: support.ClaudeRun, init: dict[str, Any]) -> None:
    """The base profile's settings, hooks, memory, rules, skills, agents and commands are all absent."""
    body = run.body_text
    assert run.bodies[0].get('model') != BASE_MODEL, run.describe()
    assert BASE_HEADER not in layout.headers(), layout.headers()
    assert not layout.hooks_ran() & {'base-hook', 'base-local-hook'}, layout.hooks_ran()
    for key in ('base-claude-md', 'base-claude-local', 'base-rule'):
        assert SENTINELS[key] not in body, f'{key} leaked: {run.describe()}'
    assert BASE_SKILL not in init['skills'], init['skills']
    assert BASE_AGENT not in init['agents'], init['agents']
    assert BASE_COMMAND not in init['slash_commands'], init['slash_commands']


def _assert_profile_applies(layout: Layout, run: support.ClaudeRun, init: dict[str, Any]) -> None:
    """The profile's config.json, settings.json, memory, rule, prompt, skill, agent, command and MCP server all apply."""
    assert {'profile-hook', 'profile-settings-hook'} <= layout.hooks_ran(), layout.hooks_ran()
    assert SENTINELS['profile-claude-md'] in run.body_text, run.describe()
    assert SENTINELS['profile-rule'] in run.body_text, run.describe()
    assert SENTINELS['profile-prompt'] in run.system_text, run.describe()
    assert PROFILE_SKILL in init['skills'], init['skills']
    assert PROFILE_AGENT in init['agents'], init['agents']
    assert PROFILE_COMMAND in init['slash_commands'], init['slash_commands']
    assert PROFILE_MCP in _mcp_names(init), init['mcp_servers']


def _assert_home_folder_files_absent(run: support.ClaudeRun, init: dict[str, Any]) -> None:
    """The home folder's own CLAUDE.md, CLAUDE.local.md and .mcp.json, outside .claude, did not load."""
    for key in ('home-claude-md', 'home-claude-local'):
        assert SENTINELS[key] not in run.body_text, f'{key} loaded: {run.describe()}'
    assert HOME_MCP not in _mcp_names(init), init['mcp_servers']


@pytest.mark.parametrize('entry_point', _entry_point_ids())
def test_session_started_in_the_home_folder_reads_nothing_from_the_base_profile(layout: Layout, entry_point: str) -> None:
    """In the home folder the base profile is the project .claude; the launcher keeps every channel of it shut.

    The profile's own config.json and settings.json still apply there: both
    hooks run, the settings.json model is requested (no project settings
    compete), its MCP server is configured and its memory, rule, prompt,
    skill, agent and command load. The home folder's own CLAUDE.md,
    CLAUDE.local.md and .mcp.json stay out with the rest of the project
    sources.
    """
    argv = dict(_entry_points(layout))[entry_point]

    run = layout.run(argv, layout.home)

    init = _assert_turn(run)
    _assert_nothing_from_the_base(layout, run, init)
    _assert_profile_applies(layout, run, init)
    _assert_home_folder_files_absent(run, init)
    assert run.bodies[0].get('model') == PROFILE_SETTINGS_MODEL, run.describe()
    assert PROJECT_HEADER not in layout.headers(), layout.headers()
    assert 'project-hook' not in layout.hooks_ran(), layout.hooks_ran()


@pytest.mark.parametrize('entry_point', _entry_point_ids())
def test_session_started_in_a_project_below_the_home_keeps_the_project_and_drops_the_base(
    layout: Layout, entry_point: str,
) -> None:
    """Below the home the project's own files load as before while the base profile's memory stays out.

    The project's settings.json sets the model, the env header and a hook;
    its CLAUDE.md, .claude/CLAUDE.md and rule load; its skill, agent and
    command are listed; the home folder's own CLAUDE.md and CLAUDE.local.md
    load as ancestor files. The CLAUDE.local.md the configuration itself
    excludes stays out, so the declared exclusion survives beside the
    toolbox's.
    """
    argv = dict(_entry_points(layout))[entry_point]

    run = layout.run(argv, layout.project)

    init = _assert_turn(run)
    _assert_nothing_from_the_base(layout, run, init)
    _assert_profile_applies(layout, run, init)
    assert run.bodies[0].get('model') == PROJECT_MODEL, run.describe()
    assert PROJECT_HEADER in layout.headers(), layout.headers()
    assert 'project-hook' in layout.hooks_ran(), layout.hooks_ran()
    for key in ('project-claude-md', 'project-dot-claude-md', 'project-rule', 'home-claude-md', 'home-claude-local'):
        assert SENTINELS[key] in run.body_text, f'{key} missing: {run.describe()}'
    assert SENTINELS['project-claude-local'] not in run.body_text, run.describe()
    assert PROJECT_SKILL in init['skills'], init['skills']
    assert PROJECT_AGENT in init['agents'], init['agents']
    assert PROJECT_COMMAND in init['slash_commands'], init['slash_commands']


@pytest.mark.parametrize('entry_point', _entry_point_ids())
@pytest.mark.parametrize('location', ['.claude', 'profile'])
def test_session_started_inside_the_base_config_home_reads_nothing_from_the_base_profile(
    layout: Layout, location: str, entry_point: str,
) -> None:
    """Started in ~/.claude itself or in the profile directory, the session takes neither the base memory nor its local memory.

    There the base profile's CLAUDE.local.md would load as the project's or
    the parent's local memory, which no other start location reaches; the
    exclusions keep it out together with CLAUDE.md and the rules. Nothing
    there is a project .claude, so the profile's own settings.json model is
    requested and the profile applies in full.
    """
    argv = dict(_entry_points(layout))[entry_point]

    run = layout.run(argv, layout.start_directory(location))

    init = _assert_turn(run)
    _assert_nothing_from_the_base(layout, run, init)
    _assert_profile_applies(layout, run, init)
    assert run.bodies[0].get('model') == PROFILE_SETTINGS_MODEL, run.describe()


@pytest.mark.skipif(sys.platform != 'win32', reason='letter case of a working directory is a Windows path form')
@pytest.mark.parametrize('entry_point', _entry_point_ids())
@pytest.mark.parametrize('spelling', WINDOWS_SPELLINGS)
def test_session_below_the_home_spelled_in_another_letter_case_still_drops_the_base(
    layout: Layout, spelling: str, entry_point: str,
) -> None:
    """A working directory spelled with a lowercase drive letter, or all in lowercase, still excludes the base memory.

    cmd.exe leaves ``c:`` after ``cd /d c:\\...`` and a user may type the
    whole path in lowercase; Claude Code builds the ancestor paths it matches
    the exclusions against from that spelling, so the case classes in the
    patterns are what keeps the base CLAUDE.md and rules out, while the
    project's own CLAUDE.md and rule load as before.
    """
    argv = dict(_entry_points(layout))[entry_point]

    run = layout.run(argv, _spell(layout.project, spelling))

    init = _assert_turn(run)
    _assert_nothing_from_the_base(layout, run, init)
    _assert_profile_applies(layout, run, init)
    for key in ('project-claude-md', 'project-rule'):
        assert SENTINELS[key] in run.body_text, f'{key} missing: {run.describe()}'


def test_a_caller_s_own_setting_sources_come_after_the_launcher_s_and_win(layout: Layout) -> None:
    """A --setting-sources the user passes to the launcher follows the launcher's, so Claude Code takes the user's.

    With ``user,project`` named by the caller in the home folder, the base
    profile's settings.json applies again as project settings: its model is
    requested and its hook runs, while settings.local.json, the ``local``
    source the caller did not name, stays out.
    """
    run = layout.run(_launch_sh(layout.profile_dir, '--setting-sources', 'user,project'), layout.home)

    _assert_turn(run)
    assert run.bodies[0].get('model') == BASE_MODEL, run.describe()
    assert {'base-hook', 'profile-hook', 'profile-settings-hook'} <= layout.hooks_ran(), layout.hooks_ran()
    assert 'base-local-hook' not in layout.hooks_ran(), layout.hooks_ran()


def test_home_folder_mcp_json_stays_out_at_home_and_loads_below_without_profile_mcp_servers(layout: Layout) -> None:
    """A profile without profile-scoped MCP servers runs without --strict-mcp-config, so a project .mcp.json reaches it.

    The home folder's .mcp.json is the home folder's own project file: it
    loads below the home as an ancestor file and stays out of a session
    started in the home folder itself, where the launcher leaves no project
    source. The base profile stays out at both places, and the profile's
    own settings.json applies.
    """
    argv = _launch_sh(layout.second_profile_dir)

    at_home = layout.run(argv, layout.home)
    init = _assert_turn(at_home)
    assert HOME_MCP not in _mcp_names(init), init['mcp_servers']
    assert at_home.bodies[0].get('model') == PROFILE_SETTINGS_MODEL, at_home.describe()
    assert not layout.hooks_ran() & {'base-hook', 'base-local-hook'}, layout.hooks_ran()
    assert 'profile-settings-hook' in layout.hooks_ran(), layout.hooks_ran()
    assert SENTINELS['base-claude-md'] not in at_home.body_text, at_home.describe()

    below = layout.run(argv, layout.project)
    init = _assert_turn(below)
    assert HOME_MCP in _mcp_names(init), init['mcp_servers']
    assert SENTINELS['base-claude-md'] not in below.body_text, below.describe()
    assert SENTINELS['base-rule'] not in below.body_text, below.describe()


def test_config_json_carries_the_declared_and_the_base_exclusions(layout: Layout) -> None:
    """config.json holds the configuration's own exclusion first and the base profile's memory files after it."""
    settings = json.loads((layout.profile_dir / 'config.json').read_text(encoding='utf-8'))

    assert settings[CLAUDE_MD_EXCLUDES_KEY] == [
        f'{layout.project.as_posix()}/CLAUDE.local.md', *_base_exclusions(layout.home),
    ]


def _control_argv(control: Path) -> list[str]:
    """claude itself, handing it one turn with ``control`` as the --settings file."""
    assert support.CLAUDE_CMD is not None
    return [str(support.CLAUDE_CMD), *support.print_args(PROMPT), '--settings', str(control)]


def test_control_without_the_toolbox_exclusions_shows_every_base_channel_leaking(layout: Layout) -> None:
    """The same binary, settings and layout without the exclusions and the launcher load the base profile.

    Run with claude itself under the profile's CLAUDE_CONFIG_DIR, as the
    launcher exports it, with a copy of config.json stripped of
    claudeMdExcludes: in the home folder the base profile's settings.json
    sets the model and the header, both base hooks run, its CLAUDE.md and
    rule load, and the home folder's own CLAUDE.md, CLAUDE.local.md and
    .mcp.json load as the project's; below the home its CLAUDE.md and rule
    still load and the configuration's own exclusion no longer applies;
    inside ~/.claude its CLAUDE.local.md loads as well. This is what every
    negative assertion of the other tests would otherwise miss.
    """
    settings = json.loads((layout.profile_dir / 'config.json').read_text(encoding='utf-8'))
    del settings[CLAUDE_MD_EXCLUDES_KEY]
    control = layout.root / 'control-config.json'
    control.write_text(json.dumps(settings), encoding='utf-8')
    argv = _control_argv(control)
    env = {**layout.session_env(), 'CLAUDE_CONFIG_DIR': str(layout.profile_dir)}

    at_home = layout.run(argv, layout.home, env=env)
    init = _assert_turn(at_home)
    assert at_home.bodies[0].get('model') == BASE_MODEL, at_home.describe()
    assert BASE_HEADER in layout.headers(), layout.headers()
    assert {'base-hook', 'base-local-hook', 'profile-hook'} <= layout.hooks_ran(), layout.hooks_ran()
    for key in ('base-claude-md', 'base-rule', 'home-claude-md', 'home-claude-local'):
        assert SENTINELS[key] in at_home.body_text, f'{key} missing: {at_home.describe()}'
    assert HOME_MCP in _mcp_names(init), init['mcp_servers']
    assert BASE_SKILL not in init['skills'], init['skills']

    below = layout.run(argv, layout.project, env=env)
    _assert_turn(below)
    assert SENTINELS['base-claude-md'] in below.body_text, below.describe()
    assert SENTINELS['base-rule'] in below.body_text, below.describe()
    assert SENTINELS['project-claude-local'] in below.body_text, below.describe()
    assert 'base-hook' not in layout.hooks_ran(), layout.hooks_ran()

    inside = layout.run(argv, layout.home / '.claude', env=env)
    _assert_turn(inside)
    for key in ('base-claude-local', 'base-claude-md', 'base-rule'):
        assert SENTINELS[key] in inside.body_text, f'{key} missing: {inside.describe()}'


@pytest.mark.skipif(sys.platform != 'win32', reason='letter case of a working directory is a Windows path form')
def test_control_with_exact_case_patterns_shows_the_base_leaking_below_a_home_spelled_in_another_case(
    layout: Layout,
) -> None:
    """Exclusions spelled with the home's own letter case match that spelling only.

    The same config.json with the toolbox's three patterns replaced by their
    exact-case spelling keeps the base memory out of a session started in
    the project as spelled and lets it in from the project spelled in
    lowercase: Claude Code matches case-sensitively against the working
    directory as spelled, which is what the case classes absorb.
    """
    settings = json.loads((layout.profile_dir / 'config.json').read_text(encoding='utf-8'))
    declared = [p for p in settings[CLAUDE_MD_EXCLUDES_KEY] if p not in _base_exclusions(layout.home)]
    settings[CLAUDE_MD_EXCLUDES_KEY] = [*declared, *_exact_case_exclusions(layout.home)]
    control = layout.root / 'exact-case-config.json'
    control.write_text(json.dumps(settings), encoding='utf-8')
    argv = _control_argv(control)
    env = {**layout.session_env(), 'CLAUDE_CONFIG_DIR': str(layout.profile_dir)}

    as_spelled = layout.run(argv, layout.project, env=env)
    _assert_turn(as_spelled)
    assert SENTINELS['base-claude-md'] not in as_spelled.body_text, as_spelled.describe()
    assert SENTINELS['base-rule'] not in as_spelled.body_text, as_spelled.describe()

    lowercase = layout.run(argv, _spell(layout.project, 'lowercase'), env=env)
    _assert_turn(lowercase)
    assert SENTINELS['base-claude-md'] in lowercase.body_text, lowercase.describe()
    assert SENTINELS['base-rule'] in lowercase.body_text, lowercase.describe()
    assert SENTINELS['project-claude-md'] in lowercase.body_text, lowercase.describe()


def test_rules_linked_from_the_base_profile_still_load(tmp_path: Path) -> None:
    """A profile whose rules/ links to ~/.claude/rules keeps those rules while the base CLAUDE.md stays out.

    The base profile is installed from the same configuration, so the base
    rules are the profile's rules; the exclusions then name the base memory
    files only, and Claude Code, which matches an exclusion against the
    target of a link as well, keeps loading the rule.
    """
    root, cleanup = support.workspace_root(tmp_path)
    try:
        home = root / 'home'
        project = home / 'work' / 'project'
        project.mkdir(parents=True)
        markers = {name: root / f'{name}.marker' for name in MARKER_NAMES}
        config = _write_configuration(root / 'configs', project, markers['profile-hook'], command_name=None)
        _run_setup(config, home)
        _write(home / '.claude' / 'CLAUDE.md', f'Sentinel {SENTINELS["base-claude-md"]}\n')
        _run_setup(config, home, '--command-names', PROFILE, '--link-dirs', 'rules', '--link-from', 'base')
        profile_dir = home / '.claude' / PROFILE
        settings = json.loads((profile_dir / 'config.json').read_text(encoding='utf-8'))
        assert settings[CLAUDE_MD_EXCLUDES_KEY] == [
            f'{project.as_posix()}/CLAUDE.local.md', *_base_exclusions(home, with_rules=False),
        ]
        _trust(profile_dir, [home, project])
        server = FakeAnthropicServer().start()
        try:
            layout = Layout(
                root=root, home=home, project=project, profile_dir=profile_dir, second_profile_dir=profile_dir,
                markers=markers, server=server,
            )

            run = layout.run(_launch_sh(profile_dir), project)

            _assert_turn(run)
            assert SENTINELS['profile-rule'] in run.body_text, run.describe()
            assert SENTINELS['base-claude-md'] not in run.body_text, run.describe()
        finally:
            server.stop()
    finally:
        cleanup()
