<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/.github/images/banner-dark.svg">
    <img alt="Claude Code Toolbox" src="https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/.github/images/banner.svg" width="600">
  </picture>
</h1>

[![GitHub License](https://img.shields.io/github/license/alex-feel/claude-code-toolbox)](https://github.com/alex-feel/claude-code-toolbox/blob/main/LICENSE) [![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/alex-feel/claude-code-toolbox)

Automated installers and an environment configuration framework for Claude Code on Windows, macOS, and Linux.

Define your complete Claude Code environment in a single YAML file -- custom agents, MCP servers, slash commands, hooks, skills, settings, and more -- and install everything with one command.

## Features

- **Custom agents** -- specialized subagents for code review, research, debugging, and any workflow you design
- **MCP servers** -- HTTP, SSE, and stdio transports with scope-based registration; unchanged servers are skipped on reruns, preserving their OAuth authentication
- **Slash commands** -- custom commands for frequently used workflows
- **Rules** -- user-scope rule files for coding standards, security policies, and project conventions
- **Skills** -- multi-file skill packages for complex agent capabilities
- **System prompts** -- replace or append to the default Claude Code prompt in the commands an isolated profile installs
- **Hooks** -- five hook types: command (shell scripts, shell or exec form), HTTP (webhooks), prompt (LLM evaluation), agent (subagent with tools), and MCP tool (a tool on a configured MCP server), plus shared helper modules delivered beside the hook scripts
- **User and global settings** -- `user-settings` is raw `settings.json` content (camelCase keys) and `global-config` is raw `~/.claude.json` content, covering model selection, permissions, effort levels, thinking mode, environment variables, and every other Claude Code setting
- **Status line** -- custom status bar scripts for real-time session information
- **Configuration inheritance** -- extend and override parent configurations with selective per-key merge
- **Component selection** -- author-defined component groups the end user picks at setup time, interactively (checkbox picker) or via `--select`/`--with`/`--without`; unclaimed items stay mandatory
- **Isolated profiles** -- `command-names` installs a configuration as a separate profile under `~/.claude/{cmd}/` with its own commands, settings, `.claude.json`, MCP registrations, and environment loaders; an isolated install leaves the base profile's `settings.json` and `.claude.json` alone, apart from the `installMethod` record the Claude Code installer keeps in `~/.claude.json`, and names every write outside the profile before you confirm: the binary and its `installMethod` record, a version pin and its IDE extension, the update controls, the command wrappers, project-scope MCP servers, `files-to-download` destinations outside the profile, and the dependency commands
- **One configuration, many profiles** -- `--command-names NAME[,ALIAS...]` installs any configuration under the names you give, placing its agents, commands, rules, skills, hooks, and launchers in the isolated profile `~/.claude/NAME`, so one YAML file serves as many profiles as you need; `NAME,none` installs it under one command, `files-to-download` destinations and dependency commands run as written, and a name another profile or program already holds is refused before anything is written
- **Re-runs that remember** -- an update is the install command run again: `--profile NAME` re-runs an installed profile from its manifest with no configuration argument (`base` for the base profile, `all` for every installed profile, each in its own run), the configuration plus the primary name does the same, and both keep the aliases and the component choice the install typed while re-reading everything the configuration declares; a leftover environment variable or a different configuration for an existing profile is held back until you consent, and `--switch-config` accepts the switch and removes what the previous configuration left behind
- **Linked profiles** -- `--link-dirs` and `--link-from` (or the `link-dirs` and `link-from` keys) take entries of an isolated profile's directory -- `skills`, `agents`, `commands`, `rules`, `hooks`, `output-styles`, `prompts`, `projects` -- through a directory link from another profile: link `projects` to share sessions and auto-memory with the base profile or any other, or link `all` to run a second command on the content of a profile installed from the same configuration, which then follows every re-run of its source
- **Dependency management** -- platform-specific package installation (apt, brew, choco, and more)
- **File downloads** -- arbitrary files downloaded to specified destinations during setup
- **Private repository support** -- GitHub and GitLab authentication with token-based access
- **Cross-platform** -- consistent behavior across Windows, macOS, and Linux
- **One-command setup** -- everything from a single YAML configuration file
- **PyPI distribution** -- the same setup and installer, runnable as `uvx cc-toolbox` on any machine with uv

## Quick Start

### Example Configuration

```yaml
name: "My Development Environment"

command-names:
  - "my-env"

# Base URL for downloading agents, commands, hooks, and other files
base-url: "https://raw.githubusercontent.com/my-org/my-configs/main"

agents:
  - "agents/code-reviewer.md"

slash-commands:
  - "commands/review.md"

rules:
  - "rules/coding-standards.md"

mcp-servers:
  - name: "context-server"
    transport: "http"
    url: "http://localhost:8000/mcp"
    # ${VAR} in a header is stored as-is and expanded by Claude Code at runtime,
    # so the token stays in your environment, never in the config file.
    header: "Authorization: Bearer ${CONTEXT_SERVER_TOKEN}"

# user-settings holds raw settings.json content with camelCase keys
user-settings:
  model: "sonnet"
  effortLevel: "high"

command-defaults:
  system-prompt: "prompts/system-prompt.md"
  mode: "append"

hooks:
  files:
    - "hooks/linter.py"
  # Shared modules the hook scripts import from their own directory
  helpers:
    - "hooks/hook_config_loader.py"
  events:
    - event: "PostToolUse"
      matcher: "Edit|MultiEdit|Write"
      type: "command"
      command: "linter.py"
```

This creates a global `my-env` command that launches Claude Code with your custom agents, MCP servers, and hooks. See the [Environment Configuration Guide](https://github.com/alex-feel/claude-code-toolbox/blob/main/docs/environment-configuration-guide.md) for all configuration keys.

### Install Your Environment

Host your YAML configuration in a repository, then run a single command to set everything up:

**Linux:**

```bash
export CLAUDE_CODE_TOOLBOX_ENV_CONFIG='https://raw.githubusercontent.com/your-org/your-repo/main/config.yaml' && curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash
```

**macOS:**

```bash
export CLAUDE_CODE_TOOLBOX_ENV_CONFIG='https://raw.githubusercontent.com/your-org/your-repo/main/config.yaml' && curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/setup-environment.sh | bash
```

**Windows:**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "`$env:CLAUDE_CODE_TOOLBOX_ENV_CONFIG='https://raw.githubusercontent.com/your-org/your-repo/main/config.yaml'; iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')"
```

**Any platform, via PyPI** (requires [uv](https://docs.astral.sh/uv/)):

```bash
uvx cc-toolbox setup 'https://raw.githubusercontent.com/your-org/your-repo/main/config.yaml'

# Private repositories: pass tokens inline with --env, or export them as regular environment variables
uvx cc-toolbox setup 'https://raw.githubusercontent.com/your-org/your-repo/main/config.yaml' --env GITHUB_TOKEN=ghp_your-token --env GITLAB_TOKEN=glpat-your-token

# The same configuration as a second isolated profile with its own command
uvx cc-toolbox setup 'https://raw.githubusercontent.com/your-org/your-repo/main/config.yaml' --command-names my-env-2

# Update that profile later: its manifest remembers the configuration, the aliases and the components
uvx cc-toolbox setup --profile my-env-2

# Update every installed profile, the base first
uvx cc-toolbox setup --profile all

# A profile that shares the sessions and auto-memory of the base profile
uvx cc-toolbox setup 'https://raw.githubusercontent.com/your-org/your-repo/main/config.yaml' --command-names my-env-3 --link-dirs projects

# A second command on the content of my-env-2, refreshed whenever my-env-2 is
uvx cc-toolbox setup 'https://raw.githubusercontent.com/your-org/your-repo/main/config.yaml' --command-names my-env-4 --link-dirs all --link-from my-env-2
```

For a persistent `cc-toolbox` command, install it once with `uv tool install cc-toolbox` (or `pipx install cc-toolbox`).

You can also use a local file (`./my-config.yaml`) or a configuration from a private repository. See the [Environment Configuration Guide](https://github.com/alex-feel/claude-code-toolbox/blob/main/docs/environment-configuration-guide.md) for all options including authentication.

### Ready-Made Configurations

Browse the [claude-code-artifacts-public](https://github.com/alex-feel/claude-code-artifacts-public) repository for ready-made environment configurations. Find a configuration you like, copy its raw URL, and use it as the `CLAUDE_CODE_TOOLBOX_ENV_CONFIG` value in the commands above.

See [Ready-Made Configurations](https://github.com/alex-feel/claude-code-toolbox/blob/main/docs/environment-configuration-guide.md#ready-made-configurations) for installation examples.

## Installing Claude Code

If you just need the Claude Code CLI without a custom environment configuration, the toolbox includes standalone installers that use the official Anthropic native installer with automatic npm fallback. With uv present, `uvx cc-toolbox install` runs the same installer from PyPI.

See the [Installing Claude Code](https://github.com/alex-feel/claude-code-toolbox/blob/main/docs/installing-claude-code.md) guide for platform-specific commands and options.

## Documentation

- [Environment Configuration Guide](https://github.com/alex-feel/claude-code-toolbox/blob/main/docs/environment-configuration-guide.md) -- complete reference for YAML configuration files with all keys, authentication, inheritance, and more
- [Installing Claude Code](https://github.com/alex-feel/claude-code-toolbox/blob/main/docs/installing-claude-code.md) -- standalone Claude Code installation, methods, and troubleshooting

## Security

Environment configurations can execute commands on your system, download files, and configure MCP servers. Only use configurations from sources you trust.

Local files are under your control. Remote URLs should be verified before use. The setup script displays a confirmation prompt and flags sensitive paths before proceeding.

See the [Security Considerations](https://github.com/alex-feel/claude-code-toolbox/blob/main/docs/environment-configuration-guide.md#security-considerations) section for details.

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](https://github.com/alex-feel/claude-code-toolbox/blob/main/CONTRIBUTING.md) for guidelines.

## License

MIT License -- see [LICENSE](https://github.com/alex-feel/claude-code-toolbox/blob/main/LICENSE) for details.

## Disclaimer

This is a community project and is not officially affiliated with Anthropic. Claude Code is a product of Anthropic, PBC.

## Getting Help

- **Bug reports**: [Report a bug](https://github.com/alex-feel/claude-code-toolbox/issues/new?template=bug-report.yml)
- **Feature requests**: [Suggest a feature](https://github.com/alex-feel/claude-code-toolbox/issues/new?template=feature-request.yml)
- **Documentation issues**: [Report a docs issue](https://github.com/alex-feel/claude-code-toolbox/issues/new?template=docs-issue.yml)
- **Questions**: [Ask a question](https://github.com/alex-feel/claude-code-toolbox/issues/new?template=question.yml)
