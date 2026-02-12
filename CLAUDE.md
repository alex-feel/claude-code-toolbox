# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Purpose

This is the Claude Code Toolbox - a community project providing automated installers and environment configuration tools for Claude Code across Windows, macOS, and Linux. The toolbox enables users to quickly set up specialized environments with custom agents, MCP servers, slash commands, and hooks.

## Key Architecture

### Two-Tier Installation System

1. **Platform-specific bootstrap scripts** (minimal ~60 lines each)
   - Windows: PowerShell scripts in `scripts/windows/`
   - Linux/macOS: Bash scripts in `scripts/linux/` and `scripts/macos/`
   - These install `uv` (Astral's Python package manager) and run Python scripts

2. **Cross-platform Python scripts** (comprehensive installers)
   - `scripts/install_claude.py`: Installs Git Bash (Windows) and Claude Code via native installers with npm fallback
   - `scripts/setup_environment.py`: Configuration-driven environment setup from YAML
   - Support three configuration sources:
     - Repository configs: `python` → downloads from repo
     - Local files: `./my-config.yaml` → loads from disk
     - Remote URLs: `https://example.com/config.yaml` → downloads from web

### Native Claude Code Installation Support

The installer uses a native-first approach with automatic npm fallback:

**Native Installation Functions:**
- `install_claude_native_windows()` - PowerShell installer for Windows
- `install_claude_native_macos()` - Shell installer for macOS
- `install_claude_native_linux()` - Shell installer for Linux
- `install_claude_native_cross_platform()` - Platform dispatcher
- `ensure_claude()` - Main orchestrator with native-first logic

**Environment Variables:**
- `CLAUDE_INSTALL_METHOD` - Controls installation method: `auto` (default), `native`, or `npm`. In `auto` mode, unknown/unrecognized installation sources are routed to native-first with npm fallback
- `CLAUDE_VERSION` - Forces specific version via npm (native installers don't support version selection)
- `CLAUDE_ALLOW_ROOT` - Allows running as root on Linux/macOS: `1` (only exact value `'1'` is accepted)

**Native Path Detection (Non-Windows):**

The `verify_claude_installation()` function classifies the Claude binary location to determine the upgrade strategy:

| Path Pattern | Detected Source | Upgrade Method |
| ------------ | --------------- | -------------- |
| Contains `npm` or `.npm-global` | `npm` | npm directly |
| Contains `.local/bin`, `/usr/local/bin`, or `.claude/bin` | `native` | Native installer |
| Any other path | `unknown` | Native-first, npm fallback |
| Not found | `none` | Fresh install |

In `auto` mode, both `native` and `unknown` sources attempt the native installer first. If native fails, npm is used as fallback. Only confirmed `npm` or `winget` sources go directly to npm.

**Benefits:**
- Resolves Node.js v25+ compatibility issues (bug #9628)
- Eliminates Node.js dependency for most users
- More reliable auto-updates via official Anthropic installers
- Maintains full backward compatibility with existing npm installations

### Root Detection Guard

All Linux and macOS scripts (both bash bootstrap scripts and Python entry points) refuse to run as root/sudo by default:

- **Detection:** Checks `id -u == 0` (shell scripts) or `os.geteuid() == 0` (Python scripts)
- **Override:** Set `CLAUDE_ALLOW_ROOT=1` to bypass the guard (only exact value `1` is accepted; `true`, `yes`, or empty strings do NOT work)
- **Scope:** Applies to all 6 entry points: `install-claude-linux.sh`, `setup-environment.sh` (both Linux and macOS), `install_claude.py`, and `setup_environment.py`
- **Rationale:** Running as root creates configuration under `/root/` instead of the regular user's home directory, causing environment setup to target the wrong user
- **When to use override:** Docker containers, CI/CD pipelines, or other legitimate root execution environments

### Environment Configuration System

YAML configurations define complete development environments including:
- Dependencies to install
- Agents (subagents for Claude Code)
- MCP servers (with automatic permission pre-allowing)
- Slash commands
- System prompts (with configurable mode: append or replace)
- Hooks (event-driven scripts)

### Platform-Conditional Tilde Expansion in Settings

The `_expand_tilde_keys_in_settings()` function handles tilde (`~`) paths differently based on the platform:

- **Windows:** Tildes are expanded to absolute paths (e.g., `~/.claude/scripts/file.py` becomes `C:\Users\user\.claude\scripts\file.py`). Windows shell does not resolve `~` in paths.
- **Linux/macOS/WSL:** Tildes are PRESERVED as-is. Claude Code resolves `~` to the correct home directory at runtime. This keeps paths portable across environments and avoids WSL HOME contamination.

**Affected settings keys** (defined in `TILDE_EXPANSION_KEYS`):

- `apiKeyHelper`
- `awsCredentialExport`

**WSL Detection:**

The `is_wsl()` utility function detects WSL by checking `/proc/version` for Microsoft/WSL indicators. When WSL is detected, the setup emits a warning if settings contain expanded Windows paths.

**Why tildes are preserved on Linux/WSL:**

On WSL, `os.path.expanduser('~')` can return a contaminated Windows home directory (e.g., `C:\Users\user`) instead of the Linux home (e.g., `/home/user`). The `normalize_tilde_path()` function uses `Path.home()` instead of `os.path.expanduser()` to avoid this contamination, but the safest approach on non-Windows platforms is to preserve tildes entirely and let the runtime resolve them.

### Cross-Shell Command Registration (Windows)

The setup creates global commands (e.g., `claude-python`) that work across all Windows shells through:
- Shared POSIX script (`~/.claude/launch-{command}.sh`) executed by Git Bash
- PowerShell wrapper (`~/.local/bin/{command}.ps1`)
- CMD wrapper (`~/.local/bin/{command}.cmd`)
- Git Bash wrapper (`~/.local/bin/{command}`)

## Development Commands

### Testing Commands
```bash
# Run all tests
uv run pytest

# Run with coverage report
uv run pytest --cov=scripts

# Run specific test files
uv run pytest tests/test_setup_environment.py
uv run pytest tests/test_install_claude.py

# Run tests matching a pattern
uv run pytest -k "test_colors"

# Run tests with verbose output
uv run pytest -v
```

### E2E Testing

The project includes a comprehensive End-to-End (E2E) testing framework that verifies the complete setup workflow on all platforms.

#### Directory Structure

```text
tests/e2e/
├── __init__.py
├── conftest.py              # E2E fixtures (isolated_home, golden_config, mock_repo_path)
├── golden_config.yaml       # Comprehensive config with ALL supported YAML keys
├── validators.py            # Composable validation functions
├── expected/                # Platform-specific expected outputs
│   ├── __init__.py
│   ├── common.py            # Shared expected values
│   ├── linux.py             # Linux expectations
│   ├── macos.py             # macOS expectations
│   └── windows.py           # Windows expectations
├── fixtures/
│   ├── __init__.py
│   └── mock_repo/           # Mock source files for testing
│       ├── configs/         # Mock YAML configurations
│       ├── hooks/           # Mock hook scripts
│       ├── agents/
│       ├── commands/
│       ├── prompts/
│       └── skills/
├── test_full_setup.py       # Main E2E workflow tests
├── test_output_files.py     # JSON file content verification
├── test_launcher_scripts.py # Platform-specific launcher tests
├── test_path_handling.py    # Tilde expansion and path format tests
├── test_path_normalization.py # Path separator consistency tests
├── test_cleanup.py          # Artifact cleanup verification
├── test_env_variable_handling.py  # OS environment variable tests
├── test_javascript_hooks.py # JavaScript hook event tests
├── test_npm_fallback.py     # npm installation and sudo fallback tests
├── test_root_guard.py       # Root detection guard tests
├── test_upgrade_source_detection.py # Source-aware upgrade routing tests
└── test_version_detection.py # Claude Code version detection tests
```

#### Running E2E Tests

```bash
# Run all E2E tests
uv run pytest tests/e2e/ -v

# Run E2E tests with detailed output
uv run pytest tests/e2e/ -v --tb=long

# Run specific E2E test module
uv run pytest tests/e2e/test_output_files.py -v

# Run E2E tests matching a pattern
uv run pytest tests/e2e/ -k "test_launcher" -v
```

#### Golden Configuration Purpose

The `tests/e2e/golden_config.yaml` is a comprehensive configuration file that includes ALL supported YAML keys. It serves as:

1. **Single source of truth** for testing - exercises every configuration option
2. **Regression prevention** - ensures all config keys work correctly on all platforms
3. **Documentation by example** - demonstrates the complete configuration schema

The golden config includes:
- Core settings: `name`, `command-names`, `base-url`, `claude-code-version`
- Dependencies: `dependencies` (with platform-specific variants)
- Resources: `agents`, `slash-commands`, `skills`, `files-to-download`
- Hooks: `hooks` (files and events with command/prompt types)
- MCP Servers: `mcp-servers` (http, sse, stdio transports)
- Settings: `model`, `permissions`, `env-variables`, `os-env-variables`
- Advanced: `command-defaults`, `user-settings`, `always-thinking-enabled`
- Extras: `company-announcements`, `attribution`, `status-line`

#### Key Design Principles

- **Complete isolation**: Tests use `tmp_path` and monkeypatched home directories
- **Function-scoped fixtures**: Each test starts with a clean state
- **Composable validators**: Return all errors, not just the first
- **Platform-specific expectations**: Separate modules for Linux, macOS, Windows
- **CI cleanup verification**: Dedicated step verifies no artifacts leak to real home

#### CI Integration

E2E tests run as a dedicated job in GitHub Actions with:
- **Platform matrix**: Ubuntu, Windows, macOS
- **Independent execution**: `fail-fast: false` - each platform runs to completion
- **Artifact upload**: Debug artifacts on failure for troubleshooting
- **Cleanup verification**: Post-test check for leaked artifacts

### Code Quality & Linting

**CRITICAL: Always use pre-commit for code quality checks. DO NOT use `ruff format` directly.**

```bash
# Run all pre-commit hooks (this is the CORRECT way to validate code)
uv run pre-commit run --all-files

# Run specific pre-commit hooks
uv run pre-commit run ruff-check       # Linting + autofix
uv run pre-commit run mypy             # Type checking
uv run pre-commit run pyright          # Additional type checking
uv run pre-commit run shellcheck       # Shell script linting
uv run pre-commit run markdownlint     # Markdown linting
uv run pre-commit run psscriptanalyzer # PowerShell linting (Windows only)
```

**Pre-commit hooks automatically handle:**
- Ruff linting with `--fix` for auto-correction
- MyPy type checking
- Pyright type checking
- PSScriptAnalyzer for PowerShell scripts (Windows)
- Shellcheck for shell scripts
- JSON/YAML syntax validation
- End-of-file and trailing whitespace fixes
- Markdown linting
- Commitizen for commit message validation

**DO NOT use these commands directly:**
- ❌ `uv run ruff format` - Not part of pre-commit configuration
- ❌ `uv run ruff check --fix` - Use pre-commit instead

**Use pre-commit for all code quality validation:**
- ✅ `uv run pre-commit run --all-files` - Correct approach

## CRITICAL: Test Suite Requirements

**ALWAYS run the full test suite after making ANY changes to the codebase:**

```bash
# Run the complete test suite
uv run pytest

# If any tests fail, they MUST be fixed before proceeding
# The codebase must maintain 100% test pass rate at all times
```

**Testing workflow after code changes:**
1. Make your code changes
2. Run `uv run pytest` to check all tests pass
3. Fix any failing tests immediately
4. Run `uv run pre-commit run --all-files` for code quality validation
5. Only commit when ALL tests pass and all pre-commit hooks pass

**IMPORTANT:**
- All tests must pass (100% pass rate)
- Use ONLY `uv run pre-commit run --all-files` for code quality checks

**Important:** Never skip the test suite. Even small changes can have unexpected impacts.

## E2E Testing Requirements for New Features

**Any new functionality MUST include E2E tests.** This is a mandatory requirement.

### When to Add E2E Tests

E2E tests are required when adding:
- New YAML configuration keys to `setup_environment.py`
- New file types or download mechanisms
- New launcher script functionality
- New MCP server transport types
- Changes to output file structures (JSON files, scripts)
- New hooks or event types

### How to Add E2E Tests for New Features

1. **Update `tests/e2e/golden_config.yaml`** - Add the new configuration key with representative test values. This file must contain ALL supported YAML keys.

2. **Update mock repository if needed** - Add mock files to `tests/e2e/fixtures/mock_repo/` for new file types.

3. **Update validators** - Add validation logic to `tests/e2e/validators.py` for new JSON structures or file content.

4. **Update expected outputs** - Modify platform-specific expectations in `tests/e2e/expected/` if the feature generates platform-dependent output.

5. **Add targeted tests** - Create or update test modules in `tests/e2e/` for specific feature validation.

### E2E Test Pattern

```python
def test_new_feature(e2e_isolated_home: dict[str, Path], golden_config: dict[str, Any]) -> None:
    """Test description."""
    # 1. Get relevant paths from fixture
    claude_dir = e2e_isolated_home['claude_dir']

    # 2. Run setup with golden config (or specific test config)
    # 3. Validate outputs using composable validators
    errors = validate_new_feature(output_path, golden_config)

    # 4. Assert no errors (fail with all errors, not just first)
    assert not errors, '\n'.join(errors)
```

### Validator Design Rules

- Return `list[str]` of errors (empty = success)
- Collect ALL errors, not just the first one
- Include context in error messages (file path, field name, expected vs actual)
- Use helper functions for reusable validation patterns

## Commit Conventions

This repository uses Conventional Commits (enforced by commitizen):
- `feat:` - New features (minor version bump)
- `fix:` - Bug fixes (patch version bump)
- `chore:` - Maintenance tasks (no version bump)
- `docs:` - Documentation improvements
- `ci:` - CI/CD changes
- `test:` - Test-related changes

Breaking changes: Add `!` after type or include `BREAKING CHANGE:` in body

## Pull Request Guidelines

### PR Title Format
- **DO NOT use Conventional Commit format in PR titles** (no `feat:`, `fix:`, etc.)
- Use clear, descriptive titles that explain the overall change
- When PR contains multiple unrelated commits, use a comprehensive title like:
  - "Update documentation and fix validation workflow"
  - "Refactor components and add badge system"
  - "Multiple improvements to environment configuration"

### Why No Conventional Commits in PR Titles
- PRs often contain multiple commits with different types
- PR titles should describe the overall change, not individual commits
- Individual commits within the PR should follow Conventional Commit format
- Release Please uses commit messages, not PR titles, for versioning

## Critical Implementation Details

### Configuration Loading Priority (setup_environment.py)

The `load_config_from_source()` function determines source by checking in order:
1. URL detection: Starts with `http://` or `https://`
2. Local file: Contains path separators (`/`, `\`) or starts with `.`
3. Repository config: Everything else (name only, `.yaml` added if missing)

For private repository access:
- GitLab: Set `GITLAB_TOKEN` environment variable with PAT (Personal Access Token)
- GitHub: Set `GITHUB_TOKEN` environment variable with PAT
- Script auto-detects GitLab/GitHub URLs and applies appropriate authentication headers

### MCP Server Permissions

When configuring MCP servers, permissions are automatically added to `additional-settings.json`:
```json
{
  "permissions": {
    "allow": ["mcp__servername"]
  }
}
```

### Environment Variables for Debugging

The setup scripts support these environment variables for debugging and customization:

- `CLAUDE_CODE_TOOLBOX_DEBUG`: Set to `1`, `true`, or `yes` to enable verbose debug logging during MCP server configuration and other operations
- `CLAUDE_CODE_GIT_BASH_PATH`: Override the Git Bash executable path (useful for non-standard installations where Git Bash is not in the default location)
- `CLAUDE_PARALLEL_WORKERS`: Override the number of concurrent download workers (default: 2)
- `CLAUDE_SEQUENTIAL_MODE`: Set to `1`, `true`, or `yes` to disable parallel downloads entirely
- `CLAUDE_ALLOW_ROOT`: Set to `1` to allow running setup scripts as root on Linux/macOS. By default, all Linux/macOS scripts refuse to run as root to prevent configuration being created under `/root/` instead of the user's home directory. The installer will request `sudo` only when needed (e.g., for npm global installs). Use this override for Docker containers, CI/CD environments, or other legitimate root use cases.

### npm Sudo Handling (Non-Interactive Mode)

When `install_claude_npm()` needs elevated permissions for global npm installs, it gates sudo attempts on TTY availability and cached credentials BEFORE attempting sudo:

1. **Interactive mode** (`sys.stdin.isatty()` is True): Sudo is attempted directly (user can enter password)
2. **Non-interactive mode** (e.g., `curl | bash`):
   - Runs `sudo -n true` to check for cached sudo credentials
   - If cached credentials exist: sudo is attempted
   - If no cached credentials: sudo is SKIPPED entirely, guidance is provided immediately
3. **Missing sudo binary**: `FileNotFoundError` is caught gracefully

This prevents the 30-second timeout waste that occurred when `curl | bash` piped installations attempted sudo without a TTY for password input.

### Download Retry Configuration

The setup scripts include robust retry logic for handling GitHub API rate limiting during file downloads:

- **Retry attempts:** 10 (with exponential backoff)
- **Initial delay:** 2 seconds, doubling each retry
- **Maximum delay cap:** 60 seconds per retry
- **Jitter:** Random 0-25% added to prevent synchronized retries
- **Stagger delay:** 0.5 second delay between launching concurrent download threads
- **Total worst-case wait:** ~6 minutes per file (covers extended rate limit windows)

### Hooks Configuration Structure

Hooks use this structure in environment YAML:
```yaml
hooks:
    files:  # Top-level list of files to download
        - my-hooks/linter.py
    events:  # Event configurations
        - event: PostToolUse
          matcher: Edit|MultiEdit|Write
          type: command
          command: linter.py  # References filename from 'files'
```

### System Prompt Configuration

The `command-defaults` section supports system prompt configuration with two modes:

```yaml
command-defaults:
  system-prompt: "prompts/my-prompt.md"  # Path to the system prompt file
  mode: "replace"  # Optional: "append" or "replace" (default: "replace")
```

**Mode Behavior:**
- **mode: "replace"** (default): Completely replaces the default system prompt using `--system-prompt` flag (added in Claude Code v2.0.14)
- **mode: "append"**: Appends to Claude's default development prompt using `--append-system-prompt` flag (added in Claude Code v1.0.55)

**Important:** If `mode` is not specified, it defaults to `"replace"` for a clean slate experience.

## Testing Workflows

### When modifying setup_environment.py
1. Test with local file: Create test YAML, run with `./test.yaml`
2. Test with remote URL to verify warning messages appear
3. Verify global command registration works
4. Verify additional-settings.json structure
5. Check that hooks execute properly after setup

### When creating custom environment configs
1. Create your YAML configuration file
2. Test local installation flow with your config
3. Verify all referenced files are accessible
4. Verify additional-settings.json structure is correct:
   - `~/.config/claude/additional-settings.json` on Linux/macOS
   - `%LOCALAPPDATA%\Claude\additional-settings.json` on Windows
5. Ensure hooks trigger correctly

## Script Dependencies

- **Python 3.12** required for all Python scripts
- **uv** (Astral's package manager) installed automatically by bootstrap scripts
- **PyYAML** and **Pydantic** installed as project dependencies
- **pytest**, **ruff**, **pre-commit** installed as dev dependencies

## Version Management

- DO NOT manually edit `CHANGELOG.md`, `version.txt`, or `.release-please-manifest.json`
- Release Please automatically manages versioning based on conventional commits
- Version bumps happen when release PRs are merged

## Security Considerations

When loading environment configurations:
- Repository configs are trusted (reviewed by maintainers)
- Local files are under user control (can contain API keys)
- Remote URLs show warning messages (verify source first)
- Never commit configurations with sensitive data to the repo

## Windows PATH Management Architecture

### Critical Implementation Details

**Platform-Specific Patterns:**

When writing Windows-specific functions that should no-op on other platforms:

```python
# CORRECT: Use positive platform check (MyPy-friendly)
def windows_specific_function() -> ReturnType:
    if sys.platform == 'win32':
        # Main Windows-specific logic here
        # ...
        return result
    # Non-Windows platforms
    return default_value

# INCORRECT: Avoid negative checks with early returns (causes MyPy "unreachable" errors in CI)
def windows_specific_function() -> ReturnType:
    if sys.platform != 'win32':
        return default_value  # MyPy on Linux CI considers code after this unreachable
    # This code becomes "unreachable" in MyPy's analysis on Linux
    try:
        # Windows logic
        pass
```

**Why this matters:** MyPy on Linux CI (GitHub Actions) performs static analysis differently than on Windows. Using `if sys.platform != 'win32':` with early returns causes MyPy to conclude that subsequent code is unreachable, even though it's reachable on Windows. Always use positive platform checks with the main logic inside the conditional block.

## MyPy Platform-Specific Behavior

**CRITICAL:** MyPy's static analysis behaves differently across platforms when analyzing platform-specific code:

- **Local Testing (Windows):** MyPy may pass locally even with negative platform checks
- **CI Testing (Linux):** MyPy on Linux uses different control flow analysis and will fail on the same code

**Best Practice:**
- Always use positive platform checks: `if sys.platform == 'win32':`
- Avoid early returns with negative checks: `if sys.platform != 'win32': return ...`
- Test with `uv run mypy scripts/` before pushing
- Expect CI to catch platform-specific analysis issues that local testing might miss

**Pattern to Follow:**
```python
# In add_directory_to_windows_path(), cleanup_temp_paths_from_registry(), etc.
if sys.platform == 'win32':
    # All Windows-specific logic inside this block
    # ...
    return windows_result
# Fallback for other platforms
return default_result
```
