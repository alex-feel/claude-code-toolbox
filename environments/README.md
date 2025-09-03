# Claude Code Environment Configurations

This directory contains YAML configuration files that define complete development environments for Claude Code. Each configuration can install dependencies, configure agents, set up MCP servers, add slash commands, and more.

## Quick Start

### Windows (PowerShell)

#### Simplest approach (in PowerShell)
```powershell
$env:CLAUDE_ENV_CONFIG='python'
iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')
```

#### One-liner (from any shell, requires escaping)
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "`$env:CLAUDE_ENV_CONFIG='python'; iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')"
```

#### Local file (after downloading)
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/setup-environment.ps1 python
```

### macOS/Linux
```bash
# Using environment variable
CLAUDE_ENV_CONFIG=python curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash

# Or pass as argument (after downloading)
./scripts/linux/setup-environment.sh python
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
    - event: Event name (PostToolUse, Notification, etc.)
      matcher: Regex pattern to match
      type: Hook type (command)
      command: Command to execute
      files:
        - Files to download for the hook

system-prompt: Path to system prompt file
```

## Creating Custom Configurations

1. Create a new YAML file in `environments/examples/`
2. Define your environment using the structure above
3. Run the setup script with your configuration name
4. Your custom command will be registered globally

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

### System Prompts
Define the core behavior and expertise for Claude in your environment.

## Notes

- Configurations are downloaded from the repo at setup time
- All files are placed in `~/.claude/` directory
- Settings are merged with existing Claude Code configuration
- Use `--force` flag to overwrite existing files
- Use `--skip-install` if Claude Code is already installed
