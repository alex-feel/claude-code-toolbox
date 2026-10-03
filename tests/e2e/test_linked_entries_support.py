"""Tests of the linked-entries support module, independent of the Claude Code binary.

They pin the behavior the real-binary tests rely on: the fake API's protocol,
the fixture sentinels, the link placement kinds and their detection, the
child environment isolation, and the stream-json parser.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.e2e import linked_entries_support as support
from tests.e2e.fake_anthropic_api import FAKE_REPLY
from tests.e2e.fake_anthropic_api import FakeAnthropicServer


@pytest.fixture
def fake_api() -> Iterator[FakeAnthropicServer]:
    """Start and stop the fake Messages API."""
    server = FakeAnthropicServer().start()
    try:
        yield server
    finally:
        server.stop()


def _post(url: str, payload: dict[str, object] | None) -> tuple[int, str]:
    data = json.dumps(payload).encode('utf-8') if payload is not None else b''
    request = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, response.read().decode('utf-8')


def test_fake_api_records_body_and_streams_one_turn(fake_api: FakeAnthropicServer) -> None:
    """A streaming request is recorded and answered with an SSE turn ending in message_stop."""
    status, text = _post(f'{fake_api.url}/v1/messages?beta=true', {'model': 'm', 'stream': True, 'messages': []})

    assert status == 200
    assert 'event: message_start' in text
    assert FAKE_REPLY in text
    assert text.rstrip().endswith('data: {"type": "message_stop"}')
    assert fake_api.bodies == [{'model': 'm', 'stream': True, 'messages': []}]


def test_fake_api_answers_non_streaming_json(fake_api: FakeAnthropicServer) -> None:
    """A non-streaming request gets the reply as a JSON message with end_turn."""
    status, text = _post(f'{fake_api.url}/v1/messages', {'model': 'm', 'messages': []})

    message = json.loads(text)
    assert status == 200
    assert message['content'] == [{'type': 'text', 'text': FAKE_REPLY}]
    assert message['stop_reason'] == 'end_turn'


def test_fake_api_counts_tokens_and_rejects_other_paths(fake_api: FakeAnthropicServer) -> None:
    """count_tokens returns a fixed count; any other path or method is 404 and is never recorded."""
    status, text = _post(f'{fake_api.url}/v1/messages/count_tokens', {'messages': []})
    assert status == 200
    assert json.loads(text) == {'input_tokens': 42}

    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _post(f'{fake_api.url}/v1/other', {})
    assert excinfo.value.code == 404
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(f'{fake_api.url}/v1/messages', timeout=10)
    assert excinfo.value.code == 404
    assert fake_api.bodies == []


def test_write_source_entries_puts_one_sentinel_per_entry(tmp_path: Path) -> None:
    """Every linkable entry exists, every content sentinel sits in its own file, and the hook script compiles."""
    source = tmp_path / 'source'
    source.mkdir()
    marker = tmp_path / 'marker.jsonl'

    support.write_source_entries(source, marker)

    for entry in support.LINKABLE_ENTRIES:
        assert (source / entry).is_dir(), entry
    files = {
        'skills': source / 'skills' / support.SKILL_NAME / 'SKILL.md',
        'agents': source / 'agents' / f'{support.AGENT_NAME}.md',
        'commands': source / 'commands' / f'{support.COMMAND_NAME}.md',
        'rules': source / 'rules' / 'sentinel-rule.md',
        'output-styles': source / 'output-styles' / f'{support.STYLE_NAME}.md',
        'prompts': source / 'prompts' / support.PROMPT_FILE,
    }
    for entry, sentinel in support.SENTINELS.items():
        content = files[entry].read_text(encoding='utf-8')
        assert sentinel in content, entry
        others = {other for other_entry, other in support.SENTINELS.items() if other_entry != entry}
        assert not any(other in content for other in others), entry
    hook_script = source / 'hooks' / support.HOOK_SCRIPT
    compile(hook_script.read_text(encoding='utf-8'), str(hook_script), 'exec')
    assert json.loads((source / 'hooks' / support.HOOK_CONFIG).read_text(encoding='utf-8')) == {'marker': str(marker)}


def test_write_source_entries_gives_the_hook_its_siblings(tmp_path: Path) -> None:
    """The hook script declares PEP 723 metadata, imports the helper and reads the override beside itself."""
    source = tmp_path / 'source'
    source.mkdir()

    support.write_source_entries(source, tmp_path / 'marker.jsonl')

    hooks_dir = source / 'hooks'
    script = (hooks_dir / support.HOOK_SCRIPT).read_text(encoding='utf-8')
    assert script.startswith('# /// script\n')
    assert f'# requires-python = "{support.HOOK_REQUIRES_PYTHON}"' in script
    assert '# dependencies = []' in script
    assert f'import {support.HOOK_HELPER.removesuffix(".py")}' in script
    assert f'"{support.HOOK_OVERRIDES_DIR}" / "{support.HOOK_OVERRIDE_FILE}"' in script
    helper = (hooks_dir / support.HOOK_HELPER).read_text(encoding='utf-8')
    assert support.HELPER_SENTINEL in helper
    override = json.loads((hooks_dir / support.HOOK_OVERRIDES_DIR / support.HOOK_OVERRIDE_FILE).read_text(encoding='utf-8'))
    assert override == {'override': support.OVERRIDE_SENTINEL}
    assert support.HELPER_SENTINEL not in script
    assert support.OVERRIDE_SENTINEL not in script
    assert not (hooks_dir / support.HOOK_LOCKFILE).exists()


def test_lock_hook_script_writes_the_lockfile_beside_the_script(tmp_path: Path) -> None:
    """uv lock --script records the declared requires-python in <script>.lock next to the script."""
    source = tmp_path / 'source'
    source.mkdir()
    support.write_source_entries(source, tmp_path / 'marker.jsonl')

    lockfile = support.lock_hook_script(source, support.isolated_home_env(tmp_path / 'home'))

    assert lockfile == source / 'hooks' / support.HOOK_LOCKFILE
    assert lockfile.is_file()
    assert f'requires-python = "{support.HOOK_REQUIRES_PYTHON}"' in lockfile.read_text(encoding='utf-8')


def test_make_hook_lock_stale_changes_only_requires_python(tmp_path: Path) -> None:
    """The stale rewrite swaps the requires-python line and leaves the lockfile and the rest of the script alone."""
    source = tmp_path / 'source'
    source.mkdir()
    support.write_source_entries(source, tmp_path / 'marker.jsonl')
    lockfile = support.lock_hook_script(source, support.isolated_home_env(tmp_path / 'home'))
    script = source / 'hooks' / support.HOOK_SCRIPT
    before_script = script.read_text(encoding='utf-8')
    before_lock = lockfile.read_text(encoding='utf-8')

    support.make_hook_lock_stale(source)

    after_script = script.read_text(encoding='utf-8')
    assert f'# requires-python = "{support.HOOK_STALE_REQUIRES_PYTHON}"' in after_script
    assert f'# requires-python = "{support.HOOK_REQUIRES_PYTHON}"' not in after_script
    assert after_script.replace(support.HOOK_STALE_REQUIRES_PYTHON, support.HOOK_REQUIRES_PYTHON) == before_script
    assert lockfile.read_text(encoding='utf-8') == before_lock


def test_command_description_carries_no_sentinel(tmp_path: Path) -> None:
    """The command's description is sentinel-free, so the sentinel proves invocation, not listing."""
    source = tmp_path / 'source'
    source.mkdir()
    support.write_source_entries(source, tmp_path / 'marker.jsonl')

    content = (source / 'commands' / f'{support.COMMAND_NAME}.md').read_text(encoding='utf-8')
    frontmatter, body = content.split('---\n')[1:3]

    assert support.SENTINELS['commands'] not in frontmatter
    assert support.SENTINELS['commands'] in body


@pytest.fixture
def source_and_profile(tmp_path: Path) -> tuple[Path, Path]:
    """Provide a populated source profile and an empty profile directory."""
    source = tmp_path / 'source'
    source.mkdir()
    support.write_source_entries(source, tmp_path / 'marker.jsonl')
    profile = tmp_path / 'profile'
    profile.mkdir()
    return source, profile


def test_place_entry_real_copies_without_a_link(source_and_profile: tuple[Path, Path]) -> None:
    """'real' copies the entry; the copy is a plain directory."""
    source, profile = source_and_profile

    support.place_entry(source, profile, 'rules', 'real')

    assert (profile / 'rules' / 'sentinel-rule.md').is_file()
    assert not support.entry_is_link_to(profile / 'rules', source / 'rules')


def test_place_entry_symlink_resolves_to_source(source_and_profile: tuple[Path, Path]) -> None:
    """'symlink' creates a directory symlink resolving to the source entry."""
    source, profile = source_and_profile

    support.place_entry(source, profile, 'rules', 'symlink')

    assert (profile / 'rules').is_symlink()
    assert support.entry_is_link_to(profile / 'rules', source / 'rules')
    assert (profile / 'rules' / 'sentinel-rule.md').is_file()


@pytest.mark.skipif(sys.platform != 'win32', reason='junctions exist on Windows only')
def test_place_entry_junction_is_a_reparse_point_not_a_symlink(source_and_profile: tuple[Path, Path]) -> None:
    """'junction' creates a reparse point that resolves to the source but is not a symlink."""
    source, profile = source_and_profile

    support.place_entry(source, profile, 'rules', 'junction')

    assert (profile / 'rules').is_dir()
    assert not (profile / 'rules').is_symlink()
    assert support.entry_is_link_to(profile / 'rules', source / 'rules')


def test_place_entry_absent_creates_nothing(source_and_profile: tuple[Path, Path]) -> None:
    """'absent' leaves the profile without the entry."""
    source, profile = source_and_profile

    support.place_entry(source, profile, 'rules', 'absent')

    assert not (profile / 'rules').exists()


def test_place_entry_rejects_unknown_kind(source_and_profile: tuple[Path, Path]) -> None:
    """An unknown kind is a programming error, not a silent no-op."""
    source, profile = source_and_profile

    with pytest.raises(ValueError, match='unknown link kind'):
        support.place_entry(source, profile, 'rules', 'hardlink')


def test_entry_is_link_to_rejects_a_link_to_another_target(source_and_profile: tuple[Path, Path]) -> None:
    """A link resolving elsewhere is not a link to the expected target."""
    source, profile = source_and_profile
    support.place_entry(source, profile, 'rules', 'symlink')

    assert not support.entry_is_link_to(profile / 'rules', source / 'agents')
    assert not support.entry_is_link_to(profile / 'missing', source / 'rules')


def test_link_kinds_match_the_platform() -> None:
    """Junctions are offered on Windows only; 'real' is never a link-only kind."""
    kinds = support.link_kinds()

    assert kinds[0] == 'real'
    assert 'symlink' in kinds
    assert ('junction' in kinds) == (sys.platform == 'win32')
    assert support.link_only_kinds() == kinds[1:]


def test_available_link_kinds_probe_leaves_no_trace(tmp_path: Path) -> None:
    """The symlink probe removes its link and reports a subset of link_kinds()."""
    kinds = support.available_link_kinds(tmp_path)

    assert set(kinds) <= set(support.link_kinds())
    assert 'real' in kinds
    assert not (tmp_path / 'symlink-probe').exists()


def test_claude_child_env_isolates_the_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Session variables are stripped, the home is redirected, and the binary directory leads PATH."""
    monkeypatch.setenv('CLAUDE_CODE_TOOLBOX_DEBUG', '1')
    monkeypatch.setenv('CLAUDE_CODE_GIT_BASH_PATH', 'C:/Git/bin/bash.exe')
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'real-secret')
    monkeypatch.setenv('DISABLE_UPDATES', '1')
    home = tmp_path / 'home'
    config_dir = tmp_path / 'profile'
    claude_cmd = tmp_path / 'bin' / 'claude'

    env = support.claude_child_env(config_dir=config_dir, home=home, api_url='http://127.0.0.1:1', claude_cmd=claude_cmd)

    assert 'CLAUDE_CODE_TOOLBOX_DEBUG' not in env
    assert 'DISABLE_UPDATES' not in env
    assert env['CLAUDE_CODE_GIT_BASH_PATH'] == 'C:/Git/bin/bash.exe'
    assert env['ANTHROPIC_API_KEY'] == support.FAKE_API_KEY
    assert env['ANTHROPIC_BASE_URL'] == 'http://127.0.0.1:1'
    assert env['CLAUDE_CONFIG_DIR'] == str(config_dir)
    assert env['HOME'] == env['USERPROFILE'] == home.as_posix()
    assert env['DISABLE_AUTOUPDATER'] == '1'
    assert env['UV_LOCKED'] == '1'
    assert env['PATH'].split(':' if sys.platform != 'win32' else ';')[0] == str(claude_cmd.parent)
    for name in ('APPDATA', 'LOCALAPPDATA', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'TEMP', 'TMP', 'TMPDIR'):
        assert Path(env[name]).is_dir(), name
        assert Path(env[name]).is_relative_to(home), name


def test_isolated_home_env_has_no_config_dir(tmp_path: Path) -> None:
    """The plain home environment carries no CLAUDE_CONFIG_DIR, so a tool falls back to ~/.claude."""
    env = support.isolated_home_env(tmp_path / 'home')

    assert 'CLAUDE_CONFIG_DIR' not in env
    assert 'ANTHROPIC_API_KEY' not in env


def test_seed_global_config_preapproves_key_and_trusts_project(tmp_path: Path) -> None:
    """The seeded .claude.json completes onboarding, approves the dummy key, and trusts the project."""
    config_dir = tmp_path / 'profile'
    config_dir.mkdir()
    project_dir = tmp_path / 'project'

    support.seed_global_config(config_dir, project_dir)

    seeded = json.loads((config_dir / '.claude.json').read_text(encoding='utf-8'))
    assert seeded['hasCompletedOnboarding'] is True
    assert seeded['customApiKeyResponses']['approved'] == [support.FAKE_API_KEY[-20:]]
    assert seeded['projects'][str(project_dir)]['hasTrustDialogAccepted'] is True


def test_profile_config_sections_declare_both_hook_events() -> None:
    """With hooks enabled the YAML shape names the script and config for SessionStart and UserPromptSubmit."""
    profile_config, user_settings = support.profile_config_sections(True)

    events = profile_config['hooks']['events']
    assert [event['event'] for event in events] == ['SessionStart', 'UserPromptSubmit']
    assert all(event['command'] == support.HOOK_SCRIPT and event['config'] == support.HOOK_CONFIG for event in events)
    assert profile_config['hooks']['files'] == [f'hooks/{support.HOOK_SCRIPT}', f'hooks/{support.HOOK_CONFIG}']
    assert profile_config['hooks']['helpers'] == [f'hooks/{support.HOOK_HELPER}']
    assert user_settings == {'outputStyle': support.STYLE_NAME}
    assert support.profile_config_sections(False) == ({}, {'outputStyle': support.STYLE_NAME})


def test_parse_stream_json_extracts_init_hooks_and_result() -> None:
    """Init, hook responses and the result are picked out; other lines are ignored."""
    stdout = '\n'.join([
        'Starting Claude Code with e2e configuration...',
        json.dumps({'type': 'system', 'subtype': 'init', 'session_id': 'sid', 'skills': []}),
        json.dumps({'type': 'system', 'subtype': 'hook_response', 'hook_name': 'SessionStart:startup', 'exit_code': 0}),
        json.dumps({'type': 'assistant', 'message': {}}),
        json.dumps(['not', 'an', 'object']),
        json.dumps({'type': 'result', 'result': 'FAKE-OK', 'session_id': 'sid'}),
    ])

    init, hook_responses, result = support.parse_stream_json(stdout)

    assert init is not None
    assert init['session_id'] == 'sid'
    assert [response['hook_name'] for response in hook_responses] == ['SessionStart:startup']
    assert result is not None
    assert result['result'] == 'FAKE-OK'


def test_print_args_limit_settings_to_the_config_dir() -> None:
    """The turn is non-interactive, single-turn, stream-json, and reads user-scope settings only."""
    args = support.print_args('hello', '--resume', 'sid')

    assert args[:4] == ['-p', 'hello', '--resume', 'sid']
    assert args[-2:] == ['--setting-sources', 'user']
    assert '--max-turns' in args
    assert args[args.index('--output-format') + 1] == 'stream-json'


def test_session_file_finds_the_transcript_by_id(tmp_path: Path) -> None:
    """A transcript is found under any project subdirectory; a missing one yields None."""
    projects = tmp_path / 'projects'
    transcript = projects / 'C--project' / 'abc.jsonl'
    transcript.parent.mkdir(parents=True)
    transcript.write_text('{}', encoding='utf-8')

    assert support.session_file(projects, 'abc') == transcript
    assert support.session_file(projects, 'missing') is None
