# Troubleshooting Guide

Common issues and solutions for Claude Code installation and usage.

## Table of Contents

- [Installation Issues](#installation-issues)
- [Runtime Errors](#runtime-errors)
- [Network Issues](#network-issues)
- [IDE Integration](#ide-integration)
- [Performance Issues](#performance-issues)
- [Getting Help](#getting-help)

## Installation Issues

### Windows

#### PowerShell Execution Policy Error

**Error**: "cannot be loaded because running scripts is disabled on this system"

**Solution**:
```powershell
# Option 1: Bypass for single execution
powershell -ExecutionPolicy Bypass -File install-claude-windows.ps1

# Option 2: Change policy for current user
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

#### Git Bash Not Found

**Error**: "bash.exe not found" or "Git Bash is required"

**Solutions**:

1. Install Git for Windows manually:
```powershell
winget install --id Git.Git
```

2. If Git is installed but not found:
```powershell
# Find bash.exe location
where.exe bash

# Set environment variable
setx CLAUDE_CODE_GIT_BASH_PATH "C:\Program Files\Git\bin\bash.exe"
```

3. Add Git to PATH:
```powershell
$env:Path += ";C:\Program Files\Git\bin"
setx PATH "$env:Path"
```

#### Node.js Version Too Old

**Error**: "Node.js version 16.x detected, version 18+ required"

**Solution**:
```powershell
# Uninstall old version
winget uninstall --id OpenJS.NodeJS

# Install LTS version
winget install --id OpenJS.NodeJS.LTS
```

#### Winget Not Available

**Error**: "winget is not recognized" or "Could not install winget"

**Common Cause**: Missing Microsoft.UI.Xaml.2.8 framework dependency

**Solutions**:

1. **Automatic (handled by installer)**:
   The installer now automatically installs the required UI.Xaml framework before winget.

2. **Manual installation if automatic fails**:
```powershell
# Install UI.Xaml framework first
$xamlUrl = 'https://github.com/microsoft/microsoft-ui-xaml/releases/download/v2.8.6/Microsoft.UI.Xaml.2.8.x64.appx'
Invoke-WebRequest -Uri $xamlUrl -OutFile UI.Xaml.appx
Add-AppxPackage -Path .\UI.Xaml.appx

# Then install App Installer (winget)
Invoke-WebRequest -Uri https://aka.ms/getwinget -OutFile AppInstaller.msixbundle
Add-AppxPackage -Path .\AppInstaller.msixbundle -ForceUpdateFromAnyVersion
```

3. **Alternative - Install from Microsoft Store**:
   Search for "App Installer" in Microsoft Store

**Note**: The installer will automatically fall back to direct downloads if winget installation fails, so winget is not required for successful installation.

#### Access Denied During Installation

**Error**: "Access is denied" or "Insufficient privileges"

**Solution**:
Run PowerShell as Administrator or allow the script to self-elevate when prompted.

### macOS

#### npm Command Not Found

**Solution**:
```bash
# Install Node.js with Homebrew
brew install node

# Or download from nodejs.org
curl -o- https://nodejs.org/dist/v20.11.0/node-v20.11.0.pkg | sudo installer -pkg - -target /
```

#### Permission Denied

**Error**: "EACCES: permission denied"

**Solution**:
```bash
# Configure npm to use local directory
mkdir ~/.npm-global
npm config set prefix '~/.npm-global'
echo 'export PATH=~/.npm-global/bin:$PATH' >> ~/.zshrc
source ~/.zshrc
```

### Linux

#### Missing Dependencies

**Error**: Various package not found errors

**Ubuntu/Debian**:
```bash
sudo apt update
sudo apt install -y build-essential git curl
```

**Fedora/RHEL**:
```bash
sudo dnf groupinstall "Development Tools"
sudo dnf install git nodejs
```

## Runtime Errors

### Claude Command Not Found

**After installation, `claude` command not recognized**

**Solutions**:

1. **Refresh PATH** (Windows):
```powershell
# Comprehensive PATH refresh
$machineEnv = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
$userEnv = [System.Environment]::GetEnvironmentVariable("Path", "User")
$env:Path = "$machineEnv;$userEnv"

# Add npm global path if not present
$npmPath = "$env:APPDATA\npm"
if ((Test-Path $npmPath) -and ($env:Path -notlike "*$npmPath*")) {
    $env:Path = "$env:Path;$npmPath"
}
```

2. **Restart terminal** or open new terminal window (most reliable)

3. **Check npm global installation path**:
```powershell
# Find where claude was installed
npm list -g claude-code

# Check npm global prefix
npm config get prefix

# Manually run from npm location
& "$env:APPDATA\npm\claude.cmd" doctor
```

3. **Check installation**:
```bash
npm list -g claude-code
```

4. **Reinstall if needed**:
```bash
npm uninstall -g claude-code
npm install -g claude-code
```

### Claude Doctor Failures

**Run diagnostics**:
```bash
claude doctor --verbose
```

Common fixes:

1. **Git not detected**:
```bash
# Verify Git installation
git --version

# Add to PATH if needed
export PATH="/usr/local/bin/git:$PATH"
```

2. **Node version mismatch**:
```bash
# Check version
node --version

# Update if needed
npm install -g n
n lts
```

### API Connection Errors

**Error**: "Failed to connect to Claude API"

**Solutions**:

1. **Check internet connection**
2. **Verify API endpoint**:
```bash
curl -I https://api.anthropic.com/health
```
3. **Check firewall/antivirus settings**

## Network Issues

### Behind Corporate Proxy

**Configure proxy settings**:

```bash
# Bash/Zsh
export HTTP_PROXY=http://proxy.company.com:8080
export HTTPS_PROXY=http://proxy.company.com:8080
export NO_PROXY=localhost,127.0.0.1

# npm
npm config set proxy http://proxy.company.com:8080
npm config set https-proxy http://proxy.company.com:8080

# Git
git config --global http.proxy http://proxy.company.com:8080
git config --global https.proxy http://proxy.company.com:8080
```

**Windows PowerShell**:
```powershell
$env:HTTP_PROXY = "http://proxy.company.com:8080"
$env:HTTPS_PROXY = "http://proxy.company.com:8080"
[Environment]::SetEnvironmentVariable("HTTP_PROXY", "http://proxy.company.com:8080", "User")
[Environment]::SetEnvironmentVariable("HTTPS_PROXY", "http://proxy.company.com:8080", "User")
```

### SSL Certificate Issues

**Error**: "unable to verify the first certificate"

**Solutions**:

1. **Update certificates**:
```bash
# Ubuntu/Debian
sudo apt-get install ca-certificates

# macOS
brew install ca-certificates
```

2. **Corporate certificates**:
```bash
# Add corporate CA
export NODE_EXTRA_CA_CERTS="/path/to/corporate-ca.crt"
export SSL_CERT_FILE="/path/to/corporate-ca.crt"
```

3. **Temporary workaround** (not recommended for production):
```bash
export NODE_TLS_REJECT_UNAUTHORIZED=0
```

## IDE Integration

### VS Code

#### Extension Not Installing

**Manual installation**:
1. Open VS Code
2. Press `Ctrl+Shift+P` (Windows/Linux) or `Cmd+Shift+P` (macOS)
3. Type "Install Extensions"
4. Search for "Claude Code"
5. Click Install

#### Terminal Integration Issues

**Solution**:
1. Set default shell to bash/zsh
2. Restart VS Code
3. Open new integrated terminal

### JetBrains IDEs

#### Plugin Not Found

**Solution**:
1. File → Settings → Plugins
2. Click "Marketplace"
3. Search "Claude Code"
4. Install and restart IDE

#### Remote Development Issues

For remote development, install plugin on remote host:
```bash
# On remote machine
npm install -g claude-code
```

## Performance Issues

### Slow Response Times

**Optimize performance**:

1. **Clear cache**:
```bash
npm cache clean --force
```

2. **Check system resources**:
```bash
# Windows
taskmgr

# macOS/Linux
top
htop
```

3. **Reduce context size**:
```bash
claude --max-context 4000
```

### High Memory Usage

**Solutions**:

1. **Increase Node memory**:
```bash
export NODE_OPTIONS="--max-old-space-size=4096"
```

2. **Close unnecessary applications**

3. **Use lightweight mode**:
```bash
claude --lightweight
```

## Common Error Messages

### "Package failed updates, dependency or conflict validation"

**Error**: When installing App Installer/winget

**Cause**: Missing Microsoft.UI.Xaml framework dependency

**Solution**: The updated installer automatically installs the required framework. If you see this error with the old installer, update to the latest version:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/install-claude-windows.ps1')"
```

### "ENOENT: no such file or directory"

File or directory doesn't exist. Check paths and create if needed.

### "EACCES: permission denied"

Permission issue. Run with appropriate privileges or fix file permissions.

### "ETIMEDOUT"

Network timeout. Check internet connection and proxy settings.

### "MODULE_NOT_FOUND"

Missing dependency. Reinstall Claude Code:
```bash
npm uninstall -g claude-code
npm install -g claude-code
```

## Getting Help

### Diagnostic Information

Gather this information when reporting issues:

```bash
# System info
claude doctor --verbose > diagnostic.txt

# Version info
node --version >> diagnostic.txt
npm --version >> diagnostic.txt
git --version >> diagnostic.txt

# Environment
echo $PATH >> diagnostic.txt
echo $HTTP_PROXY >> diagnostic.txt
```

### Support Channels

1. **GitHub Issues**: [Report bugs](https://github.com/alex-feel/claude-code-toolbox/issues)
2. **Documentation**: [Official docs](https://docs.anthropic.com/claude-code)
3. **Community**: [Discord/Forum links]

### Debug Mode

Run Claude in debug mode for detailed logs:
```bash
claude --debug
```

### Logs Location

- **Windows**: `%APPDATA%\claude\logs\`
- **macOS**: `~/Library/Logs/claude/`
- **Linux**: `~/.local/share/claude/logs/`

## Reset and Reinstall

If all else fails, complete reset:

```bash
# 1. Uninstall
npm uninstall -g claude-code

# 2. Clear cache
npm cache clean --force

# 3. Remove config
# Windows
rmdir /s %APPDATA%\claude

# macOS/Linux
rm -rf ~/.config/claude

# 4. Reinstall
npm install -g claude-code
```

---

Still having issues? [Open a GitHub issue](https://github.com/alex-feel/claude-code-toolbox/issues) with your diagnostic information.
