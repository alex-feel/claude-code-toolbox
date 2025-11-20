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
- `CLAUDE_INSTALL_METHOD` - Controls installation method: `auto` (default), `native`, or `npm`
- `CLAUDE_VERSION` - Forces specific version via npm (native installers don't support version selection)

**Benefits:**
- Resolves Node.js v25+ compatibility issues (bug #9628)
- Eliminates Node.js dependency for most users
- More reliable auto-updates via official Anthropic installers
- Maintains full backward compatibility with existing npm installations

### Environment Configuration System

YAML configurations define complete development environments including:
- Dependencies to install
- Agents (subagents for Claude Code)
- MCP servers (with automatic permission pre-allowing)
- Slash commands
- System prompts (with configurable mode: append or replace)
- Hooks (event-driven scripts)

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

### Code Quality & Linting

**CRITICAL: Always use pre-commit for code quality checks. DO NOT use `ruff format` directly.**

```bash
# Run all pre-commit hooks (this is the CORRECT way to validate code)
uv run pre-commit run --all-files

# Run specific pre-commit hooks
uv run pre-commit run ruff-check    # Linting + autofix
uv run pre-commit run mypy          # Type checking
uv run pre-commit run pyright       # Additional type checking
uv run pre-commit run shellcheck    # Shell script linting
uv run pre-commit run markdownlint  # Markdown linting
```

**Pre-commit hooks automatically handle:**
- Ruff linting with `--fix` for auto-correction
- MyPy type checking
- Pyright type checking
- JSON/YAML syntax validation
- End-of-file and trailing whitespace fixes
- Markdown and shell script linting

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
