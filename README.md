# Claude Code Toolbox

A community toolbox for Claude Code - automated installers and environment configuration framework for Windows, macOS, and Linux.

## 📋 Quick Overview

**Two installation options:**
- **Environment Configurations** - Complete custom environments with agents, MCP servers, slash commands, and tools. Perfect for teams or any specialized workflow (development, research, finance, etc.).
- **Claude Code Only** - Just the Claude Code CLI without additional configuration. Choose this for a minimal installation.

> 💡 **Not sure which to choose?** If you want a custom environment with specialized tools and agents, choose Environment Configurations. For just the CLI, skip to [Claude Code Only Installation](#-only-claude-code-installation).

## 🎯 Example Use Cases

This framework can configure environments for any purpose. Here are some examples of what you could build:

- **Python Development**: Create a configuration with Python tools, linters, formatters, testing frameworks, and specialized Python agents
- **Web Development**: Set up Node.js, npm, frontend tooling, and web development agents
- **Research Environment**: Configure data analysis tools, Jupyter integration, and research-focused MCP servers
- **Finance Workflows**: Add financial APIs, market data servers, and analysis agents
- **Team Standardization**: Share your team's custom configuration via private repository to ensure consistent environments
- **Custom Workflows**: Build any specialized environment with the exact MCP servers, agents, and tools you need

## 🚀 Environment Configurations Installation

Set up your custom environment with specialized configurations:

### Windows

#### Option 1: One-liner (recommended)

> **Note:** Replace `https://raw.githubusercontent.com/org/repo/main/config.yaml` with your actual configuration URL. The command sets your configuration source and runs the installer in one line.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "`$env:CLAUDE_ENV_CONFIG='https://raw.githubusercontent.com/org/repo/main/config.yaml'; iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')"
```

#### Option 2: Using local configuration (for sensitive configs)
```powershell
# Use a local file containing API keys or other sensitive data
$env:CLAUDE_ENV_CONFIG='./my-custom-env.yaml'
iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')
```

#### Option 3: Using private repository configurations

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
# Public repository config
export CLAUDE_ENV_CONFIG='https://raw.githubusercontent.com/org/repo/main/config.yaml'
curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/setup-environment.sh | bash

# Local config file
export CLAUDE_ENV_CONFIG=./my-env.yaml
curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/setup-environment.sh | bash

# Private GitLab repository
export CLAUDE_ENV_CONFIG='https://gitlab.company.com/namespace/project/-/raw/main/config.yaml'
export GITLAB_TOKEN='glpat-<your-token>'
curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/setup-environment.sh | bash

# Private GitHub repository
export CLAUDE_ENV_CONFIG='https://raw.githubusercontent.com/org/repo/main/config.yaml'
export GITHUB_TOKEN='ghp_<your-token>'
curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/setup-environment.sh | bash
```

### Linux
```bash
# Public repository config
export CLAUDE_ENV_CONFIG='https://raw.githubusercontent.com/org/repo/main/config.yaml'
curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash

# Local config file
export CLAUDE_ENV_CONFIG=./my-env.yaml
curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash

# Private GitLab repository
export CLAUDE_ENV_CONFIG='https://gitlab.company.com/namespace/project/-/raw/main/config.yaml'
export GITLAB_TOKEN='glpat-<your-token>'
curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash

# Private GitHub repository
export CLAUDE_ENV_CONFIG='https://raw.githubusercontent.com/org/repo/main/config.yaml'
export GITHUB_TOKEN='ghp_<your-token>'
curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash
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

## ⏬ Only Claude Code Installation

### Windows (PowerShell)

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

Run this command in PowerShell (as regular user, it will elevate if needed):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/install-claude-windows.ps1')"
```

### macOS

```bash
curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/install-claude-macos.sh | bash
```

### Linux

```bash
curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/install-claude-linux.sh | bash
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
