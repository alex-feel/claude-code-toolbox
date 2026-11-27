"""Tests for the leftovers of earlier runs: the records a run keeps and the report a re-run prints.

A profile's manifest records each profile file and each destination outside
~/.claude a run wrote, with the sha256 of its content. A re-run compares those
records, and the leftovers an earlier run carried, with what the configuration
installs now: whatever it no longer installs is a leftover, listed in the
installation summary, --dry-run and the completion summary, and left in place.
"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import setup_environment
from scripts.setup_environment import LeftoverEntry
from scripts.setup_environment import LeftoverItem
from scripts.setup_environment import LeftoverReadError
from scripts.setup_environment import LeftoverReport
from scripts.setup_environment import LiveLeftoverState
from scripts.setup_environment import PlannedRecords

_REAL_WRITE_MANIFEST = setup_environment.write_manifest
_REAL_INSTALLED_PROFILES = setup_environment.installed_profiles


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _write(path: Path, content: bytes) -> str:
    """Write a file, creating its parents, and return the sha256 of its content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return _sha(content)


def _live(
    *,
    holders: dict[str, list[str]] | None = None,
    linked: frozenset[str] = frozenset(),
    unreadable: frozenset[Path] = frozenset(),
) -> LiveLeftoverState:
    """A live state over the real file system, with links, holders and unreadable files given."""
    def _digest(path: Path) -> str | None:
        if path in unreadable:
            raise LeftoverReadError('Permission denied')
        return setup_environment._live_file_digest(path)

    return LiveLeftoverState(
        file_digest=_digest,
        under_link=lambda relative: relative.split('/')[0] in linked,
        destination_holders=lambda dest: (holders or {}).get(dest, []),
    )


@pytest.fixture
def layout(tmp_path: Path) -> tuple[Path, Path]:
    """The ~/.claude directory and an isolated profile directory inside it."""
    claude_dir = tmp_path / '.claude'
    profile_dir = claude_dir / 'p'
    profile_dir.mkdir(parents=True)
    return claude_dir, profile_dir


def _compute(
    manifest: dict[str, object],
    profile_dir: Path,
    claude_dir: Path,
    *,
    planned: PlannedRecords | None = None,
    live: LiveLeftoverState | None = None,
) -> LeftoverReport:
    return setup_environment.compute_profile_leftovers(
        manifest, profile_dir,
        profile_name='p',
        planned=planned or PlannedRecords(),
        live=live or _live(),
        claude_dir=claude_dir,
    )


def _states(report: LeftoverReport) -> dict[str, str]:
    return {entry.item.path: entry.state for entry in report.entries}


class TestLeftoverDigest:
    """One canonical JSON form decides the digest of a recorded value."""

    def test_canonical_form(self) -> None:
        value = {'b': 1, 'a': [1, 'é', None]}
        expected = _sha('{"a":[1,"é",null],"b":1}'.encode())
        assert setup_environment.leftover_digest(value) == expected

    def test_key_order_does_not_matter(self) -> None:
        assert setup_environment.leftover_digest({'a': 1, 'b': 2}) == setup_environment.leftover_digest({'b': 2, 'a': 1})

    def test_different_values_differ(self) -> None:
        assert setup_environment.leftover_digest('1') != setup_environment.leftover_digest(1)


class TestLeftoverItemRecords:
    """A leftover record round-trips, and a record of another shape is never read."""

    def test_file_and_destination_round_trip(self, tmp_path: Path) -> None:
        claude_dir = tmp_path / '.claude'
        outside = str(tmp_path / 'shared' / 'tool.txt')
        for record in (
            {'kind': 'file', 'path': 'hooks/old.py', 'sha256': 'ab'},
            {'kind': 'destination', 'path': outside, 'sha256': 'cd'},
        ):
            item = LeftoverItem.from_record(record, claude_dir=claude_dir)
            assert item is not None
            assert item.to_record() == record

    @pytest.mark.parametrize('record', [
        'hooks/old.py',
        None,
        {'kind': 'file', 'path': 'hooks/old.py'},
        {'kind': 'file', 'path': 'hooks/old.py', 'sha256': 5},
        {'kind': 'setting', 'path': 'hooks/old.py', 'sha256': 'ab'},
        {'kind': 'file', 'path': '', 'sha256': 'ab'},
        {'kind': 'file', 'path': '/etc/passwd', 'sha256': 'ab'},
        {'kind': 'file', 'path': 'C:/Windows/x', 'sha256': 'ab'},
        {'kind': 'file', 'path': '\\\\server\\share\\x', 'sha256': 'ab'},
        {'kind': 'file', 'path': '\\x', 'sha256': 'ab'},
        {'kind': 'file', 'path': '../other/x', 'sha256': 'ab'},
        {'kind': 'file', 'path': 'rules/../../x', 'sha256': 'ab'},
        {'kind': 'file', 'path': 'rules\\..\\..\\x', 'sha256': 'ab'},
        {'kind': 'destination', 'path': 'relative/x.txt', 'sha256': 'ab'},
        {'kind': 'file', 'path': 'hooks/h.py', 'sha256': 'ab', 'hook_helper': 'yes'},
        {'kind': 'file', 'path': 'hooks/h.py', 'sha256': 'ab', 'hook_helper': 1},
        {'kind': 'destination', 'path': str(Path('/srv/out/x.txt').resolve()), 'sha256': 'ab', 'hook_helper': True},
    ])
    def test_records_of_another_shape_are_refused(self, tmp_path: Path, record: object) -> None:
        assert LeftoverItem.from_record(record, claude_dir=tmp_path / '.claude') is None

    def test_a_hook_helper_mark_round_trips_and_is_read_from_files_written(self, tmp_path: Path) -> None:
        claude_dir = tmp_path / '.claude'
        record = {'kind': 'file', 'path': 'hooks/h.py', 'sha256': 'ab', 'hook_helper': True}
        item = LeftoverItem.from_record(record, claude_dir=claude_dir)
        assert item is not None
        assert item.hook_helper
        assert item.to_record() == record
        plain = LeftoverItem.from_record({**record, 'hook_helper': False}, claude_dir=claude_dir)
        assert plain is not None
        assert not plain.hook_helper
        assert plain.to_record() == {'kind': 'file', 'path': 'hooks/h.py', 'sha256': 'ab'}
        candidates = setup_environment._recorded_leftover_candidates(
            {'files_written': [{'path': 'hooks/h.py', 'sha256': 'ab', 'hook_helper': True}]}, claude_dir,
        )
        assert [(candidate.path, candidate.hook_helper) for candidate in candidates] == [('hooks/h.py', True)]

    def test_destination_inside_the_config_home_is_refused(self, tmp_path: Path) -> None:
        claude_dir = tmp_path / '.claude'
        record = {'kind': 'destination', 'path': str(claude_dir / 'p' / 'x.txt'), 'sha256': 'ab'}
        assert LeftoverItem.from_record(record, claude_dir=claude_dir) is None

    def test_file_key_ignores_letter_case(self) -> None:
        """A rename that changes only letter case names the same file on a case-insensitive file system."""
        assert LeftoverItem('file', 'Rules/Old.md', 'a').key() == LeftoverItem('file', 'rules/old.md', 'b').key()
        assert LeftoverItem('file', 'rules/a.md', 'a').key() != LeftoverItem('destination', 'rules/a.md', 'a').key()

    def test_labels(self, tmp_path: Path) -> None:
        profile_dir = tmp_path / 'p'
        outside = tmp_path / 'tool.txt'
        assert LeftoverItem('file', 'rules/old.md', 'a').label() == 'file: rules/old.md'
        assert LeftoverItem('file', 'rules/old.md', 'a').display(profile_dir) == (
            f'file: {profile_dir / "rules" / "old.md"}'
        )
        destination = LeftoverItem('destination', str(outside), 'a')
        assert destination.label() == f'file outside ~/.claude: {outside}'
        assert destination.display(profile_dir) == f'file outside ~/.claude: {outside}'


class TestLiveFileDigest:
    """The live digest tells an absent file, another kind of entry and an unreadable file apart."""

    def test_regular_absent_and_directory(self, tmp_path: Path) -> None:
        digest = _write(tmp_path / 'a.txt', b'content')
        assert setup_environment._live_file_digest(tmp_path / 'a.txt') == digest
        assert setup_environment._live_file_digest(tmp_path / 'missing.txt') is None
        (tmp_path / 'dir').mkdir()
        assert setup_environment._live_file_digest(tmp_path / 'dir') == ''

    def test_a_path_that_cannot_be_examined_raises(self, tmp_path: Path) -> None:
        """A permission error on the entry itself is no proof that the file is gone."""
        with (
            patch.object(setup_environment.os, 'lstat', side_effect=PermissionError(13, 'Permission denied')),
            pytest.raises(LeftoverReadError, match='Permission denied'),
        ):
            setup_environment._live_file_digest(tmp_path / 'a.txt')

    def test_a_file_where_a_directory_was_expected_is_gone(self, tmp_path: Path) -> None:
        _write(tmp_path / 'rules', b'a file, not a directory')
        assert setup_environment._live_file_digest(tmp_path / 'rules' / 'old.md') is None

    def test_unreadable_file_raises(self, tmp_path: Path) -> None:
        _write(tmp_path / 'a.txt', b'content')
        with (
            patch.object(Path, 'open', side_effect=PermissionError(13, 'Permission denied')),
            pytest.raises(LeftoverReadError, match='Permission denied'),
        ):
            setup_environment._live_file_digest(tmp_path / 'a.txt')


class TestComputeProfileLeftovers:
    """A re-run lists what an earlier run wrote and this configuration no longer installs."""

    def test_states_of_profile_files(self, layout: tuple[Path, Path]) -> None:
        claude_dir, profile_dir = layout
        old = _write(profile_dir / 'rules' / 'old.md', b'old')
        kept = _write(profile_dir / 'rules' / 'kept.md', b'kept')
        _write(profile_dir / 'rules' / 'edited.md', b'edited by hand')
        (profile_dir / 'rules' / 'replaced.md').mkdir()
        locked = _write(profile_dir / 'rules' / 'locked.md', b'locked')
        manifest: dict[str, object] = {
            'files_written': [
                {'path': 'rules/old.md', 'sha256': old},
                {'path': 'rules/kept.md', 'sha256': kept},
                {'path': 'rules/edited.md', 'sha256': _sha(b'as written')},
                {'path': 'rules/gone.md', 'sha256': _sha(b'gone')},
                {'path': 'rules/replaced.md', 'sha256': _sha(b'replaced')},
                {'path': 'rules/locked.md', 'sha256': locked},
                {'path': 'rules/unverified.md', 'sha256': None},
            ],
            'leftovers': {'items': []},
        }

        report = _compute(
            manifest, profile_dir, claude_dir,
            planned=PlannedRecords(files=frozenset({'rules/kept.md'})),
            live=_live(unreadable=frozenset({profile_dir / 'rules' / 'locked.md'})),
        )

        assert _states(report) == {
            'rules/old.md': 'removable',
            'rules/edited.md': 'changed',
            'rules/gone.md': 'gone',
            'rules/replaced.md': 'changed',
            'rules/locked.md': 'unreadable',
        }, 'a planned file and a record without a digest are never leftovers'
        assert not report.untracked_note
        locked_entry = next(entry for entry in report.entries if entry.item.path == 'rules/locked.md')
        assert locked_entry.detail == 'Permission denied'

    def test_a_case_only_rename_is_no_leftover(self, layout: tuple[Path, Path]) -> None:
        claude_dir, profile_dir = layout
        digest = _write(profile_dir / 'rules' / 'old.md', b'old')
        manifest: dict[str, object] = {'files_written': [{'path': 'rules/Old.md', 'sha256': digest}]}
        report = _compute(manifest, profile_dir, claude_dir, planned=PlannedRecords(files=frozenset({'rules/old.md'})))
        assert report.entries == ()

    def test_file_under_a_link_on_disk_is_linked(self, layout: tuple[Path, Path]) -> None:
        claude_dir, profile_dir = layout
        digest = _write(profile_dir / 'rules' / 'old.md', b'old')
        manifest: dict[str, object] = {'files_written': [{'path': 'rules/old.md', 'sha256': digest}]}
        report = _compute(manifest, profile_dir, claude_dir, live=_live(linked=frozenset({'rules'})))
        assert [(entry.state, entry.detail) for entry in report.entries] == [
            ('linked', 'now reached through a directory link'),
        ]

    def test_real_link_on_disk_is_seen(self, layout: tuple[Path, Path]) -> None:
        """The live state of a profile reads a junction or symlink on disk, not a recorded link."""
        claude_dir, profile_dir = layout
        source = claude_dir / 'src'
        digest = _write(source / 'rules' / 'old.md', b'old')
        setup_environment.link_profile_directory(profile_dir / 'rules', source / 'rules')
        manifest: dict[str, object] = {'files_written': [{'path': 'rules/old.md', 'sha256': digest}]}
        report = _compute(
            manifest, profile_dir, claude_dir,
            live=LiveLeftoverState.for_profile(profile_dir, claude_dir.parent),
        )
        assert _states(report) == {'rules/old.md': 'linked'}

    def test_refined_marks_files_under_this_runs_links(self, layout: tuple[Path, Path]) -> None:
        claude_dir, profile_dir = layout
        rule = _write(profile_dir / 'rules' / 'old.md', b'old')
        agent = _write(profile_dir / 'agents' / 'old.md', b'agent')
        outside = profile_dir.parent.parent / 'tool.txt'
        tool = _write(outside, b'tool')
        manifest: dict[str, object] = {
            'files_written': [{'path': 'rules/old.md', 'sha256': rule}, {'path': 'agents/old.md', 'sha256': agent}],
            'machine_wide_destinations': [{'dest': str(outside), 'source': 's', 'sha256': tool}],
        }

        report = _compute(manifest, profile_dir, claude_dir).refined(
            linked_entries=frozenset({'rules'}), link_source='src',
        )

        assert [(entry.item.path, entry.state, entry.detail) for entry in report.entries] == [
            ('agents/old.md', 'removable', ''),
            ('rules/old.md', 'linked', 'now linked from profile src'),
            (str(outside), 'removable', ''),
        ]

    def test_destinations(self, layout: tuple[Path, Path]) -> None:
        claude_dir, profile_dir = layout
        root = claude_dir.parent
        removable = _write(root / 'out' / 'removable.txt', b'r')
        held = _write(root / 'out' / 'held.txt', b'h')
        planned = _write(root / 'out' / 'Planned.txt', b'p')
        manifest: dict[str, object] = {'machine_wide_destinations': [
            {'dest': str(root / 'out' / 'removable.txt'), 'source': 's', 'sha256': removable},
            {'dest': str(root / 'out' / 'held.txt'), 'source': 's', 'sha256': held},
            {'dest': str(root / 'out' / 'Planned.txt'), 'source': 's', 'sha256': planned},
            {'dest': str(root / 'out' / 'gone.txt'), 'source': 's', 'sha256': _sha(b'g')},
            {'dest': str(root / 'out' / 'unverified.txt'), 'source': 's', 'sha256': None},
            {'dest': str(claude_dir / 'inside.txt'), 'source': 's', 'sha256': _sha(b'i')},
        ]}

        report = _compute(
            manifest, profile_dir, claude_dir,
            planned=PlannedRecords(destinations=frozenset({str(root / 'out' / 'planned.txt')})),
            live=_live(holders={str(root / 'out' / 'held.txt'): ['base', 'other']}),
        )

        assert [(Path(entry.item.path).name, entry.state, entry.detail) for entry in report.entries] == [
            ('gone.txt', 'gone', ''),
            ('held.txt', 'held', 'recorded by profile base, other'),
            ('removable.txt', 'removable', ''),
        ]

    def test_held_destination_from_the_real_manifests(self, layout: tuple[Path, Path]) -> None:
        """A destination another installed profile records is kept, read from that profile's manifest."""
        claude_dir, profile_dir = layout
        outside = claude_dir.parent / 'shared.txt'
        digest = _write(outside, b'shared')
        record = {'dest': str(outside), 'source': 's', 'sha256': digest}
        (claude_dir / 'other').mkdir()
        (claude_dir / 'other' / 'manifest.json').write_text(
            json.dumps({'name': 'other', 'machine_wide_destinations': [record]}), encoding='utf-8',
        )
        (profile_dir / 'manifest.json').write_text(
            json.dumps({'name': 'p', 'machine_wide_destinations': [record]}), encoding='utf-8',
        )

        with patch.object(setup_environment, 'installed_profiles', _REAL_INSTALLED_PROFILES):
            report = _compute(
                {'machine_wide_destinations': [record]}, profile_dir, claude_dir,
                live=LiveLeftoverState.for_profile(profile_dir, claude_dir.parent),
            )

        assert [(entry.state, entry.detail) for entry in report.entries] == [('held', 'recorded by profile other')]

    def test_carried_leftovers_stay_candidates(self, layout: tuple[Path, Path]) -> None:
        """A leftover an earlier run carried is listed again while the configuration still does not install it."""
        claude_dir, profile_dir = layout
        carried = _write(profile_dir / 'agents' / 'carried.md', b'carried')
        written = _write(profile_dir / 'agents' / 'written.md', b'written')
        manifest: dict[str, object] = {
            'files_written': [{'path': 'agents/written.md', 'sha256': written}],
            'leftovers': {'items': [
                {'kind': 'file', 'path': 'agents/carried.md', 'sha256': carried},
                {'kind': 'file', 'path': 'agents/written.md', 'sha256': _sha(b'an older write')},
                {'kind': 'file', 'path': '../escape.md', 'sha256': carried},
                {'kind': 'unknown', 'path': 'x', 'sha256': carried},
            ]},
        }

        report = _compute(manifest, profile_dir, claude_dir)

        assert _states(report) == {'agents/carried.md': 'removable', 'agents/written.md': 'removable'}
        written_entry = next(entry for entry in report.entries if entry.item.path == 'agents/written.md')
        assert written_entry.item.sha256 == written, 'the latest written record wins over a carried one'

    def test_a_configuration_listing_the_file_again_takes_it_back(self, layout: tuple[Path, Path]) -> None:
        claude_dir, profile_dir = layout
        carried = _write(profile_dir / 'agents' / 'back.md', b'back')
        manifest: dict[str, object] = {
            'leftovers': {'items': [{'kind': 'file', 'path': 'agents/back.md', 'sha256': carried}]},
        }
        report = _compute(manifest, profile_dir, claude_dir, planned=PlannedRecords(files=frozenset({'agents/back.md'})))
        assert report.entries == ()

    def test_untracked_note_for_a_manifest_without_leftovers(self, layout: tuple[Path, Path]) -> None:
        claude_dir, profile_dir = layout
        legacy: dict[str, object] = {'files_written': ['agents/old.md', 'rules/old.md']}
        report = _compute(legacy, profile_dir, claude_dir)
        assert report.entries == (), 'a record without a digest is never read'
        assert report.untracked_note
        assert report.has_content()

    def test_nothing_to_report(self, layout: tuple[Path, Path]) -> None:
        claude_dir, profile_dir = layout
        report = _compute({'files_written': [], 'leftovers': {'items': []}}, profile_dir, claude_dir)
        assert not report.has_content()
        assert report.lines() == []
        assert report.completion_sections() == []


class TestPlannedRecords:
    """The files and destinations a configuration installs, taken before component selection."""

    def test_files_destinations_and_reroot(self, tmp_path: Path) -> None:
        home = tmp_path / 'home'
        claude_dir = home / '.claude'
        profile_dir = claude_dir / 'p'
        outside = tmp_path / 'out' / 'tool.txt'
        config = {
            'agents': ['agents/core.md', 'agents/optional.md'],
            'components': [{'name': 'optional', 'default': False, 'includes': {'agents': ['agents/optional.md']}}],
            'files-to-download': [
                {'source': 'files/tool.txt', 'dest': str(outside)},
                {'source': 'files/inside.txt', 'dest': '~/.claude/inside.txt'},
            ],
        }
        reroot = setup_environment.ConfigHomeReroot(profile_dir, home, ['p'])

        with patch.object(setup_environment, 'get_real_user_home', return_value=home), \
                patch.object(Path, 'home', return_value=home):
            planned = setup_environment.planned_records(config, profile_dir, claude_dir=claude_dir, reroot=reroot)

        assert planned.files == frozenset({'agents/core.md', 'agents/optional.md', 'inside.txt'})
        assert planned.destinations == frozenset({str(outside)})
        assert planned.writes(LeftoverItem('file', 'agents/Optional.md', 'x'))
        assert planned.writes(LeftoverItem('destination', str(outside), 'x'))
        assert not planned.writes(LeftoverItem('file', 'agents/gone.md', 'x'))


class TestReportLines:
    """The summary block and the completion lines name every leftover and what the run does with it."""

    def _report(self, profile_dir: Path, *, untracked_note: bool = False) -> LeftoverReport:
        outside = str(profile_dir.parent / 'tool.txt')
        return LeftoverReport(
            profile_name='p',
            profile_dir=profile_dir,
            untracked_note=untracked_note,
            entries=(
                LeftoverEntry(LeftoverItem('file', 'rules/old.md', 'a'), 'removable', ''),
                LeftoverEntry(LeftoverItem('file', 'rules/locked.md', 'a'), 'unreadable', 'Permission denied'),
                LeftoverEntry(LeftoverItem('file', 'rules/edited.md', 'a'), 'changed', ''),
                LeftoverEntry(LeftoverItem('file', 'rules/gone.md', 'a'), 'gone', ''),
                LeftoverEntry(LeftoverItem('file', 'skills/x/a.md', 'a'), 'linked', 'now linked from profile src'),
                LeftoverEntry(LeftoverItem('destination', outside, 'a'), 'held', 'recorded by profile other'),
            ),
        )

    def test_lines(self, tmp_path: Path) -> None:
        profile_dir = tmp_path / 'p'
        outside = profile_dir.parent / 'tool.txt'
        assert self._report(profile_dir).lines() == [
            f'[leftover] file: {profile_dir / "rules" / "old.md"}',
            f'[cannot check: Permission denied] file: {profile_dir / "rules" / "locked.md"}',
            f'[changed since written: left in place, no longer tracked] file: {profile_dir / "rules" / "edited.md"}',
            f'[already gone: no longer tracked] file: {profile_dir / "rules" / "gone.md"}',
            f'[now linked from profile src: no longer tracked] file: {profile_dir / "skills" / "x" / "a.md"}',
            f'[kept: recorded by profile other] file outside ~/.claude: {outside}',
            'They stay in place.',
            setup_environment.LEFTOVERS_FLAG_FOOTER,
        ]

    def test_untracked_note_alone(self, tmp_path: Path) -> None:
        report = LeftoverReport(profile_name='team-1', profile_dir=tmp_path, entries=(), untracked_note=True)
        assert report.lines() == [
            (
                'Profile "team-1" was installed by a release that recorded no leftovers; '
                'they are tracked from this run on.'
            ),
        ]

    def test_footer_needs_a_leftover_that_stays(self, tmp_path: Path) -> None:
        report = LeftoverReport(
            profile_name='p', profile_dir=tmp_path, untracked_note=False,
            entries=(LeftoverEntry(LeftoverItem('file', 'rules/gone.md', 'a'), 'gone', ''),),
        )
        assert report.lines() == [f'[already gone: no longer tracked] file: {tmp_path / "rules" / "gone.md"}']

    def test_completion_sections(self, tmp_path: Path) -> None:
        profile_dir = tmp_path / 'p'
        outside = profile_dir.parent / 'tool.txt'
        assert self._report(profile_dir).completion_sections() == [
            ('Leftovers left in place (3; --remove-leftovers removes them):', [
                f'file: {profile_dir / "rules" / "old.md"}',
                f'file: {profile_dir / "rules" / "locked.md"} (cannot check: Permission denied)',
                f'file outside ~/.claude: {outside} (kept: recorded by profile other)',
            ]),
            ('No longer tracked:', [
                f'file: {profile_dir / "rules" / "edited.md"} (changed since written)',
                f'file: {profile_dir / "rules" / "gone.md"} (already gone)',
                f'file: {profile_dir / "skills" / "x" / "a.md"} (now linked from profile src)',
            ]),
        ]

    def test_summary_block_follows_the_stale_controls(self, tmp_path: Path) -> None:
        plan = setup_environment.InstallationPlan(
            config_name='P', config_source='p.yaml', config_source_type='local', config_version=None,
            leftovers=self._report(tmp_path / 'p', untracked_note=True),
            stale_controls_elsewhere=[setup_environment.StaleControlCopy('other', tmp_path / 's.json', ('DISABLE_UPDATES',))],
        )
        buffer = io.StringIO()
        setup_environment.display_installation_summary(plan, output=buffer)
        text = buffer.getvalue()
        heading = 'Leftovers of earlier runs (this configuration no longer installs them):'
        assert heading in text
        assert text.index('Stale update controls in other profiles') < text.index(heading)
        block = text.split(heading)[1]
        assert f'  [leftover] file: {tmp_path / "p" / "rules" / "old.md"}' in block
        assert '  They stay in place.' in block
        assert 'Profile "p" was installed by a release that recorded no leftovers' in block

    def test_no_block_without_content(self, tmp_path: Path) -> None:
        plan = setup_environment.InstallationPlan(
            config_name='P', config_source='p.yaml', config_source_type='local', config_version=None,
            leftovers=LeftoverReport(profile_name='p', profile_dir=tmp_path, entries=(), untracked_note=False),
        )
        buffer = io.StringIO()
        setup_environment.display_installation_summary(plan, output=buffer)
        assert 'Leftovers of earlier runs' not in buffer.getvalue()


class TestLeftoversManifestRecord:
    """The leftovers field carries what stays recorded and names what was dropped."""

    def test_first_install_writes_empty_lists(self) -> None:
        assert setup_environment.leftovers_manifest_record(None, run_at='2026-11-24T00:00:00+00:00') == {
            'run_at': '2026-11-24T00:00:00+00:00',
            'items': [],
            'removed': [],
            'dropped': [],
            'skipped': None,
            'failed': [],
            'kept': [],
        }

    def test_carried_and_dropped(self, tmp_path: Path) -> None:
        outside = str(tmp_path / 'tool.txt')
        report = LeftoverReport(
            profile_name='p', profile_dir=tmp_path / 'p', untracked_note=True,
            entries=(
                LeftoverEntry(LeftoverItem('file', 'rules/old.md', 'a'), 'removable', ''),
                LeftoverEntry(LeftoverItem('file', 'rules/locked.md', 'b'), 'unreadable', 'Permission denied'),
                LeftoverEntry(LeftoverItem('destination', outside, 'c'), 'held', 'recorded by profile other'),
                LeftoverEntry(LeftoverItem('file', 'rules/edited.md', 'd'), 'changed', ''),
                LeftoverEntry(LeftoverItem('file', 'rules/gone.md', 'e'), 'gone', ''),
                LeftoverEntry(LeftoverItem('file', 'rules/linked.md', 'f'), 'linked', 'now linked from profile src'),
            ),
        )

        record = setup_environment.leftovers_manifest_record(report, run_at='t')

        assert record['items'] == [
            {'kind': 'file', 'path': 'rules/old.md', 'sha256': 'a'},
            {'kind': 'file', 'path': 'rules/locked.md', 'sha256': 'b'},
            {'kind': 'destination', 'path': outside, 'sha256': 'c'},
        ]
        assert record['dropped'] == [
            {'label': 'file: rules/edited.md', 'reason': 'changed'},
            {'label': 'file: rules/gone.md', 'reason': 'gone'},
            {'label': 'file: rules/linked.md', 'reason': 'linked'},
        ]
        assert record['removed'] == []
        assert record['failed'] == []
        assert record['kept'] == [
            {'label': 'file: rules/locked.md', 'reason': 'cannot check: Permission denied'},
            {'label': f'file outside ~/.claude: {outside}', 'reason': 'kept: recorded by profile other'},
        ]
        assert record['skipped'] is None


class TestFileRecords:
    """files_written and machine_wide_destinations record a digest only for bytes the run wrote."""

    def test_digests_of_a_run_without_failures(self, tmp_path: Path) -> None:
        digest = _write(tmp_path / 'rules' / 'a.md', b'a')
        records = setup_environment.file_records(tmp_path, ['rules/a.md', 'rules/missing.md'], None, download_failed=False)
        assert records == [{'path': 'rules/a.md', 'sha256': digest}, {'path': 'rules/missing.md', 'sha256': None}]

    def test_a_failed_download_keeps_only_digests_the_previous_run_recorded(self, tmp_path: Path) -> None:
        same = _write(tmp_path / 'rules' / 'same.md', b'same')
        _write(tmp_path / 'rules' / 'changed.md', b'left by a failed download')
        _write(tmp_path / 'rules' / 'new.md', b'new')
        previous: dict[str, object] = {'files_written': [
            {'path': 'Rules/Same.md', 'sha256': same},
            {'path': 'rules/changed.md', 'sha256': _sha(b'as written before')},
        ]}

        records = setup_environment.file_records(
            tmp_path, ['rules/same.md', 'rules/changed.md', 'rules/new.md'], previous, download_failed=True,
        )

        assert records == [
            {'path': 'rules/same.md', 'sha256': same},
            {'path': 'rules/changed.md', 'sha256': None},
            {'path': 'rules/new.md', 'sha256': None},
        ]

    def test_a_hooks_helpers_module_is_marked(self, tmp_path: Path) -> None:
        script, helper = _write(tmp_path / 'hooks' / 'a.py', b'a'), _write(tmp_path / 'hooks' / 'h.py', b'h')
        helpers = setup_environment.planned_hook_helpers(
            {'hooks': {'files': ['src/a.py'], 'helpers': ['https://host/lib/h.py?ref=main']}},
        )
        assert helpers == frozenset({'hooks/h.py'})

        records = setup_environment.file_records(
            tmp_path, ['hooks/a.py', 'hooks/h.py'], None, download_failed=False, hook_helpers=helpers,
        )

        assert records == [
            {'path': 'hooks/a.py', 'sha256': script}, {'path': 'hooks/h.py', 'sha256': helper, 'hook_helper': True},
        ]

    def test_destination_records_follow_the_same_rule(self, tmp_path: Path) -> None:
        claude_dir = tmp_path / '.claude'
        kept = _write(tmp_path / 'out' / 'kept.txt', b'kept')
        _write(tmp_path / 'out' / 'new.txt', b'new')
        downloads = [
            {'source': 'https://host/kept.txt', 'dest': str(tmp_path / 'out' / 'kept.txt')},
            {'source': 'https://host/new.txt', 'dest': str(tmp_path / 'out' / 'new.txt')},
        ]
        previous: dict[str, object] = {'machine_wide_destinations': [
            {'dest': str(tmp_path / 'out' / 'kept.txt'), 'source': 'https://host/kept.txt', 'sha256': kept},
        ]}

        failed = setup_environment.destination_records(
            downloads, 'https://host/c.yaml', None, claude_dir, previous, download_failed=True,
        )
        clean = setup_environment.destination_records(
            downloads, 'https://host/c.yaml', None, claude_dir, previous, download_failed=False,
        )

        assert [record['sha256'] for record in failed] == [kept, None]
        assert [record['sha256'] for record in clean] == [kept, _sha(b'new')]
        assert [record['source'] for record in clean] == ['https://host/kept.txt', 'https://host/new.txt']


class TestWriteManifestLeftovers:
    """Every manifest carries the leftovers field."""

    def test_default_and_given_record(self, tmp_path: Path) -> None:
        assert _REAL_WRITE_MANIFEST(tmp_path / 'a', 'a', None, 'a.yaml', 'repo', None, ['a'], None)
        default = json.loads((tmp_path / 'a' / 'manifest.json').read_text(encoding='utf-8'))['leftovers']
        assert {key: value for key, value in default.items() if key != 'run_at'} == {
            'items': [], 'removed': [], 'dropped': [], 'skipped': None, 'failed': [], 'kept': [],
        }
        assert isinstance(default['run_at'], str)
        assert default['run_at']

        given = setup_environment.leftovers_manifest_record(None, run_at='t')
        files: list[dict[str, str | None]] = [{'path': 'rules/a.md', 'sha256': 'ab'}]
        assert _REAL_WRITE_MANIFEST(
            tmp_path / 'b', 'b', None, 'b.yaml', 'repo', None, ['b'], None, leftovers=given, files_written=files,
        )
        data = json.loads((tmp_path / 'b' / 'manifest.json').read_text(encoding='utf-8'))
        assert data['leftovers'] == given
        assert data['files_written'] == files
