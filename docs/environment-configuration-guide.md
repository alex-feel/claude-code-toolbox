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

Run a single command that sets your configuration source and executes the setup. The CLI and the platform bootstrap commands accept the same configuration sources, environment variables, and flags -- pick whichever fits, the behavior is identical.

### CLI (Any Platform)

With [uv](https://docs.astral.sh/uv/) installed, `uvx cc-toolbox setup` runs the setup on every platform with one identical syntax. The config is the positional argument; every documented environment variable can also be set inline with the repeatable `--env` flag:

```bash
# Public config URL
uvx cc-toolbox setup https://raw.githubusercontent.com/org/repo/main/config.yaml

# Local file
uvx cc-toolbox setup ./my-env.yaml

# Private GitLab repository
uvx cc-toolbox setup https://gitlab.company.com/namespace/project/-/raw/main/config.yaml --env GITLAB_TOKEN=glpat-<your-token>

# Private GitHub repository
uvx cc-toolbox setup https://raw.githubusercontent.com/org/repo/main/config.yaml --env GITHUB_TOKEN=ghp_<your-token>

# Config pulling from both hosts, fully non-interactive
uvx cc-toolbox setup https://raw.githubusercontent.com/org/repo/main/config.yaml --env GITHUB_TOKEN=ghp_<your-token> --env GITLAB_TOKEN=glpat-<your-token> --yes
```

Regular environment variables (`export GITHUB_TOKEN=...`, `$env:GITHUB_TOKEN='...'`) work with the CLI exactly as they do with the bootstrap scripts, including `CLAUDE_CODE_TOOLBOX_ENV_CONFIG` in place of the positional argument. Values passed with `--env` appear in shell history and the process list; prefer regular environment variables for secrets when that matters.

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

The full flag reference lives in [CLI Flags and Environment Variable Equivalents](#cli-flags-and-environment-variable-equivalents). Flags work identically for `uvx cc-toolbox setup`, direct script runs, and the bootstrap wrappers, which forward all arguments to the setup script verbatim.

> **Important:** `iex (irm ...)` on Windows accepts no arguments, so with that invocation pass options via environment variables (or use the CLI). On Linux/macOS, `curl ... | bash -s -- <config> --yes` passes flags through the pipe.

## Ready-Made Configurations

The [claude-code-artifacts-public](https://github.com/alex-feel/claude-code-artifacts-public) repository contains ready-made environment configurations that you can use directly.

To install a configuration from that repository, use its full raw URL as the config source:

### CLI (Any Platform)

```bash
uvx cc-toolbox setup https://raw.githubusercontent.com/alex-feel/claude-code-artifacts-public/main/environments/templates/basic-template.yaml
```

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
| [`command-names`](#command-names)                     | `list[str]`            | No       | `[]`    | Command names and aliases                                  |
| [`base-url`](#base-url)                               | `str`                  | No       | `None`  | Base URL for relative resource paths                       |
| [`claude-code-version`](#claude-code-version)         | `str`                  | No       | `None`  | Specific Claude Code version or `"latest"`                 |
| [`install-nodejs`](#install-nodejs)                   | `bool`                 | No       | `None`  | Install Node.js LTS before dependencies                    |
| [`link-dirs`](#link-dirs)                             | `list[str]`            | No       | `None`  | Profile entries taken through a link from another profile  |
| [`link-from`](#link-from)                             | `str`                  | No       | `base`  | The profile the linked entries come from                   |
| [`dependencies`](#dependencies)                       | `dict`                 | No       | `{}`    | Platform-specific dependency commands                      |
| [`agents`](#agents)                                   | `list[str]`            | No       | `[]`    | Agent markdown file paths                                  |
| [`slash-commands`](#slash-commands)                   | `list[str]`            | No       | `[]`    | Slash command file paths                                   |
| [`rules`](#rules)                                     | `list[str]`            | No       | `[]`    | Rule markdown file paths (user-scope)                      |
| [`skills`](#skills)                                   | `list[Skill]`          | No       | `[]`    | Skill configurations                                       |
| [`files-to-download`](#files-to-download)             | `list[FileToDownload]` | No       | `[]`    | Files to download during setup                             |
| [`global-config`](#global-config)                     | `GlobalConfig`         | No       | `None`  | Raw `~/.claude.json` content (camelCase keys)              |
| [`hooks`](#hooks)                                     | `Hooks`                | No       | `None`  | Hook configurations (files, helpers, and events)           |
| [`mcp-servers`](#mcp-servers)                         | `list[dict]`           | No       | `[]`    | MCP server configurations                                  |
| [`components`](#components)                           | `list[Component]`      | No       | `[]`    | Author-defined selectable component groups                 |
| [`os-env-variables`](#os-env-variables)               | `dict`                 | No       | `None`  | OS-level persistent environment variables                  |
| [`command-defaults`](#command-defaults)               | `CommandDefaults`      | No       | `None`  | System prompt and mode                                     |
| [`user-settings`](#user-settings)                     | `UserSettings`         | No       | `None`  | Raw `settings.json` content (camelCase keys)               |
| [`status-line`](#status-line)                         | `StatusLine`           | No       | `None`  | Status line script configuration                           |

> `link-dirs` needs an isolated profile: links live inside `~/.claude/NAME`, so a run without `command-names` (or `--command-names`) that declares `link-dirs` stops with an error naming the flag to add. `link-from` is read only together with `link-dirs`.

### Configuration key naming

All configuration keys use **kebab-case** (hyphenated lowercase), for example `mcp-servers`, `os-env-variables`, `files-to-download`. Using underscores (`os_env_variables`, `mcp_servers`) will cause the key to be flagged as unknown during installation.

**Sub-key naming conventions:**

- **Top-level keys** (`hooks`, `mcp-servers`, `status-line`, etc.): MUST be kebab-case (validated by `KNOWN_CONFIG_KEYS`)
- **Sub-keys in structured sections** (`hooks.events[]`): MUST be kebab-case (the toolbox translates to camelCase for Claude Code JSON output)
- **Sub-keys in free-form sections** (`user-settings`, `global-config`): MUST match Claude Code's native camelCase (pass-through, no translation)

> **Note:** The Pydantic validation model (`EnvironmentConfig`) uses `populate_by_name=True` for testing convenience, which means CI validation accepts both `os_env_variables` and `os-env-variables`. However, the runtime setup script (`setup_environment.py`) uses `config.get('os-env-variables')` and will not recognize underscore variants. Always use kebab-case in your configuration files.

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

Configuration version. Setup records it as `version` in the manifest of the profile it installs: `~/.claude/manifest.json` for a base install and `~/.claude/{cmd}/manifest.json` for an isolated one.

- **Type:** `str | None`
- **Default:** `None`
- **Validation:** Must be valid semver (`X.Y.Z` format, with optional pre-release and build metadata). Valid with or without `command-names`.
- **Inheritance:** Not inherited. Extracted from the root config before inheritance resolution.
- **Example:** `version: "1.0.0"` or `version: "2.1.0-beta.1"`

#### `command-names`

Creates global shell commands that launch Claude Code with this environment configuration. The first name is the primary command and names the isolated profile directory `~/.claude/<primary>`; the remaining entries are aliases.

- **Type:** `list[str] | None`
- **Default:** `[]`
- **Validation:**
  - Cannot be empty or whitespace-only
  - Cannot contain spaces
  - Must be alphanumeric, hyphens, and underscores only
  - Cannot be a reserved name, compared without regard to case: `none`, `base`, `all`, `skills`, `agents`, `commands`, `rules`, `hooks`, `output-styles`, `prompts`, `projects`
- **Inheritance:** Standard override (child replaces parent)
- **Note:** If no command names are given (neither here nor through `--command-names`), hooks are written to `~/.claude/settings.json` (global scope) instead of a per-environment `config.json`. Step 19 still writes the base profile's manifest, `~/.claude/manifest.json`, with `name` as `null` and an empty `command_names` list (see [Profile manifests](#profile-manifests)); setup skips only launcher creation and command registration (Steps 20-21). The setup still processes other resources (agents, MCP servers, dependencies, and so on) but does not create a launchable command.
- **Example:**

```yaml
command-names:
  - "my-env"       # Primary (used for file names)
  - "my-env-alias" # Alias
```

##### Choosing the command names at install time

`--command-names NAME[,ALIAS...]` (environment variable `CLAUDE_CODE_TOOLBOX_COMMAND_NAMES`) sets the command names of one run, and it works with every configuration. A configuration without `command-names` becomes the isolated profile `~/.claude/NAME` instead of a base install. A configuration with `command-names` installs under the names you give in place of its own. The value replaces the configuration's list whole and never merges with it: `NAME,ALIAS...` sets the aliases, `NAME,none` drops every alias, and a single `NAME` on a new profile is the complete list, with none of the configuration's aliases. A single `NAME` on a profile that is already installed selects that profile and leaves its aliases to the ranking in [Re-running a profile](#re-running-a-profile). The flag wins over the variable, and the variable wins over the configuration. Every source goes through the same validation and reserved names, and setup stops before writing anything when a name fails.

```bash
# One configuration, several isolated profiles
uvx cc-toolbox setup my-env.yaml --command-names my-env-1
uvx cc-toolbox setup my-env.yaml --command-names my-env-2

# A second profile from a configuration that declares its own names: one command, my-profile-2
uvx cc-toolbox setup my-profile.yaml --command-names my-profile-2
```

```powershell
# Windows one-liner: iex (irm ...) takes no arguments, so use the variable
$env:CLAUDE_CODE_TOOLBOX_ENV_CONFIG='https://raw.githubusercontent.com/org/repo/main/config.yaml'; $env:CLAUDE_CODE_TOOLBOX_COMMAND_NAMES='my-env-2'; iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')
```

Setup places these sections into `~/.claude/NAME` itself: agents, slash commands, rules, skills, the system prompt, hook files and their [`hooks.helpers`](#hook-helpers), the launchers, `config.json`, and the profile manifest. A [`files-to-download`](#files-to-download) destination, a [`dependencies`](#dependencies) command, or an `apiKeyHelper` that names the base `~/.claude` is re-rooted into the profile as well; see [Paths that name the base config home](#paths-that-name-the-base-config-home). Dependency commands also see `CLAUDE_CONFIG_DIR` set to the profile directory. A module that hook scripts import from their own directory belongs in `hooks.helpers`, which follows the scripts into the profile in both modes.

##### Paths that name the base config home

A configuration written for the base profile spells its paths against `~/.claude`: it downloads `CLAUDE.md` or a `scripts/` helper to `~/.claude/...`, runs a cleanup line such as `rm -rf "$HOME/.claude/statsig"` or `Remove-Item "$env:USERPROFILE\.claude\statsig"`, and points `apiKeyHelper` at `~/.claude/scripts/...`. Installed with `--command-names`, every such path moves into the profile directory, so the same file installs as the base profile and as any number of isolated profiles without a second copy of the configuration. In an isolated run setup rewrites:

- every `files-to-download` destination,
- every `dependencies` command, in every platform list,
- the `apiKeyHelper` and `awsCredentialExport` values of `user-settings`, before the Windows tilde expansion,

whenever the path names the base config home in any spelling (`~/.claude`, `$HOME/.claude`, `${HOME}/.claude`, `"$HOME"/.claude`, `$env:USERPROFILE\.claude`, `%USERPROFILE%\.claude`, with forward or back slashes) or one of the `~/.claude.json` siblings (`~/.claude.json`, `~/.claude.json.backup`, `~/.claude.json.corrupted.*`). The rewrite keeps the author's home token and separator and inserts the profile below `.claude`: `~/.claude/CLAUDE.md` becomes `~/.claude/NAME/CLAUDE.md`, `rm -rf "$HOME/.claude/statsig"` becomes `rm -rf "$HOME/.claude/NAME/statsig"`, `$env:USERPROFILE\.claude\statsig` becomes `$env:USERPROFILE\.claude\NAME\statsig`, and `~/.claude.json.backup` becomes `~/.claude/NAME/.claude.json.backup`. A profile relocated by a [`CLAUDE_CONFIG_DIR` override](#claude_config_dir-override-isolated-mode) receives the same paths under its own directory, spelled relative to the home when it lies below the home and absolute otherwise.

Three kinds of path stay as written: one that names another installed profile's directory (`~/.claude/other-profile/...`), one that already names this profile's directory, and one outside the config home (`~/.serena/...`, `~/.config/...`). A base run rewrites nothing.

The installation summary and `--dry-run` list every rewritten item under `Re-rooted into the profile`, one `[re-rooted]` row per destination, command or settings value with its original and its rewritten path, and the `Dependencies (shell commands)` block marks each rewritten command the same way. A re-rooted destination lies inside the profile, so it is recorded in the manifest's `files_written`, never in `machine_wide_destinations`, and it has no `Machine-wide writes` row; a re-rooted dependency command keeps the `Dependency commands` row there, because it runs on the machine and can write anywhere. Deselecting a component removes the file at its re-rooted path, so the base profile's copy of the same file survives; the `[REMOVE]` row names the re-rooted path. `resolved-config.yaml` keeps the paths as the configuration spells them, so a re-run of the profile, by configuration or by `--profile`, rewrites them again for that profile.

A profile that links content from a source (see [Linked Profiles](#linked-profiles)) re-roots the same paths, and a destination that then lies inside a linked entry is provided by the link: `~/.claude/hooks/project-overrides/x.yaml` becomes `~/.claude/NAME/hooks/project-overrides/x.yaml`, which is the source's `hooks/` seen through the link, and the source's run wrote the file there. The dependent's run downloads nothing for it, leaves it out of its manifest's `files_written`, keeps its `[re-rooted]` row, and lists it under `Provided by links`, one `[linked]` row per destination naming the entry and the source profile (`~/.claude/NAME/hooks/project-overrides/x.yaml: hooks/ is linked from profile "SOURCE"`), in the installation summary and in `--dry-run`; Step 4 prints `Skipping` with the same text, and `Files to download` counts only the files the run writes. A destination outside every linked entry (`~/.claude/x.txt`) lands in the dependent's own profile as before, a re-rooted dependency command runs as before, and a profile that links only `projects` writes everything it re-roots into its own directories. A deselected entry inside a linked entry is left alone the same way, and the Step 23 refresh a source run starts applies all of this to each dependent again.

The installation summary and the completion summary both mark where the names came from: `Command names: my-env-1 [cli]` before the run and `Global command: my-env-1 registered [cli]` after it for the flag, `[env]` for the variable, `[yaml]` for the configuration. Under `--yes` nobody reviews the installation summary, so the completion summary is where a leftover `CLAUDE_CODE_TOOLBOX_COMMAND_NAMES` shows up. When the configuration defines components, the installation summary's `Replay:` line carries `--command-names` for names from the flag or the variable, so a replay installs the same profile.

##### Names another profile or program holds

Setup registers each command name as a wrapper in `~/.local/bin`, so before it writes anything (and in `--dry-run` too) it refuses a name that is already taken, whatever source the name came from:

- **Another profile's name.** Every isolated profile lists its names in `~/.claude/<primary>/manifest.json`. A name another profile lists is refused with the owning profile and its manifest in the message. To move an alias to a new profile, re-run the owning profile with a `--command-names` list that leaves the alias out (or `NAME,none` to drop every alias), then install the new profile. A re-run of the profile that owns the names keeps working, and a re-run that drops some of its aliases removes their wrappers from `~/.local/bin`, so the names are free again.
- **A program in `~/.local/bin`.** A file there under the name that setup did not create, such as the native Claude Code link `claude`, is refused with its path. On Windows, `name.exe`, `name.bat` and `name.com` count too, because the shells run them for the bare name. Choose another name, or move the file away if you no longer need it.

Setup compares a name with other profiles' names without regard to case, because Windows and macOS map both spellings onto the same wrapper files.

##### Re-running a profile

An update is the install command run again, and the primary name alone is enough. Three forms re-run an installed profile, and all three perform the whole install: the Claude Code binary (upgraded unless an installed profile pins a version), the dependency commands, the profile's content, its MCP registrations and settings:

```bash
uvx cc-toolbox setup my-env.yaml --command-names my-env-1   # by configuration plus the primary name
uvx cc-toolbox setup --profile my-env-1                      # by name alone: the configuration comes from the manifest
uvx cc-toolbox setup --profile base                          # the base profile
uvx cc-toolbox setup --profile all                           # every installed profile, the base first, each in its own run
```

```powershell
# Windows one-liner: iex (irm ...) takes no arguments, so use the variable; no configuration is needed
$env:CLAUDE_CODE_TOOLBOX_PROFILE='my-env-1'; iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')
```

Each profile's manifest remembers the command names, the links (`link-dirs` and `link-from`, see [`link-dirs`](#link-dirs)) and the component choice (`--select`, `--with`, `--without`, or a picker choice) the install typed or took from the environment, and the configuration it was installed from. A profile that links content re-runs from its source's `resolved-config.yaml` rather than from a configuration of its own, and every run of the source re-runs it (see [Linked Profiles](#linked-profiles)). Per key, a re-run ranks its sources: a value typed for this run, an environment value for this run, the remembered value when its recorded origin is the flag or the variable, the configuration's own value, then the default. Values the configuration declares are therefore re-read on every run, and values you typed survive until you type them again. The installation summary and the completion summary mark each value `[cli]`, `[env]`, `[remembered]` or `[yaml]` (`[default]` for a profile selected by name whose configuration lists no names), and a remembered value that overrides a configuration value which changed since the install produces a warning naming both. A remembered component choice counts as supplied selectors, so the picker does not run; pass a selector to change it. The choice is checked against the components the configuration declares today: a remembered `--without` naming a component the configuration dropped is dropped itself, with a warning, and the manifest records the cleaned choice; a remembered `--select` or `--with` naming one stops the run with an error naming the manifest, because applying it would change what gets installed, and `--select` or `--with` passed explicitly (or `--select all`) replaces it.

`--profile NAME` takes no configuration, but accepts one: a configuration whose identity equals the manifest's (the same URL, or the same local file by resolved path) proceeds, any other goes through the switch guard below, whose message names the argument or `CLAUDE_CODE_TOOLBOX_ENV_CONFIG`. A `--command-names` value beside `--profile NAME` must start with `NAME`; it then sets the aliases. `--profile base` re-runs the base install and refuses a configuration that now declares `command-names`. `--profile all` lists every installed profile and, on Windows, decides administrator elevation once before anything else: when a profile's run needs it and the terminal is not elevated, the parent relaunches itself through UAC (without `--skip-install` every profile installs Claude Code; with it, each profile's recorded configuration decides, and a profile without a readable `resolved-config.yaml` counts as needing it), so no child opens a window of its own; `--no-admin` and `--dry-run` skip the decision. It then asks once (or takes `--yes`) and runs each profile -- the base first, then by name, every source before the profiles that link content from it -- as its own child process with `--yes`, this run's `--dry-run` and `--skip-install`, and `--no-admin` (a dry run forwards only this run's `--no-admin`, so each child still reports what a real run would elevate for), with every `CLAUDE_CODE_TOOLBOX_*` argument twin except `CLAUDE_CODE_TOOLBOX_ENV_AUTH` and `CLAUDE_CONFIG_DIR` removed from the child's environment. The children list no unrefreshed profiles and refresh no dependents, which the parent runs itself; the report at the end names each profile, its result and the `--profile` command that retries a failed one, and in the window a UAC relaunch opened the run then waits for Enter under the same success or errors banner a single run shows, so the report stays on screen. It cannot be combined with a configuration (positional or `CLAUDE_CODE_TOOLBOX_ENV_CONFIG`) or a selector flag.

##### Guards before any write

Two guards hold a re-run back before anything is written, and `--dry-run` reports them with exit code 1 instead of a plan the real run would not execute:

- **An environment value that would rename a profile.** A `CLAUDE_CODE_TOOLBOX_COMMAND_NAMES` value that differs from the names an installed profile records needs consent: the run stops under `--yes` or without a terminal, and asks when a terminal is available. A typed `--command-names` value proceeds. A variable holding only the primary name selects the profile and changes nothing.
- **An environment value that would change a profile's links.** A `CLAUDE_CODE_TOOLBOX_LINK_DIRS` or `CLAUDE_CODE_TOOLBOX_LINK_FROM` value that differs from the links an installed profile records needs the same consent; a typed `--link-dirs` or `--link-from` value proceeds.
- **A different configuration for an existing profile.** The run lists what the previous configuration leaves behind -- profile files it installed that the new one does not, MCP servers, OS environment variables and `settings.json` keys of a base profile (each `env` variable on its own), and destinations outside `~/.claude` whose content is still what that run wrote -- and stops under `--yes` or without a terminal, or asks when a terminal is available. The three Claude Code update controls (`DISABLE_AUTOUPDATER`, `DISABLE_UPDATES`, `CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL`) are never residue: the version pins of the installed profiles decide them. A destination outside `~/.claude` that another installed profile also records is listed as kept and never removed. The message names what to undo: clear `CLAUDE_CODE_TOOLBOX_ENV_CONFIG` when the configuration came from the variable, drop the configuration argument when it was typed, then re-run with `--profile NAME`. `--switch-config` (`CLAUDE_CODE_TOOLBOX_SWITCH_CONFIG=1`) accepts the switch; the run then removes the residue before installing the new configuration. A relative local path and its absolute spelling are the same configuration.

After a run, the completion summary lists every other installed profile with its `--profile` command, because one run refreshes one profile and the dependents it refreshed itself. A child run (one `--profile all` starts, or a dependent a source's run refreshes) leaves that list to the run that started it, whose summary covers every installed profile. A version pin names the other installed profiles whose binary it holds or moves, and a `files-to-download` destination outside `~/.claude` that a profile of another configuration recorded from a different source is named before consent; an identical file on disk is left untouched.

##### Profile manifests

Every toolbox-managed profile records its install in `manifest.json` (`~/.claude/manifest.json` for the base profile, `~/.claude/<primary>/manifest.json` for an isolated one) and the configuration it installed in `resolved-config.yaml` beside it: the resolved, component-selected configuration without `command-names`, so the same configuration renders the same bytes whichever profile installed it. The manifest fields: `name` (the primary command name, `null` for the base profile), `version`, `claude_code_version` (the pin), `config_source` (the resolved absolute path or URL), `config_source_url`, `config_source_type`, `config_identity` (the source as compared across runs), `config_digest` (the sha256 of `resolved-config.yaml`), `installed_at`, `command_names`, `components` (the `select`, `with` and `without` values as typed, or `null`), `link` (the linked entries, the source and the origin of each; an empty entry list for a `--link-dirs none` typed or taken from the environment, which later runs remember; `null` for a profile that links nothing without such a value), `origins` (per key: `cli`, `env`, `yaml` or `default`), `yaml_values` (the configuration's own `command_names`, `link_dirs`, `link_from` and default `components` at install time), `machine_wide_destinations` (`files-to-download` destinations outside `~/.claude`, each with its source and sha256), `os_env_written`, `settings_keys_written` (top-level `settings.json` keys, and one `env.<VAR>` entry per env variable), `mcp_servers` (name and scopes), and `files_written` (profile-relative paths). A manifest written without `config_identity` is matched by its `config_source_url` when present and otherwise by its resolved `config_source`; when a relative local source cannot be resolved from another directory, the first re-run records the identity of the configuration it is given, with an info line, instead of refusing.

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
- **Valid values:** `dependencies`, `agents`, `slash-commands`, `rules`, `skills`, `files-to-download`, `hooks`, `mcp-servers`, `global-config`, `user-settings`, `os-env-variables`, `components`
- **Validation:** Non-eligible keys produce an error. Non-empty `merge-keys` without `inherit` produces a validation error because `merge-keys` controls merge semantics during inheritance resolution and has no effect without a parent configuration to merge from. An empty `merge-keys` list without `inherit` is permitted (treated as a no-op).
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
- **Special value:** `"latest"` (case-insensitive) installs the latest available version (same as the default behavior) -- except while another installed profile pins a version (or a profile manifest cannot be read), when the installed Claude Code is kept at its version (see [Several Profiles on One Machine](#several-profiles-on-one-machine))
- **Validation:** Must be `"latest"` or valid semver (`X.Y.Z` with optional pre-release and build metadata)
- **Note:** Works with both native (via direct binary download from Google Cloud Storage) and npm installation methods. If the requested version is not found via GCS, the installer falls back to the native installer with the latest version
- **Auto-update management:** When a specific version is set, update controls are automatically injected into multiple targets so that neither the background auto-updater nor a manual `claude update` or `claude install` moves Claude Code off the pinned version. When `"latest"` is used or the key is absent, the controls are removed -- including `DISABLE_AUTOUPDATER` and `DISABLE_UPDATES` set by hand outside the toolbox -- while controls the YAML declares are preserved, unless another installed profile still pins a version, in which case the machine-global controls stay in force. See [Automatic Auto-Update Management](#automatic-auto-update-management) for details.
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

#### `link-dirs`

Entries of the isolated profile's directory that the profile takes through a directory link from another profile instead of installing its own copy: any of `skills`, `agents`, `commands`, `rules`, `hooks`, `output-styles`, `prompts` and `projects`, or `all` for every entry and `none` for no entry. Each link is a symbolic link on Linux and macOS and a directory junction on Windows (made without elevation through `_winapi.CreateJunction`, with `mklink /J` as the fallback), created at Step 3 before any content step, so the profile's sessions, the skills CLI and the setup itself all write through the link into the source.

- **Type:** `list[str] | None`
- **Default:** `None` (no links). `--link-dirs ENTRIES` and `CLAUDE_CODE_TOOLBOX_LINK_DIRS` give the value for one run; a typed or environment value replaces the configuration's list whole.
- **Needs an isolated profile:** links live inside `~/.claude/NAME`, so a run without `command-names` (or `--command-names`) that declares `link-dirs` stops with an error naming the flag to add. The base profile never links.
- **`projects`:** holds sessions and auto-memory rather than installed content. It links to any profile -- the source needs no manifest -- and leaves the component selection to the profile, so a profile that links only `projects` installs its own content and shares the conversation history of its source, the base `~/.claude/projects/` by default.
- **Content entries** (every entry but `projects`): the linked profile shows the source's installed content, so it is held to the source's installation. The source must be a profile this setup installed from the same configuration (the identity is the resolved path or URL: the run compares the configuration it was given with the source's manifest and fetches nothing); a profile that links content itself cannot be a source (the error names the profile that holds the entries for real); and the profile takes the source's `resolved-config.yaml` and component selection, so `--select`, `--with` and `--without` are refused, the steps that would install a linked section report that it is linked and install nothing, and a `files-to-download` destination inside a linked entry is provided by the link (see [Paths that name the base config home](#paths-that-name-the-base-config-home)). Such a profile is a dependent of its source: every run of the source refreshes it, and the source refuses to change its own links or configuration while a dependent points at it. See [Linked Profiles](#linked-profiles).
- **Existing directories:** a link that already points at the right place is kept, a link that points elsewhere is repaired, and an empty real directory is replaced. A real directory with content is converted only by a value typed for this run (`--link-dirs` or the variable): it is moved aside to `<entry>.unlinked-<timestamp>` inside the profile, and the installation summary (and `--dry-run`) lists each such directory with its path and item count before you confirm; for `projects` the row adds that those sessions and auto-memory stop appearing in the profile. A remembered or configuration value never moves a directory aside; the run stops and names the flag that would. A link on disk that no value declares is listed as `[on disk, not declared]` and left alone; `--link-dirs none` typed for the run removes the links, installs real directories, and is remembered like any typed value (see below).
- **Remembered:** the manifest records the links, so `--profile NAME` recreates them. A content link is remembered whatever source it came from (the profile reads no `link-dirs` of its own once it follows a source); a `projects`-only link is remembered when it was typed or came from the environment, and the configuration's own value is re-read otherwise. A `none` typed for a run or taken from `CLAUDE_CODE_TOOLBOX_LINK_DIRS` is remembered the same way, ahead of the configuration's `link-dirs`: a profile converted back with `--profile NAME --link-dirs none` stays unlinked on every later run although its configuration still declares `link-dirs`, and so does a source installed with `--link-dirs none` under a configuration whose link keys serve the profiles that link from it. The installation summary then shows `Links: none [remembered]` with the configuration's `link-dirs` it sets aside; pass `--link-dirs` to replace the remembered value. A `link-dirs: [none]` declared in the configuration is re-read like every configuration value and remembered by nothing. A `CLAUDE_CODE_TOOLBOX_LINK_DIRS` or `CLAUDE_CODE_TOOLBOX_LINK_FROM` value that differs from the recorded links is held back like a renaming variable (see [Guards before any write](#guards-before-any-write)).
- **Skills sync:** a profile that links `skills` gets `syncClaudeAiSkills: false` in its `user-settings`, marked `[auto]` in the installation summary, because the claude.ai skill sync would write into the source; a value the configuration declares is kept, with a warning when it differs.
- **Inheritance:** Standard override (child replaces parent)
- **Example:**

```yaml
command-names:
  - "team-2"

# Share sessions and auto-memory with the default Claude
link-dirs:
  - projects
```

```bash
# The same for one run, then a second command on the content of an installed profile
uvx cc-toolbox setup team.yaml --command-names team-2 --link-dirs projects
uvx cc-toolbox setup team.yaml --command-names team-3 --link-dirs all --link-from team-2
```

#### `link-from`

The profile the linked entries come from: `base` for `~/.claude`, or the primary command name of an installed isolated profile (`~/.claude/NAME`). Read only together with `link-dirs`: a `--link-from` or `CLAUDE_CODE_TOOLBOX_LINK_FROM` value with no linked entry is an error naming what to add or clear.

- **Type:** `str | None`
- **Default:** `base`
- **Rules:** a profile cannot link from itself, a content source must hold its entries for real, and the value is validated like a command name (see [`link-dirs`](#link-dirs)).
- **Inheritance:** Standard override (child replaces parent)
- **Example:** `link-from: team-1`

#### `dependencies`

Platform-specific shell commands to execute during setup.

- **Type:** `dict[str, list[str]]`
- **Default:** `{}`
- **Valid platform keys:** `common`, `windows`, `macos`, `linux`
- **Behavior:**
  - `common` runs on all platforms
  - Platform-specific keys run only on the matching platform
  - Invalid keys raise a `ValueError`
- **Global npm sudo fallback (Linux/macOS/WSL):** When a `npm install -g ...` dependency fails and the npm global prefix is not writable by the current user (probed via `npm config get prefix` plus a write-access check on `{prefix}/lib/node_modules`), the setup automatically retries the command with sudo using a three-tier fallback: interactive TTY prompt, then cached credentials (`sudo -n true`), then a `/dev/tty` prompt that works even in piped `curl | bash` runs. An informational note that sudo may be requested prints before the first attempt. The retry runs the parsed command arguments with a 600-second timeout. Dependencies containing shell control characters (`;`, `&`, `|`, `<`, `>`, `$`, backquote, newline) are never escalated -- compound user-authored shell strings do not run as root. When no sudo mechanism is available or the retry fails, the setup prints guidance (the manual sudo command, `npm config set prefix ~/.npm-global` plus a PATH export, or reinstalling Node.js with a version manager) and records the dependency as failed.
- **Failure handling:** Dependency execution continues after a failure (remaining dependencies still run), but every failed command is collected and listed in a dedicated "The following dependencies failed to install:" section of the "Setup Completed with Errors" block at the end of the run, and the setup exits with code 1. CI consumers see a nonzero exit code when any dependency fails.
- **Isolated profiles:** When the configuration installs with `command-names`, a command that names the base config home (`~/.claude`, `$HOME/.claude`, `$env:USERPROFILE\.claude`, and the other spellings) or a `~/.claude.json` sibling runs against the profile directory instead, and the installation summary marks it `[re-rooted]`; see [Paths that name the base config home](#paths-that-name-the-base-config-home).
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
- **Inheritance:** Standard override (child replaces parent) by default. When listed in `merge-keys`: identity-based merge by `name` field. Child skills with the same name replace the parent skill in-position (at the parent's original index). New child skills are appended at the end. Duplicate names within one list are collapsed to the last entry with a warning.
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
- **Isolated profiles:** When the configuration installs with `command-names`, a destination that names the base config home (`~/.claude/...` in any spelling) lands at the same path inside the profile directory and is marked `[re-rooted]` in the installation summary; a destination inside another installed profile or outside the config home stays as written. In a profile that links content from a source, a destination inside a linked entry is provided by the link and not written again; the summary lists it under `Provided by links`. See [Paths that name the base config home](#paths-that-name-the-base-config-home).
- **Inheritance:** Standard override (child replaces parent) by default. When listed in `merge-keys`: identity-based merge by the normalized final file path. A `dest` ending with `/` or `\` is a directory destination, so its identity is `dest` plus the source filename (query parameters stripped; for GitLab API raw-file URLs the real filename is decoded from the URL-encoded path segment) -- the trailing-separator form is the only directory form the merge identity recognizes, and the normalization is purely lexical (no filesystem checks). The filename derivation is stable across source resolution, so a parent whose sources were already resolved to absolute URLs matches a child entry written with a relative source. Distinct files sharing a directory dest therefore keep distinct identities and all survive the merge. Child entries whose final file path matches a parent entry replace it in-position; new child entries are appended at the end. Duplicate identities within one list are collapsed to the last entry with a warning.
- **Download deduplication:** After merging, entries that still resolve to the same final file (for example, a directory-form dest and an explicit file dest naming the same path) are deduplicated before the parallel download phase: the last entry wins and each skipped entry is reported with a warning. Files are written atomically (temp file plus rename), so an interrupted or concurrent write never leaves a partially-written destination.
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
- **Inheritance:** Standard override (child replaces parent) by default. When listed in `merge-keys`: identity-based merge by `name` field. Child servers with the same name replace the parent server in-position (at the parent's original index). New child servers are appended at the end. Duplicate names within one list are collapsed to the last entry with a warning.

#### HTTP Transport

- **Required fields:** `name`, `transport: "http"`, `url`
- **Optional fields:** `scope`, `header`

```yaml
mcp-servers:
  - name: "my-api"
    transport: "http"
    url: "http://localhost:3000/api"
    header: "Authorization: Bearer ${MY_TOKEN}"
```

**Environment-variable header values (`${VAR}`):** A `${VAR}` (or `${VAR:-default}`) reference inside `header` is preserved literally in the Claude Code configuration and expanded from the environment by Claude Code **at runtime**, when a session starts -- the secret itself is never written into any configuration file, only the placeholder is stored. The setup script preserves the placeholder verbatim when it registers the server (it does not expand it at install time), so the behavior is identical on every operating system and shell. This is the recommended way to configure an authenticated remote MCP server: each user sets the variable (for example `MY_TOKEN`) as a real environment variable on their own machine, and only this placeholder configuration is shared.

> **The variable must be set when Claude Code launches.** If a `${VAR}` reference has no value and no default, Claude Code fails to parse the MCP configuration. Ensure the variable is exported before launching Claude Code, or provide a fallback with `${VAR:-default}`.

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

The `args` field provides an optional argument list for the command. When `args` is specified, the `command` field is treated as just the executable and `args` provides the arguments separately. This maps directly to the `args` array in the generated MCP configuration JSON, matching the Claude Code MCP server configuration format. When `args` is absent, the `command` string is parsed into command and arguments automatically.

```yaml
mcp-servers:
  # Without args (command string is parsed automatically)
  - name: "memory-server"
    command: "npx @modelcontextprotocol/server-memory"
    env:
      - "DEBUG=1"

  # With explicit args (command + args kept separate)
  - name: "python-server"
    command: "python"
    args: ["-m", "my_mcp_server"]
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

> **Isolated environments:** When `command-names` creates an isolated environment, `scope: user` MCP servers are configured with `CLAUDE_CONFIG_DIR` pointing to the isolated directory. This ensures `claude mcp add --scope user` writes to the isolated `.claude.json` instead of the home-directory one. This per-call injection is one of the two `CLAUDE_CONFIG_DIR` channels described in [Setup-Time `CLAUDE_CONFIG_DIR` Export](#setup-time-claude_config_dir-export).
>
> **Strict mode hides non-profile servers from the isolated commands:** As soon as one server declares `profile`, the generated launcher starts Claude Code with `--strict-mcp-config --mcp-config <profile>/mcp.json`, and that session loads **only** the servers in that file. What happens to a server declared without `profile` depends on its scope. A `user`- or `local`-scope server is registered by `claude mcp add` under the isolated profile's own `.claude.json` (the per-call `CLAUDE_CONFIG_DIR` injection described above), a file no session outside those commands reads -- so while strict mode is on it loads nowhere. A `project`-scope server keeps its entry in the `.mcp.json` of the directory the setup ran in, which sessions opened there outside the isolated commands still load. The setup reports each hidden server by name, names the commands that will not load it and where its registration ended up, and the completion summary counts them. To serve a server to the isolated commands, combine its scope with `profile` -- `scope: [user, profile]` instead of `scope: user`.

#### Idempotent Reconfiguration

The setup compares every declared server with the configuration already stored at its target scope (the isolated `.claude.json` when `command-names` is set, otherwise the base one) and skips the `claude mcp remove`/`claude mcp add` cycle when they match. This matters because `claude mcp remove` deletes the stored MCP OAuth tokens of `http`/`sse` servers (they are keyed by server name plus a hash of the type/url/headers triple), and re-adding restores only the connection settings, never the tokens: without the comparison, every setup run would silently de-authenticate every authenticated remote server.

- A server is skipped only when the live entry at its **declared scope** matches the declared configuration exactly (type, command, args, env, url, headers; a same-name match at a different scope is not a match). Skipped servers appear in the completion summary as `MCP servers unchanged (skipped, tokens preserved)`.
- A same-name leftover at another scope (which would shadow the declared entry) is still removed, without touching the matching entry or its tokens.
- When the declared configuration **changed**, the server is removed and re-added. For `http`/`sse` servers this clears the stored OAuth tokens -- unavoidably, because the token key is derived from the changed configuration itself -- and the setup prints a warning to re-authenticate via `/mcp`.
- When the live state cannot be read (for example a corrupt `.claude.json`), the setup falls back to the full remove-and-add cycle so the declared configuration always wins.
- Per-project enable/disable choices made in the `/mcp` panel (`disabledMcpServers`/`enabledMcpServers` in the `projects` section) live outside the server entries and are never touched by the setup.

#### The `env` Field

Defines environment variables for the process of a **stdio** MCP server. Claude Code spawns stdio servers itself, so the declared variables reach the child process; a `${VAR}` reference in a value is expanded from the environment at session start, like in `header`.

- **String format:** Single `KEY=VALUE` assignment
- **List format:** Multiple `KEY=VALUE` pairs

```yaml
# Single variable
env: "API_TOKEN=${API_TOKEN}"

# Multiple variables
env:
  - "DEBUG=1"
  - "LOG_LEVEL=debug"
```

#### The `header` Field

Sets an HTTP header for both `http` and `sse` transports.

- **Format:** `"Header-Name: value"`
- **Example:** `header: "Authorization: Bearer token123"`

#### MCP Server Permissions

MCP servers are registered with Claude Code via `claude mcp add` (with scope-based routing). To pre-allow specific MCP tools without a per-use confirmation prompt, add `mcp__servername` (or `mcp__servername__toolname`) entries to `permissions.allow` under [`user-settings`](#user-settings).

### Environment Variables

#### `os-env-variables`

Persistent environment variables for the sessions the configuration installs. A base run (no `command-names`) writes them to the shell profile (Linux/macOS) or Windows registry, where every process sees them. An isolated run (`command-names` present) writes them to the profile's own env loader files, and `launch.sh` sources `env.sh` for every session the profile's commands start, so the variables reach that profile's sessions and nothing else on the machine; the three machine-wide binary controls (`DISABLE_AUTOUPDATER`, `DISABLE_UPDATES`, `CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL`) are the exception and go to the OS environment from any run, because they hold the one Claude Code binary every profile uses. See [Environment Variable Loading](#environment-variable-loading).

- **Type:** `dict[str, str | None] | None`
- **Default:** `None`
- **Special value:** Set a value to `null` to delete an existing variable (a base run deletes it from the OS environment; an isolated run writes an unset line into its loaders, so the profile's sessions drop a value inherited from the OS environment)
- **Validation:** Variable names must match `^[A-Za-z_][A-Za-z0-9_]*$`
- **Inheritance:** Standard override (child replaces parent) by default. When listed in `merge-keys`: shallow dictionary merge. Child keys override matching parent keys. A child `null` is carried into the resolved configuration as a deletion request rather than consumed by the parent's value, so the OS-level variable is deleted at setup time even when the parent declared it.
- **Example:**

```yaml
os-env-variables:
  MY_TOOL_PATH: "/opt/my-tool/bin"
  OLD_UNUSED_VAR: null  # Deletes this variable
```

- **Automatic string conversion:** Non-string YAML values (integers, booleans, floats) in `os-env-variables` are automatically converted to strings by the setup script. For example, `MY_TIMEOUT: 30000` (YAML integer) becomes `"30000"` (string), and `ENABLE_FEATURE: true` (YAML boolean) becomes `"True"` (string). To preserve exact string representation, quote values in YAML: `ENABLE_FEATURE: "true"`. A `null` value is never stringified -- it is a deletion request (see the `null` special value above).
- **Current session guidance (Linux/macOS):** When variables are deleted via `null`, the setup script outputs shell-specific `unset` commands so the user can remove those variables from the running session without opening a new terminal:
  - **Bash/Zsh:** `unset VARNAME` for each deleted variable
  - **Fish** (when installed): `set -e VARNAME` for each deleted variable

#### Environment Variable Loading

The setup script supports two distinct kinds of environment variables, each serving a different scope:

| Source                            | Scope                | Storage                                                              | Available In                                        |
|-----------------------------------|----------------------|----------------------------------------------------------------------|-----------------------------------------------------|
| `user-settings.env`               | Claude Code internal | `settings.json` `env` key (or profile `config.json`)                 | Claude Code sessions only                           |
| `os-env-variables` (base run)     | OS-level persistent  | Shell profiles + Windows registry                                    | All processes (terminals, programs)                 |
| `os-env-variables` (isolated run) | Profile sessions     | `~/.claude/{cmd}/env.*` loaders; `launch.sh` sources `env.sh`        | Sessions started through the profile's commands     |
| machine-wide binary controls      | OS-level persistent  | Shell profiles + Windows registry, from base and isolated runs alike | All processes; they hold the one Claude Code binary |

Claude-session variables are declared under [`user-settings.env`](#user-settings) (raw `settings.json` content). See the [`user-settings`](#user-settings) section for the `env` value rules (string-only values, `null` as delete).

##### Env Loader Files

When `os-env-variables` are configured, the setup generates Rustup-style env loader files that can be sourced to load the variables into the current shell session. These files contain **only** `os-env-variables` (not `user-settings.env`, which Claude Code reads from `settings.json`/`config.json`).

**Per-command files** (generated when `command-names` is specified) live in the profile directory: `~/.claude/{cmd}/` by default, or the directory a [`CLAUDE_CONFIG_DIR` override](#claude_config_dir-override-isolated-mode) names.

| File       | Shell      | Generated When |
|------------|------------|----------------|
| `env.sh`   | Bash/Zsh   | Always         |
| `env.fish` | Fish       | Fish installed |
| `env.ps1`  | PowerShell | Windows only   |
| `env.cmd`  | CMD batch  | Windows only   |

Loader files are toolbox-owned and rebuilt on every run. A variable set to `null` (a deletion) becomes an unset line in each shell's syntax -- `unset NAME` (Bash/Zsh), `set -q NAME; and set -e NAME` (Fish), `Remove-Item -Path Env:NAME -ErrorAction SilentlyContinue` (PowerShell), `SET "NAME="` (CMD) -- so a value the profile's sessions inherit from the OS environment is removed when `launch.sh` sources `env.sh` at session start. When the configuration declares no profile variable, the files are rewritten header-only so stale lines from a prior run stop being applied at session start. The machine-wide binary controls never appear in a loader file: an unset line there would strip a control from the profile's sessions after another profile pinned a version.

##### Automatic Loading via Launchers

When `command-names` is specified, `launch.sh` sources the profile's `env.sh` before starting Claude Code, inside the bash process that becomes the session. No manual action is required: running the command (for example, `claude-python`) loads the profile's environment variables. The source line is guarded by a file-existence check, so launchers work normally even when no `os-env-variables` are configured.

On Windows, every entry point (`start.cmd`, `start.ps1`, and the `.cmd` and `.ps1` commands in `~/.local/bin`) hands over to `launch.sh` through Git Bash and applies no loader itself. A batch file executes in the cmd.exe that calls it, and `$env:` is process-wide in PowerShell, so a loader applied at that level would stay in your window after the session ends and reach a plain `claude` started next. The `.cmd` files also run under `setlocal`, so the shell you ran the command from keeps its environment exactly as it was.

`env.cmd`, `env.ps1` and `env.fish` are generated for your own shell: source one by hand when you want the profile's variables there, with `call "%USERPROFILE%\.claude\{cmd}\env.cmd"` in cmd.exe, `. "$env:USERPROFILE\.claude\{cmd}\env.ps1"` in PowerShell, or `source ~/.claude/{cmd}/env.fish` in Fish.

##### Applying OS Environment Variables

A base run writes `os-env-variables` to the shell profile files (`.bashrc`, `.zshrc`, `.profile`, `config.fish` on Unix; Windows Registry on Windows). Open a new terminal to load the updated variables automatically. An isolated run writes only the machine-wide binary controls there (its other variables live in its loaders), and the installation summary names each such write as `[machine-wide]` before you confirm.

##### Fish Dual-Mechanism

On systems with Fish shell installed, the setup uses two complementary mechanisms for OS environment variables:

- **`set -gx` in `config.fish`**: Durable persistence. Variables are loaded when Fish starts. This is the primary mechanism.
- **`set -Ux` (Universal Exported)**: Instant propagation. Variables are immediately visible in all running Fish sessions without requiring `source` or a new terminal. For deletions, `set -Ue` removes the universal variable.

The `config.fish` write is always the authoritative source. The `set -Ux` call is a complementary enhancement that provides immediate availability.

### User Interface

#### `command-defaults`

System prompt configuration for the commands an isolated profile installs.

- **Type:** `CommandDefaults | None`
- **Default:** `None`
- **Fields:**
  - `system-prompt` (str) -- Path to the system prompt file (downloaded to the profile's `prompts/` directory)
  - `mode` (str, default: `"replace"`) -- How the prompt is applied:
    - `replace` -- Completely replaces the default system prompt (`--system-prompt` flag, added in Claude Code v2.0.14)
    - `append` -- Appends to Claude's default development prompt (`--append-system-prompt` flag, added in Claude Code v1.0.55)
- **Isolated install** (the run has command names, from `command-names`, `--command-names`, or `CLAUDE_CODE_TOOLBOX_COMMAND_NAMES`): the profile's launcher passes the prompt file from `~/.claude/{cmd}/prompts/` to Claude Code in the configured mode.
- **Base install** (none of them gives the run any names): the prompt file is still downloaded to `~/.claude/prompts/`, but a base install has no launcher, so the prompt does not reach Claude Code. The run is not refused: the installation summary and `--dry-run` state that `command-defaults` applies only to isolated installs, and the closing summary reports the system prompt as not applied. See [`command-defaults` Without Command Names](#command-defaults-without-command-names).
- **Validation:** Valid with or without `command-names`.
- **Inheritance:** Standard override (child replaces parent)
- **Example:**

```yaml
base-url: "https://raw.githubusercontent.com/my-org/my-configs/main"

command-defaults:
  system-prompt: "prompts/my-prompt.md"
  mode: "append"
```

#### `user-settings`

Raw `settings.json` content, using Claude Code's native camelCase key names exactly as they appear on disk. This is the single surface for every Claude Code `settings.json` setting -- `model`, `permissions`, `env`, `effortLevel`, and everything else. In non-isolated mode (`command-names` absent) it is deep-merged into `~/.claude/settings.json`; in isolated mode (`command-names` present) it is built into the isolated profile's `config.json` and delivered via `--settings`. See [Profile-Level Settings Routing](#profile-level-settings-routing) for the end-to-end write contract.

In non-isolated mode the write uses deep merge with universal array union: every list at every depth is unioned with the list `~/.claude/settings.json` already holds (structural dedupe), matching [Claude Code CLI's cross-scope merge semantics](https://code.claude.com/docs/en/settings) ("arrays are concatenated and deduplicated, not replaced"). In isolated mode `config.json` is rebuilt from the resolved configuration each run, so its arrays are exactly the resolved ones.

- **Type:** `UserSettings | None`
- **Default:** `None`
- **Excluded keys:** `hooks` and `statusLine` (these require dedicated write logic with file download, path resolution, and type processing, and must be configured at the YAML root level via the [`hooks`](#hooks) and [`status-line`](#status-line) keys)
- **Isolated profiles:** An `apiKeyHelper` or `awsCredentialExport` value that names the base config home (`~/.claude/scripts/...`) is re-rooted into the profile directory when the configuration installs with `command-names`, together with the `files-to-download` entry that delivers the script; see [Paths that name the base config home](#paths-that-name-the-base-config-home). On Windows the rewrite runs before the tilde expansion, so the expanded path lies inside the profile.
- **Inheritance:** Standard override (child replaces parent) by default. When listed in `merge-keys`: deep recursive merge using `deep_merge_settings()` with `DEFAULT_ARRAY_UNION_KEYS` (`permissions.allow`, `permissions.deny`, `permissions.ask` arrays are unioned with deduplication; other arrays use child-replaces-parent semantics in the YAML inheritance layer). Child keys override matching parent keys; a child `null` is carried into the resolved configuration as a deletion request rather than consumed by the parent's value, so `write_user_settings()` deletes the key from `~/.claude/settings.json` -- applying the resolved configuration equals applying the parent and then the child. **Note:** YAML inheritance semantics are intentionally separate from on-disk write semantics. The on-disk writer (`write_user_settings()` -> `_write_merged_json()`) uses universal array union at every depth for all keys and never stores a `null`; `DEFAULT_ARRAY_UNION_KEYS` and null preservation apply only inside the YAML composition layer.
- **Example:**

```yaml
user-settings:
  model: "opus"
  effortLevel: "high"
  alwaysThinkingEnabled: true
  language: "english"
  theme: "dark"
  apiKeyHelper: "uv run --no-project --python 3.12 ~/.claude/scripts/api-key-helper.py"
  permissions:
    defaultMode: "default"
    allow:
      - "Read"
      - "Glob"
      - "Grep"
    deny:
      - "Bash(rm -rf)"
    additionalDirectories:
      - "/opt/project-data"
  env:
    PROJECT_TYPE: "python"
    DISABLE_AUTOUPDATER: "1"
    OLD_UNUSED_VAR: null  # Deletes this variable
```

##### Built-in Key Reference (camelCase)

`user-settings` accepts any `settings.json` key. The keys below are the common ones and use Claude Code's native camelCase spelling. Because a misplaced or misspelled built-in key is silently ignored by Claude Code at runtime, the toolbox validates these keys fail-fast (setup exits with an error). Unknown keys pass through untouched for forward compatibility.

- **`model`** -- Model alias or custom model name. Any non-empty string: Anthropic model names (`claude-sonnet-4-20250514`), built-in aliases (`default`, `sonnet`, `opus`, `haiku`, `opus[1m]`, `sonnet[1m]`, `opusplan`, `best`), or third-party / provider-prefixed identifiers (`gpt-4o`, `openrouter/anthropic/claude-3.5-sonnet`). Empty or whitespace-only strings are rejected.
- **`permissions`** -- Permission rules controlling which tools and actions are allowed, denied, or require confirmation. Sub-keys use camelCase: `defaultMode`, `allow`, `deny`, `ask`, `additionalDirectories`. `defaultMode` must be one of `acceptEdits`, `auto`, `bypassPermissions`, `default`, `delegate`, `dontAsk`, `plan`; `allow`, `deny`, `ask`, and `additionalDirectories` must be lists of strings. The kebab-case spellings `default-mode` and `additional-directories` are rejected with the camelCase correction. To pre-allow an MCP server's tools, add `mcp__servername` entries to `permissions.allow` (see [MCP Server Permissions](#mcp-server-permissions)).
- **`env`** -- Claude-level environment variables available within Claude Code sessions. A mapping of variable names (matching `^[A-Za-z_][A-Za-z0-9_]*$`) to **string** values. A non-string value is rejected (`user-settings.env.NAME must be a string (quote the value in YAML) or null to delete the variable.`) -- quote the value in YAML to keep it a string. A `null` value deletes the variable (see [Key Deletion](#key-deletion-null-as-delete)).
- **`attribution`** -- Commit and pull-request attribution. A mapping with `commit` and `pr` string sub-keys; set a sub-key to an empty string to hide that attribution.
- **`alwaysThinkingEnabled`** -- Boolean enabling always-on extended thinking mode.
- **`companyAnnouncements`** -- List of announcement strings displayed to users.
- **`effortLevel`** -- Adaptive reasoning effort, one of `high`, `low`, `max`, `medium`, `xhigh`. The `xhigh` level requires `model` to be an Opus or Fable variant (the model name must contain `opus` or `fable`, case-insensitive) or the exact alias `best`; `max` additionally accepts a Sonnet variant. When `model` is absent or outside the required families, the effort level is rejected. See [effortLevel model requirements](#effortlevel-model-requirements) below.

###### effortLevel model requirements

The model gate matches family substrings because the free-form `model` value cannot resolve which version an alias points to; Claude Code gracefully downgrades an unsupported level to the highest supported level at runtime, but declaring an unsupported combination in the profile is almost always a mistake, so it is rejected. The alias `best` is accepted by **exact match only** (it always resolves to Fable 5 or the latest Opus model), so arbitrary model names that merely contain `best` are rejected.

```yaml
# xhigh requires an Opus or Fable model
user-settings:
  model: "claude-fable-5"   # or "opus", "fable", "best"
  effortLevel: "xhigh"
```

```yaml
# max requires an Opus, Sonnet, or Fable model
user-settings:
  model: "opus"             # or "sonnet", "fable", "best"
  effortLevel: "max"
```

```yaml
# low, medium, and high work with any model
user-settings:
  effortLevel: "high"
```

> **`max` persistence caveat:** Per the official Claude Code documentation, persisted `settings.json` files accept only `low`, `medium`, `high`, and `xhigh` for `effortLevel`; `max` (like `ultracode`) is session-only and, in a plain `settings.json`, persists across sessions only via the `CLAUDE_CODE_EFFORT_LEVEL` environment variable. The toolbox still accepts `max` because, for isolated profiles, it delivers `config.json` through the `--settings` flag on every launch, where the value applies per-session. The setup emits a warning when `user-settings.effortLevel` is `max`. `ultracode` is intentionally **not** an accepted `effortLevel` value.

##### Fail-Fast Validation Rules

The toolbox validates `user-settings` against Claude Code's `settings.json` schema and rejects (exit 1) misconfigurations that Claude Code would otherwise ignore silently. A `null` value for any key is always allowed (a deletion request). Unknown keys not covered below pass through untouched. The rules are:

- **`hooks` and `statusLine` are forbidden.** They must be configured at the YAML root level via [`hooks`](#hooks) and [`status-line`](#status-line). Blocked by `check_excluded_keys` in the `UserSettings` Pydantic model (`USER_SETTINGS_EXCLUDED_KEYS = {'hooks', 'statusLine'}`).
- **Root-level YAML keys are forbidden.** `status-line` and `os-env-variables` are YAML root keys, not `settings.json` keys, and are rejected with the message `Key '{key}' is not allowed in user-settings. It is a root-level YAML key, not a settings.json key.`
- **Kebab-case spellings of built-in keys are rejected** with the camelCase correction: `always-thinking-enabled` -> `alwaysThinkingEnabled`, `company-announcements` -> `companyAnnouncements`, `effort-level` -> `effortLevel`, `env-variables` -> `env`; and inside `permissions`, `default-mode` -> `defaultMode` and `additional-directories` -> `additionalDirectories`.
- **Global-only keys are rejected.** Keys that live in `~/.claude.json` (`autoUpdates`, `installMethod`, `autoConnectIde`, `autoInstallIdeExtension`, `externalEditorContext`, `teammateDefaultModel`, `oauthAccount`) belong in [`global-config`](#global-config), not `user-settings`, and are rejected with the message `Key '{key}' belongs in global-config (~/.claude.json), not in user-settings (settings.json).`

##### `CLAUDE_CONFIG_DIR` override (isolated mode)

To override the auto-computed isolation directory, set `CLAUDE_CONFIG_DIR` under `user-settings.env` (only meaningful when `command-names` is present). The setup reads and then removes it before writing config.json -- the launcher's `export CLAUDE_CONFIG_DIR` remains the sole authoritative runtime source, so the value is not left in the profile's `env` block.

The setup writes the whole profile into that directory, and the generated launchers and global commands start Claude Code with it: they export it as `CLAUDE_CONFIG_DIR` and read `config.json`, `mcp.json`, the system prompt and `env.sh` from it. A directory below your home directory appears in the launchers (`launch.sh`, `start.ps1`, `start.cmd`) and in the CMD and Git Bash global commands relative to your home (`$HOME/...` in bash, `%USERPROFILE%\...` in CMD, `$env:USERPROFILE` in PowerShell), so they follow the home directory each shell resolves when you run them. A directory anywhere else appears as its absolute path. The PowerShell global commands (`~/.local/bin/my-env.ps1` and one per alias) name `start.ps1` by its absolute path, and on Linux and macOS every global command is a symlink to the absolute path of `launch.sh`. Spaces and parentheses in the path work in every shell.

```yaml
command-names:
  - "my-env"

user-settings:
  env:
    CLAUDE_CONFIG_DIR: "~/.claude/my-custom-dir"
```

##### Preservation contract for `user-settings`

Keys that you put under `user-settings:` are preserved even when you re-run the setup with a different YAML that omits them, because in non-isolated mode `write_user_settings()` uses deep-merge semantics and never deletes keys unless you set them to `null`. List-valued keys (at any depth) accumulate additively across runs under the universal array-union contract, so elements you wrote in earlier runs are never silently deleted. This is the deliberate shared-file semantics: the toolbox does NOT surprise-delete the keys you manage from the shared `~/.claude/settings.json`. The one exception is the update controls a version pin manages (`DISABLE_AUTOUPDATER`, `DISABLE_UPDATES`, and `CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL` in `env`), which an unpinned run removes unless the current YAML sets them to a non-null value -- see [Deferred Stale-Key Behavior](#deferred-stale-key-behavior-user-facing-contract). In isolated mode the profile's `config.json` is rebuilt atomically each run, so removing a key from YAML cleanly removes it from `config.json` on the next run. See [Profile-Level Settings Routing](#profile-level-settings-routing) below for the full write semantics contract and the deferred stale-key behavior.

#### `global-config`

Raw `~/.claude.json` content, merged into the one global configuration file the run owns: `~/.claude.json` for a base run, `~/.claude/{cmd}/.claude.json` for an isolated run (Claude Code CLI resolves `getGlobalClaudeFile()` via `CLAUDE_CONFIG_DIR` with no fallback to the home directory, and the base file belongs to the base profile). The `global-config` write of an isolated run never touches the base `~/.claude.json` (the only thing an isolated run records there is the `installMethod` the Claude Code installer writes when Step 1 installs, upgrades, or migrates the binary), so installing a configuration that sets `oauthAccount: null` and `userID: null` as an isolated profile signs out only that profile and leaves the base profile's account in place. Uses deep merge with universal array union: every list at every depth is unioned with the list the target file already holds (existing elements first, new elements appended, duplicates removed), matching [Claude Code CLI's cross-scope merge semantics](https://code.claude.com/docs/en/settings) and preserving CLI-managed state at runtime (OAuth tokens, per-project trust decisions, user-scoped MCP server approvals via `/mcp approve`, `enabledPlugins`, `enabledMcpjsonServers`/`disabledMcpjsonServers`). A YAML array therefore only adds elements: declaring a shorter list leaves the file's other elements in place, and setting the key to `null` deletes the whole array.

When `command-names` is present, the setup also propagates the machine's recorded `installMethod` from the base `~/.claude.json` into the `global-config` write (auto-injected, even when the YAML has no `global-config` section; a user-declared `installMethod` in YAML wins with a warning when it differs; nothing is propagated when the base file or key is absent). The base file is read for this, never written; the write carries the correct installation type into the isolated `.claude.json`, so isolated sessions report it correctly.

When the resolved `global-config` sets `oauthAccount` or `userID` to `null` and the `.claude.json` this run writes holds a value for that key, the installation summary (and `--dry-run`) prints a warning in its `[!] ATTENTION` block naming the profile and the file, because the write signs the account recorded there out. The values are never printed and nothing is blocked: deleting the keys is the configuration author's choice.

- **Type:** `GlobalConfig | None`
- **Default:** `None`
- **Excluded keys:** `oauthAccount` cannot be set to non-null values (OAuth credentials must not appear in YAML configuration files). Set `oauthAccount: null` to clear authentication state.
- **Settings-only keys rejected:** Keys that live in `settings.json` (`model`, `permissions`, `env`, `attribution`, `alwaysThinkingEnabled`, `effortLevel`, `companyAnnouncements`, `statusLine`, `hooks`, `availableModels`, `enforceAvailableModels`) are rejected in `global-config` because `~/.claude.json` is not a settings file and Claude Code would silently ignore them at runtime. `model` and the other `settings.json` keys are rejected with the message `Key '{key}' is a settings.json key and is not valid in global-config (~/.claude.json). Move it to user-settings.`; `statusLine` and `hooks` are instead directed to the root-level `status-line` and `hooks` YAML keys. A `null` value is always allowed (a deletion request).
- **Inheritance:** Standard override (the child's `global-config` section replaces the parent's whole) by default. When listed in `merge-keys`: deep recursive merge using `deep_merge_settings()` with `array_union_keys=set()`: objects merge member by member, and a child array replaces the parent's array at every depth (unlike `user-settings`, whose `permissions.allow`, `permissions.deny`, and `permissions.ask` arrays are unioned). Child keys override matching parent keys; a child `null` is carried into the resolved configuration as a deletion request rather than consumed by the parent's value, so `write_global_config()` deletes the key from `~/.claude.json` (RFC 7396). **Note:** YAML inheritance semantics are intentionally separate from on-disk write semantics. The on-disk writer (`write_global_config()` -> `_write_merged_json()`) uses universal array union at every depth and never stores a `null`; the `set()` form and null preservation apply only inside the YAML composition layer.
- **Example:**

```yaml
global-config:
  autoConnectIde: true
  editorMode: "vim"
  showTurnDuration: true
```

How an array passes through both layers, with `merge-keys: [global-config]` in the child:

```text
parent.yaml        enabledMcpjsonServers: [parent-server]
child.yaml         enabledMcpjsonServers: [child-server]
resolved config    enabledMcpjsonServers: [child-server]               (child replaces parent)
~/.claude.json     enabledMcpjsonServers: [cli-server]                 (before the run)
~/.claude.json     enabledMcpjsonServers: [cli-server, child-server]   (after the run: union)
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
- A `null` member of a section the target file does not hold yet (or holds as a non-object value) is dropped as well: the section is applied onto an empty object per RFC 7396, so a literal JSON `null` is never written. This matters for `env`, because Claude Code copies a null member into the process environment as the string `'null'` rather than unsetting the variable
- Under `inherit`, a child `null` survives composition as a deletion request even when the parent declared a value for the same key, so the deletion still happens on disk
- Null inside arrays is NOT treated as deletion
- The `--dry-run` summary shows `[DELETE]` markers for null-valued keys

> **Warning:** Bare YAML keys with no value (`key:`) are equivalent to `key: null`. This means accidentally omitting a value will DELETE that key rather than set it to an empty string. Always use explicit values: `key: ""` for empty strings, `key: null` for intentional deletion.

**Profile-owned keys (`status-line`, `hooks`) in non-command-names mode:** The two profile-owned keys support null-as-delete at the YAML root level via the deep-merge writer -- see [Profile-Level Settings Routing](#profile-level-settings-routing). Both top-level and nested nulls are covered end-to-end:

- **Top-level null** (for example, `status-line: null`, `hooks: null`): deletes the entire on-disk key from `~/.claude/settings.json`.
- **Nested null** (for example, `hooks: {PreToolUse: null}`): deletes only the nested sub-key while preserving the rest of the block (other hook event names).

The dict-membership construction in the data flow from YAML root to the writer preserves the distinction between "declared with explicit null" and "absent from YAML" -- only the former triggers deletion. OMITTING a profile-owned key from a subsequent YAML run does NOT delete it; see [Deferred Stale-Key Behavior](#deferred-stale-key-behavior-user-facing-contract) for the intentional preservation contract.

**Per-variable nulls in `user-settings.env` and `os-env-variables`:** a `null` value deletes the variable instead of setting a literal string. In non-isolated mode, `user-settings: {env: {VAR: null}}` deletes `env.VAR` from `~/.claude/settings.json` via the deep-merge writer (this also cleans up any stale literal value a prior run may have written). In isolated mode, `create_profile_config()` strips null-valued members recursively before the atomic `config.json` write -- absence equals deletion under atomic rebuild -- so a JSON `null` is never written for an `env` entry. `os-env-variables: {VAR: null}` deletes the OS-level variable from shell profiles or the Windows registry and excludes it from the env loader files.

#### `status-line`

Status line script configuration. The script file and optional config file are downloaded to `~/.claude/hooks/`.

- **Type:** `StatusLine | None`
- **Default:** `None`
- **Inheritance:** Standard override (child replaces parent)
- **Fields:**
  - `file` (str, required) -- Script filename; must exactly match the basename of a `hooks.files` entry (a path form like `hooks/statusline.py` fails validation)
  - `padding` (int, optional) -- Padding value
  - `config` (str, optional) -- Config file reference (appended as command argument); matched against `hooks.files` basenames after query-parameter stripping and basename extraction
- **Note:** Both `file` and `config` (if specified) must exist in `hooks.files`. If `status-line` is configured, the `hooks` key must also be present.
- **Example:**

```yaml
hooks:
  files:
    - "hooks/statusline.py"
    - "configs/statusline-config.yaml"
  # events may reference other hooks.files entries; the status-line
  # references below already count as usage for these two files

status-line:
  file: "statusline.py"
  config: "statusline-config.yaml"
  padding: 0
```

### Hooks

Event-driven hooks that run automatically during Claude Code sessions. Five hook types are supported: `command`, `http`, `prompt`, `agent`, and `mcp_tool`.

- **Type:** `Hooks | None`
- **Default:** `None`
- **Inheritance:** Standard override (child replaces parent) by default. When listed in `merge-keys`: composite merge. `files` and `helpers` lists are concatenated with deduplication by full file path string equality. `events` lists are concatenated without deduplication (each event is unique by its field combination).
- **Fields:**
  - `files` (list[str]) -- Script files to download to the hooks directory. Only used by command hooks and `status-line`.
  - `helpers` (list[str]) -- Shared modules to download to the same hooks directory, imported by the hook scripts (see [Hook Helpers](#hook-helpers))
  - `events` (list[HookEvent]) -- Event configurations

#### Hook Types

| Type       | Description                                            | Required Fields  |
|------------|--------------------------------------------------------|------------------|
| `command`  | Executes a shell command or script (default)           | `command`        |
| `http`     | Sends an HTTP POST request to a URL                    | `url`            |
| `prompt`   | Single-turn LLM evaluation with no tool access         | `prompt`         |
| `agent`    | Spawns a subagent with tool access for evaluation      | `prompt`         |
| `mcp_tool` | Calls a tool on an already-configured MCP server       | `server`, `tool` |

#### Common Fields (All Hook Types)

These fields apply to all five hook types:

| Field            | YAML Key         | Type   | Required | Description                                                                                                                                                          |
|------------------|------------------|--------|----------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `event`          | `event`          | `str`  | Yes      | Event name (for example, `PreToolUse`, `PostToolUse`, `Notification`); see [Recognized Event Names](#recognized-event-names)                                         |
| `matcher`        | `matcher`        | `str`  | No       | Regex pattern for matching (default: `""`)                                                                                                                           |
| `type`           | `type`           | `str`  | No       | Hook type: `command`, `http`, `prompt`, `agent`, or `mcp_tool` (default: `command`)                                                                                  |
| `if`             | `if`             | `str`  | No       | Permission rule syntax filter (for example, `"Bash(git *)"`, `"Edit(*.ts)"`)                                                                                         |
| `status-message` | `status-message` | `str`  | No       | Custom spinner message displayed while the hook runs                                                                                                                 |
| `once`           | `once`           | `bool` | No       | If true, runs only once per session then is removed (skills only)                                                                                                    |
| `timeout`        | `timeout`        | `int`  | No       | Timeout in seconds; must be positive (defaults vary by type: 600 for command, 30 for prompt, 60 for agent)                                                           |
| `id`             | `id`             | `str`  | No       | Stable identifier used solely as a [`components`](#components) selector for this event; unique across events when present, never written to the generated hooks JSON |

#### Type-Specific Fields

##### Command Hook Fields

| Field          | YAML Key       | Type        | Required | Description                                                                                 |
|----------------|----------------|-------------|----------|---------------------------------------------------------------------------------------------|
| `command`      | `command`      | `str`       | Yes      | Script filename (must exist in `hooks.files`)                                               |
| `config`       | `config`       | `str`       | No       | Config file reference (must exist in `hooks.files`). Toolbox-specific: appended as argument |
| `args`         | `args`         | `list[str]` | No       | Argument list switching the command to exec form (see [Command Hooks](#command-hooks))      |
| `async`        | `async`        | `bool`      | No       | If true, runs the command in the background without blocking                                |
| `async-rewake` | `async-rewake` | `bool`      | No       | If true, runs in the background and wakes the model on exit code 2; implies `async`         |
| `shell`        | `shell`        | `str`       | No       | Shell to use: `"bash"` (default) or `"powershell"`; cannot be combined with `args`          |

##### HTTP Hook Fields

| Field              | YAML Key           | Type            | Required | Description                                                               |
|--------------------|--------------------|-----------------|----------|---------------------------------------------------------------------------|
| `url`              | `url`              | `str`           | Yes      | URL to send the HTTP POST request to                                      |
| `headers`          | `headers`          | `dict[str,str]` | No       | Additional HTTP headers. Values support `$VAR_NAME` env var interpolation |
| `allowed-env-vars` | `allowed-env-vars` | `list[str]`     | No       | Environment variable names permitted for interpolation into header values |

##### Prompt and Agent Hook Fields

| Field               | YAML Key            | Type   | Required | Description                                                                                     |
|---------------------|---------------------|--------|----------|-------------------------------------------------------------------------------------------------|
| `prompt`            | `prompt`            | `str`  | Yes      | Prompt text for LLM evaluation                                                                  |
| `model`             | `model`             | `str`  | No       | Model to use for the evaluation                                                                 |
| `continue-on-block` | `continue-on-block` | `bool` | No       | Prompt hooks only: a deny feeds its reason back to the agent and the turn continues (see below) |

##### MCP Tool Hook Fields

| Field    | YAML Key | Type   | Required | Description                                                                                    |
|----------|----------|--------|----------|------------------------------------------------------------------------------------------------|
| `server` | `server` | `str`  | Yes      | Name of an already-configured MCP server to invoke                                             |
| `tool`   | `tool`   | `str`  | Yes      | Name of the tool on that server to call                                                        |
| `input`  | `input`  | `dict` | No       | Arguments passed to the tool; string values support `${path}` interpolation from the hook JSON |

#### Field Matrix

Complete required/forbidden field matrix across all hook types:

| Field               | `command` | `http`    | `prompt`  | `agent`   | `mcp_tool` |
|---------------------|-----------|-----------|-----------|-----------|------------|
| `command`           | REQUIRED  | FORBIDDEN | FORBIDDEN | FORBIDDEN | FORBIDDEN  |
| `config`            | Optional  | FORBIDDEN | FORBIDDEN | FORBIDDEN | FORBIDDEN  |
| `args`              | Optional  | FORBIDDEN | FORBIDDEN | FORBIDDEN | FORBIDDEN  |
| `async`             | Optional  | FORBIDDEN | FORBIDDEN | FORBIDDEN | FORBIDDEN  |
| `async-rewake`      | Optional  | FORBIDDEN | FORBIDDEN | FORBIDDEN | FORBIDDEN  |
| `shell`             | Optional  | FORBIDDEN | FORBIDDEN | FORBIDDEN | FORBIDDEN  |
| `url`               | FORBIDDEN | REQUIRED  | FORBIDDEN | FORBIDDEN | FORBIDDEN  |
| `headers`           | FORBIDDEN | Optional  | FORBIDDEN | FORBIDDEN | FORBIDDEN  |
| `allowed-env-vars`  | FORBIDDEN | Optional  | FORBIDDEN | FORBIDDEN | FORBIDDEN  |
| `prompt`            | FORBIDDEN | FORBIDDEN | REQUIRED  | REQUIRED  | FORBIDDEN  |
| `model`             | FORBIDDEN | FORBIDDEN | Optional  | Optional  | FORBIDDEN  |
| `continue-on-block` | FORBIDDEN | FORBIDDEN | Optional  | FORBIDDEN | FORBIDDEN  |
| `server`            | FORBIDDEN | FORBIDDEN | FORBIDDEN | FORBIDDEN | REQUIRED   |
| `tool`              | FORBIDDEN | FORBIDDEN | FORBIDDEN | FORBIDDEN | REQUIRED   |
| `input`             | FORBIDDEN | FORBIDDEN | FORBIDDEN | FORBIDDEN | Optional   |
| `if`                | Optional  | Optional  | Optional  | Optional  | Optional   |
| `status-message`    | Optional  | Optional  | Optional  | Optional  | Optional   |
| `once`              | Optional  | Optional  | Optional  | Optional  | Optional   |
| `timeout`           | Optional  | Optional  | Optional  | Optional  | Optional   |

Setting a field marked FORBIDDEN on a hook type produces a validation error. Two combinations are additionally rejected on command hooks: `shell` together with `args` (exec form spawns the executable without a shell), and a non-positive `timeout` on any hook type.

#### Recognized Event Names

Claude Code 2.1.238 recognizes exactly these hook event names and rejects any other name at configuration load time:

`ConfigChange`, `CwdChanged`, `DirectoryAdded`, `Elicitation`, `ElicitationResult`, `FileChanged`, `InstructionsLoaded`, `MessageDisplay`, `Notification`, `PermissionDenied`, `PermissionRequest`, `PostCompact`, `PostToolBatch`, `PostToolUse`, `PostToolUseFailure`, `PreCompact`, `PreToolUse`, `SessionEnd`, `SessionStart`, `Setup`, `Stop`, `StopFailure`, `SubagentStart`, `SubagentStop`, `TaskCompleted`, `TaskCreated`, `TeammateIdle`, `UserPromptExpansion`, `UserPromptSubmit`, `WorktreeCreate`, `WorktreeRemove`

The toolbox warns about an event name outside this set but still writes it, so a configuration written for a newer Claude Code release keeps installing; a typo surfaces as the warning at setup time and as a load-time rejection by Claude Code.

#### Command Hooks

Execute a script file when the event fires. The `command` field must reference a filename listed in `hooks.files`. The toolbox processes command paths by prepending the appropriate runtime (`uv run` for `.py`, `node` for `.js`/`.mjs`/`.cjs`). Built file paths are double-quoted in the generated command, so hooks directories containing spaces (for example a Windows home like `C:/Users/John Smith`) work in every shell.

The `config` field is a toolbox-specific extension: when set, the config file path is appended as an argument to the command. This field is not part of the official Claude Code hooks specification.

Setting `args` switches the hook to exec form: Claude Code resolves `command` as an executable and spawns it directly with the argument list, without any shell. The toolbox folds the launcher into that shape -- for a Python script it emits `command: "uv"` with `run --no-project --python 3.12`, the resolved script path, the config path (when set), and your `args` entries as the argument list; for a JavaScript script it emits `command: "node"` the same way. No element is quoted, because there is no shell to word-split, so spaced hooks directories are safe in exec form too. `shell` cannot be combined with `args`.

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
    - event: "PostToolUse"
      matcher: "Write"
      type: "command"
      command: "linter.py"
      args: ["--fix", "--level", "2"]
    - event: "Notification"
      type: "command"
      command: "linter.py"
      async: true
      async-rewake: true
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

By default, a denying evaluation (`ok: false`) ends the turn. With `continue-on-block: true`, the deny still blocks the matched action, but its reason is fed back to the agent and the turn continues, so a steering hook can redirect the agent within the same turn. Claude Code supports this setting although its public hooks reference does not document it (verified against Claude Code 2.1.238); it applies to prompt hooks only.

```yaml
hooks:
  events:
    - event: "PreToolUse"
      matcher: "Bash"
      type: "prompt"
      prompt: "Check if this bash command is safe to execute"
      model: "sonnet"
      continue-on-block: true
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

#### MCP Tool Hooks

Call a tool on an already-configured MCP server when the event fires. The server must be connected in the session the hook runs in (for example, one declared under [`mcp-servers`](#mcp-servers)); the toolbox passes `server`, `tool`, and `input` through to the generated configuration as-is. String values inside `input` support `${path}` interpolation from the hook input JSON.

```yaml
hooks:
  events:
    - event: "PostToolUse"
      matcher: "Edit"
      type: "mcp_tool"
      server: "linter"
      tool: "lint_file"
      input:
        file_path: "${tool_input.file_path}"
      timeout: 20
```

#### File Consistency Rules

Hook file references are validated for **command hooks only**. HTTP, prompt, agent, and MCP tool hooks do not use file references and are excluded from file consistency validation.

The rules are enforced in two layers. The Pydantic model validates configurations that do not declare `inherit`; for a config that declares `inherit`, cross-references are decidable only on the resolved composition, so the model skips them. The setup script then validates every fully resolved configuration at runtime -- before the admin check, remote file validation, and any installation work -- listing all violations and exiting with code 1. When component selection filters the configuration, the setup re-validates the filtered result: a dangling event or `status-line` reference is still an error, while a file stranded by a deselected component is tolerated (see [Component Selection](#components)). A composition whose hook events or status-line reference a missing hook file therefore fails at setup time, not at hook execution.

1. Every file listed in `hooks.files` must be used by at least one command hook event or the `status-line` configuration
2. Every `command` in command hook events must exist in `hooks.files`
3. Every `config` in command hook events must exist in `hooks.files`
4. If `status-line` is configured, its `file` and `config` must exist in `hooks.files`
5. If `status-line` is configured but `hooks` is not defined, that is an error
6. No filename may appear in both `hooks.files` and `hooks.helpers`

Entries in `hooks.helpers` are exempt from rule 1 -- they exist precisely to be unreferenced. Naming a helper as a `command`, a `config`, or a `status-line` `file`/`config` is an error that tells you to move the entry to `hooks.files`, because a referenced script or config is launched by Claude Code rather than imported by a script.

#### Hook Helpers

Hook scripts frequently share code -- a config loader, a formatting utility, a small client library. Declare those modules in `hooks.helpers` and they download into the same directory as the scripts in `hooks.files`, so a script reaches them as a sibling of itself:

```yaml
hooks:
  files:
    - "hooks/linter.py"
    - "hooks/statusline.py"
  helpers:
    - "hooks/hook_config_loader.py"
  events:
    - event: "PostToolUse"
      matcher: "Edit|MultiEdit|Write"
      type: "command"
      command: "linter.py"
```

```python
# Inside hooks/linter.py and hooks/statusline.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hook_config_loader
```

`helpers` accepts the same source forms as `files` (a repository-relative path resolved against `base-url`, or a full URL). Helpers are never registered as a command: no helper name reaches the generated `hooks` JSON or the `statusLine` entry.

The destination follows the hook scripts, which is the point of the key. With `command-names`, both lists install into `~/.claude/{cmd}/hooks/`; without it, both install into `~/.claude/hooks/`; in a profile that links `hooks/` from a source, the scripts and their helpers are the source's, seen through the link. A helper can also travel as a [`files-to-download`](#files-to-download) entry: a destination that names the base config home (`~/.claude/hooks/helper.py`) is re-rooted beside the scripts in an isolated run (see [Paths that name the base config home](#paths-that-name-the-base-config-home)), while a destination outside the config home (`~/.config/...`) stays where it is written and is no sibling of the scripts. `hooks.helpers` stays the key to declare a helper with, for two reasons that hold in every mode.

Helpers carry no [component](#components) identity: a component selector cannot claim one, and deselecting a component never deletes one, whereas a downloaded file can be claimed by a component and removed with it. Scope a helper by scoping the scripts that import it -- an unused helper costs one download and nothing else, while a missing one breaks every script that imports it. The [File Consistency Rules](#file-consistency-rules) cover helpers, which no `files-to-download` entry gets: no filename may appear in both `hooks.files` and `hooks.helpers`, and a reference that names a helper is reported as a misplaced declaration.

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
  helpers:
    # Imported by linter.py from its own directory, never launched directly
    - "hooks/hook_config_loader.py"
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

| Scenario                | Target File                    | Write Mechanism                                        | Hook Files Directory     |
|-------------------------|--------------------------------|--------------------------------------------------------|--------------------------|
| `command-names` present | `~/.claude/{cmd}/config.json`  | `create_profile_config()` (atomic overwrite)           | `~/.claude/{cmd}/hooks/` |
| `command-names` absent  | `~/.claude/settings.json`      | `write_profile_settings_to_settings()` (deep-merge)    | `~/.claude/hooks/`       |

When `command-names` is absent, the setup writes hooks to the global `~/.claude/settings.json` via `write_profile_settings_to_settings()` as part of the 2-key `PROFILE_OWNED_KEYS` delta. The writer delegates to `_write_merged_json()`, which deep-merges the `hooks` dict into the existing file: disjoint event names (in the delta but not on disk, and vice versa) compose additively, and the per-event matcher-group lists are unioned with structural dedupe across runs (every list at every depth is unioned under the universal array-union contract). All other keys -- user-managed keys, other profile-owned keys not in the current delta, and Step 14 `user-settings` contributions -- are preserved. See [Profile-Level Settings Routing](#profile-level-settings-routing) for the full contract.

**Re-run behavior:** When the YAML re-declares `hooks`, the deep-merge writer recurses into the existing `hooks` dict. Disjoint event names compose additively across runs. For the same event name, matcher groups accumulate: two matcher groups with the same `matcher` string but different inner handlers from different runs coexist as separate entries (naive structural dedupe -- they are not structurally equal, so neither is discarded). Structurally identical matcher groups collapse to one, making repeat runs with the same YAML idempotent. This matches [Claude Code's native cross-scope merge semantics](https://code.claude.com/docs/en/settings); at runtime, Claude Code deduplicates command hooks by command string and HTTP hooks by URL (per the [Claude Code hooks documentation](https://code.claude.com/docs/en/hooks): "Command hooks are deduplicated by command string, and HTTP hooks are deduplicated by URL"), so on-disk consolidation is unnecessary. To fully clear stale events for a specific event name, set `hooks: {EventName: null}` to delete just that event list; declaring a new list under the same event name unions with existing entries rather than replacing them.

**Deleting hooks:** Setting `hooks: null` at YAML root level deletes the entire `hooks` key from `~/.claude/settings.json` via RFC 7396 null-as-delete. Setting `hooks: {EventName: null}` deletes just that event list while preserving the other events under `hooks`. OMITTING `hooks` entirely from a subsequent YAML run does NOT delete it (per [Deferred Stale-Key Behavior](#deferred-stale-key-behavior-user-facing-contract)); the prior-run `hooks` content is preserved.

The installation summary distinguishes between the two routing targets:

- With `command-names`: `Hooks: N configured (in config.json)`
- Without `command-names`: `Hooks: N configured (in settings.json)`

### components

Author-defined selectable component groups. Components let a configuration author group items from the eight selectable sections -- `agents`, `slash-commands`, `rules`, `skills`, `files-to-download`, `mcp-servers`, `dependencies`, and `hooks` -- into named units the end user can pick at setup time (interactively via the checkbox picker, or non-interactively via `--select`/`--with`/`--without`). An item claimed by at least one component installs only when a selected component claims it; an item claimed by no component is mandatory, never appears in any picker, and always installs. A configuration without a `components:` key behaves exactly as before -- the feature is entirely opt-in.

```yaml
components:
  - name: core
    label: "Core tooling"
    description: "Base agent, rules, and the linter hook"
    includes:
      agents: ["agents/my-agent.md"]
      rules: ["rules/style.md"]
      hooks: ["post-edit-lint", "hooks/linter.py"]
  - name: mcp
    label: "MCP servers"
    requires: [core]
    includes:
      mcp-servers: ["context-server"]
  - name: extras
    label: "Optional extras"
    default: false
    bundles: [mcp]
    includes:
      files-to-download: ["~/.claude/extra.txt"]
      dependencies: ["npm install -g some-tool"]
```

#### Component Fields

| Field         | Type              | Required | Default | Description                                                                                                                                                                                                               |
|---------------|-------------------|----------|---------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `name`        | `str`             | **Yes**  | --      | Unique identifier used with `--select`/`--with`/`--without`. Lowercase letters, digits, dots, underscores, hyphens; must start with a letter or digit. The literals `all` and `none` are reserved as `--select` sentinels |
| `label`       | `str`             | No       | `None`  | Human-readable name shown in the picker and the installation summary (falls back to `name`)                                                                                                                               |
| `description` | `str`             | No       | `None`  | Hint line shown in the picker and in `--list-components` output                                                                                                                                                           |
| `default`     | `bool`            | No       | `true`  | Whether the component is pre-selected (checked in the picker; included in `--yes` and non-interactive runs)                                                                                                               |
| `requires`    | `list[str]`       | No       | `[]`    | Hard edges: components transitively auto-included whenever this component is selected (wins over `--without` with a warning; cycles are tolerated)                                                                        |
| `bundles`     | `list[str]`       | No       | `[]`    | Soft edges: components pre-selected together with this component; the user may still deselect them, and `--without` removes them                                                                                          |
| `includes`    | `dict[str, list]` | **Yes**  | --      | Mapping of selectable section name to the item selectors this component claims (must claim at least one item)                                                                                                             |

#### Selector Identities

Each section's selectors use its existing merge identity, so a selector is written exactly the way the item appears in the YAML:

| Section                             | Selector                                                                                                                                  |
|-------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------|
| `agents`, `slash-commands`, `rules` | The exact path string as written in the list                                                                                              |
| `skills`, `mcp-servers`             | The entry's `name`                                                                                                                        |
| `files-to-download`                 | The entry's `dest`; a directory dest (trailing `/` or `\`) is also matchable by its normalized final file path (`dest` + source filename) |
| `dependencies`                      | The exact command string, matched across every platform list                                                                              |
| `hooks`                             | A `hooks.events[].id` (see the `id` common field) or a path string present in `hooks.files`; `hooks.helpers` entries carry no identity    |

Validation fails fast on duplicate component names, dangling `requires`/`bundles` references, `includes` keys outside the selectable sections, selectors matching no item, duplicate hook event ids, and distinct `files-to-download` entries sharing a final path (which would make selectors ambiguous).

#### Selection Flow

1. The base set is the author defaults, unless `--select` replaces it entirely (`--select all` selects every component; `--select none` selects none).
2. `--with` adds names to the set; `bundles` edges then softly expand it; `--without` removes names.
3. The interactive picker (a questionary checkbox, falling back to a numbered toggle prompt when questionary is unavailable or the console cannot render it) runs only when no selector flag was given, neither `--yes` nor `--dry-run` is set, and an interactive terminal is available. Non-interactive runs silently use the author defaults.
4. The hard `requires` closure runs last: deselecting a component that a selected component requires brings it back with a warning and an `[auto: required by '...']` marker in the summary.

The installation summary shows a `Components:` block with `[x]`/`[ ]` rows, auto-include causes, and a copy-pasteable `Replay:` selector line (`--select ...`, plus `--without ...` for the skipped components so bundle edges do not re-add them, plus `--command-names ...` when the command names came from that flag or its variable) reproducing the selection non-interactively. `--list-components` prints the registry (names, labels, defaults, edges, and per-section item counts) and exits without installing.

Selection resolves before the Windows admin-elevation check and before remote file validation, so deselected items never trigger UAC prompts, network fetches, or authentication prompts.

CI model validation of a config that declares `inherit` skips the cross-reference checks (selector resolution, `requires`/`bundles` references, and the duplicate final-path check): the full item and component sets exist only after inheritance resolution, so those checks run at setup time against the resolved configuration instead. Within-file invariants (duplicate component names, duplicate hook event ids) stay enforced on every file.

During inheritance resolution, selectors for the path-identity sections (`agents`, `slash-commands`, `rules`, and `hooks` file paths) are resolved with the same rules as the items they claim: write the same string in the item list and the selector, and both resolve identically against the declaring file's source. Hook event ids and already-absolute selectors pass through unchanged; a component claiming an item another file contributes uses that item's resolved form.

An inherited registry survives composition like any other undeclared key: a key the composing config does not declare SURVIVES from its parent, and `merge-keys` only chooses merge-versus-replace for keys the child declares. When a composition removes items a parent's registry claims (for example by replacing `hooks` or emptying `skills`), the composing config must override the registry itself -- declare `components: []` to drop selectability entirely, or declare a replacement registry claiming only surviving items.

Deselection also uninstalls. A re-run that deselects a component removes what an earlier run installed for it: deselected MCP servers are removed via `claude mcp remove` for every non-profile scope (`user`, `local`, `project`; the profile `mcp.json` is rebuilt from the filtered configuration each run), toolbox-written hook entries of deselected events are stripped from the shared `settings.json` (matched quote-insensitively on the command, so entries written by versions that built unquoted paths still match), and deselected skill directories, agent/command/rule files, hook files, and downloaded files are deleted from their install locations. The removal plan derives entirely from the current configuration (every claimed item is named there), so no on-disk state is required; removals appear in the installation summary as `[REMOVE]` rows and are previewed without acting under `--dry-run`. Dependencies are never uninstalled: arbitrary install commands cannot be reversed.

Deselection is also re-validated. After the selection filter is applied, the setup re-runs the hooks-files consistency check on the filtered configuration: a surviving hook event or `status-line` reference whose file was dropped with a deselected component stops the setup with exit code 1 and the guidance `The selected components leave hook references dangling` (fix by selecting the component that provides the file, or by claiming the event and its file together in the registry). A file stranded in the opposite direction -- kept while its only referencing event was deselected -- is tolerated as deselection residue and only downloads unused.

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

- Each parent config's relative resource paths (agents, rules, slash-commands, hook files and helpers, files-to-download sources, skill bases, and system prompts) are resolved to absolute URLs or paths **before** merging with child values. `status-line` and hook event `command`/`config` references are `hooks.files` basenames, not paths, so they are never rewritten
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
user-settings:
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
user-settings:                # Completely REPLACES parent's user-settings (not in merge-keys)
  effortLevel: "high"
# The parent's user-settings.model is NOT inherited here, because user-settings
# uses replace semantics by default. Add 'merge-keys: [user-settings]' to deep-merge
# the parent's model with the child's effortLevel instead.
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

The `merge-keys` in a structured entry accepts the same values as the top-level `merge-keys` directive: `dependencies`, `agents`, `slash-commands`, `rules`, `skills`, `files-to-download`, `hooks`, `mcp-servers`, `global-config`, `user-settings`, `os-env-variables`, `components`.

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
user-settings:
  model: "sonnet"
os-env-variables:
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
os-env-variables:
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
user-settings:
  model: "opus"
os-env-variables:
  LEAF_VAR: "leaf_val"
```

Result:

- `agents`: `["agents/core-agent.md", "agents/extra-agent.md"]` -- merged by the structured entry's `merge-keys` (Rule 3)
- `rules`: `["rules/base-rule.md", "rules/extra-rule.md"]` -- merged by the structured entry's `merge-keys` (Rule 3)
- `user-settings`: `{"model": "opus"}` -- `user-settings` is not in per-entry merge-keys and not in the leaf's top-level `merge-keys`, so it uses replace semantics: extensions declares none, then the leaf replaces with its own `user-settings`
- `name`: `"My Environment"` -- leaf overrides
- `os-env-variables`: `{"SHARED_VAR": "from_extensions", "EXT_VAR": "ext_val", "LEAF_VAR": "leaf_val"}` -- extensions is not in per-entry merge-keys, so it REPLACES base's `os-env-variables` (dropping `BASE_VAR`); then the leaf's top-level `merge-keys: [os-env-variables]` shallow-merges the leaf on top, adding `LEAF_VAR`
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

| Type                            | Keys                                  | Strategy                                                                                                                                                                                      |
|---------------------------------|---------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| String list                     | `agents`, `slash-commands`, `rules`   | Concatenate parent + child; deduplicate by string equality; parent items first                                                                                                                |
| Named list (by `name`)          | `mcp-servers`, `skills`, `components` | Identity-based: child overrides parent in-position; new items appended                                                                                                                        |
| Named list (by final file path) | `files-to-download`                   | Identity-based: child overrides parent in-position; new items appended                                                                                                                        |
| Per-platform dict               | `dependencies`                        | Per-platform sub-key list concatenation with deduplication                                                                                                                                    |
| Composite                       | `hooks`                               | `files` and `helpers`: concat + dedup by full path; `events`: concat (no dedup)                                                                                                               |
| Deep dict                       | `global-config`                       | `deep_merge_settings()` with `array_union_keys=set()`: objects merge, every child array replaces the parent's; child `null` carried forward                                                   |
| Deep dict                       | `user-settings`                       | `deep_merge_settings()` with `DEFAULT_ARRAY_UNION_KEYS`: objects merge, `permissions.allow`/`deny`/`ask` unioned, every other child array replaces the parent's; child `null` carried forward |
| Shallow dict                    | `os-env-variables`                    | Shallow merge; child overrides; child `null` carried forward as a deletion request                                                                                                            |

The `files-to-download` identity is the normalized final file path: a `dest` ending with `/` or `\` is combined with the source filename (query parameters stripped) before matching, so distinct files sharing a directory dest keep distinct identities. See [`files-to-download`](#files-to-download) for details.

> **Note:** The `global-config` and `user-settings` rows above describe the YAML inheritance layer only -- how `merge-keys` composes parent and child configurations before the writer touches disk. The `user-settings` deep merge covers its nested `env` block (Claude-session environment variables). The on-disk writers (`write_global_config()`, `write_user_settings()`, `write_profile_settings_to_settings()`) then apply the universal array-union contract: every list at every depth is unioned with the list the target file already holds (structural dedupe), independent of `DEFAULT_ARRAY_UNION_KEYS`, so a resolved array keeps the elements the file held before the run. In isolated mode, `config.json` is rebuilt from the resolved `user-settings` each run instead. See [Profile-Level Settings Routing](#profile-level-settings-routing) for the on-disk write contract.

#### Non-Mergeable Keys

Keys not listed in the 12 mergeable keys (such as `name`, `command-defaults`, `status-line`) always use replace semantics, regardless of `merge-keys`.

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

1. **Explicit override** -- `CLAUDE_CODE_TOOLBOX_ENV_AUTH` environment variable, format `"header:value"`, `"header=value"`, or plain token
2. **URL-specific environment variables** -- `GITLAB_TOKEN` for GitLab URLs, `GITHUB_TOKEN` for GitHub URLs
3. **Generic token** -- `REPO_TOKEN` environment variable (auto-detects repository type)
4. **Interactive prompt** -- If a terminal is available and the repository type is detected

Every variable above can be set for a single run with the repeatable `--env` flag, identically in every shell: `--env GITHUB_TOKEN=... --env GITLAB_TOKEN=...`. Values passed on the command line are visible in shell history and the process list; prefer real environment variables for secrets when that matters.

#### Variable Scopes

| Variable                       | Scope                                 | Description                                     |
|--------------------------------|---------------------------------------|-------------------------------------------------|
| `GITHUB_TOKEN`                 | Python-level (auto-detected from URL) | GitHub PAT with `repo` scope                    |
| `GITLAB_TOKEN`                 | Python-level (auto-detected from URL) | GitLab PAT with `read_repository` scope         |
| `REPO_TOKEN`                   | Python-level (auto-detected from URL) | Generic token, auto-detects repo type           |
| `CLAUDE_CODE_TOOLBOX_ENV_AUTH` | Python-level (explicit override)      | Custom header format: `Header-Name:token-value` |

#### URL Handling

- GitLab web URLs (`/-/raw/`) are automatically converted to API format
- GitHub raw URLs are automatically converted to API URLs
- Public access is attempted first; authentication is applied only on 401/403/404 responses
- GitHub Pages URLs (`*.github.io`) are never treated as repository URLs -- no auth prompt is issued for them even on 404 responses
- For GitHub 404 responses, the setup script probes `api.github.com/repos/{owner}/{repo}` unauthenticated to distinguish missing files in public repositories (no auth prompt) from private or nonexistent repositories (auth prompt)

### Automatic Auto-Update Management

When `claude-code-version` specifies a pinned version (any value other than `"latest"` or absent), the setup script automatically injects update controls into three targets that block Claude Code's own update paths -- the background auto-updater, `claude update`, and `claude install` -- so none of them moves Claude Code off the pinned version. When the version is `"latest"` or absent, the setup removes these controls, re-enabling those update paths, and keeps only the controls its YAML declares (see [Removal Behavior](#removal-behavior)).

The machine has one Claude Code binary, so these controls are machine-global and shared by every profile installed on it. Removal is therefore gated on the whole machine, not on the current run: an unpinned run removes the controls only when no OTHER installed profile pins a version either. See [Several Profiles on One Machine](#several-profiles-on-one-machine).

#### Injection Targets

| Target             | Key                                              | Value   | On-disk file (isolated)                           | On-disk file (non-isolated)                         |
|--------------------|--------------------------------------------------|---------|---------------------------------------------------|-----------------------------------------------------|
| `global-config`    | `autoUpdates`                                    | `false` | `~/.claude/{cmd}/.claude.json`                    | `~/.claude.json`                                    |
| `user-settings`    | `env.DISABLE_AUTOUPDATER`, `env.DISABLE_UPDATES` | `"1"`   | `~/.claude/{cmd}/config.json` (`env` key)         | `~/.claude/settings.json` (`env` key, deep-merge)   |
| `os-env-variables` | `DISABLE_AUTOUPDATER`, `DISABLE_UPDATES`         | `"1"`   | Shell profiles / Windows registry (machine-wide)  | Shell profiles / Windows registry                   |

All three targets are injected unconditionally regardless of whether `command-names` is present, and each environment variable key is injected and conflict-checked on its own. The `user-settings.env` controls follow the standard `user-settings` routing: in isolated mode they are built into `~/.claude/{cmd}/config.json` (`env` key) at Step 18; in non-isolated mode they are deep-merged into `~/.claude/settings.json['env']` at Step 14. Deep-merge makes them additive with any user-declared environment variables: `_merge_recursive()` recurses into the `env` dict and preserves sub-keys not present in the delta. The `os-env-variables` controls are the machine-wide exception to the isolated-run routing of that section: an isolated run writes them to the OS environment, not to its loaders, because they hold the one Claude Code binary every profile uses, and names each of them as `[machine-wide]` in the installation summary. A pinned run performs no Step 16 sweep at all, so the env-based controls persist in the final file.

The two environment variables block different update paths. `DISABLE_AUTOUPDATER` stops only the background auto-updater. `DISABLE_UPDATES` blocks every update path, including manual ones: while it is set, `claude update` and `claude install` print `Updates are disabled by your administrator` and exit without changing the installed binary. Claude Code reads both variables from the process environment and from the `env` block of the settings files it loads at startup, before any subcommand runs, so a bare `claude update` is blocked by the OS-level variable in shells started after the setup and, in non-isolated mode, by `~/.claude/settings.json` alone.

To move to another release, change `claude-code-version` (to another version, or to `"latest"`) and re-run the setup. The setup's installer downloads the binary directly from Google Cloud Storage, which `DISABLE_UPDATES` does not gate; an official installer run that `DISABLE_UPDATES` refuses counts as a failed attempt, and the installer continues with its remaining methods (see [Native Installation](installing-claude-code.md#native-installation-default)).

Claude Code releases before 2.1.118 do not recognize `DISABLE_UPDATES`. For a pin to such a release, `DISABLE_AUTOUPDATER` stops the background auto-updater, and manual `claude update` and `claude install` remain possible.

#### Removal Behavior

When the version is `"latest"` or absent, nothing is auto-injected, so every auto-update control key present in the in-memory configuration comes from the user's YAML and is preserved -- the removal counterpart of the WARN-but-Respect write semantics. When nothing on the machine pins a version, the run removes each of `DISABLE_AUTOUPDATER` and `DISABLE_UPDATES` that its YAML does not declare from the OS environment and from its own profile's `settings.json`, whoever set it -- a value set by hand outside the toolbox is removed as well. To keep a variable, declare it in the YAML: a declaration in `os-env-variables` keeps the OS-level variable, and a declaration in `user-settings.env` with a value keeps it in the running profile's `settings.json` (a `null` there is a deletion request, so the sweep removes the variable from that file). Two cleanup mechanisms perform the removal:

- **OS-level variables:** `DISABLE_AUTOUPDATER` and `DISABLE_UPDATES` have no filesystem sweep, so a deletion entry is scheduled in `os-env-variables` for each of them the user does not explicitly declare there (and for neither while another installed profile pins a version), and the OS environment writer removes the OS-level variable, whether a prior pinned run or anything else set it, from a base run and from an isolated run alike. Deleting an absent variable is a safe no-op on all platforms.
- **On-disk files:** Stale artifacts in the running profile's `settings.json` and `.claude.json` are removed by the Step 16 filesystem sweep described below; copies in other profiles are reported, never edited.

**Write-remove symmetry:** After all write operations, `cleanup_stale_auto_update_controls()` runs as a filesystem sweep pass (Step 16). The sweep runs only when NO installed profile pins a version -- neither this run nor any other profile recorded in the profile manifests. It then removes `DISABLE_AUTOUPDATER` and `DISABLE_UPDATES` from the running profile's `settings.json` (`~/.claude/settings.json` for a base run, `~/.claude/{cmd}/settings.json` for an isolated run) -- except a key the current YAML itself sets to a non-null value in `user-settings.env`, which the `settings.json` sweep keeps (the removal counterpart of the WARN-but-Respect write semantics). Each key is decided on its own: declaring `DISABLE_AUTOUPDATER` keeps only that key and still removes a stale `DISABLE_UPDATES`, and the reverse. A file whose `env` block is left empty loses the `env` key. The sweep also removes `autoUpdates: false` from the running profile's `.claude.json` (`~/.claude.json` for a base run, `~/.claude/{cmd}/.claude.json` for an isolated run) -- unless the current YAML sets `autoUpdates: false` in `global-config`, in which case the file keeps it. Removal of `autoUpdates` is value-conditional: only `false` is removed, `true` (user preference) is preserved. Other profiles' files are never edited: the same two gates decide which controls found in the base profile's pair and in every other `~/.claude/*/` profile are stale, and those are listed -- profile name, file, and keys -- in the installation summary before you confirm, again at Step 16, and in the final summary, each time with the note to re-run that profile's install, which removes them. While any profile pins a version, no file is swept and nothing is reported: every `settings.json`, `.claude.json`, and OS-level control already on the machine stays exactly as it is, and no OS-level deletion is scheduled.

#### Conflict Resolution (WARN-but-Respect)

If the user explicitly sets a value in the YAML configuration that contradicts the automatic intent, the user value is preserved and a warning is emitted:

- **User value absent:** Auto-inject (proceed silently)
- **User value matches intent:** No-op (no warning). A `DISABLE_AUTOUPDATER` or `DISABLE_UPDATES` value matches whenever Claude Code treats it as enabled: `1`, `true`, `yes`, or `on`, in any letter case and ignoring surrounding whitespace.
- **User value contradicts intent:** Respect user value, emit warning. For example, if the user sets `autoUpdates: true` in `global-config` while pinning a specific version, the `true` value is preserved and a warning like `"User set global-config.autoUpdates to True (auto-update intent is False for pinned version). Respecting user value."` is displayed. Any other `DISABLE_AUTOUPDATER` or `DISABLE_UPDATES` value, such as `"0"` or `"false"`, contradicts the intent in the same way.

Injection is gated on key MEMBERSHIP, not on value: an explicit user `null` (a deletion request, legal in every target) is a user declaration that contradicts the intent, so it is respected with a warning and never overwritten.

#### `[auto]` Marker in Installation Summary

Auto-injected values are displayed in the installation summary (including `--dry-run` output) with a green `[auto]` marker, similar to the existing `[?]` (unknown keys) and `[!]` (sensitive paths) markers. This makes it clear which values were automatically added by the setup script rather than explicitly configured in the YAML.

```text
Settings added by the setup:
  [auto] global-config.autoUpdates: false
  [auto] user-settings.env.DISABLE_AUTOUPDATER: "1"
  [auto] user-settings.env.DISABLE_UPDATES: "1"
  [auto] os-env-variables.DISABLE_AUTOUPDATER: "1"
  [auto] os-env-variables.DISABLE_UPDATES: "1"
```

#### Defense-in-Depth

The `autoUpdates` key in `~/.claude.json` is considered deprecated by Anthropic (see [issue #3479](https://github.com/anthropics/claude-code/issues/3479)) and may stop working in future Claude Code releases. It is included as a defense-in-depth mechanism alongside the `DISABLE_AUTOUPDATER` and `DISABLE_UPDATES` environment variables, which are the primary update controls. The Claude Code auto-updater may also ignore disable settings in some versions (see issues [#10764](https://github.com/anthropics/claude-code/issues/10764), [#11263](https://github.com/anthropics/claude-code/issues/11263), [#12564](https://github.com/anthropics/claude-code/issues/12564)) -- covering all three targets provides the best protection.

### Several Profiles on One Machine

One machine has one Claude Code binary, so the controls that hold it at a pinned version are machine-global: `DISABLE_AUTOUPDATER`, `DISABLE_UPDATES`, and `CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL` in the OS environment, `autoUpdates` and `autoInstallIdeExtension` in `~/.claude.json`. A machine can carry several toolbox-managed profiles at once -- the base profile plus one isolated profile per `command-names` entry -- and a run of any of them must not undo what another one needs.

Each profile records its own pin in its installation manifest (Step 19): `~/.claude/manifest.json` for the base profile, `~/.claude/{cmd}/manifest.json` for each isolated profile. The `claude_code_version` field holds the normalized pin, or `null` when that profile tracks the latest release. Before applying auto-update settings, the setup reads every manifest except its own and decides on the whole machine:

- **This run pins a version:** it writes its own controls and sweeps nothing anywhere, whether or not another profile pins.
- **This run is unpinned and another installed profile pins:** nothing is swept, no OS-level deletion is scheduled, and the setup prints an info line naming the profiles that keep the controls in force.
- **This run is unpinned and a manifest cannot be read:** the pin cannot be ruled out, so the run behaves exactly as if another profile pinned and says so in the info line. A manifest that is absent, or present without a pin, is a definite answer and does not trigger this.
- **This run is unpinned and no other profile pins:** the sweep runs on this run's own profile -- its `settings.json` (except an environment control key the current YAML sets to a non-null value in `user-settings.env`), its `.claude.json` (except `autoUpdates` or `autoInstallIdeExtension` the current YAML sets to `false` in `global-config`), and the OS-level variables (except those the current YAML declares in `os-env-variables`). Stale controls the other installed profiles still hold are listed, with the profile name and file, in the installation summary before you confirm and again at the end of the run, and are never edited: re-run each listed profile's install to remove them.

The binary itself is held the same way. When this run is unpinned and another installed profile pins a version -- or a manifest cannot be read -- Step 1 keeps a working Claude Code installation at its version instead of upgrading it to the latest release: it runs `claude --version` and hands the installer that exact version, so the installer keeps the version while still performing its usual checks (an npm installation is migrated to native only when that exact version can be downloaded, and otherwise stays as it is), and the installation summary shows `Claude Code: keep the installed version <version>`. A binary that is missing, or that does not run, is installed at the version the pinning profiles pin when exactly one is known (with a warning when a manifest could not be read); when they pin different versions, or none is known, it installs the latest release and prints the warning in the installation summary as well. Changing the machine's Claude Code version is therefore done from a pinned profile: change its `claude-code-version` and re-run its setup.

An unpinned profile is protected by the machine-global controls rather than by its own files. Its isolated `~/.claude/{cmd}/config.json` is rebuilt from its own configuration on every run, so it carries `env.DISABLE_AUTOUPDATER` or `env.DISABLE_UPDATES` only when its own YAML pins a version or declares that variable; the OS-level `DISABLE_AUTOUPDATER`, `DISABLE_UPDATES`, and `CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL` the pinning profile wrote are inherited by every session started afterwards, including that profile's.

A profile's own manifest is matched by the `name` field it records, so a profile relocated with a user-set `CLAUDE_CONFIG_DIR` is recognized as its own rather than counted as another profile. A profile relocated outside `~/.claude/` altogether is not scanned, so its pin is invisible to the other profiles even though the controls it needs are machine-global. A manifest written without a pin -- including one that never recorded the field -- counts as unpinned; running that profile's setup again records its current pin.

A recorded pin is retired only by re-running that profile's setup with an unpinned configuration. A profile directory left behind -- a renamed command, an abandoned profile -- therefore keeps its pinned manifest, which holds the machine-global controls in force and keeps the Claude Code binary at its installed version on every unpinned run, indefinitely. Delete the stale `~/.claude/{cmd}/` directory, or just its `manifest.json`, to retire a pin whose profile is gone.

### Linked Profiles

A profile whose `link-dirs` names a content entry follows the profile it links from. Its directory holds links in place of those entries; its `config.json`, launchers, wrappers, `.claude.json`, env loaders and manifest are its own; and its configuration is the source's `resolved-config.yaml`: a run of the dependent (`--profile team-2`, or the configuration with `--command-names team-2`) applies that snapshot as installed in the source, components included, and fetches nothing. The source does the installing: a `files-to-download` destination that lies inside a linked entry, including one re-rooted from `~/.claude/...` (see [Paths that name the base config home](#paths-that-name-the-base-config-home)), is provided by the link, so the dependent's run skips it, keeps it out of its manifest's `files_written`, and lists it under `Provided by links` before you confirm. Each run of the source -- `--profile team-1`, or `--profile base` for the base profile -- ends with Step 23, which re-runs every profile whose manifest links content from it, by name, as a child run of `--profile NAME` with `--yes`, `--skip-install` and `--no-admin` (the command the Dependents block of the installation summary shows) and the parent's environment minus every `CLAUDE_CODE_TOOLBOX_*` argument twin except `CLAUDE_CODE_TOOLBOX_ENV_AUTH` and minus `CLAUDE_CONFIG_DIR`, so the repository tokens and `--env` values of the source run reach the dependents and its selectors and configuration do not. The installation summary names the dependents before you confirm, `--dry-run` lists them and starts none, and the completion summary of the source run reports each one and lists the installed profiles the run did not refresh; each child's own completion summary leaves that list to the source run, which covers every installed profile. A dependent that fails is named with the `--profile` command that retries it (and, when its configuration installs a global npm package the child could not elevate for, the note to retry from an elevated terminal), the others still run, and the source run exits 1. `--profile all` runs every source before its dependents and refreshes each profile once.

A dependent is checked on every run: after the dependency commands and again at the end, each link must still be a link to its target, or the run stops with the `--profile NAME` command that repairs it; before `config.json` is written, every hook file the events wire must exist through the linked `hooks/`, or the run stops and names the source to re-run first. A deselection in the source is applied by the source; the dependent's own deselection step never touches a linked section. While a dependent points at it, the source refuses to change its own links or configuration (a different configuration, `--link-dirs`, `--link-from`) and names each dependent with the two ways out: re-point it (`--profile NAME --link-from <other profile>`) or unlink it (`--profile NAME --link-dirs none`).

Two profiles can link the same entry from one source. A `projects` link needs none of this: it links to any profile, keeps the profile's own content and selection, and is never refreshed by the source. A content source is always a profile that holds its entries for real; linking from a profile that links content itself is refused with the profile to use instead.

```powershell
# Windows one-liner: iex (irm ...) takes no arguments, so the configuration, the names and the links come from the variables
powershell -NoProfile -ExecutionPolicy Bypass -Command "`$env:CLAUDE_CODE_TOOLBOX_ENV_CONFIG='team'; `$env:CLAUDE_CODE_TOOLBOX_COMMAND_NAMES='team-2'; `$env:CLAUDE_CODE_TOOLBOX_LINK_DIRS='all'; `$env:CLAUDE_CODE_TOOLBOX_LINK_FROM='team-1'; iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')"
```

### Automatic IDE Extension Version Management

When `claude-code-version` specifies a pinned version, the setup script also automatically disables IDE extension auto-installation and installs the matching extension version into detected VS Code family IDEs. When the version is `"latest"` or absent, IDE extension controls the YAML does not declare are removed, whether a prior pinned run or anything else set them, while user-declared controls are preserved.

This feature mirrors the [Automatic Auto-Update Management](#automatic-auto-update-management) architecture: same 3-target write matrix, same membership-gated WARN-but-Respect conflict resolution, same write-remove symmetry cleanup, same unpinned removal semantics (user declarations preserved in memory, OS-level deletion scheduled, on-disk cleanup via the Step 16 sweep), and the same machine-wide gate described in [Several Profiles on One Machine](#several-profiles-on-one-machine).

#### Injection Targets

| Target             | Key                                     | Value   | On-disk file (isolated)                           | On-disk file (non-isolated)                         |
|--------------------|-----------------------------------------|---------|---------------------------------------------------|-----------------------------------------------------|
| `global-config`    | `autoInstallIdeExtension`               | `false` | `~/.claude/{cmd}/.claude.json`                    | `~/.claude.json`                                    |
| `user-settings`    | `env.CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL` | `"1"`   | `~/.claude/{cmd}/config.json` (`env` key)         | `~/.claude/settings.json` (`env` key, deep-merge)   |
| `os-env-variables` | `CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL`     | `"1"`   | Shell profiles / Windows registry (machine-wide)  | Shell profiles / Windows registry                   |

All three targets are injected unconditionally regardless of whether `command-names` is present, consistent with auto-update management behavior. The `user-settings.env.CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL` control follows the standard `user-settings` routing: in isolated mode it is built into `~/.claude/{cmd}/config.json` (`env` key); in non-isolated mode it is deep-merged into `~/.claude/settings.json['env']`. Deep-merge recurses into the `env` dict so that the injected IDE control coexists with any user-declared environment variables in the same on-disk container. The `os-env-variables` control is machine-wide like its auto-update twins: an isolated run writes it to the OS environment, not to its loaders, and names it as `[machine-wide]` in the installation summary.

#### Removal Behavior

When the version is `"latest"` or absent, nothing is auto-injected, so every IDE extension control key present in the in-memory configuration comes from the user's YAML and is preserved -- identical to the auto-update twin. Two cleanup mechanisms remove the controls the YAML does not declare, whoever set them (a `null` for `CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL` in `user-settings.env` is a deletion request and does not keep the `settings.json` copy):

- **OS-level variable:** `CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL` has no filesystem sweep, so a deletion entry is scheduled in `os-env-variables` (unless the user explicitly declares the variable there, and not while another installed profile pins a version) and the OS environment writer removes the OS-level variable, whether a prior pinned run or anything else set it, from a base run and from an isolated run alike. Deleting an absent variable is a safe no-op on all platforms.
- **On-disk files:** Controls the YAML does not keep in the running profile's `settings.json` and `.claude.json` are removed by the Step 16 filesystem sweep described below, which likewise stands down while another installed profile pins a version; copies in other profiles are reported, never edited.

**Write-remove symmetry:** After all write operations, `cleanup_stale_ide_extension_controls()` runs alongside `cleanup_stale_auto_update_controls()` as a filesystem sweep pass (Step 16) with identical guards and the same profile confinement. When no installed profile pins a version, it removes `CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL` from the running profile's `settings.json` -- unless the current YAML itself sets the key to a non-null value in `user-settings.env`, in which case the `settings.json` sweep is skipped -- and removes `autoInstallIdeExtension: false` from the running profile's `.claude.json` (value-conditional: user-set `true` is preserved) unless the current YAML sets `autoInstallIdeExtension: false` in `global-config`. Copies in other profiles are listed in the installation summary, at Step 16, and in the final summary with the note to re-run that profile's install. While any profile pins a version, nothing is swept or reported.

#### Conflict Resolution (WARN-but-Respect)

Same rules as auto-update management: if the user explicitly sets a value that contradicts the automatic intent, the user value is preserved and a warning is emitted. A user `CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL` value that Claude Code reads as enabled (`1`, `true`, `yes`, or `on`, in any letter case) matches the intent without a warning; any other value is respected with a warning.

#### `[auto]` Marker in Installation Summary

Auto-injected IDE extension values are displayed with the same green `[auto]` marker, in the same summary block after the auto-update values:

```text
Settings added by the setup:
  [auto] global-config.autoInstallIdeExtension: false
  [auto] user-settings.env.CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL: "1"
  [auto] os-env-variables.CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL: "1"
```

#### VSIX Installation

When a version is pinned, the setup installs the matching Claude Code extension (`anthropic.claude-code`) into all detected VS Code family IDEs. The extension is platform-specific: the marketplace hosts a separate VSIX per OS/architecture pair (`targetPlatform`), so the setup first computes the host identifier as `{os}-{arch}` -- `os` is `win32`, `darwin`, `linux`, or `alpine` (when `/etc/alpine-release` exists), and `arch` is `x64` or `arm64`. Installation then uses a three-tier fallback chain:

1. **Tier 1 -- Bundled VSIX:** Check `~/.claude/local/node_modules/@anthropic-ai/claude-code/vendor/claude-code.vsix`. The file is opened as a zip archive and used only when its embedded `extension/package.json` version equals the pinned version AND its manifest's declared `TargetPlatform` (if any) matches the host. A version or platform mismatch, or an unreadable archive, falls through to Tier 2. No network download needed.
2. **Tier 2 -- Marketplace CDN download:** Download the platform-specific VSIX from the VS Code Marketplace CDN by appending `?targetPlatform={os}-{arch}` to both the primary and fallback URLs (without the parameter, the marketplace serves an arbitrary platform's build of this platform-specific extension). Gzip-encoded response bodies (served by the fallback endpoint) are decompressed, and every payload is validated against the zip magic prefix before use. The VSIX is written to a temp file, installed via `--install-extension <path> --force`, then cleaned up. Skipped entirely (in favor of Tier 3) when the host OS or architecture has no known marketplace identifier.
3. **Tier 3 -- Marketplace @version syntax:** Use `anthropic.claude-code@{version}` syntax directly; the IDE resolves its own targetPlatform. Emits a warning because VS Code may auto-update the extension despite version pinning. Also reached when a downloaded payload is invalid or the temp-file write fails.

**Version-missing skip:** When every Tier 2 download URL returns HTTP 404, the pinned Claude Code version has no matching extension in the marketplace for the host targetPlatform (extension version gaps are real). The setup prints a warning naming the version and targetPlatform, skips IDE extension installation, and the IDEs keep their current extension -- this counts as success, not failure, and Tier 3 is not attempted. The warning only fires after at least one IDE was detected. Non-404 download failures (network errors, 5xx) keep the Tier 3 fallback and its auto-update warning.

Installation is **non-fatal**: failures produce warnings but do not abort the setup.

#### VSIX Auto-Update Behavior

The three installation tiers have different auto-update implications for the installed extension:

| Tier   | Method               | Auto-Update Status                             |
|--------|----------------------|------------------------------------------------|
| Tier 1 | Bundled VSIX         | **Disabled by default** (VS Code v1.92+)       |
| Tier 2 | Downloaded VSIX      | **Disabled by default** (VS Code v1.92+)       |
| Tier 3 | Marketplace @version | **Active** -- VS Code may update the extension |

Since VS Code v1.92, extensions installed via VSIX files (Tiers 1 and 2) have auto-update disabled by default. This is the primary defense mechanism for version pinning -- the installed extension stays at the pinned version without any additional IDE-level configuration.

Tier 3 (marketplace @version syntax) is a last-resort fallback that triggers when no usable bundled VSIX exists AND the marketplace CDN download is unavailable -- the host targetPlatform is unknown, the download fails for a non-404 reason, the payload is not a valid VSIX archive, or the temp-file write fails. (When all download URLs return 404, the setup skips installation with a warning instead of reaching Tier 3 -- see Version-missing skip above.) In the Tier 3 case, VS Code may auto-update the extension despite version pinning, so the setup emits a warning with instructions to manually disable auto-update for the extension:

> In VS Code's Extensions view, right-click the Claude Code extension and set "Auto Update" to off.

This per-extension "Auto Update" toggle is the only targeted control available. There is no `settings.json` key for per-extension auto-update exceptions -- the only JSON setting (`extensions.autoUpdate: false`) disables auto-update for ALL extensions, which is too broad.

**JetBrains IDEs:** JetBrains IDEs use their own plugin ecosystem and do not support VSIX extensions. The Claude Code JetBrains plugin is versioned independently from the CLI, and there is no external mechanism to control per-plugin auto-update from outside the IDE. The existing `autoInstallIdeExtension: false` control is the only applicable protection for JetBrains.

#### VS Code Family IDE Detection

Detection runs in two passes. First, `shutil.which()` checks PATH for each CLI name: `code`, `code-insiders`, `cursor`, `windsurf`, `codium`. Then, for CLI names not found on PATH, well-known install locations are probed (results are deduplicated by CLI name, with a PATH hit always winning):

- **macOS:** App bundles under `/Applications` and `~/Applications` for all five IDEs (for example, `Visual Studio Code.app/Contents/Resources/app/bin/code`) -- drag-and-drop installs do not register the `code` CLI on PATH
- **Linux:** `/usr/bin/code`, `/usr/share/code/bin/code`, `/snap/bin/code`, and the system and per-user Flatpak exports of `com.visualstudio.code`
- **Windows:** `%LOCALAPPDATA%\Programs\Microsoft VS Code\bin\code.cmd`

The extension is installed into all detected IDEs. If no IDEs are detected, the step is a silent no-op.

JetBrains IDEs are excluded because they use their own plugin ecosystem and do not support VSIX extensions.

#### Process Environment Early-Set

When a version is pinned, `CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL=1` is set in the process environment before Step 1 (Claude Code installation). This prevents the Claude Code CLI from auto-installing IDE extensions during the installation process itself.

### Configuration Sources

The setup script determines the configuration source by checking in this order:

1. **URL:** Starts with `http://` or `https://` -- fetched directly from the web
2. **Local file:** Contains path separators (`/`, `\`), starts with `./` or `../`, is an absolute path, or the file exists on disk -- loaded from the local filesystem
3. **Repository config:** Everything else -- `.yaml` is added if missing, then fetched from `https://raw.githubusercontent.com/alex-feel/claude-code-artifacts-public/main/{name}.yaml`

### Setup-Time `CLAUDE_CONFIG_DIR` Export

When `command-names` creates an isolated profile, the setup script exports `CLAUDE_CONFIG_DIR` into its own process environment (set to the isolated profile directory, for example `~/.claude/{cmd}`) early in `main()`, before any resources are processed. Child processes spawned during setup -- dependency installers, `npx`-based tooling, `claude mcp ...` calls, and the IDE-extension installer -- inherit this value and therefore resolve against the isolated profile directory instead of the default `~/.claude/`. For example, `npx <skill-installer>` launched during setup installs into the isolated profile rather than the home-directory Claude.

This setup-time export is transient and process-scoped: it lives only for the duration of the setup process and is deliberately never written to `config.json` or any other on-disk settings file. It exists purely so setup-time child processes target the correct directory.

The two `CLAUDE_CONFIG_DIR` channels are orthogonal and serve different lifetimes:

| Channel                          | When it applies            | Scope                                          | Source                                                |
|----------------------------------|----------------------------|------------------------------------------------|-------------------------------------------------------|
| Setup-time process export        | During `setup_environment` | Child processes spawned by the setup script    | `os.environ['CLAUDE_CONFIG_DIR']` set in `main()`     |
| Runtime launcher export          | When you run the command   | The launched Claude Code session and its tools | `export CLAUDE_CONFIG_DIR` in the generated launcher  |

The runtime launcher export (documented in [Cross-Shell Launcher Architecture](cross-shell-launcher-architecture.md)) remains the sole authoritative runtime source. The setup-time export only governs processes started during installation. The per-call MCP `CLAUDE_CONFIG_DIR` injection (see the [Isolated environments](#scope-options) note under MCP Servers) is retained independently, because the Windows MCP code path builds a curated environment for child processes rather than inheriting the full `os.environ`.

#### Running Setup From Inside An Isolated Profile Session

An isolated command exports `CLAUDE_CONFIG_DIR` for the session it launches, so a setup run started from a terminal inside that session inherits the variable; a base configuration can also persist it through `os-env-variables`, and any configuration through a `user-settings.env` entry, in which case every terminal (or every session of that profile) carries it. The Claude CLI resolves `CLAUDE_CONFIG_DIR` ahead of the home directory and offers no fallback, so the inherited value decides where `claude mcp add` and the global-config writes land. Any non-empty value counts, matching the CLI. The setup checks the variable as soon as it knows the directory the run targets -- before the component picker, the Windows elevation prompt and the installation summary -- so no prompt precedes the outcome and `--dry-run` reports it too:

- **Configuration without `command-names`:** the run is refused with exit code 1. The toolbox targets the base `~/.claude` directory and the base global config is `~/.claude.json`, but the CLI would use `$CLAUDE_CONFIG_DIR/.claude.json` instead -- splitting one run across two directories. Clear the variable (`unset CLAUDE_CONFIG_DIR` in bash, `Remove-Item Env:CLAUDE_CONFIG_DIR` in PowerShell), run the setup from a terminal that is not inside an isolated profile session, or remove the variable from the configuration that persists it and open a new terminal.
- **Configuration with `command-names`:** the run proceeds. When the inherited value differs from the profile directory this run targets, the setup reports that it replaces the value for its child processes and names the profile it is actually configuring. An inherited value equal to the target directory -- setting up a profile from inside its own session -- needs no report.

### Cross-Shell Command Registration (Windows)

On Windows, the setup creates global commands that work across all shells (PowerShell, CMD, Git Bash) through a set of launcher and wrapper scripts. The launchers live in the profile directory, `~/.claude/{command}/` unless a [`CLAUDE_CONFIG_DIR` override](#claude_config_dir-override-isolated-mode) moves it, and every script names that directory:

- Shared POSIX launcher (`launch.sh`) -- the actual launcher executed by Git Bash
- PowerShell wrapper (`start.ps1`) -- invokes launch.sh via Git Bash
- CMD wrapper (`start.cmd`) -- invokes launch.sh via Git Bash
- Global wrappers in `~/.local/bin/` (`{command}`, `{command}.ps1`, `{command}.cmd`, and the same set for each alias) -- entry points that delegate to the above

`launch.sh` also limits a session you start in your home folder to the profile's own settings sources (`--setting-sources user`), because the home folder's `.claude` is the base profile and would otherwise apply as the project settings of that session; it compares the two directories by identity, so the letter case or short name you spell the folder with makes no difference. On Windows it also starts the session in the long spelling of the folder you started in, so a path spelled by 8.3 short names (`%TEMP%` spells a home folder whose account name is longer than eight characters that way) does not make Claude Code read the base profile's skills, agents and commands as a project's (see [Isolated Mode](#isolated-mode-command-names-present)).

`launch.sh` keeps slash commands intact: Git Bash passes an argument that starts with a single `/` and names no existing path to Claude Code as `launch.sh` received it, so a slash command arrives unchanged. The quoting rules of cmd.exe and Windows PowerShell still apply before `launch.sh` sees an argument: when Windows PowerShell 5.1 passes on an argument that holds double quotes, the quotes can disappear or the argument can split into several. Git Bash runs `launch.sh`, and it rewrites any argument that looks like a POSIX path when it starts `claude.exe`: left alone, `my-env -p "/review src"` would hand Claude Code `C:/Program Files/Git/review src`. `launch.sh` therefore lists each argument that starts with a single `/` and names no existing path in `MSYS2_ARG_CONV_EXCL` for that launch, and Git Bash passes listed arguments unchanged. An argument that is exactly an existing path keeps its conversion: `/c/work` arrives as `C:/work`, as do a bare `/tmp` and `/usr`, while `/usr review` names no path and arrives unchanged. A launch with a listed argument hands the variable on to the session: one entry arrives in its Windows spelling, such as `C:/Program Files/Git/review src`, several arrive as listed, and entries you set yourself stay in the list. Git Bash started from the session, as the Bash tool starts it, keeps converting every path that starts with none of the listed texts, such as `/tmp/...`. A launch without a listed argument leaves `MSYS2_ARG_CONV_EXCL` as it found it.

For the full technical architecture, see [Cross-Shell Launcher Architecture](cross-shell-launcher-architecture.md).

## What Happens When You Run Setup

Here is a conceptual overview of what the setup script does when you run it with a configuration:

1. **Install Claude Code** -- Runs the `install_claude.py` that ships beside the setup script (the PyPI wheel and the bootstrap wrappers stage both files together) under the interpreter already running the setup, on every platform; without a bundled copy, downloads and runs the platform bootstrap script. The installer uses the native installer with npm fallback. Skipped with `--skip-install`. An unpinned run on a machine where another installed profile pins a version requests the installed version instead of the latest release (see [Several Profiles on One Machine](#several-profiles-on-one-machine)).
2. **Install IDE extensions** -- Installs the pinned-version Claude Code extension into detected VS Code family IDEs, selecting the VSIX build matching the host targetPlatform. Skipped if no version is pinned or `--skip-install` is used. When the pinned version has no matching marketplace extension for the host platform (every download URL returns HTTP 404), the step prints a warning and skips installation, leaving each IDE's current extension in place.
3. **Create directories and links** -- Creates `~/.claude/agents/`, `commands/`, `rules/`, `prompts/`, `hooks/`, and `skills/` directories, and for a profile with `link-dirs` every link before any content step: a missing link is created, a link that points elsewhere is repaired, and a real directory with content is moved aside only when a value typed for this run asks for it (see [`link-dirs`](#link-dirs)).
4. **Download custom files** -- Processes `files-to-download` entries.
5. **Install Node.js** -- If `install-nodejs: true` is set in the config.
6. **Install dependencies** -- Runs platform-specific dependency commands. Failed global npm installs are retried with sudo on Linux/macOS/WSL when the npm global prefix is not user-writable; every failed dependency is listed in the end-of-run error block and causes exit code 1.
7. **Set OS environment variables** -- A base run writes every `os-env-variables` entry to the OS environment (a `null` value deletes the variable). An isolated run writes only the three machine-wide binary controls there and rebuilds its env loader files from every other entry (`env.sh`, which `launch.sh` sources at session start, plus `env.fish`, `env.ps1` and `env.cmd` for sourcing by hand), `null` entries as unset lines -- header-only when the configuration declares no profile variable, so stale lines are cleared.
8. **Process agents** -- Downloads agent Markdown files to `~/.claude/agents/`.
9. **Process slash commands** -- Downloads command files to `~/.claude/commands/`.
10. **Process rules** -- Downloads rule Markdown files to `~/.claude/rules/`.
11. **Process skills** -- Downloads skill file sets to `~/.claude/skills/{name}/`.
12. **Process system prompt** -- Downloads the prompt file if configured.
13. **Configure MCP servers** -- Sets up MCP servers with scope-based routing.
14. **Write user settings** -- In non-isolated mode, deep-merges `user-settings` into `~/.claude/settings.json`. In isolated mode, this write is skipped -- the `user-settings` content is built into the profile's `config.json` at Step 18.
15. **Write global config** -- Merges `global-config` into the run's own `.claude.json`: `~/.claude.json` without `command-names`, `~/.claude/{cmd}/.claude.json` with. With `command-names`, also propagates the machine's recorded `installMethod` from the base `~/.claude.json` (read, never written) into the isolated `.claude.json`.
16. **Cleanup stale controls** -- Removes the auto-update and IDE extension controls the current YAML does not keep from the running profile's `settings.json` and `.claude.json`, whoever set them, preserving `settings.json` keys the YAML sets to a non-null value in `user-settings.env` and `.claude.json` keys it sets to `false` in `global-config`; stale copies found in other profiles are listed with the profile name and file and left for that profile's own re-run. The sweep runs only when no installed profile pins a Claude Code version; while any profile does, every location keeps its controls.
17. **Download hooks** -- Downloads the `hooks.files` scripts and the `hooks.helpers` modules to `~/.claude/{cmd}/hooks/` (with `command-names`) or `~/.claude/hooks/` (without). In non-command-names mode, Step 17 runs when ANY of the following are declared: `hooks.events` non-empty, `hooks.files` non-empty, `hooks.helpers` non-empty, or `status-line.file` set.
18. **Write profile settings** -- Writes the profile-owned keys (`statusLine`, `hooks`) as camelCase keys on disk. With `command-names`: writes `~/.claude/{cmd}/config.json` via `create_profile_config()`, merging the `user-settings` content, including the `claudeMdExcludes` entries that keep the base profile's `CLAUDE.md`, `CLAUDE.local.md` and rules out of the profile's sessions, with the built `statusLine`/`hooks` entries (atomic overwrite -- fresh dict each run). Without `command-names`: writes to `~/.claude/settings.json` via `write_profile_settings_to_settings()`, which delegates to `_write_merged_json()` for **deep-merge, universal array union at every depth, and RFC 7396 null-as-delete** (preserves non-delta keys; see [Profile-Level Settings Routing](#profile-level-settings-routing)).
19. **Write manifest** -- Creates the profile's installation tracking manifest: `~/.claude/{cmd}/manifest.json` with `command-names`, `~/.claude/manifest.json` without. Records the run's `claude-code-version` pin so any later run can tell whether another profile still needs the machine-global auto-update controls.
20. **Create launcher** -- Creates the launcher script for the command; it limits a session started in the home folder to the profile's own settings sources. (Only if `command-names` is specified.)
21. **Register commands** -- Creates global command wrappers. (Only if `command-names` is specified.)
22. **Remove deselected components** -- Uninstalls previously installed artifacts of deselected components: MCP servers, skill directories, agent/command/rule/hook/downloaded files, and shared-settings hook entries. Runs in both modes, only when the selection deselects at least one claimed item, and never touches a linked section.
23. **Refresh dependent profiles** -- Re-runs every installed profile that links content from this one, each as its own child run (see [Linked Profiles](#linked-profiles)). `--dry-run` lists the dependents and starts none. A child run (one `--profile all` starts, or a dependent this step refreshes) leaves the refresh, and the completion summary's list of profiles the run did not refresh, to the run that started it.

Step 17 is skipped if no hooks, hook files, or status-line file are configured. In non-isolated mode, Step 18 is a no-op if the profile delta is empty -- no `status-line` or `hooks` declared at YAML root level. Steps 20-21 are skipped if `command-names` is not specified. In a profile that links content, Steps 8-12 and 17 report each linked section as linked and install nothing for it, and the links are verified after Step 6 and after Step 22.

## Profile-Level Settings Routing

The setup script supports two modes of profile-settings routing, controlled by the presence of `command-names:` in the YAML configuration. This section documents how the profile-owned keys (`status-line`, `hooks`) and the `user-settings` content land on disk in each mode.

### Profile-Owned Keys

Two YAML root-level keys are **profile-owned** -- they are extracted from YAML root, translated to camelCase, and written to disk by the profile-settings subsystem (`_build_profile_settings()` builder + one of two writers) because they require toolbox-side processing (file download, absolute-path command construction):

| YAML root key (kebab-case)    | On-disk key (camelCase)   |
|-------------------------------|---------------------------|
| `status-line`                 | `statusLine`              |
| `hooks`                       | `hooks`                   |

The shared pure builder `_build_profile_settings()` performs status-line command-string construction and delegates to `_build_hooks_json()` for the `hooks` universe. The 2-key set is declared as `PROFILE_OWNED_KEYS = frozenset({'statusLine', 'hooks'})` in `scripts/setup_environment.py`, and the mapping of YAML kebab-case root keys to camelCase on-disk names is declared as the module-level constant `_YAML_TO_CAMEL_PROFILE_KEYS`. These keys match `USER_SETTINGS_EXCLUDED_KEYS = {'hooks', 'statusLine'}` exactly: they are forbidden inside `user-settings` because the toolbox owns their processing, while every other `settings.json` key is declared under `user-settings` (see [`user-settings`](#user-settings)).

### Isolated Mode (command-names present)

When `command-names` is specified, the setup creates an isolated directory `~/.claude/{cmd}/` (or the directory a [`CLAUDE_CONFIG_DIR` override](#claude_config_dir-override-isolated-mode) names). The `config.json` file carries the complete `settings.json` content -- the `user-settings` section plus the toolbox-built `statusLine` and `hooks` entries -- and the toolbox does not write the isolated `settings.json`:

| File          | Priority (CLI)   | Content                                                         | Writer                    | Step | Semantics                                              |
|---------------|------------------|-----------------------------------------------------------------|---------------------------|------|--------------------------------------------------------|
| `config.json` | 2 (flagSettings) | `user-settings:` content + built `statusLine` / `hooks` entries | `create_profile_config()` | 18   | Atomic overwrite (fresh dict each run; nulls stripped) |

The launcher script passes `config.json` via the `--settings` flag (command-line settings layer, priority 2) and sets `CLAUDE_CONFIG_DIR` to the isolated directory. Because `--settings` outranks a repository's project settings, the isolated profile's settings are enforced -- exactly what an isolated environment exists to provide. The `user-settings` section and the built `statusLine`/`hooks` entries are disjoint by construction, because `statusLine` and `hooks` are rejected inside `user-settings`. In isolated mode, stale-key accumulation is NOT a concern because `create_profile_config()` uses atomic overwrite: every run produces a fresh `config.json` containing only the currently-declared keys, so removing a key from YAML cleanly removes it from `config.json` on the next run. Null-valued dict members at every depth are stripped before the write (absence expresses deletion under atomic rebuild), so a literal JSON null is never written.

A session of an isolated profile reads nothing from the base profile's `~/.claude`, wherever you start it. Claude Code treats the folder you start in as the project and its `.claude` directory as the project settings, and it reads the `.claude` directory of every folder above it for memory, so a session started in your home folder would otherwise take `~/.claude/settings.json` (its `env`, `apiKeyHelper`, `model` and hooks) as project settings, a session started in any project below your home would load `~/.claude/CLAUDE.md` and `~/.claude/rules/`, and a session started inside `~/.claude` itself or inside the profile's own directory would load `~/.claude/CLAUDE.local.md` too. The setup closes every path for every isolated profile; you change nothing in the configuration. `config.json` carries `claudeMdExcludes` entries for `~/.claude/CLAUDE.md`, `~/.claude/CLAUDE.local.md` and `~/.claude/rules/**`, spelled as absolute paths with forward slashes and with every letter written as a case class (`[cC]:/[uU][sS][eE][rR][sS]/...`): Claude Code matches the patterns case-sensitively against paths it builds from the folder you started in, spelled the way you or your shell spelled it, and cmd.exe keeps a lowercase drive letter after `cd /d c:\...`. On Windows the same three entries are repeated for the 8.3 short spelling of your home folder when Windows gives one that differs (`C:/Users/CHRIST~1/.claude/...`, every letter a case class as well): Windows spells a home folder whose account name is longer than eight characters short in `%TEMP%` and `%TMP%`, and a session started under such a path builds its ancestor paths from that spelling, whether the folders below your home are spelled long, as `%TEMP%` spells them, or short. A path that spells a folder above your home short while your home folder itself stays long (`C:\DOCUME~1\Me\...`) matches neither set, so a session started under such a path still loads the base `CLAUDE.md` and rules. The entries are added to any `claudeMdExcludes` your `user-settings` declares and listed in the installation summary as `[auto] user-settings.claudeMdExcludes: ...`; a profile whose `rules/` is linked from the base profile keeps the rules entry out, because the base rules are that profile's own rules. The launcher passes `--setting-sources user` when the session starts in your home folder, so the base profile's `settings.json` and `settings.local.json` stay out there while the profile's own `settings.json`, `config.json`, MCP configuration and system prompt still apply. On Windows the launcher also starts the session in the long spelling of the folder you started in: Claude Code tells your home folder's `.claude` apart from a project's `.claude` by spelling, so a session started under the 8.3 short spelling of your home folder (`C:\Users\CHRIST~1\...`, the spelling of `%TEMP%`) would otherwise load the base profile's skills, agents and commands as a project's, and no exclusion setting reaches those. The launcher changes to the long spelling only when `cygpath` names the same folder, and leaves the folder as it was otherwise. Claude Code has no finer source than `project`, so a session started in the home folder itself also loads neither a `CLAUDE.md`, `CLAUDE.local.md` nor `.mcp.json` of the home folder. Anywhere else the working project's own `.claude` settings, hooks, `CLAUDE.md`, `CLAUDE.local.md` and rules load as before, and the home folder's `CLAUDE.md`, `CLAUDE.local.md` and `.mcp.json`, which lie outside `~/.claude`, load below the home as the home folder's own project files (a profile with profile-scoped MCP servers reads no `.mcp.json` anywhere, because its launcher passes `--strict-mcp-config`). An argument you pass yourself, such as `--setting-sources user,project`, comes after the launcher's and wins. A base profile excludes nothing: `~/.claude` is its own config home.

Everything else an isolated run writes stays inside `~/.claude/{cmd}/` as well: its `.claude.json` (the `global-config` section, the propagated `installMethod`, and the MCP registrations of `user`/`local` scope), its `manifest.json`, `mcp.json`, launchers, and env loaders. An isolated run never writes the base profile's `~/.claude/settings.json`, and it writes `~/.claude.json` only through the Claude Code installer, which records `installMethod` there when Step 1 installs, upgrades, or migrates the binary, so installing a base configuration as an isolated profile leaves the base profile's account and settings as they were. The writes that do leave the profile directory are the machine-wide ones every profile shares, and the installation summary (and `--dry-run`) lists each of them under `Machine-wide writes` before you confirm: the Claude Code binary install, upgrade, or kept version together with the `installMethod` the installer records in `~/.claude.json`, a `claude-code-version` pin holding that binary, the IDE extension Step 2 installs at that pin into every detected VS Code family IDE (the row names the detected IDEs and is absent when none is detected or `--skip-install` skips Step 2), each OS-level `DISABLE_AUTOUPDATER`, `DISABLE_UPDATES`, and `CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL` write or deletion, the command wrappers in `~/.local/bin`, project-scope MCP servers in the working directory's `.mcp.json`, `files-to-download` destinations outside the profile directory, and the dependency commands. A `files-to-download` destination, or an `apiKeyHelper` or `awsCredentialExport` value, that names the base `~/.claude` is not among them: an isolated run re-roots it into the profile directory and lists it under `Re-rooted into the profile` instead, with no `Machine-wide writes` row (see [Paths that name the base config home](#paths-that-name-the-base-config-home)). A dependency command that names it is re-rooted too, marked `[re-rooted]` in the `Dependencies (shell commands)` block, and still listed in the `Dependency commands` row, because it runs on the machine and can write anywhere. The completion summary then names the files the run wrote: `User settings: built into ~/.claude/{cmd}/config.json` and `Global config: configured in ~/.claude/{cmd}/.claude.json` for an isolated run, `~/.claude/settings.json` and `~/.claude.json` for a base run.

### Non-Isolated Mode (command-names absent)

When `command-names` is ABSENT, the setup writes to the shared `~/.claude/` directory. BOTH Step 14 and Step 18 target the SAME file (`~/.claude/settings.json`) and BOTH use the same READ-MERGE-WRITE contract inherited from `_write_merged_json()`:

| File                       | Content                                            | Writer                                  | Step | Semantics                                                                    |
|----------------------------|----------------------------------------------------|-----------------------------------------|------|------------------------------------------------------------------------------|
| `~/.claude/settings.json`  | YAML `user-settings:` (all non-excluded keys)      | `write_user_settings()`                 | 14   | Deep merge + universal array union at every depth + RFC 7396 null-as-delete  |
| `~/.claude/settings.json`  | `statusLine`/`hooks` delta from YAML root          | `write_profile_settings_to_settings()`  | 18   | Deep merge + universal array union at every depth + RFC 7396 null-as-delete  |

1. **Step 14** deep-merges `user-settings:` into `settings.json`. Existing keys are preserved; for leaf scalar conflicts the new YAML values overwrite the existing values; every list at every depth is unioned with structural dedupe; `null` values delete keys via RFC 7396.
2. **Step 18** deep-merges the `statusLine`/`hooks` delta into the same file using the same semantics. Existing keys not in the delta are preserved; existing nested dicts are recursively merged with the delta; every list at every depth is unioned with structural dedupe across both steps; top-level or nested `null` in the delta deletes keys.

Under this contract, the shared `~/.claude/settings.json` is never scrubbed of keys the current YAML does not declare, and contributions from manual user edits, other YAML configurations, the Claude Code CLI itself, and the Step 14 `user-settings` write all survive the profile-settings write at Step 18. List-valued keys (such as `permissions.allow/deny/ask/additionalDirectories`, `companyAnnouncements`, `hooks.<EventName>` matcher-group lists, `sandbox.filesystem.*` path lists, `disabledMcpjsonServers`/`enabledMcpjsonServers`) accumulate additively across runs, matching [Claude Code CLI's documented cross-scope merge semantics](https://code.claude.com/docs/en/settings): "arrays are concatenated and deduplicated, not replaced".

### Write Semantics Contract

**Design principle:** `~/.claude/settings.json` is a SHARED/COMMON user-facing file. The toolbox treats it as a collaborative surface: other writers (the user, the CLI, other YAML configurations) contribute keys the current run knows nothing about, and the shared-settings writers preserve those contributions while still allowing explicit deletion via YAML-level null. Matches [Claude Code CLI's documented cross-scope merge semantics](https://code.claude.com/docs/en/settings): "arrays are concatenated and deduplicated, not replaced".

`write_profile_settings_to_settings()` delegates to `_write_merged_json()`, which implements the three-step READ-MERGE-WRITE process:

1. **READ** the existing `~/.claude/settings.json` (or start fresh with an empty dict if the file is missing, malformed, or has a non-dict top-level value; a warning is emitted in those cases).
2. **DEEP MERGE** the builder delta into the existing content via `_merge_recursive()`, which handles:
   - **Deep recursion** into nested dicts (for example, a delta `hooks: {PostToolUse: [...]}` updates only the `PostToolUse` sub-key of `hooks`, leaving other event names intact if not in the delta).
   - **Universal array union** at every depth via Python structural equality -- existing and new arrays are combined, order-preserving (existing elements first), with duplicate elements removed. Applies to every list-valued key at any nesting level, matching Claude Code CLI's cross-scope merge semantics.
   - **RFC 7396 null-as-delete**: any value of `None` in the delta (top-level or nested) deletes the corresponding key from the target via `target.pop(key, None)`; a nested dict landing on a key the file lacks (or on a non-object member) is applied onto an empty object, so its `None` members are dropped rather than written as JSON `null`.
   - **Scalar overwrite** on leaf conflicts (new value wins).
3. **WRITE** the merged result back to disk with a trailing newline for file-format consistency.

The builder `_build_profile_settings()` accepts a `profile_config` dict keyed by the camelCase on-disk names; dict membership encodes the YAML declaration state (present-with-value, present-with-null, or absent) end-to-end so that the downstream writer can apply RFC 7396 null-as-delete to the shared `settings.json` for both top-level and nested YAML nulls. `main()` constructs `profile_config` with a comprehension that iterates `_YAML_TO_CAMEL_PROFILE_KEYS` and includes a key when `yaml_key in config`, which preserves the distinction between "absent from YAML" (key omitted from `profile_config`, on-disk value preserved) and "declared with explicit null" (`profile_config[camel_key] = None`, on-disk value deleted).

**Merge cases for each key in the delta:**

| Case                           | Builder output            | Writer on-disk effect                                                                           |
|--------------------------------|---------------------------|-------------------------------------------------------------------------------------------------|
| YAML declares `key: scalar`    | `{'key': scalar}`         | Scalar overwrite (leaf wins)                                                                    |
| YAML declares `key: {nested}`  | `{'key': {nested}}`       | Deep-merge (recurse into sub-keys; nested lists also unioned at every depth)                    |
| YAML declares `key: [list]`    | `{'key': [list]}`         | Union with structural dedupe at every depth (elements added additively, duplicates removed)     |
| YAML declares `key: []`        | `{'key': []}`             | No-op under union semantics (empty list adds nothing; use `null` to clear)                      |
| YAML declares `key: null`      | `{'key': None}`           | DELETE the key from the file (RFC 7396 null-as-delete)                                          |
| YAML omits `key`               | key absent from delta     | PRESERVE existing value unchanged                                                               |

**Null-as-delete is supported for both profile-owned keys** (`status-line`, `hooks`), and for every key written by the shared-settings writers, both at the top level (`status-line: null`, `hooks: null`) and nested (`hooks: {PreToolUse: null}`). The top-level and nested cases go through the same `_merge_recursive()` path inside the writer; the top-level path additionally requires the dict-membership threading in `profile_config` to survive main()'s YAML extraction.

**Preservation coverage (what survives shared-settings writes):**

Keys absent from the delta are preserved in `~/.claude/settings.json`. This covers:

- Prior contributions from `write_profile_settings_to_settings()` itself across other YAML configurations, including list-valued keys (which accumulate additively under the universal array-union contract).
- Deep-merged contributions from Step 14 `write_user_settings()` (all `user-settings` keys -- `model`, `permissions`, `env`, `effortLevel`, and everything else -- with list-valued keys unioned with structural dedupe across Step 14 and Step 18).
- User-managed keys outside the toolbox's YAML schema (for example, `includeGitInstructions`, `apiKeyHelper`, `cleanupPeriodDays`, `outputStyle`, `autoMemoryDirectory`, `sandbox.*`, user-managed array-valued keys like `companyAnnouncements` or `permissions.additionalDirectories`).
- Auto-injected `env.DISABLE_AUTOUPDATER` and `env.DISABLE_UPDATES` (auto-update) and `env.CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL` (IDE extension) controls, which are injected into `user-settings.env` and written by Step 14: because deep-merge recurses into the `env` dict, the injected controls coexist with any user-declared environment variables and survive the Step 18 write, which touches only `statusLine`/`hooks`. (Pinned runs perform no Step 16 sweep, so these controls also survive the cleanup pass -- see [Automatic Auto-Update Management](#automatic-auto-update-management).)
- Elements written to list-valued keys by any prior contributor (manual user edits, the Claude Code CLI, teammate YAMLs): new elements from the current YAML are unioned with the existing list rather than replacing it.

**Empty-delta no-op:** If neither `status-line` nor `hooks` is declared at YAML root level, the builder returns `{}` and `write_profile_settings_to_settings()` performs ZERO file I/O -- it neither creates nor touches `~/.claude/settings.json`. A YAML with only `user-settings:`, `global-config:`, `agents:`, and so on will never have Step 18 modify `settings.json`; the `user-settings` content (including auto-injected env controls) reaches `settings.json` through Step 14 instead.

**Malformed or non-dict existing content:** If `~/.claude/settings.json` contains invalid JSON, unreadable content, or a non-dict top-level value (for example, a bare list), `_write_merged_json()` emits a warning (`"Existing ... is not a dict, starting fresh"` or `"Invalid JSON in ..."`) and starts fresh (treats the existing content as `{}`). The written file ends with a trailing newline for file-format consistency with `write_user_settings()` and `write_global_config()`.

### Null-as-Delete for Profile-Owned Keys (YAML contract)

Both profile-owned keys (`status-line`, `hooks`) support null-as-delete at the YAML root level in non-command-names mode. Every other `settings.json` key deletes the same way from under `user-settings` (see [Key Deletion](#key-deletion-null-as-delete)). Examples:

```yaml
# Delete the entire hooks block from settings.json
hooks: null

# Delete just one event list (keep other event names)
hooks:
    PreToolUse: null

# Delete the status-line key
status-line: null

# Delete a settings.json key managed under user-settings
user-settings:
    model: null
    permissions: null
```

**Top-level null vs nested null:**

- **Top-level null** (for example, `hooks: null`): the entire top-level key is removed from `~/.claude/settings.json` via `existing.pop('hooks', None)`.
- **Nested null** (for example, `hooks: {PreToolUse: null}`): deep-merge recurses into the `hooks` dict, and the `PreToolUse` sub-key is removed while other event names are preserved.

Both cases are handled by `_merge_recursive()` inside `_write_merged_json()`. The top-level case additionally requires the dict-membership construction in `main()` and the builder so that the profile_config can carry `None` for top-level YAML nulls -- a plain `config.get('hooks')` would otherwise erase the distinction between "absent" and "null".

**Re-run semantics:** After `hooks: null` has been applied, removing the `hooks: null` line from the YAML (so the key is absent) in a later run preserves the `hooks` key's then-current state (which is "absent from settings.json", unchanged by the new no-op delta). There is no auto-undelete -- once deleted, a key stays deleted until a subsequent YAML explicitly re-declares it with a non-null value.

### Deferred Stale-Key Behavior (User-Facing Contract)

This is an INTENTIONAL user-facing contract, not a bug. Understanding this behavior is critical to using `command-names`-absent mode correctly.

**Scenario:** You had `user-settings: {permissions: {allow: [Read]}}` in one setup run. You then remove the entire `permissions` block from your `user-settings` and re-run setup.

**Result:** The `permissions` key in `~/.claude/settings.json` retains its existing on-disk value (`{allow: [Read]}`). It is NOT deleted.

**Why:** `~/.claude/settings.json` is a shared file. Removing a key from YAML is NOT a sufficient signal for the toolbox to delete that key from the shared file, because:

1. The key might have been set by a setup run that used a different YAML configuration.
2. The key might have been set manually by the user or by another tool.
3. The key might have been set by a teammate's YAML that is managed separately.
4. The profile-settings writer has no state-tracking sidecar to distinguish keys it wrote in prior runs from user-managed keys.

**To remove a key, you have two explicit options:**

1. **Set the key to `null` in YAML.** Examples:
   ```yaml
   hooks: null                     # Delete hooks block (profile-owned, YAML root)
   status-line: null               # Delete statusLine (profile-owned, YAML root)
   user-settings:
       permissions: null           # Delete entire permissions block from settings.json
       model: null                 # Delete model key
       env: null                   # Delete env block from settings.json
   ```
   To delete only a nested sub-key, nest the null under the parent instead of nulling the whole block (the two forms are mutually exclusive alternatives for the same key):
   ```yaml
   user-settings:
       permissions:
           deny: null              # Delete only the deny sub-key (keep allow/ask)
   ```
2. **Manually delete the key** from `~/.claude/settings.json` using a text editor.

Automated YAML-removal-triggered cleanup (a state-tracking sidecar approach, for example `~/.claude/toolbox-managed-keys.json` recording which keys the toolbox wrote in the last run) is not implemented. The preservation behavior is the intended design.

**Exception: pinned-version update controls.** The contract covers the keys you manage through `user-settings`, not the update controls a version pin manages. When no installed profile pins a Claude Code version, the Step 16 sweep of an unpinned run removes `DISABLE_AUTOUPDATER`, `DISABLE_UPDATES`, and `CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL` from the `env` block of the running profile's `settings.json`, whoever set them, unless the current YAML sets them to a non-null value in `user-settings.env`; copies in other profiles are reported, never edited. See [Automatic Auto-Update Management](#automatic-auto-update-management) and [Automatic IDE Extension Version Management](#automatic-ide-extension-version-management).

**Security framing: preventing silent destruction of user state.** Deep-merge with universal array-union at every depth is the core mechanism that prevents silent destruction of security rules and user state in the shared `~/.claude/settings.json`. The contract applies uniformly to every list-valued key at any depth: `permissions.allow/deny/ask/additionalDirectories`, `companyAnnouncements`, `hooks.<EventName>` matcher-group lists, `sandbox.filesystem.*` path lists, `disabledMcpjsonServers`/`enabledMcpjsonServers`, `projects.<path>.allowedTools`, and every other list-valued key. A narrower YAML declaration such as `user-settings: {permissions: {allow: [Read]}}` MUST NOT remove `permissions.deny` entries, `permissions.additionalDirectories`, `companyAnnouncements` entries, or any other user-managed state contributed by other writers (manual user edits, the Claude Code CLI, or teammate YAMLs). Under the unified deep-merge + universal-array-union contract, list entries accumulate additively across runs and explicit null is the only way to shrink them:

- To remove ALL entries under a list-valued sub-key: nest-null the sub-key (`user-settings: {permissions: {deny: null}}` deletes just the `deny` sub-key) or top-level-null the parent (`user-settings: {permissions: null}` deletes the entire `permissions` block).
- To remove a specific element: edit `~/.claude/settings.json` manually, because array union only grows lists -- declaring `user-settings: {permissions: {deny: [X]}}` in YAML unions `[X]` with the existing deny list, not replaces it.

Any rule or entry preserved on disk is the combined contribution of all writers; losing rules silently on re-run would be a critical security regression, so the toolbox instead requires explicit null to delete them. This matches [Claude Code CLI's documented cross-scope merge semantics](https://code.claude.com/docs/en/settings) for shared settings files.

**Note on `hooks` deletion and composition:** Setting `hooks: null` at YAML root deletes the entire `hooks` key from `~/.claude/settings.json`. Setting `hooks: {EventName: null}` deletes only that event list while preserving other event names. Under the universal array-union contract, per-event matcher lists are unioned across runs via Python structural equality: disjoint event names compose additively, and for the same event name, matcher groups accumulate. Two matcher groups with the same `matcher` string but different inner handlers from different contributions coexist as separate entries (naive structural dedupe -- they are not structurally equal, so neither is discarded); structurally identical matcher groups collapse to one (idempotent re-run). This matches Claude Code's native cross-scope merge behavior; at runtime, [Claude Code deduplicates command hooks by command string and HTTP hooks by URL](https://code.claude.com/docs/en/hooks) ("Command hooks are deduplicated by command string, and HTTP hooks are deduplicated by URL"), so on-disk consolidation is unnecessary.

### Profile-Scoped MCP Servers in Non-Command-Names Mode (ERROR)

Profile-scoped MCP servers (`scope: profile` or `scope: [user, profile]`) CANNOT work without `command-names` because the launcher script that consumes `--mcp-config` is only created in isolated mode. In non-isolated mode, profile-scoped servers would have no launcher target and would be silently dropped at runtime -- a correctness risk.

This constraint is enforced at two levels: the `EnvironmentConfig` Pydantic model raises a `ValueError` during YAML validation (catching the issue at parse time), and the setup script enforces a hard validation error (exit 1) at the runtime validation phase as defense-in-depth, BEFORE any side effects (downloads, writes) occur:

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

### `command-defaults` Without Command Names

System prompts are applied by the launcher via `--system-prompt` or `--append-system-prompt` CLI flags, and only an isolated install creates a launcher. A run with no command names installs a configuration that declares `command-defaults` without `command-names` as the base profile, and downloads the prompt file to `~/.claude/prompts/`. The same file run with `--command-names NAME` (or `CLAUDE_CODE_TOOLBOX_COMMAND_NAMES=NAME`) installs the isolated profile `~/.claude/NAME`, whose launcher applies the prompt. When the run has no command names and `command-defaults` is not empty, the installation summary, shown before consent and by `--dry-run`, carries this line under Settings:

```text
* command-defaults applies only to isolated installs, whose launcher passes the system prompt to Claude Code; this run has no command names
```

and the closing summary reports the system prompt as not applied:

```text
* System prompt: not applied (command-defaults applies only to isolated installs, whose launcher passes the system prompt to Claude Code; this run has no command names)
```

Unlike profile-scoped MCP servers (a hard error, because silently dropped servers are a correctness risk), `command-defaults` without command names never fails a run: the prompt file is installed and the summaries say where it applies.

### Four-Writer Architectural Model Summary

| Writer                                 | YAML Source                              | Target                                                               | Key Universe                                     | Semantics                                                                   | Step              |
|----------------------------------------|------------------------------------------|----------------------------------------------------------------------|--------------------------------------------------|-----------------------------------------------------------------------------|-------------------|
| `write_user_settings()`                | `user-settings:`                         | `~/.claude/settings.json` (non-isolated only)                        | All non-excluded `settings.json` keys            | Deep merge + universal array union at every depth + RFC 7396 null-as-delete | 14                |
| `write_global_config()`                | `global-config:`                         | `~/.claude.json` (base) or `~/.claude/{cmd}/.claude.json` (isolated) | Free-form `~/.claude.json` keys                  | Deep merge + universal array union at every depth + RFC 7396 null-as-delete | 15                |
| `create_profile_config()`              | `user-settings:` + `status-line`/`hooks` | `~/.claude/{cmd}/config.json`                                        | `user-settings` content + 2 `PROFILE_OWNED_KEYS` | Atomic overwrite (fresh dict each run, nulls stripped, fully toolbox-owned) | 18 (isolated)     |
| `write_profile_settings_to_settings()` | `status-line`/`hooks` (YAML root)        | `~/.claude/settings.json`                                            | 2 `PROFILE_OWNED_KEYS` delta                     | Deep merge + universal array union at every depth + RFC 7396 null-as-delete | 18 (non-isolated) |

The two shared-file merge writers (`write_user_settings()` and `write_global_config()`) plus `write_profile_settings_to_settings()` delegate to the same `_write_merged_json()` helper, which gives them a single unified universal deep-merge contract: every list at every depth is unioned with structural dedupe, matching [Claude Code CLI's cross-scope merge semantics](https://code.claude.com/docs/en/settings) ("arrays are concatenated and deduplicated, not replaced"). Both Step 18 writers (`create_profile_config()` and `write_profile_settings_to_settings()`) are fed by the shared pure builder `_build_profile_settings()`, which accepts a `profile_config` dict for the `status-line`/`hooks` keys and delegates to `_build_hooks_json()` for hook events. In isolated mode, `create_profile_config()` atomically rewrites `~/.claude/{cmd}/config.json` from scratch on each run (fully toolbox-owned), merging the `user-settings` content with the built profile-owned entries and stripping null-valued members. In non-isolated mode, `user-settings` reaches `~/.claude/settings.json` through `write_user_settings()` at Step 14, and `write_profile_settings_to_settings()` deep-merges the `status-line`/`hooks` delta into the same file at Step 18, preserving contributions from other writers and accumulating list elements additively across runs.

**YAML inheritance layer is separate.** The per-path whitelist mechanism in `deep_merge_settings()` (`DEFAULT_ARRAY_UNION_KEYS` and explicit `set[str]` arguments) applies only to the YAML composition layer (`_merge_config_key()`): `array_union_keys=set()` for `global-config` inheritance (child replaces parent for arrays) and `array_union_keys=DEFAULT_ARRAY_UNION_KEYS` for `user-settings` inheritance (union only for `permissions.allow/deny/ask`, replace for other arrays). On-disk shared-file writers are decoupled from YAML composition by intent; they always union every array with the array the target file already holds.

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

# Share sessions and auto-memory with the default Claude
link-dirs:
  - projects

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

# OS-level persistent environment variables
os-env-variables:
  PYTHONDONTWRITEBYTECODE: "1"

# System prompt
command-defaults:
  system-prompt: "prompts/python-system-prompt.md"
  mode: "append"

# User settings -- raw settings.json content (camelCase keys)
user-settings:
  # Use Opus model with maximum effort
  model: "opus"
  effortLevel: "max"
  alwaysThinkingEnabled: true
  language: "english"
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
  env:
    PROJECT_TYPE: "python"
    COVERAGE_THRESHOLD: "80"
  # Company announcements
  companyAnnouncements:
    - "Welcome to the Python development environment!"
    - "Run /lint to check your code"
  # Attribution
  attribution:
    commit: "Co-authored-by: Claude AI"
    pr: ""  # Hide PR attribution

# Global config -- raw ~/.claude.json content (camelCase keys)
global-config:
  autoConnectIde: true
  showTurnDuration: true

# Hooks for code quality and safety
hooks:
  files:
    - "hooks/python-linter.py"
    - "configs/linter-config.yaml"
  helpers:
    - "hooks/hook_config_loader.py"
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

### Workflow Control and Behavior

| Variable                               | Purpose                                                                  | Accepted Values                        |
|----------------------------------------|--------------------------------------------------------------------------|----------------------------------------|
| `CLAUDE_CODE_TOOLBOX_CONFIRM_INSTALL`  | Auto-confirm installation (`--yes`)                                      | Exact value `1` only                   |
| `CLAUDE_CODE_TOOLBOX_DRY_RUN`          | Preview installation plan (`--dry-run`)                                  | Exact value `1` only                   |
| `CLAUDE_CODE_TOOLBOX_SKIP_INSTALL`     | Skip Claude Code installation (`--skip-install`)                         | Exact value `1` only                   |
| `CLAUDE_CODE_TOOLBOX_NO_ADMIN`         | Skip Windows admin elevation (`--no-admin`)                              | Exact value `1` only                   |
| `CLAUDE_CODE_TOOLBOX_ALLOW_ROOT`       | Allow running as root on Linux/macOS                                     | Exact value `1` only                   |
| `CLAUDE_CODE_TOOLBOX_DEBUG`            | Enable verbose debug logging                                             | `1`, `true`, or `yes`                  |
| `CLAUDE_CODE_TOOLBOX_PARALLEL_WORKERS` | Override concurrent download workers                                     | Integer (default: 2)                   |
| `CLAUDE_CODE_TOOLBOX_SEQUENTIAL_MODE`  | Disable parallel downloads                                               | `1`, `true`, or `yes`                  |
| `CLAUDE_CODE_TOOLBOX_GIT_BASH_PATH`    | Override Git Bash executable path (Windows)                              | Path to `bash.exe`                     |
| `CLAUDE_CODE_TOOLBOX_SELECT`           | Install these components plus bundled/required components (`--select`)   | Comma-separated names, or `all`/`none` |
| `CLAUDE_CODE_TOOLBOX_WITH`             | Add components to the defaults (`--with`)                                | Comma-separated names                  |
| `CLAUDE_CODE_TOOLBOX_WITHOUT`          | Remove components from the selection (`--without`)                       | Comma-separated names                  |
| `CLAUDE_CODE_TOOLBOX_COMMAND_NAMES`    | Command names of this run, replacing `command-names` (`--command-names`) | Comma-separated names, primary first   |
| `CLAUDE_CODE_TOOLBOX_LINK_DIRS`        | Profile entries linked from another profile (`--link-dirs`)              | Comma-separated entries, `all`, `none` |
| `CLAUDE_CODE_TOOLBOX_LINK_FROM`        | The profile the linked entries come from (`--link-from`)                 | `base` or a profile's primary name     |

### Authentication

| Variable                       | Scope                                 | Purpose                                  |
|--------------------------------|---------------------------------------|------------------------------------------|
| `GITHUB_TOKEN`                 | Python-level (auto-detected from URL) | GitHub PAT with `repo` scope             |
| `GITLAB_TOKEN`                 | Python-level (auto-detected from URL) | GitLab PAT with `read_repository` scope  |
| `REPO_TOKEN`                   | Python-level (auto-detected from URL) | Generic token, auto-detects repo type    |
| `CLAUDE_CODE_TOOLBOX_ENV_AUTH` | Python-level (explicit override)      | Custom header: `Header-Name:token-value` |

### CLI Flags and Environment Variable Equivalents

| Flag                              | Environment Variable                  | Purpose                                                                                       |
|-----------------------------------|---------------------------------------|-----------------------------------------------------------------------------------------------|
| `--yes` / `-y`                    | `CLAUDE_CODE_TOOLBOX_CONFIRM_INSTALL` | Auto-confirm installation (skip interactive prompt)                                           |
| `--dry-run`                       | `CLAUDE_CODE_TOOLBOX_DRY_RUN`         | Show installation plan and exit without installing or requesting admin elevation              |
| `--skip-install`                  | `CLAUDE_CODE_TOOLBOX_SKIP_INSTALL`    | Skip Claude Code installation                                                                 |
| `--no-admin`                      | `CLAUDE_CODE_TOOLBOX_NO_ADMIN`        | Do not request admin elevation on Windows                                                     |
| `--env KEY=VALUE`                 | --                                    | Set an environment variable for this run (repeatable; any documented variable)                |
| `--select`                        | `CLAUDE_CODE_TOOLBOX_SELECT`          | Install these components plus bundled/required components (sentinels: `all`, `none`)          |
| `--with`                          | `CLAUDE_CODE_TOOLBOX_WITH`            | Add components to the default selection                                                       |
| `--without`                       | `CLAUDE_CODE_TOOLBOX_WITHOUT`         | Remove components from the selection (hard `requires` still win)                              |
| `--list-components`               | --                                    | List the configuration's components and exit                                                  |
| `--command-names NAME[,ALIAS...]` | `CLAUDE_CODE_TOOLBOX_COMMAND_NAMES`   | Install as the isolated profile `~/.claude/NAME` under these names; `NAME,none`: no aliases   |
| `--profile NAME`                  | `CLAUDE_CODE_TOOLBOX_PROFILE`         | Re-run the installed profile `NAME` from its manifest with no configuration (`base`, `all`)   |
| `--switch-config`                 | `CLAUDE_CODE_TOOLBOX_SWITCH_CONFIG`   | Accept another configuration for an existing profile and remove what the previous one left    |
| `--link-dirs ENTRIES`             | `CLAUDE_CODE_TOOLBOX_LINK_DIRS`       | Link these entries of the isolated profile from another profile (`all`, `none`)               |
| `--link-from SOURCE`              | `CLAUDE_CODE_TOOLBOX_LINK_FROM`       | The profile the linked entries come from: `base`, or an installed profile's primary name      |

CLI flags take precedence over environment variables. For piped invocations, environment variables are the reliable channel: `iex (irm ...)` accepts no arguments, and `curl ... | bash` passes them only with `bash -s -- <config> <flags>`. In PowerShell, quote a comma-separated flag value (`--command-names 'main,alias'`), because PowerShell reads an unquoted `main,alias` as an array. The bootstrap wrappers hand your arguments to the setup script exactly as typed and never put `CLAUDE_CODE_TOOLBOX_ENV_CONFIG` on the command line, so the script knows whether a configuration was typed or set in the environment; they require a configuration (a first non-flag argument or the variable) unless `--profile` or `CLAUDE_CODE_TOOLBOX_PROFILE` is given, in which case they run the setup script without one.

## Troubleshooting

### No configuration specified

If you see an error about no configuration, ensure you set the `CLAUDE_CODE_TOOLBOX_ENV_CONFIG` variable inline with the bootstrap command, or re-run an installed profile with `--profile NAME` (or `CLAUDE_CODE_TOOLBOX_PROFILE`), which needs no configuration. See [Quick Start](#quick-start) and [Re-running a profile](#re-running-a-profile) for examples.

### Profile "NAME" was installed from another configuration

A profile keeps the configuration it was installed from. Giving it another configuration, positionally or through `CLAUDE_CODE_TOOLBOX_ENV_CONFIG`, is a switch: the setup lists what the previous configuration leaves behind and stops under `--yes`, `--dry-run` or without a terminal, or asks when a terminal is available. Pass `--switch-config` (or set `CLAUDE_CODE_TOOLBOX_SWITCH_CONFIG=1`) to accept the switch and remove the residue, or re-run the profile with its own configuration: `--profile NAME`. See [Guards before any write](#guards-before-any-write).

### CLAUDE_CODE_TOOLBOX_COMMAND_NAMES changes the command names of profile "NAME"

A variable left over from an earlier install would rename the profile. The setup stops under `--yes`, `--dry-run` or without a terminal, and asks when a terminal is available. Pass `--command-names` with the new list to change the names deliberately, or clear the variable to keep the recorded ones.

### Configuration not found in repository

If the named configuration is not found, verify the name matches a YAML file in the [claude-code-artifacts-public](https://github.com/alex-feel/claude-code-artifacts-public) repository. Browse the repository to see available configurations.

### merge-keys requires inherit

The `merge-keys` directive controls merge semantics during inheritance resolution. Without `inherit`, there is no parent configuration to merge from. Either add `inherit` or remove `merge-keys`. Note: an empty `merge-keys: []` without `inherit` is permitted.

### link-dirs needs an isolated profile

Links live inside an isolated profile's directory, so a configuration that declares `link-dirs`, or a run given `--link-dirs`, needs `command-names` or `--command-names NAME`. Add one, or remove `link-dirs`. The message names the value the way it was given; when it came from `CLAUDE_CODE_TOOLBOX_LINK_DIRS`, left in the shell by an earlier one-liner, the message also says how to clear the link variables (`unset`, or `Remove-Item Env:` in PowerShell) so `--profile base` runs without links.

### Profile "NAME" cannot link from itself

A profile is never its own link source. The usual cause is the one-liner's variables still set in the shell: after `CLAUDE_CODE_TOOLBOX_LINK_DIRS='all'` and `CLAUDE_CODE_TOOLBOX_LINK_FROM='team-1'` installed a dependent, `--profile team-1` in the same shell reads them for the source itself. The message names the variable and how to clear both (`unset CLAUDE_CODE_TOOLBOX_LINK_DIRS CLAUDE_CODE_TOOLBOX_LINK_FROM`, or `Remove-Item Env:CLAUDE_CODE_TOOLBOX_LINK_DIRS, Env:CLAUDE_CODE_TOOLBOX_LINK_FROM` in PowerShell); a fresh shell works too. When the configuration's own `link-from` names the profile being installed, pass `--link-dirs none` for that run: the configuration's link keys are meant for the profiles that link from it, and the typed `none` is remembered, so every later `--profile NAME` run of the source (and `--profile all`) needs no flag.

### Content entries link only between installs of one configuration

Every entry but `projects` shows the source's installed content, so the profile that links it must be installed from the configuration the source was installed from (the same resolved path or URL). To run several profiles of one configuration beside a base of another (an `team-corp` base with `team` profiles), install one full profile of that configuration first (`--command-names team-1`, no link keys) and link the others from it (`--command-names team-2 --link-dirs all --link-from team-1`); or run the setup with the source's configuration; or link only `projects`. A profile that already follows a source stops following it with `--link-dirs none`, or with `--link-from` naming a profile of the new configuration, before it switches configuration.

### Profile "NAME" is the link source of other profiles

A profile that other profiles link content from keeps its links and its configuration until each dependent is re-pointed (`--profile DEP --link-from <other profile>`) or unlinked (`--profile DEP --link-dirs none`); the message lists both commands for each dependent.

### Profile "NAME" no longer holds every link it was installed with

A dependency command, or something outside the setup, replaced a link with a real directory or re-pointed it. Re-run the profile with `--profile NAME`: the remembered value repairs a link that points elsewhere, and a real directory with content is moved aside only when `--link-dirs` is passed for the run.

### CLAUDE_CONFIG_DIR is set for a configuration without command-names

A configuration without `command-names` writes its artifacts to `~/.claude` and its global configuration to `~/.claude.json`, while the Claude CLI resolves `CLAUDE_CONFIG_DIR` ahead of the home directory, so `claude mcp add` and the global-config writes would land under the directory that variable names. The setup refuses the run with exit code 1 instead of splitting it across two directories, and reports the same block under `--dry-run`. Clear the variable (`unset CLAUDE_CONFIG_DIR` in bash, `Remove-Item Env:CLAUDE_CONFIG_DIR` in PowerShell) and run the setup again, run it from a terminal that is not inside an isolated profile session, or -- when a configuration persists the variable through `os-env-variables` or `user-settings.env` -- remove it there and open a new terminal. A configuration with `command-names` is not refused: it reports that it replaces the inherited value with its own profile directory. See [Running Setup From Inside An Isolated Profile Session](#running-setup-from-inside-an-isolated-profile-session).

### user-settings.effortLevel 'xhigh'/'max' requires a matching model

The `xhigh` and `max` effort levels require `user-settings.model` to be set to a supporting variant: `xhigh` requires an Opus or Fable model (the model name must contain `opus` or `fable`, case-insensitive) or the exact alias `best`; `max` additionally accepts a Sonnet model. The validation errors read `user-settings.effortLevel '{level}' requires user-settings.model to be specified. This effort level is only available for {families}.` (when `model` is missing) and `user-settings.effortLevel '{level}' is only available for {families}, but model is set to '{model}'. Use 'low', 'medium', or 'high' for other models.` (when the model is outside the required families), where `{families}` is "Opus and Fable models" for `xhigh` and "Opus, Sonnet, and Fable models" for `max`:

```yaml
user-settings:
  model: "claude-fable-5"   # or "opus", "fable", "best"; "sonnet" also works for max
  effortLevel: "max"        # or "xhigh"
```

### Component selector matches no item

Every `includes` selector must resolve to an item that exists in the same configuration, using the section's identity from the [Selector Identities](#selector-identities) table. The most common causes are a renamed item whose selector was not updated, a `files-to-download` selector that does not match the entry's `dest`, and a `hooks` selector naming an event without an `id`. The error message names the component, the section, and the unmatched selector.

### --without ignored for a required component

Hard `requires` edges win over `--without`: when a selected component requires the one you excluded, the setup re-adds it, prints a warning naming the requester, and marks it `[auto: required by '...']` in the summary. To drop it, also drop every selected component that requires it.

### Component picker does not appear

The interactive picker runs only when the configuration defines `components`, no selector flag or its environment variable was given (`--select`/`--with`/`--without`, `CLAUDE_CODE_TOOLBOX_SELECT`/`_WITH`/`_WITHOUT`), neither `--yes` nor `--dry-run` is set, and an interactive terminal (or `/dev/tty`) is available. Piped invocations without a terminal silently use the author defaults; use `--select` to choose components in that mode.

### Numbered picker instead of the checkbox

When the `questionary` library is not installed (for example, when running the standalone script without `uv`) or the console cannot render the interactive checkbox (for example, older mintty terminals on Windows), the setup falls back to a numbered toggle prompt with the same semantics. Enter a number to toggle a component, `a` to select all, `n` to select none, and press Enter to confirm. Ctrl-C cancels the setup without installing anything, exactly as in the checkbox picker.

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

### hooks.events command is declared in hooks.helpers

A `command`, `config`, or `status-line` reference names an entry from `hooks.helpers`. Helpers are imported by hook scripts, not launched by Claude Code; move the entry to `hooks.files` if it really is a hook script or a config file.

### hooks.helpers duplicates hooks.files entries

Both lists install into the same hooks directory, so a filename can appear in only one of them. Keep the entry in `hooks.files` when something references it, and in `hooks.helpers` when the hook scripts import it.

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

**CLI flag (direct invocation or CLI; piped on Linux/macOS via `bash -s -- <config> <flag>`):**

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
curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash -s -- <config> --yes
```

### Dry-run mode

To preview the installation plan without making any changes:

**Environment variable (all platforms, works in piped mode):**

```bash
export CLAUDE_CODE_TOOLBOX_DRY_RUN=1
```

**CLI flag (direct invocation or CLI; piped on Linux/macOS via `bash -s -- <config> <flag>`):**

```bash
./setup-environment.sh python --dry-run
```

**Windows PowerShell (piped via iex):**

```powershell
$env:CLAUDE_CODE_TOOLBOX_DRY_RUN='1'; $env:CLAUDE_CODE_TOOLBOX_ENV_CONFIG='python'; iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')
```

On Windows, a dry run never requests administrator elevation, so no UAC prompt opens. When the real run would request it, the dry run prints `Dry run: administrator elevation is not requested.` with the same reasons the elevation banner lists (installing Claude Code, `winget ... --scope machine` dependencies, global `npm` dependencies), then shows the installation plan and exits 0.

### Skip Claude Code installation

To skip the Claude Code installation step (useful when Claude Code is already installed):

**Environment variable (all platforms, works in piped mode):**

```bash
export CLAUDE_CODE_TOOLBOX_SKIP_INSTALL=1
```

**CLI flag (direct invocation or CLI; piped on Linux/macOS via `bash -s -- <config> <flag>`):**

```bash
./setup-environment.sh python --skip-install
```

### Skip admin elevation (Windows)

From a terminal without administrator rights, a real run on Windows requests elevation through a UAC prompt when it installs Claude Code (unless `--skip-install` is set) or runs a `winget ... --scope machine` or `npm install -g` dependency. It prints the reasons, then continues in a new elevated window; a run there that completes or fails, a validation error included, ends with a success or errors banner and waits for Enter so its output stays on screen, while a declined confirmation closes the window at once; if elevation is denied, the run exits 1. A dry run never requests elevation (see [Dry-run mode](#dry-run-mode)).

With `--no-admin`, no step of the run requests elevation: the setup installs Claude Code and runs the `winget ... --scope machine` and `npm install -g` dependencies without administrator rights. An operation that needs those rights fails and the run exits 1: a failed Claude Code installation stops the setup, and a failed dependency appears in the error summary at the end of the run.

To prevent the setup from requesting Windows admin elevation:

**Environment variable (all platforms, works in piped mode):**

```bash
export CLAUDE_CODE_TOOLBOX_NO_ADMIN=1
```

**CLI flag (direct invocation or CLI; piped on Linux/macOS via `bash -s -- <config> <flag>`):**

```bash
./setup-environment.sh python --no-admin
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

By default, the setup requires explicit confirmation before installing. Use `--dry-run` to preview the installation plan without making changes or requesting administrator elevation. Unknown configuration keys are flagged with `[?]` in the installation summary to help you identify potential typos or unsupported keys.
