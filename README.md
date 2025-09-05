# Claude Code Toolbox

A community toolbox for Claude Code - automated installers, scripts, agent templates, and utilities for Windows, macOS, and Linux.

## 🚀 Quick Install

### 🐍 Python Developer Setup

Set up a complete Python development environment with one command:

#### Windows

##### Option 1: Simple approach (recommended)
```powershell
# First set the environment variable, then run the installer
$env:CLAUDE_ENV_CONFIG='python'
iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')
```

##### Option 2: One-liner (requires escaping)
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "`$env:CLAUDE_ENV_CONFIG='python'; iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')"
```

##### Option 3: Using CMD
```cmd
curl -L -o %TEMP%\setup-env.ps1 https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1 && powershell -NoProfile -ExecutionPolicy Bypass -File %TEMP%\setup-env.ps1 python
```

##### Option 4: Using local configuration (for sensitive configs)
```powershell
# Use a local file containing API keys or other sensitive data
$env:CLAUDE_ENV_CONFIG='./my-python-env.yaml'
iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-environment.ps1')
```

#### macOS
```bash
# Repository config
CLAUDE_ENV_CONFIG=python curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/setup-environment.sh | bash

# Local config file
CLAUDE_ENV_CONFIG=./my-env.yaml curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/setup-environment.sh | bash
```

#### Linux
```bash
# Repository config
CLAUDE_ENV_CONFIG=python curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash

# Local config file
CLAUDE_ENV_CONFIG=./my-env.yaml curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-environment.sh | bash
```

This automated setup includes:
- ✨ Claude Code installation
- 🤖 7 Python-optimized subagents (code review, testing, docs, etc.)
- 🎯 6 custom slash commands (/commit, /debug, /test, etc.)
- 📚 Context7 MCP server for up-to-date library documentation
- 🔧 Comprehensive Python developer system prompt
- 🚀 Convenience launchers for quick startup

**✅ After setup, use the simple command:**
```bash
claude-python  # Works in all Windows shells (PowerShell, CMD, Git Bash)
```

The setup automatically creates properly escaped wrappers for each Windows shell, ensuring the Python developer system prompt loads correctly regardless of which shell you use.

---

### ⚠️ Security Warning: Environment Configurations

**IMPORTANT:** Environment configurations can contain:
- 🔑 **API Keys** for MCP servers
- 📝 **System commands** that will be executed during setup
- 🪝 **Hook scripts** that run automatically on Claude Code events
- 🌐 **Remote dependencies** that will be downloaded and installed

**Only use environment configurations from trusted sources!**

When loading configurations:
- ✅ **Repository configs** (`python`) - Reviewed and maintained by the community
- ✅ **Your local files** (`./my-config.yaml`) - Under your control
- ⚠️ **Remote URLs** (`https://example.com/config.yaml`) - **VERIFY THE SOURCE FIRST!**

The setup script will warn you when loading from remote URLs. Always review the configuration content before proceeding.

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

### macOS

```bash
curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/install-claude-macos.sh | bash
```

### Linux

```bash
curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/install-claude-linux.sh | bash
```

**Note**: macOS and Linux installers are in beta.

## 📋 Requirements

### Windows
- Windows 10/11 with PowerShell 5.1+
- Internet connection
- Admin rights (auto-elevation for system-wide installs)

### Behind a Proxy?

Set your proxy before running:

```powershell
$env:HTTP_PROXY = "http://your-proxy:port"
$env:HTTPS_PROXY = "http://your-proxy:port"
```

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
│   ├── install-claude.py        # Cross-platform Claude installer
│   ├── setup-environment.py     # Cross-platform environment setup
│   ├── windows/                 # Windows bootstrap scripts
│   │   ├── install-claude-windows.ps1
│   │   └── setup-environment.ps1
│   ├── linux/                   # Linux bootstrap scripts
│   │   ├── install-claude-linux.sh
│   │   └── setup-environment.sh
│   └── macos/                   # macOS bootstrap scripts
│       ├── install-claude-macos.sh
│       └── setup-environment.sh
├── agents/                      # Agent templates and examples
│   ├── examples/                # Ready-to-use subagents (7 specialized agents)
│   └── templates/               # Templates for creating new agents
├── system-prompts/              # Comprehensive system prompts
│   ├── examples/                # Role-specific configurations (3 roles)
│   └── templates/               # Templates for custom prompts
├── output-styles/               # Output style transformations
│   ├── examples/                # Ready-to-use professional styles (6 styles)
│   └── templates/               # Templates for creating new styles
├── slash-commands/              # Custom slash command templates
│   ├── examples/                # Ready-to-use commands (6 commands)
│   └── templates/               # Command templates
├── hooks/                       # Git hooks and event handlers
│   └── examples/                # Ready-to-use hooks
├── environments/                # Environment configurations
│   ├── examples/                # Ready-to-use environments
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

## ✨ After Installation

### Standard Installation
Once installed, verify everything works:

```bash
claude doctor
```

Then start using Claude:

```bash
claude
```

### Python Developer Setup
After running the Python setup script:

```bash
# 1. Verify installation
claude doctor

# 2. Start Claude with Python configuration - just run:
claude-python

# That's it! The command is registered globally during setup
```

**⚠️ Common Mistakes:**
- Running `claude` directly won't load the Python system prompt!

For IDE integration:
- **VS Code**: Configure terminal to use the launcher script
- **JetBrains**: Set shell path to the launcher script

---

<!-- Version and release information is managed by Release Please -->
<!-- See releases: https://github.com/alex-feel/claude-code-toolbox/releases -->
