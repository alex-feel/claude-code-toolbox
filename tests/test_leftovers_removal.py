"""Tests for the removal of leftovers: --remove-leftovers and the Step 23 remover.

A run given --remove-leftovers (or CLAUDE_CODE_TOOLBOX_REMOVE_LEFTOVERS=1)
removes in Step 23 each leftover that still holds what the setup wrote. Step
23 derives every state again from what is on disk then, a wired hook file and
the dropped helpers it may import included (tests/test_leftovers_hook_references.py
covers that check), records each outcome in the manifest, and a removal that
fails keeps the item recorded and ends the run with exit code 1.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import setup_environment
from scripts.setup_environment import LeftoverEntry
from scripts.setup_environment import LeftoverItem
from scripts.setup_environment import LeftoverOutcome
from scripts.setup_environment import LeftoverRemoval
from scripts.setup_environment import LeftoverReport
from scripts.setup_environment import LiveLeftoverState
from scripts.setup_environment import PlannedRecords
from tests.leftovers_unit_support import helper_entry
from tests.leftovers_unit_support import live_state
from tests.leftovers_unit_support import sha
from tests.leftovers_unit_support import wiring
from tests.leftovers_unit_support import write
from tests.leftovers_unit_support import write_json

_REAL_RECORD_MANIFEST_LEFTOVERS = setup_environment._record_manifest_leftovers
REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def layout(tmp_path: Path) -> tuple[Path, Path]:
    """The ~/.claude directory and an isolated profile directory inside it."""
    claude_dir = tmp_path / '.claude'
    profile_dir = claude_dir / 'p'
    profile_dir.mkdir(parents=True)
    return claude_dir, profile_dir


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


class TestRunLeftoversStep:
    """Step 23 derives each state again, removes what still holds what the setup wrote, and records the outcome."""

    def test_nothing_runs_without_the_flag(self, layout: tuple[Path, Path]) -> None:
        claude_dir, profile_dir = layout
        digest = write(profile_dir / 'rules' / 'old.md', b'old')
        report = _report(profile_dir, _removable('rules/old.md', digest))
        live = live_state(profile_dir)
        assert _step(report, live=live, claude_dir=claude_dir, profile_dir=profile_dir, remove=False) is None
        assert _step(None, live=live_state(profile_dir), claude_dir=claude_dir, profile_dir=profile_dir) is None
        assert (profile_dir / 'rules' / 'old.md').is_file()

    def test_nothing_runs_without_anything_to_look_at(self, layout: tuple[Path, Path]) -> None:
        """A flagged run with no carried leftover has no Step 23 part."""
        claude_dir, profile_dir = layout
        gone = _report(profile_dir, LeftoverEntry(LeftoverItem('file', 'rules/gone.md', 'a'), 'gone', ''))
        assert not setup_environment.leftovers_step_runs(gone, remove=True)
        assert _step(
            gone, live=live_state(profile_dir), claude_dir=claude_dir, profile_dir=profile_dir, download_failed=True,
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
        rule = write(profile_dir / 'rules' / 'old.md', b'old')
        skill = write(profile_dir / 'skills' / 'gone-skill' / 'main.md', b'skill')
        kept_skill = write(profile_dir / 'skills' / 'kept-skill' / 'a.md', b'a')
        write(profile_dir / 'skills' / 'kept-skill' / 'b.md', b'b')
        outside = claude_dir.parent / 'out' / 'tool.txt'
        tool = write(outside, b'tool')
        report = _report(
            profile_dir,
            _removable('rules/old.md', rule),
            _removable('skills/gone-skill/main.md', skill),
            _removable('skills/kept-skill/a.md', kept_skill),
            _removable(str(outside), tool, 'destination'),
        )

        removal = _step(report, live=live_state(profile_dir), claude_dir=claude_dir, profile_dir=profile_dir)

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
        linked = write(profile_dir / 'agents' / 'old.md', b'agent')
        held_path = claude_dir.parent / 'out' / 'held.txt'
        held = write(held_path, b'held')
        edited = write(profile_dir / 'rules' / 'edited.md', b'as written')
        (profile_dir / 'rules' / 'edited.md').write_bytes(b'edited after the summary')
        gone = write(profile_dir / 'rules' / 'gone.md', b'gone')
        (profile_dir / 'rules' / 'gone.md').unlink()
        report = _report(
            profile_dir,
            _removable('agents/old.md', linked),
            _removable('rules/edited.md', edited),
            _removable('rules/gone.md', gone),
            _removable(str(held_path), held, 'destination'),
        )
        live = live_state(profile_dir, linked=frozenset({'agents'}), holders={str(held_path): ['other']})

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

    def test_a_wired_hook_file_and_the_helpers_are_kept(self, layout: tuple[Path, Path]) -> None:
        claude_dir, profile_dir = layout
        script = write(profile_dir / 'hooks' / 'a.py', b'import helper')
        helper = write(profile_dir / 'hooks' / 'helper.py', b'helper')
        settings = profile_dir / 'config.json'
        write_json(settings, wiring(profile_dir, 'a.py'))
        report = _report(profile_dir, _removable('hooks/a.py', script), helper_entry('hooks/helper.py', helper))

        removal = _step(
            report, live=live_state(profile_dir, settings_files=(settings,)), claude_dir=claude_dir, profile_dir=profile_dir,
        )

        assert _results(removal) == {'hooks/a.py': 'kept', 'hooks/helper.py': 'kept'}
        assert (profile_dir / 'hooks' / 'a.py').is_file()
        assert (profile_dir / 'hooks' / 'helper.py').is_file()

    def test_a_helper_is_kept_in_step_23_while_a_script_edited_by_hand_is_wired(
        self, layout: tuple[Path, Path],
    ) -> None:
        """The edited script is reported once and no longer tracked; Step 23 still keeps the helper it may import."""
        claude_dir, profile_dir = layout
        write(profile_dir / 'hooks' / 'a.py', b'edited by hand')
        helper = write(profile_dir / 'hooks' / 'helper.py', b'helper')
        settings = profile_dir / 'settings.json'
        write_json(settings, wiring(profile_dir, 'a.py'))
        live = live_state(profile_dir, settings_files=(settings,))
        manifest: dict[str, object] = {'files_written': [
            {'path': 'hooks/a.py', 'sha256': sha(b'as written')},
            {'path': 'hooks/helper.py', 'sha256': helper, 'hook_helper': True},
        ]}
        report = setup_environment.compute_profile_leftovers(
            manifest, profile_dir, profile_name='p', planned=PlannedRecords(), live=live, claude_dir=claude_dir,
        )
        assert [(entry.item.path, entry.state) for entry in report.entries] == [
            ('hooks/a.py', 'changed'), ('hooks/helper.py', 'held'),
        ]

        removal = _step(report, live=live, claude_dir=claude_dir, profile_dir=profile_dir)

        assert _results(removal) == {'hooks/helper.py': 'kept'}
        assert (profile_dir / 'hooks' / 'helper.py').is_file()

    def test_a_helper_leaves_in_step_23_once_nothing_in_the_folder_is_wired(self, layout: tuple[Path, Path]) -> None:
        claude_dir, profile_dir = layout
        helper = write(profile_dir / 'hooks' / 'helper.py', b'helper')
        write(profile_dir / 'hooks' / 'kept.py', b'unwired')
        report = _report(profile_dir, helper_entry('hooks/helper.py', helper))

        removal = _step(report, live=live_state(profile_dir), claude_dir=claude_dir, profile_dir=profile_dir)

        assert _results(removal) == {'hooks/helper.py': 'removed'}
        assert not (profile_dir / 'hooks' / 'helper.py').exists()

    def test_a_helper_leaves_in_step_23_while_only_the_scripts_this_run_wrote_are_wired(
        self, layout: tuple[Path, Path],
    ) -> None:
        """The configuration's own script, which Step 17 wrote as the configuration ships it, imports no dropped helper."""
        claude_dir, profile_dir = layout
        helper = write(profile_dir / 'hooks' / 'helper.py', b'helper')
        write(profile_dir / 'hooks' / 'b.py', b'new')
        settings = profile_dir / 'config.json'
        write_json(settings, wiring(profile_dir, 'b.py'))
        report = _report(profile_dir, helper_entry('hooks/helper.py', helper))

        removal = _step(
            report, live=live_state(profile_dir, settings_files=(settings,)), claude_dir=claude_dir, profile_dir=profile_dir,
            written=PlannedRecords(files=frozenset({'hooks/b.py'})),
        )

        assert _results(removal) == {'hooks/helper.py': 'removed'}
        assert not (profile_dir / 'hooks' / 'helper.py').exists()
        assert (profile_dir / 'hooks' / 'b.py').is_file()

    def test_a_file_this_run_wrote_again_is_dropped_before_anything_is_removed(
        self, layout: tuple[Path, Path],
    ) -> None:
        claude_dir, profile_dir = layout
        digest = write(profile_dir / 'rules' / 'again.md', b'again')
        report = _report(profile_dir, _removable('rules/again.md', digest))

        removal = _step(
            report, live=live_state(profile_dir), claude_dir=claude_dir, profile_dir=profile_dir,
            written=PlannedRecords(files=frozenset({'rules/again.md'})),
        )

        assert removal is not None
        assert [(o.result, o.detail) for o in removal.outcomes] == [('dropped', 'written again')]
        assert (profile_dir / 'rules' / 'again.md').is_file()

    def test_a_failed_removal_is_carried(self, layout: tuple[Path, Path]) -> None:
        claude_dir, profile_dir = layout
        digest = write(profile_dir / 'rules' / 'old.md', b'old')
        report = _report(profile_dir, _removable('rules/old.md', digest))

        with patch.object(Path, 'unlink', side_effect=PermissionError(13, 'Permission denied')):
            removal = _step(report, live=live_state(profile_dir), claude_dir=claude_dir, profile_dir=profile_dir)

        assert removal is not None
        assert [(o.result, o.detail) for o in removal.failed()] == [('failed', 'Permission denied')]
        record = setup_environment.leftovers_manifest_record(report, run_at='t', removal=removal)
        assert record['items'] == [{'kind': 'file', 'path': 'rules/old.md', 'sha256': digest}]
        assert record['failed'] == ['file: rules/old.md']
        assert record['removed'] == []

    def test_a_content_download_failure_skips_every_removal(self, layout: tuple[Path, Path]) -> None:
        claude_dir, profile_dir = layout
        digest = write(profile_dir / 'rules' / 'old.md', b'old')
        report = _report(profile_dir, _removable('rules/old.md', digest))

        removal = _step(
            report, live=live_state(profile_dir), claude_dir=claude_dir, profile_dir=profile_dir, download_failed=True,
        )

        assert removal == LeftoverRemoval(outcomes=(), skipped='content downloads failed')
        assert (profile_dir / 'rules' / 'old.md').is_file()
        record = setup_environment.leftovers_manifest_record(report, run_at='t', removal=removal)
        assert record['skipped'] == 'content downloads failed'
        assert record['items'] == [{'kind': 'file', 'path': 'rules/old.md', 'sha256': digest}]

    def test_the_outcome_replaces_the_record_step_20_wrote(self, layout: tuple[Path, Path]) -> None:
        claude_dir, profile_dir = layout
        rule = write(profile_dir / 'rules' / 'old.md', b'old')
        write_json(profile_dir / 'manifest.json', {'name': 'p', 'leftovers': {'items': ['step 20']}})
        report = _report(profile_dir, _removable('rules/old.md', rule))

        with patch.object(setup_environment, '_record_manifest_leftovers', _REAL_RECORD_MANIFEST_LEFTOVERS):
            _step(report, live=live_state(profile_dir), claude_dir=claude_dir, profile_dir=profile_dir)

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
        rule = write(profile_dir / 'rules' / 'old.md', b'old')
        agent = write(profile_dir / 'agents' / 'old.md', b'agent')
        manifest: dict[str, object] = {'files_written': [
            {'path': 'rules/old.md', 'sha256': rule}, {'path': 'agents/old.md', 'sha256': agent},
        ]}
        return setup_environment.compute_profile_leftovers(
            manifest, profile_dir, profile_name='p', planned=PlannedRecords(), live=live_state(profile_dir),
            claude_dir=claude_dir,
        )

    def test_a_file_under_a_link_this_run_made_is_dropped_not_failed(self, layout: tuple[Path, Path]) -> None:
        claude_dir, profile_dir = layout
        report = self._report(claude_dir, profile_dir)
        source = claude_dir / 'src'
        write(source / 'rules' / 'old.md', b'old')
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
            report, live=live_state(profile_dir), claude_dir=claude_dir, profile_dir=profile_dir,
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
