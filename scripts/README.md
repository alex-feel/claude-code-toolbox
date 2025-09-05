# Scripts Directory

This directory contains installation and setup scripts for Claude Code across different platforms.

## 📁 Directory Structure

```text
scripts/
├── install-claude.py            # Cross-platform Claude Code installer (Python)
├── setup-environment.py         # Cross-platform environment setup (Python)
├── windows/                     # Windows bootstrap scripts
│   ├── install-claude-windows.ps1      # Bootstrap: installs uv, runs install-claude.py
│   └── setup-environment.ps1            # Bootstrap: installs uv, runs setup-environment.py
├── linux/                       # Linux bootstrap scripts
│   ├── install-claude-linux.sh         # Bootstrap: installs uv, runs install-claude.py
│   └── setup-environment.sh             # Bootstrap: installs uv, runs setup-environment.py
├── macos/                       # macOS bootstrap scripts
│   ├── install-claude-macos.sh         # Bootstrap: installs uv, runs install-claude.py
│   └── setup-environment.sh             # Bootstrap: installs uv, runs setup-environment.py
└── hooks/                       # Git hooks and validation scripts
    └── check-powershell.ps1            # PowerShell script analyzer
```

## 🏗️ Architecture

The installation system uses a two-tier architecture:

1. **Platform-specific bootstrap scripts** (minimal ~60 lines each)
   - Install `uv` (Astral's fast Python package manager)
   - Download and run the appropriate Python script
   - Handle platform-specific PATH setup

2. **Cross-platform Python scripts** (comprehensive installers)
   - `install-claude.py`: Handles Git Bash, Node.js, and Claude Code installation
   - `setup-environment.py`: Sets up complete development environment based on YAML configuration
   - Work identically across Windows, Linux, and macOS
   - Require Python 3.12+ (automatically handled by uv)

## 📦 Requirements

### Automatic Installation
The scripts automatically install all requirements, including:
- **uv** - Astral's fast Python package and project manager
- **Python 3.12+** - Managed automatically by uv
- **Node.js 18+** - For Claude Code CLI
- **Git** (Windows only) - For Git Bash

### Manual Prerequisites
If you prefer manual installation:
- **uv**: Install from [docs.astral.sh/uv](https://docs.astral.sh/uv/)
- **Python**: Version 3.12 or higher
- **Node.js**: Version 18.0.0 or higher
- **Git**: Required on Windows for Git Bash

## 🚀 Quick Start

### Environment Setup (Recommended)

The environment setup scripts provide complete development environments based on YAML configurations:

#### Windows
```powershell
# For Python environment
.\scripts\windows\setup-environment.ps1 python

# Or using environment variable
$env:CLAUDE_ENV_CONFIG='python'; .\scripts\windows\setup-environment.ps1
```

#### Linux
```bash
# For Python environment
bash scripts/linux/setup-environment.sh python

# Or using environment variable
CLAUDE_ENV_CONFIG=python bash scripts/linux/setup-environment.sh
```

#### macOS
```bash
# For Python environment
bash scripts/macos/setup-environment.sh python

# Or using environment variable
CLAUDE_ENV_CONFIG=python bash scripts/macos/setup-environment.sh
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

## 📋 Script Functionality

### Installation Scripts (`install-claude.py`)

Comprehensive Claude Code installer that:
- **Windows**: Installs Git Bash via winget or direct download
- **All Platforms**: Installs Node.js LTS (>= 18.0.0) if needed
- Downloads and installs Claude Code CLI via npm
- Configures PowerShell execution policy (Windows)
- Sets up environment variables (PATH, CLAUDE_CODE_GIT_BASH_PATH)
- Handles SSL certificate issues in corporate environments
- Provides fallback installation methods

### Environment Setup Scripts (`setup-environment.py`)

Configuration-driven environment setup that installs based on YAML files:
- Claude Code (if not already installed)
- **Custom agents** defined in configuration
- **Slash commands** specified in YAML
- **MCP servers** with support for HTTP, SSE, and stdio transports
- **Hooks** for automatic actions on events
- **System prompts** for role-specific behavior
- **Output styles** for formatted responses
- **Global commands** (e.g., `claude-python`) that work in all shells

Example Python environment includes:
- 7 Python-optimized subagents
- 6 custom slash commands
- Context7 MCP server for documentation
- Python developer system prompt
- Ruff linting hook

## 🔧 Script Options

### Python Scripts (All Platforms)

The Python scripts support command-line arguments:

```bash
# Specify configuration
python setup-environment.py python

# Skip Claude Code installation (if already installed)
python setup-environment.py python --skip-install

# Use environment variable
CLAUDE_ENV_CONFIG=python python setup-environment.py --skip-install
```

### Bootstrap Scripts

The platform-specific bootstrap scripts automatically:
1. Install uv if not present
2. Download the Python script from GitHub
3. Run it with Python 3.12+ via uv
4. Pass any arguments through to the Python script

```bash
# Linux/macOS - configuration and arguments are passed to Python script
bash setup-environment.sh python --skip-install

# Windows - configuration and arguments are passed to Python script
.\setup-environment.ps1 python --skip-install
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

- **Python Scripts**: Work identically on Windows, Linux, and macOS
- **Python Version**: Requires Python 3.12+ (automatically handled by uv)
- **Package Manager**: Uses uv for fast, reliable Python management
- **Windows**: PowerShell 5.1+ for bootstrap, full Windows 10/11 support
  - `claude-python` command works in **all Windows shells** (PowerShell, CMD, Git Bash)
  - Automated wrappers handle shell-specific escaping requirements
- **Linux**: Bash 4.0+ for bootstrap, tested on Ubuntu, Debian, Fedora, Arch
- **macOS**: Compatible with macOS 10.15+ (Catalina and later)

### Advanced Features

- **SSL Certificate Handling**: Automatic fallback for corporate environments
- **Multiple Installation Methods**: winget, direct download, package managers
- **Intelligent Path Management**: Automatic PATH configuration
- **Git Bash Detection**: Multiple detection strategies on Windows
- **Node.js Management**: Automatic LTS installation if needed
- **Cross-Shell Support on Windows**: Automated wrappers for all shells
  - `claude-python` command works in PowerShell, CMD, and Git Bash
  - Each shell has a properly escaped wrapper for reliable operation

### Error Handling

All scripts include:
- Comprehensive error checking
- Graceful fallbacks for network issues
- SSL certificate verification with fallback
- Clear error messages with solutions
- Rollback capabilities (where applicable)

### Logging

Scripts provide detailed output with:
- Color-coded status messages (cross-platform)
- Progress indicators for long operations
- Success/failure summaries
- Next steps guidance
- Detailed installation reports

## 🛠️ Customization

### Environment Variables

Scripts respect these environment variables:

```bash
# Proxy settings (all platforms)
HTTP_PROXY=http://proxy:port
HTTPS_PROXY=http://proxy:port

# Custom Git Bash path (Windows only)
CLAUDE_CODE_GIT_BASH_PATH=C:\Program Files\Git\bin\bash.exe

# Terminal session detection (Windows)
WT_SESSION=1  # Windows Terminal detection for ANSI colors
```

### Configuration Files

Scripts create configuration in:
- **Windows**: `%USERPROFILE%\.claude\`
- **Linux/macOS**: `~/.claude/`

Directory structure created:
```text
~/.claude/
├── agents/          # Subagent configurations
├── commands/        # Slash command definitions
├── prompts/         # System prompts
├── output-styles/   # Output style configurations
├── hooks/           # Event handler scripts
└── start-<command-name>.{ps1,sh}  # Launcher script
```

## 🤝 Contributing

When adding new scripts:

1. Follow platform conventions
2. Include comprehensive error handling
3. Add clear documentation
4. Test on target platforms
5. Update this README

See [CONTRIBUTING.md](../CONTRIBUTING.md) for detailed guidelines.
