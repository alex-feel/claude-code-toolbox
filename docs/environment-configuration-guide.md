# Environment Configuration Guide

This guide covers how to create YAML configuration files for setting up complete Claude Code environments using the Claude Code Toolbox. Environment configurations let you define custom development setups with agents, MCP servers, slash commands, hooks, skills, and more -- all installable with a single command.

The setup script handles everything automatically -- it installs Claude Code, creates the necessary directories, downloads all configured resources, and registers global commands. No prior installation is required.

**Supported platforms:** Windows, macOS, and Linux.

## Quick Start

### Minimal Configuration

A working configuration needs just a few keys:

```yaml
name: "My Environment"

command-names:
  - "my-env"

base-url: "https://raw.githubusercontent.com/my-org/my-claude-configs/main"

command-defaults:
  system-prompt: "prompts/my-prompt.md"
  mode: "append"
```

This creates a global command `my-env` that launches Claude Code with a custom system prompt appended to the default development prompt. The `base-url` tells the setup where to find resources. The `system-prompt` path `prompts/my-prompt.md` resolves to `https://raw.githubusercontent.com/my-org/my-claude-configs/main/prompts/my-prompt.md`. To use this config, host it in your repository and run the one-liner command below.

### How to Run

Run a single command that sets your configuration source and executes the setup script. The examples below show the one-liner format for each platform.

### Windows

#### Public config URL

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "`$env:CLAUDE_CODE_TOOLBOX_ENV_CONFIG='https://raw.githubusercontent.com/org/repo/main/config.yaml'; iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')"
```

#### Local file

```powershell
$env:CLAUDE_CODE_TOOLBOX_ENV_CONFIG='./my-env.yaml'
iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')
```

#### Private GitLab repository

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "`$env:CLAUDE_CODE_TOOLBOX_ENV_CONFIG='https://gitlab.company.com/namespace/project/-/raw/main/config.yaml'; `$env:GITLAB_TOKEN='glpat-<your-token>'; iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')"
```

#### Private GitHub repository

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "`$env:CLAUDE_CODE_TOOLBOX_ENV_CONFIG='https://raw.githubusercontent.com/org/repo/main/config.yaml'; `$env:GITHUB_TOKEN='ghp_<your-token>'; iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')"
```

### macOS

```bash
# Public config URL
export CLAUDE_CODE_TOOLBOX_ENV_CONFIG='https://raw.githubusercontent.com/org/repo/main/config.yaml' && curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/setup-environment.sh | bash

# Local file
export CLAUDE_CODE_TOOLBOX_ENV_CONFIG=./my-env.yaml && curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/setup-environment.sh | bash

# Private GitLab
export CLAUDE_CODE_TOOLBOX_ENV_CONFIG='https://gitlab.company.com/namespace/project/-/raw/main/config.yaml' && export GITLAB_TOKEN='glpat-<your-token>' && curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/setup-environment.sh | bash

# Private GitHub
export CLAUDE_CODE_TOOLBOX_ENV_CONFIG='https://raw.githubusercontent.com/org/repo/main/config.yaml' && export GITHUB_TOKEN='ghp_<your-token>' && curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/setup-environment.sh | bash
```

### Linux

```bash
# Public config URL
export CLAUDE_CODE_TOOLBOX_ENV_CONFIG='https://raw.githubusercontent.com/org/repo/main/config.yaml' && curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash

# Local file
export CLAUDE_CODE_TOOLBOX_ENV_CONFIG=./my-env.yaml && curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash

# Private GitLab
export CLAUDE_CODE_TOOLBOX_ENV_CONFIG='https://gitlab.company.com/namespace/project/-/raw/main/config.yaml' && export GITLAB_TOKEN='glpat-<your-token>' && curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash

# Private GitHub
export CLAUDE_CODE_TOOLBOX_ENV_CONFIG='https://raw.githubusercontent.com/org/repo/main/config.yaml' && export GITHUB_TOKEN='ghp_<your-token>' && curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash
```

> **Important:** Do not run the setup scripts as root or with `sudo`. The scripts will request elevated permissions only when needed. For Docker or CI environments, set `CLAUDE_CODE_TOOLBOX_ALLOW_ROOT=1`.

### CLI Flags

| Flag           | Purpose                                             |
|----------------|-----------------------------------------------------|
| `--yes` / `-y` | Auto-confirm installation (skip interactive prompt) |
| `--dry-run`    | Show installation plan and exit without installing  |

> **Important:** CLI flags like `--yes` and `--dry-run` cannot be passed through piped invocations (`iex (irm ...)` on Windows, `curl ... | bash` on Linux/macOS). The piped execution pattern creates no parameter binding context, so flags are silently ignored. Use environment variables instead (see [Non-interactive mode](#non-interactive-mode) and [Dry-run mode](#dry-run-mode) below).

## Ready-Made Configurations

The [claude-code-artifacts-public](https://github.com/alex-feel/claude-code-artifacts-public) repository contains ready-made environment configurations that you can use directly.

To install a configuration from that repository, use its full raw URL as the config source:

### Linux

```bash
export CLAUDE_CODE_TOOLBOX_ENV_CONFIG='https://raw.githubusercontent.com/alex-feel/claude-code-artifacts-public/main/environments/templates/basic-template.yaml' && curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash
```

### macOS

```bash
export CLAUDE_CODE_TOOLBOX_ENV_CONFIG='https://raw.githubusercontent.com/alex-feel/claude-code-artifacts-public/main/environments/templates/basic-template.yaml' && curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/setup-environment.sh | bash
```

### Windows

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "`$env:CLAUDE_CODE_TOOLBOX_ENV_CONFIG='https://raw.githubusercontent.com/alex-feel/claude-code-artifacts-public/main/environments/templates/basic-template.yaml'; iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')"
```

Browse the [repository](https://github.com/alex-feel/claude-code-artifacts-public/tree/main/environments/templates) to discover available configurations and use them as starting points for your own.

## Configuration Reference

Quick-reference table of all 26 configuration keys. Each key links to its detailed documentation in the [Configuration Keys](#configuration-keys) section below.

| YAML Key                                              | Type                   | Required | Default | Brief Description                          |
|-------------------------------------------------------|------------------------|----------|---------|--------------------------------------------|
| [`name`](#name)                                       | `str`                  | **Yes**  | --      | Display name for the environment           |
| [`version`](#version)                                 | `str`                  | No       | `None`  | Config version (semver)                    |
| [`inherit`](#inherit)                                 | `str`                  | No       | `None`  | Parent config URL/path/name                |
| [`command-names`](#command-names)                     | `list[str]`            | No*      | `[]`    | Command names and aliases                  |
| [`base-url`](#base-url)                               | `str`                  | No       | `None`  | Base URL for relative resource paths       |
| [`claude-code-version`](#claude-code-version)         | `str`                  | No       | `None`  | Specific Claude Code version or `"latest"` |
| [`install-nodejs`](#install-nodejs)                   | `bool`                 | No       | `None`  | Install Node.js LTS before dependencies    |
| [`dependencies`](#dependencies)                       | `dict`                 | No       | `{}`    | Platform-specific dependency commands      |
| [`agents`](#agents)                                   | `list[str]`            | No       | `[]`    | Agent markdown file paths                  |
| [`slash-commands`](#slash-commands)                   | `list[str]`            | No       | `[]`    | Slash command file paths                   |
| [`skills`](#skills)                                   | `list[Skill]`          | No       | `[]`    | Skill configurations                       |
| [`files-to-download`](#files-to-download)             | `list[FileToDownload]` | No       | `[]`    | Files to download during setup             |
| [`global-config`](#global-config)                     | `GlobalConfig`         | No       | `None`  | Settings for `~/.claude.json`              |
| [`hooks`](#hooks)                                     | `Hooks`                | No       | `None`  | Hook configurations (files and events)     |
| [`mcp-servers`](#mcp-servers)                         | `list[dict]`           | No       | `[]`    | MCP server configurations                  |
| [`model`](#model)                                     | `str`                  | No       | `None`  | Model alias or custom model name           |
| [`permissions`](#permissions)                         | `Permissions`          | No       | `None`  | Permission rules for tools                 |
| [`env-variables`](#env-variables)                     | `dict[str, str]`       | No       | `None`  | Claude-level environment variables         |
| [`os-env-variables`](#os-env-variables)               | `dict`                 | No       | `None`  | OS-level persistent environment variables  |
| [`command-defaults`](#command-defaults)               | `CommandDefaults`      | No*      | `None`  | System prompt and mode                     |
| [`user-settings`](#user-settings)                     | `UserSettings`         | No       | `None`  | Merged into `settings.json`                |
| [`always-thinking-enabled`](#always-thinking-enabled) | `bool`                 | No       | `None`  | Enable always-on thinking mode             |
| [`effort-level`](#effort-level)                       | `str`                  | No       | `None`  | Adaptive reasoning effort level            |
| [`company-announcements`](#company-announcements)     | `list[str]`            | No       | `None`  | Announcement strings for users             |
| [`attribution`](#attribution)                         | `Attribution`          | No       | `None`  | Commit and PR attribution strings          |
| [`status-line`](#status-line)                         | `StatusLine`           | No       | `None`  | Status line script configuration           |

> `command-names` and `command-defaults` have a co-dependency: if one is specified, the other must also be specified.

### Configuration key naming

All configuration keys use **kebab-case** (hyphenated lowercase), for example `mcp-servers`, `effort-level`, `files-to-download`. Using underscores (`effort_level`, `mcp_servers`) will cause the key to be flagged as unknown during installation.

> **Note:** The Pydantic validation model (`EnvironmentConfig`) uses `populate_by_name=True` for testing convenience, which means CI validation accepts both `effort_level` and `effort-level`. However, the runtime setup script (`setup_environment.py`) uses `config.get('effort-level')` and will not recognize underscore variants. Always use kebab-case in your configuration files.

## Configuration Keys

### Core Settings

#### `name`

Display name for the environment, shown in the setup header and summary.

- **Type:** `str` (required)
- **Example:** `name: "Python Development"`

#### `version`

Configuration version for update checking. Extracted from the root config before inheritance resolution.

- **Type:** `str | None`
- **Default:** `None`
- **Validation:** Must be valid semver (`X.Y.Z` format, with optional pre-release and build metadata)
- **Example:** `version: "1.0.0"` or `version: "2.1.0-beta.1"`

#### `command-names`

Creates global shell commands that launch Claude Code with this environment configuration. The first name is the primary command (used for file naming), and subsequent entries are aliases.

- **Type:** `list[str] | None`
- **Default:** `[]`
- **Validation:**
  - Cannot be empty or whitespace-only
  - Cannot contain spaces
  - Must be alphanumeric, hyphens, and underscores only
- **Co-dependency:** If specified, `command-defaults` must also be specified (and vice versa)
- **Note:** If empty or not specified, setup steps for hooks download, settings, manifest, launcher, and command registration are skipped. The setup still processes other resources (agents, MCP servers, dependencies, and so on) but does not create a launchable command.
- **Example:**

```yaml
command-names:
  - "my-env"       # Primary (used for file names)
  - "my-env-alias" # Alias
```

#### `base-url`

Base URL for resolving relative resource paths (agents, commands, skills, hooks, and other files).

- **Type:** `str | None`
- **Default:** `None`
- **Validation:** Must start with `http://` or `https://`
- **Example:** `base-url: "https://raw.githubusercontent.com/org/repo/main"`

#### `inherit`

URL, local path, or repository config name to inherit from. The child configuration overrides parent values at the top level (no deep merge).

- **Type:** `str | None`
- **Default:** `None`
- **Validation:** Cannot be empty, no null bytes
- **Max depth:** 10 levels
- **Circular dependency detection:** Automatic
- **Example:**

```yaml
inherit: "https://raw.githubusercontent.com/org/repo/main/base.yaml"
# or
inherit: "./base-config.yaml"
# or
inherit: "base-config"  # fetched from artifacts-public repo
```

See [Configuration Inheritance](#configuration-inheritance) for details.

### Installation Control

#### `claude-code-version`

Specific Claude Code version to install.

- **Type:** `str | None`
- **Default:** `None`
- **Special value:** `"latest"` (case-insensitive) installs the latest available version (same as the default behavior)
- **Validation:** Must be `"latest"` or valid semver (`X.Y.Z` with optional pre-release and build metadata)
- **Note:** Works with both native (via direct binary download from Google Cloud Storage) and npm installation methods. If the requested version is not found via GCS, the installer falls back to the native installer with the latest version
- **Example:** `claude-code-version: "1.0.128"` or `claude-code-version: "latest"`

#### `install-nodejs`

Install Node.js LTS before processing dependencies. Used when MCP servers or tools need Node.js but Claude Code itself was installed natively (without Node.js).

- **Type:** `bool | None`
- **Default:** `None`
- **Note:** When `true`, only checks the minimum Node.js version (>= 18.0.0), not Claude Code npm compatibility
- **Example:** `install-nodejs: true`

#### `dependencies`

Platform-specific shell commands to execute during setup.

- **Type:** `dict[str, list[str]]`
- **Default:** `{}`
- **Valid platform keys:** `common`, `windows`, `macos`, `linux`
- **Behavior:**
  - `common` runs on all platforms
  - Platform-specific keys run only on the matching platform
  - Invalid keys raise a `ValueError`
- **Example:**

```yaml
dependencies:
  common:
    - "uv tool install ruff"
    - "uv tool install mypy"
  windows:
    - "winget install --id Git.Git --scope machine --accept-package-agreements --accept-source-agreements"
  macos:
    - "brew install shellcheck"
  linux:
    - "sudo apt-get install -y shellcheck"
```

### Claude Code Resources

#### `agents`

Markdown files placed in `~/.claude/agents/` during setup. Values are URLs or relative paths resolved against the configuration source or `base-url`.

- **Type:** `list[str] | None`
- **Default:** `[]`
- **Example:**

```yaml
agents:
  - "agents/code-reviewer.md"
  - "https://example.com/agents/security-auditor.md"
```

#### `slash-commands`

Command files placed in `~/.claude/commands/` during setup. Uses the same path resolution as `agents`.

- **Type:** `list[str] | None`
- **Default:** `[]`
- **Example:**

```yaml
slash-commands:
  - "commands/review.md"
  - "commands/deploy.md"
```

#### `skills`

Skill configurations. Each skill is a set of files placed in `~/.claude/skills/{name}/`.

- **Type:** `list[Skill] | None`
- **Default:** `[]`
- **Skill fields:**
  - `name` (str, required): Skill identifier
  - `base` (str, required): Base URL or local path for skill files
  - `files` (list[str], required): List of files to download. **Must include `SKILL.md`.**
- **Example:**

```yaml
skills:
  - name: "code-review"
    base: "skills/"
    files:
      - "SKILL.md"
      - "review-checklist.md"
```

#### `files-to-download`

Arbitrary files to download during setup. Each entry specifies a source and a destination path.

- **Type:** `list[FileToDownload] | None`
- **Default:** `[]`
- **Fields:**
  - `source` (str, required): URL or path to the source file
  - `dest` (str, required): Destination path (supports `~` expansion)
- **Validation:** Paths cannot be empty or contain null bytes
- **Security:** Destinations matching sensitive path prefixes (for example, `~/.ssh/`, `~/.bashrc`) are flagged with `[!]` in the installation summary
- **Example:**

```yaml
files-to-download:
  - source: "configs/api-key-helper.py"
    dest: "~/.claude/scripts/api-key-helper.py"
```

### MCP Servers

MCP (Model Context Protocol) servers extend Claude Code with additional capabilities. The setup supports three transport types.

- **Type:** `list[dict] | None`
- **Default:** `[]`
- **Note:** Each server must have a `name` field

#### HTTP Transport

- **Required fields:** `name`, `transport: "http"`, `url`
- **Optional fields:** `scope`, `header`, `env`

```yaml
mcp-servers:
  - name: "my-api"
    transport: "http"
    url: "http://localhost:3000/api"
    header: "Authorization: Bearer ${MY_TOKEN}"
    env: "MY_TOKEN"
```

#### SSE Transport

Uses the same fields as HTTP transport with `transport: "sse"`.

```yaml
mcp-servers:
  - name: "my-events"
    transport: "sse"
    url: "http://localhost:3001/events"
    header: "X-API-Key: my-secret"
```

#### Stdio Transport

- **Required fields:** `name`, `command`
- **Optional fields:** `scope`, `env`, `args`
- **Note:** On Windows, commands starting with `npx` get automatic `cmd /c` wrapping

```yaml
mcp-servers:
  - name: "memory-server"
    command: "npx @modelcontextprotocol/server-memory"
    env:
      - "DEBUG=1"
```

#### Scope Options

Controls where the MCP server configuration is written.

- **Valid values:** `user`, `local`, `project`, `profile`
- **Default:** `user`
- **Combined scopes:** Use a list format. Combined scopes must include `profile` for meaningful combination.

```yaml
mcp-servers:
  - name: "dual-scope-server"
    scope:
      - "user"
      - "profile"
    transport: "http"
    url: "http://localhost:3000/api"
```

#### The `env` Field

Defines environment variables for the MCP server.

- **String format:** Single environment variable name
- **List format:** Multiple `KEY=VALUE` pairs

```yaml
# Single variable
env: "API_TOKEN"

# Multiple variables
env:
  - "DEBUG=1"
  - "LOG_LEVEL=debug"
```

#### The `header` Field

Sets an HTTP header for both `http` and `sse` transports.

- **Format:** `"Header-Name: value"`
- **Example:** `header: "Authorization: Bearer token123"`

#### Automatic Permission Pre-Allowing

MCP server names are automatically added to the `permissions.allow` list as `mcp__servername` in the settings file. You do not need to manually add MCP server permissions.

### Model and Reasoning

#### `model`

Model alias or custom model name for Claude Code.

- **Type:** `str | None`
- **Default:** `None`
- **Valid aliases:** `default`, `sonnet`, `opus`, `haiku`, `opus[1m]`, `sonnet[1m]`, `opusplan`
- **Custom names:** Any model name starting with `claude-` (for example, `claude-3-5-sonnet-20241022`)
- **Example:** `model: "opus"` or `model: "claude-3-5-sonnet-20241022"`

#### `always-thinking-enabled`

Enable always-on extended thinking mode.

- **Type:** `bool | None`
- **Default:** `None`
- **Example:** `always-thinking-enabled: true`

#### `effort-level`

Controls adaptive reasoning effort.

- **Type:** `str | None` (one of `low`, `medium`, `high`, `max`)
- **Default:** `None`
- **Values:**
  - `low` -- Minimal reasoning, fastest responses
  - `medium` -- Balanced reasoning and speed
  - `high` -- Thorough reasoning for complex tasks
  - `max` -- Maximum reasoning effort. **Requires the model to be set to an Opus variant** (the model name must contain `opus`, case-insensitive)
- **Example:**

```yaml
# max requires Opus
model: "opus"
effort-level: "max"
```

```yaml
# high works with any model
effort-level: "high"
```

### Permissions

Permission rules controlling which tools and actions are allowed, denied, or require confirmation.

- **Type:** `Permissions | None`
- **Default:** `None`
- **Fields:**
  - `defaultMode` -- One of `default`, `acceptEdits`, `plan`, `bypassPermissions`
  - `allow` -- List of explicitly allowed actions
  - `deny` -- List of explicitly denied actions
  - `ask` -- List of actions requiring confirmation
  - `additionalDirectories` -- List of additional directory paths
- **Note:** MCP server permissions (for example, `mcp__servername`) are automatically merged into the `allow` list
- **Example:**

```yaml
permissions:
  defaultMode: "default"
  allow:
    - "Read"
    - "Glob"
    - "Grep"
  deny:
    - "Bash(rm -rf)"
  ask:
    - "Edit"
    - "Write"
  additionalDirectories:
    - "/opt/project-data"
```

### Environment Variables

#### `env-variables`

Claude-level environment variables set in the settings file. These are available within Claude Code sessions only.

- **Type:** `dict[str, str] | None`
- **Default:** `None`
- **Example:**

```yaml
env-variables:
  API_KEY: "sk-..."
  DATABASE_URL: "postgres://localhost/mydb"
```

#### `os-env-variables`

OS-level persistent environment variables written to the shell profile (Linux/macOS) or Windows registry.

- **Type:** `dict[str, str | None] | None`
- **Default:** `None`
- **Special value:** Set a value to `null` to delete an existing variable
- **Validation:** Variable names must match `^[A-Za-z_][A-Za-z0-9_]*$`
- **Example:**

```yaml
os-env-variables:
  MY_TOOL_PATH: "/opt/my-tool/bin"
  OLD_UNUSED_VAR: null  # Deletes this variable
```

### User Interface

#### `command-defaults`

System prompt configuration for the environment command.

- **Type:** `CommandDefaults | None`
- **Default:** `None`
- **Fields:**
  - `system-prompt` (str) -- Path to the system prompt file (downloaded to `~/.claude/prompts/`)
  - `mode` (str, default: `"replace"`) -- How the prompt is applied:
    - `replace` -- Completely replaces the default system prompt (`--system-prompt` flag, added in Claude Code v2.0.14)
    - `append` -- Appends to Claude's default development prompt (`--append-system-prompt` flag, added in Claude Code v1.0.55)
- **Co-dependency:** If specified, `command-names` must also be specified (and vice versa)
- **Example:**

```yaml
base-url: "https://raw.githubusercontent.com/my-org/my-configs/main"

command-defaults:
  system-prompt: "prompts/my-prompt.md"
  mode: "append"
```

#### `user-settings`

Free-form settings merged into `~/.claude/settings.json`. Uses deep merge with array union for `permissions.allow`, `permissions.deny`, and `permissions.ask`.

- **Type:** `UserSettings | None`
- **Default:** `None`
- **Excluded keys:** `hooks` and `statusLine` (these are profile-specific and must be configured at the root level of the YAML configuration)
- **Example:**

```yaml
user-settings:
  language: "english"
  theme: "dark"
  apiKeyHelper: "uv run --no-project --python 3.12 ~/.claude/scripts/api-key-helper.py"
```

#### `global-config`

Settings merged into `~/.claude.json` (the Claude Code global configuration file). Uses deep merge with no array union (arrays are replaced, not merged).

- **Type:** `GlobalConfig | None`
- **Default:** `None`
- **Excluded keys:** `oauthSession` and `oauthAccount` (OAuth credentials must not appear in YAML configuration files)
- **Example:**

```yaml
global-config:
  autoConnectIde: true
  editorMode: "vim"
  showTurnDuration: true
```

#### `company-announcements`

Announcement strings displayed to users during setup.

- **Type:** `list[str] | None`
- **Default:** `None`
- **Example:**

```yaml
company-announcements:
  - "Welcome to the team development environment!"
  - "Run /help for available commands"
```

#### `attribution`

Attribution strings for commits and pull requests. Set a field to an empty string to hide attribution.

- **Type:** `Attribution | None`
- **Default:** `None`
- **Fields:**
  - `commit` (str) -- Attribution string for commits
  - `pr` (str) -- Attribution string for pull requests
- **Example:**

```yaml
attribution:
  commit: "Co-authored-by: AI Assistant"
  pr: ""  # Hide PR attribution
```

#### `status-line`

Status line script configuration. The script file and optional config file are downloaded to `~/.claude/hooks/`.

- **Type:** `StatusLine | None`
- **Default:** `None`
- **Fields:**
  - `file` (str, required) -- Script file path
  - `padding` (int, optional) -- Padding value
  - `config` (str, optional) -- Config file (appended as command argument)
- **Note:** Both `file` and `config` (if specified) must exist in `hooks.files`. If `status-line` is configured, the `hooks` key must also be present.
- **Example:**

```yaml
status-line:
  file: "hooks/statusline.py"
  config: "configs/statusline-config.yaml"
  padding: 0
```

### Hooks

Event-driven scripts that run automatically during Claude Code sessions.

- **Type:** `Hooks | None`
- **Default:** `None`
- **Fields:**
  - `files` (list[str]) -- Script files to download to `~/.claude/hooks/`
  - `events` (list[HookEvent]) -- Event configurations

#### Hook Event Fields

| Field     | Type  | Required          | Description                                                           |
|-----------|-------|-------------------|-----------------------------------------------------------------------|
| `event`   | `str` | Yes               | Event name (for example, `PreToolUse`, `PostToolUse`, `Notification`) |
| `matcher` | `str` | No                | Regex pattern for matching (default: `""`)                            |
| `type`    | `str` | No                | Hook type: `command` or `prompt` (default: `command`)                 |
| `command` | `str` | For command hooks | Script filename (must exist in `hooks.files`)                         |
| `config`  | `str` | No                | Config file reference (must exist in `hooks.files`)                   |
| `prompt`  | `str` | For prompt hooks  | Prompt text for LLM evaluation                                        |
| `timeout` | `int` | No                | Timeout in seconds (default: 30, prompt hooks only)                   |

#### Command Hooks

Execute a script file when the event fires. The `command` field must reference a filename listed in `hooks.files`.

```yaml
hooks:
  files:
    - "hooks/linter.py"
    - "configs/linter-config.yaml"
  events:
    - event: "PostToolUse"
      matcher: "Edit|MultiEdit|Write"
      type: "command"
      command: "linter.py"
      config: "linter-config.yaml"
```

#### Prompt Hooks

Send a prompt to the LLM for evaluation when the event fires. The `command` and `config` fields are not allowed for prompt hooks.

```yaml
hooks:
  files:
    - "hooks/linter.py"
  events:
    - event: "PreToolUse"
      matcher: "Bash"
      type: "prompt"
      prompt: "Check if this bash command is safe to execute"
      timeout: 30
```

#### File Consistency Rules

The setup validates hook file references:

1. Every file listed in `hooks.files` must be used by at least one event or the `status-line` configuration
2. Every `command` in hook events must exist in `hooks.files`
3. Every `config` in hook events must exist in `hooks.files`
4. If `status-line` is configured, its `file` and `config` must exist in `hooks.files`
5. If `status-line` is configured but `hooks` is not defined, that is an error

#### Supported Script Types

- Python: `.py`
- JavaScript: `.js`, `.mjs`, `.cjs`

#### Complete Hooks Example

```yaml
hooks:
  files:
    - "hooks/linter.py"
    - "hooks/security-check.js"
    - "configs/linter-config.yaml"
  events:
    - event: "PostToolUse"
      matcher: "Edit|MultiEdit|Write"
      type: "command"
      command: "linter.py"
      config: "linter-config.yaml"
    - event: "PreToolUse"
      matcher: "Bash"
      type: "prompt"
      prompt: "Check if this bash command is safe to execute"
      timeout: 30
```

## Advanced Topics

### Configuration Inheritance

The `inherit` key allows a configuration to extend a parent configuration.

#### How Inheritance Works

- Child values completely **replace** parent values for the same top-level key (no deep merge)
- Maximum inheritance depth is 10 levels
- Circular dependencies are detected automatically
- The `version` key is extracted from the root config **before** inheritance resolution
- The `inherit` key is stripped from the final merged configuration

#### Inheritance Path Resolution

The `inherit` value uses the same routing as config sources:

- **URL:** Starts with `http://` or `https://` -- fetched directly
- **Local path:** Contains path separators or starts with `.` -- loaded from disk
- **Repository name:** Everything else -- fetched from the artifacts-public repository

#### Example

```yaml
# base.yaml
name: "Base Environment"
model: "sonnet"
agents:
  - "agents/core-agent.md"
```

```yaml
# child.yaml
inherit: "base.yaml"
name: "Extended Environment"  # Overrides parent's name
agents:                       # Completely REPLACES parent's agents list
  - "agents/core-agent.md"
  - "agents/extra-agent.md"
effort-level: "high"          # Added (not in parent)
# model: "sonnet" is inherited from parent (not overridden)
```

### Authentication for Private Repositories

When using configurations from private repositories, you need to provide authentication credentials.

#### Auth Precedence

Authentication is resolved in this order (highest priority first):

1. **CLI `--auth` parameter** -- Format: `"header:value"`, `"header=value"`, or plain token
2. **URL-specific environment variables** -- `GITLAB_TOKEN` for GitLab URLs, `GITHUB_TOKEN` for GitHub URLs
3. **Generic token** -- `REPO_TOKEN` environment variable (auto-detects repository type)
4. **Interactive prompt** -- If a terminal is available and the repository type is detected

#### Variable Scopes

| Variable                       | Scope                                 | Description                                     |
|--------------------------------|---------------------------------------|-------------------------------------------------|
| `GITHUB_TOKEN`                 | Python-level (auto-detected from URL) | GitHub PAT with `repo` scope                    |
| `GITLAB_TOKEN`                 | Python-level (auto-detected from URL) | GitLab PAT with `read_repository` scope         |
| `REPO_TOKEN`                   | Shell-level (passed as `--auth`)      | Generic token, auto-detects repo type           |
| `CLAUDE_CODE_TOOLBOX_ENV_AUTH` | Shell-level (passed as `--auth`)      | Custom header format: `Header-Name:token-value` |

#### URL Handling

- GitLab web URLs (`/-/raw/`) are automatically converted to API format
- GitHub raw URLs are automatically converted to API URLs
- Public access is attempted first; authentication is applied only on 401/403/404 responses

### Configuration Sources

The setup script determines the configuration source by checking in this order:

1. **URL:** Starts with `http://` or `https://` -- fetched directly from the web
2. **Local file:** Contains path separators (`/`, `\`), starts with `./` or `../`, is an absolute path, or the file exists on disk -- loaded from the local filesystem
3. **Repository config:** Everything else -- `.yaml` is added if missing, then fetched from `https://raw.githubusercontent.com/alex-feel/claude-code-artifacts-public/main/{name}.yaml`

### Cross-Shell Command Registration (Windows)

On Windows, the setup creates global commands that work across all shells (PowerShell, CMD, Git Bash) through a set of wrapper scripts:

- Shared POSIX script (`~/.claude/launch-{command}.sh`) executed by Git Bash
- PowerShell wrapper (`~/.local/bin/{command}.ps1`)
- CMD wrapper (`~/.local/bin/{command}.cmd`)
- Git Bash wrapper (`~/.local/bin/{command}`)

For the full technical architecture, see [Cross-Shell Launcher Architecture](cross-shell-launcher-architecture.md).

## What Happens When You Run Setup

Here is a conceptual overview of what the setup script does when you run it with a configuration:

1. **Install Claude Code** -- Uses the native installer with npm fallback. Skipped with `--skip-install`.
2. **Create directories** -- Creates `~/.claude/agents/`, `commands/`, `prompts/`, `hooks/`, and `skills/` directories.
3. **Download custom files** -- Processes `files-to-download` entries.
4. **Install Node.js** -- If `install-nodejs: true` is set in the config.
5. **Install dependencies** -- Runs platform-specific dependency commands.
6. **Set OS environment variables** -- Writes persistent environment variables from `os-env-variables`.
7. **Process agents** -- Downloads agent markdown files to `~/.claude/agents/`.
8. **Process slash commands** -- Downloads command files to `~/.claude/commands/`.
9. **Process skills** -- Downloads skill file sets to `~/.claude/skills/{name}/`.
10. **Process system prompt** -- Downloads the prompt file if configured.
11. **Configure MCP servers** -- Sets up MCP servers with scope-based routing.
12. **Write user settings** -- Merges `user-settings` into `~/.claude/settings.json`.
13. **Write global config** -- Merges `global-config` into `~/.claude.json`.
14. **Download hooks** -- Downloads hook script files. (Only if `command-names` is specified.)
15. **Configure settings** -- Creates the settings file for the command.
16. **Write manifest** -- Creates an installation tracking manifest.
17. **Create launcher** -- Creates the launcher script for the command.
18. **Register commands** -- Creates global command wrappers.

Steps 14 through 18 are skipped if `command-names` is not specified.

## Complete Annotated Example

A realistic configuration demonstrating most keys:

```yaml
# Python Development Environment Configuration
name: "Python Development"
version: "1.0.0"

command-names:
  - "claude-python"   # Primary command name
  - "pydev"           # Alias

base-url: "https://raw.githubusercontent.com/myorg/my-configs/main"

# Install Node.js for MCP servers that need npx
install-nodejs: true

# Platform-specific dependencies
dependencies:
  common:
    - "uv tool install ruff"
    - "uv tool install mypy"
  windows:
    - "winget install --id Git.Git --scope machine --accept-package-agreements --accept-source-agreements"
  macos:
    - "brew install shellcheck"
  linux:
    - "sudo apt-get install -y shellcheck"

# Agent for code review
agents:
  - "agents/python-reviewer.md"

# Custom slash commands
slash-commands:
  - "commands/lint.md"
  - "commands/test.md"

# Skills
skills:
  - name: "python-best-practices"
    base: "skills/"
    files:
      - "SKILL.md"
      - "python-patterns.md"

# MCP servers
mcp-servers:
  - name: "context-server"
    transport: "http"
    url: "http://localhost:8000/mcp"
    scope: "user"
  - name: "code-search"
    command: "npx @example/code-search-mcp"
    scope: "profile"

# Use Opus model with maximum effort
model: "opus"
effort-level: "max"
always-thinking-enabled: true

# Permissions
permissions:
  defaultMode: "default"
  allow:
    - "Read"
    - "Glob"
    - "Grep"
  deny:
    - "Bash(rm -rf)"

# Claude-level environment variables
env-variables:
  PROJECT_TYPE: "python"
  COVERAGE_THRESHOLD: "80"

# OS-level persistent environment variables
os-env-variables:
  PYTHONDONTWRITEBYTECODE: "1"

# System prompt
command-defaults:
  system-prompt: "prompts/python-system-prompt.md"
  mode: "append"

# User settings
user-settings:
  language: "english"

# Global config
global-config:
  autoConnectIde: true
  showTurnDuration: true

# Company announcements
company-announcements:
  - "Welcome to the Python development environment!"
  - "Run /lint to check your code"

# Attribution
attribution:
  commit: "Co-authored-by: Claude AI"
  pr: ""  # Hide PR attribution

# Hooks for code quality
hooks:
  files:
    - "hooks/python-linter.py"
    - "configs/linter-config.yaml"
  events:
    - event: "PostToolUse"
      matcher: "Edit|MultiEdit|Write"
      type: "command"
      command: "python-linter.py"
      config: "linter-config.yaml"
```

## Environment Variables Reference

### Configuration

| Variable                         | Purpose                                   | Example                              |
|----------------------------------|-------------------------------------------|--------------------------------------|
| `CLAUDE_CODE_TOOLBOX_ENV_CONFIG` | Configuration source (URL, path, or name) | `python`, `./my.yaml`, `https://...` |

### Debugging and Behavior

| Variable                               | Purpose                                     | Accepted Values       |
|----------------------------------------|---------------------------------------------|-----------------------|
| `CLAUDE_CODE_TOOLBOX_DEBUG`            | Enable verbose debug logging                | `1`, `true`, or `yes` |
| `CLAUDE_CODE_TOOLBOX_PARALLEL_WORKERS` | Override concurrent download workers        | Integer (default: 2)  |
| `CLAUDE_CODE_TOOLBOX_SEQUENTIAL_MODE`  | Disable parallel downloads                  | `1`, `true`, or `yes` |
| `CLAUDE_CODE_TOOLBOX_ALLOW_ROOT`       | Allow running as root on Linux/macOS        | Exact value `1` only  |
| `CLAUDE_CODE_TOOLBOX_CONFIRM_INSTALL`  | Auto-confirm installation                   | Exact value `1` only  |
| `CLAUDE_CODE_TOOLBOX_DRY_RUN`          | Preview installation plan without changes   | Exact value `1` only  |
| `CLAUDE_CODE_TOOLBOX_GIT_BASH_PATH`    | Override Git Bash executable path (Windows) | Path to `bash.exe`    |

### Authentication

| Variable                       | Scope                                 | Purpose                                  |
|--------------------------------|---------------------------------------|------------------------------------------|
| `GITHUB_TOKEN`                 | Python-level (auto-detected from URL) | GitHub PAT with `repo` scope             |
| `GITLAB_TOKEN`                 | Python-level (auto-detected from URL) | GitLab PAT with `read_repository` scope  |
| `REPO_TOKEN`                   | Shell-level (passed as `--auth`)      | Generic token, auto-detects repo type    |
| `CLAUDE_CODE_TOOLBOX_ENV_AUTH` | Shell-level (passed as `--auth`)      | Custom header: `Header-Name:token-value` |

### CLI Flags

| Flag             | Purpose                                                 |
|------------------|---------------------------------------------------------|
| `--yes` / `-y`   | Auto-confirm installation (skip interactive prompt)     |
| `--dry-run`      | Show installation plan and exit without installing      |
| `--auth`         | Authentication parameter: `"token"` or `"header:value"` |
| `--skip-install` | Skip Claude Code installation                           |
| `--no-admin`     | Do not request admin elevation on Windows               |

## Troubleshooting

### No configuration specified

If you see an error about no configuration, ensure you set the `CLAUDE_CODE_TOOLBOX_ENV_CONFIG` variable inline with the bootstrap command. See [Quick Start](#quick-start) for examples.

### Configuration not found in repository

If the named configuration is not found, verify the name matches a YAML file in the [claude-code-artifacts-public](https://github.com/alex-feel/claude-code-artifacts-public) repository. Browse the repository to see available configurations.

### command-defaults requires command-names

Both `command-names` and `command-defaults` must be specified together. Provide both or neither.

### effort-level 'max' requires model to be specified

The `max` effort level requires the `model` key to be set to an Opus variant:

```yaml
model: "opus"
effort-level: "max"
```

### Invalid platform keys in dependencies

Use `macos` as the platform key:

```yaml
dependencies:
  macos:  # Correct
    - "brew install wget"
```

### SKILL.md is required in the files list

Every skill must include `SKILL.md` in its `files` list:

```yaml
skills:
  - name: "my-skill"
    base: "skills/"
    files:
      - "SKILL.md"       # Required
      - "other-file.md"
```

### hooks.events command not found in hooks.files

Every `command` referenced in hook events must be listed in `hooks.files`. Ensure the filenames match exactly.

### Key 'hooks' is not allowed in user-settings

The `hooks` and `statusLine` keys are profile-specific and must be configured at the root level of the YAML configuration, not inside `user-settings`.

### Debug mode

Enable verbose logging to diagnose issues:

```bash
export CLAUDE_CODE_TOOLBOX_DEBUG=1
```

### Permission errors on Linux/macOS

The setup refuses to run as root by default. For Docker or CI environments where root execution is necessary:

```bash
export CLAUDE_CODE_TOOLBOX_ALLOW_ROOT=1
```

### Non-interactive mode

For automated environments where no interactive prompt is available:

**Environment variable (all platforms, works in piped mode):**

```bash
export CLAUDE_CODE_TOOLBOX_CONFIRM_INSTALL=1
```

**CLI flag (direct invocation only, not piped):**

```bash
./setup-environment.sh python --yes
```

**Windows PowerShell (piped via iex):**

```powershell
$env:CLAUDE_CODE_TOOLBOX_CONFIRM_INSTALL='1'; $env:CLAUDE_CODE_TOOLBOX_ENV_CONFIG='python'; iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')
```

**Linux/macOS (piped via curl):**

```bash
export CLAUDE_CODE_TOOLBOX_CONFIRM_INSTALL=1
export CLAUDE_CODE_TOOLBOX_ENV_CONFIG=python
curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash
```

Alternatively, on Linux/macOS you can pass flags through `bash -s --`:

```bash
curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash -s -- --yes
```

### Dry-run mode

To preview the installation plan without making any changes:

**Environment variable (all platforms, works in piped mode):**

```bash
export CLAUDE_CODE_TOOLBOX_DRY_RUN=1
```

**CLI flag (direct invocation only, not piped):**

```bash
./setup-environment.sh python --dry-run
```

**Windows PowerShell (piped via iex):**

```powershell
$env:CLAUDE_CODE_TOOLBOX_DRY_RUN='1'; $env:CLAUDE_CODE_TOOLBOX_ENV_CONFIG='python'; iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')
```

## Security Considerations

### Trust Levels

Configuration sources have different trust levels:

- **Repository configs** (from [claude-code-artifacts-public](https://github.com/alex-feel/claude-code-artifacts-public)) -- Community-reviewed configurations
- **Local files** -- Under your direct control. May contain API keys and other sensitive data.
- **Remote URLs** -- The setup displays a warning when loading from remote URLs. Always verify the source before proceeding.

### Sensitive Path Detection

Destinations in `files-to-download` are checked against sensitive path prefixes (for example, `~/.ssh/`, `~/.bashrc`). Sensitive paths are flagged with `[!]` in the installation summary so you can review them before confirming.

### Token Handling

Never commit authentication tokens to repositories. Use environment variables (`GITHUB_TOKEN`, `GITLAB_TOKEN`, `REPO_TOKEN`) instead.

### Protected Configuration Keys

The `global-config` key excludes `oauthSession` and `oauthAccount` to prevent OAuth credentials from appearing in YAML configuration files.

### Installation Confirmation

By default, the setup requires explicit confirmation before installing. Use `--dry-run` to preview the installation plan without making changes. Unknown configuration keys are flagged with `[?]` in the installation summary to help you identify potential typos or unsupported keys.
