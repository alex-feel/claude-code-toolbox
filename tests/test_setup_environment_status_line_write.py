"""Tests for the base settings.json status line, which Step 18 writes whole on every run.

Step 18 merges the profile settings delta into the shared settings.json, so
every other key and every hook group stays, but the status line object the
configuration builds replaces the one in the file: a member a later
configuration leaves out is gone after the next run, a member added by hand
or by /statusline is replaced, and the digest the manifest records equals the
value in the file. A null status line still deletes it, and a run whose
configuration declares no status line leaves the file's as it is.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts import setup_environment
from scripts.setup_environment import LiveLeftoverState


def _status_delta(hooks_dir: Path, **members: Any) -> dict[str, Any]:
    """The Step 18 delta of a status-line declaration running hooks/s.py."""
    return setup_environment._build_profile_settings({'statusLine': {'file': 's.py', **members}}, hooks_dir)


def _write(claude_dir: Path, content: dict[str, Any]) -> None:
    (claude_dir / 'settings.json').write_text(json.dumps(content), encoding='utf-8')


def _read(claude_dir: Path) -> dict[str, Any]:
    content: dict[str, Any] = json.loads((claude_dir / 'settings.json').read_text(encoding='utf-8'))
    return content


@pytest.fixture
def claude_dir(tmp_path: Path) -> Path:
    directory = tmp_path / '.claude'
    (directory / 'hooks').mkdir(parents=True)
    return directory


class TestStep18WritesTheStatusLineWhole:
    """The status line object the configuration builds replaces the file's, and nothing else is replaced."""

    @pytest.mark.parametrize('member', ['padding', 'refreshInterval', 'hideVimModeIndicator'])
    def test_a_member_the_new_object_lacks_is_gone(self, claude_dir: Path, member: str) -> None:
        """A member an earlier configuration wrote, or one added by hand, does not survive the next write."""
        hooks_dir = claude_dir / 'hooks'
        earlier = {**_status_delta(hooks_dir)['statusLine'], member: 7}
        _write(claude_dir, {'statusLine': earlier})
        delta = _status_delta(hooks_dir)

        assert setup_environment.write_profile_settings_to_settings(delta, claude_dir)

        assert _read(claude_dir)['statusLine'] == delta['statusLine']
        assert member not in _read(claude_dir)['statusLine']

    def test_a_null_member_is_never_written(self, claude_dir: Path) -> None:
        hooks_dir = claude_dir / 'hooks'
        _write(claude_dir, {'statusLine': {**_status_delta(hooks_dir)['statusLine'], 'padding': 2}})

        assert setup_environment.write_profile_settings_to_settings(_status_delta(hooks_dir, padding=None), claude_dir)

        status_line = _read(claude_dir)['statusLine']
        assert set(status_line) == {'type', 'command'}, 'the null member is dropped, not written as JSON null'
        assert None not in status_line.values()

    def test_a_null_status_line_deletes_it(self, claude_dir: Path) -> None:
        _write(claude_dir, {'statusLine': {'type': 'command', 'command': 'x'}, 'model': 'opus'})

        assert setup_environment.write_profile_settings_to_settings({'statusLine': None}, claude_dir)

        assert _read(claude_dir) == {'model': 'opus'}

    def test_a_delta_without_a_status_line_leaves_the_file_s_as_it_is(self, claude_dir: Path) -> None:
        mine = {'type': 'command', 'command': 'bash ~/.claude/statusline-command.sh', 'padding': 1}
        _write(claude_dir, {'statusLine': mine})
        delta = setup_environment._build_profile_settings(
            {'hooks': {'files': ['hooks/a.py'], 'events': [{'event': 'Stop', 'type': 'command', 'command': 'a.py'}]}},
            claude_dir / 'hooks',
        )

        assert setup_environment.write_profile_settings_to_settings(delta, claude_dir)

        assert _read(claude_dir)['statusLine'] == mine

    def test_every_other_key_and_hook_group_still_merges(self, claude_dir: Path) -> None:
        """Only the status line is replaced: a key outside the delta and a hook group the user wrote stay."""
        hooks_dir = claude_dir / 'hooks'
        user_group = {'matcher': '', 'hooks': [{'type': 'command', 'command': 'echo mine'}]}
        _write(claude_dir, {'model': 'opus', 'hooks': {'Stop': [user_group]}, 'statusLine': {'type': 'command'}})
        delta = setup_environment._build_profile_settings({
            'statusLine': {'file': 's.py'},
            'hooks': {'files': ['hooks/a.py'], 'events': [{'event': 'Stop', 'type': 'command', 'command': 'a.py'}]},
        }, hooks_dir)

        assert setup_environment.write_profile_settings_to_settings(delta, claude_dir)

        content = _read(claude_dir)
        assert content['model'] == 'opus'
        assert content['hooks']['Stop'] == [user_group, *delta['hooks']['Stop']]
        assert content['statusLine'] == delta['statusLine']

    def test_the_recorded_digest_equals_the_status_line_in_the_file(self, claude_dir: Path) -> None:
        """The manifest's whole-object record matches what the file holds after the write, so it stays removable."""
        hooks_dir = claude_dir / 'hooks'
        _write(claude_dir, {'statusLine': {**_status_delta(hooks_dir)['statusLine'], 'refreshInterval': 30}})
        delta = _status_delta(hooks_dir, padding=None)

        assert setup_environment.write_profile_settings_to_settings(delta, claude_dir)

        records = setup_environment.written_settings_records(None, delta)
        assert [record['sha256'] for record in records if record['path'] == ['statusLine']] == [
            setup_environment.leftover_digest(_read(claude_dir)['statusLine']),
        ]


class TestMergeSettingsDelta:
    """One merge serves the Step 18 write and the summary's view of the file before it."""

    @pytest.mark.parametrize(('delta', 'expected'), [
        ({'statusLine': {'type': 'command', 'command': 'new', 'padding': None}}, {'type': 'command', 'command': 'new'}),
        ({'statusLine': None}, None),
        ({'model': 'x'}, {'type': 'command', 'command': 'old', 'padding': 3}),
    ], ids=['object-replaces', 'null-deletes', 'absent-keeps'])
    def test_a_key_written_whole(self, delta: dict[str, Any], expected: dict[str, Any] | None) -> None:
        existing = {'statusLine': {'type': 'command', 'command': 'old', 'padding': 3}, 'hooks': {'Stop': [1]}}

        merged = setup_environment.merge_settings_delta(
            existing, delta, written_whole=setup_environment.SETTINGS_OBJECTS_WRITTEN_WHOLE,
        )

        assert merged.get('statusLine') == expected
        assert merged['hooks'] == {'Stop': [1]}
        assert existing['statusLine'] == {'type': 'command', 'command': 'old', 'padding': 3}, 'the input stays'

    def test_without_keys_written_whole_every_object_merges(self) -> None:
        existing = {'statusLine': {'type': 'command', 'command': 'old', 'padding': 3}}

        merged = setup_environment.merge_settings_delta(existing, {'statusLine': {'command': 'new'}})

        assert merged == {'statusLine': {'type': 'command', 'command': 'new', 'padding': 3}}

    def test_the_summary_reads_the_status_line_as_step_18_writes_it(self, claude_dir: Path) -> None:
        """Before consent the base settings.json is read as Step 18 leaves it, with the status line replaced whole."""
        _write(claude_dir, {'statusLine': {'type': 'command', 'command': 'old', 'padding': 3, 'refreshInterval': 9}})
        config = {'hooks': {'files': ['hooks/s.py']}, 'status-line': {'file': 's.py'}}
        planned = setup_environment.planned_records(config, claude_dir, claude_dir=claude_dir, base=True)
        live = LiveLeftoverState.for_profile(
            claude_dir, claude_dir.parent,
            settings_files=setup_environment.leftover_settings_files(claude_dir, isolated=False, before_consent=True),
        )

        view = dict(setup_environment._settings_after_this_run(live, claude_dir, [], planned).settings_after)
        assert setup_environment.write_profile_settings_to_settings(
            setup_environment._build_profile_settings({'statusLine': config['status-line']}, claude_dir / 'hooks'),
            claude_dir,
        )

        assert view[claude_dir / 'settings.json'] == _read(claude_dir)
