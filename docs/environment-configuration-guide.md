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

Quick-reference table of all configuration keys. Each key links to its detailed documentation in the [Configuration Keys](#configuration-keys) section below.

| YAML Key                                              | Type                   | Required | Default | Brief Description                                          |
|-------------------------------------------------------|------------------------|----------|---------|------------------------------------------------------------|
| [`name`](#name)                                       | `str`                  | **Yes**  | --      | Display name for the environment                           |
| [`description`](#description)                         | `str`                  | No       | `None`  | Config description (shown in summary)                      |
| [`post-install-notes`](#post-install-notes)           | `str`                  | No       | `None`  | Notes shown after successful installation                  |
| [`version`](#version)                                 | `str`                  | No       | `None`  | Config version (semver)                                    |
| [`inherit`](#inherit)                                 | `str \| list`          | No       | `None`  | Parent config URL/path/name or list for composition chains |
| [`merge-keys`](#merge-keys)                           | `list[str]`            | No       | `None`  | Keys to merge instead of replace                           |
| [`command-names`](#command-names)                     | `list[str]`            | No*      | `[]`    | Command names and aliases                                  |
| [`base-url`](#base-url)                               | `str`                  | No       | `None`  | Base URL for relative resource paths                       |
| [`claude-code-version`](#claude-code-version)         | `str`                  | No       | `None`  | Specific Claude Code version or `"latest"`                 |
| [`install-nodejs`](#install-nodejs)                   | `bool`                 | No       | `None`  | Install Node.js LTS before dependencies                    |
| [`dependencies`](#dependencies)                       | `dict`                 | No       | `{}`    | Platform-specific dependency commands                      |
| [`agents`](#agents)                                   | `list[str]`            | No       | `[]`    | Agent markdown file paths                                  |
| [`slash-commands`](#slash-commands)                   | `list[str]`            | No       | `[]`    | Slash command file paths                                   |
| [`rules`](#rules)                                     | `list[str]`            | No       | `[]`    | Rule markdown file paths (user-scope)                      |
| [`skills`](#skills)                                   | `list[Skill]`          | No       | `[]`    | Skill configurations                                       |
| [`files-to-download`](#files-to-download)             | `list[FileToDownload]` | No       | `[]`    | Files to download during setup                             |
| [`global-config`](#global-config)                     | `GlobalConfig`         | No       | `None`  | Settings for `~/.claude.json`                              |
| [`hooks`](#hooks)                                     | `Hooks`                | No       | `None`  | Hook configurations (files and events)                     |
| [`mcp-servers`](#mcp-servers)                         | `list[dict]`           | No       | `[]`    | MCP server configurations                                  |
| [`model`](#model)                                     | `str`                  | No       | `None`  | Model alias or custom model name                           |
| [`permissions`](#permissions)                         | `Permissions`          | No       | `None`  | Permission rules for tools                                 |
| [`env-variables`](#env-variables)                     | `dict[str, str]`       | No       | `None`  | Claude-level environment variables                         |
| [`os-env-variables`](#os-env-variables)               | `dict`                 | No       | `None`  | OS-level persistent environment variables                  |
| [`command-defaults`](#command-defaults)               | `CommandDefaults`      | No*      | `None`  | System prompt and mode                                     |
| [`user-settings`](#user-settings)                     | `UserSettings`         | No       | `None`  | Merged into `settings.json`                                |
| [`always-thinking-enabled`](#always-thinking-enabled) | `bool`                 | No       | `None`  | Enable always-on thinking mode                             |
| [`effort-level`](#effort-level)                       | `str`                  | No       | `None`  | Adaptive reasoning effort level                            |
| [`company-announcements`](#company-announcements)     | `list[str]`            | No       | `None`  | Announcement strings for users                             |
| [`attribution`](#attribution)                         | `Attribution`          | No       | `None`  | Commit and PR attribution strings                          |
| [`status-line`](#status-line)                         | `StatusLine`           | No       | `None`  | Status line script configuration                           |

> `command-names` and `command-defaults` have a co-dependency: if one is specified, the other must also be specified.

### Configuration key naming

All configuration keys use **kebab-case** (hyphenated lowercase), for example `mcp-servers`, `effort-level`, `files-to-download`. Using underscores (`effort_level`, `mcp_servers`) will cause the key to be flagged as unknown during installation.

**Sub-key naming conventions:**

- **Top-level keys** (`hooks`, `permissions`, `mcp-servers`, etc.): MUST be kebab-case (validated by `KNOWN_CONFIG_KEYS`)
- **Sub-keys in structured sections** (`hooks.events[]`, `permissions`): MUST be kebab-case (the toolbox translates to camelCase for Claude Code JSON output)
- **Sub-keys in free-form sections** (`user-settings`, `global-config`): MUST match Claude Code's native camelCase (pass-through, no translation)

> **Note:** The Pydantic validation model (`EnvironmentConfig`) uses `populate_by_name=True` for testing convenience, which means CI validation accepts both `effort_level` and `effort-level`. However, the runtime setup script (`setup_environment.py`) uses `config.get('effort-level')` and will not recognize underscore variants. Always use kebab-case in your configuration files.

## Configuration Keys

### Core Settings

#### `name`

Display name for the environment, shown in the setup header and summary.

- **Type:** `str` (required)
- **Inheritance:** Standard override (child replaces parent)
- **Example:** `name: "Python Development"`

#### `description`

Description of the environment configuration. Shown in the installation summary immediately after the configuration name, providing context about the environment's purpose.

- **Type:** `str | None`
- **Default:** `None`
- **Multiline:** Supported via YAML `|` (literal block) or `>` (folded block) scalars
- **Display:** In installation summary, after "Configuration:" and before "Source:", with 2-space indent per line. No "Description:" label prefix.
- **Inheritance:** Standard override (child replaces parent)
- **Example:**

```yaml
description: |
  A comprehensive development environment for AI-powered coding
  with pre-configured MCP servers, custom agents, and debugging tools.
```

#### `post-install-notes`

Notes displayed after successful installation. Use for next steps, setup instructions, API key configuration, or any guidance the configuration author wants to communicate after the environment is installed.

- **Type:** `str | None`
- **Default:** `None`
- **Multiline:** Supported via YAML `|` (literal block) or `>` (folded block) scalars
- **Display:** After successful installation only (not on failure, not in dry-run). Rendered after the "Documentation:" section with a yellow header "Notes from the configuration author:" and 2-space indent per line.
- **Inheritance:** Standard override (child replaces parent)
- **Example:**

```yaml
post-install-notes: |
  Next steps:
  1. Set your API key: export ANTHROPIC_API_KEY=sk-...
  2. Start the environment: my-env
  3. Run /help to see available commands

  Documentation: https://docs.example.com/my-env
```

#### `version`

Configuration version for update checking. Extracted from the root config before inheritance resolution.

- **Type:** `str | None`
- **Default:** `None`
- **Validation:** Must be valid semver (`X.Y.Z` format, with optional pre-release and build metadata)
- **Inheritance:** Not inherited. Extracted from the root config before inheritance resolution.
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
- **Inheritance:** Standard override (child replaces parent)
- **Note:** If empty or not specified, hooks are written to `~/.claude/settings.json` (global scope) instead of a per-environment `config.json`. Manifest, launcher, and command registration steps are skipped. The setup still processes other resources (agents, MCP servers, dependencies, and so on) but does not create a launchable command.
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
- **Inheritance:** Standard override (child replaces parent). Each level's `base-url` applies to that level's own resource paths during inheritance resolution. A child `base-url` does **not** retroactively affect parent resource paths -- see [Resource Path Resolution in Inheritance](#resource-path-resolution-in-inheritance).
- **Example:** `base-url: "https://raw.githubusercontent.com/org/repo/main"`

#### `inherit`

URL, local path, or repository config name to inherit from. Accepts a single string or a list of strings/structured objects for composition chains.

- **Type:** `str | list[str | {config: str, merge-keys: list[str]}] | None`
- **Default:** `None`
- **Single string:** Standard recursive inheritance (child overrides parent). Use `merge-keys` to selectively merge.
- **List of strings/objects:** Flat composition chain (left-to-right). Each entry's own `inherit` and `merge-keys` are stripped. Per-entry merge-keys specified via structured `{config: ..., merge-keys: [...]}` entries in the leaf. See [List Inherit (Composition Chains)](#list-inherit-composition-chains).
- **Validation:** Cannot be empty, no null bytes. Lists must be non-empty with all entries as non-empty strings or valid structured objects.
- **Max depth:** 10 levels
- **Circular dependency detection:** Automatic
- **Inheritance:** Not applicable (structural meta-key consumed during resolution)
- **Example:**

```yaml
# Single string (standard recursive inheritance)
inherit: "https://raw.githubusercontent.com/org/repo/main/base.yaml"
# or
inherit: "./base-config.yaml"
# or
inherit: "base-config"  # fetched from artifacts-public repo

# List (composition chain)
inherit:
  - base.yaml
  - extensions.yaml

# List with per-entry merge-keys (structured entries)
inherit:
  - base.yaml
  - config: extensions.yaml
    merge-keys:
      - agents
      - rules
```

See [Configuration Inheritance](#configuration-inheritance) for details.

#### `merge-keys`

List of top-level keys that should be merged (extended from parent) rather than replaced during inheritance resolution. Only effective when `inherit` is also specified.

- **Type:** `list[str] | None`
- **Default:** `None`
- **Valid values:** `dependencies`, `agents`, `slash-commands`, `rules`, `skills`, `files-to-download`, `hooks`, `mcp-servers`, `global-config`, `user-settings`, `env-variables`, `os-env-variables`
- **Validation:** Non-eligible keys produce an error. Presence without `inherit` produces a warning.
- **Stripped from output:** Yes (like `inherit`)
- **Inheritance:** Not applicable. Evaluated at each inheritance level independently; not inherited or accumulated across levels.
- **Example:**

```yaml
inherit: base.yaml
merge-keys:
  - agents
  - mcp-servers
  - dependencies
  - hooks
```

See [Selective Merge (merge-keys)](#selective-merge-merge-keys) for details.

### Installation Control

#### `claude-code-version`

Specific Claude Code version to install.

- **Type:** `str | None`
- **Default:** `None`
- **Special value:** `"latest"` (case-insensitive) installs the latest available version (same as the default behavior)
- **Validation:** Must be `"latest"` or valid semver (`X.Y.Z` with optional pre-release and build metadata)
- **Note:** Works with both native (via direct binary download from Google Cloud Storage) and npm installation methods. If the requested version is not found via GCS, the installer falls back to the native installer with the latest version
- **Auto-update management:** When a specific version is set, auto-update controls are automatically injected into multiple targets to prevent Claude Code from overwriting the pinned version. When `"latest"` is used or the key is absent, those controls are automatically removed. See [Automatic Auto-Update Management](#automatic-auto-update-management) for details.
- **IDE extension management:** When a specific version is set, IDE extension auto-install is disabled and the matching extension version is installed into detected VS Code family IDEs. See [Automatic IDE Extension Version Management](#automatic-ide-extension-version-management) for details.
- **Inheritance:** Standard override (child replaces parent)
- **Example:** `claude-code-version: "1.0.128"` or `claude-code-version: "latest"`

#### `install-nodejs`

Install Node.js LTS before processing dependencies. Used when MCP servers or tools need Node.js but Claude Code itself was installed natively (without Node.js).

- **Type:** `bool | None`
- **Default:** `None`
- **Note:** When `true`, only checks the minimum Node.js version (>= 18.0.0), not Claude Code npm compatibility
- **Inheritance:** Standard override (child replaces parent)
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
- **Inheritance:** Standard override (child replaces parent) by default. When listed in `merge-keys`: per-platform sub-key list concatenation with deduplication. Parent platform commands appear first; child commands are appended. Duplicates are removed by string equality.
- **Example:**

```yaml
dependencies:
  common:
    - "uv tool install ruff"
    - "uv tool install ty"
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
- **Inheritance:** Standard override (child replaces parent) by default. When listed in `merge-keys`: parent and child lists are concatenated with deduplication by string equality. Parent items appear first; new child items are appended.
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
- **Inheritance:** Standard override (child replaces parent) by default. When listed in `merge-keys`: parent and child lists are concatenated with deduplication by string equality. Parent items appear first; new child items are appended.
- **Example:**

```yaml
slash-commands:
  - "commands/review.md"
  - "commands/deploy.md"
```

#### `rules`

Rule files placed in `~/.claude/rules/` during setup. Claude Code loads `.md` files from this directory recursively as user-scope rules that apply across all projects.

- **Type:** `list[str] | None`
- **Default:** `[]`
- **Scope:** User-scope only (`~/.claude/rules/`). Project-scope rules (`.claude/rules/` in the repository) should be committed directly to version control.
- **Note:** Only `.md` files are recognized by Claude Code. Rules support optional YAML frontmatter with `description:` and `paths:` for path-scoped rules (glob patterns).
- **Inheritance:** Standard override (child replaces parent) by default. When listed in `merge-keys`: parent and child lists are concatenated with deduplication by string equality. Parent items appear first; new child items are appended.
- **Example:**

```yaml
rules:
  - "rules/coding-standards.md"
  - "rules/security-policy.md"
```

#### `skills`

Skill configurations. Each skill is a set of files placed in `~/.claude/skills/{name}/`.

- **Type:** `list[Skill] | None`
- **Default:** `[]`
- **Inheritance:** Standard override (child replaces parent) by default. When listed in `merge-keys`: identity-based merge by `name` field. Child skills with the same name replace the parent skill in-position (at the parent's original index). New child skills are appended at the end.
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
- **Inheritance:** Standard override (child replaces parent) by default. When listed in `merge-keys`: identity-based merge by `dest` field. Child entries with the same destination replace the parent entry in-position. New child entries are appended at the end.
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
- **Inheritance:** Standard override (child replaces parent) by default. When listed in `merge-keys`: identity-based merge by `name` field. Child servers with the same name replace the parent server in-position (at the parent's original index). New child servers are appended at the end.

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

> **Isolated environments:** When `command-names` creates an isolated environment, `scope: user` MCP servers are configured with `CLAUDE_CONFIG_DIR` pointing to the isolated directory. This ensures `claude mcp add --scope user` writes to the isolated `.claude.json` instead of the home-directory one.

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

MCP server names are automatically added to the `permissions.allow` list as `mcp__servername`. You do not need to manually add MCP server permissions.

### Model and Reasoning

#### `model`

Model alias or custom model name for Claude Code.

- **Type:** `str | None`
- **Default:** `None`
- **Valid aliases:** `default`, `sonnet`, `opus`, `haiku`, `opus[1m]`, `sonnet[1m]`, `opusplan`
- **Custom names:** Any model name starting with `claude-` (for example, `claude-3-5-sonnet-20241022`)
- **Inheritance:** Standard override (child replaces parent)
- **Example:** `model: "opus"` or `model: "claude-3-5-sonnet-20241022"`

#### `always-thinking-enabled`

Enable always-on extended thinking mode.

- **Type:** `bool | None`
- **Default:** `None`
- **Inheritance:** Standard override (child replaces parent)
- **Example:** `always-thinking-enabled: true`

#### `effort-level`

Controls adaptive reasoning effort.

- **Type:** `str | None` (one of `low`, `medium`, `high`, `max`)
- **Default:** `None`
- **Inheritance:** Standard override (child replaces parent)
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
- **Inheritance:** Standard override (child replaces parent). Note: MCP server permissions are automatically added during setup regardless of inheritance.
- **Fields:**
  - `default-mode` -- One of `default`, `acceptEdits`, `plan`, `bypassPermissions`
  - `allow` -- List of explicitly allowed actions
  - `deny` -- List of explicitly denied actions
  - `ask` -- List of actions requiring confirmation
  - `additional-directories` -- List of additional directory paths
- **Note:** MCP server permissions (for example, `mcp__servername`) are automatically merged into the `allow` list
- **Example:**

```yaml
permissions:
  default-mode: "default"
  allow:
    - "Read"
    - "Glob"
    - "Grep"
  deny:
    - "Bash(rm -rf)"
  ask:
    - "Edit"
    - "Write"
  additional-directories:
    - "/opt/project-data"
```

### Environment Variables

#### `env-variables`

Claude-level environment variables set in the settings file. These are available within Claude Code sessions only.

- **Type:** `dict[str, str] | None`
- **Default:** `None`
- **Inheritance:** Standard override (child replaces parent) by default. When listed in `merge-keys`: shallow dictionary merge. Child keys override matching parent keys. Set a value to `null` to delete a parent key (RFC 7396 semantics).
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
- **Inheritance:** Standard override (child replaces parent) by default. When listed in `merge-keys`: shallow dictionary merge. Child keys override matching parent keys. Set a value to `null` to delete a parent key (RFC 7396 semantics).
- **Example:**

```yaml
os-env-variables:
  MY_TOOL_PATH: "/opt/my-tool/bin"
  OLD_UNUSED_VAR: null  # Deletes this variable
```

- **Automatic string conversion:** Non-string YAML values (integers, booleans, floats) in both `env-variables` and `os-env-variables` are automatically converted to strings by the setup script. For example, `MCP_TIMEOUT: 30000` (YAML integer) becomes `"30000"` (string), and `ENABLE_FEATURE: true` (YAML boolean) becomes `"True"` (string). To preserve exact string representation, quote values in YAML: `ENABLE_FEATURE: "true"`.
- **Current session guidance (Linux/macOS):** When variables are deleted via `null`, the setup script outputs shell-specific `unset` commands so the user can remove those variables from the running session without opening a new terminal:
  - **Bash/Zsh:** `unset VARNAME` for each deleted variable
  - **Fish** (when installed): `set -e VARNAME` for each deleted variable

#### Environment Variable Loading

The setup script provides two distinct mechanisms for environment variables, each serving a different scope:

| YAML Key           | Scope                | Storage                           | Available In                         |
|--------------------|----------------------|-----------------------------------|--------------------------------------|
| `env-variables`    | Claude Code internal | `config.json` `env` key (profile) | Claude Code sessions only            |
| `os-env-variables` | OS-level persistent  | Shell profiles + Windows registry | All processes (terminals, programs)  |

##### Env Loader Files

When `os-env-variables` are configured, the setup generates Rustup-style env loader files that can be sourced to load the variables into the current shell session. These files contain **only** `os-env-variables` (not `env-variables`, which are handled by Claude Code's `config.json`).

**Per-command files** (generated when `command-names` is specified):

| File                         | Shell      | Generated When |
|------------------------------|------------|----------------|
| `~/.claude/{cmd}/env.sh`     | Bash/Zsh   | Always         |
| `~/.claude/{cmd}/env.fish`   | Fish       | Fish installed |
| `~/.claude/{cmd}/env.ps1`    | PowerShell | Windows only   |
| `~/.claude/{cmd}/env.cmd`    | CMD batch  | Windows only   |

**Global convenience files** (always generated when `os-env-variables` are non-empty):

| File                          | Shell      | Generated When |
|-------------------------------|------------|----------------|
| `~/.claude/toolbox-env.sh`    | Bash/Zsh   | Always         |
| `~/.claude/toolbox-env.fish`  | Fish       | Fish installed |
| `~/.claude/toolbox-env.ps1`   | PowerShell | Windows only   |
| `~/.claude/toolbox-env.cmd`   | CMD batch  | Windows only   |

Variables set to `null` (deletions) are excluded from loader files.

##### Automatic Loading via Launchers

When `command-names` is specified, the generated launcher scripts automatically source the per-command env loader file before starting Claude Code. No manual action is required -- running the command (for example, `claude-python`) loads all OS environment variables.

The source line is guarded by a file-existence check, so launchers work normally even when no `os-env-variables` are configured.

##### Manual Sourcing for Bare `claude`

Users who run bare `claude` (without a command-name launcher) can manually source the global loader to apply OS environment variables to their current shell session:

**Bash/Zsh:**

```bash
source ~/.claude/toolbox-env.sh
```

**Fish:**

```fish
source ~/.claude/toolbox-env.fish
```

**PowerShell (Windows):**

```powershell
. ~/.claude/toolbox-env.ps1
```

**CMD (Windows):**

```batch
%USERPROFILE%\.claude\toolbox-env.cmd
```

Alternatively, open a new terminal -- shell profiles are updated during setup and will load the variables automatically.

##### Fish Dual-Mechanism

On systems with Fish shell installed, the setup uses two complementary mechanisms for OS environment variables:

- **`set -gx` in `config.fish`**: Durable persistence. Variables are loaded when Fish starts. This is the primary mechanism.
- **`set -Ux` (Universal Exported)**: Instant propagation. Variables are immediately visible in all running Fish sessions without requiring `source` or a new terminal. For deletions, `set -Ue` removes the universal variable.

The `config.fish` write is always the authoritative source. The `set -Ux` call is a complementary enhancement that provides immediate availability.

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
- **Inheritance:** Standard override (child replaces parent)
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
- **Excluded keys:** `hooks` and `statusLine` (these require dedicated write logic with path resolution and type processing, and must be configured at the root level of the YAML configuration)
- **Inheritance:** Standard override (child replaces parent) by default. When listed in `merge-keys`: deep recursive merge using `deep_merge_settings()` with `DEFAULT_ARRAY_UNION_KEYS` (`permissions.allow`, `permissions.deny`, `permissions.ask` arrays are unioned with deduplication). Child keys override matching parent keys; `null` values delete keys.
- **Example:**

```yaml
user-settings:
  language: "english"
  theme: "dark"
  apiKeyHelper: "uv run --no-project --python 3.12 ~/.claude/scripts/api-key-helper.py"
  env:
    DISABLE_AUTOUPDATER: "1"
```

##### Relationship to Profile-Owned Keys

`user-settings` is the **forward-compatibility escape hatch** for the ~85% of Claude Code CLI `settings.json` schema that the toolbox does not model at the YAML root level. It COMPLEMENTS (does not replace or contradict) the profile-settings writer used in non-command-names mode. See also [Profile-Level Settings Routing](#profile-level-settings-routing) for the end-to-end picture.

**Decision matrix -- where should I put a given setting?**

| Setting category                     | YAML root level                      | `user-settings:`         | `global-config:`         |
|--------------------------------------|--------------------------------------|--------------------------|--------------------------|
| 9 profile-owned keys (below)         | **YES** (profile-owned, auto-routed) | No                       | No                       |
| Any other `settings.json` CLI key    | No                                   | **YES** (free-form)      | No                       |
| Any `~/.claude.json` CLI key         | No                                   | No                       | **YES** (free-form)      |

**9 profile-owned keys (placed at YAML root level):**

- `model`, `permissions`, `env-variables`, `attribution`, `always-thinking-enabled`, `effort-level`, `company-announcements`, `status-line`, `hooks`

**Examples of "any other `settings.json` CLI key" (placed under `user-settings:`):**

- `language`, `theme`, `includeGitInstructions`, `apiKeyHelper`, `awsCredentialExport`, `cleanupPeriodDays`, `outputStyle`, `autoMemoryDirectory`, `defaultShell`, `respectGitignore`, `sandbox.*`, plus any new Claude Code CLI setting not yet modeled at YAML root level. `user-settings` uses `extra='allow'` Pydantic semantics, so any key that is not explicitly excluded passes through unchanged.

**Examples of "any `~/.claude.json` CLI key" (placed under `global-config:`):**

- `autoConnectIde`, `editorMode`, `showTurnDuration`, `terminalProgressBarEnabled`, and any other global CLI settings.

**Precedence rule for the 9 profile-owned keys:**

If you declare a profile-owned key (e.g., `permissions`) at BOTH YAML root level AND under `user-settings:`, the **root-level value wins** because Step 18 `write_profile_settings_to_settings()` runs AFTER Step 14 `write_user_settings()` and performs a full top-level REPLACE (not a deep merge). A warning from `detect_settings_conflicts()` is emitted during validation to make the precedence explicit. The warning fires in BOTH command-names-present and command-names-absent modes.

**Why the two surfaces coexist:**

- **Profile-owned keys** (9 keys) have first-class atomic semantics because the toolbox fully owns them: kebab-to-camel translation (`default-mode` -> `defaultMode`), file path resolution for hook events, status-line command-string generation with absolute POSIX paths, and auto-update Target 2/3 injection management.
- **`user-settings`** passes through any other key without interpretation. This allows users to configure any Claude Code CLI setting the toolbox does not model at the YAML root level -- including settings added in future Claude Code releases -- without waiting for a toolbox update. This is the meaning of "forward-compatibility escape hatch".

**Keys explicitly FORBIDDEN under `user-settings:` (validation error):**

- `hooks` -- must be at YAML root level (requires file download, path resolution, type processing via `_build_hooks_json()`).
- `statusLine` -- must be at YAML root level via `status-line:` (requires file download and path resolution into `hooks.files`).

These two keys are blocked by `check_excluded_keys` in the `UserSettings` Pydantic model (`USER_SETTINGS_EXCLUDED_KEYS = {'hooks', 'statusLine'}`). No other keys are blocked -- this exclusion set is NOT extended to cover the 9 profile-owned keys.

**Preservation contract for `user-settings`:**

Keys that you put under `user-settings:` are preserved even when you re-run the setup with a different YAML that omits them, because Step 14 `write_user_settings()` uses deep-merge semantics and never deletes keys unless you set them to `null`. Additionally, Step 18 `write_profile_settings_to_settings()` only touches keys that appear in the profile delta; all other keys (including your `user-settings` contributions and any user-managed keys outside the YAML) remain intact. This is the deliberate shared-file semantics: the toolbox does NOT surprise-delete anything from the shared `~/.claude/settings.json`. See [Profile-Level Settings Routing](#profile-level-settings-routing) below for the full write semantics contract and the deferred stale-key behavior.

#### `global-config`

Settings merged into `~/.claude.json` (the Claude Code global configuration file). When `command-names` is present, additionally written to `~/.claude/{cmd}/.claude.json` for isolated environments (Claude Code CLI resolves `getGlobalClaudeFile()` via `CLAUDE_CONFIG_DIR` with no fallback to the home directory). Uses deep merge with no array union (arrays are replaced, not merged).

- **Type:** `GlobalConfig | None`
- **Default:** `None`
- **Excluded keys:** `oauthAccount` cannot be set to non-null values (OAuth credentials must not appear in YAML configuration files). Set `oauthAccount: null` to clear authentication state.
- **Inheritance:** Standard override (child replaces parent) by default. When listed in `merge-keys`: deep recursive merge using `deep_merge_settings()` with `array_union_keys=set()` (arrays are replaced, not unioned). Child keys override matching parent keys; `null` values delete keys (RFC 7396).
- **Example:**

```yaml
global-config:
  autoConnectIde: true
  editorMode: "vim"
  showTurnDuration: true
```

#### Key Deletion (Null-as-Delete)

Both `user-settings` and `global-config` support key deletion via RFC 7396 JSON Merge Patch semantics. Set a key to `null` to remove it from the target JSON file.

```yaml
user-settings:
  theme: "dark"
  staleKey: null  # Removes staleKey from settings.json

global-config:
  autoConnectIde: true
  oldSetting: null  # Removes oldSetting from ~/.claude.json
  oauthAccount: null  # Clears OAuth authentication state
```

**Behavior:**

- Setting a key to `null` removes it from the target file
- Setting a nonexistent key to `null` is a silent no-op
- Nested deletion: `section: {key: null}` removes only `key`, preserving `section`
- Top-level deletion: `section: null` removes the entire section
- Null inside arrays is NOT treated as deletion
- The `--dry-run` summary shows `[DELETE]` markers for null-valued keys

> **Warning:** Bare YAML keys with no value (`key:`) are equivalent to `key: null`. This means accidentally omitting a value will DELETE that key rather than set it to an empty string. Always use explicit values: `key: ""` for empty strings, `key: null` for intentional deletion.

**Profile-owned keys in non-command-names mode:** The nine profile-owned keys (`model`, `permissions`, `env-variables`, `attribution`, `always-thinking-enabled`, `effort-level`, `company-announcements`, `status-line`, `hooks`) also support null-as-delete at the YAML root level via the [conditional top-level replace writer](#profile-level-settings-routing). Setting `model: null` at YAML root level deletes the `model` key from `~/.claude/settings.json`. OMITTING a profile-owned key from a subsequent YAML run does NOT delete it -- see [Deferred Stale-Key Behavior](#deferred-stale-key-behavior-user-facing-contract) for the intentional preservation contract.

#### `company-announcements`

Announcement strings displayed to users during setup.

- **Type:** `list[str] | None`
- **Default:** `None`
- **Inheritance:** Standard override (child replaces parent)
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
- **Inheritance:** Standard override (child replaces parent)
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
- **Inheritance:** Standard override (child replaces parent)
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

Event-driven hooks that run automatically during Claude Code sessions. Four hook types are supported: `command`, `http`, `prompt`, and `agent`.

- **Type:** `Hooks | None`
- **Default:** `None`
- **Inheritance:** Standard override (child replaces parent) by default. When listed in `merge-keys`: composite merge. `files` lists are concatenated with deduplication by full file path string equality. `events` lists are concatenated without deduplication (each event is unique by its field combination).
- **Fields:**
  - `files` (list[str]) -- Script files to download to `~/.claude/hooks/`. Only used by command hooks.
  - `events` (list[HookEvent]) -- Event configurations

#### Hook Types

| Type      | Description                                            | Required Field |
|-----------|--------------------------------------------------------|----------------|
| `command` | Executes a shell command or script (default)           | `command`      |
| `http`    | Sends an HTTP POST request to a URL                    | `url`          |
| `prompt`  | Single-turn LLM evaluation with no tool access         | `prompt`       |
| `agent`   | Spawns a subagent with tool access for evaluation      | `prompt`       |

#### Common Fields (All Hook Types)

These fields apply to all four hook types:

| Field            | YAML Key         | Type   | Required | Description                                                                              |
|------------------|------------------|--------|----------|------------------------------------------------------------------------------------------|
| `event`          | `event`          | `str`  | Yes      | Event name (for example, `PreToolUse`, `PostToolUse`, `Notification`)                    |
| `matcher`        | `matcher`        | `str`  | No       | Regex pattern for matching (default: `""`)                                               |
| `type`           | `type`           | `str`  | No       | Hook type: `command`, `http`, `prompt`, or `agent` (default: `command`)                  |
| `if`             | `if`             | `str`  | No       | Permission rule syntax filter (for example, `"Bash(git *)"`, `"Edit(*.ts)"`)             |
| `status-message` | `status-message` | `str`  | No       | Custom spinner message displayed while the hook runs                                     |
| `once`           | `once`           | `bool` | No       | If true, runs only once per session then is removed (skills only)                        |
| `timeout`        | `timeout`        | `int`  | No       | Timeout in seconds (defaults vary by type: 600 for command, 30 for prompt, 60 for agent) |

#### Type-Specific Fields

##### Command Hook Fields

| Field     | YAML Key  | Type   | Required | Description                                                                                 |
|-----------|-----------|--------|----------|---------------------------------------------------------------------------------------------|
| `command` | `command` | `str`  | Yes      | Script filename (must exist in `hooks.files`)                                               |
| `config`  | `config`  | `str`  | No       | Config file reference (must exist in `hooks.files`). Toolbox-specific: appended as argument |
| `async`   | `async`   | `bool` | No       | If true, runs the command in the background without blocking                                |
| `shell`   | `shell`   | `str`  | No       | Shell to use: `"bash"` (default) or `"powershell"`                                          |

##### HTTP Hook Fields

| Field              | YAML Key           | Type            | Required | Description                                                               |
|--------------------|--------------------|-----------------|----------|---------------------------------------------------------------------------|
| `url`              | `url`              | `str`           | Yes      | URL to send the HTTP POST request to                                      |
| `headers`          | `headers`          | `dict[str,str]` | No       | Additional HTTP headers. Values support `$VAR_NAME` env var interpolation |
| `allowed-env-vars` | `allowed-env-vars` | `list[str]`     | No       | Environment variable names permitted for interpolation into header values |

##### Prompt and Agent Hook Fields

| Field    | YAML Key | Type  | Required | Description                                       |
|----------|----------|-------|----------|---------------------------------------------------|
| `prompt` | `prompt` | `str` | Yes      | Prompt text for LLM evaluation                    |
| `model`  | `model`  | `str` | No       | Model to use for the evaluation                   |

#### Field Matrix

Complete required/forbidden field matrix across all hook types:

| Field              | `command` | `http`    | `prompt`  | `agent`   |
|--------------------|-----------|-----------|-----------|-----------|
| `command`          | REQUIRED  | FORBIDDEN | FORBIDDEN | FORBIDDEN |
| `config`           | Optional  | FORBIDDEN | FORBIDDEN | FORBIDDEN |
| `async`            | Optional  | FORBIDDEN | FORBIDDEN | FORBIDDEN |
| `shell`            | Optional  | FORBIDDEN | FORBIDDEN | FORBIDDEN |
| `url`              | FORBIDDEN | REQUIRED  | FORBIDDEN | FORBIDDEN |
| `headers`          | FORBIDDEN | Optional  | FORBIDDEN | FORBIDDEN |
| `allowed-env-vars` | FORBIDDEN | Optional  | FORBIDDEN | FORBIDDEN |
| `prompt`           | FORBIDDEN | FORBIDDEN | REQUIRED  | REQUIRED  |
| `model`            | FORBIDDEN | FORBIDDEN | Optional  | Optional  |
| `if`               | Optional  | Optional  | Optional  | Optional  |
| `status-message`   | Optional  | Optional  | Optional  | Optional  |
| `once`             | Optional  | Optional  | Optional  | Optional  |
| `timeout`          | Optional  | Optional  | Optional  | Optional  |

Setting a field marked FORBIDDEN on a hook type produces a validation error.

#### Command Hooks

Execute a script file when the event fires. The `command` field must reference a filename listed in `hooks.files`. The toolbox processes command paths by prepending the appropriate runtime (`uv run` for `.py`, `node` for `.js`/`.mjs`/`.cjs`).

The `config` field is a toolbox-specific extension: when set, the config file path is appended as an argument to the command. This field is not part of the official Claude Code hooks specification.

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
    - event: "Notification"
      type: "command"
      command: "linter.py"
      async: true
      shell: "bash"
      status-message: "Running notification handler..."
```

#### HTTP Hooks

Send an HTTP POST request to the specified URL when the event fires. No file processing is involved -- all fields are passed through to the profile configuration as-is.

```yaml
hooks:
  events:
    - event: "PostToolUse"
      matcher: "Write"
      type: "http"
      url: "http://localhost:8080/hooks/post-tool-use"
      headers:
        Authorization: "Bearer $MY_TOKEN"
        Content-Type: "application/json"
      allowed-env-vars:
        - "MY_TOKEN"
      timeout: 15
      status-message: "Sending webhook notification..."
```

#### Prompt Hooks

Send a prompt to the LLM for single-turn evaluation when the event fires. No tool access is available.

```yaml
hooks:
  events:
    - event: "PreToolUse"
      matcher: "Bash"
      type: "prompt"
      prompt: "Check if this bash command is safe to execute"
      model: "sonnet"
      timeout: 30
```

#### Agent Hooks

Spawn a subagent with tool access for evaluation when the event fires. The subagent can use tools to perform its evaluation, unlike prompt hooks.

```yaml
hooks:
  events:
    - event: "PreToolUse"
      matcher: "Bash(rm *)"
      type: "agent"
      prompt: "Verify security implications of: $ARGUMENTS"
      model: "sonnet"
      timeout: 60
      if: "Bash(rm *)"
      once: true
```

#### File Consistency Rules

The setup validates hook file references for **command hooks only**. HTTP, prompt, and agent hooks do not use file references and are excluded from file consistency validation.

1. Every file listed in `hooks.files` must be used by at least one command hook event or the `status-line` configuration
2. Every `command` in command hook events must exist in `hooks.files`
3. Every `config` in command hook events must exist in `hooks.files`
4. If `status-line` is configured, its `file` and `config` must exist in `hooks.files`
5. If `status-line` is configured but `hooks` is not defined, that is an error

#### Supported Script Types

For command hooks:

- Python: `.py`
- JavaScript: `.js`, `.mjs`, `.cjs`

#### Pass-Through Architecture

The setup script processes hooks differently based on type:

| Hook Type | File Processing                                                | Pass-Through Fields                                    |
|-----------|----------------------------------------------------------------|--------------------------------------------------------|
| `command` | Yes (Python via `uv run`, JavaScript via `node`, other as-is)  | `async`, `shell` + common fields                       |
| `http`    | No (pure pass-through)                                         | `url`, `headers`, `allowed-env-vars` + common fields   |
| `prompt`  | No (pure pass-through)                                         | `prompt`, `model` + common fields                      |
| `agent`   | No (pure pass-through)                                         | `prompt`, `model` + common fields                      |

#### Complete Hooks Example

```yaml
hooks:
  files:
    - "hooks/linter.py"
    - "hooks/security-check.js"
    - "configs/linter-config.yaml"
  events:
    # Command hook with config file
    - event: "PostToolUse"
      matcher: "Edit|MultiEdit|Write"
      type: "command"
      command: "linter.py"
      config: "linter-config.yaml"
    # Command hook with async and shell
    - event: "Notification"
      type: "command"
      command: "security-check.js"
      async: true
      shell: "bash"
      status-message: "Running security check..."
    # HTTP webhook
    - event: "PostToolUse"
      matcher: "Write"
      type: "http"
      url: "http://localhost:8080/hooks/write"
      headers:
        Authorization: "Bearer $API_TOKEN"
      allowed-env-vars:
        - "API_TOKEN"
      timeout: 15
    # Prompt hook for safety check
    - event: "PreToolUse"
      matcher: "Bash"
      type: "prompt"
      prompt: "Check if this bash command is safe to execute"
      timeout: 30
    # Agent hook for security review
    - event: "PreToolUse"
      matcher: "Bash(rm *)"
      type: "agent"
      prompt: "Verify security implications of: $ARGUMENTS"
      model: "sonnet"
      timeout: 60
      if: "Bash(rm *)"
      once: true
```

#### Hooks Routing

Hooks are routed to different target files based on whether `command-names` is specified. Both paths share the same pure builder `_build_hooks_json()` for the `hooks` key universe:

| Scenario                | Target File                    | Write Mechanism                                                  | Hook Files Directory     |
|-------------------------|--------------------------------|------------------------------------------------------------------|--------------------------|
| `command-names` present | `~/.claude/{cmd}/config.json`  | `create_profile_config()` (atomic overwrite)                     | `~/.claude/{cmd}/hooks/` |
| `command-names` absent  | `~/.claude/settings.json`      | `write_profile_settings_to_settings()` (top-level replace)       | `~/.claude/hooks/`       |

When `command-names` is absent, the setup writes hooks to the global `~/.claude/settings.json` via `write_profile_settings_to_settings()` as part of the 9-key `PROFILE_OWNED_KEYS` delta. The writer uses **conditional top-level replace** semantics: the existing file is read, the `hooks` top-level key is replaced entirely (removing stale events from prior runs), and all other keys -- including user-managed keys and other profile-owned keys not in the current delta -- are preserved. See [Profile-Level Settings Routing](#profile-level-settings-routing) for the full contract.

**Re-run behavior:** The toolbox owns the `hooks` key in `settings.json`. Re-running the setup overwrites any manually-added hook events when the YAML re-declares `hooks` (top-level replace semantics). To configure hooks, define them in the YAML configuration rather than editing `settings.json` directly.

**Deleting hooks:** Setting `hooks: null` at YAML root level deletes the entire `hooks` key from `~/.claude/settings.json` via RFC 7396 null-as-delete. OMITTING `hooks` from a subsequent YAML run does NOT delete it (per [Deferred Stale-Key Behavior](#deferred-stale-key-behavior-user-facing-contract)); the prior-run `hooks` content is preserved.

The installation summary distinguishes between the two routing targets:

- With `command-names`: `Hooks: N configured (in config.json)`
- Without `command-names`: `Hooks: N configured (in settings.json)`

## Advanced Topics

### Configuration Inheritance

The `inherit` key allows a configuration to extend a parent configuration. It accepts a single string for standard recursive inheritance or a list of strings/structured objects for explicit composition chains (see [List Inherit (Composition Chains)](#list-inherit-composition-chains)).

#### How Inheritance Works

- Child values completely **replace** parent values for the same top-level key by default
- Use `merge-keys` to selectively **merge** (extend) specific keys instead of replacing them -- see [Selective Merge (merge-keys)](#selective-merge-merge-keys)
- Maximum inheritance depth is 10 levels
- Circular dependencies are detected automatically
- The `version` key is extracted from the root config **before** inheritance resolution
- Both `inherit` and `merge-keys` are stripped from the final merged configuration

#### Resource Path Resolution in Inheritance

When configurations are inherited across different sources (e.g., a GitHub-hosted parent and a local child), relative file paths in each config are resolved using that config's own source location and `base-url`. This ensures that files referenced by a parent config are found at the correct location regardless of where the child config is stored.

**How it works:**

- Each parent config's relative resource paths (agents, rules, slash-commands, hooks files, files-to-download sources, skill bases, system prompts, and status-line files) are resolved to absolute URLs or paths **before** merging with child values
- The resolution uses the parent config's own `config_source` (where it was loaded from) and `base-url`
- Child (leaf) config paths continue to be resolved at validation time using the leaf's own source

**Example:** A GitHub-hosted parent with a local child:

```yaml
# Parent (hosted at https://raw.githubusercontent.com/org/repo/main/parent.yaml)
agents:
  - "agents/shared-agent.md"       # Resolved to https://raw.githubusercontent.com/org/repo/main/agents/shared-agent.md
rules:
  - "rules/coding-standards.md"    # Resolved to https://raw.githubusercontent.com/org/repo/main/rules/coding-standards.md
```

```yaml
# Child (local file: ~/my-project/config.yaml)
inherit: "https://raw.githubusercontent.com/org/repo/main/parent.yaml"
agents:
  - "agents/local-agent.md"        # Resolved locally from ~/my-project/ at validation time
```

After inheritance resolution, the merged config contains both the GitHub-resolved parent paths and the local child paths. Each is resolved from the correct source.

**Key points:**

- A child `base-url` does **not** affect parent resource paths. Each config level's `base-url` governs only its own resources.
- Skills `base` paths ignore `base-url` by design -- they are resolved directly from the config source.
- Already-absolute paths and full URLs pass through resolution unchanged.

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

### List Inherit (Composition Chains)

The `inherit` key also accepts a list of configuration paths for explicit composition chains. The list may contain plain strings (backward compatible) and structured objects with per-entry merge-keys. Four mandatory rules govern list inherit behavior:

#### Rule 1: Own inherit stripped

Each listed file's own `inherit` key is **completely ignored** in list composition mode. It does not participate in chain resolution. The user explicitly specifies the full chain in one place -- if additional parent files are needed, they must be added to the list in the correct order.

#### Rule 2: Equivalent to separate-file chains

`inherit: [base.yaml, extensions.yaml]` behaves **identically** to:

- `leaf.yaml` sets `inherit: extensions.yaml`
- `extensions.yaml` sets `inherit: base.yaml`

Resolution order is left-to-right: the first entry is the base (lowest priority), subsequent entries override earlier ones, and the leaf config overrides everything.

#### Rule 3: Own merge-keys stripped, per-entry from leaf

Each listed file's own `merge-keys` key is **stripped and ignored**. Per-entry merge behavior is controlled by the leaf config using structured inherit entries: `{config: ..., merge-keys: [...]}`.

This design reflects the principle that **merge-keys are a property of the relationship between the leaf and each listed entry**, not an intrinsic property of the listed config. A config file's own `merge-keys` may have been written for a different inheritance context and should not leak into an unrelated composition chain.

Without structured entries, all composition steps use replace semantics (no merging between entries). To merge specific keys at a composition step, use a structured entry with `merge-keys`.

#### Rule 4: Leaf merge-keys for final step

The leaf config's top-level `merge-keys` applies to the **final composition step** (leaf on top of the accumulated base). This is orthogonal to per-entry merge-keys -- Rule 3 controls how listed entries compose with each other, while Rule 4 controls how the leaf merges on top.

#### Structured Inherit Entries

The inherit list accepts mixed entries: plain strings and structured objects.

**Plain string entry** (replace semantics at that step):

```yaml
inherit:
  - base.yaml
  - extensions.yaml
```

**Structured entry** (per-entry merge-keys at that step):

```yaml
inherit:
  - base.yaml
  - config: extensions.yaml
    merge-keys:
      - agents
      - rules
```

Structured entries have the following fields:

| Field        | Type         | Required | Description                                               |
|--------------|--------------|----------|-----------------------------------------------------------|
| `config`     | `str`        | Yes      | Configuration source (URL, path, or repo name)            |
| `merge-keys` | `list[str]`  | No       | Keys to merge instead of replace at this composition step |

The `merge-keys` in a structured entry accepts the same values as the top-level `merge-keys` directive: `dependencies`, `agents`, `slash-commands`, `rules`, `skills`, `files-to-download`, `hooks`, `mcp-servers`, `global-config`, `user-settings`, `env-variables`, `os-env-variables`.

Plain strings and structured entries can be mixed in the same list:

```yaml
inherit:
  - base.yaml                    # Plain string (replace semantics)
  - config: extensions.yaml      # Structured (merge agents and rules)
    merge-keys:
      - agents
      - rules
  - overrides.yaml               # Plain string (replace semantics)
```

> **Note:** Per-entry merge-keys on the **first** entry in the list is a no-op (there is no predecessor to merge with). The first entry always becomes the base.

#### Virtual Chain Equivalence

`inherit: [A, B, C]` is equivalent to creating a virtual chain of separate files:

```text
A (base, no inherit)
B_virtual (inherits A, own inherit + merge-keys stripped, per-entry merge-keys from leaf applied)
C_virtual (inherits B_virtual, own inherit + merge-keys stripped, per-entry merge-keys from leaf applied)
leaf (inherits C_virtual, leaf's top-level merge-keys applied)
```

#### Single-Element List

- `inherit: ["x"]` (plain string) is normalized to `inherit: "x"` and uses the standard recursive single-string path. The file `x.yaml`'s own `inherit` **is** recursively resolved.
- `inherit: [{config: "x", merge-keys: [agents]}]` (structured entry) routes to composition mode. The file's own `inherit` and `merge-keys` are stripped per Rules 1 and 3.

#### Example

```yaml
# base.yaml
name: "Base"
agents:
  - "agents/core-agent.md"
rules:
  - "rules/base-rule.md"
model: "sonnet"
env-variables:
  SHARED_VAR: "from_base"
  BASE_VAR: "base_val"

# extensions.yaml (has own inherit and merge-keys that will be ignored in list mode)
name: "Extensions"
inherit: "some-parent.yaml"  # IGNORED (Rule 1)
merge-keys:                  # IGNORED (Rule 3)
  - agents
  - rules
agents:
  - "agents/extra-agent.md"
rules:
  - "rules/extra-rule.md"
env-variables:
  SHARED_VAR: "from_extensions"
  EXT_VAR: "ext_val"

# leaf.yaml -- per-entry merge-keys specified in the leaf
inherit:
  - base.yaml
  - config: extensions.yaml
    merge-keys:
      - agents
      - rules
name: "My Environment"
merge-keys:
  - os-env-variables
model: "opus"
env-variables:
  LEAF_VAR: "leaf_val"
```

Result:

- `agents`: `["agents/core-agent.md", "agents/extra-agent.md"]` -- merged by the structured entry's `merge-keys` (Rule 3)
- `rules`: `["rules/base-rule.md", "rules/extra-rule.md"]` -- merged by the structured entry's `merge-keys` (Rule 3)
- `model`: `"opus"` -- leaf overrides
- `name`: `"My Environment"` -- leaf overrides
- `env-variables`: `{"LEAF_VAR": "leaf_val"}` -- extensions replaces base's env-variables (not in per-entry merge-keys), then leaf replaces again
- `some-parent.yaml` referenced in extensions.yaml's own inherit is **never loaded** (Rule 1)
- extensions.yaml's own `merge-keys: [agents, rules]` is **ignored** (Rule 3)

### Selective Merge (`merge-keys`)

By default, child configurations completely replace parent values at the top level. The `merge-keys` directive enables selective extension: child values are merged with parent values for specified keys instead of replacing them.

#### Syntax

```yaml
inherit: base-config.yaml
merge-keys:
  - agents
  - mcp-servers
  - dependencies
```

#### Per-Level Evaluation

`merge-keys` is evaluated at each inheritance level independently. It is NOT inherited or accumulated across levels. A replace at level N resets the accumulated value; a merge at level N+1 extends from level N's resolved value only.

Example -- 4-level chain:

```text
Level 1 (source):  agents: [A, B]
Level 2 (merge):   merge-keys: [agents], agents: [C]     => [A, B, C]
Level 3 (replace): agents: [D]                            => [D]
Level 4 (merge):   merge-keys: [agents], agents: [E]     => [D, E]
```

If all levels 2-4 use merge: `[A, B, C, D, E]`.

#### Merge Strategies by Key Type

| Type                   | Keys                                | Strategy                                                                             |
|------------------------|-------------------------------------|--------------------------------------------------------------------------------------|
| String list            | `agents`, `slash-commands`, `rules` | Concatenate parent + child; deduplicate by string equality; parent items first       |
| Named list (by `name`) | `mcp-servers`, `skills`             | Identity-based: child overrides parent in-position; new items appended               |
| Named list (by `dest`) | `files-to-download`                 | Identity-based: child overrides parent in-position; new items appended               |
| Per-platform dict      | `dependencies`                      | Per-platform sub-key list concatenation with deduplication                           |
| Composite              | `hooks`                             | `files`: concat + dedup by full path; `events`: concat (no dedup)                    |
| Deep dict              | `global-config`                     | `deep_merge_settings()` with no array union                                          |
| Deep dict              | `user-settings`                     | `deep_merge_settings()` with `permissions.*` array union                             |
| Shallow dict           | `env-variables`, `os-env-variables` | Shallow merge; child overrides; `null` deletes (RFC 7396)                            |

#### Non-Mergeable Keys

Keys not listed in the 12 mergeable keys (such as `name`, `model`, `permissions`, `command-defaults`) always use replace semantics, regardless of `merge-keys`.

#### Complete Merge Example

```yaml
# base.yaml
name: "Base Environment"
agents:
  - "agents/core-agent.md"
mcp-servers:
  - name: "context-server"
    transport: "http"
    url: "http://localhost:8000/mcp"
dependencies:
  common:
    - "uv tool install ruff"
```

```yaml
# child.yaml
inherit: "base.yaml"
merge-keys:
  - agents
  - mcp-servers
  - dependencies
name: "Extended Environment"  # Replaces (not in merge-keys)
agents:
  - "agents/extra-agent.md"  # Appended to parent's list
mcp-servers:
  - name: "context-server"   # Replaces parent's context-server in-position
    transport: "http"
    url: "http://localhost:9000/mcp"
  - name: "new-server"       # Appended (new identity)
    command: "npx @example/new-mcp"
dependencies:
  common:
    - "uv tool install ty"  # Appended to parent's common list
  linux:
    - "sudo apt-get install -y shellcheck"  # New platform
```

Result after merge:

- `name`: `"Extended Environment"` (replaced)
- `agents`: `["agents/core-agent.md", "agents/extra-agent.md"]` (merged)
- `mcp-servers`: context-server with updated URL at index 0, new-server appended (merged)
- `dependencies.common`: `["uv tool install ruff", "uv tool install ty"]` (merged)
- `dependencies.linux`: `["sudo apt-get install -y shellcheck"]` (new platform from child)

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

### Automatic Auto-Update Management

When `claude-code-version` specifies a pinned version (any value other than `"latest"` or absent), the setup script automatically injects auto-update disable controls into four targets to prevent Claude Code from overwriting the pinned version. When the version is `"latest"` or absent, any previously injected controls are automatically removed to re-enable auto-updates.

#### Injection Targets

| Target             | Key                       | Value   | On-disk file (isolated)                           | On-disk file (non-isolated)                         |
|--------------------|---------------------------|---------|---------------------------------------------------|-----------------------------------------------------|
| `global-config`    | `autoUpdates`             | `false` | `~/.claude/{cmd}/.claude.json` + `~/.claude.json` | `~/.claude.json`                                    |
| `user-settings`    | `env.DISABLE_AUTOUPDATER` | `"1"`   | `~/.claude/{cmd}/settings.json`                   | `~/.claude/settings.json`                           |
| `env-variables`    | `DISABLE_AUTOUPDATER`     | `"1"`   | `~/.claude/{cmd}/config.json` (`env` key)         | `~/.claude/settings.json` (`env` key, top-replace)  |
| `os-env-variables` | `DISABLE_AUTOUPDATER`     | `"1"`   | Shell profiles / Windows registry                 | Shell profiles / Windows registry                   |

All four targets are injected unconditionally regardless of whether `command-names` is present. In isolated mode (`command-names` present), `env-variables` reaches `~/.claude/{cmd}/config.json` via `create_profile_config()` (Step 18). In non-isolated mode (`command-names` absent), `env-variables` is routed directly to `~/.claude/settings.json['env']` via `write_profile_settings_to_settings()` (Step 18) using conditional top-level replace semantics. Both Target 2 (`user-settings.env.DISABLE_AUTOUPDATER`) and Target 3 (`env-variables.DISABLE_AUTOUPDATER`) therefore reach the same on-disk `settings.json['env']` container in non-isolated mode -- Target 2 via Step 14 `write_user_settings()` deep-merge, Target 3 via Step 18 top-level replace. When YAML has NO root-level `env-variables`, Step 18 omits `env` from its delta and the Target 2 Step 14 contribution SURVIVES Step 18's preservation invariant (see [Profile-Level Settings Routing](#profile-level-settings-routing)).

#### Removal Behavior

When the version is `"latest"` or absent:

- `autoUpdates` in `global-config` is set to `null` (RFC 7396 null-as-delete) only if the current value is `false`. User-set `true` values are left alone.
- `DISABLE_AUTOUPDATER` in `user-settings.env` is set to `null` for RFC 7396 null-as-delete (not `del`, because merge semantics require `None` to trigger removal from disk).
- `DISABLE_AUTOUPDATER` is removed from `env-variables` (using `del`, correct because `create_profile_config()` uses atomic overwrite) and `os-env-variables` (set to `None` for OS-level deletion).

**Write-remove symmetry:** After all write operations, `cleanup_stale_auto_update_controls()` runs as a filesystem sweep pass. When not pinned, it removes `DISABLE_AUTOUPDATER` from ALL `settings.json` files (`~/.claude/settings.json` and all `~/.claude/*/settings.json`) and removes `autoUpdates: false` from ALL `.claude.json` files (`~/.claude.json` and all `~/.claude/*/.claude.json`). When pinned, it only cleans `~/.claude/settings.json` to prevent bare sessions from inheriting isolated environment restrictions.

#### Conflict Resolution (WARN-but-Respect)

If the user explicitly sets a value in the YAML configuration that contradicts the automatic intent, the user value is preserved and a warning is emitted:

- **User value absent:** Auto-inject (proceed silently)
- **User value matches intent:** No-op (no warning)
- **User value contradicts intent:** Respect user value, emit warning. For example, if the user sets `autoUpdates: true` in `global-config` while pinning a specific version, the `true` value is preserved and a warning like `"User set global-config.autoUpdates to True (auto-update intent is False for pinned version). Respecting user value."` is displayed.

#### `[auto]` Marker in Installation Summary

Auto-injected values are displayed in the installation summary (including `--dry-run` output) with a green `[auto]` marker, similar to the existing `[?]` (unknown keys) and `[!]` (sensitive paths) markers. This makes it clear which values were automatically added by the setup script rather than explicitly configured in the YAML.

```text
Auto-injected settings (version pinning):
  [auto] global-config.autoUpdates: false
  [auto] user-settings.env.DISABLE_AUTOUPDATER: "1"
  [auto] env-variables.DISABLE_AUTOUPDATER: "1"
  [auto] os-env-variables.DISABLE_AUTOUPDATER: "1"
```

#### Defense-in-Depth

The `autoUpdates` key in `~/.claude.json` is considered deprecated by Anthropic (see [issue #3479](https://github.com/anthropics/claude-code/issues/3479)) and may stop working in future Claude Code releases. It is included as a defense-in-depth mechanism alongside the `DISABLE_AUTOUPDATER` environment variable, which is the primary auto-update control. The Claude Code auto-updater may also ignore disable settings in some versions (see issues [#10764](https://github.com/anthropics/claude-code/issues/10764), [#11263](https://github.com/anthropics/claude-code/issues/11263), [#12564](https://github.com/anthropics/claude-code/issues/12564)) -- covering all four targets provides the best protection.

### Automatic IDE Extension Version Management

When `claude-code-version` specifies a pinned version, the setup script also automatically disables IDE extension auto-installation and installs the matching extension version into detected VS Code family IDEs. When the version is `"latest"` or absent, any previously injected IDE extension controls are automatically removed.

This feature mirrors the [Automatic Auto-Update Management](#automatic-auto-update-management) architecture: same 4-target write matrix, same WARN-but-Respect conflict resolution, same write-remove symmetry cleanup.

#### Injection Targets

| Target             | Key                                     | Value   | On-disk file (isolated)                           | On-disk file (non-isolated)                         |
|--------------------|-----------------------------------------|---------|---------------------------------------------------|-----------------------------------------------------|
| `global-config`    | `autoInstallIdeExtension`               | `false` | `~/.claude/{cmd}/.claude.json` + `~/.claude.json` | `~/.claude.json`                                    |
| `user-settings`    | `env.CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL` | `"1"`   | `~/.claude/{cmd}/settings.json`                   | `~/.claude/settings.json`                           |
| `env-variables`    | `CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL`     | `"1"`   | `~/.claude/{cmd}/config.json` (`env` key)         | `~/.claude/settings.json` (`env` key, top-replace)  |
| `os-env-variables` | `CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL`     | `"1"`   | Shell profiles / Windows registry                 | Shell profiles / Windows registry                   |

All four targets are injected unconditionally regardless of whether `command-names` is present, consistent with auto-update management behavior. In non-isolated mode, `env-variables` reaches `~/.claude/settings.json['env']` via conditional top-level replace (identical routing to auto-update Target 3).

#### Removal Behavior

When the version is `"latest"` or absent:

- `autoInstallIdeExtension` in `global-config` is set to `null` (RFC 7396 null-as-delete) only if the current value is `false`. User-set `true` values are left alone.
- `CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL` in `user-settings.env` is set to `null` for RFC 7396 null-as-delete (not `del`, because merge semantics require `None` to trigger removal from disk).
- `CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL` is removed from `env-variables` (using `del`, correct because `create_profile_config()` uses atomic overwrite) and `os-env-variables` (set to `None` for OS-level deletion).

**Write-remove symmetry:** After all write operations, `cleanup_stale_ide_extension_controls()` runs alongside `cleanup_stale_auto_update_controls()` as a filesystem sweep pass. When not pinned, it removes `CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL` from ALL `settings.json` files and removes `autoInstallIdeExtension: false` from ALL `.claude.json` files. When pinned, it only cleans `~/.claude/settings.json` to prevent bare sessions from inheriting isolated environment restrictions.

#### Conflict Resolution (WARN-but-Respect)

Identical to auto-update management: if the user explicitly sets a value that contradicts the automatic intent, the user value is preserved and a warning is emitted.

#### `[auto]` Marker in Installation Summary

Auto-injected IDE extension values are displayed with the same green `[auto]` marker as auto-update values:

```text
Auto-injected settings (version pinning):
  [auto] global-config.autoInstallIdeExtension: false
  [auto] user-settings.env.CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL: "1"
  [auto] env-variables.CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL: "1"
  [auto] os-env-variables.CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL: "1"
```

#### VSIX Installation

When a version is pinned, the setup installs the matching Claude Code extension (`anthropic.claude-code`) into all detected VS Code family IDEs using a three-tier fallback chain:

1. **Tier 1 -- Bundled VSIX:** Check `~/.claude/local/node_modules/@anthropic-ai/claude-code/vendor/claude-code.vsix`. Validates file exists and `st_size > 1000` (same zero-byte guard as `verify_claude_installation()`). No network download needed.
2. **Tier 2 -- Marketplace CDN download:** Download the VSIX binary from the VS Code Marketplace CDN (primary URL with fallback). Downloaded to a temp file, installed via `--install-extension <path> --force`, then cleaned up.
3. **Tier 3 -- Marketplace @version syntax:** Use `anthropic.claude-code@{version}` syntax directly. Emits a warning because VS Code may auto-update the extension despite version pinning.

Installation is **non-fatal**: failures produce warnings but do not abort the setup.

#### VSIX Auto-Update Behavior

The three installation tiers have different auto-update implications for the installed extension:

| Tier   | Method               | Auto-Update Status                             |
|--------|----------------------|------------------------------------------------|
| Tier 1 | Bundled VSIX         | **Disabled by default** (VS Code v1.92+)       |
| Tier 2 | Downloaded VSIX      | **Disabled by default** (VS Code v1.92+)       |
| Tier 3 | Marketplace @version | **Active** -- VS Code may update the extension |

Since VS Code v1.92, extensions installed via VSIX files (Tiers 1 and 2) have auto-update disabled by default. This is the primary defense mechanism for version pinning -- the installed extension stays at the pinned version without any additional IDE-level configuration.

Tier 3 (marketplace @version syntax) is a last-resort fallback that only triggers when both the bundled VSIX is unavailable and the marketplace CDN download fails. In this case, VS Code may auto-update the extension despite version pinning. When Tier 3 is used, the setup emits a warning with instructions to manually disable auto-update for the extension:

> In VS Code's Extensions view, right-click the Claude Code extension and set "Auto Update" to off.

This per-extension "Auto Update" toggle is the only targeted control available. There is no `settings.json` key for per-extension auto-update exceptions -- the only JSON setting (`extensions.autoUpdate: false`) disables auto-update for ALL extensions, which is too broad.

**JetBrains IDEs:** JetBrains IDEs use their own plugin ecosystem and do not support VSIX extensions. The Claude Code JetBrains plugin is versioned independently from the CLI, and there is no external mechanism to control per-plugin auto-update from outside the IDE. The existing `autoInstallIdeExtension: false` control is the only applicable protection for JetBrains.

#### VS Code Family IDE Detection

IDEs are detected via `shutil.which()` for each CLI name: `code`, `code-insiders`, `cursor`, `windsurf`, `codium`. The extension is installed into all detected IDEs. If no IDEs are detected, the step is a silent no-op.

JetBrains IDEs are excluded because they use their own plugin ecosystem and do not support VSIX extensions.

#### Process Environment Early-Set

When a version is pinned, `CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL=1` is set in the process environment before Step 1 (Claude Code installation). This prevents the Claude Code CLI from auto-installing IDE extensions during the installation process itself.

### Configuration Sources

The setup script determines the configuration source by checking in this order:

1. **URL:** Starts with `http://` or `https://` -- fetched directly from the web
2. **Local file:** Contains path separators (`/`, `\`), starts with `./` or `../`, is an absolute path, or the file exists on disk -- loaded from the local filesystem
3. **Repository config:** Everything else -- `.yaml` is added if missing, then fetched from `https://raw.githubusercontent.com/alex-feel/claude-code-artifacts-public/main/{name}.yaml`

### Cross-Shell Command Registration (Windows)

On Windows, the setup creates global commands that work across all shells (PowerShell, CMD, Git Bash) through a set of launcher and wrapper scripts:

- Shared POSIX launcher (`~/.claude/{command}/launch.sh`) -- the actual launcher executed by Git Bash
- PowerShell wrapper (`~/.claude/{command}/start.ps1`) -- invokes launch.sh via Git Bash
- CMD wrapper (`~/.claude/{command}/start.cmd`) -- invokes launch.sh via Git Bash
- Global wrappers in `~/.local/bin/` (`{command}`, `{command}.ps1`, `{command}.cmd`) -- entry points that delegate to the above

For the full technical architecture, see [Cross-Shell Launcher Architecture](cross-shell-launcher-architecture.md).

## What Happens When You Run Setup

Here is a conceptual overview of what the setup script does when you run it with a configuration:

1. **Install Claude Code** -- Uses the native installer with npm fallback. Skipped with `--skip-install`.
2. **Install IDE extensions** -- Installs the pinned-version Claude Code extension into detected VS Code family IDEs. Skipped if no version is pinned or `--skip-install` is used.
3. **Create directories** -- Creates `~/.claude/agents/`, `commands/`, `rules/`, `prompts/`, `hooks/`, and `skills/` directories.
4. **Download custom files** -- Processes `files-to-download` entries.
5. **Install Node.js** -- If `install-nodejs: true` is set in the config.
6. **Install dependencies** -- Runs platform-specific dependency commands.
7. **Set OS environment variables** -- Writes persistent environment variables from `os-env-variables`. Generates env loader files (`env.sh`, `env.fish`, `env.ps1`, `env.cmd`) for launcher auto-sourcing.
8. **Process agents** -- Downloads agent Markdown files to `~/.claude/agents/`.
9. **Process slash commands** -- Downloads command files to `~/.claude/commands/`.
10. **Process rules** -- Downloads rule Markdown files to `~/.claude/rules/`.
11. **Process skills** -- Downloads skill file sets to `~/.claude/skills/{name}/`.
12. **Process system prompt** -- Downloads the prompt file if configured.
13. **Configure MCP servers** -- Sets up MCP servers with scope-based routing.
14. **Write user settings** -- Merges `user-settings` into `~/.claude/settings.json`.
15. **Write global config** -- Merges `global-config` into `~/.claude.json`.
16. **Cleanup stale controls** -- Sweeps all filesystem locations for stale auto-update and IDE extension artifacts from prior configurations.
17. **Download hooks** -- Downloads hook script files to `~/.claude/{cmd}/hooks/` (with `command-names`) or `~/.claude/hooks/` (without). In non-command-names mode, Step 17 runs when ANY of the following are declared: `hooks.events` non-empty, `hooks.files` non-empty, or `status-line.file` set.
18. **Write profile settings** -- Writes all nine profile-owned keys (`model`, `permissions`, `env`, `attribution`, `alwaysThinkingEnabled`, `effortLevel`, `companyAnnouncements`, `statusLine`, `hooks`) as camelCase keys on disk. With `command-names`: writes to `~/.claude/{cmd}/config.json` via `create_profile_config()` (atomic overwrite -- fresh dict each run). Without `command-names`: writes to `~/.claude/settings.json` via `write_profile_settings_to_settings()` using **conditional top-level replace semantics** (preserves non-delta keys; see [Profile-Level Settings Routing](#profile-level-settings-routing)).
19. **Write manifest** -- Creates an installation tracking manifest. (Only if `command-names` is specified.)
20. **Create launcher** -- Creates the launcher script for the command. (Only if `command-names` is specified.)
21. **Register commands** -- Creates global command wrappers. (Only if `command-names` is specified.)

Step 17 is skipped if no hooks, hook files, or status-line file are configured. Step 18 is a no-op if the profile delta is empty (no profile-owned keys declared at YAML root level). Steps 19-21 are skipped if `command-names` is not specified.

## Profile-Level Settings Routing

The setup script supports two modes of profile-settings routing, controlled by the presence of `command-names:` in the YAML configuration. This section documents how the nine profile-owned keys land on disk in each mode and how they interact with `user-settings:`.

### Profile-Owned Keys

Nine YAML root-level keys are **profile-owned** -- they are written to disk by the profile-settings subsystem (`_build_profile_settings()` builder + one of two writers):

| YAML root key (kebab-case)    | On-disk key (camelCase)   |
|-------------------------------|---------------------------|
| `model`                       | `model`                   |
| `permissions`                 | `permissions`             |
| `env-variables`               | `env`                     |
| `attribution`                 | `attribution`             |
| `always-thinking-enabled`     | `alwaysThinkingEnabled`   |
| `effort-level`                | `effortLevel`             |
| `company-announcements`       | `companyAnnouncements`    |
| `status-line`                 | `statusLine`              |
| `hooks`                       | `hooks`                   |

The shared pure builder `_build_profile_settings()` performs kebab-to-camel translation and delegates to `_build_hooks_json()` for the `hooks` universe. The 9-key set is declared as `PROFILE_OWNED_KEYS` (a `frozenset`) in `scripts/setup_environment.py`. These keys are distinct from `USER_SETTINGS_EXCLUDED_KEYS = {'hooks', 'statusLine'}`, which is NOT extended to cover all 9 profile-owned keys -- `user-settings` remains a free-form pass-through for forward compatibility (see [Relationship to Profile-Owned Keys](#relationship-to-profile-owned-keys)).

### Isolated Mode (command-names present)

When `command-names` is specified, the setup creates an isolated directory `~/.claude/{cmd}/` containing:

| File            | Priority (CLI)   | Content                                                 | Writer                    | Step | Semantics                                                                         |
|-----------------|------------------|---------------------------------------------------------|---------------------------|------|-----------------------------------------------------------------------------------|
| `settings.json` | 5 (userSettings) | YAML `user-settings:` (all non-excluded keys)           | `write_user_settings()`   | 14   | Deep merge + array-union (`permissions.allow/deny/ask`) + RFC 7396 null-as-delete |
| `config.json`   | 2 (flagSettings) | 9 `PROFILE_OWNED_KEYS` from YAML root                   | `create_profile_config()` | 18   | Atomic overwrite (fresh dict each run)                                            |

The launcher script passes `config.json` via the `--settings` flag and sets `CLAUDE_CONFIG_DIR` to the isolated directory. Claude Code CLI's native priority resolution (`flagSettings (2) > userSettings (5)`) ensures `config.json` wins over `settings.json` for overlapping keys at runtime. In isolated mode, stale-key accumulation is NOT a concern because `create_profile_config()` uses atomic overwrite: every run produces a fresh `config.json` containing only the currently-declared keys, so removing a key from YAML cleanly removes it from `config.json` on the next run.

### Non-Isolated Mode (command-names absent)

When `command-names` is ABSENT, the setup writes to the shared `~/.claude/` directory. BOTH Step 14 and Step 18 target the SAME file (`~/.claude/settings.json`) but with strict step ordering and distinct merge semantics:

| File                       | Content                                            | Writer                                  | Step | Semantics                                              |
|----------------------------|----------------------------------------------------|-----------------------------------------|------|--------------------------------------------------------|
| `~/.claude/settings.json`  | YAML `user-settings:` (all non-excluded keys)      | `write_user_settings()`                 | 14   | Deep merge + array-union + RFC 7396 null-as-delete     |
| `~/.claude/settings.json`  | 9 `PROFILE_OWNED_KEYS` delta from YAML root        | `write_profile_settings_to_settings()`  | 18   | Conditional top-level replace                          |

1. **Step 14** deep-merges `user-settings:` into `settings.json`. Existing keys are preserved; merged keys are overridden by the new YAML values; `permissions.allow/deny/ask` arrays are unioned with deduplication; `null` values delete keys via RFC 7396.
2. **Step 18** applies the profile delta: for each key in the builder delta, REPLACE the entire top-level key value (or DELETE if explicitly `None`). Keys NOT in the delta are PRESERVED.

This preserves the Step 14 contributions (and any user-managed keys outside the YAML) and ensures the shared `settings.json` is never scrubbed of keys the current YAML does not declare.

### Write Semantics Contract

**Design principle:** `~/.claude/settings.json` is a SHARED/COMMON user-facing file, NOT an isolated profile. The toolbox must NOT scrub or delete existing keys merely because the YAML does not declare them. Unexpected deletion of settings the user did not intend to remove is explicitly prohibited.

`write_profile_settings_to_settings()` implements three branches for each key in the profile delta:

| Branch | YAML root state                         | Builder delta   | On-disk effect                                                          |
|--------|-----------------------------------------|-----------------|-------------------------------------------------------------------------|
| 1      | Key present with non-null value         | `{key: value}`  | **REPLACE** entire top-level value (no deep merge, no array-union)      |
| 2      | Key present with explicit `null` value  | `{key: None}`   | **DELETE** key from file (RFC 7396 null-as-delete via `existing.pop()`) |
| 3      | Key absent from YAML root               | `{}` (omitted)  | **PRESERVE** existing value unchanged                                   |

The builder `_build_profile_settings()` OMITS `None` inputs from its returned dict by default -- this means that when you OMIT a key from YAML, it is not represented in the delta at all (branch 3, preserve). To trigger branch 2 (explicit delete), construct the delta directly in code or -- at the YAML level -- set the key to `null` (the merge/validation layers translate this to an explicit `None` passed to the writer for the profile-owned keys that support it).

**Preservation coverage (what survives profile-settings writes):**

Keys NOT present in the delta are preserved in `~/.claude/settings.json`. This covers:

- Prior-run contributions from `write_profile_settings_to_settings()` itself.
- Deep-merged contributions from Step 14 `write_user_settings()` (including `user-settings.permissions.allow/deny/ask` array-unions and any free-form `user-settings` keys).
- User-managed keys outside the toolbox's YAML schema (e.g., `includeGitInstructions`, `apiKeyHelper`, `cleanupPeriodDays`, `outputStyle`, `autoMemoryDirectory`, `sandbox.*`).
- Auto-injected `env.DISABLE_AUTOUPDATER` (auto-update Target 2) and `env.CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL` (IDE extension Target 2) controls written via `user-settings.env` when YAML has no root-level `env-variables`. In that case, Step 18's builder omits `env` entirely from the delta, and the Step 14 contributions SURVIVE.

**Empty-delta no-op:** If no profile-owned keys are declared at YAML root level, the builder returns `{}` and `write_profile_settings_to_settings()` performs ZERO file I/O -- it neither creates nor touches `~/.claude/settings.json`. A YAML with only `user-settings:`, `global-config:`, `agents:`, etc. will never have Step 18 modify `settings.json`.

**Malformed or non-dict existing content:** If `~/.claude/settings.json` contains invalid JSON, unreadable content, or a non-dict top-level value (e.g., a bare list), the writer emits a warning (`"Existing ... is not a dict, starting fresh"` or `"Invalid JSON in ..."`) and starts fresh (treats `existing` as `{}`). The written file ends with a trailing newline for file-format consistency with `write_hooks_to_settings()`.

### Deferred Stale-Key Behavior (User-Facing Contract)

This is an INTENTIONAL user-facing contract, not a bug. Understanding this behavior is critical to using `command-names`-absent mode correctly.

**Scenario:** You had `permissions: {allow: [Read]}` at YAML root in a previous setup run. You then remove the entire `permissions` block from your YAML and re-run setup.

**Result:** The `permissions` key in `~/.claude/settings.json` RETAINS its previous value (`{allow: [Read]}`). It is NOT deleted.

**Why:** `~/.claude/settings.json` is a shared file. Removing a key from YAML is NOT a sufficient signal for the toolbox to delete that key from the shared file, because:

1. The key might have been set by a previous toolbox run with a different YAML.
2. The key might have been set manually by the user or by another tool.
3. The key might have been set by a teammate's YAML that is managed separately.
4. The profile-settings writer has no state-tracking sidecar to distinguish keys it wrote in prior runs from user-managed keys.

**To remove a key, you have two explicit options:**

1. **Set the key to `null` in YAML.** Examples:
   ```yaml
   permissions: null        # Delete entire permissions block from settings.json
   model: null              # Delete model key
   hooks: null              # Delete hooks block (but see note below)
   env-variables: null      # Delete env block from settings.json
   ```
2. **Manually delete the key** from `~/.claude/settings.json` using a text editor.

Automated YAML-removal-triggered cleanup (a state-tracking sidecar approach, e.g., `~/.claude/toolbox-managed-keys.json` recording which keys the toolbox wrote in the last run) is not implemented. The preservation behavior is the intended design.

**Security implication for `permissions.deny`:** If you previously declared `permissions.deny: ['Bash(rm -rf)']` at YAML root and then remove `permissions:` from YAML, the deny rule REMAINS in `~/.claude/settings.json`. This is the INTENDED behavior: removing security rules from YAML should NOT silently remove them from the shared file. If you want to remove deny rules, you must either explicitly set `permissions: {deny: []}` or `permissions: null`, or edit the file manually.

**Note on `hooks` deletion:** Because Step 18 performs top-level replace, setting `hooks: null` at YAML root deletes the entire `hooks` key. Removing individual hook entries requires re-declaring the full `hooks` block with the entries you want to keep.

### Profile-Scoped MCP Servers in Non-Command-Names Mode (ERROR)

Profile-scoped MCP servers (`scope: profile` or `scope: [user, profile]`) CANNOT work without `command-names` because the launcher script that consumes `--mcp-config` is only created in isolated mode. In non-isolated mode, profile-scoped servers would have no launcher target and would be silently dropped at runtime -- a correctness risk.

The setup script enforces this with a hard validation error (exit 1) at the validation phase, BEFORE any side effects (downloads, writes) occur:

```text
[ERROR] MCP server 'my-server' declares scope: profile but command-names is not specified.
[ERROR] Profile-scoped MCP servers require a launcher script with --mcp-config flag, which
[ERROR] is only created when command-names is present in your YAML configuration.
[ERROR]
[ERROR] Fix one of:
[ERROR]   1. Add "command-names: [your-name]" to enable isolated environment (preferred)
[ERROR]   2. Change scope to "user" to install globally via ~/.claude.json
[ERROR]   3. Change scope to "local" to install in project-specific .mcp.json
[ERROR]   4. Change scope to "project" to install in shared project .mcp.json
```

The validation walks `config.get('mcp-servers', [])` and matches BOTH the string form (`scope: profile`) AND the list form (`scope: [user, profile]`) -- a combined `[user, profile]` scope without `command-names` also triggers the error because the `profile` portion of the list has no launcher target. Error output is written to `sys.stderr` (not stdout).

### `command-defaults.system-prompt` in Non-Command-Names Mode (WARNING)

System prompts are applied by the launcher via `--system-prompt` or `--append-system-prompt` CLI flags. Without `command-names`, there is no launcher, so the prompt file cannot be passed to Claude at runtime. The setup script emits a non-fatal WARNING (setup continues):

```text
[WARN] command-defaults.system-prompt is set to 'prompts/my-prompt.md' but command-names is not specified.
[WARN] System prompts are applied by the launcher; without command-names there is no launcher,
[WARN] so the system prompt will NOT be applied.
[WARN] Add 'command-names: [your-name]' to enable isolated environment with launcher-based system prompt injection.
```

Unlike profile-scoped MCP servers (which are a hard error because silently-dropped servers are a correctness risk), a silently-unused system prompt file is merely a configuration mistake -- a warning is sufficient. Warning output is written to stdout.

### Conflict Detection

`detect_settings_conflicts()` runs UNCONDITIONALLY in BOTH modes (isolated and non-isolated). If you declare a profile-owned key under BOTH `user-settings:` AND at YAML root level, a warning is emitted during the validation phase:

```text
[WARN] Key 'model' specified in both root level and user-settings.
[WARN]   user-settings value: claude-opus-4
[WARN]   root-level value: claude-sonnet-4
[WARN]   Root-level value takes precedence (written last in Step 18).
```

**Why root-level wins (in both modes):**

- **Isolated mode:** Step 14 writes `user-settings:` to `~/.claude/{cmd}/settings.json` (priority 5), Step 18 writes the profile delta to `~/.claude/{cmd}/config.json` (priority 2). The CLI's native `flagSettings > userSettings` resolution means `config.json` wins at runtime.
- **Non-isolated mode:** Step 14 writes `user-settings:` to `~/.claude/settings.json` via deep-merge, Step 18 writes the profile delta to the SAME file via top-level replace. Step 18 writes last, so its REPLACE overwrites the Step 14 merge result for the overlapping profile-owned key.

The conflict warning ensures users are informed regardless of which mode they use.

### Three-Writer Architectural Model Summary

| Writer                                 | YAML Source                  | Target                                                       | Key Universe                              | Semantics                                                                          | Step                |
|----------------------------------------|------------------------------|--------------------------------------------------------------|-------------------------------------------|------------------------------------------------------------------------------------|---------------------|
| `write_user_settings()`                | `user-settings:`             | `~/.claude/settings.json` OR `~/.claude/{cmd}/settings.json` | ~58 non-excluded CLI keys                 | Deep merge + array-union (`permissions.allow/deny/ask`) + RFC 7396 null-as-delete  | 14                  |
| `create_profile_config()`              | YAML root profile keys       | `~/.claude/{cmd}/config.json`                                | 9 `PROFILE_OWNED_KEYS`                    | Atomic overwrite (fresh dict each run)                                             | 18 (isolated)       |
| `write_profile_settings_to_settings()` | YAML root profile keys       | `~/.claude/settings.json`                                    | 9 `PROFILE_OWNED_KEYS` delta              | Conditional top-level replace                                                      | 18 (non-isolated)   |

Both Step 18 writers are fed by the shared pure builder `_build_profile_settings()`, which translates kebab-case YAML keys to camelCase JSON keys and delegates to `_build_hooks_json()` for hook events. `create_profile_config()` is a thin wrapper that delegates to the pure builder and atomically writes `config.json`; its output dict is identical to what the builder returns for the same inputs.

## Complete Annotated Example

A realistic configuration demonstrating most keys:

```yaml
# Python Development Environment Configuration
name: "Python Development"
version: "1.0.0"

description: |
  Full-featured Python environment with linting, type checking,
  and AI-powered MCP servers pre-configured.

post-install-notes: |
  Next steps:
  1. Run: claude-python
  2. Try: /help to see available commands

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
    - "uv tool install ty"
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

# User-scope rules (placed in ~/.claude/rules/)
rules:
  - "rules/coding-standards.md"

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
  default-mode: "default"
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

# Hooks for code quality and safety
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
    - event: "PreToolUse"
      matcher: "Bash"
      type: "prompt"
      prompt: "Check if this bash command is safe to execute"
      timeout: 30
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

The `global-config` key blocks non-null `oauthAccount` values to prevent OAuth credentials from appearing in YAML configuration files. Setting `oauthAccount: null` is allowed to support clearing authentication state (useful for account switching and auth recovery).

### Installation Confirmation

By default, the setup requires explicit confirmation before installing. Use `--dry-run` to preview the installation plan without making changes. Unknown configuration keys are flagged with `[?]` in the installation summary to help you identify potential typos or unsupported keys.
