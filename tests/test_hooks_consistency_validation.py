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

from scripts.setup_environment import LinkSource
from scripts.setup_environment import _build_file_command
from scripts.setup_environment import _build_hooks_json
from scripts.setup_environment import _build_profile_settings
from scripts.setup_environment import _hook_file_basename
from scripts.setup_environment import replay_source_snapshot
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

    def test_status_line_empty_or_missing_file_fails(self) -> None:
        """The status-line file field mirrors the model: required and non-empty."""
        base_hooks = {'files': ['hooks/sl.py'], 'events': []}
        missing = validate_hooks_files_consistency(
            {'hooks': dict(base_hooks), 'status-line': {'padding': 0}},
        )
        assert 'status-line.file cannot be empty' in missing
        empty = validate_hooks_files_consistency(
            {'hooks': dict(base_hooks), 'status-line': {'file': '   '}},
        )
        assert 'status-line.file cannot be empty' in empty

    def test_status_line_empty_config_fails(self) -> None:
        """An empty status-line.config mirrors the model's rejection."""
        errors = validate_hooks_files_consistency({
            'hooks': {'files': ['hooks/sl.py'], 'events': []},
            'status-line': {'file': 'sl.py', 'config': ''},
        })
        assert 'status-line.config cannot be empty when specified' in errors

    def test_status_line_null_bytes_fail(self) -> None:
        """Null bytes in status-line references mirror the model's rejection."""
        errors = validate_hooks_files_consistency({
            'hooks': {'files': ['hooks/sl.py'], 'events': []},
            'status-line': {'file': 'sl\x00.py', 'config': 'c\x00.yaml'},
        })
        assert 'status-line.file cannot contain null bytes' in errors
        assert 'status-line.config cannot contain null bytes' in errors

    def test_require_all_files_used_false_skips_unused_rule(self) -> None:
        """The post-selection mode tolerates stranded files but not dangling refs."""
        stranded = {
            'hooks': {
                'files': ['hooks/a.py', 'hooks/stranded.py'],
                'events': [{'event': 'PostToolUse', 'command': 'a.py'}],
            },
        }
        assert validate_hooks_files_consistency(stranded, require_all_files_used=False) == []
        assert validate_hooks_files_consistency(stranded) != []

        dangling = {
            'hooks': {
                'files': [],
                'events': [{'event': 'PostToolUse', 'command': 'dropped.py'}],
            },
        }
        errors = validate_hooks_files_consistency(dangling, require_all_files_used=False)
        assert any('dropped.py' in e for e in errors)


class TestHooksHelpersConsistency:
    """Runtime verdicts for the hooks.helpers list."""

    @staticmethod
    def _with_helper(**overrides: Any) -> dict[str, Any]:
        """Return a consistent config that also declares a helper module."""
        hooks: dict[str, Any] = {
            'files': ['hooks/a.py'],
            'helpers': ['hooks/shared.py'],
            'events': [{'event': 'PostToolUse', 'command': 'a.py'}],
        }
        hooks.update(overrides)
        return {'hooks': hooks}

    def test_unreferenced_helper_passes(self) -> None:
        """A helper referenced by nothing is valid; the unused rule skips it."""
        assert validate_hooks_files_consistency(self._with_helper()) == []

    def test_helper_only_config_passes(self) -> None:
        """Helpers alone, with no events and no files, are valid."""
        config = {'hooks': {'helpers': ['hooks/shared.py'], 'events': []}}
        assert validate_hooks_files_consistency(config) == []

    def test_duplicate_basename_fails(self) -> None:
        """A basename declared in both lists is reported once."""
        config = self._with_helper(helpers=['other/a.py'])
        errors = validate_hooks_files_consistency(config)
        assert len(errors) == 1
        assert "hooks.helpers duplicates hooks.files entries: ['a.py']" in errors[0]

    def test_command_referencing_helper_fails(self) -> None:
        """A command naming a helper is reported as a misplaced declaration."""
        config = self._with_helper(
            events=[{'event': 'PostToolUse', 'command': 'shared.py'}],
            files=[],
        )
        errors = validate_hooks_files_consistency(config)
        assert len(errors) == 1
        assert 'hooks.events command "shared.py" is declared in hooks.helpers' in errors[0]
        assert 'belong in hooks.files' in errors[0]

    def test_event_config_referencing_helper_fails(self) -> None:
        """An event config naming a helper is reported as a misplaced declaration."""
        config = self._with_helper(
            helpers=['configs/shared.yaml'],
            events=[{'event': 'PostToolUse', 'command': 'a.py', 'config': 'shared.yaml?ref=main'}],
        )
        errors = validate_hooks_files_consistency(config)
        assert len(errors) == 1
        assert 'hooks.events config "shared.yaml?ref=main" is declared in hooks.helpers' in errors[0]

    def test_status_line_referencing_helper_fails(self) -> None:
        """A status-line file naming a helper is reported as a misplaced declaration."""
        config = self._with_helper(helpers=['hooks/sl.py'])
        config['status-line'] = {'file': 'sl.py'}
        errors = validate_hooks_files_consistency(config)
        assert any(
            'status-line.file "sl.py" is declared in hooks.helpers' in e for e in errors
        )

    def test_status_line_config_referencing_helper_fails(self) -> None:
        """A status-line config naming a helper is reported as a misplaced declaration."""
        config = self._with_helper(
            files=['hooks/a.py', 'hooks/sl.py'],
            helpers=['configs/sl_cfg.yaml'],
        )
        config['status-line'] = {'file': 'sl.py', 'config': 'sl_cfg.yaml'}
        errors = validate_hooks_files_consistency(config)
        assert any(
            'status-line.config "sl_cfg.yaml" is declared in hooks.helpers' in e
            for e in errors
        )

    def test_helpers_non_list_fails(self) -> None:
        """A non-list helpers value is a structural error."""
        errors = validate_hooks_files_consistency({'hooks': {'helpers': 'shared.py'}})
        assert errors == ["'hooks.helpers' must be a list of file paths or URLs"]

    def test_non_string_helper_entry_reported(self) -> None:
        """A non-string helper entry is reported and suppresses the unused rule."""
        config = {
            'hooks': {
                'files': ['hooks/a.py', 'hooks/unused.py'],
                'helpers': [42],
                'events': [{'event': 'PostToolUse', 'command': 'a.py'}],
            },
        }
        errors = validate_hooks_files_consistency(config)
        assert errors == ['hooks.helpers[0] must be a string path or URL']


class TestProgramCommands:
    """Runtime verdicts for command hooks that name a program instead of a script."""

    @staticmethod
    def _config(*events: dict[str, Any], files: list[str] | None = None) -> dict[str, Any]:
        """Return a hooks config with the given events and hooks.files list."""
        return {'hooks': {'files': files or [], 'events': list(events)}}

    @pytest.mark.parametrize(
        'command',
        ['my-tool', '/usr/local/bin/my-tool', 'C:/Program Files/My Tool/my-tool.exe'],
    )
    def test_exec_form_program_accepted(self, command: str) -> None:
        """A command naming no hooks.files entry is a program when args is set."""
        config = self._config(
            {'event': 'Stop', 'type': 'command', 'command': command, 'args': ['hook', 'stop'],
             'async-rewake': True, 'timeout': 86400},
        )
        assert validate_hooks_files_consistency(config) == []

    def test_exec_form_program_with_empty_args_accepted(self) -> None:
        """An empty args list declares a program that takes no arguments."""
        config = self._config({'event': 'SessionStart', 'command': 'my-tool', 'args': []})
        assert validate_hooks_files_consistency(config) == []

    def test_program_does_not_excuse_unused_files(self) -> None:
        """A program never counts as a use of a hooks.files entry."""
        config = self._config(
            {'event': 'Stop', 'command': 'my-tool', 'args': []},
            files=['hooks/a.py'],
        )
        errors = validate_hooks_files_consistency(config)
        assert len(errors) == 1
        assert "unused files: ['a.py']" in errors[0]

    def test_shell_form_program_refused_naming_args(self) -> None:
        """Without args a command naming no hooks.files entry is refused."""
        config = self._config({'event': 'Stop', 'command': 'my-tool'}, files=['hooks/a.py'])
        config['hooks']['events'].append({'event': 'PostToolUse', 'command': 'a.py'})
        assert validate_hooks_files_consistency(config) == [(
            'hooks.events command "my-tool" not found in hooks.files. '
            "Available files: ['a.py']. "
            'A command that is not a hooks.files script runs as a program in exec form: '
            'name the program (on PATH or by absolute path) in command and give its '
            'arguments in args, using args: [] when it takes none.'
        )]

    def test_shell_form_command_line_refused(self) -> None:
        """A shell command line is refused; the program and its arguments go in args."""
        config = self._config({'event': 'Stop', 'command': 'my-tool hook stop'})
        errors = validate_hooks_files_consistency(config)
        assert len(errors) == 1
        assert errors[0].startswith(
            'hooks.events command "my-tool hook stop" not found in hooks.files. Available files: none.',
        )

    def test_null_args_is_shell_form(self) -> None:
        """A bare args key (null) declares no exec form, so the program is refused."""
        config = self._config({'event': 'Stop', 'command': 'my-tool', 'args': None})
        errors = validate_hooks_files_consistency(config)
        assert len(errors) == 1
        assert 'command "my-tool" not found in hooks.files' in errors[0]

    def test_config_beside_program_refused(self) -> None:
        """Only a hooks.files script receives a config, so a program cannot take one."""
        config = self._config(
            {'event': 'PostToolUse', 'command': 'a.py', 'config': 'c.yaml'},
            {'event': 'Stop', 'command': 'my-tool', 'config': ' c.yaml ', 'args': ['hook']},
            files=['hooks/a.py', 'configs/c.yaml'],
        )
        assert validate_hooks_files_consistency(config) == [(
            'hooks.events config "c.yaml" is set beside command "my-tool", which is '
            'a program, not a hooks.files script. config is passed only to a hooks.files '
            'script; a program takes its arguments in args.'
        )]

    def test_exec_form_helper_command_keeps_helper_error(self) -> None:
        """A command naming a helper stays a misplaced declaration in exec form."""
        config = {
            'hooks': {
                'files': [],
                'helpers': ['hooks/shared.py'],
                'events': [{'event': 'PostToolUse', 'command': 'shared.py', 'args': []}],
            },
        }
        errors = validate_hooks_files_consistency(config)
        assert len(errors) == 1
        assert 'hooks.events command "shared.py" is declared in hooks.helpers' in errors[0]

    def test_exec_form_listed_script_with_config_accepted(self) -> None:
        """A listed script keeps its config in exec form and marks both files used."""
        config = self._config(
            {'event': 'PostToolUse', 'command': 'a.py', 'config': 'c.yaml', 'args': ['--fix']},
            files=['hooks/a.py', 'configs/c.yaml'],
        )
        assert validate_hooks_files_consistency(config) == []


class TestDeclaredFiles:
    """Post-selection verdicts for references to hooks.files scripts a selection dropped."""

    @staticmethod
    def _recheck(files: list[str], declared: list[str], *events: dict[str, Any]) -> list[str]:
        """Run the post-selection recheck on the filtered hooks.files and the declared list."""
        config = {'hooks': {'files': files, 'events': list(events)}}
        return validate_hooks_files_consistency(
            config, require_all_files_used=False, declared_files=declared,
        )

    def test_exec_form_reference_to_dropped_script_is_dangling(self) -> None:
        """A dropped script named in exec form is a dangling reference, never a program."""
        errors = self._recheck(
            [], ['hooks/lint.py'],
            {'event': 'PostToolUse', 'matcher': 'Write', 'type': 'command',
             'command': 'lint.py', 'args': ['--fix']},
        )
        assert errors == ['hooks.events command "lint.py" not found in hooks.files. Available files: none']

    def test_exec_form_reference_with_empty_args_to_dropped_script_is_dangling(self) -> None:
        """An empty args list does not turn a dropped script into a program."""
        errors = self._recheck(
            ['hooks/keep.py'], ['hooks/keep.py', 'https://example.com/hooks/lint.py?ref=main'],
            {'event': 'PostToolUse', 'command': ' lint.py ', 'args': []},
            {'event': 'Stop', 'command': 'keep.py'},
        )
        assert errors == [
            "hooks.events command \"lint.py\" not found in hooks.files. Available files: ['keep.py']",
        ]

    def test_shell_form_reference_to_dropped_script_names_no_program_form(self) -> None:
        """A dropped script in shell form gets the plain dangling-reference message."""
        errors = self._recheck(
            [], ['hooks/lint.py'],
            {'event': 'PostToolUse', 'command': 'lint.py'},
        )
        assert errors == ['hooks.events command "lint.py" not found in hooks.files. Available files: none']

    def test_dropped_script_and_its_config_both_reported(self) -> None:
        """The config beside a dropped script is a dangling reference, not a program config."""
        errors = self._recheck(
            [], ['hooks/lint.py', 'configs/lint.yaml'],
            {'event': 'PostToolUse', 'command': 'lint.py', 'config': 'lint.yaml', 'args': ['--fix']},
        )
        assert errors == [
            'hooks.events command "lint.py" not found in hooks.files. Available files: none',
            'hooks.events config "lint.yaml" not found in hooks.files. Available files: none',
        ]

    def test_surviving_script_and_program_keep_their_verdicts(self) -> None:
        """Declared files change nothing for a surviving script or a program."""
        errors = self._recheck(
            ['hooks/keep.py'], ['hooks/keep.py', 'hooks/lint.py'],
            {'event': 'PostToolUse', 'command': 'keep.py', 'args': ['--fix']},
            {'event': 'Stop', 'command': 'my-tool', 'args': ['hook', 'stop']},
        )
        assert errors == []

    def test_unlisted_shell_form_program_keeps_args_advice(self) -> None:
        """A shell-form command that was never declared still names args as the program form."""
        errors = self._recheck(
            [], ['hooks/lint.py'],
            {'event': 'Stop', 'command': 'my-tool'},
        )
        assert len(errors) == 1
        assert errors[0].startswith('hooks.events command "my-tool" not found in hooks.files. Available files: none. ')
        assert 'give its arguments in args' in errors[0]

    def test_source_snapshot_replay_exits_on_a_dropped_exec_form_script(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Replaying a source's selection rechecks exec-form references to the scripts it drops."""
        config = {
            'name': 'Stranded Exec Form',
            'agents': ['agents/keep.md'],
            'hooks': {
                'files': ['hooks/lint.py'],
                'events': [{'event': 'PostToolUse', 'matcher': 'Write', 'type': 'command',
                            'command': 'lint.py', 'args': ['--fix']}],
            },
            'components': [
                {'name': 'core', 'includes': {'agents': ['agents/keep.md']}},
                {'name': 'lint', 'default': False, 'includes': {'hooks': ['hooks/lint.py']}},
            ],
        }

        with pytest.raises(SystemExit) as exc_info:
            replay_source_snapshot(config, LinkSource('source', tmp_path, None))

        assert exc_info.value.code == 1
        assert (
            'hooks.events command "lint.py" not found in hooks.files. Available files: none'
            in capsys.readouterr().err
        )


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

    def test_shell_form_builds_script_command_without_files_list(self, tmp_path: Path) -> None:
        """Shell form always runs a hooks.files script, even when no files list is given.

        The deselection reconciliation builds the removed events without the
        files list, so a spaced script name must still resolve to its path.
        """
        hooks = {
            'events': [
                {'event': 'PreToolUse', 'matcher': 'Bash', 'type': 'command', 'command': 'my hook.sh'},
            ],
        }
        built = _build_hooks_json(hooks, tmp_path)
        command = built['PreToolUse'][0]['hooks'][0]['command']
        assert command == f'"{(tmp_path / "my hook.sh").as_posix()}"'

    def test_exec_form_program_written_exactly(self, tmp_path: Path) -> None:
        """A program on PATH is written with its declared fields and nothing else."""
        hooks = {
            'files': ['hooks/a.py'],
            'events': [
                {'event': 'PostToolUse', 'matcher': 'Edit', 'type': 'command', 'command': 'a.py'},
                {'event': 'Stop', 'type': 'command', 'command': 'my-tool', 'args': ['hook', 'stop'],
                 'async-rewake': True, 'timeout': 86400},
                {'event': 'UserPromptSubmit', 'type': 'command', 'command': 'my-tool',
                 'args': ['hook', 'prompt-submit'], 'async': True},
                {'event': 'SessionStart', 'type': 'command', 'command': 'my-tool', 'args': []},
            ],
        }
        built = _build_hooks_json(hooks, tmp_path)
        assert built['Stop'] == [{'matcher': '', 'hooks': [
            {'type': 'command', 'command': 'my-tool', 'args': ['hook', 'stop'],
             'asyncRewake': True, 'timeout': 86400},
        ]}]
        assert built['UserPromptSubmit'] == [{'matcher': '', 'hooks': [
            {'type': 'command', 'command': 'my-tool', 'args': ['hook', 'prompt-submit'], 'async': True},
        ]}]
        assert built['SessionStart'] == [{'matcher': '', 'hooks': [
            {'type': 'command', 'command': 'my-tool', 'args': []},
        ]}]

    def test_exec_form_listed_script_classified_as_the_validator_does(self, tmp_path: Path) -> None:
        """A command equal to a listed basename folds into the launcher in exec form.

        A local hooks.files path keeps its query string in its basename, and
        the validator matches the command against that basename, so the
        writer folds the same command into the hooks directory.
        """
        hooks = {
            'files': ['hooks/win.pyw?ref=main'],
            'events': [{'event': 'Stop', 'type': 'command', 'command': 'win.pyw?ref=main', 'args': ['--x']}],
        }
        assert validate_hooks_files_consistency({'hooks': hooks}) == []
        hook = _build_hooks_json(hooks, tmp_path)['Stop'][0]['hooks'][0]
        assert hook['command'] == 'uv'
        assert hook['args'] == ['run', '--no-project', '--python', '3.12', (tmp_path / 'win.pyw').as_posix(), '--x']


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
