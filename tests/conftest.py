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
        'command-names': ['claude-test'],
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
        'hooks': {
            'files': [
                'hooks/test-hook.py',
                'configs/test-hook-config.yaml',
            ],
            'events': [
                {
                    'event': 'PostToolUse',
                    'matcher': 'Edit|Write',
                    'type': 'command',
                    'command': 'test-hook.py',
                    'config': 'test-hook-config.yaml',
                },
            ],
        },
        'model': 'sonnet',
        'env-variables': {'TEST_VAR': 'test_value'},
        'permissions': {
            'default-mode': 'default',
            'allow': ['mcp__test'],
        },
        'command-defaults': {
            'system-prompt': 'prompts/test-prompt.md',
            'mode': 'replace',  # Optional: 'append' or 'replace' (default: 'replace')
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
command-names:
  - "invalid name with spaces"
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
                cmd,
                0,
                commands_output.get(cmd_name, ''),
                '',
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
command-names:
  - claude-python
dependencies:
  - uv
  - pytest
agents:
  - my-agents/custom-agent.md
''')
    files['valid'] = valid_env

    # Invalid environment
    invalid_env = env_dir / 'invalid.yaml'
    invalid_env.write_text('''
name: Invalid
command-names:
  - "invalid name"
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


@pytest.fixture(autouse=True)
def _guard_real_home_writes(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent unit tests from writing to the real ~/.claude/ directory.

    Autouse safety guard that intercepts Path.open(), Path.write_text(),
    Path.write_bytes(), Path.mkdir(), and Path.unlink() to detect writes
    targeting the real user home. Tests that legitimately need real home
    access can mark themselves with @pytest.mark.allow_real_home.

    This guard does NOT apply to E2E tests (which have their own
    e2e_isolated_home fixture providing complete isolation).
    """
    # Skip for tests explicitly marked as allowing real home access
    if request.node.get_closest_marker('allow_real_home'):
        return

    # Skip for E2E tests (they have e2e_isolated_home fixture)
    if 'e2e' in str(request.fspath):
        return

    real_home = Path.home()
    real_claude_dir = real_home / '.claude'
    real_claude_json = real_home / '.claude.json'
    real_local_bin = real_home / '.local' / 'bin'

    original_open = Path.open
    original_write_text = Path.write_text
    original_write_bytes = Path.write_bytes
    original_mkdir = Path.mkdir
    original_unlink = Path.unlink

    def _check_path(path: Path, operation: str) -> None:
        """Raise if a test attempts to write under real home directories."""
        try:
            resolved = path.resolve()
        except (OSError, ValueError):
            return
        resolved_str = str(resolved)
        real_claude_resolved = str(real_claude_dir.resolve())
        real_local_bin_resolved = str(real_local_bin.resolve())
        real_claude_json_resolved = str(real_claude_json.resolve())
        protected_prefixes = (real_claude_resolved, real_local_bin_resolved)
        if resolved_str.startswith(protected_prefixes) or resolved_str == real_claude_json_resolved:
            pytest.fail(
                f'Unit test attempted {operation} to real home directory: {resolved}\n'
                f'This test is missing mocks for Path.home() or filesystem writers.\n'
                f'Add @pytest.mark.allow_real_home to override (not recommended).',
            )

    def guarded_open(self, *args, **kwargs):
        mode = args[0] if args else kwargs.get('mode', 'r')
        if isinstance(mode, str) and ('w' in mode or 'a' in mode or 'x' in mode):
            _check_path(self, f'open({mode!r})')
        return original_open(self, *args, **kwargs)

    def guarded_write_text(self, *args, **kwargs):
        _check_path(self, 'write_text()')
        return original_write_text(self, *args, **kwargs)

    def guarded_write_bytes(self, *args, **kwargs):
        _check_path(self, 'write_bytes()')
        return original_write_bytes(self, *args, **kwargs)

    def guarded_mkdir(self, *args, **kwargs):
        _check_path(self, 'mkdir()')
        return original_mkdir(self, *args, **kwargs)

    def guarded_unlink(self, *args, **kwargs):
        _check_path(self, 'unlink()')
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', guarded_open)
    monkeypatch.setattr(Path, 'write_text', guarded_write_text)
    monkeypatch.setattr(Path, 'write_bytes', guarded_write_bytes)
    monkeypatch.setattr(Path, 'mkdir', guarded_mkdir)
    monkeypatch.setattr(Path, 'unlink', guarded_unlink)


@pytest.fixture(autouse=True)
def _mock_cleanup_stale_auto_update_controls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent cleanup_stale_auto_update_controls from touching real filesystem.

    This function iterates ~/.claude/ subdirectories and writes to settings.json
    and .claude.json files. In test environments, it must be mocked to prevent
    the conftest safety guard from blocking writes to real user paths.
    """
    try:
        import setup_environment
        monkeypatch.setattr(
            setup_environment,
            'cleanup_stale_auto_update_controls',
            lambda **_kwargs: None,
        )
    except (ImportError, AttributeError):
        pass  # Not all test modules import setup_environment
