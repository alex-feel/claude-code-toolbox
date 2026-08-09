"""Tests for deselection reconciliation: a re-run that deselects a component
removes what an earlier run installed.

The removal plan derives entirely from the unfiltered config
(collect_deselected_items), execution mirrors each installer's target-path
resolution (execute_deselection_cleanup), and the shared settings.json hook
union is reconciled by exact-entry stripping (_strip_hooks_from_settings).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

import setup_environment
from tests.test_setup_environment import _component_args
from tests.test_setup_environment import _components_config


def _resolve(config: dict[str, Any], **kw: Any) -> setup_environment.ComponentSelection:
    return setup_environment.resolve_component_selection(
        config['components'], _component_args(**kw),
    )


class TestCollectDeselectedItems:
    """Inverse-filter semantics of the removal plan."""

    def test_full_selection_collects_nothing(self) -> None:
        """When every component is selected the plan is empty."""
        config = _components_config()
        deselected = setup_environment.collect_deselected_items(
            config, _resolve(config, select='all'),
        )
        assert not setup_environment.has_deselected_items(deselected)

    def test_inactive_selection_collects_nothing(self) -> None:
        """A config without components produces an empty plan."""
        deselected = setup_environment.collect_deselected_items(
            {'name': 'Test'}, setup_environment.ComponentSelection(),
        )
        assert not setup_environment.has_deselected_items(deselected)

    def test_deselected_component_items_are_collected(self) -> None:
        """Items claimed only by deselected components enter the plan."""
        config = _components_config()
        deselected = setup_environment.collect_deselected_items(
            config, _resolve(config, select='none'),
        )
        assert deselected['agents'] == ['agents/a.md']
        assert [s['name'] for s in deselected['mcp-servers']] == ['srv2']
        assert deselected['hooks-files'] == ['hooks/h.py']
        assert [e['id'] for e in deselected['hooks-events']] == ['post-edit']

    def test_unclaimed_and_kept_items_stay_out_of_the_plan(self) -> None:
        """Mandatory items and items kept by a selected component never enter."""
        config = _components_config()
        deselected = setup_environment.collect_deselected_items(
            config, _resolve(config, select='all'),
        )
        assert deselected == {
            'agents': [], 'slash-commands': [], 'rules': [], 'skills': [],
            'mcp-servers': [], 'files-to-download': [],
            'hooks-files': [], 'hooks-events': [],
        }

    def test_plan_is_computed_from_the_unfiltered_config(self) -> None:
        """Filtering the config first would lose the dropped items."""
        config = _components_config()
        selection = _resolve(config, select='none')
        deselected = setup_environment.collect_deselected_items(config, selection)
        setup_environment.apply_component_selection(config, selection)
        after_filter = setup_environment.collect_deselected_items(config, selection)
        assert setup_environment.has_deselected_items(deselected)
        assert not setup_environment.has_deselected_items(after_filter)


class TestExecuteDeselectionCleanup:
    """Removal execution against a simulated prior installation."""

    @staticmethod
    def _dirs(base: Path) -> dict[str, Path]:
        dirs = {name: base / name for name in ('agents', 'commands', 'rules', 'skills', 'hookfiles')}
        for d in dirs.values():
            d.mkdir()
        return dirs

    def test_removes_installed_artifacts_and_spares_the_rest(self, tmp_path: Path) -> None:
        """Deselected files, skill dirs, and servers are removed; others survive."""
        dirs = self._dirs(tmp_path)
        (dirs['agents'] / 'a.md').write_text('x')
        (dirs['agents'] / 'b.md').write_text('x')
        (dirs['hookfiles'] / 'h.py').write_text('x')
        (dirs['hookfiles'] / 'k.py').write_text('x')
        (dirs['skills'] / 'sk').mkdir()
        (dirs['skills'] / 'sk' / 'SKILL.md').write_text('x')
        expanded = tmp_path / 'expanded'
        expanded.mkdir()
        dest_file = expanded / 'gdir_g.txt'
        dest_file.write_text('x')

        deselected: dict[str, list[Any]] = {
            'agents': ['agents/a.md'],
            'slash-commands': [], 'rules': [],
            'skills': [{'name': 'sk'}],
            'mcp-servers': [{'name': 'srv2', 'scope': 'user'}],
            'files-to-download': [{'source': 'files/g.txt', 'dest': '~/gdir/g.txt'}],
            'hooks-files': ['hooks/h.py'],
            'hooks-events': [],
        }
        calls: list[list[str]] = []

        def fake_run(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, '', '')

        def fake_tilde(path: str, resolve: bool = False) -> str:
            del resolve
            return str(expanded / path.replace('~/', '').replace('/', '_'))

        with (
            patch.object(setup_environment, 'normalize_tilde_path', side_effect=fake_tilde),
            patch.object(setup_environment, 'find_command', return_value='claude'),
            patch.object(setup_environment, 'run_command', side_effect=fake_run),
        ):
            setup_environment.execute_deselection_cleanup(
                deselected,
                agents_dir=dirs['agents'],
                commands_dir=dirs['commands'],
                rules_dir=dirs['rules'],
                skills_dir=dirs['skills'],
                hooks_dir=dirs['hookfiles'],
                is_isolated=True,
            )

        assert not (dirs['agents'] / 'a.md').exists()
        assert (dirs['agents'] / 'b.md').exists()
        assert not (dirs['hookfiles'] / 'h.py').exists()
        assert (dirs['hookfiles'] / 'k.py').exists()
        assert not (dirs['skills'] / 'sk').exists()
        assert not dest_file.exists()
        assert calls == [['claude', 'mcp', 'remove', 'srv2', '--scope', 'user']]

    def test_absent_targets_are_skipped_silently(self, tmp_path: Path) -> None:
        """A first run has nothing to remove; cleanup is a quiet no-op."""
        dirs = self._dirs(tmp_path)
        deselected: dict[str, list[Any]] = {
            'agents': ['agents/a.md'], 'slash-commands': [], 'rules': [],
            'skills': [{'name': 'sk'}], 'mcp-servers': [],
            'files-to-download': [], 'hooks-files': [], 'hooks-events': [],
        }
        with patch.object(setup_environment, 'success') as mock_success:
            setup_environment.execute_deselection_cleanup(
                deselected,
                agents_dir=dirs['agents'],
                commands_dir=dirs['commands'],
                rules_dir=dirs['rules'],
                skills_dir=dirs['skills'],
                hooks_dir=dirs['hookfiles'],
                is_isolated=True,
            )
        assert not mock_success.called

    def test_profile_scope_needs_no_explicit_removal(self, tmp_path: Path) -> None:
        """Profile-scoped servers are reconciled by the mcp.json rebuild."""
        dirs = self._dirs(tmp_path)
        deselected: dict[str, list[Any]] = {
            'agents': [], 'slash-commands': [], 'rules': [], 'skills': [],
            'mcp-servers': [{'name': 'p', 'scope': 'profile'}],
            'files-to-download': [], 'hooks-files': [], 'hooks-events': [],
        }
        with (
            patch.object(setup_environment, 'find_command', return_value='claude'),
            patch.object(setup_environment, 'run_command') as mock_run,
        ):
            setup_environment.execute_deselection_cleanup(
                deselected,
                agents_dir=dirs['agents'],
                commands_dir=dirs['commands'],
                rules_dir=dirs['rules'],
                skills_dir=dirs['skills'],
                hooks_dir=dirs['hookfiles'],
                is_isolated=True,
            )
        assert not mock_run.called


class TestStripHooksFromSettings:
    """Exact-entry reconciliation of the shared settings.json hook union."""

    def test_deselected_entries_are_stripped_and_others_kept(self, tmp_path: Path) -> None:
        """Only the deselected events' generated entries are removed."""
        hooks_dir = tmp_path / 'hookfiles'
        hooks_dir.mkdir()
        deselected_events = [
            {'event': 'PreToolUse', 'matcher': 'Bash', 'type': 'prompt', 'prompt': 'gate', 'id': 'x'},
        ]
        kept_events = [
            {'event': 'PreToolUse', 'matcher': 'Bash', 'type': 'prompt', 'prompt': 'other'},
        ]
        hooks_json = setup_environment._build_hooks_json(
            {'events': deselected_events + kept_events}, hooks_dir,
        )
        settings_path = tmp_path / 'settings.json'
        settings_path.write_text(json.dumps({'hooks': hooks_json, 'model': 'opus'}))

        removed = setup_environment._strip_hooks_from_settings(
            settings_path, deselected_events, hooks_dir,
        )

        assert removed == 1
        final = json.loads(settings_path.read_text())
        assert final['model'] == 'opus'
        remaining = final['hooks']['PreToolUse']
        assert len(remaining) == 1
        assert remaining[0]['hooks'][0]['prompt'] == 'other'

    def test_missing_file_and_empty_plan_are_noops(self, tmp_path: Path) -> None:
        """No file or no deselected events means nothing to reconcile."""
        hooks_dir = tmp_path
        assert setup_environment._strip_hooks_from_settings(tmp_path / 'absent.json', [{'event': 'Stop'}], hooks_dir) == 0
        settings_path = tmp_path / 'settings.json'
        settings_path.write_text('{}')
        assert setup_environment._strip_hooks_from_settings(settings_path, [], hooks_dir) == 0
