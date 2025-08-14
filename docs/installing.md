# Installation Guide

Comprehensive installation instructions for Claude Code across all platforms.

## Table of Contents

- [Windows](#windows)
- [macOS](#macos)
- [Linux](#linux)
- [Docker](#docker)
- [Manual Installation](#manual-installation)
- [Verification](#verification)
- [Troubleshooting](#troubleshooting)

## Windows

### Automated Installation (Recommended)

The easiest way to install on Windows is using our PowerShell script:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/install-claude-windows.ps1')"
```

This script:
1. Checks for Git Bash and installs if missing
2. Checks for Node.js v18+ and installs if missing
3. Configures environment variables
4. Installs Claude Code CLI
5. Runs verification

### Manual Installation

If you prefer manual installation:

#### Step 1: Install Git for Windows

Download from [git-scm.com](https://git-scm.com/download/win) or use winget:

```powershell
winget install --id Git.Git
```

#### Step 2: Install Node.js

Download LTS from [nodejs.org](https://nodejs.org/) or use winget:

```powershell
winget install --id OpenJS.NodeJS.LTS
```

#### Step 3: Configure Environment (if needed)

If `bash.exe` is not on PATH:

```powershell
setx CLAUDE_CODE_GIT_BASH_PATH "C:\Program Files\Git\bin\bash.exe"
```

#### Step 4: Install Claude Code

```powershell
irm https://claude.ai/install.ps1 | iex
```

### Alternative: Using Package Managers

#### Scoop

```powershell
# Install Scoop if not present
irm get.scoop.sh | iex

# Install dependencies
scoop install git nodejs

# Install Claude Code
irm https://claude.ai/install.ps1 | iex
```

#### Chocolatey

```powershell
# Install dependencies
choco install git nodejs

# Install Claude Code
irm https://claude.ai/install.ps1 | iex
```

## macOS

### Automated Installation

```bash
curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/install-claude-macos.sh | bash
```

**Features:**
- Automatically installs Node.js if missing or outdated
- Installs Claude Code CLI via npm or official installer
- Configures shell PATH for immediate use
- Works with zsh, bash, and fish shells

### Manual Installation

#### Step 1: Install Homebrew (if needed)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

#### Step 2: Install Dependencies

```bash
brew install git node
```

#### Step 3: Install Claude Code

```bash
curl -fsSL https://claude.ai/install.sh | sh
```

## Linux

### Automated Installation

```bash
curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/install-claude-linux.sh | bash
```

**Features:**
- Detects your Linux distribution automatically
- Installs Node.js using the appropriate package manager
- Installs Claude Code CLI via npm or official installer
- Works with Ubuntu, Debian, Fedora, RHEL, CentOS, Arch, and more

### Manual Installation

#### Ubuntu/Debian

```bash
# Update package list
sudo apt update

# Install dependencies
sudo apt install -y git curl

# Install Node.js via NodeSource
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt install -y nodejs

# Install Claude Code
curl -fsSL https://claude.ai/install.sh | sh
```

### Fedora/RHEL/CentOS

```bash
# Install dependencies
sudo dnf install -y git nodejs npm

# Install Claude Code
curl -fsSL https://claude.ai/install.sh | sh
```

### Arch Linux

```bash
# Install dependencies
sudo pacman -S git nodejs npm

# Install Claude Code
curl -fsSL https://claude.ai/install.sh | sh
```

### Using Node Version Managers

#### With nvm

```bash
# Install nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash

# Install Node.js
nvm install --lts
nvm use --lts

# Install Claude Code
npm install -g claude-code
```

#### With fnm

```bash
# Install fnm
curl -fsSL https://fnm.vercel.app/install | bash

# Install Node.js
fnm install --lts
fnm use lts-latest

# Install Claude Code
npm install -g claude-code
```

## Docker

### Using Docker

**Note**: Pre-built images are not yet available. You can build your own image using the Dockerfile below.

### Building Your Own Image

Create a `Dockerfile`:

```dockerfile
FROM node:lts

# Install Git
RUN apt-get update && apt-get install -y git

# Install Claude Code
RUN npm install -g claude-code

WORKDIR /workspace

CMD ["claude"]
```

Build and run:

```bash
docker build -t my-claude-code .
docker run -it --rm -v $(pwd):/workspace my-claude-code
```

## Manual Installation

### Prerequisites

1. **Git**: Version 2.0 or higher
2. **Node.js**: Version 18.0 or higher
3. **npm**: Usually comes with Node.js

### Installation Steps

1. Verify prerequisites:

```bash
git --version    # Should be 2.0+
node --version   # Should be 18.0+
npm --version    # Should be 8.0+
```

2. Install Claude Code globally:

```bash
npm install -g claude-code
```

3. Verify installation:

```bash
claude --version
claude doctor
```

## Verification

After installation, always verify:

```bash
claude doctor
```

Expected output:
```text
✅ Claude Code CLI installed
✅ Git available
✅ Node.js v18+ installed
✅ npm available
✅ Environment configured correctly
```

## Troubleshooting

### Windows Issues

#### "bash.exe not found"

Set the environment variable:
```powershell
setx CLAUDE_CODE_GIT_BASH_PATH "C:\Program Files\Git\bin\bash.exe"
```

#### "Execution Policy" Error

Run PowerShell as Administrator:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### macOS Issues

#### "Command not found"

Add to PATH in `~/.zshrc` or `~/.bash_profile`:
```bash
export PATH="$PATH:$(npm config get prefix)/bin"
```

### Linux Issues

#### Permission Denied

Use npm prefix for local installation:
```bash
npm config set prefix ~/.npm
export PATH="$PATH:~/.npm/bin"
npm install -g claude-code
```

### Proxy Configuration

For corporate networks:

```bash
# HTTP proxy
export HTTP_PROXY=http://proxy.company.com:8080
export HTTPS_PROXY=http://proxy.company.com:8080

# npm proxy
npm config set proxy http://proxy.company.com:8080
npm config set https-proxy http://proxy.company.com:8080
```

## Uninstallation

### Windows

```powershell
# Uninstall Claude Code
npm uninstall -g claude-code

# Remove environment variable (if set)
[System.Environment]::SetEnvironmentVariable("CLAUDE_CODE_GIT_BASH_PATH", $null, "User")
```

### macOS/Linux

```bash
npm uninstall -g claude-code
```

## Support

For additional help:
- Check [Troubleshooting Guide](troubleshooting.md)
- Open an [issue on GitHub](https://github.com/alex-feel/claude-code-toolbox/issues)
- Visit [official documentation](https://docs.anthropic.com/claude-code)
