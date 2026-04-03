"""Pytest configuration and shared fixtures for all tests."""

import json
import shutil
import sys
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
import yaml

# Known test artifact names used by the post-test leak detector.
# Maintain this set when adding new test command names to the test suite.
_KNOWN_TEST_ARTIFACT_NAMES: frozenset[str] = frozenset({
    'test-cmd', 'test-env', 'valid', 'invalid name',
})

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
    Path.write_bytes(), Path.mkdir(), Path.unlink(), and builtins.open()
    to detect writes targeting the real user home. Tests that legitimately
    need real home access can mark themselves with @pytest.mark.allow_real_home.

    Protected paths:
      - ~/.claude/ (Claude configuration directory)
      - ~/.local/bin/ (global command symlinks)
      - ~/.claude.json (global Claude config)
      - Shell config files (~/.bashrc, ~/.bash_profile, ~/.profile, ~/.zshrc,
        ~/.zprofile, ~/.config/fish/config.fish)

    This guard does NOT apply to E2E tests (which have their own
    e2e_isolated_home fixture providing complete isolation).
    """
    import builtins
    import os

    # Skip for tests explicitly marked as allowing real home access
    if request.node.get_closest_marker('allow_real_home'):
        return

    # Skip for E2E tests (they have e2e_isolated_home fixture)
    if 'e2e' in str(request.fspath):
        return

    real_home = Path.home()
    assert real_home.exists(), (
        f'Guard initialization failed: home directory {real_home} does not exist'
    )

    # Pre-resolve all protected paths once at fixture initialization (not per-call)
    real_claude_dir = real_home / '.claude'
    real_claude_json = real_home / '.claude.json'
    real_local_bin = real_home / '.local' / 'bin'

    real_claude_resolved = str(real_claude_dir.resolve())
    real_local_bin_resolved = str(real_local_bin.resolve())
    real_claude_json_resolved = str(real_claude_json.resolve())
    protected_prefixes = (real_claude_resolved, real_local_bin_resolved)

    # Shell config files to protect from accidental writes
    shell_config_paths = [
        real_home / '.bashrc',
        real_home / '.bash_profile',
        real_home / '.profile',
        real_home / '.zshrc',
        real_home / '.zprofile',
        real_home / '.config' / 'fish' / 'config.fish',
        real_home / '.config' / 'fish',
    ]
    shell_config_resolved = [str(p.resolve()) for p in shell_config_paths]

    original_path_open = Path.open
    original_write_text = Path.write_text
    original_write_bytes = Path.write_bytes
    original_mkdir = Path.mkdir
    original_unlink = Path.unlink
    original_builtin_open = builtins.open

    def _check_path(path: Path, operation: str) -> None:
        """Raise if a test attempts to write under real home directories."""
        try:
            resolved = path.resolve()
        except (OSError, ValueError):
            return
        resolved_str = str(resolved)
        if (
            resolved_str.startswith(protected_prefixes)
            or resolved_str == real_claude_json_resolved
            or any(
                resolved_str == sc or resolved_str.startswith(sc + os.sep)
                for sc in shell_config_resolved
            )
        ):
            pytest.fail(
                f'Unit test attempted {operation} to real home directory: {resolved}\n'
                f'This test is missing mocks for Path.home() or filesystem writers.\n'
                f'Add @pytest.mark.allow_real_home to override (not recommended).',
            )

    def guarded_path_open(self, *args, **kwargs):
        mode = args[0] if args else kwargs.get('mode', 'r')
        if isinstance(mode, str) and ('w' in mode or 'a' in mode or 'x' in mode):
            _check_path(self, f'Path.open({mode!r})')
        return original_path_open(self, *args, **kwargs)

    def guarded_builtin_open(file, mode='r', *args, **kwargs):
        if (
            isinstance(mode, str)
            and ('w' in mode or 'a' in mode or 'x' in mode)
            and isinstance(file, (str, Path))
        ):
            _check_path(
                Path(file) if isinstance(file, str) else file,
                f'builtins.open({mode!r})',
            )
        return original_builtin_open(file, mode, *args, **kwargs)

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

    monkeypatch.setattr(Path, 'open', guarded_path_open)
    monkeypatch.setattr(builtins, 'open', guarded_builtin_open)
    monkeypatch.setattr(Path, 'write_text', guarded_write_text)
    monkeypatch.setattr(Path, 'write_bytes', guarded_write_bytes)
    monkeypatch.setattr(Path, 'mkdir', guarded_mkdir)
    monkeypatch.setattr(Path, 'unlink', guarded_unlink)

    # Guard Fish shell subprocess (set -Ux modifies universal variables permanently)
    original_which = shutil.which

    def guarded_which(name, *args, **kwargs):
        if name == 'fish':
            return None
        return original_which(name, *args, **kwargs)

    monkeypatch.setattr(shutil, 'which', guarded_which)


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


@pytest.fixture(autouse=True)
def _mock_manifest_and_stale_marker(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent write_manifest and cleanup_stale_marker from writing to real ~/.claude/.

    These functions write manifest.json and stale.marker under ~/.claude/{cmd}/,
    which is caught by _guard_real_home_writes. Tests that need to exercise
    these functions directly should provide their own mocks.
    """
    if request.node.get_closest_marker('allow_real_home'):
        return
    if 'e2e' in str(request.fspath):
        return
    try:
        import setup_environment
        monkeypatch.setattr(setup_environment, 'write_manifest', lambda *_a, **_kw: True)
        monkeypatch.setattr(setup_environment, 'cleanup_stale_marker', lambda *_a, **_kw: None)
    except (ImportError, AttributeError):
        pass


@pytest.fixture(autouse=True)
def _guard_windows_registry_writes(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent unit tests from modifying Windows registry.

    On Windows, set_os_env_variable_windows() calls setx/reg,
    _broadcast_wm_settingchange() runs real setx/reg delete, and
    add_directory_to_windows_path() uses winreg.SetValueEx().
    This fixture mocks these at function level to avoid real registry writes.

    Tests that directly test these functions (identified by test class name)
    are excluded so they can exercise the real function with their own mocks.
    """
    if request.node.get_closest_marker('allow_real_home'):
        return
    if 'e2e' in str(request.fspath):
        return
    if sys.platform != 'win32':
        return

    # Skip for test classes that directly test the guarded functions
    _excluded_classes = {
        'TestSetOsEnvVariableWindows',
        'TestBroadcastWmSettingchange',
        'TestSetOsEnvVariableWindowsBroadcast',
        'TestAddDirectoryToWindowsPathLength',
    }
    parent = request.node.getparent(pytest.Class)
    if parent is not None and parent.name in _excluded_classes:
        return

    try:
        import setup_environment
        monkeypatch.setattr(
            setup_environment, 'set_os_env_variable_windows', lambda *_a, **_kw: True,
        )
        monkeypatch.setattr(
            setup_environment, 'add_directory_to_windows_path',
            lambda *_a, **_kw: (True, '[mock] guarded'),
        )
        monkeypatch.setattr(
            setup_environment, '_broadcast_wm_settingchange', lambda *_a, **_kw: None,
        )
    except (ImportError, AttributeError):
        pass


@pytest.fixture(autouse=True, scope='session')
def _check_leaked_artifacts():
    """Detect test artifacts leaked to real filesystem after the session completes.

    Scans ~/.local/bin/ and ~/.claude/ for files/directories matching known
    test artifact names. Emits a warning (does not fail the session) if any
    are found, enabling early detection of guard bypasses.
    """
    import warnings

    yield  # Run after all tests

    real_home = Path.home()
    leaked = []

    # Check ~/.local/bin/ for test-named files
    local_bin = real_home / '.local' / 'bin'
    if local_bin.exists():
        for item in local_bin.iterdir():
            stem = item.stem if item.suffix else item.name
            if stem in _KNOWN_TEST_ARTIFACT_NAMES:
                leaked.append(str(item))

    # Check ~/.claude/ for test-named directories
    claude_dir = real_home / '.claude'
    if claude_dir.exists():
        leaked.extend(
            str(item)
            for item in claude_dir.iterdir()
            if item.is_dir() and item.name in _KNOWN_TEST_ARTIFACT_NAMES
        )

    if leaked:
        warnings.warn(
            f'Test artifacts leaked to real filesystem ({len(leaked)} files):\n'
            + '\n'.join(f'  - {f}' for f in sorted(leaked)),
            stacklevel=1,
        )
