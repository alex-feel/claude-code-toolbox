"""Unit tests for the runtime hooks-files consistency validation.

validate_hooks_files_consistency() in setup_environment.py is the runtime
twin of the Pydantic model validator of the same name (verdict parity is
enforced by tests/scripts/models/test_hooks_consistency_parity.py). These
tests cover the twin's behavior on raw resolved-config dictionaries,
including structural shapes the Pydantic model rejects at the typing layer,
plus the hooks.files-aware file-reference classification and the quoted
command construction in _build_hooks_json()/_build_profile_settings().
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from scripts.setup_environment import _build_file_command
from scripts.setup_environment import _build_hooks_json
from scripts.setup_environment import _build_profile_settings
from scripts.setup_environment import _hook_file_basename
from scripts.setup_environment import validate_hooks_files_consistency


class TestHookFileBasename:
    """Basename extraction from hooks.files entries."""

    @pytest.mark.parametrize(
        ('path_or_url', 'expected'),
        [
            ('script.py', 'script.py'),
            ('hooks/script.py', 'script.py'),
            ('/home/user/script.py', 'script.py'),
            ('C:\\Users\\user\\script.py', 'script.py'),
            ('https://example.com/path/to/script.py', 'script.py'),
            ('https://example.com/path/to/script.py?ref=main', 'script.py'),
            ('http://example.com/script.py', 'script.py'),
            ('', ''),
        ],
    )
    def test_extracts_basename(self, path_or_url: str, expected: str) -> None:
        """Every supported path and URL form reduces to its basename."""
        assert _hook_file_basename(path_or_url) == expected


def _consistent_config() -> dict[str, Any]:
    """Return a fully consistent hooks + status-line configuration."""
    return {
        'hooks': {
            'files': [
                'https://example.com/hooks/a.py',
                'configs/a_cfg.yaml',
                'hooks/sl.py',
                'configs/sl_cfg.yaml',
            ],
            'events': [
                {
                    'event': 'PostToolUse',
                    'matcher': 'Edit',
                    'type': 'command',
                    'command': 'a.py',
                    'config': 'a_cfg.yaml',
                },
                {'event': 'PreToolUse', 'matcher': 'Bash', 'type': 'prompt', 'prompt': 'check'},
            ],
        },
        'status-line': {'file': 'sl.py', 'config': 'sl_cfg.yaml', 'padding': 0},
    }


class TestValidateHooksFilesConsistency:
    """Runtime consistency verdicts over resolved configuration dicts."""

    def test_consistent_config_passes(self) -> None:
        """A fully cross-referenced hooks + status-line config yields no errors."""
        assert validate_hooks_files_consistency(_consistent_config()) == []

    def test_no_hooks_key_passes(self) -> None:
        """A config without hooks or status-line has nothing to check."""
        assert validate_hooks_files_consistency({'name': 'x'}) == []

    def test_null_hooks_passes(self) -> None:
        """An explicit hooks null (deletion request) has nothing to check."""
        assert validate_hooks_files_consistency({'hooks': None}) == []

    def test_status_line_without_hooks_fails(self) -> None:
        """A status-line without hooks has no hooks.files to carry its script."""
        errors = validate_hooks_files_consistency({'status-line': {'file': 'sl.py'}})
        assert len(errors) == 1
        assert 'requires hooks.files to be configured' in errors[0]
        assert 'sl.py' in errors[0]

    def test_missing_command_reference_fails(self) -> None:
        """A command referencing a file absent from hooks.files is reported."""
        config = {
            'hooks': {
                'files': ['hooks/a.py'],
                'events': [{'event': 'PostToolUse', 'command': 'missing.py'}],
            },
        }
        errors = validate_hooks_files_consistency(config)
        assert any('command "missing.py" not found in hooks.files' in e for e in errors)

    def test_missing_config_reference_fails(self) -> None:
        """An event config referencing a file absent from hooks.files is reported."""
        config = {
            'hooks': {
                'files': ['hooks/a.py'],
                'events': [
                    {'event': 'PostToolUse', 'command': 'a.py', 'config': 'missing.yaml'},
                ],
            },
        }
        errors = validate_hooks_files_consistency(config)
        assert any('config "missing.yaml" not found in hooks.files' in e for e in errors)

    def test_config_query_parameters_stripped(self) -> None:
        """Query parameters on a config reference do not defeat the match."""
        config = {
            'hooks': {
                'files': ['hooks/a.py', 'configs/c.yaml'],
                'events': [
                    {'event': 'PostToolUse', 'command': 'a.py', 'config': 'c.yaml?ref=main'},
                ],
            },
        }
        assert validate_hooks_files_consistency(config) == []

    def test_unused_file_fails(self) -> None:
        """A hooks.files entry no event or status-line references is reported."""
        config = {
            'hooks': {
                'files': ['hooks/a.py', 'hooks/b.py'],
                'events': [{'event': 'PostToolUse', 'command': 'a.py'}],
            },
        }
        errors = validate_hooks_files_consistency(config)
        assert len(errors) == 1
        assert "unused files: ['b.py']" in errors[0]

    def test_missing_type_defaults_to_command(self) -> None:
        """An event without a type is a command hook and gets file checks."""
        config = {
            'hooks': {
                'files': ['hooks/a.py'],
                'events': [{'event': 'PostToolUse', 'command': 'missing.py'}],
            },
        }
        errors = validate_hooks_files_consistency(config)
        assert any('missing.py' in e for e in errors)

    @pytest.mark.parametrize('hook_type', ['prompt', 'http', 'agent'])
    def test_non_command_types_excluded(self, hook_type: str) -> None:
        """Prompt, http, and agent hooks never participate in file checks."""
        config = {
            'hooks': {
                'files': ['hooks/a.py'],
                'events': [
                    {'event': 'PostToolUse', 'command': 'a.py'},
                    # A file-like command on a non-command hook is ignored
                    {'event': 'PreToolUse', 'type': hook_type, 'command': 'missing.py'},
                ],
            },
        }
        assert validate_hooks_files_consistency(config) == []

    def test_status_line_file_requires_exact_basename(self) -> None:
        """A path-form status-line.file never matches; the file entry is a basename."""
        config = {
            'hooks': {
                'files': ['hooks/sl.py'],
                'events': [],
            },
            'status-line': {'file': 'hooks/sl.py'},
        }
        errors = validate_hooks_files_consistency(config)
        assert any('status-line.file "hooks/sl.py" not found' in e for e in errors)

    def test_status_line_config_matches_by_basename(self) -> None:
        """A path-form status-line.config matches through basename extraction."""
        config = {
            'hooks': {
                'files': ['hooks/sl.py', 'configs/sl_cfg.yaml'],
                'events': [],
            },
            'status-line': {'file': 'sl.py', 'config': 'configs/sl_cfg.yaml'},
        }
        assert validate_hooks_files_consistency(config) == []

    def test_missing_status_line_config_fails(self) -> None:
        """A status-line.config absent from hooks.files is reported."""
        config = {
            'hooks': {
                'files': ['hooks/sl.py'],
                'events': [],
            },
            'status-line': {'file': 'sl.py', 'config': 'missing.yaml'},
        }
        errors = validate_hooks_files_consistency(config)
        assert any('status-line.config "missing.yaml" not found' in e for e in errors)

    def test_whitespace_stripped_before_matching(self) -> None:
        """Leading and trailing whitespace on references does not defeat the match."""
        config = {
            'hooks': {
                'files': ['hooks/a.py'],
                'events': [{'event': 'PostToolUse', 'command': '  a.py  '}],
            },
        }
        assert validate_hooks_files_consistency(config) == []

    def test_all_errors_collected(self) -> None:
        """Every violation is reported in one pass, not only the first."""
        config = {
            'hooks': {
                'files': ['hooks/a.py', 'hooks/unused.py'],
                'events': [
                    {'event': 'PostToolUse', 'command': 'missing1.py'},
                    {'event': 'PreToolUse', 'command': 'missing2.py'},
                ],
            },
            'status-line': {'file': 'missing_sl.py'},
        }
        errors = validate_hooks_files_consistency(config)
        joined = '\n'.join(errors)
        assert 'missing1.py' in joined
        assert 'missing2.py' in joined
        assert 'missing_sl.py' in joined
        assert 'unused files' in joined

    def test_hooks_non_mapping_fails(self) -> None:
        """A non-mapping hooks value is a structural error."""
        errors = validate_hooks_files_consistency({'hooks': 'not-a-dict'})
        assert errors == ["'hooks' must be a mapping with 'files' and 'events' entries"]

    def test_files_non_list_fails(self) -> None:
        """A non-list hooks.files value is a structural error."""
        errors = validate_hooks_files_consistency({'hooks': {'files': 'a.py'}})
        assert errors == ["'hooks.files' must be a list of file paths or URLs"]

    def test_events_non_list_fails(self) -> None:
        """A non-list hooks.events value is a structural error."""
        errors = validate_hooks_files_consistency({'hooks': {'files': [], 'events': 'x'}})
        assert errors == ["'hooks.events' must be a list of event mappings"]

    def test_status_line_non_mapping_fails(self) -> None:
        """A non-mapping status-line value is a structural error."""
        errors = validate_hooks_files_consistency({'status-line': 'sl.py'})
        assert "'status-line' must be a mapping with a 'file' entry" in errors

    def test_non_dict_event_reported_and_unused_check_suppressed(self) -> None:
        """A non-mapping event is reported; the unused-files verdict is withheld."""
        config = {
            'hooks': {
                'files': ['hooks/a.py'],
                'events': ['not-a-dict'],
            },
        }
        errors = validate_hooks_files_consistency(config)
        assert errors == ['hooks.events[0] must be a mapping']

    def test_non_string_command_reported(self) -> None:
        """A non-string command is reported as a structural error."""
        config = {
            'hooks': {
                'files': ['hooks/a.py'],
                'events': [{'event': 'PostToolUse', 'command': 123}],
            },
        }
        errors = validate_hooks_files_consistency(config)
        assert 'hooks.events[0] command must be a string' in errors

    def test_non_string_file_entry_reported(self) -> None:
        """A non-string hooks.files entry is reported as a structural error."""
        config = {
            'hooks': {
                'files': [42],
                'events': [],
            },
        }
        errors = validate_hooks_files_consistency(config)
        assert 'hooks.files[0] must be a string path or URL' in errors


class TestBuildHooksJsonFileReferenceClassification:
    """hooks.files-aware file-reference classification in _build_hooks_json."""

    def test_listed_filename_with_spaces_is_file_reference(self, tmp_path: Path) -> None:
        """A space-containing basename listed in hooks.files builds a path command."""
        hooks = {
            'files': ['hooks/my hook.sh'],
            'events': [
                {'event': 'PreToolUse', 'matcher': 'Bash', 'type': 'command', 'command': 'my hook.sh'},
            ],
        }
        built = _build_hooks_json(hooks, tmp_path)
        command = built['PreToolUse'][0]['hooks'][0]['command']
        expected = (tmp_path / 'my hook.sh').as_posix()
        assert command == f'"{expected}"'

    def test_unlisted_command_with_spaces_stays_direct(self, tmp_path: Path) -> None:
        """A space-containing command absent from hooks.files passes through as-is."""
        hooks = {
            'files': ['hooks/a.py'],
            'events': [
                {'event': 'PostToolUse', 'matcher': 'Edit', 'type': 'command', 'command': 'a.py'},
                {'event': 'Notification', 'matcher': '', 'type': 'command', 'command': 'echo "done"'},
            ],
        }
        built = _build_hooks_json(hooks, tmp_path)
        assert built['Notification'][0]['hooks'][0]['command'] == 'echo "done"'

    def test_no_files_key_keeps_space_heuristic(self, tmp_path: Path) -> None:
        """Without hooks.files, spaceless commands stay file references."""
        hooks = {
            'events': [
                {'event': 'PostToolUse', 'matcher': 'Edit', 'type': 'command', 'command': 'a.py'},
            ],
        }
        built = _build_hooks_json(hooks, tmp_path)
        command = built['PostToolUse'][0]['hooks'][0]['command']
        expected = (tmp_path / 'a.py').as_posix()
        assert command == f'uv run --no-project --python 3.12 "{expected}"'


class TestBuildFileCommandQuoting:
    """Quoted command construction shared by hooks and statusLine builders."""

    def test_python_script_with_config(self) -> None:
        """Python scripts run via uv with both paths quoted."""
        hooks_dir = Path('/home/john smith/.claude/hooks')
        command = _build_file_command('a.py', 'a_cfg.yaml', hooks_dir)
        script = (hooks_dir / 'a.py').as_posix()
        config = (hooks_dir / 'a_cfg.yaml').as_posix()
        assert command == f'uv run --no-project --python 3.12 "{script}" "{config}"'

    @pytest.mark.parametrize('extension', ['js', 'mjs', 'cjs'])
    def test_javascript_runs_via_node(self, extension: str) -> None:
        """JavaScript scripts run via node with the path quoted."""
        hooks_dir = Path('/tmp/hooks')
        command = _build_file_command(f'a.{extension}', None, hooks_dir)
        script = (hooks_dir / f'a.{extension}').as_posix()
        assert command == f'node "{script}"'

    def test_other_file_executes_directly(self) -> None:
        """Non-Python, non-JavaScript files execute directly, path quoted."""
        hooks_dir = Path('/tmp/hooks')
        command = _build_file_command('a.sh', None, hooks_dir)
        assert command == f'"{(hooks_dir / "a.sh").as_posix()}"'

    def test_query_parameters_stripped_from_both_references(self) -> None:
        """Query parameters never reach the built paths."""
        hooks_dir = Path('/tmp/hooks')
        command = _build_file_command('a.py?ref=main', 'c.yaml?ref=main', hooks_dir)
        script = (hooks_dir / 'a.py').as_posix()
        config = (hooks_dir / 'c.yaml').as_posix()
        assert command == f'uv run --no-project --python 3.12 "{script}" "{config}"'


class TestStatusLineCommandConstruction:
    """statusLine command construction goes through the shared builder."""

    def test_python_status_line_quoted_with_config(self, tmp_path: Path) -> None:
        """A Python statusLine builds a quoted uv command with its config."""
        settings = _build_profile_settings(
            {'statusLine': {'file': 'sl.py', 'config': 'sl_cfg.yaml', 'padding': 0}},
            tmp_path,
        )
        script = (tmp_path / 'sl.py').as_posix()
        config = (tmp_path / 'sl_cfg.yaml').as_posix()
        assert settings['statusLine'] == {
            'type': 'command',
            'command': f'uv run --no-project --python 3.12 "{script}" "{config}"',
            'padding': 0,
        }

    def test_javascript_status_line_runs_via_node(self, tmp_path: Path) -> None:
        """A JavaScript statusLine runs via node, matching command hooks."""
        settings = _build_profile_settings({'statusLine': {'file': 'sl.js'}}, tmp_path)
        script = (tmp_path / 'sl.js').as_posix()
        assert settings['statusLine']['command'] == f'node "{script}"'
