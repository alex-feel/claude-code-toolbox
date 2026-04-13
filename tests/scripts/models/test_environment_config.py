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

from scripts.models.environment_config import EnvironmentConfig
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
            'merge-keys': ['agents', 'rules', 'mcp-servers', 'env-variables'],
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
        from scripts.models.environment_config import HookEvent
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
        from scripts.models.environment_config import HookEvent
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
        from scripts.models.environment_config import HookEvent
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
        from scripts.models.environment_config import HookEvent
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
        from scripts.models.environment_config import HookEvent
        with pytest.raises(ValidationError) as exc_info:
            HookEvent.model_validate({
                'event': 'PreToolUse',
                'type': 'command',
            })
        assert "requires 'command' field" in str(exc_info.value)

    # Invalid: command hook with prompt
    def test_command_hook_with_prompt_raises(self) -> None:
        """Command hook with prompt field raises ValueError."""
        from scripts.models.environment_config import HookEvent
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
        from scripts.models.environment_config import HookEvent
        with pytest.raises(ValidationError) as exc_info:
            HookEvent.model_validate({
                'event': 'PreToolUse',
                'type': 'prompt',
            })
        assert "requires 'prompt' field" in str(exc_info.value)

    # Invalid: prompt hook with command
    def test_prompt_hook_with_command_raises(self) -> None:
        """Prompt hook with command field raises ValueError."""
        from scripts.models.environment_config import HookEvent
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
        from scripts.models.environment_config import HookEvent
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
        from scripts.models.environment_config import HookEvent
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
        from scripts.models.environment_config import HookEvent
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
        from scripts.models.environment_config import HookEvent
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
        from scripts.models.environment_config import HookEvent
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
        from scripts.models.environment_config import HookEvent
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
        from scripts.models.environment_config import HookEvent
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
        from scripts.models.environment_config import HookEvent
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
        from scripts.models.environment_config import HookEvent
        event = HookEvent.model_validate({
            'event': 'PreToolUse',
            'type': 'command',
            'command': 'check.py',
            'if': 'Bash(git *)',
        })
        assert event.if_condition == 'Bash(git *)'

    def test_hook_with_status_message_alias(self) -> None:
        """The 'status-message' alias maps to status_message field."""
        from scripts.models.environment_config import HookEvent
        event = HookEvent.model_validate({
            'event': 'PreToolUse',
            'type': 'command',
            'command': 'check.py',
            'status-message': 'Running check...',
        })
        assert event.status_message == 'Running check...'

    def test_hook_with_async_alias(self) -> None:
        """The 'async' alias maps to async_execution field."""
        from scripts.models.environment_config import HookEvent
        event = HookEvent.model_validate({
            'event': 'Notification',
            'type': 'command',
            'command': 'notify.py',
            'async': True,
        })
        assert event.async_execution is True

    def test_hook_with_allowed_env_vars_alias(self) -> None:
        """The 'allowed-env-vars' alias maps to allowed_env_vars field."""
        from scripts.models.environment_config import HookEvent
        event = HookEvent.model_validate({
            'event': 'PostToolUse',
            'type': 'http',
            'url': 'https://example.com/hook',
            'allowed-env-vars': ['TOKEN', 'SECRET'],
        })
        assert event.allowed_env_vars == ['TOKEN', 'SECRET']

    def test_hook_with_once_field(self) -> None:
        """The once field is accepted on all types."""
        from scripts.models.environment_config import HookEvent
        event = HookEvent.model_validate({
            'event': 'PreToolUse',
            'type': 'agent',
            'prompt': 'Check once',
            'once': True,
        })
        assert event.once is True

    def test_common_fields_on_all_types(self) -> None:
        """Common fields (if, status-message, once, timeout) work on all types."""
        from scripts.models.environment_config import HookEvent
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
        from scripts.models.environment_config import HookEvent
        with pytest.raises(ValidationError) as exc_info:
            HookEvent.model_validate({
                'event': 'PostToolUse',
                'type': 'http',
            })
        assert "requires 'url' field" in str(exc_info.value)

    def test_http_hook_with_command_raises(self) -> None:
        """HTTP hook with command field raises ValueError."""
        from scripts.models.environment_config import HookEvent
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
        from scripts.models.environment_config import HookEvent
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
        from scripts.models.environment_config import HookEvent
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
        from scripts.models.environment_config import HookEvent
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
        from scripts.models.environment_config import HookEvent
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
        from scripts.models.environment_config import HookEvent
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
        from scripts.models.environment_config import HookEvent
        with pytest.raises(ValidationError) as exc_info:
            HookEvent.model_validate({
                'event': 'PreToolUse',
                'type': 'agent',
            })
        assert "requires 'prompt' field" in str(exc_info.value)

    def test_agent_hook_with_command_raises(self) -> None:
        """Agent hook with command field raises ValueError."""
        from scripts.models.environment_config import HookEvent
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
        from scripts.models.environment_config import HookEvent
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
        from scripts.models.environment_config import HookEvent
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
        from scripts.models.environment_config import HookEvent
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
        from scripts.models.environment_config import HookEvent
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
        from scripts.models.environment_config import HookEvent
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
        from scripts.models.environment_config import HookEvent
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
        from scripts.models.environment_config import HookEvent
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
        from scripts.models.environment_config import HookEvent
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


class TestEffortLevel:
    """Test effort-level field validation on EnvironmentConfig."""

    def test_effort_level_low(self) -> None:
        """effort-level 'low' validates correctly."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'effort-level': 'low',
        })
        assert config.effort_level == 'low'

    def test_effort_level_medium(self) -> None:
        """effort-level 'medium' validates correctly."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'effort-level': 'medium',
        })
        assert config.effort_level == 'medium'

    def test_effort_level_high(self) -> None:
        """effort-level 'high' validates correctly."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'effort-level': 'high',
        })
        assert config.effort_level == 'high'

    def test_effort_level_none_by_default(self) -> None:
        """effort-level defaults to None when not specified."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
        })
        assert config.effort_level is None

    def test_effort_level_invalid_value_rejected(self) -> None:
        """effort-level rejects invalid values."""
        with pytest.raises(ValidationError):
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'effort-level': 'extreme',
            })

    def test_effort_level_empty_string_rejected(self) -> None:
        """effort-level rejects empty string."""
        with pytest.raises(ValidationError):
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'effort-level': '',
            })

    def test_effort_level_max_with_opus_alias(self) -> None:
        """effort-level 'max' accepted when model is 'opus'."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'model': 'opus',
            'effort-level': 'max',
        })
        assert config.effort_level == 'max'

    def test_effort_level_max_with_opus_1m_alias(self) -> None:
        """effort-level 'max' accepted when model is 'opus[1m]'."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'model': 'opus[1m]',
            'effort-level': 'max',
        })
        assert config.effort_level == 'max'

    def test_effort_level_max_with_opusplan_alias(self) -> None:
        """effort-level 'max' accepted when model is 'opusplan'."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'model': 'opusplan',
            'effort-level': 'max',
        })
        assert config.effort_level == 'max'

    def test_effort_level_max_with_claude_opus_model(self) -> None:
        """effort-level 'max' accepted when model is 'claude-opus-4-6'."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'model': 'claude-opus-4-6',
            'effort-level': 'max',
        })
        assert config.effort_level == 'max'

    def test_effort_level_max_with_claude_opus_1m_model(self) -> None:
        """effort-level 'max' accepted when model is 'claude-opus-4-6[1m]'."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'model': 'claude-opus-4-6[1m]',
            'effort-level': 'max',
        })
        assert config.effort_level == 'max'

    def test_effort_level_max_rejected_with_sonnet_model(self) -> None:
        """effort-level 'max' rejected when model is 'sonnet'."""
        with pytest.raises(ValidationError, match='only available for Opus models'):
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'model': 'sonnet',
                'effort-level': 'max',
            })

    def test_effort_level_max_rejected_with_haiku_model(self) -> None:
        """effort-level 'max' rejected when model is 'haiku'."""
        with pytest.raises(ValidationError, match='only available for Opus models'):
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'model': 'haiku',
                'effort-level': 'max',
            })

    def test_effort_level_max_rejected_with_claude_sonnet_model(self) -> None:
        """effort-level 'max' rejected when model is 'claude-sonnet-4-6'."""
        with pytest.raises(ValidationError, match='only available for Opus models'):
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'model': 'claude-sonnet-4-6',
                'effort-level': 'max',
            })

    def test_effort_level_max_rejected_without_model(self) -> None:
        """effort-level 'max' rejected when model is not specified."""
        with pytest.raises(ValidationError, match='requires model to be specified'):
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'effort-level': 'max',
            })

    def test_effort_level_max_rejected_with_default_model(self) -> None:
        """effort-level 'max' rejected when model is 'default'."""
        with pytest.raises(ValidationError, match='only available for Opus models'):
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'model': 'default',
                'effort-level': 'max',
            })

    def test_effort_level_high_allowed_without_model(self) -> None:
        """effort-level 'high' accepted even without model (non-max levels are unrestricted)."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'effort-level': 'high',
        })
        assert config.effort_level == 'high'

    def test_effort_level_high_allowed_with_sonnet_model(self) -> None:
        """effort-level 'high' accepted with non-opus model (non-max levels are unrestricted)."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'model': 'sonnet',
            'effort-level': 'high',
        })
        assert config.effort_level == 'high'


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
        config = EnvironmentConfig.model_validate({'rules': ['rule1.md', 'rule2.md']})
        assert config.rules == ['rule1.md', 'rule2.md']

    def test_rules_field_default_empty_list(self) -> None:
        """Rules field defaults to empty list."""
        config = EnvironmentConfig.model_validate({})
        assert config.rules == []

    def test_rules_field_none_accepted(self) -> None:
        """Rules field accepts None value."""
        config = EnvironmentConfig.model_validate({'rules': None})
        assert config.rules is None

    def test_rules_included_in_validate_file_paths(self) -> None:
        """Rules field is covered by validate_file_paths validator."""
        config = EnvironmentConfig.model_validate({
            'rules': ['https://example.com/rule.md', 'local-rule.md'],
        })
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
        """Field accepts all 12 mergeable keys at once."""
        all_keys = [
            'dependencies', 'agents', 'slash-commands', 'rules', 'skills',
            'files-to-download', 'hooks', 'mcp-servers',
            'global-config', 'user-settings', 'env-variables', 'os-env-variables',
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


class TestModelValidation:
    """Tests for relaxed model field validation."""

    def test_claude_model_valid(self) -> None:
        """Claude model name passes."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'model': 'claude-sonnet-4-20250514',
        })
        assert config.model == 'claude-sonnet-4-20250514'

    def test_model_alias_valid(self) -> None:
        """Known alias passes."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'model': 'opus',
        })
        assert config.model == 'opus'

    def test_third_party_model_valid(self) -> None:
        """Third-party model name passes."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'model': 'gpt-4o',
        })
        assert config.model == 'gpt-4o'

    def test_openrouter_model_valid(self) -> None:
        """OpenRouter-prefixed model passes."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'model': 'openrouter/anthropic/claude-3.5-sonnet',
        })
        assert config.model == 'openrouter/anthropic/claude-3.5-sonnet'

    def test_empty_model_raises(self) -> None:
        """Empty string model raises."""
        with pytest.raises(ValidationError, match='empty or whitespace'):
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'model': '',
            })

    def test_whitespace_model_raises(self) -> None:
        """Whitespace-only model raises."""
        with pytest.raises(ValidationError, match='empty or whitespace'):
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'model': '   ',
            })

    def test_none_model_valid(self) -> None:
        """None (omitted) model is valid."""
        config = EnvironmentConfig.model_validate({'name': 'Test'})
        assert config.model is None


class TestEnvVariablesValidation:
    """Tests for env-variables field validation."""

    def test_valid_env_variables(self) -> None:
        """Valid environment variable names pass."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'env-variables': {'MY_VAR': 'value', '_PRIVATE': 'secret', 'PATH_EXT': '/usr/bin'},
        })
        assert config.env_variables == {'MY_VAR': 'value', '_PRIVATE': 'secret', 'PATH_EXT': '/usr/bin'}

    def test_invalid_env_variable_name_starts_with_digit(self) -> None:
        """Variable name starting with digit raises."""
        with pytest.raises(ValidationError, match='Invalid environment variable name'):
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'env-variables': {'1BAD': 'value'},
            })

    def test_invalid_env_variable_name_has_dash(self) -> None:
        """Variable name with dash raises."""
        with pytest.raises(ValidationError, match='Invalid environment variable name'):
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'env-variables': {'MY-VAR': 'value'},
            })

    def test_env_variable_value_with_null_byte_raises(self) -> None:
        """Value containing null byte raises."""
        with pytest.raises(ValidationError, match='null bytes'):
            EnvironmentConfig.model_validate({
                'name': 'Test',
                'env-variables': {'MY_VAR': 'val\x00ue'},
            })

    def test_none_env_variables_valid(self) -> None:
        """None (omitted) env-variables is valid."""
        config = EnvironmentConfig.model_validate({'name': 'Test'})
        assert config.env_variables is None

    def test_empty_env_variables_valid(self) -> None:
        """Empty dict for env-variables is valid."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'env-variables': {},
        })
        assert config.env_variables == {}


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
