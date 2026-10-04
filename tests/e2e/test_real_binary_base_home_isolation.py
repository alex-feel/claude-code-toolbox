"""E2E tests proving, with the real Claude Code binary, that an isolated profile's sessions read nothing from the base profile.

Claude Code reads the working directory's ``.claude`` as the project settings
of a session and the ``.claude`` of every directory above it as project
memory. The home folder's ``.claude`` is the base profile, so a session of an
isolated profile started in the home folder would take the base profile's
``settings.json`` (its ``env``, ``model`` and hooks) and ``settings.local.json``
as project settings, and a session started anywhere below the home would load
the base profile's ``CLAUDE.md`` and ``rules/`` as ancestor memory. The
toolbox closes both channels: the profile's ``config.json`` excludes the base
profile's memory files, and ``launch.sh`` limits a session started in the home
folder to the profile's own settings sources.

The profile is installed by ``main()`` in a child interpreter and started
exactly as a user starts it -- through ``launch.sh`` and, on Windows,
``start.cmd``, ``start.ps1`` and the ``~/.local/bin`` wrappers, on Unix the
``~/.local/bin`` symlink -- with no argument added by the tests, from the home
folder and from a project below it. Every channel carries a sentinel that is
observable only when it loaded: the requested model, a request header the
``env`` block sets, a marker file each hook writes, memory text in the request
body, and the skills, agents, commands and MCP servers the init message lists.
A control run without the toolbox's exclusions shows each base sentinel
leaking, so every negative assertion is discriminating. The working project's
own ``CLAUDE.md``, ``CLAUDE.local.md``, ``.claude`` settings, hooks, rules,
skills, agents and commands keep loading, and a ``claudeMdExcludes`` the
configuration declares still applies beside the toolbox's.

The layout lives where no real config home is an ancestor (see
linked_entries_support.workspace_root()), so nothing real contributes to a
run; the sentinels are unique strings, so no real file could stand in for one
either. Skipped when the binary is absent; CLAUDE_CODE_TOOLBOX_REQUIRE_REAL_BINARY=1
(set in CI) turns absence into a failure instead of a silent skip.
"""

from __future__ import annotations

import json
import os
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
PROMPT = 'Reply with the single word READY.'

BASE_MODEL = 'zqx-base-model-7f3a'
PROJECT_MODEL = 'zqx-project-model-4b8d'
# Request headers the base and project env blocks set through ANTHROPIC_CUSTOM_HEADERS
BASE_HEADER = 'x-zqx-base'
PROJECT_HEADER = 'x-zqx-project'
SENTINELS = {
    'base-claude-md': 'ZQX-BASE-CLAUDEMD-1a2b',
    'base-claude-local': 'ZQX-BASE-CLAUDE-LOCAL-3c4d',
    'base-rule': 'ZQX-BASE-RULE-5e6f',
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


def _write_configuration(configs: Path, project: Path, marker: Path, *, command_names: bool = True) -> Path:
    """Write team.yaml and the resources it installs beside it.

    The configuration declares one exclusion of its own (the project's
    CLAUDE.local.md) so the union with the toolbox's exclusions is observed,
    a UserPromptSubmit hook whose run shows config.json applies, a system
    prompt, a CLAUDE.md destination naming the base config home, which
    an isolated install re-roots into the profile, and, when it names the
    command, a profile-scoped MCP server (which a base install has no
    launcher for).

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
    if command_names:
        config['command-names'] = [PROFILE]
        config['mcp-servers'] = [{
            'name': PROFILE_MCP, 'scope': 'profile', 'command': sys.executable,
            'args': ['-c', 'import sys; sys.exit(1)'],
        }]
    path = configs / 'team.yaml'
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
    """Mark onboarding complete, the fake key approved and every start directory trusted in the profile's .claude.json."""
    path = profile_dir / '.claude.json'
    content: dict[str, Any] = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
    content['hasCompletedOnboarding'] = True
    content['customApiKeyResponses'] = {'approved': [support.FAKE_API_KEY[-20:]], 'rejected': []}
    projects = content.setdefault('projects', {})
    for directory in directories:
        projects.setdefault(str(directory), {})['hasTrustDialogAccepted'] = True
    path.write_text(json.dumps(content), encoding='utf-8')


@dataclass
class Layout:
    """An isolated home with a base profile, a project below it, and the installed isolated profile."""

    root: Path
    home: Path
    project: Path
    profile_dir: Path
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

    def run(self, argv: list[str] | str, cwd: Path, *, env: dict[str, str] | None = None) -> support.ClaudeRun:
        """Run one turn through ``argv`` from ``cwd`` and attach what the fake API recorded.

        Args:
            argv: The command line; a string is handed to the OS verbatim.
            cwd: The working directory the session starts in.
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


def _build_layout(tmp_path: Path) -> Iterator[Layout]:
    root, cleanup = support.workspace_root(tmp_path)
    home = root / 'home'
    project = home / 'work' / 'project'
    project.mkdir(parents=True)
    markers = {
        name: root / f'{name}.marker'
        for name in ('base-hook', 'base-local-hook', 'project-hook', 'profile-hook')
    }
    _write_base_profile(home, markers)
    _write_project(project, markers)
    config = _write_configuration(root / 'configs', project, markers['profile-hook'])
    _run_setup(config, home)
    profile_dir = home / '.claude' / PROFILE
    assert (profile_dir / 'launch.sh').is_file()
    _trust(profile_dir, [home, project])
    server = FakeAnthropicServer().start()
    try:
        yield Layout(root=root, home=home, project=project, profile_dir=profile_dir, markers=markers, server=server)
    finally:
        server.stop()
        cleanup()


@pytest.fixture(scope='module')
def layout(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Layout]:
    """One installed isolated profile beside a base profile and a project, shared by the module's tests."""
    yield from _build_layout(tmp_path_factory.mktemp('base-home-isolation'))


def _bash() -> str:
    bash = setup_environment.find_bash_windows() if sys.platform == 'win32' else shutil.which('bash')
    if bash is None:
        pytest.skip('bash is required to run the toolbox launcher')
    return bash


def _entry_points(layout: Layout) -> list[tuple[str, list[str] | str]]:
    """Every way a user starts the profile, each handing it one non-interactive turn."""
    args = support.print_args(PROMPT)
    local_bin = layout.home / '.local' / 'bin'
    bash = _bash()
    points: list[tuple[str, list[str] | str]] = [('launch.sh', [bash, (layout.profile_dir / 'launch.sh').as_posix(), *args])]
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
    """The profile's config.json, memory, rule, prompt, skill, agent, command and MCP server all apply."""
    assert 'profile-hook' in layout.hooks_ran(), layout.hooks_ran()
    assert SENTINELS['profile-claude-md'] in run.body_text, run.describe()
    assert SENTINELS['profile-rule'] in run.body_text, run.describe()
    assert SENTINELS['profile-prompt'] in run.system_text, run.describe()
    assert PROFILE_SKILL in init['skills'], init['skills']
    assert PROFILE_AGENT in init['agents'], init['agents']
    assert PROFILE_COMMAND in init['slash_commands'], init['slash_commands']
    assert PROFILE_MCP in [server.get('name') for server in init['mcp_servers']], init['mcp_servers']


@pytest.mark.parametrize('entry_point', _entry_point_ids())
def test_session_started_in_the_home_folder_reads_nothing_from_the_base_profile(layout: Layout, entry_point: str) -> None:
    """In the home folder the base profile is the project .claude; the launcher keeps every channel of it shut.

    The profile's own config.json still applies there: its hook runs, its
    MCP server is configured and its memory, rule, prompt, skill, agent and
    command load.
    """
    argv = dict(_entry_points(layout))[entry_point]

    run = layout.run(argv, layout.home)

    init = _assert_turn(run)
    _assert_nothing_from_the_base(layout, run, init)
    _assert_profile_applies(layout, run, init)
    assert PROJECT_HEADER not in layout.headers(), layout.headers()
    assert 'project-hook' not in layout.hooks_ran(), layout.hooks_ran()


@pytest.mark.parametrize('entry_point', _entry_point_ids())
def test_session_started_in_a_project_below_the_home_keeps_the_project_and_drops_the_base(
    layout: Layout, entry_point: str,
) -> None:
    """Below the home the project's own files load as before while the base profile's memory stays out.

    The project's settings.json sets the model, the env header and a hook;
    its CLAUDE.md, .claude/CLAUDE.md and rule load; its skill, agent and
    command are listed. The CLAUDE.local.md the configuration itself
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
    for key in ('project-claude-md', 'project-dot-claude-md', 'project-rule'):
        assert SENTINELS[key] in run.body_text, f'{key} missing: {run.describe()}'
    assert SENTINELS['project-claude-local'] not in run.body_text, run.describe()
    assert PROJECT_SKILL in init['skills'], init['skills']
    assert PROJECT_AGENT in init['agents'], init['agents']
    assert PROJECT_COMMAND in init['slash_commands'], init['slash_commands']


def test_config_json_carries_the_declared_and_the_base_exclusions(layout: Layout) -> None:
    """config.json holds the configuration's own exclusion first and the base profile's memory files after it."""
    settings = json.loads((layout.profile_dir / 'config.json').read_text(encoding='utf-8'))
    base = (layout.home / '.claude').as_posix()

    assert settings[CLAUDE_MD_EXCLUDES_KEY] == [
        f'{layout.project.as_posix()}/CLAUDE.local.md', f'{base}/CLAUDE.md', f'{base}/CLAUDE.local.md', f'{base}/rules/**',
    ]


def test_control_without_the_toolbox_exclusions_shows_every_base_channel_leaking(layout: Layout) -> None:
    """The same binary, settings and layout without the exclusions and the launcher load the base profile.

    Run with claude itself under the profile's CLAUDE_CONFIG_DIR, as the
    launcher exports it, with a copy of config.json stripped of
    claudeMdExcludes: in the home folder the base profile's settings.json
    sets the model and the header, both base hooks run, and its CLAUDE.md
    and rule load; below the home its CLAUDE.md and rule still load and the
    configuration's own exclusion no longer applies. This is what every
    negative assertion of the other tests would otherwise miss.
    """
    assert support.CLAUDE_CMD is not None
    settings = json.loads((layout.profile_dir / 'config.json').read_text(encoding='utf-8'))
    del settings[CLAUDE_MD_EXCLUDES_KEY]
    control = layout.root / 'control-config.json'
    control.write_text(json.dumps(settings), encoding='utf-8')
    argv = [str(support.CLAUDE_CMD), *support.print_args(PROMPT), '--settings', str(control)]
    env = {**layout.session_env(), 'CLAUDE_CONFIG_DIR': str(layout.profile_dir)}

    at_home = layout.run(argv, layout.home, env=env)
    init = _assert_turn(at_home)
    assert at_home.bodies[0].get('model') == BASE_MODEL, at_home.describe()
    assert BASE_HEADER in layout.headers(), layout.headers()
    assert {'base-hook', 'base-local-hook', 'profile-hook'} <= layout.hooks_ran(), layout.hooks_ran()
    assert SENTINELS['base-claude-md'] in at_home.body_text, at_home.describe()
    assert SENTINELS['base-rule'] in at_home.body_text, at_home.describe()
    assert BASE_SKILL not in init['skills'], init['skills']

    below = layout.run(argv, layout.project, env=env)
    _assert_turn(below)
    assert SENTINELS['base-claude-md'] in below.body_text, below.describe()
    assert SENTINELS['base-rule'] in below.body_text, below.describe()
    assert SENTINELS['project-claude-local'] in below.body_text, below.describe()
    assert 'base-hook' not in layout.hooks_ran(), layout.hooks_ran()


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
        markers = {'base-hook': root / 'unused-1', 'base-local-hook': root / 'unused-2',
                   'project-hook': root / 'unused-3', 'profile-hook': root / 'profile-hook.marker'}
        config = _write_configuration(root / 'configs', project, markers['profile-hook'], command_names=False)
        _run_setup(config, home)
        _write(home / '.claude' / 'CLAUDE.md', f'Sentinel {SENTINELS["base-claude-md"]}\n')
        _run_setup(config, home, '--command-names', PROFILE, '--link-dirs', 'rules', '--link-from', 'base')
        profile_dir = home / '.claude' / PROFILE
        settings = json.loads((profile_dir / 'config.json').read_text(encoding='utf-8'))
        base = (home / '.claude').as_posix()
        assert settings[CLAUDE_MD_EXCLUDES_KEY] == [
            f'{project.as_posix()}/CLAUDE.local.md', f'{base}/CLAUDE.md', f'{base}/CLAUDE.local.md',
        ]
        _trust(profile_dir, [home, project])
        server = FakeAnthropicServer().start()
        try:
            layout = Layout(root=root, home=home, project=project, profile_dir=profile_dir, markers=markers, server=server)
            argv = [_bash(), (profile_dir / 'launch.sh').as_posix(), *support.print_args(PROMPT)]

            run = layout.run(argv, project)

            _assert_turn(run)
            assert SENTINELS['profile-rule'] in run.body_text, run.describe()
            assert SENTINELS['base-claude-md'] not in run.body_text, run.describe()
        finally:
            server.stop()
    finally:
        cleanup()
