# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Purpose

This is the Claude Code Toolbox - a community project providing automated installers, environment configurations, agent templates, and utilities for Claude Code across Windows, macOS, and Linux. The toolbox enables users to quickly set up specialized development environments with custom agents, MCP servers, slash commands, and hooks.

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

YAML configurations in `environments/library/` define complete development environments including:
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
uv run pytest --cov=src

# Run only unit tests
uv run pytest tests/

# Run a specific test file
uv run pytest tests/test_count_entities.py

# Run a specific test function
uv run pytest tests/unit/test_card_service.py::TestCountFiles::test_count_files_existing_directory
```

### Code Quality
```bash
# Run pre-commit hooks on all files
uv run pre-commit run --all-files

# Auto-fix linting issues, including after using Write, Edit, and MultiEdit tools and received feedback
uv run ruff check --fix
```

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

As of latest version, hooks use this structure in environment YAML:
```yaml
hooks:
    files:  # Top-level list of files to download
        - hooks/library/script.py
    events:  # Event configurations
        - event: PostToolUse
          matcher: Edit|MultiEdit|Write
          type: command
          command: script.py  # References filename from 'files'
```

### System Prompts vs Output Styles

- **system-prompt**: Appends to Claude's default development prompt (use `--append-system-prompt`)
- **output-style**: Completely replaces the system prompt (use `--output-style`)
- These are mutually exclusive in `command-defaults`

## Testing Workflows

### When modifying setup_environment.py
1. Test with repository config: `python scripts/setup_environment.py python --skip-install` (make sure latest changes are merged if structure changed)
2. Test with local file: Create test YAML, run with `./test.yaml` (prefer if structure changed)
3. Test with mock URL to verify warning messages appear
4. Verify global command registration works
5. Verify additional-settings.json structure
6. Check that hooks execute properly after setup

### When adding new environment configs
1. Place in `environments/library/`
2. Test local installation flow
3. Verify all referenced files exist in repo
4. Verify additional-settings.json structure
5. Ensure hooks trigger correctly

## File Modification Guidelines

### When editing scripts
- Must pass linting with zero warnings

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
