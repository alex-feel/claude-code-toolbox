"""Tests for the leftovers of the base profile's settings.json.

The base settings.json is shared with Claude Code and the user, and the setup
merges what Steps 14 and 18 write into it. A run records a digest of every
value, list element and hook group it writes; a re-run lists the recorded
items its configuration no longer writes, and a run given --remove-leftovers
removes in Step 23 each one that still holds what the setup wrote: a hook
group whole, or, inside a group changed since, only the hooks the setup
wrote. The machine-wide update controls are never recorded.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts import setup_environment
from scripts.setup_environment import LeftoverEntry
from scripts.setup_environment import LeftoverItem
from scripts.setup_environment import LeftoverReadError
from scripts.setup_environment import LeftoverReport
from scripts.setup_environment import LiveLeftoverState
from scripts.setup_environment import PlannedRecords
from tests.e2e.leftovers_support import symlink_file

digest = setup_environment.leftover_digest


def _record(kind: str, path: list[str], value: object) -> dict[str, Any]:
    return {'kind': kind, 'path': path, 'sha256': digest(value)}


def _group_record(event: str, group: dict[str, Any]) -> dict[str, Any]:
    return {
        'kind': 'hook-group', 'path': ['hooks', event], 'sha256': digest(group),
        'matcher': digest(group.get('matcher', '')), 'entries': [digest(entry) for entry in group['hooks']],
    }


def _item(record: dict[str, Any]) -> LeftoverItem:
    item = LeftoverItem.from_record(record, claude_dir=Path('/home/u/.claude'))
    assert item is not None, record
    return item


def _hook(command: str) -> dict[str, Any]:
    return {'type': 'command', 'command': command}


def _sorted(records: list[dict[str, Any]]) -> list[str]:
    return sorted(json.dumps(record, sort_keys=True) for record in records)


@pytest.fixture
def claude_dir(tmp_path: Path) -> Path:
    """The base ~/.claude directory."""
    directory = tmp_path / '.claude'
    directory.mkdir()
    return directory


def _settings(claude_dir: Path, content: dict[str, Any]) -> Path:
    path = claude_dir / 'settings.json'
    path.write_text(json.dumps(content), encoding='utf-8')
    return path


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def _base_live(claude_dir: Path, *, before_consent: bool = True) -> LiveLeftoverState:
    return LiveLeftoverState.for_profile(
        claude_dir, claude_dir.parent,
        settings_files=setup_environment.leftover_settings_files(
            claude_dir, isolated=False, before_consent=before_consent,
        ),
    )


class TestRecords:
    """A run records each value, list element and hook group it writes, never a value itself."""

    def test_values_elements_and_empty_objects_are_recorded_one_by_one(self) -> None:
        delta = {
            'theme': 'dark',
            'gone': None,
            'permissions': {'allow': ['Read', 'Bash(ls)'], 'defaultMode': 'plan'},
            'sandbox': {},
            'env': {'FOO': 'x', 'NULL': None},
            'statusLine': {'type': 'command', 'command': 'c', 'padding': 0},
        }

        records = setup_environment.settings_write_records(delta)

        assert _sorted(records) == _sorted([
            _record('setting', ['theme'], 'dark'),
            _record('setting-element', ['permissions', 'allow'], 'Read'),
            _record('setting-element', ['permissions', 'allow'], 'Bash(ls)'),
            _record('setting', ['permissions', 'defaultMode'], 'plan'),
            _record('setting', ['sandbox'], {}),
            _record('setting', ['env', 'FOO'], 'x'),
            _record('setting', ['statusLine'], {'type': 'command', 'command': 'c', 'padding': 0}),
        ])
        assert 'dark' not in json.dumps(records), 'only digests are recorded'

    def test_the_status_line_is_recorded_whole_as_the_write_leaves_it(self) -> None:
        """A status line is one display setting: one record, its null members left out as the merge deletes them."""
        delta = {'statusLine': {'type': 'command', 'command': 'c', 'padding': None, 'refreshInterval': 5}}

        records = setup_environment.settings_write_records(delta)

        assert records == [_record('setting', ['statusLine'], {'type': 'command', 'command': 'c', 'refreshInterval': 5})]

    def test_hook_groups_are_recorded_whole_with_their_matcher_and_entries(self) -> None:
        pre = {'matcher': '*', 'hooks': [_hook('a'), _hook('b')]}
        stop = {'matcher': '', 'hooks': [_hook('c')]}

        records = setup_environment.settings_write_records({'hooks': {'PreToolUse': [pre], 'Stop': [stop]}})

        assert _sorted(records) == _sorted([_group_record('PreToolUse', pre), _group_record('Stop', stop)])

    def test_machine_wide_controls_are_never_recorded(self) -> None:
        env = {'DISABLE_UPDATES': '1', 'DISABLE_AUTOUPDATER': '1', 'CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL': '1', 'FOO': 'x'}

        records = setup_environment.settings_write_records({'env': env})

        assert records == [_record('setting', ['env', 'FOO'], 'x')]

    def test_written_records_join_the_tilde_expanded_step_14_delta_and_the_step_18_delta(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(setup_environment.sys, 'platform', 'win32')
        user_settings = {'apiKeyHelper': '~/.claude/helper.sh', 'theme': 'dark'}
        delta = {'statusLine': {'type': 'command', 'command': 's'}}

        records = setup_environment.written_settings_records(user_settings, delta)

        expanded = setup_environment._expand_tilde_keys_in_settings(user_settings)['apiKeyHelper']
        assert expanded != '~/.claude/helper.sh'
        assert _record('setting', ['apiKeyHelper'], expanded) in records
        assert _record('setting', ['statusLine'], {'type': 'command', 'command': 's'}) in records
        assert setup_environment.written_settings_records(None, {}) == []

    def test_planned_records_are_computed_without_printing(
        self, claude_dir: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        config = {
            'user-settings': {'theme': 'dark'},
            'hooks': {
                'files': ['hooks/a.py'],
                'events': [
                    {'event': 'Stop', 'type': 'command', 'command': 'a.py', 'unknown-key': 1},
                    {'event': 'Stop', 'type': 'nope', 'command': 'a.py'},
                ],
            },
            'status-line': {'file': 'hooks/a.py'},
        }

        records = setup_environment.planned_settings_records(config, claude_dir)

        assert capsys.readouterr().out == '', 'planning prints none of the warnings Step 18 prints'
        delta = setup_environment._build_profile_settings(
            {'hooks': config['hooks'], 'statusLine': config['status-line']}, claude_dir / 'hooks',
        )
        assert 'ignoring key(s)' in capsys.readouterr().out, 'Step 18 still warns'
        assert _sorted(records) == _sorted(setup_environment.written_settings_records({'theme': 'dark'}, delta))


class TestBuilders:
    """The builders Step 18 runs keep their output and messages; their cores print nothing."""

    def test_hooks_json_core_returns_the_problems_the_builder_prints(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        hooks = {'files': ['a.py'], 'events': [
            {'event': 'Stop', 'type': 'command', 'command': 'a.py'},
            {'event': 'Stop', 'type': 'http'},
        ]}

        result, problems = setup_environment._hooks_json_and_problems(hooks, tmp_path)

        assert capsys.readouterr().out == ''
        assert problems == ['Invalid http hook: missing url, skipping']
        assert setup_environment._build_hooks_json(hooks, tmp_path) == result
        assert 'Invalid http hook: missing url, skipping' in capsys.readouterr().out

    def test_profile_settings_core_returns_the_notes_the_builder_prints(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        profile_config = {'statusLine': {'file': 's.py'}, 'hooks': None}

        build = setup_environment._profile_settings_delta(profile_config, tmp_path)

        assert capsys.readouterr().out == ''
        assert build.notes == ['Setting statusLine: s.py', 'Deleting hooks via explicit null']
        assert setup_environment._build_profile_settings(profile_config, tmp_path) == build.settings
        printed = capsys.readouterr().out
        assert 'Setting statusLine: s.py' in printed
        assert 'Deleting hooks via explicit null' in printed


class TestRecordContract:
    """What a run records is exactly what the real writers leave in settings.json."""

    def test_every_record_is_removable_and_removing_them_restores_the_earlier_file(self, claude_dir: Path) -> None:
        earlier: dict[str, Any] = {
            'model': 'opus',
            'permissions': {'allow': ['Read'], 'deny': ['Bash(rm *)']},
            'hooks': {'Stop': [{'matcher': '', 'hooks': [_hook('user-hook')]}]},
        }
        settings = _settings(claude_dir, earlier)
        user_settings = {
            'theme': 'dark', 'permissions': {'allow': ['Bash(ls)']}, 'env': {'FOO': 'x', 'DISABLE_UPDATES': '1'},
            'apiKeyHelper': '~/.claude/helper.sh',
        }
        config = {
            'user-settings': {key: value for key, value in user_settings.items() if key != 'env'} | {
                'env': {'FOO': 'x'},
            },
            'hooks': {'files': ['hooks/a.py'], 'events': [
                {'event': 'PreToolUse', 'matcher': '*', 'type': 'command', 'command': 'a.py'},
                {'event': 'Stop', 'type': 'command', 'command': 'a.py'},
            ]},
            'status-line': {'file': 'hooks/a.py', 'padding': 1},
        }
        setup_environment.write_user_settings(user_settings, claude_dir)
        delta = setup_environment._build_profile_settings(
            {'hooks': config['hooks'], 'statusLine': config['status-line']}, claude_dir / 'hooks',
        )
        setup_environment.write_profile_settings_to_settings(delta, claude_dir)

        planned = setup_environment.planned_settings_records(config, claude_dir)
        written = setup_environment.written_settings_records(user_settings, delta)
        assert _sorted(planned) == _sorted(written), 'the planned digests equal the written ones'
        entries = [
            setup_environment.settings_item_state(_item(record), _read(settings), written=PlannedRecords())
            for record in written
        ]
        assert {entry.state for entry in entries} == {'removable'}, entries

        outcomes = setup_environment.remove_settings_leftovers(settings, entries, written=PlannedRecords())

        assert {outcome.result for outcome in outcomes} == {'removed'}
        assert len(outcomes) == len(entries)
        restored = _read(settings)
        assert restored.pop('env') == {'DISABLE_UPDATES': '1'}, 'a machine-wide control stays in place'
        assert restored == earlier


class TestItemState:
    """A recorded settings item is removable only while it still holds what the setup wrote."""

    @pytest.mark.parametrize(('content', 'state'), [
        ({'permissions': {'defaultMode': 'plan'}}, 'removable'),
        ({'permissions': {'defaultMode': 'acceptEdits'}}, 'changed'),
        ({'permissions': {}}, 'gone'),
        ({'permissions': ['not', 'an', 'object']}, 'gone'),
        (None, 'gone'),
    ])
    def test_value(self, content: dict[str, Any] | None, state: str) -> None:
        item = _item(_record('setting', ['permissions', 'defaultMode'], 'plan'))

        entry = setup_environment.settings_item_state(item, content, written=PlannedRecords())

        assert entry.state == state

    @pytest.mark.parametrize(('content', 'state'), [
        ({'permissions': {'allow': ['Read', 'Bash(ls)']}}, 'removable'),
        ({'permissions': {'allow': ['Read']}}, 'gone'),
        ({'permissions': {'allow': 'Bash(ls)'}}, 'gone'),
    ])
    def test_element(self, content: dict[str, Any], state: str) -> None:
        item = _item(_record('setting-element', ['permissions', 'allow'], 'Bash(ls)'))

        entry = setup_environment.settings_item_state(item, content, written=PlannedRecords())

        assert entry.state == state
        if state == 'removable':
            assert entry.shown == '"Bash(ls)"'

    @pytest.mark.parametrize(('content', 'state'), [
        ({'statusLine': {'type': 'command', 'command': 'c', 'padding': 2}}, 'removable'),
        ({'statusLine': {'type': 'command', 'command': 'claude-statusline', 'padding': 2}}, 'changed'),
        ({'statusLine': {'type': 'command', 'command': 'c'}}, 'changed'),
        ({'statusLine': {'type': 'command', 'command': 'c', 'padding': 2, 'refreshInterval': 9}}, 'changed'),
        ({}, 'gone'),
    ])
    def test_status_line_is_one_value(self, content: dict[str, Any], state: str) -> None:
        """A status line changed in any member, as /statusline changes it, reads as changed whole."""
        item = _item(_record('setting', ['statusLine'], {'type': 'command', 'command': 'c', 'padding': 2}))

        entry = setup_environment.settings_item_state(item, content, written=PlannedRecords())

        assert entry.state == state

    def test_a_member_the_configuration_dropped_without_a_null_keeps_the_status_line_changed(self) -> None:
        """The merge keeps a member an earlier run wrote, so the status line no longer equals what was written."""
        written = setup_environment.settings_write_records({'statusLine': {'type': 'command', 'command': 'c'}})
        merged = setup_environment.deep_merge_settings(
            {'statusLine': {'type': 'command', 'command': 'c', 'padding': 2}},
            {'statusLine': {'type': 'command', 'command': 'c'}},
        )

        entry = setup_environment.settings_item_state(_item(written[0]), merged, written=PlannedRecords())

        assert entry.state == 'changed'

    def test_group_present_whole_is_removable(self) -> None:
        group = {'matcher': '*', 'hooks': [_hook('a'), _hook('b')]}
        content = {'hooks': {'PreToolUse': [{'matcher': '', 'hooks': [_hook('user')]}, group]}}

        entry = setup_environment.settings_item_state(
            _item(_group_record('PreToolUse', group)), content, written=PlannedRecords(),
        )

        assert (entry.state, entry.shown) == ('removable', 'matcher "*" (2 hooks)')

    def test_group_changed_since_written_is_partial(self) -> None:
        group = {'matcher': '*', 'hooks': [_hook('a'), _hook('b')]}
        changed = {'matcher': '*', 'hooks': [_hook('a'), _hook('user')]}

        entry = setup_environment.settings_item_state(
            _item(_group_record('PreToolUse', group)), {'hooks': {'PreToolUse': [changed]}}, written=PlannedRecords(),
        )

        assert entry.state == 'partial'
        assert entry.shown == 'matcher "*" (1 hook inside a group changed since written)'

    def test_group_of_another_matcher_or_without_the_hooks_is_gone(self) -> None:
        group = {'matcher': '*', 'hooks': [_hook('a')]}
        item = _item(_group_record('PreToolUse', group))

        for content in (
            {'hooks': {'PreToolUse': [{'matcher': 'Bash', 'hooks': [_hook('a')]}]}},
            {'hooks': {'PreToolUse': [{'matcher': '*', 'hooks': [_hook('user')]}]}},
            {'hooks': {'Stop': [group]}},
        ):
            assert setup_environment.settings_item_state(item, content, written=PlannedRecords()).state == 'gone'

    def test_a_group_this_run_writes_is_never_matched_in_part(self) -> None:
        recorded = {'matcher': '*', 'hooks': [_hook('a'), _hook('c')]}
        written_now = {'matcher': '*', 'hooks': [_hook('b'), _hook('c')]}
        written = PlannedRecords(settings=(_item(_group_record('PreToolUse', written_now)),))

        entry = setup_environment.settings_item_state(
            _item(_group_record('PreToolUse', recorded)), {'hooks': {'PreToolUse': [written_now]}}, written=written,
        )

        assert entry.state == 'gone'

    @pytest.mark.parametrize('text', ['{not json', '["a list"]'])
    def test_unreadable_settings_file_cannot_be_checked(self, claude_dir: Path, text: str) -> None:
        (claude_dir / 'settings.json').write_text(text, encoding='utf-8')
        item = _item(_record('setting', ['theme'], 'dark'))

        entry = setup_environment._leftover_entry(item, claude_dir, _base_live(claude_dir))

        assert entry.state == 'unreadable'
        assert 'settings.json' in entry.detail


class TestRemoval:
    """One read, every removal applied, only the containers a removal emptied pruned, one write."""

    def test_only_containers_a_removal_emptied_are_pruned(self, claude_dir: Path) -> None:
        settings = _settings(claude_dir, {
            'env': {'FOO': 'x', 'BAR': 'y'}, 'sandbox': {}, 'permissions': {'allow': ['A']}, 'model': 'opus',
        })
        entries = [
            setup_environment.settings_item_state(_item(record), _read(settings), written=PlannedRecords())
            for record in (
                _record('setting', ['env', 'FOO'], 'x'),
                _record('setting-element', ['permissions', 'allow'], 'A'),
            )
        ]

        outcomes = setup_environment.remove_settings_leftovers(settings, entries, written=PlannedRecords())

        assert [outcome.result for outcome in outcomes] == ['removed', 'removed']
        assert _read(settings) == {'env': {'BAR': 'y'}, 'sandbox': {}, 'model': 'opus'}

    def test_inside_a_changed_group_only_the_recorded_hooks_leave(self, claude_dir: Path) -> None:
        recorded = {'matcher': '*', 'hooks': [_hook('a'), _hook('b')]}
        user_group = {'matcher': '', 'hooks': [_hook('user-stop')]}
        settings = _settings(claude_dir, {'hooks': {
            'PreToolUse': [{'matcher': '*', 'hooks': [_hook('a'), _hook('user')]}],
            'Stop': [user_group],
        }})
        item = _item(_group_record('PreToolUse', recorded))
        entry = setup_environment.settings_item_state(item, _read(settings), written=PlannedRecords())

        outcomes = setup_environment.remove_settings_leftovers(settings, [entry], written=PlannedRecords())

        assert [outcome.result for outcome in outcomes] == ['removed']
        assert _read(settings) == {'hooks': {
            'PreToolUse': [{'matcher': '*', 'hooks': [_hook('user')]}], 'Stop': [user_group],
        }}

    def test_a_group_removed_whole_leaves_the_groups_beside_it(self, claude_dir: Path) -> None:
        recorded = {'matcher': '*', 'hooks': [_hook('a')]}
        kept = {'matcher': '*', 'hooks': [_hook('b')]}
        settings = _settings(claude_dir, {'hooks': {'PreToolUse': [recorded, kept]}})
        entry = setup_environment.settings_item_state(
            _item(_group_record('PreToolUse', recorded)), _read(settings), written=PlannedRecords(),
        )

        setup_environment.remove_settings_leftovers(settings, [entry], written=PlannedRecords())

        assert _read(settings) == {'hooks': {'PreToolUse': [kept]}}

    def test_a_status_line_leaves_whole_and_one_changed_in_any_member_stays_whole(self, claude_dir: Path) -> None:
        written = {'type': 'command', 'command': 'c', 'padding': 2}
        item = _item(_record('setting', ['statusLine'], written))
        settings = _settings(claude_dir, {'statusLine': written, 'model': 'm'})

        removed = setup_environment.remove_settings_leftovers(
            settings, [setup_environment.settings_item_state(item, _read(settings), written=PlannedRecords())],
            written=PlannedRecords(),
        )

        assert [outcome.result for outcome in removed] == ['removed']
        assert _read(settings) == {'model': 'm'}
        rewritten = {'type': 'command', 'command': 'claude-statusline'}
        _settings(claude_dir, {'statusLine': rewritten})

        kept = setup_environment.remove_settings_leftovers(
            settings, [LeftoverEntry(item, 'removable')], written=PlannedRecords(),
        )

        assert [(outcome.result, outcome.detail) for outcome in kept] == [('dropped', 'changed')]
        assert _read(settings) == {'statusLine': rewritten}, 'no member of a changed status line leaves'

    def test_an_item_changed_before_the_removal_is_left_in_place(self, claude_dir: Path) -> None:
        settings = _settings(claude_dir, {'theme': 'dark'})
        entry = setup_environment.settings_item_state(
            _item(_record('setting', ['theme'], 'dark')), _read(settings), written=PlannedRecords(),
        )
        _settings(claude_dir, {'theme': 'light'})

        outcomes = setup_environment.remove_settings_leftovers(settings, [entry], written=PlannedRecords())

        assert [(outcome.result, outcome.detail) for outcome in outcomes] == [('dropped', 'changed')]
        assert _read(settings) == {'theme': 'light'}

    def test_a_failed_write_fails_every_removal_and_leaves_the_file(self, claude_dir: Path) -> None:
        settings = _settings(claude_dir, {'theme': 'dark', 'model': 'm'})
        entry = setup_environment.settings_item_state(
            _item(_record('setting', ['theme'], 'dark')), _read(settings), written=PlannedRecords(),
        )

        with patch.object(setup_environment, '_write_file_atomic', side_effect=PermissionError(13, 'Access is denied')):
            outcomes = setup_environment.remove_settings_leftovers(settings, [entry], written=PlannedRecords())

        assert [(outcome.result, outcome.detail) for outcome in outcomes] == [('failed', 'Access is denied')]
        assert _read(settings) == {'theme': 'dark', 'model': 'm'}

    @pytest.mark.parametrize('spelling', ['absolute', 'relative', 'chain'])
    def test_a_symlinked_settings_file_keeps_its_link_and_its_target_loses_the_leftover(
        self, claude_dir: Path, spelling: str,
    ) -> None:
        """The write lands in the file the link resolves to, so a settings.json kept elsewhere stays linked."""
        dotfiles = claude_dir.parent / 'dotfiles'
        dotfiles.mkdir()
        target = dotfiles / 'claude-settings.json'
        target.write_text(json.dumps({'theme': 'dark', 'model': 'm'}), encoding='utf-8')
        settings = claude_dir / 'settings.json'
        if spelling == 'absolute':
            symlink_file(settings, target)
        elif spelling == 'relative':
            symlink_file(settings, Path('..') / 'dotfiles' / 'claude-settings.json')
        else:
            hop = dotfiles / 'settings-link.json'
            symlink_file(hop, target)
            symlink_file(settings, hop)
        entry = setup_environment.settings_item_state(
            _item(_record('setting', ['theme'], 'dark')), _read(settings), written=PlannedRecords(),
        )

        outcomes = setup_environment.remove_settings_leftovers(settings, [entry], written=PlannedRecords())

        assert [outcome.result for outcome in outcomes] == ['removed']
        assert settings.is_symlink(), 'the link itself is not replaced by a regular file'
        assert os.path.samefile(settings, target)
        assert _read(target) == {'model': 'm'}, 'the file the link resolves to loses the leftover'
        if spelling == 'chain':
            assert (dotfiles / 'settings-link.json').is_symlink(), 'every link of the chain stays'
        assert sorted(path.name for path in claude_dir.iterdir()) == ['settings.json'], 'no temporary file is left'
        assert sorted(path.name for path in dotfiles.iterdir()) == sorted(
            ['claude-settings.json', *(['settings-link.json'] if spelling == 'chain' else [])],
        ), 'no temporary file is left beside the target'

    def test_an_unreadable_file_keeps_every_item(self, claude_dir: Path) -> None:
        settings = claude_dir / 'settings.json'
        settings.write_text('{broken', encoding='utf-8')
        entry = LeftoverEntry(_item(_record('setting', ['theme'], 'dark')), 'removable')

        outcomes = setup_environment.remove_settings_leftovers(settings, [entry], written=PlannedRecords())

        assert [(outcome.result, outcome.entry.state) for outcome in outcomes] == [('kept', 'unreadable')]
        assert settings.read_text(encoding='utf-8') == '{broken'


# What an earlier run wrote through Step 14 (user-settings), as settings.json holds it, with its records by item.
_STEP_14_CONTENT: dict[str, Any] = {
    'env': {'FOO': 'x', 'FOO_BAR': 'y'},
    'availableModels': ['opus', 'sonnet'],
    'permissions': {'ask': ['Bash(git push)']},
}
_STEP_14_RECORDS: dict[str, list[dict[str, Any]]] = {
    'env.FOO': [_record('setting', ['env', 'FOO'], 'x')],
    'env.FOO_BAR': [_record('setting', ['env', 'FOO_BAR'], 'y')],
    'availableModels': [
        _record('setting-element', ['availableModels'], 'opus'),
        _record('setting-element', ['availableModels'], 'sonnet'),
    ],
    'permissions.ask': [_record('setting-element', ['permissions', 'ask'], 'Bash(git push)')],
}

# What an earlier run wrote through Step 18 (status-line and hooks), as settings.json holds it, with its records.
_STATUS_COMMAND = 'uv run --no-project --python 3.12 "/home/u/.claude/hooks/s.py"'
_STOP_GROUP: dict[str, Any] = {'matcher': '', 'hooks': [_hook('echo stop')]}
_STEP_18_CONTENT: dict[str, Any] = {
    'statusLine': {'type': 'command', 'command': _STATUS_COMMAND, 'padding': 2, 'refreshInterval': 30},
    'hooks': {'Stop': [_STOP_GROUP]},
}
_STEP_18_RECORDS: dict[str, list[dict[str, Any]]] = {
    'statusLine': [_record('setting', ['statusLine'], _STEP_18_CONTENT['statusLine'])],
    'hooks.Stop': [_group_record('Stop', _STOP_GROUP)],
}


def _manifest_with(records: list[dict[str, Any]], *, leftovers: bool = True) -> dict[str, Any]:
    manifest: dict[str, Any] = {'settings_written': records}
    if leftovers:
        manifest['leftovers'] = {'items': []}
    return manifest


def _compute(
    manifest: dict[str, Any],
    claude_dir: Path,
    *,
    planned: PlannedRecords | None = None,
) -> LeftoverReport:
    return setup_environment.compute_profile_leftovers(
        manifest, claude_dir,
        profile_name='base',
        planned=planned or PlannedRecords(),
        live=_base_live(claude_dir),
        claude_dir=claude_dir,
    )


def _states(report: LeftoverReport) -> dict[str, str]:
    return {entry.item.label(): entry.state for entry in report.entries}


class TestComputation:
    """A re-run lists the recorded settings items its configuration no longer writes."""

    def test_machine_wide_controls_recorded_by_hand_are_never_leftovers(self, claude_dir: Path) -> None:
        _settings(claude_dir, {'env': {'DISABLE_UPDATES': '1', 'FOO': 'x'}})
        records = [_record('setting', ['env', 'DISABLE_UPDATES'], '1'), _record('setting', ['env', 'FOO'], 'x')]

        report = _compute(_manifest_with(records), claude_dir)

        assert _states(report) == {'settings.json: env.FOO': 'removable'}

    def test_a_value_the_configuration_writes_again_is_no_leftover_whatever_it_holds(self, claude_dir: Path) -> None:
        _settings(claude_dir, {'theme': 'dark', 'permissions': {'allow': ['A', 'B']}})
        manifest = _manifest_with([
            _record('setting', ['theme'], 'dark'),
            _record('setting-element', ['permissions', 'allow'], 'A'),
            _record('setting-element', ['permissions', 'allow'], 'B'),
        ])
        planned = PlannedRecords(settings=(
            _item(_record('setting', ['theme'], 'light')),
            _item(_record('setting-element', ['permissions', 'allow'], 'A')),
        ))

        report = _compute(manifest, claude_dir, planned=planned)

        element = f'settings.json: permissions.allow element {digest("B")[:12]}'
        assert _states(report) == {element: 'removable'}

    @pytest.mark.parametrize(
        ('user_settings', 'listed'),
        [
            ({'env': {'FOO': None}}, ['env.FOO_BAR', 'availableModels', 'permissions.ask']),
            ({'env': None}, ['availableModels', 'permissions.ask']),
            ({'availableModels': None}, ['env.FOO', 'env.FOO_BAR', 'permissions.ask']),
            ({'permissions': {'ask': None}}, ['env.FOO', 'env.FOO_BAR', 'availableModels']),
        ],
    )
    def test_an_item_the_configuration_deletes_is_no_leftover(
        self, claude_dir: Path, user_settings: dict[str, Any], listed: list[str],
    ) -> None:
        """Step 14 deletes what a null names, so no value, element or list at or below it is left behind."""
        self._assert_listed_and_carried(claude_dir, {'user-settings': user_settings}, listed)

    @pytest.mark.parametrize(
        ('user_settings', 'listed'),
        [
            ({'env': None}, ['env.FOO', 'env.FOO_BAR', 'availableModels', 'permissions.ask']),
            ({'env': {'FOO': None}}, ['env.FOO_BAR', 'availableModels', 'permissions.ask']),
        ],
    )
    def test_a_pin_turns_a_null_env_into_the_update_controls_which_delete_no_variable(
        self, claude_dir: Path, user_settings: dict[str, Any], listed: list[str],
    ) -> None:
        """A pinned run writes the update controls into env, in place of a null env, and keeps a null member."""
        self._assert_listed_and_carried(
            claude_dir, {'claude-code-version': '2.1.280', 'user-settings': user_settings}, listed,
        )

    @pytest.mark.parametrize('pin', ['latest', ' ', None])
    def test_a_run_installing_the_latest_release_deletes_a_null_env(self, claude_dir: Path, pin: str | None) -> None:
        self._assert_listed_and_carried(
            claude_dir, {'claude-code-version': pin, 'user-settings': {'env': None}}, ['availableModels', 'permissions.ask'],
        )

    @pytest.mark.parametrize(
        ('value', 'pinned'),
        [('2.1.280', '2.1.280'), (' 2.1.280 ', '2.1.280'), (1.0, '1.0'), ('LATEST', None), ('', None), (None, None)],
    )
    def test_the_pin_is_read_as_the_run_reads_it(self, value: object, pinned: str | None) -> None:
        assert setup_environment.normalized_claude_code_version(value) == pinned

    @pytest.mark.parametrize(
        ('config', 'listed'),
        [
            ({}, ['statusLine', 'hooks.Stop']),
            ({'status-line': None}, ['hooks.Stop']),
            ({'hooks': None}, ['statusLine']),
            ({'status-line': None, 'hooks': None}, []),
            ({'hooks': {'files': ['hooks/s.py']}, 'status-line': {'file': 's.py', 'padding': None}}, ['hooks.Stop']),
        ],
    )
    def test_a_status_line_or_hooks_member_the_configuration_deletes_is_no_leftover(
        self, claude_dir: Path, config: dict[str, Any], listed: list[str],
    ) -> None:
        """Step 18 deletes what a null in status-line or hooks names, so nothing at or below it is left behind."""
        self._assert_listed_and_carried(claude_dir, config, listed, content=_STEP_18_CONTENT, records=_STEP_18_RECORDS)

    @staticmethod
    def _assert_listed_and_carried(
        claude_dir: Path,
        config: dict[str, Any],
        listed: list[str],
        *,
        content: dict[str, Any] = _STEP_14_CONTENT,
        records: dict[str, list[dict[str, Any]]] = _STEP_14_RECORDS,
    ) -> None:
        _settings(claude_dir, content)
        planned = setup_environment.planned_records(config, claude_dir, claude_dir=claude_dir, base=True)

        report = _compute(_manifest_with([record for group in records.values() for record in group]), claude_dir,
                          planned=planned)

        expected = sorted(_item(record).label() for path in listed for record in records[path])
        assert sorted(_states(report)) == expected
        assert set(_states(report).values()) == ({'removable'} if listed else set())
        carried = setup_environment.leftovers_manifest_record(report, run_at='2026-11-25T00:00:00Z')['items']
        assert sorted(_item(record).label() for record in carried) == expected

    def test_rows_name_the_settings_file_and_what_sits_there(self, claude_dir: Path) -> None:
        group = {'matcher': '*', 'hooks': [_hook('x')]}
        settings = _settings(claude_dir, {'theme': 'dark', 'permissions': {'allow': ['B']}, 'hooks': {'Stop': [group]}})
        manifest = _manifest_with([
            _record('setting', ['theme'], 'dark'),
            _record('setting-element', ['permissions', 'allow'], 'B'),
            _group_record('Stop', group),
        ])

        lines = _compute(manifest, claude_dir).lines()

        assert lines == [
            f'[leftover] {settings}: hooks.Stop group matcher "*" (1 hook)',
            f'[leftover] {settings}: permissions.allow element "B"',
            f'[leftover] {settings}: theme',
            'They stay in place.',
            setup_environment.LEFTOVERS_FLAG_FOOTER,
        ]
        assert 'dark' not in '\n'.join(lines), 'a value is never printed'

    def test_selected_configuration_refines_away_a_group_it_writes(self, claude_dir: Path) -> None:
        """A remembered --without that splits a matcher group writes a group the full build never holds."""
        config: dict[str, Any] = {
            'hooks': {'files': ['hooks/a.py', 'hooks/b.py'], 'events': [
                {'event': 'PreToolUse', 'matcher': '*', 'type': 'command', 'command': 'a.py', 'id': 'ea'},
                {'event': 'PreToolUse', 'matcher': '*', 'type': 'command', 'command': 'b.py', 'id': 'eb'},
            ]},
        }
        selected = {'hooks': {'files': ['hooks/a.py'], 'events': [config['hooks']['events'][0]]}}
        written = setup_environment.planned_settings_records(selected, claude_dir)
        settings_content = {'hooks': {'PreToolUse': [
            setup_environment._build_hooks_json(selected['hooks'], claude_dir / 'hooks')['PreToolUse'][0],
        ]}}
        _settings(claude_dir, settings_content)
        planned = setup_environment.planned_records(config, claude_dir, claude_dir=claude_dir, base=True)

        report = _compute(_manifest_with(written), claude_dir, planned=planned)

        assert [entry.item.kind for entry in report.entries] == ['hook-group'], 'the full build differs'
        selected_planned = setup_environment.planned_records(selected, claude_dir, claude_dir=claude_dir, base=True)
        refined = report.refined(linked_entries=frozenset(), link_source='base', selected=selected_planned)
        assert refined.entries == ()

    def test_isolated_profile_plans_no_settings(self, tmp_path: Path) -> None:
        planned = setup_environment.planned_records(
            {'user-settings': {'theme': 'dark'}}, tmp_path / '.claude' / 'p', claude_dir=tmp_path / '.claude',
        )
        assert planned.settings == ()


def _step(
    report: LeftoverReport,
    claude_dir: Path,
    *,
    written: PlannedRecords | None = None,
    remove: bool = True,
) -> dict[str, tuple[str, str]]:
    removal = setup_environment.run_leftovers_step(
        report,
        remove=remove,
        download_failed=False,
        written=written or PlannedRecords(),
        live=_base_live(claude_dir, before_consent=False),
        profile_dir=claude_dir,
        claude_dir=claude_dir,
        manifest_path=claude_dir / 'manifest.json',
        run_at='t',
    )
    assert removal is not None
    return {outcome.entry.item.label(): (outcome.result, outcome.detail) for outcome in removal.outcomes}


class TestStep23:
    """Step 23 removes settings items first, so a hook file and the group wiring it leave together."""

    def _wired(self, claude_dir: Path) -> tuple[LeftoverReport, dict[str, Any]]:
        script = claude_dir / 'hooks' / 'a.py'
        script.parent.mkdir()
        script.write_bytes(b'print(1)\n')
        command = f'uv run --no-project --python 3.12 "{script.as_posix()}"'
        group = {'matcher': '', 'hooks': [_hook(command)]}
        _settings(claude_dir, {'hooks': {'Stop': [group]}, 'model': 'opus'})
        manifest = _manifest_with(setup_environment.settings_write_records({'hooks': {'Stop': [group]}}))
        manifest['files_written'] = [{'path': 'hooks/a.py', 'sha256': setup_environment._sha256_of_file(script)}]
        return _compute(manifest, claude_dir), group

    def test_the_group_and_its_hook_file_leave_in_the_same_step(self, claude_dir: Path) -> None:
        report, group = self._wired(claude_dir)

        outcomes = _step(report, claude_dir)

        assert outcomes == {
            'file: hooks/a.py': ('removed', ''),
            f'settings.json: hooks.Stop group {digest(group)[:12]}': ('removed', ''),
        }
        assert not (claude_dir / 'hooks' / 'a.py').exists()
        assert _read(claude_dir / 'settings.json') == {'model': 'opus'}

    def test_a_failed_settings_write_keeps_the_hook_file(self, claude_dir: Path) -> None:
        report, group = self._wired(claude_dir)

        with patch.object(setup_environment, '_write_file_atomic', side_effect=PermissionError(13, 'Access is denied')):
            outcomes = _step(report, claude_dir)

        assert outcomes[f'settings.json: hooks.Stop group {digest(group)[:12]}'] == ('failed', 'Access is denied')
        assert outcomes['file: hooks/a.py'][0] == 'kept'
        assert (claude_dir / 'hooks' / 'a.py').is_file()

    def test_without_the_flag_nothing_leaves(self, claude_dir: Path) -> None:
        report, _group = self._wired(claude_dir)

        assert setup_environment.run_leftovers_step(
            report, remove=False, download_failed=False, written=PlannedRecords(),
            live=_base_live(claude_dir, before_consent=False), profile_dir=claude_dir, claude_dir=claude_dir,
            manifest_path=claude_dir / 'manifest.json', run_at='t',
        ) is None
        assert (claude_dir / 'hooks' / 'a.py').is_file()

    def test_an_item_this_run_wrote_again_is_dropped(self, claude_dir: Path) -> None:
        _settings(claude_dir, {'theme': 'dark'})
        item = _item(_record('setting', ['theme'], 'dark'))
        report = LeftoverReport('base', claude_dir, (LeftoverEntry(item, 'removable'),), untracked_note=False)

        outcomes = _step(report, claude_dir, written=PlannedRecords(settings=(item,)))

        assert outcomes == {'settings.json: theme': ('dropped', 'written again')}
        assert _read(claude_dir / 'settings.json') == {'theme': 'dark'}

    def test_a_changed_group_loses_only_the_recorded_hooks_and_the_group_written_now_stays(
        self, claude_dir: Path,
    ) -> None:
        recorded = {'matcher': '*', 'hooks': [_hook('a'), _hook('c')]}
        written_now = {'matcher': '*', 'hooks': [_hook('b'), _hook('c')]}
        changed = {'matcher': '*', 'hooks': [_hook('a'), _hook('c'), _hook('user')]}
        _settings(claude_dir, {'hooks': {'PreToolUse': [changed, written_now]}})
        item = _item(_group_record('PreToolUse', recorded))
        report = LeftoverReport('base', claude_dir, (LeftoverEntry(item, 'removable'),), untracked_note=False)
        written = PlannedRecords(settings=(_item(_group_record('PreToolUse', written_now)),))

        outcomes = _step(report, claude_dir, written=written)

        assert list(outcomes.values()) == [('removed', '')]
        assert _read(claude_dir / 'settings.json') == {'hooks': {'PreToolUse': [
            {'matcher': '*', 'hooks': [_hook('user')]}, written_now,
        ]}}


class TestItemRecords:
    """Settings items round-trip through the leftovers field and refuse every other shape."""

    @pytest.mark.parametrize('record', [
        _record('setting', ['env', 'FOO'], 'x'),
        _record('setting-element', ['permissions', 'allow'], 'A'),
        _group_record('Stop', {'matcher': '', 'hooks': [_hook('a')]}),
    ])
    def test_round_trip(self, record: dict[str, Any]) -> None:
        assert _item(record).to_record() == record

    @pytest.mark.parametrize('record', [
        {'kind': 'setting', 'path': 'theme', 'sha256': 'h'},
        {'kind': 'setting', 'path': [], 'sha256': 'h'},
        {'kind': 'setting', 'path': ['a', 1], 'sha256': 'h'},
        {'kind': 'setting-element', 'path': ['a']},
        {'kind': 'hook-group', 'path': ['hooks'], 'sha256': 'h', 'matcher': 'm', 'entries': []},
        {'kind': 'hook-group', 'path': ['env', 'Stop'], 'sha256': 'h', 'matcher': 'm', 'entries': []},
        {'kind': 'hook-group', 'path': ['hooks', 'Stop'], 'sha256': 'h', 'matcher': 'm', 'entries': [1]},
        {'kind': 'hook-group', 'path': ['hooks', 'Stop'], 'sha256': 'h', 'entries': []},
    ])
    def test_other_shapes_are_refused(self, record: dict[str, Any]) -> None:
        assert LeftoverItem.from_record(record, claude_dir=Path('/c')) is None

    def test_labels_name_identities_only(self) -> None:
        group = {'matcher': '', 'hooks': [_hook('a')]}
        assert _item(_record('setting', ['env', 'FOO'], 'x')).label() == 'settings.json: env.FOO'
        assert _item(_record('setting-element', ['permissions', 'allow'], 'A')).label() == (
            f'settings.json: permissions.allow element {digest("A")[:12]}'
        )
        assert _item(_group_record('Stop', group)).label() == f'settings.json: hooks.Stop group {digest(group)[:12]}'

    def test_a_settings_item_has_no_file_location(self) -> None:
        with pytest.raises(ValueError, match='settings'):
            _item(_record('setting', ['theme'], 'dark')).location(Path('/c'))

    def test_manifest_carries_settings_items(self, claude_dir: Path) -> None:
        _settings(claude_dir, {'theme': 'dark'})
        report = _compute(_manifest_with([_record('setting', ['theme'], 'dark')]), claude_dir)

        record = setup_environment.leftovers_manifest_record(report, run_at='t')

        assert record['items'] == [_record('setting', ['theme'], 'dark')]


class TestWrittenRecords:
    """Step 23 reads back the settings items Step 20 recorded as written."""

    def test_written_settings_records_are_read_back_for_step_23(self) -> None:
        record = _record('setting', ['theme'], 'dark')
        written = setup_environment.written_leftover_records(
            {'files_written': [], 'machine_wide_destinations': [], 'settings_written': [record]},
        )
        assert written.writes(_item(record))
        assert not written.writes(_item(_record('setting', ['model'], 'opus')))


class TestReadSettings:
    """The live settings reader tells an absent file from one that cannot be read."""

    def test_reader(self, claude_dir: Path) -> None:
        read = setup_environment._read_settings_object
        assert read(claude_dir / 'settings.json') is None
        _settings(claude_dir, {'a': 1})
        assert read(claude_dir / 'settings.json') == {'a': 1}
        (claude_dir / 'settings.json').write_text('[1]', encoding='utf-8')
        with pytest.raises(LeftoverReadError, match='not a JSON object'):
            read(claude_dir / 'settings.json')
