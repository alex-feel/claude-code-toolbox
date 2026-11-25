"""Tests for the removal of leftovers: --remove-leftovers, the hook-file reference check and the Step 23 remover.

A run given --remove-leftovers (or CLAUDE_CODE_TOOLBOX_REMOVE_LEFTOVERS=1)
removes in Step 23 each leftover that still holds what the setup wrote. A
hook file a settings file still wires is kept, and so is every other
leftover under hooks/ while one is kept, because a kept script may import
them. Step 23 derives every state again from what is on disk then, records
each outcome in the manifest, and a removal that fails keeps the item
recorded and ends the run with exit code 1.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts import setup_environment
from scripts.setup_environment import InstalledProfile
from scripts.setup_environment import LeftoverEntry
from scripts.setup_environment import LeftoverItem
from scripts.setup_environment import LeftoverOutcome
from scripts.setup_environment import LeftoverReadError
from scripts.setup_environment import LeftoverRemoval
from scripts.setup_environment import LeftoverReport
from scripts.setup_environment import LiveLeftoverState
from scripts.setup_environment import PlannedRecords

_REAL_RECORD_MANIFEST_LEFTOVERS = setup_environment._record_manifest_leftovers
REPO_ROOT = Path(__file__).resolve().parents[1]


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _write(path: Path, content: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return _sha(content)


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding='utf-8')


@pytest.fixture
def layout(tmp_path: Path) -> tuple[Path, Path]:
    """The ~/.claude directory and an isolated profile directory inside it."""
    claude_dir = tmp_path / '.claude'
    profile_dir = claude_dir / 'p'
    profile_dir.mkdir(parents=True)
    return claude_dir, profile_dir


def _live(
    profile_dir: Path,
    *,
    holders: dict[str, list[str]] | None = None,
    linked: frozenset[str] = frozenset(),
    settings_files: tuple[Path, ...] = (),
    dependents: tuple[InstalledProfile, ...] = (),
) -> LiveLeftoverState:
    """A live state over the real file system and real settings files, with links and holders given."""
    def _references(relative: str, view: Mapping[Path, dict[str, Any]]) -> str | None:
        return setup_environment._hook_file_references(
            relative, profile_dir=profile_dir, settings_files=settings_files, dependents=dependents, view=view,
        )

    return LiveLeftoverState(
        file_digest=setup_environment._live_file_digest,
        under_link=lambda relative: relative.split('/')[0] in linked,
        destination_holders=lambda dest: (holders or {}).get(dest, []),
        hook_references=_references,
    )


def _report(profile_dir: Path, *entries: LeftoverEntry) -> LeftoverReport:
    return LeftoverReport(profile_name='p', profile_dir=profile_dir, entries=tuple(entries), untracked_note=False)


def _removable(path: str, digest: str, kind: str = 'file') -> LeftoverEntry:
    return LeftoverEntry(LeftoverItem(kind, path, digest), 'removable', '')


def _step(
    report: LeftoverReport | None,
    *,
    live: LiveLeftoverState,
    claude_dir: Path,
    profile_dir: Path,
    remove: bool = True,
    download_failed: bool = False,
    written: PlannedRecords | None = None,
) -> LeftoverRemoval | None:
    return setup_environment.run_leftovers_step(
        report,
        remove=remove,
        download_failed=download_failed,
        written=written or PlannedRecords(),
        live=live,
        profile_dir=profile_dir,
        claude_dir=claude_dir,
        manifest_path=profile_dir / 'manifest.json',
        run_at='t',
    )


def _results(removal: LeftoverRemoval | None) -> dict[str, str]:
    assert removal is not None
    return {outcome.entry.item.path: outcome.result for outcome in removal.outcomes}


class TestFlagAndVariable:
    """--remove-leftovers is one interface: the flag, its variable, the CLI and the wrappers."""

    def test_variable_is_a_switch_twin_that_child_runs_do_not_inherit(self) -> None:
        twins = {twin.variable: twin for twin in setup_environment.ENV_TWINS}
        twin = twins['CLAUDE_CODE_TOOLBOX_REMOVE_LEFTOVERS']
        assert (twin.dest, twin.kind) == ('remove_leftovers', 'switch')
        assert 'CLAUDE_CODE_TOOLBOX_REMOVE_LEFTOVERS' not in setup_environment.CHILD_RUN_INHERITED_TWINS

    @pytest.mark.parametrize(('argv', 'env', 'expected'), [
        (['--remove-leftovers'], {}, True),
        ([], {'CLAUDE_CODE_TOOLBOX_REMOVE_LEFTOVERS': '1'}, True),
        ([], {'CLAUDE_CODE_TOOLBOX_REMOVE_LEFTOVERS': 'true'}, False),
        ([], {}, False),
    ])
    def test_cc_toolbox_setup_hands_the_flag_to_resolve_args(
        self, argv: list[str], env: dict[str, str], expected: bool, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from scripts import cli

        for name, value in env.items():
            monkeypatch.setenv(name, value)
        monkeypatch.setattr(sys, 'argv', ['cc-toolbox', 'setup', 'env.yaml', *argv])
        seen: list[bool] = []
        real_resolve = setup_environment.resolve_args

        def _resolve(args: argparse.Namespace) -> argparse.Namespace:
            resolved = real_resolve(args)
            seen.append(bool(resolved.remove_leftovers))
            raise SystemExit(0)

        with (
            patch.object(setup_environment, 'resolve_args', _resolve),
            patch.object(setup_environment, 'is_admin', return_value=False),
            pytest.raises(SystemExit),
        ):
            cli.main()

        assert seen == [expected]

    @pytest.mark.parametrize('wrapper', [
        'scripts/linux/setup-environment.sh', 'scripts/macos/setup-environment.sh',
    ])
    def test_bash_wrapper_headers_name_the_variable(self, wrapper: str) -> None:
        text = (REPO_ROOT / wrapper).read_text(encoding='utf-8')
        assert (
            '# To remove what earlier runs installed and the configuration no longer installs '
            '(same as --remove-leftovers):\n#   export CLAUDE_CODE_TOOLBOX_REMOVE_LEFTOVERS=1\n'
        ) in text

    def test_powershell_wrapper_header_names_the_variable(self) -> None:
        text = (REPO_ROOT / 'scripts/windows/setup-environment.ps1').read_text(encoding='utf-8')
        assert (
            '    To remove what earlier runs installed and the configuration no longer installs '
            "(same as --remove-leftovers):\n      $env:CLAUDE_CODE_TOOLBOX_REMOVE_LEFTOVERS='1'\n"
        ) in text


def _hooks_settings(event: str, hook: dict[str, object]) -> dict[str, object]:
    return {'hooks': {event: [{'matcher': '*', 'hooks': [hook]}]}}


def _wiring(profile_dir: Path, name: str, event: str = 'Stop') -> dict[str, object]:
    """A settings file whose one hook runs hooks/NAME of the profile through uv, as the setup spells it."""
    return _hooks_settings(event, {'type': 'command', 'command': f'uv run "{(profile_dir / "hooks" / name).as_posix()}"'})


class TestHookFileReferences:
    """A hook file is wired while a settings file a session reads names it in a hook or the status line."""

    def test_shell_form_command(self, layout: tuple[Path, Path]) -> None:
        _claude_dir, profile_dir = layout
        settings = profile_dir / 'settings.json'
        _write_json(settings, _wiring(profile_dir, 'a.py', 'PreToolUse'))

        detail = setup_environment._hook_file_references(
            'hooks/a.py', profile_dir=profile_dir, settings_files=[settings], dependents=[],
        )

        assert detail == f'still wired in {settings} hooks.PreToolUse'

    def test_exec_form_args_and_command(self, layout: tuple[Path, Path]) -> None:
        _claude_dir, profile_dir = layout
        settings = profile_dir / 'settings.json'
        _write_json(settings, {'hooks': {
            'Stop': [{'matcher': '', 'hooks': [
                {'type': 'command', 'command': 'uv', 'args': ['run', (profile_dir / 'hooks' / 'a.py').as_posix()]},
                {'type': 'command', 'command': (profile_dir / 'hooks' / 'run.sh').as_posix(), 'args': []},
            ]}],
        }})

        def _references(relative: str) -> str | None:
            return setup_environment._hook_file_references(
                relative, profile_dir=profile_dir, settings_files=[settings], dependents=[],
            )

        assert _references('hooks/a.py') == f'still wired in {settings} hooks.Stop'
        assert _references('hooks/run.sh') == f'still wired in {settings} hooks.Stop'
        assert _references('hooks/other.py') is None

    def test_status_line(self, layout: tuple[Path, Path]) -> None:
        _claude_dir, profile_dir = layout
        settings = profile_dir / 'settings.json'
        status = (profile_dir / 'hooks' / 'status.py').as_posix()
        _write_json(settings, {'statusLine': {'type': 'command', 'command': f'uv run "{status}"'}})

        detail = setup_environment._hook_file_references(
            'hooks/status.py', profile_dir=profile_dir, settings_files=[settings], dependents=[],
        )

        assert detail == f'still wired in {settings} statusLine'

    def test_a_longer_name_and_a_path_outside_hooks_are_not_references(self, layout: tuple[Path, Path]) -> None:
        _claude_dir, profile_dir = layout
        settings = profile_dir / 'settings.json'
        _write_json(settings, _wiring(profile_dir, 'a.py.bak'))

        def _references(relative: str) -> str | None:
            return setup_environment._hook_file_references(
                relative, profile_dir=profile_dir, settings_files=[settings], dependents=[],
            )

        assert _references('hooks/a.py') is None
        assert _references('rules/a.py.bak') is None, 'only files under hooks/ are wired'

    def test_absent_settings_files_wire_nothing(self, layout: tuple[Path, Path]) -> None:
        _claude_dir, profile_dir = layout
        assert setup_environment._hook_file_references(
            'hooks/a.py', profile_dir=profile_dir, settings_files=[profile_dir / 'settings.json'], dependents=[],
        ) is None

    def test_an_unreadable_settings_file_cannot_be_checked(self, layout: tuple[Path, Path]) -> None:
        _claude_dir, profile_dir = layout
        settings = profile_dir / 'settings.json'
        settings.write_text('{not json', encoding='utf-8')
        with pytest.raises(LeftoverReadError, match='settings.json'):
            setup_environment._hook_file_references(
                'hooks/a.py', profile_dir=profile_dir, settings_files=[settings], dependents=[],
            )

    def test_a_dependent_linking_hooks_wires_its_own_spelling(self, layout: tuple[Path, Path]) -> None:
        claude_dir, profile_dir = layout
        lab, docs = claude_dir / 'lab', claude_dir / 'docs'
        _write_json(lab / 'config.json', _wiring(lab, 'a.py', 'UserPromptSubmit'))
        _write_json(docs / 'config.json', _wiring(docs, 'a.py'))
        dependents = [
            InstalledProfile('docs', docs, docs / 'manifest.json', {'link': {'dirs': ['rules'], 'source': 'p'}}),
            InstalledProfile('lab', lab, lab / 'manifest.json', {'link': {'dirs': ['hooks', 'rules'], 'source': 'p'}}),
        ]

        detail = setup_environment._hook_file_references(
            'hooks/a.py', profile_dir=profile_dir, settings_files=[], dependents=dependents,
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
        assert setup_environment._text_names_path(text, 'C:/Users/Me/.claude/hooks/a.py', windows=windows) is expected


class TestComputeWithHookReferences:
    """A wired hook file is kept, and every other leftover under hooks/ stays with it."""

    def test_wired_script_holds_its_helpers(self, layout: tuple[Path, Path]) -> None:
        claude_dir, profile_dir = layout
        script = _write(profile_dir / 'hooks' / 'a.py', b'import helper')
        helper = _write(profile_dir / 'hooks' / 'helper.py', b'helper')
        rule = _write(profile_dir / 'rules' / 'old.md', b'rule')
        settings = profile_dir / 'settings.json'
        _write_json(settings, _wiring(profile_dir, 'a.py', 'PreToolUse'))
        manifest: dict[str, object] = {'files_written': [
            {'path': 'hooks/a.py', 'sha256': script},
            {'path': 'hooks/helper.py', 'sha256': helper},
            {'path': 'rules/old.md', 'sha256': rule},
        ]}

        report = setup_environment.compute_profile_leftovers(
            manifest, profile_dir, profile_name='p', planned=PlannedRecords(),
            live=_live(profile_dir, settings_files=(settings,)), claude_dir=claude_dir,
        )

        assert [(entry.item.path, entry.state, entry.detail) for entry in report.entries] == [
            ('hooks/a.py', 'referenced', f'still wired in {settings} hooks.PreToolUse'),
            ('hooks/helper.py', 'held', 'stays with hooks/a.py, which is still wired'),
            ('rules/old.md', 'removable', ''),
        ]
        assert [item.path for item in report.carried()] == ['hooks/a.py', 'hooks/helper.py', 'rules/old.md']

    def test_a_hand_edited_script_that_is_still_wired_holds_the_helpers(self, layout: tuple[Path, Path]) -> None:
        """An edited script is left in place, and while a settings file runs it, it may still import the helpers."""
        claude_dir, profile_dir = layout
        _write(profile_dir / 'hooks' / 'a.py', b'edited by hand')
        helper = _write(profile_dir / 'hooks' / 'helper.py', b'helper')
        settings = profile_dir / 'settings.json'
        manifest: dict[str, object] = {'files_written': [
            {'path': 'hooks/a.py', 'sha256': _sha(b'as written')},
            {'path': 'hooks/helper.py', 'sha256': helper},
        ]}

        def _states() -> list[tuple[str, str]]:
            report = setup_environment.compute_profile_leftovers(
                manifest, profile_dir, profile_name='p', planned=PlannedRecords(),
                live=_live(profile_dir, settings_files=(settings,)), claude_dir=claude_dir,
            )
            return [(entry.item.path, entry.state) for entry in report.entries]

        assert _states() == [('hooks/a.py', 'changed'), ('hooks/helper.py', 'removable')], 'nothing wires it yet'
        _write_json(settings, _wiring(profile_dir, 'a.py'))
        assert _states() == [('hooks/a.py', 'changed'), ('hooks/helper.py', 'held')]

    def test_the_own_config_json_is_not_read_before_consent(self, layout: tuple[Path, Path]) -> None:
        """Step 18 rebuilds an isolated profile's config.json, so the summary does not count its wiring."""
        claude_dir, profile_dir = layout
        script = _write(profile_dir / 'hooks' / 'old.py', b'old')
        _write_json(profile_dir / 'config.json', _wiring(profile_dir, 'old.py'))
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


class TestRunLeftoversStep:
    """Step 23 derives each state again, removes what still holds what the setup wrote, and records the outcome."""

    def test_nothing_runs_without_the_flag(self, layout: tuple[Path, Path]) -> None:
        claude_dir, profile_dir = layout
        digest = _write(profile_dir / 'rules' / 'old.md', b'old')
        report = _report(profile_dir, _removable('rules/old.md', digest))
        assert _step(report, live=_live(profile_dir), claude_dir=claude_dir, profile_dir=profile_dir, remove=False) is None
        assert _step(None, live=_live(profile_dir), claude_dir=claude_dir, profile_dir=profile_dir) is None
        assert (profile_dir / 'rules' / 'old.md').is_file()

    def test_nothing_runs_without_anything_to_look_at(self, layout: tuple[Path, Path]) -> None:
        """A flagged run with no carried leftover has no Step 23 part."""
        claude_dir, profile_dir = layout
        gone = _report(profile_dir, LeftoverEntry(LeftoverItem('file', 'rules/gone.md', 'a'), 'gone', ''))
        assert not setup_environment.leftovers_step_runs(gone, remove=True)
        assert _step(
            gone, live=_live(profile_dir), claude_dir=claude_dir, profile_dir=profile_dir, download_failed=True,
        ) is None, 'a download failure records no skip when there is nothing to remove'
        assert setup_environment.step_23_heading(deselection=False, leftovers=False) is None
        assert setup_environment.step_23_heading(deselection=True, leftovers=True) == (
            'Step 23: Removing deselected components and leftovers...'
        )
        assert setup_environment.step_23_heading(deselection=False, leftovers=True) == 'Step 23: Removing leftovers...'

    def test_removes_files_and_destinations_and_prunes_emptied_skill_directories(
        self, layout: tuple[Path, Path],
    ) -> None:
        claude_dir, profile_dir = layout
        rule = _write(profile_dir / 'rules' / 'old.md', b'old')
        skill = _write(profile_dir / 'skills' / 'gone-skill' / 'main.md', b'skill')
        kept_skill = _write(profile_dir / 'skills' / 'kept-skill' / 'a.md', b'a')
        _write(profile_dir / 'skills' / 'kept-skill' / 'b.md', b'b')
        outside = claude_dir.parent / 'out' / 'tool.txt'
        tool = _write(outside, b'tool')
        report = _report(
            profile_dir,
            _removable('rules/old.md', rule),
            _removable('skills/gone-skill/main.md', skill),
            _removable('skills/kept-skill/a.md', kept_skill),
            _removable(str(outside), tool, 'destination'),
        )

        removal = _step(report, live=_live(profile_dir), claude_dir=claude_dir, profile_dir=profile_dir)

        assert _results(removal) == {
            'rules/old.md': 'removed', 'skills/gone-skill/main.md': 'removed',
            'skills/kept-skill/a.md': 'removed', str(outside): 'removed',
        }
        assert not (profile_dir / 'rules' / 'old.md').exists()
        assert not outside.exists()
        assert not (profile_dir / 'skills' / 'gone-skill').exists(), 'an emptied skill directory is pruned'
        assert (profile_dir / 'skills' / 'kept-skill' / 'b.md').is_file()
        assert (profile_dir / 'skills').is_dir()

    def test_every_state_is_derived_again_before_a_removal(self, layout: tuple[Path, Path]) -> None:
        """What changed between the summary and Step 23 decides: a new link, a new holder, an edit, a removal."""
        claude_dir, profile_dir = layout
        linked = _write(profile_dir / 'agents' / 'old.md', b'agent')
        held_path = claude_dir.parent / 'out' / 'held.txt'
        held = _write(held_path, b'held')
        edited = _write(profile_dir / 'rules' / 'edited.md', b'as written')
        (profile_dir / 'rules' / 'edited.md').write_bytes(b'edited after the summary')
        gone = _write(profile_dir / 'rules' / 'gone.md', b'gone')
        (profile_dir / 'rules' / 'gone.md').unlink()
        report = _report(
            profile_dir,
            _removable('agents/old.md', linked),
            _removable('rules/edited.md', edited),
            _removable('rules/gone.md', gone),
            _removable(str(held_path), held, 'destination'),
        )
        live = _live(profile_dir, linked=frozenset({'agents'}), holders={str(held_path): ['other']})

        removal = _step(report, live=live, claude_dir=claude_dir, profile_dir=profile_dir)

        assert removal is not None
        assert [(o.entry.item.path, o.result, o.detail) for o in removal.outcomes] == [
            ('agents/old.md', 'dropped', 'linked'),
            ('rules/edited.md', 'dropped', 'changed'),
            ('rules/gone.md', 'dropped', 'gone'),
            (str(held_path), 'kept', 'recorded by profile other'),
        ]
        assert (profile_dir / 'agents' / 'old.md').is_file()
        assert held_path.is_file()

    def test_a_wired_hook_file_and_its_helpers_are_kept(self, layout: tuple[Path, Path]) -> None:
        claude_dir, profile_dir = layout
        script = _write(profile_dir / 'hooks' / 'a.py', b'import helper')
        helper = _write(profile_dir / 'hooks' / 'helper.py', b'helper')
        settings = profile_dir / 'config.json'
        _write_json(settings, _wiring(profile_dir, 'a.py'))
        report = _report(profile_dir, _removable('hooks/a.py', script), _removable('hooks/helper.py', helper))

        removal = _step(
            report, live=_live(profile_dir, settings_files=(settings,)), claude_dir=claude_dir, profile_dir=profile_dir,
        )

        assert _results(removal) == {'hooks/a.py': 'kept', 'hooks/helper.py': 'kept'}
        assert (profile_dir / 'hooks' / 'a.py').is_file()
        assert (profile_dir / 'hooks' / 'helper.py').is_file()

    def test_a_file_this_run_wrote_again_is_dropped_before_anything_is_removed(
        self, layout: tuple[Path, Path],
    ) -> None:
        claude_dir, profile_dir = layout
        digest = _write(profile_dir / 'rules' / 'again.md', b'again')
        report = _report(profile_dir, _removable('rules/again.md', digest))

        removal = _step(
            report, live=_live(profile_dir), claude_dir=claude_dir, profile_dir=profile_dir,
            written=PlannedRecords(files=frozenset({'rules/again.md'})),
        )

        assert removal is not None
        assert [(o.result, o.detail) for o in removal.outcomes] == [('dropped', 'written again')]
        assert (profile_dir / 'rules' / 'again.md').is_file()

    def test_a_failed_removal_is_carried(self, layout: tuple[Path, Path]) -> None:
        claude_dir, profile_dir = layout
        digest = _write(profile_dir / 'rules' / 'old.md', b'old')
        report = _report(profile_dir, _removable('rules/old.md', digest))

        with patch.object(Path, 'unlink', side_effect=PermissionError(13, 'Permission denied')):
            removal = _step(report, live=_live(profile_dir), claude_dir=claude_dir, profile_dir=profile_dir)

        assert removal is not None
        assert [(o.result, o.detail) for o in removal.failed()] == [('failed', 'Permission denied')]
        record = setup_environment.leftovers_manifest_record(report, run_at='t', removal=removal)
        assert record['items'] == [{'kind': 'file', 'path': 'rules/old.md', 'sha256': digest}]
        assert record['failed'] == ['file: rules/old.md']
        assert record['removed'] == []

    def test_a_content_download_failure_skips_every_removal(self, layout: tuple[Path, Path]) -> None:
        claude_dir, profile_dir = layout
        digest = _write(profile_dir / 'rules' / 'old.md', b'old')
        report = _report(profile_dir, _removable('rules/old.md', digest))

        removal = _step(
            report, live=_live(profile_dir), claude_dir=claude_dir, profile_dir=profile_dir, download_failed=True,
        )

        assert removal == LeftoverRemoval(outcomes=(), skipped='content downloads failed')
        assert (profile_dir / 'rules' / 'old.md').is_file()
        record = setup_environment.leftovers_manifest_record(report, run_at='t', removal=removal)
        assert record['skipped'] == 'content downloads failed'
        assert record['items'] == [{'kind': 'file', 'path': 'rules/old.md', 'sha256': digest}]

    def test_the_outcome_replaces_the_record_step_20_wrote(self, layout: tuple[Path, Path]) -> None:
        claude_dir, profile_dir = layout
        rule = _write(profile_dir / 'rules' / 'old.md', b'old')
        _write_json(profile_dir / 'manifest.json', {'name': 'p', 'leftovers': {'items': ['step 20']}})
        report = _report(profile_dir, _removable('rules/old.md', rule))

        with patch.object(setup_environment, '_record_manifest_leftovers', _REAL_RECORD_MANIFEST_LEFTOVERS):
            _step(report, live=_live(profile_dir), claude_dir=claude_dir, profile_dir=profile_dir)

        manifest = json.loads((profile_dir / 'manifest.json').read_text(encoding='utf-8'))
        assert manifest['name'] == 'p'
        assert manifest['leftovers'] == {
            'run_at': 't', 'items': [], 'removed': ['file: rules/old.md'], 'dropped': [], 'skipped': None, 'failed': [],
            'kept': [],
        }

    def test_record_manifest_leftovers_needs_a_readable_manifest(self, tmp_path: Path) -> None:
        assert not _REAL_RECORD_MANIFEST_LEFTOVERS(tmp_path / 'manifest.json', {'items': []})
        (tmp_path / 'manifest.json').write_text('[]', encoding='utf-8')
        assert not _REAL_RECORD_MANIFEST_LEFTOVERS(tmp_path / 'manifest.json', {'items': []})


class TestStep23AfterTheSummary:
    """Step 23 looks at the links and the files this run wrote as they are when it removes, not as the summary saw them."""

    def _report(self, claude_dir: Path, profile_dir: Path) -> LeftoverReport:
        rule = _write(profile_dir / 'rules' / 'old.md', b'old')
        agent = _write(profile_dir / 'agents' / 'old.md', b'agent')
        manifest: dict[str, object] = {'files_written': [
            {'path': 'rules/old.md', 'sha256': rule}, {'path': 'agents/old.md', 'sha256': agent},
        ]}
        return setup_environment.compute_profile_leftovers(
            manifest, profile_dir, profile_name='p', planned=PlannedRecords(), live=_live(profile_dir),
            claude_dir=claude_dir,
        )

    def test_a_file_under_a_link_this_run_made_is_dropped_not_failed(self, layout: tuple[Path, Path]) -> None:
        claude_dir, profile_dir = layout
        report = self._report(claude_dir, profile_dir)
        source = claude_dir / 'src'
        _write(source / 'rules' / 'old.md', b'old')
        (profile_dir / 'rules' / 'old.md').unlink()
        (profile_dir / 'rules').rmdir()
        setup_environment.link_profile_directory(profile_dir / 'rules', source / 'rules')

        removal = _step(
            report, live=LiveLeftoverState.for_profile(profile_dir, claude_dir.parent), claude_dir=claude_dir,
            profile_dir=profile_dir,
        )

        assert removal is not None
        assert ('rules/old.md', 'dropped', 'linked') in [
            (o.entry.item.path, o.result, o.detail) for o in removal.outcomes
        ]
        assert (source / 'rules' / 'old.md').is_file(), "the source's file of the same name stays"
        assert not (profile_dir / 'agents' / 'old.md').exists()
        assert not removal.failed()

    def test_a_path_this_run_wrote_in_another_letter_case_is_never_removed(self, layout: tuple[Path, Path]) -> None:
        """A recorded spelling that differs only in letter case names the file this run installed."""
        claude_dir, profile_dir = layout
        report = self._report(claude_dir, profile_dir)

        removal = _step(
            report, live=_live(profile_dir), claude_dir=claude_dir, profile_dir=profile_dir,
            written=PlannedRecords(files=frozenset({'Rules/Old.md'})),
        )

        assert _results(removal) == {'agents/old.md': 'removed', 'rules/old.md': 'dropped'}
        assert (profile_dir / 'rules' / 'old.md').is_file()


class TestReportRendering:
    """The summary rows and footers say what the run does with each leftover, and name the flag."""

    def _report(self, profile_dir: Path) -> LeftoverReport:
        return _report(
            profile_dir,
            _removable('rules/old.md', 'a'),
            LeftoverEntry(LeftoverItem('file', 'hooks/a.py', 'b'), 'referenced', 'still wired in s.json hooks.Stop'),
            LeftoverEntry(LeftoverItem('file', 'hooks/h.py', 'c'), 'held', 'stays with hooks/a.py, which is still wired'),
            LeftoverEntry(LeftoverItem('file', 'rules/gone.md', 'd'), 'gone', ''),
        )

    def test_without_the_flag(self, tmp_path: Path) -> None:
        assert self._report(tmp_path).lines(remove=False, dry_run=False) == [
            f'[leftover] file: {tmp_path / "rules" / "old.md"}',
            f'[kept: still wired in s.json hooks.Stop] file: {tmp_path / "hooks" / "a.py"}',
            f'[kept: stays with hooks/a.py, which is still wired] file: {tmp_path / "hooks" / "h.py"}',
            f'[already gone: no longer tracked] file: {tmp_path / "rules" / "gone.md"}',
            'They stay in place.',
            (
                'Pass --remove-leftovers (or set CLAUDE_CODE_TOOLBOX_REMOVE_LEFTOVERS=1) to remove the items marked '
                '[leftover]; each is removed only while it still holds what the setup wrote.'
            ),
        ]

    def test_with_the_flag(self, tmp_path: Path) -> None:
        lines = self._report(tmp_path).lines(remove=True, dry_run=False)
        assert lines[0] == f'[remove] file: {tmp_path / "rules" / "old.md"}'
        assert lines[-1] == (
            'Step 23 removes each item marked [remove] only while it still holds what the setup wrote; '
            'the others stay in place.'
        )

    def test_with_the_flag_under_dry_run(self, tmp_path: Path) -> None:
        lines = self._report(tmp_path).lines(remove=True, dry_run=True)
        assert lines[0] == f'[would be removed in Step 23] file: {tmp_path / "rules" / "old.md"}'
        assert lines[-1] == (
            'Step 23 removes each item marked [would be removed in Step 23] only while it still holds what the '
            'setup wrote; the others stay in place.'
        )

    def test_nothing_to_remove_names_no_flag(self, tmp_path: Path) -> None:
        report = _report(tmp_path, LeftoverEntry(LeftoverItem('file', 'hooks/a.py', 'b'), 'referenced', 'wired'))
        assert report.lines(remove=False, dry_run=False)[-1] == 'They stay in place.'
        assert report.lines(remove=True, dry_run=False)[-1] == 'They stay in place.'

    def test_the_summary_renders_the_runs_decision(self, tmp_path: Path) -> None:
        plan = setup_environment.InstallationPlan(
            config_name='P', config_source='p.yaml', config_source_type='local', config_version=None,
            leftovers=self._report(tmp_path), remove_leftovers=True, dry_run=True,
        )
        buffer = io.StringIO()
        setup_environment.display_installation_summary(plan, output=buffer)
        assert f'  [would be removed in Step 23] file: {tmp_path / "rules" / "old.md"}' in buffer.getvalue()

    def test_completion_without_the_flag_names_it(self, tmp_path: Path) -> None:
        sections = self._report(tmp_path).completion_sections(None)
        assert sections[0][0] == 'Leftovers left in place (3; --remove-leftovers removes them):'

    def test_completion_after_removal(self, tmp_path: Path) -> None:
        report = self._report(tmp_path)
        entries = report.entries
        removal = LeftoverRemoval(outcomes=(
            LeftoverOutcome(entries[0], 'removed'),
            LeftoverOutcome(entries[1], 'kept', entries[1].detail),
            LeftoverOutcome(entries[2], 'kept', entries[2].detail),
            LeftoverOutcome(entries[3], 'dropped', 'gone'),
        ))
        assert report.completion_sections(removal) == [
            ('Leftovers removed (1):', [f'file: {tmp_path / "rules" / "old.md"}']),
            ('Leftovers left in place (2):', [
                f'file: {tmp_path / "hooks" / "a.py"} (kept: still wired in s.json hooks.Stop)',
                f'file: {tmp_path / "hooks" / "h.py"} (kept: stays with hooks/a.py, which is still wired)',
            ]),
            ('No longer tracked:', [f'file: {tmp_path / "rules" / "gone.md"} (already gone)']),
        ]

    def test_manifest_record_after_removal(self, tmp_path: Path) -> None:
        report = self._report(tmp_path)
        entries = report.entries
        removal = LeftoverRemoval(outcomes=(
            LeftoverOutcome(entries[0], 'removed'),
            LeftoverOutcome(entries[1], 'kept', entries[1].detail),
            LeftoverOutcome(entries[2], 'failed', 'Permission denied'),
            LeftoverOutcome(entries[3], 'dropped', 'written again'),
        ))
        assert setup_environment.leftovers_manifest_record(report, run_at='t', removal=removal) == {
            'run_at': 't',
            'items': [
                {'kind': 'file', 'path': 'hooks/a.py', 'sha256': 'b'},
                {'kind': 'file', 'path': 'hooks/h.py', 'sha256': 'c'},
            ],
            'removed': ['file: rules/old.md'],
            'dropped': [{'label': 'file: rules/gone.md', 'reason': 'written again'}],
            'skipped': None,
            'failed': ['file: hooks/h.py'],
            'kept': [{'label': 'file: hooks/a.py', 'reason': 'kept: still wired in s.json hooks.Stop'}],
        }


class TestMachineWideRows:
    """An isolated run given the flag names each destination outside ~/.claude it removes."""

    def test_removable_destinations_are_machine_wide_writes(self, tmp_path: Path) -> None:
        rows = setup_environment.collect_machine_wide_writes(
            profile_dir=tmp_path / 'p', command_names=['p'], skip_install=True, install_version=None,
            keep_installed=False, pinned_version=None, ide_clis=[], os_level_env={}, mcp_servers=[],
            files_to_download=[], has_dependency_commands=False,
            leftover_destinations=[str(tmp_path / 'out' / 'tool.txt')],
        )
        assert f'remove leftover file: {tmp_path / "out" / "tool.txt"}' in rows

    def test_the_report_names_only_removable_destinations(self, tmp_path: Path) -> None:
        outside, held = str(tmp_path / 'out' / 'tool.txt'), str(tmp_path / 'out' / 'held.txt')
        report = _report(
            tmp_path / 'p',
            _removable('rules/old.md', 'a'),
            _removable(outside, 'b', 'destination'),
            LeftoverEntry(LeftoverItem('destination', held, 'c'), 'held', 'recorded by profile other'),
        )
        assert report.removable_destinations() == [outside]
