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
export CLAUDE_ENV_CONFIG='https://raw.githubusercontent.com/org/repo/main/config.yaml' && curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/setup-environment.sh | bash

# Local config file
export CLAUDE_ENV_CONFIG=./my-env.yaml && curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/setup-environment.sh | bash

# Private GitLab repository
export CLAUDE_ENV_CONFIG='https://gitlab.company.com/namespace/project/-/raw/main/config.yaml' && export GITLAB_TOKEN='glpat-<your-token>' && curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/setup-environment.sh | bash

# Private GitHub repository
export CLAUDE_ENV_CONFIG='https://raw.githubusercontent.com/org/repo/main/config.yaml' && export GITHUB_TOKEN='ghp_<your-token>' && curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/setup-environment.sh | bash
```

### Linux
```bash
# Public repository config
export CLAUDE_ENV_CONFIG='https://raw.githubusercontent.com/org/repo/main/config.yaml' && curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash

# Local config file
export CLAUDE_ENV_CONFIG=./my-env.yaml && curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash

# Private GitLab repository
export CLAUDE_ENV_CONFIG='https://gitlab.company.com/namespace/project/-/raw/main/config.yaml' && export GITLAB_TOKEN='glpat-<your-token>' && curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash

# Private GitHub repository
export CLAUDE_ENV_CONFIG='https://raw.githubusercontent.com/org/repo/main/config.yaml' && export GITHUB_TOKEN='ghp_<your-token>' && curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash
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

### Installation Methods

The installer supports two installation methods for Claude Code:

#### 🎯 Native Installation (Default)

- Uses official installers from Anthropic
- No Node.js dependency required
- More reliable auto-updates
- Resolves Node.js v25+ compatibility issues
- Recommended for most users

#### 📦 NPM Installation (Fallback)
- Installs via npm package manager
- Requires Node.js 18+
- Used automatically if native installation fails
- Can be forced via environment variable

### Windows (PowerShell)

The Windows installer automatically:
- ✅ Installs Git for Windows (Git Bash) if not present
- ✅ Installs Node.js LTS (v18+) only if needed for npm method
- ✅ Handles dependencies (Microsoft.UI.Xaml) for winget if needed
- ✅ Falls back to direct downloads if winget is unavailable
- ✅ Configures `CLAUDE_CODE_GIT_BASH_PATH` if bash.exe is not on PATH
- ✅ Installs Claude Code CLI using native installer (with npm fallback)

**Reliability Features:**
- Native-first installation approach (bypasses Node.js dependency)
- Smart dependency resolution for winget/App Installer
- Automatic fallback to npm if native installation fails
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

The installer uses the native shell installer from Anthropic with automatic npm fallback if needed.

### Linux

```bash
curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/install-claude-linux.sh | bash
```

The installer uses the native shell installer from Anthropic with automatic npm fallback if needed.

### Environment Variables

Control the installation behavior with these environment variables:

#### CLAUDE_INSTALL_METHOD

- `auto` (default) - Try native installation first, fall back to npm if needed
- `native` - Use only native installation, no npm fallback
- `npm` - Use only npm installation method

#### CLAUDE_VERSION

- Specify a particular version to install (e.g., `1.0.128`)
- Forces npm installation method (native installers don't support version selection)

**Examples:**

```powershell
# Windows - Force npm installation
$env:CLAUDE_INSTALL_METHOD='npm'
iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/install-claude-windows.ps1')

# Windows - Install specific version
$env:CLAUDE_VERSION='1.0.128'
iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/install-claude-windows.ps1')

# Linux/macOS - Force native installation only
export CLAUDE_INSTALL_METHOD=native
curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/install-claude-linux.sh | bash

# Linux/macOS - Install specific version
export CLAUDE_VERSION=1.0.128
curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/install-claude-linux.sh | bash
```

### Troubleshooting

#### Native installation fails on Windows

- The installer will automatically fall back to npm method
- Check Windows firewall or corporate proxy settings
- Try manual installation: `irm https://claude.ai/install.ps1 | iex`

#### Native installation fails on macOS/Linux

- The installer will automatically fall back to npm method
- Ensure you have `curl` and `bash` installed
- Check sudo permissions if needed
- Try manual installation: `curl -fsSL https://claude.ai/install.sh | bash`

#### Node.js v25+ compatibility issues

- Native installation bypasses this issue entirely
- If you must use npm method, downgrade to Node.js v18 or v20 LTS

#### Switching from npm to native installation

- Uninstall npm version: `npm uninstall -g @anthropic-ai/claude-code`
- Run the installer again (it will use native method by default)
- Your configurations are preserved (both methods use the same config directory)

## 🤝 Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

## ⚠️ Disclaimer

This is a community project and is not officially affiliated with Anthropic. Claude Code is a product of Anthropic, PBC.

## 🆘 Getting Help

- **Bug reports**: [Open an issue](https://github.com/alex-feel/claude-code-toolbox/issues)
- **Claude Code documentation**: [Official docs](https://docs.anthropic.com/claude-code)
