"""
Test suite for environment_config.py hooks cross-validation rules.

This test suite validates that the hooks cross-validation rules correctly ensure:
1. Each file in hooks.files is used somewhere (events or status-line)
2. Each file referenced in hooks.events (command hooks only) exists in hooks.files
3. The status-line.file (if configured) exists in hooks.files
4. HookEvent validation for command and prompt hook types

Uses model_validate() with dictionaries for Pydantic model instantiation to work
properly with static type checkers while testing runtime validation.
"""

import pytest
from pydantic import ValidationError

from scripts.models.environment_config import Component
from scripts.models.environment_config import EnvironmentConfig
from scripts.models.environment_config import HookEvent
from scripts.models.environment_config import InheritEntry
from scripts.models.environment_config import MCPServerStdio


class TestInheritEntryModel:
    """Tests for the InheritEntry Pydantic model."""

    def test_inherit_entry_basic_valid(self):
        """Basic InheritEntry with only config succeeds."""
        entry = InheritEntry(config='base.yaml')
        assert entry.config == 'base.yaml'
        assert entry.merge_keys is None

    def test_inherit_entry_with_merge_keys(self):
        """InheritEntry with merge-keys via model_validate succeeds."""
        entry = InheritEntry.model_validate({'config': 'x.yaml', 'merge-keys': ['agents']})
        assert entry.config == 'x.yaml'
        assert entry.merge_keys == ['agents']

    def test_inherit_entry_empty_config_rejected(self):
        """Empty config string raises ValueError."""
        with pytest.raises(Exception, match='config cannot be empty'):
            InheritEntry(config='')

    def test_inherit_entry_blank_config_rejected(self):
        """Whitespace-only config raises ValueError."""
        with pytest.raises(Exception, match='config cannot be empty'):
            InheritEntry(config='   ')

    def test_inherit_entry_null_bytes_rejected(self):
        """Config with null bytes raises ValueError."""
        with pytest.raises(Exception, match='config cannot contain null bytes'):
            InheritEntry(config='base\x00.yaml')

    def test_inherit_entry_invalid_merge_key_rejected(self):
        """Invalid merge-key raises ValueError."""
        with pytest.raises(Exception, match='Invalid merge-keys'):
            InheritEntry.model_validate({'config': 'x.yaml', 'merge-keys': ['invalid-key']})

    def test_inherit_entry_extra_field_rejected(self):
        """Extra field rejected by extra=forbid."""
        with pytest.raises(ValidationError, match='extra'):
            InheritEntry.model_validate({'config': 'x.yaml', 'extra': 'y'})

    def test_inherit_entry_missing_config_rejected(self):
        """Missing config field raises error."""
        with pytest.raises(ValidationError, match='config'):
            InheritEntry.model_validate({'merge-keys': ['agents']})

    def test_inherit_entry_model_validate_alias(self):
        """model_validate works with kebab-case alias."""
        entry = InheritEntry.model_validate({'config': 'x.yaml', 'merge-keys': ['agents', 'rules']})
        assert entry.merge_keys == ['agents', 'rules']

    def test_inherit_entry_multiple_merge_keys(self):
        """Multiple valid merge-keys accepted."""
        entry = InheritEntry.model_validate({
            'config': 'x.yaml',
            'merge-keys': ['agents', 'rules', 'mcp-servers', 'os-env-variables'],
        })
        assert len(entry.merge_keys) == 4


class TestHooksUnusedFiles:
    """Test Rule 1: Each file in hooks.files must be used somewhere."""

    def test_hooks_file_used_by_event(self) -> None:
        """File in hooks.files used by event - should PASS."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'hooks': {
                'files': ['https://example.com/path/script.py'],
                'events': [{'event': 'PostToolUse', 'command': 'script.py'}],
            },
        })
        assert config.hooks is not None
        assert len(config.hooks.files) == 1
        assert len(config.hooks.events) == 1

    def test_hooks_file_used_by_status_line(self) -> None:
        """File in hooks.files used by status-line - should PASS."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'hooks': {
                'files': ['https://example.com/path/status_line.py'],
                'events': [],
            },
            'status-line': {'file': 'status_line.py'},
        })
        assert config.hooks is not None
        assert config.status_line is not None

    def test_hooks_file_used_by_both_event_and_status_line(self) -> None:
        """File in hooks.files used by both event and status-line - should PASS."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'hooks': {
                'files': [
                    'https://example.com/path/script.py',
                    'https://example.com/path/status_line.py',
                ],
                'events': [{'event': 'PostToolUse', 'command': 'script.py'}],
            },
            'status-line': {'file': 'status_line.py'},
        })
        assert config.hooks is not None
        assert len(config.hooks.files) == 2

    def test_hooks_file_not_used_anywhere(self) -> None:
        """File in hooks.files not used anywhere - should FAIL."""
        with pytest.raises(ValidationError) as exc_info:
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'hooks': {
                    'files': ['https://example.com/path/unused.py'],
                    'events': [],
                },
            })
        assert 'unused files' in str(exc_info.value).lower()


class TestEventFileReferences:
    """Test Rule 2: Each file in hooks.events must exist in hooks.files."""

    def test_event_command_matches_file_basename(self) -> None:
        """Event command matches file basename - should PASS."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'hooks': {
                'files': ['https://example.com/path/to/quality_checks.py'],
                'events': [{'event': 'PostToolUse', 'command': 'quality_checks.py'}],
            },
        })
        assert config.hooks is not None
        assert config.hooks.events[0].command == 'quality_checks.py'

    def test_event_command_not_matching_any_file(self) -> None:
        """Event command doesn't match any file - should FAIL."""
        with pytest.raises(ValidationError) as exc_info:
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'hooks': {
                    'files': ['https://example.com/path/script.py'],
                    'events': [{'event': 'PostToolUse', 'command': 'nonexistent.py'}],
                },
            })
        assert 'nonexistent.py' in str(exc_info.value)
        assert 'not found' in str(exc_info.value).lower()

    def test_multiple_events_all_reference_valid_files(self) -> None:
        """Multiple events all reference valid files - should PASS."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'hooks': {
                'files': [
                    'https://example.com/path/hook1.py',
                    'https://example.com/path/hook2.py',
                    'https://example.com/path/hook3.py',
                ],
                'events': [
                    {'event': 'PostToolUse', 'command': 'hook1.py'},
                    {'event': 'PreToolUse', 'command': 'hook2.py'},
                    {'event': 'Notification', 'command': 'hook3.py'},
                ],
            },
        })
        assert config.hooks is not None
        assert len(config.hooks.events) == 3

    def test_one_of_multiple_events_references_invalid_file(self) -> None:
        """One of multiple events references invalid file - should FAIL."""
        with pytest.raises(ValidationError) as exc_info:
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'hooks': {
                    'files': [
                        'https://example.com/path/hook1.py',
                        'https://example.com/path/hook2.py',
                    ],
                    'events': [
                        {'event': 'PostToolUse', 'command': 'hook1.py'},
                        {'event': 'PreToolUse', 'command': 'hook2.py'},
                        {'event': 'Notification', 'command': 'missing.py'},
                    ],
                },
            })
        assert 'missing.py' in str(exc_info.value)
        assert 'not found' in str(exc_info.value).lower()


class TestStatusLineFileReference:
    """Test Rule 3: status-line.file must exist in hooks.files."""

    def test_status_line_file_matches_hooks_files_basename(self) -> None:
        """Status-line file matches hooks.files basename - should PASS."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'hooks': {
                'files': ['https://example.com/path/status_display.py'],
                'events': [],
            },
            'status-line': {'file': 'status_display.py', 'padding': 0},
        })
        assert config.status_line is not None
        assert config.status_line.file == 'status_display.py'

    def test_status_line_file_not_matching_any_file(self) -> None:
        """Status-line file doesn't match any file - should FAIL."""
        with pytest.raises(ValidationError) as exc_info:
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'hooks': {
                    'files': ['https://example.com/path/other_script.py'],
                    'events': [],
                },
                'status-line': {'file': 'missing_status.py'},
            })
        assert 'missing_status.py' in str(exc_info.value)
        assert 'not found' in str(exc_info.value).lower()

    def test_status_line_configured_but_hooks_is_none(self) -> None:
        """Status-line configured but hooks is None - should FAIL."""
        with pytest.raises(ValidationError) as exc_info:
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'hooks': None,
                'status-line': {'file': 'status_line.py'},
            })
        assert 'status-line.file' in str(exc_info.value)
        assert 'hooks.files' in str(exc_info.value).lower()


class TestEdgeCases:
    """Test edge cases for hooks cross-validation."""

    def test_empty_hooks_files_with_no_events_and_no_status_line(self) -> None:
        """Empty hooks.files with no events and no status-line - should PASS."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'hooks': {
                'files': [],
                'events': [],
            },
            'status-line': None,
        })
        assert config.hooks is not None
        assert config.hooks.files == []
        assert config.hooks.events == []

    def test_hooks_is_none_and_status_line_is_none(self) -> None:
        """hooks is None and status-line is None - should PASS."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'hooks': None,
            'status-line': None,
        })
        assert config.hooks is None
        assert config.status_line is None

    def test_hooks_is_none_but_status_line_is_configured(self) -> None:
        """hooks is None but status-line is configured - should FAIL."""
        with pytest.raises(ValidationError) as exc_info:
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'hooks': None,
                'status-line': {'file': 'status.py'},
            })
        assert 'status-line.file' in str(exc_info.value)
        assert 'hooks.files' in str(exc_info.value).lower()

    def test_url_with_query_parameters_extracts_basename(self) -> None:
        """URL with query parameters - correctly extracts basename (PASS)."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'hooks': {
                'files': ['https://example.com/path/script.py?token=abc123&version=1.0'],
                'events': [{'event': 'PostToolUse', 'command': 'script.py'}],
            },
        })
        assert config.hooks is not None
        # The validator correctly extracted 'script.py' from URL with query params
        assert len(config.hooks.events) == 1

    def test_windows_path_in_hooks_files_extracts_basename(self) -> None:
        """Windows path in hooks.files - correctly extracts basename (PASS)."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'hooks': {
                'files': ['C:\\Users\\Developer\\hooks\\quality_check.py'],
                'events': [{'event': 'PostToolUse', 'command': 'quality_check.py'}],
            },
        })
        assert config.hooks is not None
        # The validator correctly extracted 'quality_check.py' from Windows path
        assert config.hooks.events[0].command == 'quality_check.py'


class TestHookEventValidation:
    """Test HookEvent model validation for command and prompt hooks."""

    # Valid command hooks
    def test_command_hook_with_command(self) -> None:
        """Command hook with command field is valid."""
        event = HookEvent.model_validate({
            'event': 'PreToolUse',
            'matcher': 'Task',
            'type': 'command',
            'command': 'validate_task.py',
        })
        assert event.type == 'command'
        assert event.command == 'validate_task.py'

    def test_command_hook_with_config(self) -> None:
        """Command hook with command and config is valid."""
        event = HookEvent.model_validate({
            'event': 'PreToolUse',
            'matcher': 'Task',
            'type': 'command',
            'command': 'validate_task.py',
            'config': 'validate_task_config.yaml',
        })
        assert event.config == 'validate_task_config.yaml'

    # Valid prompt hooks
    def test_prompt_hook_with_prompt(self) -> None:
        """Prompt hook with prompt field is valid."""
        event = HookEvent.model_validate({
            'event': 'PreToolUse',
            'matcher': 'Search|Grep',
            'type': 'prompt',
            'prompt': 'You are a tool validator...',
        })
        assert event.type == 'prompt'
        assert event.prompt == 'You are a tool validator...'

    def test_prompt_hook_with_timeout(self) -> None:
        """Prompt hook with timeout is valid."""
        event = HookEvent.model_validate({
            'event': 'PreToolUse',
            'matcher': 'Search|Grep',
            'type': 'prompt',
            'prompt': 'Validate this call...',
            'timeout': 15,
        })
        assert event.timeout == 15

    # Invalid: command hook without command
    def test_command_hook_without_command_raises(self) -> None:
        """Command hook without command raises ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            HookEvent.model_validate({
                'event': 'PreToolUse',
                'type': 'command',
            })
        assert "requires 'command' field" in str(exc_info.value)

    # Invalid: command hook with prompt
    def test_command_hook_with_prompt_raises(self) -> None:
        """Command hook with prompt field raises ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            HookEvent.model_validate({
                'event': 'PreToolUse',
                'type': 'command',
                'command': 'some_command.py',
                'prompt': 'This should not be here',
            })
        assert "cannot have 'prompt' field" in str(exc_info.value)

    # Invalid: prompt hook without prompt
    def test_prompt_hook_without_prompt_raises(self) -> None:
        """Prompt hook without prompt raises ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            HookEvent.model_validate({
                'event': 'PreToolUse',
                'type': 'prompt',
            })
        assert "requires 'prompt' field" in str(exc_info.value)

    # Invalid: prompt hook with command
    def test_prompt_hook_with_command_raises(self) -> None:
        """Prompt hook with command field raises ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            HookEvent.model_validate({
                'event': 'PreToolUse',
                'type': 'prompt',
                'prompt': 'Validate this...',
                'command': 'should_not_be_here.py',
            })
        assert "cannot have 'command' field" in str(exc_info.value)

    # Invalid: prompt hook with config
    def test_prompt_hook_with_config_raises(self) -> None:
        """Prompt hook with config field raises ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            HookEvent.model_validate({
                'event': 'PreToolUse',
                'type': 'prompt',
                'prompt': 'Validate this...',
                'config': 'should_not_be_here.yaml',
            })
        assert "cannot have 'config' field" in str(exc_info.value)

    # Backward compatibility: default type is command
    def test_default_type_is_command(self) -> None:
        """Default type should be 'command' for backward compatibility."""
        event = HookEvent.model_validate({
            'event': 'PreToolUse',
            'command': 'test.py',
        })
        assert event.type == 'command'


class TestHookEventAllTypes:
    """Test HookEvent model for all 4 hook types with aliases and field matrix."""

    # --- HTTP hook valid cases ---
    def test_http_hook_with_url(self) -> None:
        """HTTP hook with url field is valid."""
        event = HookEvent.model_validate({
            'event': 'PostToolUse',
            'matcher': 'Write',
            'type': 'http',
            'url': 'http://localhost:8080/hooks/post-tool-use',
        })
        assert event.type == 'http'
        assert event.url == 'http://localhost:8080/hooks/post-tool-use'

    def test_http_hook_with_headers_and_allowed_env_vars(self) -> None:
        """HTTP hook with all optional fields is valid."""
        event = HookEvent.model_validate({
            'event': 'PostToolUse',
            'type': 'http',
            'url': 'https://example.com/webhook',
            'headers': {'Authorization': 'Bearer $MY_TOKEN', 'Content-Type': 'application/json'},
            'allowed-env-vars': ['MY_TOKEN'],
        })
        assert event.headers == {'Authorization': 'Bearer $MY_TOKEN', 'Content-Type': 'application/json'}
        assert event.allowed_env_vars == ['MY_TOKEN']

    # --- Agent hook valid cases ---
    def test_agent_hook_with_prompt(self) -> None:
        """Agent hook with prompt field is valid."""
        event = HookEvent.model_validate({
            'event': 'PreToolUse',
            'matcher': 'Bash',
            'type': 'agent',
            'prompt': 'Verify security implications of: $ARGUMENTS',
        })
        assert event.type == 'agent'
        assert event.prompt == 'Verify security implications of: $ARGUMENTS'

    def test_agent_hook_with_model(self) -> None:
        """Agent hook with model field is valid."""
        event = HookEvent.model_validate({
            'event': 'PreToolUse',
            'type': 'agent',
            'prompt': 'Review this action',
            'model': 'sonnet',
        })
        assert event.model == 'sonnet'

    # --- Command hook with new fields ---
    def test_command_hook_with_async_and_shell(self) -> None:
        """Command hook with async and shell fields is valid."""
        event = HookEvent.model_validate({
            'event': 'Notification',
            'type': 'command',
            'command': 'notify.py',
            'async': True,
            'shell': 'bash',
        })
        assert event.async_execution is True
        assert event.shell == 'bash'

    def test_command_hook_shell_powershell(self) -> None:
        """Command hook with shell=powershell is valid."""
        event = HookEvent.model_validate({
            'event': 'Notification',
            'type': 'command',
            'command': 'notify.ps1',
            'shell': 'powershell',
        })
        assert event.shell == 'powershell'

    # --- Alias tests (populate_by_name) ---
    def test_hook_with_if_condition_alias(self) -> None:
        """The 'if' alias maps to if_condition field."""
        event = HookEvent.model_validate({
            'event': 'PreToolUse',
            'type': 'command',
            'command': 'check.py',
            'if': 'Bash(git *)',
        })
        assert event.if_condition == 'Bash(git *)'

    def test_hook_with_status_message_alias(self) -> None:
        """The 'status-message' alias maps to status_message field."""
        event = HookEvent.model_validate({
            'event': 'PreToolUse',
            'type': 'command',
            'command': 'check.py',
            'status-message': 'Running check...',
        })
        assert event.status_message == 'Running check...'

    def test_hook_with_async_alias(self) -> None:
        """The 'async' alias maps to async_execution field."""
        event = HookEvent.model_validate({
            'event': 'Notification',
            'type': 'command',
            'command': 'notify.py',
            'async': True,
        })
        assert event.async_execution is True

    def test_hook_with_allowed_env_vars_alias(self) -> None:
        """The 'allowed-env-vars' alias maps to allowed_env_vars field."""
        event = HookEvent.model_validate({
            'event': 'PostToolUse',
            'type': 'http',
            'url': 'https://example.com/hook',
            'allowed-env-vars': ['TOKEN', 'SECRET'],
        })
        assert event.allowed_env_vars == ['TOKEN', 'SECRET']

    def test_hook_with_once_field(self) -> None:
        """The once field is accepted on all types."""
        event = HookEvent.model_validate({
            'event': 'PreToolUse',
            'type': 'agent',
            'prompt': 'Check once',
            'once': True,
        })
        assert event.once is True

    def test_common_fields_on_all_types(self) -> None:
        """Common fields (if, status-message, once, timeout) work on all types."""
        common = {'if': 'Bash(*)', 'status-message': 'Working...', 'once': True, 'timeout': 30}

        for hook_data in [
            {'event': 'E', 'type': 'command', 'command': 'c.py', **common},
            {'event': 'E', 'type': 'http', 'url': 'http://x.com', **common},
            {'event': 'E', 'type': 'prompt', 'prompt': 'p', **common},
            {'event': 'E', 'type': 'agent', 'prompt': 'a', **common},
        ]:
            event = HookEvent.model_validate(hook_data)
            assert event.if_condition == 'Bash(*)'
            assert event.status_message == 'Working...'
            assert event.once is True
            assert event.timeout == 30

    # --- HTTP hook forbidden cases ---
    def test_http_hook_without_url_raises(self) -> None:
        """HTTP hook without url raises ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            HookEvent.model_validate({
                'event': 'PostToolUse',
                'type': 'http',
            })
        assert "requires 'url' field" in str(exc_info.value)

    def test_http_hook_with_command_raises(self) -> None:
        """HTTP hook with command field raises ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            HookEvent.model_validate({
                'event': 'PostToolUse',
                'type': 'http',
                'url': 'http://x.com',
                'command': 'bad.py',
            })
        assert "cannot have 'command' field" in str(exc_info.value)

    def test_http_hook_with_config_raises(self) -> None:
        """HTTP hook with config field raises ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            HookEvent.model_validate({
                'event': 'PostToolUse',
                'type': 'http',
                'url': 'http://x.com',
                'config': 'bad.yaml',
            })
        assert "cannot have 'config' field" in str(exc_info.value)

    def test_http_hook_with_async_raises(self) -> None:
        """HTTP hook with async field raises ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            HookEvent.model_validate({
                'event': 'PostToolUse',
                'type': 'http',
                'url': 'http://x.com',
                'async': True,
            })
        assert "cannot have 'async' field" in str(exc_info.value)

    def test_http_hook_with_shell_raises(self) -> None:
        """HTTP hook with shell field raises ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            HookEvent.model_validate({
                'event': 'PostToolUse',
                'type': 'http',
                'url': 'http://x.com',
                'shell': 'bash',
            })
        assert "cannot have 'shell' field" in str(exc_info.value)

    def test_http_hook_with_prompt_raises(self) -> None:
        """HTTP hook with prompt field raises ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            HookEvent.model_validate({
                'event': 'PostToolUse',
                'type': 'http',
                'url': 'http://x.com',
                'prompt': 'bad',
            })
        assert "cannot have 'prompt' field" in str(exc_info.value)

    def test_http_hook_with_model_raises(self) -> None:
        """HTTP hook with model field raises ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            HookEvent.model_validate({
                'event': 'PostToolUse',
                'type': 'http',
                'url': 'http://x.com',
                'model': 'sonnet',
            })
        assert "cannot have 'model' field" in str(exc_info.value)

    # --- Agent hook forbidden cases ---
    def test_agent_hook_without_prompt_raises(self) -> None:
        """Agent hook without prompt raises ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            HookEvent.model_validate({
                'event': 'PreToolUse',
                'type': 'agent',
            })
        assert "requires 'prompt' field" in str(exc_info.value)

    def test_agent_hook_with_command_raises(self) -> None:
        """Agent hook with command field raises ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            HookEvent.model_validate({
                'event': 'PreToolUse',
                'type': 'agent',
                'prompt': 'test',
                'command': 'bad.py',
            })
        assert "cannot have 'command' field" in str(exc_info.value)

    def test_agent_hook_with_url_raises(self) -> None:
        """Agent hook with url field raises ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            HookEvent.model_validate({
                'event': 'PreToolUse',
                'type': 'agent',
                'prompt': 'test',
                'url': 'http://bad.com',
            })
        assert "cannot have 'url' field" in str(exc_info.value)

    # --- Command hook forbidden cases ---
    def test_command_hook_with_url_raises(self) -> None:
        """Command hook with url field raises ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            HookEvent.model_validate({
                'event': 'PreToolUse',
                'type': 'command',
                'command': 'test.py',
                'url': 'http://bad.com',
            })
        assert "cannot have 'url' field" in str(exc_info.value)

    def test_command_hook_with_headers_raises(self) -> None:
        """Command hook with headers field raises ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            HookEvent.model_validate({
                'event': 'PreToolUse',
                'type': 'command',
                'command': 'test.py',
                'headers': {'Key': 'Value'},
            })
        assert "cannot have 'headers' field" in str(exc_info.value)

    def test_command_hook_with_model_raises(self) -> None:
        """Command hook with model field raises ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            HookEvent.model_validate({
                'event': 'PreToolUse',
                'type': 'command',
                'command': 'test.py',
                'model': 'sonnet',
            })
        assert "cannot have 'model' field" in str(exc_info.value)

    # --- Prompt hook forbidden cases (new fields) ---
    def test_prompt_hook_with_url_raises(self) -> None:
        """Prompt hook with url field raises ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            HookEvent.model_validate({
                'event': 'PreToolUse',
                'type': 'prompt',
                'prompt': 'test',
                'url': 'http://bad.com',
            })
        assert "cannot have 'url' field" in str(exc_info.value)

    def test_prompt_hook_with_async_raises(self) -> None:
        """Prompt hook with async field raises ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            HookEvent.model_validate({
                'event': 'PreToolUse',
                'type': 'prompt',
                'prompt': 'test',
                'async': True,
            })
        assert "cannot have 'async' field" in str(exc_info.value)

    def test_prompt_hook_with_shell_raises(self) -> None:
        """Prompt hook with shell field raises ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            HookEvent.model_validate({
                'event': 'PreToolUse',
                'type': 'prompt',
                'prompt': 'test',
                'shell': 'bash',
            })
        assert "cannot have 'shell' field" in str(exc_info.value)

    # --- Literal validation ---
    def test_shell_literal_validation(self) -> None:
        """Invalid shell value is rejected by Pydantic Literal."""
        with pytest.raises(ValidationError):
            HookEvent.model_validate({
                'event': 'PreToolUse',
                'type': 'command',
                'command': 'test.py',
                'shell': 'zsh',
            })

    # --- Validator: hooks files consistency skips new types ---
    def test_validate_hooks_files_consistency_skips_http(self) -> None:
        """HTTP hooks are skipped during file consistency validation."""
        from scripts.models.environment_config import EnvironmentConfig
        config = EnvironmentConfig.model_validate({
            'name': 'test',
            'hooks': {
                'files': [],
                'events': [
                    {'event': 'PostToolUse', 'type': 'http', 'url': 'http://x.com'},
                ],
            },
        })
        assert config.hooks is not None
        assert len(config.hooks.events) == 1

    def test_validate_hooks_files_consistency_skips_agent(self) -> None:
        """Agent hooks are skipped during file consistency validation."""
        from scripts.models.environment_config import EnvironmentConfig
        config = EnvironmentConfig.model_validate({
            'name': 'test',
            'hooks': {
                'files': [],
                'events': [
                    {'event': 'PreToolUse', 'type': 'agent', 'prompt': 'test'},
                ],
            },
        })
        assert config.hooks is not None
        assert len(config.hooks.events) == 1


class TestPromptHooksWithEnvironmentConfig:
    """Test prompt hooks integration with EnvironmentConfig."""

    def test_prompt_hook_does_not_require_files(self) -> None:
        """Prompt hooks should not require entries in hooks.files."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'hooks': {
                'files': ['command_hook.py'],
                'events': [
                    {'event': 'PreToolUse', 'matcher': 'Task', 'type': 'command', 'command': 'command_hook.py'},
                    {'event': 'PreToolUse', 'matcher': 'Search', 'type': 'prompt', 'prompt': 'Validate this search...'},
                ],
            },
        })
        assert config.hooks is not None
        assert len(config.hooks.events) == 2

    def test_mixed_command_and_prompt_hooks(self) -> None:
        """Mix of command and prompt hooks validates correctly."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'hooks': {
                'files': ['hook1.py', 'hook2.py', 'config.yaml'],
                'events': [
                    {'event': 'PreToolUse', 'matcher': 'Task', 'type': 'command', 'command': 'hook1.py'},
                    {'event': 'PreToolUse', 'matcher': 'Search', 'type': 'prompt', 'prompt': 'Validate search...'},
                    {
                        'event': 'PostToolUse', 'matcher': 'Edit', 'type': 'command',
                        'command': 'hook2.py', 'config': 'config.yaml',
                    },
                ],
            },
        })
        assert config.hooks is not None
        assert len(config.hooks.events) == 3
        # Verify types are correct
        assert config.hooks.events[0].type == 'command'
        assert config.hooks.events[1].type == 'prompt'
        assert config.hooks.events[2].type == 'command'

    def test_only_prompt_hooks_with_empty_files(self) -> None:
        """Environment with only prompt hooks requires no files."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'hooks': {
                'files': [],
                'events': [
                    {'event': 'PreToolUse', 'matcher': 'Search', 'type': 'prompt', 'prompt': 'Validate search...'},
                    {'event': 'PreToolUse', 'matcher': 'Grep', 'type': 'prompt', 'prompt': 'Validate grep...', 'timeout': 30},
                ],
            },
        })
        assert config.hooks is not None
        assert len(config.hooks.files) == 0
        assert len(config.hooks.events) == 2


class TestUserSettings:
    """Test UserSettings model validation."""

    def test_hooks_key_rejected(self) -> None:
        """UserSettings with 'hooks' key raises ValueError."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'hooks': {'events': []}})
        assert 'hooks' in str(exc_info.value)
        assert 'not allowed in user-settings' in str(exc_info.value)

    def test_status_line_key_rejected(self) -> None:
        """UserSettings with 'statusLine' key raises ValueError."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'statusLine': {'file': 'script.py'}})
        assert 'statusLine' in str(exc_info.value)
        assert 'not allowed in user-settings' in str(exc_info.value)

    def test_extra_keys_allowed_for_forward_compatibility(self) -> None:
        """UserSettings allows any keys via model_extra."""
        from scripts.models.environment_config import UserSettings
        settings = UserSettings.model_validate({
            'model': 'claude-sonnet-4',
            'futureKey': 'futureValue',
            'anotherNewSetting': True,
        })
        # All keys are stored in model_extra (no hardcoded fields)
        assert settings.model_extra is not None
        assert settings.model_extra.get('model') == 'claude-sonnet-4'
        assert settings.model_extra.get('futureKey') == 'futureValue'
        assert settings.model_extra.get('anotherNewSetting') is True

    def test_arbitrary_keys_stored_in_model_extra(self) -> None:
        """Any camelCase key is accepted and stored in model_extra."""
        from scripts.models.environment_config import UserSettings
        settings = UserSettings.model_validate({
            'apiKeyHelper': '/path/to/helper.sh',
            'disableAllHooks': True,
            'cleanupPeriodDays': 7,
            'customKey': 'customValue',
        })
        assert settings.model_extra is not None
        assert settings.model_extra['apiKeyHelper'] == '/path/to/helper.sh'
        assert settings.model_extra['disableAllHooks'] is True
        assert settings.model_extra['cleanupPeriodDays'] == 7
        assert settings.model_extra['customKey'] == 'customValue'

    def test_nested_dict_values_pass_through(self) -> None:
        """Nested dicts are preserved as-is (not parsed into sub-models)."""
        from scripts.models.environment_config import UserSettings
        settings = UserSettings.model_validate({
            'permissions': {
                'allow': ['Read(*)'],
                'deny': ['Bash(rm -rf *)'],
            },
            'sandbox': {
                'enabled': True,
                'network': {'httpProxyPort': 8080},
            },
        })
        assert settings.model_extra is not None
        # Nested dicts preserved as plain dicts, not typed sub-models
        assert isinstance(settings.model_extra['permissions'], dict)
        assert settings.model_extra['permissions']['allow'] == ['Read(*)']
        assert isinstance(settings.model_extra['sandbox'], dict)
        assert settings.model_extra['sandbox']['enabled'] is True

    def test_empty_user_settings_valid(self) -> None:
        """Empty user settings dict is valid."""
        from scripts.models.environment_config import UserSettings
        settings = UserSettings.model_validate({})
        # model_extra may be {} or None depending on Pydantic version
        assert settings.model_extra is None or settings.model_extra == {}


class TestUserSettingsInEnvironmentConfig:
    """Test UserSettings integration with EnvironmentConfig."""

    def test_environment_config_with_user_settings(self) -> None:
        """EnvironmentConfig with user-settings validates correctly."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test Environment',
            'user-settings': {
                'model': 'claude-sonnet-4',
                'language': 'english',
                'alwaysThinkingEnabled': True,
                'permissions': {
                    'allow': ['Read(*)'],
                },
            },
        })
        assert config.user_settings is not None
        extras = config.user_settings.model_extra
        assert extras is not None
        assert extras.get('model') == 'claude-sonnet-4'
        assert extras.get('language') == 'english'
        assert extras.get('alwaysThinkingEnabled') is True
        assert isinstance(extras.get('permissions'), dict)
        assert extras['permissions']['allow'] == ['Read(*)']

    def test_environment_config_without_user_settings(self) -> None:
        """EnvironmentConfig without user-settings validates correctly."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test Environment',
        })
        assert config.user_settings is None

    def test_environment_config_user_settings_hooks_rejected(self) -> None:
        """EnvironmentConfig rejects hooks in user-settings."""
        with pytest.raises(ValidationError) as exc_info:
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'user-settings': {
                    'model': 'claude-sonnet-4',
                    'hooks': {'events': []},
                },
            })
        assert 'hooks' in str(exc_info.value)
        assert 'not allowed in user-settings' in str(exc_info.value)

    def test_environment_config_user_settings_with_full_sandbox(self) -> None:
        """EnvironmentConfig with full sandbox config in user-settings."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'user-settings': {
                'sandbox': {
                    'enabled': True,
                    'autoAllowBashIfSandboxed': False,
                    'allowUnsandboxedCommands': True,
                    'excludedCommands': ['npm'],
                    'enableWeakerNestedSandbox': True,
                    'network': {
                        'allowUnixSockets': ['/tmp/socket'],
                        'allowLocalBinding': True,
                        'httpProxyPort': 3128,
                        'socksProxyPort': 1080,
                    },
                },
            },
        })
        assert config.user_settings is not None
        extras = config.user_settings.model_extra
        assert extras is not None
        sandbox = extras['sandbox']
        assert isinstance(sandbox, dict)
        assert sandbox['enabled'] is True
        assert sandbox['autoAllowBashIfSandboxed'] is False
        assert sandbox['allowUnsandboxedCommands'] is True
        assert sandbox['excludedCommands'] == ['npm']
        assert sandbox['enableWeakerNestedSandbox'] is True
        network = sandbox['network']
        assert isinstance(network, dict)
        assert network['allowUnixSockets'] == ['/tmp/socket']
        assert network['allowLocalBinding'] is True
        assert network['httpProxyPort'] == 3128
        assert network['socksProxyPort'] == 1080


class TestGlobalConfig:
    """Test GlobalConfig model validation."""

    def test_global_config_accepts_arbitrary_keys(self) -> None:
        """GlobalConfig allows any keys via model_extra."""
        from scripts.models.environment_config import GlobalConfig
        config = GlobalConfig.model_validate({
            'autoConnectIde': True,
            'editorMode': 'vim',
            'showTurnDuration': True,
        })
        assert config.model_extra is not None
        assert config.model_extra.get('autoConnectIde') is True
        assert config.model_extra.get('editorMode') == 'vim'
        assert config.model_extra.get('showTurnDuration') is True

    def test_global_config_rejects_non_null_oauth_account(self) -> None:
        """GlobalConfig with non-null 'oauthAccount' value raises ValueError."""
        from scripts.models.environment_config import GlobalConfig
        with pytest.raises(ValidationError) as exc_info:
            GlobalConfig.model_validate({'oauthAccount': 'account123'})
        assert 'oauthAccount' in str(exc_info.value)
        assert 'non-null' in str(exc_info.value)

    def test_global_config_allows_null_oauth_account(self) -> None:
        """GlobalConfig with null oauthAccount is accepted for clearing auth state."""
        from scripts.models.environment_config import GlobalConfig
        config = GlobalConfig.model_validate({'oauthAccount': None})
        assert config.model_extra is not None
        assert config.model_extra.get('oauthAccount') is None

    def test_global_config_allows_null_oauth_with_other_keys(self) -> None:
        """GlobalConfig with null oauthAccount alongside valid keys passes."""
        from scripts.models.environment_config import GlobalConfig
        config = GlobalConfig.model_validate({
            'oauthAccount': None,
            'editorMode': 'vim',
        })
        assert config.model_extra is not None
        assert config.model_extra.get('oauthAccount') is None
        assert config.model_extra.get('editorMode') == 'vim'

    def test_global_config_accepts_mcp_servers(self) -> None:
        """GlobalConfig allows mcpServers dict-of-dicts."""
        from scripts.models.environment_config import GlobalConfig
        config = GlobalConfig.model_validate({
            'mcpServers': {
                'server1': {'url': 'http://localhost:3000'},
                'server2': {'command': 'npx some-server'},
            },
        })
        assert config.model_extra is not None
        assert isinstance(config.model_extra['mcpServers'], dict)
        assert 'server1' in config.model_extra['mcpServers']

    def test_global_config_empty(self) -> None:
        """Empty GlobalConfig is valid."""
        from scripts.models.environment_config import GlobalConfig
        config = GlobalConfig.model_validate({})
        assert config.model_extra is None or config.model_extra == {}

    def test_global_config_nested_dicts(self) -> None:
        """Nested dicts are preserved as-is."""
        from scripts.models.environment_config import GlobalConfig
        config = GlobalConfig.model_validate({
            'projects': {
                '/home/user/project': {
                    'allowedTools': ['Read', 'Write'],
                },
            },
        })
        assert config.model_extra is not None
        assert isinstance(config.model_extra['projects'], dict)


class TestGlobalConfigInEnvironmentConfig:
    """Test GlobalConfig integration with EnvironmentConfig."""

    def test_environment_config_with_global_config(self) -> None:
        """EnvironmentConfig with global-config validates correctly."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test Environment',
            'global-config': {
                'autoConnectIde': True,
                'editorMode': 'vim',
            },
        })
        assert config.global_config is not None
        extras = config.global_config.model_extra
        assert extras is not None
        assert extras.get('autoConnectIde') is True
        assert extras.get('editorMode') == 'vim'

    def test_environment_config_without_global_config(self) -> None:
        """EnvironmentConfig without global-config validates correctly."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test Environment',
        })
        assert config.global_config is None

    def test_environment_config_global_config_oauth_non_null_rejected(self) -> None:
        """EnvironmentConfig rejects non-null oauthAccount in global-config."""
        with pytest.raises(ValidationError) as exc_info:
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'global-config': {
                    'autoConnectIde': True,
                    'oauthAccount': 'account123',
                },
            })
        assert 'oauthAccount' in str(exc_info.value)
        assert 'non-null' in str(exc_info.value)

    def test_environment_config_allows_null_oauth_in_global_config(self) -> None:
        """EnvironmentConfig accepts null oauthAccount in global-config."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'global-config': {
                'autoConnectIde': True,
                'oauthAccount': None,
            },
        })
        assert config.global_config is not None
        extras = config.global_config.model_extra
        assert extras is not None
        assert extras.get('oauthAccount') is None
        assert extras.get('autoConnectIde') is True

    def test_environment_config_with_both_settings_types(self) -> None:
        """EnvironmentConfig with both user-settings and global-config."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'user-settings': {'language': 'english'},
            'global-config': {'autoConnectIde': True},
        })
        assert config.user_settings is not None
        assert config.global_config is not None
        assert config.user_settings.model_extra is not None
        assert config.user_settings.model_extra.get('language') == 'english'
        assert config.global_config.model_extra is not None
        assert config.global_config.model_extra.get('autoConnectIde') is True


class TestVersionValidation:
    """Test version field validation (semantic versioning)."""

    def test_valid_version_string(self) -> None:
        """Standard semantic version - should PASS."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'version': '1.0.0',
            'command-names': ['test-cmd'],
            'command-defaults': {'system-prompt': 'test.md'},
        })
        assert config.version == '1.0.0'

    def test_valid_version_with_prerelease(self) -> None:
        """Semantic version with pre-release tag - should PASS."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'version': '2.1.0-beta.1',
            'command-names': ['test-cmd'],
            'command-defaults': {'system-prompt': 'test.md'},
        })
        assert config.version == '2.1.0-beta.1'

    def test_valid_version_with_build_metadata(self) -> None:
        """Semantic version with build metadata - should PASS."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'version': '1.0.0+build.123',
            'command-names': ['test-cmd'],
            'command-defaults': {'system-prompt': 'test.md'},
        })
        assert config.version == '1.0.0+build.123'

    def test_none_version(self) -> None:
        """None version (optional field) - should PASS."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
        })
        assert config.version is None

    def test_invalid_version_not_semver(self) -> None:
        """Non-semver string - should FAIL."""
        with pytest.raises(ValidationError, match='version must be a valid semantic version'):
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'version': 'abc',
            })

    def test_invalid_version_two_parts(self) -> None:
        """Two-part version string - should FAIL."""
        with pytest.raises(ValidationError, match='version must be a valid semantic version'):
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'version': '1.0',
            })

    def test_invalid_version_with_v_prefix(self) -> None:
        """Version with v prefix - should FAIL."""
        with pytest.raises(ValidationError, match='version must be a valid semantic version'):
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'version': 'v1.0.0',
            })

    def test_invalid_version_latest(self) -> None:
        """'latest' not allowed for config version (unlike claude_code_version) - should FAIL."""
        with pytest.raises(ValidationError, match='version must be a valid semantic version'):
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'version': 'latest',
            })


class TestRulesField:
    """Test rules field in EnvironmentConfig model."""

    def test_rules_field_valid(self) -> None:
        """Rules field accepts list of strings."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'rules': ['rule1.md', 'rule2.md'],
        })
        assert config.rules == ['rule1.md', 'rule2.md']

    def test_rules_field_default_empty_list(self) -> None:
        """Rules field defaults to empty list."""
        config = EnvironmentConfig.model_validate({'name': 'Test'})
        assert config.rules == []

    def test_rules_field_none_accepted(self) -> None:
        """Rules field accepts None value."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'rules': None,
        })
        assert config.rules is None

    def test_rules_included_in_validate_file_paths(self) -> None:
        """Rules field is covered by validate_file_paths validator."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'rules': ['https://example.com/rule.md', 'local-rule.md'],
        })
        assert config.rules is not None
        assert len(config.rules) == 2


class TestDescriptionField:
    """Test description field in EnvironmentConfig."""

    def test_description_field_optional(self) -> None:
        """Config validates without description."""
        config = EnvironmentConfig.model_validate({'name': 'Test'})
        assert config.description is None

    def test_description_field_accepted(self) -> None:
        """Config accepts a description string."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'description': 'A test environment for demos.',
        })
        assert config.description == 'A test environment for demos.'

    def test_description_multiline(self) -> None:
        """Config accepts multiline description."""
        desc = 'Line one\nLine two\nLine three'
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'description': desc,
        })
        assert config.description == desc


class TestPostInstallNotesField:
    """Test post-install-notes field in EnvironmentConfig."""

    def test_post_install_notes_field_optional(self) -> None:
        """Config validates without post-install-notes."""
        config = EnvironmentConfig.model_validate({'name': 'Test'})
        assert config.post_install_notes is None

    def test_post_install_notes_field_with_alias(self) -> None:
        """Config accepts post-install-notes via kebab-case alias."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'post-install-notes': 'Run setup commands after install.',
        })
        assert config.post_install_notes == 'Run setup commands after install.'

    def test_post_install_notes_multiline(self) -> None:
        """Config accepts multiline post-install-notes."""
        notes = 'Step 1: Do X\nStep 2: Do Y'
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'post-install-notes': notes,
        })
        assert config.post_install_notes == notes


class TestMergeKeysField:
    """Tests for the merge_keys field in EnvironmentConfig."""

    def test_merge_keys_accepts_valid_keys(self) -> None:
        """Field accepts a list of valid mergeable key names."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'inherit': 'parent.yaml',
            'merge-keys': ['agents', 'mcp-servers', 'dependencies'],
        })
        assert config.merge_keys == ['agents', 'mcp-servers', 'dependencies']

    def test_merge_keys_default_none(self) -> None:
        """Field defaults to None when not provided."""
        config = EnvironmentConfig.model_validate({'name': 'Test'})
        assert config.merge_keys is None

    def test_merge_keys_rejects_invalid_key(self) -> None:
        """Field rejects keys not in the mergeable set."""
        with pytest.raises(ValidationError, match='Invalid merge-keys'):
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'merge-keys': ['model'],
            })

    def test_merge_keys_alias(self) -> None:
        """Field uses 'merge-keys' as YAML alias."""
        field_info = EnvironmentConfig.model_fields['merge_keys']
        assert field_info.alias == 'merge-keys'

    def test_merge_keys_empty_list(self) -> None:
        """Field accepts an empty list (valid, semantically a no-op)."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'merge-keys': [],
        })
        assert config.merge_keys == []

    def test_merge_keys_all_valid_keys(self) -> None:
        """Field accepts all 11 mergeable keys at once."""
        all_keys = [
            'dependencies', 'agents', 'slash-commands', 'rules', 'skills',
            'files-to-download', 'hooks', 'mcp-servers',
            'global-config', 'user-settings', 'os-env-variables',
        ]
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'inherit': 'parent.yaml',
            'merge-keys': all_keys,
        })
        assert config.merge_keys == all_keys

    def test_merge_keys_rejects_multiple_invalid(self) -> None:
        """Field error message lists all invalid keys."""
        with pytest.raises(ValidationError, match='model'):
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'merge-keys': ['agents', 'model', 'name'],
            })


class TestInheritValidation:
    """Tests for inherit field validation (str | list[str] | None)."""

    def test_inherit_string_valid(self) -> None:
        """String inherit value is accepted."""
        config = EnvironmentConfig.model_validate({'name': 'Test', 'inherit': 'base.yaml'})
        assert config.inherit == 'base.yaml'

    def test_inherit_list_valid(self) -> None:
        """List of strings is accepted."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'inherit': ['base.yaml', 'aegis.yaml'],
        })
        assert config.inherit == ['base.yaml', 'aegis.yaml']

    def test_inherit_single_element_list_valid(self) -> None:
        """Single-element list is valid at model level."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'inherit': ['base.yaml'],
        })
        assert config.inherit == ['base.yaml']

    def test_inherit_none_valid(self) -> None:
        """None inherit is accepted (no inheritance)."""
        config = EnvironmentConfig.model_validate({'name': 'Test'})
        assert config.inherit is None

    def test_inherit_empty_list_rejected(self) -> None:
        """Empty list raises ValidationError."""
        with pytest.raises(ValidationError, match='inherit list cannot be empty'):
            EnvironmentConfig.model_validate({'name': 'Test', 'inherit': []})

    def test_inherit_list_with_empty_string_rejected(self) -> None:
        """List with empty string raises ValidationError."""
        with pytest.raises(ValidationError, match=r'inherit\[0\] cannot be empty'):
            EnvironmentConfig.model_validate({'name': 'Test', 'inherit': ['']})

    def test_inherit_list_with_blank_string_rejected(self) -> None:
        """List with whitespace-only string raises ValidationError."""
        with pytest.raises(ValidationError, match=r'inherit\[0\] cannot be empty'):
            EnvironmentConfig.model_validate({'name': 'Test', 'inherit': ['   ']})

    def test_inherit_list_with_non_string_rejected(self) -> None:
        """List with non-string element raises ValidationError."""
        with pytest.raises(ValidationError, match=r'inherit\[0\] must be a string or'):
            EnvironmentConfig.model_validate({'name': 'Test', 'inherit': [123]})

    def test_inherit_list_with_null_bytes_rejected(self) -> None:
        """List with null bytes in element raises ValidationError."""
        with pytest.raises(ValidationError, match=r'inherit\[0\] cannot contain null bytes'):
            EnvironmentConfig.model_validate({'name': 'Test', 'inherit': ['base\x00.yaml']})

    def test_inherit_dict_rejected(self) -> None:
        """Dict value (not in list) raises ValidationError."""
        with pytest.raises(ValidationError, match='must be a string or list'):
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'inherit': {'source': 'base.yaml'},
            })

    def test_inherit_int_rejected(self) -> None:
        """Integer value raises ValidationError."""
        with pytest.raises(ValidationError, match='must be a string or list'):
            EnvironmentConfig.model_validate({'name': 'Test', 'inherit': 42})

    def test_inherit_list_second_element_invalid(self) -> None:
        """Second element validation error includes correct index."""
        with pytest.raises(ValidationError, match=r'inherit\[1\] cannot be empty'):
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'inherit': ['valid.yaml', ''],
            })

    def test_inherit_three_element_list_valid(self) -> None:
        """Three-element list is accepted."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'inherit': ['a.yaml', 'b.yaml', 'c.yaml'],
        })
        assert config.inherit == ['a.yaml', 'b.yaml', 'c.yaml']

    def test_inherit_list_with_structured_entry_valid(self) -> None:
        """List with structured entry (dict) is accepted."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'inherit': [{'config': 'x.yaml', 'merge-keys': ['agents']}, 'y.yaml'],
        })
        assert len(config.inherit) == 2

    def test_inherit_list_mixed_entries_valid(self) -> None:
        """Mixed strings and dicts in list accepted."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'inherit': ['a.yaml', {'config': 'b.yaml', 'merge-keys': ['rules']}, 'c.yaml'],
        })
        assert len(config.inherit) == 3

    def test_inherit_list_structured_entry_missing_config(self) -> None:
        """Dict without config key raises ValidationError."""
        with pytest.raises(ValidationError, match=r'inherit\[0\]'):
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'inherit': [{'merge-keys': ['agents']}],
            })

    def test_inherit_single_structured_entry_valid(self) -> None:
        """Single structured entry in list passes validation."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'inherit': [{'config': 'x.yaml', 'merge-keys': ['agents']}],
        })
        assert len(config.inherit) == 1


class TestMCPServerStdioArgs:
    """Tests for MCPServerStdio args field."""

    def test_stdio_with_args_valid(self) -> None:
        """MCPServerStdio with args field passes validation."""
        server = MCPServerStdio.model_validate({
            'name': 'test-server',
            'command': 'python',
            'args': ['-m', 'my_server'],
        })
        assert server.args == ['-m', 'my_server']

    def test_stdio_without_args_valid(self) -> None:
        """MCPServerStdio without args field passes validation."""
        server = MCPServerStdio.model_validate({
            'name': 'test-server',
            'command': 'python -m my_server',
        })
        assert server.args is None

    def test_stdio_with_empty_args_valid(self) -> None:
        """MCPServerStdio with empty args list passes validation."""
        server = MCPServerStdio.model_validate({
            'name': 'test-server',
            'command': 'python',
            'args': [],
        })
        assert server.args == []

    def test_mcp_server_with_args_in_environment_config(self) -> None:
        """MCP server with args field in EnvironmentConfig context."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'mcp-servers': [
                {'name': 'srv', 'command': 'python', 'args': ['-m', 'server']},
            ],
        })
        assert len(config.mcp_servers) == 1


class TestVersionRequiresCommandNames:
    """Tests for version + command-names cross-field validation."""

    def test_version_without_command_names_raises(self) -> None:
        """version without command-names raises ValueError."""
        with pytest.raises(ValidationError, match='version requires command-names'):
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'version': '1.0.0',
            })

    def test_version_with_empty_command_names_raises(self) -> None:
        """version with empty command-names list raises ValueError."""
        with pytest.raises(ValidationError, match='version requires command-names'):
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'version': '1.0.0',
                'command-names': [],
            })

    def test_version_with_command_names_valid(self) -> None:
        """version with command-names passes validation."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'version': '1.0.0',
            'command-names': ['my-cmd'],
            'command-defaults': {'system-prompt': 'test.md'},
        })
        assert config.version == '1.0.0'

    def test_no_version_without_command_names_valid(self) -> None:
        """Omitting version without command-names is valid."""
        config = EnvironmentConfig.model_validate({'name': 'Test'})
        assert config.version is None

    def test_no_version_with_command_names_valid(self) -> None:
        """command-names without version is valid (version is optional)."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'command-names': ['my-cmd'],
            'command-defaults': {'system-prompt': 'test.md'},
        })
        assert config.version is None


class TestLinkProjectsDirRequiresCommandNames:
    """Tests for link-projects-dir + command-names cross-field validation."""

    def test_link_projects_dir_without_command_names_raises(self) -> None:
        """link-projects-dir true without command-names raises ValueError."""
        with pytest.raises(ValidationError, match='link-projects-dir requires command-names'):
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'link-projects-dir': True,
            })

    def test_link_projects_dir_with_empty_command_names_raises(self) -> None:
        """link-projects-dir true with empty command-names list raises ValueError."""
        with pytest.raises(ValidationError, match='link-projects-dir requires command-names'):
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'link-projects-dir': True,
                'command-names': [],
            })

    def test_link_projects_dir_with_command_names_valid(self) -> None:
        """link-projects-dir true with command-names passes validation."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'link-projects-dir': True,
            'command-names': ['my-cmd'],
            'command-defaults': {'system-prompt': 'test.md'},
        })
        assert config.link_projects_dir is True

    def test_link_projects_dir_false_without_command_names_valid(self) -> None:
        """link-projects-dir false without command-names is valid (falsy is off)."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'link-projects-dir': False,
        })
        assert config.link_projects_dir is False

    def test_no_link_projects_dir_without_command_names_valid(self) -> None:
        """Omitting link-projects-dir without command-names is valid (defaults to None)."""
        config = EnvironmentConfig.model_validate({'name': 'Test'})
        assert config.link_projects_dir is None


class TestMergeKeysRequiresInherit:
    """Tests for merge-keys + inherit cross-field validation."""

    def test_merge_keys_without_inherit_raises(self) -> None:
        """merge-keys without inherit raises ValueError."""
        with pytest.raises(ValidationError, match='merge-keys requires inherit'):
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'merge-keys': ['agents'],
            })

    def test_merge_keys_with_inherit_valid(self) -> None:
        """merge-keys with inherit passes validation."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'inherit': 'parent.yaml',
            'merge-keys': ['agents'],
        })
        assert config.merge_keys == ['agents']

    def test_no_merge_keys_without_inherit_valid(self) -> None:
        """Omitting both merge-keys and inherit is valid."""
        config = EnvironmentConfig.model_validate({'name': 'Test'})
        assert config.merge_keys is None
        assert config.inherit is None

    def test_inherit_without_merge_keys_valid(self) -> None:
        """inherit without merge-keys is valid (all keys use replace semantics)."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'inherit': 'parent.yaml',
        })
        assert config.inherit == 'parent.yaml'
        assert config.merge_keys is None

    def test_empty_merge_keys_without_inherit_valid(self) -> None:
        """Empty merge-keys list without inherit is valid (no-op)."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'merge-keys': [],
        })
        assert config.merge_keys == []


class TestProfileMCPRequiresCommandNames:
    """Tests for profile-scoped MCP servers + command-names cross-field validation."""

    def test_profile_mcp_without_command_names_raises(self) -> None:
        """Profile-scoped MCP server without command-names raises."""
        with pytest.raises(ValidationError, match='Profile-scoped MCP server'):
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'mcp-servers': [
                    {'name': 'my-server', 'scope': 'profile', 'command': 'python -m server'},
                ],
            })

    def test_profile_in_combined_scope_without_command_names_raises(self) -> None:
        """Combined scope containing profile without command-names raises."""
        with pytest.raises(ValidationError, match='Profile-scoped MCP server'):
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'mcp-servers': [
                    {'name': 'my-server', 'scope': ['user', 'profile'], 'command': 'python -m server'},
                ],
            })

    def test_profile_mcp_with_command_names_valid(self) -> None:
        """Profile-scoped MCP server with command-names passes."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'command-names': ['my-cmd'],
            'command-defaults': {'system-prompt': 'test.md'},
            'mcp-servers': [
                {'name': 'my-server', 'scope': 'profile', 'command': 'python -m server'},
            ],
        })
        assert len(config.mcp_servers) == 1

    def test_user_scope_mcp_without_command_names_valid(self) -> None:
        """Non-profile-scoped MCP server without command-names is valid."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'mcp-servers': [
                {'name': 'my-server', 'scope': 'user', 'command': 'python -m server'},
            ],
        })
        assert len(config.mcp_servers) == 1

    def test_multiple_profile_servers_all_reported(self) -> None:
        """All profile-scoped server names appear in error message."""
        with pytest.raises(ValidationError, match="'srv1'.*'srv2'|'srv2'.*'srv1'"):
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'mcp-servers': [
                    {'name': 'srv1', 'scope': 'profile', 'command': 'python -m s1'},
                    {'name': 'srv2', 'scope': 'profile', 'command': 'python -m s2'},
                ],
            })

    def test_http_profile_mcp_without_command_names_raises(self) -> None:
        """Profile-scoped HTTP MCP server without command-names raises."""
        with pytest.raises(ValidationError, match='Profile-scoped MCP server'):
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'mcp-servers': [
                    {'name': 'my-http', 'scope': 'profile', 'transport': 'http', 'url': 'http://localhost:3000'},
                ],
            })


class TestUserSettingsRootOnlyKeys:
    """Reject root-level YAML keys placed inside user-settings."""

    def test_status_line_kebab_rejected(self) -> None:
        """'status-line' is a root-level YAML key, not a settings.json key."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'status-line': {'file': 'x.py'}})
        assert "Key 'status-line' is not allowed in user-settings" in str(exc_info.value)
        assert 'root-level YAML key' in str(exc_info.value)

    def test_os_env_variables_rejected(self) -> None:
        """'os-env-variables' is a root-level YAML key, not a settings.json key."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'os-env-variables': {'VAR': 'value'}})
        assert "Key 'os-env-variables' is not allowed in user-settings" in str(exc_info.value)
        assert 'root-level YAML key' in str(exc_info.value)


class TestUserSettingsKebabCorrections:
    """Reject kebab-case spellings of known camelCase settings keys."""

    def test_always_thinking_enabled_kebab_rejected(self) -> None:
        """'always-thinking-enabled' must be spelled 'alwaysThinkingEnabled'."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'always-thinking-enabled': True})
        assert "Key 'always-thinking-enabled' is not a settings.json key" in str(exc_info.value)
        assert "use 'alwaysThinkingEnabled' instead" in str(exc_info.value)

    def test_company_announcements_kebab_rejected(self) -> None:
        """'company-announcements' must be spelled 'companyAnnouncements'."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'company-announcements': ['note']})
        assert "use 'companyAnnouncements' instead" in str(exc_info.value)

    def test_effort_level_kebab_rejected(self) -> None:
        """'effort-level' must be spelled 'effortLevel'."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'effort-level': 'high'})
        assert "use 'effortLevel' instead" in str(exc_info.value)

    def test_env_variables_kebab_rejected(self) -> None:
        """'env-variables' must be spelled 'env'."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'env-variables': {'VAR': 'value'}})
        assert "Key 'env-variables' is not a settings.json key" in str(exc_info.value)
        assert "use 'env' instead" in str(exc_info.value)


class TestUserSettingsGlobalOnlyKeys:
    """Reject keys that live in ~/.claude.json (global-config)."""

    @pytest.mark.parametrize('key', [
        'autoUpdates',
        'installMethod',
        'autoConnectIde',
        'autoInstallIdeExtension',
        'externalEditorContext',
        'teammateDefaultModel',
    ])
    def test_global_only_key_rejected(self, key: str) -> None:
        """Global-config keys are rejected in user-settings."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({key: 'value'})
        assert f"Key '{key}' belongs in global-config" in str(exc_info.value)
        assert 'not in user-settings' in str(exc_info.value)

    def test_global_only_key_rejected_even_when_null(self) -> None:
        """Placement is wrong regardless of value; a null global-only key is still rejected."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'autoConnectIde': None})
        assert "Key 'autoConnectIde' belongs in global-config" in str(exc_info.value)


class TestUserSettingsModelValue:
    """Validate the user-settings model value shape."""

    def test_model_string_accepted(self) -> None:
        """A non-empty model string is accepted."""
        from scripts.models.environment_config import UserSettings
        settings = UserSettings.model_validate({'model': 'opus'})
        assert settings.model_extra is not None
        assert settings.model_extra.get('model') == 'opus'

    def test_model_empty_string_rejected(self) -> None:
        """An empty model string is rejected."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'model': ''})
        assert 'user-settings.model must be a non-empty string' in str(exc_info.value)

    def test_model_non_string_rejected(self) -> None:
        """A non-string model is rejected."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'model': 123})
        assert 'user-settings.model must be a non-empty string' in str(exc_info.value)

    def test_model_null_allowed(self) -> None:
        """A null model is a deletion request and is allowed."""
        from scripts.models.environment_config import UserSettings
        settings = UserSettings.model_validate({'model': None})
        assert settings.model_extra is not None
        assert settings.model_extra.get('model') is None


class TestUserSettingsEnvValue:
    """Validate the user-settings env value shape."""

    def test_env_string_values_accepted(self) -> None:
        """A mapping of names to string values is accepted."""
        from scripts.models.environment_config import UserSettings
        settings = UserSettings.model_validate({'env': {'FOO': 'bar', 'BAZ': 'qux'}})
        assert settings.model_extra is not None
        assert settings.model_extra['env'] == {'FOO': 'bar', 'BAZ': 'qux'}

    def test_env_null_entry_value_allowed(self) -> None:
        """A null env entry value is a deletion request and is allowed."""
        from scripts.models.environment_config import UserSettings
        settings = UserSettings.model_validate({'env': {'DELETE_ME': None, 'KEEP': 'v'}})
        assert settings.model_extra is not None
        assert settings.model_extra['env'] == {'DELETE_ME': None, 'KEEP': 'v'}

    def test_env_non_string_value_rejected(self) -> None:
        """A non-string, non-null env value is rejected."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'env': {'PORT': 8080}})
        assert 'user-settings.env.PORT must be a string' in str(exc_info.value)
        assert 'quote the value in YAML' in str(exc_info.value)

    def test_env_not_a_mapping_rejected(self) -> None:
        """A non-mapping env value is rejected."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'env': ['FOO=bar']})
        assert 'user-settings.env must be a mapping' in str(exc_info.value)

    def test_env_invalid_name_rejected(self) -> None:
        """An invalid environment variable name is rejected."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'env': {'1BAD': 'value'}})
        assert 'invalid environment variable name' in str(exc_info.value)

    def test_env_value_with_null_byte_rejected(self) -> None:
        """A string env value containing a null byte is rejected."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'env': {'FOO': 'bar\x00baz'}})
        assert 'user-settings.env.FOO value cannot contain null bytes' in str(exc_info.value)

    def test_env_null_whole_value_allowed(self) -> None:
        """A null env value (deleting the whole env key) is allowed."""
        from scripts.models.environment_config import UserSettings
        settings = UserSettings.model_validate({'env': None})
        assert settings.model_extra is not None
        assert settings.model_extra.get('env') is None


class TestUserSettingsPermissionsValue:
    """Validate the user-settings permissions value shape."""

    def test_permissions_valid_shape_accepted(self) -> None:
        """A well-formed permissions mapping is accepted."""
        from scripts.models.environment_config import UserSettings
        settings = UserSettings.model_validate({
            'permissions': {
                'defaultMode': 'acceptEdits',
                'allow': ['Read(*)'],
                'deny': ['Bash(rm *)'],
                'ask': ['Write(*)'],
                'additionalDirectories': ['/tmp'],
            },
        })
        assert settings.model_extra is not None
        assert settings.model_extra['permissions']['defaultMode'] == 'acceptEdits'

    def test_permissions_not_a_mapping_rejected(self) -> None:
        """A non-mapping permissions value is rejected."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'permissions': ['Read(*)']})
        assert 'user-settings.permissions must be a mapping' in str(exc_info.value)

    def test_permissions_default_mode_kebab_rejected(self) -> None:
        """Kebab-case 'default-mode' must be 'defaultMode'."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'permissions': {'default-mode': 'default'}})
        assert 'user-settings.permissions uses camelCase keys' in str(exc_info.value)
        assert "use 'defaultMode' instead of 'default-mode'" in str(exc_info.value)

    def test_permissions_additional_directories_kebab_rejected(self) -> None:
        """Kebab-case 'additional-directories' must be 'additionalDirectories'."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'permissions': {'additional-directories': ['/tmp']}})
        assert "use 'additionalDirectories' instead of 'additional-directories'" in str(exc_info.value)

    def test_permissions_default_mode_invalid_enum_rejected(self) -> None:
        """An unknown defaultMode value is rejected."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'permissions': {'defaultMode': 'turbo'}})
        assert 'user-settings.permissions.defaultMode must be one of' in str(exc_info.value)

    @pytest.mark.parametrize('mode', [
        'acceptEdits', 'auto', 'bypassPermissions', 'default', 'delegate', 'dontAsk', 'plan',
    ])
    def test_permissions_default_mode_valid_enum_accepted(self, mode: str) -> None:
        """Every documented defaultMode value is accepted."""
        from scripts.models.environment_config import UserSettings
        settings = UserSettings.model_validate({'permissions': {'defaultMode': mode}})
        assert settings.model_extra is not None
        assert settings.model_extra['permissions']['defaultMode'] == mode

    def test_permissions_list_key_non_list_rejected(self) -> None:
        """A list-typed permissions key with a non-list value is rejected."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'permissions': {'allow': 'Read(*)'}})
        assert 'user-settings.permissions.allow must be a list of strings' in str(exc_info.value)

    def test_permissions_list_key_non_string_item_rejected(self) -> None:
        """A list-typed permissions key with a non-string item is rejected."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'permissions': {'deny': [123]}})
        assert 'user-settings.permissions.deny must be a list of strings' in str(exc_info.value)

    def test_permissions_null_allowed(self) -> None:
        """A null permissions value is a deletion request and is allowed."""
        from scripts.models.environment_config import UserSettings
        settings = UserSettings.model_validate({'permissions': None})
        assert settings.model_extra is not None
        assert settings.model_extra.get('permissions') is None

    def test_permissions_unknown_subkey_passes_through(self) -> None:
        """Unknown permissions sub-keys pass through untouched."""
        from scripts.models.environment_config import UserSettings
        settings = UserSettings.model_validate({'permissions': {'futureOption': True}})
        assert settings.model_extra is not None
        assert settings.model_extra['permissions']['futureOption'] is True


class TestUserSettingsAttributionValue:
    """Validate the user-settings attribution value shape."""

    def test_attribution_valid_shape_accepted(self) -> None:
        """A well-formed attribution mapping is accepted."""
        from scripts.models.environment_config import UserSettings
        settings = UserSettings.model_validate({'attribution': {'commit': '', 'pr': 'Co-authored-by'}})
        assert settings.model_extra is not None
        assert settings.model_extra['attribution'] == {'commit': '', 'pr': 'Co-authored-by'}

    def test_attribution_not_a_mapping_rejected(self) -> None:
        """A non-mapping attribution value is rejected."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'attribution': 'none'})
        assert 'user-settings.attribution must be a mapping' in str(exc_info.value)

    def test_attribution_non_string_sub_value_rejected(self) -> None:
        """A non-string attribution sub-value is rejected."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'attribution': {'commit': True}})
        assert 'user-settings.attribution.commit must be a string' in str(exc_info.value)

    def test_attribution_null_allowed(self) -> None:
        """A null attribution value is a deletion request and is allowed."""
        from scripts.models.environment_config import UserSettings
        settings = UserSettings.model_validate({'attribution': None})
        assert settings.model_extra is not None
        assert settings.model_extra.get('attribution') is None


class TestUserSettingsAlwaysThinkingEnabledValue:
    """Validate the user-settings alwaysThinkingEnabled value shape."""

    def test_boolean_accepted(self) -> None:
        """A boolean value is accepted."""
        from scripts.models.environment_config import UserSettings
        settings = UserSettings.model_validate({'alwaysThinkingEnabled': True})
        assert settings.model_extra is not None
        assert settings.model_extra['alwaysThinkingEnabled'] is True

    def test_non_boolean_rejected(self) -> None:
        """A non-boolean value is rejected."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'alwaysThinkingEnabled': 'yes'})
        assert 'user-settings.alwaysThinkingEnabled must be a boolean' in str(exc_info.value)

    def test_null_allowed(self) -> None:
        """A null value is a deletion request and is allowed."""
        from scripts.models.environment_config import UserSettings
        settings = UserSettings.model_validate({'alwaysThinkingEnabled': None})
        assert settings.model_extra is not None
        assert settings.model_extra.get('alwaysThinkingEnabled') is None


class TestUserSettingsCompanyAnnouncementsValue:
    """Validate the user-settings companyAnnouncements value shape."""

    def test_list_of_strings_accepted(self) -> None:
        """A list of strings is accepted."""
        from scripts.models.environment_config import UserSettings
        settings = UserSettings.model_validate({'companyAnnouncements': ['a', 'b']})
        assert settings.model_extra is not None
        assert settings.model_extra['companyAnnouncements'] == ['a', 'b']

    def test_non_list_rejected(self) -> None:
        """A non-list value is rejected."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'companyAnnouncements': 'single'})
        assert 'user-settings.companyAnnouncements must be a list of strings' in str(exc_info.value)

    def test_non_string_item_rejected(self) -> None:
        """A list with a non-string item is rejected."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'companyAnnouncements': ['ok', 42]})
        assert 'user-settings.companyAnnouncements must be a list of strings' in str(exc_info.value)

    def test_null_allowed(self) -> None:
        """A null value is a deletion request and is allowed."""
        from scripts.models.environment_config import UserSettings
        settings = UserSettings.model_validate({'companyAnnouncements': None})
        assert settings.model_extra is not None
        assert settings.model_extra.get('companyAnnouncements') is None


class TestUserSettingsEffortLevelValue:
    """Validate the user-settings effortLevel value and its model support."""

    @pytest.mark.parametrize('level', ['low', 'medium', 'high'])
    def test_unrestricted_levels_accepted_without_model(self, level: str) -> None:
        """low/medium/high require no model and are accepted."""
        from scripts.models.environment_config import UserSettings
        settings = UserSettings.model_validate({'effortLevel': level})
        assert settings.model_extra is not None
        assert settings.model_extra['effortLevel'] == level

    def test_invalid_effort_level_rejected(self) -> None:
        """An unknown effortLevel value is rejected."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'effortLevel': 'extreme'})
        assert 'user-settings.effortLevel must be one of' in str(exc_info.value)

    def test_null_allowed(self) -> None:
        """A null effortLevel value is a deletion request and is allowed."""
        from scripts.models.environment_config import UserSettings
        settings = UserSettings.model_validate({'effortLevel': None})
        assert settings.model_extra is not None
        assert settings.model_extra.get('effortLevel') is None

    # --- xhigh model support cross-check ---
    def test_xhigh_requires_model(self) -> None:
        """effortLevel 'xhigh' without a model is rejected."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'effortLevel': 'xhigh'})
        assert 'requires user-settings.model to be specified' in str(exc_info.value)

    def test_xhigh_with_opus_accepted(self) -> None:
        """effortLevel 'xhigh' with an Opus model is accepted."""
        from scripts.models.environment_config import UserSettings
        settings = UserSettings.model_validate({'model': 'claude-opus-4-8', 'effortLevel': 'xhigh'})
        assert settings.model_extra is not None
        assert settings.model_extra['effortLevel'] == 'xhigh'

    def test_xhigh_with_fable_accepted(self) -> None:
        """effortLevel 'xhigh' with a Fable model is accepted."""
        from scripts.models.environment_config import UserSettings
        settings = UserSettings.model_validate({'model': 'claude-fable-5', 'effortLevel': 'xhigh'})
        assert settings.model_extra is not None
        assert settings.model_extra['effortLevel'] == 'xhigh'

    def test_xhigh_with_best_alias_accepted(self) -> None:
        """effortLevel 'xhigh' with the exact 'best' alias is accepted."""
        from scripts.models.environment_config import UserSettings
        settings = UserSettings.model_validate({'model': 'best', 'effortLevel': 'xhigh'})
        assert settings.model_extra is not None
        assert settings.model_extra['effortLevel'] == 'xhigh'

    def test_xhigh_with_sonnet_rejected(self) -> None:
        """effortLevel 'xhigh' with a Sonnet model is rejected (Opus/Fable only)."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'model': 'claude-sonnet-4-6', 'effortLevel': 'xhigh'})
        assert 'only available for Opus and Fable models' in str(exc_info.value)

    def test_xhigh_with_bestish_substring_rejected(self) -> None:
        """effortLevel 'xhigh' with a model merely containing 'best' is rejected."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'model': 'bestish-model', 'effortLevel': 'xhigh'})
        assert 'only available for Opus and Fable models' in str(exc_info.value)

    # --- max model support cross-check ---
    def test_max_requires_model(self) -> None:
        """effortLevel 'max' without a model is rejected."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'effortLevel': 'max'})
        assert 'requires user-settings.model to be specified' in str(exc_info.value)

    def test_max_with_sonnet_accepted(self) -> None:
        """effortLevel 'max' with a Sonnet model is accepted (Sonnet supports max)."""
        from scripts.models.environment_config import UserSettings
        settings = UserSettings.model_validate({'model': 'claude-sonnet-4-6', 'effortLevel': 'max'})
        assert settings.model_extra is not None
        assert settings.model_extra['effortLevel'] == 'max'

    def test_max_with_opus_accepted(self) -> None:
        """effortLevel 'max' with an Opus model is accepted."""
        from scripts.models.environment_config import UserSettings
        settings = UserSettings.model_validate({'model': 'opus', 'effortLevel': 'max'})
        assert settings.model_extra is not None
        assert settings.model_extra['effortLevel'] == 'max'

    def test_max_with_best_alias_accepted(self) -> None:
        """effortLevel 'max' with the exact 'best' alias is accepted."""
        from scripts.models.environment_config import UserSettings
        settings = UserSettings.model_validate({'model': 'best', 'effortLevel': 'max'})
        assert settings.model_extra is not None
        assert settings.model_extra['effortLevel'] == 'max'

    def test_max_with_haiku_rejected(self) -> None:
        """effortLevel 'max' with a Haiku model is rejected."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'model': 'haiku', 'effortLevel': 'max'})
        assert 'only available for Opus, Sonnet, and Fable models' in str(exc_info.value)

    def test_max_with_bestish_substring_rejected(self) -> None:
        """effortLevel 'max' with a model merely containing 'best' is rejected."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({'model': 'bestish-model', 'effortLevel': 'max'})
        assert 'only available for Opus, Sonnet, and Fable models' in str(exc_info.value)


class TestUserSettingsMultipleErrors:
    """Multiple validation failures are surfaced together (newline-joined)."""

    def test_multiple_errors_reported(self) -> None:
        """Several rule violations appear in one raised message."""
        from scripts.models.environment_config import UserSettings
        with pytest.raises(ValidationError) as exc_info:
            UserSettings.model_validate({
                'model': '',
                'autoUpdates': False,
                'effort-level': 'high',
            })
        message = str(exc_info.value)
        assert 'user-settings.model must be a non-empty string' in message
        assert "Key 'autoUpdates' belongs in global-config" in message
        assert "use 'effortLevel' instead" in message


class TestGlobalConfigKnownKeyPlacement:
    """Reject known settings.json keys misplaced into global-config."""

    @pytest.mark.parametrize('key', [
        'model',
        'permissions',
        'env',
        'attribution',
        'alwaysThinkingEnabled',
        'effortLevel',
        'companyAnnouncements',
        'availableModels',
        'enforceAvailableModels',
    ])
    def test_settings_only_key_rejected(self, key: str) -> None:
        """A settings.json key placed in global-config is rejected."""
        from scripts.models.environment_config import GlobalConfig
        with pytest.raises(ValidationError) as exc_info:
            GlobalConfig.model_validate({key: 'value'})
        message = str(exc_info.value)
        assert f"Key '{key}' is a settings.json key" in message
        assert 'Move it to user-settings' in message

    def test_status_line_key_rejected_with_root_hint(self) -> None:
        """'statusLine' in global-config points to the root-level status-line key."""
        from scripts.models.environment_config import GlobalConfig
        with pytest.raises(ValidationError) as exc_info:
            GlobalConfig.model_validate({'statusLine': {'file': 'x.py'}})
        message = str(exc_info.value)
        assert "Key 'statusLine' is not valid in global-config" in message
        assert "root-level 'status-line' YAML key" in message

    def test_hooks_key_rejected_with_root_hint(self) -> None:
        """'hooks' in global-config points to the root-level hooks key."""
        from scripts.models.environment_config import GlobalConfig
        with pytest.raises(ValidationError) as exc_info:
            GlobalConfig.model_validate({'hooks': {'events': []}})
        message = str(exc_info.value)
        assert "Key 'hooks' is not valid in global-config" in message
        assert "root-level 'hooks' YAML key" in message

    def test_settings_only_null_value_still_rejected(self) -> None:
        """Placement errors apply regardless of value, including null."""
        from scripts.models.environment_config import GlobalConfig
        with pytest.raises(ValidationError) as exc_info:
            GlobalConfig.model_validate({'model': None})
        assert "Key 'model' is a settings.json key" in str(exc_info.value)

    def test_global_only_key_accepted(self) -> None:
        """A genuine global-config key passes."""
        from scripts.models.environment_config import GlobalConfig
        config = GlobalConfig.model_validate({'autoUpdates': True, 'installMethod': 'native'})
        assert config.model_extra is not None
        assert config.model_extra['autoUpdates'] is True
        assert config.model_extra['installMethod'] == 'native'


class TestSettingsValidationValueFunctions:
    """Direct coverage of the pure validation helpers."""

    def test_validate_user_settings_values_empty(self) -> None:
        """No known keys means no errors."""
        from scripts.models.environment_config import validate_user_settings_values
        assert validate_user_settings_values({'customKey': 'value'}) == []

    def test_validate_user_settings_values_collects_errors(self) -> None:
        """Errors are returned as a list rather than raised."""
        from scripts.models.environment_config import validate_user_settings_values
        errors = validate_user_settings_values({'status-line': {}, 'model': ''})
        assert len(errors) == 2

    def test_validate_global_config_values_empty(self) -> None:
        """No settings.json keys means no errors."""
        from scripts.models.environment_config import validate_global_config_values
        assert validate_global_config_values({'autoConnectIde': True}) == []

    def test_validate_global_config_values_collects_errors(self) -> None:
        """Settings-only keys are returned as errors."""
        from scripts.models.environment_config import validate_global_config_values
        errors = validate_global_config_values({'model': 'opus', 'hooks': {}})
        assert len(errors) == 2


class TestHookEventIdField:
    """Tests for the optional HookEvent id field (component selector identity)."""

    def test_id_defaults_to_none(self):
        """HookEvent without id defaults to None."""
        event = HookEvent.model_validate({'event': 'PostToolUse', 'type': 'command', 'command': 'h.py'})
        assert event.id is None

    def test_id_accepted_on_all_hook_types(self):
        """The id field is a common field accepted on every hook type."""
        payloads: list[dict[str, str]] = [
            {'event': 'PostToolUse', 'type': 'command', 'command': 'h.py', 'id': 'cmd-hook'},
            {'event': 'PostToolUse', 'type': 'http', 'url': 'http://localhost:8080/x', 'id': 'web-hook'},
            {'event': 'PreToolUse', 'type': 'prompt', 'prompt': 'Check safety', 'id': 'llm-hook'},
            {'event': 'PreToolUse', 'type': 'agent', 'prompt': 'Verify: $ARGUMENTS', 'id': 'agent-hook'},
        ]
        for payload in payloads:
            event = HookEvent.model_validate(payload)
            assert event.id == payload['id']


class TestComponentModel:
    """Tests for the Component Pydantic model field-level validation."""

    def test_minimal_component_defaults(self):
        """Component with only name and includes gets documented defaults."""
        component = Component.model_validate({'name': 'core', 'includes': {'agents': ['a.md']}})
        assert component.name == 'core'
        assert component.label is None
        assert component.description is None
        assert component.default is True
        assert component.requires == []
        assert component.bundles == []

    def test_full_component_valid(self):
        """Component with every field populated validates."""
        component = Component.model_validate({
            'name': 'mcp-http',
            'label': 'HTTP MCP servers',
            'description': 'Optional HTTP servers',
            'default': False,
            'requires': ['core'],
            'bundles': ['extras'],
            'includes': {'mcp-servers': ['srv']},
        })
        assert component.default is False
        assert component.requires == ['core']
        assert component.bundles == ['extras']

    def test_name_pattern_accepts_valid_names(self):
        """Lowercase names with digits, dots, underscores, and hyphens pass."""
        for name in ('core', 'mcp-http', 'a.b_c-1', '0start'):
            component = Component.model_validate({'name': name, 'includes': {'agents': ['a.md']}})
            assert component.name == name

    @pytest.mark.parametrize('value', [1, 0, 'yes', 'true', 'false', None])
    def test_default_rejects_non_bool_values(self, value):
        """default is strict: values the runtime's isinstance(bool) check rejects fail here too."""
        with pytest.raises(ValidationError):
            Component.model_validate({
                'name': 'core',
                'default': value,
                'includes': {'agents': ['a.md']},
            })

    def test_name_rejects_uppercase(self):
        """Uppercase letters in the name are rejected."""
        with pytest.raises(ValidationError, match='invalid'):
            Component.model_validate({'name': 'Core', 'includes': {'agents': ['a.md']}})

    def test_name_rejects_leading_hyphen(self):
        """Names must start with a letter or digit."""
        with pytest.raises(ValidationError, match='invalid'):
            Component.model_validate({'name': '-core', 'includes': {'agents': ['a.md']}})

    def test_name_rejects_spaces(self):
        """Names with spaces are rejected."""
        with pytest.raises(ValidationError, match='invalid'):
            Component.model_validate({'name': 'my core', 'includes': {'agents': ['a.md']}})

    def test_name_rejects_reserved_all(self):
        """The literal 'all' is reserved as a --select sentinel."""
        with pytest.raises(ValidationError, match='reserved'):
            Component.model_validate({'name': 'all', 'includes': {'agents': ['a.md']}})

    def test_name_rejects_reserved_none(self):
        """The literal 'none' is reserved as a --select sentinel."""
        with pytest.raises(ValidationError, match='reserved'):
            Component.model_validate({'name': 'none', 'includes': {'agents': ['a.md']}})

    def test_extra_fields_forbidden(self):
        """Unknown component fields are rejected (extra='forbid')."""
        with pytest.raises(ValidationError):
            Component.model_validate({'name': 'core', 'includes': {'agents': ['a.md']}, 'unknown': True})

    def test_includes_required(self):
        """A component without includes is rejected."""
        with pytest.raises(ValidationError):
            Component.model_validate({'name': 'core'})

    def test_includes_empty_dict_rejected(self):
        """An empty includes mapping is rejected."""
        with pytest.raises(ValidationError, match='at least one item'):
            Component.model_validate({'name': 'core', 'includes': {}})

    def test_includes_unknown_section_rejected(self):
        """Keys outside SELECTABLE_SECTIONS are rejected."""
        with pytest.raises(ValidationError, match='not selectable'):
            Component.model_validate({'name': 'core', 'includes': {'command-names': ['x']}})

    def test_includes_components_section_rejected(self):
        """The components registry itself is never claimable."""
        with pytest.raises(ValidationError, match='not selectable'):
            Component.model_validate({'name': 'core', 'includes': {'components': ['other']}})

    def test_includes_empty_selector_list_rejected(self):
        """An empty selector list for a section is rejected."""
        with pytest.raises(ValidationError, match='at least one selector'):
            Component.model_validate({'name': 'core', 'includes': {'agents': []}})

    def test_includes_empty_selector_string_rejected(self):
        """An empty selector string is rejected."""
        with pytest.raises(ValidationError, match='cannot be empty'):
            Component.model_validate({'name': 'core', 'includes': {'agents': ['']}})


class TestComponentsGraphValidation:
    """Tests for the EnvironmentConfig components cross-field graph validator."""

    @staticmethod
    def _config(**overrides: object) -> dict[str, object]:
        """Build a valid config dict with items in every selectable section.

        Args:
            overrides: Top-level keys to add or replace in the base config.

        Returns:
            A config dict suitable for EnvironmentConfig.model_validate().
        """
        base: dict[str, object] = {
            'name': 'Test',
            'agents': ['agents/a.md'],
            'slash-commands': ['commands/c.md'],
            'rules': ['rules/r.md'],
            'skills': [{'name': 'sk', 'base': 'skills/sk', 'files': ['SKILL.md']}],
            'mcp-servers': [{'name': 'srv', 'scope': 'user', 'command': 'python -m x'}],
            'dependencies': {'common': ['echo hi']},
            'files-to-download': [
                {'source': 'files/f.txt', 'dest': '~/.claude/f.txt'},
                {'source': 'files/g.txt', 'dest': '~/.claude/gdir/'},
            ],
            'hooks': {
                'files': ['hooks/h.py'],
                'events': [
                    {
                        'event': 'PostToolUse',
                        'matcher': 'Edit',
                        'type': 'command',
                        'command': 'h.py',
                        'id': 'post-edit',
                    },
                ],
            },
        }
        base.update(overrides)
        return base

    def test_components_absent_is_inert(self):
        """A config without components validates and defaults to an empty list."""
        config = EnvironmentConfig.model_validate(self._config())
        assert config.components == []

    def test_valid_components_all_sections(self):
        """Components claiming items in every selectable section validate."""
        config = EnvironmentConfig.model_validate(self._config(components=[
            {
                'name': 'core',
                'includes': {
                    'agents': ['agents/a.md'],
                    'slash-commands': ['commands/c.md'],
                    'rules': ['rules/r.md'],
                    'skills': ['sk'],
                    'mcp-servers': ['srv'],
                    'dependencies': ['echo hi'],
                    'files-to-download': ['~/.claude/f.txt'],
                    'hooks': ['post-edit', 'hooks/h.py'],
                },
            },
            {
                'name': 'extra',
                'default': False,
                'requires': ['core'],
                'bundles': ['core'],
                'includes': {'files-to-download': ['~/.claude/gdir/']},
            },
        ]))
        assert config.components is not None
        assert len(config.components) == 2

    def test_directory_dest_matches_by_normalized_identity(self):
        """A directory dest is claimable by its normalized final file path."""
        config = EnvironmentConfig.model_validate(self._config(components=[
            {'name': 'core', 'includes': {'files-to-download': ['~/.claude/gdir/g.txt']}},
        ]))
        assert config.components is not None

    def test_selector_whitespace_stripped_like_section_values(self):
        """Selectors receive the same whitespace stripping as section values."""
        config = EnvironmentConfig.model_validate(self._config(components=[
            {'name': 'core', 'includes': {'dependencies': [' echo hi ']}},
        ]))
        assert config.components is not None

    def test_duplicate_component_names_rejected(self):
        """Two components with the same name are rejected."""
        with pytest.raises(ValidationError, match='Duplicate component name'):
            EnvironmentConfig.model_validate(self._config(components=[
                {'name': 'core', 'includes': {'agents': ['agents/a.md']}},
                {'name': 'core', 'includes': {'rules': ['rules/r.md']}},
            ]))

    def test_dangling_requires_rejected(self):
        """A requires edge naming an unknown component is rejected."""
        with pytest.raises(ValidationError, match="requires unknown component 'nope'"):
            EnvironmentConfig.model_validate(self._config(components=[
                {'name': 'core', 'requires': ['nope'], 'includes': {'agents': ['agents/a.md']}},
            ]))

    def test_dangling_bundles_rejected(self):
        """A bundles edge naming an unknown component is rejected."""
        with pytest.raises(ValidationError, match="bundles unknown component 'nope'"):
            EnvironmentConfig.model_validate(self._config(components=[
                {'name': 'core', 'bundles': ['nope'], 'includes': {'agents': ['agents/a.md']}},
            ]))

    def test_agents_selector_matching_no_item_rejected(self):
        """A selector matching no agents entry is rejected."""
        with pytest.raises(ValidationError, match='matches no item in agents'):
            EnvironmentConfig.model_validate(self._config(components=[
                {'name': 'core', 'includes': {'agents': ['agents/missing.md']}},
            ]))

    def test_skills_selector_matching_no_item_rejected(self):
        """A selector matching no skill name is rejected."""
        with pytest.raises(ValidationError, match='matches no item in skills'):
            EnvironmentConfig.model_validate(self._config(components=[
                {'name': 'core', 'includes': {'skills': ['unknown']}},
            ]))

    def test_dependencies_selector_matching_no_item_rejected(self):
        """A selector matching no dependency command is rejected."""
        with pytest.raises(ValidationError, match='matches no item in dependencies'):
            EnvironmentConfig.model_validate(self._config(components=[
                {'name': 'core', 'includes': {'dependencies': ['echo other']}},
            ]))

    def test_hooks_selector_matching_no_item_rejected(self):
        """A selector matching no hook id and no hooks.files path is rejected."""
        with pytest.raises(ValidationError, match='matches no item in hooks'):
            EnvironmentConfig.model_validate(self._config(components=[
                {'name': 'core', 'includes': {'hooks': ['nope']}},
            ]))

    def test_duplicate_hook_ids_rejected_without_components(self):
        """Duplicate hook event ids are rejected even when no components exist."""
        with pytest.raises(ValidationError, match='Duplicate hook event id'):
            EnvironmentConfig.model_validate(self._config(hooks={
                'files': ['hooks/h.py'],
                'events': [
                    {'event': 'PostToolUse', 'type': 'command', 'command': 'h.py', 'id': 'dup'},
                    {'event': 'PreToolUse', 'type': 'command', 'command': 'h.py', 'id': 'dup'},
                ],
            }))

    def test_multiple_errors_aggregated(self):
        """Every graph error is reported in a single aggregated message."""
        with pytest.raises(ValidationError) as exc_info:
            EnvironmentConfig.model_validate(self._config(components=[
                {
                    'name': 'core',
                    'requires': ['nope'],
                    'includes': {'agents': ['agents/missing.md']},
                },
            ]))
        message = str(exc_info.value)
        assert "requires unknown component 'nope'" in message
        assert 'matches no item in agents' in message

    def test_duplicate_final_path_rejected_with_components(self):
        """Entries sharing a final path are ambiguous once components exist."""
        with pytest.raises(ValidationError, match='share the final path'):
            EnvironmentConfig.model_validate(self._config(
                **{'files-to-download': [
                    {'source': 'files/f.txt', 'dest': '~/.claude/gdir/f.txt'},
                    {'source': 'files/f.txt', 'dest': '~/.claude/gdir/'},
                ]},
                components=[
                    {'name': 'core', 'includes': {'files-to-download': ['~/.claude/gdir/f.txt']}},
                ],
            ))

    def test_whitespace_hook_id_matches_stripped_selector(self):
        """Identities are stripped so padded ids match stripped selectors."""
        config = EnvironmentConfig.model_validate(self._config(
            hooks={
                'files': ['hooks/h.py'],
                'events': [
                    {
                        'event': 'PostToolUse',
                        'type': 'command',
                        'command': 'h.py',
                        'id': ' post-edit ',
                    },
                ],
            },
            components=[
                {'name': 'core', 'includes': {'hooks': ['post-edit']}},
            ],
        ))
        assert config.components is not None
