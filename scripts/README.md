# Scripts Directory

This directory contains installation and setup scripts for Claude Code across different platforms.

## 📁 Directory Structure

```text
scripts/
├── windows/                     # Windows PowerShell scripts
│   ├── install-claude-windows.ps1      # Base Claude Code installer
│   └── setup-python-environment.ps1    # Python development environment setup
├── linux/                       # Linux shell scripts
│   ├── install-claude-linux.sh         # Base Claude Code installer
│   └── setup-python-environment.sh     # Python development environment setup
├── macos/                       # macOS shell scripts
│   ├── install-claude-macos.sh         # Base Claude Code installer
│   └── setup-python-environment.sh     # Python development environment setup
└── hooks/                       # Git hooks and validation scripts
    └── check-powershell.ps1            # PowerShell script analyzer
```

## 🚀 Quick Start

### Python Developer Setup (Recommended)

The Python environment setup scripts provide a complete development environment with one command:

#### Windows
```powershell
.\scripts\windows\setup-python-environment.ps1
```

#### Linux
```bash
bash scripts/linux/setup-python-environment.sh
```

#### macOS
```bash
bash scripts/macos/setup-python-environment.sh
```

### Standard Installation

For basic Claude Code installation without additional configurations:

#### Windows
```powershell
.\scripts\windows\install-claude-windows.ps1
```

#### Linux
```bash
bash scripts/linux/install-claude-linux.sh
```

#### macOS
```bash
bash scripts/macos/install-claude-macos.sh
```

## 📋 Script Types

### Installation Scripts (`install-claude-*`)

Basic Claude Code installation scripts that:
- Install system dependencies (Git, Node.js)
- Download and install Claude Code CLI
- Configure environment variables
- Verify installation with `claude doctor`

### Environment Setup Scripts (`setup-*-environment`)

Comprehensive setup scripts that:
- Run the base installer (if needed)
- Download and configure subagents
- Install custom slash commands
- Configure MCP servers
- Set up system prompts
- Create convenience launchers

## 🔧 Script Options

### Windows Scripts

PowerShell scripts support these parameters:

```powershell
# Skip Claude Code installation (if already installed)
.\setup-python-environment.ps1 -SkipInstall

# Force overwrite existing configuration files
.\setup-python-environment.ps1 -Force

# Combine options
.\setup-python-environment.ps1 -SkipInstall -Force
```

### Linux/macOS Scripts

Shell scripts support these options:

```bash
# Skip Claude Code installation
bash setup-python-environment.sh --skip-install

# Force overwrite existing files
bash setup-python-environment.sh --force

# Show help
bash setup-python-environment.sh --help
```

## 🔒 Security Considerations

### Script Verification

Always verify scripts before running:

1. **Review the source code** - All scripts are open source
2. **Pin to specific commits** for supply chain security
3. **Check file hashes** if downloading manually

### Execution Policies

#### Windows
Scripts require appropriate execution policy:
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

#### Linux/macOS
Ensure scripts have execute permissions:
```bash
chmod +x setup-python-environment.sh
```

## 📝 Script Features

### Cross-Platform Compatibility

- **Windows**: PowerShell 5.1+ compatible
- **Linux**: Bash 4.0+ compatible, tested on major distributions
- **macOS**: Compatible with macOS 10.15+ (Catalina and later)

### Error Handling

All scripts include:
- Comprehensive error checking
- Graceful fallbacks
- Clear error messages
- Rollback capabilities (where applicable)

### Logging

Scripts provide detailed output with:
- Color-coded status messages
- Progress indicators
- Success/failure summaries
- Next steps guidance

## 🛠️ Customization

### Environment Variables

Scripts respect these environment variables:

```bash
# Proxy settings (all platforms)
HTTP_PROXY=http://proxy:port
HTTPS_PROXY=http://proxy:port

# Custom Claude directory (all platforms)
CLAUDE_USER_DIR=/custom/path/.claude
```

### Configuration Files

Scripts create configuration in:
- **Windows**: `%USERPROFILE%\.claude\`
- **Linux/macOS**: `~/.claude/`

## 🤝 Contributing

When adding new scripts:

1. Follow platform conventions
2. Include comprehensive error handling
3. Add clear documentation
4. Test on target platforms
5. Update this README

See [CONTRIBUTING.md](../CONTRIBUTING.md) for detailed guidelines.

## 📚 Related Documentation

- [Python Setup Guide](../docs/python-setup.md)
- [Installation Guide](../docs/installing.md)
- [Troubleshooting](../docs/troubleshooting.md)
- [Windows Script Details](windows/README.md)
- [Linux Script Details](linux/README.md)
- [macOS Script Details](macos/README.md)
