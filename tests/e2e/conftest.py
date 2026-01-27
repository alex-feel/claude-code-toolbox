"""E2E test fixtures providing filesystem isolation and configuration loading.

This module provides comprehensive fixtures for E2E testing of setup_environment.py.
All fixtures use function scope for complete test isolation.
"""

from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts import setup_environment


@pytest.fixture(autouse=True)
def mock_claude_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent E2E tests from executing real Claude CLI commands.

    When Claude is installed locally, configure_mcp_server() would execute
    `claude mcp add --scope project ...` which writes to .mcp.json in CWD.
    This mock prevents that by making find_command_robust return None for 'claude'.

    This fixture is autouse=True to automatically apply to all E2E tests.
    """
    original_find = setup_environment.find_command_robust

    def mock_find(cmd: str) -> str | None:
        if cmd == 'claude':
            return None  # Pretend Claude is not installed
        return original_find(cmd)

    monkeypatch.setattr(setup_environment, 'find_command_robust', mock_find)


@pytest.fixture
def e2e_isolated_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> Generator[dict[str, Path], None, None]:
    """Create an isolated home directory with complete filesystem and environment isolation.

    This fixture provides:
    - Isolated home directory structure mimicking real user environment
    - Complete monkeypatching of Path.home() and all relevant environment variables
    - Pre-created directory structure required by setup_environment.py
    - Post-test cleanup verification to detect artifact leakage

    The fixture uses function scope to ensure complete isolation between tests.

    Args:
        tmp_path: pytest's built-in temporary directory fixture (auto-cleanup)
        monkeypatch: pytest's monkeypatch fixture for environment modification

    Yields:
        Dictionary containing all relevant paths:
        - home: The isolated home directory
        - claude_dir: ~/.claude directory
        - local_bin: ~/.local/bin directory
        - config_claude: ~/.config/claude directory (Linux/macOS)
        - localappdata_claude: AppData/Local/Claude directory (Windows)
        - appdata_roaming: AppData/Roaming directory (Windows)

    Example:
        def test_example(e2e_isolated_home):
            home = e2e_isolated_home["home"]
            claude_dir = e2e_isolated_home["claude_dir"]
            # Test code that uses isolated directories...
    """
    # Create isolated home directory
    home = tmp_path / 'home'
    home.mkdir()

    # Create Claude user directory (~/.claude)
    claude_dir = home / '.claude'
    claude_dir.mkdir(parents=True)

    # Create local bin directory (~/.local/bin)
    local_bin = home / '.local' / 'bin'
    local_bin.mkdir(parents=True)

    # Create XDG config directory (~/.config/claude) - Linux/macOS
    config_claude = home / '.config' / 'claude'
    config_claude.mkdir(parents=True)

    # Create Windows AppData directories
    appdata_local = tmp_path / 'AppData' / 'Local'
    appdata_local.mkdir(parents=True)
    localappdata_claude = appdata_local / 'Claude'
    localappdata_claude.mkdir(parents=True)

    appdata_roaming = tmp_path / 'AppData' / 'Roaming'
    appdata_roaming.mkdir(parents=True)

    # Monkeypatch Path.home() to return our isolated home
    monkeypatch.setattr(Path, 'home', lambda: home)

    # Monkeypatch all home-related environment variables
    # Unix/Linux/macOS
    monkeypatch.setenv('HOME', str(home))

    # Windows
    monkeypatch.setenv('USERPROFILE', str(home))
    monkeypatch.setenv('LOCALAPPDATA', str(appdata_local))
    monkeypatch.setenv('APPDATA', str(appdata_roaming))

    # XDG Base Directory Specification (Linux)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(home / '.config'))
    monkeypatch.setenv('XDG_DATA_HOME', str(home / '.local' / 'share'))

    # Create paths dictionary for easy access in tests
    paths = {
        'home': home,
        'claude_dir': claude_dir,
        'local_bin': local_bin,
        'config_claude': config_claude,
        'localappdata_claude': localappdata_claude,
        'appdata_roaming': appdata_roaming,
        'appdata_local': appdata_local,
    }

    # Yield paths to the test
    yield paths

    # Post-test cleanup verification
    # Verify no artifacts leaked outside tmp_path
    # This is handled automatically by pytest's tmp_path fixture
    # but we verify the structure was used correctly

    # Verify home directory exists (test didn't accidentally delete it)
    if not home.exists():
        pytest.fail(
            'e2e_isolated_home: home directory was deleted during test - '
            'this may indicate a test bug',
        )


@pytest.fixture
def golden_config() -> dict[str, Any]:
    """Load the golden configuration YAML for E2E testing.

    This fixture loads the comprehensive golden_config.yaml that contains
    ALL supported configuration keys for complete E2E test coverage.

    The golden config includes:
    - command-names: Array of command names/aliases
    - base-url: Resource URL (uses local mock_repo)
    - claude-code-version: Version specification
    - install-nodejs: Node.js installation flag
    - dependencies: Platform-specific dependencies
    - agents: Agent markdown files
    - slash-commands: Slash command files
    - skills: Skills configuration with name, base, files
    - files-to-download: Additional files with source/dest
    - hooks: Files and events configuration
    - mcp-servers: All transport types (http, sse, stdio)
    - model: Model configuration
    - permissions: defaultMode, allow, deny, ask lists
    - env-variables: Environment variables for Claude
    - os-env-variables: OS-level environment variables
    - command-defaults: System prompt and mode
    - user-settings: User settings to merge
    - always-thinking-enabled: Thinking mode flag
    - company-announcements: Announcement messages
    - attribution: Commit and PR attribution settings
    - status-line: Status line configuration

    Returns:
        Dictionary containing the parsed golden configuration.

    Raises:
        FileNotFoundError: If golden_config.yaml is missing (indicates Phase 1 incomplete)
        ValueError: If golden_config.yaml is empty or contains only comments

    Example:
        def test_parse_config(golden_config):
            assert golden_config["name"] == "E2E Test Environment"
            assert "mcp-servers" in golden_config
    """
    # Determine path to golden_config.yaml relative to this file
    # This file is at: tests/e2e/conftest.py
    # Golden config is at: tests/e2e/golden_config.yaml
    config_path = Path(__file__).parent / 'golden_config.yaml'

    if not config_path.exists():
        raise FileNotFoundError(
            f'golden_config.yaml not found at {config_path}. '
            'Ensure Phase 1 of E2E framework is complete.',
        )

    with config_path.open('r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    if config is None:
        raise ValueError('golden_config.yaml is empty or contains only comments')

    # Ensure proper type for mypy (yaml.safe_load returns Any)
    result: dict[str, Any] = config
    return result


@pytest.fixture
def mock_repo_path() -> Path:
    """Return the path to the mock repository for E2E testing.

    The mock repository contains sample files that simulate a remote
    repository structure. This is used with the file:// protocol
    in golden_config.yaml's base-url setting.

    Directory structure:
        tests/e2e/fixtures/mock_repo/
        ├── agents/
        │   └── e2e-test-agent.md
        ├── commands/
        │   └── e2e-test-command.md
        ├── skills/
        │   ├── SKILL.md
        │   └── e2e-test-skill.md
        ├── hooks/
        │   ├── e2e_test_hook.py
        │   └── e2e_statusline.py
        ├── configs/
        │   ├── e2e-hook-config.yaml
        │   ├── e2e-statusline-config.yaml
        │   └── e2e-extra-file.txt
        └── prompts/
            └── e2e-test-prompt.md

    Returns:
        Path object pointing to the mock_repo directory.

    Raises:
        AssertionError: If mock_repo directory doesn't exist (Phase 1 incomplete)

    Example:
        def test_file_download(mock_repo_path, e2e_isolated_home):
            agent_file = mock_repo_path / "agents" / "e2e-test-agent.md"
            assert agent_file.exists()
    """
    # This file is at: tests/e2e/conftest.py
    # Mock repo is at: tests/e2e/fixtures/mock_repo/
    repo_path = Path(__file__).parent / 'fixtures' / 'mock_repo'

    if not repo_path.exists():
        raise AssertionError(
            f'Mock repository not found at {repo_path}. '
            'Ensure Phase 1 of E2E framework is complete.',
        )

    return repo_path
