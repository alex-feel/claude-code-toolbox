"""Test suite for MCP server scope validation.

This test suite validates that MCP servers correctly support all scope values:
- user: Server is available at user scope
- project: Server is available at project scope
- profile: Server is available only in profile session (new capability)
"""

import pytest
from pydantic import ValidationError

from scripts.models.environment_config import EnvironmentConfig
from scripts.models.environment_config import MCPServerHTTP
from scripts.models.environment_config import MCPServerStdio


class TestMCPServerHTTPScope:
    """Test MCPServerHTTP scope validation."""

    def test_user_scope_valid(self) -> None:
        """User scope is valid."""
        server = MCPServerHTTP.model_validate({
            'name': 'test-server',
            'transport': 'http',
            'url': 'http://localhost:8080',
            'scope': 'user',
        })
        assert server.scope == 'user'

    def test_project_scope_valid(self) -> None:
        """Project scope is valid."""
        server = MCPServerHTTP.model_validate({
            'name': 'test-server',
            'transport': 'http',
            'url': 'http://localhost:8080',
            'scope': 'project',
        })
        assert server.scope == 'project'

    def test_profile_scope_valid(self) -> None:
        """Profile scope is valid."""
        server = MCPServerHTTP.model_validate({
            'name': 'test-server',
            'transport': 'http',
            'url': 'http://localhost:8080',
            'scope': 'profile',
        })
        assert server.scope == 'profile'

    def test_default_scope_is_user(self) -> None:
        """Default scope should be user."""
        server = MCPServerHTTP.model_validate({
            'name': 'test-server',
            'transport': 'http',
            'url': 'http://localhost:8080',
        })
        assert server.scope == 'user'

    def test_invalid_scope_raises(self) -> None:
        """Invalid scope raises ValidationError."""
        with pytest.raises(ValidationError):
            MCPServerHTTP.model_validate({
                'name': 'test-server',
                'transport': 'http',
                'url': 'http://localhost:8080',
                'scope': 'invalid',
            })

    def test_local_scope_valid(self) -> None:
        """Local scope is valid."""
        server = MCPServerHTTP.model_validate({
            'name': 'test-server',
            'transport': 'http',
            'url': 'http://localhost:8080',
            'scope': 'local',
        })
        assert server.scope == 'local'


class TestMCPServerStdioScope:
    """Test MCPServerStdio scope validation."""

    def test_user_scope_valid(self) -> None:
        """User scope is valid."""
        server = MCPServerStdio.model_validate({
            'name': 'test-server',
            'command': 'echo hello',
            'scope': 'user',
        })
        assert server.scope == 'user'

    def test_project_scope_valid(self) -> None:
        """Project scope is valid."""
        server = MCPServerStdio.model_validate({
            'name': 'test-server',
            'command': 'echo hello',
            'scope': 'project',
        })
        assert server.scope == 'project'

    def test_profile_scope_valid(self) -> None:
        """Profile scope is valid."""
        server = MCPServerStdio.model_validate({
            'name': 'test-server',
            'command': 'echo hello',
            'scope': 'profile',
        })
        assert server.scope == 'profile'

    def test_default_scope_is_user(self) -> None:
        """Default scope should be user."""
        server = MCPServerStdio.model_validate({
            'name': 'test-server',
            'command': 'echo hello',
        })
        assert server.scope == 'user'

    def test_local_scope_valid(self) -> None:
        """Local scope is valid."""
        server = MCPServerStdio.model_validate({
            'name': 'test-server',
            'command': 'echo hello',
            'scope': 'local',
        })
        assert server.scope == 'local'

    def test_invalid_scope_raises(self) -> None:
        """Invalid scope raises ValidationError."""
        with pytest.raises(ValidationError):
            MCPServerStdio.model_validate({
                'name': 'test-server',
                'command': 'echo hello',
                'scope': 'invalid',
            })


class TestEnvironmentConfigWithProfileScope:
    """Test EnvironmentConfig with profile-scoped MCP servers."""

    def test_profile_scoped_http_server(self) -> None:
        """Profile-scoped HTTP server validates correctly."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test Environment',
            'mcp-servers': [{
                'name': 'profile-server',
                'transport': 'http',
                'url': 'http://localhost:8080',
                'scope': 'profile',
            }],
        })
        assert config.mcp_servers is not None
        assert len(config.mcp_servers) == 1
        assert config.mcp_servers[0]['scope'] == 'profile'

    def test_profile_scoped_stdio_server(self) -> None:
        """Profile-scoped stdio server validates correctly."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test Environment',
            'mcp-servers': [{
                'name': 'profile-server',
                'command': 'echo hello',
                'scope': 'profile',
            }],
        })
        assert config.mcp_servers is not None
        assert len(config.mcp_servers) == 1
        assert config.mcp_servers[0]['scope'] == 'profile'

    def test_mixed_scope_servers(self) -> None:
        """Mix of user, project, and profile scoped servers validates correctly."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test Environment',
            'mcp-servers': [
                {
                    'name': 'user-server',
                    'command': 'echo user',
                    'scope': 'user',
                },
                {
                    'name': 'project-server',
                    'transport': 'http',
                    'url': 'http://localhost:8081',
                    'scope': 'project',
                },
                {
                    'name': 'profile-server',
                    'command': 'echo profile',
                    'scope': 'profile',
                },
            ],
        })
        assert config.mcp_servers is not None
        assert len(config.mcp_servers) == 3
        assert config.mcp_servers[0]['scope'] == 'user'
        assert config.mcp_servers[1]['scope'] == 'project'
        assert config.mcp_servers[2]['scope'] == 'profile'

    def test_sse_transport_with_profile_scope(self) -> None:
        """SSE transport with profile scope validates correctly."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test Environment',
            'mcp-servers': [{
                'name': 'sse-profile-server',
                'transport': 'sse',
                'url': 'http://localhost:8080/events',
                'scope': 'profile',
            }],
        })
        assert config.mcp_servers is not None
        assert len(config.mcp_servers) == 1
        assert config.mcp_servers[0]['transport'] == 'sse'
        assert config.mcp_servers[0]['scope'] == 'profile'


class TestCombinedScopeSupport:
    """Test combined scope support for MCP servers."""

    def test_combined_scope_user_profile_valid(self) -> None:
        """Combined user + profile scope is valid."""
        server = MCPServerHTTP.model_validate({
            'name': 'test-server',
            'transport': 'http',
            'url': 'http://localhost:8080',
            'scope': ['user', 'profile'],
        })
        assert server.scope == ['user', 'profile']

    def test_combined_scope_local_profile_valid(self) -> None:
        """Combined local + profile scope is valid."""
        server = MCPServerStdio.model_validate({
            'name': 'test-server',
            'command': 'echo hello',
            'scope': ['local', 'profile'],
        })
        assert server.scope == ['local', 'profile']

    def test_comma_separated_scope_valid(self) -> None:
        """Comma-separated scope string is valid."""
        server = MCPServerHTTP.model_validate({
            'name': 'test-server',
            'transport': 'http',
            'url': 'http://localhost:8080',
            'scope': 'user, profile',
        })
        assert server.scope == ['user', 'profile']

    def test_case_normalization(self) -> None:
        """Scope values are case-normalized."""
        server = MCPServerHTTP.model_validate({
            'name': 'test-server',
            'transport': 'http',
            'url': 'http://localhost:8080',
            'scope': ['USER', 'Profile'],
        })
        assert server.scope == ['user', 'profile']

    def test_combined_without_profile_invalid(self) -> None:
        """Combined scopes without profile raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            MCPServerHTTP.model_validate({
                'name': 'test-server',
                'transport': 'http',
                'url': 'http://localhost:8080',
                'scope': ['user', 'local'],
            })
        assert 'profile' in str(exc_info.value).lower()

    def test_duplicate_scopes_invalid(self) -> None:
        """Duplicate scope values raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            MCPServerHTTP.model_validate({
                'name': 'test-server',
                'transport': 'http',
                'url': 'http://localhost:8080',
                'scope': ['user', 'user', 'profile'],
            })
        assert 'duplicate' in str(exc_info.value).lower()

    def test_environment_config_combined_scope(self) -> None:
        """EnvironmentConfig validates combined scope correctly."""
        config = EnvironmentConfig.model_validate({
            'name': 'Test Environment',
            'mcp-servers': [{
                'name': 'combined-server',
                'transport': 'http',
                'url': 'http://localhost:8080',
                'scope': ['user', 'profile'],
            }],
        })
        assert config.mcp_servers is not None
        assert len(config.mcp_servers) == 1
        assert config.mcp_servers[0]['scope'] == ['user', 'profile']
