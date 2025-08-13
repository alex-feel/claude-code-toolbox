# Claude Code Toolbox

A community toolbox for Claude Code - automated installers, scripts, agent templates, and utilities for Windows, macOS, and Linux.

## 🚀 Quick Install

### Windows (PowerShell)

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
- ✅ Runs `claude doctor` to verify the installation

**Reliability Features:**
- Smart dependency resolution for winget/App Installer
- Automatic fallback to direct downloads
- Cached availability checks to prevent redundant attempts
- Comprehensive PATH refresh for immediate command availability

### macOS and Linux

Coming soon! Check [docs/installing.md](docs/installing.md) for manual installation steps.

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

- [Installation Guide](docs/installing.md) - Detailed installation instructions
- [Troubleshooting](docs/troubleshooting.md) - Common issues and solutions
- [Quick Start](docs/quickstart.md) - Getting started with Claude Code
- [Sub-agents Guide](docs/agents.md) - Creating specialized AI assistants
- [Slash Commands](docs/slash-commands.md) - Custom command shortcuts
- [.claude Directory](docs/claude-directory.md) - Project configuration structure

## 🛠️ Repository Structure

```text
claude-code-toolbox/
├── scripts/           # Installation and utility scripts
│   ├── windows/       # Windows PowerShell scripts
│   ├── linux/         # Linux shell scripts
│   └── macos/         # macOS shell scripts
├── agents/            # Agent templates and examples
├── slash-commands/    # Custom slash command templates
└── docs/              # Documentation
```

## 🤝 Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

## ⚠️ Disclaimer

This is a community project and is not officially affiliated with Anthropic. Claude Code is a product of Anthropic, PBC.

## 🆘 Getting Help

- **Installation issues**: Check [docs/troubleshooting.md](docs/troubleshooting.md)
- **Bug reports**: [Open an issue](https://github.com/alex-feel/claude-code-toolbox/issues)
- **Claude Code documentation**: [Official docs](https://docs.anthropic.com/claude-code)

## ✨ After Installation

Once installed, verify everything works:

```bash
claude doctor
```

Then start using Claude:

```bash
claude
```

For IDE integration:
- **VS Code**: Run `claude` in the integrated terminal
- **JetBrains**: Install the Claude Code plugin from Marketplace

---

<!-- Version and release information is managed by Release Please -->
<!-- See releases: https://github.com/alex-feel/claude-code-toolbox/releases -->
