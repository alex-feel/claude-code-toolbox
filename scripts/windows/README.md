# Windows Scripts

PowerShell scripts for installing and configuring Claude Code on Windows systems.

## 📋 Available Scripts

### install-claude-windows.ps1

Base installer for Claude Code on Windows.

**Features:**
- Automatic dependency installation (Git Bash, Node.js)
- Smart package manager detection (winget with fallbacks)
- Environment variable configuration
- PATH management
- Installation verification

**Usage:**
```powershell
# Standard installation
.\install-claude-windows.ps1

# With verbose output
.\install-claude-windows.ps1 -Verbose

# Force reinstall
.\install-claude-windows.ps1 -Force
```

**Requirements:**
- Windows 10/11
- PowerShell 5.1 or later
- Internet connection
- Admin rights (auto-elevation if needed)

### setup-python-environment.ps1

Complete Python development environment setup for Claude Code.

**Features:**
- Runs base installer if Claude Code not present (Step 1)
- Creates configuration directories (Step 2)
- Downloads 7 Python-optimized subagents (Step 3)
- Installs 6 custom slash commands (Step 4)
- Downloads Python developer system prompt (Step 5)
- Configures Context7 MCP server (Step 6)
- Creates convenience launcher script (Step 7)
- Registers global `claude-python` command (Step 8)

**Usage:**
```powershell
# Full setup (installs Claude Code if needed)
.\setup-python-environment.ps1

# Skip Claude Code installation
.\setup-python-environment.ps1 -SkipInstall

# Force overwrite existing files
.\setup-python-environment.ps1 -Force

# Combine parameters
.\setup-python-environment.ps1 -SkipInstall -Force
```

**What it installs:**

| Component | Location | Description |
|-----------|----------|-------------|
| Subagents | `%USERPROFILE%\.claude\agents\` | 7 Python-specific agents |
| Commands | `%USERPROFILE%\.claude\commands\` | 6 development commands |
| Prompts | `%USERPROFILE%\.claude\prompts\` | Python developer prompt |
| Launcher | `%USERPROFILE%\.claude\start-python-claude.ps1` | Quick start script |
| Global Command | `%USERPROFILE%\.local\bin\claude-python.cmd` | System-wide command |

## 🔧 PowerShell Execution Policy

These scripts require appropriate execution policy:

```powershell
# Check current policy
Get-ExecutionPolicy

# Set policy for current user (recommended)
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

# Or bypass for single execution
powershell -ExecutionPolicy Bypass .\script-name.ps1
```

## 🌐 Proxy Configuration

For corporate environments:

```powershell
# Set proxy before running scripts
$env:HTTP_PROXY = "http://proxy.company.com:8080"
$env:HTTPS_PROXY = "http://proxy.company.com:8080"

# For authenticated proxies
$env:HTTP_PROXY = "http://username:password@proxy.company.com:8080"
```

## 🛡️ Security Features

### SmartScreen Warnings

Windows SmartScreen may warn about downloaded scripts. These scripts are:
- Open source and reviewable
- Digitally signed when possible
- Safe to run after review

To bypass SmartScreen:
1. Right-click the script file
2. Select Properties
3. Check "Unblock"
4. Click OK

### Script Signing

For enhanced security in enterprise environments:

```powershell
# Check if script is signed
Get-AuthenticodeSignature .\script-name.ps1

# Sign your own scripts
$cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert
Set-AuthenticodeSignature .\script-name.ps1 $cert
```

## 📝 Script Parameters

### Common Parameters

All scripts support standard PowerShell parameters:

```powershell
# Get help
Get-Help .\script-name.ps1 -Full

# Verbose output
.\script-name.ps1 -Verbose

# Debug mode
.\script-name.ps1 -Debug

# Confirm actions
.\script-name.ps1 -Confirm

# Dry run
.\script-name.ps1 -WhatIf
```

### Custom Parameters

#### install-claude-windows.ps1
- `-Force` - Force reinstallation
- `-SkipGitBash` - Skip Git Bash installation
- `-SkipNodeJs` - Skip Node.js installation

#### setup-python-environment.ps1
- `-SkipInstall` - Skip Claude Code installation
- `-Force` - Overwrite existing files

## 🔍 Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| "cannot be loaded because running scripts is disabled" | Set execution policy (see above) |
| "Access denied" | Run as Administrator or check file permissions |
| "Unable to connect" | Check proxy settings and internet connection |
| "Command not found" | Restart terminal to refresh PATH |

### Logging

Enable detailed logging:

```powershell
# Transcript logging
Start-Transcript -Path "$env:TEMP\claude-install.log"
.\script-name.ps1 -Verbose
Stop-Transcript

# View log
notepad "$env:TEMP\claude-install.log"
```

### Debug Mode

For troubleshooting:

```powershell
# Enable debug output
$DebugPreference = "Continue"
.\script-name.ps1 -Debug

# Reset debug preference
$DebugPreference = "SilentlyContinue"
```

## 🚀 Quick Start Examples

### Fresh Python Developer Setup

```powershell
# One-liner from web (recommended)
powershell -NoProfile -ExecutionPolicy Bypass -Command "iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-python-environment.ps1')"

# Alternative using curl (if preferred)
curl -L -o setup-python.ps1 https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/setup-python-environment.ps1
powershell -ExecutionPolicy Bypass .\setup-python.ps1
```

**What to Expect:**
The script will execute 8 steps in sequence:
1. **Install Claude Code** (if needed) - includes Git Bash and Node.js
2. **Create directories** - `.claude/agents`, `.claude/commands`, etc.
3. **Download subagents** - 7 Python-specific AI agents
4. **Install slash commands** - `/commit`, `/debug`, `/test`, etc.
5. **Setup system prompt** - Python developer configuration
6. **Configure MCP server** - Context7 for library documentation
7. **Create launcher script** - Quick start script
8. **Register global command** - `claude-python` available system-wide

**⚠️ After Setup - IMPORTANT:**
```powershell
# You can now use the simple global command:
claude-python

# NOT this (won't have Python configuration):
claude  # ❌ No system prompt loaded!
```

### Update Existing Installation

```powershell
# Update configs without reinstalling Claude Code
.\setup-python-environment.ps1 -SkipInstall -Force
```

## 📁 File Structure

After running scripts, your system will have:

```text
%USERPROFILE%\
└── .claude\
    ├── agents\           # Subagent configurations
    ├── commands\         # Slash commands
    ├── prompts\          # System prompts
    ├── settings.json     # User settings
    └── start-python-claude.ps1  # Launcher script

%LOCALAPPDATA%\
└── claude-code\          # Claude Code installation
    └── bin\
        └── claude.exe    # Main executable
```

## 🔄 Updates and Maintenance

### Updating Scripts

```powershell
# Get latest version
git pull origin main

# Or re-download
curl -L -o script.ps1 https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/script-name.ps1
```

### Cleaning Up

```powershell
# Remove Claude Code configurations
Remove-Item -Recurse -Force "$env:USERPROFILE\.claude"

# Uninstall Claude Code
winget uninstall claude-code
# Or
npm uninstall -g claude-code
```

## 🤝 Contributing

When modifying Windows scripts:

1. **Test on Windows 10 and 11**
2. **Maintain PowerShell 5.1 compatibility**
3. **Use approved verbs** (Get-, Set-, New-, etc.)
4. **Include proper error handling**
5. **Add comment-based help**
6. **Run PSScriptAnalyzer**

Example:

```powershell
# Run analyzer
Install-Module -Name PSScriptAnalyzer -Force
Invoke-ScriptAnalyzer -Path .\script-name.ps1
```

## 📚 Related Documentation

- [Windows Installer Internals](../../docs/windows-installer-internals.md)
- [Python Setup Guide](../../docs/python-setup.md)
- [Troubleshooting](../../docs/troubleshooting.md)
- [Main README](../../README.md)
