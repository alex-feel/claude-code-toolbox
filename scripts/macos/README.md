# macOS Scripts

Shell scripts for installing and configuring Claude Code on macOS systems.

## 📋 Available Scripts

### install-claude-macos.sh

Base installer for Claude Code on macOS.

**Features:**
- Automatic dependency installation (Git, Node.js)
- Homebrew detection and usage
- Xcode Command Line Tools verification
- Environment variable configuration
- PATH management for zsh/bash
- Installation verification

**Usage:**
```bash
# Standard installation
bash install-claude-macos.sh

# Make executable and run
chmod +x install-claude-macos.sh
./install-claude-macos.sh
```

**Requirements:**
- macOS 10.15 (Catalina) or later
- Internet connection
- Admin privileges (for some operations)

### setup-python-environment.sh

Complete Python development environment setup for Claude Code.

**Features:**
- Runs base installer if Claude Code not present
- Downloads 7 Python-optimized subagents
- Installs 6 custom slash commands
- Configures Context7 MCP server
- Sets up Python developer system prompt
- Creates convenience launcher script
- Optional macOS app creation

**Usage:**
```bash
# Full setup (installs Claude Code if needed)
bash setup-python-environment.sh

# Skip Claude Code installation
bash setup-python-environment.sh --skip-install

# Force overwrite existing files
bash setup-python-environment.sh --force

# Show help
bash setup-python-environment.sh --help
```

**What it installs:**

| Component | Location | Description |
|-----------|----------|-------------|
| Subagents | `~/.claude/agents/` | 7 Python-specific agents |
| Commands | `~/.claude/commands/` | 6 development commands |
| Prompts | `~/.claude/prompts/` | Python developer prompt |
| Launcher | `~/.claude/start-python-claude.sh` | Quick start script |
| Global Command | `/usr/local/bin/claude-python` or `~/.local/bin/claude-python` | System-wide command |
| App (optional) | `~/.claude/ClaudePython.app` | Double-clickable app |

## 🍎 macOS Version Support

Tested on:
- **macOS 14** (Sonoma)
- **macOS 13** (Ventura)
- **macOS 12** (Monterey)
- **macOS 11** (Big Sur)
- **macOS 10.15** (Catalina)

### Apple Silicon Support

Full native support for:
- **M3** (Pro/Max/Ultra)
- **M2** (Pro/Max/Ultra)
- **M1** (Pro/Max/Ultra)
- **Intel** processors

## 🍺 Homebrew Integration

Scripts automatically use Homebrew when available:

```bash
# Check if Homebrew is installed
brew --version

# Install Homebrew (if needed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# What gets installed via Homebrew
brew list | grep -E "node|git"
```

### Manual Homebrew Installation

```bash
# Install Node.js
brew install node

# Install Git
brew install git

# Then run Claude Code installer
npm install -g claude-code
```

## 🔧 Shell Configuration

Scripts detect and configure your default shell:

### Zsh (default since macOS Catalina)
```bash
# Configuration file
~/.zshrc

# Profile file
~/.zprofile

# Check current shell
echo $SHELL  # Should show /bin/zsh
```

### Bash (legacy)
```bash
# Configuration files
~/.bash_profile
~/.bashrc

# Switch to bash if preferred
chsh -s /bin/bash
```

### Fish (optional)
```bash
# Install fish
brew install fish

# Configuration
~/.config/fish/config.fish
```

## 🛡️ Security & Privacy

### Gatekeeper and Notarization

macOS may block unsigned scripts:

```bash
# Remove quarantine attribute
xattr -d com.apple.quarantine setup-python-environment.sh

# Check attributes
xattr -l setup-python-environment.sh

# Allow in System Settings
# System Settings > Privacy & Security > Allow
```

### Code Signing

For distribution:

```bash
# Sign script (requires Developer ID)
codesign --sign "Developer ID Application: Your Name" script.sh

# Verify signature
codesign --verify --verbose script.sh
```

## 🌐 Proxy Configuration

For corporate networks:

```bash
# Set proxy
export HTTP_PROXY="http://proxy.company.com:8080"
export HTTPS_PROXY="http://proxy.company.com:8080"
export NO_PROXY="localhost,127.0.0.1"

# Configure git proxy
git config --global http.proxy http://proxy.company.com:8080

# Configure npm proxy
npm config set proxy http://proxy.company.com:8080
npm config set https-proxy http://proxy.company.com:8080
```

## 📝 Script Options

### Environment Variables

```bash
# Custom installation directory
export CLAUDE_USER_DIR="$HOME/Documents/claude"

# Skip confirmations
export CLAUDE_SKIP_CONFIRM="true"

# Verbose output
export CLAUDE_VERBOSE="true"

# Use specific Node version
export NODE_VERSION="20"
```

### Command Line Options

#### setup-python-environment.sh
```bash
--skip-install    # Skip Claude Code installation
--force          # Overwrite existing files
--help           # Show usage information
```

## 🔍 Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| "xcrun: error" | Install Xcode Command Line Tools: `xcode-select --install` |
| "Permission denied" | Use `chmod +x` or check System Settings |
| "Operation not permitted" | Grant Terminal full disk access in System Settings |
| "Command not found" | Restart Terminal or run `source ~/.zshrc` |
| "SSL certificate problem" | Update certificates: `brew install ca-certificates` |

### System Integrity Protection (SIP)

If scripts fail due to SIP:

```bash
# Check SIP status
csrutil status

# Workaround (don't disable SIP)
# Install to user directory instead
export NPM_CONFIG_PREFIX="$HOME/.npm-global"
export PATH="$HOME/.npm-global/bin:$PATH"
```

### Debugging

```bash
# Enable debug mode
set -x
bash setup-python-environment.sh
set +x

# Verbose output
bash -v setup-python-environment.sh

# Check system logs
log show --predicate 'process == "Terminal"' --last 5m
```

## 🚀 Quick Start Examples

### Fresh Python Developer Setup

```bash
# One-liner from web
curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/setup-python-environment.sh | bash

# Or using Homebrew
brew tap alex-feel/claude-code-toolbox
brew install claude-python-setup
```

**⚠️ After Setup - IMPORTANT:**
```bash
# You can now use the simple global command:
claude-python

# Or double-click the app (if created):
open ~/.claude/ClaudePython.app

# NOT this (won't have Python configuration):
claude  # ❌ No system prompt loaded!
```

### Update Existing Installation

```bash
# Update configs only
./setup-python-environment.sh --skip-install --force

# Update everything including Claude Code
brew upgrade claude-code
./setup-python-environment.sh --force
```

## 📁 File Structure

After installation:

```text
~/
├── .claude/
│   ├── agents/           # Subagent configurations
│   ├── commands/         # Slash commands
│   ├── prompts/          # System prompts
│   ├── settings.json     # User settings
│   ├── start-python-claude.sh  # Launcher script
│   └── ClaudePython.app  # macOS app (optional)
├── .zshrc               # Updated with PATH
└── /usr/local/bin/
    └── claude           # Claude Code symlink
```

## 🎯 macOS-Specific Features

### Creating a macOS App

The setup script can create a double-clickable app:

```applescript
-- Created at ~/.claude/ClaudePython.app
on run
    do shell script "~/.claude/start-python-claude.sh"
end run
```

### Adding to Dock

```bash
# Add to Dock
defaults write com.apple.dock persistent-apps -array-add \
  '<dict><key>tile-data</key><dict><key>file-data</key><dict>\
  <key>_CFURLString</key><string>~/.claude/ClaudePython.app</string>\
  </dict></dict></dict>'

# Restart Dock
killall Dock
```

### Spotlight Integration

Make Claude Code searchable:

```bash
# Create alias in Applications
ln -s ~/.claude/ClaudePython.app /Applications/
```

## 🔄 Updates and Maintenance

### Using Homebrew

```bash
# Update Homebrew
brew update

# Upgrade Claude Code
brew upgrade claude-code

# Check for issues
brew doctor
```

### Manual Updates

```bash
# Update npm packages
npm update -g claude-code

# Update scripts
curl -fsSL -o setup-python-environment.sh \
  https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/setup-python-environment.sh
```

### Cleaning Up

```bash
# Remove configurations
rm -rf ~/.claude

# Uninstall via npm
npm uninstall -g claude-code

# Or via Homebrew
brew uninstall claude-code

# Clean PATH (edit ~/.zshrc)
nano ~/.zshrc
```

## 🤖 Automation

### LaunchAgent

Create auto-start service:

```xml
<!-- ~/Library/LaunchAgents/com.claude.python.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.claude.python</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/YOUR_USER/.claude/start-python-claude.sh</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
```

```bash
# Load service
launchctl load ~/Library/LaunchAgents/com.claude.python.plist
```

### Shortcuts App Integration

Create a shortcut that runs:
```bash
shortcuts run "Start Claude Python"
```

## 🤝 Contributing

When modifying macOS scripts:

1. **Test on multiple macOS versions**
2. **Support both Intel and Apple Silicon**
3. **Handle both zsh and bash**
4. **Use shellcheck for validation**
5. **Test with and without Homebrew**

```bash
# Install shellcheck
brew install shellcheck

# Check script
shellcheck setup-python-environment.sh

# Test on different shells
zsh -n setup-python-environment.sh  # Syntax check
bash -n setup-python-environment.sh  # Syntax check
```

## 📚 Related Documentation

- [Installation Guide](../../docs/installing.md)
- [Python Setup Guide](../../docs/python-setup.md)
- [Troubleshooting](../../docs/troubleshooting.md)
- [Main README](../../README.md)
