"""Tests for the dependency entries: what the Step 6 dependency commands install into a profile's content directories.

Step 6 observes the top-level entries of every content directory of the
profile that is not linked, around each dependency command, and credits
each command with the entries it created or touched. The manifest records
them per command with the identity of each entry (file ID and birth time,
or inode change time where the platform carries no birth time). An entry
of an earlier run that no command credits any more, still holding its
recorded identity, is listed as a leftover after Step 6 and removed by a
later run given --remove-leftovers, never by the run that listed it.

Every test that needs a recreated entry builds the replacement in a sibling
directory outside the content directory while the old entry still exists,
then removes the old one and moves the replacement into place, so the two
entries differ by construction on every platform.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts import setup_environment
from scripts.setup_environment import DependencyEntryObserver
from scripts.setup_environment import DependencyRun
from scripts.setup_environment import LeftoverEntry
from scripts.setup_environment import LeftoverItem
from scripts.setup_environment import LeftoverReadError
from scripts.setup_environment import LeftoverRemoval
from scripts.setup_environment import LeftoverReport
from scripts.setup_environment import LiveLeftoverState
from scripts.setup_environment import PlannedRecords

# The conftest replaces the factory for main()-flow unit tests; these tests
# exercise the real one
_REAL_OBSERVER_FACTORY = setup_environment.dependency_entry_observer
_REAL_WRITE_MANIFEST = setup_environment.write_manifest

DEP = 'dependency-entry'
FLAG_NOTE = 'listed after Step 6 of this run; a later run with --remove-leftovers removes it'


def _skill(profile_dir: Path, name: str, content: str = 'skill') -> Path:
    """Create a skill directory with one file and return it."""
    entry = profile_dir / 'skills' / name
    entry.mkdir(parents=True)
    (entry / 'SKILL.md').write_text(content, encoding='utf-8')
    return entry


def _recreate(entry: Path, aside: Path, content: str = 'recreated') -> None:
    """Replace an entry with a new one built beside it while the old one still exists."""
    aside.mkdir(parents=True)
    (aside / 'SKILL.md').write_text(content, encoding='utf-8')
    if entry.is_dir():
        shutil.rmtree(entry)
    else:
        entry.unlink()
    aside.rename(entry)


def _identity(path: Path) -> str:
    identity = setup_environment.entry_identity(path)
    assert identity is not None
    return identity


def _item(path: str, identity: str, command: str = 'cmd') -> LeftoverItem:
    return LeftoverItem.dependency_entry(path, command, identity)


def _live(profile_dir: Path, *, linked: frozenset[str] = frozenset()) -> LiveLeftoverState:
    """A live state over the real file system, with the linked top-level entries given."""
    return LiveLeftoverState(
        file_digest=setup_environment._live_file_digest,
        under_link=lambda relative: relative.split('/')[0] in linked
        or setup_environment._under_directory_link(profile_dir, relative),
        destination_holders=lambda _dest: [],
        identity=setup_environment.entry_identity,
    )


def _report(profile_dir: Path, *entries: LeftoverEntry) -> LeftoverReport:
    return LeftoverReport(profile_name='p', profile_dir=profile_dir, entries=tuple(entries), untracked_note=False)


def _step(
    report: LeftoverReport,
    profile_dir: Path,
    *,
    live: LiveLeftoverState | None = None,
    written: PlannedRecords | None = None,
    failed_commands: frozenset[str] = frozenset(),
) -> LeftoverRemoval | None:
    return setup_environment.run_leftovers_step(
        report,
        remove=True,
        download_failed=False,
        written=written or PlannedRecords(),
        live=live or _live(profile_dir),
        profile_dir=profile_dir,
        claude_dir=profile_dir.parent,
        manifest_path=profile_dir / 'manifest.json',
        run_at='t',
        failed_commands=failed_commands,
    )


def _results(removal: LeftoverRemoval | None) -> dict[str, tuple[str, str]]:
    assert removal is not None
    return {outcome.entry.item.path: (outcome.result, outcome.detail) for outcome in removal.outcomes}


@pytest.fixture
def profile_dir(tmp_path: Path) -> Path:
    """An isolated profile directory inside a ~/.claude directory."""
    directory = tmp_path / '.claude' / 'p'
    directory.mkdir(parents=True)
    return directory


class TestEntryIdentity:
    """An entry's identity is its file ID and birth time, read without following a link."""

    def test_an_untouched_entry_keeps_its_identity(self, profile_dir: Path) -> None:
        entry = _skill(profile_dir, 's1')
        assert setup_environment.entry_identity(entry) == setup_environment.entry_identity(entry)

    def test_a_recreated_entry_has_another_identity(self, profile_dir: Path, tmp_path: Path) -> None:
        entry = _skill(profile_dir, 's1')
        before = _identity(entry)
        _recreate(entry, tmp_path / 'aside' / 's1')
        assert _identity(entry) != before

    def test_nothing_at_the_path_has_no_identity(self, profile_dir: Path) -> None:
        assert setup_environment.entry_identity(profile_dir / 'skills' / 'absent') is None

    def test_a_link_is_observed_as_itself(self, profile_dir: Path, tmp_path: Path) -> None:
        target = tmp_path / 'target'
        target.mkdir()
        link = profile_dir / 'skills' / 'linked'
        link.parent.mkdir(parents=True)
        setup_environment.link_profile_directory(link, target)
        assert _identity(link) != _identity(target)

    def test_an_unreadable_path_raises(self, profile_dir: Path) -> None:
        entry = _skill(profile_dir, 's1')
        with (
            patch.object(setup_environment.os, 'lstat', side_effect=PermissionError(13, 'Permission denied')),
            pytest.raises(LeftoverReadError, match='Permission denied'),
        ):
            setup_environment.entry_identity(entry)

    def test_the_identity_is_read_with_lstat(self, profile_dir: Path) -> None:
        entry = _skill(profile_dir, 's1')
        calls: list[str] = []
        real_lstat = os.lstat

        def _lstat(path: str | os.PathLike[str], *args: Any, **kwargs: Any) -> os.stat_result:
            calls.append(str(path))
            return real_lstat(path, *args, **kwargs)

        with patch.object(setup_environment.os, 'lstat', side_effect=_lstat):
            setup_environment.entry_identity(entry)
        assert calls == [str(entry)]


class TestEntryFingerprint:
    """A fingerprint tells whether one command touched an entry: its identity and what it directly holds."""

    def test_an_unchanged_directory_keeps_its_fingerprint(self, profile_dir: Path) -> None:
        entry = _skill(profile_dir, 's1')
        assert setup_environment.entry_fingerprint(entry) == setup_environment.entry_fingerprint(entry)

    def test_a_child_overwritten_in_place_changes_the_fingerprint_not_the_identity(self, profile_dir: Path) -> None:
        entry = _skill(profile_dir, 's1')
        identity, fingerprint = _identity(entry), setup_environment.entry_fingerprint(entry)
        (entry / 'SKILL.md').write_text('a longer body written in place', encoding='utf-8')
        assert setup_environment.entry_fingerprint(entry) != fingerprint
        assert _identity(entry) == identity

    def test_a_new_child_changes_the_fingerprint(self, profile_dir: Path) -> None:
        entry = _skill(profile_dir, 's1')
        fingerprint = setup_environment.entry_fingerprint(entry)
        (entry / 'extra.md').write_text('x', encoding='utf-8')
        assert setup_environment.entry_fingerprint(entry) != fingerprint

    def test_a_file_overwritten_in_place_changes_the_fingerprint(self, profile_dir: Path) -> None:
        entry = profile_dir / 'rules' / 'rule.md'
        entry.parent.mkdir(parents=True)
        entry.write_text('one', encoding='utf-8')
        fingerprint = setup_environment.entry_fingerprint(entry)
        entry.write_text('a different length', encoding='utf-8')
        assert setup_environment.entry_fingerprint(entry) != fingerprint

    def test_a_link_does_not_follow_its_target(self, profile_dir: Path, tmp_path: Path) -> None:
        target = tmp_path / 'target'
        target.mkdir()
        link = profile_dir / 'skills' / 'linked'
        link.parent.mkdir(parents=True)
        setup_environment.link_profile_directory(link, target)
        fingerprint = setup_environment.entry_fingerprint(link)
        (target / 'new.md').write_text('x', encoding='utf-8')
        assert setup_environment.entry_fingerprint(link) == fingerprint

    def test_nothing_at_the_path_has_no_fingerprint(self, profile_dir: Path) -> None:
        assert setup_environment.entry_fingerprint(profile_dir / 'skills' / 'absent') is None


class TestObserver:
    """The observer credits each command with the content entries it created or touched."""

    def test_around_records_created_and_touched_entries(self, profile_dir: Path, tmp_path: Path) -> None:
        kept = _skill(profile_dir, 'kept')
        recreated = _skill(profile_dir, 'recreated')
        deleted = _skill(profile_dir, 'deleted')
        observer = _REAL_OBSERVER_FACTORY(profile_dir, frozenset())

        def _command() -> bool:
            _recreate(recreated, tmp_path / 'aside' / 'recreated')
            shutil.rmtree(deleted)
            _skill(profile_dir, 'new')
            (profile_dir / 'agents').mkdir()
            (profile_dir / 'agents' / 'a.md').write_text('a', encoding='utf-8')
            return True

        assert observer.around('install', _command) is True
        assert observer.runs == [
            DependencyRun('install', True, created=('agents/a.md', 'skills/new'), touched=('skills/recreated',)),
        ]
        assert kept.exists()

    def test_around_passes_a_failure_through(self, profile_dir: Path) -> None:
        observer = _REAL_OBSERVER_FACTORY(profile_dir, frozenset())
        assert observer.around('broken', lambda: False) is False
        assert observer.runs == [DependencyRun('broken', False)]

    @pytest.mark.parametrize('linked_entries', [frozenset({'skills'}), frozenset()], ids=['this-run', 'on-disk'])
    def test_a_linked_content_directory_is_never_observed(
        self, profile_dir: Path, tmp_path: Path, linked_entries: frozenset[str],
    ) -> None:
        source_skills = tmp_path / 'source' / 'skills'
        setup_environment.link_profile_directory(profile_dir / 'skills', source_skills)
        rules = profile_dir / 'rules'
        rules.mkdir()
        observer = _REAL_OBSERVER_FACTORY(profile_dir, linked_entries)

        def _command() -> bool:
            (source_skills / 'through-link').mkdir()
            (rules / 'rule.md').write_text('r', encoding='utf-8')
            return True

        observer.around('install', _command)
        assert observer.runs == [DependencyRun('install', True, created=('rules/rule.md',))]

    def test_install_dependencies_runs_every_command_through_the_observer(self, profile_dir: Path) -> None:
        observer = _REAL_OBSERVER_FACTORY(profile_dir, frozenset())
        made: list[str] = []

        def _run(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
            name = 'one' if 'one' in argv[-1] else 'two'
            _skill(profile_dir, name)
            made.append(name)
            return subprocess.CompletedProcess(argv, 0 if name == 'one' else 1, '', '')

        with patch.object(setup_environment, 'run_command', side_effect=_run):
            failed = setup_environment.install_dependencies(
                {'common': ['make-one --now', 'make-two --now']}, observer=observer,
            )

        assert made == ['one', 'two']
        assert failed == ['make-two --now']
        assert observer.runs == [
            DependencyRun('make-one --now', True, created=('skills/one',)),
            DependencyRun('make-two --now', False, created=('skills/two',)),
        ]


class TestAttribution:
    """attribute_dependency_entries() records each command's entries and lists the ones no command installs any more."""

    @staticmethod
    def _previous(command: str, *entries: tuple[str, str]) -> dict[str, Any]:
        return {'command': command, 'entries': [{'path': path, 'identity': identity} for path, identity in entries]}

    @staticmethod
    def _attribute(
        profile_dir: Path,
        previous: object,
        runs: list[DependencyRun],
        *,
        planned_files: tuple[str, ...] = (),
        linked_entries: frozenset[str] = frozenset(),
    ) -> setup_environment.DependencyAttribution:
        return setup_environment.attribute_dependency_entries(
            previous, runs,
            profile_dir=profile_dir,
            planned_files=planned_files,
            linked_entries=linked_entries,
            identity=setup_environment.entry_identity,
        )

    def test_each_command_is_credited_with_what_it_created_or_touched(self, profile_dir: Path) -> None:
        s1, s2 = _skill(profile_dir, 's1'), _skill(profile_dir, 's2')
        result = self._attribute(profile_dir, [], [
            DependencyRun('a', True, created=('skills/s1',)),
            DependencyRun('b', True, touched=('skills/s2',)),
        ])
        assert result.records == [
            self._previous('a', ('skills/s1', _identity(s1))),
            self._previous('b', ('skills/s2', _identity(s2))),
        ]
        assert result.listed_now == ()

    def test_a_later_command_wins_a_shared_entry(self, profile_dir: Path) -> None:
        s1 = _skill(profile_dir, 's1')
        result = self._attribute(profile_dir, [], [
            DependencyRun('a', True, created=('skills/s1',)),
            DependencyRun('b', True, touched=('skills/s1',)),
        ])
        assert result.records == [self._previous('b', ('skills/s1', _identity(s1)))]

    def test_a_recreating_command_lists_its_earlier_entries_it_did_not_touch(
        self, profile_dir: Path, tmp_path: Path,
    ) -> None:
        s1, s2 = _skill(profile_dir, 's1'), _skill(profile_dir, 's2')
        previous = [self._previous('skills add', ('skills/s1', _identity(s1)), ('skills/s2', _identity(s2)))]
        _recreate(s1, tmp_path / 'aside' / 's1')
        result = self._attribute(profile_dir, previous, [DependencyRun('skills add', True, touched=('skills/s1',))])
        assert result.records == [self._previous('skills add', ('skills/s1', _identity(s1)))]
        assert result.listed_now == (_item('skills/s2', _identity(s2), 'skills add'),)

    @pytest.mark.parametrize('run', [
        DependencyRun('skills add', False, touched=('skills/s1',)),
        DependencyRun('skills add', True, created=('skills/s3',)),
        DependencyRun('skills add', True),
    ], ids=['failed', 'created-only', 'touched-nothing'])
    def test_a_failed_command_or_one_that_touched_nothing_existing_keeps_its_entries(
        self, profile_dir: Path, run: DependencyRun,
    ) -> None:
        s1, s2 = _skill(profile_dir, 's1'), _skill(profile_dir, 's2')
        if run.created:
            _skill(profile_dir, 's3')
        previous = [self._previous('skills add', ('skills/s1', 'stale'), ('skills/s2', _identity(s2)))]
        result = self._attribute(profile_dir, previous, [run])
        recorded = {entry['path']: entry['identity'] for entry in result.records[0]['entries']}
        assert recorded['skills/s1'] == _identity(s1), 'the identity is read again'
        assert recorded['skills/s2'] == _identity(s2)
        assert result.listed_now == ()

    def test_the_entries_of_a_dropped_command_are_listed_while_unchanged(
        self, profile_dir: Path, tmp_path: Path,
    ) -> None:
        unchanged, changed = _skill(profile_dir, 'unchanged'), _skill(profile_dir, 'changed')
        previous = [self._previous(
            'dropped',
            ('skills/unchanged', _identity(unchanged)),
            ('skills/changed', _identity(changed)),
            ('skills/gone', 'whatever'),
        )]
        _recreate(changed, tmp_path / 'aside' / 'changed')
        result = self._attribute(profile_dir, previous, [])
        assert result.records == []
        assert result.listed_now == (_item('skills/unchanged', _identity(unchanged), 'dropped'),)

    def test_entries_under_a_linked_entry_or_holding_a_planned_file_are_dropped(self, profile_dir: Path) -> None:
        rule = profile_dir / 'rules' / 'r.md'
        rule.parent.mkdir(parents=True)
        rule.write_text('r', encoding='utf-8')
        planned = _skill(profile_dir, 'planned')
        free = _skill(profile_dir, 'free')
        previous = [self._previous(
            'dropped',
            ('rules/r.md', _identity(rule)),
            ('skills/planned', _identity(planned)),
            ('skills/free', _identity(free)),
        )]
        result = self._attribute(
            profile_dir, previous, [DependencyRun('a', True, created=('rules/r.md', 'skills/planned'))],
            planned_files=('skills/PLANNED/SKILL.md',),
            linked_entries=frozenset({'rules'}),
        )
        assert result.records == []
        assert result.listed_now == (_item('skills/free', _identity(free), 'dropped'),)

    def test_malformed_records_are_ignored(self, profile_dir: Path) -> None:
        entry = _skill(profile_dir, 's1')
        previous: list[object] = [
            'text',
            {'command': 1, 'entries': []},
            {'command': 'c', 'entries': 'x'},
            self._previous(
                'c',
                ('skills', _identity(entry)),
                ('skills/s1/SKILL.md', _identity(entry)),
                ('../skills/s1', _identity(entry)),
                ('projects/s1', _identity(entry)),
            ),
            {'command': 'c', 'entries': [{'path': 'skills/s1'}, {'path': 'skills/s1', 'identity': ''}]},
        ]
        result = self._attribute(profile_dir, previous, [])
        assert (result.records, result.listed_now) == ([], ())

    def test_credited_names_every_entry_recorded_this_run(self, profile_dir: Path) -> None:
        _skill(profile_dir, 'S1')
        result = self._attribute(profile_dir, [], [DependencyRun('a', True, created=('skills/S1',))])
        assert result.credited == frozenset({'skills/s1'})


class TestItem:
    """A dependency entry is an item of its own: a path inside a content directory, its command and identity."""

    def test_record_round_trip(self, tmp_path: Path) -> None:
        item = _item('skills/foo', 'abc', 'npx skills add src')
        record = item.to_record()
        assert record == {'kind': DEP, 'path': 'skills/foo', 'command': 'npx skills add src', 'identity': 'abc'}
        assert LeftoverItem.from_record(record, claude_dir=tmp_path) == item

    @pytest.mark.parametrize('record', [
        {'kind': DEP, 'path': 'skills', 'command': 'c', 'identity': 'h'},
        {'kind': DEP, 'path': 'skills/a/b', 'command': 'c', 'identity': 'h'},
        {'kind': DEP, 'path': 'skills/a\\b', 'command': 'c', 'identity': 'h'},
        {'kind': DEP, 'path': 'projects/a', 'command': 'c', 'identity': 'h'},
        {'kind': DEP, 'path': '../a', 'command': 'c', 'identity': 'h'},
        {'kind': DEP, 'path': 'skills/..', 'command': 'c', 'identity': 'h'},
        {'kind': DEP, 'path': '/skills/a', 'command': 'c', 'identity': 'h'},
        {'kind': DEP, 'path': 'C:/skills/a', 'command': 'c', 'identity': 'h'},
        {'kind': DEP, 'path': 'skills/a', 'command': 'c', 'identity': ''},
        {'kind': DEP, 'path': 'skills/a', 'command': 'c', 'identity': None},
        {'kind': DEP, 'path': 'skills/a', 'command': 'c'},
        {'kind': DEP, 'path': 'skills/a', 'identity': 'h'},
        {'kind': DEP, 'path': 'skills/a', 'command': 'c', 'sha256': 'h'},
    ])
    def test_from_record_refuses_any_other_shape(self, record: dict[str, Any], tmp_path: Path) -> None:
        assert LeftoverItem.from_record(record, claude_dir=tmp_path) is None

    def test_label_display_location_and_key(self, profile_dir: Path) -> None:
        item = _item('skills/Foo', 'abc', 'npx skills add src')
        assert item.label() == 'dependency entry: skills/Foo'
        assert item.display(profile_dir) == (
            f'dependency entry: {profile_dir / "skills" / "Foo"} (from: npx skills add src)'
        )
        assert item.key() == _item('SKILLS/foo', 'other', 'other').key()
        assert item.location(profile_dir) == profile_dir / 'skills' / 'Foo'


class TestReport:
    """A dependency entry an earlier run listed is checked by its identity before consent."""

    @staticmethod
    def _compute(
        profile_dir: Path,
        items: list[LeftoverItem],
        *,
        planned: PlannedRecords | None = None,
        live: LiveLeftoverState | None = None,
    ) -> LeftoverReport:
        return setup_environment.compute_profile_leftovers(
            {'leftovers': {'items': [item.to_record() for item in items]}},
            profile_dir,
            profile_name='p',
            planned=planned or PlannedRecords(),
            live=live or _live(profile_dir),
            claude_dir=profile_dir.parent,
        )

    def test_states_follow_the_identity(self, profile_dir: Path, tmp_path: Path) -> None:
        unchanged, changed = _skill(profile_dir, 'unchanged'), _skill(profile_dir, 'changed')
        items = [
            _item('skills/unchanged', _identity(unchanged)),
            _item('skills/changed', _identity(changed)),
            _item('skills/gone', 'h'),
        ]
        _recreate(changed, tmp_path / 'aside' / 'changed')
        report = self._compute(profile_dir, items)
        assert {entry.item.path: entry.state for entry in report.entries} == {
            'skills/unchanged': 'removable', 'skills/changed': 'changed', 'skills/gone': 'gone',
        }

    def test_an_entry_reached_through_a_link_is_linked_before_its_identity_is_read(self, profile_dir: Path) -> None:
        reads: list[Path] = []

        def _identity_reader(path: Path) -> str | None:
            reads.append(path)
            return 'h'

        live = LiveLeftoverState(
            file_digest=setup_environment._live_file_digest,
            under_link=lambda _relative: True,
            destination_holders=lambda _dest: [],
            identity=_identity_reader,
        )
        report = self._compute(profile_dir, [_item('skills/s1', 'h')], live=live)
        assert [entry.state for entry in report.entries] == ['linked']
        assert reads == []

    def test_an_unreadable_entry_cannot_be_checked(self, profile_dir: Path) -> None:
        def _unreadable(_path: Path) -> str | None:
            raise LeftoverReadError('Permission denied')

        live = LiveLeftoverState(
            file_digest=setup_environment._live_file_digest,
            under_link=lambda _relative: False,
            destination_holders=lambda _dest: [],
            identity=_unreadable,
        )
        report = self._compute(profile_dir, [_item('skills/s1', 'h')], live=live)
        assert [(entry.state, entry.detail) for entry in report.entries] == [('unreadable', 'Permission denied')]

    def test_an_entry_holding_a_planned_file_is_no_leftover(self, profile_dir: Path) -> None:
        entry = _skill(profile_dir, 's1')
        report = self._compute(
            profile_dir,
            [_item('skills/s1', _identity(entry))],
            planned=PlannedRecords(files=frozenset({'skills/s1/SKILL.md'})),
        )
        assert report.entries == ()

    def test_refined_marks_an_entry_under_an_entry_this_run_links(self, profile_dir: Path) -> None:
        entry = _skill(profile_dir, 's1')
        report = self._compute(profile_dir, [_item('skills/s1', _identity(entry))])
        refined = report.refined(linked_entries=frozenset({'skills'}), link_source='src')
        assert [(entry.state, entry.detail) for entry in refined.entries] == [('linked', 'now linked from profile src')]

    def test_rows_name_the_entry_and_its_command(self, profile_dir: Path) -> None:
        entry = _skill(profile_dir, 's1')
        report = self._compute(profile_dir, [_item('skills/s1', _identity(entry), 'npx skills add src')])
        assert report.rows() == [f'[leftover] dependency entry: {entry} (from: npx skills add src)']


class TestAfterDependencyCommands:
    """After Step 6 the report knows what the commands installed again, which failed, and what they left behind."""

    def test_an_entry_a_command_installed_again_is_no_longer_tracked(self, profile_dir: Path) -> None:
        report = _report(profile_dir, LeftoverEntry(_item('skills/S1', 'h'), 'removable'))
        after = report.after_dependency_commands(
            credited=frozenset({'skills/s1'}), failed_commands=frozenset(), listed_now=(),
        )
        assert [entry.state for entry in after.entries] == ['recreated']
        assert after.carried() == []
        record = setup_environment.leftovers_manifest_record(after, run_at='t')
        assert record['items'] == []
        assert record['dropped'] == [{'label': 'dependency entry: skills/S1', 'reason': 'recreated'}]
        assert after.completion_sections() == [(
            'No longer tracked:',
            [f'dependency entry: {profile_dir / "skills" / "S1"} (from: cmd) (installed again by a dependency command)'],
        )]

    def test_an_entry_whose_command_failed_is_kept(self, profile_dir: Path) -> None:
        report = _report(
            profile_dir,
            LeftoverEntry(_item('skills/s1', 'h', 'flaky'), 'removable'),
            LeftoverEntry(_item('skills/s2', 'h', 'fine'), 'removable'),
        )
        after = report.after_dependency_commands(
            credited=frozenset(), failed_commands=frozenset({'flaky'}), listed_now=(),
        )
        assert [(entry.state, entry.detail) for entry in after.entries] == [
            ('held', 'its dependency command failed in this run'), ('removable', ''),
        ]

    def test_a_profile_file_inside_or_at_an_entry_a_command_installed_is_no_longer_tracked(
        self, profile_dir: Path,
    ) -> None:
        inside, at_entry = LeftoverItem('file', 'skills/S1/SKILL.md', 'h'), LeftoverItem('file', 'rules/r.md', 'h')
        elsewhere = LeftoverItem('file', 'skills/s2/SKILL.md', 'h')
        report = _report(
            profile_dir, *(LeftoverEntry(item, 'removable') for item in (inside, at_entry, elsewhere)),
        )
        after = report.after_dependency_commands(
            credited=frozenset({'skills/s1', 'rules/r.md'}), failed_commands=frozenset(), listed_now=(),
        )
        assert [entry.state for entry in after.entries] == ['recreated', 'recreated', 'removable']
        assert after.carried() == [elsewhere]
        record = setup_environment.leftovers_manifest_record(after, run_at='t')
        assert record['items'] == [elsewhere.to_record()]
        assert record['dropped'] == [
            {'label': 'file: skills/S1/SKILL.md', 'reason': 'recreated'},
            {'label': 'file: rules/r.md', 'reason': 'recreated'},
        ]
        assert ('No longer tracked:', [
            f'file: {profile_dir / "skills" / "S1" / "SKILL.md"} (installed again by a dependency command)',
            f'file: {profile_dir / "rules" / "r.md"} (installed again by a dependency command)',
        ]) in after.completion_sections()

    def test_entries_listed_now_are_recorded_and_never_part_of_this_run_s_removal(self, profile_dir: Path) -> None:
        listed = _item('skills/s9', 'h', 'dropped')
        after = _report(profile_dir).after_dependency_commands(
            credited=frozenset(), failed_commands=frozenset(), listed_now=(listed,),
        )
        assert after.carried() == []
        assert not setup_environment.leftovers_step_runs(after, remove=True)
        record = setup_environment.leftovers_manifest_record(after, run_at='t')
        assert record['items'] == [listed.to_record()]
        assert record['kept'] == [{'label': 'dependency entry: skills/s9', 'reason': FLAG_NOTE}]
        assert after.completion_sections() == [(
            'Dependency entries listed now (1; --remove-leftovers removes them on a later run):',
            [f'dependency entry: {profile_dir / "skills" / "s9"} (from: dropped)'],
        )]


class TestStep23:
    """Step 23 removes a listed dependency entry while it keeps its identity, its command ran and no link reaches it."""

    @staticmethod
    def _listed(entry: Path, command: str = 'cmd') -> LeftoverEntry:
        relative = f'{entry.parent.name}/{entry.name}'
        return LeftoverEntry(_item(relative, _identity(entry), command), 'removable')

    def test_removes_a_directory_a_file_and_a_link_without_its_target(
        self, profile_dir: Path, tmp_path: Path,
    ) -> None:
        directory = _skill(profile_dir, 'dir')
        file_entry = profile_dir / 'rules' / 'r.md'
        file_entry.parent.mkdir(parents=True)
        file_entry.write_text('r', encoding='utf-8')
        target = tmp_path / 'target'
        (target / 'inside').mkdir(parents=True)
        (target / 'inside' / 'keep.md').write_text('keep', encoding='utf-8')
        link = profile_dir / 'skills' / 'link'
        setup_environment.link_profile_directory(link, target)
        report = _report(profile_dir, self._listed(directory), self._listed(file_entry), self._listed(link))

        assert _results(_step(report, profile_dir)) == {
            'skills/dir': ('removed', ''), 'rules/r.md': ('removed', ''), 'skills/link': ('removed', ''),
        }
        assert not directory.exists()
        assert not file_entry.exists()
        assert not link.exists()
        assert not setup_environment._is_directory_link(link)
        assert (target / 'inside' / 'keep.md').read_text(encoding='utf-8') == 'keep'

    def test_an_entry_a_link_reaches_since_the_summary_is_left_to_its_source(
        self, profile_dir: Path, tmp_path: Path,
    ) -> None:
        listed = self._listed(_skill(profile_dir, 's1'))
        shutil.rmtree(profile_dir / 'skills')
        source_skills = tmp_path / 'source' / 'skills'
        (source_skills / 's1').mkdir(parents=True)
        (source_skills / 's1' / 'SKILL.md').write_text('source', encoding='utf-8')
        setup_environment.link_profile_directory(profile_dir / 'skills', source_skills)

        assert _results(_step(_report(profile_dir, listed), profile_dir)) == {'skills/s1': ('dropped', 'linked')}
        assert (source_skills / 's1' / 'SKILL.md').read_text(encoding='utf-8') == 'source'

    def test_kept_while_its_command_failed_this_run(self, profile_dir: Path) -> None:
        entry = _skill(profile_dir, 's1')
        report = _report(profile_dir, self._listed(entry, 'flaky'))
        assert _results(_step(report, profile_dir, failed_commands=frozenset({'flaky'}))) == {
            'skills/s1': ('kept', 'its dependency command failed in this run'),
        }
        assert entry.exists()

    def test_changed_gone_and_installed_again_are_dropped(self, profile_dir: Path, tmp_path: Path) -> None:
        changed, gone, again = _skill(profile_dir, 'changed'), _skill(profile_dir, 'gone'), _skill(profile_dir, 'again')
        report = _report(profile_dir, self._listed(changed), self._listed(gone), self._listed(again))
        _recreate(changed, tmp_path / 'aside' / 'changed')
        shutil.rmtree(gone)
        removal = _step(report, profile_dir, written=PlannedRecords(dependency_entries=frozenset({'skills/again'})))
        assert _results(removal) == {
            'skills/changed': ('dropped', 'changed'),
            'skills/gone': ('dropped', 'gone'),
            'skills/again': ('dropped', 'written again'),
        }
        assert changed.exists()
        assert again.exists()

    def test_a_profile_file_inside_an_entry_this_run_wrote_is_dropped_as_written_again(
        self, profile_dir: Path,
    ) -> None:
        entry = _skill(profile_dir, 'moved')
        skill_file = entry / 'SKILL.md'
        listed = LeftoverEntry(
            LeftoverItem('file', 'skills/moved/SKILL.md', setup_environment._hash_file(skill_file)), 'removable',
        )
        written = PlannedRecords(dependency_entries=frozenset({'skills/moved'}))
        assert _results(_step(_report(profile_dir, listed), profile_dir, written=written)) == {
            'skills/moved/SKILL.md': ('dropped', 'written again'),
        }
        assert skill_file.read_text(encoding='utf-8') == 'skill'

    def test_a_failed_removal_is_carried(self, profile_dir: Path) -> None:
        entry = _skill(profile_dir, 's1')
        report = _report(profile_dir, self._listed(entry))
        with patch.object(setup_environment.shutil, 'rmtree', side_effect=PermissionError(13, 'Access is denied')):
            removal = _step(report, profile_dir)
        assert _results(removal) == {'skills/s1': ('failed', 'Access is denied')}
        assert removal is not None
        record = setup_environment.leftovers_manifest_record(report, run_at='t', removal=removal)
        assert record['failed'] == ['dependency entry: skills/s1']
        assert record['items'] == [report.entries[0].item.to_record()]

    def test_dependency_entries_go_last(self, profile_dir: Path) -> None:
        entry = _skill(profile_dir, 's1')
        rule = profile_dir / 'rules' / 'r.md'
        rule.parent.mkdir(parents=True)
        rule.write_bytes(b'r')
        file_entry = LeftoverEntry(LeftoverItem('file', 'rules/r.md', setup_environment._hash_file(rule)), 'removable')
        removal = _step(_report(profile_dir, self._listed(entry), file_entry), profile_dir)
        assert removal is not None
        assert [outcome.entry.item.kind for outcome in removal.outcomes] == ['file', DEP]

    def test_entries_listed_now_stay_on_disk_and_in_the_record(self, profile_dir: Path) -> None:
        listed_now = _skill(profile_dir, 'listed-now')
        carried = _skill(profile_dir, 'carried')
        report = _report(profile_dir, self._listed(carried)).after_dependency_commands(
            credited=frozenset(), failed_commands=frozenset(),
            listed_now=(_item('skills/listed-now', _identity(listed_now)),),
        )
        recorded: list[dict[str, Any]] = []

        def _record(_path: Path, record: dict[str, Any]) -> bool:
            recorded.append(record)
            return True

        with patch.object(setup_environment, '_record_manifest_leftovers', side_effect=_record):
            removal = _step(report, profile_dir)
        assert _results(removal) == {'skills/carried': ('removed', '')}
        assert listed_now.exists()
        assert len(recorded) == 1
        assert recorded[0]['items'] == [_item('skills/listed-now', _identity(listed_now)).to_record()]
        assert recorded[0]['removed'] == ['dependency entry: skills/carried']


class TestManifest:
    """The manifest records the dependency entries per command, and Step 23 reads them as written."""

    def test_write_manifest_records_the_dependency_entries(self, tmp_path: Path) -> None:
        records = [{'command': 'c', 'entries': [{'path': 'skills/s1', 'identity': 'h'}]}]
        assert _REAL_WRITE_MANIFEST(
            tmp_path, 'p', None, str(tmp_path / 'c.yaml'), 'local', None, ['p'], None, dependency_entries=records,
        )
        manifest = json.loads((tmp_path / 'manifest.json').read_text(encoding='utf-8'))
        assert manifest['dependency_entries'] == records

    def test_written_records_name_the_entries_of_this_run(self) -> None:
        written = setup_environment.written_leftover_records({
            'files_written': [], 'machine_wide_destinations': [],
            'dependency_entries': [{'command': 'c', 'entries': [{'path': 'skills/S1', 'identity': 'h'}]}],
        })
        assert written.writes(_item('skills/s1', 'other'))
        assert not written.writes(_item('skills/s2', 'h'))

    def test_a_planned_file_inside_an_entry_makes_the_entry_written(self) -> None:
        planned = PlannedRecords(files=frozenset({'skills/s1/SKILL.md', 'rules/r.md'}))
        assert planned.writes(_item('skills/s1', 'h'))
        assert planned.writes(_item('rules/r.md', 'h'))
        assert not planned.writes(_item('skills/s2', 'h'))

    def test_a_file_inside_or_at_an_entry_the_commands_installed_is_written(self) -> None:
        written = PlannedRecords(dependency_entries=frozenset({'skills/S1', 'rules/r.md'}))
        for path in ('skills/s1/SKILL.md', 'skills/s1/refs/deep.md', 'rules/r.md'):
            assert written.writes(LeftoverItem('file', path, 'h')), path
        assert not written.writes(LeftoverItem('file', 'skills/s2/SKILL.md', 'h'))
        assert not written.writes(LeftoverItem('file', 'rules/other.md', 'h'))

    def test_a_planned_file_never_makes_its_sibling_files_written(self) -> None:
        planned = PlannedRecords(files=frozenset({'skills/s1/SKILL.md'}))
        assert planned.writes(LeftoverItem('file', 'skills/s1/SKILL.md', 'h'))
        assert not planned.writes(LeftoverItem('file', 'skills/s1/old.md', 'h'))


class TestUnitTestIsolation:
    """main()-flow unit tests observe nothing: the conftest replaces the observer factory."""

    def test_the_conftest_observer_observes_no_directory(self, profile_dir: Path) -> None:
        observer = setup_environment.dependency_entry_observer(profile_dir, frozenset())
        assert isinstance(observer, DependencyEntryObserver)
        observer.around('c', lambda: _skill(profile_dir, 'made').exists())
        assert observer.runs == [DependencyRun('c', True)]
