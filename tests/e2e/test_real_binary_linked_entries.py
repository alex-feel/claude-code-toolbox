"""E2E tests proving that linked profile entries load through the real Claude Code binary.

For each of the eight linkable entries of a profile directory -- skills,
agents, commands, rules, hooks, output-styles, prompts and projects -- the
real binary runs one non-interactive turn against an offline fake API with
CLAUDE_CONFIG_DIR pointing at a profile whose entry is a real directory, a
directory symlink, or (Windows) a junction created with the primitive
link_profile_directory() uses. Each entry carries a sentinel that is only
observable when the entry loaded: in the recorded request body, in the
stream-json init message, in the hook's marker file, or as a session file at
the link target. A negative control per entry (the entry absent) shows the
sentinel missing, so every positive assertion is discriminating.

hooks is proven with what an installed hooks/ holds beside the script: the
helper module the script imports from its own directory, the
project-overrides/ file it reads next to itself, and the uv script lockfile
uv reads beside it under UV_LOCKED=1 (a lockfile made stale after locking
stops the hook with uv's stale-lockfile error through every link kind, while
a lockfile uv could not find would only draw a warning and let the script
run). prompts is proven through the toolbox launcher
create_launcher_script() writes, which passes the file with
--system-prompt-file (replace mode) or --append-system-prompt-file (append
mode); projects is proven by a session written through the link landing at
the link target and resuming from a second profile that links the same
target.

Skipped when the binary is absent; CLAUDE_CODE_TOOLBOX_REQUIRE_REAL_BINARY=1
(set in CI) turns absence into a failure instead of a silent skip. A
Windows symlink the OS refuses skips only that variant, with the reason.
"""

from __future__ import annotations

import os
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from scripts import setup_environment
from tests.e2e import linked_entries_support as support
from tests.e2e.linked_entries_workspace import Workspace
from tests.e2e.linked_entries_workspace import open_workspace

_REQUIRE_REAL_BINARY = os.environ.get('CLAUDE_CODE_TOOLBOX_REQUIRE_REAL_BINARY') == '1'
_PROFILE_NAME = 'e2e-linked'
_PROMPT = 'Reply with the single word READY.'

pytestmark = [
    pytest.mark.real_binary,
    pytest.mark.skipif(
        support.CLAUDE_CMD is None and not _REQUIRE_REAL_BINARY,
        reason='claude binary not available',
    ),
]


@pytest.fixture
def workspace(tmp_path: Path) -> Iterator[Workspace]:
    """Provide an isolated home, a populated source profile and a running fake API."""
    yield from open_workspace(tmp_path)


def _assert_single_turn(run: support.ClaudeRun) -> dict[str, Any]:
    """Assert the turn completed with one request and return its init message."""
    assert run.returncode == 0, run.describe()
    assert len(run.bodies) == 1, run.describe()
    assert run.init is not None, run.describe()
    return run.init


# --- skills -----------------------------------------------------------------


@pytest.mark.parametrize('kind', support.link_kinds())
def test_skill_loads_through_link(workspace: Workspace, kind: str) -> None:
    """The skill under a linked skills/ is listed at init and described in the request."""
    profile = workspace.make_profile(_PROFILE_NAME, kind)

    run = profile.run(_PROMPT)

    init = _assert_single_turn(run)
    assert support.SKILL_NAME in init['skills'], run.describe()
    assert support.SENTINELS['skills'] in run.body_text, run.describe()


def test_skill_absent_does_not_load(workspace: Workspace) -> None:
    """Without skills/, neither the init list nor the request carries the skill."""
    profile = workspace.make_profile(_PROFILE_NAME, 'real', absent=frozenset({'skills'}))

    run = profile.run(_PROMPT)

    init = _assert_single_turn(run)
    assert support.SKILL_NAME not in init['skills'], run.describe()
    assert support.SENTINELS['skills'] not in run.body_text, run.describe()


# --- agents -----------------------------------------------------------------


@pytest.mark.parametrize('kind', support.link_kinds())
def test_agent_loads_through_link(workspace: Workspace, kind: str) -> None:
    """The agent under a linked agents/ is listed at init and described in the request."""
    profile = workspace.make_profile(_PROFILE_NAME, kind)

    run = profile.run(_PROMPT)

    init = _assert_single_turn(run)
    assert support.AGENT_NAME in init['agents'], run.describe()
    assert support.SENTINELS['agents'] in run.body_text, run.describe()


def test_agent_absent_does_not_load(workspace: Workspace) -> None:
    """Without agents/, neither the init list nor the request carries the agent."""
    profile = workspace.make_profile(_PROFILE_NAME, 'real', absent=frozenset({'agents'}))

    run = profile.run(_PROMPT)

    init = _assert_single_turn(run)
    assert support.AGENT_NAME not in init['agents'], run.describe()
    assert support.SENTINELS['agents'] not in run.body_text, run.describe()


# --- commands ---------------------------------------------------------------


@pytest.mark.parametrize('kind', support.link_kinds())
def test_command_expands_through_link(workspace: Workspace, kind: str) -> None:
    """Invoking the command under a linked commands/ sends its body."""
    profile = workspace.make_profile(_PROFILE_NAME, kind)

    run = profile.run(f'/{support.COMMAND_NAME}')

    init = _assert_single_turn(run)
    assert support.COMMAND_NAME in init['slash_commands'], run.describe()
    assert support.SENTINELS['commands'] in run.body_text, run.describe()


def test_command_absent_is_sent_literally(workspace: Workspace) -> None:
    """Without commands/, the slash command is unknown and reaches the API as typed."""
    profile = workspace.make_profile(_PROFILE_NAME, 'real', absent=frozenset({'commands'}))

    run = profile.run(f'/{support.COMMAND_NAME}')

    init = _assert_single_turn(run)
    assert support.COMMAND_NAME not in init['slash_commands'], run.describe()
    assert support.SENTINELS['commands'] not in run.body_text, run.describe()
    assert f'/{support.COMMAND_NAME}' in run.body_text, run.describe()


# --- rules ------------------------------------------------------------------


@pytest.mark.parametrize('kind', support.link_kinds())
def test_rule_loads_through_link(workspace: Workspace, kind: str) -> None:
    """The rule under a linked rules/ is sent with the request."""
    profile = workspace.make_profile(_PROFILE_NAME, kind)

    run = profile.run(_PROMPT)

    _assert_single_turn(run)
    assert support.SENTINELS['rules'] in run.body_text, run.describe()


def test_rule_absent_does_not_load(workspace: Workspace) -> None:
    """Without rules/, the request carries no rule content."""
    profile = workspace.make_profile(_PROFILE_NAME, 'real', absent=frozenset({'rules'}))

    run = profile.run(_PROMPT)

    _assert_single_turn(run)
    assert support.SENTINELS['rules'] not in run.body_text, run.describe()


# --- hooks ------------------------------------------------------------------


@pytest.mark.parametrize('kind', support.link_kinds())
def test_hooks_run_through_link(workspace: Workspace, kind: str) -> None:
    """The hook script under a linked hooks/ runs on SessionStart and UserPromptSubmit with its siblings.

    config.json names the script under the profile; the marker the script
    writes shows that path as ``file`` and the directory the link resolves
    to as ``realpath``, and carries the sentinels of the helper module it
    imported and the project-overrides/ file it read beside itself. Its
    ``sys_path0`` resolves to the directory that holds the helper for real:
    CPython canonicalizes the script path on POSIX, so the module search
    root is the link target there, while on Windows it stays the profile
    path. The lockfile locked beside the source script is visible beside
    the profile's script, where uv reads it under UV_LOCKED=1.
    """
    profile = workspace.make_profile(_PROFILE_NAME, kind)
    profile_hooks = profile.config_dir / 'hooks'
    assert (profile_hooks / support.HOOK_LOCKFILE).is_file()

    run = profile.run(_PROMPT)

    _assert_single_turn(run)
    assert run.hook_responses, run.describe()
    assert all(response.get('exit_code') == 0 for response in run.hook_responses), run.describe()
    # uv found the lockfile beside the script: it warns when there is none
    assert all('No lockfile found' not in str(response.get('stderr', '')) for response in run.hook_responses), (
        run.describe()
    )
    records = workspace.hook_records()
    assert {record['event'] for record in records} == {'SessionStart', 'UserPromptSubmit'}, records
    real_holder = profile.config_dir if kind == 'real' else workspace.source
    real_hooks = real_holder / 'hooks'
    for record in records:
        assert Path(record['file']) == profile_hooks / support.HOOK_SCRIPT, record
        assert Path(record['sys_path0']).resolve() == real_hooks.resolve(), record
        assert Path(record['realpath']).resolve() == (real_hooks / support.HOOK_SCRIPT).resolve(), record
        assert record['helper'] == support.HELPER_SENTINEL, record
        assert record['override'] == support.OVERRIDE_SENTINEL, record


@pytest.mark.parametrize('kind', support.link_kinds())
def test_hooks_stale_lock_stops_the_hook(workspace: Workspace, kind: str) -> None:
    """A lockfile that no longer matches the script stops the hook through every link kind.

    uv reads the lockfile beside the script it is given; under UV_LOCKED=1 a
    stale one makes uv refuse to run the script with its "needs to be
    updated" error, while a lockfile uv cannot find only draws a "No
    lockfile found" warning and lets the script run. The script not running
    and the hook failing with that error therefore prove the lockfile is
    read through the link.

    What the failure does to the turn follows uv's exit code, which the
    SessionStart response reports for the command UserPromptSubmit runs as
    well: uv exits 2 on a stale lockfile before 0.12.14 and 1 from 0.12.14
    on, and Claude Code blocks a UserPromptSubmit only when its hook exits
    2, so the turn is blocked exactly when the hook exited 2 and otherwise
    completes without the hook.
    """
    support.make_hook_lock_stale(workspace.source)
    profile = workspace.make_profile(_PROFILE_NAME, kind)

    run = profile.run(_PROMPT)

    assert not workspace.hook_records(), run.describe()
    errors = [response for response in run.hook_responses if response.get('outcome') == 'error']
    assert errors, run.describe()
    for response in errors:
        stderr = str(response.get('stderr', ''))
        assert 'needs to be updated' in stderr, run.describe()
        assert 'No lockfile found' not in stderr, run.describe()
    exit_codes = {response.get('exit_code') for response in errors}
    assert len(exit_codes) == 1, run.describe()
    exit_code = exit_codes.pop()
    assert exit_code not in (0, None), run.describe()
    blocked = exit_code == 2
    assert len(run.bodies) == (0 if blocked else 1), run.describe()
    assert run.result is not None, run.describe()
    assert ('blocked by hook' in str(run.result.get('result', ''))) is blocked, run.describe()


def test_hooks_absent_block_the_prompt(workspace: Workspace) -> None:
    """Without hooks/, the configured command cannot spawn and UserPromptSubmit blocks the turn."""
    profile = workspace.make_profile(_PROFILE_NAME, 'real', absent=frozenset({'hooks'}))

    run = profile.run(_PROMPT)

    assert not workspace.hook_records(), run.describe()
    assert len(run.bodies) == 0, run.describe()
    assert any(response.get('outcome') == 'error' for response in run.hook_responses), run.describe()
    assert run.result is not None, run.describe()
    assert 'blocked by hook' in str(run.result.get('result', '')), run.describe()


# --- output-styles ----------------------------------------------------------


@pytest.mark.parametrize('kind', support.link_kinds())
def test_output_style_loads_through_link(workspace: Workspace, kind: str) -> None:
    """The style under a linked output-styles/ is sent with the request."""
    profile = workspace.make_profile(_PROFILE_NAME, kind)

    run = profile.run(_PROMPT)

    init = _assert_single_turn(run)
    assert init['output_style'] == support.STYLE_NAME, run.describe()
    assert support.SENTINELS['output-styles'] in run.body_text, run.describe()


def test_output_style_absent_does_not_load(workspace: Workspace) -> None:
    """Without output-styles/, the init echoes the configured name but the request has no style body."""
    profile = workspace.make_profile(_PROFILE_NAME, 'real', absent=frozenset({'output-styles'}))

    run = profile.run(_PROMPT)

    init = _assert_single_turn(run)
    assert init['output_style'] == support.STYLE_NAME, run.describe()
    assert support.SENTINELS['output-styles'] not in run.body_text, run.describe()


# --- prompts ----------------------------------------------------------------


@pytest.mark.parametrize('mode', ['replace', 'append'])
@pytest.mark.parametrize('kind', support.link_kinds())
def test_prompt_file_is_read_through_link_by_launcher(workspace: Workspace, kind: str, mode: str) -> None:
    """The launcher passes the prompt file under a linked prompts/ and its content reaches the system prompt."""
    profile = workspace.make_profile(_PROFILE_NAME, kind)

    run = profile.run_launcher(mode, _PROMPT)

    _assert_single_turn(run)
    assert support.SENTINELS['prompts'] in run.system_text, run.describe()


@pytest.mark.parametrize('mode', ['replace', 'append'])
def test_prompt_file_absent_stops_the_launcher(workspace: Workspace, mode: str) -> None:
    """Without prompts/, the launcher refuses to start claude and no request is made."""
    profile = workspace.make_profile(_PROFILE_NAME, 'real', absent=frozenset({'prompts'}))

    run = profile.run_launcher(mode, _PROMPT)

    assert run.returncode != 0, run.describe()
    # The Windows launcher reports on stderr, the Unix launcher on stdout
    assert 'System prompt not found' in run.stdout + run.stderr, run.describe()
    assert len(run.bodies) == 0, run.describe()


# --- projects ---------------------------------------------------------------


@pytest.mark.parametrize('kind', support.link_only_kinds())
def test_session_written_through_link_lands_at_target(workspace: Workspace, kind: str) -> None:
    """A session of a profile whose projects/ is a link is stored under the link target."""
    profile = workspace.make_profile(_PROFILE_NAME, kind)
    session_id = str(uuid.uuid4())

    run = profile.run(_PROMPT, '--session-id', session_id)

    init = _assert_single_turn(run)
    assert init['session_id'] == session_id, run.describe()
    stored = support.session_file(workspace.source / 'projects', session_id)
    assert stored is not None, f'session not found under {workspace.source / "projects"}'
    through_link = support.session_file(profile.config_dir / 'projects', session_id)
    assert through_link is not None, f'session not visible under {profile.config_dir / "projects"}'
    assert through_link.resolve() == stored.resolve()


def test_session_of_unlinked_profile_stays_in_profile(workspace: Workspace) -> None:
    """With a real projects/, the session stays in the profile and never reaches the source."""
    profile = workspace.make_profile(_PROFILE_NAME, 'real')
    session_id = str(uuid.uuid4())

    run = profile.run(_PROMPT, '--session-id', session_id)

    _assert_single_turn(run)
    assert support.session_file(profile.config_dir / 'projects', session_id) is not None
    assert support.session_file(workspace.source / 'projects', session_id) is None


@pytest.mark.parametrize('kind', support.link_only_kinds())
def test_session_resumes_from_another_profile_linking_the_same_target(
    workspace: Workspace, kind: str,
) -> None:
    """A session one profile wrote through the link resumes and continues from a second linked profile."""
    writer = workspace.make_profile('e2e-writer', kind)
    reader = workspace.make_profile('e2e-reader', kind)
    session_id = str(uuid.uuid4())
    first_prompt = 'Remember the word PINEAPPLE.'
    assert writer.run(first_prompt, '--session-id', session_id).returncode == 0

    resumed = reader.run('Continue.', '--resume', session_id)

    init = _assert_single_turn(resumed)
    assert init['session_id'] == session_id, resumed.describe()
    assert first_prompt in resumed.body_text, resumed.describe()

    continued = reader.run('Continue again.', '--continue')

    init = _assert_single_turn(continued)
    assert init['session_id'] == session_id, continued.describe()


@pytest.mark.parametrize('kind', support.link_only_kinds())
def test_session_is_not_resumable_from_a_profile_without_the_link(workspace: Workspace, kind: str) -> None:
    """A profile with its own real projects/ cannot resume a session stored at the link target."""
    writer = workspace.make_profile('e2e-writer', kind)
    reader = workspace.make_profile('e2e-reader', 'real')
    session_id = str(uuid.uuid4())
    assert writer.run('Remember the word PINEAPPLE.', '--session-id', session_id).returncode == 0

    resumed = reader.run('Continue.', '--resume', session_id)

    assert resumed.returncode != 0, resumed.describe()
    assert len(resumed.bodies) == 0, resumed.describe()
    assert 'No conversation found' in resumed.stdout + resumed.stderr, resumed.describe()


def test_link_profile_directory_carries_sessions_to_the_base(workspace: Workspace) -> None:
    """The projects link the toolbox creates stores the profile's sessions under the base ~/.claude/projects."""
    profile = workspace.make_profile(_PROFILE_NAME, 'real', absent=frozenset({'projects'}))
    base_projects = workspace.home / '.claude' / 'projects'
    setup_environment.link_profile_directory(profile.config_dir / 'projects', base_projects)
    assert support.entry_is_link_to(profile.config_dir / 'projects', base_projects)
    session_id = str(uuid.uuid4())

    run = profile.run(_PROMPT, '--session-id', session_id)

    _assert_single_turn(run)
    assert support.session_file(base_projects, session_id) is not None


# --- identical behavior across kinds ----------------------------------------


def test_entries_load_identically_across_link_kinds(workspace: Workspace, tmp_path: Path) -> None:
    """Every link kind yields the same init lists and the same sentinel hits as the real directories."""
    observations: dict[str, dict[str, Any]] = {}
    for kind in support.available_link_kinds(tmp_path):
        profile = workspace.make_profile(f'e2e-{kind}', kind)
        run = profile.run(f'/{support.COMMAND_NAME}')
        init = _assert_single_turn(run)
        observations[kind] = {
            'skills': sorted(init['skills']),
            'agents': sorted(init['agents']),
            'slash_commands': sorted(init['slash_commands']),
            'output_style': init['output_style'],
            'sentinels': {
                entry: sentinel in run.body_text for entry, sentinel in support.SENTINELS.items() if entry != 'prompts'
            },
        }
    assert 'real' in observations
    assert len(observations) >= 2, f'no link kind could be created on {sys.platform}: {observations}'
    for kind, observed in observations.items():
        assert observed == observations['real'], f'{kind} differs from real: {observed} != {observations["real"]}'
