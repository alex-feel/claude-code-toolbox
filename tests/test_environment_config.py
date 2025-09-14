"""Tests for environment configuration Pydantic models."""

import pytest
from pydantic import ValidationError
from scripts.models.environment_config import CommandDefaults
from scripts.models.environment_config import EnvironmentConfig
from scripts.models.environment_config import HookEvent
from scripts.models.environment_config import Hooks
from scripts.models.environment_config import MCPServerHTTP
from scripts.models.environment_config import MCPServerStdio
from scripts.models.environment_config import Permissions


class TestMCPServerHTTP:
    """Test MCPServerHTTP model."""

    def test_valid_http_server(self):
        """Test valid HTTP server configuration."""
        server = MCPServerHTTP(
            name='test-server',
            transport='http',
            url='http://localhost:3000',
        )
        assert server.name == 'test-server'
        assert server.scope == 'user'  # default
        assert server.transport == 'http'
        assert server.url == 'http://localhost:3000'
        assert server.header is None

    def test_sse_server_with_header(self):
        """Test SSE server with authentication header."""
        server = MCPServerHTTP(
            name='sse-server',
            scope='project',
            transport='sse',
            url='https://api.example.com',
            header='Bearer token123',
        )
        assert server.transport == 'sse'
        assert server.header == 'Bearer token123'
        assert server.scope == 'project'

    def test_invalid_transport(self):
        """Test invalid transport type."""
        with pytest.raises(ValidationError) as exc_info:
            MCPServerHTTP(
                name='test',
                transport='websocket',  # Invalid
                url='http://example.com',
            )
        assert 'transport' in str(exc_info.value)

    def test_invalid_scope(self):
        """Test invalid scope."""
        with pytest.raises(ValidationError) as exc_info:
            MCPServerHTTP(
                name='test',
                scope='global',  # Invalid
                transport='http',
                url='http://example.com',
            )
        assert 'scope' in str(exc_info.value)


class TestMCPServerStdio:
    """Test MCPServerStdio model."""

    def test_valid_stdio_server(self):
        """Test valid stdio server configuration."""
        server = MCPServerStdio(
            name='stdio-server',
            command='npx @modelcontextprotocol/server-memory',
        )
        assert server.name == 'stdio-server'
        assert server.scope == 'user'  # default
        assert server.command == 'npx @modelcontextprotocol/server-memory'
        assert server.env is None

    def test_stdio_server_with_env(self):
        """Test stdio server with environment variables."""
        server = MCPServerStdio(
            name='test',
            scope='project',
            command='python server.py',
            env='DEBUG=true',
        )
        assert server.env == 'DEBUG=true'
        assert server.scope == 'project'


class TestHookEvent:
    """Test HookEvent model."""

    def test_valid_hook_event(self):
        """Test valid hook event configuration."""
        hook = HookEvent(
            event='PostToolUse',
            command='format.py',
        )
        assert hook.event == 'PostToolUse'
        assert hook.matcher == ''  # default
        assert hook.type == 'command'  # default
        assert hook.command == 'format.py'

    def test_hook_with_matcher(self):
        """Test hook event with regex matcher."""
        hook = HookEvent(
            event='Notification',
            matcher='Edit|Write|MultiEdit',
            type='command',
            command='lint.sh',
        )
        assert hook.matcher == 'Edit|Write|MultiEdit'

    def test_invalid_type(self):
        """Test invalid hook type."""
        with pytest.raises(ValidationError) as exc_info:
            HookEvent(
                event='PostToolUse',
                type='script',  # Invalid
                command='test.py',
            )
        assert 'type' in str(exc_info.value)


class TestHooks:
    """Test Hooks model."""

    def test_empty_hooks(self):
        """Test empty hooks configuration."""
        hooks = Hooks()
        assert hooks.files == []
        assert hooks.events == []

    def test_hooks_with_files_and_events(self):
        """Test hooks with files and events."""
        hooks = Hooks(
            files=['hooks/format.py', 'hooks/lint.sh'],
            events=[
                {
                    'event': 'PostToolUse',
                    'matcher': 'Edit',
                    'type': 'command',
                    'command': 'format.py',
                },
            ],
        )
        assert len(hooks.files) == 2
        assert len(hooks.events) == 1
        assert hooks.events[0].event == 'PostToolUse'


class TestPermissions:
    """Test Permissions model."""

    def test_empty_permissions(self):
        """Test empty permissions configuration."""
        perms = Permissions()
        assert perms.default_mode is None
        assert perms.allow is None
        assert perms.deny is None
        assert perms.ask is None
        assert perms.additional_directories is None

    def test_permissions_with_all_fields(self):
        """Test permissions with all fields."""
        perms = Permissions(
            defaultMode='acceptEdits',
            allow=['mcp__test', 'read'],
            deny=['write'],
            ask=['delete'],
            additionalDirectories=['/tmp', '/var'],
        )
        assert perms.default_mode == 'acceptEdits'
        assert perms.allow == ['mcp__test', 'read']
        assert perms.deny == ['write']
        assert perms.ask == ['delete']
        assert perms.additional_directories == ['/tmp', '/var']

    def test_invalid_default_mode(self):
        """Test invalid default mode."""
        with pytest.raises(ValidationError) as exc_info:
            Permissions(defaultMode='always')  # Invalid
        assert 'defaultMode' in str(exc_info.value)


class TestCommandDefaults:
    """Test CommandDefaults model."""

    def test_empty_defaults(self):
        """Test empty command defaults."""
        defaults = CommandDefaults()
        assert defaults.output_style is None
        assert defaults.system_prompt is None

    def test_output_style_only(self):
        """Test with output style only."""
        defaults = CommandDefaults(**{'output-style': 'concise'})
        assert defaults.output_style == 'concise'
        assert defaults.system_prompt is None

    def test_system_prompt_only(self):
        """Test with system prompt only."""
        defaults = CommandDefaults(**{'system-prompt': 'prompt.md'})
        assert defaults.output_style is None
        assert defaults.system_prompt == 'prompt.md'

    def test_mutual_exclusivity(self):
        """Test that output-style and system-prompt are mutually exclusive."""
        with pytest.raises(ValidationError) as exc_info:
            CommandDefaults(**{
                'output-style': 'concise',
                'system-prompt': 'prompt.md',
            })
        assert 'mutually exclusive' in str(exc_info.value).lower()


class TestEnvironmentConfig:
    """Test EnvironmentConfig model."""

    def test_minimal_valid_config(self):
        """Test minimal valid environment configuration."""
        config = EnvironmentConfig(
            name='Test Environment',
            **{'command-name': 'claude-test'},
        )
        assert config.name == 'Test Environment'
        assert config.command_name == 'claude-test'
        assert config.base_url is None
        assert config.dependencies == []
        assert config.agents == []
        assert config.mcp_servers == []

    def test_full_config(self, sample_environment_config):
        """Test full environment configuration."""
        config = EnvironmentConfig(**sample_environment_config)
        assert config.name == 'Test Environment'
        assert config.command_name == 'claude-test'
        assert config.base_url == 'https://example.com/repo'
        assert len(config.dependencies) == 2
        assert len(config.agents) == 1
        assert len(config.mcp_servers) == 1
        assert config.model == 'sonnet'
        assert config.env_variables == {'TEST_VAR': 'test_value'}

    def test_invalid_command_name_spaces(self):
        """Test invalid command name with spaces."""
        with pytest.raises(ValidationError) as exc_info:
            EnvironmentConfig(
                name='Test',
                **{'command-name': 'invalid name'},
            )
        assert 'command-name' in str(exc_info.value)

    def test_invalid_command_name_special_chars(self):
        """Test invalid command name with special characters."""
        with pytest.raises(ValidationError) as exc_info:
            EnvironmentConfig(
                name='Test',
                **{'command-name': 'claude-test!'},
            )
        assert 'alphanumeric' in str(exc_info.value)

    def test_command_name_without_claude_prefix(self):
        """Test command name without claude- prefix."""
        with pytest.raises(ValidationError) as exc_info:
            EnvironmentConfig(
                name='Test',
                **{'command-name': 'test-env'},
            )
        assert 'should start with' in str(exc_info.value)

    def test_invalid_base_url(self):
        """Test invalid base URL."""
        with pytest.raises(ValidationError) as exc_info:
            EnvironmentConfig(
                name='Test',
                **{
                    'command-name': 'claude-test',
                    'base-url': 'ftp://example.com',
                },
            )
        assert 'http://' in str(exc_info.value)

    def test_invalid_model(self):
        """Test invalid model configuration."""
        with pytest.raises(ValidationError) as exc_info:
            EnvironmentConfig(
                name='Test',
                **{
                    'command-name': 'claude-test',
                    'model': 'gpt-4',
                },
            )
        assert 'model must be' in str(exc_info.value)

    def test_valid_model_aliases(self):
        """Test valid model aliases."""
        valid_models = ['default', 'sonnet', 'opus', 'haiku', 'sonnet[1m]', 'opusplan', 'claude-3-sonnet']
        for model in valid_models:
            config = EnvironmentConfig(
                name='Test',
                **{
                    'command-name': 'claude-test',
                    'model': model,
                },
            )
            assert config.model == model

    def test_local_paths_allowed(self):
        """Test that local paths are now allowed."""
        # Test relative paths with ..
        config1 = EnvironmentConfig(
            name='Test',
            **{
                'command-name': 'claude-test',
                'agents': ['../../../custom/agent.md'],
            },
        )
        assert config1.agents[0] == '../../../custom/agent.md'

        # Test absolute paths
        config2 = EnvironmentConfig(
            name='Test',
            **{
                'command-name': 'claude-test',
                'slash-commands': ['/etc/custom-command.md', 'C:\\custom\\command.md'],
            },
        )
        assert config2.slash_commands[0] == '/etc/custom-command.md'
        assert config2.slash_commands[1] == 'C:\\custom\\command.md'

        # Test home directory paths
        config3 = EnvironmentConfig(
            name='Test',
            **{
                'command-name': 'claude-test',
                'output-styles': ['~/my-styles/custom.md'],
            },
        )
        assert config3.output_styles[0] == '~/my-styles/custom.md'

    def test_url_paths_allowed(self):
        """Test that full URLs are allowed in file paths."""
        config = EnvironmentConfig(
            name='Test',
            **{
                'command-name': 'claude-test',
                'agents': ['https://example.com/agent.md'],
                'slash-commands': ['http://example.com/cmd.md'],
                'output-styles': ['https://example.com/style.md'],
            },
        )
        assert config.agents[0] == 'https://example.com/agent.md'

    def test_mcp_server_validation_http(self):
        """Test MCP server validation for HTTP transport."""
        config = EnvironmentConfig(
            name='Test',
            **{
                'command-name': 'claude-test',
                'mcp-servers': [
                    {
                        'name': 'http-server',
                        'transport': 'http',
                        'url': 'http://localhost:3000',
                    },
                ],
            },
        )
        assert len(config.mcp_servers) == 1
        assert config.mcp_servers[0]['transport'] == 'http'

    def test_mcp_server_validation_stdio(self):
        """Test MCP server validation for stdio transport."""
        config = EnvironmentConfig(
            name='Test',
            **{
                'command-name': 'claude-test',
                'mcp-servers': [
                    {
                        'name': 'stdio-server',
                        'command': 'npx server',
                    },
                ],
            },
        )
        assert len(config.mcp_servers) == 1
        assert config.mcp_servers[0]['command'] == 'npx server'

    def test_mcp_server_missing_name(self):
        """Test MCP server without name field."""
        with pytest.raises(ValidationError) as exc_info:
            EnvironmentConfig(
                name='Test',
                **{
                    'command-name': 'claude-test',
                    'mcp-servers': [
                        {
                            'transport': 'http',
                            'url': 'http://localhost:3000',
                        },
                    ],
                },
            )
        assert 'name' in str(exc_info.value)

    def test_mcp_server_missing_transport_and_command(self):
        """Test MCP server without transport or command."""
        with pytest.raises(ValidationError) as exc_info:
            EnvironmentConfig(
                name='Test',
                **{
                    'command-name': 'claude-test',
                    'mcp-servers': [
                        {
                            'name': 'invalid-server',
                        },
                    ],
                },
            )
        assert 'transport' in str(exc_info.value) or 'command' in str(exc_info.value)

    def test_config_strip_whitespace(self):
        """Test that strings are stripped of whitespace."""
        config = EnvironmentConfig(
            name='  Test Environment  ',
            **{'command-name': '  claude-test  '},
        )
        assert config.name == 'Test Environment'
        assert config.command_name == 'claude-test'

    def test_populate_by_name(self):
        """Test that both field names and aliases work."""
        # Using aliases
        config1 = EnvironmentConfig(
            name='Test',
            **{
                'command-name': 'claude-test',
                'base-url': 'https://example.com',
                'mcp-servers': [],
                'slash-commands': [],
                'output-styles': [],
                'env-variables': {},
                'command-defaults': {},
            },
        )

        # Using field names
        config2 = EnvironmentConfig(
            name='Test',
            command_name='claude-test',
            base_url='https://example.com',
            mcp_servers=[],
            slash_commands=[],
            output_styles=[],
            env_variables={},
            command_defaults={},
        )

        assert config1.command_name == config2.command_name
        assert config1.base_url == config2.base_url
