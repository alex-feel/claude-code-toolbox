# Scripts Directory

This directory contains installation and setup scripts for Claude Code across different platforms.

## 📁 Directory Structure

```text
scripts/
├── install-claude.py            # Cross-platform Claude Code installer (Python)
├── setup-python-environment.py  # Cross-platform Python environment setup (Python)
├── windows/                     # Windows bootstrap scripts
│   ├── install-claude-windows.ps1      # Bootstrap: installs uv, runs install-claude.py
│   └── setup-python-environment.ps1    # Bootstrap: installs uv, runs setup-python-environment.py
├── linux/                       # Linux bootstrap scripts
│   ├── install-claude-linux.sh         # Bootstrap: installs uv, runs install-claude.py
│   └── setup-python-environment.sh     # Bootstrap: installs uv, runs setup-python-environment.py
├── macos/                       # macOS bootstrap scripts
│   ├── install-claude-macos.sh         # Bootstrap: installs uv, runs install-claude.py
│   └── setup-python-environment.sh     # Bootstrap: installs uv, runs setup-python-environment.py
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
   - `setup-python-environment.py`: Sets up complete Python development environment
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

### Environment Setup Scripts (`setup-python-environment.py`)

Complete Python development environment that installs:
- Claude Code (if not already installed)
- **7 general-purpose subagents**:
  - code-reviewer (code quality analysis)
  - doc-writer (documentation generation)
  - implementation-guide (library usage guidance)
  - performance-optimizer (performance analysis)
  - refactoring-assistant (code refactoring)
  - security-auditor (security analysis)
  - test-generator (test creation)
- **6 Custom slash commands**:
  - /commit (smart Git commits)
  - /debug (debugging assistance)
  - /document (documentation generation)
  - /refactor (code refactoring)
  - /review (code review)
  - /test (test generation)
- **Python developer system prompt** with SOLID, DRY, KISS, YAGNI principles
- **Context7 MCP server** for up-to-date library documentation
- **Global `claude-python` command** (Git Bash only on Windows)

## 🔧 Script Options

### Python Scripts (All Platforms)

The Python scripts support command-line arguments:

```bash
# Skip Claude Code installation (if already installed)
python setup-python-environment.py --skip-install

# Force overwrite existing configuration files
python setup-python-environment.py --force

# Combine options
python setup-python-environment.py --skip-install --force
```

### Bootstrap Scripts

The platform-specific bootstrap scripts automatically:
1. Install uv if not present
2. Download the Python script from GitHub
3. Run it with Python 3.12+ via uv
4. Pass any arguments through to the Python script

```bash
# Linux/macOS - arguments are passed to Python script
bash setup-python-environment.sh --skip-install --force

# Windows - arguments are passed to Python script
.\setup-python-environment.ps1
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
  - `claude-python` command works **only in Git Bash** due to shell escaping limitations
  - PowerShell/CMD cannot properly pass the system prompt - Git Bash is REQUIRED
- **Linux**: Bash 4.0+ for bootstrap, tested on Ubuntu, Debian, Fedora, Arch
- **macOS**: Compatible with macOS 10.15+ (Catalina and later)

### Advanced Features

- **SSL Certificate Handling**: Automatic fallback for corporate environments
- **Multiple Installation Methods**: winget, direct download, package managers
- **Intelligent Path Management**: Automatic PATH configuration
- **Git Bash Detection**: Multiple detection strategies on Windows
- **Node.js Management**: Automatic LTS installation if needed
- **Git Bash Requirement on Windows**: Due to command-line escaping limitations
  - `claude-python` command is available only in Git Bash
  - PowerShell/CMD users must use the full command syntax

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
└── start-python-claude.{ps1,sh}  # Launcher script
```

## 🤝 Contributing

When adding new scripts:

1. Follow platform conventions
2. Include comprehensive error handling
3. Add clear documentation
4. Test on target platforms
5. Update this README

See [CONTRIBUTING.md](../CONTRIBUTING.md) for detailed guidelines.
