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
        })
        assert config.version == '1.0.0'

    def test_valid_version_with_prerelease(self) -> None:
        """Semantic version with pre-release tag - should PASS."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'version': '2.1.0-beta.1',
        })
        assert config.version == '2.1.0-beta.1'

    def test_valid_version_with_build_metadata(self) -> None:
        """Semantic version with build metadata - should PASS."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test',
            'version': '1.0.0+build.123',
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
