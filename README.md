# Claude Code Toolbox

A community toolbox for Claude Code - automated installers and environment configuration framework for Windows, macOS, and Linux.

## 🚀 Quick Install

## 🚀 Quick Start with Environment Configurations

Set up a complete development environment with specialized configurations:

### Windows

#### Option 1: One-liner (recommended)
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

### Standard Installation

#### Windows (PowerShell)

Run this command in PowerShell (as regular user, it will elevate if needed):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/install-claude-windows.ps1')"
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

Visit the [Claude Code Toolbox Wiki](https://github.com/alex-feel/claude-code-toolbox/wiki) for guides on creating your own:
- Sub-agents (specialized AI assistants)
- System Prompts (role-based configurations)
- Output Styles (transform Claude Code for different domains)
- Slash Commands (custom command shortcuts)
- MCP Servers (Model Context Protocol setup)
- Hooks (event-driven automations)

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
├── tests/                       # Test suite for the toolbox
│   ├── conftest.py              # Test fixtures and configuration
│   └── ...                      # Unit and integration tests
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
