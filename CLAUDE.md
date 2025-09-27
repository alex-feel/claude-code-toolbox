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
   - `scripts/install_claude.py`: Installs Git Bash, Node.js, and Claude Code
   - `scripts/setup_environment.py`: Configuration-driven environment setup from YAML
   - Support three configuration sources:
     - Repository configs: `python` → downloads from repo
     - Local files: `./my-config.yaml` → loads from disk
     - Remote URLs: `https://example.com/config.yaml` → downloads from web

### Environment Configuration System

YAML configurations define complete development environments including:
- Dependencies to install
- Agents (subagents for Claude Code)
- MCP servers (with automatic permission pre-allowing)
- Slash commands
- Output styles (complete system prompt replacements)
- System prompts (append to default prompt)
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
```bash
# Fix all linting issues (run this after making code changes)
uv run ruff check --fix

# Format Python code
uv run ruff format

# Run all pre-commit hooks
uv run pre-commit run --all-files

# Run specific pre-commit hooks
uv run pre-commit run ruff-check
uv run pre-commit run shellcheck
uv run pre-commit run markdownlint
```

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
4. Run `uv run ruff check --fix` to fix linting issues
5. Run `uv run pre-commit run --all-files` for final validation
6. Only commit when ALL tests pass and linting is clean

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

### System Prompts vs Output Styles

- **system-prompt**: Appends to Claude's default development prompt (use `--append-system-prompt`)
- **output-style**: Completely replaces the system prompt (use `--output-style`)
- These are mutually exclusive in `command-defaults`

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

- **Python 3.12+** required for all Python scripts
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
