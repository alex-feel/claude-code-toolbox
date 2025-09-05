# Claude Code Environment Configurations

This directory contains YAML configuration files that define complete development environments for Claude Code. Each configuration can install dependencies, configure agents, set up MCP servers, add slash commands, and more.

## ⚠️ Security Notice

Environment configurations can execute commands and download scripts. **Only use configurations from trusted sources!**

Configurations can contain:
- **API keys and secrets** for MCP servers
- **System commands** executed during installation
- **Hook scripts** that run automatically on Claude Code events
- **Remote dependencies** downloaded from the internet

## Configuration Sources

The setup script supports three types of configuration sources:

### 1. Repository Configurations (Trusted)
Pre-defined configurations from this repository:
```powershell
# Windows
$env:CLAUDE_ENV_CONFIG='python'
iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')

# Linux/macOS
CLAUDE_ENV_CONFIG=python curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash
```

### 2. Local Files (Your Control)
Use your own configuration files with sensitive data:
```powershell
# Windows - relative path
$env:CLAUDE_ENV_CONFIG='./my-config.yaml'
iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')

# Windows - absolute path
$env:CLAUDE_ENV_CONFIG='C:/projects/configs/team-env.yaml'
iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')

# Linux/macOS
CLAUDE_ENV_CONFIG=./my-config.yaml curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash
```

### 3. Remote URLs (⚠️ Verify Source!)
Load configurations from any web server:
```powershell
# Windows
$env:CLAUDE_ENV_CONFIG='https://example.com/my-env.yaml'
iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')

# Linux/macOS
CLAUDE_ENV_CONFIG=https://example.com/my-env.yaml curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash
```

**⚠️ WARNING:** The script will display a warning when loading from URLs. Review the configuration carefully!

## Private Repository Support

The setup script supports loading configurations from private GitLab and GitHub repositories with authentication.

### Authentication Methods (in order of precedence)

1. **Command-line parameter** (highest priority)
2. **Environment variables**
3. **Interactive prompt** (fallback)

### GitLab Private Repositories

```powershell
# Windows - Using environment variable
$env:GITLAB_TOKEN='glpat-YOUR_TOKEN_HERE'
$env:CLAUDE_ENV_CONFIG='https://gitlab.company.com/api/v4/projects/123/repository/files/config.yaml/raw?ref=main'
iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')

# Windows - Using --auth parameter
python scripts/setup_environment.py "https://gitlab.company.com/api/v4/projects/123/repository/files/config.yaml/raw?ref=main" --auth "glpat-YOUR_TOKEN_HERE"

# Linux/macOS - Using environment variable
export GITLAB_TOKEN='glpat-YOUR_TOKEN_HERE'
CLAUDE_ENV_CONFIG='https://gitlab.company.com/api/v4/projects/123/repository/files/config.yaml/raw?ref=main' \
  curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash
```

### GitHub Private Repositories

```powershell
# Windows - Using environment variable
$env:GITHUB_TOKEN='ghp_YOUR_TOKEN_HERE'
$env:CLAUDE_ENV_CONFIG='https://api.github.com/repos/owner/repo/contents/config.yaml'
iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')

# Windows - Using --auth parameter
python scripts/setup_environment.py "https://api.github.com/repos/owner/repo/contents/config.yaml" --auth "ghp_YOUR_TOKEN_HERE"

# Linux/macOS - Using environment variable
export GITHUB_TOKEN='ghp_YOUR_TOKEN_HERE'
CLAUDE_ENV_CONFIG='https://api.github.com/repos/owner/repo/contents/config.yaml' \
  curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash
```

### Generic Token Support

You can also use `REPO_TOKEN` as a generic environment variable that works for both GitLab and GitHub:

```powershell
# Windows
$env:REPO_TOKEN='your-token-here'

# Linux/macOS
export REPO_TOKEN='your-token-here'
```

### One-liner with Authentication

```powershell
# Windows PowerShell - GitLab with token
powershell -NoProfile -ExecutionPolicy Bypass -Command "`$env:CLAUDE_ENV_CONFIG='https://gitlab.company.com/api/v4/projects/123/repository/files/config.yaml/raw?ref=main'; `$env:GITLAB_TOKEN='glpat-xxx'; iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')"

# Linux/macOS - GitHub with token
GITHUB_TOKEN='ghp_xxx' CLAUDE_ENV_CONFIG='https://api.github.com/repos/owner/repo/contents/config.yaml' curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash
```

### Authentication Notes

- The script tries to access public repositories first, only using authentication if needed (401/403 errors)
- Tokens are never stored or logged by the setup script
- For CI/CD pipelines, use environment variables rather than --auth parameter
- Interactive prompt is only available when running in a terminal (not in CI/CD)

## Quick Start Examples

### Windows (PowerShell)

```powershell
# Repository config (recommended for standard setups)
$env:CLAUDE_ENV_CONFIG='python'
iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')

# Local config with API keys (for team/personal setups)
$env:CLAUDE_ENV_CONFIG='./team-config.yaml'
iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')

# One-liner for any shell
powershell -NoProfile -ExecutionPolicy Bypass -Command "`$env:CLAUDE_ENV_CONFIG='python'; iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')"
```

### macOS/Linux

```bash
# Repository config
CLAUDE_ENV_CONFIG=python curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash

# Local config
CLAUDE_ENV_CONFIG=./my-env.yaml curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash

# Remote URL (verify source first!)
CLAUDE_ENV_CONFIG=https://trusted-site.com/config.yaml curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash
```

## Available Configurations

### python.yaml
**Command:** `claude-python`

A Python development environment with:
- 7 Python-optimized subagents (code review, testing, docs, etc.)
- 6 slash commands (/commit, /debug, /test, etc.)
- Context7 MCP server for library documentation
- Python developer system prompt

### Additional Configurations

More environment configurations are coming soon. You can create your own by following the structure below.

## Configuration Structure

Each YAML file can contain:

```yaml
name: Display name for the environment
command-name: The global command to register (e.g., claude-python)

dependencies:
    - Command to install dependency 1
    - Command to install dependency 2

agents:
    - Path to agent file relative to repo root

mcp-servers:
    - name: Server name
      scope: user/project
      transport: http/sse/stdio
      url: Server URL (for http/sse)
      command: Command to run (for stdio)
      header: Optional header (for http/sse)
      env: Optional environment variable (for stdio)

slash-commands:
    - Path to slash command file

output-styles:
    - Path to output style file

hooks:
    files:
        - List of hook script files to download
    events:
        - event: Event name (PostToolUse, Notification, etc.)
          matcher: Regex pattern to match
          type: Hook type (command)
          command: Command to execute

model: opus

env-variables:
    BASH_DEFAULT_TIMEOUT_MS: "5000"
    MAX_MCP_OUTPUT_TOKENS: "50000"

permissions:
    defaultMode: acceptEdits
    allow:
        - WebFetch
        - mcp__context7
        - Bash(git diff:*)
    deny:
        - Bash(rm:*)
        - Read(.env)
    ask:
        - Bash(git push:*)
    additionalDirectories:
        - ../other-project/

command-defaults:
    output-style: Name of output style to use (optional)
    system-prompt: Path to additional system prompt file (optional)
```

### Model Configuration

**Available model aliases:**
- `default` - Recommended model based on your account
- `sonnet` - Latest Sonnet model for daily coding tasks
- `opus` - Most capable Opus model for complex reasoning
- `haiku` - Fast and efficient model for simple tasks
- `sonnet[1m]` - Sonnet with 1 million token context window
- `opusplan` - Hybrid mode (Opus for planning, Sonnet for execution)

You can also specify custom model names like `claude-opus-4-1-20250805`.

### Permissions Configuration

Controls how Claude Code interacts with your system:

**Permission Modes:**
- `default` - Prompts for permission on first use of each tool
- `acceptEdits` - Automatically accepts file edit permissions
- `plan` - Plan Mode - analyze without modifying files
- `bypassPermissions` - Skips all permission prompts (use with caution)

**Permission Rules:**
- `allow` - Explicitly allowed actions
- `deny` - Prohibited actions
- `ask` - Actions requiring user confirmation
- `additionalDirectories` - Extra directories Claude can access

**Smart MCP Server Auto-Allow:**
MCP servers are automatically added to the allow list UNLESS they're explicitly mentioned in deny/ask lists. This reduces friction while respecting your security preferences.

### URL Support in Configurations

Environment configurations support flexible URL resolution for all file resources (agents, slash commands, output styles, hooks, and system prompts). This allows you to:
- Load configurations from one repository while fetching resources from others
- Mix resources from multiple sources in a single configuration
- Override the default resource location with custom URLs

**Priority order for resource resolution:**

1. **Full URLs** (highest priority) - Resources specified as full URLs are used as-is
2. **base-url override** - If `base-url` is set in the config, all relative paths use it
3. **Config source derivation** - If loading config from a URL, resources inherit that base
4. **Default repository** - Falls back to the main claude-code-toolbox repository

**Examples:**

```yaml
# Option 1: Use base-url to override default source for all resources
# Note: {path} is optional - it's automatically added if not present
base-url: https://raw.githubusercontent.com/my-org/my-configs/main
# Or explicitly with {path} for custom placement:
# base-url: https://my-server.com/v2/{path}/latest

agents:
    - agents/my-agent.md  # Uses base-url
    - https://example.com/special-agent.md  # Full URL takes priority

# Option 2: Mix resources from different sources
agents:
    - agents/examples/code-reviewer.md  # Uses default or derived base
    - https://gitlab.company.com/api/v4/projects/123/repository/files/agents%2Fcustom.md/raw?ref=main

# Option 3: Load config from URL - resources inherit that base automatically
# If you load config from https://example.com/configs/env.yaml
# Then agents/my-agent.md resolves to https://example.com/agents/my-agent.md
```

**Authentication:** When fetching from private repositories, the same authentication (environment variables or --auth parameter) is used for all resources, regardless of their source.

## Creating Custom Configurations

### For Repository (Public)

1. Create a new YAML file in `environments/examples/`
2. Define your environment using the structure above
3. **Do NOT include sensitive data like API keys**
4. Run the setup script with your configuration name
5. Your custom command will be registered globally

### For Local Use (Private)

Create a local YAML file for configurations with sensitive data:

```yaml
# my-team-env.yaml
name: Team Development Environment
command-name: claude-team

dependencies:
    - uv tool install ruff@latest

agents:
    - agents/examples/code-reviewer.md
    - agents/examples/test-generator.md

# MCP servers with API keys (keep these private!)
mcp-servers:
    - name: my-api-server
      scope: user
      transport: http
      url: https://api.mycompany.com/mcp
      header: X-API-Key: sk-abc123xyz789...  # SENSITIVE - DO NOT COMMIT!

    - name: database-tools
      scope: user
      transport: sse
      url: https://db.internal.com/mcp
      header: Authorization: Bearer eyJhbGc...  # SENSITIVE!

slash-commands:
    - slash-commands/examples/commit.md
    - slash-commands/examples/test.md

hooks:
    files:
        - hooks/examples/python_ruff_lint.py
    events:
        - event: PostToolUse
          matcher: Edit|MultiEdit|Write
          type: command
          command: python_ruff_lint.py
```

Then use it:
```powershell
# Windows
$env:CLAUDE_ENV_CONFIG='./my-team-env.yaml'
iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')

# Linux/macOS
CLAUDE_ENV_CONFIG=./my-team-env.yaml curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash
```

**Security Best Practices:**
- Store local configs in a secure location
- Add `*.local.yaml` or `*-private.yaml` to `.gitignore`
- Never commit files containing API keys or secrets
- Use environment variables for extra sensitive data
- Share config templates without actual keys

## Features

### Dependencies
Install any command-line tools or packages needed for your environment.

### Agents
Include specialized subagents for different tasks (code review, testing, documentation, etc.).

### MCP Servers
Configure Model Context Protocol servers with different transport types:
- **HTTP/SSE**: Web-based servers with optional authentication
- **Stdio**: Local command-based servers (like npx packages)

### Slash Commands
Add custom slash commands for common tasks like `/commit`, `/test`, `/refactor`.

### Output Styles
Configure how Claude formats its responses.

### Hooks
Set up automatic actions triggered by events:
- Linting on file changes
- Notifications for long-running tasks
- Custom scripts for specific file types

### Command Defaults
Configure how Claude starts in your environment:
- **output-style**: Use a complete alternative system prompt (e.g., for non-development roles like business analysis)
- **system-prompt**: Append additional context to Claude's default development prompt

Choose one or the other:
- Use `output-style` when you need a completely different persona (replaces entire system prompt)
- Use `system-prompt` when you want to enhance Claude's development capabilities with domain-specific knowledge

## Notes

- Configurations are downloaded from the repo at setup time
- All files are placed in `~/.claude/` directory
- Settings are merged with existing Claude Code configuration
- Files are automatically overwritten by default (to preserve latest versions)
- Use `--skip-install` if Claude Code is already installed
