"""Tests for the hook-file wiring check of the leftovers and the hold on a dropped hook helper.

A hook file a settings file a session reads still wires, by its absolute path
or below a home token, is kept, in the profile's own settings files and in the
config.json and settings.json of a profile that links hooks/ from this one. A
dropped hooks.helpers module stays while a wired hook file of the folder is one
the run does not install as the configuration ships it: a script edited by
hand, a leftover script still wired, a file the setup never wrote. The
configuration's own scripts hold nothing, because Step 17 writes them as the
configuration ships them, over an edit too.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from scripts import setup_environment
from scripts.setup_environment import InstalledProfile
from scripts.setup_environment import LeftoverReadError
from scripts.setup_environment import LiveLeftoverState
from scripts.setup_environment import PlannedRecords
from tests.leftovers_unit_support import helper_entry
from tests.leftovers_unit_support import hooks_settings
from tests.leftovers_unit_support import live_state
from tests.leftovers_unit_support import sha
from tests.leftovers_unit_support import wiring
from tests.leftovers_unit_support import write
from tests.leftovers_unit_support import write_json


@pytest.fixture
def layout(tmp_path: Path) -> tuple[Path, Path]:
    """The ~/.claude directory and an isolated profile directory inside it."""
    claude_dir = tmp_path / '.claude'
    profile_dir = claude_dir / 'p'
    profile_dir.mkdir(parents=True)
    return claude_dir, profile_dir


class TestHookFileReferences:
    """A hook file is wired while a settings file a session reads names it in a hook or the status line."""

    def test_shell_form_command(self, layout: tuple[Path, Path]) -> None:
        _claude_dir, profile_dir = layout
        settings = profile_dir / 'settings.json'
        write_json(settings, wiring(profile_dir, 'a.py', 'PreToolUse'))

        detail = setup_environment._hook_file_references(
            'hooks/a.py', profile_dir=profile_dir, home_dir=profile_dir.parents[1], settings_files=[settings], dependents=[],
        )

        assert detail == f'still wired in {settings} hooks.PreToolUse'

    def test_exec_form_args_and_command(self, layout: tuple[Path, Path]) -> None:
        _claude_dir, profile_dir = layout
        settings = profile_dir / 'settings.json'
        write_json(settings, {'hooks': {
            'Stop': [{'matcher': '', 'hooks': [
                {'type': 'command', 'command': 'uv', 'args': ['run', (profile_dir / 'hooks' / 'a.py').as_posix()]},
                {'type': 'command', 'command': (profile_dir / 'hooks' / 'run.sh').as_posix(), 'args': []},
            ]}],
        }})

        def _references(relative: str) -> str | None:
            return setup_environment._hook_file_references(
                relative, profile_dir=profile_dir, home_dir=profile_dir.parents[1], settings_files=[settings], dependents=[],
            )

        assert _references('hooks/a.py') == f'still wired in {settings} hooks.Stop'
        assert _references('hooks/run.sh') == f'still wired in {settings} hooks.Stop'
        assert _references('hooks/other.py') is None

    def test_status_line(self, layout: tuple[Path, Path]) -> None:
        _claude_dir, profile_dir = layout
        settings = profile_dir / 'settings.json'
        status = (profile_dir / 'hooks' / 'status.py').as_posix()
        write_json(settings, {'statusLine': {'type': 'command', 'command': f'uv run "{status}"'}})

        detail = setup_environment._hook_file_references(
            'hooks/status.py', profile_dir=profile_dir, home_dir=profile_dir.parents[1], settings_files=[settings],
            dependents=[],
        )

        assert detail == f'still wired in {settings} statusLine'

    def test_a_longer_name_and_a_path_outside_hooks_are_not_references(self, layout: tuple[Path, Path]) -> None:
        _claude_dir, profile_dir = layout
        settings = profile_dir / 'settings.json'
        write_json(settings, wiring(profile_dir, 'a.py.bak'))

        def _references(relative: str) -> str | None:
            return setup_environment._hook_file_references(
                relative, profile_dir=profile_dir, home_dir=profile_dir.parents[1], settings_files=[settings], dependents=[],
            )

        assert _references('hooks/a.py') is None
        assert _references('rules/a.py.bak') is None, 'only files under hooks/ are wired'

    def test_absent_settings_files_wire_nothing(self, layout: tuple[Path, Path]) -> None:
        _claude_dir, profile_dir = layout
        assert setup_environment._hook_file_references(
            'hooks/a.py', profile_dir=profile_dir, home_dir=profile_dir.parents[1],
            settings_files=[profile_dir / 'settings.json'], dependents=[],
        ) is None

    def test_an_unreadable_settings_file_cannot_be_checked(self, layout: tuple[Path, Path]) -> None:
        _claude_dir, profile_dir = layout
        settings = profile_dir / 'settings.json'
        settings.write_text('{not json', encoding='utf-8')
        with pytest.raises(LeftoverReadError, match='settings.json'):
            setup_environment._hook_file_references(
                'hooks/a.py', profile_dir=profile_dir, home_dir=profile_dir.parents[1], settings_files=[settings],
                dependents=[],
            )

    def test_a_dependent_linking_hooks_wires_its_own_spelling(self, layout: tuple[Path, Path]) -> None:
        claude_dir, profile_dir = layout
        lab, docs = claude_dir / 'lab', claude_dir / 'docs'
        write_json(lab / 'config.json', wiring(lab, 'a.py', 'UserPromptSubmit'))
        write_json(docs / 'config.json', wiring(docs, 'a.py'))
        dependents = [
            InstalledProfile('docs', docs, docs / 'manifest.json', {'link': {'dirs': ['rules'], 'source': 'p'}}),
            InstalledProfile('lab', lab, lab / 'manifest.json', {'link': {'dirs': ['hooks', 'rules'], 'source': 'p'}}),
        ]

        detail = setup_environment._hook_file_references(
            'hooks/a.py', profile_dir=profile_dir, home_dir=profile_dir.parents[1], settings_files=[], dependents=dependents,
        )

        assert detail == (
            f'still wired in profile lab ({lab / "config.json"} hooks.UserPromptSubmit) until that profile is '
            'refreshed; a later run with --remove-leftovers removes it'
        ), 'a dependent that does not link hooks/ wires its own files'

    @pytest.mark.parametrize(('text', 'windows', 'expected'), [
        ('uv run "C:/Users/Me/.claude/hooks/a.py"', False, True),
        ('uv run "c:/users/me/.claude/HOOKS/a.py"', False, False),
        ('uv run "c:/users/me/.claude/HOOKS/a.py"', True, True),
        ('uv run "C:\\Users\\Me\\.claude\\hooks\\a.py"', True, True),
        ('uv run "C:\\Users\\Me\\.claude\\hooks\\a.py"', False, False),
        ('uv run "C:/Users/Me/.claude/hooks/a.pyc"', True, False),
        ('uv run "C:/Users/Me/.claude/hooks/a.py" "C:/Users/Me/.claude/hooks/a.json"', False, True),
        ('C:/Users/Me/.claude/hooks/a.py', False, True),
    ])
    def test_spelling_match(self, text: str, windows: bool, expected: bool) -> None:
        """Windows paths compare without letter case and with either separator; other platforms exactly."""
        assert setup_environment._text_names_path(
            text, 'C:/Users/Me/.claude/hooks/a.py', windows=windows, home='C:/Users/Me',
        ) is expected

    @pytest.mark.parametrize(('text', 'expected'), [
        ('uv run ~/.claude/hooks/a.py', True),
        ('uv run "$HOME/.claude/hooks/a.py"', True),
        ('uv run "$HOME"/.claude/hooks/a.py', True),
        ('uv run ${HOME}/.claude/hooks/a.py', True),
        ('uv run $env:USERPROFILE/.claude/hooks/a.py', True),
        ('uv run %USERPROFILE%/.claude/hooks/a.py', True),
        ('uv run --script=~/.claude/hooks/a.py', True),
        ('uv run ~\\.claude\\hooks\\a.py', False),
        ('uv run foo~/.claude/hooks/a.py', False),
        ('uv run /x$HOME/.claude/hooks/a.py', False),
        ('uv run ~other/.claude/hooks/a.py', False),
        ('uv run ~/.claude/hooks/a.pyc', False),
        ('uv run ~/.claude/p/hooks/a.py', False),
    ])
    def test_home_token_spellings_outside_windows(self, text: str, expected: bool) -> None:
        """A hook wired by hand names a file through the home token, which the check reads as the home.

        A token glued to a word or a path, ~other and a longer name name
        nothing; outside Windows a path compares as spelled, so a backslash
        spelling names no file there.
        """
        assert setup_environment._text_names_path(
            text, '/home/me/.claude/hooks/a.py', windows=False, home='/home/me',
        ) is expected

    @pytest.mark.parametrize('token', ['~', '$HOME', '${HOME}', '"$HOME"', '$env:USERPROFILE', '%USERPROFILE%'])
    @pytest.mark.parametrize('separator', ['/', '\\'])
    def test_home_token_spellings_on_windows(self, token: str, separator: str) -> None:
        """On Windows every home token names the home with either separator and in any letter case."""
        text = f'uv run {token}{separator}.claude{separator}Hooks{separator}A.py'
        assert setup_environment._text_names_path(
            text, 'C:/Users/Me/.claude/hooks/a.py', windows=True, home='C:/Users/Me',
        ) is True

    @pytest.mark.parametrize('profile', ['', 'p'], ids=['base', 'isolated'])
    def test_a_hand_wired_home_token_spelling_is_a_reference(self, tmp_path: Path, profile: str) -> None:
        """A settings file that runs the file as ~/.claude/... or $HOME/.claude/... still wires it."""
        home = tmp_path / 'home'
        profile_dir = home / '.claude' / profile if profile else home / '.claude'
        settings = profile_dir / 'settings.json'
        prefix = f'~/.claude/{profile}/' if profile else '~/.claude/'
        write_json(settings, {'hooks': {'Stop': [{'matcher': '', 'hooks': [
            {'type': 'command', 'command': f'uv run {prefix}hooks/a.py'},
            {'type': 'command', 'command': 'uv', 'args': ['run', f'$HOME/{prefix[2:]}hooks/b.py']},
        ]}]}})

        def _references(relative: str) -> str | None:
            return setup_environment._hook_file_references(
                relative, profile_dir=profile_dir, home_dir=home, settings_files=[settings], dependents=[],
            )

        assert _references('hooks/a.py') == f'still wired in {settings} hooks.Stop'
        assert _references('hooks/b.py') == f'still wired in {settings} hooks.Stop'
        assert _references('hooks/c.py') is None

    def test_a_dependent_wiring_through_a_home_token_is_a_reference(self, layout: tuple[Path, Path]) -> None:
        claude_dir, profile_dir = layout
        lab = claude_dir / 'lab'
        write_json(lab / 'settings.json', hooks_settings(
            'Stop', {'type': 'command', 'command': 'uv run %USERPROFILE%/.claude/lab/hooks/a.py'},
        ))
        dependents = [
            InstalledProfile('lab', lab, lab / 'manifest.json', {'link': {'dirs': ['hooks'], 'source': 'p'}}),
        ]

        detail = setup_environment._hook_file_references(
            'hooks/a.py', profile_dir=profile_dir, home_dir=claude_dir.parent, settings_files=[], dependents=dependents,
        )

        assert detail is not None
        assert detail.startswith(f'still wired in profile lab ({lab / "settings.json"} hooks.Stop)')


class TestComputeWithHookReferences:
    """A wired hook file is kept, and so is a dropped hook helper while a hook file the run does not install is wired."""

    def test_wired_script_holds_the_helpers_but_not_another_dropped_script(self, layout: tuple[Path, Path]) -> None:
        claude_dir, profile_dir = layout
        script = write(profile_dir / 'hooks' / 'a.py', b'import helper')
        other = write(profile_dir / 'hooks' / 'other.py', b'other')
        helper = write(profile_dir / 'hooks' / 'helper.py', b'helper')
        rule = write(profile_dir / 'rules' / 'old.md', b'rule')
        settings = profile_dir / 'settings.json'
        write_json(settings, wiring(profile_dir, 'a.py', 'PreToolUse'))
        manifest: dict[str, object] = {'files_written': [
            {'path': 'hooks/a.py', 'sha256': script},
            {'path': 'hooks/helper.py', 'sha256': helper, 'hook_helper': True},
            {'path': 'hooks/other.py', 'sha256': other},
            {'path': 'rules/old.md', 'sha256': rule},
        ]}

        report = setup_environment.compute_profile_leftovers(
            manifest, profile_dir, profile_name='p', planned=PlannedRecords(),
            live=live_state(profile_dir, settings_files=(settings,)), claude_dir=claude_dir,
        )

        assert [(entry.item.path, entry.state, entry.detail) for entry in report.entries] == [
            ('hooks/a.py', 'referenced', f'still wired in {settings} hooks.PreToolUse'),
            ('hooks/helper.py', 'held', 'stays with hooks/a.py, which is still wired'),
            ('hooks/other.py', 'removable', ''),
            ('rules/old.md', 'removable', ''),
        ], 'a dropped script nothing wires is no helper: only a hooks.helpers module stays'
        assert [item.path for item in report.carried()] == [
            'hooks/a.py', 'hooks/helper.py', 'hooks/other.py', 'rules/old.md',
        ]
        record = setup_environment.leftovers_manifest_record(report, run_at='t')
        assert {'kind': 'file', 'path': 'hooks/helper.py', 'sha256': helper, 'hook_helper': True} in record['items']

    @pytest.mark.parametrize('holder', ['edited', 'leftover', 'never-written'])
    def test_a_wired_hook_file_the_run_does_not_install_holds_the_helper(
        self, layout: tuple[Path, Path], holder: str,
    ) -> None:
        """A script edited by hand, a leftover script still wired and one the setup never wrote each keep a helper."""
        claude_dir, profile_dir = layout
        helper = write(profile_dir / 'hooks' / 'helper.py', b'helper')
        settings = profile_dir / 'settings.json'
        records: list[dict[str, object]] = [{'path': 'hooks/helper.py', 'sha256': helper, 'hook_helper': True}]
        if holder == 'edited':
            write(profile_dir / 'hooks' / 'a.py', b'edited by hand')
            records.append({'path': 'hooks/a.py', 'sha256': sha(b'as written')})
        elif holder == 'leftover':
            records.append({'path': 'hooks/a.py', 'sha256': write(profile_dir / 'hooks' / 'a.py', b'as written')})
        else:
            write(profile_dir / 'hooks' / 'a.py', b'mine')
        manifest: dict[str, object] = {'files_written': records}

        def _details() -> dict[str, tuple[str, str]]:
            report = setup_environment.compute_profile_leftovers(
                manifest, profile_dir, profile_name='p', planned=PlannedRecords(files=frozenset({'hooks/b.py'})),
                live=live_state(profile_dir, settings_files=(settings,)), claude_dir=claude_dir,
            )
            return {entry.item.path: (entry.state, entry.detail) for entry in report.entries}

        assert _details()['hooks/helper.py'] == ('removable', ''), 'nothing wires a hook file yet'
        write_json(settings, wiring(profile_dir, 'a.py'))
        assert _details()['hooks/helper.py'] == ('held', 'stays with hooks/a.py, which is still wired')

    @pytest.mark.parametrize('on_disk', [None, b'as the configuration ships it', b'edited by hand'],
                             ids=['not-yet-installed', 'as-written', 'edited'])
    def test_a_wired_hook_file_the_run_installs_holds_nothing(
        self, layout: tuple[Path, Path], on_disk: bytes | None,
    ) -> None:
        """Step 17 writes the configuration's own script with its bytes, over an edit too, so it imports no dropped helper."""
        claude_dir, profile_dir = layout
        helper = write(profile_dir / 'hooks' / 'helper.py', b'helper')
        if on_disk is not None:
            write(profile_dir / 'hooks' / 'b.py', on_disk)
        settings = profile_dir / 'settings.json'
        write_json(settings, wiring(profile_dir, 'b.py'))
        manifest: dict[str, object] = {
            'files_written': [{'path': 'hooks/helper.py', 'sha256': helper, 'hook_helper': True}],
        }

        report = setup_environment.compute_profile_leftovers(
            manifest, profile_dir, profile_name='p', planned=PlannedRecords(files=frozenset({'hooks/B.py'})),
            live=live_state(profile_dir, settings_files=(settings,)), claude_dir=claude_dir,
        )

        assert [(entry.item.path, entry.state) for entry in report.entries] == [('hooks/helper.py', 'removable')], (
            'the planned path compares as the leftover keys do'
        )

    def test_unreadable_wiring_leaves_a_helper_unchecked(self, layout: tuple[Path, Path]) -> None:
        claude_dir, profile_dir = layout
        helper = write(profile_dir / 'hooks' / 'helper.py', b'helper')
        settings = profile_dir / 'settings.json'
        settings.write_text('{broken', encoding='utf-8')

        held = setup_environment._hold_with_wired_hook_files(
            [helper_entry('hooks/helper.py', helper)], live_state(profile_dir, settings_files=(settings,)), installed=(),
        )

        assert [(entry.state, 'settings.json' in entry.detail) for entry in held] == [('unreadable', True)]

    @pytest.mark.parametrize(('wired', 'expected'), [('a.py', 'held'), ('b.py', 'removable')],
                             ids=['dropped-script', 'own-script'])
    def test_a_dependent_wiring_its_own_spelling_holds_the_helper_only_with_a_dropped_script(
        self, layout: tuple[Path, Path], wired: str, expected: str,
    ) -> None:
        """A profile linking hooks/ runs the dropped script until its refresh; the source's own new script holds nothing."""
        claude_dir, profile_dir = layout
        helper = write(profile_dir / 'hooks' / 'helper.py', b'helper')
        script = write(profile_dir / 'hooks' / 'a.py', b'import helper')
        write(profile_dir / 'hooks' / 'b.py', b'new')
        lab = claude_dir / 'lab'
        write_json(lab / 'config.json', wiring(lab, wired))
        dependents = (
            InstalledProfile('lab', lab, lab / 'manifest.json', {'link': {'dirs': ['hooks'], 'source': 'p'}}),
        )
        manifest: dict[str, object] = {'files_written': [
            {'path': 'hooks/a.py', 'sha256': script},
            {'path': 'hooks/helper.py', 'sha256': helper, 'hook_helper': True},
        ]}

        report = setup_environment.compute_profile_leftovers(
            manifest, profile_dir, profile_name='p', planned=PlannedRecords(files=frozenset({'hooks/b.py'})),
            live=live_state(profile_dir, dependents=dependents), claude_dir=claude_dir,
        )

        states = {entry.item.path: (entry.state, entry.detail) for entry in report.entries}
        assert states['hooks/helper.py'][0] == expected
        if expected == 'held':
            assert states['hooks/helper.py'][1] == 'stays with hooks/a.py, which is still wired'
            assert states['hooks/a.py'][0] == 'referenced'
        else:
            assert states['hooks/a.py'] == ('removable', '')

    def test_the_rebuilt_config_json_of_an_isolated_profile_is_read_before_consent(
        self, layout: tuple[Path, Path],
    ) -> None:
        """Step 18 rebuilds config.json, so the summary reads the hooks the configuration wires, not the file on disk.

        The config.json on disk still runs the dropped script; the rebuilt
        one runs the configuration's own script, which holds nothing, and,
        in exec form, a program the user put in the hooks folder, which the
        run does not install and which keeps the helper as Step 23 will.
        """
        claude_dir, profile_dir = layout
        helper = write(profile_dir / 'hooks' / 'helper.py', b'helper')
        script = write(profile_dir / 'hooks' / 'a.py', b'import helper')
        write(profile_dir / 'hooks' / 'tool', b'mine')
        write_json(profile_dir / 'config.json', wiring(profile_dir, 'a.py'))
        manifest: dict[str, object] = {'files_written': [
            {'path': 'hooks/a.py', 'sha256': script},
            {'path': 'hooks/helper.py', 'sha256': helper, 'hook_helper': True},
        ]}
        live = LiveLeftoverState.for_profile(
            profile_dir, claude_dir.parent,
            settings_files=setup_environment.leftover_settings_files(profile_dir, isolated=True, before_consent=True),
        )

        def _states(config: dict[str, Any]) -> dict[str, tuple[str, str]]:
            planned = setup_environment.planned_records(config, profile_dir, claude_dir=claude_dir)
            report = setup_environment.compute_profile_leftovers(
                manifest, profile_dir, profile_name='p', planned=planned, live=live, claude_dir=claude_dir,
            )
            return {entry.item.path: (entry.state, entry.detail) for entry in report.entries}

        removable = {'hooks/a.py': ('removable', ''), 'hooks/helper.py': ('removable', '')}
        own = {'event': 'Stop', 'type': 'command', 'command': 'b.py'}
        program = {
            'event': 'Stop', 'type': 'command', 'command': (profile_dir / 'hooks' / 'tool').as_posix(), 'args': ['run'],
        }
        assert _states({'hooks': {'files': ['hooks/b.py'], 'events': [own]}}) == removable
        assert _states({'hooks': {'files': ['hooks/b.py']}, 'status-line': {'file': 'b.py'}}) == removable
        assert _states({'hooks': {'files': ['hooks/b.py'], 'events': [own, program]}}) == {
            'hooks/a.py': ('removable', ''),
            'hooks/helper.py': ('held', 'stays with hooks/tool, which is still wired'),
        }

    @pytest.mark.parametrize('selected_config', [
        {'hooks': {'files': ['hooks/a.py'], 'events': [{'event': 'Stop', 'type': 'command', 'command': 'a.py'}]}},
        {},
    ], ids=['script-selected', 'script-deselected'])
    def test_refining_keeps_the_hold_computed_before_selection(
        self, layout: tuple[Path, Path], selected_config: dict[str, Any],
    ) -> None:
        """The configuration's script holds nothing whether a selection keeps it (Step 17) or drops it (Step 23)."""
        claude_dir, _profile_dir = layout
        helper = write(claude_dir / 'hooks' / 'helper.py', b'helper')
        write(claude_dir / 'hooks' / 'a.py', b'a')
        write_json(claude_dir / 'settings.json', wiring(claude_dir, 'a.py'))
        manifest: dict[str, object] = {
            'files_written': [{'path': 'hooks/helper.py', 'sha256': helper, 'hook_helper': True}],
        }
        live = LiveLeftoverState.for_profile(
            claude_dir, claude_dir.parent,
            settings_files=setup_environment.leftover_settings_files(claude_dir, isolated=False, before_consent=True),
        )
        hooked = {'hooks': {'files': ['hooks/a.py'], 'events': [{'event': 'Stop', 'type': 'command', 'command': 'a.py'}]}}
        report = setup_environment.compute_profile_leftovers(
            manifest, claude_dir, profile_name='base',
            planned=setup_environment.planned_records(hooked, claude_dir, claude_dir=claude_dir, base=True),
            live=live, claude_dir=claude_dir,
        )
        assert report.entries[0].state == 'removable', 'the configuration installs the wired script as written'
        selected = setup_environment.planned_records(selected_config, claude_dir, claude_dir=claude_dir, base=True)

        refined = report.refined(linked_entries=frozenset(), link_source='base', selected=selected)

        assert refined.entries[0].state == 'removable'

    def test_the_own_config_json_on_disk_is_not_read_before_consent(self, layout: tuple[Path, Path]) -> None:
        """Step 18 rebuilds an isolated profile's config.json, so the summary does not count the wiring on disk."""
        claude_dir, profile_dir = layout
        script = write(profile_dir / 'hooks' / 'old.py', b'old')
        write_json(profile_dir / 'config.json', wiring(profile_dir, 'old.py'))
        manifest: dict[str, object] = {'files_written': [{'path': 'hooks/old.py', 'sha256': script}]}

        def _state(before_consent: bool) -> str:
            live = LiveLeftoverState.for_profile(
                profile_dir, claude_dir.parent, settings_files=setup_environment.leftover_settings_files(
                    profile_dir, isolated=True, before_consent=before_consent,
                ),
            )
            report = setup_environment.compute_profile_leftovers(
                manifest, profile_dir, profile_name='p', planned=PlannedRecords(), live=live, claude_dir=claude_dir,
            )
            return report.entries[0].state

        assert _state(before_consent=True) == 'removable'
        assert _state(before_consent=False) == 'referenced'

    def test_settings_files_of_each_kind_of_profile(self, tmp_path: Path) -> None:
        profile_dir = tmp_path / 'p'
        base = [profile_dir / 'settings.json', profile_dir / 'settings.local.json']
        assert setup_environment.leftover_settings_files(profile_dir, isolated=False, before_consent=True) == base
        assert setup_environment.leftover_settings_files(profile_dir, isolated=False, before_consent=False) == base
        assert setup_environment.leftover_settings_files(profile_dir, isolated=True, before_consent=True) == [
            profile_dir / 'settings.json',
        ]
        assert setup_environment.leftover_settings_files(profile_dir, isolated=True, before_consent=False) == [
            profile_dir / 'config.json', profile_dir / 'settings.json',
        ]
