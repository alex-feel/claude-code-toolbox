"""Tests for hook files that only a leftover of the base settings.json still runs.

A run given --remove-leftovers removes the settings.json leftovers in Step 23
before it looks at the hook files, so every run lists a hook file against
settings.json without them: a file that only a leftover hook group or status
line runs is itself a leftover the flag removes with it, and so is a hook
helper beside it, never one listed as kept that the flag then removes. Wiring
the user wrote, and a profile that links hooks/ from this one, keep the file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts import setup_environment
from scripts.setup_environment import InstalledProfile
from scripts.setup_environment import LeftoverItem
from scripts.setup_environment import LeftoverReport
from scripts.setup_environment import LiveLeftoverState
from scripts.setup_environment import PlannedRecords

digest = setup_environment.leftover_digest


@pytest.fixture
def claude_dir(tmp_path: Path) -> Path:
    """The base ~/.claude directory."""
    directory = tmp_path / '.claude'
    directory.mkdir()
    return directory


def _hook(command: str) -> dict[str, Any]:
    return {'type': 'command', 'command': command}


def _command(claude_dir: Path, name: str = 'a.py') -> str:
    """A hook command running hooks/NAME of the base profile through uv, as the setup spells it."""
    return f'uv run --no-project --python 3.12 "{(claude_dir / "hooks" / name).as_posix()}"'


def _stop_group(claude_dir: Path) -> dict[str, Any]:
    return {'matcher': '', 'hooks': [_hook(_command(claude_dir))]}


def _layout(
    claude_dir: Path,
    written: dict[str, Any],
    *,
    content: dict[str, Any] | None = None,
    helper: bool = False,
) -> dict[str, Any]:
    """Install hooks/a.py (and hooks/h.py as its helper) with settings.json as the setup wrote it, or as content."""
    script = claude_dir / 'hooks' / 'a.py'
    script.parent.mkdir()
    script.write_bytes(b'import h\n')
    (claude_dir / 'settings.json').write_text(json.dumps(written if content is None else content), encoding='utf-8')
    records: list[dict[str, Any]] = [{'path': 'hooks/a.py', 'sha256': setup_environment._sha256_of_file(script)}]
    if helper:
        module = claude_dir / 'hooks' / 'h.py'
        module.write_bytes(b'VALUE = 1\n')
        records.append({'path': 'hooks/h.py', 'sha256': setup_environment._sha256_of_file(module), 'hook_helper': True})
    return {
        'settings_written': setup_environment.settings_write_records(written),
        'files_written': records,
        'leftovers': {'items': []},
    }


def _live(claude_dir: Path, dependents: list[InstalledProfile] | None = None) -> LiveLeftoverState:
    return LiveLeftoverState.for_profile(
        claude_dir, claude_dir.parent,
        settings_files=setup_environment.leftover_settings_files(claude_dir, isolated=False, before_consent=True),
        dependents=dependents or [],
    )


def _compute(
    manifest: dict[str, Any],
    claude_dir: Path,
    *,
    planned: PlannedRecords | None = None,
    live: LiveLeftoverState | None = None,
) -> LeftoverReport:
    return setup_environment.compute_profile_leftovers(
        manifest, claude_dir,
        profile_name='base',
        planned=planned or PlannedRecords(),
        live=live or _live(claude_dir),
        claude_dir=claude_dir,
    )


def _states(report: LeftoverReport) -> dict[str, str]:
    return {entry.item.label(): entry.state for entry in report.entries}


def _details(report: LeftoverReport) -> dict[str, tuple[str, str]]:
    return {entry.item.label(): (entry.state, entry.detail) for entry in report.entries}


class TestHookFileWiredByASettingsLeftover:
    """In every run, wiring that a settings leftover holds keeps no hook file."""

    def test_a_group_the_flag_removes_does_not_keep_the_file(self, claude_dir: Path) -> None:
        group = _stop_group(claude_dir)
        manifest = _layout(claude_dir, {'hooks': {'Stop': [group]}})

        states = _states(_compute(manifest, claude_dir))

        assert states == {
            'file: hooks/a.py': 'removable',
            f'settings.json: hooks.Stop group {digest(group)[:12]}': 'removable',
        }

    def test_a_changed_group_that_still_holds_the_recorded_hook_does_not_keep_the_file(self, claude_dir: Path) -> None:
        """Step 23 removes the setup's hook from a group the user added to, so that hook keeps nothing either."""
        group = _stop_group(claude_dir)
        changed = {'matcher': '', 'hooks': [*group['hooks'], _hook('echo mine')]}
        manifest = _layout(claude_dir, {'hooks': {'Stop': [group]}}, content={'hooks': {'Stop': [changed]}})

        states = _states(_compute(manifest, claude_dir))

        assert states == {
            'file: hooks/a.py': 'removable',
            f'settings.json: hooks.Stop group {digest(group)[:12]}': 'partial',
        }

    def test_a_status_line_the_flag_removes_does_not_keep_the_file(self, claude_dir: Path) -> None:
        manifest = _layout(claude_dir, {'statusLine': {'type': 'command', 'command': _command(claude_dir)}})

        states = _states(_compute(manifest, claude_dir))

        assert states == {'file: hooks/a.py': 'removable', 'settings.json: statusLine': 'removable'}

    def test_a_helper_beside_a_file_only_a_leftover_wires_is_a_leftover_too(self, claude_dir: Path) -> None:
        manifest = _layout(claude_dir, {'hooks': {'Stop': [_stop_group(claude_dir)]}}, helper=True)

        states = _states(_compute(manifest, claude_dir))

        assert states['file: hooks/a.py'] == 'removable'
        assert states['file: hooks/h.py'] == 'removable'

    def test_a_selection_keeps_the_helper_a_leftover_beside_a_file_only_a_leftover_wires(self, claude_dir: Path) -> None:
        """The summary of a run with selected components keeps the states computed against the same view."""
        manifest = _layout(claude_dir, {'hooks': {'Stop': [_stop_group(claude_dir)]}}, helper=True)
        report = _compute(manifest, claude_dir)
        selected = setup_environment.planned_records({}, claude_dir, claude_dir=claude_dir, base=True)

        refined = report.refined(linked_entries=frozenset(), link_source='base', selected=selected)

        assert _states(refined)['file: hooks/h.py'] == 'removable'
        assert _states(refined)['file: hooks/a.py'] == 'removable'

    def test_a_status_line_step_18_points_elsewhere_does_not_keep_the_file(self, claude_dir: Path) -> None:
        """A renamed status-line file: Step 18 overwrites the command before Step 23 looks at the old file."""
        manifest = _layout(claude_dir, {'statusLine': {'type': 'command', 'command': _command(claude_dir)}})
        planned = setup_environment.planned_records(
            {'hooks': {'files': ['hooks/b.py']}, 'status-line': {'file': 'hooks/b.py'}},
            claude_dir, claude_dir=claude_dir, base=True,
        )
        status_line = {'type': 'command', 'command': _command(claude_dir, 'b.py')}
        record = {'kind': 'setting', 'path': ['statusLine'], 'sha256': digest(status_line)}
        assert LeftoverItem.from_record(record, claude_dir=claude_dir) in planned.settings

        states = _states(_compute(manifest, claude_dir, planned=planned))

        assert states == {'file: hooks/a.py': 'removable'}

    def test_wiring_a_user_wrote_keeps_the_file(self, claude_dir: Path) -> None:
        group = _stop_group(claude_dir)
        user_group = {'matcher': 'Bash', 'hooks': [_hook(_command(claude_dir))]}
        manifest = _layout(
            claude_dir, {'hooks': {'Stop': [group]}}, content={'hooks': {'Stop': [group], 'PreToolUse': [user_group]}},
            helper=True,
        )

        report = _compute(manifest, claude_dir)

        assert _details(report) == {
            'file: hooks/a.py': ('referenced', f'still wired in {claude_dir / "settings.json"} hooks.PreToolUse'),
            'file: hooks/h.py': ('held', 'stays with hooks/a.py, which is still wired'),
            f'settings.json: hooks.Stop group {digest(group)[:12]}': ('removable', ''),
        }

    def test_a_status_line_changed_since_written_keeps_the_file(self, claude_dir: Path) -> None:
        """A status line the user changed is no leftover the flag removes, so the file it runs stays wired."""
        written = {'statusLine': {'type': 'command', 'command': _command(claude_dir)}}
        changed = {'statusLine': {'type': 'command', 'command': _command(claude_dir), 'padding': 2}}
        manifest = _layout(claude_dir, written, content=changed)

        states = _states(_compute(manifest, claude_dir))

        assert states == {'file: hooks/a.py': 'referenced', 'settings.json: statusLine': 'changed'}

    def test_a_dependent_that_still_wires_the_file_keeps_it(self, claude_dir: Path) -> None:
        """A profile linking hooks/ from the base runs the file until its own run rebuilds its config.json."""
        lab = claude_dir / 'lab'
        lab.mkdir()
        (lab / 'config.json').write_text(json.dumps({'hooks': {'Stop': [
            {'matcher': '', 'hooks': [_hook(f'uv run "{(lab / "hooks" / "a.py").as_posix()}"')]},
        ]}}), encoding='utf-8')
        dependents = [InstalledProfile('lab', lab, lab / 'manifest.json', {'link': {'dirs': ['hooks'], 'source': 'base'}})]
        manifest = _layout(claude_dir, {'hooks': {'Stop': [_stop_group(claude_dir)]}}, helper=True)

        details = _details(_compute(manifest, claude_dir, live=_live(claude_dir, dependents)))

        assert details['file: hooks/a.py'] == ('referenced', (
            f'still wired in profile lab ({lab / "config.json"} hooks.Stop) until that profile is refreshed; '
            'a later run with --remove-leftovers removes it'
        ))
        assert details['file: hooks/h.py'] == ('held', 'stays with hooks/a.py, which is still wired')
