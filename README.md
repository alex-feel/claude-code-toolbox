# Claude Code Toolbox

A community toolbox for Claude Code - automated installers, scripts, agent templates, and utilities for Windows, macOS, and Linux.

<!-- Dynamic entity count badges -->
<p align="left">
  <img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Falex-feel%2Fclaude-code-toolbox%2Fmain%2F.github%2Fbadges%2Fenvironments.json&query=%24.message&label=Environments&color=blue&style=for-the-badge" alt="Environments" />
  <img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Falex-feel%2Fclaude-code-toolbox%2Fmain%2F.github%2Fbadges%2Fagents.json&query=%24.message&label=Agents&color=green&style=for-the-badge" alt="Agents" />
  <img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Falex-feel%2Fclaude-code-toolbox%2Fmain%2F.github%2Fbadges%2Fcommands.json&query=%24.message&label=Commands&color=yellow&style=for-the-badge" alt="Commands" />
  <img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Falex-feel%2Fclaude-code-toolbox%2Fmain%2F.github%2Fbadges%2Fprompts.json&query=%24.message&label=Prompts&color=orange&style=for-the-badge" alt="Prompts" />
  <img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Falex-feel%2Fclaude-code-toolbox%2Fmain%2F.github%2Fbadges%2Fstyles.json&query=%24.message&label=Styles&color=purple&style=for-the-badge" alt="Styles" />
  <img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Falex-feel%2Fclaude-code-toolbox%2Fmain%2F.github%2Fbadges%2Fhooks.json&query=%24.message&label=Hooks&color=red&style=for-the-badge" alt="Hooks" />
</p>

## 🚀 Quick Install

## 🚀 Quick Start with Environment Configurations

Set up a complete development environment with specialized configurations:

### Windows

#### Option 1: One-liner (recommended)
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "`$env:CLAUDE_ENV_CONFIG='<environment-name>'; iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')"
```

#### Option 2: Using CMD
```cmd
curl -L -o %TEMP%\setup-env.ps1 https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1 && powershell -NoProfile -ExecutionPolicy Bypass -File %TEMP%\setup-env.ps1 <environment-name>
```

#### Option 3: Using local configuration (for sensitive configs)
```powershell
# Use a local file containing API keys or other sensitive data
$env:CLAUDE_ENV_CONFIG='./my-custom-env.yaml'
iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')
```

#### Option 4: Using private repository configurations

**For Private GitLab Repositories (One-liner recommended):**
```powershell
# One-liner (recommended) - works from any shell, Run dialog, or shortcuts
powershell -NoProfile -NoExit -ExecutionPolicy Bypass -Command "`$env:CLAUDE_ENV_CONFIG='https://gitlab.company.com/namespace/project/-/raw/main/config.yaml'; `$env:GITLAB_TOKEN='glpat-<your-token>'; iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')"

# Alternative: Two-step approach (if already in PowerShell)
$env:CLAUDE_ENV_CONFIG='https://gitlab.company.com/namespace/project/-/raw/main/path/to/config.yaml'
$env:GITLAB_TOKEN='glpat-<your-token>'
iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')
```

**For Private GitHub Repositories (One-liner recommended):**
```powershell
# One-liner (recommended) - works from any shell, Run dialog, or shortcuts
powershell -NoProfile -NoExit -ExecutionPolicy Bypass -Command "`$env:CLAUDE_ENV_CONFIG='https://raw.githubusercontent.com/org/repo/main/config.yaml'; `$env:GITHUB_TOKEN='ghp_<your-token>'; iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')"

# Alternative: Two-step approach (if already in PowerShell)
$env:CLAUDE_ENV_CONFIG='https://raw.githubusercontent.com/org/repo/main/config.yaml'
$env:GITHUB_TOKEN='ghp_<your-token>'
iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')
```

**💡 Pro Tips:**
- Use `-NoExit` flag to keep the window open and see any errors
- GitLab web URLs (`/-/raw/`) are automatically converted to API format
- Query parameters (like `?ref_type=heads`) are handled automatically
- The script only uses authentication when needed (public repos work without tokens)

### macOS
```bash
# Repository config
CLAUDE_ENV_CONFIG=<environment-name> curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/setup-environment.sh | bash

# Local config file
CLAUDE_ENV_CONFIG=./my-env.yaml curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/setup-environment.sh | bash

# Private GitLab repository (one-liner)
CLAUDE_ENV_CONFIG='https://gitlab.company.com/namespace/project/-/raw/main/config.yaml' GITLAB_TOKEN='glpat-<your-token>' curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/setup-environment.sh | bash

# Private GitHub repository (one-liner)
CLAUDE_ENV_CONFIG='https://raw.githubusercontent.com/org/repo/main/config.yaml' GITHUB_TOKEN='ghp_<your-token>' curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/setup-environment.sh | bash
```

### Linux
```bash
# Repository config
CLAUDE_ENV_CONFIG=<environment-name> curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash

# Local config file
CLAUDE_ENV_CONFIG=./my-env.yaml curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash

# Private GitLab repository (one-liner)
CLAUDE_ENV_CONFIG='https://gitlab.company.com/namespace/project/-/raw/main/config.yaml' GITLAB_TOKEN='glpat-<your-token>' curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash

# Private GitHub repository (one-liner)
CLAUDE_ENV_CONFIG='https://raw.githubusercontent.com/org/repo/main/config.yaml' GITHUB_TOKEN='ghp_<your-token>' curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash
```

**✅ After setup, use the simple command:**
```bash
<command-name>  # Works in all Windows shells (PowerShell, CMD, Git Bash)
```

The setup automatically creates properly escaped wrappers for each Windows shell, ensuring your environment configuration loads correctly regardless of which shell you use.

---

### ⚠️ Security Warning: Environment Configurations

**IMPORTANT:** Environment configurations can contain:
- 🔑 **API Keys** for MCP servers
- 📝 **System commands** that will be executed during setup
- 🪝 **Hook scripts** that run automatically on Claude Code events
- 🌐 **Remote dependencies** that will be downloaded and installed

**Only use environment configurations from trusted sources!**

When loading configurations:
- ✅ **Repository configs** - Reviewed and maintained by the community
- ✅ **Your local files** (`./my-config.yaml`) - Under your control
- ⚠️ **Remote URLs** (`https://example.com/config.yaml`) - **VERIFY THE SOURCE FIRST!**

The setup script will warn you when loading from remote URLs. Always review the configuration content before proceeding.

### 🔐 Using Private Repository Configurations

For configurations stored in private repositories, you need to provide authentication.

#### Quick Start: One-liner Commands

**GitLab Private Repository (Windows):**
```powershell
powershell -NoProfile -NoExit -ExecutionPolicy Bypass -Command "`$env:CLAUDE_ENV_CONFIG='https://gitlab.company.com/team/configs/-/raw/main/env.yaml'; `$env:GITLAB_TOKEN='glpat-<your-token>'; iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')"
```

**GitHub Private Repository (Windows):**
```powershell
powershell -NoProfile -NoExit -ExecutionPolicy Bypass -Command "`$env:CLAUDE_ENV_CONFIG='https://raw.githubusercontent.com/org/configs/main/env.yaml'; `$env:GITHUB_TOKEN='ghp_<your-token>'; iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')"
```

**GitLab Private Repository (macOS/Linux):**
```bash
CLAUDE_ENV_CONFIG='https://gitlab.company.com/team/configs/-/raw/main/env.yaml' GITLAB_TOKEN='glpat-<your-token>' curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash
```

**GitHub Private Repository (macOS/Linux):**
```bash
CLAUDE_ENV_CONFIG='https://raw.githubusercontent.com/org/configs/main/env.yaml' GITHUB_TOKEN='ghp_<your-token>' curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash
```

#### Authentication Details

**GitLab Authentication:**
- Create a personal access token with `read_repository` scope
- Use `GITLAB_TOKEN` environment variable
- GitLab web URLs (`/-/raw/`) are automatically converted to API format
- Query parameters (like `?ref_type=heads`) are handled automatically

**GitHub Authentication:**
- Create a personal access token with `repo` scope
- Use `GITHUB_TOKEN` environment variable
- Use raw.githubusercontent.com URLs

**Additional Options:**
- `REPO_TOKEN` - Generic token that auto-detects repository type
- `CLAUDE_ENV_AUTH` - Custom header format: `Header-Name:token-value`

#### Pro Tips

- **Windows**: Always use `-NoExit` flag to see any errors
- **All platforms**: The script tries public access first, only using tokens when needed
- **GitLab**: Both web (`/-/raw/`) and API URLs work - web URLs are auto-converted
- **Tokens**: Never commit tokens to repositories - use environment variables instead

---

### Standard Installation

#### Windows (PowerShell)

Run this command in PowerShell (as regular user, it will elevate if needed):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/install-claude-windows.ps1')"
```

Or using CMD:

```cmd
curl -L -o %TEMP%\install-claude-windows.ps1 https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/install-claude-windows.ps1 && powershell -NoProfile -ExecutionPolicy Bypass -File %TEMP%\install-claude-windows.ps1
```

### What it does

The Windows installer automatically:
- ✅ Installs Git for Windows (Git Bash) if not present
- ✅ Installs Node.js LTS (v18+) if not present or outdated
- ✅ Handles dependencies (Microsoft.UI.Xaml) for winget if needed
- ✅ Falls back to direct downloads if winget is unavailable
- ✅ Configures `CLAUDE_CODE_GIT_BASH_PATH` if bash.exe is not on PATH
- ✅ Installs Claude Code CLI using the official installer

**Reliability Features:**
- Smart dependency resolution for winget/App Installer
- Automatic fallback to direct downloads
- Cached availability checks to prevent redundant attempts
- Comprehensive PATH refresh for immediate command availability

#### macOS

```bash
curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/install-claude-macos.sh | bash
```

#### Linux

```bash
curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/install-claude-linux.sh | bash
```

**Note**: macOS and Linux installers are in beta.

## 📋 Requirements

### Windows
- Windows 10/11 with PowerShell 5.1+
- Internet connection
- Admin rights (auto-elevation for system-wide installs)

## 🔒 Security

### Verify Script Integrity

Pin to a specific commit for supply chain security:

```powershell
$commit = "abc123..." # Replace with actual commit hash
$url = "https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/$commit/scripts/windows/install-claude-windows.ps1"
iex (irm $url)
```

### Windows SmartScreen

If you download the script manually, Windows SmartScreen may warn you. The script is open source - review it at [scripts/windows/install-claude-windows.ps1](scripts/windows/install-claude-windows.ps1).

## 📚 Documentation

- [Sub-agents Guide](agents/README.md) - Creating specialized AI assistants
- [System Prompts Guide](system-prompts/README.md) - Comprehensive role-based configurations
- [Output Styles Guide](output-styles/README.md) - Transform Claude Code for different professional domains
- [Slash Commands Guide](slash-commands/README.md) - Custom command shortcuts
- [MCP Configuration Guide](mcp/README.md) - Model Context Protocol setup
- [Scripts Documentation](scripts/README.md) - Installation and setup scripts

## 🛠️ Repository Structure

```text
claude-code-toolbox/
├── scripts/                     # Installation and utility scripts
│   ├── install_claude.py        # Cross-platform Claude installer
│   ├── setup_environment.py     # Cross-platform environment setup
│   ├── windows/                 # Windows bootstrap scripts
│   │   ├── install-claude-windows.ps1
│   │   └── setup-environment.ps1
│   ├── linux/                   # Linux bootstrap scripts
│   │   ├── install-claude-linux.sh
│   │   └── setup-environment.sh
│   └── macos/                   # macOS bootstrap scripts
│       ├── install-claude-macos.sh
│       └── setup-environment.sh
├── agents/                      # Agents (subagents)
│   ├── library/                 # Ready-to-use subagents
│   └── templates/               # Templates for creating new agents
├── system-prompts/              # Comprehensive system prompts
│   ├── library/                 # Role-specific configurations
│   └── templates/               # Templates for custom prompts
├── output-styles/               # Output style transformations
│   ├── library/                 # Ready-to-use professional styles
│   └── templates/               # Templates for creating new styles
├── slash-commands/              # Custom slash command templates
│   ├── library/                 # Ready-to-use commands
│   └── templates/               # Command templates
├── hooks/                       # Git hooks and event handlers
│   └── library/                 # Ready-to-use hooks
├── environments/                # Environment configurations
│   ├── library/                 # Ready-to-use environments
│   └── templates/               # Environment templates
├── mcp/                         # Model Context Protocol configuration
│   └── README.md                # MCP setup and usage guide
└── docs/                        # Documentation
```

## 🤝 Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

## ⚠️ Disclaimer

This is a community project and is not officially affiliated with Anthropic. Claude Code is a product of Anthropic, PBC.

## 🆘 Getting Help

- **Bug reports**: [Open an issue](https://github.com/alex-feel/claude-code-toolbox/issues)
- **Claude Code documentation**: [Official docs](https://docs.anthropic.com/claude-code)
