# Quick Start Guide

Get up and running with Claude Code in minutes!

## Installation

### Windows

Open PowerShell and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "iex (irm 'https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/windows/install-claude-windows.ps1')"
```

### macOS

Open Terminal and run:

```bash
curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/macos/install-claude-macos.sh | bash
```

### Linux

Open Terminal and run:

```bash
curl -fsSL https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/scripts/linux/install-claude-linux.sh | bash
```

The installer automatically:
- Detects your operating system
- Installs Git (if needed)
- Installs Node.js LTS v18+ (if needed)
- Installs Claude Code CLI
- Configures your environment

### Verify Installation

After installation, open a new terminal and run:

```bash
claude doctor
```

You should see all checks pass:
- ✅ Claude Code CLI installed
- ✅ Git Bash available
- ✅ Node.js v18+ installed
- ✅ Environment configured

## First Steps with Claude Code

### 1. Start Claude

```bash
claude
```

### 2. Basic Commands

Ask Claude to help with your code:

```bash
# Get help with a specific file
claude "explain this function" main.py

# Generate code
claude "create a REST API endpoint for user authentication"

# Debug issues
claude "why is this test failing?" --include tests/

# Refactor code
claude "refactor this class to use dependency injection" src/service.py
```

### 3. IDE Integration

#### VS Code

1. Open VS Code
2. Open integrated terminal (Ctrl+`)
3. Run `claude`
4. The Claude extension installs automatically

#### JetBrains IDEs

1. Open Settings/Preferences
2. Go to Plugins
3. Search for "Claude Code"
4. Install and restart IDE

## Common Use Cases

### Working with Projects

```bash
# Navigate to your project
cd /path/to/your/project

# Start Claude with project context
claude

# Claude now understands your project structure
```

### Code Review

```bash
claude "review this code for security issues" src/auth.py
```

### Documentation

```bash
claude "generate documentation for this module" lib/api.py
```

### Testing

```bash
claude "write unit tests for this function" utils.js
```

## Tips for Best Results

1. **Be Specific**: Provide clear, detailed requests
2. **Include Context**: Reference specific files or functions
3. **Iterative Refinement**: Build on Claude's responses
4. **Use Examples**: Show Claude what you want

## Keyboard Shortcuts

While Claude is running:

- `Ctrl+C`: Cancel current operation
- `Ctrl+D`: Exit Claude (Unix-like systems)
- `Ctrl+Z`: Exit Claude (Windows)

## Configuration

Claude Code stores configuration in:
- Windows: `%APPDATA%\claude\`
- macOS/Linux: `~/.config/claude/`

## Next Steps

- Read the [full documentation](https://docs.anthropic.com/claude-code)
- Explore [agent templates](agents.md)
- Learn about [slash commands](slash-commands.md)
- Check [troubleshooting](troubleshooting.md) if you encounter issues

## Getting Help

- Run `claude --help` for command options
- Check [troubleshooting guide](troubleshooting.md)
- Open an issue on [GitHub](https://github.com/alex-feel/claude-code-toolbox/issues)

---

Happy coding with Claude! 🚀
