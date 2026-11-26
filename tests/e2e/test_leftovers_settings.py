"""E2E tests for the leftovers of the base profile's settings.json.

The tests install real local YAML files as the base profile of an isolated
home through main(), edit settings.json by hand the way Claude Code and the
user do, change the configuration in place (its identity stays the same, as
an update of a remote configuration does) and re-run the profile: the
summary lists each value, list element and hook group the configuration no
longer writes, and a run given --remove-leftovers removes in Step 23 each
one still holding what the setup wrote, a renamed hook file together with
the hook group that wires it, while everything Claude Code, the user or the
version pin wrote stays.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from scripts import setup_environment
from tests.e2e.leftovers_support import HEADING
from tests.e2e.leftovers_support import REMOVES
from tests.e2e.leftovers_support import REMOVES_OTHERS_STAY
from tests.e2e.leftovers_support import SKIP
from tests.e2e.leftovers_support import leftover_rows
from tests.e2e.leftovers_support import printed
from tests.e2e.leftovers_support import symlink_file
from tests.e2e.profile_support import home_state
from tests.e2e.profile_support import read_manifest
from tests.e2e.profile_support import run_main
from tests.e2e.profile_support import write_config
from tests.e2e.validators import validate_manifest

PIN = '2.1.280'
USER_GROUP = {'matcher': '', 'hooks': [{'type': 'command', 'command': 'echo user-stop'}]}


@pytest.fixture
def configs(tmp_path: Path) -> Path:
    """A directory of configurations with the resources they install beside them."""
    directory = tmp_path / 'configs'
    for relative, content in (
        ('rules/rule.md', '# rule\n'),
        ('hooks/a.py', 'import h\n'),
        ('hooks/b.py', 'print("b")\n'),
        ('hooks/h.py', 'VALUE = 1\n'),
    ):
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    return directory


def _hooked(script: str, *, helpers: list[str], allow: list[str], event: str = 'PreToolUse') -> dict[str, Any]:
    """A pinned base configuration whose one hook runs a hooks.files script through uv."""
    return {
        'name': 'Base Settings Env',
        'claude-code-version': PIN,
        'rules': ['rules/rule.md'],
        'user-settings': {'permissions': {'allow': allow}},
        'hooks': {
            'files': [f'hooks/{script}'],
            'helpers': [f'hooks/{name}' for name in helpers],
            'events': [{'event': event, 'matcher': '*', 'type': 'command', 'command': script}],
        },
    }


def _settings(claude_dir: Path) -> dict[str, Any]:
    content: dict[str, Any] = json.loads((claude_dir / 'settings.json').read_text(encoding='utf-8'))
    return content


def _write_settings(claude_dir: Path, content: dict[str, Any]) -> None:
    (claude_dir / 'settings.json').write_text(json.dumps(content, indent=2), encoding='utf-8')


def _commands(groups: list[dict[str, Any]]) -> list[str]:
    return [str(hook.get('command')) for group in groups for hook in group['hooks']]


def _hook_command(claude_dir: Path, script: str) -> str:
    return f'uv run --no-project --python 3.12 "{(claude_dir / "hooks" / script).as_posix()}"'


@pytest.mark.usefixtures('e2e_isolated_home')
class TestBaseSettingsLeftovers:
    """The base settings.json loses only what the setup wrote and the configuration no longer writes."""

    def test_renamed_hook_leaves_with_its_group_and_everything_else_stays(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        claude_dir = e2e_isolated_home['claude_dir']
        settings_path = claude_dir / 'settings.json'
        cfg = write_config(configs, 'base.yaml', _hooked('a.py', helpers=['h.py'], allow=['Read', 'Bash(ls)']))
        assert run_main([str(cfg), *SKIP, '--yes']) == 0
        manifest = read_manifest(claude_dir)
        assert not any(record['path'][0] == 'env' for record in manifest['settings_written']), (
            'the machine-wide update controls the pin writes are never recorded'
        )
        installed = _settings(claude_dir)
        assert installed['env']['DISABLE_UPDATES'] == '1'
        installed['model'] = 'opus'
        installed['permissions']['allow'].append('Edit')
        installed['hooks']['Stop'] = [USER_GROUP]
        _write_settings(claude_dir, installed)
        write_config(configs, 'base.yaml', _hooked('b.py', helpers=[], allow=['Read']))
        capsys.readouterr()

        before = home_state(e2e_isolated_home['home'])
        assert run_main(['--profile', 'base', *SKIP, '--remove-leftovers', '--dry-run']) == 0
        dry = printed(capsys)
        assert home_state(e2e_isolated_home['home']) == before, 'a dry run removes nothing'
        marker = '[would be removed in Step 23]'
        held = f'  [kept: stays with hooks/b.py, which is still wired] file: {claude_dir / "hooks" / "h.py"}'
        assert leftover_rows(dry) == [
            f'  {marker} file: {claude_dir / "hooks" / "a.py"}',
            held,
            f'  {marker} {settings_path}: hooks.PreToolUse group matcher "*" (1 hook)',
            f'  {marker} {settings_path}: permissions.allow element "Bash(ls)"',
            f'  {REMOVES_OTHERS_STAY.replace("[remove]", marker)}',
        ]

        assert run_main(['--profile', 'base', *SKIP, '--remove-leftovers', '--yes']) == 0

        output = printed(capsys)
        assert leftover_rows(output) == [
            f'  [remove] file: {claude_dir / "hooks" / "a.py"}',
            held,
            f'  [remove] {settings_path}: hooks.PreToolUse group matcher "*" (1 hook)',
            f'  [remove] {settings_path}: permissions.allow element "Bash(ls)"',
            f'  {REMOVES_OTHERS_STAY}',
        ]
        group_removed = output.index(f'Removed leftover {settings_path}: hooks.PreToolUse group')
        assert output.index('Step 23: Removing leftovers...') < group_removed
        assert group_removed < output.index(f'Removed leftover file: {claude_dir / "hooks" / "a.py"}'), (
            'the hook group leaves before the hook file it wires'
        )
        assert not (claude_dir / 'hooks' / 'a.py').exists()
        assert (claude_dir / 'hooks' / 'h.py').is_file(), 'the wired b.py may import the dropped helper'
        assert (claude_dir / 'hooks' / 'b.py').is_file()
        final = _settings(claude_dir)
        assert _commands(final['hooks']['PreToolUse']) == [_hook_command(claude_dir, 'b.py')]
        assert final['hooks']['Stop'] == [USER_GROUP], 'a group the user wrote stays'
        assert final['model'] == 'opus', 'a key written after the install stays'
        assert final['env']['DISABLE_UPDATES'] == '1', 'the machine-wide update controls stay'
        assert final['permissions']['allow'] == ['Read', 'Edit'], 'only the dropped element leaves'
        leftovers = read_manifest(claude_dir)['leftovers']
        assert [item['path'] for item in leftovers['items']] == ['hooks/h.py']
        assert [label.split(' group ')[0] for label in leftovers['removed']] == [
            'settings.json: hooks.PreToolUse',
            f'settings.json: permissions.allow element {setup_environment.leftover_digest("Bash(ls)")[:12]}',
            'file: hooks/a.py',
        ]
        assert not validate_manifest(claude_dir / 'manifest.json', _hooked('b.py', helpers=[], allow=['Read']))

        assert run_main(['--profile', 'base', *SKIP, '--yes']) == 0

        assert leftover_rows(printed(capsys)) == [held, '  They stay in place.'], 'only the held helper is left'

    def test_a_settings_file_linked_from_elsewhere_stays_linked_and_its_target_loses_the_leftovers(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A settings.json kept in a dotfiles folder and linked into ~/.claude is edited where it lives."""
        home = e2e_isolated_home['home']
        claude_dir = e2e_isolated_home['claude_dir']
        settings_path = claude_dir / 'settings.json'
        target = home / 'dotfiles' / 'claude-settings.json'
        target.parent.mkdir()
        target.write_text(json.dumps({'model': 'opus'}, indent=2), encoding='utf-8')
        symlink_file(settings_path, target)
        cfg = write_config(configs, 'base.yaml', {
            'name': 'Linked Settings', 'user-settings': {'theme': 'dark', 'permissions': {'allow': ['Read', 'Bash(ls)']}},
        })
        assert run_main([str(cfg), *SKIP, '--yes']) == 0
        assert settings_path.is_symlink(), 'the install writes through the link'
        assert _settings(claude_dir) == {
            'model': 'opus', 'theme': 'dark', 'permissions': {'allow': ['Read', 'Bash(ls)']},
        }
        write_config(configs, 'base.yaml', {'name': 'Linked Settings', 'user-settings': {'permissions': {'allow': ['Read']}}})
        capsys.readouterr()

        assert run_main(['--profile', 'base', *SKIP, '--remove-leftovers', '--yes']) == 0

        output = printed(capsys)
        assert leftover_rows(output) == [
            f'  [remove] {settings_path}: permissions.allow element "Bash(ls)"',
            f'  [remove] {settings_path}: theme',
            f'  {REMOVES}',
        ]
        assert f'Removed leftover {settings_path}: theme' in output, 'the run names the settings file as linked'
        assert settings_path.is_symlink(), 'the removal keeps the link'
        assert os.path.samefile(settings_path, target)
        assert json.loads(target.read_text(encoding='utf-8')) == {'model': 'opus', 'permissions': {'allow': ['Read']}}
        assert sorted(path.name for path in target.parent.iterdir()) == ['claude-settings.json'], (
            'no temporary file is left beside the target'
        )
        assert read_manifest(claude_dir)['leftovers']['items'] == []

    def test_dropping_every_hook_removes_the_scripts_the_group_and_the_helper_in_one_run(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Step 23 removes the hook group first, so no file of the folder stays wired and the helper leaves too."""
        claude_dir = e2e_isolated_home['claude_dir']
        settings_path = claude_dir / 'settings.json'
        cfg = write_config(configs, 'base.yaml', _hooked('a.py', helpers=['h.py'], allow=['Read']))
        assert run_main([str(cfg), *SKIP, '--yes']) == 0
        unhooked = _hooked('a.py', helpers=[], allow=['Read'])
        del unhooked['hooks']
        write_config(configs, 'base.yaml', unhooked)
        capsys.readouterr()

        assert run_main(['--profile', 'base', *SKIP, '--yes']) == 0

        assert leftover_rows(printed(capsys))[:3] == [
            f'  [kept: still wired in {settings_path} hooks.PreToolUse] file: {claude_dir / "hooks" / "a.py"}',
            f'  [kept: stays with hooks/a.py, which is still wired] file: {claude_dir / "hooks" / "h.py"}',
            f'  [leftover] {settings_path}: hooks.PreToolUse group matcher "*" (1 hook)',
        ], 'without the flag the group stays and keeps both files'

        before = home_state(e2e_isolated_home['home'])
        assert run_main(['--profile', 'base', *SKIP, '--remove-leftovers', '--dry-run']) == 0
        marker = '[would be removed in Step 23]'
        assert leftover_rows(printed(capsys)) == [
            f'  {marker} file: {claude_dir / "hooks" / "a.py"}',
            f'  {marker} file: {claude_dir / "hooks" / "h.py"}',
            f'  {marker} {settings_path}: hooks.PreToolUse group matcher "*" (1 hook)',
            f'  {REMOVES.replace("[remove]", marker)}',
        ]
        assert home_state(e2e_isolated_home['home']) == before, 'a dry run removes nothing'

        assert run_main(['--profile', 'base', *SKIP, '--yes', '--remove-leftovers']) == 0

        assert leftover_rows(printed(capsys)) == [
            f'  [remove] file: {claude_dir / "hooks" / "a.py"}',
            f'  [remove] file: {claude_dir / "hooks" / "h.py"}',
            f'  [remove] {settings_path}: hooks.PreToolUse group matcher "*" (1 hook)',
            f'  {REMOVES}',
        ]
        assert not (claude_dir / 'hooks' / 'a.py').exists()
        assert not (claude_dir / 'hooks' / 'h.py').exists()
        assert 'PreToolUse' not in _settings(claude_dir).get('hooks', {})

    def test_inside_a_changed_group_only_the_hooks_the_setup_wrote_leave(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        claude_dir = e2e_isolated_home['claude_dir']
        settings_path = claude_dir / 'settings.json'
        cfg = write_config(configs, 'base.yaml', _hooked('a.py', helpers=[], allow=['Read']))
        assert run_main([str(cfg), *SKIP, '--yes']) == 0
        installed = _settings(claude_dir)
        installed['hooks']['PreToolUse'][0]['hooks'].append({'type': 'command', 'command': 'echo mine'})
        _write_settings(claude_dir, installed)
        write_config(configs, 'base.yaml', _hooked('b.py', helpers=[], allow=['Read'], event='Stop'))
        capsys.readouterr()

        assert run_main(['--profile', 'base', *SKIP, '--yes']) == 0

        group_row = f'{settings_path}: hooks.PreToolUse group matcher "*" (1 hook inside a group changed since written)'
        assert leftover_rows(printed(capsys))[:2] == [
            f'  [kept: still wired in {settings_path} hooks.PreToolUse] file: {claude_dir / "hooks" / "a.py"}',
            f'  [leftover] {group_row}',
        ]

        assert run_main(['--profile', 'base', *SKIP, '--yes', '--remove-leftovers']) == 0

        assert leftover_rows(printed(capsys))[:2] == [
            f'  [remove] file: {claude_dir / "hooks" / "a.py"}',
            f'  [remove] {group_row}',
        ]
        final = _settings(claude_dir)
        assert final['hooks']['PreToolUse'] == [
            {'matcher': '*', 'hooks': [{'type': 'command', 'command': 'echo mine'}]},
        ], 'the hook the user added keeps the group'
        assert _commands(final['hooks']['Stop']) == [_hook_command(claude_dir, 'b.py')]
        assert not (claude_dir / 'hooks' / 'a.py').exists()

    def test_a_value_or_list_the_configuration_now_deletes_is_neither_listed_nor_carried(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A null in user-settings makes Step 14 delete the item, so no run reports it as left in place."""
        claude_dir = e2e_isolated_home['claude_dir']
        settings_path = claude_dir / 'settings.json'
        cfg = write_config(configs, 'base.yaml', {
            'name': 'Null Settings',
            'user-settings': {
                'theme': 'dark',
                'env': {'FOO': 'x'},
                'availableModels': ['opus', 'sonnet'],
                'permissions': {'allow': ['Read'], 'ask': ['Bash(git push)']},
            },
        })
        assert run_main([str(cfg), *SKIP, '--yes']) == 0
        recorded = [record['path'] for record in read_manifest(claude_dir)['settings_written']]
        assert ['env', 'FOO'] in recorded
        assert ['availableModels'] in recorded
        assert ['permissions', 'ask'] in recorded
        write_config(configs, 'base.yaml', {
            'name': 'Null Settings',
            'user-settings': {
                'env': {'FOO': None},
                'availableModels': None,
                'permissions': {'allow': ['Read'], 'ask': None},
            },
        })
        capsys.readouterr()
        rows = [
            f'  [leftover] {settings_path}: theme',
            '  They stay in place.',
            f'  {setup_environment.LEFTOVERS_FLAG_FOOTER}',
        ]
        deleted = [f'{settings_path}: env.FOO', f'{settings_path}: availableModels', f'{settings_path}: permissions.ask']

        assert run_main(['--profile', 'base', *SKIP, '--dry-run']) == 0
        assert leftover_rows(printed(capsys)) == rows

        assert run_main(['--profile', 'base', *SKIP, '--yes']) == 0

        output = printed(capsys)
        assert leftover_rows(output) == rows
        assert f'       - {settings_path}: theme' in output, 'the completion summary lists the value left in place'
        assert not [name for name in deleted if name in output], 'nothing the run deleted is listed anywhere'
        final = _settings(claude_dir)
        assert 'FOO' not in final.get('env', {})
        assert 'availableModels' not in final
        assert final['permissions'] == {'allow': ['Read']}
        assert final['theme'] == 'dark', 'the leftover stays in place without the flag'
        leftovers = read_manifest(claude_dir)['leftovers']
        assert [item['path'] for item in leftovers['items']] == [['theme']]
        assert leftovers['dropped'] == []

        assert run_main(['--profile', 'base', *SKIP, '--yes']) == 0

        output = printed(capsys)
        assert leftover_rows(output) == rows
        assert 'already gone' not in output, 'the next run finds nothing it carried gone'

    @staticmethod
    def _switch_to_null_hooks_and_status_line(
        e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> list[str]:
        """Install a base profile whose hooks and status line run two hook files, then null both in its configuration.

        Returns:
            The rows naming the two hook files, as the leftovers block prints them after its marker.
        """
        claude_dir = e2e_isolated_home['claude_dir']
        cfg = write_config(configs, 'base.yaml', {
            'name': 'Null Hooks',
            'rules': ['rules/rule.md'],
            'hooks': {
                'files': ['hooks/a.py', 'hooks/b.py'],
                'events': [{'event': 'PreToolUse', 'matcher': '*', 'type': 'command', 'command': 'a.py'}],
            },
            'status-line': {'file': 'b.py', 'padding': 1, 'refresh-interval': 30},
        })
        assert run_main([str(cfg), *SKIP, '--yes']) == 0
        installed = _settings(claude_dir)
        assert _commands(installed['hooks']['PreToolUse']) == [_hook_command(claude_dir, 'a.py')]
        assert installed['statusLine']['command'] == _hook_command(claude_dir, 'b.py')
        assert installed['statusLine']['refreshInterval'] == 30
        recorded = [record['path'][0] for record in read_manifest(claude_dir)['settings_written']]
        assert recorded.count('statusLine') == 1, 'the status line is recorded whole'
        assert 'hooks' in recorded
        write_config(configs, 'base.yaml', {
            'name': 'Null Hooks', 'rules': ['rules/rule.md'], 'hooks': None, 'status-line': None,
        })
        capsys.readouterr()
        return [f'file: {claude_dir / "hooks" / "a.py"}', f'file: {claude_dir / "hooks" / "b.py"}']

    @staticmethod
    def _assert_no_settings_row_and_both_deleted(output: str, claude_dir: Path) -> None:
        settings_path = claude_dir / 'settings.json'
        assert f'{settings_path}: statusLine' not in output, 'nothing the run deletes is listed anywhere'
        assert f'{settings_path}: hooks.' not in output, 'nothing the run deletes is listed anywhere'
        final = _settings(claude_dir)
        assert 'hooks' not in final
        assert 'statusLine' not in final

    def test_null_hooks_and_status_line_leave_only_the_unwired_hook_files_as_leftovers(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A null hooks or status-line makes Step 18 delete it whole, so only the hook files it ran are listed."""
        claude_dir = e2e_isolated_home['claude_dir']
        files = self._switch_to_null_hooks_and_status_line(e2e_isolated_home, configs, capsys)

        assert run_main(['--profile', 'base', *SKIP, '--yes']) == 0

        output = printed(capsys)
        assert leftover_rows(output) == [
            *(f'  [leftover] {row}' for row in files),
            '  They stay in place.',
            f'  {setup_environment.LEFTOVERS_FLAG_FOOTER}',
        ], 'no settings.json item is listed: Step 18 deletes them'
        self._assert_no_settings_row_and_both_deleted(output, claude_dir)
        assert (claude_dir / 'hooks' / 'a.py').is_file(), 'nothing leaves without the flag'
        leftovers = read_manifest(claude_dir)['leftovers']
        assert [item['path'] for item in leftovers['items']] == ['hooks/a.py', 'hooks/b.py'], 'nothing else is carried'
        assert leftovers['dropped'] == []

    def test_the_flagged_run_that_nulls_hooks_and_status_line_removes_the_hook_files_they_ran(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Before consent no group keeps the hook files Step 18 is about to unwire, so Step 23 of the same run removes them."""
        claude_dir = e2e_isolated_home['claude_dir']
        files = self._switch_to_null_hooks_and_status_line(e2e_isolated_home, configs, capsys)

        before = home_state(e2e_isolated_home['home'])
        assert run_main(['--profile', 'base', *SKIP, '--remove-leftovers', '--dry-run']) == 0
        marker = '[would be removed in Step 23]'
        assert leftover_rows(printed(capsys)) == [
            *(f'  {marker} {row}' for row in files),
            f'  Step 23 removes each item marked {marker} only while it still holds what the setup wrote.',
        ]
        assert home_state(e2e_isolated_home['home']) == before, 'a dry run removes nothing'

        assert run_main(['--profile', 'base', *SKIP, '--remove-leftovers', '--yes']) == 0

        output = printed(capsys)
        assert leftover_rows(output) == [*(f'  [remove] {row}' for row in files), f'  {REMOVES}']
        self._assert_no_settings_row_and_both_deleted(output, claude_dir)
        assert not (claude_dir / 'hooks' / 'a.py').exists()
        assert not (claude_dir / 'hooks' / 'b.py').exists()
        assert (claude_dir / 'rules' / 'rule.md').is_file()
        leftovers = read_manifest(claude_dir)['leftovers']
        assert leftovers['removed'] == ['file: hooks/a.py', 'file: hooks/b.py']
        assert leftovers['items'] == []
        assert leftovers['dropped'] == []

    def test_a_pin_writes_the_update_controls_in_place_of_a_null_env_so_its_variables_stay_leftovers(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A pinned run merges the update controls into env instead of deleting it, so a variable written earlier stays."""
        claude_dir = e2e_isolated_home['claude_dir']
        settings_path = claude_dir / 'settings.json'
        cfg = write_config(configs, 'base.yaml', {
            'name': 'Pinned Null Env', 'claude-code-version': PIN, 'user-settings': {'env': {'FOO': 'x'}},
        })
        assert run_main([str(cfg), *SKIP, '--yes']) == 0
        write_config(configs, 'base.yaml', {
            'name': 'Pinned Null Env', 'claude-code-version': PIN, 'user-settings': {'env': None},
        })
        capsys.readouterr()

        assert run_main(['--profile', 'base', *SKIP, '--yes']) == 0

        assert leftover_rows(printed(capsys)) == [
            f'  [leftover] {settings_path}: env.FOO',
            '  They stay in place.',
            f'  {setup_environment.LEFTOVERS_FLAG_FOOTER}',
        ]
        assert _settings(claude_dir)['env']['FOO'] == 'x', 'the null env deleted nothing'
        assert [item['path'] for item in read_manifest(claude_dir)['leftovers']['items']] == [['env', 'FOO']]

        assert run_main(['--profile', 'base', *SKIP, '--yes', '--remove-leftovers']) == 0

        env = _settings(claude_dir)['env']
        assert 'FOO' not in env
        assert env['DISABLE_UPDATES'] == '1', 'the update controls of the pin stay'

    def test_a_remembered_selection_that_splits_a_matcher_group_lists_no_leftover_group(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The group the selected components write differs from the full build's, and it is written again."""
        claude_dir = e2e_isolated_home['claude_dir']
        cfg = write_config(configs, 'base.yaml', {
            'name': 'Split Group',
            'hooks': {
                'files': ['hooks/a.py', 'hooks/b.py'],
                'events': [
                    {'event': 'PreToolUse', 'matcher': '*', 'type': 'command', 'command': 'a.py', 'id': 'ea'},
                    {'event': 'PreToolUse', 'matcher': '*', 'type': 'command', 'command': 'b.py', 'id': 'eb'},
                ],
            },
            'components': [
                {'name': 'core', 'includes': {'hooks': ['hooks/a.py', 'ea']}},
                {'name': 'extra', 'default': False, 'includes': {'hooks': ['hooks/b.py', 'eb']}},
            ],
        })
        assert run_main([str(cfg), *SKIP, '--yes', '--without', 'extra']) == 0
        group = _settings(claude_dir)['hooks']['PreToolUse']
        assert _commands(group) == [_hook_command(claude_dir, 'a.py')]
        capsys.readouterr()

        for _ in range(2):
            assert run_main(['--profile', 'base', *SKIP, '--yes']) == 0
            assert HEADING not in printed(capsys)

        assert _settings(claude_dir)['hooks']['PreToolUse'] == group
        recorded = [record for record in read_manifest(claude_dir)['settings_written'] if record['kind'] == 'hook-group']
        assert [record['sha256'] for record in recorded] == [setup_environment.leftover_digest(group[0])]

    def test_a_switch_removes_settings_one_by_one_and_only_while_unchanged(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        claude_dir = e2e_isolated_home['claude_dir']
        first = write_config(configs, 'first.yaml', {
            'name': 'First', 'user-settings': {'theme': 'dark', 'cleanupPeriodDays': 7, 'permissions': {'allow': ['Read']}},
        })
        second = write_config(configs, 'second.yaml', {'name': 'Second', 'user-settings': {'includeCoAuthoredBy': False}})
        assert run_main([str(first), *SKIP, '--yes']) == 0
        installed = _settings(claude_dir)
        installed['theme'] = 'light'
        installed['permissions']['allow'].append('Edit')
        _write_settings(claude_dir, installed)
        capsys.readouterr()

        assert run_main([str(second), *SKIP, '--yes', '--switch-config']) == 0

        output = printed(capsys)
        settings_path = claude_dir / 'settings.json'
        assert f'{settings_path}: cleanupPeriodDays' in output.split('Accepted via')[0]
        assert _settings(claude_dir) == {
            'theme': 'light', 'permissions': {'allow': ['Edit']}, 'includeCoAuthoredBy': False,
        }, 'a changed value and an element the user added stay; no whole key is deleted'
        assert leftover_rows(output) == [
            f'  [remove] {settings_path}: cleanupPeriodDays',
            f'  [remove] {settings_path}: permissions.allow element "Read"',
            f'  [changed since written: left in place, no longer tracked] {settings_path}: theme',
            f'  {REMOVES}',
        ], 'the summary lists what the switch removes as a run given --remove-leftovers does'
        leftovers = read_manifest(claude_dir)['leftovers']
        assert sorted(leftovers['removed']) == [
            'settings.json: cleanupPeriodDays',
            f'settings.json: permissions.allow element {setup_environment.leftover_digest("Read")[:12]}',
        ]
        assert leftovers['items'] == []

    def test_a_switch_removes_a_hook_file_together_with_the_group_that_wires_it(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Before consent the switch reads settings.json as Step 23 leaves it, so the wired file shows [remove]."""
        claude_dir = e2e_isolated_home['claude_dir']
        settings_path = claude_dir / 'settings.json'
        first = write_config(configs, 'first.yaml', _hooked('a.py', helpers=['h.py'], allow=['Read']))
        second = write_config(configs, 'second.yaml', {**_hooked('b.py', helpers=[], allow=['Read']), 'name': 'Second'})
        assert run_main([str(first), *SKIP, '--yes']) == 0
        installed = _settings(claude_dir)
        installed['hooks']['Stop'] = [USER_GROUP]
        _write_settings(claude_dir, installed)
        capsys.readouterr()

        assert run_main([str(second), *SKIP, '--yes', '--switch-config']) == 0

        output = printed(capsys)
        rows = [
            f'  [remove] file: {claude_dir / "hooks" / "a.py"}',
            f'  [kept: stays with hooks/b.py, which is still wired] file: {claude_dir / "hooks" / "h.py"}',
            f'  [remove] {settings_path}: hooks.PreToolUse group matcher "*" (1 hook)',
            f'  {REMOVES_OTHERS_STAY}',
        ]
        guard = output.split('The previous configuration leaves behind:')[1].split('Accepted via')[0]
        assert all(row.strip() in guard for row in rows), guard
        assert '[kept: still wired' not in guard, 'no settings file Step 23 leaves keeps the old script'
        assert leftover_rows(output) == rows
        assert not (claude_dir / 'hooks' / 'a.py').exists()
        assert (claude_dir / 'hooks' / 'h.py').is_file(), 'the wired b.py may import the dropped helper'
        assert (claude_dir / 'hooks' / 'b.py').is_file()
        settings = _settings(claude_dir)
        assert _commands(settings['hooks']['PreToolUse']) == [_hook_command(claude_dir, 'b.py')]
        assert settings['hooks']['Stop'] == [USER_GROUP], 'a group the user added stays'

    def test_a_status_line_pointed_at_another_file_no_longer_keeps_the_old_one(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Step 18 overwrites the status line command before Step 23 looks at the old file."""
        claude_dir = e2e_isolated_home['claude_dir']
        cfg = write_config(configs, 'base.yaml', {
            'name': 'Status Env', 'hooks': {'files': ['hooks/a.py']}, 'status-line': {'file': 'a.py'},
        })
        assert run_main([str(cfg), *SKIP, '--yes']) == 0
        assert _settings(claude_dir)['statusLine']['command'] == _hook_command(claude_dir, 'a.py')
        write_config(configs, 'base.yaml', {
            'name': 'Status Env', 'hooks': {'files': ['hooks/b.py']}, 'status-line': {'file': 'b.py'},
        })
        capsys.readouterr()

        assert run_main(['--profile', 'base', *SKIP, '--yes']) == 0

        assert leftover_rows(printed(capsys))[0] == f'  [leftover] file: {claude_dir / "hooks" / "a.py"}'
        assert (claude_dir / 'hooks' / 'a.py').is_file(), 'nothing leaves without the flag'

        assert run_main(['--profile', 'base', *SKIP, '--yes', '--remove-leftovers']) == 0

        assert leftover_rows(printed(capsys))[0] == f'  [remove] file: {claude_dir / "hooks" / "a.py"}'
        assert not (claude_dir / 'hooks' / 'a.py').exists()
        assert _settings(claude_dir)['statusLine']['command'] == _hook_command(claude_dir, 'b.py')

    @pytest.mark.parametrize('padding', [1, None], ids=['padding', 'null-padding'])
    def test_a_dropped_status_line_leaves_whole_with_the_file_it_ran(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
        padding: int | None,
    ) -> None:
        """The status line is one item: unchanged since written, it leaves whole, its null members never recorded."""
        claude_dir = e2e_isolated_home['claude_dir']
        settings_path = claude_dir / 'settings.json'
        cfg = write_config(configs, 'base.yaml', {
            'name': 'Status Env', 'rules': ['rules/rule.md'], 'hooks': {'files': ['hooks/a.py']},
            'status-line': {'file': 'a.py', 'padding': padding},
        })
        assert run_main([str(cfg), *SKIP, '--yes']) == 0
        written: dict[str, Any] = {'type': 'command', 'command': _hook_command(claude_dir, 'a.py')}
        if padding is not None:
            written['padding'] = padding
        assert _settings(claude_dir)['statusLine'] == written
        write_config(configs, 'base.yaml', {'name': 'Status Env', 'rules': ['rules/rule.md']})
        capsys.readouterr()

        assert run_main(['--profile', 'base', *SKIP, '--yes', '--remove-leftovers']) == 0

        assert leftover_rows(printed(capsys)) == [
            f'  [remove] file: {claude_dir / "hooks" / "a.py"}',
            f'  [remove] {settings_path}: statusLine',
            f'  {REMOVES}',
        ]
        assert 'statusLine' not in _settings(claude_dir)
        assert not (claude_dir / 'hooks' / 'a.py').exists()
        assert read_manifest(claude_dir)['leftovers']['removed'] == ['settings.json: statusLine', 'file: hooks/a.py']

    def test_a_status_line_changed_in_place_stays_whole_when_the_configuration_drops_it(
        self, e2e_isolated_home: dict[str, Path], configs: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A status line /statusline rewrote is the user's now: no member of it leaves, and it is no longer tracked."""
        claude_dir = e2e_isolated_home['claude_dir']
        settings_path = claude_dir / 'settings.json'
        cfg = write_config(configs, 'base.yaml', {
            'name': 'Status Env', 'rules': ['rules/rule.md'], 'hooks': {'files': ['hooks/a.py']},
            'status-line': {'file': 'a.py', 'padding': 1},
        })
        assert run_main([str(cfg), *SKIP, '--yes']) == 0
        installed = _settings(claude_dir)
        installed['statusLine'] = {'type': 'command', 'command': 'bash ~/.claude/statusline-command.sh'}
        _write_settings(claude_dir, installed)
        write_config(configs, 'base.yaml', {'name': 'Status Env', 'rules': ['rules/rule.md']})
        capsys.readouterr()

        assert run_main(['--profile', 'base', *SKIP, '--yes', '--remove-leftovers']) == 0

        rows = leftover_rows(printed(capsys))
        assert f'  [changed since written: left in place, no longer tracked] {settings_path}: statusLine' in rows
        assert _settings(claude_dir)['statusLine'] == installed['statusLine'], 'the status line keeps its type'
        leftovers = read_manifest(claude_dir)['leftovers']
        assert {'label': 'settings.json: statusLine', 'reason': 'changed'} in leftovers['dropped']
        assert all(item['kind'] != 'setting' for item in leftovers['items'])
