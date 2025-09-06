"""Pytest configuration and shared fixtures for all tests."""

import json
import sys
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
import yaml

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_home_dir(temp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Mock home directory for testing."""
    monkeypatch.setattr(Path, 'home', lambda: temp_dir)
    return temp_dir


@pytest.fixture
def claude_user_dir(mock_home_dir: Path) -> Path:
    """Create and return Claude user directory."""
    claude_dir = mock_home_dir / '.claude'
    claude_dir.mkdir(exist_ok=True)
    return claude_dir


@pytest.fixture
def sample_environment_config() -> dict[str, Any]:
    """Return a sample environment configuration."""
    return {
        'name': 'Test Environment',
        'command-name': 'claude-test',
        'base-url': 'https://example.com/repo',
        'dependencies': ['pytest', 'pyyaml'],
        'agents': ['agents/test-agent.md'],
        'mcp-servers': [
            {
                'name': 'test-server',
                'scope': 'user',
                'transport': 'http',
                'url': 'http://localhost:3000',
            },
        ],
        'slash-commands': ['commands/test-command.md'],
        'output-styles': ['styles/test-style.md'],
        'hooks': {
            'files': ['hooks/test-hook.py'],
            'events': [
                {
                    'event': 'PostToolUse',
                    'matcher': 'Edit|Write',
                    'type': 'command',
                    'command': 'test-hook.py',
                },
            ],
        },
        'model': 'sonnet',
        'env-variables': {'TEST_VAR': 'test_value'},
        'permissions': {
            'defaultMode': 'default',
            'allow': ['mcp__test'],
        },
        'command-defaults': {
            'output-style': 'test-style',
        },
    }


@pytest.fixture
def valid_yaml_content(sample_environment_config: dict) -> str:
    """Return valid YAML content for testing."""
    return yaml.dump(sample_environment_config)


@pytest.fixture
def invalid_yaml_content() -> str:
    """Return invalid YAML content for testing."""
    return '''
name: Test
command-name: invalid name with spaces
'''


@pytest.fixture
def mock_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock URL fetching for testing."""
    def mock_urlopen(url, *args, **kwargs):
        # Mark args and kwargs as intentionally unused
        del args, kwargs

        class MockResponse:
            def read(self):
                if 'node' in str(url):
                    return json.dumps([{'version': 'v20.0.0', 'lts': 'Iron'}]).encode()
                if 'git-scm' in str(url):
                    return b'<a href="Git-2.40.0-64-bit.exe">Download</a>'
                return b'Mock content'

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        return MockResponse()

    import urllib.request
    monkeypatch.setattr(urllib.request, 'urlopen', mock_urlopen)


@pytest.fixture
def mock_commands(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Mock system commands for testing."""
    commands_output = {
        'node': '--version: v20.0.0',
        'npm': 'v10.0.0',
        'claude': '--version: 0.8.0',
        'git': '--version: git version 2.40.0',
        'bash': '--version: GNU bash, version 5.0.0',
        'winget': 'v1.5.0',
        'python': '3.12.0',
        'py': '3.12.0',
    }

    def mock_which(cmd):
        if cmd in commands_output:
            return f'/usr/bin/{cmd}'
        return None

    def mock_run(cmd, *args, **kwargs):
        # Mark args and kwargs as intentionally unused
        del args, kwargs
        import subprocess
        cmd_name = cmd[0] if isinstance(cmd, list) else cmd.split()[0]

        # Remove .exe, .cmd extensions for Windows
        cmd_name = cmd_name.replace('.exe', '').replace('.cmd', '')

        if cmd_name in commands_output:
            return subprocess.CompletedProcess(
                cmd, 0, commands_output.get(cmd_name, ''), '',
            )
        return subprocess.CompletedProcess(cmd, 1, '', 'Command not found')

    import shutil
    import subprocess
    monkeypatch.setattr(shutil, 'which', mock_which)
    monkeypatch.setattr(subprocess, 'run', mock_run)

    return commands_output


@pytest.fixture
def mock_platform(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> str:
    """Mock platform detection."""
    system = getattr(request, 'param', 'Linux')
    monkeypatch.setattr('platform.system', lambda: system)
    monkeypatch.setattr('platform.machine', lambda: 'x86_64')
    return system


@pytest.fixture
def environment_yaml_files(temp_dir: Path) -> dict[str, Path]:
    """Create sample environment YAML files for testing."""
    env_dir = temp_dir / 'environments' / 'library'
    env_dir.mkdir(parents=True, exist_ok=True)

    files = {}

    # Valid environment
    valid_env = env_dir / 'python.yaml'
    valid_env.write_text('''
name: Python Development
command-name: claude-python
dependencies:
  - uv
  - pytest
agents:
  - agents/library/python-developer.md
''')
    files['valid'] = valid_env

    # Invalid environment
    invalid_env = env_dir / 'invalid.yaml'
    invalid_env.write_text('''
name: Invalid
command-name: invalid name
''')
    files['invalid'] = invalid_env

    # Empty environment
    empty_env = env_dir / 'empty.yaml'
    empty_env.write_text('')
    files['empty'] = empty_env

    return files


@pytest.fixture
def mock_env_vars(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Mock environment variables for testing."""
    env_vars = {
        'HOME': '/home/test',
        'USERPROFILE': 'C:\\Users\\test',
        'APPDATA': 'C:\\Users\\test\\AppData\\Roaming',
        'LOCALAPPDATA': 'C:\\Users\\test\\AppData\\Local',
        'PATH': '/usr/bin:/bin',
    }

    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)

    return env_vars


@pytest.fixture
def mock_ssl_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock SSL context for testing certificate errors."""
    import ssl

    class MockSSLContext:
        def __init__(self):
            self.check_hostname = True
            self.verify_mode = ssl.CERT_REQUIRED

    def mock_create_default_context():
        return MockSSLContext()

    monkeypatch.setattr(ssl, 'create_default_context', mock_create_default_context)
