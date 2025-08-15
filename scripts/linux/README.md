# Linux Scripts

Shell scripts for installing and configuring Claude Code on Linux systems.

## 📋 Available Scripts

### install-claude-linux.sh

Base installer for Claude Code on Linux distributions.

**Features:**
- Automatic dependency installation (Git, Node.js)
- Distribution detection (Ubuntu, Debian, Fedora, Arch, etc.)
- Package manager selection (apt, yum, dnf, pacman)
- Environment variable configuration
- PATH management
- Installation verification

**Usage:**
```bash
# Standard installation
bash install-claude-linux.sh

# Make executable and run
chmod +x install-claude-linux.sh
./install-claude-linux.sh
```

**Requirements:**
- Linux distribution with bash 4.0+
- Internet connection
- sudo privileges (for system packages)

### setup-python-environment.sh

Complete Python development environment setup for Claude Code.

**Features:**
- Runs base installer if Claude Code not present
- Downloads 7 Python-optimized subagents
- Installs 6 custom slash commands
- Configures Context7 MCP server
- Sets up Python developer system prompt
- Creates convenience launcher script

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
| Global Command | `~/.local/bin/claude-python` | System-wide command (symlink) |

## 🐧 Distribution Support

Tested on:
- **Ubuntu** 20.04, 22.04, 24.04
- **Debian** 10, 11, 12
- **Fedora** 37, 38, 39
- **CentOS** Stream 8, 9
- **RHEL** 8, 9
- **Arch Linux** (rolling)
- **openSUSE** Leap, Tumbleweed
- **Alpine Linux** 3.18+

## 📦 Package Managers

Scripts automatically detect and use:

| Distribution | Package Manager | Node.js Installation |
|-------------|----------------|---------------------|
| Ubuntu/Debian | apt | NodeSource repository |
| Fedora/RHEL | dnf/yum | NodeSource repository |
| Arch/Manjaro | pacman | Community repository |
| openSUSE | zypper | Official repository |
| Alpine | apk | Community repository |

## 🔧 Shell Configuration

Scripts update appropriate shell configuration files:

```bash
# Bash
~/.bashrc
~/.bash_profile

# Zsh
~/.zshrc
~/.zprofile

# Fish
~/.config/fish/config.fish
```

## 🌐 Proxy Configuration

For corporate environments:

```bash
# Set proxy before running scripts
export HTTP_PROXY="http://proxy.company.com:8080"
export HTTPS_PROXY="http://proxy.company.com:8080"
export NO_PROXY="localhost,127.0.0.1"

# For authenticated proxies
export HTTP_PROXY="http://username:password@proxy.company.com:8080"

# Make permanent (add to ~/.bashrc)
echo 'export HTTP_PROXY="http://proxy:8080"' >> ~/.bashrc
```

## 🛡️ Security Considerations

### Script Verification

```bash
# Check script contents before running
cat install-claude-linux.sh | less

# Verify checksum (if provided)
sha256sum install-claude-linux.sh

# Run with restricted permissions
bash -r install-claude-linux.sh
```

### Permissions

```bash
# Make scripts executable
chmod +x setup-python-environment.sh

# Check file permissions
ls -la *.sh

# Restrict to owner only
chmod 700 setup-python-environment.sh
```

## 📝 Script Options

### Environment Variables

Scripts respect these environment variables:

```bash
# Custom Claude directory
export CLAUDE_USER_DIR="/custom/path/.claude"

# Skip confirmations
export CLAUDE_SKIP_CONFIRM="true"

# Verbose output
export CLAUDE_VERBOSE="true"
```

### Command Line Options

#### setup-python-environment.sh
```bash
# Skip installation
--skip-install    # Skip Claude Code installation

# Force overwrite
--force          # Overwrite existing files

# Help
--help           # Show usage information
```

## 🔍 Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| "Permission denied" | Use `chmod +x` or run with `bash` |
| "Command not found" | Source shell config or restart terminal |
| "Unable to locate package" | Update package lists: `sudo apt update` |
| "No such file or directory" | Check working directory and paths |
| "Connection refused" | Check proxy settings and firewall |

### Debugging

Enable debug mode:

```bash
# Debug output
set -x
bash setup-python-environment.sh
set +x

# Verbose mode
bash -v setup-python-environment.sh

# Trace execution
bash -x setup-python-environment.sh
```

### Logging

Capture output for troubleshooting:

```bash
# Log to file
bash setup-python-environment.sh 2>&1 | tee install.log

# Separate stdout and stderr
bash setup-python-environment.sh > install.log 2> error.log

# With timestamps
bash setup-python-environment.sh | ts '[%Y-%m-%d %H:%M:%S]' | tee install.log
```

## 🚀 Quick Start Examples

### Fresh Python Developer Setup

```bash
# One-liner from web
curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-python-environment.sh | bash

# Or download and run
wget https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-python-environment.sh
chmod +x setup-python-environment.sh
./setup-python-environment.sh
```

**⚠️ After Setup - IMPORTANT:**
```bash
# You can now use the simple global command:
claude-python

# NOT this (won't have Python configuration):
claude  # ❌ No system prompt loaded!
```

### Update Existing Installation

```bash
# Update configs without reinstalling Claude Code
./setup-python-environment.sh --skip-install --force
```

### Custom Installation

```bash
# Set custom directory
export CLAUDE_USER_DIR="$HOME/my-claude"
./setup-python-environment.sh

# Non-interactive installation
yes | ./setup-python-environment.sh
```

## 📁 File Structure

After running scripts:

```text
~/
├── .claude/
│   ├── agents/           # Subagent configurations
│   ├── commands/         # Slash commands
│   ├── prompts/          # System prompts
│   ├── settings.json     # User settings
│   └── start-python-claude.sh  # Launcher script
├── .local/
│   └── bin/
│       └── claude        # Claude Code executable
└── .bashrc              # Updated with PATH
```

## 🔄 Updates and Maintenance

### Updating Scripts

```bash
# Using git
git pull origin main

# Or re-download
curl -fsSL -o setup-python-environment.sh \
  https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/setup-python-environment.sh
```

### Cleaning Up

```bash
# Remove Claude Code configurations
rm -rf ~/.claude

# Uninstall Claude Code
npm uninstall -g claude-code

# Remove from PATH (edit ~/.bashrc)
nano ~/.bashrc
# Remove claude-related PATH entries
```

## 🐳 Docker Support

Run in a container:

```dockerfile
# Dockerfile example
FROM ubuntu:22.04
RUN apt-get update && apt-get install -y curl bash
COPY setup-python-environment.sh /tmp/
RUN bash /tmp/setup-python-environment.sh
```

```bash
# Build and run
docker build -t claude-python .
docker run -it claude-python claude
```

## 🤖 Automation

### Systemd Service

Create a service for Claude Code:

```ini
# /etc/systemd/system/claude.service
[Unit]
Description=Claude Code Service
After=network.target

[Service]
Type=simple
User=your-user
ExecStart=/home/your-user/.local/bin/claude
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
# Enable service
sudo systemctl enable claude
sudo systemctl start claude
```

### Cron Jobs

Schedule Claude Code tasks:

```bash
# Edit crontab
crontab -e

# Daily Python environment update
0 2 * * * /path/to/setup-python-environment.sh --skip-install --force
```

## 🤝 Contributing

When modifying Linux scripts:

1. **Test on multiple distributions**
2. **Maintain POSIX compatibility**
3. **Use shellcheck for validation**
4. **Include error handling**
5. **Add inline documentation**

Example:

```bash
# Install shellcheck
sudo apt install shellcheck

# Check script
shellcheck setup-python-environment.sh

# Fix issues
shellcheck -f diff setup-python-environment.sh | patch
```

## 📚 Related Documentation

- [Installation Guide](../../docs/installing.md)
- [Python Setup Guide](../../docs/python-setup.md)
- [Troubleshooting](../../docs/troubleshooting.md)
- [Main README](../../README.md)
